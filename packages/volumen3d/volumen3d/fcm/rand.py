"""Randbedingungen und Lasten ueber Flaechen- und Volumenquadratur (Vorgabe Abschnitt 7,
Entwurf 3.6).

Verschiebungsraender ueber **symmetrisches Nitsche** mit Projektion P (voll: alle drei
Komponenten, normal: nur die Normalkomponente fuer Symmetrie- und Gleitraender). Je
Quadraturpunkt mit Verschiebungsinterpolation Nm (3 x 3m), Traktionsoperator
T = Nn D B (3 x 3m, Nn bildet den Voigt-Spannungsvektor auf sigma.n ab) und Gewicht w:

    K_N += w [ -T^T P Nm - Nm^T P T + beta Nm^T P Nm ]
    f_N += w [ -T^T P g      + beta Nm^T P g ]

beta = C E p^2 / h je Zelle (Vorgabe: Heuristik; C = 10 Startwert, steht im Protokoll).
Das Verfahren ist konsistent: fuer die exakte Loesung heben sich die Terme auf, unabhaengig
von beta (Patch-Test T4). Traktion: f += w Nm^T t; Druck p: t = -p n; Volumenlast b nur im
Werkstoff (alpha-Punkte tragen nicht).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from .basis import anzahl_moden, basis_3d
from .elastizitaet import b_matrizen, d_matrix, n_matrizen


def nn_matrizen(n: np.ndarray) -> np.ndarray:
    """Nn (q,3,6): Traktion t = Nn @ sigma_voigt fuer Normalen n (q,3)."""
    n = np.asarray(n, float)
    Nn = np.zeros((len(n), 3, 6))
    Nn[:, 0, 0] = n[:, 0]; Nn[:, 0, 3] = n[:, 1]; Nn[:, 0, 5] = n[:, 2]
    Nn[:, 1, 1] = n[:, 1]; Nn[:, 1, 3] = n[:, 0]; Nn[:, 1, 4] = n[:, 2]
    Nn[:, 2, 2] = n[:, 2]; Nn[:, 2, 4] = n[:, 1]; Nn[:, 2, 5] = n[:, 0]
    return Nn


def projektionen(art: str, n: np.ndarray) -> np.ndarray:
    """P (q,3,3): Einheit ('voll') oder n n^T ('normal')."""
    n = np.asarray(n, float)
    if art == "voll":
        return np.broadcast_to(np.eye(3), (len(n), 3, 3)).copy()
    if art == "normal":
        return np.einsum("qa,qb->qab", n, n)
    raise ValueError("projektion: 'voll' oder 'normal'")


def _zellweise(gitter, fq):
    """Iteration ueber die Zellen einer Flaechenquadratur: (Zelle, Indizes, N, G)."""
    reihenfolge = np.argsort(fq.zelle, kind="stable")
    zellen, start = np.unique(fq.zelle[reihenfolge], return_index=True)
    grenzen = list(start) + [len(reihenfolge)]
    for k, c in enumerate(zellen):
        idx = reihenfolge[grenzen[k]:grenzen[k + 1]]
        N, dN = basis_3d(gitter.p, fq.xi[idx])
        yield int(c), idx, N, dN * (2.0 / float(gitter.h_zelle(int(c))))


def beta_zelle(gitter, c: int, E: float, beta_faktor: float) -> float:
    """Nitsche-Parameter je Zelle: C * E * p^2 / h_c (Vorgabe Abschnitt 7)."""
    return float(beta_faktor) * float(E) * int(gitter.p) ** 2 / float(gitter.h_zelle(c))


def nitsche_steifigkeit(gitter, fq, E: float, nu: float, beta_faktor: float, art: str) -> sp.coo_matrix:
    D = d_matrix(E, nu)
    m = anzahl_moden(gitter.p)
    n = gitter.n_dof
    Z, S, V = [], [], []
    for c, idx, N, G in _zellweise(gitter, fq):
        beta = beta_zelle(gitter, c, E, beta_faktor)
        w = fq.gewichte[idx]
        T = np.einsum("qab,bc,qcd->qad", nn_matrizen(fq.normalen[idx]), D, b_matrizen(G))   # (q,3,3m)
        PN = np.einsum("qab,qbd->qad", projektionen(art, fq.normalen[idx]), n_matrizen(N))  # (q,3,3m)
        Tw = (T * w[:, None, None]).reshape(-1, T.shape[2])                                # BLAS statt einsum
        PNf = PN.reshape(-1, PN.shape[2])
        TPN = Tw.T @ PNf
        Ke = -TPN - TPN.T + beta * ((PN * w[:, None, None]).reshape(-1, PN.shape[2]).T @ PNf)
        dof = gitter.zell_dofs(c)
        Z.append(np.repeat(dof, 3 * m))
        S.append(np.tile(dof, 3 * m))
        V.append(Ke.ravel())
    if not V:
        return sp.coo_matrix((n, n))
    return sp.coo_matrix((np.concatenate(V), (np.concatenate(Z), np.concatenate(S))), shape=(n, n))


def nitsche_rechte_seite(gitter, fq, E: float, nu: float, beta_faktor: float, art: str, g: np.ndarray) -> np.ndarray:
    """Vorgabe g (nq,3) an den Quadraturpunkten -> f (n_dof,)."""
    D = d_matrix(E, nu)
    g = np.asarray(g, float).reshape(-1, 3)
    f = np.zeros(gitter.n_dof)
    for c, idx, N, G in _zellweise(gitter, fq):
        beta = beta_zelle(gitter, c, E, beta_faktor)
        w = fq.gewichte[idx]
        T = np.einsum("qab,bc,qcd->qad", nn_matrizen(fq.normalen[idx]), D, b_matrizen(G))
        Pg = np.einsum("qab,qb->qa", projektionen(art, fq.normalen[idx]), g[idx])               # (q,3)
        fe = -np.einsum("q,qad,qa->d", w, T, Pg) + beta * np.einsum("q,qad,qa->d", w, n_matrizen(N), Pg)
        f[gitter.zell_dofs(c)] += fe
    return f


def flaechenlast(gitter, fq, t: np.ndarray) -> np.ndarray:
    """Traktion t (nq,3) an den Quadraturpunkten -> f (n_dof,)."""
    t = np.asarray(t, float).reshape(-1, 3)
    f = np.zeros(gitter.n_dof)
    for c, idx, N, _ in _zellweise(gitter, fq):
        f[gitter.zell_dofs(c)] += np.einsum("q,qi,qa->ia", fq.gewichte[idx], N, t[idx]).ravel()
    return f


def starrkoerper_moden(fq) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """In-Ebene-Starrkoerpermoden einer (nahezu ebenen) Flaeche: zwei Tangentialverschiebungen
    und die Drehung um die Normale, (nq,3,3) [Punkt, Mode, Komponente]; dazu Normale und
    Flaechenschwerpunkt.

    Anlass (Kragarm-Kopplung 27.09.2026): Die ebene Querschnittskinematik eines Stabs enthaelt
    keine Querkontraktion. Wird sie mit allen drei Komponenten punktweise vorgegeben, ist die
    Schnittebene seitlich gesperrt und das uebertragene Moment um 45 % zu hoch (Segment 3 h).
    Darum gilt an Schnittebenen: Normalkomponente punktweise (traegt Biegung, Laengskraft,
    Verwoelbung), in der Ebene nur die drei Resultierenden - Querkraft und Torsion - als
    Mittelwertzwaenge. Querkontraktion und Schubverwoelbung bleiben frei.
    """
    n = fq.normalen.mean(axis=0)
    n /= np.linalg.norm(n)
    c = (fq.gewichte[:, None] * fq.punkte).sum(axis=0) / fq.gewichte.sum()
    hilfe = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    t1 = np.cross(n, hilfe)
    t1 /= np.linalg.norm(t1)
    t2 = np.cross(n, t1)
    dreh = np.cross(n, fq.punkte - c)
    moden = np.stack([np.broadcast_to(t1, dreh.shape), np.broadcast_to(t2, dreh.shape), dreh], axis=1)
    return moden, n, c


def mittelwert_zwaenge(gitter, fq, moden: np.ndarray) -> np.ndarray:
    """B (3, n_dof): b_k . U = int_Gamma u . m_k dA fuer die drei Moden."""
    B = np.zeros((moden.shape[1], gitter.n_dof))
    for c, idx, N, _ in _zellweise(gitter, fq):
        Nm = n_matrizen(N)                                                       # (q,3,3m)
        B[:, gitter.zell_dofs(c)] += np.einsum("q,qka,qad->kd", fq.gewichte[idx], moden[idx], Nm)
    return B


def mittelwert_vorgabe(fq, moden: np.ndarray, g: np.ndarray) -> np.ndarray:
    """d_k = int_Gamma g . m_k dA."""
    g = np.asarray(g, float).reshape(-1, 3)
    return np.einsum("q,qka,qa->k", fq.gewichte, moden, g)


def volumenlast(gitter, quadratur, b: np.ndarray) -> np.ndarray:
    """Konstante Volumenlast b (3,) in N/mm^3, nur im Werkstoff."""
    b = np.asarray(b, float).reshape(3)
    f = np.zeros(gitter.n_dof)
    for c in range(len(gitter.ijk)):
        P, W, I = quadratur.zelle(c)
        if len(P) == 0:
            continue
        N, _ = basis_3d(gitter.p, gitter.lokal(P, np.full(len(P), c)))
        f[gitter.zell_dofs(c)] += np.outer((W * I) @ N, b).ravel()
    return f


__all__ = ["nn_matrizen", "projektionen", "beta_zelle", "nitsche_steifigkeit", "nitsche_rechte_seite", "flaechenlast",
           "volumenlast", "starrkoerper_moden", "mittelwert_zwaenge", "mittelwert_vorgabe"]
