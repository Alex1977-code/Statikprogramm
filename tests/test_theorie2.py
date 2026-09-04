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


def main():
    print("=" * 92)
    print("STATIK3D - Verifikation Theorie II. Ordnung (DIN EN 1993-1-1, 5.2/5.3)")
    print("=" * 92)
    for t in (test_imperfektionsbeiwerte, test_alpha_cr, test_vergroesserung,
              test_ersatzlasten, test_vorkruemmung, test_im_modell_und_bericht):
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
