"""
Export als IFC 4 Statikmodell (Structural Analysis View), STEP-Datei.

Geschrieben werden IfcStructuralAnalysisModel mit IfcStructuralPointConnection
(Knoten, Lager als AppliedCondition), IfcStructuralCurveMember (Staebe mit
Werkstoff und Profil als IfcMaterialProfileSet, Stabendgelenke als
AppliedCondition des Anschlusses), IfcStructuralSurfaceMember (Schalen mit
Werkstoff und Dicke), IfcStructuralLoadCase (Lastfaelle mit Eigengewicht)
samt IfcStructuralPointAction, IfcStructuralCurveAction und
IfcStructuralSurfaceAction sowie die Kombinationen.

Lage (Befund B2 der Pruefagenten, 09.11.2026): alle Koordinaten stehen in
Weltkoordinaten, und jedes Objekt haengt an *einer* Platzierung im Ursprung.
Bis dahin trug jeder Knoten und jeder Stab seine Lage zweimal - als Punkt und
noch einmal als eigene Platzierung -, und ein Programm, das die Platzierung
anwendet (auch der eigene Import), bekam jeden Punkt an doppelter Stelle.
Kraefte stehen in N; bis dahin nannte der Kopf kN bei Werten in N.

Was IFC hier nicht traegt, steht nach dem Export als Hinweis mit Anzahl im
Protokoll (:func:`_common.nicht_uebertragen`).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from ..model import Model
from ..elements.beam3d import local_axes
from . import _common as C
from .. import elemente as EL


class _Step:
    """Sammelt STEP-Zeilen und vergibt die Nummern."""

    def __init__(self):
        self.lines: list[str] = []
        self.n = 0
        self.kennung = 0

    def add(self, text: str) -> str:
        self.n += 1
        self.lines.append(f"#{self.n}={text};")
        return f"#{self.n}"

    def guid(self) -> str:
        self.kennung += 1
        return "'" + _guid(self.kennung) + "'"

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


def _r(x) -> str:
    """Zahl als STEP-REAL mit voller Genauigkeit (immer mit Dezimalpunkt)."""
    t = repr(float(x))
    if "e" in t:
        m, e = t.split("e")
        t = (m if "." in m else m + ".") + "E" + e
    return t


def _s(text) -> str:
    """Zeichenkette als STEP-STRING: Hochkomma verdoppelt, alles ausserhalb
    von ASCII als \\X2\\....\\X0\\ (ISO 10303-21)."""
    aus = []
    for ch in str(text or ""):
        if ch == "'":
            aus.append("''")
        elif ch == "\\":
            aus.append("\\\\")
        elif 32 <= ord(ch) < 127:
            aus.append(ch)
        else:
            aus.append("\\X2\\" + ch.encode("utf-16-be").hex().upper() + "\\X0\\")
    return "'" + "".join(aus) + "'"


def _pt(s: _Step, p) -> str:
    return s.add(f"IFCCARTESIANPOINT(({_r(p[0])},{_r(p[1])},{_r(p[2])}))")


#: Lastfallkategorie -> (IfcActionTypeEnum, IfcActionSourceTypeEnum)
_KATEGORIE = {"G": ("PERMANENT_G", "DEAD_LOAD_G"), "Q": ("VARIABLE_Q", "LIVE_LOAD_Q"),
              "S": ("VARIABLE_Q", "SNOW_S"), "W": ("VARIABLE_Q", "WIND_W"),
              "T": ("VARIABLE_Q", "TEMPERATURE_T"), "P": ("PERMANENT_G", "PRESTRESSING_P"),
              "A": ("EXTRAORDINARY_A", "NOTDEFINED"), "SET": ("PERMANENT_G", "SETTLEMENT_U")}

#: Kombinationsart -> Text im Feld Purpose (der eigene Import liest ihn so)
_ZWECK = {"ULS": "ULS", "EQU": "ULS EQU", "ACC": "ACC", "SLS_CH": "SLS CHARACTERISTIC",
          "SLS_FR": "SLS FREQUENT", "SLS_QP": "SLS QUASI-PERMANENT"}


def _gelenk(e, ende: int) -> list[int]:
    """Freigegebene lokale FHG 0..5 am Stabende ``ende`` (0 Anfang, 1 Ende)."""
    return sorted({int(d) % 6 for d in (getattr(e, "hinges", None) or [])
                   if int(d) // 6 == ende})


def _gelenkfeder(e, ende: int) -> int:
    return sum(1 for x in (getattr(e, "hinge_springs", None) or []) if int(x[0]) // 6 == ende)


def _lastmerkmal(model: Model) -> tuple[dict, int, int]:
    """Je Element die vollen, gleichmaessigen Stablasten aller Lastfaelle als
    vergleichbares Merkmal - und die Zahl der Stablasten, die so nicht
    darstellbar sind (trapezfoermig oder auf einem Teilstueck), und die Zahl
    der Stablasten je Projektion, die in die gleichwertige Last je wahrer
    Stablaenge umgerechnet wurden.

    Eine globale Last „je Projektion“ (``bl.bezugslaenge``) geht als Last je
    wahrer Laenge hinaus (.TRUE_LENGTH.): q_wahr = q_proj * L_proj / L mit dem
    Faktor aus :func:`assemble.projektionsfaktor`, beide Endwerte mit
    demselben Faktor, Richtung unveraendert. So bleibt die Gesamtkraft gleich;
    bis zum 11.11.2026 ging der Wert je Projektion unveraendert als Last je
    wahrer Laenge hinaus (am Stab unter 45 Grad 41 % zu viel)."""
    from ..assemble import projektionsfaktor
    merk: dict[int, list] = {}
    rest = umgerechnet = 0
    for name, lc in model.load_cases.items():
        for bl in lc.beam_loads:
            q = [float(v) for v in bl.q]
            q2 = None if bl.q2 is None else [float(v) for v in bl.q2]
            if bl.system == "global" and getattr(bl, "bezugslaenge", "") == "projektion":
                e = model.elements[int(bl.elem)]
                T3, _L = local_axes(model.nodes[int(e.nodes[0])], model.nodes[int(e.nodes[1])],
                                    float(e.roll or 0.0))
                f = projektionsfaktor(T3[0], q if np.any(q) else (q2 or q))
                q = [f * v for v in q]
                q2 = None if q2 is None else [f * v for v in q2]
                umgerechnet += 1
            # gleichmaessig heisst: Anfangs- und Endwert stimmen bis auf das
            # Rundungsrauschen der Netzteilung ueberein (2000 und
            # 2000,0000000000002 sind dieselbe Last)
            gleich = q2 is None or np.allclose(np.asarray(q2, float), q,
                                               rtol=1e-9, atol=0.0)
            if gleich and not bl.teilweise:
                q = [float(f"{v:.12g}") for v in q]
                merk.setdefault(int(bl.elem), []).append((name, bl.system, tuple(q)))
            else:
                rest += 1
    return {e: tuple(sorted(v)) for e, v in merk.items()}, rest, umgerechnet


def _stuecke(model: Model, merk: dict) -> tuple[list, int]:
    """Die Staebe als gerade, einheitliche Stuecke [(Name, Elemente)]: IFC
    kennt je Stab einen Werkstoff, ein Profil, eine Verdrehung, Gelenke nur an
    den Enden und eine Streckenlast ueber die ganze Laenge. Wo sich daran etwas
    aendert, beginnt ein neues Stueck. Rueckgabe dazu: Zahl der geteilten
    Staebe."""
    def passt(a: int, b: int) -> bool:
        ea, eb = model.elements[a], model.elements[b]
        if int(ea.nodes[1]) != int(eb.nodes[0]):
            return False
        if (ea.typ, ea.mat, ea.sec) != (eb.typ, eb.mat, eb.sec):
            return False
        if abs(float(ea.roll or 0.0) - float(eb.roll or 0.0)) > 1e-12:
            return False
        if _gelenk(ea, 1) or _gelenk(eb, 0) or _gelenkfeder(ea, 1) or _gelenkfeder(eb, 0):
            return False
        if merk.get(a, ()) != merk.get(b, ()):
            return False
        da = model.nodes[int(ea.nodes[1])] - model.nodes[int(ea.nodes[0])]
        db = model.nodes[int(eb.nodes[1])] - model.nodes[int(eb.nodes[0])]
        knick = np.linalg.norm(np.cross(da, db)) / (np.linalg.norm(da) * np.linalg.norm(db))
        return bool(knick < 1e-9 and np.dot(da, db) > 0)

    def teile(folge: list[int]) -> list[list[int]]:
        st = [[folge[0]]]
        for a, b in zip(folge[:-1], folge[1:]):
            if passt(a, b):
                st[-1].append(b)
            else:
                st.append([b])
        return st

    aus = []
    geteilt = 0
    for name, elems in C.member_chains(model):
        elems = [i for i in elems if model.elements[i].typ in ("beam", "truss", "seil")]
        if not elems:
            continue
        st = teile(elems)
        if len(st) > 1:
            rueck = teile(elems[::-1])
            if len(rueck) < len(st):
                st = rueck
        if len(st) == 1:
            aus.append((name, st[0]))
        else:
            geteilt += 1
            aus.extend((f"{name}.{k + 1}", teil) for k, teil in enumerate(st))
    return aus, geteilt


def _mit_massen(sec) -> bool:
    """Geht der Querschnitt mit seinen Massen (parametrisch) hinaus?"""
    h, b, tw, tf = (float(getattr(sec, k, 0.0) or 0.0) for k in ("h", "b", "tw", "tf"))
    if getattr(sec, "parts", None):
        return False
    return ((sec.typ == "I" and min(h, b, tw, tf) > 0)
            or (sec.typ == "RHS" and min(h, b, tw) > 0)
            or (sec.typ == "CHS" and min(h, tw) > 0)
            or (sec.typ == "rect" and min(h, b) > 0)
            or (sec.typ == "circle" and h > 0))


def _profil(s: _Step, sec) -> str:
    """Profil eines Querschnitts: parametrisch, wo die Masse vorliegen, sonst
    nur mit Namen. Die Querschnittswerte des Modells stehen in jedem Fall
    daneben (Pset_ProfileMechanical); der eigene Import nimmt sie vor den aus
    den Massen berechneten."""
    n = _s(sec.name)
    h, b, tw, tf, r = (float(getattr(sec, k, 0.0) or 0.0) for k in ("h", "b", "tw", "tf", "r"))
    if not _mit_massen(sec):
        pd = s.add(f"IFCPROFILEDEF(.AREA.,{n})")
    elif sec.typ == "I":
        pd = s.add(f"IFCISHAPEPROFILEDEF(.AREA.,{n},$,{_r(b)},{_r(h)},{_r(tw)},{_r(tf)},"
                   f"{_r(r) if r > 0 else '$'},$,$)")
    elif sec.typ == "RHS":
        # Section.r ist beim Hohlprofil der innere Eckradius; der aeussere
        # steht nicht im Modell und bleibt offen
        pd = s.add(f"IFCRECTANGLEHOLLOWPROFILEDEF(.AREA.,{n},$,{_r(b)},{_r(h)},{_r(tw)},"
                   f"{_r(r)},$)")
    elif sec.typ == "CHS":
        pd = s.add(f"IFCCIRCLEHOLLOWPROFILEDEF(.AREA.,{n},$,{_r(h / 2)},{_r(tw)})")
    elif sec.typ == "rect":
        pd = s.add(f"IFCRECTANGLEPROFILEDEF(.AREA.,{n},$,{_r(b)},{_r(h)})")
    else:
        pd = s.add(f"IFCCIRCLEPROFILEDEF(.AREA.,{n},$,{_r(h / 2)})")
    werte = [("CrossSectionArea", "IFCAREAMEASURE", sec.A),
             ("MomentOfInertiaY", "IFCMOMENTOFINERTIAMEASURE", sec.Iy),
             ("MomentOfInertiaZ", "IFCMOMENTOFINERTIAMEASURE", sec.Iz),
             ("TorsionalConstantX", "IFCMOMENTOFINERTIAMEASURE", sec.It),
             ("ShearDeformationAreaY", "IFCAREAMEASURE", sec.Asy),
             ("ShearDeformationAreaZ", "IFCAREAMEASURE", sec.Asz),
             ("WarpingConstant", "IFCWARPINGCONSTANTMEASURE", sec.Iw),
             ("MinimumSectionModulusY", "IFCSECTIONMODULUSMEASURE",
              sec.Iy / sec.zmax if sec.zmax else 0.0),
             ("MinimumSectionModulusZ", "IFCSECTIONMODULUSMEASURE",
              sec.Iz / sec.ymax if sec.ymax else 0.0)]
    props = [s.add(f"IFCPROPERTYSINGLEVALUE('{k}',$,{typ}({_r(v or 0.0)}),$)")
             for k, typ, v in werte]
    s.add(f"IFCPROFILEPROPERTIES('Pset_ProfileMechanical',$,({','.join(props)}),{pd})")
    return pd


def _werkstoff(s: _Step, mat) -> str:
    m = s.add(f"IFCMATERIAL({_s(mat.name)},$,'Steel')")
    mech = [s.add(f"IFCPROPERTYSINGLEVALUE('YoungModulus',$,"
                  f"IFCMODULUSOFELASTICITYMEASURE({_r(mat.E)}),$)"),
            s.add(f"IFCPROPERTYSINGLEVALUE('PoissonRatio',$,"
                  f"IFCPOSITIVERATIOMEASURE({_r(mat.nu)}),$)"),
            s.add(f"IFCPROPERTYSINGLEVALUE('ThermalExpansionCoefficient',$,"
                  f"IFCTHERMALEXPANSIONCOEFFICIENTMEASURE({_r(mat.alpha)}),$)")]
    s.add(f"IFCMATERIALPROPERTIES('Pset_MaterialMechanical',$,({','.join(mech)}),{m})")
    dichte = s.add(f"IFCPROPERTYSINGLEVALUE('MassDensity',$,"
                   f"IFCMASSDENSITYMEASURE({_r(mat.rho)}),$)")
    s.add(f"IFCMATERIALPROPERTIES('Pset_MaterialCommon',$,({dichte}),{m})")
    stahl = [s.add(f"IFCPROPERTYSINGLEVALUE('{k}',$,IFCPRESSUREMEASURE({_r(v)}),$)")
             for k, v in (("YieldStress", mat.fy), ("UltimateStress", mat.fu)) if v]
    if stahl:
        s.add(f"IFCMATERIALPROPERTIES('Pset_MaterialSteel',$,({','.join(stahl)}),{m})")
    return m


def write_ifc(model: Model, path: str, results=None, log: list = None, **_) -> str:
    s = _Step()
    person = s.add("IFCPERSON($,'Statik3D',$,$,$,$,$,$)")
    org = s.add("IFCORGANIZATION($,'Statik3D',$,$,$)")
    pao = s.add(f"IFCPERSONANDORGANIZATION({person},{org},$)")
    app = s.add(f"IFCAPPLICATION({org},'2.1','Statik3D','STATIK3D')")
    owner = s.add(f"IFCOWNERHISTORY({pao},{app},$,.ADDED.,$,$,$,"
                  f"{int(datetime.now().timestamp())})")
    einheiten = [s.add("IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)"),
                 s.add("IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)"),
                 s.add("IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.)"),
                 # die Werte stehen in N (bis 09.11.2026 nannte der Kopf kN)
                 s.add("IFCSIUNIT(*,.FORCEUNIT.,$,.NEWTON.)"),
                 s.add("IFCSIUNIT(*,.PRESSUREUNIT.,$,.PASCAL.)"),
                 s.add("IFCSIUNIT(*,.MASSUNIT.,.KILO.,.GRAM.)"),
                 s.add("IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.)")]
    units = s.add(f"IFCUNITASSIGNMENT(({','.join(einheiten)}))")
    d3 = s.add("IFCDIRECTION((0.,0.,1.))")
    d1 = s.add("IFCDIRECTION((1.,0.,0.))")
    p0 = s.add("IFCCARTESIANPOINT((0.,0.,0.))")
    ax = s.add(f"IFCAXIS2PLACEMENT3D({p0},{d3},{d1})")
    ctx = s.add(f"IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-5,{ax},$)")
    proj = s.add(f"IFCPROJECT({s.guid()},{owner},"
                 f"{_s(model.meta.get('projekt') or model.name)},$,$,$,$,({ctx}),{units})")
    # die eine Platzierung aller Objekte: der Ursprung. Die Punkte selbst
    # stehen in Weltkoordinaten.
    lp0 = s.add(f"IFCLOCALPLACEMENT($,{ax})")
    site = s.add(f"IFCSITE({s.guid()},{owner},'Baugrund',$,$,{lp0},$,$,"
                 ".ELEMENT.,$,$,$,$,$)")
    s.add(f"IFCRELAGGREGATES({s.guid()},{owner},$,$,{proj},({site}))")

    def wert(b, drehung: bool) -> str:
        if b[0] == "rigid":
            return "IFCBOOLEAN(.T.)"
        if b[0] == "spring" and b[1] > 0:
            return (f"IFCROTATIONALSTIFFNESSMEASURE({_r(b[1])})" if drehung
                    else f"IFCLINEARSTIFFNESSMEASURE({_r(b[1])})")
        return "IFCBOOLEAN(.F.)"

    # ---- Lager je Knoten ------------------------------------------------
    lager: dict[int, list] = {}
    namen: dict[int, str] = {}
    for k, sup in enumerate(model.supports):
        zeile = lager.setdefault(int(sup.node), [("free", 0.0)] * 6)
        namen.setdefault(int(sup.node), sup.name or f"Lager{k + 1}")
        for d in range(6):
            b = sup.dof_behaviour(d)
            if b.typ == "rigid" or (b.typ == "spring" and zeile[d][0] == "free"):
                zeile[d] = (b.typ, float(b.stiffness or 0.0))

    # ---- Knoten ---------------------------------------------------------
    knoten = {}
    produkte = []
    for i, p in enumerate(model.nodes):
        vp = s.add(f"IFCVERTEXPOINT({_pt(s, p)})")
        tp = s.add(f"IFCTOPOLOGYREPRESENTATION({ctx},'Reference','Vertex',({vp}))")
        pr = s.add(f"IFCPRODUCTDEFINITIONSHAPE($,$,({tp}))")
        cond = "$"
        if i in lager:
            z = lager[i]
            cond = s.add(f"IFCBOUNDARYNODECONDITION({_s(namen[i])},"
                         + ",".join(wert(z[d], d >= 3) for d in range(6)) + ")")
        knoten[i] = s.add(f"IFCSTRUCTURALPOINTCONNECTION({s.guid()},{owner},"
                          f"'N{i + 1}',$,$,{lp0},{pr},{cond},$)")
        produkte.append(knoten[i])

    # ---- Werkstoffe und Profile ----------------------------------------
    werkstoff: dict[str, str] = {}
    profilsatz: dict[tuple, str] = {}

    def werkstoff_von(name: str):
        if name not in werkstoff:
            werkstoff[name] = _werkstoff(s, model.materials[name]) \
                if name in model.materials else None
        return werkstoff[name]

    def profilsatz_von(mat: str, sec: str):
        key = (mat, sec)
        if key not in profilsatz:
            m = werkstoff_von(mat)
            pd = _profil(s, model.sections[sec]) if sec in model.sections else None
            if m is None and pd is None:
                profilsatz[key] = None
            else:
                mp = s.add(f"IFCMATERIALPROFILE({_s(sec)},$,{m or '$'},{pd or '$'},$,$)")
                profilsatz[key] = s.add(f"IFCMATERIALPROFILESET({_s(sec)},$,({mp}),$)")
        return profilsatz[key]

    # ---- Staebe ----------------------------------------------------------
    merk, n_stablast_rest, n_projektion = _lastmerkmal(model)
    stuecke, n_geteilt = _stuecke(model, merk)
    stab_von: dict[int, str] = {}          # erstes Element des Stuecks -> Stab
    zuordnung: dict[str, list] = {}        # Profilsatz/Werkstoff -> Objekte
    n_feder = 0
    for name, elems in stuecke:
        e0, e1 = model.elements[elems[0]], model.elements[elems[-1]]
        kette = [int(model.elements[i].nodes[0]) for i in elems] + [int(e1.nodes[1])]
        pl_line = s.add("IFCPOLYLINE((" + ",".join(_pt(s, model.nodes[n]) for n in kette) + "))")
        sr = s.add(f"IFCSHAPEREPRESENTATION({ctx},'Axis','Curve3D',({pl_line}))")
        pr = s.add(f"IFCPRODUCTDEFINITIONSHAPE($,$,({sr}))")
        T3, _L = local_axes(model.nodes[kette[0]], model.nodes[kette[1]], float(e0.roll or 0.0))
        ez = T3[2]
        achse = s.add(f"IFCDIRECTION(({_r(ez[0])},{_r(ez[1])},{_r(ez[2])}))")
        art = {"truss": "PIN_JOINED_MEMBER", "seil": "CABLE"}.get(e0.typ, "RIGID_JOINED_MEMBER")
        cm = s.add(f"IFCSTRUCTURALCURVEMEMBER({s.guid()},{owner},{_s(name)},"
                   f"{_s(e0.sec or '')},$,{lp0},{pr},.{art}.,{achse})")
        produkte.append(cm)
        for i in elems:
            stab_von[i] = cm
        satz = profilsatz_von(e0.mat, e0.sec)
        if satz:
            zuordnung.setdefault(satz, []).append(cm)
        # Anschluesse an die Knoten; an den Enden mit dem Gelenk
        for lage, n in enumerate(kette):
            cond = "$"
            ende = 0 if lage == 0 else (1 if lage == len(kette) - 1 else None)
            if ende is not None:
                e = e0 if ende == 0 else e1
                frei = _gelenk(e, ende)
                n_feder += _gelenkfeder(e, ende)
                if frei and e.typ == "beam":
                    cond = s.add("IFCBOUNDARYNODECONDITION('Gelenk',"
                                 + ",".join("IFCBOOLEAN(.F.)" if d in frei else "IFCBOOLEAN(.T.)"
                                            for d in range(6)) + ")")
            s.add(f"IFCRELCONNECTSSTRUCTURALMEMBER({s.guid()},{owner},$,$,{cm},"
                  f"{knoten[n]},{cond},$,$,$)")

    # ---- Schalen -----------------------------------------------------------
    flaeche_von: dict[int, str] = {}
    n_quad = 0
    for i in C.shell_elements(model):
        e = model.elements[i]
        ecken = 3 if e.typ in ("shell3", "shell6") else 4
        n_quad += 1 if len(e.nodes) > ecken else 0
        pts = [_pt(s, model.nodes[int(n)]) for n in e.nodes[:ecken]]
        loop = s.add(f"IFCPOLYLOOP(({','.join(pts)}))")
        face = s.add(f"IFCFACEOUTERBOUND({loop},.T.)")
        fc = s.add(f"IFCFACE(({face}))")
        fbs = s.add(f"IFCFACEBASEDSURFACEMODEL(({s.add(f'IFCCONNECTEDFACESET(({fc}))')}))")
        sr = s.add(f"IFCSHAPEREPRESENTATION({ctx},'Body','SurfaceModel',({fbs}))")
        pr = s.add(f"IFCPRODUCTDEFINITIONSHAPE($,$,({sr}))")
        t = model.shells[e.sec].t if e.sec in model.shells else None
        sm = s.add(f"IFCSTRUCTURALSURFACEMEMBER({s.guid()},{owner},"
                   f"'S{i + 1}',$,$,{lp0},{pr},.SHELL.,{_r(t) if t else '$'})")
        produkte.append(sm)
        flaeche_von[i] = sm
        m = werkstoff_von(e.mat)
        if m:
            zuordnung.setdefault(m, []).append(sm)

    for ziel, objekte in zuordnung.items():
        s.add(f"IFCRELASSOCIATESMATERIAL({s.guid()},{owner},$,$,({','.join(objekte)}),{ziel})")

    # ---- Lastfaelle und Lasten ------------------------------------------
    gruppen: dict[str, str] = {}
    n_kat = n_flaechenlast_rest = 0
    for name, lc in model.load_cases.items():
        typ, quelle = _KATEGORIE.get(str(lc.category or "").upper(), (None, None))
        if typ is None:
            typ, quelle = "VARIABLE_Q", "NOTDEFINED"
            n_kat += 1
        g = np.asarray(lc.gravity, float).ravel()
        eigen = "(" + ",".join(_r(v / 9.81) for v in g[:3]) + ")" if np.any(g) else "$"
        grp = s.add(f"IFCSTRUCTURALLOADCASE({s.guid()},{owner},{_s(name)},"
                    f"{_s(lc.description)},$,.LOAD_CASE.,.{typ}.,.{quelle}.,1.,$,{eigen})")
        gruppen[name] = grp
        lasten = []
        for l in lc.nodal_loads:
            F = [float(v) for v in l.F] + [0.0] * 6
            last = s.add("IFCSTRUCTURALLOADSINGLEFORCE($," + ",".join(_r(v) for v in F[:6]) + ")")
            act = s.add(f"IFCSTRUCTURALPOINTACTION({s.guid()},{owner},{_s(name)},$,$,{lp0},$,"
                        f"{last},.GLOBAL_COORDS.,$)")
            s.add(f"IFCRELCONNECTSSTRUCTURALACTIVITY({s.guid()},{owner},$,$,"
                  f"{knoten[int(l.node)]},{act})")
            lasten.append(act)
        # Streckenlasten: je Stueck einmal (alle Elemente des Stuecks tragen
        # dieselbe Last, dafuer sorgt die Teilung)
        for _n, elems in stuecke:
            for lf, system, q in merk.get(elems[0], ()):
                if lf != name:
                    continue
                last = s.add("IFCSTRUCTURALLOADLINEARFORCE($," + ",".join(_r(v) for v in q)
                             + ",0.,0.,0.)")
                koord = "LOCAL_COORDS" if system == "local" else "GLOBAL_COORDS"
                act = s.add(f"IFCSTRUCTURALCURVEACTION({s.guid()},{owner},{_s(name)},$,$,{lp0},$,"
                            f"{last},.{koord}.,$,.TRUE_LENGTH.,.CONST.)")
                s.add(f"IFCRELCONNECTSSTRUCTURALACTIVITY({s.guid()},{owner},$,$,"
                      f"{stab_von[elems[0]]},{act})")
                lasten.append(act)
        for fl in lc.face_loads:
            if int(fl.elem) not in flaeche_von:
                n_flaechenlast_rest += 1
                continue
            if fl.direction is not None:
                d = np.asarray(fl.direction, float)
                d = d / (np.linalg.norm(d) or 1.0)
                F, koord = [float(fl.p) * float(v) for v in d], "GLOBAL_COORDS"
            else:
                F, koord = [0.0, 0.0, float(fl.p)], "LOCAL_COORDS"
            last = s.add("IFCSTRUCTURALLOADPLANARFORCE($," + ",".join(_r(v) for v in F) + ")")
            act = s.add(f"IFCSTRUCTURALSURFACEACTION({s.guid()},{owner},{_s(name)},$,$,{lp0},$,"
                        f"{last},.{koord}.,$,.TRUE_LENGTH.,.CONST.)")
            s.add(f"IFCRELCONNECTSSTRUCTURALACTIVITY({s.guid()},{owner},$,$,"
                  f"{flaeche_von[int(fl.elem)]},{act})")
            lasten.append(act)
        if lasten:
            s.add(f"IFCRELASSIGNSTOGROUP({s.guid()},{owner},$,$,({','.join(lasten)}),$,{grp})")

    # ---- Kombinationen ---------------------------------------------------
    n_ek = n_komb = 0
    for name, c in model.combinations.items():
        faktoren = {k: float(v) for k, v in c.factors.items() if k in gruppen}
        if getattr(c, "alternativen", None) or not faktoren:
            n_ek += 1
            continue
        grp = s.add(f"IFCSTRUCTURALLOADGROUP({s.guid()},{owner},{_s(name)},"
                    f"{_s(c.description)},$,.LOAD_COMBINATION.,.NOTDEFINED.,.NOTDEFINED.,"
                    f"1.,{_s(_ZWECK.get(c.typ, c.typ))})")
        gruppen["\0" + name] = grp
        n_komb += 1
        for lf, f in faktoren.items():
            s.add(f"IFCRELASSIGNSTOGROUPBYFACTOR({s.guid()},{owner},$,$,({gruppen[lf]}),$,"
                  f"{grp},{_r(f)})")

    geladen = "(" + ",".join(gruppen.values()) + ")" if gruppen else "$"
    modell = s.add(f"IFCSTRUCTURALANALYSISMODEL({s.guid()},{owner},{_s(model.name)},"
                   f"$,$,.LOADING_3D.,$,{geladen},$,{lp0})")
    if produkte:
        s.add(f"IFCRELASSIGNSTOGROUP({s.guid()},{owner},$,$,({','.join(produkte)}),$,{modell})")
    s.add(f"IFCRELDECLARES({s.guid()},{owner},$,$,{proj},({modell}))")

    kopf = ("ISO-10303-21;\nHEADER;\n"
            f"FILE_DESCRIPTION(('ViewDefinition [StructuralAnalysisView]'),'2;1');\n"
            f"FILE_NAME({_s(path)},'{datetime.now().isoformat(timespec='seconds')}',"
            f"('Statik3D'),('Statik3D'),'Statik3D 2.1','Statik3D','');\n"
            "FILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n")
    with open(path, "w", encoding="ascii", errors="replace") as f:
        f.write(kopf + s.body() + "\nENDSEC;\nEND-ISO-10303-21;\n")

    n_schale = len(flaeche_von)
    C.say(log, f"IFC geschrieben: {len(stuecke)} Stäbe, {n_schale} Schalenelemente, "
               f"{model.nn} Knoten, {len(lager)} Lager, {len(werkstoff)} Werkstoffe, "
               f"{len(model.load_cases)} Lastfälle, {n_komb} Kombinationen -> {path}")
    if n_geteilt:
        C.warn(log, f"IFC: {C.anzahl(n_geteilt, 'Stab wurde', 'Stäbe wurden')} an Gelenken, "
                    "Knicken, Querschnitts- oder Lastwechseln in gerade Stücke geteilt (IFC "
                    "kennt je Stab ein Profil, Gelenke nur an den Enden und eine Streckenlast "
                    "über die ganze Länge). Die Stabzuordnung, etwa für Knicklängen, ist nach "
                    "dem Einlesen zu prüfen.")
    if n_projektion:
        C.warn(log, f"IFC: {C.anzahl(n_projektion, 'Stablast', 'Stablasten')} je Projektion "
                    "(projizierte Länge) in die gleichwertige Last je wahrer Stablänge "
                    "umgerechnet (q · L_Projektion / L, Richtung und Gesamtkraft unverändert); "
                    "nach dem Einlesen gilt sie je Stablänge.")
    n_lager_nl = sum(1 for sup in model.supports
                     if sup.nonlinear or any(float(v) for v in (sup.values or [])))
    n_frei = sum(1 for sec in model.sections.values()
                 if not _mit_massen(sec) and (sec.typ != "free" or sec.parts))
    n_plast = sum(1 for m in model.materials.values()
                  if getattr(m, "verfestigung", None) is not None
                  or getattr(m, "Ep", None) is not None)
    # ebene Elemente (Scheibe, ebener Dehnungszustand, rotationssymmetrisch)
    # und was sonst weder Stab, Schale noch Volumen ist (Befund 17,
    # 11.11.2026: bis dahin fehlten sie ohne ein Wort)
    ohne = [i for i, e in enumerate(model.elements)
            if e.typ not in EL.STAB_TYPEN and not e.typ.startswith("shell")
            and e.typ not in EL.VOLUMEN_TYPEN and not C.von_weiteres(e)]
    C.nicht_uebertragen(log, "IFC", [
        (len(C.solid_elements(model)), "Volumenelement", "Volumenelemente"),
        C.elementhinweis(model, ohne, "ebenes oder sonstiges Element",
                         "ebene oder sonstige Elemente",
                         "(das Statikmodell von IFC führt Stäbe und Schalen; es fehlt ganz)",
                         "(das Statikmodell von IFC führt Stäbe und Schalen; sie fehlen ganz)"),
        (n_quad, "Seitenmittenknoten eines Schalenelements (es geht mit den Eckknoten hinaus)",
         "Schalenelemente mit Seitenmittenknoten (sie gehen mit den Eckknoten hinaus)"),
        (n_frei, "Querschnitt nur mit Fläche, Trägheitsmomenten, Schubflächen, "
                 "Wölbwiderstand und Randabständen (ohne Maße und Teilquerschnitte)",
         "Querschnitte nur mit Fläche, Trägheitsmomenten, Schubflächen, "
         "Wölbwiderstand und Randabständen (ohne Maße und Teilquerschnitte)"),
        (n_plast, "Werkstoffgesetz mit Verfestigung", "Werkstoffgesetze mit Verfestigung"),
        (sum(1 for n in model.materials if werkstoff.get(n) is None),
         "Werkstoff, den kein Stab und keine Schale benutzt",
         "Werkstoffe, die kein Stab und keine Schale benutzt"),
        (sum(1 for n in model.sections if not any(k[1] == n for k in profilsatz)),
         "Querschnitt, den kein Stab benutzt", "Querschnitte, die kein Stab benutzt"),
        (n_feder, "Gelenkfeder", "Gelenkfedern"),
        (n_lager_nl, "Knotenlager mit Ausfall, Schlupf, Reibung, Grenzkraft oder vorgegebener "
                     "Verschiebung (es geht als starres oder gefedertes Lager hinaus)",
         "Knotenlager mit Ausfall, Schlupf, Reibung, Grenzkraft oder vorgegebener "
         "Verschiebung (sie gehen als starre oder gefederte Lager hinaus)"),
        (len(model.line_supports), "Linienlager", "Linienlager"),
        (len(model.surface_supports), "Flächenlager", "Flächenlager"),
        (n_stablast_rest, "Stablast (trapezförmig oder auf einem Teilstück)",
         "Stablasten (trapezförmig oder auf einem Teilstück)"),
        (n_flaechenlast_rest, "Flächenlast auf Volumenelementen",
         "Flächenlasten auf Volumenelementen"),
        (C.lastzahl(model, "temp_loads"), "Temperaturlast", "Temperaturlasten"),
        (n_kat, "Lastfallkategorie ohne Entsprechung in IFC (der Lastfall geht als "
                "veränderliche Einwirkung hinaus)",
         "Lastfallkategorien ohne Entsprechung in IFC (die Lastfälle gehen als "
         "veränderliche Einwirkung hinaus)"),
        (n_ek, "Ergebniskombination oder Kombination ohne Lastfall der Datei",
         "Ergebniskombinationen oder Kombinationen ohne Lastfall der Datei"),
    ] + C.weiteres(model))
    return path
