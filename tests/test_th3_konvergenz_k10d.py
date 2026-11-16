"""
Runde k10d (16.11.2026), Theorie III. Ordnung: Restschranke und Konvergenz.

(a) Die Restschranke in theorie3._lastknoten war min(1e-9 * Betragssumme,
    0,001 N). Am weichen Kragarm (L = 10 m, I = 1e-6 m^4, 1 N am Ende b) mit
    -1e7 N / +1e7 N und einem Rest von 0,0009 N am Slave c eines RBE3
    „Stabende 1“ blieb der Rest unter der Schranke: Theorie III. Ordnung
    rechnete still w(b) = 1,587302 mm, Theorie I. Ordnung und Hand ergeben
    1,588730 mm. Jetzt liegt die Schranke auf Rundungsniveau (1e-13 der
    Betragssumme, hoechstens 0,001 N): der Lastfall wird abgewiesen.
    Nachbesserung 1 (Gegenpruefung 1 zu k10d): ab einer Betragssumme von
    1e10 N erreichte 1e-13 der Betragssumme die Kappung, und 0,0009 N gingen
    wieder still verloren. Jetzt 4 * n * 2,2e-16 der Betragssumme bei n
    Beitraegen, hoechstens 0,001 N.
    Nachbesserung 2 (Gegenpruefung 2 zu k10d): diese Schranke lag etwa
    achtfach ueber der Rundung; ab ±2e11 N (einzeln) bzw. ±5e10 N (auf
    10 + 10 Beitraege verteilt) gingen 0,0009 N wieder still verloren. Jetzt
    exakte Summe der Produkte und eine Schranke nur aus der Darstellung der
    nicht exakt darstellbaren Eingaben (Faktor 0,1, Last 0,0009 N, g 9,81).
(b) Am Kragarm L = 10 m, A = 1e-3 m², I = 1e-6 m⁴ meldete Theorie III.
    Ordnung bei F = 0,1 N „keine Konvergenz“ (Theorie I. Ordnung und Hand
    0,158730 mm), mit Koordinaten um 100 km schon bei 0,001 N. Ursache: die
    Laengung L - L0 als Differenz zweier Laengen aus X0 + u; deren Rundung
    gab eine Normalkraft, die nicht unter die Schranke 1e-6 der Last fiel.
(c) Mit Vorverformungen meldete Theorie III. Ordnung „keine Konvergenz“ am
    IPE 300, 6 m, N = 100 kN mit 15 kN/m bzw. Endmomenten 60 kNm (etwa
    0,29 N_cr,z, nahe am Biegedrillknicken) und bei LK1 einer Hallenreihe
    (Schiefstellung quer). Ursachen: die genaeherte Tangente
    T^T (k_l + k_g(N)) T konvergiert bei grosser Verdrehung nur linear, und
    die Vorkruemmung schaltete sich je Iteration mit der Normalkraft der
    Zwischenlage ein und aus (Grenze 5.3.2(6) bei 86,9 kN). Jetzt rechnet
    eine stockende Laststufe neu mit der vollen Tangente und mit der
    Entscheidung 5.3.2(6) aus der vollen Last nach Theorie I. Ordnung; was
    vorher konvergierte, rechnet unveraendert.
(d) An L-Rahmen (90° und 60°, auch mit Versatz) mit einem Stummel von
    0,02 m bzw. 0,005 m an der Ecke meldete Theorie III. Ordnung „keine
    Konvergenz“ und gab den Zustand der ersten Laststufe aus (ein Zehntel).
    Neben (c) stand die Rechnung am Stummel 0,005 m bei Korrekturen um
    1e-16 m: das Residuum war Rundungsrauschen (6 E I / L² mal 2e-16 rad,
    etwa 0,001 N). Jetzt endet eine Stufe auch, wenn die Korrektur die Lage
    nicht mehr aendert (unter 1e-12 der Modellgroesse bzw. 1e-12 rad) und
    das Residuum unter 0,1 % der Last liegt.
(e) Theorie III. Ordnung kondensierte Dreh- und Drehfedergelenke und bildete
    das Gleichgewicht am Gelenk um die Sehne statt um die mitgedrehte
    Gelenkachse. L-Rahmen mit Torsionsfeder 2 kNm/rad an der Ecke:
    Verdrehung der Spitze 5,7 % neben dem Stummelmodell mit l0 -> 0 (jetzt
    0,03 % bei l0 = 0,001 m); mit Torsionsgelenk bei 3 kN 0,0036 mm neben dem
    Stummel; Traeger mit Gabellagern und Torsionsgelenk in der Mitte
    verdrillte unsymmetrisch. Merkmal theorie3_gelenk_achse, Stand 75.
    Nachbesserung 1 (Gegenpruefung 1 zu k10d): die Gelenkdrehung φ wurde nur
    bis zu einer groben Schranke iteriert (etwa 0,0016 Nm); das Federmoment
    rauschte ueber der Konvergenzschranke, und U-Rahmen mit Torsionsfedern
    meldeten „keine Konvergenz“ bzw. „Gleichungssystem singulär“, obwohl sie
    ein Gleichgewicht haben. Jetzt bis auf Rundungsniveau.

Aufruf:  python -m tests.test_th3_konvergenz_k10d
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []

E = 210e9
TEXT_KP = "Theorie III. Ordnung rechnet keine"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"[{'OK ' if ok else 'XX '}] {name}" + (f"  ({detail})" if detail else ""))
    sys.stdout.flush()


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


def _rechne(m, name="LK1"):
    """(Results, Fehlertext Theorie III. Ordnung) der Kombination ``name``."""
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=1, design=False)
    f = ""
    th3 = getattr(an, "theorie3", None)
    if th3 is not None and name in th3.kombinationen:
        f = th3.kombinationen[name].fehler or ""
    return an.combinations.get(name), f


# --------------------------------------------------------------------------
# (a) Restschranke am weichen Kragarm
# --------------------------------------------------------------------------
L_W, I_W = 10.0, 1e-6
FLEX_W = L_W ** 3 / (3 * E * I_W)          # m/N, 1,587302 mm je N


def weich(th, gross, rest, fb=1.0, rbe=True):
    from statik3d.model import Model, Material, Section
    from statik3d.stabeinleitung import STABENDE
    m = Model("W")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-3, Iy=I_W, Iz=I_W, It=1e-7, zmax=0.05, ymax=0.05))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(L_W, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    for n in ("LF2", "LF3", "LF4"):
        m.add_load_case(n)
    m.load_node(b, Fz=-fb, case="LF1")
    if rbe:
        c = m.add_node(L_W, -0.2, 0)
        d = m.add_node(L_W, 0.2, 0)
        e = m.add_node(L_W, 0, 0.2)
        m.add_starrkoerper(b, [c, d, e], "RBE3", name=STABENDE + "1")
        m.load_node(c, Fz=-gross, case="LF2")
        m.load_node(c, Fz=gross, case="LF3")
        if rest:
            m.load_node(c, Fz=-rest, case="LF4")
    elif rest:
        m.load_node(b, Fz=-rest, case="LF4")
    k = m.add_combination("LK1", {"LF1": 1.0, "LF2": 1.0, "LF3": 1.0, "LF4": 1.0}, "ULS")
    k.theorie = th
    return m, b


def test_a_restschranke():
    from statik3d import rechenverfahren as rv
    from statik3d.theorie3 import kopplung_sperre
    mk = rv.merkmal("theorie3_stabende_anschluss")
    for gross, rest in ((1e7, 0.0009), (1e5, 0.0009), (1e9, 0.0005)):
        hand = (1.0 + rest) * FLEX_W
        m, b = weich("I", gross, rest)
        r1, _f = _rechne(m)
        w1 = -np.asarray(r1.u).reshape(-1, 6)[b, 2]
        check(f"(a) ±{gross:.0f} N, Rest {rest} N: Theorie I. Ordnung w(b) = Hand",
              abs(w1 - hand) <= 1e-6 * hand, f"{w1 * 1e3:.6f} mm, Hand {hand * 1e3:.6f} mm")
        m, b = weich("III", gross, rest)
        wg = _rechne(weich("III", gross, rest, rbe=False)[0])
        wg = -np.asarray(wg[0].u).reshape(-1, 6)[b, 2]
        check("… gleichwertiges Modell (Rest direkt an b) nach Theorie III. Ordnung = Hand",
              abs(wg - hand) <= 1e-5 * hand, f"{wg * 1e3:.6f} mm")
        t = kopplung_sperre(m, None, factors={"LF1": 1.0, "LF2": 1.0, "LF3": 1.0, "LF4": 1.0})
        check("… kopplung_sperre sieht den Rest (stille Abweichung waere "
              f"{rest * FLEX_W * 1e3:.4f} mm)", TEXT_KP in t, t[:80])
        r3, f3 = _rechne(m)
        check("… Theorie III. Ordnung weist ab statt still ohne Rest zu rechnen",
              TEXT_KP in f3, f"{f3[:80]!r}")
        check("… Merkmal theorie3_stabende_anschluss betrifft",
              mk.betrifft(weich("III", gross, rest)[0]) is True)
    # Gegenprobe: genau aufgehoben wird gerechnet
    m, b = weich("III", 1e7, 0.0)
    r3, f3 = _rechne(m)
    w3 = -np.asarray(r3.u).reshape(-1, 6)[b, 2] if r3 is not None else float("nan")
    check("(a) Gegenprobe ±1e7 N ohne Rest: gerechnet, w(b) = Hand",
          not f3 and abs(w3 - FLEX_W) <= 1e-5 * FLEX_W, f"{f3[:60]!r} {w3 * 1e3:.6f} mm")


def test_a_grosse_betragssumme():
    """Gegenpruefung 1 zu k10d: mit 1e-13 der Betragssumme erreichte die
    Schranke ab einer Betragssumme von 1e10 N die Kappung 0,001 N, und ein
    Rest von 0,0009 N ging still verloren (Theorie III. Ordnung 1,587302 statt
    1,588730 mm). Jetzt 4 * n * 2,2e-16 der Betragssumme bei n Beitraegen."""
    from statik3d.theorie3 import kopplung_sperre
    fak = {"LF1": 1.0, "LF2": 1.0, "LF3": 1.0, "LF4": 1.0}
    for gross in (5e9, 1e10, 1e11):
        rest = 0.0009
        hand = (1.0 + rest) * FLEX_W
        m, b = weich("I", gross, rest)
        r1, _f = _rechne(m)
        w1 = -np.asarray(r1.u).reshape(-1, 6)[b, 2]
        check(f"(a) ±{gross:.0f} N, Rest {rest} N: Theorie I. Ordnung loest den Rest auf (w(b) = Hand auf 0,00001 mm)",
              abs(w1 - hand) <= 1e-8, f"{w1 * 1e3:.6f} mm, Hand {hand * 1e3:.6f} mm")
        m, b = weich("III", gross, rest)
        t = kopplung_sperre(m, None, factors=fak)
        check(f"… kopplung_sperre sieht den Rest (stille Abweichung waere {rest * FLEX_W * 1e3:.6f} mm)",
              TEXT_KP in t, t[:80])
        r3, f3 = _rechne(m)
        check("… Theorie III. Ordnung weist ab statt still ohne Rest zu rechnen", TEXT_KP in f3, f"{f3[:80]!r}")
    # Gegenproben: Rundungsreste grosser Lasten bleiben aufgehoben und werden gerechnet
    for gross, f2, f3_, last2, last3 in ((1e10, 1.0, 1.0, -1.0, 1.0), (1e10, 0.1, 0.3, -3.0, 1.0),
                                         (1e11, 0.1, 0.3, -3.0, 1.0)):
        m, b = weich("III", 1.0, 0.0)
        m.load_cases["LF2"].nodal_loads[0].F = [0.0, 0.0, last2 * gross, 0.0, 0.0, 0.0]
        m.load_cases["LF3"].nodal_loads[0].F = [0.0, 0.0, last3 * gross, 0.0, 0.0, 0.0]
        faktoren = {"LF1": 1.0, "LF2": f2, "LF3": f3_, "LF4": 1.0}
        m.combinations["LK1"].factors = dict(faktoren)
        S = f2 * last2 * gross + f3_ * last3 * gross
        t = kopplung_sperre(m, None, factors=faktoren)
        r3, f3 = _rechne(m)
        w3 = -np.asarray(r3.u).reshape(-1, 6)[b, 2] if r3 is not None else float("nan")
        check(f"(a) Gegenprobe {f2} * {last2 * gross:.0f} N + {f3_} * {last3 * gross:.0f} N (Rest {S:.3g} N, "
              "Rundung): nicht abgewiesen, w(b) = Hand", not t and not f3 and abs(w3 - FLEX_W) <= 1e-5 * FLEX_W,
              f"{t[:40]!r} {f3[:40]!r} {w3 * 1e3:.6f} mm")


# --------------------------------------------------------------------------
# (b) kleine Lasten
# --------------------------------------------------------------------------
def kragarm(F, th, versatz=0.0, L=L_W, A=1e-3, I=I_W, teil=1):
    from statik3d.model import Model, Material, Section
    m = Model("K")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-7, zmax=0.05, ymax=0.05))
    m.design.imperfektionen = False
    m.netz.stabteilung = teil
    a = m.add_node(versatz, versatz, versatz)
    b = m.add_node(versatz + L, versatz, versatz)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    m.load_node(b, Fz=-F)
    k = m.add_combination("LK1", {"LF1": 1.0}, "ULS")
    k.theorie = th
    return m, b


def test_b_kleine_last():
    for F, off in ((0.1, 0.0), (1.0, 0.0), (0.001, 1e5), (0.1, 1e5)):
        hand = F * FLEX_W
        m, b = kragarm(F, "I", off)
        r1, _f = _rechne(m)
        w1 = -np.asarray(r1.u).reshape(-1, 6)[b, 2]
        m, b = kragarm(F, "III", off)
        r3, f3 = _rechne(m)
        w3 = -np.asarray(r3.u).reshape(-1, 6)[b, 2]
        th = str((r3.info or {}).get("theorie", ""))
        check(f"(b) F = {F} N, Koordinaten um {off:.0f} m: Theorie III. Ordnung konvergiert",
              not f3 and th.startswith("III"), f"{f3!r} {th}")
        check("… w(b) = Hand = Theorie I. Ordnung (auf 0,000001 mm)",
              abs(w3 - hand) <= 1e-9 and abs(w1 - hand) <= 1e-9,
              f"Th III {w3 * 1e3:.6f}, Th I {w1 * 1e3:.6f}, Hand {hand * 1e3:.6f} mm")


# --------------------------------------------------------------------------
# (c) Vorverformungen, Biegedrillnaehe, Hallenreihe
# --------------------------------------------------------------------------
def ipe(last="linie", N=100e3, imp=True):
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    from statik3d import mesher
    m = Model("IPE")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6.0, 0, 0), 1)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[-1], Fx=-N)
    if last == "moment":
        m.load_node(ids[0], My=60e3)
        m.load_node(ids[-1], My=-60e3)
    else:
        m.load_beam(0, qz=-15e3)
    m.add_member("T1", [0])
    m.design.imperfektionen = imp
    m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie="III")
    return m


def test_c_ipe_vorverformung():
    import math
    for last in ("linie", "moment"):
        m = ipe(last)
        r, f = _rechne(m, "K1")
        th = str((r.info or {}).get("theorie", ""))
        check(f"(c) IPE 300, N = 100 kN, {last}, mit Vorverformung: Theorie III. Ordnung konvergiert",
              not f and th.startswith("III"), f"{f!r} {th}")
        if f:
            continue
        R = np.asarray(r.reactions).reshape(-1, 6)
        qz = 15e3 * 6.0 if last == "linie" else 0.0
        check("… Gleichgewicht: Summe Rx = N, Summe Rz = q L (auf 1 N)",
              abs(R[:, 0].sum() - 100e3) <= 1.0 and abs(R[:, 2].sum() - qz) <= 1.0,
              f"Rx {R[:, 0].sum():.3f} N, Rz {R[:, 2].sum():.3f} N")
        from statik3d import solver
        an = _still(solver.solve_all, m, workers=1, design=False)
        vk = an.theorie3.kombinationen["K1"].vorkruemmung
        sec = m.sections["IPE 300"]
        fy = 235e6
        grenze = 0.5 * math.sqrt(sec.A * fy / 100e3)
        js = vk.get("je_stab") or []
        check("… Vorkruemmung nach 5.3.2(6) mit N_Ed der vollen Last (Theorie I. Ordnung): "
              f"Grenze 0,5 √(A f_y/N_Ed) = {grenze:.3f}",
              len(js) == 1 and abs(js[0]["grenze"] - grenze) <= 1e-3, js[:1])


def halle(n_rahmen=3):
    """Reihe von Zweigelenkrahmen HEB 400 / IPE 600 mit Laengsriegeln IPE
    200 (Hallenreihe der EC3-Gegenpruefung), Schiefstellung quer (y)."""
    from statik3d.model import Model, Material, Section
    from statik3d import mesher
    m = Model("Halle")
    m.add_material(Material.steel("S355"))
    for p in ("HEB 400", "IPE 600", "IPE 200"):
        m.add_section(Section.from_profile(p))
    m.case().category = "G"
    a, b, h = 5.0, 15.0, 6.0
    staebe, riegel = [], []

    def stab(p, q, sec, nel):
        e0 = len(m.elements)
        mesher.line_of_beams(m, "S355", sec, p, q, nel)
        staebe.append(list(range(e0, len(m.elements))))
        return staebe[-1]
    for i in range(n_rahmen):
        y = i * a
        stab((0, y, 0), (0, y, h), "HEB 400", 3)
        stab((b, y, 0), (b, y, h), "HEB 400", 3)
        riegel.append(stab((0, y, h), (b, y, h), "IPE 600", 4))
    for i in range(n_rahmen - 1):
        for x in (0.0, b):
            stab((x, i * a, h), (x, (i + 1) * a, h), "IPE 200", 1)
    mesher.merge_nodes(m)
    for k, els in enumerate(staebe):
        m.add_member(f"S{k + 1}", els)
    for n in mesher.select_nodes(m, zmin=-1e-6, zmax=1e-6):
        m.fix(int(n), [0, 1, 2, 5])
    for els in riegel:
        for e in els:
            m.load_beam(e, qz=-6e3)
    m.add_load_case("LF2", "S", "Schnee", nummer=2)
    for els in riegel:
        for e in els:
            m.load_beam(e, qz=-5e3)
    m.add_load_case("LF3", "W", "Wind x", nummer=3)
    for n in range(m.nn):
        if abs(m.nodes[n][0]) < 1e-9 and m.nodes[n][2] > 1e-6:
            m.load_node(n, Fx=8e3)
    m.active_case = "LF1"
    m.add_combination("LK1", {"LF1": 1.35, "LF2": 1.5}, "ULS", theorie="III")
    m.add_combination("LK2", {"LF1": 1.35, "LF2": 0.75, "LF3": 1.5}, "ULS", theorie="III")
    m.design.th2_richtung = [0.0, 1.0]
    return m


def test_c_hallenreihe():
    m = halle()
    r1, f1 = _rechne(m, "LK1")
    th = str((r1.info or {}).get("theorie", ""))
    check("(c) Hallenreihe 3 Rahmen, LK1 mit Schiefstellung quer: Theorie III. Ordnung konvergiert",
          not f1 and th.startswith("III"), f"{f1!r} {th}")
    if not f1:
        R = np.asarray(r1.reactions).reshape(-1, 6)
        F = (1.35 * 6e3 + 1.5 * 5e3) * 15.0 * 3
        check("… Gleichgewicht: Summe Rz = Summe der Lasten (auf 1 N)",
              abs(R[:, 2].sum() - F) <= 1.0, f"{R[:, 2].sum():.3f} N, Last {F:.3f} N")
    m = halle()
    r2, f2 = _rechne(m, "LK2")
    u2 = np.asarray(r2.u).reshape(-1, 6)
    # LK2 konvergierte schon vorher: Ergebnis unveraendert (Wert auf 81d2ce1b)
    check("… LK2 (konvergierte schon vorher) rechnet unveraendert: uy(Knoten 31) = 3,638048 mm",
          not f2 and abs(u2[31, 1] * 1e3 - 3.63804835) <= 1e-6, f"{f2!r} {u2[31, 1] * 1e3:.8f} mm")


# --------------------------------------------------------------------------
# (d) kurze Elemente an Rahmenecken
# --------------------------------------------------------------------------
G_W = E / 2.6


def _rechteck(name, b=0.02, h=0.4):
    from statik3d.model import Section
    return Section(name, A=b * h, Iy=b * h ** 3 / 12, Iz=h * b ** 3 / 12,
                   It=h * b ** 3 / 3 * (1 - 0.63 * b / h), typ="rect", h=h, b=b, zmax=h / 2, ymax=b / 2)


def l_rahmen(winkel=90.0, l0=0.02, art="stummel", kt=2e3, ecc=None, L=2.0, n=10, P=1e3, stoer=2.0,
             fix_spitze=False):
    """L-Rahmen (Gegenpruefung k11, v3b.rahmen): Schenkel 1 von (0,0,0) nach
    (L,0,0), an der Ecke ein Stueck l0 in Richtung des zweiten Schenkels
    (``art`` "stummel": G I_t / l0 = kt ohne Gelenk; "feder": normales I_t,
    Federgelenk Torsion kt am Anfang des zweiten Schenkels), Rechteck
    20 x 400 mm hochkant; Fuss eingespannt, an der Spitze -P in x und stoer
    in z. Rueckgabe (Modell, Spitze)."""
    import math
    from statik3d.model import Model, Material
    m = Model("L")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(_rechteck("P"))
    st = _rechteck("S")
    if art == "stummel":
        st.It = kt * l0 / G_W
    m.add_section(st)
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    r = math.radians(90.0)

    def strecke(a_id, b_xyz, nn, sec, ecc_=None):
        a = np.array(m.nodes[a_id], float)
        b = np.array(b_xyz, float)
        ids = [a_id] + [m.add_node(*(a + (b - a) * j / nn)) for j in range(1, nn + 1)]
        for j in range(nn):
            kw = {"roll": r}
            if ecc_ is not None:
                kw["exzentrizitaet"] = [list(ecc_), list(ecc_)]
            m.add_element("beam", [ids[j], ids[j + 1]], "ST", sec, **kw)
        return ids
    w = math.radians(180.0 - winkel)
    pb = np.array([L, 0.0, 0.0])
    t = np.array([math.cos(w), math.sin(w), 0.0])
    start = m.add_node(0, 0, 0)
    ids = strecke(start, tuple(pb), n, "P")
    s_ids = strecke(ids[-1], tuple(pb + l0 * t), 1, "S", ecc if art == "stummel" else None)
    erstes = len(m.elements)
    ids = strecke(s_ids[-1], tuple(pb + L * t), n, "P")
    el = m.elements[erstes]
    if ecc is not None:
        el.exzentrizitaet = [list(ecc), list(ecc)]
    if art == "feder":
        el.hinge_springs = [(3, kt)]
    elif art == "gelenk":
        el.hinges = sorted(set(el.hinges) | {3})
    m.fix(start, "all")
    if art == "gelenk" or fix_spitze:
        m.fix(ids[-1], [4])              # Torsion des zweiten Schenkels an der Spitze gehalten
    m.load_node(ids[-1], Fx=-P, Fz=stoer)
    return m, ids[-1]


def _th3_direkt(m, schritte=10):
    from statik3d.theorie3 import solve_theorie3
    r, info = _still(solve_theorie3, m, {m.active_case: 1.0}, m.active_case, schritte=schritte,
                     imperfektionen=False, stabteilung=False)
    return np.asarray(r.u, float), info, r


# Spitze nach Theorie II. Ordnung mit Momentenglied (Runde k11, Gegenpruefung
# 3, logs/v3b_neu.txt, Stummel l0 = 0,02 m) [m]
TH2_K11 = {90.0: (-4.774022e-04, 1.785847e-04, 4.049460e-04),
           60.0: (-3.586039e-04, -5.102490e-05, 2.654552e-04)}


def test_d_kurze_elemente():
    for winkel in (90.0, 60.0):
        for l0 in (0.02, 0.005):
            for ecc in ((None, (0.0, 0.0, 0.05)) if winkel == 90.0 else (None,)):
                m, sp = l_rahmen(winkel, l0, ecc=ecc)
                u, info, r = _th3_direkt(m)
                txt = f"(d) L-Rahmen {winkel:.0f}°, Stummel {l0} m" + (", Versatz 0,05 m" if ecc else "")
                check(f"{txt}: Theorie III. Ordnung konvergiert", not info.fehler, info.fehler)
                if info.fehler:
                    continue
                u20, info20, _r = _th3_direkt(l_rahmen(winkel, l0, ecc=ecc)[0], 20)
                d = float(np.abs(u[sp, :3] - u20[sp, :3]).max()) * 1e3
                check("… 10 und 20 Laststufen ergeben dieselbe Spitze (auf 0,00001 mm)",
                      not info20.fehler and d <= 1e-5, f"{d:.2e} mm")
                Rk = np.asarray(r.reactions).reshape(-1, 6)
                check("… Gleichgewicht: Summe Rx = P, Summe Rz = -stoer (auf 0,001 N)",
                      abs(Rk[:, 0].sum() - 1e3) <= 1e-3 and abs(Rk[:, 2].sum() + 2.0) <= 1e-3,
                      f"{Rk[:, 0].sum():.6f} / {Rk[:, 2].sum():.6f} N")
                if l0 == 0.02 and ecc is None:
                    ref = np.asarray(TH2_K11[winkel])
                    d2 = float(np.abs(u[sp, :3] - ref).max()) * 1e3
                    check("… Spitze = Theorie II. Ordnung mit Momentenglied (Runde k11) auf 0,001 mm",
                          d2 <= 1e-3, f"{d2:.6f} mm, Th III {np.round(u[sp, :3] * 1e3, 6)} mm")


# --------------------------------------------------------------------------
# (e) Dreh- und Drehfedergelenke
# --------------------------------------------------------------------------
def test_e_torsionsfeder():
    for l0, soll in ((0.1, -2.723), (0.001, 0.0)):
        us, i1, _r = _th3_direkt(l_rahmen(90.0, l0, art="stummel")[0])
        m, sp = l_rahmen(90.0, l0, art="feder")
        uf, i2, _r = _th3_direkt(m)
        rel = 100.0 * (uf[sp, 4] / us[sp, 4] - 1.0)
        du = float(np.abs(uf[:, :3] - us[:, :3]).max()) * 1e3
        if l0 == 0.001:
            check("(e) L-Rahmen, Torsionsfeder 2 kNm/rad gegen Stummel l0 = 0,001 m: Verdrehung der Spitze "
                  "auf 0,1 %, Verschiebungen auf 0,00001 mm",
                  not i1.fehler and not i2.fehler and abs(rel) <= 0.1 and du <= 1e-5,
                  f"{rel:+.3f} %, {du:.2e} mm, ry {uf[sp, 4]:.6e} / {us[sp, 4]:.6e}")
        else:
            # Theorie II. Ordnung mit Momentenglied (Runde k11, probe_feder_1kN.txt): Feder gegen
            # Stummel 0,1 m -2,723 %; das Stummelmodell ist bei 0,1 m nicht mehr gleichwertig
            check("(e) … bei l0 = 0,1 m wie Theorie II. Ordnung mit Momentenglied: Feder/Stummel -2,723 % "
                  "(auf 0,2 Prozentpunkte)", abs(rel - soll) <= 0.2, f"{rel:+.3f} %")


def test_e_torsionsgelenk():
    us, i1, _r = _th3_direkt(l_rahmen(90.0, 0.001, art="stummel", kt=1.0, P=3e3, fix_spitze=True)[0])
    ug, i2, _r = _th3_direkt(l_rahmen(90.0, 0.001, art="gelenk", P=3e3)[0])
    du = float(np.abs(ug[:, :3] - us[:, :3]).max()) * 1e3
    check("(e) L-Rahmen 3 kN, Torsionsgelenk gegen Stummel l0 = 0,001 m mit G I_t / l0 = 1 Nm/rad: "
          "Verschiebungen auf 0,0001 mm", not i1.fehler and not i2.fehler and du <= 1e-4, f"{du:.6f} mm")


def kette(art="gelenk", n=20, L=4.0, M=1.0e3):
    """Traeger (Rechteck 20 x 400 hochkant) mit Gabellagern, Randmomenten M
    und 2 N quer in der Mitte, Torsionsgelenk bzw. -feder am Anfang des
    Elements hinter der Mitte (Gegenpruefung k11, kette_torsion)."""
    from statik3d.model import Model, Material
    m = Model("K")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(_rechteck("P"))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    ids = [m.add_node(L * j / n, 0, 0) for j in range(n + 1)]
    for j in range(n):
        m.add_element("beam", [ids[j], ids[j + 1]], "ST", "P")
    e = m.elements[n // 2]
    if art == "gelenk":
        e.hinges = [3]
    elif art == "feder":
        e.hinge_springs = [(3, 2e3)]
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[0], My=M)
    m.load_node(ids[-1], My=-M)
    m.load_node(ids[n // 2], Fy=2.0)
    return m, ids


def test_e_symmetrie():
    n = 20
    u0, i0, _r = _th3_direkt(kette("ohne")[0])
    for art in ("gelenk", "feder"):
        u, info, _r = _th3_direkt(kette(art)[0])
        asym = max(abs(u[k, 3] - u[n - k, 3]) for k in range(n // 2))
        check(f"(e) Traeger mit Torsions{art} in der Mitte: symmetrisch verdrillt (Spiegelknoten auf 1e-12 rad)",
              not info.fehler and asym <= 1e-12, f"{asym:.2e} rad, rx {u[n // 2 - 1, 3]:.4e} / {u[n // 2 + 1, 3]:.4e}")
        # aus Symmetrie traegt die Mitte kein Torsionsmoment: wie ohne Gelenk
        d = float(np.abs(u[:, 3] - u0[:, 3]).max())
        check("… gleich dem Traeger ohne Gelenk (Torsionsmoment in der Mitte null, auf 1e-12 rad)",
              not i0.fehler and d <= 1e-12, f"{d:.2e} rad")


# --------------------------------------------------------------------------
# (e), Nachbesserung 1: Federgelenke konvergieren wieder
# --------------------------------------------------------------------------
def u_rahmen(art="feder", l0=0.0, kt=2e3, P=1e3, stoer=20.0, n=10, L=2.0):
    """U-Rahmen (Gegenpruefung k11, v3.u_federn): A(0,0,0)-B(L,0,0)-C(L,L,0)-
    D(0,L,0), Rechteck 20 x 400 mm hochkant, je n Elemente, A eingespannt,
    an D -P in y und ``stoer`` in z. An beiden Ecken ``art`` "feder":
    Torsionsfeder kt am Anfang des folgenden Schenkels (mit l0 > 0 hinter
    einem Stueck l0 normalen Querschnitts), "stummel": Stueck l0 mit
    G I_t / l0 = kt ohne Gelenk. Rueckgabe (Modell, D)."""
    import math
    from statik3d.model import Model, Material
    m = Model("U")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(_rechteck("P"))
    st = _rechteck("S")
    if art == "stummel":
        st.It = kt * l0 / G_W
    m.add_section(st)
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    r = math.radians(90.0)

    def strecke(a_id, b_xyz, nn, sec):
        a = np.array(m.nodes[a_id], float)
        b = np.array(b_xyz, float)
        ids = [a_id] + [m.add_node(*(a + (b - a) * j / nn)) for j in range(1, nn + 1)]
        for j in range(nn):
            m.add_element("beam", [ids[j], ids[j + 1]], "ST", sec, roll=r)
        return ids
    fuss = m.add_node(0, 0, 0)
    a = strecke(fuss, (L, 0, 0), n, "P")
    if l0 > 0:
        a = strecke(a[-1], (L, l0, 0), 1, "S")
    e1 = len(m.elements)
    b = strecke(a[-1], (L, L, 0), n, "P")
    if l0 > 0:
        b = strecke(b[-1], (L - l0, L, 0), 1, "S")
    e2 = len(m.elements)
    c = strecke(b[-1], (0, L, 0), n, "P")
    if art == "feder":
        m.elements[e1].hinge_springs = [(3, kt)]
        m.elements[e2].hinge_springs = [(3, kt)]
    m.fix(fuss, "all")
    m.load_node(c[-1], Fy=-P, Fz=stoer)
    return m, c[-1]


def test_e_federn_konvergieren():
    """Gegenpruefung 1 zu k10d: _Stab._gelenk_lage hoerte an einer groben
    Schranke (1e3 * 2,2e-16 * Drehsteifigkeit, hier etwa 0,0016 Nm) auf; φ
    blieb je nach Startwert um bis zu 4e-7 rad offen, das Federmoment
    rauschte ueber der Konvergenzschranke, und Modelle mit Torsionsfedern
    meldeten „keine Konvergenz“ (U-Rahmen 1 kN, 3 kN) oder „Gleichungssystem
    singulär“, obwohl sie ein Gleichgewicht haben."""
    for P in (1e3, 3e3):
        # Bezug: Stummelmodell, linear nach l0 -> 0 (aus l0 = 0,002 und 0,001 m)
        w = {}
        for l0 in (0.002, 0.001):
            m, sp = u_rahmen("stummel", l0, P=P)
            u, info, _r = _th3_direkt(m, 20)
            w[l0] = u[sp, :3]
        ref = 2.0 * w[0.001] - w[0.002]
        m, sp = u_rahmen("feder", P=P)
        m.add_combination("LK1", {m.active_case: 1.0}, "ULS", theorie="III")
        r, f = _rechne(m)
        th = str((r.info or {}).get("theorie", "")) if r is not None else ""
        u = np.asarray(r.u).reshape(-1, 6) if r is not None else np.full((sp + 1, 6), np.nan)
        d = float(np.abs(u[sp, :3] - ref).max()) * 1e3
        check(f"(e) U-Rahmen, Torsionsfedern 2 kNm/rad, P = {P / 1e3:.0f} kN, Stoerlast 20 N, LK1 ueber "
              "solve_all: Theorie III. Ordnung konvergiert", not f and th.startswith("III"), f"{f!r} {th}")
        check("… Spitze = Stummelmodell mit l0 -> 0 (auf 0,001 mm)", d <= 1e-3,
              f"{d:.6f} mm, Th III uz {u[sp, 2] * 1e3:.6f}, Stummel {ref[2] * 1e3:.6f} mm")
        u40, i40, _r = _th3_direkt(u_rahmen("feder", P=P)[0], 40)
        u10, i10, _r = _th3_direkt(u_rahmen("feder", P=P)[0], 10)
        d = float(np.abs(u10[sp, :3] - u40[sp, :3]).max()) * 1e3
        check("… 10 und 40 Laststufen konvergieren und ergeben dieselbe Spitze (auf 0,0001 mm)",
              not i10.fehler and not i40.fehler and d <= 1e-4, f"{i10.fehler!r} {i40.fehler!r} {d:.6f} mm")
    # Federvariante mit zusaetzlichem Stueck l0 (Gegenpruefung: keine
    # Konvergenz bzw. singulaer), gegen das Stummelmodell: Abstand linear in l0
    for P, stoer, l0, s in ((1e3, 2.0, 0.004, 40), (1e3, 2.0, 0.002, 40), (1e3, 2.0, 0.001, 10),
                            (1e3, 2.0, 0.001, 40), (2e3, 20.0, 0.001, 10), (1e3, 20.0, 0.001, 10)):
        m, sp = u_rahmen("feder", l0, P=P, stoer=stoer)
        uf, i_f, _r = _th3_direkt(m, s)
        us, i_s, _r = _th3_direkt(u_rahmen("stummel", l0, P=P, stoer=stoer)[0], s)
        d = float(np.abs(uf[:, :3] - us[:, :3]).max()) * 1e3
        # Abstand Feder/Stummel waechst linear mit l0 und Last (Gegenpruefung:
        # 0,0176 / 0,0088 / 0,0044 mm bei 1 kN, 20 N); Grenze 20 mm je m l0 und kN
        grenze = 20.0 * l0 * P / 1e3
        check(f"(e) U-Rahmen mit Stueck l0 = {l0} m, P = {P / 1e3:.0f} kN, Stoerlast {stoer:g} N, {s} Stufen: "
              f"Federvariante konvergiert, Abstand zum Stummel unter {grenze:.3f} mm",
              not i_f.fehler and not i_s.fehler and d <= grenze, f"{i_f.fehler!r} {d:.6f} mm")


def test_e_merkmal():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("theorie3_gelenk_achse")
    check("Merkmal theorie3_gelenk_achse: Stand 75, Fehlerkorrektur, 16.11.2026, VERFAHRENSSTAND 75",
          mk is not None and mk.wechsel[-1].stand == 75 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].datum == "16.11.2026" and rv.VERFAHRENSSTAND == 75
          and rv.VERFAHRENSSTAND == max(w.stand for x in rv.MERKMALE for w in x.wechsel),
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return

    def mit(th, art):
        m, _sp = l_rahmen(90.0, 0.02, art=art)
        k = m.add_combination("LK1", {"LF1": 1.0}, "ULS")
        k.theorie = th
        return m
    check("… betrifft: Theorie III. Ordnung mit Torsionsfeder bzw. Torsionsgelenk",
          mk.betrifft(mit("III", "feder")) is True and mk.betrifft(mit("III", "gelenk")) is True)
    check("… nicht: Theorie I. Ordnung mit Feder, Theorie III. Ordnung ohne Gelenk",
          mk.betrifft(mit("I", "feder")) is False and mk.betrifft(mit("III", "stummel")) is False)


def _weich_verteilt(gross, k, rest, faktor=1.0):
    """Weicher Kragarm, ±gross an c auf k + k Beitraege verteilt, Faktor je Beitrag."""
    m, b = weich("III", gross, rest)
    c = m.load_cases["LF2"].nodal_loads[0].node
    fak = {"LF1": 1.0, "LF2": faktor, "LF3": faktor, "LF4": 1.0}
    m.load_cases["LF2"].nodal_loads[0].F = [0.0, 0.0, -gross / k, 0.0, 0.0, 0.0]
    m.load_cases["LF3"].nodal_loads[0].F = [0.0, 0.0, gross / k, 0.0, 0.0, 0.0]
    for j in range(1, k):
        for nm, sg in (("A%d" % j, -1.0), ("B%d" % j, 1.0)):
            m.add_load_case(nm)
            m.load_node(c, Fz=sg * gross / k, case=nm)
            fak[nm] = faktor
    m.combinations["LK1"].factors = dict(fak)
    return m, b, fak


def test_a_exakte_summe():
    """Gegenpruefung 2 zu k10d: mit 4 * n * 2,2e-16 der Betragssumme ging ein
    Rest von 0,0009 N ab ±2e11 N (einzeln) bzw. ±5e10 N (auf 10 + 10
    Beitraege verteilt) wieder still verloren (Theorie III. Ordnung 1,587302
    statt 1,588730 mm). Jetzt exakte Summe der Produkte, Schranke nur aus der
    Darstellung der nicht exakt darstellbaren Eingaben."""
    from statik3d import rechenverfahren as rv
    from statik3d.theorie3 import kopplung_sperre
    mk = rv.merkmal("theorie3_stabende_anschluss")
    faelle = [(g, 1, 0.0009, 1.0) for g in (2e11, 3e11, 5e11, 1e12, 3e12)]
    faelle += [(2e11, 1, 0.0007, 1.0), (5e10, 10, 0.0009, 1.0), (1e12, 1, 0.0009, 1.35),
               (1e11, 10, 0.0009, 1.35)]
    for gross, k, rest, faktor in faelle:
        hand = (1.0 + rest) * FLEX_W
        m, b, fak = _weich_verteilt(gross, k, rest, faktor)
        m.combinations["LK1"].theorie = "I"
        r1, _f = _rechne(m)
        w1 = -np.asarray(r1.u).reshape(-1, 6)[b, 2]
        txt = f"(a) ±{gross:.0f} N auf {k} + {k} Beitraege, Faktor {faktor}, Rest {rest} N"
        check(f"{txt}: Theorie I. Ordnung loest den Rest auf (naeher an der Hand als ohne Rest)",
              abs(w1 - hand) < abs(w1 - FLEX_W), f"{w1 * 1e3:.6f} mm, Hand {hand * 1e3:.6f} mm")
        m, b, fak = _weich_verteilt(gross, k, rest, faktor)
        t = kopplung_sperre(m, None, factors=fak)
        r3, f3 = _rechne(m)
        w3 = -np.asarray(r3.u).reshape(-1, 6)[b, 2] if r3 is not None else float("nan")
        check(f"… Theorie III. Ordnung weist ab statt still ohne Rest zu rechnen "
              f"(stille Abweichung waere {rest * FLEX_W * 1e3:.6f} mm)",
              TEXT_KP in t and TEXT_KP in f3, f"{t[:40]!r} {f3[:40]!r} {w3 * 1e3:.6f} mm")
        check("… Merkmal theorie3_stabende_anschluss betrifft",
              mk.betrifft(_weich_verteilt(gross, k, rest, faktor)[0]) is True)
    # Gegenproben: Reste aus der Rundung dezimal aufgehobener Summen bleiben
    # aufgehoben, auch bei grossen Lasten und mit Punktmasse unter g
    for gross, f2, f3_, last2, last3 in ((1e12, 0.1, 0.3, -3.0, 1.0), (3e12, 0.1, 0.3, -3.0, 1.0),
                                         (1e11, 1.35, 0.45, -1.0, 3.0), (7e11, 0.7, 0.35, 1.0, -2.0),
                                         (1e12, 1.35, 1.35, -1.0, 1.0)):
        m, b = weich("III", 1.0, 0.0)
        m.load_cases["LF2"].nodal_loads[0].F = [0.0, 0.0, last2 * gross, 0.0, 0.0, 0.0]
        m.load_cases["LF3"].nodal_loads[0].F = [0.0, 0.0, last3 * gross, 0.0, 0.0, 0.0]
        faktoren = {"LF1": 1.0, "LF2": f2, "LF3": f3_, "LF4": 1.0}
        m.combinations["LK1"].factors = dict(faktoren)
        S = f2 * last2 * gross + f3_ * last3 * gross
        t = kopplung_sperre(m, None, factors=faktoren)
        r3, f3 = _rechne(m)
        w3 = -np.asarray(r3.u).reshape(-1, 6)[b, 2] if r3 is not None else float("nan")
        check(f"(a) Gegenprobe {f2} * {last2 * gross:.0f} N + {f3_} * {last3 * gross:.0f} N (Rest {S:.3g} N, "
              "Rundung): nicht abgewiesen, w(b) = Hand", not t and not f3 and abs(w3 - FLEX_W) <= 1e-5 * FLEX_W,
              f"{t[:40]!r} {f3[:40]!r} {w3 * 1e3:.6f} mm")
    from decimal import Decimal
    for masse, f in ((101.94, 1.35), (1234.567, 1.0), (3.3e9, 0.9)):
        m, b = weich("III", 1.0, 0.0)
        c = m.load_cases["LF2"].nodal_loads[0].node
        m.load_cases["LF2"].nodal_loads = []
        m.load_cases["LF3"].nodal_loads = []
        m.add_punktmasse(c, masse)
        m.set_gravity(-9.81, case="LF2")
        m.load_node(c, Fz=float(Decimal(repr(masse)) * Decimal("9.81")), case="LF3")
        faktoren = {"LF1": 1.0, "LF2": f, "LF3": f, "LF4": 1.0}
        m.combinations["LK1"].factors = dict(faktoren)
        t = kopplung_sperre(m, None, factors=faktoren)
        r3, f3 = _rechne(m)
        w3 = -np.asarray(r3.u).reshape(-1, 6)[b, 2] if r3 is not None else float("nan")
        check(f"(a) Gegenprobe Punktmasse {masse} kg unter g = 9,81, aufgehoben durch {masse} * 9,81 N, "
              f"Faktor {f}: nicht abgewiesen, w(b) = Hand", not t and not f3 and abs(w3 - FLEX_W) <= 1e-5 * FLEX_W,
              f"{t[:40]!r} {f3[:40]!r} {w3 * 1e3:.6f} mm")
    # Zufallskombinationen mit dezimal genau aufgehobenen Lasten (wie die
    # Gegenpruefung, q_schranke.py): bei Betragssummen unter 1e12 N nie ein
    # Lastknoten, mit 0,0009 N Rest unter 5e11 N immer einer. Darueber
    # erreicht die Schranke (bis zu 1,1e-15 der Betragssumme, wenn die
    # letzte Last 17 Stellen hat) die Kappung 0,001 N bzw. den Rest, und Rest
    # und Rundung sind nicht mehr zu trennen
    import random
    from types import SimpleNamespace as NS
    from statik3d.theorie3 import _lastknoten
    D = Decimal
    random.seed(7)
    fk = ["0.1", "0.3", "0.7", "1.35", "1.5", "0.9", "0.6", "1.05", "0.8", "0.15", "0.35", "1.1", "1", "1.2"]
    falsch_auf = falsch_ab = 0
    for _ in range(3000):
        n = random.randint(2, 12)
        fs = [random.choice(fk) for _ in range(n)]
        ls = [D(random.randint(1, 10 ** 6)) / D(random.choice([1, 10, 100, 1000])) * D(10) ** random.randint(-3, 8)
              * random.choice([-1, 1]) for _ in range(n - 1)]
        s = sum(D(f) * x for f, x in zip(fs[:-1], ls))
        ls.append(-s / D(fs[-1]))
        for rest in (0.0, 0.0009):
            lcs, fak = {}, {}
            for j, (f, x) in enumerate(zip(fs, ls)):
                lcs["L%d" % j] = NS(nodal_loads=[NS(node=0, F=[0.0, 0.0, float(x), 0.0, 0.0, 0.0])], gravity=None)
                fak["L%d" % j] = float(f)
            if rest:
                lcs["R"] = NS(nodal_loads=[NS(node=0, F=[0.0, 0.0, rest, 0.0, 0.0, 0.0])], gravity=None)
                fak["R"] = 1.0
            ist = bool(_lastknoten(NS(load_cases=lcs, punktmassen=[]), 1, fak)[0])
            summe = sum(abs(float(f) * float(x)) for f, x in zip(fs, ls))
            if not rest and ist and summe < 1e12:
                falsch_auf += 1
            if rest and not ist and summe < 5e11:
                falsch_ab += 1
    check("(a) 3000 Zufallskombinationen: dezimal aufgehobene Summen nie Lastknoten, Rest 0,0009 N "
          "immer (Betragssumme unter 1e12 bzw. 5e11 N)", falsch_auf == 0 and falsch_ab == 0,
          f"aufgehoben als Last {falsch_auf}, Rest uebersehen {falsch_ab}")


TESTS = [test_a_restschranke, test_a_grosse_betragssumme, test_a_exakte_summe, test_b_kleine_last, test_c_ipe_vorverformung, test_c_hallenreihe,
         test_d_kurze_elemente, test_e_torsionsfeder, test_e_torsionsgelenk, test_e_symmetrie, test_e_merkmal,
         test_e_federn_konvergieren]


def main():
    for t in TESTS:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
