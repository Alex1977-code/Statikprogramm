"""Wurzelgitter wuerfelfoermiger Zellen mit Zellklassifikation und Modennummerierung
(Vorgabe Abschnitt 4, Entwurf 3.4).

Teilprojekt 1: alle Zellen liegen auf Oktree-Ebene 0. Die Entitaetsschluessel (verdoppelte
Ganzzahlkoordinaten plus Ebene) tragen die Ebene schon mit, damit die Verfeinerung mit
haengenden Freiheitsgraden in Teilprojekt 2 anschliesst, ohne die Nummerierung umzubauen.

Klassifikation: d = Abstand der Zellmitte, r = halbe Raumdiagonale. d > r: OUTSIDE (keine
Freiheitsgrade), d < -r: INSIDE (Standard-Gauss), sonst CUT (rekursive Quadratur). Weil die
CSG-Abstaende den wahren Abstand nie ueberschaetzen (geometry/csg.py), ist INSIDE/OUTSIDE
sicher; ein CUT-Urteil kann zu vorsichtig sein und kostet dann nur Quadraturpunkte.
"""
from __future__ import annotations

import numpy as np

from .basis import modenklassen

OUTSIDE, INSIDE, CUT = 0, 1, 2


class Gitter:
    def __init__(self, geometrie, h: float, polster: float = 0.1) -> None:
        """h Kantenlaenge der Zellen in mm; polster in Zellen an jeder Seite des Huellquaders,
        damit die Oberflaeche nicht genau auf Zellgrenzen faellt (0,1 = ein Zehntel h)."""
        if not h > 0:
            raise ValueError("Zellgroesse h muss positiv sein")
        self.geometrie = geometrie
        self.h = float(h)
        lo, hi = geometrie.huellquader()
        self.ursprung = lo - polster * self.h
        self.n = np.maximum(1, np.ceil((hi - lo + 2 * polster * self.h) / self.h - 1e-9)).astype(int)
        self.gesamt_zellen = int(np.prod(self.n))
        self._klassifizieren()
        self.p: int | None = None
        self.zell_moden: np.ndarray | None = None
        self.n_moden = 0

    # -- Aufbau ----------------------------------------------------------------
    def alle_mitten(self) -> tuple[np.ndarray, np.ndarray]:
        """Mitten (N,3) und Indizes (N,3) aller Wurzelzellen, Reihenfolge i, j, k (k schnell)."""
        I = np.stack(np.meshgrid(*[np.arange(k) for k in self.n], indexing="ij"), axis=-1).reshape(-1, 3)
        return self.ursprung + (I + 0.5) * self.h, I

    def _klassifizieren(self) -> None:
        M, I = self.alle_mitten()
        d = self.geometrie.abstand(M)
        r = 0.5 * np.sqrt(3.0) * self.h * (1 + 1e-9)
        kl = np.where(d > r, OUTSIDE, np.where(d < -r, INSIDE, CUT))
        self.alle_klassen = kl
        aktiv = kl != OUTSIDE
        self.ijk = I[aktiv]
        self.klasse = kl[aktiv]
        self.ebene = np.zeros(len(self.ijk), int)
        self._aktiv_index = np.full(self.gesamt_zellen, -1, int)
        self._aktiv_index[np.flatnonzero(aktiv)] = np.arange(len(self.ijk))
        if len(self.ijk) == 0:
            raise ValueError("Geometrie enthaelt keine Zelle mit Werkstoff")

    # -- Zugriff -----------------------------------------------------------------
    def flach(self, I: np.ndarray) -> np.ndarray:
        return (I[..., 0] * self.n[1] + I[..., 1]) * self.n[2] + I[..., 2]

    def zellbox(self, c) -> tuple[np.ndarray, np.ndarray]:
        lo = self.ursprung + self.ijk[c] * self.h
        return lo, lo + self.h

    def zelle_finden(self, P) -> np.ndarray:
        """Aktive Zelle je Punkt, -1 ausserhalb des Gitters oder in einer OUTSIDE-Zelle.
        Punkte auf einer Zellgrenze werden der Nachbarzelle mit Werkstoff zugeschlagen."""
        P = np.asarray(P, float).reshape(-1, 3)
        aus = np.full(len(P), -1, int)
        for eps in (0.0, 1e-9, -1e-9):
            I = np.floor((P - self.ursprung) / self.h + eps).astype(int)
            ok = np.all((I >= 0) & (I < self.n), axis=1) & (aus < 0)
            if not ok.any():
                continue
            c = np.full(len(P), -1, int)
            c[ok] = self._aktiv_index[self.flach(I[ok])]
            aus = np.where((aus < 0) & (c >= 0), c, aus)
        return aus

    def lokal(self, P, c) -> np.ndarray:
        """Referenzkoordinaten xi in [-1,1]^3 der Punkte P in den Zellen c."""
        lo, hi = self.zellbox(np.asarray(c))
        return 2.0 * (np.asarray(P, float).reshape(-1, 3) - lo) / (hi - lo) - 1.0

    # -- Freiheitsgrade ------------------------------------------------------------
    def moden_nummerieren(self, p: int) -> np.ndarray:
        """Globale Modennummern je Zelle (nz, (p+1)^3) ueber Entitaetsschluessel.

        Lokaler Mode (a,b,c) gehoert zur Entitaet mit verdoppelter Koordinate je Richtung
        0 (Index 0), 2 (Index 1) oder 1 (Index >= 2, hoeherer Mode); die Position innerhalb
        der Entitaet sind die hohen Indizes minus 2 in der Reihenfolge x, y, z. Weil alle
        Kanten und Flaechen kanonisch in +Achsrichtung parametrisiert sind, sehen Nachbarzellen
        dieselbe Funktion unter derselben Nummer - ohne Vorzeichenwechsel (Entwurf 3.3).
        """
        if not 1 <= p <= 4:
            raise ValueError("p muss zwischen 1 und 4 liegen")
        kl = modenklassen(p)
        abc, hoch = kl["abc"], kl["hoch"]
        koord = np.where(hoch, 1, np.where(abc == 0, 0, 2))
        groesse = np.maximum(1, (p - 1)) ** kl["klasse"] if p > 1 else np.ones(len(abc), int)
        pos = np.zeros(len(abc), int)
        for m in range(len(abc)):
            q = 0
            for d in range(3):
                if hoch[m, d]:
                    q = q * (p - 1) + (abc[m, d] - 2)
            pos[m] = q
        schluessel: dict[tuple[int, int, int, int], int] = {}
        zm = np.empty((len(self.ijk), len(abc)), int)
        n = 0
        for c in range(len(self.ijk)):
            b = 2 * self.ijk[c]
            eb = int(self.ebene[c])
            for m in range(len(abc)):
                k = (int(b[0] + koord[m, 0]), int(b[1] + koord[m, 1]), int(b[2] + koord[m, 2]), eb)
                start = schluessel.get(k)
                if start is None:
                    start = n
                    schluessel[k] = start
                    n += int(groesse[m])
                zm[c, m] = start + pos[m]
        self.p = p
        self.zell_moden = zm
        self.n_moden = n
        return zm

    @property
    def n_dof(self) -> int:
        return 3 * self.n_moden

    def zell_dofs(self, c: int) -> np.ndarray:
        """Globale Freiheitsgrade einer Zelle, Reihenfolge 3*mode + Komponente."""
        return (3 * self.zell_moden[c][:, None] + np.arange(3)).ravel()


__all__ = ["Gitter", "OUTSIDE", "INSIDE", "CUT"]
