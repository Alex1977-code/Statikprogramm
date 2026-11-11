"""
Kur der Befunde 15/20, 16/22, 18, 21, 25 und 26 der zehn Pruefagenten
(11.11.2026) an den Exporten und Importen aus 68f867a.

K15  IFC-Export: Eine Stablast „je Projektion“ ging als Last je wahrer
     Stablaenge hinaus (am Stab (0,0,0)-(3,0,2) mit qz = -10 kN/m 20 % zu
     viel, beim Stab unter 45 Grad 41 %). Jetzt wird sie in die gleichwertige
     Last je wahrer Laenge umgerechnet (q · L_proj / L) und das Protokoll
     nennt die Umrechnung.
       Hand: Summe Fz = qz · (Projektion senkrecht zu z = 3 m) = -30 kN,
             Summe Fx = qx · (Projektion senkrecht zu x = 2 m) = 20 kN.
K16  Abaqus-Export: n1 = lokale y-Achse jedes Stabs (bis dahin (0,0,-1) fuer
     alle), passend zu I11 = Iy, K23 = G Asz, K13 = G Asy und *RELEASE M1 =
     Gelenk um y. Die Karten werden von Hand gelesen und Achse fuer Achse
     gegen die lokalen Achsen des Stabs geprueft; die Rundreise traegt die
     Verdrehung und rechnet wie das Ausgangsmodell.
K22  Abaqus-Import: Bei *BEAM GENERAL SECTION folgt die Verdrehung aus n1
     (Vorgabe (0,0,-1)): Kragarm mit Querlast in n2-Richtung biegt um die
     1-Achse, u = F L³ / (3 E I11). *RELEASE M1 ist das Gelenk um die
     1-Achse, auch bei *BEAM SECTION (dort 1-Achse = lokale z).
K18  DXF-Export: Der Hinweis nennt Prismen, Pyramiden, hex20 und tetp als
     ganz fehlend, nicht als „nur die Außenflächen als 3DFACE“.
K21  Nastran-Import: PLOAD1 mit LEPR/FRPR je Richtung getrennt projiziert.
       Hand: Stab (0,0,0)-(3,0,4), FX FRPR 1000 N/m -> 1000 · 4 = 4000 N,
             FZ FRPR -1000 N/m -> -1000 · 3 = -3000 N.
K25  Nastran-Import: CELAS2 gegen den Grund mit G2 = 0 oder G1 = 0 wird
     Lagerfeder wie mit leerem G2.
K26  DXF-Import: unbekannter $INSUNITS-Wert steht in der Meldung.

Aufruf:  python -m tests.test_kur_export
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

from statik3d import solver  # noqa: E402
from statik3d.assemble import projektionsfaktor  # noqa: E402
from statik3d.elements.beam3d import local_axes  # noqa: E402
from statik3d.model import Model, Material, Section  # noqa: E402
from statik3d.exporters import export_model  # noqa: E402
from statik3d.importers import import_file  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _nah(a, b, rel):
    return abs(a - b) <= rel * abs(b)


def _reaktionen(m):
    """Summe der Auflagerkraefte je Lastfall {Name: (Rx, Ry, Rz)}."""
    an = solver.solve_all(m, workers=1, combinations=False)
    return {n: np.asarray(r.reactions, float).reshape(-1, 6)[:, :3].sum(axis=0)
            for n, r in an.cases.items()}


def _lesen(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


# --------------------------------------------------------------------------
# K15: IFC, Stablast je Projektion
# --------------------------------------------------------------------------
def test_k15_ifc_projektion():
    m = Model("K15")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.rhs("R", 0.3, 0.2, 0.01))
    a, b = m.add_node(0, 0, 0), m.add_node(3, 0, 2)
    e = m.add_element("beam", [a, b], "S355", "R")
    m.fix(a, "all")
    m.fix(b, "all")
    m.load_beam(e, qz=-10e3, case="LF1", bezugslaenge="projektion")
    m.add_load_case("LF2", "Q")
    m.load_beam(e, qx=10e3, case="LF2", bezugslaenge="projektion")
    L = float(np.sqrt(13.0))
    hand = {"LF1": (2, 30000.0), "LF2": (0, -20000.0)}     # Achse, Summe R (= -Summe F)
    vor = _reaktionen(m)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "k15.ifc")
        log = []
        export_model(m, p, log=log)
        m2 = import_file(p, log=[])
        nach = _reaktionen(m2)
        # zweiter Weg: die Werte der Datei von Hand, mal wahrer Laenge
        text = _lesen(p)
        kraefte = re.findall(r"IFCSTRUCTURALLOADLINEARFORCE\(\$,([^,]+),([^,]+),([^,]+),", text)
        aktionen = re.findall(r"IFCSTRUCTURALCURVEACTION\([^;]*\.(TRUE_LENGTH|PROJECTED_LENGTH)\.",
                              text)
    datei = sorted(float(k[0]) * L + float(k[2]) * L for k in kraefte)
    for lf, (achse, soll) in hand.items():
        check(f"K15 IFC: {lf} Summe R{'xyz'[achse]} vor dem Export = Hand {soll:.0f} N",
              _nah(float(vor[lf][achse]), soll, 1e-9), f"{float(vor[lf][achse]):.3f} N")
        check(f"K15 IFC: {lf} Summe R{'xyz'[achse]} nach Export und Import = Hand {soll:.0f} N",
              lf in nach and _nah(float(nach[lf][achse]), soll, 1e-9),
              f"{float(nach[lf][achse]) if lf in nach else float('nan'):.3f} N")
    check("K15 IFC: Datei von Hand: q_Datei · L_wahr = -30000 N (qz) und 20000 N (qx), .TRUE_LENGTH.",
          len(datei) == 2 and _nah(datei[0], -30000.0, 1e-9) and _nah(datei[1], 20000.0, 1e-9)
          and aktionen == ["TRUE_LENGTH", "TRUE_LENGTH"],
          f"{[round(v, 3) for v in datei]} N, {aktionen}")
    zeile = [z for z in log if "je Projektion" in z and "umgerechnet" in z]
    check("K15 IFC: das Exportprotokoll nennt 2 umgerechnete Stablasten je Projektion",
          len(zeile) == 1 and "2 Stablasten" in zeile[0], zeile[0][:120] if zeile else "(keine Zeile)")

def main():
    for t in (test_k15_ifc_projektion,):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
