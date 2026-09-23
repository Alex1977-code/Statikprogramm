"""
Rechenbarkeit eines Modells: was dem Gleichungssystem fehlt, bevor der
Solver mit „Factor is exactly singular“ abbricht.

* **Unvernetzte Flächen und Volumen**: Geometrie ohne Elemente trägt nichts;
  ein Modell aus RFEM/HiCAD besteht nach dem Import oft nur aus Geometrie und
  ein paar Stäben (Schrauben). Vor dem Rechnen vernetzen.
* **Teiltragwerke ohne Lager**: das Elementnetz zerfällt in zusammenhängende
  Teile; jedes braucht Lager (Knoten-, Linien-, Flächenlager, einseitige
  Lager) oder eine Kopplung an ein gelagertes Teil. Ein Teil, das nur über
  Kontakt (Kontaktpaare, Spaltelemente) gehalten wird, kann rechenbar sein -
  oder abheben; das sagt erst die Kontakt-Iteration.
* **Lose Knoten** tragen kein Element (Rand nicht vernetzter Flächen).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def teiltragwerke(model) -> list:
    """Zusammenhängende Teile des Elementnetzes (Kopplungen verbinden),
    jedes als Liste von Knotennummern - die groessten zuerst.

    Vektorisiert ueber scipy.sparse.csgraph.connected_components: der
    Elementgraph (erster Knoten jedes Elements zu seinen uebrigen) als duenne
    Matrix, die Zusammenhangskomponenten in C. Die Vereinigungs-Suche in
    Python brauchte am Drehlager (1,8 Mio. Tetraeder, 10,9 Mio. Vereinigungen)
    32 s je Aufruf, und die Modellpruefung des Berichts rief sie zweimal
    (12.09.2026).
    """
    import itertools
    from scipy import sparse
    from scipy.sparse import csgraph
    nn = int(model.nn)
    if nn == 0:
        return []
    # Abgeschaltete Staebe (Member.aus) gehoeren nicht zum tragenden Netz:
    # ihre Knoten haengen an nichts und werden beim Loesen festgehalten
    basis = model.grundmaske() if hasattr(model, "grundmaske") else None
    elemente = model.elements if basis is None else [e for i, e in enumerate(model.elements) if basis[i]]
    ne = len(elemente)
    if ne:
        laengen = np.fromiter((len(e.nodes) for e in elemente), int, count=ne)
        flach = np.fromiter(itertools.chain.from_iterable(e.nodes for e in elemente), int,
                            count=int(laengen.sum()))
        elem = np.repeat(np.arange(ne), laengen)
    else:
        flach, elem = np.zeros(0, int), np.zeros(0, int)
    gueltig = (flach >= 0) & (flach < nn)
    flach, elem = flach[gueltig], elem[gueltig]
    belegt = np.zeros(nn, bool)
    belegt[flach] = True
    zeilen, spalten = np.zeros(0, int), np.zeros(0, int)
    if flach.size:
        # Kante: erster gueltiger Knoten des Elements -> jeder weitere
        # (elem ist aufsteigend: der erste Eintrag je Element per searchsorted)
        start = np.searchsorted(elem, np.arange(ne), side="left")
        erster = np.full(ne, -1, int)
        hat = start < elem.size
        idx = np.arange(ne)[hat]
        hat2 = elem[start[hat]] == idx
        erster[idx[hat2]] = flach[start[hat][hat2]]
        a = erster[elem]
        kante = a != flach
        zeilen, spalten = a[kante], flach[kante]
    kopp_a, kopp_b = [], []
    for kp in getattr(model, "kopplungen", []) or []:
        i, j = int(getattr(kp, "node_a", -1)), int(getattr(kp, "node_b", -1))
        if 0 <= i < nn and 0 <= j < nn:
            kopp_a.append(i)
            kopp_b.append(j)
            belegt[i] = belegt[j] = True
    if kopp_a:
        zeilen = np.concatenate([zeilen, np.asarray(kopp_a, int)])
        spalten = np.concatenate([spalten, np.asarray(kopp_b, int)])
    if zeilen.size:
        G = sparse.coo_matrix((np.ones(zeilen.size, np.int8), (zeilen, spalten)), shape=(nn, nn))
        _n, marke = csgraph.connected_components(G, directed=False)
    else:
        marke = np.arange(nn)
    knoten = np.flatnonzero(belegt)
    if knoten.size == 0:
        return []
    order = np.argsort(marke[knoten], kind="stable")
    sortiert = knoten[order]
    grenzen = np.flatnonzero(np.diff(marke[sortiert])) + 1
    gruppen = [g.tolist() for g in np.split(sortiert, grenzen)]
    gruppen.sort(key=lambda g: (-len(g), g[0]))
    return gruppen


def gehaltene_knoten(model) -> tuple:
    """(fest gelagert, nur durch Kontakt gehalten) als Knotenmengen."""
    fest = {int(s.node) for s in model.supports}
    ne = len(model.elements)
    for ls in getattr(model, "line_supports", []) or []:
        kn = list(getattr(ls, "nodes", None) or [])
        if not kn and getattr(ls, "line", "") and ls.line in (getattr(model, "lines", {}) or {}):
            kn = list(model.lines[ls.line].nodes)
        fest.update(int(k) for k in kn)
    for ss in getattr(model, "surface_supports", []) or []:
        kn = list(getattr(ss, "nodes", None) or [])
        for ei in (getattr(ss, "elements", None) or []):
            if 0 <= int(ei) < ne:
                kn += [int(k) for k in model.elements[int(ei)].nodes]
        fest.update(int(k) for k in kn)
    kontakt = set()
    for cs in getattr(model, "contact_supports", []) or []:
        kontakt.add(int(getattr(cs, "node", -1)))
    for g in getattr(model, "gap_elements", []) or []:
        for k in (getattr(g, "nodes", None) or (getattr(g, "node_a", None), getattr(g, "node_b", None))):
            if k is not None:
                kontakt.add(int(k))
    from .contact import master_facets
    for cp in getattr(model, "contact_pairs", []) or []:
        kontakt.update(int(k) for k in (cp.slave_nodes or []))
        # Beide Seiten zaehlen. Die Gegenseite steht in aller Regel als
        # Facetten in ``master_faces`` - so legt fugen.py ein Kontaktpaar an -,
        # als Elementliste in ``master_elements`` nur bei einem von Hand ueber
        # Elemente gebildeten Paar. Wer nur ``master_elements`` liest, sieht
        # die Gegenseite gar nicht: jedes Bauteil, das ausschliesslich
        # Gegenseite ist - die Passstifte, die Unterlegbleche, die Grundplatte
        # eines Lagerbocks -, haette dann weder Lagerknoten noch Slave-Knoten
        # und stuende als "Teiltragwerk ohne Lager" da, obwohl der Kontakt es
        # haelt. ``master_facets`` loest beide Felder auf.
        for f in master_facets(model, cp):
            kontakt.update(int(k) for k in f)
    kontakt.discard(-1)
    return fest, kontakt


# Ein Element ohne Ausdehnung hat keine Steifigkeit: die Elementmatrix wird
# singulaer und die Formulierung bricht ab ("Tetraeder ohne Volumen"). Die
# Grenzen liegen weit unter allem, was ein Bauteil je ist - ein Wuerfel mit
# 0,1 um Kante hat 1e-21 m^3 - und treffen damit nur wirklich entartete
# Elemente, nicht bloss sehr kleine.
GRENZE_LAENGE = 1e-9        # m
GRENZE_FLAECHE = 1e-12      # m^2
GRENZE_VOLUMEN = 1e-15      # m^3


def entartete_elemente(model, hoechstens: int = 0) -> list:
    """Elemente ohne Ausdehnung: doppelte Knoten oder (nahezu) kein Mass.

    Rueckgabe: Liste von (elementindex, art, grund). ``hoechstens`` begrenzt
    die Ausgabe (0 = alle). Vektorisiert je Elementart, weil ein Volumennetz
    mit einer halben Million Tetraedern sonst Minuten braucht - die Pruefung
    laeuft vor **jeder** Rechnung.
    """
    import numpy as _np
    from . import elemente as _EL

    treffer = []
    nn = int(getattr(model, "nn", 0))
    gruppen: dict = {}
    for i, e in enumerate(model.elements):
        gruppen.setdefault(e.typ, []).append(i)

    for typ, idx in gruppen.items():
        art = _EL.ELEMENTE.get(typ)
        familie = art.familie if art is not None else ""
        if familie == "verbindung":
            continue                     # Federn und Grenzschichten duerfen dick null sein
        idx = _np.asarray(idx, int)
        try:
            K = _np.array([[int(x) for x in model.elements[i].nodes] for i in idx], dtype=int)
        except Exception:                # noqa: BLE001 - uneinheitliche Knotenzahl
            continue
        if K.ndim != 2 or not K.size:
            continue
        gueltig = (K >= 0).all(axis=1) & (K < nn).all(axis=1)
        # 1) doppelte Knoten - das ist immer falsch, unabhaengig von der Lage.
        #    Sortieren und Nachbarn vergleichen statt set() je Zeile: bei
        #    370 000 Tetraedern sind das Sekunden Unterschied.
        sortiert = _np.sort(K, axis=1)
        doppelt = (sortiert[:, 1:] == sortiert[:, :-1]).any(axis=1)
        for i in idx[doppelt & gueltig]:
            treffer.append((int(i), typ, "zwei Knoten des Elements sind derselbe"))
        # 2) Mass des Elements
        pruef = gueltig & ~doppelt
        if not pruef.any():
            continue
        jdx, X = idx[pruef], model.nodes[K[pruef]]
        mass, grenze, wort = None, 0.0, ""
        if familie == "stab":
            mass = _np.linalg.norm(X[:, 1] - X[:, 0], axis=1)
            grenze, wort = GRENZE_LAENGE, "Länge"
        elif familie in ("schale", "ebene"):
            e1, e2 = X[:, 1] - X[:, 0], X[:, 2] - X[:, 0]
            mass = 0.5 * _np.linalg.norm(_np.cross(e1, e2), axis=1)
            if K.shape[1] >= 4 and typ in ("shell4", "shell8", "ebene4", "ebene8"):
                e3 = X[:, 3] - X[:, 0]
                mass = mass + 0.5 * _np.linalg.norm(_np.cross(e2, e3), axis=1)
            grenze, wort = GRENZE_FLAECHE, "Fläche"
        elif familie == "volumen":
            if typ in ("tet4", "tet10"):
                mass = _np.abs(_np.einsum("ij,ij->i", X[:, 1] - X[:, 0],
                                          _np.cross(X[:, 2] - X[:, 0], X[:, 3] - X[:, 0]))) / 6.0
            else:
                # Fuer Sechsflaechner, Keile und Pyramiden reicht ein Mass, das
                # nur die *Entartung* erkennt: die Streumatrix der Eckpunkte.
                # Ihre Determinante ist genau dann null, wenn die Punkte in
                # einer Ebene liegen; die dritte Wurzel daraus hat die Einheit
                # eines Volumens. Das laeuft fuer alle Elemente auf einmal,
                # waehrend die exakte Integration je Element Minuten kostet.
                Xc = X - X.mean(axis=1, keepdims=True)
                C = _np.einsum("nki,nkj->nij", Xc, Xc) / X.shape[1]
                mass = _np.sqrt(_np.maximum(_np.linalg.det(C), 0.0))
            grenze, wort = GRENZE_VOLUMEN, "Volumen"
        if mass is None:
            continue
        for i, m in zip(jdx[mass <= grenze], mass[mass <= grenze]):
            treffer.append((int(i), typ, f"{wort} praktisch null ({float(m):.3e})"))
        if hoechstens and len(treffer) >= hoechstens:
            break
    treffer.sort()
    return treffer[:hoechstens] if hoechstens else treffer



#: Ein Koerper gilt als entartet, wenn seine Dicke unter diesem Anteil seiner
#: eigenen Groesse liegt. **Relativ**, nicht absolut: eine feste Schranke in m³
#: liegt bei Metern als Einheit unter dem, was eine Determinante ueberhaupt
#: aufloest - dasselbe Bauteil bekaeme je nach Lage im Raum ein anderes Urteil.
ENTARTET_REL = 1e-7

#: Volumen unter diesem Anteil von d³ (d = Diagonale der Huellbox) ist keines.
ENTARTET_VOL_REL = 1e-9


def entartete_punktwolke(P) -> bool:
    """Liegen alle Punkte in einer Ebene (bzw. auf einer Geraden)?

    Gemessen wird der **kleinste Singulaerwert** der zentrierten Koordinaten,
    bezogen auf die Groesse der Wolke: er ist die Ausdehnung senkrecht zur
    besten Ebene. Die Singulaerwertzerlegung ist rueckwaertsstabil; die frueher
    benutzte Determinante der Streumatrix multipliziert drei Werte und hebt
    damit das Rauschen in die dritte Potenz. Zwei gespiegelte Kopien desselben
    flachen Bauteils bekamen so gegensaetzliche Urteile.
    """
    import numpy as _np
    P = _np.asarray(P, float).reshape(-1, 3)
    if len(P) < 4:
        return True
    d = float(_np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
    if d <= 0.0:
        return True
    Xc = P - P.mean(axis=0)
    s = _np.linalg.svd(Xc, compute_uv=False)
    return float(s[-1]) / _np.sqrt(len(P)) <= ENTARTET_REL * d


def entartetes_volumen(V: float, d: float) -> bool:
    """Ist das Volumen V zu klein fuer einen Koerper der Groesse d (Diagonale
    der Huellbox)? Auch hier relativ - eine absolute Schranke haengt sonst an
    der gewaehlten Laengeneinheit."""
    return abs(float(V)) <= ENTARTET_VOL_REL * max(float(d), 0.0) ** 3


def entartete_menge(model) -> frozenset:
    """Die Indizes der entarteten Elemente - je Modellstand einmal ermittelt.

    Die Assemblierung fragt das fuer Steifigkeit, Masse und Nachlauf; bei
    einer halben Million Elementen darf die Pruefung nicht dreimal laufen.
    Der Modellstand ist an Knotenzahl, Elementzahl und den Knotenkoordinaten
    festgemacht - wer einen Knoten verschiebt, bekommt eine neue Antwort.
    """
    import numpy as _np
    try:
        stand = (int(model.nn), len(model.elements),
                 hash(_np.asarray(model.nodes[:model.nn]).tobytes()))
    except Exception:                       # noqa: BLE001
        return frozenset(i for i, _t, _g in entartete_elemente(model))
    zw = getattr(model, "_entartet_zwischen", None)
    if zw is not None and zw[0] == stand:
        return zw[1]
    res = frozenset(i for i, _t, _g in entartete_elemente(model))
    try:
        model._entartet_zwischen = (stand, res)
    except Exception:                       # noqa: BLE001 - z.B. __slots__
        pass
    return res


def diagnose(model) -> dict:
    """Kennzahlen zur Rechenbarkeit: unvernetzte Geometrie, Teiltragwerke
    ohne Lager, nur durch Kontakt gehaltene Teile, lose Knoten."""
    # Randflaechen von Volumen ohne Dicke brauchen kein eigenes Netz - sie
    # zaehlen nicht als unvernetzt (Model.flaeche_traegt)
    traegt = getattr(model, "flaeche_traegt", None)
    flaechen = [n for n, f in (getattr(model, "flaechen", {}) or {}).items()
                if not (f.elemente or []) and (traegt is None or traegt(n))]
    # Ein Koerper ohne Volumen (alle Randknoten in einer Ebene) kann kein Netz
    # bekommen; er zaehlt darum nicht als unvernetzt, sonst fragte das
    # Programm vor jeder Rechnung nach einem Netz, das es nie geben kann.
    kann = getattr(model, "koerper_traegt", None)
    koerper, ohne_volumen, gescheitert = [], [], []
    for n, k in (getattr(model, "koerper", {}) or {}).items():
        if k.elemente:
            continue
        if not (kann is None or kann(n)):
            ohne_volumen.append(n)
            continue
        # Schon versucht und misslungen: ein zweiter Vernetzungsversuch bringt
        # nichts, und stillschweigend weiterrechnen darf man erst recht nicht.
        if str(getattr(k, "netzgrund", "") or ""):
            gescheitert.append((n, _netzgrund_text(k)))
        else:
            koerper.append(n)
    teile = teiltragwerke(model)
    fest, kontakt = gehaltene_knoten(model)
    ohne = [g for g in teile if not (set(g) & fest) and not (set(g) & kontakt)]
    nur_kontakt = [g for g in teile if not (set(g) & fest) and (set(g) & kontakt)]
    belegt = set(k for g in teile for k in g)
    entartet = entartete_elemente(model)
    return {"koerper_gescheitert": gescheitert,
            "entartete_elemente": entartet,
            "unvernetzte_flaechen": flaechen, "unvernetzte_koerper": koerper,
            "koerper_ohne_volumen": ohne_volumen,
            "teile": len(teile), "groesstes_teil": max((len(g) for g in teile), default=0),
            "ohne_lager": ohne, "nur_kontakt": nur_kontakt,
            "lose_knoten": int(model.nn - len(belegt)),
            "rechenbar": not ohne and bool(model.elements)}


#: Grenzen der Abnahme vor dem Rechnen. Ein Bauteil ist vollstaendig
#: angebunden, oder es ist ein Fehler **mit Namen** - nichts halb Gekoppeltes,
#: nichts stillschweigend Uebergangenes.
ABNAHME_ABDECKUNG = 0.95     #: Anteil der Kontaktseite mit Gegenflaeche
ABNAHME_ELEMENTGUETE = 0.05  #: Formguete des schlechtesten Elements je Koerper
#: Zweite, weichere Stufe (Anforderungen des Vernetzers, 3.4; der Anwender will
#: keine Splitter): Elemente mit Formguete unter 0,10 werden je Koerper als
#: WARNUNG genannt - Zahl, Koerper, die drei schlechtesten mit Nummer -, ohne
#: die Rechnung anzuhalten. Am Drehlager bleiben nach der Nachvernetzung rund
#: 200 in fuenf Koerpern (30 von 53 258 ... 74 von 38 564, schlechteste 0,025;
#: Lauf der Loeser-Sitzung, 21.09.2026) - die Abnahme soll sie zeigen, nicht
#: verschweigen.
ABNAHME_SPLITTER = 0.10
ABNAHME_RANDTREUE = 0.99     #: Netzhaut gegen Huelle je Koerper
#: Volumenbilanz je Koerper: das Volumen, mit dem der Loeser rechnet
#: (Jacobi-Integration je Element), gegen das Volumen, das die Randflaechen
#: einschliessen. Dieselbe Grenze, mit der der freie Vernetzer sein eigenes
#: Netz abnimmt (mesher3d.VOLUMEN_ABW_MAX = 0,5 %).
ABNAHME_VOLUMENBILANZ = 0.005
#: Eine freie Elementseite liegt auf einer Randflaeche, wenn der Schwerpunkt
#: ihrer Ecken naeher als dieser Anteil ihres Durchmessers daran liegt.
ABNAHME_HUELLABSTAND = 0.01


@dataclass
class Befund:
    """Eine Verletzung der Abnahme - mit Namen, Zahl und Grenze.

    Keine Sammelmeldung und keine Auslassungspunkte: sind zwoelf Bauteile
    betroffen, stehen zwoelf Befunde da. Wer etwas abstellen soll, muss
    wissen, **was** und **wo**.
    """
    pruefung: str = ""
    objekt: str = ""
    element: int = -1
    knoten: list = field(default_factory=list)
    wert: float = 0.0
    grenze: float = 0.0
    text: str = ""
    stufe: str = "FEHLER"                #: FEHLER haelt an, WARNUNG nennt nur


def abnahme(model, guete: list = None, warnungen: bool = False) -> list:
    """Das Netz vor dem Rechnen abnehmen: je Verletzung ein :class:`Befund`.

    Ein ehrlicher Fehler vor dem Lauf ist mehr wert als ein unzuverlaessiges
    Ergebnis nach neun Minuten. Geprueft wird:

    1. **Elemente, die eine Kontaktfuge ueberspannen** - beim Ausfuehren einer
       Fuge werden Randknoten verdoppelt; danach darf kein Element einen
       Knoten der alten und einen der neuen Seite zugleich benutzen. Sonst
       ueberbrueckt es genau die Trennung, die eben entstand, und die Fuge
       wirkt dort nicht. Das ist der Fall, den man von aussen als „halb
       vernetzt" sieht.
    2. **Abdeckung der Kontaktseite** - wie viel ihrer Flaeche eine Gegenseite
       gefunden hat (:data:`ABNAHME_ABDECKUNG`).
    3. **Gegenkoerper ohne Facette** - ein Koerper, den die Kontaktbedingung
       als Gegenseite nennt und der nichts beisteuert, ist ein Fehler mit
       Namen; heute verschwaende er lautlos.
    4. **Haltegueete je Teiltragwerk** (:data:`singular.HALTEGUETE_MIN`) -
       ``guete`` nimmt ein schon gerechnetes Ergebnis entgegen, sonst wird es
       hier ermittelt.
    5. **Knoten ohne Element**, **Elementgueete** und **Randtreue je Koerper**.
    6. **Volumenbilanz** und **Seiten neben der Huelle** je Koerper - das
       Netz gegen seine Randflaechen (:func:`_abnahme_volumenbilanz`); findet
       den verdrehten Sechsflaechner, den keine Pruefung am Element sieht.

    Faellt eine der Teilpruefungen aus (die Halteguete oder die Formguete
    lassen sich nicht ermitteln), erscheint das als eigener Befund der Stufe
    WARNUNG mit dem Zusatz „nicht geprueft" im Namen - eine leere Liste hiesse
    sonst „abgenommen", obwohl gar nicht gemessen wurde.

    Rueckgabe die Liste der Befunde; leer heisst: das Netz ist abgenommen.
    Mit ``warnungen=True`` stehen auch die Befunde der Stufe WARNUNG dabei
    (Splitter unter :data:`ABNAHME_SPLITTER` je Koerper) - sie halten nichts
    an, der Aufrufer trennt sie an ``Befund.stufe``.
    """
    aus: list = []
    aus += _abnahme_fugen(model)
    aus += _abnahme_huellen(model)
    aus += _abnahme_gemeinsame_flaechen(model)
    aus += _abnahme_kontaktpaare(model)
    aus += _abnahme_halteguete(model, guete)
    aus += _abnahme_netz(model)
    if not warnungen:
        aus = [b for b in aus if getattr(b, "stufe", "FEHLER") != "WARNUNG"]
    return aus


def _abnahme_gemeinsame_flaechen(model) -> list:
    """Zwei Koerper mit derselben Randflaeche teilen dort ihre Knoten.

    Sonst stehen sie unverbunden nebeneinander: die Flaeche ist zweimal
    vernetzt, die Kraefte gehen nicht hinueber, und von aussen sieht das Netz
    tadellos aus. Es ist der stillste aller Netzfehler - und der teuerste,
    denn er verfaelscht jede Schnittgroesse jenseits der Fuge.

    Geprueft wird je Koerperpaar mit gemeinsamer Flaeche: die Randknoten des
    einen, die auf dem Rand des anderen liegen, muessen **dieselben
    Knotennummern** sein. Zwei Sorten Verletzung werden getrennt genannt,
    weil sie verschiedene Ursachen haben:

    * **doppelt** - gleicher Ort, andere Nummer. Die Teilung passt, aber die
      Knoten wurden zweimal angelegt.
    * **haengend** - kein Knoten des Nachbarn in der Naehe. Die beiden haben
      die gemeinsame Linie oder Flaeche verschieden fein geteilt.
    """
    import numpy as np
    from .assemble import SOLID_FACES
    from . import mesher3d as M3
    koerper = getattr(model, "koerper", None) or {}
    if not koerper:
        return []
    fk: dict = {}
    for k in koerper.values():
        for fn in (k.flaechen or []):
            fk.setdefault(fn, []).append(k.name)
    paare: dict = {}
    for fn, ks in fk.items():
        if len(ks) == 2:
            paare.setdefault(tuple(sorted(ks)), []).append(fn)
    if not paare:
        return []
    gebraucht = {n for pp in paare for n in pp}
    rand: dict = {}
    for name in gebraucht:
        k = koerper.get(name)
        seiten = _freie_seiten_des_koerpers(model, k, SOLID_FACES)
        if seiten is not None:
            rand[name] = seiten
    aus = []
    N = np.asarray(model.nodes, float)
    for (a, b), flaechen in sorted(paare.items()):
        if a not in rand or b not in rand:
            continue
        ia, _Ta = rand[a]
        ib, Tb = rand[b]
        if not len(ia) or not len(Tb):
            continue
        # Welche Randknoten von A liegen auf dem Rand von B?
        d_flaeche = np.asarray(M3.abstand_zur_huelle(N[ia], N, Tb))
        auf = ia[d_flaeche < ABNAHME_FUGENWEITE]
        if not len(auf):
            continue
        setb = set(int(x) for x in ib)
        gleich = np.array([int(i) in setb for i in auf])
        from scipy.spatial import cKDTree
        dk, _ = cKDTree(N[ib]).query(N[auf])
        doppelt = int(((~gleich) & (dk < ABNAHME_FUGENNAEHE)).sum())
        haengend = int(((~gleich) & (dk >= ABNAHME_FUGENNAEHE)).sum())
        if doppelt or haengend:
            schlecht = [int(i) for i, g in zip(auf, gleich) if not g]
            aus.append(Befund(
                pruefung="gemeinsame Fläche", objekt=f"{a} | {b}",
                knoten=schlecht[:20],
                wert=float(doppelt + haengend), grenze=0.0,
                text=(f"{a} und {b} teilen sich {', '.join(sorted(flaechen)[:5])}, "
                      f"sind dort aber nicht verbunden: {doppelt} doppelte und "
                      f"{haengend} hängende von {len(auf)} Knoten auf der Fuge - "
                      "die Kräfte gehen nicht hinüber")))
    return aus


def _freie_seiten_des_koerpers(model, koerper, SOLID_FACES):
    """(Randknoten, Randdreiecke) eines Volumenkoerpers - oder None.

    Frei heisst: die Elementseite liegt in genau einem Element. Vierecke
    werden in zwei Dreiecke geteilt, damit sich der Abstand zu ihnen
    ausrechnen laesst.
    """
    import numpy as np
    els = [int(e) for e in (getattr(koerper, "elemente", None) or [])]
    if not els:
        return None
    zahl: dict = {}
    for e in els:
        if not 0 <= e < len(model.elements):
            continue
        el = model.elements[e]
        seiten = SOLID_FACES.get(el.typ)
        if not seiten:
            continue
        for seite in seiten:
            ecken = tuple(int(el.nodes[j]) for j in seite)
            zahl.setdefault(tuple(sorted(ecken)), []).append(ecken)
    dreiecke, knoten = [], set()
    for key, vorkommen in zahl.items():
        if len(vorkommen) != 1:
            continue
        ecken = vorkommen[0]
        knoten.update(key)
        if len(ecken) >= 3:
            dreiecke.append(ecken[:3])
        if len(ecken) >= 4:
            dreiecke.append((ecken[0], ecken[2], ecken[3]))
    if not knoten or not dreiecke:
        return None
    return np.array(sorted(knoten), int), np.array(dreiecke, int)


#: Bis zu diesem Abstand gilt ein Knoten des Nachbarn als **derselbe** Punkt
ABNAHME_FUGENNAEHE = 1e-6

#: Bis zu diesem Abstand liegt ein Knoten noch auf der Flaeche des Nachbarn -
#: findet er dort keinen Partner, haengt er
ABNAHME_FUGENWEITE = 1e-5


def _abnahme_fugen(model) -> list:
    """Elemente, die eine ausgefuehrte Kontaktfuge ueberbruecken.

    Die Pruefung ist billig: fuer jedes getrennte Knotenpaar (alt, neu) darf
    kein Element beide Nummern enthalten. Gesucht wird in einem Durchgang
    ueber die Elemente, und nur die Elemente, die ueberhaupt einen getrennten
    Knoten benutzen, werden genauer angesehen.
    """
    paare = getattr(model, "getrennte_knoten", None) or {}
    if not paare:
        return []
    partner: dict = {}
    fuge_von: dict = {}
    for name, liste in paare.items():
        for a, b in liste:
            partner[int(a)] = int(b)
            partner[int(b)] = int(a)
            fuge_von[int(a)] = fuge_von[int(b)] = str(name)
    aus = []
    for i, e in enumerate(model.elements):
        nd = [int(x) for x in e.nodes]
        beide = [k for k in nd if partner.get(k, -1) in nd]
        if not beide:
            continue
        k = min(beide)
        aus.append(Befund(
            pruefung="Fuge überbrückt", objekt=str(getattr(e, "group", "") or ""),
            element=i, knoten=[k, partner[k]], wert=1.0, grenze=0.0,
            text=f"Element {i} ({e.typ}, Bauteil "
                 f"{getattr(e, 'group', '') or '?'}) benutzt die Knoten {k} und "
                 f"{partner[k]} - beide Seiten der Fuge „{fuge_von.get(k, '?')}“. "
                 "Es überbrückt die Trennung; die Fuge wirkt dort nicht."))
    return aus


def _abnahme_huellen(model) -> list:
    """Geschlossene Huellen: jede Randlinie gehoert zu genau zwei Raendern.

    Ein Volumenkoerper aus RFEM ist eine Randdarstellung. Ist er dicht, kommt
    jede seiner Randlinien in genau zwei Flaechenraendern vor - einmal von
    jeder Seite. Kommt eine nur einmal vor, fehlt dort eine Flaeche.

    **Die Oeffnungsringe zaehlen mit.** Wer sie vergisst, haelt die Haelfte der
    Koerper fuer kaputt: am Drehlagermodell melden 26 der 108 Koerper offene
    Kanten, wenn man nur die Aussenraender zaehlt (V33 allein 118, V14 160),
    und **keiner einzige**, wenn man die Innenraender mitnimmt. Ein Innenrand
    ist Teil des Randes - die Wand einer Bohrung stoesst dort an.

    Geprueft wird nur, wo die Angabe vollstaendig ist: ein Koerper, dessen
    Flaechen keine Randlinien tragen (von Hand aus Elementen gebaut), sagt zu
    dieser Frage nichts.
    """
    aus = []
    flaechen = getattr(model, "flaechen", None) or {}
    for name, k in (getattr(model, "koerper", None) or {}).items():
        namen = [x for x in (getattr(k, "flaechen", None) or [])]
        teile = [flaechen.get(x) for x in namen]
        if not namen or any(f is None or not (f.linien or []) for f in teile):
            continue
        zahl: dict = {}
        for f in teile:
            for ln in (f.linien or []):
                zahl[ln] = zahl.get(ln, 0) + 1
            for ring in (f.oeffnungen or []):
                for ln in ring:
                    zahl[ln] = zahl.get(ln, 0) + 1
        offen = sorted(ln for ln, n in zahl.items() if n != 2)
        if offen:
            aus.append(Befund(
                pruefung="Hülle offen", objekt=str(name),
                wert=float(len(offen)), grenze=0.0,
                text=f"Volumen {name}: {len(offen)} Randlinien gehören nicht zu "
                     f"genau zwei Flächenrändern (z. B. "
                     + ", ".join(offen[:5]) + (" …" if len(offen) > 5 else "")
                     + ") - dort fehlt eine Fläche, die Hülle ist nicht dicht."))
    return aus


def _abnahme_kontaktpaare(model) -> list:
    """Abdeckung der Kontaktseite und Gegenkoerper ohne Facette."""
    aus = []
    kbs = getattr(model, "kontaktbedingungen", None) or {}
    for cp in (getattr(model, "contact_pairs", None) or []):
        a = float(getattr(cp, "abdeckung", 0.0) or 0.0)
        if 0.0 < a < ABNAHME_ABDECKUNG:
            aus.append(Befund(
                pruefung="Abdeckung der Kontaktseite", objekt=str(cp.name),
                wert=a, grenze=ABNAHME_ABDECKUNG,
                text=f"Kontaktpaar {cp.name}: nur {a * 100:.0f} % der Kontaktseite "
                     f"finden eine Gegenfläche (Grenze {ABNAHME_ABDECKUNG * 100:.0f} %). "
                     "Der Rest liegt weiter entfernt als der Suchradius - dort "
                     "überträgt die Fuge nichts."))
        kb = kbs.get(str(cp.name))
        genannt = {str(x) for x in (getattr(kb, "gegenkoerper", None) or [])} if kb else set()
        gestellt = {str(x) for x in (getattr(cp, "gegenkoerper", None) or [])}
        # Ein Bauteil traegt die Fuge auch dann, wenn es die **Knotenseite**
        # stellt statt der Facetten. An einer gemeinsamen Flaeche steht in
        # koerpernamen/gegenkoerper nicht zwingend dieselbe Rolle wie in den
        # Flaechenlisten: am Drehlager nannte V29-V34 die Flaechen von V34 als
        # Kontaktseite, die Facetten kamen von V29 - die Fuge deckte 100 % ab
        # und trug, die Pruefung meldete trotzdem einen Mangel (18.09.2026).
        if genannt - gestellt:
            traeger = set()
            for i in (getattr(cp, "slave_nodes", None) or []):
                for kn in _koerper_des_knotens(model, int(i)):
                    traeger.add(str(kn))
            gestellt |= traeger
        for name in sorted(genannt - gestellt):
            aus.append(Befund(
                pruefung="Gegenkörper ohne Facette", objekt=str(cp.name),
                wert=0.0, grenze=1.0,
                text=f"Kontaktbedingung {cp.name} nennt {name} als Gegenseite, "
                     "aber von diesem Bauteil ist weder eine Facette noch ein "
                     "Knoten in der Fuge gelandet - die Fuge trägt dorthin nichts ab."))
    return aus


def _koerper_des_knotens(model, knoten: int) -> set:
    """Die Bauteile, deren Elemente diesen Knoten benutzen - einmal je Modell
    aufgebaut und am Modell gemerkt (die Abnahme fragt viele Knoten ab)."""
    karte = getattr(model, "_abnahme_knotenkoerper", None)
    if karte is None or getattr(model, "_abnahme_knotenkoerper_n", -1) != len(model.elements):
        karte = {}
        for el in model.elements:
            grp = str(getattr(el, "group", "") or "")
            if not grp:
                continue
            for n in el.nodes:
                karte.setdefault(int(n), set()).add(grp)
        model._abnahme_knotenkoerper = karte
        model._abnahme_knotenkoerper_n = len(model.elements)
    return karte.get(int(knoten), set())


def _abnahme_halteguete(model, guete: list = None) -> list:
    """Teiltragwerke, die zwar gehalten sind, aber in einer Richtung fast nicht."""
    from .singular import HALTEGUETE_MIN, restfreiheiten
    aus = []
    if guete is None:
        guete = []
        try:
            restfreiheiten(model, guete=guete)
        except Exception as ex:           # noqa: BLE001 - eine Abnahme darf nie sperren
            # **„Ausgefallen" ist nicht „nichts gefunden".** Eine leere Liste
            # heisst in abnahme() ausdruecklich „das Netz ist abgenommen" -
            # eine von sechs Teilpruefungen fiel damit aus, ohne dass es
            # jemand erfuhr. Was schon gemessen wurde, bleibt ausserdem
            # stehen: restfreiheiten fuellt guete je Teiltragwerk
            # fortlaufend, und ein Fehler beim 40. von 60 warf bisher auch
            # die 39 gemessenen Werte weg.
            #
            # Stufe WARNUNG und nicht FEHLER: eine ausgefallene Messung ist
            # keine Verletzung des Modells. Als FEHLER stuende vor jedem Lauf
            # die Rueckfrage „Trotzdem rechnen?", und die Ueberschrift
            # „bestanden, soweit geprueft" waere toter Code.
            aus.append(Befund(
                pruefung="Haltegüte nicht geprüft", wert=0.0, grenze=0.0,
                stufe="WARNUNG",
                text="Die Haltegüte der Teiltragwerke konnte nicht ermittelt "
                     f"werden ({type(ex).__name__}: {str(ex)[:100]}) - ob ein "
                     "Bauteil in einer Richtung fast ohne Steifigkeit gehalten "
                     "ist, ist hier nicht geprüft."))
    for g in sorted((x for x in (guete or []) if 0.0 < x.wert < HALTEGUETE_MIN),
                    key=lambda x: x.wert):
        aus.append(Befund(
            pruefung="Haltegüte", objekt=", ".join(g.koerper[:3]),
            knoten=list(g.knoten[:1]), wert=g.wert, grenze=HALTEGUETE_MIN,
            text=g.text + f" (Grenze {HALTEGUETE_MIN:.0e})"))
    return aus


def _abnahme_netz(model) -> list:
    """Knoten ohne Element, Elementgueete, Randtreue und Volumenbilanz je Koerper."""
    aus = []
    belegt = {int(n) for e in model.elements for n in e.nodes}
    lose = [k for k in range(model.nn) if k not in belegt]
    if lose:
        aus.append(Befund(
            pruefung="Knoten ohne Element", knoten=lose[:8],
            wert=float(len(lose)), grenze=0.0,
            text=f"{len(lose)} Knoten im Rechennetz hängen an keinem Element "
                 f"(z. B. {', '.join('K' + str(k) for k in lose[:6])}"
                 + (" …" if len(lose) > 6 else "") + ") - sie tragen nichts, "
                 "und eine Last darauf ginge verloren."))
    try:
        from .netzguete import guete as _formguete
        q = _formguete(model)
    except Exception as ex:               # noqa: BLE001
        q = None
        # Ohne Formguete entfallen Elementguete UND Splitter fuer **jeden**
        # Koerper zugleich. Auch das ist nicht „nichts gefunden".
        aus.append(Befund(
            pruefung="Elementgüte nicht geprüft", wert=0.0, grenze=0.0,
            stufe="WARNUNG",
            text="Die Formgüte der Elemente konnte nicht ermittelt werden "
                 f"({type(ex).__name__}: {str(ex)[:100]}) - Elementgüte und "
                 "Splitter sind für kein Volumen geprüft."))
    for name, k in (getattr(model, "koerper", None) or {}).items():
        els = [int(x) for x in (k.elemente or []) if 0 <= int(x) < len(model.elements)]
        if els and q is not None:
            werte = [float(q[i]) for i in els if np.isfinite(q[i])]
            offen = len(els) - len(werte)
            if offen:
                aus.append(Befund(
                    pruefung="Elementgüte nicht geprüft", objekt=str(name),
                    wert=float(offen), grenze=0.0, stufe="WARNUNG",
                    text=f"Volumen {name}: von {len(els)} Elementen ließ sich bei "
                         f"{offen} die Formgüte nicht ermitteln - sie sind weder "
                         "auf Elementgüte noch auf Splitter geprüft."))
            if werte and min(werte) < ABNAHME_ELEMENTGUETE:
                i = els[int(np.argmin([q[j] for j in els]))]
                aus.append(Befund(
                    pruefung="Elementgüte", objekt=str(name), element=i,
                    knoten=[int(x) for x in model.elements[i].nodes],
                    wert=min(werte), grenze=ABNAHME_ELEMENTGUETE,
                    text=f"Volumen {name}: Element {i} hat die Formgüte "
                         f"{min(werte):.3f} (Grenze {ABNAHME_ELEMENTGUETE:.2f}) - "
                         "ein Splitter, der die Steifigkeitsmatrix verdirbt."))
            # Zweite Stufe: Splitter unter 0,10 als WARNUNG mit Zahl und Nummern.
            # **Nicht messbar ist nicht „beste Form".** Bis zum 22.09.2026 ging
            # ein nan hier als 1,000 ein - ein Element, dessen Form sich nicht
            # ermitteln liess, galt damit als das formbeste ueberhaupt
            # (gemessen 1,000 statt 0,039, Faktor 26 zu gut). Solche Elemente
            # zaehlen jetzt gar nicht mit; sie stehen oben als „Elementgüte
            # nicht geprüft".
            gemessen = [i for i in els if np.isfinite(q[i])]
            qe = np.array([q[i] for i in gemessen], float)
            splitter = (np.nonzero(qe < ABNAHME_SPLITTER)[0] if len(qe)
                        else np.zeros(0, int))
            if len(splitter):
                reihe = splitter[np.argsort(qe[splitter])][:3]
                namen = ", ".join(f"Element {gemessen[int(j)]} ({qe[int(j)]:.3f})"
                                  for j in reihe)
                aus.append(Befund(
                    pruefung="Splitter", objekt=str(name),
                    element=int(gemessen[int(reihe[0])]),
                    knoten=[int(x) for x in
                            model.elements[int(gemessen[int(reihe[0])])].nodes],
                    wert=float(qe[int(reihe[0])]), grenze=ABNAHME_SPLITTER, stufe="WARNUNG",
                    text=f"Volumen {name}: {len(splitter)} von {len(gemessen)} Elementen "
                         f"mit Formgüte unter {ABNAHME_SPLITTER:.2f} - "
                         f"schlechteste: {namen}."))
        rt = float(getattr(k, "randtreue", 0.0) or 0.0)
        if 0.0 < rt < ABNAHME_RANDTREUE:
            aus.append(Befund(
                pruefung="Randtreue", objekt=str(name), wert=rt,
                grenze=ABNAHME_RANDTREUE,
                text=f"Volumen {name}: das Netz deckt nur {rt * 100:.1f} % der "
                     f"Hülle (Grenze {ABNAHME_RANDTREUE * 100:.0f} %) - die "
                     "Geometrie ist im Netz nicht vollständig abgebildet."))
        if els:
            try:
                aus += _abnahme_volumenbilanz(model, name, k, els)
            except Exception as ex:       # noqa: BLE001 - eine Abnahme darf nie sperren
                # Nicht nach oben durchlassen: die Oberflaeche faengt eine
                # Ausnahme aus abnahme() als „Abnahme nicht möglich" ab, und
                # dann fielen alle anderen Teilpruefungen mit aus.
                aus.append(Befund(
                    pruefung="Volumenbilanz nicht geprüft", objekt=str(name),
                    wert=0.0, grenze=0.0, stufe="WARNUNG",
                    text=f"Volumen {name}: Volumenbilanz und freie Seiten ließen sich "
                         f"nicht prüfen ({type(ex).__name__}: {str(ex)[:100]}) - ob ein "
                         "Element verdreht ist, ist hier nicht geprüft."))
    return aus


#: Elemente je Block der gestapelten Jacobi-Integration. Begrenzt den
#: Speicher: 200 000 hex8 sind (200 000, 8, 3) Koordinaten, 38 MB.
_VOLUMEN_STAPEL = 200_000


def _knotenmatrizen(model, els) -> dict:
    """{Elementart: (Stellen in els, Knotenmatrix (n, Knotenzahl))} - einmal
    gebaut und von Volumen und freien Seiten gemeinsam benutzt. Das
    Einsammeln der Knotennummern ist eine Schleife je Element; zweimal
    gemacht kostete es an 64 000 hex8 0,22 s von 1,1 s."""
    els = np.asarray(els, int)
    gruppen: dict = {}
    for p, i in enumerate(els):
        gruppen.setdefault(model.elements[int(i)].typ, []).append(p)
    aus = {}
    for typ, pos in gruppen.items():
        pos = np.asarray(pos, int)
        K = np.array([model.elements[int(i)].nodes for i in els[pos]], dtype=np.int64)
        aus[typ] = (pos, K)
    return aus


def _det3(J: np.ndarray) -> np.ndarray:
    """Determinante eines Stapels (n, 3, 3), ausgeschrieben - fuer 3 x 3
    schneller als die LU-Zerlegung von np.linalg.det."""
    return (J[:, 0, 0] * (J[:, 1, 1] * J[:, 2, 2] - J[:, 1, 2] * J[:, 2, 1])
            - J[:, 0, 1] * (J[:, 1, 0] * J[:, 2, 2] - J[:, 1, 2] * J[:, 2, 0])
            + J[:, 0, 2] * (J[:, 1, 0] * J[:, 2, 1] - J[:, 1, 1] * J[:, 2, 0]))


def elementvolumina(model, els, gruppen: dict = None) -> np.ndarray:
    """Volumen je Element aus der Jacobi-Integration (nan fuer Elemente, die
    keine Volumenelemente sind).

    Dasselbe, womit der Loeser rechnet - elements.solid.solid_volume summiert
    w * |det J| ueber die Gausspunkte -, aber gestapelt je Elementart: je
    Gausspunkt eine (n, 3, 3)-Determinante statt einer Schleife je Element.
    Beim verdrehten Sechsflaechner ist det J an allen acht Gausspunkten
    positiv (Nachtrag A, 22.09.2026); der Betrag aendert dort nichts, er
    steht hier nur, damit die Zahl dieselbe ist wie im Element.
    """
    from .elements import solid as sl
    els = np.asarray(els, int)
    V = np.full(len(els), np.nan)
    for typ, (pos, K_alle) in (gruppen or _knotenmatrizen(model, els)).items():
        try:
            GP, W = sl.gauss(typ)
        except ValueError:
            continue                        # kein Volumenelement
        dNT = [np.ascontiguousarray(sl.N_dN(typ, *gp)[1].T) for gp in GP]   # (3, k)
        for a in range(0, len(pos), _VOLUMEN_STAPEL):
            X = model.nodes[K_alle[a:a + _VOLUMEN_STAPEL]]              # (n, k, 3)
            v = np.zeros(len(X))
            for d, w in zip(dNT, W):
                v += w * np.abs(_det3(np.matmul(d, X)))                  # J = dN^T X
            V[pos[a:a + _VOLUMEN_STAPEL]] = v
    return V


def _bilinear_punkt(X4: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Punkt x(u, v) der bilinearen Flaeche ueber den Ecken X4 (Ringfolge)."""
    x0, x1, x2, x3 = X4
    return (x0 + u[..., None] * (x1 - x0) + v[..., None] * (x3 - x0)
            + (u * v)[..., None] * (x0 - x1 + x2 - x3))


def _bilinear_gitter(X4: np.ndarray, teilung: int = 16) -> tuple:
    """Die bilineare Flaeche als Dreiecke: teilung x teilung Teilvierecke,
    jedes als Faecher um seine Mitte (die liegt auf der Flaeche). Die Dreiecke
    laufen wie der Ring X4 - ihre Normale zeigt wie x_u x x_v.

    Der Faecher eines Teilvierecks weicht von der Flaeche um hoechstens
    |d| / (16 * teilung^2) ab (d = x0 - x1 + x2 - x3, die Verwindung): bei
    16 Teilen |d| / 4096, fuer eine um 1 m verwundene Flaeche 0,24 mm. Der
    grobe Faecher um die Mitte des ganzen Vierecks weicht um |d| / 16 ab -
    gemessen 31,25 mm am Wuerfel mit um 0,5 m angehobener Deckelecke, bei
    Seitenschwerpunkten des freien Netzes zwischen -0,87 und 5,21 mm.
    """
    n = int(teilung)
    t = np.linspace(0.0, 1.0, n + 1)
    tm = 0.5 * (t[:-1] + t[1:])
    u, v = np.meshgrid(t, t, indexing="ij")
    um, vm = np.meshgrid(tm, tm, indexing="ij")
    P = np.vstack([_bilinear_punkt(X4, u, v).reshape(-1, 3),
                   _bilinear_punkt(X4, um, vm).reshape(-1, 3)])
    i, j = (g.ravel() for g in np.meshgrid(np.arange(n), np.arange(n), indexing="ij"))
    e = [i * (n + 1) + j, (i + 1) * (n + 1) + j, (i + 1) * (n + 1) + j + 1, i * (n + 1) + j + 1]
    mitte = (n + 1) ** 2 + i * n + j
    T = np.concatenate([np.stack([mitte, e[q], e[(q + 1) % 4]], axis=1) for q in range(4)])
    return P, T


def _strecke_abstand(Q: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Abstand jedes Punktes zur Strecke a-b."""
    s = b - a
    L2 = float(s @ s)
    t = np.clip(((Q - a) @ s) / L2, 0.0, 1.0) if L2 > 0.0 else np.zeros(len(Q))
    return np.linalg.norm(Q - (a + t[:, None] * s), axis=1)


def _bilinear_abstand(Q: np.ndarray, X4: np.ndarray) -> np.ndarray:
    """Kuerzester Abstand jedes Punktes zur bilinearen Flaeche ueber X4.

    Fusspunkt (u, v) nach Newton, gestapelt ueber alle Punkte: Start am
    naechsten Punkt eines 5 x 5-Rasters, dann hoechstens zwoelf Schritte mit der vollen
    Hesse-Matrix (x_uu = x_vv = 0, x_uv = d), wo sie nicht positiv ist mit
    Gauss-Newton; geklemmt auf das Einheitsquadrat. Liegt der Fusspunkt auf
    dem Rand, gibt der Abstand zu den vier geraden Randkanten ihn genau.
    Ersetzt die Schleife ueber 16 x 16 x 4 = 1024 Dreiecke je Flaeche mit je
    einem Aufruf von punkt_dreieck_abstand: die brauchte an 64 000 hex8 mit
    sechs windschiefen Flaechen 4,5 bis 5,4 s (Gegenpruefung, 23.09.2026).
    """
    Q = np.atleast_2d(np.asarray(Q, float))
    if not len(Q):
        return np.zeros(0)
    X4 = np.asarray(X4, float)
    x0, x1, x2, x3 = X4
    a, b, d = x1 - x0, x3 - x0, x0 - x1 + x2 - x3
    t = np.linspace(0.0, 1.0, 5)
    ug, vg = (g.ravel() for g in np.meshgrid(t, t, indexing="ij"))
    G = _bilinear_punkt(X4, ug, vg)                              # (25, 3)
    u, v = np.empty(len(Q)), np.empty(len(Q))
    for s in range(0, len(Q), 20_000):
        D2 = ((Q[s:s + 20_000, None, :] - G[None]) ** 2).sum(axis=2)
        k = D2.argmin(axis=1)
        u[s:s + 20_000], v[s:s + 20_000] = ug[k], vg[k]
    for _ in range(12):
        r = _bilinear_punkt(X4, u, v) - Q
        Bu, Bv = a + v[:, None] * d, b + u[:, None] * d
        g1, g2 = np.einsum("ij,ij->i", Bu, r), np.einsum("ij,ij->i", Bv, r)
        h11, h22 = np.einsum("ij,ij->i", Bu, Bu), np.einsum("ij,ij->i", Bv, Bv)
        h12g = np.einsum("ij,ij->i", Bu, Bv)
        h12 = h12g + r @ d
        det = h11 * h22 - h12 * h12
        gn = ~(det > 1e-12 * h11 * h22)
        h12 = np.where(gn, h12g, h12)
        det = np.maximum(h11 * h22 - h12 * h12, 1e-300)
        u1 = np.clip(u - (h22 * g1 - h12 * g2) / det, 0.0, 1.0)
        v1 = np.clip(v - (h11 * g2 - h12 * g1) / det, 0.0, 1.0)
        schritt = max(float(np.abs(u1 - u).max()), float(np.abs(v1 - v).max()))
        u, v = u1, v1
        if schritt < 1e-12:
            break                           # alle Fusspunkte stehen
    dist = np.linalg.norm(_bilinear_punkt(X4, u, v) - Q, axis=1)
    for i in range(4):
        dist = np.minimum(dist, _strecke_abstand(Q, X4[i], X4[(i + 1) % 4]))
    return dist


def _sehnengrenze(X4: np.ndarray) -> float:
    """|d| / (4 sigma_min^2): mal D^2 der groesste Abstand einer Sehne der
    Weite D von der bilinearen Flaeche ueber X4.

    d = x0 - x1 + x2 - x3 ist die Verwindung (x_uv), sigma_min die kleinste
    Dehnung der Abbildung (u, v) -> x, der kleinste Singulaerwert von
    [x_u, x_v] auf einem 9 x 9-Raster. Eine flache Seite ueber die
    Parameterweiten du, dv weicht um hoechstens |d| du dv / 4 ab, und
    du, dv <= D / sigma_min.
    """
    X4 = np.asarray(X4, float)
    x0, x1, x2, x3 = X4
    a, b, d = x1 - x0, x3 - x0, x0 - x1 + x2 - x3
    t = np.linspace(0.0, 1.0, 9)
    u, v = (g.ravel() for g in np.meshgrid(t, t, indexing="ij"))
    Ju, Jv = a + v[:, None] * d, b + u[:, None] * d
    g11, g22, g12 = (Ju * Ju).sum(1), (Jv * Jv).sum(1), (Ju * Jv).sum(1)
    spur, det = g11 + g22, g11 * g22 - g12 * g12
    lam = 0.5 * (spur - np.sqrt(np.maximum(spur * spur - 4.0 * det, 0.0)))
    s2 = float(lam.min())
    if not s2 > 0.0:
        # Flaeche an einer Stelle ohne Dehnung: keine Sehne zulassen, lieber
        # eine Warnung zu viel als eine Luecke uebersehen
        return 0.0
    return float(np.linalg.norm(d)) / (4.0 * s2)


def _eben_abstand(Q: np.ndarray, eb) -> np.ndarray:
    """Abstand jedes Punktes zu einer ebenen Randflaeche (mit Oeffnungen)."""
    from . import mesher3d as M3
    c0, e1, e2, n0, ringe2 = eb
    d = Q - c0
    off = d @ n0
    p2 = np.stack([d @ e1, d @ e2], axis=1)
    drin = M3._in_polygon_2d(p2, ringe2)
    rand = np.full(len(Q), np.inf)
    for R in ringe2:
        for i in range(len(R)):
            a, b = R[i], R[(i + 1) % len(R)]
            s = b - a
            L2 = float(s @ s)
            t = np.clip(((p2 - a) @ s) / L2, 0.0, 1.0) if L2 > 0.0 else np.zeros(len(Q))
            rand = np.minimum(rand, np.linalg.norm(p2 - (a + t[:, None] * s), axis=1))
    return np.sqrt(off * off + np.where(drin, 0.0, rand) ** 2)


def _huelle_abstand(Q: np.ndarray, huelle: dict) -> tuple:
    """(Abstand zur Huelle, naechster Teil ist windschief) je Punkt."""
    Q = np.atleast_2d(np.asarray(Q, float))
    dist = np.full(len(Q), np.inf)
    schief = np.zeros(len(Q), bool)
    for eb in huelle["ebenen"]:
        dist = np.minimum(dist, _eben_abstand(Q, eb))
    for X4 in huelle["bilinear"]:
        db = _bilinear_abstand(Q, X4)
        schief = np.where(db < dist, True, schief)
        dist = np.minimum(dist, db)
    return dist, schief


def _polyederhuelle(model, koerper):
    """Die Huelle eines Koerpers aus seinen Randflaechen - nur dort, wo sie
    sich **ohne Naeherung** darstellen laesst, sonst None.

    Ohne Naeherung heisst: jede Randlinie ist gerade (Polylinie), und jede
    Randflaeche ist eben oder ein Viereck ohne Oeffnung. Ein nicht ebenes
    Viereck mit geraden Kanten ist die bilineare Flaeche. So bildet der
    Sechsflaechner es ab (seine Knoten liegen darauf). Der freie Vernetzer
    legt sein Netz nur **naeherungsweise** darauf: am Wuerfel mit um 0,5 m
    angehobener Deckelecke (h = 0,25) liegen Deckelknoten bis 7,55 mm neben
    der bilinearen Flaeche (dz * h^2 / 4 = 7,81 mm, die Sehne seines groben
    Dreiecksnetzes; Gegenpruefung, 23.09.2026). Diese Sehnenabweichung wird
    in :func:`_abnahme_volumenbilanz` ausdruecklich zugelassen. Krumme Linien
    (Bogen, Kreis, Spline) bleiben aussen vor: ihre Teilung haengt an der
    Netzweite, und die Sehnenabweichung laege in derselben Groesse wie das,
    was gesucht wird.

    Jeder Rand wird als Faecher um den Schwerpunkt seiner Ecken dargestellt.
    Das ist fuer eine ebene Flaeche exakt, und fuer das Viereck ist das
    Volumen des Faechers genau das der bilinearen Flaeche: beide sind
    1/3 * Schwerpunkt * Flaechenvektor. Ausgerichtet wird **je Flaeche**: die
    Oeffnungen gegen den Aussenrand, dann die Flaechen ueber ihre gemeinsamen
    Randkanten gegeneinander. mesher3d.ausrichten geht dafuer nicht - es
    richtet Dreieck fuer Dreieck ueber gemeinsame Kanten aus, und Aussen- und
    Oeffnungsfaecher derselben Flaeche teilen keine Kante: ein Prisma mit
    eckigem Loch zerfiel so in zwei Schalen (gemessen teile = 2), deren
    innere nicht gegenlaeufig zu richten war. Die Tupel in
    elements.solid.FLAECHEN (gemischt orientiert, Nachtrag C) werden gar
    nicht gebraucht.

    Rueckgabe dict: V (Huellvolumen aus den Faechern), PW und TW (die Huelle
    fuer die Windungszahl, nach aussen gerichtet: ebene Flaechen als ihre
    Faecher, windschiefe fein unterteilt, siehe :func:`_bilinear_gitter` - der
    grobe Faecher liegt dort bis |d| / 16 neben der Flaeche), ebenen
    [(Mitte, e1, e2, Normale, Ringe in der Ebene)], bilinear [Ecken (4, 3),
    nach aussen gerichtet]. Fuer Abstaende taugen die Faecher nicht: der
    Faecher des Aussenrands deckt auch die Oeffnungen.
    """
    from . import mesher3d as M3
    from .model import _rand_aus_linien
    namen = list(getattr(koerper, "flaechen", None) or [])
    alle_fl = getattr(model, "flaechen", None) or {}
    linien = getattr(model, "lines", None) or {}
    flaechen = [alle_fl.get(x) for x in namen]
    if len(flaechen) < 4 or any(f is None for f in flaechen):
        return None
    nn = int(model.nn)
    lokal: dict = {}
    punkte: list = []

    def knoten(n):
        j = lokal.get(n)
        if j is None:
            j = lokal[n] = len(punkte)
            punkte.append(np.asarray(model.nodes[n], float))
        return j

    def punkt(x):
        punkte.append(np.asarray(x, float))
        return len(punkte) - 1

    def newell(r):
        R = model.nodes[r]
        return np.cross(R, np.roll(R, -1, axis=0)).sum(axis=0)

    dreiecke, kanten_je_flaeche, ebenen, schief = [], [], [], []
    for fi, f in enumerate(flaechen):
        ringe = []
        for zug in [list(f.linien or [])] + [list(o) for o in (f.oeffnungen or [])]:
            for ln_name in zug:
                ln = linien.get(ln_name)
                if ln is None or (ln.typ or "polyline") != "polyline":
                    return None             # krumm: die Huelle waere genaehert
            r = [int(n) for n in _rand_aus_linien(model, zug)]
            if len(r) < 3 or any(not 0 <= n < nn for n in r):
                return None
            ringe.append(r)
        X = model.nodes[[n for r in ringe for n in r]]
        eben = M3.ist_eben(X)
        if not eben and (len(ringe) > 1 or len(ringe[0]) != 4):
            return None                     # gewoelbt und kein bilineares Viereck
        n_aussen = newell(ringe[0])
        if not np.linalg.norm(n_aussen) > 0.0:
            return None                     # Rand ohne Flaeche
        # Oeffnungen laufen gegen den Aussenrand - dann ist die Summe der
        # Faecher die Flaeche mit ausgesparten Loechern
        ringe = [ringe[0]] + [r[::-1] if newell(r) @ n_aussen > 0 else r for r in ringe[1:]]
        tri, kanten = [], []
        for r in ringe:
            c = punkt(model.nodes[r].mean(axis=0))
            ids = [knoten(n) for n in r]
            tri += [(c, ids[i], ids[(i + 1) % len(ids)]) for i in range(len(ids))]
            kanten += [(r[i], r[(i + 1) % len(r)]) for i in range(len(r))]
        dreiecke.append(tri)
        kanten_je_flaeche.append(kanten)
        if eben:
            c0, e1, e2, n0, _abw = M3.ausgleichsebene(X)
            ringe2 = [np.stack([(model.nodes[r] - c0) @ e1, (model.nodes[r] - c0) @ e2],
                               axis=1) for r in ringe]
            ebenen.append((c0, e1, e2, n0, ringe2))
        else:
            schief.append((fi, np.array(model.nodes[ringe[0]], float)))
    # Flaechen gegeneinander richten: eine gemeinsame Randkante durchlaufen
    # die beiden Nachbarn gegenlaeufig. Jede Kante muss in genau zwei Raendern
    # liegen, und alle Flaechen muessen zusammenhaengen - sonst ist die Huelle
    # nicht dicht oder zerfaellt, und das sagt „Hülle offen", nicht diese
    # Pruefung.
    an_kante: dict = {}
    for fi, kanten in enumerate(kanten_je_flaeche):
        for a, b in kanten:
            an_kante.setdefault((min(a, b), max(a, b)), []).append((fi, 1 if a < b else -1))
    if any(len(v) != 2 for v in an_kante.values()):
        return None
    nachbarn: list = [[] for _ in flaechen]
    for (fa, sa), (fb, sb) in an_kante.values():
        nachbarn[fa].append((fb, sa, sb))
        nachbarn[fb].append((fa, sb, sa))
    vz = [0] * len(flaechen)
    vz[0] = 1
    stapel = [0]
    while stapel:
        fa = stapel.pop()
        for fb, sa, sb in nachbarn[fa]:
            soll = -vz[fa] * sa * sb
            if vz[fb] == 0:
                vz[fb] = soll
                stapel.append(fb)
            elif vz[fb] != soll:
                return None                 # nicht orientierbar
    if 0 in vz:
        return None                         # zerfaellt in Teile
    T = np.array([(c, a, b) if s > 0 else (c, b, a)
                  for s, tri in zip(vz, dreiecke) for c, a, b in tri], dtype=int)
    von = np.array([fi for fi, tri in enumerate(dreiecke) for _ in tri], dtype=int)
    P = np.array(punkte, float)
    V = M3.huellvolumen(P, T)
    kehren = V < 0.0
    if kehren:
        T, V = T[:, [0, 2, 1]], -V          # nach aussen kehren
    if not V > 0.0:
        return None
    # Windschiefe Flaechen nach aussen gerichtet (Ring umkehren heisst u und
    # v tauschen, die Normale x_u x x_v kehrt sich um) und fein unterteilt
    bilinear, PW, TW = [], [P], [T[~np.isin(von, [fi for fi, _ in schief])]]
    basis = len(P)
    for fi, X4 in schief:
        if (vz[fi] > 0) == kehren:
            X4 = X4[[0, 3, 2, 1]]
        bilinear.append(X4)
        Pg, Tg = _bilinear_gitter(X4)
        PW.append(Pg)
        TW.append(Tg + basis)
        basis += len(Pg)
    return {"V": float(V), "P": P, "T": T, "PW": np.vstack(PW),
            "TW": np.concatenate(TW), "ebenen": ebenen, "bilinear": bilinear}


def _freie_seiten_ecken(model, els, gruppen: dict = None):
    """Die freien Seiten eines Elementsatzes: (Ecken (m, 4), Element je Seite).

    Frei heisst: die Seite kommt in genau einem Element vor. Dreiecksseiten
    stehen mit -1 aufgefuellt. Die sortierten Eckennummern werden in zwei
    int64 gepackt (je zwei Nummern, Faktor nn) und mit np.lexsort sortiert -
    np.unique(axis=0) brauchte dafuer an 64 000 hex8 allein 0,34 s.
    """
    from .elements import solid as sl
    els = np.asarray(els, int)
    teile, eigner = [], []
    for typ, (pos, K) in (gruppen or _knotenmatrizen(model, els)).items():
        seiten = sl.FLAECHEN_ECKEN.get(typ)
        if not seiten:
            continue
        for s in seiten:
            F = np.full((len(pos), 4), -1, dtype=np.int64)
            F[:, :len(s)] = K[:, list(s)]
            teile.append(F)
            eigner.append(els[pos])
    if not teile:
        return np.zeros((0, 4), np.int64), np.zeros(0, int)
    F = np.concatenate(teile)
    E = np.concatenate(eigner)
    S = np.sort(F, axis=1) + 1                      # -1 -> 0, Nummern ab 1
    n = np.int64(int(model.nn) + 2)
    hoch, tief = S[:, 0] * n + S[:, 1], S[:, 2] * n + S[:, 3]
    o = np.lexsort((tief, hoch))
    hs, ts = hoch[o], tief[o]
    neu = np.ones(len(o), bool)
    neu[1:] = (hs[1:] != hs[:-1]) | (ts[1:] != ts[:-1])
    gruppe = np.cumsum(neu) - 1
    frei = np.empty(len(o), bool)
    frei[o] = np.bincount(gruppe)[gruppe] == 1
    return F[frei], E[frei]


#: Wann eine Gruppe freier Seiten im Inneren ein **Riss ohne Weite** ist
#: (WARNUNG) und kein fehlender Nachbar (FEHLER). Zwei Bedingungen:
#:
#: * **geschlossen**: die Seiten umschliessen etwas. Die gerichteten Kanten
#:   der Seiten (umlaufend wie ihr Flaechenvektor, vom eigenen Element weg)
#:   heben sich paarweise auf; was bleibt, ist der Rand der Gruppe. Seine
#:   Schleifen duerfen zusammen hoechstens diesen Anteil der Seitenflaeche
#:   aufspannen. Ein Riss mit Knoten nur auf einem Ufer (T-Stoss) hat
#:   Randschleifen ohne Flaeche (drei Punkte auf einer Kante), ein Hohlraum
#:   gar keinen Rand. Gemessen an den 29 Gruppen, die die Modelle der Suiten
#:   test_mesher3d und test_sweep bilden (23.09.2026): Rand 0 bis 5,6 % der
#:   Seitenflaeche. Die Seiten an doppelten Knoten sind dagegen ein Ufer ohne
#:   Gegenueber (Rand 100 %), und die Gruppe um einen verdrehten Wuerfel in
#:   einer Reihe ist vorn und hinten offen: 2,00 m2 Rand bei 4,83 m2
#:   Seitenflaeche (41 %; verdrehter Boden 26 %, verdrehtes Eckelement 30 %).
#:   Die Summe der Flaechenvektoren taugt dafuer nicht - in der Reihe heben
#:   sich vorn und hinten auf (gemessen |Summe S| = 0, das scheinbare Volumen
#:   ebenso 0, und die Gruppe galt im ersten Entwurf als Riss).
ABNAHME_RISS_UFER = 0.10
#: * **ohne nennenswertes Volumen**: nicht mehr, als der freie Vernetzer
#:   selbst aussortiert - er wirft Tetraeder mit V <= FLACH * h^3 hinaus
#:   (mesher3d._innere und die Nachpruefung nach der Glaettung), und genau
#:   diese Luecken bleiben im Netz. Als h gilt hier die groesste
#:   Elementdiagonale im Koerper (die Diagonale ist nie kleiner als die
#:   laengste Kante), und je Seite der Gruppe ist ein solcher Tetraeder
#:   zugelassen - ein Haufen aus k Tetraedern hat mehr als k freie Seiten.
#:   Ein Formmass taugt dafuer nicht: die Hohlraeume des Vernetzers haben
#:   V / L^3 bis 0,015 (einzeln) und 0,031 (Haufen), die Zelle eines
#:   verdrehten Wuerfels 0,118 wie ein fehlender regelmaessiger Tetraeder -
#:   und neben ihren Nachbarn sind die Hohlraeume an der Bohrung 1 bis 10 %
#:   gross (die Nachbarn sind dort klein), die Zelle des verdrehten Wuerfels
#:   7 %. Gegen FLACH * h^3 liegen sie dagegen weit auseinander: die 29
#:   Gruppen der Suiten mindestens um den Faktor 8,3 unter dieser Grenze,
#:   die fehlende Zelle des verdrehten Wuerfels bei einem Drittel seines
#:   Volumens, dem Hunderttausendfachen von FLACH * h^3.


def _randflaeche(F, Xf, S) -> float:
    """Flaeche, die der Rand einer Gruppe von Seiten aufspannt.

    Jede Seite laeuft so um, dass ihre Normale in Richtung S zeigt. Ihre
    gerichteten Kanten werden gezaehlt (a -> b plus, b -> a minus); was sich
    nicht aufhebt, ist der Rand. Er wird zu Schleifen verkettet, und je
    Schleife zaehlt der Betrag ihres Flaechenvektors 1/2 sum p_i x p_i+1 -
    einzeln, damit sich zwei gegenueberliegende Oeffnungen nicht aufheben.
    """
    zahl: dict = {}
    for i in range(len(F)):
        r = [j for j in range(4) if F[i][j] >= 0]
        P = Xf[i][r]
        n_ring = 0.5 * sum(np.cross(P[j], P[(j + 1) % len(r)]) for j in range(len(r)))
        kn = [int(F[i][j]) for j in r]
        if float(n_ring @ S[i]) < 0.0:
            kn, P = kn[::-1], P[::-1]
        for j in range(len(kn)):
            a, b = kn[j], kn[(j + 1) % len(kn)]
            zahl[(a, b)] = zahl.get((a, b), 0) + 1
            zahl[(b, a)] = zahl.get((b, a), 0) - 1
    lage: dict = {}
    for i in range(len(F)):
        for j in range(4):
            if F[i][j] >= 0:
                lage[int(F[i][j])] = Xf[i][j]
    weiter: dict = {}
    for (a, b), k in zahl.items():
        for _ in range(max(k, 0)):
            weiter.setdefault(a, []).append(b)
    flaeche = 0.0
    while weiter:
        start = next(iter(weiter))
        schleife, a = [start], start
        while True:
            b = weiter[a].pop()
            if not weiter[a]:
                del weiter[a]
            if b == start or b not in weiter:
                break
            schleife.append(b)
            a = b
        P = np.array([lage[k] for k in schleife])
        flaeche += 0.5 * float(np.linalg.norm(np.cross(P, np.roll(P, -1, axis=0)).sum(axis=0)))
    return flaeche


def _flache_hohlraeume(F, Xf, S, h_max: float) -> tuple:
    """Welche dieser Seiten im Inneren bilden Risse ohne Weite?
    -> (Maske, Volumen dieser Hohlraeume zusammen).

    F (m, 4) Eckknoten (-1 bei Dreiecken), Xf (m, 4, 3) ihre Lage, S (m, 3)
    Flaechenvektor vom eigenen Element weg, h_max die groesste
    Elementdiagonale im Koerper.

    Die Seiten werden ueber gemeinsame Kanten zu Gruppen verbunden. Eine
    Gruppe ist ein Riss ohne Weite, wenn sie geschlossen ist
    (:data:`ABNAHME_RISS_UFER`, :func:`_randflaeche`) und hoechstens so viel
    Volumen einschliesst, wie der freie Vernetzer je Seite aussortiert
    (FLACH * h_max^3). Das Volumen folgt aus dem Gaussschen Satz,
    sum 1/3 * (q - c) * S um den Schwerpunkt c der Gruppe.

    Dazu gehoeren: ein Riss zwischen zwei verschieden in Dreiecke geteilten
    Haelften einer ebenen Flaeche (Volumen 0), ein Riss mit Knoten nur auf
    einer Seite (offen, Volumen 0 - am Modell test_nachbar_mit_verschiedener_
    teilung 8 Seiten, 1e-19 m^3), die Luecke eines aussortierten flachen
    Tetraeders (geschlossen, 4 Seiten). Nicht dazu: doppelte Knoten (je ein
    Ufer), eine fehlende Zelle, ein verdrehtes Element.

    Bis zum 23.09.2026 stand hier ein Ebenheitstest mit 1 % des
    Seitendurchmessers. Die Luecken des Vernetzers sind aber 1,7 bis 11 %
    dick (Platte mit Bohrung, 34 600 und 12 925 tet4; Keile am feinen Rand,
    2701 tet4) und wurden als FEHLER „Seiten im Inneren" gemeldet.
    """
    from .mesher3d import FLACH
    m = len(F)
    riss = np.zeros(m, bool)
    if not m:
        return riss, 0.0
    an_kante: dict = {}
    for i in range(m):
        ecken = [int(k) for k in F[i] if k >= 0]
        for a, b in zip(ecken, ecken[1:] + ecken[:1]):
            an_kante.setdefault((min(a, b), max(a, b)), []).append(i)
    wurzel = list(range(m))

    def finde(i):
        while wurzel[i] != i:
            wurzel[i] = wurzel[wurzel[i]]
            i = wurzel[i]
        return i

    for seiten in an_kante.values():
        for j in seiten[1:]:
            ra, rb = finde(seiten[0]), finde(j)
            if ra != rb:
                wurzel[rb] = ra
    gruppen: dict = {}
    for i in range(m):
        gruppen.setdefault(finde(i), []).append(i)
    maske = (F >= 0)[:, :, None]
    q = (Xf * maske).sum(axis=1) / maske.sum(axis=1)
    A = np.linalg.norm(S, axis=1)
    V_zus = 0.0
    for idx in gruppen.values():
        idx = np.asarray(idx)
        if _randflaeche(F[idx], Xf[idx], S[idx]) > ABNAHME_RISS_UFER * A[idx].sum():
            continue                        # offen: doppelte Knoten, Luecke, verdreht
        c = q[idx].mean(axis=0)
        V_g = abs(float(np.einsum("ij,ij->", q[idx] - c, S[idx]))) / 3.0
        if V_g <= len(idx) * FLACH * h_max ** 3:
            riss[idx] = True
            V_zus += V_g
    return riss, V_zus


def _abnahme_volumenbilanz(model, name, koerper, els) -> list:
    """Volumenbilanz und Seiten neben der Huelle - gegen die Randflaechen.

    Ein verdrehter Sechsflaechner (Deckelknoten um eins versetzt) ist ein
    gueltiger Koerper, nur ein anderer als der gemeinte: det J ueberall
    positiv, Formguete 0,707, Volumen 0,6667 statt 1,0 (Nachtrag A,
    22.09.2026). Keine Pruefung am Element findet ihn. Zwei Merkmale tun es,
    beide **gegen die Randflaechen** gemessen:

    1. **Volumenbilanz**: Summe der Elementvolumina (:func:`elementvolumina`)
       gegen das Volumen der Huelle (:func:`_polyederhuelle`). Nicht gegen
       das Randvolumen der freien Elementseiten: in bilinearer Darstellung
       ist das mit der Jacobi-Summe identisch (gemessen 1,6667 = 1,6667 am
       verdrehten Wuerfelpaar), und gefaechert haengt es an der Diagonale
       (1,3333 oder 2,0000) - beides sagt nichts. Zugelassen wird zu den
       0,5 % das Volumen, das der Netzrand durch seinen gemessenen Abstand zu
       windschiefen Randflaechen erklaert (Seitenflaeche mal groesster
       Abstand): auf einer windschiefen Flaeche liegt ein Tetraedernetz auf
       Sehnen. Am frei vernetzten Wuerfel mit um 1 m angehobener Deckelecke
       (h = 0,5) waren das 0,782 % mehr Volumen, bei richtigem Netz.
    2. **Freie Seiten neben der Huelle**: freie Elementseiten, deren
       Schwerpunkt auf keiner Randflaeche liegt. Wo Nachbarn nicht
       zusammenpassen, wird eine Seite frei, die im Inneren liegt - das
       findet auch **ein** verdrehtes Element unter tausenden, bei dem die
       Bilanz nur um ein Drittel seines Volumens verschoebe. An einer
       windschiefen Randflaeche gilt eine Seite als darauf, solange sie nicht
       weiter daneben liegt als eine Sehne der groessten Seite auf dieser
       Flaeche (:func:`_sehnengrenze`). Geht der Koerper knapp hinter der Seite weiter
       (Windungszahl der feinen Huelle, 1 % des Seitendurchmessers dahinter),
       ist es ein FEHLER („Seiten im Inneren") - ausser die Seiten bilden
       zusammen einen Riss ohne Weite: WARNUNG („Riss im Netz",
       :func:`_flache_hohlraeume`). Sonst weicht nur der Netzrand von der
       Randflaeche ab (eine abgeschnittene Ecke, eine Beule): WARNUNG
       („Netzrand neben der Hülle").

       Bis zum 23.09.2026 meldete das richtige freie Netze als FEHLER
       (Gegenpruefung): am Wuerfel mit angehobener Deckelecke 2 bis 53
       Aussenseiten auf Sehnen, an der Platte mit Bohrung und an den Keilen
       am feinen Rand die Luecken aussortierter flacher Tetraeder. Drei
       Ursachen: die Windungszahl rechnete gegen den groben Faecher der
       windschiefen Flaeche, der bis |d| / 16 danebenliegt (31,25 mm am
       Wuerfel mit dz = 0,5, die Seiten nur -0,87 bis 5,21 mm); an
       windschiefen Flaechen galt dieselbe 1-%-Grenze wie an ebenen; und der
       Risstest verlangte Ebenheit auf 1 %, die Luecken sind 1,7 bis 11 % dick.

    Geprueft wird nur, wo die Huelle ohne Naeherung feststeht (gerade Kanten,
    siehe :func:`_polyederhuelle`); fuer Koerper mit krummen Randlinien sagt
    diese Pruefung nichts - dort nimmt der freie Vernetzer sein Netz beim
    Vernetzen selbst ab (Volumen gegen Huelle, Randtreue).
    """
    from . import mesher3d as M3
    from .spannungen import dezimal
    huelle = _polyederhuelle(model, koerper)
    if huelle is None:
        return []
    gruppen = _knotenmatrizen(model, els)
    V_el = elementvolumina(model, els, gruppen)
    if not len(V_el) or not np.isfinite(V_el).all():
        return []                           # nicht nur Volumenelemente
    aus = []
    V_netz, V_h = float(V_el.sum()), huelle["V"]
    abw = abs(V_netz - V_h) / V_h
    F, E = _freie_seiten_ecken(model, els, gruppen)
    m = len(F)
    maske = (F >= 0)[:, :, None]
    Xf = model.nodes[np.maximum(F, 0)]                         # (m, 4, 3)
    q = (Xf * maske).sum(axis=1) / np.maximum(maske.sum(axis=1), 1)
    Xb = np.where(maske, Xf, Xf[:, :1])
    D_f = np.linalg.norm(Xb.max(axis=1) - Xb.min(axis=1), axis=1)     # Seitendurchmesser
    tol = ABNAHME_HUELLABSTAND * D_f
    viereck = F[:, 3] >= 0
    # Flaechenvektor (Dreieck: (b-a) x (c-a) / 2, Viereck: Diagonalen)
    S = 0.5 * np.cross(Xf[:, 1] - Xf[:, 0], Xf[:, 2] - Xf[:, 0])
    S[viereck] = 0.5 * np.cross(Xf[viereck, 2] - Xf[viereck, 0],
                                Xf[viereck, 3] - Xf[viereck, 1])
    A = np.linalg.norm(S, axis=1)

    def stich(idx):
        """Stichpunkte je Seite fuer den groessten Abstand zur Flaeche: Ecken,
        Kantenmitten und Schwerpunkt (dort liegt die Sehnenabweichung)."""
        Xi = Xb[idx]
        Xn = np.roll(Xi, -1, axis=1)
        Xn[~viereck[idx], 2] = Xi[~viereck[idx], 0]
        return np.concatenate([Xi, 0.5 * (Xi + Xn), q[idx, None]], axis=1).reshape(-1, 3)

    auf = np.zeros(m, bool)
    abstand = np.zeros(m)                  # groesster Abstand zur Randflaeche
    schief_nr = np.full(m, -1)             # auf welcher windschiefen Flaeche
    for c0, e1, e2, n0, ringe2 in huelle["ebenen"]:
        rest = np.nonzero(~auf)[0]
        if not len(rest):
            break
        nah = rest[np.abs((q[rest] - c0) @ n0) <= tol[rest]]
        if not len(nah):
            continue
        d = q[nah] - c0
        drin = M3._in_polygon_2d(np.stack([d @ e1, d @ e2], axis=1), ringe2)
        auf[nah[drin]] = True
    if huelle["bilinear"]:
        # Groesse des eigenen Elements (Diagonale seiner Huellbox) je Seite -
        # sie bestimmt, wie weit ein Netz auf Sehnen neben der Flaeche liegt
        stelle = np.full(len(model.elements), -1)
        stelle[np.asarray(els, int)] = np.arange(len(els))
        D_el = np.zeros(len(els))
        for _typ, (pos, K) in gruppen.items():
            X = model.nodes[K]
            D_el[pos] = np.linalg.norm(X.max(axis=1) - X.min(axis=1), axis=1)
        D_e = D_el[stelle[E]]
    for nr, X4 in enumerate(huelle["bilinear"]):
        rest = np.nonzero(~auf)[0]
        if not len(rest):
            break
        # Wie weit darf eine Seite neben der windschiefen Flaeche liegen?
        # Ein Tetraedernetz liegt dort auf Sehnen, und der freie Vernetzer
        # setzt Knoten auf Sehnen seines groben Dreiecksnetzes (huelle_verfeinern
        # halbiert Huelldreiecke an der laengsten Kante, der neue Punkt liegt
        # auf dem groben Dreieck): gemessen bis 7,55 mm am Wuerfel mit um 0,5 m
        # angehobener Deckelecke (h = 0,25), so viel weicht die Mitte einer
        # Zellendiagonale ab, dz * h^2 / 4 = 7,81 mm. Allgemein weicht eine
        # Sehne ueber die Parameterweiten du, dv um hoechstens |d| du dv / 4
        # ab (d = x0 - x1 + x2 - x3), und du, dv <= D / sigma_min mit sigma_min,
        # der kleinsten Dehnung der Flaeche (:func:`_sehnengrenze`). Fuer D
        # taugt die einzelne Seite nicht: die Knoten liegen auf Sehnen des
        # **groben** Netzes der Flaeche. Am Wuerfel lagen Ecken 7,55 mm daneben
        # an Seiten, deren Element nur 0,163 m Diagonale hat - die Grenze aus
        # der eigenen Diagonale waere 4,8 mm gewesen (18 von 90 Seiten
        # darueber, bei dz = 1,0 30 von 202). D ist darum der groesste
        # Seitendurchmesser auf dieser Flaeche; welche Seiten darauf liegen,
        # sagt ein erster Durchgang ueber den Schwerpunkt mit der Diagonale
        # des eigenen Elements. Gemessen am Wuerfel (dz 0,3 / 0,5 / 1,0 / 1,0
        # bei h 0,25 / 0,25 / 0,25 / 0,5): Ecken bis 4,65 / 7,55 / 6,55 /
        # 27,0 mm gegen die Grenze 9,6 / 16,1 / 26,2 / 132,7 mm. Die
        # Elementdiagonale selbst waere zu grosszuegig: am abgebildeten
        # 4 x 4 x 4-Netz (dz = 0,5) 51,9 mm statt 21,6 mm, weil die Elemente
        # am angehobenen Eck hoch sind. Eine Luecke, ein verdrehtes Element
        # liegt um Elementgroesse daneben, das ist 4 sigma^2 / (|d| D) mal mehr
        # als diese Grenze. Kleinere Abweichungen des Netzrands meldet die
        # Abnahme an windschiefen Flaechen nicht.
        s_b = _sehnengrenze(X4)
        # Nur Seiten in der Huellbox der Flaeche - die uebrigen liegen weiter
        # als jede Grenze davon weg
        weit = tol[rest] + s_b * float(D_e[rest].max()) ** 2
        lo, hi = X4.min(axis=0), X4.max(axis=0)
        drin = ((q[rest] >= lo - weit[:, None]) & (q[rest] <= hi + weit[:, None])).all(1)
        rest = rest[drin]
        if not len(rest):
            continue
        d_q = _bilinear_abstand(q[rest], X4)
        erst = d_q <= tol[rest] + s_b * D_e[rest] ** 2
        if not erst.any():
            continue
        H = float(D_f[rest[erst]].max())
        grenze_b = tol[rest] + s_b * H * H
        rest, grenze_b = rest[d_q <= grenze_b], grenze_b[d_q <= grenze_b]
        # Die Grenze gilt fuer jeden Punkt des Netzrands, also auch fuer die
        # Ecken. Nur am Schwerpunkt gemessen, verschwand eine Beule: ein
        # Deckelknoten des abgebildeten 4 x 4 x 4-Netzes 50 mm aus dem
        # windschiefen Deckel (dz = 0,5) verschiebt die Schwerpunkte seiner
        # vier Seiten nur um 12,5 mm, die Grenze dort ist 21,6 mm.
        kn = F[rest]
        gueltig = kn >= 0
        uniq, inv = np.unique(kn[gueltig], return_inverse=True)
        d_ecke = np.zeros(kn.shape)
        d_ecke[gueltig] = _bilinear_abstand(model.nodes[uniq], X4)[inv]
        nah = rest[d_ecke.max(axis=1) <= grenze_b]
        auf[nah] = True
        schief_nr[nah] = nr
    neben = np.nonzero(~auf)[0]
    innen = np.zeros(m, bool)
    riss = np.zeros(m, bool)
    V_riss = 0.0
    if len(neben):
        # Auf welcher Seite geht der Koerper weiter? Die Aussenrichtung wird
        # am Element gemessen (weg von seinem Schwerpunkt, wie
        # Model._seitennormale) - die Tupel in FLAECHEN sind gemischt
        # orientiert (Nachtrag C).
        Xs = Xf[neben]
        a, b, c = Xs[:, 0], Xs[:, 1], Xs[:, 2]
        nvec = np.cross(b - a, c - a)
        vn = viereck[neben]
        nvec[vn] = np.cross(c[vn] - a[vn], Xs[vn, 3] - b[vn])
        ce = np.array([model.nodes[[int(x) for x in model.elements[int(e)].nodes]].mean(axis=0)
                       for e in E[neben]])
        vor = np.where(np.einsum("ij,ij->i", nvec, q[neben] - ce) < 0.0, -1.0, 1.0)
        nvec *= vor[:, None]
        S[neben] *= vor[:, None]
        nvec /= np.maximum(np.linalg.norm(nvec, axis=1), 1e-300)[:, None]
        # Ein Punkt knapp hinter der Seite, auf der dem eigenen Element
        # abgewandten Seite, und die Windungszahl der **feinen** Huelle dort
        # (der grobe Faecher einer windschiefen Flaeche liegt bis |d| / 16
        # daneben, siehe _bilinear_gitter)
        probe = q[neben] + tol[neben][:, None] * nvec
        drin = M3.windungszahl(probe, huelle["PW"], huelle["TW"]) > 0.5
        innen[neben[drin]] = True
        # Im Inneren: umschliessen die Seiten einen Hohlraum ohne nennenswertes
        # Volumen, ist es ein Riss ohne Weite (so bleiben flache Tetraeder
        # zurueck, die der freie Vernetzer aussortiert), sonst fehlt ein
        # Nachbar: verdrehtes Element, Luecke, doppelte Knoten.
        ii = neben[drin]
        if len(ii):
            h_max = 0.0
            for _typ, (pos, K) in gruppen.items():
                X = model.nodes[K]
                h_max = max(h_max, float(np.linalg.norm(X.max(axis=1) - X.min(axis=1),
                                                        axis=1).max()))
            r, V_riss = _flache_hohlraeume(F[ii], Xf[ii], S[ii], h_max)
            riss[ii[r]] = True
        rand = neben[~drin]
        if len(rand):
            d_r, schief_r = _huelle_abstand(stich(rand), huelle)
            abstand[rand] = d_r.reshape(len(rand), -1).max(1)
            schief_nr[rand[schief_r.reshape(len(rand), -1).any(1)]] = len(huelle["bilinear"])
    # Volumen, das der Netzrand an windschiefen Flaechen erklaert: hoechstens
    # Seitenflaeche mal groesster Abstand (eine obere Schranke). Gebraucht nur,
    # wenn die Bilanz ueber 0,5 % liegt - an 216 000 hex8 mit sechs
    # windschiefen Flaechen kosteten die neun Stichpunkte je Seite sonst bei
    # jeder Abnahme den groessten Teil der Zeit.
    V_sehne = 0.0
    if abw > ABNAHME_VOLUMENBILANZ:
        for nr, X4 in enumerate(huelle["bilinear"]):
            idx = np.nonzero((schief_nr == nr) & ~innen)[0]
            if len(idx):
                abstand[idx] = _bilinear_abstand(stich(idx), X4).reshape(len(idx), -1).max(1)
        idx = np.nonzero((schief_nr >= 0) & ~innen)[0]
        V_sehne = float((A[idx] * abstand[idx]).sum())
    grenze = ABNAHME_VOLUMENBILANZ + V_sehne / V_h
    if abw > grenze:
        sehnen_text = ("" if V_sehne <= 0.0 else
                       f"; davon zugelassen {dezimal(V_sehne * 1e6)} cm³, die der Netzrand "
                       "auf den windschiefen Randflächen erklären kann")
        aus.append(Befund(
            pruefung="Volumenbilanz", objekt=str(name), wert=float(abw),
            grenze=float(grenze),
            text=f"Volumen {name}: die Elemente haben zusammen {dezimal(V_netz * 1e6)} cm³, "
                 f"die Randflächen schließen {dezimal(V_h * 1e6)} cm³ ein (Abweichung "
                 f"{dezimal(abw * 100)} %, Grenze "
                 f"{dezimal(grenze * 100, None if V_sehne > 0.0 else 1)} %{sehnen_text}) "
                 "- gerechnet würde ein anderer Körper als der gezeichnete. Ursache ist "
                 "ein verdrehtes Element (Deckel um eine Ecke versetzt) oder ein Netz, "
                 "das den Körper nicht füllt. Den Körper neu vernetzen (Netz → Vernetzen)."))
    if not len(neben):
        return aus

    def beispiele(idx):
        el, zahl = np.unique(E[idx], return_counts=True)
        reihe = np.argsort(-zahl, kind="stable")
        text = ", ".join(f"Element {int(el[j])} mit {int(zahl[j])} "
                         f"Seite{'n' if zahl[j] > 1 else ''}" for j in reihe[:3])
        return int(el[reihe[0]]), text + (" …" if len(reihe) > 3 else "")

    echt_idx = np.nonzero(innen & ~riss)[0]
    riss_idx = np.nonzero(riss)[0]
    rand_idx = np.nonzero(~auf & ~innen)[0]
    if len(echt_idx):
        schlimm, bsp = beispiele(echt_idx)
        aus.append(Befund(
            pruefung="Seiten im Inneren", objekt=str(name), element=schlimm,
            knoten=[int(x) for x in model.elements[schlimm].nodes],
            wert=float(len(echt_idx)), grenze=0.0,
            text=f"Volumen {name}: {len(echt_idx)} von {m} freien Elementseiten "
                 f"liegen im Inneren des Körpers statt auf einer Randfläche (z. B. {bsp}) "
                 "- der Körper geht dort weiter, aber kein Nachbarelement schließt an. "
                 "Über diese Seiten gehen keine Kräfte. Ursache ist ein verdrehtes "
                 "Element (Deckel um eine Ecke versetzt), doppelte Knoten oder eine "
                 "Lücke im Netz. Den Körper neu vernetzen (Netz → Vernetzen)."))
    if len(riss_idx):
        schlimm, bsp = beispiele(riss_idx)
        aus.append(Befund(
            pruefung="Riss im Netz", objekt=str(name), element=schlimm,
            knoten=[int(x) for x in model.elements[schlimm].nodes],
            wert=float(len(riss_idx)), grenze=0.0, stufe="WARNUNG",
            text=f"Volumen {name}: {len(riss_idx)} freie Elementseiten im Inneren "
                 f"umschließen Hohlräume ohne nennenswertes Volumen (zusammen "
                 f"{dezimal(V_riss * 1e9)} mm³; z. B. {bsp}) - Risse ohne Weite, wie sie "
                 "bleiben, wenn der Vernetzer flache Tetraeder aussortiert oder beiderseits "
                 "einer Fläche verschieden in Dreiecke teilt. Der Körper stimmt, die "
                 "Verschiebungen passen dort aber nur an Knoten und Kanten zusammen. Wo es "
                 "auf diese Stelle ankommt, neu vernetzen."))
    if len(rand_idx):
        schlimm, bsp = beispiele(rand_idx)
        aus.append(Befund(
            pruefung="Netzrand neben der Hülle", objekt=str(name), element=schlimm,
            knoten=[int(x) for x in model.elements[schlimm].nodes],
            wert=float(len(rand_idx)), grenze=0.0, stufe="WARNUNG",
            text=f"Volumen {name}: {len(rand_idx)} von {m} freien Elementseiten liegen "
                 f"neben den Randflächen, bis {dezimal(float(abstand[rand_idx].max()) * 1e3)} mm "
                 f"(z. B. {bsp}) - der Netzrand schneidet dort eine Ecke ab, wölbt sich "
                 "oder liegt auf Sehnen einer windschiefen Fläche; das Netz hat "
                 f"{dezimal(abw * 100)} % {'mehr' if V_netz >= V_h else 'weniger'} "
                 "Volumen als die Randflächen einschließen. Wo es auf diese Stelle "
                 "ankommt, dort feiner oder neu vernetzen."))
    return aus


def meldungen(model, d: dict = None) -> list:
    """Die Diagnose als Zeilen mit Vorsatz FEHLER/WARNUNG/Hinweis."""
    d = d or diagnose(model)
    z = []
    ent = d.get("entartete_elemente") or []
    if ent:
        beispiel = "; ".join(f"Element {i + 1} ({t}): {g}" for i, t, g in ent[:3])
        wort = ("1 entartetes Element" if len(ent) == 1
                else f"{len(ent)} entartete Elemente")
        # Kein FEHLER: ein Element ohne Ausdehnung hat auch keine Steifigkeit
        # und keine Masse. Es wegzulassen ist exakt, nicht genaehert - die
        # Rechnung darf daran nicht scheitern. Gesagt wird es trotzdem, denn
        # es zeigt eine Schwaeche im Netz oder in der Quelldatei.
        z.append(f"WARNUNG: {wort} ohne Ausdehnung - ohne Steifigkeit tragen sie "
                 f"nichts und werden bei der Rechnung übergangen ({beispiel}"
                 + (" …" if len(ent) > 3 else "") + "). Wo sie stören, das Netz "
                 "dort neu erzeugen (Netz → Vernetzen); bei importierten Netzen "
                 "die doppelten Knoten zusammenlegen")
    nf, nk = len(d["unvernetzte_flaechen"]), len(d["unvernetzte_koerper"])
    if nf or nk:
        z.append("WARNUNG: " + " und ".join(x for x in (f"{nf} Flächen" if nf else "", f"{nk} Volumen" if nk else "") if x)
                 + " ohne Netz - Geometrie ohne Elemente trägt nichts; vor dem Rechnen vernetzen "
                   "(Netz → Netz erzeugen)")
    if d["ohne_lager"]:
        n = len(d["ohne_lager"])
        kn = sorted(d["ohne_lager"][0])
        # Fehlt einem tragenden Bauteil das Netz, zerfaellt das Modell genau
        # dort - die losen Teile sind die **Folge**, nicht die Ursache. Dann
        # ist „Lager setzen" der falsche Rat: die Koerper ohne Netz gehoeren
        # genannt, denn erst wenn sie vernetzt sind, haengt der Rest wieder
        # zusammen. (Am Drehlagermodell: 12 Teile ohne Lager, weil V31, V34
        # und V108-V110 ohne Netz blieben - mit Netz keine einzige Meldung.)
        fehlt = [x for x, _g in (d.get("koerper_gescheitert") or [])]
        if fehlt:
            rat = ("zuerst die Volumen ohne Netz beheben ("
                   + ", ".join(fehlt[:6]) + (" …" if len(fehlt) > 6 else "")
                   + ") - ohne ihr Netz hängen die anderen Bauteile nicht "
                     "zusammen; die losen Teile sind die Folge, nicht die Ursache")
        else:
            rat = ("Lager setzen, die Teile verbinden oder die tragenden "
                   "Flächen/Volumen vernetzen")
        z.append(f"FEHLER: {n} Teiltragwerk{'e' if n > 1 else ''} ohne Lager (z. B. Knoten "
                 + ", ".join(f"K{k}" for k in kn[:6]) + (" …" if len(kn) > 6 else "")
                 + f"; das Netz zerfällt in {d['teile']} Teile) - so ist das Gleichungssystem singulär: "
                 + rat)
    if d["nur_kontakt"]:
        z.append(f"Hinweis: {len(d['nur_kontakt'])} Teiltragwerke sind nur durch Kontakt gehalten - "
                 "rechenbar, solange der Kontakt trägt (sonst hebt das Teil ab)")
    for name, grund in (d.get("koerper_gescheitert") or []):
        k = (getattr(model, "koerper", {}) or {}).get(name)
        wo = ""
        if k is not None:
            wo = f" ({getattr(k, 'material', '') or 'ohne Werkstoff'}, " \
                 f"{len(k.flaechen or [])} Randflächen)"
        z.append(f"FEHLER: Volumen {name}{wo} hat auch nach dem Vernetzen kein "
                 f"Element - {grund}. Ein Bauteil ohne Elemente trägt keine Last; "
                 "das Ergebnis wäre nicht ungenau, sondern falsch.")
        # Die offenen Kanten gleich mit: „9 Kanten offen" sagt nicht, wo sie
        # liegen. Mit Koordinaten und Randflaechen ist die Stelle im Modell zu
        # finden, ohne erst ins Protokoll zu steigen - dort steht der Rest.
        kanten = list(getattr(k, "netzkanten", None) or []) if k is not None else []
        z.extend(kanten)
    ov = d.get("koerper_ohne_volumen") or []
    if ov:
        z.append(f"Hinweis: {len(ov)} Volumen ohne Rauminhalt (alle Randknoten in einer "
                 "Ebene) - sie bekommen kein Netz und tragen nichts; in Dateien aus RFEM "
                 "sind das Hilfsobjekte (z. B. " + ", ".join(ov[:4])
                 + (" …" if len(ov) > 4 else "") + ")")
    if d["lose_knoten"]:
        z.append(f"Hinweis: {d['lose_knoten']} Knoten tragen kein Element (Rand nicht vernetzter Flächen)")
    return z


def _netzgrund_text(k) -> str:
    """Warum dieser Koerper kein Netz hat - im Klartext aus dem Vernetzer."""
    from .model import OHNE_NETZ
    kom = str(getattr(k, "kommentar", "") or "")
    if kom.startswith(OHNE_NETZ):
        rest = kom[len(OHNE_NETZ):].strip()
        if rest:
            return rest
    return {"abgebrochen": "das Vernetzen wurde abgebrochen",
            "gescheitert": "der Vernetzer ist gescheitert",
            "vernetzer_aus": "der freie Vernetzer ist abgeschaltet",
            }.get(str(getattr(k, "netzgrund", "") or ""), "Grund nicht vermerkt")


def singulaer_text(model, ex=None, system=None) -> str:
    """Erklärung zu einem singulären Gleichungssystem (statt „Factor is exactly singular“).

    Bleibt die Topologie stumm - kein loses Teiltragwerk, kein fehlendes Netz -,
    kommt ``system`` zum Zuge: die Matrixdiagnose (Stufe 2 in
    :mod:`statik3d.singular`) nennt das Bauteil, dessen Bewegung fast keine
    Energie kostet. Das ist der Fall, den die Topologie nicht sehen kann:
    weiche Mechanismen, Splitterelemente, Nullsteifigkeit.
    """
    d = diagnose(model)
    kopf = "Gleichungssystem singulär (kein statisches Gleichgewicht möglich)"
    if ex is not None:
        kopf += f" - {ex}"
    z = [m for m in meldungen(model, d) if not m.startswith("Hinweis")]
    if not z:
        # Stufe 1b: was sich bewegen kann, mit Bauteil und Richtung. Erst
        # danach die Matrix (Stufe 2) - sie faktorisiert ein zweites Mal.
        z += _bewegungsbefund(model)
    if not z and system is not None:
        z += _matrixbefund(model, system)
    if not z:
        z.append("Ursache nicht feststellbar: die Topologie ist geschlossen, es gibt "
                 "kein loses Teiltragwerk, keine freie Starrkörperbewegung und keinen "
                 "auffällig weichen Modus. Was hier noch bleibt, sieht keines der "
                 "Verfahren - Gelenke, Lagersteifigkeiten und Nullwerte bei Querschnitt, "
                 "Dicke und Werkstoff sind von Hand zu prüfen.")
    return kopf + "\n" + "\n".join(z)


def _halteguetebefund(guete: list, hoechstens: int = 6) -> list:
    """Die Haltegüte der gehaltenen Teile - die weichsten zuerst.

    ``wert = lambda_min / lambda_max`` der 6x6-Haltematrix: 1 heisst allseitig
    gleich fest, 1e-5 heisst in einer Richtung fast nichts. Der Rang sieht das
    nicht - er zaehlt nur, ob eine Richtung ueberhaupt angefasst wird. Ein
    Teil unter :data:`singular.HALTEGUETE_MIN` ist der Kandidat fuer eine
    Meldung aus dem Loeser, und es steht hier mit Namen, Richtung und Wert -
    ohne Loeserlauf.
    """
    from .singular import HALTEGUETE_MIN
    schwach = sorted((g for g in (guete or []) if 0.0 < g.wert < HALTEGUETE_MIN),
                     key=lambda g: g.wert)
    if not schwach:
        return []
    out = [f"WARNUNG: {g.text}" for g in schwach[:hoechstens]]
    if len(schwach) > hoechstens:
        out.append(f"… und {len(schwach) - hoechstens} weitere Teile unter der "
                   f"Haltegüte {HALTEGUETE_MIN:.0e}")
    return out


def _bewegungsbefund(model) -> list:
    """Stufe 1b: die freien Bewegungen als Meldung - Bauteil, Art, Richtung.

    Das Programm kennt diese Frage: :func:`singular.restfreiheiten` nennt je
    Teiltragwerk, ob es **gleitet** oder **abhebt**, und in welcher Richtung.
    Frueher wurde das hier nicht gefragt und stattdessen eine Liste von vier
    moeglichen Ursachen ausgegeben - eine Vermutung, wo eine Messung vorlag.
    """
    try:
        from .singular import restfreiheiten, wichtigste
        guete: list = []
        sing = restfreiheiten(model, guete=guete)
    except Exception:                     # noqa: BLE001 - eine Diagnose darf nie sperren
        return []
    if not sing:
        # Kein Teil ist frei - dann ist die Frage nicht mehr **ob**, sondern
        # **wie fest** gehalten wird. Genau dort steckt der Unterschied
        # zwischen zwei aeusserlich gleichen Bauteilen, von denen eines
        # gemeldet wird und das andere nicht.
        return _halteguetebefund(guete)
    try:
        zeigen = wichtigste(sing) or sing
    except Exception:                     # noqa: BLE001
        zeigen = sing
    out = []
    for s in zeigen[:6]:
        wo = ", ".join(s.koerper[:3]) + (" …" if len(s.koerper) > 3 else "")
        satz = f"FEHLER: {s.text or (wo + ' ist beweglich')}"
        if s.ursache:
            satz += f" - {s.ursache}"
        if abs(s.kraft) > 1e-6 or abs(s.moment) > 1e-6:
            satz += (f" (unausgeglichen: {s.kraft:.3g} N, {s.moment:.3g} Nm)")
        out.append(satz)
    if len(sing) > len(out):
        out.append(f"… und {len(sing) - len(out)} weitere freie Bewegungen")
    return out


def _matrixbefund(model, system) -> list:
    """Stufe 2: der weichste Modus der Steifigkeitsmatrix als Meldung."""
    try:
        from .singular import weichster_modus
        # Der Fortschrittsempfaenger des Systems, falls es einen hat: diese
        # Diagnose faktorisiert ein zweites Mal und darf nicht stumm laufen.
        melden = getattr(system, "_progress", None)
        moden = weichster_modus(getattr(system, "K", None), model,
                                getattr(system, "fi", None), melden=melden)
    except Exception:                     # noqa: BLE001 - eine Diagnose darf nie sperren
        return []
    return [f"FEHLER: {s.text} - {s.ursache}" for s in moden]
