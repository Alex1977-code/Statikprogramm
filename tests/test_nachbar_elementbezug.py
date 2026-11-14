"""
Befund A'2 der Befundliste vom 14.11.2026 (zweite Runde), zur Behebung
freigegeben am 14.11.2026.

Seit Stand 50 nimmt der Vernetzer schon vernetzte Nachbarflaechen mit
(mesher.mit_vernetzten_nachbarn, Befund B9). Was am alten Netz eines solchen
Nachbarn hing, ging dabei still verloren: Elementlasten ohne Objektbezug,
Temperaturlasten, Abschaltungen in Situationen und Flaechenlager mit
Elementliste auf einem Teil der Flaeche. Platte 4 x 2 m aus F1/F2, 10 kN/m²
als Elementlast auf jeder Schale, gelenkig an x = 0 und x = 4, Eigengewicht:
ΣR_z 86,161 kN, nach dem Neuvernetzen nur von F2 6,161 kN, keine Meldung
(Belege ag_pruef2_10/t1*.py).

Jetzt uebertraegt der Vernetzer diese Angaben auf das neue Netz (ueber den
Elementmittelpunkt in den alten Elementen); laesst es sich fuer einen nicht
gewaehlten Nachbarn nicht eindeutig uebertragen, bricht er mit Klartext ab,
ohne etwas zu aendern.

Zwei Wege fuer die Zahlen: Handrechnung (p mal Flaeche, Eigengewicht
rho g t A) gegen die Summe der Auflagerkraefte aus dem Gleichungsloeser bzw.
die Summe p mal Elementflaeche der uebertragenen Lasten.

Aufruf:  python -m tests.test_nachbar_elementbezug
"""
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_nachbar_elementbezug_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import diagnose, mesher, solver                           # noqa: E402
from statik3d.model import (DofBehaviour, FaceLoad, Material, Model,     # noqa: E402
                            ShellProp, Situation)

RESULTS = []
#: Handrechnung: 10 kN/m² auf 8 m², Eigengewicht 7850 kg/m³ * 9,81 * 0,01 m * 8 m²
P = 10e3
G_HAND = 7850.0 * 9.81 * 0.01 * 8.0
RZ_HAND = P * 8.0 + G_HAND


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<96} {detail}")
    return bool(ok)


def still(f, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **kw)


def platte(h: float = 0.2) -> Model:
    """Platte 4 x 2 m aus F1 (x 0..2) und F2 (x 2..4), gemeinsame Linie L7,
    t = 10 mm, gelenkig an x = 0 und x = 4, LF1 mit Eigengewicht, Netz mit
    eigener Ziellaenge ``h``, vernetzt."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01))
    for p in [(0, 0, 0), (2, 0, 0), (4, 0, 0), (4, 2, 0), (2, 2, 0), (0, 2, 0)]:
        m.add_node(*p)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0)]):
        m.add_line(f"L{i + 1}", [a, b])
    m.add_line("L7", [1, 4])
    m.add_flaeche("F1", ["L1", "L7", "L5", "L6"], material="S235", dicke="D10")
    m.add_flaeche("F2", ["L2", "L3", "L4", "L7"], material="S235", dicke="D10")
    m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0, 0, -9.81]
    ls = m.add_line_support([], name="LL")
    ls.linien = ["L6", "L3"]
    for d in (0, 1, 2):
        ls.behaviour[d] = DofBehaviour("rigid")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = h
    m.netz.intelligent = False
    still(mesher.modell_vernetzen, m, [], workers=1)
    return m


def ecken(m, e) -> np.ndarray:
    el = m.elements[int(e)]
    n = 3 if len(el.nodes) in (3, 6) else 4
    return np.asarray(m.nodes, float)[[int(k) for k in el.nodes[:n]]]


def flaeche_el(m, e) -> float:
    Q = ecken(m, e)
    return float(np.linalg.norm(0.5 * np.cross(Q, np.roll(Q, -1, axis=0)).sum(axis=0)))


def mitte_x(m, e) -> float:
    return float(ecken(m, e)[:, 0].mean())


def summe_rz(m) -> float:
    r = still(solver.solve_all, m, workers=1, combinations=False).cases["LF1"]
    return float(np.asarray(r.reactions)[:, 2].sum())


def links(m) -> list:
    """Elemente von F1 mit Mittelpunkt x < 1 (die linke Haelfte von F1)."""
    return [int(e) for e in m.flaechen["F1"].elemente if mitte_x(m, e) < 1.0]


def teil_setzen(m) -> None:
    """Auf der linken Haelfte von F1 (1 x 2 m): Flaechenlager mit Elementliste,
    Elementlast 10 kN/m² (lokal z) in LF2 und Abschaltung in der Situation S1."""
    teil = links(m)
    ss = m.add_surface_support(teil, name="FL_teil")
    ss.behaviour[2] = DofBehaviour("spring", stiffness=1e7)
    m.add_load_case("LF2", "Q")
    for e in teil:
        m.case("LF2").face_loads.append(FaceLoad(elem=int(e), p=P))
    m.situationen["S1"] = Situation("S1", deaktiviert=list(teil))


def teil_werte(m) -> dict:
    ss = next(s for s in m.surface_supports if s.name == "FL_teil")
    return {"lager": sum(flaeche_el(m, e) for e in ss.elements),
            "last": sum(P * flaeche_el(m, fl.elem) for fl in m.case("LF2").face_loads),
            "aus": sum(flaeche_el(m, e) for e in m.situationen["S1"].deaktiviert),
            "links_last": all(mitte_x(m, fl.elem) < 1.0 for fl in m.case("LF2").face_loads),
            "entfallen": int(getattr(ss, "entfallen", 0) or 0),
            "lager_meldung": [b.text for b in diagnose.eingabepruefung(m) if "FL_teil" in b.text]}


# ---------------------------------------------------------------------------
def test_elementlasten_ganz(weg: str):
    """t1b/t1c: Elementlast auf jeder Schale, nur F2 neu vernetzen."""
    m = platte()
    for i, e in enumerate(m.elements):
        if e.typ.startswith("shell"):
            m.load_face(i, -P, direction=(0, 0, 1), case="LF1")
    rz0 = summe_rz(m)
    n0 = len(m.case("LF1").face_loads)
    if weg == "Befehl":
        log = []
        still(mesher.modell_vernetzen, m, log, workers=1, flaechen=[m.flaechen["F2"]], koerper=[])
    else:
        from tests.test_netz_teilvernetzen import gui_vernetzen
        log = gui_vernetzen(m, [m.flaechen["F2"]])
    rz1 = summe_rz(m)
    check(f"**A'2 ({weg}): ΣR_z nach dem Neuvernetzen von F2 wie vorher und wie von Hand "
          "(10 kN/m² · 8 m² + ρ g t A)**",
          abs(rz1 - RZ_HAND) <= 1e-6 * RZ_HAND and abs(rz0 - RZ_HAND) <= 1e-6 * RZ_HAND,
          f"vorher {rz0 / 1e3:.3f} kN, nachher {rz1 / 1e3:.3f} kN, Hand {RZ_HAND / 1e3:.3f} kN")
    check(f"… ({weg}): alle Elementlasten wieder da, das Protokoll nennt die Übertragung für F1",
          len(m.case("LF1").face_loads) == n0 and any("F1" in z and "übertragen" in z for z in log),
          f"{len(m.case('LF1').face_loads)} von {n0}; "
          + str([z[:110] for z in log if "übertragen" in z][:2]))


def test_teilmenge_gleiches_netz():
    """t1: Lager, Last und Abschaltung auf einem Teil von F1, nur F2 neu vernetzen."""
    m = platte()
    teil_setzen(m)
    vor = teil_werte(m)
    log = []
    still(mesher.modell_vernetzen, m, log, workers=1, flaechen=[m.flaechen["F2"]], koerper=[])
    nach = teil_werte(m)
    hand = 1.0 * 2.0
    check("**A'2: Teil von F1 (1 x 2 m) nach dem Neuvernetzen von F2 – Flächenlager, Elementlast und "
          "Abschaltung je 2,0 m² (Hand), Last 20 kN**",
          all(abs(nach[k] - hand) <= 1e-9 for k in ("lager", "aus")) and abs(nach["last"] - P * hand) <= 1e-6
          and abs(vor["lager"] - hand) <= 1e-9,
          f"vorher Lager {vor['lager']:.4f} m², nachher Lager {nach['lager']:.4f} m², Last "
          f"{nach['last'] / 1e3:.3f} kN, aus {nach['aus']:.4f} m²")
    check("… und das Lager gilt nicht als „Netz geändert“ (keine Meldung)",
          nach["entfallen"] == 0 and not nach["lager_meldung"], str(nach["lager_meldung"])[:160])


def test_teilmenge_neue_dichte():
    """Netz feiner (0,2 -> 0,1 m): die Teilmenge folgt ueber den Elementmittelpunkt."""
    m = platte(0.2)
    teil_setzen(m)
    n_alt = len(m.flaechen["F1"].elemente)
    m.netz.ziellaenge = 0.1
    log = []
    still(mesher.modell_vernetzen, m, log, workers=1, flaechen=[m.flaechen["F2"]], koerper=[])
    nach = teil_werte(m)
    n_neu = len(m.flaechen["F1"].elemente)
    hand = 2.0
    check("**A'2: neue Netzdichte (0,2 → 0,1 m) – Teil von F1 bleibt 2,0 m² (Lager, Abschaltung) und "
          "20 kN (Elementlast), nur links von x = 1 m**",
          n_neu > n_alt and abs(nach["lager"] - hand) <= 1e-9 and abs(nach["aus"] - hand) <= 1e-9
          and abs(nach["last"] - P * hand) <= 1e-6 and nach["links_last"],
          f"F1 {n_alt} → {n_neu} Elemente; Lager {nach['lager']:.4f} m², Last {nach['last'] / 1e3:.3f} kN, "
          f"aus {nach['aus']:.4f} m²")
    # zweiter Weg: Auflagerkraft der Elementlast aus dem Gleichungsloeser
    m.case("LF2").gravity = [0, 0, 0]
    for ss in list(m.surface_supports):
        m.surface_supports.remove(ss)
    r = still(solver.solve_all, m, workers=1, combinations=False).cases["LF2"]
    rz = float(np.asarray(r.reactions)[:, 2].sum())
    check("… zweiter Weg: |ΣR_z| aus LF2 = 20 kN (Gleichungslöser)", abs(abs(rz) - P * hand) <= 1e-6 * P,
          f"{rz / 1e3:.3f} kN")


def test_temperatur_ganz():
    """Temperaturlast auf allen Elementen von F1 (gleichmaessig) geht mit."""
    m = platte()
    for e in m.flaechen["F1"].elemente:
        m.load_temp(int(e), 30.0, 5.0, case="LF1")
    n = len(m.flaechen["F1"].elemente)
    m.netz.ziellaenge = 0.25
    still(mesher.modell_vernetzen, m, [], workers=1, flaechen=[m.flaechen["F2"]], koerper=[])
    tl = m.case("LF1").temp_loads
    f1 = set(int(e) for e in m.flaechen["F1"].elemente)
    check("**A'2: Temperaturlast (ΔT 30 K, ΔT_z 5 K) auf ganz F1 – nach dem Neuvernetzen auf jedem neuen "
          "Element von F1**",
          {int(t.elem) for t in tl} == f1 and all(t.dT == 30.0 and t.dT_z == 5.0 for t in tl) and len(f1) != n,
          f"{len(tl)} Temperaturlasten, F1 {n} → {len(f1)} Elemente")


def test_nicht_eindeutig():
    """Geometrie von F1 nach dem Vernetzen geaendert (Ecke verschoben): die
    Teilmenge hat im neuen Netz keinen eindeutigen Ort - Abbruch mit Klartext,
    nichts geaendert."""
    m = platte()
    teil_setzen(m)
    m.nodes[5] = [0.0, 2.5, 0.0]
    n_el = len(m.elements)
    n_last = len(m.case("LF2").face_loads)
    try:
        still(mesher.modell_vernetzen, m, [], workers=1, flaechen=[m.flaechen["F2"]], koerper=[])
        ex = None
    except ValueError as e:                    # mesher.NachbarElementbezug
        ex = e
    text = str(ex) if ex else ""
    check("**A'2: nicht eindeutig übertragbar (Geometrie von F1 geändert) – Abbruch mit Klartext, der "
          "Fläche, Lasten, Abschaltung und Lager nennt**",
          ex is not None and "F1" in text and "Elementlasten in LF2" in text and "Situation S1" in text
          and "FL_teil" in text and getattr(ex, "flaechen", None) == ["F1"],
          text[:220])
    check("… und nichts geändert (Elemente, Elementlasten)",
          len(m.elements) == n_el and len(m.case("LF2").face_loads) == n_last,
          f"{len(m.elements)}/{n_el} Elemente, {len(m.case('LF2').face_loads)}/{n_last} Lasten")
    # Gewaehlt hat der Anwender F1 selbst: dann wird vernetzt, und was keinen Ort
    # findet, steht als Warnung im Protokoll (nicht still)
    log = []
    still(mesher.modell_vernetzen, m, log, workers=1, flaechen=[m.flaechen["F2"], m.flaechen["F1"]], koerper=[])
    warn = [z for z in log if "F1" in z and ("übertragen" in z or "keinem alten Element" in z)]
    check("… F1 bewusst mit gewählt: vernetzt, das Protokoll nennt die Übertragung",
          bool(warn), warn[0][:200] if warn else str(log[-3:]))


def test_gui_abbruch():
    """Oberflaeche: der Abbruch kommt als Meldung, das Netz bleibt."""
    m = platte()
    teil_setzen(m)
    m.nodes[5] = [0.0, 2.5, 0.0]
    n_el = len(m.elements)
    from tests.test_netz_teilvernetzen import gui_vernetzen
    log = gui_vernetzen(m, [m.flaechen["F2"]])
    z = [x for x in log if "Vernetzen abgebrochen" in x]
    check("A'2 (Oberfläche): Abbruch steht im Protokoll, Netz unverändert",
          bool(z) and len(m.elements) == n_el, z[0][:160] if z else str(log[-3:]))


def main():
    for t in (lambda: test_elementlasten_ganz("Befehl"), lambda: test_elementlasten_ganz("Oberfläche"),
              test_teilmenge_gleiches_netz, test_teilmenge_neue_dichte, test_temperatur_ganz,
              test_nicht_eindeutig, test_gui_abbruch):
        try:
            t()
        except Exception as ex:                    # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{getattr(t, '__name__', 'test')} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
