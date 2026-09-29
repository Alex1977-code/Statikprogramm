"""Oktree-Gitter: Wurzelgitter wuerfelfoermiger Zellen, Verfeinerung zu Blaettern mit Ebene,
Zellklassifikation und Modennummerierung (Vorgabe Abschnitt 4, Entwurf 3.4 und 4b.1).

Jedes aktive Blatt traegt seine Ebene l und seinen Index ijk auf dieser Ebene; Kantenlaenge
h_l = h / 2^l. Aufbau: Wurzelzellen klassifizieren -> Verfeinerungsregeln (Schnittzellen,
Nutzerbereiche, duenne Waende) bis zum Fixpunkt -> 2:1-Balancierung ueber alle 26 Nachbarn
(damit jede haengende Entitaet genau eine Ebene groeber ist) -> OUTSIDE-Blaetter verwerfen.

Klassifikation: d = Abstand der Zellmitte, r = halbe Raumdiagonale. d > r: OUTSIDE, d < -r:
INSIDE, sonst CUT. Weil die CSG-Abstaende den wahren Abstand nie ueberschaetzen
(geometry/csg.py), ist INSIDE/OUTSIDE sicher; ein CUT-Urteil kann zu vorsichtig sein.

Entitaetsschluessel: Ecken ebenenfrei ueber ihre Lage im feinsten verdoppelten Gitter (eine
feine Ecke auf einer groben Ecke ist dieselbe Ecke), Kanten/Flaechen/Zellinneres mit Ebene.
Gleiche Ebene -> geteilte Nummern ohne Vorzeichenwechsel (kanonische +Achsrichtung); die
Stetigkeit ueber haengende Entitaeten stellt fcm/zwaenge.py her.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .basis import modenklassen

OUTSIDE, INSIDE, CUT = 0, 1, 2

_NACHBARN26 = np.array([(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                        if (dx, dy, dz) != (0, 0, 0)], int)


@dataclass(frozen=True)
class Verfeinerung:
    """Regeln fuer den Oktree.

    schnitt_ebenen: CUT-Zellen bis zu dieser Ebene teilen (Vorgabe 4, geometrisches Kriterium).
    bereiche: Folge von (mitte (3,), radius_mm, zielgroesse_mm) - Zellen, deren Box die Kugel
        beruehrt, werden geteilt, bis h_l <= zielgroesse (RefinementRegion des Vertrags).
    duenne_waende: CUT-Zellen teilen, wenn die Werkstoffstrecke durch die Zellmitte laengs einer
        Achse kuerzer als zwei Zellkanten ist (bis max_ebene).
    max_ebene: Obergrenze der Ebenen; Standard ist die groesste aus den Regeln folgende Ebene,
        mindestens schnitt_ebenen, bei duenne_waende mindestens 2; nie ueber 8.
    zellen: erzwungene Teilungen einzelner Blaetter als (ebene, i, j, k) - die Zellaggregation
        fordert sie fuer schlecht geschnittene Zellen, deren wohlgestellte Nachbarn alle feiner
        sind (eine feinere Wurzel hinge an der Zelle selbst: Zwangszyklus, Entwurf 4b.2).
    """
    schnitt_ebenen: int = 0
    bereiche: tuple = ()
    duenne_waende: bool = False
    max_ebene: int | None = None
    zellen: tuple = ()

    def ebenen_grenze(self, h: float) -> int:
        l = int(self.schnitt_ebenen)
        for mitte, radius, ziel in self.bereiche:
            l = max(l, int(np.ceil(np.log2(max(h / float(ziel), 1.0)) - 1e-9)))
        if self.duenne_waende:
            l = max(l, 2)
        if self.max_ebene is not None:
            l = max(int(self.max_ebene), 0)
        for z in self.zellen:
            l = max(l, int(z[0]) + 1)
        return min(l, 8)


class Gitter:
    def __init__(self, geometrie, h: float, polster: float = 0.1, verfeinerung: Verfeinerung | None = None) -> None:
        """h Kantenlaenge der Wurzelzellen in mm; polster in Zellen an jeder Seite des Huellquaders,
        damit die Oberflaeche nicht genau auf Zellgrenzen faellt (0,1 = ein Zehntel h)."""
        if not h > 0:
            raise ValueError("Zellgroesse h muss positiv sein")
        self.geometrie = geometrie
        self.h = float(h)
        self.verfeinerung = verfeinerung or Verfeinerung()
        lo, hi = geometrie.huellquader()
        self.ursprung = lo - polster * self.h
        self.n = np.maximum(1, np.ceil((hi - lo + 2 * polster * self.h) / self.h - 1e-9)).astype(int)
        self.gesamt_zellen = int(np.prod(self.n))
        self.max_ebene = self.verfeinerung.ebenen_grenze(self.h)
        self._aufbauen()
        self.p: int | None = None
        self.zell_moden: np.ndarray | None = None
        self.n_moden = 0

    # -- Aufbau ----------------------------------------------------------------
    def alle_mitten(self) -> tuple[np.ndarray, np.ndarray]:
        """Mitten (N,3) und Indizes (N,3) aller Wurzelzellen, Reihenfolge i, j, k (k schnell)."""
        I = np.stack(np.meshgrid(*[np.arange(k) for k in self.n], indexing="ij"), axis=-1).reshape(-1, 3)
        return self.ursprung + (I + 0.5) * self.h, I

    def _klassen(self, ebene: np.ndarray, I: np.ndarray) -> np.ndarray:
        hl = self.h / 2.0 ** ebene
        M = self.ursprung + (I + 0.5) * hl[:, None]
        d = self.geometrie.abstand(M)
        r = 0.5 * np.sqrt(3.0) * hl * (1 + 1e-9)
        return np.where(d > r, OUTSIDE, np.where(d < -r, INSIDE, CUT))

    def _aufbauen(self) -> None:
        M, I = self.alle_mitten()
        kl0 = self._klassen(np.zeros(len(I), int), I)
        self.alle_klassen = kl0
        aktiv = kl0 != OUTSIDE
        ebene = np.zeros(int(aktiv.sum()), int)
        ijk = I[aktiv].copy()
        klasse = kl0[aktiv].copy()
        if len(ijk) == 0:
            raise ValueError("Geometrie enthaelt keine Zelle mit Werkstoff")
        # Regeln bis zum Fixpunkt
        while True:
            teilen = self._regel_teilen(ebene, ijk, klasse)
            if not teilen.any():
                break
            ebene, ijk, klasse = self._teilen(ebene, ijk, klasse, teilen)
        # 2:1-Balancierung ueber 26 Nachbarn
        while True:
            self._indizieren(ebene, ijk, klasse)
            teilen = self._unbalanciert()
            if not teilen.any():
                break
            ebene, ijk, klasse = self._teilen(ebene, ijk, klasse, teilen)
        self._indizieren(ebene, ijk, klasse)

    def _regel_teilen(self, ebene, ijk, klasse) -> np.ndarray:
        v = self.verfeinerung
        hl = self.h / 2.0 ** ebene
        teilen = np.zeros(len(ijk), bool)
        if v.schnitt_ebenen > 0:
            teilen |= (klasse == CUT) & (ebene < v.schnitt_ebenen)
        lo = self.ursprung + ijk * hl[:, None]
        hi = lo + hl[:, None]
        for mitte, radius, ziel in v.bereiche:
            ziel_ebene = int(np.ceil(np.log2(max(self.h / float(ziel), 1.0)) - 1e-9))
            m = np.asarray(mitte, float).reshape(3)
            naechster = np.clip(m, lo, hi)
            abstand = np.linalg.norm(naechster - m, axis=1)
            teilen |= (abstand <= float(radius)) & (ebene < ziel_ebene)
        if v.duenne_waende:
            kandidaten = np.flatnonzero((klasse == CUT) & (ebene < self.max_ebene) & ~teilen)
            for c in kandidaten:
                if self._duenn(lo[c], hl[c]):
                    teilen[c] = True
        if v.zellen:
            # erzwungene Teilungen: genau die genannten Blaetter (Kinder haben eine andere Ebene)
            schluessel = {(int(z[0]), int(z[1]), int(z[2]), int(z[3])) for z in v.zellen}
            for c in np.flatnonzero(~teilen):
                if (int(ebene[c]), int(ijk[c, 0]), int(ijk[c, 1]), int(ijk[c, 2])) in schluessel:
                    teilen[c] = True
        teilen &= ebene < self.max_ebene
        return teilen

    def _duenn(self, lo, hl) -> bool:
        """Werkstoffstrecke durch die Zellmitte laengs einer Achse kuerzer als zwei Zellkanten?"""
        m = lo + 0.5 * hl
        s = np.linspace(-2.0 * hl, 2.0 * hl, 17)
        for d in range(3):
            P = np.repeat(m[None], len(s), axis=0)
            P[:, d] += s
            innen = self.geometrie.innen(P)
            if not innen[8]:                       # Mitte ausserhalb: laengsten ganz sichtbaren Werkstofflauf nehmen
                wechsel = np.flatnonzero(np.diff(np.concatenate([[0], innen.astype(int), [0]])))
                anfang, ende = wechsel[::2], wechsel[1::2]          # Lauf = innen[anfang:ende]
                # Laeufe, die den Fensterrand beruehren, sind abgeschnitten: ihre Laenge sagt nichts
                # (Gutachten 27.09.2026: sonst galt jede Wand mit aussenliegender Zellmitte als duenn)
                ganz = (anfang > 0) & (ende < len(innen))
                if ganz.any() and (ende - anfang)[ganz].max() * (s[1] - s[0]) < 2.0 * hl:
                    return True
                continue
            a = 8
            while a > 0 and innen[a - 1]:
                a -= 1
            b = 8
            while b < 16 and innen[b + 1]:
                b += 1
            if (b - a) * (s[1] - s[0]) < 2.0 * hl and (a > 0 or b < 16):
                return True
        return False

    def _teilen(self, ebene, ijk, klasse, teilen):
        bleiben = ~teilen
        kinder_ebene = np.repeat(ebene[teilen] + 1, 8)
        basis = np.repeat(2 * ijk[teilen], 8, axis=0)
        versatz = np.array([(a, b, c) for a in (0, 1) for b in (0, 1) for c in (0, 1)], int)
        kinder_ijk = basis + np.tile(versatz, (int(teilen.sum()), 1))
        kinder_klasse = self._klassen(kinder_ebene, kinder_ijk)
        ok = kinder_klasse != OUTSIDE
        return (np.concatenate([ebene[bleiben], kinder_ebene[ok]]),
                np.concatenate([ijk[bleiben], kinder_ijk[ok]]),
                np.concatenate([klasse[bleiben], kinder_klasse[ok]]))

    def _indizieren(self, ebene, ijk, klasse) -> None:
        """Felder sortiert nach (Ebene, flacher Index); je Ebene ein sortiertes Suchfeld."""
        reihenfolge = np.lexsort((ijk[:, 2], ijk[:, 1], ijk[:, 0], ebene))
        self.ebene = ebene[reihenfolge]
        self.ijk = ijk[reihenfolge]
        self.klasse = klasse[reihenfolge]
        self._suche: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for l in range(self.max_ebene + 1):
            idx = np.flatnonzero(self.ebene == l)
            fl = self.flach(self.ijk[idx], l)
            self._suche[l] = (fl, idx)
        # Blattlisten je Wurzelzelle fuer Boxabfragen
        wurzel = self.ijk >> self.ebene[:, None]
        self._wurzel_flach = self.flach(wurzel, 0)
        self._wurzel_reihenfolge = np.argsort(self._wurzel_flach, kind="stable")
        self._wurzel_sortiert = self._wurzel_flach[self._wurzel_reihenfolge]
        # Rueckabbildung Wurzelindex -> aktives Blatt, wenn die Wurzelzelle selbst Blatt ist
        self._aktiv_index = np.full(self.gesamt_zellen, -1, int)
        w0 = self.ebene == 0
        self._aktiv_index[self.flach(self.ijk[w0], 0)] = np.flatnonzero(w0)

    def _unbalanciert(self) -> np.ndarray:
        """Blaetter, die geteilt werden muessen: sie sind um mehr als eine Ebene groeber als ein
        Nachbar (26 Richtungen), gemessen vom feineren Blatt aus."""
        teilen = np.zeros(len(self.ijk), bool)
        for l in range(2, self.max_ebene + 1):
            idx = np.flatnonzero(self.ebene == l)
            if len(idx) == 0:
                continue
            lo, hi = self.zellbox(idx)
            m = 0.5 * (lo + hi)
            hl = self.h / 2.0 ** l
            for d in _NACHBARN26:
                P = m + (0.5 * hl + 1e-6 * hl) * d
                n = self.zelle_finden(P)
                schlecht = (n >= 0) & (self.ebene[np.maximum(n, 0)] < l - 1)
                teilen[n[schlecht]] = True
        return teilen

    # -- Zugriff -----------------------------------------------------------------
    def n_ebene(self, l: int) -> np.ndarray:
        return self.n * (2 ** int(l))

    def flach(self, I: np.ndarray, l) -> np.ndarray:
        n = self.n_ebene(int(np.max(l)) if np.ndim(l) else int(l))
        if np.ndim(l):
            n = self.n[None, :] * (2 ** np.asarray(l))[:, None]
            return (I[..., 0] * n[:, 1] + I[..., 1]) * n[:, 2] + I[..., 2]
        return (I[..., 0] * n[1] + I[..., 1]) * n[2] + I[..., 2]

    def h_zelle(self, c) -> np.ndarray:
        return self.h / 2.0 ** self.ebene[c]

    def zellbox(self, c) -> tuple[np.ndarray, np.ndarray]:
        hl = np.asarray(self.h_zelle(c), float)
        lo = self.ursprung + self.ijk[c] * (hl[..., None] if np.ndim(hl) else hl)
        return lo, lo + (hl[..., None] if np.ndim(hl) else hl)

    def zelle_finden(self, P) -> np.ndarray:
        """Aktives Blatt je Punkt, -1 ausserhalb des Gitters oder in OUTSIDE-Gebiet.
        Punkte auf einer Zellgrenze werden dem Nachbarn mit Werkstoff zugeschlagen."""
        P = np.asarray(P, float).reshape(-1, 3)
        aus = np.full(len(P), -1, int)
        for eps in (0.0, 1e-9, -1e-9):
            offen = aus < 0
            if not offen.any():
                break
            for l in range(self.max_ebene + 1):
                fl_sort, idx = self._suche[l]
                if len(idx) == 0:
                    continue
                hl = self.h / 2.0 ** l
                I = np.floor((P[offen] - self.ursprung) / hl + eps).astype(int)
                ok = np.all((I >= 0) & (I < self.n_ebene(l)), axis=1)
                if not ok.any():
                    continue
                fl = self.flach(I[ok], l)
                pos = np.searchsorted(fl_sort, fl)
                pos = np.minimum(pos, len(fl_sort) - 1)
                treffer = fl_sort[pos] == fl
                ziel = np.flatnonzero(offen)[np.flatnonzero(ok)[treffer]]
                aus[ziel] = idx[pos[treffer]]
                offen = aus < 0
                if not offen.any():
                    break
        return aus

    def blaetter_in_box(self, lo, hi) -> np.ndarray:
        """Indizes aller Blaetter, deren Box die Box [lo, hi] schneidet (Rand eingeschlossen)."""
        lo = np.asarray(lo, float)
        hi = np.asarray(hi, float)
        i0 = np.maximum(np.floor((lo - self.ursprung) / self.h - 1e-9).astype(int), 0)
        i1 = np.minimum(np.floor((hi - self.ursprung) / self.h + 1e-9).astype(int), self.n - 1)
        if np.any(i1 < i0):
            return np.zeros(0, int)
        I = np.stack(np.meshgrid(*[np.arange(a, b + 1) for a, b in zip(i0, i1)], indexing="ij"), axis=-1).reshape(-1, 3)
        fl = np.sort(self.flach(I, 0))
        a = np.searchsorted(self._wurzel_sortiert, fl, side="left")
        b = np.searchsorted(self._wurzel_sortiert, fl, side="right")
        kandidaten = np.concatenate([self._wurzel_reihenfolge[x:y] for x, y in zip(a, b)]) if len(fl) else np.zeros(0, int)
        if len(kandidaten) == 0:
            return kandidaten
        blo, bhi = self.zellbox(kandidaten)
        ok = np.all((blo <= hi + 1e-12 * self.h) & (bhi >= lo - 1e-12 * self.h), axis=1)
        return kandidaten[ok]

    def lokal(self, P, c) -> np.ndarray:
        """Referenzkoordinaten xi in [-1,1]^3 der Punkte P in den Zellen c."""
        lo, hi = self.zellbox(np.asarray(c))
        return 2.0 * (np.asarray(P, float).reshape(-1, 3) - lo) / (hi - lo) - 1.0

    # -- Freiheitsgrade ------------------------------------------------------------
    def entitaets_schluessel(self, c: int, koord: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Schluessel der 27 Entitaeten einer Zelle fuer die Modenkoordinaten koord (m,3) in {0,1,2}:
        Ecken ebenenfrei im feinsten verdoppelten Gitter, Kanten/Flaechen/Inneres mit Ebene."""
        l = int(self.ebene[c])
        skal = 2 ** (self.max_ebene - l)
        basis = 2 * self.ijk[c]
        aus = []
        for k in koord:
            X = (int(basis[0] + k[0]) * skal, int(basis[1] + k[1]) * skal, int(basis[2] + k[2]) * skal)
            ecke = k[0] != 1 and k[1] != 1 and k[2] != 1
            aus.append((X[0], X[1], X[2], -1 if ecke else l))
        return aus

    def moden_nummerieren(self, p: int) -> np.ndarray:
        """Globale Modennummern je Zelle (nz, (p+1)^3) ueber Entitaetsschluessel.

        Lokaler Mode (a,b,c) gehoert zur Entitaet mit verdoppelter Koordinate je Richtung
        0 (Index 0), 2 (Index 1) oder 1 (Index >= 2, hoeherer Mode); die Position innerhalb
        der Entitaet sind die hohen Indizes minus 2 in der Reihenfolge x, y, z.
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
            for m, k in enumerate(self.entitaets_schluessel(c, koord)):
                start = schluessel.get(k)
                if start is None:
                    start = n
                    schluessel[k] = start
                    n += int(groesse[m])
                zm[c, m] = start + pos[m]
        self.p = p
        self.zell_moden = zm
        self.n_moden = n
        self._koord = koord
        return zm

    @property
    def n_dof(self) -> int:
        return 3 * self.n_moden

    def zell_dofs(self, c: int) -> np.ndarray:
        """Globale Freiheitsgrade einer Zelle, Reihenfolge 3*mode + Komponente."""
        return (3 * self.zell_moden[c][:, None] + np.arange(3)).ravel()

    def ebenen_verteilung(self) -> dict[int, int]:
        return {int(l): int((self.ebene == l).sum()) for l in range(self.max_ebene + 1) if (self.ebene == l).any()}


__all__ = ["Gitter", "Verfeinerung", "OUTSIDE", "INSIDE", "CUT"]
