"""
Export als STL-Oberflaechennetz (ASCII oder binaer).

Geschrieben werden die Schalenelemente und die Aussenflaechen der
Volumenelemente als Dreiecke - fuer Ansicht, 3D-Druck und CAD.
"""
from __future__ import annotations

import struct

import numpy as np

from ..model import Model
from . import _common as C


def _tris(model: Model) -> list:
    out = list(C.triangles(model))
    for f in C.solid_faces(model):
        idx = f[0] if isinstance(f, (tuple, list)) and not np.isscalar(f[0]) else f
        try:
            n = [int(x) for x in idx]
        except (TypeError, ValueError):
            continue
        if len(n) >= 3:
            out.append((n[0], n[1], n[2]))
        if len(n) == 4:
            out.append((n[0], n[2], n[3]))
    return out


def write_stl(model: Model, path: str, results=None, log: list = None,
              binary: bool = True, scale: float = 1.0, **_) -> str:
    tris = _tris(model)
    if not tris:
        raise ValueError("Das Modell enthaelt keine Flaechen (Schalen oder Volumen).")
    P = np.asarray(model.nodes, float) * float(scale)
    if binary:
        with open(path, "wb") as f:
            f.write(b"Statik3D " + model.name.encode("latin-1", "replace")[:70])
            f.write(b"\x00" * max(0, 80 - 9 - len(model.name)))
            f.seek(80)
            f.write(struct.pack("<I", len(tris)))
            for a, b, c in tris:
                p1, p2, p3 = P[a], P[b], P[c]
                nv = np.cross(p2 - p1, p3 - p1)
                ln = np.linalg.norm(nv)
                nv = nv / ln if ln > 0 else np.zeros(3)
                f.write(struct.pack("<12fH", *nv, *p1, *p2, *p3, 0))
    else:
        z = [f"solid {model.name}"]
        for a, b, c in tris:
            p1, p2, p3 = P[a], P[b], P[c]
            nv = np.cross(p2 - p1, p3 - p1)
            ln = np.linalg.norm(nv)
            nv = nv / ln if ln > 0 else np.zeros(3)
            z.append(f"  facet normal {nv[0]:.6e} {nv[1]:.6e} {nv[2]:.6e}")
            z.append("    outer loop")
            for p in (p1, p2, p3):
                z.append(f"      vertex {p[0]:.6e} {p[1]:.6e} {p[2]:.6e}")
            z.append("    endloop")
            z.append("  endfacet")
        z.append(f"endsolid {model.name}")
        with open(path, "w", encoding="ascii", errors="replace") as f:
            f.write("\n".join(z) + "\n")
    C.say(log, f"STL geschrieben: {len(tris)} Dreiecke -> {path}")
    return path
