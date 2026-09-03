"""
Anschluesse: Schrauben, Schweissnaehte, T-Stummel und die FE-Abbildung mit
Vorspannung, Reibung und Lochspiel.

Geprueft wird gegen die Zahlenwerte der EN 1993-1-8 (Tab. 3.1, 3.4, 3.6, 4.1,
6.2) und gegen Handrechnungen; die FE-Abbildung wird gegen das mechanische
Verhalten geprueft (Klemmkraftabbau, Gleiten bei mu*N, Durchfahren des
Lochspiels, Lochleibung).

Aufruf:  python -m tests.test_joints
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver  # noqa: E402
from statik3d.model import Model, Material, Section  # noqa: E402
from statik3d.joints.bolts import (Bolt, BoltGeometry, block_tearing,  # noqa: E402
                                   beta_Lf, check_spacing, min_spacing, SIZES, GRADES)
from statik3d.joints.welds import (Fillet, Butt, fvw_d, beta_w, min_throat,  # noqa: E402
                                   max_throat, WeldSegment, weld_group_properties,
                                   weld_group_stress)
from statik3d.joints.tstub import TStub, effective_lengths  # noqa: E402
from statik3d.joints.build import add_bolt, plate_shells, plate_solid  # noqa: E402
from statik3d.joints.design import (check_bolt, check_weld, JointCheck,  # noqa: E402
                                    fatigue_check, check_block_tearing,
                                    check_net_section, DETAILS)

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:56s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    err = abs(got - want)
    rel = err / abs(want) if want else err
    return check(name, err <= tol * max(1.0, abs(want)),
                 f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {rel * 100:.3f} %")


# --------------------------------------------------------------------------
# 1) Schrauben: Abmessungen und Tragfaehigkeiten (EN 1993-1-8 Tab. 3.1/3.4)
# --------------------------------------------------------------------------
def test_schrauben():
    b = Bolt("M20", "10.9")
    close("M20: Spannungsquerschnitt A_s", b.As, 245e-6, 1e-9, " m^2")
    close("M20: Schaftquerschnitt A", b.A, math.pi * 0.020 ** 2 / 4, 1e-12, " m^2")
    close("M20 10.9: f_ub", b.fub, 1000e6, 1e-12, " Pa")
    close("M20 10.9: f_yb", b.fyb, 900e6, 1e-12, " Pa")

    # Lochspiel EN 1090-2 Tab. 11
    close("M12: Lochspiel 1 mm", Bolt("M12", "8.8").clearance, 0.001, 1e-12, " m")
    close("M16: Lochspiel 2 mm", Bolt("M16", "8.8").clearance, 0.002, 1e-12, " m")
    close("M24: Lochspiel 2 mm", Bolt("M24", "8.8").clearance, 0.002, 1e-12, " m")
    close("M27: Lochspiel 3 mm", Bolt("M27", "8.8").clearance, 0.003, 1e-12, " m")
    close("Passschraube M20: 0,3 mm", Bolt("M20", "8.8", hole="pass").clearance,
          0.0003, 1e-12, " m")
    close("M20: Lochdurchmesser d_0 = 22 mm", b.d0, 0.022, 1e-12, " m")

    # Abscheren: alpha_v = 0,5 fuer 10.9 mit Gewinde in der Scherfuge
    close("M20 10.9 Gewinde: F_v,Rd", b.Fv_Rd(), 0.5 * 1000e6 * 245e-6 / 1.25, 1e-9, " N")
    close("M20 10.9 Schaft: F_v,Rd",
          Bolt("M20", "10.9", threads_in_shear=False).Fv_Rd(),
          0.6 * 1000e6 * math.pi * 0.020 ** 2 / 4 / 1.25, 1e-9, " N")
    close("M20 8.8 Gewinde: F_v,Rd (alpha_v = 0,6)",
          Bolt("M20", "8.8").Fv_Rd(), 0.6 * 800e6 * 245e-6 / 1.25, 1e-9, " N")
    close("zweischnittig: doppelte Tragfaehigkeit",
          Bolt("M20", "10.9", shear_planes=2).Fv_Rd(), 2 * b.Fv_Rd(), 1e-12, " N")

    # Zug und Durchstanzen
    close("M20 10.9: F_t,Rd", b.Ft_Rd(), 0.9 * 1000e6 * 245e-6 / 1.25, 1e-9, " N")
    close("Senkschraube: k_2 = 0,63",
          Bolt("M20", "10.9", countersunk=True).Ft_Rd(), 0.63 / 0.9 * b.Ft_Rd(), 1e-9, " N")
    close("M20: B_p,Rd bei t = 15 mm",
          b.Bp_Rd(0.015, 490e6), 0.6 * math.pi * b.dm * 0.015 * 490e6 / 1.25, 1e-9, " N")

    # Vorspannung und Gleitfestigkeit
    bp = Bolt("M20", "10.9", category="C", mu=0.5)
    close("F_p,C = 0,7 f_ub A_s", bp.Fp_C, 0.7 * 1000e6 * 245e-6, 1e-9, " N")
    close("F_s,Rd = k_s n mu F_p,C / gamma_M3", bp.Fs_Rd(),
          1.0 * 1 * 0.5 * 171.5e3 / 1.25, 1e-4, " N")
    close("F_s,Rd mit Zugkraft (0,8 F_t,Ed)", bp.Fs_Rd(50e3),
          0.5 * (171.5e3 - 0.8 * 50e3) / 1.25, 1e-4, " N")
    close("F_s,Rd,ser mit gamma_M3 = 1,10", bp.Fs_Rd(sls=True),
          0.5 * 171.5e3 / 1.10, 1e-4, " N")
    close("uebergrosses Loch: k_s = 0,85",
          Bolt("M20", "10.9", category="C", mu=0.5, hole="uebergross").ks, 0.85, 1e-12)
    ok = False
    try:
        Bolt("M20", "5.6", category="C")
    except ValueError:
        ok = True
    check("Klasse 5.6 darf nicht vorgespannt werden", ok)

    # Lochleibung: Randschraube und innere Schraube
    geo_rand = BoltGeometry(e1=0.040, e2=0.040)
    geo_innen = BoltGeometry(p1=0.070, p2=0.070, inner_1=True, inner_2=True)
    b8 = Bolt("M20", "8.8")
    close("alpha_b Randschraube = e_1/(3 d_0)", b8.alpha_b(geo_rand, 490e6),
          0.040 / (3 * 0.022), 1e-9)
    close("alpha_b innen = p_1/(3 d_0) - 1/4", b8.alpha_b(geo_innen, 490e6),
          0.070 / (3 * 0.022) - 0.25, 1e-9)
    close("k_1 Rand = 2,8 e_2/d_0 - 1,7 (<= 2,5)", b8.k1(geo_rand),
          min(2.8 * 0.040 / 0.022 - 1.7, 2.5), 1e-9)
    close("k_1 innen = 1,4 p_2/d_0 - 1,7 (<= 2,5)", b8.k1(geo_innen),
          min(1.4 * 0.070 / 0.022 - 1.7, 2.5), 1e-9)
    close("F_b,Rd Randschraube", b8.Fb_Rd(0.015, 490e6, geo_rand),
          2.5 * (0.040 / (3 * 0.022)) * 490e6 * 0.020 * 0.015 / 1.25, 1e-9, " N")

    # Interaktion
    eta = b.interaction(50e3, 60e3)
    close("Interaktion F_v/F_v,Rd + F_t/(1,4 F_t,Rd)", eta,
          50e3 / b.Fv_Rd() + 60e3 / (1.4 * b.Ft_Rd()), 1e-12)

    # lange Anschluesse
    close("beta_Lf = 1 bei L_j <= 15 d", beta_Lf(0.250, 0.020), 1.0, 1e-12)
    close("beta_Lf bei L_j = 600 mm", beta_Lf(0.600, 0.020),
          1.0 - (0.600 - 0.300) / (200 * 0.020), 1e-12)
    close("beta_Lf nicht unter 0,75", beta_Lf(5.0, 0.020), 0.75, 1e-12)

    # Rand- und Lochabstaende
    ms = min_spacing(0.022)
    close("Mindestrandabstand e_1 = 1,2 d_0", ms["e1"], 1.2 * 0.022, 1e-12, " m")
    close("Mindestlochabstand p_1 = 2,2 d_0", ms["p1"], 2.2 * 0.022, 1e-12, " m")
    v = check_spacing(BoltGeometry(e1=0.020, e2=0.040, p1=0.070, p2=0.070), 0.022, 0.015)
    check("zu kleiner Randabstand wird gemeldet", any("e1" in x for x in v), str(v[:1]))
    check("richtige Abstaende ohne Beanstandung",
          not check_spacing(BoltGeometry(e1=0.040, e2=0.040, p1=0.070, p2=0.070),
                            0.022, 0.015))

    # Blockversagen
    R = block_tearing(300e-6, 900e-6, 490e6, 355e6)
    close("Blockversagen mittig", R,
          490e6 * 300e-6 / 1.25 + 355e6 * 900e-6 / math.sqrt(3), 1e-9, " N")
    close("Blockversagen aussermittig: halber Zuganteil",
          block_tearing(300e-6, 900e-6, 490e6, 355e6, concentric=False),
          0.5 * 490e6 * 300e-6 / 1.25 + 355e6 * 900e-6 / math.sqrt(3), 1e-9, " N")

    check("alle Groessen M8 bis M36 vorhanden", len(SIZES) == 13, str(len(SIZES)))
    check("alle Festigkeitsklassen vorhanden", len(GRADES) == 7, str(len(GRADES)))


# --------------------------------------------------------------------------
# 2) Schweissnaehte
# --------------------------------------------------------------------------
def test_naehte():
    close("beta_w S235", beta_w("S235"), 0.80, 1e-12)
    close("beta_w S355", beta_w("S355J2+N"), 0.90, 1e-12)
    close("beta_w S460", beta_w("S460"), 1.00, 1e-12)
    close("f_vw,d S355", fvw_d(490e6, "S355"), 490e6 / math.sqrt(3) / (0.9 * 1.25), 1e-9, " Pa")

    n = Fillet(a=0.005, length=0.300, fu=490e6, grade="S355")
    close("Kehlnahtflaeche a*l", n.area, 0.005 * 0.300, 1e-12, " m^2")
    close("F_w,Rd (vereinfacht)", n.Fw_Rd(), fvw_d(490e6, "S355") * 0.0015, 1e-9, " N")
    close("beidseitig: doppelte Flaeche",
          Fillet(a=0.005, length=0.300, fu=490e6, double=True).area, 2 * 0.0015, 1e-12, " m^2")

    # Richtungsbezogenes Verfahren: reine Laengskraft -> nur tau_parallel
    r = n.utilisation_directional(0.0, 0.0, 100e3)
    close("Laengsnaht: tau_parallel = F/A", r["tau_laengs"], 100e3 / 0.0015, 1e-9, " Pa")
    close("Laengsnaht: Vergleichsspannung = sqrt(3) tau",
          r["vergleichsspannung"], math.sqrt(3) * 100e3 / 0.0015, 1e-9, " Pa")
    check("Laengsnaht: sigma senkrecht = 0", abs(r["sigma_senkrecht"]) < 1e-6)
    # Stirnkehlnaht: Kraft senkrecht -> sigma und tau je F/(A sqrt(2))
    r2 = n.utilisation_directional(100e3, 0.0, 0.0)
    close("Stirnnaht: sigma senkrecht = F/(A sqrt2)", r2["sigma_senkrecht"],
          100e3 / 0.0015 / math.sqrt(2), 1e-9, " Pa")
    # sigma = tau = F/(A sqrt2)  ->  sqrt(sigma^2 + 3 tau^2) = sqrt(2) F/A
    close("Stirnnaht: Vergleichsspannung = sqrt(2) F/A",
          r2["vergleichsspannung"], math.sqrt(2.0) * 100e3 / 0.0015, 1e-9, " Pa")

    close("kleinste Nahtdicke bei t = 25 mm", min_throat(0.025),
          (math.sqrt(25) - 0.5) * 1e-3, 1e-12, " m")
    check("kleinste Nahtdicke nie unter 3 mm", min_throat(0.005) >= 0.003 - 1e-12)
    close("groesste Nahtdicke 0,7 t", max_throat(0.010), 0.007, 1e-12, " m")
    v = Fillet(a=0.002, length=0.020, fu=490e6).check_throat(0.010, 0.025)
    check("zu duenne und zu kurze Naht werden gemeldet", len(v) >= 2, str(len(v)))

    st = Butt(thickness=0.015, length=0.200, fy=355e6)
    close("durchgeschweisste Stumpfnaht: N_Rd = A f_y", st.N_Rd(),
          355e6 * 0.015 * 0.200, 1e-9, " N")

    # Nahtbild: zwei waagerechte Naehte im Abstand 300 mm (Flanschnaehte)
    segs = [WeldSegment((-0.100, -0.150), (0.100, -0.150), a=0.005),
            WeldSegment((-0.100, 0.150), (0.100, 0.150), a=0.005)]
    p = weld_group_properties(segs)
    close("Nahtbild: Flaeche", p["A"], 2 * 0.005 * 0.200, 1e-12, " m^2")
    close("Nahtbild: Schwerpunkt z", p["zc"], 0.0, 1e-12, " m")
    close("Nahtbild: I_y = A/2 * 2 * e^2", p["Iy"],
          2 * (0.005 * 0.200) * 0.150 ** 2, 1e-9, " m^4")
    s = weld_group_stress(segs, My=30e3)
    close("Nahtbild: sigma aus M_y = M z/I_y", abs(s["nahtspannungen"][0]["sigma"]),
          30e3 * 0.150 / p["Iy"], 1e-9, " Pa")


# --------------------------------------------------------------------------
# 3) T-Stummel (EN 1993-1-8, 6.2.4)
# --------------------------------------------------------------------------
def test_tstub():
    le = effective_lengths("innen", m=0.040, e=0.045)
    close("l_eff,cp innen = 2 pi m", le["cp"], 2 * math.pi * 0.040, 1e-12, " m")
    close("l_eff,nc innen = 4m + 1,25e", le["nc"], 4 * 0.040 + 1.25 * 0.045, 1e-12, " m")
    ler = effective_lengths("rand", m=0.040, e=0.045, e1=0.035)
    close("l_eff,cp Rand = min(2 pi m, pi m + 2 e_1)", ler["cp"],
          min(2 * math.pi * 0.040, math.pi * 0.040 + 2 * 0.035), 1e-12, " m")

    b = Bolt("M24", "10.9")
    ts = TStub(t=0.020, fy=355e6, m=0.040, e=0.045, leff_cp=le["cp"], leff_nc=le["nc"],
               Ft_Rd=b.Ft_Rd(), n_bolts=2)
    close("n = min(e, 1,25 m)", ts.n, min(0.045, 1.25 * 0.040), 1e-12, " m")
    Mpl1 = 0.25 * ts.leff_1 * 0.020 ** 2 * 355e6
    close("M_pl,1,Rd", ts.Mpl(ts.leff_1), Mpl1, 1e-9, " Nm")
    close("Modus 1: 4 M_pl,1/m", ts.F_T1(), 4 * Mpl1 / 0.040, 1e-9, " N")
    Mpl2 = 0.25 * ts.leff_2 * 0.020 ** 2 * 355e6
    close("Modus 2: (2 M_pl,2 + n sum F_t,Rd)/(m+n)", ts.F_T2(),
          (2 * Mpl2 + ts.n * 2 * b.Ft_Rd()) / (0.040 + ts.n), 1e-9, " N")
    close("Modus 3: sum F_t,Rd", ts.F_T3(), 2 * b.Ft_Rd(), 1e-12, " N")
    r = ts.resistance()
    check("massgebend ist der kleinste Wert",
          abs(r["F_T_Rd"] - min(r["werte"].values())) < 1e-6, r["versagen"])

    # duennes Blech -> Modus 1, dickes Blech -> Modus 3
    duenn = TStub(t=0.010, fy=355e6, m=0.040, e=0.045, leff_cp=le["cp"], leff_nc=le["nc"],
                  Ft_Rd=b.Ft_Rd(), n_bolts=2).resistance()
    dick = TStub(t=0.050, fy=355e6, m=0.040, e=0.045, leff_cp=le["cp"], leff_nc=le["nc"],
                 Ft_Rd=b.Ft_Rd(), n_bolts=2).resistance()
    check("duennes Blech -> Modus 1", duenn["versagen"].startswith("Modus 1"),
          duenn["versagen"])
    check("dickes Blech -> Modus 3", dick["versagen"].startswith("Modus 3"),
          dick["versagen"])
    check("dickes Blech traegt mehr", dick["F_T_Rd"] > duenn["F_T_Rd"],
          f"{dick['F_T_Rd'] / 1e3:.0f} kN > {duenn['F_T_Rd'] / 1e3:.0f} kN")
    ohne = TStub(t=0.020, fy=355e6, m=0.040, e=0.045, leff_cp=le["cp"], leff_nc=le["nc"],
                 Ft_Rd=b.Ft_Rd(), n_bolts=2, prying=False)
    close("Modus 1* ohne Abstuetzung: 2 M_pl,1/m", ohne.F_T1(), 2 * Mpl1 / 0.040, 1e-9, " N")


# --------------------------------------------------------------------------
# 4) FE-Abbildung: Vorspannung, Reibung, Lochspiel, Lochleibung
# --------------------------------------------------------------------------
def _bolt_model(bolt, H=0.0, N=0.0, shear="lochleibung", mu=None):
    m = Model("Schraube")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.rectangle("R", 0.05, 0.05))
    a = m.add_node(0, 0, 0)
    b = m.add_node(0, 0, 0.040)
    m.fix(a, "all")
    inst = add_bolt(m, a, b, bolt, case="LF1", shear=shear)
    m.add_gap_element(a, b, direction=[0, 0, 1], gap=0.0,
                      mu=(bolt.mu if bolt.preloaded else 0.0) if mu is None else mu)
    m.fix(b, [1, 3, 4, 5])
    if H or N:
        m.load_node(b, Fx=H, Fz=N, case="LF1")
    return m, a, b, inst, solver.solve_static(m, case="LF1")


def test_fe_schraube():
    b = Bolt("M20", "10.9", category="E")
    # Vorspannung ohne aeussere Last: Schraubenkraft = Klemmkraft = F_p,C
    m, na, nb, inst, r = _bolt_model(b)
    fuge = [c for c in r.contact if c["normal"][2] > 0.5][0]
    close("Vorspannung: Klemmkraft = F_p,C", fuge["Fn"], b.Fp_C, 1e-4, " N")
    N0 = float(r.beam_end[inst.element][6])
    close("Vorspannung: Schraubenkraft = F_p,C", abs(N0), b.Fp_C, 1e-3, " N")

    # aeussere Zugkraft baut die Klemmkraft ab, die Schraubenkraft bleibt
    for Fz, rest in ((50e3, b.Fp_C - 50e3), (150e3, b.Fp_C - 150e3)):
        m, na, nb, inst, r = _bolt_model(b, N=Fz)
        fuge = [c for c in r.contact if c["normal"][2] > 0.5][0]
        close(f"Zug {Fz / 1e3:.0f} kN: Klemmkraft F_p,C - F", fuge["Fn"], rest, 2e-3, " N")
        close(f"Zug {Fz / 1e3:.0f} kN: Schraubenkraft bleibt F_p,C",
              abs(float(r.beam_end[inst.element][6])), b.Fp_C, 3e-3, " N")
    # ueber der Vorspannung: Fuge oeffnet, Schraube traegt die volle Last
    m, na, nb, inst, r = _bolt_model(b, N=250e3)
    fuge = [c for c in r.contact if c["normal"][2] > 0.5][0]
    check("Zug 250 kN > F_p,C: Fuge oeffnet", fuge["status"] == "offen", fuge["status"])
    close("Fuge offen: Schraubenkraft = aeussere Kraft",
          abs(float(r.beam_end[inst.element][6])), 250e3, 2e-3, " N")

    # Reibung: Haften bis mu*F_p,C, danach Gleiten mit genau mu*F_n
    bc = Bolt("M20", "10.9", category="C", mu=0.5)
    grenz = bc.mu * bc.Fp_C
    for H, soll in ((0.6 * grenz, "Haften"), (0.99 * grenz, "Haften"),
                    (1.4 * grenz, "Gleiten")):
        m, na, nb, inst, r = _bolt_model(bc, H=H)
        fuge = [c for c in r.contact if c["normal"][2] > 0.5][0]
        check(f"Reibung bei H = {H / 1e3:.0f} kN: {soll}", fuge["status"] == soll,
              f"{fuge['status']}, F_t = {abs(fuge['Ft']) / 1e3:.1f} kN")
        if soll == "Haften":
            close(f"  Haften: F_t = H ({H / 1e3:.0f} kN)", abs(fuge["Ft"]), H, 2e-3, " N")
        else:
            close("  Gleiten: F_t = mu F_n", abs(fuge["Ft"]), grenz, 2e-3, " N")

    # Zugkraft mindert die Reibkapazitaet
    m, na, nb, inst, r = _bolt_model(bc, H=0.6 * grenz, N=100e3)
    fuge = [c for c in r.contact if c["normal"][2] > 0.5][0]
    check("Zug mindert die Reibkapazitaet -> Gleiten", fuge["status"] == "Gleiten",
          f"F_n = {fuge['Fn'] / 1e3:.0f} kN, mu F_n = {bc.mu * fuge['Fn'] / 1e3:.0f} kN")

    # Lochspiel: die Fuge verschiebt sich um das halbe Lochspiel, dann traegt der Schaft
    for hole, spiel in (("normal", 0.002), ("pass", 0.0003)):
        bb = Bolt("M20", "10.9", category="E", hole=hole, mu=0.0)
        m, na, nb, inst, r = _bolt_model(bb, H=40e3, shear="spiel", mu=0.0)
        ux = float(r.u.reshape(-1, 6)[nb, 0])
        close(f"Lochspiel {hole}: Verschiebung = halbes Spiel", ux, 0.5 * spiel, 5e-3, " m")
        lz = [c for c in r.contact if c["normal"][0] < -0.5][0]
        close(f"Lochspiel {hole}: Schaft traegt die Querkraft", abs(lz["Fn"]), 40e3,
              5e-3, " N")

    # Lochleibung: der Schaft traegt die Querkraft von Anfang an
    ba = Bolt("M20", "8.8", category="A")
    m, na, nb, inst, r = _bolt_model(ba, H=60e3)
    V = float(r.beam_end[inst.element][2])
    close("Lochleibung: Schaftquerkraft = H", abs(V), 60e3, 1e-6, " N")
    M = float(r.beam_end[inst.element][4])
    close("Schaftmoment = V L/2 (beidseitig eingespannt)", abs(M),
          60e3 * 0.040 / 2, 1e-6, " Nm")


# --------------------------------------------------------------------------
# 5) Bleche als Schalen und als Volumen
# --------------------------------------------------------------------------
def test_bleche():
    m = Model("Blech")
    m.add_material(Material.steel("S355"))
    ids = plate_shells(m, (0, 0, 0), (0, 0, 1), 0.200, 0.300, 0.020, "S355", nx=4, ny=6)
    check("Schalenblech: Knotengitter", ids.shape == (5, 7), str(ids.shape))
    check("Schalenblech: 24 Elemente", len(m.elements) == 24, str(len(m.elements)))
    check("Schalenblech: Dicke angelegt", "t20" in m.shells, str(list(m.shells)))
    close("Schalenblech: Breite", float(m.nodes[ids[-1, 0]][0] - m.nodes[ids[0, 0]][0]),
          0.200, 1e-12, " m")

    m2 = Model("Volumen")
    m2.add_material(Material.steel("S355"))
    v = plate_solid(m2, (0, 0, 0), (0, 0, 1), 0.200, 0.300, 0.020, "S355",
                    nx=2, ny=3, nz=2)
    check("Volumenblech: Knotengitter", v.shape == (3, 4, 3), str(v.shape))
    check("Volumenblech: 12 Hexaeder", len(m2.elements) == 12, str(len(m2.elements)))
    close("Volumenblech: Dicke in Normalenrichtung",
          float(m2.nodes[v[0, 0, -1]][2] - m2.nodes[v[0, 0, 0]][2]), 0.020, 1e-12, " m")

    # Zugscheibe: sigma = N/A, Verlaengerung = N L/(E A)
    m3 = Model("Scheibe")
    m3.add_material(Material.steel("S355"))
    g = plate_shells(m3, (0, 0, 0), (0, 1, 0), 1.0, 0.200, 0.010, "S355", nx=10, ny=4,
                     ref=(1, 0, 0))
    for n in g[0, :]:
        m3.fix(int(n), [0, 1, 2, 3, 4, 5])
    F = 100e3 / (g.shape[1])
    for n in g[-1, :]:
        m3.load_node(int(n), Fx=F, case=m3.active_case)
    r = solver.solve_static(m3)
    E, A = 210e9, 0.200 * 0.010
    close("Zugscheibe: Verlaengerung N L/(E A)",
          float(r.u.reshape(-1, 6)[int(g[-1, 0]), 0]), 100e3 * 1.0 / (E * A), 5e-3, " m")


# --------------------------------------------------------------------------
# 6) Nachweise und Ermuedung
# --------------------------------------------------------------------------
def test_nachweise():
    b = Bolt("M20", "10.9", category="C", mu=0.5)
    geo = BoltGeometry(e1=0.040, e2=0.040, p1=0.070, p2=0.070)
    j = JointCheck("Laschenstoss")
    j.add(check_bolt(b, Fv_Ed=60e3, Ft_Ed=40e3, geo=geo, t=0.015, fu=490e6, tp=0.015))
    namen = [c.name for c in j.checks]
    check("Nachweise angelegt", len(j.checks) >= 6, str(len(j.checks)))
    check("Gleitnachweis Kategorie C enthalten",
          any("Gleitfestigkeit" in n for n in namen), str(namen[-1]))
    check("massgebender Nachweis wird benannt", bool(j.massgebend), j.massgebend)
    check("Bericht nennt die Ausnutzung", "eta" in j.report())

    ok = JointCheck("klein")
    ok.add(check_bolt(b, Fv_Ed=20e3, geo=geo, t=0.015, fu=490e6))
    check("kleine Last: alle Nachweise erfuellt", ok.ok, f"eta = {ok.eta:.3f}")

    nz = check_net_section(30e-4, 24e-4, 355e6, 490e6, 700e3, category_C=True)
    check("Nettoquerschnitt: drei Nachweise", len(nz) == 3, str(len(nz)))
    close("N_u,Rd = 0,9 A_net f_u/gamma_M2", nz[1].R, 0.9 * 24e-4 * 490e6 / 1.25, 1e-9, " N")
    bt = check_block_tearing(400e3, 300e-6, 900e-6, 490e6, 355e6)
    check("Blockversagen als Nachweis", bt.name.startswith("Blockversagen"), bt.line()[:40])

    # Ermuedung: N_R gegen die Woehlerlinie
    f = fatigue_check("schraube_zug", [(20e3, 2e6)], gamma_Mf=1.15, area=b.As)
    ds = 20e3 / b.As
    N_soll = 2e6 * ((50e6 / 1.15) / ds) ** 3
    close("Ermuedung Schraube: N_R = 2e6 (dc/ds)^3", f["N_R"][0], N_soll, 1e-6)
    close("Schaedigung D = n/N_R", f["schaedigung"], 2e6 / N_soll, 1e-6)
    check("Kerbfall 50 fuer Schrauben auf Zug", f["kerbfall"] == 50, str(f["kerbfall"]))
    fs = fatigue_check("schraube_abscheren", [(50e6, 1e6)])
    check("Kerbfall 100 mit m = 5 fuer Abscheren",
          fs["kerbfall"] == 100 and fs["steigung"] == 5, str(fs["steigung"]))
    klein = fatigue_check("schraube_zug", [(3e3, 2e6)], area=b.As)
    check("kleine Schwingbreite: Dauerfestigkeit", klein["ok"],
          f"D = {klein['schaedigung']:.4f}")
    check("Kerbfallverzeichnis vorhanden", len(DETAILS) >= 14, str(len(DETAILS)))


# --------------------------------------------------------------------------
# 7) Anschlussvorlagen: Typ waehlen, Stabende anklicken
# --------------------------------------------------------------------------
def _rahmen():
    m = Model("Rahmen")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("IPE 400"))
    m.add_section(Section.from_profile("HEB 300"))
    m.add_section(Section.from_profile("L 100x100x10")
                  if "L 100x100x10" in [] else Section.from_profile("HEB 300"))
    n0 = m.add_node(0, 0, 0)
    n1 = m.add_node(6, 0, 0)
    n2 = m.add_node(0, 0, 4)
    e_traeger = m.add_element("beam", [n0, n1], "S355", "IPE 400")
    e_diag = m.add_element("beam", [n0, n2], "S355", "HEB 300")
    return m, e_traeger, e_diag


def test_vorlagen():
    from statik3d.joints.templates import (EndPlate, Splice, Gusset, propose,
                                           TYPES, TEMPLATES)
    m, e_tr, e_di = _rahmen()
    check("drei Anschlusstypen", sorted(TYPES) == ["diagonale", "kopfplatte", "lasche"],
          str(sorted(TYPES)))

    # Kopfplatte
    a = EndPlate.propose(m, elem=e_tr, end=1, N=-100e3, Vz=90e3, My=180e3)
    sec = m.sections["IPE 400"]
    check("Kopfplatte: Blech breiter als der Flansch", a.bp > sec.b,
          f"{a.bp * 1e3:.0f} > {sec.b * 1e3:.0f} mm")
    check("Kopfplatte: Blech hoeher als das Profil", a.hp > sec.h,
          f"{a.hp * 1e3:.0f} > {sec.h * 1e3:.0f} mm")
    check("Kopfplatte: Schraubenreihen ausserhalb und innerhalb", len(a.rows) >= 4,
          str([round(z * 1e3) for z in a.rows]))
    check("Kopfplatte: Riss haelt den Mindestabstand", a.w >= 2.4 * a.bolt.d0 - 1e-9,
          f"w = {a.w * 1e3:.0f} mm, 2,4 d_0 = {2.4 * a.bolt.d0 * 1e3:.0f} mm")
    check("Kopfplatte: Nahtdicke im zulaessigen Bereich",
          min_throat(sec.tf) - 1e-9 <= a.a_f <= max_throat(sec.tf) + 1e-9,
          f"a_f = {a.a_f * 1e3:g} mm")
    check("Kopfplatte: Schraubenlagen paarweise",
          len(a.bolt_positions()) == 2 * len(a.rows), str(len(a.bolt_positions())))
    j = a.design(N=-100e3, Vz=90e3, My=180e3)
    check("Kopfplatte: Vorschlag erfuellt die Nachweise", j.ok,
          f"eta = {j.eta:.3f}, massgebend {j.massgebend}")
    check("Kopfplatte: T-Stummel wird gefuehrt",
          any("T-Stummel" in c.name for c in j.checks))
    check("Kopfplatte: Beschreibung nennt Blech und Schrauben",
          "Blech" in a.describe() and a.bolt.size in a.describe())

    # groesseres Moment -> staerkerer Anschluss
    a2 = EndPlate.propose(m, elem=e_tr, end=1, N=0.0, Vz=90e3, My=320e3)
    check("groesseres Moment -> dickeres Blech oder groessere Schraube",
          a2.tp >= a.tp or a2.bolt.d > a.bolt.d,
          f"t = {a2.tp * 1e3:.0f} mm, {a2.bolt.size}")

    # FE-Modell der Kopfplatte
    log = []
    teil = a.build(kind="2d", nx=6, ny=8, log=log)
    check("Kopfplatte 2D: Schalen erzeugt",
          any(e.typ.startswith("shell") for e in teil.elements))
    check("Kopfplatte 2D: Schrauben eingebaut",
          sum(1 for e in teil.elements if e.group == "schraube") == len(a.bolt_positions()),
          str(sum(1 for e in teil.elements if e.group == "schraube")))
    check("Kopfplatte 2D: Trennfuge als Kontakt", len(teil.gap_elements) > 0,
          f"{len(teil.gap_elements)} Spaltelemente")
    r = solver.solve_static(teil)
    check("Kopfplatte 2D: Teilmodell rechnet", r.u is not None,
          f"{teil.nn} Knoten, u_max = {abs(r.u).max() * 1e3:.3f} mm")
    teil3 = a.build(kind="3d", nx=4, ny=6, nz=2)
    check("Kopfplatte 3D: Volumenelemente",
          any(e.typ == "hex8" for e in teil3.elements),
          str(sum(1 for e in teil3.elements if e.typ == "hex8")))

    # Laschenstoss
    s = Splice.propose(m, elem=e_tr, end=1, N=-80e3, Vz=60e3, My=90e3)
    check("Lasche: Flansch- und Steglaschen", s.t_fl > 0 and s.t_web > 0,
          f"{s.t_fl * 1e3:g} / {s.t_web * 1e3:g} mm")
    check("Lasche: gerade Schraubenzahl je Flansch", s.n_fl % 2 == 0, str(s.n_fl))
    js = s.design(N=-80e3, Vz=60e3, My=90e3)
    check("Lasche: Vorschlag erfuellt die Nachweise", js.ok,
          f"eta = {js.eta:.3f}, massgebend {js.massgebend}")
    check("Lasche: Blockversagen wird gefuehrt",
          any("Blockversagen" in c.name for c in js.checks))
    ts = s.build(kind="2d")
    check("Lasche: Teilmodell mit Laschen und Schrauben",
          any(e.group == "schraube" for e in ts.elements) and ts.nn > 0,
          f"{ts.nn} Knoten")

    # zu hohe Beanspruchung -> ehrlicher Hinweis statt stiller Vergroesserung
    s2 = Splice.propose(m, elem=e_tr, end=1, N=-450e3, Vz=120e3, My=250e3)
    check("Lasche: Bauteilversagen wird benannt",
          any("Traegerflansch" in h or "Flansch" in h for h in s2.hinweise),
          s2.hinweise[-1][:60])

    # Diagonalanschluss
    g = Gusset.propose(m, elem=e_di, end=1, N=-450e3)
    check("Diagonale: Knotenblech vorgeschlagen", g.t_g >= 0.008, f"t = {g.t_g * 1e3:g} mm")
    check("Diagonale: Whitmore-Breite", g.whitmore_width() > 0,
          f"{g.whitmore_width() * 1e3:.0f} mm")
    jg = g.design(N=-450e3)
    check("Diagonale: Vorschlag erfuellt die Nachweise", jg.ok,
          f"eta = {jg.eta:.3f}, massgebend {jg.massgebend}")
    check("Diagonale: Knicken des Blechs bei Druck",
          any("Knotenblech auf Druck" in c.name for c in jg.checks))
    gw = Gusset.propose(m, elem=e_di, end=1, N=-300e3, welded=True)
    check("Diagonale geschweisst: Nahtlaenge vorgeschlagen", gw.l_weld > 0.05,
          f"l = {gw.l_weld * 1e3:.0f} mm")
    jw = gw.design(N=-300e3)
    check("Diagonale geschweisst: Nahtnachweis",
          any("Kehlnaht" in c.name for c in jw.checks), f"eta = {jw.eta:.3f}")
    tg = g.build(kind="2d")
    check("Diagonale: Teilmodell rechnet", solver.solve_static(tg).u is not None,
          f"{tg.nn} Knoten")

    # Dispatcher
    for kind in TYPES:
        p = propose(kind, m, elem=e_tr if kind != "diagonale" else e_di, end=1,
                    N=-100e3, Vz=60e3, My=90e3)
        check(f"propose('{kind}') liefert eine Vorlage",
              isinstance(p, TEMPLATES[kind]), type(p).__name__)

    # Ermuedung im Anschluss
    jf = a.design(N=0.0, Vz=50e3, My=100e3, n_cycles=2e6, dMy=40e3)
    check("Kopfplatte: Ermuedungsnachweise vorhanden", len(jf.ermuedung) >= 2,
          str(len(jf.ermuedung)))
    a_vor = EndPlate.propose(m, elem=e_tr, end=1, N=0.0, Vz=50e3, My=100e3,
                             bolt=Bolt("M24", "10.9", category="E"))
    check("vorgespannte Schraube mindert die Schwingbreite",
          a_vor.bolt_range_factor() < 0.3, f"{a_vor.bolt_range_factor():.2f}")


# --------------------------------------------------------------------------
# Anschluss als Teil des Modells: speichern, ueber alle Kombinationen
# nachweisen, Ermuedung aus den Ermuedungslasten, Bericht
# --------------------------------------------------------------------------
def test_anschluss_im_modell():
    from statik3d import solver, examples_lib
    from statik3d.model import Model
    from statik3d.joints import anschluss as A
    from statik3d.joints.templates import propose

    m = examples_lib.build_example("hall")
    r = m.members["Riegel"]
    e_kopf, e_lasche = r.elements[0], r.elements[len(r.elements) // 2]
    t = propose("kopfplatte", m, e_kopf, end=0, N=-50e3, Vz=150e3, My=300e3)
    j = A.als_joint(t, "K1")
    m.joints[j.name] = j
    check("Anschluss wird zum Modellobjekt", j.typ == "kopfplatte" and j.elem == e_kopf,
          f"{j.typ}, {j.ort()}")
    check("Geometrie steht im Modellobjekt",
          abs(j.geometrie["tp"] - t.tp) < 1e-12 and j.geometrie["rows"] == t.rows,
          f"t_p = {j.geometrie['tp'] * 1e3:.0f} mm, {len(j.geometrie['rows'])} Reihen")
    check("Schraube steht im Modellobjekt",
          j.schraube["size"] == t.bolt.size and j.schraube["grade"] == t.bolt.grade,
          f"{j.schraube['size']} {j.schraube['grade']}")

    # -- speichern und laden ------------------------------------------
    d = Model.from_dict(m.to_dict())
    check("Anschluss übersteht Speichern und Laden",
          list(d.joints) == ["K1"] and d.joints["K1"].geometrie == j.geometrie)
    check("Anschluss übersteht Rückgängig (Modellkopie)",
          m.copy().joints["K1"].schraube == j.schraube)

    # -- Vorlage aus dem Modellobjekt zurueckbauen ---------------------
    t2 = A.vorlage(d, d.joints["K1"])
    check("Vorlage lässt sich zurückbauen",
          type(t2) is type(t) and abs(t2.tp - t.tp) < 1e-12 and t2.rows == t.rows)
    j1 = t.design(N=-50e3, Vz=150e3, My=300e3)
    j2 = t2.design(N=-50e3, Vz=150e3, My=300e3)
    check("zurückgebaute Vorlage rechnet dasselbe",
          abs(j1.eta - j2.eta) < 1e-12, f"{j1.eta:.6f} / {j2.eta:.6f}")

    # -- Endkraefte: Vorzeichen wie in beam_end_forces ------------------
    m.joints["S1"] = A.als_joint(
        propose("lasche", m, e_lasche, end=1, N=-50e3, Vz=50e3, My=200e3), "S1")
    an = solver.solve_all(m, design=True, fatigue=True)
    ein = next(iter(an.combinations.values()))
    k = A.endkraefte(ein, e_kopf, 0)
    from statik3d.solver import beam_end_forces
    bf = beam_end_forces(m, e_kopf, ein.beam_end[e_kopf])
    check("Endkräfte stimmen mit beam_end_forces überein",
          abs(k["N"] - bf["N"][0]) < 1e-6 and abs(k["My"] - bf["My"][0]) < 1e-6,
          f"N = {k['N'] / 1e3:.1f} kN, My = {k['My'] / 1e3:.1f} kNm")

    # -- Nachweis ueber alle Kombinationen ------------------------------
    res = an.joints
    check("Anschlüsse werden mit der Berechnung nachgewiesen",
          res is not None and set(res.joints) == {"K1", "S1"})
    c = res.joints["K1"]
    check("jede GZT-Kombination wird geführt",
          len(c.je_kombination) == len(res.combinations) == len(an.envelopes["ULS"].results)
          if hasattr(an.envelopes.get("ULS"), "results") else
          len(c.je_kombination) == len(res.combinations),
          f"{len(c.je_kombination)} Kombinationen")
    beste = max(c.je_kombination, key=lambda d: d["eta"])
    check("die ungünstigste Kombination ist maßgebend",
          abs(beste["eta"] - c.util) < 1e-12 and beste["kombination"] == c.kombination,
          f"{c.kombination}: eta = {c.util:.3f}")
    check("Einzelnachweise sind aufgeführt",
          any("Abscheren" in x["name"] for x in c.checks)
          and any("Kehlnaht" in x["name"] for x in c.checks)
          and any("T-Stummel" in x["name"] for x in c.checks),
          f"{len(c.checks)} Nachweise")
    eta_max = max(x["eta"] for x in c.checks)
    check("die Ausnutzung ist die größte der Einzelnachweise",
          abs(eta_max - c.util) < 1e-12, f"{eta_max:.3f}")

    # -- Ermuedung ------------------------------------------------------
    check("Ermüdung aus den Ermüdungslasten des Modells",
          c.ermuedung and c.D > 0,
          f"D = {c.D:.3f} aus {[e['lasten'] for e in c.ermuedung]}")
    check("Kerbfall der Schraube ist 50 (Tab. 8.1)",
          any(e["kerbfall"] == 50 for e in c.ermuedung))
    ohne = solver.solve_all(m, design=True, fatigue=False)
    check("ohne Ermüdungsnachweis bleibt die Schädigung außen vor",
          ohne.joints.joints["K1"].D == 0.0
          and abs(ohne.joints.joints["K1"].util - c.util) < 1e-12)

    # -- feste Schnittgroessen -------------------------------------------
    m.joints["K1"].kraefte = {"N": 0.0, "Vz": 10e3, "My": 20e3}
    fest = solver.solve_all(m, design=True).joints.joints["K1"]
    check("festgehaltene Schnittgrößen gehen vor",
          fest.kombination == "von Hand" and fest.util < c.util,
          f"eta = {fest.util:.3f} statt {c.util:.3f}")
    m.joints["K1"].kraefte = {}

    # -- Fehler werden benannt, nicht verschwiegen -------------------------
    m.joints["X"] = A.als_joint(propose("kopfplatte", m, e_kopf, end=0, My=100e3), "X")
    m.joints["X"].typ = "gibtsnicht"
    schlecht = solver.solve_all(m, design=True).joints.joints["X"]
    check("unbekannter Anschlusstyp wird gemeldet, nicht geraten",
          schlecht.fehler and schlecht.status() == "nicht geführt", schlecht.fehler[:50])
    del m.joints["X"]

    # -- Bericht ---------------------------------------------------------
    from statik3d.report import Report
    rep = Report(m, an)
    html = rep.html()
    check("Bericht hat ein Kapitel Anschlüsse",
          "Anschlüsse nach DIN EN 1993-1-8" in html)
    for text in ("T-Stummel", "Kehlnaht", "Abscheren F_v,Rd", "Palmgren-Miner",
                 "K1", "S1"):
        check(f"Bericht nennt „{text}“", text in html)
    check("Bericht nennt die maßgebende Kombination im Anschluss",
          c.kombination in html, c.kombination)
    check("der alte Ausschluss steht nicht mehr im Bericht",
          "nicht Bestandteil dieses Berichts" not in html.split("Anschlüsse, Schweißnähte")[0]
          or "in Kapitel 7 nachgewiesen" in html)
    check("Zusammenfassung führt die Anschlüsse",
          "max. Ausnutzung Anschlüsse" in html)


# --------------------------------------------------------------------------
# Momenten-Rotations-Verhalten: Komponentenverfahren, Klassifizierung,
# Rotationsvermoegen und die Drehfeder in der Rechnung
# --------------------------------------------------------------------------
def test_momenten_rotation():
    from statik3d.joints import rotation as R

    # -- Steifigkeitsbeiwerte gegen die Formeln der Tab. 6.11 ------------
    k5 = R.k5_stirnplatte(l_eff=0.200, t_p=0.020, m=0.040)
    close("k_5 = 0,9 l_eff t^3 / m^3", k5.k, 0.9 * 0.200 * 0.020 ** 3 / 0.040 ** 3,
          1e-12, " m")
    k10 = R.k10_schrauben(As=353e-6, L_b=0.060)
    close("k_10 = 1,6 A_s / L_b", k10.k, 1.6 * 353e-6 / 0.060, 1e-12, " m")
    k1 = R.k1_schubfeld(A_vc=47.4e-4, beta=1.0, z=0.480)
    close("k_1 = 0,38 A_vc / (beta z)", k1.k, 0.38 * 47.4e-4 / 0.480, 1e-12, " m")
    close("Schubfläche HEB 300 (EN 1993-1-1, 6.2.6(3))",
          R.schubflaeche_I(0.300, 0.300, 0.011, 0.019, 0.027, 149.1e-4),
          47.43e-4, 3e-3, " m^2")

    # -- eine Reihe: S_j,ini = E z^2 / (1/k_5 + 1/k_10) ------------------
    r = R.Reihe(h=0.500, komponenten=[k5, k10])
    close("k_eff einer Reihe", r.k_eff, 1.0 / (1.0 / k5.k + 1.0 / k10.k), 1e-12, " m")
    S, z, keq, _ = R.steifigkeit([r])
    close("S_j,ini einer Reihe", S, R.E_STAHL * 0.5 ** 2 / (1.0 / k5.k + 1.0 / k10.k),
          1e-12, " Nm/rad")

    # -- zwei Reihen: Ersatzfeder nach 6.3.3.1 ---------------------------
    r1 = R.Reihe(h=0.500, komponenten=[k5, k10])
    r2 = R.Reihe(h=0.400, komponenten=[k5, k10])
    z_eq, k_eq = R.ersatzfeder([r1, r2])
    keff = r1.k_eff
    soll_z = (keff * 0.5 ** 2 + keff * 0.4 ** 2) / (keff * 0.5 + keff * 0.4)
    close("z_eq zweier Reihen", z_eq, soll_z, 1e-12, " m")
    close("k_eq zweier Reihen", k_eq, (keff * 0.5 + keff * 0.4) / soll_z, 1e-12, " m")
    S2, _z, _k, _ = R.steifigkeit([r1, r2])
    check("zwei Reihen sind steifer als eine", S2 > S, f"{S2 / 1e6:.1f} > {S / 1e6:.1f}")

    # -- eine unendlich steife Komponente faellt heraus -------------------
    starr = R.Komponente("k_x", float("inf"))
    r3 = R.Reihe(h=0.500, komponenten=[k5, k10, starr])
    close("unendliche Komponente ändert nichts", r3.k_eff, r1.k_eff, 1e-12, " m")

    # -- Klassifizierung 5.2.2.5 -----------------------------------------
    E, I_b, L_b = R.E_STAHL, 48200e-8, 15.0
    grenze = 8.0 * E * I_b / L_b
    for S_test, soll in ((1.01 * grenze, "starr"), (0.99 * grenze, "nachgiebig"),
                         (0.49 * E * I_b / L_b, "gelenkig")):
        kl, _grund, gs, gg = R.klassifizieren(S_test, E, I_b, L_b, "ausgesteift")
        check(f"Klassifizierung {soll}", kl == soll, f"{S_test / 1e6:.1f} -> {kl}")
    kl, _g, gs, _gg = R.klassifizieren(1.01 * grenze, E, I_b, L_b, "nicht ausgesteift")
    check("nicht ausgesteift verlangt k_b = 25", kl == "nachgiebig"
          and abs(gs - 25.0 * E * I_b / L_b) < 1e-6, f"{kl}, Grenze {gs / 1e6:.1f}")

    # -- Tragfaehigkeitsklasse 5.2.3 --------------------------------------
    Mpl = 400e3
    for M, soll in ((410e3, "volltragfähig"), (200e3, "teiltragfähig"),
                    (90e3, "gelenkig")):
        check(f"Tragfähigkeitsklasse {soll}",
              R.tragfaehigkeitsklasse(M, Mpl) == soll, f"{M / 1e3:.0f} kNm")

    # -- Momententragfaehigkeit mit begrenzter Druckzone (6.2.7.2(6)) -----
    ra = R.Reihe(h=0.50, F_Rd=300e3)
    rb = R.Reihe(h=0.40, F_Rd=300e3)
    M, anteile = R.momententragfaehigkeit([ra, rb], F_c_Rd=1e9)
    close("M_j,Rd ohne Begrenzung", M, 300e3 * 0.5 + 300e3 * 0.4, 1e-9, " Nm")
    M2, anteile2 = R.momententragfaehigkeit([ra, rb], F_c_Rd=400e3)
    close("M_j,Rd mit begrenzter Druckzone", M2, 300e3 * 0.5 + 100e3 * 0.4, 1e-9, " Nm")
    check("die unterste Reihe wird zuerst abgebaut",
          abs(anteile2[0][1] - 300e3) < 1 and abs(anteile2[1][1] - 100e3) < 1,
          str([f"{F / 1e3:.0f}" for _h, F, _v in anteile2]))

    # -- Rotationsvermoegen 6.4.2(2) --------------------------------------
    d, fub, fy = 0.024, 1000e6, 355e6
    grenze_t = 0.36 * d * math.sqrt(fub / fy)
    ok1, _ = R.rotationskapazitaet("Modus 1 (Blech)", 0.9 * grenze_t, d, fub, fy)
    ok2, _ = R.rotationskapazitaet("Modus 1 (Blech)", 1.1 * grenze_t, d, fub, fy)
    ok3, _ = R.rotationskapazitaet("Modus 3 (Schraube)", 0.5 * grenze_t, d, fub, fy)
    check("dünnes Blech mit Blechbiegen: Rotationsvermögen ausreichend", ok1)
    check("zu dickes Blech: nicht ausreichend", not ok2,
          f"Grenze {grenze_t * 1e3:.1f} mm")
    check("Schraubenversagen ist nicht duktil", not ok3)


def test_gelenk_in_der_rechnung():
    """Die Drehfeder des Anschlusses muss in der Rechnung ankommen.

    Kragarm der Laenge L mit Endlast P. Sitzt am Einspannknoten eine
    Drehfeder S, verdreht sich der Stabanfang um phi = M/S = P L / S; die
    Spitze senkt sich zusaetzlich um phi L::

        w = P L^3 / (3 E I) + P L^2 / S
    """
    from statik3d import solver
    from statik3d.model import Model, Material, Section
    from statik3d.joints import anschluss as A

    L, P = 4.0, 20e3
    E, I = 210e9, 8356e-8            # IPE 300
    for S, name in ((1e12, "sehr steif"), (5e6, "weich"), (2e7, "mittel")):
        m = Model("Kragarm")
        m.add_material(Material.steel("S355"))
        m.add_section(Section("IPE 300", A=53.8e-4, Iy=I, Iz=604e-8, It=20.1e-8,
                              Wpl_y=628e-6, Wel_y=557e-6, typ="I", h=0.300, b=0.150,
                              tw=0.0071, tf=0.0107, r=0.015, zmax=0.150, ymax=0.075))
        n0 = m.add_node(0, 0, 0)
        n1 = m.add_node(L, 0, 0)
        e = m.add_element("beam", [n0, n1], "S355", "IPE 300")
        m.fix(n0, "all")
        m.load_node(n1, Fz=-P)
        m.joints["A1"] = A.als_joint(
            __import__("statik3d.joints.templates", fromlist=["propose"]).propose(
                "kopfplatte", m, e, end=0, N=0.0, Vz=P, My=P * L), "A1")
        m.joints["A1"].modellierung = "feder"
        m.joints["A1"].S_j = S
        an = solver.solve_all(m, combinations=False, envelopes=False)
        u = an.cases[m.active_case].u[n1, 2]
        soll = -(P * L ** 3 / (3 * E * I) + P * L ** 2 / S)
        close(f"Kragarm mit Drehfeder S = {S:.0e} Nm/rad ({name})", u, soll, 2e-3, " m")

    # Gelenk und starr als Grenzfaelle
    def bau(modellierung):
        m = Model("Kragarm")
        m.add_material(Material.steel("S355"))
        m.add_section(Section("IPE 300", A=53.8e-4, Iy=I, Iz=604e-8, It=20.1e-8,
                              Wpl_y=628e-6, Wel_y=557e-6, typ="I", h=0.300, b=0.150,
                              tw=0.0071, tf=0.0107, r=0.015, zmax=0.150, ymax=0.075))
        n0 = m.add_node(0, 0, 0)
        n1 = m.add_node(L, 0, 0)
        n2 = m.add_node(2 * L, 0, 0)
        e0 = m.add_element("beam", [n0, n1], "S355", "IPE 300")
        m.add_element("beam", [n1, n2], "S355", "IPE 300")
        m.fix(n0, "all")
        m.fix(n2, [2])
        m.load_node(n1, Fz=-P)
        from statik3d.joints.templates import propose
        m.joints["A1"] = A.als_joint(propose("kopfplatte", m, e0, end=0,
                                             N=0.0, Vz=P, My=P * L), "A1")
        m.joints["A1"].modellierung = modellierung
        return m, n1, e0

    m_s, n1, e0 = bau("starr")
    u_starr = solver.solve_all(m_s, combinations=False, envelopes=False).cases[
        m_s.active_case].u[n1, 2]
    m_g, n1g, e0g = bau("gelenkig")
    ang = solver.solve_all(m_g, combinations=False, envelopes=False)
    u_gel = ang.cases[m_g.active_case].u[n1g, 2]
    check("Gelenk am Stabanfang verformt mehr als starr",
          abs(u_gel) > abs(u_starr) * 1.2,
          f"{u_gel * 1e3:.2f} mm gegen {u_starr * 1e3:.2f} mm")
    check("das Gelenk steht auch am Element", 4 in m_g.elements[e0g].hinges,
          str(m_g.elements[e0g].hinges))
    check("starr setzt weder Feder noch Gelenk",
          not m_s.elements[e0].hinges and not m_s.elements[e0].hinge_springs)

    # wiederholtes Rechnen darf die Federn nicht anhaeufen
    m_f, n1f, e0f = bau("feder")
    m_f.joints["A1"].S_j = 1e7
    for _ in range(3):
        solver.solve_all(m_f, combinations=False, envelopes=False)
    check("wiederholtes Rechnen häuft keine Federn an",
          m_f.elements[e0f].hinge_springs == [(4, 1e7)],
          str(m_f.elements[e0f].hinge_springs))


def test_gelenk_im_modell_und_bericht():
    from statik3d import solver, examples_lib
    from statik3d.joints import anschluss as A
    from statik3d.joints.templates import propose
    from statik3d.report import Report

    m = examples_lib.build_example("hall")
    r = m.members["Riegel"]
    m.joints["K1"] = A.als_joint(propose("kopfplatte", m, r.elements[0], end=0,
                                         N=-50e3, Vz=160e3, My=400e3), "K1")
    an = solver.solve_all(m, design=True)
    ohne = an.joints.joints["K1"].gelenk
    check("ohne Stütze wird die obere Schranke benannt",
          any("obere Schranke" in h for h in ohne.hinweise), str(ohne.hinweise)[:60])

    m.joints["K1"].stuetze = {"section": "HEB 300"}
    an2 = solver.solve_all(m, design=True)
    mit = an2.joints.joints["K1"].gelenk
    check("die Stütze macht den Anschluss weicher",
          mit.S_j_ini < ohne.S_j_ini,
          f"{mit.S_j_ini / 1e6:.1f} < {ohne.S_j_ini / 1e6:.1f} MNm/rad")
    check("die Komponenten der Stütze sind dabei",
          {k for k, _v, _t in mit.komponenten} >= {"k_1", "k_2", "k_3", "k_4"},
          str(sorted({k for k, _v, _t in mit.komponenten})))
    check("mit Stütze gilt der Nachweis als vollständig", mit.vollstaendig)

    m.joints["K1"].stuetze = {"section": "gibtsnicht"}
    c = solver.solve_all(m, design=True).joints.joints["K1"]
    check("unbekannter Stützenquerschnitt wird gemeldet",
          any("gibtsnicht" in h for h in c.hinweise), str(c.hinweise)[:70])
    m.joints["K1"].stuetze = {"section": "HEB 300"}

    # Klassifizierung schlaegt auf die Rechnung durch
    m.joints["K1"].modellierung = "feder"
    an3 = solver.solve_all(m, design=True)
    e = m.elements[r.elements[0]]
    check("die Drehfeder sitzt am Stabende",
          any(d == 4 for d, _k in e.hinge_springs), str(e.hinge_springs))
    check("die Rechnung nennt die Feder",
          "K1" in an3.info.get("anschlussfedern", {}),
          str(an3.info.get("anschlussfedern")))

    # Momententragfaehigkeit ist ein Nachweis
    c3 = an3.joints.joints["K1"]
    check("M_j,Rd steht unter den Nachweisen",
          any("M_j,Rd" in x["name"] for x in c3.checks))

    html = Report(m, an3).html()
    for text in ("S_j,ini", "Komponentenverfahren", "Steifigkeitsbeiwerte nach Tab. 6.11",
                 "Rotationsvermögen", "Klassifizierung Steifigkeit", "k_5", "k_10",
                 "Schraubenreihen der Zugzone"):
        check(f"Bericht nennt „{text}“", text in html)
    check("der alte Ausschluss der Kennlinien ist weg",
          "Momenten-Rotations-Kennlinien nach 6.3 sind nicht enthalten" not in html)


def main():
    for t in (test_schrauben, test_naehte, test_tstub, test_fe_schraube,
              test_bleche, test_nachweise, test_vorlagen, test_anschluss_im_modell,
              test_momenten_rotation, test_gelenk_in_der_rechnung,
              test_gelenk_im_modell_und_bericht):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
