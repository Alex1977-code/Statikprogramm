"""Fachwerkstab mit Querlast (14.10.2026, Entscheidung des Anwenders).

1. **Ersatzlasten des Fachwerkstabs.** Ein Fachwerkstab (auch „nur Zug“,
   „nur Druck“) und ein Seil bekamen die Ersatzknotenlasten des beidseitig
   eingespannten Balkens, mit den Knotenmomenten -+q L^2/12. Der Fachwerkstab
   hat keine Drehsteifigkeit, die Momente landeten in den automatisch
   gehaltenen Drehfreiheitsgraden: an Gelenklagern standen Lagermomente
   My = +-1,333 kNm (4 m, 1 kN/m), und im Stab ergab sich der Verlauf des
   eingespannten Balkens mit q L^2/24 im Feld statt q L^2/8 - um den Faktor 3
   auf der unsicheren Seite. Richtig sind Ersatzlasten nur als Kraefte
   (q L/2 bei Gleichlast, die Auflagerkraefte des Einfeldtraegers bei Trapez-
   und Teillast), das Stabmoment als Einfeldtraeger und der Nachweis N + M.

Geprueft gegen Hand (Einfeldtraeger):

* Gleichlast quer: Auflager je q L/2, keine Lagermomente, M = q L^2/8 in
  Feldmitte, M = 0 an den Enden, V = -+q L/2.
* Trapezlast 0 -> 2 kN/m: Auflager q L/6 und q L/3, max M = q L^2/(9 sqrt 3)
  bei x = L/sqrt 3.
* Kurze Teillast (Ersatz fuer die Einzellast; eine Einzellast auf dem Stab
  kennt das Programm nicht): Auflager nach dem Hebelgesetz.
* Eigengewicht am schraegen Stab 3/4/5 m: quer 0,6 kN/m, M = 1,875 kNm, die
  Laengskomponente als N, Summe der Auflager = Gewicht.
* Lokale und globale Last quer in y: M_z.
* Temperatur mit Gradient: kein Moment im Fachwerkstab, kein Lagermoment.
* Zugstab mit Zug und Querlast, Druckstab mit Druck und Querlast: M = q L^2/8,
  Nachweis M_y + N (6.2.9.1) = M_Ed/(M_pl,Rd (1 - n^1,7)) (Rohr).
* Seil nach Theorie I. Ordnung: die Querlast geht als Kraft q L/2 an die
  Seilenden, das Seil traegt nur N (kein Moment, keine Querkraft), und das
  Ergebnis sagt es in einer Warnung; nach Theorie III. Ordnung keine Warnung.
* Fachwerktraeger mit Eigengewicht (ebenes Fachwerk): keine Lagermomente,
  Summe der Auflager = Gewicht + Last.

2. **Einzelknicken der Fachwerk-Druckstaebe in alpha_cr.** Die geometrische
   Steifigkeit des Fachwerkstabs ist die Saitenform N/L; das Knicken eines
   Druckstabs zwischen seinen Knoten steht darum nicht im alpha_cr des
   Systems. Je Druckstab (truss, auch „nur Druck“) wird alpha_cr,i =
   pi^2 E I/(L^2 N_Ed) mit der Systemlaenge und dem kleineren I ausgegeben, die
   Uebersicht nennt min(System; Einzelstab) mit dem massgebenden Stab.

* Pendelstab mit Querfeder (System k L/P = 200) aus Rundstahl 50 mm, 2 m,
  P = 1 kN: Einzelstab pi^2 E I/(L^2 P) = 158,97 ist massgebend.
* Rechteck 20 x 40 mm: das kleinere I (um z) zaehlt.
* Gelenkig gehaltener Druckstab aus zwei Elementen: L ist die Stablaenge;
  das System hat kein Verzweigungsproblem (alpha_cr unendlich), der
  Einzelstab schon.
* Ein Zugstab, ein gezogener Fachwerkstab und ein Balken zaehlen nicht.
* Theorie II. Ordnung („auto“) ueber solve_all: Zusammenfassung, Tabelle und
  Bericht nennen den Einzelstab.

Aufruf:  python -m tests.test_stab_querlast
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver, theorie3                                  # noqa: E402
from statik3d.ec3 import design                                        # noqa: E402
from statik3d.model import Material, Model, NodalLoad, Section         # noqa: E402

RESULTS = []
FY = 355e6
L = 4.0
Q = 1e3


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def nahe(name, ist, soll, tol, einheit=""):
    ist, soll = float(ist), float(soll)
    abw = abs(ist - soll) / (abs(soll) if abs(soll) > 1e-14 else 1.0)
    return check(name, abw <= tol, f"ist {ist:.9g} soll {soll:.9g} ({abw:.2e}) {einheit}")


def _rohr():
    return Section.pipe("RO", 0.1683, 0.008)


def _stab(typ="truss", nur="", X2=(L, 0, 0), rho=0.0):
    """Ein Stab von (0, 0, 0) nach X2, Rohr 168,3 x 8, S 355; Knoten 1 in
    x, y, z fest, Knoten 2 in y, z (gelenkig, verschieblich in x)."""
    m = Model("Querlast")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=rho, fy=FY))
    m.add_section(_rohr())
    a, b = m.add_node(0, 0, 0), m.add_node(*X2)
    m.fix(a, [0, 1, 2])
    m.fix(b, [1, 2])
    e = m.add_element(typ, [a, b], "S", "RO")
    m.elements[e].nur = nur
    m.add_member("S1", [e])
    m.add_load_case("LF1").gravity = [0, 0, 0]
    return m, e, a, b


def _rechnen(m):
    return solver.solve_static(m, case="LF1")


def _lagermoment(res):
    return float(np.abs(np.asarray(res.reactions)[:, 3:6]).max())


def _verlauf(m, res, n=401):
    return res.member_forces(m.members["S1"], n)


def test_gleichlast():
    print("\n--- 1: Gleichlast quer – Einfeldträger ---")
    m, e, a, b = _stab()
    m.load_beam(e, qz=-Q, case="LF1")
    r = _rechnen(m)
    R = np.asarray(r.reactions)
    nahe("Gleichlast: Auflager z Knoten 1 = q L/2", R[a, 2], Q * L / 2, 1e-9, "N")
    nahe("Gleichlast: Auflager z Knoten 2 = q L/2", R[b, 2], Q * L / 2, 1e-9, "N")
    check("Gleichlast: keine Lagermomente an den Gelenklagern", _lagermoment(r) <= 1e-6,
          f"max |M| {_lagermoment(r):.6g} Nm")
    mf = _verlauf(m, r)
    j = len(mf["x"]) // 2
    nahe("Gleichlast: Feldmoment M_y = q L²/8", abs(mf["My"][j]), Q * L ** 2 / 8, 1e-9, "Nm")
    check("Gleichlast: Moment an den Enden 0", max(abs(mf["My"][0]), abs(mf["My"][-1])) <= 1e-6,
          f"({mf['My'][0]:.3g}, {mf['My'][-1]:.3g}) Nm")
    nahe("Gleichlast: Querkraft am Ende = q L/2", abs(mf["Vz"][0]), Q * L / 2, 1e-9, "N")
    # die Last bleibt im Gleichgewicht
    nahe("Gleichlast: Summe der Auflager = q L", R[:, 2].sum(), Q * L, 1e-9, "N")


def test_trapez_und_teillast():
    print("\n--- 1: Trapez- und Teillast – Hebelgesetz ---")
    m, e, a, b = _stab()
    q2 = 2e3
    m.load_beam(e, qz=0.0, q2=[0, 0, -q2], case="LF1")
    r = _rechnen(m)
    R = np.asarray(r.reactions)
    nahe("Trapez 0 → 2 kN/m: Auflager 1 = q L/6", R[a, 2], q2 * L / 6, 1e-9, "N")
    nahe("Trapez 0 → 2 kN/m: Auflager 2 = q L/3", R[b, 2], q2 * L / 3, 1e-9, "N")
    check("Trapez: keine Lagermomente", _lagermoment(r) <= 1e-6, f"{_lagermoment(r):.3g} Nm")
    from statik3d.solver import beam_station_forces
    st = beam_station_forces(m, r, e, 20001)
    nahe("Trapez: max M = q L²/(9 √3)", float(np.abs(st["My"]).max()),
         q2 * L ** 2 / (9 * math.sqrt(3)), 1e-6, "Nm")
    nahe("Trapez: Stelle des Maximums x = L/√3", st["x"][int(np.argmax(np.abs(st["My"])))],
         L / math.sqrt(3), 1e-3, "m")
    # kurze Teillast 10 kN/m auf 1,0 .. 1,1 m = 1 kN bei 1,05 m
    m, e, a, b = _stab()
    m.load_beam(e, qz=-10e3, a=1.0, b=1.1, case="LF1")
    r = _rechnen(m)
    R = np.asarray(r.reactions)
    nahe("Teillast 1 kN bei 1,05 m: Auflager 1 = 1 kN · 2,95/4", R[a, 2], 1e3 * 2.95 / 4, 1e-9, "N")
    nahe("Teillast: Auflager 2 = 1 kN · 1,05/4", R[b, 2], 1e3 * 1.05 / 4, 1e-9, "N")
    check("Teillast: keine Lagermomente", _lagermoment(r) <= 1e-6, f"{_lagermoment(r):.3g} Nm")
    st = beam_station_forces(m, r, e, 81)                 # x = 0,05 m Raster: 1,05 ist dabei
    j = int(np.argmin(np.abs(st["x"] - 1.05)))
    nahe("Teillast: M bei 1,05 m = R1 · 1,05 − q · 0,05²/2", abs(st["My"][j]),
         1e3 * 2.95 / 4 * 1.05 - 10e3 * 0.05 ** 2 / 2, 1e-9, "Nm")


def test_eigengewicht_schraeg():
    print("\n--- 1: Eigengewicht am schrägen Fachwerkstab 3/4/5 m ---")
    A = _rohr().A
    m, e, a, b = _stab(X2=(3.0, 0.0, 4.0), rho=1e3 / (A * 9.81))
    m.fix(b, [0, 1, 2])
    m.load_cases["LF1"].gravity = [0, 0, -9.81]
    r = _rechnen(m)
    R = np.asarray(r.reactions)
    nahe("schräg: Summe der Auflager z = Gewicht 5 kN", R[:, 2].sum(), 5e3, 1e-9, "N")
    check("schräg: keine Lagermomente", _lagermoment(r) <= 1e-6, f"{_lagermoment(r):.3g} Nm")
    mf = _verlauf(m, r)
    j = len(mf["x"]) // 2
    M = max(abs(mf["My"][j]), abs(mf["Mz"][j]))
    nahe("schräg: Feldmoment aus 0,6 kN/m quer = 1,875 kNm", M, 0.6e3 * 25 / 8, 1e-9, "Nm")
    nahe("schräg: N am unteren Ende aus 0,8 kN/m längs = −2 kN (Druck)", mf["N"][-1] if mf["N"][0] > 0
         else mf["N"][0], -2e3, 1e-9, "N")


def test_querlast_y():
    print("\n--- 1: Querlast in y, global und lokal ---")
    for system in ("global", "local"):
        m, e, a, b = _stab()
        m.load_beam(e, qy=-Q, system=system, case="LF1")
        r = _rechnen(m)
        mf = _verlauf(m, r)
        j = len(mf["x"]) // 2
        nahe(f"qy {system}: Feldmoment M_z = q L²/8", abs(mf["Mz"][j]), Q * L ** 2 / 8, 1e-9, "Nm")
        check(f"qy {system}: keine Lagermomente", _lagermoment(r) <= 1e-6, f"{_lagermoment(r):.3g} Nm")


def test_temperatur():
    print("\n--- 1: Temperatur mit Gradient am Fachwerkstab ---")
    m, e, a, b = _stab()
    m.fix(b, [0])
    m.load_temp(e, 20.0, dT_z=30.0, case="LF1")
    r = _rechnen(m)
    mf = _verlauf(m, r)
    check("Temperatur: kein Moment im Fachwerkstab", float(np.abs(mf["My"]).max()) <= 1e-6,
          f"{float(np.abs(mf['My']).max()):.3g} Nm")
    check("Temperatur: keine Lagermomente", _lagermoment(r) <= 1e-6, f"{_lagermoment(r):.3g} Nm")
    mat, sec = m.materials["S"], m.sections["RO"]
    nahe("Temperatur: Zwangskraft −E A α ΔT", mf["N"][0], -mat.E * sec.A * mat.alpha * 20.0, 1e-9, "N")


def _nachweis_hand(sec, N, M):
    """M_y + N (6.2.9.1) am Rohr: M_Ed/(M_pl,Rd (1 - n^1,7)), gamma_M0 = 1."""
    n = abs(N) / (sec.A * FY)
    return M / (sec.Wpl_y * FY * (1.0 - n ** 1.7))


def test_zug_druckstab():
    print("\n--- 1: Zug- und Druckstab mit Querlast, Nachweis N + M ---")
    for nur, N, wo in (("zug", 10e3, "qz"), ("druck", -10e3, "qy")):
        m, e, a, b = _stab(nur=nur)
        m.load_beam(e, **{wo: -Q}, case="LF1")
        m.load_cases["LF1"].nodal_loads.append(NodalLoad(b, [N, 0, 0, 0, 0, 0]))
        r = _rechnen(m)
        mf = _verlauf(m, r)
        j = len(mf["x"]) // 2
        M = max(abs(mf["My"][j]), abs(mf["Mz"][j]))
        text = "Zugstab" if nur == "zug" else "Druckstab"
        nahe(f"{text}: N = {N / 1e3:+.0f} kN", mf["N"][j], N, 1e-9, "N")
        nahe(f"{text}: Feldmoment = q L²/8", M, Q * L ** 2 / 8, 1e-9, "Nm")
        check(f"{text}: keine Lagermomente", _lagermoment(r) <= 1e-6, f"{_lagermoment(r):.3g} Nm")
        mc = design.check_member(m, m.members["S1"], {"LF1": r})
        qs = max((c for c in mc.section_checks), key=lambda c: c["util"])
        nahe(f"{text}: Querschnittsnachweis M + N gegen Hand", qs["util"],
             _nachweis_hand(m.sections["RO"], N, Q * L ** 2 / 8), 1e-6)
        check(f"{text}: maßgebend ist M + N (6.2.9.1)", "+N" in qs["name"], qs["name"])


def test_seil():
    print("\n--- 1: Seil mit Querlast – Theorie I. Ordnung meldet, Theorie III. Ordnung rechnet ---")
    m, e, a, b = _stab(typ="seil")
    m.load_beam(e, qz=-Q, case="LF1")
    m.load_cases["LF1"].nodal_loads.append(NodalLoad(b, [10e3, 0, 0, 0, 0, 0]))
    r = _rechnen(m)
    R = np.asarray(r.reactions)
    nahe("Seil Th I: Auflager z = q L/2", R[a, 2], Q * L / 2, 1e-9, "N")
    check("Seil Th I: keine Lagermomente", _lagermoment(r) <= 1e-6, f"{_lagermoment(r):.3g} Nm")
    mf = _verlauf(m, r)
    check("Seil Th I: kein Moment und keine Querkraft im Seil",
          max(float(np.abs(mf[k]).max()) for k in ("My", "Mz", "Vy", "Vz")) <= 1e-9)
    nahe("Seil Th I: N = 10 kN", mf["N"][0], 10e3, 1e-9, "N")
    s = r.summary()
    check("Seil Th I: das Ergebnis warnt (Seil, q L/2, Theorie III. Ordnung)",
          "Querlast auf Seil S1" in s and "q L/2" in s and "Theorie III. Ordnung" in s,
          [z for z in s.splitlines() if "Seil" in z][:1])
    an = solver.solve_all(m)
    check("Seil Th I: auch die Zusammenfassung aller Ergebnisse warnt",
          "Querlast auf Seil S1" in an.summary())
    # das vorgespannte Seil 10 m mit qz = -1 kN/m (tests.test_stab_nachzug):
    # nach Theorie I. Ordnung die Warnung, nach Theorie III. Ordnung die
    # Kettenlinie ohne Warnung
    from tests.test_stab_nachzug import _seil
    m2, _b = _seil("global")
    check("Seil 10 m Th I: Warnung", "Querlast auf Seil Tragseil" in _rechnen(m2).summary())
    res3, info3 = theorie3.solve_theorie3(m2, {"LF1": 1.0}, "LF1", schritte=5, imperfektionen=False)
    check("Seil 10 m Th III: gerechnet", info3.gerechnet, info3.fehler)
    check("Seil 10 m Th III: keine Warnung", "Querlast auf Seil" not in res3.summary())
    nahe("Seil 10 m Th III: Summe der Auflager z = q L", np.asarray(res3.reactions)[:, 2].sum(), 10 * Q,
         1e-9, "N")


def test_fachwerktraeger():
    print("\n--- 1: Fachwerkträger mit Eigengewicht ---")
    from statik3d.examples_lib import truss_bridge_example
    m = truss_bridge_example()
    lc = m.case()
    lc.gravity = [0, 0, -9.81]
    r = solver.solve_static(m, case=lc.name)
    R = np.asarray(r.reactions)
    G = sum(m.materials[el.mat].rho * m.sections[el.sec].A * m.element_length(i) * 9.81
            for i, el in enumerate(m.elements))
    nahe("Fachwerkträger: Summe der Auflager z = Gewicht + 4 x 40 kN", R[:, 2].sum(), G + 160e3, 1e-9, "N")
    check("Fachwerkträger: keine Lagermomente", _lagermoment(r) <= 1e-6, f"{_lagermoment(r):.3g} Nm")


# --------------------------------------------------------------------------
# 2. Einzelknicken der Fachwerk-Druckstaebe
# --------------------------------------------------------------------------
def _ac(m, faktoren=None):
    from statik3d import theorie2
    system = solver.StaticSystem(m)
    u = system.solve(solver.case_loads(m, faktoren or {"LF1": 1.0})[0])
    return theorie2.alpha_cr(m, system, u)


def test_einzelstab_pendel():
    print("\n--- 2: Pendelstab – System k L/P gegen Einzelstab π²EI/(L²P) ---")
    from tests.test_stab_nachzug import K_FEDER, L_PENDEL, _pendel
    m, e, b = _pendel()
    ac = _ac(m)
    I = math.pi * 0.05 ** 4 / 64
    soll = math.pi ** 2 * 210e9 * I / (L_PENDEL ** 2 * 1e3)
    nahe("Pendel: alpha_cr des Systems = k L/P = 200", ac["alpha_cr"], K_FEDER * L_PENDEL / 1e3, 1e-9)
    nahe("Pendel: alpha_cr,i Einzelstab = π²EI/(L²P)", ac.get("alpha_cr_stab", math.inf), soll, 1e-9)
    check("Pendel: der Stab heißt St", ac.get("stab") == "St", str(ac.get("stab")))
    d = (ac.get("einzelstaebe") or [{}])[0]
    nahe("Pendel: N_Ed = 1 kN", d.get("N", 0.0), 1e3, 1e-9, "N")
    nahe("Pendel: L = 2 m", d.get("L", 0.0), L_PENDEL, 1e-12, "m")
    # „nur Druck“ zaehlt, „nur Zug“ faellt bei Druck aus und zaehlt nicht
    m2, _e2, _b2 = _pendel(nur="druck")
    nahe("Pendel „nur Druck“: Einzelstab ebenso", _ac(m2).get("alpha_cr_stab", math.inf), soll, 1e-9)
    m3, _e3, _b3 = _pendel(typ="beam")
    check("Pendel als Balken: kein Einzelstab (sein Knicken steht im System)",
          not _ac(m3).get("einzelstaebe") and "alpha_cr_stab" in _ac(m3))


def test_einzelstab_achsen_und_laenge():
    print("\n--- 2: Rechteck 20 x 40 mm, Stab aus zwei Elementen, gelenkig ---")
    m = Model("Druckstab")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=0.0, fy=FY))
    m.add_section(Section.rectangle("R", 0.02, 0.04))
    a, c, b = m.add_node(0, 0, 0), m.add_node(1.5, 0, 0), m.add_node(3.0, 0, 0)
    m.fix(a, [0, 1, 2])
    m.fix(b, [1, 2])
    m.fix(c, [1, 2])
    e1 = m.add_element("truss", [a, c], "S", "R")
    e2 = m.add_element("truss", [c, b], "S", "R")
    m.add_member("D1", [e1, e2])
    # daneben ein Zugstab (gedrueckt, faellt aus) und ein gezogener Fachwerkstab
    d1, d2 = m.add_node(0, 1, 0), m.add_node(3, 1, 0)
    m.fix(d1, [0, 1, 2])
    m.fix(d2, [1, 2])
    ez = m.add_element("truss", [d1, d2], "S", "R")
    m.elements[ez].nur = "zug"
    m.add_member("Z1", [ez])
    g1, g2 = m.add_node(0, 2, 0), m.add_node(3, 2, 0)
    m.fix(g1, [0, 1, 2])
    m.fix(g2, [1, 2])
    m.add_member("G1", [m.add_element("truss", [g1, g2], "S", "R")])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    P = 5e3
    lc.nodal_loads.append(NodalLoad(b, [-P, 0, 0, 0, 0, 0]))
    lc.nodal_loads.append(NodalLoad(d2, [-P, 0, 0, 0, 0, 0]))
    lc.nodal_loads.append(NodalLoad(g2, [+P, 0, 0, 0, 0, 0]))
    ac = _ac(m)
    Iz = 0.04 * 0.02 ** 3 / 12
    soll = math.pi ** 2 * 210e9 * Iz / (3.0 ** 2 * P)
    check("Druckstab: das System hat kein Verzweigungsproblem (alpha_cr ∞)", math.isinf(ac["alpha_cr"]),
          f"{ac['alpha_cr']}")
    nahe("Druckstab: alpha_cr,i mit dem kleineren I (um z) und L = 3 m", ac.get("alpha_cr_stab", math.inf),
         soll, 1e-9)
    check("Druckstab: Achse z", (ac.get("einzelstaebe") or [{}])[0].get("achse") == "z")
    check("Zugstab und gezogener Fachwerkstab zählen nicht",
          [d["stab"] for d in ac.get("einzelstaebe") or []] == ["D1"],
          str([d["stab"] for d in ac.get("einzelstaebe") or []]))


def test_einzelstab_ausgabe():
    print("\n--- 2: Ausgabe über „Alle Lastfälle“: Zusammenfassung, Tabelle, Bericht ---")
    from tests.test_stab_nachzug import _pendel
    from statik3d.report import Report
    m, e, b = _pendel()
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    m.design.theorie2 = "auto"
    an = solver.solve_all(m, design=False)
    t2 = an.theorie2
    info = t2.kombinationen.get("K1") if t2 else None
    check("K1: Einzelstab im α_cr-Ergebnis", info is not None and info.stab_massgebend == "St"
          and math.isfinite(info.alpha_cr_stab), str(getattr(info, "stab_massgebend", None)))
    s = t2.summary() if t2 else ""
    check("Zusammenfassung: min(System; Einzelstab) mit dem Stab",
          "min. α_cr = 158.97 (System 200.00; Einzelstab 158.97, Stab St)" in s, s)
    check("Zusammenfassung aller Ergebnisse ebenso", "Einzelstab 158.97, Stab St" in an.summary())
    tab = t2.table()
    check("Tabelle: Spalte „α_cr Einzelstab“ mit Stab", tab[0][2] == "α_cr Einzelstab"
          and tab[1][2] == "158.97 (St)", str(tab[:2]))
    h = Report(m, an).html()
    for text in ("Einzelknicken der Fachwerk-Druckstäbe", "α_cr,i = π²·E·I/(L²·N_Ed)",
                 "maßgebend min(System; Einzelstab)", "Einzelstab St"):
        check(f"Bericht nennt „{text}“", text in h)


def main():
    for t in (test_gleichlast, test_trapez_und_teillast, test_eigengewicht_schraeg, test_querlast_y,
              test_temperatur, test_zug_druckstab, test_seil, test_fachwerktraeger,
              test_einzelstab_pendel, test_einzelstab_achsen_und_laenge, test_einzelstab_ausgabe):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
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
