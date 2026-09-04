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
``releasedSurfaces`` seine Kopien der Fugenflaeche und ``assignedToObjects``
die Flaechen der Gegenseite. Der Vernetzer legt an gemeinsamen Flaechen
gemeinsame Knoten an - an der Fuge haengen die Bauteile also zusammen und
muessen getrennt werden.

Ausgefuehrt wird in vier Schritten:

1. **Seiten bestimmen.** Geloest wird der Koerper aus ``koerpernamen``;
   ersatzweise der Koerper, dem die freigegebenen Flaechen gehoeren.

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
    """
    from .assemble import SOLID_FACES
    out = []
    for f in flaechen:
        for e, seite in (f.randseiten or []):
            e = int(e)
            if not 0 <= e < len(model.elements):
                continue
            el = model.elements[e]
            seiten = SOLID_FACES.get(el.typ)
            if not seiten or int(seite) >= len(seiten):
                continue
            nd = [int(el.nodes[j]) for j in seiten[int(seite)]]
            n = _aussennormale(model, nd, [int(x) for x in el.nodes])
            if n is not None:
                out.append((e, nd, n))
        for e in (f.elemente or []):
            e = int(e)
            if not 0 <= e < len(model.elements):
                continue
            nd = [int(x) for x in model.elements[e].nodes]
            n = _aussennormale(model, nd[:3], nd)
            if n is not None:
                out.append((e, nd, n))
    return out


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
                           knotengruppen: dict = None) -> dict:
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
    if not flaechen:
        bericht["grund"] = "keine der freigegebenen Flächen ist im Modell"
        return bericht
    dreiecke = _dreiecke_der_fuge(model, flaechen)
    if not dreiecke:
        bericht["grund"] = "die Flächen sind noch nicht vernetzt"
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
    _lager_mitnehmen(model, neu, log)
    bericht["knoten"] = len(neu)

    if not passend:
        # Nur der gemeinsame Rand war verschweisst; die Flaeche dazwischen
        # passt nicht Knoten fuer Knoten. Sie traegt ein Kontaktpaar.
        return _fuge_ueber_kontaktpaar(
            model, kb, _dreiecke_der_fuge(model, flaechen), geloest, bericht, log)

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


def _randseiten_aller(model: Model) -> list:
    """[(Element, Knoten, Aussennormale, Gruppe)] aller Randseiten des Modells."""
    out = []
    for f in (model.flaechen or {}).values():
        for e, nd, n in _dreiecke_der_fuge(model, [f]):
            out.append((e, nd, n, _gruppe(model, e)))
    return out


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
                            bericht: dict, log: list = None) -> dict:
    """Zwei getrennte, aufeinanderliegende Netze ueber ein Kontaktpaar verbinden.

    Passen die Netze an der Fuge nicht Knoten fuer Knoten zusammen, gibt es
    nichts zu trennen - die Bauteile stehen unverbunden nebeneinander und das
    Gleichungssystem waere singulaer. Gesucht werden dann die Gegenflaechen:
    Randseiten anderer Bauteile, die demselben Ort und der entgegengesetzten
    Richtung folgen. Sie werden Master, die Knoten der freigegebenen Seite
    Slave. Das Kontaktpaar traegt Druck und Reibung und laesst Abheben zu - und
    es verlangt **nicht**, dass die beiden Netze zusammenpassen.
    """
    from .importers import _common as C
    from .model import ContactPair
    from scipy.spatial import cKDTree
    # Gesucht wird ueber die **Geometrie**, nicht ueber die Liste der Flaechen,
    # an denen die Freigabe haengt: die ist unvollstaendig. Im Beispielmodell
    # nennt sie fuer 36 freigegebene Flaechen nur 5 Gegenflaechen - die
    # restliche Fuge bliebe unverbunden. Wer aufeinanderliegt und entgegen-
    # gesetzt zeigt, gehoert zur Fuge; das ist nachpruefbar, die Liste nicht.
    alle = [x for x in _randseiten_aller(model) if x[3] not in geloest]
    if not alle:
        bericht["grund"] = "keine Gegenfläche eines anderen Bauteils gefunden"
        return bericht
    schwer_a = np.array([model.nodes[nd].mean(axis=0) for _e, nd, _n, _g in alle])
    norm_a = np.array([n for _e, _nd, n, _g in alle])
    baum = cKDTree(schwer_a)
    # Suchweite: die mittlere Seitenlaenge der Fuge
    laengen = [float(np.linalg.norm(model.nodes[nd[0]] - model.nodes[nd[1]]))
               for _e, nd, _n in seite_b if len(nd) > 1]
    weite = max(float(np.median(laengen)) if laengen else 0.0, 1e-9)
    master, slave = [], set()
    for _e, nd, n in seite_b:
        c = model.nodes[nd].mean(axis=0)
        for j in baum.query_ball_point(c, weite):
            if float(norm_a[j] @ n) > -0.7:
                continue                    # Gegenflaeche muss entgegengesetzt zeigen
            master.append(_nach_normale(model, alle[j][1], alle[j][2]))
            slave.update(int(x) for x in nd)
    if not master:
        bericht["grund"] = ("keine Gegenfläche in Reichweite – die Bauteile "
                            "berühren sich im Netz nicht")
        return bericht
    einmal = {tuple(x): x for x in master}
    b_n = kb.dof_behaviour(2)
    b_t = [kb.dof_behaviour(0), kb.dof_behaviour(1)]
    mu = max(float(b.mu or 0.0) for b in (b_n, *b_t))
    model.contact_pairs.append(ContactPair(
        name=kb.name, slave_nodes=sorted(slave),
        master_faces=[list(v) for v in einmal.values()], mu=mu))
    kb.ausgefuehrt = True
    bericht["kontaktpaar"] = 1
    bericht["slave"] = len(slave)
    bericht["master"] = len(einmal)
    if log is not None:
        C.say(log, f"Kontaktbedingung {kb.name}: "
                   + (f"{bericht['knoten']} Randknoten getrennt, " if bericht["knoten"] else "")
                   + f"Kontaktpaar mit {len(slave)} Knoten gegen "
                   f"{len(einmal)} Gegenflächen"
                   + (f", Reibung mu = {mu:g}" if mu else "")
                   + f" (gelöst: {', '.join(sorted(geloest))})")
        _vorzeichen_melden(kb, b_n, log)
        if any(b.typ == "rigid" for b in b_t):
            C.warn(log, f"  {kb.name}: in der Fugenebene ist die Freigabe starr, "
                        "die Netze passen dort aber nicht Knoten für Knoten "
                        "zusammen. Das Kontaktpaar trägt Druck und Reibung; eine "
                        "starre Verbindung in der Fugenebene gibt es nicht. Wer "
                        "sie braucht, vernetzt beide Seiten gleich fein.")
        else:
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
    for kb in (getattr(model, "kontaktbedingungen", {}) or {}).values():
        b = kontaktfuge_ausfuehren(model, kb, log, knotengruppen)
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
    if not namen:
        return 0
    n = 0
    vorher = (len(model.gap_elements), len(model.kopplungen), len(model.contact_pairs))
    model.gap_elements = [g for g in model.gap_elements
                          if str(getattr(g, "group", "")) not in namen]
    model.kopplungen = [k for k in model.kopplungen
                        if str(getattr(k, "gruppe", "")) not in namen]
    model.contact_pairs = [c for c in model.contact_pairs if c.name not in namen]
    n = (vorher[0] - len(model.gap_elements) + vorher[1] - len(model.kopplungen)
         + vorher[2] - len(model.contact_pairs))
    for kb in (getattr(model, "kontaktbedingungen", {}) or {}).values():
        kb.ausgefuehrt = False
    if n and log is not None:
        C.say(log, f"{n} Verbindungen aus Kontaktbedingungen zurückgenommen "
                   "(sie gehörten zum alten Netz)")
    return n
