"""Konvexe Polyeder: Box gegen Halbraeume clippen, in Tetraeder zerlegen, exakt integrieren.

Grundlage der ebenen-exakten Schnittzellen-Integration (Entwurf 3.5). Ein Polyeder ist eine
Liste ebener Flaechenpolygone (k,3); Clippen gegen den Halbraum (x - p) . n <= 0 schneidet
jede Flaeche (Sutherland-Hodgman) und schliesst das Loch mit dem Deckelpolygon aus den
Schnittkanten. Tetraeder entstehen vom Schwerpunkt aus ueber Faecher der Flaechen; darauf
integriert die konische Produktregel (Gauss-Jacobi in u und v, Gauss-Legendre in w) mit n
Punkten je Richtung Polynome bis zum Gesamtgrad 2n-1 exakt - nur positive Gewichte.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.polynomial import legendre as L
from scipy.special import roots_jacobi


def box_flaechen(lo, hi) -> list[np.ndarray]:
    lo = np.asarray(lo, float)
    hi = np.asarray(hi, float)
    V = np.array([[lo[0], lo[1], lo[2]], [hi[0], lo[1], lo[2]], [hi[0], hi[1], lo[2]], [lo[0], hi[1], lo[2]],
                  [lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]], [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]]])
    seiten = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return [V[list(s)] for s in seiten]


def polygon_clippen(F: np.ndarray, p, n, tol: float) -> tuple[np.ndarray, list[np.ndarray]]:
    """Ein Polygon gegen (x-p).n <= 0; liefert das Restpolygon und die neuen Schnittpunkte."""
    d = (F - p) @ n
    if np.all(d <= tol):
        return F, []
    if np.all(d >= -tol):
        return np.zeros((0, 3)), []
    neu, schnitt = [], []
    k = len(F)
    for i in range(k):
        a, b = F[i], F[(i + 1) % k]
        da, db = d[i], d[(i + 1) % k]
        if da <= 0:
            neu.append(a)
        if (da <= 0) != (db <= 0):
            s = da / (da - db)
            q = a + s * (b - a)
            neu.append(q)
            schnitt.append(q)
    return np.asarray(neu).reshape(-1, 3), schnitt


def clippen(flaechen: list[np.ndarray], p, n, tol: float = 1e-12) -> list[np.ndarray]:
    """Konvexes Polyeder gegen den Halbraum (x-p).n <= 0 clippen (leer -> [])."""
    p = np.asarray(p, float)
    n = np.asarray(n, float)
    neu: list[np.ndarray] = []
    kanten: list[np.ndarray] = []
    for F in flaechen:
        G, s = polygon_clippen(F, p, n, tol)
        if len(G) >= 3:
            neu.append(G)
        kanten += s
    if not neu:
        return []
    if len(kanten) >= 3:
        K = np.asarray(kanten)
        c = K.mean(axis=0)
        hilfe = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
        u = np.cross(n, hilfe)
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        w = np.arctan2((K - c) @ v, (K - c) @ u)
        K = K[np.argsort(w)]
        # doppelte Punkte (jede Schnittkante liefert ihre Endpunkte zweimal) entfernen
        behalten = [0]
        for i in range(1, len(K)):
            if np.linalg.norm(K[i] - K[behalten[-1]]) > 1e-9 * (1 + np.abs(K).max()):
                behalten.append(i)
        if len(behalten) > 1 and np.linalg.norm(K[behalten[-1]] - K[behalten[0]]) <= 1e-9 * (1 + np.abs(K).max()):
            behalten.pop()
        if len(behalten) >= 3:
            neu.append(K[behalten])
    return neu


def tetraeder(flaechen: list[np.ndarray]) -> np.ndarray:
    """(t,4,3): Faecher jeder Flaeche mit dem Schwerpunkt aller Ecken als Spitze."""
    if not flaechen:
        return np.zeros((0, 4, 3))
    c = np.concatenate(flaechen).mean(axis=0)
    T = []
    for F in flaechen:
        for i in range(1, len(F) - 1):
            T.append([c, F[0], F[i], F[i + 1]])
    return np.asarray(T)


def volumen(flaechen: list[np.ndarray]) -> float:
    T = tetraeder(flaechen)
    if len(T) == 0:
        return 0.0
    return float(np.abs(np.linalg.det(T[:, 1:] - T[:, :1])).sum() / 6.0)


@lru_cache(maxsize=None)
def tet_regel(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Konische Produktregel auf dem Einheitstetraeder (0,0,0),(1,0,0),(0,1,0),(0,0,1):
    (n^3,3) Punkte, (n^3,) Gewichte mit Summe 1/6, exakt bis Gesamtgrad 2n-1.

    Kollaps x = u, y = v(1-u), z = w(1-u)(1-v) mit Jacobi-Determinante (1-u)^2 (1-v); die
    Faktoren (1-u)^2 und (1-v) uebernehmen Gauss-Jacobi-Regeln (alpha = 2 bzw. 1), w bleibt
    Gauss-Legendre. So bleibt die Regel fuer Polynome exakt und alle Gewichte positiv.
    """
    tu, wu = roots_jacobi(n, 2.0, 0.0)
    tv, wv = roots_jacobi(n, 1.0, 0.0)
    tw, ww = L.leggauss(n)
    u, v, w = 0.5 * (tu + 1), 0.5 * (tv + 1), 0.5 * (tw + 1)
    wu, wv, ww = wu / 8.0, wv / 4.0, ww / 2.0
    U, Vv, Ww = np.meshgrid(u, v, w, indexing="ij")
    X = np.stack([U.ravel(), (Vv * (1 - U)).ravel(), (Ww * (1 - U) * (1 - Vv)).ravel()], axis=1)
    W = (wu[:, None, None] * wv[None, :, None] * ww[None, None, :]).ravel()
    return X, W


def polyeder_quadratur(flaechen: list[np.ndarray], n: int) -> tuple[np.ndarray, np.ndarray]:
    """Punkte (m,3) und Gewichte (m,) fuer das konvexe Polyeder (Summe der Gewichte = Volumen)."""
    T = tetraeder(flaechen)
    if len(T) == 0:
        return np.zeros((0, 3)), np.zeros(0)
    X, W = tet_regel(n)
    J = T[:, 1:] - T[:, :1]                                     # (t,3,3) Kantenvektoren
    det = np.abs(np.linalg.det(J))
    P = T[:, None, 0, :] + np.einsum("qk,tkd->tqd", X, J)       # (t,q,3)
    Wt = W[None, :] * det[:, None]
    return P.reshape(-1, 3), Wt.ravel()


__all__ = ["box_flaechen", "polygon_clippen", "clippen", "tetraeder", "volumen", "tet_regel", "polyeder_quadratur"]
