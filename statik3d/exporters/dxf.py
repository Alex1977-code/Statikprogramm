"""
Export nach AutoCAD DXF (ASCII, R12-vertraeglich).

Staebe werden zu LINE, Schalen zu 3DFACE, Aussenflaechen der Volumen ebenso;
Knoten zu POINT. Lager, Lasten und Stabnamen kommen auf eigene Layer, damit
sie sich im CAD getrennt schalten lassen.

    from statik3d.exporters.dxf import write_dxf
    write_dxf(m, "modell.dxf")
"""
from __future__ import annotations

import numpy as np

from ..model import Model
from . import _common as C

#: Layer -> Farbnummer (AutoCAD Color Index)
LAYERS = {"STAEBE": 7, "SCHALEN": 5, "VOLUMEN": 8, "KNOTEN": 9,
          "LAGER": 1, "LASTEN": 2, "BESCHRIFTUNG": 3, "LINIEN": 4}


def _p(code: int, value) -> str:
    return f"{code:3d}\n{value}\n"


def write_dxf(model: Model, path: str, results=None, log: list = None,
              text_height: float = None, **_) -> str:
    """Modell als DXF schreiben. Rueckgabe: Pfad."""
    h = text_height or max(model.characteristic_size() * 0.02, 1e-3)
    out = []
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
                   + _p(10, f"{p1[0]:.6f}") + _p(20, f"{p1[1]:.6f}") + _p(30, f"{p1[2]:.6f}")
                   + _p(11, f"{p2[0]:.6f}") + _p(21, f"{p2[1]:.6f}") + _p(31, f"{p2[2]:.6f}"))

    def face(pts, layer):
        q = list(pts) + [pts[-1]] * (4 - len(pts))
        s = _p(0, "3DFACE") + _p(8, layer)
        for k, pt in enumerate(q[:4]):
            s += _p(10 + k, f"{pt[0]:.6f}") + _p(20 + k, f"{pt[1]:.6f}") \
                 + _p(30 + k, f"{pt[2]:.6f}")
        out.append(s)

    def text(p, s, layer, hh=None):
        out.append(_p(0, "TEXT") + _p(8, layer)
                   + _p(10, f"{p[0]:.6f}") + _p(20, f"{p[1]:.6f}") + _p(30, f"{p[2]:.6f}")
                   + _p(40, f"{hh or h:.6f}") + _p(1, s))

    n_line = n_face = 0
    for i, e in enumerate(model.elements):
        n = [int(x) for x in e.nodes]
        if e.typ in ("beam", "truss"):
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
            line(model.nodes[a], model.nodes[b], "LINIEN")
    for s in model.supports:
        p = model.nodes[s.node]
        d = h
        for v in ((d, 0, 0), (0, d, 0), (0, 0, d)):
            line(np.asarray(p) - np.asarray(v), np.asarray(p) + np.asarray(v), "LAGER")
    for name, mem in model.members.items():
        if not mem.elements:
            continue
        e = model.elements[int(mem.elements[0])]
        p = 0.5 * (model.nodes[int(e.nodes[0])] + model.nodes[int(e.nodes[1])])
        text(p, f"{name} {e.sec or ''}".strip(), "BESCHRIFTUNG")
    for lc in model.load_cases.values():
        for nl in lc.nodal_loads:
            p = model.nodes[nl.node]
            text(p, f"{lc.name}", "LASTEN", h * 0.7)
    out.append(_p(0, "ENDSEC") + _p(0, "EOF"))
    with open(path, "w", encoding="latin-1", errors="replace") as f:
        f.write("".join(out))
    C.say(log, f"DXF geschrieben: {n_line} Linien, {n_face} Flaechen -> {path}")
    return path
