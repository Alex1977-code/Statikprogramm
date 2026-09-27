"""T2: Geometriekern - Grundformen, CSG, Oberflaechenquadratur.

Aufruf: python -m tests.volumen3d.test_geometrie
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from tests.volumen3d._pruef import check, lauf  # noqa: E402


def _num_grad(f, P, h=1e-6):
    g = np.zeros_like(P)
    for d in range(3):
        e = np.zeros(3)
        e[d] = h
        g[:, d] = (f(P + e) - f(P - e)) / (2 * h)
    return g


def _flaeche(V, T):
    return 0.5 * np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1).sum()


def test_grundformen():
    from volumen3d.geometry.sdf import Halbraum, Kugel, Quader, Zylinder
    rng = np.random.default_rng(1)
    q = Quader([0, 0, 0], [100, 50, 20])
    P = np.array([[50, 25, 10], [150, 25, 10], [-30, -40, 10], [50, 25, 25]], float)
    check("Quader: Abstand innen -10, aussen 50, Ecke 50, oben 5", np.allclose(q.abstand(P), [-10, 50, 50, 5]), str(q.abstand(P)))
    z = Zylinder([0, 0, 0], [0, 0, 100], 20)
    P = np.array([[0, 0, 50], [30, 0, 50], [0, 0, 120], [30, 0, 140]], float)
    check("Zylinder: -20, 10, 20, sqrt(10^2+40^2)", np.allclose(z.abstand(P), [-20, 10, 20, np.hypot(10, 40)]), str(z.abstand(P)))
    k = Kugel([1, 2, 3], 5)
    check("Kugel: -5 in der Mitte, 5 im Abstand 10", np.allclose(k.abstand(np.array([[1, 2, 3], [1, 2, 13.0]])), [-5, 5]))
    hr = Halbraum([0, 0, 10], [0, 0, 1])
    check("Halbraum: unter der Ebene negativ (Werkstoff gegen die Normale)",
          np.allclose(hr.abstand(np.array([[5, 5, 0], [5, 5, 12.0]])), [-10, 2]))
    for form in (q, z, k, hr):
        lo, hi = form.huellquader()
        lo = np.where(np.isfinite(lo), lo, -200.0)
        hi = np.where(np.isfinite(hi), hi, 200.0)
        P = rng.uniform(lo - 10, hi + 10, (300, 3))
        g = form.gradient(P)
        num = _num_grad(form.abstand, P)
        # an Knicken der Abstandsfunktion (Kanten, Achse) weicht die Differenz ab: nur glatte Punkte werten
        glatt = np.linalg.norm(num, axis=1) > 0.999
        check(f"{type(form).__name__}: Gradient gegen zentrale Differenz (glatte Punkte), Betrag 1",
              np.allclose(g[glatt], num[glatt], atol=1e-5) and np.allclose(np.linalg.norm(g, axis=1), 1.0, atol=1e-9),
              f"{glatt.sum()} von 300 Punkten glatt, max Abw. {np.abs(g[glatt] - num[glatt]).max():.1e}")
    # Normalen auf der Oberflaeche (dort ist max(q,0) = 0: Sonderfall der Boxformel)
    n = q.gradient(np.array([[100.0, 25, 10], [50, 0, 10], [50, 25, 20]]))
    check("Quader: Seitennormalen auf der Oberflaeche", np.allclose(n, [[1, 0, 0], [0, -1, 0], [0, 0, 1]]), str(n))
    n = z.gradient(np.array([[20.0, 0, 50], [0, 0, 100], [10, 0, 0]]))
    check("Zylinder: Mantel-, Deckel- und Bodennormale", np.allclose(n, [[1, 0, 0], [0, 0, 1], [0, 0, -1]]), str(n))
    V, T = z.dreiecke(np.array([-50.0, -50, -50]), np.array([50.0, 50, 150]), facette_mm=2.0)
    soll = 2 * np.pi * 20 * 100 + 2 * np.pi * 20 ** 2
    check("Zylinder-Tessellierung: Mantel + Deckel (Facette 2 mm, Fehler < 1e-3)", abs(_flaeche(V, T) / soll - 1) < 1e-3,
          f"{_flaeche(V, T):.2f} / {soll:.2f}")
    V, T = k.dreiecke(None, None, facette_mm=0.5)
    check("Kugel-Tessellierung: Flaeche 4 pi r^2 auf 1e-2", abs(_flaeche(V, T) / (4 * np.pi * 25) - 1) < 1e-2, f"{_flaeche(V, T):.3f}")
    V, T = Halbraum([50, 50, 50], [1, 1, 1]).dreiecke(np.zeros(3), np.full(3, 100.0), 0.0)
    # regelmaessiges Sechseck mit Seite 50 sqrt(2): Flaeche 3 sqrt(3)/2 * s^2 = 12990.38
    check("Halbraum: Sechseck Ebene ∩ Wuerfel, Flaeche 12990.38",
          len(V) == 6 and abs(_flaeche(V, T) - 1.5 * np.sqrt(3) * 5000.0) < 0.01, f"{len(V)} Ecken, {_flaeche(V, T):.3f}")


def test_csg():
    from volumen3d.geometry.csg import aus_params
    params = {"csg": {"typ": "differenz", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [400, 200, 10], "name": "platte"},
        {"typ": "zylinder", "p0": [200, 100, -100], "p1": [200, 100, 110], "radius": 20, "name": "bohrung"}]}}
    g = aus_params(params)
    # Bohrungsmitte: 20 zur Bohrungswand; neben der Bohrung und in der Plattenmitte ist die
    # Deckflaeche (5 mm) naeher als die Wand; ueber der Platte +2
    P = np.array([[200, 100, 5], [230, 100, 5], [100, 100, 5], [100, 100, 12.0]])
    check("Differenz: in der Bohrung +20, daneben -5 (Deckflaeche), Plattenmitte -5, ueber der Platte +2",
          np.allclose(g.abstand(P), [20, -5, -5, 2]), str(g.abstand(P)))
    # kurzer Bohrzylinder (Deckel 1 mm ausserhalb der Platte): der CSG-Abstand in der Bohrung ist
    # dann nur 6 (Abstand zum Deckel des subtrahierten Zylinders) - konservativ, nie zu gross
    kurz = aus_params({"csg": {"typ": "differenz", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [400, 200, 10]},
        {"typ": "zylinder", "p0": [200, 100, -1], "p1": [200, 100, 11], "radius": 20}]}})
    check("kurzer Bohrzylinder: Abstand in der Bohrung 6 <= wahrer Abstand 20 (konservativ)",
          abs(kurz.abstand(np.array([[200, 100, 5.0]]))[0] - 6.0) < 1e-12)
    n = g.gradient(np.array([[220.0, 100, 5]]))[0]
    check("Normale am Bohrungsrand zeigt zur Achse (aus dem Werkstoff heraus)", np.allclose(n, [-1, 0, 0]), str(n))
    lo, hi = g.huellquader()
    check("Huellquader der Differenz = Platte", np.allclose(lo, [0, 0, 0]) and np.allclose(hi, [400, 200, 10]))
    check("Namen der Grundformen", [f.name for f in g.grundformen()] == ["platte", "bohrung"])
    V, T, quelle = g.dreiecke(facette_mm=5.0)
    check("Tessellierung nennt je Dreieck die Quelle", len(T) == len(quelle) and set(quelle) == {0, 1})
    u = aus_params({"csg": {"typ": "vereinigung", "teile": [{"typ": "kugel", "mitte": [0, 0, 0], "radius": 10},
                                                              {"typ": "kugel", "mitte": [15, 0, 0], "radius": 10}]}})
    check("Vereinigung: innen negativ, auf der Oberflaeche 0",
          u.abstand(np.array([[7.5, 0, 0.0]]))[0] < 0 and abs(u.abstand(np.array([[-10, 0, 0.0]]))[0]) < 1e-12)
    s = aus_params({"csg": {"typ": "schnitt", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100]},
                                                          {"typ": "halbraum", "punkt": [50, 50, 50], "normale": [1, 0, 0]}]}})
    check("Schnitt mit achsparallelem Halbraum: Huellquader wird bei x = 50 begrenzt, x=70 ist aussen",
          np.allclose(s.huellquader()[1], [50, 100, 100]) and s.abstand(np.array([[70, 50, 50.0]]))[0] == 20, str(s.huellquader()))
    s2 = aus_params({"csg": {"typ": "schnitt", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100]},
                                                           {"typ": "halbraum", "punkt": [50, 50, 50], "normale": [1, 1, 0]}]}})
    check("schraeger Halbraum begrenzt den Huellquader nicht", np.allclose(s2.huellquader()[1], 100))
    # konservative Abstaende: |d_csg| <= wahrer Abstand (Stichprobe gegen feine Punktwolke der Oberflaeche)
    rng = np.random.default_rng(5)
    Pw = rng.uniform([-20, -20, -20], [420, 220, 30], (400, 3))
    Vf, Tf, _ = g.dreiecke(facette_mm=1.0)
    S = Vf[Tf].mean(axis=1)
    S = S[np.abs(g.abstand(S)) < 1e-3]                       # Schwerpunkte, die wirklich auf der Gesamtoberflaeche liegen
    wahr = np.min(np.linalg.norm(Pw[:, None, :] - S[None, :, :], axis=2), axis=1)
    check("CSG-Abstand ueberschaetzt den wahren Abstand nie (Toleranz Facette 1 mm)",
          np.all(np.abs(g.abstand(Pw)) <= wahr + 1.0), f"max Ueberschuss {np.max(np.abs(g.abstand(Pw)) - wahr):.3f} mm")
    try:
        aus_params({"csg": {"typ": "torus"}})
        fehler = False
    except ValueError:
        fehler = True
    check("unbekannter Typ -> ValueError", fehler)
    try:
        aus_params({"csg": {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, 0, 1]}})
        fehler = False
    except ValueError:
        fehler = True
    check("unendlicher Huellquader -> ValueError", fehler)


def test_lokale_stuecke():
    """Lokale Zerlegung: Platte mit Loch nahe der Bohrung und der Deckflaeche, ferne Form, Vereinigung."""
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "differenz", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [400, 200, 10], "name": "platte"},
        {"typ": "zylinder", "p0": [200, 100, -1], "p1": [200, 100, 11], "radius": 20, "name": "bohrung"}]}})
    proben = np.random.default_rng(7).uniform(-1, 1, (27, 3))
    # Deckflaeche und Bohrungswand aktiv (Kappe bei z = 11 ist 2 mm > r entfernt):
    # Box ∩ {z <= 10} minus Loch -> ein Stueck mit zwei Halbraeumen
    st = g.lokale_stuecke(np.array([221.0, 100, 9.0]), 1.5, np.array([221.0, 100, 9.0]) + 1.5 * proben)
    check("Deckflaeche + Bohrung: ein Stueck, zwei Halbraeume, gekruemmt", st is not None and len(st[0]) == 1 and len(st[0][0]) == 2 and st[1], str(st))
    # mit Kappe in Reichweite (z = 9,5, Kappe bei 11 genau 1,5 entfernt): Loch = Mantel ∩ Kappe -> zwei Stuecke
    st = g.lokale_stuecke(np.array([221.0, 100, 9.5]), 1.5, np.array([221.0, 100, 9.5]) + 1.5 * proben)
    check("Deckflaeche + Bohrung mit Kappe: zwei disjunkte Stuecke", st is not None and len(st[0]) == 2, str(st and len(st[0])))
    # ferne Bohrung (1,85 mm > r) darf die Rekonstruktion nicht stoeren (Fehlerbild vom 27.09.)
    st = g.lokale_stuecke(np.array([209.62, 119.62, 0.88]), 1.08, np.array([209.62, 119.62, 0.88]) + 1.08 * proben)
    check("Bodenflaeche mit ferner Bohrung: ein Stueck mit nur der Bodenebene, eben", st is not None and len(st[0]) == 1 and len(st[0][0]) == 1 and not st[1], str(st))
    # tief in der Bohrung: nur die Bohrung aktiv -> Komplement des Lochs = ein Stueck mit gekipptem Halbraum
    st = g.lokale_stuecke(np.array([219.0, 100, 5]), 1.5, np.array([219.0, 100, 5]) + 1.5 * proben)
    # Komplement der Tangentialebene (Punkt (220,100,5), Normale nach aussen aus dem Zylinder +x):
    # behalte (x - p) . (-n) <= 0, also x >= 220 = Werkstoff ausserhalb des Lochs
    check("nur Bohrungswand aktiv: ein Stueck (Komplement der Tangentialebene, Normale -x)", st is not None and len(st[0]) == 1 and len(st[0][0]) == 1
          and np.allclose(st[0][0][0][0], [220, 100, 5]) and np.allclose(st[0][0][0][1], [-1, 0, 0]), str(st))
    # ferne Form fuellt die Umgebung (Vereinigung, zweiter Quader tief innen): ganzer Werkstoff
    u = aus_params({"csg": {"typ": "vereinigung", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [10, 10, 10]},
                                                              {"typ": "quader", "min": [5, 5, 0], "max": [15, 15, 10]}]}})
    st = u.lokale_stuecke(np.array([10.0, 10.0, 5.0]), 1.5, np.array([10.0, 10.0, 5.0]) + 1.5 * proben)
    check("Vereinigung, zweiter Quader ueberdeckt die Umgebung: ein Stueck ohne Halbraeume (alles Werkstoff)", st is not None and st[0] == [[]], str(st))
    # einspringende Ecke bei (10, 5): Werkstoff = {x <= 10} ∪ {y >= 5}, Box 3x3x3 minus 1,5x1,5x3 = 20,25
    st = u.lokale_stuecke(np.array([10.0, 5.0, 5.0]), 1.5, np.array([10.0, 5.0, 5.0]) + 1.5 * proben)
    check("Vereinigung an der einspringenden Ecke: zwei disjunkte Stuecke", st is not None and len(st[0]) == 2, str(st and len(st[0])))
    from volumen3d.geometry.polyeder import box_flaechen, clippen, volumen
    V = 0.0
    for stueck in st[0]:
        F = box_flaechen([8.5, 3.5, 3.5], [11.5, 6.5, 6.5])
        for p, n in stueck:
            F = clippen(F, p, n)
            if not F:
                break
        V += volumen(F) if F else 0.0
    check("Stuecke fuellen genau den Werkstoff der Box (27 - 6,75 = 20,25)", abs(V - 20.25) < 1e-12, f"{V:.6f}")


def test_oberflaechenquadratur():
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.geometry.csg import aus_params
    from volumen3d.geometry.oberflaeche import Flaechenquadratur, dreieck_an_box_clippen, dreieck_gauss, polygon_flaeche
    # Dreieck (-10,0),(30,0),(10,40) enthaelt das Quadrat [0,20]^2 ganz (Kanten x = -10 + y/2 und x = 30 - y/2 treffen bei y = 20 genau 0 und 20)
    poly = dreieck_an_box_clippen(np.array([[-10, 0, 5], [30, 0, 5], [10, 40, 5.0]]), np.array([0, 0, 0.0]), np.array([20, 20, 10.0]))
    check("Clipping: Dreieck ∩ Box = ganzes Quadrat, Flaeche 400", abs(polygon_flaeche(poly) - 400.0) < 1e-9 and len(poly) == 4, f"{polygon_flaeche(poly):.3f}, {len(poly)} Ecken")
    poly2 = dreieck_an_box_clippen(np.array([[-10, -10, 5], [30, -10, 5], [-10, 30, 5.0]]), np.array([0, 0, 0.0]), np.array([20, 20, 10.0]))
    check("Clipping: Dreieck x+y <= 20 ∩ Quadrat = Dreieck 200", abs(polygon_flaeche(poly2) - 200.0) < 1e-9, f"{polygon_flaeche(poly2):.3f}")
    xi, w = dreieck_gauss(3)
    check("Dreiecks-Gauss: Gewichte summieren zu 1/2, integriert x^2 y^2 exakt (2!2!/6! = 1/180)",
          abs(w.sum() - 0.5) < 1e-14 and abs((w * xi[:, 0] ** 2 * xi[:, 1] ** 2).sum() - 1 / 180) < 1e-14)
    g = aus_params({"csg": {"typ": "differenz", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [200, 100, 10], "name": "platte"},
        {"typ": "zylinder", "p0": [100, 50, -1], "p1": [100, 50, 11], "radius": 20, "name": "bohrung"}]}})
    G = Gitter(g, h=10.0)
    fq = Flaechenquadratur.aus_geometrie(g, G, ordnung=3)          # Facette Standard 0,5 h = 5 mm
    A = {name: fq.gewichte[fq.name == name].sum() for name in ("platte", "bohrung")}
    soll_platte = 2 * (200 * 100 - np.pi * 400) + 2 * (200 * 10 + 100 * 10)
    # Lochrand auf der Deckflaeche als Sehnen der Tangentialebenen (Vierteilung bis Tiefe 2): zweite Ordnung
    check("Plattenflaechen ohne Loch (2 Deck + 4 Stirn) auf 3e-4 (Sehnen am Lochrand, Facette 5 mm)", abs(A["platte"] / soll_platte - 1) < 3e-4, f"{A['platte']:.3f} / {soll_platte:.3f}, {fq.statistik}, {len(fq.punkte)} Punkte")
    check("Bohrungsmantel nur innerhalb der Platte (2 pi r t) auf 1e-7 dank Flaechenfaktor Bogen/Sehne (Facette 5 mm)", abs(A["bohrung"] / (2 * np.pi * 20 * 10) - 1) < 1e-7, f"{A['bohrung']:.8f} / {2 * np.pi * 200:.8f}")
    kugel = aus_params({"csg": {"typ": "kugel", "mitte": [0, 0, 0], "radius": 30.0}})
    fk = Flaechenquadratur.aus_geometrie(kugel, Gitter(kugel, h=10.0), ordnung=3)
    # Restfehler ist die Quadraturordnung auf der Facette (Flaechenfaktor glatt, nicht polynomial): 9e-9 bei Facette 5 mm
    check("Kugeloberflaeche 4 pi r^2 auf 1e-7 mit Facette 5 mm (Flaechenfaktor)", abs(fk.gewichte.sum() / (4 * np.pi * 900) - 1) < 1e-7, f"{fk.gewichte.sum():.6f} / {4 * np.pi * 900:.6f}, {len(fk.punkte)} Punkte")
    n = fq.normalen[fq.name == "bohrung"]
    P = fq.punkte[fq.name == "bohrung"]
    check("Normalen der Bohrung zeigen zur Achse, Punkte exakt auf r = 20",
          np.allclose(n[:, :2], -(P[:, :2] - [100, 50]) / 20, atol=1e-9) and np.allclose(n[:, 2], 0) and np.allclose(np.hypot(*(P[:, :2] - [100, 50]).T), 20.0))
    check("jeder Punkt liegt in seiner Zelle", np.all(np.abs(fq.xi) <= 1 + 1e-9))
    check("kein Rueckfall, kein Punkt vom Sicherheitsfilter verworfen", fq.statistik["rueckfall"] == 0 and fq.statistik["verworfen"] == 0, str(fq.statistik))
    e = Flaechenquadratur.ebene(g, G, punkt=np.array([0.0, 0, 0]), normale=np.array([-1.0, 0, 0]), ordnung=3)
    check("Ebenenauswahl x=0: Flaeche 100 x 10 exakt", abs(e.gewichte.sum() - 1000.0) < 1e-9, f"{e.gewichte.sum():.6f}")
    # Ebene durch die Bohrung (y = 50): Deckflaeche der Platte minus Lochstrecke -> nichts, denn sie liegt im Inneren
    check("Ebene im Werkstoffinneren liefert keine Punkte", len(Flaechenquadratur.ebene(g, G, np.array([0, 50.0, 0]), np.array([0, 1.0, 0]), 3).punkte) == 0)
    # schraeg geschnittener Quader: Schnittflaeche = Sechseck 12990,38 exakt, Normale (1,1,1)/sqrt3
    s = aus_params({"csg": {"typ": "schnitt", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "w"},
                                                          {"typ": "halbraum", "punkt": [50, 50, 50], "normale": [1, 1, 1], "name": "s"}]}})
    Gs = Gitter(s, h=20.0)
    fs = Flaechenquadratur.aus_geometrie(s, Gs, ordnung=4)
    As = fs.gewichte[fs.name == "s"].sum()
    check("schraege Schnittflaeche: Sechseck exakt (< 1e-10)", abs(As / 12990.381056766578 - 1) < 1e-10, f"{As:.6f}")
    # drei Seiten bei 0 verlieren je ein Dreieck 50x50/2 = 1250, drei Seiten bei 100 behalten je 1250: 3*8750 + 3*1250 = 30000
    Aw = fs.gewichte[fs.name == "w"].sum()
    check("Wuerfelseiten ohne den abgeschnittenen Teil: 30000 exakt (< 1e-10)", abs(Aw / 30000.0 - 1) < 1e-10, f"{Aw:.6f}, {fs.statistik}")


if __name__ == "__main__":
    sys.exit(lauf([test_grundformen, test_csg, test_lokale_stuecke, test_oberflaechenquadratur]))
