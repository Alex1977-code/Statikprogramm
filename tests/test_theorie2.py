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

und die Handbuchsaetze zu Ergebniskombinationen bei "automatisch" gegen die
Rechnung (Zweigelenkrahmen, Stauwand): laufen Rechnung und Satz auseinander,
schlaegt die Pruefung fehl.

Aufruf:  python -m tests.test_theorie2
"""
import math
import os
import re
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


# --------------------------------------------------------------------------
# Handbuchsaetze gegen die Rechnung (Befund B139, 23.09.2026). Bis dahin lag
# die Pruefung dieser Absaetze nur im Scratchpad und suchte nur Zeichenketten;
# die Zahlen des heutigen Standes (α_cr 18,1 bis 25,8, Stiel links 0,5423,
# Stielkopf 102,14 mm, drei Stellungen) pruefte niemand. Hier werden sie
# nachgerechnet - gemessen am 23.09.2026 an ec6448c: α_cr der Alternativen
# 18,0916 bis 25,8131, Stiel links 0,542323, Stielkopf 102,141489 mm, gleich
# mit Skript und mit dieser Pruefung. Aussagen ueber den Stand vor der
# Aenderung (54b6f9a, 22.09.2026) und ueber die nicht ausgelieferte
# Zwischenfassung (9337a3c) sind im Repo nicht nachzurechnen; sie muessen
# darum den Stand nennen, an dem sie gemessen wurden.

_DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
_ZAHLWORT = {"eine": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6}
# Die vier GZT-Kombinationen des Zweigelenkrahmens
_RAHMEN_GZT = {"K1": {"G": 1.35, "Q": 1.5}, "K2": {"G": 1.35, "W": 1.5},
               "K3": {"G": 1.35, "Q": 1.5, "W": 0.9}, "K4": {"G": 1.0, "W": 1.5}}


def _absatz(datei: str, merkmal: str) -> str:
    """Der Absatz aus docs/<datei>, der ``merkmal`` enthaelt, Leerraum zu
    einem Leerzeichen zusammengezogen; "" wenn es keinen gibt."""
    with open(os.path.join(_DOCS, datei), encoding="utf-8") as f:
        text = f.read()
    for a in re.split(r"\n\s*\n", text):
        a = " ".join(a.split())
        if merkmal in a:
            return a
    return ""


def _wie_im_text(text_zahl, wert: float) -> bool:
    """Gerundet auf die Stellen, die der Handbuchsatz nennt, gleich?"""
    if not text_zahl:
        return False
    stellen = len(text_zahl.split(",", 1)[1]) if "," in text_zahl else 0
    return f"{wert:.{stellen}f}".replace(".", ",") == text_zahl


def _gruppe(muster: str, text: str):
    t = re.search(muster, text)
    return t.group(1) if t else None


def _zweigelenkrahmen(ergebniskombination: bool):
    """Verschieblicher Zweigelenkrahmen der Handbuchsaetze: Stiele HEB 200,
    5 m, Riegel IPE 300, 8 m; G 8 kN/m und Q 0,5 kN/m auf dem Riegel, W 25 kN
    am linken Stielkopf; W auf Theorie II. Ordnung, theorie2 "automatisch".
    Die vier GZT-Kombinationen gewoehnlich oder als eine Ergebniskombination
    "EK" mit vier Alternativen (Aufbau der Gegenpruefung vom 23.09.2026)."""
    from statik3d import mesher
    from statik3d.model import Section, Combination
    m = Model("Rahmen")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("HEB 200"))
    m.add_section(Section.from_profile("IPE 300"))
    mesher.line_of_beams(m, "S235", "HEB 200", (0, 0, 0), (0, 0, 5.0), 5)
    ne = len(m.elements)
    mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 5.0), (8.0, 0, 5.0), 8)
    nr = len(m.elements)
    mesher.line_of_beams(m, "S235", "HEB 200", (8.0, 0, 5.0), (8.0, 0, 0), 5)
    mesher.merge_nodes(m)
    m.add_member("StielL", list(range(0, ne)))
    m.add_member("Riegel", list(range(ne, nr)))
    m.add_member("StielR", list(range(nr, len(m.elements))))
    for i in range(m.nn):
        if abs(m.nodes[i][2]) < 1e-9:
            m.fix(i, [0, 1, 2, 3, 5])      # Fussgelenk: Drehung um y frei
    kopf = [i for i in range(m.nn) if abs(m.nodes[i][2] - 5.0) < 1e-9]
    for i in kopf:
        m.fix(i, [1])                      # aus der Ebene gehalten
    for lf in ("G", "Q", "W"):
        m.add_load_case(lf, lf)
    for e in range(ne, nr):
        m.load_beam(e, qz=-8e3, case="G")
        m.load_beam(e, qz=-0.5e3, case="Q")
    kl = min(kopf, key=lambda i: m.nodes[i][0])
    m.load_node(kl, Fx=25e3, case="W")
    m.load_cases["W"].theorie = "II"
    m.design.theorie2 = "auto"
    if ergebniskombination:
        m.combinations["EK"] = Combination(
            "EK", {}, "ULS", alternativen=[dict(f) for f in _RAHMEN_GZT.values()])
    else:
        for n, f in _RAHMEN_GZT.items():
            m.combinations[n] = Combination(n, dict(f), "ULS")
    return m, kl


def test_handbuch_zweigelenkrahmen():
    """Benutzerhandbuch (Theorie II. Ordnung, Alternative bei I. Ordnung) und
    Theoriehandbuch (Kombinationen mit Alternativen) nennen Zahlen des
    Zweigelenkrahmens. Die des heutigen Standes werden nachgerechnet."""
    A = _absatz("Benutzerhandbuch.md",
                "mit α_cr an oder über der Grenze bleibt eine Alternative")
    B = _absatz("Theoriehandbuch.md", "Bleibt eine Alternative bei I. Ordnung")
    check("Handbuchabsätze zum Zweigelenkrahmen gefunden", A and B,
          f"Benutzerhandbuch {len(A)} Zeichen, Theoriehandbuch {len(B)} Zeichen")
    erg = {}
    for v, ek in (("K", False), ("EK", True)):
        m, kl = _zweigelenkrahmen(ek)
        erg[v] = (m, kl, solver.solve_all(m, design=True))
    m, kl, an = erg["EK"]
    _mk, klk, ank = erg["K"]
    check("W ist nach II. Ordnung gerechnet",
          an.cases["W"].info.get("theorie") == "II. Ordnung",
          str(an.cases["W"].info.get("theorie")))
    alt = {z: i for z, i in an.theorie2.kombinationen.items() if z.startswith("EK [")}
    ac = [i.alpha_cr for i in alt.values()]
    check("alle vier Alternativen bleiben bei I. Ordnung (α_cr ≥ 10)",
          len(alt) == 4 and all(not i.gerechnet and i.alpha_cr >= i.grenze
                                for i in alt.values()),
          ", ".join(f"{z} {i.alpha_cr:.2f}" for z, i in alt.items()))
    warn = list(getattr(an.design, "warnungen", None) or [])
    check("und es kommt keine Warnung", not warn, str(warn[:1]))
    kopf = float(an.envelopes["ULS"].u_max[kl, 0]) * 1e3
    kopf_k = float(ank.envelopes["ULS"].u_max[klk, 0]) * 1e3
    eta = {s: mc.util for s, mc in an.design.members.items()}
    eta_k = {s: mc.util for s, mc in ank.design.members.items()}
    check("Stielkopf und Ausnutzungen gleich wie mit den gewöhnlichen Kombinationen",
          abs(kopf - kopf_k) <= 1e-9 * kopf_k
          and all(abs(eta[s] - eta_k[s]) <= 1e-12 for s in eta_k) and set(eta) == set(eta_k),
          f"Stielkopf {kopf:.6f} / {kopf_k:.6f} mm, Stiel links "
          f"{eta.get('StielL', 0):.6f} / {eta_k.get('StielL', 0):.6f}")

    # Benutzerhandbuch: nur gerundete Zahlen des heutigen Standes
    check("BH beschreibt den gerechneten Aufbau",
          "Zweigelenkrahmen mit dem Windlastfall W auf II. Ordnung" in A)
    a1 = _gruppe(r"α_cr der Alternativen (\d+,\d+) bis \d+,\d+\)", A)
    a2 = _gruppe(r"α_cr der Alternativen \d+,\d+ bis (\d+,\d+)\)", A)
    check("BH: α_cr der Alternativen wie gerechnet",
          ac and _wie_im_text(a1, min(ac)) and _wie_im_text(a2, max(ac)),
          f"Text {a1} bis {a2}, gerechnet {min(ac or [0]):.4f} bis {max(ac or [0]):.4f}")
    t = re.search(r"Stielkopf (\d+,\d+) mm und Ausnutzung Stiel links (\d+,\d+), "
                  r"gleich wie mit den gewöhnlichen Kombinationen", A)
    check("BH: Stielkopf wie gerechnet", t and _wie_im_text(t.group(1), kopf),
          f"Text {t and t.group(1)} mm, gerechnet {kopf:.6f} mm")
    check("BH: Ausnutzung Stiel links wie gerechnet",
          t and _wie_im_text(t.group(2), eta.get("StielL", 0.0)),
          f"Text {t and t.group(2)}, gerechnet {eta.get('StielL', 0.0):.6f}")
    check("BH (Rahmen): Aussage über den Stand vor der Änderung nennt den Stand",
          "22.09.2026" not in A or "Stand 54b6f9a" in A,
          _gruppe(r"(Bis zum 22\.09\.2026[^,:]*)", A) or "")

    # Theoriehandbuch: nach "statt" steht der heutige Stand
    check("TH beschreibt den gerechneten Aufbau",
          "Stiele HEB 200, 5 m, Riegel IPE 300, 8 m; G 8 kN/m und Q 0,5 kN/m auf "
          "dem Riegel, W 25 kN am linken Stielkopf" in B)
    k2 = [i + 1 for i, f in enumerate(_RAHMEN_GZT.values()) if f == {"G": 1.35, "W": 1.5}][0]
    a_k2 = alt.get(f"EK [{k2}]")
    t = _gruppe(r"α_cr der Alternative (\d+,\d+)\)", B)
    check("TH: α_cr der Alternative 1,35·G + 1,5·W wie gerechnet",
          a_k2 is not None and _wie_im_text(t, a_k2.alpha_cr),
          f"Text {t}, gerechnet {a_k2.alpha_cr if a_k2 else float('nan'):.4f}")
    for name, muster, wert in (
            ("Stielkopf", r"Stielkopf [\d,]+ statt (\d+,\d+) mm wie die gewöhnliche", kopf),
            ("Stiel links", r"Ausnutzung Stiel links [\d,]+ statt (\d+,\d+)", eta.get("StielL", 0.0)),
            ("Riegel", r"Riegel [\d,]+ statt (\d+,\d+)", eta.get("Riegel", 0.0)),
            ("Stiel rechts", r"Stiel rechts [\d,]+ statt (\d+,\d+)", eta.get("StielR", 0.0)),
            ("Stiel links gegen den Stand vor der Änderung",
             r"Stiel links [\d,]+ aus W statt (\d+,\d+)\.", eta.get("StielL", 0.0))):
        t = _gruppe(muster, B)
        check(f"TH: {name} heute wie gerechnet", _wie_im_text(t, wert),
              f"Text {t}, gerechnet {wert:.6f}")
    check("TH: Aussage über den Stand vor der Änderung nennt den Stand",
          "22.09.2026" not in B or "Stand 54b6f9a" in B,
          _gruppe(r"(Vor dieser Änderung \([^)]*\))", B) or "")
    check("TH: die Zwischenfassung nennt den gemessenen Stand",
          "Zwischenfassung" not in B or "9337a3c" in B,
          _gruppe(r"(Zwischenfassung dieser Änderung \([^)]*\))", B) or "")


def test_handbuch_stauwand():
    """Benutzerhandbuch (Bewegliche Bruecken): eine Stellungsreihe mit
    ``kombinationen=False`` weist nichts nach. Gerechnet wird die Stauwand
    mit den drei Stellungen der Messung am Stand 54b6f9a (0°, 40°, 82°); was
    der Absatz ueber den heutigen Stand sagt, muss die Rechnung zeigen, und
    die Stellungszahl im Satz ueber den Stand vor der Aenderung muss die der
    Rechnung sein."""
    from statik3d.bridges.positions import Stellungsreihe, Stellung
    P = _absatz("Benutzerhandbuch.md",
                "Die Nachweise einer Stellung brauchen die Ergebnisse ihrer Kombinationen.")
    C = _absatz("Benutzerhandbuch.md", "Im Browser zeigt eine Stellung ohne jeden geführten Nachweis")
    check("Handbuchabsätze zu den Stellungen gefunden", P and C,
          f"{len(P)} und {len(C)} Zeichen")
    m = examples_lib.build_example("gate")
    reihe = Stellungsreihe(m, "Stauwand")
    for name, w in (("geschlossen", 0.0), ("Zwischen", 40.0), ("offen", 82.0)):
        reihe.add(Stellung(name, w, f"{w:g} Grad"))
    umh = reihe.rechnen(kombinationen=False, nachweise=True)
    erg = reihe.ergebnisse
    check("BH: `reihe.rechnen(kombinationen=False, nachweise=True)` – keine Stellung `ok`",
          "`reihe.rechnen(kombinationen=False, nachweise=True)`" in P and "nicht `ok`" in P
          and erg and all(not e.ok and e.warnungen for e in erg),
          ", ".join(f"{e.stellung.name}: ok {e.ok}, {len(e.warnungen or [])} Warnungen"
                    for e in erg))
    b = umh.bericht()
    for text, n in (("Umhüllende: eta nicht bestimmt", 1),
                    ("NICHT VOLLSTÄNDIG NACHGEWIESEN", len(erg))):
        check(f"BH und Bericht: „{text}“",
              f"„{text}" in P and b.count(text) >= n, f"{b.count(text)}× im Bericht")
    check("BH und Bericht: Warnungen unter „Nicht nachgewiesen“",
          "Unter „Nicht nachgewiesen\" stehen die Warnungen" in P
          and "\nNicht nachgewiesen:" in b and "WARNUNG: Kombination" in b)
    kurz = umh.kurztext()
    check("BH und Meldung nach dem Rechnen: „eta nicht bestimmt“",
          "(`umh.kurztext()`) sagt es ebenso" in P and "eta nicht bestimmt" in kurz, kurz[:70])
    t = _gruppe(r"\(Stauwand, (\w+) Stellungen:", C)
    check("BH: Stellungszahl der Stauwand wie gerechnet",
          _ZAHLWORT.get(t or "") == len(erg), f"Text „{t}“, gerechnet {len(erg)}")
    check("BH (Stellungen): Aussage über den Stand vor der Änderung nennt den Stand",
          "22.09.2026" not in C or "Stand 54b6f9a" in C,
          _gruppe(r"(Bis zum 22\.09\.2026[^,:]*)", C) or "")


def main():
    print("=" * 92)
    print("STATIK3D - Verifikation Theorie II. Ordnung (DIN EN 1993-1-1, 5.2/5.3)")
    print("=" * 92)
    for t in (test_imperfektionsbeiwerte, test_alpha_cr, test_vergroesserung,
              test_ersatzlasten, test_vorkruemmung, test_im_modell_und_bericht,
              test_handbuch_zweigelenkrahmen, test_handbuch_stauwand):
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
