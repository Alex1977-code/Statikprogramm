"""Querschnitte aus Massen wie in RFEM und aus einer gezeichneten Kontur
(16.09.2026): Wpl exakt am Polygon, Parameterprofile gegen geschlossene
Formeln, Skizze -> Querschnitt (Linien, Boegen, Kreise, Loecher, Massstab,
Blattachse y nach unten), offene Kontur wird benannt.

Aufruf:  python -m tests.test_kontur
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import sections as S, skizze as sk                  # noqa: E402
from statik3d.model import Section                               # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:72s} {detail}")
    return ok


def nahe(name, ist, soll, tol, einheit=""):
    ist, soll = float(ist), float(soll)
    abw = abs(ist - soll) / (abs(soll) if abs(soll) > 1e-14 else 1.0)
    return check(name, abw <= tol, f"ist {ist:.6g} soll {soll:.6g} ({abw * 100:.3f} %) {einheit}")


def test_wpl_polygon():
    b, h = 0.2, 0.3
    r = S.polygon("R", [(0, 0), (b, 0), (b, h), (0, h)])
    nahe("Rechteck: Wpl,y = b h²/4 aus der plastischen Nulllinie", r.Wpl_y, b * h ** 2 / 4, 1e-9, "m³")
    nahe("Rechteck: Wpl,z = h b²/4", r.Wpl_z, h * b ** 2 / 4, 1e-9, "m³")
    # Doppel-T als Polygon gegen die Katalogformel (r = 0)
    hh, bb, tw, tf = 0.3, 0.15, 0.008, 0.012
    i = Section.i_profile("I", hh, bb, tw, tf, fabrication="welded")
    P = [(-bb / 2, 0), (bb / 2, 0), (bb / 2, tf), (tw / 2, tf), (tw / 2, hh - tf), (bb / 2, hh - tf),
         (bb / 2, hh), (-bb / 2, hh), (-bb / 2, hh - tf), (-tw / 2, hh - tf), (-tw / 2, tf), (-bb / 2, tf)]
    pg = S.polygon("I-Polygon", P)
    nahe("Doppel-T: Wpl,y Polygon = Formel", pg.Wpl_y, i.Wpl_y, 1e-9, "m³")
    nahe("Doppel-T: Wpl,z Polygon = Formel", pg.Wpl_z, i.Wpl_z, 1e-9, "m³")
    # Kasten mit Loch: Wpl,y = (b h² - bi hi²)/4
    bi, hi = b - 0.02, h - 0.02
    k = S.polygon("Kasten", [(0, 0), (b, 0), (b, h), (0, h)],
                  [[(0.01, 0.01), (b - 0.01, 0.01), (b - 0.01, h - 0.01), (0.01, h - 0.01)]])
    nahe("Kasten mit Loch: Wpl,y = (b h² − bi hi²)/4", k.Wpl_y, (b * h ** 2 - bi * hi ** 2) / 4, 1e-9, "m³")
    # gedrehtes Rechteck: Hauptwerte und Wpl wie ungedreht, Wel in den Hauptachsen
    a = math.radians(30)
    Q = [(y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a)) for y, z in
         [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]]
    g = S.polygon("gedreht", Q)
    nahe("gedrehtes Rechteck: Iy = Hauptwert b h³/12", g.Iy, b * h ** 3 / 12, 1e-9, "m⁴")
    nahe("gedrehtes Rechteck: Wel,y = b h²/6 (Randabstand in Hauptachsen)", g.Wel_y, b * h ** 2 / 6, 1e-9, "m³")
    nahe("gedrehtes Rechteck: Wpl,y = b h²/4", g.Wpl_y, b * h ** 2 / 4, 1e-9, "m³")


def test_parameterprofile():
    h, bo, to, bu, tu, tw = 0.4, 0.2, 0.016, 0.3, 0.02, 0.01
    s = S.i_unsym("I2", h, bo, to, bu, tu, tw)
    hw = h - to - tu
    A = bo * to + bu * tu + hw * tw
    nahe("Doppel-T unsymmetrisch: A", s.A, A, 1e-12, "m²")
    zc = (bu * tu * tu / 2 + hw * tw * (tu + hw / 2) + bo * to * (h - to / 2)) / A
    nahe("Doppel-T unsymmetrisch: Schwerpunkt", s.zc, zc, 1e-9, "m")
    Iy = (bu * tu ** 3 / 12 + bu * tu * (zc - tu / 2) ** 2 + tw * hw ** 3 / 12 + hw * tw * (tu + hw / 2 - zc) ** 2
          + bo * to ** 3 / 12 + bo * to * (h - to / 2 - zc) ** 2)
    nahe("Doppel-T unsymmetrisch: Iy nach Steiner", s.Iy, Iy, 1e-9, "m⁴")
    nahe("Doppel-T unsymmetrisch: It = Σ b t³/3", s.It, (bo * to ** 3 + bu * tu ** 3 + hw * tw ** 3) / 3, 1e-12, "m⁴")
    z = S.z_profil("Z", 0.2, 0.08, 0.006)
    nahe("Z: A = t (h + 2 (b − t))", z.A, 0.006 * (0.2 + 2 * (0.08 - 0.006)), 1e-12, "m²")
    check("Z: Hauptachsen gedreht (|alpha| <= 45°), Iy bleibt die Achse näher an y",
          0.05 < abs(z.alpha) <= math.pi / 4 and z.Iy > z.Iz, f"alpha {math.degrees(z.alpha):.1f}°")
    # das Deviationsmoment verschwindet in den Hauptachsen: nachgerechnet am Polygon
    P = np.asarray(z.parts[0]["polygon"], float) - [z.yc, z.zc]
    c, s_ = math.cos(z.alpha), math.sin(z.alpha)
    for R in (np.array([[c, s_], [-s_, c]]), np.array([[c, -s_], [s_, c]])):
        Q = P @ R.T
        _a, _sy, _sz, iyy, _izz, iyz = S._polygon_momente(Q)
        if abs(iyz) < 1e-12 * iyy:
            nahe("Z: in den Hauptachsen ist Iy der angegebene Hauptwert", iyy, z.Iy, 1e-9, "m⁴")
            break
    else:
        check("Z: eine Drehung um ±alpha bringt Iyz auf null", False)
    hu = S.hut("Hut", 0.1, 0.06, 0.02, 0.003)
    nahe("Hut: A", hu.A, 0.003 * ((0.06 + 2 * 0.003) + 2 * (0.1 - 0.003) + 2 * (0.02 - 0.003)), 1e-12, "m²")
    kr = S.kreuz("Kreuz", 0.2, 0.2, 0.012)
    nahe("Kreuz: A = t (h + b − t)", kr.A, 0.012 * (0.2 + 0.2 - 0.012), 1e-12, "m²")
    nahe("Kreuz: Iy = Iz", kr.Iy, kr.Iz, 1e-9, "m⁴")
    el = S.ellipse("El", 0.2, 0.1)
    nahe("Ellipse: A = π a b / 4", el.A, math.pi * 0.2 * 0.1 / 4, 1e-12, "m²")
    nahe("Ellipse: Iy = π a b³ / 64", el.Iy, math.pi * 0.2 * 0.1 ** 3 / 64, 1e-12, "m⁴")
    nahe("Ellipse: It = π a³ b³ / (16 (a² + b²))", el.It, math.pi * 0.1 ** 3 * 0.05 ** 3 / (0.1 ** 2 + 0.05 ** 2), 1e-12, "m⁴")
    hk = S.halbkreis("Hk", 0.2)
    nahe("Halbkreis: A = π r²/2", hk.A, math.pi * 0.1 ** 2 / 2, 1e-12, "m²")
    nahe("Halbkreis: Schwerpunkt 4r/3π (Polygon mit 64 Ecken)", hk.zc, 4 * 0.1 / (3 * math.pi), 1e-3, "m")
    tr = S.trapez("Tr", 0.1, 0.2, 0.15)
    nahe("Trapez: A = (bo + bu) h / 2", tr.A, (0.1 + 0.2) * 0.15 / 2, 1e-12, "m²")
    nahe("Trapez: Schwerpunkt h (2 bo + bu) / (3 (bo + bu))", tr.zc, 0.15 * (2 * 0.1 + 0.2) / (3 * 0.3), 1e-12, "m")
    dr = S.dreieck("Dr", 0.2, 0.15)
    nahe("Dreieck: Iy = b h³/36", dr.Iy, 0.2 * 0.15 ** 3 / 36, 1e-12, "m⁴")
    sk6 = S.sechskant("6kt", 0.1)
    nahe("Sechskant: A = √3/2 sw²", sk6.A, math.sqrt(3) / 2 * 0.1 ** 2, 1e-12, "m²")
    nahe("Sechskant: Iy = Iz", sk6.Iy, sk6.Iz, 1e-9, "m⁴")
    for art in ("Doppel-T unsymmetrisch", "Z", "Hut", "Kreuz", "Ellipse", "Halbkreis", "Trapez", "Dreieck", "Sechskant"):
        try:
            from statik3d.gui.profilmaske import PARAMETER, parameterprofil
        except Exception as ex:      # noqa: BLE001 - ohne Qt bleibt die Maske aussen vor
            check("Maske: PARAMETER importierbar (Qt)", False, str(ex))
            break
        eintrag = next(e for e in PARAMETER if e[0] == art)
        sec = parameterprofil(art, eintrag[2])
        check(f"Maske: „{art}“ mit den Vorgaben rechenbar, A > 0, Wpl ≥ Wel", sec.A > 0 and sec.Wpl_y >= sec.Wel_y * 0.999,
              f"A {sec.A * 1e4:.2f} cm²")


def _linie(a, b):
    return {"art": "linie", "p1": list(a), "p2": list(b)}


def test_kontur_aus_skizze():
    s = sk.neu(400.0, 400.0, 1.0, "mm", 10.0)
    # Rechteck 200 x 100 mm, unten links bei (50, 250) auf dem Blatt (y nach unten)
    s["elemente"] = [_linie((50, 250), (250, 250)), _linie((250, 250), (250, 150)),
                     _linie((250, 150), (50, 150)), _linie((50, 150), (50, 250))]
    sec = S.aus_skizze("R", s)
    nahe("Rechteck aus vier Linien: A = 0,02 m²", sec.A, 0.02, 1e-12, "m²")
    nahe("… Iy = b h³/12 (Hauptachse y, h = 100 mm)", sec.Iy, 0.2 * 0.1 ** 3 / 12, 1e-9, "m⁴")
    nahe("… Schwerpunkt z = −200 mm (Blatt y = 200 nach unten wird z nach oben)", sec.zc, -0.200, 1e-9, "m")
    nahe("… Wpl,y = b h²/4", sec.Wpl_y, 0.2 * 0.1 ** 2 / 4, 1e-9, "m³")
    check("… die Skizze reist mit dem Querschnitt", S.skizze_inhalt(sec) is not None and len(S.skizze_inhalt(sec)["elemente"]) == 4)
    # Kreis mit Loch (Rohr) im Massstab 1 : 2 (1 Blatt-mm = 2 mm)
    s2 = sk.neu(300.0, 300.0, 2.0, "mm", 5.0)
    s2["elemente"] = [{"art": "kreis", "mitte": [150, 150], "r": 50}, {"art": "kreis", "mitte": [150, 150], "r": 40}]
    rohr = S.aus_skizze("Rohr", s2)
    nahe("zwei Kreise = Rohr: A = π (R² − r²), Maßstab 2 (R = 100, r = 80 mm)", rohr.A, math.pi * (0.1 ** 2 - 0.08 ** 2), 2e-3, "m²")
    nahe("… Iy = π (R⁴ − r⁴)/4", rohr.Iy, math.pi * (0.1 ** 4 - 0.08 ** 4) / 4, 4e-3, "m⁴")
    # Kontur mit Boegen: Rechteck 100 x 60 mit zwei Halbkreisen (Langloch-Form) - Flaeche geschlossen
    r, L = 30.0, 100.0
    s3 = sk.neu(300.0, 300.0, 1.0, "mm", 5.0)
    # Winkel zaehlen gegen den Uhrzeigersinn, wie man sie auf dem Blatt sieht (Blattachse y nach
    # unten): der rechte Halbkreis laeuft von 270° (unten) ueber 0° (rechts) nach 90° (oben)
    s3["elemente"] = [_linie((100, 100), (200, 100)),
                      {"art": "bogen", "mitte": [200, 130], "r": r, "von": 270.0, "bis": 90.0},
                      _linie((200, 160), (100, 160)),
                      {"art": "bogen", "mitte": [100, 130], "r": r, "von": 90.0, "bis": 270.0}]
    lang = S.aus_skizze("Langloch", s3)
    soll = (L * 2 * r + math.pi * r ** 2) * 1e-6
    nahe("Kontur mit zwei Halbkreisbögen: A = 2 r L + π r² (Bogen alle 5° abgetastet)", lang.A, soll, 2e-3, "m²")
    # nach innen gewoelbte Boegen (Knochenform) sind ebenso eine geschlossene Kontur - kleiner
    s3["elemente"][1]["von"], s3["elemente"][1]["bis"] = 90.0, 270.0
    s3["elemente"][3]["von"], s3["elemente"][3]["bis"] = 270.0, 90.0
    nahe("… nach innen gewölbt: A = 2 r L − π r²", S.aus_skizze("Knochen", s3).A, (L * 2 * r - math.pi * r ** 2) * 1e-6, 2e-3, "m²")
    # offene Kontur: der Fehler nennt die Enden
    s4 = sk.neu()
    s4["elemente"] = [_linie((0, 0), (100, 0)), _linie((100, 0), (100, 50)), _linie((100, 50), (0, 50))]
    try:
        S.aus_skizze("offen", s4)
        check("offene Kontur wird abgewiesen", False)
    except ValueError as ex:
        check("offene Kontur wird abgewiesen und nennt die offenen Enden", "nicht geschlossen" in str(ex) and "(0.0, 0.0)" in str(ex), str(ex)[:120])
    # Loch in einem Loch ist wieder Material: Rahmen + Insel
    s5 = sk.neu(400.0, 400.0, 1.0, "mm", 10.0)
    s5["elemente"] = [_linie((0, 0), (200, 0)), _linie((200, 0), (200, 200)), _linie((200, 200), (0, 200)), _linie((0, 200), (0, 0)),
                      _linie((50, 50), (150, 50)), _linie((150, 50), (150, 150)), _linie((150, 150), (50, 150)), _linie((50, 150), (50, 50)),
                      _linie((80, 80), (120, 80)), _linie((120, 80), (120, 120)), _linie((120, 120), (80, 120)), _linie((80, 120), (80, 80))]
    insel = S.aus_skizze("Insel", s5)
    nahe("Rahmen mit Loch und Insel darin: A = 200² − 100² + 40²", insel.A, (200 ** 2 - 100 ** 2 + 40 ** 2) * 1e-6, 1e-9, "m²")
    # Umriss zum Zeichnen: Aussen und Loch
    um = S.umriss(rohr)
    check("Umriss des gezeichneten Rohrs: Außen und Loch", len(um) == 2 and sum(1 for _p, loch in um if loch) == 1)


def main():
    for t in (test_wpl_polygon, test_parameterprofile, test_kontur_aus_skizze):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
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
    sys.exit(main())
