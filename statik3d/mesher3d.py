"""
Freier 3D-Vernetzer: aus der Randdarstellung eines Koerpers werden Tetraeder
===========================================================================

Ein Volumenkoerper aus RFEM ist eine **Randdarstellung**: eine Huelle aus
Flaechen, die ihrerseits von Linien berandet sind. Abgebildet (*mapped*)
vernetzen liessen sich davon bisher nur der Sechsflaechner (6 Vierecke,
8 Knoten) und der Tetraeder (4 Dreiecke, 4 Knoten). Alles andere - jeder
Lagerbock, jedes Augenblech mit Bohrung, jede Buchse - blieb ohne Netz und
damit ohne Nachweis.

Dieses Modul vernetzt frei. Der Weg ist in vier Schritten angeschrieben,
damit er nachrechenbar bleibt:

1. **Randnetz.** Jede Randflaeche wird in Dreiecke geteilt. Ebene Flaechen -
   auch solche mit Bohrungen - werden in ihrer Ebene frei vernetzt, krumme
   Vierseitflaechen (Zylinder, Kegelstumpf) ueber die **Coons-Abbildung**
   zwischen ihren vier Randkurven. Jede *Linie* wird dabei genau **einmal**
   abgetastet; nur so passen die Netze benachbarter Flaechen aufeinander.

2. **Dichtheit.** Die Dreiecke werden vernaeht und geprueft: jede Kante muss
   in genau zwei Dreiecken liegen. Das Volumen folgt aus dem Gaussschen Satz,

       V = 1/6 * Summe ueber alle Dreiecke von (a x b) . c

   und muss positiv sein - dann zeigt die Huelle nach aussen. Ist die Huelle
   nicht dicht, wird **nicht** vernetzt: ein Netz aus einer undichten Huelle
   ist stillschweigend falsch, und das ist schlimmer als kein Netz.

3. **Punkte.** Auf dem Rand liegen die Punkte des Randnetzes, im Inneren ein
   raumzentriertes kubisches Gitter (BCC) mit der Zielkantenlaenge. Das
   BCC-Gitter ist das Punktmuster, dessen Delaunay-Zerlegung von sich aus
   gute Tetraeder liefert (Labelle/Shewchuk). Ein Gitterpunkt wird nur
   genommen, wenn er im Koerper liegt und weit genug vom Rand entfernt ist -
   sonst entstehen dort flache Elemente.

4. **Tetraeder.** Delaunay-Zerlegung aller Punkte (Qhull ueber scipy), dann
   bleiben die Tetraeder, deren Schwerpunkt im Koerper liegt. Zum Schluss
   wird gerechnet, nicht gehofft: die Summe der Tetraedervolumen gegen das
   Volumen aus Schritt 2, das kleinste Kantenverhaeltnis, und wieviel der
   Randflaeche das Netz wiedergibt. Alles davon steht im Protokoll.

Die Punkt-im-Koerper-Frage wird auf zwei voellig verschiedenen Wegen
beantwortet: als **Strahlenzaehlung** (schnell, mit Gitterindex) und als
**verallgemeinerte Windungszahl** (langsam, aber ohne Sonderfaelle). Die
Pruefungen vergleichen beide gegeneinander.
"""
from __future__ import annotations

import numpy as np

from .model import Model, _randstuecke

#: Kantenlaenge, wenn weder Koerper noch Netzeinstellungen etwas sagen [m]
STANDARDLAENGE = 0.5

#: So nah darf ein Punkt des ebenen Netzes an seinen Rand (Vielfaches von h)
RANDABSTAND = 0.65

#: Ein Tetraeder unter diesem Anteil von h^3 gilt als flach und faellt weg
FLACH = 1e-6

#: Groesste Abweichung von der Ausgleichsebene, bis zu der eine Flaeche als
#: eben gilt - bezogen auf ihre eigene Ausdehnung
EBENHEIT = 1e-6

#: Groesster Richtungswechsel je Abschnitt einer krummen Linie [Grad].
#: Er begrenzt die Sehnenabweichung unabhaengig von der Groesse: ein Kreis
#: bekommt so immer mindestens 360/BOGENWINKEL Abschnitte, ob er nun 10 mm
#: oder 10 m Durchmesser hat. Ohne diese Schranke wuerde eine Bohrung von
#: 20 mm bei 50 mm Zielkantenlaenge zu einer Strecke zusammenfallen.
BOGENWINKEL = 30.0

#: Wenigstens so viele Elemente ueber die groesste Ausdehnung eines Koerpers.
#: Ist die Zielkantenlaenge groeber, wird sie fuer diesen Koerper verkleinert.
MINDESTTEILUNG = 4


# --------------------------------------------------------------------------
# Hilfen: Ebene, Flaecheninhalt, Volumen
# --------------------------------------------------------------------------
def ausgleichsebene(P: np.ndarray) -> tuple:
    """(Mittelpunkt, e1, e2, Normale, groesste Abweichung) einer Punktwolke.

    Die Ebene folgt aus der Singulaerwertzerlegung: die kleinste
    Singulaerrichtung ist die Normale, die beiden anderen spannen die Ebene.
    """
    P = np.asarray(P, float)
    c = P.mean(axis=0)
    U, S, Vt = np.linalg.svd(P - c, full_matrices=True)
    e1, e2, n = Vt[0], Vt[1], Vt[2]
    abw = float(np.abs((P - c) @ n).max()) if len(P) else 0.0
    return c, e1, e2, n, abw


def ist_eben(P: np.ndarray, toleranz: float = EBENHEIT) -> bool:
    """Liegt die Punktfolge in einer Ebene?"""
    P = np.asarray(P, float)
    if len(P) < 4:
        return True
    c, _, _, _, abw = ausgleichsebene(P)
    gr = float(np.linalg.norm(P - c, axis=1).max())
    return gr <= 0 or abw <= toleranz * gr


def huellvolumen(P: np.ndarray, T: np.ndarray) -> float:
    """Volumen einer geschlossenen Dreieckshuelle (Gaussscher Satz).

        V = 1/6 * Summe (a x b) . c

    Positiv, wenn die Dreiecke nach aussen zeigen. Der Wert ist **exakt**
    (bis auf Rundung) und dient als Sollwert fuer das Tetraedernetz.
    """
    if len(T) == 0:
        return 0.0
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    return float(np.einsum("ij,ij->i", np.cross(a, b), c).sum()) / 6.0


def huellflaeche(P: np.ndarray, T: np.ndarray) -> float:
    """Gesamte Flaeche einer Dreiecksmenge [m^2]."""
    if len(T) == 0:
        return 0.0
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    return float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum()) / 2.0


def tetraedervolumen(P: np.ndarray, TET: np.ndarray) -> np.ndarray:
    """Vorzeichenbehaftetes Volumen je Tetraeder."""
    if len(TET) == 0:
        return np.zeros(0)
    a, b, c, d = P[TET[:, 0]], P[TET[:, 1]], P[TET[:, 2]], P[TET[:, 3]]
    return np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) / 6.0


# --------------------------------------------------------------------------
# Punkt im Koerper: Strahlenzaehlung und Windungszahl
# --------------------------------------------------------------------------
def windungszahl(q: np.ndarray, P: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Verallgemeinerte Windungszahl der Huelle um jeden Punkt in ``q``.

    Fuer jedes Dreieck (a, b, c) ist der Raumwinkel nach van Oosterom und
    Strackee

        tan(Omega/2) = det[A B C] / (|A||B||C| + (A.B)|C| + (B.C)|A| + (C.A)|B|)

    mit A = a - q usw. Die Summe aller Raumwinkel ist 4*pi im Inneren einer
    geschlossenen, nach aussen gerichteten Huelle und 0 ausserhalb. Der Weg
    kennt keine Sonderfaelle (keine Strahlen, die eine Kante treffen) und ist
    darum der Pruefstein fuer die schnelle Strahlenzaehlung.
    """
    q = np.atleast_2d(np.asarray(q, float))
    if len(T) == 0 or len(q) == 0:
        return np.zeros(len(q))
    out = np.zeros(len(q))
    a0, b0, c0 = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    # In Bloecken rechnen: n_q * n_T Doubles passen sonst nicht in den Speicher
    block = max(1, int(2e6 // max(len(T), 1)))
    for i in range(0, len(q), block):
        Q = q[i:i + block][:, None, :]
        A, B, C = a0[None] - Q, b0[None] - Q, c0[None] - Q
        la = np.linalg.norm(A, axis=2)
        lb = np.linalg.norm(B, axis=2)
        lc = np.linalg.norm(C, axis=2)
        num = np.einsum("ijk,ijk->ij", np.cross(A, B), C)
        den = (la * lb * lc
               + np.einsum("ijk,ijk->ij", A, B) * lc
               + np.einsum("ijk,ijk->ij", B, C) * la
               + np.einsum("ijk,ijk->ij", C, A) * lb)
        out[i:i + block] = 2.0 * np.arctan2(num, den).sum(axis=1)
    return out / (4.0 * np.pi)


class Gitterindex:
    """Dreiecke nach ihrem Schatten in der xy-Ebene einsortiert.

    Fuer die Strahlenzaehlung nach +z braucht ein Punkt nur die Dreiecke, die
    ueber ihm liegen koennen. Ohne diesen Index waere jeder Punkt gegen jedes
    Dreieck zu pruefen - bei 100 000 Punkten und 50 000 Dreiecken sind das
    5 Milliarden Paare.
    """

    def __init__(self, P: np.ndarray, T: np.ndarray, zelle: float = 0.0):
        self.P, self.T = P, T
        a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
        self.lo = np.minimum(np.minimum(a[:, :2], b[:, :2]), c[:, :2])
        self.hi = np.maximum(np.maximum(a[:, :2], b[:, :2]), c[:, :2])
        gr = float(np.max(self.hi - self.lo)) if len(T) else 1.0
        self.zelle = float(zelle) if zelle > 0 else max(gr, 1e-12)
        self.p0 = P[:, :2].min(axis=0) if len(P) else np.zeros(2)
        self.faecher: dict = {}
        i0 = np.floor((self.lo - self.p0) / self.zelle).astype(np.int64)
        i1 = np.floor((self.hi - self.p0) / self.zelle).astype(np.int64)
        for k in range(len(T)):
            for ix in range(i0[k, 0], i1[k, 0] + 1):
                for iy in range(i0[k, 1], i1[k, 1] + 1):
                    self.faecher.setdefault((ix, iy), []).append(k)

    def kandidaten(self, punkt) -> np.ndarray:
        ix, iy = np.floor((np.asarray(punkt, float)[:2] - self.p0) / self.zelle).astype(np.int64)
        return np.asarray(self.faecher.get((int(ix), int(iy)), ()), dtype=np.int64)


def innen(q: np.ndarray, P: np.ndarray, T: np.ndarray,
          index: "Gitterindex" = None) -> np.ndarray:
    """Liegt jeder Punkt in ``q`` im Koerper? (Strahlenzaehlung nach +z)

    Ein Strahl von jedem Punkt senkrecht nach oben schneidet eine
    geschlossene Huelle **ungerade** oft, wenn der Punkt innen liegt. Der
    Schnitt wird in der xy-Projektion ueber baryzentrische Koordinaten
    gesucht; senkrechte Dreiecke haben dort keine Flaeche und koennen den
    Strahl nicht schneiden.

    Gerechnet wird zellenweise und im Ganzen: alle Punkte einer Gitterzelle
    gegen alle Dreiecke dieser Zelle in einem Zug. Punkt fuer Punkt in Python
    zu schleifen waere bei hunderttausend Punkten und dreissig
    Verfeinerungsdurchgaengen der langsamste Teil des ganzen Vernetzers.
    """
    q = np.atleast_2d(np.asarray(q, float))
    if len(T) == 0 or len(q) == 0:
        return np.zeros(len(q), bool)
    if index is None:
        index = Gitterindex(P, T)
    A, B, C = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    flaeche2 = ((B[:, 0] - A[:, 0]) * (C[:, 1] - A[:, 1])
                - (C[:, 0] - A[:, 0]) * (B[:, 1] - A[:, 1]))
    with np.errstate(invalid="ignore", over="ignore"):
        roh = (q[:, :2] - index.p0) / index.zelle
    # Ein entarteter Tetraeder liefert einen Umkugelmittelpunkt im Unendlichen.
    # Solche Punkte liegen sicher nicht im Koerper und werden gleich verworfen.
    brauchbar = (np.all(np.isfinite(roh), axis=1) & np.isfinite(q[:, 2])
                 & (np.abs(roh) < 1e15).all(axis=1))
    if not brauchbar.all():
        out = np.zeros(len(q), bool)
        if brauchbar.any():
            out[brauchbar] = innen(q[brauchbar], P, T, index)
        return out
    zellen = np.floor(roh).astype(np.int64)
    schluessel = zellen[:, 0] * np.int64(1000003) + zellen[:, 1]
    ordnung = np.argsort(schluessel, kind="stable")
    sortiert = schluessel[ordnung]
    anfang = np.flatnonzero(np.concatenate(([True], sortiert[1:] != sortiert[:-1])))
    grenzen = np.concatenate([anfang, [len(sortiert)]])
    zaehler = np.zeros(len(q), np.int64)
    for g in range(len(anfang)):
        idx = ordnung[grenzen[g]:grenzen[g + 1]]
        zelle = (int(zellen[idx[0], 0]), int(zellen[idx[0], 1]))
        kand = index.faecher.get(zelle)
        if not kand:
            continue
        kand = np.asarray(kand, dtype=np.int64)
        kand = kand[np.abs(flaeche2[kand]) > 1e-30]
        if not len(kand):
            continue
        # In Bloecken, damit n_punkte * n_dreiecke nie den Speicher sprengt
        block = max(1, int(2e6 // len(kand)))
        for i0 in range(0, len(idx), block):
            teil = idx[i0:i0 + block]
            pi = np.repeat(teil, len(kand))
            ti = np.tile(kand, len(teil))
            px, py, pz = q[pi, 0], q[pi, 1], q[pi, 2]
            a, b, c = A[ti], B[ti], C[ti]
            d = flaeche2[ti]
            l1 = ((b[:, 0] - px) * (c[:, 1] - py) - (c[:, 0] - px) * (b[:, 1] - py)) / d
            l2 = ((c[:, 0] - px) * (a[:, 1] - py) - (a[:, 0] - px) * (c[:, 1] - py)) / d
            l3 = 1.0 - l1 - l2
            z = l1 * a[:, 2] + l2 * b[:, 2] + l3 * c[:, 2]
            treffer = (l1 >= 0) & (l2 >= 0) & (l3 >= 0) & (z > pz)
            if treffer.any():
                np.add.at(zaehler, pi[treffer], 1)
    return (zaehler % 2).astype(bool)


# --------------------------------------------------------------------------
# Schritt 1: Randnetz
# --------------------------------------------------------------------------
def _linienlaenge(model: Model, name: str) -> float:
    ln = model.lines.get(name)
    if ln is None:
        return 0.0
    try:
        return float(ln.laenge(model))
    except Exception:                       # noqa: BLE001
        idx = [int(n) for n in ln.nodes if 0 <= int(n) < model.nn]
        if len(idx) < 2:
            return 0.0
        return float(np.linalg.norm(np.diff(model.nodes[idx], axis=0), axis=1).sum())


def _linienpunkte(model: Model, name: str, n: int) -> np.ndarray:
    """n+1 Punkte auf der wahren Kurve einer Linie, gleiche Bogenlaengen.

    Beim Bogen und beim Kreis laeuft der innere Kurvenparameter schon mit
    gleicher Bogenlaenge; dann werden die Punkte **unmittelbar** von der Kurve
    genommen und liegen genau auf ihr. Nur wenn das nicht so ist (Spline,
    Ellipse), wird ueber eine feine Naeherung umparametrisiert - und dann fein
    genug, dass der Sehnenfehler unter einem Millionstel bleibt.
    """
    ln = model.lines.get(name)
    if ln is None:
        return np.zeros((0, 3))
    idx = [int(x) for x in ln.nodes if 0 <= int(x) < model.nn]
    roh = None
    if (ln.typ or "polyline") != "polyline":
        try:
            kurve = ln.kurve(model)
            genau = np.asarray(kurve.punkte(max(int(n), 1)), float)
            L = np.linalg.norm(np.diff(genau, axis=0), axis=1)
            if len(L) and L.max() > 0 and (L.max() - L.min()) <= 1e-12 * L.max():
                return _enden_setzen(model, idx, genau)
            roh = np.asarray(kurve.punkte(max(16 * n, 512)), float)
        except Exception:                   # noqa: BLE001
            roh = None
    if roh is None:
        if len(idx) < 2:
            return np.zeros((0, 3))
        roh = model.nodes[idx]
    lang = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(roh, axis=0), axis=1))])
    if lang[-1] <= 0:
        return roh[:1]
    ziel = np.linspace(0.0, lang[-1], n + 1)
    k = np.clip(np.searchsorted(lang, ziel, side="right") - 1, 0, len(roh) - 2)
    t = ((ziel - lang[k]) / (lang[k + 1] - lang[k]))[:, None]
    return _enden_setzen(model, idx, roh[k] + t * (roh[k + 1] - roh[k]))


def _enden_setzen(model: Model, idx: list, P: np.ndarray) -> np.ndarray:
    """Anfang und Ende genau auf die Stuetzknoten legen."""
    P = np.array(P, dtype=float, copy=True)
    if len(idx) >= 2 and len(P) >= 2:
        a, b = model.nodes[idx[0]], model.nodes[idx[-1]]
        if np.linalg.norm(P[0] - a) <= np.linalg.norm(P[0] - b):
            P[0], P[-1] = a, b
        else:
            P[0], P[-1] = b, a
    return P


def _bogenabschnitte(model: Model, name: str) -> int:
    """Mindestzahl der Abschnitte einer krummen Linie aus ihrer Kruemmung.

    Der gesamte Richtungswechsel entlang der Kurve wird durch den groessten
    zugelassenen Wechsel je Abschnitt geteilt. Fuer den Halbkreis sind das
    180/30 = 6 Abschnitte, fuer den Vollkreis 12 - unabhaengig davon, wie
    gross er ist.
    """
    ln = model.lines.get(name)
    if ln is None or (ln.typ or "polyline") == "polyline":
        return 1
    try:
        P = np.asarray(ln.kurve(model).punkte(64), float)
    except Exception:                       # noqa: BLE001
        return 2
    d = np.diff(P, axis=0)
    lang = np.linalg.norm(d, axis=1)
    gut = lang > 1e-15
    d = d[gut] / lang[gut][:, None]
    if len(d) < 2:
        return 2
    cos = np.clip(np.einsum("ij,ij->i", d[:-1], d[1:]), -1.0, 1.0)
    winkel = float(np.degrees(np.arccos(cos)).sum())
    return max(2, int(np.ceil(winkel / BOGENWINKEL)))


class Linienteilung:
    """Wieviele Abschnitte bekommt jede Linie - fuer alle Flaechen dieselbe.

    Zwei benachbarte Flaechen teilen ihre gemeinsame Randlinie. Taeten sie das
    mit verschiedener Teilung, klaffte die Huelle dort auf und waere nicht
    dicht. Darum wird die Teilung **je Linie** festgelegt, nicht je Flaeche.

    Krumme Vierseitflaechen werden abgebildet vernetzt; dort muessen die
    gegenueberliegenden Seiten gleich viele Abschnitte haben. Diese Bindung
    wird ueber eine Vereinigungssuche (union-find) durch das ganze Modell
    weitergereicht, und die Klasse bekommt die groesste geforderte Teilung.
    """

    def __init__(self, model: Model, flaechen: list, h: float):
        self.model, self.h = model, max(float(h), 1e-9)
        self.vater: dict = {}
        namen = set()
        for f in flaechen:
            namen.update(f.linien or [])
            for loch in (f.oeffnungen or []):
                namen.update(loch)
        for f in flaechen:
            seiten = seiten_im_umlauf(model, f.linien or [])
            if seiten is None or len(seiten) != 4:
                continue
            P = f.randpunkte(model, 12)
            if len(P) >= 4 and ist_eben(P):
                continue                     # eben: frei vernetzt, keine Bindung
            self._verbinden(seiten[0][0], seiten[2][0])
            self._verbinden(seiten[1][0], seiten[3][0])
        self.n: dict = {}
        self.gruppe: dict = {}
        for name in namen:
            self.gruppe.setdefault(self._wurzel(name), []).append(name)
        for wurzel, mitglieder in self.gruppe.items():
            k = 1
            for x in mitglieder:
                k = max(k, int(round(_linienlaenge(model, x) / self.h)),
                        _bogenabschnitte(model, x))
            for x in mitglieder:
                self.n[x] = k

    def verfeinern(self, namen) -> int:
        """Die genannten Linien feiner teilen - **mitsamt ihrer Klasse**.

        Gegenueberliegende Seiten einer abgebildet vernetzten Flaeche muessen
        gleich viele Abschnitte behalten. Wird nur eine von beiden feiner,
        zerfaellt die Abbildung und die Huelle reisst erst recht auf.
        """
        wurzeln = {self._wurzel(x) for x in namen if x in self.n}
        geaendert = 0
        for wurzel in wurzeln:
            mitglieder = self.gruppe.get(wurzel, [])
            if not mitglieder:
                continue
            k = self.n.get(mitglieder[0], 1)
            neu = k + max(1, k // 2)
            for x in mitglieder:
                self.n[x] = neu
            geaendert += len(mitglieder)
        return geaendert

    def _wurzel(self, x):
        while self.vater.get(x, x) != x:
            self.vater[x] = self.vater.get(self.vater[x], self.vater[x])
            x = self.vater[x]
        return x

    def _verbinden(self, a, b):
        ra, rb = self._wurzel(a), self._wurzel(b)
        if ra != rb:
            self.vater[ra] = rb

    def punkte(self, name: str) -> np.ndarray:
        return _linienpunkte(self.model, name, self.n.get(name, 1))


def seiten_im_umlauf(model: Model, linien: list) -> list | None:
    """[(Linienname, Knoten im Umlauf)] - oder None, wenn der Rand nicht schliesst."""
    st = _randstuecke(model, list(linien or []))
    return st or None


def _linienzug(teilung: "Linienteilung", model: Model, linien: list):
    """Ein geschlossener Rand als Punktfolge - jede Linie mit ihrer Teilung.

    Rueckgabe (Punkte, Herkunft): ``Herkunft[i]`` nennt die Linie, zu der die
    Strecke vom Punkt i zum Punkt i+1 gehoert. Die Herkunft wird gebraucht,
    wenn eine Randstrecke im Netz fehlt: dann muss **diese Linie** feiner
    geteilt werden, und zwar fuer alle Flaechen, die sie berandet.
    """
    stuecke = seiten_im_umlauf(model, linien)
    if not stuecke:
        return None
    punkte, herkunft = [], []
    for name, knoten in stuecke:
        teil = teilung.punkte(name)
        if len(teil) < 2:
            return None
        if knoten:
            p0 = model.nodes[int(knoten[0])]
            if np.linalg.norm(teil[0] - p0) > np.linalg.norm(teil[-1] - p0):
                teil = teil[::-1]
        punkte.extend(teil[:-1])
        herkunft.extend([name] * (len(teil) - 1))
    if len(punkte) < 3:
        return None
    return np.asarray(punkte, float), herkunft


def _in_polygon_2d(q: np.ndarray, ringe: list) -> np.ndarray:
    """Punkt-im-Vieleck mit Loechern (gerade-ungerade), vektorisiert."""
    q = np.atleast_2d(np.asarray(q, float))
    drin = np.zeros(len(q), bool)
    for R in ringe:
        R = np.asarray(R, float)
        a, b = R, np.roll(R, -1, axis=0)
        for i in range(len(R)):
            x1, y1 = a[i]
            x2, y2 = b[i]
            trifft = ((y1 > q[:, 1]) != (y2 > q[:, 1]))
            if not trifft.any():
                continue
            xs = x1 + (q[:, 1] - y1) * (x2 - x1) / (y2 - y1)
            drin ^= trifft & (q[:, 0] < xs)
    return drin


def _dreiecke_2d(ringe: list, h: float) -> tuple:
    """Ebenes Vieleck mit Loechern in Dreiecke teilen.

    Randpunkte sind vorgegeben (sie sind mit den Nachbarflaechen gemeinsam).
    Im Inneren wird ein Dreiecksgitter mit der Kantenlaenge h ausgelegt; alles
    zusammen wird Delaunay-zerlegt, und es bleiben die Dreiecke, deren
    Schwerpunkt im Gebiet liegt. Das ist die ebene Fassung genau des Weges,
    der spaeter im Raum gegangen wird.
    """
    from scipy.spatial import Delaunay
    rand = np.vstack([np.asarray(R, float) for R in ringe])
    lo, hi = rand.min(axis=0), rand.max(axis=0)
    innenpunkte = []
    if h > 0:
        # Dreiecksgitter (versetzte Reihen) - gleichseitig, also beste Form
        dy = h * np.sqrt(3.0) / 2.0
        ny = max(int(np.ceil((hi[1] - lo[1]) / dy)), 1)
        kandidaten = []
        for j in range(ny + 1):
            y = lo[1] + j * dy
            versatz = 0.5 * h if j % 2 else 0.0
            nx = max(int(np.ceil((hi[0] - lo[0]) / h)), 1)
            for i in range(nx + 1):
                kandidaten.append((lo[0] + versatz + i * h, y))
        if kandidaten:
            K = np.asarray(kandidaten, float)
            K = K[_in_polygon_2d(K, ringe)]
            if len(K):
                # Nicht zu nah an den Rand: sonst entstehen dort Splitter
                d = np.linalg.norm(K[:, None, :] - rand[None, :, :], axis=2).min(axis=1)
                innenpunkte = K[d > RANDABSTAND * h]
    P2 = np.vstack([rand] + ([innenpunkte] if len(innenpunkte) else []))
    if len(P2) < 3:
        return P2, np.zeros((0, 3), int), _randstrecken(ringe)
    try:
        tri = Delaunay(P2, qhull_options="Qbb Qc Qz Q12")
    except Exception:                       # noqa: BLE001 - entartete Punktwolke
        return P2, np.zeros((0, 3), int), _randstrecken(ringe)
    T = np.asarray(tri.simplices, int)
    if not len(T):
        return P2, T, _randstrecken(ringe)
    schwer = P2[T].mean(axis=1)
    T = T[_in_polygon_2d(schwer, ringe)]
    # Flache Dreiecke fallen weg
    if len(T):
        a, b, c = P2[T[:, 0]], P2[T[:, 1]], P2[T[:, 2]]
        A = 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
                         - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))
        T = T[A > FLACH * h * h]
    return P2, T, _fehlende_randstrecken(ringe, T)


def _randstrecken(ringe: list) -> list:
    """Alle Randstrecken als Indexpaare in die aneinandergehaengten Ringe."""
    out, basis = [], 0
    for R in ringe:
        n = len(R)
        out.extend((basis + i, basis + (i + 1) % n) for i in range(n))
        basis += n
    return out


def _fehlende_randstrecken(ringe: list, T: np.ndarray) -> list:
    """Randstrecken, die im Dreiecksnetz **nicht** als Kante vorkommen.

    Die freie Delaunay-Zerlegung kennt keine Randbedingung: an einer stark
    gekruemmten oder engen Stelle kann sie eine Randstrecke ueberspringen.
    Bliebe das unbemerkt, klaffte die Randhuelle dort auf.
    """
    if not len(T):
        return _randstrecken(ringe)
    kanten = set()
    for i, j in ((0, 1), (1, 2), (2, 0)):
        for a, b in zip(T[:, i], T[:, j]):
            kanten.add((int(min(a, b)), int(max(a, b))))
    return [(a, b) for a, b in _randstrecken(ringe)
            if (min(a, b), max(a, b)) not in kanten]


def flaechennetz(model: Model, flaeche, teilung: "Linienteilung") -> tuple:
    """Dreiecksnetz einer Randflaeche.

    Rueckgabe (Punkte, Dreiecke, Meldung, Linien-die-feiner-muessen).
    """
    zug = _linienzug(teilung, model, flaeche.linien or [])
    if zug is None:
        return np.zeros((0, 3)), np.zeros((0, 3), int), "Rand schliesst nicht", []
    aussen, herkunft = zug
    ringe3, quellen = [aussen], [herkunft]
    for loch in (flaeche.oeffnungen or []):
        z = _linienzug(teilung, model, loch)
        if z is not None and len(z[0]) >= 3:
            ringe3.append(z[0])
            quellen.append(z[1])
    alle = np.vstack(ringe3)
    c, e1, e2, n, abw = ausgleichsebene(alle)
    gr = float(np.linalg.norm(alle - c, axis=1).max())
    eben = gr > 0 and abw <= EBENHEIT * gr
    if not eben:
        if len(ringe3) == 1:
            P, T, meldung = _coons_netz(model, flaeche, teilung)
            if not meldung:
                return P, T, "", []
        achse = zylinderpassung(model, flaeche, alle)
        if achse is not None:
            P, T, fehlt = _zylindernetz(flaeche, ringe3, teilung.h, achse)
            if len(T):
                return P, T, "", _linien_zu(fehlt, ringe3, quellen)
    ringe = [np.stack([(R - c) @ e1, (R - c) @ e2], axis=1) for R in ringe3]
    P2, T, fehlt = _dreiecke_2d(ringe, teilung.h)
    if not len(T):
        return (np.zeros((0, 3)), np.zeros((0, 3), int),
                "Netz in der Ebene misslungen", _linien_zu(fehlt, ringe3, quellen))
    if eben:
        P = c + P2[:, 0:1] * e1 + P2[:, 1:2] * e2
    else:
        P = _harmonisch_heben(P2, T, ringe3, c, e1, e2, n)
    return P, T, "", _linien_zu(fehlt, ringe3, quellen)


def _linien_zu(strecken: list, ringe3: list, quellen: list) -> list:
    """Zu fehlenden Randstrecken die Linien nennen, aus denen sie stammen."""
    if not strecken:
        return []
    grenzen, basis = [], 0
    for R in ringe3:
        grenzen.append((basis, basis + len(R)))
        basis += len(R)
    namen = set()
    for a, b in strecken:
        for k, (lo, hi) in enumerate(grenzen):
            if lo <= a < hi:
                namen.add(quellen[k][(a - lo) % (hi - lo)])
                break
    return sorted(namen)


def zylinderpassung(model: Model, flaeche, punkte: np.ndarray,
                    toleranz: float = 1e-6) -> tuple | None:
    """Achse und Halbmesser des Zylinders, auf dem die Flaeche liegt - oder None.

    Volumenmodelle aus RFEM bestehen zum grossen Teil aus Zylinderflaechen:
    jede Bohrung, jedes Auge, jede Buchse. Ihr Rand enthaelt Boegen, und jeder
    Bogen kennt seinen Mittelpunkt und seine Ebenennormale - das ist bereits
    die Zylinderachse. Geprueft wird sie an **allen** Randpunkten: liegen alle
    im selben Abstand von dieser Achse, ist es ein Zylinder.

    Das lohnt die Muehe, weil eine solche Flaeche danach in der Abwicklung
    (Bogenlaenge quer, Achsrichtung laengs) vernetzt werden kann - ein ebenes
    Gebiet ohne Verzerrung, und das Netz liegt hinterher **genau** auf dem
    Zylinder. Ueber die Ausgleichsebene ginge das nicht: eine halbe
    Zylinderschale faltet sich dort auf sich selbst.
    """
    if len(punkte) < 4:
        return None
    for name in (flaeche.linien or []):
        ln = model.lines.get(name)
        if ln is None or (ln.typ or "polyline") == "polyline":
            continue
        try:
            k = ln.kurve(model)
        except Exception:                   # noqa: BLE001
            continue
        mitte = getattr(k, "mitte", None)
        e1, e2 = getattr(k, "e1", None), getattr(k, "e2", None)
        if mitte is None or e1 is None or e2 is None:
            continue
        d = np.cross(np.asarray(e1, float), np.asarray(e2, float))
        nd = float(np.linalg.norm(d))
        if nd < 1e-12:
            continue
        d = d / nd
        c = np.asarray(mitte, float)
        rel = punkte - c
        quer = rel - np.outer(rel @ d, d)
        r = np.linalg.norm(quer, axis=1)
        rm = float(r.mean())
        if rm <= 0:
            continue
        if float(np.abs(r - rm).max()) <= toleranz * rm:
            return c, d, rm
    return None


def _zylindernetz(flaeche, ringe3: list, h: float, achse: tuple) -> tuple:
    """Krumme Flaeche auf einem Zylinder: in der Abwicklung vernetzen.

    Die Abwicklung ist (r * Winkel, Achskoordinate). Der Schnitt fuer den
    Winkel wird in die groesste winkelfreie Luecke gelegt, damit der Rand
    nicht ueber den Sprung von +pi nach -pi laeuft.
    """
    c, d, r = achse
    hilf = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(hilf, d)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(d, e1)
    alle = np.vstack(ringe3)
    rel = alle - c
    w = np.arctan2(rel @ e2, rel @ e1)
    # Groesste Luecke im Winkelband suchen und den Schnitt dorthin legen
    ws = np.sort(w)
    luecken = np.diff(np.concatenate([ws, ws[:1] + 2 * np.pi]))
    schnitt = ws[int(np.argmax(luecken))] + float(luecken.max()) / 2.0
    def eben(P3):
        rel = P3 - c
        wi = np.mod(np.arctan2(rel @ e2, rel @ e1) - schnitt, 2 * np.pi)
        return np.stack([r * wi, rel @ d], axis=1)
    ringe = [eben(R) for R in ringe3]
    P2, T, fehlt = _dreiecke_2d(ringe, h)
    if not len(T):
        return np.zeros((0, 3)), np.zeros((0, 3), int), fehlt
    wi = P2[:, 0] / r + schnitt
    P = (c + np.outer(P2[:, 1], d)
         + r * (np.outer(np.cos(wi), e1) + np.outer(np.sin(wi), e2)))
    # Die Randpunkte genau uebernehmen (Rundung im Winkel)
    P[:len(alle)] = alle
    return P, T, fehlt


def _harmonisch_heben(P2: np.ndarray, T: np.ndarray, ringe3: list,
                      c: np.ndarray, e1: np.ndarray, e2: np.ndarray,
                      n: np.ndarray) -> np.ndarray:
    """Das ebene Netz auf die krumme Flaeche zurueckheben.

    Die Coons-Abbildung braucht vier Randkurven. Eine Flaeche mit fuenf
    Randlinien oder mit einer Bohrung hat sie nicht. Statt aufzugeben wird
    hier die **harmonische Ausdehnung** des Randes genommen: der Abstand jedes
    Randpunktes von der Ausgleichsebene ist bekannt, fuer die inneren Punkte
    folgt er aus der Laplace-Gleichung ``div grad w = 0`` mit dem Rand als
    Randbedingung - also die glatteste Flaeche, die in den gegebenen Rand
    eingespannt ist. Fuer eine Zylinderschale ist das die Zylinderschale.

    Der Rand bleibt dabei **punktgenau** erhalten; die Huelle bleibt dicht.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve
    alle = np.vstack(ringe3)
    n_rand = len(alle)
    w = np.zeros(len(P2))
    w[:n_rand] = (alle - c) @ n
    if len(P2) > n_rand and len(T):
        zeilen, spalten, werte = [], [], []
        for t in T:
            X = P2[t]
            b = np.array([X[1, 1] - X[2, 1], X[2, 1] - X[0, 1], X[0, 1] - X[1, 1]])
            g = np.array([X[2, 0] - X[1, 0], X[0, 0] - X[2, 0], X[1, 0] - X[0, 0]])
            A2 = b[0] * g[1] - b[1] * g[0]          # = +- 2 * Flaeche
            if abs(A2) < 1e-300:
                continue
            ke = (np.outer(b, b) + np.outer(g, g)) / (2.0 * abs(A2))
            for i in range(3):
                for j in range(3):
                    zeilen.append(int(t[i]))
                    spalten.append(int(t[j]))
                    werte.append(ke[i, j])
        K = coo_matrix((werte, (zeilen, spalten)),
                       shape=(len(P2), len(P2))).tocsr()
        frei = np.arange(n_rand, len(P2))
        try:
            rhs = -np.asarray(K[frei][:, :n_rand] @ w[:n_rand]).ravel()
            w[frei] = spsolve(K[frei][:, frei].tocsc(), rhs)
        except Exception:                   # noqa: BLE001 - dann eben eben
            w[frei] = 0.0
        if not np.all(np.isfinite(w)):
            w = np.nan_to_num(w)
    return c + P2[:, 0:1] * e1 + P2[:, 1:2] * e2 + w[:, None] * n


def _coons_netz(model: Model, flaeche, teilung: "Linienteilung") -> tuple:
    """Krumme Vierseitflaeche ueber die Coons-Abbildung ihrer vier Randkurven.

    Der Coons-Fleck ist die Summe der beiden Linearinterpolationen zwischen
    gegenueberliegenden Randkurven, vermindert um die bilineare Interpolation
    der vier Ecken. Fuer eine Zylinderhaelfte - zwei Boegen und zwei Geraden -
    ist er die Flaeche selbst, nicht eine Naeherung.
    """
    stuecke = seiten_im_umlauf(model, flaeche.linien or [])
    if stuecke is None or len(stuecke) != 4:
        return (np.zeros((0, 3)), np.zeros((0, 3), int),
                f"krumme Flaeche mit {len(flaeche.linien or [])} Randlinien")
    seiten = []
    for name, knoten in stuecke:
        pts = teilung.punkte(name)
        if len(pts) < 2:
            return np.zeros((0, 3)), np.zeros((0, 3), int), "Randkurve leer"
        if knoten:
            p0 = model.nodes[int(knoten[0])]
            if np.linalg.norm(pts[0] - p0) > np.linalg.norm(pts[-1] - p0):
                pts = pts[::-1]
        seiten.append(pts)
    unten, rechts, oben, links = seiten
    oben = oben[::-1]                        # gleiche Richtung wie unten
    links = links[::-1]                      # gleiche Richtung wie rechts
    nu, nv = len(unten), len(rechts)
    if len(oben) != nu or len(links) != nv:
        return (np.zeros((0, 3)), np.zeros((0, 3), int),
                "gegenueberliegende Randkurven verschieden fein geteilt")
    u = np.linspace(0.0, 1.0, nu)[:, None, None]
    v = np.linspace(0.0, 1.0, nv)[None, :, None]
    U = unten[:, None, :]
    O = oben[:, None, :]
    L = links[None, :, :]
    R = rechts[None, :, :]
    E = ((1 - u) * (1 - v) * unten[0] + u * (1 - v) * unten[-1]
         + (1 - u) * v * oben[0] + u * v * oben[-1])
    G = (1 - v) * U + v * O + (1 - u) * L + u * R - E
    # Die Raender genau auf die Kurven legen (Rundung)
    G[:, 0, :] = unten
    G[:, -1, :] = oben
    G[0, :, :] = links
    G[-1, :, :] = rechts
    P = G.reshape(-1, 3)
    idx = np.arange(nu * nv).reshape(nu, nv)
    T = []
    for i in range(nu - 1):
        for j in range(nv - 1):
            a, b, c2, d = idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]
            T.append((a, b, c2))
            T.append((a, c2, d))
    return P, np.asarray(T, int), ""


# --------------------------------------------------------------------------
# Schritt 2: vernaehen und Dichtheit
# --------------------------------------------------------------------------
def vernaehen(P: np.ndarray, T: np.ndarray, tol: float) -> tuple:
    """Gleiche Punkte zusammenlegen und entartete Dreiecke entfernen.

    Rueckgabe (Punkte, Dreiecke, Zuordnung alt -> neu, behaltene Dreiecke).
    """
    if not len(P):
        return P, T, np.zeros(0, int), np.zeros(0, bool)
    key = np.round(P / max(tol, 1e-15)).astype(np.int64)
    _, erste, invers = np.unique(key, axis=0, return_index=True, return_inverse=True)
    invers = np.asarray(invers).reshape(-1)
    ordnung = np.argsort(erste)
    neu = np.zeros(len(erste), dtype=int)
    neu[ordnung] = np.arange(len(erste))
    index = neu[invers]
    Pn = np.zeros((len(erste), 3))
    Pn[index] = P
    Tn = index[T] if len(T) else T
    gut = np.ones(len(Tn), bool)
    if len(Tn):
        gut = ((Tn[:, 0] != Tn[:, 1]) & (Tn[:, 1] != Tn[:, 2]) & (Tn[:, 0] != Tn[:, 2]))
        Tn = Tn[gut]
    return Pn, Tn, index, gut


def ausrichten(P: np.ndarray, T: np.ndarray) -> tuple:
    """Alle Dreiecke gleich herum drehen und die Huelle nach aussen kehren.

    Rueckgabe (Dreiecke, Bericht). Der Bericht nennt die Zahl der Kanten, die
    **nicht** in genau zwei Dreiecken liegen - das ist das Mass fuer die
    Dichtheit.
    """
    T = np.asarray(T, int)
    n = len(T)
    if n == 0:
        return T, {"offen": 0, "teile": 0, "volumen": 0.0}
    kante: dict = {}
    for k in range(n):
        a, b, c = T[k]
        for x, y in ((a, b), (b, c), (c, a)):
            kante.setdefault((min(x, y), max(x, y)), []).append(k)
    offen = sum(1 for v in kante.values() if len(v) != 2)
    # Nachbarschaft aufbauen und die Ausrichtung fortpflanzen
    besucht = np.zeros(n, bool)
    teile = 0
    for start in range(n):
        if besucht[start]:
            continue
        teile += 1
        besucht[start] = True
        stapel = [start]
        while stapel:
            k = stapel.pop()
            a, b, c = T[k]
            for x, y in ((a, b), (b, c), (c, a)):
                for m in kante.get((min(x, y), max(x, y)), ()):
                    if m == k or besucht[m]:
                        continue
                    besucht[m] = True
                    # Gleiche Kantenrichtung heisst entgegengesetzte Umlaufsinne
                    p, q, r = T[m]
                    if (x, y) in ((p, q), (q, r), (r, p)):
                        T[m] = [p, r, q]
                    stapel.append(m)
    V = huellvolumen(P, T)
    if V < 0:
        T = T[:, [0, 2, 1]]
        V = -V
    return T, {"offen": offen, "teile": teile, "volumen": float(V)}


# --------------------------------------------------------------------------
# Schritt 3 und 4: Punkte und Tetraeder
# --------------------------------------------------------------------------
#: Wie schnell die Elemente vom feinen Rand weg wachsen duerfen
WACHSTUM = 0.35

#: Groesstes Verhaeltnis Umkugelhalbmesser zu kuerzester Kante. 2.0 ist die
#: uebliche Schranke der Delaunay-Verfeinerung; darunter ist jeder Tetraeder
#: gut geformt - bis auf die Splitter, die kein Kriterium dieser Art erfasst.
KUGELKANTE = 2.0

#: Hoechstzahl der Verfeinerungsdurchgaenge
MAXRUNDEN = 30


def bcc_gitter(P: np.ndarray, T: np.ndarray, h: float,
               index: "Gitterindex" = None) -> np.ndarray:
    """Raumzentriertes kubisches Gitter im Koerper - die erste Fuellung.

    Das BCC-Gitter (Wuerfelecken und Wuerfelmitten) ist das Punktmuster,
    dessen Delaunay-Zerlegung von sich aus gute Tetraeder liefert
    (Labelle/Shewchuk). Es wird hier nur zum **Anlegen** gebraucht: die
    Verfeinerung danach muss so viel weniger nachbessern, dass der ganze
    Koerper in einem Bruchteil der Zeit fertig ist. Das Gitter ist um einen
    krummen Bruchteil von h verschoben, damit seine Punkte nicht ausgerechnet
    auf den achsenparallelen Flaechen des Koerpers liegen.
    """
    if h <= 0 or not len(P):
        return np.zeros((0, 3))
    from scipy.spatial import cKDTree
    lo, hi = P.min(axis=0), P.max(axis=0)
    versatz = np.array([0.1237, 0.2371, 0.3719]) * h
    achsen = [np.arange(lo[k] + versatz[k], hi[k], h) for k in range(3)]
    if any(len(a) == 0 for a in achsen):
        return np.zeros((0, 3))
    G = np.stack(np.meshgrid(*achsen, indexing="ij"), axis=-1).reshape(-1, 3)
    K = np.vstack([G, G + 0.5 * h])
    K = K[np.all((K >= lo) & (K <= hi), axis=1)]
    if not len(K):
        return np.zeros((0, 3))
    if index is None:
        index = Gitterindex(P, T, zelle=max(h, 1e-12))
    K = K[innen(K, P, T, index)]
    if not len(K):
        return np.zeros((0, 3))
    K = K[cKDTree(P).query(K)[0] > RANDABSTAND * h]
    if not len(K):
        return np.zeros((0, 3))
    stoerung = np.random.default_rng(20240904).normal(scale=1e-3 * h, size=K.shape)
    return K + stoerung


def randkantenlaenge(P: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Mittlere Laenge der Dreieckskanten an jedem Randpunkt.

    Sie ist das Mass fuer die oertliche Feinheit der Huelle: um eine Bohrung
    von 20 mm sind die Randdreiecke klein, auf einer 900-mm-Platte gross. Das
    Innere muss dieser Feinheit folgen, sonst stehen grobe Innenpunkte neben
    feinen Randpunkten - und dazwischen entstehen Splitter.
    """
    summe = np.zeros(len(P))
    zahl = np.zeros(len(P))
    for i, j in ((0, 1), (1, 2), (2, 0)):
        L = np.linalg.norm(P[T[:, i]] - P[T[:, j]], axis=1)
        np.add.at(summe, T[:, i], L)
        np.add.at(summe, T[:, j], L)
        np.add.at(zahl, T[:, i], 1.0)
        np.add.at(zahl, T[:, j], 1.0)
    out = np.zeros(len(P))
    gut = zahl > 0
    out[gut] = summe[gut] / zahl[gut]
    out[~gut] = out[gut].mean() if gut.any() else 1.0
    return out


def umkugel(P: np.ndarray, TET: np.ndarray) -> tuple:
    """Mittelpunkt und Halbmesser der Umkugel je Tetraeder.

    Der Mittelpunkt loest das Gleichungssystem der drei Mittelsenkrechten

        2 (b-a) . x = |b|^2 - |a|^2      (ebenso mit c und d).
    """
    if not len(TET):
        return np.zeros((0, 3)), np.zeros(0)
    a, b, c, d = P[TET[:, 0]], P[TET[:, 1]], P[TET[:, 2]], P[TET[:, 3]]
    A = 2.0 * np.stack([b - a, c - a, d - a], axis=1)
    q = lambda X: np.einsum("ij,ij->i", X, X)          # noqa: E731
    r = np.stack([q(b) - q(a), q(c) - q(a), q(d) - q(a)], axis=1)
    M = np.array(a, dtype=float, copy=True)
    det = np.linalg.det(A)
    gut = np.abs(det) > 1e-300
    if gut.any():
        # b als Spaltenvektor je Gleichungssystem - sonst deutet numpy den
        # Stapel als eine einzige rechte Seite
        M[gut] = np.linalg.solve(A[gut], r[gut][:, :, None])[:, :, 0]
    return M, np.linalg.norm(M - a, axis=1)


def kuerzeste_kante(P: np.ndarray, TET: np.ndarray) -> np.ndarray:
    """Kuerzeste Kante je Tetraeder."""
    if not len(TET):
        return np.zeros(0)
    kanten = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    return np.min(np.stack([np.linalg.norm(P[TET[:, i]] - P[TET[:, j]], axis=1)
                            for i, j in kanten], axis=1), axis=1)


def _ausduennen(X: np.ndarray, abstand: np.ndarray) -> np.ndarray:
    """Punkte ausduennen, bis keiner dem anderen naeher kommt als erlaubt.

    Gierig in fester Reihenfolge (nach Koordinaten sortiert) - das Ergebnis
    haengt damit nicht davon ab, in welcher Reihenfolge die Tetraeder aus der
    Zerlegung gekommen sind, und ist wiederholbar. Die zu nahen Paare kommen
    aus dem k-d-Baum; ohne ihn waere das ein Vergleich jeder mit jedem.
    """
    if len(X) < 2:
        return X
    from scipy.spatial import cKDTree
    ordnung = np.lexsort((X[:, 2], X[:, 1], X[:, 0]))
    rang = np.empty(len(X), dtype=np.int64)
    rang[ordnung] = np.arange(len(X))
    paare = cKDTree(X).query_pairs(float(np.max(abstand)), output_type="ndarray")
    behalten = np.ones(len(X), bool)
    if len(paare):
        d = np.linalg.norm(X[paare[:, 0]] - X[paare[:, 1]], axis=1)
        zu_nah = d < np.minimum(abstand[paare[:, 0]], abstand[paare[:, 1]])
        paare = paare[zu_nah]
    nachbarn: dict = {}
    for a, b in paare:
        nachbarn.setdefault(int(a), []).append(int(b))
        nachbarn.setdefault(int(b), []).append(int(a))
    for i in ordnung:
        i = int(i)
        if not behalten[i]:
            continue
        for j in nachbarn.get(i, ()):
            if rang[j] > rang[i]:
                behalten[j] = False
    return X[behalten]


def _innere(punkte: np.ndarray, simplices: np.ndarray, P: np.ndarray,
            T: np.ndarray, index: "Gitterindex", h: float) -> tuple:
    """Die Tetraeder der Zerlegung, die im Koerper liegen - mit ihren Volumen.

    Die Delaunay-Zerlegung fuellt immer die **konvexe Huelle** der Punktwolke.
    Alles, was in einer Einbuchtung des Koerpers liegt, gehoert nicht dazu und
    wird hier ueber den Schwerpunkt aussortiert.
    """
    TET = np.asarray(simplices, int).copy()
    if not len(TET):
        return TET, np.zeros(0)
    V = tetraedervolumen(punkte, TET)
    dreh = V < 0
    TET[dreh] = TET[dreh][:, [0, 2, 1, 3]]
    V = np.abs(V)
    behalt = V > FLACH * h ** 3
    TET, V = TET[behalt], V[behalt]
    if not len(TET):
        return TET, V
    drin = innen(punkte[TET].mean(axis=1), P, T, index)
    return TET[drin], V[drin]


def tetraedern(P: np.ndarray, T: np.ndarray, h: float) -> tuple:
    """Aus der geschlossenen Huelle (P, T) ein Tetraedernetz machen.

    **Delaunay-Verfeinerung.** Begonnen wird mit den Randpunkten allein. Dann
    wird wiederholt der Umkugelmittelpunkt der schlechten Tetraeder eingefuegt
    - das ist genau der Punkt, der ihre Umkugel am wirksamsten leert und sie
    damit beseitigt. Schlecht heisst:

    * **zu gross** - Umkugelhalbmesser groesser als die halbe Sollkantenlaenge
      an seinem Ort, oder
    * **schlecht geformt** - Umkugelhalbmesser mehr als das KUGELKANTE-fache
      der kuerzesten Kante (Ruppert, Shewchuk).

    Die Sollkantenlaenge waechst vom Rand weg:

        h_lokal(x) = min(h, Randkantenlaenge am naechsten Randpunkt
                            + WACHSTUM * Abstand zum Rand)

    So bekommt eine 20-mm-Bohrung in einer 900-mm-Platte kleine Elemente, ohne
    dass die ganze Platte fein wird. Ein festes Gitter koennte das nicht: es
    haette entweder ueberall die feine oder ueberall die grobe Weite.

    Rueckgabe (Punkte, Tetraeder, Bericht).
    """
    from scipy.spatial import Delaunay, cKDTree
    bericht = {"randpunkte": len(P), "innenpunkte": 0, "tetraeder": 0,
               "volumen": 0.0, "sollvolumen": huellvolumen(P, T),
               "guete": 0.0, "randtreue": 0.0, "verfeinerungen": 0}
    if len(P) < 4 or not len(T):
        return P, np.zeros((0, 4), int), bericht
    # Kleinere Zellen als die Zielkantenlaenge: je weniger Dreiecke in einer
    # Zelle stehen, desto weniger Paare hat die Strahlenzaehlung zu pruefen.
    index = Gitterindex(P, T, zelle=max(0.5 * h, 1e-12))
    kante = randkantenlaenge(P, T)
    baum_rand = cKDTree(P)

    def sollgroesse(X: np.ndarray) -> np.ndarray:
        d, i = baum_rand.query(X)
        return np.minimum(h, kante[i] + WACHSTUM * d)

    G = bcc_gitter(P, T, h, index)
    start = np.vstack([P, G]) if len(G) else P
    try:
        tri = Delaunay(start, incremental=True, qhull_options="Qc Q12")
    except Exception as ex:                 # noqa: BLE001
        bericht["fehler"] = f"Delaunay-Zerlegung misslungen: {ex}"
        return P, np.zeros((0, 4), int), bericht
    try:
        for runde in range(MAXRUNDEN):
            punkte = np.asarray(tri.points, float)
            TET = np.asarray(tri.simplices, int)
            if not len(TET):
                break
            # Waehrend der Verfeinerung wird **nicht** aussortiert, was
            # ausserhalb des Koerpers liegt: das kostet bei hunderttausend
            # Tetraedern je Durchgang mehr Zeit als die Verfeinerung selbst.
            # Es genuegt, die wenigen neuen Punkte zu pruefen - ein Punkt
            # ausserhalb wird ohnehin nicht eingefuegt.
            M, R = umkugel(punkte, TET)
            L = kuerzeste_kante(punkte, TET)
            h_lok = sollgroesse(M)
            # Der regelmaessige Tetraeder mit der Kante a hat den
            # Umkugelhalbmesser a*sqrt(6)/4 = 0.6124 a - das ist das Mass
            schlecht = (R > 0.62 * h_lok) | (R > KUGELKANTE * L)
            if not schlecht.any():
                break
            K = M[schlecht]
            K = K[innen(K, P, T, index)]
            if not len(K):
                break
            hk = sollgroesse(K)
            # Nicht zu nah an vorhandene Punkte und nicht zu nah an den Rand -
            # beides erzeugte sonst Splitter statt guter Tetraeder
            d_alt, _ = cKDTree(punkte).query(K)
            d_rand = abstand_zur_huelle(K, P, T)
            K = K[(d_alt > 0.5 * hk) & (d_rand > 0.4 * hk)]
            if not len(K):
                break
            K = _ausduennen(K, 0.5 * sollgroesse(K))
            if not len(K):
                break
            # Winzige, immer gleiche Stoerung: sonst liegen die neuen Punkte
            # leicht wieder auf gemeinsamen Kugeln, und Qhull antwortet mit
            # flachen Tetraedern
            rng = np.random.default_rng(20240906 + runde)
            tri.add_points(K + rng.normal(scale=1e-4 * h, size=K.shape))
            bericht["verfeinerungen"] = runde + 1
            # Wenn kaum noch Punkte dazukommen, ist nichts mehr zu holen
            if len(K) < 0.005 * len(punkte):
                break
        punkte = np.asarray(tri.points, float)
        TET, V = _innere(punkte, tri.simplices, P, T, index, h)
    except Exception as ex:                 # noqa: BLE001
        bericht["fehler"] = f"Verfeinerung misslungen: {ex}"
        return P, np.zeros((0, 4), int), bericht
    finally:
        tri.close()
    bericht["innenpunkte"] = len(punkte) - len(P)
    bericht["tetraeder"] = len(TET)
    bericht["volumen"] = float(V.sum())
    if len(TET):
        q = guete(punkte, TET)
        bericht["guete"] = float(q.min())
        bericht["guete_mittel"] = float(q.mean())
        bericht["splitter"] = int(np.count_nonzero(q < 0.1))
        bericht["randtreue"], bericht["randabweichung"] = randtreue(
            punkte, TET, P, T, tol=0.2 * h)
    return punkte, TET, bericht


def huelle_verfeinern(P: np.ndarray, T: np.ndarray, welche,
                      quelle: list = None) -> tuple:
    """Genannte Huelldreiecke im Schwerpunkt teilen (1 -> 3).

    Der neue Punkt liegt **in** dem Dreieck, also auf der Huelle: die
    Geometrie aendert sich nicht, nur ihre Aufloesung. Weil der Punkt keine
    Kante beruehrt, bleibt die Huelle dabei zusammenhaengend - es entstehen
    keine haengenden Knoten.
    """
    welche = set(int(x) for x in welche)
    if not welche:
        return P, T, list(quelle or [])
    neu_p = [P]
    neu_t = []
    neu_q = []
    n = len(P)
    for k, t in enumerate(T):
        q = quelle[k] if quelle is not None and k < len(quelle) else ""
        if k not in welche:
            neu_t.append(t)
            neu_q.append(q)
            continue
        a, b, c = t
        m = P[[a, b, c]].mean(axis=0)
        neu_p.append(m[None, :])
        neu_t.extend([(a, b, n), (b, c, n), (c, a, n)])
        neu_q.extend([q, q, q])
        n += 1
    return np.vstack(neu_p), np.asarray(neu_t, int), neu_q


def tetraedern_treu(P: np.ndarray, T: np.ndarray, h: float,
                    runden: int = 3, quelle: list = None) -> tuple:
    """Tetraedern und dabei den Rand nachfuehren, wo er nicht getroffen wurde.

    Eine einspringende Kante - der Innenwinkel eines L-Koerpers, die Kehle
    eines Lagerbocks - wird von der Delaunay-Zerlegung gern ueberbrueckt. Die
    uebergebrueckten Tetraeder liegen ausserhalb und fallen weg; zurueck
    bleibt eine Kerbe im Netz. Man sieht sie am fehlenden Volumen und an den
    freien Elementseiten, die nicht auf der Huelle liegen.

    Hier wird die Huelle **genau dort** feiner gemacht: die Dreiecke neben den
    danebenliegenden freien Seiten werden geteilt, und es wird noch einmal
    zerlegt. Das setzt die Punkte hin, wo sie gebraucht werden, statt ueberall
    - eine gleichmaessige Verfeinerung wuerde nur Splitter erzeugen.
    """
    from scipy.spatial import cKDTree
    bestes = None
    for runde in range(max(1, runden)):
        Pn, TET, bericht = tetraedern(P, T, h)
        bericht["runden"] = runde + 1
        bericht["huelldreiecke"] = len(T)
        soll = bericht["sollvolumen"]
        fehl = abs(bericht["volumen"] - soll) / soll if soll > 0 else 1.0
        bericht["volumenabweichung"] = fehl
        if bestes is None or fehl < bestes[3]:
            bestes = (Pn, TET, bericht, fehl, P, T, quelle)
        if not len(TET) or (fehl <= 1e-4 and bericht.get("randtreue", 0) >= 0.999):
            break
        if runde == runden - 1:
            break
        # Wo liegt der Netzrand daneben?
        frei = freie_seiten(TET)
        if not len(frei):
            break
        schwer = Pn[frei].mean(axis=1)
        gr = float(np.linalg.norm(P - P.mean(axis=0), axis=1).max())
        d = abstand_zur_huelle(schwer, P, T)
        daneben = schwer[d > max(1e-9 * gr, 1e-12)]
        if not len(daneben):
            break
        # Die naechstliegenden Huelldreiecke teilen
        baum = cKDTree(P[T].mean(axis=1))
        _, nn = baum.query(daneben, k=min(3, len(T)))
        P, T, quelle = huelle_verfeinern(P, T, np.unique(np.atleast_2d(nn)), quelle)
    Pn, TET, bericht, _, P, T, quelle = bestes
    return Pn, TET, bericht, P, T, quelle


def guete(P: np.ndarray, TET: np.ndarray) -> np.ndarray:
    """Formguete je Tetraeder: 1 fuer den regelmaessigen, 0 fuer den flachen.

        q = 12 * (3V)^(2/3) / Summe(l_i^2)

    Der Vorfaktor ist so gewaehlt, dass der regelmaessige Tetraeder q = 1
    bekommt. Das ist das uebliche Mass; ANSYS und RFEM nennen es
    "element quality".
    """
    if not len(TET):
        return np.zeros(0)
    V = np.abs(tetraedervolumen(P, TET))
    kanten = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    L2 = sum(np.sum((P[TET[:, a]] - P[TET[:, b]]) ** 2, axis=1) for a, b in kanten)
    mit = L2 > 0
    q = np.zeros(len(TET))
    q[mit] = 12.0 * (3.0 * V[mit]) ** (2.0 / 3.0) / L2[mit]
    return q


def freie_seiten(TET: np.ndarray) -> np.ndarray:
    """Die Seitenflaechen, die nur zu einem Tetraeder gehoeren - der Netzrand."""
    if not len(TET):
        return np.zeros((0, 3), int)
    seiten = np.vstack([TET[:, [0, 2, 1]], TET[:, [0, 1, 3]],
                        TET[:, [1, 2, 3]], TET[:, [0, 3, 2]]])
    key = np.sort(seiten, axis=1)
    _, erste, zahl = np.unique(key, axis=0, return_index=True, return_counts=True)
    return seiten[erste[zahl == 1]]


def punkt_dreieck_abstand(q: np.ndarray, a: np.ndarray, b: np.ndarray,
                          c: np.ndarray) -> np.ndarray:
    """Kuerzester Abstand jedes Punktes zu seinem Dreieck (paarweise).

    Der Fusspunkt wird in baryzentrischen Koordinaten gesucht; liegt er
    ausserhalb, wird auf die naechste Kante beziehungsweise Ecke geklemmt.
    Das ist die uebliche geschlossene Loesung ohne Fallunterscheidung im Code:
    erst auf die Ebene, dann die Kanten, dann die Ecken.
    """
    ab, ac, aq = b - a, c - a, q - a
    d00 = np.einsum("ij,ij->i", ab, ab)
    d01 = np.einsum("ij,ij->i", ab, ac)
    d11 = np.einsum("ij,ij->i", ac, ac)
    d20 = np.einsum("ij,ij->i", aq, ab)
    d21 = np.einsum("ij,ij->i", aq, ac)
    nen = d00 * d11 - d01 * d01
    gut = np.abs(nen) > 1e-300
    v = np.zeros(len(q))
    w = np.zeros(len(q))
    v[gut] = (d11[gut] * d20[gut] - d01[gut] * d21[gut]) / nen[gut]
    w[gut] = (d00[gut] * d21[gut] - d01[gut] * d20[gut]) / nen[gut]
    # Auf das Dreieck klemmen: erst die Ecken, dann die Kanten
    v2, w2 = np.clip(v, 0.0, 1.0), np.clip(w, 0.0, 1.0)
    ueber = v2 + w2 > 1.0
    if ueber.any():
        s = v2[ueber] + w2[ueber]
        v2[ueber] /= s
        w2[ueber] /= s
    fuss = a + v2[:, None] * ab + w2[:, None] * ac
    return np.linalg.norm(q - fuss, axis=1)


def abstand_zur_huelle(q: np.ndarray, RP: np.ndarray, RT: np.ndarray,
                       nachbarn: int = 24) -> np.ndarray:
    """Abstand jedes Punktes zur Dreieckshuelle (naechste Dreiecke exakt)."""
    from scipy.spatial import cKDTree
    q = np.atleast_2d(np.asarray(q, float))
    if not len(RT) or not len(q):
        return np.full(len(q), np.inf)
    schwer = RP[RT].mean(axis=1)
    k = min(nachbarn, len(RT))
    _, nn = cKDTree(schwer).query(q, k=k)
    nn = np.atleast_2d(nn)
    out = np.full(len(q), np.inf)
    for j in range(nn.shape[1]):
        t = RT[nn[:, j]]
        d = punkt_dreieck_abstand(q, RP[t[:, 0]], RP[t[:, 1]], RP[t[:, 2]])
        out = np.minimum(out, d)
    return out


def randtreue(P: np.ndarray, TET: np.ndarray, RP: np.ndarray, RT: np.ndarray,
              tol: float = 0.0) -> tuple:
    """Wie gut der Netzrand auf der Huelle liegt: (Anteil, groesster Abstand).

    Nicht Dreieck gegen Dreieck: ein ebenes Viereck laesst sich ueber beide
    Diagonalen teilen, und die Delaunay-Zerlegung waehlt nicht zwingend
    dieselbe wie das Randnetz - auf einer Zylinderschale liegen die beiden
    Teilungen sogar merklich auseinander, ohne dass eine von beiden falsch
    waere. Geprueft wird darum der **Abstand** jeder freien Elementseite zur
    Huelle. Wo die Zerlegung eine Einbuchtung nicht getroffen hat, liegen
    freie Seiten mitten im Koerper - das sind Abstaende in der Groessenordnung
    der Elementkante, und genau die zaehlen gegen das Netz.

    ``tol`` ist der Abstand, bis zu dem eine freie Seite noch als auf der
    Huelle liegend gilt (Vorgabe: ein Fuenftel der Zielkantenlaenge).
    Rueckgabe (1.0, 0.0) = der Netzrand deckt sich mit der Huelle.
    """
    if not len(RT) or not len(TET):
        return 0.0, float("inf")
    frei = freie_seiten(TET)
    if not len(frei):
        return 0.0, float("inf")
    gr = float(np.linalg.norm(RP - RP.mean(axis=0), axis=1).max())
    tol = tol if tol > 0 else max(1e-9 * max(gr, 1.0), 1e-12)
    schwer = P[frei].mean(axis=1)
    d = abstand_zur_huelle(schwer, RP, RT)
    a, b, c = P[frei[:, 0]], P[frei[:, 1]], P[frei[:, 2]]
    A = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2.0
    daneben = float(A[d > tol].sum())
    soll = huellflaeche(RP, RT)
    anteil = float(max(0.0, 1.0 - daneben / soll)) if soll > 0 else 0.0
    return anteil, float(d.max())


# --------------------------------------------------------------------------
# Einbau ins Modell
# --------------------------------------------------------------------------
def _ausdehnung(model: Model, koerper) -> float:
    """Groesste Kantenlaenge des umschliessenden Quaders eines Koerpers."""
    punkte = []
    for name in (koerper.flaechen or []):
        f = model.flaechen.get(name)
        if f is None:
            continue
        P = f.randpunkte(model, 8)
        if len(P):
            punkte.append(P)
    if not punkte:
        return 0.0
    P = np.vstack(punkte)
    return float(np.max(P.max(axis=0) - P.min(axis=0)))


def randschale(model: Model, koerper, h: float, log: list = None) -> tuple:
    """Die geschlossene Dreieckshuelle eines Koerpers: (P, T, Bericht).

    Der Bericht fuehrt unter ``quelle`` je Dreieck die Randflaeche mit, von
    der es stammt. Darueber teilen sich zwei Koerper, die dieselbe Flaeche
    berandet, spaeter dieselben Knoten.

    Fehlt einer Flaeche eine Randstrecke, wird die **Linie** feiner geteilt -
    fuer alle Flaechen, die sie berandet. Nur so bleiben die Netze der
    Nachbarflaechen aufeinander passend; eine Flaeche fuer sich zu verfeinern
    risse die Huelle auf.
    """
    from .importers import _common as C
    flaechen = [model.flaechen.get(x) for x in (koerper.flaechen or [])]
    fehlt = [x for x, f in zip(koerper.flaechen or [], flaechen) if f is None]
    if fehlt:
        return (np.zeros((0, 3)), np.zeros((0, 3), int),
                {"fehler": f"Randflächen fehlen: {', '.join(fehlt)}"})
    teilung = Linienteilung(model, flaechen, h)
    nachgeteilt: set = set()
    for runde in range(4):
        P_teile, T_teile, quelle, gruende = [], [], [], {}
        zu_grob: set = set()
        n_punkte = 0
        for f in flaechen:
            Pf, Tf, meldung, grob = flaechennetz(model, f, teilung)
            zu_grob.update(grob)
            if meldung or not len(Tf):
                gruende[meldung or "leer"] = gruende.get(meldung or "leer", 0) + 1
                continue
            P_teile.append(Pf)
            T_teile.append(Tf + n_punkte)
            quelle.extend([f.name] * len(Tf))
            n_punkte += len(Pf)
        if not P_teile:
            return (np.zeros((0, 3)), np.zeros((0, 3), int),
                    {"fehler": "keine Randfläche vernetzbar", "gruende": gruende})
        P = np.vstack(P_teile)
        T = np.vstack(T_teile)
        P, T, _, behalten = vernaehen(P, T, tol=max(h * 1e-4, 1e-9))
        quelle = [q for q, b in zip(quelle, behalten) if b]
        T, bericht = ausrichten(P, T)
        if not bericht["offen"] or not zu_grob or runde == 3:
            break
        if not teilung.verfeinern(zu_grob):
            break
        nachgeteilt.update(zu_grob)
    bericht["gruende"] = gruende
    bericht["quelle"] = quelle
    bericht["flaechen"] = len(flaechen)
    bericht["ohne_netz"] = sum(gruende.values())
    bericht["dreiecke"] = len(T)
    bericht["nachgeteilt"] = sorted(nachgeteilt)
    if log is not None and gruende:
        for grund, anzahl in sorted(gruende.items()):
            C.warn(log, f"  Volumen {koerper.name}: {anzahl} Randfläche(n) ohne "
                        f"Netz ({grund})")
    if log is not None and nachgeteilt:
        C.say(log, f"  Volumen {koerper.name}: {len(nachgeteilt)} Randlinie(n) "
                   "feiner geteilt, damit die Hülle schließt")
    return P, T, bericht


def _knoten_anlegen(model: Model, koerper, Pn: np.ndarray, benutzt: np.ndarray,
                    n_rand: int, T: np.ndarray, quelle: list,
                    cache: dict = None) -> np.ndarray:
    """Die Netzpunkte als Modellknoten anlegen - gemeinsame Flaechen geteilt.

    Zwei Volumenkoerper, die **dieselbe** Randflaeche haben, muessen dort
    dieselben Knoten benutzen; sonst stehen sie unverbunden nebeneinander und
    das Modell zerfaellt. Geteilt wird ausdruecklich ueber die Flaeche, nicht
    ueber die Koordinate: zwei Flaechen, die aufeinanderliegen, aber
    verschiedene Objekte sind, gehoeren zu einer Kontaktfuge und duerfen
    **nicht** verschweisst werden.

    Die Eckknoten der Randlinien sind ohnehin schon Modellknoten; sie werden
    wiederverwendet, damit Lasten und Lager an der Geometrie wirksam bleiben.
    """
    neu = np.full(len(Pn), -1, dtype=int)
    tol = 1e-9
    schluessel = lambda p: (round(float(p[0]) / tol), round(float(p[1]) / tol),  # noqa: E731
                            round(float(p[2]) / tol))
    # 1) vorhandene Knoten der Randlinien dieses Koerpers
    vorhanden: dict = {}
    for fname in (koerper.flaechen or []):
        f = model.flaechen.get(fname)
        if f is None:
            continue
        for lname in list(f.linien or []) + [x for loch in (f.oeffnungen or []) for x in loch]:
            ln = model.lines.get(lname)
            if ln is None:
                continue
            for k in ln.nodes:
                if 0 <= int(k) < model.nn:
                    vorhanden.setdefault(schluessel(model.nodes[int(k)]), int(k))
    # 2) Punkte, die schon fuer eine gemeinsame Flaeche anderswo angelegt wurden
    punkt_flaeche: dict = {}
    if cache is not None and len(T):
        for t, q in zip(T, quelle):
            for i in t:
                if int(i) < n_rand:
                    punkt_flaeche.setdefault(int(i), q)
    for i in benutzt:
        i = int(i)
        p = Pn[i]
        s = schluessel(p)
        k = vorhanden.get(s)
        if k is None and cache is not None and i in punkt_flaeche:
            k = cache.get((punkt_flaeche[i], s))
        if k is None:
            k = int(model.add_node(*p))
            if cache is not None and i in punkt_flaeche:
                cache[(punkt_flaeche[i], s)] = k
        neu[i] = k
    return neu


def mesh_koerper_frei(model: Model, koerper, h: float = 0.0,
                      log: list = None, cache: dict = None) -> list[int]:
    """Einen Volumenkoerper frei in Tetraeder vernetzen.

    ``h`` ist die angestrebte Kantenlaenge; 0 nimmt die Netzeinstellungen des
    Modells. ``cache`` ist ein Woerterbuch, das ueber mehrere Koerper hinweg
    dieselben Knoten fuer **gemeinsame Randflaechen** vergibt - ohne es steht
    jeder Koerper fuer sich und das Modell zerfaellt in Teile. Rueckgabe: die
    Nummern der neuen Elemente (leer, wenn nicht vernetzt - der Grund steht
    dann im Protokoll).
    """
    from .importers import _common as C
    if h <= 0:
        netz = getattr(model, "netz", None)
        h = float(getattr(netz, "ziellaenge", 0.0) or 0.0)
    if h <= 0:
        h = STANDARDLAENGE
    mat = koerper.material or C.ensure_material(model, log=log)

    # Ein 20-mm-Bolzen bei 50 mm Zielkantenlaenge haette kein einziges
    # Element. Die Kantenlaenge wird darum je Koerper an seine Groesse
    # angepasst - nach unten, nie nach oben.
    gross = _ausdehnung(model, koerper)
    if gross > 0 and h > gross / MINDESTTEILUNG:
        h_neu = gross / MINDESTTEILUNG
        C.say(log, f"Volumen {koerper.name}: Kantenlänge {h * 1e3:.0f} mm ist für "
                   f"dieses Bauteil ({gross * 1e3:.0f} mm groß) zu grob - "
                   f"mit {h_neu * 1e3:.1f} mm vernetzt.")
        h = h_neu

    P, T, bericht = randschale(model, koerper, h, log)
    if bericht.get("fehler"):
        C.warn(log, f"Volumen {koerper.name}: {bericht['fehler']} - nicht vernetzt.")
        return []
    if bericht.get("offen"):
        C.warn(log, f"Volumen {koerper.name}: die Randhülle ist nicht dicht "
                    f"({bericht['offen']} Kanten liegen nicht in genau zwei "
                    "Dreiecken) - nicht vernetzt. Ein Netz aus einer undichten "
                    "Hülle wäre stillschweigend falsch.")
        return []
    if bericht.get("teile", 1) > 1:
        C.warn(log, f"Volumen {koerper.name}: die Randflächen bilden "
                    f"{bericht['teile']} getrennte Hüllen - nicht vernetzt.")
        return []
    if bericht.get("volumen", 0.0) <= 0:
        C.warn(log, f"Volumen {koerper.name}: die Hülle umschließt kein Volumen "
                    "- nicht vernetzt.")
        return []

    quelle = bericht.get("quelle") or []
    n_rand = len(P)
    Pn, TET, tb, P, T, quelle = tetraedern_treu(P, T, h, quelle=quelle)
    if tb.get("fehler"):
        C.warn(log, f"Volumen {koerper.name}: {tb['fehler']}")
        return []
    if not len(TET):
        C.warn(log, f"Volumen {koerper.name}: kein Tetraeder entstanden.")
        return []

    soll = bericht["volumen"]
    ist = tb["volumen"]
    abw = abs(ist - soll) / soll if soll > 0 else 1.0

    # Nur die wirklich benutzten Punkte ins Modell uebernehmen
    benutzt = np.unique(TET)
    neu = _knoten_anlegen(model, koerper, Pn, benutzt, len(P), T, quelle, cache)
    els = [model.add_element("tet4", [int(neu[i]) for i in t], mat,
                             group=koerper.name) for t in TET]
    koerper.elemente = els
    koerper.kommentar = (f"{len(els)} Tetraeder, Kantenlänge {h * 1e3:.0f} mm, "
                         f"Güte min {tb['guete']:.3f}")
    C.say(log, f"Volumen {koerper.name}: {len(els)} Tetraeder aus "
               f"{tb.get('huelldreiecke', bericht['dreiecke'])} Randdreiecken "
               f"(Kantenlänge {h * 1e3:.0f} mm, {len(benutzt)} Knoten"
               + (f", {tb['runden']} Durchgänge" if tb.get("runden", 1) > 1 else "")
               + ")")
    C.say(log, f"  Volumen {ist:.6g} m^3 gegen {soll:.6g} m^3 aus der Hülle "
               f"(Abweichung {abw * 100:.3f} %), Güte min {tb['guete']:.3f} / "
               f"Mittel {tb.get('guete_mittel', 0.0):.3f}, "
               f"Randtreue {tb['randtreue'] * 100:.2f} % "
               f"(größter Abstand zur Hülle {tb.get('randabweichung', 0.0) * 1e3:.2f} mm)")
    if tb.get("splitter"):
        C.say(log, f"  {tb['splitter']} Splitter (Güte unter 0.1) von "
                   f"{len(TET)} Tetraedern")
    if abw > 1e-3:
        C.warn(log, f"  Volumen {koerper.name}: das Netz gibt {abw * 100:.3f} % "
                    "weniger Volumen als die Hülle - der Rand ist nicht überall "
                    "getroffen. Mit kleinerer Kantenlänge nachvernetzen.")
    if tb["randtreue"] < 0.99:
        C.warn(log, f"  Volumen {koerper.name}: nur {tb['randtreue'] * 100:.1f} % "
                    "des Netzrandes liegen auf der Hülle.")
    if tb.get("guete", 1.0) < 0.02:
        C.warn(log, f"  Volumen {koerper.name}: schlechtester Tetraeder hat die "
                    f"Güte {tb['guete']:.4f} - solche Splitter machen die "
                    "Steifigkeitsmatrix schlecht konditioniert.")
    return els
