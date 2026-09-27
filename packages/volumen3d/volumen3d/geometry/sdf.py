"""Grundformen als vorzeichenbehaftete Abstandsfunktionen (SDF, Vorgabe Abschnitt 3).

Alle Abstaende sind echte euklidische Abstaende zur Oberflaeche (1-Lipschitz), negativ im
Werkstoff. Das braucht die Zellklassifikation (fcm/gitter.py): |d(Mitte)| > halbe
Raumdiagonale heisst sicher ganz innen bzw. ganz aussen. Gradienten sind analytisch, weil
daraus die Normalen fuer Nitsche-Raender und Flaechenlasten kommen. Die Tessellierungen liefern
Dreiecke der Oberflaeche innerhalb einer Box; ihre Feinheit steuert nur die Flaechengewichte -
Lage und Normale der Quadraturpunkte werden in oberflaeche.py auf die exakte Flaeche projiziert.

Konvention Halbraum: Werkstoff liegt **gegen** die Normale (d = (P - punkt) . n), wie
``CutPlane.normal`` des Vertrags, die aus dem Detail heraus zeigt.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _einheit(v) -> np.ndarray:
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    if n == 0.0:
        raise ValueError("Nullvektor als Richtung")
    return v / n


def _senkrechte(a: np.ndarray) -> np.ndarray:
    """Ein Einheitsvektor senkrecht zu a (fuer Parametrisierungen um eine Achse)."""
    hilfe = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
    return _einheit(np.cross(a, hilfe))


def _box_abstand(q: np.ndarray) -> np.ndarray:
    """Abstandsformel achsparalleler Boxen in beliebiger Dimension, q = |x| - e."""
    aussen = np.linalg.norm(np.maximum(q, 0.0), axis=1)
    innen = np.minimum(q.max(axis=1), 0.0)
    return aussen + innen


def _box_gradient(q: np.ndarray, vorzeichen: np.ndarray) -> np.ndarray:
    """Gradient der Boxformel bezueglich x (q = |x| - e), vorzeichen = sign(x).

    Aussen zeigt er zum naechsten Punkt der Box, innen und auf der Oberflaeche senkrecht zur
    naechsten Seite (groesstes q) - so hat ein Punkt auf einer Seite die Seitennormale und
    kein entartetes max(q,0) = 0.
    """
    qp = np.maximum(q, 0.0)
    na = np.linalg.norm(qp, axis=1)
    g = np.zeros_like(q)
    a = na > 0
    g[a] = qp[a] / na[a, None]
    i = np.flatnonzero(~a)
    if len(i):
        g[i, q[i].argmax(axis=1)] = 1.0
    return g * vorzeichen


@dataclass(frozen=True)
class Quader:
    lo: np.ndarray
    hi: np.ndarray
    name: str = "quader"

    def __post_init__(self) -> None:
        object.__setattr__(self, "lo", np.asarray(self.lo, float).reshape(3))
        object.__setattr__(self, "hi", np.asarray(self.hi, float).reshape(3))
        if not np.all(self.hi > self.lo):
            raise ValueError(f"Quader {self.name!r}: max muss groesser als min sein")

    def _q(self, P):
        c = 0.5 * (self.lo + self.hi)
        e = 0.5 * (self.hi - self.lo)
        x = np.asarray(P, float).reshape(-1, 3) - c
        return np.abs(x) - e, np.where(x >= 0, 1.0, -1.0)

    def abstand(self, P) -> np.ndarray:
        return _box_abstand(self._q(P)[0])

    def gradient(self, P) -> np.ndarray:
        q, s = self._q(P)
        return _box_gradient(q, s)

    def huellquader(self) -> tuple[np.ndarray, np.ndarray]:
        return self.lo.copy(), self.hi.copy()

    gekruemmt = False

    def lokale_ebenen(self, P, r: float) -> list[tuple[np.ndarray, np.ndarray]]:
        """Seitenebenen im Abstand <= r von P (Punkt, Normale nach aussen); exakt."""
        P = np.asarray(P, float).reshape(3)
        aus = []
        for d in range(3):
            for grenze, vz in ((self.lo[d], -1.0), (self.hi[d], 1.0)):
                if abs(P[d] - grenze) <= r:
                    q = P.copy()
                    q[d] = grenze
                    n = np.zeros(3)
                    n[d] = vz
                    aus.append((q, n))
        return aus

    def dreiecke(self, box_lo, box_hi, facette_mm: float) -> tuple[np.ndarray, np.ndarray]:
        lo, hi = self.lo, self.hi
        V = np.array([[lo[0], lo[1], lo[2]], [hi[0], lo[1], lo[2]], [hi[0], hi[1], lo[2]], [lo[0], hi[1], lo[2]],
                      [lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]], [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]]])
        T = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                      [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]], int)
        return V, T


@dataclass(frozen=True)
class Zylinder:
    """Endlicher Kreiszylinder von p0 nach p1 mit Radius; Deckel eingeschlossen."""
    p0: np.ndarray
    p1: np.ndarray
    radius: float
    name: str = "zylinder"

    def __post_init__(self) -> None:
        object.__setattr__(self, "p0", np.asarray(self.p0, float).reshape(3))
        object.__setattr__(self, "p1", np.asarray(self.p1, float).reshape(3))
        if self.radius <= 0 or np.allclose(self.p0, self.p1):
            raise ValueError(f"Zylinder {self.name!r}: Radius > 0 und p0 != p1 noetig")

    def _achse(self):
        a = self.p1 - self.p0
        Lz = float(np.linalg.norm(a))
        return a / Lz, Lz

    def _lokal(self, P):
        a, Lz = self._achse()
        rel = np.asarray(P, float).reshape(-1, 3) - self.p0
        t = rel @ a
        rvec = rel - t[:, None] * a
        r = np.linalg.norm(rvec, axis=1)
        q = np.stack([r - self.radius, np.abs(t - 0.5 * Lz) - 0.5 * Lz], axis=1)
        return a, Lz, t, rvec, r, q

    def abstand(self, P) -> np.ndarray:
        return _box_abstand(self._lokal(P)[5])

    def gradient(self, P) -> np.ndarray:
        a, Lz, t, rvec, r, q = self._lokal(P)
        g2 = _box_gradient(q, np.stack([np.ones_like(r), np.where(t - 0.5 * Lz >= 0, 1.0, -1.0)], axis=1))
        er = np.zeros_like(rvec)
        ok = r > 0
        er[ok] = rvec[ok] / r[ok, None]
        er[~ok] = _senkrechte(a)                      # auf der Achse: Radialrichtung beliebig
        return g2[:, :1] * er + g2[:, 1:] * a

    def huellquader(self) -> tuple[np.ndarray, np.ndarray]:
        a, _ = self._achse()
        e = self.radius * np.sqrt(np.clip(1.0 - a ** 2, 0.0, 1.0))
        return np.minimum(self.p0, self.p1) - e, np.maximum(self.p0, self.p1) + e

    gekruemmt = True

    def lokale_ebenen(self, P, r: float) -> list[tuple[np.ndarray, np.ndarray]]:
        """Tangentialebene des Mantels (am radial projizierten Punkt) und Deckelebenen im
        Abstand <= r von P."""
        a, Lz, t, rvec, rho, _ = self._lokal(np.asarray(P, float).reshape(1, 3))
        t, rvec, rho = float(t[0]), rvec[0], float(rho[0])
        aus = []
        if abs(rho - self.radius) <= r:
            er = rvec / rho if rho > 0 else _senkrechte(a)
            aus.append((self.p0 + t * a + self.radius * er, er))
        if abs(t) <= r:
            aus.append((self.p0.copy(), -a))
        if abs(t - Lz) <= r:
            aus.append((self.p1.copy(), a.copy()))
        return aus

    def dreiecke(self, box_lo, box_hi, facette_mm: float) -> tuple[np.ndarray, np.ndarray]:
        a, Lz = self._achse()
        u = _senkrechte(a)
        v = np.cross(a, u)
        ns = max(8, int(np.ceil(2 * np.pi * self.radius / max(facette_mm, 1e-9))))
        na = max(1, int(np.ceil(Lz / max(facette_mm, 1e-9))))
        th = np.linspace(0, 2 * np.pi, ns, endpoint=False)
        ring = self.radius * (np.cos(th)[:, None] * u + np.sin(th)[:, None] * v)
        V = np.concatenate([self.p0 + ring + (Lz * k / na) * a for k in range(na + 1)]
                           + [self.p0[None], self.p1[None]])
        T = []
        for k in range(na):
            b0, b1 = k * ns, (k + 1) * ns
            for i in range(ns):
                j = (i + 1) % ns
                T += [[b0 + i, b0 + j, b1 + j], [b0 + i, b1 + j, b1 + i]]
        c0, c1 = len(V) - 2, len(V) - 1
        for i in range(ns):
            j = (i + 1) % ns
            T += [[c0, j, i], [c1, na * ns + i, na * ns + j]]
        return V, np.asarray(T, int)


@dataclass(frozen=True)
class Kugel:
    mitte: np.ndarray
    radius: float
    name: str = "kugel"

    def __post_init__(self) -> None:
        object.__setattr__(self, "mitte", np.asarray(self.mitte, float).reshape(3))
        if self.radius <= 0:
            raise ValueError(f"Kugel {self.name!r}: Radius > 0 noetig")

    def abstand(self, P) -> np.ndarray:
        return np.linalg.norm(np.asarray(P, float).reshape(-1, 3) - self.mitte, axis=1) - self.radius

    def gradient(self, P) -> np.ndarray:
        d = np.asarray(P, float).reshape(-1, 3) - self.mitte
        n = np.linalg.norm(d, axis=1)
        g = np.zeros_like(d)
        ok = n > 0
        g[ok] = d[ok] / n[ok, None]
        g[~ok] = [0.0, 0.0, 1.0]
        return g

    def huellquader(self) -> tuple[np.ndarray, np.ndarray]:
        return self.mitte - self.radius, self.mitte + self.radius

    gekruemmt = True

    def lokale_ebenen(self, P, r: float) -> list[tuple[np.ndarray, np.ndarray]]:
        """Tangentialebene am radial projizierten Punkt, wenn die Kugelflaeche naeher als r ist."""
        d = np.asarray(P, float).reshape(3) - self.mitte
        rho = float(np.linalg.norm(d))
        if abs(rho - self.radius) > r:
            return []
        er = d / rho if rho > 0 else np.array([0.0, 0.0, 1.0])
        return [(self.mitte + self.radius * er, er)]

    def dreiecke(self, box_lo, box_hi, facette_mm: float) -> tuple[np.ndarray, np.ndarray]:
        ns = max(8, int(np.ceil(2 * np.pi * self.radius / max(facette_mm, 1e-9))))
        nph = max(4, ns // 2)
        th = np.linspace(0, 2 * np.pi, ns, endpoint=False)
        ph = np.linspace(0, np.pi, nph + 1)
        V = [self.mitte + self.radius * np.array([0, 0, 1.0])]
        for j in range(1, nph):
            V += list(self.mitte + self.radius * np.stack([np.sin(ph[j]) * np.cos(th), np.sin(ph[j]) * np.sin(th),
                                                          np.full(ns, np.cos(ph[j]))], axis=1))
        V.append(self.mitte + self.radius * np.array([0, 0, -1.0]))
        V = np.asarray(V)
        T = []
        for i in range(ns):
            j = (i + 1) % ns
            T.append([0, 1 + i, 1 + j])
            for k in range(nph - 2):
                a0, a1 = 1 + k * ns, 1 + (k + 1) * ns
                T += [[a0 + i, a1 + i, a1 + j], [a0 + i, a1 + j, a0 + j]]
            b = 1 + (nph - 2) * ns
            T.append([b + i, len(V) - 1, b + j])
        return V, np.asarray(T, int)


@dataclass(frozen=True)
class Halbraum:
    """Werkstoff auf der Seite gegen die Normale: d = (P - punkt) . n."""
    punkt: np.ndarray
    normale: np.ndarray
    name: str = "halbraum"

    def __post_init__(self) -> None:
        object.__setattr__(self, "punkt", np.asarray(self.punkt, float).reshape(3))
        object.__setattr__(self, "normale", _einheit(np.asarray(self.normale, float).reshape(3)))

    def abstand(self, P) -> np.ndarray:
        return (np.asarray(P, float).reshape(-1, 3) - self.punkt) @ self.normale

    def gradient(self, P) -> np.ndarray:
        return np.broadcast_to(self.normale, (len(np.asarray(P).reshape(-1, 3)), 3)).copy()

    def huellquader(self) -> tuple[np.ndarray, np.ndarray]:
        return np.full(3, -np.inf), np.full(3, np.inf)

    gekruemmt = False

    def lokale_ebenen(self, P, r: float) -> list[tuple[np.ndarray, np.ndarray]]:
        if abs(float(self.abstand(np.asarray(P, float).reshape(1, 3))[0])) > r:
            return []
        return [(self.punkt.copy(), self.normale.copy())]

    def dreiecke(self, box_lo, box_hi, facette_mm: float) -> tuple[np.ndarray, np.ndarray]:
        """Polygon Ebene ∩ Box aus den Schnittpunkten der zwoelf Boxkanten, nach Winkel
        sortiert, als Faecher trianguliert."""
        lo, hi = np.asarray(box_lo, float), np.asarray(box_hi, float)
        ecken = np.array([[hi[0] if i & 1 else lo[0], hi[1] if i & 2 else lo[1], hi[2] if i & 4 else lo[2]]
                          for i in range(8)])
        kanten = [(i, j) for i in range(8) for j in range(i + 1, 8) if bin(i ^ j).count("1") == 1]
        d = self.abstand(ecken)
        pts = []
        for i, j in kanten:
            if (d[i] <= 0) != (d[j] <= 0) and d[i] != d[j]:
                s = d[i] / (d[i] - d[j])
                pts.append(ecken[i] + s * (ecken[j] - ecken[i]))
        if len(pts) < 3:
            return np.zeros((0, 3)), np.zeros((0, 3), int)
        pts = np.asarray(pts)
        c = pts.mean(axis=0)
        u = _senkrechte(self.normale)
        v = np.cross(self.normale, u)
        pts = pts[np.argsort(np.arctan2((pts - c) @ v, (pts - c) @ u))]
        T = np.array([[0, i, i + 1] for i in range(1, len(pts) - 1)], int).reshape(-1, 3)
        return pts, T


Grundform = Quader | Zylinder | Kugel | Halbraum

__all__ = ["Quader", "Zylinder", "Kugel", "Halbraum", "Grundform"]
