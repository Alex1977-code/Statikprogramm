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


BDF_KEIL_ALS_HEXA = textwrap.dedent("""    $ Keil als entarteter CHEXA (G3 = G4, G7 = G8) - so schreiben ihn
    $ Nastran-Netze; dazu ein zweiter, dessen Doppelknoten erst durch das
    $ Zusammenfuehren gleich liegender GRIDs entsteht
    BEGIN BULK
    GRID,1,,0.0,0.0,0.0
    GRID,2,,1.0,0.0,0.0
    GRID,3,,0.0,1.0,0.0
    GRID,4,,0.0,0.0,1.0
    GRID,5,,1.0,0.0,1.0
    GRID,6,,0.0,1.0,1.0
    GRID,13,,0.0,1.0,0.0
    GRID,16,,0.0,1.0,1.0
    GRID,21,,1.0,0.0,0.0
    GRID,22,,1.0,1.0,0.0
    GRID,23,,0.0,1.0,0.0
    GRID,25,,1.0,0.0,1.0
    GRID,26,,1.0,1.0,1.0
    GRID,27,,0.0,1.0,1.0
    CHEXA,1,1,1,2,3,3,4,5
    ,6,6
    CHEXA,2,1,21,22,23,13,25,26
    ,27,16
    PSOLID,1,1
    MAT1,1,2.1+11,,0.3,7850.0
    ENDDATA
    """)


def test_entarteter_sechsflaechner_beim_import():
    """Ein zum Keil entarteter Sechsflaechner wird schon beim Import
    umgewandelt und im Protokoll genannt (23.09.2026).

    Bis dahin stand er als hex8 mit doppelten Knoten im Modell; die
    Modellpruefung hielt ihn fuer ein Element ohne Ausdehnung, und die
    Rechnung liess ihn weg (am Kragarm aus solchen Elementen: Durchbiegung
    0,0). Seit element/entartete-elemente wandelt die Rechnung ihn um - der
    Import soll es aber schon sagen, denn dort entstehen solche Elemente:
    in der Datei (Nastran/Abaqus) oder beim Zusammenfuehren gleich liegender
    Knoten.
    """
    from statik3d.elements import solid as SO
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "keil.bdf")
        with open(p, "w") as f:
            f.write(BDF_KEIL_ALS_HEXA)
        log = []
        m = import_file(p, log=log)
    typen = [e.typ for e in m.elements]
    expect("Keil aus der Datei (G3 = G4) ist nach dem Import ein pent6",
           len(typen) == 2 and typen[0] == "pent6", str(typen))
    expect("Keil, der erst durch zusammengefuehrte Knoten entsteht, ebenso",
           len(typen) == 2 and typen[1] == "pent6", str(typen))
    vol = [abs(SO.solid_volume(e.typ, m.nodes[[int(x) for x in e.nodes]])) for e in m.elements]
    expect("beide behalten ihr Volumen (0,5 m³)",
           all(abs(v - 0.5) < 1e-12 for v in vol), str(vol))
    zeile = [z for z in log if "umgewandelt" in z]
    expect("das Importprotokoll nennt die Umwandlung mit Anzahl",
           len(zeile) == 1 and "hex8→pent6: 2" in zeile[0], str(zeile))
    expect("… und was sie an Genauigkeit kostet",
           bool(zeile) and "Keils" in zeile[0], zeile[0][:120] if zeile else "–")


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
def test_dicke_wird_nicht_still_geerbt():
    """Eine Schale ohne eigene Dicke erbt - aber sie sagt es.

    `_common.ensure_shell_prop` gibt ohne Namen und ohne Dicke die **zuerst
    gelesene** Dicke zurueck. Bis zum 22.09.2026 geschah das wortlos: eine
    Flaeche, deren Dickenangabe in der Datei fehlte, trug damit eine Dicke,
    die nirgends steht - gemessen 20 mm statt der 10 mm des Rueckfalls, also
    Biegesteifigkeit (20/10)^3 = 8fach und die Spannung aus Moment um den
    Faktor 4 zu klein. Welcher Wert es wird, haengt allein daran, welche
    Flaeche zuerst in der Datei stand.

    Gemeldet wird **einmal je Protokoll** und nicht je Aufruf: die Funktion
    wird auch je Element gerufen (InfoCAD-Leser), eine Zeile je Aufruf waere
    eine Flut.
    """
    from statik3d.importers import _common as C
    from statik3d.model import ShellProp

    m = Model("erbe")
    m.add_shell_prop(ShellProp("t20", 0.020))
    log = []
    name = C.ensure_shell_prop(m, None, None, log)
    expect("die geerbte Dicke ist die zuerst gelesene",
           name == "t20" and abs(m.shells[name].t - 0.020) < 1e-12,
           f"{name} = {m.shells[name].t * 1e3:g} mm")
    zeilen = [z for z in log if "erben" in z]
    expect("und das Erben steht im Protokoll", len(zeilen) == 1,
           zeilen[0] if zeilen else "keine Zeile")
    expect("die Zeile nennt den Wert, der wirklich angesetzt wird",
           "20 mm" in zeilen[0], zeilen[0] if zeilen else "-")

    # Zehn weitere Schalen duerfen das Protokoll nicht fluten
    for _ in range(10):
        C.ensure_shell_prop(m, None, None, log)
    expect("auch nach elf Schalen steht die Meldung genau einmal",
           len([z for z in log if "erben" in z]) == 1,
           f"{len([z for z in log if 'erben' in z])} Zeilen")

    # Gegenprobe: ohne vorhandene Dicke greift der 10-mm-Rueckfall mit
    # seiner eigenen, schon vorhandenen Warnung
    m2 = Model("leer")
    log2 = []
    n2 = C.ensure_shell_prop(m2, None, None, log2)
    expect("ohne jede vorhandene Dicke gilt der 10-mm-Rueckfall",
           abs(m2.shells[n2].t - 0.010) < 1e-12,
           f"{m2.shells[n2].t * 1e3:g} mm")
    expect("und auch der wird genannt",
           any("10 mm angenommen" in z for z in log2),
           next((z for z in log2), "keine Zeile"))


# --------------------------------------------------------------------------
# JSON-Modell an ein vorhandenes anhaengen (Befund SV11, 22.09.2026)
# --------------------------------------------------------------------------
#: Schluessel von Model.to_dict(), die keine Objektliste sind: Einstellungen
#: und Kopfangaben. Sie gehoeren dem Ziel und werden nicht gezaehlt.
_KEINE_OBJEKTLISTE = {"format", "name", "meta", "active_case", "netz", "design",
                      "plastizitaet", "knotendilatation", "randspannung", "bemassung_einstellung",
                      "werteskala", "bericht_rahmen", "einheiten", "nodes", "elements"}

#: Die Lastlisten eines Lastfalls (LoadCase.to_dict ohne Eigenschaften)
_LASTLISTEN = ("nodal_loads", "beam_loads", "face_loads", "temp_loads", "geometrielasten",
               "linienlasten", "zwangsverformungen", "vorspannungen", "uebermasse")


def _anhaengen_ziel() -> Model:
    """Ein Ziel mit eigenen Objekten, deren Namen die Quelle wieder benutzt:
    Linien L1-L4, Flaeche F1, Stab S1, Fuge KB1, Situation Montage,
    Kombination CO1, Ermuedungslast E1 und ein Werkstoff S235 mit anderen
    Werten. Der Knoten (0, 0, 0) liegt in beiden Modellen - dort schliesst
    das angehaengte Teil an."""
    from statik3d.model import Material, Section, ShellProp, Situation
    z = Model("Ziel")
    z.add_material(Material("S235"))
    z.add_section(Section.rectangle("R", 0.1, 0.2))
    z.add_shell_prop(ShellProp("t8", 0.008))
    for p in [(0, 0, 0), (-1, 0, 0), (-1, -1, 0), (0, -1, 0)]:
        z.add_node(*p)
    eb = z.add_element("beam", [0, 1], "S235", "R")
    es = z.add_element("shell4", [0, 1, 2, 3], "S235", "t8")
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)], start=1):
        z.add_line(f"L{i}", [a, b])
    z.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke="t8", material="S235", elemente=[es])
    z.add_member("S1", [eb])
    z.fix(1, "all")
    z.add_kontaktbedingung("KB1", flaechennamen=["F1"])
    z.situationen["Montage"] = Situation("Montage", deaktiviert=[eb])
    z.load_node(1, Fz=-1.0, case="LF1")
    z.load_cases["LF1"].gravity = [0.0, 0.0, -9.81]
    z.add_combination("CO1", {"LF1": 1.0})
    z.add_fatigue_load("E1", "LF1")
    return z


def _anhaengen_quelle() -> Model:
    """Je ein Objekt jeder Art, die Model.to_dict() kennt."""
    from statik3d.model import (Material, Section, ShellProp, Volumenkoerper, Berichtseintrag,
                                Kopplung, Subsystem, Layer, Unterlage, Situation)
    from statik3d.bridges.positions import Stellung
    from statik3d.wasserdruck import Wasserdruck
    from statik3d.wind import Wind
    from statik3d.schwingung import Schwingungsnachweis
    from statik3d.schweissnaehte import Schweissnaht
    from statik3d.bemassung import Bemassung
    m = Model("Quelle")
    m.add_material(Material("S235", E=200e9))          # Name wie im Ziel, andere Werte
    m.add_material(Material("S355", fy=355e6))
    m.add_section(Section.rectangle("R", 0.1, 0.2))    # genau wie im Ziel
    m.add_shell_prop(ShellProp("t12", 0.012))
    m.add_feder_prop("FE1", k=[1e6, 1e6, 1e6])
    m.add_grenzschicht_prop("GS1")
    for p in [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0),
              (3, 0, 0), (4, 0, 0), (4, 1, 0), (3, 1, 0),
              (3, 0, 1), (4, 0, 1), (4, 1, 1), (3, 1, 1),
              (5, 0, 0), (6, 0, 0)]:
        m.add_node(*p)
    eb = m.add_element("beam", [0, 1], "S355", "R")
    es = m.add_element("shell4", [0, 1, 2, 3], "S355", "t12")
    eh = m.add_element("hex8", list(range(4, 12)), "S235")
    m.add_element("feder", [12, 13], "S355", "FE1")
    et = m.add_element("truss", [1, 4], "S355", "R", nur="zug")
    m.support(0, "pinned", name="A1", uz=dict(failure="zug"))
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)], start=1):
        m.add_line(f"L{i}", [a, b])
    m.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke="t12", material="S355",
                  elemente=[es], ecken=[0, 1, 2, 3], integrierte_knoten=[2],
                  integrierte_linien=["L3"], gelenklinien=["L4"], randseiten=[[eh, 0]])
    m.koerper["K1"] = Volumenkoerper("K1", flaechen=["F1"], material="S235", elemente=[eh])
    ls = m.add_line_support([0, 1], name="LL1", uz=dict(typ="rigid"))
    ls.line, ls.linien = "L1", ["L1"]
    ss = m.add_surface_support(elements=[es], name="FL1", nodes=[0, 1, 2, 3],
                               areas=[0.5] * 4, uz=dict(typ="spring", stiffness=1e7))
    ss.flaechen, ss.lokal = ["F1"], True
    ss.gruppen = [[2, 1, [0, 1, 2, 3], [0.5] * 4]]
    m.add_hinge("G1", end=1, phiy="free")
    m.apply_hinge(eb, "G1")
    m.add_member("S1", [eb], beta_y=0.7)
    m.situationen["Montage"] = Situation("Montage", deaktiviert=[et])
    m.add_kontaktbedingung("KB1", flaechennamen=["F1"], koerpernamen=["K1"],
                           gegenflaechen=["F1"], gegenkoerper=["K1"])
    # Lastfall LF1 gibt es auch im Ziel, LF-Q nur hier - mit allen Eigenschaften
    m.load_node(1, Fz=-1e3, case="LF1")
    m.load_beam(eb, qz=-1e3, case="LF1", a=0.2, b=0.8)
    m.load_face(es, 1e3, case="LF1")
    m.load_temp(eb, 10.0, case="LF1")
    m.add_geometrielast("F1", 2e3, case="LF1")
    m.add_linienlast("S1", [0.0, 0.0, -2e3], case="LF1")
    m.add_linienlast("L1", [0.0, 0.0, -1e3], art="linie", case="LF1")
    m.add_zwangsverformung(0, [2], [-0.001], case="LF1")
    m.add_vorspannung("S1", 1e4, case="LF1")
    m.add_uebermass("KB1", 1e-5, case="LF1")
    m.load_cases["LF1"].gravity = [0.0, 0.0, -9.81]
    m.add_load_case("LF-Q", "Q", "Nutzlast", activate=False, psi=[0.7, 0.5, 0.3],
                    exclusive_group="A", situation="Montage", theorie="II", nummer=7,
                    grundlast=True, gamma_sup=1.4, gamma_inf=0.0)
    m.load_node(2, Fx=500.0, case="LF-Q")
    m.add_combination("CO1", {"LF1": 1.35, "LF-Q": 1.5}).situation = "Montage"
    m.add_fatigue_load("E1", "LF-Q")
    m.add_joint("J1", "kopfplatte", eb, ermuedung=["E1"])
    m.add_verformungsgrenze("VG1", "stab", stab="S1")
    m.add_verformungsgrenze("VG2", "knoten", knoten=[1])
    m.add_beulfeld("BF1", [es])
    m.add_volumenbereich("VB1", [eh])
    m.add_lasteinleitung("LE1", 1, stab="S1")
    m.bericht.append(Berichtseintrag(name="B1", art="text", text="Notiz"))
    m.add_contact_support(4)
    m.add_gap_element(5, 9, group="KB1")
    m.kopplungen.append(Kopplung(6, 10, [[1.0, 0.0, 0.0]], [1e9], gruppe="KB1"))
    cp = m.add_contact_pair("KB1", [8, 9], master_elements=[eh])
    cp.knotenflaechen, cp.rand_knoten, cp.gegenkoerper = {8: 0.1}, [9], ["K1"]
    m.getrennte_knoten = {"KB1": [[8, 9]]}
    m.kontakt_ausnahmen = [["K1", "K1"]]
    m.importhinweise = [{"art": "hinweis", "text": "Probe", "objekte": ["K1"]}]
    m.add_punktmasse(3, 100.0)
    m.add_daempfer(12, -1, c=[10.0])
    m.add_starrkoerper(4, [5, 6])
    m.subsysteme["SU1"] = Subsystem("SU1", elemente=[eb], beruehrung=[es], knoten=[1],
                                    linien=["L1"], staebe=["S1"], flaechen=["F1"],
                                    koerper=["K1"], lager=[0], linienlager=[0],
                                    flaechenlager=[0], kontakte=["KB1"])
    m.layer["LY1"] = Layer("LY1", knoten=[1], elemente=[eb], staebe=["S1"], linien=["L1"],
                           flaechen=["F1"], koerper=["K1"])
    m.unterlagen["U1"] = Unterlage("U1", art="skizze")
    m.stellungen = [Stellung("ST1")]
    m.wasserdruecke["WD1"] = Wasserdruck("WD1", situation="Montage", lastfall="LF-Q",
                                         flaechen=["F1"], koerper=["K1"], dichtung=["L1"],
                                         ow_flaeche="F1")
    m.winde["W1"] = Wind("W1", situation="Montage", lastfall="LF-Q", flaechen=["F1"],
                         staebe=["S1"])
    m.schwingungen["SW1"] = Schwingungsnachweis("SW1", wasserdruck="WD1")
    m.schweissnaehte["N1"] = Schweissnaht("N1", staebe=["S1"], linien=["L1"], flaechen=["F1"])
    m.bemassungen["M1"] = Bemassung("M1", punkte=[[0, 0, 0], [2, 0, 0]])
    m.netz.verfeinerungen = [{"art": "flaeche", "name": "F1", "h": 0.05}]
    m.netz.koerper_h = {"K1": 0.1}
    m.netz.feldpunkte = [[0.0, 0.0, 0.0, 0.05]]
    return m


def _offene_verweise(m: Model) -> list:
    """Namensverweise, die im Modell ins Leere zeigen - je einer eine Zeile."""
    out = []

    def pruefe(wo, namen, vorrat):
        for n in namen or []:
            if n and n not in vorrat:
                out.append(f"{wo} -> {n}")

    fugen = set(m.kontaktbedingungen) | {c.name for c in m.contact_pairs}
    for f in m.flaechen.values():
        pruefe(f"Flaeche {f.name}", list(f.linien) + list(f.gelenklinien)
               + list(f.integrierte_linien) + [x for o in f.oeffnungen for x in o], m.lines)
        pruefe(f"Flaeche {f.name} Dicke", [f.dicke], m.shells)
        pruefe(f"Flaeche {f.name} Werkstoff", [f.material], m.materials)
    for k in m.koerper.values():
        pruefe(f"Koerper {k.name}", k.flaechen, m.flaechen)
        pruefe(f"Koerper {k.name} Werkstoff", [k.material], m.materials)
    for ls in m.line_supports:
        pruefe(f"Linienlager {ls.name}", [ls.line] + list(ls.linien), m.lines)
    for ss in m.surface_supports:
        pruefe(f"Flaechenlager {ss.name}", ss.flaechen, m.flaechen)
    for kb in m.kontaktbedingungen.values():
        pruefe(f"Fuge {kb.name}", list(kb.flaechennamen) + list(kb.gegenflaechen), m.flaechen)
        pruefe(f"Fuge {kb.name}", list(kb.koerpernamen) + list(kb.gegenkoerper), m.koerper)
    for lc in m.load_cases.values():
        pruefe(f"Lastfall {lc.name} Situation", [lc.situation], m.situationen)
        for g in lc.geometrielasten:
            pruefe(f"{lc.name} Geometrielast", [g.ziel],
                   m.flaechen if g.art == "flaeche" else m.koerper)
        for ll in lc.linienlasten:
            pruefe(f"{lc.name} Linienlast", [ll.ziel], m.members if ll.art == "stab" else m.lines)
        for v in lc.vorspannungen:
            pruefe(f"{lc.name} Vorspannung", [v.ziel], m.members if v.art == "stab" else m.koerper)
        pruefe(f"{lc.name} Uebermass", [u.ziel for u in lc.uebermasse], fugen)
    for c in m.combinations.values():
        pruefe(f"Kombination {c.name}", list(c.factors), m.load_cases)
        pruefe(f"Kombination {c.name} Situation", [c.situation], m.situationen)
    for f in m.fatigue_loads.values():
        # ein Zustand darf ein Lastfall oder eine Kombination sein (Model.check)
        pruefe(f"Ermuedung {f.name}", [f.case_max, f.case_min] + list(f.folge),
               set(m.load_cases) | set(m.combinations))
    koerper_gruppen = {n: sorted({m.elements[e].group for e in k.elemente})
                       for n, k in m.koerper.items() if k.elemente}
    for n, gr in koerper_gruppen.items():
        # die Gruppe eines Koerperelements nennt den Koerper (fugen.py sucht so)
        if any(g in m.koerper and g != n for g in gr):
            out.append(f"Koerper {n}: Elemente der Gruppe {gr}")
    for j in m.joints.values():
        pruefe(f"Anschluss {j.name}", j.ermuedung, m.fatigue_loads)
    for v in m.verformungsgrenzen.values():
        pruefe(f"Verformungsgrenze {v.name}", [v.stab], m.members)
    for le in m.lasteinleitungen.values():
        pruefe(f"Lasteinleitung {le.name}", [le.stab], m.members)
    for cp in m.contact_pairs:
        pruefe(f"Kontaktpaar {cp.name}", cp.gegenkoerper, m.koerper)
    for g in m.gap_elements:
        if g.group != "default":
            pruefe("Spaltelement", [g.group], fugen)
    for k in m.kopplungen:
        pruefe("Kopplung", [k.gruppe], fugen)
    pruefe("getrennte Knoten", list(m.getrennte_knoten), fugen)
    pruefe("Kontaktausnahme", [x for p in m.kontakt_ausnahmen for x in p], m.koerper)
    for s in m.subsysteme.values():
        pruefe(f"Subsystem {s.name}", s.linien, m.lines)
        pruefe(f"Subsystem {s.name}", s.staebe, m.members)
        pruefe(f"Subsystem {s.name}", s.flaechen, m.flaechen)
        pruefe(f"Subsystem {s.name}", s.koerper, m.koerper)
        pruefe(f"Subsystem {s.name}", s.kontakte, fugen)
    for ly in m.layer.values():
        pruefe(f"Layer {ly.name}", ly.linien, m.lines)
        pruefe(f"Layer {ly.name}", ly.staebe, m.members)
        pruefe(f"Layer {ly.name}", ly.flaechen, m.flaechen)
        pruefe(f"Layer {ly.name}", ly.koerper, m.koerper)
    for w in m.wasserdruecke.values():
        pruefe(f"Wasserdruck {w.name}", list(w.flaechen) + [w.ow_flaeche, w.uw_flaeche],
               m.flaechen)
        pruefe(f"Wasserdruck {w.name}", w.koerper, m.koerper)
        pruefe(f"Wasserdruck {w.name}", w.dichtung, m.lines)
        pruefe(f"Wasserdruck {w.name}", [w.situation], m.situationen)
    for w in m.winde.values():
        pruefe(f"Wind {w.name}", list(w.flaechen) + list(w.freie_waende) + list(w.schilder),
               m.flaechen)
        pruefe(f"Wind {w.name}", w.staebe, m.members)
        pruefe(f"Wind {w.name}", [w.situation], m.situationen)
    for s in m.schwingungen.values():
        pruefe(f"Schwingung {s.name}", [s.wasserdruck], m.wasserdruecke)
    for n in m.schweissnaehte.values():
        pruefe(f"Naht {n.name}", n.staebe, m.members)
        pruefe(f"Naht {n.name}", n.linien, m.lines)
        pruefe(f"Naht {n.name}", n.flaechen, m.flaechen)
    for v in m.netz.verfeinerungen:
        art = v.get("art")
        if art in ("flaeche", "linie", "koerper"):
            pruefe("Netzverfeinerung", [v.get("name")],
                   {"flaeche": m.flaechen, "linie": m.lines, "koerper": m.koerper}[art])
    pruefe("Kantenlaenge je Koerper", list(m.netz.koerper_h), m.koerper)
    return out


def _anzahl(m: Model, key: str) -> int:
    v = getattr(m, key)
    return len(v) if v is not None else 0


def test_json_anhaengen_vollstaendig():
    """Ein angehaengtes JSON-Modell kommt ganz an.

    Bis zum 22.09.2026 uebertrug ``_append_model`` nur Werkstoffe,
    Querschnitte, Dicken, Knoten, Elemente, Knotenlager, vier Lastarten, das
    Eigengewicht und die Staebe. Alles andere blieb liegen - Linien- und
    Flaechenlager, Kombinationen, Ermuedungslasten, Flaechen, Koerper,
    Kontakte, die Objektlasten und die Eigenschaften neuer Lastfaelle -, und
    das Protokoll meldete nur Knoten- und Elementzahl (Befund SV11).

    Geprueft wird je Liste: nachher = vorher + Quelle. Dazu zeigt kein
    Namensverweis ins Leere, und die umbenannten Objekte der Quelle tragen
    ihre eigenen Knoten und Elemente, nicht die gleichnamigen des Ziels.
    """
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "quelle.json")
        _anhaengen_quelle().save(p)
        quelle = Model.load(p)                 # so, wie sie beim Anhaengen gelesen wird
        ziel = _anhaengen_ziel()
        vorher = {k: _anzahl(ziel, k) for k in quelle.to_dict()
                  if k not in _KEINE_OBJEKTLISTE}
        lasten_vorher = {(n, k): len(getattr(lc, k)) for n, lc in ziel.load_cases.items()
                         for k in _LASTLISTEN}
        ne0, nn0 = len(ziel.elements), ziel.nn
        log = []
        ziel = import_file(p, model=ziel, log=log)

    # -- Anzahl je Liste ---------------------------------------------------
    # Ausnahmen mit Grund: der Querschnitt R ist in beiden gleich und wird
    # wiederverwendet; Lastfaelle gleichen Namens werden zusammengelegt;
    # Stellungen und Berichtseintraege werden nicht uebertragen, sondern
    # gemeldet (Pruefung weiter unten).
    erwartet = {k: vorher[k] + _anzahl(quelle, k) for k in vorher}
    erwartet["sections"] = vorher["sections"]
    erwartet["load_cases"] = len(set(quelle.load_cases) | {"LF1"})
    erwartet["stellungen"] = vorher["stellungen"]
    erwartet["bericht"] = vorher["bericht"]
    fehlt = [f"{k}: {_anzahl(ziel, k)} statt {erwartet[k]}" for k in sorted(erwartet)
             if _anzahl(ziel, k) != erwartet[k]]
    expect("Anhaengen: jede Liste der Quelle kommt an (nachher = vorher + Quelle)",
           not fehlt, "; ".join(fehlt) or f"{len(erwartet)} Listen")
    fehlt = []
    for n, lc in quelle.load_cases.items():
        for k in _LASTLISTEN:
            soll = lasten_vorher.get((n, k), 0) + len(getattr(lc, k))
            ist = len(getattr(ziel.load_cases[n], k))
            if ist != soll:
                fehlt.append(f"{n}.{k}: {ist} statt {soll}")
    expect("Anhaengen: jede Lastart jedes Lastfalls kommt an", not fehlt,
           "; ".join(fehlt) or "alle Lastarten")
    expect("Anhaengen: Elemente vollstaendig, Anschlussknoten (0,0,0) zusammengefuehrt",
           len(ziel.elements) == ne0 + len(quelle.elements) and ziel.nn == nn0 + quelle.nn - 1,
           f"{len(ziel.elements)} Elemente, {ziel.nn} Knoten")

    # -- Eigenschaften des neuen Lastfalls ---------------------------------
    lq = ziel.load_cases["LF-Q"]
    ist = (lq.category, lq.psi, lq.exclusive_group, lq.theorie, lq.nummer, lq.grundlast,
           lq.gamma_sup, lq.gamma_inf)
    soll = ("Q", [0.7, 0.5, 0.3], "A", "II", 7, True, 1.4, 0.0)
    expect("Anhaengen: neuer Lastfall behaelt psi, Gruppe, Theorie, Nummer, Grundlast, gamma",
           ist == soll, f"{ist}")
    expect("Anhaengen: Situation des Lastfalls folgt der umbenannten Situation",
           lq.situation == "Montage_2" and ziel.situationen["Montage_2"].deaktiviert
           == [ne0 + 4], f"{lq.situation}")

    # -- Verweise ----------------------------------------------------------
    offen = _offene_verweise(ziel)
    expect("Anhaengen: kein Namensverweis zeigt ins Leere", not offen, "; ".join(offen[:8]))

    def koord(knoten):
        return [tuple(float(x) for x in np.round(ziel.nodes[int(n)], 9)) for n in knoten]

    def el_koord(e):
        return koord(ziel.elements[int(e)].nodes)

    stab = ziel.members.get("S1_2")
    ll = [x for x in ziel.load_cases["LF1"].linienlasten if x.art == "stab"]
    expect("Anhaengen: Stab S1 der Quelle heisst S1_2 und liegt auf dem Quellstab",
           stab is not None and el_koord(stab.elements[0]) == [(0, 0, 0), (2, 0, 0)]
           and stab.beta_y == 0.7 and [x.ziel for x in ll] == ["S1_2"],
           f"{None if stab is None else el_koord(stab.elements[0])}, Linienlast auf "
           f"{[x.ziel for x in ll]}")
    f1 = ziel.flaechen.get("F1_2")
    expect("Anhaengen: Flaeche F1 der Quelle heisst F1_2, Rand, Ecken und Elemente folgen",
           f1 is not None and f1.linien == ["L1_2", "L2_2", "L3_2", "L4_2"]
           and koord(f1.ecken) == [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)]
           and koord(f1.integrierte_knoten) == [(2, 1, 0)]
           and f1.elemente == [ne0 + 1] and f1.randseiten == [[ne0 + 2, 0]]
           and f1.dicke == "t12",
           f"{None if f1 is None else (f1.linien, f1.elemente, f1.randseiten)}")
    kb = ziel.kontaktbedingungen.get("KB1_2")
    lf1 = ziel.load_cases["LF1"]
    expect("Anhaengen: Fuge KB1 der Quelle heisst KB1_2, Uebermass und Kontaktpaar folgen",
           kb is not None and kb.flaechennamen == ["F1_2"] and kb.koerpernamen == ["K1"]
           and [u.ziel for u in lf1.uebermasse] == ["KB1_2"]
           and [c.name for c in ziel.contact_pairs] == ["KB1_2"]
           and list(ziel.getrennte_knoten) == ["KB1_2"],
           f"{[u.ziel for u in lf1.uebermasse]}, {[c.name for c in ziel.contact_pairs]}")
    if ziel.contact_pairs:
        cp = ziel.contact_pairs[0]
        expect("Anhaengen: Kontaktpaar traegt seine Knoten, Flaechen und Randknoten",
               koord(cp.slave_nodes) == [(3, 0, 1), (4, 0, 1)]
               and koord(cp.knotenflaechen) == [(3, 0, 1)]
               and koord(cp.rand_knoten) == [(4, 0, 1)] and cp.master_elements == [ne0 + 2],
               f"{cp.slave_nodes}, {cp.knotenflaechen}, {cp.rand_knoten}")
    co = ziel.combinations.get("CO1_2")
    expect("Anhaengen: Kombination CO1 der Quelle heisst CO1_2, Faktoren und Situation bleiben",
           co is not None and co.factors == {"LF1": 1.35, "LF-Q": 1.5}
           and co.situation == "Montage_2" and ziel.combinations["CO1"].factors == {"LF1": 1.0},
           f"{None if co is None else (co.factors, co.situation)}")
    j1 = ziel.joints.get("J1")
    expect("Anhaengen: Anschluss nennt die umbenannte Ermuedungslast E1_2",
           j1 is not None and j1.ermuedung == ["E1_2"] and j1.elem == ne0
           and ziel.fatigue_loads["E1_2"].case_max == "LF-Q",
           f"{None if j1 is None else (j1.ermuedung, j1.elem)}")

    # -- Felder, die der alte Weg unterwegs verlor ------------------------
    e = ziel.elements
    bl = [b for b in lf1.beam_loads if not getattr(b, "_geo", False)]
    expect("Anhaengen: Elementfelder bleiben (nur Zug, Gelenk, Feder, Werkstoff der Quelle)",
           e[ne0 + 4].nur == "zug" and e[ne0].hinges and e[ne0 + 3].sec == "FE1"
           and e[ne0 + 2].mat == "S235_2" and "S235_2" in ziel.materials
           and ziel.materials["S235_2"].E == 200e9 and ziel.materials["S235"].E == 210e9,
           f"nur={e[ne0 + 4].nur!r}, Gelenke={e[ne0].hinges}, mat={e[ne0 + 2].mat}")
    s_q = [s for s in ziel.supports if s.name == "A1"]
    expect("Anhaengen: Knotenlager behaelt Ausfall bei Zug; Teilstrecke der Stablast bleibt",
           s_q and s_q[0].dof_behaviour(2).failure == "zug"
           and [(b.a, b.b) for b in bl] == [(0.2, 0.8)],
           f"{[(b.a, b.b) for b in bl]}, Lager A1: {len(s_q)}")
    if ziel.line_supports and ziel.surface_supports:
        ls = ziel.line_supports[0]
        ss = ziel.surface_supports[0]
        expect("Anhaengen: Linien- und Flaechenlager auf den Knoten der Quelle",
               koord(ls.nodes) == [(0, 0, 0), (2, 0, 0)] and ls.linien == ["L1_2"]
               and ss.elements == [ne0 + 1] and ss.flaechen == ["F1_2"]
               and koord(ss.gruppen[0][2]) == [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)],
               f"{koord(ls.nodes)}, {ss.elements}, {ss.flaechen}")
    if ziel.punktmassen and ziel.starrkoerper and lf1.zwangsverformungen:
        pm, sk = ziel.punktmassen[0], ziel.starrkoerper[0]
        zv = lf1.zwangsverformungen[0]
        expect("Anhaengen: Punktmasse, Starrkoerper und Zwangsverformung an den Quellknoten",
               koord([pm.node]) == [(0, 1, 0)] and koord([sk.master]) == [(3, 0, 0)]
               and koord(sk.slaves) == [(4, 0, 0), (4, 1, 0)] and zv.node == 0,
               f"{koord([pm.node])}, {koord([sk.master])}, Zwang an {zv.node}")
    su = ziel.subsysteme.get("SU1")
    expect("Anhaengen: Subsystem zaehlt seine Lager ab den Lagern des Ziels",
           su is not None and su.lager == [1] and su.linienlager == [0]
           and su.flaechenlager == [0] and su.elemente == [ne0] and su.staebe == ["S1_2"]
           and su.kontakte == ["KB1_2"],
           f"{None if su is None else (su.lager, su.elemente, su.staebe)}")

    # -- Protokoll ---------------------------------------------------------
    text = "\n".join(log)
    expect("Anhaengen: Protokoll nennt die nicht uebertragenen Stellungen und Berichtseintraege",
           any("Stellungen" in z and "1" in z for z in log)
           and any("Bericht" in z and "1" in z for z in log), text[-600:])
    expect("Anhaengen: Protokoll nennt die Umbenennungen",
           "S1_2" in text and "F1_2" in text and "S235_2" in text, text[-600:])


def test_json_anhaengen_hallenrahmen():
    """Die Probe aus der Stand-Pruefung: der Hallenrahmen, ergaenzt um ein
    Linienlager, ein Flaechenlager, eine Linienlast und eine Ermuedungslast,
    an den Rahmen gehaengt. Gemessen am 22.09.2026 kamen 0 von 72
    Kombinationen, 0 von 1 Linienlager, 0 von 1 Flaechenlager und 0 von 2
    Ermuedungslasten an."""
    from statik3d import examples_lib
    src = examples_lib.build_example("hall")
    lf = next(iter(src.load_cases))
    src.add_line_support([0, 1], name="LL-Probe", uz=dict(typ="rigid"))
    src.add_surface_support(elements=[0], name="FL-Probe")
    src.add_linienlast(next(iter(src.members)), [0.0, 0.0, -5e3], case=lf)
    src.add_fatigue_load("Erm-Probe", lf)
    src.load_cases[lf].grundlast = True
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "quelle.json")
        src.save(p)
        ziel = examples_lib.build_example("frame")
        vorher = (len(ziel.combinations), len(ziel.line_supports), len(ziel.surface_supports),
                  len(ziel.fatigue_loads), len(ziel.load_cases[lf].linienlasten))
        log = []
        ziel = import_file(p, model=ziel, log=log)
    ist = (len(ziel.combinations) - vorher[0], len(ziel.line_supports) - vorher[1],
           len(ziel.surface_supports) - vorher[2], len(ziel.fatigue_loads) - vorher[3],
           len(ziel.load_cases[lf].linienlasten) - vorher[4])
    soll = (len(src.combinations), 1, 1, len(src.fatigue_loads), 1)
    expect("Hallenrahmen angehaengt: Kombinationen, Linien-/Flaechenlager, Ermuedung, Linienlast",
           ist == soll, f"angekommen {ist}, in der Quelle {soll}")
    # LF1 gibt es im Rahmen schon: seine Eigenschaften bleiben die des Ziels,
    # die abweichende Grundlast der Quelle steht im Protokoll
    expect("Hallenrahmen: abweichende Grundlast des gleichnamigen Lastfalls wird gemeldet",
           any(lf in z and "grundlast" in z.lower() for z in log), "\n".join(log[-6:]))


def test_json_anhaengen_eigengewicht_und_gleiches():
    """Das Eigengewicht gilt je Lastfall fuer alle Elemente. Haben Ziel und
    Quelle es in einem Lastfall verschieden, erfasst es nach dem Anhaengen
    auch die Elemente des anderen Teils (oder fehlt ihnen) - das steht im
    Protokoll. Und gleichnamige Werkstoffe mit gleichem Inhalt werden nicht
    doppelt angelegt, auch wenn einer 7850 und der andere 7850.0 fuehrt."""
    from statik3d.model import Material, Section
    z = Model("Ziel")
    z.add_material(Material("S235", rho=7850))           # ganze Zahl im Speicher
    z.add_section(Section.rectangle("R", 0.1, 0.2))
    z.add_node(0, 0, 0); z.add_node(1, 0, 0)
    z.add_element("beam", [0, 1], "S235", "R")
    z.load_cases["LF1"].gravity = [0.0, 0.0, -9.81]
    q = Model("Quelle")
    q.add_material(Material("S235", rho=7850.0))
    q.add_section(Section.rectangle("R", 0.1, 0.2))
    q.add_node(5, 0, 0); q.add_node(6, 0, 0)
    q.add_element("beam", [0, 1], "S235", "R")
    q.add_load_case("LF2", "G", activate=False).gravity = [0.0, 0.0, -9.81]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "q.json")
        q.save(p)
        log = []
        z = import_file(p, model=z, log=log)
    lf1 = [x for x in log if "'LF1'" in x and "Eigengewicht" in x]
    lf2 = [x for x in log if "'LF2'" in x and "Eigengewicht" in x]
    expect("Anhaengen: verschiedenes Eigengewicht je Lastfall steht im Protokoll",
           len(lf1) == 1 and len(lf2) == 1, "\n".join(lf1 + lf2) or "\n".join(log))
    expect("Anhaengen: gleicher Werkstoff (7850 gegen 7850.0) wird nicht umbenannt",
           list(z.materials) == ["S235"] and z.elements[1].mat == "S235",
           f"{list(z.materials)}")


def _zwei_staebe_mit_spalt(name: str, x0: float) -> Model:
    """Zwei Staebe, deren Enden bei x0 + 1 aufeinanderliegen und nur ueber
    ein Spaltelement verbunden sind - eine getrennte Fuge."""
    from statik3d.model import Material, Section
    m = Model(name)
    m.add_material(Material("S235"))
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    for p in [(x0, 0, 0), (x0 + 1, 0, 0), (x0 + 1, 0, 0), (x0 + 2, 0, 0)]:
        m.add_node(*p)
    m.add_element("beam", [0, 1], "S235", "R")
    m.add_element("beam", [2, 3], "S235", "R")
    m.add_gap_element(1, 2, direction=[1, 0, 0])
    return m


def test_json_anhaengen_doppelknoten_bleiben():
    """Nach dem Anhaengen schliesst nur die Quelle an das Ziel an; Knoten,
    die in einem Teil schon aufeinanderliegen, bleiben getrennt.

    Bis zur Nachbesserung vom 23.09.2026 lief merge_duplicate_nodes ueber
    das ganze Modell: das Spaltelement (1, 2) des Ziels wurde (1, 1), das der
    Quelle ebenso, und die Staebe hingen zusammen. Liegt ein Knoten des einen
    Teils auf einer solchen Fuge des anderen, ist nicht eindeutig, woran er
    anschliessen soll: dann bleibt er getrennt, und das Protokoll nennt die
    Stelle."""
    q = _zwei_staebe_mit_spalt("Quelle", 5.0)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "q.json")
        q.save(p)
        log = []
        z = import_file(p, model=_zwei_staebe_mit_spalt("Ziel", 0.0), log=log)
        spalt = [(g.node_a, g.node_b) for g in z.gap_elements]
        expect("Anhaengen: Spaltelemente von Ziel und Quelle verbinden weiter zwei Knoten",
               spalt == [(1, 2), (5, 6)] and z.nn == 8,
               f"{spalt}, {z.nn} Knoten")
        expect("Anhaengen: ohne Anschluss keine Zeile ueber zusammengefuehrte Knoten",
               not any("zusammengeführt" in x for x in log), "\n".join(log))
        # Quelle beginnt genau auf der Fuge des Ziels bei x = 1: uneindeutig
        from statik3d.model import Material, Section
        q2 = Model("Quelle2")
        q2.add_material(Material("S235"))
        q2.add_section(Section.rectangle("R", 0.1, 0.2))
        q2.add_node(1, 0, 0); q2.add_node(1, 1, 0); q2.add_node(0, 0, 0)
        q2.add_element("beam", [0, 1], "S235", "R")
        q2.add_element("beam", [1, 2], "S235", "R")
        q2.save(p)
        log = []
        z = import_file(p, model=_zwei_staebe_mit_spalt("Ziel", 0.0), log=log)
    unklar = [x for x in log if x.startswith("WARNUNG") and "An 1 Stelle " in x
              and "(1, 0, 0)" in x]
    expect("Anhaengen: eindeutiger Anschluss (0,0,0) zusammengefuehrt, die Fuge bei (1,0,0) "
           "nicht, und das Protokoll nennt sie",
           z.nn == 4 + 2 and [(g.node_a, g.node_b) for g in z.gap_elements] == [(1, 2)]
           and z.elements[3].nodes == [5, 0] and len(unklar) == 1
           and any("1 Knoten der Quelle lagen auf Knoten des Ziels" in x for x in log),
           f"{z.nn} Knoten, Elemente {[e.nodes for e in z.elements]}\n" + "\n".join(log))


def test_doppelte_knoten_verweise():
    """``merge_duplicate_nodes`` (Nachbereitung jedes Nicht-JSON-Imports,
    also auch jedes .rf6) haengt auch Flaechenecken, integrierte Knoten und
    Punktmassen um. Am Drehlager_V15_4_export.rf6 lagen bis zum 22.09.2026
    1444 von 3128 Ecken nicht auf den Knoten ihrer Randlinien."""
    from statik3d.model import Material, Flaeche
    from statik3d.importers import _common as C
    m = Model("m")
    m.add_material(Material("S235"))
    for p in [(0, 0, 0), (1, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]:
        m.add_node(*p)
    m.add_line("L1", [0, 1]); m.add_line("L2", [2, 3]); m.add_line("L3", [3, 4])
    m.add_line("L4", [4, 0])
    # direkt angelegt wie in den Lesern: vor dem Zusammenfuehren ist der Rand
    # bei (1, 0, 0) noch offen, add_flaeche lehnte das ab
    m.flaechen["F1"] = Flaeche("F1", ["L1", "L2", "L3", "L4"], ecken=[0, 2, 3, 4],
                               integrierte_knoten=[3])
    m.add_punktmasse(4, 10.0)
    weg = C.merge_duplicate_nodes(m)
    f = m.flaechen["F1"]
    expect("Doppelte Knoten: Ecken, integrierte Knoten und Punktmasse folgen der neuen Nummer",
           weg == 1 and m.nn == 4 and f.ecken == [0, 1, 2, 3] and f.integrierte_knoten == [2]
           and m.lines["L2"].nodes == [1, 2] and m.punktmassen[0].node == 3,
           f"weg {weg}, Ecken {f.ecken}, integriert {f.integrierte_knoten}, "
           f"Punktmasse {m.punktmassen[0].node}")


def test_json_anhaengen_fuge_traegt_wie_allein():
    """Eine Quelle mit ausgefuehrter Kontaktfuge ("Ausfall bei Zug") rechnet
    angehaengt wie allein. Gemessen vor der Nachbesserung vom 23.09.2026
    (zwei Bloecke aus tests.test_fugen, 200 kN Zug): allein 0,0 N am
    Fundament, an ein leeres Ziel gehaengt -198 152,7 N - 24 von 24
    Spaltelementen verbanden einen Knoten mit sich selbst, und die Fuge stand
    weiter auf "ausgefuehrt"."""
    from tests.test_fugen import zwei_bloecke, kontaktbedingung, _flaechenknoten
    from statik3d import fugen, solver
    from statik3d.model import Material, Section
    q = zwei_bloecke("gemeinsam")
    kontaktbedingung(q, "gemeinsam", failure="zug")
    fugen.kontaktfugen_ausfuehren(q, [])
    unten, oben = _flaechenknoten(q, 0.0), _flaechenknoten(q, 2.0)
    for i in unten:
        q.fix(i, [0, 1, 2])
    k = 1e9 / len(oben)
    for i in oben:
        q.fix(i, [0, 1, 2], stiffness=[k, k, k])
    lc = q.add_load_case("LZ", "Q", activate=False)
    lc.gravity = [0, 0, 0]
    q.add_geometrielast("Dach", -2e5, "flaeche", case="LZ")          # zieht nach oben
    q.lasten_verteilen()
    unten_xyz = np.array([q.nodes[i] for i in unten])

    def fundament(m):
        r = solver.solve_static(m, case="LZ", workers=1)
        idx = [i for i in range(m.nn) if np.min(np.abs(unten_xyz - m.nodes[i]).sum(1)) < 1e-9]
        return float(np.asarray(r.reactions)[idx, 2].sum())

    fern = Model("Ziel")                          # ein Stab abseits, eingespannt
    fern.add_material(Material("S235"))
    fern.add_section(Section.rectangle("R", 0.1, 0.2))
    fern.add_node(10, 0, 0); fern.add_node(11, 0, 0)
    fern.add_element("beam", [0, 1], "S235", "R")
    fern.fix(0, "all")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "q.json")
        q.save(p)
        allein = fundament(Model.load(p))
        for text, ziel in (("leeres Ziel", Model("leer")), ("Ziel mit Stab abseits", fern)):
            z = import_file(p, model=ziel, log=[])
            selbst = sum(1 for g in z.gap_elements if int(g.node_a) == int(g.node_b))
            r = fundament(z)
            expect(f"Anhaengen an {text}: Fuge bleibt getrennt, Fundament wie allein",
                   selbst == 0 and len(z.gap_elements) == 24 and abs(r - allein) < 1.0,
                   f"allein {allein:.1f} N, angehaengt {r:.1f} N, Spaltelemente mit sich "
                   f"selbst {selbst} von {len(z.gap_elements)}")


def test_json_anhaengen_ermuedung_auf_kombination():
    """Ein Zustand einer Ermuedungslast darf eine Kombination sein (am CBG
    alle 20). Wird die Kombination der Quelle umbenannt, folgt ihr die
    Ermuedungslast. Gemessen vor der Nachbesserung vom 23.09.2026: Quelle
    CO1 = {LF1: 1,0; LF2: 1,0}, Ziel CO1 = {LF1: 1,0; LF2: 0,1}; danach hiess
    die der Quelle CO1_2, FAT-Q zeigte aber auf 'CO1' des Ziels. Hatte das
    Ziel auch eine FAT-Q auf seine CO1, galten beide als gleich, und die der
    Quelle fiel weg."""
    from statik3d.model import Material, Section, FatigueLoad

    def modell(name, x0, faktor, mit_fat):
        m = Model(name)
        m.add_material(Material("S235"))
        m.add_section(Section.rectangle("R", 0.1, 0.2))
        m.add_node(x0, 0, 0); m.add_node(x0 + 1, 0, 0)
        m.add_element("beam", [0, 1], "S235", "R")
        m.fix(0, "all")
        m.load_node(1, Fz=-1e3, case="LF1")
        m.add_load_case("LF2", "Q", activate=False)
        m.load_node(1, Fz=-5e3, case="LF2")
        m.add_combination("CO1", {"LF1": 1.0, "LF2": faktor}, typ="FAT")
        if mit_fat:
            m.add_fatigue_load("FAT-Q", "CO1")
        return m

    def anhaengen(ziel, quelle):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "q.json")
            quelle.save(p)
            return import_file(p, model=ziel, log=[])

    q = modell("Quelle", 5.0, 1.0, True)
    q.fatigue_loads["FAT-V"] = FatigueLoad("FAT-V", folge=["LF1", "CO1", "LF1"])
    z = anhaengen(modell("Ziel", 0.0, 0.1, False), q)
    fq, fv = z.fatigue_loads.get("FAT-Q"), z.fatigue_loads.get("FAT-V")
    expect("Anhaengen: Ermuedungslast folgt der umbenannten Kombination (case_max, folge)",
           fq is not None and fq.case_max == "CO1_2"
           and z.combinations["CO1_2"].factors == {"LF1": 1.0, "LF2": 1.0}
           and fv is not None and fv.folge == ["LF1", "CO1_2", "LF1"],
           f"FAT-Q -> {None if fq is None else fq.case_max}, FAT-V -> "
           f"{None if fv is None else fv.folge}")
    z = anhaengen(modell("Ziel", 0.0, 0.1, True), modell("Quelle", 5.0, 1.0, True))
    zustaende = {n: (f.case_max, z.combinations[f.case_max].factors["LF2"])
                 for n, f in z.fatigue_loads.items()}
    expect("Anhaengen: gleichnamige Ermuedungslast auf verschiedene Kombination bleibt erhalten",
           zustaende == {"FAT-Q": ("CO1", 0.1), "FAT-Q_2": ("CO1_2", 1.0)}, f"{zustaende}")
    z = anhaengen(modell("Ziel", 0.0, 1.0, True), modell("Quelle", 5.0, 1.0, True))
    expect("Anhaengen: gleiche Kombination und gleiche Ermuedungslast werden nicht verdoppelt",
           list(z.combinations) == ["CO1"] and list(z.fatigue_loads) == ["FAT-Q"],
           f"{list(z.combinations)}, {list(z.fatigue_loads)}")


def test_json_anhaengen_koerpergruppe():
    """Die Gruppe eines Volumenelements nennt seinen Koerper, und
    fugen.kontaktfuge_ausfuehren sucht den Koerper einer Kontaktbedingung
    ueber sie. Gemessen vor der Nachbesserung vom 23.09.2026: zwei hex8 V1
    (unten) und V2 (oben) mit Fuge KB1 auf V1 - allein wird der untere Block
    geloest; an ein Ziel mit eigenen V1/V2 gehaengt hiess der Koerper V1_2,
    seine Elemente trugen aber die Gruppe 'V1', und die Fuge loeste den
    oberen Block."""
    from statik3d.model import Material, Volumenkoerper, Flaeche
    from statik3d import fugen

    def bloecke(name, x0, mit_fuge):
        m = Model(name)
        m.add_material(Material("S235"))
        for zz in (0.0, 1.0, 2.0):
            for (x, y) in ((0, 0), (1, 0), (1, 1), (0, 1)):
                m.add_node(x0 + x, y, zz)
        u = m.add_element("hex8", [0, 1, 2, 3, 4, 5, 6, 7], "S235", group="V1")
        o = m.add_element("hex8", [4, 5, 6, 7, 8, 9, 10, 11], "S235", group="V2")
        m.koerper["V1"] = Volumenkoerper("V1", material="S235", elemente=[u])
        m.koerper["V2"] = Volumenkoerper("V2", material="S235", elemente=[o])
        for i in range(4):
            m.fix(i, "all")
        if mit_fuge:
            m.flaechen["FF"] = Flaeche("FF", randseiten=[[u, 1], [o, 0]])
            m.add_kontaktbedingung("KB1", flaechennamen=["FF"], koerpernamen=["V1"])
        return m

    def geloest(m, kb, unten, oben):
        vorher = (list(m.elements[unten].nodes), list(m.elements[oben].nodes))
        fugen.kontaktfuge_ausfuehren(m, m.kontaktbedingungen[kb], [])
        return (m.elements[unten].nodes != vorher[0], m.elements[oben].nodes != vorher[1])

    allein = geloest(bloecke("Quelle", 5.0, True), "KB1", 0, 1)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "q.json")
        bloecke("Quelle", 5.0, True).save(p)
        z = import_file(p, model=bloecke("Ziel", 0.0, False), log=[])
    gruppen = {n: sorted({z.elements[e].group for e in k.elemente}) for n, k in z.koerper.items()}
    kb = next(iter(z.kontaktbedingungen))
    angehaengt = geloest(z, kb, 2, 3)
    expect("Anhaengen: Elemente der umbenannten Koerper tragen den neuen Koerpernamen",
           gruppen == {"V1": ["V1"], "V2": ["V2"], "V1_2": ["V1_2"], "V2_2": ["V2_2"]},
           f"{gruppen}")
    expect("Anhaengen: die Fuge der Quelle loest denselben Block wie allein (unten)",
           allein == (True, False) and angehaengt == allein,
           f"allein (unten, oben) geloest {allein}, angehaengt {angehaengt}")


def test_json_anhaengen_stellung_des_ziels():
    """Stellungen werden nicht uebertragen; eine Situation der Quelle, die
    eine nennt, darf dann nicht still die gleichnamige Stellung des Ziels
    benutzen. Gemessen vor der Nachbesserung vom 23.09.2026: Rahmen als
    Quelle bei x = 50 m, Stellung 'Offen' hebt die ungelagerten Knoten um
    1,0 m, Lastfall LF-S (10 kN waagerecht) in Situation 'S-offen'; das Ziel
    ist der Rahmen bei x = 0 mit eigener Stellung 'Offen' ohne Verschiebung.
    Allein |u| = 4,7572 mm am Lastknoten, angehaengt 1,7876 mm - die
    Situation S-offen_2 nannte 'Offen' des Ziels, und weder Modellpruefung
    noch Protokoll sagten etwas (das Protokoll versprach es sogar)."""
    from statik3d import examples_lib
    from statik3d.model import Situation
    from statik3d.bridges.positions import Stellung
    from statik3d.situationen import situationsmodell

    def rahmen(dz, x0, mit_last):
        m = examples_lib.build_example("frame")
        m.nodes = np.asarray(m.nodes, float) + np.array([x0, 0.0, 0.0])
        m.stellungen = [Stellung("Offen", verschiebung=(0.0, 0.0, dz))]
        m.situationen["S-offen"] = Situation("S-offen", stellung="Offen")
        if mit_last:
            m.situationen["S-wind"] = Situation("S-wind", stellung="Offen")
            lc = m.add_load_case("LF-S", "Q", activate=False, situation="S-offen")
            lc.gravity = [0.0, 0.0, 0.0]
            m.load_node(2, Fx=1e4, case="LF-S")
        return m

    def verschiebung(m):
        """|u| am Lastknoten der Quelle (bei x = 50 m, ueber die Lage gesucht)."""
        p = np.asarray(examples_lib.build_example("frame").nodes[2], float) + [50.0, 0, 0]
        i = int(np.argmin(np.abs(np.asarray(m.nodes) - p).max(axis=1)))
        r = solver.solve_cases(m, ["LF-S"], workers=1)["LF-S"]
        return float(np.linalg.norm(np.asarray(r.u).reshape(-1, 6)[i, :3]))

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "q.json")
        rahmen(1.0, 50.0, True).save(p)
        allein = verschiebung(Model.load(p))
        # Ziel ohne Stellung: die Situation behaelt ihren Verweis, die
        # Modellpruefung meldet ihn (so, wie das Protokoll es sagt)
        z = examples_lib.build_example("frame")
        z = import_file(p, model=z, log=[])
        chk = [c for c in z.check() if "Stellung" in c]
        expect("Anhaengen an Ziel ohne Stellung: Verweis bleibt, Modellpruefung meldet ihn",
               z.situationen["S-offen"].stellung == "Offen" and len(chk) == 2, f"{chk}")
        # Ziel mit eigener Stellung 'Offen'
        log = []
        z = import_file(p, model=rahmen(0.0, 0.0, False), log=log)
    sit = z.load_cases["LF-S"].situation
    verweise = {n: s.stellung for n, s in z.situationen.items()}
    chk = [c for c in z.check() if "Stellung" in c]
    expect("Anhaengen: Situationen der Quelle nennen nicht die gleichnamige Stellung des Ziels",
           sit == "S-offen_2" and verweise == {"S-offen": "Offen", "S-offen_2": "Offen_2",
                                               "S-wind": "Offen_2"},
           f"{verweise}")
    expect("Anhaengen: Modellpruefung meldet beide Situationen der Quelle",
           len(chk) == 2 and all("Offen_2" in c for c in chk)
           and any("'S-offen_2'" in c for c in chk) and any("'S-wind'" in c for c in chk),
           f"{chk}")
    zeilen = [x for x in log if x.startswith("WARNUNG") and "S-offen_2" in x
              and "S-wind" in x and "'Offen_2'" in x]
    expect("Anhaengen: Protokoll nennt die Situationen und den neuen Verweis",
           len(zeilen) == 1, "\n".join(x for x in log if "Stellung" in x))
    try:
        situationsmodell(z, sit)
        fehler = ""
    except ValueError as ex:
        fehler = str(ex)
    expect("Anhaengen: Rechnung in der Situation der Quelle bricht mit Meldung ab",
           "Offen_2" in fehler and "unbekannt" in fehler, fehler or "rechnet ohne Meldung")
    # Wie weit solve_all abbricht, haengt an "Lastfaelle gleichzeitig
    # (Ketten)"; das Handbuch nennt beide Faelle.
    # * Vorgabe nacheinander (ketten = 1): solve_all baut alle
    #   Situationssysteme, bevor der erste Lastfall rechnet
    #   (solver.systeme_je_situation), und die Ausnahme traegt kein
    #   Teilergebnis - auch LF1 des Ziels in der Grundstellung bekommt keines.
    # * Zwei Ketten: _cases_in_ketten teilt Situation fuer Situation auf, nur
    #   die Kette mit LF-S scheitert, und LF1 haengt als Teilergebnis an der
    #   Ausnahme (_teil_merken, _teilanalyse).
    # LF1 allein rechnet.
    from statik3d import parallel

    def alle_rechnen(ketten):
        parallel.configure(ketten=ketten)
        try:
            solver.solve_all(z, workers=1)
            return "fertig", None, None
        except (ValueError, RuntimeError) as ex:
            teil = getattr(ex, "teilanalyse", None)
            return (f"{type(ex).__name__}: {(str(ex).splitlines() or [''])[0]}",
                    None if teil is None else sorted(teil.cases),
                    getattr(ex, "teil_cases", None))

    alt_k = parallel.settings().ketten
    try:
        fehler, teil, teil_cases = alle_rechnen(1)
        fehler2, teil2, _teil_cases2 = alle_rechnen(2)
    finally:
        parallel.configure(ketten=alt_k)
    nur_lf1 = sorted(solver.solve_cases(z, ["LF1"], workers=1))
    expect("Anhaengen: nacheinander bricht solve_all ganz ab, ohne Teilergebnis; "
           "LF1 allein rechnet",
           fehler.startswith("ValueError:") and "Offen_2" in fehler and "unbekannt" in fehler
           and teil is None and teil_cases is None and nur_lf1 == ["LF1"],
           f"solve_all: {fehler}, Teilergebnis {teil}, teil_cases {teil_cases}; "
           f"solve_cases(['LF1']): {nur_lf1}")
    expect("Anhaengen: in zwei Ketten scheitert nur die Kette mit LF-S, LF1 ist Teilergebnis",
           fehler2.startswith("RuntimeError: Kette") and "'S-offen_2'" in fehler2
           and "unbekannt" in fehler2 and teil2 == ["LF1"],
           f"solve_all: {fehler2}, Teilergebnis {teil2}")
    # Legt der Anwender die Stellung der Quelle unter dem neuen Namen an,
    # rechnet der Lastfall der Quelle wie allein
    z.stellungen.append(Stellung("Offen_2", verschiebung=(0.0, 0.0, 1.0)))
    angehaengt = verschiebung(z)
    expect("Anhaengen: mit der Stellung der Quelle unter neuem Namen rechnet LF-S wie allein",
           abs(angehaengt - allein) <= 1e-9 * max(allein, 1e-12) + 1e-15,
           f"allein {allein * 1e3:.4f} mm, angehaengt {angehaengt * 1e3:.4f} mm")


def test_json_anhaengen_stellung_protokoll():
    """Das Protokoll sagt, was eine nicht uebertragene Stellung bewegt, so wie
    Stellung._bewegte_knoten es tut: mit Gruppenangabe nur die Knoten der
    Gruppe, ohne sie alle Knoten ohne Knotenlager - auch die auf einem
    Linienlager -, und nur, wenn sie verschiebt oder dreht. Bis zum
    23.09.2026 stand dort "eine Stellung bewegt das ganze System"; gemessen
    am Beispiel 'frame' (17 Knoten, Knotenlager an 0 und 5): Gruppe 'Klappe'
    aus den Elementen 10 bis 15 bewegt 7 Knoten, eine Stellung, die nur ein
    Lager abschaltet, keinen."""
    from statik3d import examples_lib
    from statik3d.model import Situation, LineSupport, DofBehaviour
    from statik3d.bridges.positions import Stellung
    from statik3d.situationen import situationsmodell

    def bewegt(m, st):
        m.stellungen = [st]
        m.situationen["S"] = Situation("S", stellung=st.name)
        ms, _a, _log = situationsmodell(m, "S")
        return np.abs(np.asarray(ms.nodes) - np.asarray(m.nodes)).max(axis=1) > 1e-12

    m = examples_lib.build_example("frame")
    for i in range(10, 16):
        m.elements[i].group = "Klappe"
    gruppe = int(bewegt(m, Stellung("Klappe", verschiebung=(0.0, 0.0, 1.0),
                                    dreh_gruppen=["Klappe"])).sum())
    m = examples_lib.build_example("frame")
    nur_lager = int(bewegt(m, Stellung("Riegel", lager_aus=["0"])).sum())
    m = examples_lib.build_example("frame")
    fest = {s.node for s in m.supports}
    auf_linienlager = [i for i in range(m.nn) if i not in fest][:2]
    m.line_supports.append(LineSupport("LL", nodes=auf_linienlager, behaviour={
        k: DofBehaviour("rigid") for k in range(3)}))
    ohne = bewegt(m, Stellung("Offen", verschiebung=(0.0, 0.0, 1.0)))
    expect("Stellung bewegt: Gruppe nur ihre Knoten, nur Lager aus keinen, sonst alle ohne "
           "Knotenlager",
           gruppe == 7 and nur_lager == 0 and int(ohne.sum()) == m.nn - len(fest)
           and bool(ohne[auf_linienlager].all()),
           f"Gruppe {gruppe}, nur Lager aus {nur_lager}, ohne Gruppe {int(ohne.sum())} von "
           f"{m.nn} (Knotenlager an {sorted(fest)}), auf Linienlager bewegt "
           f"{ohne[auf_linienlager].tolist()}")

    q = examples_lib.build_example("frame")
    q.nodes = np.asarray(q.nodes, float) + np.array([50.0, 0.0, 0.0])
    q.stellungen = [Stellung("Offen", verschiebung=(0.0, 0.0, 1.0))]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "q.json")
        q.save(p)
        log = []
        import_file(p, model=examples_lib.build_example("frame"), log=log)
    zeile = [x for x in log if x.startswith("WARNUNG: Stellungen:")]
    expect("Anhaengen: Protokoll sagt, was eine Stellung bewegt, nicht 'das ganze System'",
           len(zeile) == 1 and "ganze System" not in zeile[0]
           and "ohne Gruppenangabe" in zeile[0] and "ohne Knotenlager" in zeile[0],
           "\n".join(zeile) or "keine Zeile")


def test_json_anhaengen_tetp_kantenmitten():
    """Die gekruemmte Geometrie der Tetraeder mit Ordnung p (Modellschluessel
    ``tetp_kantenmitten``, seit dem 23.09.2026 in der Datei) kommt beim
    Anhaengen mit: die Knotennummern ihrer Kanten folgen dem Versatz und dem
    Zusammenfuehren mit dem Ziel. Geprueft an der Geometrie jedes
    angehaengten Elements (tetp.geometrie_modell) gegen die der Quelle -
    bitgleich. Ein Zielknoten liegt auf einer Ecke einer gekruemmten Kante
    der Quelle; das Zusammenfuehren nummeriert damit jeden spaeteren Knoten
    der Quelle um.

    Treffen beim Zusammenfuehren zwei verschiedene Kantenmitten auf dieselbe
    Kante (die Quelle an sich selbst gehaengt, eine Kantenmitte um 1 mm
    verschoben), gilt die des Ziels, und das Protokoll nennt die Kante."""
    from statik3d.elements import tetp as tp
    from tests import pruefkoerper as pk
    hk = pk.Hohlkugel()
    q0 = hk.modell("tet10", 2, 2)
    q0.case().nodal_loads.clear()
    tp.aus_tet10(q0, ordnung=3)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "hohlkugel.json")
        q0.save(p)
        quelle = Model.load(p)                 # so, wie sie beim Anhaengen gelesen wird
        km_q = getattr(quelle, "tetp_kantenmitten", None) or {}
        a = next(iter(km_q))[0] if km_q else 0
        ziel = Model("ziel")
        ziel.add_node(5.0, 5.0, 5.0)
        ziel.add_node(*[float(x) for x in quelle.nodes[a]])
        log = []
        ziel = import_file(p, model=ziel, log=log)

        idx_q = [i for i, e in enumerate(quelle.elements) if tp.ist_tetp(e.typ)]
        G_q = tp.geometrie_modell(quelle, idx_q)
        G_z = tp.geometrie_modell(ziel, idx_q)       # das Ziel hatte keine Elemente
        km_z = getattr(ziel, "tetp_kantenmitten", None) or {}
        text = "\n".join(log)
        expect("Anhaengen: gekruemmte Kanten der Quelle kommen an, Geometrie bitgleich",
               len(km_q) > 0 and len(km_z) == len(km_q) and ziel.nn == 2 + quelle.nn - 1
               and np.array_equal(G_q, G_z),
               f"{len(km_z)} von {len(km_q)} Kanten, {ziel.nn} Knoten, "
               f"max|dG| {float(np.abs(G_z - G_q).max()):.3e} m")
        expect("Anhaengen: Protokoll nennt die gekruemmten Kanten, keine Warnung zum Feld",
               "tetp_kantenmitten" not in text and "gekrümmte Kanten" in text, text[-400:])

        # Konflikt: die Quelle an sich selbst, eine Kantenmitte um 1 mm verschoben
        schl = next(iter(km_q))
        q2 = Model.load(p)
        q2.tetp_kantenmitten[schl] = np.asarray(q2.tetp_kantenmitten[schl], float) \
            + np.array([0.0, 0.0, 1e-3])
        p2 = os.path.join(d, "verschoben.json")
        q2.save(p2)
        ziel2 = Model.load(p)
        log2 = []
        ziel2 = import_file(p2, model=ziel2, log=log2)
    km2 = ziel2.tetp_kantenmitten
    zeile = [x for x in log2 if "Kantenmitte" in x]
    expect("Anhaengen: zwei verschiedene Kantenmitten auf einer Kante - die des Ziels "
           "gilt, das Protokoll nennt sie",
           ziel2.nn == quelle.nn and len(km2) == len(km_q)
           and np.array_equal(km2[schl], km_q[schl]) and len(zeile) == 1
           and zeile[0].startswith("WARNUNG") and "1 Kante " in zeile[0]
           and "1 mm" in zeile[0],
           f"{ziel2.nn} Knoten, {len(km2)} Kanten; " + ("\n".join(zeile) or "keine Zeile"))


def test_json_anhaengen_schluessel():
    """Jeder Schluessel von Model.to_dict() und LoadCase.to_dict() ist beim
    Anhaengen eingeordnet: uebertragen, als Einstellung des Ziels behalten
    oder mit Grund als nicht uebertragbar gemeldet. Ein kuenftig ergaenztes
    Modellfeld faellt so nicht wieder still weg - diese Pruefung schlaegt an,
    bis es eingeordnet ist."""
    from statik3d.model import LoadCase
    try:
        from statik3d.importers import anhaengen as A
    except ImportError as ex:
        expect("Anhaengen: Einordnung der Modellschluessel vorhanden", False, repr(ex))
        return
    eingeordnet = set(A.UEBERTRAGEN) | set(A.ZIEL_BEHAELT) | set(A.NICHT_UEBERTRAGEN)
    fehlt = sorted(set(Model("x").to_dict()) - eingeordnet)
    expect("Anhaengen: jeder Schluessel von Model.to_dict() ist eingeordnet", not fehlt,
           ", ".join(fehlt) or f"{len(eingeordnet)} Schluessel")
    doppelt = sorted((set(A.UEBERTRAGEN) & set(A.NICHT_UEBERTRAGEN))
                     | (set(A.UEBERTRAGEN) & set(A.ZIEL_BEHAELT))
                     | (set(A.ZIEL_BEHAELT) & set(A.NICHT_UEBERTRAGEN)))
    expect("Anhaengen: kein Schluessel ist doppelt eingeordnet", not doppelt, ", ".join(doppelt))
    lc_fehlt = sorted(set(LoadCase("x").to_dict()) - set(A.LASTFALL_EINGEORDNET))
    expect("Anhaengen: jeder Schluessel von LoadCase.to_dict() ist eingeordnet", not lc_fehlt,
           ", ".join(lc_fehlt) or "alle")
    ohne_grund = [k for k, v in A.NICHT_UEBERTRAGEN.items() if not str(v).strip()]
    expect("Anhaengen: jeder nicht uebertragene Schluessel hat einen Grund fuer das Protokoll",
           not ohne_grund, ", ".join(ohne_grund))


TESTS = [
    test_dicke_wird_nicht_still_geerbt, test_xlsx_roundtrip, test_dxf, test_abaqus_inp, test_nastran_bdf, test_ifc_parser,
         test_ifc, test_ifc2x3, test_ifc_physical_fallback, test_saf, test_rfem_xlsx,
         test_rfem_csv_folder, test_dispatcher, test_json_anhaengen_vollstaendig,
         test_json_anhaengen_hallenrahmen, test_json_anhaengen_eigengewicht_und_gleiches,
         test_json_anhaengen_doppelknoten_bleiben, test_doppelte_knoten_verweise,
         test_json_anhaengen_fuge_traegt_wie_allein,
         test_json_anhaengen_ermuedung_auf_kombination, test_json_anhaengen_koerpergruppe,
         test_json_anhaengen_stellung_des_ziels, test_json_anhaengen_stellung_protokoll,
         test_json_anhaengen_tetp_kantenmitten, test_json_anhaengen_schluessel,
         test_entarteter_sechsflaechner_beim_import]


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
