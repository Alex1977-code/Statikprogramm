"""
Loeschen im Modell (Plan-Paket 14a, Nachzug 03.10.2026, Gegenpruefung der Taste Entf).

* Stab und Linie loeschen nehmen die Elementlasten und Knotenlasten mit, die
  ``Model.lasten_verteilen`` aus ihren Linienlasten gemacht hat (Kennzeichen
  ``_geo``). Bis dahin blieben sie wirksam und waren in der Lasttabelle
  unsichtbar - die Rechnung trug eine Last, die es nicht mehr gab.
* viele Knoten in einem Zug (``knoten_loeschen_viele``): dasselbe Ergebnis wie
  ``knoten_loeschen`` je Knoten von hinten nach vorn, aber ein Umnummerieren
  statt eines je Knoten. Strg+A und Entf an einem vernetzten Modell war
  quadratisch (``knoten_benutzt_von`` geht je Knoten durch alle Elemente).

Aufruf:  python -m tests.test_loeschen
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from statik3d import mesher, solver
from statik3d.model import Line, Material, Model, Section

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _balken(zwei_staebe: bool = False):
    """Ein Einfeldtraeger aus vier Elementen als Stab „A“ (mit dem zweiten Stab
    „B“ daneben), gelagert."""
    m = Model("Balken")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    m.add_section(Section.i_profile("IPE 300", 0.300, 0.150, 0.0071, 0.0107))
    n0 = len(m.elements)
    mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6.0, 0, 0), 4)
    m.add_member("A", list(range(n0, len(m.elements))))
    m.fix(0, [0, 1, 2, 3])
    m.fix(m.nn - 1, [1, 2])
    if zwei_staebe:
        n1 = len(m.elements)
        mesher.line_of_beams(m, "S235", "IPE 300", (0, 5.0, 0), (6.0, 5.0, 0), 4)
        m.add_member("B", list(range(n1, len(m.elements))))
        m.fix(m.nn - 5, [0, 1, 2, 3])
        m.fix(m.nn - 1, [1, 2])
    return m


def _geo(lc, liste):
    return [l for l in getattr(lc, liste) if getattr(l, "_geo", False)]


def test_stab_loeschen_nimmt_die_abgeleiteten_lasten_mit():
    m = _balken(zwei_staebe=True)
    q = 10e3
    m.add_linienlast("A", [0, 0, -q], art="stab")
    m.add_linienlast("B", [0, 0, -q], art="stab")
    m.lasten_verteilen()
    lc = m.case()
    n_alle = len(_geo(lc, "beam_loads"))
    check("Vorbereitung: beide Stäbe tragen abgeleitete Elementlasten (8 Stück)", n_alle == 8, str(n_alle))
    elem_a = set(m.members["A"].elements)
    check("… Stab A vier davon", sum(1 for b in _geo(lc, "beam_loads") if b.elem in elem_a) == 4)
    ohne_last = _balken(zwei_staebe=True)
    ohne_last.add_linienlast("B", [0, 0, -q], art="stab")
    ohne_last.lasten_verteilen()
    ohne_last.stab_loeschen("A")                    # Soll: A ist nie belastet gewesen
    soll = [(b.elem, round(b.a, 9), b.b, tuple(b.q)) for b in _geo(ohne_last.case(), "beam_loads")]
    grund = m.stab_loeschen("A")
    ist = [(b.elem, round(b.a, 9), b.b, tuple(b.q)) for b in _geo(lc, "beam_loads")]
    check("Stab A löschen: die abgeleiteten Elementlasten von A sind weg, die von B bleiben",
          grund == "" and len(ist) == 4 and not any(e in elem_a for e, *_ in ist), f"{len(ist)} Elementlasten")
    check("… und es sind genau die von B (Wert und Lage)", sorted(ist) == sorted(soll), str(ist[:2]))
    check("… die Linienlast von A ist weg, die von B bleibt",
          [ll.ziel for ll in lc.linienlasten] == ["B"], str([ll.ziel for ll in lc.linienlasten]))
    # Rechnung: ein Stab ohne seine Last verformt sich nicht
    m2 = _balken()
    m2.add_linienlast("A", [0, 0, -q], art="stab")
    m2.lasten_verteilen()
    w_vorher = float(np.abs(solver.solve_static(m2).u).max())
    m2.stab_loeschen("A")
    w_nachher = float(np.abs(solver.solve_static(m2).u).max())
    check("Rechnung: mit der Last verformt sich der Träger, nach dem Löschen des Stabs nicht mehr",
          w_vorher > 1e-4 and w_nachher < 1e-12, f"{w_vorher:.3e} -> {w_nachher:.3e} m")
    check("… die Lasttabelle zeigt nichts (n_loads)", m2.case().n_loads == 0, str(m2.case().n_loads))


def test_stab_ohne_linienlast_loeschen_fasst_die_lasten_nicht_an():
    m = _balken(zwei_staebe=True)
    m.add_linienlast("B", [0, 0, -5e3], art="stab")
    m.lasten_verteilen()
    vorher = [id(b) for b in m.case().beam_loads]
    m.stab_loeschen("A")                            # A trägt nichts: nichts neu verteilen
    check("Stab ohne Linienlast: die Elementlasten bleiben dieselben Objekte (kein Neuverteilen)",
          [id(b) for b in m.case().beam_loads] == vorher)


def test_linie_loeschen_nimmt_die_knotenlasten_mit():
    from tests.test_lasten import platte
    m = platte()
    ecke0 = int(mesher.select_nodes(m, xmin=-1e-6, xmax=1e-6, ymin=-1e-6, ymax=1e-6)[0])
    ecke1 = int(mesher.select_nodes(m, xmin=3 - 1e-6, ymin=-1e-6, ymax=1e-6)[0])
    m.lines["L1"] = Line("L1", [ecke0, ecke1])
    m.add_linienlast("L1", [0, 0, -4e3], art="linie", von=0.5, bis=2.5)
    n = m.lasten_verteilen()
    lc = m.case()
    check("Vorbereitung: die Linienlast hat Knotenlasten erzeugt", n == 9 and len(_geo(lc, "nodal_loads")) == 9, str(n))
    grund = m.linie_loeschen("L1")
    check("Linie löschen: auch die Knotenlasten daraus sind weg",
          grund == "" and not _geo(lc, "nodal_loads") and not lc.linienlasten,
          f"{len(_geo(lc, 'nodal_loads'))} Knotenlasten, {len(lc.linienlasten)} Linienlasten")
    r = solver.solve_static(m)
    check("Rechnung ohne die Last: Auflagerkräfte null", float(np.abs(r.reactions).max()) < 1e-6,
          f"{float(np.abs(r.reactions).max()):.3e} N")


def test_schleife_mit_einer_verteilung():
    """Für viele Stäbe auf einmal: ``verteilen=False`` und danach ein einziges
    ``lasten_verteilen`` - dasselbe Ergebnis wie je Stab verteilen."""
    a = _balken(zwei_staebe=True)
    b = _balken(zwei_staebe=True)
    for m in (a, b):
        m.add_linienlast("A", [0, 0, -1e3], art="stab")
        m.add_linienlast("B", [0, 0, -2e3], art="stab")
        m.lasten_verteilen()
    a.stab_loeschen("A")
    a.stab_loeschen("B")
    b.stab_loeschen("A", verteilen=False)
    b.stab_loeschen("B", verteilen=False)
    b.lasten_verteilen()
    check("Schleife mit verteilen=False und einem lasten_verteilen: dasselbe wie je Stab",
          not a.case().beam_loads and not b.case().beam_loads,
          f"{len(a.case().beam_loads)} / {len(b.case().beam_loads)}")


# ---------------------------------------------------------------------------
def _modell_mit_anhang():
    """Das Balkenmodell mit freien Knoten, an denen allerlei haengt, und mit
    benutzten Knoten (Element, Linie)."""
    m = _balken()
    m.add_linienlast("A", [0, 0, -1e3], art="stab")
    frei = []
    for i in range(12):
        k = m.add_node(10.0 + i, 1.0, 0.0)
        frei.append(k)
        if i % 3 == 0:
            m.fix(k, [0, 1, 2])
        if i % 2 == 0:
            m.load_node(k, Fz=-1e3 * (i + 1))
        if i % 4 == 1:
            m.add_zwangsverformung(k, [2], [1e-3])
        if i % 5 == 0:
            m.add_punktmasse(k, 100.0 + i)
        if i % 6 == 0:
            m.add_daempfer(k, -1, c=[1e3])
    m.layer_anlegen("Freie", knoten=frei[:6])
    k0, k1 = m.add_node(30.0, 0.0, 0.0), m.add_node(31.0, 0.0, 0.0)
    m.lines["LX"] = Line("LX", [k0, k1])
    m.lasten_verteilen()
    return m, frei, [k0, k1]


def _abbild(m) -> str:
    return json.dumps(m.to_dict(), sort_keys=True, default=str)


def test_viele_knoten_wie_einzeln():
    m, frei, benutzt = _modell_mit_anhang()
    wahl = frei[1:] + benutzt + [0, 2, 99999]       # frei, mit Linie, mit Element, nicht da
    a, b = m.copy(), m.copy()
    gruende_a = {}
    for i in sorted({int(x) for x in wahl}, reverse=True):
        g = a.knoten_loeschen(i)
        if g:
            gruende_a[i] = g
    gruende_b = b.knoten_loeschen_viele(wahl)
    check("viele Knoten in einem Zug: dieselben Gründe wie je Knoten einzeln",
          gruende_a == gruende_b and len(gruende_b) == 5, str(sorted(gruende_b)))
    check("… Knoten, Elemente, Lager, Lasten, Zwang, Masse, Dämpfer, Layer: Zustand identisch",
          _abbild(a) == _abbild(b), f"{a.nn} / {b.nn} Knoten")
    check("… elf freie Knoten sind verschwunden, die benutzten geblieben",
          b.nn == m.nn - len(frei) + 1 and "LX" in b.lines, f"{m.nn} -> {b.nn}")
    z = m.copy()
    check("Gegenprobe: ohne Auswahl (nur gesperrte) ändert sich nichts",
          z.knoten_loeschen_viele(benutzt + [0]) != {} and _abbild(z) == _abbild(m))
    check("knoten_gesperrt nennt dieselben Gründe, ohne etwas zu ändern",
          m.knoten_gesperrt(wahl) == gruende_a and _abbild(m) == _abbild(_modell_mit_anhang()[0]))


def test_viele_knoten_schnell():
    """Strg+A, Entf an einem vernetzten Modell: je Knoten ein Durchgang durch alle
    Elemente war quadratisch."""
    m = Model("Kette")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    m.add_section(Section.i_profile("IPE 300", 0.300, 0.150, 0.0071, 0.0107))
    n_el = 4000
    mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (float(n_el), 0, 0), n_el)
    alle = list(range(m.nn))
    t0 = time.time()
    gesperrt = m.knoten_loeschen_viele(alle)
    dt = time.time() - t0
    check("Kette mit 4001 Knoten und 4000 Elementen, alle gewählt: alle gesperrt, unter 2 s",
          len(gesperrt) == len(alle) and m.nn == len(alle) and dt < 2.0, f"{dt:.2f} s")
    # freie Knoten mit Lager und Last: die Hälfte des Modells
    for i in range(3000):
        k = m.add_node(10000.0 + i, 0.0, 0.0)
        m.fix(k, [0, 1, 2])
        m.load_node(k, Fz=-1e3)
    frei = list(range(len(alle), m.nn))
    t0 = time.time()
    gesperrt = m.knoten_loeschen_viele(frei)
    dt = time.time() - t0
    check("3000 freie Knoten mit Lager und Last in einem Zug: alle weg, unter 2 s",
          not gesperrt and m.nn == len(alle) and not any(sp.node >= m.nn for sp in m.supports)
          and dt < 2.0, f"{dt:.2f} s, {m.nn} Knoten, {len(m.supports)} Lager")


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_stab_loeschen_nimmt_die_abgeleiteten_lasten_mit,
              test_stab_ohne_linienlast_loeschen_fasst_die_lasten_nicht_an,
              test_linie_loeschen_nimmt_die_knotenlasten_mit, test_schleife_mit_einer_verteilung,
              test_viele_knoten_wie_einzeln, test_viele_knoten_schnell):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
