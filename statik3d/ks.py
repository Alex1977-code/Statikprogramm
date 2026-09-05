"""
Koordinatensysteme, Arbeitsebene und Objektfang.

Ein Modell wird selten im globalen System eingegeben. Eine geneigte Gleitbahn,
ein Segmentverschluss, ein Rohrstutzen - jedes davon hat sein eigenes Bezugs-
system, und die Eingabe soll darin erfolgen dürfen. Dieses Modul haelt drei
Dinge auseinander:

**Koordinatensystem** - Ursprung und drei Achsen, wahlweise kartesisch,
zylindrisch (r, θ, z) oder sphaerisch (r, θ, φ). ``nach_global`` rechnet
Eingabewerte in das globale System, ``aus_global`` zurueck::

    ks = Koordinatensystem.aus_punkten("Gleitbahn", (0,0,0), (1,0,0.2), (0,1,0))
    ks.nach_global((2, 0, 0))        # 2 m entlang der geneigten x-Achse

**Arbeitsebene** - die Ebene, in der geklickt wird, mit Raster. Ein Klick in
die Ansicht liefert einen Strahl; ``schnitt`` gibt den Punkt, in dem er die
Ebene trifft, ``fangen`` rastet ihn auf das Raster ein.

**Fang** - der angeklickte Punkt wird auf die naechste markante Stelle gezogen:
Knoten, Mittelpunkt einer Kante, Rasterpunkt. Was gefangen wurde, steht in der
Rueckgabe, damit die Oberflaeche es anzeigen kann.

Winkel stehen in Grad, wo sie eingegeben werden, und in Radiant, wo gerechnet
wird; die Umrechnung steht jeweils an der Schnittstelle.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Arten von Koordinatensystemen
ARTEN = ("kartesisch", "zylindrisch", "sphaerisch")

#: Ebenen der Arbeitsebene
EBENEN = ("xy", "yz", "xz")

#: Was gefangen werden kann - in dieser Reihenfolge hat der Fang den Vorrang:
#: ein Knoten geht der Stabmitte vor, diese dem Punkt auf einer Linie, dann
#: Stab, Flaeche (Randmitten und Schwerpunkt), Volumen (Schwerpunkt), Raster.
FANGARTEN = ("knoten", "mitte", "linie", "stab", "flaeche", "volumen", "raster")

#: Klartext je Fangart
FANG_TEXT = {"knoten": "Knoten", "mitte": "Kantenmitte", "linie": "Linie",
             "stab": "Stab", "flaeche": "Fläche", "volumen": "Volumen",
             "raster": "Raster"}


def _v(p) -> np.ndarray:
    return np.asarray(p, dtype=float).reshape(3)


def _einheit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-14:
        raise ValueError("Achse hat die Länge null")
    return v / n


@dataclass
class Koordinatensystem:
    """Ursprung und Achsen. Die Achsen stehen als Zeilen in der Drehmatrix."""
    name: str = "global"
    ursprung: np.ndarray = field(default_factory=lambda: np.zeros(3))
    ex: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0]))
    ey: np.ndarray = field(default_factory=lambda: np.array([0.0, 1.0, 0.0]))
    ez: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0]))
    art: str = "kartesisch"

    # -- Anlegen ---------------------------------------------------------
    @classmethod
    def global_ks(cls) -> "Koordinatensystem":
        return cls()

    @classmethod
    def aus_punkten(cls, name: str, ursprung, punkt_x, punkt_xy,
                    art: str = "kartesisch") -> "Koordinatensystem":
        """Aus drei Punkten: Ursprung, ein Punkt auf der x-Achse, einer in der xy-Ebene."""
        o, px, pxy = _v(ursprung), _v(punkt_x), _v(punkt_xy)
        ex = _einheit(px - o)
        h = pxy - o
        h = h - (h @ ex) * ex
        ey = _einheit(h)
        return cls(name, o, ex, ey, np.cross(ex, ey), art)

    @classmethod
    def aus_winkeln(cls, name: str, ursprung, alpha: float = 0.0, beta: float = 0.0,
                    gamma: float = 0.0, art: str = "kartesisch") -> "Koordinatensystem":
        """Aus Drehungen um x, y, z (Grad, in dieser Reihenfolge angewandt)."""
        a, b, c = np.radians([float(alpha), float(beta), float(gamma)])
        Rx = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
        Ry = np.array([[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]])
        Rz = np.array([[np.cos(c), -np.sin(c), 0], [np.sin(c), np.cos(c), 0], [0, 0, 1]])
        R = Rz @ Ry @ Rx
        return cls(name, _v(ursprung), R[:, 0], R[:, 1], R[:, 2], art)

    @classmethod
    def an_stab(cls, name: str, p1, p2, hoch=(0.0, 0.0, 1.0)) -> "Koordinatensystem":
        """Achse x entlang des Stabes, z möglichst nach oben."""
        a, b = _v(p1), _v(p2)
        ex = _einheit(b - a)
        h = _v(hoch)
        h = h - (h @ ex) * ex
        if float(np.linalg.norm(h)) < 1e-9:      # senkrechter Stab
            h = np.array([1.0, 0.0, 0.0]) - float(ex[0]) * ex
        ez = _einheit(h)
        return cls(name, a, ex, np.cross(ez, ex), ez)

    # -- Umrechnen -------------------------------------------------------
    @property
    def matrix(self) -> np.ndarray:
        """Spalten sind die Achsen: x_global = R @ x_lokal + Ursprung."""
        return np.column_stack([self.ex, self.ey, self.ez])

    def nach_global(self, p) -> np.ndarray:
        """Eingabewerte dieses Systems in globale Koordinaten."""
        q = self._kartesisch(_v(p))
        return self.ursprung + self.matrix @ q

    def aus_global(self, p) -> np.ndarray:
        """Globale Koordinaten in die Werte dieses Systems."""
        q = self.matrix.T @ (_v(p) - self.ursprung)
        return self._entkartesisch(q)

    def _kartesisch(self, q: np.ndarray) -> np.ndarray:
        if self.art == "zylindrisch":
            r, t, z = float(q[0]), np.radians(float(q[1])), float(q[2])
            return np.array([r * np.cos(t), r * np.sin(t), z])
        if self.art == "sphaerisch":
            r, t, f = float(q[0]), np.radians(float(q[1])), np.radians(float(q[2]))
            return np.array([r * np.sin(f) * np.cos(t), r * np.sin(f) * np.sin(t),
                             r * np.cos(f)])
        return q

    def _entkartesisch(self, q: np.ndarray) -> np.ndarray:
        if self.art == "zylindrisch":
            r = float(np.hypot(q[0], q[1]))
            return np.array([r, np.degrees(np.arctan2(q[1], q[0])), float(q[2])])
        if self.art == "sphaerisch":
            r = float(np.linalg.norm(q))
            if r < 1e-14:
                return np.zeros(3)
            return np.array([r, np.degrees(np.arctan2(q[1], q[0])),
                             np.degrees(np.arccos(float(q[2]) / r))])
        return q

    def beschreibung(self) -> str:
        if self.art == "kartesisch":
            return f"{self.name}: Ursprung {np.round(self.ursprung, 3).tolist()}"
        return (f"{self.name} ({self.art}): Ursprung "
                f"{np.round(self.ursprung, 3).tolist()}")

    def achsennamen(self) -> tuple:
        if self.art == "zylindrisch":
            return ("r [m]", "θ [°]", "z [m]")
        if self.art == "sphaerisch":
            return ("r [m]", "θ [°]", "φ [°]")
        return ("x [m]", "y [m]", "z [m]")


@dataclass
class Arbeitsebene:
    """Die Ebene, in der geklickt wird, mit Raster."""
    ks: Koordinatensystem = field(default_factory=Koordinatensystem)
    ebene: str = "xy"
    versatz: float = 0.0            # Abstand von der Ebene des KS [m]
    raster: float = 0.5             # Rasterweite [m], 0 = kein Raster

    def achsen(self) -> tuple:
        """(u, v, n): die beiden Richtungen in der Ebene und ihre Normale."""
        if self.ebene == "yz":
            return self.ks.ey, self.ks.ez, self.ks.ex
        if self.ebene == "xz":
            return self.ks.ex, self.ks.ez, -self.ks.ey
        return self.ks.ex, self.ks.ey, self.ks.ez

    def ursprung(self) -> np.ndarray:
        _u, _v_, n = self.achsen()
        return self.ks.ursprung + self.versatz * n

    def schnitt(self, punkt, richtung) -> np.ndarray | None:
        """Punkt, in dem der Strahl die Arbeitsebene trifft (None = parallel)."""
        _u, _v_, n = self.achsen()
        p, d = _v(punkt), _v(richtung)
        nenner = float(n @ d)
        if abs(nenner) < 1e-12:
            return None
        t = float(n @ (self.ursprung() - p)) / nenner
        return p + t * d

    def projizieren(self, punkt) -> np.ndarray:
        """Einen Punkt senkrecht auf die Arbeitsebene legen."""
        _u, _v_, n = self.achsen()
        p = _v(punkt)
        return p - float(n @ (p - self.ursprung())) * n

    def rasterpunkt(self, punkt) -> np.ndarray:
        """Den Punkt auf den nächsten Rasterpunkt der Ebene ziehen."""
        if self.raster <= 0:
            return _v(punkt)
        u, v, _n = self.achsen()
        o = self.ursprung()
        d = _v(punkt) - o
        a = round(float(d @ u) / self.raster) * self.raster
        b = round(float(d @ v) / self.raster) * self.raster
        return o + a * u + b * v

    def beschreibung(self) -> str:
        return (f"{self.ks.name} · Ebene {self.ebene}"
                + (f" · Versatz {self.versatz:g} m" if self.versatz else "")
                + (f" · Raster {self.raster:g} m" if self.raster > 0 else " · kein Raster"))


@dataclass
class Fangtreffer:
    """Was der Fang gefunden hat."""
    punkt: np.ndarray
    art: str = ""                   # "" = nichts gefangen
    knoten: int = -1
    abstand: float = 0.0

    def text(self) -> str:
        if not self.art:
            return "frei"
        if self.art == "knoten":
            return f"Knoten {self.knoten + 1}"
        return {"mitte": "Kantenmitte", "raster": "Raster"}.get(self.art, self.art)


def fangen(punkt, knoten=None, kanten=None, ebene: Arbeitsebene = None,
           weite: float = 0.15, arten=FANGARTEN) -> Fangtreffer:
    """Den Punkt auf die nächste markante Stelle ziehen.

    knoten: (n,3) Koordinaten, kanten: Liste von (i, j) auf diese Knoten.
    weite:  Fangradius [m]. Die Reihenfolge ist verbindlich - ein Knoten geht
            der Kantenmitte vor, diese dem Raster.
    """
    p = _v(punkt)
    K = np.asarray(knoten, float).reshape(-1, 3) if knoten is not None and len(knoten) \
        else np.zeros((0, 3))
    if "knoten" in arten and len(K):
        d = np.linalg.norm(K - p, axis=1)
        i = int(np.argmin(d))
        if float(d[i]) <= weite:
            return Fangtreffer(K[i].copy(), "knoten", i, float(d[i]))
    if "mitte" in arten and kanten is not None and len(K):
        best, bi = None, -1.0
        for a, b in kanten:
            m = 0.5 * (K[int(a)] + K[int(b)])
            dd = float(np.linalg.norm(m - p))
            if dd <= weite and (best is None or dd < bi):
                best, bi = m, dd
        if best is not None:
            return Fangtreffer(best, "mitte", -1, bi)
    if "raster" in arten and ebene is not None and ebene.raster > 0:
        r = ebene.rasterpunkt(p)
        dd = float(np.linalg.norm(r - p))
        if dd <= weite:
            return Fangtreffer(r, "raster", -1, dd)
    return Fangtreffer(p)
