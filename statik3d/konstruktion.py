"""Konstruktionshilfen: Lot und Projektion auf Ebene, Flaeche und Linie.

Wunsch vom 15.09.2026: „im Ribbon Geometrie brauchen wir spezielle
Funktionen wie Lot auf Ebene, projizierter Punkt auf Ebene, Fangfunktionen
Mitte, Lot". Hier steht die Geometrie dazu, ohne Oberflaeche:

* :func:`lot_auf_ebene` - der Fusspunkt des Lots von einem Punkt auf eine
  Ebene (Arbeitsebene oder die Ebene einer ebenen Flaeche); auf dieselbe
  Ebene **projiziert** heisst: der Punkt wird dorthin gesetzt.
* :func:`lot_auf_flaeche` - der naechste Punkt einer Flaeche, auch einer
  gewoelbten (Zylindermantel): Fusspunkt auf den Dreiecken der Flaeche.
* :func:`lot_auf_linie` - der naechste Punkt einer Linie (Bogen, Kreis,
  Spline abgetastet).
* :func:`fusspunkte_auf_strecken` - alle Lotfusspunkte von einem Punkt auf
  ein Feld von Strecken; der Fang „Lot" bietet davon den unter dem Zeiger an.
"""
from __future__ import annotations

import numpy as np


def _v(p) -> np.ndarray:
    return np.asarray(p, float).reshape(3)


# --------------------------------------------------------------------------
# Ebene
# --------------------------------------------------------------------------
def lot_auf_ebene(p, ursprung, normale) -> np.ndarray:
    """Fusspunkt des Lots von ``p`` auf die Ebene durch ``ursprung`` mit ``normale``."""
    n = _v(normale)
    ln = float(np.linalg.norm(n))
    if ln < 1e-14:
        raise ValueError("Die Normale hat die Länge null")
    n = n / ln
    p = _v(p)
    return p - float(n @ (p - _v(ursprung))) * n


def ebene_der_punkte(P) -> tuple:
    """(Schwerpunkt, Normale, groesster Abstand) der Ausgleichsebene durch
    die Punkte - Normale nach Newell (robust fuer Vielecke), der Abstand sagt,
    wie eben die Punkte sind."""
    P = np.asarray(P, float).reshape(-1, 3)
    if len(P) < 3:
        raise ValueError("Für eine Ebene braucht es drei Punkte")
    o = P.mean(axis=0)
    n = np.cross(P, np.roll(P, -1, axis=0)).sum(axis=0)
    ln = float(np.linalg.norm(n))
    if ln < 1e-14:
        # alle Punkte auf einer Geraden: Hauptachsen
        _w, V = np.linalg.eigh((P - o).T @ (P - o))
        n = V[:, 0]
    else:
        n = n / ln
    abstand = float(np.abs((P - o) @ n).max())
    return o, n, abstand


def ebene_der_flaeche(model, f, teilung: int = 16) -> tuple:
    """(Ursprung, Normale) der Ebene einer ebenen Flaeche - None, wenn die
    Flaeche gewoelbt ist (Regelflaeche) oder keinen Rand hat."""
    ring = f.randpunkte(model, teilung)
    if len(ring) < 3:
        return None
    o, n, abstand = ebene_der_punkte(ring)
    gr = float(np.linalg.norm(np.asarray(ring, float).max(axis=0) - np.asarray(ring, float).min(axis=0)))
    if abstand > 1e-6 * max(gr, 1.0):
        return None
    return o, n


# --------------------------------------------------------------------------
# Strecken, Linien
# --------------------------------------------------------------------------
def fusspunkte_auf_strecken(p, A, B) -> tuple:
    """Fusspunkte des Lots von ``p`` auf die Strecken A[i]-B[i]: (Punkte, t).

    ``t`` ist die Lage auf der Strecke (0 = A, 1 = B) **ohne** Klemmen - so
    laesst sich unterscheiden, ob das Lot die Strecke innen trifft (0 < t < 1)
    oder daneben faellt; die Punkte selbst sind auf die Strecke geklemmt.
    """
    A = np.atleast_2d(np.asarray(A, float))
    B = np.atleast_2d(np.asarray(B, float))
    p = _v(p)
    ab = B - A
    L2 = np.einsum("ij,ij->i", ab, ab)
    t = np.zeros(len(A))
    gut = L2 > 1e-24
    t[gut] = np.einsum("ij,ij->i", p - A, ab)[gut] / L2[gut]
    tc = np.clip(t, 0.0, 1.0)
    return A + tc[:, None] * ab, t


def lot_auf_strecken(p, A, B):
    """Der naechste Fusspunkt auf einem Feld von Strecken - oder None."""
    A = np.atleast_2d(np.asarray(A, float))
    if not len(A):
        return None
    F, _t = fusspunkte_auf_strecken(p, A, B)
    d = np.linalg.norm(F - _v(p), axis=1)
    return F[int(np.argmin(d))]


def lot_auf_linie(model, ln, p, teilung: int = 64):
    """Der naechste Punkt einer Linie (krumme Linien abgetastet) - oder None."""
    idx = [int(n) for n in (ln.nodes or []) if 0 <= int(n) < model.nn]
    try:
        X = np.asarray(ln.punkte(model, teilung), float)
    except Exception:                        # noqa: BLE001 - dann die Stuetzknoten
        X = model.nodes[idx] if len(idx) >= 2 else np.zeros((0, 3))
    if len(X) < 2:
        return None
    return lot_auf_strecken(p, X[:-1], X[1:])


# --------------------------------------------------------------------------
# Flaechen
# --------------------------------------------------------------------------
def fusspunkte_auf_dreiecken(q, a, b, c) -> np.ndarray:
    """Fusspunkt von q[i] auf dem Dreieck (a[i], b[i], c[i]) - baryzentrisch,
    ausserhalb auf Kante oder Ecke geklemmt (wie mesher3d.punkt_dreieck_abstand,
    nur dass der Punkt zurueckkommt)."""
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
    # Wer ausserhalb landet, wird auf die naechste Kante geklemmt - dafuer die
    # drei Kanten einzeln pruefen, sonst ist die Ecke nicht immer die naechste
    innen = (v >= 0) & (w >= 0) & (v + w <= 1)
    fuss = a + v[:, None] * ab + w[:, None] * ac
    if not innen.all():
        aussen = ~innen
        beste = None
        bd = None
        for x, y in ((a, b), (b, c), (c, a)):
            F, _t = fusspunkte_auf_strecken_feld(q[aussen], x[aussen], y[aussen])
            d = np.linalg.norm(F - q[aussen], axis=1)
            if beste is None:
                beste, bd = F, d
            else:
                besser = d < bd
                beste[besser] = F[besser]
                bd[besser] = d[besser]
        fuss[aussen] = beste
    return fuss


def fusspunkte_auf_strecken_feld(Q, A, B) -> tuple:
    """Wie :func:`fusspunkte_auf_strecken`, aber je Zeile ein eigener Punkt Q[i]."""
    ab = B - A
    L2 = np.einsum("ij,ij->i", ab, ab)
    t = np.zeros(len(A))
    gut = L2 > 1e-24
    t[gut] = np.einsum("ij,ij->i", Q - A, ab)[gut] / L2[gut]
    tc = np.clip(t, 0.0, 1.0)
    return A + tc[:, None] * ab, t


def lot_auf_flaeche(model, f, p, raender=None, seiten=None, loecher=None):
    """Der naechste Punkt der Flaeche zu ``p`` - der Fusspunkt des Lots.

    Eine ebene Flaeche: das Lot auf ihre Ebene, sofern der Fusspunkt in der
    Flaeche liegt - sonst (und bei gewoelbten Flaechen) der naechste Punkt
    ihrer Dreiecke, dieselben wie im Bild. None ohne Rand.
    """
    from .gui.viewport import flaechenpolygone   # erst hier: zieht pyvista nach
    p = _v(p)
    P, T = [], []
    for Q in flaechenpolygone(model, f, raender, seiten, loecher):
        Q = np.asarray(Q, float)
        if len(Q) < 3:
            continue
        b = len(P)
        P.extend(Q.tolist())
        T.extend([b, b + j, b + j + 1] for j in range(1, len(Q) - 1))
    if not T:
        return None
    P = np.asarray(P, float)
    T = np.asarray(T, int)
    q = np.repeat(p[None, :], len(T), axis=0)
    F = fusspunkte_auf_dreiecken(q, P[T[:, 0]], P[T[:, 1]], P[T[:, 2]])
    d = np.linalg.norm(F - p, axis=1)
    return F[int(np.argmin(d))]
