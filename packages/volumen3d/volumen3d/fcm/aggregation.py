"""Zellaggregation fuer kleine Schnittzellen (Vorgabe Abschnitt 8.3, Gegenmassnahme 1).

Befund (Patch-Test, 27.09.2026): Zellen mit Werkstoffanteil 2,8e-5 (und drei mit 0) treiben
den Fehler der FCM-Loesung auf alpha/Anteil - bei alpha = 1e-8 also 1e-2 statt 1e-6. Der
Faktor alpha allein regularisiert die Matrix, aber die Moden solcher Zellen haben kaum
Werkstoff unter sich und schwingen im fiktiven Gebiet frei.

Abhilfe nach dem Prinzip der aggregierten finiten Elemente (Badia, Verdugo, Martin 2018):
eine Zelle mit Anteil < Schwelle ist "schlecht gestellt" und bekommt eine wohlgestellte
Wurzelzelle (Nachbar mit dem groessten Anteil, ueber Flaeche vor Kante vor Ecke; Ketten
werden zur letzten Wurzel aufgeloest; Nachbarn ueber die Punktsuche, damit auch Blaetter
anderer Ebenen gefunden werden). Ein Mode ist schlecht gestellt, wenn keine wohlgestellte
Zelle ihn traegt; er wird an die **Fortsetzung des Wurzelpolynoms** gebunden: in der
Modalbasis der schlechten Zelle sind die Koeffizienten der Fortsetzung eine lineare Abbildung
M = V_c^-1 V_R(Punkte von c) der Wurzelmoden (Vandermonde an Tensor-Chebyshev-Lobatto-Punkten;
bei verschiedener Zellgroesse ist die Fortsetzung weiterhin ein Polynom vom Grad p). Freie
Moden bleiben frei. Lineare Felder werden von der Fortsetzung exakt reproduziert, darum bleibt
der Patch-Test exakt; die Konditionszahl wird von der Schnittlage unabhaengig.

Die Rohzwaenge (Mode -> Wurzelmoden mit Koeffizienten) verarbeitet fcm/zwaenge.py zusammen
mit den haengenden Freiheitsgraden zur Zwangsmatrix.
"""
from __future__ import annotations

import numpy as np

from .basis import basis_3d
from .gitter import CUT

_NACHBARN = sorted(((dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1) if (dx, dy, dz) != (0, 0, 0)),
                   key=lambda v: (abs(v[0]) + abs(v[1]) + abs(v[2])))     # Flaechen-, dann Kanten-, dann Eckennachbarn


def werkstoffanteile(gitter, quadratur) -> np.ndarray:
    """Werkstoffvolumen je aktiver Zelle geteilt durch h_c^3 (ohne den Faktor 1-alpha)."""
    a = np.ones(len(gitter.ijk))
    for c in np.flatnonzero(gitter.klasse == CUT):
        P, W, I = quadratur.zelle(c)
        skal = 1.0 / ((1.0 - quadratur.alpha) * float(gitter.h_zelle(c)) ** 3)
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
        self.statistik = {"schwelle": self.schwelle, "zellen_schlecht": int(self.schlecht.sum()),
                          "zellen_ohne_wurzel": int((self.schlecht & (self.wurzel < 0)).sum()),
                          "moden_gebunden": 0, "anteil_min": float(self.anteil.min()),
                          "anteil_min_wohl": float(self.anteil[~self.schlecht].min()) if (~self.schlecht).any() else 0.0}

    # -- Zellen ------------------------------------------------------------------------
    def _nachbar(self, c: int, d) -> int:
        """Blatt hinter der Flaeche/Kante/Ecke in Richtung d (per Punktsuche, ebenenunabhaengig)."""
        lo, hi = self.gitter.zellbox(c)
        m = 0.5 * (lo + hi)
        hl = float(self.gitter.h_zelle(c))
        P = m + (0.5 * hl + 1e-4 * hl) * np.asarray(d, float)
        return int(self.gitter.zelle_finden(P[None])[0])

    def _wurzeln_zuordnen(self) -> None:
        offen = list(np.flatnonzero(self.schlecht))
        rest = []
        for c in offen:
            beste, best_schluessel = -1, (99, 99, 0.0)
            for d in _NACHBARN:
                n = self._nachbar(c, d)
                if n < 0 or n == c or self.schlecht[n]:
                    continue
                stufe = abs(d[0]) + abs(d[1]) + abs(d[2])
                # Wurzeln auf gleicher oder groeberer Ebene zuerst: eine feinere Wurzel koennte an der
                # aggregierten Zelle haengen, und die Zwangsketten wuerden zirkulaer (fcm/zwaenge.py)
                feiner = 1 if self.gitter.ebene[n] > self.gitter.ebene[c] else 0
                schluessel = (feiner, stufe, -self.anteil[n])
                if schluessel < best_schluessel:
                    beste, best_schluessel = n, schluessel
            if beste >= 0:
                self.wurzel[c] = beste
            else:
                rest.append(c)
        while rest:
            neu = []
            fortschritt = False
            for c in rest:
                kandidaten = []
                for d in _NACHBARN:
                    n = self._nachbar(c, d)
                    if n >= 0 and n != c and self.wurzel[n] >= 0:
                        kandidaten.append(self.wurzel[n])
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

    def roh_zwaenge(self, bereits: set | None = None) -> dict[int, list[tuple[int, float]]]:
        """Mode -> [(Wurzelmode, Koeffizient)] fuer schlecht gestellte Moden, die nicht schon
        (durch haengende Entitaeten) gebunden sind."""
        bereits = bereits or set()
        g = self.gitter
        wohl_mode = np.zeros(g.n_moden, bool)
        for c in np.flatnonzero(~self.schlecht):
            wohl_mode[g.zell_moden[c]] = True
        eigentuemer = np.full(g.n_moden, -1, int)
        reihenfolge = sorted(np.flatnonzero(self.schlecht & (self.wurzel >= 0)), key=lambda c: -self.anteil[self.wurzel[c]])
        for c in reihenfolge:
            for i in g.zell_moden[c]:
                if not wohl_mode[i] and eigentuemer[i] < 0 and int(i) not in bereits:
                    eigentuemer[i] = c
        roh: dict[int, list[tuple[int, float]]] = {}
        for c in reihenfolge:
            eigene = np.flatnonzero(eigentuemer[g.zell_moden[c]] == c)
            if len(eigene) == 0:
                continue
            M = self._fortsetzung(c, int(self.wurzel[c]))
            wurzel_moden = g.zell_moden[int(self.wurzel[c])]
            for i_loc in eigene:
                koeff = M[i_loc]
                nz = np.flatnonzero(np.abs(koeff) > 1e-14)
                roh[int(g.zell_moden[c, i_loc])] = [(int(wurzel_moden[j]), float(koeff[j])) for j in nz]
        self.statistik["moden_gebunden"] = len(roh)
        return roh


__all__ = ["werkstoffanteile", "Zellaggregation"]
