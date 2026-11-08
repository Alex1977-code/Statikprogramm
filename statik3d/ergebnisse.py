"""Ergebnisse neben der Modelldatei speichern und wieder laden.

Bis zum 12.09.2026 hielt die Modelldatei nur das Modell: nach dem Öffnen war
jede Rechnung weg - am Drehlager 18 Minuten je Lastfall. Jetzt schreibt das
Programm beim Speichern die Analyse (Lastfälle, Kombinationen, Umhüllende,
Nachweise) in eine zweite Datei ``<modell>.ergebnisse`` und liest sie beim
Öffnen wieder ein, wenn sie zum Modell passt (Kennung: Knoten- und
Elementzahl, Lastfallnamen, seit dem 24.09.2026 ein Hash der Elemente, seit
dem 06.10.2026 ein Hash der Knotenkoordinaten statt ihrer Summe, seit dem
07.10.2026 je Gruppe der Rechenangaben ein Hash - Lasten, Werkstoffe,
Querschnitte, Lager, Gelenke, Kontakt, Stellungen, Rechenart, Nachweise ...;
siehe rechenkennung).

Form: ein Pickle (Protokoll 5). Das Modell selbst steht nicht in der Datei -
jede Referenz auf das Modell (Results.model, Envelope.model, Nachweise) wird
beim Schreiben durch eine Marke ersetzt und beim Lesen auf das geladene
Modell gesetzt (persistent_id). Die grossen Woerterbuecher je Element
(solid_res, shell_res, beam_end, ...) werden als (Nummern, Matrix) gepackt:
1,8 Mio. einzelne Arrays wuerden das Pickle um Hunderte MB aufblaehen.
Rechenzwischenwerte (Results._cache) werden nicht geschrieben.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import pickle

import numpy as np

DATEIENDUNG = ".ergebnisse"
VERSION = 1
_MODELLMARKE = "STATIK3D_MODELL"
#: Woerterbuecher je Element, die als (Nummern, Matrix) gepackt werden
_JE_ELEMENT = ("beam_end", "beam_q", "shell_res", "solid_res", "solid_mittel", "feder_res",
               "grenzschicht_res", "bimomente")
#: Felder der Analyse, die {Name: Results} halten und gepackt werden
_ERGEBNISGRUPPEN = ("cases", "combinations", "alternativen")


def pfad_zu(modellpfad: str) -> str:
    """``modell.json`` -> ``modell.ergebnisse``."""
    return os.path.splitext(str(modellpfad))[0] + DATEIENDUNG


def elementhash(model) -> str:
    """Hash je Element (Typ, Knoten) in Reihenfolge, als Hex-Text.

    hashlib statt hash(): hash() von Zeichenketten wechselt mit jedem
    Programmstart (PYTHONHASHSEED), die Kennung muss aber beim naechsten
    Oeffnen dieselbe sein. Gemessen wird hier nur beim Speichern und Laden,
    nicht bei jedem Neuzeichnen (dafuer viewport._elementhash)."""
    h = hashlib.blake2b(digest_size=16)
    for e in model.elements:
        h.update(f"{e.typ}:{','.join(str(int(k)) for k in e.nodes)};".encode())
    return h.hexdigest()


def knotenhash(model) -> str:
    """Hash der Knotenmatrix (alle Koordinaten in ihrer Reihenfolge, Bit fuer
    Bit) als Hex-Text - seit dem 06.10.2026 Teil der Kennung (Fehlerliste F06).

    Bis dahin stand in der Kennung nur die Summe aller Koordinaten. Ein Knoten
    um (+0,3; 0; -0,3) m verschoben aenderte sie nicht, und eine
    Ergebnisdatei, neben der die Modelldatei ohne sie neu geschrieben worden
    war (Export als .json, Kommandozeile), galt beim Oeffnen als passend - mit
    den Verschiebungen des alten Stands. Verglichen wird genau: die
    Modelldatei haelt jede Koordinate als JSON-Zahl, und die kommt beim Lesen
    Bit fuer Bit wieder. ``+ 0.0`` macht aus -0.0 ein 0.0, beides ist
    derselbe Ort."""
    knoten = np.asarray(model.nodes, float).reshape(-1, 3) if model.nn else np.zeros((0, 3))
    knoten = np.ascontiguousarray(knoten + 0.0, dtype="<f8")
    return hashlib.blake2b(knoten.tobytes(), digest_size=16).hexdigest()


# ---------------------------------------------------------------------------
# Rechenangaben (07.10.2026, Nachtrag N38)
# ---------------------------------------------------------------------------
# Bis zum 07.10.2026 pruefte die Kennung nur Knoten, Elemente (Typ und Knoten)
# und die Namen der Lastfaelle. Eigengewicht verdoppelt, Modell als .json
# exportiert (die Ergebnisdatei bleibt daneben), Oeffnen: „passt“, gezeigt uz
# -15,2543 statt -15,6466 mm (Beleg p6_werkzeug/probe_last_export.py). Jetzt
# traegt sie je Gruppe der Rechenangaben einen Hash, gebildet aus der Form,
# in der das Modell gespeichert wird (Model.to_dict) - was nach Speichern und
# Laden wieder da ist, ergibt denselben Hash. Nicht darin stehen Anzeige,
# Bericht, Layer und die Textfelder der Objekte; die Oberflaeche behaelt bei
# genau diesen Feldern die Ergebnisse (MainWindow.BESCHRIFTUNGSFELDER), und
# die Pruefung tests.test_nachtrag_q1 haelt beides zusammen.

#: Gruppen der Rechenangaben und wie die Meldung beim Oeffnen sie nennt
GRUPPEN = {
    "lasten": "Lasten",
    "lastfaelle": "Lastfalleigenschaften",
    "kombinationen": "Kombinationen",
    "werkstoffe": "Werkstoffe",
    "querschnitte": "Querschnitte und Dicken",
    "elemente": "Elementeigenschaften",
    "geometrie": "Linien, Flächen und Volumen",
    "lager": "Lager",
    "gelenke": "Gelenke, Federn und Kopplungen",
    "kontakt": "Kontakt",
    "massen": "Massen und Dämpfer",
    "stellungen": "Stellungen und Situationen",
    "rechenart": "Rechenart und Einstellungen",
    "nachweise": "Nachweise",
    "sonstiges": "übrige Modellangaben",
}

#: Schluessel der Modelldatei (Model.to_dict) -> Gruppe. None: nur Anzeige,
#: Bericht oder Ordnung - oder anderswo erfasst (Knoten: knotenhash,
#: Elemente: elementhash und elementwertehash). Ein Schluessel, der hier
#: fehlt - ein kuenftiger -, zaehlt unter „sonstiges“: im Zweifel mit.
MODELLTEILE = {
    "format": None, "nodes": None, "elements": None,
    "name": None, "meta": None, "active_case": None, "bericht": None, "bericht_rahmen": None,
    "layer": None, "unterlagen": None, "bemassungen": None, "bemassung_einstellung": None,
    "werteskala": None, "einheiten": None, "importhinweise": None,
    # gespeicherte Ansichten (14.10.2026): wie man schaut, nicht was gerechnet wird
    "ansichten": None,
    # Vorgaben des Vernetzers - das Netz selbst steht in Knoten und Elementen
    "netz": None,
    "tetp_kantenmitten": "elemente",
    "materials": "werkstoffe",
    "sections": "querschnitte", "shells": "querschnitte",
    "lines": "geometrie", "flaechen": "geometrie", "koerper": "geometrie",
    "supports": "lager", "line_supports": "lager", "surface_supports": "lager",
    "hinges": "gelenke", "kopplungen": "gelenke", "starrkoerper": "gelenke", "federn": "gelenke",
    # Einleitung der Stabenden in Volumen (13.10.2026) - steht nur in der Datei, wenn gesetzt
    "stabeinleitung": "gelenke",
    "grenzschichten": "gelenke",
    # je Lastfall geteilt: die Lasten nach „lasten“, der Rest nach „lastfaelle“;
    # die Lastgenerierer stehen bei den Lasten, die sie erzeugen
    "load_cases": "lasten", "winde": "lasten", "wasserdruecke": "lasten",
    # Vorspannung je Anker (16.10.2026): zaehlt nicht fuer sich, sondern in den
    # Lasten jedes Lastfalls, der auf eine Definition verweist (rechenkennung) -
    # eine Definition ohne Verweis rechnet nirgends mit
    "vorspann_definitionen": None,
    "combinations": "kombinationen",
    "kontaktbedingungen": "kontakt", "contact_supports": "kontakt", "gap_elements": "kontakt",
    "contact_pairs": "kontakt", "getrennte_knoten": "kontakt", "kontakt_ausnahmen": "kontakt",
    "punktmassen": "massen", "daempfer": "massen",
    "situationen": "stellungen", "stellungen": "stellungen", "subsysteme": "stellungen",
    "design": "rechenart", "plastizitaet": "rechenart", "knotendilatation": "rechenart",
    "randspannung": "rechenart",
    "members": "nachweise", "joints": "nachweise", "verformungsgrenzen": "nachweise",
    "beulfelder": "nachweise", "volumenbereiche": "nachweise", "lasteinleitungen": "nachweise",
    "fatigue_loads": "nachweise", "schwingungen": "nachweise", "schweissnaehte": "nachweise",
}

#: Textfelder eines Objekts (und jeder Last eines Lastfalls): sie beschriften,
#: die Rechnung liest sie nicht. Den Kommentar einer Linienlast etwa
#: ueberschreibt das Verteilen selbst („n Elementlasten“).
TEXTFELDER = frozenset(("kommentar", "comment", "beschreibung", "description", "bezeichnung"))
#: weitere Felder ohne Einfluss auf die Rechnung, je Schluessel der Modelldatei:
#: die Nummer eines Lastfalls und einer Kombination (ihr Name ist der
#: Schluessel), die Groesse des Lagersymbols
ANZEIGEFELDER = {"load_cases": ("nummer",), "combinations": ("nummer",), "supports": ("groesse",),
                # Bolzen (06.11.2026): wird nur nachgewiesen, nicht gerechnet
                "koerper": ("bolzen",)}
#: Neue Felder mit ihrer Vorgabe zaehlen nicht: model.NEUE_FELDER (ein Mechanismus
#: fuer alle Pakete seit der Zusammenfuehrung am 14.10.2026; bis dahin standen hier
#: NEUE_VORGABEN, NEU_AUF_VORGABE und SPAETERE_FELDER).
#: Felder eines Lastfalls, die Lasten tragen - der Rest sind seine Eigenschaften
LASTFELDER = ("nodal_loads", "beam_loads", "face_loads", "geometrielasten", "linienlasten",
              "zwangsverformungen", "vorspannungen", "uebermasse", "temp_loads", "gravity",
              # Verweis auf die Vorspannung je Anker (16.10.2026, nur in der Datei, wenn gesetzt)
              "vorspannzustand")
#: einzelne Objekte (Einstellungen) statt Sammlungen
_EINZELOBJEKTE = ("design", "plastizitaet")
#: Sammlungen {Name: Objekt}. Sie zaehlen nur mit den Eintraegen, deren Name
#: im Modell vorkommt (_verwendete_namen): das Oeffnen im Fenster legt einem
#: Modell ohne Werkstoffe, Querschnitte oder Dicken Vorgaben an
#: (MainWindow.__init_defaults, etwa „t = 10 mm“). Ein Modell, das ohne sie
#: gerechnet wurde (aus dem Browser, einem Skript), fand seine Ergebnisdatei
#: danach nicht mehr passend (Gesamtlauf 07.10.2026, test_namen_lf_lk G1).
_NAMENSSAMMLUNGEN = ("materials", "sections", "shells")
#: die Listen der Lager und die Felder einer Stellung, die Lager beim Namen nennen
_LAGERLISTEN = ("supports", "line_supports", "surface_supports")
_LAGER_IN_STELLUNG = ("lager_aus", "lager_aktiv", "linienlager_aus", "flaechenlager_aus")
#: Fassung der Regeln oben. Wer sie aendert, zaehlt hoch: eine Datei mit
#: anderer Fassung wird dann mit Vorbehalt geladen statt als „geaendert“
#: abgewiesen.
RECHENKENNUNG_FASSUNG = 1
#: die Felder der Kennung je Teil, den eine aeltere Datei nicht kennt
_KENNUNGSTEILE = {"knoten": ("knoten",),
                  "rechnung": ("rechnung", "rechnung_fassung", "lastfaelle_einzeln")}


def lagernamen_zaehlen(model) -> bool:
    """Rechnet der Name eines Lagers mit? Nur, wenn eine Stellung Lager beim
    Namen nennt (lager_aus, lager_aktiv, linienlager_aus, flaechenlager_aus);
    sonst beschriftet er nur - die Oberflaeche behaelt dann beim Umbenennen
    die Ergebnisse (MainWindow._lagernamen_rechnen fragt hier)."""
    for st in getattr(model, "stellungen", None) or []:
        for attr in _LAGER_IN_STELLUNG:
            if (st.get(attr) if isinstance(st, dict) else getattr(st, attr, None)):
                return True
    return False


def _normal(x):
    """Zahlen und Folgen einheitlich, wie sie nach Speichern und Laden sind:
    7850 und 7850.0 sind derselbe Wert, -0.0 und 0.0 derselbe Ort, ein Tupel
    im Speicher ist nach dem JSON-Umlauf eine Liste (wie
    importers.anhaengen._normal)."""
    if x is None or isinstance(x, (bool, str)):
        return x
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x) + 0.0
    if isinstance(x, dict):
        return {str(k): _normal(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_normal(v) for v in x]
    return str(x)


def _text(x) -> str:
    return json.dumps(_normal(x), sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _hash(x) -> str:
    return hashlib.blake2b(_text(x).encode(), digest_size=16).hexdigest()


def elementwertehash(model) -> str:
    """Hash der Eigenschaften je Element ausser Typ und Knoten (die haelt
    elementhash): Werkstoff, Querschnitt, Drehung, Gruppe, Linie, nur Zug oder
    Druck, Woelben, Zustand, Seillaenge, Gelenke, Gelenkfedern,
    Exzentrizitaet. Ohne asdict je Element: jede verschiedene Zeile bekommt
    eine Nummer, gehasht werden die Zeilen und die Nummernfolge."""
    arten: dict = {}
    folge = []
    extra = []
    for i, e in enumerate(model.elements):
        k = (e.mat, e.sec, e.roll, e.group, e.line, e.nur, e.woelb, e.zustand, getattr(e, "laenge0", 0.0))
        try:
            n = arten.setdefault(k, len(arten))
        except TypeError:                  # ein Feld ist eine Liste: ueber den Text
            k = _text(list(k))
            n = arten.setdefault(k, len(arten))
        folge.append(n)
        if e.hinges or e.hinge_springs or e.exzentrizitaet:
            extra.append([i, e.hinges, e.hinge_springs, e.exzentrizitaet])
    h = hashlib.blake2b(digest_size=16)
    h.update(_text([list(k) if isinstance(k, tuple) else k for k in arten]).encode())
    h.update(np.asarray(folge, dtype="<i8").tobytes())
    h.update(_text(extra).encode())
    return h.hexdigest()


def _texte(x) -> set:
    """Alle Texte in einem Wert der Modelldatei (auch Schluessel)."""
    texte, stapel = set(), [x]
    while stapel:
        x = stapel.pop()
        if isinstance(x, str):
            texte.add(x)
        elif isinstance(x, dict):
            texte.update(k for k in x if isinstance(k, str))
            stapel.extend(v for v in x.values() if isinstance(v, (str, dict, list, tuple)))
        elif isinstance(x, (list, tuple)):
            stapel.extend(v for v in x if isinstance(v, (str, dict, list, tuple)))
    return texte


def _verwendete_namen(model, d: dict) -> set:
    """Jeder Text, der in der Modelldatei ``d`` (ohne Netz) und in den
    Elementen (Werkstoff, Querschnitt) steht - ein Werkstoff, Querschnitt oder
    eine Dicke zaehlt dabei nicht als Nennung ihrer selbst. Wer sie benutzt,
    nennt sie beim Namen; was hier fehlt, rechnet nirgends mit. Zufaellig
    gleiche Texte zaehlen mit - im Zweifel mit."""
    namen = {e.mat for e in model.elements} | {e.sec for e in model.elements}
    for schluessel, wert in d.items():
        if schluessel in _NAMENSSAMMLUNGEN and isinstance(wert, dict):
            for name, eintrag in wert.items():
                namen |= _texte(eintrag) - {name}
        else:
            if schluessel in ANZEIGEFELDER and isinstance(wert, list):
                # Anzeigefelder nennen keinen Werkstoff, der rechnet (Bolzen, 06.11.2026)
                wert = [{k: v for k, v in x.items() if k not in ANZEIGEFELDER[schluessel]}
                        if isinstance(x, dict) else x for x in wert]
            namen |= _texte(wert)
    return namen


def _bereinigt(schluessel: str, wert, lagernamen: bool, ausdruecklich=frozenset()):
    """Ein Schluessel der Modelldatei ohne seine Anzeigefelder (TEXTFELDER,
    ANZEIGEFELDER, die Namen der Lager, wenn keine Stellung sie nennt).
    ``ausdruecklich``: {(Schluessel, Feld)} der neuen Felder, die auch mit
    ihrer heutigen Vorgabe zaehlen (rechenkennung)."""
    weg = set(TEXTFELDER) | set(ANZEIGEFELDER.get(schluessel, ()))
    if schluessel in _LAGERLISTEN and not lagernamen:
        weg.add("name")
    from .model import ist_vorgabe

    def ist_vorgabe(s, k, v, _heute=ist_vorgabe):
        if (s, k) in ausdruecklich:
            return False
        return _heute(s, k, v)

    def objekt(x):
        if not isinstance(x, dict):
            return x
        # neue Felder mit ihrer Vorgabe zaehlen nicht (model.NEUE_FELDER)
        y = {k: v for k, v in x.items() if k not in weg and not ist_vorgabe(schluessel, k, v)}
        if schluessel == "load_cases":
            for f in LASTFELDER:
                if isinstance(y.get(f), list):
                    y[f] = [{k: v for k, v in l.items()
                             if k not in TEXTFELDER and not ist_vorgabe(f"load_cases.{f}", k, v)}
                            if isinstance(l, dict) else l for l in y[f]]
        return y
    if isinstance(wert, list):
        return [objekt(x) for x in wert]
    if isinstance(wert, dict) and schluessel in _NAMENSSAMMLUNGEN:
        return {k: objekt(v) for k, v in wert.items()}
    if isinstance(wert, dict) and schluessel in _EINZELOBJEKTE:
        return objekt(wert)
    return wert


def _vorgabe_einsetzen(d: dict, schluessel: str, feld: str) -> None:
    """In ``d`` (Model.to_dict) das neue Feld ``feld`` unter ``schluessel``
    mit seiner heutigen Vorgabe einsetzen, wo es fehlt - die Modelldatei
    laesst es mit der Vorgabe weg (model.NEUE_FELDER). Einzelobjekt, Sammlung
    mit Namen, Liste von Objekten oder Lasten eines Lastfalls
    („load_cases.<liste>“)."""
    from .model import NEUE_FELDER
    vg = NEUE_FELDER.get(schluessel, {})
    if feld not in vg:
        return
    import copy

    def setzen(x):
        if isinstance(x, dict) and feld not in x:
            x[feld] = copy.deepcopy(vg[feld])
    oben, _, liste = schluessel.partition(".")
    wert = d.get(oben)
    if liste:
        for lc in wert or []:
            for last in (lc.get(liste) or []) if isinstance(lc, dict) else []:
                setzen(last)
    elif isinstance(wert, list):
        for x in wert:
            setzen(x)
    elif isinstance(wert, dict) and oben in _NAMENSSAMMLUNGEN:
        for x in wert.values():
            setzen(x)
    elif isinstance(wert, dict):
        setzen(wert)


def rechenkennung(model, frueher: bool = False, ausdruecklich=None, d=None) -> tuple:
    """({Gruppe: Hash}, {Lastfall: [Hash Eigenschaften, Hash Lasten]}) - alles,
    was das Ergebnis bestimmt, ausser Knoten und Elementen (eigene Hashes).

    Gelesen wird die Form der Modelldatei (Model.to_dict ohne Netz): sie ist
    das, was nach Speichern und Laden wieder da ist; aus Objektlasten
    abgeleitete Elementlasten etwa stehen nicht darin, sie entstehen beim
    Verteilen neu. Sammlungen mit Namen zaehlen ohne ihre Reihenfolge, Listen
    (Lager, Kopplungen: ueber die Nummer genannt) mit ihr.

    ``ausdruecklich`` (16.10.2026): {(Schluessel, Feld)} - diese Felder
    zaehlen auch mit ihrer heutigen Vorgabe, so wie ein frueherer Stand sie
    schrieb, als ihre Vorgabe eine andere war (rechenverfahren, Wechsel mit
    ``vorher_einstellung``; reibungstangente: true vom 15.10.2026 mittags).
    Es kommt nur hinzu, nie faellt ein Wert weg: ein Wert, den der Anwender
    nach der Rechnung gesetzt hat, bleibt eine Aenderung des Modells.
    ``frueher``: alle solchen Felder (bis 15.10.2026 abends die einzige Form).

    ``d`` (R2-A2): die Modelldatei ohne Netz, die statt ``model.to_dict``
    zaehlt - der Stand mit den alten Namen vor der Umstellung beim Oeffnen
    (Model._dict_vor_umstellung); Netz und Elementwerte kommen weiter vom Modell.
    """
    import copy
    d = copy.deepcopy(d) if d is not None else model.to_dict(netz=False)
    if frueher and ausdruecklich is None:
        from .rechenverfahren import ausdruecklich_moeglich
        ausdruecklich = {(s, f) for s, f, _st in ausdruecklich_moeglich(None)}
    ausdruecklich = frozenset(ausdruecklich or ())
    for schluessel, feld in ausdruecklich:
        _vorgabe_einsetzen(d, schluessel, feld)
    namen = lagernamen_zaehlen(model)
    verwendet = _verwendete_namen(model, d)
    teile: dict = {g: [] for g in GRUPPEN}
    einzeln: dict = {}
    from .model import ist_vorgabe
    for schluessel, wert in d.items():
        gruppe = MODELLTEILE.get(schluessel, "sonstiges")
        if gruppe is None or ist_vorgabe("", schluessel, wert):
            continue
        if schluessel in _NAMENSSAMMLUNGEN and isinstance(wert, dict):
            wert = {k: v for k, v in wert.items() if k in verwendet}
        wert = _bereinigt(schluessel, wert, namen, ausdruecklich)
        if (isinstance(wert, list) and isinstance(getattr(model, schluessel, None), dict)
                and all(isinstance(x, dict) for x in wert)):
            wert = sorted(wert, key=lambda x: str(x.get("name", "")))
        if schluessel == "load_cases":
            for lc in wert:
                name = str(lc.get("name", ""))
                eig = _hash({k: v for k, v in lc.items() if k not in LASTFELDER})
                lasten_lc = {k: v for k, v in lc.items() if k in LASTFELDER}
                if lasten_lc.get("vorspannzustand"):
                    # die Definitionen sind die Lasten eines verweisenden Lastfalls
                    # (16.10.2026): aendert sich eine, ist sein Ergebnis alt. Alle,
                    # nicht nur die genannten: P₀ fuer ΔP_t kommt aus dem Spannen
                    # aller Definitionen (vorspannkraft.p0_zustand0)
                    lasten_lc["_vorspann_definitionen"] = _bereinigt(
                        "vorspann_definitionen", list(d.get("vorspann_definitionen") or []), namen,
                        ausdruecklich)
                last = _hash(lasten_lc)
                einzeln[name] = [eig, last]
                teile["lastfaelle"].append([name, eig])
                teile["lasten"].append([name, last])
            continue
        teile[gruppe].append([schluessel, wert])
    teile["elemente"].append(["je Element", elementwertehash(model)])
    return {g: _hash(v) for g, v in teile.items()}, einzeln


def vorbehalt_text(fehlt) -> str:
    """Der Vorbehalt einer Datei, deren Kennung Teile nicht kennt: „knoten“
    (vor dem 06.10.2026, F06), „rechnung“ (vor dem 07.10.2026, N38)."""
    fehlt = set(fehlt or ())
    if not fehlt:
        return ""
    if "knoten" in fehlt and "rechnung" in fehlt:
        was = ("prüft die Knotenlage nur als Summe der Koordinaten, Lasten, Werkstoffe, Querschnitte, "
               "Lager und die übrigen Rechenangaben gar nicht")
    elif "knoten" in fehlt:
        was = "prüft die Knotenlage nur als Summe der Koordinaten"
    else:
        was = "prüft Lasten, Werkstoffe, Querschnitte, Lager und die übrigen Rechenangaben nicht"
    datum = "06.10.2026" if "knoten" in fehlt else "07.10.2026"
    return (f"sie stammt von vor dem {datum} und {was} – wurde das Modell ohne sie geändert "
            "(Export als .json, Kommandozeile), bitte neu rechnen")


#: Vorbehalt einer Ergebnisdatei von vor dem 06.10.2026 (passt, F06) - nur
#: die Knotenlage; vorbehalt_text nennt seit N38 auch die Rechenangaben
ALTE_KENNUNG = vorbehalt_text(["knoten"])


def kennung(model, d=None) -> dict:
    """Woran die Ergebnisdatei erkennt, dass sie zu diesem Modell gehoert.

    „elemente“ (24.09.2026): Element 0 loeschen und einen Stab [0,5] anlegen
    aendert weder Knoten- und Elementzahl noch die Koordinatensumme - die
    alte Datei passte dann zum neuen Modell, die Werte standen an anderen
    Elementen (Gegenpruefung von 97be9ff). Die Dateiversion bleibt 1: alte
    Dateien ohne den Eintrag werden weiter gelesen (passt prueft ihn nur, wo
    er steht), und ein aelteres Programm uebergeht den zusaetzlichen.

    „knoten“ (06.10.2026, F06): der Hash der Knotenmatrix (knotenhash) statt
    der Summe der Koordinaten. „koordinaten“ bleibt fuer aeltere Programme
    in der Datei, die nur ihn kennen.

    „rechnung“ (07.10.2026, N38): je Gruppe der Rechenangaben ein Hash
    (rechenkennung), „lastfaelle_einzeln“ dieselben je Lastfall - damit die
    Meldung sagen kann, welcher Lastfall anders ist.

    „modellfassung“ (R2-A2, 06.10.2026): die Fassung der Modelldatei, zu der
    die Namen der Ergebnisse gehoeren. Eine Datei ohne den Eintrag stammt von
    vor der Umstellung auf LF/LK/EK und traegt die alten Namen. Gelesen wird
    sie vor der Umstellung, am Modell mit den alten Namen; danach stellt das
    Oeffnen beides um (Model.namen_umstellen, _namen_umschluesseln)."""
    from .model import FORMAT_VERSION
    knoten = np.asarray(model.nodes, float).reshape(-1, 3) if model.nn else np.zeros((0, 3))
    gruppen, einzeln = rechenkennung(model, d=d)
    lastfaelle = (sorted(str(lc.get("name", "")) for lc in (d.get("load_cases") or []))
                  if d is not None else sorted(model.load_cases))
    return {"version": VERSION, "name": str(model.name), "nn": int(model.nn),
            "ne": int(len(model.elements)),
            "koordinaten": float(np.round(knoten.sum(), 6)) if knoten.size else 0.0,
            "knoten": knotenhash(model),
            "lastfaelle": lastfaelle,
            "elemente": elementhash(model),
            "rechnung": gruppen, "rechnung_fassung": RECHENKENNUNG_FASSUNG,
            "lastfaelle_einzeln": einzeln, "modellfassung": FORMAT_VERSION}


def _gruppentext(gruppe: str, k: dict, jetzt: dict) -> str:
    """„Lasten (LF1, LF3)“ - bei Lasten und Lastfalleigenschaften mit den
    Lastfaellen, die anders sind."""
    text = GRUPPEN.get(gruppe, gruppe)
    stelle = {"lastfaelle": 0, "lasten": 1}.get(gruppe)
    alt = k.get("lastfaelle_einzeln")
    if stelle is None or not isinstance(alt, dict):
        return text
    namen = [n for n, h in jetzt["lastfaelle_einzeln"].items()
             if not isinstance(alt.get(n), (list, tuple)) or len(alt[n]) < 2 or alt[n][stelle] != h[stelle]]
    if not namen:
        return text
    return f"{text} ({', '.join(namen[:5])}{' …' if len(namen) > 5 else ''})"


def pruefen(k: dict, model) -> tuple:
    """(passt, Grund, fehlt): wie passt, dazu die Teile, die die Kennung
    nicht kennt (_KENNUNGSTEILE) - lesen merkt sie sich, damit Speichern
    ohne neue Rechnung die alte Form behaelt."""
    return _pruefen(k, model)[:3]


def _ausdruecklich_passend(rk: dict, model, stand, d=None) -> list:
    """Die Einstellungen [(Schluessel, Feld, Stand)], mit denen die Kennung
    ``rk`` passt, wenn sie mit ihrer heutigen Vorgabe ausdruecklich zaehlen -
    so schrieb ein Stand vor dem Wechsel ihrer Vorgabe einen damals gesetzten
    Wert (rechenverfahren.Wechsel.vorher_einstellung). Nur Felder, die heute
    ihre Vorgabe tragen; jede Teilmenge wird versucht (es sind wenige).
    None, wenn keine passt. ``stand``: der Verfahrensstand der Datei, soweit
    bekannt (None: unbekannt)."""
    import itertools
    from .model import ist_vorgabe
    from .rechenverfahren import ausdruecklich_moeglich
    felder = []
    for s, f, st in ausdruecklich_moeglich(stand):
        oben, _, liste = s.partition(".")
        if liste:
            werte = [l.get(f) if isinstance(l, dict) else getattr(l, f, None)
                     for lc in (getattr(model, "load_cases", None) or {}).values()
                     for l in (getattr(lc, liste, None) or [])]
        else:
            obj = getattr(model, oben, None)
            if isinstance(obj, dict):
                werte = [getattr(x, f, None) for x in obj.values()]
            elif isinstance(obj, (list, tuple)):
                werte = [getattr(x, f, None) for x in obj]
            else:
                werte = [getattr(obj, f, None)]
        if any(ist_vorgabe(s, f, w) for w in werte):
            felder.append((s, f, st))
    for n in range(1, len(felder) + 1):
        for teil in itertools.combinations(felder, n):
            alt = rechenkennung(model, ausdruecklich={(s, f) for s, f, _st in teil}, d=d)[0]
            if all(rk.get(g) == alt[g] for g in GRUPPEN):
                return list(teil)
    return None


def _pruefen(k: dict, model, stand=None, d=None) -> tuple:
    """(passt, Grund, fehlt, ausdruecklich) - ``ausdruecklich``: die
    Einstellungen [(Schluessel, Feld, Stand)], die in der Kennung der Datei
    mit ihrem heutigen Vorgabewert ausdruecklich stehen (geschrieben vor dem
    Wechsel ihrer Vorgabe, rechenverfahren); ``stand``: Verfahrensstand der
    Datei, soweit bekannt. ``d``: der Stand mit den alten Namen vor der
    Umstellung beim Oeffnen (R2-A2, siehe rechenkennung)."""
    jetzt = kennung(model, d)
    if not isinstance(k, dict):
        return False, "keine Kennung", []
    if int(k.get("version", 0)) != VERSION:
        return False, f"Dateiversion {k.get('version')} statt {VERSION}", []
    for feld, text in (("nn", "Knotenzahl"), ("ne", "Elementzahl")):
        if k.get(feld) != jetzt[feld]:
            return False, f"{text} {k.get(feld)} statt {jetzt[feld]}", []
    fehlt = []
    if "knoten" in k:
        if k["knoten"] != jetzt["knoten"]:
            return False, "die Knotenkoordinaten sind andere", []
    else:
        if abs(float(k.get("koordinaten", 0.0)) - jetzt["koordinaten"]) > 1e-6 * max(1.0, abs(jetzt["koordinaten"])):
            return False, "die Knotenkoordinaten sind andere", []
        fehlt.append("knoten")
    if list(k.get("lastfaelle", [])) != jetzt["lastfaelle"]:
        return False, "die Lastfälle sind andere", []
    if "elemente" in k and k["elemente"] != jetzt["elemente"]:
        return False, "die Elemente sind andere (Typ oder Knoten)", []
    rk = k.get("rechnung")
    if isinstance(rk, dict) and k.get("rechnung_fassung") == RECHENKENNUNG_FASSUNG:
        anders = [g for g in GRUPPEN if rk.get(g) != jetzt["rechnung"][g]]
        if anders:
            # Modell oder Verfahren? Ein Wert, der damals ausdruecklich gesetzt
            # war und heute die Vorgabe ist (reibungstangente: true vom 15.10.2026
            # mittags), steht nur in der alten Kennung - dasselbe Modell, ein
            # Wechsel der Vorgabe (rechenverfahren). Alles andere hat der
            # Anwender geaendert: ungueltig. Bis zum 16.10.2026 fiel dabei auch
            # ein Wert weg, der der frueheren Vorgabe glich - dann galt eine
            # Datei als passend, nachdem der Anwender auf das bisherige
            # Reibverfahren umgestellt hatte.
            gesetzt = _ausdruecklich_passend(rk, model, stand, d)
            if gesetzt is not None:
                return True, vorbehalt_text(fehlt), fehlt, gesetzt
            return False, "seit der Rechnung geändert: " + ", ".join(_gruppentext(g, k, jetzt) for g in anders), [], []
    else:
        fehlt.append("rechnung")
    return True, vorbehalt_text(fehlt), fehlt, []


def passt(k: dict, model) -> tuple:
    """(True, "") wenn die Kennung zum Modell passt, sonst (False, Grund).

    Eine Kennung ohne „knoten“ (Ergebnisdatei von vor dem 06.10.2026) laesst
    sich nur ueber die Summe der Koordinaten pruefen, eine ohne „rechnung“
    (vor dem 07.10.2026) gar nicht an Lasten, Werkstoffen, Lagern. Sie wird
    nicht still als passend angenommen (Fehlerliste F06, Nachtrag N38):
    Rueckgabe (True, Vorbehalt - vorbehalt_text), und wer liest, sagt es dem
    Anwender (lesen legt den Vorbehalt in die Analyse, die Oberflaeche zeigt
    ihn als Hinweis). Passt sie nicht, nennt der Grund, was anders ist - bei
    den Rechenangaben die Gruppen („seit der Rechnung geändert: Lasten (LF1),
    Werkstoffe“)."""
    ok, grund, _fehlt = pruefen(k, model)
    return ok, grund


class _Schreiber(pickle.Pickler):
    """Ersetzt das Modell durch eine Marke - es steht in der Modelldatei."""

    def __init__(self, datei, model):
        super().__init__(datei, protocol=5)
        self._model = model

    def persistent_id(self, obj):
        if obj is self._model:
            return _MODELLMARKE
        return None


class _Leser(pickle.Unpickler):
    def __init__(self, datei, model):
        super().__init__(datei)
        self._model = model

    def persistent_load(self, pid):
        if pid == _MODELLMARKE:
            return self._model
        raise pickle.UnpicklingError(f"unbekannte Marke {pid!r}")


def _packen_results(res) -> dict:
    """Ein Results-Objekt als flaches Woerterbuch mit gepackten Elementfeldern."""
    d = {}
    for feld, wert in vars(res).items():
        if feld == "_cache":
            continue
        if feld in _JE_ELEMENT and isinstance(wert, dict) and wert:
            ids = np.fromiter(wert.keys(), int, count=len(wert))
            try:
                matrix = np.array([np.asarray(v, float) for v in wert.values()], float)
                if matrix.ndim >= 2 and matrix.shape[0] == len(ids):
                    d[feld] = ("__je_element__", ids, matrix)
                    continue
            except (ValueError, TypeError):
                pass
        d[feld] = wert
    return d


def _entpacken_results(d: dict, model):
    from .solver import Results
    res = Results(model=model)
    for feld, wert in d.items():
        if isinstance(wert, tuple) and len(wert) == 3 and wert[0] == "__je_element__":
            ids, matrix = wert[1], wert[2]
            wert = {int(i): matrix[k] for k, i in enumerate(ids.tolist())}
        setattr(res, feld, wert)
    res.model = model
    res._cache = {}
    return res


#: Reibverfahren in der Ergebnisdatei (15.10.2026), nach
#: Plastizitaet.reibungstangente
REIBVERFAHREN = {True: "konsistente Tangente", False: "bisheriges Verfahren",
                 # Modell ohne Reibung (16.10.2026, rechenverfahren.KEINE_REIBUNG)
                 "keine_reibung": "keine Reibung im Modell"}
#: Hinweis zu einer Ergebnisdatei ohne Angabe des Reibverfahrens, deren Modell
#: Reibung hat: geschrieben vor dem 15.10.2026, gerechnet ohne die Tangente
REIBVERFAHREN_ALT = "gerechnet mit dem bisherigen Reibverfahren – für aktuelle Ergebnisse neu rechnen"


def reibverfahren(model) -> str:
    """Das Reibverfahren, mit dem das Modell rechnet (solver.reibungstangente)."""
    from .solver import reibungstangente
    return REIBVERFAHREN[bool(reibungstangente(model)[0])]


def modell_hat_reibung(model) -> bool:
    """Rechnet das Modell mit Reibung? Kontaktpaar, Kontaktlager oder
    Kontaktelement mit mu > 0, ein Knoten-, Linien- oder Flaechenlager mit
    Reibbeiwert in einem Freiheitsgrad (wie model.lagerreibung_hinweis)."""
    for liste in ("contact_pairs", "contact_supports", "gap_elements"):
        if any(float(getattr(c, "mu", 0.0) or 0.0) > 0.0 for c in getattr(model, liste, None) or []):
            return True
    from .model import NDOF
    for liste in ("supports", "line_supports", "surface_supports"):
        for s in getattr(model, liste, None) or []:
            if any(float(s.dof_behaviour(d).mu or 0.0) > 0.0 for d in range(NDOF)):
                return True
    return False


def schreiben(pfad: str, model, analysis, fortschritt=None) -> int:
    """Die Analyse neben das Modell schreiben. Rueckgabe: Bytes."""
    if fortschritt:
        fortschritt(0.05, "Ergebnisse packen")
    inhalt = {"kennung": kennung(model)}
    info = getattr(analysis, "info", None) or {}
    # das Rechenverfahren (16.10.2026, rechenverfahren): Stand dieses Programms
    # und die Merkmale, mit denen gerechnet wurde - bei einer neuen Rechnung die
    # des Modells (die Kennung haelt die Einstellungen, eine passende Analyse ist
    # damit gerechnet), bei einer aus der Datei geladenen und nicht neu
    # gerechneten die der Datei (unbekannte bleiben None); das naechste Oeffnen
    # sagt den Hinweis dann wieder (wie kennung_vorbehalt)
    from . import rechenverfahren as rv
    merkmale = info.get("rechenverfahren") if info.get("verfahren_aus_datei") else None
    inhalt["verfahren"] = rv.angabe(model, merkmale if isinstance(merkmale, dict) else None)
    # „reibverfahren“ (15.10.2026) weiter fuer das Programm dieses Tages - ohne
    # die Angabe nennt es das bisherige Verfahren; so bleibt sie bei einer
    # geladenen, mit dem bisherigen Verfahren gerechneten Analyse weg, solange
    # das Modell heute mit der Tangente rechnet
    rt = inhalt["verfahren"]["merkmale"].get("reibverfahren")
    if rt is True or rt == rv.KEINE_REIBUNG or (rt is False and rv.merkmal("reibverfahren").aktuell(model) is False):
        inhalt["reibverfahren"] = REIBVERFAHREN[rt]
    if info.get("kennung_vorbehalt"):
        # aus einer Datei mit aelterer Kennung geladen und nicht neu gerechnet
        # (F06, N38): die neue Kennung behauptete, Knotenlage oder
        # Rechenangaben seien geprueft. Die Datei behaelt die alte Form, und
        # das naechste Oeffnen sagt den Vorbehalt wieder.
        for teil in info.get("kennung_fehlt") or ["knoten"]:
            for feld in _KENNUNGSTEILE.get(teil, ()):
                inhalt["kennung"].pop(feld, None)
    # alternativen: Ergebnisse von Alternativen einer Ergebniskombination, die
    # die Nachweise nicht aus den Lastfaellen wiedergewinnen koennen
    # (Kontaktmodell, Theorie II./III. Ordnung) - gepackt wie die Lastfaelle
    for gruppe in _ERGEBNISGRUPPEN:
        inhalt[gruppe] = {}
        for name, res in (getattr(analysis, gruppe, None) or {}).items():
            inhalt[gruppe][name] = _packen_results(res)
    for feld, wert in vars(analysis).items():
        # systeme: Faktorisierungen (SuperLU/Pardiso, nicht picklebar, nach dem
        # Laden wertlos); modelle: die Modellkopien je Stellung - sie entstehen
        # bei der naechsten Rechnung neu
        if feld in ("model", "systeme", "modelle", "reibverfahren", "verfahren") + _ERGEBNISGRUPPEN:
            continue
        if feld == "info" and isinstance(wert, dict) and "umstellung" in wert:
            # die Hinweise des Umschluesselns gelten der gelesenen alten Datei,
            # nicht der neu geschriebenen (R2-A2)
            wert = {k: v for k, v in wert.items() if k != "umstellung"}
        inhalt[feld] = wert
    if fortschritt:
        fortschritt(0.4, "Ergebnisse schreiben")
    with open(pfad, "wb") as fh:
        _Schreiber(fh, model).dump(inhalt)
    if fortschritt:
        fortschritt(1.0, "Ergebnisse geschrieben")
    return os.path.getsize(pfad)


def _huellen_umhaengen(an, model) -> None:
    """Ergebnisdatei von vor dem 04.10.2026 (Befund R1): dort steht die
    Umhuellende einer Ergebniskombination immer unter ihrem Namen. Heisst sie
    wie ein Schluessel des Programms („ULS“), hatte sie die Umhuellende unter
    diesem Schluessel ueberschrieben, soweit es die gab - unter ULS liegt dann
    die Umhuellende der Ergebniskombination, die Umhuellende GZT fehlt. Sie kommt unter den
    Schluessel, den solve_all ihr heute gibt („ULS (Ergebniskombination)“),
    und die Zusammenfassung nennt, was fehlt, statt unter „Umhüllende GZT“ die
    einer einzelnen Ergebniskombination zu zeigen.

    Erkannt wird sie an der Datei allein, nicht am Modell: die Umhuellende
    einer Ergebniskombination heisst seit jeher genau wie diese
    (umhuellende_der_kombination), die einer Art nie nur wie ihr Schluessel
    (seit a81fa7b „Umhuellende ULS“, seit dem 03.10.2026 „Umhüllende GZT“).
    ``env.name == Schluessel`` heisst darum sicher: Ergebniskombination. In
    der Nachbesserung vom 04.10.2026 (Befund L1 der Gegenpruefung) ersetzt
    das die erste Fassung, die nur Ergebniskombinationen des geladenen Modells
    erkannte: war „ULS“ nach der Rechnung umbenannt oder geloescht, blieb ihre
    Umhuellende die „Umhüllende GZT“, und nach dem naechsten Speichern war
    das Merkmal endgueltig weg. Eine Datei ab dem 04.10.2026 (eine
    Umhuellende traegt ``kombination``) und jede ohne Kollision bleiben
    unberuehrt."""
    from .begriffe import umhuellende_schluessel
    from .solver import umhuellende_art
    envs = getattr(an, "envelopes", None)
    if not envs or any(getattr(e, "kombination", None) is not None for e in envs.values()):
        return
    eks = [k for k, e in envs.items() if getattr(e, "name", None) == k]
    if not eks:
        return
    arten_modell = {umhuellende_art(c.typ) for c in model.combinations.values()}
    # die Arten des Modells und die, die in der Datei stehen (auch ein
    # unbekannter Typ, dessen Kombination es im Modell nicht mehr gibt)
    arten = arten_modell | {k for k in envs if k not in eks}
    neu = {n: k for n, k in umhuellende_schluessel(eks, arten).items() if k != n}
    if not neu:
        return
    an.envelopes = {neu.get(k, k): v for k, v in envs.items()}
    for n, k in neu.items():
        an.envelopes[k].kombination = n
        an.info.setdefault("umhuellende_schluessel", {})[n] = k
        # fehlt: das Modell hat Kombinationen dieser Art, die Datei keine
        # Umhuellende mehr unter ihrem Schluessel
        if n in arten_modell and n not in an.envelopes:
            an.info.setdefault("umhuellende_ueberschrieben", {})[n] = n


class _Unsicher(Exception):
    """Ein Name der Ergebnisdatei laesst sich nicht sicher umschluesseln."""


#: Felder der Nachweisergebnisse, die den Namen einer Kombination, eines
#: Lastfalls oder einer Alternative „<EK> [k]“ tragen (Anzeige): EC3
#: (MemberCheck.governing, section_checks, stability, woelb: "combo"), GZG,
#: Beulen, Lasteinleitung, Volumen, Anschluesse (kombination, je_kombination),
#: Theorie II. Ordnung (Th2Info.kombination); Schwingung (dyn["lastfall"]),
#: Knicklaengen (KnicklaengenErgebnis.grundzustand)
_NAMENSFELDER = ("kombination", "combo", "lastfall", "grundzustand")
#: Listen solcher Namen (DesignResults/AnschlussResults.combinations,
#: GZG-/Beul-/Einleitungs-/VolumenResults.kombinationen) - bei Theorie II./III.
#: Ordnung ist ``kombinationen`` ein Woerterbuch {Name: Info}
_LISTENFELDER = ("kombinationen", "combinations")
#: Freie Texte, in denen ein Name nach seinem Klartext steht („Kombination K1
#: nicht nachgewiesen“, „Ergebnis 'K1' fehlt“)
_TEXTFELDER = ("warnungen", "warnings", "hinweise", "log")
#: Nachweise und Ergebnisse der Analyse, die Namen tragen koennen
_NACHWEISE = (("design", "Nachweise EC3"), ("gzg", "Verformungsnachweise (GZG)"),
              ("beulen", "Beulnachweise"), ("lasteinleitung", "Lasteinleitung"),
              ("volumen", "Volumennachweise"), ("joints", "Anschlüsse"),
              ("fatigue", "Ermüdung"), ("schwingung", "Schwingung"),
              ("knicklaengen", "Knicklängen"), ("theorie2", "Theorie II. Ordnung"),
              ("theorie3", "Theorie III. Ordnung"))


def _namen_umschluesseln(an, model, tab: dict) -> None:
    """Eine Ergebnisdatei auf die Namen der Umstellung beim Oeffnen
    bringen (Model._namen_umstellen, Paket R2-A2) - dieselben
    Zahlen unter den neuen Namen, ohne Neurechnung.

    Umgeschluesselt werden die Schluessel von ``cases``, ``combinations``
    und ``alternativen`` („<EK> [k]“ wird „<EK neu> [k]“), ``Results.name``
    und die Namen in ``Results.info`` (Grundlast, eingefrorener Zustand,
    Herkunft des Starts), die Umhuellenden mit Schluessel, Herkunft
    (``names``), ``kombination`` und ``name`` - nach _huellen_umhaengen, also
    auch die R1-Schluessel „<Name> (Ergebniskombination)“ -, die Tabellen der
    Theorie II./III. Ordnung, die Felder der Nachweise mit einem Namen
    (_NAMENSFELDER, _LISTENFELDER, ``gleiche`` der EC3-Nachweise, auch
    zusammengefasste Eintraege „A [1] = B [1]“), ihre Warnungstexte (nur der
    Klartext „Lastfall X“, „Kombination X“, „Ergebnis 'X'“ - nie „Ermüdungslast
    'X'“: RFEM-Ermuedungslasten heissen wie ihre FAT-Kombination) und die
    Eintraege von
    ``info`` mit Namen. Die Stellungsreihe steht nicht in der Ergebnisdatei
    (sie lebt nur in der Sitzung) und kommt mit der naechsten Rechnung.

    Ein Name, den das alte Modell nicht kannte (etwa die Umhuellende einer
    danach geloeschten Ergebniskombination), bleibt, wie er ist - ausser er
    gliche einem neuen Namen oder war schon im alten Modell mehrdeutig
    (Lastfall und Kombination gleichen Namens). Dann wird verworfen, was ihn
    traegt, und die Zusammenfassung nennt es: lieber neu rechnen als ein
    Ergebnis unter einem falschen Namen zeigen. Die Hinweise stehen in
    ``an.info["umstellung"]`` (Analysis.summary); geschrieben werden sie
    nicht."""
    import re
    from .model import Model
    from .solver import Results, Envelope, umhuellende_schluessel_im_modell
    lf = dict(tab.get("lastfaelle") or {})
    ko = dict(tab.get("kombinationen") or {})
    zweideutig = set(tab.get("zweideutig") or ())
    neue = set(model.load_cases) | set(model.combinations)
    alt_muster = re.compile(r"(.+) \[(\d+)\]")
    hinweise = []

    def alternative(n):
        t = alt_muster.fullmatch(n)
        if t and t.group(1) in ko:
            return f"{ko[t.group(1)]} [{t.group(2)}]"
        return None

    def name(n):
        """Ein Name ohne Angabe, ob Lastfall, Kombination oder Alternative."""
        if not isinstance(n, str):
            return n
        if n in zweideutig:
            raise _Unsicher(n)
        if n in lf:
            return lf[n]
        if n in ko:
            return ko[n]
        a = alternative(n)
        if a is not None:
            return a
        # unbekannt (veraltet): bleibt, solange er keinen neuen Namen vortaeuscht
        t = alt_muster.fullmatch(n)
        if n in neue or (t is not None and t.group(1) in neue):
            raise _Unsicher(n)
        return n

    def eintrag(n):
        """Wie name, auch fuer zusammengefasste Eintraege „A [1] = B [1] = …“
        (ec3.design._gleich_name)."""
        if not isinstance(n, str) or " = " not in n or n in lf or n in ko or alternative(n):
            return name(n)
        return " = ".join(t if t.startswith("… (") else name(t) for t in n.split(" = "))

    # Klartext in freien Texten: ein Durchgang, damit ein neuer Name nicht
    # noch einmal ersetzt wird (K1 -> LK1, LK1 -> LK5)
    geaendert_lf = {a: b for a, b in lf.items() if a != b}
    geaendert_ko = {a: b for a, b in ko.items() if a != b}
    muster_text = None
    if (geaendert_lf or geaendert_ko) and not zweideutig:
        namen = sorted(set(geaendert_lf) | set(geaendert_ko), key=len, reverse=True)
        alternativen = "|".join(re.escape(n) for n in namen)
        muster_text = re.compile(
            rf"(?P<p>Lastfall |Lastfalls |Kombination |Ergebniskombination |Lastkombination )"
            rf"(?P<n>{alternativen})(?!\w)|(?P<q>(?:Ergebnis|Überlagerung) ')(?P<m>{alternativen})(?P<e>')")

    def text(t):
        if muster_text is None or not isinstance(t, str):
            return t

        def ersetzen(mt):
            if mt.group("p"):
                p, n = mt.group("p"), mt.group("n")
                tafel = geaendert_lf if p.startswith("Lastfall") else geaendert_ko
                return p + tafel.get(n, n)
            n = mt.group("m")
            neu = geaendert_ko.get(n) if n not in lf else geaendert_lf.get(n)
            return mt.group("q") + (neu or n) + mt.group("e")
        return muster_text.sub(ersetzen, t)

    def results_umschluesseln(r, neu_name) -> None:
        if getattr(r, "name", None) is not None and isinstance(r.name, str):
            r.name = neu_name
        info = getattr(r, "info", None)
        if not isinstance(info, dict):
            return
        if isinstance(info.get("grundlast"), list):
            info["grundlast"] = [lf.get(x, x) for x in info["grundlast"]]
        if isinstance(info.get("factors"), dict):
            # {Lastfall: Faktor} der Rechnung - der Bericht nennt sie
            # („Lastfaktoren“)
            try:
                info["factors"] = {name(x): f for x, f in info["factors"].items()}
            except _Unsicher:
                info.pop("factors")
        if info.get("contact_frozen_from"):
            try:
                info["contact_frozen_from"] = name(info["contact_frozen_from"])
            except _Unsicher:
                info.pop("contact_frozen_from")
        for schl in ("start_angeboten_von", "theorie_fehler"):
            if isinstance(info.get(schl), str):
                info[schl] = text(info[schl])

    # --- Lastfaelle, Kombinationen, Alternativen ---
    neu_cases = {}
    for n, r in an.cases.items():
        n2 = lf.get(n)
        if n2 is None:
            hinweise.append(f"Lastfall „{n}“ der Ergebnisdatei gibt es im Modell nicht - verworfen")
            continue
        results_umschluesseln(r, n2)
        neu_cases[n2] = r
    an.cases = neu_cases
    neu_k = {}
    for n, r in an.combinations.items():
        n2 = ko[n]                      # lesen hat fremde Kombinationen abgewiesen
        results_umschluesseln(r, n2)
        neu_k[n2] = r
    an.combinations = neu_k
    neu_alt = {}
    for n, r in (getattr(an, "alternativen", None) or {}).items():
        try:
            n2 = alternative(n) or name(n)
        except _Unsicher:
            hinweise.append(f"Ergebnis der Alternative „{n}“ verworfen: der Name lässt sich nicht "
                            "sicher zuordnen – neu rechnen")
            continue
        if n2 in neu_alt:
            hinweise.append(f"Ergebnis der Alternative „{n}“ verworfen: „{n2}“ gibt es schon – neu rechnen")
            continue
        results_umschluesseln(r, n2)
        neu_alt[n2] = r
    an.alternativen = neu_alt

    # --- Umhuellende (nach _huellen_umhaengen: kombination ist gesetzt, wo
    # R1 den Schluessel geaendert hat; sonst heisst die Umhuellende einer
    # Ergebniskombination wie ihr Schluessel) ---
    schluessel = umhuellende_schluessel_im_modell(model)
    neu_env = {}
    for key, env in (getattr(an, "envelopes", None) or {}).items():
        besitzer = getattr(env, "kombination", None)
        if besitzer is None and getattr(env, "name", None) == key:
            besitzer = key
        try:
            alt_namen = list(getattr(env, "names", None) or [])
            namen = [name(x) for x in alt_namen]
            if len(set(namen)) != len(set(alt_namen)):
                raise _Unsicher(", ".join(alt_namen))
            if besitzer is None:
                k2 = key
            elif besitzer in ko:
                k2 = schluessel.get(ko[besitzer], ko[besitzer])
            elif besitzer in neue or key in neue or besitzer in zweideutig:
                raise _Unsicher(besitzer)
            else:
                k2 = key
            if k2 in neu_env:
                raise _Unsicher(k2)
        except _Unsicher as ex:
            hinweise.append(f"Umhüllende „{key}“ verworfen: der Name „{ex}“ lässt sich nicht sicher "
                            "zuordnen – neu rechnen")
            continue
        if besitzer is not None and besitzer in ko:
            env.kombination = ko[besitzer]
            env.name = ko[besitzer]
        if hasattr(env, "names"):
            env.names = namen
        neu_env[k2] = env
    an.envelopes = neu_env

    # --- info: Eintraege unter Namen; einer, der sich nicht sicher zuordnen
    # laesst (eine veraltete „EK1“ neben der neuen EK1), faellt weg ---
    info = an.info if isinstance(getattr(an, "info", None), dict) else {}

    def neu_geschluesselt(d: dict, wert=lambda v: v) -> dict:
        aus = {}
        for n, v in d.items():
            try:
                aus[name(n)] = wert(v)
            except _Unsicher:
                continue
        return aus
    if isinstance(info.get("umhuellende"), dict):
        info["umhuellende"] = neu_geschluesselt(info["umhuellende"])
    if isinstance(info.get("umhuellende_schluessel"), dict):
        # der R1-Schluessel einer umbenannten Ergebniskombination ist ihr
        # neuer Name - der Hinweis „heißt … (Ergebniskombination)“ entfaellt
        neu = {}
        for n, kk in info["umhuellende_schluessel"].items():
            if n in ko:
                k2 = schluessel.get(ko[n], ko[n])
                if k2 != ko[n]:
                    neu[ko[n]] = k2
            else:
                neu.update(neu_geschluesselt({n: kk}))
        info["umhuellende_schluessel"] = neu
        if not neu:
            info.pop("umhuellende_schluessel")
    if isinstance(info.get("umhuellende_ueberschrieben"), dict):
        info["umhuellende_ueberschrieben"] = neu_geschluesselt(info["umhuellende_ueberschrieben"])
    if isinstance(info.get("kontakt_eingefroren"), dict):
        neu = {}
        for n, r in info["kontakt_eingefroren"].items():
            try:
                neu[name(n)] = name(r)
            except _Unsicher:
                continue
        info["kontakt_eingefroren"] = neu
    if isinstance(info.get("warnungen"), list):
        info["warnungen"] = [text(z) for z in info["warnungen"]]

    # --- Nachweise ---
    def walk(obj, tiefe=0):
        if tiefe > 12 or obj is None or isinstance(obj, (str, bytes, int, float, bool, np.ndarray,
                                                            np.generic, Model, Results, Envelope)):
            return
        if isinstance(obj, dict):
            felder = list(obj.items())
            setzen = obj.__setitem__
        elif isinstance(obj, (list, tuple, set)):
            for x in obj:
                walk(x, tiefe + 1)
            return
        else:
            d = getattr(obj, "__dict__", None)
            if not isinstance(d, dict):
                return
            felder = list(d.items())

            def setzen(k, v, _o=obj):
                setattr(_o, k, v)
        for k, v in felder:
            if k in _NAMENSFELDER and isinstance(v, str):
                setzen(k, eintrag(v))
            elif k in _LISTENFELDER and isinstance(v, list) and all(isinstance(x, str) for x in v):
                setzen(k, [eintrag(x) for x in v])
            elif k in _LISTENFELDER and isinstance(v, dict):
                neu = {}
                for n, info_n in v.items():
                    n2 = eintrag(n)
                    # Th3Info nennt sich ``name``, Th2Info ``kombination``
                    if isinstance(getattr(info_n, "name", None), str) and info_n.name == n:
                        info_n.name = n2
                    walk(info_n, tiefe + 1)
                    neu[n2] = info_n
                setzen(k, neu)
            elif k == "gleiche" and isinstance(v, dict):
                setzen(k, {eintrag(n): [name(x) for x in liste] for n, liste in v.items()})
            elif k in _TEXTFELDER and isinstance(v, list):
                setzen(k, [text(x) for x in v])
            else:
                walk(v, tiefe + 1)

    for feld, titel in _NACHWEISE:
        wert = getattr(an, feld, None)
        if wert is None:
            continue
        try:
            walk(wert)
        except _Unsicher as ex:
            setattr(an, feld, None)
            hinweise.append(f"{titel} verworfen: der Name „{ex}“ lässt sich nicht sicher zuordnen – "
                            "neu rechnen")
    if zweideutig:
        hinweise.append("Die Warnungstexte der Nachweise nennen die alten Namen - die alte Datei hatte "
                        "mehrdeutige Namen (" + ", ".join(f"„{n}“" for n in sorted(zweideutig)[:5]) + ")")
    if geaendert_lf or geaendert_ko:
        hinweise.insert(0, "Ergebnisse unter den beim Öffnen umgestellten Namen geladen (Tabelle "
                           "alt → neu oben) - dieselben Zahlen ohne Neurechnung")
    if hinweise:
        info["umstellung"] = hinweise
    an.info = info


def lesen(pfad: str, model, fortschritt=None):
    """Die Analyse zum Modell lesen; ValueError, wenn die Datei nicht passt."""
    from .solver import Analysis
    if fortschritt:
        fortschritt(0.05, "Ergebnisse lesen")
    with open(pfad, "rb") as fh:
        inhalt = _Leser(fh, model).load()
    from . import rechenverfahren as rvf
    angabe = inhalt.get("verfahren") if isinstance(inhalt.get("verfahren"), dict) else {}
    stand = angabe.get("stand") if isinstance(angabe.get("stand"), int) else None
    if stand is None and "reibverfahren" in inhalt:
        stand = 2                       # a371cf2 bis b63e669 (15.10.2026 abends)
    # R2-A2: Hat das Oeffnen die Namen auf LF/LK/EK umgestellt (model._umbenennung),
    # traegt die Datei die alten Namen. Die Kennung wird dann gegen den Stand mit
    # den alten Namen geprueft (Model._dict_vor_umstellung), Kombinationen ueber die
    # Tabelle alt -> neu; danach schluesselt _namen_umschluesseln die Ergebnisse um.
    tab = getattr(model, "_umbenennung", None)
    d_alt = getattr(model, "_dict_vor_umstellung", None) if tab is not None else None
    if d_alt is not None:
        # nur fuer das Modell, wie die Umstellung es hinterliess: wurde es danach
        # geaendert (Lastfall angelegt, Last geaendert ...), zaehlt der heutige Stand
        # mit den neuen Namen - und die Datei passt nicht
        d_neu = getattr(model, "_dict_nach_umstellung", None)
        if d_neu is None or kennung(model) != kennung(model, d_neu):
            d_alt = None
    ko = (tab.get("kombinationen") or {}) if tab is not None else {}
    k_datei = inhalt.get("kennung")
    if (tab is None and isinstance(k_datei, dict) and int(k_datei.get("modellfassung", 0) or 0) < 9
            and int(getattr(model, "_dateifassung", 0) or 0) >= 9):
        # ein Modell der Fassung 9 (schon umgestellt gespeichert) neben einer Ergebnisdatei
        # von vor der Umstellung: ihre Namen sind die alten - verwerfen statt Ergebnisse
        # unter fremden Namen zu zeigen
        raise ValueError("Die Ergebnisdatei passt nicht zum Modell: sie trägt die Namen von vor der "
                         "Umstellung auf LF/LK/EK, das Modell schon die neuen – neu rechnen")
    ok, grund, fehlt, *rest = _pruefen(inhalt.get("kennung"), model, stand, d_alt)
    gesetzt = (rest[0] if rest else None) or []
    # eine Kombination der Datei, die es im Modell nicht (mehr) gibt, wird
    # beim Namen genannt (R2-A1, G1) - auch neben den geaenderten Gruppen
    fremd = [n for n in (inhalt.get("combinations") or {}) if ko.get(n, n) not in model.combinations]
    if not ok and fremd:
        grund = (f"Kombination {', '.join(repr(n) for n in fremd[:5])}{' …' if len(fremd) > 5 else ''} "
                 f"gibt es im Modell nicht (umbenannt oder gelöscht); {grund}")
    if not ok:
        raise ValueError(f"Die Ergebnisdatei passt nicht zum Modell: {grund}")
    vorbehalt = grund                   # passt, aber nur mit einer aelteren Kennung (F06, N38)
    if fortschritt:
        fortschritt(0.6, "Ergebnisse entpacken")
    # Ergebnisse folgen jedem Namen (R2-A1, Nachbesserung G1, 04.10.2026): die
    # Kennung vergleicht nur die Lastfallnamen. Eine Kombination der Datei, die
    # das Modell nicht (mehr) hat - umbenannt oder geloescht, nachdem die
    # Datei geschrieben war -, liess die Ergebnisliste beim Oeffnen mit
    # KeyError scheitern (gui/main.py, _fill_result_selector) und stand sonst
    # unter ihrem alten Namen. Seit R2-A2 mit der Tabelle alt -> neu.
    fremd = [n for n in (inhalt.get("combinations") or {}) if ko.get(n, n) not in model.combinations]
    if fremd:
        raise ValueError("Die Ergebnisdatei passt nicht zum Modell: Kombination "
                         + ", ".join(f"'{n}'" for n in fremd[:5]) + (" …" if len(fremd) > 5 else "")
                         + " gibt es im Modell nicht (umbenannt oder gelöscht)")
    an = Analysis(model)
    for gruppe in _ERGEBNISGRUPPEN:
        for name, d in (inhalt.get(gruppe) or {}).items():
            getattr(an, gruppe)[name] = _entpacken_results(d, model)
    for feld, wert in inhalt.items():
        if feld in ("kennung", "reibverfahren", "verfahren") + _ERGEBNISGRUPPEN:
            continue
        setattr(an, feld, wert)
    # Das Rechenverfahren (16.10.2026, rechenverfahren): womit die Datei
    # gerechnet ist - aus ihrer Angabe, ohne sie aus dem, was sie sicher sagt
    # (Reibverfahren vom 15.10.2026 abends, Kennung mit einem damals gesetzten
    # Wert, Protokollzeilen); was sich nicht sicher erkennen laesst, bleibt None.
    # Die Ergebnisse gelten; weicht ein Merkmal, das dieses Modell betrifft, vom
    # heutigen Verfahren ab, sagt es der Hinweis (Statuszeile und Protokoll).
    for k in ("rechenverfahren", "verfahren_hinweis", "verfahren_betroffen", "verfahren_aus_datei", "reibverfahren",
              "reibverfahren_vorbehalt"):
        an.info.pop(k, None)
    merkmale = rvf.merkmale_der_datei(inhalt, model, gesetzt)
    an.info["rechenverfahren"] = merkmale
    an.info["verfahren_aus_datei"] = True
    # Verbesserung: Hinweis; Fehlerkorrektur (auch am Import, auch bei unsicherem
    # Alter der Datei): Status „Ergebnis möglicherweise betroffen – neu rechnen“ -
    # die Ergebnisse bleiben (Einstufung des Anwenders vom 16.10.2026)
    bew = rvf.bewerten(model, merkmale, an)
    an.info.pop("verfahren_unsicher", None)
    if bew["hinweis"]:
        an.info["verfahren_hinweis"] = bew["hinweis"]
    if bew["betroffen"]:
        an.info["verfahren_betroffen"] = bew["betroffen"]
    if bew["unsicher"]:
        an.info["verfahren_unsicher"] = list(bew["unsicher"])
    # wie am 15.10.2026 (a371cf2): das Reibverfahren als Text, und der Vorbehalt
    # zu einer Datei mit dem bisherigen Verfahren an einem Modell mit Reibung
    if merkmale.get("reibverfahren") is not None and merkmale.get("reibverfahren") in REIBVERFAHREN:
        an.info["reibverfahren"] = REIBVERFAHREN[merkmale["reibverfahren"]]
    if merkmale.get("reibverfahren") is False and rvf.merkmal("reibverfahren").aktuell(model) is True \
            and modell_hat_reibung(model):
        an.info["reibverfahren_vorbehalt"] = REIBVERFAHREN_ALT
    # der Vorbehalt der alten Kennung (F06, N38) gilt fuer diese Analyse, bis
    # neu gerechnet wird: schreiben behaelt dann die alte Form der Kennung
    an.info.pop("kennung_vorbehalt", None)
    an.info.pop("kennung_fehlt", None)
    if vorbehalt:
        an.info["kennung_vorbehalt"] = vorbehalt
        an.info["kennung_fehlt"] = list(fehlt)
    # erst die Schluessel aus R1 („ULS (Ergebniskombination)“), dann die
    # Tabelle: sonst traefe die Tabelle den alten Namen „ULS“ und haengte die
    # Umhuellende GZT um (Bestandsaufnahme R2, Risiko 3)
    _huellen_umhaengen(an, model)
    if tab is not None:
        _namen_umschluesseln(an, model, tab)
    # Die Umhuellenden mit bekanntem Schluessel heissen wie an der Oberflaeche
    # („Umhüllende GZT“). Der Name ist mit gespeichert: eine Datei von vor dem
    # 03.10.2026 traegt „Umhuellende ULS“, und so stand es dann in Protokoll
    # und Zusammenfassung (Befund S2 der Gegenpruefung von 11b).
    from .begriffe import UMHUELLENDE, umhuellende_kurz
    for k, env in (getattr(an, "envelopes", None) or {}).items():
        if k in UMHUELLENDE and hasattr(env, "name"):
            env.name = umhuellende_kurz(k)
    if fortschritt:
        fortschritt(1.0, "Ergebnisse geladen")
    return an


def groesse_text(n_bytes: int) -> str:
    if n_bytes >= 1e9:
        return f"{n_bytes / 1e9:.2f} GB"
    if n_bytes >= 1e6:
        return f"{n_bytes / 1e6:.1f} MB"
    return f"{n_bytes / 1e3:.0f} kB"
