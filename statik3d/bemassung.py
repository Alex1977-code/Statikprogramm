"""
Messen und Bemaßen in der Ansicht.

**Messen** (Register Messen → Messen) beantwortet eine Frage sofort - Abstand
zweier Punkte, Winkel dreier Punkte, Koordinaten, Länge und Fläche der
Auswahl - und zeichnet die Antwort vorübergehend in die Ansicht; sie wird
nicht gespeichert.

**Bemaßungen** (Register Messen → Bemaßung) sind Objekte des Modells: Linear-
maß, Maßkette, Höhenkote, Winkelmaß und Radius. Sie hängen an Weltpunkten,
werden mit Maßhilfslinien, Maßlinie, Schrägstrichen und Text gezeichnet,
mit der Datei gespeichert und stehen im Modellbaum. Einheit, Nachkomma-
stellen, Textgröße, Versatz und Höhenbezug regeln die Einstellungen.

Die Geometrie eines Maßes (``geometrie``) ist reine Rechnung: Strecken und
Textanker in Weltkoordinaten. Die Ansicht zeichnet sie, der Test prüft sie.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

EINHEITEN = {"m": 1.0, "cm": 100.0, "mm": 1000.0}
ARTEN = {"linear": "Linearmaß", "kette": "Maßkette", "hoehenkote": "Höhenkote",
         "winkel": "Winkelmaß", "radius": "Radius"}
#: Punkte, die eine Bemaßungsart braucht (0 = beliebig viele, mindestens 2)
PUNKTE = {"linear": 2, "kette": 0, "hoehenkote": 1, "winkel": 3, "radius": 2}


@dataclass
class BemassungEinstellung:
    einheit: str = "m"
    nachkomma: int = 3
    textgroesse: int = 11              # Punkt
    versatz: float = 0.0               # Abstand der Maßlinie [m]; 0 = 8 % der Modellgröße
    farbe: str = "#1d2731"
    hoehen_bezug: float = 0.0          # z der Kote ±0.000 [m]


@dataclass
class Bemassung:
    """Ein Maß im Modell."""
    name: str
    art: str = "linear"
    punkte: list = field(default_factory=list)      # [[x, y, z], …] Weltkoordinaten
    versatz: Optional[float] = None                 # None = Einstellung
    richtung: Optional[list] = None                 # Versatzrichtung (Einheitsvektor); None = automatisch
    text: str = ""                                  # Übersteuerung des Maßtexts
    einheit: str = ""                               # "" = Einstellung
    nachkomma: Optional[int] = None
    kommentar: str = ""

    def bezug(self) -> str:
        t = ARTEN.get(self.art, self.art)
        P = [np.asarray(p, float) for p in self.punkte]
        if self.art in ("linear", "kette") and len(P) >= 2:
            L = sum(float(np.linalg.norm(P[i + 1] - P[i])) for i in range(len(P) - 1))
            t += f" {L:.3f} m" + (f" ({len(P) - 1} Glieder)" if self.art == "kette" else "")
        elif self.art == "hoehenkote" and P:
            t += f" z = {P[0][2]:.3f} m"
        elif self.art == "winkel" and len(P) == 3:
            t += f" {winkel(P[0], P[1], P[2]):.1f}°"
        elif self.art == "radius" and len(P) >= 2:
            t += f" R {radius(P):.3f} m"
        return t


# ==========================================================================
# Geschlossene Formeln
# ==========================================================================
def abstand(a, b) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    return {"L": float(np.linalg.norm(d)), "dx": float(d[0]), "dy": float(d[1]), "dz": float(d[2]),
            "L_xy": float(math.hypot(d[0], d[1]))}


def winkel(a, b, c) -> float:
    """Winkel [°] im Scheitel b zwischen den Schenkeln b→a und b→c."""
    u = np.asarray(a, float) - np.asarray(b, float)
    v = np.asarray(c, float) - np.asarray(b, float)
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu < 1e-15 or nv < 1e-15:
        return 0.0
    return float(math.degrees(math.acos(max(-1.0, min(1.0, float(u @ v) / (nu * nv))))))


def polygonflaeche(punkte) -> tuple:
    """(Fläche, Schwerpunkt) eines ebenen Polygons im Raum (Newell / Dreiecksfächer)."""
    P = np.asarray(punkte, float)
    if len(P) < 3:
        return 0.0, (P.mean(axis=0) if len(P) else np.zeros(3))
    n = np.zeros(3)
    for i in range(len(P)):
        n += np.cross(P[i], P[(i + 1) % len(P)])
    A = 0.5 * float(np.linalg.norm(n))
    if A < 1e-15:
        return 0.0, P.mean(axis=0)
    e = n / np.linalg.norm(n)
    S = np.zeros(3)
    for i in range(1, len(P) - 1):
        Ai = 0.5 * float(np.cross(P[i] - P[0], P[i + 1] - P[0]) @ e)
        S += Ai * (P[0] + P[i] + P[i + 1]) / 3.0
    return A, S / A


def kreis_aus_drei(a, b, c) -> tuple:
    """(Radius, Mittelpunkt) des Kreises durch drei Punkte."""
    a, b, c = (np.asarray(x, float) for x in (a, b, c))
    ab, ac = b - a, c - a
    n = np.cross(ab, ac)
    nn = float(n @ n)
    if nn < 1e-24:
        raise ValueError("Die drei Punkte liegen auf einer Geraden - kein Kreis")
    m = a + (np.cross(n, ab) * float(ac @ ac) + np.cross(ac, n) * float(ab @ ab)) / (2.0 * nn)
    return float(np.linalg.norm(m - a)), m


def radius(punkte) -> float:
    P = [np.asarray(p, float) for p in punkte]
    if len(P) >= 3:
        return kreis_aus_drei(P[0], P[1], P[2])[0]
    return float(np.linalg.norm(P[1] - P[0]))


def masstext(wert_m: float, einheit: str = "m", nachkomma: int = 3, vorzeichen: bool = False) -> str:
    f = EINHEITEN.get(einheit, 1.0)
    v = wert_m * f
    if vorzeichen:
        if abs(v) < 0.5 * 10.0 ** (-nachkomma):
            return f"±{0:.{nachkomma}f} {einheit}"
        return f"{'+' if v > 0 else '−'}{abs(v):.{nachkomma}f} {einheit}"
    return f"{v:.{nachkomma}f} {einheit}"


def versatzrichtung(a, b, blick=None) -> np.ndarray:
    """Einheitsvektor senkrecht zur Strecke a-b und senkrecht zur Blickrichtung
    (dann liegt die Maßlinie sichtbar neben der Strecke)."""
    s = np.asarray(b, float) - np.asarray(a, float)
    Ls = float(np.linalg.norm(s))
    if Ls < 1e-15:
        return np.array([0.0, 0.0, 1.0])
    s /= Ls
    kandidaten = []
    if blick is not None:
        kandidaten.append(np.cross(np.asarray(blick, float), s))
    kandidaten += [np.cross(np.array([0.0, -1.0, 0.0]), s), np.cross(np.array([0.0, 0.0, 1.0]), s),
                   np.cross(np.array([1.0, 0.0, 0.0]), s)]
    for d in kandidaten:
        L = float(np.linalg.norm(d))
        if L > 1e-9:
            d = d / L
            # nach oben bzw. nach rechts, nicht nach unten - so liest man Maße
            if d[2] < -1e-9 or (abs(d[2]) <= 1e-9 and (d[0] < -1e-9 or (abs(d[0]) <= 1e-9 and d[1] < 0))):
                d = -d
            return d
    return np.array([0.0, 0.0, 1.0])


def messung_text(art: str, punkte, einheit: str = "m", nachkomma: int = 3) -> str:
    """Die Antwort einer Messung als Zeile für Statuszeile und Protokoll."""
    P = [np.asarray(p, float) for p in punkte]
    f = lambda v: masstext(v, einheit, nachkomma)          # noqa: E731
    if art == "abstand" and len(P) >= 2:
        d = abstand(P[0], P[1])
        return (f"Abstand {f(d['L'])}  (Δx {f(d['dx'])}, Δy {f(d['dy'])}, Δz {f(d['dz'])}, "
                f"in der Ebene {f(d['L_xy'])})")
    if art == "winkel" and len(P) >= 3:
        return f"Winkel {winkel(P[0], P[1], P[2]):.2f}° im Scheitel ({P[1][0]:.3f}, {P[1][1]:.3f}, {P[1][2]:.3f})"
    if art == "koordinaten" and P:
        return f"Punkt x = {f(P[0][0])}, y = {f(P[0][1])}, z = {f(P[0][2])}"
    if art == "flaeche" and len(P) >= 3:
        A, S = polygonflaeche(P)
        return f"Fläche {A:.4f} m², Schwerpunkt ({S[0]:.3f}, {S[1]:.3f}, {S[2]:.3f})"
    if art == "radius" and len(P) >= 2:
        return f"Radius {f(radius(P))}"
    return ""


# ==========================================================================
# Geometrie eines Maßes
# ==========================================================================
def _linear(a, b, d, v, s, text) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float)
    A, B = a + v * d, b + v * d
    ueber = 0.25 * s
    t = B - A
    Lt = float(np.linalg.norm(t))
    t = t / Lt if Lt > 1e-15 else np.zeros(3)
    schraeg = (t + d) / math.sqrt(2.0) * 0.5 * s        # Schrägstrich 45°
    linien = [(a, A + ueber * d), (b, B + ueber * d), (A - 0.1 * s * t, B + 0.1 * s * t),
              (A - schraeg, A + schraeg), (B - schraeg, B + schraeg)]
    return {"linien": linien, "texte": [(0.5 * (A + B) + 0.45 * s * d, text)], "punkte": [A, B]}


def geometrie(bem: Bemassung, einst: BemassungEinstellung, groesse: float, blick=None) -> dict:
    """Strecken, Texte und Hilfspunkte eines Maßes in Weltkoordinaten."""
    P = [np.asarray(p, float) for p in bem.punkte]
    einheit = bem.einheit or einst.einheit
    nk = einst.nachkomma if bem.nachkomma is None else int(bem.nachkomma)
    v = bem.versatz if bem.versatz is not None else (einst.versatz or 0.08 * max(groesse, 1e-9))
    s = 0.25 * abs(v) if v else 0.02 * groesse                 # Maß der Striche und Symbole
    aus = {"linien": [], "texte": [], "punkte": []}
    art = bem.art
    if art in ("linear", "kette") and len(P) >= 2:
        d = np.asarray(bem.richtung, float) if bem.richtung else versatzrichtung(P[0], P[-1], blick)
        paare = [(P[i], P[i + 1]) for i in range(len(P) - 1)] if art == "kette" else [(P[0], P[1])]
        for k, (a, b) in enumerate(paare):
            text = bem.text if (bem.text and art == "linear") else masstext(abstand(a, b)["L"], einheit, nk)
            g = _linear(a, b, d, v, s, text)
            aus["linien"] += g["linien"]
            aus["texte"] += g["texte"]
            aus["punkte"] += g["punkte"]
        if art == "kette" and len(paare) > 1:
            L = sum(abstand(a, b)["L"] for a, b in paare)
            g = _linear(P[0], P[-1], d, 2.2 * v, s, bem.text or masstext(L, einheit, nk))
            aus["linien"] += g["linien"]
            aus["texte"] += g["texte"]
    elif art == "hoehenkote" and P:
        p = P[0]
        rechts = np.array([1.0, 0.0, 0.0])
        if blick is not None:
            r = np.cross(np.array([0.0, 0.0, 1.0]), np.asarray(blick, float))
            if np.linalg.norm(r) > 1e-9:
                rechts = r / np.linalg.norm(r)
        h = 0.03 * groesse
        spitze = p
        links, re = p + np.array([0, 0, h]) - 0.5 * h * rechts, p + np.array([0, 0, h]) + 0.5 * h * rechts
        aus["linien"] = [(spitze, links), (spitze, re), (links, re),
                         (p + np.array([0, 0, h]), p + np.array([0, 0, h]) + 0.15 * groesse * rechts)]
        text = bem.text or masstext(float(p[2]) - float(einst.hoehen_bezug), einheit, nk, vorzeichen=True)
        aus["texte"] = [(p + np.array([0, 0, 1.4 * h]) + 0.075 * groesse * rechts, text)]
        aus["punkte"] = [p]
    elif art == "winkel" and len(P) >= 3:
        a, b, c = P[0], P[1], P[2]
        u, w = a - b, c - b
        nu, nw = np.linalg.norm(u), np.linalg.norm(w)
        if nu > 1e-15 and nw > 1e-15:
            u, w = u / nu, w / nw
            r = bem.versatz if bem.versatz is not None else 0.1 * groesse
            phi = math.radians(winkel(a, b, c))
            n = np.cross(u, w)
            nn = np.linalg.norm(n)
            if nn > 1e-12:
                n = n / nn
                w2 = np.cross(n, u)                                # in der Ebene senkrecht zu u
                bogen = [b + r * (math.cos(t) * u + math.sin(t) * w2) for t in np.linspace(0.0, phi, 17)]
                aus["linien"] = [(bogen[i], bogen[i + 1]) for i in range(16)]
                aus["linien"] += [(b, b + 1.15 * r * u), (b, b + 1.15 * r * w)]
                mitte = b + 1.3 * r * (math.cos(phi / 2) * u + math.sin(phi / 2) * w2)
                aus["texte"] = [(mitte, bem.text or f"{math.degrees(phi):.{max(0, nk - 2)}f}°")]
            else:
                aus["texte"] = [(b, bem.text or f"{math.degrees(phi):.1f}°")]
            aus["punkte"] = [a, b, c]
    elif art == "radius" and len(P) >= 2:
        if len(P) >= 3:
            r, z = kreis_aus_drei(P[0], P[1], P[2])
            p = P[0]
        else:
            z, p = P[0], P[1]
            r = float(np.linalg.norm(p - z))
        aus["linien"] = [(z, p)]
        e = (p - z) / r if r > 1e-15 else np.zeros(3)
        s2 = 0.03 * groesse
        aus["linien"] += [(z - s2 * np.array([1, 0, 0]), z + s2 * np.array([1, 0, 0])),
                          (z - s2 * np.array([0, 1, 0]), z + s2 * np.array([0, 1, 0]))]
        aus["texte"] = [(z + 0.5 * r * e + s2 * np.array([0, 0, 1]), bem.text or "R " + masstext(r, einheit, nk))]
        aus["punkte"] = [z, p]
    return aus


def messung_geometrie(art: str, punkte, einst: BemassungEinstellung, groesse: float, blick=None) -> dict:
    """Die vorübergehende Zeichnung einer Messung (wie ein Maß, aber ohne Objekt)."""
    P = [list(map(float, p)) for p in punkte]
    if art == "abstand" and len(P) >= 2:
        return geometrie(Bemassung("Messung", "linear", P[:2]), einst, groesse, blick)
    if art == "winkel" and len(P) >= 3:
        return geometrie(Bemassung("Messung", "winkel", P[:3]), einst, groesse, blick)
    if art == "radius" and len(P) >= 2:
        return geometrie(Bemassung("Messung", "radius", P), einst, groesse, blick)
    if art == "koordinaten" and P:
        p = np.asarray(P[0])
        s = 0.03 * groesse
        return {"linien": [(p - s * np.array([1, 0, 0]), p + s * np.array([1, 0, 0])),
                           (p - s * np.array([0, 1, 0]), p + s * np.array([0, 1, 0])),
                           (p - s * np.array([0, 0, 1]), p + s * np.array([0, 0, 1]))],
                "texte": [(p + s * np.array([1, 1, 1]), messung_text("koordinaten", P, einst.einheit, einst.nachkomma).replace("Punkt ", ""))],
                "punkte": [p]}
    if art == "flaeche" and len(P) >= 3:
        A, S = polygonflaeche(P)
        ring = [np.asarray(p) for p in P]
        return {"linien": [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))],
                "texte": [(S, f"A = {A:.4f} m²")], "punkte": [S]}
    return {"linien": [], "texte": [], "punkte": []}
