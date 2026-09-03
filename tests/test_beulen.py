"""
Verifikation des Plattenbeulens nach DIN EN 1993-1-5.

Geprueft wird gegen die Zahlenwerte der Norm - die Beulwerte der Tabellen 4.1,
4.2 und A.3, die Bezugsspannung 190000 (t/b)^2, die Abminderungsbeiwerte nach
4.4(2) und Tab. 5.1 - sowie gegen Handrechnungen fuer den Schubbeulnachweis
und die Methode der reduzierten Spannungen.

Aufruf:  python -m tests.test_beulen
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.ec3 import beulen as B                              # noqa: E402
from statik3d.model import Model, Material, ShellProp, Section    # noqa: E402
from statik3d import solver                                       # noqa: E402

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
def test_beulwerte():
    # Tab. 4.1, beidseitig gestuetzte Bleche
    for psi, soll in ((1.0, 4.0), (0.0, 7.81), (-1.0, 23.9), (-2.0, 53.82),
                      (-3.0, 95.68)):
        close(f"k_σ Tab. 4.1 für ψ = {psi:g}", B.k_sigma(psi), soll, 2e-3)
    close("k_σ Tab. 4.1 für ψ = 0,5", B.k_sigma(0.5), 8.2 / 1.55, 1e-12)
    check("k_σ fällt mit ψ monoton",
          B.k_sigma(1.0) < B.k_sigma(0.0) < B.k_sigma(-1.0) < B.k_sigma(-2.0))
    # Tab. 4.2, einseitig gestuetzt
    close("k_σ Tab. 4.2 für ψ = 1 (Druck am freien Rand)",
          B.k_sigma(1.0, "einseitig"), 0.43, 1e-12)
    close("k_σ Tab. 4.2 für ψ = 0", B.k_sigma(0.0, "einseitig"), 0.578 / 0.34, 1e-12)
    check("einseitig gestützt ist deutlich ungünstiger",
          B.k_sigma(1.0, "einseitig") < 0.15 * B.k_sigma(1.0))

    # A.3: Schubbeulwerte
    close("k_τ für α = 1", B.k_tau(1.0), 9.34, 1e-12)
    close("k_τ für α = 2", B.k_tau(2.0), 5.34 + 1.0, 1e-12)
    close("k_τ für α = 0,5", B.k_tau(0.5), 4.00 + 5.34 / 0.25, 1e-12)
    check("k_τ nimmt mit dem Seitenverhältnis ab",
          B.k_tau(1.0) > B.k_tau(2.0) > B.k_tau(4.0) > 5.34)

    # Bezugsspannung: 190000 (t/b)^2 N/mm^2
    for tb in (1 / 100.0, 1 / 50.0, 1 / 200.0):
        close(f"σ_E für t/b = {tb:.4f}", B.sigma_E(tb, 1.0) / 1e6,
              190000.0 * tb ** 2, 2e-3, " N/mm²")


def test_abminderung():
    # 4.4(2), beidseitig gestuetzt: Grenze 0,673 bei psi = 1
    close("Grenzschlankheit ψ = 1", 0.5 + math.sqrt(0.085 - 0.055), 0.673, 2e-3)
    check("ρ = 1 unterhalb der Grenze", B.rho_platte(0.672, 1.0) == 1.0)
    close("ρ bei λ̄_p = 1,0 und ψ = 1", B.rho_platte(1.0, 1.0), (1.0 - 0.22) / 1.0, 1e-12)
    close("ρ bei λ̄_p = 1,5 und ψ = -1", B.rho_platte(1.5, -1.0),
          (1.5 - 0.055 * 2.0) / 1.5 ** 2, 1e-12)
    check("ρ ist nie größer als 1", B.rho_platte(0.7, -1.0) <= 1.0)
    # einseitig: Grenze 0,748
    check("ρ = 1 unterhalb 0,748 (einseitig)",
          B.rho_platte(0.747, rand="einseitig") == 1.0)
    close("ρ bei λ̄_p = 1,0 (einseitig)", B.rho_platte(1.0, rand="einseitig"),
          1.0 - 0.188, 1e-12)

    # Tab. 5.1, chi_w
    eta = B.ETA_SCHUB
    check("χ_w = η für sehr gedrungene Stege", B.chi_w(0.5) == eta)
    close("χ_w = 0,83/λ̄_w im mittleren Bereich", B.chi_w(1.0), 0.83, 1e-12)
    close("χ_w mit starrer Endsteife (λ̄_w = 1,5)", B.chi_w(1.5, True),
          1.37 / (0.7 + 1.5), 1e-12)
    close("χ_w ohne starre Endsteife (λ̄_w = 1,5)", B.chi_w(1.5, False),
          0.83 / 1.5, 1e-12)
    check("die starre Endsteife hilft", B.chi_w(2.0, True) > B.chi_w(2.0, False))


def test_schubbeulen():
    hw, tw, fy = 1.200, 0.008, 355e6
    noetig, grenze, _text = B.schubbeulen_noetig(hw, tw, fy)
    eps = math.sqrt(235.0 / 355.0)
    close("Grenze 72 ε/η", grenze, 72.0 * eps / 1.2, 1e-12)
    check("schlanker Steg braucht den Nachweis", noetig, f"h_w/t_w = {hw / tw:.0f}")
    check("gedrungener Steg braucht ihn nicht",
          not B.schubbeulen_noetig(0.300, 0.020, fy)[0])

    r = B.schubbeulen(hw, tw, fy, a=0.0, gamma_M1=1.1)
    close("λ̄_w = h_w/(86,4 t_w ε)", r["lambda_w"], hw / (86.4 * tw * eps), 1e-12)
    close("χ_w aus Tab. 5.1", r["chi_w"], B.chi_w(r["lambda_w"]), 1e-12)
    close("V_b,Rd = χ_w f_yw h_w t_w /(√3 γ_M1)", r["V_b_Rd"],
          r["chi_w"] * fy * hw * tw / (math.sqrt(3) * 1.1), 1e-12, " N")
    check("V_b,Rd liegt unter der plastischen Grenze", r["V_b_Rd"] < r["V_max"],
          f"{r['V_b_Rd'] / 1e3:.0f} < {r['V_max'] / 1e3:.0f} kN")

    # Quersteifen machen den Steg tragfaehiger
    r2 = B.schubbeulen(hw, tw, fy, a=1.200, gamma_M1=1.1)
    check("Quersteifen erhöhen V_b,Rd", r2["V_b_Rd"] > r["V_b_Rd"],
          f"{r2['V_b_Rd'] / 1e3:.0f} > {r['V_b_Rd'] / 1e3:.0f} kN")
    close("k_τ der Steifen geht ein", r2["k_tau"], B.k_tau(1.2 / 1.2), 1e-12)

    # gedrungener Steg: chi_w = eta, V_b,Rd wird begrenzt
    r3 = B.schubbeulen(0.500, 0.020, fy, a=0.0, gamma_M1=1.1)
    check("gedrungener Steg wird auf η f_yw h_w t_w/(√3 γ_M1) begrenzt",
          abs(r3["V_b_Rd"] - r3["V_max"]) < 1e-6, f"χ_w = {r3['chi_w']:.3f}")


def test_stabnachweis_fuehrt_schubbeulen():
    """Im Querschnittsnachweis steht jetzt ein Nachweis, keine Ankündigung."""
    from statik3d.ec3.resistance import section_check
    # Blechtraeger 1240 x 400, Flansch 20 mm, Steg 8 mm - Kennwerte passend
    sec = Section("Blechträger", A=2 * 0.400 * 0.020 + 1.200 * 0.008, Iy=7.106e-3,
                  Iz=2.13e-4, It=3.0e-6, Wpl_y=12.64e-3, Wel_y=11.46e-3,
                  Wpl_z=1.63e-3, Wel_z=1.07e-3, typ="I", h=1.240, b=0.400,
                  tw=0.008, tf=0.020, zmax=0.62, ymax=0.2, Asz=1.200 * 0.008)
    b = B.schubbeulen(1.200, 0.008, 355e6, 0.0, 1.1)
    M_f_Rd = 0.400 * 0.020 * (1.240 - 0.020) * 355e6      # Flansche allein
    r = section_check(sec, 355e6, N=0.0, Vy=0.0, Vz=600e3, Mt=0.0, My=1500e3,
                      Mz=0.0, gamma_M0=1.0, gamma_M1=1.1)
    name = "Schubbeulen V_b,Rd (EN 1993-1-5, 5.2)"
    check("der Schubbeulnachweis wird geführt", name in r["checks"],
          str(sorted(r["checks"]))[:70])
    u, text = r["checks"][name]
    close("Ausnutzung stimmt mit dem Kernmodul überein", u, 600e3 / b["V_b_Rd"], 1e-9)
    check("der Text nennt λ̄_w und χ_w", "λ̄_w" in text and "χ_w" in text, text[:60])
    check("unter M_f,Rd entfällt die Interaktion M–V (7.1(1))",
          not any("7.1" in k for k in r["checks"]),
          f"M_Ed = 1500 kNm ≤ M_f,Rd = {M_f_Rd / 1e3:.0f} kNm")
    r2 = section_check(sec, 355e6, N=0.0, Vy=0.0, Vz=600e3, Mt=0.0, My=4000e3,
                       Mz=0.0, gamma_M0=1.0, gamma_M1=1.1)
    check("über M_f,Rd wird die Interaktion M–V geführt",
          any("7.1" in k for k in r2["checks"]), str(sorted(r2["checks"]))[:110])
    # gedrungener Steg: kein Beulnachweis
    sec2 = Section("HEB 300", A=149.1e-4, Iy=25170e-8, Iz=8563e-8, It=185e-8,
                   Wpl_y=1869e-6, Wel_y=1678e-6, Wpl_z=870e-6, Wel_z=571e-6,
                   typ="I", h=0.300, b=0.300, tw=0.011, tf=0.019, r=0.027,
                   zmax=0.15, ymax=0.15, Asz=47.4e-4)
    r2 = section_check(sec2, 355e6, N=0.0, Vy=0.0, Vz=300e3, Mt=0.0, My=300e3,
                       Mz=0.0, gamma_M0=1.0, gamma_M1=1.1)
    check("gedrungener Steg bekommt keinen Beulnachweis",
          not any("Schubbeulen" in k for k in r2["checks"]))


def _blechfeld(a=2.0, b=1.0, t=0.008, nx=8, ny=4, druck=200e3, schub=0.0):
    m = Model("Blechfeld")
    m.add_material(Material.steel("S355"))
    m.add_shell_prop(ShellProp("t", t))
    ids = {}
    for j in range(ny + 1):
        for i in range(nx + 1):
            ids[(i, j)] = m.add_node(a * i / nx, 0.0, b * j / ny)
    els = []
    for j in range(ny):
        for i in range(nx):
            els.append(m.add_element("shell4", [ids[(i, j)], ids[(i + 1, j)],
                                                ids[(i + 1, j + 1)], ids[(i, j + 1)]],
                                     "S355", "t"))
    for j in range(ny + 1):
        m.fix(ids[(0, j)], "all")
    for j in range(ny + 1):
        m.load_node(ids[(nx, j)], Fx=-druck / (ny + 1), Fz=schub / (ny + 1))
    return m, els, ids


def test_beulfeld_im_modell():
    m, els, _ids = _blechfeld()
    bf = m.add_beulfeld("F1", els)
    check("Beulfeld wird zum Modellobjekt",
          bf.name == "F1" and len(bf.elemente) == len(els), bf.bezug())
    d = Model.from_dict(m.to_dict())
    check("Beulfeld übersteht Speichern und Laden",
          list(d.beulfelder) == ["F1"] and d.beulfelder["F1"].elemente == bf.elemente)
    check("und die Modellkopie", m.copy().beulfelder["F1"].rand == "beidseitig")
    try:
        m.add_beulfeld("X", [])
        check("leeres Beulfeld wird abgewiesen", False)
    except ValueError:
        check("leeres Beulfeld wird abgewiesen", True)

    an = solver.solve_all(m, combinations=False, envelopes=False, design=True)
    check("Beulnachweise laufen mit der Berechnung",
          an.beulen is not None and "F1" in an.beulen.felder)
    c = an.beulen.felder["F1"]
    close("a aus der Geometrie", c.a, 2.0, 1e-6, " m")
    close("b aus der Geometrie", c.b, 1.0, 1e-6, " m")
    close("t aus der Schalendicke", c.t, 0.008, 1e-12, " m")
    w = c.werte
    close("σ_E des Feldes", w["sigma_E"], B.sigma_E(0.008, 1.0), 1e-12, " Pa")
    close("σ_cr,x = k_σ σ_E", w["sigma_cr_x"], w["k_sigma_x"] * w["sigma_E"], 1e-12)
    close("λ̄_p = √(α_ult,k/α_cr)", w["lambda_p"],
          math.sqrt(w["alpha_ult_k"] / w["alpha_cr"]), 1e-12)
    check("Druck wird positiv gezählt", w["sigma_x"] > 0,
          f"σ_x = {w['sigma_x'] / 1e6:.1f} MPa")
    soll = 200e3 / (1.0 * 0.008)
    close("σ_x trifft die Handrechnung N/(b t)", w["sigma_x"], soll, 0.15, " Pa")

    # dickeres Blech beult weniger
    m2, els2, _ = _blechfeld(t=0.020)
    m2.add_beulfeld("F1", els2)
    an2 = solver.solve_all(m2, combinations=False, envelopes=False, design=True)
    c2 = an2.beulen.felder["F1"]
    check("das dickere Blech ist gedrungener",
          c2.werte["lambda_p"] < w["lambda_p"],
          f"λ̄_p {c2.werte['lambda_p']:.3f} < {w['lambda_p']:.3f}")
    check("und weniger ausgenutzt", c2.util < c.util,
          f"{c2.util:.3f} < {c.util:.3f}")


def test_reduzierte_spannungen_gegen_handrechnung():
    a, b, t, fy = 3.0, 1.0, 0.010, 355e6
    sx = 100e6
    r = B.beulfeld(a=a, b=b, t=t, fy=fy, sx=sx, gamma_M1=1.1)
    sE = B.sigma_E(t, b)
    close("σ_E", r["sigma_E"], sE, 1e-12, " Pa")
    close("k_σ,x für ψ = 1", r["k_sigma_x"], 4.0, 1e-12)
    close("α_cr = σ_cr/σ_x bei reinem Druck", r["alpha_cr"], 4.0 * sE / sx, 1e-9)
    close("α_ult,k = f_y/σ_x bei einachsigem Druck", r["alpha_ult_k"], fy / sx, 1e-9)
    lam = math.sqrt(fy / (4.0 * sE))
    close("λ̄_p", r["lambda_p"], lam, 1e-9)
    close("ρ_x", r["rho_x"], B.rho_platte(lam, 1.0), 1e-12)
    close("η nach Gl. (10.5) = σ_x/(ρ f_y/γ_M1)", r["eta_interaktion"],
          sx / (B.rho_platte(lam, 1.0) * fy / 1.1), 1e-9)
    check("die Vereinfachung 10.5(2) liegt nicht darunter",
          r["eta_rho_min"] >= r["eta_interaktion"] - 1e-9,
          f"{r['eta_rho_min']:.4f} ≥ {r['eta_interaktion']:.4f}")

    # reiner Schub
    tau = 60e6
    r2 = B.beulfeld(a=a, b=b, t=t, fy=fy, tau=tau, gamma_M1=1.1)
    close("α_cr = τ_cr/τ bei reinem Schub", r2["alpha_cr"],
          B.k_tau(a / b) * sE / tau, 1e-9)
    close("α_ult,k = f_y/(√3 τ)", r2["alpha_ult_k"], fy / (math.sqrt(3) * tau), 1e-9)
    close("η bei reinem Schub = √3 τ/(χ_w f_y/γ_M1)", r2["eta_interaktion"],
          math.sqrt(3) * tau / (r2["chi_w"] * fy / 1.1), 1e-9)

    # gedrungenes Feld: kein Beulen
    r3 = B.beulfeld(a=1.0, b=0.30, t=0.030, fy=fy, sx=100e6)
    check("gedrungenes Feld beult nicht", r3["rho_x"] == 1.0 and r3["lambda_p"] < 0.673,
          f"λ̄_p = {r3['lambda_p']:.3f}")
    check("und wird als solches benannt",
          any("beult nicht" in h for h in r3["hinweise"]), str(r3["hinweise"])[:60])


# --------------------------------------------------------------------------
def test_shell4_spannungen():
    """Die beiden Dreiecke eines Vierecks haben verschiedene lokale Systeme.

    Frueher wurden ihre Schnittgroessen ohne Drehung gemittelt - das Ergebnis
    war von der Knotenreihenfolge abhaengig und im Betrag falsch.
    """
    from statik3d.elements import shell as sh

    # Der Drehsatz selbst
    v = np.array([100e6, 0.0, 0.0])
    close("Tensor um 90° gedreht", float(sh.dreh_tensor(v, math.pi / 2)[1]), 100e6,
          1e-9, " Pa")
    close("Tensor um 45°: reiner Schub", float(sh.dreh_tensor(v, math.pi / 4)[2]),
          -50e6, 1e-9, " Pa")
    check("zweimal drehen hebt sich auf",
          np.allclose(sh.dreh_tensor(sh.dreh_tensor(v, 0.7), -0.7), v))

    def scheibe(nx, ny, versatz=0):
        """Scheibe unter einachsigem Zug, statisch bestimmt gelagert."""
        a, b, t, N = 2.0, 1.0, 0.010, 100e3
        m = Model("S")
        m.add_material(Material.steel("S355"))
        m.add_shell_prop(ShellProp("t", t))
        ids = {}
        for j in range(ny + 1):
            for i in range(nx + 1):
                ids[(i, j)] = m.add_node(a * i / nx, b * j / ny, 0.0)
        els = []
        for j in range(ny):
            for i in range(nx):
                ecken = [ids[(i, j)], ids[(i + 1, j)], ids[(i + 1, j + 1)],
                         ids[(i, j + 1)]]
                ecken = ecken[versatz:] + ecken[:versatz]      # andere Startecke
                els.append(m.add_element("shell4", ecken, "S355", "t"))
        for j in range(ny + 1):
            m.fix(ids[(0, j)], [0, 2, 3, 4, 5])
        m.fix(ids[(0, 0)], [1])
        for j in range(ny + 1):
            m.load_node(ids[(nx, j)], Fx=N / ny * (0.5 if j in (0, ny) else 1.0))
        an = solver.solve_all(m, combinations=False, envelopes=False)
        res = an.cases[m.active_case]
        i = els[len(els) // 2]
        n = res.shell_stress[i]["n"] / t
        return 0.5 * (n[0] + n[1]) + math.hypot(0.5 * (n[0] - n[1]), n[2])

    soll = 100e3 / (1.0 * 0.010)
    for nx, ny in ((4, 2), (8, 4), (16, 8)):
        close(f"Scheibe {nx}×{ny}: konstanter Spannungszustand exakt",
              scheibe(nx, ny), soll, 1e-9, " Pa")
    werte = [scheibe(8, 4, v) for v in range(4)]
    check("das Ergebnis hängt nicht von der Startecke ab",
          max(werte) - min(werte) < 1e-3,
          f"{[round(x / 1e6, 4) for x in werte]} MPa")


def test_steifen():
    from statik3d.ec3.beulen import Steife

    kw = dict(a=3.0, b=1.5, t=0.008, fy=355e6, sx=250e6, tau=50e6, gamma_M1=1.1)
    ohne = B.beulfeld(**kw)
    st = Steife("laengs", lage=0.75, A_sl=0.001, I_sl=1.2e-6, I_T=3.3e-9,
                I_p=8.0e-6, name="L1")
    mit = B.beulfeld(**kw, steifen=[st])
    check("die Längssteife erhöht die Beulspannung",
          mit["sigma_cr_x"] > 3 * ohne["sigma_cr_x"],
          f"{mit['sigma_cr_x'] / 1e6:.1f} statt {ohne['sigma_cr_x'] / 1e6:.1f} MPa")
    check("und senkt die Ausnutzung",
          mit["eta_interaktion"] < ohne["eta_interaktion"],
          f"{mit['eta_interaktion']:.3f} < {ohne['eta_interaktion']:.3f}")
    check("eine Steife führt über A.2.2, nicht A.1",
          "A.2.2" in mit["k_sigma_p"]["verfahren"], mit["k_sigma_p"]["verfahren"])
    check("σ_cr,p ≥ σ_cr,c (sonst wäre das Modell widersprüchlich)",
          mit["sigma_cr_x"] >= mit["sigma_cr_c"],
          f"{mit['sigma_cr_x'] / 1e6:.1f} ≥ {mit['sigma_cr_c'] / 1e6:.1f} MPa")
    check("ξ liegt zwischen 0 und 1", 0.0 <= mit["xi"] <= 1.0, f"ξ = {mit['xi']:.3f}")
    check("ρ_c liegt zwischen χ_c und ρ",
          mit["chi_c"] <= mit["rho_x"] <= mit["rho_platte"] + 1e-12,
          f"{mit['chi_c']:.3f} ≤ {mit['rho_x']:.3f} ≤ {mit['rho_platte']:.3f}")

    # A.2.2 gegen die Formel
    d = B.sigma_cr_sl_A22(3.0, 1.5, 0.008, st, 355e6)
    A1 = st.flaeche_mit_blech(0.008, 355e6)
    soll_ac = 4.33 * (st.I_sl * 0.75 ** 2 * 0.75 ** 2 / (0.008 ** 3 * 1.5)) ** 0.25
    close("Grenzlänge a_c nach A.2.2", d["a_c"], soll_ac, 1e-12, " m")
    euler = math.pi ** 2 * B.E_STAHL * st.I_sl / (A1 * 3.0 ** 2)
    bett = (B.E_STAHL * 0.008 ** 3 * 1.5 * 9.0
            / (4 * math.pi ** 2 * (1 - 0.3 ** 2) * A1 * 0.75 ** 2 * 0.75 ** 2))
    close("σ_cr,sl im Zweig a < a_c", d["sigma_cr_sl"], euler + bett, 1e-9, " Pa")
    lang = B.sigma_cr_sl_A22(6.0, 1.5, 0.008, st, 355e6)
    close("σ_cr,sl im Zweig a ≥ a_c", lang["sigma_cr_sl"],
          1.05 * B.E_STAHL * math.sqrt(st.I_sl * 0.008 ** 3 * 1.5) / (A1 * 0.75 * 0.75),
          1e-9, " Pa")
    check("der lange Zweig greift ab a_c", lang["zweig"] == "a ≥ a_c")

    # A.1 ab drei Steifen
    drei = [Steife("laengs", lage=0.375 * k, A_sl=0.001, I_sl=1.2e-6)
            for k in (1, 2, 3)]
    d3 = B.sigma_cr_p(3.0, 1.5, 0.008, drei, 1.0, 355e6)
    check("ab drei Steifen gilt A.1", "A.1" in d3["verfahren"], d3["verfahren"])
    I_p = 1.5 * 0.008 ** 3 / (12 * (1 - 0.3 ** 2))
    close("γ = ΣI_sl / I_p", d3["gamma"], 3 * 1.2e-6 / I_p, 1e-12)
    close("δ = ΣA_sl / (b t)", d3["delta"], 3 * 0.001 / (1.5 * 0.008), 1e-12)

    # k_tau,st nach A.3(2)
    kst = B.k_tau_st(3.0, 1.5, 0.008, [st])
    w1 = 9.0 * (1.5 / 3.0) ** 2 * ((st.I_sl / (0.008 ** 3 * 1.5)) ** 3) ** 0.25
    w2 = (2.1 / 0.008) * (st.I_sl / 1.5) ** (1.0 / 3.0)
    close("k_τ,st = max der beiden Formeln", kst, max(w1, w2), 1e-12)
    check("k_τ wächst durch die Steife", mit["k_tau"] > ohne["k_tau"],
          f"{mit['k_tau']:.2f} > {ohne['k_tau']:.2f}")

    # Nachweise der Steifen (Abschnitt 9)
    d = B.steife_drillknicken(st, 355e6)
    close("Grenze I_T/I_p = 5,3 f_y/E", d["grenze"], 5.3 * 355e6 / B.E_STAHL, 1e-12)
    check("die flache Steife fällt beim Drillknicken durch", not d["ok"])
    dick = B.Steife("laengs", I_T=1e-4, I_p=1e-3)
    check("eine drillsteife Steife besteht", B.steife_drillknicken(dick, 355e6)["ok"])
    ohne_it = B.steife_drillknicken(B.Steife("laengs"), 355e6)
    check("ohne I_T wird das gesagt, nicht geraten",
          not ohne_it["gefuehrt"] and "gesondert" in ohne_it["hinweis"])
    q = B.quersteife_starr(2.0e-6, 1.5, 0.008, 1.5)
    close("Mindeststeifigkeit a/h_w < √2", q["I_noetig"],
          1.5 * 1.5 ** 3 * 0.008 ** 3 / 1.5 ** 2, 1e-12, " m^4")
    q2 = B.quersteife_starr(2.0e-6, 1.5, 0.008, 3.0)
    close("Mindeststeifigkeit a/h_w ≥ √2", q2["I_noetig"],
          0.75 * 1.5 * 0.008 ** 3, 1e-12, " m^4")


def test_lasteinleitung():
    hw, tw, tf, bf, fy = 1.200, 0.008, 0.020, 0.400, 355e6
    close("k_F Typ a", B.k_F("a", hw, a=1.5), 6.0 + 2.0 * (hw / 1.5) ** 2, 1e-12)
    close("k_F Typ b", B.k_F("b", hw, a=1.5), 3.5 + 2.0 * (hw / 1.5) ** 2, 1e-12)
    close("k_F Typ c", B.k_F("c", hw, s_s=0.2, c=0.05),
          2.0 + 6.0 * 0.25 / hw, 1e-12)
    check("k_F Typ c ist auf 6 begrenzt",
          B.k_F("c", 0.3, s_s=1.0, c=0.5) == 6.0)

    r = B.lasteinleitung(400e3, hw, tw, tf, bf, fy, art="a", s_s=0.200, a=1.5,
                         gamma_M1=1.1)
    close("F_cr = 0,9 k_F E t_w³/h_w", r["F_cr"],
          0.9 * r["k_F"] * B.E_STAHL * tw ** 3 / hw, 1e-12, " N")
    close("m_1 = f_yf b_f/(f_yw t_w)", r["m_1"], bf / tw, 1e-12)
    close("m_2 = 0,02 (h_w/t_f)²", r["m_2"], 0.02 * (hw / tf) ** 2, 1e-12)
    close("ℓ_y = s_s + 2 t_f (1 + √(m_1+m_2))", r["l_y"],
          0.200 + 2 * tf * (1 + math.sqrt(r["m_1"] + r["m_2"])), 1e-12, " m")
    close("λ̄_F = √(ℓ_y t_w f_yw/F_cr)", r["lambda_F"],
          math.sqrt(r["l_y"] * tw * fy / r["F_cr"]), 1e-12)
    close("χ_F = 0,5/λ̄_F", r["chi_F"], min(0.5 / r["lambda_F"], 1.0), 1e-12)
    close("F_Rd = f_yw χ_F ℓ_y t_w/γ_M1", r["F_Rd"],
          fy * r["chi_F"] * r["l_y"] * tw / 1.1, 1e-9, " N")
    check("Typ a trägt mehr als Typ b",
          r["F_Rd"] > B.lasteinleitung(400e3, hw, tw, tf, bf, fy, art="b",
                                       s_s=0.200, a=1.5)["F_Rd"])
    check("Typ c am freien Trägerende trägt am wenigsten",
          B.lasteinleitung(400e3, hw, tw, tf, bf, fy, art="c", s_s=0.200,
                           c=0.05)["F_Rd"] < r["F_Rd"])
    gedrungen = B.lasteinleitung(400e3, 0.300, 0.020, tf, bf, fy, art="a", s_s=0.2)
    check("gedrungener Steg: χ_F = 1, kein Beulen", gedrungen["chi_F"] == 1.0,
          f"λ̄_F = {gedrungen['lambda_F']:.3f}")
    i = B.lasteinleitung_interaktion(0.9, 0.7)
    close("Interaktion 7.2: η_2 + 0,8 η_1", i["wert"], 0.9 + 0.8 * 0.7, 1e-12)
    check("Grenze der Interaktion ist 1,4", i["grenze"] == 1.4 and not i["ok"])

    # im Modell
    from statik3d import examples_lib
    m = examples_lib.build_example("hall")
    r_ = m.members["Riegel"]
    kn = int(m.elements[r_.elements[len(r_.elements) // 2]].nodes[0])
    m.load_node(kn, Fz=-300e3)
    m.add_lasteinleitung("Radlast", kn, stab="Riegel", typ="b", s_s=0.200, a=1.5)
    an = solver.solve_all(m, design=True)
    check("Lasteinleitung läuft mit der Berechnung",
          an.lasteinleitung is not None and "Radlast" in an.lasteinleitung.stellen)
    c = an.lasteinleitung.stellen["Radlast"]
    check("die Kraft kommt aus der Kombination", c.F_Ed > 300e3,
          f"F_Ed = {c.F_Ed / 1e3:.0f} kN in {c.kombination}")
    check("jede Kombination wird geführt",
          len(c.je_kombination) == len(an.lasteinleitung.kombinationen),
          f"{len(c.je_kombination)}")
    beste = max(c.je_kombination, key=lambda d: d["eta"])
    check("die ungünstigste ist maßgebend", abs(beste["eta"] - c.util) < 1e-12)
    # Interaktion mit der Biegung nach 7.2(1)
    ia = c.interaktion
    check("die Interaktion 7.2 wird geführt", bool(ia), str(ia.get("text", ""))[:60])
    close("η_2 + 0,8 η_1 aus den Einzelwerten", ia["wert"],
          ia["eta_2"] + 0.8 * ia["eta_1"], 1e-12)
    check("die Interaktion ist die ungünstigste über alle Kombinationen",
          abs(max(d["eta_72"] for d in c.je_kombination) - ia["wert"]) < 1e-12)
    # η_1 gegen die Handrechnung am Nachweisort
    sec = m.sections[m.elements[r_.elements[0]].sec]
    fy_ = m.materials[m.elements[r_.elements[0]].mat].yield_strength(sec.t_max)
    res = an.combinations[ia["kombination"]]
    mf = res.member_forces(r_, m.design.stations)
    import numpy as _np
    p_kn = _np.asarray(m.nodes[kn], dtype=float)
    p_0 = _np.asarray(m.nodes[int(m.elements[r_.elements[0]].nodes[0])], dtype=float)
    j = int(_np.argmin(_np.abs(_np.asarray(mf["x"]) - float(_np.linalg.norm(p_kn - p_0)))))
    soll = (abs(float(mf["N"][j])) / (sec.A * fy_ / m.design.gamma_M0)
            + abs(float(mf["My"][j])) / (sec.Wel_y * fy_ / m.design.gamma_M0))
    close("η_1 = N/(A f_y/γ_M0) + M/(W_el f_y/γ_M0)", ia["eta_1"], soll, 1e-9)
    check("die Interaktion geht in den Status ein",
          (c.status() == "erfüllt") == (c.util <= 1.0 and ia["ok"]),
          f"η_2 = {c.util:.3f}, η_2+0,8η_1 = {ia['wert']:.3f}, {c.status()}")

    m.add_lasteinleitung("Auflager", int(m.elements[
        m.members["Stiel links"].elements[0]].nodes[0]), stab="Stiel links",
        quelle="auflager", typ="c", s_s=0.150, c=0.05)
    an2 = solver.solve_all(m, design=True)
    check("die Auflagerkraft wird als Quelle erkannt",
          an2.lasteinleitung.stellen["Auflager"].F_Ed > 0,
          f"{an2.lasteinleitung.stellen['Auflager'].F_Ed / 1e3:.0f} kN")


def test_schalenbeulen():
    from statik3d.ec3 import schalenbeulen as S
    r, t, l, fy = 0.5, 0.010, 4.0, 355e6
    close("ω = l/√(r t)", S.omega(l, r, t), l / math.sqrt(r * t), 1e-12)
    check("Längenbereiche werden unterschieden",
          (S.laengenbereich(0.1, r, t) == "kurz"
           and S.laengenbereich(1.0, r, t) == "mittel"
           and S.laengenbereich(20.0, r, t) == "lang"),
          f"{S.laengenbereich(0.1, r, t)}/{S.laengenbereich(1.0, r, t)}/"
          f"{S.laengenbereich(20.0, r, t)}")
    d = S.sigma_x_Rcr(1.0, r, t)
    close("σ_x,Rcr = 0,605 E C_x t/r (mittellang, C_x = 1)", d["sigma_Rcr"],
          0.605 * S.E_STAHL * t / r, 1e-12, " Pa")
    a = S.alpha_x(r, t, "B")
    close("Δw_k = (1/Q)√(r/t) t", a["Delta_wk"], (1 / 25.0) * math.sqrt(r / t) * t,
          1e-12, " m")
    close("α_x = 0,62/(1+1,91 (Δw_k/t)^1,44)", a["alpha"],
          0.62 / (1 + 1.91 * (a["Delta_wk"] / t) ** 1.44), 1e-12)
    check("bessere Herstelltoleranz gibt größeres α",
          S.alpha_x(r, t, "A")["alpha"] > S.alpha_x(r, t, "B")["alpha"]
          > S.alpha_x(r, t, "C")["alpha"])

    c1 = S.chi_schale(0.1, 0.5)
    check("χ = 1 unterhalb λ̄_0", c1["chi"] == 1.0)
    lam_p = math.sqrt(0.5 / 0.4)
    c2 = S.chi_schale(lam_p + 0.5, 0.5)
    close("χ = α/λ̄² im elastischen Bereich", c2["chi"], 0.5 / (lam_p + 0.5) ** 2,
          1e-12)
    c3 = S.chi_schale(0.5 * (0.2 + lam_p), 0.5)
    check("dazwischen liegt χ zwischen beiden Ästen", 0 < c3["chi"] < 1.0,
          f"χ = {c3['chi']:.3f}")

    z = S.zylinder(r=r, t=t, l=l, fy=fy, sigma_x=120e6, klasse="B")
    me = z.werte["meridian"]
    close("λ̄ = √(f_y/σ_Rcr)", me["lambda"], math.sqrt(fy / me["sigma_Rcr"]), 1e-12)
    close("σ_Rd = χ f_y/γ_M1", me["sigma_Rd"], me["chi"] * fy / 1.1, 1e-12, " Pa")
    close("Ausnutzung bei reinem Meridiandruck", z.util,
          (120e6 / me["sigma_Rd"]) ** (1.25 + 0.75 * me["chi"]), 1e-9)
    check("Zug beult nicht",
          S.zylinder(r=r, t=t, l=l, fy=fy, sigma_x=-200e6).util == 0.0)
    check("der lange Zylinder wird benannt",
          any("Langer Zylinder" in h for h in z.hinweise), str(z.hinweise)[:60])
    dick = S.zylinder(r=0.1, t=0.020, l=1.0, fy=fy, sigma_x=100e6)
    check("die dickwandige Schale wird benannt",
          any("dickwandig" in h for h in dick.hinweise), str(dick.hinweise)[:60])


def test_zylinder_im_modell():
    m = Model("Rohr")
    m.add_material(Material.steel("S355"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    r, l, nu_, nz = 0.5, 3.0, 24, 6
    ids = {}
    for k in range(nz + 1):
        for j in range(nu_):
            a = 2 * math.pi * j / nu_
            ids[(j, k)] = m.add_node(r * math.cos(a), r * math.sin(a), l * k / nz)
    els = []
    for k in range(nz):
        for j in range(nu_):
            j2 = (j + 1) % nu_
            els.append(m.add_element("shell4", [ids[(j, k)], ids[(j2, k)],
                                                ids[(j2, k + 1)], ids[(j, k + 1)]],
                                     "S355", "t10"))
    for j in range(nu_):
        m.fix(ids[(j, 0)], "all")
    N = 1500e3
    for j in range(nu_):
        m.load_node(ids[(j, nz)], Fz=-N / nu_)
    m.add_beulfeld("Mantel", els, art="zylinder", qualitaet="B")
    an = solver.solve_all(m, combinations=False, envelopes=False, design=True)
    c = an.beulen.felder["Mantel"]
    w = c.werte
    close("Radius aus der Geometrie", w["r"], r, 1e-9, " m")
    close("Beullänge aus der Geometrie", w["l"], l, 1e-9, " m")
    umfang = nu_ * 2 * r * math.sin(math.pi / nu_)      # Vieleck statt Kreis
    close("Meridianspannung trifft N/(U t)", w["sigma_x"], N / (umfang * 0.010),
          2e-3, " Pa")
    check("die Schalenwerte stehen im Ergebnis", "zylinder" in w
          and w["zylinder"]["meridian"]["chi"] > 0)
    check("Umfangsspannung bleibt klein", w["sigma_z"] < 0.25 * w["sigma_x"],
          f"{w['sigma_z'] / 1e6:.1f} gegen {w['sigma_x'] / 1e6:.1f} MPa")


def test_bericht():
    from statik3d.report import Report
    m, els, _ids = _blechfeld()
    m.add_beulfeld("Stegfeld", els, beschreibung="Steg zwischen den Quersteifen")
    an = solver.solve_all(m, combinations=False, envelopes=False, design=True)
    html = Report(m, an).html()
    for text in ("Beulnachweise nach DIN EN 1993-1-5", "Stegfeld",
                 "reduzierten Spannungen", "α_ult,k", "α_cr", "λ̄_p",
                 "Bezugsspannung", "max. Ausnutzung Beulen"):
        check(f"Bericht nennt „{text}“", text in html)
    check("der alte Ausschluss ist weg",
          "Schubbeulen nach DIN EN 1993-1-5 wird nur angezeigt" not in html)
    check("Zusammenfassung nennt das Beulen", "Beulen (EN 1993-1-5)" in an.summary())

    # versteiftes Feld, Zylinder und Lasteinleitung im Bericht
    from statik3d.model import Beulsteife
    from statik3d import examples_lib
    m2, els2, _ids = _blechfeld()
    m2.add_beulfeld("Versteift", els2, steifen=[
        Beulsteife("laengs", lage=0.5, A_sl=0.001, I_sl=1.2e-6, I_T=3.3e-9,
                   I_p=8.0e-6, name="L1"),
        Beulsteife("quer", lage=1.0, I_sl=2.0e-6, name="Q1")])
    an2 = solver.solve_all(m2, combinations=False, envelopes=False, design=True)
    h2 = Report(m2, an2).html()
    for text in ("Steifen des Feldes", "Längsversteifung", "Nachweise der Steifen",
                 "A.2.2", "Knickstab", "Drillknicken", "Mindeststeifigkeit"):
        check(f"Bericht nennt „{text}“", text in h2)

    # Zylinder: der Bericht darf keine Plattenkennwerte zeigen
    mz = Model("Rohr")
    mz.add_material(Material.steel("S355"))
    mz.add_shell_prop(ShellProp("t8", 0.008))
    nu_, nz, rr, ll = 24, 6, 0.5, 3.0
    idz = {}
    for k in range(nz + 1):
        for j in range(nu_):
            w_ = 2 * math.pi * j / nu_
            idz[(j, k)] = mz.add_node(rr * math.cos(w_), rr * math.sin(w_), ll * k / nz)
    elz = []
    for k in range(nz):
        for j in range(nu_):
            j2 = (j + 1) % nu_
            elz.append(mz.add_element("shell4", [idz[(j, k)], idz[(j2, k)],
                                                 idz[(j2, k + 1)], idz[(j, k + 1)]],
                                      "S355", "t8"))
    for j in range(nu_):
        mz.fix(idz[(j, 0)], "all")
        mz.load_node(idz[(j, nz)], Fz=-1200e3 / nu_)
    mz.add_beulfeld("Mantel", elz, art="zylinder", qualitaet="B")
    anz = solver.solve_all(mz, combinations=False, envelopes=False, design=True)
    hz = Report(mz, anz).html()
    for text in ("Beulnachweise nach DIN EN 1993-1-5 und DIN EN 1993-1-6",
                 "Zylinderschale Mantel", "Zylinderschalen: Spannungen",
                 "Ausnutzung nach 8.5.3(3)", "Herstelltoleranz"):
        check(f"Zylinderbericht nennt „{text}“", text in hz)
    kap = hz.split('id="k6"')[1].split('id="k7"')[0]
    for text in ("Bezugsspannung σ_E", "α_ult,k (Gl. 10.3)", "Methode der reduzierten",
                 "Lagerung", "Blechfelder: Spannungen"):
        check(f"Kapitel 6 zeigt „{text}“ nicht", text not in kap)
    check("auch das Rechenverfahren nennt keine Blechfelder",
          "Blechfelder nach DIN EN 1993-1-5" not in hz)

    m3 = examples_lib.build_example("hall")
    r3 = m3.members["Riegel"]
    kn = int(m3.elements[r3.elements[len(r3.elements) // 2]].nodes[0])
    m3.load_node(kn, Fz=-300e3)
    m3.add_lasteinleitung("Radlast", kn, stab="Riegel", typ="b", s_s=0.2, a=1.5)
    an3 = solver.solve_all(m3, design=True)
    h3 = Report(m3, an3).html()
    for text in ("Lasteinleitung (Abschnitt 6)", "Radlast", "wirksame Lastlänge",
                 "λ̄_F", "max. Ausnutzung Lasteinleitung"):
        check(f"Bericht nennt „{text}“", text in h3)
    check("Zusammenfassung nennt die Lasteinleitung",
          "Lasteinleitung (EN 1993-1-5, 6)" in an3.summary())


def main():
    print("=" * 92)
    print("STATIK3D - Verifikation Plattenbeulen (DIN EN 1993-1-5)")
    print("=" * 92)
    for t in (test_beulwerte, test_abminderung, test_schubbeulen,
              test_stabnachweis_fuehrt_schubbeulen, test_beulfeld_im_modell,
              test_reduzierte_spannungen_gegen_handrechnung, test_shell4_spannungen,
              test_steifen, test_lasteinleitung, test_schalenbeulen,
              test_zylinder_im_modell, test_bericht):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 92)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
