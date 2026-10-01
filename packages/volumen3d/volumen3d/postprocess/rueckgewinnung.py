"""Spannungsrueckgewinnung durch globale L2-Projektion (Vorgabe 11.1, Plan TP 5 B2).

Die Rohspannung sigma_h = D B u ist je Zelle ein Polynom und springt an Zellgrenzen; in Schnittzellen mit
wenig Werkstoff und an gebundenen (aggregierten) Zellen ist sie an der Oberflaeche am unsichersten. Projiziert
wird jede der sechs Komponenten auf den stetigen skalaren Ansatzraum vom Grad p derselben Zellen:

    M X = B,   M = C^T (sum_c int N^T N dOmega) C,   B = C^T sum_c int N^T sigma_h dOmega,

mit der skalaren Zwangsmatrix C (haengende Moden und Aggregation; die Zwaenge der Verschiebungen sind je
Komponente gleich, C_skalar = C[0::3, 0::3]) und der Zellquadratur der Steifigkeit (Werkstoff- und alpha-Punkte).
Das Werkstoffgebiet bestimmt M wie die Steifigkeit: gebundene Moden schlecht geschnittener Zellen haengen an
ihrer Wurzel, isolierte Splitter behalten alpha. M wird einmal je Problem faktorisiert; jeder Lastfall kostet nur
die rechten Seiten. Konstante Spannungen gehoeren zum Ansatzraum und werden exakt wiedergegeben (Patch-Test).
"""
from __future__ import annotations

import time

import numpy as np
import scipy.sparse as sp

from ..fcm.basis import basis_3d
from ..fcm.elastizitaet import b_matrizen, d_matrix
from ..fcm.gitter import INSIDE
from ..linalg.direkt import Direktloeser

# Punkte je Auswerteblock: X[zell_moden[c]] ist (n, m, 6, k) - bei 200 000 Oberflaechenpunkten und p 3 waeren das
# 614 MB je Lastfall auf einmal
_PUNKTE_JE_BLOCK = 20_000


class L2Rueckgewinnung:
    """Einmal je Problem: skalare Massenmatrix auf den freien Moden, faktorisiert. ``knoten(U)`` liefert die
    Koeffizienten der geglaetteten Spannungen je Mode (n_moden, 6, k), ``spannung(P, X)`` wertet sie aus."""

    def __init__(self, problem) -> None:
        t0 = time.perf_counter()
        self.problem = problem
        g = problem.gitter
        self.gitter = g
        self.p = g.p
        self.m = (g.p + 1) ** 3
        self.D = d_matrix(problem.werkstoff.E, problem.werkstoff.nu)
        C = problem.zwaenge.C.tocsr()
        self.C = sp.csr_matrix(C[0::3, 0::3])                   # skalar: Zwaenge je Komponente gleich
        n = g.n_moden
        zeilen, spalten, werte = [], [], []
        M_innen: dict[int, np.ndarray] = {}
        Q = problem.quadratur
        for c in range(len(g.ijk)):
            if g.klasse[c] == INSIDE:
                l = int(g.ebene[c])
                if l not in M_innen:
                    N, W = self._basis_und_gewichte(c)[:2]
                    M_innen[l] = (N * W[:, None]).T @ N
                Me = M_innen[l]
            else:
                P, W, _ = Q.zelle(c)
                if len(W) == 0:
                    continue
                N, _ = basis_3d(self.p, g.lokal(P, np.full(len(P), c)))
                Me = (N * W[:, None]).T @ N
            mo = g.zell_moden[c]
            zeilen.append(np.repeat(mo, self.m))
            spalten.append(np.tile(mo, self.m))
            werte.append(Me.ravel())
        M_voll = sp.coo_matrix((np.concatenate(werte), (np.concatenate(zeilen), np.concatenate(spalten))), shape=(n, n)).tocsr()
        self.M = (self.C.T @ M_voll @ self.C).tocsr()
        self.loeser = Direktloeser(self.M)
        self.statistik = {"verfahren": "L2-Projektion", "moden_frei": int(self.M.shape[0]), "nnz": int(self.M.nnz),
                          "t_einrichten_s": round(time.perf_counter() - t0, 3)}

    def _basis_und_gewichte(self, c: int):
        P, W, _ = self.problem.quadratur.zelle(c)
        N, dN = basis_3d(self.p, self.gitter.lokal(P, np.full(len(P), c)))
        return N, W, dN * (2.0 / float(self.gitter.h_zelle(c)))

    def knoten(self, U: np.ndarray) -> np.ndarray:
        """Koeffizienten (n_moden, 6, k) der projizierten Spannungen fuer U (n_dof,) oder (n_dof, k)."""
        t0 = time.perf_counter()
        g = self.gitter
        U = np.asarray(U, float)
        U = U.reshape(U.shape[0], -1)
        k = U.shape[1]
        B_voll = np.zeros((g.n_moden, 6 * k))
        innen_ref: dict[int, tuple] = {}
        for c in range(len(g.ijk)):
            if g.klasse[c] == INSIDE:
                l = int(g.ebene[c])
                if l not in innen_ref:
                    innen_ref[l] = self._basis_und_gewichte(c)
                N, W, G = innen_ref[l]
            else:
                N, W, G = self._basis_und_gewichte(c)
                if len(W) == 0:
                    continue
            mo = g.zell_moden[c]
            Uc = U[(3 * mo[:, None] + np.arange(3)).ravel()]                       # (3m, k)
            sig = np.einsum("st,qtk->qsk", self.D, np.einsum("qtd,dk->qtk", b_matrizen(G), Uc))   # (nq, 6, k)
            B_voll[mo] += np.einsum("qi,q,qsk->isk", N, W, sig).reshape(self.m, 6 * k)
        X = self.loeser.loesen(np.asarray(self.C.T @ B_voll))
        self.statistik["t_rechte_seiten_s"] = round(time.perf_counter() - t0, 3)
        return np.asarray(self.C @ X).reshape(g.n_moden, 6, k)

    def spannung(self, P: np.ndarray, X: np.ndarray, zellen: np.ndarray | None = None) -> np.ndarray:
        """Geglaettete Spannungen (n,6) bzw. (n,6,k) an Punkten P aus den Koeffizienten X."""
        g = self.gitter
        P = np.asarray(P, float).reshape(-1, 3)
        c = g.zelle_finden(P) if zellen is None else np.asarray(zellen)
        if np.any(c < 0):
            # zelle_finden liefert -1 ausserhalb; zell_moden[-1] haette still die letzte Zelle genommen (Gutachten C2, G2-9)
            i = int(np.flatnonzero(c < 0)[0])
            raise ValueError(f"{int((c < 0).sum())} Punkte ausserhalb aller aktiven Zellen, z. B. {P[i]}")
        s = np.empty((len(P), 6, X.shape[2]))
        for a in range(0, len(P), _PUNKTE_JE_BLOCK):
            b = min(len(P), a + _PUNKTE_JE_BLOCK)
            N, _ = basis_3d(self.p, g.lokal(P[a:b], c[a:b]))
            s[a:b] = np.einsum("ni,nisk->nsk", N, X[g.zell_moden[c[a:b]]])
        return s[:, :, 0] if s.shape[2] == 1 else s


def rueckgewinnung(problem) -> L2Rueckgewinnung:
    """Die Rueckgewinnung eines Problems, einmal gebaut und am Problem gehalten (Zwaenge und Quadratur stehen nach
    dem Konstruktor fest)."""
    r = getattr(problem, "_rueckgewinnung", None)
    if r is None or r.gitter is not problem.gitter:
        r = L2Rueckgewinnung(problem)
        problem._rueckgewinnung = r
    return r


__all__ = ["L2Rueckgewinnung", "rueckgewinnung"]
