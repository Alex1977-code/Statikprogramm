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


def main():
    print("=" * 92)
    print("STATIK3D - Verifikation Plattenbeulen (DIN EN 1993-1-5)")
    print("=" * 92)
    for t in (test_beulwerte, test_abminderung, test_schubbeulen,
              test_stabnachweis_fuehrt_schubbeulen, test_beulfeld_im_modell,
              test_reduzierte_spannungen_gegen_handrechnung, test_bericht):
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
