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

Zellen ohne wohlgestellten Nachbarn erben die Wurzel eines Nachbarn (Ketten). Dabei gilt die
naechstgelegene Wurzel, und die Ketten wachsen schichtweise (jede Runde nur aus den Wurzeln der
Vorrunde). Frueher gewann die Wurzel mit dem groessten Anteil, und innerhalb einer Runde reichte eine
eben vergebene Wurzel gleich weiter: an der Kirsch-Scheibe (10 mm dick, Schichten ohne wohlgestellte
Zelle) wanderte die Wurzel so bis 38 Halbweiten weit, das Wurzelpolynom wurde ueber elf Zellen
fortgesetzt, und C bekam Koeffizienten bis 3,5e9 (h 8, Versatz 0,6; 28.09.2026) - die reduzierte
Matrix hatte Diagonalwerte bis 2,5e21 gegen einen Median von 1,4e5. Die weitesten Faelle waren leere
Zellen im Loch, 19 mm vom naechsten Werkstoff: die Abstandsfunktion der Mengenoperation ist dort nur
eine untere Schranke (0,6 mm), die Klassifikation nennt sie darum geschnitten. Leere Zellen, die keine
Zelle mit Werkstoff beruehren, bekommen deshalb keine Wurzel; ihre Moden beeinflussen keinen
Werkstoffpunkt und werden null gesetzt. Leere Zellen am Werkstoff brauchen dagegen eine Wurzel: ihre
Moden sind Meister haengender Moden von Werkstoffzellen und bekaemen frei nur deren Steifigkeit
(Patch-Test duenne Waende p 3: Randspannung 2,8e-6 statt 5,8e-8).

Die Rohzwaenge (Mode -> Wurzelmoden mit Koeffizienten) verarbeitet fcm/zwaenge.py zusammen
mit den haengenden Freiheitsgraden zur Zwangsmatrix.
"""
from __future__ import annotations

import numpy as np

from .basis import basis_3d
from .gitter import CUT

_NACHBARN_TAB: dict = {}                                            # wird unten aus _NACHBARN gefuellt
_NACHBARN = sorted(((dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1) if (dx, dy, dz) != (0, 0, 0)),
                   key=lambda v: (abs(v[0]) + abs(v[1]) + abs(v[2])))     # Flaechen-, dann Kanten-, dann Eckennachbarn
_NACHBARN_TAB.update({d: i for i, d in enumerate(_NACHBARN)})


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
    def __init__(self, gitter, quadratur, schwelle: float = 0.4) -> None:
        self.gitter = gitter
        self.schwelle = float(schwelle)
        self.anteil = werkstoffanteile(gitter, quadratur)
        # Rangfolge der Wurzeln nur nach dem gerundeten Anteil: zwei volle Nachbarn unterschieden sich um 3e-15 je
        # nach Quadratur (Referenz gegen Moment Fitting, Lame h 20 p 3), der Zufallssieger aenderte C und die
        # Spannungen am Rand um 4e-3 (30.09.2026). Gleichstand entscheidet die feste Nachbarreihenfolge.
        self._rang = np.round(self.anteil, 9)
        self.wurzel = np.full(len(gitter.ijk), -1, int)             # -1: wohlgestellt oder ohne Wurzel
        self.schlecht = self.anteil < self.schwelle
        self.leer = self.schlecht & (self.anteil <= 0.0)             # geschnitten klassifiziert, aber ohne Werkstoff
        self.werkstofffern = self._werkstofffern()                    # leer und ohne Beruehrung mit Werkstoff
        self.zu_teilen: tuple = ()
        self._nachbar_tab: dict[int, np.ndarray] = {}
        self._wurzeln_zuordnen()
        self.statistik = {"schwelle": self.schwelle, "zellen_schlecht": int(self.schlecht.sum()),
                          "zellen_leer": int(self.leer.sum()), "zellen_werkstofffern": int(self.werkstofffern.sum()),
                          "zellen_ohne_wurzel": int((self.schlecht & ~self.werkstofffern & (self.wurzel < 0)).sum()),
                          "zellen_zu_teilen": len(self.zu_teilen),
                          "moden_gebunden": 0, "moden_null": 0, "wurzelabstand_max": 0.0, "anteil_min": float(self.anteil.min()),
                          "anteil_min_wohl": float(self.anteil[~self.schlecht].min()) if (~self.schlecht).any() else 0.0}

    # -- Zellen ------------------------------------------------------------------------
    def _werkstofffern(self) -> np.ndarray:
        """Leere Zellen, die keine Zelle mit Werkstoff beruehren (Flaeche, Kante oder Ecke, auch
        feinere Blaetter an ihrem Rand)."""
        g = self.gitter
        fern = np.zeros(len(g.ijk), bool)
        for c in np.flatnonzero(self.leer):
            lo, hi = g.zellbox(c)
            eps = 1e-6 * float(g.h_zelle(c))
            fern[c] = not bool(np.any(self.anteil[g.blaetter_in_box(lo - eps, hi + eps)] > 0.0))
        return fern

    def _nachbarn_vorberechnen(self, zellen: np.ndarray) -> None:
        """Blaetter hinter allen 26 Flaechen, Kanten und Ecken der Zellen in einem Aufruf von zelle_finden.
        Einzeln waren es 50 492 Aufrufe mit je einem Punkt, 6,4 s von 23 s Konstruktor bei Kirsch h 8 p 3 (Profil
        29.09.2026, A2 Plan TP 5); die Suche ist punktweise, die Nachbarn sind dieselben."""
        zellen = np.asarray(zellen, int)
        if len(zellen) == 0:
            return
        g = self.gitter
        lo, hi = g.zellbox(zellen)
        m = 0.5 * (lo + hi)
        hl = np.asarray(g.h_zelle(zellen), float).reshape(-1, 1, 1)
        D = np.asarray(_NACHBARN, float)                               # (26, 3)
        P = m[:, None, :] + (0.5 * hl + 1e-4 * hl) * D[None, :, :]
        n = g.zelle_finden(P.reshape(-1, 3)).reshape(len(zellen), len(_NACHBARN))
        for c, zeile in zip(zellen, n):
            self._nachbar_tab[int(c)] = zeile

    def _nachbar(self, c: int, d) -> int:
        """Blatt hinter der Flaeche/Kante/Ecke in Richtung d (per Punktsuche, ebenenunabhaengig)."""
        zeile = self._nachbar_tab.get(int(c))
        if zeile is not None:
            return int(zeile[_NACHBARN_TAB[tuple(d)]])
        lo, hi = self.gitter.zellbox(c)
        m = 0.5 * (lo + hi)
        hl = float(self.gitter.h_zelle(c))
        P = m + (0.5 * hl + 1e-4 * hl) * np.asarray(d, float)
        return int(self.gitter.zelle_finden(P[None])[0])

    def _wurzeln_zuordnen(self) -> None:
        """Wurzel je schlecht geschnittener Zelle: der wohlgestellte Nachbar auf gleicher oder
        groeberer Ebene mit der kleinsten Nachbarstufe und dem groessten Werkstoffanteil, sonst
        die Wurzel eines Nachbarn (ebenfalls nicht feiner). Nie eine feinere Zelle: die hinge
        mit ihren Moden an der aggregierten Zelle, und die Zwangsketten wuerden zirkulaer
        (test_zwaenge, duenne Wand: 53 Selbstbezuege mit Rest bis 2,45, 27.09.2026). Zellen, die
        nur feinere wohlgestellte Nachbarn haben, landen in ``zu_teilen``; FcmProblem teilt sie
        und baut das Gitter neu, dann liegen ihre Kinder auf der Ebene der Nachbarn."""
        g = self.gitter
        offen = list(np.flatnonzero(self.schlecht & ~self.werkstofffern))
        self._nachbarn_vorberechnen(np.asarray(offen, int))
        rest = []
        nur_feiner: set[int] = set()
        for c in offen:
            beste, best_schluessel = -1, (99, 0.0)
            feiner_gesehen = False
            for d in _NACHBARN:
                n = self._nachbar(c, d)
                if n < 0 or n == c or self.schlecht[n]:
                    continue
                if g.ebene[n] > g.ebene[c]:
                    feiner_gesehen = True
                    continue
                stufe = abs(d[0]) + abs(d[1]) + abs(d[2])
                schluessel = (stufe, -self._rang[n])
                if schluessel < best_schluessel:
                    beste, best_schluessel = n, schluessel
            if beste >= 0:
                self.wurzel[c] = beste
            else:
                rest.append(c)
                if feiner_gesehen:
                    nur_feiner.add(int(c))
        while rest:
            # schichtweise: Kandidaten nur aus den Wurzeln der Vorrunde, die naechste gewinnt (kleinste
            # Fortsetzungskoeffizienten ~ Abstand^p), bei Gleichstand der groessere Anteil
            vorher = self.wurzel.copy()
            neu = []
            vergeben = {}
            for c in rest:
                kandidaten = set()
                for d in _NACHBARN:
                    n = self._nachbar(c, d)
                    if n >= 0 and n != c and vorher[n] >= 0 and g.ebene[vorher[n]] <= g.ebene[c]:
                        kandidaten.add(int(vorher[n]))
                if kandidaten:
                    vergeben[c] = min(kandidaten, key=lambda r: (self._abstand_zu(c, r), -self._rang[r], r))
                else:
                    neu.append(c)
            for c, r in vergeben.items():
                self.wurzel[c] = r
            rest = neu
            if not vergeben:
                break                                                 # isolierte Zellen ohne Werkstoffnachbar
        # ohne Wurzel, aber mit feineren wohlgestellten Nachbarn: teilen statt aggregieren
        self.zu_teilen = tuple((int(g.ebene[c]), int(g.ijk[c, 0]), int(g.ijk[c, 1]), int(g.ijk[c, 2]))
                               for c in rest if c in nur_feiner and g.ebene[c] < 8)

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

    def _abstand_zu(self, c: int, r: int) -> float:
        """Abstand der Mitten von Zelle c und Wurzel r in Halbweiten der Wurzel (Maximumnorm): 2 fuer den
        Flaechennachbarn gleicher Groesse; bestimmt die Groesse der Fortsetzungskoeffizienten (~ Abstand^p)."""
        g = self.gitter
        lo_c, hi_c = g.zellbox(c)
        lo_r, hi_r = g.zellbox(int(r))
        return float((np.abs(0.5 * (lo_c + hi_c) - 0.5 * (lo_r + hi_r)) / (0.5 * (hi_r - lo_r))).max())

    def _abstand(self, c: int) -> float:
        return self._abstand_zu(c, int(self.wurzel[c]))

    def roh_zwaenge(self, haengend: dict[int, list[tuple[int, float]]] | None = None) -> dict[int, list[tuple[int, float]]]:
        """Mode -> [(Wurzelmode, Koeffizient)] fuer schlecht gestellte Moden, die nicht schon durch
        haengende Entitaeten gebunden sind (haengend: deren Rohzwaenge); Mode -> [] (null) fuer Moden,
        die keinen Werkstoffpunkt beeinflussen."""
        haengend = haengend or {}
        g = self.gitter
        wohl_mode = np.zeros(g.n_moden, bool)
        for c in np.flatnonzero(~self.schlecht):
            wohl_mode[g.zell_moden[c]] = True
        # relevant: von einer Zelle mit Werkstoff getragen oder (transitiv) Meister eines relevanten
        # haengenden Modes - nur solche Moden beeinflussen die Loesung an Werkstoffpunkten
        relevant = np.zeros(g.n_moden, bool)
        for c in np.flatnonzero(self.anteil > 0.0):
            relevant[g.zell_moden[c]] = True
        geaendert = True
        while geaendert:
            geaendert = False
            for mode, eintraege in haengend.items():
                if relevant[mode]:
                    for mm, _ in eintraege:
                        if not relevant[mm]:
                            relevant[mm] = True
                            geaendert = True
        eigentuemer = np.full(g.n_moden, -1, int)
        # Eigentuemer eines geteilten Modes ist die groebste schlechte Zelle: ein Eckmode, den eine
        # grobe und eine feine schlechte Zelle teilen, wuerde sonst ueber die Wurzel der feinen Zelle
        # gebunden, deren Moden (haengende Ecken) wiederum an der groben Zelle haengen - Zwangszyklus
        # (test_zwaenge, duenne Wand, 27.09.2026: Mode 582 -> 6605 -> 582). Mit dem groebsten Eigentuemer
        # laufen alle Zwangsketten monoton zu groeberen Ebenen. Auf gleicher Ebene gewinnt die naechste
        # Wurzel (kleinste Fortsetzungskoeffizienten), dann die mit dem groessten Anteil.
        #
        # Die groebste schlechte Zelle zaehlt auch ohne Wurzel (sie behaelt alpha, FcmProblem): Ihre Moden sind frei und
        # duerfen nicht ueber eine feinere Zelle an deren Wurzel haengen. Sonst band Z54 (Ebene 1) die Ecke, die sie mit der
        # unverwurzelten Z11 (Ebene 0, Anteil 0,18) teilt, an die Wurzel Z66, waehrend ein haengender Mode der Nachbarzelle
        # Z50 an Z11 haengt und die Wurzel denselben Mode enthaelt: 803 -> 192 -> 803, Zwangszyklus mit Koeffizient 1 und Rest
        # 2,45 (T-Stoss mit zwei lokalen Halbierungen an den Kehlnaehten, Plan TP 5 B4, 30.09.2026). Ohne die Sperre lief die
        # Kette nicht monoton zu groeberen Ebenen.
        ebene_frei = np.full(g.n_moden, 1 << 30, int)
        for c in np.flatnonzero(self.schlecht & (self.wurzel < 0) & ~self.werkstofffern):
            mo = g.zell_moden[c]
            ebene_frei[mo] = np.minimum(ebene_frei[mo], int(g.ebene[c]))
        mit_wurzel = np.flatnonzero(self.schlecht & (self.wurzel >= 0))
        abstand = {int(c): self._abstand(int(c)) for c in mit_wurzel}
        self.statistik["wurzelabstand_max"] = round(max(abstand.values(), default=0.0), 3)
        reihenfolge = sorted(mit_wurzel, key=lambda c: (int(g.ebene[c]), abstand[int(c)], -self._rang[self.wurzel[c]]))
        for c in reihenfolge:
            for i in g.zell_moden[c]:
                # alle Moden einer Zelle mit Wurzel werden gebunden, auch nicht relevante: eine leere Zelle
                # kann einen Werkstoffsplitter unterhalb der Quadraturaufloesung beruehren, und dort
                # ausgewertete Randspannungen verfehlten sonst das lineare Feld (Patch-Test duenne Waende
                # p 3: 2,8e-6 statt < 1e-6)
                if not wohl_mode[i] and eigentuemer[i] < 0 and int(i) not in haengend and ebene_frei[i] >= g.ebene[c]:
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
        # null: freie Moden ohne Einfluss auf Werkstoffpunkte (nur werkstoffferne Zellen tragen sie)
        n_null = 0
        for i in np.flatnonzero(~relevant & ~wohl_mode):
            if int(i) not in haengend and int(i) not in roh:
                roh[int(i)] = []
                n_null += 1
        self.statistik["moden_gebunden"] = len(roh) - n_null
        self.statistik["moden_null"] = n_null
        return roh


__all__ = ["werkstoffanteile", "Zellaggregation"]
