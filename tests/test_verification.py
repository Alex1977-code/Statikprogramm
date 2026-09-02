"""
Verifikation gegen analytische Loesungen.
Aufruf:  python -m tests.test_verification
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material, Section, ShellProp
from statik3d import solver

RESULTS = []


def check(name, num, ana, tol):
    err = abs(num - ana) / abs(ana) if ana else abs(num)
    ok = err <= tol
    RESULTS.append((name, num, ana, err, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:44s} num={num: .6e} "
          f"ana={ana: .6e} Abw={err*100:6.2f}%")
    return ok


# --------------------------------------------------------------------------
def t_cantilever_beam():
    L, F = 5.0, 1000.0
    m = Model()
    m.add_material(Material("S235", E=210e9, nu=0.3, rho=7850))
    sec = m.add_section(Section.rectangle("R", 0.1, 0.2))
    ne = 4
    for i in range(ne + 1):
        m.add_node(i * L / ne, 0, 0)
    for i in range(ne):
        m.add_element("beam", [i, i + 1], "S235", "R")
    m.fix(0, "all")
    m.load_node(ne, Fz=-F)
    r = solver.solve_static(m)
    w = -r.u[ne, 2]
    G = 210e9 / (2 * 1.3)
    ana = F * L ** 3 / (3 * 210e9 * sec.Iy) + F * L / (G * sec.Asz)
    check("Kragarm Einzellast (Timoshenko)", w, ana, 1e-6)
    Mmax = max(abs(r.beam_forces[0]["My"][0]), abs(r.beam_forces[0]["My"][1]))
    check("Kragarm Einspannmoment", Mmax, F * L, 1e-6)
    check("Kragarm Auflagerkraft Fz", r.reactions[0, 2], F, 1e-6)


def t_simply_supported_udl():
    L, q = 6.0, 10000.0
    m = Model()
    m.add_material(Material("S235"))
    sec = m.add_section(Section.rectangle("R", 0.2, 0.4))
    ne = 8
    for i in range(ne + 1):
        m.add_node(i * L / ne, 0, 0)
    for i in range(ne):
        e = m.add_element("beam", [i, i + 1], "S235", "R")
        m.load_beam(e, qz=-q)
    m.fix(0, [0, 1, 2, 3])
    m.fix(ne, [1, 2, 3])
    r = solver.solve_static(m)
    w = -r.u[ne // 2, 2]
    G = 210e9 / (2 * 1.3)
    ana = (5 * q * L ** 4 / (384 * 210e9 * sec.Iy)
           + q * L ** 2 / (8 * G * sec.Asz))
    check("Einfeldtraeger Gleichlast (Timoshenko)", w, ana, 5e-3)
    check("Einfeldtraeger Auflagerkraft", r.reactions[0, 2], q * L / 2, 1e-6)
    Mf = max(abs(r.beam_forces[ne // 2 - 1]["My"][1]),
             abs(r.beam_forces[ne // 2]["My"][0]))
    check("Einfeldtraeger Feldmoment", Mf, q * L ** 2 / 8, 5e-3)


def t_frame_3d():
    """Raeumlicher Kragarm mit Torsion: Endverdrehung phi = M*L/(G*It)."""
    L, Mt = 3.0, 5000.0
    m = Model()
    m.add_material(Material("S235"))
    sec = m.add_section(Section.circle("C", 0.1))
    m.add_node(0, 0, 0); m.add_node(L, 0, 0)
    m.add_element("beam", [0, 1], "S235", "C")
    m.fix(0, "all")
    m.load_node(1, Mx=Mt)
    r = solver.solve_static(m)
    G = 210e9 / (2 * 1.3)
    check("Kragarm Torsion (Verdrehwinkel)", r.u[1, 3], Mt * L / (G * sec.It), 1e-6)


def t_truss():
    """Zweistab-Fachwerk, symmetrisch, Vertikallast in der Spitze."""
    h, b, F = 3.0, 4.0, 20000.0
    m = Model()
    m.add_material(Material("S235"))
    m.add_section(Section("A", A=1e-3))
    m.add_node(-b, 0, 0); m.add_node(b, 0, 0); m.add_node(0, 0, -h)
    m.add_element("truss", [0, 2], "S235", "A")
    m.add_element("truss", [1, 2], "S235", "A")
    m.fix(0, "all"); m.fix(1, "all")
    m.fix(2, [1])
    m.load_node(2, Fz=-F)
    r = solver.solve_static(m)
    Lst = np.hypot(b, h)
    N = F / 2 * Lst / h            # Druckkraft je Stab
    check("Fachwerk Stabkraft", abs(r.beam_forces[0]["N"][0]), N, 1e-6)
    delta = N * Lst / (210e9 * 1e-3) * Lst / h
    check("Fachwerk Knotenverschiebung", abs(r.u[2, 2]), delta, 1e-6)


def t_euler_buckling():
    L = 4.0
    m = Model()
    m.add_material(Material("S235"))
    sec = m.add_section(Section.circle("C", 0.06))
    ne = 10
    for i in range(ne + 1):
        m.add_node(0, 0, i * L / ne)
    for i in range(ne):
        m.add_element("beam", [i, i + 1], "S235", "C")
    m.fix(0, [0, 1, 2, 5])             # Fusspunkt gelenkig, Torsion gehalten
    m.fix(ne, [0, 1, 5])               # Kopf gehalten, vertikal frei
    m.load_node(ne, Fz=-1000.0)
    r = solver.solve_buckling(m, nmodes=3)
    Ncr = r.buckling_factors[0] * 1000.0
    ana = np.pi ** 2 * 210e9 * sec.Iy / L ** 2
    check("Eulerknicken Fall 2 (Ncr)", Ncr, ana, 5e-3)


def t_modal_cantilever():
    L = 2.0
    m = Model()
    m.add_material(Material("S235", rho=7850))
    sec = m.add_section(Section.rectangle("R", 0.05, 0.05))
    ne = 12
    for i in range(ne + 1):
        m.add_node(i * L / ne, 0, 0)
    for i in range(ne):
        m.add_element("beam", [i, i + 1], "S235", "R")
    m.fix(0, "all")
    r = solver.solve_modal(m, nmodes=4)
    ana = (1.875104 ** 2) / (2 * np.pi) * np.sqrt(
        210e9 * sec.Iy / (7850 * sec.A * L ** 4))
    check("Kragarm 1. Eigenfrequenz", r.freqs[0], ana, 5e-3)


# --------------------------------------------------------------------------
def _plate_mesh(a, b, nx, ny, m, mat, prop, quad=False):
    ids = np.zeros((nx + 1, ny + 1), dtype=int)
    for i in range(nx + 1):
        for j in range(ny + 1):
            ids[i, j] = m.add_node(i * a / nx, j * b / ny, 0.0)
    for i in range(nx):
        for j in range(ny):
            n1, n2, n3, n4 = ids[i, j], ids[i + 1, j], ids[i + 1, j + 1], ids[i, j + 1]
            if quad:
                m.add_element("shell4", [n1, n2, n3, n4], mat, prop)
            else:
                m.add_element("shell3", [n1, n2, n3], mat, prop)
                m.add_element("shell3", [n1, n3, n4], mat, prop)
    return ids


def t_plate_ss(quad=False):
    """Allseitig gelenkig gelagerte Quadratplatte, Gleichlast.
    w_max = 0.00406 * q a^4 / D  (Navier)."""
    a = 2.0; t = 0.02; q = 10000.0
    E, nu = 210e9, 0.3
    m = Model()
    m.add_material(Material("S", E=E, nu=nu))
    m.add_shell_prop(ShellProp("t20", t))
    n = 12
    ids = _plate_mesh(a, a, n, n, m, "S", "t20", quad)
    for i in range(n + 1):
        for j in range(n + 1):
            if i in (0, n) or j in (0, n):
                m.fix(int(ids[i, j]), [2])
    m.fix(int(ids[0, 0]), [0, 1])
    m.fix(int(ids[n, 0]), [1])
    for e in range(len(m.elements)):
        m.load_face(e, -q)
    r = solver.solve_static(m)
    w = -r.u[ids[n // 2, n // 2], 2]
    D = E * t ** 3 / (12 * (1 - nu ** 2))
    ana = 0.00406 * q * a ** 4 / D
    check(f"Platte 4-seitig gelenkig ({'quad' if quad else 'tri'})", w, ana, 0.03)


def t_plate_cantilever():
    """Kragplatte unter Endlast, verhaelt sich wie Balken der Breite b."""
    L, b, t = 2.0, 0.5, 0.01
    E, nu = 210e9, 0.0          # nu=0 -> exakter Balkenvergleich
    F = 500.0
    m = Model()
    m.add_material(Material("S", E=E, nu=nu))
    m.add_shell_prop(ShellProp("t", t))
    nx, ny = 16, 4
    ids = _plate_mesh(L, b, nx, ny, m, "S", "t")
    for j in range(ny + 1):
        m.fix(int(ids[0, j]), "all")
    for j in range(ny + 1):
        f = F / ny if 0 < j < ny else F / (2 * ny)
        m.load_node(int(ids[nx, j]), Fz=-f)
    r = solver.solve_static(m)
    w = -r.u[ids[nx, ny // 2], 2]
    I = b * t ** 3 / 12
    ana = F * L ** 3 / (3 * E * I)
    check("Kragplatte Endlast (Durchbiegung)", w, ana, 0.02)


def t_membrane():
    """Scheibe unter reinem Zug: sigma = F/A, u = sigma*L/E."""
    L, b, t = 2.0, 0.5, 0.01
    E = 210e9; F = 100000.0
    m = Model()
    m.add_material(Material("S", E=E, nu=0.3))
    m.add_shell_prop(ShellProp("t", t))
    nx, ny = 8, 4
    ids = _plate_mesh(L, b, nx, ny, m, "S", "t")
    for j in range(ny + 1):
        m.fix(int(ids[0, j]), [0, 2, 3, 4, 5])
    m.fix(int(ids[0, 0]), [1])
    for j in range(ny + 1):
        f = F / ny if 0 < j < ny else F / (2 * ny)
        m.load_node(int(ids[nx, j]), Fx=f)
    r = solver.solve_static(m)
    u = r.u[ids[nx, ny // 2], 0]
    ana = F / (b * t) * L / E
    check("Scheibe Zug (Verlaengerung)", u, ana, 1e-3)
    sig = r.shell_stress[0]["sig_top"][0]
    check("Scheibe Zug (Normalspannung)", sig, F / (b * t), 1e-3)


# --------------------------------------------------------------------------
def _box_mesh(m, mat, L, b, h, nx, ny, nz, typ="hex8"):
    ids = np.zeros((nx + 1, ny + 1, nz + 1), dtype=int)
    for i in range(nx + 1):
        for j in range(ny + 1):
            for k in range(nz + 1):
                ids[i, j, k] = m.add_node(i * L / nx, j * b / ny, k * h / nz)
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                c = [ids[i, j, k], ids[i + 1, j, k], ids[i + 1, j + 1, k], ids[i, j + 1, k],
                     ids[i, j, k + 1], ids[i + 1, j, k + 1], ids[i + 1, j + 1, k + 1],
                     ids[i, j + 1, k + 1]]
                if typ == "hex8":
                    m.add_element("hex8", c, mat)
                else:
                    for tet in [(0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6),
                                (1, 4, 5, 6), (3, 4, 6, 7)]:
                        m.add_element("tet4", [c[x] for x in tet], mat)
    return ids


def t_solid_tension(typ="hex8"):
    L, b, h = 2.0, 0.4, 0.3
    E = 210e9; F = 200000.0
    m = Model()
    m.add_material(Material("S", E=E, nu=0.3))
    nx, ny, nz = 4, 2, 2
    ids = _box_mesh(m, "S", L, b, h, nx, ny, nz, typ)
    for j in range(ny + 1):
        for k in range(nz + 1):
            m.fix(int(ids[0, j, k]), [0])
    m.fix(int(ids[0, 0, 0]), [1, 2])
    m.fix(int(ids[0, ny, 0]), [2])
    A = b * h
    for j in range(ny + 1):
        for k in range(nz + 1):
            w = 1.0
            if j in (0, ny):
                w *= 0.5
            if k in (0, nz):
                w *= 0.5
            m.load_node(int(ids[nx, j, k]), Fx=F * w / (ny * nz))
    r = solver.solve_static(m)
    u = r.u[ids[nx, ny // 2, nz // 2], 0]
    check(f"Volumen Zug {typ} (Verlaengerung)", u, F / A * L / E, 1e-6)
    check(f"Volumen Zug {typ} (Spannung)", r.solid_stress[0]["s"][0], F / A, 1e-6)


def t_patch_test(typ="tet4"):
    """Patch-Test: lineares Verschiebungsfeld auf dem gesamten Rand vorgeben.
    Alle Elemente muessen den konstanten Spannungszustand exakt abbilden."""
    E, nu, eps = 210e9, 0.3, 1e-4
    m = Model()
    m.add_material(Material("S", E=E, nu=nu))
    nx = ny = nz = 2
    ids = _box_mesh(m, "S", 1.0, 0.8, 0.6, nx, ny, nz, typ)
    lo, hi = m.bbox()
    for n in range(m.nn):
        x, y, z = m.nodes[n]
        on_bnd = (np.isclose(x, lo[0]) or np.isclose(x, hi[0]) or
                  np.isclose(y, lo[1]) or np.isclose(y, hi[1]) or
                  np.isclose(z, lo[2]) or np.isclose(z, hi[2]))
        if on_bnd:
            m.fix(n, [0, 1, 2],
                  values=[eps * x, -nu * eps * y, -nu * eps * z])
    r = solver.solve_static(m)
    smax = max(abs(v["s"][0] - E * eps) for v in r.solid_stress.values())
    check(f"Patch-Test {typ} (sigma_x konstant)", E * eps + smax, E * eps, 1e-8)
    q = max(abs(v["s"][1]) for v in r.solid_stress.values())
    check(f"Patch-Test {typ} (sigma_y = 0)", q / (E * eps) + 1.0, 1.0, 1e-8)


def t_solid_tet10():
    """Tet10 Patch-Test: konstanter Zug in einem einzelnen Element."""
    E, nu = 210e9, 0.3
    m = Model()
    m.add_material(Material("S", E=E, nu=nu))
    P = np.array([[0, 0, 0], [1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]], float)
    corners = [m.add_node(*p) for p in P]
    pairs = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]
    mids = [m.add_node(*(0.5 * (P[a] + P[b]))) for a, b in pairs]
    m.add_element("tet10", corners + mids, "S")
    eps = 1e-4
    for n in range(m.nn):
        x, y, z = m.nodes[n]
        m.fix(n, [0, 1, 2], values=[eps * x, -nu * eps * y, -nu * eps * z])
    r = solver.solve_static(m)
    check("Tet10 Patch-Test (sigma_x)", r.solid_stress[0]["s"][0], E * eps, 1e-8)
    q = abs(r.solid_stress[0]["s"][1]) / (E * eps)
    check("Tet10 Patch-Test (sigma_y = 0)", 1.0 + q, 1.0, 1e-8)


def t_tet10_cantilever():
    """Kragtraeger aus Tet10 gegen Balkentheorie (Biegung, nu=0)."""
    L, b, h = 2.0, 0.2, 0.2
    E, nu, F = 210e9, 0.0, 10000.0
    m = Model()
    m.add_material(Material("S", E=E, nu=nu))
    nx, ny, nz = 8, 2, 2
    ids = _box_mesh(m, "S", L, b, h, nx, ny, nz, "tet4")
    m2 = _tet4_to_tet10(m)
    lo, hi = m2.bbox()
    end_nodes = []
    for n in range(m2.nn):
        x, y, z = m2.nodes[n]
        if np.isclose(x, 0.0):
            m2.fix(n, [0, 1, 2])
        if np.isclose(x, L):
            end_nodes.append(n)
    for n in end_nodes:
        m2.load_node(n, Fz=-F / len(end_nodes))
    r = solver.solve_static(m2)
    w = max(-r.u[n, 2] for n in end_nodes)
    I = b * h ** 3 / 12
    G = E / 2.0
    ana = F * L ** 3 / (3 * E * I) + F * L / (5 / 6 * b * h * G)
    check("Tet10-Kragtraeger vs. Timoshenko", w, ana, 0.05)


def _tet4_to_tet10(m):
    """Konvertiert ein reines Tet4-Netz in Tet10 (Kantenmittelknoten)."""
    from statik3d.model import Model as _M
    out = _M(m.name)
    out.materials = m.materials
    out.sections = m.sections
    out.shells = m.shells
    out.nodes = m.nodes.copy()
    cache = {}

    def mid(a, b):
        key = (min(a, b), max(a, b))
        if key not in cache:
            cache[key] = out.add_node(*(0.5 * (out.nodes[a] + out.nodes[b])))
        return cache[key]

    for e in m.elements:
        n = e.nodes
        pairs = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]
        mids = [mid(n[a], n[b]) for a, b in pairs]
        out.add_element("tet10", list(n) + mids, e.mat)
    return out


def t_solid_cantilever():
    """Kragtraeger als Volumenmodell gegen Balkentheorie (inkl. Schub)."""
    L, b, h = 2.0, 0.2, 0.2
    E, nu, F = 210e9, 0.0, 10000.0
    m = Model()
    m.add_material(Material("S", E=E, nu=nu))
    nx, ny, nz = 20, 3, 3
    ids = _box_mesh(m, "S", L, b, h, nx, ny, nz, "hex8")
    for j in range(ny + 1):
        for k in range(nz + 1):
            m.fix(int(ids[0, j, k]), [0, 1, 2])
    npts = (ny + 1) * (nz + 1)
    for j in range(ny + 1):
        for k in range(nz + 1):
            m.load_node(int(ids[nx, j, k]), Fz=-F / npts)
    r = solver.solve_static(m)
    w = -r.u[ids[nx, ny // 2, nz // 2], 2]
    I = b * h ** 3 / 12
    G = E / 2.0
    ana = F * L ** 3 / (3 * E * I) + F * L / (5 / 6 * b * h * G)
    check("Volumen-Kragtraeger vs. Timoshenko", w, ana, 0.08)


# --------------------------------------------------------------------------
def main():
    print("=" * 92)
    print("STATIK3D - Verifikation gegen analytische Loesungen")
    print("=" * 92)
    print("\n-- Stabtragwerke ---------------------------------------------------")
    t_cantilever_beam()
    t_simply_supported_udl()
    t_frame_3d()
    t_truss()
    t_euler_buckling()
    t_modal_cantilever()
    print("\n-- Flaechentragwerke -----------------------------------------------")
    t_membrane()
    t_plate_cantilever()
    t_plate_ss(False)
    t_plate_ss(True)
    print("\n-- Volumentragwerke ------------------------------------------------")
    t_solid_tension("hex8")
    t_patch_test("tet4")
    t_patch_test("hex8")
    t_solid_tet10()
    t_solid_cantilever()
    t_tet10_cantilever()

    print("\n" + "=" * 92)
    nok = sum(1 for r in RESULTS if r[4])
    print(f"Ergebnis: {nok}/{len(RESULTS)} Tests bestanden")
    print("=" * 92)
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
