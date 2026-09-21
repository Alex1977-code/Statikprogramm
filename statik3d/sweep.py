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

from .model import Model

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
def _ringpunkte(model: Model, f, teilung: int = 24) -> list:
    """[Aussenrand, Oeffnung 1, ...] als Punktfolgen (abgetastet)."""
    aus = [np.asarray(f.randpunkte(model, teilung), float)]
    aus += [np.asarray(P, float) for P in f.oeffnungspunkte(model, teilung)]
    return aus


def _passt(A: np.ndarray, B: np.ndarray, t: np.ndarray, tol: float) -> bool:
    """Ist B die um t verschobene Punktmenge A (als Menge, nicht als Folge)?"""
    from scipy.spatial import cKDTree
    if len(A) != len(B) or not len(A):
        return False
    d, _ = cKDTree(B).query(A + t)
    return bool(d.max() <= tol)


def _gerade(model: Model, name: str) -> "np.ndarray | None":
    """Vektor einer geraden Linie mit zwei Knoten - sonst None."""
    ln = model.lines.get(name)
    if ln is None or (ln.typ or "polyline") != "polyline" or len(ln.nodes) != 2:
        return None
    a, b = int(ln.nodes[0]), int(ln.nodes[1])
    if not (0 <= a < model.nn and 0 <= b < model.nn):
        return None
    return model.nodes[b] - model.nodes[a]


def erkennen(model: Model, koerper) -> "dict | None":
    """Grund, Deckel, Weg und Waende eines sweepbaren Koerpers - oder None.

    Rueckgabe {"grund": Flaeche, "deckel": Flaeche, "t": Vektor,
    "linien": {Linie des Grundes: Linie des Deckels},
    "waende": {Linie des Grundes: Wandflaeche},
    "mantel": {Knoten des Grundes: Mantellinie}, "tol": Toleranz}.
    """
    from .mesher3d import ist_eben
    flaechen = [model.flaechen.get(x) for x in (koerper.flaechen or [])]
    if len(flaechen) < 5 or any(f is None for f in flaechen):
        return None
    ringe = {}
    for f in flaechen:
        try:
            ringe[f.name] = _ringpunkte(model, f)
        except Exception:                   # noqa: BLE001
            return None
        if len(ringe[f.name][0]) < 3:
            return None
    alle = np.vstack([R for rs in ringe.values() for R in rs])
    gross = float(np.linalg.norm(alle.max(axis=0) - alle.min(axis=0)))
    tol = max(TOL_REL * gross, 1e-12)
    eben = {f.name: ist_eben(np.vstack(ringe[f.name])) for f in flaechen}
    namen = {f.name: f for f in flaechen}
    for i, fa in enumerate(flaechen):
        if not eben[fa.name]:
            continue
        for fb in flaechen[i + 1:]:
            if not eben[fb.name]:
                continue
            if len(fa.linien or []) != len(fb.linien or []) or len(fa.oeffnungen or []) != len(fb.oeffnungen or []):
                continue
            RA, RB = ringe[fa.name], ringe[fb.name]
            if len(RA) != len(RB) or any(len(a) != len(b) for a, b in zip(RA, RB)):
                continue
            t = RB[0].mean(axis=0) - RA[0].mean(axis=0)
            if float(np.linalg.norm(t)) <= tol:
                continue
            if not all(_passt(a, b, t, tol) for a, b in zip(RA, RB)):
                continue
            erg = _waende_pruefen(model, koerper, fa, fb, t, tol, namen)
            if erg is not None:
                return erg
    return None


def _linienenden(model: Model, name: str) -> "tuple | None":
    ln = model.lines.get(name)
    if ln is None or len(ln.nodes) < 2:
        return None
    a, b = int(ln.nodes[0]), int(ln.nodes[-1])
    if not (0 <= a < model.nn and 0 <= b < model.nn):
        return None
    return a, b


def _waende_pruefen(model: Model, koerper, fa, fb, t: np.ndarray, tol: float, namen: dict) -> "dict | None":
    """Jede uebrige Randflaeche muss eine Wand zwischen einer Grundlinie und
    ihrer Deckellinie sein, mit zwei geraden Mantellinien laengs t."""
    def linien(f):
        out = list(f.linien or [])
        for loch in (f.oeffnungen or []):
            out += list(loch)
        return out
    la, lb = linien(fa), linien(fb)
    if len(la) != len(lb):
        return None
    # Linienpaare ueber die verschobenen Endknoten
    enden_b = {}
    for name in lb:
        e = _linienenden(model, name)
        if e is None:
            return None
        enden_b[name] = e
    paare = {}
    for name in la:
        e = _linienenden(model, name)
        if e is None:
            return None
        pa, pb = model.nodes[e[0]] + t, model.nodes[e[1]] + t
        treffer = None
        for nb, (c, d) in enden_b.items():
            if nb in paare.values():
                continue
            qc, qd = model.nodes[c], model.nodes[d]
            if ((np.linalg.norm(pa - qc) <= tol and np.linalg.norm(pb - qd) <= tol)
                    or (np.linalg.norm(pa - qd) <= tol and np.linalg.norm(pb - qc) <= tol)):
                treffer = nb
                break
        if treffer is None:
            return None
        paare[name] = treffer
    # Mantellinien: je Grundknoten genau eine gerade Linie mit Vektor +-t
    knoten_a = {k for name in la for k in _linienenden(model, name)}
    mantel = {}
    waende = {}
    rest = [f for f in namen.values() if f.name not in (fa.name, fb.name)]
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
        for s in senk:
            v = _gerade(model, s)
            if v is None:
                return None
            if not (np.linalg.norm(v - t) <= tol or np.linalg.norm(v + t) <= tol):
                return None
            e = _linienenden(model, s)
            unten = e[0] if e[0] in knoten_a else e[1]
            if unten not in knoten_a:
                return None
            if mantel.get(unten, s) != s:
                return None
            mantel[unten] = s
        waende[grund[0]] = w
    if len(waende) != len(la) or set(mantel) != knoten_a:
        return None
    return {"grund": fa, "deckel": fb, "t": np.asarray(t, float), "linien": paare,
            "waende": waende, "mantel": mantel, "tol": tol}


def sweepbar(model: Model, koerper) -> bool:
    """Laesst sich der Koerper sweepen (und ist das eingeschaltet)?"""
    if not bool(getattr(getattr(model, "netz", None), "sweep", True)):
        return False
    try:
        return erkennen(model, koerper) is not None
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
    """Dreiecke zu Vierecken paaren - gierig nach der Guete des Vierecks.

    ``T`` sind Dreiecke mit gleichem Umlauf (gegen den Uhrzeiger in ``P2``).
    Zwei Dreiecke, die eine Kante teilen, geben das Viereck ueber die andere
    Diagonale; es wird genommen, wenn seine Guete mindestens ``guete_min``
    ist und beide Dreiecke noch frei sind. Rueckgabe (Vierecke (q, 4),
    uebrige Dreiecke (r, 3)), beide gegen den Uhrzeiger.
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
        # Reihenfolge der Kante im ersten Dreieck: i -> j
        i1 = t1.index(s1)
        i, j = t1[(i1 + 1) % 3], t1[(i1 + 2) % 3]      # Kante in Umlaufrichtung von t1
        viereck = (s1, i, s2, j)
        kandidaten.append((k1, k2, viereck))
    if not kandidaten:
        return np.zeros((0, 4), int), T
    Q = np.array([v for _, _, v in kandidaten], int)
    q = _viereckguete(P2[Q])
    reihenfolge = np.argsort(-q, kind="stable")
    benutzt = np.zeros(len(T), bool)
    vierecke = []
    for r in reihenfolge:
        if q[r] < guete_min:
            break
        k1, k2, v = kandidaten[r]
        if benutzt[k1] or benutzt[k2]:
            continue
        benutzt[k1] = benutzt[k2] = True
        vierecke.append(v)
    rest = T[~benutzt]
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
    """Lagen aus Weg und Kantenlaenge, mindestens :func:`lagen_min`."""
    weg = float(np.linalg.norm(erk["t"]))
    return max(int(round(weg / max(float(h), 1e-12))), lagen_min(model), 1)


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
    if not bool(getattr(getattr(model, "netz", None), "sweep", True)):
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
        if erk is None:
            continue
        flaechen = [model.flaechen[x] for x in k.flaechen]
        h = M3._kantenlaenge(model, k, float(hs.get(k.name, 0.0) or 0.0))
        teilung = M3.Linienteilung(model, flaechen, h, h_linien, h_flaechen, gemeinsam)
        mantel = set(erk["mantel"].values())
        # Nur die Mantellinien, die ein Nachbar mitbenutzt, bringen ihre
        # Kartenteilung ein. Die eigenen nicht: ihre Karte traegt die Regel
        # „Linie neben einer feineren" (_linien_wachsen_lassen), und die gab
        # der Kragplatte 10 statt 2 Lagen, 4 473 statt 1 491 Knoten (21.09.2026,
        # tests.test_sweep.test_kragplatte_tet4_gegen_hex8).
        gem = [s for s in mantel if s in teilung.gem_linien]
        L = max([_lagen_aus_weg(model, erk, h)] + [int(teilung.n.get(s, 1)) for s in gem])
        wunsch.append((k.name, mantel, L))
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
        oben = _linienenden(model, erk["mantel"][knoten])
        return ("K", oben[0] if oben[1] == knoten else oben[1])
    _, name, k = kenn
    name_b = erk["linien"][name]
    # Laufen beide Linien in derselben Richtung? (erster Punkt der Teilung)
    pa = teilung.punkte(name)
    pb = teilung.punkte(name_b)
    if len(pa) and len(pb) and np.linalg.norm(pb[0] - (pa[0] + erk["t"])) <= erk["tol"]:
        return ("L", name_b, k)
    return ("L", name_b, len(pa) - 1 - k)


def vernetzen(model: Model, koerper, erk: dict, h: float, log: list = None, cache: dict = None,
              karten: tuple = None) -> list:
    """Den erkannten Koerper sweepen: Grundflaechennetz, Lagen, Elemente,
    Randseiten, vorgegebene Flaechennetze fuer die Nachbarn. Rueckgabe die
    Elementnummern; leer, wenn der Sweep nicht geht (der Grund steht im
    Protokoll, der Aufrufer nimmt den freien Vernetzer)."""
    from .importers import _common as C
    from . import mesher3d as M3
    from .assemble import SOLID_FACES
    grund, deckel, t = erk["grund"], erk["deckel"], erk["t"]
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
    # ---- Grundflaeche -----------------------------------------------------
    P, T, meldung, grob, kenn = M3.flaechennetz(model, grund, teilung)
    if meldung or not len(T) or grob:
        C.say(log, f"Volumen {koerper.name}: nicht gesweept - Grundfläche {grund.name}: "
                   f"{meldung or 'Randlinien zu grob geteilt'}.")
        return []
    P = np.asarray(P, float)
    T = np.asarray(T, int)
    kenn = list(kenn) + [None] * (len(P) - len(kenn))
    # Ebene der Grundflaeche, Normale in Richtung des Weges
    c, e1, e2, n, _abw = M3.ausgleichsebene(P)
    if float(n @ t) < 0:
        n, e2 = -n, -e2
    P2 = np.stack([(P - c) @ e1, (P - c) @ e2], axis=1)
    a, b, d = P2[T[:, 0]], P2[T[:, 1]], P2[T[:, 2]]
    flaeche2 = (b[:, 0] - a[:, 0]) * (d[:, 1] - a[:, 1]) - (d[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])
    T = np.where((flaeche2 < 0)[:, None], T[:, [0, 2, 1]], T)
    vierecke, dreiecke = paaren(P2, T)
    # ---- Kanten des Randes -> Wandflaeche ----------------------------------
    # Die Randpunkte stehen in P vorn, ring fuer ring in der Reihenfolge des
    # Linienzugs (_dreiecke_2d haelt sie so); Herkunft je Strecke aus _linienzug.
    ringe = [list(grund.linien or [])] + [list(loch) for loch in (grund.oeffnungen or [])]
    kante_wand: dict = {}                    # gerichtete Randkante -> Grundlinie (beide Richtungen)
    wand_kanten: dict = {}                   # Grundlinie -> ihre Randkanten in Ringrichtung
    basis = 0
    for lin in ringe:
        zug = _linienzug_herkunft(teilung, model, lin)
        if zug is None:
            C.say(log, f"Volumen {koerper.name}: nicht gesweept - Rand der Grundfläche schließt nicht.")
            return []
        pts, herkunft, _k = zug
        m = len(pts)
        if np.linalg.norm(pts - P[basis:basis + m], axis=1).max() > erk["tol"] * 10 + 1e-12:
            C.say(log, f"Volumen {koerper.name}: nicht gesweept - Randpunkte der Grundfläche "
                       "stehen nicht in der erwarteten Reihenfolge.")
            return []
        for i in range(m):
            a_, b_ = basis + i, basis + (i + 1) % m
            kante_wand[(a_, b_)] = herkunft[i]
            kante_wand[(b_, a_)] = herkunft[i]
            wand_kanten.setdefault(herkunft[i], []).append((a_, b_))
        basis += m
    n_rand = basis
    if set(wand_kanten) != set(erk["waende"]):
        C.say(log, f"Volumen {koerper.name}: nicht gesweept - Randlinien der Grundfläche und Wände "
                   "passen nicht zusammen.")
        return []
    # ---- Knoten je Lage ---------------------------------------------------
    mat = koerper.material or C.ensure_material(model, log=log)
    schritt = t / float(L)
    knoten = np.zeros((L + 1, len(P)), int)
    zug_kenn = [[None] * len(P) for _ in range(L + 1)]
    for i in range(len(P)):
        zug_kenn[0][i] = kenn[i]
        zug_kenn[L][i] = _deckel_kennung(model, erk, kenn[i], teilung)
        if kenn[i] is not None and kenn[i][0] == "K":
            for k in range(1, L):
                zug_kenn[k][i] = _mantel_kennung(model, erk, int(kenn[i][1]), k, L)
    # Flaeche je Punkt: Grund (Lage 0), Deckel (Lage L), Wand (Randpunkt dazwischen)
    wand_von_punkt = {}
    for (i, j), lin in kante_wand.items():
        wand_von_punkt.setdefault(i, erk["waende"][lin].name)
    for k in range(L + 1):
        X = P + k * schritt
        if k == 0:
            fl = [grund.name] * len(P)
        elif k == L:
            fl = [deckel.name] * len(P)
        else:
            fl = [wand_von_punkt.get(i) if i < n_rand else None for i in range(len(P))]
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
                grund.randseiten.append([e, 0])
            if k == L - 1:
                deckel.randseiten.append([e, 1])
            for (a_, b_), s in seite_hex.items():
                lin = kante_wand.get((int(q[a_]), int(q[b_])))
                if lin is not None:
                    erk["waende"][lin].randseiten.append([e, s])
        for ti, tr in enumerate(dreiecke):
            e = els_keil[k * n_d + ti]
            if k == 0:
                grund.randseiten.append([e, 0])
            if k == L - 1:
                deckel.randseiten.append([e, 1])
            for (a_, b_), s in seite_keil.items():
                lin = kante_wand.get((int(tr[a_]), int(tr[b_])))
                if lin is not None:
                    erk["waende"][lin].randseiten.append([e, s])
    # ---- Vorgegebene Flaechennetze fuer die Nachbarn -----------------------
    netze = getattr(model, "flaechennetze", None)
    if netze is None:
        netze = model.flaechennetze = {}
    T_voll = _dreiecke_aus(P2, vierecke, dreiecke)
    netze[grund.name] = (P.copy(), T_voll.copy(), list(zug_kenn[0]))
    netze[deckel.name] = (P + t, T_voll.copy(), list(zug_kenn[L]))
    for lin, wand in erk["waende"].items():
        folge = _randfolge(wand_kanten[lin])
        WP, WT, WK = _wandnetz(P, folge, schritt, L, zug_kenn)
        netze[wand.name] = (WP, WT, WK)
    # ---- Rauminhalt: Grundflaeche mal Hoehe gegen die Elemente ---------------
    from .elements.solid import solid_volume
    A_grund = 0.5 * float(np.abs(flaeche2).sum())
    V_soll = A_grund * abs(float(n @ t))
    V_ist = float(sum(solid_volume(model.elements[e].typ, model.nodes[model.elements[e].nodes]) for e in els))
    abw = abs(V_ist - V_soll) / V_soll if V_soll > 0 else 1.0
    # ---- Protokoll --------------------------------------------------------
    koerper.kommentar = (f"{len(els_hex)} Hexaeder + {len(els_keil)} Keile (gesweept, {L} Lagen)")
    koerper.randtreue = 1.0
    koerper.netzgrund = ""
    koerper.netzkanten = []
    anteil = 100.0 * len(els_hex) / max(1, len(els))
    C.say(log, f"Volumen {koerper.name}: {len(els_hex)} Hexaeder (hex8) + {len(els_keil)} Keile (pent6) "
               f"gesweept - Grundfläche {grund.name} → {deckel.name}, {L} Lagen à "
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


def _wandnetz(P: np.ndarray, folge: list, schritt: np.ndarray, L: int, zug_kenn: list) -> tuple:
    """Das strukturierte Netz einer Wand: Randpunkte der Grundlinie x Lagen,
    Vierecke in zwei Dreiecke (kuerzere Diagonale) - fuer den Nachbarn."""
    m = len(folge)
    WP = np.vstack([P[folge] + k * schritt for k in range(L + 1)])
    WK = [zug_kenn[k][i] for k in range(L + 1) for i in folge]
    T = []
    for k in range(L):
        for s in range(m - 1):
            a, b = k * m + s, k * m + s + 1
            c, d = (k + 1) * m + s + 1, (k + 1) * m + s
            if np.linalg.norm(WP[a] - WP[c]) <= np.linalg.norm(WP[b] - WP[d]):
                T += [(a, b, c), (a, c, d)]
            else:
                T += [(a, b, d), (b, c, d)]
    return WP, np.asarray(T, int).reshape(-1, 3), WK


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


def hexaederanteil(model: Model, koerper=None) -> dict:
    """{"hexaeder", "keile", "pyramiden", "tetraeder", "elemente", "knoten",
    "anteil_hexaeder", "elemente_je_knoten"} ueber die genannten Koerper (alle)."""
    koerper = list(koerper if koerper is not None else model.koerper.values())
    zaehl = {"hex8": 0, "hex20": 0, "pent6": 0, "pent15": 0, "pyr5": 0, "tet4": 0, "tet10": 0}
    knoten = set()
    for k in koerper:
        for e in (k.elemente or []):
            el = model.elements[int(e)]
            if el.typ in zaehl:
                zaehl[el.typ] += 1
            knoten.update(int(x) for x in el.nodes)
    n = sum(zaehl.values())
    hexa = zaehl["hex8"] + zaehl["hex20"]
    return {"hexaeder": hexa, "keile": zaehl["pent6"] + zaehl["pent15"], "pyramiden": zaehl["pyr5"],
            "tetraeder": zaehl["tet4"] + zaehl["tet10"], "elemente": n, "knoten": len(knoten),
            "anteil_hexaeder": hexa / n if n else 0.0,
            "elemente_je_knoten": n / len(knoten) if knoten else 0.0}
