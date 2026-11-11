"""
Export nach AutoCAD DXF (ASCII, R12-vertraeglich).

Staebe werden zu LINE, Schalen zu 3DFACE, Aussenflaechen der Volumen tet4, tet10
und hex8 ebenso (die uebrigen Volumenarten nennt der Hinweis „nicht übertragen“).
Lagersymbole, Linien, Lastnamen und Stabnamen kommen auf eigene Ebenen, deren
Name mit ``STATIK3D_`` beginnt: so lassen sie sich im CAD getrennt schalten,
und der eigene Import liest sie nicht als Tragwerk (Befund B5 der
Pruefagenten, 09.11.2026: bis dahin lagen sie auf LAGER und LINIEN und kamen
als Staebe zurueck). Die Koordinaten stehen in Metern; der Kopf nennt das mit
$INSUNITS = 6 (bis zum 09.11.2026 fehlte die Angabe, und der Import las die
eigene Datei als Millimeter).

    from statik3d.exporters.dxf import write_dxf
    write_dxf(m, "modell.dxf")
"""
from __future__ import annotations

import numpy as np

from ..model import Model
from ..importers.dxf import HILFSEBENE
from . import _common as C

#: Volumenarten, deren Aussenflaechen als 3DFACE hinausgehen (die Arten, die
#: mesher.surface_facets kennt)
_VOLUMEN_MIT_FLAECHEN = ("tet4", "tet10", "hex8")

#: Ebenen der Symbole und Beschriftungen (kein Tragwerk)
E_LAGER = HILFSEBENE + "LAGER"
E_LASTEN = HILFSEBENE + "LASTEN"
E_TEXT = HILFSEBENE + "BESCHRIFTUNG"
E_LINIEN = HILFSEBENE + "LINIEN"

#: Layer -> Farbnummer (AutoCAD Color Index)
LAYERS = {"STAEBE": 7, "SCHALEN": 5, "VOLUMEN": 8, "KNOTEN": 9,
          E_LAGER: 1, E_LASTEN: 2, E_TEXT: 3, E_LINIEN: 4}

#: $INSUNITS: 6 = Meter
INSUNITS_METER = 6


def _p(code: int, value) -> str:
    return f"{code:3d}\n{value}\n"


def _k(x) -> str:
    """Koordinate mit voller Genauigkeit (09.11.2026, Befund B5): die kuerzeste
    Schreibweise, die dieselbe Zahl zurueckgibt. Bis dahin sechs
    Nachkommastellen - die Rundreise verschob Knoten um bis zu einem halben
    Mikrometer."""
    return repr(float(x)).upper()


def write_dxf(model: Model, path: str, results=None, log: list = None,
              text_height: float = None, **_) -> str:
    """Modell als DXF schreiben. Rueckgabe: Pfad."""
    h = text_height or max(model.characteristic_size() * 0.02, 1e-3)
    out = []
    # ---- Kopf: Herkunft (Kommentar) und Laengeneinheit -----------------
    out.append(_p(999, "Statik3D DXF-Export, Koordinaten in Metern"))
    out.append(_p(0, "SECTION") + _p(2, "HEADER")
               + _p(9, "$INSUNITS") + _p(70, INSUNITS_METER) + _p(0, "ENDSEC"))
    # ---- Tabellen (Layer) ---------------------------------------------
    out.append(_p(0, "SECTION") + _p(2, "TABLES"))
    out.append(_p(0, "TABLE") + _p(2, "LAYER") + _p(70, len(LAYERS)))
    for name, farbe in LAYERS.items():
        out.append(_p(0, "LAYER") + _p(2, name) + _p(70, 0) + _p(62, farbe)
                   + _p(6, "CONTINUOUS"))
    out.append(_p(0, "ENDTAB") + _p(0, "ENDSEC"))
    # ---- Objekte ------------------------------------------------------
    out.append(_p(0, "SECTION") + _p(2, "ENTITIES"))

    def line(p1, p2, layer):
        out.append(_p(0, "LINE") + _p(8, layer)
                   + _p(10, _k(p1[0])) + _p(20, _k(p1[1])) + _p(30, _k(p1[2]))
                   + _p(11, _k(p2[0])) + _p(21, _k(p2[1])) + _p(31, _k(p2[2])))

    def face(pts, layer):
        q = list(pts) + [pts[-1]] * (4 - len(pts))
        s = _p(0, "3DFACE") + _p(8, layer)
        for k, pt in enumerate(q[:4]):
            s += _p(10 + k, _k(pt[0])) + _p(20 + k, _k(pt[1])) + _p(30 + k, _k(pt[2]))
        out.append(s)

    def text(p, s, layer, hh=None):
        out.append(_p(0, "TEXT") + _p(8, layer)
                   + _p(10, f"{p[0]:.6f}") + _p(20, f"{p[1]:.6f}") + _p(30, f"{p[2]:.6f}")
                   + _p(40, f"{hh or h:.6f}") + _p(1, s))

    n_line = n_face = 0
    for i, e in enumerate(model.elements):
        n = [int(x) for x in e.nodes]
        # das Seil wie der Fachwerkstab (14.10.2026: RFEM-Seile kommen als Seil
        # an; bis dahin fehlte es hier)
        if e.typ in ("beam", "truss", "seil"):
            line(model.nodes[n[0]], model.nodes[n[1]], "STAEBE")
            n_line += 1
        elif e.typ.startswith("shell"):
            face([model.nodes[x] for x in n], "SCHALEN")
            n_face += 1
    for f in C.solid_faces(model):
        idx = f[0] if isinstance(f, (tuple, list)) and not np.isscalar(f[0]) else f
        try:
            pts = [model.nodes[int(x)] for x in idx]
        except (TypeError, ValueError):
            continue
        if len(pts) >= 3:
            face(pts, "VOLUMEN")
            n_face += 1
    for name, ln in model.lines.items():
        for a, b in zip(ln.nodes[:-1], ln.nodes[1:]):
            line(model.nodes[a], model.nodes[b], E_LINIEN)
    for s in model.supports:
        p = model.nodes[s.node]
        d = h
        for v in ((d, 0, 0), (0, d, 0), (0, 0, d)):
            line(np.asarray(p) - np.asarray(v), np.asarray(p) + np.asarray(v), E_LAGER)
    for name, mem in model.members.items():
        if not mem.elements:
            continue
        e = model.elements[int(mem.elements[0])]
        p = 0.5 * (model.nodes[int(e.nodes[0])] + model.nodes[int(e.nodes[1])])
        text(p, f"{name} {e.sec or ''}".strip(), E_TEXT)
    for lc in model.load_cases.values():
        for nl in lc.nodal_loads:
            p = model.nodes[nl.node]
            text(p, f"{lc.name}", E_LASTEN, h * 0.7)
    out.append(_p(0, "ENDSEC") + _p(0, "EOF"))
    with open(path, "w", encoding="latin-1", errors="replace") as f:
        f.write("".join(out))
    C.say(log, f"DXF geschrieben: {n_line} Linien, {n_face} Flaechen -> {path}")
    C.say(log, "DXF: Die Datei trägt die Geometrie in Metern ($INSUNITS = 6). Lagersymbole, "
               f"Linien und Beschriftung liegen auf Ebenen mit dem Vorsatz {HILFSEBENE}.")
    n_stab = sum(1 for e in model.elements if e.typ in ("truss", "seil"))
    # Aussenflaechen schreibt solid_faces (mesher.surface_facets) nur fuer
    # tet4, tet10 und hex8; die uebrigen Volumenarten (Prismen, Pyramiden,
    # hex20, tetp) fehlen ganz in der Datei (bis zum 11.11.2026 hiess es fuer
    # alle „nur die Außenflächen als 3DFACE“)
    vol = [model.elements[i].typ for i in C.solid_elements(model)]
    n_vol = sum(1 for t in vol if t in _VOLUMEN_MIT_FLAECHEN)
    ohne = sorted({t for t in vol if t not in _VOLUMEN_MIT_FLAECHEN})
    n_vol_fehlt = len(vol) - n_vol
    C.nicht_uebertragen(log, "DXF", [
        (len(model.materials), "Werkstoff", "Werkstoffe"),
        (len(model.sections), "Querschnitt", "Querschnitte"),
        (len(model.shells), "Schalendicke", "Schalendicken"),
        (n_stab, "Stabart Fachwerkstab oder Seil (geht als Linie hinaus)",
         "Stabarten Fachwerkstab oder Seil (gehen als Linien hinaus)"),
        (n_vol, "Volumenelement (nur die Außenflächen als 3DFACE)",
         "Volumenelemente (nur die Außenflächen als 3DFACE)"),
        (n_vol_fehlt, f"Volumenelement der Art {', '.join(ohne)} (fehlt ganz, als 3DFACE "
                      "gehen nur die Außenflächen von tet4, tet10 und hex8 hinaus)",
         f"Volumenelemente der Arten {', '.join(ohne)} (fehlen ganz, als 3DFACE gehen nur "
         "die Außenflächen von tet4, tet10 und hex8 hinaus)"),
        (len(C.gelenkenden(model)), "Stabendgelenk", "Stabendgelenke"),
        (len(model.supports), "Knotenlager (nur als Symbol)", "Knotenlager (nur als Symbol)"),
        (len(model.line_supports), "Linienlager", "Linienlager"),
        (len(model.surface_supports), "Flächenlager", "Flächenlager"),
        (C.lastzahl(model, "nodal_loads"), "Knotenlast (nur der Lastfallname als Text)",
         "Knotenlasten (nur der Lastfallname als Text)"),
        (C.lastzahl(model, "beam_loads"), "Stablast", "Stablasten"),
        (C.lastzahl(model, "face_loads"), "Flächenlast", "Flächenlasten"),
        (C.lastzahl(model, "temp_loads"), "Temperaturlast", "Temperaturlasten"),
        (sum(1 for lc in model.load_cases.values() if np.any(np.asarray(lc.gravity, float))),
         "Lastfall mit Eigengewicht", "Lastfälle mit Eigengewicht"),
        (len(model.combinations), "Kombination", "Kombinationen"),
    ] + C.weiteres(model))
    return path
