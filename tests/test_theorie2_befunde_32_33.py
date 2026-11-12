"""
Theorie II. Ordnung: Befunde 32 und 33 des Pruefberichts vom 11.11.2026
(Behebung freigegeben am 12.11.2026).

Befund 32: Ein Balken mit Woelbkrafttorsion (7 FHG je Knoten, „woelb“)
bekam nach Theorie II. Ordnung weder den Anteil k_G u in den
Stabendkraeften noch den Feldanteil N w (Korrektur A8). Kragarm 5 m, Druck
0,6 N_cr, Kopflast 2 kN, ein Element: Stab My(0) 23,997 gegen Lager
22,158 kNm, Vz(0) 4,544 gegen Rz 2,000 kN. Die interne Stabteilung teilt
diese Balken nicht; der Fehler steht mit und ohne Teilung.

Befund 33: Ein Laengsgelenk (ux frei, auch Federgelenk ux mit k = 0) traegt
keine Normalkraft. Die geometrische Steifigkeit nahm trotzdem E A Δl/L aus
den Knotenverschiebungen: Stuetze 5 m, oben Laengsgelenk, die Kopflast von
1 MN traegt ein Haenger, Querlast 1 kN/m. Ergebnis N = 0, aber alpha_cr
endlich und max |My| nach Theorie II. Ordnung 4,11 statt 3,125 kNm (Druck)
bzw. 2,68 statt 3,125 kNm (Zug, unsichere Seite).

Zwei Wege je Wert: die geschlossene Loesung der Differentialgleichung
(Kragarm mit Druck und Querlast; Einfeldtraeger ohne Normalkraft q L²/8) und
ein zweiter Programmweg (derselbe Balken ohne Woelbkrafttorsion; Theorie I.
Ordnung).

Aufruf:  python -m tests.test_theorie2_befunde_32_33
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


# ---------------------------------------------------------------- Befund 32
LK = 5.0                                     # Kragarmlaenge
PK = 0.6 * math.pi ** 2 * EI / (4 * LK ** 2)  # Druck 0,6 N_cr (Euler-Fall 1)
HK = 2e3                                     # Kopflast quer


def _kragarm(woelb: bool, n: int = 1, teilung: bool = True):
    """Kragarm in n Elementen; teilung=False rechnet ohne interne Stabteilung
    (theorie2.solve_theorie2(stabteilung=False)). Rueckgabe (Modell,
    Ergebnis, Knoten, Elemente)."""
    from statik3d.model import Model, Material, Section
    from statik3d import solver, theorie2
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1.0, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.05))
    m.sections["Q"].Iw = 1e-7
    m.design.imperfektionen = False
    ids = [m.add_node(LK * j / n, 0, 0) for j in range(n + 1)]
    els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q") for j in range(n)]
    if woelb:
        for e in els:
            m.stab_woelb_setzen(e, True)
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fx=-PK, Fz=-HK)
    m.load_cases["LF1"].theorie = "II"
    if teilung:
        r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
    else:
        r, _info = theorie2.solve_theorie2(m, {"LF1": 1.0}, "LF1", imperfektionen=False,
                                           stabteilung=False)
    return m, r, ids, els


def _m_kragarm(x: float) -> float:
    """Geschlossene Loesung: Moment des Kragarms mit Druck P und Kopflast H,
    M(x) = H sin(k (L - x)) / (k cos k L), k = sqrt(P/EI)."""
    k = math.sqrt(PK / EI)
    return HK * math.sin(k * (LK - x)) / (k * math.cos(k * LK))


def test_woelb_stabende():
    from statik3d import solver
    soll = _m_kragarm(0.0)
    for teilung in (True, False):
        wie = "mit Vorgabe (Teilung)" if teilung else "ohne Stabteilung"
        m, r, ids, els = _kragarm(True, 1, teilung)
        check(f"Befund 32, {wie}: der Balken rechnet mit Wölbkrafttorsion",
              m.stab_woelbt(m.elements[els[0]]), "")
        b = r.beam_forces[els[0]]
        M0, RM = abs(b["My"][0]), abs(r.reactions[ids[0], 4])
        V0, RZ = abs(b["Vz"][0]), abs(r.reactions[ids[0], 2])
        check(f"… Stab My(0) = Lagermoment (vorher 23,997 gegen 22,158 kNm)",
              abs(M0 - RM) < 1e-6 * RM, f"{M0 / 1e3:.4f} / {RM / 1e3:.4f} kNm")
        check(f"… Querkraft Vz(0) = Auflagerkraft Rz = Kopflast 2,000 kN (vorher 4,544)",
              abs(V0 - RZ) < 1e-6 * RZ and abs(RZ - HK) < 1e-6 * HK, f"{V0 / 1e3:.4f} / {RZ / 1e3:.4f} kN")
        check(f"… Lagermoment auf 0,5 % an der Differentialgleichung {soll / 1e3:.4f} kNm (ein Element)",
              abs(RM / soll - 1) < 5e-3, f"{RM / 1e3:.4f} kNm")
        check("… Feldanteil N·w geführt (beam_th2 mit dem Element)", els[0] in (r.beam_th2 or {}),
              str(sorted(r.beam_th2 or {})))
        st = solver.beam_station_forces(m, r, els[0], 11)
        xm = float(st["x"][5])
        Mm, sm = abs(float(st["My"][5])), _m_kragarm(xm)
        check(f"… Feldmoment bei x = {xm:.2f} m auf 1 % an der Differentialgleichung {sm / 1e3:.4f} kNm",
              abs(Mm / sm - 1) < 1e-2, f"{Mm / 1e3:.4f} kNm")


def test_woelb_wie_ohne_woelb():
    """Zweiter Programmweg: ohne Torsion ist der Balken mit Woelbkrafttorsion
    in der Biegung derselbe Balken wie ohne - beide in einem Element, ohne
    Stabteilung, an 21 Stellen."""
    from statik3d import solver
    for n in (1, 2):
        mw, rw, _iw, ew = _kragarm(True, n, teilung=False)
        mo, ro, _io, eo = _kragarm(False, n, teilung=False)
        abw = 0.0
        for a, b in zip(ew, eo):
            sw = solver.beam_station_forces(mw, rw, a, 21)
            so = solver.beam_station_forces(mo, ro, b, 21)
            for c in ("N", "Vz", "My"):
                abw = max(abw, float(np.abs(np.asarray(sw[c]) - np.asarray(so[c])).max()))
        check(f"Befund 32, {n} Element(e), ohne Stabteilung: N, Vz, My mit Wölbkrafttorsion = ohne "
              "(21 Stellen, auf 0,01 N bzw. Nm)", abw < 1e-2, f"größte Abweichung {abw:.3e}")


# ---------------------------------------------------------------- Befund 33
HS = 5.0                                     # Stuetzenhoehe
FK = 1e6                                     # Kopflast, traegt der Haenger
QX = 1e3                                     # Querlast


def _stuetze(art: str, fz: float, teilung: bool = True, theorie: str = "II"):
    """Stuetze in 4 Elementen, unten gelenkig, oben seitlich gehalten; oben am
    letzten Element ein Laengsgelenk (art "ux_frei" oder Federgelenk
    "ux_null" mit k = 0, "ohne": keins). Die Kopflast fz traegt ein Haenger
    nach oben, quer wirkt qx. Rueckgabe (Modell, Ergebnis, alpha_cr, Elemente)."""
    from statik3d.model import Model, Material, Section
    from statik3d import solver, theorie2
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=0.01, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.05))
    m.design.imperfektionen = False
    n = 4
    ids = [m.add_node(0, 0, HS * j / n) for j in range(n + 1)]
    els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q") for j in range(n)]
    t = m.add_node(0, 0, 2 * HS)
    m.add_element("truss", [ids[-1], t], "ST", "Q")
    m.fix(t, [0, 1, 2])
    m.fix(ids[0], [0, 1, 2, 5])
    m.fix(ids[-1], [0, 1])
    if art == "ux_frei":
        m.add_hinge("GE", end=1, ux="free")
        m.apply_hinge(els[-1], "GE")
    elif art == "ux_null":
        m.add_hinge("GE", end=1, ux=0.0)
        m.apply_hinge(els[-1], "GE")
    m.load_node(ids[-1], Fz=fz)
    for e in els:
        m.load_beam(e, qx=QX)
    m.load_cases["LF1"].theorie = theorie
    if teilung:
        r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
        a = r.info.get("alpha_cr")
    else:
        r, info = theorie2.solve_theorie2(m, {"LF1": 1.0}, "LF1", imperfektionen=False,
                                          stabteilung=False)
        a = info.alpha_cr
    return m, r, a, els


def _max_my(m, r, els) -> float:
    from statik3d import solver
    return max(float(np.abs(solver.beam_station_forces(m, r, e, 21)["My"]).max()) for e in els)


def test_laengsgelenk():
    from statik3d import theorie2
    soll = QX * HS ** 2 / 8.0                 # ohne Normalkraft: Einfeldtraeger q L²/8
    m1, r1, _a1, e1 = _stuetze("ux_frei", -FK, theorie="I")
    m1max = _max_my(m1, r1, e1)
    check(f"Befund 33, zweiter Weg: Theorie I. Ordnung max |My| = q L²/8 = {soll / 1e3:.4f} kNm",
          abs(m1max / soll - 1) < 1e-6, f"{m1max / 1e3:.4f} kNm")
    for art in ("ux_frei", "ux_null"):
        for fz, wie in ((-FK, "Druck"), (FK, "Zug")):
            for teilung in (True, False):
                t_ = "mit Vorgabe" if teilung else "ohne Stabteilung"
                m, r, a, els = _stuetze(art, fz, teilung)
                N = max(abs(float(r.beam_forces[e]["N"][0])) for e in els)
                mx = _max_my(m, r, els)
                ohne = a is None or not math.isfinite(float(a))
                check(f"Befund 33, {art}, Kopflast {wie}, {t_}: Stütze trägt N = 0, Theorie II. "
                      f"max |My| = q L²/8 (vorher 4,11 bzw. 2,68 kNm)",
                      N < 1e-6 and abs(mx / soll - 1) < 1e-6, f"N {N:.3e} N, max |My| {mx / 1e3:.4f} kNm")
                check(f"… alpha_cr ohne Verzweigung (Stütze ohne Normalkraft; vorher endlich)",
                      ohne, f"alpha_cr {a}")
    # die Normalkraft fuer K_G direkt
    m, r, _a, els = _stuetze("ux_frei", -FK, teilung=False, theorie="I")
    u = np.zeros(m.ndof)
    u[:m.nn * 6] = np.asarray(r.u, float).ravel()
    ng = theorie2.normalkraefte_kg(m, u)
    check("… Normalkraft für K_G am Element mit Längsgelenk 0 (wie im Ergebnis)",
          abs(ng[els[-1]]) < 1e-9 and abs(float(r.beam_forces[els[-1]]["N"][0])) < 1e-6,
          f"K_G {ng[els[-1]]:.3e} N, Ergebnis {float(r.beam_forces[els[-1]]['N'][0]):.3e} N")


def test_ohne_laengsgelenk_unveraendert():
    """Gegenprobe: ohne Laengsgelenk traegt die Stuetze die halbe Kopflast
    (Stuetze und Haenger gleich steif), K_G nimmt sie wie bisher."""
    m, r, a, els = _stuetze("ohne", -FK, teilung=False)
    N = [float(r.beam_forces[e]["N"][0]) for e in els]
    check("Gegenprobe ohne Längsgelenk: Stütze trägt -500 kN, alpha_cr endlich",
          all(abs(x + 0.5 * FK) < 1e-3 * FK for x in N) and a is not None and math.isfinite(a) and a > 1,
          f"N {[round(x / 1e3, 3) for x in N]} kN, alpha_cr {a}")


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    a, b = rv.merkmal("theorie2_woelb"), rv.merkmal("theorie2_laengsgelenk")
    check("Verfahrenstabelle: Befund 32 und 33 als Fehlerkorrektur Stand 35",
          a is not None and b is not None and a.wechsel[-1].stand == 35 and b.wechsel[-1].stand == 35
          and a.wechsel[-1].art == rv.FEHLERKORREKTUR and b.wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.VERFAHRENSSTAND >= 35, f"Stand {rv.VERFAHRENSSTAND}")
    if a is None or b is None:
        return
    mw, _r, _i, _e = _kragarm(True, 1, teilung=False)
    mo, _r, _i, _e = _kragarm(False, 1, teilung=False)
    ml, _r, _a, _e = _stuetze("ux_frei", -FK, teilung=False, theorie="I")
    mf, _r, _a, _e = _stuetze("ux_null", -FK, teilung=False, theorie="I")
    mn, _r, _a, _e = _stuetze("ohne", -FK, teilung=False, theorie="I")
    check("… betroffen: Wölbkrafttorsion ja, derselbe Balken ohne nein; Längsgelenk (frei, k = 0) ja, "
          "ohne nein",
          a.betrifft(mw) and not a.betrifft(mo) and b.betrifft(ml) and b.betrifft(mf)
          and not b.betrifft(mn) and not b.betrifft(mw),
          f"{a.betrifft(mw)}/{a.betrifft(mo)}/{b.betrifft(ml)}/{b.betrifft(mf)}/{b.betrifft(mn)}")


def main():
    for t in (test_woelb_stabende, test_woelb_wie_ohne_woelb, test_laengsgelenk,
              test_ohne_laengsgelenk_unveraendert, test_verfahrenstabelle):
        try:
            t()
        except Exception as exc:              # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, repr(exc)[:200])
    ok = sum(1 for _n, o in RESULTS if o)
    print(f"\n{ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
