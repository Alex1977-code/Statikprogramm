"""
DSTV-NC: Stahlbauteile im NC-Format (.nc, .nc1, .nc2, .dstv).

Das Format ist die "Standardbeschreibung Stahlbau-Teile fuer die NC-Steuerung"
des Deutschen Stahlbau-Verbandes und wird von HiCAD, Tekla, Advance Steel,
bocad und praktisch jeder Stahlbausoftware geschrieben. Eine Datei beschreibt
**ein** Teil: Kopfdaten, Bohrungen, Konturen.

    ST                      Beginn Teil
      <Auftrag>             Zeile je Wert, Kommentare mit ** oder nach //
      <Zeichnung>
      <Phase>
      <Position>
      <Werkstoff>
      <Stueckzahl>
      <Profil>              z. B. HEA200, IPE300, L80*8, RO114.3*3.6
      <Profilcode>          I U L M R RU RO B C T SO
      <Laenge>              [mm]
      <Hoehe> <Breite> <Flanschdicke> <Stegdicke> <Radius>
      <Gewicht je m> <Oberflaeche je m>
      ...
    BO   Bohrungen          Flaeche v/o/u/h, Lage, Durchmesser
    AK   Aussenkontur
    IK   Innenkontur
    SI   Beschriftung
    EN   Ende

Eine einzelne NC-Datei traegt **keine** Lage im Bauwerk - sie beschreibt das
Teil in seinem eigenen Koordinatensystem. Ein Ordner oder ZIP mit NC-Dateien
ergibt deshalb eine Teileliste: je Teil ein Stab der richtigen Laenge mit
richtigem Profil und Werkstoff, nebeneinander gelegt. Fuer die Lage im Bauwerk
ist SDNF oder IFC der richtige Weg (siehe sdnf.py, ifc.py).

    from statik3d.importers.dstv import read_nc, import_dstv
    teil = read_nc("HEA200.nc1")
    m = import_dstv("ordner_mit_nc_dateien", log=msgs)
"""
from __future__ import annotations

import os
import re
import zipfile

from ..model import Model, Section
from . import _common as C

NC_EXT = (".nc", ".nc1", ".nc2", ".dstv")

#: Profilcodes der DSTV-Norm
PROFILE_CODES = {
    "I": "I-Profil", "U": "U-Profil", "L": "Winkel", "M": "Rohr (rechteckig)",
    "R": "Rundstahl", "RU": "Rundrohr", "RO": "Rundrohr", "B": "Blech",
    "C": "C-Profil", "T": "T-Profil", "SO": "Sonderprofil",
}

#: Kopffelder in ihrer Reihenfolge nach ST
HEADER_FIELDS = [
    "auftrag", "zeichnung", "phase", "position", "werkstoff", "stueckzahl",
    "profil", "code", "laenge", "hoehe", "breite", "flanschdicke", "stegdicke",
    "radius", "gewicht", "oberflaeche",
]

BLOCKS = ("ST", "BO", "SI", "AK", "IK", "PU", "KO", "SC", "KA", "EN", "TO", "UE", "PR", "KP")


def _clean(line: str) -> str:
    """Kommentare und Fuehrungszeichen entfernen."""
    s = line.rstrip("\n\r")
    if "**" in s:
        s = s.split("**", 1)[0]
    if "//" in s:
        s = s.split("//", 1)[0]
    return s.strip()


def _number(text: str):
    """Erste Zahl einer Zeile; Zusaetze wie 's' oder 'u' werden verworfen."""
    m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text or "")
    return float(m.group(0)) if m else None


def read_nc(path_or_text: str, name: str = "") -> dict:
    """Eine NC-Datei lesen. Rueckgabe: dict mit Kopfdaten, Bohrungen, Konturen."""
    if os.path.sep in path_or_text or os.path.exists(path_or_text):
        with open(path_or_text, "r", encoding="latin-1", errors="ignore") as f:
            text = f.read()
        name = name or os.path.basename(path_or_text)
    else:
        text = path_or_text
    lines = [_clean(l) for l in text.splitlines()]
    part: dict = {"datei": name, "bohrungen": [], "konturen": []}
    block = ""
    header: list[str] = []
    contour: list[list[float]] = []
    for raw in lines:
        if not raw:
            continue
        tag = raw.split()[0].upper() if raw.split() else ""
        if tag in BLOCKS and len(raw.split()) == 1:
            if block in ("AK", "IK") and contour:
                part["konturen"].append({"art": block, "punkte": contour})
                contour = []
            block = tag
            continue
        if block == "ST":
            header.append(raw)
        elif block == "BO":
            vals = raw.split()
            if len(vals) >= 3:
                part["bohrungen"].append({
                    "flaeche": vals[0], "x": _number(vals[1]),
                    "y": _number(vals[2]) if len(vals) > 2 else None,
                    "d": _number(vals[3]) if len(vals) > 3 else None})
        elif block in ("AK", "IK"):
            vals = [_number(v) for v in raw.split()[1:]] if raw.split() else []
            vals = [v for v in vals if v is not None]
            if len(vals) >= 2:
                contour.append(vals[:3])
    if block in ("AK", "IK") and contour:
        part["konturen"].append({"art": block, "punkte": contour})
    for key, val in zip(HEADER_FIELDS, header):
        part[key] = val
    for key in ("laenge", "hoehe", "breite", "flanschdicke", "stegdicke",
                "radius", "gewicht", "oberflaeche", "stueckzahl"):
        part[key] = _number(part.get(key, "")) if part.get(key) is not None else None
    part["code"] = (part.get("code") or "").strip().upper()
    part["profil"] = (part.get("profil") or "").strip()
    part["werkstoff"] = (part.get("werkstoff") or "").strip()
    return part


def is_nc(path: str) -> bool:
    """Datei am Kopfblock ST und am Endblock EN erkennen."""
    try:
        with open(path, "r", encoding="latin-1", errors="ignore") as f:
            head = f.read(4096)
    except OSError:
        return False
    lines = [_clean(l) for l in head.splitlines()]
    return any(l == "ST" for l in lines[:8])


def section_from_part(part: dict, log: list = None) -> Section:
    """Querschnitt aus Profilbezeichnung, sonst aus den Kopfmassen."""
    name = part.get("profil") or "Profil"
    sec = C.section_from_designation(name, name)
    if sec is not None:
        return sec
    code = part.get("code") or ""
    h = (part.get("hoehe") or 0.0) / 1000.0
    b = (part.get("breite") or 0.0) / 1000.0
    tf = (part.get("flanschdicke") or 0.0) / 1000.0
    tw = (part.get("stegdicke") or 0.0) / 1000.0
    r = (part.get("radius") or 0.0) / 1000.0
    try:
        if code == "I" and h and b and tw and tf:
            return Section.i_profile(name, h, b, tw, tf, r)
        if code in ("U", "C") and h and b and tw and tf:
            return Section.channel(name, h, b, tw, tf, r)
        if code == "L" and h and b and tf:
            return Section.angle(name, h, b, tf, r)
        if code == "M" and h and b and tf:
            return Section.rhs(name, h, b, tf)
        if code in ("RU", "RO") and h and tf:
            return Section.pipe(name, h, tf)
        if code == "R" and h:
            return Section.circle(name, h)
        if code == "B" and h and b:
            return Section.rectangle(name, b, h)
    except (ValueError, ZeroDivisionError):
        pass
    C.warn(log, f"Profil '{name}' (Code {code or '-'}) nicht aufloesbar - "
                "Kennwerte aus Hoehe und Breite geschaetzt.")
    return Section.rectangle(name, b or 0.1, h or 0.1)


def nc_files(path: str) -> list[tuple[str, str]]:
    """[(Anzeigename, Inhalt)] aus einer Datei, einem Ordner oder einem ZIP."""
    out: list[tuple[str, str]] = []
    if os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            for fn in sorted(files):
                if os.path.splitext(fn)[1].lower() in NC_EXT:
                    full = os.path.join(root, fn)
                    with open(full, "r", encoding="latin-1", errors="ignore") as f:
                        out.append((fn, f.read()))
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for nm in sorted(z.namelist()):
                if os.path.splitext(nm)[1].lower() in NC_EXT:
                    out.append((os.path.basename(nm),
                                z.read(nm).decode("latin-1", "ignore")))
    else:
        with open(path, "r", encoding="latin-1", errors="ignore") as f:
            out.append((os.path.basename(path), f.read()))
    return out


def import_dstv(path: str, model: Model = None, log: list = None,
                spacing: float = 0.5, **_) -> Model:
    """DSTV-NC-Teile als Teileliste einlesen (Datei, Ordner oder ZIP).

    Je Teil entsteht ein Stab der im Kopf angegebenen Laenge mit seinem Profil
    und Werkstoff. Die Teile liegen nebeneinander in y, weil NC-Dateien keine
    Lage im Bauwerk fuehren.
    """
    m = model or Model(os.path.splitext(os.path.basename(path))[0])
    files = nc_files(path)
    if not files:
        raise ImportError(f"{os.path.basename(path)}: keine DSTV-NC-Dateien gefunden "
                          f"(erwartet {', '.join(NC_EXT)}).")
    C.say(log, f"{len(files)} DSTV-NC-Datei(en) gefunden")
    y = 0.0
    n_teile = 0
    gesamt_masse = 0.0
    for name, text in files:
        part = read_nc(text, name)
        L = (part.get("laenge") or 0.0) / 1000.0
        if L <= 0:
            C.warn(log, f"{name}: keine Laenge im Kopf - uebersprungen.")
            continue
        sec = section_from_part(part, log)
        sec.name = C.unique_name(m.sections, sec.name)
        m.add_section(sec)
        mat = part.get("werkstoff") or C.DEFAULT_STEEL
        grade = C.steel_grade_from_text(mat)
        matname = C.unique_name(m.materials, mat) if mat not in m.materials else mat
        if matname not in m.materials:
            C.ensure_material(m, matname, log, quiet=bool(grade))
        n0 = m.add_node(0.0, y, 0.0)
        n1 = m.add_node(L, y, 0.0)
        e = m.add_element("beam", [n0, n1], matname, sec.name)
        pos = (part.get("position") or part.get("zeichnung") or name).strip()
        stk = int(part.get("stueckzahl") or 1)
        m.add_member(C.unique_name(m.members, pos or f"T{n_teile + 1}"), [e])
        masse = (part.get("gewicht") or 0.0) * L * stk
        gesamt_masse += masse
        C.say(log, f"  {pos or name}: {part.get('profil') or '-'} "
                   f"({PROFILE_CODES.get(part['code'], part['code'] or '-')}), "
                   f"L = {L * 1000:.0f} mm, {mat}, {stk} Stk"
                   + (f", {len(part['bohrungen'])} Bohrungen" if part["bohrungen"] else "")
                   + (f", {masse:.1f} kg" if masse else ""))
        y += spacing + (part.get("breite") or 0.0) / 1000.0
        n_teile += 1
    if not n_teile:
        raise ImportError(f"{os.path.basename(path)}: keine lesbaren Teile "
                          "(Kopfblock ST mit Laenge fehlt).")
    C.say(log, f"{n_teile} Teile uebernommen"
               + (f", Gesamtmasse {gesamt_masse:.1f} kg" if gesamt_masse else ""))
    C.say(log, "DSTV-NC beschreibt Einzelteile ohne Lage im Bauwerk - die Teile liegen "
               "nebeneinander. Fuer das zusammengebaute Tragwerk aus HiCAD den Weg "
               "ueber SDNF oder IFC nehmen.")
    return m
