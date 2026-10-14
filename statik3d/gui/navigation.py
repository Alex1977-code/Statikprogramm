"""Rechnung der Navigation in der 3D-Ansicht (Ansichtspaket A, 14.10.2026).

Reine Rechnung ohne Qt und ohne VTK, damit sie sich ohne Fenster pruefen
laesst (tests/test_ansicht_gizmo.py). Das Konzept stammt aus ediBIM
(Achsen-Gizmo nach Blender-Vorbild, Drehpunkt am angeklickten Punkt,
Umschalter perspektivisch/orthogonal); uebernommen sind Bedienregeln und
Verfahren, kein Code.

* :func:`gizmo_punkte` legt die sechs Achsenenden des Gizmos auf die
  Zeichenflaeche, hinterstes zuerst; :func:`zeichenfolge` ordnet die Linien
  zu den positiven Enden mit ein.
* :func:`zug_drehung` macht aus einem Zug am Gizmo eine Kameradrehung.
* :func:`drehen_um_punkt` dreht Kamera und Blickziel starr um einen Punkt -
  um die Hochachse Z der Welt und um die waagerechte Querachse der Kamera, mit
  einer weichen Bremse an den Polen (Draufsicht, Untersicht).
* :func:`blick_aus` stellt die Blickrichtung aus einer Achsrichtung ein und
  laesst Blickziel und Abstand, wie sie sind.
* :func:`parallelmassstab` / :func:`abstand_aus_massstab`: Umschalten
  zwischen Perspektive und Parallelprojektion bei gleicher Bildgroesse in der
  Zielebene.

Das Programm rechnet mit z nach oben (Benutzerhandbuch, RFEM-Import). Die
Draufsicht schaut darum von +Z nach unten (Blick in -Z), mit X nach rechts
und Y nach oben im Bild.
"""
from __future__ import annotations

import math

import numpy as np

#: Hochachse der Welt: um sie dreht das Ziehen nach links und rechts
WELT_OBEN = np.array([0.0, 0.0, 1.0])

#: Abstand der Blickrichtung zu den Polen [rad] (ediBIM: 0,08 rad, etwa 4,6 Grad).
#: Genau senkrecht wird die Querachse der Kamera unbestimmt, und das Bild
#: flackert beim Weiterziehen von einer Seite auf die andere.
POL_RAND = 0.08
#: Groesster Neigeschritt einer einzelnen Mausbewegung [Grad]: ein Sprung
#: (Fenster verlassen und an anderer Stelle wieder hinein) kippt sonst in einem
#: Schritt ueber den Pol
NEIGE_MAX = 57.0
#: Drehung je Zug ueber die ganze Breite (Hoehe) der Ansicht [Grad] - so viel wie
#: der Trackball von VTK (MotionFactor 10: 20 x 10 Grad), mit dem bis zum
#: 14.10.2026 gedreht wurde; das Gefuehl bleibt
GRAD_JE_ANSICHT = 200.0

#: Achsenenden: (Name, Achse, Vorzeichen, Richtung vom Blickziel zur Kamera)
ACHSEN_ENDEN = (
    ("+x", "x", 1, (1.0, 0.0, 0.0)), ("-x", "x", -1, (-1.0, 0.0, 0.0)),
    ("+y", "y", 1, (0.0, 1.0, 0.0)), ("-y", "y", -1, (0.0, -1.0, 0.0)),
    ("+z", "z", 1, (0.0, 0.0, 1.0)), ("-z", "z", -1, (0.0, 0.0, -1.0)),
)

#: Bildoben je Blickrichtung des Gizmos: an den Polen (Draufsicht, Untersicht)
#: ist die Drehung um die Blickachse sonst nicht festgelegt. Wie bisher im
#: Programm (MainWindow.BLICKRICHTUNGEN): Draufsicht mit Y oben, Untersicht mit
#: -Y oben (X bleibt rechts), alle Seitenansichten mit Z oben.
OBEN_FUER = {"+x": (0.0, 0.0, 1.0), "-x": (0.0, 0.0, 1.0),
             "+y": (0.0, 0.0, 1.0), "-y": (0.0, 0.0, 1.0),
             "+z": (0.0, 1.0, 0.0), "-z": (0.0, -1.0, 0.0)}

#: Klartext je Achsenende fuer Hinweis und Statuszeile
NAMEN = {"+x": "Ansicht von +X", "-x": "Ansicht von −X", "+y": "Ansicht von +Y",
         "-y": "Ansicht von −Y (Vorderansicht)", "+z": "Draufsicht (von +Z)",
         "-z": "Untersicht (von −Z)"}


def _einheit(v) -> np.ndarray | None:
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return None if n < 1e-12 else v / n


def _drehung(achse, winkel: float) -> np.ndarray:
    """Drehmatrix um ``achse`` (Einheitsvektor) um ``winkel`` [rad], rechtsdrehend."""
    k = np.asarray(achse, float)
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + math.sin(winkel) * K + (1.0 - math.cos(winkel)) * (K @ K)


# --------------------------------------------------------------------------
# Gizmo
# --------------------------------------------------------------------------
def gizmo_punkte(R, mx: float, my: float, radius: float) -> list:
    """Die sechs Achsenenden auf der Zeichenflaeche, **hinterstes zuerst**.

    ``R`` ist die Drehung Welt -> Kamera (3 x 3, Zeilen: Bild rechts, Bild
    oben, zum Betrachter - die Ansichtsmatrix von VTK). Rueckgabe je Ende ein
    dict mit ``name`` ("+x" …), ``achse``, ``vorzeichen``, ``x``/``y`` in
    Bildpunkten (y nach unten wie in Qt) und ``tiefe`` (groesser = naeher am
    Betrachter). Gezeichnet in dieser Reihenfolge, verdecken die vorderen
    Kugeln die hinteren.
    """
    R = np.asarray(R, float)
    aus = []
    for name, achse, vz, r in ACHSEN_ENDEN:
        b = R @ np.asarray(r, float)
        aus.append({"name": name, "achse": achse, "vorzeichen": vz,
                    "x": float(mx + b[0] * radius), "y": float(my - b[1] * radius),
                    "tiefe": float(b[2])})
    aus.sort(key=lambda p: p["tiefe"])
    return aus


def zeichenfolge(punkte) -> list:
    """Zeichenreihenfolge, hinterstes zuerst: (\"linie\", Achse) steht jeweils
    direkt vor der Kugel ihres positiven Endes, (\"ende\", Name) ist eine Kugel.

    Die Linie rueckt so in den Tiefenrang ihrer Kugel. Das ist ohne Zerlegen
    der Linien richtig, weil die Achsen senkrecht aufeinander stehen: zwei
    Enden auf derselben Tiefenseite liegen im Bild stumpfwinklig zueinander,
    und Enden auf verschiedenen Seiten trennt die Mitte (Tiefe 0) - die
    Ueberlegung aus ediBIM (gizmo-ansicht.ts, zeichenFolge)."""
    folge = []
    for p in punkte:
        if p["vorzeichen"] > 0:
            folge.append(("linie", p["achse"]))
        folge.append(("ende", p["name"]))
    return folge


def ende_unter(punkte, x: float, y: float, kugel_r: float) -> str:
    """Das Achsenende unter dem Bildpunkt (x, y) - das vorderste, wenn sich
    Kugeln ueberdecken; "" ausserhalb jeder Kugel."""
    for p in reversed(list(punkte)):
        if (p["x"] - x) ** 2 + (p["y"] - y) ** 2 <= kugel_r ** 2:
            return p["name"]
    return ""


def zug_drehung(dx: float, dy: float, durchmesser: float) -> tuple:
    """Kameradrehung (Azimut, Neigung) in Grad aus einem Zug am Gizmo.

    Ein Zug ueber den Durchmesser des Gizmos dreht um 180 Grad - das Gizmo
    folgt damit etwa wie eine Kugel unter dem Finger. Vorzeichen wie beim
    Ziehen in der Ansicht: Maus nach rechts dreht das Modell nach rechts (die
    Kamera nach links), Maus nach unten zeigt mehr von oben."""
    je = 180.0 / durchmesser if durchmesser > 1 else 0.0
    return -float(dx) * je, float(dy) * je


def ansicht_drehung(dx: float, dy: float, breite: float, hoehe: float) -> tuple:
    """Kameradrehung (Azimut, Neigung) in Grad aus einem Zug in der Ansicht
    (mittlere Taste): :data:`GRAD_JE_ANSICHT` je ganze Breite bzw. Hoehe."""
    az = -float(dx) * GRAD_JE_ANSICHT / breite if breite > 1 else 0.0
    ne = float(dy) * GRAD_JE_ANSICHT / hoehe if hoehe > 1 else 0.0
    return az, ne


# --------------------------------------------------------------------------
# Drehen um einen Punkt
# --------------------------------------------------------------------------
def polwinkel(blick) -> float:
    """Winkel der Blickrichtung zur Hochachse [rad]: 0 = nach oben geschaut,
    pi = senkrecht von oben (Draufsicht)."""
    b = _einheit(blick)
    if b is None:
        return 0.5 * math.pi
    return math.acos(max(-1.0, min(1.0, float(b @ WELT_OBEN))))


def gebremste_neigung(phi: float, schritt: float, rand: float = POL_RAND) -> float:
    """Der Polwinkel nach einer Neigung um ``schritt`` [rad], weich gebremst.

    Innerhalb von [rand, pi - rand] geht der Schritt voll durch. Wer an den
    Rand stoesst, bleibt genau am Rand stehen - nicht ganz oder gar nicht
    (das flackerte in ediBIM bei jeder kleinen Bewegung am Anschlag). Steht
    die Kamera schon jenseits des Randes (die Draufsicht aus dem Gizmo liegt
    genau am Pol), geht jeder Schritt weg vom Pol voll durch, keiner weiter
    hin."""
    lo, hi = rand, math.pi - rand
    neu = phi + schritt

    def draussen(w):
        return max(lo - w, w - hi, 0.0)
    if draussen(neu) <= 0.0:
        return neu
    if draussen(neu) < draussen(phi):
        return neu                          # zurueck zum erlaubten Bereich
    if draussen(phi) > 0.0:
        return phi                          # schon am Pol: nicht weiter
    return min(max(neu, lo), hi)            # bis an den Rand, nicht darueber


def drehen_um_punkt(pos, fokus, oben, punkt, azimut_grad: float, neigung_grad: float,
                    rand: float = POL_RAND) -> tuple:
    """Kamera und Blickziel **starr** um ``punkt`` drehen.

    Erst um die Hochachse Z durch ``punkt`` (``azimut_grad``, rechtsdrehend),
    dann um die waagerechte Querachse der Kamera (``neigung_grad``; positiv
    hebt die Kamera, sie schaut mehr von oben, wie Elevation in VTK). Weil
    dieselbe Drehung auf Standort, Blickziel und Bildoben wirkt, bleibt der
    Punkt im Bild an derselben Stelle, der Abstand Kamera - Blickziel bleibt,
    und das Blickziel springt nicht auf den Punkt. Die Neigung ist an den Polen
    weich gebremst (:func:`gebremste_neigung`). Rueckgabe (Standort, Blickziel,
    Bildoben) als Felder.
    """
    P = np.asarray(pos, float)
    F = np.asarray(fokus, float)
    U = np.asarray(oben, float)
    C = np.asarray(punkt, float)
    neigung_grad = max(-NEIGE_MAX, min(NEIGE_MAX, float(neigung_grad)))
    Rz = _drehung(WELT_OBEN, math.radians(float(azimut_grad)))
    p, f, u = Rz @ (P - C), Rz @ (F - C), Rz @ U
    blick = _einheit(f - p)
    if blick is None:
        return P.copy(), F.copy(), U.copy()
    # Querachse: waagerecht (senkrecht zu Blick und Hochachse) - dann aendert
    # die Drehung um sie den Polwinkel genau um ihren Winkel. Am Pol (Blick
    # senkrecht) ist sie unbestimmt; dort gilt die Querachse aus Bildoben.
    quer = _einheit(np.cross(blick, WELT_OBEN))
    if quer is None or float(np.linalg.norm(np.cross(blick, WELT_OBEN))) < 1e-6:
        quer = _einheit(np.cross(blick, u))
    if quer is not None and neigung_grad:
        phi = polwinkel(blick)
        phi_neu = gebremste_neigung(phi, math.radians(neigung_grad), rand)
        # Drehung um +quer um t verringert den Polwinkel um t
        R = _drehung(quer, phi - phi_neu)
        p, f, u = R @ p, R @ f, R @ u
    return C + p, C + f, u


def blick_aus(name: str, pos, fokus) -> tuple:
    """Blick aus einer Achsrichtung ("+x" … "-z"): Blickziel und Abstand
    bleiben, nur die Richtung wechselt (ein Klick auf das Gizmo passt nicht
    ein). Rueckgabe (Standort, Blickziel, Bildoben)."""
    richtung = dict((n, r) for n, _a, _v, r in ACHSEN_ENDEN)[name]
    F = np.asarray(fokus, float)
    d = float(np.linalg.norm(np.asarray(pos, float) - F))
    if d < 1e-12:
        d = 1.0
    return F + np.asarray(richtung, float) * d, F.copy(), np.asarray(OBEN_FUER[name], float)


# --------------------------------------------------------------------------
# Perspektive und Parallelprojektion
# --------------------------------------------------------------------------
def parallelmassstab(abstand: float, blickwinkel_grad: float) -> float:
    """Halbe Bildhoehe in der Zielebene: so gross ist das perspektivische Bild
    im Abstand ``abstand`` - der Massstab der Parallelprojektion, der beim
    Umschalten dieselbe Bildgroesse gibt."""
    return float(abstand) * math.tan(math.radians(float(blickwinkel_grad)) / 2.0)


def abstand_aus_massstab(massstab: float, blickwinkel_grad: float) -> float:
    """Umkehrung von :func:`parallelmassstab`: der Abstand, in dem das
    perspektivische Bild so gross ist wie das parallele."""
    t = math.tan(math.radians(float(blickwinkel_grad)) / 2.0)
    return float(massstab) / t if t > 1e-12 else float(massstab)
