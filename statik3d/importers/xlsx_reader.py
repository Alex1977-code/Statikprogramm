"""
Minimaler Excel-Leser (xlsx) und CSV-Tabellenleser - nur Standardbibliothek.

    sheets = read_xlsx("datei.xlsx")      # {Blattname: [[Zelle, ...], ...]}
    rows   = read_csv_table("datei.csv")  # [[Zelle, ...], ...]
    write_xlsx("out.xlsx", {"Blatt": [["a", 1.0], ["b", 2.5]]})

Zellen sind str, float, bool oder None. Unterstuetzt werden gemeinsame
Zeichenketten (sharedStrings), Inline-Zeichenketten, Zahlen, Wahrheitswerte,
Formeln (zwischengespeicherter Wert) und Fehlerzellen (-> None).
"""
from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

_CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------
def _local(tag: str) -> str:
    """XML-Tag ohne Namensraum."""
    return tag.rsplit("}", 1)[-1]


def _attr(elem, name: str, default=None):
    """Attribut unabhaengig vom Namensraum lesen (z.B. r:id)."""
    if name in elem.attrib:
        return elem.attrib[name]
    for k, v in elem.attrib.items():
        if k.rsplit("}", 1)[-1] == name:
            return v
    return default


def column_index(letters: str) -> int:
    """'A' -> 0, 'Z' -> 25, 'AA' -> 26."""
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def column_letters(index: int) -> str:
    """0 -> 'A', 26 -> 'AA'."""
    s = ""
    index += 1
    while index > 0:
        index, r = divmod(index - 1, 26)
        s = chr(65 + r) + s
    return s


def _text_of(elem) -> str:
    """Gesamten Text eines <si>/<is>-Elements (auch Rich-Text-Runs) einsammeln."""
    parts = []
    for node in elem.iter():
        if _local(node.tag) == "t" and node.text:
            parts.append(node.text)
    return "".join(parts)


# --------------------------------------------------------------------------
# xlsx lesen
# --------------------------------------------------------------------------
def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    for name in ("xl/sharedStrings.xml", "xl/SharedStrings.xml"):
        if name in zf.namelist():
            root = ET.fromstring(zf.read(name))
            return [_text_of(si) for si in root if _local(si.tag) == "si"]
    return []


def _sheet_targets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """[(Blattname, Pfad im Archiv), ...] in Arbeitsmappenreihenfolge."""
    names = set(zf.namelist())
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = {}
    if "xl/_rels/workbook.xml.rels" in names:
        rr = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in rr:
            rid = rel.attrib.get("Id")
            target = rel.attrib.get("Target", "")
            if rid and target:
                rels[rid] = target
    out = []
    for node in wb.iter():
        if _local(node.tag) != "sheet":
            continue
        title = node.attrib.get("name", f"Sheet{len(out) + 1}")
        rid = _attr(node, "id")
        target = rels.get(rid, "")
        if not target:
            target = f"worksheets/sheet{len(out) + 1}.xml"
        if target.startswith("/"):
            path = target.lstrip("/")
        elif target.startswith("xl/"):
            path = target
        else:
            path = "xl/" + target
        if path in names:
            out.append((title, path))
    return out


def _cell_value(c, shared: list[str]):
    t = c.attrib.get("t", "n")
    v_text = None
    inline = None
    for child in c:
        tag = _local(child.tag)
        if tag == "v":
            v_text = child.text
        elif tag == "is":
            inline = _text_of(child)
    if t == "inlineStr":
        return inline if inline is not None else ""
    if t == "s":
        if v_text is None:
            return None
        try:
            return shared[int(v_text)]
        except (ValueError, IndexError):
            return None
    if t == "b":
        return v_text not in (None, "0", "false", "FALSE")
    if t == "e":                     # Fehlerzelle (#N/A ...)
        return None
    if t in ("str", "d"):            # Formelergebnis als Text / Datum (ISO-Text)
        return v_text if v_text is not None else ""
    if v_text is None:
        return None
    try:
        return float(v_text)
    except ValueError:
        return v_text


def _read_sheet(data: bytes, shared: list[str]) -> list[list]:
    root = ET.fromstring(data)
    rows: dict[int, dict[int, object]] = {}
    row_counter = 0
    for row in root.iter():
        if _local(row.tag) != "row":
            continue
        row_counter += 1
        try:
            r = int(row.attrib.get("r", row_counter))
        except ValueError:
            r = row_counter
        col_counter = -1
        cells = rows.setdefault(r, {})
        for c in row:
            if _local(c.tag) != "c":
                continue
            ref = c.attrib.get("r")
            m = _CELL_REF.match(ref) if ref else None
            if m:
                col = column_index(m.group(1))
            else:
                col = col_counter + 1
            col_counter = col
            val = _cell_value(c, shared)
            if val is not None:
                cells[col] = val
    if not rows:
        return []
    nrows = max(rows)
    table: list[list] = []
    for r in range(1, nrows + 1):
        cells = rows.get(r, {})
        if cells:
            width = max(cells) + 1
            table.append([cells.get(k) for k in range(width)])
        else:
            table.append([])
    return table


def read_xlsx(path: str) -> dict[str, list[list]]:
    """Alle Blaetter einer xlsx-Datei lesen: {Blattname: Zeilen}.

    Jede Zeile ist eine Liste von Zellen (str / float / bool / None); leere
    Zeilen sind leere Listen, so dass der Zeilenindex der Excel-Zeile - 1 entspricht.
    """
    with zipfile.ZipFile(path) as zf:
        shared = _read_shared_strings(zf)
        out = {}
        for title, target in _sheet_targets(zf):
            try:
                out[title] = _read_sheet(zf.read(target), shared)
            except ET.ParseError as ex:
                raise ValueError(f"Blatt '{title}' in {os.path.basename(path)} "
                                 f"ist nicht lesbar: {ex}") from ex
    return out


# --------------------------------------------------------------------------
# xlsx schreiben (fuer Tests / Round-Trip, bewusst minimal)
# --------------------------------------------------------------------------
def _sheet_xml(rows: list[list]) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           "<sheetData>"]
    for i, row in enumerate(rows, 1):
        out.append(f'<row r="{i}">')
        for j, val in enumerate(row):
            if val is None or val == "":
                continue
            ref = f"{column_letters(j)}{i}"
            if isinstance(val, bool):
                out.append(f'<c r="{ref}" t="b"><v>{1 if val else 0}</v></c>')
            elif isinstance(val, (int, float)):
                out.append(f'<c r="{ref}"><v>{repr(float(val))}</v></c>')
            else:
                out.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">'
                           f"{escape(str(val))}</t></is></c>")
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def write_xlsx(path: str, sheets: dict[str, list[list]]) -> None:
    """Einfache xlsx-Datei schreiben (Inline-Zeichenketten, Zahlen, Wahrheitswerte)."""
    names = list(sheets)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    for k in range(len(names)):
        ct.append(f'<Override PartName="/xl/worksheets/sheet{k + 1}.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    ct.append("</Types>")
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                 "</Relationships>")
    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
    wb_rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for k, name in enumerate(names, 1):
        wb.append(f'<sheet name="{escape(name, {chr(34): "&quot;"})}" sheetId="{k}" r:id="rId{k}"/>')
        wb_rels.append(f'<Relationship Id="rId{k}" '
                       'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                       f'Target="worksheets/sheet{k}.xml"/>')
    wb.append("</sheets></workbook>")
    wb_rels.append(f'<Relationship Id="rId{len(names) + 1}" '
                   'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                   'Target="styles.xml"/>')
    wb_rels.append("</Relationships>")
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
              "</styleSheet>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "".join(ct))
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", "".join(wb))
        zf.writestr("xl/_rels/workbook.xml.rels", "".join(wb_rels))
        zf.writestr("xl/styles.xml", styles)
        for k, name in enumerate(names, 1):
            zf.writestr(f"xl/worksheets/sheet{k}.xml", _sheet_xml(sheets[name]))


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------
_DE_NUMBER = re.compile(r"^[+-]?(\d{1,3}(\.\d{3})+|\d+)?(,\d+)?$")
_EN_NUMBER = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d+)?(\.\d+)?([eE][+-]?\d+)?$")


def _read_text(path: str) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def sniff_delimiter(text: str) -> str:
    """Trennzeichen ';', ',' oder Tabulator anhand der ersten Zeilen bestimmen."""
    lines = [ln for ln in text.splitlines()[:30] if ln.strip()]
    best, best_score = ";", -1.0
    for d in (";", "\t", ","):
        counts = [ln.count(d) for ln in lines]
        if not counts or max(counts) == 0:
            continue
        # Bevorzugt Trennzeichen mit gleichmaessiger Anzahl je Zeile
        mean = sum(counts) / len(counts)
        var = sum((c - mean) ** 2 for c in counts) / len(counts)
        score = mean / (1.0 + var)
        if d == ";" and mean > 0:
            score *= 1.5          # deutsches CSV
        if score > best_score:
            best, best_score = d, score
    return best


def convert_cell(text: str, decimal_comma: bool = None):
    """Textzelle -> float, wenn sie eine Zahl darstellt, sonst str; '' -> None."""
    s = text.strip()
    if s == "":
        return None
    if decimal_comma is None:
        decimal_comma = "," in s and "." not in s
    if decimal_comma and _DE_NUMBER.match(s) and any(ch.isdigit() for ch in s):
        try:
            return float(s.replace(".", "").replace(",", "."))
        except ValueError:
            return s
    if _EN_NUMBER.match(s) and any(ch.isdigit() for ch in s):
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return s
    try:
        return float(s)
    except ValueError:
        return s


def read_csv_table(path: str, delimiter: str = None) -> list[list]:
    """CSV-Datei als Tabelle lesen (Trennzeichen automatisch, deutsches Dezimalkomma)."""
    text = _read_text(path)
    if delimiter is None:
        delimiter = sniff_delimiter(text)
    decimal_comma = delimiter != ","
    rows = []
    for rec in csv.reader(io.StringIO(text), delimiter=delimiter, quotechar='"'):
        row = [convert_cell(c, decimal_comma) for c in rec]
        while row and row[-1] is None:
            row.pop()
        rows.append(row)
    return rows


def read_table_file(path: str) -> dict[str, list[list]]:
    """xlsx oder csv -> {Blattname: Zeilen} (CSV: Dateiname ohne Endung)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm", ".xltx"):
        return read_xlsx(path)
    if ext in (".csv", ".txt", ".tsv"):
        return {os.path.splitext(os.path.basename(path))[0]: read_csv_table(path)}
    raise ValueError(f"Tabellendatei mit Endung '{ext}' wird nicht unterstuetzt")
