"""
SAF-Import (Structural Analysis Format, Excel-basiert; RFEM 6, SCIA, Allplan,
AxisVM, ...).

Gelesen werden die Blaetter (Kopfzeile = erste Zeile, Spalten nach Namen,
Gross-/Kleinschreibung egal, fehlende optionale Spalten werden toleriert):
    StructuralMaterial, StructuralCrossSection, StructuralPointConnection,
    StructuralCurveMember, StructuralSurfaceMember, StructuralPointSupport,
    StructuralLoadGroup, StructuralLoadCase, StructuralLoadCombination,
    StructuralPointAction, StructuralPointMoment, StructuralCurveAction,
    StructuralSurfaceAction
Einheiten laut SAF: Koordinaten m, Querschnittsabmessungen mm (A mm², I mm⁴),
Dicken mm, E-Modul MPa, Lasten kN / kN/m / kN/m², Federn MN/m bzw. MNm/rad.
Abweichende Einheiten in eckigen Klammern der Kopfzeile werden erkannt.
Globales Z zeigt nach oben (Eigengewicht -> g = -9.81 m/s² in Z).
"""
from __future__ import annotations

import math
import os
import re
from typing import Optional

import numpy as np

from ..model import Model, Material, Section
from . import _common as C
from .xlsx_reader import read_table_file

DEFAULT_UNIT_SCALE = 1.0


# --------------------------------------------------------------------------
# Tabellenzugriff
# --------------------------------------------------------------------------
class Sheet:
    """Blatt mit Kopfzeile: Spaltensuche ueber Muster auf normalisierten Namen."""

    def __init__(self, name: str, rows: list[list]):
        self.name = name
        self.rows = rows
        self.header: list[str] = []
        self.start = 0
        for i, r in enumerate(rows[:10]):
            if r and sum(1 for c in r if C.clean_text(c)) >= 2:
                self.header = [C.clean_text(c) for c in r]
                self.start = i + 1
                break
        self.keys = [C.norm_key(h) for h in self.header]

    def col(self, *patterns: str) -> Optional[int]:
        """Erste Spalte, deren normalisierter Name eines der Muster (Regex) erfuellt."""
        for pat in patterns:
            rx = re.compile(pat)
            for i, k in enumerate(self.keys):
                if rx.search(k):
                    return i
        return None

    def unit(self, col: Optional[int], default: float) -> float:
        if col is None:
            return default
        return C.unit_factor(self.header[col], default)

    def data(self):
        for r in self.rows[self.start:]:
            if r and any(C.clean_text(c) for c in r):
                yield r

    @staticmethod
    def text(row: list, col: Optional[int]) -> str:
        if col is None or col >= len(row):
            return ""
        return C.clean_text(row[col])

    @staticmethod
    def num(row: list, col: Optional[int]) -> Optional[float]:
        if col is None or col >= len(row):
            return None
        return C.parse_number(row[col])


def find_sheets(tables: dict[str, list[list]]) -> dict[str, Sheet]:
    """Blattnamen normalisieren: 'StructuralPointConnection' -> 'pointconnection'."""
    out = {}
    for name, rows in tables.items():
        key = re.sub(r"[^a-z]", "", name.lower())
        if key.startswith("structural"):
            key = key[len("structural"):]
        out[key] = Sheet(name, rows)
    return out


def is_saf(tables: dict[str, list[list]]) -> bool:
    return any(re.sub(r"[^a-z]", "", n.lower()).startswith("structural") for n in tables)


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------
_SHAPE_PARAMS = {
    # Formname (normalisiert) -> (Bauart, Parameterreihenfolge)
    "rectangle": ("rect", ("h", "b")),
    "rectangular": ("rect", ("h", "b")),
    "circle": ("circle", ("d",)),
    "circular": ("circle", ("d",)),
    "i": ("I", ("h", "b", "tw", "tf", "r")),
    "ishape": ("I", ("h", "b", "tw", "tf", "r")),
    "rectangularhollow": ("RHS", ("h", "b", "t", "r")),
    "rhs": ("RHS", ("h", "b", "t", "r")),
    "box": ("RHS", ("h", "b", "t", "r")),
    "circularhollow": ("CHS", ("d", "t")),
    "chs": ("CHS", ("d", "t")),
    "pipe": ("CHS", ("d", "t")),
    "tube": ("CHS", ("d", "t")),
}


def _section_from_shape(name: str, shape: str, params: list[float]) -> Optional[Section]:
    key = re.sub(r"[^a-z]", "", shape.lower())
    spec = _SHAPE_PARAMS.get(key)
    if spec is None or not params:
        return None
    kind, order = spec
    d = dict(zip(order, params))
    try:
        if kind == "rect" and "b" in d:
            return Section.rectangle(name, d["b"], d["h"])
        if kind == "circle":
            return Section.circle(name, d["d"])
        if kind == "I" and "tf" in d:
            return Section.i_profile(name, d["h"], d["b"], d["tw"], d["tf"], d.get("r", 0.0))
        if kind == "RHS" and "t" in d:
            return Section.rhs(name, d["h"], d["b"], d["t"])
        if kind == "CHS" and "t" in d:
            return Section.pipe(name, d["d"], d["t"])
    except Exception:
        return None
    return None


def _direction_vector(text: str, row: list, sh: Sheet) -> Optional[np.ndarray]:
    s = text.strip().upper()
    if s in ("X", "Y", "Z"):
        v = np.zeros(3)
        v["XYZ".index(s)] = 1.0
        return v
    if s in ("-X", "-Y", "-Z"):
        v = np.zeros(3)
        v["XYZ".index(s[1])] = -1.0
        return v
    if s in ("VECTOR", "VEKTOR", ""):
        cx = sh.col(r"^vector x", r"^(coordinate|vektor) x", r"^x$")
        cy = sh.col(r"^vector y", r"^(coordinate|vektor) y", r"^y$")
        cz = sh.col(r"^vector z", r"^(coordinate|vektor) z", r"^z$")
        if cx is not None and cy is not None and cz is not None:
            v = np.array([Sheet.num(row, c) or 0.0 for c in (cx, cy, cz)])
            if np.linalg.norm(v) > 0:
                return v / np.linalg.norm(v)
    return None


_GROUP_TYPE_CAT = {"permanent": "G", "variable": "Q", "accidental": "A", "seismic": "A",
                   "fatigue": "FAT", "moving": "Q", "prestress": "P"}
_LOAD_TYPE_CAT = {"selfweight": "G", "prestress": "P", "wind": "W", "snow": "S",
                  "temperature": "T", "seismic": "A", "fire": "A", "maintenance": "Q_H",
                  "primaryeffect": "G", "water": "H", "settlement": "SET"}


def _lookup(table: dict, text: str) -> Optional[str]:
    key = re.sub(r"[^a-z]", "", text.lower())
    if not key:
        return None
    for k, v in table.items():
        if key.startswith(k):
            return v
    return None


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------
def import_saf(path: str, model: Model = None, log: list = None,
               unit_scale: float = DEFAULT_UNIT_SCALE, tol: float = C.DEFAULT_TOL,
               tables: dict = None, **_ignored) -> Model:
    """SAF-Arbeitsmappe (xlsx) importieren. 'tables' = bereits gelesene Blaetter."""
    if model is None:
        model = Model(os.path.splitext(os.path.basename(path))[0])
    if tables is None:
        tables = read_table_file(path)
    sheets = find_sheets(tables)
    if not sheets:
        raise ValueError("SAF: keine Blaetter gefunden")
    scale = float(unit_scale)
    nodes = C.NodeIndex(model, tol)

    # ---- Projektinfo ---------------------------------------------------------
    sh = sheets.get("projectinformation")
    if sh is not None:
        for r in sh.data():
            c = sh.col(r"^project ?name", r"^name$")
            if Sheet.text(r, c):
                model.meta["projekt"] = Sheet.text(r, c)
                break

    # ---- Materialien ---------------------------------------------------------
    mat_names: dict[str, str] = {}          # SAF-Name -> Modellname
    sh = sheets.get("material")
    if sh is not None:
        c_name = sh.col(r"^name$")
        c_type = sh.col(r"^type$")
        c_qual = sh.col(r"^quality")
        c_rho = sh.col(r"unit ?mass|density|dichte")
        c_E = sh.col(r"^e ?modul", r"modulus of elasticity", r"^e$")
        c_nu = sh.col(r"poisson")
        c_al = sh.col(r"thermal ?expansion|expansion")
        f_E = sh.unit(c_E, 1e6)
        f_rho = sh.unit(c_rho, 1.0)
        for r in sh.data():
            name = Sheet.text(r, c_name)
            if not name:
                continue
            quality = Sheet.text(r, c_qual)
            typ = Sheet.text(r, c_type).lower()
            grade = C.steel_grade_from_text(quality) or C.steel_grade_from_text(name)
            if grade:
                m = Material.steel(grade, name)
            else:
                m = Material(name, 210e9, 0.3, 7850.0, 1.2e-5)
                if "steel" in typ or "stahl" in typ:
                    m.fy = 235e6
            E = Sheet.num(r, c_E)
            if E:
                m.E = E * f_E
            nu = Sheet.num(r, c_nu)
            if nu is not None:
                m.nu = nu
            rho = Sheet.num(r, c_rho)
            if rho:
                m.rho = rho * f_rho
            al = Sheet.num(r, c_al)
            if al is not None and al > 0:
                m.alpha = al
            model.add_material(m)
            mat_names[name] = m.name
        C.say(log, f"SAF: {len(mat_names)} Materialien")

    def material(name: str) -> str:
        if name in mat_names:
            return mat_names[name]
        if name:
            mat_names[name] = C.ensure_material(model, name, log)
            return mat_names[name]
        return C.ensure_material(model, None, log, quiet=True)

    # ---- Querschnitte --------------------------------------------------------
    sec_names: dict[str, str] = {}
    sec_material: dict[str, str] = {}
    sh = sheets.get("crosssection")
    if sh is not None:
        c_name = sh.col(r"^name$")
        c_mat = sh.col(r"^material")
        c_shape = sh.col(r"^shape")
        c_par = sh.col(r"^parameters")
        c_prof = sh.col(r"^profile$", r"^profile")
        c_A = sh.col(r"^a$")
        c_Iy = sh.col(r"^iy$")
        c_Iz = sh.col(r"^iz$")
        c_It = sh.col(r"^it$")
        c_Iw = sh.col(r"^iw$")
        c_Wy = sh.col(r"^wely$")
        c_Wz = sh.col(r"^welz$")
        c_Wpy = sh.col(r"^wply$")
        c_Wpz = sh.col(r"^wplz$")
        f_par = sh.unit(c_par, 1e-3)
        f_A = sh.unit(c_A, 1e-6)
        f_I = sh.unit(c_Iy, 1e-12)
        f_Iw = sh.unit(c_Iw, 1e-18)
        f_W = sh.unit(c_Wy, 1e-9)
        for r in sh.data():
            name = Sheet.text(r, c_name)
            if not name:
                continue
            profile = Sheet.text(r, c_prof)
            shape = Sheet.text(r, c_shape)
            params = [v * f_par for v in (C.parse_number(p) for p in
                                          C.split_list(Sheet.text(r, c_par), r"[;|]"))
                      if v is not None]
            sec = None
            for cand in (profile, name):
                sec = C.section_from_designation(cand, name) if cand else None
                if sec is not None:
                    break
            if sec is None and shape and params:
                sec = _section_from_shape(name, shape, params)
            if sec is None:
                A = Sheet.num(r, c_A)
                if A:
                    sec = Section(name, A=A * f_A,
                                  Iy=(Sheet.num(r, c_Iy) or 0.0) * f_I or 1e-9,
                                  Iz=(Sheet.num(r, c_Iz) or 0.0) * f_I or 1e-9,
                                  It=(Sheet.num(r, c_It) or 0.0) * f_I or 1e-10,
                                  Iw=(Sheet.num(r, c_Iw) or 0.0) * f_Iw,
                                  Wel_y=(Sheet.num(r, c_Wy) or 0.0) * f_W,
                                  Wel_z=(Sheet.num(r, c_Wz) or 0.0) * f_W,
                                  Wpl_y=(Sheet.num(r, c_Wpy) or 0.0) * f_W,
                                  Wpl_z=(Sheet.num(r, c_Wpz) or 0.0) * f_W)
                    C.say(log, f"Querschnitt '{name}': Kennwerte aus Tabelle (freier Querschnitt)")
            if sec is None:
                C.warn(log, f"Querschnitt '{name}' (Profil '{profile}', Form '{shape}') nicht "
                            f"auswertbar - {C.DEFAULT_PROFILE} verwendet")
                sec = C.section_from_designation(C.DEFAULT_PROFILE, name)
            model.add_section(sec)
            sec_names[name] = sec.name
            sec_material[name] = material(Sheet.text(r, c_mat))
        C.say(log, f"SAF: {len(sec_names)} Querschnitte")

    # ---- Knoten ----------------------------------------------------------------
    node_idx: dict[str, int] = {}
    sh = sheets.get("pointconnection")
    if sh is not None:
        c_name = sh.col(r"^name$")
        c_x = sh.col(r"coordinate x", r"^x$")
        c_y = sh.col(r"coordinate y", r"^y$")
        c_z = sh.col(r"coordinate z", r"^z$")
        f = sh.unit(c_x, 1.0) * scale
        for r in sh.data():
            name = Sheet.text(r, c_name)
            if not name:
                continue
            xyz = [(Sheet.num(r, c) or 0.0) * f for c in (c_x, c_y, c_z)]
            node_idx[name] = nodes.add(*xyz)
        C.say(log, f"SAF: {len(node_idx)} Knoten")

    def node_of(name: str) -> Optional[int]:
        name = name.strip()
        if name in node_idx:
            return node_idx[name]
        for k, v in node_idx.items():          # Gross-/Kleinschreibung
            if k.lower() == name.lower():
                return v
        return None

    # ---- Staebe --------------------------------------------------------------------
    member_elems: dict[str, list[int]] = {}
    sh = sheets.get("curvemember")
    if sh is not None:
        c_name = sh.col(r"^name$")
        c_sec = sh.col(r"^cross ?section")
        c_nodes = sh.col(r"^nodes$", r"^nodes")
        c_n1 = sh.col(r"^begin ?node", r"^start ?node")
        c_n2 = sh.col(r"^end ?node")
        c_beh = sh.col(r"^behaviour", r"^behavior")
        c_lcs = sh.col(r"^lcs$")
        c_rot = sh.col(r"^lcs ?rotation", r"rotation")
        c_layer = sh.col(r"^layer$")
        c_vx = sh.col(r"^coordinate x", r"^lcs.*x$", r"^vector x")
        c_vy = sh.col(r"^coordinate y", r"^lcs.*y$", r"^vector y")
        c_vz = sh.col(r"^coordinate z", r"^lcs.*z$", r"^vector z")
        f_rot = sh.unit(c_rot, math.pi / 180.0)
        n_missing = 0
        for r in sh.data():
            name = Sheet.text(r, c_name)
            if not name:
                continue
            try:
                names = C.split_list(Sheet.text(r, c_nodes), r"[;,|]+")
                if len(names) < 2:
                    names = [Sheet.text(r, c_n1), Sheet.text(r, c_n2)]
                chain = []
                for nm in names:
                    n = node_of(nm)
                    if n is None:
                        raise KeyError(f"Knoten '{nm}' unbekannt")
                    if not chain or chain[-1] != n:
                        chain.append(n)
                if len(chain) < 2:
                    raise ValueError("weniger als zwei Knoten")
                sec_key = Sheet.text(r, c_sec)
                sec = sec_names.get(sec_key)
                if sec is None:
                    sec = C.ensure_section(model, sec_key, log)
                    sec_names[sec_key] = sec
                mat = sec_material.get(sec_key) or material("")
                beh = Sheet.text(r, c_beh).lower()
                typ = "beam"
                if "axial" in beh or "truss" in beh:
                    typ = "truss"
                elif "tension" in beh or "compression" in beh:
                    typ = "truss"
                    C.warn(log, f"Stab '{name}': Verhalten '{Sheet.text(r, c_beh)}' als "
                                f"linearer Fachwerkstab")
                roll = (Sheet.num(r, c_rot) or 0.0) * f_rot
                lcs = Sheet.text(r, c_lcs).lower()
                if "vector" in lcs and c_vx is not None:
                    v = np.array([Sheet.num(r, c) or 0.0 for c in (c_vx, c_vy, c_vz)])
                    if np.linalg.norm(v) > 0:
                        axis = "y" if lcs.startswith("y") else "z"
                        roll += C.roll_from_vector(nodes.get(chain[0]), nodes.get(chain[-1]),
                                                   v, axis)
                group = Sheet.text(r, c_layer) or "Staebe"
                elems = [model.add_element(typ, [a, b], mat, sec, roll=roll, group=group)
                         for a, b in zip(chain[:-1], chain[1:])]
                member_elems[name] = elems
                model.add_member(C.unique_name(model.members, name), elems)
            except Exception as ex:
                n_missing += 1
                C.warn(log, f"Stab '{name}' uebersprungen: {ex}")
        C.say(log, f"SAF: {len(member_elems)} Staebe")

    # ---- Flaechen ---------------------------------------------------------------------
    surface_elems: dict[str, list[int]] = {}
    sh = sheets.get("surfacemember")
    if sh is not None:
        c_name = sh.col(r"^name$")
        c_mat = sh.col(r"^material")
        c_t = sh.col(r"^thickness")
        c_nodes = sh.col(r"^nodes$", r"^nodes")
        c_layer = sh.col(r"^layer$")
        f_t = sh.unit(c_t, 1e-3)
        for r in sh.data():
            name = Sheet.text(r, c_name)
            if not name:
                continue
            try:
                ids = []
                for nm in C.split_list(Sheet.text(r, c_nodes), r"[;,|]+"):
                    n = node_of(nm)
                    if n is None:
                        raise KeyError(f"Knoten '{nm}' unbekannt")
                    ids.append(n)
                t = (Sheet.num(r, c_t) or 0.0) * f_t
                prop = C.ensure_shell_prop(model, f"t{t * 1e3:g}" if t > 0 else None,
                                           t if t > 0 else None, log)
                mat = material(Sheet.text(r, c_mat))
                group = Sheet.text(r, c_layer) or name
                surface_elems[name] = C.polygon_to_shells(model, ids, mat, prop, group, log,
                                                          f"Flaeche '{name}'")
            except Exception as ex:
                C.warn(log, f"Flaeche '{name}' uebersprungen: {ex}")
        C.say(log, f"SAF: {len(surface_elems)} Flaechen")
    nodes.flush()

    # ---- Lager ------------------------------------------------------------------------
    sh = sheets.get("pointsupport")
    if sh is not None:
        c_node = sh.col(r"^node$", r"^node", r"^point")
        c_dof = [sh.col(r"^ux$", r"^u ?x$"), sh.col(r"^uy$", r"^u ?y$"), sh.col(r"^uz$", r"^u ?z$"),
                 sh.col(r"^fix$", r"^fi ?x$", r"^phi ?x$", r"^rx$"),
                 sh.col(r"^fiy$", r"^fi ?y$", r"^phi ?y$", r"^ry$"),
                 sh.col(r"^fiz$", r"^fi ?z$", r"^phi ?z$", r"^rz$")]
        c_k = [sh.col(r"^stiffness ?x$", r"stiffness x\b"), sh.col(r"^stiffness ?y$", r"stiffness y\b"),
               sh.col(r"^stiffness ?z$", r"stiffness z\b"),
               sh.col(r"^stiffness ?fix$", r"stiffness (fix|phi ?x|rx)"),
               sh.col(r"^stiffness ?fiy$", r"stiffness (fiy|phi ?y|ry)"),
               sh.col(r"^stiffness ?fiz$", r"stiffness (fiz|phi ?z|rz)")]
        f_k = [sh.unit(c, 1e6) for c in c_k]
        c_cs = sh.col(r"^coordinate ?system")
        n_sup = 0
        for r in sh.data():
            nm = Sheet.text(r, c_node)
            n = node_of(nm)
            if n is None:
                if nm:
                    C.warn(log, f"Lager: Knoten '{nm}' unbekannt")
                continue
            if "local" in Sheet.text(r, c_cs).lower():
                C.warn(log, f"Lager an '{nm}': lokales Koordinatensystem wird als global gelesen")
            fixed, sdofs, sk = [], [], []
            for dof in range(6):
                v = Sheet.text(r, c_dof[dof]).lower()
                if not v or v.startswith("free") or v == "frei":
                    continue
                if v.startswith("flexible") or v.startswith("feder") or v.startswith("spring"):
                    k = (Sheet.num(r, c_k[dof]) or 0.0) * f_k[dof]
                    if "only" in v:
                        C.warn(log, f"Lager an '{nm}': '{v}' als lineare Feder")
                    if k > 0:
                        sdofs.append(dof)
                        sk.append(k)
                    continue
                if "only" in v or "non" in v:
                    C.warn(log, f"Lager an '{nm}': '{v}' als starres Lager (linear)")
                fixed.append(dof)
            if fixed:
                model.fix(n, fixed)
            if sdofs:
                model.fix(n, sdofs, stiffness=sk)
            if fixed or sdofs:
                n_sup += 1
        C.say(log, f"SAF: {n_sup} Knotenlager")

    # ---- Lastgruppen / Lastfaelle -------------------------------------------------------
    groups: dict[str, dict] = {}
    sh = sheets.get("loadgroup")
    if sh is not None:
        c_name = sh.col(r"^name$")
        c_gtype = sh.col(r"^load ?group ?type", r"^type$")
        c_rel = sh.col(r"^relation")
        c_ltype = sh.col(r"^load ?type")
        for r in sh.data():
            name = Sheet.text(r, c_name)
            if not name:
                continue
            groups[name] = {
                "cat": _lookup(_LOAD_TYPE_CAT, Sheet.text(r, c_ltype))
                       or _lookup(_GROUP_TYPE_CAT, Sheet.text(r, c_gtype)),
                "exclusive": Sheet.text(r, c_rel).lower().startswith("excl"),
            }
    case_names: dict[str, str] = {}
    sh = sheets.get("loadcase")
    if sh is not None:
        c_name = sh.col(r"^name$")
        c_act = sh.col(r"^action ?type")
        c_grp = sh.col(r"^load ?group")
        c_lt = sh.col(r"^load ?type")
        c_desc = sh.col(r"^description")
        for r in sh.data():
            name = Sheet.text(r, c_name)
            if not name:
                continue
            g = groups.get(Sheet.text(r, c_grp), {})
            ltype = Sheet.text(r, c_lt)
            cat = (_lookup(_LOAD_TYPE_CAT, ltype) or g.get("cat")
                   or _lookup(_GROUP_TYPE_CAT, Sheet.text(r, c_act)) or "Q")
            lc = C.get_or_add_case(model, C.unique_name(model.load_cases, name), cat,
                                   Sheet.text(r, c_desc))
            if g.get("exclusive"):
                lc.exclusive_group = Sheet.text(r, c_grp)
            if re.sub(r"[^a-z]", "", ltype.lower()).startswith("selfweight"):
                lc.gravity = [0.0, 0.0, -9.81]
                C.say(log, f"Lastfall '{name}': Eigengewicht (g = -9.81 m/s² in Z)")
            case_names[name] = lc.name
        C.say(log, f"SAF: {len(case_names)} Lastfaelle")

    def case_of(name: str) -> str:
        name = name.strip()
        if name in case_names:
            return case_names[name]
        if name:
            lc = C.get_or_add_case(model, name, "Q")
            case_names[name] = lc.name
            C.warn(log, f"Lastfall '{name}' nicht in StructuralLoadCase - angelegt (Q)")
            return lc.name
        return model.active_case

    # ---- Kombinationen -----------------------------------------------------------------
    sh = sheets.get("loadcombination")
    if sh is not None:
        c_name = sh.col(r"^name$")
        c_desc = sh.col(r"^description")
        c_cat = sh.col(r"^category", r"^type$")
        c_lc = sh.col(r"^load ?case$", r"^load ?case( ?1)?$")
        c_f = sh.col(r"^factor$", r"^factor( ?1)?$")
        combos: dict[str, dict] = {}
        for r in sh.data():
            name = Sheet.text(r, c_name)
            if not name:
                continue
            cb = combos.setdefault(name, {"factors": {}, "cat": Sheet.text(r, c_cat),
                                          "desc": Sheet.text(r, c_desc)})
            pairs = []
            if c_lc is not None:
                pairs.append((Sheet.text(r, c_lc), Sheet.num(r, c_f)))
            for i, key in enumerate(sh.keys):          # "load case 2" / "factor 2"
                m = re.match(r"^load ?case ?(\d+)$", key)
                if m and int(m.group(1)) > 1:
                    cf = sh.col(rf"^factor ?{m.group(1)}$")
                    pairs.append((Sheet.text(r, i), Sheet.num(r, cf)))
            for lc, f in pairs:
                if lc:
                    cb["factors"][case_of(lc)] = f if f is not None else 1.0
        for name, cb in combos.items():
            cat = cb["cat"].lower()
            typ = "ULS"
            if "sls" in cat or "service" in cat or "gzg" in cat:
                typ = "SLS_QP" if "quasi" in cat else ("SLS_FR" if "freq" in cat else "SLS_CH")
            elif "acc" in cat or "seism" in cat:
                typ = "ACC"
            elif "equ" in cat:
                typ = "EQU"
            model.add_combination(C.unique_name(model.combinations, name), cb["factors"],
                                  typ, cb["desc"] or cb["cat"])
        C.say(log, f"SAF: {len(combos)} Kombinationen")

    # ---- Knotenlasten (Kraefte und Momente) ---------------------------------------------
    for key, is_moment in (("pointaction", False), ("pointmoment", True)):
        sh = sheets.get(key)
        if sh is None:
            continue
        c_type = sh.col(r"^type$")
        c_fa = sh.col(r"^force ?action")
        c_dir = sh.col(r"^direction")
        c_val = sh.col(r"^value$", r"^value")
        c_lc = sh.col(r"^load ?case")
        c_node = sh.col(r"^point ?on ?node", r"^node$", r"^node")
        c_cs = sh.col(r"^coordinate ?system")
        f_val = sh.unit(c_val, 1e3)
        n_loads = 0
        for r in sh.data():
            try:
                fa = Sheet.text(r, c_fa).lower()
                nm = Sheet.text(r, c_node)
                n = node_of(nm)
                if n is None:
                    if "beam" in fa or "member" in fa or "edge" in fa:
                        C.warn(log, f"Punktlast '{Sheet.text(r, 0)}': Last auf Stab/Kante "
                                    f"wird nicht unterstuetzt")
                    else:
                        C.warn(log, f"Punktlast: Knoten '{nm}' unbekannt")
                    continue
                d = _direction_vector(Sheet.text(r, c_dir), r, sh)
                if d is None:
                    raise ValueError(f"Richtung '{Sheet.text(r, c_dir)}' unbekannt")
                if "local" in Sheet.text(r, c_cs).lower():
                    C.warn(log, f"Punktlast an '{nm}': lokale Richtung als global gelesen")
                val = (Sheet.num(r, c_val) or 0.0) * f_val
                moment = is_moment or "moment" in Sheet.text(r, c_type).lower()
                comp = (d * val).tolist()
                F = ([0.0, 0.0, 0.0] + comp) if moment else (comp + [0.0, 0.0, 0.0])
                model.load_node(n, *F, case=case_of(Sheet.text(r, c_lc)))
                n_loads += 1
            except Exception as ex:
                C.warn(log, f"Punktlast uebersprungen: {ex}")
        C.say(log, f"SAF: {n_loads} {'Knotenmomente' if is_moment else 'Knotenlasten'}")

    # ---- Streckenlasten -----------------------------------------------------------------
    sh = sheets.get("curveaction")
    if sh is not None:
        c_dist = sh.col(r"^distribution")
        c_dir = sh.col(r"^direction")
        c_v1 = sh.col(r"^value ?1$", r"^value$", r"^value ?1")
        c_v2 = sh.col(r"^value ?2")
        c_lc = sh.col(r"^load ?case")
        c_mem = sh.col(r"^member$", r"^member", r"^1d ?member")
        c_cs = sh.col(r"^coordinate ?system")
        c_loc = sh.col(r"^location")
        c_ext = sh.col(r"^extent")
        f_v = sh.unit(c_v1, 1e3)
        n_loads = 0
        for r in sh.data():
            try:
                mem = Sheet.text(r, c_mem)
                elems = member_elems.get(mem)
                if not elems:
                    raise KeyError(f"Stab '{mem}' unbekannt")
                d = _direction_vector(Sheet.text(r, c_dir), r, sh)
                if d is None:
                    raise ValueError(f"Richtung '{Sheet.text(r, c_dir)}' unbekannt")
                v1 = (Sheet.num(r, c_v1) or 0.0) * f_v
                v2 = Sheet.num(r, c_v2)
                v2 = v2 * f_v if (v2 is not None and "trapez" in Sheet.text(r, c_dist).lower()) else v1
                system = "local" if "local" in Sheet.text(r, c_cs).lower() else "global"
                if "proj" in Sheet.text(r, c_loc).lower():
                    C.warn(log, f"Streckenlast auf '{mem}': Projektion als wahre Laenge angesetzt")
                ext = Sheet.text(r, c_ext).lower()
                if ext and not ext.startswith("full") and not ext.startswith("span"):
                    C.warn(log, f"Streckenlast auf '{mem}': Teilbereich '{ext}' als Volllast")
                lengths = [model.element_length(e) for e in elems]
                total = sum(lengths) or 1.0
                pos = 0.0
                case = case_of(Sheet.text(r, c_lc))
                for e, L in zip(elems, lengths):
                    qa = (d * (v1 + (v2 - v1) * pos / total)).tolist()
                    qb = (d * (v1 + (v2 - v1) * (pos + L) / total)).tolist()
                    model.load_beam(e, *qa, system=system, case=case,
                                    q2=qb if qb != qa else None)
                    pos += L
                n_loads += 1
            except Exception as ex:
                C.warn(log, f"Streckenlast uebersprungen: {ex}")
        C.say(log, f"SAF: {n_loads} Streckenlasten")

    # ---- Flaechenlasten -------------------------------------------------------------------
    sh = sheets.get("surfaceaction")
    if sh is not None:
        c_dir = sh.col(r"^direction")
        c_val = sh.col(r"^value")
        c_lc = sh.col(r"^load ?case")
        c_mem = sh.col(r"^2d ?member", r"^member", r"^surface")
        c_cs = sh.col(r"^coordinate ?system")
        f_v = sh.unit(c_val, 1e3)
        n_loads = 0
        for r in sh.data():
            try:
                mem = Sheet.text(r, c_mem)
                elems = surface_elems.get(mem)
                if not elems:
                    raise KeyError(f"Flaeche '{mem}' unbekannt")
                val = (Sheet.num(r, c_val) or 0.0) * f_v
                dtxt = Sheet.text(r, c_dir)
                case = case_of(Sheet.text(r, c_lc))
                if "local" in Sheet.text(r, c_cs).lower():
                    if dtxt.strip().upper().lstrip("-") != "Z":
                        C.warn(log, f"Flaechenlast auf '{mem}': lokale Richtung {dtxt} "
                                    f"als Normalenrichtung")
                    sign = -1.0 if dtxt.strip().startswith("-") else 1.0
                    for e in elems:
                        model.load_face(e, sign * val, 0, case=case)
                else:
                    d = _direction_vector(dtxt, r, sh)
                    if d is None:
                        raise ValueError(f"Richtung '{dtxt}' unbekannt")
                    for e in elems:
                        model.load_face(e, val, 0, case=case, direction=d.tolist())
                n_loads += 1
            except Exception as ex:
                C.warn(log, f"Flaechenlast uebersprungen: {ex}")
        C.say(log, f"SAF: {n_loads} Flaechenlasten")

    known = {"projectinformation", "material", "crosssection", "pointconnection",
             "curvemember", "surfacemember", "pointsupport", "loadgroup", "loadcase",
             "loadcombination", "pointaction", "pointmoment", "curveaction", "surfaceaction"}
    other = [s.name for k, s in sheets.items() if k not in known and any(True for _ in s.data())]
    if other:
        C.say(log, "Nicht ausgewertete Blaetter: " + ", ".join(other))
    return model
