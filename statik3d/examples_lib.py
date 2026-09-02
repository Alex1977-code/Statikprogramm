"""Fertige Beispielmodelle (auch aus der GUI ueber das Menue 'Beispiele')."""
from __future__ import annotations

import numpy as np

from .model import Model, Material, Section, ShellProp
from . import mesher


def frame_example() -> Model:
    """Zweistieliger Rahmen, 6 m Spannweite, 4 m hoch, mit Dachgleichlast."""
    m = Model("Rahmen")
    m.add_material(Material("S355", 210e9, 0.3, 7850, fy=355e6))
    m.add_section(Section.i_profile("HEA 200", 0.190, 0.200, 0.0065, 0.010))
    left = mesher.line_of_beams(m, "S355", "HEA 200", (0, 0, 0), (0, 0, 4), 4)
    right = mesher.line_of_beams(m, "S355", "HEA 200", (6, 0, 0), (6, 0, 4), 4)
    top = mesher.line_of_beams(m, "S355", "HEA 200", (0, 0, 4), (6, 0, 4), 8)
    mesher.merge_nodes(m)
    lo = mesher.select_nodes(m, zmin=-1e-6, zmax=1e-6)
    for n in lo:
        m.fix(int(n), "all")
    for i, e in enumerate(m.elements):
        p = m.nodes[e.nodes]
        if abs(p[0][2] - 4) < 1e-9 and abs(p[1][2] - 4) < 1e-9:
            m.load_beam(i, qz=-15000.0)
    # Windlast horizontal am Riegelanfang
    n_corner = mesher.select_nodes(m, xmin=-1e-6, xmax=1e-6, zmin=4 - 1e-6)
    for n in n_corner:
        m.load_node(int(n), Fx=12000.0)
    m.set_gravity(-9.81)
    return m


def plate_example() -> Model:
    """Vierseitig gelagerte Stahlplatte 3 x 2 m, t = 12 mm, Flaechenlast 5 kN/m²."""
    m = Model("Platte")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    m.add_shell_prop(ShellProp("t = 12 mm", 0.012))
    ids = mesher.grid_plate(m, "S235", "t = 12 mm", 3.0, 2.0, 24, 16, quad=True)
    nx, ny = ids.shape[0] - 1, ids.shape[1] - 1
    for i in range(nx + 1):
        for j in range(ny + 1):
            if i in (0, nx) or j in (0, ny):
                m.fix(int(ids[i, j]), [2])
    m.fix(int(ids[0, 0]), [0, 1])
    m.fix(int(ids[nx, 0]), [1])
    for e in range(len(m.elements)):
        m.load_face(e, -5000.0)
    return m


def solid_example() -> Model:
    """Volumenmodell einer Konsole 1,0 x 0,3 x 0,4 m mit Endlast."""
    m = Model("Konsole")
    m.add_material(Material("S355", 210e9, 0.3, 7850, fy=355e6))
    ids = mesher.grid_box(m, "S355", 1.0, 0.3, 0.4, 20, 6, 8, typ="hex8")
    for j in range(ids.shape[1]):
        for k in range(ids.shape[2]):
            m.fix(int(ids[0, j, k]), [0, 1, 2])
    end = ids[-1, :, -1].ravel()
    for n in end:
        m.load_node(int(n), Fz=-50000.0 / len(end))
    return m


def truss_bridge_example() -> Model:
    """Ebener Fachwerktraeger, 5 Felder à 3 m, Nutzlast in den Untergurtknoten."""
    m = Model("Fachwerk")
    m.add_material(Material("S355", 210e9, 0.3, 7850, fy=355e6))
    m.add_section(Section.pipe("RO 168/8", 0.1683, 0.008))
    L, h, nf = 15.0, 2.0, 5
    bot = [m.add_node(i * L / nf, 0, 0) for i in range(nf + 1)]
    top = [m.add_node((i + 0.5) * L / nf, 0, h) for i in range(nf)]
    for i in range(nf):
        m.add_element("truss", [bot[i], bot[i + 1]], "S355", "RO 168/8")
        m.add_element("truss", [bot[i], top[i]], "S355", "RO 168/8")
        m.add_element("truss", [top[i], bot[i + 1]], "S355", "RO 168/8")
        if i < nf - 1:
            m.add_element("truss", [top[i], top[i + 1]], "S355", "RO 168/8")
    m.fix(bot[0], [0, 1, 2])
    m.fix(bot[-1], [1, 2])
    for n in bot[1:-1]:
        m.load_node(n, Fz=-40000.0)
    for n in top:
        m.fix(n, [1])
    return m


EXAMPLES = {
    "frame": frame_example,
    "plate": plate_example,
    "solid": solid_example,
    "truss": truss_bridge_example,
}


def build_example(name: str) -> Model:
    if name not in EXAMPLES:
        raise KeyError(f"Beispiel '{name}' unbekannt. Verfuegbar: {list(EXAMPLES)}")
    return EXAMPLES[name]()
