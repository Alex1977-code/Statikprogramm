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


def _abstand(k, P: np.ndarray, vorab: dict | None = None) -> np.ndarray:
    """Gesamtabstand des Teilbaums k; ``vorab`` liefert schon berechnete Abstaende je Grundform
    (Schluessel id(form)), damit lokale_stuecke jede Form nur einmal auswertet."""
    if isinstance(k, Operation):
        d = np.stack([_abstand(t, P, vorab) for t in k.teile], axis=1)
        if k.op == "vereinigung":
            return d.min(axis=1)
        if k.op == "schnitt":
            return d.max(axis=1)
        return np.maximum(d[:, 0], -d[:, 1:].min(axis=1))
    if vorab is not None:
        return vorab[id(k)]
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


class BaumStuecke(list):
    """Stueckliste aus dem Baumweg (Csg._baum_stuecke). Die Stuecke einer Vereinigung sind disjunkt, aber ein
    Flaechenpolygon auf einer Form wird von den Stuecken der anderen Formen nicht geteilt - die Flaechenquadratur
    zerlegt es darum an allen beteiligten Ebenen (geometry/oberflaeche.py)."""
    baum = True


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


def _pruefe_teile(teile: list[Halbraeume], proben: np.ndarray, d_probe: np.ndarray, r: float) -> bool:
    """Stimmen die Teile an den Proben mit dem Vorzeichen des Formabstands ueberein? Proben auf
    der Flaeche (|d| <= tol) entscheiden nicht."""
    tol = 1e-9 * max(r, 1e-12)
    drin = np.zeros(len(proben), bool)
    for t in teile:
        ok = np.ones(len(proben), bool)
        for p, n in t:
            ok &= (proben - p) @ n <= tol
        drin |= ok
    return bool(np.all((drin == (d_probe < 0)) | (np.abs(d_probe) <= tol)))


def _form_teile(f, mitte, r: float, proben: np.ndarray | None = None, d_probe: np.ndarray | None = None) -> list[Halbraeume] | None:
    """Der Werkstoff der Grundform f in der Kugel (mitte, r) als disjunkte konvexe Teile.
    Grundformen sind lokal konvex (ein Teil: Schnitt ihrer lokalen Ebenen). Ein STL meldet seine
    Lage: konvex ebenso; konkav (Bohrungswand, einspringende Kante) ist der Werkstoff die
    Vereinigung der Halbraeume = Kugel minus Schnitt der gespiegelten Ebenen; gemischt
    (Deckel trifft Bohrungswand) Schnitt der Schnitt-Typ-Ebenen ∩ Vereinigung der uebrigen.
    Gemischte Teile werden an den Proben gegen das Vorzeichen des Formabstands geprueft;
    scheitert das, zerlegt die binaere Raumteilung (wenige Ebenen), sonst None."""
    if not hasattr(f, "lokale_lage"):
        return [f.lokale_ebenen(mitte, r)]
    ebenen, lage, schnitt = f.lokale_lage(mitte, r)
    if lage == "konvex":
        return [ebenen]
    if lage == "konkav":
        return _subtrahieren([[]], [(p, -n) for p, n in ebenen])
    I = [e for e, s in zip(ebenen, schnitt) if s]
    U = [(p, -n) for (p, n), s in zip(ebenen, schnitt) if not s]
    teile = _schneiden(_subtrahieren([[]], U), I)
    if proben is None or d_probe is None or _pruefe_teile(teile, proben, d_probe, r):
        return teile
    teile2 = _bsp_teile(f, mitte, r, ebenen, max_ebenen=6)
    if teile2 is not None and (proben is None or _pruefe_teile(teile2, proben, d_probe, r)):
        return teile2
    return None


def _schwerpunkt(flaechen: list[np.ndarray]) -> np.ndarray:
    from .polyeder import tetraeder
    T = tetraeder(flaechen)
    v = np.abs(np.linalg.det(T[:, 1:] - T[:, :1])) / 6.0
    return (T.mean(axis=1) * v[:, None]).sum(axis=0) / v.sum()


def _bsp_teile(f, mitte, r: float, ebenen: Halbraeume, max_ebenen: int = 8, max_zellen: int = 64) -> list[Halbraeume] | None:
    """Gemischte STL-Lage (Deckel trifft Bohrungswand, Sattel): binaere Raumteilung des Wuerfels
    [mitte - r, mitte + r] an allen lokalen Ebenen. Innerhalb der Kugel liegt die Oberflaeche ganz
    auf diesen Ebenen, also ist jede Zelle dort ganz Werkstoff oder ganz leer; Zeuge ist der
    Schwerpunkt der Zelle im einbeschriebenen Wuerfel (sicher in der Kugel), sonst der
    Zellschwerpunkt - liegt auch der ausserhalb der Kugel, None (Rueckfall: teilen, zuletzt
    Punkttest). Viele Ebenen (grobe Blaetter an einer Bohrungskante) ebenfalls None: eine Stufe
    tiefer beruehren weniger Facetten."""
    from .polyeder import box_flaechen, clippen, volumen
    if len(ebenen) > max_ebenen:
        return None
    mitte = np.asarray(mitte, float)
    eps_v = 1e-12 * r ** 3
    zellen: list[tuple[list[np.ndarray], Halbraeume]] = [(box_flaechen(mitte - r, mitte + r), [])]
    for p, n in ebenen:
        neu = []
        for poly, hs in zellen:
            vorn = clippen(poly, p, n)
            hinten = clippen(poly, p, -n)
            if volumen(vorn) > eps_v and volumen(hinten) > eps_v:
                neu.append((vorn, hs + [(p, n)]))
                neu.append((hinten, hs + [(p, -n)]))
            else:
                neu.append((poly, hs))
        zellen = neu
        if len(zellen) > max_zellen:
            return None
    a = r / np.sqrt(3.0)
    klein = [(mitte - a, -np.eye(3)[d]) for d in range(3)] + [(mitte + a, np.eye(3)[d]) for d in range(3)]
    teile: list[Halbraeume] = []
    for poly, hs in zellen:
        innen_poly = poly
        for p, n in klein:
            innen_poly = clippen(innen_poly, p, n)
            if not innen_poly:
                break
        w = _schwerpunkt(innen_poly) if innen_poly and volumen(innen_poly) > eps_v else _schwerpunkt(poly)
        if float(np.linalg.norm(w - mitte)) > r:
            return None
        if bool(f.innen(w[None])[0]):
            teile.append(hs)
    return teile


def _mit_teilen_schneiden(stuecke: list[Halbraeume], teile: list[Halbraeume]) -> list[Halbraeume]:
    """stuecke ∩ (∪ teile) fuer disjunkte Teile."""
    aus: list[Halbraeume] = []
    for t in teile:
        aus += _schneiden(stuecke, t)
    return aus


def _teile_subtrahieren(stuecke: list[Halbraeume], teile: list[Halbraeume]) -> list[Halbraeume]:
    """stuecke minus (∪ teile), nacheinander je Teil; ein leeres Teil ist die ganze Kugel (ein Loch,
    das sie ausfuellt) und loescht alles."""
    for t in teile:
        if not t:
            return []
        stuecke = _subtrahieren(stuecke, t)
    return stuecke


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
        # Angaben zur Herkunft der Huelle fuers Protokoll (STEP: Tessellierung, siehe geometry/step.py), sonst None
        self.tessellierung: dict | None = None

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

    def lokale_stuecke(self, mitte, r: float, proben: np.ndarray, ohne=None):
        """Lokale Beschreibung des Werkstoffs in der Kugel um ``mitte`` mit Radius r als
        disjunkte konvexe Stuecke (Listen von Halbraeumen, Box implizit), oder None.

        An den Probenpunkten wird ueber **alle** Grundformen geprueft, ob sich der
        Gesamtabstand als max(positive d_i, -d_j der Loecher) ("Schnitt minus Loecher") oder
        als min(positive d_i) (Vereinigung) rekonstruieren laesst; sonst None (Rueckfall
        Punkttest - oder, wenn keins der beiden Muster passt, ueber den Baum selbst, siehe
        _baum_stuecke). Die Stuecke bauen nur die **aktiven** Grundformen (|d(mitte)| <= r) aus
        ihren lokalen Ebenen (Tangentialebenen bei gekruemmten Formen): eine ferne Form
        schneidet die Kugel nicht, und wuerde sie die Kugel ganz ausschliessen, waere
        |d(mitte)| > r und die Teilbox schon vorher als innen/aussen erkannt.
        Rueckgabe: (stuecke, gekruemmt, aktive Grundformen).
        """
        mitte = np.asarray(mitte, float).reshape(3)
        alle: list = []
        _mit_vorzeichen(self.wurzel, 1, alle)
        if ohne is not None and hasattr(ohne, "dreiecke_ecken"):
            # Flaechenpolygon auf einer Facette dieser Huelle: die Huelle selbst clippt es nicht (es liegt auf ihr), nur die
            # anderen Formen - ihre eigenen lokalen Ebenen (bei gemischter Lage unloesbar: Theorie 11.15) entfallen (Plan TP 5 B6)
            return self._stuecke_ohne(ohne, mitte, r, proben, alle)
        proben = np.asarray(proben, float).reshape(-1, 3)
        tol = 1e-9 * max(r, 1e-12)
        # ein Aufruf je Grundform fuer Mitte und Proben zusammen; der Gesamtabstand an den Proben
        # folgt aus denselben Werten ueber den Baum (Profil Lame CSG 27.09.: 320 000 kleine
        # abstand-Aufrufe, 15 s von 50 s Aufbau)
        punkte = np.concatenate([mitte[None], proben])
        d_formen = [f.abstand(punkte) for f, _ in alle]
        d_m = np.array([float(d[0]) for d in d_formen])
        d_alle = [d[1:] for d in d_formen]                   # einmal je Form, auch fuer die Teilpruefung
        d_ist = _abstand(self.wurzel, proben, {id(f): d for (f, _), d in zip(alle, d_alle)})
        aktiv = np.abs(d_m) <= r
        if not aktiv.any():
            return None
        pos = [(f, d) for (f, s), d in zip(alle, d_alle) if s > 0]
        neg = [(f, d) for (f, s), d in zip(alle, d_alle) if s < 0]
        pos_akt = [(f, d) for (f, s), a, d in zip(alle, aktiv, d_alle) if s > 0 and a]
        neg_akt = [(f, d) for (f, s), a, d in zip(alle, aktiv, d_alle) if s < 0 and a]
        gekruemmt = any(f.gekruemmt for f, _ in pos_akt + neg_akt)
        dpos = np.stack([d for _, d in pos], axis=1) if pos else None
        dneg = np.stack([-d for _, d in neg], axis=1) if neg else None
        rek = np.max(np.concatenate([d for d in (dpos, dneg) if d is not None], axis=1), axis=1)
        vz = np.array([s for _, s in alle])
        if np.all(np.abs(rek - d_ist) <= tol):
            # Waechter: eine ferne Form, die die ganze Kugel ausschliesst (positive weit aussen,
            # Loch weit innen), macht die Umgebung werkstofffrei - normalerweise schon vorher
            # als OUTSIDE erkannt, hier der Vollstaendigkeit halber
            aktive = [f for f, _ in pos_akt + neg_akt]
            if np.any(~aktiv & (vz * d_m > r)):
                return [], gekruemmt, aktive
            stuecke: list[Halbraeume] = [[]]
            for f, d in pos_akt:
                teile = _form_teile(f, mitte, r, proben, d)
                if teile is None:
                    return None                   # STL-Lage nicht darstellbar: Rueckfall (teilen, zuletzt Punkttest)
                stuecke = _mit_teilen_schneiden(stuecke, teile)
            for f, d in neg_akt:
                teile = _form_teile(f, mitte, r, proben, d)
                if teile is None:
                    return None
                stuecke = _teile_subtrahieren(stuecke, teile)
            return stuecke, gekruemmt, aktive
        if dpos is not None and dneg is None and len(pos_akt) >= 1 and np.all(np.abs(dpos.min(axis=1) - d_ist) <= tol):
            aktive = [f for f, _ in pos_akt]
            if np.any(~aktiv & (d_m < -r)):
                return [[]], gekruemmt, aktive          # eine ferne Form fuellt die ganze Kugel
            stuecke = []
            bisher: list[list[Halbraeume]] = []
            for f, d in pos_akt:
                teile = _form_teile(f, mitte, r, proben, d)
                if teile is None:
                    return None
                teil = list(teile)
                for g in bisher:
                    teil = _teile_subtrahieren(teil, g)
                stuecke += teil
                bisher.append(teile)
            return stuecke, gekruemmt, aktive
        return self._baum_stuecke(mitte, r, proben, alle, d_m, d_alle, aktiv, d_ist, tol)

    def _stuecke_ohne(self, huelle, mitte, r, proben, alle):
        """Stuecke fuer ein Polygon auf einer Facette der Huelle: die Huelle selbst gilt als voll (das Polygon liegt auf ihr),
        die anderen Formen entscheiden ueber den Baum, welcher Teil des Polygons wirklich Rand des Werkstoffs ist - im Schnitt
        bleibt, was in den anderen Formen liegt; in einer Vereinigung faellt weg, was andere Glieder ueberdecken; als Loch
        (subtrahiert) bleibt, wo der erste Operand Werkstoff hat und der Teilbaum des Lochs Rand liefert. Inaktive Formen zaehlen
        als voll oder leer nach dem Vorzeichen ihres Abstands; ohne andere Form ist das Stueck die ganze Kugel."""
        proben = np.asarray(proben, float).reshape(-1, 3)
        andere = [(f, s) for f, s in alle if f is not huelle]
        if not andere:
            return [[]], False, []
        punkte = np.concatenate([mitte[None], proben])
        d_formen = {id(f): f.abstand(punkte) for f, _ in andere}
        d_m = np.array([float(d_formen[id(f)][0]) for f, _ in andere])
        aktiv = np.abs(d_m) <= r
        # auch ohne aktive andere Form entscheidet der Baum: eine Schnittebene, die das Polygon ganz ueberholt hat (Abstand der Mitte > r
        # auf der Aussenseite), nimmt es weg (Befund aus B7, 01.10.2026; ein frueher Rueckgabewert "alles" liess Facetten hinter der Ebene stehen)
        info = {id(f): (float(dm), d_formen[id(f)][1:], bool(a)) for (f, _), dm, a in zip(andere, d_m, aktiv)}
        aktive: list = []

        def teile(k):
            """(Stuecke, enthaelt die Huelle); None, wenn eine Form nicht darstellbar ist."""
            if isinstance(k, Operation):
                kinder = [teile(t) for t in k.teile]
                if any(c is None for c in kinder):
                    return None
                mit = [i for i, (_, h) in enumerate(kinder) if h]
                if k.op == "schnitt":
                    acc: list[Halbraeume] = [[]]
                    for c, _ in kinder:
                        acc = _mit_teilen_schneiden(acc, c)
                    return acc, bool(mit)
                if k.op == "vereinigung":
                    if mit:
                        acc = list(kinder[mit[0]][0])
                        for i, (c, _) in enumerate(kinder):
                            if i != mit[0]:
                                acc = _teile_subtrahieren(acc, c)
                        return acc, True
                    acc, bisher = [], []
                    for c, _ in kinder:
                        t = list(c)
                        for g in bisher:
                            t = _teile_subtrahieren(t, g)
                        acc += t
                        bisher.append(c)
                    return acc, False
                acc = list(kinder[0][0])                        # differenz: erster Operand minus die Loecher
                for i, (c, h) in enumerate(kinder[1:], start=1):
                    if h:
                        # das Loch, auf dessen Wand das Polygon liegt: Rand ist nur, was im ersten Operanden UND auf dem Rand des Lochs
                        # liegt - fuer ein Loch, das selbst eine Operation ist, also nur der Teil, den dessen Teilbaum als Rand liefert.
                        # Vorher wurde es uebersprungen, und Facetten der Huelle ausserhalb des Lochrands blieben als Flaeche im Werkstoff
                        # stehen (A − (H ∩ {x <= 20}): 11 634 statt 11 200 mm2, Gutachten C2, G1-4)
                        acc = _mit_teilen_schneiden(acc, c)
                        continue
                    acc = _teile_subtrahieren(acc, c)
                return acc, bool(mit)
            if k is huelle:
                return [[]], True
            dm, d, a = info[id(k)]
            if not a:
                return ([[]] if dm < 0 else []), False
            if not any(k is f for f in aktive):
                aktive.append(k)
            t = _form_teile(k, mitte, r, proben, d)
            return (None if t is None else (t, False))
        erg = teile(self.wurzel)
        if erg is None:
            return None
        return BaumStuecke(erg[0]), any(f.gekruemmt for f in aktive), aktive

    def _baum_stuecke(self, mitte, r, proben, alle, d_m, d_alle, aktiv, d_ist, tol):
        """Stuecke ueber den CSG-Baum selbst, fuer verschachtelte Baeume, die keins der beiden flachen Muster
        erfuellen - etwa eine Vereinigung, deren Teile Schnitte sind (Kehlnaht = Quader ∩ Halbraum am T-Stoss;
        vorher fiel dort jedes Blatt auf den Punkttest erster Ordnung: 18 401 Blaetter, Volumen +0,13 %, Plan
        TP 5 B3, 30.09.2026). Je Knoten: Schnitt schneidet die Stuecke der Kinder, Vereinigung haengt jedes Kind
        ohne die vorigen an (disjunkt), Differenz zieht ab; eine inaktive Form (|d(mitte)| > r) ist die ganze
        Kugel oder leer. Ohne gekruemmte aktive Form sind die Stuecke exakt und werden an den Proben gegen das
        Vorzeichen des Gesamtabstands geprueft (Punkte naeher als tol an der Flaeche ausgenommen); scheitert
        das, None (Rueckfall wie bisher)."""
        info = {id(f): (float(dm), d, bool(a)) for (f, _), dm, d, a in zip(alle, d_m, d_alle, aktiv)}
        aktive: list = []

        def teile(k):
            if isinstance(k, Operation):
                kinder = [teile(t) for t in k.teile]
                if any(c is None for c in kinder):
                    return None
                if k.op == "schnitt":
                    acc: list[Halbraeume] = [[]]
                    for c in kinder:
                        acc = _mit_teilen_schneiden(acc, c)
                    return acc
                if k.op == "vereinigung":
                    acc, bisher = [], []
                    for c in kinder:
                        t = list(c)
                        for g in bisher:
                            t = _teile_subtrahieren(t, g)
                        acc += t
                        bisher.append(c)
                    return acc
                acc = list(kinder[0])                       # differenz
                for c in kinder[1:]:
                    acc = _teile_subtrahieren(acc, c)
                return acc
            dm, d, a = info[id(k)]
            if not a:
                return [[]] if dm < 0 else []
            if not any(k is f for f in aktive):             # Identitaet: Grundformen tragen Arrays, == waere elementweise
                aktive.append(k)
            return _form_teile(k, mitte, r, proben, d)

        stuecke = teile(self.wurzel)
        if stuecke is None:
            return None
        gekruemmt = any(f.gekruemmt for f in aktive)
        if not gekruemmt and len(proben):
            # Abdeckung mit abgeschlossenen Stuecken (eine Probe auf der Trennflaeche zweier Stuecke liegt in beiden), Disjunktheit
            # nur mit offenen: vorher zaehlte "drin == 1" eine Probe auf einer inneren Trennflaeche doppelt und verwarf die richtige
            # Zerlegung (Knotenblech im Nahtstumpf, Plan TP 5 C1: 1 534 Flaechenstuecke im Rueckfall, Oberflaeche +481 mm2)
            drin = np.zeros(len(proben), int)
            offen = np.zeros(len(proben), int)
            for st in stuecke:
                m = np.ones(len(proben), bool)
                mo = np.ones(len(proben), bool)
                for p0, n0 in st:
                    s_ = (proben - p0) @ n0
                    m &= s_ <= tol
                    mo &= s_ < -tol
                drin += m
                offen += mo
            klar = np.abs(d_ist) > tol
            if np.any((drin[klar] > 0) != (d_ist[klar] < 0)) or np.any(offen > 1):
                return None
        return BaumStuecke(stuecke), gekruemmt, aktive

    def huellenzelle(self, mitte, r: float):
        """Ist der Werkstoff in der Kugel (mitte, r) genau eine tessellierte Huelle (oder ihr Komplement)?

        Liefert (huelle, vorzeichen) mit +1 (Werkstoff = Huelle ∩ Kugel) oder -1 (Werkstoff = Kugel minus Huelle), sonst None.
        Alle anderen Grundformen muessen die Kugel ganz enthalten oder ganz ausschliessen (|d(mitte)| > r); der Baum wird dann
        ueber den vier Werten leer, voll, Huelle, Komplement ausgewertet (Schnitt = und, Vereinigung = oder, Differenz = und nicht).
        Grundlage der exakten Integration tessellierter Huellen (geometry/huelle.py, Plan TP 5 B6)."""
        mitte = np.asarray(mitte, float).reshape(3)
        huellen = [f for f in self._formen if hasattr(f, "dreiecke_ecken")]
        if not huellen:
            return None
        d = {id(f): float(f.abstand(mitte[None])[0]) for f in self._formen}
        aktiv = [f for f in self._formen if abs(d[id(f)]) <= r]
        if len(aktiv) != 1 or not hasattr(aktiv[0], "dreiecke_ecken"):
            return None
        h = aktiv[0]
        if getattr(h, "offene_kanten", 0) > 0:
            # Divergenzsatz nur fuer geschlossene Huellen: eine Luecke verfaelscht die ganze x-Saeule hinter ihr (Wuerfel ohne eine
            # Facette auf einer x-Seite 13 859 statt 27 000 mm3, Gutachten C2, G1-2); offene Huellen gehen den alten Weg
            return None
        # Werte: 0 leer, 1 voll, 2 Huelle, 3 Komplement der Huelle
        NICHT = {0: 1, 1: 0, 2: 3, 3: 2}

        def und(a, b):
            if a == 0 or b == 0:
                return 0
            if a == 1:
                return b
            if b == 1:
                return a
            return a if a == b else 0                           # Huelle ∩ Komplement = leer

        def oder(a, b):
            if a == 1 or b == 1:
                return 1
            if a == 0:
                return b
            if b == 0:
                return a
            return a if a == b else 1                           # Huelle ∪ Komplement = voll

        def wert(k):
            if isinstance(k, Operation):
                w = [wert(t) for t in k.teile]
                if k.op == "schnitt":
                    acc = 1
                    for x in w:
                        acc = und(acc, x)
                    return acc
                if k.op == "vereinigung":
                    acc = 0
                    for x in w:
                        acc = oder(acc, x)
                    return acc
                acc = w[0]
                for x in w[1:]:
                    acc = und(acc, NICHT[x])
                return acc
            if k is h:
                return 2
            return 1 if d[id(k)] < 0.0 else 0
        v = wert(self.wurzel)
        if v == 2:
            return h, 1
        if v == 3:
            return h, -1
        return None

    def dreiecke(self, facette_mm: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Dreiecke aller Grundformen innerhalb des Huellquaders; quelle = Index in grundformen()."""
        Vs, Ts, Q = [], [], []
        n = 0
        # Box fuer die Halbraum-Polygone minimal groesser als der Huellquader: liegt eine
        # achsparallele Ebene genau auf der Huellquaderseite, faende der Kantenschnitt sonst nichts
        rand = 1e-6 * float(np.max(self._hi - self._lo))
        for i, f in enumerate(self._formen):
            V, T = f.dreiecke(self._lo - rand, self._hi + rand, facette_mm)
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
        if typ == "stl":
            from .stl import Stl
            if "dreiecke" in d:
                return Stl.aus_dreiecken(np.asarray(d["dreiecke"], float), name or "stl")
            return Stl.aus_datei(d["pfad"], name)
    except KeyError as ex:
        raise ValueError(f"CSG-Knoten {typ!r}: Angabe {ex} fehlt") from ex
    raise ValueError(f"unbekannter CSG-Typ {typ!r}; bekannt: quader, zylinder, kugel, halbraum, stl, "
                     f"vereinigung, differenz, schnitt")


def aus_params(params: dict) -> Csg:
    """``GeometrySource.params`` -> Csg (Schema in docs/Volumenmodul_Entwurf.md, 3.7)."""
    if not isinstance(params, dict) or "csg" not in params:
        raise ValueError("GeometrySource.params braucht den Eintrag 'csg'")
    return Csg(_knoten(params["csg"]))


__all__ = ["Operation", "Knoten", "Csg", "aus_params", "OPERATIONEN"]
