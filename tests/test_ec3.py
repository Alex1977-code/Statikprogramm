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
    test_design_driver()
    test_frame_parallel_design()
    nok = sum(1 for r in RESULTS if r[4])
    print("=" * 100)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Tests bestanden")
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
