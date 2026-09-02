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


# --------------------------------------------------------------------------
# Erweiterte Beispiele: Lastfaelle/Kombinationen, EC3, Kontakt, Stahlwasserbau
# --------------------------------------------------------------------------
def hall_frame_example() -> Model:
    """Hallenrahmen HEB 300 / IPE 500, S355, 15 m Spannweite, 6 m Traufhoehe,
    Lastfaelle G, Schnee, Wind links/rechts (Ausschlussgruppe), automatische
    Kombinationen nach DIN EN 1990, Staebe mit Nachweisparametern."""
    from .combinations import generate_combinations
    m = Model("Hallenrahmen")
    m.meta.update({"projekt": "Beispiel Hallenrahmen", "bauteil": "Zweigelenkrahmen Achse 3"})
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    m.add_section(Section.from_profile("IPE 500"))
    L, h = 15.0, 6.0
    m.case().category = "G"
    m.case().description = "Eigengewicht + Dachaufbau"
    left = mesher.line_of_beams(m, "S355", "HEB 300", (0, 0, 0), (0, 0, h), 4)
    right = mesher.line_of_beams(m, "S355", "HEB 300", (L, 0, 0), (L, 0, h), 4)
    top = mesher.line_of_beams(m, "S355", "IPE 500", (0, 0, h), (L, 0, h), 10)
    mesher.merge_nodes(m)
    m.add_member("Stiel links", list(range(0, 4)), beta_y=2.0, beta_z=1.0, L_LT=h)
    m.add_member("Stiel rechts", list(range(4, 8)), beta_y=2.0, beta_z=1.0, L_LT=h)
    m.add_member("Riegel", list(range(8, 18)), beta_y=1.0, beta_z=0.25, L_LT=5.0,
                 detail_category=80e6)
    foot = mesher.select_nodes(m, zmin=-1e-6, zmax=1e-6)
    for n in foot:
        m.fix(int(n), [0, 1, 2, 3, 5])           # Fussgelenke (Drehung um y frei)
    # Halterung aus der Ebene (y) an allen Knoten (ebener Rahmen)
    for n in range(m.nn):
        m.fix(n, [1, 3])
    riegel = list(range(8, 18))
    for e in riegel:
        m.load_beam(e, qz=-6000.0)               # G: 6 kN/m
    m.set_gravity(-9.81)
    m.add_load_case("S", "S", "Schnee 0,85 kN/m² x 6 m")
    for e in riegel:
        m.load_beam(e, qz=-5100.0)
    m.add_load_case("W_links", "W", "Wind von links", exclusive_group="Wind")
    for e in range(0, 4):
        m.load_beam(e, qx=3000.0)                # Druck auf linken Stiel
    for e in range(4, 8):
        m.load_beam(e, qx=1500.0)                # Sog rechts
    for e in riegel:
        m.load_beam(e, qz=2400.0)                # Dachsog
    m.add_load_case("W_rechts", "W", "Wind von rechts", exclusive_group="Wind")
    for e in range(4, 8):
        m.load_beam(e, qx=-3000.0)
    for e in range(0, 4):
        m.load_beam(e, qx=-1500.0)
    for e in riegel:
        m.load_beam(e, qz=2400.0)
    m.add_load_case("Kran", "Q_K", "Kranbahnlast (Ermuedung)")
    m.load_node(int(mesher.select_nodes(m, xmin=6 - 1e-6, xmax=6 + 1e-6, zmin=h - 1e-6)[0]), Fz=-40000.0)
    m.add_fatigue_load("Kranspiele", "Kran", None, 5e5)
    m.active_case = "LF1"
    generate_combinations(m)
    return m


def contact_example() -> Model:
    """Gelagerter Traeger auf Betonsockel: Einfeldtraeger mit Kragarm auf zwei
    einseitigen Lagern - das hintere Lager hebt ab. Zusaetzlich Spaltelement
    als Anschlag unter dem Kragarmende."""
    m = Model("Kontakt: abhebendes Lager")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 200"))
    ids = mesher.line_of_beams(m, "S235", "IPE 200", (0, 0, 0), (6, 0, 0), 12)
    A, B, C = ids[0], ids[8], ids[12]
    m.fix(A, [0, 1, 3, 5])
    m.fix(B, [1, 2, 3, 5])
    m.add_contact_support(A, (0, 0, 1))
    stop = m.add_node(6.0, 0, -0.003)
    m.fix(stop, "all")
    m.add_gap_element(C, stop, direction=(0, 0, -1), gap=0.003)
    m.load_node(ids[10], Fz=-30000.0)
    m.add_member("Traeger", list(range(12)))
    return m


def block_friction_example() -> Model:
    """Stahlblock (Volumen) auf starrer Platte mit Reibung mu = 0,3:
    Auflast 90 kN, Horizontalkraft 20 kN -> teilweises Gleiten."""
    m = Model("Kontakt: Block mit Reibung")
    m.add_material(Material.steel("S235"))
    m.add_material(Material("Starr", E=210e12))
    m.add_shell_prop(ShellProp("t = 50 mm", 0.05))
    pl = mesher.grid_plate(m, "Starr", "t = 50 mm", 1.0, 1.0, 2, 2, origin=(-0.5, -0.5, 0))
    for n in pl.ravel():
        m.fix(int(n), "all")
    plate = list(range(len(m.elements)))
    box = mesher.grid_box(m, "S235", 0.4, 0.4, 0.4, 4, 4, 4, origin=(-0.2, -0.2, 0.0))
    bottom = [int(n) for n in box[:, :, 0].ravel()]
    top = [int(n) for n in box[:, :, -1].ravel()]
    m.add_contact_pair("Block/Platte", bottom, plate, mu=0.3)
    for n in top:
        m.load_node(n, Fz=-90000.0 / len(top), Fx=20000.0 / len(top))
    return m


def gate_example() -> Model:
    """Stahlwasserbau: Stauwandplatte 4 x 3 m (t = 12 mm) mit horizontalen
    Riegeln (HEB 200), Wasserdruck dreieckfoermig (Stauhoehe 3 m), Lastfaelle
    G und Wasserdruck (Kategorie H), Kombinationen nach DIN 19704 sinngemaess."""
    from .combinations import generate_combinations
    m = Model("Stauwand")
    m.meta.update({"projekt": "Beispiel Stahlwasserbau", "bauteil": "Stauwand / Schuetz"})
    m.add_material(Material.steel("S355"))
    m.add_shell_prop(ShellProp("t = 12 mm", 0.012))
    m.add_section(Section.from_profile("HEB 200"))
    b, h = 4.0, 3.0
    nx, nz = 16, 12
    # Platte in der x-z-Ebene (y = 0), Wasser auf der -y-Seite
    ids = np.zeros((nx + 1, nz + 1), dtype=int)
    for i in range(nx + 1):
        for k in range(nz + 1):
            ids[i, k] = m.add_node(i * b / nx, 0.0, k * h / nz)
    plate_elems = []
    for i in range(nx):
        for k in range(nz):
            plate_elems.append(m.add_element("shell4", [ids[i, k], ids[i + 1, k],
                                                        ids[i + 1, k + 1], ids[i, k + 1]],
                                             "S355", "t = 12 mm"))
    # Riegel bei z = 0.5, 1.5, 2.5 m (Knoten der Platte mitbenutzen)
    n_rows = [2, 6, 10]
    e0 = len(m.elements)
    for r, k in enumerate(n_rows):
        for i in range(nx):
            m.add_element("beam", [ids[i, k], ids[i + 1, k]], "S355", "HEB 200")
        m.add_member(f"Riegel {r+1}", list(range(e0 + r * nx, e0 + (r + 1) * nx)),
                     beta_y=1.0, beta_z=1.0, detail_category=71e6)
    # Lagerung: seitliche Raender (Auflager in den Nischen), unterer Rand
    for k in range(nz + 1):
        m.fix(int(ids[0, k]), [0, 1, 2])
        m.fix(int(ids[nx, k]), [0, 1, 2])
    for i in range(nx + 1):
        m.fix(int(ids[i, 0]), [1, 2])
    m.case().category = "G"
    m.set_gravity(-9.81)
    m.add_load_case("Wasser", "H", "Wasserdruck, Stauhoehe 3 m")
    for e in plate_elems:
        zc = m.nodes[m.elements[e].nodes][:, 2].mean()
        p = 1000.0 * 9.81 * (h - zc)            # [Pa]
        m.load_face(e, p, direction=(0, 1, 0))  # Druck in +y (vom Wasser weg)
    m.add_load_case("Wasser_Wellen", "Q", "Wellenschlag / Windstau (Zusatz)")
    for e in plate_elems:
        m.load_face(e, 2000.0, direction=(0, 1, 0))
    m.add_fatigue_load("Stauwechsel", "Wasser", None, 2e5)
    m.active_case = "LF1"
    generate_combinations(m)
    return m


EXAMPLES.update({
    "hall": hall_frame_example,
    "contact": contact_example,
    "friction": block_friction_example,
    "gate": gate_example,
})
