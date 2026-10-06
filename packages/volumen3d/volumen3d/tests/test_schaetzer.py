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


if __name__ == "__main__":
    sys.exit(lauf([test_hesse, test_lasten_aufgezeichnet]))
