"""Hierarchie achsparalleler Boxen (BVH) ueber Dreiecke: naechster Punkt und Facetten im Radius,
exakt, mit numba-Kernen (je Punkt ein Stapel).

Warum nicht der k-d-Baum ueber Schwerpunkte mit Kugelschranke (``stl._DreieckIndex``): dessen
Schranke |c_t - P| - R_t <= d* laesst fuer jeden Punkt alle Facetten in einer Schale der Dicke
2 R_max durch. Beim Viertelring (1268 Facetten, fuer den Index in 324 608 Teildreiecke mit
R <= 2,1 mm geteilt) sind das fuer einen Punkt 5 mm vor der Wand rund 1300 Kandidaten, weit
weg noch mehr - der Index war nur 2,2-mal schneller als die volle Suche (10 000 Punkte: 14,9 s
gegen 32,8 s, Maschine belegt, 27.09.2026). Eine BVH schneidet mit dem Boxabstand ganze
Teilbaeume ab und besucht fuer glatte Flaechen nur O(log m) Knoten je Punkt.

Aufbau: Median-Teilung der Schwerpunkte entlang der laengsten Achse, Blaetter mit hoechstens
``blatt`` Dreiecken; die Box eines Knotens umfasst alle Ecken seiner Dreiecke. Ohne numba
faellt ``stl.Stl`` auf den Schwerpunkt-Index zurueck (gleiche Ergebnisse, langsamer).
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


class Dreiecksbaum:
    def __init__(self, D: np.ndarray, blatt: int = 8) -> None:
        D = np.ascontiguousarray(np.asarray(D, float).reshape(-1, 3, 3))
        m = len(D)
        if m == 0:
            self.perm = np.zeros(0, int)
            self.T = D
            self.lo = self.hi = np.zeros((0, 3))
            self.links = self.rechts = self.start = self.ende = np.zeros(0, np.int64)
            self.tiefe = 0
            return
        C = D.mean(axis=1)
        perm = np.arange(m)
        lo, hi, links, rechts, start, ende = [], [], [], [], [], []
        # iterativ: Stapel von (Bereich, Knotennummer); Kinder bekommen ihre Nummern beim Anlegen
        stapel = [(0, m)]
        lo.append(None); hi.append(None); links.append(-1); rechts.append(-1); start.append(0); ende.append(m)
        nummern = [0]
        while stapel:
            s, e = stapel.pop()
            k = nummern.pop()
            V = D[perm[s:e]].reshape(-1, 3)
            lo[k], hi[k] = V.min(axis=0), V.max(axis=0)
            if e - s <= blatt:
                links[k], rechts[k], start[k], ende[k] = -1, -1, s, e
                continue
            Cs = C[perm[s:e]]
            achse = int(np.argmax(np.ptp(Cs, axis=0)))
            mitte = (s + e) // 2
            ordnung = np.argpartition(Cs[:, achse], mitte - s)
            perm[s:e] = perm[s:e][ordnung]
            a, b = len(lo), len(lo) + 1
            for _ in range(2):
                lo.append(None); hi.append(None); links.append(-1); rechts.append(-1); start.append(0); ende.append(0)
            links[k], rechts[k], start[k], ende[k] = a, b, s, e
            stapel.append((s, mitte)); nummern.append(a)
            stapel.append((mitte, e)); nummern.append(b)
        self.perm = perm
        self.T = np.ascontiguousarray(D[perm])
        self.lo = np.ascontiguousarray(np.array(lo, float))
        self.hi = np.ascontiguousarray(np.array(hi, float))
        self.links = np.array(links, np.int64)
        self.rechts = np.array(rechts, np.int64)
        self.start = np.array(start, np.int64)
        self.ende = np.array(ende, np.int64)
        self.tiefe = 0
        if m:
            # Tiefe fuer die Stapelgroesse
            tiefe = np.zeros(len(self.links), np.int64)
            for k in range(len(self.links)):
                if self.links[k] >= 0:
                    tiefe[self.links[k]] = tiefe[self.rechts[k]] = tiefe[k] + 1
            self.tiefe = int(tiefe.max())

    def naechste(self, P: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        P = np.ascontiguousarray(np.asarray(P, float).reshape(-1, 3))
        if len(self.T) == 0:
            return np.full(len(P), np.inf), np.full((len(P), 3), np.nan), np.full(len(P), -1)
        # parallel erst ab einigen hundert Punkten: der Threadstart kostet 0,2 ms je Aufruf, ein
        # einzelner Punkt 2 us (Messung 27.09.2026)
        kern = _naechste_nb if len(P) >= 256 else _naechste_nb_seriell
        d, Q, t = kern(P, self.T, self.lo, self.hi, self.links, self.rechts, self.start, self.ende, 2 * self.tiefe + 4)
        return d, Q, self.perm[t]

    def beruehrende(self, P: np.ndarray, r: float) -> np.ndarray:
        P = np.ascontiguousarray(np.asarray(P, float).reshape(3))
        if len(self.T) == 0:
            return np.zeros(0, int)
        aus = np.empty(len(self.T), np.int64)
        n = _im_radius_nb(P, float(r) * (1 + 1e-9), self.T, self.lo, self.hi, self.links, self.rechts, self.start, self.ende, 2 * self.tiefe + 4, aus)
        return np.sort(self.perm[aus[:n]])

    def in_box(self, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        """Indizes der Dreiecke, deren Huellbox die Box [lo, hi] beruehrt (Obermenge der schneidenden; +-inf erlaubt).
        Fuer die Saeule einer Zelle bei der Huellenintegration (geometry/huelle.py): alle Dreiecke mit x >= x_lo in der
        y-z-Scheibe der Zelle, auch weit entfernte."""
        if len(self.T) == 0:
            return np.zeros(0, int)
        lo = np.ascontiguousarray(np.asarray(lo, float).reshape(3))
        hi = np.ascontiguousarray(np.asarray(hi, float).reshape(3))
        aus = np.empty(len(self.T), np.int64)
        n = _in_box_nb(lo, hi, self.T, self.lo, self.hi, self.links, self.rechts, self.start, self.ende, 2 * self.tiefe + 4, aus)
        return np.sort(self.perm[aus[:n]])


if _NUMBA:
    @numba.njit(cache=True, inline="always")
    def _box_d2(px, py, pz, lo, hi, k):                        # pragma: no cover - numba
        dx = max(lo[k, 0] - px, 0.0, px - hi[k, 0])
        dy = max(lo[k, 1] - py, 0.0, py - hi[k, 1])
        dz = max(lo[k, 2] - pz, 0.0, pz - hi[k, 2])
        return dx * dx + dy * dy + dz * dz

    @numba.njit(cache=True, inline="always")
    def _punkt_dreieck(px, py, pz, T, t):                      # pragma: no cover - numba
        """Ericson 5.1.5 skalar: naechster Punkt (qx,qy,qz) des Dreiecks T[t] zu P."""
        ax, ay, az = T[t, 0, 0], T[t, 0, 1], T[t, 0, 2]
        bx, by, bz = T[t, 1, 0], T[t, 1, 1], T[t, 1, 2]
        cx, cy, cz = T[t, 2, 0], T[t, 2, 1], T[t, 2, 2]
        abx, aby, abz = bx - ax, by - ay, bz - az
        acx, acy, acz = cx - ax, cy - ay, cz - az
        apx, apy, apz = px - ax, py - ay, pz - az
        d1 = abx * apx + aby * apy + abz * apz
        d2 = acx * apx + acy * apy + acz * apz
        if d1 <= 0.0 and d2 <= 0.0:
            return ax, ay, az
        bpx, bpy, bpz = px - bx, py - by, pz - bz
        d3 = abx * bpx + aby * bpy + abz * bpz
        d4 = acx * bpx + acy * bpy + acz * bpz
        if d3 >= 0.0 and d4 <= d3:
            return bx, by, bz
        vc = d1 * d4 - d3 * d2
        if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
            v = d1 / (d1 - d3) if d1 != d3 else 0.0
            return ax + v * abx, ay + v * aby, az + v * abz
        cpx, cpy, cpz = px - cx, py - cy, pz - cz
        d5 = abx * cpx + aby * cpy + abz * cpz
        d6 = acx * cpx + acy * cpy + acz * cpz
        if d6 >= 0.0 and d5 <= d6:
            return cx, cy, cz
        vb = d5 * d2 - d1 * d6
        if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
            w = d2 / (d2 - d6) if d2 != d6 else 0.0
            return ax + w * acx, ay + w * acy, az + w * acz
        va = d3 * d6 - d5 * d4
        if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
            nenner = (d4 - d3) + (d5 - d6)
            w = (d4 - d3) / nenner if nenner != 0.0 else 0.0
            return bx + w * (cx - bx), by + w * (cy - by), bz + w * (cz - bz)
        summe = va + vb + vc
        if summe == 0.0:
            return ax, ay, az
        v = vb / summe
        w = vc / summe
        return ax + abx * v + acx * w, ay + aby * v + acy * w, az + abz * v + acz * w

    @numba.njit(cache=True, inline="always")
    def _naechster_einzel(px, py, pz, T, lo, hi, links, rechts, start, ende, stapel):   # pragma: no cover - numba
        best2 = np.inf
        bqx = bqy = bqz = 0.0
        bt = -1
        sp = 1
        stapel[0] = 0
        while sp > 0:
            sp -= 1
            k = stapel[sp]
            if _box_d2(px, py, pz, lo, hi, k) >= best2:
                continue
            if links[k] < 0:
                for t in range(start[k], ende[k]):
                    qx, qy, qz = _punkt_dreieck(px, py, pz, T, t)
                    d2 = (qx - px) ** 2 + (qy - py) ** 2 + (qz - pz) ** 2
                    if d2 < best2:
                        best2 = d2
                        bqx, bqy, bqz = qx, qy, qz
                        bt = t
            else:
                a = links[k]
                b = rechts[k]
                da = _box_d2(px, py, pz, lo, hi, a)
                db = _box_d2(px, py, pz, lo, hi, b)
                if da < db:                                    # naeheres Kind zuoberst
                    stapel[sp] = b
                    stapel[sp + 1] = a
                else:
                    stapel[sp] = a
                    stapel[sp + 1] = b
                sp += 2
        return math.sqrt(best2), bqx, bqy, bqz, bt

    @numba.njit(parallel=True, cache=True)
    def _naechste_nb(P, T, lo, hi, links, rechts, start, ende, stapelgroesse):     # pragma: no cover - numba
        n = P.shape[0]
        d_aus = np.empty(n)
        q_aus = np.empty((n, 3))
        t_aus = np.empty(n, np.int64)
        for i in numba.prange(n):
            stapel = np.empty(stapelgroesse, np.int64)
            d, qx, qy, qz, t = _naechster_einzel(P[i, 0], P[i, 1], P[i, 2], T, lo, hi, links, rechts, start, ende, stapel)
            d_aus[i] = d
            q_aus[i, 0], q_aus[i, 1], q_aus[i, 2] = qx, qy, qz
            t_aus[i] = t
        return d_aus, q_aus, t_aus

    @numba.njit(cache=True)
    def _naechste_nb_seriell(P, T, lo, hi, links, rechts, start, ende, stapelgroesse):   # pragma: no cover - numba
        n = P.shape[0]
        d_aus = np.empty(n)
        q_aus = np.empty((n, 3))
        t_aus = np.empty(n, np.int64)
        stapel = np.empty(stapelgroesse, np.int64)
        for i in range(n):
            d, qx, qy, qz, t = _naechster_einzel(P[i, 0], P[i, 1], P[i, 2], T, lo, hi, links, rechts, start, ende, stapel)
            d_aus[i] = d
            q_aus[i, 0], q_aus[i, 1], q_aus[i, 2] = qx, qy, qz
            t_aus[i] = t
        return d_aus, q_aus, t_aus

    @numba.njit(cache=True)
    def _im_radius_nb(P, r, T, lo, hi, links, rechts, start, ende, stapelgroesse, aus):   # pragma: no cover - numba
        px, py, pz = P[0], P[1], P[2]
        r2 = r * r
        n = 0
        stapel = np.empty(stapelgroesse, np.int64)
        sp = 1
        stapel[0] = 0
        while sp > 0:
            sp -= 1
            k = stapel[sp]
            if _box_d2(px, py, pz, lo, hi, k) > r2:
                continue
            if links[k] < 0:
                for t in range(start[k], ende[k]):
                    qx, qy, qz = _punkt_dreieck(px, py, pz, T, t)
                    if (qx - px) ** 2 + (qy - py) ** 2 + (qz - pz) ** 2 <= r2:
                        aus[n] = t
                        n += 1
            else:
                stapel[sp] = links[k]
                stapel[sp + 1] = rechts[k]
                sp += 2
        return n

    @numba.njit(cache=True)
    def _in_box_nb(blo, bhi, T, lo, hi, links, rechts, start, ende, stapelgroesse, aus):   # pragma: no cover - numba
        n = 0
        stapel = np.empty(stapelgroesse, np.int64)
        sp = 1
        stapel[0] = 0
        while sp > 0:
            sp -= 1
            k = stapel[sp]
            if hi[k, 0] < blo[0] or lo[k, 0] > bhi[0] or hi[k, 1] < blo[1] or lo[k, 1] > bhi[1] or hi[k, 2] < blo[2] or lo[k, 2] > bhi[2]:
                continue
            if links[k] < 0:
                for t in range(start[k], ende[k]):
                    ok = True
                    for d in range(3):
                        mn = min(T[t, 0, d], T[t, 1, d], T[t, 2, d])
                        mx = max(T[t, 0, d], T[t, 1, d], T[t, 2, d])
                        if mx < blo[d] or mn > bhi[d]:
                            ok = False
                            break
                    if ok:
                        aus[n] = t
                        n += 1
            else:
                stapel[sp] = links[k]
                stapel[sp + 1] = rechts[k]
                sp += 2
        return n


__all__ = ["Dreiecksbaum"]
