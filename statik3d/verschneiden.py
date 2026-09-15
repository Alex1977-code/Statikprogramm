"""Schnittlinien zweier Flaechen.

Wunsch vom 15.09.2026: „Verschneiden von Flächen, auch Quadrangle und/oder
Splines". Die Flaechen werden ueber ihre Dreiecke verschnitten - dieselbe
Zerlegung wie im Bild (viewport.flaechenpolygone): eine ebene Flaeche ist ein
Faecher, eine Regelflaeche (Viereck, Zylindermantel) eine Coons-Flaeche aus
Dreiecken, ein Spline-Rand ist abgetastet. So gibt es einen Weg fuer alle
Flaechenarten; die Genauigkeit ist die der Abtastung (16 Abschnitte je
Bogen).

Je Dreieckspaar wird die Schnittstrecke bestimmt (Intervalle beider Dreiecke
auf der Schnittgeraden ihrer Ebenen, Ueberlappung), danach werden die
Strecken zu Polygonzuegen verkettet. Was daraus wird - Knoten und Linien -,
entscheidet die Oberflaeche.
"""
from __future__ import annotations

import numpy as np


def _dreiecke(polys) -> tuple:
    P, T = [], []
    for Q in polys:
        Q = np.asarray(Q, float)
        if len(Q) < 3:
            continue
        b = len(P)
        P.extend(Q.tolist())
        T.extend([b, b + j, b + j + 1] for j in range(1, len(Q) - 1))
    return np.asarray(P, float).reshape(-1, 3), np.asarray(T, int).reshape(-1, 3)


def _intervalle(A, dA, D) -> tuple:
    """Fuer Dreiecke A (n,3,3) mit Abstaenden dA (n,3) zur anderen Ebene: die
    beiden Punkte, in denen die Dreieckskanten die Ebene schneiden, und ihre
    Lage t = D . X auf der Schnittgeraden. Ein Dreieck schneidet die Ebene in
    genau zwei Kantenpunkten, wenn ein Eckpunkt auf der einen und zwei auf der
    anderen Seite liegen (Eckpunkte in der Ebene zaehlen zur Minderheit)."""
    n = len(A)
    X = np.zeros((n, 2, 3))
    for k in range(n):
        d = dA[k]
        a = A[k]
        # der Eckpunkt, der allein auf seiner Seite liegt
        s = np.sign(d)
        s[np.abs(d) < 1e-15] = 0.0
        if (s > 0).sum() == 1:
            i = int(np.flatnonzero(s > 0)[0])
        elif (s < 0).sum() == 1:
            i = int(np.flatnonzero(s < 0)[0])
        else:
            # zwei Ecken in der Ebene (Kante liegt drin) oder alle drei: die
            # Ecke mit dem groessten Abstand als "allein"
            i = int(np.argmax(np.abs(d)))
        j, l = (i + 1) % 3, (i + 2) % 3
        for r, m_ in enumerate((j, l)):
            nen = d[i] - d[m_]
            f = d[i] / nen if abs(nen) > 1e-300 else 0.0
            X[k, r] = a[i] + (a[m_] - a[i]) * f
    t = np.einsum("j,nij->ni", D, X) if D.ndim == 1 else np.einsum("nj,nij->ni", D, X)
    return X, t


def schnittstrecken(P1, T1, P2, T2) -> np.ndarray:
    """Die Schnittstrecken aller Dreieckspaare als Feld (k, 2, 3).

    Vorfilter sind die umschliessenden Quader der Dreiecke; koplanare Paare
    (Flaechen liegen aufeinander) geben keine Linie und werden uebergangen.
    """
    A = P1[T1]
    B = P2[T2]
    if not len(A) or not len(B):
        return np.zeros((0, 2, 3))
    loA, hiA = A.min(axis=1), A.max(axis=1)
    loB, hiB = B.min(axis=1), B.max(axis=1)
    gr = float(max(np.linalg.norm(hiA.max(axis=0) - loA.min(axis=0)),
                   np.linalg.norm(hiB.max(axis=0) - loB.min(axis=0)), 1e-9))
    eps = 1e-9 * gr
    ii, jj = np.nonzero(np.all(hiA[:, None, :] >= loB[None, :, :] - eps, axis=2)
                        & np.all(hiB[None, :, :] >= loA[:, None, :] - eps, axis=2))
    if not len(ii):
        return np.zeros((0, 2, 3))
    a, b = A[ii], B[jj]
    n1 = np.cross(a[:, 1] - a[:, 0], a[:, 2] - a[:, 0])
    n2 = np.cross(b[:, 1] - b[:, 0], b[:, 2] - b[:, 0])
    l1 = np.linalg.norm(n1, axis=1)
    l2 = np.linalg.norm(n2, axis=1)
    gut = (l1 > 1e-300) & (l2 > 1e-300)
    n1[gut] /= l1[gut, None]
    n2[gut] /= l2[gut, None]
    # Abstaende der Ecken von A zur Ebene von B und umgekehrt
    dA = np.einsum("nj,nij->ni", n2, a - b[:, :1])
    dB = np.einsum("nj,nij->ni", n1, b - a[:, :1])
    tolA = 1e-12 * gr
    schneidetA = (dA.max(axis=1) > tolA) & (dA.min(axis=1) < -tolA)
    schneidetB = (dB.max(axis=1) > tolA) & (dB.min(axis=1) < -tolA)
    D = np.cross(n1, n2)
    lD = np.linalg.norm(D, axis=1)
    gut &= schneidetA & schneidetB & (lD > 1e-9)
    if not gut.any():
        return np.zeros((0, 2, 3))
    a, b, dA, dB, D = a[gut], b[gut], dA[gut], dB[gut], D[gut] / lD[gut, None]
    XA, tA = _intervalle(a, dA, D)
    XB, tB = _intervalle(b, dB, D)
    lo = np.maximum(tA.min(axis=1), tB.min(axis=1))
    hi = np.minimum(tA.max(axis=1), tB.max(axis=1))
    ok = hi - lo > 1e-9 * gr
    if not ok.any():
        return np.zeros((0, 2, 3))
    XA, tA, lo, hi = XA[ok], tA[ok], lo[ok], hi[ok]
    # Punkte auf der Schnittgeraden zur Lage t: linear zwischen den beiden
    # Kantenpunkten von A
    o = np.argsort(tA, axis=1)
    t0 = np.take_along_axis(tA, o[:, :1], axis=1)[:, 0]
    t1 = np.take_along_axis(tA, o[:, 1:], axis=1)[:, 0]
    X0 = np.take_along_axis(XA, o[:, :1, None], axis=1)[:, 0]
    X1 = np.take_along_axis(XA, o[:, 1:, None], axis=1)[:, 0]
    dt = np.where(np.abs(t1 - t0) > 1e-300, t1 - t0, 1.0)
    p = X0 + (X1 - X0) * ((lo - t0) / dt)[:, None]
    q = X0 + (X1 - X0) * ((hi - t0) / dt)[:, None]
    return np.stack([p, q], axis=1)


def verketten(strecken, tol: float) -> list:
    """Strecken zu Polygonzuegen verketten: Endpunkte naeher als ``tol`` sind
    derselbe Punkt. Rueckgabe Liste von Punktfeldern (k, 3); geschlossene
    Zuege enden auf ihrem Anfangspunkt."""
    S = np.asarray(strecken, float).reshape(-1, 2, 3)
    if not len(S):
        return []
    # Punkte zusammenfassen
    E = S.reshape(-1, 3)
    from scipy.spatial import cKDTree
    baum = cKDTree(E)
    paare = baum.query_pairs(tol)
    eltern = list(range(len(E)))

    def wurzel(i):
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i
    for i, j in paare:
        ri, rj = wurzel(i), wurzel(j)
        if ri != rj:
            eltern[rj] = ri
    kennung = [wurzel(i) for i in range(len(E))]
    punkte: dict = {}
    for i, k in enumerate(kennung):
        punkte.setdefault(k, []).append(i)
    lage = {k: E[idx].mean(axis=0) for k, idx in punkte.items()}
    kanten = set()
    for s in range(len(S)):
        a, b = kennung[2 * s], kennung[2 * s + 1]
        if a != b:
            kanten.add((min(a, b), max(a, b)))
    nachbarn: dict = {}
    for a, b in kanten:
        nachbarn.setdefault(a, []).append(b)
        nachbarn.setdefault(b, []).append(a)
    offen = set(kanten)
    zuege = []
    # erst an freien Enden beginnen (Grad 1), dann geschlossene Ringe
    starts = sorted([k for k, nb in nachbarn.items() if len(nb) == 1]) \
        + sorted([k for k, nb in nachbarn.items() if len(nb) != 1])
    for start in starts:
        if not any((min(start, nb), max(start, nb)) in offen for nb in nachbarn.get(start, [])):
            continue
        zug = [start]
        k = start
        while True:
            weiter = [nb for nb in nachbarn.get(k, []) if (min(k, nb), max(k, nb)) in offen]
            if not weiter:
                break
            nb = weiter[0]
            offen.discard((min(k, nb), max(k, nb)))
            zug.append(nb)
            k = nb
            if k == start:
                break
        zuege.append(np.asarray([lage[k] for k in zug], float))
    return zuege


def schnittlinien(model, f1, f2, raender=None, seiten=None, loecher=None, tol: float = None) -> list:
    """Die Schnittlinien der Flaechen ``f1`` und ``f2`` als Polygonzuege
    (Punktfelder). Leer, wenn sich die Flaechen nicht schneiden oder nur
    aufeinanderliegen."""
    from .gui.viewport import flaechenpolygone   # erst hier: zieht pyvista nach
    P1, T1 = _dreiecke(flaechenpolygone(model, f1, raender, seiten, loecher))
    P2, T2 = _dreiecke(flaechenpolygone(model, f2, raender, seiten, loecher))
    if not len(T1) or not len(T2):
        return []
    S = schnittstrecken(P1, T1, P2, T2)
    if not len(S):
        return []
    if tol is None:
        gr = float(np.linalg.norm(np.vstack([P1, P2]).max(axis=0) - np.vstack([P1, P2]).min(axis=0)))
        tol = 1e-7 * max(gr, 1.0)
    return verketten(S, tol)


def ausduennen(zug, winkel_grad: float = 0.5) -> np.ndarray:
    """Zwischenpunkte auf einer Geraden weglassen: Punkte, an denen der Zug
    um weniger als ``winkel_grad`` abknickt, tragen nichts bei."""
    Z = np.asarray(zug, float)
    if len(Z) < 3:
        return Z
    behalten = [0]
    for i in range(1, len(Z) - 1):
        a = Z[i] - Z[behalten[-1]]
        b = Z[i + 1] - Z[i]
        la, lb = np.linalg.norm(a), np.linalg.norm(b)
        if la < 1e-300 or lb < 1e-300:
            continue
        c = float(np.clip(a @ b / (la * lb), -1.0, 1.0))
        if np.degrees(np.arccos(c)) > winkel_grad:
            behalten.append(i)
    behalten.append(len(Z) - 1)
    return Z[behalten]
