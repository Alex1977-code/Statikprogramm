"""
Verifikation der wirksamen Querschnitte der Klasse 4 nach DIN EN 1993-1-5,
Abschnitt 4, und des Schalenbeulens schlanker Kreisrohre nach EN 1993-1-6.

Geprueft wird gegen die Zahlenwerte der Norm (Beulwerte Tab. 4.1 und 4.2,
Grenzschlankheiten 0,673 und 0,748, Aufteilung b_e1/b_e2 nach Tab. 4.1) sowie
gegen eine unabhaengige Handrechnung des wirksamen Querschnitts eines
geschweissten Blechtraegers.

Aufruf:  python -m tests.test_klasse4
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material, Section                    # noqa: E402
from statik3d.profiles import make_section                             # noqa: E402
from statik3d.combinations import generate_combinations                # noqa: E402
from statik3d import solver                                            # noqa: E402
from statik3d.ec3 import classify, section_check                       # noqa: E402
from statik3d.ec3 import section_class as SC                           # noqa: E402

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
def blechtraeger(h=1.500, b=0.400, tf=0.020, tw=0.008) -> Section:
    """Geschweisster Blechtraeger ohne Ausrundungen."""
    hw = h - 2 * tf
    A = 2 * b * tf + hw * tw
    Iy = b * h ** 3 / 12 - (b - tw) * hw ** 3 / 12
    Iz = 2 * tf * b ** 3 / 12 + hw * tw ** 3 / 12
    return Section(name=f"SB {h * 1e3:.0f}", typ="I", A=A, Iy=Iy, Iz=Iz,
                   It=(2 * b * tf ** 3 + hw * tw ** 3) / 3,
                   Iw=Iz * (h - tf) ** 2 / 4, h=h, b=b, tw=tw, tf=tf, r=0.0,
                   Wel_y=Iy / (h / 2), Wel_z=Iz / (b / 2),
                   Wpl_y=b * tf * (h - tf) + tw * hw ** 2 / 4,
                   Wpl_z=tf * b ** 2 / 2 + hw * tw ** 2 / 4,
                   Asz=hw * tw, Asy=2 * b * tf, fabrication="welded")


def test_beulwerte_und_rho():
    # Tab. 4.1 (beidseitig gestuetzt)
    for psi, soll in ((1.0, 4.0), (0.0, 7.81), (-1.0, 23.9)):
        close(f"k_σ Tab. 4.1 für ψ = {psi:g}", SC.k_sigma_internal(psi), soll, 2e-3)
    # Tab. 4.2 (einseitig, Druck am freien Rand)
    close("k_σ Tab. 4.2 für ψ = 1", SC.k_sigma_outstand(1.0), 0.43, 1e-12)
    close("k_σ Tab. 4.2 für ψ = 0", SC.k_sigma_outstand(0.0), 0.578 / 0.34, 1e-12)
    check("es ist dieselbe Tabelle wie beim Blechbeulen",
          SC.k_sigma_internal(-0.5) == __import__(
              "statik3d.ec3.beulen", fromlist=["k_sigma"]).k_sigma(-0.5))

    eps = math.sqrt(235 / 355)
    # Grenzschlankheiten 4.4(2)
    i = SC._rho_info(50.0, eps, 1.0, 4.0, True)
    close("Grenze innen für ψ = 1", i["grenze"], 0.673, 2e-3)
    i2 = SC._rho_info(50.0, eps, 1.0, 0.43, False)
    close("Grenze außen", i2["grenze"], 0.748, 1e-12)
    # rho nach Gl. (4.2)
    d = SC._rho_info(182.5, eps, -1.0, SC.k_sigma_internal(-1.0), True)
    lam = 182.5 / (28.4 * eps * math.sqrt(SC.k_sigma_internal(-1.0)))
    close("λ̄_p = (b/t)/(28,4 ε √k_σ)", d["lambda_p"], lam, 1e-12)
    close("ρ = (λ̄_p − 0,055(3+ψ))/λ̄_p²", d["rho"],
          (lam - 0.055 * 2) / lam ** 2, 1e-12)
    check("gedrungenes Teil beult nicht",
          SC._rho_info(30.0, eps, 1.0, 4.0, True)["rho"] == 1.0)


def test_wirksamer_blechtraeger():
    """W_eff,y gegen eine unabhaengige Handrechnung."""
    sec = blechtraeger()
    fy = 355e6
    c = classify(sec, fy, 0.0, 1e6)
    check("schlanker Steg gibt Klasse 4", c.cls == 4 and c.web == 4,
          f"Klasse {c.cls} (Flansch {c.flange}, Steg {c.web})")
    w = c.details["wirksam"]["biegung_y"]

    eps = math.sqrt(235 / 355)
    h, b, tf, tw = sec.h, sec.b, sec.tf, sec.tw
    hw = h - 2 * tf
    k = SC.k_sigma_internal(-1.0)
    lam = (hw / tw) / (28.4 * eps * math.sqrt(k))
    rho = (lam - 0.055 * (3 - 1)) / lam ** 2
    bc = hw / 2
    beff = rho * bc
    close("ρ des Stegs", w["steg"]["rho"], rho, 1e-12)
    close("b_eff = ρ b_c", w["b_eff"], beff, 1e-12, " m")
    close("b_e1 = 0,4 b_eff (Tab. 4.1)", w["b_e1"], 0.4 * beff, 1e-12, " m")
    close("b_e2 = 0,6 b_eff", w["b_e2"], 0.6 * beff, 1e-12, " m")

    # Handrechnung des wirksamen Querschnitts
    zt = h / 2
    zc = zt - tf - bc
    rects = [(-b / 2, b / 2, zt - tf, zt), (-b / 2, b / 2, -zt, -zt + tf),
             (-tw / 2, tw / 2, zt - tf - 0.4 * beff, zt - tf),
             (-tw / 2, tw / 2, zc, zc + 0.6 * beff),
             (-tw / 2, tw / 2, -zt + tf, zc)]
    Ae = sum((y1 - y0) * (z1 - z0) for y0, y1, z0, z1 in rects)
    zs = sum((y1 - y0) * (z1 - z0) * 0.5 * (z0 + z1) for y0, y1, z0, z1 in rects) / Ae
    Ie = sum((y1 - y0) * (z1 - z0) ** 3 / 12
             + (y1 - y0) * (z1 - z0) * (0.5 * (z0 + z1) - zs) ** 2
             for y0, y1, z0, z1 in rects)
    We = Ie / max(zt - zs, zt + zs)
    close("Schwerachse z_s des wirksamen Querschnitts", w["z_s"], zs, 1e-9, " m")
    close("I_eff", w["I_eff"], Ie, 1e-9, " m⁴")
    close("W_eff,y gegen die Handrechnung", c.Weff_y, We, 1e-9, " m³")
    check("W_eff,y ist kleiner als W_el,y", c.Weff_y < sec.Wel_y,
          f"{c.Weff_y * 1e6:.1f} < {sec.Wel_y * 1e6:.1f} cm³")

    # reiner Druck: A_eff und e_N
    cd = classify(sec, fy, -1e6)
    i_w = SC._rho_info(hw / tw, eps, 1.0, 4.0, True)
    i_f = SC._rho_info((b - tw) / 2 / tf, eps, 1.0, 0.43, False)
    soll = 2 * (tw + 2 * i_f["rho"] * (b - tw) / 2) * tf + i_w["rho"] * hw * tw
    close("A_eff unter reinem Druck", cd.A_eff, soll, 1e-9, " m²")
    check("e_N = 0 beim doppeltsymmetrischen Querschnitt",
          abs(cd.eN_y) < 1e-12 and abs(cd.eN_z) < 1e-12,
          f"e_Ny = {cd.eN_y * 1e3:+.3e} mm")
    check("e_N wird berechnet, nicht gesetzt",
          "e_N" in cd.details["wirksam"])

    # dickerer Steg: Klasse 3, keine Abminderung
    dick = blechtraeger(tw=0.020)
    c3 = classify(dick, fy, 0.0, 1e6)
    check("der dicke Steg ist nicht mehr Klasse 4", c3.cls < 4,
          f"Klasse {c3.cls}, h_w/t_w = {(dick.h - 2 * dick.tf) / dick.tw:.1f}")
    close("dann bleibt W_eff = W_el", c3.Weff_y, dick.Wel_y, 1e-12, " m³")


def test_zusatzmoment_eN():
    """Klasse 4 mit e_N != 0: ΔM = N e_N geht in 6.2.9.3 ein."""
    sec = blechtraeger()
    fy = 355e6
    c = classify(sec, fy, -2000e3, 500e3)
    r = section_check(sec, fy, -2000e3, 0.0, 0.0, 0.0, 500e3, 0.0, 1.0, c)
    name = "N+M elastisch (6.2.9.2/3)"
    check("die Interaktion 6.2.9.3 wird geführt", name in r["checks"])
    u, txt = r["checks"][name]
    soll = (2000e3 / (c.A_eff * fy) + 500e3 / (c.Weff_y * fy))
    close("N/(A_eff f_yd) + M/(W_eff f_yd)", u, soll, 1e-9)
    check("der Bericht nennt e_N ausdrücklich", "e_N" in txt, txt[-60:])

    # kuenstlich verschobene Schwerachse: das Zusatzmoment muss wirken
    c2 = classify(sec, fy, -2000e3, 500e3)
    c2.eN_y = 0.010
    r2 = section_check(sec, fy, -2000e3, 0.0, 0.0, 0.0, 500e3, 0.0, 1.0, c2)
    u2 = r2["checks"][name][0]
    close("ΔM = N e_N erhöht die Ausnutzung",
          u2, soll + 2000e3 * 0.010 / (c.Weff_y * fy), 1e-9)
    check("und wird beziffert", "ΔM" in r2["checks"][name][1],
          r2["checks"][name][1][-70:])


def test_schlankes_rohr():
    """CHS Klasse 4: EN 1993-1-6 statt Bruttoquerschnitt."""
    sec = make_section("CHS 508x8")
    fy = 355e6
    dt = sec.h / sec.tw
    check("d/t > 90 ε² gibt Klasse 4", dt > 90 * 235 / 355,
          f"d/t = {dt:.1f} > {90 * 235 / 355:.1f}")
    c = classify(sec, fy, -2000e3, 300e3)
    check("Klasse 4", c.cls == 4)
    check("die alte Warnung ist weg",
          not any("Bruttoquerschnitt" in w for w in c.warnings), str(c.warnings)[:70])
    check("und der Schalenbeulnachweis ist angekündigt",
          c.details.get("schalenbeulen") is True)

    r = section_check(sec, fy, -2000e3, 0.0, 200e3, 0.0, 300e3, 0.0, 1.0, c,
                      l_schale=6.0)
    name = "Schalenbeulen Rohr (EN 1993-1-6, 8.5)"
    check("der Nachweis wird geführt", name in r["checks"], str(list(r["checks"]))[:80])
    # gegen den Kern gerechnet
    from statik3d.ec3.schalenbeulen import zylinder
    r_m = (sec.h - sec.tw) / 2
    s_x = 2000e3 / sec.A + 300e3 / sec.Wel_y
    tau = 200e3 / sec.Asz
    z = zylinder(r=r_m, t=sec.tw, l=6.0, fy=fy, sigma_x=s_x, tau=tau, klasse="B")
    close("Ausnutzung = Interaktion 8.5.3(3)", r["checks"][name][0], z.util, 1e-9)
    check("und ist hier maßgebend", r["governing"] == name,
          f"{r['governing']} mit {r['util']:.3f}")

    # dickeres Rohr: kein Schalenbeulen
    dick = make_section("CHS 508x16")
    cd = classify(dick, fy, -2000e3)
    rd = section_check(dick, fy, -2000e3, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, cd, l_schale=6.0)
    check("das dicke Rohr braucht keinen Schalenbeulnachweis",
          cd.cls < 4 and name not in rd["checks"],
          f"Klasse {cd.cls}, d/t = {dick.h / dick.tw:.1f}")


def test_im_modell_und_bericht():
    from statik3d.report import Report
    sec = blechtraeger()
    m = Model("Blechtraeger")
    m.add_material(Material.steel("S355"))
    m.add_section(sec)
    L, n = 24.0, 8
    ids = [m.add_node(L * i / n, 0.0, 0.0) for i in range(n + 1)]
    els = [m.add_element("beam", [ids[i], ids[i + 1]], "S355", sec.name) for i in range(n)]
    mem = m.add_member("Träger", els)
    mem.L_LT, mem.a_steifen, mem.starre_endsteife = 4.0, 3.0, True
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[n], [1, 2, 3])
    m.add_load_case("LF1", "G", "Eigengewicht")
    m.add_load_case("LF2", "Q_E", "Lagerlast")
    for e in els:
        m.load_beam(e, qz=-12e3, case="LF1")
        m.load_beam(e, qz=-20e3, case="LF2")
    generate_combinations(m)
    an = solver.solve_all(m, design=True)
    mc = an.design.members["Träger"]
    check("der Stab ist Klasse 4", mc.cls == 4, f"Klasse {mc.cls}")
    best = max(mc.section_checks, key=lambda s: s["util"])
    w = best.get("wirksam") or {}
    check("die wirksamen Werte stehen im Ergebnis",
          bool(w) and w.get("A_eff", 0) > 0 and w.get("Weff_y", 0) > 0)
    close("A_eff des Ergebnisses = A_eff der Klassifizierung",
          w["A_eff"], classify(sec, 355e6, best["N"], best["My"], best["Mz"]).A_eff,
          1e-12, " m²")

    html = Report(m, an).html()
    for text in ("Wirksamer Querschnitt (Klasse 4)",
                 "Querschnittsteile: Schlankheit und Abminderungsbeiwert",
                 "wirksame Stegbreite (Biegung y)", "Schwerachse des wirksamen",
                 "Fläche A → A_eff", "Verschiebung der Schwerachse e_N",
                 "λ̄_p"):
        check(f"Bericht nennt „{text}“", text in html)
    check("die Ausrundungen werden als sichere Seite benannt",
          "sicheren Seite" in html)
    check("kein rohes HTML im Text", "&lt;b&gt;" not in html and "<b>wirksamen" not in html)

    # Klasse-3-Vergleich: kein Abschnitt
    m2 = Model("dick")
    dick = blechtraeger(tw=0.020)
    m2.add_material(Material.steel("S355"))
    m2.add_section(dick)
    ids2 = [m2.add_node(L * i / n, 0.0, 0.0) for i in range(n + 1)]
    els2 = [m2.add_element("beam", [ids2[i], ids2[i + 1]], "S355", dick.name)
            for i in range(n)]
    mem2 = m2.add_member("Träger", els2)
    mem2.L_LT = 4.0
    m2.fix(ids2[0], [0, 1, 2, 3])
    m2.fix(ids2[n], [1, 2, 3])
    m2.add_load_case("LF1", "G", "Eigengewicht")
    for e in els2:
        m2.load_beam(e, qz=-12e3, case="LF1")
    generate_combinations(m2)
    an2 = solver.solve_all(m2, design=True)
    h2 = Report(m2, an2).html()
    check("beim gedrungenen Querschnitt entfällt der Abschnitt",
          "Wirksamer Querschnitt (Klasse 4)" not in h2)


def main():
    print("=" * 92)
    print("STATIK3D - Verifikation Klasse 4 (DIN EN 1993-1-5, Abschnitt 4)")
    print("=" * 92)
    for t in (test_beulwerte_und_rho, test_wirksamer_blechtraeger,
              test_zusatzmoment_eN, test_schlankes_rohr, test_im_modell_und_bericht):
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
