"""
Verifikation der Nachweise nach EC3 gegen Handrechnung.
Aufruf:  python -m tests.test_ec3
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material, Section
from statik3d.profiles import make_section
from statik3d import solver, mesher
from statik3d.ec3 import classify, section_check, flexural_buckling, Mcr, lateral_torsional
from statik3d.ec3.stability import C1_factor, Cm_factor, member_stability
from statik3d.ec3.fatigue import sn_life, damage
from statik3d.ec3.design import check_members
from statik3d.combinations import generate_combinations

RESULTS = []


def check(name, num, ana, tol):
    err = abs(num - ana) / abs(ana) if ana else abs(num)
    ok = err <= tol
    RESULTS.append((name, num, ana, err, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:52s} num={num: .5e} ana={ana: .5e} Abw={err*100:6.2f}%")
    return ok


def test_classification():
    ipe = make_section("IPE 300")
    heb = make_section("HEB 200")
    check("Klasse IPE 300 S355 Biegung = 1", classify(ipe, 355e6, 0, 1e5).cls, 1, 0)
    check("Klasse IPE 300 S355 Druck = 4", classify(ipe, 355e6, -1e5).cls, 4, 0)
    check("Klasse IPE 300 S235 Druck = 2", classify(ipe, 235e6, -1e5).cls, 2, 0)
    check("Klasse HEB 200 S235 Druck = 1", classify(heb, 235e6, -1e5).cls, 1, 0)
    chs = make_section("CHS 508x10")     # d/t = 50.8 > 50 eps^2 (S235) -> Klasse 2
    check("Klasse CHS 508x10 S235 = 2", classify(chs, 235e6, -1e5).cls, 2, 0)
    shs = make_section("SHS 200x6")      # c/t = (200-12-12)/6 = 29.3 -> Klasse 1 (<= 33)
    check("Klasse SHS 200x6 S235 Druck = 1", classify(shs, 235e6, -1e5).cls, 1, 0)
    # Klasse 4: wirksame Flaeche kleiner als Bruttoflaeche
    c4 = classify(ipe, 355e6, -1e5)
    check("Klasse 4: A_eff < A", float(c4.A_eff < ipe.A), 1.0, 0)
    check("Klasse 4: A_eff > 0.8 A", float(c4.A_eff > 0.8 * ipe.A), 1.0, 0)


def test_section_resistance():
    ipe = make_section("IPE 300")
    fy = 235e6
    r = section_check(ipe, fy, 0, 0, 30e3, 0, 100e3, 0, 1.0)
    check("IPE 300: M_c,Rd = Wpl fy", r["res"]["M_y_Rd"], ipe.Wpl_y * fy, 1e-9)
    check("IPE 300: Ausnutzung M = 100/147.7", r["util"], 100e3 / (ipe.Wpl_y * fy), 1e-9)
    check("IPE 300: V_pl,Rd = Av fy/sqrt3", r["res"]["V_z_Rd"], ipe.Asz * fy / np.sqrt(3), 1e-9)
    # M+N Klasse 1: n = 0.4, a = 0.42 -> M_N = Mpl (1-n)/(1-0.5a)
    Npl = ipe.A * fy
    r = section_check(ipe, fy, -0.4 * Npl, 0, 0, 0, 50e3, 0, 1.0)
    a = min((ipe.A - 2 * ipe.b * ipe.tf) / ipe.A, 0.5)
    MN = ipe.Wpl_y * fy * 0.6 / (1 - 0.5 * a)
    u = r["checks"]["M_y+N (6.2.9.1)"][0]
    check("IPE 300: M+N Interaktion (6.36)", u, 50e3 / MN, 1e-9)
    # Querkraft > 50 % -> Abminderung
    Vpl = ipe.Asz * fy / np.sqrt(3)
    r = section_check(ipe, fy, 0, 0, 0.8 * Vpl, 0, 50e3, 0, 1.0)
    rho = (2 * 0.8 - 1) ** 2
    Aw = (ipe.h - 2 * ipe.tf) * ipe.tw
    MyV = (ipe.Wpl_y - rho * Aw ** 2 / (4 * ipe.tw)) * fy
    check("IPE 300: M_V,Rd (6.30)", r["M_y_Rd"], MyV, 1e-9)


def test_torsion_schoepft_schub_aus():
    """Grosse Torsion: V_pl,Rd wird zu null - die Ausnutzung muss endlich bleiben."""
    ipe = make_section("IPE 300")
    fy = 235e6
    fvd = fy / np.sqrt(3)
    r = section_check(ipe, fy, 0, 0, 200e3, 0, 50e3, 0, 1.0)
    check("ohne Torsion: gewohnter Querkraftnachweis",
          r["checks"]["V_z (6.2.6)"][0], 200e3 / (ipe.Asz * fy / np.sqrt(3)), 1e-9)
    # Torsionsmoment so gross, dass tau_t > 1,25 f_vd wird: die Abminderung red_T
    # aus 6.2.7 wird null und V_pl,Rd damit ebenfalls null
    Mt = 6.0 * fvd * ipe.It / max(ipe.tf, ipe.tw)
    r = section_check(ipe, fy, 0, 0, 200e3, Mt, 50e3, 0, 1.0)
    check("Torsionsnachweis schlaegt an", float(r["checks"]["tau_t (6.2.7)"][0] > 1.0), 1.0, 0)
    check("kein Querkraftnachweis durch null", float("V_z (6.2.6)" not in r["checks"]), 1.0, 0)
    u = r["checks"]["V_z + tau_t (6.2.6/6.2.7)"][0]
    check("Ersatznachweis ueber die Schubspannungen",
          float(np.isfinite(u) and u > 1.0), 1.0, 0)
    check("Gesamtausnutzung bleibt endlich",
          float(np.isfinite(r["util"]) and r["util"] > 1.0), 1.0, 0)


def test_flexural_buckling():
    heb = make_section("HEB 200")
    fy = 235e6
    cls = classify(heb, fy, -1e5)
    fb = flexural_buckling(heb, 210e9, 210e9 / 2.6, fy, cls, 4.0, 4.0, 1.1)
    Ncr = np.pi ** 2 * 210e9 * heb.Iz / 16.0
    check("HEB 200: N_cr,z", fb["N_cr_z"], Ncr, 1e-9)
    lam = np.sqrt(heb.A * fy / Ncr)
    phi = 0.5 * (1 + 0.49 * (lam - 0.2) + lam ** 2)
    chi = 1 / (phi + np.sqrt(phi ** 2 - lam ** 2))
    check("HEB 200: Knicklinie z = c", float(fb["curve_z"] == "c"), 1.0, 0)
    check("HEB 200: chi_z", fb["chi_z"], chi, 1e-9)
    check("HEB 200: chi_z ~ 0.636 (Handrechnung)", fb["chi_z"], 0.636, 5e-3)
    check("HEB 200: N_b,z,Rd", fb["N_b_z_Rd"], chi * heb.A * fy / 1.1, 1e-9)


def test_ltb():
    ipe = make_section("IPE 300")
    E, G = 210e9, 210e9 / 2.6
    L = 6.0
    M = Mcr(ipe, E, G, L, 1, 1, 1.132, 0, 0)
    # Handrechnung mit Katalogwerten: Mcr ~ 102 kNm
    check("IPE 300 L=6m: M_cr (C1=1.132)", M, 102.3e3, 0.02)
    fy = 235e6
    cls = classify(ipe, fy, 0, 1e5)
    lt = lateral_torsional(ipe, fy, cls, M, "general", 1.1, 1.132)
    lam = np.sqrt(ipe.Wpl_y * fy / M)
    phi = 0.5 * (1 + 0.21 * (lam - 0.2) + lam ** 2)
    chi = 1 / (phi + np.sqrt(phi ** 2 - lam ** 2))
    check("IPE 300: lambda_LT", lt["lam_LT"], lam, 1e-9)
    check("IPE 300: chi_LT allgemein (Linie a)", lt["chi_LT"], chi, 1e-9)
    lt2 = lateral_torsional(ipe, fy, cls, M, "rolled", 1.1, 1.132)
    phi = 0.5 * (1 + 0.34 * (lam - 0.4) + 0.75 * lam ** 2)
    chi2 = min(1 / (phi + np.sqrt(phi ** 2 - 0.75 * lam ** 2)), 1.0, 1 / lam ** 2)
    kc = 1 / np.sqrt(1.132)
    f = 1 - 0.5 * (1 - kc) * (1 - 2 * (lam - 0.8) ** 2)
    check("IPE 300: chi_LT gewalzt (Linie b, f-Korrektur)", lt2["chi_LT"], min(chi2 / f, 1.0), 1e-9)
    # C1 / Cm aus Momentenverlauf
    x = np.linspace(0, 1, 21)
    check("C1 Gleichmoment = 1", C1_factor(np.ones(21))[0], 1.0, 1e-9)
    check("C1 Parabel (Gleichlast) ~ 1.13", C1_factor(4 * x * (1 - x))[0], 1.136, 1e-2)
    check("C1 linear psi=-1 = 2.6", C1_factor(np.linspace(1, -1, 21))[0], 2.6, 1e-9)
    check("Cm linear psi=0 = 0.6", Cm_factor(np.linspace(1, 0, 21))[0], 0.6, 1e-9)
    check("Cm Gleichlast Einfeld = 0.95", Cm_factor(4 * x * (1 - x))[0], 0.95, 1e-9)


def test_interaction():
    """Druck + Biegung: IPE 300, N = 300 kN, My = 60 kNm, L = 4 m gelenkig, Gleichmoment."""
    ipe = make_section("IPE 300")
    fy = 235e6
    N, My = 300e3, 60e3
    cls = classify(ipe, fy, -N, My)
    st = member_stability(ipe, 210e9, 210e9 / 2.6, fy, cls, N, My, 0.0, np.full(9, My),
                          np.zeros(9), 4.0, 4.0, 4.0, gamma_M1=1.1)
    d = st["details"]
    n_y = N / (d["chi_y"] * ipe.A * fy / 1.1)
    kyy = min(1.0 * (1 + (d["lam_y"] - 0.2) * n_y), 1.0 * (1 + 0.8 * n_y))
    u61 = n_y + kyy * My / (d["chi_LT"] * ipe.Wpl_y * fy / 1.1)
    check("Interaktion 6.61 Handrechnung", st["checks"]["Interaktion Gl. 6.61"][0], u61, 1e-9)
    check("Interaktion kyy", d["kyy"], kyy, 1e-9)
    check("Interaktion Cmy = 1 (Gleichmoment)", d["Cmy"], 1.0, 1e-9)


def test_fatigue():
    check("Woehler: N_R(100 MPa, KF 71)", sn_life(100e6, 71e6), 2e6 * (71 / 100) ** 3, 1e-9)
    dD = (2 / 5) ** (1 / 3) * 71e6
    check("Woehler: Delta_sigma_D = 0.737 KF", dD, 0.7368 * 71e6, 1e-3)
    check("Woehler: m=5 unterhalb D", sn_life(40e6, 71e6), 5e6 * (dD / 40e6) ** 5, 1e-9)
    check("Woehler: unendlich unter L", float(np.isinf(sn_life(20e6, 71e6))), 1.0, 0)
    D = damage([(100e6, 1e6), (50e6, 5e6)], 71e6, 1.15)
    ana = 1e6 / sn_life(100e6, 71e6, 1.15) + 5e6 / sn_life(50e6, 71e6, 1.15)
    check("Miner: D", D, ana, 1e-12)
    check("Woehler Schub: N_R", sn_life(60e6, 100e6, shear=True), 2e6 * (100 / 60) ** 5, 1e-9)


def test_zaehlverfahren():
    """Rainflow und Reservoir nach EN 1993-1-9, Anhang A."""
    from statik3d.ec3.fatigue import (umkehrpunkte, rainflow, reservoir, kollektiv,
                                      schaedigungstabelle, lebensdauer)
    # Zwischenwerte auf dem Weg nach oben sind keine Umkehr
    check("Umkehrpunkte: Zwischenwerte fallen weg",
          float(umkehrpunkte([0, 40, 100, 20, 60]) == [0.0, 100.0, 20.0, 60.0]), 1.0, 0)
    # Lehrbuchbeispiel ASTM E1049-85, Bild 6: 3:0.5, 4:1.5, 6:0.5, 8:1.0, 9:0.5
    k = dict(kollektiv(rainflow([-2, 1, -3, 5, -1, 3, -4, 4, -2])))
    soll = {9.0: 0.5, 8.0: 1.0, 6.0: 0.5, 4.0: 1.5, 3.0: 0.5}
    check("Rainflow trifft das Lehrbuchbeispiel", float(k == soll), 1.0, 0)
    check("Rainflow: Summe der Spiele = (Umkehrungen - 1)/2",
          sum(k.values()), (9 - 1) / 2, 1e-12)
    # Beginnt und endet der Verlauf am groessten Wert, sind beide Verfahren gleich
    zu = [5, -1, 3, -4, 4, -2, 1, -3, 5]
    a = kollektiv(rainflow(zu))
    b = kollektiv(reservoir(zu))
    check("Reservoir = Rainflow beim geschlossenen Verlauf", float(a == b), 1.0, 0)
    check("und nur ganze Spiele", float(all(n == 1.0 for _h, n in b)), 1.0, 0)
    # Ein einzelner Ausschlag ist ein Spiel - nicht zwei
    check("ein Ausschlag = ein Spiel", float(kollektiv(reservoir([0, 10, 0])) == [(10.0, 1.0)]),
          1.0, 0)
    # Klassieren rafft auf die obere Stufengrenze (sichere Seite)
    kl = kollektiv([(9.0, 1), (5.0, 1), (1.0, 1)], klassen=3)
    check("Klassierung auf die obere Grenze", float(kl == [(9.0, 1.0), (6.0, 1.0), (3.0, 1.0)]),
          1.0, 0)
    # Schadenstabelle: die laufende Summe endet bei D
    tab = schaedigungstabelle([(100e6, 1e6), (50e6, 5e6), (10e6, 1e9)], 71e6, 1.0)
    check("Schadenstabelle: Stufen absteigend",
          float([z[0] for z in tab] == sorted([z[0] for z in tab], reverse=True)), 1.0, 0)
    check("Schadenstabelle: laufende Summe = Miner-Summe",
          tab[-1][4], damage([(100e6, 1e6), (50e6, 5e6), (10e6, 1e9)], 71e6, 1.0), 1e-12)
    check("Stufe unter dem Schwellenwert steht drin, schaedigt aber nicht",
          tab[-1][3], 0.0, 1e-12)
    check("Lebensdauer = Bezugszeit / D", lebensdauer(0.25, 100.0), 400.0, 1e-12)
    check("D = 0 heisst rechnerisch kein Ende",
          float(np.isinf(lebensdauer(0.0, 100.0))), 1.0, 0)


def test_schadensakkumulation():
    """Die Schaedigung gehoert an den Ort - und ein Verlauf traegt mehr Spiele
    als seine beiden Aussenwerte.

    Einfeldtraeger IPE 300, L = 6 m, Kerbfall 71. Zwei Ermuedungslasten
    belasten **verschiedene** Stellen: einmal Gleichlast (groesstes Moment in
    Feldmitte), einmal eine Einzellast im Viertelspunkt. Wer die groessten
    Schwingbreiten beider Lasten addiert, addiert zwei verschiedene Punkte.
    """
    from statik3d.ec3.fatigue import sn_life as _N
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 8)
    m.fix(ids[0], [0, 1, 2, 3]); m.fix(ids[-1], [1, 2, 3])
    m.case().category = "G"
    for e in range(8):
        m.load_beam(e, qz=-10000.0)           # LF1: Gleichlast
    m.add_load_case("LF2", "Q")
    m.load_node(ids[2], Fz=-60000.0)          # LF2: Einzellast im Viertelspunkt
    m.add_member("Traeger", list(range(8)), detail_category=71e6)
    m.add_fatigue_load("Feld", "LF1", None, 1e6)
    m.add_fatigue_load("Viertel", "LF2", None, 1e6)
    an = solver.solve_all(m, design=False, fatigue=True)
    fm = an.fatigue.members["Traeger"]
    # Von Hand: die Schaedigung am massgebenden Ort aus seinem eigenen Kollektiv
    hand = sum(n / _N(h, 71e6, fm.gamma_Mf) for h, n in fm.kollektiv
               if np.isfinite(_N(h, 71e6, fm.gamma_Mf)))
    check("Schaedigung = Miner-Summe des Kollektivs am massgebenden Ort", fm.D, hand, 1e-12)
    # Die naive Summe der Groesstwerte beider Lasten liegt darueber - sie
    # gehoert zu zwei verschiedenen Punkten und tritt nirgends auf.
    naiv = sum(r[1] / _N(r[0], 71e6, fm.gamma_Mf) for r in fm.ranges
               if np.isfinite(_N(r[0], 71e6, fm.gamma_Mf)))
    check("die Summe der Groesstwerte ueber verschiedene Orte ist groesser",
          float(naiv > fm.D * 1.02), 1.0, 0)
    check("das Kollektiv nennt den Ort", float(0.0 <= fm.x_governing <= 6.0), 1.0, 0)
    check("und fuehrt beide Lasten", float(len(fm.kollektiv) == 2), 1.0, 0)

    # Derselbe Traeger als **Verlauf**: 0 -> voll -> teilweise entlastet ->
    # voll -> 0. Eine Ueberfahrt, die zwischendurch abhebt und wieder
    # aufsetzt. Das traegt ein grosses Spiel (0 -> voll) **und** ein kleineres
    # (voll -> teilweise) - genau die Zwischenstufe, die zwei Zustaende nicht
    # sehen koennen.
    m2 = Model()
    m2.add_material(Material.steel("S235"))
    m2.add_section(make_section("IPE 300"))
    ids2 = mesher.line_of_beams(m2, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 8)
    m2.fix(ids2[0], [0, 1, 2, 3]); m2.fix(ids2[-1], [1, 2, 3])
    m2.case().category = "G"
    for e in range(8):
        m2.load_beam(e, qz=-10000.0)
    m2.add_load_case("LF2", "Q")
    for e in range(8):
        m2.load_beam(e, qz=-10000.0)
    m2.load_node(ids2[4], Fz=-40000.0)
    m2.add_load_case("LF0", "Q")              # Nullzustand
    m2.add_member("Traeger", list(range(8)), detail_category=71e6)
    fl = m2.add_fatigue_load("Überfahrt", "LF0", None, 0.0)
    fl.folge = ["LF0", "LF2", "LF1", "LF2", "LF0"]
    fl.wiederholungen = 1e6
    fl.zaehlung = "rainflow"                 # der Verlauf ist eine Zeitfolge - Zwischenstufen zaehlen
    an2 = solver.solve_all(m2, design=False, fatigue=True)
    f2 = an2.fatigue.members["Traeger"]
    check("der Verlauf liefert zwei Stufen, nicht eine",
          float(len(f2.kollektiv) == 2), 1.0, 0)
    check("die groesste Stufe ist der volle Ausschlag 0 -> LF2",
          f2.kollektiv[0][0], f2.dsig_max, 1e-12)
    check("und sie kommt genau einmal je Ueberfahrt vor",
          f2.kollektiv[0][1], 1e6, 1e-6)
    check("die kleinere Stufe traegt zur Schaedigung bei",
          float(f2.D > damage([(f2.kollektiv[0][0], f2.kollektiv[0][1])], 71e6, f2.gamma_Mf)),
          1.0, 0)
    check("und sie ist der Sprung von voll auf teilweise entlastet",
          float(0 < f2.kollektiv[1][0] < f2.kollektiv[0][0]), 1.0, 0)
    # Reservoir statt Rainflow: derselbe Verlauf, dasselbe Ergebnis (er ist
    # geschlossen und beginnt am Nullzustand)
    fl.zaehlung = "reservoir"
    an3 = solver.solve_all(m2, design=False, fatigue=True)
    check("Reservoir liefert hier dieselbe Schaedigung",
          an3.fatigue.members["Traeger"].D, f2.D, 1e-9)

    # Zwei Zustaende allein saehen die Zwischenstufe nicht
    m2.fatigue_loads.clear()
    m2.add_fatigue_load("nur zwei Zustände", "LF2", "LF0", 1e6)
    an_zwei = solver.solve_all(m2, design=False, fatigue=True)
    fz = an_zwei.fatigue.members["Traeger"]
    check("zwei Zustaende sehen nur eine Stufe", float(len(fz.kollektiv) == 1), 1.0, 0)
    check("und unterschaetzen die Schaedigung des Verlaufs", float(fz.D < f2.D), 1.0, 0)

    # Die Uebersichtszeile je Ermuedungslast nennt **ihre** groesste Stufe.
    # Steht davor eine Last mit groesserem Ausschlag, darf deren Zahl nicht in
    # die Zeile des Verlaufs rutschen - sonst laese der Bericht die Ueberfahrt
    # schaerfer, als sie ist.
    m2.fatigue_loads.clear()
    m2.add_fatigue_load("Voll", "LF2", "LF0", 1e3)     # grosser Ausschlag zuerst
    fl2 = m2.add_fatigue_load("Überfahrt", "LF0", None, 0.0)
    fl2.folge = ["LF0", "LF1", "LF0"]                  # kleinerer Ausschlag
    fl2.wiederholungen = 1e3
    fl2.zaehlung = "rainflow"
    f4 = solver.solve_all(m2, design=False, fatigue=True).fatigue.members["Traeger"]
    zeile = {r[2]: r for r in f4.ranges}
    check("die Zeile des Verlaufs nennt nicht die Schwingbreite der Last davor",
          float(zeile["Überfahrt"][0] < zeile["Voll"][0]), 1.0, 0)
    check("sie zaehlt ein Spiel je Ueberfahrt", zeile["Überfahrt"][1], 1e3, 1e-6)
    check("und sie nennt eine Stelle am Stab",
          float(0.0 <= zeile["Überfahrt"][3] <= 6.0), 1.0, 0)
    check("auch der Schub bekommt vom Verlauf eine Zeile",
          float(len(f4.ranges_shear) == 2), 1.0, 0)


def test_design_driver():
    """Einfeldtraeger IPE 300 S235, L = 6 m, q = 10 kN/m (GZT-Kombi 1.0):
    M = 45 kNm -> Querschnitt 0.305; Biegedrillknicken massgebend (Mb,Rd < Mc,Rd)."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3]); m.fix(ids[-1], [1, 2, 3])
    m.case().category = "G"
    for e in range(6):
        m.load_beam(e, qz=-10000.0)
    m.add_member("Traeger", list(range(6)), detail_category=71e6)
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    m.add_fatigue_load("Ermuedung", "LF1", None, 2e6)
    an = solver.solve_all(m, design=True, fatigue=True)
    mc = an.design.members["Traeger"]
    sec = m.sections["IPE 300"]
    u_sec = 45e3 / (sec.Wpl_y * 235e6)
    sec_best = max(mc.section_checks, key=lambda b: b["util"])
    check("Nachweis: Querschnitt M/Mc,Rd", sec_best["util"], u_sec, 1e-2)
    check("Nachweis: Klasse 1", mc.cls, 1, 0)
    st = mc.stability[0]
    check("Nachweis: BDK vorhanden", float("Biegedrillknicken (6.3.2)" in st["checks"]), 1.0, 0)
    check("Nachweis: massgebend BDK", float(mc.governing["name"].startswith("Biegedrill")), 1.0, 0)
    check("Nachweis: BDK C1 ~ 1.13", st["details"]["C1"], 1.136, 2e-2)
    # Ermuedung: Delta_sigma = M/Wel = 45e3/557e-6 = 80.8 MPa, n = 2e6, KF 71, gamma_Mf 1.0
    fm = an.fatigue.members["Traeger"]
    ds = 45e3 / sec.Wel_y
    check("Ermuedung: Delta_sigma", fm.dsig_max, ds, 1e-2)
    check("Ermuedung: D = n/N_R", fm.D, 2e6 / sn_life(fm.dsig_max, 71e6, 1.0), 1e-9)
    # Textausgaben
    check("Zusammenfassung vorhanden", float(len(an.summary()) > 50), 1.0, 0)
    check("Tabelle Nachweise", float(len(an.design.table()) == 2), 1.0, 0)


def _traeger_und_stab_ohne_fy():
    """Einfeldtraeger IPE 300 S235 wie in test_design_driver, daneben ein
    zweiter Stab aus einem Werkstoff **ohne Streckgrenze** - so kommt er aus
    einem Import (rfem_tables, nastran, abaqus, saf ohne erkannte Sorte)."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_material(Material("Frei", 210e9, 0.3, 7850.0))        # fy = None
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3]); m.fix(ids[-1], [1, 2, 3])
    ids2 = mesher.line_of_beams(m, "Frei", "IPE 300", (0, 2, 0), (6, 2, 0), 6)
    m.fix(ids2[0], [0, 1, 2, 3]); m.fix(ids2[-1], [1, 2, 3])
    m.case().category = "G"
    for e in range(len(m.elements)):
        m.load_beam(e, qz=-10000.0)
    m.add_member("Traeger", list(range(6)))
    m.add_member("Ohne_fy", list(range(6, 12)))
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    return m


def test_stab_ohne_streckgrenze_nicht_gefuehrt():
    """Ein Stab ohne Streckgrenze ist **nicht gefuehrt**, nicht erfuellt.

    check_member bricht bei f_y = 0 ab; der MemberCheck behaelt Ausnutzung
    0,000. Seit efcf3d6 traegt er ``fehler`` und status() sagt "nicht
    geführt" - aber DesignResults.summary() zaehlte weiter nur util > 1 und
    schrieb "... max. Ausnutzung 0.633 ... - alle erfuellt" (gemessen
    22.09.2026). Genau diese Zeile steht in der Oberflaeche nach "Nachweise
    EC3", im Etikett der Maske Nachweise (Gruppe "Nachweise führen"), im
    Textfeld der Maske Ergebnisse und in Analysis.summary() - alle Stellen
    im Kommentar von DesignResults.summary().
    Geprueft wird am echten Weg solve_all(design=True).
    """
    m = _traeger_und_stab_ohne_fy()
    an = solver.solve_all(m, design=True)
    d = an.design
    mc = d.members["Ohne_fy"]
    check("ohne f_y: check_member setzt mc.fehler",
          float("ohne Streckgrenze" in mc.fehler), 1.0, 0)
    check("ohne f_y: status() = 'nicht geführt'", float(mc.status() == "nicht geführt"), 1.0, 0)
    zeile = [r for r in d.table()[1:] if r[0] == "Ohne_fy"]
    check("ohne f_y: table() zeigt 'nicht geführt'",
          float(bool(zeile) and zeile[0][-1] == "nicht geführt"), 1.0, 0)
    s = d.summary()
    print("     summary():", s)
    check("ohne f_y: summary() sagt nicht 'alle erfuellt'", float("alle erfuellt" not in s), 1.0, 0)
    check("ohne f_y: summary() nennt den Stab als nicht geführt",
          float("1 nicht geführt" in s and "Ohne_fy" in s), 1.0, 0)
    check("ohne f_y: max. Ausnutzung kommt vom gefuehrten Stab",
          float("max. Ausnutzung" in s and "(Traeger:" in s), 1.0, 0)
    zeilen = [z for z in an.summary().splitlines() if z.startswith("Nachweise EC3")]
    check("ohne f_y: auch Analysis.summary() sagt nicht 'alle erfuellt'",
          float(bool(zeilen) and "alle erfuellt" not in zeilen[0]), 1.0, 0)
    # Nur der Stab ohne f_y: keine Ausnutzung behaupten, die es nicht gibt
    d1 = check_members(m, an, members=["Ohne_fy"], use_jobs=False)
    s1 = d1.summary()
    print("     summary() nur Ohne_fy:", s1)
    check("nur ein nicht gefuehrter Stab: keine 'max. Ausnutzung', nicht 'alle erfuellt'",
          float("max. Ausnutzung" not in s1 and "alle erfuellt" not in s1
                and "nicht geführt" in s1), 1.0, 0)
    # Gegenprobe: nur der gefuehrte Stab - dort bleibt es bei "alle erfuellt"
    d2 = check_members(m, an, members=["Traeger"], use_jobs=False)
    check("Gegenprobe nur Traeger: summary() 'alle erfuellt'",
          float(d2.summary().endswith(" - alle erfuellt")), 1.0, 0)


def _svg_mit_titel(html: str, titel: str) -> str:
    """Das eingebettete SVG-Bild mit diesem <title> - leer, wenn es fehlt."""
    i = html.find(f"<title>{titel}</title>")
    if i < 0:
        return ""
    return html[html.rfind("<svg", 0, i):html.find("</svg>", i) + len("</svg>")]


def test_nicht_gefuehrt_ohne_ausnutzung_in_bildern():
    """Ein nicht gefuehrter Stab hat keine Ausnutzung - auch nicht in der
    Faerbung "Ausnutzung EC3" und im Balkendiagramm des Berichts.

    Bis zum 23.09.2026 gab util_by_element den Elementen eines Stabes ohne
    f_y seine Ausnutzung 0,0 mit: in der Oberflaeche und im Bericht wurden
    sie gruen (#2e8b57, Klasse < 0,50) und sahen aus wie unbeansprucht, und
    das Balkendiagramm "Ausnutzung je Stab" zeigte fuer "Ohne_fy" einen
    gruenen Balken mit "0.000" (Befund B054, gemessen am selben Modell).
    """
    from statik3d.report import Report
    from statik3d.report import svg as sv
    m = _traeger_und_stab_ohne_fy()
    an = solver.solve_all(m, design=True)
    d = an.design
    ube = d.util_by_element()
    ohne = list(m.members["Ohne_fy"].elements)
    traeger = list(m.members["Traeger"].elements)
    ut = d.members["Traeger"].util
    check("util_by_element: kein Wert fuer die Elemente des nicht gefuehrten Stabs",
          float(sum(1 for e in ohne if e in ube)), 0.0, 0)
    check("util_by_element: der Traeger behaelt seine Ausnutzung",
          float(all(e in ube and ube[e] == ut for e in traeger) and ut > 0.5), 1.0, 0)
    html = Report(m, an).html()
    balken = _svg_mit_titel(html, "Ausnutzung je Stab")
    check("Balkendiagramm: kein Balken fuer den nicht gefuehrten Stab",
          float(bool(balken) and ">Ohne_fy<" not in balken), 1.0, 0)
    check("Balkendiagramm: der Traeger mit seinem Wert",
          float(">Traeger<" in balken and f">{ut:.3f}<" in balken), 1.0, 0)
    bild = _svg_mit_titel(html, "Ausnutzung der Stäbe")
    gruen = bild.count(f'stroke="{sv.util_colour(0.0)}"')
    stabfarbe = bild.count(f'stroke="{sv.COL_BEAM}"')
    print(f"     Bild 'Ausnutzung der Stäbe': {gruen} Linien gruen, {stabfarbe} in Stabfarbe")
    check("Bericht, Faerbung: keine Linie in der Farbe der Ausnutzung 0",
          float(gruen), 0.0, 0)
    check("Bericht, Faerbung: die sechs Elemente von Ohne_fy in Stabfarbe",
          float(stabfarbe), float(len(ohne)), 0)
    check("beide Bildunterschriften nennen den nicht gefuehrten Stab",
          float(html.count("weil nicht geführt: Ohne_fy")), 2.0, 0)


def test_kein_stab_gefuehrt_keine_bilder():
    """Ist **kein** Stab gefuehrt, zeichnet der Bericht weder das
    Balkendiagramm "Ausnutzung je Stab" noch das Bild "Ausnutzung der Staebe"
    (html.py chapter_design, ``and gefuehrt``) - es gaebe keinen Wert zu
    zeigen. So steht es in beiden Handbuechern und im Docstring von
    util_by_element. Bis zum 24.09.2026 sagten sie nur "in Stabfarbe, beide
    Bildunterschriften nennen ihn", was hier nicht zutrifft (Gegenpruefung
    zu B054: ein Stab HEA 200 aus Werkstoff ohne f_y, kein Bild, keine
    Bildunterschrift). Der Fall ist nicht abwegig: bei Importen ohne
    erkannte Stahlsorte fehlt f_y oft an allen Staeben.
    """
    from statik3d.report import Report
    m = _traeger_und_stab_ohne_fy()
    for e in m.members["Traeger"].elements:
        m.elements[e].mat = "Frei"               # jetzt ist auch er ohne f_y
    an = solver.solve_all(m, design=True)
    d = an.design
    check("kein Stab gefuehrt: beide Staebe 'nicht geführt'",
          float(sorted(mc.status() for mc in d.members.values())
                == ["nicht geführt", "nicht geführt"]), 1.0, 0)
    check("kein Stab gefuehrt: util_by_element ist leer",
          float(len(d.util_by_element())), 0.0, 0)
    html = Report(m, an).html()
    check("kein Stab gefuehrt: kein Balkendiagramm 'Ausnutzung je Stab'",
          float(bool(_svg_mit_titel(html, "Ausnutzung je Stab"))), 0.0, 0)
    check("kein Stab gefuehrt: kein Bild 'Ausnutzung der Stäbe'",
          float(bool(_svg_mit_titel(html, "Ausnutzung der Stäbe"))), 0.0, 0)
    check("kein Stab gefuehrt: keine Bildunterschrift zur Ausnutzung",
          float(html.count("Ausnutzungsgrade der Stäbe")
                + html.count("Ausnutzung der Stäbe (Farbskala)")), 0.0, 0)


def test_sorte_ohne_streckgrenze():
    """Befund B060: Werkstoff mit Stahlsorte, aber leerem f_y.

    Der Werkstoffdialog sagt bei f_y "leer = aus der Stahlsorte" und
    speichert dann fy = None. Material.yield_strength nahm die Sorte aber nur
    fuer t > 40 mm und gab darunter ``fy or 0.0`` zurueck: gemessen am Stand
    ec6448c (23.09.2026) mit Sorte S235 und leerem f_y 0 N/mm² bei 0 / 10,7 /
    40 mm und 215 N/mm² bei 41 / 80 mm; ein IPE 300 aus diesem Werkstoff war
    "nicht geführt" ("Werkstoff Frei ohne Streckgrenze"), obwohl die Sorte
    eingetragen ist. Richtig ist EN 1993-1-1 Tab. 3.1 bis 40 mm: 235 / 360
    N/mm² (die Zweistufenregel bei 40 mm; EN 10025-2 selbst stuft feiner).
    Ohne Sorte und ohne f_y bleibt der Stab nicht gefuehrt
    (test_stab_ohne_streckgrenze_nicht_gefuehrt).
    """
    mt = Material("Frei", 210e9, 0.3, 7850.0, 12e-6, None, None, "S235")
    check("Sorte S235, f_y leer: f_y bei t = 10,7 mm = 235 N/mm²", mt.yield_strength(0.0107), 235e6, 0)
    check("Sorte S235, f_y leer: f_y bei t = 0 (ohne Dicke) = 235 N/mm²", mt.yield_strength(0.0), 235e6, 0)
    check("Sorte S235, f_y leer: f_y bei t = 40 mm = 235 N/mm²", mt.yield_strength(0.040), 235e6, 0)
    check("Sorte S235, f_y leer: f_y bei t = 41 mm = 215 N/mm² (wie bisher)",
          mt.yield_strength(0.041), 215e6, 0)
    check("Sorte S235, f_u leer: f_u bei t = 10,7 mm = 360 N/mm²", mt.ultimate_strength(0.0107), 360e6, 0)
    # Ein ausdrueckliches f_y bleibt bis 40 mm vorn - die Sorte ersetzt dort
    # nur das leere Feld. Ueber 40 mm gilt die untere Stufe der Sorte auch
    # gegen ein eingetragenes f_y (yield_strength fragt t > 0,040 m zuerst ab).
    # Das Benutzerhandbuch sagte am 23.09.2026 "geht der Sorte immer vor";
    # gemessen 24.09.2026: bei 41 mm 215 statt 300 N/mm², f_u 360 statt 390
    mx = Material("Eigen", fy=300e6, grade="S235")
    check("f_y 300 mit Sorte S235: f_y bei 10,7 mm bleibt 300 N/mm²", mx.yield_strength(0.0107), 300e6, 0)
    check("f_y 300 mit Sorte S235: f_y bei 40 mm bleibt 300 N/mm²", mx.yield_strength(0.040), 300e6, 0)
    check("f_y 300 ohne f_u: f_u bleibt 1,3 f_y = 390 N/mm²", mx.ultimate_strength(0.0107), 390e6, 1e-12)
    check("f_y 300 mit Sorte S235: über 40 mm gilt die untere Stufe der Sorte, 215 N/mm²",
          mx.yield_strength(0.041), 215e6, 0)
    check("f_y 300 ohne f_u: über 40 mm f_u der Sorte, 360 N/mm² (nicht 1,3 f_y)",
          mx.ultimate_strength(0.041), 360e6, 0)

    # Am echten Weg: derselbe Traeger zweimal, einmal aus Material.steel("S235"),
    # einmal aus dem Werkstoff mit Sorte S235 und leerem f_y
    m = _traeger_und_stab_ohne_fy()
    m.materials["Frei"].grade = "S235"
    an = solver.solve_all(m, design=True)
    mc, mt_ = an.design.members["Ohne_fy"], an.design.members["Traeger"]
    print("     Ohne_fy:", mc.status(), repr(mc.fehler), f"util {mc.util:.4f}",
          "| Traeger:", mt_.status(), f"util {mt_.util:.4f}")
    check("Stab aus Sorte S235 mit leerem f_y ist geführt (kein fehler)",
          float(not mc.fehler and mc.status() != "nicht geführt"), 1.0, 0)
    check("… mit derselben Ausnutzung wie der Träger aus S235", mc.util, mt_.util, 1e-9)


def test_frame_parallel_design():
    """Rahmen mit vielen Staeben: Nachweise seriell == parallel (Auftraege)."""
    from statik3d.examples_lib import frame_example
    m = frame_example()
    m.sections.clear(); m.add_section(make_section("HEA 200", "HEA 200"))
    for e in m.elements:
        e.sec = "HEA 200"
    m.materials["S355"] = Material.steel("S355")
    m.auto_members()
    m.add_load_case("W", "W")
    m.load_node(int(mesher.select_nodes(m, xmin=-1e-6, xmax=1e-6, zmin=4 - 1e-6)[0]), Fx=8000)
    generate_combinations(m)
    an = solver.solve_all(m)
    d1 = check_members(m, an, use_jobs=False)
    d2 = check_members(m, an, use_jobs=True, workers=2)
    check("Rahmen: Staebe erkannt", float(len(m.members)), 3.0, 0)
    check("Rahmen: Nachweise seriell == parallel", d2.util_max, d1.util_max, 1e-12)
    check("Rahmen: Ausnutzung plausibel (0 < u < 5)", float(0 < d1.util_max < 5), 1.0, 0)


def test_nachweisauftrag_traegt_kein_modell():
    """Ein Nachweis-Auftrag darf das Modell nicht mitschleppen.

    Bis zum 21.09.2026 stand in **jedem** Auftrag ein eigenes
    ``model.to_dict()``. Am Drehlager des Anwenders (162 166 Knoten, 662 889
    Elemente, 239 MB als Datei) waren das rund 228 MB je Auftrag bei 64
    Auftraegen - etwa 14,6 GB durch die Prozess-Pipes. Der Lauf stand nach
    698 Minuten bei 94 % und kam nicht weiter; ein Arbeiter starb vorher mit
    AssertionError in multiprocessing/connection.py (_get_more_data, die
    Pipe brach).

    Gemessen an Pruefkoerpern (21.09.2026), ein Auftrag alt gegen neu:
    17 Knoten 0,058 MB gegen 76 Byte, 360 Knoten 0,478 MB, 2 214 Knoten
    2,996 MB - die Last waechst linear mit dem Netz, der neue Auftrag nicht.
    """
    import pickle
    from statik3d import parallel as _par
    from statik3d.examples_lib import frame_example
    m = frame_example()
    m.sections.clear(); m.add_section(make_section("HEA 200", "HEA 200"))
    for e in m.elements:
        e.sec = "HEA 200"
    m.materials["S355"] = Material.steel("S355")
    m.auto_members()
    generate_combinations(m)
    # Ein Volumennetz danebenlegen - wie am Drehlager, wo das Modell fast
    # nur aus Netz besteht
    mesher.grid_box(m, "S355", 1.0, 1.0, 1.0, 8, 8, 8, origin=(10, 10, 0), typ="tet4")
    an = solver.solve_all(m)

    gefangen = []
    echt = _par.run_jobs

    def fangen(jobs, **kw):
        gefangen.extend(jobs)
        return echt(jobs, **kw)

    _par.run_jobs = fangen
    try:
        import statik3d.ec3.design as _d
        _d.run_jobs = fangen if hasattr(_d, "run_jobs") else None
        check_members(m, an, use_jobs=True, workers=2)
    finally:
        _par.run_jobs = echt
    check("Nachweisauftraege wurden gebildet", float(bool(gefangen)), 1.0, 0)
    if not gefangen:
        return
    groesse = max(len(pickle.dumps(j.payload, protocol=pickle.HIGHEST_PROTOCOL))
                  for j in gefangen)
    ohne_modell = all("model" not in j.payload or j.payload.get("model") is None
                      for j in gefangen)
    check("kein Auftrag traegt das Modell", float(ohne_modell), 1.0, 0)
    # Ohne die Aenderung liegt ein Auftrag dieses Modells bei rund 1 MB.
    check("ein Auftrag bleibt unter 10 kB", float(groesse < 10_000), 1.0, 0)
    check("… und nennt stattdessen eine Paketdatei",
          float(all(j.payload.get("paket") for j in gefangen)), 1.0, 0)


def test_nachweisetikett_folgt_dem_ergebnis():
    """Das Etikett der Maske Nachweise (Gruppe „Nachweise führen“) zeigt,
    was die statische Analyse (self.analysis: das Ergebnis der letzten
    Rechnung „Alle Lastfaelle + Kombinationen“ oder „Nur aktiver Lastfall“)
    an Nachweisen hat - nicht, was eine fruehere statische Rechnung hatte.
    Eigenformen und Knicken lassen diese Analyse stehen (_solve_done setzt
    dann nur results): danach bleibt ihre Zeile, obwohl das gezeigte
    Ergebnis selbst keine Nachweise hat. Gemessen am 24.09.2026 im Fenster
    (offscreen), Einfeldtraeger IPE 300 mit Druckkraft: EC3-Zeile nach
    do_solve('modal') und do_solve('buckling') unveraendert.

    MainWindow.show_results setzte das Etikett bis zum 23.09.2026 nur, wenn
    ein EC3- oder Ermuedungsergebnis vorlag. Nach einer Rechnung mit EC3 und
    einer zweiten ohne Nachweise blieb die alte Zeile „Nachweise EC3: …
    max. Ausnutzung …“ stehen (Nebenbefund NB1, Probe np_6/p68: am
    Hallenrahmen 0 setText-Aufrufe bei der zweiten Rechnung); mit nur
    Ermuedung wurde es geleert (B069).
    Ohne Fenster: echte Methoden, self als Attrappe, das Etikett merkt sich
    seinen Text wie das QLabel.
    Geprueft sind show_results und _solve_done (Eigenformen, Knicken,
    aktiver Lastfall nach einer Rechnung mit Nachweisen). Wege, die das
    Ergebnis verwerfen, ohne show_results aufzurufen (clear_loads,
    new_model, Uebernehmen in der Lastfallmaske), lassen die alte Zeile
    stehen - gemessen am 24.09.2026,
    clear_loads und new_model im Fenster (offscreen), das Uebernehmen mit
    Attrappe; noch offen.
    """
    from unittest import mock
    from statik3d.gui.main import MainWindow

    class Etikett:
        def __init__(self):
            self.text = "noch keine Nachweise"      # wie beim Anlegen der Maske

        def setText(self, t):
            self.text = str(t)

    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3]); m.fix(ids[-1], [1, 2, 3])
    m.case().category = "G"
    for e in range(6):
        m.load_beam(e, qz=-10000.0)
    m.add_member("Traeger", list(range(6)), detail_category=71e6)
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    m.add_fatigue_load("Ermuedung", "LF1", None, 2e6)
    an_ec3 = solver.solve_all(m, design=True, fatigue=False)
    an_fat = solver.solve_all(m, design=False, fatigue=True)
    an_beide = solver.solve_all(m, design=True, fatigue=True)
    an_ohne = solver.solve_all(m, design=False, fatigue=False)

    fenster = mock.MagicMock()
    fenster.model = m
    fenster.results = None
    fenster.lbl_design = Etikett()
    # die Ermuedungszeile traegt seit 25.09.2026 das Urteil wie im Protokoll
    fenster._ermuedung_zusatz = MainWindow._ermuedung_zusatz

    def erm(an):
        return an.fatigue.summary() + MainWindow._ermuedung_zusatz(an.fatigue)

    def zeige(an):
        fenster.analysis = an
        fenster.current_result.return_value = (
            None if an is None else next(iter(an.combinations.values())))
        try:
            MainWindow.show_results(fenster)
        except Exception as ex:      # noqa: BLE001 - als Fehlschlag zaehlen
            print(f"     show_results: {type(ex).__name__}: {ex}")
            return f"(Ausnahme {type(ex).__name__})"
        return fenster.lbl_design.text

    t = zeige(an_ec3)
    print("     mit EC3:", t)
    check("Etikett: mit EC3 steht die Zeile der Nachweise EC3",
          float(t == an_ec3.design.summary()), 1.0, 0)
    t = zeige(an_ohne)
    print("     danach ohne Nachweise:", t)
    check("Etikett: danach ohne Nachweise keine EC3-Zeile mehr",
          float("Nachweise EC3" not in t), 1.0, 0)
    check("Etikett: ohne Nachweise 'noch keine Nachweise'",
          float(t == "noch keine Nachweise"), 1.0, 0)
    t = zeige(an_fat)
    print("     nur Ermuedung:", t)
    check("Etikett: nur Ermuedung zeigt die Zeile der Ermuedung",
          float(t == erm(an_fat) and "Nachweise EC3" not in t), 1.0, 0)
    t = zeige(an_beide)
    check("Etikett: EC3 und Ermuedung untereinander",
          float(t == an_beide.design.summary() + "\n" + erm(an_beide)), 1.0, 0)
    t = zeige(None)
    check("Etikett: ohne Ergebnis 'noch keine Nachweise'",
          float(t == "noch keine Nachweise"), 1.0, 0)

    # Nach der statischen Rechnung eine weitere Rechnung ueber den echten
    # _solve_done: Eigenformen und Knicken setzen nur results und lassen
    # analysis stehen - gezeigt werden dann Eigenformen bzw. Knickfiguren,
    # das Etikett behaelt die Zeile der statischen Rechnung. Der Einzellastfall
    # ersetzt analysis und hat keine Nachweise. Bis zum 24.09.2026 sagten
    # Docstring und Handbuch „das gezeigte Ergebnis“ - nach Eigenformen falsch
    # (Gegenpruefung, im Fenster gemessen).
    import copy
    m_druck = copy.deepcopy(m)
    m_druck.load_node(ids[-1], Fx=-100000.0)     # Normalkraft fuer das Verzweigungsproblem
    fenster.show_results = lambda: MainWindow.show_results(fenster)

    def danach(an, art, r):
        zeige(an)                                # die statische Rechnung vorher
        fenster.results = None
        fenster.current_result.return_value = r
        if art != "case":                        # results gesetzt: die echte Auswahl
            fenster.current_result.side_effect = lambda: MainWindow.current_result(fenster)
        try:
            MainWindow._solve_done(fenster, art, r)
        except Exception as ex:      # noqa: BLE001 - als Fehlschlag zaehlen
            print(f"     _solve_done({art!r}): {type(ex).__name__}: {ex}")
            return f"(Ausnahme {type(ex).__name__})"
        finally:
            fenster.current_result.side_effect = None
        return fenster.lbl_design.text

    r_modal = solver.solve_modal(m, 2)
    t = danach(an_ec3, "modal", r_modal)
    print("     EC3, danach Eigenformen:", t)
    check("Etikett: nach Eigenformen sind die Eigenformen gezeigt",
          float(fenster.results is r_modal and r_modal.freqs is not None), 1.0, 0)
    check("Etikett: nach Eigenformen bleibt die EC3-Zeile der statischen Rechnung",
          float(t == an_ec3.design.summary()), 1.0, 0)
    r_knick = solver.solve_buckling(m_druck, 2)
    t = danach(an_beide, "buckling", r_knick)
    print("     EC3 + Ermuedung, danach Knicken:", t.replace("\n", " | "))
    check("Etikett: nach Knicken sind die Knickfiguren gezeigt",
          float(fenster.results is r_knick and r_knick.buckling_factors is not None), 1.0, 0)
    check("Etikett: nach Knicken bleiben EC3- und Ermuedungszeile",
          float(t == an_beide.design.summary() + "\n" + erm(an_beide)), 1.0, 0)
    t = danach(an_ec3, "case", solver.solve_static(m))
    print("     EC3, danach aktiver Lastfall:", t)
    check("Etikett: nach dem aktiven Lastfall 'noch keine Nachweise'",
          float(t == "noch keine Nachweise"), 1.0, 0)


def main():
    print("=" * 100)
    print("STATIK3D - Verifikation EC3 (Klassifizierung, Querschnitt, Stabilitaet, Ermuedung)")
    print("=" * 100)
    test_classification()
    test_section_resistance()
    test_torsion_schoepft_schub_aus()
    test_flexural_buckling()
    test_ltb()
    test_interaction()
    test_fatigue()
    test_zaehlverfahren()
    test_schadensakkumulation()
    test_design_driver()
    test_stab_ohne_streckgrenze_nicht_gefuehrt()
    test_nicht_gefuehrt_ohne_ausnutzung_in_bildern()
    test_kein_stab_gefuehrt_keine_bilder()
    test_sorte_ohne_streckgrenze()
    test_frame_parallel_design()
    test_nachweisauftrag_traegt_kein_modell()
    test_nachweisetikett_folgt_dem_ergebnis()
    nok =sum(1 for r in RESULTS if r[4])
    print("=" * 100)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Tests bestanden")
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
