"""CSG-Baum ueber Grundformen (Vorgabe Abschnitt 3, Entwurf 3.7).

Operationen auf SDF-Ebene: Vereinigung = min, Schnitt = max,
Differenz a \\ (b ∪ c ∪ ...) = max(d_a, -min(d_b, d_c, ...)).

Das Ergebnis ist kein exakter Abstand mehr, aber es **ueberschaetzt den Abstand zur
Oberflaeche der Gesamtgeometrie nie**. Skizze fuer den Schnitt A ∩ B: Sei p ausserhalb und
q der naechste Punkt auf ∂(A∩B) ⊂ closure(A) ∩ closure(B). Liegt p ausserhalb von A, kreuzt
die Strecke pq die Flaeche ∂A, also |pq| >= d_A(p); entsprechend fuer B; damit
|pq| >= max(d_A, d_B) = d(p). Innen (p in A∩B) gilt ∂(A∩B) ⊂ ∂A ∪ ∂B, also
dist >= min(|d_A|, |d_B|) = |max(d_A, d_B)|. Fuer die Vereinigung genauso mit vertauschten
Rollen, die Differenz ist ein Schnitt mit dem Komplement. Darum darf fcm/gitter.py aus
|d(Mitte)| > halbe Raumdiagonale auf "sicher ganz innen/aussen" schliessen; ein CUT-Urteil
kann zu vorsichtig sein, nie falsch.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .sdf import Grundform, Halbraum, Kugel, Quader, Zylinder

OPERATIONEN = ("vereinigung", "differenz", "schnitt")


@dataclass(frozen=True)
class Operation:
    op: str
    teile: tuple


Knoten = Grundform | Operation


def _abstand(k, P: np.ndarray) -> np.ndarray:
    if isinstance(k, Operation):
        d = np.stack([_abstand(t, P) for t in k.teile], axis=1)
        if k.op == "vereinigung":
            return d.min(axis=1)
        if k.op == "schnitt":
            return d.max(axis=1)
        return np.maximum(d[:, 0], -d[:, 1:].min(axis=1))
    return k.abstand(P)


def _gradient(k, P: np.ndarray) -> np.ndarray:
    """Gradient des aktiven Zweigs; subtrahierte Teile mit umgekehrtem Vorzeichen."""
    if not isinstance(k, Operation):
        return k.gradient(P)
    d = np.stack([_abstand(t, P) for t in k.teile], axis=1)
    if k.op == "differenz":
        d = np.concatenate([d[:, :1], -d[:, 1:]], axis=1)
        aktiv = d.argmax(axis=1)
    elif k.op == "vereinigung":
        aktiv = d.argmin(axis=1)
    else:
        aktiv = d.argmax(axis=1)
    g = np.zeros((len(P), 3))
    for i, t in enumerate(k.teile):
        m = aktiv == i
        if m.any():
            gi = _gradient(t, P[m])
            g[m] = -gi if (k.op == "differenz" and i > 0) else gi
    return g


def _huelle(k) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(k, Operation):
        return k.huellquader()
    boxen = [_huelle(t) for t in k.teile]
    if k.op == "vereinigung":
        return np.min([b[0] for b in boxen], axis=0), np.max([b[1] for b in boxen], axis=0)
    if k.op == "schnitt":
        return np.max([b[0] for b in boxen], axis=0), np.min([b[1] for b in boxen], axis=0)
    return boxen[0]


def _grundformen(k, aus: list) -> None:
    if isinstance(k, Operation):
        for t in k.teile:
            _grundformen(t, aus)
    else:
        aus.append(k)


def _mit_vorzeichen(k, vorzeichen: int, aus: list) -> None:
    """Alle Grundformen samt Vorzeichen (-1 unter einem subtrahierten Zweig, doppelt = +1)."""
    if isinstance(k, Operation):
        for i, t in enumerate(k.teile):
            s = -vorzeichen if (k.op == "differenz" and i > 0) else vorzeichen
            _mit_vorzeichen(t, s, aus)
    else:
        aus.append((k, vorzeichen))


Halbraeume = list[tuple[np.ndarray, np.ndarray]]      # (Punkt, Normale): behalte (x-p).n <= 0


def _schneiden(stuecke: list[Halbraeume], ebenen: Halbraeume) -> list[Halbraeume]:
    return [s + ebenen for s in stuecke]


def _subtrahieren(stuecke: list[Halbraeume], ebenen: Halbraeume) -> list[Halbraeume]:
    """Stuecke minus (Schnitt der Halbraeume) als disjunkte konvexe Stuecke:
    S \\ (h1 ∩ ... ∩ hm) = ∪_j  S ∩ ¬h_j ∩ h_1 ∩ ... ∩ h_{j-1}."""
    aus: list[Halbraeume] = []
    for s in stuecke:
        for j, (p, n) in enumerate(ebenen):
            aus.append(s + [(p, -n)] + ebenen[:j])
    return aus


class Csg:
    """Gesamtgeometrie: innen(P), abstand(P), gradient(P), huellquader(), dreiecke()."""

    def __init__(self, wurzel: Knoten) -> None:
        self.wurzel = wurzel
        lo, hi = _huelle(wurzel)
        if not (np.all(np.isfinite(lo)) and np.all(np.isfinite(hi)) and np.all(hi > lo)):
            raise ValueError(f"Huellquader der Geometrie ist nicht endlich oder leer: {lo} .. {hi} "
                             "(Halbraeume nur als Schnitt oder Differenz mit einer endlichen Form)")
        self._lo, self._hi = lo, hi
        self._formen: list = []
        _grundformen(wurzel, self._formen)

    def abstand(self, P) -> np.ndarray:
        return _abstand(self.wurzel, np.asarray(P, float).reshape(-1, 3))

    def gradient(self, P) -> np.ndarray:
        return _gradient(self.wurzel, np.asarray(P, float).reshape(-1, 3))

    def innen(self, P) -> np.ndarray:
        return self.abstand(P) <= 0.0

    def huellquader(self) -> tuple[np.ndarray, np.ndarray]:
        return self._lo.copy(), self._hi.copy()

    def grundformen(self) -> list:
        return list(self._formen)

    def lokale_stuecke(self, mitte, r: float, proben: np.ndarray):
        """Lokale Beschreibung des Werkstoffs in der Kugel um ``mitte`` mit Radius r als
        disjunkte konvexe Stuecke (Listen von Halbraeumen, Box implizit), oder None.

        An den Probenpunkten wird ueber **alle** Grundformen geprueft, ob sich der
        Gesamtabstand als max(positive d_i, -d_j der Loecher) ("Schnitt minus Loecher") oder
        als min(positive d_i) (Vereinigung) rekonstruieren laesst; sonst None (Rueckfall
        Punkttest). Die Stuecke bauen nur die **aktiven** Grundformen (|d(mitte)| <= r) aus
        ihren lokalen Ebenen (Tangentialebenen bei gekruemmten Formen): eine ferne Form
        schneidet die Kugel nicht, und wuerde sie die Kugel ganz ausschliessen, waere
        |d(mitte)| > r und die Teilbox schon vorher als innen/aussen erkannt.
        Rueckgabe: (stuecke, gekruemmt).
        """
        mitte = np.asarray(mitte, float).reshape(3)
        alle: list = []
        _mit_vorzeichen(self.wurzel, 1, alle)
        proben = np.asarray(proben, float).reshape(-1, 3)
        d_ist = self.abstand(proben)
        tol = 1e-9 * max(r, 1e-12)
        d_m = np.array([float(f.abstand(mitte[None])[0]) for f, _ in alle])
        aktiv = np.abs(d_m) <= r
        if not aktiv.any():
            return None
        pos = [f for f, s in alle if s > 0]
        neg = [f for f, s in alle if s < 0]
        pos_akt = [f for (f, s), a in zip(alle, aktiv) if s > 0 and a]
        neg_akt = [f for (f, s), a in zip(alle, aktiv) if s < 0 and a]
        gekruemmt = any(f.gekruemmt for f in pos_akt + neg_akt)
        dpos = np.stack([f.abstand(proben) for f in pos], axis=1) if pos else None
        dneg = np.stack([-f.abstand(proben) for f in neg], axis=1) if neg else None
        rek = np.max(np.concatenate([d for d in (dpos, dneg) if d is not None], axis=1), axis=1)
        vz = np.array([s for _, s in alle])
        if np.all(np.abs(rek - d_ist) <= tol):
            # Waechter: eine ferne Form, die die ganze Kugel ausschliesst (positive weit aussen,
            # Loch weit innen), macht die Umgebung werkstofffrei - normalerweise schon vorher
            # als OUTSIDE erkannt, hier der Vollstaendigkeit halber
            if np.any(~aktiv & (vz * d_m > r)):
                return [], gekruemmt
            stuecke: list[Halbraeume] = [[]]
            for f in pos_akt:
                stuecke = _schneiden(stuecke, f.lokale_ebenen(mitte, r))
            for f in neg_akt:
                ebenen = f.lokale_ebenen(mitte, r)
                if ebenen:
                    stuecke = _subtrahieren(stuecke, ebenen)
            return stuecke, gekruemmt
        if dpos is not None and dneg is None and len(pos_akt) >= 1 and np.all(np.abs(dpos.min(axis=1) - d_ist) <= tol):
            if np.any(~aktiv & (d_m < -r)):
                return [[]], gekruemmt                  # eine ferne Form fuellt die ganze Kugel
            stuecke = []
            bisher: list[Halbraeume] = []
            for f in pos_akt:
                ebenen = f.lokale_ebenen(mitte, r)
                teil = _schneiden([[]], ebenen)
                for g in bisher:
                    teil = _subtrahieren(teil, g)
                stuecke += teil
                bisher.append(ebenen)
            return stuecke, gekruemmt
        return None

    def dreiecke(self, facette_mm: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Dreiecke aller Grundformen innerhalb des Huellquaders; quelle = Index in grundformen()."""
        Vs, Ts, Q = [], [], []
        n = 0
        for i, f in enumerate(self._formen):
            V, T = f.dreiecke(self._lo, self._hi, facette_mm)
            if len(T):
                Vs.append(V)
                Ts.append(T + n)
                Q.append(np.full(len(T), i))
                n += len(V)
        if not Ts:
            return np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros(0, int)
        return np.concatenate(Vs), np.concatenate(Ts), np.concatenate(Q)


def _knoten(d: dict) -> Knoten:
    typ = d.get("typ")
    if typ in OPERATIONEN:
        teile = tuple(_knoten(t) for t in d.get("teile", ()))
        if len(teile) < 2:
            raise ValueError(f"{typ} braucht mindestens zwei Teile")
        return Operation(typ, teile)
    name = d.get("name")
    try:
        if typ == "quader":
            return Quader(d["min"], d["max"], name or "quader")
        if typ == "zylinder":
            return Zylinder(d["p0"], d["p1"], float(d["radius"]), name or "zylinder")
        if typ == "kugel":
            return Kugel(d["mitte"], float(d["radius"]), name or "kugel")
        if typ == "halbraum":
            return Halbraum(d["punkt"], d["normale"], name or "halbraum")
    except KeyError as ex:
        raise ValueError(f"CSG-Knoten {typ!r}: Angabe {ex} fehlt") from ex
    raise ValueError(f"unbekannter CSG-Typ {typ!r}; bekannt: quader, zylinder, kugel, halbraum, "
                     f"vereinigung, differenz, schnitt")


def aus_params(params: dict) -> Csg:
    """``GeometrySource.params`` -> Csg (Schema in docs/Volumenmodul_Entwurf.md, 3.7)."""
    if not isinstance(params, dict) or "csg" not in params:
        raise ValueError("GeometrySource.params braucht den Eintrag 'csg'")
    return Csg(_knoten(params["csg"]))


__all__ = ["Operation", "Knoten", "Csg", "aus_params", "OPERATIONEN"]
