"""Matrixfreier Operator v = K u (Teilprojekt 3, Vorgabe 8.1, Entwurf 4c).

Zellen liegen als Structure of Arrays vor: INSIDE-Zellen tragen je Ebene nur einen Massstab
(K ∝ h, K_e = h_l/h_0 · K_ref mit einer Referenz-Zellmatrix je p und Werkstoff), CUT-Zellen ihre
gespeicherte Zellmatrix aus der Schnittzellen-Quadratur (Vorgabe 8.1 „optional, konfigurierbar“;
Kirsch h 10 p 3: 1722 Schnittzellen x 295 KB = 0,5 GB). Eingesammelt wird ohne Wettlauf ueber
eine Inzidenz Freiheitsgrad -> (Zelle, lokaler Index): der Zellkern schreibt in einen Puffer
(nz, 3m), das Einsammeln laeuft je Freiheitsgrad parallel (Gather statt Scatter, keine Atomics,
keine Faerbung; auf CPU und GPU gleich).

Zwaenge (haengende Freiheitsgrade, Aggregation) bleiben die Zwangsmatrix C, die Nitsche-Raender
die duennbesetzte Matrix K_rand: A = C^T (K + K_rand) C. Kerne mit numba, wenn vorhanden, sonst
numpy-Rueckfall mit denselben Zahlen (Blockprodukte je Ebene).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from .basis import anzahl_moden, basis_3d, gauss_3d
from .elastizitaet import zell_gradienten, zellsteifigkeit
from .gitter import CUT, INSIDE

try:
    import numba
    _NUMBA = True
except ImportError:                                            # pragma: no cover - CI ohne numba
    numba = None
    _NUMBA = False


class Zelldaten:
    """Freiheitsgradtabelle, Inzidenz und Zellmatrizen eines Gitters."""

    def __init__(self, gitter, quadratur, E: float, nu: float) -> None:
        g = gitter
        p = int(g.p)
        m = anzahl_moden(p)
        # Referenz-Zellmatrix fuer eine Zelle der Kantenlaenge h (Ebene 0): Tensor-Gauss (p+1)^3 ist
        # fuer Polynome vom Grad 2p exakt, also identisch mit der Quadratur der INSIDE-Zellen
        xi, w = gauss_3d(p + 1)
        _, dN = basis_3d(p, xi)
        h0 = float(g.h)
        K_ref = zellsteifigkeit(dN * (2.0 / h0), w * (0.5 * h0) ** 3, E, nu)
        innen = np.flatnonzero(g.klasse == INSIDE).astype(np.int64)
        cut = np.flatnonzero(g.klasse == CUT).astype(np.int64)
        n3 = 3 * m
        K_cut = np.empty((len(cut), n3, n3))
        for i, c in enumerate(cut):
            G, W = zell_gradienten(g, quadratur, int(c))
            K_cut[i] = zellsteifigkeit(G, W, E, nu)
        self._einrichten(g, m, K_ref, innen, cut, K_cut)

    def _einrichten(self, g, m: int, K_ref: np.ndarray, innen: np.ndarray, cut: np.ndarray, K_cut: np.ndarray) -> None:
        self.gitter = g
        self.m = m
        nz = len(g.ijk)
        n3 = 3 * m
        self.dofs = np.ascontiguousarray((3 * g.zell_moden[:, :, None] + np.arange(3)).reshape(nz, n3), dtype=np.int32)
        self.K_ref = np.ascontiguousarray(K_ref)
        self.innen = innen
        self.skala_innen = np.ascontiguousarray(0.5 ** g.ebene[innen].astype(float))            # h_l/h_0
        self.cut = cut
        self.K_cut = np.ascontiguousarray(K_cut)
        # Inzidenz Freiheitsgrad -> (Zelle, lokal), CSR ueber alle Zellen (auch OUTSIDE gibt es nicht)
        flach = self.dofs.ravel()
        reihen = np.argsort(flach, kind="stable")
        self.inz_zelle = np.ascontiguousarray((reihen // n3).astype(np.int64))
        self.inz_lokal = np.ascontiguousarray((reihen % n3).astype(np.int64))
        self.inz_zeiger = np.searchsorted(flach[reihen], np.arange(g.n_dof + 1)).astype(np.int64)
        self.statistik = {"zellen_innen": int(len(self.innen)), "zellen_cut": int(len(self.cut)),
                          "speicher_zellmatrizen_mb": round(self.K_cut.nbytes / 1e6, 1),
                          "speicher_inzidenz_mb": round((self.inz_zelle.nbytes + self.inz_lokal.nbytes + self.inz_zeiger.nbytes) / 1e6, 1)}

    @classmethod
    def teilraum(cls, fein: "Zelldaten", gitter_grob, sub: np.ndarray) -> "Zelldaten":
        """Zelldaten eines groeberen Polynomgrads aus den feinen: die Zellmatrizen sind Teilbloecke
        (hierarchische Basis: der Raum vom Grad p-1 sind die Moden mit Indizes <= p-1), keine neue
        Integration. ``sub``: feiner lokaler Modenindex je grobem lokalen Mode."""
        sub3 = (3 * np.asarray(sub, int)[:, None] + np.arange(3)).ravel()
        z = cls.__new__(cls)
        z._einrichten(gitter_grob, len(sub), fein.K_ref[np.ix_(sub3, sub3)], fein.innen, fein.cut,
                      fein.K_cut[:, sub3][:, :, sub3] if len(fein.cut) else np.empty((0, len(sub3), len(sub3))))
        return z

    def matrix(self) -> sp.csr_matrix:
        """Assemblierte Matrix aus denselben Zellmatrizen (Pruefung gegen elastizitaet.assemblieren)."""
        n = self.gitter.n_dof
        n3 = 3 * self.m
        bloecke = []
        for i, c in enumerate(self.innen):
            bloecke.append((int(c), self.skala_innen[i] * self.K_ref))
        for i, c in enumerate(self.cut):
            bloecke.append((int(c), self.K_cut[i]))
        zeilen = np.concatenate([np.repeat(self.dofs[c], n3) for c, _ in bloecke])
        spalten = np.concatenate([np.tile(self.dofs[c], n3) for c, _ in bloecke])
        werte = np.concatenate([Ke.ravel() for _, Ke in bloecke])
        K = sp.coo_matrix((werte, (zeilen, spalten)), shape=(n, n)).tocsr()
        K.sum_duplicates()
        return K


if _NUMBA:
    @numba.njit(parallel=True, cache=True)
    def _zellkern(u, dofs, innen, skala, K_ref, cut, K_cut, puffer):      # pragma: no cover - numba
        n3 = dofs.shape[1]
        for i in numba.prange(len(innen)):
            c = innen[i]
            ue = np.empty(n3)
            for a in range(n3):
                ue[a] = u[dofs[c, a]]
            s = skala[i]
            for a in range(n3):
                acc = 0.0
                for b in range(n3):
                    acc += K_ref[a, b] * ue[b]
                puffer[c, a] = s * acc
        for i in numba.prange(len(cut)):
            c = cut[i]
            ue = np.empty(n3)
            for a in range(n3):
                ue[a] = u[dofs[c, a]]
            for a in range(n3):
                acc = 0.0
                for b in range(n3):
                    acc += K_cut[i, a, b] * ue[b]
                puffer[c, a] = acc

    @numba.njit(parallel=True, cache=True)
    def _einsammeln(puffer, inz_zeiger, inz_zelle, inz_lokal, v):          # pragma: no cover - numba
        for d in numba.prange(len(v)):
            acc = 0.0
            for j in range(inz_zeiger[d], inz_zeiger[d + 1]):
                acc += puffer[inz_zelle[j], inz_lokal[j]]
            v[d] = acc


class Operator:
    """v = K u ueber die Zelldaten; mit C und K_rand auch der freie Operator C^T (K + K_rand) C."""

    def __init__(self, zelldaten: Zelldaten, C: sp.spmatrix | None = None, K_rand: sp.spmatrix | None = None) -> None:
        self.z = zelldaten
        self.n = int(zelldaten.gitter.n_dof)
        self.C = C.tocsr() if C is not None else None
        self.CT = self.C.T.tocsr() if C is not None else None
        self.K_rand = K_rand.tocsr() if K_rand is not None else None
        self.numba = _NUMBA
        self._puffer = np.zeros((len(zelldaten.gitter.ijk), 3 * zelldaten.m))

    def anwenden(self, u: np.ndarray) -> np.ndarray:
        u = np.ascontiguousarray(u, dtype=float)
        z = self.z
        v = np.empty(self.n)
        if self.numba:
            _zellkern(u, z.dofs, z.innen, z.skala_innen, z.K_ref, z.cut, z.K_cut, self._puffer)
            _einsammeln(self._puffer, z.inz_zeiger, z.inz_zelle, z.inz_lokal, v)
            return v
        # numpy-Rueckfall: Blockprodukte, dann Einsammeln ueber die Inzidenz
        if len(z.innen):
            Ue = u[z.dofs[z.innen]]                                              # (ni, 3m)
            self._puffer[z.innen] = (Ue @ z.K_ref.T) * z.skala_innen[:, None]
        if len(z.cut):
            Ue = u[z.dofs[z.cut]]
            self._puffer[z.cut] = np.einsum("iab,ib->ia", z.K_cut, Ue)
        beitrag = self._puffer[z.inz_zelle, z.inz_lokal]
        v[:] = np.add.reduceat(beitrag, z.inz_zeiger[:-1])
        return v

    def voll_anwenden(self, u: np.ndarray) -> np.ndarray:
        """(K + K_rand) u auf dem vollen Vektor."""
        v = self.anwenden(u)
        if self.K_rand is not None:
            v = v + self.K_rand @ u
        return v

    def frei_anwenden(self, x: np.ndarray) -> np.ndarray:
        """A x = C^T (K + K_rand) C x auf den freien Freiheitsgraden."""
        if self.C is None:
            return self.voll_anwenden(x)
        return self.CT @ self.voll_anwenden(self.C @ x)


__all__ = ["Zelldaten", "Operator"]
