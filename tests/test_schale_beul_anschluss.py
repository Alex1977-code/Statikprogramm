"""
Drei Befunde vom 11./12.11.2026 (Pruefbericht der zehn Agenten, Abschnitte 2
und 3, dazu ein Nebenfehler im Beulnachweis), vom Anwender zur Behebung
freigegeben.

1. Anschluss ohne Stahlsorte (Befund 2): der Korrelationsbeiwert β_w der
   Kehlnaht haengt nur an der Stahlsorte (EN 1993-1-8 Tab. 4.1). Ohne Sorte
   rechnete der Anschluss still mit S355 (β_w = 0,9) und nannte S355 in der
   Beschreibung. Festlegung des Anwenders: „Ohne angegebenen Werkstoff kein
   Nachweis“ - ein geschweisster Anschluss ohne Sorte wird nicht nachgewiesen,
   die Meldung nennt Sorte, β_w und Werkstoff. Mit Sorte bleibt alles, wie es
   war (Knotenblech S460 f_u 540: f_vw,d = 540/√3/(1,0 · 1,25) = 249,42 N/mm²).

2. Randspannungen einer geschichteten Schale (Befund 3): bisher n/t ± 6 m/t²
   wie fuer eine homogene Schale. Richtig nach der klassischen Laminattheorie:
   [ε0; κ] = ABD⁻¹ [n; m], σ_k(z) = Q̄_k (ε0 + z κ), oben die aeusserste Faser
   der obersten Lage, unten die der untersten.
   a) Zweischichter 5 mm E 210 000 unten, 5 mm E 70 000 oben, ν = 0,3, ΔT =
      50 K, voll gehalten: σ_k = −E_k α ΔT/(1 − ν), unten −180, oben −60
      N/mm² (bisher −210/−30).
   b) Derselbe Aufbau, gleichmaessig zweiachsig n = 100 N/mm, m = 0, von
      Hand: c_k = E_k/(1 − ν) = 300 000 bzw. 100 000 N/mm²,
      a = Σ c_k t_k = 2 000 000 N/mm, b = Σ c_k (z1² − z0²)/2 = −2 500 000 N,
      d = Σ c_k (z1³ − z0³)/3 = 50 000 000/3 Nmm; ε0 = d n/(a d − b²) = 0,8/13 ‰,
      κ = −b n/(a d − b²) = 0,12/13 1/m; σ oben = c_2 (ε0 + 5 mm κ) = 140/13,
      σ unten = c_1 (ε0 − 5 mm κ) = 60/13 N/mm² (bisher beide 10 N/mm²).
   Die homogene Schale bleibt bitgleich.

3. Beulnachweis in Flaechenachsen: res.shell_stress[i]["n"] steht seit dem
   09.11.2026 (Befund A20) im Flaechensystem, feldspannungen und
   zylinderspannungen drehten es trotzdem mit der ersten Elementkante. Ein
   Blechfeld, dessen Elementachsen gegen die Flaechenachsen verdreht sind,
   bekam andere Beulspannungen als dasselbe Feld mit gleichen Achsen
   (σ_u 22,6 statt 25,9 N/mm² bei 30°, σ_u und σ_v vertauscht bei 90°).
   Zwei Wege: Handrechnung N/(b t) und dasselbe Feld unverdreht.

Aufruf:  python -m tests.test_schale_beul_anschluss
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


# --------------------------------------------------------------------------
# 1. Anschluss ohne Stahlsorte
# --------------------------------------------------------------------------
def _diagonale(fy, fu, grade, art="diagonale", welded=True, l_weld=None):
    """Kragarm IPE 300 mit Anschluss am Einspannende. Die Geometrie kommt aus
    dem Vorschlag mit S460-Werten, nachgewiesen wird mit dem Werkstoff des
    Falls (wie tests.test_anschluss_festigkeit)."""
    from statik3d.model import Model, Material, Section
    from statik3d import mesher, solver
    from statik3d.joints import anschluss, templates
    m = Model("A")
    m.add_material(Material("X", E=210e9, nu=0.3, rho=7850, fy=fy, fu=fu, grade=grade))
    m.add_section(Section.i_profile("IPE300", 0.300, 0.150, 0.0071, 0.0107))
    ids = mesher.line_of_beams(m, "X", "IPE300", (0, 0, 0), (4, 0, 0), n=4)
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fz=-20000.0, Fx=300e3)
    an = solver.solve_all(m, workers=1, combinations=False)
    fall = m.materials["X"]
    m.materials["X"] = Material("X", E=210e9, nu=0.3, rho=7850, fy=460e6, fu=540e6, grade="S460")
    if art == "diagonale":
        t = templates.propose(art, m, 0, end=0, N=300e3, welded=welded)
    else:
        t = templates.propose(art, m, 0, end=0, N=0.0, Vz=20000.0, My=80000.0)
    m.materials["X"] = fall
    if l_weld is not None:
        t.l_weld = l_weld
    j = anschluss.als_joint(t, name=f"J_{art}")
    m.joints[j.name] = j
    c = anschluss.check_joint(m, j, dict(an.cases), analysis=an)
    c.modell = m
    return c


def test_anschluss_ohne_sorte():
    from statik3d.joints import welds, templates
    from statik3d.model import Model, Material, Section
    from statik3d import mesher
    soll = 540e6 / math.sqrt(3.0) / (1.0 * 1.25)
    check("f_vw,d S460 f_u 540 = 540/√3/(1,0 · 1,25) = 249,42 N/mm² (Handrechnung)",
          abs(welds.fvw_d(540e6, "S460") - soll) < 1.0, f"{welds.fvw_d(540e6, 'S460') / 1e6:.3f} N/mm²")
    try:
        b = welds.beta_w("")
        check("β_w ohne Stahlsorte: Meldung statt Vorgabewert", False, f"β_w = {b}")
    except ValueError as ex:
        check("β_w ohne Stahlsorte: Meldung statt Vorgabewert", "Stahlsorte" in str(ex), str(ex)[:80])

    # Naht a = 4 mm, l = 136 mm je Flanke (der bisherige Vorschlag): η = N/(2 a l f_vw,d)
    mit = _diagonale(460e6, 540e6, "S460", l_weld=0.136)
    eta = 300e3 / (2 * 0.004 * 0.136 * soll)
    check(f"Knotenblech geschweißt S460, l = 136 mm: η = N/(2 a l f_vw,d) = {eta:.4f} wie bisher",
          not mit.fehler and abs(float(mit.util) - eta) < 1e-6 and abs(eta - 1.1055267) < 1e-6,
          f"η = {mit.util}, Fehler {mit.fehler!r}")
    neu = _diagonale(460e6, 540e6, "S460")
    eta = 300e3 / (2 * 0.004 * 0.151 * soll)
    check(f"… mit dem Vorschlag (l = 151 mm statt 136, β_w 1,0 statt 0,9): η = {eta:.4f} ≤ 1",
          not neu.fehler and abs(float(neu.util) - eta) < 1e-6 and eta <= 1.0, f"η = {neu.util}")
    ohne = _diagonale(460e6, 540e6, "", l_weld=0.136)
    check("Knotenblech geschweißt, f_y/f_u ohne Sorte: kein Nachweis (bisher η 0,9950 mit β_w 0,9)",
          bool(ohne.fehler) and not ohne.util, f"η = {ohne.util}, Fehler {ohne.fehler!r}")
    check("… die Meldung nennt Stahlsorte, β_w und den Werkstoff „X“",
          all(s in (ohne.fehler or "") for s in ("Stahlsorte", "β_w", "„X“")), ohne.fehler)
    check("… und nirgends S355", "S355" not in (ohne.fehler or "") + (ohne.beschreibung or ""),
          (ohne.beschreibung or "")[:80])
    kp = _diagonale(235e6, 360e6, "", art="kopfplatte")
    check("Kopfplatte (Kehlnähte) ohne Sorte: kein Nachweis, Meldung nennt β_w",
          bool(kp.fehler) and "β_w" in kp.fehler, f"Fehler {kp.fehler!r}")
    la = _diagonale(235e6, 360e6, "", art="lasche")
    la_s = _diagonale(235e6, 360e6, "S235", art="lasche")
    check("Laschenstoß (ohne Naht) ohne Sorte: Nachweis wie mit Sorte S235, Beschreibung ohne S355",
          not la.fehler and abs(la.util - la_s.util) < 1e-12 and "S355" not in la.beschreibung,
          f"η = {la.util:.4f} / {la_s.util:.4f}, {la.beschreibung.splitlines()[0] if la.beschreibung else ''}")
    # Vorschlag geschweisst ohne Sorte: die Nahtlaenge haengt an β_w - kein Vorschlag
    m = Model("V")
    m.add_material(Material("X", E=210e9, nu=0.3, rho=7850, fy=460e6, fu=540e6, grade=""))
    m.add_section(Section.i_profile("IPE300", 0.300, 0.150, 0.0071, 0.0107))
    mesher.line_of_beams(m, "X", "IPE300", (0, 0, 0), (4, 0, 0), n=4)
    try:
        t = templates.propose("diagonale", m, 0, end=0, N=300e3, welded=True)
        check("Vorschlag geschweißt ohne Sorte: Meldung (bisher still S355, β_w 0,9)", False,
              t.describe().splitlines()[0])
    except ValueError as ex:
        check("Vorschlag geschweißt ohne Sorte: Meldung (bisher still S355, β_w 0,9)",
              "Stahlsorte" in str(ex) and "X" in str(ex), str(ex)[:80])
    # Vorschlag S460: die Nahtlaenge mit β_w 1,0 (bisher fest 0,9): l = N/(2 f_vw,d a)
    m.materials["X"] = Material("X", E=210e9, nu=0.3, rho=7850, fy=460e6, fu=540e6, grade="S460")
    t = templates.propose("diagonale", m, 0, end=0, N=300e3, welded=True)
    l_soll = math.ceil(max(0.100, 300e3 / (2.0 * soll * t.a_w)) * 1000) / 1000.0
    check(f"Vorschlag geschweißt S460: Nahtlänge mit β_w 1,0 = {l_soll * 1e3:.0f} mm",
          abs(t.l_weld - l_soll) < 1e-9, f"l = {t.l_weld * 1e3:.0f} mm, a = {t.a_w * 1e3:g} mm")


# --------------------------------------------------------------------------
# 2. Randspannungen eines Laminats
# --------------------------------------------------------------------------
UNSYM = [{"t": 0.005, "E": 210e9, "nu": 0.3, "winkel": 0.0},
         {"t": 0.005, "E": 70e9, "nu": 0.3, "winkel": 0.0}]


def _ein_element(lagen=None, t=0.010):
    from statik3d.model import Model, Material, ShellProp
    m = Model("L")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("s", t, lagen=[dict(x) for x in lagen] if lagen else None))
    for p in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]:
        m.add_node(*p)
    m.add_element("shell4", [0, 1, 2, 3], "S235", "s")
    return m


def test_laminat_randspannung():
    from statik3d import solver
    from tests import test_laminat_temperatur as T
    for o in (1, 2):
        m = T._platte(o, T.UNSYM)
        typen = sorted({e.typ for e in m.elements})
        for n in range(m.nn):
            m.fix(n, "all")
        r, _acc = T._rechnen(m)
        top = np.array([d["sig_top"] for d in r.shell_stress.values()])
        bot = np.array([d["sig_bot"] for d in r.shell_stress.values()])
        check(f"{typen}: voll gehalten, oben (E 70 000): σ_x = σ_y = −E α ΔT/(1 − ν) = −60 N/mm², τ = 0",
              np.abs(top[:, :2] + 60e6).max() < 1e-3 * 60e6 and np.abs(top[:, 2]).max() < 1e3,
              f"σ oben {top[0] / 1e6}")
        check(f"{typen}: voll gehalten, unten (E 210 000): σ_x = σ_y = −180 N/mm²",
              np.abs(bot[:, :2] + 180e6).max() < 1e-3 * 180e6 and np.abs(bot[:, 2]).max() < 1e3,
              f"σ unten {bot[0] / 1e6}")
        vm = [(d["vM_top"], d["vM_bot"], d["vM"]) for d in r.shell_stress.values()]
        check(f"{typen}: Vergleichsspannung oben 60, unten 180, maßgebend 180 N/mm²",
              all(abs(a - 60e6) < 0.1e6 and abs(b - 180e6) < 0.1e6 and abs(c - 180e6) < 0.1e6
                  for a, b, c in vm), f"{[round(x / 1e6, 3) for x in vm[0]]}")

    # Handrechnung ABD, zweiachsig n = 100 N/mm, m = 0
    m = _ein_element(UNSYM)
    d = solver.shell_derived(m, 0, np.array([1e5, 1e5, 0.0, 0.0, 0.0, 0.0]))
    so, su = 140.0 / 13.0, 60.0 / 13.0
    check(f"ABD von Hand, n = 100 N/mm: oben σ = 140/13 = {so:.4f} N/mm²",
          np.abs(d["sig_top"][:2] / 1e6 - so).max() < 1e-6 and abs(d["sig_top"][2]) < 1e-3,
          f"{d['sig_top'] / 1e6}")
    check(f"ABD von Hand, n = 100 N/mm: unten σ = 60/13 = {su:.4f} N/mm² (bisher beide 10)",
          np.abs(d["sig_bot"][:2] / 1e6 - su).max() < 1e-6 and abs(d["sig_bot"][2]) < 1e-3,
          f"{d['sig_bot'] / 1e6}")
    check("… Schnittgrößen n, m bleiben, wie sie übergeben wurden",
          np.allclose(d["n"], [1e5, 1e5, 0]) and np.allclose(d["m"], 0.0))

    # Homogene Schale: n/t ± 6 m/t², bitgleich
    m = _ein_element(None)
    r6 = np.array([2e5, -1e5, 3e4, 400.0, -250.0, 80.0])
    d = solver.shell_derived(m, 0, r6)
    t = 0.010
    check("homogene Schale: σ = n/t ± 6 m/t² (bitgleich)",
          np.array_equal(d["sig_top"], r6[:3] / t + 6.0 * r6[3:] / t ** 2)
          and np.array_equal(d["sig_bot"], r6[:3] / t - 6.0 * r6[3:] / t ** 2))
    # Ein Laminat aus einer einzigen Lage ist die homogene Schale
    m1 = _ein_element([{"t": 0.010, "E": 210e9, "nu": 0.3, "winkel": 0.0}])
    d1 = solver.shell_derived(m1, 0, r6)
    check("einlagiges Laminat = homogene Schale (auf 1e-9)",
          np.allclose(d1["sig_top"], d["sig_top"], rtol=1e-9, atol=1e-3)
          and np.allclose(d1["sig_bot"], d["sig_bot"], rtol=1e-9, atol=1e-3))


# --------------------------------------------------------------------------
# 3. Beulnachweis in Flaechenachsen
# --------------------------------------------------------------------------
def _platte(winkel_grad=0.0, versatz=0, a=2.0, b=1.0, t=0.008, nx=8, ny=4, druck=200e3):
    """Blechfeld a × b in der XY-Ebene, um winkel_grad um Z gedreht, an
    x = 0 eingespannt, am anderen Ende Druck laengs. Die Elementachse x
    (erste Kante) laeuft laengs des Feldes (versatz 0) bzw. quer (versatz 1);
    die Flaechenachse x ist die globale X-Achse."""
    from statik3d.model import Model, Material, ShellProp
    from statik3d import solver
    c, s = math.cos(math.radians(winkel_grad)), math.sin(math.radians(winkel_grad))
    m = Model("P")
    m.add_material(Material.steel("S355"))
    m.add_shell_prop(ShellProp("t", t))
    ids = {}
    for j in range(ny + 1):
        for i in range(nx + 1):
            x, y = a * i / nx, b * j / ny
            ids[(i, j)] = m.add_node(c * x - s * y, s * x + c * y, 0.0)
    els = []
    for j in range(ny):
        for i in range(nx):
            e = [ids[(i, j)], ids[(i + 1, j)], ids[(i + 1, j + 1)], ids[(i, j + 1)]]
            els.append(m.add_element("shell4", e[versatz:] + e[:versatz], "S355", "t"))
    for j in range(ny + 1):
        m.fix(ids[(0, j)], "all")
    for j in range(ny + 1):
        anteil = 0.5 if j in (0, ny) else 1.0
        m.load_node(ids[(nx, j)], Fx=-druck * anteil / ny * c, Fy=-druck * anteil / ny * s)
    m.add_beulfeld("F", els)
    an = solver.solve_all(m, combinations=False, envelopes=False, design=True)
    return an.beulen.felder["F"].werte, m


def _gleich(w, w0):
    return max(abs(w[k] - w0[k]) / max(abs(w0["sigma_x"]), 1.0)
               for k in ("sigma_x", "sigma_z", "tau", "lambda_p"))


def test_beulen_flaechenachsen():
    from statik3d.solver import flaechen_bezugssystem
    from statik3d.elements import shell as sh
    soll = 200e3 / (1.0 * 0.008)
    w0, _m0 = _platte(0.0, 0)
    check("Feld unverdreht: σ_u trifft die Handrechnung N/(b t) = 25 N/mm² (±15 %)",
          abs(w0["sigma_x"] - soll) < 0.15 * soll and w0["sigma_z"] < 0.25 * soll,
          f"σ_u {w0['sigma_x'] / 1e6:.3f}, σ_v {w0['sigma_z'] / 1e6:.3f} N/mm²")
    for wg, vs in ((30.0, 0), (0.0, 1), (90.0, 0)):
        w, m = _platte(wg, vs)
        X = m.nodes[m.elements[0].nodes]
        T3e = sh.shell_frame(X[0], X[1], X[2])[0]
        dreh = math.degrees(sh.frame_winkel(T3e, flaechen_bezugssystem(T3e)))
        check(f"Feld {wg:g}° gedreht, Startecke {vs} (Elementachse {dreh:+.0f}° zur Flächenachse): "
              "Beulspannungen wie unverdreht",
              _gleich(w, w0) < 1e-6,
              f"σ_u {w['sigma_x'] / 1e6:.3f}/{w0['sigma_x'] / 1e6:.3f}, σ_v {w['sigma_z'] / 1e6:.3f}/"
              f"{w0['sigma_z'] / 1e6:.3f}, τ {w['tau'] / 1e6:.3f}/{w0['tau'] / 1e6:.3f} N/mm²")


def test_zylinder_liegend():
    """Rohr mit Achse X: Flaechenachse x = Meridian, die erste Elementkante
    laeuft in Umfangsrichtung (90°). Meridianspannung N/(U t)."""
    from statik3d.model import Model, Material, ShellProp
    from statik3d import solver
    m = Model("Rohr")
    m.add_material(Material.steel("S355"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    r, l, nu_, nz = 0.5, 3.0, 24, 6
    ids = {}
    for k in range(nz + 1):
        for j in range(nu_):
            a = 2 * math.pi * j / nu_
            ids[(j, k)] = m.add_node(l * k / nz, r * math.cos(a), r * math.sin(a))
    els = []
    for k in range(nz):
        for j in range(nu_):
            j2 = (j + 1) % nu_
            els.append(m.add_element("shell4", [ids[(j, k)], ids[(j2, k)],
                                                ids[(j2, k + 1)], ids[(j, k + 1)]], "S355", "t10"))
    for j in range(nu_):
        m.fix(ids[(j, 0)], "all")
    N = 1500e3
    for j in range(nu_):
        m.load_node(ids[(j, nz)], Fx=-N / nu_)
    m.add_beulfeld("Mantel", els, art="zylinder", qualitaet="B")
    an = solver.solve_all(m, combinations=False, envelopes=False, design=True)
    w = an.beulen.felder["Mantel"].werte
    umfang = nu_ * 2 * r * math.sin(math.pi / nu_)
    soll = N / (umfang * 0.010)
    check(f"liegendes Rohr: Meridianspannung N/(U t) = {soll / 1e6:.3f} N/mm² (±0,2 %)",
          abs(w["sigma_x"] - soll) < 2e-3 * soll, f"σ_x {w['sigma_x'] / 1e6:.3f} N/mm²")
    check("… Umfangsspannung bleibt klein (< 25 % von σ_x)", w["sigma_z"] < 0.25 * soll,
          f"σ_θ {w['sigma_z'] / 1e6:.3f} N/mm²")


# --------------------------------------------------------------------------
# Verfahrenstabelle
# --------------------------------------------------------------------------
def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    check("VERFAHRENSSTAND ≥ 36", rv.VERFAHRENSSTAND >= 36, str(rv.VERFAHRENSSTAND))
    for name in ("anschluss_beta_w", "laminat_randspannung", "beulen_flaechenachsen"):
        mk = rv.merkmal(name)
        check(f"Merkmal „{name}“: Fehlerkorrektur Stand 36",
              mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and mk.wechsel[-1].stand == 36)
    mk = rv.merkmal("anschluss_beta_w")
    if mk is not None:
        check("… „anschluss_beta_w“: geschweißter Anschluss ohne Sorte betroffen",
              mk.betrifft(_diagonale(460e6, 540e6, "").modell))
        check("… mit Sorte S460 nicht", not mk.betrifft(_diagonale(460e6, 540e6, "S460").modell))
        check("… Laschenstoß ohne Sorte (keine Naht) nicht",
              not mk.betrifft(_diagonale(235e6, 360e6, "", art="lasche").modell))
    mk = rv.merkmal("laminat_randspannung")
    if mk is not None:
        check("… „laminat_randspannung“: geschichtete Schale betroffen, homogene nicht",
              mk.betrifft(_ein_element(UNSYM)) and not mk.betrifft(_ein_element(None)))
    mk = rv.merkmal("beulen_flaechenachsen")
    if mk is not None:
        check("… „beulen_flaechenachsen“: Feld mit Elementachse 30° bzw. 90° zur Flächenachse betroffen",
              mk.betrifft(_platte(30.0, 0)[1]) and mk.betrifft(_platte(0.0, 1)[1]))
        check("… Feld mit Elementachse = Flächenachse nicht", not mk.betrifft(_platte(0.0, 0)[1]))


def main():
    for t in (test_anschluss_ohne_sorte, test_laminat_randspannung, test_beulen_flaechenachsen,
              test_zylinder_liegend, test_verfahrenstabelle):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
