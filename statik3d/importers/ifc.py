"""
IFC-Import (IFC2X3 / IFC4, STEP Physical File nach ISO 10303-21).

Eigener, abhaengigkeitsfreier Parser:
    ifc = parse_ifc("modell.ifc")          # IfcFile
    ifc.entities[12]                        # IfcEntity (id, type, args)
    ifc.by_type("IfcStructuralCurveMember") # inkl. bekannter Untertypen

Modellaufbau aus der *Structural Analysis View*:
    IfcStructuralPointConnection   -> Knoten (+ AppliedCondition -> Lager)
    IfcStructuralCurveMember       -> Stab (PIN_JOINED/TENSION/COMPRESSION -> Fachwerkstab)
    IfcStructuralSurfaceMember     -> Schalen (Polygon: 3 -> shell3, 4 -> shell4, sonst Faecher)
    IfcStructuralPointAction       -> Knotenlast, IfcStructuralLinearAction -> Streckenlast,
    IfcStructuralPlanarAction      -> Flaechenlast
    IfcStructuralLoadCase/-Group   -> Lastfall (ActionType/ActionSource -> Kategorie),
                                      LOAD_COMBINATION -> Kombination
    Material ueber IfcRelAssociatesMaterial, Profil ueber IfcMaterialProfileSet(-Usage)
    bzw. IfcRelAssociatesProfileProperties (IFC2X3).
Ohne Statikmodell werden IfcBeam/IfcColumn/IfcMember-Achsen aus Achsdarstellung
bzw. IfcExtrudedAreaSolid abgeleitet (nur Stabachsen, mit Hinweis).
Einheiten aus IfcProject.UnitsInContext (SI-Praefixe, Umrechnungseinheiten,
abgeleitete Einheiten); 'unit_scale' ueberschreibt den Laengenmassstab.
"""
from __future__ import annotations

import math
import os
import re
from typing import Optional

import numpy as np

from ..model import Model, Material, Section
from . import _common as C


# ==========================================================================
# STEP-Parser
# ==========================================================================
class Ref:
    """Verweis auf eine Instanz (#12)."""
    __slots__ = ("id",)

    def __init__(self, id_: int):
        self.id = id_

    def __repr__(self):
        return f"#{self.id}"

    def __eq__(self, other):
        return isinstance(other, Ref) and other.id == self.id

    def __hash__(self):
        return hash(("Ref", self.id))


class Enum(str):
    """Aufzaehlungswert (.TRUE. -> 'TRUE')."""


class Typed:
    """Typisierter Wert, z.B. IFCBOOLEAN(.T.) oder IFCLENGTHMEASURE(2.5)."""
    __slots__ = ("type", "value")

    def __init__(self, type_: str, value):
        self.type = type_
        self.value = value

    def __repr__(self):
        return f"{self.type}({self.value!r})"


class IfcEntity:
    __slots__ = ("id", "type", "args", "file")

    def __init__(self, id_: int, type_: str, args: list, file: "IfcFile"):
        self.id = id_
        self.type = type_
        self.args = args
        self.file = file

    def __repr__(self):
        return f"#{self.id}={self.type}({len(self.args)} Attribute)"

    def __getitem__(self, i: int):
        return self.args[i] if 0 <= i < len(self.args) else None

    def ref(self, i: int) -> Optional["IfcEntity"]:
        """Attribut i als Instanz aufloesen (None, wenn kein Verweis)."""
        v = self[i]
        return self.file.resolve(v) if isinstance(v, Ref) else None

    def refs(self, i: int) -> list["IfcEntity"]:
        """Attribut i als Liste von Instanzen."""
        v = self[i]
        if isinstance(v, Ref):
            e = self.file.resolve(v)
            return [e] if e else []
        if isinstance(v, list):
            out = []
            for x in v:
                if isinstance(x, Ref):
                    e = self.file.resolve(x)
                    if e:
                        out.append(e)
            return out
        return []

    def is_a(self, name: str) -> bool:
        return self.file.is_subtype(self.type, name)

    @property
    def name(self) -> str:
        """Name eines IfcRoot-Objekts (GlobalId, OwnerHistory, Name, ...)."""
        v = self[2]
        if isinstance(self[0], str) and isinstance(v, str):
            return v
        return ""


# Untertypen fuer by_type (nur die hier benoetigten Zweige)
_SUBTYPES: dict[str, set[str]] = {
    "IFCSTRUCTURALCURVEMEMBER": {"IFCSTRUCTURALCURVEMEMBERVARYING"},
    "IFCSTRUCTURALSURFACEMEMBER": {"IFCSTRUCTURALSURFACEMEMBERVARYING"},
    "IFCSTRUCTURALMEMBER": {"IFCSTRUCTURALCURVEMEMBER", "IFCSTRUCTURALSURFACEMEMBER"},
    "IFCSTRUCTURALCONNECTION": {"IFCSTRUCTURALPOINTCONNECTION", "IFCSTRUCTURALCURVECONNECTION",
                                "IFCSTRUCTURALSURFACECONNECTION"},
    "IFCSTRUCTURALLINEARACTION": {"IFCSTRUCTURALLINEARACTIONVARYING"},
    "IFCSTRUCTURALCURVEACTION": {"IFCSTRUCTURALLINEARACTION"},
    "IFCSTRUCTURALPLANARACTION": {"IFCSTRUCTURALPLANARACTIONVARYING"},
    "IFCSTRUCTURALSURFACEACTION": {"IFCSTRUCTURALPLANARACTION"},
    "IFCSTRUCTURALACTION": {"IFCSTRUCTURALPOINTACTION", "IFCSTRUCTURALCURVEACTION",
                            "IFCSTRUCTURALSURFACEACTION"},
    "IFCSTRUCTURALACTIVITY": {"IFCSTRUCTURALACTION", "IFCSTRUCTURALREACTION"},
    "IFCSTRUCTURALREACTION": {"IFCSTRUCTURALPOINTREACTION", "IFCSTRUCTURALCURVEREACTION",
                              "IFCSTRUCTURALSURFACEREACTION"},
    "IFCSTRUCTURALLOADGROUP": {"IFCSTRUCTURALLOADCASE"},
    "IFCRELASSIGNSTOGROUP": {"IFCRELASSIGNSTOGROUPBYFACTOR"},
    "IFCBEAM": {"IFCBEAMSTANDARDCASE"},
    "IFCCOLUMN": {"IFCCOLUMNSTANDARDCASE"},
    "IFCMEMBER": {"IFCMEMBERSTANDARDCASE"},
    "IFCPLATE": {"IFCPLATESTANDARDCASE"},
    "IFCSLAB": {"IFCSLABSTANDARDCASE", "IFCSLABELEMENTEDCASE"},
    "IFCWALL": {"IFCWALLSTANDARDCASE", "IFCWALLELEMENTEDCASE"},
    "IFCFACE": {"IFCFACESURFACE", "IFCADVANCEDFACE"},
    "IFCFACEBOUND": {"IFCFACEOUTERBOUND"},
    "IFCEDGE": {"IFCEDGECURVE", "IFCORIENTEDEDGE", "IFCSUBEDGE"},
    "IFCPROFILEPROPERTIES": {"IFCGENERALPROFILEPROPERTIES"},
    "IFCGENERALPROFILEPROPERTIES": {"IFCSTRUCTURALPROFILEPROPERTIES"},
    "IFCSTRUCTURALPROFILEPROPERTIES": {"IFCSTRUCTURALSTEELPROFILEPROPERTIES"},
    "IFCMECHANICALMATERIALPROPERTIES": {"IFCMECHANICALSTEELMATERIALPROPERTIES",
                                        "IFCMECHANICALCONCRETEMATERIALPROPERTIES"},
    "IFCBOUNDARYNODECONDITION": {"IFCBOUNDARYNODECONDITIONWARPING"},
    "IFCSTRUCTURALLOADSINGLEFORCE": {"IFCSTRUCTURALLOADSINGLEFORCEWARPING"},
    "IFCCONNECTEDFACESET": {"IFCCLOSEDSHELL", "IFCOPENSHELL"},
}


def _closure(name: str, seen: set = None) -> set[str]:
    seen = seen if seen is not None else set()
    for sub in _SUBTYPES.get(name, ()):
        if sub not in seen:
            seen.add(sub)
            _closure(sub, seen)
    return seen


_TOKEN = re.compile(r"""
      (?P<ws>\s+)
    | (?P<comment>/\*.*?\*/)
    | (?P<str>'(?:[^']|'')*')
    | (?P<ref>\#\d+)
    | (?P<enum>\.[A-Za-z0-9_]+\.)
    | (?P<num>[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][+-]?\d+)?)
    | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<punct>[\$\*(),;=])
""", re.VERBOSE | re.DOTALL)

_ESC_X2 = re.compile(r"\\X2\\([0-9A-Fa-f]*)\\X0\\")
_ESC_X4 = re.compile(r"\\X4\\([0-9A-Fa-f]*)\\X0\\")
_ESC_X = re.compile(r"\\X\\([0-9A-Fa-f]{2})")
_ESC_S = re.compile(r"\\S\\(.)")
_ESC_P = re.compile(r"\\P[A-Z]\\")


def decode_step_string(s: str) -> str:
    """STEP-Zeichenkette dekodieren ('' -> ', \\X2\\...\\X0\\ -> Unicode)."""
    s = s.replace("''", "'")
    if "\\" not in s:
        return s
    s = _ESC_P.sub("", s)
    s = _ESC_X2.sub(lambda m: bytes.fromhex(m.group(1)).decode("utf-16-be", "replace"), s)
    s = _ESC_X4.sub(lambda m: bytes.fromhex(m.group(1)).decode("utf-32-be", "replace"), s)
    s = _ESC_X.sub(lambda m: chr(int(m.group(1), 16)), s)
    s = _ESC_S.sub(lambda m: chr((ord(m.group(1)) + 128) % 256), s)
    return s


class IfcFile:
    """Geparste IFC-Datei: entities {id: IfcEntity}, schema ('IFC4', 'IFC2X3')."""

    def __init__(self):
        self.schema = ""
        self.header: dict[str, list] = {}
        self.entities: dict[int, IfcEntity] = {}
        self.errors: list[str] = []
        self._index: dict[str, list[IfcEntity]] = {}

    def resolve(self, v):
        if isinstance(v, Ref):
            return self.entities.get(v.id)
        return v

    def get(self, id_: int) -> Optional[IfcEntity]:
        return self.entities.get(id_)

    def is_subtype(self, typ: str, name: str) -> bool:
        name = name.upper()
        return typ == name or typ in _closure(name)

    def by_type(self, name: str, subtypes: bool = True) -> list[IfcEntity]:
        """Alle Instanzen eines Typs (Gross-/Kleinschreibung egal), sortiert nach id."""
        name = name.upper()
        if not self._index:
            for e in self.entities.values():
                self._index.setdefault(e.type, []).append(e)
        out = list(self._index.get(name, []))
        if subtypes:
            for sub in _closure(name):
                out.extend(self._index.get(sub, []))
        out.sort(key=lambda e: e.id)
        return out


class _Parser:
    def __init__(self, text: str, file: IfcFile):
        self.file = file
        self.toks: list[tuple[str, str]] = []
        for m in _TOKEN.finditer(text):
            kind = m.lastgroup
            if kind in ("ws", "comment"):
                continue
            self.toks.append((kind, m.group(kind)))
        self.pos = 0

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else (None, None)

    def next(self):
        t = self.peek()
        self.pos += 1
        return t

    def expect(self, kind: str, val: str = None):
        k, v = self.next()
        if k != kind or (val is not None and v != val):
            raise SyntaxError(f"erwartet {val or kind}, gefunden {v!r}")
        return v

    def skip_statement(self):
        while self.pos < len(self.toks):
            k, v = self.next()
            if k == "punct" and v == ";":
                return

    def parse_value(self):
        k, v = self.next()
        if k == "str":
            return decode_step_string(v[1:-1])
        if k == "ref":
            return Ref(int(v[1:]))
        if k == "enum":
            return Enum(v[1:-1])
        if k == "num":
            if any(ch in v for ch in ".eE"):
                return float(v)
            return int(v)
        if k == "punct":
            if v == "$" or v == "*":
                return None
            if v == "(":
                return self.parse_list_body()
            raise SyntaxError(f"unerwartet {v!r}")
        if k == "ident":
            self.expect("punct", "(")
            inner = self.parse_list_body()
            return Typed(v.upper(), inner[0] if len(inner) == 1 else inner)
        raise SyntaxError("unerwartetes Dateiende")

    def parse_list_body(self) -> list:
        out = []
        k, v = self.peek()
        if k == "punct" and v == ")":
            self.next()
            return out
        while True:
            out.append(self.parse_value())
            k, v = self.next()
            if k == "punct" and v == ",":
                continue
            if k == "punct" and v == ")":
                return out
            raise SyntaxError(f"',' oder ')' erwartet, gefunden {v!r}")

    def parse_data(self):
        toks = self.toks
        n = len(toks)
        while self.pos < n:
            k, v = self.next()
            if k == "ident" and v.upper() == "ENDSEC":
                break
            if k != "ref":
                continue
            id_ = int(v[1:])
            start = self.pos
            try:
                self.expect("punct", "=")
                k2, v2 = self.next()
                if k2 == "punct" and v2 == "(":         # komplexe Instanz
                    self.parse_list_body()
                    self.file.errors.append(f"#{id_}: komplexe Instanz uebersprungen")
                    self.expect("punct", ";")
                    continue
                if k2 != "ident":
                    raise SyntaxError("Typname erwartet")
                self.expect("punct", "(")
                args = self.parse_list_body()
                self.expect("punct", ";")
                self.file.entities[id_] = IfcEntity(id_, v2.upper(), args, self.file)
            except SyntaxError as ex:
                self.file.errors.append(f"#{id_}: {ex}")
                self.pos = start
                self.skip_statement()


def parse_ifc(path: str) -> IfcFile:
    """IFC-Datei (SPF) lesen. Fehlerhafte Instanzen werden uebersprungen (IfcFile.errors)."""
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    f = IfcFile()
    m = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']*)'", text)
    if m:
        f.schema = m.group(1).upper()
    m = re.search(r"\bDATA\s*;", text)
    data = text[m.end():] if m else text
    _Parser(data, f).parse_data()
    return f


# ==========================================================================
# Geometrie-Hilfen
# ==========================================================================
def _vec3(v, default=(0.0, 0.0, 0.0)) -> np.ndarray:
    if isinstance(v, Typed):
        v = v.value
    if isinstance(v, (list, tuple)):
        out = [float(x.value if isinstance(x, Typed) else x) for x in v if x is not None]
        while len(out) < 3:
            out.append(0.0)
        return np.asarray(out[:3], float)
    return np.asarray(default, float)


def _num(v, default: float = 0.0) -> float:
    if isinstance(v, Typed):
        v = v.value
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return default


def _axis2_matrix(pl: Optional[IfcEntity]) -> np.ndarray:
    """IfcAxis2Placement3D/2D -> 4x4-Matrix."""
    M = np.eye(4)
    if pl is None:
        return M
    loc = pl.ref(0)
    if loc is not None:
        M[:3, 3] = _vec3(loc[0])
    if pl.type == "IFCAXIS2PLACEMENT2D":
        rd = pl.ref(1)
        x = _vec3(rd[0], (1, 0, 0)) if rd else np.array([1.0, 0, 0])
        z = np.array([0.0, 0.0, 1.0])
    else:
        ax = pl.ref(1)
        rd = pl.ref(2)
        z = _vec3(ax[0], (0, 0, 1)) if ax else np.array([0.0, 0, 1])
        x = _vec3(rd[0], (1, 0, 0)) if rd else np.array([1.0, 0, 0])
    nz = np.linalg.norm(z)
    z = z / nz if nz > 0 else np.array([0.0, 0, 1])
    x = x - np.dot(x, z) * z
    nx = np.linalg.norm(x)
    if nx < 1e-12:
        x = np.cross(np.array([0.0, 1, 0]), z)
        if np.linalg.norm(x) < 1e-12:
            x = np.cross(np.array([1.0, 0, 0]), z)
        nx = np.linalg.norm(x)
    x = x / nx
    y = np.cross(z, x)
    M[:3, 0], M[:3, 1], M[:3, 2] = x, y, z
    return M


def _apply(M: np.ndarray, p) -> np.ndarray:
    p = np.asarray(p, float)
    return M[:3, :3] @ p + M[:3, 3]


# ==========================================================================
# Einheiten
# ==========================================================================
_PREFIX = {"EXA": 1e18, "PETA": 1e15, "TERA": 1e12, "GIGA": 1e9, "MEGA": 1e6, "KILO": 1e3,
           "HECTO": 1e2, "DECA": 1e1, "DECI": 1e-1, "CENTI": 1e-2, "MILLI": 1e-3,
           "MICRO": 1e-6, "NANO": 1e-9, "PICO": 1e-12, "FEMTO": 1e-15, "ATTO": 1e-18}
_SI_BASE = {"METRE": 1.0, "NEWTON": 1.0, "PASCAL": 1.0, "RADIAN": 1.0, "GRAM": 1e-3,
            "SQUARE_METRE": 1.0, "CUBIC_METRE": 1.0, "KELVIN": 1.0, "DEGREE_CELSIUS": 1.0,
            "SECOND": 1.0, "HERTZ": 1.0, "JOULE": 1.0, "WATT": 1.0}


class Units:
    """Massstaebe Datei -> SI je Einheitentyp."""

    def __init__(self, ifc: IfcFile, log: list = None):
        self.scale: dict[str, float] = {}
        self.log = log
        for proj in ifc.by_type("IfcProject"):
            ua = proj.ref(8)
            if ua is None:
                continue
            for u in ua.refs(0):
                try:
                    ut = u[1] if u.type != "IFCMONETARYUNIT" else None
                    if isinstance(ut, str):
                        self.scale[str(ut).upper()] = self._unit_scale(u)
                except Exception as ex:      # einzelne Einheit
                    C.warn(log, f"Einheit {u!r} nicht verstanden: {ex}")
        self.length = self.scale.get("LENGTHUNIT", 1.0)
        self.force = self.scale.get("FORCEUNIT", 1.0)
        self.mass = self.scale.get("MASSUNIT", 1.0)
        self.angle = self.scale.get("PLANEANGLEUNIT", 1.0)
        L, F = self.length, self.force
        self.moment = self.scale.get("TORQUEUNIT", F * L)
        self.linear_force = self.scale.get("LINEARFORCEUNIT", F / L)
        self.planar_force = self.scale.get("PLANARFORCEUNIT", F / L ** 2)
        self.linear_moment = self.scale.get("LINEARMOMENTUNIT", F)
        self.linear_stiffness = self.scale.get("LINEARSTIFFNESSUNIT", F / L)
        self.rotational_stiffness = self.scale.get("ROTATIONALSTIFFNESSUNIT", F * L)
        self.pressure = self.scale.get("MODULUSOFELASTICITYUNIT",
                                       self.scale.get("PRESSUREUNIT", F / L ** 2))
        self.density = self.scale.get("MASSDENSITYUNIT", self.mass / L ** 3)

    def _unit_scale(self, u: IfcEntity) -> float:
        if u.type == "IFCSIUNIT":
            prefix = str(u[2] or "").upper()
            base = str(u[3] or "").upper()
            return _PREFIX.get(prefix, 1.0) * _SI_BASE.get(base, 1.0)
        if u.type == "IFCCONVERSIONBASEDUNIT" or u.type == "IFCCONVERSIONBASEDUNITWITHOFFSET":
            mwu = u.ref(3)
            if mwu is None:
                return 1.0
            val = _num(mwu[0], 1.0)
            base = mwu.ref(1)
            return val * (self._unit_scale(base) if base is not None else 1.0)
        if u.type == "IFCDERIVEDUNIT":
            s = 1.0
            for el in u.refs(0):
                base = el.ref(0)
                exp = _num(el[1], 1.0)
                if base is not None:
                    s *= self._unit_scale(base) ** exp
            return s
        return 1.0


# ==========================================================================
# Modellaufbau
# ==========================================================================
_CATEGORY_BY_SOURCE = {
    "DEAD_LOAD": "G", "COMPLETION_G1": "G", "LIVE_LOAD_Q": "Q", "LIVE_LOAD": "Q",
    "SNOW": "S", "WIND": "W", "PRESTRESSING": "P", "SETTLEMENT_U": "SET", "TEMPERATURE_T": "T",
    "THERMAL": "T", "EARTHQUAKE": "A", "FIRE": "A", "IMPULSE": "A", "IMPACT": "A",
    "TRANSPORT": "Q", "ERECTION": "Q", "PROPPING": "Q", "SYSTEM_IMPERFECTION": "G",
    "SHRINKAGE": "T", "CREEP": "T", "LACK_OF_FIT": "T", "BUOYANCY": "H", "ICE": "H",
    "CURRENT": "H", "WAVE": "H", "RAIN": "Q", "BRAKES": "Q",
}
_CATEGORY_BY_TYPE = {
    "PERMANENT_G": "G", "DEAD_LOAD_G": "G", "VARIABLE_Q": "Q", "LIVE_LOAD_Q": "Q",
    "SNOW_S": "S", "WIND_W": "W", "TEMPERATURE_T": "T", "PRESTRESSING_P": "P",
    "EXTRAORDINARY_A": "A", "ACCIDENTAL_A": "A",
}


class _Builder:
    def __init__(self, ifc: IfcFile, model: Model, log: list, unit_scale: Optional[float],
                 tol: float):
        self.ifc = ifc
        self.model = model
        self.log = log
        self.units = Units(ifc, log)
        if unit_scale is not None:
            self.units.length = float(unit_scale)
        self.L = self.units.length
        self.nodes = C.NodeIndex(model, tol)
        self.placement_cache: dict[int, np.ndarray] = {}
        self.conn_node: dict[int, int] = {}          # Punktlager-Instanz -> Knoten
        self.member_elems: dict[int, list[int]] = {}
        self.member_chain: dict[int, list[int]] = {}   # Stab -> Knotenkette
        self.case_of_group: dict[int, str] = {}
        self.materials: dict[int, str] = {}
        self.sections: dict[int, str] = {}
        self.default_mat: Optional[str] = None
        self.stats: dict[str, int] = {}
        self._build_inverse_maps()

    # ---- Beziehungen ---------------------------------------------------------
    def _build_inverse_maps(self):
        ifc = self.ifc
        self.member_conns: dict[int, list[tuple[IfcEntity, IfcEntity]]] = {}
        self.conn_members: dict[int, list[tuple[IfcEntity, IfcEntity]]] = {}
        for rel in ifc.by_type("IfcRelConnectsStructuralMember"):
            m, c = rel.ref(4), rel.ref(5)
            if m is not None and c is not None:
                self.member_conns.setdefault(m.id, []).append((c, rel))
                self.conn_members.setdefault(c.id, []).append((m, rel))
        self.activity_target: dict[int, IfcEntity] = {}
        for rel in ifc.by_type("IfcRelConnectsStructuralActivity"):
            el, act = rel.ref(4), rel.ref(5)
            if el is not None and act is not None:
                self.activity_target[act.id] = el
        self.group_of: dict[int, list[tuple[IfcEntity, float]]] = {}
        for rel in ifc.by_type("IfcRelAssignsToGroup"):
            grp = rel.ref(6)
            if grp is None:
                continue
            factor = _num(rel[7], 1.0) if rel.type == "IFCRELASSIGNSTOGROUPBYFACTOR" else 1.0
            for obj in rel.refs(4):
                self.group_of.setdefault(obj.id, []).append((grp, factor))
        self.material_of: dict[int, IfcEntity] = {}
        for rel in ifc.by_type("IfcRelAssociatesMaterial"):
            mat = rel.ref(5)
            if mat is None:
                continue
            for obj in rel.refs(4):
                self.material_of[obj.id] = mat
        self.profile_props_of: dict[int, IfcEntity] = {}
        for rel in ifc.by_type("IfcRelAssociatesProfileProperties"):
            pp = rel.ref(5)
            if pp is None:
                continue
            for obj in rel.refs(4):
                self.profile_props_of[obj.id] = pp
        # Materialkennwerte (IFC2X3 IfcMaterialProperties.Material / IFC4 .Material)
        self.material_props: dict[int, list[IfcEntity]] = {}
        for typ in ("IfcMechanicalMaterialProperties", "IfcGeneralMaterialProperties",
                    "IfcExtendedMaterialProperties", "IfcMaterialProperties"):
            for mp in ifc.by_type(typ):
                mat = mp.ref(0) if typ != "IfcMaterialProperties" else mp.ref(3)
                if mat is not None:
                    self.material_props.setdefault(mat.id, []).append(mp)

    def count(self, key: str, n: int = 1):
        self.stats[key] = self.stats.get(key, 0) + n

    # ---- Placement / Punkte --------------------------------------------------
    def placement(self, pl: Optional[IfcEntity]) -> np.ndarray:
        if pl is None:
            return np.eye(4)
        if pl.id in self.placement_cache:
            return self.placement_cache[pl.id]
        M = np.eye(4)
        if pl.type == "IFCLOCALPLACEMENT":
            parent = self.placement(pl.ref(0))
            M = parent @ _axis2_matrix(pl.ref(1))
        elif pl.type in ("IFCAXIS2PLACEMENT3D", "IFCAXIS2PLACEMENT2D"):
            M = _axis2_matrix(pl)
        elif pl.type == "IFCGRIDPLACEMENT":
            C.warn(self.log, f"IfcGridPlacement #{pl.id} wird als Ursprung behandelt")
        self.placement_cache[pl.id] = M
        return M

    def product_matrix(self, product: IfcEntity) -> np.ndarray:
        return self.placement(product.ref(5))

    def point(self, cp: Optional[IfcEntity], M: np.ndarray) -> Optional[np.ndarray]:
        """IfcCartesianPoint -> globale Koordinaten [m]."""
        if cp is None or cp.type != "IFCCARTESIANPOINT":
            return None
        return _apply(M, _vec3(cp[0])) * self.L

    def vertex_point(self, v: Optional[IfcEntity], M: np.ndarray) -> Optional[np.ndarray]:
        if v is None:
            return None
        if v.type == "IFCVERTEXPOINT":
            return self.point(v.ref(0), M)
        if v.type == "IFCCARTESIANPOINT":
            return self.point(v, M)
        return None

    def rep_items(self, product: IfcEntity) -> list[tuple[IfcEntity, IfcEntity]]:
        rep = product.ref(6)
        if rep is None:
            return []
        out = []
        for sr in rep.refs(2):
            for it in sr.refs(3):
                out.append((sr, it))
        return out

    def node_of_point(self, p: np.ndarray) -> int:
        return self.nodes.add(*p)

    # ---- Material ----------------------------------------------------------
    def _ifc_material(self, m: Optional[IfcEntity]) -> tuple[Optional[IfcEntity], Optional[IfcEntity], float]:
        """Beliebiges Materialobjekt -> (IfcMaterial, IfcProfileDef, Schichtdicke)."""
        if m is None:
            return None, None, 0.0
        t = m.type
        if t == "IFCMATERIAL":
            return m, None, 0.0
        if t == "IFCMATERIALPROFILESETUSAGE":
            return self._ifc_material(m.ref(0))
        if t == "IFCMATERIALPROFILESET":
            profs = m.refs(2)
            if profs:
                return self._ifc_material(profs[0])
            return None, None, 0.0
        if t == "IFCMATERIALPROFILE":
            return m.ref(2), m.ref(3), 0.0
        if t == "IFCMATERIALLAYERSETUSAGE":
            return self._ifc_material(m.ref(0))
        if t == "IFCMATERIALLAYERSET":
            layers = m.refs(0)
            mat = layers[0].ref(0) if layers else None
            thick = sum(_num(l[1]) for l in layers)
            return mat, None, thick
        if t == "IFCMATERIALLAYER":
            return m.ref(0), None, _num(m[1])
        if t == "IFCMATERIALLIST":
            mats = m.refs(0)
            return (mats[0] if mats else None), None, 0.0
        if t == "IFCMATERIALCONSTITUENTSET":
            cs = m.refs(2)
            return (cs[0].ref(2) if cs else None), None, 0.0
        if t == "IFCMATERIALCONSTITUENT":
            return m.ref(2), None, 0.0
        return None, None, 0.0

    def material_name(self, product: IfcEntity) -> str:
        mat_obj = self.material_of.get(product.id)
        mat, _, _ = self._ifc_material(mat_obj)
        return self._register_material(mat)

    def _register_material(self, mat: Optional[IfcEntity]) -> str:
        if mat is None:
            if self.default_mat is None:
                self.default_mat = C.ensure_material(self.model, None, self.log, quiet=True)
                C.warn(self.log, f"Elemente ohne Materialzuordnung erhalten {self.default_mat}")
            return self.default_mat
        if mat.id in self.materials:
            return self.materials[mat.id]
        name = str(mat[0] or f"Material {mat.id}")
        name = C.unique_name(self.model.materials, name)
        grade = C.steel_grade_from_text(name)
        if grade:
            m = Material.steel(grade, name)
        else:
            m = Material(name, 210e9, 0.3, 7850.0, 1.2e-5)
            found = self._read_material_props(mat, m)
            if not found:
                m = Material.steel(C.DEFAULT_STEEL, name)
                C.warn(self.log, f"Material '{name}': keine Stahlsorte erkannt - Kennwerte "
                                 f"von {C.DEFAULT_STEEL} verwendet")
        self.model.add_material(m)
        self.materials[mat.id] = name
        return name

    def _read_material_props(self, mat: IfcEntity, m: Material) -> bool:
        found = False
        u = self.units
        for mp in self.material_props.get(mat.id, []):
            if mp.is_a("IfcMechanicalMaterialProperties"):
                if _num(mp[2]):
                    m.E = _num(mp[2]) * u.pressure
                    found = True
                if mp[4] is not None:
                    m.nu = _num(mp[4], 0.3)
                if mp[5] is not None:
                    m.alpha = _num(mp[5], m.alpha)
                if mp.type == "IFCMECHANICALSTEELMATERIALPROPERTIES":
                    if _num(mp[6]):
                        m.fy = _num(mp[6]) * u.pressure
                    if _num(mp[7]):
                        m.fu = _num(mp[7]) * u.pressure
            elif mp.type == "IFCGENERALMATERIALPROPERTIES":
                if _num(mp[3]):
                    m.rho = _num(mp[3]) * u.density
            else:                                   # IFC4: Properties-Liste
                props = mp.refs(2) if mp.type == "IFCMATERIALPROPERTIES" else mp.refs(1)
                for p in props:
                    if p.type != "IFCPROPERTYSINGLEVALUE":
                        continue
                    key = str(p[0] or "").upper().replace(" ", "")
                    val = _num(p[2], None) if p[2] is not None else None
                    if val is None:
                        continue
                    if key in ("YOUNGMODULUS", "MODULUSOFELASTICITY", "E"):
                        m.E = val * u.pressure
                        found = True
                    elif key in ("POISSONRATIO", "NU"):
                        m.nu = val
                    elif key in ("MASSDENSITY", "DENSITY"):
                        m.rho = val * u.density
                    elif key in ("THERMALEXPANSIONCOEFFICIENT", "THERMALEXPANSION"):
                        m.alpha = val
                    elif key in ("YIELDSTRESS", "YIELDSTRENGTH"):
                        m.fy = val * u.pressure
                    elif key in ("ULTIMATESTRESS", "TENSILESTRENGTH"):
                        m.fu = val * u.pressure
        return found

    # ---- Querschnitt -----------------------------------------------------------
    def section_from_profile(self, pdef: Optional[IfcEntity], depth: int = 0) -> Optional[Section]:
        if pdef is None or depth > 3:
            return None
        L = self.L
        t = pdef.type
        pname = pdef[1] if isinstance(pdef[1], str) else ""
        name = pname or f"{t[3:].replace('PROFILEDEF', '').title()} #{pdef.id}"
        name = C.unique_name(self.model.sections, name)
        try:
            if t in ("IFCISHAPEPROFILEDEF", "IFCASYMMETRICISHAPEPROFILEDEF"):
                b, h, tw, tf = (_num(pdef[k]) * L for k in (3, 4, 5, 6))
                r = _num(pdef[7]) * L
                return Section.i_profile(name, h, b, tw, tf, r)
            if t == "IFCRECTANGLEHOLLOWPROFILEDEF":
                b, h, tw = (_num(pdef[k]) * L for k in (3, 4, 5))
                ri = _num(pdef[6], -1.0)
                ro = _num(pdef[7], -1.0)
                return Section.rhs(name, h, b, tw,
                                   r_out=ro * L if ro >= 0 else None,
                                   r_in=ri * L if ri >= 0 else None)
            if t == "IFCRECTANGLEPROFILEDEF" or t == "IFCROUNDEDRECTANGLEPROFILEDEF":
                b, h = _num(pdef[3]) * L, _num(pdef[4]) * L
                return Section.rectangle(name, b, h)
            if t == "IFCCIRCLEHOLLOWPROFILEDEF":
                return Section.pipe(name, 2 * _num(pdef[3]) * L, _num(pdef[4]) * L)
            if t == "IFCCIRCLEPROFILEDEF":
                return Section.circle(name, 2 * _num(pdef[3]) * L)
            if t == "IFCDERIVEDPROFILEDEF":
                return self.section_from_profile(pdef.ref(0), depth + 1)
            if t == "IFCCOMPOSITEPROFILEDEF":
                subs = pdef.refs(2)
                C.warn(self.log, f"Zusammengesetztes Profil '{pname}': nur erstes Teilprofil")
                return self.section_from_profile(subs[0], depth + 1) if subs else None
        except Exception as ex:
            C.warn(self.log, f"Profil '{pname}' ({t}): {ex}")
            return None
        sec = C.section_from_designation(pname, name) if pname else None
        if sec is not None:
            return sec
        if t == "IFCARBITRARYCLOSEDPROFILEDEF":
            sec = self._section_from_polygon(pdef.ref(2), name)
            if sec is not None:
                C.warn(self.log, f"Profil '{pname}': Kennwerte aus Polygon berechnet "
                                 f"(It naeherungsweise)")
                return sec
        return None

    def _section_from_polygon(self, curve: Optional[IfcEntity], name: str) -> Optional[Section]:
        if curve is None or curve.type != "IFCPOLYLINE":
            return None
        pts = [_vec3(p[0])[:2] * self.L for p in curve.refs(0)]
        if len(pts) > 1 and np.allclose(pts[0], pts[-1]):
            pts.pop()
        if len(pts) < 3:
            return None
        P = np.asarray(pts)
        x, y = P[:, 0], P[:, 1]
        x1, y1 = np.roll(x, -1), np.roll(y, -1)
        cross = x * y1 - x1 * y
        A = 0.5 * cross.sum()
        if abs(A) < 1e-16:
            return None
        cx = (x + x1) @ cross / (6 * A)
        cy = (y + y1) @ cross / (6 * A)
        Ixx = ((y ** 2 + y * y1 + y1 ** 2) @ cross) / 12.0 - A * cy ** 2
        Iyy = ((x ** 2 + x * x1 + x1 ** 2) @ cross) / 12.0 - A * cx ** 2
        A, Ixx, Iyy = abs(A), abs(Ixx), abs(Iyy)
        It = A ** 4 / (40.0 * (Ixx + Iyy))
        return Section(name, A=A, Iy=Ixx, Iz=Iyy, It=It,
                       zmax=float(max(abs(y - cy))), ymax=float(max(abs(x - cx))))

    def _section_from_props(self, pp: IfcEntity, name: str) -> Optional[Section]:
        """IfcStructuralProfileProperties (IFC2X3): Zahlenwerte -> freier Querschnitt."""
        if not pp.is_a("IfcStructuralProfileProperties"):
            return None
        L = self.L
        A = _num(pp[6]) * L ** 2
        if A <= 0:
            return None
        It = _num(pp[7]) * L ** 4
        Iy = _num(pp[9]) * L ** 4
        Iz = _num(pp[10]) * L ** 4
        Iw = _num(pp[11]) * L ** 6
        Asz = _num(pp[14]) * L ** 2
        Asy = _num(pp[15]) * L ** 2
        return Section(name, A=A, Iy=Iy or 1e-8, Iz=Iz or 1e-8, It=It or 1e-9,
                       Asy=Asy, Asz=Asz, Iw=Iw)

    def section_name(self, product: IfcEntity, explicit_profile: IfcEntity = None) -> str:
        key = product.id
        if key in self.sections:
            return self.sections[key]
        sec: Optional[Section] = None
        pdef = explicit_profile
        if pdef is None:
            _, pdef, _ = self._ifc_material(self.material_of.get(product.id))
        pp = self.profile_props_of.get(product.id)
        if pdef is None and pp is not None:
            for k in range(len(pp.args)):
                cand = pp.ref(k)
                if cand is not None and cand.type.endswith("PROFILEDEF"):
                    pdef = cand
                    break
        if pdef is not None:
            pname = pdef[1] if isinstance(pdef[1], str) else ""
            if pname:
                for s in self.model.sections.values():
                    if s.name == pname:
                        self.sections[key] = pname
                        return pname
            sec = self.section_from_profile(pdef)
            if sec is None and pp is not None:
                sec = self._section_from_props(pp, C.unique_name(self.model.sections,
                                                                  pname or f"Profil #{pp.id}"))
        elif pp is not None:
            pname = pp[0] if isinstance(pp[0], str) else ""
            sec = C.section_from_designation(pname, pname) if pname else None
            if sec is None:
                sec = self._section_from_props(pp, C.unique_name(self.model.sections,
                                                                  pname or f"Profil #{pp.id}"))
        if sec is None:
            label = product.name or f"#{product.id}"
            fb = C.ensure_section(self.model, None, self.log)
            C.warn(self.log, f"Stab '{label}': kein auswertbares Profil - {fb} verwendet")
            self.sections[key] = fb
            return fb
        self.model.add_section(sec)
        self.sections[key] = sec.name
        return sec.name

    # ---- Lastfaelle --------------------------------------------------------------
    def _group_category(self, grp: IfcEntity, depth: int = 0) -> str:
        src = str(grp[7] or "").upper()
        typ = str(grp[6] or "").upper()
        cat = _CATEGORY_BY_SOURCE.get(src) or _CATEGORY_BY_TYPE.get(typ)
        if cat:
            return cat
        if depth < 3:
            for parent, _ in self.group_of.get(grp.id, []):
                if parent.is_a("IfcStructuralLoadGroup"):
                    c = self._group_category(parent, depth + 1)
                    if c:
                        return c
        return ""

    def case_name(self, grp: Optional[IfcEntity]) -> str:
        """Lastgruppe/-fall -> Lastfallname im Modell (legt ihn an)."""
        if grp is None:
            if "LF1" not in self.model.load_cases:
                C.get_or_add_case(self.model, "LF1", "G")
            return "LF1"
        if grp.id in self.case_of_group:
            return self.case_of_group[grp.id]
        name = grp.name or f"LG {grp.id}"
        name = C.unique_name(self.model.load_cases, name)
        cat = self._group_category(grp) or "Q"
        desc = str(grp[3] or "")
        lc = C.get_or_add_case(self.model, name, cat, desc)
        if grp.type == "IFCSTRUCTURALLOADCASE":
            coeffs = grp[10]
            if isinstance(coeffs, list) and len(coeffs) == 3:
                g = [_num(c) * 9.81 for c in coeffs]
                if any(g):
                    lc.gravity = g
        self.case_of_group[grp.id] = name
        return name

    def case_for(self, action: IfcEntity) -> str:
        for grp, _ in self.group_of.get(action.id, []):
            if grp.is_a("IfcStructuralLoadGroup"):
                pt = str(grp[5] or "").upper()
                if pt == "LOAD_COMBINATION":
                    continue
                return self.case_name(grp)
        return self.case_name(None)

    def build_combinations(self):
        for grp in self.ifc.by_type("IfcStructuralLoadGroup"):
            if str(grp[5] or "").upper() != "LOAD_COMBINATION":
                continue
            factors: dict[str, float] = {}
            for rel in self.ifc.by_type("IfcRelAssignsToGroup"):
                if rel.ref(6) is not grp:
                    continue
                f = _num(rel[7], 1.0) if rel.type == "IFCRELASSIGNSTOGROUPBYFACTOR" else 1.0
                for obj in rel.refs(4):
                    if obj.is_a("IfcStructuralLoadGroup") and obj.id in self.case_of_group:
                        nm = self.case_of_group[obj.id]
                        factors[nm] = factors.get(nm, 0.0) + f
            if not factors:
                continue
            name = C.unique_name(self.model.combinations, grp.name or f"Kombination {grp.id}")
            purpose = (str(grp[9] or "") + " " + name).upper()
            typ = "ULS"
            if "SLS" in purpose or "GZG" in purpose or "SERVICE" in purpose:
                typ = "SLS_QP" if "QUASI" in purpose else ("SLS_FR" if "FREQ" in purpose
                                                            else "SLS_CH")
            elif "ACC" in purpose or "AUSSERGEW" in purpose:
                typ = "ACC"
            self.model.add_combination(name, factors, typ, str(grp[3] or ""))
            self.count("Kombinationen")

    # ---- Lagerbedingungen ----------------------------------------------------------
    def _classify(self, v, scale: float) -> tuple[str, float]:
        """Wert einer IfcBoundaryNodeCondition -> ('free'|'fixed'|'spring', k)."""
        if v is None:
            return "free", 0.0
        if isinstance(v, Typed):
            if v.type == "IFCBOOLEAN":
                val = v.value
                fixed = (val == "T") if isinstance(val, str) else bool(val)
                return ("fixed" if fixed else "free"), 0.0
            v = v.value
        if isinstance(v, Enum):
            return ("fixed" if str(v).upper() in ("T", "TRUE") else "free"), 0.0
        if isinstance(v, bool):
            return ("fixed" if v else "free"), 0.0
        if isinstance(v, (int, float)):
            if v < 0:
                return "fixed", 0.0
            if v == 0:
                return "free", 0.0
            k = float(v) * scale
            if k >= 1e15:
                return "fixed", 0.0
            return "spring", k
        return "free", 0.0

    def apply_condition(self, node: int, cond: Optional[IfcEntity], label: str) -> bool:
        if cond is None or not cond.is_a("IfcBoundaryNodeCondition"):
            if cond is not None:
                C.warn(self.log, f"Lager '{label}': {cond.type} nicht unterstuetzt")
            return False
        u = self.units
        fixed, spring_dofs, spring_k = [], [], []
        for dof in range(6):
            scale = u.linear_stiffness if dof < 3 else u.rotational_stiffness
            kind, k = self._classify(cond[dof + 1], scale)
            if kind == "fixed":
                fixed.append(dof)
            elif kind == "spring":
                spring_dofs.append(dof)
                spring_k.append(k)
        if fixed:
            self.model.fix(node, fixed)
        if spring_dofs:
            self.model.fix(node, spring_dofs, stiffness=spring_k)
        return bool(fixed or spring_dofs)

    def _release_hinges(self, elem: int, at_end: bool, cond: Optional[IfcEntity]):
        """Gelenkbedingung aus IfcRelConnectsStructuralMember.AppliedCondition."""
        if cond is None or not cond.is_a("IfcBoundaryNodeCondition"):
            return
        e = self.model.elements[elem]
        for dof in range(3, 6):
            kind, _ = self._classify(cond[dof + 1], 1.0)
            if kind == "free":
                local = dof + (6 if at_end else 0)
                if local not in e.hinges:
                    e.hinges.append(local)
        for dof in range(3):
            kind, _ = self._classify(cond[dof + 1], 1.0)
            if kind == "free":
                C.warn(self.log, f"Stabanschluss: Verschiebungsfreigabe (FHG {dof}) "
                                 f"wird nicht unterstuetzt")
                break

    # ---- Structural Analysis View --------------------------------------------------
    def build_structural(self) -> int:
        ifc = self.ifc
        model = self.model
        conns = ifc.by_type("IfcStructuralPointConnection")
        members = ifc.by_type("IfcStructuralCurveMember")
        surfaces = ifc.by_type("IfcStructuralSurfaceMember")
        if not conns and not members and not surfaces:
            return 0

        # Knoten
        for c in conns:
            try:
                M = self.product_matrix(c)
                p = None
                for _, it in self.rep_items(c):
                    p = self.vertex_point(it, M)
                    if p is not None:
                        break
                if p is None:
                    p = _apply(M, (0.0, 0.0, 0.0)) * self.L
                    C.warn(self.log, f"Punktknoten '{c.name or c.id}': keine Geometrie, "
                                     f"Placement-Ursprung verwendet")
                self.conn_node[c.id] = self.node_of_point(p)
                self.count("Knoten")
            except Exception as ex:
                C.warn(self.log, f"IfcStructuralPointConnection #{c.id}: {ex}")

        # Staebe
        for m in members:
            try:
                self._build_curve_member(m)
            except Exception as ex:
                C.warn(self.log, f"Stab '{m.name or m.id}' uebersprungen: {ex}")
        # Flaechen
        for s in surfaces:
            try:
                self._build_surface_member(s)
            except Exception as ex:
                C.warn(self.log, f"Flaeche '{s.name or s.id}' uebersprungen: {ex}")
        self.nodes.flush()

        # Lager
        for c in conns:
            node = self.conn_node.get(c.id)
            if node is None:
                continue
            cond = c.ref(7)
            label = c.name or f"#{c.id}"
            if cond is not None and self.apply_condition(node, cond, label):
                self.count("Lager")
        # Gelenke
        for m in members:
            elems = self.member_elems.get(m.id)
            if not elems:
                continue
            chain = self.member_chain.get(m.id, [])
            for conn, rel in self.member_conns.get(m.id, []):
                cond = rel.ref(6)
                if cond is None:
                    continue
                node = self.conn_node.get(conn.id)
                if node is None:
                    continue
                if chain and node == chain[0]:
                    self._release_hinges(elems[0], False, cond)
                elif chain and node == chain[-1]:
                    self._release_hinges(elems[-1], True, cond)

        # Lastfaelle in Dateireihenfolge anlegen
        for grp in ifc.by_type("IfcStructuralLoadGroup"):
            pt = str(grp[5] or "").upper()
            if grp.type == "IFCSTRUCTURALLOADCASE" or pt in ("LOAD_CASE", "NOTDEFINED", "",
                                                             "USERDEFINED"):
                self.case_name(grp)
        # Lasten
        for act in ifc.by_type("IfcStructuralPointAction"):
            try:
                self._build_point_action(act)
            except Exception as ex:
                C.warn(self.log, f"Knotenlast #{act.id}: {ex}")
        for act in ifc.by_type("IfcStructuralCurveAction"):
            try:
                self._build_linear_action(act)
            except Exception as ex:
                C.warn(self.log, f"Streckenlast #{act.id}: {ex}")
        for act in ifc.by_type("IfcStructuralSurfaceAction"):
            try:
                self._build_planar_action(act)
            except Exception as ex:
                C.warn(self.log, f"Flaechenlast #{act.id}: {ex}")
        self.build_combinations()
        return len(conns) + len(members) + len(surfaces)

    def _edge_points(self, item: IfcEntity, M: np.ndarray) -> list[np.ndarray]:
        """Kanten-/Kurvendarstellung -> Punktfolge."""
        t = item.type
        if t == "IFCORIENTEDEDGE":
            base = item.ref(2)
            pts = self._edge_points(base, M) if base is not None else []
            if item[3] is not None and str(item[3]).upper() in ("F", "FALSE"):
                pts = pts[::-1]
            return pts
        if t in ("IFCEDGE", "IFCEDGECURVE", "IFCSUBEDGE"):
            a = self.vertex_point(item.ref(0), M)
            b = self.vertex_point(item.ref(1), M)
            return [p for p in (a, b) if p is not None]
        if t == "IFCPOLYLINE":
            return [p for p in (self.point(cp, M) for cp in item.refs(0)) if p is not None]
        if t == "IFCTRIMMEDCURVE":
            out = []
            for k in (1, 2):
                trims = item[k] if isinstance(item[k], list) else []
                for tr in trims:
                    e = self.ifc.resolve(tr)
                    if isinstance(e, IfcEntity) and e.type == "IFCCARTESIANPOINT":
                        out.append(self.point(e, M))
            return out
        if t == "IFCEDGELOOP":
            out = []
            for e in item.refs(0):
                out.extend(self._edge_points(e, M))
            return out
        return []

    def _build_curve_member(self, m: IfcEntity):
        model = self.model
        M = self.product_matrix(m)
        rep_pts: list[np.ndarray] = []
        for _, it in self.rep_items(m):
            rep_pts = self._edge_points(it, M)
            if len(rep_pts) >= 2:
                break
        chain: list[int] = []
        for p in rep_pts:
            n = self.node_of_point(p)
            if n not in chain:
                chain.append(n)
        for conn, _ in self.member_conns.get(m.id, []):
            n = self.conn_node.get(conn.id)
            if n is not None and n not in chain:
                chain.append(n)
        if len(chain) < 2:
            raise ValueError("weniger als zwei Endknoten")
        if len(chain) > 2:
            p0 = self.nodes.get(chain[0])
            dists = [np.linalg.norm(self.nodes.get(n) - p0) for n in chain]
            far = chain[int(np.argmax(dists))]
            axis = self.nodes.get(far) - p0
            axis /= (np.linalg.norm(axis) or 1.0)
            chain.sort(key=lambda n: float(np.dot(self.nodes.get(n) - p0, axis)))
        pt = str(m[7] or "").upper()
        typ = "truss" if pt in ("PIN_JOINED_MEMBER", "TENSION_MEMBER",
                                "COMPRESSION_MEMBER", "CABLE") else "beam"
        if pt in ("TENSION_MEMBER", "COMPRESSION_MEMBER", "CABLE"):
            C.warn(self.log, f"Stab '{m.name or m.id}': {pt} als linearer Fachwerkstab")
        mat = self.material_name(m)
        sec = self.section_name(m)
        roll = 0.0
        ax = m.ref(8) if self.ifc.schema.startswith("IFC4") else None
        if ax is not None and ax.type == "IFCDIRECTION":
            v = M[:3, :3] @ _vec3(ax[0])
            roll = C.roll_from_vector(self.nodes.get(chain[0]), self.nodes.get(chain[-1]), v, "z")
        name = C.unique_name(model.members, m.name or f"S{m.id}")
        elems = []
        for a, b in zip(chain[:-1], chain[1:]):
            elems.append(model.add_element(typ, [a, b], mat, sec, roll=roll, group=name))
        self.member_elems[m.id] = elems
        self.member_chain[m.id] = chain
        model.add_member(name, elems)
        self.count("Staebe")

    def _faces_of(self, item: IfcEntity, depth: int = 0) -> list[IfcEntity]:
        t = item.type
        if item.is_a("IfcFace"):
            return [item]
        if depth > 4:
            return []
        out = []
        if t in ("IFCCONNECTEDFACESET", "IFCCLOSEDSHELL", "IFCOPENSHELL"):
            for f in item.refs(0):
                out.extend(self._faces_of(f, depth + 1))
        elif t in ("IFCSHELLBASEDSURFACEMODEL", "IFCFACEBASEDSURFACEMODEL",
                   "IFCFACETEDBREP", "IFCMANIFOLDSOLIDBREP"):
            for s in item.refs(0):
                out.extend(self._faces_of(s, depth + 1))
        return out

    def _loop_points(self, bound: IfcEntity, M: np.ndarray) -> list[np.ndarray]:
        loop = bound.ref(0)
        if loop is None:
            return []
        if loop.type == "IFCPOLYLOOP":
            pts = [self.point(cp, M) for cp in loop.refs(0)]
        else:
            pts = self._edge_points(loop, M)
        pts = [p for p in pts if p is not None]
        if bound[1] is not None and str(bound[1]).upper() in ("F", "FALSE"):
            pts = pts[::-1]
        return pts

    def _build_surface_member(self, s: IfcEntity):
        model = self.model
        M = self.product_matrix(s)
        faces = []
        for _, it in self.rep_items(s):
            faces.extend(self._faces_of(it))
        if not faces:
            raise ValueError("keine Flaechengeometrie (IfcFace/IfcFaceSurface)")
        mat_obj = self.material_of.get(s.id)
        mat_ent, _, layer_t = self._ifc_material(mat_obj)
        mat = self._register_material(mat_ent)
        t = _num(s[8]) * self.L
        if t <= 0 and layer_t > 0:
            t = layer_t * self.L
        label = s.name or f"F{s.id}"
        prop = C.ensure_shell_prop(model, C.unique_name(model.shells, f"t{t * 1e3:g}")
                                   if t > 0 else None, t if t > 0 else None, self.log)
        elems = []
        for face in faces:
            outer, inner = [], []
            for b in face.refs(0):
                (outer if b.type == "IFCFACEOUTERBOUND" or not outer else inner).append(b)
            if inner:
                C.warn(self.log, f"Flaeche '{label}': {len(inner)} Oeffnung(en) werden ignoriert")
            for b in outer[:1]:
                pts = self._loop_points(b, M)
                ids = [self.node_of_point(p) for p in pts]
                elems.extend(C.polygon_to_shells(model, ids, mat, prop, label, self.log,
                                                 f"Flaeche '{label}'"))
        self.member_elems[s.id] = elems
        self.count("Flaechen")
        self.count("Schalenelemente", len(elems))

    def _load_values(self, load: Optional[IfcEntity]) -> tuple[list, list]:
        """AppliedLoad -> (Werte, Werte am Ende) fuer Kraft-/Momentkomponenten 1..6."""
        if load is None:
            return [], []
        if load.type == "IFCSTRUCTURALLOADCONFIGURATION":
            vals = load.refs(1)
            if not vals:
                return [], []
            first = [_num(vals[0][k]) for k in range(1, 7)]
            last = [_num(vals[-1][k]) for k in range(1, 7)]
            return first, last
        vals = [_num(load[k]) for k in range(1, 7)]
        return vals, vals

    def _target_node(self, act: IfcEntity) -> Optional[int]:
        target = self.activity_target.get(act.id)
        if target is not None and target.id in self.conn_node:
            return self.conn_node[target.id]
        M = self.product_matrix(act)
        for _, it in self.rep_items(act):
            p = self.vertex_point(it, M)
            if p is not None:
                n = self.nodes.find(*p)
                if n is not None:
                    return n
                if target is not None and target.id in self.member_chain:
                    C.warn(self.log, f"Knotenlast #{act.id} liegt innerhalb von Stab "
                                     f"'{target.name}' - naechster Knoten verwendet")
                    chain = self.member_chain[target.id]
                    return min(chain, key=lambda n: np.linalg.norm(self.nodes.get(n) - p))
        if target is not None and target.id in self.member_chain:
            return self.member_chain[target.id][0]
        return None

    def _build_point_action(self, act: IfcEntity):
        load = act.ref(7)
        if load is None or not load.is_a("IfcStructuralLoadSingleForce"):
            if load is not None:
                C.warn(self.log, f"Knotenlast #{act.id}: {load.type} nicht unterstuetzt")
            return
        node = self._target_node(act)
        if node is None:
            C.warn(self.log, f"Knotenlast #{act.id}: kein Zielknoten gefunden")
            return
        vals, _ = self._load_values(load)
        u = self.units
        F = [vals[k] * u.force for k in range(3)] + [vals[k] * u.moment for k in range(3, 6)]
        if not any(F):
            return
        self.model.load_node(node, *F, case=self.case_for(act))
        self.count("Knotenlasten")

    def _build_linear_action(self, act: IfcEntity):
        target = self.activity_target.get(act.id)
        elems = self.member_elems.get(target.id) if target is not None else None
        if not elems:
            C.warn(self.log, f"Streckenlast #{act.id}: kein Stab zugeordnet")
            return
        load = act.ref(7)
        if load is None:
            return
        vals, vals2 = self._load_values(load)
        if not vals:
            return
        base = load.refs(1)[0] if load.type == "IFCSTRUCTURALLOADCONFIGURATION" else load
        if not base.is_a("IfcStructuralLoadLinearForce"):
            C.warn(self.log, f"Streckenlast #{act.id}: {base.type} nicht unterstuetzt")
            return
        u = self.units
        q1 = [vals[k] * u.linear_force for k in range(3)]
        q2 = [vals2[k] * u.linear_force for k in range(3)]
        if any(vals[3:6]):
            C.warn(self.log, f"Streckenlast #{act.id}: Streckenmomente werden ignoriert")
        system = "local" if str(act[8] or "").upper() == "LOCAL_COORDS" else "global"
        proj_idx = 10 if self.ifc.schema.startswith("IFC4") else 11
        if str(act[proj_idx] or "").upper() == "PROJECTED_LENGTH":
            C.warn(self.log, f"Streckenlast #{act.id}: Projektionslaenge wird als wahre "
                             f"Laenge angesetzt")
        case = self.case_for(act)
        # Linear veraenderlich ueber die Stabkette verteilen
        model = self.model
        lengths = [model.element_length(e) for e in elems]
        total = sum(lengths) or 1.0
        pos = 0.0
        for e, L in zip(elems, lengths):
            f1, f2 = pos / total, (pos + L) / total
            qa = [a + (b - a) * f1 for a, b in zip(q1, q2)]
            qb = [a + (b - a) * f2 for a, b in zip(q1, q2)]
            model.load_beam(e, *qa, system=system, case=case,
                            q2=qb if qb != qa else None)
            pos += L
        self.count("Streckenlasten")

    def _build_planar_action(self, act: IfcEntity):
        target = self.activity_target.get(act.id)
        elems = self.member_elems.get(target.id) if target is not None else None
        if not elems:
            C.warn(self.log, f"Flaechenlast #{act.id}: keine Flaeche zugeordnet")
            return
        load = act.ref(7)
        if load is None:
            return
        vals, _ = self._load_values(load)
        base = load.refs(1)[0] if load.type == "IFCSTRUCTURALLOADCONFIGURATION" else load
        if not base.is_a("IfcStructuralLoadPlanarForce") or not vals:
            C.warn(self.log, f"Flaechenlast #{act.id}: {base.type} nicht unterstuetzt")
            return
        F = np.array(vals[:3]) * self.units.planar_force
        if not np.any(F):
            return
        case = self.case_for(act)
        if str(act[8] or "").upper() == "LOCAL_COORDS":
            for e in elems:
                self.model.load_face(e, float(F[2]), 0, case=case)
        else:
            mag = float(np.linalg.norm(F))
            d = (F / mag).tolist()
            for e in elems:
                self.model.load_face(e, mag, 0, case=case, direction=d)
        self.count("Flaechenlasten")

    # ---- Fallback: Bauteile -------------------------------------------------------
    def _find_solids(self, item: IfcEntity, M: np.ndarray, out: list, depth: int = 0):
        t = item.type
        if depth > 6:
            return
        if t == "IFCEXTRUDEDAREASOLID":
            out.append((item, M))
        elif t == "IFCMAPPEDITEM":
            src = item.ref(0)
            op = item.ref(1)
            Mt = np.eye(4)
            if op is not None:
                Mt = _axis2_matrix_from_operator(op)
            if src is not None:
                Mo = _axis2_matrix(src.ref(0))
                rep = src.ref(1)
                if rep is not None:
                    for it in rep.refs(3):
                        self._find_solids(it, M @ Mt @ Mo, out, depth + 1)
        elif t in ("IFCBOOLEANCLIPPINGRESULT", "IFCBOOLEANRESULT"):
            first = item.ref(1)
            if first is not None:
                self._find_solids(first, M, out, depth + 1)

    def build_physical(self) -> int:
        ifc = self.ifc
        model = self.model
        n = 0
        for typ in ("IfcBeam", "IfcColumn", "IfcMember"):
            for prod in ifc.by_type(typ):
                try:
                    if self._build_physical_member(prod, typ):
                        n += 1
                except Exception as ex:
                    C.warn(self.log, f"{typ} '{prod.name or prod.id}': {ex}")
        self.nodes.flush()
        skipped = {}
        for typ in ("IfcPlate", "IfcSlab", "IfcWall", "IfcFooting", "IfcRoof"):
            k = len(ifc.by_type(typ))
            if k:
                skipped[typ] = k
        for typ, k in skipped.items():
            C.say(self.log, f"{k} x {typ} nicht importiert (nur Stabachsen aus "
                            f"Bauteilen ableitbar)")
        if n:
            C.warn(self.log, f"Kein Statikmodell (Structural Analysis View) in der Datei - "
                             f"{n} Stabachsen aus IfcBeam/IfcColumn/IfcMember abgeleitet; "
                             f"Lager und Lasten muessen ergaenzt werden")
        return n

    def _build_physical_member(self, prod: IfcEntity, typ: str) -> bool:
        M = self.product_matrix(prod)
        pts: list[np.ndarray] = []
        profile = None
        # 1. Achsdarstellung
        rep = prod.ref(6)
        if rep is not None:
            for sr in rep.refs(2):
                if str(sr[1] or "").upper() == "AXIS":
                    for it in sr.refs(3):
                        pts = self._edge_points(it, M)
                        if len(pts) >= 2:
                            break
                if len(pts) >= 2:
                    break
        # 2. Extrusion
        if len(pts) < 2 and rep is not None:
            solids = []
            for sr in rep.refs(2):
                for it in sr.refs(3):
                    self._find_solids(it, M, solids)
            if solids:
                solid, Ms = solids[0]
                Mp = Ms @ _axis2_matrix(solid.ref(1))
                d = _vec3(solid.ref(2)[0], (0, 0, 1)) if solid.ref(2) else np.array([0.0, 0, 1])
                depth = _num(solid[3])
                p0 = _apply(Mp, (0.0, 0.0, 0.0))
                p1 = _apply(Mp, d / (np.linalg.norm(d) or 1.0) * depth)
                pts = [p0 * self.L, p1 * self.L]
                profile = solid.ref(0)
        if len(pts) < 2:
            C.warn(self.log, f"{typ} '{prod.name or prod.id}': keine Achse ableitbar")
            return False
        mat = self.material_name(prod)
        sec = self.section_name(prod, explicit_profile=profile)
        name = C.unique_name(self.model.members, prod.name or f"{typ[3:]} {prod.id}")
        chain = []
        for p in pts:
            n = self.node_of_point(p)
            if n not in chain:
                chain.append(n)
        if len(chain) < 2:
            return False
        elems = [self.model.add_element("beam", [a, b], mat, sec, group=typ[3:])
                 for a, b in zip(chain[:-1], chain[1:])]
        self.model.add_member(name, elems)
        self.count(f"{typ}-Achsen")
        return True


def _axis2_matrix_from_operator(op: IfcEntity) -> np.ndarray:
    """IfcCartesianTransformationOperator3D -> 4x4 (Skalierung wird ignoriert)."""
    M = np.eye(4)
    a1 = op.ref(0)
    a2 = op.ref(1)
    loc = op.ref(2)
    a3 = op.ref(4)
    x = _vec3(a1[0], (1, 0, 0)) if a1 else np.array([1.0, 0, 0])
    y = _vec3(a2[0], (0, 1, 0)) if a2 else np.array([0.0, 1, 0])
    z = _vec3(a3[0], (0, 0, 1)) if a3 else np.cross(x, y)
    for v in (x, y, z):
        nv = np.linalg.norm(v)
        if nv > 0:
            v /= nv
    M[:3, 0], M[:3, 1], M[:3, 2] = x, y, z
    if loc is not None:
        M[:3, 3] = _vec3(loc[0])
    return M


# ==========================================================================
def import_ifc(path: str, model: Model = None, log: list = None,
               unit_scale: float = None, tol: float = C.DEFAULT_TOL,
               **_ignored) -> Model:
    """IFC-Datei importieren (Statikmodell, sonst Bauteilachsen)."""
    if model is None:
        model = Model(os.path.splitext(os.path.basename(path))[0])
    ifc = parse_ifc(path)
    if not ifc.entities:
        raise ValueError(f"{os.path.basename(path)}: keine IFC-Instanzen gefunden "
                         f"(keine STEP-Datei?)")
    for err in ifc.errors[:20]:
        C.warn(log, f"IFC-Syntax: {err}")
    if len(ifc.errors) > 20:
        C.warn(log, f"... {len(ifc.errors) - 20} weitere Syntaxfehler")
    C.say(log, f"IFC-Schema {ifc.schema or 'unbekannt'}, {len(ifc.entities)} Instanzen")
    b = _Builder(ifc, model, log, unit_scale, tol)
    u = b.units
    C.say(log, f"Einheiten: Laenge x{u.length:g} m, Kraft x{u.force:g} N")
    n = b.build_structural()
    if n == 0:
        b.build_physical()
    for k, v in b.stats.items():
        C.say(log, f"{v} {k}")
    if not model.elements:
        C.warn(log, "IFC-Datei enthaelt keine importierbaren Tragwerkselemente")
    return model
