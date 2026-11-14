"""
Stäbe mit Versatz: Achsen, Stablast nach Theorie III. Ordnung, Knicken mit
Sollkraft, Konvergenz nach Theorie II. Ordnung (14.11.2026, Verfahrensstand 41;
Befunde A1 bis A4 und A10 der Befundliste vom 14.11.2026).

A1  Stab mit verschiedenem Versatz an Anfang und Ende: seine Achsen kamen aus
    bm.local_axes für die Linie zwischen den versetzten Enden. Für eine
    lotrechte Knotenlinie springt dort die Bezugsrichtung (|e_x,z| > 0,9999
    nimmt global X statt Z): der Querschnitt drehte um 90° bzw. 180°.
    Lotrechte Stütze 4 m, Iy = 1e-4, Iz = 4e-4 m⁴, Versatz oben 0,1 m,
    Fx = 10 kN: Kopfverdrehung 0,9639 statt 3,8119 mrad; lokale Streckenlast
    qz = 1 kN/m: Lager Rx +4,0 statt −4,0 kN. Seither die Achsen der
    Knotenlinie durch die kleinste Drehung auf die Stabrichtung t:
    y' = y_n − (y_n·t) t normiert, z' = t × y' (bm.stab_achsen_versetzt).
A2  Theorie III. Ordnung: die Stablast eines Stabs mit Versatz stand als
    feste Knotenlast mit unverdrehtem Arm in F_ref. Kragarm 4 m, Versatz
    0,5 m, qz −400 kN/m: Einspannmoment 3061,42 statt 3171,17 kNm
    (Kurzstabmodell). Seither wirkt die Stablast am Stabende in festen
    Richtungen und geht je Iteration über den mitgedrehten Arm auf den Knoten.
A3  Knicken mit Vorspannkraft (Sollkraft) im Stab mit Arm: der Armanteil las
    die Stabendkraft ohne die Verriegelung (Knickfaktor 88,34 bzw. 1038,76
    statt 801,61 bzw. 817,69); alpha_cr im Modus „auto“ sah mit Sollkraft gar
    keine Normalkraft (∞).
A4  Theorie II. Ordnung mit schiefsymmetrischem Armanteil als Last: die
    Iteration stockte (α_cr 1,4: nach 30 Schritten 0,355 % Änderung) und gab
    trotzdem ein gerechnetes Ergebnis aus. Seither löst sie dann mit der
    vollen unsymmetrischen Matrix; bleibt sie unkonvergiert, ist es ein Fehler.
A10 Ein axialer Versatz, der die Stabenden aufeinanderlegt, steht in der
    Modellprüfung mit Hinweis auf den Versatz.

Aufruf:  python -m tests.test_versatz_achsen_lotrecht
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []

E, NU = 210e9, 0.3
IY, IZ, L = 1e-4, 4e-4, 4.0


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {detail}")
    return ok


def _rechnen(m, case="LF1"):
    from statik3d import solver
    return solver.solve_all(m, workers=1, design=False).cases[case]


# ---------------------------------------------------------------- A1 Achsen
def _stuetze(art, r2, last=None, stablast=None, roll=0.0, kopf=(0.0, 0.0, L), roll_n=0.0):
    """Stütze vom Ursprung zum Kopf, unten eingespannt, Versatz r2 (lokal der
    Knotenlinie) nur oben. art "versatz": Versatz am Element; "kurzstab": der
    Stab an eigenem Knoten x + a mit Drehwinkel ``roll`` (so gewählt, dass
    seine Achsen die der Behebung sind), steifer Kurzstab zum Kopfknoten;
    ``roll_n`` der Drehwinkel der Knotenlinie, in deren Achsen r2 steht
    (Vorgabe 0)."""
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=NU, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=IY, Iz=IZ, It=1e-4, zmax=0.1, ymax=0.05))
    m.add_section(Section("STARR", A=10.0, Iy=1.0, Iz=1.0, It=1.0, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(*kopf)
    if art == "versatz":
        e = m.add_element("beam", [a, b], "ST", "Q", exzentrizitaet=[[0, 0, 0], list(r2)])
        m.elements[e].roll = roll
    else:
        from statik3d.elements import beam3d as bm
        T3n, _L = bm.local_axes([0, 0, 0], kopf, roll_n)
        p = m.add_node(*(np.asarray(kopf, float) + T3n.T @ np.asarray(r2, float)))
        e = m.add_element("beam", [a, p], "ST", "Q")
        m.elements[e].roll = roll
        m.add_element("beam", [p, b], "ST", "STARR")
    m.fix(a, "all")
    m.case("LF1")
    if last:
        m.load_node(b, case="LF1", **last)
    if stablast:
        m.load_beam(e, case="LF1", **stablast)
    return m, a, b, e


def test_achsen_stetig():
    """Die Achsen des Stabs folgen denen der Knotenlinie stetig: y'·y_n und
    z'·z_n nahe 1, orthonormal, rechtshändig, für lotrecht (Versatz in y, in z,
    in beiden), schräg und mit Drehwinkel."""
    from statik3d import assemble as asm
    from statik3d.elements import beam3d as bm
    faelle = [("lotrecht, Versatz y 0,1 m", (0, 0, L), [0, 0.1, 0], 0.0),
              ("lotrecht, Versatz z 0,1 m", (0, 0, L), [0, 0, 0.1], 0.0),
              ("lotrecht, Versatz y und z", (0, 0, L), [0, 0.07, -0.05], 0.0),
              ("lotrecht, Drehwinkel 30°", (0, 0, L), [0, 0.1, 0.05], math.radians(30)),
              ("lotrecht nach unten, Versatz y", (0, 0, -L), [0, 0.1, 0], 0.0),
              ("schräg, Versatz y und z", (3.0, 1.0, 2.0), [0, 0.1, 0.2], 0.0),
              ("schräg, Drehwinkel −50°", (3.0, 1.0, 2.0), [0.3, -0.1, 0.2], math.radians(-50))]
    for text, kopf, r2, roll in faelle:
        m, _a, _b, e = _stuetze("versatz", r2, roll=roll, kopf=kopf)
        el = m.elements[e]
        T3, Lp = asm.stab_achsen(m, el)
        X = m.nodes[el.nodes]
        T3n, _Ln = bm.local_axes(X[0], X[1], roll)
        arme = asm.stab_arme(m, el)
        t = (X[1] + arme[1]) - (X[0] + arme[0])
        ortho = np.allclose(T3 @ T3.T, np.eye(3), atol=1e-12) and np.linalg.det(T3) > 0.999999999
        lage = np.allclose(T3[0], t / np.linalg.norm(t), atol=1e-14) and abs(Lp - np.linalg.norm(t)) < 1e-14
        stetig = float(T3[1] @ T3n[1]) > 0.99 and float(T3[2] @ T3n[2]) > 0.99
        # die Formel selbst (zweiter Weg): Projektion von y_n senkrecht zu t
        tt = t / np.linalg.norm(t)
        y = T3n[1] - (T3n[1] @ tt) * tt
        y /= np.linalg.norm(y)
        formel = np.allclose(T3[1], y, atol=1e-14) and np.allclose(T3[2], np.cross(tt, y), atol=1e-14)
        # stab_versatz in denselben Achsen: der Arm in Stabachsen ist T3 a
        A = asm.stab_versatz(m, el)
        a_stab = T3 @ arme[1]
        Aok = A is not None and np.allclose(-A[6:9, 9:12], bm._skew(a_stab), atol=1e-15)
        check(f"A1 Achsen des Stabs, {text}: stetig zur Knotenlinie (y'·y_n, z'·z_n > 0,99), "
              "orthonormal, y' = y_n − (y_n·t) t, A in denselben Achsen",
              ortho and lage and stetig and formel and Aok,
              f"y'·y_n {T3[1] @ T3n[1]:+.4f}, z'·z_n {T3[2] @ T3n[2]:+.4f}")


def test_stuetze_kopfverdrehung():
    """Fall A des Befunds: Versatz oben (0; 0,1; 0) lokal = 0,1 m in −Y,
    Fx = 10 kN am Kopf (lokal z der Knotenlinie): Biegung mit Iy.
    Weg 1 von Hand φ_y = F L'²/(2 E Iy); Weg 2 das Kurzstabmodell, Stab an
    eigenem Knoten mit Drehwinkel −90° (local_axes nimmt für die geneigte
    Linie y = +X, die Achsen der Knotenlinie verlangen y ≈ −Y), nach Theorie
    I. Ordnung - nach Theorie III. Ordnung konvergiert das Kurzstabmodell
    mit dem 0,1 m kurzen, sehr steifen Kurzstab nicht (Residuum 0,03 %), die
    Last ist ohne Normalkraft ohnehin im linearen Bereich."""
    F = 10e3
    Lp = math.hypot(L, 0.1)
    hand = F * Lp ** 2 / (2 * E * IY)
    for th in ("I", "II", "III"):
        m, a, b, e = _stuetze("versatz", [0, 0.1, 0], last={"Fx": F})
        mk, ak, bk, ek = _stuetze("kurzstab", [0, 0.1, 0], last={"Fx": F}, roll=-math.pi / 2)
        if th == "III":
            from statik3d.theorie3 import solve_theorie3
            r, _i = solve_theorie3(m, {"LF1": 1.0}, "LF1", schritte=5, imperfektionen=False, stabteilung=False)
            rk = _rechnen(mk)
            if _i.fehler:
                r.u[b, 4] = math.nan
        else:
            m.load_cases["LF1"].theorie = th
            mk.load_cases["LF1"].theorie = th
            r, rk = _rechnen(m), _rechnen(mk)
        phi, phik = r.u[b, 4], rk.u[bk, 4]
        check(f"A1 lotrechte Stütze, Versatz oben 0,1 m in −Y, Fx 10 kN, Th {th}: Kopfverdrehung um Y "
              "wie Kurzstab (1e-4) und Hand F L'²/(2 E Iy) (0,5 %); vorher 0,9639 mrad",
              abs(phi / phik - 1) < 1e-4 and abs(phi / hand - 1) < 5e-3,
              f"Versatz {phi * 1e3:.4f}, Kurzstab {phik * 1e3:.4f}, Hand {hand * 1e3:.4f} mrad")


def test_stuetze_lokale_streckenlast():
    """Fall B des Befunds: Versatz oben (0; 0; 0,1) lokal = 0,1 m in +X,
    lokale qz = 1 kN/m (lokal z der Knotenlinie = +X). Der Stab liegt
    zwischen (0; 0; 0) und (0,1; 0; 4), seine lokale z-Achse z' = (L; 0;
    −0,1)/L' steht senkrecht auf ihm: von Hand Rx = −qz L' · L/L' = −qz L =
    −4,0 kN und Rz = +qz L' · 0,1/L' = +0,1 kN."""
    m, a, b, e = _stuetze("versatz", [0, 0, 0.1], stablast={"qz": 1e3, "system": "local"})
    r = _rechnen(m)
    Lp = math.hypot(L, 0.1)
    # Kurzstab: der Stab von (0,0,0) nach (0,1; 0; 4); local_axes nimmt dort
    # (ref Z) y = +Y wie die Knotenlinie die y = −Y: Drehwinkel 180°
    mk, ak, bk, ek = _stuetze("kurzstab", [0, 0, 0.1], stablast={"qz": 1e3, "system": "local"}, roll=math.pi)
    rk = _rechnen(mk)
    ok = abs(r.reactions[a, 0] / (-1e3 * L) - 1) < 1e-9 and abs(r.reactions[a, 2] / 100.0 - 1) < 1e-9         and np.allclose(r.reactions[a, :3], rk.reactions[ak, :3], rtol=0, atol=1e-6 * 1e3 * Lp)
    check("A1 lotrechte Stütze, Versatz oben 0,1 m in +X, lokale qz 1 kN/m: Lager Rx = −qz L, Rz = +0,1 kN "
          "(Hand) und wie Kurzstab; vorher Rx +4,0 kN", ok,
          f"R {np.round(r.reactions[a, :3] / 1e3, 5)} kN, Kurzstab {np.round(rk.reactions[ak, :3] / 1e3, 5)}")


def test_drehwinkel_lotrecht():
    """Lotrechte Stütze mit Drehwinkel 30° und Versatz in y und z oben, Fx und
    Fy am Kopf: wie das Kurzstabmodell mit den Achsen der Behebung (Drehwinkel
    des Kurzstabs aus den Achsen gerechnet)."""
    from statik3d import assemble as asm
    from statik3d.elements import beam3d as bm
    r2, roll = [0, 0.08, -0.06], math.radians(30)
    last = {"Fx": 8e3, "Fy": -5e3, "Mz": 300.0}
    m, a, b, e = _stuetze("versatz", r2, last=last, roll=roll)
    T3, _Lp = asm.stab_achsen(m, m.elements[e])
    # Drehwinkel, mit dem local_axes fuer die Stablinie dieselben Achsen gibt
    X = m.nodes[m.elements[e].nodes]
    arme = asm.stab_arme(m, m.elements[e])
    T0, _ = bm.local_axes(X[0] + arme[0], X[1] + arme[1], 0.0)
    roll_k = math.atan2(float(T3[1] @ T0[2]), float(T3[1] @ T0[1]))
    mk, ak, bk, ek = _stuetze("kurzstab", r2, last=last, roll=roll_k, roll_n=roll)
    Tk, _ = bm.local_axes(mk.nodes[mk.elements[ek].nodes[0]], mk.nodes[mk.elements[ek].nodes[1]], roll_k)
    r, rk = _rechnen(m), _rechnen(mk)
    rel = float(np.abs(r.u[b] - rk.u[bk]).max() / np.abs(rk.u[bk]).max())
    check("A1 lotrechte Stütze, Drehwinkel 30°, Versatz oben in y und z, Fx/Fy/Mz: Kopfverschiebung und "
          "-verdrehung wie das Kurzstabmodell mit denselben Achsen (1e-5)",
          np.allclose(Tk, T3, atol=1e-12) and rel < 1e-5,
          f"rel {rel:.2e}, u {np.round(r.u[b, :3] * 1e3, 4)} / {np.round(rk.u[bk, :3] * 1e3, 4)} mm")


def test_bitgleich():
    """Ohne Versatz und mit gleichem Versatz an beiden Enden: die Achsen des
    Stabs sind bitgleich die von local_axes der Knotenlinie, die der Theorie
    III. Ordnung (Stab zwischen den parallel verschobenen Enden) bitgleich die
    von local_axes zwischen diesen Enden - wie vor der Behebung."""
    from statik3d import assemble as asm
    from statik3d.elements import beam3d as bm
    ok = True
    for kopf in ((0, 0, L), (3.0, 1.0, 2.0)):
        for ex in (None, [[0, 0.1, -0.2], [0, 0.1, -0.2]], [[0, 0, 0], [0, 0, 0]]):
            m, _a, _b, e = _stuetze("versatz", [0, 0, 0], kopf=kopf, roll=0.3)
            el = m.elements[e]
            el.exzentrizitaet = ex
            X = m.nodes[el.nodes]
            T3a, La = bm.local_axes(X[0], X[1], 0.3)
            T3, Lp = asm.stab_achsen(m, el)
            ok = ok and np.array_equal(T3, T3a) and Lp == La
            if ex:
                rr = np.asarray(ex[0], float)
                P = X + T3a.T @ rr
                _kl, T3p, _T, Lpp = asm.beam_local(m, el, P)
                T3q, Lq = bm.local_axes(P[0], P[1], 0.3)
                ok = ok and np.array_equal(T3p, T3q) and Lpp == Lq
    check("A1 ohne Versatz und mit gleichem Versatz: Achsen und Länge bitgleich wie vor der Behebung "
          "(auch Theorie III. Ordnung)", ok)


# ---------------------------------------------------------------- A2 Th III Stablast
def _kragarm_th3(art, e, n, q):
    """Kragarm 4 m entlang x, Versatz (0; 0; e) an beiden Enden jedes Elements
    bzw. Stab an eigenen Knoten über steife Kurzstäbe (Beleg s1 des
    Prüfagenten 6); Streckenlast qz global auf jedem Stabelement."""
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=NU, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=1e-4, Iz=1e-4, It=1.5e-4, zmax=0.1, ymax=0.05))
    m.add_section(Section("STARR", A=1.0, Iy=0.1, Iz=0.1, It=0.1, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    ids = [m.add_node(L * k / n, 0, 0) for k in range(n + 1)]
    els = []
    if art == "versatz":
        for k in range(n):
            els.append(m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q",
                                     exzentrizitaet=[[0, 0, e], [0, 0, e]]))
    else:
        st = [m.add_node(L * k / n, 0, e) for k in range(n + 1)]
        for k in range(n):
            els.append(m.add_element("beam", [st[k], st[k + 1]], "ST", "Q"))
        for a, b in zip(ids, st):
            m.add_element("beam", [a, b], "ST", "STARR")
    m.fix(ids[0], "all")
    for el in els:
        m.load_beam(el, qz=q)
    m.load_cases["LF1"].theorie = "III"
    return m, ids, els


def test_th3_stablast_versatz():
    """Weg 1 das Kurzstabmodell, Weg 2 das Moment der Last um die Einspannung
    aus der Lage der Stabenden x + R a des Versatzmodells selbst."""
    from statik3d.theorie3 import solve_theorie3, rot_exp
    e, n = 0.5, 8
    for q, vorher in ((-60e3, "477,20"), (-400e3, "3061,42")):
        mA, iA, _ = _kragarm_th3("versatz", e, n, q)
        mB, iB, _ = _kragarm_th3("kurzstab", e, n, q)
        rA, infA = solve_theorie3(mA, {"LF1": 1.0}, "LF1", schritte=20, imperfektionen=False, stabteilung=False)
        rB, infB = solve_theorie3(mB, {"LF1": 1.0}, "LF1", schritte=20, imperfektionen=False, stabteilung=False)
        MA, MB = rA.reactions[iA[0], 4], rB.reactions[iB[0], 4]
        X0 = np.asarray(mA.nodes, float)
        pos = np.array([X0[k] + rA.u[k, :3] + rot_exp(rA.u[k, 3:]) @ np.array([0, 0, e]) for k in iA])
        Ml = sum(np.cross(0.5 * (pos[k] + pos[k + 1]) - X0[iA[0]], [0, 0, q * L / n])[1] for k in range(n))
        check(f"A2 Th III, Kragarm, Versatz 0,5 m, qz {q / 1e3:.0f} kN/m: Einspannmoment wie Kurzstab (0,1 %) "
              f"und wie das Moment der Last aus der Lage der Stabenden (0,2 %); vorher {vorher} kNm",
              not infA.fehler and not infB.fehler and abs(MA / MB - 1) < 1e-3 and abs(-MA / Ml - 1) < 2e-3,
              f"Versatz {MA / 1e3:.2f}, Kurzstab {MB / 1e3:.2f}, Lage {-Ml / 1e3:.2f} kNm")


# ---------------------------------------------------------------- A3 Knicken mit Sollkraft
def _zugband(art, soll, F0=70e3, teile=16, arm=0.3):
    """Kragstütze 3 m mit Zugband vom Boden (2; 0; 0) zum Kopf, am Kopf ein
    Arm längs des Bandes (Beleg p8 des Prüfagenten 5)."""
    from statik3d.model import Model, Material, Section
    m = Model("Zugband")
    m.add_material(Material("S355", E=E, nu=NU, rho=0.0, fy=355e6))
    q = Section.rectangle("Q", 0.2, 0.2)
    q.Asy = q.Asz = 0.0
    m.add_section(q)
    m.add_section(Section.circle("D", 0.03))
    m.add_section(Section("STARR", A=10.0, Iy=1.0, Iz=1.0, It=1.0, zmax=0.1, ymax=0.1))
    kn = [m.add_node(0.0, 0.0, 3.0 * k / teile) for k in range(teile + 1)]
    c = m.add_node(2.0, 0.0, 0.0)
    m.fix(kn[0], "all")
    m.fix(c, "all")
    for k in range(teile):
        m.add_element("beam", [kn[k], kn[k + 1]], "S355", "Q")
    kopf = np.array([0.0, 0.0, 3.0])
    t = kopf - np.array([2.0, 0.0, 0.0])
    t /= np.linalg.norm(t)
    if art == "versatz":
        band = m.add_element("beam", [c, kn[-1]], "S355", "D", exzentrizitaet=[[0, 0, 0], [-arm, 0, 0]])
    else:
        p = m.add_node(*(kopf - arm * t))
        band = m.add_element("beam", [c, p], "S355", "D")
        m.add_element("beam", [p, kn[-1]], "S355", "STARR")
    m.add_member("Band", [band])
    m.add_load_case("V").gravity = [0, 0, 0]
    m.add_vorspannung("Band", F0, case="V", sollkraft=soll)
    m.design.imperfektionen = False
    return m, band


def _knick(m):
    from statik3d import solver
    rb = solver.solve_buckling(m, nmodes=4, case="V")
    f = np.asarray(rb.buckling_factors, float)
    return float(f[f > 0].min())


def test_knicken_sollkraft():
    """Weg 1 das Kurzstabmodell mit Sollkraft, Weg 2 der Versatz mit einer
    Anfangsdehnung, die dieselbe Bandkraft 70 kN gibt (feq trägt die Kraft)."""
    from statik3d import solver
    for arm, vorher in ((0.3, "88,34"), (-0.3, "1038,76")):
        a = _knick(_zugband("versatz", True, arm=arm)[0])
        b = _knick(_zugband("kurzstab", True, arm=arm)[0])
        m1, band = _zugband("versatz", False, arm=arm)
        r1 = solver.solve_static(m1, case="V")
        be = np.asarray(r1.beam_end[band], float)
        N1 = 0.5 * (be[6] - be[0])
        c = _knick(_zugband("versatz", False, F0=70e3 * 70e3 / N1, arm=arm)[0])
        check(f"A3 Knicken, Zugband mit Sollkraft 70 kN, Arm {arm:+.1f} m längs des Bandes: Faktor wie "
              f"Kurzstab und wie Anfangsdehnung (1e-3); vorher {vorher}",
              abs(a / b - 1) < 1e-3 and abs(a / c - 1) < 1e-3,
              f"Versatz/Soll {a:.4f}, Kurzstab/Soll {b:.4f}, Versatz/Anfangsdehnung {c:.4f}")


def test_alpha_cr_auto_sollkraft():
    """alpha_cr im Modus „auto“ (check_theorie2) mit einer Sollkraft: wie das
    Knicken derselben Kombination (solve_buckling) und wie das Kurzstabmodell.
    Vorher fehlte die Verriegelung ganz: „keine Normalkräfte“, α_cr = ∞."""
    from statik3d import solver, theorie2
    for arm in (0.3, -0.3):
        m, band = _zugband("versatz", True, arm=arm)
        m.add_combination("K1", {"V": 1.0}, "ULS")
        m.design.theorie2 = "auto"
        rb = solver.solve_buckling(m, nmodes=4, combination="K1")
        f = np.asarray(rb.buckling_factors, float)
        lb = float(f[f > 0].min())
        info = theorie2.check_theorie2(m, None, ["K1"]).kombinationen["K1"]
        b = _knick(_zugband("kurzstab", True, arm=arm)[0])
        check(f"A3 α_cr im Modus „auto“ mit Sollkraft 70 kN, Arm {arm:+.1f} m: wie Knicken der Kombination "
              "und wie Kurzstab (1e-3); vorher ∞",
              math.isfinite(info.alpha_cr) and abs(info.alpha_cr / lb - 1) < 1e-3 and abs(info.alpha_cr / b - 1) < 1e-3,
              f"auto {info.alpha_cr:.4f}, Knicken {lb:.4f}, Kurzstab {b:.4f}")


# ---------------------------------------------------------------- A4 Konvergenz Th II
def _stuetze_seitlich(e, P, n=16, quer=None):
    """Gelenkstütze 4 m, gleicher seitlicher Versatz (0; 0; e) an allen
    Elementen, Druck P in der Knotenlinie, Querlast in Stabmitte (Beleg p3 des
    Prüfagenten 5)."""
    from statik3d.model import Model, Material, Section
    m = Model("S")
    m.add_material(Material("ST", E=E, nu=NU, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=1e-4, Iz=1e-4, It=1e-5, zmax=0.1, ymax=0.05))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    ids = [m.add_node(L * k / n, 0, 0) for k in range(n + 1)]
    for k in range(n):
        m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q", exzentrizitaet=[[0, 0, e], [0, 0, e]])
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2])
    m.load_node(ids[-1], Fx=-P)
    if quer:
        m.load_node(ids[n // 2], **quer)
    m.load_cases["LF1"].theorie = "II"
    return m, ids


def _p_fuer(ziel, e=0.3):
    from statik3d import solver, theorie2
    m, _ids = _stuetze_seitlich(e, 100e3)
    sy = solver.StaticSystem(m)
    F, feq, _q, _t = solver.case_loads(m, {"LF1": 1.0})
    a100 = theorie2.alpha_cr(m, sy, sy.solve(F), feq=feq)["alpha_cr"]
    return 100e3 * a100 / ziel


def test_theorie2_konvergenz():
    """α_cr 1,4: die Iteration mit dem schiefsymmetrischen Teil als Last
    stockte. Weg 1 das Programm, Weg 2 die dichte Lösung derselben Gleichung
    (K + K_G(u) + K_a(u)) u = F mit der vollen Matrix je Schritt."""
    from statik3d import theorie2, solver, assemble as asm
    P = _p_fuer(1.4)
    quer = {"Fy": 1e3, "Fz": 1e3}
    m, ids = _stuetze_seitlich(0.3, P, quer=quer)
    r2, info = theorie2.solve_theorie2(m, {"LF1": 1.0}, "LF1", imperfektionen=False, stabteilung=False)
    m, ids = _stuetze_seitlich(0.3, P, quer=quer)
    sy = solver.StaticSystem(m)
    F, feq, _q, _t = solver.case_loads(m, {"LF1": 1.0})
    fi = sy.fi
    K = sy.Kff.toarray()
    u = sy.solve(F)
    for _it in range(200):
        Kg = asm.geometric_stiffness(m, u, feq=feq).toarray()
        un = np.zeros(m.ndof)
        un[fi] = np.linalg.solve(K + Kg[np.ix_(fi, fi)], F[fi])
        d = np.abs(un - u).max() / np.abs(un).max()
        u = un
        if d < 1e-11:
            break
    mi = ids[len(ids) // 2]
    ref = u.reshape(-1, 6)[mi]
    rel = float(np.abs(r2.u[mi] - ref).max() / np.abs(ref).max())
    phx = r2.u[mi, 3]
    check("A4 Th II, Stütze mit Versatz 0,3 m, α_cr 1,4: konvergiert, Mitte wie die dichte Lösung mit voller "
          "Matrix (1e-4, φx auf 1 %); vorher nach 30 Schritten 0,355 %",
          info.gerechnet and not info.fehler and info.konvergenz < 1e-6 and rel < 1e-4
          and abs(phx / ref[3] - 1) < 1e-2,
          f"it {info.iterationen}, φx {phx * 1e3:.4f} / dicht {ref[3] * 1e3:.4f} mrad, rel {rel:.2e}")
    # bleibt sie unkonvergiert (hier: zu wenige Schritte erlaubt), ist es ein Fehler
    m, ids = _stuetze_seitlich(0.3, P, quer=quer)
    r3, info3 = theorie2.solve_theorie2(m, {"LF1": 1.0}, "LF1", imperfektionen=False, stabteilung=False,
                                        max_iter=3)
    check("A4 Th II mit Versatz unkonvergiert (3 Schritte erlaubt): Fehler mit klarer Meldung, nicht gerechnet",
          not info3.gerechnet and "nicht konvergiert" in info3.fehler and "e-" not in info3.fehler,
          info3.fehler[:140])


# ---------------------------------------------------------------- A10 Meldung
def test_versatz_laenge_null():
    from statik3d.model import Model, Material, Section
    out = {}
    for name, r1, r2 in (("null", [2.0, 0, 0], [-2.0, 0, 0]), ("umgekehrt", [3.0, 0, 0], [-3.0, 0, 0]),
                         ("normal", [0.5, 0, 0], [-0.5, 0.1, 0])):
        m = Model("T")
        m.add_material(Material("ST", E=E, nu=NU, rho=0.0, fy=355e6))
        m.add_section(Section("Q", A=1e-2, Iy=1e-4, Iz=2e-4, It=1e-5, zmax=0.1, ymax=0.05))
        a, b = m.add_node(0, 0, 0), m.add_node(4, 0, 0)
        m.add_element("beam", [a, b], "ST", "Q", exzentrizitaet=[r1, r2])
        m.fix(a, "all")
        m.load_node(b, Fz=-1e3, case="LF1")
        out[name] = [s for s in m.check() if "Versatz" in s]
    check("A10 axialer Versatz legt die Stabenden aufeinander: FEHLER in der Modellprüfung mit Hinweis auf "
          "den Versatz (Element ab 0 gezählt); vorher keine Meldung",
          len(out["null"]) == 1 and out["null"][0].startswith("FEHLER") and "Element 0" in out["null"][0],
          out["null"][0][:160] if out["null"] else "keine Meldung")
    check("A10 … Versatz kehrt den Stab um: WARNUNG mit Hinweis auf den Versatz; normaler Versatz: keine",
          len(out["umgekehrt"]) == 1 and out["umgekehrt"][0].startswith("WARNUNG") and not out["normal"],
          (out["umgekehrt"] or ["keine Meldung"])[0][:160])


# ---------------------------------------------------------------- Verfahrenstabelle
def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("versatz_achsen_lotrecht")
    ok = mk is not None and mk.wechsel[-1].stand == 41 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR \
        and rv.VERFAHRENSSTAND >= 41
    m_ja, _a, _b, _e = _stuetze("versatz", [0, 0.1, 0])                        # A1
    m_nein, _a, _b, _e = _stuetze("versatz", [0, 0, 0])
    m_gleich, _ids, _els = _kragarm_th3("versatz", 0.5, 2, -1e3)               # A2 (Stablast, Th III)
    m_gleich.load_cases["LF1"].beam_loads.clear()
    m_th3, _ids, _els = _kragarm_th3("versatz", 0.5, 2, -1e3)
    m_soll, _band = _zugband("versatz", True)                                  # A3
    m_soll0, _band = _zugband("kurzstab", False)
    ok = ok and mk is not None and mk.betrifft(m_ja) and not mk.betrifft(m_nein) \
        and mk.betrifft(m_th3) and not mk.betrifft(m_gleich) and mk.betrifft(m_soll) \
        and not mk.betrifft(m_soll0)
    check("Verfahrenstabelle: „Achsen und Arm bei Stäben mit Versatz“ Stand 41 als Fehlerkorrektur; "
          "betroffen verschiedener Versatz, Stablast mit Versatz nach Th III, Sollkraft mit Arm bzw. α_cr auto",
          ok, f"Stand {rv.VERFAHRENSSTAND}")


def main():
    np.set_printoptions(suppress=True)
    for t in (test_achsen_stetig, test_stuetze_kopfverdrehung, test_stuetze_lokale_streckenlast,
              test_drehwinkel_lotrecht, test_bitgleich, test_th3_stablast_versatz, test_knicken_sollkraft,
              test_alpha_cr_auto_sollkraft, test_theorie2_konvergenz, test_versatz_laenge_null,
              test_verfahrenstabelle):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
