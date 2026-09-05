"""
Messen und Bemassen: Abstand, Winkel, Polygonflaeche, Kreis durch drei
Punkte, Masstexte, Versatzrichtung und die Geometrie der Masse (Strecken,
Texte) - alles gegen geschlossene Werte; Persistenz im Modell.
Aufruf:  python -m tests.test_bemassung
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model  # noqa: E402
from statik3d import bemassung as bm  # noqa: E402
from statik3d.bemassung import Bemassung, BemassungEinstellung  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")
    return ok


def close(name, got, want, tol=1e-9, unit=""):
    got, want = float(got), float(want)
    err = abs(got - want) / (abs(want) if abs(want) > 1e-12 else 1.0)
    return check(name, err <= tol, f"num={got:.6g} ana={want:.6g} {unit}")


def test_formeln():
    d = bm.abstand([0, 0, 0], [3, 4, 0])
    close("Abstand 3-4-5", d["L"], 5.0)
    check("Δx, Δy, Δz, Ebene", d["dx"] == 3.0 and d["dy"] == 4.0 and d["dz"] == 0.0 and abs(d["L_xy"] - 5.0) < 1e-12)
    close("Winkel 90°", bm.winkel([1, 0, 0], [0, 0, 0], [0, 1, 0]), 90.0)
    close("Winkel 45°", bm.winkel([1, 0, 0], [0, 0, 0], [1, 1, 0]), 45.0)
    close("Winkel 180°", bm.winkel([1, 0, 0], [0, 0, 0], [-1, 0, 0]), 180.0)
    close("Winkel im Raum 60° (Würfeldiagonalen)", bm.winkel([1, 1, 0], [0, 0, 0], [1, 0, 1]), 60.0)
    A, S = bm.polygonflaeche([[0, 0, 0], [2, 0, 0], [2, 3, 0], [0, 3, 0]])
    close("Rechteck 2×3: A = 6", A, 6.0)
    check("Rechteck: Schwerpunkt (1, 1.5, 0)", np.allclose(S, [1, 1.5, 0]))
    A, S = bm.polygonflaeche([[0, 0, 0], [4, 0, 0], [0, 3, 0]])
    close("Dreieck 4×3/2 = 6", A, 6.0)
    check("Dreieck: Schwerpunkt (4/3, 1, 0)", np.allclose(S, [4 / 3, 1, 0]))
    A, _ = bm.polygonflaeche([[0, 0, 0], [0, 2, 0], [0, 2, 3], [0, 0, 3]])
    close("Polygon in der y-z-Ebene: 6", A, 6.0)
    r, z = bm.kreis_aus_drei([2, 0, 0], [0, 2, 0], [-2, 0, 0])
    close("Kreis durch drei Punkte: r = 2", r, 2.0)
    check("… Mittelpunkt im Ursprung", np.allclose(z, [0, 0, 0], atol=1e-12))
    r, z = bm.kreis_aus_drei([1, 0, 5], [0, 1, 5], [-1, 0, 5])
    check("Kreis auf z = 5: r = 1, Mittelpunkt (0,0,5)", abs(r - 1.0) < 1e-12 and np.allclose(z, [0, 0, 5]))
    try:
        bm.kreis_aus_drei([0, 0, 0], [1, 0, 0], [2, 0, 0])
        check("kollineare Punkte → ValueError", False)
    except ValueError:
        check("kollineare Punkte → ValueError", True)
    close("Radius aus Mittelpunkt und Punkt", bm.radius([[0, 0, 0], [0, 3, 4]]), 5.0)
    check("Maßtext m / cm / mm", bm.masstext(2.5) == "2.500 m" and bm.masstext(2.5, "cm", 1) == "250.0 cm"
          and bm.masstext(2.5, "mm", 0) == "2500 mm", bm.masstext(2.5, "mm", 0))
    check("Höhenkote mit Vorzeichen", bm.masstext(0.0, vorzeichen=True) == "±0.000 m"
          and bm.masstext(1.25, vorzeichen=True) == "+1.250 m" and bm.masstext(-0.5, vorzeichen=True) == "−0.500 m")
    d = bm.versatzrichtung([0, 0, 0], [4, 0, 0], blick=[0, -1, 0])
    check("Versatz senkrecht zur Strecke und zum Blick: nach oben (z)", np.allclose(d, [0, 0, 1]), str(d))
    d = bm.versatzrichtung([0, 0, 0], [0, 0, 4], blick=[0, -1, 0])
    check("senkrechte Strecke, Blick −y: Versatz nach +x", np.allclose(d, [1, 0, 0]), str(d))
    d = bm.versatzrichtung([0, 0, 0], [4, 0, 0], blick=[1, 0, 0])
    check("Blick längs der Strecke: Rückfall auf eine Senkrechte", abs(float(d @ [1, 0, 0])) < 1e-12 and abs(np.linalg.norm(d) - 1) < 1e-12)
    t = bm.messung_text("abstand", [[0, 0, 0], [3, 4, 0]])
    check("Messtext Abstand", t.startswith("Abstand 5.000 m") and "Δx 3.000 m" in t, t)
    check("Messtext Winkel", bm.messung_text("winkel", [[1, 0, 0], [0, 0, 0], [0, 1, 0]]).startswith("Winkel 90.00°"))
    check("Messtext Koordinaten", bm.messung_text("koordinaten", [[1, 2, 3]]) == "Punkt x = 1.000 m, y = 2.000 m, z = 3.000 m")
    check("Messtext Fläche", bm.messung_text("flaeche", [[0, 0, 0], [2, 0, 0], [2, 3, 0], [0, 3, 0]]).startswith("Fläche 6.0000 m²"))


def test_geometrie():
    e = BemassungEinstellung()
    g = bm.geometrie(Bemassung("M1", "linear", [[0, 0, 0], [4, 0, 0]]), e, groesse=10.0, blick=[0, -1, 0])
    check("Linearmaß: 5 Strecken (2 Hilfslinien, Maßlinie, 2 Schrägstriche), 1 Text", len(g["linien"]) == 5 and len(g["texte"]) == 1)
    v = 0.08 * 10.0
    ml = g["linien"][2]
    close("Maßlinie in Versatz 8 % der Modellgröße über der Strecke", ml[0][2], v)
    close("Maßlinie überragt die Hilfslinien beidseitig um 0,1·s", float(np.linalg.norm(ml[1] - ml[0])), 4.0 + 0.2 * 0.25 * v)
    pos, text = g["texte"][0]
    check("Text 4.000 m über der Mitte", text == "4.000 m" and abs(pos[0] - 2.0) < 1e-12 and pos[2] > v, str((pos, text)))
    g = bm.geometrie(Bemassung("M2", "linear", [[0, 0, 0], [4, 0, 0]], versatz=1.0, richtung=[0, 0, -1], text="L"), e, 10.0)
    check("Versatz und Richtung aus dem Maß, Text übersteuert", abs(g["linien"][2][0][2] + 1.0) < 1e-12 and g["texte"][0][1] == "L")
    g = bm.geometrie(Bemassung("K", "kette", [[0, 0, 0], [2, 0, 0], [5, 0, 0], [6, 0, 0]]), e, 10.0, [0, -1, 0])
    check("Maßkette: 3 Glieder je 5 Strecken + Gesamtmaß, 4 Texte", len(g["linien"]) == 20 and len(g["texte"]) == 4
          and [t for _, t in g["texte"]] == ["2.000 m", "3.000 m", "1.000 m", "6.000 m"], str([t for _, t in g["texte"]]))
    g = bm.geometrie(Bemassung("H", "hoehenkote", [[1, 2, 3.5]]), e, 10.0, [0, -1, 0])
    check("Höhenkote: Dreieck (3) + Fahne (1), Text +3.500 m", len(g["linien"]) == 4 and g["texte"][0][1] == "+3.500 m", str(g["texte"]))
    e2 = BemassungEinstellung(hoehen_bezug=3.5, einheit="cm", nachkomma=1)
    g = bm.geometrie(Bemassung("H", "hoehenkote", [[1, 2, 3.5]]), e2, 10.0)
    check("Höhenbezug und Einheit aus den Einstellungen: ±0.0 cm", g["texte"][0][1] == "±0.0 cm", g["texte"][0][1])
    g = bm.geometrie(Bemassung("W", "winkel", [[1, 0, 0], [0, 0, 0], [0, 1, 0]]), e, 10.0)
    check("Winkelmaß: Bogen aus 16 Strecken + 2 Schenkel, Text 90.0°", len(g["linien"]) == 18 and g["texte"][0][1] == "90.0°", str(g["texte"]))
    bogen = [p for a, b in g["linien"][:16] for p in (a, b)]
    check("Bogen liegt auf dem Radius 0,1·Größe", all(abs(np.linalg.norm(p) - 1.0) < 1e-9 for p in bogen))
    g = bm.geometrie(Bemassung("R", "radius", [[0, 0, 0], [3, 4, 0]]), e, 10.0)
    check("Radius: Strahl + Mittelpunktkreuz, Text R 5.000 m", len(g["linien"]) == 3 and g["texte"][0][1] == "R 5.000 m")
    g = bm.geometrie(Bemassung("R3", "radius", [[2, 0, 0], [0, 2, 0], [-2, 0, 0]]), e, 10.0)
    check("Radius aus drei Punkten: R 2.000 m", g["texte"][0][1] == "R 2.000 m")
    g = bm.messung_geometrie("flaeche", [[0, 0, 0], [2, 0, 0], [2, 3, 0], [0, 3, 0]], e, 10.0)
    check("Messung Fläche: Umring (4) und A = 6.0000 m² im Schwerpunkt", len(g["linien"]) == 4 and g["texte"][0][1] == "A = 6.0000 m²"
          and np.allclose(g["texte"][0][0], [1, 1.5, 0]))
    g = bm.messung_geometrie("koordinaten", [[1, 2, 3]], e, 10.0)
    check("Messung Koordinaten: Kreuz aus 3 Strecken", len(g["linien"]) == 3 and "x = 1.000 m" in g["texte"][0][1])
    check("Bezugstexte", Bemassung("M", "linear", [[0, 0, 0], [4, 0, 0]]).bezug() == "Linearmaß 4.000 m"
          and Bemassung("K", "kette", [[0, 0, 0], [2, 0, 0], [6, 0, 0]]).bezug() == "Maßkette 6.000 m (2 Glieder)"
          and Bemassung("H", "hoehenkote", [[0, 0, 2]]).bezug() == "Höhenkote z = 2.000 m"
          and Bemassung("W", "winkel", [[1, 0, 0], [0, 0, 0], [0, 1, 0]]).bezug() == "Winkelmaß 90.0°")


def test_modell():
    m = Model()
    check("Vorgabe-Einstellungen bei Bedarf", m.bemassung_einstellungen().einheit == "m" and m.bemassung_einstellung is not None)
    m.bemassungen["M1"] = Bemassung("M1", "linear", [[0, 0, 0], [4, 0, 0]], richtung=[0, 0, 1])
    m.bemassung_einstellung.einheit = "cm"
    m2 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("Bemaßungen und Einstellungen werden gespeichert und geladen",
          "M1" in m2.bemassungen and m2.bemassungen["M1"].richtung == [0, 0, 1] and m2.bemassung_einstellung.einheit == "cm")
    m3 = Model.from_dict(json.loads(json.dumps(Model().to_dict())))
    check("Modell ohne Bemaßungen lädt ohne Einstellungen", not m3.bemassungen and m3.bemassung_einstellung is None)
    c = m.copy()
    check("Kopie trägt die Bemaßungen", "M1" in c.bemassungen)


def main():
    for f in (test_formeln, test_geometrie, test_modell):
        print(f"\n--- {f.__name__} ---")
        try:
            f()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
