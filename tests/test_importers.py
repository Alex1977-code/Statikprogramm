"""
Tests der Importer (DXF, Abaqus INP, Nastran BDF, IFC, SAF, RFEM-Tabellen).

Aufruf:  python -m tests.test_importers      (OK/FAIL-Zeilen, Exit-Code)
oder:    pytest tests/test_importers.py
Alle Beispieldateien werden im Test selbst in ein temporaeres Verzeichnis geschrieben.
"""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model  # noqa: E402
from statik3d import solver  # noqa: E402
from statik3d.importers import (import_file, explain_format, file_filter,  # noqa: E402
                                SUPPORTED, PROPRIETARY)
from statik3d.importers.xlsx_reader import write_xlsx, read_xlsx, read_csv_table  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def expect(name: str, cond, detail: str = ""):
    ok = bool(cond)
    RESULTS.append((name, ok, detail))
    print(f"{'OK ' if ok else 'FAIL'} {name:60s} {detail}")
    assert ok, f"{name} {detail}"


def close(name: str, num: float, ana: float, tol: float):
    err = abs(num - ana) / abs(ana) if ana else abs(num)
    expect(name, err <= tol, f"num={num:.6e} ana={ana:.6e} Abw={err * 100:.3f}%")


def solve_ok(name: str, model: Model, case: str = None):
    if case:
        model.active_case = case
    r = solver.solve_static(model)
    finite = bool(np.all(np.isfinite(r.u)))
    nonzero = float(np.abs(r.u).max()) > 0.0
    expect(f"{name}: Loesung endlich und ungleich Null", finite and nonzero,
           f"max|u|={np.abs(r.u).max():.3e}")
    return r


def node_at(model: Model, x, y, z, tol=1e-6) -> int:
    d = np.abs(model.nodes - np.array([x, y, z], float)).max(axis=1)
    i = int(np.argmin(d))
    assert d[i] <= tol, f"kein Knoten bei ({x}, {y}, {z})"
    return i


# --------------------------------------------------------------------------
# DXF
# --------------------------------------------------------------------------
def _dxf_pair(code, val):
    return f"{code:>3}\n{val}\n"


def _dxf_line(layer, p1, p2):
    s = _dxf_pair(0, "LINE") + _dxf_pair(8, layer)
    for k, c in enumerate(p1):
        s += _dxf_pair(10 + 10 * k, c)
    for k, c in enumerate(p2):
        s += _dxf_pair(11 + 10 * k, c)
    return s


def _dxf_face(layer, pts):
    s = _dxf_pair(0, "3DFACE") + _dxf_pair(8, layer)
    for i, p in enumerate(pts):
        for k, c in enumerate(p):
            s += _dxf_pair(10 + i + 10 * k, c)
    return s


def write_dxf(path):
    s = _dxf_pair(0, "SECTION") + _dxf_pair(2, "HEADER") + _dxf_pair(0, "ENDSEC")
    s += _dxf_pair(0, "SECTION") + _dxf_pair(2, "ENTITIES")
    # Rahmen in mm: zwei Stuetzen, ein Riegel
    s += _dxf_line("STUETZEN", (0, 0, 0), (0, 0, 4000))
    s += _dxf_line("STUETZEN", (6000, 0, 0), (6000, 0, 4000))
    s += _dxf_line("RIEGEL", (0, 0, 4000), (6000, 0, 4000))
    # Wandscheibe oberhalb des Riegels (teilt zwei Knoten mit dem Rahmen)
    s += _dxf_face("WAND", [(0, 0, 4000), (6000, 0, 4000), (6000, 0, 5000), (0, 0, 5000)])
    # Dreieck (4. Punkt == 3. Punkt) und eine unbekannte Entitaet
    s += _dxf_face("WAND", [(0, 0, 5000), (6000, 0, 5000), (3000, 0, 6000), (3000, 0, 6000)])
    s += _dxf_pair(0, "CIRCLE") + _dxf_pair(8, "0") + _dxf_pair(10, 0) + _dxf_pair(20, 0) \
        + _dxf_pair(40, 100)
    s += _dxf_pair(0, "ENDSEC") + _dxf_pair(0, "EOF")
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)


def test_dxf():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "rahmen.dxf")
        write_dxf(p)
        log = []
        m = import_file(p, log=log, section="HEA 200",
                        layer_sections={"RIEGEL": "IPE 300"})
        expect("DXF: Knotenzahl", m.nn == 7, f"nn={m.nn}")
        beams = [e for e in m.elements if e.typ == "beam"]
        shells = [e for e in m.elements if e.typ.startswith("shell")]
        expect("DXF: 3 Staebe + 2 Schalen", len(beams) == 3 and len(shells) == 2,
               f"{len(beams)} / {len(shells)}")
        expect("DXF: Schalentypen shell4 + shell3",
               sorted(e.typ for e in shells) == ["shell3", "shell4"])
        expect("DXF: Gruppen = Layer", {e.group for e in m.elements} == {"STUETZEN", "RIEGEL", "WAND"})
        expect("DXF: Querschnitt je Layer",
               all(e.sec == "IPE 300" for e in beams if e.group == "RIEGEL")
               and all(e.sec == "HEA 200" for e in beams if e.group == "STUETZEN"))
        expect("DXF: Massstab mm -> m", abs(m.nodes[:, 0].max() - 6.0) < 1e-9)
        expect("DXF: Staebe automatisch gebildet", len(m.members) == 3, str(len(m.members)))
        expect("DXF: unbekannte Entitaet protokolliert", any("CIRCLE" in s for s in log))
        expect("DXF: Quelle in Metadaten", m.meta.get("quelle") == p)
        # Lager + Last, dann rechnen
        m.fix(node_at(m, 0, 0, 0), "all")
        m.fix(node_at(m, 6, 0, 0), "all")
        m.load_node(node_at(m, 0, 0, 4), Fx=10e3)
        solve_ok("DXF", m)
        # Unterteilung
        m2 = import_file(p, subdivide=2, element_type="truss")
        expect("DXF: subdivide=2 -> 6 Fachwerkstaebe",
               sum(1 for e in m2.elements if e.typ == "truss") == 6)


# --------------------------------------------------------------------------
# Abaqus INP
# --------------------------------------------------------------------------
INP = """\
*HEADING
Kragarm B31
** Knoten
*NODE, NSET=ALLE
1, 0.0, 0.0, 0.0
2, 0.5, 0.0, 0.0
3, 1.0, 0.0, 0.0
4, 1.5, 0.0, 0.0
5, 2.0, 0.0, 0.0
*ELEMENT, TYPE=B31, ELSET=BALKEN
1, 1, 2
2, 2, 3
3, 3, 4
4, 4, 5
*NSET, NSET=FEST
1
*NSET, NSET=SPITZE
5
*MATERIAL, NAME=STAHL
*ELASTIC
210.0E9, 0.3
*DENSITY
7850.0
*BEAM SECTION, SECTION=RECT, ELSET=BALKEN, MATERIAL=STAHL
0.1, 0.05
0.0, 0.0, -1.0
*BOUNDARY
FEST, ENCASTRE
*STEP, NAME=LAST
*STATIC
*CLOAD
SPITZE, 3, -1000.0
*END STEP
"""


def test_abaqus_inp():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "kragarm.inp")
        with open(p, "w") as f:
            f.write(INP)
        log = []
        m = import_file(p, log=log)
        expect("INP: 5 Knoten, 4 Balken", m.nn == 5 and len(m.elements) == 4
               and all(e.typ == "beam" for e in m.elements))
        expect("INP: Material E", abs(m.materials["STAHL"].E - 210e9) < 1 and
               abs(m.materials["STAHL"].rho - 7850) < 1e-9)
        sec = m.sections[m.elements[0].sec]
        expect("INP: RECT-Querschnitt (a=h=0.1, b=0.05)", abs(sec.h - 0.1) < 1e-12
               and abs(sec.b - 0.05) < 1e-12, f"h={sec.h} b={sec.b}")
        expect("INP: Einspannung (6 FHG)", len(m.supports) == 1 and m.supports[0].node == 0
               and sorted(m.supports[0].dofs) == [0, 1, 2, 3, 4, 5])
        expect("INP: Lastfall LAST mit Knotenlast", "LAST" in m.load_cases
               and len(m.load_cases["LAST"].nodal_loads) == 1
               and m.load_cases["LAST"].nodal_loads[0].F[2] == -1000.0)
        expect("INP: Stab automatisch gebildet", len(m.members) == 1
               and len(next(iter(m.members.values())).elements) == 4)
        expect("INP: Richtungskosinus im Protokoll", any("Richtungskosinus" in s for s in log))
        r = solve_ok("INP", m, "LAST")
        L, F, E = 2.0, 1000.0, 210e9
        I = 0.05 * 0.1 ** 3 / 12.0
        G = E / (2 * 1.3)
        ana = F * L ** 3 / (3 * E * I) + F * L / (G * sec.Asz)
        close("INP: Kragarm-Durchbiegung F L³/(3 E I)", -r.u[4, 2], ana, 0.01)


# --------------------------------------------------------------------------
# Nastran BDF
# --------------------------------------------------------------------------
def _f8(*vals):
    return "".join(f"{str(v):<8s}" for v in vals).rstrip() + "\n"


BDF_SMALL = (
    "$ Kragarm CBAR / PBARL BAR\n"
    "SOL 101\nCEND\nBEGIN BULK\n"
    + _f8("GRID", 1, "", "0.0", "0.0", "0.0")
    + _f8("GRID", 2, "", "0.5", "0.0", "0.0")
    + _f8("GRID", 3, "", "1.0", "0.0", "0.0")
    + _f8("GRID", 4, "", "1.5", "0.0", "0.0")
    + _f8("GRID", 5, "", "2.0", "0.0", "0.0")
    + _f8("CBAR", 1, 1, 1, 2, "0.0", "0.0", "1.0")
    + _f8("CBAR", 2, 1, 2, 3, "0.0", "0.0", "1.0")
    + _f8("CBAR", 3, 1, 3, 4, "0.0", "0.0", "1.0")
    + _f8("CBAR", 4, 1, 4, 5, "0.0", "0.0", "1.0")
    + _f8("PBARL", 1, 1, "", "BAR")
    + _f8("", "0.1", "0.05")
    + _f8("MAT1", 1, "2.1+11", "", "0.3", "7850.0")
    + _f8("SPC1", 1, 123456, 1)
    + _f8("FORCE", 2, 5, 0, "1000.0", "0.0", "0.0", "-1.0")
    + _f8("GRAV", 3, 0, "9.81", "0.0", "0.0", "-1.0")
    + _f8("LOAD", 10, "1.0", "1.35", 3, "1.5", 2)
    + _f8("TEMPD", 4, "20.0")
    + "ENDDATA\n"
)

BDF_FREE = textwrap.dedent("""\
    $ Kragarm im Free-Field-Format
    BEGIN BULK
    GRID,1,,0.0,0.0,0.0
    GRID,2,,0.5,0.0,0.0
    GRID,3,,1.0,0.0,0.0
    GRID,4,,1.5,0.0,0.0
    GRID,5,,2.0,0.0,0.0
    CBAR,1,1,1,2,0.0,0.0,1.0
    CBAR,2,1,2,3,0.0,0.0,1.0
    CBAR,3,1,3,4,0.0,0.0,1.0
    CBAR,4,1,4,5,0.0,0.0,1.0
    PBARL,1,1,,BAR
    ,0.1,0.05
    MAT1,1,2.1+11,,0.3,7850.0
    SPC1,1,123456,1
    FORCE,2,5,0,1000.0,0.0,0.0,-1.0
    ENDDATA
    """)


def _check_bdf(name, m, r_case="SID 2"):
    expect(f"{name}: 5 Knoten, 4 Balken", m.nn == 5 and len(m.elements) == 4
           and all(e.typ == "beam" for e in m.elements))
    sec = m.sections[m.elements[0].sec]
    # DIM1 = 0.1 in Ebene 1 (vertikal, Orientierungsvektor z) -> Iz = DIM2*DIM1^3/12
    I1 = 0.05 * 0.1 ** 3 / 12.0
    close(f"{name}: PBARL BAR -> Iz = I1", sec.Iz, I1, 1e-9)
    expect(f"{name}: Verdrehung aus Orientierungsvektor",
           abs(abs(m.elements[0].roll) - np.pi / 2) < 1e-9, f"roll={m.elements[0].roll}")
    expect(f"{name}: SPC1 Einspannung", len(m.supports) == 1 and m.supports[0].node == 0
           and sorted(m.supports[0].dofs) == [0, 1, 2, 3, 4, 5])
    expect(f"{name}: Material E = 2.1e11 (Kurzschreibweise)",
           abs(m.materials["MAT 1"].E - 2.1e11) < 1)
    lc = m.load_cases[r_case]
    expect(f"{name}: FORCE -> Lastfall '{r_case}'", len(lc.nodal_loads) == 1
           and lc.nodal_loads[0].F[2] == -1000.0 and lc.nodal_loads[0].node == 4)
    r = solve_ok(name, m, r_case)
    L, F, E = 2.0, 1000.0, 2.1e11
    G = E / (2 * 1.3)
    ana = F * L ** 3 / (3 * E * I1) + F * L / (G * sec.Asz)
    close(f"{name}: Kragarm-Durchbiegung F L³/(3 E I)", -r.u[4, 2], ana, 0.01)


def test_nastran_bdf():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "kragarm.bdf")
        with open(p, "w") as f:
            f.write(BDF_SMALL)
        log = []
        m = import_file(p, log=log)
        _check_bdf("BDF (small field)", m)
        expect("BDF: GRAV -> Eigengewicht", "SID 3" in m.load_cases
               and abs(m.load_cases["SID 3"].gravity[2] + 9.81) < 1e-9)
        expect("BDF: LOAD -> Kombination", "LOAD 10" in m.combinations
               and m.combinations["LOAD 10"].factors == {"SID 3": 1.35, "SID 2": 1.5})
        expect("BDF: TEMPD protokolliert", any("TEMPD" in s for s in log))
        expect("BDF: leerer Standardlastfall entfernt", "LF1" not in m.load_cases)
        p2 = os.path.join(d, "kragarm_free.nas")
        with open(p2, "w") as f:
            f.write(BDF_FREE)
        m2 = import_file(p2)
        _check_bdf("BDF (free field)", m2)


# --------------------------------------------------------------------------
# IFC4 Structural Analysis View
# --------------------------------------------------------------------------
IFC = """\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [StructuralAnalysisView]'),'2;1');
FILE_NAME('kragarm.ifc','2024-01-01T00:00:00',(''),(''),'','','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('0YvctVUKr0kugbFTf53O9L',$,'Kragarm ''IFC''',$,$,$,$,(#20),#10);
#10=IFCUNITASSIGNMENT((#11,#12,#13,#14));
#11=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#12=IFCSIUNIT(*,.FORCEUNIT.,.KILO.,.NEWTON.);
#13=IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.);
#14=IFCDERIVEDUNIT((#15,#16),.LINEARFORCEUNIT.,$);
#15=IFCDERIVEDUNITELEMENT(#12,1);
#16=IFCDERIVEDUNITELEMENT(#17,-1);
#17=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#20=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.0E-5,#21,$);
#21=IFCAXIS2PLACEMENT3D(#22,$,$);
#22=IFCCARTESIANPOINT((0.,0.,0.));
#23=IFCLOCALPLACEMENT($,#21);
#30=IFCSTRUCTURALANALYSISMODEL('2YvctVUKr0kugbFTf53O9L',$,'Modell',$,$,
 .LOADING_3D.,$,$,$,$);
#100=IFCCARTESIANPOINT((0.,0.,0.));
#101=IFCVERTEXPOINT(#100);
#102=IFCTOPOLOGYREPRESENTATION(#20,'Reference','Vertex',(#101));
#103=IFCPRODUCTDEFINITIONSHAPE($,$,(#102));
#104=IFCSTRUCTURALPOINTCONNECTION('1YvctVUKr0kugbFTf53O9L',$,'N1',$,$,#23,#103,#105,$);
#105=IFCBOUNDARYNODECONDITION('Einspannung',IFCBOOLEAN(.T.),IFCBOOLEAN(.T.),IFCBOOLEAN(.T.),IFCBOOLEAN(.T.),IFCBOOLEAN(.T.),IFCBOOLEAN(.T.));
#110=IFCCARTESIANPOINT((3000.,0.,0.));
#111=IFCVERTEXPOINT(#110);
#112=IFCTOPOLOGYREPRESENTATION(#20,'Reference','Vertex',(#111));
#113=IFCPRODUCTDEFINITIONSHAPE($,$,(#112));
#114=IFCSTRUCTURALPOINTCONNECTION('3YvctVUKr0kugbFTf53O9L',$,'N2',$,$,#23,#113,$,$);
#120=IFCEDGE(#101,#111);
#121=IFCTOPOLOGYREPRESENTATION(#20,'Reference','Edge',(#120));
#122=IFCPRODUCTDEFINITIONSHAPE($,$,(#121));
#123=IFCSTRUCTURALCURVEMEMBER('4YvctVUKr0kugbFTf53O9L',$,'S1',$,$,#23,#122,.RIGID_JOINED_MEMBER.,#124);
#124=IFCDIRECTION((0.,0.,1.));
#130=IFCRELCONNECTSSTRUCTURALMEMBER('5YvctVUKr0kugbFTf53O9L',$,$,$,#123,#104,$,$,$,$);
#131=IFCRELCONNECTSSTRUCTURALMEMBER('6YvctVUKr0kugbFTf53O9L',$,$,$,#123,#114,$,$,$,$);
#140=IFCMATERIAL('S355',$,'Steel');
#141=IFCISHAPEPROFILEDEF(.AREA.,'IPE 200',$,100.,200.,5.6,8.5,12.,$,$);
#142=IFCMATERIALPROFILE('IPE 200',$,#140,#141,$,$);
#143=IFCMATERIALPROFILESET('IPE 200',$,(#142),$);
#144=IFCRELASSOCIATESMATERIAL('7YvctVUKr0kugbFTf53O9L',$,$,$,(#123),#143);
#150=IFCSTRUCTURALLOADCASE('8YvctVUKr0kugbFTf53O9L',$,'LC1 Nutzlast',$,$,.LOAD_CASE.,.VARIABLE_Q.,.LIVE_LOAD_Q.,$,$,$);
#151=IFCSTRUCTURALLOADSINGLEFORCE('F',0.,0.,-10.,0.,0.,0.);
#152=IFCSTRUCTURALPOINTACTION('9YvctVUKr0kugbFTf53O9L',$,'F1',$,$,#23,#113,#151,.GLOBAL_COORDS.,$);
#153=IFCRELCONNECTSSTRUCTURALACTIVITY('AYvctVUKr0kugbFTf53O9L',$,$,$,#114,#152);
#154=IFCRELASSIGNSTOGROUP('BYvctVUKr0kugbFTf53O9L',$,$,$,(#152),$,#150);
#160=IFCSTRUCTURALLOADLINEARFORCE('q',0.,0.,-2.,0.,0.,0.);
#161=IFCSTRUCTURALLINEARACTION('CYvctVUKr0kugbFTf53O9L',$,'q1',$,$,#23,#122,#160,.GLOBAL_COORDS.,$,.TRUE_LENGTH.,.CONST.);
#162=IFCRELCONNECTSSTRUCTURALACTIVITY('DYvctVUKr0kugbFTf53O9L',$,$,$,#123,#161);
#163=IFCRELASSIGNSTOGROUP('EYvctVUKr0kugbFTf53O9L',$,$,$,(#161),$,#150);
ENDSEC;
END-ISO-10303-21;
"""


def test_ifc():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "kragarm.ifc")
        with open(p, "w") as f:
            f.write(IFC)
        log = []
        m = import_file(p, log=log)
        expect("IFC: 2 Knoten, 1 Balken", m.nn == 2 and len(m.elements) == 1
               and m.elements[0].typ == "beam", f"nn={m.nn} ne={len(m.elements)}")
        expect("IFC: Einheiten mm -> m", abs(m.nodes[:, 0].max() - 3.0) < 1e-9)
        sec = m.sections[m.elements[0].sec]
        expect("IFC: I-Profil aus IfcIShapeProfileDef", sec.typ == "I"
               and abs(sec.h - 0.2) < 1e-12 and abs(sec.b - 0.1) < 1e-12
               and abs(sec.tw - 0.0056) < 1e-12, f"{sec.describe()}")
        mat = m.materials[m.elements[0].mat]
        expect("IFC: Material S355", mat.grade == "S355" and mat.fy == 355e6)
        expect("IFC: Stab S1", "S1" in m.members and m.members["S1"].elements == [0])
        expect("IFC: Einspannung an N1", len(m.supports) == 1
               and sorted(m.supports[0].dofs) == [0, 1, 2, 3, 4, 5]
               and np.allclose(m.nodes[m.supports[0].node], [0, 0, 0]))
        lc = m.load_cases.get("LC1 Nutzlast")
        expect("IFC: Lastfall LC1 (Kategorie Q)", lc is not None and lc.category == "Q")
        expect("IFC: Knotenlast -10 kN -> -10000 N", lc is not None
               and len(lc.nodal_loads) == 1 and lc.nodal_loads[0].F[2] == -10000.0
               and np.allclose(m.nodes[lc.nodal_loads[0].node], [3, 0, 0]))
        expect("IFC: Streckenlast -2 kN/m -> -2000 N/m", lc is not None
               and len(lc.beam_loads) == 1 and abs(lc.beam_loads[0].q[2] + 2000.0) < 1e-9
               and lc.beam_loads[0].system == "global")
        expect("IFC: leerer Standardlastfall entfernt", "LF1" not in m.load_cases)
        r = solve_ok("IFC", m, "LC1 Nutzlast")
        L, F, q, E = 3.0, 10000.0, 2000.0, 210e9
        G = E / (2 * 1.3)
        ana = (F * L ** 3 / (3 * E * sec.Iy) + F * L / (G * sec.Asz)
               + q * L ** 4 / (8 * E * sec.Iy) + q * L ** 2 / (2 * G * sec.Asz))
        close("IFC: Kragarm-Durchbiegung (Timoshenko)", -r.u[1, 2], ana, 0.01)


def test_ifc_parser():
    from statik3d.importers.ifc import parse_ifc, decode_step_string, Typed
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.ifc")
        with open(p, "w") as f:
            f.write(IFC)
        ifc = parse_ifc(p)
        expect("IFC-Parser: Schema", ifc.schema == "IFC4")
        proj = ifc.by_type("IfcProject")[0]
        expect("IFC-Parser: Zeichenkette mit '' ", proj[2] == "Kragarm 'IFC'")
        cond = ifc.get(105)
        expect("IFC-Parser: typisierter Wert IFCBOOLEAN", isinstance(cond[1], Typed)
               and cond[1].type == "IFCBOOLEAN" and cond[1].value == "T")
        expect("IFC-Parser: Untertypen (IfcStructuralLoadGroup -> LoadCase)",
               len(ifc.by_type("IfcStructuralLoadGroup")) == 1)
        expect("IFC-Parser: mehrzeilige Instanz", ifc.get(30) is not None
               and ifc.get(30)[5] == "LOADING_3D")
        expect("IFC-Parser: Unicode-Escape",
               decode_step_string("St\\X2\\00FC\\X0\\tze") == "Stütze")


IFC2X3 = """\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [StructuralAnalysisView]'),'2;1');
FILE_NAME('platte.ifc','2024-01-01T00:00:00',(''),(''),'','','');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1=IFCPROJECT('0YvctVUKr0kugbFTf53O9L',$,'Platte',$,$,$,$,(#20),#10);
#10=IFCUNITASSIGNMENT((#11,#12));
#11=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#12=IFCSIUNIT(*,.FORCEUNIT.,.KILO.,.NEWTON.);
#20=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.0E-5,#21,$);
#21=IFCAXIS2PLACEMENT3D(#22,$,$);
#22=IFCCARTESIANPOINT((0.,0.,0.));
#23=IFCLOCALPLACEMENT($,#21);
#100=IFCCARTESIANPOINT((0.,0.,0.));
#101=IFCCARTESIANPOINT((2.,0.,0.));
#102=IFCCARTESIANPOINT((2.,1.,0.));
#103=IFCCARTESIANPOINT((0.,1.,0.));
#110=IFCVERTEXPOINT(#100);
#111=IFCVERTEXPOINT(#101);
#112=IFCVERTEXPOINT(#102);
#113=IFCVERTEXPOINT(#103);
#120=IFCTOPOLOGYREPRESENTATION(#20,'Reference','Vertex',(#110));
#121=IFCTOPOLOGYREPRESENTATION(#20,'Reference','Vertex',(#111));
#122=IFCTOPOLOGYREPRESENTATION(#20,'Reference','Vertex',(#112));
#123=IFCTOPOLOGYREPRESENTATION(#20,'Reference','Vertex',(#113));
#130=IFCPRODUCTDEFINITIONSHAPE($,$,(#120));
#131=IFCPRODUCTDEFINITIONSHAPE($,$,(#121));
#132=IFCPRODUCTDEFINITIONSHAPE($,$,(#122));
#133=IFCPRODUCTDEFINITIONSHAPE($,$,(#123));
#140=IFCBOUNDARYNODECONDITION('starr',-1.,-1.,-1.,-1.,-1.,-1.);
#141=IFCBOUNDARYNODECONDITION('Feder',0.,0.,5000.,$,$,$);
#150=IFCSTRUCTURALPOINTCONNECTION('1YvctVUKr0kugbFTf53O9L',$,'N1',$,$,#23,#130,#140);
#151=IFCSTRUCTURALPOINTCONNECTION('2YvctVUKr0kugbFTf53O9L',$,'N2',$,$,#23,#131,#141);
#152=IFCSTRUCTURALPOINTCONNECTION('3YvctVUKr0kugbFTf53O9L',$,'N3',$,$,#23,#132,#141);
#153=IFCSTRUCTURALPOINTCONNECTION('4YvctVUKr0kugbFTf53O9L',$,'N4',$,$,#23,#133,#140);
#160=IFCPOLYLOOP((#100,#101,#102,#103));
#161=IFCFACEOUTERBOUND(#160,.T.);
#162=IFCPLANE(#21);
#163=IFCFACESURFACE((#161),#162,.T.);
#164=IFCTOPOLOGYREPRESENTATION(#20,'Reference','Face',(#163));
#165=IFCPRODUCTDEFINITIONSHAPE($,$,(#164));
#166=IFCSTRUCTURALSURFACEMEMBER('5YvctVUKr0kugbFTf53O9L',$,'Platte',$,$,#23,#165,.SHELL.,0.02);
#167=IFCMATERIAL('Baustahl S235');
#168=IFCRELASSOCIATESMATERIAL('6YvctVUKr0kugbFTf53O9L',$,$,$,(#166),#167);
#170=IFCEDGE(#110,#111);
#171=IFCTOPOLOGYREPRESENTATION(#20,'Reference','Edge',(#170));
#172=IFCPRODUCTDEFINITIONSHAPE($,$,(#171));
#173=IFCSTRUCTURALCURVEMEMBER('7YvctVUKr0kugbFTf53O9L',$,'Rand',$,$,#23,#172,.RIGID_JOINED_MEMBER.);
#174=IFCRELCONNECTSSTRUCTURALMEMBER('8YvctVUKr0kugbFTf53O9L',$,$,$,#173,#150,$,$,$,$);
#175=IFCRELCONNECTSSTRUCTURALMEMBER('9YvctVUKr0kugbFTf53O9L',$,$,$,#173,#151,$,$,$,$);
#176=IFCRECTANGLEPROFILEDEF(.AREA.,'R 100/200',$,0.1,0.2);
#177=IFCSTRUCTURALSTEELPROFILEPROPERTIES('R 100/200',#176,$,$,$,$,0.02,$,$,$,$,$,$,$,$,$,$,$,$,$,$,$,$);
#178=IFCRELASSOCIATESPROFILEPROPERTIES('AYvctVUKr0kugbFTf53O9L',$,$,$,(#173),#177,$,$);
#179=IFCRELASSOCIATESMATERIAL('BYvctVUKr0kugbFTf53O9L',$,$,$,(#173),#167);
#180=IFCSTRUCTURALLOADGROUP('CYvctVUKr0kugbFTf53O9L',$,'Schnee',$,$,.LOAD_CASE.,.SNOW_S.,.SNOW.,$,$);
#181=IFCSTRUCTURALLOADPLANARFORCE('p',0.,0.,-1.5);
#182=IFCSTRUCTURALPLANARACTION('DYvctVUKr0kugbFTf53O9L',$,'p1',$,$,#23,#165,#181,.LOCAL_COORDS.,$,$,.TRUE_LENGTH.);
#183=IFCRELCONNECTSSTRUCTURALACTIVITY('EYvctVUKr0kugbFTf53O9L',$,$,$,#166,#182);
#184=IFCRELASSIGNSTOGROUP('FYvctVUKr0kugbFTf53O9L',$,$,$,(#182),$,#180);
ENDSEC;
END-ISO-10303-21;
"""

IFC_BEAM = """\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('traeger.ifc','2024-01-01T00:00:00',(''),(''),'','','');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1=IFCPROJECT('0YvctVUKr0kugbFTf53O9L',$,'Traeger',$,$,$,$,(#20),#10);
#10=IFCUNITASSIGNMENT((#11));
#11=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#20=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.0E-5,#21,$);
#21=IFCAXIS2PLACEMENT3D(#22,$,$);
#22=IFCCARTESIANPOINT((0.,0.,0.));
#23=IFCLOCALPLACEMENT($,#21);
#30=IFCCARTESIANPOINT((1000.,0.,3000.));
#31=IFCDIRECTION((1.,0.,0.));
#32=IFCDIRECTION((0.,0.,-1.));
#33=IFCAXIS2PLACEMENT3D(#30,#31,#32);
#34=IFCLOCALPLACEMENT(#23,#33);
#40=IFCISHAPEPROFILEDEF(.AREA.,'HEA 200',$,200.,190.,6.5,10.,18.);
#41=IFCEXTRUDEDAREASOLID(#40,#21,#42,4000.);
#42=IFCDIRECTION((0.,0.,1.));
#43=IFCSHAPEREPRESENTATION(#20,'Body','SweptSolid',(#41));
#44=IFCPRODUCTDEFINITIONSHAPE($,$,(#43));
#45=IFCBEAM('1YvctVUKr0kugbFTf53O9L',$,'Traeger 1',$,$,#34,#44,'T1');
#46=IFCMATERIAL('S 355 JR');
#47=IFCRELASSOCIATESMATERIAL('2YvctVUKr0kugbFTf53O9L',$,$,$,(#45),#46);
#50=IFCSLAB('3YvctVUKr0kugbFTf53O9L',$,'Decke',$,$,#23,$,$,.FLOOR.);
ENDSEC;
END-ISO-10303-21;
"""


def test_ifc2x3():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "platte.ifc")
        with open(p, "w") as f:
            f.write(IFC2X3)
        log = []
        m = import_file(p, log=log)
        expect("IFC2X3: 4 Knoten, 1 Balken + 1 shell4", m.nn == 4 and len(m.elements) == 2
               and sorted(e.typ for e in m.elements) == ["beam", "shell4"],
               f"nn={m.nn} typen={[e.typ for e in m.elements]}")
        sh = next(e for e in m.elements if e.typ == "shell4")
        expect("IFC2X3: Schalendicke 20 mm", abs(m.shells[sh.sec].t - 0.02) < 1e-12)
        expect("IFC2X3: Material aus Name 'Baustahl S235'",
               m.materials[sh.mat].grade == "S235")
        bm = next(e for e in m.elements if e.typ == "beam")
        sec = m.sections[bm.sec]
        expect("IFC2X3: Rechteckprofil ueber IfcRelAssociatesProfileProperties",
               sec.typ == "rect" and abs(sec.b - 0.1) < 1e-12 and abs(sec.h - 0.2) < 1e-12,
               sec.describe())
        fixed = [s for s in m.supports if not s.stiffness]
        springs = [s for s in m.supports if s.stiffness]
        expect("IFC2X3: -1 = starr (2 Knoten, 6 FHG)", len(fixed) == 2
               and all(sorted(s.dofs) == [0, 1, 2, 3, 4, 5] for s in fixed))
        expect("IFC2X3: Feder 5000 kN/m in Z (0 = frei)", len(springs) == 2
               and all(s.dofs == [2] and abs(s.stiffness[0] - 5e6) < 1e-6 for s in springs))
        lc = m.load_cases.get("Schnee")
        expect("IFC2X3: Lastfall Schnee (S)", lc is not None and lc.category == "S")
        expect("IFC2X3: Flaechenlast -1.5 kN/m² lokal", lc is not None
               and len(lc.face_loads) == 1 and abs(lc.face_loads[0].p + 1500.0) < 1e-9
               and lc.face_loads[0].direction is None)
        solve_ok("IFC2X3", m, "Schnee")


def test_ifc_physical_fallback():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "traeger.ifc")
        with open(p, "w") as f:
            f.write(IFC_BEAM)
        log = []
        m = import_file(p, log=log)
        expect("IFC-Bauteile: Warnung 'nur Stabachsen'", any("Stabachsen" in s for s in log))
        expect("IFC-Bauteile: IfcSlab nicht importiert protokolliert",
               any("IfcSlab" in s and "nicht importiert" in s for s in log))
        expect("IFC-Bauteile: 1 Balken aus IfcBeam", len(m.elements) == 1
               and m.elements[0].typ == "beam" and m.nn == 2)
        # Placement: Ursprung (1, 0, 3) m, lokale z-Achse = globale x -> Ende bei (5, 0, 3)
        expect("IFC-Bauteile: Achse aus Placement + Extrusion",
               np.allclose(sorted(m.nodes.tolist()), [[1, 0, 3], [5, 0, 3]]),
               str(m.nodes.tolist()))
        sec = m.sections[m.elements[0].sec]
        expect("IFC-Bauteile: Profil HEA 200 aus SweptArea", sec.typ == "I"
               and abs(sec.h - 0.19) < 1e-12 and abs(sec.b - 0.2) < 1e-12)
        expect("IFC-Bauteile: Material S355", m.materials[m.elements[0].mat].grade == "S355")
        expect("IFC-Bauteile: Stab benannt", "Traeger 1" in m.members)


# --------------------------------------------------------------------------
# SAF
# --------------------------------------------------------------------------
def saf_sheets():
    return {
        "StructuralMaterial": [
            ["Name", "Type", "Quality", "Unit mass [kg/m³]", "E modulus [MPa]",
             "Poisson coefficient", "Thermal expansion [1/K]"],
            ["S 235", "Steel", "S 235", 7850, 210000, 0.3, 1.2e-5],
        ],
        "StructuralCrossSection": [
            ["Name", "Material", "Cross-section type", "Shape", "Parameters [mm]", "Profile",
             "A [mm²]", "Iy [mm⁴]", "Iz [mm⁴]", "It [mm⁴]"],
            ["CS1", "S 235", "Manufactured", "I", "", "IPE200", 2850, 19430000, 1420000, 69800],
            ["CS2", "S 235", "Parametric", "Rectangle", "300; 200", "", 60000, 4.5e8, 2e8, 4e8],
        ],
        "StructuralPointConnection": [
            ["Name", "Coordinate X [m]", "Coordinate Y [m]", "Coordinate Z [m]"],
            ["N1", 0, 0, 0], ["N2", 0, 0, 3], ["N3", 5, 0, 3], ["N4", 5, 0, 0],
            ["N5", 0, 4, 3], ["N6", 5, 4, 3],
        ],
        "StructuralCurveMember": [
            ["Name", "Type", "Cross section", "Nodes", "Behaviour", "LCS rotation [deg]"],
            ["B1", "Column", "CS1", "N1;N2", "Standard", 0],
            ["B2", "Beam", "CS1", "N2;N3", "Standard", 0],
            ["B3", "Column", "CS2", "N4;N3", "Standard", 90],
        ],
        "StructuralSurfaceMember": [
            ["Name", "Type", "Material", "Thickness [mm]", "Nodes"],
            ["S1", "Plate", "S 235", 20, "N2;N3;N6;N5"],
        ],
        "StructuralPointSupport": [
            ["Name", "Node", "ux", "uy", "uz", "fix", "fiy", "fiz", "Stiffness X [MN/m]",
             "Stiffness Y [MN/m]", "Stiffness Z [MN/m]"],
            ["Sn1", "N1", "Rigid", "Rigid", "Rigid", "Rigid", "Rigid", "Rigid", "", "", ""],
            ["Sn2", "N4", "Rigid", "Rigid", "Flexible", "Free", "Free", "Free", "", "", 50],
            ["Sn3", "N5", "Rigid", "Rigid", "Rigid", "Free", "Free", "Free", "", "", ""],
            ["Sn4", "N6", "Rigid", "Rigid", "Rigid", "Free", "Free", "Free", "", "", ""],
        ],
        "StructuralLoadGroup": [
            ["Name", "Load group type", "Relation", "Load type"],
            ["LG1", "Permanent", "Standard", "Standard"],
            ["LG2", "Variable", "Exclusive", "Standard"],
        ],
        "StructuralLoadCase": [
            ["Name", "Action type", "Load group", "Load type", "Description"],
            ["LC1", "Permanent", "LG1", "Self weight", "Eigengewicht"],
            ["LC2", "Variable", "LG2", "Standard", "Nutzlast"],
            ["LC3", "Variable", "LG2", "Wind", "Wind"],
        ],
        "StructuralLoadCombination": [
            ["Name", "Description", "Category", "Load case", "Factor"],
            ["CO1", "GZT", "ULS", "LC1", 1.35],
            ["CO1", "GZT", "ULS", "LC2", 1.5],
            ["CO2", "GZG", "SLS", "LC1", 1.0],
        ],
        "StructuralPointAction": [
            ["Name", "Force action", "Direction", "Value [kN]", "Load case", "Point on node",
             "Coordinate system"],
            ["PF1", "In node", "X", 10, "LC3", "N2", "Global"],
        ],
        "StructuralCurveAction": [
            ["Name", "Distribution", "Direction", "Value 1 [kN/m]", "Value 2 [kN/m]",
             "Load case", "Member", "Coordinate system", "Location"],
            ["LF1", "Uniform", "Z", -5, "", "LC2", "B2", "Global", "Length"],
        ],
        "StructuralSurfaceAction": [
            ["Name", "Direction", "Value [kN/m²]", "Load case", "2D Member", "Coordinate system"],
            ["SF1", "Z", -2, "LC2", "S1", "Global"],
        ],
    }


def test_xlsx_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "rt.xlsx")
        sheets = {"Blatt 1": [["Name", "Wert", "ok"], ["a;b", 1.5, True], [], ["ü", -2, None]]}
        write_xlsx(p, sheets)
        back = read_xlsx(p)
        expect("xlsx: Blattname", list(back) == ["Blatt 1"])
        expect("xlsx: Zellen", back["Blatt 1"][0] == ["Name", "Wert", "ok"]
               and back["Blatt 1"][1] == ["a;b", 1.5, True] and back["Blatt 1"][2] == []
               and back["Blatt 1"][3][:2] == ["ü", -2.0], str(back))
        c = os.path.join(d, "t.csv")
        with open(c, "w", encoding="cp1252") as f:
            f.write("Knoten Nr.;Koordinaten X [m];Y\n1;1,5;2,25\n2;-3;\"a;b\"\n")
        rows = read_csv_table(c)
        expect("csv: Trennzeichen und Dezimalkomma", rows[1] == [1.0, 1.5, 2.25]
               and rows[2] == [2.0, -3.0, "a;b"], str(rows))


def test_saf():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "modell.xlsx")
        write_xlsx(p, saf_sheets())
        log = []
        m = import_file(p, log=log)
        expect("SAF: als SAF erkannt", any("SAF" in s for s in log))
        expect("SAF: 6 Knoten", m.nn == 6, f"nn={m.nn}")
        beams = [e for e in m.elements if e.typ == "beam"]
        shells = [e for e in m.elements if e.typ == "shell4"]
        expect("SAF: 3 Staebe + 1 shell4", len(beams) == 3 and len(shells) == 1)
        expect("SAF: Stabnamen", set(m.members) == {"B1", "B2", "B3"})
        expect("SAF: Profil IPE200 aus Datenbank", m.sections["CS1"].typ == "I"
               and abs(m.sections["CS1"].h - 0.2) < 1e-9)
        expect("SAF: parametrischer Rechteckquerschnitt", m.sections["CS2"].typ == "rect"
               and abs(m.sections["CS2"].h - 0.3) < 1e-9 and abs(m.sections["CS2"].b - 0.2) < 1e-9)
        expect("SAF: Material S235", m.materials["S 235"].grade == "S235"
               and abs(m.materials["S 235"].E - 210e9) < 1)
        expect("SAF: LCS-Drehung 90° -> roll", abs(abs(beams[2].roll) - np.pi / 2) < 1e-9)
        expect("SAF: Schalendicke 20 mm", abs(m.shells[shells[0].sec].t - 0.02) < 1e-12)
        fixed = [s for s in m.supports if not s.stiffness]
        springs = [s for s in m.supports if s.stiffness]
        expect("SAF: Lager (4 starr, 1 Feder 50 MN/m)", len(fixed) == 4 and len(springs) == 1
               and springs[0].dofs == [2] and abs(springs[0].stiffness[0] - 50e6) < 1e-3)
        expect("SAF: Lastfaelle LC1..LC3", set(m.load_cases) == {"LC1", "LC2", "LC3"})
        expect("SAF: Kategorien G/Q/W", (m.load_cases["LC1"].category, m.load_cases["LC2"].category,
                                         m.load_cases["LC3"].category) == ("G", "Q", "W"))
        expect("SAF: Eigengewicht", abs(m.load_cases["LC1"].gravity[2] + 9.81) < 1e-9)
        expect("SAF: exklusive Gruppe", m.load_cases["LC2"].exclusive_group == "LG2"
               and m.load_cases["LC3"].exclusive_group == "LG2")
        expect("SAF: Kombinationen", m.combinations["CO1"].factors == {"LC1": 1.35, "LC2": 1.5}
               and m.combinations["CO1"].typ == "ULS" and m.combinations["CO2"].typ == "SLS_CH")
        expect("SAF: Knotenlast 10 kN in X", len(m.load_cases["LC3"].nodal_loads) == 1
               and m.load_cases["LC3"].nodal_loads[0].F[0] == 10000.0)
        bl = m.load_cases["LC2"].beam_loads
        expect("SAF: Streckenlast -5 kN/m auf B2", len(bl) == 1 and bl[0].q == [0.0, 0.0, -5000.0]
               and bl[0].elem == m.members["B2"].elements[0])
        fl = m.load_cases["LC2"].face_loads
        expect("SAF: Flaechenlast -2 kN/m²", len(fl) == 1 and fl[0].p == -2000.0
               and fl[0].direction == [0.0, 0.0, 1.0])
        solve_ok("SAF", m, "LC2")
        solve_ok("SAF (LC3)", m, "LC3")


# --------------------------------------------------------------------------
# RFEM-Tabellen
# --------------------------------------------------------------------------
def rfem_sheets():
    return {
        "1.1 Knoten": [
            ["Knoten", "Bezugs-", "Koordinaten-", "Knotenkoordinaten", None, None, "Kommentar"],
            ["Nr.", "knoten", "system", "X [m]", "Y [m]", "Z [m]", None],
            [1, None, "Kartesisch", 0.0, 0.0, 0.0, None],
            [2, None, "Kartesisch", 0.0, 0.0, -4.0, None],
            [3, None, "Kartesisch", 6.0, 0.0, -4.0, None],
            [4, None, "Kartesisch", 6.0, 0.0, 0.0, None],
        ],
        "1.5 Querschnitte": [
            ["Querschnitt", "Querschnittsbezeichnung", "Material", "Querschnittswerte", None, None, None],
            ["Nr.", None, "Nr.", "A [cm²]", "Iy [cm⁴]", "Iz [cm⁴]", "It [cm⁴]"],
            [1, "IPE 200", 1, 28.5, 1943.0, 142.0, 6.98],
            [2, "HE A 200", 1, 53.8, 3692.0, 1336.0, 21.0],
        ],
        "1.7 Stäbe": [
            ["Stab", "Stabtyp", "Knoten Nr.", None, "Drehung", "Querschnitt Nr.", None],
            ["Nr.", None, "Anfang", "Ende", "β [°]", "Anfang", "Ende"],
            [1, "Balkenstab", 1, 2, 0.0, 2, 2],
            [2, "Balkenstab", 2, 3, 0.0, 1, 1],
            [3, "Balkenstab", 4, 3, 0.0, 2, 2],
        ],
        "1.8 Knotenlager": [
            ["Lager", "Knoten", "Lagerdrehung", "Stützung bzw. Feder [kN/m]", None, None,
             "Einspannung bzw. Feder [kNm/rad]", None, None],
            ["Nr.", "Nr.", "β [°]", "uX'", "uY'", "uZ'", "φX'", "φY'", "φZ'"],
            [1, "1,4", 0.0, "Ja", "Ja", "Ja", "Ja", "Ja", "Ja"],
            [2, "3", 0.0, "Nein", "Ja", 5000.0, "Nein", "Nein", "Nein"],
        ],
        "3.1 Knotenlasten": [
            ["Knotenlast", "Bezug", "An Knoten", "Lastart", "Kraft [kN]", None, None,
             "Moment [kNm]", None, None],
            ["Nr.", None, "Nr.", None, "Fx", "Fy", "Fz", "Mx", "My", "Mz"],
            ["LF2", "Nutzlast", None, None, None, None, None, None, None, None],
            [1, "Knoten", "2", "Kraft", 10.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [2, "Knoten", "2,3", "Kraft", 0.0, 0.0, 5.0, 0.0, 0.0, 0.0],
        ],
    }


def _check_rfem(name, m):
    expect(f"{name}: 4 Knoten, 3 Balken", m.nn == 4 and len(m.elements) == 3
           and all(e.typ == "beam" for e in m.elements), f"nn={m.nn} ne={len(m.elements)}")
    expect(f"{name}: Koordinaten (Z nach unten unveraendert)",
           abs(m.nodes[:, 2].min() + 4.0) < 1e-9 and abs(m.nodes[:, 0].max() - 6.0) < 1e-9)
    expect(f"{name}: Querschnitte IPE 200 / HEA 200", m.elements[1].sec == "IPE 200"
           and m.elements[0].sec == "HE A 200" and m.sections["HE A 200"].typ == "I"
           and abs(m.sections["HE A 200"].h - 0.190) < 1e-9)
    expect(f"{name}: Staebe", len(m.members) == 3)
    fixed = [s for s in m.supports if not s.stiffness]
    springs = [s for s in m.supports if s.stiffness]
    expect(f"{name}: Lager 1,4 starr + Knoten 3 (uY starr, uZ Feder 5000 kN/m)",
           len(fixed) == 3 and len(springs) == 1 and springs[0].dofs == [2]
           and abs(springs[0].stiffness[0] - 5e6) < 1e-6
           and sorted(s.node for s in fixed) == [0, 2, 3])
    lc = m.load_cases.get("LF2")
    expect(f"{name}: Lastfall LF2 aus Blocktitel", lc is not None and len(lc.nodal_loads) == 3,
           str(list(m.load_cases)))
    expect(f"{name}: Knotenlast 10 kN -> 10000 N", lc is not None
           and lc.nodal_loads[0].F[0] == 10000.0 and lc.nodal_loads[0].node == 1
           and lc.nodal_loads[2].F[2] == 5000.0)
    solve_ok(name, m, "LF2")


def test_rfem_xlsx():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "rahmen.xlsx")
        write_xlsx(p, rfem_sheets())
        log = []
        m = import_file(p, log=log)
        expect("RFEM xlsx: als Tabellenexport erkannt", any("RFEM" in s for s in log))
        _check_rfem("RFEM xlsx", m)


def test_rfem_csv_folder():
    with tempfile.TemporaryDirectory() as d:
        folder = os.path.join(d, "export")
        os.mkdir(folder)
        for name, rows in rfem_sheets().items():
            with open(os.path.join(folder, name + ".csv"), "w", encoding="utf-8-sig") as f:
                for r in rows:
                    cells = []
                    for c in r:
                        if c is None:
                            cells.append("")
                        elif isinstance(c, float):
                            cells.append(f"{c:.3f}".replace(".", ","))
                        else:
                            cells.append(str(c))
                    f.write(";".join(cells) + "\n")
        m = import_file(folder)
        _check_rfem("RFEM CSV-Ordner", m)


# --------------------------------------------------------------------------
# Dispatcher / Hilfen
# --------------------------------------------------------------------------
def test_dispatcher():
    expect("SUPPORTED enthaelt Kernformate",
           all(e in SUPPORTED for e in (".json", ".dxf", ".ifc", ".xlsx", ".inp", ".bdf", ".step")))
    flt = file_filter()
    expect("file_filter: Qt-Filter", "*.dxf" in flt and ";;" in flt and "*.ifc" in flt)
    for ext in PROPRIETARY:
        txt = explain_format("modell" + ext)
        expect(f"explain_format {ext}", "Export" in txt and ("IFC" in txt or "DXF" in txt))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "modell.rf6")
        open(p, "wb").close()
        try:
            import_file(p)
            expect("ImportError fuer .rf6", False)
        except ImportError as ex:
            expect("ImportError fuer .rf6 mit Exportweg", "SAF" in str(ex) and "IFC" in str(ex))
        # JSON-Roundtrip und Anhaengen an ein bestehendes Modell
        m = Model("A")
        from statik3d.model import Material, Section
        m.add_material(Material("S235"))
        m.add_section(Section.rectangle("R", 0.1, 0.2))
        m.add_node(0, 0, 0); m.add_node(1, 0, 0)
        m.add_element("beam", [0, 1], "S235", "R")
        m.fix(0, "all")
        m.load_node(1, Fz=-1.0)
        pj = os.path.join(d, "a.json")
        m.save(pj)
        m2 = import_file(pj)
        expect("JSON: Modell geladen", m2.nn == 2 and len(m2.elements) == 1
               and m2.meta.get("quelle") == pj)
        write_dxf(os.path.join(d, "r.dxf"))
        m3 = import_file(os.path.join(d, "r.dxf"), model=m2)
        expect("DXF an bestehendes Modell angehaengt (gemeinsamer Knoten (0,0,0))",
               m3 is m2 and m3.nn == 2 + 7 - 1 and len(m3.elements) == 6, f"nn={m3.nn}")
        expect("unbekannte Endung -> ImportError",
               explain_format("x.abc").startswith("Dateiendung"))


# --------------------------------------------------------------------------
TESTS = [test_xlsx_roundtrip, test_dxf, test_abaqus_inp, test_nastran_bdf, test_ifc_parser,
         test_ifc, test_ifc2x3, test_ifc_physical_fallback, test_saf, test_rfem_xlsx,
         test_rfem_csv_folder, test_dispatcher]


def main() -> int:
    print("=" * 92)
    print("STATIK3D - Importer-Tests")
    print("=" * 92)
    failures = 0
    for t in TESTS:
        print(f"\n-- {t.__name__} " + "-" * (80 - len(t.__name__)))
        try:
            t()
        except AssertionError as ex:
            failures += 1
            print(f"FAIL {t.__name__}: {ex}")
        except Exception as ex:               # Absturz eines Tests
            failures += 1
            RESULTS.append((t.__name__, False, repr(ex)))
            import traceback
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {ex!r}")
    nok = sum(1 for r in RESULTS if r[1])
    print("\n" + "=" * 92)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden, "
          f"{len(TESTS) - failures}/{len(TESTS)} Tests ohne Fehler")
    print("=" * 92)
    return 0 if failures == 0 and nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
