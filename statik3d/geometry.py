"""
Linienarten: Polylinie, Bogen, Kreis, Ellipse, Spline, Parabel.

Eine Linie ist reine Geometrie - sie traegt Staebe, Flaechenraender,
Linienlager und Netzvorgaben, hat aber selbst keine Steifigkeit. Dieses Modul
liefert zu jeder Art die **Stuetzpunkte**: die Punktfolge, mit der die Linie
gezeichnet, vernetzt und in Stabelemente geteilt wird.

Jede Art ist ueber ihre Stuetzstellen definiert, nicht ueber ein Netz; die
Teilung entsteht erst beim Abruf::

    b = Bogen.aus_drei_punkten(p1, p2, p3)
    b.punkte(24)          # 25 Punkte auf dem Bogen
    b.laenge()            # Bogenlaenge

Die Formeln sind geschlossen angeschrieben, damit sie nachrechenbar bleiben:

* **Bogen durch drei Punkte** - Mittelpunkt als Schnitt der Mittelsenkrechten
  in der Ebene der drei Punkte; Radius und Oeffnungswinkel folgen daraus.
* **Kreis** - Mittelpunkt, Radius, Ebenennormale.
* **Ellipse** - Mittelpunkt und die beiden Halbachsenvektoren.
* **Spline** - B-Spline vom Grad p mit gleichmaessigem, geklemmtem Knotenvektor
  (Cox-de-Boor); mit Gewichten wird daraus eine NURBS.
* **Parabel** - quadratische Bezierkurve durch Anfang, Scheitelrichtung, Ende.

Alle Punkte sind in Metern und im globalen System; die Umrechnung aus einem
benutzerdefinierten Koordinatensystem macht ``statik3d.ks``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Voreinstellung: so viele Abschnitte, wenn nichts anderes verlangt wird
TEILUNG = 16

#: Arten, die dieses Modul kennt
ARTEN = ("polyline", "arc", "circle", "ellipse", "spline", "parabola")


class GeometrieFehler(ValueError):
    """Die Angaben ergeben keine Linie (etwa drei Punkte auf einer Geraden)."""


def _v(p) -> np.ndarray:
    return np.asarray(p, dtype=float).reshape(3)


def _einheit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-14:
        raise GeometrieFehler("Richtungsvektor hat die Länge null")
    return v / n


# --------------------------------------------------------------------------
class Kurve:
    """Gemeinsamer Teil aller Linienarten."""

    art = "kurve"

    def punkte(self, n: int = TEILUNG) -> np.ndarray:
        """n+1 Punkte entlang der Linie, Anfang und Ende eingeschlossen."""
        raise NotImplementedError

    def laenge(self, n: int = 256) -> float:
        """Länge, aus einer feinen Teilung summiert."""
        p = self.punkte(n)
        return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())

    def beschreibung(self) -> str:
        return self.art


@dataclass
class Polylinie(Kurve):
    """Gerader Zug durch die gegebenen Punkte."""
    stuetzpunkte: list = field(default_factory=list)
    art = "polyline"

    def punkte(self, n: int = TEILUNG) -> np.ndarray:
        """n Abschnitte insgesamt - die Ecken bleiben immer Stuetzpunkte.

        Waere gleichmaessig ueber die Gesamtlaenge geteilt worden, faenden die
        Ecken sich nicht zwangslaeufig unter den Punkten wieder und der Zug
        wuerde sie abschneiden. Darum wird jeder Abschnitt fuer sich geteilt,
        seiner Laenge nach.
        """
        p = np.array([_v(x) for x in self.stuetzpunkte], dtype=float)
        if len(p) < 2:
            raise GeometrieFehler("Eine Polylinie braucht mindestens zwei Punkte")
        n = max(int(n), len(p) - 1)
        laengen = np.linalg.norm(np.diff(p, axis=0), axis=1)
        gesamt = float(laengen.sum())
        if gesamt <= 0:
            return p
        # Abschnitte nach Laenge verteilen, jeder bekommt mindestens einen
        teile = np.maximum(1, np.round(n * laengen / gesamt).astype(int))
        out = [p[0]]
        for k, t in enumerate(teile):
            for j in range(1, int(t) + 1):
                out.append(p[k] + (p[k + 1] - p[k]) * (j / t))
        return np.array(out)

    def laenge(self, n: int = 256) -> float:
        """Summe der Abschnittslaengen - fuer eine Polylinie exakt."""
        p = np.array([_v(x) for x in self.stuetzpunkte], dtype=float)
        if len(p) < 2:
            raise GeometrieFehler("Eine Polylinie braucht mindestens zwei Punkte")
        return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())

    def beschreibung(self) -> str:
        return f"Polylinie über {len(self.stuetzpunkte)} Punkte"


@dataclass
class Bogen(Kurve):
    """Kreisbogen: Mittelpunkt, Radius, Ebene und Öffnungswinkel."""
    mitte: np.ndarray = field(default_factory=lambda: np.zeros(3))
    radius: float = 1.0
    e1: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0]))
    e2: np.ndarray = field(default_factory=lambda: np.array([0.0, 1.0, 0.0]))
    winkel: float = np.pi          # Öffnungswinkel [rad], vom Anfang aus
    art = "arc"

    @classmethod
    def aus_drei_punkten(cls, p1, p2, p3) -> "Bogen":
        """Bogen durch drei Punkte: Anfang p1, Zwischenpunkt p2, Ende p3.

        Der Mittelpunkt ist der Schnitt der Mittelsenkrechten von p1p2 und
        p2p3 in der Ebene der drei Punkte.
        """
        a, b, c = _v(p1), _v(p2), _v(p3)
        n = np.cross(b - a, c - a)
        if float(np.linalg.norm(n)) < 1e-12:
            raise GeometrieFehler("Die drei Punkte liegen auf einer Geraden")
        n = _einheit(n)
        # Mittelpunkt: |m-a| = |m-b| = |m-c|, m in der Ebene
        A = np.array([b - a, c - a, n])
        rhs = np.array([0.5 * float((b - a) @ (b + a)),
                        0.5 * float((c - a) @ (c + a)),
                        float(n @ a)])
        m = np.linalg.solve(A, rhs)
        r = float(np.linalg.norm(a - m))
        e1 = _einheit(a - m)
        e2 = _einheit(np.cross(n, e1))

        def winkel_von(p):
            d = p - m
            return float(np.arctan2(d @ e2, d @ e1)) % (2 * np.pi)

        w2, w3 = winkel_von(b), winkel_von(c)
        # Laeuft der Zwischenpunkt nicht auf dem Weg von 0 nach w3, ist der
        # Bogen andersherum zu durchlaufen.
        if w2 > w3:
            e2 = -e2
            w3 = (2 * np.pi - w3) % (2 * np.pi)
        return cls(m, r, e1, e2, w3)

    @classmethod
    def aus_mitte(cls, mitte, radius: float, normale, start_richtung,
                  winkel_grad: float) -> "Bogen":
        """Bogen aus Mittelpunkt, Radius, Ebenennormale, Anfangsrichtung, Winkel."""
        n = _einheit(_v(normale))
        e1 = _v(start_richtung)
        e1 = _einheit(e1 - (e1 @ n) * n)
        e2 = _einheit(np.cross(n, e1))
        return cls(_v(mitte), float(radius), e1, e2, np.radians(float(winkel_grad)))

    def punkte(self, n: int = TEILUNG) -> np.ndarray:
        n = max(int(n), 1)
        t = np.linspace(0.0, self.winkel, n + 1)
        return (self.mitte + self.radius
                * (np.outer(np.cos(t), self.e1) + np.outer(np.sin(t), self.e2)))

    def laenge(self, n: int = 256) -> float:
        return float(self.radius * self.winkel)

    def beschreibung(self) -> str:
        return (f"Bogen r = {self.radius:.4g} m, "
                f"{np.degrees(self.winkel):.1f}°")


@dataclass
class Kreis(Bogen):
    """Vollkreis - ein Bogen über 360°."""
    art = "circle"

    @classmethod
    def aus_mitte_radius(cls, mitte, radius: float, normale=(0, 0, 1)) -> "Kreis":
        n = _einheit(_v(normale))
        hilf = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        e1 = _einheit(np.cross(hilf, n))
        e2 = _einheit(np.cross(n, e1))
        return cls(_v(mitte), float(radius), e1, e2, 2 * np.pi)

    def beschreibung(self) -> str:
        return f"Kreis r = {self.radius:.4g} m"


@dataclass
class Ellipse(Kurve):
    """Ellipse oder Ellipsenbogen: Mittelpunkt und zwei Halbachsenvektoren."""
    mitte: np.ndarray = field(default_factory=lambda: np.zeros(3))
    a: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0]))
    b: np.ndarray = field(default_factory=lambda: np.array([0.0, 1.0, 0.0]))
    von: float = 0.0
    bis: float = 2 * np.pi
    art = "ellipse"

    def punkte(self, n: int = TEILUNG) -> np.ndarray:
        t = np.linspace(self.von, self.bis, max(int(n), 1) + 1)
        return (self.mitte + np.outer(np.cos(t), _v(self.a))
                + np.outer(np.sin(t), _v(self.b)))

    def beschreibung(self) -> str:
        return (f"Ellipse {float(np.linalg.norm(self.a)):.4g} × "
                f"{float(np.linalg.norm(self.b)):.4g} m")


@dataclass
class Parabel(Kurve):
    """Parabel als quadratische Bezierkurve: Anfang, Steuerpunkt, Ende.

    Für einen Bogen mit Stich f in der Mitte liegt der Steuerpunkt bei
    2f über der Sehnenmitte - der Scheitel erreicht dann genau f.
    """
    p0: np.ndarray = field(default_factory=lambda: np.zeros(3))
    steuer: np.ndarray = field(default_factory=lambda: np.zeros(3))
    p1: np.ndarray = field(default_factory=lambda: np.zeros(3))
    art = "parabola"

    @classmethod
    def aus_stich(cls, anfang, ende, stich: float, richtung=(0, 0, 1)) -> "Parabel":
        a, e = _v(anfang), _v(ende)
        r = _v(richtung)
        sehne = e - a
        if float(np.linalg.norm(sehne)) < 1e-12:
            raise GeometrieFehler("Anfang und Ende fallen zusammen")
        # Richtung senkrecht zur Sehne, so nah wie möglich an der Vorgabe
        quer = r - (r @ _einheit(sehne)) * _einheit(sehne)
        quer = _einheit(quer) if float(np.linalg.norm(quer)) > 1e-12 else \
            _einheit(np.cross(sehne, [0.0, 0.0, 1.0]))
        return cls(a, 0.5 * (a + e) + 2.0 * float(stich) * quer, e)

    def punkte(self, n: int = TEILUNG) -> np.ndarray:
        t = np.linspace(0.0, 1.0, max(int(n), 1) + 1).reshape(-1, 1)
        return ((1 - t) ** 2 * _v(self.p0) + 2 * (1 - t) * t * _v(self.steuer)
                + t ** 2 * _v(self.p1))

    def beschreibung(self) -> str:
        return "Parabel"


@dataclass
class Spline(Kurve):
    """B-Spline / NURBS vom Grad p über Steuerpunkte.

    Der Knotenvektor ist gleichmäßig und geklemmt, die Kurve läuft also durch
    den ersten und letzten Steuerpunkt. Mit Gewichten (alle > 0) wird daraus
    eine NURBS; ohne Gewichte ist es ein gewöhnlicher B-Spline.
    """
    steuerpunkte: list = field(default_factory=list)
    grad: int = 3
    gewichte: list = field(default_factory=list)
    art = "spline"

    def _knoten(self, n: int, p: int) -> np.ndarray:
        """Geklemmter, gleichmäßiger Knotenvektor für n+1 Steuerpunkte."""
        m = n + p + 2
        u = np.zeros(m)
        u[:p + 1] = 0.0
        u[-(p + 1):] = 1.0
        innen = m - 2 * (p + 1)
        if innen > 0:
            u[p + 1:-(p + 1)] = np.arange(1, innen + 1) / (innen + 1)
        return u

    @staticmethod
    def _basis(i: int, p: int, u: float, U: np.ndarray) -> float:
        """Cox-de-Boor, rekursiv - der Lesbarkeit halber direkt hingeschrieben."""
        if p == 0:
            return 1.0 if (U[i] <= u < U[i + 1] or
                           (u >= U[-1] - 1e-12 and U[i] < U[i + 1] == U[-1])) else 0.0
        w = 0.0
        if U[i + p] > U[i]:
            w += (u - U[i]) / (U[i + p] - U[i]) * Spline._basis(i, p - 1, u, U)
        if U[i + p + 1] > U[i + 1]:
            w += ((U[i + p + 1] - u) / (U[i + p + 1] - U[i + 1])
                  * Spline._basis(i + 1, p - 1, u, U))
        return w

    def punkte(self, n: int = TEILUNG) -> np.ndarray:
        P = np.array([_v(x) for x in self.steuerpunkte], dtype=float)
        if len(P) < 2:
            raise GeometrieFehler("Ein Spline braucht mindestens zwei Steuerpunkte")
        p = int(min(max(self.grad, 1), len(P) - 1))
        U = self._knoten(len(P) - 1, p)
        w = (np.asarray(self.gewichte, float) if len(self.gewichte) == len(P)
             else np.ones(len(P)))
        if np.any(w <= 0):
            raise GeometrieFehler("Gewichte eines NURBS müssen größer als null sein")
        out = []
        for u in np.linspace(0.0, 1.0, max(int(n), 1) + 1):
            b = np.array([self._basis(i, p, float(u), U) for i in range(len(P))])
            s = float((b * w).sum())
            if s <= 1e-14:            # numerischer Randfall am Ende
                out.append(P[-1])
            else:
                out.append(((b * w) @ P) / s)
        return np.array(out)

    def beschreibung(self) -> str:
        art = "NURBS" if len(self.gewichte) == len(self.steuerpunkte) else "B-Spline"
        return f"{art} Grad {self.grad} über {len(self.steuerpunkte)} Punkte"


# --------------------------------------------------------------------------
def kurve(art: str, **kw) -> Kurve:
    """Eine Kurve über ihren Artnamen bauen.

        kurve("arc", punkte=[p1, p2, p3])
        kurve("circle", mitte=(0,0,0), radius=2.0, normale=(0,0,1))
        kurve("spline", steuerpunkte=[...], grad=3)
    """
    art = (art or "polyline").lower()
    if art == "polyline":
        return Polylinie(list(kw.get("punkte") or kw.get("stuetzpunkte") or []))
    if art == "arc":
        p = kw.get("punkte")
        if p is not None and len(p) >= 3:
            return Bogen.aus_drei_punkten(p[0], p[1], p[2])
        return Bogen.aus_mitte(kw["mitte"], kw["radius"], kw.get("normale", (0, 0, 1)),
                               kw.get("richtung", (1, 0, 0)), kw.get("winkel", 90.0))
    if art == "circle":
        return Kreis.aus_mitte_radius(kw["mitte"], kw["radius"],
                                      kw.get("normale", (0, 0, 1)))
    if art == "ellipse":
        return Ellipse(_v(kw["mitte"]), _v(kw["a"]), _v(kw["b"]),
                       float(kw.get("von", 0.0)), float(kw.get("bis", 2 * np.pi)))
    if art == "parabola":
        if "stich" in kw:
            return Parabel.aus_stich(kw["anfang"], kw["ende"], kw["stich"],
                                     kw.get("richtung", (0, 0, 1)))
        p = kw.get("punkte") or []
        return Parabel(_v(p[0]), _v(p[1]), _v(p[2]))
    if art == "spline":
        return Spline(list(kw.get("steuerpunkte") or kw.get("punkte") or []),
                      int(kw.get("grad", 3)), list(kw.get("gewichte") or []))
    raise GeometrieFehler(f"Linienart '{art}' gibt es nicht: {', '.join(ARTEN)}")
