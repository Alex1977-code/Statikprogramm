"""
Kur der aelteren Exportbefunde 17, 19/24 und 23 der zehn Pruefagenten
(11.11.2026, zur Behebung freigegeben am 12.11.2026).

A17  tetp2/3/4 und ebene3 bis ebene8 fehlten ohne Hinweis in Nastran,
     Abaqus, IFC und DXF. Jetzt: Nastran und Abaqus schreiben den Tetraeder
     mit Ordnung p als linearen Tetraeder ueber seine vier Eckknoten (CTETRA,
     C3D4) und sagen das; Nastran nennt die ebenen Elemente (keine Karte im
     Grundumfang), IFC nennt sie, DXF schreibt sie als 3DFACE wie die
     Schalen. Jeder Hinweis nennt Art und Anzahl.
       Hand: im Modell 1 tetp2, 1 tetp3, 1 ebene3, 1 ebene4.
A19  SAF: eine globale Stablast je Projektion in einer Achsrichtung geht mit
     Location "Projection" hinaus und kommt als Last je Projektion zurueck.
       Hand: Stab (0,0,0)-(3,0,3), qz = -10 kN/m je Projektion,
             Summe Fz = -10 kN/m * 3 m = -30 kN.
     Eine schraege Last je Projektion (mehrere Komponenten) kennt SAF nur je
     Richtung getrennt; sie geht als gleichwertige Last je wahrer Laenge
     hinaus (q * L_proj / L), das Protokoll nennt es.
       Hand: q = (5, 0, -10) kN/m, t = (1,0,1)/sqrt2, d = q/|q|:
             t.d = -5/sqrt(250), L_proj = L * sqrt(1 - (t.d)^2)
             = 4,2426 * 0,948683 = 4,02492 m, Summe Fx = 20,1246 kN,
             Summe Fz = -40,2492 kN.
A24  SAF: Lastfallkategorien kommen an (Action type, Load type, Blatt
     StructuralLoadGroup und die Statik3D-Spalte "Category"); was SAF nicht
     genau kennt, nennt der Hinweis.
A23  SAF: Federsteifigkeit der Knotenlager in MN/m bzw. MNm/rad, wie die
     SAF-Beschreibung (saf.guide, StructuralPointSupport) es vorschreibt.
       Hand: kz = 2e6 N/m -> 2 MN/m in der Datei; k_phiy = 5e5 Nm/rad ->
             0,5 MNm/rad. Am Kragarm (Feder am Ende) gleiche Verschiebung
             vor und nach dem Rundlauf.

Aufruf:  python -m tests.test_export_altbefunde
"""
import math
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

from statik3d import solver  # noqa: E402
from statik3d.model import Model, Material, Section, ShellProp  # noqa: E402
from statik3d.exporters import export_model  # noqa: E402
from statik3d.importers import import_file  # noqa: E402
from statik3d.importers.xlsx_reader import read_xlsx  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _nah(a, b, rel):
    return abs(a - b) <= rel * max(abs(b), 1e-30)


def _lesen(p):
    with open(p, encoding="latin-1", errors="replace") as f:
        return f.read()


def _reaktionen(m):
    an = solver.solve_all(m, workers=1, combinations=False)
    return {n: np.asarray(r.reactions, float).reshape(-1, 6)[:, :3].sum(axis=0)
            for n, r in an.cases.items()}


def _hinweis(log, fmt):
    z = [x for x in log if x.startswith(f"WARNUNG: {fmt}: nicht übertragen")]
    return z[0] if z else ""


# --------------------------------------------------------------------------
# A17: tetp und ebene Elemente in Nastran, Abaqus, IFC, DXF
# --------------------------------------------------------------------------
def _modell17():
    m = Model("A17")
    m.add_material(Material.steel("S355"))
    m.add_shell_prop(ShellProp("t", 0.01))
    t1 = [m.add_node(*p) for p in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]]
    m.add_element("tetp2", t1, "S355")
    t2 = [m.add_node(*p) for p in [(5, 0, 0), (6, 0, 0), (5, 1, 0), (5, 0, 1)]]
    m.add_element("tetp3", t2, "S355")
    k = [m.add_node(*p) for p in [(2, 0, 0), (3, 0, 0), (3, 1, 0), (2, 1, 0)]]
    m.add_element("ebene4", k, "S355", "t", zustand="spannung")
    d = [m.add_node(*p) for p in [(2, 2, 0), (3, 2, 0), (2, 3, 0)]]
    m.add_element("ebene3", d, "S355", "t", zustand="spannung")
    return m


def test_a17():
    m = _modell17()
    with tempfile.TemporaryDirectory() as tmp:
        # ---- Nastran -------------------------------------------------------
        p = os.path.join(tmp, "a17.bdf")
        log = []
        export_model(m, p, log=log)
        txt = _lesen(p)
        tet = [z.split() for z in txt.splitlines() if z.startswith("CTETRA")]
        knoten = sorted(tuple(int(v) for v in z[3:7]) for z in tet)
        check("A17 Nastran: zwei CTETRA mit den vier Eckknoten der beiden tetp (Knoten ab 1)",
              knoten == [(1, 2, 3, 4), (5, 6, 7, 8)], str(knoten))
        h = _hinweis(log, "Nastran")
        check("A17 Nastran: Hinweis nennt tetp2: 1, tetp3: 1 als lineare Tetraeder CTETRA",
              "tetp2: 1" in h and "tetp3: 1" in h and "CTETRA" in h, h[:200])
        check("A17 Nastran: Hinweis nennt die ebenen Elemente ebene3: 1, ebene4: 1 als fehlend",
              "ebene3: 1" in h and "ebene4: 1" in h, h[:300])
        m2 = import_file(p, log=[])
        check("A17 Nastran: Rundlauf gibt 2 Tetraeder tet4 zurück",
              sorted(e.typ for e in m2.elements) == ["tet4", "tet4"],
              str([e.typ for e in m2.elements]))
        # ---- Abaqus --------------------------------------------------------
        p = os.path.join(tmp, "a17.inp")
        log = []
        export_model(m, p, log=log)
        txt = _lesen(p)
        arten = re.findall(r"\*ELEMENT, TYPE=(\w+)", txt)
        check("A17 Abaqus: C3D4 für die tetp, CPS3 und CPS4 für die ebenen Elemente",
              sorted(arten) == ["C3D4", "CPS3", "CPS4"], str(arten))
        zeilen = txt.splitlines()
        kopf = next((z for z in zeilen if "TYPE=C3D4" in z), None)
        c3d4 = [] if kopf is None else [
            tuple(int(v) for v in zeilen[zeilen.index(kopf) + j].split(",")[1:]) for j in (1, 2)]
        check("A17 Abaqus: die C3D4 tragen die vier Eckknoten der tetp",
              sorted(c3d4) == [(1, 2, 3, 4), (5, 6, 7, 8)], str(c3d4))
        h = _hinweis(log, "Abaqus")
        check("A17 Abaqus: Hinweis nennt tetp2: 1, tetp3: 1 als lineare Tetraeder C3D4",
              "tetp2: 1" in h and "tetp3: 1" in h and "C3D4" in h, h[:200])
        # ---- IFC -----------------------------------------------------------
        p = os.path.join(tmp, "a17.ifc")
        log = []
        export_model(m, p, log=log)
        h = _hinweis(log, "IFC")
        check("A17 IFC: Hinweis nennt ebene3: 1, ebene4: 1 und weiter 2 Volumenelemente",
              "ebene3: 1" in h and "ebene4: 1" in h and "2 Volumenelemente" in h, h[:300])
        # ---- DXF -----------------------------------------------------------
        p = os.path.join(tmp, "a17.dxf")
        log = []
        export_model(m, p, log=log)
        txt = _lesen(p)
        flaechen = txt.count("3DFACE")
        # zweiter Weg: Eckpunkte von Hand aus der Datei
        bl = txt.split("3DFACE")[1:]
        ecken = []
        for s in bl:
            w = s.split("\n")
            paare = {w[i].strip(): w[i + 1].strip() for i in range(1, min(len(w) - 1, 30), 2)}
            ecken.append(tuple((float(paare[f"1{j}"]), float(paare[f"2{j}"])) for j in range(4)))
        soll = {((2.0, 0.0), (3.0, 0.0), (3.0, 1.0), (2.0, 1.0)),
                ((2.0, 2.0), (3.0, 2.0), (2.0, 3.0), (2.0, 3.0))}
        check("A17 DXF: zwei 3DFACE mit den Ecken der ebenen Elemente (Dreieck: 4. = 3. Punkt)",
              flaechen == 2 and set(ecken) == soll, f"{flaechen} 3DFACE, {ecken}")
        h = _hinweis(log, "DXF")
        check("A17 DXF: Hinweis nennt ebene3: 1, ebene4: 1 (als 3DFACE) und die tetp als fehlend",
              "ebene3: 1" in h and "ebene4: 1" in h and "tetp2" in h and "tetp3" in h, h[:400])


# --------------------------------------------------------------------------
# A19 / A24: SAF, Stablast je Projektion und Lastfallkategorien
# --------------------------------------------------------------------------
KATEGORIEN = {"LF1": "G", "LF2": "S", "LF3": "W", "LF4": "Q_B", "LF5": "H", "LF6": "A",
              "LF7": "SET"}


def _modell19():
    m = Model("A19")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.rhs("R", 0.3, 0.2, 0.01))
    a, b = m.add_node(0, 0, 0), m.add_node(3, 0, 3)
    e = m.add_element("beam", [a, b], "S355", "R")
    m.fix(a, "all")
    m.fix(b, "all")
    for lf, kat in KATEGORIEN.items():
        if lf in m.load_cases:
            m.load_cases[lf].category = kat
        else:
            m.add_load_case(lf, kat)
    m.load_beam(e, qz=-10e3, case="LF1", bezugslaenge="projektion")
    m.load_beam(e, qx=5e3, qz=-10e3, case="LF2", bezugslaenge="projektion")
    L = math.sqrt(18.0)
    m.load_beam(e, qz=-10e3, q2=[0.0, 0.0, -20e3], a=1.0, b=3.0, case="LF3",
                bezugslaenge="projektion")
    m.load_beam(e, qy=-2e3, case="LF4")
    return m, L


def test_a19_a24():
    m, L = _modell19()
    vor = _reaktionen(m)
    f2 = math.sqrt(1.0 - (-5.0 / math.sqrt(250.0)) ** 2)
    hand = {"LF1": (0.0, 0.0, 30000.0), "LF2": (-5e3 * L * f2, 0.0, 10e3 * L * f2)}
    for lf, soll in hand.items():
        check(f"A19 SAF: {lf} Summe R vor dem Export = Hand {tuple(round(v, 1) for v in soll)} N",
              all(_nah(float(vor[lf][k]), soll[k], 1e-9) or abs(soll[k]) < 1e-9
                  and abs(float(vor[lf][k])) < 1e-6 for k in range(3)),
              str(np.round(vor[lf], 3)))
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "a19.xlsx")
        log = []
        export_model(m, p, log=log)
        bl = read_xlsx(p)
        ilog = []
        m2 = import_file(p, log=ilog)
    nach = _reaktionen(m2)
    # ---- Datei von Hand ----------------------------------------------------
    ca = bl["StructuralCurveAction"]
    kopf = ca[0]
    sp = {n: kopf.index(n) for n in ("Direction", "Value 1 [kN/m]", "Value 2 [kN/m]",
                                     "Load case", "Location")}
    zeilen = {}
    for z in ca[1:]:
        zeilen.setdefault(z[sp["Load case"]], []).append(z)
    lf1 = zeilen.get("LF1", [])
    check("A19 SAF-Datei: LF1 eine Zeile Z, -10 kN/m, Location Projection",
          len(lf1) == 1 and lf1[0][sp["Direction"]] == "Z"
          and _nah(float(lf1[0][sp["Value 1 [kN/m]"]]), -10.0, 1e-12)
          and lf1[0][sp["Location"]] == "Projection", str(lf1))
    lf2 = zeilen.get("LF2", [])
    summe = {z[sp["Direction"]]: float(z[sp["Value 1 [kN/m]"]]) * L for z in lf2}
    check("A19 SAF-Datei: LF2 (schräg) als Length, Wert · wahre Länge = Hand 20,1246 / -40,2492 kN",
          len(lf2) == 2 and all(z[sp["Location"]] == "Length" for z in lf2)
          and _nah(summe.get("X", 0.0), 5.0 * L * f2, 1e-9)
          and _nah(summe.get("Z", 0.0), -10.0 * L * f2, 1e-9), str(summe))
    lf3 = zeilen.get("LF3", [])
    check("A19 SAF-Datei: LF3 (trapezförmig, Abschnitt) mit Location Projection",
          len(lf3) == 1 and lf3[0][sp["Location"]] == "Projection", str(lf3))
    zeile = [z for z in log if "je Projektion" in z and "umgerechnet" in z]
    check("A19 SAF: Protokoll nennt 1 Stablast je Projektion, in Last je wahrer Länge umgerechnet",
          len(zeile) == 1 and "1 Stablast" in zeile[0], zeile[0][:200] if zeile else "(keine Zeile)")
    # ---- Rundlauf ----------------------------------------------------------
    for lf in ("LF1", "LF2", "LF3", "LF4"):
        ok = lf in nach and np.allclose(nach[lf], vor[lf], rtol=1e-9, atol=1e-6)
        check(f"A19 SAF: {lf} Summe R nach Export und Import = vorher",
              ok, f"vorher {np.round(vor[lf], 3)}, nachher "
                  f"{np.round(nach[lf], 3) if lf in nach else '-'}")
    proj = [b.bezugslaenge for b in m2.load_cases["LF1"].beam_loads] if "LF1" in m2.load_cases else []
    warn = [z for z in ilog if "Projektion als wahre" in z]
    check("A19 SAF: LF1 kommt als Last je Projektion zurück, ohne Warnung „als wahre Länge“",
          proj == ["projektion"] and not warn, f"{proj} {warn}")
    # ---- Kategorien (A24) --------------------------------------------------
    kat = {n: lc.category for n, lc in m2.load_cases.items()}
    check("A24 SAF: Lastfallkategorien nach dem Rundlauf wie vorher",
          kat == KATEGORIEN, str(kat))
    lc = bl.get("StructuralLoadCase", [])
    k = lc[0] if lc else []
    act = {z[0]: z[k.index("Action type")] for z in lc[1:]} if "Action type" in k else {}
    check("A24 SAF-Datei: Action type Permanent (G, SET), Variable (S, W, Q_B, H), Accidental (A)",
          act == {"LF1": "Permanent", "LF2": "Variable", "LF3": "Variable", "LF4": "Variable",
                  "LF5": "Variable", "LF6": "Accidental", "LF7": "Permanent"}, str(act))
    lt = {z[0]: z[k.index("Load type")] for z in lc[1:]} if "Load type" in k else {}
    check("A24 SAF-Datei: Load type Snow (S), Wind (W)",
          lt.get("LF2") == "Snow" and lt.get("LF3") == "Wind", str(lt))
    grp = bl.get("StructuralLoadGroup", [])
    namen = {z[k.index("Load group")] for z in lc[1:]} if "Load group" in k else set()
    check("A24 SAF-Datei: Blatt StructuralLoadGroup führt jede Lastgruppe der Lastfälle",
          len(grp) > 1 and namen <= {z[0] for z in grp[1:]}, f"{namen} / {grp}")
    h = _hinweis(log, "SAF")
    check("A24 SAF: Hinweis nennt die Kategorien ohne genaue SAF-Entsprechung (H, SET)",
          "Lastfallkategorie" in h and "H" in h and "SET" in h and "Q_B" not in h, h[:400])


# --------------------------------------------------------------------------
# A23: SAF, Federsteifigkeit der Knotenlager
# --------------------------------------------------------------------------
def test_a23():
    m = Model("A23")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.rhs("R", 0.3, 0.2, 0.01))
    a, b = m.add_node(0, 0, 0), m.add_node(4, 0, 0)
    m.add_element("beam", [a, b], "S355", "R")
    m.fix(a, [0, 1, 2, 3, 5])
    m.fix(a, [4], stiffness=[5e5])                 # Drehfeder um y
    m.fix(b, [2], stiffness=[2e6])                 # Wegfeder in z
    m.load_node(b, Fz=-10e3, case="LF1")
    an = solver.solve_all(m, workers=1, combinations=False)
    uz_vor = float(an.cases["LF1"].u[b, 2])
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "a23.xlsx")
        export_model(m, p, log=[])
        bl = read_xlsx(p)
        m2 = import_file(p, log=[])
    sp = bl["StructuralPointSupport"]
    kopf = sp[0]
    print("   Kopf:", kopf)
    print("   Zeilen:", sp[1:])
    try:
        cz, cy = kopf.index("Stiffness Z [MN/m]"), kopf.index("Stiffness Fiy [MNm/rad]")
        werte = sorted(float(z[c]) for z in sp[1:] for c in (cz, cy) if z[c] not in (None, ""))
    except ValueError:
        werte = []
    check("A23 SAF-Datei: Stiffness Z [MN/m] = 2 und Stiffness Fiy [MNm/rad] = 0,5 (Hand)",
          werte == [0.5, 2.0], str(werte))
    k2 = sorted(float(k) for s in m2.supports for k in (s.stiffness or []))
    check("A23 SAF: nach dem Rundlauf kz = 2000000 N/m und k_phiy = 500000 Nm/rad",
          len(k2) == 2 and _nah(k2[0], 5e5, 1e-12) and _nah(k2[1], 2e6, 1e-12), str(k2))
    an2 = solver.solve_all(m2, workers=1, combinations=False)
    knoten = int(np.argmin(np.linalg.norm(m2.nodes - np.array([4.0, 0, 0]), axis=1)))
    uz_nach = float(an2.cases["LF1"].u[knoten, 2])
    check("A23 SAF: Verschiebung uz am Federende vor und nach dem Rundlauf gleich",
          _nah(uz_nach, uz_vor, 1e-9), f"vorher {uz_vor * 1e3:.4f} mm, nachher {uz_nach * 1e3:.4f} mm")


def main():
    for t in (test_a17, test_a19_a24, test_a23):
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
