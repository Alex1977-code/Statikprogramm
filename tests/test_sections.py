"""
Profildatenbank nach Laendern und zusammengesetzte Querschnitte.
Katalogwerte aus EN 10365 / DIN 1026 / EN 10056 / BS 4-1 / AISC.
Aufruf:  python -m tests.test_sections
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Section  # noqa: E402
from statik3d import profiles as P, sections as S  # noqa: E402

RESULTS = []
IN2, IN4 = 6.4516, 41.623          # in^2 -> cm^2, in^4 -> cm^4


def check(name, num, ana, tol, unit=""):
    num, ana = float(num), float(ana)
    err = abs(num - ana) / (abs(ana) if abs(ana) > 1e-12 else 1.0)
    ok = err <= tol
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:46s} num={num: .5e} kat={ana: .5e} "
          f"Abw={err * 100:6.2f}% {unit}")
    return ok


def test_datenbank():
    check("Laender in der Datenbank", len(P.countries()), 3, 0)
    check("Profile gesamt", len(P.list_profiles()) > 400, True, 0)
    for c, n_min in (("EU", 300), ("GB", 40), ("US", 40)):
        check(f"Profile Land {c}", len(P.list_profiles(country=c)) >= n_min, True, 0)
    check("Familie zu Land", P.country_of("UB"), "GB" == "GB" and 1.0, 0) if False else None
    check("country_of(UB) = GB", 1.0 if P.country_of("UB") == "GB" else 0.0, 1.0, 0)
    check("country_of(W) = US", 1.0 if P.country_of("W") == "US" else 0.0, 1.0, 0)
    n = 0
    for d in P.list_profiles():
        s = P.make_section(d)
        if s.A > 0 and s.Iy > 0 and s.Iz > 0 and s.It > 0:
            n += 1
    check("alle Profile liefern gueltige Werte", n, len(P.list_profiles()), 0)
    try:
        P.make_section("XYZ 999")
        check("unbekanntes Profil meldet Fehler", 0.0, 1.0, 0)
    except KeyError as ex:
        check("unbekanntes Profil meldet Fehler", 1.0 if "unbekannt" in str(ex) else 0.0, 1.0, 0)


def test_katalogwerte():
    """A, Iy, Iz gegen Katalogwerte (cm^2 / cm^4)."""
    kat = {
        # EN 10365 / DIN 1026-2 (parallele Flansche) - Abweichung < 1 %
        "IPE 300": (53.8, 8356, 604, 0.01), "HEB 300": (149.1, 25170, 8563, 0.02),
        "UPE 200": (29.0, 1910, 187, 0.01), "UPE 300": (56.6, 7820, 538, 0.02),
        # DIN 1026-1 (geneigte Flansche): Zehenausrundung nicht erfasst -> bis 5 %
        "UPN 200": (32.2, 1910, 148, 0.06), "UPN 100": (13.5, 206, 29.3, 0.06),
        # EN 10056 Winkel: Iy/Iz sind die Hauptwerte
        "L 100x100x10": (19.2, 280, 72.9, 0.03),
        # BS 4-1
        "UB 457x191x74": (94.6, 33300, 1670, 0.01), "UC 254x254x89": (113.0, 14300, 4860, 0.01),
        # AISC (aus den Nennabmessungen gerechnet)
        "W14x90": (26.5 * IN2, 999 * IN4, 362 * IN4, 0.02),
        "W36x150": (44.2 * IN2, 9040 * IN4, 270 * IN4, 0.02),
        "C10x15.3": (4.48 * IN2, 67.3 * IN4, 2.27 * IN4, 0.03),
        "HSS8x8x1/2": (13.5 * IN2, 125 * IN4, 125 * IN4, 0.04),
    }
    for d, (A, Iy, Iz, tol) in kat.items():
        s = P.make_section(d)
        check(f"{d}: A", s.A * 1e4, A, tol, "cm2")
        check(f"{d}: Iy", s.Iy * 1e8, Iy, tol, "cm4")
        check(f"{d}: Iz", s.Iz * 1e8, Iz, tol, "cm4")


def test_rohre():
    """Rohre: Flaeche gegen AISC (Bemessungswanddicke 0.93 t) und Ringformel."""
    import math as _m
    d_in, t_nom = 6.625, 0.280
    D, t = d_in * P.INCH, 0.93 * t_nom * P.INCH
    s = P.make_section("PIPE 6 STD")
    check("PIPE 6 STD: A (AISC 5.20 in2)", s.A * 1e4, 5.20 * IN2, 0.02, "cm2")
    check("PIPE 6 STD: A = Ringformel", s.A, _m.pi / 4 * (D ** 2 - (D - 2 * t) ** 2), 1e-9, "m2")
    check("PIPE 6 STD: I = Ringformel", s.Iy, _m.pi / 64 * (D ** 4 - (D - 2 * t) ** 4), 1e-9, "m4")
    c = P.make_section("CHS 168.3x5")
    Dc, tc = 0.1683, 0.005
    check("CHS 168.3x5: A = Ringformel", c.A, _m.pi / 4 * (Dc ** 2 - (Dc - 2 * tc) ** 2), 1e-9, "m2")
    check("CHS 168.3x5: A (Katalog 25.7 cm2)", c.A * 1e4, 25.7, 0.01, "cm2")
    check("CHS 168.3x5: I (Katalog 856 cm4)", c.Iy * 1e8, 856, 0.01, "cm4")


def test_winkel_hauptachsen():
    """Winkel: Drehung um alpha muss die Traegheitsmatrix diagonalisieren."""
    for d, tan_kat in (("L 100x100x10", 1.0), ("L 100x50x8", 0.259), ("L 150x90x10", 0.360)):
        s = P.make_section(d)
        I = np.array([[s.Iy_geo, s.Iyz_geo], [s.Iyz_geo, s.Iz_geo]])
        c, sn = math.cos(s.alpha), math.sin(s.alpha)
        R = np.array([[c, -sn], [sn, c]])
        Ip = R.T @ I @ R
        check(f"{d}: Hauptachsen diagonal", abs(Ip[0, 1]) / max(s.Iy, 1e-20), 0.0, 1e-9)
        check(f"{d}: I1 aus Drehung", Ip[0, 0], s.Iy, 1e-9, "m4")
        check(f"{d}: I2 aus Drehung", Ip[1, 1], s.Iz, 1e-9, "m4")
        check(f"{d}: tan(alpha)", abs(math.tan(s.alpha)), tan_kat, 0.05)


def test_zusammengesetzt():
    """Steiner-Anteile gegen Handrechnung."""
    one = P.make_section("IPE 300")
    d = 0.200
    c = S.build("2 IPE 300", [("IPE 300", -d / 2, 0), ("IPE 300", +d / 2, 0)])
    check("2x IPE 300: A", c.A, 2 * one.A, 1e-12, "m2")
    check("2x IPE 300: Iy", c.Iy, 2 * one.Iy, 1e-12, "m4")
    check("2x IPE 300: Iz mit Steiner", c.Iz, 2 * (one.Iz + one.A * (d / 2) ** 2), 1e-12, "m4")
    check("2x IPE 300: It Summe", c.It, 2 * one.It, 1e-12, "m4")

    h, b, tw, tf = 0.600, 0.400, 0.012, 0.020
    bx = S.box_from_plates("Kasten", h, b, tw, tf)
    A_ana = 2 * tw * (h - 2 * tf) + 2 * b * tf
    Iy_ana = 2 * (tw * (h - 2 * tf) ** 3 / 12) + 2 * (b * tf ** 3 / 12 + b * tf * ((h - tf) / 2) ** 2)
    check("Kasten aus Blechen: A", bx.A, A_ana, 1e-12, "m2")
    check("Kasten aus Blechen: Iy", bx.Iy, Iy_ana, 1e-12, "m4")

    base = P.make_section("IPE 400")
    pl_b, pl_t = 0.300, 0.015
    pi = S.plated_i("IPE 400 + Gurtplatten", "IPE 400", pl_b, pl_t)
    dz = base.h / 2 + pl_t / 2
    Iy_ana = base.Iy + 2 * (pl_b * pl_t ** 3 / 12 + pl_b * pl_t * dz ** 2)
    check("I mit Gurtplatten: A", pi.A, base.A + 2 * pl_b * pl_t, 1e-12, "m2")
    check("I mit Gurtplatten: Iy", pi.Iy, Iy_ana, 1e-12, "m4")

    a1 = P.make_section("L 100x100x10")
    da = S.double_angle("2L 100x100x10", "L 100x100x10", gap=0.010)
    check("2 Winkel: A", da.A, 2 * a1.A, 1e-12, "m2")
    check("2 Winkel: Hauptachsen ungedreht (symmetrisch)", abs(da.alpha), 0.0, 1e-9, "rad")
    check("2 Winkel: Teile vermerkt", len(da.parts), 2, 0)
    check("Beschreibung nennt die Teile", 1.0 if "L 100" in S.describe(da) else 0.0, 1.0, 0)

    dc = S.double_channel("2 UPE 200 Kasten", "UPE 200", gap=0.100, back_to_back=False)
    u = P.make_section("UPE 200")
    check("2 U-Profile Kasten: A", dc.A, 2 * u.A, 1e-12, "m2")
    check("2 U-Profile Kasten: Iy", dc.Iy, 2 * u.Iy, 1e-9, "m4")

    # Drehung: ein um 90 Grad gedrehtes Profil vertauscht Iy und Iz
    rot = S.build("IPE 300 gedreht", [("IPE 300", 0, 0, 90)])
    check("Drehung 90 Grad vertauscht Iy/Iz", rot.Iy, one.Iy, 1e-12, "m4")
    check("Drehung 90 Grad: I2", rot.Iz, one.Iz, 1e-12, "m4")


def test_querschnitt_im_modell():
    """Zusammengesetzter Querschnitt rechnet im Modell (Kragarm f = FL^3/3EI)."""
    from statik3d.model import Model, Material
    from statik3d import solver, mesher
    E, L, F = 210e9, 4.0, 20e3
    sec = S.plated_i("IPE 300 + Platten", "IPE 300", 0.200, 0.012)
    m = Model("Kragarm")
    m.add_material(Material("S", E=E))
    m.add_section(sec)
    ids = mesher.line_of_beams(m, "S", sec.name, (0, 0, 0), (L, 0, 0), 8)
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fz=-F)
    r = solver.solve_static(m)
    check("Kragarm mit zusammengesetztem Querschnitt", abs(r.u[ids[-1], 2]),
          F * L ** 3 / (3 * E * sec.Iy), 0.02, "m")


def test_frei():
    """T-Profil, Blechstreifen, Polygone und das frei zusammengesetzte Profil -
    alles gegen geschlossene Formeln und gegeneinander."""
    # --- T-Profil gegen das Polygon derselben Kontur (zwei getrennte Rechenwege)
    h, b, tw, tf = 0.2, 0.1, 0.01, 0.012
    t = Section.tee("T", h, b, tw, tf)
    check("T: Flaeche", t.A, b * tf + (h - tf) * tw, 1e-12, "m²")
    zc = (b * tf * tf / 2 + (h - tf) * tw * (tf + (h - tf) / 2)) / t.A
    check("T: Schwerpunkt zc", t.zc, zc, 1e-12, "m")
    kontur = [(-b / 2, 0), (b / 2, 0), (b / 2, -tf), (tw / 2, -tf), (tw / 2, -h),
              (-tw / 2, -h), (-tw / 2, -tf), (-b / 2, -tf)]
    pg = S.polygon("T-Polygon", kontur)
    check("T: Iy = Polygon (Green)", t.Iy, pg.Iy, 1e-10, "m⁴")
    check("T: Iz = Polygon (Green)", t.Iz, pg.Iz, 1e-10, "m⁴")
    check("T: Schwerpunkt = Polygon", t.zc, -pg.zc, 1e-10, "m")
    # Wpl,y: Nulllinie halbiert die Flaeche - hier im Steg
    A0 = t.A / 2
    z0 = tf + (A0 - b * tf) / tw
    Wpl = b * tf * (z0 - tf / 2) + tw * (z0 - tf) ** 2 / 2 + tw * (h - z0) ** 2 / 2
    check("T: Wpl,y aus der plastischen Nulllinie", t.Wpl_y, Wpl, 1e-12, "m³")
    # Halbiertes IPE: halbe Flaeche, halbes Iz
    ipe, ipet = P.make_section("IPE 200"), P.make_section("IPET 200")
    check("IPET 200: A = A(IPE 200)/2", ipet.A, ipe.A / 2, 1e-12, "m²")
    # Katalogkonstante 0,2146 gegen (1 − π/4): Abweichung im 1e-7-Bereich
    check("IPET 200: Iz = Iz(IPE 200)/2", ipet.Iz, ipe.Iz / 2, 1e-5, "m⁴")
    check("IPET in der Datenbank", 1.0 if "IPET 200" in P.list_profiles("IPET") else 0.0, 1.0, 0)
    check("family_of(HEAT 200)", 1.0 if P.family_of("HEAT 200") == "HEAT" else 0.0, 1.0, 0)

    # --- Blechstreifen (Element): waagerecht, senkrecht, schraeg
    L, tt = 0.3, 0.01
    w = S.segment("w", (0, 0), (L, 0), tt)
    check("Streifen waagerecht: Iy_geo = L t³/12", w.Iy_geo, L * tt ** 3 / 12, 1e-12, "m⁴")
    check("Streifen waagerecht: Iz_geo = t L³/12", w.Iz_geo, tt * L ** 3 / 12, 1e-12, "m⁴")
    check("Streifen: It = L t³/3", w.It, L * tt ** 3 / 3, 1e-12, "m⁴")
    v = S.segment("v", (0, 0), (0, L), tt)
    check("Streifen senkrecht: Iy_geo = t L³/12", v.Iy_geo, tt * L ** 3 / 12, 1e-12, "m⁴")
    d = S.segment("d", (0, 0), (L / math.sqrt(2), L / math.sqrt(2)), tt)
    Il, Iq = tt * L ** 3 / 12, L * tt ** 3 / 12
    check("Streifen 45°: Iy_geo = (Il + Iq)/2", d.Iy_geo, (Il + Iq) / 2, 1e-10, "m⁴")
    check("Streifen 45°: Iyz_geo = (Il − Iq)/2", d.Iyz_geo, (Il - Iq) / 2, 1e-10, "m⁴")
    check("Streifen 45°: Hauptwert I1 = Il", d.Iy, Il, 1e-10, "m⁴")
    check("Streifen 45°: Hauptachse 45°", d.alpha, math.pi / 4, 1e-10, "rad")

    # --- Polygone: Rechteck mit Versatz, Rechteck mit Loch, duenner Ring
    bb, hh, y0, z0 = 0.2, 0.4, 0.5, -0.3
    R = [(y0, z0), (y0 + bb, z0), (y0 + bb, z0 + hh), (y0, z0 + hh)]
    pr = S.polygon("R", R)
    rr = Section.rectangle("R", bb, hh)
    check("Polygon Rechteck: A", pr.A, rr.A, 1e-12, "m²")
    check("Polygon Rechteck: Iy", pr.Iy, rr.Iy, 1e-12, "m⁴")
    check("Polygon Rechteck: Iz", pr.Iz, rr.Iz, 1e-12, "m⁴")
    check("Polygon Rechteck: Schwerpunkt y", pr.yc, y0 + bb / 2, 1e-12, "m")
    check("Polygon Rechteck: Schwerpunkt z", pr.zc, z0 + hh / 2, 1e-12, "m")
    check("Polygon Rechteck (Uhrzeigersinn) gleich", S.polygon("R2", R[::-1]).Iy, rr.Iy, 1e-12, "m⁴")
    tw_ = 0.01
    H = [(y0 + tw_, z0 + tw_), (y0 + bb - tw_, z0 + tw_), (y0 + bb - tw_, z0 + hh - tw_),
         (y0 + tw_, z0 + hh - tw_)]
    ph = S.polygon("Kasten", R, [H])
    check("Polygon mit Loch: A", ph.A, bb * hh - (bb - 2 * tw_) * (hh - 2 * tw_), 1e-12, "m²")
    check("Polygon mit Loch: Iy", ph.Iy,
          (bb * hh ** 3 - (bb - 2 * tw_) * (hh - 2 * tw_) ** 3) / 12, 1e-12, "m⁴")
    r, tr = 0.1, 0.004
    n = 360
    aussen = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    innen = [((r - tr) * math.cos(2 * math.pi * i / n), (r - tr) * math.sin(2 * math.pi * i / n))
             for i in range(n)]
    ring = S.polygon("Ring", aussen, [innen])
    rm = r - tr / 2
    check("Ring: It nach Saint-Venant ≈ Bredt 2π rm³ t", ring.It, 2 * math.pi * rm ** 3 * tr, 0.01, "m⁴")
    check("Ring: A", ring.A, math.pi * (r ** 2 - (r - tr) ** 2), 2e-4, "m²")
    kreis = S.polygon("Kreis", aussen)
    check("Vollkreis: It = π r⁴/2 (Saint-Venant exakt)", kreis.It, math.pi * r ** 4 / 2, 2e-4, "m⁴")

    # --- frei: geschweisstes I aus drei Streifen = i_profile ohne Ausrundung
    h, b, tw, tf = 0.4, 0.2, 0.01, 0.016
    hw = h - 2 * tf
    kn = {1: (-b / 2, (h - tf) / 2), 2: (b / 2, (h - tf) / 2),
          3: (-b / 2, -(h - tf) / 2), 4: (b / 2, -(h - tf) / 2),
          5: (0, -hw / 2), 6: (0, hw / 2)}
    frei = S.build_free("I frei", knoten=kn, elemente=[(1, 2, tf), (3, 4, tf), (5, 6, tw)])
    ref = Section.i_profile("I", h, b, tw, tf, 0.0)
    check("frei (Streifen): A = I-Profil", frei.A, ref.A, 1e-12, "m²")
    check("frei (Streifen): Iy = I-Profil", frei.Iy, ref.Iy, 1e-10, "m⁴")
    check("frei (Streifen): Iz = I-Profil", frei.Iz, ref.Iz, 1e-10, "m⁴")
    check("frei (Streifen): It = I-Profil", frei.It, ref.It, 1e-10, "m⁴")
    check("frei: Schwerpunkt bleibt im Ursprung", abs(frei.yc) + abs(frei.zc), 0.0, 1e-9, "m")
    # --- frei: zwei IPE 200 uebereinander (Steiner)
    ipe = P.make_section("IPE 200")
    zwei = S.build_free("2 IPE", teile=[("IPE 200", 0, ipe.h / 2), ("IPE 200", 0, -ipe.h / 2)])
    check("frei (Teile): A = 2 A", zwei.A, 2 * ipe.A, 1e-12, "m²")
    check("frei (Teile): Iy = 2 (Iy + A (h/2)²)", zwei.Iy, 2 * (ipe.Iy + ipe.A * (ipe.h / 2) ** 2), 1e-10, "m⁴")
    # --- frei: Flaeche mit Loch = Kasten; Editorinhalt reist mit
    kn = {1: (0, 0), 2: (0.3, 0), 3: (0.3, 0.5), 4: (0, 0.5),
          5: (0.02, 0.02), 6: (0.28, 0.02), 7: (0.28, 0.48), 8: (0.02, 0.48)}
    kasten = S.build_free("Kasten", knoten=kn,
                          flaechen=[{"knoten": [1, 2, 3, 4]}, {"knoten": [5, 6, 7, 8], "loch": True}])
    check("frei (Flaeche mit Loch): A", kasten.A, 0.3 * 0.5 - 0.26 * 0.46, 1e-12, "m²")
    check("frei (Flaeche mit Loch): Iy", kasten.Iy, (0.3 * 0.5 ** 3 - 0.26 * 0.46 ** 3) / 12, 1e-12, "m⁴")
    inhalt = S.editor_inhalt(kasten)
    wieder = S.build_free("Kasten 2", inhalt["teile"], inhalt["knoten"], inhalt["elemente"], inhalt["flaechen"])
    check("Editorinhalt: erneut gebaut gleich", wieder.Iy, kasten.Iy, 1e-12, "m⁴")
    for fehler, kw in (("Loch ohne Flaeche", dict(knoten=kn, flaechen=[{"knoten": [5, 6, 7, 8], "loch": True}])),
                       ("unbekannter Knoten", dict(knoten=kn, elemente=[(1, 99, 0.01)])),
                       ("nichts", dict())):
        try:
            S.build_free("x", **kw)
            check(f"frei: Fehler „{fehler}“ wird gemeldet", 0.0, 1.0, 0)
        except ValueError:
            check(f"frei: Fehler „{fehler}“ wird gemeldet", 1.0, 1.0, 0)
    # --- Umriss: Schwerpunkt der gezeichneten Kontur liegt im Ursprung
    for name, sec, tol in (("I", ref, 1e-9), ("T", t, 1e-9), ("Rechteck", rr, 1e-9),
                           ("U (UPE 200, ohne Ausrundung)", P.make_section("UPE 200"), 0.04),
                           ("L 100x100x10", P.make_section("L 100x100x10"), 0.02),
                           ("RHS 200x100x8", P.make_section("RHS 200x100x8"), 0.05),
                           ("frei (Streifen)", frei, 1e-9), ("2 IPE (ohne Ausrundung)", zwei, 0.05),
                           ("Kasten", kasten, 1e-9)):
        A_ = Sy_ = Sz_ = 0.0
        for Pp, loch in S.umriss(sec):
            a, sy, sz, *_ = S._polygon_momente(Pp)
            f = -1.0 if loch else 1.0
            A_, Sy_, Sz_ = A_ + f * a, Sy_ + f * sy, Sz_ + f * sz
        check(f"Umriss {name}: Flaeche ≈ A", A_, sec.A, tol if tol > 1e-9 else 1e-9, "m²")
        check(f"Umriss {name}: Schwerpunkt im Ursprung", abs(Sy_ / A_) + abs(Sz_ / A_), 0.0,
              1e-9 if tol <= 1e-9 else 1.0, "m")
        if tol > 1e-9:
            RESULTS[-1] = (RESULTS[-1][0], abs(Sy_ / A_) + abs(Sz_ / A_) < tol * max(sec.h, sec.b))
    check("Umriss CHS: Aussen und Loch", len(S.umriss(P.make_section("CHS 168.3x5"))), 2, 0)


def main():
    for t in (test_datenbank, test_katalogwerte, test_rohre, test_winkel_hauptachsen,
              test_zusammengesetzt, test_querschnitt_im_modell, test_frei):
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
