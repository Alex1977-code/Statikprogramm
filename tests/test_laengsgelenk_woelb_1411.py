"""
Befunde B1 bis B3 der Befundliste vom 14.11.2026 (Gruppe B, Theorie II./III.
Ordnung).

B1: Ein Laengsgelenk (lokaler FHG ux frei) liess asm.stab_normalkraft pauschal
N = 0 liefern, auch wenn eine Stablast in Stabrichtung im Stab Druck erzeugt.
K_G, alpha_cr, das Einzelknicken und die Auswahl der internen Stabteilung
rechneten damit; der Feldanteil N w nahm die Stabendkraft fl[0] (am Gelenk am
Anfang also 0), Theorie III. Ordnung ebenfalls N = 0. Stuetze 5 m, gelenkig,
Q L = 6 MN in Stabrichtung, Querlast 1 kN/m: alpha_cr „unendlich“ statt 2,600,
nach Theorie III. Ordnung 3,125 statt 5,07 kNm.

B2: Gelenke und Federgelenke an Balken mit Woelbkrafttorsion fehlten in der
Steifigkeit (assemble.element_matrix, Woelbzweig ohne Kondensation), die Last
wurde kondensiert: Einfeldtraeger 6 m eingespannt/Gelenk, q = 5 kN/m,
Gelenkmoment 16,875 statt 0 kNm, Lagermoment 15,94 statt 22,50 kNm.

B3: Theorie III. Ordnung mit Woelbkrafttorsion brach mit „Gleichungssystem
singulär: cannot reshape …“ ab. Entscheidung des Anwenders: vorher erkennen
und mit Klartext abweisen, auch in der Modellpruefung.

Zwei Wege je Zahl: die Differentialgleichung (finite Differenzen,
unabhaengig vom Programm) bzw. die Handformel und dasselbe System ohne
Gelenk bzw. ohne Woelbkrafttorsion im Programm.

Aufruf:  python -m tests.test_laengsgelenk_woelb_1411
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
E = 210e9
I = 1e-4
EI = E * I


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def nahe(name, ist, soll, rel):
    ok = math.isfinite(ist) and abs(ist - soll) <= rel * max(abs(soll), 1e-30)
    return check(name, ok, f"ist {ist:.6g}, soll {soll:.6g} (±{rel * 100:g} %)")


# --------------------------------------------------------------------------
# B1: Stuetze mit Laengsgelenk und Last in Stabrichtung
# --------------------------------------------------------------------------
L1 = 5.0
QX = 1e3            # quer, N/m
QL = 1.2e6          # in Stabrichtung, N/m (Q L = 6 MN)


def _stuetze(art, theorie="II", n=1, umgedreht=False, laengslast=True):
    """A: Laengsgelenk oben, Kopf in z gehalten; B: ohne Gelenk, Kopf in z
    frei - dasselbe System. ``umgedreht``: Elemente von oben nach unten, das
    Laengsgelenk (A) am Stabanfang."""
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=0.01, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.05))
    m.design.imperfektionen = False
    ids = [m.add_node(0, 0, L1 * j / n) for j in range(n + 1)]
    if umgedreht:
        els = [m.add_element("beam", [ids[j + 1], ids[j]], "ST", "Q") for j in range(n)]
    else:
        els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q") for j in range(n)]
    m.fix(ids[0], [0, 1, 2, 5])
    if art == "A":
        m.fix(ids[-1], [0, 1, 2])
        if umgedreht:
            m.add_hinge("GE", end=0, ux="free")
        else:
            m.add_hinge("GE", end=1, ux="free")
        m.apply_hinge(els[-1], "GE")
    else:
        m.fix(ids[-1], [0, 1])
    for e in els:
        # global: qz nach unten (Druck), qx quer
        m.load_beam(e, qx=QX, qz=-QL if laengslast else 0.0)
    m.load_cases["LF1"].theorie = theorie
    return m, ids, els


def _dgl():
    """Finite Differenzen der DGL EI w'''' + (P(x) w')' = q_x, P(x) = Q (L - x),
    w = w'' = 0 an beiden Enden - max|M| und alpha_cr (wie Pruefagent 6, s2)."""
    nfd = 2000
    h = L1 / nfd
    x = np.linspace(0, L1, nfd + 1)
    nn = nfd - 1
    K = np.zeros((nn, nn))
    G = np.zeros((nn, nn))
    for k in range(1, nfd):
        r = k - 1
        for off, c in ((-2, 1), (-1, -4), (0, 6), (1, -4), (2, 1)):
            j = k + off
            if j == 0 or j == nfd:
                continue
            if j == -1:
                K[r, 0] -= c * EI / h ** 4
                continue
            if j == nfd + 1:
                K[r, nn - 1] -= c * EI / h ** 4
                continue
            K[r, j - 1] += c * EI / h ** 4
        pp = QL * (L1 - (x[k] + h / 2))
        pm = QL * (L1 - (x[k] - h / 2))
        for j, c in ((k + 1, pp), (k, -(pp + pm)), (k - 1, pm)):
            if 1 <= j <= nfd - 1:
                G[r, j - 1] += c / h ** 2
    w = np.linalg.solve(K + G, np.full(nn, QX))
    wv = np.concatenate([[0.0], w, [0.0]])
    M = -EI * np.gradient(np.gradient(wv, h), h)
    ev = np.linalg.eigvals(np.linalg.solve(-G, K))
    ev = np.sort(np.real(ev[np.abs(np.imag(ev)) < 1e-9]))
    return float(np.abs(M[2:-2]).max()), float(ev[ev > 0][0])


def _max_my(m, r, els):
    from statik3d import solver
    return max(float(np.abs(solver.beam_station_forces(m, r, e, 41)["My"]).max()) for e in els)


def test_b1_theorie2():
    from statik3d import solver, theorie2
    M_dgl, a_dgl = _dgl()
    print(f"   DGL: max|My| {M_dgl / 1e3:.4f} kNm, alpha_cr {a_dgl:.4f}")
    erg = {}
    for art in ("A", "B"):
        m, ids, els = _stuetze(art)
        r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
        erg[art] = (float(r.info.get("alpha_cr") or math.inf), _max_my(m, r, els))
        print(f"   Modell {art}: alpha_cr {erg[art][0]:.4f}, max|My| {erg[art][1] / 1e3:.4f} kNm, "
              f"Teilung {r.info.get('stabteilung')}")
    nahe("B1 Th II: alpha_cr Längsgelenk = DGL 2,600", erg["A"][0], a_dgl, 0.01)
    nahe("B1 Th II: alpha_cr Längsgelenk = ohne Gelenk", erg["A"][0], erg["B"][0], 0.002)
    nahe("B1 Th II: max|My| Längsgelenk = DGL 5,0745 kNm", erg["A"][1], M_dgl, 0.005)
    nahe("B1 Th II: max|My| Längsgelenk = ohne Gelenk", erg["A"][1], erg["B"][1], 0.002)
    # die Normalkraft in K_G: Mittel -Q L/2 wie ohne Gelenk (E A Δl/L)
    m, ids, els = _stuetze("A")
    sy = solver.StaticSystem(m)
    F, feq, _q, _t = solver.case_loads(m, {"LF1": 1.0})
    u = sy.solve(F)
    nA = theorie2.normalkraefte_kg(m, u, feq=feq)[els[0]]
    nahe("B1: N in K_G am Längsgelenk = -Q L/2 = -3000 kN", nA, -0.5 * QL * L1, 1e-9)


def test_b1_gelenk_am_anfang():
    """Feldanteil N w: Laengsgelenk am Stabanfang (fl[0] = 0) und am Stabende
    rechnen dasselbe, ein Element ohne Stabteilung."""
    from statik3d import theorie2
    mx = []
    for umg in (False, True):
        m, ids, els = _stuetze("A", umgedreht=umg)
        r, info = theorie2.solve_theorie2(m, {"LF1": 1.0}, "LF1", imperfektionen=False, stabteilung=False)
        mx.append((_max_my(m, r, els), info.alpha_cr))
        print(f"   Gelenk am {'Anfang' if umg else 'Ende'}: max|My| {mx[-1][0] / 1e3:.4f} kNm, "
              f"alpha_cr {mx[-1][1]:.4f}")
    nahe("B1 Feldanteil: Gelenk am Stabanfang = am Stabende (max|My|)", mx[1][0], mx[0][0], 1e-6)
    nahe("B1 Feldanteil: Gelenk am Stabanfang = am Stabende (alpha_cr)", mx[1][1], mx[0][1], 1e-6)
    check("B1 Feldanteil: ein Element über q L²/8 (Normalkraft wirkt)", mx[1][0] > 1.2 * QX * L1 ** 2 / 8,
          f"{mx[1][0] / 1e3:.4f} gegen {QX * L1 ** 2 / 8e3:.4f} kNm")


def test_b1_ohne_laengslast_unveraendert():
    """Ohne Last in Stabrichtung traegt das Laengsgelenk keine Normalkraft
    (Befund 33 vom 11.11.2026): q L²/8 = 3,125 kNm, kein alpha_cr."""
    from statik3d import solver
    m, ids, els = _stuetze("A", laengslast=False)
    r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
    nahe("B1 ohne Längslast: max|My| = q L²/8", _max_my(m, r, els), QX * L1 ** 2 / 8, 1e-6)
    check("B1 ohne Längslast: kein alpha_cr", not math.isfinite(float(r.info.get("alpha_cr") or math.inf)),
          f"{r.info.get('alpha_cr')}")


def test_b1_kragstuetze():
    """Beleg Pruefagent 4 (b2): Kragstuetze 4 m, Last in Stabrichtung q = 1 MN/m
    lokal, H = 1 kN am Kopf. Laengsgelenk oben (Kopf lotrecht gehalten) gegen
    ohne Gelenk (Kopf frei) - dasselbe System, Fussmoment gleich."""
    from statik3d.model import Model, Material, Section
    from statik3d import solver
    q, H, L = 1.0e6, 1e3, 4.0

    def bau(gelenk, n):
        m = Model("T")
        m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
        m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=1e-4, zmax=0.1, ymax=0.1))
        m.design.imperfektionen = False
        m.netz.stabteilung = 1
        ids = [m.add_node(0, 0, L * k / n) for k in range(n + 1)]
        els = [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q") for k in range(n)]
        m.case("LF1")
        m.load_cases["LF1"].theorie = "II"
        for e in els:
            m.load_beam(e, qx=-q, system="local", case="LF1")
        if gelenk:
            m.elements[els[-1]].hinges = [6]
            m.fix(ids[-1], [2])
        m.fix(ids[0], "all")
        m.load_node(ids[-1], Fx=H, case="LF1")
        return m, ids

    for n in (1, 4):
        werte = []
        for g in (False, True):
            m, ids = bau(g, n)
            r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
            werte.append(float(r.reactions[ids[0], 4]))
        print(f"   n = {n}: ohne Gelenk {werte[0] / 1e3:.4f}, Längsgelenk {werte[1] / 1e3:.4f} kNm")
        nahe(f"B1 Kragstütze n = {n}: Fußmoment Längsgelenk = ohne Gelenk", werte[1], werte[0], 1e-6)


def test_b1_theorie3():
    """Theorie III. Ordnung rechnet den P-Δ-Anteil aus der mitgedrehten
    inneren Kraft; ein Element mit Laengsgelenk traegt seine Laengslast dort
    nicht (sie steht als Knotenlast am anderen Ende), darum braucht es die
    interne Stabteilung - deren Auswahl (stabteilung.kraefte_theorie1) sah am
    Laengsgelenk N = 0 und teilte nicht: 3,125 statt 5,07 kNm."""
    from statik3d import solver
    M_dgl, _a = _dgl()
    mx = {}
    for art in ("A", "B"):
        m, ids, els = _stuetze(art, "III")
        r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
        mx[art] = _max_my(m, r, els)
        print(f"   Th III solve_all, Modell {art}: max|My| {mx[art] / 1e3:.4f} kNm ({r.info.get('theorie')!r})")
        if art == "A":
            check("B1 Th III: Ergebnis nach Theorie III. Ordnung",
                  str(r.info.get("theorie", "")).startswith("III"), f"{r.info.get('theorie')!r}")
    nahe("B1 Th III: max|My| Längsgelenk = DGL 5,0745 kNm", mx["A"], M_dgl, 0.01)
    nahe("B1 Th III: max|My| Längsgelenk = ohne Gelenk", mx["A"], mx["B"], 0.005)
    from statik3d.stabteilung import kraefte_theorie1
    m, ids, els = _stuetze("A", "III")
    n1 = kraefte_theorie1(m, solver.StaticSystem(m), {"LF1": 1.0})[els[0]]
    nahe("B1 Stabteilung: Normalkraft der Auswahl am Längsgelenk = -Q L/2", n1, -0.5 * QL * L1, 1e-9)


# --------------------------------------------------------------------------
# B2: Gelenk und Federgelenk an Balken mit Woelbkrafttorsion
# --------------------------------------------------------------------------
L2 = 6.0
Q2 = 5e3


def _einfeld(woelb, theorie="II", feder=None, torsion=0.0):
    """Einfeldtraeger 6 m in zwei Elementen, links eingespannt, rechts
    eingespannt mit Gelenk phi_y am Stabende (bzw. Federgelenk ``feder``),
    x frei, Druck 0,6 N_cr (eingespannt/gelenkig), q = 5 kN/m (Pruefagent 6, s3)."""
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.05))
    m.sections["Q"].Iw = 1e-7
    m.design.imperfektionen = False
    n = 2
    ids = [m.add_node(L2 * j / n, 0, 0) for j in range(n + 1)]
    els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q") for j in range(n)]
    if woelb:
        for e in els:
            m.stab_woelb_setzen(e, True)
    m.fix(ids[0], "all")
    m.fix(ids[-1], [1, 2, 3, 4, 5])
    if feder is None:
        m.add_hinge("GE", end=1, phiy="free")
        m.apply_hinge(els[-1], "GE")
    else:
        m.elements[els[-1]].hinge_springs = [(10, float(feder))]
    if theorie == "II":
        m.load_node(ids[-1], Fx=-0.6 * math.pi ** 2 * EI / (0.699 * L2) ** 2)
    if torsion:
        m.load_node(ids[1], Mx=torsion)
    for e in els:
        m.load_beam(e, qz=-Q2)
    m.load_cases["LF1"].theorie = theorie
    return m, ids, els


def test_b2_gelenk():
    from statik3d import solver, theorie2
    # Theorie I: eingespannt/gelenkig, M_A = q L²/8 = 22,5 kNm (Handformel)
    erg = {}
    for w in (True, False):
        m, ids, els = _einfeld(w, "I")
        r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
        erg[w] = (float(r.reactions[ids[0], 4]), float(r.beam_forces[els[-1]]["My"][-1]))
    print(f"   Th I mit/ohne Wölb: Lager {erg[True][0] / 1e3:.4f}/{erg[False][0] / 1e3:.4f}, "
          f"Gelenk {erg[True][1] / 1e3:.4f}/{erg[False][1] / 1e3:.4f} kNm")
    nahe("B2 Th I Wölb: Lagermoment = q L²/8 = 22,5 kNm", abs(erg[True][0]), Q2 * L2 ** 2 / 8, 1e-9)
    check("B2 Th I Wölb: Moment am Gelenk 0", abs(erg[True][1]) < 1e-6, f"{erg[True][1]:.3e} Nm")
    # Theorie II: wie ohne Woelbkrafttorsion (42,78 kNm)
    erg = {}
    for w in (True, False):
        m, ids, els = _einfeld(w, "II")
        r, info = theorie2.solve_theorie2(m, {"LF1": 1.0}, "LF1", imperfektionen=False, stabteilung=False)
        st = solver.beam_station_forces(m, r, els[-1], 21)
        erg[w] = (float(r.reactions[ids[0], 4]), float(r.beam_forces[els[-1]]["My"][-1]),
                  float(np.abs(st["My"]).max()), info.alpha_cr)
    print(f"   Th II mit/ohne Wölb: Lager {erg[True][0] / 1e3:.4f}/{erg[False][0] / 1e3:.4f}, "
          f"Gelenk {erg[True][1] / 1e3:.4f}/{erg[False][1] / 1e3:.4f} kNm, "
          f"alpha_cr {erg[True][3]:.4f}/{erg[False][3]:.4f}")
    nahe("B2 Th II Wölb: Lagermoment = ohne Wölbkrafttorsion", erg[True][0], erg[False][0], 1e-6)
    nahe("B2 Th II Wölb: Feldmoment im Element mit Gelenk = ohne Wölb", erg[True][2], erg[False][2], 1e-6)
    nahe("B2 Th II Wölb: alpha_cr = ohne Wölbkrafttorsion", erg[True][3], erg[False][3], 1e-6)
    check("B2 Th II Wölb: Moment am Gelenk 0", abs(erg[True][1]) < 1e-6, f"{erg[True][1]:.3e} Nm")


def test_b2_federgelenk():
    from statik3d import solver
    erg = {}
    k = 2.0 * EI / L2
    for w in (True, False):
        m, ids, els = _einfeld(w, "I", feder=k)
        r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
        erg[w] = (float(r.reactions[ids[0], 4]), float(r.reactions[ids[-1], 4]))
    print(f"   Federgelenk Th I mit/ohne Wölb: Lager links {erg[True][0] / 1e3:.4f}/{erg[False][0] / 1e3:.4f}, "
          f"rechts {erg[True][1] / 1e3:.4f}/{erg[False][1] / 1e3:.4f} kNm")
    # Handrechnung, Kraftgroessenmethode am Kragarm (links eingespannt) mit den
    # Unbekannten V_B und M_B am rechten Ende; die Drehfeder k liegt in Reihe
    # (k -> unendlich: M_A = M_B = q L²/12, k -> 0: M_A = q L²/8)
    a = np.array([[L2 ** 3 / (3 * EI), L2 ** 2 / (2 * EI)],
                  [L2 ** 2 / (2 * EI), L2 / EI + 1.0 / k]])
    b = np.array([Q2 * L2 ** 4 / (8 * EI), Q2 * L2 ** 3 / (6 * EI)])
    VB, MB = np.linalg.solve(a, b)
    # M_B dreht dem Lastsinn entgegen und mindert das Einspannmoment
    MA = Q2 * L2 ** 2 / 2 - VB * L2 - MB
    print(f"   Hand (Kraftgrößenmethode): M_A {MA / 1e3:.4f}, M_B {MB / 1e3:.4f} kNm")
    nahe("B2 Federgelenk Wölb: Lagermoment links = Kraftgrößenmethode", abs(erg[True][0]), abs(MA), 1e-6)
    nahe("B2 Federgelenk Wölb: Lagermoment links = ohne Wölb", erg[True][0], erg[False][0], 1e-9)
    nahe("B2 Federgelenk Wölb: Lagermoment rechts = ohne Wölb", erg[True][1], erg[False][1], 1e-9)


def test_b2_torsion_bleibt():
    """Ein Biegegelenk aendert die Woelbkrafttorsion nicht: Torsionsmoment in
    Feldmitte, beidseits gabelgelagert und woelbbehindert eingespannt - die
    Verdrehung mit und ohne Biegegelenk gleich."""
    from statik3d import solver
    phi = []
    for gel in (True, False):
        m, ids, els = _einfeld(True, "I", torsion=1e3)
        if not gel:
            m.elements[els[-1]].hinges = []
        r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
        phi.append(float(r.u[ids[1], 3]))
    print(f"   phi_x Mitte mit/ohne Biegegelenk: {phi[0] * 1e3:.6f}/{phi[1] * 1e3:.6f} mrad")
    nahe("B2 Torsion: Verdrehung mit Biegegelenk = ohne", phi[0], phi[1], 1e-9)


# --------------------------------------------------------------------------
# B3: Theorie III. Ordnung mit Woelbkrafttorsion
# --------------------------------------------------------------------------
def _kragarm_woelb(theorie):
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=5e-3, Iy=8e-5, Iz=4e-6, It=2e-7, zmax=0.15, ymax=0.075))
    m.sections["Q"].Iw = 5e-7
    m.design.imperfektionen = False
    n = 8
    ids = [m.add_node(4.0 * j / n, 0, 0) for j in range(n + 1)]
    els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q") for j in range(n)]
    for e in els[3:]:
        m.stab_woelb_setzen(e, True)
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Mx=1e3)
    m.load_cases["LF1"].theorie = theorie
    return m, ids, els


TEXT_B3 = "Theorie III. Ordnung rechnet keine Wölbkrafttorsion"


def test_b3():
    from statik3d import solver
    from statik3d.theorie3 import solve_theorie3
    m, ids, els = _kragarm_woelb("III")
    try:
        solve_theorie3(m, {"LF1": 1.0}, "LF1", schritte=2, imperfektionen=False, stabteilung=False)
        text = ""
    except Exception as ex:          # noqa: BLE001
        text = str(ex)
    print(f"   Meldung: {text}")
    check("B3: Th III mit Wölbkrafttorsion abgewiesen mit Klartext", TEXT_B3 in text and "singulär" not in text)
    check("B3: Meldung nennt das erste Element ab 0 (Element 3) und den Ausweg",
          "Element 3" in text and "ab 0 gezählt" in text and "Theorie II. Ordnung" in text
          and "abschalten" in text)
    an = solver.solve_all(m, workers=1, design=False)
    info = an.theorie3.kombinationen.get("LF1") if an.theorie3 is not None else None
    fehler = getattr(info, "fehler", "") or ""
    check("B3: solve_all trägt den Klartext als Fehler der Th-III-Rechnung", TEXT_B3 in fehler, fehler[:120])
    msgs = m.check()
    treffer = [z for z in msgs if TEXT_B3 in z]
    check("B3: Modellprüfung meldet es vor dem Rechnen als FEHLER",
          len(treffer) == 1 and treffer[0].startswith("FEHLER"), "; ".join(treffer)[:160])
    m2, _i, _e = _kragarm_woelb("II")
    check("B3: Modellprüfung nach Theorie II. Ordnung ohne diese Meldung",
          not any(TEXT_B3 in z for z in m2.check()))


# --------------------------------------------------------------------------
# Verfahrenstabelle
# --------------------------------------------------------------------------
def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    check("Verfahrensstand mindestens 48", rv.VERFAHRENSSTAND >= 48, f"{rv.VERFAHRENSSTAND}")
    a = rv.merkmal("laengsgelenk_laengslast")
    b = rv.merkmal("woelb_gelenk")
    check("Merkmal laengsgelenk_laengslast mit Stand 48", a is not None and any(w.stand == 48 for w in a.wechsel))
    check("Merkmal woelb_gelenk mit Stand 48", b is not None and any(w.stand == 48 for w in b.wechsel))
    if a is not None:
        check("… betroffen: Längsgelenk mit Längslast ja, ohne Längslast nein, ohne Gelenk nein",
              a.betrifft(_stuetze("A")[0]) and not a.betrifft(_stuetze("A", laengslast=False)[0])
              and not a.betrifft(_stuetze("B")[0]))
    if b is not None:
        m_f = _einfeld(True, "I", feder=1e6)[0]
        check("… betroffen: Wölbbalken mit Gelenk/Federgelenk ja, ohne Wölb nein",
              b.betrifft(_einfeld(True)[0]) and b.betrifft(m_f) and not b.betrifft(_einfeld(False)[0])
              and not b.betrifft(_kragarm_woelb("I")[0]))


def main():
    for t in (test_b1_theorie2, test_b1_gelenk_am_anfang, test_b1_ohne_laengslast_unveraendert,
              test_b1_kragstuetze, test_b1_theorie3, test_b2_gelenk, test_b2_federgelenk,
              test_b2_torsion_bleibt, test_b3, test_verfahrenstabelle):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
