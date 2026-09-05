"""
Lastarten gegen geschlossene Loesungen: abschnittsweise Streckenlast
(Volleinspannkraefte, Auflagerkraefte, Schnittgroessen), Zwangsverformung
am Kragarm, linear veraenderliche Flaechenlast, Linienlast auf einer Linie,
Temperatur als Objektlast, Speichern und Laden.

    python -m tests.test_lasten
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from statik3d.model import Model, Material, Section, ShellProp, Flaeche, Line
from statik3d import mesher, solver, assemble as asm

RESULTS = []


def check(name, ok, info=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:<62s} {info}")


def balken(L=6.0, n=4):
    m = Model("Balken")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    m.add_section(Section.i_profile("IPE 300", 0.300, 0.150, 0.0071, 0.0107))
    n0 = len(m.elements)
    mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (L, 0, 0), n)
    els = list(range(n0, len(m.elements)))
    m.add_member("Traeger", els)
    return m, els


def test_volleinspannkraefte():
    print("--- Abschnittslast: Volleinspannkraefte ---")
    L = 4.0
    q1 = np.array([1.0, 2.0, 3.0])
    q2 = np.array([-1.0, 5.0, 0.5])
    voll = asm.trapezoid_fixed_end_forces(q1, q2, L)
    teil = asm.partial_trapezoid_fixed_end_forces(q1, q2, 0.0, L, L)
    check("Abschnitt [0, L] = Trapezformel", np.allclose(voll, teil, atol=1e-12),
          f"max. Abweichung {np.abs(voll - teil).max():.1e}")
    # Einzellast P = 1 an der Stelle c als Grenzfall eines kurzen Abschnitts
    c, e = 1.5, 1e-4
    q = np.array([0.0, 1.0, 0.0]) / (2 * e)
    f = asm.partial_trapezoid_fixed_end_forces(q, q, c - e, c + e, L)
    a, b = c, L - c
    soll = [b ** 2 * (3 * a + b) / L ** 3, a ** 2 * (a + 3 * b) / L ** 3,
            a * b ** 2 / L ** 2, -a ** 2 * b / L ** 2]
    ist = [f[1], f[7], f[5], f[11]]
    check("Grenzfall Einzellast: Volleinspannwerte P a b^2/L^2 usw.",
          np.allclose(ist, soll, rtol=1e-6), f"{np.round(ist, 6)} gegen {np.round(soll, 6)}")
    q = np.array([0.0, 3.0, 2.0])
    f = asm.partial_trapezoid_fixed_end_forces(q, q, 1.0, 3.0, L)
    check("Gleichgewicht der Kraefte", np.isclose(f[1] + f[7], 6.0) and np.isclose(f[2] + f[8], 4.0))
    check("Gleichgewicht der Momente um den Anfang",
          np.isclose(f[5] + f[11] + f[7] * L, 6.0 * 2.0)
          and np.isclose(-(f[4] + f[10]) + f[8] * L, 4.0 * 2.0))
    check("leerer Abschnitt gibt nichts",
          not np.any(asm.partial_trapezoid_fixed_end_forces(q, q, 3.0, 3.0, L)))


def test_teillast_einfeldtraeger():
    print("--- Linienlast auf dem Stab, abschnittsweise ---")
    m, els = balken()
    m.fix(0, [0, 1, 2, 3])
    m.fix(m.nn - 1, [1, 2])
    q = 10e3
    ll = m.add_linienlast("Traeger", [0, 0, -q], art="stab", von=2.0, bis=4.0)
    n_el = m.lasten_verteilen()
    bl = m.case().beam_loads
    check("Abschnitte auf zwei Elementen (1.5 m Elemente)", n_el == 2
          and all(getattr(b, "_geo", False) for b in bl),
          str([(b.elem, round(b.a, 3), b.b) for b in bl]))
    check("Objektlast weiss es", "2 Elementlasten" in ll.kommentar, ll.kommentar)
    check("n_loads zaehlt die Objektlast, nicht die Ableitungen", m.case().n_loads == 1,
          str(m.case().n_loads))
    r = solver.solve_static(m)
    L, a, b = 6.0, 2.0, 4.0
    RA = q * (b - a) * (L - (a + b) / 2) / L
    check("Auflagerkraft A = q (b-a) (L - (a+b)/2) / L", np.isclose(r.reactions[0, 2], RA, rtol=1e-9),
          f"{r.reactions[0, 2] / 1e3:.4f} kN gegen {RA / 1e3:.4f}")
    mf = solver.member_forces(m, r, m.members["Traeger"], n=25)
    x = np.asarray(mf["x"])
    My = np.asarray(mf["My"])
    Vz = np.asarray(mf["Vz"])
    k = int(np.argmin(np.abs(x - 3.0)))
    M3 = RA * 3 - q * 0.5
    check("Moment in Feldmitte M = R_A 3 - q 1^2/2", np.isclose(abs(My[k]), M3, rtol=1e-9),
          f"{abs(My[k]) / 1e3:.4f} kNm gegen {M3 / 1e3:.4f}")
    k1 = int(np.argmin(np.abs(x - 1.0)))
    k5 = int(np.argmin(np.abs(x - 5.0)))
    check("Querkraft vor und hinter der Last", np.isclose(abs(Vz[k1]), RA, rtol=1e-9)
          and np.isclose(abs(Vz[k5]), abs(RA - 2 * q), rtol=1e-9),
          f"{Vz[k1] / 1e3:.3f} / {Vz[k5] / 1e3:.3f} kN")
    # Feineres Netz aendert an der Verformung praktisch nichts (aequivalente
    # Knotenlasten des Abschnitts sind verteilungstreu)
    m2, _ = balken(n=60)
    m2.fix(0, [0, 1, 2, 3])
    m2.fix(m2.nn - 1, [1, 2])
    m2.add_linienlast("Traeger", [0, 0, -q], art="stab", von=2.0, bis=4.0)
    m2.lasten_verteilen()
    r2 = solver.solve_static(m2)
    w1, w2 = r.u[:, 2].min(), r2.u[:, 2].min()
    check("Durchbiegung grob gegen fein (4 gegen 60 Elemente)", abs(w1 - w2) < 2e-3 * abs(w2),
          f"{w1 * 1e3:.4f} / {w2 * 1e3:.4f} mm")
    # trapezfoermig ueber die ganze Laenge: Resultierende und Lage
    m3, _ = balken(n=3)
    m3.fix(0, [0, 1, 2, 3])
    m3.fix(m3.nn - 1, [1, 2])
    m3.add_linienlast("Traeger", [0, 0, 0.0], art="stab", q2=[0, 0, -q])
    m3.lasten_verteilen()
    r3 = solver.solve_static(m3)
    R = q * 6.0 / 2
    check("Trapezlast 0 -> q: Auflager A = R/3, B = 2R/3",
          np.isclose(r3.reactions[0, 2], R / 3, rtol=1e-9)
          and np.isclose(r3.reactions[m3.nn - 1, 2], 2 * R / 3, rtol=1e-9),
          f"{r3.reactions[0, 2] / 1e3:.3f} / {r3.reactions[m3.nn - 1, 2] / 1e3:.3f} kN")
    # Neu verteilen verdoppelt nichts
    n_vorher = len(m3.case().beam_loads)
    m3.lasten_verteilen()
    check("erneutes Verteilen verdoppelt die Last nicht",
          len(m3.case().beam_loads) == n_vorher)


def test_zwangsverformung():
    print("--- Zwangsverformung am Kragarm ---")
    m, els = balken(L=3.0, n=3)
    m.fix(0, "all")
    tip = m.nn - 1
    m.fix(tip, [2])
    delta = 0.005
    m.add_zwangsverformung(tip, [2], [-delta])
    check("keine Vorgabe ohne Lager", not m.zwang_ohne_lager())
    r = solver.solve_static(m)
    sec = m.sections["IPE 300"]
    E, G = 210e9, 210e9 / (2 * 1.3)
    I, L = sec.Iy, 3.0
    As = getattr(sec, "Asz", 0.0) or 0.0
    # Kragarm mit Schubverformung (Timoshenko): delta = R (L^3/3EI + L/(G As))
    R_soll = delta / (L ** 3 / (3 * E * I) + (L / (G * As) if As else 0.0))
    check("Spitze steht auf dem vorgegebenen Wert", np.isclose(r.u[tip, 2], -delta, rtol=1e-12),
          f"{r.u[tip, 2] * 1e3:.4f} mm")
    check("Lagerkraft an der Spitze = delta / (L^3/3EI + L/GA_s)",
          np.isclose(abs(r.reactions[tip, 2]), R_soll, rtol=2e-3),
          f"{abs(r.reactions[tip, 2]) / 1e3:.4f} kN gegen {R_soll / 1e3:.4f}")
    check("Einspannmoment = R L", np.isclose(abs(r.reactions[0, 4]), R_soll * L, rtol=2e-3),
          f"{abs(r.reactions[0, 4]) / 1e3:.4f} kNm")
    # Zwang ohne Lager wird gemeldet und bleibt unwirksam
    m2, _ = balken(L=3.0, n=3)
    m2.fix(0, "all")
    m2.add_zwangsverformung(m2.nn - 1, [2], [-delta])
    check("Zwang ohne Lager wird erkannt", m2.zwang_ohne_lager() == [(m2.nn - 1, 2)])
    meldungen = []
    r2 = solver.solve_static(m2, progress=meldungen.append)
    check("und gemeldet, das System bleibt unbelastet",
          any("ohne Lager" in t for t in meldungen) and abs(r2.u).max() < 1e-15)
    # Kombination: Faktor 2 verdoppelt den Zwang
    m.add_load_case("LF2", "Q")
    m.add_zwangsverformung(tip, [2], [-delta], case="LF2")
    m.add_combination("K", {m.case().name: 1.0, "LF2": 1.0}) if hasattr(m, "add_combination") else None
    rs = solver.solve_cases(m)
    check("zweiter Lastfall mit Zwang loest sich gleich",
          np.isclose(rs["LF2"].u[tip, 2], -delta, rtol=1e-12))


def platte():
    m = Model("Platte")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    m.add_shell_prop(ShellProp("t12", 0.012))
    mesher.grid_plate(m, "S235", "t12", 3.0, 2.0, 12, 8, quad=True)
    for n in mesher.select_nodes(m, xmin=-1e-6, xmax=1e-6):
        m.fix(int(n), "all")
    for n in mesher.select_nodes(m, xmin=3 - 1e-6):
        m.fix(int(n), [2])
    m.flaechen["F1"] = Flaeche("F1", linien=[], elemente=list(range(len(m.elements))))
    return m


def test_flaechenlast_linear():
    print("--- Flaechenlast linear veraenderlich ---")
    m = platte()
    p1 = 5e3
    gl = m.add_geometrielast("F1", 0.0, verlauf={"art": "linear",
                                                 "punkte": [[0, 0, 0, 0.0], [3, 0, 0, p1]]})
    check("Wert an den Stuetzpunkten und dazwischen",
          np.isclose(gl.wert([0, 1, 0]), 0.0) and np.isclose(gl.wert([3, 0.5, 0]), p1)
          and np.isclose(gl.wert([1.5, 2, 0]), p1 / 2))
    n_el = m.lasten_verteilen()
    fl = m.case().face_loads
    check("Elementlasten mit dem Wert am Elementschwerpunkt", n_el == 96
          and np.isclose(min(f.p for f in fl), p1 / 24) and np.isclose(max(f.p for f in fl), p1 * 23 / 24),
          f"{min(f.p for f in fl):.1f} .. {max(f.p for f in fl):.1f}")
    r = solver.solve_static(m)
    check("Summe der Auflagerkraefte = Integral p dA = p1/2 * A",
          np.isclose(abs(r.reactions[:, 2].sum()), 3 * p1, rtol=1e-9),
          f"{abs(r.reactions[:, 2].sum()) / 1e3:.4f} kN")
    # drei Punkte: Ebene
    gl3 = m.add_geometrielast("F1", 0.0, verlauf={"art": "linear", "punkte":
                                                  [[0, 0, 0, 1.0], [1, 0, 0, 2.0], [0, 1, 0, 3.0]]})
    check("drei Punkte spannen die Ebene p = 1 + x + 2y auf",
          np.isclose(gl3.wert([2, 1, 5]), 5.0) and np.isclose(gl3.wert([0.5, 0.5, -3]), 2.5))
    check("gleichmaessig ohne Verlauf",
          np.isclose(m.add_geometrielast("F1", 7.0).wert([9, 9, 9]), 7.0))


def test_linienlast_auf_linie():
    print("--- Linienlast auf einer Linie ---")
    m = platte()
    ecke0 = int(mesher.select_nodes(m, xmin=-1e-6, xmax=1e-6, ymin=-1e-6, ymax=1e-6)[0])
    ecke1 = int(mesher.select_nodes(m, xmin=3 - 1e-6, ymin=-1e-6, ymax=1e-6)[0])
    m.lines["L1"] = Line("L1", [ecke0, ecke1])
    kn = m.knoten_auf_linie("L1")
    check("Netzknoten auf der Linie gefunden und sortiert", len(kn) == 13
          and all(kn[i][1] < kn[i + 1][1] for i in range(len(kn) - 1)), str(len(kn)))
    qz = 4e3
    m.add_linienlast("L1", [0, 0, -qz], art="linie", von=0.5, bis=2.5)
    n_el = m.lasten_verteilen()
    nl = m.case().nodal_loads
    summe = sum(l.F[2] for l in nl)
    xs = sum(l.F[2] * m.nodes[l.node][0] for l in nl) / summe
    check("Knotenlasten: Resultierende q (b-a)", n_el == 9 and np.isclose(summe, -qz * 2.0),
          f"{summe / 1e3:.3f} kN aus {n_el} Knotenlasten")
    check("und ihr Schwerpunkt in der Abschnittsmitte", np.isclose(xs, 1.5), f"x_s = {xs:.4f}")
    # trapezfoermig 0 -> q ueber die ganze Linie: Schwerpunkt bei 2/3
    m.case().linienlasten.clear()
    m.add_linienlast("L1", [0, 0, 0.0], art="linie", q2=[0, 0, -qz])
    m.lasten_verteilen()
    nl = m.case().nodal_loads
    summe = sum(l.F[2] for l in nl)
    xs = sum(l.F[2] * m.nodes[l.node][0] for l in nl) / summe
    check("Trapez 0 -> q: Resultierende q L/2 mit Schwerpunkt bei 2L/3",
          np.isclose(summe, -qz * 1.5) and np.isclose(xs, 2.0), f"{summe / 1e3:.3f} kN, x_s = {xs:.4f}")


def test_temperatur_objektlast():
    print("--- Temperatur als Objektlast ---")
    m = platte()
    gl = m.add_geometrielast("F1", lastart="temperatur", dT=30.0)
    n_el = m.lasten_verteilen()
    check("Temperaturlast auf allen Elementen der Flaeche", n_el == 96
          and all(getattr(t, "_geo", False) and t.dT == 30.0 for t in m.case().temp_loads))
    check("Objektlast zaehlt einmal", m.case().n_loads == 1 and "96" in gl.kommentar)
    d = m.to_dict()
    m2 = Model.from_dict(d)
    lc = m2.case()
    check("Speichern ohne die abgeleiteten Lasten, Laden verteilt neu",
          len(lc.temp_loads) == 0 and len(lc.geometrielasten) == 1 and m2.lasten_verteilen() == 96)
    # freie Dehnung eines Stabes bleibt wie gehabt: alpha dT L
    mb, els = balken(L=2.0, n=2)
    mb.fix(0, "all")
    for e in els:
        mb.load_temp(e, 50.0)
    r = solver.solve_static(mb)
    alpha = mb.materials["S235"].alpha
    check("freier Stab dehnt sich alpha dT L", np.isclose(r.u[mb.nn - 1, 0], alpha * 50.0 * 2.0, rtol=1e-9),
          f"{r.u[mb.nn - 1, 0] * 1e3:.4f} mm")


def test_speichern_linienlast_zwang():
    print("--- Speichern und Laden ---")
    m, els = balken()
    m.fix(0, "all")
    m.add_linienlast("Traeger", [0, 0, -1e3], art="stab", q2=[0, 0, -2e3], von=1.0, bis=5.0,
                     system="local")
    m.add_zwangsverformung(0, [2, 4], [0, 0, -0.01, 0, 0.002, 0])
    m.lasten_verteilen()
    m2 = Model.from_dict(m.to_dict())
    lc = m2.case()
    ll = lc.linienlasten[0]
    zv = lc.zwangsverformungen[0]
    check("Linienlast vollstaendig", ll.ziel == "Traeger" and ll.von == 1.0 and ll.bis == 5.0
          and ll.system == "local" and ll.q2 == [0, 0, -2e3])
    check("Zwangsverformung vollstaendig", zv.node == 0 and zv.dofs == [2, 4]
          and zv.u[2] == -0.01 and zv.u[4] == 0.002)
    check("abgeleitete Stablasten nicht gespeichert", len(lc.beam_loads) == 0
          and m2.lasten_verteilen() == 4)
    check("bezug() liest sich", "Traeger" in ll.bezug() and "von 1 m bis 5 m" in ll.bezug()
          and "-10 mm" in zv.bezug(), ll.bezug() + " | " + zv.bezug())


def main():
    for t in (test_volleinspannkraefte, test_teillast_einfeldtraeger, test_zwangsverformung,
              test_flaechenlast_linear, test_linienlast_auf_linie, test_temperatur_objektlast,
              test_speichern_linienlast_zwang):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} laeuft durch", False, str(ex)[:80])
    nok = sum(1 for r in RESULTS if r[1])
    print("=" * 60)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
