"""Auswertung der Loesung an Punkten (Entwurf 3.9): Verschiebung, Spannung (Voigt),
Vergleichsspannung, Schnittgroessen ueber eine Flaechenquadratur.

Spannungen werden direkt aus der Loesung ausgewertet (sigma = D B u); Rueckgewinnung
(SPR/L2) kommt mit Teilprojekt 5.
"""
from __future__ import annotations

import numpy as np

from ..fcm.basis import basis_3d
from ..fcm.elastizitaet import b_matrizen, d_matrix


def von_mises(s: np.ndarray) -> np.ndarray:
    sx, sy, sz, txy, tyz, txz = np.asarray(s, float).reshape(-1, 6).T
    return np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3.0 * (txy ** 2 + tyz ** 2 + txz ** 2))


def traktion(s: np.ndarray, n: np.ndarray) -> np.ndarray:
    """t = sigma . n aus Voigt (q,6) und Normalen (q,3)."""
    s = np.asarray(s, float).reshape(-1, 6)
    n = np.asarray(n, float).reshape(-1, 3)
    return np.stack([s[:, 0] * n[:, 0] + s[:, 3] * n[:, 1] + s[:, 5] * n[:, 2],
                     s[:, 3] * n[:, 0] + s[:, 1] * n[:, 1] + s[:, 4] * n[:, 2],
                     s[:, 5] * n[:, 0] + s[:, 4] * n[:, 1] + s[:, 2] * n[:, 2]], axis=1)


class Auswertung:
    def __init__(self, problem, U) -> None:
        self.problem = problem
        self.U = np.asarray(U, float).ravel()
        self.D = d_matrix(problem.werkstoff.E, problem.werkstoff.nu)

    def _zellen(self, P: np.ndarray) -> np.ndarray:
        c = self.problem.gitter.zelle_finden(P)
        if (c < 0).any():
            i = int(np.flatnonzero(c < 0)[0])
            raise ValueError(f"{int((c < 0).sum())} Punkte liegen ausserhalb der aktiven Zellen, z. B. {P[i]}")
        return c

    def _lokal(self, P):
        P = np.asarray(P, float).reshape(-1, 3)
        g = self.problem.gitter
        c = self._zellen(P)
        Uc = self.U[(3 * g.zell_moden[c][:, :, None] + np.arange(3)).reshape(len(P), -1)]     # (n,3m)
        return g, c, g.lokal(P, c), Uc

    def verschiebung(self, P) -> np.ndarray:
        g, c, xi, Uc = self._lokal(P)
        N, _ = basis_3d(g.p, xi)
        return np.einsum("ni,nia->na", N, Uc.reshape(len(N), -1, 3))

    def spannung(self, P) -> np.ndarray:
        g, c, xi, Uc = self._lokal(P)
        _, dN = basis_3d(g.p, xi)
        eps = np.einsum("nsd,nd->ns", b_matrizen(dN * (2.0 / g.h)), Uc)
        return eps @ self.D.T

    def spannung_und_verschiebung(self, P) -> tuple[np.ndarray, np.ndarray]:
        g, c, xi, Uc = self._lokal(P)
        N, dN = basis_3d(g.p, xi)
        u = np.einsum("ni,nia->na", N, Uc.reshape(len(N), -1, 3))
        eps = np.einsum("nsd,nd->ns", b_matrizen(dN * (2.0 / g.h)), Uc)
        return eps @ self.D.T, u

    def schnittgroessen(self, fq, ursprung) -> tuple[np.ndarray, np.ndarray]:
        """F = int sigma.n dA und M = int (x - o) x sigma.n dA ueber eine Flaechenquadratur,
        Normale nach aussen aus dem Detail (Vorzeichen wie SectionForces des Vertrags)."""
        t = traktion(self.spannung(fq.punkte), fq.normalen)
        F = (fq.gewichte[:, None] * t).sum(axis=0)
        M = (fq.gewichte[:, None] * np.cross(fq.punkte - np.asarray(ursprung, float).reshape(3), t)).sum(axis=0)
        return F, M


__all__ = ["von_mises", "traktion", "Auswertung"]
