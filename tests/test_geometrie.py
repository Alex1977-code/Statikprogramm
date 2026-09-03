"""
Verifikation der Geometrie: Linienarten, Koordinatensysteme, Arbeitsebene, Fang.

Geprueft wird gegen geschlossene Loesungen - Bogenlaenge r*phi, Kreisumfang
2*pi*r, Ellipsenumfang nach Ramanujan, der Scheitel einer Parabel, der
NURBS-Viertelkreis mit dem Gewicht 1/sqrt(2) (Radius muss ueberall genau 1
sein) und die Umrechnung zwischen Koordinatensystemen.

Aufruf:  python -m tests.test_geometrie
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import geometry as G          # noqa: E402
from statik3d import ks as KS               # noqa: E402
from statik3d.model import Model, Material, Section   # noqa: E402

RESULTS = []


def check(name, num, ana, tol):
    err = abs(num - ana) / abs(ana) if ana else abs(num)
    ok = err <= tol
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:58s} num={num: .6e} ana={ana: .6e} "
          f"Abw={err * 100:7.4f}%")
    return ok


def ja(name, bedingung, info=""):
    ok = bool(bedingung)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:58s} {info}")
    return ok


# --------------------------------------------------------------------------
def test_polylinie():
    p = G.Polylinie([(0, 0, 0), (3, 0, 0), (3, 4, 0)])
    check("Polylinie: Länge = 3 + 4", p.laenge(), 7.0, 1e-12)
    ja("Polylinie: Stützpunkte bleiben erhalten",
       np.allclose(p.punkte(2)[1], (3, 0, 0)))
    fein = p.punkte(14)
    ja("Polylinie: feine Teilung liegt auf dem Zug", len(fein) == 15)
    s = np.linalg.norm(np.diff(fein, axis=0), axis=1)
    check("Polylinie: gleichmäßig geteilt", float(s.max()), 7.0 / 14, 1e-9)
    ja("Polylinie: ein Punkt ist zu wenig",
       _wirft(lambda: G.Polylinie([(0, 0, 0)]).punkte()))


def test_bogen():
    # Halbkreis r = 2 durch drei Punkte
    b = G.Bogen.aus_drei_punkten((2, 0, 0), (0, 2, 0), (-2, 0, 0))
    check("Bogen durch 3 Punkte: Radius", b.radius, 2.0, 1e-12)
    check("Bogen durch 3 Punkte: Öffnungswinkel", math.degrees(b.winkel), 180.0, 1e-12)
    check("Bogen durch 3 Punkte: Länge = r·phi", b.laenge(), 2.0 * math.pi, 1e-12)
    P = b.punkte(12)
    ja("Bogen: alle Punkte auf dem Kreis",
       np.allclose(np.linalg.norm(P - b.mitte, axis=1), 2.0))
    ja("Bogen: läuft von p1 nach p3",
       np.allclose(P[0], (2, 0, 0)) and np.allclose(P[-1], (-2, 0, 0)))

    # Viertelkreis, andere Umlaufrichtung
    b2 = G.Bogen.aus_drei_punkten((1, 0, 0), (0, 1, 0), (-1, 0, 0))
    check("Halbkreis andersherum: Länge", b2.laenge(), math.pi, 1e-12)
    b3 = G.Bogen.aus_drei_punkten((1, 0, 0), (0, -1, 0), (-1, 0, 0))
    check("Bogen unten herum: Länge", b3.laenge(), math.pi, 1e-12)
    ja("Bogen unten herum: Zwischenpunkt wird getroffen",
       np.allclose(b3.punkte(2)[1], (0, -1, 0), atol=1e-12))

    # geneigte Ebene
    b4 = G.Bogen.aus_drei_punkten((1, 0, 0), (0, 0.6, 0.8), (-1, 0, 0))
    check("Bogen in geneigter Ebene: Länge", b4.laenge(), math.pi, 1e-12)

    b5 = G.Bogen.aus_mitte((0, 0, 0), 3.0, (0, 0, 1), (1, 0, 0), 90.0)
    check("Bogen aus Mitte und Winkel: Länge", b5.laenge(), 3.0 * math.pi / 2, 1e-12)
    ja("Bogen aus Mitte: Endpunkt", np.allclose(b5.punkte(4)[-1], (0, 3, 0), atol=1e-12))
    ja("Drei Punkte auf einer Geraden werden abgewiesen",
       _wirft(lambda: G.Bogen.aus_drei_punkten((0, 0, 0), (1, 0, 0), (2, 0, 0))))


def test_kreis_ellipse():
    k = G.Kreis.aus_mitte_radius((1, 2, 3), 5.0, (0, 0, 1))
    check("Kreis: Umfang 2·pi·r", k.laenge(), 2 * math.pi * 5.0, 1e-12)
    P = k.punkte(60)
    ja("Kreis: geschlossen", np.allclose(P[0], P[-1], atol=1e-9))
    ja("Kreis: alle Punkte im Abstand r",
       np.allclose(np.linalg.norm(P - np.array([1, 2, 3]), axis=1), 5.0))
    kn = G.Kreis.aus_mitte_radius((0, 0, 0), 1.0, (1, 1, 0))
    ja("Kreis in geneigter Ebene liegt in dieser Ebene",
       abs(float(np.asarray(kn.punkte(30)) @ np.array([1, 1, 0]) / math.sqrt(2)).max()) < 1e-9
       if False else np.allclose(np.asarray(kn.punkte(30)) @ np.array([1, 1, 0]), 0, atol=1e-9))

    a, b = 3.0, 2.0
    e = G.Ellipse(np.zeros(3), np.array([a, 0, 0]), np.array([0, b, 0]))
    ramanujan = math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))
    check("Ellipse: Umfang nach Ramanujan", e.laenge(4000), ramanujan, 1e-5)
    P = e.punkte(4)
    ja("Ellipse: Halbachsen getroffen",
       np.allclose(P[0], (a, 0, 0)) and np.allclose(P[1], (0, b, 0), atol=1e-12))


def test_parabel():
    p = G.Parabel.aus_stich((0, 0, 0), (10, 0, 0), 1.0, (0, 0, 1))
    ja("Parabel: Scheitel liegt beim Stich",
       np.allclose(p.punkte(2)[1], (5, 0, 1), atol=1e-12))
    ja("Parabel: Anfang und Ende genau getroffen",
       np.allclose(p.punkte(8)[0], (0, 0, 0)) and np.allclose(p.punkte(8)[-1], (10, 0, 0)))
    # Laenge einer flachen Parabel: Naeherung L(1 + 8/3 (f/L)^2)
    f, L = 1.0, 10.0
    check("Parabel: Länge nahe der Näherung L(1+8/3·(f/L)²)",
          p.laenge(4000), L * (1 + 8.0 / 3.0 * (f / L) ** 2), 2e-3)
    ja("Parabel ohne Länge wird abgewiesen",
       _wirft(lambda: G.Parabel.aus_stich((1, 1, 1), (1, 1, 1), 1.0)))


def test_spline():
    s = G.Spline([(0, 0, 0), (1, 2, 0), (3, 2, 0), (4, 0, 0)], 3)
    P = s.punkte(20)
    ja("Spline: läuft durch den ersten Steuerpunkt", np.allclose(P[0], (0, 0, 0)))
    ja("Spline: läuft durch den letzten Steuerpunkt",
       np.allclose(P[-1], (4, 0, 0), atol=1e-9))
    ja("Spline: bleibt in der konvexen Hülle",
       P[:, 1].max() <= 2.0 + 1e-9 and P[:, 0].min() >= -1e-9)

    gerade = G.Spline([(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)], 1).punkte(6)
    check("Spline Grad 1 ist die Polylinie", float(gerade[3][0]), 1.5, 1e-12)

    # NURBS: Viertelkreis mit dem Gewicht 1/sqrt(2) - Radius muss genau 1 sein
    q = G.Spline([(1, 0, 0), (1, 1, 0), (0, 1, 0)], 2,
                 [1.0, math.sqrt(0.5), 1.0]).punkte(16)
    r = np.linalg.norm(q, axis=1)
    check("NURBS-Viertelkreis: größter Radius", float(r.max()), 1.0, 1e-12)
    check("NURBS-Viertelkreis: kleinster Radius", float(r.min()), 1.0, 1e-12)
    ja("Gewichte kleiner null werden abgewiesen",
       _wirft(lambda: G.Spline([(0, 0, 0), (1, 0, 0)], 1, [1.0, -1.0]).punkte()))
    ja("Ein Steuerpunkt ist zu wenig",
       _wirft(lambda: G.Spline([(0, 0, 0)]).punkte()))
    ja("Unbekannte Art wird abgewiesen", _wirft(lambda: G.kurve("wolke")))


# --------------------------------------------------------------------------
def test_koordinatensysteme():
    g = KS.Koordinatensystem.global_ks()
    ja("Globales KS ändert nichts", np.allclose(g.nach_global((1, 2, 3)), (1, 2, 3)))

    neigung = 20.0
    s = KS.Koordinatensystem.aus_punkten(
        "Gleitbahn", (0, 0, 0),
        (math.cos(math.radians(neigung)), 0, math.sin(math.radians(neigung))), (0, 1, 0))
    p = s.nach_global((10, 0, 0))
    check("Geneigte Bahn: Höhe nach 10 m", float(p[2]),
          10 * math.sin(math.radians(neigung)), 1e-12)
    ja("Geneigte Bahn: Rückweg trifft wieder", np.allclose(s.aus_global(p), (10, 0, 0)))
    check("Achsen bleiben rechtshändig", float(np.cross(s.ex, s.ey) @ s.ez), 1.0, 1e-12)

    v = KS.Koordinatensystem("Rohr", np.zeros(3), art="zylindrisch")
    ja("Zylindrisch: r=2, θ=90° liegt auf der y-Achse",
       np.allclose(v.nach_global((2, 90, 1)), (0, 2, 1), atol=1e-12))
    ja("Zylindrisch: Rückweg", np.allclose(v.aus_global((0, 2, 1)), (2, 90, 1)))
    ja("Zylindrisch: Achsennamen", v.achsennamen()[1].startswith("θ"))

    k = KS.Koordinatensystem("Kugel", np.zeros(3), art="sphaerisch")
    ja("Sphärisch: r=1, θ=0, φ=90° liegt auf der x-Achse",
       np.allclose(k.nach_global((1, 0, 90)), (1, 0, 0), atol=1e-12))
    ja("Sphärisch: Rückweg", np.allclose(k.aus_global((0, 0, 2)), (2, 0, 0), atol=1e-12))

    d = KS.Koordinatensystem.aus_winkeln("gedreht", (1, 1, 1), 0, 0, 90)
    ja("Drehung um z: x-Achse zeigt nach y", np.allclose(d.ex, (0, 1, 0), atol=1e-12))
    ja("Drehung: Ursprung wird mitgeführt",
       np.allclose(d.nach_global((0, 0, 0)), (1, 1, 1)))

    st = KS.Koordinatensystem.an_stab("Stab", (0, 0, 0), (0, 0, 5))
    ja("KS am senkrechten Stab: x läuft die Achse entlang",
       np.allclose(st.ex, (0, 0, 1), atol=1e-12))
    ja("Ungültige Achse wird abgewiesen",
       _wirft(lambda: KS.Koordinatensystem.aus_punkten("x", (0, 0, 0), (0, 0, 0), (1, 0, 0))))


def test_arbeitsebene_und_fang():
    g = KS.Koordinatensystem.global_ks()
    ae = KS.Arbeitsebene(g, "xy", 0.0, 0.5)
    ja("Strahl von oben trifft die xy-Ebene",
       np.allclose(ae.schnitt((1, 2, 5), (0, 0, -1)), (1, 2, 0)))
    ja("Paralleler Strahl trifft nicht", ae.schnitt((0, 0, 1), (1, 0, 0)) is None)
    ja("Versatz hebt die Ebene an",
       np.allclose(KS.Arbeitsebene(g, "xy", 2.0, 0).schnitt((0, 0, 9), (0, 0, -1)),
                   (0, 0, 2)))
    ja("Punkt wird auf die Ebene gelegt",
       np.allclose(ae.projizieren((1, 2, 7)), (1, 2, 0)))
    ja("Raster zieht auf das nächste Vielfache",
       np.allclose(ae.rasterpunkt((1.2, 2.4, 0)), (1.0, 2.5, 0)))
    ja("Ohne Raster bleibt der Punkt",
       np.allclose(KS.Arbeitsebene(g, "xy", 0, 0).rasterpunkt((1.2, 2.4, 0)),
                   (1.2, 2.4, 0)))
    ja("Ebene yz", KS.Arbeitsebene(g, "yz").achsen()[2][0] == 1.0)

    kn = np.array([[0, 0, 0], [4, 0, 0], [4, 3, 0]], float)
    kanten = [(0, 1), (1, 2)]
    t = KS.fangen((0.05, 0.02, 0), kn, kanten, ae, 0.15)
    ja("Fang: Knoten geht vor", t.art == "knoten" and t.knoten == 0, t.text())
    ja("Fang: Punkt liegt genau auf dem Knoten", np.allclose(t.punkt, (0, 0, 0)))
    t = KS.fangen((2.02, 0.01, 0), kn, kanten, ae, 0.15)
    ja("Fang: Kantenmitte", t.art == "mitte" and np.allclose(t.punkt, (2, 0, 0)), t.text())
    t = KS.fangen((1.49, 0.98, 0), kn, kanten, ae, 0.15)
    ja("Fang: Rasterpunkt", t.art == "raster" and np.allclose(t.punkt, (1.5, 1.0, 0)),
       t.text())
    t = KS.fangen((1.2, 0.9, 0), kn, kanten, ae, 0.05)
    ja("Fang: außerhalb der Weite wird nichts gefangen", t.art == "" and t.text() == "frei")
    t = KS.fangen((0.05, 0.02, 0), kn, kanten, ae, 0.15, arten=("raster",))
    ja("Fang: abgeschaltete Arten greifen nicht", t.art != "knoten", t.text())


def test_linien_im_modell():
    m = Model("Linien")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 200"))
    for p in ((2, 0, 0), (0, 2, 0), (-2, 0, 0)):
        m.add_node(*p)
    m.add_line("B1", [0, 1, 2], "arc")
    check("Bogen im Modell: Länge", m.lines["B1"].laenge(m), 2 * math.pi, 1e-9)
    els = m.line_to_beams("B1", "S235", "IPE 200", 8)
    ja("Bogen wird in Stäbe geteilt", len(els) == 8 and m.nn == 9, f"{len(els)}/{m.nn}")
    L = sum(float(np.linalg.norm(m.nodes[e.nodes[1]] - m.nodes[e.nodes[0]]))
            for e in m.elements)
    ja("Sehnenzug ist etwas kürzer als der Bogen", L < 2 * math.pi, f"{L:.4f}")
    check("Sehnenzug nähert den Bogen auf 1 %", L, 2 * math.pi, 1.1e-2)
    ja("Stäbe hängen zusammen",
       all(m.elements[k].nodes[1] == m.elements[k + 1].nodes[0]
           for k in range(len(m.elements) - 1)))
    ja("Stäbe tragen den Namen der Linie als Gruppe",
       all(e.group == "B1" for e in m.elements))

    m.add_line("K1", typ="circle", mitte=(0, 0, 5), radius=3.0)
    check("Kreis im Modell: Umfang", m.lines["K1"].laenge(m), 2 * math.pi * 3, 1e-9)
    m.add_line("S1", [0, 1, 2], "spline", grad=2)
    ja("Spline im Modell", m.lines["S1"].punkte(m, 10).shape == (11, 3))

    d = m.to_dict()
    m2 = Model.from_dict(d)
    ja("Linien überstehen Speichern und Laden",
       set(m2.lines) == {"B1", "K1", "S1"} and m2.lines["K1"].typ == "circle")
    check("Kreis nach dem Laden unverändert", m2.lines["K1"].laenge(m2),
          2 * math.pi * 3, 1e-9)
    ja("Geometrieangaben überstehen den Rückweg",
       abs(float(m2.lines["K1"].geometrie["radius"]) - 3.0) < 1e-12)


def _wirft(fn) -> bool:
    try:
        fn()
    except Exception:      # noqa: BLE001
        return True
    return False


def main():
    print("=" * 92)
    print("STATIK3D - Verifikation Geometrie (Linienarten, Koordinatensysteme, Fang)")
    print("=" * 92)
    for t in (test_polylinie, test_bogen, test_kreis_ellipse, test_parabel,
              test_spline, test_koordinatensysteme, test_arbeitsebene_und_fang,
              test_linien_im_modell):
        print(f"\n--- {t.__name__} ---")
        t()
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 92)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
