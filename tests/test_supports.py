"""
Verifikation der nichtlinearen Lager: Knotenlager, Linienlager, Flaechenlager mit
Ausfall bei Zug/Druck, Schlupf, Reibung und Grenzkraft.
Aufruf:  python -m tests.test_supports
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, Section, ShellProp  # noqa: E402
from statik3d import solver, mesher, supports  # noqa: E402

RESULTS = []


def check(name, num, ana, tol, unit=""):
    num, ana = float(num), float(ana)
    err = abs(num - ana) / (abs(ana) if abs(ana) > 1e-12 else 1.0)
    ok = err <= tol
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:52s} num={num: .6e} ana={ana: .6e} "
          f"Abw={err * 100:6.3f}% {unit}")
    return ok


def _bar(L=2.0, A=1e-3, E=210e9):
    """Senkrechter Fachwerkstab von (0,0,0) nach (0,0,L); Knoten 0 fest."""
    m = Model("Stab")
    m.add_material(Material("S", E=E))
    m.add_section(Section("A", A=A, Iy=1e-6, Iz=1e-6, It=1e-6))
    n0 = m.add_node(0, 0, 0)
    n1 = m.add_node(0, 0, L)
    m.add_element("truss", [n0, n1], "S", "A")
    m.fix(n0, "all")
    return m, n1, E * A / L


def test_federlager_mit_schlupf():
    """Federlager (nur Druck) mit Schlupf s unter Last P:
    u = -(P + k s)/(EA/L + k),  Lagerkraft = k |u + s|."""
    L, A, E, k, s, P = 2.0, 1e-3, 210e9, 3e7, 0.0002, 60e3   # freie Stabverformung 0.571 mm > s
    m, n1, ka = _bar(L, A, E)
    m.support(n1, [2], uz=dict(typ="spring", stiffness=k, failure="zug", slip=s))
    m.load_node(n1, Fz=-P)
    r = solver.solve_static(m)
    u = float(r.u[n1, 2])
    u_ana = -(P + k * s) / (ka + k)
    check("Federlager Schlupf: Verschiebung", u, u_ana, 1e-6, "m")
    check("Federlager Schlupf: Lagerkraft", r.contact[0]["Fn"], k * abs(u_ana + s), 1e-6, "N")
    check("Federlager Schlupf: Zustand aktiv", 1.0 if r.contact[0]["status"] != "offen" else 0.0, 1.0, 0)
    check("Federlager Schlupf: Auflagerkraft = Kontaktkraft",
          r.reactions[n1, 2], r.contact[0]["Fn"], 1e-6, "N")
    check("Federlager Schlupf: Gleichgewicht", r.reactions[:, 2].sum(), P, 1e-6, "N")

    # Last kleiner als der Schlupf: Lager wirkt noch nicht -> reiner Stab
    P2 = 1e3
    m2, n1b, _ = _bar(L, A, E)
    m2.support(n1b, [2], uz=dict(typ="spring", stiffness=k, failure="zug", slip=0.02))
    m2.load_node(n1b, Fz=-P2)
    r2 = solver.solve_static(m2)
    check("Schlupf groesser als Weg: Lager offen", r2.contact[0]["Fn"], 0.0, 0)
    check("Schlupf groesser als Weg: Verschiebung", r2.u[n1b, 2], -P2 / ka, 1e-6, "m")


def test_zug_und_druckausfall():
    """Zugausfall: Lager traegt nur Druck. Druckausfall: nur Zug."""
    L, A, E, P = 2.0, 1e-3, 210e9, 40e3
    for last, mode, traegt in ((-P, "zug", True), (+P, "zug", False),
                               (+P, "druck", True), (-P, "druck", False)):
        m, n1, ka = _bar(L, A, E)
        m.support(n1, [2], uz=dict(typ="spring", stiffness=1e9, failure=mode))
        m.load_node(n1, Fz=last)
        r = solver.solve_static(m)
        Fn = r.contact[0]["Fn"]
        richtung = "Druck" if last < 0 else "Zug"
        if traegt:
            check(f"Ausfall bei {mode}: {richtung} wird getragen",
                  1.0 if Fn > 0.5 * P else 0.0, 1.0, 0)
            check(f"Ausfall bei {mode}: {richtung} Verschiebung klein",
                  abs(r.u[n1, 2]) < abs(P / ka), True, 0)
        else:
            check(f"Ausfall bei {mode}: {richtung} faellt aus (F = 0)", Fn, 0.0, 0)
            check(f"Ausfall bei {mode}: {richtung} nur Stab", r.u[n1, 2], last / ka, 1e-6, "m")


def test_grenzkraft():
    """Grenzkraft (plastisch): Lagerkraft bleibt bei 'limit' stehen."""
    L, A, E, P, lim = 2.0, 1e-3, 210e9, 200e3, 50e3
    m, n1, ka = _bar(L, A, E)
    m.support(n1, [2], uz=dict(typ="spring", stiffness=1e9, failure="zug", limit=lim))
    m.load_node(n1, Fz=-P)
    r = solver.solve_static(m)
    check("Grenzkraft: Lagerkraft begrenzt", r.contact[0]["Fn"], lim, 1e-3, "N")
    check("Grenzkraft: Zustand Fliessen", 1.0 if r.contact[0]["status"] == "Fliessen" else 0.0, 1.0, 0)
    check("Grenzkraft: Rest traegt der Stab", r.u[n1, 2], -(P - lim) / ka, 2e-3, "m")
    check("Grenzkraft: Gleichgewicht", r.reactions[:, 2].sum(), P, 1e-3, "N")


def test_reibung_knotenlager():
    """Knotenlager mit Reibung: waagerechte Kraft H gegen mu*N.
    Der Traeger liegt auf zwei Lagern, die nur Druck aufnehmen; waagerecht
    haelt ihn nur die Reibung am linken Lager."""
    def build(H, mu=0.4, N=100e3):
        m = Model("Reibung")
        m.add_material(Material.steel("S235"))
        m.add_section(Section.from_profile("IPE 300"))
        ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (4, 0, 0), 4)
        m.support(ids[0], [2], uz=dict(failure="zug"), ux=dict(mu=mu, mu_ref=2),
                  uy=dict(mu=mu, mu_ref=2))
        m.support(ids[-1], [1, 2], uz=dict(failure="zug"))
        m.fix(ids[0], [3])                      # Torsion halten
        for n in ids:
            m.load_node(n, Fz=-N / len(ids))
        m.load_node(ids[2], Fx=H)
        return m, ids

    mu, N = 0.4, 100e3
    m, ids = build(0.5 * mu * N)                # H = 20 kN < mu N = 40 kN -> Haften
    r = solver.solve_static(m)
    stat = [c["status"] for c in r.contact if c["node"] == ids[0] and c["dof"] == 2]
    Fx = r.contact_forces[ids[0], 0]
    check("Reibung: H < mu N haftet", 1.0 if "Haften" in stat else 0.0, 1.0, 0)
    check("Reibung: Haften, Gleichgewicht x", Fx, -0.5 * mu * N, 1e-3, "N")
    check("Reibung: Summe Fn = N", sum(c["Fn"] for c in r.contact), N, 1e-3, "N")

    m2, ids2 = build(1.5 * mu * N)              # H = 60 kN > mu N -> Gleiten
    r2 = solver.solve_static(m2)
    stat2 = [c["status"] for c in r2.contact if c["node"] == ids2[0] and c["dof"] == 2]
    Fn0 = sum(c["Fn"] for c in r2.contact if c["node"] == ids2[0])
    Ft0 = sum(c["Ft"] for c in r2.contact if c["node"] == ids2[0])
    check("Reibung: H > mu N gleitet", 1.0 if "Gleiten" in stat2 else 0.0, 1.0, 0)
    check("Reibung: Reibkraft = mu Fn", Ft0, mu * Fn0, 2e-2, "N")
    check("Reibung: Warnung Rutschen",
          1.0 if any("rutscht" in w for w in r2.info["contact_log"]) else 0.0, 1.0, 0)


def test_linienlager():
    """Steifer Traeger auf elastischer Bettung k [N/m je m] unter Gleichlast q:
    gleichmaessige Setzung u = -q/k, Summe der Lagerkraefte = q L."""
    L, q, k = 6.0, 20e3, 5e7
    m = Model("Linienlager")
    m.add_material(Material("steif", E=210e12))
    m.add_section(Section("gross", A=1.0, Iy=1.0, Iz=1.0, It=1.0))
    ids = mesher.line_of_beams(m, "steif", "gross", (0, 0, 0), (L, 0, 0), 6)
    m.add_line_support(ids, uz=dict(typ="spring", stiffness=k))
    m.fix(ids[0], [0, 1, 3, 5])
    for e in range(len(m.elements)):
        m.load_beam(e, qz=-q)
    r = solver.solve_static(m)
    check("Linienlager: Setzung u = -q/k", r.u[ids[3], 2], -q / k, 1e-3, "m")
    check("Linienlager: Summe Lagerkraft", -r.reactions[:, 2].sum(), -q * L, 1e-3, "N")
    trib = supports.tributary_lengths(m, ids)
    check("Linienlager: Einflusslaengen = L", sum(trib.values()), L, 1e-12, "m")

    # mit Zugausfall: durchgehend gebetteter Traeger, Einzellast am Ende
    m2 = Model("Linienlager Abheben")
    m2.add_material(Material.steel("S235"))
    m2.add_section(Section.from_profile("IPE 400"))
    ids2 = mesher.line_of_beams(m2, "S235", "IPE 400", (0, 0, 0), (8, 0, 0), 16)
    m2.add_line_support(ids2, uz=dict(typ="spring", stiffness=2e7, failure="zug"))
    m2.fix(ids2[0], [0, 1, 3, 5])
    m2.load_node(ids2[0], Fz=-60e3)            # Last am Ende -> anderes Ende hebt ab
    r2 = solver.solve_static(m2)
    offen = [c for c in r2.contact if c["status"] == "offen"]
    check("Linienlager Zugausfall: Knoten heben ab", 1.0 if offen else 0.0, 1.0, 0)
    check("Linienlager Zugausfall: keine Zugkraft",
          max((c["Fn"] for c in r2.contact), default=0) >= 0
          and all(c["Fn"] >= -1e-6 for c in r2.contact), True, 0)
    check("Linienlager Zugausfall: Gleichgewicht", r2.reactions[:, 2].sum(), 60e3, 1e-3, "N")


def test_flaechenlager():
    """Steife Platte auf Bettung c [N/m^3] unter Flaechenlast p: u = -p/c."""
    lx, ly, p, c = 2.0, 1.0, 50e3, 1e8
    m = Model("Flaechenlager")
    m.add_material(Material("steif", E=210e12))
    m.add_shell_prop(ShellProp("t", 0.2))
    grid = mesher.grid_plate(m, "steif", "t", lx, ly, 4, 2)
    elems = list(range(len(m.elements)))
    m.add_surface_support(elems, uz=dict(typ="spring", stiffness=c))
    m.fix(int(grid[0, 0]), [0, 1, 5])
    m.fix(int(grid[-1, 0]), [1, 5])
    for e in elems:
        m.load_face(e, -p)                      # Flaechenlast nach unten (lokale -z)
    r = solver.solve_static(m)
    mitte = int(grid[2, 1])
    check("Flaechenlager: Setzung u = -p/c", r.u[mitte, 2], -p / c, 5e-3, "m")
    check("Flaechenlager: Summe Lagerkraft", -r.reactions[:, 2].sum(), -p * lx * ly, 1e-2, "N")
    ar = supports.tributary_areas(m, elems)
    check("Flaechenlager: Einflussflaechen = A", sum(ar.values()), lx * ly, 1e-12, "m^2")

    # Bettung mit Zugausfall: aussermittige Last -> Ecke hebt ab
    m2 = Model("Bettung Abheben")
    m2.add_material(Material.steel("S235"))
    m2.add_shell_prop(ShellProp("t", 0.02))
    g2 = mesher.grid_plate(m2, "S235", "t", 2.0, 2.0, 4, 4)
    elems2 = list(range(len(m2.elements)))
    m2.add_surface_support(elems2, uz=dict(typ="spring", stiffness=5e6, failure="zug"))
    m2.fix(int(g2[0, 0]), [0, 1])
    m2.fix(int(g2[-1, 0]), [1])
    m2.load_node(int(g2[-1, -1]), Fz=-40e3)     # Last in einer Ecke
    r2 = solver.solve_static(m2)
    offen = sum(1 for x in r2.contact if x["status"] == "offen")
    check("Bettung Zugausfall: Knoten heben ab", 1.0 if offen > 0 else 0.0, 1.0, 0)
    check("Bettung Zugausfall: Gleichgewicht", r2.reactions[:, 2].sum(), 40e3, 1e-3, "N")


def test_rotationslager_und_zusammenfassung():
    """Ausfall an einem Rotations-FHG und die Lageruebersicht."""
    m = Model("Drehlager")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 200"))
    ids = mesher.line_of_beams(m, "S235", "IPE 200", (0, 0, 0), (3, 0, 0), 3)
    m.fix(ids[0], [0, 1, 2, 3, 5])
    m.support(ids[0], [4], phiy=dict(typ="spring", stiffness=5e5, failure="zug"))
    m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[1], Fz=-10e3)
    r = solver.solve_static(m)
    rot = [c for c in r.contact if c["dof"] == 4]
    check("Rotationslager: Bedingung aufgebaut", 1.0 if rot else 0.0, 1.0, 0)
    check("Rotationslager: keine Kraft in Knotenkraeften",
          abs(r.contact_forces[ids[0]]).sum(), 0.0, 0, "N")
    check("Rotationslager: Gleichgewicht", r.reactions[:, 2].sum(), 10e3, 1e-6, "N")
    txt = supports.summary(m)
    check("Zusammenfassung nennt nichtlineare FHG", 1.0 if "nichtlineare" in txt else 0.0, 1.0, 0)
    print("   " + txt)


def test_federgelenke():
    """Stabendgelenk als Drehfeder: Einfeldtraeger, links elastisch eingespannt.
    M = q L^2/8 / (1 + 3EI/(k L)); k -> 0 Gelenk, k -> unendlich volle Einspannung.
    Die Restabweichung von 0,7 % ist die Schubverformung (Handformel: Bernoulli)."""
    E, L, q = 210e9, 6.0, 10e3
    I = Section.from_profile("IPE 300").Iy

    def build(kphi):
        m = Model("Federgelenk")
        m.add_material(Material("S", E=E))
        m.add_section(Section.from_profile("IPE 300"))
        ids = mesher.line_of_beams(m, "S", "IPE 300", (0, 0, 0), (L, 0, 0), 12)
        m.fix(ids[0], "all")
        m.fix(ids[-1], [1, 2, 3, 5])
        if kphi == "free":
            m.add_hinge("G", end=0, phiy="free")
            m.apply_hinge(0, "G")
        elif kphi is not None:
            m.add_hinge("F", end=0, phiy=kphi)
            m.apply_hinge(0, "F")
        for e in range(len(m.elements)):
            m.load_beam(e, qz=-q)
        return m, ids

    for k in (1e5, 1e6, 1e8):
        m, ids = build(k)
        r = solver.solve_static(m)
        M_ana = q * L ** 2 / 8 / (1 + 3 * E * I / (k * L))
        check(f"Federgelenk k = {k:.0e}: Einspannmoment",
              abs(r.stations(3)[0]["My"][0]), M_ana, 1e-2, "Nm")
    m, ids = build("free")
    r = solver.solve_static(m)
    check("Gelenk: Moment = 0", abs(r.stations(3)[0]["My"][0]) / 1e3, 0.0, 1e-6, "kNm")
    m, ids = build(None)
    r = solver.solve_static(m)
    check("Volle Einspannung: Moment", abs(r.stations(3)[0]["My"][0]), q * L ** 2 / 8, 1e-2, "Nm")
    h = m.add_hinge("H2", end=1, phiy="free", phiz=2e6)
    check("Gelenkbeschreibung", 1.0 if "phiy" in h.describe() and "phiz" in h.describe() else 0.0, 1.0, 0)


def main():
    for t in (test_federlager_mit_schlupf, test_zug_und_druckausfall, test_grenzkraft,
              test_reibung_knotenlager, test_linienlager, test_flaechenlager,
              test_rotationslager_und_zusammenfassung, test_federgelenke):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
