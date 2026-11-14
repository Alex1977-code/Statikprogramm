"""Einheiten und Kennwerte beim Import und Export (Befunde I1 bis I7, B11, B12 vom
14.11.2026, Gruppe B der Befundliste; vom Anwender am 14.11.2026 freigegeben).

* I3  RFEM 6: Eigengewicht aus der Wichte gamma wie RFEM (g der Datei), nicht aus
      rho * 9,81; Masse bleibt rho; ein frueher uebernommenes Modell meldet sich.
* I1  Importdialog: IFC und SDNF lesen ihre Einheit aus dem Dateikopf.
* I2  Tabellen im RFEM-Aufbau: Export und eigener Import passen zusammen (Rundlauf).
* I4  Einheiten in Kopfzeilen (MN/m³, N/mm³, kNcm/rad ...), unbekannte mit Warnung.
* I5  IFC: AREAUNIT, MOMENTOFINERTIAUNIT ... gelten fuer die Querschnittswerte.
* I6  Nastran und Abaqus in mm-N-MPa: das ganze System wird umgerechnet.
* I7  SDNF-Export mit „m“ wird abgelehnt (SDNF kennt nur mm und inch).
* B11 alte Statik3D-SAF-Datei (vor 12.11.2026): Federn in N/m, nicht 10⁶fach.
* B12 SAF ohne Spalte „Category“: Domestic ... Roofs -> Q_A ... Q_H, Seismic -> ERD.

Aufruf:  python -m tests.test_import_einheiten
"""
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_import_einheiten_"), "einstellungen.json")

from statik3d.model import Model, Material, Section, ShellProp     # noqa: E402

RESULTS = []
DATEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten")


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def close(name, ist, soll, tol_rel=1e-6, einheit=""):
    ok = ist is not None and abs(float(ist) - float(soll)) <= tol_rel * max(abs(float(soll)), 1e-30)
    return check(name, ok, f"ist {ist!r}{einheit}, soll {soll!r}{einheit}")


def _staebe(m):
    return [round(float(np.linalg.norm(m.nodes[e.nodes[1]] - m.nodes[e.nodes[0]])), 6)
            for e in m.elements if e.typ == "beam"]


def _rz(res) -> float:
    return float(np.asarray(res.reactions, float).reshape(-1, 6)[:, 2].sum())


# --------------------------------------------------------------------------
# I3: RFEM 6, Eigengewicht aus der Wichte
# --------------------------------------------------------------------------
def _rf6_mit_wichte(pfad, gamma=78500.0, rho=7850.0, g=10.0, ohne_rho=False):
    """Kragarm 4 m (Rundstahl d = 40 mm) mit Lastfall Eigengewicht; der Werkstoff
    traegt die Wichte gamma, ModelData die Erdbeschleunigung g (wie RFEM 6)."""
    from tests.test_rfem6 import INF, make_rf6
    make_rf6(pfad, nodes=[(0, 0, 0), (4, 0, 0)], lines=[[1, 2]], members=[(1, None, None)],
             supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1])],
             load_cases=[("Eigengewicht", 1, 1.0), ("Nutzlast", 2, 0.0)])
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(pfad) as z:
        namen = z.namelist()
        z.extractall(tmp)
    con = sqlite3.connect(os.path.join(tmp, "model.db"))
    con.execute("UPDATE MaterialPropertyDouble SET valueSI = ? WHERE propertyKey = 'rho'", (rho,))
    # die Kennwerte am Parameterprofil fuehren die Dichte mit (wie RFEM)
    con.execute("UPDATE SectionMaterialCharacteristics SET density = ?", (None if ohne_rho else rho,))
    if ohne_rho:
        nr = con.execute("SELECT container_order FROM MaterialProperties_propertiesMap_keys "
                         "WHERE value = 'rho'").fetchone()[0]
        con.execute("DELETE FROM MaterialProperties_propertiesMap_keys WHERE container_order = ?", (nr,))
        con.execute("DELETE FROM MaterialProperties_propertiesMap_values WHERE container_order = ?", (nr,))
    con.execute("INSERT INTO MaterialPropertyDouble VALUES (100,1,'gamma',?)", (gamma,))
    con.execute("INSERT INTO MaterialProperties_propertiesMap_keys VALUES (1,20,'gamma')")
    con.execute("INSERT INTO MaterialProperties_propertiesMap_values VALUES (1,20,100,'MaterialPropertyDouble')")
    if g is not None:
        con.execute("CREATE TABLE ModelData (id INTEGER PRIMARY KEY, gravitationalAcceleration REAL)")
        con.execute("INSERT INTO ModelData VALUES (1, ?)", (g,))
    con.commit()
    con.close()
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        for n in namen:
            z.write(os.path.join(tmp, n), n)
    shutil.rmtree(tmp, ignore_errors=True)
    return pfad


def test_i3_wichte():
    print("\n--- I3: RFEM 6, Eigengewicht aus der Wichte gamma ---")
    from statik3d import solver
    from statik3d import rechenverfahren as RV
    from statik3d.importers import import_file
    tmp = tempfile.mkdtemp()
    p = _rf6_mit_wichte(os.path.join(tmp, "kragarm.rf6"))
    log = []
    m = import_file(p, log=log)
    mat = next(iter(m.materials.values()))
    lc = next(lc for lc in m.load_cases.values() if np.any(lc.gravity))
    gz = abs(float(np.asarray(lc.gravity, float)[2]))
    close("I3 Wichte im Modell rho * |g| = gamma = 78 500 N/m³", mat.rho * gz, 78500.0, 1e-9, " N/m³")
    close("I3 Masse fuer Eigenformen bleibt rho = 7 850 kg/m³", mat.rho, 7850.0, 1e-12, " kg/m³")
    # zweiter Weg: Rechnung gegen Handwert gamma * A * L
    A = np.pi * 0.020 ** 2
    hand = 78500.0 * A * 4.0
    res = solver.solve_static(m, case=lc.name)
    close("I3 Rechnung: Summe R_z = gamma * A * L (Handwert 394,6 N)", abs(_rz(res)), hand, 1e-6, " N")
    check("I3 Protokoll nennt das Eigengewicht aus gamma mit g = 10",
          any("Wichte γ" in z and "g = 10" in z for z in log), str([z for z in log if "Wichte" in z])[:200])
    # gewichtsloses Material bleibt gewichtslos
    m0 = import_file(_rf6_mit_wichte(os.path.join(tmp, "null.rf6"), gamma=0.0, rho=0.0), log=[])
    check("I3 gewichtsloses Material (gamma = rho = 0) bleibt 0", next(iter(m0.materials.values())).rho == 0.0)
    # nur Wichte (ohne Dichte): rho = gamma / g, Gewicht = gamma
    m1 = import_file(_rf6_mit_wichte(os.path.join(tmp, "nur_gamma.rf6"), ohne_rho=True), log=[])
    mat1 = next(iter(m1.materials.values()))
    g1 = abs(float(np.asarray(next(lc for lc in m1.load_cases.values() if np.any(lc.gravity)).gravity)[2]))
    close("I3 nur Wichte: rho * |g| = gamma", mat1.rho * g1, 78500.0, 1e-9, " N/m³")
    # Merkmal: ein frueher (mit rho * 9,81) uebernommenes Modell meldet sich
    alt = import_file(p, log=[])
    alt.meta.pop("rfem_eigengewicht", None)
    for lc_ in alt.load_cases.values():
        if np.any(lc_.gravity):
            lc_.gravity = [0.0, 0.0, -9.81]
    # in Statik3D von Hand angesetztes Eigengewicht (in RFEM ohne): kam nicht vom Import
    alt.load_cases["LF2"].gravity = [0.0, 0.0, -9.81]
    alt._rfem_eigengewicht_abw = None
    mk = RV.merkmal("import_eigengewicht")
    check("I3 Merkmal import_eigengewicht in der Verfahrenstabelle, Stand 46, Fehlerkorrektur",
          mk is not None and mk.import_korrektur and mk.wechsel[-1].stand == 46
          and mk.wechsel[-1].art == RV.FEHLERKORREKTUR and RV.VERFAHRENSSTAND >= 46)
    check("I3 altes Modell (rho * 9,81) ist betroffen", mk is not None and mk.betrifft(alt))
    an = solver.solve_all(alt, workers=1, combinations=False)
    text = RV.betroffen(alt, RV.merkmale_der_datei({}, alt), an) if mk is not None else ""
    check("I3 Status nennt „Eigengewicht 1,9 % zu klein“ und „neu importieren“",
          "Eigengewicht 1,9 % zu klein" in text and "neu importieren" in text, text[:260])
    check("I3 Status nennt nur LF1 (Eigengewicht aus RFEM), nicht LF2 (von Hand)",
          "zu klein in LF1)" in text and "LF2" not in text, text[160:300])
    check("I3 neuer Import ist nicht betroffen", mk is not None and not mk.betrifft(m))
    for lc_ in alt.load_cases.values():
        if np.any(lc_.gravity):
            lc_.gravity = [0.0, 0.0, -10.0]
    check("I3 altes Modell mit g = 10 von Hand ist nicht mehr betroffen", mk is not None and not mk.betrifft(alt))
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# Modell fuer IFC, SDNF und Tabellen
# --------------------------------------------------------------------------
def modell(schale=True, flaechenlast=True):
    m = Model("R")
    m.add_material(Material.steel("S355"))
    m.add_material(Material("ALU", 70e9, 0.33, 2700.0, 2.3e-5))
    m.add_section(Section.from_profile("HEA 200"))
    q = Section("FREI", A=53.8e-4, Iy=3692e-8, Iz=1336e-8, It=20.98e-8)
    m.add_section(q)
    m.add_shell_prop(ShellProp("t12", 0.012))
    n = [m.add_node(*p) for p in ((0, 0, 0), (4, 0, 0), (8, 0, 0), (12, 0, 0),
                                  (0, 2, 0), (4, 2, 0), (4, 4, 0), (0, 4, 0))]
    m.add_element("beam", [n[0], n[1]], "S355", "HEA 200")
    m.add_element("beam", [n[1], n[2]], "S355", "HEA 200")
    m.add_element("beam", [n[2], n[3]], "ALU", "FREI")
    if schale:
        m.add_element("shell4", [n[4], n[5], n[6], n[7]], "S355", "t12")
        for k in (4, 5, 6, 7):
            m.fix(n[k], "pinned")
    m.fix(n[0], "all")
    m.support(n[3], "free", ux=dict(typ="spring", stiffness=5e6),
              uz=dict(typ="spring", stiffness=2e7), phiy=dict(typ="spring", stiffness=3e5))
    m.load_node(n[1], Fx=25e3, Fz=-40e3, My=12e3, case="LF1")
    m.load_beam(0, qz=-12e3, case="LF1")
    m.load_beam(1, qz=-5e3, q2=[0, 0, -15e3], case="LF1")
    m.load_beam(2, qy=2e3, system="local", case="LF1")
    if schale and flaechenlast:
        m.load_face(3, 3.5e3, case="LF1")
    m.add_load_case("LF2", "G", "EG")
    m.set_gravity(-9.81, case="LF2")
    m.add_load_case("LF3", "Q_A", "Nutzlast Wohnen")
    m.load_node(n[2], Fz=-1e3, case="LF3")
    m.auto_members()
    return m


def _ifc_in_mm(p_m, p_mm, flaeche_m2=True):
    """Eigene IFC (m) -> dieselbe Datei in mm; die Flaecheneinheit bleibt m² (so
    schreibt etwa Tekla den Kopf), die Profilmasse und die Dicke gehen in mm."""
    out = []
    for z in open(p_m, encoding="utf-8").read().splitlines():
        z = z.replace("IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)", "IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)")
        if "IFCCARTESIANPOINT((" in z:
            z = re.sub(r"IFCCARTESIANPOINT\(\(([^)]*)\)\)",
                       lambda mm: "IFCCARTESIANPOINT((" + ",".join(
                           f"{float(v) * 1000.0!r}" for v in mm.group(1).split(",")) + "))", z)
        elif "IFCISHAPEPROFILEDEF(" in z and "'HEA 200',$," in z:
            kopf, rest = z.split("'HEA 200',$,", 1)
            werte = rest.rstrip(");").split(",")
            z = kopf + "'HEA 200',$," + ",".join(f"{float(v) * 1000.0!r}" if v != "$" else v
                                                 for v in werte) + ");"
        elif "IFCSTRUCTURALSURFACEMEMBER(" in z:
            z = z.replace(",.SHELL.,0.012);", ",.SHELL.,12.0);")
        out.append(z)
    open(p_mm, "w", encoding="utf-8").write("\n".join(out) + "\n")


# --------------------------------------------------------------------------
# I1: Importdialog, Einheit aus dem Dateikopf
# --------------------------------------------------------------------------
def test_i1_dialog():
    print("\n--- I1: Importdialog, IFC und SDNF mit Einheit im Dateikopf ---")
    from PySide6 import QtWidgets
    from statik3d.exporters import export_model
    from statik3d.gui.dialogs import ImportDialog
    from statik3d.importers import import_file
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])   # noqa: F841
    tmp = tempfile.mkdtemp()
    p_m = os.path.join(tmp, "m.ifc")
    export_model(modell(flaechenlast=False), p_m, log=[])
    p_mm = os.path.join(tmp, "mm.ifc")
    _ifc_in_mm(p_m, p_mm)
    d = ImportDialog(None, p_mm, Model())
    opt = d.options()
    check("I1 IFC: vorgewählt „wie in der Datei: mm“", "wie in der Datei: mm" in d.unit.currentText(),
          d.unit.currentText())
    check("I1 IFC: der Dialog schickt keinen Längenmaßstab", "unit_scale" not in opt,
          str(opt.get("unit_scale")))
    m = import_file(p_mm, log=[], **opt)
    check("I1 IFC in mm mit den Optionen des Dialogs: Stäbe 4 m", _staebe(m) == [4.0, 4.0, 4.0], str(_staebe(m)))
    p_s = os.path.join(tmp, "m.sdnf")
    export_model(modell(), p_s, log=[])
    d = ImportDialog(None, p_s, Model())
    opt = d.options()
    check("I1 SDNF: vorgewählt „wie in der Datei: mm“, kein Maßstab",
          "wie in der Datei: mm" in d.unit.currentText() and "unit_scale" not in opt, d.unit.currentText())
    m = import_file(p_s, log=[], **opt)
    check("I1 SDNF mit den Optionen des Dialogs: Stäbe 8 m und 4 m (Kette)", sorted(_staebe(m)) == [4.0, 8.0],
          str(_staebe(m)))
    d = ImportDialog(None, os.path.join(tmp, "x.dxf"), Model())
    check("I1 DXF ohne Kopfeinheit wie bisher: Maßstab mm", d.options().get("unit_scale") == 1e-3,
          str(d.options().get("unit_scale")))
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# I5: IFC, Querschnittseinheiten
# --------------------------------------------------------------------------
def test_i5_ifc():
    print("\n--- I5: IFC in mm mit Flächeneinheit m² ---")
    from statik3d.exporters import export_model
    from statik3d.importers import import_file
    tmp = tempfile.mkdtemp()
    p_m = os.path.join(tmp, "m.ifc")
    export_model(modell(flaechenlast=False), p_m, log=[])
    p_mm = os.path.join(tmp, "mm.ifc")
    _ifc_in_mm(p_m, p_mm)
    with open(p_mm, encoding="utf-8") as f:
        txt = f.read()
    # Flaechen- und Traegheitsmomenteinheit ausdruecklich in m² bzw. m⁴
    txt = re.sub(r"(#\d+)=IFCUNITASSIGNMENT\(\(([^)]*)\)\);",
                 lambda mm: ("#901=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);\n"
                             "#902=IFCDERIVEDUNITELEMENT(#901,4);\n"
                             "#903=IFCDERIVEDUNIT((#902),.MOMENTOFINERTIAUNIT.,$);\n"
                             f"{mm.group(1)}=IFCUNITASSIGNMENT(({mm.group(2)},#903));"), txt)
    with open(p_mm, "w", encoding="utf-8") as f:
        f.write(txt)
    a = import_file(p_m, log=[])
    b = import_file(p_mm, log=[])
    for qs in ("HEA 200", "FREI"):
        sa, sb = a.sections.get(qs), b.sections.get(qs)
        close(f"I5 {qs}: A der mm-Datei = A der m-Datei", sb.A if sb else None, sa.A, 1e-9, " m²")
        close(f"I5 {qs}: I_y der mm-Datei = I_y der m-Datei", sb.Iy if sb else None, sa.Iy, 1e-9, " m⁴")
    close("I5 Handwert HEA 200: A = 53,8 cm²", b.sections["HEA 200"].A, 53.8e-4, 2e-3, " m²")
    close("I5 Handwert HEA 200: I_y = 3 692 cm⁴", b.sections["HEA 200"].Iy, 3692e-8, 2e-3, " m⁴")
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# I7: SDNF-Export mit „m“
# --------------------------------------------------------------------------
def test_i7_sdnf():
    print("\n--- I7: SDNF-Export mit Längeneinheit m ---")
    from statik3d.exporters.sdnf import write_sdnf
    from statik3d.importers import import_file
    tmp = tempfile.mkdtemp()
    try:
        write_sdnf(modell(), os.path.join(tmp, "m.sdnf"), unit="m")
        abgelehnt = False
    except ValueError as ex:
        abgelehnt = "mm" in str(ex) and "inch" in str(ex)
    check("I7 unit = „m“ wird mit Hinweis auf mm und inch abgelehnt", abgelehnt)
    for u in ("mm", "inch"):
        p = os.path.join(tmp, f"{u}.sdnf")
        write_sdnf(modell(), p, unit=u)
        r = import_file(p, log=[])
        # die Datei schreibt vier Nachkommastellen: in inch 314,9606 -> 7,999999 m
        check(f"I7 unit = „{u}“: Stäbe 8 m und 4 m zurück",
              np.allclose(sorted(_staebe(r)), [4.0, 8.0], rtol=1e-6), str(_staebe(r)))
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# I6: Nastran und Abaqus in mm-N-MPa
# --------------------------------------------------------------------------
BDF = """BEGIN BULK
GRID,1,,0.,0.,0.
GRID,2,,4000.,0.,0.
CBAR,1,1,1,2,0.,1.,0.
PBAR,1,1,5380.,1.336+7,3.692+7,2.098+5
MAT1,1,210000.,,0.3,7.85-9
,355.
SPC1,1,123456,1
CELAS2,9,2000.,2,3
FORCE,2,2,,1.,0.,0.,-10000.
MOMENT,3,2,,1000000.,0.,1.,0.
PLOAD1,4,1,FZ,FR,0.,-2.,1.,-2.
GRAV,5,,9810.,0.,0.,-1.
ENDDATA
"""

INP = """*NODE
1, 0., 0., 0.
2, 4000., 0., 0.
*ELEMENT, TYPE=B31, ELSET=E1
1, 1, 2
*BEAM GENERAL SECTION, ELSET=E1, SECTION=GENERAL, MATERIAL=S
5380., 3.692e7, 0., 1.336e7, 2.098e5
0., 0., -1.
*MATERIAL, NAME=S
*ELASTIC
210000., 0.3
*DENSITY
7.85e-9
*BOUNDARY
1, 1, 6
*STEP
*STATIC
*CLOAD
2, 3, -10000.
*END STEP
*STEP, NAME=MOM
*STATIC
*CLOAD
2, 5, 1000000.
*DLOAD
E1, PZ, -2.
*DLOAD
, GRAV, 9810., 0., 0., -1.
*END STEP
"""


def test_i6_mm_n_mpa():
    print("\n--- I6: Nastran und Abaqus in mm-N-MPa ---")
    from statik3d import solver
    from statik3d.importers import import_file
    tmp = tempfile.mkdtemp()
    E, I_y, I_22, L, F = 210e9, 3.692e-5, 1.336e-5, 4.0, 10000.0
    p = os.path.join(tmp, "m.bdf")
    open(p, "w").write(BDF)
    m = import_file(p, log=[], unit_scale=1e-3)
    mat = m.materials["MAT 1"]
    close("I6 Nastran: E = 210 000 N/mm² = 2,1e11 Pa", mat.E, 2.1e11, 1e-9, " Pa")
    close("I6 Nastran: rho = 7,85e-9 t/mm³ = 7 850 kg/m³", mat.rho, 7850.0, 1e-9, " kg/m³")
    close("I6 Nastran: f_y = 355 N/mm²", mat.fy, 355e6, 1e-9, " Pa")
    k = [s for s in m.supports if s.stiffness]
    close("I6 Nastran: Feder 2 000 N/mm = 2e6 N/m", float(k[0].stiffness[0]) if k else None, 2e6, 1e-9, " N/m")
    my = [float(l.F[4]) for l in m.load_cases["SID 3"].nodal_loads]
    close("I6 Nastran: Moment 1e6 Nmm = 1 000 Nm", my[0] if my else None, 1000.0, 1e-9, " Nm")
    q = [float(l.q[2]) for l in m.load_cases["SID 4"].beam_loads]
    close("I6 Nastran: Streckenlast -2 N/mm = -2 000 N/m", q[0] if q else None, -2000.0, 1e-9, " N/m")
    close("I6 Nastran: GRAV 9 810 mm/s² = 9,81 m/s²", float(m.load_cases["SID 5"].gravity[2]), -9.81, 1e-9, " m/s²")
    res = solver.solve_static(m, case="SID 2")
    u = np.asarray(res.u).reshape(-1, 6)
    k_balken = 3.0 * E * I_y / L ** 3
    hand = F / (2e6 + k_balken)
    close("I6 Nastran: w = F/(k + 3EI/L³) = 4,231 mm (Hand)", abs(float(u[int(np.argmax(m.nodes[:, 0])), 2])),
          hand, 1e-4, " m")
    p = os.path.join(tmp, "m.inp")
    open(p, "w").write(INP)
    m = import_file(p, log=[], unit_scale=1e-3)
    mat = m.materials["S"]
    close("I6 Abaqus: E = 2,1e11 Pa", mat.E, 2.1e11, 1e-9, " Pa")
    close("I6 Abaqus: rho = 7 850 kg/m³", mat.rho, 7850.0, 1e-9, " kg/m³")
    lc = m.load_cases["MOM"]
    my = [float(l.F[4]) for l in lc.nodal_loads]
    close("I6 Abaqus: Moment 1e6 Nmm = 1 000 Nm", my[0] if my else None, 1000.0, 1e-9, " Nm")
    q = [float(l.q[2]) for l in lc.beam_loads]
    close("I6 Abaqus: Streckenlast PZ -2 N/mm = -2 000 N/m", q[0] if q else None, -2000.0, 1e-9, " N/m")
    close("I6 Abaqus: GRAV 9 810 mm/s² = 9,81 m/s²", float(lc.gravity[2]), -9.81, 1e-9, " m/s²")
    erster = next(n for n, c in m.load_cases.items() if c.nodal_loads and n != "MOM")
    res = solver.solve_static(m, case=erster)
    u = np.asarray(res.u).reshape(-1, 6)
    # n1 = (0, 0, -1): die 1-Achse liegt in z, Biegung unter F_z um die 2-Achse mit I22
    close("I6 Abaqus: w = F L³/(3 E I22) = 76,04 mm (Hand)", abs(float(u[int(np.argmax(m.nodes[:, 0])), 2])),
          F * L ** 3 / (3 * E * I_22), 1e-4, " m")
    m1 = import_file(p, log=[])
    close("I6 Abaqus ohne Maßstab: SI wie bisher (E = 210 000 Pa unverändert)", m1.materials["S"].E, 210000.0,
          1e-12, " Pa")
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# I4: Einheiten in Kopfzeilen
# --------------------------------------------------------------------------
def test_i4_einheiten():
    print("\n--- I4: Einheiten in Kopfzeilen ---")
    from statik3d.importers import _common as C
    from statik3d.importers import import_file
    for u, soll in (("MN/m³", 1e6), ("MN/m3", 1e6), ("N/mm³", 1e9), ("N/cm³", 1e6), ("kN/m³", 1e3),
                    ("kNcm/rad", 10.0), ("kNm/rad/m", 1e3), ("kN/m/m", 1e3), ("Nmm/rad", 1e-3)):
        close(f"I4 unit_factor [{u}]", C.unit_factor(f"x [{u}]", 123.0), soll, 1e-12)
    knoten = "Knoten Nr.;Koordinate X [m];Koordinate Y [m];Koordinate Z [m]\n1;0;0;0\n2;4;0;0\n3;4;3;0\n4;0;3;0\n"
    linien = "Linie Nr.;Knoten Nr.\n1;1,2\n2;2,3\n3;3,4\n4;4,1\n"
    mat = "Material Nr.;Bezeichnung;E-Modul [N/mm²];Wichte [kN/m³]\n1;C30/37;33000;25\n"
    fl = "Fläche Nr.;Begrenzungslinien;Material;Dicke [mm]\n1;1,2,3,4;1;300\n"

    def ordner(einheit, wert):
        d = tempfile.mkdtemp(prefix="einh_rtab_")
        for name, text in (("1.1 Knoten.csv", knoten), ("1.2 Linien.csv", linien),
                           ("1.3 Materialien.csv", mat), ("1.4 Flaechen.csv", fl),
                           ("1.10 Flaechenlager.csv",
                            f"Flächenlager Nr.;An Flächen;uz [{einheit}];ux;uy\n1;1;{wert};frei;frei\n")):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(text)
        return d
    m = import_file(ordner("MN/m³", 50), log=[])
    b = m.surface_supports[0].dof_behaviour(2) if m.surface_supports else None
    close("I4 Bettung uz = 50 [MN/m³] = 5e7 N/m³", b.stiffness if b else None, 5e7, 1e-12, " N/m³")
    m2 = import_file(ordner("kN/m³", 50000), log=[])
    close("I4 Gegenprobe 50 000 [kN/m³] = 5e7 N/m³", m2.surface_supports[0].dof_behaviour(2).stiffness, 5e7,
          1e-12, " N/m³")
    log = []
    import_file(ordner("kN/qm³", 50000), log=log)
    w = [z for z in log if "nicht erkannt" in z and "kN/qm³" in z]
    check("I4 unbekannte Einheit [kN/qm³]: genau eine Warnung mit Spalte", len(w) == 1 and "uz" in w[0],
          str(w)[:200])
    zeilen = []
    try:
        C.unit_factor("Knoten Nr. (Anfang)", 1.0, zeilen)
        C.unit_factor("nu [-]", 1.0, zeilen)
        ohne = not zeilen
    except TypeError:                   # vor der Behebung ohne Protokoll
        ohne = False
    check("I4 keine Warnung zu runden Klammern oder [-]", ohne, str(zeilen)[:160])


# --------------------------------------------------------------------------
# I2: Tabellen im RFEM-Aufbau, Rundlauf
# --------------------------------------------------------------------------
def test_i2_tabellen():
    print("\n--- I2: Tabellen im RFEM-Aufbau, Export und Import ---")
    from statik3d import solver
    from statik3d.exporters import export_model
    from statik3d.importers import import_file
    tmp = tempfile.mkdtemp()
    m = modell(flaechenlast=False)
    log_ex = []
    ordner = export_model(m, os.path.join(tmp, "m.csv"), log=log_ex)
    r = import_file(ordner, log=[])
    check("I2 Knoten 8, Stabelemente 3, Schale 1",
          r.nn == 8 and sum(e.typ == "beam" for e in r.elements) == 3
          and sum(e.typ == "shell4" for e in r.elements) == 1,
          f"{r.nn} Knoten, {[e.typ for e in r.elements]}")
    close("I2 freier Querschnitt: I_y = 3 692 cm⁴", r.sections["FREI"].Iy if "FREI" in r.sections else None,
          3692e-8, 1e-9, " m⁴")
    mat = [r.elements[i].mat for i, e in enumerate(r.elements) if e.typ == "beam" and e.sec == "FREI"]
    check("I2 Stab mit FREI behält den Werkstoff ALU", mat == ["ALU"], str(mat))
    fed = [s for s in r.supports if any(s.dof_behaviour(d).typ == "spring" for d in range(6))]
    k = [fed[0].dof_behaviour(d).stiffness if fed and fed[0].dof_behaviour(d).typ == "spring" else 0.0
         for d in range(6)] if fed else []
    check("I2 Federlager ux 5e6 N/m, uz 2e7 N/m, phiy 3e5 Nm/rad",
          k == [5e6, 0.0, 2e7, 0.0, 3e5, 0.0], str(k))
    nl = sum(np.asarray(l.F, float) for l in r.load_cases["LF1"].nodal_loads)
    check("I2 Knotenlasten LF1: Fx 25 kN, Fz -40 kN, My 12 kNm",
          np.allclose(nl, [25e3, 0, -40e3, 0, 12e3, 0]), str(nl))
    check("I2 Lastfall LF3 behält die Kategorie Q_A", r.load_cases["LF3"].category == "Q_A",
          r.load_cases["LF3"].category)
    close("I2 Eigengewicht LF2: g = -9,81 m/s²", float(r.load_cases["LF2"].gravity[2]), -9.81, 1e-9, " m/s²")
    # zwei Wege: Handwert des Gewichts und Rechnung des Originals gegen die Rechnung der Kopie
    hand = 0.0
    for i, e in enumerate(m.elements):
        mt = m.materials[e.mat]
        if e.typ == "beam":
            hand += mt.rho * 9.81 * m.sections[e.sec].A * m.element_length(i)
        else:
            hand += mt.rho * 9.81 * m.shells[e.sec].t * 8.0          # Schale 4 x 2 m
    rz_o = _rz(solver.solve_static(m, case="LF2"))
    rz_k = _rz(solver.solve_static(r, case="LF2"))
    close("I2 LF2 Summe R_z der Kopie = Handwert rho g (A L + t A_Schale)", rz_k, hand, 1e-6, " N")
    close("I2 LF2 Summe R_z Original = Handwert", rz_o, hand, 1e-6, " N")
    uo = np.asarray(solver.solve_static(m, case="LF1").u).reshape(-1, 6)
    uk = np.asarray(solver.solve_static(r, case="LF1").u).reshape(-1, 6)
    close("I2 LF1 größte Verschiebung der Kopie = Original", float(np.abs(uk[:, :3]).max()),
          float(np.abs(uo[:, :3]).max()), 1e-6, " m")
    # was der Aufbau nicht traegt, steht im Hinweis
    m2 = modell()
    log_ex = []
    export_model(m2, os.path.join(tmp, "m2.csv"), log=log_ex)
    check("I2 Hinweis nennt die nicht übertragene Flächenlast",
          any("nicht übertragen" in z and "Flächenlast" in z for z in log_ex), str(log_ex[-1:])[:200])
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# B11 / B12: SAF
# --------------------------------------------------------------------------
def test_b11_saf_alt():
    print("\n--- B11: alte Statik3D-SAF-Datei (Export eb88ecc), Federn in N/m ---")
    from statik3d import solver
    from statik3d.exporters import export_model
    from statik3d.importers import import_file
    from statik3d.importers.xlsx_reader import read_xlsx, write_xlsx
    p = os.path.join(DATEN, "saf_alt_eb88ecc", "feder_alt.xlsx")
    log = []
    m = import_file(p, log=log)
    k = [float(x) for s in m.supports for x in (s.stiffness or [])]
    close("B11 Feder uz = 2e6 N/m wie im alten Modell (nicht 2e12)", k[0] if k else None, 2e6, 1e-12, " N/m")
    check("B11 Protokoll nennt die alte Statik3D-Datei", any("vor dem 12.11.2026" in z for z in log),
          str([z for z in log if "12.11" in z])[:200])
    # zwei Wege: Rechnung gegen Hand w = F / (k + 3EI/L³) des Kragarms mit Endfeder
    an = solver.solve_all(m, workers=1, combinations=False)
    kn = int(np.argmin(np.linalg.norm(m.nodes - np.array([4.0, 0, 0]), axis=1)))
    e = next(e for e in m.elements if e.typ == "beam")
    mt, qs = m.materials[e.mat], m.sections[e.sec]
    # Kragarm mit Biege- und Schubnachgiebigkeit (Timoshenko), Endfeder parallel
    f_balken = 4.0 ** 3 / (3 * mt.E * qs.Iy) + (4.0 / (mt.G * qs.Asz) if qs.Asz else 0.0)
    hand = 10e3 / (2e6 + 1.0 / f_balken)
    close("B11 w(LF1) = F/(k + 1/(L³/3EI + L/GA_s)) = 3,173 mm", abs(float(an.cases["LF1"].u[kn, 2])), hand,
          1e-6, " m")
    # fremde SAF-Datei: „Stiffness Z“ ohne Einheit bleibt MN/m (SAF)
    mm = Model("F")
    mm.add_material(Material.steel("S355"))
    mm.add_section(Section.rhs("R", 0.3, 0.2, 0.01))
    a, b = mm.add_node(0, 0, 0), mm.add_node(4, 0, 0)
    mm.add_element("beam", [a, b], "S355", "R")
    mm.fix(a, "all")
    mm.fix(b, [2], stiffness=[2e6])
    tmp = tempfile.mkdtemp()
    q = os.path.join(tmp, "f.xlsx")
    export_model(mm, q, log=[])
    bl = read_xlsx(q)
    lc = bl["StructuralLoadCase"]
    c = lc[0].index("Category")
    a_t = lc[0].index("Action type")
    bl["StructuralLoadCase"] = [z[:c] + z[c + 1:] for z in lc]
    for z in bl["StructuralLoadCase"][1:]:
        z[a_t] = "Permanent"
    ps = bl["StructuralPointSupport"]
    ps[0] = [re.sub(r"\s*\[[^\]]*\]", "", str(h)) if str(h).startswith("Stiffness") else h for h in ps[0]]
    q2 = os.path.join(tmp, "fremd.xlsx")
    write_xlsx(q2, bl)
    log = []
    f = import_file(q2, log=log)
    k = [float(x) for s in f.supports for x in (s.stiffness or [])]
    close("B11 fremde SAF-Datei: „Stiffness Z“ = 2 ohne Einheit bleibt 2 MN/m", k[0] if k else None, 2e6, 1e-12,
          " N/m")
    check("B11 fremde Datei: kein Hinweis auf Statik3D", not any("vor dem 12.11.2026" in z for z in log))
    shutil.rmtree(tmp, ignore_errors=True)


def test_b12_saf_kategorie():
    print("\n--- B12: SAF ohne Spalte „Category“ ---")
    from statik3d.exporters import export_model
    from statik3d.exporters.saf import SAF_GENAU
    from statik3d.importers import import_file
    from statik3d.importers.xlsx_reader import read_xlsx, write_xlsx
    m = Model("K")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.rhs("R", 0.3, 0.2, 0.01))
    a, b = m.add_node(0, 0, 0), m.add_node(4, 0, 0)
    e = m.add_element("beam", [a, b], "S355", "R")
    m.fix(a, "all")
    m.fix(b, "all")
    soll = {}
    for k, kat in enumerate(SAF_GENAU):
        lf = f"LF{k + 1}"
        if lf in m.load_cases:
            m.load_cases[lf].category = kat
        else:
            m.add_load_case(lf, kat)
        m.load_beam(e, qz=-1e3, case=lf)
        soll[lf] = kat
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "k.xlsx")
    export_model(m, p, log=[])
    bl = read_xlsx(p)
    lc = bl["StructuralLoadCase"]
    c = lc[0].index("Category")
    bl["StructuralLoadCase"] = [z[:c] + z[c + 1:] for z in lc]
    p2 = os.path.join(tmp, "k_ohne.xlsx")
    write_xlsx(p2, bl)
    m2 = import_file(p2, log=[])
    falsch = {lf: m2.load_cases[lf].category for lf, kat in soll.items() if m2.load_cases[lf].category != kat}
    check(f"B12 alle {len(soll)} Kategorien zurück (Q_A … Q_H, ERD)", not falsch, str(falsch))
    shutil.rmtree(tmp, ignore_errors=True)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1200, exit=True)
    for t in (test_i3_wichte, test_i1_dialog, test_i5_ifc, test_i7_sdnf, test_i6_mm_n_mpa,
              test_i4_einheiten, test_i2_tabellen, test_b11_saf_alt, test_b12_saf_kategorie):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
