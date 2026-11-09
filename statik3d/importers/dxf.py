"""
DXF-Import (ASCII-DXF, R12 bis 2018).

Entitaeten:
    LINE                      -> Stabelement (beam / truss)
    LWPOLYLINE                -> Stabelemente je Segment (geschlossen: mit Schlusssegment)
    POLYLINE / VERTEX         -> 2D/3D-Polylinien -> Staebe; Polyface-Netz -> Schalen
    3DFACE                    -> shell3 / shell4 (4. Punkt == 3. Punkt -> Dreieck)

Optionen:
    unit_scale      Laengenfaktor Datei -> m. Ohne Angabe gilt die Einheit, die
                    die Datei im Kopf nennt ($INSUNITS); nennt sie keine,
                    wird Millimeter angenommen (1e-3) und das gemeldet
    element_type    'beam' oder 'truss' fuer Linien
    subdivide       jede Linie in n Elemente teilen
    layer_sections  {Layername: Querschnittsname / Profilbezeichnung}
    section         Standardquerschnitt (vorhandener Name oder z.B. 'HEA 200')
    material        Materialname (Standard S235)
    shell_prop      Name der Schalendicke fuer 3DFACE (Standard t10)
    tol             Knotentoleranz [m]
Elemente werden nach Layer gruppiert (Element.group = Layer).

Ebenen, deren Name mit ``STATIK3D_`` beginnt (:data:`HILFSEBENE`), traegt der
eigene DXF-Export fuer Lagersymbole, Linien, Lastnamen und Beschriftung ein.
Sie sind kein Tragwerk und werden nicht gelesen (Befund B5 der Pruefagenten,
09.11.2026: die Lagersymbole kamen als Staebe zurueck).
"""
from __future__ import annotations

import os
from typing import Optional

from ..model import Model
from . import _common as C

DEFAULT_UNIT_SCALE = 1e-3

#: Vorsatz der Ebenen, auf die der eigene Export seine Symbole legt
HILFSEBENE = "STATIK3D_"

#: $INSUNITS -> (Name, Faktor nach m). 0 heisst "ohne Einheit" und zaehlt wie
#: eine fehlende Angabe.
EINHEITEN = {1: ("Zoll", 0.0254), 2: ("Fuß", 0.3048), 4: ("Millimeter", 1e-3),
             5: ("Zentimeter", 1e-2), 6: ("Meter", 1.0), 14: ("Dezimeter", 0.1)}


def _de(x: float) -> str:
    """Zahl fuer eine Meldung: Dezimalkomma, nie wissenschaftlich."""
    t = f"{float(x):.6f}".rstrip("0").rstrip(".")
    return t.replace(".", ",")


# --------------------------------------------------------------------------
# Datei lesen: Gruppencode/Wert-Paare -> Entitaeten
# --------------------------------------------------------------------------
def _read_pairs(path: str) -> list[tuple[int, str]]:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("latin-1", errors="replace")
    lines = text.splitlines()
    pairs = []
    i = 0
    n = len(lines)
    while i + 1 < n:
        code_s = lines[i].strip()
        if code_s == "":
            i += 1
            continue
        try:
            code = int(code_s)
        except ValueError:
            i += 1
            continue
        pairs.append((code, lines[i + 1].strip()))
        i += 2
    return pairs


def parse_dxf_entities(path: str) -> list[dict]:
    """ENTITIES-Abschnitt lesen. Jede Entitaet: {'type': 'LINE', 'layer': ...,
    'pairs': [(code, wert), ...]}. Bei fehlendem SECTION-Aufbau (Fragmente) werden
    alle Entitaeten der Datei genommen."""
    pairs = _read_pairs(path)
    ents: list[dict] = []
    in_entities = False
    saw_section = False
    cur: Optional[dict] = None
    section_name_next = False
    for code, val in pairs:
        if code == 0 and val == "SECTION":
            saw_section = True
            section_name_next = True
            cur = None
            continue
        if section_name_next and code == 2:
            in_entities = (val.upper() == "ENTITIES")
            section_name_next = False
            continue
        section_name_next = False
        if code == 0 and val == "ENDSEC":
            in_entities = False
            cur = None
            continue
        if code == 0 and val == "EOF":
            break
        if saw_section and not in_entities:
            continue
        if code == 0:
            cur = {"type": val.upper(), "layer": "0", "pairs": []}
            ents.append(cur)
            continue
        if cur is None:
            continue
        if code == 8:
            cur["layer"] = val or "0"
        cur["pairs"].append((code, val))
    return ents


def einheit_der_datei(path: str) -> Optional[tuple]:
    """Die Laengeneinheit, die eine DXF-Datei im Kopf nennt:
    (Name, Faktor nach m, $INSUNITS) - oder None, wenn $INSUNITS fehlt, 0
    ("ohne Einheit") ist oder eine Einheit nennt, die EINHEITEN nicht kennt."""
    try:
        pairs = _read_pairs(path)
    except OSError:
        return None
    for k, (code, val) in enumerate(pairs):
        if code == 2 and val.upper() == "ENTITIES" and k > 0 \
                and pairs[k - 1] == (0, "SECTION"):
            break                              # der Kopf ist vorbei
        if code == 9 and val.upper() == "$INSUNITS" and k + 1 < len(pairs):
            v = C.parse_number(pairs[k + 1][1])
            eintrag = EINHEITEN.get(int(v)) if v is not None else None
            return (eintrag[0], eintrag[1], int(v)) if eintrag else None
    return None


def _floats(ent: dict, codes: tuple) -> Optional[tuple]:
    """Erstes Vorkommen der Codes als Zahlen (fehlende -> 0.0)."""
    vals = []
    found = False
    for c in codes:
        v = None
        for code, s in ent["pairs"]:
            if code == c:
                v = C.parse_number(s)
                break
        if v is not None:
            found = True
        vals.append(v if v is not None else 0.0)
    return tuple(vals) if found else None


def _int_code(ent: dict, code: int, default: int = 0) -> int:
    for c, s in ent["pairs"]:
        if c == code:
            v = C.parse_number(s)
            return int(v) if v is not None else default
    return default


def _lwpolyline_points(ent: dict) -> tuple[list, bool]:
    """Punktliste einer LWPOLYLINE (x, y, z=Erhebung) und Geschlossen-Flag."""
    pts = []
    z = 0.0
    x = None
    for code, s in ent["pairs"]:
        if code == 38:
            z = C.parse_number(s) or 0.0
    for code, s in ent["pairs"]:
        if code == 10:
            x = C.parse_number(s) or 0.0
        elif code == 20 and x is not None:
            pts.append((x, C.parse_number(s) or 0.0, z))
            x = None
    closed = bool(_int_code(ent, 70) & 1)
    return pts, closed


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------
def import_dxf(path: str, model: Model = None, log: list = None,
               unit_scale: float = None, element_type: str = "beam",
               subdivide: int = 1, layer_sections: dict = None, section: str = None,
               material: str = None, shell_prop: str = None,
               tol: float = C.DEFAULT_TOL, **_ignored) -> Model:
    """DXF-Datei in ein Modell einlesen (siehe Modulbeschreibung)."""
    if model is None:
        model = Model(os.path.splitext(os.path.basename(path))[0])
    if element_type not in ("beam", "truss"):
        raise ValueError("element_type muss 'beam' oder 'truss' sein")
    subdivide = max(1, int(subdivide or 1))
    # Einheit (Befund B5, 09.11.2026): der eigene Export schreibt Meter und
    # nennt das seitdem im Kopf; bis dahin las der Import jede Datei ohne
    # Angabe als Millimeter - auch die eigene, die damit 1000fach zu klein
    # zurueckkam.
    datei = einheit_der_datei(path)
    if unit_scale is None:
        if datei is not None:
            scale = float(datei[1])
            C.say(log, f"DXF: Die Datei nennt im Kopf die Längeneinheit {datei[0]} "
                       f"($INSUNITS = {datei[2]}); sie wird so gelesen.")
        else:
            scale = DEFAULT_UNIT_SCALE
            C.warn(log, "DXF: Die Datei nennt keine Längeneinheit ($INSUNITS fehlt im Kopf "
                        "oder ist 0). Angenommen wurde Millimeter (Faktor 0,001). Ist die "
                        "Datei in einer anderen Einheit gezeichnet, die Einheit beim Import "
                        "angeben.")
    else:
        scale = float(unit_scale)
        if datei is not None and abs(datei[1] - scale) > 1e-9 * max(datei[1], scale):
            C.warn(log, f"DXF: Die Datei nennt im Kopf die Längeneinheit {datei[0]} "
                        f"($INSUNITS = {datei[2]}, Faktor {_de(datei[1])}); gelesen wurde "
                        f"mit dem vorgegebenen Faktor {_de(scale)}.")
        elif datei is None:
            C.say(log, "DXF: Die Datei nennt keine Längeneinheit; gelesen wurde mit dem "
                       f"vorgegebenen Faktor {_de(scale)} m je Zeicheneinheit.")
    layer_sections = dict(layer_sections or {})
    nodes = C.NodeIndex(model, tol)

    mat = C.ensure_material(model, material, log)
    default_sec = C.ensure_section(model, section, log)
    sec_cache: dict[str, str] = {}

    def section_for_layer(layer: str) -> str:
        if layer in sec_cache:
            return sec_cache[layer]
        want = layer_sections.get(layer)
        if want is None:
            for k, v in layer_sections.items():         # Layernamen ohne Gross/Klein
                if k.lower() == layer.lower():
                    want = v
                    break
        sec_cache[layer] = C.ensure_section(model, want, log, fallback=default_sec) \
            if want else default_sec
        return sec_cache[layer]

    shell_name: Optional[str] = None
    stats: dict[str, dict[str, int]] = {}
    skipped: dict[str, int] = {}

    def count(layer: str, kind: str, n: int = 1):
        d = stats.setdefault(layer, {})
        d[kind] = d.get(kind, 0) + n

    def add_line(p1, p2, layer: str):
        p1 = tuple(c * scale for c in p1)
        p2 = tuple(c * scale for c in p2)
        if max(abs(a - b) for a, b in zip(p1, p2)) <= tol:
            count(layer, "Nulllinien")
            return
        chain = C.subdivide_line(nodes, p1, p2, subdivide)
        sec = section_for_layer(layer)
        for a, b in zip(chain[:-1], chain[1:]):
            if a == b:
                continue
            model.add_element(element_type, [a, b], mat, sec, group=layer)
            count(layer, "Staebe")

    def add_face(points, layer: str):
        nonlocal shell_name
        if shell_name is None:
            shell_name = C.ensure_shell_prop(model, shell_prop, None, log)
        ids = [nodes.add(*(c * scale for c in p)) for p in points]
        n = len(C.polygon_to_shells(model, ids, mat, shell_name, layer, log,
                                    f"3DFACE auf Layer '{layer}'"))
        count(layer, "Schalen", n)

    entities = parse_dxf_entities(path)
    hilfe: dict[str, int] = {}
    i = 0
    while i < len(entities):
        ent = entities[i]
        typ = ent["type"]
        layer = ent["layer"]
        try:
            if layer.upper().startswith(HILFSEBENE):
                # Symbole des eigenen Exports: kein Tragwerk
                hilfe[layer] = hilfe.get(layer, 0) + 1
            elif typ == "LINE":
                p1 = _floats(ent, (10, 20, 30))
                p2 = _floats(ent, (11, 21, 31))
                if p1 and p2:
                    add_line(p1, p2, layer)
            elif typ == "LWPOLYLINE":
                pts, closed = _lwpolyline_points(ent)
                segs = list(zip(pts[:-1], pts[1:]))
                if closed and len(pts) > 2:
                    segs.append((pts[-1], pts[0]))
                for a, b in segs:
                    add_line(a, b, layer)
            elif typ == "POLYLINE":
                flags = _int_code(ent, 70)
                verts = []
                j = i + 1
                while j < len(entities) and entities[j]["type"] == "VERTEX":
                    verts.append(entities[j])
                    j += 1
                if j < len(entities) and entities[j]["type"] == "SEQEND":
                    j += 1
                i = j - 1
                if flags & 64:                                 # Polyface-Netz
                    locs = []
                    faces = []
                    for v in verts:
                        vf = _int_code(v, 70)
                        if vf & 128 and not (vf & 64):         # Flaechendefinition
                            idx = [abs(_int_code(v, c)) for c in (71, 72, 73, 74)]
                            faces.append([k for k in idx if k > 0])
                        else:
                            locs.append(_floats(v, (10, 20, 30)) or (0.0, 0.0, 0.0))
                    for f in faces:
                        pts = [locs[k - 1] for k in f if 0 < k <= len(locs)]
                        if len(pts) >= 3:
                            add_face(pts, layer)
                elif flags & 16:                               # Polygonnetz (M x N)
                    m = _int_code(ent, 71)
                    n = _int_code(ent, 72)
                    locs = [_floats(v, (10, 20, 30)) or (0.0, 0.0, 0.0) for v in verts]
                    if m * n == len(locs) and m > 1 and n > 1:
                        for a in range(m - 1):
                            for b in range(n - 1):
                                add_face([locs[a * n + b], locs[a * n + b + 1],
                                          locs[(a + 1) * n + b + 1], locs[(a + 1) * n + b]],
                                         layer)
                    else:
                        skipped["POLYLINE (Polygonnetz)"] = \
                            skipped.get("POLYLINE (Polygonnetz)", 0) + 1
                else:                                          # 2D/3D-Polylinie
                    pts = [_floats(v, (10, 20, 30)) or (0.0, 0.0, 0.0) for v in verts]
                    segs = list(zip(pts[:-1], pts[1:]))
                    if flags & 1 and len(pts) > 2:
                        segs.append((pts[-1], pts[0]))
                    for a, b in segs:
                        add_line(a, b, layer)
            elif typ == "3DFACE":
                p = [_floats(ent, (10 + k, 20 + k, 30 + k)) for k in range(4)]
                pts = [q for q in p if q is not None]
                if len(pts) == 4 and max(abs(a - b) for a, b in zip(pts[3], pts[2])) < 1e-12:
                    pts = pts[:3]
                if len(pts) >= 3:
                    add_face(pts, layer)
            elif typ in ("VERTEX", "SEQEND"):
                pass
            else:
                skipped[typ] = skipped.get(typ, 0) + 1
        except Exception as ex:      # einzelne Entitaet nicht abbrechen lassen
            C.warn(log, f"DXF-Entitaet {typ} auf Layer '{layer}' uebersprungen: {ex}")
        i += 1

    nodes.flush()
    for layer in sorted(stats):
        parts = ", ".join(f"{v} {k}" for k, v in stats[layer].items())
        C.say(log, f"Layer '{layer}': {parts}")
    for typ, n in sorted(skipped.items()):
        C.say(log, f"{n} x {typ} nicht importiert (nicht unterstuetzt)")
    for layer in sorted(hilfe):
        C.say(log, f"Ebene '{layer}': {hilfe[layer]} Zeichenelemente sind Symbole oder "
                   "Beschriftungen des Statik3D-Exports und wurden nicht als Tragwerk gelesen.")
    C.say(log, f"DXF: {model.nn} Knoten, {len(model.elements)} Elemente "
               f"(Massstab {scale:g} m je Zeicheneinheit)")
    return model
