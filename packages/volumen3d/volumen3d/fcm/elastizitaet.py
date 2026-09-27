"""Linear-elastische Zellsteifigkeit und Assemblierung (CPU-Referenz, Entwurf 3.8).

Die Zellsteifigkeit entsteht aus Gradientenmomenten statt aus einer expliziten B-Matrix:
M_ab = sum_q w_q dN/dx_a (x) dN/dx_b (m x m), und der Block (i,a),(j,b) von K_e ist
lambda M_ab[i,j] + mu M_ba[i,j] + mu delta_ab sum_g M_gg[i,j]. Das ist dieselbe Matrix wie
B^T D B (packages/volumen3d/volumen3d/tests/test_elastizitaet.py prueft beide Wege gegeneinander), kommt aber
ohne die (6 x 3m)-Matrizen je Quadraturpunkt aus - bei Schnittzellen mit tausenden Punkten
entscheidet das ueber Speicher und Zeit.

Freiheitsgrade: 3 * mode + Komponente (verschraenkt), Voigt-Reihenfolge xx, yy, zz, xy, yz, xz
mit technischen Gleitungen.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from .basis import anzahl_moden, basis_3d
from .gitter import INSIDE


def lame(E: float, nu: float) -> tuple[float, float]:
    return E * nu / ((1 + nu) * (1 - 2 * nu)), E / (2 * (1 + nu))


def d_matrix(E: float, nu: float) -> np.ndarray:
    lam, mu = lame(E, nu)
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[np.arange(3), np.arange(3)] += 2 * mu
    D[3:, 3:] = mu * np.eye(3)
    return D


def b_matrizen(G: np.ndarray) -> np.ndarray:
    """B (q,6,3m) aus globalen Gradienten G (q,m,3): Voigt xx,yy,zz,xy,yz,xz, technische
    Gleitungen, Freiheitsgrad 3*i + Komponente."""
    G = np.asarray(G, float)
    q, m, _ = G.shape
    B = np.zeros((q, 6, 3 * m))
    B[:, 0, 0::3] = G[:, :, 0]
    B[:, 1, 1::3] = G[:, :, 1]
    B[:, 2, 2::3] = G[:, :, 2]
    B[:, 3, 0::3] = G[:, :, 1]
    B[:, 3, 1::3] = G[:, :, 0]
    B[:, 4, 1::3] = G[:, :, 2]
    B[:, 4, 2::3] = G[:, :, 1]
    B[:, 5, 0::3] = G[:, :, 2]
    B[:, 5, 2::3] = G[:, :, 0]
    return B


def n_matrizen(N: np.ndarray) -> np.ndarray:
    """Nm (q,3,3m) mit Nm[q, a, 3i+a] = N[q, i]: Verschiebung u = Nm @ u_e."""
    N = np.asarray(N, float)
    q, m = N.shape
    Nm = np.zeros((q, 3, 3 * m))
    for a in range(3):
        Nm[:, a, a::3] = N
    return Nm


def zellsteifigkeit(G: np.ndarray, w: np.ndarray, E: float, nu: float) -> np.ndarray:
    """K_e (3m,3m) aus globalen Gradienten G (nq,m,3) und Gewichten w (nq,)."""
    lam, mu = lame(E, nu)
    q, m, _ = G.shape
    # Gradientenmomente als ein BLAS-Produkt: Spalte a*m + i von A ist dN_i/dx_a an allen Punkten
    A = np.ascontiguousarray(G.transpose(0, 2, 1).reshape(q, 3 * m))
    M = ((A * w[:, None]).T @ A).reshape(3, m, 3, m)                  # M[a,i,b,j] = sum w dN_i/dx_a dN_j/dx_b
    spur = M[0, :, 0, :] + M[1, :, 1, :] + M[2, :, 2, :]
    K = np.empty((m, 3, m, 3))
    for a in range(3):
        for b in range(3):
            K[:, a, :, b] = lam * M[a, :, b, :] + mu * M[b, :, a, :] + (mu * spur if a == b else 0.0)
    return K.reshape(3 * m, 3 * m)


def zell_gradienten(gitter, quadratur, c: int) -> tuple[np.ndarray, np.ndarray]:
    """Globale Gradienten (nq,m,3) und Gewichte (nq,) einer Zelle; dN/dx = (2/h) dN/dxi."""
    P, W, _ = quadratur.zelle(c)
    xi = gitter.lokal(P, np.full(len(P), c))
    _, dN = basis_3d(gitter.p, xi)
    return dN * (2.0 / float(gitter.h_zelle(c))), W


def assemblieren(gitter, quadratur, E: float, nu: float, fortschritt=None, block_eintraege: int = 20_000_000) -> sp.csr_matrix:
    """Globale Steifigkeit (n_dof x n_dof) als CSR; doppelte Eintraege werden summiert.

    Blockweise: die COO-Tripel aller Zellen auf einmal brauchen 24 Byte je Eintrag - bei der
    Kirsch-Platte mit h 5 (8300 Zellen, p 3) 7,3 GB, was auf der belegten Maschine mit einem
    MemoryError endete (27.09.). Bloecke von etwa 20 Mio. Eintraegen (~0,5 GB) werden als CSR
    aufsummiert.
    """
    n = gitter.n_dof
    m = anzahl_moden(gitter.p)
    nz = len(gitter.ijk)
    je = (3 * m) ** 2
    je_block = max(1, block_eintraege // je)
    K: sp.csr_matrix | None = None
    Ke_innen: dict[int, np.ndarray] = {}        # INSIDE-Zellen einer Ebene sind bis auf die Lage gleich
    for start in range(0, nz, je_block):
        zellen = range(start, min(start + je_block, nz))
        zeilen = np.empty(len(zellen) * je, np.int32 if n < 2 ** 31 else np.int64)
        spalten = np.empty_like(zeilen)
        werte = np.empty(len(zellen) * je)
        for k, c in enumerate(zellen):
            if gitter.klasse[c] == INSIDE:
                l = int(gitter.ebene[c])
                if l not in Ke_innen:
                    G, W = zell_gradienten(gitter, quadratur, c)
                    Ke_innen[l] = zellsteifigkeit(G, W, E, nu)
                Ke = Ke_innen[l]
            else:
                G, W = zell_gradienten(gitter, quadratur, c)
                Ke = zellsteifigkeit(G, W, E, nu)
            dof = gitter.zell_dofs(c)
            s = slice(k * je, (k + 1) * je)
            zeilen[s] = np.repeat(dof, 3 * m)
            spalten[s] = np.tile(dof, 3 * m)
            werte[s] = Ke.ravel()
            if fortschritt is not None and c % 200 == 0:
                fortschritt("Steifigkeit assemblieren", c / nz)
        K_block = sp.coo_matrix((werte, (zeilen, spalten)), shape=(n, n)).tocsr()
        K_block.sum_duplicates()
        K = K_block if K is None else K + K_block
    if K is None:
        K = sp.csr_matrix((n, n))
    return K


__all__ = ["lame", "d_matrix", "zellsteifigkeit", "zell_gradienten", "assemblieren"]
