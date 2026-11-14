"""
Versatz der Stabenden als starrer Arm nach Theorie I. und II. Ordnung,
12.11.2026.

Nachstellung am Stand cf2713c: Kragarm L = 4 m in einem Element, Versatz
nur am Stabende (0; 0; 0,1) m (lokal = global z), Zug F = 50 kN in der
Knotenlinie an der Spitze. Die Zuglinie geht durch die Einspannung, das
Einspannmoment ist 0 (Hand). Theorie I. Ordnung gab 5,000 kNm und eine
Momentensumme um die Einspannung von 5,000 kNm statt 0: der Stab lag auf
der Knotenlinie (Laenge und Achsen von dort), nur seine Enden waren starr
versetzt - verschiedener Versatz an den Enden verdreht den Stab aber.

Seither liegt der Stab zwischen seinen Stabenden P_i = x_i + a_i (Laenge
und lokale Achsen aus den versetzten Punkten, assemble.stab_achsen), der
Versatz ist ein starrer Arm am Knoten (assemble.stab_versatz) - wie Theorie
III. Ordnung seit Stand 34. Gleicher Versatz an beiden Enden verschiebt den
Stab nur parallel und rechnet wie bisher (bitgleich).

Zwei Wege je Zahl:
1. Handrechnung (Einspannmoment, Momentensumme, Spitzenverschiebung,
   Stabendkraefte, Auflagersumme der Stablasten);
2. dasselbe System mit dem Stab an eigenen Knoten, ueber steife Kurzstaebe
   an die Knotenlinie gehaengt (wie tests/test_theorie3_versatz.py) - ohne
   jeden Versatz im Programm.

Aufruf:  python -m tests.test_versatz_starrer_arm
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
E = 210e9
NU = 0.3
I = 1e-4
A = 1e-2
EI = E * I
L = 4.0
#: Kurzstaebe 1e3- bzw. 1e4-fach so steif wie der Stab (A, I); zehnfach
#: weicher aendert die Werte um weniger als 1e-5 relativ, zehnfach steifer
#: macht der 8-Elemente-Fall Rundungsrauschen bis 3e-2 oder bricht als
#: singulaer ab (kurze Kurzstaebe am eingespannten Ende)
STARR = (10.0, 1.0)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {detail}")
    return ok


def _rel(a, b, skala=None):
    a, b = np.asarray(a, float), np.asarray(b, float)
    s = float(np.max(np.abs(b))) if skala is None else float(skala)
    return float(np.max(np.abs(a - b))) / s if s > 0 else float("inf")


def _kragarm(art, r1, r2, n, lasten, theorie="I", stablasten=(), rho=0.0):
    """Kragarm entlang x, eingespannt in Knoten 0, Last ``lasten`` an der
    Spitze. art "versatz": Versatz am Element, linear von r1 (Knoten 0) bis r2
    (Spitze), je Element der Wert an seinen Enden; "kurzstab": der Stab an
    eigenen Knoten x + r, ueber Kurzstaebe angeschlossen. ``stablasten``:
    je Element des Stabs dieselben load_beam-Argumente. Rueckgabe (Modell,
    Knoten der Knotenlinie, Elemente des Stabs)."""
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=NU, rho=rho, fy=355e6))
    m.add_material(Material("ST0", E=E, nu=NU, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.05))
    m.add_section(Section("STARR", A=STARR[0], Iy=STARR[1], Iz=STARR[1], It=STARR[1], zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1              # gleiche Elemente in beiden Modellen
    r1, r2 = np.asarray(r1, float), np.asarray(r2, float)

    def r(k):
        return r1 + (r2 - r1) * k / n
    ids = [m.add_node(L * k / n, 0, 0) for k in range(n + 1)]
    if art == "versatz":
        els = [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q",
                             exzentrizitaet=[r(k).tolist(), r(k + 1).tolist()]) for k in range(n)]
    else:
        st = [m.add_node(L * k / n + r(k)[0], r(k)[1], r(k)[2]) if np.any(r(k)) else ids[k]
              for k in range(n + 1)]
        els = [m.add_element("beam", [st[k], st[k + 1]], "ST", "Q") for k in range(n)]
        for a, b in zip(ids, st):
            if a != b:
                m.add_element("beam", [a, b], "ST0", "STARR")
    for e in els:
        for kw in stablasten:
            m.load_beam(e, case="LF1", **kw)
    if rho:
        m.load_cases["LF1"].gravity = [0.0, 0.0, -9.81]
    m.fix(ids[0], "all")
    m.load_node(ids[-1], **lasten)
    m.load_cases["LF1"].theorie = theorie
    return m, ids, els


def _rechnen(m):
    from statik3d import solver
    return solver.solve_all(m, workers=1, design=False).cases["LF1"]


def _momentensumme(m, r, ids, lasten):
    """Summe der Momente um den Ursprung (unverformte Lage) aus Knotenlast und
    Auflagerkraeften."""
    X = np.asarray(m.nodes)
    Fk = np.zeros((m.nn, 6))
    Fk[ids[-1]] = [lasten.get(k, 0.0) for k in ("Fx", "Fy", "Fz", "Mx", "My", "Mz")]
    ges = Fk + r.reactions
    return sum(np.cross(X[k], ges[k, :3]) + ges[k, 3:] for k in range(m.nn))


# ---------------------------------------------------------------- Nachstellung
def test_kragarm_zug():
    e, F = 0.1, 50e3
    last = {"Fx": F}
    mv, iv, ev = _kragarm("versatz", (0, 0, 0), (0, 0, e), 1, last)
    mk, ik, ek = _kragarm("kurzstab", (0, 0, 0), (0, 0, e), 1, last)
    rv, rk = _rechnen(mv), _rechnen(mk)
    My0 = float(rv.reactions[iv[0], 4])
    check("Th I, Kragarm, Zug 50 kN durch die Einspannung, Versatz (0; 0; 0,1) m nur am Ende: "
          "Einspannmoment 0 (Hand; vorher 5,000 kNm)", abs(My0) < 1e-6 * F * e, f"My = {My0 / 1e3:.6f} kNm")
    Mges = _momentensumme(mv, rv, iv, last)
    check("… ΣM um die Einspannung = 0 (auf 1e-9 F L; vorher 5,000 kNm)",
          float(np.linalg.norm(Mges)) < 1e-9 * F * L, f"{np.round(Mges / 1e3, 9)} kNm")
    Lp = math.hypot(L, e)
    w_hand = F * e * Lp * L / (6 * EI) + F * (L / Lp) * Lp / (E * A) * (e / Lp)
    w = float(rv.u[iv[-1], 2])
    check(f"… Spitze w = F e L' L/(6 E I) + N L'/(E A) · e/L' = {w_hand * 1e3:.5f} mm (Hand, auf 1e-6; "
          "vorher 1,90476 mm)", abs(w / w_hand - 1) < 1e-6, f"{w * 1e3:.5f} mm")
    du = _rel(rv.u[iv[-1]], rk.u[ik[-1]])
    check("… Verschiebung und Verdrehung der Spitze wie mit Kurzstäben (auf 1e-4)", du < 1e-4,
          f"Versatz {np.round(rv.u[iv[-1]] * 1e3, 5)}, Kurzstab {np.round(rk.u[ik[-1]] * 1e3, 5)}")
    be = np.asarray(rv.beam_end[ev[0]], float)
    soll = np.zeros(12)
    soll[0], soll[6] = -F * L / Lp, F * L / Lp          # N = F cos α
    soll[2], soll[8] = F * e / Lp, -F * e / Lp          # V = F sin α
    soll[10] = -F * e                                    # My am Ende, am Anfang 0
    check("… Stabendkräfte in den Achsen des Stabs: N = F L/L', V = F e/L', My Anfang 0, Ende −F e "
          "(Hand, auf 1e-9)", _rel(be, soll, F) < 1e-9, f"{np.round(be / 1e3, 5)} kN/kNm")
    check("… Stabendkräfte wie im Stab mit Kurzstäben (auf 1e-4)",
          _rel(be, rk.beam_end[ek[0]], F) < 1e-4, f"Kurzstab {np.round(np.asarray(rk.beam_end[ek[0]]) / 1e3, 5)}")
    from statik3d import solver
    st = solver.beam_station_forces(mv, rv, ev[0], 5)
    check("… Momentenverlauf im Stab linear von 0 auf F e (Hand, auf 1e-9)",
          _rel(np.abs(st["My"]), F * e * np.linspace(0, 1, 5), F * e) < 1e-9,
          f"{np.round(np.asarray(st['My']) / 1e3, 5)} kNm")
    check("… Länge des Stabelements L' = √(L² + e²) = 4,00125 m (zwischen den versetzten Enden)",
          abs(mv.element_length(ev[0]) - Lp) < 1e-12, f"{mv.element_length(ev[0]):.6f} m")


def test_kragarm_zug_theorie2():
    e, F = 0.1, 50e3
    last = {"Fx": F}
    mv, iv, ev = _kragarm("versatz", (0, 0, 0), (0, 0, e), 1, last, "II")
    mk, ik, ek = _kragarm("kurzstab", (0, 0, 0), (0, 0, e), 1, last, "II")
    rv, rk = _rechnen(mv), _rechnen(mk)
    Mv, Mk = float(rv.reactions[iv[0], 4]), float(rk.reactions[ik[0], 4])
    check("Th II, derselbe Kragarm: Einspannmoment wie mit Kurzstäben (auf 0,1 %; vorher 4,906 kNm)",
          abs(Mv - Mk) < 1e-3 * abs(Mk), f"Versatz {Mv / 1e3:.5f}, Kurzstab {Mk / 1e3:.5f} kNm")
    check("… Spitze wie mit Kurzstäben (auf 1e-4)", _rel(rv.u[iv[-1]], rk.u[ik[-1]]) < 1e-4,
          f"Versatz {np.round(rv.u[iv[-1]] * 1e3, 5)}, Kurzstab {np.round(rk.u[ik[-1]] * 1e3, 5)}")


# ---------------------------------------------------------------- Querlast, Stablasten
def test_querlast_raeumlich():
    r1, r2 = (0, 0, 0.05), (0, 0.1, -0.1)
    last = {"Fx": 20e3, "Fy": 3e3, "Fz": -10e3}
    mv, iv, ev = _kragarm("versatz", r1, r2, 1, last)
    mk, ik, ek = _kragarm("kurzstab", r1, r2, 1, last)
    rv, rk = _rechnen(mv), _rechnen(mk)
    soll = -np.cross([L, 0, 0], [20e3, 3e3, -10e3])
    check("Th I, Versatz (0; 0; 0,05) → (0; 0,1; −0,1) m, F = (20; 3; −10) kN: Einspannmomente −x × F "
          "(Hand, auf 1e-9; vorher −0,55/−43/−14 kNm)", _rel(rv.reactions[iv[0], 3:], soll) < 1e-9,
          f"{np.round(rv.reactions[iv[0], 3:] / 1e3, 6)} kNm, Hand {np.round(soll / 1e3, 6)}")
    check("… Spitze wie mit Kurzstäben (auf 1e-4)", _rel(rv.u[iv[-1]], rk.u[ik[-1]]) < 1e-4,
          f"Versatz {np.round(rv.u[iv[-1]] * 1e3, 5)}, Kurzstab {np.round(rk.u[ik[-1]] * 1e3, 5)}")
    check("… Stabendkräfte wie mit Kurzstäben (auf 1e-4)",
          _rel(rv.beam_end[ev[0]], rk.beam_end[ek[0]]) < 1e-4,
          f"{np.round(np.asarray(rv.beam_end[ev[0]]) / 1e3, 4)}")


def test_stablasten():
    """Gleichlast global, Teillast lokal, Last je Projektion und Eigengewicht
    auf dem Stab mit verschiedenem Versatz."""
    r1, r2 = (0, 0, 0.05), (0, 0.1, -0.1)
    lasten = ({"qz": -5e3},
              {"qy": 2e3, "qz": 1e3, "system": "local", "a": 1.0, "b": 3.0},
              {"qx": 4e3, "bezugslaenge": "projektion"})
    last = {"Fz": -1e3}
    rho = 7850.0
    mv, iv, ev = _kragarm("versatz", r1, r2, 1, last, stablasten=lasten, rho=rho)
    mk, ik, ek = _kragarm("kurzstab", r1, r2, 1, last, stablasten=lasten, rho=rho)
    rv, rk = _rechnen(mv), _rechnen(mk)
    check("Th I, Stablasten (global, lokale Teillast, je Projektion, Eigengewicht): Einspannkräfte "
          "und -momente wie mit Kurzstäben (auf 1e-4)", _rel(rv.reactions[iv[0]], rk.reactions[ik[0]]) < 1e-4,
          f"Versatz {np.round(rv.reactions[iv[0]] / 1e3, 5)}, Kurzstab {np.round(rk.reactions[ik[0]] / 1e3, 5)}")
    check("… Spitze wie mit Kurzstäben (auf 1e-4)", _rel(rv.u[iv[-1]], rk.u[ik[-1]]) < 1e-4,
          f"Versatz {np.round(rv.u[iv[-1]] * 1e3, 5)}, Kurzstab {np.round(rk.u[ik[-1]] * 1e3, 5)}")
    check("… Stabendkräfte wie mit Kurzstäben (auf 1e-4)",
          _rel(rv.beam_end[ev[0]], rk.beam_end[ek[0]]) < 1e-4,
          f"{np.round(np.asarray(rv.beam_end[ev[0]]) / 1e3, 4)}")
    from statik3d import solver
    sv = solver.beam_station_forces(mv, rv, ev[0], 9)
    sk = solver.beam_station_forces(mk, rk, ek[0], 9)
    d = max(_rel(sv[c], sk[c], 1e3) for c in ("N", "Vy", "Vz", "Mt", "My", "Mz"))
    check("… Schnittgrößen an 9 Stellen im Stab wie mit Kurzstäben (auf 1e-4 kN bzw. kNm je kN)", d < 1e-4,
          f"{d:.1e}")
    # Auflagersumme z von Hand: q L' + Teillast + Gewicht ρ A g L' + Knotenlast
    P1, P2 = np.array([0, 0, 0.05]), np.array([L, 0.1, -0.1])
    Lp = float(np.linalg.norm(P2 - P1))
    t = (P2 - P1) / Lp
    from statik3d.elements import beam3d as bm
    T3, _ = bm.local_axes(P1, P2, 0.0)
    teil = T3.T @ np.array([0.0, 2e3, 1e3]) * 2.0
    proj = 4e3 * math.sqrt(1 - t[0] ** 2) * Lp
    soll = np.array([proj, 0, -5e3 * Lp - rho * A * 9.81 * Lp - 1e3]) + teil
    check("… Auflagersumme = Lasten von Hand mit der Stablänge L' zwischen den versetzten Enden (auf 1e-9)",
          _rel(-rv.reactions[iv[0], :3], soll) < 1e-9,
          f"{np.round(-rv.reactions[iv[0], :3] / 1e3, 6)} kN, Hand {np.round(soll / 1e3, 6)}")


# ---------------------------------------------------------------- Theorie II, alpha_cr
def test_theorie2_und_3():
    """Druck 200 kN mit Momenten an der Spitze. Die Kurzstaebe tragen dabei
    keine Normalkraft: mit Normalkraft N_k bekaemen sie nach Theorie II.
    Ordnung eine eigene geometrische Steifigkeit (N_k mal Laenge bei ihrer
    Drehung), die der Versatz als Matrix A nicht hat - gemessen 1,5e-3 der
    Verdrillung mit N_k = 3 kN am 0,1-m-Arm, wie N_k l/(G I_T/L) = 1,49e-3;
    nach Theorie I. Ordnung 1e-7 (Nebenbefund, ausserhalb dieser Kur)."""
    from statik3d.theorie3 import solve_theorie3
    r1, r2 = (0, 0, 0), (0, 0.05, 0.1)
    last = {"Fx": -200e3, "Mx": 0.5e3, "My": 2e3, "Mz": -1e3}
    mv, iv, ev = _kragarm("versatz", r1, r2, 8, last, "II")
    mk, ik, ek = _kragarm("kurzstab", r1, r2, 8, last, "II")
    rv, rk = _rechnen(mv), _rechnen(mk)
    check("Th II, Druck 200 kN mit Momenten, Versatz linear 0 → (0; 0,05; 0,1) m in 8 Elementen: "
          "Spitze wie mit Kurzstäben (auf 1e-4)", _rel(rv.u[iv[-1]], rk.u[ik[-1]]) < 1e-4,
          f"Versatz {np.round(rv.u[iv[-1]] * 1e3, 5)}, Kurzstab {np.round(rk.u[ik[-1]] * 1e3, 5)}")
    check("… Einspannmomente wie mit Kurzstäben (auf 1e-4)",
          _rel(rv.reactions[iv[0], 3:], rk.reactions[ik[0], 3:]) < 1e-4,
          f"Versatz {np.round(rv.reactions[iv[0], 3:] / 1e3, 5)}, Kurzstab "
          f"{np.round(rk.reactions[ik[0], 3:] / 1e3, 5)} kNm")
    av, ak = rv.info.get("alpha_cr"), rk.info.get("alpha_cr")
    check("… alpha_cr wie mit Kurzstäben (auf 1e-4)",
          av is not None and ak is not None and abs(av / ak - 1) < 1e-4, f"Versatz {av}, Kurzstab {ak}")
    # Theorie III. Ordnung mit Kraeften an der Spitze. Mit den Momenten von
    # oben weicht Theorie III. um 2 % in den Einspannmomenten ab (ohne Versatz
    # 1,5e-5): Theorie III. dreht den Arm mit, (θ × a) × F mit der
    # Stabendkraft F ≈ 200 kN, a bis 0,11 m und θ ≈ 2,5 mrad gibt die
    # gemessenen 54 Nm; Theorie II. Ordnung kennt diesen Anteil weder beim
    # Versatz noch beim Kurzstab (Nebenbefund, ausserhalb dieser Kur)
    last = {"Fx": -200e3, "Fz": -3e3, "Fy": 1e3}
    mv, iv, ev = _kragarm("versatz", r1, r2, 8, last, "II")
    rv = _rechnen(mv)
    m3, i3, e3 = _kragarm("versatz", r1, r2, 8, last, "III")
    r3, info = solve_theorie3(m3, {"LF1": 1.0}, "LF1", schritte=10, imperfektionen=False, stabteilung=False)
    check("Th III, Druck 200 kN mit Querkräften 3 und 1 kN, derselbe Versatz: Rechnung ohne Fehler",
          not info.fehler, repr(info.fehler))
    d3 = _rel(r3.u[i3[-1], :3], rv.u[iv[-1], :3])
    M3 = _rel(r3.reactions[i3[0], 3:], rv.reactions[iv[0], 3:])
    check("… Spitze und Einspannmomente nach Th III wie nach Th II (kleine Verdrehung, auf 0,5 %)",
          d3 < 5e-3 and M3 < 5e-3, f"u {d3:.1e}, M {M3:.1e}; Th III {np.round(r3.u[i3[-1], :3] * 1e3, 4)}, "
                                   f"Th II {np.round(rv.u[iv[-1], :3] * 1e3, 4)} mm")


# ---------------------------------------------------------------- geteilt
def test_geteilt():
    """Ein Element mit Versatz (0; 0; 0,05) → (0; 0,1; −0,1) m und Teillast
    gegen dasselbe Element, bei x = 2 m geteilt (Model.stabelement_geteilt):
    jedes Teil bekommt den Versatz linear dazwischen und liegt auf derselben
    Achse."""
    r1, r2 = (0, 0, 0.05), (0, 0.1, -0.1)
    last = {"Fx": 20e3, "Fz": -10e3}
    lasten = ({"qz": -5e3, "a": 1.0, "b": 3.0},)

    def bau():
        return _kragarm("versatz", r1, r2, 1, last, stablasten=lasten)
    m0, i0, e0 = bau()
    r0 = _rechnen(m0)
    m1, i1, e1 = bau()
    k = m1.add_node(2.0, 0, 0)
    el = m1.elements[e1[0]]
    hinten = int(el.nodes[-1])
    el.nodes = [int(el.nodes[0]), k]
    neu = m1.add_element("beam", [k, hinten], el.mat, el.sec, roll=el.roll)
    m1.stabelement_geteilt(e1[0], neu)
    r1_ = _rechnen(m1)
    du = _rel(r1_.u[[i0[0], i0[-1]]], r0.u[[i0[0], i0[-1]]])
    dr = _rel(r1_.reactions[i0[0]], r0.reactions[i0[0]])
    check("Geteilt bei x = 2 m (Versatz linear, Teillast 1 … 3 m): Spitze und Einspannung wie ungeteilt "
          "(auf 1e-9)", du < 1e-9 and dr < 1e-9, f"u {du:.1e}, R {dr:.1e}")
    L0 = m0.element_length(e0[0])
    La, Ln = m1.element_length(e1[0]), m1.element_length(neu)
    check("… die Teile liegen auf der Achse des ungeteilten Stabs: L'a + L'n = L' (auf 1e-12)",
          abs(La + Ln - L0) < 1e-12, f"{La:.9f} + {Ln:.9f} = {L0:.9f} m")
    soll = -np.cross([L, 0, 0], [20e3, 0, -10e3]) + np.array([0.0, 0.0, 0.0])
    # Momente der Teillast: von Hand über die versetzte Achse
    P1, P2 = np.array([0, 0, 0.05]), np.array([L, 0.1, -0.1])
    t = (P2 - P1) / L0
    for s0, s1 in ((1.0, 3.0),):
        xs = P1 + t * 0.5 * (s0 + s1)
        soll = soll - np.cross(xs, [0, 0, -5e3 * (s1 - s0)])
    check("… Einspannmomente von Hand (Knotenlast und Teillast auf der versetzten Achse, auf 1e-9)",
          _rel(r1_.reactions[i0[0], 3:], soll) < 1e-9 and _rel(r0.reactions[i0[0], 3:], soll) < 1e-9,
          f"geteilt {np.round(r1_.reactions[i0[0], 3:] / 1e3, 6)}, ungeteilt "
          f"{np.round(r0.reactions[i0[0], 3:] / 1e3, 6)}, Hand {np.round(soll / 1e3, 6)} kNm")


# ---------------------------------------------------------------- bitgleich
def test_bitgleich():
    """Gleicher Versatz an beiden Enden und ohne Versatz: derselbe Weg wie
    bisher (Matrix A in den Achsen der Knotenlinie, Laenge der Knotenlinie)."""
    from statik3d import assemble as asm
    from statik3d.elements import beam3d as bm
    ok = True
    for ex in ([[0, 0.1, 0.2], [0, 0.1, 0.2]], [], [[0, 0, 0], [0, 0, 0]]):
        m, ids, els = _kragarm("versatz", (0, 0, 0), (0, 0, 0), 1, {"Fz": -1.0})
        m.nodes[ids[-1]] = [3.7, 0.4, 1.3]
        e = m.elements[els[0]]
        e.exzentrizitaet = ex
        e.roll = 0.3
        X = m.nodes[e.nodes]
        T3, Ln = bm.local_axes(X[0], X[1], e.roll)
        T = bm.transform_matrix(T3)
        mat = m.materials["ST"]
        kl = bm.k_local_beam(mat.E, mat.G, A, I, I, 1e-5, Ln)
        Av = asm.beam_versatz(e)
        k_alt = T.T @ ((Av.T @ kl @ Av) if Av is not None else kl) @ T
        ok = ok and np.array_equal(asm.element_matrix(m, e), k_alt) \
            and m.element_length(els[0]) == float(np.linalg.norm(X[1] - X[0])) \
            and (asm.stab_versatz(m, e) is Av or np.array_equal(asm.stab_versatz(m, e), Av))
    check("Gleicher Versatz an beiden Enden und ohne Versatz: Steifigkeit, Länge und Matrix A bitgleich "
          "wie bisher", ok)


# ---------------------------------------------------------------- Verfahrenstabelle
def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("versatz_starrer_arm")
    ok = mk is not None and mk.wechsel[-1].stand == 38 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR \
        and rv.VERFAHRENSSTAND >= 38
    m_ja, _i, _e = _kragarm("versatz", (0, 0, 0), (0, 0, 0.1), 2, {"Fx": 1.0})
    m_gleich, _i, _e = _kragarm("versatz", (0, 0, 0.1), (0, 0, 0.1), 2, {"Fx": 1.0})
    m_nein, _i, _e = _kragarm("versatz", (0, 0, 0), (0, 0, 0), 2, {"Fx": 1.0})
    ok = ok and mk.betrifft(m_ja) and not mk.betrifft(m_gleich) and not mk.betrifft(m_nein)
    check("Verfahrenstabelle: „Versatz als starrer Arm“ Stand 38 als Fehlerkorrektur, betroffen nur "
          "Stäbe mit verschiedenem Versatz an den Enden", ok, f"Stand {rv.VERFAHRENSSTAND}")


def main():
    np.set_printoptions(suppress=True)
    for t in (test_kragarm_zug, test_kragarm_zug_theorie2, test_querlast_raeumlich, test_stablasten,
              test_theorie2_und_3, test_geteilt, test_bitgleich, test_verfahrenstabelle):
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
