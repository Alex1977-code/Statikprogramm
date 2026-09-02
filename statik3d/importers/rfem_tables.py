"""
Dlubal RFEM 5/6 und RSTAB: Tabellenexport nach Excel (xlsx) oder CSV
("Tabellen exportieren").

Erkannte Tabellen (Blatt- bzw. Dateiname, deutsch/englisch):
    1.1 Knoten / Nodes            1.2 Linien / Lines           1.3 Materialien / Materials
    1.4 Flaechen / Surfaces       1.5 Querschnitte / Cross-Sections
    1.7 Staebe / Members          1.8 Knotenlager / Nodal Supports
    2.1 Lastfaelle / Load Cases   2.5 Lastkombinationen / Load Combinations
    3.1 Knotenlasten / Nodal Loads   3.2 Stablasten / Member Loads
Die Kopfzeile wird ueber Schluesselwoerter gesucht (auch zwei- oder dreizeilige
Kopfzeilen mit verbundenen Zellen). Einheiten in eckigen Klammern ([kN], [mm],
[kN/cm²] ...) werden ausgewertet. Staebe verweisen auf Linien (RFEM) oder direkt auf
Knoten (RSTAB). Querschnittsnamen wie 'IPE 200', 'HE A 200', 'QRO 100x5',
'RO 168.3x5' werden ueber die Profildatenbank aufgeloest.
Lastfaelle in Lasttabellen: Spalte 'Lastfall'/'LF' oder Blocktitel-Zeilen ('LF1 ...').
Koordinaten werden unveraendert uebernommen (RFEM: Z meist nach unten; Option
z_up=True kehrt das Eigengewicht um).
"""
from __future__ import annotations

import math
import os
import re
from typing import Optional

from ..model import Model, Material, Section
from . import _common as C
from .xlsx_reader import read_table_file, read_csv_table

DEFAULT_UNIT_SCALE = 1.0

# --------------------------------------------------------------------------
# Tabellenerkennung
# --------------------------------------------------------------------------
_SHEET_KINDS = [
    ("supports", r"knotenlager|nodal support|node support"),
    ("nodal_loads", r"knotenlast|nodal load|node load"),
    ("member_loads", r"stablast|member load"),
    ("surface_loads", r"flaechenlast|surface load"),
    ("load_cases", r"lastfall|lastfaelle|load case"),
    ("combinations", r"lastkombination|load combination"),
    ("skip", r"einwirkungskombination|action combination|ergebnis|result|lastsatz"),
    ("nodes", r"^(\d+(\.\d+)? )?(knoten|nodes?)$|\bknoten\b|\bnodes?\b"),
    ("lines", r"\blinien?\b|\blines?\b"),
    ("materials", r"material"),
    ("surfaces", r"flaeche|surface"),
    ("sections", r"querschnitt|cross ?section"),
    ("members", r"\bstab\b|\bstaebe\b|\bmembers?\b"),
]
_SHEET_NUMBERS = {"1.1": "nodes", "1.2": "lines", "1.3": "materials", "1.4": "surfaces",
                  "1.5": "sections", "1.7": "members", "1.8": "supports",
                  "2.1": "load_cases", "2.5": "combinations", "3.1": "nodal_loads",
                  "3.2": "member_loads"}


def classify_sheet(name: str) -> Optional[str]:
    key = C.norm_key(name)
    for kind, pat in _SHEET_KINDS:
        if re.search(pat, key):
            return None if kind == "skip" else kind
    m = re.match(r"^(\d+\.\d+)", name.strip())
    if m:
        return _SHEET_NUMBERS.get(m.group(1))
    return None


# Spaltenmuster (Regex auf normalisierten Kopftext)
_NO = [r"^(nr|no|number)$"]
SPECS: dict[str, dict] = {
    "nodes": {
        "no": [r"^(knoten|node)s?\s*(nr|no|number)?$"] + _NO,
        "x": [r"koordinat\w*\s+x$", r"coordinat\w*\s+x$", r"^x$"],
        "y": [r"koordinat\w*\s+y$", r"coordinat\w*\s+y$", r"^y$"],
        "z": [r"koordinat\w*\s+z$", r"coordinat\w*\s+z$", r"^z$"],
    },
    "lines": {
        "no": [r"^(linie|line)s?\s*(nr|no)?$"] + _NO,
        "type": [r"(linien|line)\s*(typ|type)$", r"^(typ|type)$"],
        "nodes": [r"^(knoten|node)s?\s*(nr|no)?$", r"(knoten|node)"],
    },
    "materials": {
        "no": [r"^(material)s?\s*(nr|no)?$"] + _NO,
        "name": [r"bezeichnung|description|^name$"],
        "E": [r"^e\s*modul", r"modulus of elasticity", r"^e$"],
        "G": [r"schubmodul|shear modulus|^g$"],
        "nu": [r"poisson|querdehn|^nu$"],
        "gamma": [r"spez\w*\s*gewicht|specific weight|wichte|^gamma$"],
        "rho": [r"dichte|density|^rho$"],
        "alpha": [r"temp\w*\s*dehn|thermal exp|expansion|^alpha$"],
    },
    "surfaces": {
        "no": [r"^(flaeche|surface)s?\s*(nr|no)?$"] + _NO,
        "type": [r"(flaechen|surface)\s*(typ|type)$", r"^(typ|type)$"],
        "lines": [r"begrenzungslinien|boundary lines|^(linien|lines)"],
        "mat": [r"^material"],
        "t": [r"dicke|thickness"],
    },
    "sections": {
        "no": [r"^(querschnitt|cross section|section)s?\s*(nr|no)?$"] + _NO,
        "name": [r"bezeichnung|description|^name$"],
        "mat": [r"^material"],
        "A": [r"^a$", r"querschnittsflaeche|cross section area|flaeche a$|area a$"],
        "Iy": [r"^iy$", r"\biy$"],
        "Iz": [r"^iz$", r"\biz$"],
        "It": [r"^it$", r"\bit$", r"^j$", r"torsion"],
    },
    "members": {
        "no": [r"^(stab|member)s?\s*(nr|no)?$"] + _NO,
        "type": [r"(stab|member)\s*(typ|type)$", r"^(typ|type)$"],
        "line": [r"^(linie|line)s?\s*(nr|no)?$"],
        "n1": [r"(knoten|node)\w*\s*(nr|no)?\s*(anfang|start|begin|i)$",
               r"^(anfang|start|begin)$", r"(anfang|start).*(knoten|node)"],
        "n2": [r"(knoten|node)\w*\s*(nr|no)?\s*(ende|end|j)$",
               r"^(ende|end)$", r"(ende|end).*(knoten|node)"],
        "sec1": [r"(querschnitt|cross section|section)\w*\s*(nr|no)?\s*(anfang|start|begin)$",
                 r"^(querschnitt|cross section|section)s?\s*(nr|no)?$"],
        "sec2": [r"(querschnitt|cross section|section)\w*\s*(nr|no)?\s*(ende|end)$"],
        "beta": [r"drehung|rotation|^beta$"],
    },
    "supports": {
        "no": [r"^(knotenlager|lager|nodal support|support)s?\s*(nr|no)?$"] + _NO,
        "nodes": [r"^(an )?(knoten|node)s?\s*(nr|no)?$", r"(knoten|node)"],
        "ux": [r"\bux\b", r"\bu\s?x\b"], "uy": [r"\buy\b", r"\bu\s?y\b"], "uz": [r"\buz\b", r"\bu\s?z\b"],
        "rx": [r"\bphix\b", r"\bphi\s?x\b", r"\brx\b", r"rot\w*\s*x\b"],
        "ry": [r"\bphiy\b", r"\bphi\s?y\b", r"\bry\b", r"rot\w*\s*y\b"],
        "rz": [r"\bphiz\b", r"\bphi\s?z\b", r"\brz\b", r"rot\w*\s*z\b"],
    },
    "load_cases": {
        "no": [r"^(lastfall|load case|lf|lc)s?\s*(nr|no)?$"] + _NO,
        "name": [r"bezeichnung|description|^name$"],
        "cat": [r"einwirkung|action|kategorie|category|(lastfall|load case)\s*(typ|type)",
                r"^(typ|type)$"],
        "sw": [r"eigengewicht|self ?weight"],
        "fx": [r"(faktor|factor)\w*\s*(in richtung|in direction)?\s*x$"],
        "fy": [r"(faktor|factor)\w*\s*(in richtung|in direction)?\s*y$"],
        "fz": [r"(faktor|factor)\w*\s*(in richtung|in direction)?\s*z$"],
    },
    "combinations": {
        "no": [r"^(lastkombination|load combination|lk|co)s?\s*(nr|no)?$"] + _NO,
        "name": [r"bezeichnung|description|^name$"],
        "situation": [r"bemessungssituation|design situation", r"^(typ|type)$"],
        "formula": [r"belastung|loading|^kombination|combination|lastfaelle|load cases"],
    },
    "nodal_loads": {
        "no": [r"^(knotenlast|nodal load|last|load)s?\s*(nr|no)?$"] + _NO,
        "case": [r"^(lastfall|load case|lf|lc)\b"],
        "nodes": [r"^(an )?(knoten|node)s?\s*(nr|no)?$", r"(knoten|node)"],
        "fx": [r"\bfx\b"], "fy": [r"\bfy\b"], "fz": [r"\bfz\b"],
        "mx": [r"\bmx\b"], "my": [r"\bmy\b"], "mz": [r"\bmz\b"],
    },
    "member_loads": {
        "no": [r"^(stablast|member load|last|load)s?\s*(nr|no)?$"] + _NO,
        "case": [r"^(lastfall|load case|lf|lc)\b"],
        "members": [r"^(an )?(staebe|stab|member)s?\s*(nr|no)?$", r"(staebe|stab|member)"],
        "kind": [r"lastart|load type"],
        "distribution": [r"lastverlauf|load distribution|verlauf|distribution"],
        "direction": [r"lastrichtung|load direction|richtung|direction"],
        "reflen": [r"bezugslaenge|reference length"],
        "p1": [r"\bp1\b", r"^p$", r"lastparameter", r"magnitude"],
        "p2": [r"\bp2\b"],
    },
}
REQUIRED = {"nodes": ["x", "y"], "lines": ["nodes"], "materials": ["name"],
            "surfaces": ["lines"], "sections": ["name"], "members": [],
            "supports": ["nodes"], "load_cases": ["no"], "combinations": ["formula"],
            "nodal_loads": ["nodes"], "member_loads": ["members", "p1"]}
_BLOCK_TITLE = re.compile(r"^(LF|LC|CO|LK|EK|RC)\s*(\d+)\b", re.IGNORECASE)


class Table:
    """Tabelle mit erkannter Kopfzeile."""

    def __init__(self, name: str, rows: list[list], kind: str):
        self.name = name
        self.rows = rows
        self.kind = kind
        self.cols: dict[str, int] = {}
        self.raw: dict[str, str] = {}
        self.start = len(rows)
        self.ok = False
        spec = SPECS[kind]
        required = REQUIRED[kind]
        best = None
        for i in range(min(len(rows), 15)):
            for span in (1, 2, 3):
                if i + span > len(rows):
                    break
                hdr = self._merge(rows[i:i + span])
                keys = [C.norm_key(h) for h in hdr]
                cols: dict[str, int] = {}
                for key, patterns in spec.items():
                    for pat in patterns:
                        rx = re.compile(pat)
                        hit = next((j for j, k in enumerate(keys)
                                    if k and rx.search(k) and j not in cols.values()), None)
                        if hit is not None:
                            cols[key] = hit
                            break
                n_req = sum(1 for k in required if k in cols)
                score = n_req * 10 + len(cols)
                if n_req == len(required) and len(cols) >= 2 and \
                        (best is None or score > best[0]):
                    best = (score, i, span, cols, hdr)
        if best is not None:
            _, i, span, self.cols, hdr = best
            self.raw = {k: hdr[j] for k, j in self.cols.items()}
            self.start = i + span
            self.ok = True

    @staticmethod
    def _merge(rows: list[list]) -> list[str]:
        width = max((len(r) for r in rows), default=0)
        texts = []
        for k, r in enumerate(rows):
            t = [C.clean_text(c) if c is not None else "" for c in r] + [""] * (width - len(r))
            if k < len(rows) - 1:                      # verbundene Zellen nach rechts fuellen
                last = ""
                for j in range(width):
                    if t[j]:
                        last = t[j]
                    else:
                        t[j] = last
            texts.append(t)
        return [" ".join(t[j] for t in texts if t[j]).strip() for j in range(width)]

    def has(self, key: str) -> bool:
        return key in self.cols

    def unit(self, key: str, default: float) -> float:
        return C.unit_factor(self.raw.get(key, ""), default)

    def text(self, row: list, key: str) -> str:
        j = self.cols.get(key)
        if j is None or j >= len(row):
            return ""
        return C.clean_text(row[j])

    def num(self, row: list, key: str) -> Optional[float]:
        j = self.cols.get(key)
        if j is None or j >= len(row):
            return None
        return C.parse_number(row[j])

    def data(self):
        """(Zeile, Blocktitel) - Blocktitel z.B. 'LF1' aus Zwischenzeilen."""
        for r in self.rows[self.start:]:
            cells = [C.clean_text(c) for c in r]
            if not any(cells):
                continue
            first = next(c for c in cells if c)
            m = _BLOCK_TITLE.match(first)
            if m and sum(1 for c in cells if c) <= 3 and \
                    all(C.parse_number(c) is None or c == first for c in cells if c):
                yield None, m.group(0).upper().replace(" ", "")
                continue
            yield r, None

    def id_list(self, row: list, key: str) -> list[int]:
        return [int(float(v)) for v in C.expand_ranges(C.split_list(self.text(row, key)))
                if C.parse_number(v) is not None]


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------
def normalise_section_name(name: str) -> str:
    """'HE A 200' -> 'HEA 200', 'QRO 100x5' -> 'SHS 100x5', 'RO 168.3x5' -> 'CHS 168.3x5'."""
    s = re.split(r"[|;(]", name)[0].strip()
    s = s.replace("×", "x").replace(",", ".")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^QRO\b", "SHS", s, flags=re.IGNORECASE)
    s = re.sub(r"^RRO\b", "RHS", s, flags=re.IGNORECASE)
    s = re.sub(r"^RO\b", "CHS", s, flags=re.IGNORECASE)
    s = re.sub(r"^(HE)\s*([ABM])\s*(\d+)", r"HE\2 \3", s, flags=re.IGNORECASE)
    s = re.sub(r"^(HE)\s*(\d+)\s*([ABM])\b", r"HE\3 \2", s, flags=re.IGNORECASE)
    return s


def section_from_name(name: str, sec_name: str = None) -> Optional[Section]:
    s = normalise_section_name(name)
    sec_name = sec_name or name
    sec = C.section_from_designation(s, sec_name)
    if sec is not None:
        return sec
    m = re.match(r"^(rechteck|rectangle|rect)\s*(\d+(?:\.\d+)?)\s*[/x]\s*(\d+(?:\.\d+)?)",
                 s, re.IGNORECASE)
    if m:
        return Section.rectangle(sec_name, float(m.group(2)) * 1e-3, float(m.group(3)) * 1e-3)
    m = re.match(r"^(kreis|circle|rund)\s*(\d+(?:\.\d+)?)", s, re.IGNORECASE)
    if m:
        return Section.circle(sec_name, float(m.group(2)) * 1e-3)
    return None


def _support_value(cell, f_unit: float) -> tuple[str, float]:
    """Zelle einer Lagertabelle -> ('free'|'fixed'|'spring', k)."""
    if cell is None:
        return "free", 0.0
    if isinstance(cell, bool):
        return ("fixed" if cell else "free"), 0.0
    s = C.clean_text(cell).lower()
    if not s or s in ("nein", "no", "n", "-", "false", "falsch", "frei", "free", "0", "0.0"):
        return "free", 0.0
    v = C.parse_number(s)
    if v is not None:
        if v == 1.0 or v < 0 or v * f_unit >= 1e12:
            return "fixed", 0.0
        return "spring", v * f_unit
    if C.is_truthy(s) or s.startswith(("ja", "yes", "starr", "rigid", "fest", "fix")):
        return "fixed", 0.0
    return "free", 0.0


def _load_direction(text: str) -> tuple[Optional[int], str, bool]:
    """RFEM-Lastrichtung 'ZG', 'z', 'XL', 'ZP', 'Z (global)' -> (Achse, System, projiziert)."""
    s = text.strip()
    if not s:
        return None, "global", False
    up = s.upper()
    m = re.search(r"[XYZ]", up)
    if not m:
        return None, "global", False
    axis = "XYZ".index(m.group(0))
    local = bool(re.search(r"\bL\b|LOKAL|LOCAL|^[xyz]$|^[xyz]\b", s)) or \
        (s[m.start()].islower())
    projected = bool(re.search(r"P\b|PROJ", up[m.end():]))
    return axis, ("local" if local else "global"), projected


def _parse_formula(text: str) -> tuple[dict[str, float], list[str]]:
    """'1.35*LF1 + 1.5*LF2' -> ({'LF1': 1.35, 'LF2': 1.5}, [nicht aufloesbare Teile])."""
    factors: dict[str, float] = {}
    others = []
    for m in re.finditer(r"([+-]?\s*\d+(?:[.,]\d+)?)?\s*\*?\s*(LF|LC|CO|LK|EK)\s*(\d+)",
                         text, re.IGNORECASE):
        f = m.group(1)
        f = C.parse_number(f.replace(" ", "")) if f else 1.0
        if f is None:
            f = 1.0
        kind = m.group(2).upper()
        if kind in ("LF", "LC"):
            key = f"LF{int(m.group(3))}"
            factors[key] = factors.get(key, 0.0) + f
        else:
            others.append(f"{kind}{m.group(3)}")
    return factors, others


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------
def read_rfem_tables(path: str) -> dict[str, list[list]]:
    """xlsx-Datei, einzelne CSV-Datei oder Ordner mit CSV-Dateien -> {Name: Zeilen}.

    CSV-Zellen bleiben Text: In deutschen Exporten ist die Knotenliste '1,4' sonst
    nicht von der Dezimalzahl 1,4 zu unterscheiden (parse_number wertet spaeter aus).
    """
    if os.path.isdir(path):
        out = {}
        for fn in sorted(os.listdir(path)):
            if fn.lower().endswith((".csv", ".txt")):
                out[os.path.splitext(fn)[0]] = read_csv_table(os.path.join(path, fn),
                                                              convert=False)
        if not out:
            raise ValueError(f"Ordner '{path}' enthaelt keine CSV-Dateien")
        return out
    return read_table_file(path, convert=False)


def import_rfem_tables(path: str, model: Model = None, log: list = None,
                       unit_scale: float = DEFAULT_UNIT_SCALE, tol: float = C.DEFAULT_TOL,
                       tables: dict = None, z_up: bool = False, **_ignored) -> Model:
    """RFEM/RSTAB-Tabellenexport importieren."""
    if model is None:
        base = os.path.basename(os.path.normpath(path))
        model = Model(os.path.splitext(base)[0])
    if tables is None:
        tables = read_rfem_tables(path)
    scale = float(unit_scale)
    nodes = C.NodeIndex(model, tol)

    found: dict[str, Table] = {}
    for name, rows in tables.items():
        kind = classify_sheet(name)
        if kind is None or kind in found:
            continue
        t = Table(name, rows, kind)
        if t.ok:
            found[kind] = t
        else:
            C.warn(log, f"Tabelle '{name}': Kopfzeile nicht erkannt - uebersprungen")
    if not found:
        raise ValueError("Keine RFEM/RSTAB-Tabelle erkannt (Blattnamen wie '1.1 Knoten', "
                         "'1.7 Staebe' erwartet)")
    C.say(log, "RFEM-Tabellen: " + ", ".join(f"{t.name} [{k}]" for k, t in found.items()))

    # ---- Materialien ---------------------------------------------------------------
    mat_by_no: dict[int, str] = {}
    t = found.get("materials")
    if t is not None:
        f_E = t.unit("E", 1e7)             # RFEM: kN/cm²
        f_gamma = t.unit("gamma", 1e3)     # kN/m³
        f_rho = t.unit("rho", 1.0)
        k = 0
        for row, _ in t.data():
            if row is None:
                continue
            k += 1
            no = t.num(row, "no")
            no = int(no) if no is not None else k
            name = t.text(row, "name") or f"Material {no}"
            grade = C.steel_grade_from_text(name)
            m = Material.steel(grade, name) if grade else Material(name, 210e9, 0.3, 7850.0)
            E = t.num(row, "E")
            if E:
                m.E = E * f_E
            nu = t.num(row, "nu")
            G = t.num(row, "G")
            if nu is not None:
                m.nu = nu
            elif G and E:
                m.nu = max(0.0, E / (2 * G) - 1.0)
            rho = t.num(row, "rho")
            gamma = t.num(row, "gamma")
            if rho:
                m.rho = rho * f_rho
            elif gamma:
                m.rho = gamma * f_gamma / 9.81
            al = t.num(row, "alpha")
            if al:
                m.alpha = al
            model.add_material(m)
            mat_by_no[no] = m.name
        C.say(log, f"{len(mat_by_no)} Materialien")

    def material(ref) -> str:
        v = C.parse_number(ref)
        if v is not None and int(v) in mat_by_no:
            return mat_by_no[int(v)]
        txt = C.clean_text(ref)
        if txt and C.parse_number(txt) is None:
            return C.ensure_material(model, txt, log)
        return C.ensure_material(model, None, log, quiet=True)

    # ---- Querschnitte ------------------------------------------------------------------
    sec_by_no: dict[int, str] = {}
    sec_mat: dict[str, str] = {}
    t = found.get("sections")
    if t is not None:
        f_A = t.unit("A", 1e-4)
        f_I = t.unit("Iy", 1e-8)
        f_It = t.unit("It", 1e-8)
        k = 0
        for row, _ in t.data():
            if row is None:
                continue
            k += 1
            no = t.num(row, "no")
            no = int(no) if no is not None else k
            name = t.text(row, "name") or f"QS {no}"
            sec = section_from_name(name, name)
            if sec is None:
                A = t.num(row, "A")
                if A:
                    sec = Section(name, A=A * f_A, Iy=(t.num(row, "Iy") or 0.0) * f_I or 1e-9,
                                  Iz=(t.num(row, "Iz") or 0.0) * f_I or 1e-9,
                                  It=(t.num(row, "It") or 0.0) * f_It or 1e-10)
                    C.say(log, f"Querschnitt '{name}': Kennwerte aus Tabelle (freier Querschnitt)")
            if sec is None:
                C.warn(log, f"Querschnitt '{name}' unbekannt - {C.DEFAULT_PROFILE} verwendet")
                sec = C.section_from_designation(C.DEFAULT_PROFILE, name)
            model.add_section(sec)
            sec_by_no[no] = sec.name
            if t.has("mat"):
                sec_mat[sec.name] = material(row[t.cols["mat"]] if t.cols["mat"] < len(row) else None)
        C.say(log, f"{len(sec_by_no)} Querschnitte")

    def section(ref) -> str:
        v = C.parse_number(ref)
        if v is not None:
            if int(v) in sec_by_no:
                return sec_by_no[int(v)]
            fb = C.ensure_section(model, None, log)
            C.warn(log, f"Querschnitt Nr. {int(v)} nicht in Querschnittstabelle - {fb} verwendet")
            return fb
        txt = C.clean_text(ref)
        if txt:
            sec = section_from_name(txt, txt)
            if sec is not None:
                if txt not in model.sections:
                    model.add_section(sec)
                return txt
            return C.ensure_section(model, txt, log)
        return C.ensure_section(model, None, log)

    # ---- Knoten -----------------------------------------------------------------------
    node_by_no: dict[int, int] = {}
    t = found.get("nodes")
    if t is not None:
        f = t.unit("x", 1.0) * scale
        k = 0
        for row, _ in t.data():
            if row is None:
                continue
            x = t.num(row, "x")
            y = t.num(row, "y")
            if x is None and y is None:
                continue
            k += 1
            no = t.num(row, "no")
            no = int(no) if no is not None else k
            z = t.num(row, "z") or 0.0
            node_by_no[no] = nodes.add((x or 0.0) * f, (y or 0.0) * f, z * f)
        C.say(log, f"{len(node_by_no)} Knoten")
    else:
        C.warn(log, "Keine Knotentabelle ('1.1 Knoten') gefunden")

    # ---- Linien -----------------------------------------------------------------------
    line_nodes: dict[int, list[int]] = {}
    t = found.get("lines")
    if t is not None:
        k = 0
        for row, _ in t.data():
            if row is None:
                continue
            k += 1
            no = t.num(row, "no")
            no = int(no) if no is not None else k
            ids = t.id_list(row, "nodes")
            chain = [node_by_no[i] for i in ids if i in node_by_no]
            if len(chain) < 2:
                C.warn(log, f"Linie {no}: Knoten {ids} nicht aufloesbar")
                continue
            line_nodes[no] = chain
        C.say(log, f"{len(line_nodes)} Linien")

    # ---- Staebe -----------------------------------------------------------------------
    member_elems: dict[int, list[int]] = {}
    t = found.get("members")
    if t is not None:
        f_beta = t.unit("beta", math.pi / 180.0)
        k = 0
        for row, _ in t.data():
            if row is None:
                continue
            k += 1
            no = t.num(row, "no")
            no = int(no) if no is not None else k
            try:
                chain: list[int] = []
                ln = t.num(row, "line")
                if ln is not None and int(ln) in line_nodes:
                    chain = line_nodes[int(ln)]
                elif t.has("n1") and t.has("n2"):
                    a, b = t.num(row, "n1"), t.num(row, "n2")
                    if a is None or b is None:
                        raise ValueError("Anfangs-/Endknoten fehlt")
                    chain = [node_by_no[int(a)], node_by_no[int(b)]]
                elif ln is not None:
                    raise KeyError(f"Linie {int(ln)} unbekannt")
                else:
                    raise ValueError("weder Linie noch Knoten angegeben")
                typ_txt = t.text(row, "type").lower()
                typ = "beam"
                if re.search(r"fachwerk|truss|zugstab|tension|druckstab|compression|seil|cable", typ_txt):
                    typ = "truss"
                elif re.search(r"null|dummy", typ_txt):
                    C.say(log, f"Stab {no}: Nullstab uebersprungen")
                    continue
                sec_ref = row[t.cols["sec1"]] if t.has("sec1") and t.cols["sec1"] < len(row) else None
                sec = section(sec_ref)
                if t.has("sec2"):
                    s2 = t.text(row, "sec2")
                    if s2 and s2 != t.text(row, "sec1"):
                        C.warn(log, f"Stab {no}: Voute (Querschnitt Ende '{s2}') - Anfangsquerschnitt verwendet")
                mat = sec_mat.get(sec) or C.ensure_material(model, None, log, quiet=True)
                roll = (t.num(row, "beta") or 0.0) * f_beta
                elems = [model.add_element(typ, [a, b], mat, sec, roll=roll, group="Staebe")
                         for a, b in zip(chain[:-1], chain[1:])]
                member_elems[no] = elems
                model.add_member(C.unique_name(model.members, f"Stab {no}"), elems)
            except Exception as ex:
                C.warn(log, f"Stab {no} uebersprungen: {ex}")
        C.say(log, f"{len(member_elems)} Staebe")

    # ---- Flaechen ---------------------------------------------------------------------
    surface_elems: dict[int, list[int]] = {}
    t = found.get("surfaces")
    if t is not None:
        f_t = t.unit("t", 1e-3)
        k = 0
        for row, _ in t.data():
            if row is None:
                continue
            k += 1
            no = t.num(row, "no")
            no = int(no) if no is not None else k
            try:
                if re.search(r"null|dummy", t.text(row, "type").lower()):
                    continue
                lines = t.id_list(row, "lines")
                poly: list[int] = []
                for ln in lines:
                    ch = line_nodes.get(ln)
                    if not ch:
                        raise KeyError(f"Linie {ln} unbekannt")
                    if poly and poly[-1] != ch[0]:
                        if poly[-1] == ch[-1]:
                            ch = ch[::-1]
                        elif len(poly) == 1 and poly[0] in (ch[0], ch[-1]):
                            pass
                    for n in ch:
                        if not poly or poly[-1] != n:
                            poly.append(n)
                thick = (t.num(row, "t") or 0.0) * f_t
                prop = C.ensure_shell_prop(model, f"t{thick * 1e3:g}" if thick > 0 else None,
                                           thick if thick > 0 else None, log)
                mat = material(row[t.cols["mat"]] if t.has("mat") and t.cols["mat"] < len(row) else None)
                surface_elems[no] = C.polygon_to_shells(model, poly, mat, prop, f"Flaeche {no}",
                                                        log, f"Flaeche {no}")
            except Exception as ex:
                C.warn(log, f"Flaeche {no} uebersprungen: {ex}")
        C.say(log, f"{len(surface_elems)} Flaechen")
    nodes.flush()

    # ---- Knotenlager -------------------------------------------------------------------
    t = found.get("supports")
    if t is not None:
        keys = ["ux", "uy", "uz", "rx", "ry", "rz"]
        f_k = [t.unit(k, 1e3) for k in keys]
        n_sup = 0
        for row, _ in t.data():
            if row is None:
                continue
            ids = t.id_list(row, "nodes")
            fixed, sdofs, sk = [], [], []
            for dof, key in enumerate(keys):
                if not t.has(key):
                    continue
                cell = row[t.cols[key]] if t.cols[key] < len(row) else None
                kind, kval = _support_value(cell, f_k[dof])
                if kind == "fixed":
                    fixed.append(dof)
                elif kind == "spring":
                    sdofs.append(dof)
                    sk.append(kval)
            for i in ids:
                n = node_by_no.get(i)
                if n is None:
                    C.warn(log, f"Knotenlager: Knoten {i} unbekannt")
                    continue
                if fixed:
                    model.fix(n, fixed)
                if sdofs:
                    model.fix(n, sdofs, stiffness=sk)
                if fixed or sdofs:
                    n_sup += 1
        C.say(log, f"{n_sup} Knotenlager")

    # ---- Lastfaelle -------------------------------------------------------------------
    case_by_no: dict[int, str] = {}
    t = found.get("load_cases")
    if t is not None:
        for row, _ in t.data():
            if row is None:
                continue
            no = t.num(row, "no")
            if no is None:
                m = re.match(r"^(?:LF|LC)\s*(\d+)", t.text(row, "no"), re.IGNORECASE)
                if not m:
                    continue
                no = int(m.group(1))
            no = int(no)
            name = f"LF{no}"
            cat = C.category_from_text(t.text(row, "cat"), "G" if no == 1 else "Q")
            desc = t.text(row, "name")
            if name in model.load_cases:
                lc = model.load_cases[name]
                lc.category = cat
                lc.description = desc
            else:
                lc = C.get_or_add_case(model, name, cat, desc)
            sw = t.text(row, "sw")
            if sw and (C.is_truthy(sw) or C.parse_number(sw)):
                fx = t.num(row, "fx") or 0.0
                fy = t.num(row, "fy") or 0.0
                fz = t.num(row, "fz")
                if fz is None:
                    fz = C.parse_number(sw) if C.parse_number(sw) else 1.0
                if z_up:
                    fz = -fz
                lc.gravity = [9.81 * fx, 9.81 * fy, 9.81 * fz]
                C.say(log, f"Lastfall {name}: Eigengewicht g = {lc.gravity} m/s² "
                           f"({'Z nach oben' if z_up else 'RFEM: Z nach unten'})")
            case_by_no[no] = name
        C.say(log, f"{len(case_by_no)} Lastfaelle")

    def case_of(text: str, current: Optional[str]) -> str:
        m = re.match(r"^(?:LF|LC|Lastfall|Load case)?\s*(\d+)", text.strip(), re.IGNORECASE) \
            if text else None
        if m:
            name = f"LF{int(m.group(1))}"
        elif current:
            name = current
        else:
            name = "LF1"
        if name not in model.load_cases:
            C.get_or_add_case(model, name, "G" if name == "LF1" else "Q", "")
        return name

    # ---- Kombinationen ------------------------------------------------------------------
    t = found.get("combinations")
    if t is not None:
        n_co = 0
        for row, _ in t.data():
            if row is None:
                continue
            formula = t.text(row, "formula")
            factors, others = _parse_formula(formula)
            if not factors:
                continue
            no = t.num(row, "no")
            no = int(no) if no is not None else n_co + 1
            for key in factors:
                if key not in model.load_cases:
                    C.get_or_add_case(model, key, "Q", "")
            sit = t.text(row, "situation").upper()
            typ = "ULS"
            if re.search(r"GZG|SLS|GEBRAUCH|SERVICE", sit):
                typ = "SLS_QP" if re.search(r"QUASI", sit) else ("SLS_FR" if re.search(r"HAEUFIG|HÄUFIG|FREQ", sit) else "SLS_CH")
            elif re.search(r"AUSSERGEW|AUßERGEW|ACC|ERDBEBEN|SEISM", sit):
                typ = "ACC"
            elif re.search(r"EQU|LAGESICH", sit):
                typ = "EQU"
            name = f"LK{no}"
            model.add_combination(C.unique_name(model.combinations, name), factors, typ,
                                  t.text(row, "name") or formula)
            if others:
                C.warn(log, f"Kombination {name}: Verweise {others} nicht aufgeloest")
            n_co += 1
        C.say(log, f"{n_co} Lastkombinationen")

    # ---- Knotenlasten -----------------------------------------------------------------
    t = found.get("nodal_loads")
    if t is not None:
        keys = ["fx", "fy", "fz", "mx", "my", "mz"]
        f = [t.unit(k, 1e3) for k in keys]
        current = None
        n_loads = 0
        for row, title in t.data():
            if title:
                current = case_of(title, current)
                continue
            case = case_of(t.text(row, "case"), current)
            F = [(t.num(row, k) or 0.0) * f[i] for i, k in enumerate(keys)]
            if not any(F):
                continue
            for i in t.id_list(row, "nodes"):
                n = node_by_no.get(i)
                if n is None:
                    C.warn(log, f"Knotenlast: Knoten {i} unbekannt")
                    continue
                model.load_node(n, *F, case=case)
                n_loads += 1
        C.say(log, f"{n_loads} Knotenlasten")

    # ---- Stablasten -------------------------------------------------------------------
    t = found.get("member_loads")
    if t is not None:
        f_p = t.unit("p1", 1e3)
        current = None
        n_loads = 0
        for row, title in t.data():
            if title:
                current = case_of(title, current)
                continue
            case = case_of(t.text(row, "case"), current)
            kind = t.text(row, "kind").lower()
            if kind and not re.search(r"kraft|force", kind):
                C.warn(log, f"Stablast: Lastart '{t.text(row, 'kind')}' wird nicht unterstuetzt")
                continue
            dist = t.text(row, "distribution").lower()
            if re.search(r"konzentr|concentr|einzel|point", dist):
                C.warn(log, "Stablast: Einzellast auf Stab wird nicht unterstuetzt")
                continue
            axis, system, projected = _load_direction(t.text(row, "direction"))
            if axis is None:
                axis = 2
            if projected or re.search(r"proj", t.text(row, "reflen").lower()):
                C.warn(log, "Stablast: Projektion wird als wahre Laenge angesetzt")
            p1 = (t.num(row, "p1") or 0.0) * f_p
            p2 = t.num(row, "p2")
            p2 = p2 * f_p if (p2 is not None and re.search(r"trapez|linear|veraender", dist)) else p1
            q1 = [0.0, 0.0, 0.0]
            q1[axis] = p1
            q2 = [0.0, 0.0, 0.0]
            q2[axis] = p2
            for i in t.id_list(row, "members"):
                elems = member_elems.get(i)
                if not elems:
                    C.warn(log, f"Stablast: Stab {i} unbekannt")
                    continue
                lengths = [model.element_length(e) for e in elems]
                total = sum(lengths) or 1.0
                pos = 0.0
                for e, L in zip(elems, lengths):
                    qa = [a + (b - a) * pos / total for a, b in zip(q1, q2)]
                    qb = [a + (b - a) * (pos + L) / total for a, b in zip(q1, q2)]
                    model.load_beam(e, *qa, system=system, case=case,
                                    q2=qb if qb != qa else None)
                    pos += L
                n_loads += 1
        C.say(log, f"{n_loads} Stablasten")
    return model
