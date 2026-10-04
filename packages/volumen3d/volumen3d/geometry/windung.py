"""Schnelle Windungszahlen nach Barill, Dickson, Schmidt, Levin, Jacobson 2018 ("Fast Winding Numbers for Soups and Clouds",
ACM TOG 37(4)) auf der vorhandenen Dreieck-BVH (dreiecksbaum.Dreiecksbaum). Plan TP 5 B6 Teil 2, Theorie 11.16.

Die verallgemeinerte Windungszahl eines Punktes q ist das Flaechenintegral des Dipolkerns ueber die Huelle,

    w(q) = int_S f(p) . n(p) dA,   f(p) = (p - q) / (4 pi |p - q|^3).

Fuer einen Baumknoten, dessen Dreiecke weit von q liegen, wird f um den flaechengewichteten Schwerpunkt p~ des Knotens bis zur
zweiten Ordnung entwickelt; die Entwicklung braucht nur die Momente des Knotens

    N      = sum_t a_t n_t                              (0. Ordnung, Gesamtnormale)
    M1[ij] = sum_t n_ti int_T (p - p~)_j dA             (1. Ordnung)
    M2[ijk]= sum_t n_ti int_T (p - p~)_j (p - p~)_k dA  (2. Ordnung)

und die Integrale ueber die Dreiecke sind exakt: int_T (p - c) dA = 0 und int_T (p - c)(p - c)^T dA = (a/12) sum_v (v - c)(v - c)^T
mit dem Schwerpunkt c (anders als bei Barill, die den Schwerpunkt als Punktmasse nehmen; so bleibt nur der Abbruchfehler
der Taylorreihe). Mit r = p~ - q, R = |r| und den Ableitungen des Kerns

    d_j f_i = (delta_ij / R^3 - 3 r_i r_j / R^5) / 4 pi
    d_jk f_i = (-3 (delta_ij r_k + delta_ik r_j + delta_jk r_i) / R^5 + 15 r_i r_j r_k / R^7) / 4 pi

ist der Beitrag des Knotens  f(p~) . N + sum_ij d_j f_i M1[ij] + 1/2 sum_ijk d_jk f_i M2[ijk].  Ein Knoten gilt als fern, wenn
R > beta mal seinem Umkugelradius um p~ (beta = 2, Plan), sonst steigt die Suche ab; Blaetter rechnen exakt (Van Oosterom und
Strackee, stl._raumwinkel_summe). beta: siehe BETA_STANDARD. Die Momente aller Knoten folgen aus Praefixsummen ueber die Dreiecke in Baumordnung (die Dreiecke
eines Knotens liegen dort zusammenhaengend), ohne Rekursion.

Eingesetzt nur fuer die Innen/Aussen-Entscheidung (Stl.innen) ab WINDUNG_BAUM_AB Facetten; Stl.windungszahl und die Facettenpruefung
beim Laden (Defekt) rechnen weiter exakt. Ohne numba gibt es keine BVH und keinen Baum (exakte numpy-Summe wie bisher).
"""
from __future__ import annotations

import math

import numpy as np

try:
    import numba
    _NUMBA = True
except ImportError:                                            # pragma: no cover - CI ohne numba
    numba = None
    _NUMBA = False

# Vorgabe: ab dieser Facettenzahl laeuft die Innen/Aussen-Entscheidung ueber den Baum (Plan TP 5 B6; Messung in Theorie 11.16)
WINDUNG_BAUM_AB = 20_000
# Fernfeldgrenze beta (Abstand zu p~ groesser als beta mal Umkugel). Der Plan nannte beta 2 nach Barill; gemessen an 100 000
# Zufallspunkten um die Tessellierung N 240 (107 636 Dreiecke, 01.10.2026): |dw| max 9,9e-3 (beta 2, 73-mal schneller als die
# exakte Summe), 2,9e-3 (2,5), 1,2e-3 (3), 2,6e-4 (4, 28-mal schneller) - die Planschranke 1e-3 haelt erst mit beta 4;
# die Innen/Aussen-Entscheidung stimmte bei allen beta fuer alle Punkte
BETA_STANDARD = 4.0


class Windungsbaum:
    """Momente je BVH-Knoten; ``windungszahl(P)`` naehert die Windungszahl mit Abbruch nach der zweiten Ordnung."""

    def __init__(self, baum, beta: float = BETA_STANDARD) -> None:
        if not _NUMBA:
            raise RuntimeError("Windungsbaum braucht numba")
        self.baum = baum
        self.beta = float(beta)
        T = baum.T                                             # (m,3,3) in Baumordnung
        m = len(T)
        n_knoten = len(baum.links)
        if m == 0:
            self.pt = np.zeros((0, 3)); self.rad = np.zeros(0); self.N = np.zeros((0, 3))
            self.M1 = np.zeros((0, 3, 3)); self.M2 = np.zeros((0, 3, 3, 3))
            return
        kreuz = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        an = 0.5 * kreuz                                       # a_t n_t (Flaeche mal Einheitsnormale)
        a = np.linalg.norm(an, axis=1)
        c_abs = T.mean(axis=1)
        # exakte zweite Momente des Dreiecks um seinen Schwerpunkt: (a/12) sum_v (v - c)(v - c)^T
        dv = T - c_abs[:, None, :]
        # Schwerpunkte relativ zur Mitte des Huellquaders: in absoluten Koordinaten loeschten sich in A2 - A1 p~ ... die grossen Terme aus
        # (Versatz 1e6 mm: |dw| 3,5e-3 statt 1,8e-4, Gutachten C2, G1-6); die Zentralmomente M1, M2 haengen vom Bezug nicht ab
        s0 = 0.5 * (baum.lo[0] + baum.hi[0])
        c = c_abs - s0
        S = (a / 12.0)[:, None, None] * np.einsum("tvj,tvk->tjk", dv, dv)
        # Praefixsummen der Groessen, aus denen die Knotenmomente um beliebiges p~ folgen:
        #   N = sum a n;  A1[ij] = sum a n_i c_j;  A2[ijk] = sum n_i (a c_j c_k + S_jk);  sum a;  sum a c
        A1 = np.einsum("ti,tj->tij", an, c)
        A2 = np.einsum("ti,tjk->tijk", an, np.einsum("tj,tk->tjk", c, c)) + np.einsum("ti,tjk->tijk", an / np.where(a > 0, a, 1.0)[:, None], S)
        spalten = np.concatenate([a[:, None], a[:, None] * c, an, A1.reshape(m, 9), A2.reshape(m, 27)], axis=1)
        praefix = np.zeros((m + 1, spalten.shape[1]))
        np.cumsum(spalten, axis=0, out=praefix[1:])
        s_, e_ = baum.start, baum.ende
        summe = praefix[e_] - praefix[s_]                      # (n_knoten, 43)
        a_k = summe[:, 0]
        ac_k = summe[:, 1:4]
        N = summe[:, 4:7]
        A1k = summe[:, 7:16].reshape(n_knoten, 3, 3)
        A2k = summe[:, 16:43].reshape(n_knoten, 3, 3, 3)
        mitte_box = 0.5 * (baum.lo + baum.hi) - s0
        pt = np.where((a_k > 0)[:, None], ac_k / np.where(a_k > 0, a_k, 1.0)[:, None], mitte_box)
        # Umkugel um p~ ueber die acht Boxecken (obere Schranke der wahren Umkugel, ohne Durchlauf der Ecken)
        ecken = np.stack([baum.hi[:, d] if (i >> d) & 1 else baum.lo[:, d] for i in range(8) for d in range(3)], axis=1).reshape(n_knoten, 8, 3) - s0
        rad = np.linalg.norm(ecken - pt[:, None, :], axis=2).max(axis=1)
        M1 = A1k - N[:, :, None] * pt[:, None, :]
        M2 = (A2k - A1k[:, :, :, None] * pt[:, None, None, :] - A1k[:, :, None, :] * pt[:, None, :, None]
              + N[:, :, None, None] * pt[:, None, :, None] * pt[:, None, None, :])
        self.pt = np.ascontiguousarray(pt + s0)
        self.rad = np.ascontiguousarray(rad)
        self.N = np.ascontiguousarray(N)
        self.M1 = np.ascontiguousarray(M1)
        self.M2 = np.ascontiguousarray(M2)
        # vorkontrahierte Spuren fuer die zweite Ordnung: v1_j = sum_i M2[i,j,i], v2_i = sum_j M2[i,j,j]
        self.spurM1 = np.ascontiguousarray(np.einsum("kii->k", M1))
        self.v1 = np.ascontiguousarray(np.einsum("kiji->kj", M2))
        self.v2 = np.ascontiguousarray(np.einsum("kijj->ki", M2))

    def windungszahl(self, P: np.ndarray) -> np.ndarray:
        P = np.ascontiguousarray(np.asarray(P, float).reshape(-1, 3))
        b = self.baum
        if len(b.T) == 0 or len(P) == 0:
            return np.zeros(len(P))
        kern = _windung_nb if len(P) >= 256 else _windung_nb_seriell
        return kern(P, b.T, b.links, b.rechts, b.start, b.ende, self.pt, self.rad, self.N, self.M1, self.spurM1, self.M2,
                    self.v1, self.v2, self.beta, 2 * b.tiefe + 4)

    def innen(self, P: np.ndarray) -> np.ndarray:
        return self.windungszahl(P) > 0.5


if _NUMBA:
    from .stl import _raumwinkel_summe

    @numba.njit(cache=True, inline="always")
    def _fernfeld(k, rx, ry, rz, R2, N, M1, spurM1, M2, v1, v2):          # pragma: no cover - numba
        """Beitrag eines fernen Knotens zu 4 pi w (Taylor bis zweiter Ordnung um p~, r = p~ - q)."""
        R = math.sqrt(R2)
        R3 = R2 * R
        R5 = R3 * R2
        R7 = R5 * R2
        s = (rx * N[k, 0] + ry * N[k, 1] + rz * N[k, 2]) / R3
        # erste Ordnung: sum_ij (delta_ij / R^3 - 3 r_i r_j / R^5) M1[ij]
        rMr = (rx * (M1[k, 0, 0] * rx + M1[k, 0, 1] * ry + M1[k, 0, 2] * rz)
               + ry * (M1[k, 1, 0] * rx + M1[k, 1, 1] * ry + M1[k, 1, 2] * rz)
               + rz * (M1[k, 2, 0] * rx + M1[k, 2, 1] * ry + M1[k, 2, 2] * rz))
        s += spurM1[k] / R3 - 3.0 * rMr / R5
        # zweite Ordnung: 1/2 [ -3 (2 r . v1 + r . v2) / R^5 + 15 sum_ijk r_i r_j r_k M2[ijk] / R^7 ]
        rv = 2.0 * (rx * v1[k, 0] + ry * v1[k, 1] + rz * v1[k, 2]) + (rx * v2[k, 0] + ry * v2[k, 1] + rz * v2[k, 2])
        rrr = 0.0
        for i in range(3):
            ri = rx if i == 0 else (ry if i == 1 else rz)
            for j in range(3):
                rj = rx if j == 0 else (ry if j == 1 else rz)
                rrr += ri * rj * (M2[k, i, j, 0] * rx + M2[k, i, j, 1] * ry + M2[k, i, j, 2] * rz)
        s += 0.5 * (-3.0 * rv / R5 + 15.0 * rrr / R7)
        return s

    @numba.njit(cache=True, inline="always")
    def _windung_einzel(px, py, pz, T, links, rechts, start, ende, pt, rad, N, M1, spurM1, M2, v1, v2, beta, stapel):   # pragma: no cover - numba
        sp = 0
        stapel[sp] = 0
        sp += 1
        s = 0.0
        while sp > 0:
            sp -= 1
            k = stapel[sp]
            rx = pt[k, 0] - px
            ry = pt[k, 1] - py
            rz = pt[k, 2] - pz
            R2 = rx * rx + ry * ry + rz * rz
            grenze = beta * rad[k]
            if R2 > grenze * grenze:
                s += _fernfeld(k, rx, ry, rz, R2, N, M1, spurM1, M2, v1, v2)
            elif links[k] < 0:
                s += _raumwinkel_summe(px, py, pz, T[start[k]:ende[k]])
            else:
                stapel[sp] = links[k]
                stapel[sp + 1] = rechts[k]
                sp += 2
        return s / (4.0 * math.pi)

    @numba.njit(parallel=True, cache=True)
    def _windung_nb(P, T, links, rechts, start, ende, pt, rad, N, M1, spurM1, M2, v1, v2, beta, stapelgroesse):   # pragma: no cover - numba
        n = P.shape[0]
        w = np.empty(n)
        for i in numba.prange(n):
            stapel = np.empty(stapelgroesse, np.int64)
            w[i] = _windung_einzel(P[i, 0], P[i, 1], P[i, 2], T, links, rechts, start, ende, pt, rad, N, M1, spurM1, M2, v1, v2, beta, stapel)
        return w

    @numba.njit(cache=True)
    def _windung_nb_seriell(P, T, links, rechts, start, ende, pt, rad, N, M1, spurM1, M2, v1, v2, beta, stapelgroesse):   # pragma: no cover - numba
        n = P.shape[0]
        w = np.empty(n)
        stapel = np.empty(stapelgroesse, np.int64)
        for i in range(n):
            w[i] = _windung_einzel(P[i, 0], P[i, 1], P[i, 2], T, links, rechts, start, ende, pt, rad, N, M1, spurM1, M2, v1, v2, beta, stapel)
        return w


__all__ = ["Windungsbaum", "WINDUNG_BAUM_AB", "BETA_STANDARD"]
