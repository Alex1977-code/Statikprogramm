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
from statik3d.model import Model  # noqa: E402
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
CREATE TABLE LineImplArc (id INTEGER PRIMARY KEY, version INTEGER, parent_id bigint,
                   rotationType INTEGER, angle double precision,
                   controlPoint_id bigint, controlPoint_table TEXT);
CREATE TABLE LineImplArc_definitionNodes (id INTEGER, container_order INTEGER,
                   reference_id bigint, reference_table TEXT);
CREATE TABLE ControlPoint (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE ControlPointImpl (id INTEGER PRIMARY KEY, version INTEGER, parent_id bigint,
                   coordinates_x double precision, coordinates_y double precision,
                   coordinates_z double precision);
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
CREATE TABLE SurfaceImplPlane (id INTEGER PRIMARY KEY, version INTEGER, parent_id bigint,
                   stiffness_id bigint, stiffness_table TEXT,
                   isDeactivatedForCalculation boolean);
CREATE TABLE SurfaceImplPlane_cornerNodes (id INTEGER, container_order INTEGER,
                   reference_id bigint, reference_table TEXT);
CREATE TABLE SurfaceImplPlane_boundaryLines (id INTEGER, container_order INTEGER,
                   value_id bigint);
CREATE TABLE SurfaceImplQuadrangle_boundaryLines (id INTEGER, container_order INTEGER,
                   value_id bigint);
CREATE TABLE SurfaceImplPlane_integratedOpenings (id INTEGER, container_order INTEGER,
                   value_id bigint);
CREATE TABLE SurfaceStiffnessStandard (id INTEGER PRIMARY KEY, version INTEGER,
                   owner_id bigint, owner_table TEXT, thickness_id bigint);
CREATE TABLE SurfaceStiffnessWithoutThickness (id INTEGER PRIMARY KEY, version INTEGER,
                   owner_id bigint, owner_table TEXT);
CREATE TABLE SurfaceStiffnessRigid (id INTEGER PRIMARY KEY, version INTEGER,
                   owner_id bigint, owner_table TEXT);
CREATE TABLE Thickness (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE ThicknessImplUniform (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                   parent_id bigint, material_id bigint, thickness double precision);
CREATE TABLE Solid (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE SolidImplStandard (id INTEGER PRIMARY KEY, version INTEGER, parent_id bigint,
                   material_id bigint, isDeactivatedForCalculation boolean);
CREATE TABLE SolidImplStandard_boundarySurfaces (id INTEGER, container_order INTEGER,
                   value_id bigint);
CREATE TABLE SurfaceRelease (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE SurfaceReleaseImpl (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                   comment TEXT, parent_id bigint, releaseType_id bigint,
                   releaseType_table TEXT, releaseLocation INTEGER,
                   deactivated boolean, defineReleaseTypeForEachObject boolean);
CREATE TABLE SurfaceReleaseImpl_releasedSurfaces (id INTEGER, container_order INTEGER,
                   value_id bigint);
CREATE TABLE SurfaceReleaseImpl_releasedSolids (id INTEGER, container_order INTEGER,
                   value_id bigint);
CREATE TABLE SurfaceReleaseImpl_assignedToObjects (id INTEGER, container_order INTEGER,
                   reference_id bigint, reference_table TEXT);
CREATE TABLE SurfaceReleaseImpl_useDefinitionLines (id INTEGER, container_order INTEGER,
                   value_id bigint);
CREATE TABLE SurfaceReleaseImpl_releaseTypeForObjects_values (id INTEGER,
                   container_order INTEGER, value_id bigint);
CREATE TABLE SurfaceReleaseType (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE SurfaceReleaseTypeImplVersion1 (id INTEGER PRIMARY KEY, version INTEGER,
                   name TEXT, parent_id bigint, springConstants_id bigint,
                   localAxisSystemType INTEGER);
CREATE TABLE SurfaceLoad (id INTEGER PRIMARY KEY, version INTEGER,
                   parentModelObject_id bigint, parentModelObject_table TEXT,
                   userID INTEGER, impl_id bigint, impl_table TEXT);
CREATE TABLE SurfaceTypeLoadImplForce (id INTEGER PRIMARY KEY, version INTEGER,
                   parent_id bigint, parent_table TEXT, loadDistribution INTEGER,
                   loadParameters_id bigint, loadParameters_table TEXT,
                   loadDirection INTEGER);
CREATE TABLE SurfaceTypeLoadImplForce_assignedTo (id INTEGER, container_order INTEGER,
                   value_id bigint);
CREATE TABLE SurfaceTypeLoadImplForce_NodeAndMagnitudeParameters_loadParameters
                  (id INTEGER, container_order INTEGER, magnitude double precision,
                   node_id bigint);
CREATE TABLE MemberImplBeam (id INTEGER PRIMARY KEY, version INTEGER, parent_id bigint,
                   line_id bigint, sectionStart_id bigint, sectionEnd_id bigint,
                   memberHingeStart_id bigint, memberHingeEnd_id bigint,
                   angle double precision, isDeactivatedForCalculation boolean);
CREATE TABLE MemberImplResultBeam (id INTEGER PRIMARY KEY, version INTEGER, parent_id bigint,
                   line_id bigint, sectionStart_id bigint, sectionEnd_id bigint,
                   memberHingeStart_id bigint, memberHingeEnd_id bigint,
                   angle double precision, isDeactivatedForCalculation boolean);
CREATE TABLE FreeRectangularLoad (id INTEGER PRIMARY KEY, version INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE NodalLoad (id INTEGER PRIMARY KEY, version INTEGER,
                   parentModelObject_id bigint, parentModelObject_table TEXT,
                   userID INTEGER, impl_id bigint, impl_table TEXT);
CREATE TABLE NodalTypeLoadImplForce (id INTEGER PRIMARY KEY, version INTEGER,
                   parent_id bigint, parent_table TEXT, loadDirection INTEGER,
                   forceMagnitude_x double precision, forceMagnitude_y double precision,
                   forceMagnitude_z double precision,
                   momentMagnitude_x double precision, momentMagnitude_y double precision,
                   momentMagnitude_z double precision, magnitude double precision);
CREATE TABLE NodalTypeLoadImplForce_assignedTo (id INTEGER, container_order INTEGER,
                   value_id bigint);
CREATE TABLE MemberLoad (id INTEGER PRIMARY KEY, version INTEGER,
                   parentModelObject_id bigint, parentModelObject_table TEXT,
                   userID INTEGER, impl_id bigint, impl_table TEXT);
CREATE TABLE MemberTypeLoadImplInitialPrestress (id INTEGER PRIMARY KEY, version INTEGER,
                   parent_id bigint, parent_table TEXT, magnitude double precision);
CREATE TABLE MemberTypeLoadImplInitialPrestress_assignedTo (id INTEGER,
                   container_order INTEGER, value_id bigint);
CREATE TABLE ResultCombination (id INTEGER PRIMARY KEY, version INTEGER, userID INTEGER,
                   impl_id bigint, impl_table TEXT);
CREATE TABLE ResultCombinationImpl (id INTEGER PRIMARY KEY, version INTEGER, name TEXT,
                   parent_id bigint, designSituationType INTEGER);
CREATE TABLE ResultCombinationImpl_items (id INTEGER, container_order INTEGER,
                   modelObject_id bigint, modelObject_table TEXT,
                   modelObjectFactor REAL, groupFactor REAL,
                   leftParenthesis boolean, rightParenthesis boolean,
                   operator INTEGER, subResult INTEGER);
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
             surface_supports=(), surfaces=(), hinges=(), partials=(),
             solids=(), releases=(), surface_loads=(), load_cases=(),
             free_loads=0, openings=(), nodal_loads=(), prestress=(),
             combinations=(), boundary_lines=None, stiffness_reverse=False,
             rigid_surfaces=()):
    """Modelldatenbank im RFEM-6-Schema erzeugen.

    ``surfaces``   Eintrag ``[Knoten...]``           -> Flaeche ohne Dicke
                   Eintrag ``([Knoten...], t)``      -> Flaeche mit Dicke t [m]
    ``solids``     Liste der Randflaechennummern je Volumenkoerper
    ``releases``   (Name, [Flaechen], [Volumen], Zielzahl, Federn, Kennzahlen)
    ``surface_loads`` (Lastfall-id, [Flaechen], Groesse [N/m^2], Richtung)
    ``load_cases`` (Name, Einwirkungskategorie, Eigengewichtsfaktor z)
    ``openings``   Flaechennummern, die eine Oeffnung tragen
    ``nodal_loads``   (Lastfall-id, [Knoten], (Fx,Fy,Fz), (Mx,My,Mz))
    ``prestress``     (Lastfall-id, [Stabnummern], N_0 [N])
    ``combinations``  (Name, Situationsart, {Lastfall-id: Faktor})
    ``boundary_lines`` {Flaechennummer: [Liniennummern]} - Randlinien
    ``stiffness_reverse`` Vorwaertszeiger der Flaeche leer lassen; die
                   Steifigkeit ist dann nur ueber ``owner_id`` zu finden
    ``rigid_surfaces`` Flaechennummern mit SurfaceStiffnessRigid
    """
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    for i, (x, y, z) in enumerate(nodes, 1):
        con.execute("INSERT INTO Node VALUES (?,1,?,?,'NodeImplStandard')", (i, i, i))
        con.execute("INSERT INTO NodeImplStandard VALUES (?,1,?,?,?,?)", (i, i, x, y, z))
    cp_id = 0
    for i, entry in enumerate(lines, 1):
        # [Knoten]                  -> Polylinie
        # ([Knoten], (x, y, z))     -> Bogen ueber seinen Kontrollpunkt
        ns, mitte = (entry, None) if not isinstance(entry, tuple) else entry
        if mitte is None:
            con.execute("INSERT INTO Line VALUES (?,1,?,?,'LineImplPolyline')", (i, i, i))
            con.execute("INSERT INTO LineImplPolyline VALUES (?,1,?)", (i, i))
            tbl = "LineImplPolyline_definitionNodes"
        else:
            cp_id += 1
            con.execute("INSERT INTO ControlPoint VALUES (?,1,?,?,'ControlPointImpl')",
                        (cp_id, cp_id, cp_id))
            con.execute("INSERT INTO ControlPointImpl VALUES (?,1,?,?,?,?)",
                        (cp_id, cp_id, mitte[0], mitte[1], mitte[2]))
            con.execute("INSERT INTO Line VALUES (?,1,?,?,'LineImplArc')", (i, i, i))
            con.execute("INSERT INTO LineImplArc VALUES (?,1,?,2,0.0,?,'ControlPoint')",
                        (i, i, cp_id))
            tbl = "LineImplArc_definitionNodes"
        for j, n in enumerate(ns):
            con.execute(f"INSERT INTO {tbl} VALUES (?,?,?,'Node')", (i, j, n))
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
    for i, mem in enumerate(members, 1):
        line, hs, he = mem[:3]
        tbl = mem[3] if len(mem) > 3 else "MemberImplBeam"
        con.execute("INSERT INTO Member VALUES (?,1,?,?,?)", (i, i, i, tbl))
        con.execute(f"INSERT INTO {tbl} VALUES (?,1,?,?,1,1,?,?,0,0)", (i, i, line, hs, he))
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
    thick_id = 0
    for i, entry in enumerate(surfaces, 1):
        # [Knoten]        -> Viereckflaeche ohne Steifigkeitsobjekt
        # ([Knoten], 0.0) -> Flaeche mit SurfaceStiffnessWithoutThickness
        # ([Knoten], t)   -> Flaeche mit Dicke t
        corners, t = (entry, None) if not isinstance(entry, tuple) else entry
        if t == 0.0:
            steif = ("SurfaceStiffnessRigid" if i in rigid_surfaces
                     else "SurfaceStiffnessWithoutThickness")
            con.execute(f"INSERT INTO {steif} VALUES (?,1,?,'SurfaceImplPlane')", (i, i))
            con.execute("INSERT INTO Surface VALUES (?,1,?,?,'SurfaceImplPlane')",
                        (i, i, i))
            # Vorwaertszeiger - in manchen Dateien ist er leer, dann bleibt
            # nur der Rueckzeiger owner_id der Steifigkeitstabelle
            con.execute("INSERT INTO SurfaceImplPlane VALUES (?,1,?,?,?,0)",
                        (i, i, None if stiffness_reverse else i,
                         None if stiffness_reverse else steif))
            for j, n in enumerate(corners):
                con.execute("INSERT INTO SurfaceImplPlane_cornerNodes "
                            "VALUES (?,?,?,'Node')", (i, j, n))
            for j, ln in enumerate((boundary_lines or {}).get(i, [])):
                con.execute("INSERT INTO SurfaceImplPlane_boundaryLines "
                            "VALUES (?,?,?)", (i, j, ln))
            continue
        if not t:
            # Flaeche ohne eigene Steifigkeit (Randflaeche eines Volumens):
            # Viereckflaeche mit Null-Steifigkeit, wie in echten Volumenmodellen
            con.execute("INSERT INTO Surface VALUES (?,1,?,?,'SurfaceImplQuadrangle')",
                        (i, i, i))
            con.execute("INSERT INTO SurfaceImplQuadrangle VALUES (?,1,?)", (i, i))
            for j, n in enumerate(corners):
                con.execute("INSERT INTO SurfaceImplQuadrangle_cornerNodes "
                            "VALUES (?,?,?,'Node')", (i, j, n))
            for j, ln in enumerate((boundary_lines or {}).get(i, [])):
                con.execute("INSERT INTO SurfaceImplQuadrangle_boundaryLines "
                            "VALUES (?,?,?)", (i, j, ln))
            continue
        # Flaeche mit Dicke: SurfaceImplPlane -> SurfaceStiffnessStandard -> Thickness
        thick_id += 1
        con.execute("INSERT INTO Thickness VALUES (?,1,?,?,'ThicknessImplUniform')",
                    (thick_id, thick_id, thick_id))
        con.execute("INSERT INTO ThicknessImplUniform VALUES (?,1,?,?,1,?)",
                    (thick_id, f"D{thick_id}", thick_id, t))
        con.execute("INSERT INTO SurfaceStiffnessStandard VALUES (?,1,?,'SurfaceImplPlane',?)",
                    (i, i, thick_id))
        con.execute("INSERT INTO Surface VALUES (?,1,?,?,'SurfaceImplPlane')", (i, i, i))
        con.execute("INSERT INTO SurfaceImplPlane VALUES (?,1,?,?,"
                    "'SurfaceStiffnessStandard',0)", (i, i, i))
        for j, n in enumerate(corners):
            con.execute("INSERT INTO SurfaceImplPlane_cornerNodes VALUES (?,?,?,'Node')",
                        (i, j, n))
        for j, ln in enumerate((boundary_lines or {}).get(i, [])):
            con.execute("INSERT INTO SurfaceImplPlane_boundaryLines VALUES (?,?,?)",
                        (i, j, ln))
        if i in openings:
            con.execute("INSERT INTO SurfaceImplPlane_integratedOpenings VALUES (?,0,1)", (i,))
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
    for i, faces in enumerate(solids, 1):
        con.execute("INSERT INTO Solid VALUES (?,1,?,?,'SolidImplStandard')", (i, i, i))
        con.execute("INSERT INTO SolidImplStandard VALUES (?,1,?,1,0)", (i, i))
        for j, sf in enumerate(faces):
            con.execute("INSERT INTO SolidImplStandard_boundarySurfaces VALUES (?,?,?)",
                        (i, j, sf))
    for i, (name, srf, sol, ziele, k, nl) in enumerate(releases, 1):
        con.execute("INSERT INTO SurfaceReleaseType VALUES (?,1,?,?,"
                    "'SurfaceReleaseTypeImplVersion1')", (i, i, i))
        con.execute("INSERT INTO SurfaceReleaseTypeImplVersion1 VALUES (?,1,?,?,?,0)",
                    (i, f"Fuge {i}", i, sid))
        _spring(con, sid, i, "SurfaceReleaseTypeImplVersion1", k, nl)
        sid += 1
        con.execute("INSERT INTO SurfaceRelease VALUES (?,1,?,?,'SurfaceReleaseImpl')",
                    (i, i, i))
        con.execute("INSERT INTO SurfaceReleaseImpl VALUES (?,1,'',?,?,?,"
                    "'SurfaceReleaseType',0,0,0)", (i, name, i, i))
        for j, n in enumerate(srf):
            con.execute("INSERT INTO SurfaceReleaseImpl_releasedSurfaces VALUES (?,?,?)",
                        (i, j, n))
        for j, n in enumerate(sol):
            con.execute("INSERT INTO SurfaceReleaseImpl_releasedSolids VALUES (?,?,?)",
                        (i, j, n))
        for j in range(ziele):
            con.execute("INSERT INTO SurfaceReleaseImpl_assignedToObjects "
                        "VALUES (?,?,?,'Solid')", (i, j, j + 1))
    faelle = load_cases or [("Eigengewicht", 1, 1.0)]
    for i, (name, cat, gz) in enumerate(faelle, 1):
        con.execute("INSERT INTO LoadCase VALUES (?,1,?,?,'LoadCaseImplStatic')", (i, i, i))
        con.execute("INSERT INTO LoadCaseImplStatic VALUES (?,1,?,?,?,?,0,0,?)",
                    (i, name, i, cat, 1 if gz else 0, gz))
    for i, (lc, srf, p, richtung) in enumerate(surface_loads, 1):
        con.execute("INSERT INTO SurfaceLoad VALUES (?,1,?,'LoadCase',?,?,"
                    "'SurfaceTypeLoadImplForce')", (i, lc, i, i))
        con.execute("INSERT INTO SurfaceTypeLoadImplForce VALUES (?,1,?,'SurfaceLoad',0,?,"
                    "'SurfaceTypeLoadImplForce_NodeAndMagnitudeParameters',?)",
                    (i, i, i, richtung))
        con.execute("INSERT INTO SurfaceTypeLoadImplForce_NodeAndMagnitudeParameters"
                    "_loadParameters VALUES (?,0,?,NULL)", (i, p))
        for j, n in enumerate(srf):
            con.execute("INSERT INTO SurfaceTypeLoadImplForce_assignedTo VALUES (?,?,?)",
                        (i, j, n))
    for i in range(1, free_loads + 1):
        con.execute("INSERT INTO FreeRectangularLoad VALUES (?,1,?,'x')", (i, i))
    for i, (lc, knoten, F, M) in enumerate(nodal_loads, 1):
        con.execute("INSERT INTO NodalLoad VALUES (?,1,?,'LoadCase',?,?,"
                    "'NodalTypeLoadImplForce')", (i, lc, i, i))
        con.execute("INSERT INTO NodalTypeLoadImplForce VALUES "
                    "(?,1,?,'NodalLoad',1,?,?,?,?,?,?,0)",
                    (i, i) + tuple(F) + tuple(M))
        for j, n in enumerate(knoten):
            con.execute("INSERT INTO NodalTypeLoadImplForce_assignedTo VALUES (?,?,?)",
                        (i, j, n))
    for i, (lc, staebe, N0) in enumerate(prestress, 1):
        con.execute("INSERT INTO MemberLoad VALUES (?,1,?,'LoadCase',?,?,"
                    "'MemberTypeLoadImplInitialPrestress')", (i, lc, i, i))
        con.execute("INSERT INTO MemberTypeLoadImplInitialPrestress VALUES "
                    "(?,1,?,'MemberLoad',?)", (i, i, N0))
        for j, n in enumerate(staebe):
            con.execute("INSERT INTO MemberTypeLoadImplInitialPrestress_assignedTo "
                        "VALUES (?,?,?)", (i, j, n))
    for i, (name, situation, faktoren) in enumerate(combinations, 1):
        con.execute("INSERT INTO ResultCombination VALUES (?,1,?,?,"
                    "'ResultCombinationImpl')", (i, i, i))
        con.execute("INSERT INTO ResultCombinationImpl VALUES (?,1,?,?,?)",
                    (i, name, i, situation))
        for j, (lcid, f) in enumerate(faktoren.items()):
            con.execute("INSERT INTO ResultCombinationImpl_items VALUES "
                        "(?,?,?,'LoadCase',?,1.0,0,0,0,0)", (i, j, lcid, f))
    con.commit()
    con.close()


MESH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<property key="meshConfig">
  <property value="0.075" key="E_VALUE_GENERAL_TARGET_LENGTH_OF_FE"/>
  <property value="0.002" key="E_VALUE_GENERAL_MAXIMUM_DISTANCE_BETWEEN_NODE_AND_LINE"/>
  <property value="12" key="E_VALUE_MEMBERS_NUMBER_OF_DIVISIONS_FOR_SPECIAL_TYPES"/>
  <property value="2.5" key="E_VALUE_SURFACES_MAXIMUM_RATIO_OF_FE"/>
  <property value="1" key="E_VALUE_SURFACES_SHAPE_OF_FINITE_ELEMENTS"/>
  <property value="true" key="E_VALUE_SURFACES_MAPPED_MESH_PREFERRED"/>
</property>"""


def make_rf6(path, mesh_xml: str = MESH_XML, **kw):
    """.rf6-Behaelter mit model.db, format.txt und mesh.xml."""
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "model.db")
    build_db(db, **kw)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db, "model.db")
        if mesh_xml:
            z.writestr("mesh.xml", mesh_xml)
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
# 4b) Flaechen mit Dicke, Volumenkoerper, Stabtypen
# --------------------------------------------------------------------------
#: Wuerfel 1 m: Boden, Deckel, vier Seiten (Knoten 1..8)
WUERFEL_FLAECHEN = [[1, 2, 3, 4], [5, 6, 7, 8],
                    [1, 2, 6, 5], [2, 3, 7, 6], [3, 4, 8, 7], [4, 1, 5, 8]]
WUERFEL_KNOTEN = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                  (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]


def test_flaechen_mit_dicke():
    """Flaeche mit Dicke -> Schalenelemente, Flaeche ohne Dicke -> keine."""
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(
            os.path.join(tmp, "platte.rf6"),
            nodes=[(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0),
                   (4, 0, 0), (4, 2, 0), (6, 0, 0), (6, 2, 0)],
            lines=[[1, 2], [2, 3], [3, 4], [4, 1]],
            members=[],
            supports=[],
            surfaces=[([1, 2, 3, 4], 0.012),      # 12 mm -> Schalen
                      ([2, 5, 6, 3], 0.012),       # gleiche Dicke -> gleiche Kennung
                      ([5, 7, 8, 6], 0.0),         # ohne Dicke -> nichts
                      ([1, 2, 3, 4], 0.020)],      # mit Oeffnung -> nicht vernetzt
            openings=(4,),
            boundary_lines={1: [1, 2, 3, 4]},
        )
        log = []
        m = R6.read_rf6(f, log=log)
        check("Flaeche mit Dicke vernetzt", len(m.elements) > 0, f"{len(m.elements)} Elemente")
        check("nur Schalenelemente", all(e.typ.startswith("shell") for e in m.elements),
              ", ".join(sorted({e.typ for e in m.elements})))
        check("jede Flaeche wird ein Modellobjekt", len(m.flaechen) == 4,
              ", ".join(m.flaechen))
        check("Randlinien am Objekt", m.flaechen["F1"].linien == ["L1", "L2", "L3", "L4"],
              str(m.flaechen["F1"].linien))
        check("Objekt kennt seine Elemente", len(m.flaechen["F1"].elemente) == 1,
              str(m.flaechen["F1"].elemente))
        check("Flaeche ohne Dicke traegt kein Netz",
              not m.flaechen["F3"].elemente and "Null-Element" in m.flaechen["F3"].kommentar,
              m.flaechen["F3"].kommentar)
        check("zwei gleich dicke Flaechen teilen die Kennung",
              m.flaechen["F1"].dicke == m.flaechen["F2"].dicke == "d12",
              f"{m.flaechen['F1'].dicke} / {m.flaechen['F2'].dicke}")
        check("die dickere Flaeche hat ihre eigene Kennung",
              m.flaechen["F4"].dicke == "d20", m.flaechen["F4"].dicke)
        close("Schalendicke", m.shells["d12"].t, 0.012, 1e-12, " m")
        check("Flaeche ohne Dicke gemeldet",
              any("ohne eigene Steifigkeit" in x for x in log),
              next((x for x in log if "ohne eigene" in x), "-"))
        check("Flaeche mit Oeffnung nicht vernetzt",
              any("Oeffnung" in x for x in log), next((x for x in log if "ffnung" in x), "-"))
        check("Zahl der Objekte und der vernetzten genannt",
              any("4 Flaechen als Objekte angelegt" in x and "2 vernetzt" in x
                  for x in log),
              next((x for x in log if "als Objekte" in x), "-"))
        check("Netzeinstellungen aus mesh.xml", abs(m.netz.ziellaenge - 0.075) < 1e-12
              and m.netz.stabteilung == 12 and m.netz.abgebildet,
              m.netz.beschreibung())

        # Rechnung: Kragplatte, 2 m x 2 m, 12 mm, Streifenlast
        for nd in range(m.nn):
            if abs(float(m.nodes[nd][0])) < 1e-9:
                m.support(nd, [0, 1, 2, 3, 4, 5])
        m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
        for i in range(len(m.elements)):
            m.load_face(i, -1000.0, case="LF1")
        r = solver.solve_static(m, case="LF1")
        check("Kragplatte rechenbar", np.isfinite(r.u).all() and abs(r.u).max() > 0,
              f"w_max = {abs(r.u.reshape(-1, 6)[:, 2]).max() * 1e3:.3f} mm")
        close("Summe der Auflagerkraefte = q * A (2 Flaechen a 4 m^2)",
              float(r.reactions[:, 2].sum()), 1000.0 * 8.0, 1e-6, " N")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_volumenkoerper():
    """Sechs Viereckflaechen -> ein Hexaeder, vier Dreiecke -> ein Tetraeder."""
    tmp = tempfile.mkdtemp()
    try:
        # Wuerfel (Flaechen 1..6) und Tetraeder (Flaechen 7..10)
        nodes = WUERFEL_KNOTEN + [(3, 0, 0), (4, 0, 0), (3, 1, 0), (3, 0, 1)]
        tet = [[9, 10, 11], [9, 10, 12], [10, 11, 12], [9, 11, 12]]
        f = make_rf6(
            os.path.join(tmp, "volumen.rf6"),
            nodes=nodes, lines=[], members=[], supports=[],
            surfaces=WUERFEL_FLAECHEN + tet,
            solids=[[1, 2, 3, 4, 5, 6], [7, 8, 9, 10]],
        )
        log = []
        m = R6.read_rf6(f, log=log)
        typen = sorted(e.typ for e in m.elements)
        check("ein Hexaeder und ein Tetraeder", typen == ["hex8", "tet4"], str(typen))
        check("Protokoll nennt beide", any("1 Hexaeder, 1 Tetraeder" in x for x in log),
              next((x for x in log if "Hexaeder" in x), "-"))
        hex_el = [e for e in m.elements if e.typ == "hex8"][0]
        from statik3d.elements import solid as SO
        X = m.nodes[hex_el.nodes]
        close("Volumen des Hexaeders", SO.solid_volume("hex8", X), 1.0, 1e-9, " m^3")
        check("Boden und Deckel getrennt",
              sorted(hex_el.nodes[:4]) == [0, 1, 2, 3]
              and sorted(hex_el.nodes[4:]) == [4, 5, 6, 7], str(hex_el.nodes))
        tet_el = [e for e in m.elements if e.typ == "tet4"][0]
        close("Volumen des Tetraeders", SO.solid_volume("tet4", m.nodes[tet_el.nodes]),
              1.0 / 6.0, 1e-9, " m^3")

        # Reihenfolge der Randflaechen darf das Ergebnis nicht aendern
        f2 = make_rf6(
            os.path.join(tmp, "volumen2.rf6"),
            nodes=WUERFEL_KNOTEN, lines=[], members=[], supports=[],
            surfaces=[WUERFEL_FLAECHEN[i] for i in (2, 5, 1, 3, 0, 4)],
            solids=[[1, 2, 3, 4, 5, 6]],
        )
        m2 = R6.read_rf6(f2)
        e2 = m2.elements[0]
        close("Volumen unabhaengig von der Flaechenreihenfolge",
              SO.solid_volume("hex8", m2.nodes[e2.nodes]), 1.0, 1e-9, " m^3")
        K, V = SO.k_hex8(m2.nodes[e2.nodes], 210e9, 0.3)
        check("Hexaeder ist rechenbar (positive Jacobi-Determinante)",
              np.isfinite(K).all() and V > 0, f"V = {V:.4g} m^3")

        # Koerper, den der Leser ohne Vernetzer nicht bilden kann
        f3 = make_rf6(
            os.path.join(tmp, "offen.rf6"),
            nodes=WUERFEL_KNOTEN, lines=[], members=[], supports=[],
            surfaces=WUERFEL_FLAECHEN[:5],
            solids=[[1, 2, 3, 4, 5]],
        )
        log3 = []
        m3 = R6.read_rf6(f3, log=log3)
        check("unvollstaendiger Koerper nicht uebernommen",
              not [e for e in m3.elements if e.typ in ("hex8", "tet4")],
              str([e.typ for e in m3.elements]))
        check("Grund genannt (3D-Vernetzer)",
              any("Vernetzer" in x for x in log3),
              next((x for x in log3 if "Vernetzer" in x), "-"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_stabtypen():
    """Der Name der Umsetzungstabelle ist der Stabtyp."""
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(
            os.path.join(tmp, "typen.rf6"),
            nodes=[(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)],
            lines=[[1, 2], [2, 3], [3, 4]],
            members=[(1, None, None, "MemberImplBeam"),
                     (2, None, None, "MemberImplTension"),
                     (3, None, None, "MemberImplResultBeam")],
            supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1])],
        )
        log = []
        m = R6.read_rf6(f, log=log)
        typen = [e.typ for e in m.elements]
        check("Balken bleibt Balken", typen[0] == "beam", typen[0])
        check("Zugstab wird Fachwerkstab", typen[1] == "truss", typen[1])
        check("Ergebnisstab wird nicht uebernommen", len(m.elements) == 2, str(typen))
        check("Protokoll listet die Stabtypen",
              any("Stabtypen:" in x and "Balken" in x and "Zugstab" in x for x in log),
              next((x for x in log if "Stabtypen" in x), "-"))
        check("Zugstab-Hinweis (traegt hier auch Druck) steht im Protokoll",
              any("Zugstab" in x and "faellt in RFEM bei Druck aus" in x for x in log),
              next((x for x in log if "Zugstab" in x and "faellt" in x), "-"))
        check("Ergebnisstab als Nicht-Tragglied genannt",
              any("keine Tragglieder" in x and "Ergebnisstab" in x for x in log),
              next((x for x in log if "Tragglieder" in x), "-"))
        check("member_type: unbekannte Tabelle -> Balken",
              R6.member_type("MemberImplNeu")[0] == "beam")
        check("member_type: Seil ist Fachwerkstab mit Hinweis",
              R6.member_type("MemberImplCable")[0] == "truss"
              and "Seiltheorie" in R6.member_type("MemberImplCable")[2])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 4c) Flaechenfreigaben mit Typeinstellung
# --------------------------------------------------------------------------
def test_flaechenfreigaben():
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(
            os.path.join(tmp, "freigabe.rf6"),
            nodes=WUERFEL_KNOTEN, lines=[], members=[], supports=[],
            surfaces=WUERFEL_FLAECHEN,
            solids=[[1, 2, 3, 4, 5, 6]],
            # ux/uy starr, uz frei mit Ausfall bei Zug -> Kontaktfuge
            releases=[("Lagerbock-Grundplatte", [1, 2], [1], 3,
                       (INF, INF, 0.0, 0.0, 0.0, 0.0), (0, 0, 1, 0, 0, 0))],
        )
        log = []
        m = R6.read_rf6(f, log=log)
        del m
        txt = "\n".join(log)
        check("Name der Freigabe uebernommen", "Lagerbock-Grundplatte" in txt)
        check("freigegebene Flaechen gezaehlt", "2 freigegebene Flaechen" in txt,
              next((x for x in log if "freigegebene" in x), "-"))
        check("freigegebene Volumen gezaehlt", "1 Volumen" in txt)
        check("Zuordnung gezaehlt", "zugeordnet an 3 Objekte" in txt)
        check("Ort der Freigabe genannt", "Ort Anfang" in txt)
        check("Typeinstellung: ux und uy starr", "ux=starr" in txt and "uy=starr" in txt,
              next((x for x in log if "ux=" in x), "-"))
        check("Typeinstellung: uz frei mit Ausfall bei Zug",
              "uz=frei (Ausfall bei Zug)" in txt,
              next((x for x in log if "uz=" in x), "-"))
        check("Typname genannt", "Fuge 1" in txt)
        check("nicht ausgefuehrte Trennung wird benannt",
              "Trennung selbst wird nicht ausgefuehrt" in txt)
        check("Folge der fehlenden Trennung benannt", "zu steif" in txt)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 4d) Lastfaelle mit Lasten
# --------------------------------------------------------------------------
def test_lastfaelle_und_lasten():
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(
            os.path.join(tmp, "lasten.rf6"),
            nodes=[(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0),
                   (4, 0, 0), (4, 2, 0)],
            lines=[], members=[], supports=[],
            surfaces=[([1, 2, 3, 4], 0.010), [2, 5, 6, 3]],
            load_cases=[("Eigengewicht", 1, 1.0), ("Schnee", 12, 0.0)],
            # 2 kN/m^2 auf die vernetzte Flaeche, 3 kN/m^2 auf die Flaeche ohne Dicke
            surface_loads=[(2, [1], -2000.0, 0), (2, [2], -3000.0, 1)],
            free_loads=5,
        )
        log = []
        m = R6.read_rf6(f, log=log)
        txt = "\n".join(log)
        check("beide Lastfaelle uebernommen", len(m.load_cases) == 2, str(list(m.load_cases)))
        lf2 = m.load_cases["LF2"]
        check("Lastfallname als Beschreibung", lf2.description == "Schnee", lf2.description)
        check("Einwirkungskategorie aus RFEM", m.load_cases["LF1"].category == "G",
              m.load_cases["LF1"].category)
        close("Eigengewicht nur im ersten Lastfall",
              m.load_cases["LF1"].gravity[2], -9.81, 1e-9, " m/s^2")
        close("zweiter Lastfall ohne Eigengewicht", lf2.gravity[2], 0.0, 1e-12, " m/s^2")
        check("Flaechenlast auf die vernetzte Flaeche gelegt", lf2.n_loads > 0,
              f"{lf2.n_loads} Lasten")
        check("Protokoll: eine Last gelegt", "1 Flaechenlasten auf vernetzte" in txt,
              next((x for x in log if "auf vernetzte" in x), "-"))
        check("Protokoll: eine Last ohne Zielflaeche",
              "1 Flaechenlasten ohne vernetzte Zielflaeche" in txt,
              next((x for x in log if "ohne vernetzte" in x), "-"))
        check("Lastrichtung im Klartext", "lokal z" in txt and "global Z" in txt,
              next((x for x in log if "Lastrichtung" in x), "-"))
        check("freie Rechtecklasten mit Grund genannt",
              "5 freie Rechtecklasten nicht uebernommen" in txt,
              next((x for x in log if "Rechtecklasten" in x), "-"))

        # Rechnung: Kragplatte 2 m unter 2 kN/m^2
        for nd in range(m.nn):
            if abs(float(m.nodes[nd][0])) < 1e-9:
                m.support(nd, [0, 1, 2, 3, 4, 5])
        r = solver.solve_static(m, case="LF2")
        Rz = float(r.reactions[:, 2].sum())
        close("Summe der Auflagerkraefte = q * A", Rz, 2000.0 * 4.0, 1e-6, " N")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 4e) Knotenlasten, Vorspannung, Kombinationen, Netzeinstellungen
# --------------------------------------------------------------------------
def test_lasten_und_kombinationen():
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(
            os.path.join(tmp, "lasten2.rf6"),
            nodes=[(0, 0, 0), (2, 0, 0), (4, 0, 0)],
            lines=[[1, 2], [2, 3]],
            members=[(1, None, None), (2, None, None)],
            supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1])],
            load_cases=[("Eigengewicht", 1, 1.0), ("Nutzlast", 12, 0.0),
                        ("Vorspannung", 3, 0.0)],
            nodal_loads=[(2, [3], (0.0, 0.0, -50e3), (0.0, 12e3, 0.0)),
                         (2, [2], (10e3, 0.0, 0.0), (0.0, 0.0, 0.0)),
                         (2, [], (5e3, 0.0, 0.0), (0.0, 0.0, 0.0))],   # ohne Ziel
            prestress=[(3, [1, 2], 120e3)],
            combinations=[("GZT: 1,35 G + 1,5 Q", 0, {1: 1.35, 2: 1.5}),
                          ("GZG selten", 1, {1: 1.0, 2: 1.0})],
        )
        log = []
        m = R6.read_rf6(f, log=log)
        txt = "\n".join(log)

        # ---- Knotenlasten
        lf2 = m.load_cases["LF2"]
        check("Knotenlasten uebernommen", len(lf2.nodal_loads) == 2,
              f"{len(lf2.nodal_loads)}")
        l = [x for x in lf2.nodal_loads if x.node == 2][0]
        close("Knotenlast Fz", l.F[2], -50e3, 1e-9, " N")
        close("Knotenlast My", l.F[4], 12e3, 1e-9, " Nm")
        check("Knotenlast ohne Ziel wird gemeldet",
              "1 Knotenlasten ohne Ziel" in txt,
              next((x for x in log if "ohne Ziel" in x), "-"))
        check("Zahl der uebernommenen Knotenlasten genannt",
              "2 Knotenlasten uebernommen" in txt)

        # ---- Vorspannung als gleichwertige Temperaturlast
        lf3 = m.load_cases["LF3"]
        check("Vorspannung auf beide Staebe gelegt", len(lf3.temp_loads) == 2,
              f"{len(lf3.temp_loads)}")
        t = lf3.temp_loads[0]
        e = m.elements[t.elem]
        sec, mat = m.sections[e.sec], m.materials[e.mat]
        close("dT = -N_0/(E*A*alpha)", t.dT, -120e3 / (mat.E * sec.A * mat.alpha),
              1e-12, " K")
        check("der Weg steht im Protokoll",
              "gleichwertige Temperaturlast" in txt,
              next((x for x in log if "Temperaturlast" in x), "-"))
        # Gegenprobe: der voll behinderte Stab traegt genau N_0
        mm = Model("Probe")
        mm.add_material(mat)
        mm.add_section(sec)
        mm.add_nodes(np.array([[0, 0, 0], [2, 0, 0.]]))
        mm.add_element("truss", [0, 1], mat.name, sec.name)
        mm.support(0, [0, 1, 2])
        mm.support(1, [0, 1, 2])
        mm.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
        mm.load_temp(0, t.dT, case="LF1")
        r = solver.solve_static(mm, case="LF1")
        close("voll behinderter Stab traegt N_0", abs(float(r.reactions[0, 0])),
              120e3, 1e-9, " N")

        # ---- Kombinationen
        check("beide Kombinationen uebernommen", len(m.combinations) == 2,
              ", ".join(m.combinations))
        k = m.combinations["GZT: 1,35 G + 1,5 Q"]
        close("Faktor auf den staendigen Lastfall", k.factors["LF1"], 1.35, 1e-12)
        close("Faktor auf die Nutzlast", k.factors["LF2"], 1.5, 1e-12)
        check("Bemessungssituation uebernommen", k.typ == "ULS", k.typ)
        check("GZG als SLS gefuehrt", m.combinations["GZG selten"].typ == "SLS_CH",
              m.combinations["GZG selten"].typ)
        check("Zahl genannt", "2 Kombinationen uebernommen" in txt)

        # ---- Netzeinstellungen
        close("Ziellaenge aus mesh.xml", m.netz.ziellaenge, 0.075, 1e-12, " m")
        close("groesster Knoten-Linien-Abstand", m.netz.knoten_linie, 0.002, 1e-12, " m")
        check("Stabteilung", m.netz.stabteilung == 12, str(m.netz.stabteilung))
        check("abgebildetes Netz bevorzugt", m.netz.abgebildet)
        check("Netzeinstellungen im Protokoll",
              "Netzeinstellungen übernommen" in txt,
              next((x for x in log if "Netzeinstellungen" in x), "-"))
        check("Teilung nach der Ziellaenge", m.netz.teilung(1.5) == 20,
              str(m.netz.teilung(1.5)))

        # ---- ohne mesh.xml bleibt die Vorgabe des Programms
        f2 = make_rf6(
            os.path.join(tmp, "ohne_mesh.rf6"), mesh_xml="",
            nodes=[(0, 0, 0), (2, 0, 0)], lines=[[1, 2]],
            members=[(1, None, None)],
            supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1])],
        )
        log2 = []
        m2 = R6.read_rf6(f2, log=log2)
        check("ohne mesh.xml gilt die Vorgabe", m2.netz.quelle == "",
              m2.netz.beschreibung())
        check("und das wird gesagt",
              any("Keine mesh.xml" in x for x in log2),
              next((x for x in log2 if "mesh.xml" in x), "-"))
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


# --------------------------------------------------------------------------
# 7) Boegen ueber ihre Kontrollpunkte - Augenbleche, Bolzen, Buchsen
# --------------------------------------------------------------------------
def test_boegen_und_kreisflaechen():
    """Ein Kreis besteht in RFEM aus zwei Halbboegen zwischen denselben zwei
    Knoten. Ueber die Knoten allein waeren das zwei Punkte - die Flaeche fiele
    in ihre Sehne zusammen und waere unsichtbar. Genau so fehlten dem Nutzer
    Augenbleche, Bolzen und Buchsen."""
    tmp = tempfile.mkdtemp()
    try:
        r = 0.05
        f = make_rf6(
            os.path.join(tmp, "buchse.rf6"),
            # Knoten 1 und 2 liegen sich auf dem Kreis gegenueber,
            # Knoten 3/4 sind die Scheitel der beiden Halbboegen
            nodes=[(-r, 0, 0), (r, 0, 0), (0, 0, 0), (2 * r, 0, 0)],
            lines=[([1, 2], (0.0, r, 0.0)),      # oberer Halbbogen
                   ([2, 1], (0.0, -r, 0.0)),     # unterer Halbbogen
                   [3, 4]],                      # eine gerade Linie zum Vergleich
            members=[], supports=[],
            surfaces=[([1, 2], 0.0)],
            boundary_lines={1: [1, 2]})
        log = []
        m = R6.read_rf6(f, log=log)
        b = m.lines["L1"]
        check("Bogen wird als Bogen gelesen", b.typ == "arc", b.typ)
        check("der Kontrollpunkt steht in der Geometrie",
              len(b.geometrie.get("punkte") or []) == 3,
              str(b.geometrie.get("punkte")))
        close("der Bogen ist ein Halbkreis", b.laenge(m), np.pi * r, 1e-9, " m")
        check("die gerade Linie bleibt gerade", m.lines["L3"].typ == "polyline",
              m.lines["L3"].typ)
        check("Protokoll nennt die Boegen",
              any("2x arc" in z for z in log),
              next((z for z in log if "Linien gelesen" in z), ""))

        fl = m.flaechen["F1"]
        check("ueber die Knoten schliesst der Rand nicht",
              len(fl.randknoten(m)) == 0, str(fl.randknoten(m)))
        P = fl.randpunkte(m)
        check("ueber die Kurven schliesst er", len(P) >= 3, f"{len(P)} Punkte")
        rad = np.linalg.norm(P - P.mean(axis=0), axis=1)
        close("alle Randpunkte liegen auf dem Kreis", float(rad.max()), r, 1e-9, " m")
        close("die Flaeche ist die Kreisflaeche", fl.inhalt(m), np.pi * r * r,
              2e-3 * np.pi * r * r, " m^2")
        check("und sie steht im Modellbaum-Objekt", fl.linien == ["L1", "L2"],
              str(fl.linien))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Eine Buchse: zwei Kreisdeckel und zwei Zylinderhaelften. Vier
    # Randflaechen mit vier Knoten - aber kein Tetraeder.
    tmp = tempfile.mkdtemp()
    try:
        r, hh = 0.05, 0.2
        f = make_rf6(
            os.path.join(tmp, "zylinder.rf6"),
            nodes=[(-r, 0, 0), (r, 0, 0), (-r, 0, hh), (r, 0, hh)],
            lines=[([1, 2], (0.0, r, 0.0)), ([2, 1], (0.0, -r, 0.0)),
                   ([3, 4], (0.0, r, hh)), ([4, 3], (0.0, -r, hh)),
                   [1, 3], [2, 4]],
            members=[], supports=[],
            surfaces=[([1, 2], 0.0), ([3, 4], 0.0),
                      ([1, 2, 4, 3], 0.0), ([1, 2, 4, 3], 0.0)],
            boundary_lines={1: [1, 2], 2: [3, 4],
                            3: [1, 5, 3, 6], 4: [2, 5, 4, 6]},
            solids=[[1, 2, 3, 4]])
        log = []
        m = R6.read_rf6(f, log=log)
        check("die Buchse wird kein Tetraeder",
              not any(e.typ == "tet4" for e in m.elements),
              str([e.typ for e in m.elements]))
        check("sie steht trotzdem als Koerper im Modell", len(m.koerper) == 1,
              str(list(m.koerper)))
        k = list(m.koerper.values())[0]
        check("und der Grund steht daran", "krumm" in k.kommentar, k.kommentar)
        check("das Protokoll nennt die krummen Randflaechen",
              any("krummen Randflaechen" in z for z in log),
              next((z for z in log if "krumm" in z), ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 8) Flaechensteifigkeit auch ueber den Rueckzeiger owner_id
# --------------------------------------------------------------------------
def test_steifigkeit_rueckzeiger():
    """In manchen Dateien ist SurfaceImpl*.stiffness_table leer; die Zuordnung
    steht dann nur in SurfaceStiffness*.owner_id. Ohne den Rueckweg waere jede
    Flaeche 'unbekannt' und rutschte als Null-Element durch."""
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(
            os.path.join(tmp, "rueck.rf6"),
            nodes=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
            lines=[], members=[], supports=[],
            surfaces=[([1, 2, 3, 4], 0.0), ([1, 2, 3, 4], 0.0)],
            rigid_surfaces=(2,), stiffness_reverse=True)
        log = []
        m = R6.read_rf6(f, log=log)
        text = "\n".join(log)
        check("keine Flaeche bleibt unbekannt", "unbekannt" not in text,
              next((z for z in log if "unbekannt" in z), ""))
        check("Null-Element erkannt", "ohne Dicke (Null-Element)" in text,
              next((z for z in log if "Null-Element" in z), ""))
        check("starre Flaeche erkannt", "starr" in text,
              next((z for z in log if "starr" in z), ""))
        check("beide Flaechen sind Objekte", len(m.flaechen) == 2, str(len(m.flaechen)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 9) Aufeinanderliegende Knoten werden nicht stillschweigend verschweisst
# --------------------------------------------------------------------------
def test_kein_stilles_verschmelzen():
    """An einer Kontaktfuge und an jeder Flaechenfreigabe liegen die Knoten
    absichtlich aufeinander. Werden sie zusammengefuehrt, ist das Modell dort
    verschweisst - zu steif, und die Freigaben laufen ins Leere."""
    from statik3d.importers.rfem_native import import_rfem_native
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(
            os.path.join(tmp, "fuge.rf6"),
            nodes=[(0, 0, 0), (1, 0, 0), (1, 0, 0), (2, 0, 0)],
            lines=[[1, 2], [3, 4]],
            members=[(1, None, None), (2, None, None)],
            supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1])])
        log = []
        m = import_rfem_native(f, log=log)
        check("die Fuge bleibt offen", m.nn == 4, f"nn = {m.nn}")
        check("und das Protokoll sagt es",
              any("NICHT zusammengefuehrt" in z for z in log),
              next((z for z in log if "liegen auf" in z), ""))
        log2 = []
        m2 = import_rfem_native(f, log=log2, merge_nodes=True)
        check("auf Verlangen wird zusammengefuehrt", m2.nn == 3, f"nn = {m2.nn}")
        check("auch das steht im Protokoll",
              any("zusammengefuehrt" in z and "NICHT" not in z for z in log2),
              next((z for z in log2 if "zusammengefuehrt" in z), ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for t in (test_grundmodell, test_nichtlineare_lager, test_abheben,
              test_linien_flaechenlager, test_flaechen_mit_dicke,
              test_volumenkoerper, test_stabtypen, test_flaechenfreigaben,
              test_lastfaelle_und_lasten, test_lasten_und_kombinationen,
              test_dispatcher_und_hilfen,
              test_knoten_zusammenfuehren, test_boegen_und_kreisflaechen,
              test_steifigkeit_rueckzeiger, test_kein_stilles_verschmelzen):
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
