"""Exakte Integration tessellierter Huellen ueber den Divergenzsatz (Plan TP 5 B6, Theorie 11.16).

Fuer eine achsparallele Zelle B = [lo, hi] und eine geschlossene, nach aussen orientierte Huelle Omega (Dreiecke) gilt mit
G = (G_x, 0, 0), G_x(x, y, z) = int_{x_lo}^{x} g(x', y, z) chi_B(x', y, z) dx' fuer polynomiales g

    int_{Omega ∩ B} g dV = sum ueber die Dreiecke T von int_T G_x n_x dA.

Begruendung: div G = g chi_B im Sinne der Distributionen, G_x ist in x stetig (Integral einer beschraenkten Funktion), und die
Spruenge von G ueber die Ebenen y = y_lo, y_hi, z = z_lo, z_hi haben keinen Fluss, weil ihre Normale senkrecht zu G steht.
Der Gaussche Satz ueber Omega braucht darum nur den Rand von Omega - die Dreiecke -, nicht den Werkstoffteil der Zellflaechen.
Je Dreieck genuegt das Clippen an den y- und z-Scheiben der Zelle und das Teilen bei x_lo und x_hi: Teile mit x < x_lo tragen
null, Teile mit x > x_hi den vollen Wert int_{x_lo}^{x_hi} g dx' (konstant in x). Alles sind exakte Polygonoperationen; die
Zerlegung an lokalen Ebenen (csg.lokale_stuecke) und der Punkttest entfallen fuer Huellen.

Momente der Tensor-Legendre-Basis vom Grad q (fcm/basis.legendre_1d) in den Referenzkoordinaten xi der Zelle: mit
S_a(xi) = int_{-1}^{xi} N_a ist G_x = (h/2) S_a(xi(x)) N_b(eta) N_c(zeta) (geklemmt auf [-1, 1] in xi). Der Integrand auf einem
ebenen Polygonstueck ist ein Polynom vom Gesamtgrad hoechstens 3q + 1; die Faecherdreiecke mit der kollabierten Gauss-Jacobi-Regel
(oberflaeche.dreieck_gauss, exakt bis 2n - 1) integrieren ihn exakt.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.polynomial import legendre as L

from ..fcm.basis import legendre_1d
from .polyeder import polygon_clippen


def legendre_1d_stamm(q: int, xi: np.ndarray) -> np.ndarray:
    """S (n, q+1) mit S[:, a] = int_{-1}^{xi} N_a(t) dt fuer die hierarchische 1D-Basis vom Grad q.

    N_0 = (1 - t)/2 -> S_0 = xi/2 - xi^2/4 + 3/4; N_1 = (1 + t)/2 -> S_1 = xi/2 + xi^2/4 + 1/4;
    N_j = (P_j - P_{j-2}) / sqrt(2 (2j - 1)) fuer j >= 2 mit int_{-1}^{xi} P_k = (P_{k+1} - P_{k-1}) / (2k + 1) (k >= 1),
    int_{-1}^{xi} P_0 = xi + 1 (die Randterme bei -1 heben sich auf)."""
    xi = np.asarray(xi, float).ravel()
    S = np.empty((len(xi), q + 1))
    S[:, 0] = 0.5 * xi - 0.25 * xi ** 2 + 0.75
    if q >= 1:
        S[:, 1] = 0.5 * xi + 0.25 * xi ** 2 + 0.25
    if q >= 2:
        P = L.legvander(xi, q + 1)                       # Spalte k = P_k(xi)

        def int_p(k: int) -> np.ndarray:
            if k == 0:
                return xi + 1.0
            return (P[:, k + 1] - P[:, k - 1]) / (2 * k + 1)
        for j in range(2, q + 1):
            S[:, j] = (int_p(j) - int_p(j - 2)) / np.sqrt(2.0 * (2 * j - 1))
    return S


@lru_cache(maxsize=None)
def _dreieckregel(n: int) -> tuple[np.ndarray, np.ndarray]:
    from .oberflaeche import dreieck_gauss
    return dreieck_gauss(n)


def _faecher(polys: list[np.ndarray]) -> np.ndarray:
    """Alle Faecherdreiecke der Polygone als (k,3,3)."""
    T = []
    for poly in polys:
        for i in range(1, len(poly) - 1):
            T.append((poly[0], poly[i], poly[i + 1]))
    return np.asarray(T, float).reshape(-1, 3, 3)


def _stuecke_in_scheibe(D: np.ndarray, lo: np.ndarray, hi: np.ndarray, tol: float) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Dreiecke an den y- und z-Scheiben clippen und in x bei lo und hi teilen. Rueckgabe: (Polygone mit x_lo <= x <= x_hi,
    in denen G_x laeuft; Polygone mit x >= x_hi, in denen G_x voll ist). Teile mit x <= x_lo tragen nichts.
    Dreiecke, deren Huellbox ganz in der Scheibe und auf einer Seite von x_hi liegt, brauchen kein Clippen (die Mehrzahl,
    sobald die Facetten kleiner als die Zellen sind)."""
    D = np.asarray(D, float).reshape(-1, 3, 3)
    laufend: list[np.ndarray] = []
    voll: list[np.ndarray] = []
    if len(D) == 0:
        return laufend, voll
    mn, mx = D.min(axis=1), D.max(axis=1)
    in_scheibe = (mn[:, 1] >= lo[1] - tol) & (mx[:, 1] <= hi[1] + tol) & (mn[:, 2] >= lo[2] - tol) & (mx[:, 2] <= hi[2] + tol)
    ganz_links = mx[:, 0] <= lo[0] + tol
    ganz_rechts = mn[:, 0] >= hi[0] - tol
    ganz_mitte = (mn[:, 0] >= lo[0] - tol) & (mx[:, 0] <= hi[0] + tol)
    laufend += list(D[in_scheibe & ganz_mitte])
    voll += list(D[in_scheibe & ganz_rechts & ~ganz_mitte])
    rest = np.flatnonzero(~ganz_links & ~(in_scheibe & (ganz_mitte | ganz_rechts)))
    ey, ez, ex = np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0]), np.array([1.0, 0.0, 0.0])
    for t in rest:
        Q = D[t]
        for p0, n in ((lo, -ey), (hi, ey), (lo, -ez), (hi, ez), (lo, -ex)):
            Q, _ = polygon_clippen(Q, p0, n, tol)
            if len(Q) < 3:
                break
        if len(Q) < 3:
            continue
        # bei x_hi nur teilen, wenn das Polygon die Ebene wirklich kreuzt: ein Stueck genau auf x = x_hi liegt sonst in
        # beiden Haelften (Wuerfelhuelle gleich Zellbox: Volumen 16 statt 8, 01.10.2026); auf der Ebene sind beide Lagen gleich
        if Q[:, 0].max() <= hi[0] + tol:
            laufend.append(Q)
        elif Q[:, 0].min() >= hi[0] - tol:
            voll.append(Q)
        else:
            mitte, _ = polygon_clippen(Q, hi, ex, tol)
            rechts, _ = polygon_clippen(Q, hi, -ex, tol)
            if len(mitte) >= 3:
                laufend.append(mitte)
            if len(rechts) >= 3:
                voll.append(rechts)
    return laufend, voll


def huellenmomente(D: np.ndarray, lo, hi, q: int, ordnung: int | None = None) -> np.ndarray:
    """Tensor-Momente mu[a, b, c] = int_{Omega ∩ B} N_a(xi) N_b(eta) N_c(zeta) dV der Huelle D (m,3,3; nach aussen orientiert)
    in der Zelle B = [lo, hi] (Wuerfel oder Quader), Basis vom Grad q in den Referenzkoordinaten der Zelle. Exakt."""
    lo = np.asarray(lo, float).reshape(3)
    hi = np.asarray(hi, float).reshape(3)
    s = 0.5 * (hi - lo)
    tol = 1e-12 * float(s.max())
    # Grad des Integranden auf einem ebenen Stueck: laufend S_a(xi) N_b N_c vom Gesamtgrad 3q + 1, voll (S_a konstant) N_b N_c vom
    # Grad 2q; die kollabierte Regel mit n Punkten je Richtung ist exakt bis 2n - 1
    n_lauf = ordnung or int(np.ceil((3 * q + 2) / 2.0))
    n_voll = ordnung or int(np.ceil((2 * q + 1) / 2.0))
    mu = np.zeros((q + 1, q + 1, q + 1))
    laufend, voll = _stuecke_in_scheibe(D, lo, hi, tol)
    S_voll = legendre_1d_stamm(q, np.array([1.0]))[0]                   # int_{-1}^{1} N_a
    for polys, lage, n in ((laufend, 0, n_lauf), (voll, 1, n_voll)):
        T = _faecher(polys)
        if len(T) == 0:
            continue
        uv, w = _dreieckregel(n)
        # Normale je Faecherdreieck mit dem Vorzeichen der Wicklung (beim Clippen erhalten); n_x als Einheitskomponente
        nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        norm = np.linalg.norm(nrm, axis=1)
        ok = norm > 0.0
        T, nrm, norm = T[ok], nrm[ok], norm[ok]
        if len(T) == 0:
            continue
        nx = nrm[:, 0] / norm                                            # (k,)
        P = T[:, None, 0, :] + uv[None, :, :1] * (T[:, None, 1, :] - T[:, None, 0, :]) + uv[None, :, 1:] * (T[:, None, 2, :] - T[:, None, 0, :])
        Wm = (w[None, :] * norm[:, None]) * (s[0] * nx)[:, None]        # Flaechenmass (w summiert zu 1/2, norm = 2 Flaeche) mal s_x n_x
        P = P.reshape(-1, 3)
        Wm = Wm.ravel()
        xi = (P - lo) / s - 1.0
        Nb, _ = legendre_1d(q, xi[:, 1])
        Nc, _ = legendre_1d(q, xi[:, 2])
        if lage == 0:
            Sa = legendre_1d_stamm(q, xi[:, 0])
            mu += np.einsum("p,pa,pb,pc->abc", Wm, Sa, Nb, Nc, optimize=True)
        else:
            # volle Stuecke: die x-Stammfunktion ist konstant, die Summe ueber die Punkte nur zweidimensional (Block mit Bohrung
            # N 120: 106 384 volle gegen 41 574 laufende Faecherdreiecke, 16 von 22 s der Huellenmomente vor dieser Trennung)
            mu += S_voll[:, None, None] * np.einsum("p,pb,pc->bc", Wm, Nb, Nc, optimize=True)[None, :, :]
    return mu


def huellenvolumen(D: np.ndarray, lo, hi) -> float:
    """Werkstoffvolumen der Huelle in der Zelle - das Moment der Konstanten (N_0 + N_1 = 1)."""
    mu = huellenmomente(D, lo, hi, 1, ordnung=2)
    return float(mu[0:2, 0:2, 0:2].sum())


__all__ = ["legendre_1d_stamm", "huellenmomente", "huellenvolumen"]
