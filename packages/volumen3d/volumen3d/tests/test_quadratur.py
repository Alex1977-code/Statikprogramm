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


def test_momentfitting():
    """Moment Fitting (Vorgabe 6 Stufe 2, Plan TP 5 B1): (1) an einer halb gefuellten Zelle trifft die gefittete Regel
    (Tensor-Gauss (q+1)^3) alle Tensor-Momente bis Grad q exakt - Gegenprobe mit Monomen, unabhaengig von der
    Legendre-Basis des Fits; (2) mit q = 2p sind alle Integranden der Zellsteifigkeit exakt: am Lame-Zylinder h 20 p 2
    stimmt jede Schnittzellmatrix mit der Referenzquadratur auf 1e-11 ueberein, das Werkstoffvolumen auf 1e-12, kein
    Rueckfall, und die Punkte je Schnittzelle sinken mindestens um den Faktor 10 (gemessen 30.09.2026: 2517 -> 112);
    (3) mit q = p ist das nicht so: gemessen indefinite Zellmatrizen (kleinster relativer Eigenwert -1,9e-3) - darum
    ist 2p die Vorgabe (fit_grad_standard)."""
    from volumen3d.fcm.basis import gauss_3d
    from volumen3d.fcm.elastizitaet import zell_gradienten, zellsteifigkeit
    from volumen3d.fcm.gitter import CUT, Gitter
    from volumen3d.fcm.momentfitting import fit_grad_standard, gefittete_regel
    from volumen3d.fcm.quadratur import Zellquadratur
    from volumen3d.tests.test_lame import E, NU, _geometrie
    # (1) Werkstoff = Teilbox [0, 1.3] x [0, 2] x [0, 2] der Zelle [0, 2]^3, Referenz Tensor-Gauss 8^3 darauf
    q = 6
    X, W = gauss_3d(8)
    lo, hi, b_hi = np.zeros(3), np.full(3, 2.0), np.array([1.3, 2.0, 2.0])
    s = 0.5 * (b_hi - lo)
    P_ref, W_ref = lo + s * (X + 1.0), W * float(np.prod(s))
    erg = gefittete_regel(lo, hi, P_ref, W_ref, q, 3)
    f_max = 0.0
    for a in range(q + 1):
        for b in range(0, q + 1, 3):
            for c in range(0, q + 1, 2):
                exakt = (b_hi[0] ** (a + 1) / (a + 1)) * (2.0 ** (b + 1) / (b + 1)) * (2.0 ** (c + 1) / (c + 1))
                ist = float(np.sum(erg.gewichte * erg.punkte[:, 0] ** a * erg.punkte[:, 1] ** b * erg.punkte[:, 2] ** c))
                f_max = max(f_max, abs(ist - exakt) / exakt)
    check(f"Halb gefuellte Zelle, q {q}: {len(erg.gewichte)} Punkte treffen alle Monome x^a y^b z^c bis Grad {q} (< 1e-12), "
          f"Volumen {erg.gewichte.sum():.6f} = 5,2", erg.art == "fit" and f_max < 1e-12 and abs(erg.gewichte.sum() - 5.2) < 1e-12,
          f"groesste Abweichung {f_max:.1e}, kleinstes Gewicht {erg.min_gewicht:.2f} des mittleren, negative Masse {erg.neg_anteil:.3f}")
    # (2) und (3) am Lame-Zylinder
    p = 2
    G = Gitter(_geometrie(), h=20.0, polster=0.1)
    G.moden_nummerieren(p)
    # Referenz mit der Tetraederordnung 3p + 1 (exakt bis zum Gesamtgrad 6p + 1): seit O5 (03.10.2026) gehen die schraegen Stuecke mit exakten Momenten in den
    # Fit ein, die Vorgabeordnung ceil(1,5 p) der Referenz traefe die Momente nur bis zum Gesamtgrad 3p - 1 (test_stuecke_exakt)
    ref = Zellquadratur(G, p=p, momentfitting=False, ordnung_tet=3 * p + 1)
    cut = np.flatnonzero(G.klasse == CUT)
    t = time.perf_counter()
    fit = Zellquadratur(G, p=p, momentfitting=True)
    for c in cut:
        fit.zelle(int(c))
    t_fit = time.perf_counter() - t
    ergebnisse = {}
    for name, Q in (("Referenz", ref), ("q 2p", fit), ("q p", Zellquadratur(G, p=p, momentfitting=True, fit_grad=p))):
        K, n, lam = {}, 0, 0.0
        for c in cut:
            Gr, W = zell_gradienten(G, Q, int(c))
            n += len(W)
            if len(W):
                K[int(c)] = zellsteifigkeit(Gr, W, E, NU)
                ev = np.linalg.eigvalsh(K[int(c)])
                lam = min(lam, float(ev[0] / ev[-1]))
        ergebnisse[name] = (K, n, lam, Q.volumen())
    K0, n0, _, v0 = ergebnisse["Referenz"]
    K2, n2, lam2, v2 = ergebnisse["q 2p"]
    dK = max(float(np.abs(K2[c] - K0[c]).max() / np.abs(K0[c]).max()) for c in K0)
    st = fit.statistik
    check(f"Lame h 20 p {p}, q {fit.fit_grad} = 2p (fit_grad_standard {fit_grad_standard(p)}): {len(cut)} Schnittzellen, Zellmatrizen wie Referenz "
          f"(< 1e-11), Volumen gleich (< 1e-12), kein Rueckfall, Punkte {n0} -> {n2} (Faktor >= 10)",
          fit.fit_grad == 2 * p == fit_grad_standard(p) and dK < 1e-11 and abs(v2 - v0) / v0 < 1e-12 and st["fit_rueckfall"] == 0
          and st["fit_nnls"] == 0 and n0 >= 10 * n2,
          f"groesste Abweichung {dK:.1e}, Volumen {abs(v2 - v0) / v0:.1e}, Statistik {st['fit_zellen']} gefittet, kleinstes Gewicht "
          f"{st['fit_min_gewicht']:.1f}, Einrichten {t_fit:.2f} s")
    _, n1, lam1, _ = ergebnisse["q p"]
    check(f"q = p dagegen: indefinite Zellmatrizen (kleinster relativer Eigenwert {lam1:.1e} < -1e-5), bei q = 2p {lam2:.1e} >= -1e-12",
          lam1 < -1e-5 and lam2 >= -1e-12)
    # Vorgabe (Anwender 30.09.2026): ohne Angabe fittet die Zellquadratur mit q = 2p; FcmProblem reicht das durch
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    Q_std = Zellquadratur(G, p=p)
    n_std = sum(len(Q_std.zelle(int(c))[1]) for c in cut)
    pr = FcmProblem(_geometrie(), h=20.0, p=p, werkstoff=Werkstoff(E, NU))
    pr_aus = FcmProblem(_geometrie(), h=20.0, p=p, werkstoff=Werkstoff(E, NU), momentfitting=False)
    check(f"Vorgabe: Zellquadratur und FcmProblem fitten ohne Angabe mit q = 2p ({n_std} Punkte wie gefittet), "
          f"momentfitting=False schaltet zurueck",
          Q_std.momentfitting and Q_std.fit_grad == 2 * p and n_std == n2 and pr.quadratur.momentfitting
          and not pr_aus.quadratur.momentfitting and pr.quadratur.anzahl_punkte() < pr_aus.quadratur.anzahl_punkte(),
          f"Punkte FcmProblem {pr.quadratur.anzahl_punkte()} gegen {pr_aus.quadratur.anzahl_punkte()} ohne Fitting")


def test_stuecke_exakt():
    """O5 (03.10.2026): schraeg geschnittene Stuecke gehen mit exakten Momenten in das Moment Fitting ein (Divergenzsatz ueber die Polygone des Stuecks,
    geometry/huelle.polyedermomente). Vorher lieferte die Tetraederregel der Stuecke die Momente - exakt nur bis zum Gesamtgrad 2 ceil(1,5 p) - 1 = 5 (p 2)
    bzw. 9 (p 3), waehrend die Momente der Basis vom Grad 2p den Gesamtgrad 6p haben; ein quadratisches Feld wurde bei p 2 nur auf 1e-4 reproduziert
    (test_patch.test_patch_hoeherer_ordnung). Pruefkoerper: Zelle [0, 2]^3, Werkstoff die Ecke x + y + z <= 1,5 (Tetraeder). Erwartungswerte unabhaengig aus
    der Dirichlet-Formel int x^a y^b z^c dV = a! b! c! / (a + b + c + 3)! * 1,5^(a + b + c + 3), in Bruechen auf die zentrierten Monome
    (x - 1)^a (y - 1)^b (z - 1)^c umgerechnet: die sind auf der Zelle durch 1 beschraenkt, der Vergleich ist dann gut gestellt (die rohen Monome bis x^6 y^6 z^6
    reichen von 0 bis 2,6e5 bei einem Sollwert 3,6e-8 - dort misst man die Ausloeschung der Summe, nicht die Regel: 7e-5 bei p 3)."""
    from fractions import Fraction
    from math import comb, factorial
    from volumen3d.fcm.elastizitaet import zell_gradienten, zellsteifigkeit
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.fcm.quadratur import Zellquadratur
    from volumen3d.geometry.csg import aus_params
    c0 = 1.5
    g = aus_params({"csg": {"typ": "schnitt", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [2, 2, 2], "name": "w"},
        {"typ": "halbraum", "punkt": [c0, 0, 0], "normale": [1, 1, 1], "name": "e"}]}})

    c0_bruch = Fraction(3, 2)
    dirichlet = {}

    def roh(i, j, k):
        if (i, j, k) not in dirichlet:
            dirichlet[(i, j, k)] = Fraction(factorial(i) * factorial(j) * factorial(k), factorial(i + j + k + 3)) * c0_bruch ** (i + j + k + 3)
        return dirichlet[(i, j, k)]

    def zentriert(a, b, c):
        """int (x - 1)^a (y - 1)^b (z - 1)^c ueber die Ecke, exakt in Bruechen (binomische Entwicklung der Dirichlet-Formel)."""
        return float(sum(comb(a, i) * comb(b, j) * comb(c, k) * (-1) ** (a - i + b - j + c - k) * roh(i, j, k)
                         for i in range(a + 1) for j in range(b + 1) for k in range(c + 1)))

    volumen = c0 ** 3 / 6.0

    def monomfehler(Qd, q):
        """Groesste Abweichung der Regel von den exakten zentrierten Momenten, bezogen auf das Werkstoffvolumen: (alle Monome bis Grad q je Richtung,
        nur die bis zum Gesamtgrad 5)."""
        P, W, I = Qd.zelle(0)
        X = P[I] - 1.0
        alle = tief = 0.0
        for a in range(q + 1):
            for b in range(q + 1):
                for c in range(q + 1):
                    f = abs(float(np.sum(W[I] * X[:, 0] ** a * X[:, 1] ** b * X[:, 2] ** c)) - zentriert(a, b, c)) / volumen
                    alle = max(alle, f)
                    if a + b + c <= 5:
                        tief = max(tief, f)
        return alle, tief

    for p in (2, 3):
        G = Gitter(g, h=2.0, polster=0.0)
        G.moden_nummerieren(p)
        neu = Zellquadratur(G, p=p, alpha=0.0)
        alt = Zellquadratur(G, p=p, alpha=0.0, stuecke_exakt=False)
        ref = Zellquadratur(G, p=p, alpha=0.0, momentfitting=False, ordnung_tet=3 * p + 1)     # Tetraederregel exakt bis 6p + 1
        f_neu, _ = monomfehler(neu, 2 * p)
        f_alt, f_alt_tief = monomfehler(alt, 2 * p)
        K = {n: zellsteifigkeit(*zell_gradienten(G, Qd, 0), 210000.0, 0.3) for n, Qd in (("neu", neu), ("alt", alt), ("ref", ref))}
        dK_neu = float(np.abs(K["neu"] - K["ref"]).max() / np.abs(K["ref"]).max())
        dK_alt = float(np.abs(K["alt"] - K["ref"]).max() / np.abs(K["ref"]).max())
        # Schranken: gemessen 7e-16 (Monome) und 4e-15 (Zellmatrix) bei p 2 und p 3 - 1e-12 ist die Abnahmeschranke des Plans (O5, Regel 2)
        check(f"Eckzelle p {p}: eine Zelle, ein schraeges Stueck mit exakten Momenten ({len(neu.zelle(0)[1])} Punkte); alle zentrierten Monome bis Grad {2 * p} je "
              f"Richtung wie die Dirichlet-Formel ({f_neu:.1e} des Volumens < 1e-12), Zellmatrix wie die Tetraederregel der Ordnung {3 * p + 1} ({dK_neu:.1e} < 1e-12)",
              len(G.ijk) == 1 and neu.statistik["stuecke_exakt"] == 1 and neu.stuecke_exakt and f_neu < 1e-12 and dK_neu < 1e-12,
              f"Volumen {neu.volumen():.12f} (Soll {c0 ** 3 / 6:.12f})")
        # alter Weg: gemessen 2,5e-4 (p 2) und 2,6e-6 (p 3) in den Momenten, 3,6e-4 und 1,3e-5 in der Zellmatrix
        check(f"  alter Weg (stuecke_exakt=False) zum Vergleich: Monome bis Gesamtgrad 5 exakt ({f_alt_tief:.1e} < 1e-12), darueber falsch ({f_alt:.1e} > 1e-7), "
              f"Zellmatrix {dK_alt:.1e} neben der exakten (> 1e-6)",
              not alt.stuecke_exakt and "stuecke_exakt" not in alt.statistik and f_alt_tief < 1e-12 and f_alt > 1e-7 and dK_alt > 1e-6)
    # ohne Moment Fitting oder mit fit_grad < 2p bleibt die Tetraederregel (die gefittete Regel ist der Traeger der exakten Momente)
    G = Gitter(g, h=2.0, polster=0.0)
    G.moden_nummerieren(2)
    check("ohne Moment Fitting und mit fit_grad < 2p bleibt es bei der Tetraederregel (stuecke_exakt aus)",
          not Zellquadratur(G, p=2, momentfitting=False).stuecke_exakt and not Zellquadratur(G, p=2, fit_grad=2).stuecke_exakt
          and Zellquadratur(G, p=2).stuecke_exakt)


def test_verschachtelter_baum():
    """Verschachtelte CSG-Baeume (Plan TP 5 B3): ein T-Stoss als Vereinigung aus Grundblech, Querblech und zwei
    Kehlnaehten, jede Naht ein Schnitt aus Quader und 45-Grad-Halbraum. Vorher passte das auf keins der beiden flachen
    Muster, jedes Blatt fiel auf den Punkttest erster Ordnung (h 20: 18 401 Blaetter, Volumen +0,13 %, 2,6 Mio.
    Oberflaechenpunkte, 61 s). Jetzt ueber den Baum: kein Punkttest-Blatt, Volumen exakt (133 200 mm3 = 200*50*10 +
    10*50*60 + 2*50*8*8/2, < 1e-12), jede Flaeche exakt (< 1e-11) auf drei Gittern."""
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.fcm.quadratur import Zellquadratur
    from volumen3d.geometry.oberflaeche import Flaechenquadratur
    from volumen3d.tests.test_hotspot import t_stoss
    geo = t_stoss()
    v_soll = 200 * 50 * 10 + 10 * 50 * 60 + 2 * 50 * 8 * 8 / 2
    a_soll = {"grundblech": 2 * 200 * 50 - 26 * 50 + 2 * 200 * 10 + 2 * 50 * 10, "querblech": 10 * 50 + 2 * 10 * 60 + 2 * 52 * 50,
              "naht_links": 2 * 32.0, "naht_rechts": 2 * 32.0, "nahtflaeche_links": 8 * np.sqrt(2) * 50, "nahtflaeche_rechts": 8 * np.sqrt(2) * 50}
    for h in (20.0, 10.0, 7.0):
        t = time.perf_counter()
        G = Gitter(geo, h=h, polster=0.1)
        G.moden_nummerieren(3)
        Q = Zellquadratur(G, p=3, alpha=0.0)
        v = Q.volumen()
        o = Flaechenquadratur.aus_geometrie(geo, G, 5)
        nm = o.name.astype(str)
        fa = max(abs(float(o.gewichte[nm == n].sum()) - a) / a for n, a in a_soll.items())
        check(f"T-Stoss h {h:g}: kein Punkttest-Blatt, Volumen exakt (< 1e-12), alle sechs Flaechen exakt (< 1e-11), kein Flaechenrueckfall",
              Q.statistik["blaetter_punkttest"] == 0 and abs(v - v_soll) / v_soll < 1e-12 and fa < 1e-11 and o.statistik["rueckfall"] == 0,
              f"Volumen {v:.6f}, Flaechen {fa:.1e}, {Q.statistik['blaetter_eben']} ebene Blaetter, {len(o.punkte)} Oberflaechenpunkte, "
              f"{time.perf_counter() - t:.1f} s")


def test_innere_trennflaeche():
    """Befund aus C1 (Plan TP 5, 01.10.2026): Knotenblech (Quader) in einem Nahtstumpf (Quader ∩ vier 45-Grad-Halbraeume), vereinigt.
    Die Seitenflaechen des Knotenblechs laufen unterhalb der Nahtoberflaeche durch das Innere des Stumpfs; die Probenpruefung in
    Csg._baum_stuecke zaehlte Proben genau auf dieser inneren Trennflaeche in zwei abgeschlossenen Stuecken (Knotenblech und
    Stumpf minus Knotenblech) doppelt und verwarf die Zerlegung: 1 534 Flaechenstuecke im Rueckfall, Oberflaeche 8 382,7 statt
    7 901,6 mm2 (die Deckflaeche des Stumpfs im Inneren blieb stehen), Integrationswarnung. Geschlossene Form: Boden 72*20,
    Mantel des Prismatoids 2*(72+60)/2*6*sqrt2 + 2*(20+8)/2*6*sqrt2, Knotenblech ueber z 6: 2*60*34 + 2*8*34 + 60*8;
    Volumen ueber die Prismatoidformel h/6 (A1 + 4 Am + A2) = 5 616 plus 60*8*34."""
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.fcm.quadratur import Zellquadratur
    from volumen3d.geometry.csg import aus_params
    from volumen3d.geometry.oberflaeche import Flaechenquadratur
    geo = aus_params({"csg": {"typ": "vereinigung", "teile": [
        {"typ": "quader", "min": [70, 36, 0], "max": [130, 44, 40], "name": "knotenblech"},
        {"typ": "schnitt", "teile": [{"typ": "quader", "min": [64, 30, 0], "max": [136, 50, 6], "name": "naht"},
                                     {"typ": "halbraum", "punkt": [136, 0, 0], "normale": [1, 0, 1], "name": "f0"},
                                     {"typ": "halbraum", "punkt": [64, 0, 0], "normale": [-1, 0, 1], "name": "f1"},
                                     {"typ": "halbraum", "punkt": [0, 50, 0], "normale": [0, 1, 1], "name": "f2"},
                                     {"typ": "halbraum", "punkt": [0, 30, 0], "normale": [0, -1, 1], "name": "f3"}]}]}})
    s2 = np.sqrt(2.0)
    a_soll = 72 * 20 + (72 + 60) * 6 * s2 + (20 + 8) * 6 * s2 + 2 * 60 * 34 + 2 * 8 * 34 + 60 * 8
    v_soll = 6 / 6 * (72 * 20 + 4 * 66 * 14 + 60 * 8) + 60 * 8 * 34
    for h in (10.0, 5.0):
        G = Gitter(geo, h=h)
        Q = Zellquadratur(G, p=2, alpha=0.0)
        v = Q.volumen()
        o = Flaechenquadratur.aus_geometrie(geo, G, 3)
        a = float(o.gewichte.sum())
        check(f"Knotenblech im Nahtstumpf h {h:g}: Oberflaeche {a:.3f} = {a_soll:.3f} (< 1e-9), kein Flaechenrueckfall, Volumen {v:.3f} = {v_soll:.0f} (< 1e-12), kein Punkttest",
              abs(a / a_soll - 1) < 1e-9 and o.statistik["rueckfall"] == 0 and abs(v / v_soll - 1) < 1e-12 and Q.statistik["blaetter_punkttest"] == 0,
              f"{o.statistik}, {len(o.punkte)} Punkte")


def test_deckungsgleiche_flaechen():
    """Befund G1-1 (Gutachten C2, 02.10.2026): die C1-Kur fuer deckungsgleiche Flaechen (zwei Formen stehen auf derselben Ebene) half nur
    im Baumweg; auf dem flachen Vereinigungsweg (Quader + Quader) zaehlte der Boden doppelt oder teilweise doppelt, abhaengig von der
    Reihenfolge der Formen und der Gitterphase (Boden 1 756 bis 1 880 statt 1 600 mm2), und eine wieder aufgefuellte Tasche behielt einen
    Scheindeckel. Geschlossene Formen der Oberflaeche, je zwei Reihenfolgen und drei Zellgroessen:
    (a) A = [0,40]^2 x [0,10] ∪ B = [12,28]^2 x [0,20]: 1 600 + 1 344 + 1 600 + 640 + 256 = 5 440;
    (b) Knotenblech [70,130] x [36,44] x [0,40] ∪ Nahtquader [64,136] x [30,50] x [0,6]: 1 440 + 1 104 + 960 + 4 624 + 480 = 8 608;
    (c) (C − B) ∪ A mit C = [0,40]^2 x [0,10], Tasche B = [10,30]^2 x [5,11], Fuellung A = [10,20] x [10,30] x [5,10]: 5 100, davon auf z = 10 1 400."""
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.geometry.csg import aus_params
    from volumen3d.geometry.oberflaeche import Flaechenquadratur
    def q(lo, hi, name):
        return {"typ": "quader", "min": lo, "max": hi, "name": name}
    faelle = [
        ("a", [q([0, 0, 0], [40, 40, 10], "A"), q([12, 12, 0], [28, 28, 20], "B")], "vereinigung", 5440.0, None),
        ("b", [q([70, 36, 0], [130, 44, 40], "K"), q([64, 30, 0], [136, 50, 6], "N")], "vereinigung", 8608.0, None),
    ]
    zeilen, ok = [], True
    for name, teile, op, soll, _ in faelle:
        for reihe in (teile, teile[::-1]):
            g = aus_params({"csg": {"typ": op, "teile": reihe}})
            for h in (10.0, 7.0, 4.3):
                o = Flaechenquadratur.aus_geometrie(g, Gitter(g, h=h), 3)
                a = float(o.gewichte.sum())
                ok &= abs(a / soll - 1) < 1e-9
                zeilen.append(f"{name} {[t['name'] for t in reihe]} h {h:g}: {a:.3f}")
    tasche = {"typ": "vereinigung", "teile": [{"typ": "differenz", "teile": [q([0, 0, 0], [40, 40, 10], "C"), q([10, 10, 5], [30, 30, 11], "B")]},
                                               q([10, 10, 5], [20, 30, 10], "A")]}
    # (d) dieselbe Tasche buendig (Deckel der Tasche B deckungsgleich mit dem von C, Fall des Gutachtens): C = [0,40]^2 x [0,10],
    # B = [10,20]^2 x [5,10], A = [10,15] x [10,20] x [5,10] -> 4 950, davon auf z = 10 1 550 (vorher Scheindeckel 1 600)
    buendig = {"typ": "vereinigung", "teile": [{"typ": "differenz", "teile": [q([0, 0, 0], [40, 40, 10], "C"), q([10, 10, 5], [20, 20, 10], "B")]},
                                                q([10, 10, 5], [15, 20, 10], "A")]}
    for name, g_par, soll, soll_oben in (("c", tasche, 5100.0, 1400.0), ("c", {"typ": "vereinigung", "teile": tasche["teile"][::-1]}, 5100.0, 1400.0),
                                         ("d", buendig, 4950.0, 1550.0), ("d", {"typ": "vereinigung", "teile": buendig["teile"][::-1]}, 4950.0, 1550.0)):
        g = aus_params({"csg": g_par})
        for h in (10.0, 7.0, 4.3):
            o = Flaechenquadratur.aus_geometrie(g, Gitter(g, h=h), 3)
            a = float(o.gewichte.sum())
            oben = float(o.gewichte[(np.abs(o.punkte[:, 2] - 10.0) < 1e-9) & (o.normalen[:, 2] > 0.999)].sum())
            ok &= abs(a / soll - 1) < 1e-9 and abs(oben / soll_oben - 1) < 1e-9
            zeilen.append(f"{name} h {h:g}: {a:.3f} (z 10: {oben:.3f})")
    check("deckungsgleiche Flaechen auf dem flachen Weg: Oberflaechen exakt (1e-9), unabhaengig von Reihenfolge und Zellgroesse; aufgefuellte Tasche ohne Scheindeckel",
          ok, "; ".join(zeilen))


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
    sys.exit(lauf([test_innere_trennflaeche, test_deckungsgleiche_flaechen, test_polyeder, test_ebene_geometrie_exakt, test_kugel_zweite_ordnung, test_lochplatte, test_kleine_radien, test_inside_zelle, test_momentfitting, test_verschachtelter_baum]))
