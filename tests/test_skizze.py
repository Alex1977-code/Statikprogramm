"""Skizzen (16.09.2026): Linien, Kreise, Boegen, Bemassungen, Text - Geometrie,
Fang, Treffer, Masstext und SVG ohne Oberflaeche.

Aufruf:  python -m tests.test_skizze
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import skizze as sk   # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:66s} {detail}")
    return ok


def test_geometrie():
    s = sk.neu(200, 100, massstab=10.0, einheit="mm", raster=5.0)
    check("neues Blatt: Masse, Massstab, Einheit, leer",
          s["breite"] == 200 and s["hoehe"] == 100 and s["massstab"] == 10 and s["einheit"] == "mm"
          and s["elemente"] == [] and s["bild"] is None)
    check("pruefen ergaenzt Fehlendes und wirft Unbrauchbares",
          sk.pruefen({"elemente": [{"art": "linie", "p1": [0, 0], "p2": [1, 1]}, {"x": 1}, "unsinn"],
                      "einheit": "zoll"})["einheit"] == "mm"
          and len(sk.pruefen({"elemente": [{"art": "linie", "p1": [0, 0], "p2": [1, 1]}, {"x": 1}]})["elemente"]) == 1)
    check("Winkel gegen den Uhrzeigersinn auf dem Blatt (y nach unten)",
          abs(sk.winkel((0, 0), (1, 0))) < 1e-9 and abs(sk.winkel((0, 0), (0, -1)) - 90) < 1e-9
          and abs(sk.winkel((0, 0), (-1, 0)) - 180) < 1e-9 and abs(sk.winkel((0, 0), (0, 1)) - 270) < 1e-9)
    p = sk.punkt_auf_kreis((10, 10), 5, 90)
    check("Punkt auf dem Kreis bei 90 Grad liegt oben", abs(p[0] - 10) < 1e-9 and abs(p[1] - 5) < 1e-9, str(p))
    b = sk.bogen_durch_drei_punkte((0, 0), (10, 0), (5, -5))
    check("Bogen durch drei Punkte: Halbkreis oben, Mitte (5,0), r = 5, laeuft von rechts ueber oben nach links",
          b is not None and abs(b[0][0] - 5) < 1e-9 and abs(b[0][1]) < 1e-9 and abs(b[1] - 5) < 1e-9
          and abs(b[2] - 0) < 1e-9 and abs(b[3] - 180) < 1e-9, str(b))
    b2 = sk.bogen_durch_drei_punkte((0, 0), (10, 0), (5, 5))
    check("… derselbe Bogen unten laeuft von links nach rechts (180 -> 360)",
          b2 is not None and abs(b2[2] - 180) < 1e-9 and abs(b2[3] - 0) < 1e-9, str(b2))
    check("drei Punkte auf einer Geraden geben keinen Bogen", sk.bogen_durch_drei_punkte((0, 0), (1, 1), (2, 2)) is None)
    check("Bogenspanne: 350 -> 10 sind 20 Grad, gleicher Winkel ist der Vollkreis",
          abs(sk.bogen_spanne(350, 10) - 20) < 1e-9 and abs(sk.bogen_spanne(30, 30) - 360) < 1e-9)
    el = {"art": "bogen", "mitte": [0, 0], "r": 1, "von": 350, "bis": 10}
    check("auf_bogen: 0 Grad liegt drin, 180 nicht", sk.auf_bogen(el, 0) and not sk.auf_bogen(el, 180))
    d1, d2, n = sk.bemassungslinie({"art": "bemassung", "p1": [0, 0], "p2": [10, 0], "abstand": 8})
    check("Masslinie liegt 8 mm links der Richtung (oben auf dem Blatt)",
          abs(d1[1] + 8) < 1e-9 and abs(d2[1] + 8) < 1e-9 and abs(d1[0]) < 1e-9 and abs(d2[0] - 10) < 1e-9
          and abs(n[1] + 1) < 1e-9, f"{d1} {d2} {n}")


def test_mass_und_fang():
    check("Masstext: mm ganz, cm und m mit Komma und ohne Nullen",
          sk.masstext(125.4, "mm") == "125" and sk.masstext(125.0, "cm") == "12,5"
          and sk.masstext(1250.0, "m") == "1,25" and sk.masstext(1000.0, "m") == "1")
    s = sk.neu(297, 210, massstab=10.0, einheit="cm")
    el = {"art": "bemassung", "p1": [10, 50], "p2": [40, 50], "abstand": 6}
    check("Bemassungstext misst im Massstab: 30 mm Blatt x 10 = 300 mm = 30 cm",
          sk.bemassung_text(el, s) == "30", sk.bemassung_text(el, s))
    el2 = dict(el, text="R 15")
    check("eigener Text geht vor", sk.bemassung_text(el2, s) == "R 15")
    s["elemente"] = [{"art": "linie", "p1": [10, 10], "p2": [50, 10]},
                     {"art": "kreis", "mitte": [100, 100], "r": 20},
                     {"art": "bogen", "mitte": [200, 100], "r": 10, "von": 0, "bis": 90},
                     el, {"art": "text", "p": [150, 150], "text": "Blech t = 20", "groesse": 4}]
    fp = sk.fangpunkte(s)
    arten = {a for _x, _y, a in fp}
    check("Fangpunkte: Enden, Mitte, Mittelpunkte, Quadranten, Masspunkte, Text",
          {"Ende", "Mitte", "Mittelpunkt", "Quadrant", "Masspunkt", "Text"} <= arten
          and any(abs(x - 30) < 1e-9 and abs(y - 10) < 1e-9 and a == "Mitte" for x, y, a in fp)
          and any(abs(x - 120) < 1e-9 and abs(y - 100) < 1e-9 and a == "Quadrant" for x, y, a in fp), str(sorted(arten)))
    f = sk.fangen(s, (49.2, 10.9), 2.0)
    check("fangen rastet am Linienende ein, ausserhalb des Umkreises nicht",
          f is not None and f[0] == 50 and f[1] == 10 and f[2] == "Ende" and sk.fangen(s, (70, 70), 2.0) is None, str(f))
    check("rastern rundet auf das Raster, 0 laesst alles", sk.rastern((12.4, 17.6), 5) == (10.0, 20.0)
          and sk.rastern((12.4, 17.6), 0) == (12.4, 17.6))
    check("element_bei trifft Linie, Kreisrand, Bogen (nicht den fehlenden Teil), Masslinie, Text",
          sk.element_bei(s, (30, 10.8)) == 0 and sk.element_bei(s, (120.5, 100)) == 1
          and sk.element_bei(s, (207, 93)) == 2 and sk.element_bei(s, (190, 100)) == -1
          and sk.element_bei(s, (25, 44)) == 3 and sk.element_bei(s, (160, 148)) == 4
          and sk.element_bei(s, (5, 100)) == -1,
          f"{sk.element_bei(s, (30, 10.8))} {sk.element_bei(s, (120.5, 100))} {sk.element_bei(s, (207, 93))} "
          f"{sk.element_bei(s, (190, 100))} {sk.element_bei(s, (25, 44))} {sk.element_bei(s, (160, 148))}")
    g = sk.grenzen(s)
    check("grenzen umfassen den Kreis ganz", g is not None and g[0] <= 10 and g[2] >= 210 and g[1] <= 80 and g[3] >= 150, str(g))
    check("grenzen einer leeren Skizze sind None", sk.grenzen(sk.neu()) is None)
    check("beschreibung zaehlt die Arten", sk.beschreibung(s) == "1 Linien, 1 Kreise, 1 Bögen, 1 Maße, 1 Texte", sk.beschreibung(s))


def test_svg():
    s = sk.neu(100, 50, massstab=1.0, einheit="mm", raster=10)
    s["elemente"] = [{"art": "linie", "p1": [10, 10], "p2": [60, 10]},
                     {"art": "kreis", "mitte": [80, 30], "r": 8},
                     {"art": "bogen", "mitte": [30, 30], "r": 10, "von": 0, "bis": 180},
                     {"art": "bemassung", "p1": [10, 10], "p2": [60, 10], "abstand": 6},
                     {"art": "text", "p": [10, 45], "text": "A < B & C", "groesse": 3}]
    t = sk.svg(s)
    check("SVG: Blatt als viewBox in mm, Anzeige in Bildpunkten",
          'viewBox="0 0 100 50"' in t and 'width="377.95"' in t and t.startswith("<svg") and t.endswith("</svg>"))
    check("SVG: Linie, Kreis und Bogen als line, circle und path mit Bogenbefehl",
          '<line x1="10" y1="10" x2="60" y2="10"' in t and '<circle cx="80" cy="30" r="8"' in t
          and 'A 10 10 0 0 0 20 30' in t, t[:300])
    check("SVG: Bemassung mit Masslinie bei y = 4, zwei Pfeilen und der Masszahl 50",
          'y1="4" x2="60" y2="4"' in t and t.count("<polygon") == 2 and ">50</text>" in t)
    check("SVG: Sonderzeichen im Text sind maskiert", "A &lt; B &amp; C" in t)
    check("SVG ohne Raster hat kein Rasternetz, mit Raster schon",
          "#dfe3e8" not in t and "#dfe3e8" in sk.svg(s, raster=True))
    th = sk.svg(s, hervor=1)
    check("Hervorhebung faerbt genau das gewaehlte Element orange", th.count("#ff8800") == 1 and 'r="8" fill="none" stroke="#ff8800"' in th)
    s["bild"] = {"x": 0, "y": 0, "breite": 100, "hoehe": 50}
    tb = sk.svg(s, bild_png_base64="QUJD")
    check("Hintergrundbild als image mit Datenadresse", '<image x="0" y="0" width="100" height="50"' in tb and "base64,QUJD" in tb)
    check("ohne Bilddaten kein image-Element", "<image" not in sk.svg(s))
    # Bemassung schraeg: Text wird lesbar gedreht (nie auf dem Kopf)
    s2 = sk.neu()
    s2["elemente"] = [{"art": "bemassung", "p1": [50, 50], "p2": [10, 10], "abstand": 5}]
    t2 = sk.svg(s2)
    m = [x for x in t2.split("rotate(")[1:]]
    grad = float(m[0].split(" ")[0]) if m else 999
    check("Masszahl einer schraegen Bemassung steht lesbar (Drehung zwischen -90 und 90 Grad)",
          -90 < grad <= 90, str(grad))


def main():
    for t in (test_geometrie, test_mass_und_fang, test_svg):
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
