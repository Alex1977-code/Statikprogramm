"""Strukturspannung am Nahtuebergang nach IIW, Typ a (Vorgabe 11.2, Plan TP 5 B3).

Je Punkt der Nahtpolylinie (Nahtuebergang, ``WeldLine.points``): Referenzpunkte im Abstand 0,4 t und 1,0 t vom
Uebergang auf der Blechoberflaeche, senkrecht zur Naht, lineare Extrapolation auf den Uebergang:

    sigma_hs = 5/3 sigma(0,4 t) - 2/3 sigma(1,0 t)      (die IIW-Beiwerte 1,67 und 0,67 sind diese Brueche gerundet)

mit sigma = d . S . d, d der Richtung auf dem Blech senkrecht zur Naht. Die Geometrie liefert der Vertrag nur als
Polylinie und Blechdicke; auf welcher Seite des Uebergangs das Blech liegt, wird aus der Geometrie bestimmt: in der
Ebene senkrecht zur Naht schneidet ein kleiner Kreis um den Uebergang die Oberflaeche in zwei Aesten (Blech und
Nahtoberflaeche). Der Blechast ist der, dessen Oberflaeche von 0,05 t bis 1,0 t eben bleibt (Normalen innerhalb 10 Grad,
Punkte auf der Ebene) und unter dem der Werkstoff t tief ist (auf 20 %); die Nahtoberflaeche knickt innerhalb 1,0 t ab
(Ende der Kehlnahtflaeche, Ende der Ueberhoehung). Bis 02.10.2026 entschied allein die Tiefe 0,7 t laengs beider Aeste: bei
Kehlnaehten mit Schenkel unter 0,495 t lag dieser Punkt schon auf dem Anschlussblech, bei flachen Ueberhoehungen unter der
Ueberhoehung, und beide Aeste passten (kein Wert, Gutachten C2, G2-1). Ist kein Ast ueber 1,0 t eben (Blechende, Nachbarnaht,
starke Kruemmung), gaebe es keine Blechoberflaeche fuer die Referenzpunkte - vorher wurden sie still auf die Stirnflaeche gezogen
(G2-2). Ist es nicht eindeutig, gibt es keinen Wert, sondern eine Warnung - geraten wird nicht.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

_KREIS_RADIUS = 0.05          # in Blechdicken; klein gegen 0,4 t, gross gegen die Rundung der Abstandsfunktion
_KREIS_PROBEN = 720
_TIEFE_BEI = 0.7              # in Blechdicken: Mitte zwischen den Referenzpunkten
_EBEN_PROBEN = (0.05, 0.2, 0.4, 0.7, 1.0)   # in Blechdicken: Proben laengs des Asts fuer die Ebenheit
_EBEN_COS = float(np.cos(np.deg2rad(10.0)))  # Normalen innerhalb 10 Grad (Rohr: Radius ueber 5,7 t)
_EBEN_ABSTAND = 0.02          # in Blechdicken: Abstand der Proben von der Ebene am Uebergang
_TIEFE_TOLERANZ = 0.2         # Werkstofftiefe = t auf 20 %
_TIEFE_MAX = 3.0
BEIWERTE = (5.0 / 3.0, -2.0 / 3.0)
ABSTAENDE = (0.4, 1.0)


@dataclass
class Nahtpunkt:
    """Geometrie eines Punkts der Nahtpolylinie; ``ok`` False mit ``warnung``, wenn die Blechseite unklar ist."""
    position: np.ndarray
    ok: bool
    richtung: np.ndarray = field(default_factory=lambda: np.zeros(3))      # d, auf dem Blech von der Naht weg
    referenz: np.ndarray = field(default_factory=lambda: np.zeros((2, 3)))  # Punkte bei 0,4 t und 1,0 t
    normalen: np.ndarray = field(default_factory=lambda: np.zeros((2, 3)))  # aeussere Normalen dort
    tiefen: tuple = ()
    warnung: str = ""


def _tangenten(P: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(Punkte, Tangenten). Weniger als zwei Punkte: ValueError (eine leere Linie gab vorher einen IndexError, der den ganzen Vertragsweg
    abbrach, Gutachten C2, G2-3). Eine geschlossene Linie (letzter Punkt = erster) wird zyklisch behandelt: der doppelte Endpunkt
    entfaellt, und die Tangente am Stoss ist die mittlere der beiden Nachbarn statt zweier einseitiger (G2-4)."""
    P = np.asarray(P, float).reshape(-1, 3)
    if len(P) < 2:
        raise ValueError(f"Nahtpolylinie braucht mindestens zwei Punkte (Tangente), hat {len(P)}")
    groesse = max(float(np.ptp(P, axis=0).max()), 1e-300)
    geschlossen = len(P) >= 4 and float(np.linalg.norm(P[0] - P[-1])) <= 1e-9 * groesse
    if geschlossen:
        P = P[:-1]
        T = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
    else:
        T = np.empty_like(P)
        T[1:-1] = P[2:] - P[:-2]
        T[0] = P[1] - P[0]
        T[-1] = P[-1] - P[-2]
    return P, T / np.linalg.norm(T, axis=1)[:, None]


def _projizieren(geo, X: np.ndarray, schritte: int = 6) -> np.ndarray:
    """Punkte auf die Oberflaeche (Nullstelle des Abstands) ziehen; an ebenen Flaechen exakt nach einem Schritt."""
    X = np.array(X, float).reshape(-1, 3)
    for _ in range(schritte):
        a = geo.abstand(X)
        g = geo.gradient(X)
        X = X - (a / np.maximum(np.einsum("ij,ij->i", g, g), 1e-300))[:, None] * g
    return X


def _normale(geo, X: np.ndarray) -> np.ndarray:
    g = geo.gradient(np.asarray(X, float).reshape(-1, 3))
    return g / np.linalg.norm(g, axis=1)[:, None]


def _tiefe(geo, Q: np.ndarray, n: np.ndarray, t: float) -> float:
    """Werkstofftiefe unter Q laengs -n bis zum naechsten Austritt (inf, wenn nicht innerhalb _TIEFE_MAX t)."""
    tau = np.linspace(0.02 * t, _TIEFE_MAX * t, 300)
    a = geo.abstand(Q[None, :] - tau[:, None] * n[None, :])
    aussen = np.flatnonzero(a > 0.0)
    if not len(aussen):
        return float("inf")
    k = int(aussen[0])
    lo, hi = (tau[k - 1] if k > 0 else 0.0), tau[k]
    for _ in range(40):
        m = 0.5 * (lo + hi)
        if geo.abstand((Q - m * n)[None, :])[0] > 0.0:
            hi = m
        else:
            lo = m
    return float(0.5 * (lo + hi))


def nahtgeometrie(geo, punkte: np.ndarray, t: float) -> list[Nahtpunkt]:
    """Blechseite, Richtung und Referenzpunkte je Punkt der Nahtpolylinie (Einheiten wie die Geometrie, mm)."""
    P, T = _tangenten(np.asarray(punkte, float).reshape(-1, 3))
    rho = _KREIS_RADIUS * t
    th = np.linspace(0.0, 2.0 * np.pi, _KREIS_PROBEN, endpoint=False)
    aus = []
    for p0, tg in zip(P, T):
        e1 = np.cross(tg, [1.0, 0.0, 0.0] if abs(tg[0]) < 0.9 else [0.0, 1.0, 0.0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(tg, e1)

        def kreis(w):
            return p0 + rho * (np.cos(w)[..., None] * e1 + np.sin(w)[..., None] * e2)
        a = geo.abstand(kreis(th))
        s = a > 0.0
        wechsel = np.flatnonzero(s != np.roll(s, -1))
        if len(wechsel) != 2:
            aus.append(Nahtpunkt(p0, False, warnung=f"{len(wechsel)} statt 2 Oberflaechenaeste um den Nahtuebergang"))
            continue
        aeste = []
        for k in wechsel:
            lo, hi = th[k], th[k] + 2.0 * np.pi / _KREIS_PROBEN
            s_lo = bool(s[k])
            for _ in range(50):
                m = 0.5 * (lo + hi)
                if bool(geo.abstand(kreis(np.array([m])))[0] > 0.0) == s_lo:
                    lo = m
                else:
                    hi = m
            w = 0.5 * (lo + hi)
            aeste.append(np.cos(w) * e1 + np.sin(w) * e2)
        if float(aeste[0] @ aeste[1]) < -0.999:
            aus.append(Nahtpunkt(p0, False, warnung="Oberflaeche ohne Knick (Aeste gegenlaeufig): der Punkt liegt nicht auf einem Nahtuebergang"))
            continue
        tiefen, eben = [], []
        tau = np.array(_EBEN_PROBEN) * t
        for u in aeste:
            X0 = p0[None, :] + tau[:, None] * u[None, :]
            R = _projizieren(geo, X0)
            N = _normale(geo, R)
            eben.append(bool(np.all(N @ N[0] >= _EBEN_COS) and np.all(np.abs((R - R[0]) @ N[0]) <= _EBEN_ABSTAND * t)
                             and np.all(np.linalg.norm(R - X0, axis=1) <= _EBEN_ABSTAND * t + 1e-9 * t)))
            Q = _projizieren(geo, p0 + _TIEFE_BEI * t * u)[0]
            tiefen.append(_tiefe(geo, Q, _normale(geo, Q)[0], t))
        passt = [e and abs(d - t) <= _TIEFE_TOLERANZ * t for e, d in zip(eben, tiefen)]
        if sum(passt) != 1:
            tief_t = [abs(d - t) <= _TIEFE_TOLERANZ * t for d in tiefen]
            if sum(passt) == 0 and (not any(eben) or any(tt and not e for tt, e in zip(tief_t, eben))):
                grund = (f"weniger als 1,0 t ebene Blechoberflaeche senkrecht zur Naht (Blechende, Nachbarnaht oder starke Kruemmung); "
                         f"die Referenzpunkte 0,4 t und 1,0 t fehlen")
            elif sum(passt) == 0:
                grund = f"Werkstofftiefe unter dem ebenen Ast passt nicht zur Blechdicke (Tiefen {tiefen[0]:.2f} und {tiefen[1]:.2f} mm, Blechdicke {t:g} mm)"
            else:
                grund = f"Blechseite nicht eindeutig (beide Aeste eben, Werkstofftiefe {tiefen[0]:.2f} und {tiefen[1]:.2f} mm, Blechdicke {t:g} mm)"
            aus.append(Nahtpunkt(p0, False, tiefen=tuple(tiefen), warnung=grund))
            continue
        u = aeste[int(np.argmax(passt))]
        R = _projizieren(geo, p0[None, :] + np.array(ABSTAENDE)[:, None] * t * u[None, :])
        n = _normale(geo, R)
        d = u[None, :] - np.einsum("j,ij->i", u, n)[:, None] * n
        d /= np.linalg.norm(d, axis=1)[:, None]
        aus.append(Nahtpunkt(p0, True, richtung=d, referenz=R, normalen=n, tiefen=tuple(tiefen)))
    return aus


def normalspannung(S: np.ndarray, d: np.ndarray) -> np.ndarray:
    """d . S . d fuer Voigt-Spannungen S (n,6) (xx, yy, zz, xy, yz, xz) und Richtungen d (n,3)."""
    S = np.asarray(S, float).reshape(-1, 6)
    d = np.asarray(d, float).reshape(-1, 3)
    return (S[:, 0] * d[:, 0] ** 2 + S[:, 1] * d[:, 1] ** 2 + S[:, 2] * d[:, 2] ** 2
            + 2.0 * (S[:, 3] * d[:, 0] * d[:, 1] + S[:, 4] * d[:, 1] * d[:, 2] + S[:, 5] * d[:, 0] * d[:, 2]))


def strukturspannungen(nahtpunkte: list[Nahtpunkt], spannung, einruecken: float) -> list[tuple[Nahtpunkt, float, float, float]]:
    """(Nahtpunkt, sigma_hs, sigma(0,4t), sigma(1,0t)) fuer alle gueltigen Punkte. ``spannung(P) -> (n,6)``;
    die Referenzpunkte werden um ``einruecken`` (mm) laengs der Innennormalen in den Werkstoff gerueckt, damit die
    Punktsuche eine aktive Zelle findet (wie die Oberflaechenpunkte des Vertragswegs)."""
    gut = [q for q in nahtpunkte if q.ok]
    if not gut:
        return []
    R = np.concatenate([q.referenz - einruecken * q.normalen for q in gut])
    D = np.concatenate([q.richtung for q in gut])
    try:
        sig = normalspannung(spannung(R), D).reshape(len(gut), 2)
    except ValueError:
        # ein Referenzpunkt ausserhalb der aktiven Zellen (Punktsuche wirft) verwarf vorher das ganze Ergebnis des Lastfalls samt
        # Oberflaechenspannungen (Gutachten C2, G2-7); jetzt Punkt fuer Punkt, die betroffenen bleiben mit Warnung ohne Wert
        zeilen, behalten = [], []
        for i, q in enumerate(gut):
            try:
                zeilen.append(normalspannung(spannung(R[2 * i:2 * i + 2]), D[2 * i:2 * i + 2]))
                behalten.append(q)
            except ValueError as ex:
                q.ok = False
                q.warnung = f"Referenzpunkt ausserhalb der Zellen ({ex})"
        if not behalten:
            return []
        gut, sig = behalten, np.array(zeilen).reshape(len(behalten), 2)
    hs = sig @ np.array(BEIWERTE)
    return [(q, float(h), float(s[0]), float(s[1])) for q, h, s in zip(gut, hs, sig)]


__all__ = ["Nahtpunkt", "nahtgeometrie", "normalspannung", "strukturspannungen", "BEIWERTE", "ABSTAENDE"]
