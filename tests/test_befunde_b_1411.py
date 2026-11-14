"""
Behebungen vom 14.11.2026, Gruppe B der Befundliste (BEFUNDE-2026-11-14.md):
Schalenbeulen unter Umfangsdruck (C1), f_y/f_u ueber 80 mm ohne Dickentabelle
(C4), Beulfeld bei gegenlaeufiger Elementnormale (B7), Anschlussbleche mit
ihrer Dicke (B8), Anschlussmeldungen ab 0 (B13), Ermuedung der Schrauben ueber
M30 (C5) und I_w der U-Profile (C6).

Zwei Wege je Zahl: Handrechnung bzw. geschlossene Loesung gegen das Programm,
beim Beulfeld die Projektion u.S.u gegen den physikalisch gleichen Fall mit
gleichlaeufiger Normale, beim U-Profil die numerisch integrierte
Woelbordinate.

Aufruf:  python -m tests.test_befunde_b_1411
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
E = 210e9


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def close(name, ist, soll, tol, einheit=""):
    return check(name, abs(ist - soll) <= tol, f"ist {ist:.6g}, soll {soll:.6g}{einheit}")


# --------------------------------------------------------------------------
# C1: Umfangsbeulspannung nach EN 1993-1-6, D.1.3.1
# --------------------------------------------------------------------------
def test_c1_umfang():
    from statik3d.ec3 import schalenbeulen as S
    r, t = 1.0, 0.010                     # r/t = 100
    # langer Zylinder, BC2-BC2 (C_theta = 1): l = 100 m, omega = 1000 > 163
    d = S.sigma_theta_Rcr(100.0, r, t, "BC2-BC2")
    w = 100.0 / math.sqrt(r * t)
    hand = E * (t / r) ** 2 * (0.275 + 2.03 * (1.0 * r / (w * t)) ** 4)
    close("C1 langer Zylinder: σθ,Rcr = E (t/r)² [0,275 + 2,03 (Cθ r/(ω t))⁴]",
          d["sigma_Rcr"] / 1e6, hand / 1e6, 1e-9, " N/mm²")
    close("C1 … 5,78 N/mm² (Beleg)", d["sigma_Rcr"] / 1e6, 5.78, 0.005, " N/mm²")
    # zweiter Weg: Ringbeulen (Bresse) als Grenzwert des sehr langen Zylinders
    ring = E * t ** 2 / (4 * (1 - 0.3 ** 2) * r ** 2)
    check("C1 … und liegt beim Ringbeulen E t²/(4(1−ν²) r²) (unter 0,2 %)",
          abs(d["sigma_Rcr"] / ring - 1.0) < 0.002, f"{ring / 1e6:.3f} N/mm²")
    check("C1 … Bereich „lang“", d["bereich"] == "lang", d["bereich"])
    # mittellang, BC2-BC2: l = 6 m, omega = 60
    d6 = S.sigma_theta_Rcr(6.0, r, t, "BC2-BC2")
    close("C1 mittellang BC2-BC2: 0,92 E (Cθ/ω)(t/r) = 32,2 N/mm²", d6["sigma_Rcr"] / 1e6,
          0.92 * 210e3 * (1.0 / 60.0) * 0.01, 1e-9, " N/mm²")
    # Randbedingung BC1-BC1: C_theta = 1,5 (Tab. D.3)
    d6a = S.sigma_theta_Rcr(6.0, r, t, "BC1-BC1")
    close("C1 mittellang BC1-BC1: Cθ = 1,5 -> 48,3 N/mm²", d6a["sigma_Rcr"] / 1e6,
          0.92 * 210e3 * (1.5 / 60.0) * 0.01, 1e-9, " N/mm²")
    d6b = S.sigma_theta_Rcr(6.0, r, t, "BC1-BC2")
    close("C1 mittellang BC1-BC2: Cθ = 1,25", d6b["sigma_Rcr"] / 1e6,
          0.92 * 210e3 * (1.25 / 60.0) * 0.01, 1e-9, " N/mm²")
    # kurz, BC2-BC2: omega = 10 < 20, C_theta,s = 1 + 3/omega^1,35
    l = 10.0 * math.sqrt(r * t)
    dk = S.sigma_theta_Rcr(l, r, t, "BC2-BC2")
    Cts = 1.0 + 3.0 / 10.0 ** 1.35
    close("C1 kurz BC2-BC2: 0,92 E (Cθs/ω)(t/r), Cθs = 1 + 3/ω^1,35", dk["sigma_Rcr"] / 1e6,
          0.92 * 210e3 * Cts / 10.0 * 0.01, 1e-9, " N/mm²")
    # Bereichsgrenzen am Umfangsdruck, nicht am Meridiandruck: omega = 60 ist
    # fuer den Meridiandruck „lang“ (> 0,5 r/t = 50), fuer den Umfangsdruck mittel
    check("C1 Bereich des Umfangsdrucks eigenständig (ω = 60: Meridian lang, Umfang mittel)",
          S.laengenbereich(6.0, r, t) == "lang" and d6["bereich"] == "mittel",
          f"{S.laengenbereich(6.0, r, t)}/{d6['bereich']}")
    # Stetigkeit an den Grenzen (Plausibilitaet der Formeln je Randbedingung)
    for rand, Ct in (("BC1-BC1", 1.5), ("BC1-BC2", 1.25), ("BC2-BC2", 1.0)):
        a = S.sigma_theta_Rcr(1.63 * Ct * r / t * math.sqrt(r * t) * (1 - 1e-9), r, t, rand)["sigma_Rcr"]
        b = S.sigma_theta_Rcr(1.63 * Ct * r / t * math.sqrt(r * t) * (1 + 1e-9), r, t, rand)["sigma_Rcr"]
        check(f"C1 {rand}: mittel/lang an ω/Cθ = 1,63 r/t stetig (unter 0,5 %)",
              abs(a / b - 1) < 0.005, f"{a / 1e6:.3f}/{b / 1e6:.3f} N/mm²")
    # Nachweis: l = 100 m, sigma_theta = 20 N/mm², S355, BC2-BC2
    z = S.zylinder(r, t, 100.0, 355e6, sigma_theta=20e6, rand="BC2-BC2")
    lam = math.sqrt(355e6 / hand)
    chi = 0.65 / lam ** 2
    eta = 20e6 / (chi * 355e6 / 1.1)
    close("C1 Nachweis: η_θ = σθ,Ed/(χ f_y/γ_M1) = 5,86 (vorher 0,06)", z.werte["umfang"]["eta"],
          eta, 1e-6)
    check("C1 … und nicht erfüllt", z.status() == "NICHT erfüllt", z.status())


# --------------------------------------------------------------------------
# C4: f_y/f_u ueber 80 mm ohne Dickentabelle
# --------------------------------------------------------------------------
def test_c4_werkstoff():
    from statik3d.model import Material
    s = Material.steel("S355")
    close("C4 S355 nur Sorte, 60 mm: f_y 335 (Tab. 3.1, unverändert)", s.yield_strength(0.060) / 1e6,
          335.0, 1e-9, " N/mm²")
    close("C4 … 80 mm: f_y 335 (Zeile 40 < t ≤ 80 mm)", s.yield_strength(0.080) / 1e6, 335.0, 1e-9,
          " N/mm²")
    check("C4 … 90 mm: kein f_y (0)", not s.yield_strength(0.090), f"{s.yield_strength(0.090) / 1e6:g}")
    check("C4 … 200 mm: kein f_y (vorher 335)", not s.yield_strength(0.200))
    check("C4 … 200 mm: kein f_u (zugfestigkeit_angegeben None, ultimate_strength 0)",
          s.zugfestigkeit_angegeben(0.200) is None and not s.ultimate_strength(0.200))
    m = s.dicke_ohne_wert(0.200, "fy")
    check("C4 … Meldung „f_y nach Erzeugnisnorm eintragen“", "f_y nach Erzeugnisnorm eintragen" in m
          and "200 mm" in m, m)
    check("C4 … für f_u entsprechend", "f_u nach Erzeugnisnorm eintragen" in s.dicke_ohne_wert(0.2, "fu"))
    check("C4 … bis 80 mm keine Meldung", s.dicke_ohne_wert(0.080, "fy") == "")
    # Werkstoff mit Dickentabelle (RFEM): unveraendert
    r = Material.steel("S355", name="S355 RFEM")
    r.fy_dicke = [[0.016, 355e6], [0.040, 345e6], [0.063, 335e6], [0.080, 325e6], [0.100, 315e6],
                  [0.150, 295e6], [0.200, 285e6], [0.250, 275e6], [0.400, 265e6]]
    close("C4 mit Dickentabelle, 200 mm: 285 wie bisher", r.yield_strength(0.200) / 1e6, 285.0, 1e-9,
          " N/mm²")
    check("C4 … und keine Meldung", r.dicke_ohne_wert(0.200, "fy") == "")
    # Werkstoff ohne Sorte (eigener Wert): unveraendert
    o = Material("eigen", 210e9, 0.3, 7850.0, 1.2e-5, 300e6, 450e6, "")
    close("C4 ohne Sorte, eigenes f_y 300 bei 200 mm: unverändert", o.yield_strength(0.2) / 1e6, 300.0,
          1e-9, " N/mm²")


def _stab_modell(tf=0.090):
    from statik3d.model import Model, Material, Section
    from statik3d import mesher
    m = Model("C4")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.i_profile("I dick", 0.500, 0.300, 0.040, tf))
    ids = mesher.line_of_beams(m, "S355", "I dick", (0, 0, 0), (4, 0, 0), n=4)
    if not m.members:
        m.add_member("S1", list(range(len(m.elements))))
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fz=-50e3)
    return m


def test_c4_nachweise():
    from statik3d import solver
    from statik3d.ec3.design import check_member
    m = _stab_modell(0.090)
    an = solver.solve_all(m, workers=1, combinations=False)
    res = {k: v for k, v in an.cases.items()}
    mem = next(iter(m.members.values()))
    mc = check_member(m, mem, res)
    check("C4 Stabnachweis, Flansch 90 mm: nicht geführt, Meldung", bool(mc.fehler)
          and "f_y nach Erzeugnisnorm eintragen" in mc.fehler, mc.fehler)
    m2 = _stab_modell(0.060)
    an2 = solver.solve_all(m2, workers=1, combinations=False)
    mc2 = check_member(m2, next(iter(m2.members.values())), dict(an2.cases))
    check("C4 … Flansch 60 mm: geführt wie bisher", not mc2.fehler, mc2.fehler)
    # Merkmal
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("festigkeit_ueber_80")
    check("C4 Merkmal Stand 45, Fehlerkorrektur, betrifft 90 mm ja, 60 mm nein",
          mk is not None and mk.wechsel[-1].stand == 45 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.betrifft(m) and not mk.betrifft(m2))


def test_c4_beulfeld_und_volumen():
    from statik3d.model import Model, Material, ShellProp
    from statik3d.ec3 import beulen
    from statik3d.ec3 import volumen
    m = Model("B")
    m.add_material(Material.steel("S355"))
    m.add_shell_prop(ShellProp("t90", 0.090))
    ids = [m.add_node(x, y, 0.0) for y in (0.0, 1.0) for x in (0.0, 1.0)]
    e = m.add_element("shell4", [ids[0], ids[1], ids[3], ids[2]], "S355", "t90")
    m.add_beulfeld("F", [e])
    r = beulen.check_beulfeld(m, m.beulfelder["F"], res=None)
    check("C4 Beulfeld 90 mm: nicht geführt, Meldung statt 235/335",
          "f_y nach Erzeugnisnorm eintragen" in r.get("fehler", ""), r.get("fehler", "")[:90])
    meld = volumen._dicke_ohne_wert(m, [e], 0.2)
    check("C4 Volumennachweis: Meldung bei 200 mm Erzeugnisdicke", "Erzeugnisnorm" in meld, meld[:60])


# --------------------------------------------------------------------------
# B7: Beulfeld mit gegenlaeufiger Elementnormale
# --------------------------------------------------------------------------
def _feld(winkel_grad, normale_unten, a=2.0, b=1.0, t=0.008, nx=8, ny=4):
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
            if normale_unten:
                e = [e[0], e[3], e[2], e[1]]
            els.append(m.add_element("shell4", e, "S355", "t"))
    for j in range(ny + 1):
        m.fix(ids[(0, j)], "all")
    F = 200e3
    for j in range(ny + 1):
        f = F * (0.5 if j in (0, ny) else 1.0) / ny
        m.load_node(ids[(nx, j)], Fx=-f * c, Fy=-f * s)
    m.add_beulfeld("F", els)
    an = solver.solve_all(m, combinations=False, envelopes=False, design=True, workers=1)
    return m, an, els


def test_b7_beulfeld():
    from statik3d.ec3 import beulen
    werte = {}
    for unten in (False, True):
        m, an, els = _feld(30.0, unten)
        w = an.beulen.felder["F"].werte
        werte[unten] = (w["sigma_x"], w["sigma_z"], w["tau"])
        # zweiter Weg je Element: Tensor S im Flaechensystem, sigma_u = u.S.u
        res = an.cases[list(an.cases)[0]]
        _mi, u, v, _n, _L1, _L2, _eb = beulen._rahmen(m, els)
        worst = 0.0
        for i in els:
            p = beulen.feldspannungen(m, res, [i], u, v)
            d = res.shell_stress[i]
            T3 = np.asarray(d["T3"])
            tt = m.shells[m.elements[i].sec].t
            sx, sy, txy = np.asarray(d["n"], float) / tt
            S = (sx * np.outer(T3[0], T3[0]) + sy * np.outer(T3[1], T3[1])
                 + txy * (np.outer(T3[0], T3[1]) + np.outer(T3[1], T3[0])))
            ist = (-p["sigma_u_max"], -p["sigma_v_max"], p["tau"])
            soll = (float(u @ S @ u), float(v @ S @ v), abs(float(u @ S @ v)))
            worst = max(worst, max(abs(a - b) for a, b in zip(ist, soll)) / 1e6)
        check(f"B7 Feld 30°, Normale {'−Z' if unten else '+Z'}: je Element wie u·S·u (unter 0,001 N/mm²)",
              worst < 1e-3, f"{worst:.4f} N/mm²")
    close("B7 Feld 30°, Normale −Z: σ_u 25,867 N/mm² wie bei +Z (vorher 11,675)",
          werte[True][0] / 1e6, werte[False][0] / 1e6, 1e-3, " N/mm²")
    close("B7 … σ_v wie bei +Z (4,809)", werte[True][1] / 1e6, werte[False][1] / 1e6, 1e-3, " N/mm²")
    close("B7 … τ wie bei +Z (2,563)", werte[True][2] / 1e6, werte[False][2] / 1e6, 1e-3, " N/mm²")
    close("B7 … Wert 25,867 N/mm² (Beleg)", werte[True][0] / 1e6, 25.867, 2e-3, " N/mm²")
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("beulfeld_normale")
    m_u, _a, _e = _feld(30.0, True)
    m_o, _a, _e = _feld(30.0, False)
    m_0, _a, _e = _feld(0.0, True)
    check("B7 Merkmal Stand 45: betrifft 30°/−Z, nicht 30°/+Z, nicht 0°/−Z",
          mk is not None and mk.wechsel[-1].stand == 45 and mk.betrifft(m_u) and not mk.betrifft(m_o)
          and not mk.betrifft(m_0))


# --------------------------------------------------------------------------
# B8 und B13: Anschluss
# --------------------------------------------------------------------------
def _kopfplatte_modell():
    from statik3d.model import Model, Material, Section
    from statik3d import mesher, solver
    m = Model("A")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.i_profile("IPE300", 0.300, 0.150, 0.0071, 0.0107))
    ids = mesher.line_of_beams(m, "S355", "IPE300", (0, 0, 0), (4, 0, 0), n=4)
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fz=-20000.0)
    solver.solve_all(m, workers=1, combinations=False)
    return m


def test_b8_blechdicke():
    from statik3d.joints import anschluss, templates
    from statik3d.joints.tstub import TStub, effective_lengths
    m = _kopfplatte_modell()
    t = templates.propose("kopfplatte", m, 0, end=0, N=0.0, Vz=20000.0, My=80000.0)
    t.tp = 0.050
    j = anschluss.als_joint(t, name="KP50")
    m.joints[j.name] = j
    v = anschluss.vorlage(m, j)
    jc = v.design(N=0.0, Vz=20000.0, My=80000.0)
    naht = next(c for c in jc.checks if c.name.startswith("Kehlnaht am Flansch: Vergleich"))
    close("B8 Kehlnaht an Kopfplatte 50 mm: f_u/(β_w γ_M2) = 470/(0,9·1,25) = 417,78 N/mm² (vorher 453,33)",
          naht.R / 1e6, 470.0 / (0.9 * 1.25), 1e-6, " N/mm²")
    # T-Stummel mit f_y 335 der 50-mm-Platte, zweiter Weg: TStub von Hand
    tw = 0.0071
    m_arm = max(0.5 * (v.w - tw) - 0.8 * v.a_w * math.sqrt(2), 0.5 * v.bolt.d0)
    e_arm = 0.5 * (v.bp - v.w)
    le = effective_lengths("innen", m=m_arm, e=e_arm)
    soll = TStub(t=v.tp, fy=335e6, m=m_arm, e=e_arm, leff_cp=le["cp"], leff_nc=le["nc"],
                 Ft_Rd=v.bolt.Ft_Rd(), n_bolts=2, gamma_M0=v.gamma_M0).resistance()["F_T_Rd"]
    ts = next(c for c in jc.checks if c.name.startswith("T-Stummel"))
    close("B8 T-Stummel mit f_y 335 der Platte (von Hand)", ts.R / 1e3, soll / 1e3, 1e-6, " kN")
    # Stab unveraendert: Druckflansch mit f_y 355 (t_f 10,7 mm)
    dr = next(c for c in jc.checks if c.name.startswith("Druckflansch"))
    close("B8 Druckflansch des Trägers mit f_y 355 (Stab)", dr.R / 1e3, 0.150 * 0.0107 * 355e6 / 1e3,
          1e-6, " kN")
    # Platte 20 mm: alles wie bisher (f_u 510)
    v.tp = 0.020
    jc2 = v.design(N=0.0, Vz=20000.0, My=80000.0)
    naht2 = next(c for c in jc2.checks if c.name.startswith("Kehlnaht am Flansch: Vergleich"))
    close("B8 Platte 20 mm: Naht 510/(0,9·1,25) = 453,33 wie bisher", naht2.R / 1e6, 453.333333, 1e-3,
          " N/mm²")
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("anschluss_blechdicke")
    ja = mk is not None and mk.betrifft(m)
    m.joints[j.name].geometrie["tp"] = 0.020
    nein = mk is not None and not mk.betrifft(m)
    check("B8 Merkmal Stand 45: betrifft Platte 50 mm, nicht 20 mm",
          mk is not None and mk.wechsel[-1].stand == 45 and ja and nein)


def test_b13_meldungen():
    from statik3d.model import Model, Material, Section, Joint
    from statik3d.joints import anschluss
    m = Model("A")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.i_profile("IPE300", 0.300, 0.150, 0.0071, 0.0107))
    for p in [(0, 0, 0), (1, 0, 0), (2, 0, 0)]:
        m.add_node(*p)
    m.add_element("beam", [0, 1], "S355", "IPE300")
    m.add_element("beam", [1, 2], "S355", "IPE300")
    m.elements[0].sec = ""
    try:
        anschluss.vorlage(m, Joint("J", "kopfplatte", 0, 0))
        text = ""
    except ValueError as ex:
        text = str(ex)
    check("B13 Element 0 ohne Querschnitt: Meldung nennt Element 0 (vorher 1)",
          text == "Element 0 hat keinen Querschnitt", text)
    # ohne Ergebnis: „keine Stabendschnittgroessen fuer Element 1“ an Element 1
    m.elements[0].sec = "IPE300"
    from statik3d.joints import templates
    t = templates.EndPlate(name="J1", model=m, elem=1, end=0, grade="S355",
                           sec=m.sections["IPE300"], rows=[0.1, -0.1])
    m.joints["J1"] = anschluss.als_joint(t, name="J1")
    c = anschluss.check_joint(m, m.joints["J1"], {}, None)
    check("B13 ohne Ergebnis: Meldung nennt Element 1 (vorher 2)",
          "für Element 1 " in (c.fehler or ""), c.fehler)


# --------------------------------------------------------------------------
# C5: Ermuedung Schrauben ueber M30
# --------------------------------------------------------------------------
def _N_hand(dsig, dc, gMf=1.15):
    # Knickpunkte exakt: Delta_sigma_D = (2/5)^(1/3) Delta_sigma_C bei 5e6,
    # Delta_sigma_L = (5/100)^(1/5) Delta_sigma_D bei 1e8 (EN 1993-1-9, 7.1(3))
    dc = dc / gMf
    dD = (2.0 / 5.0) ** (1.0 / 3.0) * dc
    dL = (5.0 / 100.0) ** 0.2 * dD
    if dsig >= dD:
        return 2e6 * (dc / dsig) ** 3
    if dsig >= dL:
        return 5e6 * (dD / dsig) ** 5
    return math.inf


def test_c5_schrauben():
    from statik3d.joints.design import fatigue_check
    from statik3d.joints.bolts import Bolt
    b = Bolt("M36", "10.9")
    dF = 15e3
    r = fatigue_check("schraube_zug", [(dF, 2e6)], area=b.As, gamma_Mf=1.15, d=b.d)
    ks = (30.0 / 36.0) ** 0.25
    close("C5 M36: Kerbfall 50·(30/36)^0,25 = 47,8", r["kerbfall"], 50.0 * ks, 1e-9, " N/mm²")
    D = 2e6 / _N_hand(dF / b.As, 50e6 * ks)
    close("C5 M36: D = 0,031 (Wöhlerlinie von Hand; vorher 0,025)", r["schaedigung"], D, 1e-9)
    close("C5 … gerundet 0,031", round(r["schaedigung"], 3), 0.031, 1e-12)
    b30 = Bolt("M30", "10.9")
    r30 = fatigue_check("schraube_zug", [(dF, 2e6)], area=b30.As, gamma_Mf=1.15, d=b30.d)
    close("C5 M30: Kerbfall 50 unverändert", r30["kerbfall"], 50.0, 1e-12)
    # Vorschlag fuer Zugstaebe mit Rundquerschnitt
    from types import SimpleNamespace as NS
    from statik3d.model import Section
    from statik3d.ec3 import kerbfaelle as kf
    m = NS(elements=[NS(typ="truss", sec="Rd50")], sections={"Rd50": Section.circle("Rd50", 0.050)})
    v = kf.vorschlag_stab(m, NS(elements=[0], name="Z1"))
    close("C5 Vorschlag Rund 50: 50·(30/50)^0,25 = 44,0 N/mm²", v.kerbfall / 1e6, 50 * (30 / 50) ** 0.25,
          1e-9, " N/mm²")
    m20 = NS(elements=[NS(typ="truss", sec="Rd20")], sections={"Rd20": Section.circle("Rd20", 0.020)})
    close("C5 Vorschlag Rund 20: 50 unverändert", kf.vorschlag_stab(m20, NS(elements=[0], name="Z")).kerbfall
          / 1e6, 50.0, 1e-12, " N/mm²")
    from statik3d import rechenverfahren as rv
    for name in ("ermuedung_schraube_ks", "kerbfall_vorschlag_ks"):
        mk = rv.merkmal(name)
        check(f"C5 Merkmal {name}: Stand 45, Fehlerkorrektur",
              mk is not None and mk.wechsel[-1].stand == 45 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR)


# --------------------------------------------------------------------------
# C6: I_w der U-Profile
# --------------------------------------------------------------------------
def _iw_sektor(h, b, tw, tf, n=4000):
    """Woelbordinate numerisch auf der Mittellinie (Schubmittelpunkt aus I_yw = 0)."""
    bs, hs = b - tw / 2, h - tf
    s1 = np.linspace(0, bs, n)
    s2 = np.linspace(0, hs, n)
    s3 = np.linspace(0, bs, n)
    y = np.r_[bs - s1, 0 * s2, s3]
    z = np.r_[hs / 2 + 0 * s1, hs / 2 - s2, -hs / 2 + 0 * s3]
    t = np.r_[tf + 0 * s1, tw + 0 * s2, tf + 0 * s3]
    P = np.c_[y, z]
    ds = np.r_[np.diff(s1, prepend=0), np.diff(s2, prepend=0), np.diff(s3, prepend=0)]
    dP = np.diff(P, axis=0, prepend=P[:1])
    cr = P[:, 0] * dP[:, 1] - P[:, 1] * dP[:, 0]
    cr[n] = 0
    cr[2 * n] = 0
    om = -np.cumsum(cr)
    dA = t * ds
    A = dA.sum()
    Iz = (dA * z ** 2).sum()
    om = om - (dA * om).sum() / A
    om2 = om - (dA * om * z).sum() / Iz * z
    om2 = om2 - (dA * om2).sum() / A
    return (dA * om2 ** 2).sum()


def test_c6_u_profil():
    from statik3d.profiles import make_section, UPN, UPE
    # Angepasst am 14.11.2026 (Befund B'2, zweite Runde): der UPN aus der Profiltabelle
    # traegt jetzt I_w mit Flanschneigung (9 559,6 cm⁶, tests.test_ermuedung_k6_1411).
    # Die Pruefung von C6 (Mittellinie b - t_w/2) gilt weiter fuer gleich dicke
    # Flansche - hier an einem U mit den UPN-200-Massen und parallelen Flanschen
    from statik3d.model import Section
    for name, tab in (("UPN 200", UPN[200]), ("UPE 200", UPE[200]), ("UPE 300", UPE[300])):
        h, b, tw, tf, _r = [x * 1e-3 for x in tab]
        s = (Section.channel("U parallel", h, b, tw, tf, _r) if name.startswith("UPN")
             else make_section(name))
        soll = _iw_sektor(h, b, tw, tf)
        check(f"C6 {name}: I_w wie die numerisch integrierte Wölbordinate (unter 0,1 %)",
              abs(s.Iw / soll - 1) < 1e-3, f"{s.Iw * 1e12:.0f} gegen {soll * 1e12:.0f} cm⁶")
    h, b, tw, tf, _r = [x * 1e-3 for x in UPN[200]]
    s = Section.channel("U parallel", h, b, tw, tf, _r)
    close("C6 UPN-200-Maße, parallele Flansche: 10 499 cm⁶ (vorher 12 277)", round(s.Iw * 1e12), 10499.0, 1.0,
          " cm⁶")
    from statik3d.ec3 import woelb as W
    sw = W.sektorwerte(s)
    close("C6 Wölbordinaten: I_w aus ∫ω² t ds trifft den Querschnitt", sw.Iw_probe, s.Iw, s.Iw * 1e-6,
          " m⁶")
    # gespeicherter Querschnitt mit dem alten Wert: Merkmal am Modell
    from statik3d.model import Model, Material, iw_u_profil_alt
    from statik3d import rechenverfahren as rv
    m = Model("U")
    m.add_material(Material.steel("S235"))
    alt = make_section("UPN 200")
    alt.Iw = iw_u_profil_alt(alt.h, alt.b, alt.tw, alt.tf)
    m.add_section(alt)
    n0, n1 = m.add_node(0, 0, 0), m.add_node(3, 0, 0)
    m.add_element("beam", [n0, n1], "S235", alt.name)
    mk = rv.merkmal("u_profil_iw")
    text = rv.modell_betroffen(m)
    check("C6 Merkmal Stand 45: alter Wert im Modell -> Status „neu zuweisen“",
          # wechsel[0]: seit dem 14.11.2026 (Befund B'2) folgt ein zweiter Wechsel mit Stand 51
          mk is not None and mk.wechsel[0].stand == 45 and "Profiltabelle neu zuweisen" in text, text[:120])
    m.sections[alt.name].Iw = make_section("UPN 200").Iw
    check("C6 … neu zugewiesen: kein Status mehr", "U-Profile" not in rv.modell_betroffen(m))


def test_verfahrensstand():
    from statik3d import rechenverfahren as rv
    check("Verfahrensstand 45", rv.VERFAHRENSSTAND >= 45, str(rv.VERFAHRENSSTAND))
    mk = rv.merkmal("schalenbeulen_umfang")
    check("C1 Merkmal Stand 45, Fehlerkorrektur", mk is not None and mk.wechsel[-1].stand == 45
          and mk.wechsel[-1].art == rv.FEHLERKORREKTUR)


def main():
    for t in (test_c1_umfang, test_c4_werkstoff, test_c4_nachweise, test_c4_beulfeld_und_volumen,
              test_b7_beulfeld, test_b8_blechdicke, test_b13_meldungen, test_c5_schrauben,
              test_c6_u_profil, test_verfahrensstand):
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
