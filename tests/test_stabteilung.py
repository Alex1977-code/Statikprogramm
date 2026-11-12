"""
Interne Stabteilung nach Theorie II. und III. Ordnung und Stablast am Gelenk
nach Theorie III. Ordnung (12.11.2026, statik3d/stabteilung.py).

Nachstellung vom 11.11.2026: Einfeldtraeger 6 m, links eingespannt, rechts
Stabendgelenk, Druck 0,6 N_cr, q = 5 kN/m, ein Element. Theorie II. Ordnung
gab 22,5 kNm am Lager (das Ergebnis nach Theorie I) statt 44,207 kNm, ohne
Hinweis; Theorie III. Ordnung 15,0 kNm am Gelenk (q L²/12 statt 0) und 15,0
statt 22,5 am Stabanfang. Entscheidung des Anwenders: „interne stabteilung
sinnvoll vornehmen zb anzahl teilungen nach länge des stabes“.

Zwei Wege je Wert: die Loesung der Differentialgleichung und dasselbe System
mit von Hand geteilten Elementen (gleiche Teilung, gleiche Lasten).

Aufruf:  python -m tests.test_stabteilung
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
L = 6.0
Q = 5e3
P = 0.6 * 20.19 * EI / L ** 2


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def _modell():
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1.0, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.05))
    m.design.imperfektionen = False
    return m


def _analytisch() -> float:
    """Lagermoment eingespannt/gelenkig mit Druck P und q (Betrag):
    w = A + B x + C cos kx + D sin kx + q x²/(2P); w(0) = w'(0) = w(L) = w''(L) = 0."""
    k = math.sqrt(P / EI)
    Amat = np.array([[1, 0, 1, 0], [0, 1, 0, k],
                     [1, L, math.cos(k * L), math.sin(k * L)],
                     [0, 0, -k ** 2 * math.cos(k * L), -k ** 2 * math.sin(k * L)]])
    rhs = -np.array([0.0, 0.0, Q * L ** 2 / (2 * P), Q / P])
    _a, _b, C, _d = np.linalg.solve(Amat, rhs)
    return abs(EI * (-k ** 2 * C + Q / P))


def _einfeld(n, theorie, teilung=None, lasten=None):
    """Der Einfeldtraeger in n Elementen; ``lasten(m, els)`` statt q auf jedem
    Element. Rueckgabe (Modell, Ergebnis, Knoten, Elemente)."""
    from statik3d import solver
    m = _modell()
    if teilung is not None:
        m.netz.stabteilung = teilung
    ids = [m.add_node(L * j / n, 0, 0) for j in range(n + 1)]
    els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q") for j in range(n)]
    m.fix(ids[0], "all")
    m.add_hinge("GE", end=1, phiy="free", phiz="free")
    m.apply_hinge(els[-1], "GE")
    m.fix(ids[-1], [1, 2, 3, 4, 5])
    m.load_node(ids[-1], Fx=-P)
    if lasten is None:
        for e in els:
            m.load_beam(e, qz=-Q)
    else:
        lasten(m, els)
    m.load_cases["LF1"].theorie = theorie
    an = solver.solve_all(m, workers=1, design=False)
    return m, an.cases["LF1"], ids, els


def test_theorie2_ein_element():
    soll = _analytisch()
    m, r, ids, els = _einfeld(1, "II")
    b = r.beam_forces[els[0]]
    M0, ML, RM = abs(b["My"][0]), abs(b["My"][-1]), abs(r.reactions[ids[0], 4])
    check(f"Th II, ein Element: Lagermoment = Differentialgleichung {soll / 1e3:.3f} kNm auf 0,1 % "
          "(vorher 22,500)", abs(RM / soll - 1) < 1e-3, f"{RM / 1e3:.4f} kNm")
    check("… Stab My(0) = Lagermoment, My(L) = 0 am Gelenk",
          abs(M0 - RM) < 1e-6 * RM and ML < 1e-6 * RM, f"My(0) {M0 / 1e3:.4f}, My(L) {ML:.2e}")
    check("… Modell unverändert: 2 Knoten, 1 Element, Gelenk am Element; Ergebnis je Knoten des Modells",
          len(m.nodes) == 2 and len(m.elements) == 1 and m.elements[0].hinges == [10, 11]
          and r.u.shape == (2, 6) and r.reactions.shape == (2, 6),
          f"{len(m.nodes)} Knoten, {len(m.elements)} Elemente, Gelenk {m.elements[0].hinges}, u {r.u.shape}")
    check("… intern in die Stabteilung der Netzeinstellungen (10) geteilt",
          r.info.get("stabteilung") == {0: 10}, str(r.info.get("stabteilung")))


def test_theorie2_feld_wie_von_hand():
    """Zweiter Weg: dasselbe System, von Hand in 10 Elemente geteilt - das
    Feld des einen Elements muss an jeder Stelle gleich sein."""
    from statik3d import solver
    m1, r1, _i1, e1 = _einfeld(1, "II")
    m2, r2, _i2, e2 = _einfeld(10, "II")
    st = solver.beam_station_forces(m1, r1, e1[0], 41)
    abw = 0.0
    for j, (x, My) in enumerate(zip(st["x"], st["My"])):
        # 41 Stellen im Abstand 0,15 m: je Element von Hand 5 Stellen, deckungsgleich
        k = min(j // 4, 9)
        s2 = solver.beam_station_forces(m2, r2, e2[k], 5)
        ref = float(s2["My"][j - 4 * k])
        abw = max(abw, abs(My - ref))
    check("Th II: Feld des geteilten Elements = 10 Elemente von Hand (41 Stellen, auf 1 Nm)",
          abw < 1.0, f"größte Abweichung {abw:.3e} Nm, max |My| {np.abs(st['My']).max() / 1e3:.3f} kNm")
    vz = abs(st["Vz"][-1] - r1.reactions[1, 2])
    check("… Querkraft am Gelenk = Auflagerkraft rechts", vz < 1e-6 * abs(r1.reactions[1, 2]),
          f"{st['Vz'][-1]:.3f} / {r1.reactions[1, 2]:.3f} N")


def test_teillast():
    """Trapez-Teillast 2 → 6 kN/m von 1,0 bis 4,5 m: intern geteilt gegen 10
    Elemente mit von Hand zugeschnittenen Lasten."""
    a, b, q1, q2 = 1.0, 4.5, 2e3, 6e3

    def zehn(m, els):
        h = L / 10
        for k, e in enumerate(els):
            lo, hi = max(a, k * h), min(b, (k + 1) * h)
            if hi <= lo:
                continue
            qa = q1 + (q2 - q1) * (lo - a) / (b - a)
            qb = q1 + (q2 - q1) * (hi - a) / (b - a)
            _teillast(m, e, qa, qb, lo - k * h, hi - k * h, h)

    def eins_direkt(m, els):
        _teillast(m, els[0], q1, q2, a, b, L)

    _m1, r1, i1, _e1 = _einfeld(1, "II", lasten=eins_direkt)
    _m2, r2, i2, _e2 = _einfeld(10, "II", lasten=zehn)
    M1, M2 = abs(r1.reactions[i1[0], 4]), abs(r2.reactions[i2[0], 4])
    check("Th II, Trapez-Teillast auf einem Element = 10 Elemente mit zugeschnittenen Lasten (auf 1e-6)",
          abs(M1 / M2 - 1) < 1e-6, f"{M1 / 1e3:.5f} / {M2 / 1e3:.5f} kNm")


def _teillast(m, e, qa, qb, a, b, Le):
    """Eine Stablast in lokal z von a bis b (b = None bis zum Ende)."""
    from statik3d.model import BeamLoad
    tol = 1e-12
    bl = BeamLoad(elem=int(e), q=[0.0, 0.0, -qa], q2=[0.0, 0.0, -qb], system="global",
                  a=0.0 if a <= tol else a, b=None if Le - b <= tol else b)
    m.load_cases["LF1"].beam_loads.append(bl)


def test_theorie3_gelenk():
    soll = _analytisch()
    m, r, ids, els = _einfeld(1, "III")
    b = r.beam_forces[els[0]]
    M0, ML, RM = abs(b["My"][0]), abs(b["My"][-1]), abs(r.reactions[ids[0], 4])
    check("Th III, ein Element: My(L) = 0 am Gelenk (vorher 15,0 kNm = q L²/12)", ML < 1e-6 * RM,
          f"My(L) {ML:.3e} Nm")
    check("… Stab My(0) = Lagermoment (vorher 15,0 gegen 22,5 kNm)", abs(M0 - RM) < 1e-6 * RM,
          f"{M0 / 1e3:.4f} / {RM / 1e3:.4f} kNm")
    check(f"… Lagermoment auf 0,5 % an der Differentialgleichung {soll / 1e3:.3f} kNm (20 Teile; vorher 22,5)",
          abs(RM / soll - 1) < 5e-3, f"{RM / 1e3:.4f} kNm")
    _m2, r2, i2, e2 = _einfeld(2, "III", teilung=1)
    ML2 = abs(r2.beam_forces[e2[-1]]["My"][-1])
    check("Th III ohne Stabteilung, 2 Elemente: My(L) = 0 am Gelenk (vorher 3,75 kNm)",
          ML2 < 1e-6 * abs(r2.reactions[i2[0], 4]), f"{ML2:.3e} Nm")


def test_teilregel():
    from statik3d import stabteilung as st
    from statik3d.model import Section
    m = _modell()
    ids = [m.add_node(L * j / 20, 0, 0) for j in range(21)]
    for j in range(20):
        m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q")
    check("Teilregel: gerade Kette aus 20 Elementen ohne Stab bleibt ganz (sie hat schon ≥ 10 Abschnitte)",
          st.teilzahlen(m) == {}, str(st.teilzahlen(m)))
    m = _modell()
    a, b, c = m.add_node(0, 0, 0), m.add_node(3, 0, 0), m.add_node(6, 0, 0)
    e1 = m.add_element("beam", [a, b], "ST", "Q")
    e2 = m.add_element("beam", [b, c], "ST", "Q")
    m.add_member("S1", [e1, e2])
    check("… Stab aus 2 Elementen: je 5 Teile (10 je Stab)", st.teilzahlen(m) == {e1: 5, e2: 5},
          str(st.teilzahlen(m)))
    m.add_section(Section("STARR", A=1e3, Iy=1e2, Iz=1e2, It=1e2, zmax=0.1, ymax=0.1))
    d = m.add_node(3, 0.2, 0)
    e3 = m.add_element("beam", [b, d], "ST", "STARR")
    z = st.teilzahlen(m, kraefte={e1: -1e5, e2: -1e5, e3: -1e3})
    check("… starrer Kurzstab mit kleiner Normalkraft (unter 1/1000 seiner Euler-Last) bleibt ganz",
          e3 not in z and z.get(e1) == 5, str(z))
    z = st.teilzahlen(m, kraefte={e1: 0.0, e2: -1e5, e3: 0.0})
    check("… ein Element ohne Normalkraft bleibt ganz, das gedrückte wird geteilt",
          e1 not in z and z.get(e2) == 5, str(z))


def test_beidseitig_frei():
    """Torsion an beiden Enden frei: das geteilte Element darf keinen losen
    Zwischenknoten haben."""
    from statik3d import solver
    m = _modell()
    a, b, c = m.add_node(0, 0, 0), m.add_node(3, 0, 0), m.add_node(6, 0, 0)
    e1 = m.add_element("beam", [a, b], "ST", "Q")
    e2 = m.add_element("beam", [b, c], "ST", "Q")
    m.elements[e2].hinges = [3, 9]
    m.fix(a, "all")
    m.fix(c, [1, 2, 3])
    m.load_node(c, Fx=-1e5)
    for e in (e1, e2):
        m.load_beam(e, qz=-1e3)
    m.load_cases["LF1"].theorie = "II"
    try:
        r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
        ok = r.info.get("theorie") == "II. Ordnung" and r.info.get("stabteilung", {}).get(e2) == 10
        txt = f"{r.info.get('theorie')}, Teilung {r.info.get('stabteilung')}"
    except Exception as ex:                     # noqa: BLE001
        ok, txt = False, str(ex)[:120]
    check("Torsion an beiden Enden eines Elements frei: Th II rechnet geteilt (nicht singulär)", ok, txt)


def test_ohne_teilung():
    _m, r, ids, _e = _einfeld(1, "II", teilung=1)
    RM = abs(r.reactions[ids[0], 4])
    check("Stabteilung 1 in den Netzeinstellungen: keine interne Teilung (Lagermoment wie bisher 22,500)",
          abs(RM - Q * L ** 2 / 8) < 1e-6 * RM and "stabteilung" not in r.info, f"{RM / 1e3:.4f} kNm")


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    a, b = rv.merkmal("stabteilung_theorie"), rv.merkmal("theorie3_gelenk_last")
    check("Verfahrenstabelle: interne Stabteilung (Stand 29) und Gelenklast Th III (Stand 30) als "
          "Fehlerkorrektur", a is not None and b is not None and a.wechsel[-1].stand == 29
          and b.wechsel[-1].stand == 30 and a.wechsel[-1].art == rv.FEHLERKORREKTUR
          and b.wechsel[-1].art == rv.FEHLERKORREKTUR and rv.VERFAHRENSSTAND >= 30,
          f"Stand {rv.VERFAHRENSSTAND}")
    m = _modell()
    n1, n2 = m.add_node(0, 0, 0), m.add_node(6, 0, 0)
    m.add_element("beam", [n1, n2], "ST", "Q")
    fein = _modell()
    ids = [fein.add_node(L * j / 20, 0, 0) for j in range(21)]
    for j in range(20):
        fein.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q")
    check("… betroffen: Balken in einem Element ja, in 20 Elementen nein",
          a.betrifft(m) and not a.betrifft(fein))


def main():
    for t in (test_theorie2_ein_element, test_theorie2_feld_wie_von_hand, test_teillast,
              test_theorie3_gelenk, test_teilregel, test_beidseitig_frei, test_ohne_teilung,
              test_verfahrenstabelle):
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
