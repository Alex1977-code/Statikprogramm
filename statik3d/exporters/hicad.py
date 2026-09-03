"""
Export als HiCAD-Archiv (.sza) - Behaelter mit den Teilen, die ein offenes
Format haben.

**Was das kann und was nicht.** Der Behaelter selbst (Kennung ``!HFA##``,
Eintraege mit 1024-Byte-Namensfeld, 72-Byte-Kopf und Zstandard-Daten) ist
entschluesselt und wird richtig geschrieben - eine so erzeugte Datei laesst
sich von Statik3D und von jedem Leser dieses Behaelters wieder oeffnen. Die
**3D-Geometrie** von HiCAD steht dagegen im Teil ``SZN`` in einem Format, das
ISD nicht veroeffentlicht; es wird nicht geraten. Eine hier geschriebene
.sza-Datei enthaelt deshalb **kein von HiCAD lesbares Modell**, sondern:

    <name>.SZN.Units      Einheiten (XML)
    <name>.SZN.ELREF      Bauteilliste (XML) mit Profil, Werkstoff, Laenge
    STATIK3D.sdnf         das Tragwerk als SDNF - dieses Format liest HiCAD
    STATIK3D_TEILE.nc     die Teileliste als DSTV-NC
    *.IPT                 Teiletabellen der benutzten Profile und Werkstoffe

Wer das Modell **in HiCAD** haben will, nimmt die enthaltene SDNF-Datei (oder
gleich ``export_model(m, "modell.sdnf")``); das ist der Weg, den HiCAD selbst
vorsieht. Das Archiv ist fuer die Ablage und den Austausch mit Statik3D
gedacht.
"""
from __future__ import annotations

import io
import os
import struct
import tempfile
from datetime import datetime, timezone

import numpy as np

from ..model import Model
from . import _common as C
from ..importers.hicad_sza import MAGIC, FIRST_ENTRY, NAME_BYTES, HEADER_BYTES, METHOD_ZSTD

BLOCK = 1 << 20        # 1 MiB je Block, wie HiCAD


def _filetime(dt: datetime = None) -> int:
    """Windows-FILETIME (100-ns-Schritte seit 1601) als 64-Bit-Zahl."""
    dt = dt or datetime.now(timezone.utc)
    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    return int((dt - epoch).total_seconds() * 10_000_000)


def write_archive(path: str, parts: dict, log: list = None) -> str:
    """HiCAD-Archiv schreiben. parts: {Name im Archiv: bytes}.

    Der Aufbau entspricht dem gelesenen: Kopf bis 0x198, dann je Eintrag
    Namensfeld, Kopf und Zstandard-Daten; Teile ueber 1 MiB in Bloecken mit
    8 Byte Vorspann.
    """
    try:
        import zstandard
    except ImportError as ex:
        raise ImportError("Zum Schreiben eines HiCAD-Archivs wird das Paket "
                          "'zstandard' benoetigt (pip install zstandard).") from ex
    cc = zstandard.ZstdCompressor(level=10)
    kopf = bytearray(MAGIC + b"\x00\x00")
    kopf += struct.pack("<QQ", 5, 11)
    erz = "ISD Software & Systeme GmbH - Dortmund".encode("utf-16-le")
    kopf += struct.pack("<IQ", 22631, len(erz))
    kopf += erz
    kopf += b"\x00" * (FIRST_ENTRY - len(kopf))
    body = bytearray(kopf)
    ft = _filetime()
    for name, data in parts.items():
        nm = str(name).encode("utf-16-le")
        if len(nm) > NAME_BYTES:
            raise ValueError(f"Name zu lang fuer das Namensfeld: {name}")
        bloecke = [data[i:i + BLOCK] for i in range(0, max(len(data), 1), BLOCK)] or [b""]
        gepackt = [cc.compress(b) for b in bloecke]
        laenge = sum(len(g) for g in gepackt) + 8 * (len(gepackt) - 1)
        pos = len(body)
        nxt = pos + NAME_BYTES + HEADER_BYTES + laenge
        body += nm + b"\x00" * (NAME_BYTES - len(nm))
        f = [0] * 18
        f[1] = nxt
        f[13] = METHOD_ZSTD
        f[16] = len(gepackt[0])
        f[17] = len(bloecke[0])
        h = bytearray(struct.pack("<18I", *f))
        struct.pack_into("<QQQ", h, 16, ft, ft, ft)     # drei Zeitstempel
        struct.pack_into("<I", h, 4, nxt)
        struct.pack_into("<I", h, 52, f[13])
        struct.pack_into("<I", h, 64, f[16])
        struct.pack_into("<I", h, 68, f[17])
        body += bytes(h)
        for i, g in enumerate(gepackt):
            if i:
                body += struct.pack("<II", len(g), len(bloecke[i]))
            body += g
    with open(path, "wb") as fh:
        fh.write(bytes(body))
    C.say(log, f"HiCAD-Archiv geschrieben: {len(parts)} Teile -> {path}")
    return path


def _units_xml() -> bytes:
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<Units><Length unit="m"/><Force unit="N"/><Stress unit="Pa"/>'
            '<Angle unit="rad"/></Units>\n').encode("utf-16-le")


def _elref_xml(model: Model) -> bytes:
    z = ['<?xml version="1.0" encoding="utf-8"?>', '<Bauteile Programm="Statik3D">']
    for name, elems in C.member_chains(model):
        e = model.elements[elems[0]]
        L = C.chain_length(model, elems)
        z.append(f'  <Bauteil Name="{name}" Profil="{e.sec or ""}" '
                 f'Werkstoff="{C.steel_grade(model, e.mat)}" Laenge="{L:.4f}"/>')
    for i, e in enumerate(model.elements):
        if e.typ.startswith("shell") and e.sec in model.shells:
            z.append(f'  <Blech Nr="{i + 1}" Dicke="{model.shells[e.sec].t:.4f}" '
                     f'Werkstoff="{C.steel_grade(model, e.mat)}"/>')
    z.append("</Bauteile>")
    return ("\n".join(z) + "\n").encode("utf-8")


def _ipt_sections(model: Model) -> bytes:
    """Teiletabelle im Aufbau 'ISD Part Table File' mit den Profilen des Modells."""
    spalten = ["ID", "MOD", "STATUS", "BZ", "SIZE", "MATERIAL", "OBERFL", "TYPE",
               "DSTV", "H", "B", "TS", "TG", "R1", "F", "IY", "IZ", "IT", "NORM"]
    zeilen = []
    for i, (name, s) in enumerate(model.sections.items(), 1):
        zeilen.append("\t".join(str(v) for v in [
            1242000000 + i, "*", 1, name, name, "", "", "", name.replace(" ", ""),
            f"{(s.h or 0) * 1e3:g}", f"{(s.b or 0) * 1e3:g}", f"{(s.tw or 0) * 1e3:g}",
            f"{(s.tf or 0) * 1e3:g}", f"{(s.r or 0) * 1e3:g}",
            f"{s.A * 1e6:g}", f"{s.Iy * 1e8:g}", f"{s.Iz * 1e8:g}", f"{s.It * 1e8:g}",
            "Statik3D"]))
    txt = ["ISD Part Table File, Version 1.06",
           "# Von Statik3D geschrieben",
           "", "[SIZE]", f"Cols {len(spalten)}", f"Rows {len(zeilen)}",
           "", "[CATEGORY]", "STATIK3D_PROFILE:METRIC",
           "", "[PARAMETER]"]
    for c in spalten:
        art = "STR" if c in ("MOD", "BZ", "SIZE", "MATERIAL", "OBERFL", "TYPE",
                             "DSTV", "NORM") else ("INT" if c in ("ID", "STATUS") else "DBL")
        txt.append(f"{art}: {c}")
    txt += ["", "[DATA]"] + zeilen
    return b"\xff\xfe" + ("\n".join(txt) + "\n").encode("utf-16-le")


def _ipt_materials(model: Model) -> bytes:
    spalten = ["ID", "MOD", "STATUS", "BZ", "BBZ", "WN", "RHO", "RM", "RE", "MATERIAL"]
    zeilen = []
    for i, (name, m) in enumerate(model.materials.items(), 1):
        zeilen.append("\t".join(str(v) for v in [
            1080500000 + i, "*", 1, name, "", "-", f"{m.rho / 1000:g}",
            f"{(m.fu or 0) / 1e6:g}", f"{(m.fy or 0) / 1e6:g}", name]))
    txt = ["ISD Part Table File, Version 1.06", "# Von Statik3D geschrieben", "",
           "[SIZE]", f"Cols {len(spalten)}", f"Rows {len(zeilen)}",
           "", "[CATEGORY]", "MATERIAL:METRIC", "", "[PARAMETER]"]
    for c in spalten:
        art = "STR" if c in ("MOD", "BZ", "BBZ", "WN", "MATERIAL") else (
            "INT" if c in ("ID", "STATUS") else "DBL")
        txt.append(f"{art}: {c}")
    txt += ["", "[DATA]"] + zeilen
    return b"\xff\xfe" + ("\n".join(txt) + "\n").encode("utf-16-le")


def write_sza(model: Model, path: str, results=None, log: list = None, **_) -> str:
    """Modell als HiCAD-Archiv schreiben (siehe Einschraenkung im Modulkopf)."""
    from .sdnf import write_sdnf
    from .dstv import nc_text
    stamm = os.path.splitext(os.path.basename(path))[0]
    tmp = tempfile.mkdtemp(prefix="statik3d_sza_")
    try:
        sd = os.path.join(tmp, "modell.sdnf")
        write_sdnf(model, sd, log=None)
        with open(sd, "rb") as f:
            sdnf_bytes = f.read()
        nc = []
        for name, elems in C.member_chains(model):
            try:
                nc.append(nc_text(model, name, elems))
            except ValueError:
                continue
        parts = {
            f"C:\\HiCAD\\temp\\Statik3D\\{stamm}.SZN.Units": _units_xml(),
            f"C:\\HiCAD\\temp\\Statik3D\\{stamm}.SZN.ELREF": _elref_xml(model),
            "STATIK3D.sdnf": sdnf_bytes,
            "STATIK3D_TEILE.nc": ("\n".join(nc)).encode("latin-1", "replace"),
            "STATIK3D_PROFILE.IPT": _ipt_sections(model),
            "ALLGEMEINE_BAUSTAEHLE.IPT": _ipt_materials(model),
        }
        write_archive(path, parts, log)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    C.say(log, "Hinweis: HiCAD liest aus diesem Archiv kein Modell - der Aufbau des "
               "Teils SZN ist nicht veroeffentlicht. Fuer HiCAD die enthaltene "
               "SDNF-Datei nehmen (oder gleich nach .sdnf schreiben).")
    return path
