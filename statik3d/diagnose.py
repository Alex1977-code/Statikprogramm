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
    jedes als Liste von Knotennummern."""
    nn = model.nn
    eltern = np.arange(nn)

    def finde(a):
        while eltern[a] != a:
            eltern[a] = eltern[eltern[a]]
            a = eltern[a]
        return a

    def vereine(a, b):
        ra, rb = finde(a), finde(b)
        if ra != rb:
            eltern[rb] = ra

    belegt = np.zeros(nn, bool)
    for e in model.elements:
        kn = [int(k) for k in e.nodes if 0 <= int(k) < nn]
        for k in kn:
            belegt[k] = True
        for k in kn[1:]:
            vereine(kn[0], k)
    for kp in getattr(model, "kopplungen", []) or []:
        a, b = int(getattr(kp, "node_a", -1)), int(getattr(kp, "node_b", -1))
        if 0 <= a < nn and 0 <= b < nn:
            vereine(a, b)
    gruppen: dict = {}
    for k in np.flatnonzero(belegt):
        gruppen.setdefault(int(finde(int(k))), []).append(int(k))
    return sorted(gruppen.values(), key=len, reverse=True)


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
ABNAHME_RANDTREUE = 0.99     #: Netzhaut gegen Huelle je Koerper


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


def abnahme(model, guete: list = None) -> list:
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

    Rueckgabe die Liste der Befunde; leer heisst: das Netz ist abgenommen.
    """
    aus: list = []
    aus += _abnahme_fugen(model)
    aus += _abnahme_huellen(model)
    aus += _abnahme_gemeinsame_flaechen(model)
    aus += _abnahme_kontaktpaare(model)
    aus += _abnahme_halteguete(model, guete)
    aus += _abnahme_netz(model)
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
        for name in sorted(genannt - gestellt):
            aus.append(Befund(
                pruefung="Gegenkörper ohne Facette", objekt=str(cp.name),
                wert=0.0, grenze=1.0,
                text=f"Kontaktbedingung {cp.name} nennt {name} als Gegenseite, "
                     "aber von diesem Bauteil ist keine einzige Facette in der "
                     "Fuge gelandet - die Fuge trägt dorthin nichts ab."))
    return aus


def _abnahme_halteguete(model, guete: list = None) -> list:
    """Teiltragwerke, die zwar gehalten sind, aber in einer Richtung fast nicht."""
    from .singular import HALTEGUETE_MIN, restfreiheiten
    if guete is None:
        guete = []
        try:
            restfreiheiten(model, guete=guete)
        except Exception:                 # noqa: BLE001 - eine Abnahme darf nie sperren
            return []
    aus = []
    for g in sorted((x for x in (guete or []) if 0.0 < x.wert < HALTEGUETE_MIN),
                    key=lambda x: x.wert):
        aus.append(Befund(
            pruefung="Haltegüte", objekt=", ".join(g.koerper[:3]),
            knoten=list(g.knoten[:1]), wert=g.wert, grenze=HALTEGUETE_MIN,
            text=g.text + f" (Grenze {HALTEGUETE_MIN:.0e})"))
    return aus


def _abnahme_netz(model) -> list:
    """Knoten ohne Element, Elementgueete und Randtreue je Koerper."""
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
    except Exception:                     # noqa: BLE001
        q = None
    for name, k in (getattr(model, "koerper", None) or {}).items():
        els = [int(x) for x in (k.elemente or []) if 0 <= int(x) < len(model.elements)]
        if els and q is not None:
            werte = [float(q[i]) for i in els if np.isfinite(q[i])]
            if werte and min(werte) < ABNAHME_ELEMENTGUETE:
                i = els[int(np.argmin([q[j] for j in els]))]
                aus.append(Befund(
                    pruefung="Elementgüte", objekt=str(name), element=i,
                    knoten=[int(x) for x in model.elements[i].nodes],
                    wert=min(werte), grenze=ABNAHME_ELEMENTGUETE,
                    text=f"Volumen {name}: Element {i} hat die Formgüte "
                         f"{min(werte):.3f} (Grenze {ABNAHME_ELEMENTGUETE:.2f}) - "
                         "ein Splitter, der die Steifigkeitsmatrix verdirbt."))
        rt = float(getattr(k, "randtreue", 0.0) or 0.0)
        if 0.0 < rt < ABNAHME_RANDTREUE:
            aus.append(Befund(
                pruefung="Randtreue", objekt=str(name), wert=rt,
                grenze=ABNAHME_RANDTREUE,
                text=f"Volumen {name}: das Netz deckt nur {rt * 100:.1f} % der "
                     f"Hülle (Grenze {ABNAHME_RANDTREUE * 100:.0f} %) - die "
                     "Geometrie ist im Netz nicht vollständig abgebildet."))
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
