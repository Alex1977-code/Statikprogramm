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

Moment Fitting (Vorgabe 6 Stufe 2, fcm/momentfitting.py): mit ``momentfitting`` dient die rekursive
Integration einer Schnittzelle nur noch als Referenz fuer die Momente der Werkstoffdomaene; gehalten wird
die gefittete Regel auf den Tensor-Gauss-Punkten (q+1)^3 der Zelle (``innen`` heisst dann: traegt
Werkstoffgewicht, der Punkt selbst kann ausserhalb liegen) plus ein Satz alpha-Punkte (p+1)^3 fuer die
ganze Zelle - derselbe Wert wie die alpha-Punkte aller Blaetter, da beide Regeln bis Grad 2p+1 exakt sind.
Plastische Koerper brauchen nach Vertrag 6a die Unterteilung: der Schalter bleibt.

Punkte und Gewichte je Zelle werden einmal berechnet und gehalten (fuer alle Lastfaelle
gleich); Basiswerte nicht (Speicher).
"""
from __future__ import annotations

import numpy as np

from ..geometry.polyeder import box_flaechen, clippen, polyeder_quadratur
from .basis import gauss_3d
from .gitter import INSIDE
from .momentfitting import fit_grad_standard, gefittete_regel

# Vorgabe fuer neue Zellquadraturen (Anwender 30.09.2026, Plan TP 5 B1, Theorie 11.11): mit q = 2p sind die
# Zellmatrizen dieselben wie mit der rekursiven Integration (2e-13 an jeder Schnittzelle), bei 17- bis 34-mal
# weniger Punkten an gekruemmten Raendern (Lame h 20 p 3: 10 541 -> 306 je Schnittzelle). False schaltet zurueck -
# plastische Koerper brauchen nach Vertrag 6a die Unterteilung (im Paket noch keine Plastizitaet).
MOMENTFITTING_STANDARD = True


class Zellquadratur:
    def __init__(self, gitter, p: int, tiefe: int = 2, alpha: float = 1e-8, ordnung: int | None = None,
                 tiefe_punkttest: int = 2, ordnung_tet: int | None = None, momentfitting: bool | None = None,
                 fit_grad: int | None = None) -> None:
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
        self.momentfitting = MOMENTFITTING_STANDARD if momentfitting is None else bool(momentfitting)
        self.fit_grad = int(fit_grad) if fit_grad is not None else fit_grad_standard(p)
        if self.momentfitting:
            self.statistik.update({"fit_grad": self.fit_grad, "fit_zellen": 0, "fit_nnls": 0, "fit_rueckfall": 0,
                                   "fit_min_gewicht": 1.0, "fit_neg_anteil_max": 0.0,
                                   "punkte_referenz": 0, "punkte_gefittet": 0})

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
                if self.momentfitting and aus[2].any():
                    aus = self._fitten(lo, hi, aus)
        self._cache[c] = aus
        return aus

    def _fitten(self, lo, hi, referenz):
        """Werkstoffteil der Referenzregel durch die gefittete Regel ersetzen, alpha-Teil durch einen Satz."""
        P, W, I = referenz
        st = self.statistik
        st["punkte_referenz"] += int(len(P))
        # nur wo es Punkte spart: achsparallel geschnittene Zellen haben schon (p+1)^3 Punkte (Kragarmsegment 64
        # gegen 343 + 64 gefittet), die Regel ist so oder so exakt
        if len(P) <= (self.fit_grad + 1) ** 3 + (self.ordnung ** 3 if self.alpha > 0 else 0):
            st["fit_unnoetig"] = st.get("fit_unnoetig", 0) + 1
            st["punkte_gefittet"] += int(len(P))
            return referenz
        erg = gefittete_regel(lo, hi, P[I], W[I], self.fit_grad, self.p)
        st["fit_min_gewicht"] = min(st["fit_min_gewicht"], erg.min_gewicht)
        st["fit_neg_anteil_max"] = max(st["fit_neg_anteil_max"], erg.neg_anteil)
        if erg.art == "rueckfall":
            st["fit_rueckfall"] += 1
            st["punkte_gefittet"] += int(len(P))
            return referenz
        st["fit_nnls" if erg.art == "nnls" else "fit_zellen"] += 1
        if self.alpha > 0:
            s = 0.5 * (np.asarray(hi, float) - np.asarray(lo, float))
            Pa, Wa = self._box(np.asarray(lo, float), s)
            aus = (np.concatenate([erg.punkte, Pa]), np.concatenate([erg.gewichte, self.alpha * Wa]),
                   np.concatenate([np.ones(len(erg.punkte), bool), np.zeros(len(Pa), bool)]))
        else:
            aus = (erg.punkte, erg.gewichte, np.ones(len(erg.punkte), bool))
        st["punkte_gefittet"] += int(len(aus[0]))
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
