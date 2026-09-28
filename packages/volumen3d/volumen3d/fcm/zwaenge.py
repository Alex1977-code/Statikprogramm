"""Zwangsaufloeser: haengende Freiheitsgrade des Oktrees und Zellaggregation in einer
Zwangsmatrix C (Entwurf 4b.2).

Haengende Entitaeten: eine Flaeche, Kante oder Ecke einer feinen Zelle F liegt auf dem Rand
einer groeberen Zelle C (2:1-Balancierung: genau eine Ebene groeber). Stetigkeit verlangt, dass
die Spur des Polynoms von F auf der Entitaet die Spur von C ist. Fuer eine haengende Flaeche
werden alle Moden von F, die auf ihr nicht verschwinden (Index 0 bzw. 1 in Normalenrichtung:
4 Ecken, 4 Kanten, Flaecheninneres, zusammen (p+1)^2), aus den Moden von C ausgedrueckt:
M = V_F^-1 N_C(Punkte) mit (p+1)^2 Tensor-Chebyshev-Lobatto-Punkten auf der Flaeche - beidseits
derselbe Tensorraum vom Grad p, die Abbildung ist exakt. Kanten ebenso mit p+1 Punkten, Ecken
als Auswertung der Basis von C am Punkt.

Vorrang Flaeche > Kante > Ecke > Aggregation: ein schon gebundener Mode wird nicht noch einmal
definiert (die Definitionen stimmen ueberein, weil grobe Nachbarn ihre gemeinsamen Entitaeten
teilen). Die Aggregation bindet danach nur noch freie Moden schlecht geschnittener Zellen an
die Fortsetzung des Wurzelpolynoms; so bleibt die Stetigkeit ueber haengende Flaechen erhalten,
und lineare Felder bleiben exakt (beide Vorschriften reproduzieren sie). Ketten (Meister selbst
gebunden) werden durch Einsetzen aufgeloest.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from .basis import basis_3d, modenklassen

_SEITEN = [(d, s) for d in range(3) for s in (-1, 1)]
_KANTEN = [(e, d1, s1, d2, s2) for e in range(3) for d1 in range(3) for d2 in range(3) if d1 < d2 and e not in (d1, d2)
           for s1 in (-1, 1) for s2 in (-1, 1)]
_ECKEN = [(sx, sy, sz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


def _chebyshev_lobatto(p: int) -> np.ndarray:
    return -np.cos(np.pi * np.arange(p + 1) / p) if p > 0 else np.zeros(1)


class Zwaenge:
    def __init__(self, gitter, aggregation=None, eps: float = 1e-4) -> None:
        self.gitter = gitter
        self.aggregation = aggregation
        self.p = int(gitter.p)
        self.eps = eps
        self.roh: dict[int, list[tuple[int, float]]] = {}
        self.statistik = {"haengende_flaechen": 0, "haengende_kanten": 0, "haengende_ecken": 0,
                          "moden_haengend": 0, "moden_aggregiert": 0, "kettenlaenge": 0, "zyklen_frei": 0}
        self._haengende()
        if aggregation is not None:
            for mode, eintraege in aggregation.roh_zwaenge(dict(self.roh)).items():
                self.roh[mode] = eintraege
            self.statistik["moden_aggregiert"] = len(self.roh) - self.statistik["moden_haengend"]
        self._ketten_aufloesen()
        self.C = self._matrix()

    # -- haengende Entitaeten --------------------------------------------------------
    def _idx(self, s: int) -> int:
        return 0 if s < 0 else 1

    def _spur_binden(self, F: int, C: int, moden_lokal: np.ndarray, xi_punkte: np.ndarray) -> int:
        """Moden von F (lokale Indizes, auf der Entitaet nicht verschwindend) aus den Moden von C;
        xi_punkte (k,3) Referenzpunkte von F auf der Entitaet, k = len(moden_lokal). Liefert die
        Zahl neu gebundener Moden."""
        g = self.gitter
        lo, hi = g.zellbox(F)
        X = lo + 0.5 * (xi_punkte + 1.0) * (hi - lo)
        V_F, _ = basis_3d(self.p, xi_punkte)
        V_F = V_F[:, moden_lokal]
        N_C, _ = basis_3d(self.p, g.lokal(X, np.full(len(X), C)))
        M = np.linalg.solve(V_F, N_C)                       # (k, m): Koeffizienten der Moden von C
        moden_F = g.zell_moden[F][moden_lokal]
        moden_C = g.zell_moden[C]
        neu = 0
        for r, i in enumerate(moden_F):
            i = int(i)
            if i in self.roh or i in moden_C:              # schon gebunden oder mit C geteilt (Ecke)
                continue
            koeff = M[r]
            nz = np.flatnonzero(np.abs(koeff) > 1e-13)
            self.roh[i] = [(int(moden_C[j]), float(koeff[j])) for j in nz]
            neu += 1
        return neu

    def _groebster_nachbar(self, P: np.ndarray, ebene: int) -> int:
        n = self.gitter.zelle_finden(P)
        n = n[n >= 0]
        if len(n) == 0:
            return -1
        n = n[self.gitter.ebene[n] < ebene]
        if len(n) == 0:
            return -1
        return int(n[np.argmin(self.gitter.ebene[n])])

    def _haengende(self) -> None:
        g = self.gitter
        abc = modenklassen(self.p)["abc"]
        cl = _chebyshev_lobatto(self.p)
        fein = np.flatnonzero(g.ebene > 0)
        for F in fein:
            l = int(g.ebene[F])
            lo, hi = g.zellbox(F)
            m = 0.5 * (lo + hi)
            hl = float(g.h_zelle(F))
            eps = self.eps * hl
            # Flaechen
            for d, s in _SEITEN:
                P = m.copy()
                P[d] += s * (0.5 * hl + eps)
                C = self._groebster_nachbar(P[None], l)
                if C < 0:
                    continue
                moden = np.flatnonzero(abc[:, d] == self._idx(s))
                a, b = [k for k in range(3) if k != d]
                A, B = np.meshgrid(cl, cl, indexing="ij")
                xi = np.zeros((len(cl) ** 2, 3))
                xi[:, d] = s
                xi[:, a] = A.ravel()
                xi[:, b] = B.ravel()
                neu = self._spur_binden(F, C, moden, xi)
                self.statistik["haengende_flaechen"] += 1          # auch wenn Geschwister die Moden schon banden
                self.statistik["moden_haengend"] += neu
            # Kanten: die drei fremden Quadranten um die Kante absuchen, groebsten Nachbarn nehmen
            for e, d1, s1, d2, s2 in _KANTEN:
                proben = []
                for q1, q2 in ((s1, s2), (s1, -s2), (-s1, s2)):
                    P = m.copy()
                    P[d1] += q1 * (0.5 * hl + (eps if q1 == s1 else -eps))
                    P[d2] += q2 * (0.5 * hl + (eps if q2 == s2 else -eps))
                    if q1 == s1 and q2 == s2:
                        P[d1] = m[d1] + s1 * (0.5 * hl + eps)
                        P[d2] = m[d2] + s2 * (0.5 * hl + eps)
                    proben.append(P)
                C = self._groebster_nachbar(np.asarray(proben), l)
                if C < 0:
                    continue
                moden = np.flatnonzero((abc[:, d1] == self._idx(s1)) & (abc[:, d2] == self._idx(s2)))
                xi = np.zeros((len(cl), 3))
                xi[:, d1] = s1
                xi[:, d2] = s2
                xi[:, e] = cl
                neu = self._spur_binden(F, C, moden, xi)
                if neu:
                    self.statistik["haengende_kanten"] += 1
                    self.statistik["moden_haengend"] += neu
            # Ecken: die sieben fremden Oktanten absuchen
            for sx, sy, sz in _ECKEN:
                v = m + 0.5 * hl * np.array([sx, sy, sz])
                proben = []
                for ox in (-1, 1):
                    for oy in (-1, 1):
                        for oz in (-1, 1):
                            if (ox, oy, oz) == (-sx, -sy, -sz):
                                continue                       # das ist F selbst
                            proben.append(v + eps * np.array([ox, oy, oz]))
                C = self._groebster_nachbar(np.asarray(proben), l)
                if C < 0:
                    continue
                moden = np.flatnonzero((abc[:, 0] == self._idx(sx)) & (abc[:, 1] == self._idx(sy)) & (abc[:, 2] == self._idx(sz)))
                xi = np.array([[sx, sy, sz]], float)
                neu = self._spur_binden(F, C, moden, xi)
                if neu:
                    self.statistik["haengende_ecken"] += 1
                    self.statistik["moden_haengend"] += neu

    # -- Ketten und Matrix -----------------------------------------------------------
    def _ketten_aufloesen(self) -> None:
        """Meister, die selbst gebunden sind, durch Einsetzen ersetzen.

        Selbstbezug (ein Mode haengt ueber Umwege an sich selbst) entsteht, wenn eine feine
        Zelle an einer aggregierten groben Zelle haengt, deren Moden an eben diese feine Zelle
        gebunden sind. Mit Koeffizient 1 ist das eine Tautologie (Spur der Fortsetzung = eigene
        Spur): die Vorschrift ist redundant, der Mode bleibt frei. Sonst wird nach dem Mode
        aufgeloest: u = rest / (1 - c). Die Wurzelwahl der Aggregation (gleiche oder groebere
        Ebene zuerst) macht beides selten; das Protokoll zaehlt es.
        """
        for runde in range(40):
            offen = False
            for mode, eintraege in list(self.roh.items()):
                if not any(mm in self.roh for mm, _ in eintraege):
                    continue
                offen = True
                neu: dict[int, float] = {}
                for mm, k in eintraege:
                    if mm in self.roh:
                        for m2, k2 in self.roh[mm]:
                            neu[m2] = neu.get(m2, 0.0) + k * k2
                    else:
                        neu[mm] = neu.get(mm, 0.0) + k
                if mode in neu:
                    # Selbstbezug. Er entstand nur, wenn eine aggregierte Zelle eine feinere Wurzel
                    # hatte, deren Moden an ihr hingen (test_zwaenge, duenne Wand: 53 Faelle mit
                    # Koeffizient 1 und Rest bis 2,45). Seit die Aggregation keine feineren Wurzeln
                    # mehr waehlt und solche Zellen geteilt werden (aggregation.zu_teilen), sinken
                    # Zwangsketten monoton in der Ebene und koennen nicht zurueckkehren; ein
                    # Selbstbezug ist darum ein Fehler und kein Sonderfall.
                    c = neu.pop(mode)
                    rest = max((abs(k) for k in neu.values()), default=0.0)
                    raise ValueError(f"Zwangszyklus an Mode {mode} (Koeffizient {c:.6g}, Rest {rest:.2e}) - "
                                     f"Wurzelwahl der Aggregation pruefen")
                self.roh[mode] = [(mm, k) for mm, k in neu.items() if abs(k) > 1e-14]
            self.statistik["kettenlaenge"] = runde + 1
            if not offen:
                return
        raise ValueError("Zwangsketten laenger als 40 Stufen")

    def _matrix(self) -> sp.csr_matrix:
        n_moden = self.gitter.n_moden
        gebunden = np.zeros(n_moden, bool)
        gebunden[list(self.roh)] = True
        frei = ~gebunden
        neu_nr = np.cumsum(frei) - 1
        n_frei = int(frei.sum())
        Z, S, V = [], [], []
        fi = np.flatnonzero(frei)
        for a in range(3):
            Z.append(3 * fi + a)
            S.append(3 * neu_nr[fi] + a)
            V.append(np.ones(len(fi)))
        for mode, eintraege in self.roh.items():
            for mm, k in eintraege:
                for a in range(3):
                    Z.append(np.array([3 * mode + a]))
                    S.append(np.array([3 * neu_nr[mm] + a]))
                    V.append(np.array([k]))
        C = sp.coo_matrix((np.concatenate(V), (np.concatenate(Z), np.concatenate(S))), shape=(3 * n_moden, 3 * n_frei)).tocsr()
        self.statistik["moden_frei"] = n_frei
        self.statistik["moden_gebunden"] = int(gebunden.sum())
        self.moden_frei = fi                          # Modennummer je freier Spalte (p-Mehrgitter: Injektion)
        self.spalte_von_mode = neu_nr                 # freie Spalte je Mode (nur fuer freie Moden gueltig)
        return C


__all__ = ["Zwaenge"]
