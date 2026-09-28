"""Vorkonditioniertes CG fuer den matrixfreien Operator (Teilprojekt 3, Vorgabe 8.2).

A ist eine Funktion x -> A x auf den freien Freiheitsgraden (Operator.frei_anwenden), M^-1 die
Jacobi-Diagonale. Mittelwertzwaenge der Schnittebenen (B x = d, drei Zeilen je Ebene) laufen als
projizierter CG: x = x_p + z mit x_p = B^T (B B^T)^-1 d und z im Kern von B; Operator und
Vorkonditionierer werden mit P = I - B^T (B B^T)^-1 B projiziert, A bleibt symmetrisch positiv
definit, kein Sattelpunkt. Die Multiplikatoren (Resultierende in der Ebene) folgen aus
lambda = (B B^T)^-1 B (b - A x) wie beim Direktloeser.

Abbruch: relatives Residuum <= tol und Energienorm der letzten Korrektur relativ zur Energie der
Loesung <= tol (Vorgabe 8.2); fuer x0 = 0 ist ||x_k||_A^2 = sum_j alpha_j r_j.z_j, sodass die
Energienorm ohne weitere Operatoranwendung mitlaeuft.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import scipy.sparse as sp


@dataclass
class PcgErgebnis:
    x: np.ndarray
    iterationen: int
    residuum_rel: float
    energie_rel: float
    konvergiert: bool
    multiplikatoren: np.ndarray          # (k,) bei Nebenbedingungen, sonst leer


def jacobi_diagonale(zelldaten, C: sp.spmatrix, K_rand: sp.spmatrix | None = None) -> np.ndarray:
    """Exakte Diagonale von A = C^T (K + K_rand) C aus den Zellmatrizen: je Zelle C_e^T K_e C_e
    ueber die beteiligten freien Spalten; Zellen ohne Zwaenge (Einheitszeilen) direkt."""
    z = zelldaten
    C = C.tocsr()
    n3 = 3 * z.m
    diag = np.zeros(C.shape[1])
    zellen = [(int(c), z.skala_innen[i], None) for i, c in enumerate(z.innen)] + [(int(c), 1.0, i) for i, c in enumerate(z.cut)]
    Kref_diag = np.diag(z.K_ref)
    for c, s, i_cut in zellen:
        Ke = z.K_ref if i_cut is None else z.K_cut[i_cut]
        rows = z.dofs[c]
        Ce = C[rows]
        if Ce.nnz == 0:
            continue
        if Ce.nnz == n3 and np.all(Ce.data == 1.0) and np.array_equal(np.diff(Ce.indptr), np.ones(n3, int)):
            # keine Zwaenge in dieser Zelle: Diagonale direkt in die freien Spalten
            spalten = Ce.indices
            diag[spalten] += s * (Kref_diag if i_cut is None else np.diag(Ke))
            continue
        spalten = np.unique(Ce.indices)
        Cs = Ce[:, spalten].toarray()
        diag[spalten] += s * np.einsum("aj,ab,bj->j", Cs, Ke, Cs)
    if K_rand is not None and K_rand.nnz:
        diag += np.asarray((C.T @ K_rand @ C).diagonal()).ravel()
    return diag


def _modul(a):
    """numpy oder cupy, je nach Feldtyp (derselbe CG-Code fuer CPU und GPU, Vorgabe 9)."""
    try:
        import cupy
        if isinstance(a, cupy.ndarray):
            return cupy
    except ImportError:
        pass
    return np


def pcg(A: Callable[[np.ndarray], np.ndarray], b: np.ndarray, M_inv: np.ndarray | None = None,
        tol: float = 1e-8, max_iter: int | None = None, B: np.ndarray | None = None, d: np.ndarray | None = None,
        fortschritt: Callable[[int, float], None] | None = None) -> PcgErgebnis:
    xp = _modul(b)
    b = xp.asarray(b, dtype=float).ravel()
    n = int(b.shape[0])
    max_iter = max_iter or max(2000, int(20 * np.sqrt(n)))
    # Vorkonditionierer: Diagonale (Jacobi) oder Funktion r -> z (V-Zyklus des Mehrgitters)
    if callable(M_inv):
        vork = M_inv
    else:
        m_inv = xp.ones(n) if M_inv is None else xp.asarray(M_inv, dtype=float)

        def vork(r):
            return m_inv * r
    if B is not None and len(B):
        B = xp.asarray(B, dtype=float).reshape(-1, n)
        d = xp.zeros(B.shape[0]) if d is None else xp.asarray(d, dtype=float).ravel()
        G = B @ B.T
        G_inv = xp.linalg.inv(G)
        x_p = B.T @ (G_inv @ d)

        def proj(v):
            return v - B.T @ (G_inv @ (B @ v))
    else:
        B = None
        x_p = xp.zeros(n)

        def proj(v):
            return v
    r = proj(b - A(x_p)) if B is not None else b.copy()
    norm_b = float(xp.sqrt(r @ r))
    x = xp.zeros(n)
    if norm_b == 0.0:
        lam = G_inv @ (B @ (b - A(x_p))) if B is not None else xp.zeros(0)
        return PcgErgebnis(x_p, 0, 0.0, 0.0, True, lam)
    z = proj(vork(r))
    p = z.copy()
    rz = float(r @ z)
    energie = 0.0
    energie_rel = np.inf
    res_rel = 1.0
    konvergiert = False
    k = 0
    for k in range(1, max_iter + 1):
        q = proj(A(p))
        pq = float(p @ q)
        if pq <= 0.0:
            raise ValueError(f"PCG: p^T A p = {pq:.3e} <= 0 - Operator nicht positiv definit (freie Starrkoerperbewegung?)")
        alpha = rz / pq
        x += alpha * p
        r -= alpha * q
        d_e = alpha * rz                                   # Abnahme des Energiefehlers = Energie der Korrektur
        energie += d_e
        energie_rel = float(np.sqrt(max(d_e, 0.0) / energie)) if energie > 0 else 0.0
        res_rel = float(xp.sqrt(r @ r)) / norm_b
        if fortschritt is not None:
            fortschritt(k, res_rel)
        if res_rel <= tol and energie_rel <= tol:
            konvergiert = True
            break
        z = proj(vork(r))
        rz_neu = float(r @ z)
        beta = rz_neu / rz
        rz = rz_neu
        p = z + beta * p
    x_ges = x_p + x
    lam = G_inv @ (B @ (b - A(x_ges))) if B is not None else xp.zeros(0)
    return PcgErgebnis(x_ges, k, res_rel, energie_rel, konvergiert, lam)


__all__ = ["PcgErgebnis", "jacobi_diagonale", "pcg"]
