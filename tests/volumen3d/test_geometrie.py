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
    check("Schnitt mit Halbraum: Huellquader bleibt der Quader, x=70 ist aussen", np.allclose(s.huellquader()[1], 100) and s.abstand(np.array([[70, 50, 50.0]]))[0] == 20)
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


if __name__ == "__main__":
    sys.exit(lauf([test_grundformen, test_csg]))
