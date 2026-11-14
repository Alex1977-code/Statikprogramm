"""Import und Export, zweite Befundrunde vom 14.11.2026 (BEFUNDE-2026-11-14-RUNDE2.md,
vom Anwender am 14.11.2026 freigegeben).

* A'4  IFC: der Vorsatz einer Flaechen- oder Volumeneinheit gilt fuer das Meter -
       MILLI SQUARE_METRE ist mm² = 10⁻⁶ m² (nicht 10⁻³), MILLI CUBIC_METRE 10⁻⁹ m³.
* A'5  SAF ohne Spalte „Category“: der „Load type“ einer Lastgruppe nennt die
       Nutzlastkategorie nur bei „Variable“; eine staendige Gruppe bleibt G.
* A'9  RFEM 6: ein Werkstoff nur mit Wichte gamma bestimmt die Erdbeschleunigung nicht
       mit und verfaelscht weder den Nachbarwerkstoff noch die Warnung; der Status
       vergleicht rho des Modells mal g mit gamma der Datei (eine angepasste Dichte
       hebt ihn auf) und bleibt nach „neu rechnen“ stehen (modellgrund).
* A'11 Nastran/Abaqus: die E-Modul-Warnung sagt „nach der Umrechnung“ nur, wenn
       umgerechnet wurde; ohne Umrechnung warnt sie unter 1 N/mm².
* B'7  Tabellen im RFEM-Aufbau: ein Seil kommt als Seil zurueck, Lastkombinationen
       werden geschrieben und gelesen; Ergebniskombinationen nennt der Hinweis.

Aufruf:  python -m tests.test_import_runde2
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
    tempfile.mkdtemp(prefix="statik3d_import_runde2_"), "einstellungen.json")

from statik3d.model import Model, Material, Section     # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:96s} {detail}")
    return ok


def close(name, ist, soll, tol_rel=1e-6, einheit=""):
    ok = ist is not None and abs(float(ist) - float(soll)) <= tol_rel * max(abs(float(soll)), 1e-30)
    return check(name, ok, f"ist {ist!r}{einheit}, soll {soll!r}{einheit}")


# --------------------------------------------------------------------------
# A'4: IFC, Vorsatz bei Flaechen- und Volumeneinheiten
# --------------------------------------------------------------------------
def test_a4_ifc_flaeche():
    print("\n--- A'4: IFC, MILLI SQUARE_METRE = mm² ---")
    from statik3d.exporters import export_model
    from statik3d.importers import import_file
    from statik3d.importers.ifc import Units, parse_ifc
    from tests.test_import_einheiten import modell
    tmp = tempfile.mkdtemp()
    p_m = os.path.join(tmp, "m.ifc")
    export_model(modell(flaechenlast=False), p_m, log=[])
    txt = open(p_m, encoding="utf-8").read()
    check("A'4 Vorbereitung: die Datei erklärt die Flächeneinheit m²",
          "IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)" in txt)
    # dieselbe Datei mit Flaechen in mm²: Einheit MILLI SQUARE_METRE, jede Flaeche x 10⁶
    mm2 = txt.replace("IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)", "IFCSIUNIT(*,.AREAUNIT.,.MILLI.,.SQUARE_METRE.)")
    mm2 = re.sub(r"IFCAREAMEASURE\(([^)]*)\)", lambda mm: f"IFCAREAMEASURE({float(mm.group(1)) * 1e6!r})", mm2)
    p_mm2 = os.path.join(tmp, "mm2.ifc")
    open(p_mm2, "w", encoding="utf-8").write(mm2)
    a = import_file(p_m, log=[])
    b = import_file(p_mm2, log=[])
    for qs in ("FREI", "HEA 200"):
        sa, sb = a.sections[qs], b.sections.get(qs)
        for k in ("A", "Asy", "Asz"):
            close(f"A'4 {qs}: {k} der mm²-Datei = {k} der m²-Datei", getattr(sb, k) if sb else None,
                  getattr(sa, k), 1e-9, " m²")
    close("A'4 Handwert FREI: A = 53,8 cm² (5 380 mm² · 10⁻⁶)", b.sections["FREI"].A, 53.8e-4, 1e-9, " m²")
    # Einheiten selbst: Vorsatz hoch 2 bzw. 3, auch in abgeleiteten Einheiten
    p_u = os.path.join(tmp, "einheiten.ifc")
    zus = ("#9001=IFCSIUNIT(*,.VOLUMEUNIT.,.MILLI.,.CUBIC_METRE.);\n"
           "#9002=IFCSIUNIT(*,.AREAUNIT.,.CENTI.,.SQUARE_METRE.);\n"
           "#9003=IFCSIUNIT(*,.AREAUNIT.,.MILLI.,.SQUARE_METRE.);\n"
           "#9004=IFCDERIVEDUNITELEMENT(#9003,2);\n"
           "#9005=IFCDERIVEDUNIT((#9004),.MOMENTOFINERTIAUNIT.,$);\n"
           "#9006=IFCSIUNIT(*,.LENGTHUNIT.,.KILO.,.METRE.);\n"
           "#9007=IFCSIUNIT(*,.MASSUNIT.,.KILO.,.GRAM.);\n")
    ut = re.sub(r"(#\d+)=IFCUNITASSIGNMENT\(\(([^)]*)\)\);",
                lambda mm: zus + f"{mm.group(1)}=IFCUNITASSIGNMENT((#9001,#9002,#9005,#9006,#9007));", txt)
    open(p_u, "w", encoding="utf-8").write(ut)
    u = Units(parse_ifc(p_u), [])
    close("A'4 VOLUMEUNIT MILLI CUBIC_METRE = 10⁻⁹ m³", u.scale.get("VOLUMEUNIT"), 1e-9, 1e-12)
    close("A'4 AREAUNIT CENTI SQUARE_METRE = 10⁻⁴ m²", u.scale.get("AREAUNIT"), 1e-4, 1e-12)
    close("A'4 MOMENTOFINERTIAUNIT (MILLI SQUARE_METRE)² = 10⁻¹² m⁴", u.scale.get("MOMENTOFINERTIAUNIT"),
          1e-12, 1e-12)
    close("A'4 LENGTHUNIT KILO METRE bleibt 1 000 m", u.scale.get("LENGTHUNIT"), 1e3, 1e-12)
    close("A'4 MASSUNIT KILO GRAM bleibt 1 kg", u.scale.get("MASSUNIT"), 1.0, 1e-12)
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# A'5: SAF, Load type der staendigen Lastgruppe
# --------------------------------------------------------------------------
def test_a5_saf_gruppe():
    print("\n--- A'5: SAF ohne „Category“, ständige Gruppe mit Load type ---")
    from statik3d.exporters import export_model
    from statik3d.importers import import_file
    from statik3d.importers.xlsx_reader import read_xlsx, write_xlsx
    m = Model("K")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.rhs("R", 0.3, 0.2, 0.01))
    a, b = m.add_node(0, 0, 0), m.add_node(4, 0, 0)
    e = m.add_element("beam", [a, b], "S355", "R")
    m.fix(a, "all")
    m.fix(b, "all")
    m.load_cases["LF1"].category = "G"
    m.load_beam(e, qz=-1e3, case="LF1")
    m.add_load_case("LF2", "Q_A")
    m.load_beam(e, qz=-2e3, case="LF2")
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "k.xlsx")
    export_model(m, p, log=[])
    bl = read_xlsx(p)
    lc = bl["StructuralLoadCase"]
    c = lc[0].index("Category")
    bl["StructuralLoadCase"] = [z[:c] + z[c + 1:] for z in lc]
    lg = bl["StructuralLoadGroup"]
    kopf = [str(h).lower().replace(" ", "") for h in lg[0]]
    i_lt, i_gt = kopf.index("loadtype"), kopf.index("loadgrouptype")
    for lt in ("Others", "Domestic"):
        for z in lg[1:]:
            if str(z[i_gt]) == "Permanent":
                z.extend([""] * (i_lt + 1 - len(z)))
                z[i_lt] = lt
        p2 = os.path.join(tmp, f"k_{lt}.xlsx")
        write_xlsx(p2, bl)
        m2 = import_file(p2, log=[])
        kat = {k: v.category for k, v in m2.load_cases.items()}
        check(f"A'5 Gruppe „Permanent“ mit Load type „{lt}“: LF1 bleibt G, LF2 (Variable, Domestic) Q_A",
              kat.get("LF1") == "G" and kat.get("LF2") == "Q_A", str(kat))
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# A'9: RFEM 6, Eigengewicht aus der Wichte
# --------------------------------------------------------------------------
class _DbStub:
    """Was _eigengewicht_aus_wichte von der Datenbank braucht."""

    def __init__(self, wichten, g=None):
        self.wichten = wichten
        self.g_last = 9.81
        self.g_text = ""
        self._g = g

    def rows(self, tabelle):
        return [{"gravitationalAcceleration": self._g}] if (tabelle == "ModelData" and self._g) else []


def _wichte_stub(wichten, g, rho_anfang):
    from statik3d.importers.rfem6_db import _eigengewicht_aus_wichte
    m = Model("W")
    for n, rho in rho_anfang.items():
        m.add_material(Material(n, 210e9, 0.3, rho, 1.2e-5))
    db = _DbStub(wichten, g)
    log = []
    g_last = _eigengewicht_aus_wichte(db, m, log)
    return m, g_last, [z for z in log if "passen Wichte und Dichte nicht" in z]


def _rf6(pfad, gamma, rho=None, chars_rho=None, g=10.0):
    """Kragarm 4 m (Rund 40) mit Eigengewicht; Werkstoff mit gamma, rho (None: ohne
    Dichte in der Datei) und der Dichte der Querschnittskennwerte ``chars_rho``."""
    from tests.test_rfem6 import INF, make_rf6
    make_rf6(pfad, nodes=[(0, 0, 0), (4, 0, 0)], lines=[[1, 2]], members=[(1, None, None)],
             supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1])],
             load_cases=[("Eigengewicht", 1, 1.0), ("Nutzlast", 2, 0.0)])
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(pfad) as z:
        namen = z.namelist()
        z.extractall(tmp)
    con = sqlite3.connect(os.path.join(tmp, "model.db"))
    if rho is None:
        nr = con.execute("SELECT container_order FROM MaterialProperties_propertiesMap_keys "
                         "WHERE value = 'rho'").fetchone()[0]
        con.execute("DELETE FROM MaterialProperties_propertiesMap_keys WHERE container_order = ?", (nr,))
        con.execute("DELETE FROM MaterialProperties_propertiesMap_values WHERE container_order = ?", (nr,))
    else:
        con.execute("UPDATE MaterialPropertyDouble SET valueSI = ? WHERE propertyKey = 'rho'", (rho,))
    con.execute("UPDATE SectionMaterialCharacteristics SET density = ?", (chars_rho,))
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


def _gz(m):
    lc = next(lc for lc in m.load_cases.values() if np.any(lc.gravity))
    return abs(float(np.asarray(lc.gravity, float)[2]))


def test_a9_wichte():
    print("\n--- A'9: RFEM 6, Werkstoff nur mit Wichte γ ---")
    from statik3d import solver
    from statik3d import rechenverfahren as RV
    from statik3d.importers import import_file
    from statik3d.importers.rfem6_db import eigengewicht_abweichung
    # (a) Datei ohne Erdbeschleunigung: S355 mit γ und ρ, S235 nur mit γ = 25 kN/m³
    m, g, warn = _wichte_stub({"S355": (7850.0, 78500.0, 7850.0), "S235": (25000.0 / 9.81, 25000.0, None)},
                              None, {"S355": 7850.0, "S235": 25000.0 / 9.81})
    close("A'9 ohne g in der Datei: g = γ/ρ von S355 = 10 m/s² (Hand 78 500 / 7 850)", g, 10.0, 1e-12, " m/s²")
    close("A'9 Nachbar S355: ρ·g = γ = 78 500 N/m³ (nicht 77 008)", m.materials["S355"].rho * g, 78500.0, 1e-12,
          " N/m³")
    close("A'9 S235 nur mit γ: ρ = γ/g = 2 500 kg/m³", m.materials["S235"].rho, 2500.0, 1e-12, " kg/m³")
    check("A'9 keine Warnung „passen nicht“ (beide Werkstoffe stimmen)", not warn, str(warn)[:200])
    # (b) g = 10 in der Datei, S235 nur mit γ, die Querschnittskennwerte nennen 7 850
    m, g, warn = _wichte_stub({"S355": (7850.0, 78500.0, 7850.0), "S235": (7850.0, 25000.0, None)},
                              10.0, {"S355": 7850.0, "S235": 7850.0})
    close("A'9 mit g = 10: S235 ρ = 2 500 kg/m³", m.materials["S235"].rho, 2500.0, 1e-12, " kg/m³")
    check("A'9 keine Warnung mit der überholten Dichte 7 850 (ρ·g = 78,5 statt 25 kN/m³)", not warn,
          str(warn)[:200])
    # (c) ein Werkstoff, dessen γ wirklich nicht zu ρ passt, wird weiter gemeldet - mit der Dichte,
    # die gilt
    m, g, warn = _wichte_stub({"S355": (7850.0, 78500.0, 7850.0), "X": (7850.0, 77000.0, 7850.0)},
                              10.0, {"S355": 7850.0, "X": 7850.0})
    check("A'9 echte Abweichung (X: γ 77, ρ·g 78,5 kN/m³) wird gemeldet",
          len(warn) == 1 and "X (γ = 77 kN/m³, ρ·g = 78,5 kN/m³)" in warn[0] and "S355" not in warn[0],
          str(warn)[:200])
    tmp = tempfile.mkdtemp()
    # (d) Datei: Werkstoff nur mit γ = 25 kN/m³, Kennwerte mit 7 850, g = 10
    log = []
    md = import_file(_rf6(os.path.join(tmp, "nur_gamma.rf6"), 25000.0, rho=None, chars_rho=7850.0), log=log)
    mat = next(iter(md.materials.values()))
    close("A'9 Datei nur γ: Erdbeschleunigung des Lastfalls = g der Datei 10 m/s² (nicht 3,18)", _gz(md),
          10.0, 1e-12, " m/s²")
    close("A'9 Datei nur γ: ρ = γ/g = 2 500 kg/m³", mat.rho, 2500.0, 1e-12, " kg/m³")
    rz = float(np.asarray(solver.solve_static(md, case=next(
        n for n, lc in md.load_cases.items() if np.any(lc.gravity))).reactions).reshape(-1, 6)[:, 2].sum())
    close("A'9 Datei nur γ: Σ R_z = γ A L = 25 000 · π · 0,02² · 4 (Hand 125,7 N)", abs(rz),
          25000.0 * np.pi * 0.02 ** 2 * 4.0, 1e-6, " N")
    # (e) Status: frueher uebernommenes Modell, vom Anwender angepasste Dichte
    p = _rf6(os.path.join(tmp, "s355.rf6"), 78500.0, rho=7850.0, chars_rho=7850.0)
    alt = import_file(p, log=[])
    alt.meta.pop("rfem_eigengewicht", None)
    for lc in alt.load_cases.values():
        if np.any(lc.gravity):
            lc.gravity = [0.0, 0.0, -9.81]
    abw = eigengewicht_abweichung(alt)
    close("A'9 altes Modell (ρ 7 850, g 9,81): 1,9 % zu klein (Hand 1 − 7 850 · 9,81 / 78 500)",
          abw[0] if abw else None, 1.0 - 7850.0 * 9.81 / 78500.0, 1e-9)
    mk = RV.merkmal("import_eigengewicht")
    check("A'9 Merkmal import_eigengewicht hat einen modellgrund", mk is not None and bool(mk.modellgrund),
          repr(getattr(mk, "modellgrund", None)))
    neu = RV.modell_betroffen(alt)
    check("A'9 Status einer neuen Rechnung (nach „neu rechnen“) nennt das Eigengewicht aus RFEM",
          "Eigengewicht aus RFEM" in neu and "neu importieren" in neu, neu[:300])
    alt._rfem_eigengewicht_abw = None
    next(iter(alt.materials.values())).rho = 7900.0
    abw = eigengewicht_abweichung(alt)
    close("A'9 Dichte teilweise angepasst (7 900): 1,28 % zu klein (Hand 1 − 7 900 · 9,81 / 78 500)",
          abw[0] if abw else None, 1.0 - 7900.0 * 9.81 / 78500.0, 1e-9)
    next(iter(alt.materials.values())).rho = 78500.0 / 9.81
    abw = eigengewicht_abweichung(alt)
    check("A'9 Dichte vom Anwender auf γ/9,81 = 8 002 kg/m³ gesetzt: nicht mehr betroffen",
          abw is None and not mk.betrifft(alt), str(abw))
    check("A'9 dann auch kein Status einer neuen Rechnung", RV.modell_betroffen(alt) == "",
          RV.modell_betroffen(alt)[:200])
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# A'11: E-Modul-Warnung ohne Umrechnung
# --------------------------------------------------------------------------
_EL_BDF = ("BEGIN BULK\nGRID,1,,0.,0.,0.\nGRID,2,,0.4,0.,0.\nGRID,3,,0.4,0.3,0.\nGRID,4,,0.,0.3,0.\n"
           "MAT1,1,{E},,0.49,1200.\nPSHELL,2,1,0.02\nCQUAD4,5,2,1,2,3,4\nSPC1,1,123456,1,4\nENDDATA\n")


def test_a11_e_pruefen():
    print("\n--- A'11: E-Modul-Warnung, Nastran und Abaqus ---")
    from statik3d.importers import import_file
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "el.bdf")
    open(p, "w").write(_EL_BDF.format(E="5.+6"))
    log = []
    m = import_file(p, log=log)
    w = [z for z in log if "E-Modul" in z and z.startswith("WARNUNG")]
    close("A'11 Elastomer in SI: E = 5 N/mm² gelesen", m.materials["MAT 1"].E, 5e6, 1e-12, " Pa")
    check("A'11 Elastomer 5 N/mm² in SI (ohne Umrechnung): keine E-Modul-Warnung", not w, str(w)[:200])
    open(p, "w").write(_EL_BDF.format(E="210000."))
    log = []
    import_file(p, log=log)
    w = [z for z in log if "E-Modul" in z and z.startswith("WARNUNG")]
    check("A'11 E = 210 000 als SI gelesen (0,21 N/mm²): Warnung ohne „nach der Umrechnung“, nennt mm",
          len(w) == 1 and "nach der Umrechnung" not in w[0] and "mm" in w[0] and "0,21 N/mm²" in w[0],
          str(w)[:240])
    open(p, "w").write(_EL_BDF.format(E="5."))
    log = []
    import_file(p, log=log, unit_scale=1e-3)
    w = [z for z in log if "E-Modul" in z and z.startswith("WARNUNG")]
    check("A'11 mit Umrechnung (mm): Warnung wie bisher „nach der Umrechnung“",
          len(w) == 1 and "nach der Umrechnung" in w[0], str(w)[:200])
    inp = ("*NODE\n1, 0., 0., 0.\n2, 4., 0., 0.\n*ELEMENT, TYPE=B31, ELSET=E1\n1, 1, 2\n"
           "*BEAM SECTION, ELSET=E1, MATERIAL=GUMMI, SECTION=RECT\n0.1, 0.1\n0., 0., -1.\n"
           "*MATERIAL, NAME=GUMMI\n*ELASTIC\n5.E6, 0.49\n")
    q = os.path.join(tmp, "el.inp")
    open(q, "w").write(inp)
    log = []
    import_file(q, log=log)
    w = [z for z in log if "E-Modul" in z and z.startswith("WARNUNG")]
    check("A'11 Abaqus, Elastomer 5 N/mm² in SI: keine E-Modul-Warnung", not w, str(w)[:200])
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# B'7: Tabellen-Rundlauf, Seil und Kombinationen
# --------------------------------------------------------------------------
def test_b7_tabellen():
    print("\n--- B'7: Tabellen im RFEM-Aufbau, Seil und Kombinationen ---")
    from statik3d import solver
    from statik3d.exporters.tables import write_tables
    from statik3d.importers import import_file
    m = Model("S")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEA 200"))
    m.add_section(Section.circle("RD20", 0.02))
    n = [m.add_node(*p) for p in ((0, 0, 0), (4, 0, 0), (4, 0, 3))]
    m.add_element("beam", [n[0], n[1]], "S355", "HEA 200")
    m.add_element("seil", [n[2], n[1]], "S355", "RD20")
    m.fix(n[0], "all")
    m.fix(n[2], "pinned")
    m.load_node(n[1], Fz=10e3, case="LF1")
    m.add_load_case("LF2", "Q", "Nutzlast")
    m.load_node(n[1], Fz=-4e3, case="LF2")
    m.add_combination("LK1", {"LF1": 1.35, "LF2": 1.5}, "ULS", "GZT ständig")
    m.add_combination("LK2", {"LF1": 1.0, "LF2": -1.0}, "SLS_CH", "")
    m.add_combination("Wohnen", {"LF2": 1.0}, "SLS_QP", "quasi")
    m.add_combination("EK1", {}, "ULS", "Hülle", alternativen=[{"LF1": 1.35}, {"LF2": 1.5}])
    tmp = tempfile.mkdtemp()
    log = []
    o = write_tables(m, os.path.join(tmp, "t"), log=log)
    log2 = []
    r = import_file(o, log=log2)
    typen = [e.typ for e in r.elements]
    check("B'7 Seil kommt als Seil zurück", typen == ["beam", "seil"], str(typen))
    # zwei Wege: Original gegen Rundlauf, und Hand (Seil faellt bei Druck aus: alles in die Einspannung)
    an_o = solver.solve_all(m, workers=1, combinations=False)
    an_r = solver.solve_all(r, workers=1, combinations=False)
    k = int(np.argmin(np.linalg.norm(r.nodes - np.array([4.0, 0, 3.0]), axis=1)))
    R_o = np.asarray(an_o.cases["LF1"].reactions, float).reshape(-1, 6)
    R_r = np.asarray(an_r.cases["LF1"].reactions, float).reshape(-1, 6)
    check("B'7 LF1 (Seil unter Druck): R_z oberer Seilknoten des Rundlaufs = Original = 0",
          abs(R_r[k, 2] - R_o[2, 2]) < 1e-2 and abs(R_r[k, 2]) < 1e-2, f"Rundlauf {R_r[k, 2]:.3f} N, "
          f"Original {R_o[2, 2]:.3f} N")
    close("B'7 LF1: R_z Einspannung = −10 kN (Hand: Seil fällt aus)", R_r[0, 2], -10e3, 1e-6, " N")
    check("B'7 Import nennt das Seil (nur Zug)", any("Seil" in z and "Zug" in z for z in log2),
          str([z for z in log2 if "Seil" in z])[:200])
    kom = {k_: (dict(c.factors), c.typ) for k_, c in r.combinations.items()}
    check("B'7 LK1 = 1,35·LF1 + 1,5·LF2, GZT", kom.get("LK1") == ({"LF1": 1.35, "LF2": 1.5}, "ULS"),
          str(kom.get("LK1")))
    check("B'7 LK2 = LF1 − LF2, GZG charakteristisch", kom.get("LK2") == ({"LF1": 1.0, "LF2": -1.0}, "SLS_CH"),
          str(kom.get("LK2")))
    check("B'7 „Wohnen“ kommt unter der freien Nummer LK3 zurück, LF2, GZG quasi-ständig",
          kom.get("LK3") == ({"LF2": 1.0}, "SLS_QP") and r.combinations["LK3"].description == "quasi",
          str(kom))
    check("B'7 Bezeichnung von LK1 bleibt", r.combinations.get("LK1") is not None
          and r.combinations["LK1"].description == "GZT ständig",
          repr(getattr(r.combinations.get("LK1"), "description", None)))
    check("B'7 Hinweis nennt die nicht übertragene Ergebniskombination",
          any("nicht übertragen" in z and "Ergebniskombination" in z for z in log), str(log[-1:])[:240])
    check("B'7 keine Ergebniskombination im Rundlauf", len(r.combinations) == 3, str(list(r.combinations)))
    an_o = solver.solve_all(m, workers=1, combinations=True)
    an_r = solver.solve_all(r, workers=1, combinations=True)
    R_o = np.asarray(an_o.combinations["LK1"].reactions, float).reshape(-1, 6).sum(axis=0)
    R_r = np.asarray(an_r.combinations["LK1"].reactions, float).reshape(-1, 6).sum(axis=0)
    close("B'7 LK1 Σ R_z Rundlauf = Original", R_r[2], R_o[2], 1e-6, " N")
    close("B'7 LK1 Σ R_z = −(1,35 · 10 − 1,5 · 4) kN (Hand)", R_r[2], -(1.35 * 10e3 - 1.5 * 4e3), 1e-6, " N")
    shutil.rmtree(tmp, ignore_errors=True)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1200, exit=True)
    for t in (test_a4_ifc_flaeche, test_a5_saf_gruppe, test_a9_wichte, test_a11_e_pruefen, test_b7_tabellen):
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
