"""Teilprojekt 6a Phase 1: residuenbasierter Fehlerschaetzer (fcm/schaetzer.py), Plan 2026-10-06-tp6a-phase1-schaetzer.md.

Aufruf: python -m volumen3d.tests.test_schaetzer
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402


def test_hesse():
    """Hesse-Matrizen der Basis gegen den zentralen Differenzenquotienten der Gradienten; 1D geschlossen: N_j'' = sqrt((2j-1)/2) P'_{j-1}."""
    from volumen3d.fcm.basis import basis_3d, basis_3d_hesse, legendre_1d_d2
    rng = np.random.default_rng(3)
    xi = rng.uniform(-0.9, 0.9, (40, 3))
    for p in (1, 2, 3, 4):
        H = basis_3d_hesse(p, xi)
        d = 1e-5
        fd = np.empty_like(H)
        for b in range(3):
            e = np.zeros(3)
            e[b] = d
            _, dp = basis_3d(p, xi + e)
            _, dm = basis_3d(p, xi - e)
            fd[:, :, :, b] = (dp - dm) / (2 * d)
        rel = float(np.abs(H - fd).max() / max(float(np.abs(H).max()), 1.0))
        check(f"p {p}: Hesse-Matrizen gegen Differenzenquotient der Gradienten ({rel:.1e} < 1e-7), symmetrisch",
              rel < 1e-7 and np.allclose(H, H.transpose(0, 1, 3, 2)))
    x = rng.uniform(-1, 1, 20)
    d2 = legendre_1d_d2(4, x)
    check("1D geschlossen: N_0'' = N_1'' = 0, N_2'' = sqrt(3/2), N_3'' = sqrt(5/2) 3x, N_4'' = sqrt(7/2) (15x^2 - 3)/2",
          not d2[:, :2].any() and np.allclose(d2[:, 2], np.sqrt(1.5)) and np.allclose(d2[:, 3], np.sqrt(2.5) * 3 * x)
          and np.allclose(d2[:, 4], np.sqrt(3.5) * (15 * x ** 2 - 3) / 2))


def _wuerfel(p=1, h=50.0):
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "q"}})
    return FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(210000.0, 0.3))


def test_lasten_aufgezeichnet():
    """Der Schaetzer braucht die Soll-Traktion je Oberflaechenpunkt und die Volumenlast; das Problem zeichnet sie neben dem Lastvektor auf."""
    pr = _wuerfel()
    pr.druck("q", 5.0)
    pr.volumenlast([0.0, 0.0, -7.85e-5])
    fq, T = pr.flaechenlasten[-1]
    check("druck: aufgezeichnete Traktion = -p n an allen Punkten, Volumenlast aufgezeichnet",
          len(pr.flaechenlasten) == 1 and np.allclose(T, -5.0 * fq.normalen) and len(fq.punkte) == len(pr.oberflaeche.punkte)
          and len(pr.volumenlasten) == 1 and np.allclose(pr.volumenlasten[0], [0.0, 0.0, -7.85e-5]))


def test_flaechen_paare():
    """Jede Flaeche zwischen zwei aktiven Zellen genau einmal, von der feineren Zelle aus; unabhaengige Gegenprobe ueber die Zellboxen (alle Paare mit
    gemeinsamer Flaeche positiven Inhalts)."""
    from volumen3d.fcm.gitter import Verfeinerung
    from volumen3d.fcm.schaetzer import flaechen_paare
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "q"}})
    pr = FcmProblem(g, h=25.0, p=1, werkstoff=Werkstoff(210000.0, 0.3), verfeinerung=Verfeinerung(bereiche=((np.zeros(3), 30.0, 12.5),)))
    G = pr.gitter
    paare = flaechen_paare(G)
    lo, hi = G.zellbox(np.arange(len(G.ijk)))
    tol = 1e-9 * G.h
    brute = set()
    for c in range(len(G.ijk)):
        for k in range(c + 1, len(G.ijk)):
            for a in range(3):
                b, d = [x for x in range(3) if x != a]
                beruehrt = abs(hi[c, a] - lo[k, a]) < tol or abs(hi[k, a] - lo[c, a]) < tol
                ueber = all(min(hi[c, x], hi[k, x]) - max(lo[c, x], lo[k, x]) > tol for x in (b, d))
                if beruehrt and ueber:
                    brute.add((c, k))
    gefunden = {(min(c, k), max(c, k)) for c, k, _, _ in paare}
    feiner = all(G.ebene[c] >= G.ebene[k] for c, k, _, _ in paare)
    check(f"flaechen_paare: {len(paare)} Paare, gleich der Gegenprobe ueber die Boxen ({len(brute)}), keine doppelt, immer von der feineren Zelle aus",
          gefunden == brute and len(paare) == len(gefunden) and feiner and len(set(G.ebene)) > 1)


def test_flaechen_punkte():
    """Werkstoffanteil einer Zellflaeche: ganz im Werkstoff exakt die Flaeche; schraeg geschnitten auf erste Ordnung gegen das exakt geclippte Polygon."""
    from volumen3d.fcm.schaetzer import flaechen_paare, flaechen_punkte
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    from volumen3d.geometry.polyeder import polygon_clippen
    pkt, nrm = np.array([50.0, 50.0, 50.0]), np.array([1.0, 0.5, 0.0])
    g = aus_params({"csg": {"typ": "schnitt", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "q"},
                                                         {"typ": "halbraum", "punkt": list(pkt), "normale": list(nrm), "name": "s"}]}})
    G = FcmProblem(g, h=25.0, p=1, werkstoff=Werkstoff(210000.0, 0.3)).gitter
    voll = schraeg = 0
    fehler = 0.0
    for c, k, achse, seite in flaechen_paare(G):
        lo, hi = G.zellbox(int(c))
        a, b = [d for d in range(3) if d != achse]
        flaeche = (hi[a] - lo[a]) * (hi[b] - lo[b])
        ebene = hi[achse] if seite > 0 else lo[achse]
        ecken = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
        Q = np.empty((4, 3))
        Q[:, achse] = ebene
        Q[:, a] = lo[a] + ecken[:, 0] * (hi[a] - lo[a])
        Q[:, b] = lo[b] + ecken[:, 1] * (hi[b] - lo[b])
        # exakter Werkstoffanteil: Flaeche gegen den Halbraum und die sechs Quaderseiten clippen (polygon_clippen behaelt (x - p).n <= 0)
        R, _ = polygon_clippen(Q, pkt, nrm / np.linalg.norm(nrm), 1e-12)
        for x0, n0 in ((np.array([0.0, 0, 0]), np.array([-1.0, 0, 0])), (np.array([100.0, 0, 0]), np.array([1.0, 0, 0])),
                       (np.array([0.0, 0, 0]), np.array([0, -1.0, 0])), (np.array([0, 100.0, 0]), np.array([0, 1.0, 0])),
                       (np.array([0, 0, 0.0]), np.array([0, 0, -1.0])), (np.array([0, 0, 100.0]), np.array([0, 0, 1.0]))):
            if len(R) >= 3:
                R, _ = polygon_clippen(R, x0, n0, 1e-12)
        exakt = 0.5 * float(np.linalg.norm(np.cross(R[1:-1] - R[0], R[2:] - R[0]).sum(axis=0))) if len(R) >= 3 else 0.0
        P, W = flaechen_punkte(G, c, achse, seite, 2, tiefe=2)
        if abs(exakt - flaeche) < 1e-9 * flaeche:
            voll += 1
            fehler = max(fehler, abs(float(W.sum()) - flaeche) / flaeche)
        elif exakt > 0:
            # erste Ordnung: eine Gerade schneidet hoechstens 2 * 2^tiefe der 2^tiefe x 2^tiefe Unterquadrate, jedes irrt hoechstens um seine Flaeche
            schraeg += 1
            if abs(float(W.sum()) - exakt) > 2.0 * flaeche / 2 ** 2:
                fehler = max(fehler, 1.0)
    check(f"flaechen_punkte: {voll} Flaechen ganz im Werkstoff exakt ({fehler:.1e} < 1e-12), {schraeg} geschnittene innerhalb der Schranke erster Ordnung",
          voll > 0 and schraeg > 0 and fehler < 1e-12)


if __name__ == "__main__":
    sys.exit(lauf([test_hesse, test_lasten_aufgezeichnet, test_flaechen_paare, test_flaechen_punkte]))
