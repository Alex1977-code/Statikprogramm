"""
Lastbezug: global, lokale Flaechenachsen, eigene Koordinatensysteme
(Oberflaechenpaket B, Bestellung des Anwenders vom 08.11.2026).

Anlass: „ich habe gerade -5kn/m2 als flächenlast augetragen und z-achse zeigt
nach oben und die fläche verformt sich nach oben“. Die Flaechenlast der Maske
wirkte bis dahin immer **senkrecht zur Flaeche** (Geometrielast.richtung leer),
und dort haengt das Vorzeichen an der Normalen der Flaeche - also am Umlaufsinn
ihrer Randlinien, den man in der Ansicht nicht sieht (Bericht Paket B). Seitdem
hat jede neue Flaechen- und Linienlast einen **Bezug**:

* ``global``  - Achse X, Y oder Z des Modells; positiv in Richtung der Achse.
  Vorgabe der Maske: global Z, also wirkt −5 kN/m² nach unten, wenn Z nach
  oben zeigt.
* ``lokal``   - Achse x, y oder z der Flaeche (:func:`seitenachsen`).
* ``ks``      - Achse eines eigenen Koordinatensystems (Model.koordinatensysteme).

Bestehende Lasten tragen keinen Bezug (Feld leer) und wirken wie bisher.

Lokale Flaechenachsen (wie sie gerechnet **und** gezeichnet werden):

* z: bei Schalen die Elementnormale - sie folgt dem Umlauf der Randknoten
  (Rechtsschraube); an der Randflaeche eines Volumens die Aussennormale.
  Zylindrische Achsen einer gewoelbten Flaeche (Flaeche.lokale_achsen =
  "zylinder") bleiben, wie sie sind (:func:`statik3d.model.zylinderachsen_je_seite`).
* x: die globale X-Achse in die Flaechenebene projiziert; steht die Flaeche
  senkrecht zu X (|n·X| > 0,999), die globale Y-Achse projiziert.
* y = z × x (Rechtssystem).
"""
from __future__ import annotations

import math

import numpy as np

#: Achsnamen in der Maske und in der Datei
ACHSEN = ("x", "y", "z")
#: Bezugsarten in der Datei
BEZUEGE = ("global", "lokal", "ks")


def _einheit(v) -> np.ndarray:
    v = np.asarray(v, float)
    L = float(np.linalg.norm(v))
    if L <= 0:
        raise ValueError("Nullvektor")
    return v / L


def achsen_aus_winkeln(winkel) -> np.ndarray:
    """Zeilen ex, ey, ez aus drei Drehwinkeln [Grad]: erst um die globale Z-Achse
    (a), dann um die neue y-Achse (b), dann um die neue x-Achse (c) - die
    Folge Z, y', x'' (Gier, Nick, Roll). R = Rz(a)·Ry(b)·Rx(c); die Spalten von
    R sind die Achsen."""
    a, b, c = (math.radians(float(x)) for x in (list(winkel) + [0.0, 0.0, 0.0])[:3])
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    Rz = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
    Ry = np.array([[cb, 0.0, sb], [0.0, 1.0, 0.0], [-sb, 0.0, cb]])
    Rx = np.array([[1.0, 0.0, 0.0], [0.0, cc, -sc], [0.0, sc, cc]])
    R = Rz @ Ry @ Rx
    return R.T.copy()


def achsen_aus_punkten(ursprung, punkt_x, punkt_xy) -> np.ndarray:
    """Zeilen ex, ey, ez aus drei Punkten: x zeigt vom Ursprung auf ``punkt_x``,
    ``punkt_xy`` liegt in der xy-Ebene auf der Seite von +y. ValueError, wenn
    die Punkte zusammenfallen oder auf einer Geraden liegen."""
    o = np.asarray(ursprung, float)
    try:
        ex = _einheit(np.asarray(punkt_x, float) - o)
    except ValueError:
        raise ValueError("Der Punkt auf der x-Achse fällt mit dem Ursprung zusammen") from None
    v = np.asarray(punkt_xy, float) - o
    ez = np.cross(ex, v)
    if float(np.linalg.norm(ez)) <= 1e-9 * max(1.0, float(np.linalg.norm(v))):
        raise ValueError("Die drei Punkte liegen auf einer Geraden - sie spannen keine Ebene auf")
    ez = _einheit(ez)
    return np.array([ex, np.cross(ez, ex), ez])


def ebenenachsen(z) -> np.ndarray:
    """Zeilen x, y, z der Flaechenachsen zu einer Normalen ``z`` (Regel oben)."""
    z = _einheit(z)
    ref = np.array([1.0, 0.0, 0.0]) if abs(float(z[0])) <= 0.999 else np.array([0.0, 1.0, 0.0])
    x = _einheit(ref - float(ref @ z) * z)
    return np.array([x, np.cross(z, x), z])


def achsindex(achse: str) -> int:
    a = str(achse or "z").strip().lower()
    return {"x": 0, "y": 1, "z": 2}.get(a[:1], 2)


def globale_richtung(model, bezug: str, achse: str, ks: str = ""):
    """Die feste globale Richtung eines Bezugs ``global`` oder ``ks`` - oder
    None (lokal, unbekanntes Koordinatensystem)."""
    i = achsindex(achse)
    if bezug == "global":
        d = np.zeros(3)
        d[i] = 1.0
        return d
    if bezug == "ks":
        k = (getattr(model, "koordinatensysteme", None) or {}).get(str(ks))
        if k is None:
            return None
        return np.asarray(k.achsen()[i], float)
    return None


def _flaeche_ist_rand(model, f) -> bool:
    """Ist die Flaeche Randflaeche eines Volumens (und keine Schale)?"""
    if getattr(f, "randseiten", None):
        return True
    if getattr(f, "elemente", None) or getattr(f, "dicke", ""):
        return False
    return any(f.name in (k.flaechen or []) for k in (getattr(model, "koerper", None) or {}).values())


def seitenachsen(model, flaeche, elem: int, seite: int):
    """(x, y, z) der lokalen Flaechenachsen an einer Elementseite - oder None.

    Schale: z = Elementnormale; Randflaeche eines Volumens: z = Aussennormale
    der Seite. Zylindrische Flaechenachsen gehen vor (siehe Moduldoku)."""
    from .model import zylinderachse, zylinder_plus_x, zylinderachsen_je_seite
    from . import elemente as _EL
    e = model.elements[int(elem)]
    if flaeche is not None and getattr(flaeche, "lokale_achsen", "") == "zylinder":
        achse = zylinderachse(model, flaeche)
        if achse is not None:
            ax = zylinderachsen_je_seite(model._seitenmitte(elem, seite), achse[0],
                                         zylinder_plus_x(model, flaeche, achse[1]))
            if ax is not None:
                return tuple(np.asarray(a, float) for a in ax)
    if e.typ in _EL.SCHALEN_TYPEN:
        n = model._seitennormale_oder_schale(elem, seite)
    else:
        n = model._seitennormale(elem, seite)
    if n is None:
        return None
    A = ebenenachsen(n)
    return A[0], A[1], A[2]


def flaechenachsen_bild(model, flaeche):
    """(Mitte, x, y, z) der lokalen Achsen einer Flaeche fuer die Ansicht - oder None.

    Vernetzt: an der Elementseite, die dem Schwerpunkt am naechsten liegt -
    dieselben Achsen wie in der Rechnung. Ohne Netz: Normale des Randpolygons
    (Umlauf der Randknoten wie beim Vernetzen); an der Randflaeche eines
    Volumens nach aussen gedreht."""
    try:
        P = np.asarray(flaeche.randpunkte(model), float)
    except Exception:                      # noqa: BLE001
        return None
    if len(P) < 3:
        return None
    mitte = P.mean(axis=0)
    seiten = [(int(e), 0) for e in (flaeche.elemente or [])] + \
             [(int(e), int(s)) for e, s in (flaeche.randseiten or [])]
    seiten = [(e, s) for e, s in seiten if 0 <= e < len(model.elements)]
    if seiten:
        if len(seiten) > 400:
            seiten = seiten[:: max(1, len(seiten) // 400)]
        M = np.array([model._seitenmitte(e, s) for e, s in seiten])
        j = int(np.argmin(np.linalg.norm(M - mitte, axis=1)))
        ax = seitenachsen(model, flaeche, *seiten[j])
        if ax is not None:
            return (M[j],) + tuple(ax)
    n = np.zeros(3)
    for j in range(len(P)):
        n += np.cross(P[j], P[(j + 1) % len(P)])
    if float(np.linalg.norm(n)) <= 0:
        return None
    n = n / np.linalg.norm(n)
    if _flaeche_ist_rand(model, flaeche):
        koerper = [k for k in model.koerper.values() if flaeche.name in (k.flaechen or [])]
        if koerper:
            Q = np.concatenate([np.asarray(model.flaechen[x].randpunkte(model), float)
                                for x in koerper[0].flaechen if x in model.flaechen])
            if float(n @ (mitte - Q.mean(axis=0))) < 0:
                n = -n
    A = ebenenachsen(n)
    return mitte, A[0], A[1], A[2]


def bezug_text(bezug: str, achse: str, ks: str = "") -> str:
    """„global Z“, „lokal z“, „KS1 z“ - fuer Maske, Beschriftung und Tabelle."""
    a = str(achse or "z").lower()[:1]
    if bezug == "global":
        return f"global {a.upper()}"
    if bezug == "lokal":
        return f"lokal {a}"
    if bezug == "ks":
        return f"{ks} {a}"
    return ""
