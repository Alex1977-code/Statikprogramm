"""
Verifikation der Berechnung nach Theorie II. Ordnung und der
Ersatzimperfektionen nach DIN EN 1993-1-1, 5.2 und 5.3.

Geprueft wird gegen geschlossene Loesungen:

  * alpha_cr der Kragstuetze und des Pendelstabes gegen die Knicklast nach
    Engesser, N_cr = N_E / (1 + N_E/(G A_s)) mit N_E = pi^2 EI/L_cr^2 - das
    Stabelement rechnet mit Schubverformung, die schubstarre Eulerlast liegt
    darum um rund 0,5 % darueber
  * die Vergroesserung der Verformung gegen 1/(1 - N/N_cr)
  * die Ersatzhorizontalkraft gegen phi N_Ed mit phi = phi_0 alpha_h alpha_m
  * die Wirkung der Ersatzlast gegen die von Hand vergroesserte Zusatzlast

Aufruf:  python -m tests.test_theorie2
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material                          # noqa: E402
from statik3d.profiles import make_section                          # noqa: E402
from statik3d import solver, examples_lib                           # noqa: E402
from statik3d import theorie2 as T2                                 # noqa: E402

RESULTS = []


def check(name, ok, info=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:58s} {info}")
    return ok


def close(name, got, want, tol, unit=""):
    err = abs(got - want)
    rel = err / abs(want) if want else err
    return check(name, rel <= tol,
                 f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {rel * 100:.4f} %")


# --------------------------------------------------------------------------
def kragstuetze(L=6.0, n=12, profil="HEB 300"):
    sec = make_section(profil)
    m = Model("Kragstuetze")
    m.add_material(Material.steel("S355"))
    m.add_section(sec)
    ids = [m.add_node(0.0, 0.0, L * i / n) for i in range(n + 1)]
    els = [m.add_element("beam", [ids[i], ids[i + 1]], "S355", sec.name)
           for i in range(n)]
    m.add_member("Stiel", els)
    m.fix(ids[0], "all")
    return m, sec, ids, els


def test_imperfektionsbeiwerte():
    close("α_h = 2/√h für h = 9 m", T2.alpha_h(9.0), 2 / 3, 1e-12)
    check("α_h ist nach unten auf 2/3 begrenzt",
          abs(T2.alpha_h(100.0) - 2 / 3) < 1e-12, f"{T2.alpha_h(100.0):.4f}")
    check("und nach oben auf 1,0", T2.alpha_h(1.0) == 1.0)
    close("α_m = √(0,5(1+1/m)) für m = 1", T2.alpha_m(1), 1.0, 1e-12)
    close("α_m für m = 2", T2.alpha_m(2), math.sqrt(0.75), 1e-12)
    check("α_m fällt mit der Stielzahl", T2.alpha_m(1) > T2.alpha_m(4) > 0.7)
    sk = T2.schiefstellung(9.0, 2)
    close("φ = φ_0 α_h α_m", sk["phi"], (1 / 200) * (2 / 3) * math.sqrt(0.75), 1e-12)
    close("φ_0 = 1/200", sk["phi_0"], 1 / 200, 1e-12)
    # Tabelle 5.1
    for kurve, soll in (("a0", 1 / 350), ("a", 1 / 300), ("b", 1 / 250),
                        ("c", 1 / 200), ("d", 1 / 150)):
        close(f"e_0/L Tab. 5.1 elastisch, Linie {kurve}",
              T2.e0_durch_L(kurve, True), soll, 1e-12)
    check("plastisch ist ungünstiger",
          T2.e0_durch_L("b", False) > T2.e0_durch_L("b", True),
          f"1/200 gegen 1/250")

    kraefte = {"A": 100e3, "B": 100e3, "C": 20e3}
    check("nur Stiele über 50 % der mittleren Kraft zählen für m",
          sorted(T2.massgebende_stiele(kraefte)) == ["A", "B"],
          f"Mittel {sum(kraefte.values()) / 3 / 1e3:.0f} kN, "
          f"m = {len(T2.massgebende_stiele(kraefte))}")


def N_cr_engesser(E, G, I, As, Lcr):
    """Knicklast mit Schubverformung (Engesser): N_E / (1 + N_E/(G A_s))."""
    NE = math.pi ** 2 * E * I / Lcr ** 2
    return NE / (1.0 + NE / (G * As))


def test_alpha_cr():
    """Kragstuetze und Pendelstab gegen die Knicklast mit Schubverformung."""
    m, sec, ids, _els = kragstuetze()
    E = m.materials["S355"].E
    L = 6.0
    G = m.materials["S355"].G
    Ncr = N_cr_engesser(E, G, sec.Iz, sec.Asy, 2 * L)     # Knicklänge 2L
    N = 0.30 * math.pi ** 2 * E * sec.Iz / (2 * L) ** 2
    m.add_load_case("LF1", "G", "Grundlast")
    m.load_node(ids[-1], Fz=-N, Fy=20e3, case="LF1")
    system = solver.StaticSystem(m)
    F, _fe, _q, _t = solver.case_loads(m, {"LF1": 1.0})
    u1 = system.solve(F)
    ac = T2.alpha_cr(m, system, u1)
    close("α_cr der Kragstütze = N_cr/N_Ed", ac["alpha_cr"], Ncr / N, 1e-4)
    check("die schubstarre Eulerlast liegt darüber",
          ac["alpha_cr"] < math.pi ** 2 * E * sec.Iz / (2 * L) ** 2 / N,
          f"{ac['alpha_cr']:.4f} < "
          f"{math.pi ** 2 * E * sec.Iz / (2 * L) ** 2 / N:.4f}")
    check("die Eigenform wird mitgeliefert",
          ac.get("modus") is not None and np.abs(ac["modus"]).max() > 0)

    # beidseits gelenkiger Stab: N_cr = pi^2 EI/L^2
    m2 = Model("Pendelstab")
    m2.add_material(Material.steel("S355"))
    m2.add_section(sec)
    n = 12
    i2 = [m2.add_node(0.0, 0.0, L * i / n) for i in range(n + 1)]
    for i in range(n):
        m2.add_element("beam", [i2[i], i2[i + 1]], "S355", sec.name)
    # beidseits gelenkig um beide Biegeachsen, oben in Stabrichtung frei;
    # Stabachse ist global z, die Torsion ist damit phi_z (FHG 5)
    m2.fix(i2[0], [0, 1, 2, 5])
    m2.fix(i2[-1], [0, 1, 5])
    m2.add_load_case("LF1", "G", "")
    m2.load_node(i2[-1], Fz=-1000e3, Fy=1e3, case="LF1")
    s2 = solver.StaticSystem(m2)
    F2, _a, _b, _c = solver.case_loads(m2, {"LF1": 1.0})
    ac2 = T2.alpha_cr(m2, s2, s2.solve(F2))
    close("α_cr des Pendelstabes (Knicklänge L, mit Schubverformung)",
          ac2["alpha_cr"], N_cr_engesser(E, G, sec.Iz, sec.Asy, L) / 1000e3, 1e-4)

    # Kriterium 5.2.1(3)
    check("α_cr = 12 verlangt elastisch keine Theorie II. Ordnung",
          not T2.erforderlich(12.0)["noetig"])
    check("plastisch mit Grenze 15 dagegen schon",
          T2.erforderlich(12.0, True)["noetig"],
          T2.erforderlich(12.0, True)["text"])
    check("α_cr = 8 verlangt sie immer", T2.erforderlich(8.0)["noetig"])


def zweigelenkrahmen():
    """Zweigelenkrahmen: Stiele HEB 200, 5 m, Riegel IPE 300, 8 m, Fuesse
    gelenkig, die Riegelhoehe aus der Ebene gehalten; G 8 kN/m und Q 0,5 kN/m
    auf dem Riegel, W 25 kN waagerecht am linken Stielkopf. Unter W allein
    ist ein Stiel gezogen, der andere gedrueckt (N_W = ±15,625 kN)."""
    from statik3d import mesher
    from statik3d.model import Section
    m = Model("Zweigelenkrahmen")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("HEB 200"))
    m.add_section(Section.from_profile("IPE 300"))
    mesher.line_of_beams(m, "S235", "HEB 200", (0, 0, 0), (0, 0, 5.0), 5)
    a = len(m.elements)
    mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 5.0), (8.0, 0, 5.0), 8)
    b = len(m.elements)
    mesher.line_of_beams(m, "S235", "HEB 200", (8.0, 0, 5.0), (8.0, 0, 0), 5)
    mesher.merge_nodes(m)
    m.add_member("StielL", list(range(0, a)))
    m.add_member("Riegel", list(range(a, b)))
    m.add_member("StielR", list(range(b, len(m.elements))))
    for i in range(m.nn):
        if abs(m.nodes[i][2]) < 1e-9:
            m.fix(i, [0, 1, 2, 3, 5])
        elif abs(m.nodes[i][2] - 5.0) < 1e-9:
            m.fix(i, [1])
    for lf in ("G", "Q", "W"):
        m.add_load_case(lf, lf)
    for e in range(a, b):
        m.load_beam(e, qz=-8e3, case="G")
        m.load_beam(e, qz=-0.5e3, case="Q")
    kopf = min((i for i in range(m.nn) if abs(m.nodes[i][2] - 5.0) < 1e-9),
               key=lambda i: m.nodes[i][0])
    m.load_node(kopf, Fx=25e3, case="W")
    return m


def test_alpha_cr_zug_und_druck():
    """α_cr bei gezogenen und gedrückten Stäben zugleich (Befund B130).

    Bis zum 23.09.2026 rief alpha_cr eigsh(K, M=−K_g, sigma=0): ARPACK setzt
    für M ein positiv (semi)definites Skalarprodukt voraus, mit Zug und Druck
    ist −K_g aber indefinit. Am Zweigelenkrahmen gab W in 200 Aufrufen 200
    verschiedene Werte, alle unter 3,6, statt 77,33 - und „auto“ rechnete
    1,5·W nach II. Ordnung, obwohl α_cr = 51,55 ist. Bezug hier: das dichte
    Problem −K_g v = μ K v (scipy.linalg.eigh, K positiv definit), α = 1/μ_max.
    """
    import scipy.linalg as sla
    from statik3d import assemble as asm
    m = zweigelenkrahmen()
    system = solver.StaticSystem(m)
    fi = system.fi
    K = system.Kff.toarray()
    bezug = {}
    for name, fak in (("W", {"W": 1.0}), ("K1", {"G": 1.35, "Q": 1.5})):
        u = system.solve(solver.case_loads(m, fak)[0])
        G = -asm.geometric_stiffness(m, u)[fi][:, fi].toarray()
        mu = sla.eigh(G, K, eigvals_only=True)
        bezug[name] = 1.0 / mu.max()
        werte = [T2.alpha_cr(m, system, u) for _ in range(5)]
        a = [w["alpha_cr"] for w in werte]
        if name == "W":
            ew = np.linalg.eigvalsh(G)
            check("Voraussetzung: unter W ist −K_g indefinit (Zug und Druck)",
                  ew.min() < -1e-9 * abs(ew).max() and ew.max() > 1e-9 * abs(ew).max(),
                  f"{int((ew < -1e-9 * abs(ew).max()).sum())} negative, "
                  f"{int((ew > 1e-9 * abs(ew).max()).sum())} positive Eigenwerte")
        close(f"α_cr {name} gleich dem dichten Bezug", a[0], bezug[name], 1e-8)
        # Bitgleich, nicht nur auf 12 Stellen: ohne den festen Startvektor
        # gaben 200 Aufrufe unter K1 198 verschiedene Werte (Spanne 8,3e-12),
        # mit ihm einen (gemessen 24.09.2026)
        check(f"α_cr {name} fünfmal gerechnet, fünfmal bitgleich",
              len(set(a)) == 1, ", ".join(repr(x) for x in a))
        v = werte[0].get("modus")
        vf = v[fi] if v is not None else np.zeros(len(fi))
        r = np.linalg.norm(K @ vf - a[0] * (G @ vf)) / max(np.linalg.norm(K @ vf), 1e-300)
        check(f"die Eigenform {name} erfüllt K v = α_cr (−K_g) v", r < 1e-6,
              f"Residuum {r:.1e}")

    # Unter „auto“: der Lastfall W auf II. Ordnung und KW = 1,5·W
    m.load_cases["W"].theorie = "II"
    m.design.theorie2 = "auto"
    m.add_combination("KW", {"W": 1.5}, typ="ULS")
    an = solver.solve_all(m, design=False)
    kz = an.theorie2.kombinationen
    close("Lastfall W auf II. Ordnung: α_cr wie der Bezug",
          kz["W"].alpha_cr, bezug["W"], 1e-8)
    close("KW = 1,5·W: α_cr = α_cr(W)/1,5", kz["KW"].alpha_cr, bezug["W"] / 1.5, 1e-8)
    check("KW bleibt unter „auto“ bei I. Ordnung (α_cr ≥ 10)",
          not kz["KW"].gerechnet
          and an.combinations["KW"].info.get("theorie") != "II. Ordnung",
          kz["KW"].text())

    # Nur Zug: es gibt keinen positiven Verzweigungslastfaktor
    sec = make_section("HEB 300")
    mz = Model("Zugstab")
    mz.add_material(Material.steel("S355"))
    mz.add_section(sec)
    n = 12
    iz = [mz.add_node(0.0, 0.0, 6.0 * i / n) for i in range(n + 1)]
    for i in range(n):
        mz.add_element("beam", [iz[i], iz[i + 1]], "S355", sec.name)
    mz.fix(iz[0], [0, 1, 2, 5])
    mz.fix(iz[-1], [0, 1, 5])
    mz.add_load_case("LF1", "G", "")
    mz.load_node(iz[-1], Fz=+1000e3, Fy=1e3, case="LF1")
    sz = solver.StaticSystem(mz)
    az = [T2.alpha_cr(mz, sz, sz.solve(solver.case_loads(mz, {"LF1": 1.0})[0]))
          for _ in range(3)]
    check("nur Zug: α_cr = ∞, „kein positiver Verzweigungslastfaktor“",
          all(math.isinf(x["alpha_cr"]) and "kein positiver" in x["fehler"] for x in az),
          str([(x["alpha_cr"], x["fehler"]) for x in az]))


def geschossrahmen(nx=3, nz=2, a=6.0, h=4.0, s=4):
    """Symmetrischer Geschossrahmen: nx x nx Felder zu a, nz Geschosse zu h,
    Stützen HEB 300, Riegel IPE 400, Verbände CHS 88.9X5 in den Außenwänden,
    jeder Stab in s Elemente geteilt, Füße eingespannt; Lastfall G mit
    150 kN lotrecht je Knotenpunkt. Die größten μ häufen sich (3 x 3 x 2:
    27 innerhalb 10⁻³ von μ_max, dicht gerechnet 24.09.2026)."""
    m = Model("Geschossrahmen")
    m.add_material(Material.steel("S235"))
    for p in ("HEB 300", "IPE 400", "CHS 88.9X5"):
        m.add_section(make_section(p))
    kn = {}
    for k in range(nz + 1):
        for j in range(nx + 1):
            for i in range(nx + 1):
                kn[i, j, k] = m.add_node(i * a, j * a, k * h)

    def stab(p, q, sec):
        A, B = np.array(m.nodes[p]), np.array(m.nodes[q])
        ids = [p] + [m.add_node(*(A + (B - A) * t / s)) for t in range(1, s)] + [q]
        for t in range(s):
            m.add_element("beam", [ids[t], ids[t + 1]], "S235", sec)

    for k in range(nz):
        for j in range(nx + 1):
            for i in range(nx + 1):
                stab(kn[i, j, k], kn[i, j, k + 1], "HEB 300")
    for k in range(1, nz + 1):
        for j in range(nx + 1):
            for i in range(nx):
                stab(kn[i, j, k], kn[i + 1, j, k], "IPE 400")
        for i in range(nx + 1):
            for j in range(nx):
                stab(kn[i, j, k], kn[i, j + 1, k], "IPE 400")
    for k in range(nz):
        for j in (0, nx):
            stab(kn[0, j, k], kn[1, j, k + 1], "CHS 88.9X5")
            stab(kn[1, j, k], kn[0, j, k + 1], "CHS 88.9X5")
        for i in (0, nx):
            stab(kn[i, 0, k], kn[i, 1, k + 1], "CHS 88.9X5")
            stab(kn[i, 1, k], kn[i, 0, k + 1], "CHS 88.9X5")
    for j in range(nx + 1):
        for i in range(nx + 1):
            m.fix(kn[i, j, 0], "all")
    m.add_load_case("G", "G")
    for k in range(1, nz + 1):
        for j in range(nx + 1):
            for i in range(nx + 1):
                m.load_node(kn[i, j, k], Fz=-150e3, case="G")
    return m


def test_alpha_cr_haeufung():
    """α_cr bei gehäuften größten μ: richtig und nicht langsam.

    Mit eigsh(−K_g, M=K, 'LA') im Regelmodus (Stand 9dc88a3) brauchte ein
    Aufruf am symmetrischen Geschossrahmen mit 5856 FHG 52,5 s (gemessen
    24.09.2026), hier mit 1920 FHG 4,4 bis 5,6 s, das 81- bis 114-Fache
    von Aufbau und Lösung des Systems (jetzt das 1,6- bis 2,1-Fache). Der
    Grund: die 27 größten μ liegen innerhalb 10⁻³. Jetzt: Schätzwert,
    Verschiebung s über μ_max, die der Trägheitssatz an s·K + K_g
    bestätigt, dann Shift-invert um s.
    """
    import time
    import scipy.linalg as sla
    from statik3d import assemble as asm
    m = geschossrahmen()
    t_sys = []
    for _ in range(3):
        t0 = time.perf_counter()
        system = solver.StaticSystem(m)
        u = system.solve(solver.case_loads(m, {"G": 1.0})[0])
        t_sys.append(time.perf_counter() - t0)
    fi = system.fi
    Kgff = asm.geometric_stiffness(m, u)[fi][:, fi].tocsc()
    mu = np.sort(sla.eigh(-Kgff.toarray(), system.Kff.toarray(), eigvals_only=True))[::-1]
    bezug = 1.0 / mu[0]
    n_nah = int((mu >= mu[0] * (1 - 1e-3)).sum())
    check("Voraussetzung: die größten μ häufen sich", n_nah >= 20,
          f"{n_nah} μ innerhalb 10⁻³ von μ_max, {len(fi)} FHG")
    t_a, werte = [], []
    for _ in range(3):
        t0 = time.perf_counter()
        werte.append(T2.alpha_cr(m, system, u)["alpha_cr"])
        t_a.append(time.perf_counter() - t0)
    close("α_cr gleich dem dichten Bezug", werte[0], bezug, 1e-9)
    # Ein Verhaeltnis, keine Sekunden: es haengt nicht daran, wie belastet
    # die Maschine gerade ist
    check("α_cr kostet höchstens das Zehnfache von Aufbau und Lösung",
          min(t_a) <= 10.0 * min(t_sys),
          f"α_cr {min(t_a):.3f} s, System {min(t_sys):.3f} s "
          f"({min(t_a) / min(t_sys):.1f}-fach)")

    # Die Verschiebung wird erzwungen, nicht erhofft: auch aus schlechten
    # Schaetzwerten unter mu_max (statt Stufe 1) kommt mu_max heraus
    f = getattr(T2, "groesstes_mu", None)
    for faktor in (0.99, 0.3):
        try:
            r = f(system.Kff, Kgff, schaetzwert=faktor * mu[0]) if f else None
        except Exception as exc:                  # pragma: no cover
            r = None
            print("   ", type(exc).__name__, exc)
        got = 1.0 / r[0][0] if r is not None and r[0] is not None else math.nan
        check(f"Schätzwert {faktor:g}·μ_max: trotzdem α_cr gleich dem Bezug",
              abs(got / bezug - 1) <= 1e-9, f"{got:.10g} / {bezug:.10g}")


def test_vergroesserung():
    """Verformung nach Theorie II. Ordnung gegen 1/(1 − N/N_cr)."""
    m, sec, ids, _els = kragstuetze()
    E = m.materials["S355"].E
    L = 6.0
    Ncr = math.pi ** 2 * E * sec.Iz / (2 * L) ** 2
    N, H = 0.30 * Ncr, 20e3
    m.add_load_case("LF1", "G", "")
    m.load_node(ids[-1], Fz=-N, Fy=H, case="LF1")
    m.add_combination("K1", {"LF1": 1.0}, typ="ULS")
    system = solver.StaticSystem(m)
    F, _a, _b, _c = solver.case_loads(m, {"LF1": 1.0})
    u1 = system.solve(F).reshape(-1, 6)
    res2, info = T2.solve_theorie2(m, {"LF1": 1.0}, "K1", system,
                                   imperfektionen=False)
    w1 = abs(float(u1[ids[-1], 1]))
    w2 = abs(float(res2.u[ids[-1], 1]))
    close("Vergrößerung = 1/(1 − N/N_cr)", w2 / w1, 1.0 / (1.0 - N / Ncr), 5e-3)
    check("die Iteration konvergiert", info.konvergenz < 1e-8,
          f"{info.iterationen} Iterationen, letzte Änderung {info.konvergenz:.2e}")
    check("und wird als II. Ordnung gekennzeichnet",
          res2.info.get("theorie") == "II. Ordnung")

    # halbe Last -> kleinere Vergroesserung
    m.load_cases["LF1"].nodal_loads.clear()
    m.load_node(ids[-1], Fz=-0.15 * Ncr, Fy=H, case="LF1")
    res3, _i3 = T2.solve_theorie2(m, {"LF1": 1.0}, "K1", system, imperfektionen=False)
    w3 = abs(float(res3.u[ids[-1], 1]))
    close("halbe Normalkraft, Vergrößerung 1/(1−0,15)",
          w3 / w1, 1.0 / (1.0 - 0.15), 5e-3)


def test_ersatzlasten():
    """Ersatzhorizontalkraft und ihre Wirkung gegen die Handrechnung."""
    m, sec, ids, _els = kragstuetze()
    E = m.materials["S355"].E
    L = 6.0
    Ncr = math.pi ** 2 * E * sec.Iz / (2 * L) ** 2
    N, H = 0.30 * Ncr, 20e3
    m.add_load_case("LF1", "G", "")
    m.load_node(ids[-1], Fz=-N, Fy=H, case="LF1")
    m.add_combination("K1", {"LF1": 1.0}, typ="ULS")
    system = solver.StaticSystem(m)
    F, _a, _b, _c = solver.case_loads(m, {"LF1": 1.0})
    u1 = system.solve(F)
    res1 = solver.Results(name="K1", kind="combination", model=m)
    res1.u = u1.reshape(-1, 6)
    res1.reactions = system.reactions(u1, F).reshape(-1, 6)
    solver.postprocess(m, u1, res1)

    Fimp, sk = T2.ersatzlasten_schiefstellung(m, res1)
    close("φ für h = 6 m und m = 1", sk["phi"],
          (1 / 200) * T2.alpha_h(6.0) * 1.0, 1e-12)
    close("H_Ed = φ N_Ed", sk["H_gesamt"], sk["phi"] * N, 2e-3, " N")
    check("die Ersatzlast ist ein Kräftepaar (Summe null)",
          abs(Fimp.reshape(-1, 6)[:, :3].sum()) < 1e-6,
          f"Σ = {Fimp.reshape(-1, 6)[:, :3].sum():.3e} N")
    d = np.asarray(sk["richtung"])
    check("sie wirkt in Richtung der Verschiebung (ungünstig)",
          float(d[:2] @ res1.u[ids[-1], :2]) > 0,
          f"Richtung {d[:2]}, u_Kopf {res1.u[ids[-1], :2]}")

    # Wirkung: die Zusatzkraft vergroessert die Verformung wie H selbst
    res2, i2 = T2.solve_theorie2(m, {"LF1": 1.0}, "K1", system, imperfektionen=False)
    res3, i3 = T2.solve_theorie2(m, {"LF1": 1.0}, "K1", system, imperfektionen=True)
    w1 = abs(float(res1.u[ids[-1], 1]))
    w2 = abs(float(res2.u[ids[-1], 1]))
    w3 = abs(float(res3.u[ids[-1], 1]))
    soll = w2 + w1 * (sk["phi"] * N / H) / (1.0 - N / Ncr)
    close("Verformung mit Imperfektion = w_II + verstärkter Anteil aus H_imp",
          w3, soll, 5e-3, " m")
    check("die Imperfektion vergrößert die Verformung", w3 > w2,
          f"{w3 * 1e3:.2f} > {w2 * 1e3:.2f} mm")
    check("die Schiefstellung steht im Ergebnis", bool(i3.schiefstellung))
    check("ohne Imperfektion steht dort nichts", not i2.schiefstellung)


def test_vorkruemmung():
    """Vorkruemmung: Kriterium 5.3.2(6) und die Ersatzlast."""
    # schlanker Pendelstab unter kleiner Druckkraft -> Kriterium erfuellt
    sec = make_section("HEA 200")
    m = Model("Pendelstab")
    m.add_material(Material.steel("S355"))
    m.add_section(sec)
    L, n = 8.0, 8
    ids = [m.add_node(0.0, 0.0, L * i / n) for i in range(n + 1)]
    els = [m.add_element("beam", [ids[i], ids[i + 1]], "S355", sec.name)
           for i in range(n)]
    mem = m.add_member("Stütze", els)
    # beidseits gelenkig: nur die Verschiebungen und die Torsion (phi_z, weil
    # die Stabachse lotrecht ist) sind gehalten, die Biegewinkel sind frei
    m.fix(ids[0], [0, 1, 2, 5])
    m.fix(ids[-1], [0, 1, 5])
    m.add_load_case("LF1", "G", "")
    Nc = 200e3
    m.load_node(ids[-1], Fz=-Nc, case="LF1")
    m.add_combination("K1", {"LF1": 1.0}, typ="ULS")
    system = solver.StaticSystem(m)
    F, _a, _b, _c = solver.case_loads(m, {"LF1": 1.0})
    u = system.solve(F)
    res = solver.Results(name="K1", kind="combination", model=m)
    res.u = u.reshape(-1, 6)
    res.reactions = system.reactions(u, F).reshape(-1, 6)
    solver.postprocess(m, u, res)

    krit = T2.vorkruemmung_noetig(m, mem, Nc)
    check("5.3.2(6) wird ausgewertet", "lambda" in krit and "grenze" in krit,
          krit["grund"])
    E = m.materials["S355"].E
    Ncr = math.pi ** 2 * E * sec.Iz / L ** 2      # 5.3.2(6) rechnet schubstarr
    fy = m.materials["S355"].yield_strength(sec.t_max)
    close("λ̄ = √(A f_y/N_cr)", krit["lambda"], math.sqrt(sec.A * fy / Ncr), 1e-9)
    close("Grenze 0,5 √(A f_y/N_Ed)", krit["grenze"],
          0.5 * math.sqrt(sec.A * fy / Nc), 1e-12)

    Fv, vk = T2.ersatzlasten_vorkruemmung(m, res, alle=True)
    check("die Vorkrümmung wird angesetzt", vk["anzahl"] == 1, str(vk["anzahl"]))
    d = vk["je_stab"][0]
    close("e_0 = (e_0/L) L", d["e_0"], T2.e0_durch_L(d["kurve"], True) * L, 1e-12, " m")
    close("q = 8 N e_0/L²", d["q"], 8 * Nc * d["e_0"] / L ** 2, 1e-12, " N/m")
    close("V = 4 N e_0/L", d["V"], 4 * Nc * d["e_0"] / L, 1e-12, " N")
    check("das Ersatzlastsystem ist im Gleichgewicht",
          abs(Fv.reshape(-1, 6)[:, :3].sum()) < 1e-6,
          f"Σ = {Fv.reshape(-1, 6)[:, :3].sum():.3e} N")
    # die Ersatzlast wirkt quer zum Stab
    check("sie wirkt quer zur Stabachse",
          abs(Fv.reshape(-1, 6)[:, 2]).max() < 1e-9,
          "keine Komponente in Stabrichtung (global z)")

    # Handrechnung: Feldmoment aus q ueber die Stablaenge
    res2, _i = T2.solve_theorie2(m, {"LF1": 1.0}, "K1", system, imperfektionen=True)
    mf = res2.member_forces(mem, 17)
    M_soll = d["q"] * L ** 2 / 8 * 1.0 / (1.0 - Nc / Ncr)
    M_ist = float(np.abs(mf["Mz"]).max())
    close("Feldmoment q L²/8 · 1/(1−N/N_cr), II. Ordnung", M_ist, M_soll, 0.05, " Nm")
    check("und es ist größer als nach I. Ordnung",
          M_ist > d["q"] * L ** 2 / 8,
          f"{M_ist:.0f} > {d['q'] * L ** 2 / 8:.0f} Nm")

    # gedrungener Stab: nach 5.3.2(6) nicht erforderlich
    m.load_cases["LF1"].nodal_loads.clear()
    m.load_node(ids[-1], Fz=-20e3, case="LF1")
    u2 = system.solve(solver.case_loads(m, {"LF1": 1.0})[0])
    r2 = solver.Results(name="K1", kind="combination", model=m)
    r2.u = u2.reshape(-1, 6)
    solver.postprocess(m, u2, r2)
    _F3, vk3 = T2.ersatzlasten_vorkruemmung(m, r2)
    check("bei kleiner Druckkraft entfällt sie nach 5.3.2(6)",
          vk3["anzahl"] == 0 and len(vk3["uebersprungen"]) == 1,
          str(vk3["uebersprungen"])[:80])


def test_im_modell_und_bericht():
    from statik3d.report import Report
    m = examples_lib.build_example("hall")
    m.design.theorie2 = "aus"
    an0 = solver.solve_all(m, design=False)
    check("ausgeschaltet passiert nichts",
          an0.theorie2 is None or not an0.theorie2.kombinationen)

    m1 = examples_lib.build_example("hall")
    m1.design.theorie2 = "auto"
    an1 = solver.solve_all(m1, design=False)
    check("„auto“ bestimmt α_cr für jede Kombination",
          len(an1.theorie2.kombinationen) == len(
              [c for c in m1.combinations.values() if c.is_uls]),
          f"{len(an1.theorie2.kombinationen)} Kombinationen")
    check("und rechnet nur, wenn α_cr unter der Grenze liegt",
          all(i.gerechnet == (i.alpha_cr < 10.0)
              for i in an1.theorie2.kombinationen.values()),
          f"min. α_cr = {an1.theorie2.alpha_cr_min:.2f}")

    m2 = examples_lib.build_example("hall")
    m2.design.theorie2 = "ein"
    an2 = solver.solve_all(m2, design=True)
    t2 = an2.theorie2
    check("„ein“ rechnet alle Kombinationen am verformten System",
          all(i.gerechnet for i in t2.kombinationen.values()),
          f"{len(t2.kombinationen)} Kombinationen")
    check("die Verformungen wachsen", t2.zuwachs_max > 0,
          f"max. {t2.zuwachs_max * 100:+.1f} %")
    worst = min(t2.kombinationen.values(), key=lambda i: i.alpha_cr)
    kn = int(np.argmax(np.abs(an2.combinations[worst.kombination].u).max(axis=1)))
    check("die Ergebnisse der Kombination sind ersetzt worden",
          an2.combinations[worst.kombination].info.get("theorie") == "II. Ordnung",
          f"maßgebender Knoten {kn}")
    check("die Zusammenfassung nennt es",
          "Theorie II. Ordnung" in an2.summary())
    # Analysis.summary haengte die Zeile bis zum 23.09.2026 zweimal an - einmal
    # hinter den Umhuellenden, einmal am Ende (Befund B125)
    check("… und zwar einmal",
          an2.summary().count("Theorie II. Ordnung:") == 1,
          f"{an2.summary().count('Theorie II. Ordnung:')} Zeilen")

    html = Report(m2, an2).html()
    for text in ("Berechnung nach Theorie II. Ordnung",
                 "Verzweigungslastfaktor", "Kriterium 5.2.1(3)",
                 "Schiefstellung φ = φ_0 α_h α_m",
                 "Ersatzhorizontalkräfte aus der Schiefstellung",
                 "Superposition", "gerechnet wurde"):
        check(f"Bericht nennt „{text}“", text in html)
    h0 = Report(m, an0).html()
    for text in ("Verzweigungslastfaktor und Berechnungsverfahren",
                 "Ersatzhorizontalkräfte aus der Schiefstellung",
                 'class="chapter">4&nbsp;&nbsp;Berechnung nach Theorie'):
        check(f"ohne Theorie II. Ordnung fehlt „{text[:40]}“", text not in h0)
    check("stattdessen sagt der Gültigkeitsbereich, was gerechnet wurde",
          "Gerechnet wird nach Theorie I. Ordnung" in h0)


def _druckkragarm(theorie2="aus", druck=5.0e5):
    """Kragarm unter Druck mit Querlast am Ende, drei Lastfaelle."""
    from statik3d.model import Section
    from statik3d import mesher
    m = Model("Druckkragarm")
    m.add_material(Material("S", E=2.1e11, rho=0.0))
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    ids = mesher.line_of_beams(m, "S", "R", (0, 0, 0), (3.0, 0, 0), 4)
    m.fix(ids[0], "all")
    for name, fy in (("LF1", 1.0e3), ("LF2", 2.0e3), ("LF3", 1.5e3)):
        m.add_load_case(name, "G")
        m.load_node(ids[-1], Fx=-druck, Fy=fy, case=name)
    m.design.theorie2 = theorie2
    m.design.imperfektionen = False
    return m, ids


def _lastfallsatz(html):
    import re
    treffer = re.search(r"Die im Kapitel „Ergebnisse“ ausgewiesenen Lastfälle[^<]*", html)
    return treffer.group(0) if treffer else ""


def test_bericht_lastfaelle_hoeherer_ordnung():
    """Das Theoriekapitel sagte bis zum 23.09.2026 ohne Ausnahme: „Die im
    Kapitel Ergebnisse ausgewiesenen Lastfälle sind Ergebnisse nach Theorie I.
    Ordnung" - auch fuer einen Lastfall, dessen Feld Theorie auf II./III.
    steht und dessen Ergebnis in an.cases nach II./III. Ordnung gerechnet ist
    (Druckkragarm: LF1 5,339 mm am Kragende statt linear 2,574 mm)."""
    from statik3d.report import Report
    m, ids = _druckkragarm("aus")
    m.load_cases["LF1"].theorie = "II"
    m.load_cases["LF2"].theorie = "III"
    an = solver.solve_all(m, design=False)
    lin = solver.solve_cases(m)
    sp = ids[-1]
    u_ii, u_lin = an.cases["LF1"].u[sp, 1] * 1e3, lin["LF1"].u[sp, 1] * 1e3
    check("Voraussetzung: LF1 ist nach II. Ordnung gerechnet",
          an.cases["LF1"].info.get("theorie") == "II. Ordnung" and u_ii > 1.5 * u_lin,
          f"u_y {u_ii:.3f} mm, linear {u_lin:.3f} mm")
    check("Voraussetzung: LF2 ist nach III. Ordnung gerechnet",
          an.cases["LF2"].info.get("theorie") == "III. Ordnung")
    satz = _lastfallsatz(Report(m, an).html())
    check("Theoriekapitel enthält den Satz über die Lastfälle", bool(satz))
    check("er nimmt LF1 als II. Ordnung aus", "LF1 (II. Ordnung)" in satz, satz[:160])
    check("und LF2 als III. Ordnung", "LF2 (III. Ordnung)" in satz)
    check("LF3 (linear) bleibt unter Theorie I. Ordnung",
          "nach Theorie I. Ordnung" in satz and "LF3" not in satz)

    m, ids = _druckkragarm("aus")
    for lc in m.load_cases.values():
        lc.theorie = "II"
    satz = _lastfallsatz(Report(m, solver.solve_all(m, design=False)).html())
    check("alle Lastfälle nach II. Ordnung: kein Wort von Theorie I. Ordnung",
          bool(satz) and "Theorie I. Ordnung" not in satz
          and all(f"LF{k} (II. Ordnung)" in satz for k in (1, 2, 3)), satz[:160])

    # Scheitert die Rechnung nach II. Ordnung, bleibt das lineare Ergebnis
    # (info["theorie"] = "I") - der Lastfall gehoert dann zu Theorie I.
    m, ids = _druckkragarm("aus")
    m.load_cases["LF1"].theorie = "II"
    m.load_cases["LF2"].theorie = "II"
    echt = T2.solve_theorie2

    def lf2_scheitert(model, factors, name, *a, **k):
        if name == "LF2":
            raise ValueError("Probe: II. Ordnung verweigert")
        return echt(model, factors, name, *a, **k)

    T2.solve_theorie2 = lf2_scheitert
    try:
        an = solver.solve_all(m, design=False)
    finally:
        T2.solve_theorie2 = echt
    satz = _lastfallsatz(Report(m, an).html())
    check("gescheiterter Lastfall zählt zu Theorie I. Ordnung",
          an.cases["LF2"].info.get("theorie") == "I" and "LF1 (II. Ordnung)" in satz
          and "LF2" not in satz, satz[:160])

    # Gegenprobe: lineare Lastfaelle, Kombination nach II. Ordnung - der Satz
    # bleibt, wie er war. Mit halbem Druck: K1 = LF1 + LF2 traegt sonst
    # 2 x 5e5 N, alpha_cr = 0,96 <= 1, und seit B131 wird K1 dann nicht nach
    # II. Ordnung gerechnet (Fehler statt Ergebnis) - ohne gerechnete
    # Kombination steht der Satz gar nicht im Kapitel. Mit 2,5e5 N je
    # Lastfall alpha_cr = 1,92, K1 gerechnet (gemessen 24.09.2026).
    from statik3d.model import Combination
    m, ids = _druckkragarm("ein", druck=2.5e5)
    m.combinations["K1"] = Combination("K1", {"LF1": 1.0, "LF2": 1.0}, "ULS")
    satz = _lastfallsatz(Report(m, solver.solve_all(m, design=False)).html())
    check("nur lineare Lastfälle: der Satz ist unverändert",
          satz == "Die im Kapitel „Ergebnisse“ ausgewiesenen Lastfälle sind Ergebnisse "
                  "nach Theorie I. Ordnung und dürfen nicht mehr überlagert werden; "
                  "die Kombinationen und die Umhüllenden sind es nicht.", satz[:160])


def _kapitel(html, titel):
    """Text eines Kapitels (von seiner Ueberschrift bis zur naechsten) oder None."""
    import re
    for teil in re.split(r'(?=<h2 id="[^"]*" class="chapter">)', html):
        if teil.startswith("<h2") and titel in teil[:300]:
            return teil
    return None


def _zelle(html, text):
    """Steht ``text`` als ganze Tabellenzelle in ``html``?"""
    import re
    return html is not None and re.search(r"<td[^>]*>" + re.escape(text) + "</td>", html) is not None


def _theorie_in_lastfalltabelle(html, name):
    """Spalte Theorie der Lastfalltabelle (Kapitel Einwirkungen) fuer ``name``."""
    import re
    tab = re.search(r"Lastfälle und Einwirkungskategorien.*?</table>", html, re.S)
    if not tab:
        return None
    for zeile in re.findall(r"<tr>(.*?)</tr>", tab.group(0), re.S):
        zellen = re.findall(r"<td[^>]*>(.*?)</td>", zeile, re.S)
        if zellen and zellen[0] == name:
            return zellen[11]
    return None


def test_bericht_lastfall_iii_ohne_rechnung_ii():
    """Wo der Bericht einen Lastfall auf III. Ordnung nennt.

    Das Benutzerhandbuch sagte in der Fassung vom 23.09.2026 (ad451de), der
    Bericht nenne die Lastfaelle auf II. oder III. Ordnung im Kapitel zur
    Theorie II. Ordnung. Den Satz dort gibt es aber nur, wenn in diesem
    Kapitel etwas nach II. Ordnung gerechnet ist (report/html.py
    chapter_theorie2, ``if gerechnet:``), und das Kapitel nur, wenn es
    Th2-Ergebnisse gibt. Gemessen 24.09.2026 am Druckkragarm mit Druck 10 kN:
    bei „automatisch“ hat K1 = LF1 + LF3 α_cr 47,9, bleibt ungerechnet, und
    LF2 (III) fehlt im Kapitel zur Theorie II. Ordnung; bei „aus“ fehlt das
    Kapitel ganz. Genannt ist LF2 dann in der Tabelle des Kapitels zur
    Theorie III. Ordnung und in der Spalte Theorie der Lastfalltabelle - so
    steht es jetzt im Handbuch, und diese Pruefung haelt es fest."""
    from statik3d.model import Combination
    from statik3d.report import Report
    t2_titel = "Berechnung nach Theorie II. Ordnung"
    t3_titel = "Berechnung nach Theorie III. Ordnung"

    # (a) automatisch, keine Kombination verlangt II. Ordnung
    m, ids = _druckkragarm("auto", druck=1.0e4)
    m.load_cases["LF2"].theorie = "III"
    m.combinations["K1"] = Combination("K1", {"LF1": 1.0, "LF3": 1.0}, "ULS")
    an = solver.solve_all(m, design=False)
    k1 = an.theorie2.kombinationen.get("K1") if an.theorie2 is not None else None
    check("Voraussetzung (auto): LF2 nach III. Ordnung gerechnet",
          an.cases["LF2"].info.get("theorie") == "III. Ordnung")
    check("Voraussetzung (auto): K1 hält α_cr ein und ist nicht gerechnet",
          k1 is not None and not k1.gerechnet and k1.alpha_cr >= k1.grenze
          and not any(i.gerechnet for i in an.theorie2.kombinationen.values()),
          f"α_cr {getattr(k1, 'alpha_cr', None)}")
    h = Report(m, an).html()
    kap2, kap3 = _kapitel(h, t2_titel), _kapitel(h, t3_titel)
    check("auto: Kapitel Theorie II steht, aber ohne Satz über die Lastfälle",
          kap2 is not None and not _lastfallsatz(kap2))
    check("auto: LF2 wird im Kapitel Theorie II nicht genannt",
          kap2 is not None and "LF2" not in kap2)
    check("auto: LF2 steht in der Tabelle des Kapitels Theorie III",
          _zelle(kap3, "LF2"))
    check("auto: Lastfalltabelle, Spalte Theorie von LF2 ist III",
          _theorie_in_lastfalltabelle(h, "LF2") == "III",
          repr(_theorie_in_lastfalltabelle(h, "LF2")))

    # (b) aus, nur ein Lastfall auf III: kein Kapitel zur Theorie II. Ordnung
    m, ids = _druckkragarm("aus")
    m.load_cases["LF2"].theorie = "III"
    an = solver.solve_all(m, design=False)
    h = Report(m, an).html()
    check("aus: LF2 nach III. Ordnung, kein Kapitel Theorie II",
          an.cases["LF2"].info.get("theorie") == "III. Ordnung"
          and an.theorie2 is None and _kapitel(h, t2_titel) is None
          and not _lastfallsatz(h))
    check("aus: LF2 in Tabelle Theorie III und Spalte Theorie III",
          _zelle(_kapitel(h, t3_titel), "LF2")
          and _theorie_in_lastfalltabelle(h, "LF2") == "III",
          repr(_theorie_in_lastfalltabelle(h, "LF2")))

    # (c) automatisch wie (a), dazu LF1 auf II: ein gelungener Lastfall auf
    # II. Ordnung ist selbst gerechnet (auch mit α_cr ueber der Grenze), also
    # steht der Satz und nennt beide
    m, ids = _druckkragarm("auto", druck=1.0e4)
    m.load_cases["LF1"].theorie = "II"
    m.load_cases["LF2"].theorie = "III"
    m.combinations["K1"] = Combination("K1", {"LF1": 1.0, "LF3": 1.0}, "ULS")
    an = solver.solve_all(m, design=False)
    lf1 = an.theorie2.kombinationen.get("LF1") if an.theorie2 is not None else None
    satz = _lastfallsatz(_kapitel(Report(m, an).html(), t2_titel) or "")
    check("auto mit LF1 auf II: LF1 gerechnet, obwohl α_cr über der Grenze",
          lf1 is not None and lf1.gerechnet and lf1.alpha_cr >= lf1.grenze,
          f"α_cr {getattr(lf1, 'alpha_cr', None)}")
    check("auto mit LF1 auf II: Satz nennt LF1 (II) und LF2 (III)",
          "LF1 (II. Ordnung)" in satz and "LF2 (III. Ordnung)" in satz, satz[:160])

    # (d) wie (a), aber K1 ausdruecklich auf II: gerechnet trotz α_cr 47,9,
    # der Satz steht und nennt LF2 (gemessen 24.09.2026, auch bei „aus“)
    m, ids = _druckkragarm("auto", druck=1.0e4)
    m.load_cases["LF2"].theorie = "III"
    m.combinations["K1"] = Combination("K1", {"LF1": 1.0, "LF3": 1.0}, "ULS")
    m.combinations["K1"].theorie = "II"
    an = solver.solve_all(m, design=False)
    k1 = an.theorie2.kombinationen.get("K1") if an.theorie2 is not None else None
    satz = _lastfallsatz(_kapitel(Report(m, an).html(), t2_titel) or "")
    check("auto mit K1 auf II: K1 gerechnet, Satz nennt LF2 (III)",
          k1 is not None and k1.gerechnet and "LF2 (III. Ordnung)" in satz,
          f"α_cr {getattr(k1, 'alpha_cr', None)} {satz[:120]}")


def main():
    print("=" * 92)
    print("STATIK3D - Verifikation Theorie II. Ordnung (DIN EN 1993-1-1, 5.2/5.3)")
    print("=" * 92)
    for t in (test_imperfektionsbeiwerte, test_alpha_cr, test_alpha_cr_zug_und_druck,
              test_alpha_cr_haeufung, test_vergroesserung, test_ersatzlasten,
              test_vorkruemmung, test_im_modell_und_bericht,
              test_bericht_lastfaelle_hoeherer_ordnung,
              test_bericht_lastfall_iii_ohne_rechnung_ii):
        print()
        t()
    ok = sum(1 for _n, o in RESULTS if o)
    print()
    print("=" * 92)
    print(f"Ergebnis: {ok}/{len(RESULTS)} Pruefungen bestanden")
    bad = [n for n, o in RESULTS if not o]
    if bad:
        print("FEHLGESCHLAGEN:", bad)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
