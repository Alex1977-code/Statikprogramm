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
    # Der Name dieser Pruefung sagte seit jeher "Laden verteilt neu" - die
    # Zusicherung prueft seit dem 21.09.2026, dass es auch geschieht. Vorher
    # stand hier ``len(lc.temp_loads) == 0`` und dahinter ein Verteilen von
    # Hand: Name und Inhalt widersprachen sich, und der Name hatte recht.
    check("Speichern ohne die abgeleiteten Lasten, Laden verteilt neu",
          len(lc.temp_loads) == 96 and len(lc.geometrielasten) == 1
          and all(getattr(t, "_geo", False) and t.dT == 30.0 for t in lc.temp_loads)
          and m2.lasten_verteilen() == 96 and len(m2.case().temp_loads) == 96,
          f"{len(lc.temp_loads)} Temperaturlasten nach dem Laden")
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
    # Bis zum 21.09.2026 stand hier ``len(lc.beam_loads) == 0`` - die Pruefung
    # hielt die Speicherregel fest ("abgeleitete Lasten kommen nicht in die
    # Datei") und hat damit den Fehler **festgeschrieben**: dass niemand sie
    # wieder erzeugt, hat sie nie geprueft. Geprueft gehoert das Ergebnis,
    # nicht die Regel.
    check("abgeleitete Stablasten stehen nicht in der Datei, sind nach dem "
          "Laden aber wieder da", len(lc.beam_loads) == 4
          and all(getattr(f, "_geo", False) for f in lc.beam_loads)
          and len([f for f in lc.beam_loads if not getattr(f, "_geo", False)]) == 0,
          f"{len(lc.beam_loads)} Stablasten, alle aus der Objektlast")
    check("und ein zweites Verteilen verdoppelt sie nicht",
          m2.lasten_verteilen() == 4 and len(m2.case().beam_loads) == 4,
          f"{len(m2.case().beam_loads)} Stablasten")
    check("bezug() liest sich", "Traeger" in ll.bezug() and "von 1 m bis 5 m" in ll.bezug()
          and "-10 mm" in zv.bezug(), ll.bezug() + " | " + zv.bezug())


def test_geladenes_modell_traegt_dieselbe_last():
    """Ein geladenes Modell muss dieselbe Last tragen wie das gespeicherte.

    Das ist die Pruefung, die der ganzen Kette gefehlt hat. Die verteilten
    Elementlasten stehen absichtlich nicht in der Datei; erzeugt hat sie
    beim Laden aber niemand wieder, und ``lasten_verteilen`` haengt am
    Vernetzen - ein geladenes Modell hat schon ein Netz. Der Anwender
    oeffnete seine Datei, drueckte Berechnen und rechnete ohne seine
    Bemessungslast: am Drehlager fielen 9,26 MN senkrecht und 3,97 MN
    waagerecht auf **exakt null** (Lasterrechnung der Loesersitzung,
    21.09.2026), hier 1 MN auf 0 N.

    Geprueft wird der Lastvektor selbst (``solver.case_loads``), nicht die
    Zahl der Lastobjekte - die Zahl war ja gerade das, was die alte Pruefung
    ansah, und sie stand auf null, ohne dass es auffiel.
    """
    print("--- Ein geladenes Modell traegt dieselbe Last ---")
    m = Model()
    m.add_material(Material.steel("S235"))
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]])
    m.add_nodes(P)
    z = {"i": 0}

    def linie(a, b):
        z["i"] += 1
        m.add_line(f"L{z['i']}", [int(a), int(b)])
        return f"L{z['i']}"

    R = [[linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [linie(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Dach", R[1], material="S235")
    seiten = []
    for i in range(4):
        m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235")
        seiten.append(f"M{i}")
    m.add_koerper("K", ["Boden", "Dach"] + seiten, material="S235")
    m.add_load_case("LF1", "Q", "Bemessungslast")
    m.add_geometrielast("Dach", 1.0e6, art="flaeche", case="LF1")
    for k in range(4):
        m.fix(k, "all")
    mesher.modell_vernetzen(m, log=[])

    def summe(mm):
        F = np.asarray(solver.case_loads(mm, {"LF1": 1.0}, None)[0], float)
        return F.reshape(-1, 3).sum(axis=0)

    vorher = summe(m)
    check("vernetzt traegt der Koerper seine Flaechenlast",
          np.isclose(vorher[2], -1.0e6, rtol=1e-9), f"Fz {vorher[2] / 1e3:.1f} kN")

    m2 = Model.from_dict(m.to_dict())
    nachher = summe(m2)
    check("nach Speichern und Laden traegt er dieselbe Last",
          np.isclose(nachher[2], vorher[2], rtol=1e-9),
          f"Fz {nachher[2] / 1e3:.1f} kN gegen {vorher[2] / 1e3:.1f} kN")
    check("und zwar ueber alle drei Richtungen",
          np.allclose(nachher, vorher, rtol=1e-9, atol=1e-6),
          f"{nachher[0]:.1f} / {nachher[1]:.1f} / {nachher[2]:.1f} N")

    # Zweimal laden darf sie nicht verdoppeln - lasten_verteilen raeumt die
    # abgeleiteten Lasten vorher weg, aber das gehoert festgehalten.
    m3 = Model.from_dict(m2.to_dict())
    check("zweimal geladen verdoppelt sie nicht",
          np.allclose(summe(m3), vorher, rtol=1e-9, atol=1e-6),
          f"Fz {summe(m3)[2] / 1e3:.1f} kN")

    # Ohne Netz ist nichts zu verteilen - und es darf auch nichts knallen.
    leer = Model()
    leer.add_material(Material.steel("S235"))
    leer.add_load_case("LF1", "Q")
    check("ein Modell ohne Netz laedt trotzdem",
          len(Model.from_dict(leer.to_dict()).load_cases) == 1)


def test_projiziert_bereich_verlauf_zusammen():
    """Projektion, Bereich und Verlauf an **einer** Last - und von Hand
    nachgerechnet.

    ``_geometrielast_legen.nimm`` prueft seit dem 21.09.2026 den
    Windschatten zuerst und berechnet die Seitenmitte nur, wenn Bereich oder
    Verlauf sie lesen (Theoriehandbuch 7.3: 70 s -> 12,5 s am Drehlager).
    Das ist eine Umstellung der Reihenfolge, und Reihenfolgen verrutschen.
    Diese Pruefung haelt alle drei Merkmale gleichzeitig fest - keine
    bestehende Pruefung tat das - und vergleicht gegen die Handrechnung,
    nicht gegen einen frueheren Lauf.
    """
    print("--- Projektion, Bereich und Verlauf zusammen ---")
    m = Model()
    m.add_material(Material.steel("S235"))
    P = np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0],
                  [0, 0, 1], [2, 0, 1], [2, 1, 1], [0, 1, 1.]])
    m.add_nodes(P)
    z = {"i": 0}

    def linie(a, b):
        z["i"] += 1
        m.add_line(f"L{z['i']}", [int(a), int(b)])
        return f"L{z['i']}"

    R = [[linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [linie(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Dach", R[1], material="S235")
    for i in range(4):
        m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235")
    k = m.add_koerper("K", ["Boden", "Dach"] + [f"M{i}" for i in range(4)],
                      material="S235")
    k.teilung = [4, 2, 2]
    m.add_load_case("LF1", "Q")
    # Schraeg von oben, also trifft sie Dach und eine Seitenwand verschieden
    richtung = [0.0, 0.0, -1.0]
    # Bereich: nur die vordere Haelfte in x (0 bis 1 von 2)
    bereich = {"art": "rechteck", "ursprung": [0, 0, 0], "u": [1, 0, 0],
               "v": [0, 1, 0], "von": [0.0, -1.0], "bis": [1.0, 2.0]}
    # Verlauf: linear von 1,0 MN/m2 bei x = 0 auf 2,0 MN/m2 bei x = 2
    verlauf = {"art": "linear",
               "punkte": [[0.0, 0.0, 0.0, 1.0e6], [2.0, 0.0, 0.0, 2.0e6]]}
    m.add_geometrielast("K", 1.0e6, art="koerper", case="LF1",
                        richtung=richtung, projiziert=True, bereich=bereich,
                        verlauf=verlauf)
    mesher.modell_vernetzen(m, log=[])
    lasten = m.case("LF1").face_loads
    check("es entstehen ueberhaupt Lasten", len(lasten) > 0, f"{len(lasten)} Seiten")

    d = np.asarray(richtung, float)
    d = d / np.linalg.norm(d)
    gl = m.case("LF1").geometrielasten[0]
    falsch_schatten = falsch_bereich = falsch_wert = 0
    for fl in lasten:
        n = m._seitennormale(fl.elem, fl.face)
        c = float(n @ d)
        if c >= 0:
            falsch_schatten += 1                    # im Windschatten, darf nicht da sein
        if not gl.trifft(m._seitenmitte(fl.elem, fl.face)):
            falsch_bereich += 1                     # ausserhalb des Bereichs
        mitte = m._seitenmitte(fl.elem, fl.face)
        soll = gl.wert(mitte, normale=n) * (-c)     # Verlauf mal Projektion
        if not np.isclose(fl.p, soll, rtol=1e-12):
            falsch_wert += 1
    check("keine Seite im Windschatten traegt Last", falsch_schatten == 0,
          f"{falsch_schatten} von {len(lasten)}")
    check("keine Seite ausserhalb des Bereichs traegt Last", falsch_bereich == 0,
          f"{falsch_bereich} von {len(lasten)}")
    check("der Wert ist der Verlauf an der Seitenmitte mal dem Kosinus",
          falsch_wert == 0, f"{falsch_wert} von {len(lasten)}")
    check("und er ist nicht ueberall gleich - der Verlauf wirkt",
          len({round(float(fl.p), 3) for fl in lasten}) > 1,
          f"{len({round(float(fl.p), 3) for fl in lasten})} verschiedene Werte")

    # Und die Gegenprobe: jede Seite, die beide Bedingungen erfuellt, MUSS
    # eine Last haben - sonst wirft die neue Reihenfolge welche weg.
    hat = {(int(fl.elem), int(fl.face)) for fl in lasten}
    fehlt = 0
    for fn in k.flaechen:
        f = m.flaechen[fn]
        for e, seite in list((f.randseiten or [])) + [(e, 0) for e in (f.elemente or [])]:
            n = m._seitennormale(e, seite)
            if n is None:
                continue
            if float(n @ d) < 0 and gl.trifft(m._seitenmitte(e, seite)):
                fehlt += (int(e), int(seite)) not in hat
    check("und keine belastbare Seite fehlt", fehlt == 0, f"{fehlt} fehlen")

    # Die Summe von Hand: der Bereich ist 0 <= x <= 1, das Dach ist 1 m
    # breit, und der Verlauf steigt von 1,0 auf 2,0 MN/m2 ueber x = 0 bis 2.
    # Also integral p(x) dx ueber 0..1 mal 1 m Breite = (1,0 + 1,25)/2 MN.
    # Die Teilung 4 in x gibt Seiten von 0,5 m; ihre Mitten liegen bei
    # x = 0,25 und 0,75, der Verlauf wird dort abgegriffen - das trifft das
    # Integral der Geraden exakt (Mittelpunktsregel).
    soll = -(1.125e6 + 1.375e6) / 2 * 1.0 * 1.0
    S = np.asarray(solver.case_loads(m, {"LF1": 1.0}, None)[0],
                   float).reshape(-1, 3).sum(axis=0)
    check("Summe = Integral des Verlaufs ueber die projizierte Flaeche",
          np.isclose(S[2], soll, rtol=1e-9),
          f"Fz {S[2] / 1e3:.1f} kN gegen {soll / 1e3:.1f} kN")


def test_vorspannung():
    """Vorspannung als Anfangsdehnung, geschlossen geprueft:
    * beidseitig gehaltener Stab: keine Verschiebung, die Lager tragen F_v
      (der Stab steht unter dem Zug F_v);
    * freier Stab: keine Lagerkraft, Verkuerzung F_v L / (E A);
    * Volumen (Schraubenschaft als Quader): eingespannt tragen die Lager
      F_v, frei verkuerzt er sich um F_v L / (E A) - und die Spannung im
      Element ist die Vorspannung -F_v/A (frei) bzw. null nach Abzug."""
    print("--- Vorspannung ---")
    Fv = 100e3
    m, els = balken(L=6.0, n=4)
    m.fix(0, "all")
    tip = m.nn - 1
    m.fix(tip, [0, 1, 2])
    v = m.add_vorspannung("Traeger", Fv)
    check("Vorspannung haengt am Stab im aktiven Lastfall",
          m.case().vorspannungen == [v] and v.art == "stab" and m.case().n_loads == 1)
    r = solver.solve_static(m)
    EA = 210e9 * m.sections["IPE 300"].A
    check("gehaltener Stab: keine Verschiebung", abs(r.u).max() < 1e-12, f"{abs(r.u).max():.2e}")
    check("Stabendkraefte: der Stab steht unter dem Zug F_v",
          all(np.isclose(abs(r.beam_end[e][0]), Fv, rtol=1e-9) and np.isclose(r.beam_end[e][6], -r.beam_end[e][0], rtol=1e-9)
              for e in els), f"{r.beam_end[els[0]][0] / 1e3:.3f} / {r.beam_end[els[0]][6] / 1e3:.3f} kN")
    check("die Lager tragen F_v - gegeneinander gerichtet",
          np.isclose(abs(r.reactions[0, 0]), Fv, rtol=1e-9) and np.isclose(abs(r.reactions[tip, 0]), Fv, rtol=1e-9)
          and r.reactions[0, 0] * r.reactions[tip, 0] < 0,
          f"{r.reactions[0, 0] / 1e3:.3f} / {r.reactions[tip, 0] / 1e3:.3f} kN")
    m2, _ = balken(L=6.0, n=4)
    m2.fix(0, "all")
    m2.add_vorspannung("Traeger", Fv)
    r2 = solver.solve_static(m2)
    check("freier Stab: Verkuerzung F_v L / (E A), keine Lagerkraft",
          np.isclose(r2.u[m2.nn - 1, 0], -Fv * 6.0 / EA, rtol=1e-9) and abs(r2.reactions[0, 0]) < 1e-6 * Fv,
          f"{r2.u[m2.nn - 1, 0] * 1e3:.4f} mm gegen {-Fv * 6.0 / EA * 1e3:.4f}")
    d = Model.from_dict(m2.to_dict())
    check("Vorspannung ueberlebt Speichern und Laden",
          len(d.case().vorspannungen) == 1 and d.case().vorspannungen[0].kraft == Fv)
    # Volumen: Quader 0,1 x 0,1 x 0,4 m, Achse z (laengste Abmessung)
    from statik3d.model import Volumenkoerper
    a, b, L = 0.1, 0.1, 0.4
    nx, ny, nz = 2, 2, 8
    mv = Model("Schraube")
    mv.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    ids = {}
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                ids[(i, j, k)] = mv.add_node(a * i / nx, b * j / ny, L * k / nz)
    hexe = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                hexe.append(mv.add_element("hex8", [
                    ids[(i, j, k)], ids[(i + 1, j, k)], ids[(i + 1, j + 1, k)], ids[(i, j + 1, k)],
                    ids[(i, j, k + 1)], ids[(i + 1, j, k + 1)], ids[(i + 1, j + 1, k + 1)],
                    ids[(i, j + 1, k + 1)]], "S235"))
    for e in hexe:
        mv.elements[e].group = "Schaft"
    mv.koerper["Schaft"] = Volumenkoerper("Schaft", flaechen=[], material="S235", elemente=list(hexe))
    for k in range(nz + 1):
        for j in range(ny + 1):
            mv.fix(ids[(0, j, k)], [0])
        for i in range(nx + 1):
            mv.fix(ids[(i, 0, k)], [1])
    for j in range(ny + 1):
        for i in range(nx + 1):
            mv.fix(ids[(i, j, 0)], [2])
    mv.add_vorspannung("Schaft", Fv)
    elems, achse, A_q = mv.vorspannung_koerper(mv.case().vorspannungen[0])
    check("Achse = laengste Abmessung (z), A = Volumen / Laenge",
          np.allclose(achse, [0, 0, 1]) and np.isclose(A_q, a * b, rtol=1e-9), f"{achse} A = {A_q:.5f} m²")
    rv = solver.solve_static(mv)
    oben = [ids[(i, j, nz)] for j in range(ny + 1) for i in range(nx + 1)]
    check("freier Schaft: Verkuerzung F_v L / (E A) an der Stirnflaeche",
          np.allclose(rv.u[oben, 2], -Fv * L / (210e9 * a * b), rtol=1e-6),
          f"{rv.u[oben, 2].mean() * 1e3:.4f} mm gegen {-Fv * L / (210e9 * a * b) * 1e3:.4f}")
    sp = list(rv.solid_res.values())
    check("freier Schaft: Spannung null (die Dehnung hebt die Vorspannung auf)",
          bool(sp) and max(abs(float(s[2])) for s in sp) < 1e-6 * Fv / (a * b),
          f"{max(abs(float(s[2])) for s in sp) if sp else float('nan'):.3e} Pa")
    for j in range(ny + 1):
        for i in range(nx + 1):
            mv.fix(ids[(i, j, nz)], [2])
    rv2 = solver.solve_static(mv)
    unten = [ids[(i, j, 0)] for j in range(ny + 1) for i in range(nx + 1)]
    check("eingespannter Schaft: die Stirnflaechen tragen F_v",
          np.isclose(abs(rv2.reactions[unten, 2].sum()), Fv, rtol=1e-9)
          and np.isclose(abs(rv2.reactions[oben, 2].sum()), Fv, rtol=1e-9),
          f"{rv2.reactions[unten, 2].sum() / 1e3:.3f} / {rv2.reactions[oben, 2].sum() / 1e3:.3f} kN")
    sp2 = list(rv2.solid_res.values())
    check("eingespannter Schaft: sigma_z = F_v / A (Zug) in jedem Element",
          bool(sp2) and all(np.isclose(float(s[2]), Fv / (a * b), rtol=1e-6) for s in sp2),
          f"{float(sp2[0][2]) / 1e6 if sp2 else float('nan'):.3f} MPa gegen {Fv / (a * b) / 1e6:.3f}")


def test_lasten_verschwinden_nicht_mehr_still():
    """Drei Wege, auf denen eine Last zu 100 % ausfiel, ohne dass etwas
    gemeldet wurde.

    Alle drei schreiben eine **plausible Zahl**: die Last steht weiter im
    Bericht mit ihrem vollen Betrag und wird in der Ansicht gezeichnet, nur
    wirkt sie nicht. Genau das macht sie gefährlich.

    * **Eine Seitennummer, die es nicht gibt.** `solid_face_pressure` gab
      einen Nullvektor zurück, wenn `face` außerhalb des Bereichs lag -
      erreichbar von außen über ein Abaqus-`*DLOAD P5` am Tetraeder, der nur
      vier Seiten hat. Gemessen: 1000 kN → 0 kN. Das ebene Element macht es
      drei Zeilen weiter richtig und wirft eine Ausnahme.
    * **Der Nullvektor als Richtung.** Alle drei Zweige normieren mit
      `d / (norm(d) or 1.0)`; aus dem Nullvektor wird dabei wieder der
      Nullvektor. Erreichbar über eine Nastran-`PLOAD4` mit ausgeschriebenem
      Normalenvektor `0., 0., 0.`.
    * **Ein einseitiges Lager ohne Richtung** kann nie tragen; das Ergebnis
      ist Zeichen für Zeichen das eines Systems ohne dieses Lager, während
      die Ergebniszeile „Kontakt" behauptet.

    Geprüft wird auf zwei Lagen: die Ausnahme beim Aufstellen **und** die
    Zeile in `Model.check()`, die den Fall schon vor dem Rechnen zeigt.
    """
    from statik3d import assemble
    from statik3d.model import Material, Model

    def wuerfel(typ="hex8"):
        m = Model("last")
        m.add_material(Material.steel("S235"))
        if typ == "hex8":
            for p in ([0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                      [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]):
                m.add_node(*p)
            m.add_element("hex8", list(range(8)), "S235")
        else:
            for p in ([0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1.]):
                m.add_node(*p)
            m.add_element("tet4", [0, 1, 2, 3], "S235")
        return m

    # ---- (a) Seitennummer ausserhalb des Bereichs
    m = wuerfel("tet4")
    m.load_face(0, -1000e3, face=4)          # tet4 hat die Seiten 0..3
    try:
        assemble.load_vector(m, m.case())
        check("eine Seitennummer, die es nicht gibt, bricht ab", False,
              "sie lief durch und gab 0 N")
    except ValueError as ex:
        check("eine Seitennummer, die es nicht gibt, bricht ab",
              "Seite 4" in str(ex) and "0..3" in str(ex), str(ex)[:70])
    check("und Model.check() zeigt sie schon vor dem Rechnen",
          any("Seite 4 gibt es nicht" in z for z in m.check()),
          next((z for z in m.check() if "Seite 4" in z), "keine Zeile")[:90])

    # Gegenprobe: eine gueltige Seite traegt unveraendert
    m2 = wuerfel("tet4")
    m2.load_face(0, -1000e3, face=3)
    F = assemble.load_vector(m2, m2.case())
    summe = float(np.abs(np.asarray(F, float)).sum())
    check("eine gültige Seitennummer trägt unverändert", summe > 1.0,
          f"Summe |F| = {summe:.4g} N")
    check("und check() beanstandet sie nicht",
          not any("Seite" in z for z in m2.check()), str(m2.check())[:70])

    # ---- (b) Nullvektor als Richtung
    m3 = wuerfel("hex8")
    m3.load_face(0, -1000e3, face=1, direction=[0.0, 0.0, 0.0])
    try:
        assemble.load_vector(m3, m3.case())
        check("der Nullvektor als Richtung bricht ab", False,
              "er lief durch und gab 0 N")
    except ValueError as ex:
        check("der Nullvektor als Richtung bricht ab",
              "Nullvektor" in str(ex), str(ex)[:70])
    check("und check() zeigt ihn vor dem Rechnen",
          any("Nullvektor" in z and "0 N" in z for z in m3.check()),
          next((z for z in m3.check() if "Nullvektor" in z), "keine Zeile")[:90])

    m4 = wuerfel("hex8")
    m4.load_face(0, -1000e3, face=1, direction=[0.0, 0.0, -1.0])
    F4 = np.asarray(assemble.load_vector(m4, m4.case()), float)
    check("eine echte Richtung trägt unverändert", float(np.abs(F4).sum()) > 1.0,
          f"Summe |F| = {float(np.abs(F4).sum()):.4g} N")

    # ---- (c) einseitiges Lager ohne Richtung
    m5 = wuerfel("hex8")
    m5.add_contact_support(0, direction=(0.0, 0.0, 0.0))
    check("ein einseitiges Lager ohne Richtung wird benannt",
          any("Einseitiges Lager" in z and "Nullvektor" in z for z in m5.check()),
          next((z for z in m5.check() if "Einseitiges Lager" in z),
               "keine Zeile")[:90])
    m6 = wuerfel("hex8")
    m6.add_contact_support(0, direction=(0.0, 0.0, 1.0))
    check("ein Lager mit Richtung wird nicht beanstandet",
          not any("Einseitiges Lager" in z for z in m6.check()),
          str([z for z in m6.check() if "Lager" in z])[:70])


def test_objektlast_nennt_den_nullvektor_als_grund():
    """Eine Objektlast ohne Richtung hieß „liegt ganz im Windschatten".

    `_warum_leer` gibt den Grund an, warum eine Geometrielast keine
    Elementlast erzeugt hat. Steht dort der Nullvektor als Richtung, ist
    **das** der Grund - „Windschatten" schickt den Anwender auf die falsche
    Fährte, denn er sucht dann nach einer verdeckten Fläche.

    Die Reihenfolge der Prüfungen ist dabei wesentlich und darum mitgeprüft:
    ein noch nicht vernetztes Ziel muss weiterhin „Ziel noch nicht vernetzt"
    melden und nicht den Nullvektor - sonst verdeckt die neue Zeile die
    ältere und wichtigere.
    """
    from statik3d import mesher
    from statik3d.model import Geometrielast, Material, Model, Volumenkoerper

    m = Model("objekt")
    m.add_material(Material.steel("S235"))
    mesher.grid_box(m, "S235", 1.0, 1.0, 1.0, 1, 1, 1, typ="hex8")
    # add_koerper verlangt vier Randflaechen; hier zaehlt nur die
    # Elementliste, darum unmittelbar angelegt.
    k = Volumenkoerper("K1", [])
    m.koerper["K1"] = k
    k.elemente = list(range(len(m.elements)))
    gl = Geometrielast("K1", "volumen", 1000.0, [0.0, 0.0, 0.0], projiziert=True)
    grund = m._warum_leer(gl)
    check("der Nullvektor wird als Grund genannt",
          "Nullvektor" in (grund or ""), str(grund))
    check("die Probe ist scharf: vorher hiess es Windschatten",
          "Windschatten" not in (grund or ""), str(grund))

    # Gegenprobe (1): ein unvernetztes Ziel meldet weiter das Netz
    k.elemente = []
    grund2 = m._warum_leer(gl)
    check("ein unvernetztes Ziel meldet weiter das Netz, nicht den Vektor",
          "vernetzt" in (grund2 or ""), str(grund2))

    # Gegenprobe (2): mit echter Richtung bleibt es der Windschatten
    k.elemente = list(range(len(m.elements)))
    gl2 = Geometrielast("K1", "volumen", 1000.0, [0.0, 0.0, -1.0], projiziert=True)
    grund3 = m._warum_leer(gl2)
    check("mit echter Richtung bleibt der Windschatten der Grund",
          "Windschatten" in (grund3 or ""), str(grund3))


def main():
    for t in (test_lasten_verschwinden_nicht_mehr_still,
              test_objektlast_nennt_den_nullvektor_als_grund,
              test_volleinspannkraefte, test_teillast_einfeldtraeger, test_zwangsverformung,
              test_flaechenlast_linear, test_linienlast_auf_linie, test_temperatur_objektlast,
              test_speichern_linienlast_zwang, test_geladenes_modell_traegt_dieselbe_last,
              test_projiziert_bereich_verlauf_zusammen, test_vorspannung):
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
