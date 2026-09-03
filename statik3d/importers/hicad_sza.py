"""
HiCAD-Archive: .SZA (Szene), .KRA (Konstruktion), .FGA (Figur), .FIG.

Der Behaelter traegt die Kennung ``!HFA##`` (HiCAD File Archive) und wurde an
echten Dateien aus HiCAD 2024 ausgelesen. Aufbau:

    Kopf      0x00  "!HFA##\\0\\0", danach Versionsfelder und der Erzeuger
              0x24  "ISD Software & Systeme GmbH - Dortmund" (UTF-16LE)
    Eintrag   ab 0x198, hintereinander bis zum Dateiende:
              [ 1024 Byte ]  Name (UTF-16LE, mit 0 aufgefuellt); der Name ist
                             der Pfad der Datei im HiCAD-Arbeitsverzeichnis
              [   72 Byte ]  Kopf: u32[1] = Beginn des naechsten Eintrags,
                             u32[13] = Packverfahren (3 = Zstandard),
                             u32[16] = gepackte, u32[17] = rohe Groesse,
                             dazu drei FILETIME-Zeitstempel
              [   n Byte  ]  Daten. Ueberschreitet ein Eintrag 1 MiB, folgen
                             weitere Bloecke, jeweils mit 8 Byte Vorspann
                             (gepackte und rohe Groesse), bis der Beginn des
                             naechsten Eintrags erreicht ist.

Inhalt eines .SZA (Beispiel):

    847293352.SZN            Szene (weiterer Behaelter "FILE-CONTAINER ISD 1.0")
    847293352.POM            Bauteilmodell ("ISD_POM_3.1")
    847293352.SZN.ATC/DBA2/DBA3/DVI   Attribute, Bemassung, Darstellung
    847293352.SZN.ELREF      Bauteilverweise (XML)
    847293352.SZN.ITM_DFN    Positionsnummern (XML)
    VIEWER.GFIG              Anzeigegeometrie ("HiGDI")
    PREVIEW.DIB              Vorschaubild (Windows-Bitmap)
    *.IPT                    Teiletabellen: die im Modell benutzten Profile
                             und Werkstoffe ("ISD Part Table File")

Gelesen werden Aufbau und alle Teile, die ein eigenes, offenes Format haben:
Teiletabellen (Profile, Werkstoffe), die XML-Teile und das Vorschaubild. Die
3D-Geometrie steht im SZN- und GFIG-Teil in einem eigenen Binaerformat, das
ISD nicht veroeffentlicht; sie wird nicht geraten. Fuer das Tragwerk ist der
Weg ueber SDNF, DSTV-NC, IFC oder STEP der richtige.

    from statik3d.importers.hicad_sza import archive_entries, extract, part_tables
    for e in archive_entries("halle.sza"):
        print(e["name"], e["size"], e["packed"])
"""
from __future__ import annotations

import os
import re
import struct

from . import _common as C

MAGIC = b"!HFA##"
FIRST_ENTRY = 0x198          # Beginn des ersten Eintrags hinter dem Archivkopf
NAME_BYTES = 1024            # feste Groesse des Namensfeldes (UTF-16LE)
HEADER_BYTES = 72            # Kopf hinter dem Namen
METHOD_ZSTD = 3

#: Bekannte Bestandteile eines HiCAD-Archivs
PART_KINDS = {
    ".SZN": "Szene (Geometrie, eigener Behaelter)",
    ".POM": "Bauteilmodell (ISD_POM)",
    ".ANS": "Ansichten",
    ".ATC": "Attribute",
    ".DBA2": "Bemassung (Fassung 2)",
    ".DBA3": "Bemassung (Fassung 3)",
    ".DVI": "Darstellung",
    ".ELREF": "Bauteilverweise (XML)",
    ".FEA": "Feature-Protokoll (XML)",
    ".ITM_DFN": "Positionsnummern (XML)",
    ".ITM_CTX": "Positionsnummern, Zusammenhang (XML)",
    ".ITM_ST": "Positionsnummern, Einstellungen (XML)",
    ".IOX": "Ein-/Ausgabe (XML)",
    ".FRD": "Freie Darstellung (XML)",
    ".EXP": "Explosionsdarstellung (XML)",
    ".SIM": "Simulation (XML)",
    ".WSD": "Arbeitsebenen",
    ".LFG": "Beschriftungen (XML)",
    ".MTD": "Metadaten",
    ".Units": "Einheiten (XML)",
    ".GFIG": "Anzeigegeometrie (HiGDI)",
    ".DIB": "Vorschaubild (Windows-Bitmap)",
    ".IPT": "Teiletabelle (Profile, Werkstoffe)",
    ".ABW": "Biegetabelle",
}


def is_hicad_archive(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def _decompress(blob: bytes, raw_size: int, method: int):
    """Einen Block entpacken. Ohne das Paket 'zstandard' bleibt er gepackt."""
    if method != METHOD_ZSTD:
        return blob, f"Packverfahren {method} unbekannt"
    try:
        import zstandard
    except ImportError:
        return None, ("Zum Entpacken wird das Paket 'zstandard' benoetigt "
                      "(pip install zstandard).")
    try:
        dec = zstandard.ZstdDecompressor()
        return dec.decompress(blob, max_output_size=max(raw_size, 1) * 8), ""
    except Exception as ex:            # noqa: BLE001 - defekter Block
        return None, f"Block nicht entpackbar: {ex}"


def archive_entries(path: str, data: bool = False, log: list = None) -> list[dict]:
    """Inhaltsverzeichnis des Archivs.

    data=True entpackt die Teile und legt sie unter "data" ab.
    Rueckgabe je Eintrag: name, kurz, art, packed, size, offset, blocks,
    fehler und (bei data=True) data.
    """
    with open(path, "rb") as f:
        d = f.read()
    if not d.startswith(MAGIC):
        raise ImportError(f"{os.path.basename(path)}: keine HiCAD-Archivdatei "
                          f"(Kennung {MAGIC.decode()} fehlt).")
    out: list[dict] = []
    pos = FIRST_ENTRY
    seen = set()
    while pos + NAME_BYTES + HEADER_BYTES <= len(d):
        name = d[pos:pos + NAME_BYTES].decode("utf-16-le", "ignore").split("\x00")[0]
        head = pos + NAME_BYTES
        fields = struct.unpack_from("<18I", d, head)
        nxt, method, packed, raw = fields[1], fields[13], fields[16], fields[17]
        p = head + HEADER_BYTES
        blocks, chunks, fehler = 0, [], ""
        total_packed = 0
        while True:
            blob = d[p:p + packed]
            total_packed += packed
            blocks += 1
            if data:
                part, err = _decompress(blob, raw, method)
                if part is None:
                    fehler = fehler or err
                    break
                chunks.append(part)
            p += packed
            if p >= nxt or p + 8 > len(d) or nxt <= pos:
                break
            packed, raw = struct.unpack_from("<II", d, p)
            p += 8
        short = name.replace("/", "\\").split("\\")[-1] or name
        ext = os.path.splitext(short)[1]
        if short.upper().endswith(".SZN.FEA.ARCHIV"):
            ext = ".FEA"
        entry = {
            "name": name, "kurz": short, "art": PART_KINDS.get(ext, PART_KINDS.get(
                "." + short.rsplit(".", 1)[-1], "")) or "unbekannt",
            "packed": total_packed, "size": len(b"".join(chunks)) if data else None,
            "offset": pos, "blocks": blocks, "verfahren": method, "fehler": fehler,
        }
        if data:
            entry["data"] = b"".join(chunks)
        out.append(entry)
        if short in seen and len(out) > 200:
            break
        seen.add(short)
        if nxt <= pos or nxt >= len(d):
            break
        pos = nxt
    C.say(log, f"HiCAD-Archiv: {len(out)} Teile")
    return out


def extract(path: str, target_dir: str, log: list = None) -> list[str]:
    """Alle Teile des Archivs in ein Verzeichnis schreiben. Rueckgabe: Pfade."""
    os.makedirs(target_dir, exist_ok=True)
    written = []
    for e in archive_entries(path, data=True, log=log):
        if not e.get("data"):
            if e["fehler"]:
                C.warn(log, f"{e['kurz']}: {e['fehler']}")
            continue
        out = os.path.join(target_dir, e["kurz"])
        with open(out, "wb") as f:
            f.write(e["data"])
        written.append(out)
    C.say(log, f"{len(written)} Teile entpackt nach {target_dir}")
    return written


# --------------------------------------------------------------------------
# Teiletabellen (.IPT): die im Modell benutzten Profile und Werkstoffe
# --------------------------------------------------------------------------
def read_part_table(data: bytes) -> dict:
    """Eine ISD-Teiletabelle (.IPT) lesen: Kategorie, Spalten, Zeilen."""
    text = data.decode("utf-16-le", "ignore") if data[:2] in (b"\xff\xfe",) \
        else data.decode("utf-8", "ignore")
    text = text.lstrip("﻿")
    out: dict = {"kategorie": "", "spalten": [], "zeilen": [], "anzahl": 0}
    block = ""
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^\[(\w+)\]$", s)
        if m:
            block = m.group(1).upper()
            continue
        if block == "SIZE":
            mm = re.match(r"(?i)rows\s+(\d+)", s)
            if mm:
                out["anzahl"] = int(mm.group(1))
        elif block == "CATEGORY" and not out["kategorie"]:
            out["kategorie"] = s
        elif block == "PARAMETER":
            parts = s.split(":", 1)
            if len(parts) == 2:
                # "DBL: IY@~1242005312&10€30" -> "IY"
                out["spalten"].append(re.split(r"[@!&€#*]", parts[1].strip())[0].strip())
        elif block in ("DATA", "TABLE", "VALUES"):
            out["zeilen"].append([c.strip() for c in line.split("\t")])
    return out


#: Spalten der ISD-Teiletabellen -> Feld im Querschnitt, mit Umrechnung in SI
IPT_COLUMNS = {
    "H": ("h", 1e-3), "B": ("b", 1e-3), "TS": ("tw", 1e-3), "TG": ("tf", 1e-3),
    "R1": ("r", 1e-3), "F": ("A", 1e-6), "IY": ("Iy", 1e-8), "IZ": ("Iz", 1e-8),
    "WY": ("Wel_y", 1e-6), "WZ": ("Wel_z", 1e-6), "IT": ("It", 1e-8),
}


def _cols(table: dict) -> dict:
    return {name: i for i, name in enumerate(table.get("spalten", []))}


def _val(row, cols, key):
    i = cols.get(key)
    if i is None or i >= len(row):
        return None
    try:
        return float(str(row[i]).replace(",", "."))
    except ValueError:
        return None


def _name(row, cols) -> str:
    i = cols.get("BZ", cols.get("SIZE"))
    return str(row[i]).strip() if i is not None and i < len(row) else ""


def table_sections(table: dict, only: set = None) -> dict:
    """{Bezeichnung: Section} aus einer Teiletabelle.

    Die Kennwerte stehen in den Spalten der ISD-Tabelle: H, B, TS, TG, R1 in
    Millimetern, F (Flaeche) in mm^2, IY/IZ in cm^4, WY/WZ in cm^3 - die
    Katalogwerte, mit denen HiCAD selbst rechnet. Fuehrt die Tabelle nur
    Breite und Dicke (Flachstahl nach EN 10058), wird der Rechteckquerschnitt
    daraus gebildet. Tabellen ohne Querschnittswerte (Werkstoffe, Bleche,
    Schrauben, Muttern, Scheiben) liefern hier nichts.
    """
    from ..model import Section
    cols = _cols(table)
    out: dict = {}
    if "BZ" not in cols and "SIZE" not in cols:
        return out
    if "RHO" in cols or "RE" in cols:          # Werkstofftabelle
        return out
    if is_fastener_table(table):               # Schrauben, Muttern, Scheiben
        return out
    for row in table.get("zeilen", []):
        name = _name(row, cols)
        if not name or (only is not None and name not in only) or name in out:
            continue
        A = _val(row, cols, "F")
        Iy = _val(row, cols, "IY")
        Iz = _val(row, cols, "IZ")
        if A and Iy and Iz:
            sec = Section(name=name, A=A * 1e-6, Iy=Iy * 1e-8, Iz=Iz * 1e-8, It=0.0)
            for col, (field, fac) in (("H", ("h", 1e-3)), ("B", ("b", 1e-3)),
                                      ("TS", ("tw", 1e-3)), ("TG", ("tf", 1e-3)),
                                      ("R1", ("r", 1e-3)), ("WY", ("Wel_y", 1e-6)),
                                      ("WZ", ("Wel_z", 1e-6)), ("IT", ("It", 1e-8))):
                v = _val(row, cols, col)
                if v:
                    setattr(sec, field, v * fac)
            if sec.It <= 0.0:
                # Torsion fuehrt die ISD-Tabelle nicht; duennwandig offen
                # J = 1/3 * sum(b*t^3) aus Steg und zwei Flanschen.
                h, b, tw, tf = sec.h, sec.b, sec.tw, sec.tf
                if h and b and tw and tf:
                    sec.It = ((h - 2 * tf) * tw ** 3 + 2 * b * tf ** 3) / 3.0
            sec.typ = "free"
            sec.zmax = sec.h / 2.0 if sec.h else 0.0
            sec.ymax = sec.b / 2.0 if sec.b else 0.0
            out[name] = sec
            continue
        sec = _from_shape(table, row, cols, name)
        if sec is not None:
            out[name] = sec
    return out


def _from_shape(table: dict, row, cols, name: str):
    """Querschnitt aus den Abmessungen, wenn die Tabelle keine Kennwerte fuehrt.

    Die Kategorie der ISD-Tabelle nennt die Bauform; die Spalten sind je
    Bauform festgelegt (alle Masse in Millimetern).
    """
    from ..model import Section
    kat = (table.get("kategorie") or "").upper()
    g = lambda k: (_val(row, cols, k) or 0.0) * 1e-3      # noqa: E731
    try:
        if "L-PROFIL" in kat or "WINKEL" in kat:
            a, b, t, r = g("A"), g("B") or g("A"), g("S"), g("R1")
            return Section.angle(name, a, b, t, r) if a and t else None
        if "I-PROFIL" in kat or "H-PROFIL" in kat:
            h, b, tw, tf, r = g("H"), g("B"), g("TS"), g("TG"), g("R")
            return Section.i_profile(name, h, b, tw, tf, r) if h and b and tw and tf else None
        if "U-PROFIL" in kat:
            h, b, tw, tf, r = g("H"), g("B"), g("TS"), g("TG"), g("R1")
            taper = 0.08 if "GENEIGTE" in kat else 0.0
            return Section.channel(name, h, b, tw, tf, r, taper) if h and b and tw and tf else None
        if "FLACHSTAHL" in kat:
            b, t = g("B"), g("S")
            return Section.rectangle(name, t, b) if b and t else None
        if "VIERKANT" in kat:
            a = g("A")
            return Section.rectangle(name, a, a) if a else None
        if "RUNDSTAHL" in kat:
            d = g("D")
            return Section.circle(name, d) if d else None
        if "HOHLPROFIL" in kat and "ROND" not in kat and "RUND" not in kat:
            h, b, t = g("H") or g("B"), g("B"), g("S")
            return Section.rhs(name, h, b, t) if h and b and t else None
        if "ROHR" in kat or ("HOHLPROFIL" in kat and ("RUND" in kat or "ROND" in kat)):
            d, t = g("D") or g("DA"), g("S")
            return Section.pipe(name, d, t) if d and t else None
    except (ValueError, ZeroDivisionError):
        return None
    return None


#: Kategorien, die Verbindungsmittel fuehren - keine Querschnitte
FASTENER_WORDS = ("SCHR", "MUTTER", "SCHEIBE", "SECHSKANT", "BOLZEN", "NIET",
                  "DUEBEL", "STIFT", "GEWINDE", "SCREW", "NUT", "WASHER", "BOLT",
                  "DICHTUNG")


def is_fastener_table(table: dict) -> bool:
    kat = (table.get("kategorie") or "").upper()
    return any(w in kat for w in FASTENER_WORDS)


def table_fasteners(table: dict, only: set = None) -> dict:
    """{Bezeichnung: Gewindegroesse} aus einer Verbindungsmitteltabelle."""
    out: dict = {}
    if not is_fastener_table(table):
        return out
    cols = _cols(table)
    for row in table.get("zeilen", []):
        name = _name(row, cols)
        if not name or (only is not None and name not in only) or name in out:
            continue
        mm = re.search(r"M\s?(\d+(?:[.,]\d+)?)", name)
        out[name] = ("M" + mm.group(1).replace(",", ".")) if mm else ""
    return out


def table_plates(table: dict, only: set = None) -> dict:
    """{Bezeichnung: Dicke [m]} aus einer Blechtabelle (Spalte S, ohne B)."""
    cols = _cols(table)
    out: dict = {}
    if "BLECH" not in (table.get("kategorie") or "").upper() or "S" not in cols:
        return out
    for row in table.get("zeilen", []):
        name = _name(row, cols)
        t = _val(row, cols, "S")
        if name and t and (only is None or name in only) and name not in out:
            out[name] = t * 1e-3
    return out


def table_materials(table: dict, only: set = None) -> dict:
    """{Bezeichnung: (rho [kg/m^3], f_y [Pa], f_u [Pa])} aus einer Werkstofftabelle.

    Spalten RHO in g/cm^3, RE und RM in N/mm^2. Liegen die beiden Festigkeiten
    verdreht vor, wird die kleinere als Streckgrenze gefuehrt.
    """
    cols = _cols(table)
    out: dict = {}
    if "RHO" not in cols:
        return out
    for row in table.get("zeilen", []):
        name = _name(row, cols) or (str(row[cols["BZ"]]).strip() if "BZ" in cols else "")
        if not name or (only is not None and name not in only) or name in out:
            continue
        rho = _val(row, cols, "RHO")
        re_ = _val(row, cols, "RE")
        rm = _val(row, cols, "RM")
        fy = fu = None
        if re_ and rm:
            fy, fu = min(re_, rm) * 1e6, max(re_, rm) * 1e6
        elif re_:
            fy = re_ * 1e6
        out[name] = ((rho or 7.85) * 1000.0, fy, fu)
    return out


def part_designations(path: str, log: list = None) -> list[str]:
    """Bauteilbezeichnungen aus dem Attributteil (.ATC) des Archivs.

    HiCAD fuehrt die Bezeichnung eines Bauteils als Attributtext, etwa
    "U 200", "Bl 8", "Fl 60x20". Gesammelt werden alle Texte, die wie eine
    Profil- oder Blechbezeichnung aussehen.
    """
    pat = re.compile(r"^(?:[A-Z]{1,4}[ ]?\d|Bl[ ]?\d|Fl[ ]?\d|Rd[ ]?\d|Vk[ ]?\d|"
                     r"HE[ABM]|IPE|IPB|UPE|UPN|RO|RU|RHS|SHS|CHS|NOTENPROFIL)", re.I)
    found: list[str] = []
    for e in archive_entries(path, data=True, log=None):
        if not e.get("data"):
            continue
        if not (e["kurz"].upper().endswith(".ATC") or e["kurz"].upper().endswith(".DBA3")):
            continue
        for m in re.finditer(rb"(?:[ -~\xc4\xd6\xdc\xe4\xf6\xfc\xdf]\x00){3,}", e["data"]):
            t = m.group(0).decode("utf-16-le", "ignore").strip()
            if 3 <= len(t) <= 40 and pat.match(t) and t not in found and "," not in t:
                found.append(t)
    if found:
        C.say(log, "Bauteilbezeichnungen im Archiv: " + ", ".join(found[:20]))
    return found


def part_tables(path: str, log: list = None) -> dict:
    """{Tabellenname: gelesene Teiletabelle} aus einem HiCAD-Archiv."""
    out = {}
    for e in archive_entries(path, data=True, log=None):
        if e["kurz"].lower().endswith(".ipt") and e.get("data"):
            try:
                out[e["kurz"]] = read_part_table(e["data"])
            except Exception:            # noqa: BLE001
                continue
    if out:
        C.say(log, "Teiletabellen im Archiv: " + ", ".join(
            f"{k} ({v['kategorie'] or '?'}, {v['anzahl']} Zeilen)"
            for k, v in list(out.items())[:8]))
    return out


def preview_png(path: str, target: str) -> str:
    """Vorschaubild (PREVIEW.DIB) als PNG schreiben. Rueckgabe: Pfad oder ""."""
    for e in archive_entries(path, data=True):
        if e["kurz"].upper() != "PREVIEW.DIB" or not e.get("data"):
            continue
        d = e["data"]
        try:
            hdr = struct.unpack_from("<IiiHH", d, 0)
            _sz, w, h, _pl, bpp = hdr
        except struct.error:
            return ""
        # BITMAPINFOHEADER ohne Dateikopf: BMP-Kopf davorsetzen
        bmp = b"BM" + struct.pack("<IHHI", 14 + len(d), 0, 0, 14 + _sz) + d
        with open(target, "wb") as f:
            f.write(bmp)
        return target
    return ""


def report(path: str) -> str:
    """Inhaltsverzeichnis als Text."""
    ents = archive_entries(path)
    size = os.path.getsize(path)
    lines = [f"{os.path.basename(path)}: HiCAD-Archiv (!HFA##), {size / 1e6:.2f} MB, "
             f"{len(ents)} Teile"]
    for e in ents:
        lines.append(f"  {e['kurz']:<40s} {e['packed'] / 1024:9.1f} kB gepackt   {e['art']}")
    return "\n".join(lines)
