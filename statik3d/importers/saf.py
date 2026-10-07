"""
SAF-Import (Structural Analysis Format, Excel-basiert; RFEM 6, SCIA, Allplan,
AxisVM, ...).

Gelesen werden die Blaetter (Kopfzeile = erste Zeile, Spalten nach Namen,
Gross-/Kleinschreibung egal, fehlende optionale Spalten werden toleriert):
    StructuralMaterial, StructuralCrossSection, StructuralPointConnection,
    StructuralCurveMember, StructuralSurfaceMember, StructuralPointSupport,
    StructuralLoadGroup, StructuralLoadCase, StructuralLoadCombination,
    StructuralPointAction, StructuralPointMoment, StructuralCurveAction,
    StructuralSurfaceAction, StructuralCurveActionThermal,
    StructuralSurfaceActionThermal
Einheiten laut der Einheitentabelle der SAF-Beschreibung (gitbook.saf.guide,
gelesen 07.10.2026): Koordinaten m, Querschnittsparameter mm, A m², I m⁴,
Iw m⁶, Wpl m³, Dicken mm, E- und G-Modul MPa, Lasten kN / kN/m / kN/m²,
Momente kNm, Temperaturen °C, Federn MN/m bzw. MNm/rad. Bis zum 07.10.2026 las
der Import A, I und W ohne Einheit in der Kopfzeile als mm², mm⁴, mm³ - die
SAF-Beschreibung fuehrt sie in m² (Fehlerliste-Nachtrag N26).
Abweichende Einheiten in eckigen Klammern der Kopfzeile werden erkannt.
Globales Z zeigt nach oben (Eigengewicht -> g = -9.81 m/s² in Z).

Eine SAF-Datei, die Statik3D vor dem 07.10.2026 schrieb, traegt im Blatt der
Werkstoffe die Spalte "Yield strength" (SAF kennt sie nicht, dort heisst es
"Design properties"). Ihre Werte stehen in SI ohne Einheit: E und G in Pa,
Dicken in m, Knotenlasten als Spalten Fx ... Mz in N und Nm. So wird sie
gelesen, und das Protokoll sagt es.

Stablasten (StructuralCurveAction): Uniform und Trapez, ueber die ganze Laenge
(Extent Full) oder einen Abschnitt (Extent Span mit Start und End point,
Coordinate definition Absolute in m oder Relative als Anteil 0 bis 1 der
Stablaenge, Origin From start oder From end). Bis zum 06.10.2026 wurde jeder
Span ohne ein Wort als Volllast gelesen.
Kombinationen: die Spalte "Envelope" (eine Erweiterung von Statik3D, siehe
exporters/saf.py) fasst Alternativen wieder zu einer Ergebniskombination
zusammen; der Faktor heisst "Factor" (aeltere Dateien von Statik3D: "Coefficient").
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
    # SAF-Beschreibung (Annex "Supported shapes of parametric cross-section"):
    # I rolled H; B; t; s; R - t Flansch, s Steg; so schreibt es der Export
    "irolled": ("I", ("h", "b", "tf", "tw", "r")),
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


def _positionen(r: list, sh: Sheet, c_def, c_org, c_p1, c_p2, total: float) -> tuple:
    """Start und End point eines Teilbereichs [m vom Stabanfang] - Coordinate
    definition Absolute (m) oder Relative (Anteil 0 bis 1 der Stablaenge),
    Origin From start oder From end. Rueckgabe ``(p1, p2, relativ)``; p1 > p2
    ist moeglich (From end). ValueError, wenn die Positionen fehlen oder
    relative Werte nicht zwischen 0 und 1 liegen."""
    p1, p2 = Sheet.num(r, c_p1), Sheet.num(r, c_p2)
    if p1 is None or p2 is None:
        raise ValueError("Teilbereich (Span) ohne Start point und End point - "
                         "nicht übernommen, eine Volllast wäre geraten")
    relativ = Sheet.text(r, c_def).lower().startswith("rel")
    if relativ:
        if not (-1e-9 <= p1 <= 1 + 1e-9 and -1e-9 <= p2 <= 1 + 1e-9):
            raise ValueError(f"relative Positionen {p1:g} und {p2:g} liegen nicht "
                             "zwischen 0 und 1 - nicht übernommen")
        p1, p2 = p1 * total, p2 * total
    else:
        f_p = sh.unit(c_p1, 1.0)
        p1, p2 = p1 * f_p, p2 * f_p
    if "end" in Sheet.text(r, c_org).lower():       # From end: vom Stabende gezaehlt
        p1, p2 = total - p1, total - p2
    return p1, p2, relativ


def _direction_vector(text: str, row: list, sh: Sheet) -> Optional[np.ndarray]:
    s = text.strip().upper()
    if re.fullmatch(r"-?M[XYZ]", s):      # StructuralPointMoment: Direction Mx/My/Mz (N25)
        s = s.replace("M", "")
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


def _leerer_vorgabelastfall(model: Model) -> Optional[str]:
    """Der Name des leeren Vorgabelastfalls, wenn das Modell noch leer ist
    (keine Knoten, Elemente, Kombinationen, Ermuedungslasten; genau ein
    Lastfall ohne Lasten - so legt ``Model()`` LF1 an), sonst None.

    Diesen Lastfall ersetzt der gleichnamige Lastfall der Datei. Bis zum
    07.10.2026 bekam der Lastfall LF1 der Datei beim Import in ein frisches
    Modell den Namen "LF1_2" (unique_name), der leere LF1 fiel erst am Ende
    weg (importers.import_file), und die Kombinationen zeigten auf LF1_2
    (Fehlerliste-Nachtrag N29). Beim Anhaengen an ein Modell mit Inhalt bleibt
    dessen LF1 unberuehrt."""
    if model.nn or model.elements or model.combinations or getattr(model, "fatigue_loads", None):
        return None
    if len(model.load_cases) != 1:
        return None
    name, lc = next(iter(model.load_cases.items()))
    return None if lc.n_loads else name


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
    vorgabe = _leerer_vorgabelastfall(model)
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
    # Datei von Statik3D vor dem 07.10.2026 (Spalte "Yield strength", die SAF
    # nicht kennt): Werte in SI ohne Einheit (siehe oben)
    alt = sh is not None and sh.col(r"^yield ?strength") is not None
    if alt:
        C.say(log, "SAF-Datei von Statik3D vor dem 07.10.2026 erkannt (Spalte „Yield strength“): "
                   "E-Modul in Pa, Dicken in m und Knotenlasten in N gelesen")
    if sh is not None:
        c_name = sh.col(r"^name$")
        c_type = sh.col(r"^type$")
        c_qual = sh.col(r"^quality")
        c_rho = sh.col(r"unit ?mass|density|dichte")
        c_E = sh.col(r"^e ?modul", r"modulus of elasticity", r"^e$")
        c_nu = sh.col(r"poisson")
        c_al = sh.col(r"thermal ?expansion|expansion")
        c_dp = sh.col(r"^design ?properties")
        c_fy_alt = sh.col(r"^yield ?strength") if alt else None       # Pa, ohne Einheit
        c_fu_alt = sh.col(r"^ultimate ?strength") if alt else None
        f_E = sh.unit(c_E, 1.0 if alt else 1e6)
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
            # "Design properties": "1|355; 2|490" - Index 1 f_y, 2 f_u in MPa
            # (Annex "Supported design properties of the materials"); so
            # schreibt der Export sie seit dem 07.10.2026 (N26)
            for teil in C.split_list(Sheet.text(r, c_dp), r";"):
                k, _, v = teil.partition("|")
                wert = C.parse_number(v)
                if wert is not None and k.strip() in ("1", "2"):
                    setattr(m, "fy" if k.strip() == "1" else "fu", wert * 1e6)
            for c, feld in ((c_fy_alt, "fy"), (c_fu_alt, "fu")):
                wert = Sheet.num(r, c)
                if wert:
                    setattr(m, feld, wert)
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
        c_Iy = sh.col(r"^i ?y$")             # "I y": Statik3D vor dem 07.10.2026
        c_Iz = sh.col(r"^i ?z$")
        c_It = sh.col(r"^i ?t$")
        c_Iw = sh.col(r"^iw$")
        c_Wy = sh.col(r"^wely$")
        c_Wz = sh.col(r"^welz$")
        c_Wpy = sh.col(r"^wply$")
        c_Wpz = sh.col(r"^wplz$")
        c_art = sh.col(r"^cross ?section ?type")
        f_par = sh.unit(c_par, 1e-3)
        # ohne Einheit in der Kopfzeile: die Einheiten der SAF-Beschreibung
        # (A m², I m⁴, Iw m⁶, W m³); bis zum 07.10.2026 hier mm², mm⁴, mm⁶, mm³
        f_A = sh.unit(c_A, 1.0)
        f_I = sh.unit(c_Iy, 1.0)
        f_Iw = sh.unit(c_Iw, 1.0)
        f_We = sh.unit(c_Wy, 1.0)
        f_Wp = sh.unit(c_Wpy, 1.0)
        for r in sh.data():
            name = Sheet.text(r, c_name)
            if not name:
                continue
            profile = Sheet.text(r, c_prof)
            shape = Sheet.text(r, c_shape)
            params = [v * f_par for v in (C.parse_number(p) for p in
                                          C.split_list(Sheet.text(r, c_par), r"[;|]"))
                      if v is not None]
            # Cross-section type (SAF): Parametric baut aus Form und
            # Abmessungen, General nimmt die Kennwerte - beide nicht aus der
            # Datenbank, auch wenn der Name ein Profil nennt (ein HEA 200 ohne
            # Ausrundung kam sonst mit A = 53,8 statt 51,1 cm² zurueck, N26).
            # Manufactured und ohne Angabe: zuerst die Datenbank wie bisher
            art = re.sub(r"[^a-z]", "", Sheet.text(r, c_art).lower())
            sec = None
            if art.startswith("parametric") and shape and params:
                sec = _section_from_shape(name, shape, params)
            elif not art.startswith("general") and not art.startswith("parametric"):
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
                                  Wel_y=(Sheet.num(r, c_Wy) or 0.0) * f_We,
                                  Wel_z=(Sheet.num(r, c_Wz) or 0.0) * f_We,
                                  Wpl_y=(Sheet.num(r, c_Wpy) or 0.0) * f_Wp,
                                  Wpl_z=(Sheet.num(r, c_Wpz) or 0.0) * f_Wp)
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
        f_t = sh.unit(c_t, 1.0 if alt else 1e-3)
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
            if name == vorgabe:
                # der leere Vorgabelastfall des frischen Modells weicht dem
                # gleichnamigen der Datei (N29, siehe _leerer_vorgabelastfall)
                model.load_cases.pop(vorgabe)
                vorgabe = None
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
        if vorgabe is not None and case_names:
            C.drop_empty_default_case(model, vorgabe)

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
        # Der Export von Statik3D schrieb bis zum 06.10.2026 "Coefficient", der
        # Import las nur "Factor": jeder Faktor kam als 1,0 zurueck. Der Export
        # schreibt jetzt "Factor"; "Coefficient" lesen wir weiter, damit eine so
        # geschriebene Datei nicht mit lauter 1,0 hereinkommt
        c_f = sh.col(r"^factor$", r"^factor( ?1)?$", r"^coeff")
        c_env = sh.col(r"^envelope")
        combos: dict[str, dict] = {}
        for r in sh.data():
            name = Sheet.text(r, c_name)
            if not name:
                continue
            cb = combos.setdefault(name, {"factors": {}, "cat": Sheet.text(r, c_cat),
                                          "desc": Sheet.text(r, c_desc),
                                          "env": Sheet.text(r, c_env)})
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
        huellen: dict[str, object] = {}      # Spalte "Envelope" -> Ergebniskombination
        for name, cb in combos.items():
            cat = cb["cat"].lower()
            typ = "ULS"
            if "sls" in cat or "service" in cat or "gzg" in cat:
                typ = "SLS_QP" if "quasi" in cat else ("SLS_FR" if "freq" in cat else "SLS_CH")
            elif "acc" in cat or "seism" in cat:
                typ = "ACC"
            elif "equ" in cat:
                typ = "EQU"
            if cb["env"]:
                # eine Alternative einer Ergebniskombination (F26): die erste legt sie
                # an, jede weitere kommt als Alternative dazu - nicht als eigene Summe
                ek = huellen.get(cb["env"])
                if ek is None:
                    huellen[cb["env"]] = model.add_combination(
                        C.unique_name(model.combinations, cb["env"]), {}, typ,
                        cb["desc"] or cb["cat"], alternativen=[cb["factors"]])
                else:
                    ek.alternativen.append(cb["factors"])
                continue
            model.add_combination(C.unique_name(model.combinations, name), cb["factors"],
                                  typ, cb["desc"] or cb["cat"])
        n_alt = sum(len(e.alternativen) for e in huellen.values())
        C.say(log, f"SAF: {len(combos) - n_alt + len(huellen)} Kombinationen"
                   + (f" (davon {len(huellen)} Ergebniskombination"
                      f"{'en' if len(huellen) != 1 else ''} aus {n_alt} Alternativen)" if huellen else ""))

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
        # "Reference node" ist der Spaltenname der SAF-Beschreibung (N25)
        c_node = sh.col(r"^reference ?node", r"^point ?on ?node", r"^node$", r"^node")
        c_cs = sh.col(r"^coordinate ?system")
        f_val = sh.unit(c_val, 1e3)
        # Statik3D vor dem 07.10.2026: je Knotenlast eine Zeile mit den Spalten
        # Fx ... Mz in N und Nm, ohne Direction und Value
        c_komp = [sh.col(rf"^{k}$") for k in ("fx", "fy", "fz", "mx", "my", "mz")]
        alt_spalten = alt and c_dir is None and c_val is None and c_komp[0] is not None
        n_loads = 0
        for r in sh.data():
            try:
                if alt_spalten:
                    n = node_of(Sheet.text(r, c_node))
                    if n is None:
                        raise KeyError(f"Knoten '{Sheet.text(r, c_node)}' unbekannt")
                    F = [(Sheet.num(r, c) or 0.0) * sh.unit(c, 1.0) for c in c_komp]
                    model.load_node(n, *F, case=case_of(Sheet.text(r, c_lc)))
                    n_loads += 1
                    continue
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
        c_def = sh.col(r"^coordinate ?definition")
        c_org = sh.col(r"^origin")
        c_p1 = sh.col(r"^start ?point")
        c_p2 = sh.col(r"^end ?point")
        f_v = sh.unit(c_v1, 1e3)
        n_loads = 0
        relativ_gemeldet = False
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
                lengths = [model.element_length(e) for e in elems]
                total = sum(lengths) or 1.0
                # Bereich der Last entlang des Stabes: x1 bis x2 mit w1 bei x1 und w2
                # bei x2 (Value 1 gehoert zum Start point, Value 2 zum End point)
                x1, x2, w1, w2 = 0.0, total, v1, v2
                if ext.startswith("span"):
                    p1, p2, relativ = _positionen(r, sh, c_def, c_org, c_p1, c_p2, total)
                    if relativ and not relativ_gemeldet:
                        relativ_gemeldet = True
                        C.say(log, "SAF: Positionen mit Coordinate definition Relative als "
                                   "Anteil 0 bis 1 der Stablänge gelesen")
                    if p1 <= p2:
                        x1, x2 = p1, p2
                    else:
                        x1, x2, w1, w2 = p2, p1, v2, v1
                    if x2 - x1 <= 1e-9 * total:
                        raise ValueError("Teilbereich (Span) ohne Länge - nicht übernommen")
                    if x1 < -1e-9 * total or x2 > total * (1 + 1e-9):
                        raise ValueError(f"Teilbereich {x1:g} m bis {x2:g} m liegt nicht auf dem Stab "
                                         f"({total:g} m) - nicht übernommen")
                elif ext and not ext.startswith("full"):
                    C.warn(log, f"Streckenlast auf '{mem}': Teilbereich '{ext}' als Volllast")
                tol = 1e-9 * total
                pos = 0.0
                case = case_of(Sheet.text(r, c_lc))
                for e, L in zip(elems, lengths):
                    s, t = max(pos, x1), min(pos + L, x2)
                    if t - s > tol:
                        qa = (d * (w1 + (w2 - w1) * (s - x1) / (x2 - x1))).tolist()
                        qb = (d * (w1 + (w2 - w1) * (t - x1) / (x2 - x1))).tolist()
                        a, b = s - pos, t - pos
                        ganz_b = b >= L - tol
                        model.load_beam(e, *qa, system=system, case=case,
                                        q2=qb if qb != qa else None,
                                        a=0.0 if a <= tol else a, b=None if ganz_b else b)
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

    # ---- Temperaturlasten (N28) ---------------------------------------------------------
    # Staebe (StructuralCurveActionThermal): Constant mit deltaT, Linear mit
    # TempL/TempR/TempT/TempB. Die Rechnung kennt dT (Mitte) und
    # dT_z = T(+z) - T(-z) = TempT - TempB; einen Unterschied zwischen links und
    # rechts (lokales y) kennt sie nicht - das Protokoll sagt es. Die Last gilt
    # je ganzes Element; ein Element, das der Bereich nur zum Teil deckt,
    # bekommt sie nicht (gemeldet). Schalen (StructuralSurfaceActionThermal):
    # Constant mit TempT als dT, Linear mit TempT/TempB.
    sh = sheets.get("curveactionthermal")
    if sh is not None:
        c_var = sh.col(r"^variation")
        c_dT = sh.col(r"^delta ?t$")
        c_TL, c_TR, c_TT, c_TB = (sh.col(rf"^temp ?{k}$") for k in "lrtb")
        c_mem = sh.col(r"^member$", r"^member", r"^1d ?member")
        c_lc = sh.col(r"^load ?case")
        c_def = sh.col(r"^coordinate ?definition")
        c_org = sh.col(r"^origin")
        c_p1 = sh.col(r"^start ?point")
        c_p2 = sh.col(r"^end ?point")
        n_loads = 0
        for r in sh.data():
            try:
                mem = Sheet.text(r, c_mem)
                elems = member_elems.get(mem)
                if not elems:
                    raise KeyError(f"Stab '{mem}' unbekannt")
                if Sheet.text(r, c_var).lower().startswith("lin"):
                    tt, tb = Sheet.num(r, c_TT), Sheet.num(r, c_TB)
                    if tt is None or tb is None:
                        raise ValueError("Variation Linear ohne TempT und TempB")
                    dT, dTz = (tt + tb) / 2.0, tt - tb
                    tl, tr = Sheet.num(r, c_TL), Sheet.num(r, c_TR)
                    if tl is not None and tr is not None and (
                            abs(tl - tr) > 1e-9 * max(1.0, abs(tl), abs(tr))
                            or abs((tl + tr) / 2.0 - dT) > 1e-9 * max(1.0, abs(dT))):
                        C.warn(log, f"Temperaturlast auf '{mem}': links {tl:g} °C, rechts {tr:g} °C - einen "
                                    "Unterschied über die Breite (lokales y) kennt Statik3D nicht; "
                                    f"übernommen sind Mitte {dT:g} °C und oben minus unten {dTz:g} K")
                else:
                    dT, dTz = Sheet.num(r, c_dT), 0.0
                    if dT is None:
                        raise ValueError("Variation Constant ohne deltaT")
                lengths = [model.element_length(e) for e in elems]
                total = sum(lengths) or 1.0
                x1, x2 = 0.0, total
                if Sheet.text(r, c_p1) or Sheet.text(r, c_p2):
                    p1, p2, _rel = _positionen(r, sh, c_def, c_org, c_p1, c_p2, total)
                    x1, x2 = min(p1, p2), max(p1, p2)
                tol = 1e-9 * total
                case = case_of(Sheet.text(r, c_lc))
                pos, teils = 0.0, 0
                for e, L in zip(elems, lengths):
                    s, t = max(pos, x1), min(pos + L, x2)
                    if t - s > tol:
                        if s - pos > tol or pos + L - t > tol:
                            teils += 1
                        else:
                            model.load_temp(e, dT, dTz, case=case)
                    pos += L
                if teils:
                    C.warn(log, f"Temperaturlast auf '{mem}' ({x1:g} m bis {x2:g} m): {teils} Element"
                                f"{'e' if teils != 1 else ''} nur zum Teil gedeckt - dort nicht übernommen "
                                "(Statik3D trägt eine Temperaturlast je ganzes Element)")
                n_loads += 1
            except Exception as ex:
                C.warn(log, f"Temperaturlast uebersprungen: {ex}")
        C.say(log, f"SAF: {n_loads} Temperaturlasten auf Staeben")
    sh = sheets.get("surfaceactionthermal")
    if sh is not None:
        c_var = sh.col(r"^variation")
        c_TT = sh.col(r"^temp ?t$", r"^t1$")
        c_TB = sh.col(r"^temp ?b$", r"^t2$")
        c_mem = sh.col(r"^2d ?member$", r"^member$", r"^surface")
        c_lc = sh.col(r"^load ?case")
        n_loads = 0
        for r in sh.data():
            try:
                mem = Sheet.text(r, c_mem)
                elems = surface_elems.get(mem)
                if not elems:
                    raise KeyError(f"Flaeche '{mem}' unbekannt")
                tt = Sheet.num(r, c_TT)
                if tt is None:
                    raise ValueError("ohne TempT")
                if Sheet.text(r, c_var).lower().startswith("lin"):
                    tb = Sheet.num(r, c_TB)
                    if tb is None:
                        raise ValueError("Variation Linear ohne TempB")
                    dT, dTz = (tt + tb) / 2.0, tt - tb
                else:
                    dT, dTz = tt, 0.0
                case = case_of(Sheet.text(r, c_lc))
                for e in elems:
                    model.load_temp(e, dT, dTz, case=case)
                n_loads += 1
            except Exception as ex:
                C.warn(log, f"Temperaturlast uebersprungen: {ex}")
        C.say(log, f"SAF: {n_loads} Temperaturlasten auf Flaechen")

    known = {"projectinformation", "material", "crosssection", "pointconnection",
             "curvemember", "surfacemember", "pointsupport", "loadgroup", "loadcase",
             "loadcombination", "pointaction", "pointmoment", "curveaction", "surfaceaction",
             "curveactionthermal", "surfaceactionthermal"}
    other = [s.name for k, s in sheets.items() if k not in known and any(True for _ in s.data())]
    if other:
        C.say(log, "Nicht ausgewertete Blaetter: " + ", ".join(other))
    return model
