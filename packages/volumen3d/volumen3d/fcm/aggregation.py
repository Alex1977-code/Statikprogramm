"""Zellaggregation fuer kleine Schnittzellen (Vorgabe Abschnitt 8.3, Gegenmassnahme 1).

Befund (Patch-Test, 27.09.2026): Zellen mit Werkstoffanteil 2,8e-5 (und drei mit 0) treiben
den Fehler der FCM-Loesung auf alpha/Anteil - bei alpha = 1e-8 also 1e-2 statt 1e-6. Der
Faktor alpha allein regularisiert die Matrix, aber die Moden solcher Zellen haben kaum
Werkstoff unter sich und schwingen im fiktiven Gebiet frei.

Abhilfe nach dem Prinzip der aggregierten finiten Elemente (Badia, Verdugo, Martin 2018):
eine Zelle mit Anteil < Schwelle ist "schlecht gestellt" und bekommt eine wohlgestellte
Wurzelzelle (Nachbar mit dem groessten Anteil, ueber Flaeche vor Kante vor Ecke; Ketten
werden zur letzten Wurzel aufgeloest). Ein Mode ist schlecht gestellt, wenn keine
wohlgestellte Zelle ihn traegt; er wird an die **Fortsetzung des Wurzelpolynoms** gebunden:
in der Modalbasis der schlechten Zelle sind die Koeffizienten der Fortsetzung eine lineare
Abbildung M = V_c^-1 V_R(Punkte von c) der Wurzelmoden (Vandermonde an Tensor-Chebyshev-
Lobatto-Punkten; gleiche Zellgroesse, also gleicher Polynomgrad). Freie Moden bleiben frei.
Lineare Felder werden von der Fortsetzung exakt reproduziert, darum bleibt der Patch-Test
exakt; die Konditionszahl wird von der Schnittlage unabhaengig.

Ergebnis ist eine Zwangsmatrix C (n_dof x n_frei): K_red = C^T K C, f_red = C^T f, U = C U_red.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from .basis import anzahl_moden, basis_3d
from .gitter import CUT

_NACHBARN = sorted(((dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1) if (dx, dy, dz) != (0, 0, 0)),
                   key=lambda v: (abs(v[0]) + abs(v[1]) + abs(v[2])))     # Flaechen-, dann Kanten-, dann Eckennachbarn


def werkstoffanteile(gitter, quadratur) -> np.ndarray:
    """Werkstoffvolumen je aktiver Zelle geteilt durch h^3 (ohne den Faktor 1-alpha)."""
    a = np.ones(len(gitter.ijk))
    skal = 1.0 / ((1.0 - quadratur.alpha) * gitter.h ** 3)
    for c in np.flatnonzero(gitter.klasse == CUT):
        P, W, I = quadratur.zelle(c)
        a[c] = float(W[I].sum()) * skal if len(W) else 0.0
    return a


def _chebyshev_lobatto_3d(p: int) -> np.ndarray:
    x = -np.cos(np.pi * np.arange(p + 1) / p) if p > 0 else np.zeros(1)
    return np.stack(np.meshgrid(x, x, x, indexing="ij"), axis=-1).reshape(-1, 3)


class Zellaggregation:
    def __init__(self, gitter, quadratur, schwelle: float = 0.25) -> None:
        self.gitter = gitter
        self.schwelle = float(schwelle)
        self.anteil = werkstoffanteile(gitter, quadratur)
        self.wurzel = np.full(len(gitter.ijk), -1, int)             # -1: wohlgestellt oder ohne Wurzel
        self.schlecht = self.anteil < self.schwelle
        self._wurzeln_zuordnen()
        self.C, self.statistik = self._zwangsmatrix()

    # -- Zellen ------------------------------------------------------------------------
    def _nachbar(self, c: int, d) -> int:
        I = self.gitter.ijk[c] + np.asarray(d)
        if np.any(I < 0) or np.any(I >= self.gitter.n):
            return -1
        return int(self.gitter._aktiv_index[self.gitter.flach(I)])

    def _wurzeln_zuordnen(self) -> None:
        offen = list(np.flatnonzero(self.schlecht))
        # 1. Runde: direkt an einen wohlgestellten Nachbarn (bester Anteil, Flaeche vor Kante vor Ecke)
        rest = []
        for c in offen:
            beste, best_anteil, best_rang = -1, -1.0, 99
            for rang, d in enumerate(_NACHBARN):
                n = self._nachbar(c, d)
                if n < 0 or self.schlecht[n]:
                    continue
                stufe = abs(d[0]) + abs(d[1]) + abs(d[2])
                if (stufe, -self.anteil[n]) < (best_rang, -best_anteil):
                    beste, best_anteil, best_rang = n, self.anteil[n], stufe
            if beste >= 0:
                self.wurzel[c] = beste
            else:
                rest.append(c)
        # weitere Runden: ueber schon zugeordnete schlechte Nachbarn (Ketten)
        while rest:
            neu = []
            fortschritt = False
            for c in rest:
                kandidaten = [self.wurzel[self._nachbar(c, d)] for d in _NACHBARN
                              if self._nachbar(c, d) >= 0 and self.wurzel[self._nachbar(c, d)] >= 0]
                if kandidaten:
                    self.wurzel[c] = max(kandidaten, key=lambda r: self.anteil[r])
                    fortschritt = True
                else:
                    neu.append(c)
            rest = neu
            if not fortschritt:
                break                                                 # isolierte Zellen ohne Werkstoffnachbar

    # -- Moden --------------------------------------------------------------------------
    def _fortsetzung(self, c: int, r: int) -> np.ndarray:
        """M (m,m): Modenkoeffizienten der Zelle c aus den Koeffizienten der Wurzel r
        (Fortsetzung des Wurzelpolynoms), M = V_c^-1 V_r(Punkte von c)."""
        g = self.gitter
        xi_c = _chebyshev_lobatto_3d(g.p)
        lo_c, hi_c = g.zellbox(c)
        X = lo_c + 0.5 * (xi_c + 1.0) * (hi_c - lo_c)
        Vc, _ = basis_3d(g.p, xi_c)
        Vr, _ = basis_3d(g.p, g.lokal(X, np.full(len(X), r)))
        return np.linalg.solve(Vc, Vr)

    def _zwangsmatrix(self) -> tuple[sp.csr_matrix, dict]:
        g = self.gitter
        m = anzahl_moden(g.p)
        n_moden = g.n_moden
        wohl_mode = np.zeros(n_moden, bool)
        for c in np.flatnonzero(~self.schlecht):
            wohl_mode[g.zell_moden[c]] = True
        schlecht_mode = ~wohl_mode
        # Eigentuemer je schlechtem Mode: schlechte Zelle mit Wurzel, Wurzel mit groesstem Anteil zuerst
        eigentuemer = np.full(n_moden, -1, int)
        reihenfolge = sorted(np.flatnonzero(self.schlecht & (self.wurzel >= 0)), key=lambda c: -self.anteil[self.wurzel[c]])
        for c in reihenfolge:
            for i in g.zell_moden[c]:
                if schlecht_mode[i] and eigentuemer[i] < 0:
                    eigentuemer[i] = c
        gebunden = schlecht_mode & (eigentuemer >= 0)
        frei = ~gebunden
        neu_nr = np.cumsum(frei) - 1                                   # freie Moden fortlaufend
        n_frei = int(frei.sum())
        Z, S, V = [], [], []
        fi = np.flatnonzero(frei)
        for a in range(3):
            Z.append(3 * fi + a)
            S.append(3 * neu_nr[fi] + a)
            V.append(np.ones(len(fi)))
        for c in reihenfolge:
            eigene = np.flatnonzero(eigentuemer[g.zell_moden[c]] == c)
            if len(eigene) == 0:
                continue
            M = self._fortsetzung(c, int(self.wurzel[c]))
            wurzel_moden = g.zell_moden[int(self.wurzel[c])]
            for i_loc in eigene:
                i = g.zell_moden[c, i_loc]
                koeff = M[i_loc]
                nz = np.flatnonzero(np.abs(koeff) > 1e-14)
                for a in range(3):
                    Z.append(np.full(len(nz), 3 * i + a))
                    S.append(3 * neu_nr[wurzel_moden[nz]] + a)
                    V.append(koeff[nz])
        C = sp.coo_matrix((np.concatenate(V), (np.concatenate(Z), np.concatenate(S))), shape=(3 * n_moden, 3 * n_frei)).tocsr()
        stat = {"schwelle": self.schwelle, "zellen_schlecht": int(self.schlecht.sum()),
                "zellen_ohne_wurzel": int((self.schlecht & (self.wurzel < 0)).sum()),
                "moden_gebunden": int(gebunden.sum()), "moden_frei": n_frei,
                "anteil_min": float(self.anteil.min()),
                "anteil_min_wohl": float(self.anteil[~self.schlecht].min()) if (~self.schlecht).any() else 0.0}
        return C, stat


__all__ = ["werkstoffanteile", "Zellaggregation"]
