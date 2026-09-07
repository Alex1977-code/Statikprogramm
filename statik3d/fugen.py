"""
Kontaktfugen ausfuehren: die Netze an den freigegebenen Flaechen trennen.

Eine **Kontaktbedingung** (in RFEM „Flaechenfreigabe") sagt, dass zwei
Bauteile an einer Flaeche nicht durchverbunden sind: sie liegen aufeinander,
koennen abheben, vielleicht gleiten. Gelesen und gespeichert wurde das
bisher vollstaendig - **ausgefuehrt** aber nicht. Solange die Trennung fehlt,
rechnet das Modell an der Fuge durchverbunden, also zu steif, und es wuerde
dort auch Zug uebertragen, wo in Wirklichkeit ein Spalt aufgeht.

Wie RFEM es ablegt
------------------

``SurfaceReleaseImpl_releasedSolids`` nennt den Koerper, der geloest wird,
``releasedSurfaces`` **dessen ganze Aussenhaut** und ``assignedToObjects`` die
Flaechen, an denen die Freigabe haengt - und das ist die Fuge. Die Aussenhaut
ist es nicht: an einer Lagerbock-Grundplatte sind das 36 Flaechen ueber
1,65 m^2 - Ober- und Unterseite, alle Schmalseiten, alle Buchsenmaentel -, von
denen nur ein Bruchteil an einer Fuge liegt. Der Leser des rf6-Formats setzt
darum ``flaechennamen`` leer und ``gegenflaechen`` auf die zugeordneten
Flaechen, sobald ein geloester Koerper dasteht. Der Vernetzer legt an
gemeinsamen Flaechen gemeinsame Knoten an - an der Fuge haengen die Bauteile
also zusammen und muessen getrennt werden.

Ausgefuehrt wird in vier Schritten:

1. **Seiten bestimmen.** Geloest wird der Koerper aus ``koerpernamen``. Sind
   Kontaktflaechen genannt, sind sie die Fuge; sonst - der Regelfall aus RFEM -
   die Randseiten des Koerpers, die auf den ``gegenflaechen`` liegen.

2. **Knoten verdoppeln.** Jeder Knoten der Fuge, den ausser dem geloesten
   Koerper noch ein anderer benutzt, wird verdoppelt; die Elemente des
   geloesten Koerpers bekommen den neuen Knoten. Danach beruehren sich die
   Netze nur noch geometrisch.

3. **Fugenachsen.** Zu jedem Knotenpaar wird die Flaechennormale aus den
   anliegenden Dreiecken gemittelt; quer dazu stehen zwei Tangenten. In
   diesem System sind die Freiheitsgrade der Freigabe angeschrieben: uz ist
   die Normale, ux und uy liegen in der Fuge.

4. **Verbinden.** Je Freiheitsgrad nach seiner Einstellung:

   ============================  ==================================================
   Einstellung                   Umsetzung
   ============================  ==================================================
   starr                         Kopplung (Straffeder) in dieser Richtung
   Feder c [N/m je m^2]          Kopplung mit c mal Einflussflaeche des Knotens
   frei mit Ausfall              Spaltelement: traegt nur Druck
   frei                          nichts - die Richtung bleibt offen
   ============================  ==================================================

   Ein Reibbeiwert am Normal-Freiheitsgrad geht als Coulomb-Reibung in das
   Spaltelement; die Reibkraft ist damit an die wirkliche Kontaktkraft
   gebunden und nicht an eine geratene.

   Passen die Netze nicht Knoten fuer Knoten - jeder Koerper hat seine eigene
   Flaeche, die Netze sind verschieden fein, die Flaechen sind gekruemmt oder
   nicht deckungsgleich -, traegt ein **Kontaktpaar** die Fuge (Knoten gegen
   Flaeche, wie in ANSYS): die Gegenseite wird im Suchradius gefunden
   (:func:`gegenseite_finden`), Zug „starr“ macht daraus einen Verbund ohne
   Trennung, Schub „starr“ ein Haften ohne Gleiten.

Zum Vorzeichen des Ausfalls
---------------------------

RFEM schreibt den Ausfall als „bei negativer" oder „bei positiver" Kraft -
bezogen auf die **lokale z-Achse der freigegebenen Flaeche**, die in dieser
Datei nicht mitgeliefert wird. Dieselbe Fuge steht darum je nach Lage der
Flaechenachse einmal als „Ausfall bei Zug" und einmal als „Ausfall bei
Druck" in der Datei; im Beispielmodell kommen beide Schreibweisen
nebeneinander vor.

Zwischen zwei **Volumenkoerpern** ist die Frage aber nicht offen: zwei
Bauteile, die aufeinanderliegen, koennen sich nicht durchdringen. Die Fuge
traegt Druck und oeffnet unter Zug - die Richtung folgt darum der Geometrie
(die Normale zeigt in den geloesten Koerper hinein), nicht dem Vorzeichen aus
der Datei. Der Rohwert steht im Protokoll, damit die Annahme nachpruefbar
bleibt.

Die Einflussflaeche eines Knotens ist ein Drittel der anliegenden Dreiecke -
dieselbe Aufteilung, mit der auch eine Flaechenlast auf die Knoten kommt.
"""
from __future__ import annotations

import numpy as np

from .model import Model, GapElement, Kopplung

#: Freiheitsgrade der Freigabe: 0 = ux, 1 = uy (in der Fuge), 2 = uz (Normale)
FUGE_DOF = ("ux", "uy", "uz")


def _tangenten(n: np.ndarray) -> tuple:
    """Zwei Einheitsvektoren quer zur Normalen."""
    hilf = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    t1 = np.cross(hilf, n)
    t1 /= np.linalg.norm(t1)
    return t1, np.cross(n, t1)


def _seiten_flaechen(model: Model, namen) -> list:
    """Die genannten Flaechen, soweit es sie im Modell gibt."""
    return [model.flaechen[x] for x in (namen or [])
            if x in (model.flaechen or {})]


def _dreiecke_der_fuge(model: Model, flaechen: list) -> list:
    """[(Element, Knoten der Seitenflaeche, Aussennormale)] aller Fugenflaechen.

    Die Aussennormale zeigt **aus dem Element heraus**. Sie wird nicht aus der
    Knotenreihenfolge geraten, sondern am gegenueberliegenden Knoten geprueft:
    die Normale zeigt von ihm weg. Ohne diese Probe waere ihr Vorzeichen
    beliebig - und das Spaltelement traege dann Zug statt Druck.

    Gerechnet wird im Block je (Elementtyp, Seite): hunderttausend Randseiten
    einzeln durch numpy zu schicken kostete zwoelf Sekunden je Durchgang.
    """
    from .assemble import SOLID_FACES
    ne = len(model.elements)
    gruppen: dict = {}          # (typ, seite) -> [Element]
    schalen: dict = {}          # Knotenzahl -> [Element]
    for f in flaechen:
        for e, seite in (f.randseiten or []):
            e, seite = int(e), int(seite)
            if not 0 <= e < ne:
                continue
            el = model.elements[e]
            seiten = SOLID_FACES.get(el.typ)
            if not seiten or seite >= len(seiten):
                continue
            gruppen.setdefault((el.typ, seite), []).append(e)
        for e in (f.elemente or []):
            e = int(e)
            if 0 <= e < ne and len(model.elements[e].nodes) >= 3:
                schalen.setdefault(len(model.elements[e].nodes), []).append(e)
    out = []
    for (typ, seite), elems in gruppen.items():
        K = np.array([[int(x) for x in model.elements[e].nodes] for e in elems], dtype=int)
        vorn = list(SOLID_FACES[typ][seite])
        rest = [j for j in range(K.shape[1]) if j not in vorn]
        out.extend(_aussennormalen_block(model, elems, K[:, vorn], K[:, rest] if rest else None))
    for _k, elems in schalen.items():
        K = np.array([[int(x) for x in model.elements[e].nodes] for e in elems], dtype=int)
        out.extend(_aussennormalen_block(model, elems, K, K[:, 3:] if K.shape[1] > 3 else None))
    return out


def _aussennormalen_block(model: Model, elems: list, vorn: np.ndarray, rest) -> list:
    """Die Aussennormalen vieler Seitenflaechen auf einmal (siehe _aussennormale)."""
    X = model.nodes[vorn[:, :3]]                             # (n, 3, 3)
    nrm = np.cross(X[:, 1] - X[:, 0], X[:, 2] - X[:, 0])
    L = np.linalg.norm(nrm, axis=1)
    gut = L > 0
    nrm = nrm / np.where(gut, L, 1.0)[:, None]
    if rest is not None and rest.shape[1]:
        innen = model.nodes[rest].mean(axis=1) - X.mean(axis=1)
        drehen = (nrm * innen).sum(1) > 0
        nrm[drehen] = -nrm[drehen]
    knoten = vorn.tolist()
    return [(int(e), knoten[i], nrm[i]) for i, e in enumerate(elems) if gut[i]]


def _aussennormale(model: Model, nd: list, alle: list):
    """Einheitsnormale der Seitenflaeche, aus dem Element heraus gerichtet."""
    if len(nd) < 3:
        return None
    X = model.nodes[nd[:3]]
    n = np.cross(X[1] - X[0], X[2] - X[0])
    L = float(np.linalg.norm(n))
    if L <= 0:
        return None
    n = n / L
    rest = [k for k in alle if k not in nd]
    if rest:
        innen = model.nodes[rest].mean(axis=0) - X.mean(axis=0)
        if float(n @ innen) > 0:
            n = -n
    return n


def _gruppe(model: Model, elem: int) -> str:
    return str(getattr(model.elements[elem], "group", "") or "")


def _facetten_felder(model: Model, facetten: list) -> tuple:
    """Die Facetten als Felder fuer die vektorisierte Suche.

    Rueckgabe (A, B, C, von, zweite, schwer, norm, umkreis): die Ecken der
    Dreiecke - ein Viereck gibt zwei -, je Dreieck der Index seiner Facette,
    je Facette der Index ihres zweiten Dreiecks (-1 bei einem Dreieck), sowie
    Schwerpunkt, Normale und Umkreis (groesster Abstand vom Schwerpunkt zu
    einer Ecke). Das erste Dreieck der Facette i ist das Dreieck i.
    """
    nf = len(facetten)
    if not nf:
        leer = np.zeros((0, 3))
        return leer, leer, leer, np.zeros(0, int), np.zeros(0, int), leer, leer, np.zeros(0)
    K = np.zeros((nf, 4), dtype=int)
    vier = np.zeros(nf, dtype=bool)
    for i, x in enumerate(facetten):
        nd = x[1]
        K[i, :len(nd)] = [int(k) for k in nd[:4]]
        if len(nd) >= 4:
            vier[i] = True
        else:
            K[i, 3] = K[i, 0]                       # Fuellung: ohne Wirkung auf Dreiecke
    P = model.nodes[K]                                # (nf, 4, 3)
    schwer = np.where(vier[:, None], P.mean(axis=1), P[:, :3].mean(axis=1))
    d = np.linalg.norm(P - schwer[:, None, :], axis=2)
    d[~vier, 3] = 0.0
    umkreis = d.max(axis=1)
    norm = np.array([np.asarray(x[2], float) for x in facetten]).reshape(-1, 3)
    j4 = np.flatnonzero(vier)
    A = np.concatenate([P[:, 0], P[j4, 0]])
    B = np.concatenate([P[:, 1], P[j4, 2]])
    C = np.concatenate([P[:, 2], P[j4, 3]])
    von = np.concatenate([np.arange(nf), j4])
    zweite = np.full(nf, -1, dtype=int)
    zweite[j4] = nf + np.arange(len(j4))
    return A, B, C, von, zweite, schwer, norm, umkreis


def _kantenlaenge(model: Model, facetten: list) -> float:
    """Mittlere (Median-)Kantenlaenge der Facetten."""
    if not facetten:
        return 0.0
    a = np.array([int(x[1][0]) for x in facetten if len(x[1]) > 1], dtype=int)
    b = np.array([int(x[1][1]) for x in facetten if len(x[1]) > 1], dtype=int)
    if not a.size:
        return 0.0
    return float(np.median(np.linalg.norm(model.nodes[a] - model.nodes[b], axis=1)))


def _facettenflaechen(model: Model, facetten: list) -> np.ndarray:
    """Die Flaeche jeder Facette (Dreieck oder Viereck) im Block."""
    if not facetten:
        return np.zeros(0)
    A, B, C, von, _zw, _s, _n, _u = _facetten_felder(model, facetten)
    dreieck = 0.5 * np.linalg.norm(np.cross(B - A, C - A), axis=1)
    out = np.zeros(len(facetten))
    np.add.at(out, von, dreieck)
    return out


def _facettenflaeche(model: Model, nd) -> float:
    return float(_facettenflaechen(model, [(0, list(nd), (0.0, 0.0, 1.0))])[0])


def suchweite(model: Model, seite: list, gegen: list, vorgabe: float = 0.0) -> float:
    """Der Suchradius fuer die Gegenseite (ANSYS: Pinball).

    Vorgegeben aus der Kontaktbedingung, sonst die groessere mittlere
    Kantenlaenge beider Seiten: so weit darf eine Gegenfacette vom Schwerpunkt
    einer Facette entfernt liegen und gehoert noch zur Fuge. Das deckt die
    Facettierung eines groben Netzes auf einer gekruemmten Flaeche und ein
    Spiel in der Groessenordnung der Elemente - und laesst den Rest, der
    wirklich nicht anliegt, in Ruhe.
    """
    if vorgabe and float(vorgabe) > 0:
        return float(vorgabe)
    return max(_kantenlaenge(model, seite), _kantenlaenge(model, gegen), 1e-9)


def gegenseite_finden(model: Model, seite: list, gegen: list, weite: float) -> tuple:
    """Zu jeder Facette der Kontaktseite die naechste Gegenfacette.

    ``seite`` und ``gegen`` sind Listen (Element, Knoten, Aussennormale).
    Gesucht wird wie in ANSYS ueber einen Suchradius (Pinball): eine
    Gegenfacette gehoert dazu, wenn ihre Normale der Facette entgegen zeigt
    und der **naechste Punkt auf ihr** hoechstens ``weite`` vom Schwerpunkt
    der Facette entfernt liegt - nicht ihr Schwerpunkt. So findet ein feines
    Netz auch eine grobe Gegenseite, ein Zylinder seine Bohrung mit Spiel, und
    deckungsgleich muessen die Flaechen nicht sein. Frueher zaehlte der
    Abstand der Schwerpunkte bis zu einer Kantenlaenge der Kontaktseite: bei
    2-mm-Netz gegen 15-mm-Netz fand das von einer Achse in ihrer Bohrung
    sieben Quadratzentimeter.

    Gerechnet wird ohne Schleife ueber die Facetten: die Kandidatenpaare
    kommen aus zwei KD-Baeumen, alles Weitere sind Felder ueber die Paare.

    Rueckgabe ({Index der Facette: Index der Gegenfacette}, Abstand je Facette,
    inf ohne Gegenseite).
    """
    from scipy.spatial import cKDTree
    from .contact import naechste_punkte_dreiecke
    abstand = np.full(len(seite), np.inf)
    if not seite or not gegen:
        return {}, abstand
    A, B, C, von, zweite, cg, ng, rg = _facetten_felder(model, gegen)
    _a, _b, _c, _v, _z, cs, ns, _r = _facetten_felder(model, seite)
    # Vorauswahl: nur Gegenfacetten, deren Umkreis den Kasten der Kontaktseite
    # (um den Suchradius erweitert) beruehrt - von hunderttausend Randseiten
    # eines grossen Modells bleiben so die in der Naehe
    lo, hi = cs.min(axis=0) - weite, cs.max(axis=0) + weite
    kand = np.flatnonzero(np.all(cg + rg[:, None] >= lo, axis=1)
                          & np.all(cg - rg[:, None] <= hi, axis=1))
    if not kand.size:
        return {}, abstand
    # Je Gegenfacette die Facetten der Kontaktseite, deren Schwerpunkt im
    # Suchradius plus ihrem Umkreis liegt (Radius je Abfragepunkt)
    listen = cKDTree(cs).query_ball_point(cg[kand], weite + rg[kand])
    anzahl = np.array([len(x) for x in listen], dtype=int)
    if not anzahl.sum():
        return {}, abstand
    J = np.repeat(kand, anzahl)
    I = np.concatenate([np.asarray(x, dtype=int) for x in listen if x])
    # die Gegenseite zeigt entgegen
    gut = (ng[J] * ns[I]).sum(1) < -0.7
    I, J = I[gut], J[gut]
    if not I.size:
        return {}, abstand
    zw = zweite[J]
    hat2 = zw >= 0
    T = np.concatenate([J, zw[hat2]])           # Dreiecke der Kandidaten
    Ip = np.concatenate([I, I[hat2]])
    q, _w = naechste_punkte_dreiecke(cs[Ip], A[T], B[T], C[T])
    d = np.linalg.norm(q - cs[Ip], axis=1)
    reihe = np.lexsort((d, Ip))                 # je Facette der naechste zuerst
    Ip, d, T = Ip[reihe], d[reihe], T[reihe]
    erste = np.r_[True, Ip[1:] != Ip[:-1]]
    Ip, d, T = Ip[erste], d[erste], T[erste]
    nah = d <= weite
    paare = {int(i): int(von[t]) for i, t in zip(Ip[nah], T[nah])}
    abstand[Ip[nah]] = d[nah]
    return paare, abstand


def _seiten_des_koerpers_auf(model: Model, koerpernamen, gegen: list,
                             weite: float = 0.0, cache: dict = None) -> list:
    """Die Randseiten der genannten Koerper, die auf den Gegenflaechen liegen.

    RFEM kann eine Flaechenfreigabe auch **ohne** freigegebene Flaechen
    anlegen: dann steht nur der geloeste Koerper da (``releasedSolids``), und
    die zugeordneten Flaechen sind die Gegenseite - etwa die Grundplatte, die
    an den sechzehn Oberseiten der Unterlegbleche geloest wird. Die Fuge sind
    dann die Randseiten des Koerpers, die auf diesen Flaechen liegen -
    gefunden mit :func:`gegenseite_finden`, also auch bei Netzen, die nicht
    zusammenpassen.
    """
    if not gegen:
        return []
    geloest = {str(x) for x in (koerpernamen or [])}
    seiten = [(e, nd, n) for e, nd, n, g in _randseiten_aller(model, cache) if g in geloest]
    if not seiten:
        return []
    w = suchweite(model, seiten, gegen, weite)
    paare, _ab = gegenseite_finden(model, seiten, gegen, w)
    return [seiten[i] for i in sorted(paare)]


def gruppen_je_knoten(model: Model) -> dict:
    """{Knoten: Menge der Bauteile, deren Elemente ihn benutzen}.

    Daran - und nur daran - erkennt man, ob eine Fuge im Netz noch
    durchverbunden ist: ein Fugenknoten, den ausser dem geloesten Koerper
    noch ein anderer benutzt, haelt die Bauteile zusammen.
    """
    g: dict = {}
    for el in model.elements:
        grp = str(getattr(el, "group", "") or "")
        for n in el.nodes:
            g.setdefault(int(n), set()).add(grp)
    return g


def kontaktfuge_ausfuehren(model: Model, kb, log: list = None,
                           knotengruppen: dict = None, cache: dict = None) -> dict:
    """Eine einzelne Kontaktbedingung im Netz umsetzen.

    Rueckgabe ein Bericht: verdoppelte Knoten, gesetzte Spaltelemente und
    Kopplungen, sowie der Grund, wenn nichts geschehen ist.
    """
    from .importers import _common as C
    bericht = {"knoten": 0, "spalt": 0, "kopplung": 0,
               "kontaktpaar": 0, "grund": ""}
    if kb.ausgefuehrt:
        bericht["grund"] = "schon ausgeführt"
        return bericht
    if kb.aus:
        bericht["grund"] = "in der Quelldatei deaktiviert"
        return bericht
    flaechen = _seiten_flaechen(model, kb.flaechennamen)
    ueber_gegenseite = False
    if not flaechen and kb.koerpernamen and kb.gegenflaechen:
        # Ohne freigegebene Flaechen: der geloeste Koerper wird an den
        # zugeordneten Flaechen der Gegenseite getrennt.
        flaechen = _seiten_flaechen(model, kb.gegenflaechen)
        ueber_gegenseite = True
    if not flaechen:
        bericht["grund"] = ("keine der freigegebenen Flächen ist im Modell"
                            if kb.flaechennamen or not kb.koerpernamen else
                            "weder freigegebene Flächen noch zugeordnete Gegenflächen im Modell")
        return bericht
    dreiecke = _dreiecke_der_fuge(model, flaechen)
    if not dreiecke:
        bericht["grund"] = "die Flächen sind noch nicht vernetzt"
        return bericht
    if ueber_gegenseite:
        dreiecke = _seiten_des_koerpers_auf(model, kb.koerpernamen, dreiecke,
                                            getattr(kb, "suchweite", 0.0), cache)
        if not dreiecke:
            bericht["grund"] = ("der gelöste Körper liegt im Netz nicht auf den zugeordneten "
                                "Flächen - Körper und Gegenseite vernetzen")
            return bericht

    # ---- 1) Welcher Koerper wird geloest? -------------------------------
    gruppen = {_gruppe(model, x[0]) for x in dreiecke}
    geloest = set(kb.koerpernamen or []) & gruppen
    if not geloest:
        # Ohne Angabe: die freigegebenen Flaechen gehoeren dem geloesten
        # Koerper - so legt RFEM sie an. Sind es mehrere, wird der nach Namen
        # letzte genommen; willkuerlich, aber wiederholbar und protokolliert.
        geloest = set(gruppen) if len(gruppen) == 1 else {sorted(gruppen)[-1]}
    seite_b = [x for x in dreiecke if _gruppe(model, x[0]) in geloest]
    if not seite_b:
        bericht["grund"] = "die freigegebenen Flächen gehören nicht zum gelösten Bauteil"
        return bericht

    # ---- 2) Welche Fugenknoten halten die Bauteile noch zusammen? -------
    # Der Vernetzer teilt Knoten nur ueber **dieselbe** Flaeche. Zwei Bauteile,
    # die an der Fuge eigene, aufeinanderliegende Flaechen haben - so legt RFEM
    # ein Volumenmodell an -, teilen darum nur die Knoten des gemeinsamen
    # Randes (die Linien gehoeren beiden). Daran haengen die Bauteile noch
    # zusammen; die Flaeche dazwischen ist bereits getrennt.
    if knotengruppen is None:
        knotengruppen = gruppen_je_knoten(model)
    fugenknoten = {n for _e, nd, _n in seite_b for n in nd}
    gemeinsam = sorted(k for k in fugenknoten
                       if knotengruppen.get(k, set()) - geloest)
    #: Passen die Netze Knoten fuer Knoten zusammen? Dann - und nur dann - ist
    #: **jeder** Fugenknoten gemeinsam, und die Fuge laesst sich Knoten gegen
    #: Knoten anschreiben. Sonst traegt ein Kontaktpaar die Flaeche.
    passend = len(gemeinsam) == len(fugenknoten)

    # ---- 3) Normalen und Einflussflaechen ------------------------------
    # Die Richtung des Spaltelements zeigt vom bleibenden Knoten zum geloesten,
    # also **in den geloesten Koerper hinein** - das Gegenteil seiner
    # Aussennormalen. Hebt der geloeste Koerper ab, laeuft der Knoten in diese
    # Richtung und die Fuge oeffnet sich; drueckt er, wird das Spaltelement
    # aktiv. Zwei Volumen koennen sich nicht durchdringen - darum gibt die
    # Geometrie die Richtung vor und nicht das Vorzeichen aus der Datei.
    normale: dict = {}
    flaeche: dict = {}
    for _e, nd, n_aus in seite_b:
        X = model.nodes[nd[:3]]
        A = 0.5 * float(np.linalg.norm(np.cross(X[1] - X[0], X[2] - X[0])))
        if A <= 0:
            continue
        for k in nd:
            normale[k] = normale.get(k, np.zeros(3)) - A * n_aus
            flaeche[k] = flaeche.get(k, 0.0) + A / len(nd)

    # ---- 4) Knoten verdoppeln ------------------------------------------
    neu: dict = {}
    for k in gemeinsam:
        neu[k] = int(model.add_node(*model.nodes[k]))
    # Alle Elemente der geloesten Seite umhaengen - nicht nur die an der Fuge:
    # ein Element, das mit einer Kante an der Fuge liegt, gehoert genauso dazu.
    if neu:
        for el in model.elements:
            if str(getattr(el, "group", "") or "") not in geloest:
                continue
            el.nodes = [neu.get(int(n), int(n)) for n in el.nodes]
    # Die Knotenkarte nachfuehren, damit die naechste Fuge richtig sieht,
    # was noch zusammenhaengt.
    for k, n in neu.items():
        knotengruppen[n] = set(geloest)
        knotengruppen[k] = knotengruppen.get(k, set()) - geloest
    if neu:
        _randseiten_vergessen(cache, geloest)
    _lager_mitnehmen(model, neu, log)
    bericht["knoten"] = len(neu)

    if not passend:
        # Nur der gemeinsame Rand war verschweisst; die Flaeche dazwischen
        # passt nicht Knoten fuer Knoten. Sie traegt ein Kontaktpaar. Die
        # Seiten werden neu gelesen: die verdoppelten Knoten haben neue Nummern.
        if ueber_gegenseite:
            seite_neu = _seiten_des_koerpers_auf(model, geloest,
                                                 _dreiecke_der_fuge(model, flaechen),
                                                 getattr(kb, "suchweite", 0.0), cache)
        else:
            seite_neu = _dreiecke_der_fuge(model, flaechen)
        return _fuge_ueber_kontaktpaar(model, kb, seite_neu, geloest, bericht, log, cache)

    # ---- 5) Verbinden ---------------------------------------------------
    b_n = kb.dof_behaviour(2)
    b_t = [kb.dof_behaviour(0), kb.dof_behaviour(1)]
    # Der Reibbeiwert steht in RFEM an den Tangenten und bezieht sich auf die
    # Normalkraft - im Spaltelement steht er an der Normalen.
    mu = max([float(b_n.mu or 0.0)] + [float(b.mu or 0.0) for b in b_t])
    for k in gemeinsam:
        nv = normale.get(k)
        if nv is None or float(np.linalg.norm(nv)) <= 0:
            continue
        nv = nv / float(np.linalg.norm(nv))
        t1, t2 = _tangenten(nv)
        A = float(flaeche.get(k, 0.0))
        a, b = int(k), int(neu[k])
        # Normale
        if b_n.typ == "free" and b_n.failure:
            model.gap_elements.append(
                GapElement(a, b, list(nv), 0.0, 0.0, mu, group=kb.name))
            bericht["spalt"] += 1
        elif b_n.typ != "free":
            k_n = float("inf") if b_n.typ == "rigid" else float(b_n.stiffness) * A
            model.kopplungen.append(Kopplung(a, b, [list(nv)], [k_n], kb.name))
            bericht["kopplung"] += 1
        # Tangenten
        richtungen, werte = [], []
        for beh, t in zip(b_t, (t1, t2)):
            if beh.mu and b_n.typ == "free" and b_n.failure:
                continue                 # Reibung: steckt schon im Spaltelement
            if beh.typ == "rigid":
                richtungen.append(list(t))
                werte.append(float("inf"))
            elif beh.typ == "spring" and beh.stiffness:
                richtungen.append(list(t))
                werte.append(float(beh.stiffness) * A)
        if richtungen:
            model.kopplungen.append(Kopplung(a, b, richtungen, werte, kb.name))
            bericht["kopplung"] += 1

    kb.ausgefuehrt = True
    if log is not None:
        C.say(log, f"Kontaktbedingung {kb.name}: {bericht['knoten']} Knoten "
                   f"verdoppelt, {bericht['spalt']} Spaltelemente, "
                   f"{bericht['kopplung']} Kopplungen "
                   f"(gelöst: {', '.join(sorted(geloest))})")
        _vorzeichen_melden(kb, b_n, log)
        _gleiten_melden(kb, b_n, b_t, mu, log)
    return bericht


def _vorzeichen_melden(kb, b_n, log) -> None:
    """Sagen, dass die Druckrichtung aus der Geometrie kommt - nicht aus der Datei."""
    from .importers import _common as C
    if b_n.typ == "free" and b_n.failure == "druck":
        C.say(log, f"  {kb.name}: in der Quelldatei steht „Ausfall bei "
                   "Druck“ - dieses Vorzeichen bezieht sich dort auf die lokale "
                   "z-Achse der Fläche. Zwischen zwei Volumen trägt die Fuge "
                   "Druck und öffnet unter Zug; danach wird gerechnet.")


def _gleiten_melden(kb, b_n, b_t, mu, log) -> None:
    """Warnen, wenn die Fuge in ihrer Ebene voellig frei bleibt."""
    from .importers import _common as C
    if mu:
        return
    if all(b.typ == "free" and not b.stiffness for b in b_t) and b_n.typ == "free":
        C.warn(log, f"  {kb.name}: in der Fugenebene ist nichts gehalten (keine "
                    "Federn, keine Reibung). Das geloeste Bauteil kann frei "
                    "gleiten - so steht es in der Quelldatei; es braucht dann "
                    "eigene Lager, sonst ist das Gleichungssystem singulaer.")


def _lager_mitnehmen(model: Model, neu: dict, log: list = None) -> int:
    """Lager an verdoppelten Knoten auf beide Seiten legen.

    Vor der Trennung hing an einem Fugenknoten **ein** Knoten mit **einem**
    Lager - und beide Bauteile daran. Nach der Trennung gibt es zwei Knoten;
    behielte nur der alte das Lager, waere die geloeste Seite an dieser Stelle
    unversehens ungelagert. Das Lager wird darum mitgenommen, damit die
    Trennung die Lagerung nicht veraendert.

    Lasten werden **nicht** mitgenommen: eine verdoppelte Kraft waere eine
    andere Aufgabe. Sie bleiben am bleibenden Knoten.
    """
    from copy import deepcopy
    from .importers import _common as C
    n = 0
    for s in list(model.supports):
        if int(s.node) in neu:
            kopie = deepcopy(s)
            kopie.node = int(neu[int(s.node)])
            model.supports.append(kopie)
            n += 1
    for gruppe in (model.line_supports or [], model.surface_supports or []):
        for ls in gruppe:
            knoten = [int(x) for x in (getattr(ls, "nodes", None) or [])]
            dazu = [neu[k] for k in knoten if k in neu]
            if dazu:
                ls.nodes = knoten + dazu
                n += len(dazu)
    if n and log is not None:
        C.say(log, f"  {n} Lager an die neuen Fugenknoten mitgenommen")
    return n


def _randseiten_aller(model: Model, cache: dict = None) -> list:
    """[(Element, Knoten, Aussennormale, Gruppe)] aller Randseiten des Modells.

    Mit ``cache`` - einem Woerterbuch ueber alle Fugen eines Durchgangs hinweg -
    wird je Bauteil nur einmal gerechnet: bei einem halben Millionen Tetraedern
    kostet das Sammeln der Randseiten Sekunden, und acht Fugen brauchten es
    sonst achtmal. Nach dem Verdoppeln von Knoten nimmt
    :func:`_randseiten_vergessen` das betroffene Bauteil heraus, es wird beim
    naechsten Aufruf allein nachgerechnet.
    """
    if cache is None:
        gruppen = _randseiten_rechnen(model, None)
    else:
        gruppen = cache.get("randseiten")
        if gruppen is None:
            gruppen = cache["randseiten"] = _randseiten_rechnen(model, None)
            cache["randseiten_fehlend"] = set()
        fehlend = cache.get("randseiten_fehlend") or set()
        if fehlend:
            neu = _randseiten_rechnen(model, fehlend)
            for g in fehlend:
                gruppen[g] = neu.get(g, [])
            cache["randseiten_fehlend"] = set()
            cache.pop("randseiten_flach", None)
        if "randseiten_flach" in cache:
            return cache["randseiten_flach"]
    flach = [(e, nd, n, g) for g, lst in gruppen.items() for e, nd, n in lst]
    if cache is not None:
        cache["randseiten_flach"] = flach
    return flach


def _randseiten_rechnen(model: Model, nur) -> dict:
    """{Bauteil: [(Element, Knoten, Aussennormale)]} - alle oder nur ``nur``."""
    out: dict = {}
    ne = len(model.elements)
    for f in (model.flaechen or {}).values():
        if nur is not None:
            gs = {_gruppe(model, int(e)) for e, _s in (f.randseiten or []) if 0 <= int(e) < ne}
            gs |= {_gruppe(model, int(e)) for e in (f.elemente or []) if 0 <= int(e) < ne}
            if not (gs & nur):
                continue
        for e, nd, n in _dreiecke_der_fuge(model, [f]):
            g = _gruppe(model, e)
            if nur is None or g in nur:
                out.setdefault(g, []).append((e, nd, n))
    return out


def _randseiten_vergessen(cache: dict, gruppen) -> None:
    """Die Randseiten dieser Bauteile gelten nicht mehr (Knoten verdoppelt)."""
    if cache is None or "randseiten" not in cache:
        return
    for g in gruppen:
        cache["randseiten"].pop(g, None)
    cache.pop("randseiten_flach", None)
    cache.setdefault("randseiten_fehlend", set()).update(gruppen)


def _nach_normale(model: Model, nd: list, n: np.ndarray) -> list:
    """Die Knoten einer Facette so ordnen, dass ihr Umlauf der Normalen folgt.

    Der Kontakt liest die Richtung einer Master-Facette aus der Reihenfolge
    ihrer Knoten: n = (P1-P0) x (P2-P0). Liegen Slave und Master
    aufeinander - und genau das ist eine Kontaktfuge -, laesst sich die
    Richtung **nicht** mehr aus dem Abstand nachtraeglich bestimmen; sie muss
    hier schon stimmen. Sonst zoege die Fuge, statt zu druecken.
    """
    nd = [int(x) for x in nd]
    if len(nd) < 3:
        return nd
    X = model.nodes[nd[:3]]
    if float(np.cross(X[1] - X[0], X[2] - X[0]) @ n) < 0:
        nd = nd[::-1]                 # Umlauf umkehren - auch bei Vierecken
    return nd


def _fuge_ueber_kontaktpaar(model: Model, kb, seite_b: list, geloest: set,
                            bericht: dict, log: list = None, cache: dict = None) -> dict:
    """Zwei getrennte, aufeinanderliegende Netze ueber ein Kontaktpaar verbinden.

    Passen die Netze an der Fuge nicht Knoten fuer Knoten zusammen, gibt es
    nichts zu trennen - die Bauteile stehen unverbunden nebeneinander und das
    Gleichungssystem waere singulaer. Gesucht wird dann die Gegenseite: die
    Randseiten der Gegenkoerper (sind keine genannt: aller anderen Bauteile),
    die der Kontaktseite entgegen zeigen und im Suchradius liegen
    (:func:`gegenseite_finden`). Sie werden Master, die Knoten der
    Kontaktseite Slave. Das Kontaktpaar verlangt **nicht**, dass die Netze
    zusammenpassen oder die Flaechen deckungsgleich sind - wie in ANSYS.

    Aus der Wirkung je Freiheitsgrad wird: Zug „starr“ oder „Feder“ - die
    Fuge oeffnet nicht (Verbund, ohne Trennung); Schub „starr“ - haftend,
    kein Gleiten (Rau, Verbund); sonst Kontakt mit Abheben und Reibung.
    """
    from .importers import _common as C
    from .model import ContactPair
    # Gesucht wird ueber die **Geometrie**, nicht ueber die Liste der Flaechen,
    # an denen die Freigabe haengt: die ist unvollstaendig. Im Beispielmodell
    # nennt sie fuer 36 freigegebene Flaechen nur 5 Gegenflaechen - die
    # restliche Fuge bliebe unverbunden. Wer aufeinanderliegt und entgegen-
    # gesetzt zeigt, gehoert zur Fuge; das ist nachpruefbar, die Liste nicht.
    alle = [x for x in _randseiten_aller(model, cache) if x[3] not in geloest]
    ziel = {str(x) for x in (getattr(kb, "gegenkoerper", None) or [])} - set(geloest)
    if ziel and any(x[3] in ziel for x in alle):
        alle = [x for x in alle if x[3] in ziel]
    if not alle:
        bericht["grund"] = "keine Gegenfläche eines anderen Bauteils gefunden"
        return bericht
    gegen = [(e, nd, n) for e, nd, n, _g in alle]
    weite = suchweite(model, seite_b, gegen, getattr(kb, "suchweite", 0.0))
    paare, abstand = gegenseite_finden(model, seite_b, gegen, weite)
    if not paare:
        bericht["grund"] = (f"keine Gegenfläche im Suchradius {weite * 1e3:.0f} mm – die "
                            "Bauteile berühren sich im Netz nicht (Suchradius der "
                            "Kontaktbedingung vergrößern?)")
        return bericht
    master: dict = {}
    for i, j in paare.items():
        _e, nd, n = gegen[j]
        master.setdefault(tuple(sorted(int(x) for x in nd)), _nach_normale(model, nd, n))
    slave = sorted({int(x) for i in paare for x in seite_b[i][1]})
    flaechen_b = _facettenflaechen(model, seite_b)
    A_zu = float(flaechen_b[sorted(paare)].sum()) if paare else 0.0
    A_alle = float(flaechen_b.sum()) or A_zu or 1.0
    spalt = np.array([abstand[i] for i in paare])
    b_n = kb.dof_behaviour(2)
    b_t = [kb.dof_behaviour(0), kb.dof_behaviour(1)]
    mu = max(float(b.mu or 0.0) for b in (b_n, *b_t))
    zug = b_n.typ in ("rigid", "spring")
    haften = any(b.typ == "rigid" for b in b_t)
    steif = 0.0
    if b_n.typ == "spring" and float(b_n.stiffness or 0.0) > 0:
        # Feder je Flaeche -> je Knoten ueber die mittlere Einflussflaeche
        steif = float(b_n.stiffness) * A_zu / max(len(slave), 1)
    model.contact_pairs.append(ContactPair(
        name=kb.name, slave_nodes=slave,
        master_faces=[list(v) for v in master.values()], mu=mu,
        stiffness=steif, search_radius=2.0 * weite,
        zug=zug, haften=haften, anliegend=bool(getattr(kb, "spalt_schliessen", False))))
    kb.ausgefuehrt = True
    bericht["kontaktpaar"] = 1
    bericht["slave"] = len(slave)
    bericht["master"] = len(master)
    bericht["anteil"] = A_zu / A_alle
    bericht["spalt_max"] = float(spalt.max()) if spalt.size else 0.0
    if log is not None:
        art = ("Verbund" if zug and haften else "ohne Trennung" if zug
               else "haftend" if haften else "")
        C.say(log, f"Kontaktbedingung {kb.name}: "
                   + (f"{bericht['knoten']} Randknoten getrennt, " if bericht["knoten"] else "")
                   + f"Kontaktpaar mit {len(slave)} Knoten gegen {len(master)} Gegenfacetten "
                   f"({A_zu * 1e4:.0f} von {A_alle * 1e4:.0f} cm² der Kontaktseite, "
                   f"Suchradius {weite * 1e3:.0f} mm, Spalt im Mittel "
                   f"{float(np.median(spalt)) * 1e3:.2f} mm, größter {float(spalt.max()) * 1e3:.2f} mm"
                   + (", wird auf Berührung gesetzt" if getattr(kb, "spalt_schliessen", False) else "")
                   + ")"
                   + (f", Reibung mu = {mu:g}" if mu and not haften else "")
                   + (f", {art}" if art else "")
                   + f" (gelöst: {', '.join(sorted(geloest))})")
        if A_zu < 0.5 * A_alle:
            C.say(log, f"  {kb.name}: nur {100 * A_zu / A_alle:.0f} % der Kontaktseite finden "
                       "eine Gegenfläche - der Rest liegt weiter als der Suchradius von "
                       "jedem anderen Bauteil entfernt")
        if any(kb.dof_behaviour(d).typ == "rigid" for d in (3, 4, 5)):
            C.say(log, f"  {kb.name}: Verdrehungen starr - im Kontaktpaar zwischen Volumen "
                       "ohne Wirkung (Volumen haben keine Verdrehungsfreiheitsgrade)")
        _vorzeichen_melden(kb, b_n, log)
        if not zug and not haften:
            _gleiten_melden(kb, b_n, b_t, mu, log)
    return bericht


def kontaktfugen_ausfuehren(model: Model, log: list = None) -> dict:
    """Alle noch offenen Kontaktbedingungen ausfuehren.

    Rueckgabe: Summenbericht. Was nicht geht, steht mit Grund im Protokoll -
    eine Fuge, die stillschweigend zubliebe, waere schlimmer als eine, die
    man nicht ausfuehren konnte.
    """
    from .importers import _common as C
    gesamt = {"fugen": 0, "knoten": 0, "spalt": 0, "kopplung": 0,
              "kontaktpaar": 0, "offen": 0}
    gruende: dict = {}
    offene = [kb for kb in (getattr(model, "kontaktbedingungen", {}) or {}).values()
              if not kb.ausgefuehrt and not kb.aus]
    if not offene:
        return gesamt
    knotengruppen = gruppen_je_knoten(model)
    cache: dict = {}
    for kb in (getattr(model, "kontaktbedingungen", {}) or {}).values():
        b = kontaktfuge_ausfuehren(model, kb, log, knotengruppen, cache)
        if kb.ausgefuehrt and not b["grund"]:
            gesamt["fugen"] += 1
            for x in ("knoten", "spalt", "kopplung", "kontaktpaar"):
                gesamt[x] += b.get(x, 0)
        else:
            gesamt["offen"] += 1
            if b["grund"] and b["grund"] != "schon ausgeführt":
                gruende[b["grund"]] = gruende.get(b["grund"], 0) + 1
    if log is not None:
        if gesamt["fugen"]:
            C.say(log, f"{gesamt['fugen']} Kontaktfugen ausgeführt: "
                       f"{gesamt['knoten']} Fugenknoten, "
                       f"{gesamt['spalt']} Spaltelemente, "
                       f"{gesamt['kopplung']} Kopplungen, "
                       f"{gesamt['kontaktpaar']} Kontaktpaare")
        for grund, n in sorted(gruende.items()):
            C.warn(log, f"  {n} Kontaktbedingung(en) nicht ausgeführt: {grund}")
    return gesamt


#: Gruppenvorsilbe der Kopplungen, die aus starren Flaechen entstehen
STARR_GRUPPE = "starr "


def starre_flaechen(model: Model) -> list:
    """Die Flaechen, die laut Quelldatei starr sind und keine Dicke haben."""
    out = []
    for f in (getattr(model, "flaechen", None) or {}).values():
        if f.dicke:
            continue
        art = (getattr(f, "steifigkeit", "") or "") or (f.kommentar or "")
        if art in ("starr", "starre Deckenscheibe"):
            out.append(f)
    return out


def _punkte_im_polygon(P2: np.ndarray, Q: np.ndarray, rand: float = 0.0) -> np.ndarray:
    """Welche Punkte Q (m,2) im Vieleck P2 (n,2) liegen - Strahlprobe, im Block.
    ``rand`` weitet das Vieleck vom Schwerpunkt aus um diesen Betrag."""
    P2 = np.asarray(P2, float)
    if rand > 0:
        c = P2.mean(axis=0)
        r = float(np.linalg.norm(P2 - c, axis=1).mean()) or 1.0
        P2 = c + (P2 - c) * (1.0 + rand / r)
    x, y = Q[:, 0], Q[:, 1]
    innen = np.zeros(len(Q), dtype=bool)
    m = len(P2)
    for i in range(m):
        x1, y1 = P2[i]
        x2, y2 = P2[(i + 1) % m]
        if y1 == y2:
            continue
        t = (y - y1) / (y2 - y1)
        kreuzt = ((y1 > y) != (y2 > y)) & (x < x1 + t * (x2 - x1))
        innen ^= kreuzt
    return innen


def starre_flaechen_koppeln(model: Model, log: list = None) -> dict:
    """Starre Flaechen (RFEM: SurfaceStiffnessRigid) als starre Kopplung umsetzen.

    Eine starre Flaeche hat keine Dicke und kein Netz: sie ist eine Scheibe,
    die alles, was auf ihr liegt, starr zusammenhaelt. Im Drehlager sind das
    die 64 Kreisscheiben, ueber die die vorgespannten Zugstaebe an den
    Volumen haengen - der Stabknoten sitzt in der Mitte der Scheibe, die
    Scheibe liegt auf der Oberflaeche des Koerpers. Umgesetzt wird sie wie ein
    starrer Bereich in ANSYS: der Knoten in der Mitte (bevorzugt der
    Stabknoten) ist Master, alle Netzknoten in der Scheibe haengen ueber
    starre Kopplungen an ihm. So geht die Stabkraft in den Koerper, und die
    Scheibe verformt sich nicht.

    Rueckgabe {"flaechen": n, "kopplungen": n, "offen": [(Name, Grund)]}.
    Vorhandene Kopplungen dieser Art werden vorher entfernt (neues Netz).
    """
    from scipy.spatial import cKDTree
    from .importers import _common as C
    bericht = {"flaechen": 0, "kopplungen": 0, "offen": []}
    starre = starre_flaechen(model)
    model.kopplungen = [k for k in (getattr(model, "kopplungen", None) or [])
                        if not str(getattr(k, "gruppe", "")).startswith(STARR_GRUPPE)]
    if not starre or not model.nn:
        return bericht
    N = np.asarray(model.nodes[:model.nn], float)
    stab: set = set()
    andere: set = set()
    for e in model.elements:
        (stab if e.typ in ("beam", "truss") else andere).update(int(x) for x in e.nodes)
    baum = cKDTree(N)
    unendlich = float("inf")
    for f in starre:
        try:
            P = np.asarray(f.randpunkte(model, 32), float).reshape(-1, 3)
        except Exception:                 # noqa: BLE001
            P = np.zeros((0, 3))
        if len(P) < 3:
            bericht["offen"].append((f.name, "der Rand schliesst nicht"))
            continue
        c = P.mean(axis=0)
        _u, _s, vt = np.linalg.svd(P - c)
        e1, e2, nrm = vt[0], vt[1], vt[2]
        r = float(np.linalg.norm(P - c, axis=1).max())
        tol = max(0.5e-3, 0.1 * r)
        # Master: der Stabknoten in der Mitte - sonst der naechste Knoten dort
        mitte = [int(i) for i in baum.query_ball_point(c, tol)]
        master = next((i for i in mitte if i in stab), None)
        if master is None and mitte:
            master = min(mitte, key=lambda i: float(np.linalg.norm(N[i] - c)))
        if master is None:
            bericht["offen"].append((f.name, "kein Knoten in der Mitte der Scheibe"))
            continue
        # Slaves: die Netzknoten in der Scheibe (in der Ebene und im Umriss)
        kand = np.asarray(baum.query_ball_point(c, r + tol), dtype=int)
        if not kand.size:
            bericht["offen"].append((f.name, "keine Knoten in der Scheibe"))
            continue
        D = N[kand] - c
        ebene = np.abs(D @ nrm) <= tol
        Q = np.column_stack([D @ e1, D @ e2])
        P2 = np.column_stack([(P - c) @ e1, (P - c) @ e2])
        innen = _punkte_im_polygon(P2, Q, rand=tol)
        slaves = [int(i) for i in kand[ebene & innen] if int(i) != master and int(i) in andere]
        if not slaves:
            bericht["offen"].append((f.name, "keine Netzknoten in der Scheibe - liegt darunter "
                                             "kein vernetzter Koerper?"))
            continue
        for s_ in slaves:
            model.kopplungen.append(Kopplung(int(master), int(s_),
                                             [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                                             [unendlich, unendlich, unendlich], STARR_GRUPPE + f.name))
        if not (getattr(f, "steifigkeit", "") or ""):
            f.steifigkeit = "starr"
        f.kommentar = f"starr: koppelt {len(slaves)} Knoten an K{master}" \
            + (" (Stabende)" if master in stab else "")
        bericht["flaechen"] += 1
        bericht["kopplungen"] += len(slaves)
    if log is not None and (bericht["flaechen"] or bericht["offen"]):
        if bericht["flaechen"]:
            C.say(log, f"{bericht['flaechen']} starre Flächen als starre Kopplung umgesetzt: "
                       f"{bericht['kopplungen']} Netzknoten hängen an ihrem Mittelknoten "
                       "(Stabende ↔ Körperoberfläche, wie ein starrer Bereich in ANSYS)")
        for name, grund in bericht["offen"]:
            C.warn(log, f"  starre Fläche {name} nicht gekoppelt: {grund}")
    return bericht


def kontaktfugen_zuruecksetzen(model: Model, log: list = None) -> int:
    """Alles wieder entfernen, was aus Kontaktbedingungen entstanden ist.

    Vor jedem Neuvernetzen noetig: Spaltelemente, Kopplungen und Kontaktpaare
    zeigen auf Knoten und Elemente des **alten** Netzes. Bliebe eines davon
    stehen, haenge die Fuge in der Luft. Die verdoppelten Knoten selbst bleiben
    liegen - sie tragen dann kein Element mehr und stoeren nicht; das neue Netz
    legt eigene an.
    """
    from .importers import _common as C
    namen = {kb.name for kb in (getattr(model, "kontaktbedingungen", {}) or {}).values()}
    if not namen and not any(str(getattr(k, "gruppe", "")).startswith(STARR_GRUPPE)
                             for k in (getattr(model, "kopplungen", None) or [])):
        return 0
    n = 0
    vorher = (len(model.gap_elements), len(model.kopplungen), len(model.contact_pairs))
    model.gap_elements = [g for g in model.gap_elements
                          if str(getattr(g, "group", "")) not in namen]
    model.kopplungen = [k for k in model.kopplungen
                        if str(getattr(k, "gruppe", "")) not in namen]
    model.contact_pairs = [c for c in model.contact_pairs if c.name not in namen]
    # Kopplungen starrer Flaechen zeigen ebenso auf das alte Netz
    model.kopplungen = [k for k in model.kopplungen
                        if not str(getattr(k, "gruppe", "")).startswith(STARR_GRUPPE)]
    n = (vorher[0] - len(model.gap_elements) + vorher[1] - len(model.kopplungen)
         + vorher[2] - len(model.contact_pairs))
    for kb in (getattr(model, "kontaktbedingungen", {}) or {}).values():
        kb.ausgefuehrt = False
    if n and log is not None:
        C.say(log, f"{n} Verbindungen aus Kontaktbedingungen zurückgenommen "
                   "(sie gehörten zum alten Netz)")
    return n
