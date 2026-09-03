"""
Export als IFC 4 Statikmodell (Structural Analysis View), STEP-Datei.

Geschrieben werden IfcStructuralAnalysisModel mit IfcStructuralPointConnection
(Knoten), IfcStructuralCurveMember (Staebe), IfcStructuralSurfaceMember
(Flaechen), IfcBoundaryNodeCondition (Lager) sowie IfcStructuralLoadGroup mit
IfcStructuralPointAction fuer die Lastfaelle.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from ..model import Model
from . import _common as C


class _Step:
    """Sammelt STEP-Zeilen und vergibt die Nummern."""

    def __init__(self):
        self.lines: list[str] = []
        self.n = 0

    def add(self, text: str) -> str:
        self.n += 1
        self.lines.append(f"#{self.n}={text};")
        return f"#{self.n}"

    def body(self) -> str:
        return "\n".join(self.lines)


def _guid(i: int) -> str:
    """Kurze, stabile Kennung (22 Zeichen) aus einer Zahl."""
    zeichen = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"
    v = i + 1
    s = ""
    while v:
        s = zeichen[v % 64] + s
        v //= 64
    return s.rjust(22, "0")


def write_ifc(model: Model, path: str, results=None, log: list = None, **_) -> str:
    s = _Step()
    person = s.add("IFCPERSON($,'Statik3D',$,$,$,$,$,$)")
    org = s.add("IFCORGANIZATION($,'Statik3D',$,$,$)")
    pao = s.add(f"IFCPERSONANDORGANIZATION({person},{org},$)")
    app = s.add(f"IFCAPPLICATION({org},'2.1','Statik3D','STATIK3D')")
    owner = s.add(f"IFCOWNERHISTORY({pao},{app},$,.ADDED.,$,$,$,"
                  f"{int(datetime.now().timestamp())})")
    m_len = s.add("IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)")
    m_area = s.add("IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)")
    m_vol = s.add("IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.)")
    m_force = s.add("IFCSIUNIT(*,.FORCEUNIT.,.KILO.,.NEWTON.)")
    m_ang = s.add("IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.)")
    units = s.add(f"IFCUNITASSIGNMENT(({m_len},{m_area},{m_vol},{m_force},{m_ang}))")
    d3 = s.add("IFCDIRECTION((0.,0.,1.))")
    d1 = s.add("IFCDIRECTION((1.,0.,0.))")
    p0 = s.add("IFCCARTESIANPOINT((0.,0.,0.))")
    ax = s.add(f"IFCAXIS2PLACEMENT3D({p0},{d3},{d1})")
    ctx = s.add(f"IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-5,{ax},$)")
    proj = s.add(f"IFCPROJECT('{_guid(1)}',{owner},"
                 f"'{model.meta.get('projekt') or model.name}',$,$,$,$,({ctx}),{units})")
    site_pl = s.add(f"IFCLOCALPLACEMENT($,{ax})")
    site = s.add(f"IFCSITE('{_guid(2)}',{owner},'Baugrund',$,$,{site_pl},$,$,"
                 ".ELEMENT.,$,$,$,$,$)")
    s.add(f"IFCRELAGGREGATES('{_guid(3)}',{owner},$,$,{proj},({site}))")
    modell = s.add(f"IFCSTRUCTURALANALYSISMODEL('{_guid(4)}',{owner},'{model.name}',"
                   f"$,$,.LOADING_3D.,$,$,$,$)")

    knoten = {}
    for i, p in enumerate(model.nodes):
        pt = s.add(f"IFCCARTESIANPOINT(({p[0]:.6f},{p[1]:.6f},{p[2]:.6f}))")
        ap = s.add(f"IFCAXIS2PLACEMENT3D({pt},$,$)")
        pl = s.add(f"IFCLOCALPLACEMENT($,{ap})")
        vp = s.add(f"IFCVERTEXPOINT({pt})")
        tp = s.add(f"IFCTOPOLOGYREPRESENTATION({ctx},'Reference','Vertex',({vp}))")
        pr = s.add(f"IFCPRODUCTDEFINITIONSHAPE($,$,({tp}))")
        knoten[i] = s.add(f"IFCSTRUCTURALPOINTCONNECTION('{_guid(100 + i)}',{owner},"
                          f"'N{i + 1}',$,$,{pl},{pr},$,$)")

    mitglieder = []
    for k, (name, elems) in enumerate(C.member_chains(model)):
        na, nb = C.chain_ends(model, elems)
        pa = model.nodes[na]
        pb = model.nodes[nb]
        c1 = s.add(f"IFCCARTESIANPOINT(({pa[0]:.6f},{pa[1]:.6f},{pa[2]:.6f}))")
        c2 = s.add(f"IFCCARTESIANPOINT(({pb[0]:.6f},{pb[1]:.6f},{pb[2]:.6f}))")
        pl_line = s.add(f"IFCPOLYLINE(({c1},{c2}))")
        sr = s.add(f"IFCSHAPEREPRESENTATION({ctx},'Axis','Curve3D',({pl_line}))")
        pr = s.add(f"IFCPRODUCTDEFINITIONSHAPE($,$,({sr}))")
        ap = s.add(f"IFCAXIS2PLACEMENT3D({c1},$,$)")
        lp = s.add(f"IFCLOCALPLACEMENT($,{ap})")
        e = model.elements[elems[0]]
        cm = s.add(f"IFCSTRUCTURALCURVEMEMBER('{_guid(5000 + k)}',{owner},'{name}',"
                   f"'{e.sec or ''}',$,{lp},{pr},.RIGID_JOINED_MEMBER.,"
                   f"IFCDIRECTION((0.,0.,1.)))")
        mitglieder.append(cm)

    for k, i in enumerate(C.shell_elements(model)):
        e = model.elements[i]
        pts = [s.add("IFCCARTESIANPOINT((%.6f,%.6f,%.6f))" % tuple(model.nodes[int(n)]))
               for n in e.nodes]
        loop = s.add(f"IFCPOLYLOOP(({','.join(pts)}))")
        face = s.add(f"IFCFACEOUTERBOUND({loop},.T.)")
        fc = s.add(f"IFCFACE(({face}))")
        fbs = s.add(f"IFCFACEBASEDSURFACEMODEL(({s.add(f'IFCCONNECTEDFACESET(({fc}))')}))")
        sr = s.add(f"IFCSHAPEREPRESENTATION({ctx},'Body','SurfaceModel',({fbs}))")
        pr = s.add(f"IFCPRODUCTDEFINITIONSHAPE($,$,({sr}))")
        t = model.shells[e.sec].t if e.sec in model.shells else 0.010
        sm = s.add(f"IFCSTRUCTURALSURFACEMEMBER('{_guid(20000 + k)}',{owner},"
                   f"'S{i + 1}',$,$,$,{pr},.SHELL.,{t:.6f})")
        mitglieder.append(sm)

    for k, sup in enumerate(model.supports):
        b = [sup.dof_behaviour(d) for d in range(6)]
        def w(x):
            return ".T." if x.typ == "rigid" else (f"{x.stiffness:.6g}"
                                                   if x.typ == "spring" else ".F.")
        cond = s.add("IFCBOUNDARYNODECONDITION('%s',%s,%s,%s,%s,%s,%s)"
                     % (sup.name or f"Lager{k + 1}", w(b[0]), w(b[1]), w(b[2]),
                        w(b[3]), w(b[4]), w(b[5])))
        s.add(f"IFCRELCONNECTSSTRUCTURALMEMBER('{_guid(30000 + k)}',{owner},$,$,"
              f"{mitglieder[0] if mitglieder else knoten[0]},{knoten[sup.node]},"
              f"{cond},$,$,$)")

    for k, (name, lc) in enumerate(model.load_cases.items()):
        grp = s.add(f"IFCSTRUCTURALLOADGROUP('{_guid(40000 + k)}',{owner},'{name}',"
                    f"'{lc.description}',$,.LOAD_CASE.,.LIVE_LOAD_A.,"
                    f".NOTDEFINED.,$,$)")
        for j, l in enumerate(lc.nodal_loads):
            F = [float(v) for v in l.F]
            last = s.add(f"IFCSTRUCTURALLOADSINGLEFORCE('{name}',{F[0]:.6g},"
                         f"{F[1]:.6g},{F[2]:.6g},{F[3]:.6g},{F[4]:.6g},{F[5]:.6g})")
            s.add(f"IFCSTRUCTURALPOINTACTION('{_guid(50000 + k * 1000 + j)}',{owner},"
                  f"'{name}-{j + 1}',$,$,$,$,{last},$,.T.,$,$)")
        s.add(f"IFCRELASSIGNSTOGROUP('{_guid(60000 + k)}',{owner},$,$,({modell}),"
              f"$,{grp})")

    if mitglieder:
        s.add(f"IFCRELASSIGNSTOGROUP('{_guid(70000)}',{owner},$,$,"
              f"({','.join(mitglieder)}),$,{modell})")

    kopf = ("ISO-10303-21;\nHEADER;\n"
            f"FILE_DESCRIPTION(('ViewDefinition [StructuralAnalysisView]'),'2;1');\n"
            f"FILE_NAME('{path}','{datetime.now().isoformat(timespec='seconds')}',"
            f"('Statik3D'),('Statik3D'),'Statik3D 2.1','Statik3D','');\n"
            "FILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(kopf + s.body() + "\nENDSEC;\nEND-ISO-10303-21;\n")
    C.say(log, f"IFC geschrieben: {len(mitglieder)} Bauteile, {model.nn} Knoten "
               f"-> {path}")
    return path
