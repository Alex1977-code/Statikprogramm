"""Moment Fitting fuer Schnittzellen (Vorgabe Abschnitt 6, Stufe 2; Plan TP 5, B1).

Die Referenzquadratur (rekursive, ebenen-exakte Integration in fcm/quadratur.py) liefert je Schnittzelle
die Momente der Werkstoffdomaene; gesucht ist eine Regel mit wenigen festen Punkten - Tensor-Gauss
(q+1)^3 in der Zelle -, deren Gewichte diese Momente exakt treffen. Basis der Momente ist die Tensor-
Legendre-Basis vom Grad q je Richtung (legendre_1d): sie spannt dieselben Polynome auf wie die Monome,
ist auf [-1,1] aber gut konditioniert. Weil Punkte und Basis Tensorprodukte sind, ist die Momentenmatrix
A = A1 (x) A1 (x) A1 mit A1[i,a] = N_a(x_i) an den Gauss-Punkten, und die Gewichte folgen aus drei
eindimensionalen Kontraktionen mit A1^-T (Kronecker-Struktur) statt aus einer (q+1)^3-dimensionalen
Loesung.

Mit q = 2p sind alle Integranden der Zellsteifigkeit (Produkte zweier Basisableitungen, Grad <= 2p je
Richtung) exakt integriert: die Zellmatrix ist bis auf Rundung die der Referenz, negative Gewichte
koennen ihr nichts anhaben. Fuer q < 2p ist das nicht gesichert; dann gilt eine Zelle als schlecht
gefittet, wenn die negative Gewichtsmasse ``neg_schwelle`` der positiven uebersteigt - es folgt NNLS auf
den Gauss-Punkten (q+2)^3, und bleibt ein relatives Residuum ueber ``nnls_toleranz``, faellt die Zelle
auf die Referenz zurueck. Die Vorgabe fuer q steht in ``fit_grad_standard`` (Messung Theorie 11.11).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .basis import gauss_1d, gauss_3d, legendre_1d

# Vorgabe des Fit-Grads je Polynomgrad p - nach der Messung in Theorie 11.11 gesetzt (Plan TP 5, B1)
def fit_grad_standard(p: int) -> int:
    return 2 * p


@dataclass
class FitErgebnis:
    punkte: np.ndarray            # (n,3) global
    gewichte: np.ndarray          # (n,) global (Summe = Werkstoffvolumen der Referenz)
    art: str                      # 'fit' (Kronecker), 'nnls', 'rueckfall'
    min_gewicht: float            # kleinstes Gewicht relativ zum mittleren positiven
    neg_anteil: float             # negative Gewichtsmasse geteilt durch die positive


@lru_cache(maxsize=None)
def _kronecker_faktor(q: int) -> np.ndarray:
    """B = A1^-T mit A1[i,a] = N_a(x_i) an den q+1 Gauss-Punkten (Loesung der 1D-Momentengleichung)."""
    x, _ = gauss_1d(q + 1)
    A1, _ = legendre_1d(q, x)
    return np.linalg.inv(A1.T)


def momente(xi: np.ndarray, w: np.ndarray, q: int) -> np.ndarray:
    """Tensor-Momente (q+1)^3 der Regel (xi, w) in der Basis vom Grad q: mu[a,b,c] = sum w N_a N_b N_c."""
    xi = np.asarray(xi, float).reshape(-1, 3)
    Na, _ = legendre_1d(q, xi[:, 0])
    Nb, _ = legendre_1d(q, xi[:, 1])
    Nc, _ = legendre_1d(q, xi[:, 2])
    return np.einsum("q,qa,qb,qc->abc", np.asarray(w, float), Na, Nb, Nc, optimize=True)


def gewichte_kronecker(mu: np.ndarray, q: int) -> np.ndarray:
    """Gewichte auf den Tensor-Gauss-Punkten (q+1)^3 (Reihenfolge wie gauss_3d), die mu exakt treffen."""
    B = _kronecker_faktor(q)
    return np.einsum("ia,jb,kc,abc->ijk", B, B, B, mu, optimize=True).ravel()


def _momentenmatrix(q: int, n_punkte: int) -> np.ndarray:
    """A[(a,b,c), i] = N_a N_b N_c an den Tensor-Gauss-Punkten n_punkte^3 (fuer NNLS, keine Kronecker-Loesung)."""
    X, _ = gauss_3d(n_punkte)
    Na, _ = legendre_1d(q, X[:, 0])
    Nb, _ = legendre_1d(q, X[:, 1])
    Nc, _ = legendre_1d(q, X[:, 2])
    return np.einsum("ia,ib,ic->abci", Na, Nb, Nc, optimize=True).reshape((q + 1) ** 3, -1)


def _bewerten(w: np.ndarray) -> tuple[float, float]:
    pos = w[w > 0]
    mittel = float(pos.mean()) if len(pos) else 1.0
    neg = float(-w[w < 0].sum())
    return float(w.min()) / mittel, neg / float(pos.sum()) if len(pos) else np.inf


def gefittete_regel(lo: np.ndarray, hi: np.ndarray, P_ref: np.ndarray, W_ref: np.ndarray, q: int, p: int,
                    neg_schwelle: float = 1e-2, nnls_toleranz: float = 1e-10, mu_zusatz: np.ndarray | None = None) -> FitErgebnis:
    """Regel fuer die Werkstoffdomaene einer Zelle [lo, hi] aus der Referenzregel (P_ref, W_ref, global).

    Rueckgabe 'rueckfall' traegt die Referenzregel selbst. Bei q >= 2p werden negative Gewichte hingenommen
    (Zellsteifigkeit exakt, siehe Modulkopf), sonst greift die Schwelle. ``mu_zusatz`` (q+1)^3: Momente von Werkstoffteilen,
    die nicht als Punkte vorliegen (schraeg geschnittene Stuecke, exakt ueber den Divergenzsatz, Plan TP 5 O5); nur mit q >= 2p,
    weil NNLS und Rueckfall die Referenzpunkte brauchen."""
    lo = np.asarray(lo, float)
    hi = np.asarray(hi, float)
    s = 0.5 * (hi - lo)
    xi = (np.asarray(P_ref, float) - lo) / s - 1.0
    mu = momente(xi, W_ref, q)
    if mu_zusatz is not None:
        if q < 2 * p:
            raise ValueError("mu_zusatz verlangt q >= 2p (ohne Referenzpunkte kein NNLS und kein Rueckfall)")
        mu = mu + mu_zusatz
    w = gewichte_kronecker(mu, q)
    X, _ = gauss_3d(q + 1)
    min_g, neg = _bewerten(w)
    if q >= 2 * p or neg <= neg_schwelle:
        return FitErgebnis(lo + s * (X + 1.0), w, "fit", min_g, neg)
    from scipy.optimize import nnls
    A = _momentenmatrix(q, q + 2)
    b = mu.ravel()
    w2, rest = nnls(A, b)
    if rest <= nnls_toleranz * max(float(np.linalg.norm(b)), 1e-300):
        X2, _ = gauss_3d(q + 2)
        min_g2, neg2 = _bewerten(w2)
        return FitErgebnis(lo + s * (X2 + 1.0), w2, "nnls", min_g2, neg2)
    return FitErgebnis(np.asarray(P_ref, float), np.asarray(W_ref, float), "rueckfall", min_g, neg)


__all__ = ["FitErgebnis", "fit_grad_standard", "momente", "gewichte_kronecker", "gefittete_regel"]
