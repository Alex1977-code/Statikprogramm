"""T1: Basisfunktionen. Orthonormalitaet der Ableitungen, Partition der Eins, Ableitungen
gegen zentrale Differenzen, Modenklassen, Gauss-Genauigkeit.

Aufruf: python -m volumen3d.tests.test_basis
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402


def test_1d():
    from volumen3d.fcm.basis import gauss_1d, legendre_1d
    p = 4
    x, w = gauss_1d(p + 2)
    N, dN = legendre_1d(p, x)
    check("Formen (n,p+1)", N.shape == (p + 2, p + 1) and dN.shape == N.shape)
    check("Eckmoden: Partition der Eins", np.allclose(N[:, 0] + N[:, 1], 1.0, atol=1e-14))
    G = (dN[:, 2:] * w[:, None]).T @ dN[:, 2:]
    check("int phi_i' phi_j' = delta_ij (hoehere Moden)", np.allclose(G, np.eye(p - 1), atol=1e-12),
          f"max {np.abs(G - np.eye(p - 1)).max():.1e}")
    check("hoehere Moden verschwinden an +-1",
          np.allclose(legendre_1d(p, np.array([-1.0, 1.0]))[0][:, 2:], 0.0, atol=1e-14))
    h = 1e-6
    Np, _ = legendre_1d(p, x + h)
    Nm, _ = legendre_1d(p, x - h)
    check("Ableitung gegen zentrale Differenz", np.allclose((Np - Nm) / (2 * h), dN, atol=1e-8))
    # p = 1: nur die beiden linearen Moden
    N1, dN1 = legendre_1d(1, np.array([0.0]))
    check("p=1: nur lineare Moden, Werte 1/2", N1.shape == (1, 2) and np.allclose(N1, 0.5))


def test_3d():
    from volumen3d.fcm.basis import anzahl_moden, basis_3d, modenklassen
    p = 3
    kl = modenklassen(p)
    zahl = np.bincount(kl["klasse"], minlength=4)
    check("Modenklassen 8 Ecken, 12(p-1) Kanten, 6(p-1)^2 Flaechen, (p-1)^3 innen",
          list(zahl) == [8, 12 * (p - 1), 6 * (p - 1) ** 2, (p - 1) ** 3], str(zahl))
    check("anzahl_moden = (p+1)^3", anzahl_moden(p) == (p + 1) ** 3)
    xi = np.random.default_rng(0).uniform(-1, 1, (7, 3))
    N, dN = basis_3d(p, xi)
    check("Formen (n,m), (n,m,3)", N.shape == (7, 64) and dN.shape == (7, 64, 3))
    check("Eckmoden summieren zu 1", np.allclose(N[:, kl["klasse"] == 0].sum(axis=1), 1.0))
    h = 1e-6
    for d in range(3):
        e = np.zeros(3)
        e[d] = h
        num = (basis_3d(p, xi + e)[0] - basis_3d(p, xi - e)[0]) / (2 * h)
        check(f"Gradient Richtung {d} gegen zentrale Differenz", np.allclose(num, dN[:, :, d], atol=1e-7))
    # Eckmode (0,0,0) ist an der Ecke (-1,-1,-1) gleich 1 und an allen anderen Ecken 0
    ecken = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], float)
    Ne, _ = basis_3d(p, ecken)
    check("Eckmode 0 ist 1 an (-1,-1,-1), sonst 0", Ne[0, 0] == 1.0 and np.allclose(Ne[1:, 0], 0.0))


def test_gauss():
    from volumen3d.fcm.basis import gauss_1d, gauss_3d
    for n in (2, 4, 5):
        x, w = gauss_1d(n)
        grad = 2 * n - 1
        exakt = 2.0 / (grad + 1) if grad % 2 == 0 else 0.0
        check(f"Gauss {n} integriert x^{grad} exakt", abs((w * x ** grad).sum() - exakt) < 1e-13)
        # und x^(2n) nicht mehr exakt (Gegenprobe der Ordnung)
        check(f"Gauss {n} integriert x^{2 * n} nicht exakt", abs((w * x ** (2 * n)).sum() - 2.0 / (2 * n + 1)) > 1e-6)
    X, W = gauss_3d(3)
    check("gauss_3d: 27 Punkte, Summe Gewichte 8", X.shape == (27, 3) and abs(W.sum() - 8.0) < 1e-13)


if __name__ == "__main__":
    sys.exit(lauf([test_1d, test_3d, test_gauss]))
