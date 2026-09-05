"""
Rechenbarkeit: Teiltragwerke ohne Lager, unvernetzte Geometrie, Kontakt-
gehaltene Teile - Diagnose, Modellpruefung und die Meldung des Solvers.
Aufruf:  python -m tests.test_diagnose
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, ShellProp, Flaeche, Kopplung, ContactSupport  # noqa: E402
from statik3d import diagnose as dg, solver  # noqa: E402
from statik3d.profiles import make_section  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")
    return ok


def _zwei_teile(lager_b=False):
    """Zwei Kragarme: Teil A (K0-K1) gelagert, Teil B (K2-K3) frei."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 200"))
    n = [m.add_node(0, 0, 0), m.add_node(2, 0, 0), m.add_node(0, 3, 0), m.add_node(2, 3, 0)]
    m.add_element("beam", [n[0], n[1]], "S235", "IPE 200")
    m.add_element("beam", [n[2], n[3]], "S235", "IPE 200")
    m.fix(n[0], "all")
    if lager_b:
        m.fix(n[2], "all")
    m.case()
    m.load_node(n[1], Fz=-1000.0)
    m.load_node(n[3], Fz=-1000.0)
    return m, n


def test_teiltragwerke():
    m, n = _zwei_teile()
    teile = dg.teiltragwerke(m)
    check("zwei Teiltragwerke, je zwei Knoten", len(teile) == 2 and sorted(len(g) for g in teile) == [2, 2])
    d = dg.diagnose(m)
    check("Teil B ohne Lager erkannt, nicht rechenbar", len(d["ohne_lager"]) == 1 and sorted(d["ohne_lager"][0]) == [n[2], n[3]]
          and not d["rechenbar"] and d["lose_knoten"] == 0)
    z = dg.meldungen(m, d)
    check("Meldung FEHLER mit Knoten und Teilezahl", any(x.startswith("FEHLER") and "K2" in x and "2 Teile" in x for x in z), str(z))
    check("Modellprüfung nennt das Teiltragwerk als FEHLER", any("Teiltragwerk" in x and x.startswith("FEHLER") for x in m.check()))
    # Kopplung verbindet die Teile
    m.kopplungen.append(Kopplung(n[1], n[3], [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [1e9, 1e9, 1e9]))
    d = dg.diagnose(m)
    check("Kopplung verbindet: ein Teil, rechenbar", d["teile"] == 1 and d["rechenbar"], str(d["teile"]))
    m.kopplungen.clear()
    # einseitiges Lager haelt Teil B nur ueber Kontakt
    m.contact_supports.append(ContactSupport(n[2], [0, 0, 1.0]))
    d = dg.diagnose(m)
    check("einseitiges Lager: Teil nur durch Kontakt gehalten (Hinweis, kein FEHLER)",
          not d["ohne_lager"] and len(d["nur_kontakt"]) == 1 and d["rechenbar"]
          and not any(x.startswith("FEHLER") for x in m.check()), str(m.check()))
    m.contact_supports.clear()
    # mit Lager an B alles in Ordnung
    m2, _ = _zwei_teile(lager_b=True)
    d2 = dg.diagnose(m2)
    check("beide Teile gelagert: rechenbar, keine Beanstandung", d2["rechenbar"] and not any(
        x.startswith("FEHLER") for x in m2.check()), str(m2.check()))


def test_unvernetzt():
    m, n = _zwei_teile(lager_b=True)
    m.add_shell_prop(ShellProp("t", 0.01))
    m.flaechen["F1"] = Flaeche("F1", dicke="t", material="S235", elemente=[])
    d = dg.diagnose(m)
    check("Fläche ohne Netz erkannt", d["unvernetzte_flaechen"] == ["F1"])
    check("Modellprüfung: WARNUNG „ohne Netz“, kein FEHLER", any("ohne Netz" in x and x.startswith("WARNUNG") for x in m.check())
          and not any(x.startswith("FEHLER") for x in m.check()), str(m.check()))


def test_solver_meldung():
    m, n = _zwei_teile()
    try:
        solver.solve_static(m)
        # SuperLU faktorisiert eine numerisch singulaere Matrix manchmal dennoch;
        # dann liefert die Modellpruefung die Meldung (vor dem Rechnen in der GUI)
        check("Solver oder Modellprüfung nennen das Teiltragwerk ohne Lager",
              any("Teiltragwerk" in x for x in m.check()))
    except RuntimeError as ex:
        check("Solver-Meldung erklärt das singuläre System (Teiltragwerk ohne Lager)",
              "Teiltragwerk" in str(ex) and "singulär" in str(ex), str(ex)[:120])
    text = dg.singulaer_text(m, "Factor is exactly singular")
    check("singulaer_text: Kopf, Ursache und Anweisung",
          text.startswith("Gleichungssystem singulär") and "Factor is exactly singular" in text
          and "Lager setzen" in text, text[:100])
    m2, _ = _zwei_teile(lager_b=True)
    text2 = dg.singulaer_text(m2)
    check("ohne topologischen Befund: Hinweis auf Gelenke/Nullsteifigkeit", "Gelenke" in text2)


def main():
    for f in (test_teiltragwerke, test_unvernetzt, test_solver_meldung):
        print(f"\n--- {f.__name__} ---")
        try:
            f()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
