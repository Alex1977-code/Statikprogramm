"""
Alle Elementtypen durch den ganzen Weg: Modell, Assemblierung, Loeser,
Ergebnisse - gegen geschlossene Loesungen.

Die Elementformulierungen selbst sind in tests/test_elemente_volumen.py,
tests/test_elemente_schalen.py, tests/test_elemente_ebene.py und
tests/test_elemente_stab.py geprueft. Hier steht der **Einbau**: dass jeder
Typ ueber ``Model.add_element`` angelegt, assembliert, geloest, ausgewertet,
gespeichert und wieder geladen wird.

Aufruf:  python -m tests.test_elemente
"""
import os
import sys
import json
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import elemente as EL                            # noqa: E402
from statik3d import solver, mesher                            # noqa: E402
from statik3d.model import Model, Material, Section, ShellProp  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FEHLER'} {name:58s} {detail}")
    return bool(ok)


def close(name, num, ana, tol, einheit=""):
    num, ana = float(num), float(ana)
    abw = abs(num - ana) / abs(ana) if ana else abs(num)
    return check(name, abw <= tol, f"{num:.6g}{einheit} / {ana:.6g}{einheit}  Abw. {abw * 100:.3f} %")


def stahl(m: Model, E=210e9, nu=0.3, rho=7850.0) -> str:
    m.add_material(Material("S235", E=E, nu=nu, rho=rho))
    return "S235"


# --------------------------------------------------------------------------
# 1) Verzeichnis: jeder Typ ist vollstaendig beschrieben
# --------------------------------------------------------------------------
def test_verzeichnis():
    fehlt = [t for t, a in EL.ELEMENTE.items()
             if not a.name or a.knoten <= 0 or a.fhg not in (3, 6) or a.vtk <= 0]
    check("Verzeichnis: jeder Typ hat Name, Knotenzahl, FHG und VTK-Zelle",
          not fehlt, str(fehlt))
    check("Verzeichnis: Familien vollstaendig",
          set(EL.ELEMENTE) == set(EL.STAB_TYPEN + EL.SCHALEN_TYPEN + EL.VOLUMEN_TYPEN
                                  + EL.EBENE_TYPEN + EL.VERBINDUNG_TYPEN))
    from statik3d.gui import viewport as vp
    check("Ansicht kennt jede Zelle", set(vp.CELL_MAP) == set(EL.ELEMENTE))
    from statik3d.report.html import ELEMENT_TYPES
    check("Bericht benennt jeden Typ", set(ELEMENT_TYPES) == set(EL.ELEMENTE))
    from statik3d.exporters.vtk import VTK_CELLS
    check("VTK-Export kennt jede Zelle", set(VTK_CELLS) == set(EL.ELEMENTE))
    m = Model()
    stahl(m)
    m.add_nodes(np.zeros((2, 3)))
    try:
        m.add_element("gibtsnicht", [0, 1], "S235")
        check("unbekannter Elementtyp wird abgewiesen", False)
    except KeyError as ex:
        check("unbekannter Elementtyp wird abgewiesen", "gibtsnicht" in str(ex))
    # Knotenzahl je Typ stimmt mit dem Verzeichnis
    from statik3d.elements import solid as sl
    fehler = [t for t in EL.VOLUMEN_TYPEN if sl.knotenzahl(t) != EL.knotenzahl(t)]
    check("Volumenelemente: Knotenzahl wie im Verzeichnis", not fehler, str(fehler))


# --------------------------------------------------------------------------
# 2) Volumenelemente: Zug an einem Wuerfel, jeder Typ
# --------------------------------------------------------------------------
def _wuerfel_knoten(m: Model, L=1.0):
    """Die 8 Ecken, 12 Kantenmitten und 6 Seitenmitten eines Wuerfels."""
    P = np.array([[0, 0, 0], [L, 0, 0], [L, L, 0], [0, L, 0],
                  [0, 0, L], [L, 0, L], [L, L, L], [0, L, L]], float)
    return m.add_nodes(P)


def _volumen_modell(typ: str):
    """Ein Wuerfel (1 m) aus Elementen des genannten Typs, unten gehalten,
    oben mit Knotenlasten gezogen. Rueckgabe (Modell, obere Knoten, A)."""
    m = Model(typ)
    mat = stahl(m)
    L = 1.0
    ids = list(_wuerfel_knoten(m, L))
    kanten = {}

    def mitte(a, b):
        key = (min(a, b), max(a, b))
        if key not in kanten:
            kanten[key] = int(m.add_node(*(0.5 * (m.nodes[a] + m.nodes[b]))))
        return kanten[key]

    if typ == "hex8":
        m.add_element("hex8", ids, mat)
    elif typ == "hex20":
        k = [mitte(*p) for p in ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                                 (0, 4), (1, 5), (2, 6), (3, 7))]
        m.add_element("hex20", ids + k, mat)
    elif typ == "pent6":
        m.add_element("pent6", [ids[0], ids[1], ids[2], ids[4], ids[5], ids[6]], mat)
        m.add_element("pent6", [ids[0], ids[2], ids[3], ids[4], ids[6], ids[7]], mat)
    elif typ == "pent15":
        for e in ([ids[0], ids[1], ids[2], ids[4], ids[5], ids[6]],
                  [ids[0], ids[2], ids[3], ids[4], ids[6], ids[7]]):
            k = [mitte(e[0], e[1]), mitte(e[1], e[2]), mitte(e[2], e[0]),
                 mitte(e[3], e[4]), mitte(e[4], e[5]), mitte(e[5], e[3]),
                 mitte(e[0], e[3]), mitte(e[1], e[4]), mitte(e[2], e[5])]
            m.add_element("pent15", e + k, mat)
    elif typ == "pyr5":
        # Sechs Pyramiden mit gemeinsamer Spitze in der Mitte; die Grundflaeche
        # laeuft so um, dass ihre Rechtsschraube zur Spitze zeigt
        c = int(m.add_node(0.5, 0.5, 0.5))
        seiten = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
                  (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        spitze = m.nodes[c]
        for sd in seiten:
            P4 = m.nodes[[ids[i] for i in sd]]
            n = np.cross(P4[1] - P4[0], P4[2] - P4[0])
            if float(n @ (spitze - P4.mean(axis=0))) < 0:
                sd = sd[::-1]
            m.add_element("pyr5", [ids[sd[0]], ids[sd[1]], ids[sd[2]], ids[sd[3]], c], mat)
    elif typ == "tet4":
        for e in ((0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (1, 4, 5, 6), (3, 4, 6, 7)):
            m.add_element("tet4", [ids[i] for i in e], mat)
    elif typ == "tet10":
        for e in ((0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (1, 4, 5, 6), (3, 4, 6, 7)):
            a = [ids[i] for i in e]
            k = [mitte(a[0], a[1]), mitte(a[1], a[2]), mitte(a[0], a[2]),
                 mitte(a[0], a[3]), mitte(a[1], a[3]), mitte(a[2], a[3])]
            m.add_element("tet10", a + k, mat)
    unten = [int(i) for i in range(m.nn) if abs(m.nodes[i][2]) < 1e-9]
    oben = [int(i) for i in range(m.nn) if abs(m.nodes[i][2] - L) < 1e-9]
    for i in unten:
        m.fix(i, ["uz"])
    m.fix(unten[0], ["ux", "uy", "uz"])
    for i in unten[1:]:
        if abs(m.nodes[i][1]) < 1e-9:
            m.fix(i, ["uy"])
    return m, oben, L * L


def test_volumen_zug():
    """Jeder Volumentyp: einachsiger Zug am Wuerfel gegen sigma = F/A."""
    from statik3d.model import FaceLoad
    from statik3d.elements import solid as sl
    F = 1e6
    for typ in EL.VOLUMEN_TYPEN:
        m, oben, A = _volumen_modell(typ)
        # Gleichmaessige Zugspannung als Flaechenlast auf die Deckflaechen
        # aller Elemente (Druck positiv nach innen, darum -p)
        p = F / A
        lc = m.case()
        for i, e in enumerate(m.elements):
            for nr, seite in enumerate(sl.FLAECHEN[e.typ]):
                X = m.nodes[[e.nodes[k] for k in seite]]
                if np.all(np.abs(X[:, 2] - 1.0) < 1e-9):
                    lc.face_loads.append(FaceLoad(i, -p, nr))
        r = solver.solve_static(m)
        E = m.materials["S235"].E
        u = float(np.mean([r.u[i, 2] for i in oben]))
        close(f"{typ}: Verlaengerung unter Zug", u, F / A / E * 1.0, 5e-3, " m")
        sig = float(np.mean([r.solid_res[i][2] for i in range(len(m.elements))]))
        close(f"{typ}: Spannung sigma_z", sig, p, 5e-3, " Pa")
        R = float(r.reactions[:, 2].sum())
        close(f"{typ}: Gleichgewicht der Auflagerkraefte", R, -F, 1e-6, " N")


# --------------------------------------------------------------------------
# 3) Schalen: Plattenstreifen, jeder Typ
# --------------------------------------------------------------------------
def _plattenstreifen(typ: str, nx: int = 8, ny: int = 1, L: float = 5.0,
                     B: float = 1.0, t: float = 0.05):
    """Kragplattenstreifen aus Elementen des genannten Typs."""
    m = Model(typ)
    mat = stahl(m)
    m.add_shell_prop(ShellProp("t", t))
    ids = {}
    quadratisch = EL.ist_quadratisch(typ)
    nxx, nyy = (2 * nx, 2 * ny) if quadratisch else (nx, ny)
    for i in range(nxx + 1):
        for j in range(nyy + 1):
            ids[(i, j)] = int(m.add_node(i * L / nxx, j * B / nyy, 0.0))
    for i in range(nx):
        for j in range(ny):
            if quadratisch:
                a, b, c, d = (2 * i, 2 * j), (2 * i + 2, 2 * j), (2 * i + 2, 2 * j + 2), (2 * i, 2 * j + 2)
                mi = [(2 * i + 1, 2 * j), (2 * i + 2, 2 * j + 1), (2 * i + 1, 2 * j + 2), (2 * i, 2 * j + 1)]
                ecken = [ids[a], ids[b], ids[c], ids[d]]
                mitten = [ids[x] for x in mi]
                if typ == "shell8":
                    m.add_element("shell8", ecken + mitten, mat, "t")
                else:
                    zentrum = ids[(2 * i + 1, 2 * j + 1)]
                    m.add_element("shell6", [ecken[0], ecken[1], ecken[2],
                                             mitten[0], mitten[1], zentrum], mat, "t")
                    m.add_element("shell6", [ecken[0], ecken[2], ecken[3],
                                             zentrum, mitten[2], mitten[3]], mat, "t")
            else:
                ecken = [ids[(i, j)], ids[(i + 1, j)], ids[(i + 1, j + 1)], ids[(i, j + 1)]]
                if typ == "shell4":
                    m.add_element("shell4", ecken, mat, "t")
                else:
                    m.add_element("shell3", [ecken[0], ecken[1], ecken[2]], mat, "t")
                    m.add_element("shell3", [ecken[0], ecken[2], ecken[3]], mat, "t")
    fest = [i for i in range(m.nn) if abs(m.nodes[i][0]) < 1e-9]
    frei = [i for i in range(m.nn) if abs(m.nodes[i][0] - L) < 1e-9]
    for i in fest:
        m.fix(i, "all")
    return m, frei, L, B, t


def test_schalen_kragarm():
    """Jeder Schalentyp: Kragplattenstreifen gegen die Balkenloesung."""
    F = 1000.0
    for typ in EL.SCHALEN_TYPEN:
        m, frei, L, B, t = _plattenstreifen(typ)
        for i in frei:
            m.load_node(i, Fz=-F / len(frei))
        r = solver.solve_static(m)
        E, nu = m.materials["S235"].E, m.materials["S235"].nu
        # Schmaler Streifen: die Querdehnung ist frei, es gilt die
        # Balkenloesung mit E (mit Schubanteil, Schubkorrektur 5/6)
        I = B * t ** 3 / 12.0
        G = E / (2 * (1 + nu))
        ana = F * L ** 3 / (3.0 * E * I) + F * L / (G * (5.0 / 6.0) * B * t)
        w = -float(np.mean([r.u[i, 2] for i in frei]))
        close(f"{typ}: Kragplattenstreifen", w, ana, 0.05, " m")
        check(f"{typ}: Schnittgroessen berechnet",
              len(r.shell_res) == len(m.elements) and np.all(np.isfinite(r.shell_res[0])))


def test_schalen_platte():
    """shell4 und shell8: gelenkig gelagerte Quadratplatte unter Gleichlast."""
    from statik3d.model import FaceLoad
    a, t, q = 4.0, 0.04, 5000.0
    for typ, n in (("shell4", 8), ("shell8", 4)):
        m = Model(typ)
        mat = stahl(m)
        m.add_shell_prop(ShellProp("t", t))
        quadratisch = EL.ist_quadratisch(typ)
        nn = 2 * n if quadratisch else n
        ids = {}
        for i in range(nn + 1):
            for j in range(nn + 1):
                ids[(i, j)] = int(m.add_node(i * a / nn, j * a / nn, 0.0))
        for i in range(n):
            for j in range(n):
                if quadratisch:
                    ecken = [ids[(2 * i, 2 * j)], ids[(2 * i + 2, 2 * j)],
                             ids[(2 * i + 2, 2 * j + 2)], ids[(2 * i, 2 * j + 2)]]
                    mitten = [ids[(2 * i + 1, 2 * j)], ids[(2 * i + 2, 2 * j + 1)],
                              ids[(2 * i + 1, 2 * j + 2)], ids[(2 * i, 2 * j + 1)]]
                    m.add_element("shell8", ecken + mitten, mat, "t")
                else:
                    m.add_element("shell4", [ids[(i, j)], ids[(i + 1, j)],
                                             ids[(i + 1, j + 1)], ids[(i, j + 1)]], mat, "t")
        for (i, j), k in ids.items():
            if i in (0, nn) or j in (0, nn):
                m.fix(k, ["uz"])
        m.fix(ids[(0, 0)], ["ux", "uy", "uz"])
        m.fix(ids[(nn, 0)], ["uy", "uz"])
        lc = m.case()
        for i in range(len(m.elements)):
            lc.face_loads.append(FaceLoad(i, -q, 0))
        r = solver.solve_static(m)
        E, nu = m.materials["S235"].E, m.materials["S235"].nu
        D = E * t ** 3 / (12 * (1 - nu ** 2))
        ana = 0.00406 * q * a ** 4 / D
        w = -float(r.u[ids[(nn // 2, nn // 2)], 2])
        close(f"{typ}: gelenkige Quadratplatte w_max", w, ana, 0.05, " m")


# --------------------------------------------------------------------------
# 4) Ebene Elemente: Scheibe und rotationssymmetrisch
# --------------------------------------------------------------------------
def test_ebene():
    """Kragscheibe (ebener Spannungszustand) und dickwandiger Zylinder."""
    E, nu, t = 210e9, 0.3, 0.1
    L, h = 4.0, 1.0
    for typ, nx, nz, tol in (("ebene4", 8, 2, 0.05), ("ebene8", 4, 1, 0.05),
                             ("ebene3", 16, 4, 0.35), ("ebene6", 4, 1, 0.05)):
        m = Model(typ)
        mat = stahl(m, E, nu)
        m.add_shell_prop(ShellProp("t", t))
        quadratisch = EL.ist_quadratisch(typ)
        nxx, nzz = (2 * nx, 2 * nz) if quadratisch else (nx, nz)
        ids = {}
        for i in range(nxx + 1):
            for k in range(nzz + 1):
                ids[(i, k)] = int(m.add_node(i * L / nxx, 0.0, k * h / nzz))
        for i in range(nx):
            for k in range(nz):
                if quadratisch:
                    ecken = [ids[(2 * i, 2 * k)], ids[(2 * i + 2, 2 * k)],
                             ids[(2 * i + 2, 2 * k + 2)], ids[(2 * i, 2 * k + 2)]]
                    mitten = [ids[(2 * i + 1, 2 * k)], ids[(2 * i + 2, 2 * k + 1)],
                              ids[(2 * i + 1, 2 * k + 2)], ids[(2 * i, 2 * k + 1)]]
                    if typ == "ebene8":
                        m.add_element("ebene8", ecken + mitten, mat, "t", zustand="spannung")
                    else:
                        z = ids[(2 * i + 1, 2 * k + 1)]
                        m.add_element("ebene6", [ecken[0], ecken[1], ecken[2],
                                                 mitten[0], mitten[1], z], mat, "t",
                                      zustand="spannung")
                        m.add_element("ebene6", [ecken[0], ecken[2], ecken[3],
                                                 z, mitten[2], mitten[3]], mat, "t",
                                      zustand="spannung")
                else:
                    ecken = [ids[(i, k)], ids[(i + 1, k)], ids[(i + 1, k + 1)], ids[(i, k + 1)]]
                    if typ == "ebene4":
                        m.add_element("ebene4", ecken, mat, "t", zustand="spannung")
                    else:
                        m.add_element("ebene3", [ecken[0], ecken[1], ecken[2]], mat, "t",
                                      zustand="spannung")
                        m.add_element("ebene3", [ecken[0], ecken[2], ecken[3]], mat, "t",
                                      zustand="spannung")
        for k in range(nzz + 1):
            m.fix(ids[(0, k)], "all")
        F = 1000.0
        for k in range(nzz + 1):
            m.load_node(ids[(nxx, k)], Fz=-F / (nzz + 1))
        r = solver.solve_static(m)
        I = t * h ** 3 / 12.0
        G = E / (2 * (1 + nu))
        ana = F * L ** 3 / (3 * E * I) + F * L / (G * (5.0 / 6.0) * t * h)
        w = -float(np.mean([r.u[ids[(nxx, k)], 2] for k in range(nzz + 1)]))
        close(f"{typ}: Kragscheibe", w, ana, tol, " m")

    # rotationssymmetrisch: dickwandiges Rohr unter Innendruck (Lame)
    from statik3d.model import FaceLoad
    ri, ra, p, hz = 1.0, 2.0, 10e6, 0.2
    n = 10
    m = Model("Rohr")
    mat = stahl(m, E, nu)
    m.add_shell_prop(ShellProp("t", 1.0))
    ids = {}
    for i in range(n + 1):
        for k in range(2):
            ids[(i, k)] = int(m.add_node(ri + i * (ra - ri) / n, 0.0, k * hz))
    for i in range(n):
        m.add_element("ebene4", [ids[(i, 0)], ids[(i + 1, 0)], ids[(i + 1, 1)], ids[(i, 1)]],
                      mat, "t", zustand="rotation")
    for i in range(n + 1):
        for k in range(2):
            m.fix(ids[(i, k)], ["uz"])           # ebener Dehnungszustand in z
    lc = m.case()
    lc.face_loads.append(FaceLoad(0, p, 3))      # Kante 3 (Knoten 3-0) = Innenrand
    r = solver.solve_static(m)
    ur = float(r.u[ids[(0, 0)], 0])
    ana = p * ri / E * ((1 + nu) * ((1 - 2 * nu) * ri ** 2 + ra ** 2) / (ra ** 2 - ri ** 2))
    close("ebene4 rotationssymmetrisch: u_r am Innenrand (Lame)", ur, ana, 0.03, " m")


# --------------------------------------------------------------------------
# 5) Staebe: Zugstab, Seil, Exzentrizitaet, Woelbkrafttorsion
# --------------------------------------------------------------------------
def test_zugstab():
    """Zugband: der gedrueckte Diagonalstab faellt aus, das Modell bleibt stehen.

    Ein Stiel (Balken, eingespannt) traegt oben eine waagerechte Last; zwei
    Diagonalen aus Zugbaendern spannen nach links und rechts zum Boden. Nur
    das eine Band kann ziehen - das andere muesste druecken und faellt aus.
    """
    m = Model("Zugband")
    mat = stahl(m)
    m.add_section(Section("R", A=1e-2, Iy=1e-5, Iz=1e-5, It=1e-5))
    m.add_section(Section("Band", A=1e-4, Iy=1e-10, Iz=1e-10, It=1e-10))
    fuss = m.add_node(0, 0, 0)
    kopf = m.add_node(0, 0, 3)
    links = m.add_node(-2, 0, 0)
    rechts = m.add_node(2, 0, 0)
    m.add_element("beam", [fuss, kopf], mat, "R")
    i_l = m.add_element("truss", [links, kopf], mat, "Band", nur="zug")
    i_r = m.add_element("truss", [rechts, kopf], mat, "Band", nur="zug")
    m.fix(fuss, "all")
    m.fix(links, "pinned")
    m.fix(rechts, "pinned")
    for k in (kopf,):
        m.fix(k, ["uy", "rx", "rz"])
    F = 10000.0
    m.load_node(kopf, Fx=F)
    r = solver.solve_static(m)
    N_l = float(r.beam_forces[i_l]["N"][1])
    N_r = float(r.beam_forces[i_r]["N"][1])
    check("Zugband: kein Band unter Druck", min(N_l, N_r) > -1e-6,
          f"N_links = {N_l:.1f} N, N_rechts = {N_r:.1f} N")
    check("Zugband: das gezogene Band traegt", max(N_l, N_r) > 100.0,
          f"N = {max(N_l, N_r):.1f} N")
    check("Zugband: genau ein Band ist ausgefallen",
          len(r.info.get("ausfall", [])) == 1, str(r.info.get("ausfall")))
    close("Zugband: Gleichgewicht in x", float(r.reactions[:, 0].sum()), -F, 1e-9, " N")
    # Ohne Ausfall-Kennzeichen wuerden beide Baender tragen: dann ist die
    # Kopfverschiebung kleiner. Der Vergleich zeigt, dass der Ausfall wirkt.
    m2 = Model.from_dict(m.to_dict())
    for e in m2.elements:
        e.nur = ""
    r2 = solver.solve_static(m2)
    check("Zugband: Ausfall macht das System weicher",
          float(r.u[kopf, 0]) > float(r2.u[kopf, 0]) > 0,
          f"{float(r.u[kopf, 0]):.6g} > {float(r2.u[kopf, 0]):.6g}")


def test_exzentrizitaet():
    """Stab mit Versatz: die Normalkraft erzeugt am Knoten ein Moment N e."""
    m = Model("Versatz")
    mat = stahl(m)
    sec = m.add_section(Section("R", A=1e-2, Iy=1e-5, Iz=1e-5, It=1e-5))
    a = m.add_node(0, 0, 0)
    b = m.add_node(1, 0, 0)
    e = 0.1
    m.add_element("beam", [a, b], mat, "R", exzentrizitaet=[[0, 0, e], [0, 0, e]])
    m.fix(a, "all")
    m.load_node(b, Fx=1000.0)
    r = solver.solve_static(m)
    # Der Knoten sieht nur die Normalkraft; das Moment N e traegt der Stab,
    # dessen Achse um e neben dem Knoten liegt
    close("Versatz: Auflagerkraft", float(r.reactions[a, 0]), -1000.0, 1e-9, " N")
    My = max(abs(float(r.beam_end[0][4])), abs(float(r.beam_end[0][10])))
    close("Versatz: Stabmoment aus N e", My, 1000.0 * e, 1e-6, " Nm")
    m2 = Model.from_dict(m.to_dict())
    m2.elements[0].exzentrizitaet = []
    r2 = solver.solve_static(m2)
    check("ohne Versatz kein Moment", abs(float(r2.beam_end[0][4])) < 1e-9,
          f"{float(r2.beam_end[0][4]):.3g} Nm")
    _ = sec


def test_woelbkrafttorsion():
    """Gabelgelagerter I-Traeger unter Torsion: Verdrehung und Bimoment."""
    E, G = 210e9, 80.77e9
    It, Iw, L, T = 2.01e-7, 1.26e-7, 6.0, 10000.0
    m = Model("Woelb")
    m.add_material(Material("S235", E=E, nu=E / (2 * G) - 1, rho=7850))
    m.add_section(Section("I", A=1e-2, Iy=1e-4, Iz=1e-5, It=It, Iw=Iw))
    n = 20
    ids = [int(m.add_node(i * L / n, 0, 0)) for i in range(n + 1)]
    for i in range(n):
        m.add_element("beam", [ids[i], ids[i + 1]], "S235", "I", woelb=True)
    for k in (0, n):
        m.fix(ids[k], ["ux", "uy", "uz", "rx"])   # Gabellagerung, Verwoelbung frei
    m.fix(ids[0], ["ry", "rz"])
    m.load_node(ids[n // 2], Mx=T)
    check("Woelbkrafttorsion: eigene Freiheitsgrade", m.ndof > m.nn * 6,
          f"{m.ndof} FHG bei {m.nn} Knoten")
    r = solver.solve_static(m)
    lam = np.sqrt(G * It / (E * Iw))
    ana = T / (2 * G * It * lam) * (lam * L / 2 - np.tanh(lam * L / 2))
    close("Woelbkrafttorsion: Verdrehung in Feldmitte",
          float(r.u[ids[n // 2], 3]), ana, 0.02, " rad")
    B = T / (2 * lam) * np.tanh(lam * L / 2)
    Bm = max(abs(v) for paar in r.bimomente.values() for v in paar)
    close("Woelbkrafttorsion: groesstes Bimoment", Bm, B, 0.05, " Nm^2")
    check("Verwoelbung steht im Ergebnis", len(r.woelb) == m.nn, str(len(r.woelb)))


# --------------------------------------------------------------------------
# 6) Verbindungen: Feder, Punktmasse, Daempfer, starrer Koerper, Grenzschicht
# --------------------------------------------------------------------------
def test_feder_und_punktmasse():
    m = Model("Feder")
    stahl(m)
    a = m.add_node(0, 0, 0)
    b = m.add_node(0, 0, 1)
    k = 2e6
    m.add_feder_prop("F", [k, 1e9, 1e9, 1e9, 1e9, 1e9])
    m.add_element("feder", [a, b], "S235", "F")
    m.fix(a, "all")
    m.fix(b, ["rx", "ry", "rz"])
    F = 2000.0
    m.load_node(b, Fz=-F)
    r = solver.solve_static(m)
    close("Feder: Verschiebung F/k", -float(r.u[b, 2]), F / k, 1e-9, " m")
    close("Feder: Federkraft", -float(r.feder_res[0][0]), F, 1e-9, " N")
    masse = 500.0
    m.add_punktmasse(b, masse)
    mo = solver.solve_modal(m, nmodes=2)
    close("Punktmasse: Eigenfrequenz sqrt(k/m)/2pi",
          float(mo.freqs[0]), np.sqrt(k / masse) / (2 * np.pi), 1e-3, " Hz")
    lc = m.case()
    lc.gravity = [0, 0, -9.81]
    r2 = solver.solve_static(m)
    close("Punktmasse: Eigengewicht m g", -float(r2.u[b, 2]) * k,
          F + masse * 9.81, 1e-6, " N")


def test_daempfer():
    """Daempfer: Matrix und modale Daempfung."""
    from statik3d import assemble as asm
    m = Model("Daempfer")
    stahl(m)
    a = m.add_node(0, 0, 0)
    b = m.add_node(0, 0, 1)
    m.add_feder_prop("F", [1e6] * 6)
    m.add_element("feder", [a, b], "S235", "F")
    m.add_daempfer(b, -1, [50.0, 0, 0, 0, 0, 0], achse=[0, 0, 1])
    C = asm.daempfung(m)
    check("Daempfer: Matrix aufgestellt", C.nnz > 0, f"{C.nnz} Eintraege")
    close("Daempfer: c auf dem Knoten", float(C[6 * b + 2, 6 * b + 2]), 50.0, 1e-9)


def test_starrkoerper():
    """RBE3: eine Last am Master verteilt sich gleich auf die Slaves."""
    m = Model("RBE3")
    stahl(m)
    mitte = m.add_node(0, 0, 1)
    ecken = [m.add_node(x, y, 0) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    m.add_feder_prop("F", [1e7] * 6)
    for e in ecken:
        m.add_element("feder", [e, m.add_node(*(m.nodes[e]))], "S235", "F")
    for i, e in enumerate(ecken):
        m.fix(int(m.elements[i].nodes[1]), "all")
    m.add_starrkoerper(mitte, ecken, "RBE3")
    for e in ecken:
        m.fix(e, ["rx", "ry", "rz"])
    m.fix(mitte, ["ux", "uy", "rx", "ry", "rz"])
    F = 4000.0
    m.load_node(mitte, Fz=-F)
    r = solver.solve_static(m)
    uz = [float(r.u[e, 2]) for e in ecken]
    check("RBE3: alle Slaves gleich verschoben",
          max(uz) - min(uz) < 1e-9, f"{np.round(uz, 8)}")
    close("RBE3: Last gleichmaessig verteilt", -float(np.mean(uz)) * 1e7, F / 4, 1e-3, " N")


def test_grenzschicht():
    """Grenzschicht ohne Dicke: zwei Bloecke, dazwischen eine weiche Fuge."""
    m = Model("Grenzschicht")
    mat = stahl(m)
    unten = [m.add_node(x, y, 0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    fuge = [m.add_node(x, y, 1) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    m.add_element("hex8", unten + fuge, mat)
    kn = 1e9
    m.add_grenzschicht_prop("GS", kn=kn, kt=1e9)
    oben = [m.add_node(x, y, 1) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    m.add_element("grenzschicht8", fuge + oben, mat, "GS")
    oben2 = [m.add_node(x, y, 2) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    m.add_element("hex8", oben + oben2, mat)
    for i in unten:
        m.fix(i, "all")
    F = 1e5
    for i in oben2:
        m.load_node(i, Fz=F / 4)
    r = solver.solve_static(m)
    E = m.materials["S235"].E
    # Verlaengerung: zwei Bloecke (je 1 m) plus die Fuge F/(kn A)
    ana = 2 * F / (1.0 * E) + F / (kn * 1.0)
    close("Grenzschicht: Verlaengerung mit Fuge",
          float(np.mean([r.u[i, 2] for i in oben2])), ana, 0.05, " m")
    sn = float(r.grenzschicht_res[1][0])
    close("Grenzschicht: Normalspannung in der Fuge", sn, F / 1.0, 0.02, " Pa")


# --------------------------------------------------------------------------
# 7) Speichern, Laden, Vernetzen, Bericht
# --------------------------------------------------------------------------
def test_speichern_laden():
    """Jeder neue Typ und jedes neue Objekt uebersteht Speichern und Laden."""
    m = Model("Alles")
    mat = stahl(m)
    m.add_section(Section("R", A=1e-2, Iy=1e-5, Iz=1e-5, It=1e-5, Iw=1e-7))
    m.add_shell_prop(ShellProp("t", 0.01, lagen=[{"t": 0.005, "E": 210e9, "nu": 0.3, "winkel": 0.0},
                                                 {"t": 0.005, "E": 210e9, "nu": 0.3, "winkel": 1.57}]))
    m.add_feder_prop("F", [1e6] * 6)
    m.add_grenzschicht_prop("GS", 1e9, 1e9)
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]])
    ids = list(m.add_nodes(P))
    m.add_element("beam", [ids[0], ids[1]], mat, "R", woelb=True,
                  exzentrizitaet=[[0, 0, 0.05], [0, 0, 0.05]])
    m.add_element("truss", [ids[1], ids[2]], mat, "R", nur="zug")
    m.add_element("seil", [ids[2], ids[3]], mat, "R", laenge0=1.2)
    m.add_element("shell4", ids[:4], mat, "t")
    m.add_element("ebene4", ids[:4], mat, "t", zustand="dehnung")
    m.add_element("hex8", ids, mat)
    m.add_element("feder", [ids[0], ids[4]], mat, "F")
    m.add_punktmasse(ids[0], 100.0, [1, 2, 3])
    m.add_daempfer(ids[0], ids[1], [10.0] * 6)
    m.add_starrkoerper(ids[0], [ids[1], ids[2]], "RBE2")
    with tempfile.TemporaryDirectory() as d:
        pfad = os.path.join(d, "modell.s3d")
        m.save(pfad)
        m2 = Model.load(pfad)
    check("Laden: alle Elemente", len(m2.elements) == len(m.elements),
          f"{len(m2.elements)} von {len(m.elements)}")
    check("Laden: Elementtypen", [e.typ for e in m2.elements] == [e.typ for e in m.elements])
    check("Laden: Woelbkrafttorsion und Exzentrizitaet",
          m2.elements[0].woelb and m2.elements[0].exzentrizitaet == [[0, 0, 0.05], [0, 0, 0.05]])
    check("Laden: Zugstab und Seillaenge",
          m2.elements[1].nur == "zug" and abs(m2.elements[2].laenge0 - 1.2) < 1e-12)
    check("Laden: Zustand des ebenen Elements", m2.elements[4].zustand == "dehnung")
    check("Laden: Laminat der Schale", len(m2.shells["t"].lagen) == 2)
    check("Laden: Punktmasse, Daempfer, Feder, starrer Koerper",
          len(m2.punktmassen) == 1 and len(m2.daempfer) == 1
          and "F" in m2.federn and len(m2.starrkoerper) == 1
          and "GS" in m2.grenzschichten)
    check("Laden: Formatversion 7",
          json.loads(json.dumps(m.to_dict()))["format"] >= 7)


def test_netz_quadratisch():
    """Netzeinstellung „quadratisch“ erzeugt shell6/shell8, hex20, tet10."""
    m = Model("Netz")
    mat = stahl(m)
    m.add_shell_prop(ShellProp("t", 0.01))
    P = np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0.]])
    ids = list(m.add_nodes(P))
    for i in range(4):
        m.add_line(f"L{i}", [ids[i], ids[(i + 1) % 4]], "polyline")
    f = m.add_flaeche("F", [f"L{i}" for i in range(4)], material=mat, dicke="t", teilung=[2, 2])
    m.netz.ordnung = 2
    m.netz.form = 1
    els = mesher.mesh_flaeche(m, f)
    check("Netz quadratisch: Vierecke werden shell8",
          all(m.elements[i].typ == "shell8" for i in els) and len(els) == 4,
          str({m.elements[i].typ for i in els}))
    kn = {n for i in els for n in m.elements[i].nodes}
    check("Netz quadratisch: Kantenmitten werden geteilt", len(kn) == 21, f"{len(kn)} Knoten")
    m.netz.form = 0
    for i in list(f.elemente):
        pass
    m2 = Model("Netz3")
    stahl(m2)
    m2.add_shell_prop(ShellProp("t", 0.01))
    ids2 = list(m2.add_nodes(P))
    for i in range(4):
        m2.add_line(f"L{i}", [ids2[i], ids2[(i + 1) % 4]], "polyline")
    f2 = m2.add_flaeche("F", [f"L{i}" for i in range(4)], material="S235", dicke="t", teilung=[2, 2])
    m2.netz.ordnung = 2
    m2.netz.form = 0
    els2 = mesher.mesh_flaeche(m2, f2)
    check("Netz quadratisch: Dreiecke werden shell6",
          all(m2.elements[i].typ == "shell6" for i in els2),
          str({m2.elements[i].typ for i in els2}))


def test_bericht_und_export():
    """Bericht und Export kommen mit allen Typen zurecht."""
    from statik3d.exporters import vtk as vtk_ex, abaqus as abq_ex, nastran as nas_ex
    m = Model("Export")
    mat = stahl(m)
    m.add_section(Section("R", A=1e-2, Iy=1e-5, Iz=1e-5, It=1e-5))
    m.add_shell_prop(ShellProp("t", 0.01))
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]])
    ids = list(m.add_nodes(P))
    m.add_element("beam", [ids[0], ids[1]], mat, "R")
    m.add_element("shell4", ids[:4], mat, "t")
    m.add_element("hex8", ids, mat)
    m.add_element("pent6", [ids[0], ids[1], ids[2], ids[4], ids[5], ids[6]], mat)
    m.add_element("pyr5", [ids[0], ids[1], ids[2], ids[3], ids[4]], mat)
    m.add_element("ebene4", ids[:4], mat, "t", zustand="rotation")
    with tempfile.TemporaryDirectory() as d:
        p1 = vtk_ex.write_vtu(m, os.path.join(d, "m.vtu"))
        p2 = abq_ex.write_inp(m, os.path.join(d, "m.inp"))
        p3 = nas_ex.write_bdf(m, os.path.join(d, "m.bdf"))
        check("VTK-Export", os.path.getsize(p1) > 500)
        inp = open(p2, encoding="utf-8", errors="ignore").read()
        check("Abaqus-Export nennt die neuen Typen",
              "C3D6" in inp and "C3D5" in inp and "CAX4" in inp, "")
        bdf = open(p3, encoding="utf-8", errors="ignore").read()
        check("Nastran-Export nennt CPENTA und CPYRAM",
              "CPENTA" in bdf and "CPYRAM" in bdf, "")
    from statik3d.report.html import ELEMENT_TYPES
    fehlt = [e.typ for e in m.elements if e.typ not in ELEMENT_TYPES]
    check("Bericht kennt jeden verwendeten Typ", not fehlt, str(fehlt))


# --------------------------------------------------------------------------
def main():
    print("=" * 92)
    print("STATIK3D - Elementtypen im Zusammenspiel")
    print("=" * 92)
    for t in (test_verzeichnis, test_volumen_zug, test_schalen_kragarm, test_schalen_platte,
              test_ebene, test_zugstab, test_exzentrizitaet, test_woelbkrafttorsion,
              test_feder_und_punktmasse, test_daempfer, test_starrkoerper, test_grenzschicht,
              test_speichern_laden, test_netz_quadratisch, test_bericht_und_export):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:                     # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(t.__name__, False, str(ex)[:80])
    print("\n" + "=" * 92)
    nok = sum(1 for _n, ok in RESULTS if ok)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN: " + "; ".join(schlecht))
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
