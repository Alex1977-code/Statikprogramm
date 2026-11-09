"""Fertige Beispielmodelle (auch aus der GUI ueber das Menue 'Beispiele').

Namen (Paket R2-C1, 06.10.2026, Entscheidung des Anwenders vom 04.10.2026):
Lastfaelle heissen LF<Nr.>, Lastkombinationen LK<Nr.>, und der freie Name von
frueher steht als Bezeichnung daneben - Hallenrahmen: LF1 Eigengewicht, LF2 S,
LF3 W_links, LF4 W_rechts, LF5 Kran; Stauwand: LF1 Eigengewicht, LF2 Wasser,
LF3 Wasser_Wellen; die Kombinationen LK1 ... erzeugt der Generator
(combinations.generate_combinations). Die Rechnung ist bis auf die Namen
dieselbe (tests/test_namen_erzeuger.py, G5). Ergebniskombinationen (EK<Nr.>)
hat keines der eingebauten Beispiele.
"""
from __future__ import annotations

import numpy as np

from .model import Model, Material, Section, ShellProp
from . import mesher


def frame_example(L: float = 6.0, h: float = 4.0, q: float = 15000.0, H: float = 12000.0) -> Model:
    """Zweistieliger Rahmen, 6 m Spannweite, 4 m hoch, mit Dachgleichlast.

    Parameter (Beispielbibliothek): Spannweite L [m], Hoehe h [m], Dachlast
    q [N/m], Horizontallast H [N] am Riegelanfang."""
    m = Model("Rahmen")
    m.case().bezeichnung = "Eigengewicht, Dach, Wind"
    m.add_material(Material("S355", 210e9, 0.3, 7850, fy=355e6))
    m.add_section(Section.i_profile("HEA 200", 0.190, 0.200, 0.0065, 0.010))
    left = mesher.line_of_beams(m, "S355", "HEA 200", (0, 0, 0), (0, 0, h), 4)
    right = mesher.line_of_beams(m, "S355", "HEA 200", (L, 0, 0), (L, 0, h), 4)
    top = mesher.line_of_beams(m, "S355", "HEA 200", (0, 0, h), (L, 0, h), 8)
    mesher.merge_nodes(m)
    lo = mesher.select_nodes(m, zmin=-1e-6, zmax=1e-6)
    for n in lo:
        m.fix(int(n), "all")
    for i, e in enumerate(m.elements):
        p = m.nodes[e.nodes]
        if abs(p[0][2] - h) < 1e-9 and abs(p[1][2] - h) < 1e-9:
            m.load_beam(i, qz=-q)
    # Windlast horizontal am Riegelanfang
    n_corner = mesher.select_nodes(m, xmin=-1e-6, xmax=1e-6, zmin=h - 1e-6)
    for n in n_corner:
        m.load_node(int(n), Fx=H)
    m.set_gravity(-9.81)
    return m


def plate_example(a: float = 3.0, b: float = 2.0, t: float = 0.012, p: float = 5000.0) -> Model:
    """Vierseitig gelagerte Stahlplatte 3 x 2 m, t = 12 mm, Flaechenlast 5 kN/m².

    Parameter: Seiten a, b [m], Dicke t [m], Flaechenlast p [N/m²]; das Netz
    hat etwa 8 Elemente je Meter (bei 3 x 2 m 24 x 16)."""
    m = Model("Platte")
    m.case().bezeichnung = "Flächenlast"
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    tn = f"t = {t * 1000:g} mm"
    m.add_shell_prop(ShellProp(tn, t))
    ids = mesher.grid_plate(m, "S235", tn, a, b, max(2, round(8 * a)), max(2, round(8 * b)), quad=True)
    nx, ny = ids.shape[0] - 1, ids.shape[1] - 1
    for i in range(nx + 1):
        for j in range(ny + 1):
            if i in (0, nx) or j in (0, ny):
                m.fix(int(ids[i, j]), [2])
    m.fix(int(ids[0, 0]), [0, 1])
    m.fix(int(ids[nx, 0]), [1])
    for e in range(len(m.elements)):
        m.load_face(e, -p)
    return m


def solid_example(L: float = 1.0, b: float = 0.3, h: float = 0.4, F: float = 50000.0) -> Model:
    """Volumenmodell einer Konsole 1,0 x 0,3 x 0,4 m mit Endlast.

    Parameter: Laenge L, Breite b, Hoehe h [m], Endlast F [N]; etwa 20
    Elemente je Meter."""
    m = Model("Konsole")
    m.case().bezeichnung = "Endlast"
    m.add_material(Material("S355", 210e9, 0.3, 7850, fy=355e6))
    ids = mesher.grid_box(m, "S355", L, b, h, max(2, round(20 * L)), max(2, round(20 * b)),
                          max(2, round(20 * h)), typ="hex8")
    for j in range(ids.shape[1]):
        for k in range(ids.shape[2]):
            m.fix(int(ids[0, j, k]), [0, 1, 2])
    end = ids[-1, :, -1].ravel()
    for n in end:
        m.load_node(int(n), Fz=-F / len(end))
    return m


def truss_bridge_example(L: float = 15.0, h: float = 2.0, nf: int = 5, F: float = 40000.0) -> Model:
    """Ebener Fachwerktraeger, 5 Felder à 3 m, Nutzlast in den Untergurtknoten.

    Parameter: Laenge L [m], Hoehe h [m], Felder nf, Knotenlast F [N]."""
    m = Model("Fachwerk")
    m.case().bezeichnung = "Nutzlast"
    m.add_material(Material("S355", 210e9, 0.3, 7850, fy=355e6))
    m.add_section(Section.pipe("RO 168/8", 0.1683, 0.008))
    nf = int(nf)
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
        m.load_node(n, Fz=-F)
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
def hall_frame_example(L: float = 15.0, h: float = 6.0, s_k: float = 850.0, e: float = 6.0) -> Model:
    """Hallenrahmen HEB 300 / IPE 500, S355, 15 m Spannweite, 6 m Traufhoehe,
    Lastfaelle G, Schnee, Wind links/rechts (Ausschlussgruppe), automatische
    Kombinationen nach DIN EN 1990, Staebe mit Nachweisparametern.

    Parameter: Spannweite L [m], Traufhoehe h [m], Schnee s_k [N/m²],
    Binderabstand e [m]. Dachaufbau 1 kN/m² und Wind (Druck 0,5, Sog 0,25,
    Dachsog 0,4 kN/m²) wirken ueber den Binderabstand; die Kranlast sitzt bei
    0,4 L."""
    from .combinations import generate_combinations
    m = Model("Hallenrahmen")
    m.meta.update({"projekt": "Beispiel Hallenrahmen", "bauteil": "Zweigelenkrahmen Achse 3"})
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    m.add_section(Section.from_profile("IPE 500"))
    f = e / 6.0
    m.case().category = "G"
    m.case().description = "Eigengewicht + Dachaufbau"
    m.case().bezeichnung = "Eigengewicht"
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
    for i in riegel:
        m.load_beam(i, qz=-6000.0 * f)           # G: 1 kN/m² x e
    m.set_gravity(-9.81)
    from .zahlen import zahl_text
    m.add_load_case("LF2", "S", f"Schnee {zahl_text(s_k / 1000)} kN/m² x {zahl_text(e)} m", nummer=2,
                    bezeichnung="S")
    for i in riegel:
        m.load_beam(i, qz=-s_k * e)
    m.add_load_case("LF3", "W", "Wind von links", exclusive_group="Wind", nummer=3,
                    bezeichnung="W_links")
    for i in range(0, 4):
        m.load_beam(i, qx=3000.0 * f)            # Druck auf linken Stiel
    for i in range(4, 8):
        m.load_beam(i, qx=1500.0 * f)            # Sog rechts
    for i in riegel:
        m.load_beam(i, qz=2400.0 * f)            # Dachsog
    m.add_load_case("LF4", "W", "Wind von rechts", exclusive_group="Wind", nummer=4,
                    bezeichnung="W_rechts")
    for i in range(4, 8):
        m.load_beam(i, qx=-3000.0 * f)
    for i in range(0, 4):
        m.load_beam(i, qx=-1500.0 * f)
    for i in riegel:
        m.load_beam(i, qz=2400.0 * f)
    m.add_load_case("LF5", "Q_K", "Kranbahnlast (Ermuedung)", nummer=5, bezeichnung="Kran")
    xk = 0.4 * L
    m.load_node(int(mesher.select_nodes(m, xmin=xk - 1e-6, xmax=xk + 1e-6, zmin=h - 1e-6)[0]), Fz=-40000.0)
    m.add_fatigue_load("Kranspiele", "LF5", None, 5e5)
    m.active_case = "LF1"
    generate_combinations(m)
    return m


def contact_example(L: float = 6.0, F: float = 30000.0, spalt: float = 0.003) -> Model:
    """Gelagerter Traeger auf Betonsockel: Einfeldtraeger mit Kragarm auf zwei
    einseitigen Lagern - das hintere Lager hebt ab. Zusaetzlich Spaltelement
    als Anschlag unter dem Kragarmende.

    Parameter: Traegerlaenge L [m] (Lager bei 0 und 2/3 L, Last bei 5/6 L),
    Einzellast F [N], Spalt unter dem Kragarmende [m]."""
    m = Model("Kontakt: abhebendes Lager")
    m.case().bezeichnung = "Einzellast"
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 200"))
    ids = mesher.line_of_beams(m, "S235", "IPE 200", (0, 0, 0), (L, 0, 0), 12)
    A, B, C = ids[0], ids[8], ids[12]
    m.fix(A, [0, 1, 3, 5])
    m.fix(B, [1, 2, 3, 5])
    m.add_contact_support(A, (0, 0, 1))
    stop = m.add_node(L, 0, -spalt)
    m.fix(stop, "all")
    m.add_gap_element(C, stop, direction=(0, 0, -1), gap=spalt)
    m.load_node(ids[10], Fz=-F)
    m.add_member("Traeger", list(range(12)))
    return m


def block_friction_example(mu: float = 0.3, N: float = 90000.0, H: float = 20000.0) -> Model:
    """Stahlblock (Volumen) auf starrer Platte mit Reibung mu = 0,3:
    Auflast 90 kN, Horizontalkraft 20 kN -> teilweises Gleiten.

    Parameter: Reibbeiwert mu, Auflast N [N], Horizontalkraft H [N]."""
    m = Model("Kontakt: Block mit Reibung")
    m.case().bezeichnung = "Auflast und Horizontalkraft"
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
    m.add_contact_pair("Block/Platte", bottom, plate, mu=mu)
    for n in top:
        m.load_node(n, Fz=-N / len(top), Fx=H / len(top))
    return m


def gate_example(b: float = 4.0, h: float = 3.0, h_w: float | None = None, t: float = 0.012) -> Model:
    """Stahlwasserbau: Stauwandplatte 4 x 3 m (t = 12 mm) mit horizontalen
    Riegeln (HEB 200), Wasserdruck dreieckfoermig (Stauhoehe 3 m), Lastfaelle
    G und Wasserdruck (Kategorie H), Kombinationen nach DIN 19704 sinngemaess.

    Parameter: Breite b, Hoehe h [m], Stauhoehe h_w [m] (leer: h), Dicke t
    [m]; etwa 4 Elemente je Meter, Riegel bei h/6, h/2 und 5h/6."""
    from .combinations import generate_combinations
    m = Model("Stauwand")
    m.meta.update({"projekt": "Beispiel Stahlwasserbau", "bauteil": "Stauwand / Schuetz"})
    m.add_material(Material.steel("S355"))
    tn = f"t = {t * 1000:g} mm"
    m.add_shell_prop(ShellProp(tn, t))
    m.add_section(Section.from_profile("HEB 200"))
    h_w = h if h_w is None else float(h_w)
    nx, nz = max(2, round(4 * b)), max(6, round(4 * h))
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
                                             "S355", tn))
    # Riegel bei z = 0.5, 1.5, 2.5 m (Knoten der Platte mitbenutzen)
    n_rows = [round(nz * f) for f in (1 / 6, 3 / 6, 5 / 6)]
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
    m.case().bezeichnung = "Eigengewicht"
    m.set_gravity(-9.81)
    from .zahlen import zahl_text
    m.add_load_case("LF2", "H", f"Wasserdruck, Stauhoehe {zahl_text(h_w)} m", nummer=2, bezeichnung="Wasser")
    for e in plate_elems:
        zc = m.nodes[m.elements[e].nodes][:, 2].mean()
        p = 1000.0 * 9.81 * (h_w - zc)          # [Pa]
        if p > 0.0:
            m.load_face(e, p, direction=(0, 1, 0))  # Druck in +y (vom Wasser weg)
    m.add_load_case("LF3", "Q", "Wellenschlag / Windstau (Zusatz)", nummer=3,
                    bezeichnung="Wasser_Wellen")
    for e in plate_elems:
        m.load_face(e, 2000.0, direction=(0, 1, 0))
    m.add_fatigue_load("Stauwechsel", "LF2", None, 2e5)
    m.active_case = "LF1"
    generate_combinations(m)
    return m


EXAMPLES.update({
    "hall": hall_frame_example,
    "contact": contact_example,
    "friction": block_friction_example,
    "gate": gate_example,
})
