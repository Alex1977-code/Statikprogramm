"""
RFEM-6-Projektdateien (.rf6): die eingebettete Modelldatenbank model.db mit
ihrem objektrelationalen Schema.

Geprueft wird gegen eine nachgebaute Datenbank, deren Tabellen, Spalten und
Verweise dem Aufbau einer echten RFEM-6-Datei entsprechen (an einer
Projektdatei RFEM 6.11 ausgelesen): Griff-Tabellen mit impl_table/impl_id,
Listentabellen mit value_id bzw. reference_id, SpringConstants mit inf/0 fuer
starr/frei, Nichtlinearitaet und Reibbeiwerten.

Das eingelesene Modell wird gerechnet und gegen Handrechnungen geprueft.

Aufruf:  python -m tests.test_rfem6
"""
import math
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver  # noqa: E402
from statik3d.importers import import_file  # noqa: E402
from statik3d.importers import rfem6_db as R6  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:58s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    err = abs(got - want)
    rel = err / abs(want) if want else err
    return check(name, err <= tol * max(1.0, abs(want)),
                 f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {rel * 100:.3f} %")


# --------------------------------------------------------------------------
# Nachbau einer RFEM-6-Modelldatenbank
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE Node (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE NodeImplStandard (id INTEGER PRIMARY KEY, version INTEGER, parent_id bigint,
                   coordinates_x double precision, coordinates_y double precision,
                   coordinates_z double precision);
CREATE TABLE Line (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE LineImplPolyline (id INTEGER PRIMARY KEY, version INTEGER, parent_id bigint);
CREATE TABLE LineImplPolyline_definitionNodes (id INTEGER, container_order INTEGER,
                   reference_id bigint, reference_table TEXT);
CREATE TABLE Member (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE MemberImplTension (id INTEGER PRIMARY KEY, version INTEGER, parent_id bigint,
                   line_id bigint, sectionStart_id bigint, sectionEnd_id bigint,
                   memberHingeStart_id bigint, memberHingeEnd_id bigint,
                   angle double precision, isDeactivatedForCalculation boolean);
CREATE TABLE Material (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE MaterialImpl (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                   parent_id bigint, databaseMaterialId bigint, materialType INTEGER);
CREATE TABLE MaterialData (id INTEGER PRIMARY KEY, version INTEGER, impl_id bigint,
                   properties_id bigint);
CREATE TABLE MaterialProperties (id INTEGER PRIMARY KEY, version INTEGER);
CREATE TABLE MaterialProperties_propertiesMap_keys (id INTEGER, container_order INTEGER, value TEXT);
CREATE TABLE MaterialProperties_propertiesMap_values (id INTEGER, container_order INTEGER,
                   reference_id bigint, reference_table TEXT);
CREATE TABLE MaterialPropertyDouble (id INTEGER PRIMARY KEY, version INTEGER,
                   propertyKey TEXT, valueSI REAL);
CREATE TABLE Section (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE SectionImplParametricBars (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                   parent_id bigint, material_id bigint,
                   librarySection_id bigint, librarySection_table TEXT);
CREATE TABLE ParametricSection (id INTEGER PRIMARY KEY, version INTEGER, sectionData_id bigint,
                   parametrizationShape INTEGER, seriesId INTEGER);
CREATE TABLE ParametricSection_parameterValues (id INTEGER, container_order INTEGER, value REAL);
CREATE TABLE ParametricSection_sectionMaterialCharacteristics (id INTEGER,
                   container_order INTEGER, value_id bigint);
CREATE TABLE SectionMaterialCharacteristics (id INTEGER PRIMARY KEY, version INTEGER,
                   modulusOfElasticity REAL, shearModulus REAL, density REAL,
                   poissonsRatio REAL, compressiveStrength REAL, tensileStrength REAL);
CREATE TABLE SectionData (id INTEGER PRIMARY KEY, version INTEGER, topology_id bigint);
CREATE TABLE SectionData_dimensions (id INTEGER, container_order INTEGER, symbol TEXT, value REAL);
CREATE TABLE SectionData_parameterValues_keys (id INTEGER, container_order INTEGER, value TEXT);
CREATE TABLE SectionData_parameterValues_values (id INTEGER, container_order INTEGER,
                   valueSI REAL, nonnumericValue TEXT);
CREATE TABLE NodalSupport (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE NodalSupportImpl (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                   parent_id bigint, springConstants_id bigint, type INTEGER);
CREATE TABLE NodalSupportImpl_nodes (id INTEGER, container_order INTEGER, value_id bigint);
CREATE TABLE LineSupport (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE LineSupportImpl (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                   parent_id bigint, springConstants_id bigint);
CREATE TABLE LineSupportImpl_lines (id INTEGER, container_order INTEGER, value_id bigint);
CREATE TABLE Surface (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE SurfaceImplQuadrangle (id INTEGER PRIMARY KEY, version INTEGER, parent_id bigint);
CREATE TABLE SurfaceImplQuadrangle_cornerNodes (id INTEGER, container_order INTEGER,
                   reference_id bigint, reference_table TEXT);
CREATE TABLE SurfaceSupport (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE SurfaceSupportImpl (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                   parent_id bigint, springConstant_0 REAL, springConstant_1 REAL,
                   springConstant_2 REAL, springConstant_3 REAL, springConstant_4 REAL,
                   nonlinearity INTEGER, negativeFrictionCoefficient REAL,
                   positiveFrictionCoefficient REAL, negativeContactStress REAL,
                   positiveContactStress REAL);
CREATE TABLE SurfaceSupportImpl_surfaces (id INTEGER, container_order INTEGER, value_id bigint);
CREATE TABLE MemberHinge (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE MemberHingeImpl (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                   parent_id bigint, springConstants_id bigint);
CREATE TABLE LoadCase (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE LoadCaseImplStatic (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                   parent_id bigint, actionCategoryId INTEGER, selfWeightActive boolean,
                   selfWeightFactors_x REAL, selfWeightFactors_y REAL, selfWeightFactors_z REAL);
CREATE TABLE Solid (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE SpringConstants (id INTEGER PRIMARY KEY, version INTEGER,
                   owner_id bigint, owner_table TEXT,
                   springConstantAlongX REAL, springConstantAlongY REAL,
                   springConstantAlongZ REAL, springConstantAroundX REAL,
                   springConstantAroundY REAL, springConstantAroundZ REAL,
                   nonlinearityTypeAlongX INTEGER, nonlinearityTypeAlongY INTEGER,
                   nonlinearityTypeAlongZ INTEGER, nonlinearityTypeAroundX INTEGER,
                   nonlinearityTypeAroundY INTEGER, nonlinearityTypeAroundZ INTEGER,
                   nonlinearityFrictionCoefficient_X_XY REAL, nonlinearityFrictionCoefficient_XZ REAL,
                   nonlinearityFrictionCoefficient_Y_YX REAL, nonlinearityFrictionCoefficient_YZ REAL,
                   nonlinearityFrictionCoefficient_Z_ZX REAL, nonlinearityFrictionCoefficient_ZY REAL);
CREATE TABLE SpringConstants_partialActivities (id INTEGER, container_order INTEGER,
                   typeNegative INTEGER, displacementNegative REAL, forceNegative REAL,
                   slippageNegative REAL, typePositive INTEGER, displacementPositive REAL,
                   forcePositive REAL, slippagePositive REAL);
"""

INF = float("inf")


def _spring(con, sid, owner, table, k, nl=(0,) * 6, friction=None):
    con.execute(
        "INSERT INTO SpringConstants (id,version,owner_id,owner_table,"
        "springConstantAlongX,springConstantAlongY,springConstantAlongZ,"
        "springConstantAroundX,springConstantAroundY,springConstantAroundZ,"
        "nonlinearityTypeAlongX,nonlinearityTypeAlongY,nonlinearityTypeAlongZ,"
        "nonlinearityTypeAroundX,nonlinearityTypeAroundY,nonlinearityTypeAroundZ,"
        "nonlinearityFrictionCoefficient_X_XY,nonlinearityFrictionCoefficient_XZ,"
        "nonlinearityFrictionCoefficient_Y_YX,nonlinearityFrictionCoefficient_YZ,"
        "nonlinearityFrictionCoefficient_Z_ZX,nonlinearityFrictionCoefficient_ZY) "
        "VALUES (" + ",".join("?" * 22) + ")",
        (sid, 1, owner, table) + tuple(k) + tuple(nl) + tuple(friction or (0.0,) * 6))


def build_db(path, nodes, lines, members, supports, line_supports=(),
             surface_supports=(), surfaces=(), hinges=(), partials=()):
    """Modelldatenbank im RFEM-6-Schema erzeugen."""
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    for i, (x, y, z) in enumerate(nodes, 1):
        con.execute("INSERT INTO Node VALUES (?,1,?,?,'NodeImplStandard')", (i, i, i))
        con.execute("INSERT INTO NodeImplStandard VALUES (?,1,?,?,?,?)", (i, i, x, y, z))
    for i, ns in enumerate(lines, 1):
        con.execute("INSERT INTO Line VALUES (?,1,?,?,'LineImplPolyline')", (i, i, i))
        con.execute("INSERT INTO LineImplPolyline VALUES (?,1,?)", (i, i))
        for j, n in enumerate(ns):
            con.execute("INSERT INTO LineImplPolyline_definitionNodes VALUES (?,?,?,'Node')",
                        (i, j, n))
    # Material: S355
    con.execute("INSERT INTO Material VALUES (1,1,1,1,'MaterialImpl')")
    con.execute("INSERT INTO MaterialImpl VALUES (1,1,'',1,22175,10)")
    con.execute("INSERT INTO MaterialData VALUES (1,1,1,1)")
    con.execute("INSERT INTO MaterialProperties VALUES (1,1)")
    for j, (k, v) in enumerate([("E", 210e9), ("G", 80.769e9), ("nu", 0.3),
                                ("rho", 7850.0), ("f_y", 355e6), ("f_u", 490e6),
                                ("alpha", 1.2e-5)]):
        con.execute("INSERT INTO MaterialPropertyDouble VALUES (?,1,?,?)", (j + 1, k, v))
        con.execute("INSERT INTO MaterialProperties_propertiesMap_keys VALUES (1,?,?)", (j, k))
        con.execute("INSERT INTO MaterialProperties_propertiesMap_values "
                    "VALUES (1,?,?,'MaterialPropertyDouble')", (j, j + 1))
    # Querschnitt: Rundstahl d = 40 mm
    d = 0.040
    con.execute("INSERT INTO Section VALUES (1,1,1,1,'SectionImplParametricBars')")
    con.execute("INSERT INTO SectionImplParametricBars VALUES (1,1,'',1,1,1,'ParametricSection')")
    con.execute("INSERT INTO ParametricSection VALUES (1,1,1,36,1992)")
    con.execute("INSERT INTO ParametricSection_parameterValues VALUES (1,0,?)", (d,))
    con.execute("INSERT INTO ParametricSection_sectionMaterialCharacteristics VALUES (1,0,1)")
    con.execute("INSERT INTO SectionMaterialCharacteristics VALUES (1,1,210e9,80.769e9,7850,0.3,355e6,490e6)")
    con.execute("INSERT INTO SectionData VALUES (1,1,1)")
    con.execute("INSERT INTO SectionData_dimensions VALUES (1,0,'d',?)", (d,))
    A = math.pi * d ** 2 / 4.0
    I = math.pi * d ** 4 / 64.0
    for j, (k, v) in enumerate([("A", A), ("A_y", 0.9 * A), ("A_z", 0.9 * A),
                                ("I_y", I), ("I_z", I), ("I_t", 2 * I)]):
        con.execute("INSERT INTO SectionData_parameterValues_keys VALUES (1,?,?)", (j, k))
        con.execute("INSERT INTO SectionData_parameterValues_values VALUES (1,?,?,NULL)", (j, v))
    for i, (line, hs, he) in enumerate(members, 1):
        con.execute("INSERT INTO Member VALUES (?,1,?,?,'MemberImplTension')", (i, i, i))
        con.execute("INSERT INTO MemberImplTension VALUES (?,1,?,?,1,1,?,?,0,0)",
                    (i, i, line, hs, he))
    sid = 1
    for i, (name, k, nl, fr, nodes_) in enumerate(supports, 1):
        con.execute("INSERT INTO NodalSupport VALUES (?,1,?,?,'NodalSupportImpl')", (i, i, i))
        con.execute("INSERT INTO NodalSupportImpl VALUES (?,1,?,?,?,0)", (i, name, i, sid))
        _spring(con, sid, i, "NodalSupportImpl", k, nl, fr)
        for j, n in enumerate(nodes_):
            con.execute("INSERT INTO NodalSupportImpl_nodes VALUES (?,?,?)", (i, j, n))
        for order, row in (partials or {}).get(("nodal", i), []):
            con.execute("INSERT INTO SpringConstants_partialActivities VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (sid, order) + tuple(row))
        sid += 1
    for i, (name, k, nl, fr, lns) in enumerate(line_supports, 1):
        con.execute("INSERT INTO LineSupport VALUES (?,1,?,?,'LineSupportImpl')", (i, i, i))
        con.execute("INSERT INTO LineSupportImpl VALUES (?,1,?,?,?)", (i, name, i, sid))
        _spring(con, sid, i, "LineSupportImpl", k, nl, fr)
        for j, n in enumerate(lns):
            con.execute("INSERT INTO LineSupportImpl_lines VALUES (?,?,?)", (i, j, n))
        sid += 1
    for i, corners in enumerate(surfaces, 1):
        con.execute("INSERT INTO Surface VALUES (?,1,?,?,'SurfaceImplQuadrangle')", (i, i, i))
        con.execute("INSERT INTO SurfaceImplQuadrangle VALUES (?,1,?)", (i, i))
        for j, n in enumerate(corners):
            con.execute("INSERT INTO SurfaceImplQuadrangle_cornerNodes VALUES (?,?,?,'Node')",
                        (i, j, n))
    for i, (name, springs, nl, mu, srf) in enumerate(surface_supports, 1):
        con.execute("INSERT INTO SurfaceSupport VALUES (?,1,?,?,'SurfaceSupportImpl')", (i, i, i))
        con.execute("INSERT INTO SurfaceSupportImpl VALUES (?,1,?,?,?,?,?,?,?,?,?,?,0,0)",
                    (i, name, i) + tuple(springs) + (nl, mu, mu))
        for j, n in enumerate(srf):
            con.execute("INSERT INTO SurfaceSupportImpl_surfaces VALUES (?,?,?)", (i, j, n))
    for i, (name, k) in enumerate(hinges, 1):
        con.execute("INSERT INTO MemberHinge VALUES (?,1,?,?,'MemberHingeImpl')", (i, i, i))
        con.execute("INSERT INTO MemberHingeImpl VALUES (?,1,?,?,?)", (i, name, i, sid))
        _spring(con, sid, i, "MemberHingeImpl", k)
        sid += 1
    con.execute("INSERT INTO LoadCase VALUES (1,1,1,1,'LoadCaseImplStatic')")
    con.execute("INSERT INTO LoadCaseImplStatic VALUES (1,1,'Eigengewicht',1,1,1,0,0,1.0)")
    con.commit()
    con.close()


def make_rf6(path, **kw):
    """.rf6-Behaelter mit model.db und format.txt."""
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "model.db")
    build_db(db, **kw)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db, "model.db")
        z.writestr("format.txt", "RFEM\n6.11.0004\nRFEM6\n6.12.0010\n1773229130\n")
        z.writestr("general_data.xml", "<?xml version='1.0'?><property key='generalData'/>")
    shutil.rmtree(tmp, ignore_errors=True)
    return path


# --------------------------------------------------------------------------
# 1) Grundmodell: Knoten, Linien, Staebe, Querschnitt, Material
# --------------------------------------------------------------------------
def test_grundmodell():
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(
            os.path.join(tmp, "traeger.rf6"),
            nodes=[(0, 0, 0), (2, 0, 0), (4, 0, 0)],
            lines=[[1, 2, 3]],
            members=[(1, None, None)],
            supports=[("Gelenkig", (INF, INF, INF, INF, 0.0, 0.0), (0,) * 6, None, [1]),
                      ("Gleitlager", (0.0, INF, INF, 0.0, 0.0, 0.0), (0,) * 6, None, [3])],
        )
        info = R6.summary(f)
        check("summary: Schema erkannt", info["schema"] == "RFEM 6", info["schema"])
        check("summary: Programmkennung", info["format"].get("programm") == "RFEM",
              str(info["format"]))
        check("summary: Objektzahlen", info["objekte"]["Knoten"] == 3
              and info["objekte"]["Staebe"] == 1 and info["objekte"]["Knotenlager"] == 2,
              str(info["objekte"]))
        check("report() nennt die Datei", "RFEM" in R6.report(f))

        log = []
        m = R6.read_rf6(f, log=log)
        check("Knoten eingelesen", m.nn == 3, f"{m.nn}")
        close("Knoten 3 Koordinate x", float(m.nodes[2][0]), 4.0, 1e-9, " m")
        check("Linie uebernommen", len(m.lines) == 1 and
              list(m.lines.values())[0].nodes == [0, 1, 2])
        check("Stab in 2 Elemente zerlegt", len(m.elements) == 2,
              f"{len(m.elements)} Elemente")
        check("Stabgruppe angelegt", len(m.members) == 1)

        sec = list(m.sections.values())[0]
        d = 0.040
        close("Querschnitt A (Rund 40)", sec.A, math.pi * d ** 2 / 4, 1e-9, " m^2")
        close("Querschnitt I_y", sec.Iy, math.pi * d ** 4 / 64, 1e-9, " m^4")
        check("Querschnittsname aus Bemassung", sec.name == "Rund 40", sec.name)
        check("Querschnittsart erkannt", sec.typ == "circle", sec.typ)
        close("Querschnittshoehe = d", sec.h, d, 1e-9, " m")

        mat = list(m.materials.values())[0]
        close("Material E", mat.E, 210e9, 1e-9, " Pa")
        close("Material f_y", mat.fy, 355e6, 1e-9, " Pa")
        check("Materialname aus Streckgrenze", mat.name == "S355", mat.name)
        check("Stahlsorte gesetzt", mat.grade == "S355", mat.grade)

        check("Lager gesetzt", len(m.supports) == 2, f"{len(m.supports)}")
        s0 = [s for s in m.supports if s.node == 0][0]
        check("gelenkiges Lager: ux, uy, uz, phix", sorted(s0.dofs) == [0, 1, 2, 3],
              str(s0.dofs))
        s2 = [s for s in m.supports if s.node == 2][0]
        check("Gleitlager: nur uy, uz", sorted(s2.dofs) == [1, 2], str(s2.dofs))
        check("Lagername uebernommen", s0.name == "Gelenkig", s0.name)

        check("Lastfall uebernommen", "LF1" in m.load_cases, str(list(m.load_cases)))
        close("Eigengewichtsfaktor z", m.load_cases["LF1"].gravity[2], -9.81, 1e-6, " m/s^2")

        # Rechnung: Kragarm mit Einzellast am freien Ende waere ueberbestimmt;
        # hier Einfeldtraeger mit Einzellast in Feldmitte, L = 4 m
        m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
        P = 1000.0
        m.load_node(1, Fz=-P, case="LF1")
        r = solver.solve_static(m, case="LF1")
        E, I = mat.E, sec.Iy
        L = 4.0
        G, As = mat.G, sec.Asz
        w_b = P * L ** 3 / (48 * E * I)
        w_s = P * L / (4 * G * As)
        close("Durchbiegung Feldmitte (Biegung + Schub)",
              abs(float(r.u.reshape(-1, 6)[1, 2])), w_b + w_s, 2e-3, " m")
        Rz = float(r.reactions[:, 2].sum())
        close("Summe Auflagerkraefte = P", Rz, P, 1e-6, " N")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 2) Nichtlineare Lager: Ausfall, Schlupf, Grenzkraft, Reibung
# --------------------------------------------------------------------------
def test_nichtlineare_lager():
    tmp = tempfile.mkdtemp()
    try:
        # Zugausfall (Kennzahl 1) am Endlager, Reibung an uz mit mu = 0.3
        f = make_rf6(
            os.path.join(tmp, "nl.rf6"),
            nodes=[(0, 0, 0), (2, 0, 0), (4, 0, 0)],
            lines=[[1, 2, 3]],
            members=[(1, None, None)],
            supports=[
                ("Fest", (INF,) * 6, (0,) * 6, None, [1]),
                # ux/uy mit Steifigkeit 0 und Reibung: haelt starr bis mu * |F_z|
                ("Zugausfall", (0.0, 0.0, INF, 0.0, 0.0, 0.0),
                 (0, 0, 1, 0, 0, 0), (0.0, 0.3, 0.0, 0.25, 0.0, 0.0), [3]),
            ],
            partials={("nodal", 2): [(2, (0, 0.0, 0.0, 0.0, 1, 0.0, 0.0, 0.002))]},
        )
        log = []
        m = R6.read_rf6(f, log=log)
        s = [x for x in m.supports if x.node == 2][0]
        b = s.dof_behaviour(2)
        check("uz starr uebernommen", b.typ == "rigid", b.typ)
        check("Ausfall bei Zug erkannt", b.failure == "zug", b.failure or "-")
        close("Schlupf aus Teilwirkung", b.slip, 0.002, 1e-12, " m")
        bx = s.dof_behaviour(0)
        by = s.dof_behaviour(1)
        close("Reibbeiwert ux (Spalte XZ)", bx.mu, 0.3, 1e-12)
        close("Reibbeiwert uy (Spalte YZ)", by.mu, 0.25, 1e-12)
        check("Reibungs-FHG haelt starr", bx.typ == "rigid" and by.typ == "rigid",
              f"{bx.typ}/{by.typ}")
        check("Reibung bezogen auf uz", bx.mu_ref == 2 and by.mu_ref == 2,
              f"{bx.mu_ref}/{by.mu_ref}")
        check("Protokoll nennt die Kennzahl", any("Kennzahl 1" in x for x in log))
        check("Modell hat Kontaktbedingungen", m.has_contact)

        # unbekannte Kennzahl: FHG bleibt linear, Warnung im Protokoll
        f2 = make_rf6(
            os.path.join(tmp, "unbekannt.rf6"),
            nodes=[(0, 0, 0), (2, 0, 0)],
            lines=[[1, 2]],
            members=[(1, None, None)],
            supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1]),
                      ("Seltsam", (INF,) * 6, (0, 0, 99, 0, 0, 0), None, [2])],
        )
        log2 = []
        m2 = R6.read_rf6(f2, log=log2)
        b2 = [x for x in m2.supports if x.node == 1][0].dof_behaviour(2)
        check("unbekannte Kennzahl -> linear", not b2.nonlinear, b2.describe())
        check("unbekannte Kennzahl -> Warnung",
              any("Kennzahl 99 unbekannt" in x for x in log2))

        # eigene Zuordnung per Wortliste
        log3 = []
        m3 = R6.read_rf6(f2, log=log3, nonlinearity_map={99: ("druck", "Ausfall bei Druck")})
        b3 = [x for x in m3.supports if x.node == 1][0].dof_behaviour(2)
        check("eigene Zuordnung greift", b3.failure == "druck", b3.failure or "-")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 3) Zugausfall rechnen: Endlager hebt ab
# --------------------------------------------------------------------------
def test_abheben():
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(
            os.path.join(tmp, "abheben.rf6"),
            nodes=[(0, 0, 0), (2, 0, 0), (4, 0, 0)],
            lines=[[1, 2, 3]],
            members=[(1, None, None)],
            supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1, 2]),
                      ("Zugausfall", (0.0, 0.0, INF, 0.0, 0.0, 0.0),
                       (0, 0, 1, 0, 0, 0), None, [3])],
        )
        m = R6.read_rf6(f)
        m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
        P = 500.0
        m.load_node(2, Fz=+P, case="LF1")        # zieht das Endlager nach oben
        r = solver.solve_static(m, case="LF1")
        cf = r.contact
        check("Kontaktzustand gemeldet", len(cf) == 1, f"{len(cf)} Bedingungen")
        zug = [c for c in cf if c.get("dof") == 2]
        check("Bedingung ist der Zugausfall in uz", len(zug) == 1,
              zug[0]["label"] if zug else "-")
        check("Endlager faellt aus (Normalkraft = 0)",
              all(abs(c["Fn"]) < 1e-6 for c in zug),
              ", ".join(f"{c['Fn']:.3g} N" for c in zug))
        check("Zustand 'offen' gemeldet", all(c["status"] == "offen" for c in zug),
              ", ".join(c["status"] for c in zug))
        w = float(r.u.reshape(-1, 6)[2, 2])
        check("Endknoten hebt ab (w > 0)", w > 1e-9, f"w = {w * 1e3:.4g} mm")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 4) Linien- und Flaechenlager, Gelenke, Volumen
# --------------------------------------------------------------------------
def test_linien_flaechenlager():
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(
            os.path.join(tmp, "lager.rf6"),
            nodes=[(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)],
            lines=[[1, 2], [2, 3], [3, 4], [4, 1]],
            members=[(1, 1, None)],
            supports=[],
            line_supports=[("Kantenlager", (0.0, 0.0, 5e7, 0.0, 0.0, 0.0),
                            (0, 0, 1, 0, 0, 0), None, [1, 2])],
            surfaces=[[1, 2, 3, 4]],
            surface_supports=[("Bettung", (0.0, 0.0, 2.5e8, 0.0, 0.0), 1, 0.2, [1])],
            hinges=[("Momentengelenk", (INF, INF, INF, INF, 0.0, 0.0))],
        )
        log = []
        m = R6.read_rf6(f, log=log)
        check("Linienlager uebernommen", len(m.line_supports) == 1, str(len(m.line_supports)))
        ls = m.line_supports[0]
        check("Linienlager: Knoten der beiden Linien", sorted(ls.nodes) == [0, 1, 2],
              str(sorted(ls.nodes)))
        close("Linienlager uz-Steifigkeit", ls.dof_behaviour(2).stiffness, 5e7, 1e-9, " N/m/m")
        check("Linienlager: Zugausfall", ls.dof_behaviour(2).failure == "zug")

        check("Flaechenlager uebernommen", len(m.surface_supports) == 1)
        ss = m.surface_supports[0]
        close("Flaechenlager Bettungsziffer", ss.dof_behaviour(2).stiffness, 2.5e8, 1e-9, " N/m^3")
        close("Einflussflaeche gesamt = 4 m^2", sum(ss.areas), 4.0, 1e-9, " m^2")
        check("Flaechenlager: Reibung auf ux/uy",
              ss.dof_behaviour(0).mu == 0.2 and ss.dof_behaviour(0).mu_ref == 2,
              f"mu = {ss.dof_behaviour(0).mu}")

        check("Gelenk angelegt", len(m.hinges) == 1, str(list(m.hinges)))
        h = list(m.hinges.values())[0]
        check("Gelenk: phiy und phiz frei", h.released() == [4, 5], str(h.released()))
        check("Gelenk auf das Element gelegt", 4 in m.elements[0].hinges,
              str(m.elements[0].hinges))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 5) Dispatcher, Behaelter, Hilfsfunktionen
# --------------------------------------------------------------------------
def test_dispatcher_und_hilfen():
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(
            os.path.join(tmp, "dispatch.rf6"),
            nodes=[(0, 0, 0), (3, 0, 0), (9, 9, 9)],
            lines=[[1, 2]],
            members=[(1, None, None)],
            supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1])],
        )
        log = []
        m = import_file(f, log=log)
        check("import_file leitet auf den RFEM-6-Leser", m.nn == 3 and len(m.elements) == 1,
              f"{m.nn} Knoten, {len(m.elements)} Elemente")
        check("Protokoll nennt die RFEM-Version",
              any("6.11" in x for x in log), log[0] if log else "")

        m2 = import_file(f, structure_only=True)
        check("structure_only entfernt freie Knoten", m2.nn == 2, f"{m2.nn}")
        check("structure_only behaelt das Lager", len(m2.supports) == 1)

        check("_stiffness: inf = starr", R6._stiffness(INF) == ("rigid", 0.0))
        check("_stiffness: 0 = frei", R6._stiffness(0.0) == ("free", 0.0))
        check("_stiffness: endlich = Feder", R6._stiffness(1.5e7) == ("spring", 1.5e7))
        check("_stiffness: None = frei", R6._stiffness(None) == ("free", 0.0))

        # Zuordnung aus einem XSD der Web-Services
        xsd = os.path.join(tmp, "enum.xsd")
        with open(xsd, "w", encoding="utf-8") as fh:
            fh.write("""<?xml version="1.0"?><xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
            <xs:simpleType name="nodal_support_nonlinearity"><xs:restriction base="xs:string">
              <xs:enumeration value="NONLINEARITY_TYPE_NONE"/>
              <xs:enumeration value="NONLINEARITY_TYPE_FAILURE_IF_POSITIVE"/>
              <xs:enumeration value="NONLINEARITY_TYPE_FAILURE_IF_NEGATIVE"/>
              <xs:enumeration value="NONLINEARITY_TYPE_FRICTION_DIRECTION_1"/>
            </xs:restriction></xs:simpleType></xs:schema>""")
        mp = R6.nonlinearity_map_from_xsd(xsd)
        check("XSD: Kennzahl 0 = keine", mp[0][0] == "", str(mp.get(0)))
        check("XSD: Kennzahl 1 = Druckausfall", mp[1][0] == "druck", str(mp.get(1)))
        check("XSD: Kennzahl 2 = Zugausfall", mp[2][0] == "zug", str(mp.get(2)))
        check("XSD: Kennzahl 3 = Reibung", mp[3][0] == "friction", str(mp.get(3)))

        # ZIP ohne model.db
        bad = os.path.join(tmp, "leer.rf6")
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("irgendwas.txt", "nichts")
        try:
            R6.read_rf6(bad)
            check("ZIP ohne Modelldatenbank wird abgewiesen", False)
        except ImportError as ex:
            check("ZIP ohne Modelldatenbank wird abgewiesen", "model.db" in str(ex), str(ex)[:60])

        # SQLite ohne RFEM-6-Schema
        plain = os.path.join(tmp, "fremd.db")
        con = sqlite3.connect(plain)
        con.execute("CREATE TABLE Foo (a INTEGER)")
        con.commit()
        con.close()
        try:
            R6.read_rf6(plain)
            check("fremdes Schema wird abgewiesen", False)
        except ImportError as ex:
            check("fremdes Schema wird abgewiesen", "RFEM-6-Schema" in str(ex), str(ex)[:60])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 6) Zusammenfuehren doppelter Knoten haengt Linien und Lager mit um
# --------------------------------------------------------------------------
def test_knoten_zusammenfuehren():
    from statik3d.model import Model, Material, Section
    from statik3d.importers import _common as C
    m = Model()
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 0, 0], [2, 0, 0]], float))
    m.add_material(Material.steel("S235"))
    m.add_section(Section.rectangle("R", 0.1, 0.1))
    m.add_element("beam", [0, 1], "S235", "R")
    m.add_element("beam", [2, 3], "S235", "R")
    m.add_line("L1", [0, 1, 2, 3])
    m.add_line_support([0, 1, 2], uz=dict(typ="spring", stiffness=1e6))
    m.add_surface_support(name="FL", nodes=[1, 2, 3], areas=[1.0, 2.0, 4.0],
                          uz=dict(typ="spring", stiffness=1e7))
    n = C.merge_duplicate_nodes(m)
    check("ein Knoten zusammengefuehrt", n == 1 and m.nn == 3, f"{n}, nn = {m.nn}")
    check("Elemente umgehaengt", m.elements[1].nodes == [1, 2], str(m.elements[1].nodes))
    check("Linie umgehaengt (ohne Doppelung)", m.lines["L1"].nodes == [0, 1, 2],
          str(m.lines["L1"].nodes))
    check("Linienlager umgehaengt", m.line_supports[0].nodes == [0, 1],
          str(m.line_supports[0].nodes))
    ss = m.surface_supports[0]
    check("Flaechenlager umgehaengt", ss.nodes == [1, 2], str(ss.nodes))
    close("Einflussflaechen addiert (1 + 2)", ss.areas[0], 3.0, 1e-12, " m^2")
    close("Einflussflaeche unveraendert", ss.areas[1], 4.0, 1e-12, " m^2")


def main():
    for t in (test_grundmodell, test_nichtlineare_lager, test_abheben,
              test_linien_flaechenlager, test_dispatcher_und_hilfen,
              test_knoten_zusammenfuehren):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
