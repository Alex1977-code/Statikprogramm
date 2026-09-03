"""
Native Dlubal-Projektdateien: RFEM 5/6 (.rf5, .rf6) und RSTAB (.rs5, .rs6, .rs8, .rs9).

Dlubal veroeffentlicht den Aufbau dieser Dateien nicht. Statt zu raten, wird die
Datei zuerst untersucht (probe): Welcher Behaelter liegt vor? Je nach Befund

    SQLite    -> Tabellen werden gelesen und ueber Namensmuster zugeordnet
    ZIP       -> enthaltene XML-, JSON-, CSV- oder SQLite-Dateien werden gelesen
    OLE2      -> Datenstroeme werden aufgelistet, lesbare Inhalte ausgewertet
    XML/JSON  -> direkt gelesen
    unbekannt -> genauer Befund (Kennung, Groesse, gefundene Textanteile) und der
                 Exportweg; es wird nichts erraten.

    from statik3d.importers.rfem_native import probe, import_rfem_native
    print(probe("modell.rf6")["report"])
    m = import_rfem_native("modell.rf6", log=msgs)

Zuordnung der Tabellen/Spalten ueber Namensmuster (deutsch und englisch), damit
unterschiedliche Versionen erkannt werden. Erkannt werden Knoten, Linien, Staebe,
Materialien, Querschnitte, Knoten-, Linien- und Flaechenlager mit
Nichtlinearitaeten (Ausfall bei Zug/Druck, Schlupf, Reibung) sowie Gelenke.
"""
from __future__ import annotations

import io
import json
import os
import re
import sqlite3
import struct
import tempfile
import zipfile

from ..model import Model, DofBehaviour, NDOF
from . import _common as C

MAGICS = [
    (b"SQLite format 3\x00", "sqlite", "SQLite-Datenbank"),
    (b"PK\x03\x04", "zip", "ZIP-Behaelter"),
    (b"PK\x05\x06", "zip", "ZIP-Behaelter (leer)"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole", "OLE2-Verbunddatei (Microsoft)"),
    (b"\x1f\x8b", "gzip", "gzip-Strom"),
    (b"<?xml", "xml", "XML"),
    (b"{", "json", "JSON"),
]
NATIVE_EXT = (".rf3", ".rf4", ".rf5", ".rf6", ".rfem",
              ".rs5", ".rs6", ".rs7", ".rs8", ".rs9", ".rstab")
EXPORT_HINT = (
    "Exportweg aus RFEM/RSTAB: Datei -> Exportieren -> SAF (.xlsx), "
    "IFC (Statikmodell / Structural Analysis View) oder Tabellen nach Excel/CSV. "
    "Diese Formate liest Statik3D vollstaendig ein."
)

# --------------------------------------------------------------------------
# Untersuchung des Behaelters
# --------------------------------------------------------------------------
def _printable_ratio(b: bytes) -> float:
    if not b:
        return 0.0
    ok = sum(1 for x in b if 32 <= x < 127 or x in (9, 10, 13))
    return ok / len(b)


def _strings(data: bytes, minlen: int = 6, limit: int = 40) -> list[str]:
    """Lesbare Zeichenketten aus einem Binaerstrom (ASCII und UTF-16LE)."""
    out = []
    for pat in (rb"[ -~]{%d,}" % minlen, rb"(?:[ -~]\x00){%d,}" % minlen):
        for m in re.finditer(pat, data):
            s = m.group(0)
            txt = s.decode("utf-16-le", "ignore") if b"\x00" in s else s.decode("ascii", "ignore")
            txt = txt.strip()
            if len(txt) >= minlen:
                out.append(txt)
            if len(out) >= limit:
                return out
    return out


def probe(path: str, deep: bool = True) -> dict:
    """Behaelter einer Datei bestimmen. Rueckgabe: dict mit kind, name, size,
    entries (bei ZIP/OLE/SQLite) und 'report' (deutscher Befund)."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(4096)
    kind, desc = "unknown", "unbekanntes Binaerformat"
    for magic, k, d in MAGICS:
        if head.startswith(magic):
            kind, desc = k, d
            break
    info = {"path": path, "size": size, "kind": kind, "desc": desc,
            "entries": [], "tables": [], "hits": [], "magic": head[:16].hex(" ")}
    try:
        if kind == "zip":
            with zipfile.ZipFile(path) as z:
                info["entries"] = [i.filename for i in z.infolist()][:200]
        elif kind == "sqlite":
            info["tables"] = _sqlite_tables(path)
        elif kind == "ole":
            info["entries"] = ole_streams(path)[:200]
        elif kind == "unknown" and deep:
            # eingebettete Behaelter suchen (manche Formate haengen sie an)
            with open(path, "rb") as f:
                data = f.read(min(size, 8 << 20))
            for magic, k, d in MAGICS[:3]:
                i = data.find(magic, 1)
                if i > 0:
                    info["hits"].append({"kind": k, "offset": i, "desc": d})
            info["strings"] = _strings(data)
            info["printable"] = round(_printable_ratio(data[:65536]), 3)
    except Exception as ex:      # noqa: BLE001 - Befund statt Absturz
        info["error"] = f"{type(ex).__name__}: {ex}"
    info["report"] = _report(info)
    return info


def _report(info: dict) -> str:
    mb = info["size"] / 1e6
    lines = [f"{os.path.basename(info['path'])}: {mb:.2f} MB, Kennung {info['magic']}",
             f"Behaelter: {info['desc']}"]
    if info.get("error"):
        lines.append(f"Fehler beim Oeffnen: {info['error']}")
    if info["tables"]:
        lines.append(f"SQLite-Tabellen ({len(info['tables'])}): "
                     + ", ".join(info["tables"][:25])
                     + (" ..." if len(info["tables"]) > 25 else ""))
    if info["entries"]:
        lines.append(f"Enthaltene Dateien ({len(info['entries'])}): "
                     + ", ".join(info["entries"][:20])
                     + (" ..." if len(info["entries"]) > 20 else ""))
    if info["hits"]:
        lines.append("Eingebettete Behaelter: "
                     + ", ".join(f"{h['desc']} ab Byte {h['offset']}" for h in info["hits"]))
    if info.get("strings"):
        lines.append("Lesbare Zeichenketten (Auszug): "
                     + " | ".join(info["strings"][:8]))
    return "\n".join(lines)


def _sqlite_tables(path: str) -> list[str]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cur = con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
        return [r[0] for r in cur.fetchall()]
    finally:
        con.close()


# --------------------------------------------------------------------------
# OLE2 (Verbunddatei): Datenstroeme auflisten
# --------------------------------------------------------------------------
def ole_streams(path: str) -> list[str]:
    """Namen der Datenstroeme einer OLE2-Verbunddatei (minimaler Leser)."""
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return []
    sector_size = 1 << struct.unpack_from("<H", data, 30)[0]
    dir_start = struct.unpack_from("<I", data, 48)[0]
    fat_sectors = struct.unpack_from("<I", data, 44)[0]
    difat = [struct.unpack_from("<I", data, 76 + 4 * i)[0] for i in range(109)]
    fat = []
    for s in difat[:max(fat_sectors, 0)]:
        if s >= 0xFFFFFFFA:
            break
        off = 512 + s * sector_size
        fat.extend(struct.unpack_from("<%dI" % (sector_size // 4), data, off))
    names, sec, guard = [], dir_start, 0
    while sec < 0xFFFFFFFA and guard < 4096:
        off = 512 + sec * sector_size
        if off + sector_size > len(data):
            break
        for k in range(sector_size // 128):
            e = off + 128 * k
            nlen = struct.unpack_from("<H", data, e + 64)[0]
            if 2 < nlen <= 64:
                nm = data[e:e + nlen - 2].decode("utf-16-le", "ignore").strip("\x00")
                if nm and nm not in names:
                    names.append(nm)
        sec = fat[sec] if sec < len(fat) else 0xFFFFFFFE
        guard += 1
    return names


# --------------------------------------------------------------------------
# Zuordnung von Tabellen und Spalten
# --------------------------------------------------------------------------
TABLE_PATTERNS = [
    ("nodes", r"^(node|knoten|point|punkt)s?$|nodes$|knoten$"),
    ("lines", r"^(line|linie|linien|edge)s?$|lines$"),
    ("members", r"^(member|stab|staebe|beam|bar)s?$|members$|staebe$"),
    ("materials", r"material"),
    ("sections", r"crosssections?$|querschnitte?$|profiles?$|sections?$"),
    ("line_supports", r"linesupports?$|linienlager$"),
    ("surface_supports", r"surfacesupports?$|flaechenlager$|bedding$|bettung$"),
    ("supports", r"nodalsupports?$|knotenlager$|nodesupports?$|supports?$"),
    ("hinges", r"hinges?$|gelenke?$|releases?$"),
    ("surfaces", r"surfaces?$|flaechen?$"),
]
COLUMN_PATTERNS = {
    "no": r"^(no|nr|id|number|nummer|index|nodeno|lineno|memberno)$",
    "x": r"^(x|x1|coordinatex|koordinatex|globalx|xm)$",
    "y": r"^(y|y1|coordinatey|koordinatey|globaly|ym)$",
    "z": r"^(z|z1|coordinatez|koordinatez|globalz|zm)$",
    "node_a": r"^(nodea|startnode|knotena|anfangsknoten|n1|from|node1)$",
    "node_b": r"^(nodeb|endnode|knotenb|endknoten|n2|to|node2)$",
    "nodes": r"^(nodelist|nodes|knoten|knotenliste|definitionnodes|nodesno)$",
    "line": r"^(line|linie|lineno|liniennr|lines|linien)$",
    "material": r"^(material|materialno|werkstoff|materialnr)$",
    "section": r"^(section|crosssection|querschnitt|sectionno|profil|crosssectionno)$",
    "name": r"^(name|bezeichnung|designation|description|kommentar|comment|label)$",
    "rotation": r"^(rotation|verdrehung|roll|angle|winkel|rotationangle)$",
}
DOF_COLUMNS = {
    0: r"^(ux|cux|translationx|verschiebungx|springux)$",
    1: r"^(uy|cuy|translationy|verschiebungy|springuy)$",
    2: r"^(uz|cuz|translationz|verschiebungz|springuz)$",
    3: r"^(phix|rx|cphix|rotationx|verdrehungx|springphix)$",
    4: r"^(phiy|ry|cphiy|rotationy|verdrehungy|springphiy)$",
    5: r"^(phiz|rz|cphiz|rotationz|verdrehungz|springphiz)$",
}
NONLIN_PATTERNS = {
    "zug": r"ausfall.*zug|failure.*tension|fixed.*if.*negative|tension.*fail|nur.*druck|compression[_ ]?only",
    "druck": r"ausfall.*druck|failure.*compress|nur.*zug|tension[_ ]?only",
}


def _key(name: str) -> str:
    """Tabellen-/Spaltenname auf Kleinbuchstaben ohne Trennzeichen bringen."""
    return C.norm_key(name).replace(" ", "")


def classify_table(name: str) -> str:
    key = _key(name)
    for kind, pat in TABLE_PATTERNS:
        if re.search(pat, key):
            return kind
    return ""


def classify_column(name: str) -> str:
    key = _key(name)
    for kind, pat in COLUMN_PATTERNS.items():
        if re.match(pat, key):
            return kind
    for dof, pat in DOF_COLUMNS.items():
        if re.match(pat, key):
            return f"dof{dof}"
    return ""


def behaviour_from_text(text, stiffness=None) -> DofBehaviour:
    """Lagerangabe einer Zelle in ein DofBehaviour uebersetzen.
    Erkannt: 'starr'/'rigid'/'fixed', 'frei'/'free', Zahlen (Federsteifigkeit),
    Zusaetze fuer Ausfall bei Zug/Druck, Schlupf und Reibbeiwert."""
    s = C.clean_text(text)
    low = s.lower()
    b = DofBehaviour("free")
    if not s:
        return b
    if re.search(r"starr|rigid|fixed|fest|gehalten|^(yes|ja|x|1)$", low) and \
            not re.search(r"frei|free", low):
        b.typ = "rigid"
    num = stiffness
    if num is None and b.typ != "rigid":
        head = re.split(r"schlupf|slip|reibung|friction|\bmu\b|µ|grenz|limit", low)[0]
        mm = re.search(r"([+-]?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?)", head)
        if mm and not re.match(r"^(yes|ja|x|1|0)$", low):
            num = C.parse_number(mm.group(1))
    if num is not None and num > 0:
        b.typ, b.stiffness = "spring", float(num)
    for mode, pat in NONLIN_PATTERNS.items():
        if re.search(pat, low):
            b.failure = mode
    m = re.search(r"(schlupf|slip)\D{0,4}([\d.,]*\d)", low)
    if m:
        b.slip = float(C.parse_number(m.group(2)) or 0.0)
    m = re.search(r"(reibung|friction|mu|µ)\D{0,4}([\d.,]*\d)", low)
    if m:
        b.mu = float(C.parse_number(m.group(2)) or 0.0)
    if re.search(r"frei|free|none|-$", low) and b.typ == "free":
        b.typ = "free"
    return b


# --------------------------------------------------------------------------
# SQLite / ZIP lesen
# --------------------------------------------------------------------------
def _rows(con, table: str, limit: int = 200000) -> list[dict]:
    cur = con.execute(f'SELECT * FROM "{table}" LIMIT {limit}')
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def read_sqlite(path: str) -> dict:
    """{Tabellenart: Zeilen} aus einer SQLite-Datei."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    out: dict[str, list] = {}
    try:
        for t in _sqlite_tables(path):
            kind = classify_table(t)
            if not kind:
                continue
            try:
                rows = _rows(con, t)
            except sqlite3.Error:
                continue
            if rows:
                out.setdefault(kind, []).extend(rows)
    finally:
        con.close()
    return out


def read_zip(path: str, log: list = None) -> dict:
    """Tabellen aus einem ZIP-Behaelter (XML, JSON, CSV oder eingebettetes SQLite)."""
    out: dict[str, list] = {}
    with zipfile.ZipFile(path) as z:
        for item in z.infolist():
            nm = item.filename
            ext = os.path.splitext(nm)[1].lower()
            kind = classify_table(os.path.splitext(os.path.basename(nm))[0])
            data = z.read(nm)
            if data[:16] == b"SQLite format 3\x00":
                with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
                    tf.write(data)
                    tmp = tf.name
                try:
                    for k, rows in read_sqlite(tmp).items():
                        out.setdefault(k, []).extend(rows)
                finally:
                    os.unlink(tmp)
                C.say(log, f"  {nm}: eingebettete SQLite-Datenbank gelesen")
            elif ext == ".json":
                try:
                    obj = json.loads(data.decode("utf-8", "ignore"))
                except ValueError:
                    continue
                for k, v in (obj.items() if isinstance(obj, dict) else []):
                    kk = classify_table(k)
                    if kk and isinstance(v, list) and v and isinstance(v[0], dict):
                        out.setdefault(kk, []).extend(v)
            elif ext in (".csv", ".txt") and kind:
                rows = _csv_rows(data.decode("utf-8", "ignore"))
                if rows:
                    out.setdefault(kind, []).extend(rows)
            elif ext == ".xml":
                for k, rows in _xml_rows(data).items():
                    out.setdefault(k, []).extend(rows)
    return out


def _csv_rows(text: str) -> list[dict]:
    import csv as _csv
    sample = text[:2000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    rd = _csv.reader(io.StringIO(text), delimiter=delim)
    rows = [r for r in rd if any(str(c).strip() for c in r)]
    if len(rows) < 2:
        return []
    head = [str(c).strip() for c in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:]]


def _xml_rows(data: bytes) -> dict:
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return {}
    out: dict[str, list] = {}
    for parent in root.iter():
        kind = classify_table(re.sub(r"\{.*\}", "", parent.tag))
        if not kind:
            continue
        rows = []
        for child in parent:
            row = dict(child.attrib)
            for sub in child:
                tag = re.sub(r"\{.*\}", "", sub.tag)
                if sub.text and sub.text.strip():
                    row[tag] = sub.text.strip()
            if row:
                rows.append(row)
        if rows:
            out.setdefault(kind, []).extend(rows)
    return out


# --------------------------------------------------------------------------
# Tabellen -> Modell
# --------------------------------------------------------------------------
def _col(row: dict, kind: str):
    for k, v in row.items():
        if classify_column(k) == kind:
            return v
    return None


def build_model(tables: dict, model: Model = None, log: list = None,
                unit_scale: float = 1.0) -> Model:
    """Erkannte Tabellen in ein Modell umsetzen."""
    m = model or Model("RFEM-Import")
    idx = C.NodeIndex(m)
    node_of: dict[str, int] = {}
    mat = C.ensure_material(m, log=log)
    sec_of: dict[str, str] = {}

    for row in tables.get("materials", []):
        nm = C.clean_text(_col(row, "name") or _col(row, "no"))
        if nm:
            C.ensure_material(m, nm, log=log)
    for row in tables.get("sections", []):
        nm = C.clean_text(_col(row, "name") or _col(row, "section") or _col(row, "no"))
        key = C.clean_text(_col(row, "no") or nm)
        if nm:
            s = C.ensure_section(m, nm, log=log)
            if s:
                sec_of[key] = s
    for row in tables.get("nodes", []):
        no = C.clean_text(_col(row, "no"))
        x, y, z = (C.parse_number(_col(row, k)) for k in ("x", "y", "z"))
        if None in (x, y, z):
            continue
        node_of[no] = idx.add(x * unit_scale, y * unit_scale, z * unit_scale)
    idx.flush()
    line_nodes: dict[str, list[int]] = {}
    for row in tables.get("lines", []):
        no = C.clean_text(_col(row, "no"))
        lst = C.clean_text(_col(row, "nodes"))
        ids = [node_of[k] for k in C.expand_ranges(C.split_list(lst)) if k in node_of] if lst else []
        if not ids:
            a, b = C.clean_text(_col(row, "node_a")), C.clean_text(_col(row, "node_b"))
            ids = [node_of[k] for k in (a, b) if k in node_of]
        if len(ids) >= 2:
            line_nodes[no] = ids
            m.add_line(f"L{no}", ids)
    n_beams = 0
    for row in tables.get("members", []):
        no = C.clean_text(_col(row, "no"))
        ln = C.clean_text(_col(row, "line"))
        ids = line_nodes.get(ln)
        if not ids:
            a, b = C.clean_text(_col(row, "node_a")), C.clean_text(_col(row, "node_b"))
            ids = [node_of[k] for k in (a, b) if k in node_of]
        if not ids or len(ids) < 2:
            continue
        sname = sec_of.get(C.clean_text(_col(row, "section"))) or \
            C.ensure_section(m, C.clean_text(_col(row, "section")), log=log)
        mname = C.clean_text(_col(row, "material")) or mat
        if mname not in m.materials:
            mname = mat
        roll = C.parse_number(_col(row, "rotation")) or 0.0
        for a, b in zip(ids[:-1], ids[1:]):
            m.add_element("beam", [a, b], mname, sname, roll=float(roll) * 3.141592653589793 / 180)
            n_beams += 1
    _supports_from(tables, m, node_of, line_nodes, log)
    C.say(log, f"Native Datei: {m.nn} Knoten, {n_beams} Stabelemente, "
                f"{len(m.lines)} Linien, {len(m.supports)} Knotenlager, "
                f"{len(m.line_supports)} Linienlager, {len(m.surface_supports)} Flaechenlager")
    return m


def normalise_friction(beh: dict) -> dict:
    """Reibung, die am Ausfall-FHG steht, auf die beiden Querrichtungen legen.

    In RFEM gehoert der Reibbeiwert zur Lagerflaeche: die Reibkraft wirkt quer
    zur Stuetzrichtung und ist auf mu * |Normalkraft| begrenzt. Steht mu am
    Freiheitsgrad mit dem Ausfall (z.B. uz), wird er auf die beiden anderen
    Verschiebungs-FHG uebertragen und dort auf den Ausfall-FHG bezogen.
    """
    for dof, b in list(beh.items()):
        if dof < 3 and b.mu > 0 and b.failure:
            for other in (0, 1, 2):
                if other == dof:
                    continue
                ob = beh.get(other)
                if ob is None:
                    ob = DofBehaviour("rigid")
                    beh[other] = ob
                if ob.mu <= 0:
                    ob.mu, ob.mu_ref = b.mu, dof
            b.mu, b.mu_ref = 0.0, None
        elif dof < 3 and b.mu > 0 and b.mu_ref is None:
            ref = next((d for d, x in beh.items() if d < 3 and d != dof and x.failure), None)
            if ref is not None:
                b.mu_ref = ref
    return beh


def _behaviours(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        col = classify_column(k)
        if col.startswith("dof"):
            b = behaviour_from_text(v)
            if b.acts or b.failure or b.slip or b.mu:
                out[int(col[3:])] = b
    return normalise_friction(out)


def _supports_from(tables: dict, m: Model, node_of: dict, line_nodes: dict, log: list):
    for row in tables.get("supports", []):
        lst = C.clean_text(_col(row, "nodes") or _col(row, "no"))
        ids = [node_of[k] for k in C.expand_ranges(C.split_list(lst)) if k in node_of]
        beh = _behaviours(row)
        if not ids or not beh:
            continue
        for n in ids:
            s = m.support(n, [], name=C.clean_text(_col(row, "name")))
            for dof, b in beh.items():
                s.behaviour[dof] = b
                if b.acts and dof not in s.dofs:
                    s.dofs.append(dof)
    for row in tables.get("line_supports", []):
        lst = C.clean_text(_col(row, "line") or _col(row, "nodes"))
        ids: list[int] = []
        for key in C.expand_ranges(C.split_list(lst)):
            ids.extend(line_nodes.get(key, []) or ([node_of[key]] if key in node_of else []))
        beh = _behaviours(row)
        if ids and beh:
            ls = m.add_line_support(sorted(dict.fromkeys(ids)),
                                    name=C.clean_text(_col(row, "name")) or "")
            ls.behaviour.update(beh)
    for row in tables.get("surface_supports", []):
        lst = C.clean_text(_col(row, "nodes"))
        ids = [node_of[k] for k in C.expand_ranges(C.split_list(lst)) if k in node_of]
        beh = _behaviours(row)
        if beh and (ids or _col(row, "no")):
            ss = m.add_surface_support([], name=C.clean_text(_col(row, "name")) or "",
                                       nodes=ids, areas=[0.0] * len(ids))
            ss.behaviour.update(beh)


# --------------------------------------------------------------------------
def import_rfem_native(path: str, model: Model = None, log: list = None,
                       unit_scale: float = 1.0, **_) -> Model:
    """RFEM/RSTAB-Projektdatei lesen, soweit der Behaelter zugaenglich ist."""
    info = probe(path)
    C.say(log, info["report"])
    tables = {}
    if info["kind"] == "sqlite":
        tables = read_sqlite(path)
    elif info["kind"] == "zip":
        tables = read_zip(path, log)
    elif info["kind"] in ("xml", "json"):
        with open(path, "rb") as f:
            data = f.read()
        tables = _xml_rows(data) if info["kind"] == "xml" else {}
        if info["kind"] == "json":
            try:
                obj = json.loads(data.decode("utf-8", "ignore"))
                for k, v in (obj.items() if isinstance(obj, dict) else []):
                    kk = classify_table(k)
                    if kk and isinstance(v, list):
                        tables.setdefault(kk, []).extend(v)
            except ValueError:
                pass
    if not tables:
        raise ImportError(
            f"{info['report']}\n\n"
            "Der Aufbau dieser Datei ist nicht lesbar - Dlubal veroeffentlicht ihn nicht, "
            "und es wird nichts geraten. " + EXPORT_HINT)
    m = build_model(tables, model, log, unit_scale)
    if m.nn == 0:
        raise ImportError(
            f"{info['report']}\n\nDer Behaelter wurde geoeffnet, enthielt aber keine "
            "erkennbaren Knoten. " + EXPORT_HINT)
    C.merge_duplicate_nodes(m)
    return m
