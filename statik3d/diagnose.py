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
        z.append(f"FEHLER: {n} Teiltragwerk{'e' if n > 1 else ''} ohne Lager (z. B. Knoten "
                 + ", ".join(f"K{k}" for k in kn[:6]) + (" …" if len(kn) > 6 else "")
                 + f"; das Netz zerfällt in {d['teile']} Teile) - so ist das Gleichungssystem singulär: "
                   "Lager setzen, die Teile verbinden oder die tragenden Flächen/Volumen vernetzen")
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
