"""Flaechenquadratur auf der echten Oberflaeche je Zelle (Entwurf 3.6).

Ablauf je Dreieck der Tessellierung einer Grundform: Zellen im Huellquader des Dreiecks ->
Clipping an die Zellbox -> lokale Stuecke der Gesamtgeometrie (geometry/csg.py) clippen das
Flaechenpolygon gegen die Halbraeume der **anderen** Formen (die eigene Ebene ist parallel und
wird uebersprungen): ebene Kanten exakt, gekruemmte Nachbarn als Tangentialebene mit
Vierteilung bis ``tiefe`` -> Gauss auf den Faecherdreiecken -> Projektion der Punkte auf die
exakte Grundform-Flaeche -> Normale aus dem Gradienten der Gesamtgeometrie.

Die Flaechengewichte tragen den Tessellierungsfehler (Sehne statt Bogen, zweiter Ordnung in
der Facettenweite); Lage und Normale der Punkte sind exakt. Der Filter |d| <= tol ist nur
ein Sicherheitsnetz fuer den Rueckfall ohne lokale Stuecke; ``verworfen`` zaehlt ihn.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..fcm.basis import gauss_1d
from .polyeder import polygon_clippen


def dreieck_gauss(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Kollabierte Gauss-Jacobi-Regel auf dem Einheitsdreieck (0,0),(1,0),(0,1): (n^2,2),
    Gewichte mit Summe 1/2, exakt bis Gesamtgrad 2n-1."""
    from scipy.special import roots_jacobi
    tu, wu = roots_jacobi(n, 1.0, 0.0)
    tv, wv = gauss_1d(n)
    u, v = 0.5 * (tu + 1), 0.5 * (tv + 1)
    wu, wv = wu / 4.0, wv / 2.0
    U, V = np.meshgrid(u, v, indexing="ij")
    xi = np.stack([U.ravel(), (V * (1 - U)).ravel()], axis=1)
    return xi, (wu[:, None] * wv[None, :]).ravel()


def polygon_bereinigen(poly: np.ndarray, tol: float) -> np.ndarray:
    """Aufeinanderfolgende (fast) gleiche Ecken entfernen (entstehen, wenn eine Polygonecke
    genau auf einer Clip-Ebene liegt)."""
    if len(poly) == 0:
        return poly
    behalten = [0]
    for i in range(1, len(poly)):
        if np.linalg.norm(poly[i] - poly[behalten[-1]]) > tol:
            behalten.append(i)
    if len(behalten) > 1 and np.linalg.norm(poly[behalten[-1]] - poly[behalten[0]]) <= tol:
        behalten.pop()
    return poly[behalten]


def dreieck_an_box_clippen(V: np.ndarray, lo, hi) -> np.ndarray:
    """Dreieck (3,3) gegen die sechs Halbraeume der Box -> Polygon (k,3)."""
    poly = np.asarray(V, float).reshape(-1, 3)
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    for d in range(3):
        for punkt, n in ((lo, -np.eye(3)[d]), (hi, np.eye(3)[d])):
            if len(poly) < 3:
                return np.zeros((0, 3))
            poly, _ = polygon_clippen(poly, punkt, n, 0.0)
    poly = polygon_bereinigen(poly, 1e-12 * float(np.max(hi - lo)))
    return poly if len(poly) >= 3 else np.zeros((0, 3))


def polygon_normale(poly: np.ndarray) -> np.ndarray:
    n = np.zeros(3)
    for i in range(1, len(poly) - 1):
        n += np.cross(poly[i] - poly[0], poly[i + 1] - poly[0])
    l = np.linalg.norm(n)
    return n / l if l > 0 else n


def polygon_flaeche(poly: np.ndarray) -> float:
    return 0.5 * float(np.linalg.norm(sum(np.cross(poly[i] - poly[0], poly[i + 1] - poly[0]) for i in range(1, len(poly) - 1))))


def _zeuge(form, Q: np.ndarray) -> np.ndarray:
    """Schwerpunkt des Polygons, bei gekruemmter Quelle auf deren exakte Flaeche projiziert."""
    c = Q.mean(axis=0)
    if form.gekruemmt:
        c = c - float(form.abstand(c[None])[0]) * form.gradient(c[None])[0]
    return c


def _stuecke_des_polygons(geometrie, form, poly: np.ndarray, tiefe: int, stufe: int, statistik: dict,
                          tol_flaeche: float) -> list[np.ndarray]:
    """Teile des Polygons (Facette der Grundform ``form``), die auf der Oberflaeche der
    Gesamtgeometrie liegen. Jedes Stueck bestaetigt ein Zeugenpunkt (|d_gesamt| <= tol);
    Stuecke im Werkstoffinneren (innere Facetten, Ebenen durch das Innere) fallen so weg,
    bevor Punkte entstehen."""
    c0 = poly.mean(axis=0)
    # Bei gekruemmter Quelle liegt die Sehnenebene um die Sagitta der Facette unter der Flaeche;
    # Bezugspunkt ist darum der auf die Quellflaeche projizierte Schwerpunkt (dort ist d = 0,
    # wenn das Stueck zur Gesamtoberflaeche gehoert), der Radius um den Versatz vergroessert.
    # Befund 27.09.: mit dem Sehnenschwerpunkt fielen kleine Teilpolygone (r < Sagitta) als
    # "innen" weg - Kugeloberflaeche bei Tiefe 2 um 4e-4 zu klein.
    c = _zeuge(form, poly)
    r = float(np.linalg.norm(poly - c0, axis=1).max()) + float(np.linalg.norm(c - c0))
    d = float(geometrie.abstand(c[None])[0])
    if d > r * (1 + 1e-9) or d < -r * (1 + 1e-9):
        return []                                 # ganz ausserhalb oder tief im Werkstoff
    st = geometrie.lokale_stuecke(c, r, np.concatenate([poly, c[None]]))
    # Vierteilung nur, wenn eine *fremde* gekruemmte Form die Kante des Stuecks als Sehne
    # naehert; die eigene Kruemmung erledigen Projektion und Flaechenfaktor exakt
    fremd_gekruemmt = st is not None and any(f2.gekruemmt and f2 is not form for f2 in st[2])
    if st is None or (fremd_gekruemmt and stufe < tiefe):
        if stufe < tiefe + 2:
            aus: list[np.ndarray] = []
            for i in range(1, len(poly) - 1):
                D = np.array([poly[0], poly[i], poly[i + 1]])
                m01, m12, m20 = 0.5 * (D[0] + D[1]), 0.5 * (D[1] + D[2]), 0.5 * (D[2] + D[0])
                for T in (np.array([D[0], m01, m20]), np.array([m01, D[1], m12]), np.array([m20, m12, D[2]]), np.array([m01, m12, m20])):
                    aus += _stuecke_des_polygons(geometrie, form, T, tiefe, stufe + 1, statistik, tol_flaeche)
            return aus
        statistik["rueckfall"] += 1
        return [poly]                             # Rueckfall: Punktfilter entscheidet
    n_poly = polygon_normale(poly)
    # Die eigene Flaeche ist die Tangentialebene der Quellform im projizierten Schwerpunkt c
    # (bei ebenen Formen die Facettenebene selbst). Andere lokale Ebenen der Quellform - etwa
    # die Kappe eines Bohrzylinders - muessen schneiden, sonst liefern zwei Stuecke dasselbe
    # Polygon doppelt (Befund 27.09.: Bohrungsmantel +44 %).
    n_eigen = form.gradient(c[None])[0]
    aus = []
    for halbraeume in st[0]:
        Q = poly
        for p, n in halbraeume:
            if abs(float(n @ n_eigen)) > 0.999 and abs(float((c - p) @ n)) <= 1e-9 * r:
                continue                          # eigene Flaeche (Tangente in c) schneidet nicht
            if abs(float(n @ n_poly)) > 0.999:
                # fremde parallele Ebene behaelt oder entfernt das ganze Polygon (z. B. Kappe eines Bohrzylinders)
                if float((c - p) @ n) > 1e-9 * r:
                    Q = Q[:0]
                    break
                continue
            Q, _ = polygon_clippen(Q, p, n, 1e-12 * r)
            if len(Q) < 3:
                break
        if len(Q) >= 3 and polygon_flaeche(Q) > 1e-14 * r * r:
            if abs(float(geometrie.abstand(_zeuge(form, Q)[None])[0])) <= tol_flaeche:
                aus.append(Q)
            else:
                statistik["innen_verworfen"] += 1
    return aus


@dataclass
class Flaechenquadratur:
    punkte: np.ndarray      # (nq,3)
    gewichte: np.ndarray    # (nq,) Flaeche
    normalen: np.ndarray    # (nq,3) nach aussen
    zelle: np.ndarray       # (nq,) aktive Zelle
    xi: np.ndarray          # (nq,3) lokale Koordinaten
    quelle: np.ndarray      # (nq,) Index der Grundform
    name: np.ndarray        # (nq,) Name der Grundform
    statistik: dict = field(default_factory=dict)

    def auswahl(self, maske) -> "Flaechenquadratur":
        maske = np.asarray(maske, bool)
        return Flaechenquadratur(self.punkte[maske], self.gewichte[maske], self.normalen[maske], self.zelle[maske],
                                 self.xi[maske], self.quelle[maske], self.name[maske], dict(self.statistik))

    @staticmethod
    def leer() -> "Flaechenquadratur":
        return Flaechenquadratur(np.zeros((0, 3)), np.zeros(0), np.zeros((0, 3)), np.zeros(0, int),
                                 np.zeros((0, 3)), np.zeros(0, int), np.zeros(0, object),
                                 {"rueckfall": 0, "verworfen": 0, "innen_verworfen": 0})

    @classmethod
    def aus_dreiecken(cls, geometrie, gitter, V, T, quelle, ordnung: int, tiefe: int = 2, formen=None) -> "Flaechenquadratur":
        formen = formen if formen is not None else geometrie.grundformen()
        lo_g, hi_g = geometrie.huellquader()
        tol = 1e-7 * float(np.max(hi_g - lo_g))
        xi2, w2 = dreieck_gauss(ordnung)
        h = gitter.h
        statistik = {"rueckfall": 0, "verworfen": 0, "innen_verworfen": 0}
        P_l, W_l, C_l, Q_l = [], [], [], []
        for t in range(len(T)):
            Vt = V[T[t]]
            f = formen[quelle[t]]
            i0 = np.maximum(np.floor((Vt.min(axis=0) - gitter.ursprung) / h - 1e-9).astype(int), 0)
            i1 = np.minimum(np.floor((Vt.max(axis=0) - gitter.ursprung) / h + 1e-9).astype(int), gitter.n - 1)
            for i in range(i0[0], i1[0] + 1):
                for j in range(i0[1], i1[1] + 1):
                    for k in range(i0[2], i1[2] + 1):
                        c = gitter._aktiv_index[(i * gitter.n[1] + j) * gitter.n[2] + k]
                        if c < 0:
                            continue
                        lo = gitter.ursprung + np.array([i, j, k]) * h
                        poly = dreieck_an_box_clippen(Vt, lo, lo + h)
                        if len(poly) < 3 or polygon_flaeche(poly) <= 1e-14 * h * h:
                            continue
                        for Q in _stuecke_des_polygons(geometrie, f, poly, tiefe, 0, statistik, tol):
                            B = np.array([[Q[0], Q[m], Q[m + 1]] for m in range(1, len(Q) - 1)])
                            kreuz = np.cross(B[:, 1] - B[:, 0], B[:, 2] - B[:, 0])
                            A = 0.5 * np.linalg.norm(kreuz, axis=1)
                            P = (B[:, None, 0] + xi2[None, :, 0, None] * (B[:, None, 1] - B[:, None, 0])
                                 + xi2[None, :, 1, None] * (B[:, None, 2] - B[:, None, 0])).reshape(-1, 3)
                            W = (A[:, None] * w2[None, :] * 2.0).ravel()
                            if f.gekruemmt:
                                # Flaechenfaktor Bogen/Sehne am Sehnenpunkt, dann Punkt auf die exakte Grundform
                                n_f = np.repeat(kreuz / np.maximum(2.0 * A, 1e-300)[:, None], len(xi2), axis=0)
                                W = W * f.flaechenfaktor(P, n_f)
                                P = P - f.abstand(P)[:, None] * f.gradient(P)
                            P_l.append(P)
                            W_l.append(W)
                            C_l.append(np.full(len(P), c))
                            Q_l.append(np.full(len(P), quelle[t]))
        if not P_l:
            return cls.leer()
        P = np.concatenate(P_l)
        W = np.concatenate(W_l)
        C = np.concatenate(C_l)
        Qi = np.concatenate(Q_l)
        ok = np.abs(geometrie.abstand(P)) <= tol
        statistik["verworfen"] = int((~ok).sum())
        ok &= W > 0.0                                   # entartete Teildreiecke (Nullgewicht) weglassen
        P, W, C, Qi = P[ok], W[ok], C[ok], Qi[ok]
        N = geometrie.gradient(P)
        N /= np.linalg.norm(N, axis=1, keepdims=True)
        xi = np.clip(gitter.lokal(P, C), -1.0, 1.0)
        namen = np.array([formen[q].name for q in Qi], dtype=object)
        return cls(P, W, N, C, xi, Qi, namen, statistik)

    @classmethod
    def aus_geometrie(cls, geometrie, gitter, ordnung: int, facette_mm: float | None = None, tiefe: int = 2) -> "Flaechenquadratur":
        """Facettenweite Standard 0,5 h: Lage und Normale der Punkte sind exakt, die Gewichte
        ueber den Flaechenfaktor der Grundform ebenfalls; nur die Clipping-Kanten an fremden
        gekruemmten Formen sind Sehnen (Vierteilung bis ``tiefe``)."""
        V, T, Q = geometrie.dreiecke(facette_mm or 0.5 * gitter.h)
        return cls.aus_dreiecken(geometrie, gitter, V, T, Q, ordnung, tiefe)

    @classmethod
    def ebene(cls, geometrie, gitter, punkt, normale, ordnung: int, tiefe: int = 2) -> "Flaechenquadratur":
        """Quadratur auf der Geometrieoberflaeche in der Ebene (Schnitt- oder Symmetrieebene, die
        auf einer Grundform-Flaeche liegt)."""
        from .sdf import Halbraum
        hr = Halbraum(punkt, normale)
        lo, hi = geometrie.huellquader()
        V, T = hr.dreiecke(lo - 1e-6 * (hi - lo), hi + 1e-6 * (hi - lo), 0.0)
        return cls.aus_dreiecken(geometrie, gitter, V, T, np.zeros(len(T), int), ordnung, tiefe, formen=[hr])


__all__ = ["dreieck_gauss", "dreieck_an_box_clippen", "polygon_normale", "polygon_flaeche", "Flaechenquadratur"]
