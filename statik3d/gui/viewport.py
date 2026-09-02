"""Darstellung des Modells und der Ergebnisse im 3D-Viewport (pyvista)."""
from __future__ import annotations

import numpy as np
import pyvista as pv

from ..model import Model, NDOF
from ..elements import beam3d as bm
from .. import mesher

VTK_LINE, VTK_TRI, VTK_QUAD, VTK_TETRA, VTK_HEX, VTK_TET10 = 3, 5, 9, 10, 12, 24

CELL_MAP = {
    "beam": (VTK_LINE, 2), "truss": (VTK_LINE, 2),
    "shell3": (VTK_TRI, 3), "shell4": (VTK_QUAD, 4),
    "tet4": (VTK_TETRA, 4), "tet10": (VTK_TET10, 10), "hex8": (VTK_HEX, 8),
}

STATUS_COLOR = {"offen": "#9e9e9e", "Kontakt": "#1565c0", "Haften": "#2e7d32", "Gleiten": "#e65100"}


def to_grid(model: Model) -> pv.UnstructuredGrid:
    cells, types = [], []
    for e in model.elements:
        ct, n = CELL_MAP[e.typ]
        cells.append(n)
        cells.extend(e.nodes[:n])
        types.append(ct)
    if not cells:
        return pv.UnstructuredGrid()
    return pv.UnstructuredGrid(np.array(cells), np.array(types),
                               np.asarray(model.nodes, float))


def util_colors(values: np.ndarray):
    """Farbskala Ausnutzung: gruen -> gelb -> rot (>1 dunkelrot)."""
    return "RdYlGn_r"


def add_supports(plotter, model: Model, size: float):
    if not model.supports and not model.contact_supports:
        return
    d = 0.012 * size
    pts = model.nodes[[s.node for s in model.supports]] if model.supports else np.zeros((0, 3))
    if len(pts):
        plotter.add_mesh(pv.PolyData(pts).glyph(
            geom=pv.Cone(direction=(0, 0, 1), height=2 * d, radius=d),
            scale=False, orient=False), color="#207020", name="supports")
    if model.contact_supports:
        pts = model.nodes[[c.node for c in model.contact_supports]]
        plotter.add_mesh(pv.PolyData(pts).glyph(
            geom=pv.Cone(direction=(0, 0, 1), height=2 * d, radius=d),
            scale=False, orient=False), color="#c8a000", name="csupports")


def add_loads(plotter, model: Model, case, size: float):
    """Knotenlasten (Pfeile) und Streckenlasten (Pfeilreihen) eines Lastfalls."""
    pts, vec = [], []
    for l in case.nodal_loads:
        f = np.asarray(l.F[:3], float)
        if np.any(f):
            pts.append(model.nodes[l.node])
            vec.append(f)
    for bl in case.beam_loads:
        e = model.elements[bl.elem]
        X = model.nodes[e.nodes]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        q1 = np.asarray(bl.q, float)
        q2 = np.asarray(bl.q2, float) if bl.q2 is not None else q1
        if bl.system == "local":
            q1, q2 = T3.T @ q1, T3.T @ q2
        for t in np.linspace(0.1, 0.9, 4):
            q = (1 - t) * q1 + t * q2
            if np.any(q):
                pts.append(X[0] + t * (X[1] - X[0]))
                vec.append(q)
    if not pts:
        return
    pd = pv.PolyData(np.array(pts))
    v = np.array(vec, float)
    v = v / (np.abs(v).max() or 1.0) * 0.06 * size
    # Pfeile zeigen auf den Angriffspunkt: Startpunkt = Punkt - Vektor
    pd.points = pd.points - v
    pd["v"] = v
    plotter.add_mesh(pd.glyph(orient="v", scale="v", factor=1.0), color="#c02020", name="loads")


def add_contact_markers(plotter, model: Model, contact: list, size: float):
    if not contact:
        return
    for status, color in STATUS_COLOR.items():
        nodes = [c["node"] for c in contact if c["status"] == status]
        if nodes:
            plotter.add_points(model.nodes[nodes], color=color, point_size=12,
                               render_points_as_spheres=True, name=f"contact_{status}")


def beam_diagram(model: Model, res, quantity: str, scale: float, n: int = 9):
    """Schnittgroessenverlauf als Polylinien (PolyData) mit Skalarwerten."""
    st = res.stations(n) if hasattr(res, "stations") else None
    pts, lines, vals = [], [], []
    base = 0
    for i, e in enumerate(model.elements):
        if e.typ not in ("beam", "truss"):
            continue
        X = model.nodes[e.nodes]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        if st is not None:
            if i not in st:
                continue
            x = st[i]["x"]
            v = st[i][quantity]
        else:   # Envelope: max/min
            d = res.beam.get(i)
            if d is None:
                continue
            x = d["x"]
            v = np.where(np.abs(d[quantity][1]) >= np.abs(d[quantity][0]),
                         d[quantity][1], d[quantity][0])
        # Richtung: My, Vz, N in lokale z; Mz, Vy in lokale y; Mt in z
        direction = T3[1] if quantity in ("Mz", "Vy") else T3[2]
        sign = -1.0 if quantity in ("My",) else 1.0     # Momente auf der Zugseite antragen
        P0 = X[0] + np.outer(x, T3[0])
        P1 = P0 + np.outer(sign * v * scale, direction)
        k = len(x)
        for j in range(k):
            pts.append(P0[j]); pts.append(P1[j])
            lines.extend([2, base + 2 * j, base + 2 * j + 1])
            vals.extend([v[j], v[j]])
        for j in range(k - 1):
            lines.extend([2, base + 2 * j + 1, base + 2 * j + 3])
        base += 2 * k
    if not pts:
        return None
    pd = pv.PolyData(np.array(pts), lines=np.array(lines))
    pd["wert"] = np.array(vals)
    return pd


def diagram_scale(model: Model, res, quantity: str, n: int = 9) -> float:
    st = res.stations(n) if hasattr(res, "stations") else None
    vmax = 0.0
    if st is not None:
        for d in st.values():
            vmax = max(vmax, float(np.abs(d[quantity]).max()))
    else:
        for d in res.beam.values():
            vmax = max(vmax, float(np.abs(d[quantity][0]).max()), float(np.abs(d[quantity][1]).max()))
    if vmax <= 0:
        return 0.0
    return 0.08 * model.characteristic_size() / vmax


def result_field(model: Model, res, field: str, util: dict = None):
    """(Knotenskalare oder None, Zellskalare oder None, Name)."""
    nn = model.nn
    if field.startswith("|u|"):
        u = res.u if hasattr(res, "u") and res.u is not None else None
        if u is None and hasattr(res, "u_max"):
            return getattr(res, "umag_max") * 1000, None, "|u| max [mm]"
        return np.linalg.norm(u[:, :3], axis=1) * 1000, None, "|u| [mm]"
    if field in ("ux", "uy", "uz"):
        k = "xyz".index(field[1])
        if hasattr(res, "u") and res.u is not None:
            return res.u[:, k] * 1000, None, field + " [mm]"
        return np.where(np.abs(res.u_max[:, k]) > np.abs(res.u_min[:, k]),
                        res.u_max[:, k], res.u_min[:, k]) * 1000, None, field + " extrem [mm]"
    if field.startswith("Vergleich"):
        if hasattr(res, "node_vm_max"):
            return np.nan_to_num(res.node_vm_max) / 1e6, None, "σv max [MPa]"
        return np.nan_to_num(res.node_vm) / 1e6, None, "σv [MPa]"
    if field.startswith("Ausnutzung") and util:
        c = np.full(len(model.elements), np.nan)
        for i, v in util.items():
            c[i] = v
        return None, c, "Ausnutzung [-]"
    if field.startswith("Ausnutzung"):
        if hasattr(res, "util"):
            c = np.full(len(model.elements), np.nan)
            for i, v in res.util.items():
                if v is not None:
                    c[i] = v
            return None, c, "Ausnutzung elastisch [-]"
        c = np.full(len(model.elements), np.nan)
        for i, d in res.beam_forces.items():
            if d["util"] is not None:
                c[i] = d["util"]
        return None, c, "Ausnutzung elastisch [-]"
    return None, None, ""


def displacement_of(res):
    if hasattr(res, "u") and res.u is not None:
        return res.u
    if hasattr(res, "u_max"):
        return np.where(np.abs(res.u_max) > np.abs(res.u_min), res.u_max, res.u_min)
    return None
