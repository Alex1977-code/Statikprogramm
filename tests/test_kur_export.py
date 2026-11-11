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


# --------------------------------------------------------------------------
# K16 / K22: Abaqus, n1-Richtung, I11/I22, K13/K23, *RELEASE
# --------------------------------------------------------------------------
def _inp_karten(p):
    """Von Hand aus der .inp: {Element: Satz}, {Satz: (Werte, n1)},
    {Satz: (K23, K13)}, [*RELEASE-Zeilen]."""
    zeilen = [z.strip() for z in _lesen(p).splitlines()]
    satz_von, qs, schub, rel = {}, {}, {}, []
    k = 0
    while k < len(zeilen):
        z = zeilen[k]
        kopf = z.upper().replace(" ", "")
        if kopf.startswith("*ELEMENT,") and "TYPE=B31" in kopf:
            satz = re.search(r"ELSET=([^,]+)", kopf).group(1)
            k += 1
            while k < len(zeilen) and not zeilen[k].startswith("*"):
                satz_von[int(zeilen[k].split(",")[0])] = satz
                k += 1
            continue
        if kopf.startswith("*BEAMGENERALSECTION"):
            satz = re.search(r"ELSET=([^,]+)", kopf).group(1)
            werte = [float(v) for v in zeilen[k + 1].split(",")]
            n1 = np.array([float(v) for v in zeilen[k + 2].split(",")])
            qs[satz] = (werte, n1)
            if zeilen[k + 3].upper().startswith("*TRANSVERSE SHEAR STIFFNESS"):
                schub[satz] = tuple(float(v) for v in zeilen[k + 4].split(","))
            k += 3
            continue
        if kopf.startswith("*RELEASE"):
            k += 1
            while k < len(zeilen) and not zeilen[k].startswith("*"):
                rel.append(tuple(v.strip().upper() for v in zeilen[k].split(",")))
                k += 1
            continue
        k += 1
    return satz_von, qs, schub, rel


def _abaqus_modell():
    """Zweifeldtraeger entlang x (RHS 300x200x10, Iy != Iz) mit Gelenk um die
    lokale y-Achse am Anfang von Element 2, dazu ein schraeger Kragarm mit
    Verdrehung 30 Grad und Querlasten in beiden Richtungen."""
    m = Model("K16")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.rhs("R", 0.3, 0.2, 0.01))
    a, b, c = m.add_node(0, 0, 0), m.add_node(2, 0, 0), m.add_node(4, 0, 0)
    m.add_element("beam", [a, b], "S355", "R")
    m.add_element("beam", [b, c], "S355", "R", hinges=[4])
    m.fix(a, "all")
    m.fix(c, [0, 1, 2, 3])
    d, f = m.add_node(0, 3, 0), m.add_node(2, 4, 1.5)
    m.add_element("beam", [d, f], "S355", "R", roll=np.radians(30.0))
    m.fix(d, "all")
    m.load_node(b, Fy=2e3, Fz=-5e3, case="LF1")
    m.load_node(f, Fx=1e3, Fy=-3e3, Fz=-4e3, case="LF1")
    return m


def test_k16_abaqus_export():
    m = _abaqus_modell()
    s = m.sections["R"]
    G = m.materials["S355"].G
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "k16.inp")
        log = []
        export_model(m, p, log=log)
        satz_von, qs, schub, rel = _inp_karten(p)
        m2 = import_file(p, log=[])
    zitat = {k: (v[0][:5], v[1].tolist()) for k, v in qs.items()}
    print("   Karten:", zitat, "Schub:", schub, "RELEASE:", rel)
    # n1 je Element = lokale y-Achse (n1 senkrecht zur Stabachse, Laenge 1)
    abw = []
    for i, e in enumerate(m.elements, 1):
        T3, _L = local_axes(m.nodes[e.nodes[0]], m.nodes[e.nodes[1]], float(e.roll or 0.0))
        n1 = qs[satz_von[i]][1]
        n2 = np.cross(T3[0], n1 / np.linalg.norm(n1))           # Abaqus: n2 = t x n1
        abw.append(max(float(np.abs(n1 - T3[1]).max()), float(np.abs(n2 - T3[2]).max())))
    check("K16 Abaqus: n1 jedes Stabs = lokale y-Achse, n2 = t x n1 = lokale z (auch mit Verdrehung 30°)",
          len(abw) == 3 and max(abw) < 1e-12, f"größte Abweichung {max(abw) if abw else float('nan'):.2e}")
    werte = [v[0] for v in qs.values()]
    check("K16 Abaqus: I11 = Iy (Biegung um n1 = y), I22 = Iz (um n2 = z), Iy != Iz",
          bool(werte) and all(_nah(w[1], s.Iy, 1e-15) and w[2] == 0.0 and _nah(w[3], s.Iz, 1e-15)
                              for w in werte) and abs(s.Iy - s.Iz) > 0.1 * s.Iz,
          f"I11 {werte[0][1]:.6e}, I22 {werte[0][3]:.6e}; Iy {s.Iy:.6e}, Iz {s.Iz:.6e}")
    check("K16 Abaqus: K23 = G Asz (Schub in n2 = z), K13 = G Asy (Schub in n1 = y)",
          bool(schub) and all(_nah(k[0], G * s.Asz, 1e-15) and _nah(k[1], G * s.Asy, 1e-15)
                              for k in schub.values()) and abs(s.Asy - s.Asz) > 0.1 * s.Asy,
          f"{list(schub.values())[:1]}; G Asz {G * s.Asz:.6e}, G Asy {G * s.Asy:.6e}")
    check("K16 Abaqus: *RELEASE „2, S1, M1“ - Gelenk um die lokale y-Achse = n1-Achse",
          rel == [("2", "S1", "M1")], f"{rel}")
    check("K16 Abaqus: kein Hinweis „Stabverdrehung nicht übertragen“ mehr (sie steht als n1 in der Datei)",
          not any("Stabverdrehung" in z for z in log), "")
    # Rundreise: Verdrehung und Gelenk zurueck, Rechnung wie am Ausgangsmodell
    rolle = [float(e.roll or 0.0) for e in m2.elements]
    gel = [sorted(int(h) for h in (e.hinges or [])) for e in m2.elements]
    check("K16 Abaqus-Rundreise: Verdrehung 30° und Gelenk FHG 4 kommen zurück",
          len(rolle) == 3 and abs(rolle[0]) < 1e-12 and abs(rolle[1]) < 1e-12
          and abs(np.degrees(rolle[2]) - 30.0) < 1e-9 and gel == [[], [4], []],
          f"Verdrehung {[round(float(np.degrees(r)), 9) for r in rolle]}°, Gelenke {gel}")
    an1 = solver.solve_all(m, workers=1, combinations=False)
    an2 = solver.solve_all(m2, workers=1, combinations=False)
    u1 = np.asarray(next(iter(an1.cases.values())).u, float)
    u2 = np.asarray(next(iter(an2.cases.values())).u, float)
    rel_u = float(np.abs(u2 - u1).max() / np.abs(u1).max()) if u1.shape == u2.shape else float("inf")
    check("K16 Abaqus-Rundreise rechnet alle Verschiebungen wie das Ausgangsmodell",
          rel_u < 1e-9, f"größte Abweichung {rel_u:.2e} (bezogen auf max |u| {np.abs(u1).max() * 1e3:.4f} mm)")


INP_FREMD = """*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 2.0, 0.0, 0.0
*ELEMENT, TYPE=B31, ELSET={satz}
1, 1, 2
2, 2, 3
*MATERIAL, NAME=ST
*ELASTIC
2.1E11, 0.3
{schnitt}
*BOUNDARY
1, 1, 6
"""


def _fremd(schnitt, release=""):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "fremd.inp")
        with open(p, "w") as f:
            f.write(INP_FREMD.format(satz="B", schnitt=schnitt) + release)
        return import_file(p, log=[])


def _gelenkachsen(m):
    """Globale Achse jedes geloesten Drehfreiheitsgrads (lokal 4 = y, 5 = z)."""
    achsen = []
    for e in m.elements:
        T3, _L = local_axes(m.nodes[e.nodes[0]], m.nodes[e.nodes[1]], float(e.roll or 0.0))
        for h in (e.hinges or []):
            if int(h) % 6 in (4, 5):
                achsen.append(np.round(np.abs(T3[int(h) % 6 - 3]), 12).tolist())
    return achsen


def test_k22_abaqus_import():
    a, b = 0.1, 0.3                   # a in n1-Richtung, b in n2-Richtung (Abaqus)
    I11, I22 = a * b ** 3 / 12, b * a ** 3 / 12
    E, F, L = 2.1e11, 1e3, 2.0
    general = (f"*BEAM GENERAL SECTION, ELSET=B, MATERIAL=ST, SECTION=GENERAL\n"
               f"{a * b}, {I11}, 0.0, {I22}, 1e-5\n0.0, 0.0, -1.0")
    m = _fremd(general)
    m.load_node(2, Fy=F, case="LF1")          # Querlast in n2 = t x n1 = x x (-z) = +y
    u = float(np.asarray(next(iter(solver.solve_all(m, workers=1, combinations=False)
                                   .cases.values())).u)[2, 1])
    hand = F * L ** 3 / (3 * E * I11)         # Biegung um die 1-Achse (lotrecht)
    check("K22 Abaqus-Import GENERAL, n1 = (0,0,-1): Querlast in n2-Richtung biegt mit I11, "
          "u = F L³/(3 E I11)",
          _nah(u, hand, 1e-6), f"u {u * 1e3:.5f} mm, Hand {hand * 1e3:.5f} mm "
                               f"(mit I22 wären es {F * L ** 3 / (3 * E * I22) * 1e3:.5f} mm)")
    rel = "*RELEASE\n1, S2, M1\n"
    mg = _fremd(general, rel)
    mr = _fremd(f"*BEAM SECTION, ELSET=B, MATERIAL=ST, SECTION=RECT\n{a}, {b}\n0.0, 0.0, -1.0", rel)
    check("K22 Abaqus-Import: *RELEASE M1 ist das Gelenk um die 1-Achse = global z "
          "(bei GENERAL und bei RECT)",
          _gelenkachsen(mg) == [[0.0, 0.0, 1.0]] and _gelenkachsen(mr) == [[0.0, 0.0, 1.0]],
          f"GENERAL {_gelenkachsen(mg)}, RECT {_gelenkachsen(mr)}")


# --------------------------------------------------------------------------
# K18: DXF-Hinweis zu Volumen ohne 3DFACE
# --------------------------------------------------------------------------
def test_k18_dxf_volumen():
    punkte = {"pent6": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (0, 1, 1)],
              "pyr5": [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0.5, 0.5, 1)],
              "tet4": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]}
    for typ, pts in punkte.items():
        m = Model("K18")
        m.add_material(Material.steel("S355"))
        n = [m.add_node(*q) for q in pts]
        m.add_element(typ, n, "S355")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, typ + ".dxf")
            log = []
            export_model(m, p, log=log)
            n_face = _lesen(p).count("3DFACE")
        h = next((z for z in log if "DXF: nicht übertragen:" in z), "")
        if typ == "tet4":
            ok = n_face == 4 and "1 Volumenelement (nur die Außenflächen als 3DFACE)" in h
        else:
            ok = n_face == 0 and f"1 Volumenelement der Art {typ} (fehlt ganz" in h \
                and "nur die Außenflächen als 3DFACE)" not in h
        check(f"K18 DXF {typ}: {n_face} × 3DFACE, der Hinweis sagt, was geschrieben ist",
              ok, h[h.find("nicht übertragen"):][:150])


# --------------------------------------------------------------------------
# K26: DXF $INSUNITS unbekannt
# --------------------------------------------------------------------------
def test_k26_dxf_insunits():
    for code, soll in ((7, "$INSUNITS = 7"), (10, "$INSUNITS = 10"), (0, "fehlt im Kopf oder ist 0")):
        paare = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", str(code), "0", "ENDSEC",
                 "0", "SECTION", "2", "ENTITIES", "0", "LINE", "8", "0", "10", "0.0", "20", "0.0",
                 "30", "0.0", "11", "5.0", "21", "0.0", "31", "0.0", "0", "ENDSEC", "0", "EOF"]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "k26.dxf")
            with open(p, "w") as f:
                f.write("\n".join(paare) + "\n")
            log = []
            import_file(p, log=log)
        w = [z for z in log if "Längeneinheit" in z or "INSUNITS" in z]
        ok = len(w) == 1 and soll in w[0] and "Millimeter" in w[0]
        if code:
            ok = ok and "fehlt im Kopf" not in w[0]
        check(f"K26 DXF $INSUNITS = {code}: die Meldung nennt den Wert der Datei", ok,
              w[0][:150] if w else "(keine Meldung)")

def main():
    for t in (test_k15_ifc_projektion, test_k16_abaqus_export, test_k22_abaqus_import, test_k18_dxf_volumen, test_k26_dxf_insunits,):
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
