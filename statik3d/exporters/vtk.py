"""
Export nach VTK (.vtu, XML-UnstructuredGrid) fuer ParaView.

Mitgeschrieben werden Verformung, Auflagerreaktionen und - soweit vorhanden -
Stabendkraefte, Schalenschnittgroessen und Volumenspannungen. Damit lassen sich
Ergebnisse in ParaView weiterverarbeiten und mit anderen Rechnungen vergleichen.
"""
from __future__ import annotations

import base64
import zlib

import numpy as np

from ..model import Model
from . import _common as C

#: Statik3D-Element -> (VTK-Zellart, Knotenzahl)
VTK_CELLS = {"beam": (3, 2), "truss": (3, 2), "shell3": (5, 3), "shell4": (9, 4),
             "tet4": (10, 4), "tet10": (24, 10), "hex8": (12, 8)}


def _array(name: str, data: np.ndarray, comps: int = 1) -> str:
    d = np.asarray(data, float).ravel()
    txt = " ".join(f"{v:.6g}" for v in d)
    return (f'        <DataArray type="Float64" Name="{name}" '
            f'NumberOfComponents="{comps}" format="ascii">\n          {txt}\n'
            f'        </DataArray>\n')


def write_vtu(model: Model, path: str, results=None, log: list = None, **_) -> str:
    """Modell (und Ergebnisse) als .vtu schreiben."""
    zellen = [(i, e) for i, e in enumerate(model.elements) if e.typ in VTK_CELLS]
    if not zellen:
        raise ValueError("Das Modell enthaelt keine Elemente.")
    P = np.asarray(model.nodes, float)
    conn, offs, typen = [], [], []
    o = 0
    for _i, e in zellen:
        vt, nn = VTK_CELLS[e.typ]
        n = [int(x) for x in e.nodes][:nn]
        conn.extend(n)
        o += len(n)
        offs.append(o)
        typen.append(vt)
    z = ['<?xml version="1.0"?>',
         '<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">',
         "  <UnstructuredGrid>",
         f'    <Piece NumberOfPoints="{len(P)}" NumberOfCells="{len(zellen)}">']
    z.append("      <Points>")
    z.append(_array("Punkte", P, 3).rstrip("\n"))
    z.append("      </Points>")
    z.append("      <Cells>")
    z.append(f'        <DataArray type="Int64" Name="connectivity" format="ascii">\n'
             f'          {" ".join(str(v) for v in conn)}\n        </DataArray>')
    z.append(f'        <DataArray type="Int64" Name="offsets" format="ascii">\n'
             f'          {" ".join(str(v) for v in offs)}\n        </DataArray>')
    z.append(f'        <DataArray type="UInt8" Name="types" format="ascii">\n'
             f'          {" ".join(str(v) for v in typen)}\n        </DataArray>')
    z.append("      </Cells>")

    punkt = []
    if results is not None and getattr(results, "u", None) is not None:
        u = np.asarray(results.u).reshape(-1, 6)
        punkt.append(_array("Verformung", u[:, :3], 3).rstrip("\n"))
        punkt.append(_array("Verdrehung", u[:, 3:6], 3).rstrip("\n"))
        punkt.append(_array("Verformungsbetrag",
                            np.linalg.norm(u[:, :3], axis=1)).rstrip("\n"))
    if results is not None and getattr(results, "reactions", None) is not None:
        R = np.asarray(results.reactions).reshape(-1, 6)
        punkt.append(_array("Auflagerkraft", R[:, :3], 3).rstrip("\n"))
    if punkt:
        z.append('      <PointData Vectors="Verformung">')
        z.extend(punkt)
        z.append("      </PointData>")

    zelle = []
    mat_idx = {n: i for i, n in enumerate(model.materials)}
    zelle.append(_array("Material", [mat_idx.get(e.mat, -1) for _i, e in zellen]).rstrip("\n"))
    if results is not None and getattr(results, "beam_end", None):
        N = [float(results.beam_end[i][6]) if i in results.beam_end else 0.0
             for i, _e in zellen]
        M = [float(np.abs(results.beam_end[i][[4, 5, 10, 11]]).max())
             if i in results.beam_end else 0.0 for i, _e in zellen]
        zelle.append(_array("Normalkraft", N).rstrip("\n"))
        zelle.append(_array("Moment_max", M).rstrip("\n"))
    if results is not None and getattr(results, "solid_res", None):
        vm = []
        for i, _e in zellen:
            s = results.solid_res.get(i)
            if s is None:
                vm.append(0.0)
                continue
            sx, sy, sz, txy, tyz, tzx = [float(v) for v in np.asarray(s).ravel()[:6]]
            vm.append(float(np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                                    + 3.0 * (txy ** 2 + tyz ** 2 + tzx ** 2))))
        zelle.append(_array("Vergleichsspannung", vm).rstrip("\n"))
    if zelle:
        z.append("      <CellData>")
        z.extend(zelle)
        z.append("      </CellData>")

    z += ["    </Piece>", "  </UnstructuredGrid>", "</VTKFile>"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(z) + "\n")
    C.say(log, f"VTK geschrieben: {len(P)} Knoten, {len(zellen)} Zellen -> {path}")
    return path
