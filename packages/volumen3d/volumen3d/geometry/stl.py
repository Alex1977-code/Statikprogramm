"""STL-Eingang als Grundform des CSG-Baums (Vorgabe Abschnitt 3, Entwurf 4b.3).

Vorzeichen des Abstands aus der **verallgemeinerten Windungszahl** (Jacobson, Kavan, Sorkine
2013): w(P) = Summe der Raumwinkel aller Dreiecke / 4 pi, innen fuer w > 1/2. Das ist robust
gegen kleine Luecken und doppelte Facetten, wo ein Strahltest springt. Betrag = Abstand zum
naechsten Dreieck (Punkt-Dreieck exakt, Ericson 2005).

Kosten (Viertelring 1268 Facetten, 10 000 Punkte, Maschine durch Session A belegt, 27.09.2026):
blockweise numpy ueber alle Dreiecke 8,9 s fuer die naechsten Punkte und 6,5 s fuer die
Windungszahl - ein Aufbau fragt Hunderttausende Punkte ab. Darum: naechste Punkte ueber einen
k-d-Baum der Schwerpunkte mit exakter Schranke (Umkugelradius je Facette; das Ergebnis ist
identisch zur vollen Suche) und die Windungszahl als numba-Kern, wenn numba da ist (numpy
sonst; gleiche Formel, gleiche Zahlen bis auf die Summationsreihenfolge). Der schnelle
Windungszahl-Baum (Barill u. a. 2018) fuer Netze mit >10^5 Facetten kommt mit Teilprojekt 5.

Lokal ist ein STL stueckweise eben: fuer eine Teilbox liefern die sie beruehrenden Facetten
die lokalen Ebenen. Liegen alle Facettenecken auf der Werkstoffseite aller dieser Ebenen, ist
die Konfiguration konvex und der Schnitt der Halbraeume exakt; sonst (einspringende Kante)
meldet ``lokal_konvex`` False, und die Quadratur teilt weiter bzw. faellt auf den Punkttest mit
Windungszahl zurueck. Die Facettennormalen werden beim Laden ueber die Windungszahl nach
aussen orientiert (STL-Dateien halten die Regel nicht immer ein).
"""
from __future__ import annotations

import math
import os
import struct
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

try:
    import numba
    _NUMBA = True
except ImportError:                                            # CI: nur numpy/scipy
    numba = None
    _NUMBA = False


def lies_stl(pfad: str) -> tuple[np.ndarray, np.ndarray]:
    """Dreiecke (m,3,3) und Dateinormalen (m,3) aus binaerem oder ASCII-STL."""
    with open(pfad, "rb") as f:
        kopf = f.read(84)
    binaer = len(kopf) >= 84
    if binaer:
        (m,) = struct.unpack("<I", kopf[80:84])
        binaer = os.path.getsize(pfad) == 84 + 50 * m
    if binaer:
        daten = np.fromfile(pfad, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=m, offset=84)
        return daten["v"].astype(float), daten["n"].astype(float)
    ecken: list[list[float]] = []
    normalen: list[list[float]] = []
    with open(pfad, encoding="utf-8", errors="replace") as f:
        for zeile in f:
            t = zeile.split()
            if not t:
                continue
            if t[0] == "vertex":
                ecken.append([float(t[1]), float(t[2]), float(t[3])])
            elif t[0] == "facet" and len(t) >= 5:
                normalen.append([float(t[2]), float(t[3]), float(t[4])])
    V = np.asarray(ecken, float).reshape(-1, 3, 3)
    N = np.asarray(normalen, float).reshape(-1, 3) if len(normalen) == len(V) else np.zeros((len(V), 3))
    return V, N


def schreibe_stl(pfad: str, dreiecke: np.ndarray) -> None:
    """Binaeres STL (fuer Pruefungen)."""
    D = np.asarray(dreiecke, float).reshape(-1, 3, 3)
    n = np.cross(D[:, 1] - D[:, 0], D[:, 2] - D[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-300)
    daten = np.zeros(len(D), dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    daten["n"] = n
    daten["v"] = D
    with open(pfad, "wb") as f:
        f.write(b"volumen3d".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(D)))
        f.write(daten.tobytes())


# -- Windungszahl ----------------------------------------------------------------------
def _windungszahl_np(P: np.ndarray, D: np.ndarray, block: int = 512) -> np.ndarray:
    """Raumwinkel nach Van Oosterom und Strackee, blockweise ueber die Dreiecke (numpy)."""
    w = np.zeros(len(P))
    for s in range(0, len(D), block):
        T = D[s:s + block]
        a = T[None, :, 0, :] - P[:, None, :]
        b = T[None, :, 1, :] - P[:, None, :]
        c = T[None, :, 2, :] - P[:, None, :]
        la = np.linalg.norm(a, axis=2)
        lb = np.linalg.norm(b, axis=2)
        lc = np.linalg.norm(c, axis=2)
        num = np.einsum("nmi,nmi->nm", a, np.cross(b, c))
        num = np.where(num == 0.0, 0.0, num)                   # -0.0 -> +0.0: Punkt in der Facettenebene eindeutig
        den = la * lb * lc + np.einsum("nmi,nmi->nm", a, b) * lc + np.einsum("nmi,nmi->nm", b, c) * la + np.einsum("nmi,nmi->nm", c, a) * lb
        w += (2.0 * np.arctan2(num, den)).sum(axis=1)
    return w / (4.0 * np.pi)


if _NUMBA:
    @numba.njit(cache=True, inline="always")
    def _raumwinkel_summe(px, py, pz, D):                                  # pragma: no cover - numba
        s = 0.0
        for t in range(D.shape[0]):
            ax, ay, az = D[t, 0, 0] - px, D[t, 0, 1] - py, D[t, 0, 2] - pz
            bx, by, bz = D[t, 1, 0] - px, D[t, 1, 1] - py, D[t, 1, 2] - pz
            cx, cy, cz = D[t, 2, 0] - px, D[t, 2, 1] - py, D[t, 2, 2] - pz
            la = math.sqrt(ax * ax + ay * ay + az * az)
            lb = math.sqrt(bx * bx + by * by + bz * bz)
            lc = math.sqrt(cx * cx + cy * cy + cz * cz)
            num = ax * (by * cz - bz * cy) + ay * (bz * cx - bx * cz) + az * (bx * cy - by * cx)
            if num == 0.0:
                num = 0.0                                      # -0.0 -> +0.0 wie in der numpy-Fassung
            den = (la * lb * lc + (ax * bx + ay * by + az * bz) * lc + (bx * cx + by * cy + bz * cz) * la
                   + (cx * ax + cy * ay + cz * az) * lb)
            s += 2.0 * math.atan2(num, den)
        return s

    @numba.njit(parallel=True, cache=True)
    def _windungszahl_nb(P: np.ndarray, D: np.ndarray) -> np.ndarray:      # pragma: no cover - numba
        n = P.shape[0]
        w = np.zeros(n)
        for i in numba.prange(n):
            w[i] = _raumwinkel_summe(P[i, 0], P[i, 1], P[i, 2], D)
        return w / (4.0 * np.pi)

    @numba.njit(cache=True)
    def _windungszahl_nb_seriell(P: np.ndarray, D: np.ndarray) -> np.ndarray:   # pragma: no cover - numba
        n = P.shape[0]
        w = np.zeros(n)
        for i in range(n):
            w[i] = _raumwinkel_summe(P[i, 0], P[i, 1], P[i, 2], D)
        return w / (4.0 * np.pi)


def windungszahl(P: np.ndarray, D: np.ndarray, block: int = 512) -> np.ndarray:
    """Verallgemeinerte Windungszahl der Punkte P (n,3) bezueglich der Dreiecke D (m,3,3)."""
    P = np.ascontiguousarray(np.asarray(P, float).reshape(-1, 3))
    D = np.ascontiguousarray(np.asarray(D, float).reshape(-1, 3, 3))
    if len(P) == 0 or len(D) == 0:
        return np.zeros(len(P))
    if _NUMBA:
        # parallel erst ab einigen hundert Punkten (Threadstart ~0,2 ms je Aufruf; die Quadratur
        # fragt je Teilbox nur eine Handvoll Proben ab)
        return _windungszahl_nb(P, D) if len(P) * len(D) >= 200_000 else _windungszahl_nb_seriell(P, D)
    return _windungszahl_np(P, D, block)


# -- naechste Punkte -------------------------------------------------------------------
def _naechster_punkt_paare(P: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Naechster Punkt auf dem Dreieck T[k] zum Punkt P[k] (Ericson, Real-Time Collision
    Detection 5.1.5), elementweise ueber Paare (k,3) / (k,3,3)."""
    a, b, c = T[:, 0, :], T[:, 1, :], T[:, 2, :]
    ab, ac, ap = b - a, c - a, P - a
    d1 = np.einsum("ki,ki->k", ab, ap)
    d2 = np.einsum("ki,ki->k", ac, ap)
    bp = P - b
    d3 = np.einsum("ki,ki->k", ab, bp)
    d4 = np.einsum("ki,ki->k", ac, bp)
    cp = P - c
    d5 = np.einsum("ki,ki->k", ab, cp)
    d6 = np.einsum("ki,ki->k", ac, cp)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    summe = va + vb + vc
    summe = np.where(np.abs(summe) < 1e-300, 1e-300, summe)
    v = vb / summe
    w = vc / summe
    Q = a + v[:, None] * ab + w[:, None] * ac                     # Inneres
    Q = np.where(((d1 <= 0) & (d2 <= 0))[:, None], a, Q)          # Ecken
    Q = np.where(((d3 >= 0) & (d4 <= d3))[:, None], b, Q)
    Q = np.where(((d6 >= 0) & (d5 <= d6))[:, None], c, Q)
    m_ab = (vc <= 0) & (d1 >= 0) & (d3 <= 0)                      # Kanten
    t_ab = d1 / np.where(np.abs(d1 - d3) < 1e-300, 1e-300, d1 - d3)
    Q = np.where(m_ab[:, None], a + t_ab[:, None] * ab, Q)
    m_ac = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t_ac = d2 / np.where(np.abs(d2 - d6) < 1e-300, 1e-300, d2 - d6)
    Q = np.where(m_ac[:, None], a + t_ac[:, None] * ac, Q)
    m_bc = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    t_bc = (d4 - d3) / np.where(np.abs((d4 - d3) + (d5 - d6)) < 1e-300, 1e-300, (d4 - d3) + (d5 - d6))
    Q = np.where(m_bc[:, None], b + t_bc[:, None] * (c - b), Q)
    return Q


def _naechster_punkt_dreieck(P: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Naechste Punkte (n,m,3) aller Punkte P (n,3) auf allen Dreiecken T (m,3,3)."""
    n, m = len(P), len(T)
    Pp = np.broadcast_to(P[:, None, :], (n, m, 3)).reshape(-1, 3)
    Tp = np.broadcast_to(T[None, :, :, :], (n, m, 3, 3)).reshape(-1, 3, 3)
    return _naechster_punkt_paare(Pp, Tp).reshape(n, m, 3)


def naechste_punkte(P: np.ndarray, D: np.ndarray, block: int = 256) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Naechster Punkt auf den Dreiecken je Punkt, volle Suche (Referenz fuer den Index):
    (Abstand (n,), Punkt (n,3), Dreiecksindex (n,))."""
    P = np.asarray(P, float).reshape(-1, 3)
    best_d = np.full(len(P), np.inf)
    best_q = np.zeros((len(P), 3))
    best_t = np.zeros(len(P), int)
    for s in range(0, len(D), block):
        T = D[s:s + block]
        Q = _naechster_punkt_dreieck(P, T)
        d = np.linalg.norm(Q - P[:, None, :], axis=2)
        j = d.argmin(axis=1)
        dm = d[np.arange(len(P)), j]
        besser = dm < best_d
        best_d[besser] = dm[besser]
        best_q[besser] = Q[np.flatnonzero(besser), j[besser]]
        best_t[besser] = s + j[besser]
    return best_d, best_q, best_t


def _konsistent_orientieren(D: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Facetten einheitlich wickeln und nach aussen richten.

    Eine einzeln verkehrt gewickelte Facette ist mit der Windungszahl an ihrer eigenen Probe
    nicht zu erkennen (ihr eigener Raumwinkel +-1/2 ueberdeckt den Rest, Gutachten 27.09.2026),
    dreht aber innen/aussen in ihrer Umgebung um. Darum: (1) ueber gemeinsame Kanten wickeln
    (Nachbarn durchlaufen die Kante entgegengesetzt; Breitensuche je Zusammenhangskomponente,
    Kanten mit mehr als zwei Facetten tragen nicht), (2) jede Komponente ueber ihr
    Vorzeichenvolumen nach aussen, (3) Komponenten in ungerader Verschachtelungstiefe
    (Hohlraeume: Windungszahl der uebrigen, nach aussen gerichteten Komponenten an einer
    ihrer Facetten) nach innen. Rueckgabe: D, Zahl gewendeter Facetten, Zahl nicht
    mannigfaltiger Kanten."""
    m = len(D)
    if m == 0:
        return D, 0, 0
    V = D.reshape(-1, 3)
    skala = max(float(np.ptp(V, axis=0).max()), 1e-300) * 1e-9
    _, ids = np.unique(np.round(V / skala).astype(np.int64), axis=0, return_inverse=True)
    ids = ids.reshape(m, 3)
    a = ids
    b = np.roll(ids, -1, axis=1)
    richtung = np.where(a < b, 1, -1).ravel()
    schluessel = (np.minimum(a, b).astype(np.int64) * (int(ids.max()) + 1) + np.maximum(a, b)).ravel()
    facette = np.repeat(np.arange(m), 3)
    ordnung = np.argsort(schluessel, kind="stable")
    s_sort, f_sort, r_sort = schluessel[ordnung], facette[ordnung], richtung[ordnung]
    grenzen = np.flatnonzero(np.diff(s_sort)) + 1
    starts = np.concatenate([[0], grenzen])
    enden = np.concatenate([grenzen, [len(s_sort)]])
    zwei = (enden - starts) == 2
    nichtmannig = int(((enden - starts) > 2).sum())
    f1, f2 = f_sort[starts[zwei]], f_sort[starts[zwei] + 1]
    verh = -(r_sort[starts[zwei]] * r_sort[starts[zwei] + 1])      # +1: gleiches Vorzeichen, -1: Nachbar wenden
    von = np.concatenate([f1, f2])
    nach = np.concatenate([f2, f1])
    vv = np.concatenate([verh, verh])
    o = np.argsort(von, kind="stable")
    nach, vv = nach[o], vv[o]
    zeiger = np.searchsorted(von[o], np.arange(m + 1))
    vz = np.zeros(m, int)
    komp = np.full(m, -1, int)
    k = 0
    for start in range(m):
        if vz[start] != 0:
            continue
        vz[start], komp[start] = 1, k
        stapel = [start]
        while stapel:
            f = stapel.pop()
            for j in range(zeiger[f], zeiger[f + 1]):
                g = nach[j]
                if vz[g] == 0:
                    vz[g], komp[g] = vz[f] * vv[j], k
                    stapel.append(g)
        k += 1
    D2 = D.copy()
    flip = vz < 0
    D2[flip] = D2[flip][:, [0, 2, 1], :]
    vol = np.einsum("ij,ij->i", D2[:, 0], np.cross(D2[:, 1], D2[:, 2])) / 6.0
    for kk in range(k):
        maske = komp == kk
        if vol[maske].sum() < 0:
            D2[maske] = D2[maske][:, [0, 2, 1], :]
            flip[maske] = ~flip[maske]
    if k > 1:
        # Verschachtelungstiefe mit allen Komponenten nach aussen gerichtet, erst danach wenden
        tiefe = np.zeros(k, int)
        for kk in range(k):
            maske = komp == kk
            s = D2[maske][0].mean(axis=0)
            tiefe[kk] = int(round(float(windungszahl(s[None], D2[~maske])[0])))
        for kk in range(k):
            if tiefe[kk] % 2 == 1:
                maske = komp == kk
                D2[maske] = D2[maske][:, [0, 2, 1], :]
                flip[maske] = ~flip[maske]
    return np.ascontiguousarray(D2), int(flip.sum()), nichtmannig


class _DreieckIndex:
    """k-d-Baum ueber die Schwerpunkte der Facetten mit Umkugelradius je Facette.

    Exakt: liegt das naechste Dreieck t* nicht unter den k naechsten Schwerpunkten, gilt
    |c_t* - P| - R_t* <= d* <= d0 (d0 = bestes der k), also |c_t* - P| <= d0 + R_max - es liegt
    in der Kugel, die nachgeladen wird; je Kandidat wird zusaetzlich |c_t - P| - R_t < d0 verlangt.
    Grosse Facetten machen die Schranke stumpf (Viertelring: Kappenfacetten R 25 mm, Waende
    10 mm -> Index nur 2x schneller als die volle Suche). Darum werden Facetten mit R ueber
    ``r_ziel`` (1 % der Huellquader-Diagonale) fuer den Index geviertelt - der Abstand zur
    Vereinigung der Kinder ist der Abstand zur Facette, das Ergebnis bleibt exakt und nennt die
    Elternfacette."""

    def __init__(self, D: np.ndarray, r_ziel: float | None = None, max_teile: int = 400_000) -> None:
        self.D = D
        m = len(D)
        if m == 0:
            self.T, self.eltern = D, np.zeros(0, int)
            self.C, self.R, self.R_max = np.zeros((0, 3)), np.zeros(0), 0.0
            self.baum = None
            return
        diag = float(np.linalg.norm(np.ptp(D.reshape(-1, 3), axis=0)))
        r_ziel = r_ziel if r_ziel is not None else 0.01 * diag
        T, eltern = D, np.arange(m)
        R = np.linalg.norm(T - T.mean(axis=1)[:, None, :], axis=2).max(axis=1)
        while True:
            gross = R > r_ziel
            if not gross.any() or len(T) + 3 * int(gross.sum()) > max_teile:
                break
            G = T[gross]
            a, b, c = G[:, 0], G[:, 1], G[:, 2]
            ab, bc, ca = 0.5 * (a + b), 0.5 * (b + c), 0.5 * (c + a)
            kinder = np.concatenate([np.stack([a, ab, ca], axis=1), np.stack([ab, b, bc], axis=1),
                                     np.stack([ca, bc, c], axis=1), np.stack([ab, bc, ca], axis=1)])
            T = np.concatenate([T[~gross], kinder])
            eltern = np.concatenate([eltern[~gross], np.tile(eltern[gross], 4)])
            R = np.linalg.norm(T - T.mean(axis=1)[:, None, :], axis=2).max(axis=1)
        self.T = np.ascontiguousarray(T)
        self.eltern = eltern
        self.C = self.T.mean(axis=1)
        self.R = R
        self.R_max = float(R.max())
        self.baum = cKDTree(self.C)

    def naechste(self, P: np.ndarray, k: int = 8, block: int = 20_000) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        P = np.asarray(P, float).reshape(-1, 3)
        n, m = len(P), len(self.T)
        d_aus, q_aus, t_aus = np.empty(n), np.empty((n, 3)), np.empty(n, int)
        if m == 0:
            return np.full(n, np.inf), np.full((n, 3), np.nan), np.full(n, -1)
        k = min(k, m)
        for s in range(0, n, block):
            Pc = P[s:s + block]
            nc = len(Pc)
            dk, ik = self.baum.query(Pc, k)
            if dk.ndim == 1:
                dk, ik = dk[:, None], ik[:, None]
            ip = np.repeat(np.arange(nc), k)
            it = ik.ravel()
            Q = _naechster_punkt_paare(Pc[ip], self.T[it])
            d = np.linalg.norm(Q - Pc[ip], axis=1).reshape(nc, k)
            j = d.argmin(axis=1)
            zeilen = np.arange(nc)
            d0 = d[zeilen, j]
            q0 = Q.reshape(nc, k, 3)[zeilen, j]
            t0 = ik[zeilen, j]
            radius = d0 + self.R_max
            offen = np.flatnonzero(radius > dk[:, -1])
            if len(offen):
                listen = self.baum.query_ball_point(Pc[offen], radius[offen])
                laengen = np.fromiter((len(l) for l in listen), int, len(listen))
                if laengen.sum():
                    ip2 = np.repeat(offen, laengen)
                    it2 = np.concatenate([np.asarray(l, int) for l in listen if len(l)])
                    ok = np.linalg.norm(self.C[it2] - Pc[ip2], axis=1) - self.R[it2] < d0[ip2]
                    ip2, it2 = ip2[ok], it2[ok]
                    if len(ip2):
                        Q2 = _naechster_punkt_paare(Pc[ip2], self.T[it2])
                        d2 = np.linalg.norm(Q2 - Pc[ip2], axis=1)
                        reihen = np.lexsort((d2, ip2))                # je Punkt der kleinste zuerst
                        erste = np.ones(len(reihen), bool)
                        erste[1:] = ip2[reihen][1:] != ip2[reihen][:-1]
                        sel = reihen[erste]
                        besser = d2[sel] < d0[ip2[sel]]
                        sel = sel[besser]
                        d0[ip2[sel]] = d2[sel]
                        q0[ip2[sel]] = Q2[sel]
                        t0[ip2[sel]] = it2[sel]
            d_aus[s:s + block], q_aus[s:s + block], t_aus[s:s + block] = d0, q0, self.eltern[t0]
        return d_aus, q_aus, t_aus

    def in_box(self, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        """Facetten, deren Huellbox die Box [lo, hi] beruehrt (ohne Baum: alle pruefen)."""
        lo = np.asarray(lo, float).reshape(3)
        hi = np.asarray(hi, float).reshape(3)
        mn, mx = self.D.min(axis=1), self.D.max(axis=1)
        return np.flatnonzero(np.all((mx >= lo) & (mn <= hi), axis=1))

    def beruehrende(self, P: np.ndarray, r: float) -> np.ndarray:
        """Indizes der Facetten mit Abstand <= r (1 + 1e-9) zum Punkt P, aufsteigend."""
        P = np.asarray(P, float).reshape(3)
        if self.baum is None:
            return np.zeros(0, int)
        kand = np.asarray(self.baum.query_ball_point(P, r + self.R_max), int)
        if len(kand) == 0:
            return kand
        kand = kand[np.linalg.norm(self.C[kand] - P, axis=1) - self.R[kand] <= r * (1 + 1e-9)]
        if len(kand) == 0:
            return kand
        Q = _naechster_punkt_paare(np.broadcast_to(P, (len(kand), 3)), self.T[kand])
        dist = np.linalg.norm(Q - P, axis=1)
        return np.unique(self.eltern[kand[dist <= r * (1 + 1e-9)]])


@dataclass(frozen=True)
class Stl:
    dreiecke_ecken: np.ndarray          # (m,3,3)
    normalen: np.ndarray                # (m,3), nach aussen
    name: str = "stl"
    defekt: float = 0.0                 # groesste Abweichung der Windungszahl von 0/1 an der Stichprobe
    umgedreht: int = 0                  # beim Laden gewendete Facetten (verkehrte Wicklung, Hohlraeume)
    nicht_mannigfaltig: int = 0         # Kanten mit mehr als zwei Facetten (innere Doppelflaechen)
    _index: Any = field(default=None, repr=False, compare=False)
    _windung: Any = field(default=None, repr=False, compare=False)     # Windungsbaum (windung.py), erst beim ersten innen()
    gekruemmt = False
    kruemmungsradius = np.inf

    def __post_init__(self) -> None:
        if self._index is None:
            D = np.ascontiguousarray(self.dreiecke_ecken, dtype=float)
            if _NUMBA:
                from .dreiecksbaum import Dreiecksbaum
                object.__setattr__(self, "_index", Dreiecksbaum(D))
            else:
                object.__setattr__(self, "_index", _DreieckIndex(D))

    @classmethod
    def aus_dreiecken(cls, D: np.ndarray, name: str = "stl") -> "Stl":
        D = np.asarray(D, float).reshape(-1, 3, 3)
        n = np.cross(D[:, 1] - D[:, 0], D[:, 2] - D[:, 0])
        flaeche = np.linalg.norm(n, axis=1)
        ok = flaeche > 1e-14 * max(float(np.abs(D).max()), 1.0) ** 2
        D = D[ok]
        # einheitlich wickeln (Kantennachbarn), Komponenten nach aussen, Hohlraeume nach innen
        D, umgedreht, nichtmannig = _konsistent_orientieren(D)
        n = np.cross(D[:, 1] - D[:, 0], D[:, 2] - D[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        # Sicherung ueber die Windungszahl: innen ist |w| ~ 1, aussen ~ 0 - unabhaengig vom
        # Vorzeichen, das mit der Facettenorientierung wechselt (falsch herum: innen w = -1)
        probe = np.arange(0, len(D), max(1, len(D) // 64))
        s = D[probe].mean(axis=1)
        eps = 1e-4 * float(np.ptp(D.reshape(-1, 3), axis=0).max())
        w_plus = windungszahl(s + eps * n[probe], D)
        w_minus = windungszahl(s - eps * n[probe], D)
        if np.mean(np.abs(w_plus) > np.abs(w_minus)) > 0.5:
            n = -n
            D = np.ascontiguousarray(D[:, [0, 2, 1], :])
            w_plus, w_minus = -w_minus, -w_plus
        # Defekt: groesste Abweichung der Windungszahl von 0/1 beidseits der Facetten - 0 bei einer
        # geschlossenen, einheitlich orientierten Huelle; Luecken und gekippte Facetten heben ihn
        w = np.concatenate([w_plus, w_minus])
        defekt = float(np.abs(w - np.round(w)).max()) if len(w) else 0.0
        return cls(D, n, name, defekt=defekt, umgedreht=umgedreht, nicht_mannigfaltig=nichtmannig)

    @classmethod
    def aus_datei(cls, pfad: str, name: str | None = None) -> "Stl":
        D, _ = lies_stl(pfad)
        if len(D) == 0:
            raise ValueError(f"STL {pfad!r} enthaelt keine Dreiecke")
        return cls.aus_dreiecken(D, name or os.path.splitext(os.path.basename(pfad))[0])

    # -- Abfrageschnittstelle ------------------------------------------------------------
    def windungszahl(self, P) -> np.ndarray:
        return windungszahl(P, self.dreiecke_ecken)

    def innen(self, P) -> np.ndarray:
        """Innen/Aussen-Entscheidung; ab WINDUNG_BAUM_AB Facetten ueber den Windungszahl-Baum (Barill 2018, windung.py:
        Block mit Bohrung N 240 28-mal schneller, gleiche Entscheidung an 100 000 Punkten), sonst exakt."""
        P = np.ascontiguousarray(np.asarray(P, float).reshape(-1, 3))
        if self._windung is None and _NUMBA and hasattr(self._index, "links"):
            from .windung import WINDUNG_BAUM_AB, Windungsbaum        # hier, nicht oben: windung braucht den numba-Kern von stl
            if len(self.dreiecke_ecken) >= WINDUNG_BAUM_AB:
                object.__setattr__(self, "_windung", Windungsbaum(self._index))
        if self._windung is not None:
            return self._windung.innen(P)
        return self.windungszahl(P) > 0.5

    def naechste_punkte(self, P) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(Abstand, naechster Punkt, Facette) ueber den Index - identisch zur vollen Suche."""
        return self._index.naechste(P)

    def abstand(self, P) -> np.ndarray:
        P = np.asarray(P, float).reshape(-1, 3)
        d, _, _ = self._index.naechste(P)
        return np.where(self.innen(P), -d, d)

    def gradient(self, P) -> np.ndarray:
        """Nach aussen: von innen zur Flaeche hin, von aussen von ihr weg; auf der Flaeche die
        Facettennormale."""
        P = np.asarray(P, float).reshape(-1, 3)
        d, Q, t = self._index.naechste(P)
        g = np.where(self.innen(P)[:, None], Q - P, P - Q)
        l = np.linalg.norm(g, axis=1)
        nah = l <= 1e-9 * max(float(np.abs(self.dreiecke_ecken).max()), 1.0)
        g[~nah] /= l[~nah, None]
        g[nah] = self.normalen[t[nah]]
        return g

    def huellquader(self) -> tuple[np.ndarray, np.ndarray]:
        V = self.dreiecke_ecken.reshape(-1, 3)
        return V.min(axis=0), V.max(axis=0)

    def dreiecke(self, box_lo, box_hi, facette_mm: float) -> tuple[np.ndarray, np.ndarray]:
        m = len(self.dreiecke_ecken)
        return self.dreiecke_ecken.reshape(-1, 3), np.arange(3 * m).reshape(m, 3)

    def flaechenfaktor(self, Q, n_f) -> np.ndarray:
        return np.ones(len(np.asarray(Q).reshape(-1, 3)))

    def _beruehrende(self, P, r: float) -> np.ndarray:
        return self._index.beruehrende(P, r)

    def in_box(self, lo, hi) -> np.ndarray:
        """Facetten, deren Huellbox die Box [lo, hi] beruehrt (Saeule einer Zelle, geometry/huelle.py)."""
        return self._index.in_box(lo, hi)

    def _ebenen(self, idx: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
        """Ebenen der Facetten idx, koplanare zusammengefasst."""
        aus: list[tuple[np.ndarray, np.ndarray]] = []
        for t in idx:
            n = self.normalen[t]
            p = self.dreiecke_ecken[t, 0]
            doppelt = any(abs(float(n @ n2)) > 1 - 1e-9 and abs(float((p - p2) @ n2)) <= 1e-9 * (1 + float(np.abs(p).max())) for p2, n2 in aus)
            if not doppelt:
                aus.append((p.copy(), n.copy()))
        return aus

    def lokale_ebenen(self, P, r: float) -> list[tuple[np.ndarray, np.ndarray]]:
        """Ebenen der Facetten, die die Kugel (P, r) beruehren; koplanare zusammengefasst."""
        return self._ebenen(self._beruehrende(P, r))

    def lokale_lage(self, P, r: float) -> tuple[list[tuple[np.ndarray, np.ndarray]], str, np.ndarray]:
        """Lokale Ebenen, Lage des Werkstoffs in der Kugel (P, r) und je Ebene ihr Typ.

        Eine Ebene ist vom **Schnitt-Typ**, wenn alle Ecken aller beruehrenden Facetten auf ihrer
        Werkstoffseite liegen (der Werkstoff liegt lokal ganz in ihrem Halbraum), sonst vom
        **Vereinigungs-Typ** (Facetten einer konkaven Wand: die Nachbarn liegen auf ihrer Leerseite).
        'konvex'   - nur Schnitt-Typ: Werkstoff = Schnitt der Halbraeume (Flaeche, konvexe Kante/Ecke);
        'konkav'   - nur Vereinigungs-Typ: Leerraum = Schnitt der gespiegelten Halbraeume, Werkstoff
                     ihre Vereinigung (Bohrungswand, einspringende Kante);
        'gemischt' - beides: Werkstoff = (Schnitt der Schnitt-Typ-Halbraeume) ∩ (Vereinigung der
                     uebrigen), z. B. Deckel trifft Bohrungswand; csg._form_teile prueft das an den
                     Proben und faellt sonst auf die binaere Raumteilung zurueck.
        Ohne die konkave Lage fiele jede tessellierte Bohrungswand auf den Punkttest zurueck:
        Viertelring 1268 Facetten, h 10, p 3 -> 6573 Punkttest-Blaetter und 10,5 Mio.
        Randpunkte durch die Vierteilung der Facetten (27.09.2026)."""
        idx = self._beruehrende(P, r)
        ebenen = self._ebenen(idx)
        if len(ebenen) <= 1:
            return ebenen, "konvex", np.ones(len(ebenen), bool)
        V = self.dreiecke_ecken[idx].reshape(-1, 3)
        skala = 1e-9 * (1 + float(np.abs(V).max()))
        s = np.stack([(V - p) @ n for p, n in ebenen], axis=1)
        schnitt = (s <= skala).all(axis=0)
        if schnitt.all():
            return ebenen, "konvex", schnitt
        if (s >= -skala).all():
            return ebenen, "konkav", np.zeros(len(ebenen), bool)
        return ebenen, "gemischt", schnitt

    def lokal_konvex(self, P, r: float) -> bool:
        return self.lokale_lage(P, r)[1] == "konvex"


__all__ = ["lies_stl", "schreibe_stl", "windungszahl", "naechste_punkte", "Stl"]
