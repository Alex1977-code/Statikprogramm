"""Hierarchische Ansatzfunktionen aus integrierten Legendre-Polynomen (Vorgabe Abschnitt 5).

1D: N1 = (1-xi)/2, N2 = (1+xi)/2 und fuer j = 2..p
    N_{j+1} = phi_j(xi) = (P_j(xi) - P_{j-2}(xi)) / sqrt(2 (2j-1)),
    phi_j'(xi) = sqrt((2j-1)/2) P_{j-1}(xi)     (Identitaet P_j' - P_{j-2}' = (2j-1) P_{j-1}).

Damit ist int_{-1}^{1} phi_i' phi_j' dxi = delta_ij: die 1D-Steifigkeit der hoeheren Moden ist
die Einheitsmatrix, und phi_j(+-1) = 0, sodass nur die beiden linearen Moden an den Ecken
haengen; die hoeheren gehoeren zu Kanten, Flaechen und Zellinnerem. Die Normierung mit
sqrt(2(2j-1)) haelt die Zellmatrizen fuer p <= 4 gut konditioniert.

3D als volles Tensorprodukt (Entwurf 3.3): Mode (a,b,c) mit a,b,c in 0..p, Index
a*(p+1)^2 + b*(p+1) + c, N = N_a(xi) N_b(eta) N_c(zeta). Die Klasse eines Modes ist die
Anzahl der Richtungen mit Index >= 2 (0 Ecke, 1 Kante, 2 Flaeche, 3 innen).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.polynomial import legendre as L


def legendre_1d(p: int, xi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Werte N (n,p+1) und Ableitungen dN/dxi (n,p+1) der 1D-Basis vom Grad p."""
    xi = np.asarray(xi, float).ravel()
    n = len(xi)
    N = np.empty((n, p + 1))
    dN = np.empty((n, p + 1))
    N[:, 0] = 0.5 * (1.0 - xi)
    dN[:, 0] = -0.5
    N[:, 1] = 0.5 * (1.0 + xi)
    dN[:, 1] = 0.5
    if p >= 2:
        P = L.legvander(xi, p)                       # Spalte j = P_j(xi)
        for j in range(2, p + 1):
            N[:, j] = (P[:, j] - P[:, j - 2]) / np.sqrt(2.0 * (2 * j - 1))
            dN[:, j] = np.sqrt((2 * j - 1) / 2.0) * P[:, j - 1]
    return N, dN


def anzahl_moden(p: int) -> int:
    return (p + 1) ** 3


@lru_cache(maxsize=None)
def _indizes(p: int) -> np.ndarray:
    a, b, c = np.meshgrid(np.arange(p + 1), np.arange(p + 1), np.arange(p + 1), indexing="ij")
    return np.stack([a.ravel(), b.ravel(), c.ravel()], axis=1)


@lru_cache(maxsize=None)
def modenklassen(p: int) -> dict[str, np.ndarray]:
    """Je Mode: 'abc' (m,3) Indizes, 'hoch' (m,3) Index >= 2, 'klasse' (m,) 0 Ecke / 1 Kante /
    2 Flaeche / 3 innen."""
    abc = _indizes(p)
    hoch = abc >= 2
    return {"abc": abc, "hoch": hoch, "klasse": hoch.sum(axis=1)}


def basis_3d(p: int, xi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """N (n,m) und dN/dxi (n,m,3) an Referenzpunkten xi (n,3) in [-1,1]^3, m = (p+1)^3."""
    xi = np.asarray(xi, float).reshape(-1, 3)
    n = len(xi)
    Na, da = legendre_1d(p, xi[:, 0])
    Nb, db = legendre_1d(p, xi[:, 1])
    Nc, dc = legendre_1d(p, xi[:, 2])
    # Tensorprodukt per Broadcasting in der Reihenfolge von _indizes (a langsam, c schnell) statt
    # neun indizierter Kopien (n, m): Schnittzellen-Zellmatrizen Kirsch h 20 p 3 3,5 s -> siehe
    # Theorie 11.10 (28.09.2026); gleiche Produkte, Unterschied nur in der Rundungsreihenfolge
    if p <= 1:                                        # bei p = 1 sind die Kopien billiger (0,54 gegen 1,21 ms)
        abc = _indizes(p)
        A, B, C = abc[:, 0], abc[:, 1], abc[:, 2]
        return (Na[:, A] * Nb[:, B] * Nc[:, C],
                np.stack([da[:, A] * Nb[:, B] * Nc[:, C], Na[:, A] * db[:, B] * Nc[:, C], Na[:, A] * Nb[:, B] * dc[:, C]], axis=2))
    a = Na[:, :, None, None]
    b = Nb[:, None, :, None]
    c = Nc[:, None, None, :]
    bc = b * c
    m = (p + 1) ** 3                                  # explizit: reshape(0, -1) scheitert bei Zellen ohne Punkte
    N = (a * bc).reshape(n, m)
    dN = np.empty((n, m, 3))
    dN[:, :, 0] = (da[:, :, None, None] * bc).reshape(n, m)
    dN[:, :, 1] = ((a * c) * db[:, None, :, None]).reshape(n, m)
    dN[:, :, 2] = ((a * b) * dc[:, None, None, :]).reshape(n, m)
    return N, dN


@lru_cache(maxsize=None)
def gauss_1d(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Gauss-Legendre mit n Punkten auf [-1,1]: exakt bis Grad 2n-1."""
    x, w = L.leggauss(n)
    return x, w


@lru_cache(maxsize=None)
def gauss_3d(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Tensor-Gauss: (n^3,3) Punkte und (n^3,) Gewichte auf [-1,1]^3 (Summe 8)."""
    x, w = gauss_1d(n)
    X = np.stack(np.meshgrid(x, x, x, indexing="ij"), axis=-1).reshape(-1, 3)
    W = (w[:, None, None] * w[None, :, None] * w[None, None, :]).ravel()
    return X, W


__all__ = ["legendre_1d", "anzahl_moden", "modenklassen", "basis_3d", "gauss_1d", "gauss_3d"]
