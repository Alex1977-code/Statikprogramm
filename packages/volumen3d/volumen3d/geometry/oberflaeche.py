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
    # Toleranz statt 0: ein Polygon genau in einer Zellflaeche (Symmetrieebene auf Zellgrenze) liegt
    # nach Rundung um ein ulp auf einer Seite und kaeme sonst in einer der beiden Zellen nicht an;
    # _in_fremder_zellflaeche weist es dann der Werkstoffseite zu (Gutachten 27.09.2026)
    tol = 1e-12 * float(np.max(hi - lo))
    for d in range(3):
        for punkt, n in ((lo, -np.eye(3)[d]), (hi, np.eye(3)[d])):
            if len(poly) < 3:
                return np.zeros((0, 3))
            poly, _ = polygon_clippen(poly, punkt, n, tol)
    poly = polygon_bereinigen(poly, 1e-12 * float(np.max(hi - lo)))
    return poly if len(poly) >= 3 else np.zeros((0, 3))


def _in_fremder_zellflaeche(geometrie, poly: np.ndarray, lo, hi) -> bool:
    """Liegt das Polygon in einer Zellflaeche, gehoert es nur der Zelle auf der Werkstoffseite
    (Aussennormale der Geometrie zeigt aus dieser Zelle heraus). Sonst zaehlten beide Nachbarn
    es: Symmetrieebene x = 0 auf Zellflaechen der Ebenen 1 und 2 der verfeinerten Kirsch-Platte,
    Versatz 0,4 -> sym_x 2050 statt 1800 mm2, K_t 3,63 statt 3,08 (27.09.2026)."""
    s = poly.mean(axis=0)
    eps = 1e-9 * float(np.max(hi - lo))
    an_lo = np.abs(s - lo) <= eps
    an_hi = np.abs(s - hi) <= eps
    if not (an_lo.any() or an_hi.any()):
        return False
    n_p = polygon_normale(poly)
    n = geometrie.gradient(s[None])[0]
    for d in range(3):
        if abs(n_p[d]) < 1.0 - 1e-9:
            continue                                        # Polygon nicht in dieser Flaeche
        if an_lo[d] and n[d] >= 0.0:
            return True                                     # Werkstoff jenseits der lo-Flaeche
        if an_hi[d] and n[d] <= 0.0:
            return True
    return False


def _polygon_flaechenvektor(poly: np.ndarray) -> np.ndarray:
    """Summe der Kreuzprodukte des Faechers um poly[0], ein Aufruf statt einem je Dreieck
    (Profil Lame CSG 28.09.2026: 96 640 kleine cross-Aufrufe, 4,3 s von 31 s Aufbau)."""
    if len(poly) < 3:
        return np.zeros(3)
    return np.cross(poly[1:-1] - poly[0], poly[2:] - poly[0]).sum(axis=0)


def polygon_normale(poly: np.ndarray) -> np.ndarray:
    n = _polygon_flaechenvektor(poly)
    l = float(np.sqrt(n @ n))
    return n / l if l > 0 else n


def polygon_flaeche(poly: np.ndarray) -> float:
    n = _polygon_flaechenvektor(poly)
    return 0.5 * float(np.sqrt(n @ n))


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
    # Proben: Ecken und Schwerpunkt auf der Flaeche, dazu Punkte knapp beidseits (delta = 1e-3 r, Ecken
    # dafuer zum Schwerpunkt hin geschrumpft, damit alles in der Kugel bleibt). Nur die Proben abseits
    # der Flaeche entscheiden bei gemischter STL-Lage, ob die Zerlegung stimmt (csg._pruefe_teile
    # laesst |d| <= tol aus; Gutachten 27.09.2026: sonst zaehlte ein Steg auf einem Flansch doppelt).
    n_eigen = form.gradient(c[None])[0]
    delta = 1e-3 * r
    geschrumpft = c + (1.0 - 2e-3) * (poly - c)
    proben = np.concatenate([poly, c[None], c[None] + delta * n_eigen, c[None] - delta * n_eigen,
                             geschrumpft + delta * n_eigen, geschrumpft - delta * n_eigen])
    st = geometrie.lokale_stuecke(c, r, proben)
    # Vierteilung nur, wenn eine *fremde* gekruemmte Form die Kante des Stuecks als Sehne
    # naehert; die eigene Kruemmung erledigen Projektion und Flaechenfaktor exakt. Ist der
    # Kruemmungsradius der fremden Form kleiner als das Polygon, wird bis zur Hoechsttiefe geteilt.
    fremd_gekruemmt = st is not None and any(f2.gekruemmt and f2 is not form for f2 in st[2])
    zu_grob = st is not None and any(f2.gekruemmt and f2 is not form and f2.kruemmungsradius < 5.0 * r for f2 in st[2])
    if st is None or (fremd_gekruemmt and stufe < tiefe) or (zu_grob and stufe < tiefe + 2):
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
    kandidaten = []
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
            kandidaten.append(Q)
    if not kandidaten:
        return []
    # Zeugen aller Stuecke gemeinsam auswerten (ein Aufruf je Funktion statt vier je Stueck):
    # auf der Gesamtoberflaeche (|d| <= tol) UND ein Stueck nach aussen kein Werkstoff. Der zweite
    # Teil faengt beruehrende Vereinigungen (gemeinsame Seite zweier Quader hat d = 0, ist aber
    # innen; Gutachten 27.09.: Flaeche 30 000 statt 25 000 mm2).
    Z = np.array([Q.mean(axis=0) for Q in kandidaten])
    if form.gekruemmt:
        Z = Z - form.abstand(Z)[:, None] * form.gradient(Z)
    n_z = geometrie.gradient(Z)
    eps = max(1e-6 * r, 10.0 * tol_flaeche)
    auf_flaeche = np.abs(geometrie.abstand(Z)) <= tol_flaeche
    aussen_frei = ~geometrie.innen(Z + eps * n_z)
    ok = auf_flaeche & aussen_frei
    statistik["innen_verworfen"] += int((~ok).sum())
    return [Q for Q, o in zip(kandidaten, ok) if o]


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
    polygone: list = field(default_factory=list)          # geclippte Oberflaechenstuecke (k,3), Ecken auf der exakten Flaeche
    polygon_quelle: list = field(default_factory=list)    # Index der Grundform je Polygon

    def auswahl(self, maske) -> "Flaechenquadratur":
        maske = np.asarray(maske, bool)
        return Flaechenquadratur(self.punkte[maske], self.gewichte[maske], self.normalen[maske], self.zelle[maske],
                                 self.xi[maske], self.quelle[maske], self.name[maske], dict(self.statistik),
                                 self.polygone, self.polygon_quelle)

    @staticmethod
    def leer() -> "Flaechenquadratur":
        return Flaechenquadratur(np.zeros((0, 3)), np.zeros(0), np.zeros((0, 3)), np.zeros(0, int),
                                 np.zeros((0, 3)), np.zeros(0, int), np.zeros(0, object),
                                 {"rueckfall": 0, "verworfen": 0, "innen_verworfen": 0})

    def dreiecke(self, geometrie) -> tuple[np.ndarray, np.ndarray]:
        """Oberflaechentriangulierung aus den geclippten Polygonen: Ecken auf der exakten
        Flaeche, Dreiecke nach aussen orientiert, Ecken zusammengefasst. Grundlage fuer
        Vorschau und Auswertepunkte (Gutachten 27.09.: die rohe Tessellierung der Grundformen
        reicht bei schraegen Schnittebenen in den Leerraum)."""
        if not self.polygone:
            return np.zeros((0, 3)), np.zeros((0, 3), int)
        V_l, T_l, n = [], [], 0
        for Q in self.polygone:
            V_l.append(Q)
            T_l.append(np.array([[n, n + i, n + i + 1] for i in range(1, len(Q) - 1)], int).reshape(-1, 3))
            n += len(Q)
        V = np.concatenate(V_l)
        T = np.concatenate(T_l)
        skala = max(float(np.abs(V).max()), 1.0)
        _, idx, inv = np.unique(np.round(V / skala, 9), axis=0, return_index=True, return_inverse=True)
        V = V[idx]
        T = np.asarray(inv).reshape(-1)[T]
        T = T[(T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])]
        if len(T):
            S = V[T].mean(axis=1)
            nrm = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
            umdrehen = np.einsum("ij,ij->i", nrm, geometrie.gradient(S)) < 0
            T[umdrehen] = T[umdrehen][:, [0, 2, 1]]
        return V, T

    @classmethod
    def aus_dreiecken(cls, geometrie, gitter, V, T, quelle, ordnung: int, tiefe: int = 2, formen=None) -> "Flaechenquadratur":
        formen = formen if formen is not None else geometrie.grundformen()
        lo_g, hi_g = geometrie.huellquader()
        tol = 1e-7 * float(np.max(hi_g - lo_g))
        xi2, w2 = dreieck_gauss(ordnung)
        h = gitter.h
        statistik = {"rueckfall": 0, "verworfen": 0, "innen_verworfen": 0}
        P_l, W_l, C_l, Q_l = [], [], [], []
        polygone: list[np.ndarray] = []
        polygon_quelle: list[int] = []
        for t in range(len(T)):
            Vt = V[T[t]]
            f = formen[quelle[t]]
            for c in gitter.blaetter_in_box(Vt.min(axis=0), Vt.max(axis=0)):
                c = int(c)
                lo, hi_c = gitter.zellbox(c)
                poly = dreieck_an_box_clippen(Vt, lo, hi_c)
                if len(poly) < 3 or polygon_flaeche(poly) <= 1e-14 * h * h:
                    continue
                if _in_fremder_zellflaeche(geometrie, poly, lo, hi_c):
                    continue
                for Q in _stuecke_des_polygons(geometrie, f, poly, tiefe, 0, statistik, tol):
                    Qe = Q - f.abstand(Q)[:, None] * f.gradient(Q) if f.gekruemmt else Q   # Ecken auf die exakte Flaeche
                    polygone.append(Qe)
                    polygon_quelle.append(int(quelle[t]))
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
        return cls(P, W, N, C, xi, Qi, namen, statistik, polygone, polygon_quelle)

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
