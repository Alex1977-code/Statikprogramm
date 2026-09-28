"""T3: Schnittzellen-Integration. Polyeder-Bausteine, ebene Geometrie exakt auf jeder Tiefe,
gekruemmte Geometrie zweiter Ordnung in der Blattkante, Lochplatte, alpha-Anteil.

Aufruf: python -m volumen3d.tests.test_quadratur
"""
from __future__ import annotations

import os
import sys
import time
from math import factorial

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402


def _quadratur(params, h, p, tiefe, alpha=0.0, polster=0.1, **kw):
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.fcm.quadratur import Zellquadratur
    from volumen3d.geometry.csg import aus_params
    g = aus_params(params)
    G = Gitter(g, h=h, polster=polster)
    return Zellquadratur(G, p=p, tiefe=tiefe, alpha=alpha, **kw)


def test_polyeder():
    from volumen3d.geometry.polyeder import box_flaechen, clippen, polyeder_quadratur, tet_regel, volumen
    for n in (2, 3, 5):
        X, W = tet_regel(n)
        check(f"Tetraeder-Regel n={n}: Summe Gewichte 1/6, alle positiv", abs(W.sum() - 1 / 6) < 1e-14 and W.min() > 0)
        fehler = 0.0
        for a in range(0, 2 * n):
            for b in range(0, 2 * n - a):
                for c in range(0, 2 * n - a - b):
                    exakt = factorial(a) * factorial(b) * factorial(c) / factorial(a + b + c + 3)
                    fehler = max(fehler, abs((W * X[:, 0] ** a * X[:, 1] ** b * X[:, 2] ** c).sum() - exakt) / exakt)
        check(f"Tetraeder-Regel n={n}: Monome bis Gesamtgrad {2 * n - 1} exakt", fehler < 1e-12, f"{fehler:.1e}")
    F = box_flaechen([0, 0, 0], [1, 1, 1])
    check("Box: 6 Flaechen, Volumen 1", len(F) == 6 and abs(volumen(F) - 1) < 1e-14)
    G = clippen(F, [0.3, 0, 0], [1.0, 0, 0])
    check("Box ∩ {x <= 0.3}: 6 Flaechen, Volumen 0.3", len(G) == 6 and abs(volumen(G) - 0.3) < 1e-14, f"{len(G)}, {volumen(G):.6f}")
    n = np.array([1.0, 1, 1]) / np.sqrt(3)
    G = clippen(F, [0.5, 0.5, 0.5], n)
    check("Box ∩ schraeger Halbraum durch die Mitte: Volumen 1/2, Deckel Sechseck", abs(volumen(G) - 0.5) < 1e-14 and max(len(f) for f in G) == 6)
    G2 = clippen(G, [0.5, 0.5, 0.5], -n)
    check("nochmals mit der Gegenseite: Volumen 0", volumen(G2) < 1e-14)
    G3 = clippen(F, [0.2, 0, 0], [-1.0, 0, 0])                     # x >= 0.2
    G3 = clippen(G3, [0, 0.7, 0], [0, 1.0, 0])                      # y <= 0.7
    P, W = polyeder_quadratur(G3, 3)
    check("Quadratur des Polyeders: Gewichte = Volumen 0.56, int x = 0.56 * 0.6", abs(W.sum() - 0.56) < 1e-14 and abs((W * P[:, 0]).sum() - 0.56 * 0.6) < 1e-14)
    check("Clip weit ausserhalb: unveraendert; Clip alles weg: leer", len(clippen(F, [5, 0, 0], [1.0, 0, 0])) == 6 and clippen(F, [-5, 0, 0], [1.0, 0, 0]) == [])


def test_ebene_geometrie_exakt():
    n = np.array([1.0, 2.0, 3.0]) / np.sqrt(14.0)
    params = {"csg": {"typ": "schnitt", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100]},
                                                  {"typ": "halbraum", "punkt": [50, 50, 50], "normale": list(n)}]}}
    for tiefe in (0, 1, 2):
        Q = _quadratur(params, 20.0, 3, tiefe)
        V = Q.volumen()
        check(f"schraeg halbierter Wuerfel, Tiefe {tiefe}: Volumen exakt 5e5 (< 1e-10)", abs(V / 5e5 - 1) < 1e-10,
              f"{V:.6f}, {Q.anzahl_punkte()} Punkte, {Q.statistik}")
    # zwei Ebenen mit Kante im Gebiet: unabhaengig von der Tiefe (exakt) und gegen Monte-Carlo
    n2 = np.array([-2.0, 1.0, 1.5])
    n2 /= np.linalg.norm(n2)
    params2 = {"csg": {"typ": "schnitt", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100]},
                                                   {"typ": "halbraum", "punkt": [60, 50, 50], "normale": list(n)},
                                                   {"typ": "halbraum", "punkt": [30, 40, 70], "normale": list(n2)}]}}
    from volumen3d.geometry.csg import aus_params
    g = aus_params(params2)
    rng = np.random.default_rng(3)
    monte = g.innen(rng.uniform(0, 100, (2_000_000, 3))).mean() * 1e6
    V0 = _quadratur(params2, 20.0, 2, 0).volumen()
    V3 = _quadratur(params2, 20.0, 2, 3).volumen()
    check("zwei Ebenen mit Kante: Tiefe 0 = Tiefe 3 (< 1e-10)", abs(V0 / V3 - 1) < 1e-10, f"{V0:.6f} / {V3:.6f}")
    check("zwei Ebenen mit Kante: gegen Monte-Carlo 2e6 Punkte (< 3e-3)", abs(V0 / monte - 1) < 3e-3, f"{V0:.0f} / {monte:.0f}")
    # Quaderkante (zwei Seiten in einer Zelle, kein Polster): Volumen exakt
    Q = _quadratur({"csg": {"typ": "quader", "min": [3, 3, 3], "max": [37, 27, 17]}}, 10.0, 2, 0, polster=0.0)
    check("Quader mit Kanten und Ecken in den Zellen: Volumen exakt (< 1e-12)", abs(Q.volumen() / (34 * 24 * 14) - 1) < 1e-12, f"{Q.volumen():.6f}")
    check("dabei nur ebene Blaetter, kein Punkttest", Q.statistik["blaetter_punkttest"] == 0 and Q.statistik["blaetter_eben"] > 0, str(Q.statistik))


def test_kugel_zweite_ordnung():
    R = 43.0
    soll = 4 / 3 * np.pi * R ** 3
    params = {"csg": {"typ": "kugel", "mitte": [0, 0, 0], "radius": R}}
    fehler, punkte, zeiten = [], [], []
    for k in (0, 1, 2, 3):
        t = time.perf_counter()
        Q = _quadratur(params, 10.0, 2, k)
        V = Q.volumen()
        zeiten.append(time.perf_counter() - t)
        fehler.append(abs(V / soll - 1))
        punkte.append(Q.anzahl_punkte())
    # Tangentialebene: Fehler ~ 0,25 (Blattkante/R)^2, gemessen 27.09.2026 (h = 10, R = 43):
    # k=0 1,4e-2, k=1 3,4e-3, k=2 8,5e-4, k=3 2,1e-4 - Faktor 4 je Stufe
    # Tiefe 0 wird bei R 43 < 5 h automatisch auf Tiefe 1 gehoben (Regel kleine Radien), daher k=0 = k=1
    check("Kugel: Fehler faellt je Stufe (ab Tiefe 1) mindestens um den Faktor 3,5 (zweite Ordnung in der Blattkante)",
          all(fehler[i] / fehler[i + 1] > 3.5 for i in range(1, 3)) and abs(fehler[0] / fehler[1] - 1) < 1e-9,
          " ".join(f"k={k}: {f:.1e} ({n} Pkt, {z:.2f} s)" for k, f, n, z in zip((0, 1, 2, 3), fehler, punkte, zeiten)))
    check("Kugel, Tiefe 2 (Standard): Volumenfehler < 1e-3", fehler[2] < 1e-3, f"{fehler[2]:.1e}")
    check("Kugel, Tiefe 3: Volumenfehler < 3e-4", fehler[3] < 3e-4, f"{fehler[3]:.1e}")
    Q0 = _quadratur(params, 10.0, 2, 1)
    Q = _quadratur(params, 10.0, 2, 1, alpha=1e-8)
    check("alpha-Anteil (fiktives Gebiet) getrennt ausgewiesen: alpha * Aussenvolumen der aktiven Zellen",
          0 < Q.volumen_fiktiv() < 1e-7 * soll, f"{Q.volumen_fiktiv():.3e} mm^3 gegen {soll:.3e}")
    from volumen3d.fcm.gitter import CUT
    # V(alpha) = V_innen + (1 - alpha) * V_stuecke ist linear in alpha: Steigung aus alpha = 0,5 gegen 1e-8
    Qh = _quadratur(params, 10.0, 2, 1, alpha=0.5)
    steigung_h = (Q0.volumen() - Qh.volumen()) / 0.5
    steigung_a = (Q0.volumen() - Q.volumen()) / 1e-8
    check("Werkstoffgewichte skalieren linear mit (1 - alpha): Steigung bei alpha 1e-8 = Steigung bei 0,5",
          abs(steigung_a / steigung_h - 1) < 1e-6 and 0 < steigung_h < soll, f"{steigung_a:.6f} gegen {steigung_h:.6f} mm^3")
    n_cut = int((Q.gitter.klasse == CUT).sum())
    check("fiktiver Anteil hoechstens alpha * Boxvolumen der CUT-Zellen, Punkte ausserhalb kommen dazu",
          Q.volumen_fiktiv() <= 1e-8 * n_cut * 1000.0 * (1 + 1e-9) and Q.anzahl_punkte() > Q0.anzahl_punkte(),
          f"{Q.volumen_fiktiv():.3e} <= {1e-8 * n_cut * 1000.0:.3e}")


def test_lochplatte():
    W, L, T, D = 400.0, 800.0, 10.0, 40.0
    params = {"csg": {"typ": "differenz", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [L, W, T], "name": "platte"},
        {"typ": "zylinder", "p0": [L / 2, W / 2, -1], "p1": [L / 2, W / 2, T + 1], "radius": D / 2, "name": "loch"}]}}
    soll = L * W * T - np.pi * (D / 2) ** 2 * T
    # gemessen 27.09.2026 (h = 10, p = 3): Tiefe 1 2,0e-5, Tiefe 2 4,3e-6 (Bohrungswand als Tangentialebenen)
    for k, grenze in ((1, 4e-5), (2, 1e-5)):
        t = time.perf_counter()
        Q = _quadratur(params, 10.0, 3, k)
        V = Q.volumen()
        check(f"Lochplatte, Tiefe {k}: Volumen gegen Formel < {grenze:.0e}", abs(V / soll - 1) < grenze,
              f"Abw. {abs(V / soll - 1):.1e}, {Q.anzahl_punkte()} Punkte, {time.perf_counter() - t:.1f} s, {Q.statistik}")
        check(f"Lochplatte, Tiefe {k}: kein Punkttest-Rueckfall", Q.statistik["blaetter_punkttest"] == 0,
              "; ".join(f"Mitte {m.round(2)}, r {r:.2f}" for m, r in Q.punkttest_orte[:3]))
    Qp = _quadratur({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 10]}}, 10.0, 3, 2)
    check("Platte ohne Loch (alle Zellen CUT): 64 Punkte je Zelle (achsparallele Teilbox statt Tetraeder), Volumen exakt",
          Qp.anzahl_punkte() == 64 * len(Qp.gitter.ijk) and abs(Qp.volumen() / 1e5 - 1) < 1e-13,
          f"{Qp.anzahl_punkte()} Punkte, {len(Qp.gitter.ijk)} Zellen, V {Qp.volumen():.6f}")


def test_kleine_radien():
    """Gutachten 27.09.: Kruemmungsradius kleiner als das Blatt (Schraubenbohrung R 3 bei h 10) - die
    Tangentialebene ersetzte einen ganzen Bogen (Lochvolumen -5,8 %, freie Kugel R 3 +16 %)."""
    # Nachteilung bis zur Hoechsttiefe (2 + 2 = 4, Blattkante 0,625 mm): Tangentialfehler
    # 0,25 (0,625/3)^2 = 1,1 %; danach zaehlt das Protokoll die unteraufgeloesten Blaetter
    soll = 4 / 3 * np.pi * 27.0
    Q = _quadratur({"csg": {"typ": "kugel", "mitte": [0, 0, 0], "radius": 3.0}}, 10.0, 2, 2)
    check("freie Kugel R 3 in h = 10: Volumen auf 2 % (vorher +16 %), unteraufgeloeste Blaetter gezaehlt",
          abs(Q.volumen() / soll - 1) < 0.02 and Q.statistik["blaetter_unteraufgeloest"] > 0, f"{Q.volumen():.3f} / {soll:.3f}, {Q.statistik}")
    platte = {"csg": {"typ": "differenz", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 10]},
                                                    {"typ": "zylinder", "p0": [50, 50, -1], "p1": [50, 50, 11], "radius": 3.0}]}}
    Q = _quadratur(platte, 10.0, 2, 2)
    check("Platte mit Bohrung R 3 in h = 10: Lochvolumen auf 2 % (vorher -5,8 %)",
          abs((1e5 - Q.volumen()) / (np.pi * 90.0) - 1) < 0.02, f"Loch {1e5 - Q.volumen():.2f} / {np.pi * 90.0:.2f}, {Q.statistik}")
    Q8 = _quadratur({"csg": {"typ": "differenz", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 10]},
                                                             {"typ": "zylinder", "p0": [50, 50, -1], "p1": [50, 50, 11], "radius": 8.0}]}}, 10.0, 2, 2)
    check("Bohrung R 8 in h = 10: Lochvolumen auf 0,5 % (vorher -0,7 %)",
          abs((1e5 - Q8.volumen()) / (np.pi * 640.0) - 1) < 0.005, f"Loch {1e5 - Q8.volumen():.2f} / {np.pi * 640.0:.2f}, {Q8.statistik}")


def test_inside_zelle():
    from volumen3d.fcm.gitter import INSIDE, Gitter
    from volumen3d.fcm.quadratur import Zellquadratur
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "kugel", "mitte": [0, 0, 0], "radius": 43.0}})
    G = Gitter(g, h=10.0)
    Q = Zellquadratur(G, p=3)
    c = int(np.flatnonzero(G.klasse == INSIDE)[0])
    P, W, I = Q.zelle(c)
    lo, hi = G.zellbox(c)
    check("INSIDE: 64 Punkte, Summe Gewichte h^3, alle innen", len(P) == 64 and abs(W.sum() - 1000.0) < 1e-9 and I.all())
    x = P[:, 0] - lo[0]
    check("INSIDE: integriert x^7 ueber die Zelle exakt", abs((W * x ** 7).sum() - 100.0 * 10.0 ** 8 / 8) < 1e-6 * 10 ** 10)


if __name__ == "__main__":
    sys.exit(lauf([test_polyeder, test_ebene_geometrie_exakt, test_kugel_zweite_ordnung, test_lochplatte, test_kleine_radien, test_inside_zelle]))
