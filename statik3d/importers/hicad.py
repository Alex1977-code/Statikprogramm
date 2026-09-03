"""
HiCAD (ISD Software und Systeme): Szenen und Bauteile.

    .sza    Szene (Baugruppe mit Lage im Raum)
    .kra    Konstruktion / Baugruppe
    .fga    Figur / Einzelteil
    .fig    Figur (aeltere Fassung)
    .vaa    Variante

ISD veroeffentlicht den Aufbau dieser Dateien nicht. Statt zu raten, wird die
Datei untersucht (``probe``): Behaelter, Kennung, Groesse, eingebettete
Behaelter (ZIP, SQLite, OLE2, gzip) und lesbare Zeichenketten - darunter
Profilbezeichnungen und Werkstoffe, die sich gegen die Profildatenbank und die
Stahlsorten pruefen lassen. Ist ein bekannter Behaelter darin, wird er
gelesen; sonst nennt die Meldung den genauen Befund und den Exportweg.

Vollstaendig gelesen werden die Austauschformate, die HiCAD schreibt:

    SDNF (.sdnf)   Bauteile mit Lage im Bauwerk, Profil, Werkstoff  -> sdnf.py
    DSTV-NC (.nc1) Einzelteile mit Profil, Laenge, Bohrungen        -> dstv.py
    IFC (.ifc)     Bauteilachsen oder Statikmodell                  -> ifc.py
    STEP (.stp)    Geometrie, wird vernetzt                         -> mesher
    DXF (.dxf)     Linien und Flaechen                              -> dxf.py

    from statik3d.importers.hicad import probe, import_hicad
    print(probe("halle.sza")["report"])
"""
from __future__ import annotations

import os
import re
import zipfile

from ..model import Model
from .. import profiles
from . import _common as C

HICAD_EXT = (".sza", ".kra", ".fga", ".fig", ".vaa")

MAGICS = [
    (b"!HFA##", "hfa", "HiCAD-Archiv (!HFA##)"),
    (b"SQLite format 3\x00", "sqlite", "SQLite-Datenbank"),
    (b"PK\x03\x04", "zip", "ZIP-Behaelter"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole", "OLE2-Verbunddatei"),
    (b"\x1f\x8b", "gzip", "gzip-Strom"),
    (b"<?xml", "xml", "XML"),
    (b"ISO-10303", "step", "STEP (ISO 10303)"),
    (b"Packet 00", "sdnf", "SDNF"),
    (b"ST\n", "dstv", "DSTV-NC"),
    (b"ST\r\n", "dstv", "DSTV-NC"),
]

EXPORT_HINT = (
    "Exportweg aus HiCAD: Schnittstellen -> SDNF (Bauteile mit Lage im Bauwerk), "
    "DSTV-NC (Einzelteile fuer die Fertigung), IFC (Bauwerksmodell) oder "
    "STEP/DXF (Geometrie). Diese Formate liest Statik3D vollstaendig ein."
)


def _strings(data: bytes, minlen: int = 4, limit: int = 4000) -> list[str]:
    """Lesbare Zeichenketten (ASCII und UTF-16LE) aus einem Binaerstrom."""
    out: list[str] = []
    for pat in (rb"[ -~]{%d,}" % minlen, rb"(?:[ -~]\x00){%d,}" % minlen):
        for mt in re.finditer(pat, data):
            s = mt.group(0)
            txt = (s.decode("utf-16-le", "ignore") if b"\x00" in s
                   else s.decode("ascii", "ignore")).strip()
            if len(txt) >= minlen:
                out.append(txt)
            if len(out) >= limit:
                return out
    return out


def find_profiles(strings) -> list[str]:
    """Zeichenketten, die die Profildatenbank als Profil kennt."""
    found = []
    for s in strings:
        for tok in re.split(r"[;,|\t]", s):
            tok = tok.strip()
            if len(tok) < 3 or tok in found:
                continue
            try:
                profiles.make_section(tok, tok)
            except (KeyError, ValueError):
                continue
            found.append(tok)
    return found


def find_grades(strings) -> list[str]:
    out = []
    for s in strings:
        for tok in re.split(r"[\s;,|\t]", s):
            g = C.steel_grade_from_text(tok.strip())
            if g and g not in out:
                out.append(g)
    return out


def probe(path: str, deep: bool = True) -> dict:
    """Behaelter einer HiCAD-Datei bestimmen.

    Rueckgabe: dict mit kind, name, size, magic, profile, grades, strings,
    embedded und report.
    """
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(64)
        f.seek(0)
        data = f.read(min(size, 8 << 20)) if deep else head
    kind, desc = "unbekannt", "unbekanntes Format"
    for magic, k, d in MAGICS:
        if data.startswith(magic) or (k == "step" and magic in data[:512]):
            kind, desc = k, d
            break
    strings = _strings(data) if deep else []
    info = {
        "name": os.path.basename(path), "size": size, "kind": kind,
        "beschreibung": desc,
        "magic": " ".join(f"{b:02x}" for b in head[:12]),
        "profile": find_profiles(strings)[:40],
        "grades": find_grades(strings)[:20],
        "strings": [s for s in strings[:60] if len(s) >= 6],
        "embedded": [],
    }
    if deep:
        for magic, k, d in MAGICS[:4]:
            pos = data.find(magic, 1)
            if pos > 0:
                info["embedded"].append({"art": k, "beschreibung": d, "offset": pos})
    if kind == "zip":
        try:
            with zipfile.ZipFile(path) as z:
                info["zip"] = sorted(z.namelist())[:60]
        except zipfile.BadZipFile:
            pass
    info["report"] = _report(info)
    return info


def _report(info: dict) -> str:
    mb = info["size"] / 1e6
    out = [f"{info['name']}: {mb:.2f} MB, Kennung {info['magic']}",
           f"Behaelter: {info['beschreibung']}"]
    if info.get("zip"):
        out.append("Enthaltene Dateien (%d): %s" % (len(info["zip"]),
                                                    ", ".join(info["zip"][:12])))
    if info["embedded"]:
        out.append("Eingebettete Behaelter: " + ", ".join(
            f"{e['beschreibung']} ab Byte {e['offset']}" for e in info["embedded"][:4]))
    if info["profile"]:
        out.append("Erkannte Profile (%d): %s" % (len(info["profile"]),
                                                  ", ".join(info["profile"][:12])))
    if info["grades"]:
        out.append("Erkannte Werkstoffe: " + ", ".join(info["grades"][:8]))
    if not info["profile"] and info["strings"]:
        out.append("Lesbare Zeichenketten: " + ", ".join(info["strings"][:8]))
    return "\n".join(out)


def import_hicad(path: str, model: Model = None, log: list = None, **options) -> Model:
    """HiCAD-Datei einlesen, soweit ihr Behaelter zugaenglich ist.

    Enthaelt die Datei einen bekannten Behaelter oder ein bekanntes
    Austauschformat, wird dieses gelesen. Sonst nennt die Ausnahme den genauen
    Befund und den Exportweg - geraten wird nichts.
    """
    info = probe(path)
    C.say(log, info["report"])
    kind = info["kind"]
    if kind == "hfa":
        return _from_archive(path, model, log, **options)
    if kind == "sdnf":
        from .sdnf import import_sdnf
        return import_sdnf(path, model, log, **options)
    if kind == "dstv":
        from .dstv import import_dstv
        return import_dstv(path, model, log, **options)
    if kind == "step":
        from .. import mesher
        m = model or Model(os.path.splitext(os.path.basename(path))[0])
        if not mesher.HAVE_GMSH:
            raise ImportError("STEP-Geometrie in der HiCAD-Datei erkannt; zum Vernetzen "
                              "wird das Paket 'gmsh' benoetigt (pip install gmsh).")
        mat = C.ensure_material(m, options.get("material"), log)
        mesher.mesh_cad(m, path, mat, size=float(options.get("size", 0.0)),
                        dim=int(options.get("dim", 3)))
        return m
    if kind == "zip":
        m = _from_zip(path, model, log, **options)
        if m is not None:
            return m
    raise ImportError(
        f"{info['report']}\n\n"
        "Der Aufbau dieser HiCAD-Datei ist nicht lesbar - ISD veroeffentlicht ihn "
        "nicht, und es wird nichts geraten. " + EXPORT_HINT)


def _from_archive(path: str, model=None, log=None, **options):
    """HiCAD-Archiv (!HFA##) lesen: Teileliste, Profile und Werkstoffe.

    Der Behaelter und alle Teile mit offenem Format werden gelesen. Die
    3D-Geometrie liegt in den Teilen SZN und VIEWER.GFIG in einem Binaerformat,
    das ISD nicht veroeffentlicht - sie wird nicht geraten. Uebernommen werden
    die im Modell benutzten Profile mit ihren Katalogwerten aus den
    mitgelieferten Teiletabellen sowie die Werkstoffe; die Teileliste steht im
    Protokoll.
    """
    from . import hicad_sza as A
    m = model or Model(os.path.splitext(os.path.basename(path))[0])
    ents = A.archive_entries(path, log=log)
    C.say(log, "Teile: " + ", ".join(f"{e['kurz']} ({e['art']})" for e in ents[:10])
               + (" ..." if len(ents) > 10 else ""))
    desig = A.part_designations(path, log)
    used = {re.split(r"\s*\{", d)[0].strip() for d in desig} or None
    if used is None:
        C.say(log, "Keine Bauteilbezeichnungen im Archiv - es werden alle Eintraege "
                   "der Teiletabellen uebernommen.")
    from ..model import Material, ShellProp
    n_sec = n_plate = n_mat = 0
    for tname, table in A.part_tables(path, log).items():
        for name, sec in A.table_sections(table, only=used).items():
            sec.name = C.unique_name(m.sections, name)
            m.add_section(sec)
            n_sec += 1
            C.say(log, f"  Profil '{name}' aus {tname}: A = {sec.A * 1e4:.2f} cm^2, "
                       f"I_y = {sec.Iy * 1e8:.1f} cm^4, I_z = {sec.Iz * 1e8:.1f} cm^4, "
                       f"I_t = {sec.It * 1e8:.2f} cm^4")
        for name, t in A.table_plates(table, only=used).items():
            m.add_shell_prop(ShellProp(C.unique_name(m.shells, name), float(t)))
            n_plate += 1
            C.say(log, f"  Blech '{name}': t = {t * 1e3:g} mm")
        for name, (rho, fy, fu) in A.table_materials(table, only=used).items():
            if name in m.materials:
                continue
            grade = C.steel_grade_from_text(name) or ""
            quelle = "Teiletabelle"
            if grade:
                # Die Bezeichnung nennt die Sorte; massgebend ist die Norm
                # (EN 10025-2). Weicht die Teiletabelle ab, steht das im Protokoll.
                ref = Material.steel(grade)
                if fy and abs(ref.fy - fy) > 0.05 * ref.fy:
                    C.warn(log, f"Werkstoff '{name}': Teiletabelle fuehrt "
                                f"f_y = {fy / 1e6:g} N/mm^2, nach EN 10025-2 gilt "
                                f"{ref.fy / 1e6:g} N/mm^2 - die Norm wird verwendet.")
                fy, fu, quelle = ref.fy, ref.fu, f"EN 10025-2 ({grade})"
            m.add_material(Material(name, E=210e9, nu=0.3, rho=rho,
                                    fy=fy, fu=fu, grade=grade))
            n_mat += 1
            C.say(log, f"  Werkstoff '{name}': rho = {rho:g} kg/m^3"
                       + (f", f_y = {fy / 1e6:g} N/mm^2" if fy else "")
                       + (f", f_u = {fu / 1e6:g} N/mm^2" if fu else "")
                       + f" [{quelle}]")
    grades = sorted(m.materials)
    fasten = {}
    for _t, table in A.part_tables(path, None).items():
        fasten.update(A.table_fasteners(table, only=used))
    if fasten:
        C.say(log, "Verbindungsmittel im Modell: " + ", ".join(
            f"{k}" + (f" ({v})" if v else "") for k, v in fasten.items()))
    stueck = [d for d in desig if "{" in d]
    if stueck:
        C.say(log, "Teileliste (Bezeichnung {Gruppe} {Positionsnummer}):")
        for d in stueck:
            C.say(log, "  " + d)
    # Geometrie aus dem Szenenteil: Stabachsen, die HiCAD selbst nennt
    n_stab = n_knoten = 0
    if options.get("geometrie", True):
        n_stab, n_knoten = _szn_geometrie(path, m, ents, log, **options)
    C.say(log, f"HiCAD-Archiv gelesen: {n_sec} Profile mit Katalogwerten, "
               f"{n_plate} Blechdicken, {n_mat} Werkstoffe, {len(stueck)} Positionen"
               + (f", {n_stab} Staebe mit {n_knoten} Knoten aus der Szene." if n_stab
                  else ". Die Szene nennt keine Stabachsen."))
    if not n_stab:
        C.say(log, "Fuer die vollstaendige Geometrie: " + EXPORT_HINT)
    return m


def _szn_geometrie(path, m, ents, log, **options):
    """Stabachsen aus dem Szenenteil (SZN) uebernehmen.

    HiCAD legt im Szenenteil je Bauteil die Achse als eigene Punktart ab. Wo
    sie steht, wird sie unmittelbar als Stabachse uebernommen; der Querschnitt
    folgt aus den senkrecht dazu gemessenen Massen und wird in den benutzten
    Teiletabellen gesucht. Naeheres in hicad_szn.py.
    """
    from . import hicad_sza as A
    from . import hicad_szn as Z
    szn = None
    try:
        for e in A.archive_entries(path, data=True):
            if e["kurz"].upper().endswith(".SZN") and e.get("data"):
                szn = e["data"]
                break
    except Exception as ex:      # noqa: BLE001 - Geometrie ist eine Zugabe
        C.warn(log, f"Szenenteil nicht lesbar: {ex}")
        return 0, 0
    if not szn or not Z.is_szn(szn):
        return 0, 0
    try:
        r = Z.in_modell(szn, m, profile=dict(m.sections), log=log)
    except Exception as ex:      # noqa: BLE001
        C.warn(log, f"Szenenteil nicht auswertbar: {ex}")
        return 0, 0
    if r["staebe"]:
        radius = float(options.get("anschluss") or 0.0)
        if radius > 0:
            Z.an_staebe_anschliessen(m, radius, log)
        Z.zusammenhang(m, log)
        if radius <= 0:
            C.say(log, "Die Querstaebe enden an der Aussenkante der Pfosten. Mit der "
                       "Option anschluss=0.06 (60 mm) werden freie Stabenden auf die "
                       "Achse des naechsten Stabes gelotet und die Staebe dort geteilt; "
                       "in der Oberflaeche macht das 'Freie Stabenden anschliessen'.")
        C.say(log, f"Szene: {r['staebe']} Staebe mit {r['knoten']} Knoten aus den "
                   f"Bauteilachsen uebernommen (Laengen und Lage aus der Datei, "
                   f"Querschnitte ueber die gemessenen Masse zugeordnet). "
                   f"Bleche, Verbindungsmittel und die genaue Koerpergeometrie sind "
                   f"nicht enthalten - dafuer den Exportweg nehmen: " + EXPORT_HINT)
    return r["staebe"], r["knoten"]


def _from_zip(path: str, model, log, **options):
    """Bekannte Austauschformate aus einem ZIP-Behaelter lesen."""
    import tempfile
    from .sdnf import import_sdnf, SDNF_EXT
    from .dstv import import_dstv, NC_EXT
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        sdnf = [n for n in names if os.path.splitext(n)[1].lower() in SDNF_EXT]
        nc = [n for n in names if os.path.splitext(n)[1].lower() in NC_EXT]
        ifc = [n for n in names if n.lower().endswith(".ifc")]
        if not (sdnf or nc or ifc):
            return None
        tmp = tempfile.mkdtemp(prefix="statik3d_hicad_")
        try:
            if sdnf:
                out = os.path.join(tmp, os.path.basename(sdnf[0]))
                with open(out, "wb") as fh:
                    fh.write(z.read(sdnf[0]))
                C.say(log, f"SDNF im Behaelter gefunden: {sdnf[0]}")
                return import_sdnf(out, model, log, **options)
            if ifc:
                from .ifc import import_ifc
                out = os.path.join(tmp, os.path.basename(ifc[0]))
                with open(out, "wb") as fh:
                    fh.write(z.read(ifc[0]))
                C.say(log, f"IFC im Behaelter gefunden: {ifc[0]}")
                return import_ifc(out, model, log, **options)
            for n in nc:
                out = os.path.join(tmp, os.path.basename(n))
                with open(out, "wb") as fh:
                    fh.write(z.read(n))
            C.say(log, f"{len(nc)} DSTV-NC-Dateien im Behaelter gefunden")
            return import_dstv(tmp, model, log, **options)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
