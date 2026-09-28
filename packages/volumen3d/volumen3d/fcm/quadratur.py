"""Zellquadratur (Vorgabe Abschnitt 6, Entwurf 3.5).

INSIDE-Zellen: Tensor-Gauss (p+1)^3. CUT-Zellen: rekursive Oktantteilung; eine Teilbox ist
sicher innen/aussen, wenn |d(Mitte)| die halbe Raumdiagonale uebersteigt (konservative
CSG-Abstaende, geometry/csg.py). Geschnittene Teilboxen werden **ebenen-exakt** integriert:
die Geometrie nennt ihre lokalen konvexen Stuecke (Box ∩ Halbraeume; Halbraum und
Quaderseiten exakt, Zylinder und Kugel als Tangentialebene), jedes Stueck wird geclippt, in
Tetraeder zerlegt und mit der konischen Produktregel exakt bis Gesamtgrad 3p-1 integriert.
Ebene Geometrie ist damit auf jeder Tiefe exakt; gekruemmte Flaechen werden bis ``tiefe``
geteilt (Fehler O(Kruemmung * Blattkante^2)).

Fiktives Gebiet ohne negative Gewichte: die ganze Teilbox mit Gauss (p+1)^3 und Gewicht
alpha, die Werkstoffstuecke mit Gewicht (1 - alpha). Kann die Geometrie die lokale Semantik
nicht rekonstruieren, teilt die Rekursion ``tiefe_punkttest`` Stufen tiefer und faellt auf
den Punkttest der Vorgabe zurueck (Gewicht alpha ausserhalb); ``statistik`` zaehlt das.

Punkte und Gewichte je Zelle werden einmal berechnet und gehalten (fuer alle Lastfaelle
gleich); Basiswerte nicht (Speicher).
"""
from __future__ import annotations

import numpy as np

from ..geometry.polyeder import box_flaechen, clippen, polyeder_quadratur
from .basis import gauss_3d
from .gitter import INSIDE


class Zellquadratur:
    def __init__(self, gitter, p: int, tiefe: int = 2, alpha: float = 1e-8, ordnung: int | None = None,
                 tiefe_punkttest: int = 2, ordnung_tet: int | None = None) -> None:
        if tiefe < 0 or tiefe_punkttest < 0:
            raise ValueError("tiefe und tiefe_punkttest muessen >= 0 sein")
        if not 0.0 <= alpha < 1.0:
            raise ValueError("alpha muss in [0, 1) liegen")
        self.gitter = gitter
        self.p = p
        self.tiefe = tiefe
        self.tiefe_punkttest = tiefe_punkttest
        self.alpha = alpha
        self.ordnung = ordnung or (p + 1)
        # Gesamtgrad 3p-1 fuer int grad(v) exakt (Patch-Test): 2n-1 >= 3p-1
        self.ordnung_tet = ordnung_tet or max(2, int(np.ceil(1.5 * p)))
        self._X, self._W = gauss_3d(self.ordnung)
        self._cache: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        self.statistik = {"blaetter_eben": 0, "blaetter_tangential": 0, "blaetter_punkttest": 0, "stuecke": 0,
                          "blaetter_unteraufgeloest": 0}
        self.punkttest_orte: list[tuple[np.ndarray, float]] = []     # Mitte und Radius der Rueckfall-Blaetter

    # -- je Zelle -------------------------------------------------------------------
    def zelle(self, c: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(punkte (nq,3) global, gewichte (nq,) inkl. Jacobi und alpha, innen (nq,) bool)."""
        aus = self._cache.get(c)
        if aus is not None:
            return aus
        lo, hi = self.gitter.zellbox(c)
        if self.gitter.klasse[c] == INSIDE:
            s = 0.5 * (hi - lo)
            P = lo + s * (self._X + 1.0)
            W = self._W * float(np.prod(s))
            aus = (P, W, np.ones(len(P), bool))
        else:
            teile: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
            self._teilbox(lo, hi, 0, teile)
            teile = [t for t in teile if len(t[0])]
            if not teile:                                    # zu vorsichtig als CUT eingestuft, alpha = 0
                aus = (np.zeros((0, 3)), np.zeros(0), np.zeros(0, bool))
            else:
                aus = (np.concatenate([t[0] for t in teile]), np.concatenate([t[1] for t in teile]),
                       np.concatenate([t[2] for t in teile]))
        self._cache[c] = aus
        return aus

    def _box(self, lo, s):
        return lo + s * (self._X + 1.0), self._W * float(np.prod(s))

    _KINDER = np.array([(dx, dy, dz) for dx in (0, 1) for dy in (0, 1) for dz in (0, 1)], float)

    def _teilen(self, lo, s, stufe, teile) -> None:
        # die acht Kinder in einem Abstandsaufruf klassifizieren (Aufgabe 5 des Plans TP 2)
        los = lo + s * self._KINDER
        d8 = self.gitter.geometrie.abstand(los + 0.5 * s)
        for l2, d in zip(los, d8):
            self._teilbox(l2, l2 + s, stufe + 1, teile, float(d))

    def _teilbox(self, lo, hi, stufe, teile, d: float | None = None) -> None:
        s = 0.5 * (hi - lo)
        m = lo + s
        geo = self.gitter.geometrie
        if d is None:
            d = float(geo.abstand(m[None])[0])
        r = np.sqrt(3.0) * float(s[0]) * (1 + 1e-9)
        P, W = self._box(lo, s)
        if d > r:                                            # sicher ausserhalb: nur alpha
            if self.alpha > 0:
                teile.append((P, self.alpha * W, np.zeros(len(P), bool)))
            return
        if d < -r:                                           # sicher innen
            # in CUT-Zellen auch hier Werkstoff (1-alpha) plus fiktiv alpha, damit alle
            # Werkstoffpunkte einheitlich skaliert sind (alpha_entfernen, werkstoffanteile)
            teile.append((P, (1.0 - self.alpha) * W, np.ones(len(P), bool)))
            if self.alpha > 0:
                teile.append((P, self.alpha * W, np.zeros(len(P), bool)))
            return
        stuecke = geo.lokale_stuecke(m, r, P)
        if stuecke is not None:
            ebenen, gekruemmt = stuecke[0], stuecke[1]
            # Kleiner Kruemmungsradius: der Tangentialfehler ist ~0,25 (Blattkante/R)^2, also 1 %
            # erst ab R >= 5 Blattkanten (Gutachten 27.09.: Bohrung R 3 bei h 10 mit Tiefe 2 ->
            # Lochvolumen -5,8 %). Dann bis zur Hoechsttiefe weiter teilen; was danach noch zu
            # grob ist, wird gezaehlt (Protokoll) - die Abhilfe ist die Oktree-Verfeinerung (TP 2).
            a = 2.0 * float(s[0])
            zu_grob = any(f.kruemmungsradius < 5.0 * a for f in stuecke[2])
            if (gekruemmt and stufe < self.tiefe) or (zu_grob and stufe < self.tiefe + self.tiefe_punkttest):
                self._teilen(lo, s, stufe, teile)
                return
            self._stuecke_integrieren(lo, hi, ebenen, P, W, teile)
            self.statistik["blaetter_tangential" if gekruemmt else "blaetter_eben"] += 1
            if zu_grob:
                self.statistik["blaetter_unteraufgeloest"] = self.statistik.get("blaetter_unteraufgeloest", 0) + 1
            return
        if stufe < self.tiefe + self.tiefe_punkttest:
            self._teilen(lo, s, stufe, teile)
            return
        innen = geo.innen(P)                                 # Rueckfall: Punkttest der Vorgabe
        teile.append((P, np.where(innen, (1.0 - self.alpha) * W, self.alpha * W), innen))
        self.statistik["blaetter_punkttest"] += 1
        self.punkttest_orte.append((m.copy(), r))

    def _stuecke_integrieren(self, lo, hi, ebenen, P, W, teile) -> None:
        tol = 1e-12 * float(hi[0] - lo[0])
        for halbraeume in ebenen:
            achsparallel = all(np.abs(np.abs(n).max() - 1.0) < 1e-12 for _, n in halbraeume)
            if achsparallel:
                # Box ∩ achsparallele Halbraeume ist eine Teilbox: Tensor-Gauss statt Tetraeder
                # (Platten und Quader: 64 statt ~1500 Punkte je Zelle, exakt bis Grad 2p+1)
                b_lo, b_hi = np.asarray(lo, float).copy(), np.asarray(hi, float).copy()
                for punkt, n in halbraeume:
                    d = int(np.argmax(np.abs(n)))
                    if n[d] > 0:
                        b_hi[d] = min(b_hi[d], punkt[d])
                    else:
                        b_lo[d] = max(b_lo[d], punkt[d])
                if np.any(b_hi - b_lo <= tol):
                    continue
                s2 = 0.5 * (b_hi - b_lo)
                Pt, Wt = b_lo + s2 * (self._X + 1.0), self._W * float(np.prod(s2))
            else:
                flaechen = box_flaechen(lo, hi)
                for punkt, normale in halbraeume:
                    flaechen = clippen(flaechen, punkt, normale, tol)
                    if not flaechen:
                        break
                if not flaechen:
                    continue
                Pt, Wt = polyeder_quadratur(flaechen, self.ordnung_tet)
            if len(Pt):
                teile.append((Pt, (1.0 - self.alpha) * Wt, np.ones(len(Pt), bool)))
                self.statistik["stuecke"] += 1
        if self.alpha > 0:
            teile.append((P, self.alpha * W, np.zeros(len(P), bool)))

    def alpha_entfernen(self, zellen) -> None:
        """Fuer die genannten Zellen (aggregierte, schlecht geschnittene) die alpha-Punkte
        streichen und die Werkstoffstuecke von (1 - alpha) auf 1 heben.

        Grund (Patch-Test 27.09.2026): die alpha-Steifigkeit einer gebundenen Zelle wirkt auf
        die *Fortsetzung* des Wurzelpolynoms, und die waechst ausserhalb der Wurzelzelle wie
        (2 xi)^p - der alpha-Fehler stieg damit von 3e-8 auf 2e-5 (p = 2) bzw. 1e-4 (p = 3).
        Gebundene Moden brauchen keine Regularisierung; ihr Werkstoff wird exakt integriert.
        """
        for c in np.asarray(zellen, int):
            P, W, I = self.zelle(int(c))
            if I.all():
                continue
            skal = 1.0 / (1.0 - self.alpha) if self.alpha < 1.0 else 1.0
            self._cache[int(c)] = (P[I], W[I] * skal, np.ones(int(I.sum()), bool))
        self.statistik["zellen_ohne_alpha"] = int(len(zellen))

    # -- Kontrollgroessen ------------------------------------------------------------
    def volumen(self) -> float:
        """Integriertes Werkstoffvolumen (Punkte im Werkstoff; bei alpha > 0 mit Faktor 1-alpha)."""
        return float(sum(self.zelle(c)[1][self.zelle(c)[2]].sum() for c in range(len(self.gitter.ijk))))

    def volumen_fiktiv(self) -> float:
        """Summe der alpha-gewichteten Gewichte, zur Ausweisung im Protokoll."""
        return float(sum(self.zelle(c)[1][~self.zelle(c)[2]].sum() for c in range(len(self.gitter.ijk))))

    def anzahl_punkte(self) -> int:
        return int(sum(len(self.zelle(c)[0]) for c in range(len(self.gitter.ijk))))


__all__ = ["Zellquadratur"]
