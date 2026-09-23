"""
Entartete Volumenelemente: zusammenfallende Knoten (23.09.2026).

Ein Sechsflaechner mit zusammenfallenden Knoten ist oft ein Keil, eine
Pyramide oder ein Tetraeder (so entartet z. B. der VQ83 von InfoGraph, und
Nastran-CHEXA oder Abaqus-C3D8 mit wiederholten Knoten). Bis zum 23.09.2026
galt jedes solche Element als "ohne Ausdehnung" und fiel aus der Rechnung;
ein Kragarm aus Keil-Sechsflaechnern rechnete mit 0,0 mm Durchbiegung, nur
mit einer WARNUNG. Seitdem wird eindeutig Umwandelbares umgewandelt
(solid.entartung_aufloesen, diagnose.entartete_umwandeln), nur echte
Nullkoerper fallen weg, und was Volumen hat und nicht eindeutig ist, haelt
die Rechnung mit Elementnummer an.

Aufruf:  python -m tests.test_entartung
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import diagnose, solver                             # noqa: E402
from statik3d.elements import solid as sl                         # noqa: E402
from statik3d.model import Material, Model                        # noqa: E402
from tests import pruefkoerper as pk                              # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")


def keil_kragarm(netz):
    """Kragarm, jede Zelle als zwei zum Keil entartete hex8 - dieselben Keile,
    die pk.quader("pent6") erzeugt."""
    kr = pk.Kragarm()
    m, ids = kr.modell("hex8", *netz)
    neu = []
    for e in m.elements:
        c = list(e.nodes)
        neu.append([c[0], c[1], c[2], c[2], c[4], c[5], c[6], c[6]])
        neu.append([c[0], c[2], c[3], c[3], c[4], c[6], c[7], c[7]])
    m.elements = []
    for kn in neu:
        m.add_element("hex8", kn, "S")
    return m, ids


def w_max(m):
    res = next(iter(solver.solve_all(m).cases.values()))
    return float(np.abs(np.asarray(res.u)[:, 2]).max())


def test_kragarm_aus_keil_sechsflaechnern():
    """Vorher w = 0 (alle 128 Elemente weggelassen), jetzt wie das pent6-Netz."""
    m, _ids = keil_kragarm((8, 2, 4))
    mp, _i = pk.Kragarm().modell("pent6", 8, 2, 4)
    w, wp = w_max(m), w_max(mp)
    check("Kragarm aus Keil-hex8 (8,2,4): Durchbiegung wie das pent6-Netz", abs(w - wp) <= 1e-12 * wp,
          f"{w * 1e3:.6f} mm gegen {wp * 1e3:.6f} mm")
    check("… alle 128 Elemente sind jetzt pent6", {e.typ for e in m.elements} == {"pent6"}
          and len(m.elements) == 128)
    z = [x for x in diagnose.meldungen(m) if "umgewandelt" in x]
    check("die Modellprüfung nennt Anzahl und Art (hex8→pent6: 128) und die Genauigkeit",
          len(z) == 1 and "hex8→pent6: 128" in z[0] and "Keils" in z[0], z[0][:90] if z else "")
    # Ruecknahmeprobe: ohne die Einordnung (jede Entartung "null") faellt alles weg
    m2, _ids = keil_kragarm((8, 2, 4))
    alt = diagnose._entartung
    diagnose._entartung = lambda model, i: ("null", model.elements[i].typ, model.elements[i].nodes, "")
    try:
        w_alt = w_max(m2)
    finally:
        diagnose._entartung = alt
    check("Rücknahmeprobe: mit dem alten Verhalten rechnet der Kragarm mit w = 0", w_alt == 0.0,
          f"{w_alt * 1e3:.6f} mm")


def einzel(typ, kn_lokal, name, soll_typ):
    """Ein Element aus dem Einheitswuerfel; Umwandlung ueber das Modell."""
    W = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
    m = Model("einzel")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=0.0))
    ids = [m.add_node(*p) for p in W]
    kn = [ids[k] for k in kn_lokal]
    m.add_element(typ, kn, "S")
    V0 = abs(sl.jacobi_volumen(typ, m.nodes[kn])["V"])
    zahl = diagnose.entartete_umwandeln(m)
    e = m.elements[0]
    d = sl.jacobi_volumen(e.typ, m.nodes[e.nodes])
    check(f"{name}: {typ} → {soll_typ}, Volumen erhalten, Jacobi ≥ 0",
          e.typ == soll_typ and abs(d["V"] - V0) < 1e-12 and d["det_min"] >= -1e-12
          and zahl == {f"{typ}→{soll_typ}": 1}, f"{e.typ}, V {d['V']:.4f} gegen {V0:.4f}")


def test_jede_umwandlung():
    einzel("hex8", [0, 1, 2, 2, 4, 5, 6, 6], "Keil (Deck- und Grundseite zu Dreiecken)", "pent6")
    einzel("hex8", [0, 1, 2, 3, 0, 1, 6, 7], "Keil (Seitenflächen zu Dreiecken)", "pent6")
    einzel("hex8", [0, 2, 1, 1, 4, 6, 5, 5], "Keil mit gespiegeltem Umlauf", "pent6")
    einzel("hex8", [0, 1, 2, 3, 6, 6, 6, 6], "Pyramide (Deckseite zu einem Punkt)", "pyr5")
    einzel("hex8", [0, 1, 3, 3, 4, 4, 4, 4], "Tetraeder aus dem Sechsflächner", "tet4")
    einzel("pent6", [0, 1, 3, 0, 5, 7], "Keil mit zusammengezogener Längskante", "pyr5")
    einzel("pent6", [0, 1, 3, 4, 4, 4], "Keil mit Deckdreieck zu einem Punkt", "tet4")
    einzel("pyr5", [0, 1, 2, 2, 4], "Pyramide mit zusammengezogener Grundkante", "tet4")


def test_nullkoerper_und_fehler():
    """Ein flacher Sechsflaechner (kein Volumen) faellt weiter weg, mit
    WARNUNG; ein Sechsflaechner mit nur einer zusammengezogenen Kante hat
    Volumen und keine eindeutige Umwandlung: FEHLER, die Rechnung haelt an."""
    kr = pk.Kragarm()
    m, _ids = kr.modell("hex8", 4, 1, 2)
    n0 = len(m.elements)
    kn = list(m.elements[0].nodes)
    m.add_element("hex8", [kn[0], kn[1], kn[2], kn[3], kn[0], kn[1], kn[2], kn[3]], "S")
    menge = diagnose.entartete_menge(m)
    check("Nullkörper (flacher hex8): fällt weiter weg", n0 in menge and m.elements[n0].typ == "hex8")
    check("… mit WARNUNG „ohne Ausdehnung“", any(z.startswith("WARNUNG") and "ohne Ausdehnung" in z
                                                  for z in diagnose.meldungen(m)))
    check("… und die Rechnung läuft", w_max(m) > 0.0)
    m2, _ids = kr.modell("hex8", 4, 1, 2)
    kn = list(m2.elements[3].nodes)
    m2.elements[3].nodes = [kn[0], kn[1], kn[2], kn[2], kn[4], kn[5], kn[6], kn[7]]
    z = [x for x in diagnose.meldungen(m2) if x.startswith("FEHLER") and "zusammenfallenden" in x]
    check("Sechsflächner mit einer zusammengezogenen Kante (Volumen > 0): FEHLER mit Elementnummer",
          len(z) == 1 and "Element 4 (hex8)" in z[0], z[0][:100] if z else "")
    try:
        w_max(m2)
        hielt = False
        text = "die Rechnung lief"
    except Exception as ex:                      # noqa: BLE001
        hielt = "Element 4 (hex8)" in str(ex)
        text = str(ex)[:100]
    check("… und die Rechnung hält dort an, statt es still wegzulassen", hielt, text)


def test_parallel_mit_stehendem_pool():
    """Der stehende Pool (parallel.Arbeiter) pickelt das Modell beim Oeffnen -
    geschah das vor der ersten Umwandlung, rechneten die Arbeiter mit den
    entarteten hex8 (det J an den Gausspunkten positiv, also ohne Fehler) und
    der Hauptprozess mit pent6 (Befund der Statik3D-Sitzung, 23.09.2026).
    Seriell und parallel muss w bitgleich zum pent6-Netz sein."""
    from statik3d import parallel
    alt_min, alt_w = parallel.settings().min_elements, parallel.settings().workers
    parallel.configure(min_elements=1, workers=2)
    try:
        mp, _i = pk.Kragarm().modell("pent6", 8, 2, 4)
        wp = float(np.abs(np.asarray(next(iter(solver.solve_all(mp, workers=1).cases.values())).u)[:, 2]).max())
        for w in (1, 2):
            m, _ids = keil_kragarm((8, 2, 4))
            r = next(iter(solver.solve_all(m, workers=w).cases.values()))
            ww = float(np.abs(np.asarray(r.u)[:, 2]).max())
            check(f"Keil-hex8-Kragarm mit {w} Arbeiter(n) (stehender Pool): w bitgleich zum pent6-Netz",
                  ww == wp, f"{ww * 1e3:.9f} mm gegen {wp * 1e3:.9f} mm")
        # Ruecknahmeprobe: ohne Umwandlung vor dem Pickeln rechnen die Arbeiter
        # mit den entarteten hex8 - gemessen 23.09.2026: "Singular matrix"
        m, _ids = keil_kragarm((8, 2, 4))
        vorher = parallel.vor_dem_pickeln
        parallel.vor_dem_pickeln = lambda model: None
        try:
            try:
                r = next(iter(solver.solve_all(m, workers=2).cases.values()))
                ww = float(np.abs(np.asarray(r.u)[:, 2]).max())
                falsch, text = ww != wp, f"{ww * 1e3:.9f} mm"
            except Exception as ex:              # noqa: BLE001
                falsch, text = True, f"{type(ex).__name__}: {str(ex)[:60]}"
        finally:
            parallel.vor_dem_pickeln = vorher
        check("Rücknahmeprobe: ohne Umwandlung vor dem Pickeln rechnet der Pool falsch oder bricht ab",
              falsch, text)
    finally:
        parallel.configure(min_elements=alt_min, workers=alt_w)


def main():
    print("=" * 100)
    print("STATIK3D - Entartete Volumenelemente (zusammenfallende Knoten)")
    print("=" * 100)
    for t in (test_kragarm_aus_keil_sechsflaechnern, test_jede_umwandlung, test_nullkoerper_und_fehler,
              test_parallel_mit_stehendem_pool):
        try:
            t()
        except Exception as ex:                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    ok = sum(1 for _n, o in RESULTS if o)
    print(f"\nErgebnis: {ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
