"""
RFEM 6 Projektdateien (.rf6): die eingebettete Modelldatenbank ``model.db``.

Eine .rf6-Datei ist ein ZIP-Behaelter. Darin liegt ``model.db``, eine
SQLite-Datenbank mit dem objektrelationalen Abbild des RFEM-Modells. Der Aufbau
ist bei Dlubal nicht veroeffentlicht; er wurde an einer echten Projektdatei
(RFEM 6.11/6.12) ausgelesen. Er folgt durchgehend demselben Muster:

    Griff-Tabelle   Node, Line, Member, Surface, Solid, Section, Material,
                    NodalSupport, LineSupport, SurfaceSupport, MemberHinge, ...
                    Spalten: id, userID (Nummer in RFEM), impl_id, impl_table

    Umsetzung       NodeImplStandard (coordinates_x/y/z), LineImplPolyline,
                    LineImplArc, MemberImplTension, SurfaceImplPlane,
                    NodalSupportImpl, ...  -> ueber impl_table/impl_id

    Listen          <Umsetzung>_<feld>, z. B. NodalSupportImpl_nodes,
                    LineImplPolyline_definitionNodes; die Zielspalte heisst je
                    nach Tabelle value_id oder reference_id/reference_table.

    Federn          SpringConstants (owner_id/owner_table) mit
                    springConstantAlongX ... AroundZ, nonlinearityType*,
                    nonlinearityFrictionCoefficient_* und der Liste
                    SpringConstants_partialActivities (Teilweise Wirkung).

Federwerte: ``inf`` = starr, ``0`` = frei, endlich = Federsteifigkeit [N/m].

Nicht dokumentiert und deshalb ausdruecklich als Annahme behandelt sind die
Zahlenwerte der Nichtlinearitaets-Aufzaehlung (siehe NONLINEARITY_TYPES). Der
Wert 0 = linear ist an der Datei belegt. Jede andere Kennzahl wird im Protokoll
mit Rohwert und Deutung ausgewiesen; unbekannte Kennzahlen lassen den
Freiheitsgrad linear und erzeugen eine Warnung. Die Zuordnung laesst sich
ueber ``nonlinearity_map`` oder ein XSD/WSDL aus der RFEM-Installation
(``nonlinearity_map_from_xsd``) ersetzen.

    from statik3d.importers.rfem6_db import read_rf6, summary
    print(summary("modell.rf6"))
    log = []
    m = read_rf6("modell.rf6", log=log)
"""
from __future__ import annotations

import math
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile

import numpy as np

from ..model import Model, Material, Section, ShellProp, DofBehaviour
from . import _common as C

DB_NAME = "model.db"
FORMAT_FILE = "format.txt"

#: Achsen der Federkonstanten in der Reihenfolge der Freiheitsgrade 0..5
AXES = ("AlongX", "AlongY", "AlongZ", "AroundX", "AroundY", "AroundZ")

#: Reibbeiwerte: {begrenzter FHG: {Spaltenname: Bezugs-FHG}}.
#: RFEM stellt die Reibung an dem Freiheitsgrad ein, dessen Kraft begrenzt wird;
#: der Zusatz nennt die Bezugsrichtung. nonlinearityFrictionCoefficient_XZ
#: begrenzt also die Kraft in X auf mu * |F_Z| - der uebliche Fall eines
#: Gleitlagers mit lotrechter Auflagerkraft.
FRICTION_COLUMNS = {
    0: {"nonlinearityFrictionCoefficient_X_XY": 1, "nonlinearityFrictionCoefficient_XZ": 2},
    1: {"nonlinearityFrictionCoefficient_Y_YX": 0, "nonlinearityFrictionCoefficient_YZ": 2},
    2: {"nonlinearityFrictionCoefficient_Z_ZX": 0, "nonlinearityFrictionCoefficient_ZY": 1},
}

#: Deutung der Kennzahl in nonlinearityType<Achse>.
#: 0 ist an der Datei belegt (alle linearen Lager tragen 0). Die uebrigen
#: Eintraege folgen der Reihenfolge des RFEM-Dialogs und sind eine **Annahme**;
#: sie werden beim Import mit Rohwert protokolliert.
NONLINEARITY_TYPES = {
    0: ("", "linear"),
    1: ("zug", "Ausfall bei Zug"),
    2: ("druck", "Ausfall bei Druck"),
    3: ("zug", "Ausfall aller Kraefte bei Zug"),
    4: ("druck", "Ausfall aller Kraefte bei Druck"),
    5: ("friction", "Reibung"),
    6: ("friction", "Reibung"),
    7: ("friction", "Reibung"),
    8: ("friction", "Reibung"),
    9: ("partial", "teilweise Wirkung"),
    10: ("diagram", "Arbeitslinie"),
}

#: Deutung der Teilwirkungs-Kennzahl (typeNegative/typePositive).
#: 0 = wirksam ist an der Datei belegt.
PARTIAL_TYPES = {0: "wirksam", 1: "Ausfall", 2: "Fliessen", 3: "Ausfall", 4: "Fliessen"}

RIGID = float("inf")
#: Federwerte oberhalb dieser Schranke gelten als starr (RFEM schreibt inf).
RIGID_LIMIT = 1e18


# --------------------------------------------------------------------------
# Behaelter oeffnen
# --------------------------------------------------------------------------
def extract_db(path: str, target_dir: str = None) -> str:
    """``model.db`` aus einer .rf6-Datei herausloesen. Rueckgabe: Dateipfad.

    Ist ``path`` bereits eine SQLite-Datei, wird der Pfad unveraendert
    zurueckgegeben. Die Datenbank wird stromweise kopiert (sie ist in echten
    Projekten mehrere zehn Megabyte gross).
    """
    with open(path, "rb") as f:
        head = f.read(16)
    if head == b"SQLite format 3\x00":
        return path
    if head[:4] not in (b"PK\x03\x04", b"PK\x05\x06"):
        raise ImportError(f"{os.path.basename(path)} ist kein ZIP-Behaelter und keine SQLite-Datei.")
    tmpdir = target_dir or tempfile.mkdtemp(prefix="statik3d_rf6_")
    out = os.path.join(tmpdir, DB_NAME)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        cand = [n for n in names if os.path.basename(n).lower() == DB_NAME]
        if not cand:
            cand = [n for n in names if n.lower().endswith(".db")]
        if not cand:
            raise ImportError(
                f"{os.path.basename(path)}: im ZIP-Behaelter liegt keine Modelldatenbank "
                f"({DB_NAME}). Enthalten sind u. a.: " + ", ".join(sorted(names)[:8]))
        with z.open(cand[0]) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
    return out


def format_info(path: str) -> dict:
    """Inhalt von ``format.txt`` (Programm und Version) aus der .rf6-Datei."""
    info = {}
    try:
        with zipfile.ZipFile(path) as z:
            txt = z.read(FORMAT_FILE).decode("utf-8", "ignore")
    except Exception:
        return info
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    keys = ["programm", "version", "format", "format_version", "zeitstempel"]
    for k, v in zip(keys, lines):
        info[k] = v
    return info


def connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


# --------------------------------------------------------------------------
# Zugriffsschicht
# --------------------------------------------------------------------------
class Db:
    """Lesezugriff auf die Modelldatenbank mit Zwischenspeicher."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        self.tables = {r[0] for r in cur.fetchall()}
        self._cols: dict[str, list[str]] = {}
        self._cache: dict[str, dict] = {}

    # -- Grundlagen ------------------------------------------------------
    def has(self, table: str) -> bool:
        return table in self.tables

    def columns(self, table: str) -> list[str]:
        if table not in self._cols:
            if table not in self.tables:
                self._cols[table] = []
            else:
                cur = self.con.execute(f'PRAGMA table_info("{table}")')
                self._cols[table] = [r[1] for r in cur.fetchall()]
        return self._cols[table]

    def rows(self, table: str, where: str = "", args=()) -> list[dict]:
        if table not in self.tables:
            return []
        sql = f'SELECT * FROM "{table}"' + (f" WHERE {where}" if where else "")
        cur = self.con.execute(sql, args)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def count(self, table: str) -> int:
        if table not in self.tables:
            return 0
        return self.con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

    def by_id(self, table: str) -> dict:
        """{id: Zeile} einer Tabelle (zwischengespeichert)."""
        key = "id:" + table
        if key not in self._cache:
            self._cache[key] = {r["id"]: r for r in self.rows(table)}
        return self._cache[key]

    def container(self, table: str) -> dict:
        """Listenspalte lesen: {besitzer_id: [ziel_id, ...]} in Container-Reihenfolge.

        Je nach Tabelle heisst die Zielspalte ``value_id`` oder ``reference_id``.
        """
        key = "c:" + table
        if key in self._cache:
            return self._cache[key]
        out: dict[int, list] = {}
        cols = self.columns(table)
        target = None
        for cand in ("value_id", "reference_id", "value"):
            if cand in cols:
                target = cand
                break
        if target:
            order = "container_order" if "container_order" in cols else "rowid"
            cur = self.con.execute(
                f'SELECT id, "{target}" FROM "{table}" ORDER BY id, {order}')
            for oid, val in cur.fetchall():
                out.setdefault(oid, []).append(val)
        self._cache[key] = out
        return out

    def container_rows(self, table: str) -> dict:
        """Listenspalte mit allen Feldern: {besitzer_id: [zeile, ...]}."""
        key = "cr:" + table
        if key in self._cache:
            return self._cache[key]
        out: dict[int, list] = {}
        for r in self.rows(table):
            out.setdefault(r["id"], []).append(r)
        for v in out.values():
            v.sort(key=lambda r: r.get("container_order") or 0)
        self._cache[key] = out
        return out

    def impls(self, handle: str) -> list[tuple[dict, dict]]:
        """[(Griff-Zeile, Umsetzungs-Zeile)] einer Objektart."""
        out = []
        groups: dict[str, list[dict]] = {}
        for h in self.rows(handle):
            groups.setdefault(h.get("impl_table") or "", []).append(h)
        for tbl, hs in groups.items():
            impl = self.by_id(tbl) if tbl else {}
            for h in hs:
                row = impl.get(h.get("impl_id"))
                if row is not None:
                    out.append((h, dict(row)))
        out.sort(key=lambda p: p[0]["id"])
        return out


def is_rfem6(db: "Db") -> bool:
    """Erkennt das RFEM-6-Schema an seinen Kerntabellen."""
    need = ("Node", "NodeImplStandard", "Line", "Material")
    return all(db.has(t) for t in need) and "impl_table" in db.columns("Node")


# --------------------------------------------------------------------------
# Nichtlinearitaet
# --------------------------------------------------------------------------
def nonlinearity_map_from_xsd(path: str) -> dict:
    """Kennzahl -> Name aus einem XSD/WSDL der RFEM-Web-Services ableiten.

    Dlubal veroeffentlicht die Namen der Aufzaehlung in der Schnittstelle
    (nicht den Dateiaufbau). Liegt eine solche Datei vor - etwa aus der
    RFEM-Installation -, ergibt sich die Zuordnung daraus zwingend statt aus
    einer Annahme. Gesucht wird die erste Aufzaehlung, deren Werte mit
    ``NONLINEARITY`` beginnen; die Reihenfolge ergibt die Kennzahl.
    """
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    best = []
    for block in re.findall(r"<xs:restriction\b.*?</xs:restriction>", text, re.S | re.I):
        vals = re.findall(r'<xs:enumeration[^>]*value="([^"]+)"', block, re.I)
        if vals and sum(1 for v in vals if "NONLINEARITY" in v.upper()) >= max(2, len(vals) // 2):
            if len(vals) > len(best):
                best = vals
    out = {}
    for i, name in enumerate(best):
        out[i] = (_failure_from_name(name), name)
    return out


def _failure_from_name(name: str) -> str:
    """Ausfallart aus dem Namen einer Aufzaehlung (englisch oder deutsch)."""
    u = name.upper()
    if "FRICTION" in u:
        return "friction"
    if "PARTIAL" in u:
        return "partial"
    if "DIAGRAM" in u:
        return "diagram"
    if "NONE" in u or u.endswith("_TYPE"):
        return ""
    neg = "NEGATIVE" in u or "TENSION" in u or "ZUG" in u
    pos = "POSITIVE" in u or "COMPRESSION" in u or "DRUCK" in u
    if "FAILURE" in u or "AUSFALL" in u:
        if neg and not pos:
            return "zug"
        if pos and not neg:
            return "druck"
    return ""


def _load_map(nonlinearity_map=None) -> dict:
    if isinstance(nonlinearity_map, dict):
        m = dict(NONLINEARITY_TYPES)
        m.update(nonlinearity_map)
        return m
    src = nonlinearity_map or os.environ.get("STATIK3D_RFEM6_NONLIN")
    if src and os.path.isfile(src):
        m = dict(NONLINEARITY_TYPES)
        m.update(nonlinearity_map_from_xsd(src))
        return m
    return dict(NONLINEARITY_TYPES)


def _stiffness(value) -> tuple[str, float]:
    """Federwert der Datenbank -> (typ, Steifigkeit)."""
    if value is None:
        return "free", 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "free", 0.0
    if math.isinf(v) or abs(v) >= RIGID_LIMIT:
        return "rigid", 0.0
    if v <= 0.0:
        return "free", 0.0
    return "spring", v


def spring_behaviours(sc: dict, partials: list = None, nlmap: dict = None,
                      label: str = "", log: list = None) -> dict:
    """Eine ``SpringConstants``-Zeile -> {FHG: DofBehaviour}.

    Beruecksichtigt Steifigkeit (starr/frei/Feder), Ausfallart, Schlupf,
    Grenzkraft (Fliessen) und Reibbeiwerte mit Bezugs-Freiheitsgrad.
    """
    nlmap = nlmap or dict(NONLINEARITY_TYPES)
    partials = partials or []
    out: dict[int, DofBehaviour] = {}
    for d, axis in enumerate(AXES):
        typ, k = _stiffness(sc.get("springConstant" + axis))
        beh = DofBehaviour(typ=typ, stiffness=k)
        code = int(sc.get("nonlinearityType" + axis) or 0)
        if code:
            mode, text = nlmap.get(code, (None, None))
            if mode is None:
                C.warn(log, f"{label}FHG {d}: Nichtlinearitaet Kennzahl {code} unbekannt - "
                            "Freiheitsgrad bleibt linear.")
            elif mode in ("zug", "druck"):
                beh.failure = mode
                C.say(log, f"  {label}FHG {d}: {text} (Kennzahl {code})")
            elif mode in ("friction", "partial", "diagram"):
                C.say(log, f"  {label}FHG {d}: {text} (Kennzahl {code})")
        # Teilweise Wirkung: Ausfall/Fliessen/Schlupf stehen dort ausdruecklich
        pa = partials[d] if d < len(partials) else None
        if pa:
            neg = int(pa.get("typeNegative") or 0)
            pos = int(pa.get("typePositive") or 0)
            slip = max(abs(pa.get("slippageNegative") or 0.0),
                       abs(pa.get("slippagePositive") or 0.0))
            fneg = abs(pa.get("forceNegative") or 0.0)
            fpos = abs(pa.get("forcePositive") or 0.0)
            if slip:
                beh.slip = slip
            # positive Verschiebung = Zug am Lager, negative = Druck
            if pos and not neg:
                beh.failure = beh.failure or "zug"
            elif neg and not pos:
                beh.failure = beh.failure or "druck"
            elif neg and pos:
                C.warn(log, f"{label}FHG {d}: beide Richtungen mit Teilwirkung - "
                            "als frei uebernommen.")
                beh.typ = "free"
            lim = max(fneg, fpos)
            if lim and (PARTIAL_TYPES.get(max(neg, pos)) == "Fliessen"):
                beh.limit = lim
            if neg or pos or slip:
                C.say(log, f"  {label}FHG {d}: teilweise Wirkung "
                           f"({PARTIAL_TYPES.get(neg, neg)}/-, {PARTIAL_TYPES.get(pos, pos)}/+"
                           + (f", Schlupf {slip * 1000:g} mm" if slip else "")
                           + (f", Grenzkraft {lim / 1e3:g} kN" if beh.limit else "") + ")")
        out[d] = beh
    # Reibung: der Beiwert steht an dem FHG, dessen Kraft begrenzt wird
    for d, cols in FRICTION_COLUMNS.items():
        for col, ref in cols.items():
            try:
                mu = float(sc.get(col) or 0.0)
            except (TypeError, ValueError):
                mu = 0.0
            if mu > 0.0 and d in out:
                out[d].mu = mu
                out[d].mu_ref = ref
                _friction_acts(out[d], f"{label}FHG {d}", log)
                C.say(log, f"  {label}FHG {d}: Reibung mu = {mu:g} bezogen auf FHG {ref}")
    return out


def _friction_acts(beh: DofBehaviour, label: str, log: list) -> None:
    """Ein Reibungs-Freiheitsgrad muss wirken, sonst geht die Reibung verloren.

    RFEM traegt bei reiner Reibung die Steifigkeit 0 ein: der Freiheitsgrad
    haelt starr, bis die Reibkraft mu * |N| erreicht ist, und gleitet dann.
    Genau so wird er hier gefuehrt.
    """
    if beh.typ == "free":
        beh.typ = "rigid"
        C.say(log, f"  {label}: Steifigkeit 0 mit Reibung - haftet starr bis mu * |N|, "
                   "danach Gleiten")


# --------------------------------------------------------------------------
# Modellaufbau
# --------------------------------------------------------------------------
def _material(db: Db, mat_id: int, model: Model, cache: dict, log: list,
              chars: dict = None) -> str:
    """Material aus der Datenbank uebernehmen. Rueckgabe: Name im Modell.

    RFEM speichert im Projekt nur die Kennwerte und die Nummer des Eintrags in
    der Dlubal-Materialdatenbank, nicht dessen Namen. Fehlt der Name, wird er
    aus Streckgrenze und E-Modul gebildet (S235, S355, ...), sonst aus der
    Materialnummer.
    """
    if mat_id in cache:
        return cache[mat_id]
    handles = db.by_id("Material")
    h = handles.get(mat_id)
    name = ""
    E, nu, rho, alpha, fy, fu = 210e9, 0.3, 7850.0, 1.2e-5, None, None
    dbnr = None
    if h is not None:
        impl = db.by_id(h["impl_table"] or "MaterialImpl").get(h["impl_id"])
        if impl is not None:
            name = (impl.get("name") or "").strip()
            dbnr = impl.get("databaseMaterialId")
            props = _material_props(db, impl)
            E = props.get("E", E)
            nu = props.get("nu", nu)
            alpha = props.get("alpha", alpha)
            fy = props.get("f_y") or props.get("f_p01k")
            fu = props.get("f_u") or props.get("f_pk")
            rho = props.get("rho") or 0.0
            if not rho and props.get("gamma"):
                rho = props["gamma"] / 9.81      # Wichte [N/m^3] -> Dichte
            rho = rho or 7850.0
    if chars:
        E = chars.get("modulusOfElasticity") or E
        nu = chars.get("poissonsRatio") or nu
        rho = chars.get("density") or rho
        fy = fy or chars.get("compressiveStrength")
        fu = fu or chars.get("tensileStrength")
    grade = ""
    if not name:
        name, grade = _material_name(E, fy, h.get("userID") if h else mat_id, dbnr)
    grade = grade or C.steel_grade_from_text(name) or ""
    name = C.unique_name(model.materials, name)
    model.add_material(Material(name, E=E, nu=nu, rho=rho, alpha=alpha,
                                fy=fy, fu=fu, grade=grade))
    C.say(log, f"  Material '{name}': E = {E / 1e9:g} GPa"
               + (f", f_y = {fy / 1e6:g} N/mm^2" if fy else "")
               + (f", rho = {rho:g} kg/m^3" if rho else "")
               + (f" (Dlubal-Datenbanknummer {dbnr})" if dbnr else ""))
    cache[mat_id] = name
    return name


def _material_name(E: float, fy, userid, dbnr) -> tuple[str, str]:
    """Name und Stahlsorte aus den Kennwerten, wenn die Datei keinen Namen fuehrt."""
    from ..model import STEEL_GRADES
    if fy and abs(E - 210e9) < 20e9:
        for g, (gfy, _gfu, _a, _b) in STEEL_GRADES.items():
            if abs(gfy - fy) < 1e6:
                return g, g
        return f"Stahl f_y={fy / 1e6:g}", ""
    return f"Material {userid}" + (f" (DB {dbnr})" if dbnr else ""), ""


def _material_props(db: Db, impl: dict) -> dict:
    """{'E':..., 'G':..., 'rho':...} aus MaterialData/MaterialProperties."""
    out: dict[str, float] = {}
    data = [r for r in db.rows("MaterialData") if r.get("impl_id") == impl.get("id")]
    if not data:
        vec = db.container("MaterialImpl_materialDataVector").get(impl.get("id"), [])
        data = [db.by_id("MaterialData").get(v) for v in vec]
        data = [dict(d) for d in data if d is not None]
    doubles = db.by_id("MaterialPropertyDouble")
    for d in data:
        pid = d.get("properties_id")
        if pid is None:
            continue
        keys = db.container("MaterialProperties_propertiesMap_keys").get(pid, [])
        vals = db.container_rows("MaterialProperties_propertiesMap_values").get(pid, [])
        for k, v in zip(keys, vals):
            if v.get("reference_table") != "MaterialPropertyDouble":
                continue
            row = doubles.get(v.get("reference_id"))
            if row is None:
                continue
            val = row["valueSI"]
            if val not in (None, 0.0) and k not in out:
                out[str(k)] = float(val)
    return out


#: Kennwerte des Querschnitts in SectionData_parameterValues
SECTION_KEYS = {"A": "A", "A_y": "Asy", "A_z": "Asz", "I_y": "Iy", "I_z": "Iz",
                "I_t": "It", "I_w": "Iw", "h": "h", "b": "b", "t_w": "tw",
                "t_f": "tf", "r": "r", "W_el_y": "Wel_y", "W_el_z": "Wel_z",
                "W_pl_y": "Wpl_y", "W_pl_z": "Wpl_z", "alpha": "alpha"}


#: Parametrische Grundformen: Satz der Bemassungssymbole -> (typ, Bezeichnung)
SHAPE_BY_SYMBOLS = {
    ("d",): ("circle", "Rund"),
    ("D", "t"): ("CHS", "Rohr"),
    ("d", "t"): ("CHS", "Rohr"),
    ("b", "h"): ("rect", "Rechteck"),
    ("b", "h", "t"): ("RHS", "Hohlprofil"),
    ("b", "h", "t_f", "t_w"): ("I", "I-Profil"),
    ("b", "h", "r", "t_f", "t_w"): ("I", "I-Profil"),
}


def _section(db: Db, sec_id: int, model: Model, cache: dict, matcache: dict,
             log: list) -> tuple[str, str]:
    """Querschnitt uebernehmen. Rueckgabe: (Querschnittsname, Materialname)."""
    if sec_id in cache:
        return cache[sec_id]
    h = db.by_id("Section").get(sec_id)
    name = f"Q{sec_id}"
    matname = None
    kw: dict[str, float] = {}
    dims: dict[str, float] = {}
    typ = ""
    if h is not None:
        impl = db.by_id(h["impl_table"] or "").get(h["impl_id"]) if h.get("impl_table") else None
        if impl is not None:
            dims, chars = _section_shape(db, impl)
            typ, label = _shape_of(dims)
            name = ((impl.get("name") or "").strip()
                    or _shape_name(label, dims)
                    or f"Querschnitt {h.get('userID') or sec_id}")
            if impl.get("material_id"):
                matname = _material(db, impl["material_id"], model, matcache, log, chars)
            kw = _section_values(db, impl)
    if matname is None:
        matname = C.ensure_material(model, log=log)
    nm = C.unique_name(model.sections, name)
    sec = C.section_from_designation(name, nm)
    if sec is None:
        sec = Section(name=nm)
        if typ:
            sec.typ = typ
        for sym, field in (("d", "h"), ("D", "h"), ("h", "h"), ("b", "b"),
                           ("t", "tw"), ("t_w", "tw"), ("t_f", "tf"), ("r", "r")):
            if sym in dims and not getattr(sec, field, 0.0):
                setattr(sec, field, dims[sym])
        if sec.typ == "circle" and sec.h and not sec.b:
            sec.b = sec.h
    for key, val in kw.items():
        setattr(sec, key, val)
    if sec.zmax <= 0 and sec.h:
        sec.zmax = sec.h / 2.0
    if sec.ymax <= 0 and sec.b:
        sec.ymax = sec.b / 2.0
    if not kw:
        C.warn(log, f"Querschnitt '{name}': keine Kennwerte in der Datei - Ersatzwerte.")
    else:
        C.say(log, f"  Querschnitt '{nm}': A = {sec.A * 1e4:.2f} cm^2, "
                   f"I_y = {sec.Iy * 1e8:.1f} cm^4, I_z = {sec.Iz * 1e8:.1f} cm^4, "
                   f"I_t = {sec.It * 1e8:.1f} cm^4")
    model.add_section(sec)
    cache[sec_id] = (nm, matname)
    return cache[sec_id]


def _section_shape(db: Db, impl: dict) -> tuple[dict, dict]:
    """({Bemassungssymbol: Wert [m]}, Materialkennwerte) eines Parameterprofils."""
    lib_tbl = impl.get("librarySection_table")
    lib_id = impl.get("librarySection_id")
    dims: dict[str, float] = {}
    chars: dict = {}
    if not (lib_tbl and lib_id and db.has(lib_tbl)):
        return dims, chars
    lib = db.by_id(lib_tbl).get(lib_id)
    if lib is None:
        return dims, chars
    vals = db.container(lib_tbl + "_parameterValues").get(lib_id, [])
    sd_id = lib["sectionData_id"] if "sectionData_id" in lib.keys() else None
    if sd_id is not None:
        syms = [r.get("symbol") for r in
                db.container_rows("SectionData_dimensions").get(sd_id, [])]
        for sym, val in zip(syms, vals):
            if sym and val is not None:
                dims[str(sym)] = float(val)
    ref = db.container(lib_tbl + "_sectionMaterialCharacteristics").get(lib_id, [])
    if ref:
        row = db.by_id("SectionMaterialCharacteristics").get(ref[0])
        if row is not None:
            chars = {k: row[k] for k in row.keys() if row[k] not in (None, 0, 0.0)}
    return dims, chars


def _shape_of(dims: dict) -> tuple[str, str]:
    return SHAPE_BY_SYMBOLS.get(tuple(sorted(dims)), ("", ""))


def _shape_name(label: str, dims: dict) -> str:
    if not label or not dims:
        return ""
    order = ["d", "D", "h", "b", "t", "t_w", "t_f", "r"]
    keys = sorted(dims, key=lambda k: (order.index(k) if k in order else 99, k))
    return label + " " + "x".join(f"{dims[k] * 1000:g}" for k in keys)


def _section_values(db: Db, impl: dict) -> dict:
    """Querschnittskennwerte (SI) aus SectionData_parameterValues."""
    lib_tbl = impl.get("librarySection_table")
    lib_id = impl.get("librarySection_id")
    sd_id = None
    if lib_tbl and lib_id and db.has(lib_tbl):
        lib = db.by_id(lib_tbl).get(lib_id)
        if lib is not None:
            sd_id = lib["sectionData_id"] if "sectionData_id" in lib.keys() else None
    if sd_id is None:
        return {}
    keys = db.container("SectionData_parameterValues_keys").get(sd_id, [])
    vals = db.container_rows("SectionData_parameterValues_values").get(sd_id, [])
    out: dict[str, float] = {}
    for k, v in zip(keys, vals):
        field = SECTION_KEYS.get(str(k))
        if not field:
            continue
        raw = v.get("valueSI")
        if raw is None:
            continue
        try:
            out[field] = float(raw)
        except (TypeError, ValueError):
            continue
    return {k: v for k, v in out.items() if v or k == "alpha"}


def _line_nodes(db: Db) -> dict:
    """{Line.id: [Node.id, ...]} fuer alle Linienarten."""
    out: dict[int, list] = {}
    for h, impl in db.impls("Line"):
        tbl = h["impl_table"]
        nodes = db.container(tbl + "_definitionNodes").get(impl["id"], [])
        if not nodes:
            nodes = db.container(tbl + "_nodes").get(impl["id"], [])
        if nodes:
            out[h["id"]] = list(nodes)
    return out


def _polygon_area(pts: np.ndarray) -> float:
    """Flaeche eines ebenen Polygons im Raum (Newell)."""
    if len(pts) < 3:
        return 0.0
    n = np.zeros(3)
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n += np.cross(a, b)
    return 0.5 * float(np.linalg.norm(n))


def _hinge_from_springs(db: Db, hinge_id: int, end: int, model: Model,
                        nlmap: dict, log: list):
    """MemberHinge der Datenbank -> Gelenkdefinition im Modell."""
    h = db.by_id("MemberHinge").get(hinge_id)
    if h is None:
        return None
    impl = db.by_id(h.get("impl_table") or "MemberHingeImpl").get(h.get("impl_id"))
    if impl is None:
        return None
    sc = _spring_row(db, h.get("impl_table") or "MemberHingeImpl", impl["id"])
    name = (impl.get("name") or "").strip() or f"Gelenk {h.get('userID') or hinge_id}"
    name = C.unique_name(model.hinges, f"{name}_{'A' if end == 0 else 'E'}")
    kw = {}
    if sc:
        beh = spring_behaviours(sc, _partials(db, sc), nlmap, f"{name}: ", log)
        for d, b in beh.items():
            if b.typ == "free":
                kw[["ux", "uy", "uz", "phix", "phiy", "phiz"][d]] = "free"
            elif b.typ == "spring" and b.stiffness > 0:
                kw[["ux", "uy", "uz", "phix", "phiy", "phiz"][d]] = b.stiffness
    if not kw:
        return None
    return model.add_hinge(name, end=end, **kw)


def _spring_row(db: Db, owner_table: str, owner_id: int) -> dict:
    """SpringConstants-Zeile zu einem Besitzer."""
    key = "sc:" + owner_table
    if key not in db._cache:
        idx: dict[int, dict] = {}
        for r in db.rows("SpringConstants", "owner_table = ?", (owner_table,)):
            idx[r["owner_id"]] = r
        db._cache[key] = idx
    return db._cache[key].get(owner_id, {})


def _partials(db: Db, sc: dict) -> list:
    """Teilwirkungs-Zeilen einer SpringConstants-Zeile, nach Achse geordnet."""
    if not sc:
        return []
    rows = db.container_rows("SpringConstants_partialActivities").get(sc.get("id"), [])
    out = [None] * 6
    for r in rows:
        i = int(r.get("container_order") or 0)
        if 0 <= i < 6:
            out[i] = r
    return out


def read_rf6(path: str, model: Model = None, log: list = None,
             nonlinearity_map=None, keep_db: bool = False,
             structure_only: bool = False, **_) -> Model:
    """RFEM-6-Projektdatei (.rf6) oder ``model.db`` einlesen.

    Uebernommen werden Knoten, Linien, Staebe mit Querschnitt, Material und
    Gelenken, Knoten-, Linien- und Flaechenlager mit Nichtlinearitaeten
    (Ausfall bei Zug/Druck, Schlupf, Grenzkraft, Reibung) sowie die Geometrie
    der Flaechen. Flaechen und Volumen werden nicht vernetzt; ihre Anzahl und
    Zuordnung stehen im Protokoll.

    ``structure_only=True`` behaelt nur die Knoten, an denen Stabelemente
    haengen. Damit ist das Modell unmittelbar rechenbar; die Geometrie der
    Flaechen und Volumen entfaellt. Ohne diese Angabe wird alles uebernommen -
    zur Ansicht vollstaendig, fuer eine Rechnung erst nach dem Vernetzen der
    Flaechen.
    """
    m = model or Model(os.path.splitext(os.path.basename(path))[0])
    fmt = format_info(path)
    if fmt:
        C.say(log, "RFEM-Projektdatei: " + " ".join(
            f"{k}={v}" for k, v in fmt.items() if k in ("programm", "version", "format")))
    db_path = extract_db(path)
    tmp_dir = os.path.dirname(db_path) if db_path != path else None
    con = connect(db_path)
    try:
        db = Db(con)
        if not is_rfem6(db):
            raise ImportError(
                f"{os.path.basename(path)}: die Modelldatenbank folgt nicht dem "
                "bekannten RFEM-6-Schema (Tabellen Node/NodeImplStandard/Line fehlen).")
        nlmap = _load_map(nonlinearity_map)
        _build(db, m, log, nlmap)
        if structure_only:
            keep_structure(m, log)
    finally:
        con.close()
        if tmp_dir and not keep_db:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    return m


def _build(db: Db, m: Model, log: list, nlmap: dict) -> None:
    # ---- Knoten -------------------------------------------------------
    node_of: dict[int, int] = {}
    user_of: dict[int, int] = {}
    coords = []
    for h, impl in db.impls("Node"):
        node_of[h["id"]] = len(coords)
        user_of[h["id"]] = h.get("userID")
        coords.append((impl.get("coordinates_x") or 0.0,
                       impl.get("coordinates_y") or 0.0,
                       impl.get("coordinates_z") or 0.0))
    if not coords:
        raise ImportError("Die Modelldatenbank enthaelt keine Knoten.")
    m.add_nodes(np.asarray(coords, float))
    C.say(log, f"{len(coords)} Knoten gelesen")

    # ---- Linien -------------------------------------------------------
    line_nodes = _line_nodes(db)
    line_name: dict[int, str] = {}
    arcs = 0
    for h, impl in db.impls("Line"):
        nodes = [node_of[n] for n in line_nodes.get(h["id"], []) if n in node_of]
        if len(nodes) < 2:
            continue
        typ = "arc" if "Arc" in (h["impl_table"] or "") else "polyline"
        arcs += typ == "arc"
        nm = C.unique_name(m.lines, f"L{h.get('userID') or h['id']}")
        m.add_line(nm, nodes, typ)
        line_name[h["id"]] = nm
    C.say(log, f"{len(line_name)} Linien gelesen ({arcs} Boegen, als Sehne durch die "
               "Definitionsknoten gefuehrt)")

    # ---- Staebe -------------------------------------------------------
    seccache: dict[int, tuple] = {}
    matcache: dict[int, str] = {}
    n_beams = 0
    for h, impl in db.impls("Member"):
        nodes = [node_of[n] for n in line_nodes.get(impl.get("line_id"), []) if n in node_of]
        if len(nodes) < 2:
            C.warn(log, f"Stab {h.get('userID')}: Linie {impl.get('line_id')} ohne Knoten - uebersprungen.")
            continue
        sec_id = impl.get("sectionStart_id") or impl.get("sectionEnd_id")
        if sec_id:
            sname, mname = _section(db, sec_id, m, seccache, matcache, log)
        else:
            mname = C.ensure_material(m, log=log)
            sname = C.ensure_section(m, log=log)
        roll = float(impl.get("angle") or 0.0)
        elems = []
        for a, b in zip(nodes[:-1], nodes[1:]):
            if a == b:
                continue
            elems.append(m.add_element("beam", [a, b], mname, sname, roll=roll))
            n_beams += 1
        if not elems:
            continue
        mem = m.add_member(C.unique_name(m.members, f"S{h.get('userID') or h['id']}"), elems)
        if impl.get("isDeactivatedForCalculation"):
            C.say(log, f"  Stab {h.get('userID')} ist in RFEM deaktiviert - dennoch uebernommen.")
        for end, key in ((0, "memberHingeStart_id"), (1, "memberHingeEnd_id")):
            hid = impl.get(key)
            if not hid:
                continue
            hg = _hinge_from_springs(db, hid, end, m, nlmap, log)
            if hg is not None:
                m.apply_hinge(elems[0] if end == 0 else elems[-1], hg)
        del mem
    C.say(log, f"{len(m.members)} Staebe mit {n_beams} Stabelementen gelesen")

    # ---- Knotenlager ---------------------------------------------------
    n_sup = 0
    for h, impl in db.impls("NodalSupport"):
        tgt = db.container("NodalSupportImpl_nodes").get(impl["id"], [])
        nodes = [node_of[n] for n in tgt if n in node_of]
        name = (impl.get("name") or "").strip() or f"Knotenlager {h.get('userID') or h['id']}"
        sc = _spring_row(db, h.get("impl_table") or "NodalSupportImpl", impl["id"])
        if not sc:
            C.warn(log, f"{name}: keine Federkonstanten gefunden - uebersprungen.")
            continue
        beh = spring_behaviours(sc, _partials(db, sc), nlmap, f"{name}: ", log)
        dofs = [d for d, b in beh.items() if b.acts]
        if not nodes:
            C.say(log, f"  {name}: keinem Knoten zugewiesen")
            continue
        for nd in nodes:
            s = m.support(nd, dofs, name=name)
            for d, b in beh.items():
                if b.acts:
                    s.behaviour[d] = DofBehaviour(**vars(b))
            n_sup += 1
        C.say(log, f"  {name}: {len(nodes)} Knoten, "
                   + ", ".join(f"{['ux','uy','uz','phix','phiy','phiz'][d]}={beh[d].describe()}"
                               for d in sorted(beh) if beh[d].acts))
    C.say(log, f"{n_sup} Knotenlager gesetzt")

    # ---- Linienlager ---------------------------------------------------
    for h, impl in db.impls("LineSupport"):
        lines = db.container("LineSupportImpl_lines").get(impl["id"], [])
        name = (impl.get("name") or "").strip() or f"Linienlager {h.get('userID') or h['id']}"
        sc = _spring_row(db, h.get("impl_table") or "LineSupportImpl", impl["id"])
        if not sc:
            continue
        beh = spring_behaviours(sc, _partials(db, sc), nlmap, f"{name}: ", log)
        nodes: list[int] = []
        for lid in lines:
            for n in line_nodes.get(lid, []):
                if n in node_of and node_of[n] not in nodes:
                    nodes.append(node_of[n])
        if not nodes:
            C.say(log, f"  {name}: keiner Linie zugewiesen")
            continue
        ls = m.add_line_support(nodes, name=name)
        for d, b in beh.items():
            if b.acts:
                ls.behaviour[d] = DofBehaviour(**vars(b))
        C.say(log, f"  {name}: {len(lines)} Linien, {len(nodes)} Knoten")

    # ---- Flaechen und Flaechenlager -------------------------------------
    surf_nodes, surf_area = _surface_nodes(db, node_of, m)
    n_surf = db.count("Surface")
    C.say(log, f"{len(surf_nodes)} von {n_surf} Flaechen mit Randpolygon gelesen")
    if len(surf_nodes) < n_surf:
        C.say(log, f"  {n_surf - len(surf_nodes)} Flaechen ohne aufloesbaren Rand "
                   "(getrimmte Flaechen, Freiformraender)")
    _surfaces(db, m, surf_nodes, log, matcache)
    for h, impl in db.impls("SurfaceSupport"):
        sids = db.container("SurfaceSupportImpl_surfaces").get(impl["id"], [])
        name = (impl.get("name") or "").strip() or f"Flaechenlager {h.get('userID') or h['id']}"
        beh = _surface_behaviour(impl, nlmap, name, log)
        nodes: list[int] = []
        areas: dict[int, float] = {}
        for sid in sids:
            ns = surf_nodes.get(sid, [])
            if not ns:
                continue
            a = surf_area.get(sid, 0.0) / len(ns)
            for n in ns:
                areas[n] = areas.get(n, 0.0) + a
        nodes = sorted(areas)
        if not nodes:
            C.say(log, f"  {name}: {len(sids)} Flaechen, keine Knoten aufloesbar")
            continue
        ss = m.add_surface_support(name=name, nodes=nodes, areas=[areas[n] for n in nodes])
        for d, b in beh.items():
            if b.acts:
                ss.behaviour[d] = DofBehaviour(**vars(b))
        C.say(log, f"  {name}: {len(sids)} Flaechen, {len(nodes)} Knoten, "
                   f"A = {sum(areas.values()):.3f} m^2")

    _solids(db, m, surf_nodes, log, matcache)
    _load_cases(db, m, log)
    _diagnose(m, log)


def _diagnose(m: Model, log: list) -> None:
    """Rechenbarkeit des importierten Modells beurteilen und benennen."""
    if not m.elements:
        C.warn(log, "Das Modell enthaelt keine Elemente - nur Geometrie.")
        return
    adj: dict[int, set] = {}
    for e in m.elements:
        for a in e.nodes:
            for b in e.nodes:
                if a != b:
                    adj.setdefault(int(a), set()).add(int(b))
    seen: set[int] = set()
    comps = []
    for start in adj:
        if start in seen:
            continue
        stack, group = [start], []
        seen.add(start)
        while stack:
            x = stack.pop()
            group.append(x)
            for y in adj[x]:
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        comps.append(group)
    held = {s.node for s in m.supports}
    for ls in m.line_supports:
        held.update(ls.nodes)
    for ss in m.surface_supports:
        held.update(ss.nodes)
    free = [g for g in comps if not (set(g) & held)]
    loose = m.nn - len(seen)
    if loose:
        C.say(log, f"{loose} Knoten tragen kein Element (Rand von Flaechen und Volumen). "
                   "Fuer eine Berechnung entweder die Flaechen vernetzen oder mit "
                   "structure_only=True nur das Stabtragwerk uebernehmen.")
    if len(comps) > 1:
        C.say(log, f"Das Stabtragwerk zerfaellt in {len(comps)} Teile "
                   f"(groesster Teil {max(len(g) for g in comps)} Knoten).")
    if free:
        C.warn(log, f"{len(free)} Teiltragwerke ohne Lager - so ist das Modell nicht "
                    "rechenbar. In dieser Datei tragen Flaechen und Volumen die Lasten; "
                    "sie muessen dafuer vernetzt werden.")


#: Einwirkungskategorien RFEM (actionCategoryId) -> Kategorie in Statik3D
ACTION_CATEGORY = {1: "G", 2: "G", 3: "Q", 11: "Q", 12: "Q", 13: "Q"}


def _load_cases(db: Db, m: Model, log: list) -> None:
    """Lastfaelle mit Namen, Kategorie und Eigengewichtsfaktor uebernehmen.

    Die Lasten selbst (Vorspannung, Flaechenlasten, freie Lasten) haengen in
    RFEM an Objekten, die ohne Netz nicht aufloesbar sind; ihre Anzahl steht
    im Protokoll.
    """
    n = 0
    cases = db.impls("LoadCase")
    if cases:
        # Den leeren Standardlastfall vorab abmelden, damit LF1 aus RFEM
        # seinen eigenen Namen behaelt (remove_load_case legt LF1 sonst neu an).
        default = m.load_cases.get("LF1")
        if default is not None and not default.n_loads and len(m.load_cases) == 1:
            m.load_cases.pop("LF1")
            m.active_case = ""
    for h, impl in cases:
        name = (impl.get("name") or "").strip() or f"LF{h.get('userID') or h['id']}"
        cat = ACTION_CATEGORY.get(int(impl.get("actionCategoryId") or 0), "Q")
        nm = C.unique_name(m.load_cases, f"LF{h.get('userID') or h['id']}")
        lc = m.add_load_case(nm, cat, description=name, activate=False)
        gz = impl.get("selfWeightFactors_z")
        if impl.get("selfWeightActive") and gz:
            lc.gravity = [0.0, 0.0, -9.81 * float(gz)]
        n += 1
    if n:
        C.say(log, f"{n} Lastfaelle uebernommen (Namen, Einwirkungskategorie, "
                   "Eigengewichtsfaktor)")
    for table, label in (("MemberLoad", "Stablasten"), ("SurfaceLoad", "Flaechenlasten"),
                         ("NodalLoad", "Knotenlasten"), ("LineLoad", "Linienlasten"),
                         ("FreeRectangularLoad", "freie Rechtecklasten")):
        c = db.count(table)
        if c:
            C.say(log, f"  {c} {label} in der Datei - nicht uebernommen "
                       "(Lastobjekte haengen am RFEM-Netz).")


def _surface_nodes(db: Db, node_of: dict, m: Model) -> tuple[dict, dict]:
    """{Surface.id: [Knoten]} und {Surface.id: Flaeche [m^2]}.

    Eckknoten stehen entweder unmittelbar (Viereckflaechen) oder ueber die
    Randlinien; die Flaeche folgt aus dem Randpolygon (Newell).
    """
    line_nodes = _line_nodes(db)
    nodes_out: dict[int, list] = {}
    area_out: dict[int, float] = {}
    for h, impl in db.impls("Surface"):
        tbl = h["impl_table"] or ""
        raw = db.container(tbl + "_cornerNodes").get(impl["id"], [])
        if raw:
            ring = [n for n in raw if n in node_of]
        else:
            ring = []
            for lid in db.container(tbl + "_boundaryLines").get(impl["id"], []):
                for n in line_nodes.get(lid, []):
                    if n in node_of and n not in ring:
                        ring.append(n)
        if len(ring) < 3:
            continue
        idx = [node_of[n] for n in ring]
        nodes_out[h["id"]] = idx
        area_out[h["id"]] = _polygon_area(m.nodes[idx])
    return nodes_out, area_out


#: Federkonstanten des Flaechenlagers: Spalte -> Freiheitsgrad
SURFACE_SPRINGS = {"springConstant_0": 0, "springConstant_1": 1, "springConstant_2": 2}


def _surface_behaviour(impl: dict, nlmap: dict, label: str, log: list) -> dict:
    """SurfaceSupportImpl -> {FHG: DofBehaviour} (Bettung je m^2)."""
    out: dict[int, DofBehaviour] = {}
    for col, d in SURFACE_SPRINGS.items():
        typ, k = _stiffness(impl.get(col))
        out[d] = DofBehaviour(typ=typ, stiffness=k)
    code = int(impl.get("nonlinearity") or 0)
    if code:
        mode, text = nlmap.get(code, (None, None))
        if mode in ("zug", "druck"):
            out[2].failure = mode
            C.say(log, f"  {label}: uz {text} (Kennzahl {code})")
        elif mode is None:
            C.warn(log, f"{label}: Nichtlinearitaet Kennzahl {code} unbekannt - linear belassen.")
        else:
            C.say(log, f"  {label}: {text} (Kennzahl {code})")
    for col in ("negativeContactStress", "positiveContactStress"):
        val = abs(float(impl.get(col) or 0.0))
        if val:
            out[2].limit = max(out[2].limit, val)
    mu = max(abs(float(impl.get("negativeFrictionCoefficient") or 0.0)),
             abs(float(impl.get("positiveFrictionCoefficient") or 0.0)))
    if mu and code:
        for d in (0, 1):
            out[d].mu = mu
            out[d].mu_ref = 2
            _friction_acts(out[d], f"{label} FHG {d}", log)
        C.say(log, f"  {label}: Reibung mu = {mu:g} in x und y, bezogen auf uz")
    return out


# --------------------------------------------------------------------------
# Flaechen als Schalenelemente
# --------------------------------------------------------------------------
#: Steifigkeitsarten der Flaeche: Tabelle -> (traegt Dicke?, Klartext)
SURFACE_STIFFNESS = {
    "SurfaceStiffnessStandard": (True, "Standard (Dicke und Material)"),
    "SurfaceStiffnessWithoutThickness": (False, "ohne Dicke (Null-Element)"),
    "SurfaceStiffnessRigid": (False, "starr"),
    "SurfaceStiffnessMembrane": (True, "Membran"),
    "SurfaceStiffnessWithoutMembraneTension": (True, "ohne Membranzugkraefte"),
    "SurfaceStiffnessLoadTransfer": (False, "Lastverteilung"),
    "SurfaceStiffnessLoadDistribution": (False, "Lastverteilung"),
    "SurfaceStiffnessGroundwater": (False, "Grundwasser"),
    "SurfaceStiffnessFloor": (False, "Deckenscheibe"),
}


def _thickness_of(db: Db, impl: dict) -> dict:
    """
    Dicke, Material und Art der Flaechensteifigkeit.

    Die Flaeche zeigt ueber ``stiffness_id``/``stiffness_table`` auf ein
    Steifigkeitsobjekt.  Nur ``SurfaceStiffnessStandard`` (und die
    Membranformen) tragen eine Dicke; sie zeigen ueber ``thickness_id`` auf
    ``Thickness`` und von dort auf die Umsetzung, die Dicke und Material
    fuehrt.  Alle anderen Arten sind Flaechen **ohne eigene Steifigkeit**:
    Null-Elemente, starre Flaechen, Lastverteilungsflaechen und - der haeufigste
    Fall in Volumenmodellen - die Randflaechen von Volumenkoerpern.
    """
    tbl = impl.get("stiffness_table") or ""
    sid = impl.get("stiffness_id")
    traegt, text = SURFACE_STIFFNESS.get(tbl, (False, tbl or "unbekannt"))
    out = {"art": tbl, "text": text, "t": 0.0, "material_id": None,
           "variabel": False}
    if not traegt or not sid or not db.has(tbl):
        return out
    row = db.by_id(tbl).get(sid) or {}
    thid = row.get("thickness_id")
    if not thid:
        return out
    th = db.by_id("Thickness").get(thid) or {}
    itbl = th.get("impl_table") or ""
    ti = db.by_id(itbl).get(th.get("impl_id")) if itbl else None
    if not ti:
        return out
    out["material_id"] = ti.get("material_id")
    if "thickness" in ti:
        out["t"] = float(ti.get("thickness") or 0.0)
    else:
        # veraenderliche Dicke: Mittelwert der Stuetzstellen, mit Hinweis
        werte = [float(v) for k, v in ti.items()
                 if k.startswith("thickness") and isinstance(v, (int, float)) and v]
        out["t"] = sum(werte) / len(werte) if werte else 0.0
        out["variabel"] = True
    out["name"] = (ti.get("name") or "").strip()
    return out


def _openings(db: Db) -> dict:
    """{Surface.id: Anzahl Oeffnungen} ueber die integrierten Oeffnungen."""
    out: dict[int, int] = {}
    for tbl in ("SurfaceImplPlane_integratedOpenings",
                "SurfaceImplQuadrangle_integratedOpenings",
                "SurfaceImplTrimmed_integratedOpenings"):
        impl_tbl = tbl.split("_")[0]
        parent = {r["id"]: r.get("parent_id") for r in db.rows(impl_tbl)}
        for oid, lst in db.container(tbl).items():
            sid = parent.get(oid)
            if sid:
                out[sid] = out.get(sid, 0) + len(lst)
    return out


def _surfaces(db: Db, m: Model, surf_nodes: dict, log: list,
              matcache: dict) -> dict:
    """
    Flaechen mit eigener Steifigkeit in Schalenelemente umsetzen.

    Rueckgabe {Surface.id: [Elementnummern]}.

    Flaechen **ohne** Dicke (Null-Elemente, starre Flaechen,
    Lastverteilungsflaechen, Randflaechen von Volumenkoerpern) bekommen keine
    Elemente; ihre Zahl steht im Protokoll.  Flaechen mit **Oeffnung** werden
    ebenfalls nicht vernetzt: das Randpolygon allein wuerde die Oeffnung
    zubetonieren und die Flaeche zu steif machen.  Ein fehlendes Element
    faellt beim Prueflauf auf, eine zu steife Flaeche nicht.
    """
    out: dict[int, list] = {}
    ohne: dict[str, int] = {}
    mit_oeffnung = 0
    ohne_rand = 0
    props: dict[tuple, str] = {}
    openings = _openings(db)
    for h, impl in db.impls("Surface"):
        sid = h["id"]
        d = _thickness_of(db, impl)
        if d["t"] <= 0:
            ohne[d["text"]] = ohne.get(d["text"], 0) + 1
            continue
        ring = surf_nodes.get(sid)
        if not ring or len(ring) < 3:
            ohne_rand += 1
            continue
        if openings.get(sid):
            mit_oeffnung += 1
            C.warn(log, f"Flaeche {h.get('userID') or sid} hat "
                        f"{openings[sid]} Oeffnung(en) - nicht vernetzt, weil das "
                        "Randpolygon die Oeffnung schliessen wuerde.")
            continue
        mname = (_material(db, d["material_id"], m, matcache, log)
                 if d["material_id"] else C.ensure_material(m, log=log))
        key = (round(d["t"], 9), mname)
        pname = props.get(key)
        if pname is None:
            pname = C.unique_name(m.shells, f"d{d[chr(39)+chr(116)+chr(39)] * 1e3:g}")
            m.add_shell_prop(ShellProp(pname, d["t"]))
            props[key] = pname
        els = C.polygon_to_shells(m, ring, mname, pname, log=log,
                                  what=f"Flaeche {h.get('userID') or sid}")
        if els:
            out[sid] = els
        if d["variabel"]:
            C.warn(log, f"Flaeche {h.get('userID') or sid}: veraenderliche Dicke - "
                        f"mit dem Mittelwert {d['t'] * 1e3:.1f} mm gerechnet.")
        if impl.get("isDeactivatedForCalculation"):
            C.say(log, f"  Flaeche {h.get('userID') or sid} ist in RFEM deaktiviert - "
                       "dennoch uebernommen.")
    n_el = sum(len(v) for v in out.values())
    if out:
        C.say(log, f"{len(out)} Flaechen als {n_el} Schalenelemente uebernommen "
                   f"({len(props)} Dicken)")
    if ohne:
        C.say(log, "Flaechen ohne eigene Steifigkeit (keine Elemente): "
                   + ", ".join(f"{n}x {k}" for k, n in sorted(ohne.items())))
    if mit_oeffnung:
        C.say(log, f"  {mit_oeffnung} Flaechen mit Oeffnung nicht vernetzt")
    if ohne_rand:
        C.say(log, f"  {ohne_rand} Flaechen ohne aufloesbaren Rand")
    return out


# --------------------------------------------------------------------------
# Volumen als Volumenelemente
# --------------------------------------------------------------------------
def _hex_order(faces: list[list[int]]) -> list[int] | None:
    """
    Knotenreihenfolge eines Hexaeders aus seinen sechs Viereckflaechen.

    Gesucht sind Boden und Deckel (die beiden Flaechen ohne gemeinsamen
    Knoten); die vier Seitenflaechen ordnen dann jedem Bodenknoten seinen
    Deckelknoten zu.  ``None``, wenn die Topologie das nicht hergibt.
    """
    quads = [f for f in faces if len(set(f)) == 4]
    if len(quads) != 6:
        return None
    for i, a in enumerate(quads):
        sa = set(a)
        gegen = [b for b in quads if not (sa & set(b))]
        if len(gegen) != 1:
            continue
        top = gegen[0]
        paar: dict[int, int] = {}
        for f in quads:
            sf = set(f)
            if sf == sa or sf == set(top):
                continue
            unten = [n for n in f if n in sa]
            oben = [n for n in f if n in set(top)]
            if len(unten) != 2 or len(oben) != 2:
                return None
            # In der Seitenflaeche folgen die Knoten dem Umlauf: die beiden
            # unteren liegen benachbart, ebenso die beiden oberen.
            for u in unten:
                iu = f.index(u)
                for o in (f[(iu - 1) % 4], f[(iu + 1) % 4]):
                    if o in oben:
                        paar[u] = o
                        break
        if len(paar) == 4 and all(n in paar for n in a):
            return list(a) + [paar[n] for n in a]
    return None


def _solids(db: Db, m: Model, surf_nodes: dict, log: list,
            matcache: dict) -> int:
    """
    Volumenkoerper aus ihren Randflaechen in Volumenelemente umsetzen.

    Ohne 3D-Vernetzer geht das nur fuer die beiden einfachen Topologien:

        6 Viereckflaechen, 8 Eckknoten   -> hex8
        4 Dreieckflaechen, 4 Eckknoten   -> tet4

    Alles andere (Koerper mit Bohrungen, Freiformflaechen, viele Randflaechen)
    braucht einen Vernetzer und wird mit Randflaechenzahl und Material
    berichtet, aber nicht uebernommen - lieber eine sichtbare Luecke als ein
    stillschweigend falscher Koerper.
    """
    n_hex = n_tet = 0
    offen: dict[int, int] = {}
    for h, impl in db.impls("Solid"):
        tbl = h.get("impl_table") or "SolidImplStandard"
        sids = db.container(tbl + "_boundarySurfaces").get(impl["id"], [])
        faces = [surf_nodes[s] for s in sids if s in surf_nodes]
        knoten = sorted({n for f in faces for n in f})
        mname = (_material(db, impl.get("material_id"), m, matcache, log)
                 if impl.get("material_id") else C.ensure_material(m, log=log))
        if len(faces) == 6 and len(knoten) == 8:
            order = _hex_order(faces)
            if order:
                m.add_element("hex8", order, mname)
                n_hex += 1
                continue
        if len(faces) == 4 and len(knoten) == 4:
            X = m.nodes[knoten]
            v = np.dot(np.cross(X[1] - X[0], X[2] - X[0]), X[3] - X[0])
            nodes = knoten if v > 0 else [knoten[0], knoten[2], knoten[1], knoten[3]]
            m.add_element("tet4", nodes, mname)
            n_tet += 1
            continue
        offen[len(sids)] = offen.get(len(sids), 0) + 1
    if n_hex or n_tet:
        C.say(log, f"{n_hex + n_tet} Volumenkoerper uebernommen "
                   f"({n_hex} Hexaeder, {n_tet} Tetraeder)")
    if offen:
        gesamt = sum(offen.values())
        C.say(log, f"{gesamt} Volumenkoerper nicht uebernommen (Randflaechenzahl "
                   + ", ".join(f"{k}: {v}x" for k, v in sorted(offen.items()))
                   + ") - dafuer waere ein 3D-Vernetzer noetig.")
    return n_hex + n_tet


# --------------------------------------------------------------------------
# Uebersicht ohne Modellaufbau
# --------------------------------------------------------------------------
COUNT_TABLES = [
    ("Knoten", "Node"), ("Linien", "Line"), ("Staebe", "Member"),
    ("Flaechen", "Surface"), ("Volumen", "Solid"), ("Querschnitte", "Section"),
    ("Materialien", "Material"), ("Knotenlager", "NodalSupport"),
    ("Linienlager", "LineSupport"), ("Flaechenlager", "SurfaceSupport"),
    ("Stabgelenke", "MemberHinge"), ("Liniengelenke", "LineHinge"),
    ("Lastfaelle", "LoadCase"), ("Lastkombinationen", "LoadCombination"),
    ("Ergebniskombinationen", "ResultCombination"),
]


def summary(path: str) -> dict:
    """Inhaltsverzeichnis einer .rf6-Datei, ohne das Modell aufzubauen."""
    db_path = extract_db(path)
    tmp_dir = os.path.dirname(db_path) if db_path != path else None
    con = connect(db_path)
    try:
        db = Db(con)
        out = {"format": format_info(path), "schema": "RFEM 6" if is_rfem6(db) else "unbekannt",
               "tabellen": len(db.tables)}
        counts = {}
        for label, table in COUNT_TABLES:
            n = db.count(table)
            if n:
                counts[label] = n
        out["objekte"] = counts
        return out
    finally:
        con.close()
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def report(path: str) -> str:
    """Uebersicht als Text."""
    s = summary(path)
    fmt = s.get("format") or {}
    head = " ".join(f"{k} {v}" for k, v in fmt.items() if k in ("programm", "version"))
    lines = [f"{os.path.basename(path)}: {head or 'RFEM-Projektdatei'} "
             f"({s['schema']}-Schema, {s['tabellen']} Tabellen)"]
    for k, v in s["objekte"].items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def keep_structure(m: Model, log: list = None) -> int:
    """Nur die Knoten behalten, an denen Elemente haengen. Rueckgabe: entfernte Knoten.

    Eine RFEM-Datei enthaelt neben dem Stabtragwerk die Geometrie der Flaechen
    und Volumen. Ohne Netz stehen deren Knoten frei im Raum; die
    Steifigkeitsmatrix waere singulaer. Diese Funktion entfernt sie und
    nummeriert Elemente, Lager, Linien- und Flaechenlager sowie Linien um.
    """
    keep = sorted({int(n) for e in m.elements for n in e.nodes})
    if not keep or len(keep) == m.nn:
        return 0
    old = m.nn
    remap = {o: i for i, o in enumerate(keep)}
    m.nodes = m.nodes[keep]
    for e in m.elements:
        e.nodes = [remap[int(n)] for n in e.nodes]
    m.supports = [s for s in m.supports if s.node in remap]
    for s in m.supports:
        s.node = remap[s.node]
    for coll in (m.line_supports, m.surface_supports):
        for s in coll:
            s.nodes = [remap[n] for n in s.nodes if n in remap]
        coll[:] = [s for s in coll if s.nodes]
    for ss in m.surface_supports:
        if ss.areas and len(ss.areas) != len(ss.nodes):
            ss.areas = []
        ss.elements = []
    for name in list(m.lines):
        ln = m.lines[name]
        if all(n in remap for n in ln.nodes):
            ln.nodes = [remap[n] for n in ln.nodes]
        else:
            del m.lines[name]
    for nl in m.nodal_loads:
        nl.node = remap.get(nl.node, nl.node)
    C.say(log, f"Nur Stabtragwerk behalten: {old - m.nn} freie Knoten entfernt, "
               f"{m.nn} Knoten verbleiben")
    return old - m.nn
