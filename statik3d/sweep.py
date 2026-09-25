"""
Sweep: Grundflaeche mal Weg - Hexaeder und Keile statt Tetraeder.

Warum (Auftrag Sechsflaechner, 20.09.2026): der lineare Tetraeder ist ein
schlechtes Element, und ein Teil davon ist Abzaehlung. Am Drehlager stehen
645 934 Tetraeder auf 158 586 Knoten, 4,07 Elemente je Knoten; Volumentreue
ist eine Bedingung je Element, also 4,07 Bedingungen auf 3 Verschiebungen je
Knoten - das Netz versteift sich selbst, und beim Fliessen (volumentreu) erst
recht. Ein Hexaedernetz hat rund ein Element je Knoten, ein Keilnetz rund
zwei; beide sperren nicht.

Der Weg hier ist der uebliche erste Schritt zum hexaederdominanten Netz: das
**Sweepen**. Ein Koerper, der sich als Grundflaeche mal Weg beschreiben
laesst - Platte, Ring, Flansch, Rippe, Lasche mit Bohrungen: fast alles, was
aus einer Skizze extrudiert wurde -, bekommt ein Netz auf der Grundflaeche und
wird laengs des Weges in Lagen durchgezogen. Vierecke der Grundflaeche werden
Hexaeder (``hex8``), Dreiecke Keile (``pent6``); beide kann der Loeser, der
Kontakt (alle Knoten einer Seite sind Eckknoten) und die Netzguete.

Erkannt wird ein Koerper als sweepbar, wenn

* zwei seiner Randflaechen (Grund und Deckel) **eben** sind und die eine die
  um einen Vektor t verschobene Kopie der anderen ist - Aussenrand und alle
  Oeffnungen, Punkt fuer Punkt,
* jede weitere Randflaeche eine **Wand** aus vier Linien ist: eine Linie des
  Grundes, ihre Kopie im Deckel und zwei gerade **Mantellinien** mit dem
  Vektor t (ebene Wand oder Bohrungswand - der Mantel einer Bohrung ist in
  RFEM aus zwei solchen Vierseitflaechen gebaut).

Das Netz der Grundflaeche kommt aus dem vorhandenen Flaechenvernetzer
(:func:`mesher3d.flaechennetz`, Dreiecke); benachbarte Dreiecke werden zu
Vierecken **gepaart**, wo das Viereck gut geformt ist (gierig nach Guete),
der Rest bleibt Dreieck. So passt das Netz Knoten fuer Knoten zu einem
Tetraeder-Nachbarn, der dieselbe Flaeche vernetzt - und die Waende werden
ihm als **vorgegebene Flaechennetze** mitgegeben (``model.flaechennetze``),
denn ein freies Dreiecksnetz auf der Wand traefe die Lagenpunkte nicht.

Was nicht sweepbar ist, geht wie bisher an :func:`mesher3d.mesh_koerper_frei`.
Uebergangselemente (Pyramiden) und das Zerlegen in sweepbare Bloecke sind
die naechsten Schritte; siehe ``Vernetzer/UEBERGABE-VON-FABLE.md``.
"""
from __future__ import annotations

import numpy as np

from .model import Model, Flaeche, Volumenkoerper, _linienzug_punkte

#: Wenigstens so viele Lagen ueber den Weg, wenn der Koerper elastisch bleibt
#: und keine Mantellinie eine Vorgabe traegt. Der hex8 mit inkompatiblen Moden
#: (elements/solid.py) traegt Biegung **elastisch** mit einer Lage (Kragplatte
#: 1 x 0,2 x 0,05 m, zwei Lagen: 97,6 % der Balkenloesung, 20.09.2026).
LAGEN_MIN = 2

#: Wenigstens so viele Lagen, wenn Fliessen gerechnet wird
#: (``model.plastizitaet.an``). Gemessen von der Loeser-Sitzung am 21.09.2026
#: (Zweig a4a7d91; Kragtraeger 200 x 200 mm, 1,0 m, Endmoment 1,20 M_el,
#: fy = 235 N/mm2, Verfestigung 2 %; die Randfaser traegt elastisch 282 N/mm2
#: und muss fliessen, die plastische Zone reicht bis 77,5 % der halben Hoehe):
#:
#:     hex8, 1 Lage    0 von  5 Elementen fliessen   u_x 1,333 mm
#:     hex8, 2 Lagen   0 von 10                      u_x 1,324 mm
#:     hex8, 3 Lagen  10 von 15                      u_x 1,589 mm
#:     hex8, 4 Lagen   8 von 20                      u_x 1,710 mm
#:     hex8, 6 Lagen  12 von 30                      u_x 1,888 mm
#:     hex8, 8 Lagen  16 von 40                      u_x 1,949 mm
#:
#: Mit einer und mit zwei Lagen fliesst **nichts**, obwohl der Querschnitt
#: plastifiziert - die Plastizitaet wertet an den Gausspunkten aus, und deren
#: aeusserster liegt bei einer Lage auf 57,7 %, bei zwei auf 78,9 % der halben
#: Hoehe. Die Verformung liegt mit einer Lage um 32 % unter der mit acht. Vier
#: Lagen sind die Untergrenze, sechs bis acht das Richtige - das stellt der
#: Anwender ueber die Kantenlaenge ein. Elastische Bauteile zahlen den Preis
#: nicht mit: die Zahl greift nur, wenn Fliessen eingeschaltet ist.
LAGEN_MIN_PLASTISCH = 4

#: Kleinste Formguete (skalierte Jacobi-Determinante) eines Vierecks aus zwei
#: Dreiecken, damit es gepaart wird. Gemessen an der Platte 1 x 0,6 x 0,2 m
#: mit Bohrung, h = 50 mm (20.09.2026): mit 0,3 werden 90 % der Dreiecke zu
#: Vierecken, kleinste Vierecksguete 0,30, mittlere 0,84.
VIERECK_GUETE_MIN = 0.3

#: Relative Toleranz fuer „derselbe Punkt" beim Vergleich von Grund und Deckel
TOL_REL = 1e-6


# --------------------------------------------------------------------------
# Erkennung
# --------------------------------------------------------------------------
#: Wenigstens so viele Randflaechen hat ein sweepbarer Koerper: zwei Kappen
#: und zwei Waende. Bis zum 21.09.2026 waren es fuenf - damit fiel jeder
#: **Zylinder** (zwei Kreise, zwei Halbmantel-Flaechen aus RFEM) an die
#: Tetraeder; am Drehlager haben 48 von 108 Koerpern vier Flaechen (Zaehlung
#: der Loeser-Sitzung), darunter die Bolzen, Stifte und Achsen.
KAPPEN_MIN_FLAECHEN = 4

#: Hoechstens so viele Schnitte hintereinander beim Zerlegen (zerlegen):
#: ein Fussabdruck auf dem Ergebnis eines Fussabdrucks - Buchse auf Nabe auf
#: Platte. Mehr Tiefe hat an den Pruefkoerpern nichts gebracht und kostet je
#: Stufe einen Erkennungsdurchlauf ueber alle Flaechenpaare.
ZERLEGEN_TIEFE = 2
#: Zeit- und Versuchsbudget fuer das Zerlegen eines Koerpers. Ohne Grenze
#: probierte der Fussabdruck an V30 des Drehlagers (144 Flaechen, 12
#: Oeffnungen je Kappe) 255 s lang Schnitte durch, an V34 217 s - je zwei
#: Erkennungen auf ueber hundert Flaechen je Versuch - und fand nichts
#: (gemessen 23.09.2026). Und sweepbar() fragt vor dem Vernetzen noch einmal.
ZERLEGEN_ZEIT_S = 20.0
ZERLEGEN_VERSUCHE = 40


def _ringpunkte(model: Model, f, teilung: int = 24) -> list:
    """[Aussenrand, Oeffnung 1, ...] als Punktfolgen (abgetastet)."""
    aus = [np.asarray(f.randpunkte(model, teilung), float)]
    aus += [np.asarray(P, float) for P in f.oeffnungspunkte(model, teilung)]
    return aus


def _schleifenpunkte(model: Model, schleife: list, teilung: int = 24) -> np.ndarray:
    """Ein geschlossener Linienzug als abgetastete Punktfolge."""
    return np.asarray(_linienzug_punkte(model, list(schleife), teilung), float).reshape(-1, 3)


def _abbildung_finden(A: np.ndarray, B: np.ndarray, tol: float) -> "tuple | None":
    """Die Aehnlichkeit, die den Aussenrand des Grundes auf den des Deckels
    legt: ``("v", Mittelpunkt c, Massstab k, Verschiebung t)`` mit
    ``B = c + (A - c)*k + t``.

    Reine Verschiebung ist der Fall k = 1 - der haeufige, und er wird zuerst
    geprueft. Ein **verjuengter Zug** (Kegelstumpf, konische Rippe, Nabe mit
    Anzug) hat k != 1: der Deckel ist dieselbe Figur, nur kleiner oder
    groesser. Der Massstab folgt aus den mittleren Abstaenden zum Schwerpunkt;
    weil beide Kappen eben und **parallel** sind, genuegt das. Stehen sie
    schief zueinander, ist es ein Drehkoerper - siehe
    :func:`_abbildung_drehung`.
    """
    if len(A) < 3 or len(B) < 3:
        return None
    cA, cB = A.mean(axis=0), B.mean(axis=0)
    rA = float(np.linalg.norm(A - cA, axis=1).mean())
    rB = float(np.linalg.norm(B - cB, axis=1).mean())
    if rA <= tol:
        return None
    return ("v", cA, rB / rA, cB - cA)


def _abbildung_drehung(A: np.ndarray, B: np.ndarray, nA: np.ndarray, nB: np.ndarray,
                       tol: float) -> "tuple | None":
    """Die Drehung, die den Grund auf den Deckel legt:
    ``("d", Achspunkt a, Achsrichtung d, Winkel phi)``.

    Ein **Drehkoerper** (Revolve) entsteht, indem ein ebenes Profil um eine
    Achse gedreht wird: Rohrbogen, Ringsegment, Kegelrad-Ausschnitt. Seine
    beiden Kappen sind eben - aber nicht parallel, sondern um denselben
    Winkel gegeneinander verdreht wie der Koerper selbst. Beide Kappenebenen
    **enthalten die Achse**; daraus folgt sie:

    * die Achsrichtung steht auf beiden Kappennormalen senkrecht, also
      ``d = nA x nB``,
    * der Achspunkt liegt in beiden Kappenebenen - zwei Gleichungen, die
      dritte ist die Wahl des Lotpunktes zum Schwerpunktmittel,
    * der Winkel ist der zwischen den Normalen, im Vorzeichen von d.

    Ist ``nA`` parallel zu ``nB``, gibt es keine Drehung (dann ist es eine
    Verschiebung oder ein verjuengter Zug). None, wenn keine Drehung passt.
    """
    nA = np.asarray(nA, float) / max(float(np.linalg.norm(nA)), 1e-300)
    nB = np.asarray(nB, float) / max(float(np.linalg.norm(nB)), 1e-300)
    d = np.cross(nA, nB)
    ld = float(np.linalg.norm(d))
    if ld < 1e-9:                            # Kappen parallel - keine Drehung
        return None
    d = d / ld
    cA, cB = A.mean(axis=0), B.mean(axis=0)
    # Achspunkt: in beiden Kappenebenen, senkrecht unter dem Schwerpunktmittel
    M = np.vstack([nA, nB, d])
    rechts = np.array([float(nA @ cA), float(nB @ cB), float(d @ (0.5 * (cA + cB)))])
    try:
        a = np.linalg.solve(M, rechts)
    except np.linalg.LinAlgError:
        return None
    # Winkel: die Normalen gegeneinander, im Vorzeichen der Achse
    phi = float(np.arctan2(ld, float(nA @ nB)))
    for vorz in (1.0, -1.0):
        abb = ("d", a, d, vorz * phi)
        if float(np.linalg.norm(_abbilden(A[:1], abb)[0] - _naechster(B, _abbilden(A[:1], abb)[0]))) <= tol:
            return abb
    return ("d", a, d, phi)


def _naechster(B: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Der Punkt aus B, der p am naechsten liegt."""
    i = int(np.argmin(np.linalg.norm(np.asarray(B, float) - np.asarray(p, float), axis=1)))
    return np.asarray(B, float)[i]


def _drehmatrix(d: np.ndarray, w: float) -> np.ndarray:
    """Drehmatrix um die Einheitsachse ``d`` mit dem Winkel ``w`` (Rodrigues)."""
    d = np.asarray(d, float)
    K = np.array([[0.0, -d[2], d[1]], [d[2], 0.0, -d[0]], [-d[1], d[0], 0.0]])
    return np.eye(3) + np.sin(w) * K + (1.0 - np.cos(w)) * (K @ K)


def _abbilden(P: np.ndarray, abb: tuple, s: float = 1.0) -> np.ndarray:
    """Die Punkte ``P`` unter der Abbildung, zum Anteil ``s`` des Weges
    (s = 0 der Grund, s = 1 der Deckel).

    ``("v", c, k, t)``: Massstab und Verschiebung gehen linear mit.
    ``("d", a, d, phi)``: gedreht wird um den Anteil des Winkels - so liegen
    die Zwischenlagen auf dem Bogen und nicht auf der Sehne.
    """
    P = np.asarray(P, float).reshape(-1, 3)
    if abb[0] == "d":
        _tag, a, d, phi = abb
        R = _drehmatrix(d, float(phi) * float(s))
        a = np.asarray(a, float)
        return (P - a) @ R.T + a
    _tag, c, k, t = abb
    c = np.asarray(c, float)
    ks = 1.0 + (float(k) - 1.0) * float(s)
    return c + (P - c) * ks + np.asarray(t, float) * float(s)


def abbildung_von(erk: dict) -> tuple:
    """Die Abbildung des Erkennungsergebnisses - Rueckfall auf reine
    Verschiebung, damit aelterer Code und gespeicherte Ergebnisse tragen."""
    abb = erk.get("abb")
    if abb is not None:
        return abb
    return ("v", np.zeros(3), 1.0, np.asarray(erk["t"], float))


def massstab_von(abb: tuple) -> float:
    """Der Massstab der Abbildung (1 bei Verschiebung und Drehung)."""
    return float(abb[2]) if abb[0] == "v" else 1.0


def richtung_von(P: np.ndarray, abb: tuple) -> np.ndarray:
    """Die Richtung, in die der Sweep an der Grundflaeche losgeht - der
    Anfangsvektor der Abbildung. Bei einer Drehung ist das die Tangente, nicht
    die Sehne: fuer einen Halbkreis waere die Sehne null."""
    P = np.asarray(P, float).reshape(-1, 3)
    v = (_abbilden(P, abb, 1e-4) - P).mean(axis=0)
    ln = float(np.linalg.norm(v))
    if ln > 0:
        return v / ln
    return np.array([0.0, 0.0, 1.0])


def _umringmitte(P: np.ndarray) -> np.ndarray:
    """Der **Flaechenschwerpunkt** des geschlossenen Umrings.

    Der Mittelwert der Ecken taugt dafuer nicht: eine zusaetzliche Ecke
    mitten auf einer geraden Kante aendert ihn, obwohl sie die Figur nicht
    aendert. Genau das passiert nach einem Schnitt - der Deckel einer Platte
    traegt dann die zwei Ecken der Schnittlinie, der Grund nicht, und die
    Kappen galten nicht mehr als deckungsgleich (22.09.2026).

    Gerechnet als Faecher um den Eckenmittelwert mit vorzeichenbehafteten
    Dreiecksflaechen laengs der Newell-Normalen - ohne Ausgleichsebene, denn
    das hier laeuft in :func:`erkennen` ueber jedes Flaechenpaar.
    """
    P = np.asarray(P, float).reshape(-1, 3)
    if len(P) < 3:
        return P.mean(axis=0) if len(P) else np.zeros(3)
    m = P.mean(axis=0)
    Q = P - m
    R = np.roll(Q, -1, axis=0)
    kreuz = np.cross(Q, R)
    N = kreuz.sum(axis=0)
    laenge = float(np.linalg.norm(N))
    if laenge <= 1e-30:
        return m
    a2 = kreuz @ (N / laenge)               # zweifache signierte Dreiecksflaechen
    A2 = float(a2.sum())
    if abs(A2) <= 1e-30:
        return m
    return m + ((Q + R) * a2[:, None]).sum(axis=0) / (3.0 * A2)


def _abstand_zum_zug(P: np.ndarray, Q: np.ndarray, geschlossen: bool) -> np.ndarray:
    """Abstand jedes Punktes von ``P`` zum Linienzug durch ``Q`` - zu den
    **Strecken**, nicht zu den Stuetzpunkten."""
    P = np.asarray(P, float).reshape(-1, 3)
    Q = np.asarray(Q, float).reshape(-1, 3)
    if len(Q) == 1:
        return np.linalg.norm(P - Q[0], axis=1)
    A = Q if geschlossen else Q[:-1]
    B = np.roll(Q, -1, axis=0) if geschlossen else Q[1:]
    d = B - A
    l2 = np.einsum("ij,ij->i", d, d)
    rel = P[:, None, :] - A[None, :, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.einsum("nmj,mj->nm", rel, d) / np.where(l2 > 0.0, l2, 1.0)
    s = np.clip(np.nan_to_num(s), 0.0, 1.0)
    nah = A[None, :, :] + s[:, :, None] * d[None, :, :]
    return np.linalg.norm(P[:, None, :] - nah, axis=2).min(axis=1)


def _deckungsgleich_abb(A: np.ndarray, B: np.ndarray, abb: tuple, tol: float,
                        geschlossen: bool = True) -> bool:
    """Liegt jeder Punkt von ``A`` unter der Abbildung auf ``B`` und umgekehrt?

    Gemessen wird gegen die **Kurve**, nicht gegen die Stuetzpunkte: zwei
    Kappen duerfen ihren Rand in verschieden viele Linien teilen, solange sie
    dieselbe Figur umschliessen. Das steht seit jeher in :func:`_deckungsgleich`
    als Anspruch, war aber nicht eingeloest - gegen die Stuetzpunkte gemessen
    faellt jede zusaetzliche Ecke durch (22.09.2026). Die Pruefung wird dadurch
    nur **grosszuegiger**; was bisher durchging, geht weiter durch.

    Drei Stufen, weil das hier ueber jedes Flaechenpaar eines Koerpers laeuft
    (bis 144 x 144 am Drehlager): erst Stuetzpunkt auf Stuetzpunkt (KD-Baum,
    der haeufige Fall und so schnell wie zuvor), dann der umschriebene Kasten
    als notwendige Bedingung (schliesst fast jedes fremde Paar aus), und nur
    fuer die Punkte, die keinen Stuetzpunkt treffen, der Abstand zur Kurve.
    Dicht gerechnet kostete die Kurve bei 500 Randpunkten 23 ms statt 0,4 ms
    je Paar - gemessen am 22.09.2026, bevor die Stufen kamen.
    """
    from scipy.spatial import cKDTree
    if not len(A) or not len(B):
        return False
    Am = _abbilden(A, abb)
    dA, _ = cKDTree(B).query(Am)
    dB, _ = cKDTree(Am).query(B)
    if dA.max() <= tol and dB.max() <= tol:
        return True
    if len(Am) < 2 or len(B) < 2:
        return False
    if ((np.abs(Am.min(axis=0) - B.min(axis=0)) > tol).any()
            or (np.abs(Am.max(axis=0) - B.max(axis=0)) > tol).any()):
        return False                        # verschiedene Kaesten: nie dieselbe Kurve
    fern_a = Am[dA > tol]
    if len(fern_a) and float(_abstand_zum_zug(fern_a, B, geschlossen).max()) > tol:
        return False
    fern_b = B[dB > tol]
    if len(fern_b) and float(_abstand_zum_zug(fern_b, Am, geschlossen).max()) > tol:
        return False
    return True


def _umkehr(abb: tuple) -> "tuple | None":
    """Die Gegenabbildung - vom Deckel zurueck auf den Grund."""
    if abb[0] == "d":
        _tag, a, d, phi = abb
        return ("d", a, d, -float(phi))
    _tag, c, k, t = abb
    k = float(k)
    if abs(k) <= 1e-12:
        return None
    return ("v", c, 1.0 / k, -np.asarray(t, float) / k)


def _deckungsgleich(A: np.ndarray, B: np.ndarray, t: np.ndarray, tol: float) -> bool:
    """Liegt jeder Punkt von A + t auf B und jeder Punkt von B auf A + t?
    Als Mengen, ohne gleiche Punktzahl - zwei Kappen duerfen ihren Rand in
    verschieden viele Linien teilen, solange die Kurven dieselben sind."""
    from scipy.spatial import cKDTree
    if not len(A) or not len(B):
        return False
    dA, _ = cKDTree(B).query(A + t)
    dB, _ = cKDTree(A + t).query(B)
    return bool(dA.max() <= tol and dB.max() <= tol)


def _gerade(model: Model, name: str) -> "np.ndarray | None":
    """Vektor einer geraden Linie mit zwei Knoten - sonst None."""
    ln = model.lines.get(name)
    if ln is None or (ln.typ or "polyline") != "polyline" or len(ln.nodes) != 2:
        return None
    a, b = int(ln.nodes[0]), int(ln.nodes[1])
    if not (0 <= a < model.nn and 0 <= b < model.nn):
        return None
    return model.nodes[b] - model.nodes[a]


def _linienenden(model: Model, name: str) -> "tuple | None":
    ln = model.lines.get(name)
    if ln is None or len(ln.nodes) < 2:
        return None
    a, b = int(ln.nodes[0]), int(ln.nodes[-1])
    if not (0 <= a < model.nn and 0 <= b < model.nn):
        return None
    return a, b


def _linien_von(f) -> set:
    """Alle Linien einer Flaeche: Rand und Oeffnungen."""
    aus = set(f.linien or [])
    for loch in (f.oeffnungen or []):
        aus.update(loch)
    return aus


def _schleifen(model: Model, linien) -> "list | None":
    """Eine Linienmenge in geschlossene Zuege ordnen: [[Linie, ...], ...] im
    Umlauf, der groesste Zug zuerst - None, wenn ein Zug nicht schliesst."""
    from .mesher3d import seiten_im_umlauf
    linien = list(dict.fromkeys(linien))
    if not linien:
        return []
    vater: dict = {}

    def wurzel(x):
        while vater.get(x, x) != x:
            vater[x] = vater.get(vater[x], vater[x])
            x = vater[x]
        return x
    enden = {}
    for name in linien:
        e = _linienenden(model, name)
        if e is None:
            return None
        enden[name] = e
        vater.setdefault(e[0], e[0])
        vater.setdefault(e[1], e[1])
        ra, rb = wurzel(e[0]), wurzel(e[1])
        if ra != rb:
            vater[ra] = rb
    gruppen: dict = {}
    for name in linien:
        gruppen.setdefault(wurzel(enden[name][0]), []).append(name)
    aus = []
    for teil in gruppen.values():
        st = seiten_im_umlauf(model, teil)
        if not st or len(st) != len(teil):
            return None
        aus.append([name for name, _k in st])

    def ausdehnung(schleife):
        P = _schleifenpunkte(model, schleife)
        return float(np.linalg.norm(P.max(axis=0) - P.min(axis=0))) if len(P) else 0.0
    aus.sort(key=ausdehnung, reverse=True)
    return aus


def _kappen_kandidaten(model: Model, flaechen: list, tol: float) -> list:
    """Moegliche Kappen: jede ebene Flaeche fuer sich - und jede **Gruppe**
    koplanarer, ueber Linien verbundener ebener Flaechen (eine Platte, deren
    Deckel eine Nabe traegt: Deckelflaeche mit Fussabdruck als Oeffnung plus
    der Fussabdruck selbst). Rueckgabe [(Flaechen, Schleifen, Punkte je
    Schleife)]; die Schleifen einer Gruppe sind die Linien, die nur **eine**
    ihrer Flaechen benutzt - die inneren Linien zwischen den Flaechen fallen
    heraus."""
    from .mesher3d import ist_eben, ausgleichsebene
    daten: dict = {}
    for f in flaechen:
        schleifen = [list(f.linien or [])] + [list(loch) for loch in (f.oeffnungen or [])]
        try:
            pts = [_schleifenpunkte(model, sch) for sch in schleifen]
        except Exception:                   # noqa: BLE001
            continue
        if any(len(p) < 3 for p in pts):
            continue
        alle = np.vstack(pts)
        if not ist_eben(alle):
            continue
        c, _e1, _e2, n, _abw = ausgleichsebene(alle)
        daten[f.name] = (f, schleifen, pts, np.asarray(n, float), float(n @ c))
    kand = [([d[0]], d[1], d[2]) for d in daten.values()]
    namen = list(daten)
    vater = {x: x for x in namen}

    def wurzel(x):
        while vater[x] != x:
            vater[x] = vater[vater[x]]
            x = vater[x]
        return x
    for i, a_ in enumerate(namen):
        fa, _s, _p, na, da = daten[a_]
        La = _linien_von(fa)
        for b_ in namen[i + 1:]:
            fb, _s2, _p2, nb, db = daten[b_]
            cosw = float(na @ nb)
            if abs(abs(cosw) - 1.0) > 1e-6 or abs(cosw * db - da) > tol:
                continue                    # nicht dieselbe Ebene
            if not (La & _linien_von(fb)):
                continue                    # nicht verbunden
            ra, rb = wurzel(a_), wurzel(b_)
            if ra != rb:
                vater[ra] = rb
    gruppen: dict = {}
    for x in namen:
        gruppen.setdefault(wurzel(x), []).append(x)
    for mitglieder in gruppen.values():
        if len(mitglieder) < 2:
            continue
        fl = [daten[x][0] for x in mitglieder]
        zaehl: dict = {}
        for f in fl:
            for lname in _linien_von(f):
                zaehl[lname] = zaehl.get(lname, 0) + 1
        aussen = [lname for lname, k in zaehl.items() if k == 1]
        schleifen = _schleifen(model, aussen)
        if not schleifen:
            continue
        pts = [_schleifenpunkte(model, sch) for sch in schleifen]
        if any(len(p) < 3 for p in pts):
            continue
        kand.append((fl, schleifen, pts))
    return kand


def erkennen(model: Model, koerper) -> "dict | None":
    """Grund, Deckel, Weg und Waende eines sweepbaren Koerpers - oder None.

    Rueckgabe {"grund": erste Grundflaeche, "grund_gruppe": [Grundflaechen],
    "grund_ringe": [[Linien im Umlauf], ...] (Aussenrand zuerst), "deckel":
    Flaeche, "t": Vektor, "linien": {Linie des Grundes: Linie des Deckels},
    "waende": {Linie des Grundes: Wandflaeche}, "mantel": {Knoten des
    Grundes: Mantellinie}, "tol": Toleranz}.

    Der Grund darf eine **Gruppe** koplanarer Flaechen sein (Platte mit
    Fussabdruck einer Nabe, Schulter einer abgesetzten Welle), der Deckel ist
    immer eine einzelne Flaeche: das Netz der Gruppe achtet die inneren Linien,
    verschoben passt es auf die eine Deckelflaeche - umgekehrt nicht.
    """
    flaechen = [model.flaechen.get(x) for x in (koerper.flaechen or [])]
    if len(flaechen) < KAPPEN_MIN_FLAECHEN or any(f is None for f in flaechen):
        return None
    try:
        alle = np.vstack([_schleifenpunkte(model, list(f.linien or [])) for f in flaechen])
    except Exception:                       # noqa: BLE001
        return None
    if not len(alle):
        return None
    gross = float(np.linalg.norm(alle.max(axis=0) - alle.min(axis=0)))
    tol = max(TOL_REL * gross, 1e-12)
    kand = _kappen_kandidaten(model, flaechen, tol)
    einzeln = [k for k in kand if len(k[0]) == 1]
    namen = {f.name: f for f in flaechen}
    for grund in kand:
        grund_namen = {f.name for f in grund[0]}
        for deckel in einzeln:
            if deckel[0][0].name in grund_namen:
                continue
            erg = _kappen_pruefen(model, grund, deckel, tol, namen)
            if erg is not None:
                return erg
    return None


def erkennen_warum_nicht(model: Model, koerper) -> str:
    """Woran die Sweep-Erkennung an diesem Koerper scheitert - in einem Satz,
    mit Zahlen. Nur sinnvoll, wenn :func:`erkennen` None geliefert hat.

    Warum es diese Zeile gibt: am Drehlager sind 68 von 108 Koerpern sweepbar,
    aber sie tragen nur 8,2 % der Elemente - die 40 uebrigen tragen 91,8 %
    (Lauf der Loeser-Sitzung, 21.09.2026). Welche Erweiterung der Erkennung
    sich lohnt (Drehkoerper, verjuengter Zug, andere Richtung), haengt daran,
    **woran** diese 40 scheitern. Ohne die Zeile ist jede Erweiterung geraten;
    dieselbe Frage hat beim Zerlegen und bei den Splittern den Ausschlag
    gegeben (sweep.zerlegen_warum_nicht, mesher3d._enge_huellkanten).

    Die Gruende sind nach der Tiefe geordnet: genannt wird der **weiteste**,
    den irgendein Kappenpaar erreicht hat.
    """
    flaechen = [model.flaechen.get(x) for x in (koerper.flaechen or [])]
    if any(f is None for f in flaechen):
        return "eine Randfläche fehlt"
    if len(flaechen) < KAPPEN_MIN_FLAECHEN:
        return f"nur {len(flaechen)} Randflächen (mindestens {KAPPEN_MIN_FLAECHEN})"
    try:
        alle = np.vstack([_schleifenpunkte(model, list(f.linien or [])) for f in flaechen])
    except Exception:                       # noqa: BLE001
        return "eine Randlinie lässt sich nicht abtasten"
    gross = float(np.linalg.norm(alle.max(axis=0) - alle.min(axis=0)))
    tol = max(TOL_REL * gross, 1e-12)
    kand = _kappen_kandidaten(model, flaechen, tol)
    eben = [k for k in kand if len(k[0]) == 1]
    if len(kand) < 2:
        return (f"keine zwei ebenen Kappen: {len(eben)} von {len(flaechen)} Randflächen sind eben "
                "(Drehkörper oder gewölbte Kappe)")
    einzeln = eben
    namen = {f.name: f for f in flaechen}
    # Der weiteste erreichte Grund, in dieser Reihenfolge
    stufe, text = 0, ""
    for grund in kand:
        grund_namen = {f.name for f in grund[0]}
        for deckel in einzeln:
            if deckel[0][0].name in grund_namen:
                continue
            fl_g, schleifen_g, pts_g = grund
            fl_d, schleifen_d, pts_d = deckel
            if len(schleifen_g) != len(schleifen_d):
                if stufe < 1:
                    stufe, text = 1, ("kein Kappenpaar mit gleich vielen Rändern "
                                      f"({len(schleifen_g)} gegen {len(schleifen_d)})")
                continue
            t = pts_d[0].mean(axis=0) - pts_g[0].mean(axis=0)
            if float(np.linalg.norm(t)) <= tol:
                continue
            abb = ("v", pts_g[0].mean(axis=0), 1.0, t)
            if not _deckungsgleich_abb(pts_g[0], pts_d[0], abb, tol):
                for versuch in _abbildungen(pts_g, pts_d, tol):
                    abb = versuch
                    if _deckungsgleich_abb(pts_g[0], pts_d[0], versuch, tol):
                        break
            frei = list(range(len(schleifen_d)))
            passt = _deckungsgleich_abb(pts_g[0], pts_d[0], abb, tol)
            if passt:
                for P in pts_g:
                    treffer = None
                    for j in frei:
                        if _deckungsgleich_abb(P, pts_d[j], abb, tol):
                            treffer = j
                            break
                    if treffer is None:
                        passt = False
                        break
                    frei.remove(treffer)
            if not passt:
                if stufe < 2:
                    # Wie weit ist es daneben - nach Verschiebung **und** nach
                    # der besten Aehnlichkeit (verjuengter Zug ist seit dem
                    # 22.09.2026 erfasst, ein Drehkoerper nicht).
                    from scipy.spatial import cKDTree
                    d_t = float(cKDTree(pts_d[0]).query(pts_g[0] + t)[0].max())
                    d_a = float(cKDTree(pts_d[0]).query(_abbilden(pts_g[0], abb))[0].max())
                    art = ("gedreht" if abb[0] == "d" else f"skaliert (Maßstab {abb[2]:.3f})")
                    stufe, text = 2, (f"Kappen {fl_g[0].name} → {fl_d[0].name} decken sich weder "
                                      f"verschoben ({d_t * 1e3:.1f} mm daneben) noch {art} "
                                      f"({d_a * 1e3:.1f} mm) bei {np.linalg.norm(t) * 1e3:.1f} mm "
                                      "Weg - verdreht, gewölbte Kappe oder keine Kappen")
                continue
            la = [x for sch in schleifen_g for x in sch]
            lb = [x for sch in schleifen_d for x in sch]
            rest = [f for f in namen.values() if f.name not in grund_namen and f.name != fl_d[0].name]
            if len(rest) != len(la):
                if stufe < 3:
                    stufe, text = 3, (f"Kappen passen ({fl_g[0].name} → {fl_d[0].name}), aber "
                                      f"{len(rest)} Wandflächen zu {len(la)} Randlinien")
                continue
            schlecht = [w.name for w in rest if len(list(w.linien or [])) != 4 or (w.oeffnungen or [])]
            if schlecht:
                if stufe < 4:
                    stufe, text = 4, (f"Kappen passen ({fl_g[0].name} → {fl_d[0].name}), aber "
                                      f"{len(schlecht)} Wand/Wände sind nicht aus vier Linien ohne "
                                      f"Öffnung (z. B. {schlecht[0]})")
                continue
            if _waende_pruefen(model, la, lb, t, tol, rest) is None:
                if stufe < 5:
                    stufe, text = 5, (f"Kappen und Wandzahl passen ({fl_g[0].name} → {fl_d[0].name}), "
                                      "aber die Mantellinien sind nicht gerade und parallel zum Weg")
                continue
            return "sweepbar - erkennen() hätte greifen müssen"
    return text or "kein Kappenpaar mit einem Weg dazwischen"


def _abbildungen(pts_g: list, pts_d: list, tol: float) -> list:
    """Die Abbildungen, die zwischen Grund und Deckel in Frage kommen -
    Aehnlichkeit (verjuengter Zug) und Drehung (Drehkoerper), in dieser
    Reihenfolge."""
    from .mesher3d import ausgleichsebene
    aus = []
    ab = _abbildung_finden(pts_g[0], pts_d[0], tol)
    if ab is not None:
        aus.append(ab)
    try:
        _c1, _e1, _e2, nA, _a1 = ausgleichsebene(pts_g[0])
        _c2, _e3, _e4, nB, _a2 = ausgleichsebene(pts_d[0])
    except Exception:                       # noqa: BLE001
        return aus
    dreh = _abbildung_drehung(pts_g[0], pts_d[0], nA, nB, tol)
    if dreh is not None:
        aus.append(dreh)
        aus.append(("d", dreh[1], dreh[2], -float(dreh[3])))
        aus.append(("d", dreh[1], dreh[2], float(dreh[3]) - 2.0 * np.pi))
        aus.append(("d", dreh[1], dreh[2], 2.0 * np.pi - float(dreh[3])))
    return aus


def _kappen_abbildung(model: Model, grund: tuple, deckel: tuple, tol: float) -> "tuple | None":
    """Die Abbildung, die den Grund auf den Deckel legt, und die Zuordnung
    ihrer Schleifen - ``(abb, [(i, j), ...], t)`` oder None.

    Ohne die Waende: so kann auch das **Angleichen** der Linienteilung danach
    fragen, bevor es die Waende ueberhaupt geben kann.
    """
    _fl_g, schleifen_g, pts_g = grund
    _fl_d, schleifen_d, pts_d = deckel
    if len(schleifen_g) != len(schleifen_d):
        return None
    t = _umringmitte(pts_d[0]) - _umringmitte(pts_g[0])
    if float(np.linalg.norm(t)) <= tol:
        return None
    # Erst die reine Verschiebung (der haeufige Fall), dann die Aehnlichkeit
    # (verjuengter Zug). Beides ueber dieselbe Abbildung, k = 1 ist die
    # Verschiebung - so bleibt der alte Weg Zeichen fuer Zeichen derselbe.
    abb = ("v", _umringmitte(pts_g[0]), 1.0, t)
    if not _deckungsgleich_abb(pts_g[0], pts_d[0], abb, tol):
        for versuch in _abbildungen(pts_g, pts_d, tol):
            if _deckungsgleich_abb(pts_g[0], pts_d[0], versuch, tol):
                abb = versuch
                break
        else:
            return None
    paarung, frei = [], list(range(len(schleifen_d)))
    for i, P in enumerate(pts_g):
        treffer = None
        for j in frei:
            if _deckungsgleich_abb(P, pts_d[j], abb, tol):
                treffer = j
                break
        if treffer is None:
            return None
        frei.remove(treffer)
        paarung.append((i, treffer))
    return abb, paarung, t


def _kappen_pruefen(model: Model, grund: tuple, deckel: tuple, tol: float, namen: dict) -> "dict | None":
    """Ist der Deckel die um t verschobene Kopie des Grundes, Schleife fuer
    Schleife, und sind alle uebrigen Flaechen Waende?"""
    fl_g, schleifen_g, pts_g = grund
    fl_d, schleifen_d, pts_d = deckel
    erg_abb = _kappen_abbildung(model, grund, deckel, tol)
    if erg_abb is None:
        return None
    abb, _paarung, t = erg_abb
    la = [x for sch in schleifen_g for x in sch]
    lb = [x for sch in schleifen_d for x in sch]
    grund_namen = {f.name for f in fl_g}
    rest = [f for f in namen.values() if f.name not in grund_namen and f.name != fl_d[0].name]
    erg = _waende_pruefen(model, la, lb, abb, tol, rest)
    if erg is None:
        return None
    erg.update({"grund": fl_g[0], "grund_gruppe": list(fl_g),
                "grund_ringe": [list(sch) for sch in schleifen_g],
                "deckel": fl_d[0], "t": np.asarray(t, float), "abb": abb, "tol": tol})
    return erg


def _mantel_auf_bahn(model: Model, name: str, unten: int, abb: tuple, tol: float) -> bool:
    """Laeuft die Mantellinie auf der Bahn der Drehung? Geprueft wird, dass
    jeder ihrer Punkte denselben Abstand zur Achse und dieselbe Hoehe laengs
    der Achse hat wie der Grundknoten - das ist der Kreisbogen um sie, ohne
    Annahme ueber die Abtastung der Linie."""
    _tag, a, d, _phi = abb
    a = np.asarray(a, float)
    d = np.asarray(d, float)
    try:
        P = np.asarray(model.lines[name].punkte(model, 12), float).reshape(-1, 3)
    except Exception:                       # noqa: BLE001
        return False
    if len(P) < 3:
        return False
    def zylinder(X):
        rel = np.asarray(X, float).reshape(-1, 3) - a
        hoehe = rel @ d
        radius = np.linalg.norm(rel - np.outer(hoehe, d), axis=1)
        return radius, hoehe
    r0, h0 = zylinder(model.nodes[[unten]])
    r, h = zylinder(P)
    return bool(np.max(np.abs(r - r0[0])) <= tol and np.max(np.abs(h - h0[0])) <= tol)


def _waende_pruefen(model: Model, la: list, lb: list, abb: tuple, tol: float, rest: list) -> "dict | None":
    """Jede uebrige Randflaeche muss eine Wand zwischen einer Grundlinie und
    ihrer Deckellinie sein, mit zwei geraden Mantellinien laengs t."""
    if len(la) != len(lb):
        return None
    enden_b = {}
    for name in lb:
        e = _linienenden(model, name)
        if e is None:
            return None
        enden_b[name] = e
    paare = {}

    def abtasten(name):
        try:
            return np.asarray(model.lines[name].punkte(model, 8), float).reshape(-1, 3)
        except Exception:                   # noqa: BLE001
            return None
    for name in la:
        e = _linienenden(model, name)
        if e is None:
            return None
        pa, pb = _abbilden(model.nodes[[e[0], e[1]]], abb)
        treffer = None
        Pa = None
        for nb, (c, d) in enden_b.items():
            if nb in paare.values():
                continue
            qc, qd = model.nodes[c], model.nodes[d]
            if ((np.linalg.norm(pa - qc) <= tol and np.linalg.norm(pb - qd) <= tol)
                    or (np.linalg.norm(pa - qd) <= tol and np.linalg.norm(pb - qc) <= tol)):
                # Gleiche Endknoten reichen nicht: die zwei Halbboegen eines
                # Kreises teilen sich beide Enden. Erst die Kurve entscheidet.
                if Pa is None:
                    Pa = abtasten(name)
                Pb = abtasten(nb)
                if Pa is None or Pb is None or _deckungsgleich_abb(Pa, Pb, abb, tol, False):
                    treffer = nb
                    break
        if treffer is None:
            return None
        paare[name] = treffer
    knoten_a = {k for name in la for k in _linienenden(model, name)}
    mantel = {}
    waende = {}
    if len(rest) != len(la):
        return None
    for w in rest:
        wl = list(w.linien or [])
        if len(wl) != 4 or (w.oeffnungen or []):
            return None
        grund = [x for x in wl if x in paare]
        deckel = [x for x in wl if x in paare.values()]
        senk = [x for x in wl if x not in paare and x not in paare.values()]
        if len(grund) != 1 or len(deckel) != 1 or len(senk) != 2 or paare[grund[0]] != deckel[0]:
            return None
        for s_ in senk:
            # Die Mantellinie verbindet einen Grundknoten mit **seinem Bild**.
            # Bei Verschiebung und verjuengtem Zug ist sie gerade; beim
            # Drehkoerper ist sie ein **Bogen**, und dann muss ihr ganzer
            # Verlauf auf der Bahn der Drehung liegen - sonst waere die Wand
            # nicht die gedrehte Kante.
            e = _linienenden(model, s_)
            if e is None:
                return None
            unten = e[0] if e[0] in knoten_a else e[1]
            oben = e[1] if unten == e[0] else e[0]
            if unten not in knoten_a:
                return None
            if float(np.linalg.norm(_abbilden(model.nodes[[unten]], abb)[0] - model.nodes[oben])) > tol:
                return None
            if abb[0] == "d":
                if not _mantel_auf_bahn(model, s_, unten, abb, tol):
                    return None
            elif _gerade(model, s_) is None:
                return None
            if mantel.get(unten, s_) != s_:
                return None
            mantel[unten] = s_
        waende[grund[0]] = w
    if len(waende) != len(la) or set(mantel) != knoten_a:
        return None
    return {"linien": paare, "waende": waende, "mantel": mantel}


def sweepbar(model: Model, koerper, h: float = 0.0, karten: tuple = None, log: list = None) -> bool:
    """Laesst sich der Koerper sweepen - unmittelbar oder nach dem Zerlegen an
    Fussabdruecken - (und ist das eingeschaltet)?

    In der Betriebsart "sauber" heisst das: er wird **wirklich** gesweept,
    also besteht seine Probe (:func:`vernetzen` mit ``nur_pruefen``); ein
    abgelehnter Koerper gilt als frei und geht in einen Arbeitsprozess. Ohne
    diese Vorpruefung liefen die abgelehnten Koerper - am Drehlager fast
    alle sweepbaren - als "abgebildet" im Hauptprozess durch den freien
    Vernetzer, nacheinander, mit MMG3D: ueber 14 Minuten fuer einen Koerper
    (gemessen 24.09.2026). Zerlegen an Fussabdruecken gibt es in "sauber"
    nicht: die Bloecke sind gepflasterte Grundflaechen, die die Probe nicht
    bestehen."""
    from .importers import _common as C
    art = betriebsart(model)
    if art == "aus":
        return False
    try:
        if art == "sauber":
            # Das Protokoll nennt je Koerper, ob er gesweept wird und wenn
            # nicht, warum; die Ablehnung merkt sich das Modell fuer den Lauf,
            # damit mesh_koerper den Sweep nicht noch einmal versucht
            abgelehnt = getattr(model, "_sauber_abgelehnt", None)
            if abgelehnt is None:
                abgelehnt = model._sauber_abgelehnt = {}
            erk = erkennen(model, koerper)
            if erk is None:
                grund = erkennen_warum_nicht(model, koerper)
                abgelehnt[koerper.name] = grund
                if log is not None:
                    C.say(log, f"Volumen {koerper.name}: nicht gesweept - {grund}; in der Betriebsart „sauber“ "
                               "wird nicht zerlegt, der freie Vernetzer übernimmt.")
                return False
            probe = vernetzen(model, koerper, erk, h, log=None, cache=None, karten=karten, nur_pruefen=True)
            if isinstance(probe, tuple) and probe[0]:
                return True
            grund = probe[1] if isinstance(probe, tuple) else "der Sweep geht hier nicht"
            abgelehnt[koerper.name] = grund
            if log is not None:
                C.say(log, f"Volumen {koerper.name}: nicht gesweept (Betriebsart „sauber“) - {grund}; "
                           "der freie Vernetzer übernimmt, Übergang über Pyramiden.")
            return False
        if erkennen(model, koerper) is not None:
            return True
        return zerlegbar(model, koerper)
    except Exception:                       # noqa: BLE001 - eine Erkennung darf nie sperren
        return False


# --------------------------------------------------------------------------
# Vierecke aus Dreiecken
# --------------------------------------------------------------------------
def _viereckguete(Q: np.ndarray) -> np.ndarray:
    """Skalierte Jacobi-Determinante eines ebenen Vierecks (n, 4, 2): das
    Minimum ueber die vier Ecken von sin des Eckwinkels, negativ bei einer
    umgestuelpten (nicht konvexen) Ecke. 1 ist das Quadrat."""
    aus = np.full(len(Q), np.inf)
    for k in range(4):
        e1 = Q[:, (k + 1) % 4] - Q[:, k]
        e2 = Q[:, (k - 1) % 4] - Q[:, k]
        l1 = np.linalg.norm(e1, axis=1)
        l2 = np.linalg.norm(e2, axis=1)
        kreuz = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
        w = np.where((l1 > 0) & (l2 > 0), kreuz / np.maximum(l1 * l2, 1e-300), -1.0)
        aus = np.minimum(aus, w)
    return aus


def paaren(P2: np.ndarray, T: np.ndarray, guete_min: float = VIERECK_GUETE_MIN) -> tuple:
    """Dreiecke zu Vierecken paaren - gierig nach der Guete des Vierecks, dann
    **umgepaart**, bis kein Dreieck mehr uebrig ist, das noch koennte.

    ``T`` sind Dreiecke mit gleichem Umlauf (gegen den Uhrzeiger in ``P2``).
    Zwei Dreiecke, die eine Kante teilen, geben das Viereck ueber die andere
    Diagonale; es wird genommen, wenn seine Guete mindestens ``guete_min``
    ist und beide Dreiecke noch frei sind. Rueckgabe (Vierecke (q, 4),
    uebrige Dreiecke (r, 3)), beide gegen den Uhrzeiger.

    Warum das Umpaaren sein muss: **ein Keil ist kein halber Sechsflaechner.**
    Der hex8 traegt Biegung ueber inkompatible Moden, der pent6 nicht - am
    identischen Knotengitter gemessen (Statik3D-Sitzung, 22.09.2026,
    Kragarm 1,0 x 0,1 x 0,2 m gegen die Balkenloesung mit Schub):

        Gitter    hex8     pent6    der Keil ist steifer um
        4x1x1     95,9 %   56,4 %   Faktor 1,70
        8x1x2     96,8 %   81,8 %   Faktor 1,18
        16x2x4    98,2 %   93,5 %   Faktor 1,05

    Jedes Dreieck, das keinen Partner findet, kostet also am groben Netz
    richtig. Und es liegt **nicht** an der Guetegrenze: sie von 0,3 auf 10^-6
    zu senken aenderte an der Kragplatte keine einzige Zahl (96 Keile bei
    h = 50 mm, 128 bei 25 mm, 22.09.2026). Es liegt an der gierigen Auswahl -
    sie laesst Dreiecke stehen, deren Nachbarn schon vergeben sind, obwohl
    ein Tausch beide unterbraechte. Genau das holt der zweite Schritt: fuer
    jedes uebrige Dreieck u wird ein Nachbar v gesucht, dessen Partner w
    seinerseits ein **anderes** uebriges Dreieck x hat; dann werden (v, w)
    geloest und (u, v) und (w, x) genommen - ein erweiternder Weg der Laenge
    drei. Das wiederholt sich, solange es traegt.
    """
    T = np.asarray(T, int)
    if not len(T):
        return np.zeros((0, 4), int), T
    kante: dict = {}
    for k, (a, b, c) in enumerate(T):
        for x, y in ((a, b), (b, c), (c, a)):
            kante.setdefault((min(x, y), max(x, y)), []).append(k)
    kandidaten = []
    for (x, y), ks in kante.items():
        if len(ks) != 2:
            continue
        k1, k2 = ks
        t1, t2 = [int(v) for v in T[k1]], [int(v) for v in T[k2]]
        # Umlauf: das Viereck laeuft von der Spitze des ersten Dreiecks
        # (gegenueber der Kante) ueber die Kante zur Spitze des zweiten
        s1 = [v for v in t1 if v not in (x, y)][0]
        s2 = [v for v in t2 if v not in (x, y)][0]
        i1 = t1.index(s1)
        i, j = t1[(i1 + 1) % 3], t1[(i1 + 2) % 3]      # Kante in Umlaufrichtung von t1
        viereck = (s1, i, s2, j)
        kandidaten.append((k1, k2, viereck))
    if not kandidaten:
        return np.zeros((0, 4), int), T
    Q = np.array([v for _, _, v in kandidaten], int)
    q = _viereckguete(Q if Q.ndim == 3 else P2[Q])
    # ---- 1) gierig, das Beste zuerst --------------------------------------
    reihenfolge = np.argsort(-q, kind="stable")
    partner = np.full(len(T), -1, int)              # Dreieck -> Dreieck
    paar_von = {}                                   # Dreieck -> Kandidatennummer
    for r in reihenfolge:
        if q[r] < guete_min:
            break
        k1, k2, _v = kandidaten[r]
        if partner[k1] >= 0 or partner[k2] >= 0:
            continue
        partner[k1], partner[k2] = k2, k1
        paar_von[k1] = paar_von[k2] = int(r)
    # ---- 2) umpaaren: erweiternde Wege der Laenge drei ---------------------
    moeglich: dict = {}                             # Dreieck -> [(Nachbar, Kandidatennummer)]
    for r, (k1, k2, _v) in enumerate(kandidaten):
        if q[r] < guete_min:
            continue
        moeglich.setdefault(k1, []).append((k2, r))
        moeglich.setdefault(k2, []).append((k1, r))
    geaendert = True
    while geaendert:
        geaendert = False
        for u in np.nonzero(partner < 0)[0]:
            if partner[u] >= 0:
                continue
            for v, r_uv in moeglich.get(int(u), ()):
                w = partner[v]
                if w < 0:                           # haette die Gier schon genommen
                    continue
                for x, r_wx in moeglich.get(int(w), ()):
                    if x == v or partner[x] >= 0:
                        continue
                    # (v, w) loesen, (u, v) und (w, x) nehmen
                    partner[u], partner[v] = v, u
                    partner[w], partner[x] = x, w
                    paar_von[u] = paar_von[v] = int(r_uv)
                    paar_von[w] = paar_von[x] = int(r_wx)
                    geaendert = True
                    break
                if partner[u] >= 0:
                    break
    vierecke = [kandidaten[paar_von[k]][2] for k in range(len(T))
                if partner[k] > k]
    rest = T[partner < 0]
    return (np.asarray(vierecke, int).reshape(-1, 4), rest)


# --------------------------------------------------------------------------
# Das Netz
# --------------------------------------------------------------------------
def _linienzug_herkunft(teilung, model: Model, linien: list) -> "tuple | None":
    from .mesher3d import _linienzug
    return _linienzug(teilung, model, linien)


def lagen_min(model: Model) -> int:
    """Die kleinste Lagenzahl fuer dieses Modell: LAGEN_MIN_PLASTISCH, wenn
    Fliessen gerechnet wird (``model.plastizitaet.an``), sonst LAGEN_MIN."""
    pz = getattr(model, "plastizitaet", None)
    return LAGEN_MIN_PLASTISCH if bool(pz is not None and getattr(pz, "an", False)) else LAGEN_MIN


def _lagen_aus_weg(model: Model, erk: dict, h: float) -> int:
    """Lagen aus Weg und Kantenlaenge, mindestens :func:`lagen_min`.

    Wirkt ein **Groessenfeld** am Koerper (Netzverfeinerungen, Feldpunkte der
    adaptiven Schleife), zaehlt die kleinste Kantenlaenge, die es laengs der
    Randzuege des Grundes und in der Mitte des Weges verlangt: die Lagen
    sind fuer den ganzen Koerper gleich dick, und wo das Feld die
    Grundflaeche fein teilt, muessen die Lagen mithalten - sonst entstehen
    flache Hexaeder, und die Verfeinerung der Schleife kommt quer zur Platte
    nicht an. Gemessen an der gesweepten Platte 0,4 x 0,24 x 0,08 m mit
    Bohrung unter Zug (21.09.2026): ohne diese Regel fielen die Lagen in der
    adaptiven Runde von 3 auf 2 (441 -> 482 Elemente, Fehler 13,7 -> 12,8 %),
    mit ihr siehe KALIBRIERUNG_HEX in netzfehler.
    """
    # Der Weg ist die Laenge der Mantellinie, nicht nur die Verschiebung des
    # Schwerpunkts: bei einem verjuengten Zug laufen die Mantellinien schraeg.
    abb = abbildung_von(erk)
    weg = float(np.linalg.norm(erk["t"]))
    if erk.get("grund_ringe"):
        try:
            P0 = _schleifenpunkte(model, erk["grund_ringe"][0], 12)
            weg = max(weg, float(np.linalg.norm(_abbilden(P0, abb) - P0, axis=1).mean()))
        except Exception:                   # noqa: BLE001
            pass
    h_eff = max(float(h), 1e-12)
    feld = getattr(model, "groessenfeld", None)
    if feld is not None and erk.get("grund_ringe") is not None:
        try:
            P = np.vstack([_schleifenpunkte(model, sch, 12) for sch in erk["grund_ringe"]])
            P = np.vstack([P, _abbilden(P, abb, 0.5), _abbilden(P, abb, 1.0)])
            h_feld = float(np.min(np.asarray(feld(P), float)))
            if h_feld > 0:
                h_eff = min(h_eff, h_feld)
        except Exception:                   # noqa: BLE001 - ohne Feld wie bisher
            pass
    return max(int(round(weg / h_eff)), lagen_min(model), 1)


def _lagen(model: Model, erk: dict, teilung, h: float) -> "tuple[int, str]":
    """Zahl der Lagen ueber den Weg.

    Aus Weg und Kantenlaenge, mindestens :func:`lagen_min` - **nicht** aus der
    Kartenteilung der Mantellinien: die Regel „eine Linie neben einer
    feineren" (mesher3d._linien_wachsen_lassen) teilt die Mantellinie neben
    einer feinen Bohrungssehne fuer den Tetraeder fein (Platte 1 x 0,6 x
    0,2 m: 10 Lagen statt 4, Kragplatte 1 x 0,2 x 0,05 m: 4 473 statt 1 300
    Knoten, 20.09.2026); fuer Hexaeder und Keile ist die Teilung je Richtung
    frei waehlbar, das ist gerade ihr Vorzug.

    Traegt eine Mantellinie eine **Vorgabe** (:func:`lagenvorgabe`, modellweit
    vor dem ersten Netz) oder gehoert sie einem zweiten Koerper, gilt diese
    Teilung fuer alle Lagen; die eigenen Mantellinien werden darauf gesetzt.
    Verschiedene Teilungen sperren den Sweep - mit der Vorgabe kommt das nur
    noch vor, wenn ein Koerper ohne den modellweiten Lauf
    (mesher.koerper_vernetzen) vernetzt wird.
    """
    mantel = set(erk["mantel"].values())
    vorgabe = getattr(model, "linienvorgabe", None) or {}
    fest = [s for s in mantel if s in teilung.gem_linien or s in vorgabe]
    if fest:
        n_fest = {int(teilung.n.get(s, 1)) for s in fest}
        if len(n_fest) != 1:
            return 0, "die Mantellinien gehören zweiten Körpern mit verschiedener Teilung"
        L = n_fest.pop()
    else:
        L = _lagen_aus_weg(model, erk, h)
    for s in mantel:
        teilung.n[s] = L
    return int(L), ""


def _quaderkanten(model: Model, koerper) -> "list | None":
    """Die drei Kantenrichtungen eines abgebildet vernetzten Sechsflaechners
    (sechs Vierecke, acht Eckknoten) als [x-Linien, y-Linien, z-Linien] in
    der Zaehlung von mesher._hex_netz - sonst None."""
    from .mesher import quader_kanten, quader_richtungen
    from .importers.rfem6_db import _hex_order
    flaechen = [model.flaechen.get(x) for x in (koerper.flaechen or [])]
    if len(flaechen) != 6 or any(f is None for f in flaechen):
        return None
    ringe = [f.randknoten(model) for f in flaechen]
    if len({n for r in ringe for n in r}) != 8 or not all(len(r) == 4 for r in ringe):
        return None
    order = _hex_order(ringe)
    if not order:
        return None
    return quader_richtungen(quader_kanten(model, koerper, order))


def lagenvorgabe(model: Model, koerper, hs: dict = None, karten: tuple = None,
                 log: list = None) -> dict:
    """{Mantellinie: Zahl der Abschnitte} fuer alle sweepbaren Koerper -
    **modellweit**, vor dem ersten Netz (mesher.koerper_vernetzen legt das
    Ergebnis als ``model.linienvorgabe`` ab; jede Linienteilung liest es).

    Warum: die Teilung einer Linie ist im Modell eine (mesher3d.Linienteilung),
    und jeder Koerper bildet sie fuer sich aus den Karten. Die Mantellinien
    eines gesweepten Koerpers muessen aber **alle gleich** geteilt sein - der
    Weg wird in Lagen durchgezogen. Gehoeren sie Nachbarn mit verschiedener
    Kantenlaenge, teilen die Karten sie verschieden, und der Sweep faellt aus.
    Am Drehlager (Zaehlung der Loeser-Sitzung, 21.09.2026) erkannte
    :func:`erkennen` zwei von 108 Koerpern, V18 und V11 (je sieben Waende,
    Weg 40 mm, h = 50 mm, 2 864 Elemente); :func:`vernetzen` lieferte fuer
    beide **null** Elemente: „die Mantellinien gehören zweiten Körpern mit
    verschiedener Teilung". Darum wird die Lagenzahl hier vorab festgelegt
    und ueber ``model.linienvorgabe`` an **jede** Linienteilung gegeben, auch
    an die der Nachbarn: L ist das Groesste aus Weg/h, :func:`lagen_min` und
    der Kartenteilung der **gemeinsamen** Mantellinien - kein Nachbar wird
    groeber, als seine Karte will; die eigenen Mantellinien teilt der Sweep
    frei. Teilen zwei sweepbare Koerper eine Mantellinie,
    bekommen beide dasselbe L (das groessere), und das laeuft ueber Ketten
    weiter, bis nichts mehr waechst. Geprueft an einer Platte, deren Wand
    einer Pyramide gehoert und an deren einer Mantellinie eine Kugel des
    Groessenfelds sitzt (tests.test_sweep.test_nachbar_mit_verschiedener_teilung).
    """
    from .importers import _common as C
    from . import mesher3d as M3
    if betriebsart(model) == "aus":
        return {}
    hs = hs or {}
    if karten:
        h_flaechen, h_linien, gemeinsam = karten[:3]
    else:
        h_flaechen, h_linien = M3.kantenlaengen_karte(model)
        gemeinsam = M3.gemeinsame_randflaechen(model)
    wunsch = []                                  # je sweepbarem Koerper: (Name, Mantellinien, L)
    for k in koerper:
        # Abgebildete Sechsflaechner (mesher._hex_netz): jede Kantenrichtung
        # bekommt eine Teilung - die eigene (koerper.teilung), an Kanten, die
        # ein Nachbar mitbenutzt, wenigstens dessen Karte. Ohne Nachbarn an
        # den Kanten bleibt die eigene Teilung, wie sie ist.
        quader = _quaderkanten(model, k)
        if quader is not None:
            flaechen = [model.flaechen[x] for x in k.flaechen]
            h = M3._kantenlaenge(model, k, float(hs.get(k.name, 0.0) or 0.0))
            teilung = M3.Linienteilung(model, flaechen, h, h_linien, h_flaechen, gemeinsam)
            teil = (list(getattr(k, "teilung", None) or []) + [4, 4, 4])[:3]
            for d, linien_d in enumerate(quader):
                gem = [x for x in linien_d if x in teilung.gem_linien]
                if not gem:
                    continue
                n_d = max([max(1, int(teil[d]))] + [int(teilung.n.get(x, 1)) for x in gem])
                wunsch.append((k.name, set(linien_d), n_d))
            continue
        try:
            erk = erkennen(model, k)
        except Exception:                        # noqa: BLE001 - dann kein Sweep, keine Vorgabe
            erk = None
        bloecke, schnitte = [(list(k.flaechen or []), erk)], []
        if erk is None:
            try:
                bl, schnitte = zerlegen(model, k)
            except Exception:                    # noqa: BLE001
                bl, schnitte = None, []
            bloecke = bl or []
        h = M3._kantenlaenge(model, k, float(hs.get(k.name, 0.0) or 0.0))
        for namen, erk_b in bloecke:
            if erk_b is None:
                continue
            flaechen = [model.flaechen[x] for x in namen]
            teilung = M3.Linienteilung(model, flaechen, h, h_linien, h_flaechen, gemeinsam)
            mantel = set(erk_b["mantel"].values())
            # Nur die Mantellinien, die ein Nachbar mitbenutzt, bringen ihre
            # Kartenteilung ein. Die eigenen nicht: ihre Karte traegt die Regel
            # „Linie neben einer feineren" (_linien_wachsen_lassen), und die gab
            # der Kragplatte 10 statt 2 Lagen, 4 473 statt 1 491 Knoten (21.09.2026,
            # tests.test_sweep.test_kragplatte_tet4_gegen_hex8).
            gem = [s for s in mantel if s in teilung.gem_linien]
            L = max([_lagen_aus_weg(model, erk_b, h)] + [int(teilung.n.get(s, 1)) for s in gem])
            wunsch.append((k.name, mantel, L))
            # Gepaarte Kappenlinien (Grund <-> Deckel) muessen gleich geteilt
            # sein - modellweit, denn eine davon kann einem Nachbarn gehoeren.
            for la_, lb_ in erk_b["linien"].items():
                na_, nb_ = int(teilung.n.get(la_, 1)), int(teilung.n.get(lb_, 1))
                if na_ != nb_ or la_ in teilung.gem_linien or lb_ in teilung.gem_linien:
                    wunsch.append((k.name, {la_, lb_}, max(na_, nb_)))
        schnitte_entfernen(model, schnitte)
    vorgabe: dict = {}
    geaendert = True
    while geaendert:                             # Ketten ueber gemeinsame Mantellinien
        geaendert = False
        for _name, mantel, L in wunsch:
            L_neu = max([L] + [vorgabe.get(s, 0) for s in mantel])
            for s in mantel:
                if vorgabe.get(s, 0) != L_neu:
                    vorgabe[s] = L_neu
                    geaendert = True
    if wunsch:
        lagen = sorted({max(vorgabe[s] for s in mantel) for _n, mantel, _L in wunsch})
        C.say(log, f"Sweep: Lagen für {len({n for n, _m, _L in wunsch})} Körper vorab festgelegt "
                   f"({len(vorgabe)} Linien, "
                   + (f"{lagen[0]} Lagen" if len(lagen) == 1 else f"{lagen[0]} … {lagen[-1]} Lagen")
                   + (f", mindestens {LAGEN_MIN_PLASTISCH} wegen Fließen"
                      if lagen_min(model) > LAGEN_MIN else "")
                   + ")")
    return vorgabe


def _mantel_kennung(model: Model, erk: dict, knoten_unten: int, k: int, L: int) -> tuple:
    """Kennung des Punktes auf der Mantellinie ueber dem Grundknoten, Lage k."""
    name = erk["mantel"][knoten_unten]
    ln = model.lines[name]
    if int(ln.nodes[0]) == int(knoten_unten):
        return ("L", name, k)
    return ("L", name, L - k)


def _deckel_kennung(model: Model, erk: dict, kenn, teilung) -> tuple:
    """Kennung eines Grundpunktes in den Deckel uebertragen."""
    if kenn is None:
        return None
    if kenn[0] == "K":
        knoten = int(kenn[1])
        if knoten not in erk["mantel"]:      # Ecke einer inneren Linie der Kappen-Gruppe
            return None
        oben = _linienenden(model, erk["mantel"][knoten])
        return ("K", oben[0] if oben[1] == knoten else oben[1])
    _, name, k = kenn
    name_b = erk["linien"].get(name)
    if name_b is None:                       # innere Linie einer Kappen-Gruppe: im Deckel ein Flaechenpunkt
        return None
    # Laufen beide Linien in derselben Richtung? (erster Punkt der Teilung)
    pa = teilung.punkte(name)
    pb = teilung.punkte(name_b)
    if len(pa) and len(pb) and np.linalg.norm(pb[0] - _abbilden(pa[:1], abbildung_von(erk))[0]) <= erk["tol"]:
        return ("L", name_b, k)
    return ("L", name_b, len(pa) - 1 - k)


def _rahmen(P: np.ndarray, t: np.ndarray) -> tuple:
    """(Mittelpunkt, e1, e2, n) einer ebenen Punktwolke - **rechtshaendig**
    (e1 x e2 = n) und mit n laengs t. Die Singulaerwertzerlegung in
    mesher3d.ausgleichsebene liefert die Haendigkeit zufaellig: an den
    Platten stimmte sie, am Zylinder (Kreis aus zwei Boegen) nicht, und alle
    140 Elemente standen auf dem Kopf (21.09.2026)."""
    from . import mesher3d as M3
    c, e1, e2, n, _abw = M3.ausgleichsebene(P)
    if float(n @ t) < 0:
        n = -n
    if float(np.cross(e1, e2) @ n) < 0:
        e2 = -e2
    return c, e1, e2, n


def _grundnetz(model: Model, koerper, gruppe: list, teilung, erk: dict, log: list) -> "dict | None":
    """Das Netz der Grundflaeche(n) in einem gemeinsamen Index: Punkte,
    Kennungen, je Flaeche ihre Vierecke und Dreiecke.

    Jede Flaeche der Gruppe wird fuer sich vernetzt (mesher3d.flaechennetz -
    das liefert auch ein vorgegebenes Netz samt Vierecken, wenn ein Nachbar
    oder ein anderer Block diese Flaeche schon gelegt hat) und fuer sich zu
    Vierecken gepaart; die Punkte auf den inneren Linien zwischen zwei
    Flaechen fallen ueber ihre Kennung zusammen. Gepaart wird **je Flaeche**,
    nie ueber eine Flaechengrenze: nur so legt ein zweiter Block, der dieselbe
    Flaeche als Kappe hat, dieselben Vierecke darauf.
    """
    from . import mesher3d as M3
    from .importers import _common as C
    tol = 1e-9

    def schluessel(p):
        return (round(float(p[0]) / tol), round(float(p[1]) / tol), round(float(p[2]) / tol))
    P: list = []
    kenn: list = []
    fl_punkt: list = []
    index: dict = {}
    je_flaeche: list = []
    netze = getattr(model, "flaechennetze", None) or {}
    for f in gruppe:
        Pf, Tf, meldung, grob, kf = M3.flaechennetz(model, f, teilung)
        if meldung or not len(Tf) or grob:
            C.say(log, f"Volumen {koerper.name}: nicht gesweept - Grundfläche {f.name}: "
                       f"{meldung or 'Randlinien zu grob geteilt'}.")
            return None
        Pf = np.asarray(Pf, float)
        Tf = np.asarray(Tf, int).reshape(-1, 3)
        kf = list(kf) + [None] * (len(Pf) - len(kf))
        c, e1, e2, nf = _rahmen(Pf, richtung_von(Pf, abbildung_von(erk)))
        P2f = np.stack([(Pf - c) @ e1, (Pf - c) @ e2], axis=1)
        a_, b_, d_ = P2f[Tf[:, 0]], P2f[Tf[:, 1]], P2f[Tf[:, 2]]
        fl2 = (b_[:, 0] - a_[:, 0]) * (d_[:, 1] - a_[:, 1]) - (d_[:, 0] - a_[:, 0]) * (b_[:, 1] - a_[:, 1])
        Tf = np.where((fl2 < 0)[:, None], Tf[:, [0, 2, 1]], Tf)
        vorgabe = netze.get(f.name)
        Qf = Df = None
        if vorgabe is not None and len(vorgabe) >= 5 and vorgabe[3] is not None:
            Qf = np.asarray(vorgabe[3], int).reshape(-1, 4)
            Df = np.asarray(vorgabe[4], int).reshape(-1, 3)
            if len(Qf):
                # linkslaeufig wie die Dreiecke
                q0, q1, q2, q3 = (P2f[Qf[:, i]] for i in range(4))
                fq = ((q0[:, 0] * q1[:, 1] - q1[:, 0] * q0[:, 1]) + (q1[:, 0] * q2[:, 1] - q2[:, 0] * q1[:, 1])
                      + (q2[:, 0] * q3[:, 1] - q3[:, 0] * q2[:, 1]) + (q3[:, 0] * q0[:, 1] - q0[:, 0] * q3[:, 1]))
                Qf = np.where((fq < 0)[:, None], Qf[:, ::-1], Qf)
            if len(Df):
                a_, b_, d_ = P2f[Df[:, 0]], P2f[Df[:, 1]], P2f[Df[:, 2]]
                fd = (b_[:, 0] - a_[:, 0]) * (d_[:, 1] - a_[:, 1]) - (d_[:, 0] - a_[:, 0]) * (b_[:, 1] - a_[:, 1])
                Df = np.where((fd < 0)[:, None], Df[:, [0, 2, 1]], Df)
        if Qf is None:
            Qf, Df = paaren(P2f, Tf)
        Qf = np.asarray(Qf, int).reshape(-1, 4)
        Df = np.asarray(Df, int).reshape(-1, 3)
        lokal = np.zeros(len(Pf), int)
        for i in range(len(Pf)):
            key = kf[i] if kf[i] is not None else ("P", f.name, schluessel(Pf[i]))
            j = index.get(key)
            if j is None:
                j = len(P)
                index[key] = j
                P.append(Pf[i])
                kenn.append(kf[i])
                fl_punkt.append(f.name)
            lokal[i] = j
        je_flaeche.append({"flaeche": f, "vierecke": lokal[Qf] if len(Qf) else np.zeros((0, 4), int),
                           "dreiecke": lokal[Df] if len(Df) else np.zeros((0, 3), int),
                           "P": Pf, "T": Tf, "kenn": kf, "Q": Qf, "D": Df})
    if not P:
        return None
    return {"P": np.asarray(P, float), "kenn": kenn, "flaeche_von_punkt": fl_punkt, "je_flaeche": je_flaeche}


def vernetzen(model: Model, koerper, erk: dict, h: float, log: list = None, cache: dict = None,
              karten: tuple = None, nur_pruefen: bool = False) -> list:
    """Den erkannten Koerper sweepen: Grundflaechennetz, Lagen, Elemente,
    Randseiten, vorgegebene Flaechennetze fuer die Nachbarn. Rueckgabe die
    Elementnummern; leer, wenn der Sweep nicht geht (der Grund steht im
    Protokoll, der Aufrufer nimmt den freien Vernetzer).

    ``nur_pruefen`` (Betriebsart "sauber"): nur bis zur Pruefung der
    Elemente rechnen, nichts ins Modell schreiben, und (sauber, Grund,
    Trapezfehler, Winkelfehler) zurueckgeben - bzw. [] wo der Sweep schon
    vorher nicht geht. Damit entscheidet :func:`sweepbar`, ob der Koerper im
    Hauptprozess gesweept wird oder als freier Koerper in einen
    Arbeitsprozess geht."""
    from .importers import _common as C
    from . import mesher3d as M3
    from scipy.spatial import cKDTree
    grund, deckel, t = erk["grund"], erk["deckel"], erk["t"]
    abb = abbildung_von(erk)
    gruppe = list(erk.get("grund_gruppe") or [grund])
    ringe = [list(r) for r in (erk.get("grund_ringe")
                               or ([list(grund.linien or [])] + [list(loch) for loch in (grund.oeffnungen or [])]))]
    flaechen = [model.flaechen[x] for x in koerper.flaechen]
    if karten:
        h_flaechen, h_linien, gemeinsam = karten[:3]
    else:
        h_flaechen, h_linien = M3.kantenlaengen_karte(model, h=h)
        gemeinsam = M3.gemeinsame_randflaechen(model)
    h = M3._kantenlaenge(model, koerper, h, log)
    teilung = M3.Linienteilung(model, flaechen, h, h_linien, h_flaechen, gemeinsam)
    L, grund_nein = _lagen(model, erk, teilung, h)
    if not L:
        C.say(log, f"Volumen {koerper.name}: nicht gesweept - {grund_nein}.")
        return []
    # Gepaarte Kappenlinien gleich teilen: der Deckel bekommt die Punkte des
    # Grundes verschoben, seine Linien muessen dieselbe Zahl Abschnitte tragen
    for la_, lb_ in erk["linien"].items():
        n_ = max(int(teilung.n.get(la_, 1)), int(teilung.n.get(lb_, 1)))
        teilung.n[la_] = n_
        teilung.n[lb_] = n_
    # ---- Grundflaeche(n) -----------------------------------------------------
    basis = _grundnetz(model, koerper, gruppe, teilung, erk, log)
    if basis is None:
        return []
    P, kenn, je_flaeche = basis["P"], basis["kenn"], basis["je_flaeche"]
    c, e1, e2, n = _rahmen(P, richtung_von(P, abb))
    P2 = np.stack([(P - c) @ e1, (P - c) @ e2], axis=1)
    vierecke = np.vstack([jf["vierecke"] for jf in je_flaeche]) if je_flaeche else np.zeros((0, 4), int)
    dreiecke = np.vstack([jf["dreiecke"] for jf in je_flaeche]) if je_flaeche else np.zeros((0, 3), int)
    flaeche_je_viereck = [jf["flaeche"] for jf in je_flaeche for _q in range(len(jf["vierecke"]))]
    flaeche_je_dreieck = [jf["flaeche"] for jf in je_flaeche for _d in range(len(jf["dreiecke"]))]
    # Flaecheninhalt in der Ebene (fuer die Rauminhaltsprobe)
    A_grund = 0.0
    if len(vierecke):
        q0, q1, q2, q3 = (P2[vierecke[:, i]] for i in range(4))
        A_grund += 0.5 * float(np.abs((q0[:, 0] * q1[:, 1] - q1[:, 0] * q0[:, 1]) + (q1[:, 0] * q2[:, 1] - q2[:, 0] * q1[:, 1])
                                       + (q2[:, 0] * q3[:, 1] - q3[:, 0] * q2[:, 1]) + (q3[:, 0] * q0[:, 1] - q0[:, 0] * q3[:, 1])).sum())
    if len(dreiecke):
        a_, b_, d_ = P2[dreiecke[:, 0]], P2[dreiecke[:, 1]], P2[dreiecke[:, 2]]
        A_grund += 0.5 * float(np.abs((b_[:, 0] - a_[:, 0]) * (d_[:, 1] - a_[:, 1]) - (d_[:, 0] - a_[:, 0]) * (b_[:, 1] - a_[:, 1])).sum())
    # ---- Kanten des Randes -> Wandflaeche ----------------------------------
    # Die Randpunkte werden ueber die Koordinate im Netz gefunden (KD-Baum):
    # bei einer Kappen-Gruppe stehen sie nicht mehr vorn im Punktfeld.
    baum = cKDTree(P)
    kante_wand: dict = {}                    # gerichtete Randkante -> Grundlinie (beide Richtungen)
    wand_kanten: dict = {}                   # Grundlinie -> ihre Randkanten in Ringrichtung
    rand_punkte: set = set()
    for lin in ringe:
        zug = _linienzug_herkunft(teilung, model, lin)
        if zug is None:
            C.say(log, f"Volumen {koerper.name}: nicht gesweept - Rand der Grundfläche schließt nicht.")
            return []
        pts, herkunft, _k = zug
        d_, idx = baum.query(pts)
        if len(pts) and d_.max() > erk["tol"] * 10 + 1e-12:
            C.say(log, f"Volumen {koerper.name}: nicht gesweept - Randpunkte der Grundfläche "
                       "fehlen im Flächennetz.")
            return []
        m = len(pts)
        for i in range(m):
            a_, b_ = int(idx[i]), int(idx[(i + 1) % m])
            kante_wand[(a_, b_)] = herkunft[i]
            kante_wand[(b_, a_)] = herkunft[i]
            wand_kanten.setdefault(herkunft[i], []).append((a_, b_))
            rand_punkte.add(a_)
    if set(wand_kanten) != set(erk["waende"]):
        C.say(log, f"Volumen {koerper.name}: nicht gesweept - Randlinien der Grundfläche und Wände "
                   "passen nicht zusammen.")
        return []
    # ---- Knoten je Lage ---------------------------------------------------
    mat = koerper.material or C.ensure_material(model, log=log)
    schritt = t / float(L)                   # nur noch fuer die Wandnetze der reinen Verschiebung
    knoten = np.zeros((L + 1, len(P)), int)
    zug_kenn = [[None] * len(P) for _ in range(L + 1)]
    for i in range(len(P)):
        zug_kenn[0][i] = kenn[i]
        zug_kenn[L][i] = _deckel_kennung(model, erk, kenn[i], teilung)
        if kenn[i] is not None and kenn[i][0] == "K" and int(kenn[i][1]) in erk["mantel"]:
            for k in range(1, L):
                zug_kenn[k][i] = _mantel_kennung(model, erk, int(kenn[i][1]), k, L)
    wand_von_punkt = {}
    for (i, j), lin in kante_wand.items():
        wand_von_punkt.setdefault(i, erk["waende"][lin].name)
    # Betriebsart "sauber": erst pruefen, dann einbauen - ein Koerper mit
    # einem verzerrten oder umgeklappten Element wird gar nicht gesweept
    if betriebsart(model) == "sauber" or nur_pruefen:
        X_lagen = np.stack([_abbilden(P, abb, k / float(L)) for k in range(L + 1)])
        sauber, grund_s, tf, wf = sauber_pruefen(X_lagen, vierecke, dreiecke)
        if nur_pruefen:
            return (sauber, grund_s, tf, wf)
        if not sauber:
            C.say(log, f"Volumen {koerper.name}: nicht gesweept (Betriebsart „sauber“) - {grund_s}; "
                       "der freie Vernetzer übernimmt, Übergang über Pyramiden.")
            return []
        C.say(log, f"Volumen {koerper.name}: sauber gesweept - größter Trapezfehler {tf:.1f}° "
                   f"(Grenze {TRAPEZ_GRENZE:.1f}°), Winkelfehler {wf:.1f}°")
    for k in range(L + 1):
        X = _abbilden(P, abb, k / float(L))
        if k == 0:
            fl = list(basis["flaeche_von_punkt"])
        elif k == L:
            fl = [deckel.name] * len(P)
        else:
            fl = [wand_von_punkt.get(i) if i in rand_punkte else None for i in range(len(P))]
        knoten[k] = _knoten_anlegen(model, koerper, X, zug_kenn[k], fl, cache)
    # ---- Elemente ---------------------------------------------------------
    els_hex, els_keil = [], []
    for k in range(L):
        u, o = knoten[k], knoten[k + 1]
        for q in vierecke:
            els_hex.append(model.add_element(
                "hex8", [int(u[q[0]]), int(u[q[1]]), int(u[q[2]]), int(u[q[3]]),
                         int(o[q[0]]), int(o[q[1]]), int(o[q[2]]), int(o[q[3]])], mat, group=koerper.name))
        for tr in dreiecke:
            els_keil.append(model.add_element(
                "pent6", [int(u[tr[0]]), int(u[tr[1]]), int(u[tr[2]]),
                          int(o[tr[0]]), int(o[tr[1]]), int(o[tr[2]])], mat, group=koerper.name))
    els = els_hex + els_keil
    koerper.elemente = els
    # ---- Randseiten: Grund, Deckel, Waende - unmittelbar, nicht gesucht ----
    weg = set(int(e) for e in els)
    for f in flaechen:
        f.randseiten = [x for x in (f.randseiten or []) if int(x[0]) not in weg]
    n_q, n_d = len(vierecke), len(dreiecke)
    seite_hex = {(0, 1): 2, (1, 2): 3, (2, 3): 4, (3, 0): 5}
    seite_keil = {(0, 1): 2, (1, 2): 3, (2, 0): 4}
    for k in range(L):
        for qi, q in enumerate(vierecke):
            e = els_hex[k * n_q + qi]
            if k == 0:
                flaeche_je_viereck[qi].randseiten.append([e, 0])
            if k == L - 1:
                deckel.randseiten.append([e, 1])
            for (a_, b_), s_ in seite_hex.items():
                lin = kante_wand.get((int(q[a_]), int(q[b_])))
                if lin is not None:
                    erk["waende"][lin].randseiten.append([e, s_])
        for ti, tr in enumerate(dreiecke):
            e = els_keil[k * n_d + ti]
            if k == 0:
                flaeche_je_dreieck[ti].randseiten.append([e, 0])
            if k == L - 1:
                deckel.randseiten.append([e, 1])
            for (a_, b_), s_ in seite_keil.items():
                lin = kante_wand.get((int(tr[a_]), int(tr[b_])))
                if lin is not None:
                    erk["waende"][lin].randseiten.append([e, s_])
    # ---- Vorgegebene Flaechennetze fuer die Nachbarn -----------------------
    # (Punkte, Dreiecke, Kennung, Vierecke, restliche Dreiecke): wer nur
    # Dreiecke braucht, liest die ersten drei; ein zweiter gesweepter Koerper
    # an derselben Flaeche nimmt die Vierecke und legt dieselben Hexaeder.
    netze = getattr(model, "flaechennetze", None)
    if netze is None:
        netze = model.flaechennetze = {}
    for jf in je_flaeche:
        netze[jf["flaeche"].name] = (np.asarray(jf["P"], float).copy(), np.asarray(jf["T"], int).copy(),
                                     list(jf["kenn"]), np.asarray(jf["Q"], int).copy(), np.asarray(jf["D"], int).copy())
    T_voll = _dreiecke_aus(P2, vierecke, dreiecke)
    netze[deckel.name] = (_abbilden(P, abb, 1.0), T_voll.copy(), list(zug_kenn[L]),
                          vierecke.copy(), dreiecke.copy())
    for lin, wand in erk["waende"].items():
        folge = _randfolge(wand_kanten[lin])
        WP, WT, WK, WQ = _wandnetz(P, folge, abb, L, zug_kenn)
        netze[wand.name] = (WP, WT, WK, WQ, np.zeros((0, 3), int))
    # ---- Rauminhalt: Grundflaeche mal Hoehe gegen die Elemente ---------------
    from .elements.solid import solid_volume
    # Rauminhalt: Grundflaeche mal Hoehe - beim verjuengten Zug der
    # Pyramidenstumpf h/3 * (A1 + A2 + sqrt(A1*A2)) mit A2 = k^2 * A1.
    if abb[0] == "d":
        # Drehkoerper: die Guldinsche Regel - Grundflaeche mal Weg ihres
        # Schwerpunkts, also A * phi * r_s mit r_s dem Achsabstand.
        _tag, achse_p, achse_d, phi = abb
        rel = P.mean(axis=0) - np.asarray(achse_p, float)
        r_s = float(np.linalg.norm(rel - float(rel @ np.asarray(achse_d, float)) * np.asarray(achse_d, float)))
        V_soll = A_grund * abs(float(phi)) * r_s
    else:
        k_ab = massstab_von(abb)
        hoehe = abs(float(n @ t))
        V_soll = (A_grund * hoehe if abs(k_ab - 1.0) < 1e-9
                  else hoehe / 3.0 * A_grund * (1.0 + k_ab ** 2 + k_ab))
    V_ist = float(sum(solid_volume(model.elements[e].typ, model.nodes[model.elements[e].nodes]) for e in els))
    abw = abs(V_ist - V_soll) / V_soll if V_soll > 0 else 1.0
    # ---- Protokoll --------------------------------------------------------
    koerper.kommentar = (f"{len(els_hex)} Hexaeder + {len(els_keil)} Keile (gesweept, {L} Lagen)")
    koerper.randtreue = 1.0
    koerper.netzgrund = ""
    koerper.netzkanten = []
    anteil = 100.0 * len(els_hex) / max(1, len(els))
    grundname = grund.name if len(gruppe) == 1 else " + ".join(f.name for f in gruppe)
    C.say(log, f"Volumen {koerper.name}: {len(els_hex)} Hexaeder (hex8) + {len(els_keil)} Keile (pent6) "
               f"gesweept - Grundfläche {grundname} → {deckel.name}, {L} Lagen à "
               f"{np.linalg.norm(schritt) * 1e3:.1f} mm, Kantenlänge {h * 1e3:.0f} mm, "
               f"{int(knoten.size)} Knoten, Hexaederanteil {anteil:.1f} %")
    C.say(log, f"  Volumen {V_ist:.6g} m^3 gegen {V_soll:.6g} m^3 aus Grundfläche mal Höhe "
               f"(Abweichung {abw * 100:.3f} %)")
    if abw > 1e-6:
        C.warn(log, f"  Volumen {koerper.name}: das gesweepte Netz füllt den Körper nicht genau "
                    f"(Abweichung {abw * 100:.3f} %)")
    return els


def _randfolge(kanten: list) -> list:
    """Die Randpunkte einer Grundlinie in Ringreihenfolge aus ihren gerichteten
    Randkanten (a -> b); eine geschlossene Linie wiederholt den Anfang."""
    if not kanten:
        return []
    naechster = {a: b for a, b in kanten}
    anfaenge = [a for a in naechster if a not in naechster.values()]
    start = anfaenge[0] if anfaenge else kanten[0][0]
    folge = [start]
    for _ in range(len(kanten)):
        nxt = naechster.get(folge[-1])
        if nxt is None:
            break
        folge.append(nxt)
        if nxt == start:
            break
    return folge


def _wandnetz(P: np.ndarray, folge: list, abb: tuple, L: int, zug_kenn: list) -> tuple:
    """Das strukturierte Netz einer Wand: Randpunkte der Grundlinie x Lagen,
    Vierecke in zwei Dreiecke (kuerzere Diagonale) - fuer den Nachbarn; dazu
    die Vierecke selbst fuer einen gesweepten Nachbarn."""
    m = len(folge)
    WP = np.vstack([_abbilden(P[folge], abb, k / float(L)) for k in range(L + 1)])
    WK = [zug_kenn[k][i] for k in range(L + 1) for i in folge]
    T, Q = [], []
    for k in range(L):
        for s in range(m - 1):
            a, b = k * m + s, k * m + s + 1
            c, d = (k + 1) * m + s + 1, (k + 1) * m + s
            Q.append((a, b, c, d))
            if np.linalg.norm(WP[a] - WP[c]) <= np.linalg.norm(WP[b] - WP[d]):
                T += [(a, b, c), (a, c, d)]
            else:
                T += [(a, b, d), (b, c, d)]
    return WP, np.asarray(T, int).reshape(-1, 3), WK, np.asarray(Q, int).reshape(-1, 4)


def _dreiecke_aus(P2: np.ndarray, vierecke: np.ndarray, dreiecke: np.ndarray) -> np.ndarray:
    """Vierecke ueber die kuerzere Diagonale teilen, Dreiecke uebernehmen."""
    T = [tuple(int(v) for v in tr) for tr in dreiecke]
    for q in vierecke:
        a, b, c, d = (int(v) for v in q)
        if np.linalg.norm(P2[a] - P2[c]) <= np.linalg.norm(P2[b] - P2[d]):
            T += [(a, b, c), (a, c, d)]
        else:
            T += [(a, b, d), (b, c, d)]
    return np.asarray(T, int).reshape(-1, 3)


def _knoten_anlegen(model: Model, koerper, X: np.ndarray, kenn: list, flaechen: list,
                    cache: dict) -> np.ndarray:
    """Knoten einer Lage anlegen - mit denselben Schluesseln wie
    :func:`mesher3d._knoten_anlegen`, damit ein Nachbar dieselben Knoten
    findet: Linienpunkte ueber ihre Kennung, Flaechenpunkte ueber (Flaeche,
    Koordinate), Geometrieknoten ueber die Koordinate."""
    tol = 1e-9

    def schluessel(p):
        return (round(float(p[0]) / tol), round(float(p[1]) / tol), round(float(p[2]) / tol))
    vorhanden: dict = {}
    for fname in (koerper.flaechen or []):
        f = model.flaechen.get(fname)
        if f is None:
            continue
        for lname in list(f.linien or []) + [x for loch in (f.oeffnungen or []) for x in loch]:
            ln = model.lines.get(lname)
            if ln is None:
                continue
            for k in ln.nodes:
                if 0 <= int(k) < model.nn:
                    vorhanden.setdefault(schluessel(model.nodes[int(k)]), int(k))
    neu = np.full(len(X), -1, int)
    neue_punkte, neue_idx = [], []
    naechste = int(model.nn)
    for i in range(len(X)):
        p = X[i]
        s = schluessel(p)
        merk = kenn[i] if kenn[i] is not None else ((flaechen[i], s) if flaechen[i] else None)
        k = vorhanden.get(s)
        if k is None and cache is not None and merk is not None:
            k = cache.get(merk)
        if k is None:
            k = naechste
            naechste += 1
            neue_punkte.append(p)
            neue_idx.append(i)
            if cache is not None and merk is not None:
                cache[merk] = k
        neu[i] = k
    if neue_punkte:
        model.add_nodes(np.asarray(neue_punkte, float))
    return neu


# --------------------------------------------------------------------------
# Zerlegen an Fussabdruecken
# --------------------------------------------------------------------------
def _fussabdruecke(model: Model, koerper, namen: list, F, nr: int):
    """Die Aufsaetze auf der ebenen Flaeche F eines Koerpers: je Aufsatz die
    Flaechen, die nur ueber Oeffnungen von F mit dem Rest verbunden sind, und
    die **Schnittflaeche** (der Fussabdruck als ebene Flaeche in F). Eine
    Nabe auf einer Platte, der duennere Teil einer abgesetzten Welle an der
    Schulter, eine Rippe, die nicht durchlaeuft - alles, was RFEM als
    Oeffnung in der Tragflaeche und eigene Flaechen darueber modelliert.

    Ein Aufsatz, der auch den Aussenrand von F beruehrt, ist keiner (er
    setzt die Wand fort); eine Bohrung, die durch Aufsatz **und** Traeger
    laeuft, verbindet beide ueber ihre Mantelflaeche - dann gibt es keinen
    Schnitt, denn die Mantelflaeche muesste geteilt werden, und Linien dafuer
    gibt es nicht.
    """
    andere = [model.flaechen[x] for x in namen if x != F.name]
    vater = {f.name: f.name for f in andere}

    def wurzel(x):
        while vater[x] != x:
            vater[x] = vater[vater[x]]
            x = vater[x]
        return x
    an_linie: dict = {}
    for f in andere:
        for lname in _linien_von(f):
            an_linie.setdefault(lname, []).append(f.name)
    for fs in an_linie.values():
        for x in fs[1:]:
            ra, rb = wurzel(fs[0]), wurzel(x)
            if ra != rb:
                vater[ra] = rb
    komponenten: dict = {}
    for f in andere:
        komponenten.setdefault(wurzel(f.name), []).append(f.name)
    ketten = [list(F.linien or [])] + [list(loch) for loch in (F.oeffnungen or [])]
    for komp in komponenten.values():
        Lk = set()
        for x in komp:
            Lk |= _linien_von(model.flaechen[x])
        beruehrt = [j for j, kette in enumerate(ketten) if set(kette) & Lk]
        if not beruehrt or 0 in beruehrt:
            continue
        pts = {j: _schleifenpunkte(model, ketten[j]) for j in beruehrt}
        aussen = max(beruehrt, key=lambda j: float(np.linalg.norm(pts[j].max(axis=0) - pts[j].min(axis=0)))
                     if len(pts[j]) else 0.0)
        nr += 1
        S = Flaeche(f"{koerper.name}§{nr}", list(ketten[aussen]),
                    oeffnungen=[list(ketten[j]) for j in beruehrt if j != aussen],
                    material=F.material or koerper.material)
        yield list(komp), S


def schnitte_entfernen(model: Model, werk, knoten_auch: bool = True) -> None:
    """Die Hilfsgeometrie des Zerlegens wieder aus dem Modell nehmen - sie
    gehoert zu einem Vernetzungslauf, nicht zum Modell."""
    if werk is None:
        return
    if isinstance(werk, Schnittwerk):
        werk.zuruecknehmen(knoten_auch)
        return
    netze = getattr(model, "flaechennetze", None) or {}
    for S in werk:                          # aeltere Aufrufe mit einer Flaechenliste
        name = S if isinstance(S, str) else S.name
        model.flaechen.pop(name, None)
        netze.pop(name, None)


class Schnittwerk:
    """Was ein Schnitt im Modell angelegt hat - und wie es wieder verschwindet.

    Ein Schnitt an einer Ebene braucht neue Knoten, Linien und Flaechen. Sie
    sind **Hilfsgeometrie fuer diesen Lauf**: nach dem Vernetzen gehen die
    Linien und Flaechen wieder raus, die Knoten bleiben nur, wenn Elemente an
    ihnen haengen (sonst werden sie zurueckgenommen - sie waeren sonst
    „Knoten ohne Element" in der Abnahme).

    ``ersatz`` haelt fest, welche Teilflaechen aus welcher Randflaeche
    entstanden sind. Nach dem Vernetzen wandern deren **Randseiten** zurueck
    auf die Ausgangsflaeche: eine Flaechenlast auf ihr muss ankommen, auch
    wenn das Netz aus zwei Bloecken kam.
    """

    def __init__(self, model):
        self.model = model
        self.n0 = int(model.nn)
        self.flaechen: list = []
        self.linien: list = []
        self.ersatz: dict = {}
        self.zaehler = 0

    def marke(self, koerper) -> str:
        """Ein Name, der in diesem Lauf **nie wiederkehrt** - auch nicht nach
        dem Zuruecknehmen eines Versuchs. Vorher hiess der Fussabdruck nach
        der Zahl der Schnitte (``len(schnitte)``): nach einem verworfenen
        Versuch war die Zahl wieder dieselbe, der neue Schnitt bekam den
        alten Namen, und das Zuruecknehmen ueber ``schnitte.index(name)``
        raeumte den gueltigen mit weg - KeyError 'V30§2' an fuenf der sechs
        dicken Drehlagerkoerper (gemessen 23.09.2026)."""
        self.zaehler += 1
        return f"{koerper.name}§{self.zaehler}"

    def flaeche(self, f):
        self.model.flaechen[f.name] = f
        self.flaechen.append(f.name)
        return f

    def linie(self, name, knoten):
        from .model import Line
        self.model.lines[name] = Line(name, [int(x) for x in knoten])
        self.linien.append(name)
        return name

    def stand(self) -> tuple:
        """Merkzettel vor einem Versuch - siehe :meth:`zurueck_bis`."""
        return (len(self.flaechen), len(self.linien), int(self.model.nn))

    def zurueck_bis(self, stand: tuple) -> None:
        """Alles zuruecknehmen, was seit ``stand`` entstanden ist.

        Ein Schnittversuch, der nichts taugt, darf keine Spur hinterlassen:
        sonst sammeln sich bei mehreren Ebenen Flaechen im Modell, die zu
        keinem Koerper gehoeren, und der naechste Versuch findet sie als
        vermeintliche Nachbarn wieder.
        """
        nf, nl, nn = stand
        netze = getattr(self.model, "flaechennetze", None) or {}
        for name in self.flaechen[nf:]:
            self.model.flaechen.pop(name, None)
            netze.pop(name, None)
        for name in self.linien[nl:]:
            self.model.lines.pop(name, None)
        del self.flaechen[nf:]
        del self.linien[nl:]
        if int(self.model.nn) > nn:
            self.model.nodes = self.model.nodes[:nn]
        bleibt = set(self.flaechen)
        for orig in list(self.ersatz):
            rest = [t for t in self.ersatz[orig] if t in bleibt]
            if rest:
                self.ersatz[orig] = rest
            else:
                self.ersatz.pop(orig)

    def erschoepft(self) -> bool:
        """Ist das Budget fuer diesen Koerper aufgebraucht (ZERLEGEN_ZEIT_S,
        ZERLEGEN_VERSUCHE)? Dann wird nicht weiter probiert, sondern gemeldet."""
        import time as _time
        start = getattr(self, "start", None)
        if start is not None and _time.time() - start > ZERLEGEN_ZEIT_S:
            self.abgebrochen = f"Zeit ({ZERLEGEN_ZEIT_S:.0f} s)"
            return True
        if getattr(self, "versuche", 0) >= ZERLEGEN_VERSUCHE:
            self.abgebrochen = f"{ZERLEGEN_VERSUCHE} Versuche"
            return True
        return False

    def zuruecknehmen(self, knoten_auch: bool = True) -> None:
        """Die Hilfsgeometrie wieder aus dem Modell nehmen."""
        netze = getattr(self.model, "flaechennetze", None) or {}
        for name in self.flaechen:
            self.model.flaechen.pop(name, None)
            netze.pop(name, None)
        for name in self.linien:
            self.model.lines.pop(name, None)
        if knoten_auch and int(self.model.nn) > self.n0:
            # Nur, wenn seither nichts anderes Knoten angelegt hat - sonst
            # verschoeben sich fremde Nummern. Genau das ist der Fall, wenn
            # der Schnitt nichts gebracht hat und gar nicht vernetzt wurde.
            self.model.nodes = self.model.nodes[:self.n0]
        # In place leeren, nicht neu binden: zerlegen() haelt ``schnitte`` als
        # Alias auf diese Liste - neu gebunden lief der Fussabdruck nach dem
        # Ebenenschnitt auf eine veraltete Liste ("'V30§16' is not in list",
        # Drehlager 23.09.2026).
        del self.flaechen[:]
        del self.linien[:]
        self.ersatz.clear()

    def randseiten_zurueck(self) -> int:
        """Die Randseiten der Teilflaechen auf die Ausgangsflaechen legen.

        Von hinten nach vorn, denn eine Teilflaeche kann selbst wieder geteilt
        worden sein (erst der Schnitt, dann das Angleichen der Kappenlinien):
        ihre Kinder sind spaeter eingetragen und muessen zuerst bei ihr
        ankommen, bevor sie weitergibt.
        """
        n = 0
        for orig, teile in reversed(list(self.ersatz.items())):
            f = self.model.flaechen.get(orig)
            if f is None:
                continue
            for t in teile:
                tf = self.model.flaechen.get(t)
                if tf is None:
                    continue
                f.randseiten = list(f.randseiten or []) + list(tf.randseiten or [])
                n += len(tf.randseiten or [])
        return n


def _ebene_der_flaeche(model: Model, f) -> "tuple | None":
    """(Punkt, Normale) einer **ebenen** Randflaeche - sonst None."""
    from .mesher3d import ist_eben, ausgleichsebene
    try:
        P = _schleifenpunkte(model, list(f.linien or []))
    except Exception:                       # noqa: BLE001
        return None
    if len(P) < 3 or not ist_eben(P):
        return None
    c, _e1, _e2, n, _abw = ausgleichsebene(P)
    return (np.asarray(c, float), np.asarray(n, float))


def schnittebenen(model: Model, koerper, tol: float) -> list:
    """Die Ebenen von Randflaechen, die den Koerper wirklich **trennen** -
    die Kandidaten fuer einen Schnitt.

    Warum gerade sie: an einer einspringenden Kante liegt die Trennung
    zwischen zwei Bloecken immer in der Ebene einer der beiden anliegenden
    Flaechen. Eine Rippe auf einer Platte wird an der Ebene der Plattendecke
    abgeschnitten, ein Absatz an der Ebene seiner Schulter. Andere Ebenen
    muss man nicht raten.
    """
    flaechen = [model.flaechen.get(x) for x in (koerper.flaechen or [])]
    if any(f is None for f in flaechen):
        return []
    try:
        alle = np.vstack([_schleifenpunkte(model, list(f.linien or [])) for f in flaechen])
    except Exception:                       # noqa: BLE001
        return []
    aus = []

    def dazu(c, n):
        d = (alle - c) @ n
        if float(d.max()) <= tol or float(d.min()) >= -tol:
            return                          # trennt nicht - der Koerper liegt auf einer Seite
        if any(abs(float(n @ n2)) > 1.0 - 1e-9 and abs(float((c2 - c) @ n)) <= tol
               for c2, n2 in aus):
            return                          # dieselbe Ebene schon dabei
        aus.append((c, n))
    for f in flaechen:
        e = _ebene_der_flaeche(model, f)
        if e is not None:
            dazu(*e)
    # Und die Ebenen der **Boegen**: ein Zwischenkreis, an dem der Mantel eines
    # Zylinders in zwei Ringe geteilt ist (weil dort ein Nachbar anliegt),
    # gehoert keiner Flaeche - seine Ebene ist trotzdem die Trennung
    # (23 von 40 nicht sweepbaren Drehlagerkoerpern, 23.09.2026).
    for name in sorted({x for f in flaechen for sch in _randschleifen(f) for x in sch}):
        ln = model.lines.get(name)
        if ln is None or (ln.typ or "polyline") != "arc":
            continue
        try:
            P = np.asarray(ln.punkte(model, 5), float).reshape(-1, 3)
        except Exception:                   # noqa: BLE001
            continue
        if len(P) < 3:
            continue
        n = np.cross(P[2] - P[0], P[-1] - P[0])
        if float(np.linalg.norm(n)) <= 1e-30:
            n = np.cross(P[1] - P[0], P[-1] - P[0])
        laenge = float(np.linalg.norm(n))
        if laenge <= 1e-30:
            continue
        dazu(P.mean(axis=0), n / laenge)
    return aus


def _kantenseiten(P: np.ndarray, art: list, c: np.ndarray, n: np.ndarray) -> "list | None":
    """Je **Kante** des Umlaufs die Seite der Schnittebene: +1 oder -1.

    Die Zeichen der Ecken allein genuegen nicht. Eine Kante, die **in** der
    Ebene liegt (beide Ecken darauf), kann zu jeder der beiden Seiten
    gehoeren: an der T-foermigen Stirnflaeche einer Rippe liegen zwei solche
    Kanten in der Ebene, und **beide** gehoeren zur Platte darunter, obwohl
    die eine von unten, die andere von oben angelaufen wird. Wer nach den
    Ecken geht, schlaegt eine davon der Rippe zu und bekommt zwei Teile, die
    nicht aneinanderpassen (22.09.2026).

    Entschieden wird darum an der Flaeche selbst: einen kleinen Schritt von
    der Kantenmitte ins **Innere der Flaeche**, und die Seite dieses Punktes
    zaehlt. Das ist dieselbe Frage wie „wo liegt das Material?", nur lokal
    und ohne Strahlenzaehlung.
    """
    from .mesher3d import ausgleichsebene, _in_polygon_2d
    m = len(P)
    if m < 3 or len(art) != m:
        return None
    cf, e1, e2, _nf, _abw = ausgleichsebene(P)
    Q = np.stack([(P - cf) @ e1, (P - cf) @ e2], axis=1)
    gross = float(np.linalg.norm(Q.max(axis=0) - Q.min(axis=0)))
    eps = 1e-4 * max(gross, 1e-12)
    aus = []
    for i in range(m):
        j = (i + 1) % m
        if art[i] != 0 or art[j] != 0:
            aus.append(1 if max(art[i], art[j]) > 0 else -1)
            continue
        e = Q[j] - Q[i]
        le = float(np.linalg.norm(e))
        if le <= 0.0:
            return None
        w = np.array([-e[1], e[0]]) / le            # senkrecht dazu, in der Flaeche
        mitte = 0.5 * (Q[i] + Q[j])
        for vorz in (1.0, -1.0):
            q2 = mitte + vorz * eps * w
            if bool(_in_polygon_2d(q2[None, :], [Q])[0]):
                q3 = cf + q2[0] * e1 + q2[1] * e2
                aus.append(1 if float((q3 - c) @ n) > 0.0 else -1)
                break
        else:
            return None                             # entartet - lieber nicht schneiden
    return aus


def _laeufe_aus_kanten(seiten: list) -> dict:
    """Aus der Seite je Kante die Laeufe je Seite: ``{Seite: [[Ecken], ...]}``.

    Ein Lauf endet, wo die Seite wechselt; geschlossen wird er durch die
    **Schnittstrecke** von seiner letzten zu seiner ersten Ecke.
    """
    m = len(seiten)
    if m < 3:
        return {1: [], -1: []}
    if len(set(seiten)) == 1:
        return {seiten[0]: [list(range(m))], -seiten[0]: []}
    start = next(i for i in range(m) if seiten[i] != seiten[(i - 1) % m])
    aus = {1: [], -1: []}
    lauf = []
    for k in range(m):
        i = (start + k) % m
        lauf.append(i)
        if seiten[(i + 1) % m] != seiten[i]:
            aus[seiten[i]].append([lauf[0]] + [(x + 1) % m for x in lauf])
            lauf = []
    return aus


def _randschleifen(f) -> list:
    """Alle Randschleifen einer Flaeche - Aussenrand und Oeffnungen."""
    return [list(f.linien or [])] + [list(o or []) for o in (f.oeffnungen or [])]


def _geschlossene_schale(model: Model, namen: list) -> bool:
    """Bilden diese Flaechen eine geschlossene Huelle?

    Jede Linie genau zweimal - das ist die Bedingung, und sie ist scharf.
    Sie ist der Pruefstein des Ebenenschnitts: sie faengt jede falsch
    zugeordnete Flaeche ab, bevor daraus ein gueltiger, aber **anderer**
    Koerper wird als der gemeinte. Genau diese Art Fehler hat der
    Quaderpfad am Rohrbogen stumm gemacht (22.09.2026).
    """
    zahl: dict = {}
    for x in namen:
        f = model.flaechen.get(x)
        if f is None:
            return False
        for schleife in _randschleifen(f):
            for l in schleife:
                zahl[l] = zahl.get(l, 0) + 1
    return bool(zahl) and all(v == 2 for v in zahl.values())


def _fremde_flaechen(model: Model, koerper) -> set:
    """Die Randflaechen **anderer** Koerper - auch die, die dieser mitbenutzt.

    Was ihnen gehoert, wird weder geschnitten noch neu geteilt: eine Linie,
    die ein Nachbar fuehrt, hier in drei Stuecke zu zerlegen, risse die Fuge
    auf - sein Netz kennt die Stuecke nicht.
    """
    return {x for kk in (getattr(model, "koerper", {}) or {}).values()
            if kk is not koerper for x in (kk.flaechen or [])}


def _kette(model: Model, linien: list) -> "list | None":
    """Einen **offenen** Zug gerader Linien ordnen: [(Name, von, nach), ...]."""
    enden, grad = {}, {}
    for name in linien:
        e = _linienenden(model, name)
        if e is None:
            return None
        enden[name] = (int(e[0]), int(e[1]))
        for k in enden[name]:
            grad.setdefault(k, []).append(name)
    spitzen = sorted(k for k, v in grad.items() if len(v) == 1)
    if len(spitzen) != 2:
        return None
    jetzt, offen, aus = spitzen[0], set(linien), []
    while offen:
        naechste = [x for x in grad.get(jetzt, ()) if x in offen]
        if len(naechste) != 1:
            return None
        name = naechste[0]
        offen.discard(name)
        a, b = enden[name]
        if a != jetzt:
            a, b = b, a
        aus.append((name, a, b))
        jetzt = b
    return aus


def _punkt_auf_linie(model: Model, name: str, p: np.ndarray, tol: float) -> "float | None":
    """Liegt ``p`` **mitten** auf der geraden Linie? Parameter in (0, 1)."""
    if _gerade(model, name) is None:
        return None
    a, b = _linienenden(model, name)
    pa, pb = model.nodes[int(a)], model.nodes[int(b)]
    e = pb - pa
    l2 = float(e @ e)
    if l2 <= 0.0:
        return None
    t = float((np.asarray(p, float) - pa) @ e) / l2
    if not (0.0 < t < 1.0):
        return None
    if float(np.linalg.norm(pa + t * e - p)) > tol:
        return None
    if min(float(np.linalg.norm(p - pa)), float(np.linalg.norm(p - pb))) <= tol:
        return None
    return t


def _wand_teilen(model: Model, linien: list, la: set, lb: set, abb: tuple,
                 werk: "Schnittwerk", tol: float, marke: str, material) -> "list | None":
    """Eine Wand, deren Grund- und Deckelseite in mehrere Linien zerfaellt, in
    Vierecke zerlegen - eine Wand je Linienpaar, mit neuer Mantellinie
    dazwischen. Erst dadurch bleibt die Wandpruefung so streng wie sie ist:
    jede Wand aus genau vier Linien."""
    grund = [x for x in linien if x in la]
    deckel = [x for x in linien if x in lb]
    senk = [x for x in linien if x not in la and x not in lb]
    if len(senk) != 2 or len(grund) != len(deckel) or len(grund) < 2:
        return None
    ka, kb = _kette(model, grund), _kette(model, deckel)
    if ka is None or kb is None:
        return None
    p0 = _abbilden(model.nodes[[ka[0][1]]], abb)[0]
    if float(np.linalg.norm(p0 - model.nodes[kb[0][1]])) > tol:
        kb = [(n_, b_, a_) for n_, a_, b_ in reversed(kb)]
        if float(np.linalg.norm(p0 - model.nodes[kb[0][1]])) > tol:
            return None
    paare = {}
    for name in senk:
        e = _linienenden(model, name)
        if e is None:
            return None
        paare[frozenset((int(e[0]), int(e[1])))] = name
    m_a = paare.get(frozenset((ka[0][1], kb[0][1])))
    m_e = paare.get(frozenset((ka[-1][2], kb[-1][2])))
    if m_a is None or m_e is None or m_a == m_e:
        return None
    mantel = [m_a]
    for i in range(len(ka) - 1):
        unten, oben = ka[i][2], kb[i][2]
        if float(np.linalg.norm(_abbilden(model.nodes[[unten]], abb)[0]
                                - model.nodes[oben])) > tol:
            return None
        mantel.append(werk.linie(f"{marke}M{len(werk.linien) + 1}", [unten, oben]))
    mantel.append(m_e)
    aus = []
    for i in range(len(ka)):
        name = f"{marke}W{len(werk.flaechen) + 1}"
        werk.flaeche(Flaeche(name, [ka[i][0], mantel[i + 1], kb[i][0], mantel[i]],
                             material=material))
        aus.append(name)
    return aus


def kappenlinien_angleichen(model: Model, namen: list, werk: "Schnittwerk",
                            tol: float, fremd=()) -> "list | None":
    """Grund und Deckel eines Blocks **gleich** teilen - Rueckgabe die neue
    Flaechenliste oder None.

    Warum das noetig ist: ein Schnitt teilt eine Randflaeche, und die
    Schnittlinie setzt zwei neue Ecken in die eine Kappenschleife. Die andere
    hat sie nicht. Die Kappen decken sich weiterhin (das misst
    :func:`_deckungsgleich_abb` an der Kurve), aber die Wandpruefung sucht zu
    **jeder** Grundlinie genau eine Deckellinie und findet drei. Am
    Pruefkoerper „Platte mit Randrippe" blieb der Plattenblock darum
    tetraedrisch, obwohl er ein Quader ist (22.09.2026).

    Angeglichen wird, indem die fehlenden Ecken auf die andere Schleife
    abgebildet und deren Linien dort geteilt werden; die Waende dazwischen
    zerfallen mit. Angefasst werden nur Linien, die **allein diesem Block**
    gehoeren - sonst risse der Schnitt die Fuge zum Nachbarn auf.
    """
    flaechen = [model.flaechen.get(x) for x in namen]
    if any(f is None for f in flaechen):
        return None
    kand = _kappen_kandidaten(model, flaechen, tol)
    for g in kand:
        for d in kand:
            if {f.name for f in g[0]} & {f.name for f in d[0]}:
                continue
            erg = _kappen_abbildung(model, g, d, tol)
            if erg is None:
                continue
            stand = werk.stand()
            neu = _angleichen_anwenden(model, namen, g, d, erg[0], erg[1],
                                       werk, tol, set(fremd))
            if neu is not None:
                return neu
            werk.zurueck_bis(stand)
    return None


def _angleichen_anwenden(model: Model, namen: list, grund: tuple, deckel: tuple,
                         abb: tuple, paarung: list, werk: "Schnittwerk",
                         tol: float, fremd: set) -> "list | None":
    """Ein Versuch mit **einem** Kappenpaar."""
    from .mesher3d import seiten_im_umlauf
    zurueck = _umkehr(abb)
    if zurueck is None:
        return None
    fl_g, schleifen_g, _p = grund
    fl_d, schleifen_d, _q = deckel
    marke = f"{namen[0]}§A{len(werk.flaechen) + len(werk.linien)}"
    teilung: dict = {}

    def suchen(sch_von, sch_nach, richtung):
        kv, kn = seiten_im_umlauf(model, sch_von), seiten_im_umlauf(model, sch_nach)
        if not kv or not kn:
            return False
        ziel = sorted({k for _n, ks in kn for k in ks})
        Z = model.nodes[ziel]
        for _n, ks in kv:
            for k in ks:
                q = _abbilden(model.nodes[[int(k)]], richtung)[0]
                if float(np.min(np.linalg.norm(Z - q, axis=1))) <= tol:
                    continue
                for name, _ks2 in kn:
                    t_ = _punkt_auf_linie(model, name, q, tol)
                    if t_ is not None:
                        teilung.setdefault(name, []).append((t_, q))
                        break
                else:
                    return False            # das Bild liegt nirgends auf der Schleife
        return True

    for i, j in paarung:
        if not suchen(schleifen_g[i], schleifen_d[j], abb):
            return None
        if not suchen(schleifen_d[j], schleifen_g[i], zurueck):
            return None
    if not teilung:
        return None
    # ---- die Linien teilen ---------------------------------------------------
    for lin in teilung:
        for f in model.flaechen.values():
            if f.name in fremd and any(lin in sch for sch in _randschleifen(f)):
                return None                 # gehoert auch dem Nachbarn
    stuecke: dict = {}
    for lin, punkte in teilung.items():
        enden = _linienenden(model, lin)
        if enden is None:
            return None
        rein = []
        for t_, q in sorted(punkte, key=lambda x: x[0]):
            if not rein or t_ - rein[-1][0] > 1e-9:
                rein.append((t_, q))
        folge = [int(enden[0])]
        for _t, q in rein:
            folge.append(int(model.add_node(*[float(x) for x in q])))
        folge.append(int(enden[1]))
        stuecke[lin] = [werk.linie(f"{marke}L{len(werk.linien) + 1}",
                                   [folge[i], folge[i + 1]]) for i in range(len(folge) - 1)]
    # ---- die Flaechen neu bauen ---------------------------------------------
    la = {y for sch in schleifen_g for x in sch for y in (stuecke.get(x) or [x])}
    lb = {y for sch in schleifen_d for x in sch for y in (stuecke.get(x) or [x])}
    kappen = {f.name for f in fl_g} | {f.name for f in fl_d}
    aus = []
    for f in (model.flaechen[x] for x in namen):
        alt = _randschleifen(f)
        if not any(x in stuecke for sch in alt for x in sch):
            aus.append(f.name)
            continue
        neu = [[y for x in sch for y in (stuecke.get(x) or [x])] for sch in alt]
        if f.name in kappen:
            name = f"{marke}K{len(werk.flaechen) + 1}"
            werk.flaeche(Flaeche(name, neu[0], oeffnungen=[list(o) for o in neu[1:]],
                                 material=f.material))
            werk.ersatz.setdefault(f.name, []).append(name)
            aus.append(name)
            continue
        if len(neu) != 1:
            return None
        teile = _wand_teilen(model, neu[0], la, lb, abb, werk, tol, marke, f.material)
        if teile is None:
            return None
        werk.ersatz.setdefault(f.name, []).extend(teile)
        aus.extend(teile)
    return aus


def zerlegen_ebene(model: Model, koerper, werk: "Schnittwerk", tol: float) -> "list | None":
    """Den Koerper an einer Ebene in zwei Bloecke schneiden - der zweite Weg
    neben dem Fussabdruck.

    Rueckgabe ``[(Flaechennamen, Erkennung oder None), ...]`` fuer die erste
    Ebene, die zwei geschlossene Bloecke ergibt, von denen **mindestens
    einer** sweepbar ist; sonst None. Die dabei angelegte Hilfsgeometrie
    steht in ``werk``.

    Was der Fussabdruck nicht kann und das hier schon: eine Rippe, die bis an
    den **Rand** der Platte laeuft, haengt nicht ueber einer Oeffnung - ihr
    Fussabdruck beruehrt den Aussenrand der Deckflaeche, und genau das
    schliesst :func:`_fussabdruecke` aus (sonst waere der Schnitt keine
    geschlossene Flaeche). Der Ebenenschnitt trennt sie trotzdem.

    Grenzen, mit Absicht: nur gerade Linien mit zwei Knoten in den
    geschnittenen Flaechen, keine Oeffnung in ihnen, hoechstens eine
    Schnittflaeche, und **keine Flaeche, die einem zweiten Koerper gehoert** -
    sonst zerschnitte der Schnitt die Fuge zum Nachbarn.
    """
    from .mesher3d import gemeinsame_randflaechen
    gem_f, _gem_l = gemeinsame_randflaechen(model)
    flaechen = [model.flaechen.get(x) for x in (koerper.flaechen or [])]
    if any(f is None for f in flaechen):
        return None
    schwer = {x for x in (koerper.flaechen or []) if x in gem_f}
    for ebene in schnittebenen(model, koerper, tol):
        if werk.erschoepft():
            return None
        werk.versuche += 1
        aus = _an_ebene_teilen(model, koerper, flaechen, ebene, werk, tol, schwer)
        if aus is not None:
            return aus
    return None


def _an_ebene_teilen(model: Model, koerper, flaechen: list, ebene: tuple,
                     werk: "Schnittwerk", tol: float, gemeinsam: set) -> "list | None":
    """Ein Versuch mit **einer** Ebene; None, wenn sie nichts taugt.

    Eine Randflaeche, die ganz **in** der Ebene liegt, gehoert zu genau einem
    der beiden Bloecke - und welchem, sieht man ihr nicht an: die Deckflaeche
    einer Platte mit Rippe liegt in der Schnittebene, gehoert zur Platte, und
    ihre Nachbarn zeigen in beide Richtungen (die Plattenseiten nach unten,
    die Rippenwaende nach oben). Darum werden die Zuordnungen **durchprobiert**
    und die geschlossene Huelle entscheidet. Bei hoechstens drei solchen
    Flaechen sind das acht Versuche; darueber hinaus wird nicht geraten.
    """
    import itertools
    c, n = ebene
    lage: dict = {}
    for f in flaechen:
        try:
            d = np.concatenate([(_schleifenpunkte(model, sch) - c) @ n
                                for sch in _randschleifen(f) if sch])
        except Exception:                   # noqa: BLE001
            return None
        if len(d) < 3:
            return None
        if float(np.abs(d).max()) <= tol:
            lage[f.name] = 0                # koplanar
        elif float(d.min()) >= -tol:
            lage[f.name] = 1
        elif float(d.max()) <= tol:
            lage[f.name] = -1
        else:
            lage[f.name] = None             # muss geschnitten werden
    if not any(l is None for l in lage.values()):
        # Die Ebene schneidet keine Flaeche - dann trennt sie den Koerper
        # hoechstens an einer **vorhandenen Schleife** von Linien
        return _an_schleife_teilen(model, koerper, flaechen, ebene, werk, tol, lage)
    eben = [f.name for f in flaechen if lage[f.name] == 0]
    if len(eben) > 3:
        return None
    for wahl in itertools.product((-1, 1), repeat=len(eben)):
        stand = werk.stand()
        aus = _ebene_versuch(model, koerper, flaechen, ebene, werk, tol, gemeinsam,
                             lage, dict(zip(eben, wahl)))
        if aus is not None:
            return aus
        werk.zurueck_bis(stand)
    return None


def _an_schleife_teilen(model: Model, koerper, flaechen: list, ebene: tuple,
                        werk: "Schnittwerk", tol: float, lage: dict) -> "list | None":
    """Der Koerper zerfaellt an einer Ebene, in der **vorhandene** Linien einen
    geschlossenen Zug bilden, ohne dass eine Flaeche geschnitten wuerde.

    Der Fall: ein Zylinder, dessen Mantel axial in zwei Ringe geteilt ist -
    an der Zwischenkreislinie liegt ein Nachbar an, eine Flaeche gibt es
    dort nicht. Die Kappen passen, aber je Randlinie stehen **zwei** Waende
    uebereinander („4 Wandflaechen zu 2 Randlinien": 23 der 40 nicht
    sweepbaren Drehlagerkoerper, 23.09.2026). Die Schnittflaeche ist der
    Kreis selbst, aus den vorhandenen Linien; jede Linie darin trennt zwei
    Flaechen, die auf verschiedenen Seiten der Ebene liegen. Mehrere
    Schleifen ergeben eine Schnittflaeche mit Oeffnungen (Buchse: Aussen-
    und Innenkreis). Koplanare Flaechen gibt es hier nicht: sie laegen in
    der Ebene, und dann schnitte die Ebene den Koerper nicht.
    """
    c, n = ebene
    if any(l == 0 for l in lage.values()):
        return None
    nutzer: dict = {}
    for f in flaechen:
        for sch in _randschleifen(f):
            for l in sch:
                nutzer.setdefault(l, []).append(f.name)
    kanten = []
    for l, fl in nutzer.items():
        if len(fl) != 2 or lage[fl[0]] == lage[fl[1]]:
            continue
        ln = model.lines.get(l)
        if ln is None:
            continue
        try:
            P = np.asarray(ln.punkte(model, 8), float).reshape(-1, 3)
        except Exception:                   # noqa: BLE001
            return None
        if float(np.abs((P - c) @ n).max()) > tol:
            continue                        # die Linie liegt nicht in der Ebene
        kanten.append(l)
    if len(kanten) < 2:
        return None
    # Zu Schleifen ordnen
    from .mesher3d import seiten_im_umlauf
    offen = set(kanten)
    schleifen = []
    while offen:
        keim = offen.pop()
        gruppe = [keim]
        knoten = set(int(x) for x in _linienenden(model, keim) or ())
        geaendert = True
        while geaendert:
            geaendert = False
            for l in list(offen):
                e = _linienenden(model, l)
                if e is not None and (int(e[0]) in knoten or int(e[1]) in knoten):
                    gruppe.append(l)
                    knoten |= {int(e[0]), int(e[1])}
                    offen.discard(l)
                    geaendert = True
        if not seiten_im_umlauf(model, gruppe):
            return None                     # schliesst nicht
        schleifen.append(gruppe)
    # Aussenschleife: die mit der groessten Flaeche in der Ebene
    def flaeche_von(sch):
        P = _schleifenpunkte(model, sch)
        return abs(float(np.linalg.norm(np.cross(P - P.mean(axis=0), np.roll(P, -1, axis=0) - P.mean(axis=0)).sum(axis=0)))) / 2.0
    schleifen.sort(key=flaeche_von, reverse=True)
    werk.art = "an einer vorhandenen Schleife"
    name = werk.marke(koerper) + "S"
    werk.flaeche(Flaeche(name, list(schleifen[0]), oeffnungen=[list(x) for x in schleifen[1:]],
                         material=koerper.material))
    seiten = {1: [f.name for f in flaechen if lage[f.name] == 1],
              -1: [f.name for f in flaechen if lage[f.name] == -1]}
    bloecke = []
    for vorz in (1, -1):
        namen = seiten[vorz] + [name]
        if len(namen) < 4 or not _geschlossene_schale(model, namen):
            return None
        pseudo = Volumenkoerper(koerper.name, list(namen), material=koerper.material,
                                teilung=list(koerper.teilung or [4, 4, 4]))
        try:
            erk = erkennen(model, pseudo)
        except Exception:                   # noqa: BLE001
            erk = None
        bloecke.append((list(namen), erk))
    if not any(e is not None for _n, e in bloecke):
        return None
    return bloecke


def _ebene_versuch(model: Model, koerper, flaechen: list, ebene: tuple,
                   werk: "Schnittwerk", tol: float, gemeinsam: set,
                   lage: dict, wahl: dict) -> "list | None":
    """Eine Ebene und **eine** Zuordnung der koplanaren Flaechen."""
    from .mesher3d import seiten_im_umlauf
    c, n = ebene
    marke = werk.marke(koerper) + "E"
    knoten_cache: dict = {}
    linien_cache: dict = {}
    vorhandene_linien: dict = {}
    for f in flaechen:
        for schleife in _randschleifen(f):
            for name in schleife:
                ln = model.lines.get(name)
                if ln is not None and len(ln.nodes) == 2:
                    vorhandene_linien[frozenset((int(ln.nodes[0]), int(ln.nodes[1])))] = name

    def knoten(p):
        # Derselbe Kreuzungspunkt wird von beiden Flaechen an der Kante
        # berechnet, in Gleitkommazahlen um Bits verschieden. Gesucht wird
        # darum mit Toleranz, nicht ueber ein Rundungsgitter - auf dessen
        # Kante laegen sonst zwei Knoten, und die Huelle schloesse nicht.
        p = np.asarray(p, float)
        for k, q in knoten_cache.items():
            if float(np.linalg.norm(q - p)) <= tol:
                return k
        k = int(model.add_node(*[float(x) for x in p]))
        knoten_cache[k] = p
        return k

    def linie(a, b):
        key = frozenset((int(a), int(b)))
        if len(key) != 2:
            return None
        name = vorhandene_linien.get(key) or linien_cache.get(key)
        if name is None:
            name = f"{marke}L{len(linien_cache) + 1}"
            werk.linie(name, [a, b])
            linien_cache[key] = name
        return name

    fremd = _fremde_flaechen(model, koerper)
    seiten = {1: [], -1: []}
    nutzer: dict = {}                       # Linie -> Flaechen, die sie benutzen
    schnittkanten = set()                   # ungerichtet: die Raender der Schnittflaeche

    def dazu(name, seite, schleifen):
        seiten[seite].append(name)
        for schleife in schleifen:
            for l in schleife:
                nutzer.setdefault(l, []).append(name)

    for f in flaechen:
        l = lage[f.name]
        if l is not None:
            dazu(f.name, wahl[f.name] if l == 0 else l, _randschleifen(f))
            continue
        if f.name in gemeinsam or f.oeffnungen:
            return None                     # gemeinsame Flaeche oder Oeffnung: nicht schneiden
        stuecke = seiten_im_umlauf(model, list(f.linien or []))
        if not stuecke or any(len(ks) != 2 for _nm, ks in stuecke):
            return None                     # Bogen oder Polylinie
        ecken = [int(ks[0]) for _nm, ks in stuecke]
        d = (model.nodes[ecken] - c) @ n
        art = [0 if abs(x) <= tol else (1 if x > 0 else -1) for x in d]
        m_ = len(ecken)
        umlauf, umlauf_art = [], []
        for i in range(m_):
            umlauf.append(ecken[i])
            umlauf_art.append(art[i])
            j = (i + 1) % m_
            if art[i] * art[j] < 0:
                fa = d[i] / (d[i] - d[j])
                umlauf.append(knoten(model.nodes[ecken[i]]
                                     + (model.nodes[ecken[j]] - model.nodes[ecken[i]]) * fa))
                umlauf_art.append(0)
        seiten_kante = _kantenseiten(model.nodes[umlauf], umlauf_art, c, n)
        if seiten_kante is None:
            return None
        teile = _laeufe_aus_kanten(seiten_kante)
        if not teile[1] or not teile[-1]:
            return None
        werk.ersatz.setdefault(f.name, [])
        for vorz in (1, -1):
            for lauf in teile[vorz]:
                kn = []
                for i in lauf:
                    if not kn or umlauf[i] != kn[-1]:
                        kn.append(umlauf[i])
                if len(kn) > 2 and kn[0] == kn[-1]:
                    kn = kn[:-1]
                if len(kn) < 3:
                    return None
                linien = [linie(kn[i], kn[(i + 1) % len(kn)]) for i in range(len(kn))]
                if None in linien or len(set(linien)) != len(linien):
                    return None
                name = f"{marke}F{len(werk.flaechen) + 1}"
                werk.flaeche(Flaeche(name, linien, material=f.material or koerper.material))
                werk.ersatz[f.name].append(name)
                dazu(name, vorz, [linien])
                schnittkanten.add(frozenset((kn[-1], kn[0])))
    # ---- die Raender der Schnittflaeche, die aus koplanaren Flaechen kommen --
    # Eine Kante einer koplanaren Flaeche begrenzt den Schnitt genau dann, wenn
    # die Flaeche auf der **anderen** Seite dahinter liegt: an der Rippe sind das
    # die drei Kanten des Fussabdrucks in der Deckflaeche, nicht ihr Aussenrand.
    for name, sigma in wahl.items():
        for schleife in _randschleifen(model.flaechen[name]):
            for l in schleife:
                andere = [y for y in nutzer.get(l, ()) if y != name]
                if len(andere) != 1:
                    return None
                g = andere[0]
                if (g in seiten[-sigma]) and not (g in seiten[sigma]):
                    ln = model.lines.get(l)
                    if ln is None or len(ln.nodes) != 2:
                        return None
                    schnittkanten.add(frozenset((int(ln.nodes[0]), int(ln.nodes[1]))))
    if len(schnittkanten) < 3:
        return None
    # ---- die Schnittflaeche: ein Kantenzug, der sich schliesst ---------------
    nachbar: dict = {}
    for kante in schnittkanten:
        a, b = tuple(kante)
        nachbar.setdefault(a, []).append(b)
        nachbar.setdefault(b, []).append(a)
    if any(len(v) != 2 for v in nachbar.values()):
        return None                         # Verzweigung: mehr als ein Schnitt
    start = min(nachbar)
    kette, vorher, jetzt = [start], None, start
    while True:
        folge = [x for x in nachbar[jetzt] if x != vorher]
        if not folge:
            return None
        nx = folge[0]
        if nx == start:
            break
        if len(kette) > len(schnittkanten):
            return None
        kette.append(nx)
        vorher, jetzt = jetzt, nx
    if len(kette) != len(schnittkanten) or len(kette) < 3:
        return None                         # zwei getrennte Schnitte: hier nicht
    linien = [linie(kette[i], kette[(i + 1) % len(kette)]) for i in range(len(kette))]
    if None in linien or len(set(linien)) != len(linien):
        return None
    schnitt = f"{marke}S1"
    werk.art = "an einer Ebene"
    werk.flaeche(Flaeche(schnitt, linien, material=koerper.material))
    # ---- die beiden Bloecke -------------------------------------------------
    bloecke = []
    for vorz in (1, -1):
        namen = seiten[vorz] + [schnitt]
        if len(namen) < 4 or not _geschlossene_schale(model, namen):
            return None                     # die Zuordnung war falsch
        def bau(liste):
            return Volumenkoerper(koerper.name, list(liste), material=koerper.material,
                                  teilung=list(koerper.teilung or [4, 4, 4]))

        try:
            erk = erkennen(model, bau(namen))
        except Exception:                   # noqa: BLE001
            erk = None
        if erk is None:
            # Der Schnitt hat die eine Kappe feiner geteilt als die andere.
            # Angleichen - und nur behalten, wenn es traegt.
            # Fremd ist dabei auch die **Schnittflaeche**: sie gehoert beiden
            # Bloecken, und der andere kennt die Stuecke nicht.
            stand = werk.stand()
            neu = kappenlinien_angleichen(model, namen, werk, tol,
                                          set(seiten[-vorz]) | {schnitt} | fremd)
            try:
                erk2 = (None if neu is None or not _geschlossene_schale(model, neu)
                        else erkennen(model, bau(neu)))
            except Exception:               # noqa: BLE001
                erk2 = None
            if erk2 is not None:
                namen, erk = neu, erk2
            else:
                werk.zurueck_bis(stand)
        bloecke.append((list(namen), erk))
    if not any(e is not None for _n, e in bloecke):
        return None
    return bloecke


def zerlegen(model: Model, koerper, tiefe: int = ZERLEGEN_TIEFE) -> tuple:
    """Einen nicht sweepbaren Koerper an Fussabdruecken in Bloecke zerlegen.

    Rueckgabe ([(Flaechennamen des Blocks, Erkennung oder None)],
    Schnittflaechen) - die Schnittflaechen stehen danach in model.flaechen
    und werden vom Aufrufer mit :func:`schnitte_entfernen` wieder entfernt;
    (None, []) wenn kein Schnitt einen sweepbaren Block ergibt. Ein Block
    ohne Erkennung wird frei (Tetraeder) vernetzt, mit dem Netz der
    Schnittflaeche als Vorgabe - so passt er an die Hexaeder daneben.

    Warum das der Hebel ist: am Drehlager tragen acht Koerper mit 48 bis 144
    Flaechen 84,0 % der Elemente (Zaehlung der Loeser-Sitzung, 21.09.2026);
    kein einziger ist als Ganzes Grundflaeche mal Weg. Was sich davon an
    Fussabdruecken teilen laesst, entscheidet das Modell - hier ist an
    Pruefkoerpern belegt: Platte mit Nabe und abgesetzte Welle werden zu je
    zwei gesweepten Bloecken (tests.test_sweep).
    """
    import time as _time
    werk = Schnittwerk(model)
    schnitte = werk.flaechen
    werk.start = _time.time()
    werk.versuche = 0

    def block(namen):
        return Volumenkoerper(koerper.name, list(namen), material=koerper.material,
                              teilung=list(koerper.teilung or [4, 4, 4]))

    def versuch(namen, tiefe):
        if werk.erschoepft():
            return [(list(namen), None)]
        werk.versuche += 1
        try:
            erk = erkennen(model, block(namen))
        except Exception:                   # noqa: BLE001
            erk = None
        if erk is not None:
            return [(list(namen), erk)]
        if tiefe <= 0:
            return [(list(namen), None)]
        for F_name in list(namen):
            F = model.flaechen.get(F_name)
            if F is None or not (F.oeffnungen or []):
                continue
            for B_namen, S in _fussabdruecke(model, koerper, namen, F, len(schnitte)):
                S.name = werk.marke(koerper)
                werk.flaeche(S)
                A_namen = [x for x in namen if x not in B_namen] + [S.name]
                bl = versuch(A_namen, tiefe - 1) + versuch(list(B_namen) + [S.name], tiefe - 1)
                if any(e is not None for _n, e in bl):
                    return bl
                # nichts gewonnen: Schnitt und alles, was darunter entstand, zuruecknehmen
                for T_ in list(schnitte[schnitte.index(S.name):]):
                    model.flaechen.pop(T_, None)
                    schnitte.remove(T_)
        return [(list(namen), None)]

    try:
        alle = np.vstack([_schleifenpunkte(model, list(model.flaechen[x].linien or []))
                          for x in (koerper.flaechen or []) if x in model.flaechen])
        gross = float(np.linalg.norm(alle.max(axis=0) - alle.min(axis=0)))
    except Exception:                       # noqa: BLE001
        gross = 1.0
    tol = max(TOL_REL * gross, 1e-12)
    # Erst die billigen Schnitte - an einer Ebene oder an einer vorhandenen
    # Schleife (zerlegen_ebene): sie probieren nichts durch. Die Fussabdruecke
    # danach suchen kombinatorisch und kosteten an V30 des Drehlagers 255 s
    # fuer nichts (gemessen 23.09.2026); sie bekommen den Rest des Budgets.
    bl = zerlegen_ebene(model, koerper, werk, tol)
    if bl:
        return bl, werk
    werk.zuruecknehmen()
    bl = versuch(list(koerper.flaechen or []), tiefe)
    if len(bl) > 1 and any(e is not None for _n, e in bl):
        werk.art = "an Fußabdrücken"
        return bl, werk
    werk.zuruecknehmen()
    # Zuletzt: vielleicht ist er ganz sweepbar und nur seine beiden Kappen sind
    # **verschieden geteilt** - eine Linie mehr im Deckel als im Grund reicht,
    # damit die Wandpruefung zu einer Grundlinie zwei Deckellinien findet. Das
    # ist Handarbeit im Modell, kein Fehler, und es kostet nichts, es zu heilen.
    namen = list(koerper.flaechen or [])
    neu_namen = kappenlinien_angleichen(model, namen, werk, tol,
                                        _fremde_flaechen(model, koerper))
    if neu_namen and _geschlossene_schale(model, neu_namen):
        pseudo = Volumenkoerper(koerper.name, list(neu_namen), material=koerper.material,
                                teilung=list(koerper.teilung or [4, 4, 4]))
        try:
            erk = erkennen(model, pseudo)
        except Exception:                   # noqa: BLE001
            erk = None
        if erk is not None:
            return [(list(neu_namen), erk)], werk
    werk.zuruecknehmen()
    if getattr(werk, "abgebrochen", None):
        abbrueche = getattr(model, "_zerlegen_abbruch", None)
        if abbrueche is None:
            abbrueche = model._zerlegen_abbruch = {}
        abbrueche[koerper.name] = werk.abgebrochen
    return None, werk


def zerlegbar(model: Model, koerper) -> bool:
    """Ergibt das Zerlegen wenigstens einen sweepbaren Block?

    Das Ergebnis wird je Koerper und Flaechenliste am Modell gemerkt:
    sweepbar() fragt vor dem Vernetzen fuer die Reihenfolge, und
    zerlegt_vernetzen zerlegt danach noch einmal - bei einem Koerper, an dem
    das Budget (ZERLEGEN_ZEIT_S) ausgeschoepft wird, waere das zweimal die
    volle Zeit.
    """
    speicher = getattr(model, "_zerlegbar_cache", None)
    if speicher is None:
        speicher = model._zerlegbar_cache = {}
    schluessel = (koerper.name, tuple(koerper.flaechen or []), int(model.nn))
    if schluessel in speicher:
        return speicher[schluessel]
    bl, werk = zerlegen(model, koerper)
    schnitte_entfernen(model, werk)
    speicher[schluessel] = bool(bl)
    return speicher[schluessel]


def zerlegen_warum_nicht(model: Model, koerper) -> str:
    """Warum am Koerper kein Schnitt ansetzt - in einem Satz, mit Zahlen.

    Am Drehlager stand im ganzen Protokoll keine Zeile ueber das Zerlegen
    (Lauf der Loeser-Sitzung, 21.09.2026): `zerlegen` hat an keinem der 108
    Koerper angesetzt, und ohne diese Zeile laesst sich nicht sagen, ob es
    keine ebene Flaeche mit Oeffnung gab, keinen Aufsatz darauf, oder ob der
    Schnitt zwar entstand und nur keinen sweepbaren Block ergab. Genau das
    sagt sie jetzt - je Koerper, einmal.
    """
    namen = list(koerper.flaechen or [])
    mit_loch = [x for x in namen
                if (model.flaechen.get(x) is not None and (model.flaechen[x].oeffnungen or []))]
    if not mit_loch:
        return f"keine der {len(namen)} Randflächen hat eine Öffnung"
    n_abdruck = 0
    for x in mit_loch:
        try:
            n_abdruck += sum(1 for _b, _S in _fussabdruecke(model, koerper, namen, model.flaechen[x], 0))
        except Exception:                   # noqa: BLE001
            pass
    if not n_abdruck:
        return (f"{len(mit_loch)} Randfläche(n) mit Öffnung, aber kein Aufsatz hängt nur über "
                "eine ihrer Öffnungen am Rest")
    ab = (getattr(model, "_zerlegen_abbruch", None) or {}).get(koerper.name)
    return (f"{n_abdruck} Fußabdruck/-abdrücke an {len(mit_loch)} Fläche(n) - aber kein Schnitt "
            "ergab einen sweepbaren Block" + (f" (Zerlegen nach {ab} abgebrochen)" if ab else ""))


def zerlegt_vernetzen(model: Model, koerper, h: float, log: list = None, cache: dict = None,
                      karten: tuple = None, ordnung: int = 0, fortschritt=None) -> list:
    """Den Koerper zerlegen und Block fuer Block vernetzen: die sweepbaren
    Bloecke zuerst (sie legen die Netze der Schnittflaechen vor), die
    uebrigen frei mit Tetraedern. Alle Elemente gehoeren dem Koerper.
    Rueckgabe die Elementnummern; leer, wenn nichts zu zerlegen war."""
    from .importers import _common as C
    from . import mesher3d as M3
    bl, werk = zerlegen(model, koerper)
    if not bl:
        from .importers import _common as C
        C.say(log, f"Volumen {koerper.name}: nicht zerlegt - {zerlegen_warum_nicht(model, koerper)}.")
        return []
    try:
        art = getattr(werk, "art", None) or ("an Fußabdrücken" if not werk.ersatz else "an einer Ebene")
        C.say(log, f"Volumen {koerper.name}: nicht als Ganzes sweepbar - {art} in {len(bl)} Blöcke "
                   f"zerlegt ({sum(1 for _n, e in bl if e is not None)} davon sweepbar)")
        els: list = []
        n_frei = 0
        randtreue = 1.0
        for namen, erk in sorted(bl, key=lambda x: x[1] is None):
            pseudo = Volumenkoerper(koerper.name, list(namen), material=koerper.material,
                                    teilung=list(koerper.teilung or [4, 4, 4]))
            e = []
            if erk is not None:
                e = vernetzen(model, pseudo, erk, h, log, cache, karten)
            if not e:
                n_frei += 1
                e = M3.mesh_koerper_frei(model, pseudo, h=h, log=log, cache=cache, ordnung=ordnung,
                                         fortschritt=fortschritt, karten=karten)
                randtreue = min(randtreue, float(getattr(pseudo, "randtreue", 0.0) or 0.0))
            els += [int(x) for x in (e or [])]
        koerper.elemente = els
        z = {"hex8": 0, "pent6": 0, "tet4": 0}
        for e in els:
            typ = model.elements[e].typ
            z[typ] = z.get(typ, 0) + 1
        koerper.kommentar = (f"{z.get('hex8', 0)} Hexaeder + {z.get('pent6', 0)} Keile + "
                             + (f"{z['pyr5']} Pyramiden + " if z.get("pyr5") else "")
                             + f"{z.get('tet4', 0) + z.get('tet10', 0)} Tetraeder (zerlegt in {len(bl)} Blöcke)")
        koerper.randtreue = randtreue
        koerper.netzgrund = ""
        koerper.netzkanten = []
        C.say(log, f"Volumen {koerper.name}: {len(els)} Elemente aus {len(bl)} Blöcken "
                   f"({len(bl) - n_frei} gesweept, {n_frei} frei) - {koerper.kommentar}")
        n_rs = werk.randseiten_zurueck()
        if n_rs:
            C.say(log, f"  {n_rs} Randseiten der Teilflächen auf die Randflächen zurückgelegt")
        return els
    finally:
        # Die Knoten bleiben: an ihnen haengen Elemente. Linien und Flaechen
        # des Schnitts gehen raus.
        schnitte_entfernen(model, werk, knoten_auch=False)


#: Groesster zugelassener Winkelfehler eines Sechsflaechners fuer die Zaehlung
#: "regelmaessig": Abweichung eines Seiteneckwinkels von 90 Grad. Die
#: Element-Sitzung mass am Kragarm (22.09.2026): bei 45 Grad Trapez- bzw.
#: Parallelogrammverzerrung liegt die Nachweisstelle 33 bzw. 13 N/mm^2
#: daneben, regelmaessig 0,8 bzw. 0,2 N/mm^2. 15 Grad ist die Frage des
#: Auftrags vom 23.09.2026.
WINKELFEHLER_GRENZE = 2.5
#: Gemessen 24.09.2026 (tests/messung_winkelfehler.py, Kragarm wie V5, hex8):
#: das regelmaessige Netz erreicht 1 N/mm2 schon mit 8 x 2 x 4 Elementen
#: (+0,77). Parallelogrammverzerrung (Zickzack ueber die Lagen) ist bis 30
#: Grad unkritisch (Zuwachs +0,37 N/mm2 grob, +0,01 fein); Trapezverzerrung
#: nicht: am 16 x 4 x 8-Netz 2,5 Grad -0,48, 5 Grad -1,53, 10 Grad -5,4,
#: 15 Grad -11,6 N/mm2 Zuwachs, am 8 x 2 x 4-Netz 2,5 Grad schon -2,05. Der
#: Winkelfehler unterscheidet Trapez und Parallelogramm nicht, also gilt das
#: Trapez: hoechstens 2,5 Grad. Vorher standen hier 15 Grad ohne Messung.


#: Grenze fuer den Trapezfehler in der Betriebsart "sauber" (Grad): der Winkel
#: zwischen gegenueberliegenden Kanten einer Viereckseite. Ein Zickzack-Trapez
#: mit dem Eckwinkelfehler theta hat zwischen seinen Schenkeln 2 theta, also
#: ist die Grenze das Doppelte von WINKELFEHLER_GRENZE. Parallelogramme haben
#: den Trapezfehler 0 und sind nach der Messung vom 24.09.2026 bis 30 Grad
#: Eckwinkelfehler unkritisch (tests/messung_winkelfehler.py).
TRAPEZ_GRENZE = 2.0 * WINKELFEHLER_GRENZE


def trapezfehler(X: np.ndarray, typ: str) -> float:
    """Groesster Winkel zwischen **gegenueberliegenden** Kanten einer
    Viereckseite eines hex8 oder pent6, in Grad. Null fuer Rechtecke **und**
    Parallelogramme; ein Trapez mit den Schenkelwinkeln 90 +- theta gibt
    2 theta. Das ist das Mass, das den hex8 trifft: Parallelogrammverzerrung
    kostet am Kragarm bis 30 Grad nichts, Trapezverzerrung ab 2,5 Grad mehr
    als 1 N/mm2 (gemessen 24.09.2026)."""
    from .elements.solid import FLAECHEN_ECKEN
    X = np.asarray(X, float)
    schlimmst = 0.0

    def winkel(a, b):
        la, lb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
        if la <= 0.0 or lb <= 0.0:
            return 180.0
        return float(np.degrees(np.arccos(np.clip(float(a @ b) / (la * lb), -1.0, 1.0))))
    for seite in FLAECHEN_ECKEN.get(typ, ()):
        if len(seite) != 4:
            continue
        s0, s1, s2, s3 = (X[i] for i in seite)
        schlimmst = max(schlimmst, winkel(s1 - s0, s2 - s3), winkel(s2 - s1, s3 - s0))
    return schlimmst


def betriebsart(model) -> str:
    """Die Betriebsart des Sweeps aus ``Netzeinstellungen.sweep``: "aus",
    "sauber" oder "immer". Alte Dateien fuehren True/False: True heisst
    "immer" (so lief der Sweep bisher), False "aus"; unbekannte Woerter
    gelten als "immer". "sauber" (dritter Auftrag, 24.09.2026, Entscheidung des
    Anwenders: hex8 nur dort, wo der Sweep heute schon sauber geht) sweept
    einen Koerper nur, wenn jedes hex8 und pent6 hoechstens WINKELFEHLER_GRENZE
    Winkelfehler und eine positive Jacobi-Determinante hat - sonst Tetraeder,
    und der Uebergang zum Nachbarn immer ueber Pyramiden."""
    w = getattr(getattr(model, "netz", None), "sweep", False)
    if isinstance(w, str):
        w = w.strip().lower()
        return w if w in ("aus", "sauber", "immer") else "immer"
    return "immer" if bool(w) else "aus"


def sauber_pruefen(X_lagen: np.ndarray, vierecke, dreiecke) -> tuple:
    """Die Elemente eines Sweeps **vor** dem Einbau pruefen: Trapezfehler
    hoechstens TRAPEZ_GRENZE (das Mass, das den hex8 trifft) und
    Jacobi-Determinante positiv an allen Integrationspunkten und Ecken.
    ``X_lagen`` ist (L+1, n, 3), die Punkte je Lage. Rueckgabe (sauber, Grund,
    groesster Trapezfehler, groesster Winkelfehler)."""
    from .elements.solid import jacobi_volumen_stapel
    L = len(X_lagen) - 1
    trapez, winkel = 0.0, 0.0
    umgeklappt = 0
    for typ, muster in (("hex8", vierecke), ("pent6", dreiecke)):
        if not len(muster):
            continue
        for k in range(L):
            u, o = X_lagen[k], X_lagen[k + 1]
            X = np.concatenate([u[np.asarray(muster, int)], o[np.asarray(muster, int)]], axis=1)
            d = jacobi_volumen_stapel(typ, X)
            umgeklappt += int((d["det_min"] <= 0.0).sum())
            for e in range(len(X)):
                trapez = max(trapez, trapezfehler(X[e], typ))
                winkel = max(winkel, winkelfehler(X[e], typ))
                if trapez > TRAPEZ_GRENZE:
                    break
            if trapez > TRAPEZ_GRENZE or umgeklappt:
                break
        if trapez > TRAPEZ_GRENZE or umgeklappt:
            break
    if umgeklappt:
        return False, f"Jacobi-Determinante ≤ 0 in {umgeklappt} Element(en)", trapez, winkel
    if trapez > TRAPEZ_GRENZE:
        return False, f"Trapezfehler {trapez:.1f}° > {TRAPEZ_GRENZE:.1f}° (Winkelfehler {winkel:.0f}°)", trapez, winkel
    return True, "", trapez, winkel


def winkelfehler(X: np.ndarray, typ: str) -> float:
    """Groesste Abweichung eines Seiteneckwinkels vom Ideal - 90 Grad an
    Vierecken, 60 Grad an Dreiecken - in Grad. Das misst Trapez-,
    Parallelogramm- und Verwindungsverzerrung eines hex8 oder pent6 in
    **einer** Zahl; ein Wuerfel hat 0, ein Keil aus einem gleichseitigen
    Dreieck 0."""
    from .elements.solid import FLAECHEN_ECKEN
    X = np.asarray(X, float)
    schlimmst = 0.0
    for seite in FLAECHEN_ECKEN.get(typ, ()):
        n = len(seite)
        ideal = 90.0 if n == 4 else 60.0
        for i in range(n):
            a = X[seite[(i - 1) % n]] - X[seite[i]]
            b = X[seite[(i + 1) % n]] - X[seite[i]]
            la, lb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
            if la <= 0.0 or lb <= 0.0:
                return 180.0
            w = float(np.degrees(np.arccos(np.clip(float(a @ b) / (la * lb), -1.0, 1.0))))
            schlimmst = max(schlimmst, abs(w - ideal))
    return schlimmst


def hexaederanteil(model: Model, koerper=None) -> dict:
    """{"hexaeder", "keile", "pyramiden", "tetraeder", "elemente", "knoten",
    "anteil_hexaeder", "elemente_je_knoten", "winkelfehler_max",
    "hexaeder_regelmaessig"} ueber die genannten Koerper (alle).

    ``hexaeder_regelmaessig`` zaehlt die hex8 mit Winkelfehler bis
    WINKELFEHLER_GRENZE - das Mass, das die Element-Sitzung fuer V6 verlangt
    (Nachtrag 22.09.2026): hex8 lohnt sich nur, wo die Verzerrung klein
    bleibt. Am Drehlager: 54,8 % der 19 368 Hexaeder bis 15 Grad, die Deckel
    V33/V35 bis 72 Grad (gemessen 23.09.2026)."""
    koerper = list(koerper if koerper is not None else model.koerper.values())
    zaehl = {"hex8": 0, "hex20": 0, "pent6": 0, "pent15": 0, "pyr5": 0, "tet4": 0, "tet10": 0}
    knoten = set()
    wf_max, regel = 0.0, 0
    for k in koerper:
        for e in (k.elemente or []):
            el = model.elements[int(e)]
            if el.typ in zaehl:
                zaehl[el.typ] += 1
            knoten.update(int(x) for x in el.nodes)
            if el.typ in ("hex8", "pent6"):
                w = winkelfehler(model.nodes[el.nodes], el.typ)
                wf_max = max(wf_max, w)
                if el.typ == "hex8" and w <= WINKELFEHLER_GRENZE:
                    regel += 1
    n = sum(zaehl.values())
    hexa = zaehl["hex8"] + zaehl["hex20"]
    return {"hexaeder": hexa, "keile": zaehl["pent6"] + zaehl["pent15"], "pyramiden": zaehl["pyr5"],
            "tetraeder": zaehl["tet4"] + zaehl["tet10"], "elemente": n, "knoten": len(knoten),
            "anteil_hexaeder": hexa / n if n else 0.0,
            "elemente_je_knoten": n / len(knoten) if knoten else 0.0,
            "winkelfehler_max": wf_max, "hexaeder_regelmaessig": regel}
