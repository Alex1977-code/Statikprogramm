"""
Gemeinsame Hilfsfunktionen der Importer.

* Log-Ausgabe (nie print, immer an eine Liste anhaengen)
* Knotenverwaltung mit Toleranz (doppelte Koordinaten -> ein Knoten)
* Standardmaterial / Standardquerschnitt
* Zahlen mit deutschem Dezimalkomma, Einheiten aus Spaltenueberschriften
* Polygon -> Schalenelemente (Dreieck, Viereck, Faecher-Triangulierung)
* Einwirkungskategorie aus Freitext
"""
from __future__ import annotations

import math
import re
from typing import Optional

import numpy as np

from ..model import Model, Material, Section, ShellProp, ACTION_CATEGORIES
from .. import profiles

DEFAULT_TOL = 1e-6          # Knotentoleranz [m]
DEFAULT_STEEL = "S235"
DEFAULT_PROFILE = "IPE 200"


# --------------------------------------------------------------------------
# Protokoll
# --------------------------------------------------------------------------
def say(log: Optional[list], msg: str) -> None:
    """Meldung an das Importprotokoll anhaengen (falls vorhanden)."""
    if log is not None:
        log.append(msg)


def warn(log: Optional[list], msg: str) -> None:
    say(log, "WARNUNG: " + msg)


# --------------------------------------------------------------------------
# Knoten
# --------------------------------------------------------------------------
class NodeIndex:
    """Knoten mit Koordinatentoleranz verwalten.

    Neue Knoten werden gesammelt und mit flush() en bloc an das Modell
    angehaengt (Model.add_node kopiert bei jedem Aufruf das ganze Array).
    Bereits vorhandene Knoten des Modells werden beruecksichtigt, so dass ein
    Import an ein bestehendes Modell angeschlossen werden kann.
    """

    def __init__(self, model: Model, tol: float = DEFAULT_TOL):
        self.model = model
        self.tol = float(tol) if tol and tol > 0 else DEFAULT_TOL
        self._map: dict[tuple, int] = {}
        self._pending: list[tuple[float, float, float]] = []
        self._base = model.nn
        for i, p in enumerate(model.nodes):
            self._map.setdefault(self._key(p), i)

    def _key(self, p) -> tuple:
        return tuple(int(math.floor(float(c) / self.tol + 0.5)) for c in p)

    def find(self, x: float, y: float, z: float) -> Optional[int]:
        """Index eines vorhandenen Knotens an (x, y, z) oder None."""
        k = self._key((x, y, z))
        hit = self._map.get(k)
        if hit is not None:
            return hit
        # Nachbarzellen (Rundungsgrenzen)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if dx == dy == dz == 0:
                        continue
                    hit = self._map.get((k[0] + dx, k[1] + dy, k[2] + dz))
                    if hit is not None:
                        p = self.get(hit)
                        if (abs(p[0] - x) <= self.tol and abs(p[1] - y) <= self.tol
                                and abs(p[2] - z) <= self.tol):
                            return hit
        return None

    def add(self, x: float, y: float, z: float) -> int:
        """Knoten holen oder anlegen; Rueckgabe Knotenindex."""
        x, y, z = float(x), float(y), float(z)
        hit = self.find(x, y, z)
        if hit is not None:
            return hit
        idx = self._base + len(self._pending)
        self._pending.append((x, y, z))
        self._map[self._key((x, y, z))] = idx
        return idx

    def get(self, idx: int) -> np.ndarray:
        """Koordinaten eines Knotens (auch noch nicht geschriebener)."""
        if idx < self._base:
            return self.model.nodes[idx]
        return np.asarray(self._pending[idx - self._base], float)

    def flush(self) -> int:
        """Gesammelte Knoten an das Modell anhaengen."""
        n = len(self._pending)
        if n:
            self.model.add_nodes(np.asarray(self._pending, float))
            self._base = self.model.nn
            self._pending = []
        return n

    def __len__(self) -> int:
        return self._base + len(self._pending)


def count_duplicate_nodes(model: Model, tol: float = DEFAULT_TOL) -> int:
    """Wie viele Knoten auf einem anderen liegen - ohne etwas zu aendern.

    Zusammenfuehren ist nicht immer richtig: an einer Kontaktfuge, einer
    Flaechenfreigabe oder einem Gleitlager liegen die Knoten absichtlich
    aufeinander. Wer nur wissen will, wie viele es sind, fragt hier.
    """
    if model.nn == 0:
        return 0
    key = np.floor(model.nodes / tol + 0.5).astype(np.int64)
    return int(model.nn - len(np.unique(key, axis=0)))


def merge_duplicate_nodes(model: Model, tol: float = DEFAULT_TOL) -> int:
    """Doppelte Knoten zusammenfuehren, alle Verweise umhaengen.

    Wie mesher.merge_nodes, beruecksichtigt aber zusaetzlich die Knotenlasten
    *aller* Lastfaelle sowie Kontaktobjekte. Rueckgabe: Anzahl entfernter Knoten.
    """
    if model.nn == 0:
        return 0
    key = np.floor(model.nodes / tol + 0.5).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)
    order = np.argsort(first)
    remap = np.zeros(len(first), dtype=int)
    remap[order] = np.arange(len(first))
    new_index = remap[inverse]
    n_removed = model.nn - len(first)
    if n_removed == 0:
        return 0
    new_nodes = np.zeros((len(first), 3))
    new_nodes[new_index] = model.nodes
    model.nodes = new_nodes
    for e in model.elements:
        e.nodes = [int(new_index[n]) for n in e.nodes]
    for s in model.supports:
        s.node = int(new_index[s.node])
    for lc in model.load_cases.values():
        for l in lc.nodal_loads:
            l.node = int(new_index[l.node])
    for c in model.contact_supports:
        c.node = int(new_index[c.node])
    for g in model.gap_elements:
        g.node_a = int(new_index[g.node_a])
        g.node_b = int(new_index[g.node_b])
    for cp in model.contact_pairs:
        cp.slave_nodes = [int(new_index[n]) for n in cp.slave_nodes]
        cp.master_faces = [[int(new_index[n]) for n in f] for f in cp.master_faces]
    for ln in model.lines.values():
        seen, nodes = set(), []
        for n in ln.nodes:
            k = int(new_index[n])
            if not nodes or nodes[-1] != k:
                nodes.append(k)
            seen.add(k)
        ln.nodes = nodes
    for ls in model.line_supports:
        nodes = []
        for n in ls.nodes:
            k = int(new_index[n])
            if k not in nodes:
                nodes.append(k)
        ls.nodes = nodes
    for ss in model.surface_supports:
        ss.elements = [int(e) for e in ss.elements]
        nodes, areas = [], []
        pos: dict[int, int] = {}
        for i, n in enumerate(ss.nodes):
            k = int(new_index[n])
            a = ss.areas[i] if i < len(ss.areas) else 0.0
            if k in pos:
                if areas:
                    areas[pos[k]] += a          # Einflussflaechen addieren
            else:
                pos[k] = len(nodes)
                nodes.append(k)
                areas.append(a)
        ss.nodes = nodes
        ss.areas = areas if any(areas) else []
    return n_removed


# --------------------------------------------------------------------------
# Material / Querschnitt / Schalendicke
# --------------------------------------------------------------------------
def steel_grade_from_text(text: str) -> Optional[str]:
    """'S 235 JR', 'S355', 'Baustahl S235' -> 'S235' (sonst None)."""
    if not text:
        return None
    m = re.search(r"S\s?(235|275|355|420|460)", str(text).upper())
    return f"S{m.group(1)}" if m else None


def ensure_material(model: Model, name: str = None, log: list = None,
                    quiet: bool = False) -> str:
    """Material sicherstellen und Namen zurueckgeben.

    name=None -> erstes vorhandenes Material, sonst Standardstahl S235.
    Enthaelt der Name eine Stahlsorte, wird diese verwendet.
    """
    if name and name in model.materials:
        return name
    if name is None:
        if model.materials:
            return next(iter(model.materials))
        name = DEFAULT_STEEL
    grade = steel_grade_from_text(name)
    if grade:
        model.add_material(Material.steel(grade, name))
        if not quiet:
            say(log, f"Material '{name}' als Baustahl {grade} angelegt")
    else:
        model.add_material(Material.steel(DEFAULT_STEEL, name))
        if not quiet:
            warn(log, f"Material '{name}' unbekannt - Kennwerte von {DEFAULT_STEEL} verwendet")
    return name


def section_from_designation(designation: str, name: str = None) -> Optional[Section]:
    """Profil aus der Datenbank (None, wenn unbekannt)."""
    if not designation:
        return None
    try:
        return profiles.make_section(designation, name or designation)
    except (KeyError, ValueError):
        return None


def ensure_section(model: Model, name: str = None, log: list = None,
                   fallback: str = DEFAULT_PROFILE) -> str:
    """Querschnitt sicherstellen: vorhandener Name, Profilbezeichnung oder Fallback."""
    if name and name in model.sections:
        return name
    if name:
        sec = section_from_designation(name, name)
        if sec is not None:
            model.add_section(sec)
            say(log, f"Querschnitt '{name}' aus Profildatenbank")
            return name
        warn(log, f"Querschnitt '{name}' unbekannt - {fallback} verwendet")
    if fallback in model.sections:
        return fallback
    sec = section_from_designation(fallback, fallback)
    if sec is None:
        sec = Section.i_profile(fallback, 0.200, 0.100, 0.0056, 0.0085, 0.012)
    model.add_section(sec)
    return fallback


def ensure_shell_prop(model: Model, name: str = None, t: float = None,
                      log: list = None) -> str:
    """Schalendicke sicherstellen. Ohne Angabe: erste vorhandene oder t = 10 mm."""
    if name and name in model.shells:
        return name
    if t is None or t <= 0:
        if name is None and model.shells:
            return next(iter(model.shells))
        t = 0.010
        warn(log, f"Keine Dicke fuer Schale '{name or 't10'}' - 10 mm angenommen")
    name = name or f"t{t * 1e3:g}"
    if name not in model.shells:
        model.add_shell_prop(ShellProp(name, float(t)))
    return name


def unique_name(existing, base: str) -> str:
    """Eindeutigen Namen erzeugen (base, base_2, base_3, ...)."""
    if base not in existing:
        return base
    k = 2
    while f"{base}_{k}" in existing:
        k += 1
    return f"{base}_{k}"


# --------------------------------------------------------------------------
# Zahlen / Einheiten / Text
# --------------------------------------------------------------------------
_NUM_RE = re.compile(r"^[+-]?(\d+([.,]\d*)?|[.,]\d+)([eE][+-]?\d+)?$")


def parse_number(value) -> Optional[float]:
    """Zahl aus Zelle: float, '1,5', '1.234,5', '3.5 kN', '-' -> None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s in ("-", "--", "—"):
        return None
    # Einheit hinter der Zahl abschneiden ("3.5 kN")
    m = re.match(r"^([+-]?[\d.,]+(?:[eE][+-]?\d+)?)", s)
    if not m:
        return None
    s = m.group(1)
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):       # 1.234,5 (deutsch)
            s = s.replace(".", "").replace(",", ".")
        else:                                 # 1,234.5 (englisch)
            s = s.replace(",", "")
    elif "," in s:
        if s.count(",") == 1:
            s = s.replace(",", ".")           # 1,5
        else:
            s = s.replace(",", "")            # 1,234,567
    if not _NUM_RE.match(s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def is_truthy(value) -> bool:
    """'x', 'Ja', 'Yes', 'True', '1', Haken -> True."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    s = str(value).strip().lower()
    return s in ("x", "ja", "yes", "y", "j", "true", "wahr", "1", "1.0", "✓", "✔",
                 "fest", "fixed", "rigid", "starr", "gesperrt", "ja.")


# Einheitenfaktoren -> SI. Schluessel werden normalisiert (klein, ohne Leerzeichen,
# Hochzahlen als ^n).
_UNITS = {
    # Laenge
    "m": 1.0, "mm": 1e-3, "cm": 1e-2, "dm": 1e-1, "km": 1e3,
    "in": 0.0254, "ft": 0.3048,
    # Flaeche / Traegheitsmomente
    "m^2": 1.0, "cm^2": 1e-4, "mm^2": 1e-6,
    "m^3": 1.0, "cm^3": 1e-6, "mm^3": 1e-9,
    "m^4": 1.0, "cm^4": 1e-8, "mm^4": 1e-12,
    "m^6": 1.0, "cm^6": 1e-12, "mm^6": 1e-18,
    # Kraft / Moment
    "n": 1.0, "kn": 1e3, "mn": 1e6, "kgf": 9.80665, "lbf": 4.448222,
    "nm": 1.0, "knm": 1e3, "mnm": 1e6, "ncm": 1e-2, "kncm": 10.0,
    # Streckenlast / Flaechenlast
    "n/m": 1.0, "kn/m": 1e3, "mn/m": 1e6, "n/mm": 1e3, "kn/mm": 1e6, "kn/cm": 1e5,
    "n/m^2": 1.0, "kn/m^2": 1e3, "mn/m^2": 1e6, "n/mm^2": 1e6, "kn/cm^2": 1e7,
    "kn/mm^2": 1e9, "mpa": 1e6, "gpa": 1e9, "kpa": 1e3, "pa": 1.0,
    "n/m^3": 1.0, "kn/m^3": 1e3,
    # Steifigkeiten
    "n/rad": 1.0, "nm/rad": 1.0, "knm/rad": 1e3, "mnm/rad": 1e6,
    "kn/rad": 1e3, "mn/rad": 1e6, "knm/°": 1e3 * 180 / math.pi,
    # Dichte / Winkel / Temperatur
    "kg/m^3": 1.0, "t/m^3": 1e3, "g/cm^3": 1e3,
    "°": math.pi / 180.0, "deg": math.pi / 180.0, "grad": math.pi / 180.0, "rad": 1.0,
    "1/k": 1.0, "1/°c": 1.0, "k": 1.0, "°c": 1.0,
}
_SUPERSCRIPT = str.maketrans({"²": "^2", "³": "^3", "⁴": "^4", "⁶": "^6"})


def normalize_unit(text: str) -> str:
    s = str(text).strip().translate(_SUPERSCRIPT).lower()
    s = s.replace(" ", "").replace("**", "^")
    s = re.sub(r"([a-z])(\d)", r"\1^\2", s)       # mm2 -> mm^2
    return s


def unit_factor(header: str, default: float = 1.0) -> float:
    """Einheitenfaktor aus einer Spaltenueberschrift wie 'Kraft Fx [kN]'.

    Gesucht wird der letzte Klammerausdruck [..] bzw. (..) mit bekannter Einheit.
    """
    if not header:
        return default
    found = re.findall(r"[\[(]([^\[\]()]+)[\])]", str(header))
    for u in reversed(found):
        f = _UNITS.get(normalize_unit(u))
        if f is not None:
            return f
    return default


def clean_text(value) -> str:
    """Zelle als bereinigter Text ('' fuer None)."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def norm_key(text) -> str:
    """Spaltenname normalisieren: klein, Umlaute vereinfacht, Einheiten entfernt."""
    s = clean_text(text).lower()
    s = re.sub(r"[\[(][^\[\]()]*[\])]", " ", s)          # Einheiten entfernen
    s = (s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
         .replace("φ", "phi").replace("ϕ", "phi").replace("ψ", "psi").replace("ν", "nu")
         .replace("γ", "gamma").replace("α", "alpha"))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def split_list(text, sep: str = r"[;,\s]+") -> list[str]:
    """'1;2;3' / '1, 2' / '1 2' -> ['1', '2', '3']."""
    s = clean_text(text)
    if not s:
        return []
    return [p for p in re.split(sep, s) if p]


def expand_ranges(items: list[str]) -> list[str]:
    """['1-3', '5'] -> ['1', '2', '3', '5'] (RFEM-Listen)."""
    out = []
    for it in items:
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", it)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.extend(str(k) for k in range(min(a, b), max(a, b) + 1))
        else:
            out.append(it)
    return out


def category_from_text(text, default: str = "Q") -> str:
    """Einwirkungskategorie (Schluessel in ACTION_CATEGORIES) aus Freitext."""
    s = norm_key(text)
    if not s:
        return default
    if re.search(r"staendig|permanent|dead|eigengewicht|self ?weight|\bg\b", s):
        return "G"
    if re.search(r"vorspann|prestress|\bp\b", s):
        return "P"
    if re.search(r"schnee|snow", s):
        return "S_H" if re.search(r"1000|ueber|above", s) else "S"
    if re.search(r"wind", s):
        return "W"
    if re.search(r"temperatur|thermal|\bt\b", s):
        return "T"
    if re.search(r"wasser|hydro|water", s):
        return "H"
    if re.search(r"setzung|settlement", s):
        return "SET"
    if re.search(r"ermued|fatigue", s):
        return "FAT"
    if re.search(r"aussergew|accident|erdbeben|seismic|seism|anprall|explosion|fire|brand", s):
        return "A"
    if re.search(r"kran|crane", s):
        return "Q_K"
    m = re.search(r"(?:kat(?:egorie)?|cat(?:egory)?)\.?\s*([a-h])\b", s)
    if m:
        cat = "Q_" + m.group(1).upper()
        if cat in ACTION_CATEGORIES:
            return cat
    if re.search(r"nutz|verkehr|imposed|live|variable|veraenderlich|traffic|\bq\b", s):
        return "Q"
    return default


# --------------------------------------------------------------------------
# Geometrie
# --------------------------------------------------------------------------
def polygon_to_shells(model: Model, node_ids: list[int], mat: str, prop: str,
                      group: str = "default", log: list = None,
                      what: str = "Flaeche") -> list[int]:
    """Polygon (Knotenindizes) in Schalenelemente umsetzen.

    3 Knoten -> shell3, 4 -> shell4, mehr -> Faecher-Triangulierung mit Warnung.
    Doppelte aufeinanderfolgende Knoten werden entfernt.
    """
    ids = []
    for n in node_ids:
        if not ids or ids[-1] != n:
            ids.append(int(n))
    if len(ids) > 1 and ids[0] == ids[-1]:
        ids.pop()
    if len(ids) < 3:
        warn(log, f"{what}: weniger als 3 verschiedene Knoten - uebersprungen")
        return []
    out = []
    if len(ids) == 3:
        out.append(model.add_element("shell3", ids, mat, prop, group=group))
    elif len(ids) == 4:
        out.append(model.add_element("shell4", ids, mat, prop, group=group))
    else:
        warn(log, f"{what}: Polygon mit {len(ids)} Knoten wurde als Faecher trianguliert - "
                  f"fuer die Berechnung sollte ein feineres Netz erzeugt werden")
        for i in range(1, len(ids) - 1):
            out.append(model.add_element("shell3", [ids[0], ids[i], ids[i + 1]],
                                         mat, prop, group=group))
    return out


def roll_from_vector(p1, p2, vec, axis: str = "y") -> float:
    """Verdrehwinkel [rad], damit die lokale y- (oder z-) Achse eines Stabes von
    p1 nach p2 in Richtung 'vec' (projiziert senkrecht zur Stabachse) zeigt."""
    from ..elements.beam3d import local_axes
    try:
        T3, _ = local_axes(np.asarray(p1, float), np.asarray(p2, float), 0.0)
    except ValueError:
        return 0.0
    ex, ey, ez = T3
    v = np.asarray(vec, float)
    v = v - np.dot(v, ex) * ex
    n = np.linalg.norm(v)
    if n < 1e-12:
        return 0.0
    v /= n
    if axis == "y":
        return float(math.atan2(np.dot(v, ez), np.dot(v, ey)))
    return float(math.atan2(-np.dot(v, ey), np.dot(v, ez)))


def subdivide_line(nodes: NodeIndex, p1, p2, n: int) -> list[int]:
    """Knotenkette von p1 nach p2 mit n Abschnitten (n+1 Knoten)."""
    p1 = np.asarray(p1, float)
    p2 = np.asarray(p2, float)
    n = max(1, int(n))
    return [nodes.add(*(p1 + (p2 - p1) * (k / n))) for k in range(n + 1)]


# --------------------------------------------------------------------------
# Lastfaelle
# --------------------------------------------------------------------------
def get_or_add_case(model: Model, name: str, category: str = "Q",
                    description: str = "", **kw):
    """Lastfall holen oder anlegen (ohne den aktiven Lastfall zu wechseln)."""
    if name in model.load_cases:
        return model.load_cases[name]
    if category not in ACTION_CATEGORIES:
        category = "Q"
    return model.add_load_case(name, category, description, activate=False, **kw)


def drop_empty_default_case(model: Model, name: str = "LF1") -> bool:
    """Leeren Standardlastfall entfernen, wenn der Import eigene Lastfaelle brachte."""
    lc = model.load_cases.get(name)
    if lc is None or len(model.load_cases) < 2 or lc.n_loads:
        return False
    for c in model.combinations.values():
        if name in c.factors:
            return False
    for f in model.fatigue_loads.values():
        if name in (f.case_max, f.case_min):
            return False
    model.remove_load_case(name)
    return True
