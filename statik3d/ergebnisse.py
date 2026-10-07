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
    # Vorgaben des Vernetzers - das Netz selbst steht in Knoten und Elementen
    "netz": None,
    "tetp_kantenmitten": "elemente",
    "materials": "werkstoffe",
    "sections": "querschnitte", "shells": "querschnitte",
    "lines": "geometrie", "flaechen": "geometrie", "koerper": "geometrie",
    "supports": "lager", "line_supports": "lager", "surface_supports": "lager",
    "hinges": "gelenke", "kopplungen": "gelenke", "starrkoerper": "gelenke", "federn": "gelenke",
    "grenzschichten": "gelenke",
    # je Lastfall geteilt: die Lasten nach „lasten“, der Rest nach „lastfaelle“;
    # die Lastgenerierer stehen bei den Lasten, die sie erzeugen
    "load_cases": "lasten", "winde": "lasten", "wasserdruecke": "lasten",
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
ANZEIGEFELDER = {"load_cases": ("nummer",), "combinations": ("nummer",), "supports": ("groesse",)}
#: Felder eines Lastfalls, die Lasten tragen - der Rest sind seine Eigenschaften
LASTFELDER = ("nodal_loads", "beam_loads", "face_loads", "geometrielasten", "linienlasten",
              "zwangsverformungen", "vorspannungen", "uebermasse", "temp_loads", "gravity")
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
            namen |= _texte(wert)
    return namen


def _bereinigt(schluessel: str, wert, lagernamen: bool):
    """Ein Schluessel der Modelldatei ohne seine Anzeigefelder (TEXTFELDER,
    ANZEIGEFELDER, die Namen der Lager, wenn keine Stellung sie nennt)."""
    weg = set(TEXTFELDER) | set(ANZEIGEFELDER.get(schluessel, ()))
    if schluessel in _LAGERLISTEN and not lagernamen:
        weg.add("name")

    def objekt(x):
        if not isinstance(x, dict):
            return x
        y = {k: v for k, v in x.items() if k not in weg}
        if schluessel == "load_cases":
            for f in LASTFELDER:
                if isinstance(y.get(f), list):
                    y[f] = [{k: v for k, v in l.items() if k not in TEXTFELDER} if isinstance(l, dict) else l
                            for l in y[f]]
        return y
    if isinstance(wert, list):
        return [objekt(x) for x in wert]
    if isinstance(wert, dict) and schluessel in _NAMENSSAMMLUNGEN:
        return {k: objekt(v) for k, v in wert.items()}
    if isinstance(wert, dict) and schluessel in _EINZELOBJEKTE:
        return objekt(wert)
    return wert


def rechenkennung(model) -> tuple:
    """({Gruppe: Hash}, {Lastfall: [Hash Eigenschaften, Hash Lasten]}) - alles,
    was das Ergebnis bestimmt, ausser Knoten und Elementen (eigene Hashes).

    Gelesen wird die Form der Modelldatei (Model.to_dict ohne Netz): sie ist
    das, was nach Speichern und Laden wieder da ist; aus Objektlasten
    abgeleitete Elementlasten etwa stehen nicht darin, sie entstehen beim
    Verteilen neu. Sammlungen mit Namen zaehlen ohne ihre Reihenfolge, Listen
    (Lager, Kopplungen: ueber die Nummer genannt) mit ihr."""
    d = model.to_dict(netz=False)
    namen = lagernamen_zaehlen(model)
    verwendet = _verwendete_namen(model, d)
    teile: dict = {g: [] for g in GRUPPEN}
    einzeln: dict = {}
    for schluessel, wert in d.items():
        gruppe = MODELLTEILE.get(schluessel, "sonstiges")
        if gruppe is None:
            continue
        if schluessel in _NAMENSSAMMLUNGEN and isinstance(wert, dict):
            wert = {k: v for k, v in wert.items() if k in verwendet}
        wert = _bereinigt(schluessel, wert, namen)
        if (isinstance(wert, list) and isinstance(getattr(model, schluessel, None), dict)
                and all(isinstance(x, dict) for x in wert)):
            wert = sorted(wert, key=lambda x: str(x.get("name", "")))
        if schluessel == "load_cases":
            for lc in wert:
                name = str(lc.get("name", ""))
                eig = _hash({k: v for k, v in lc.items() if k not in LASTFELDER})
                last = _hash({k: v for k, v in lc.items() if k in LASTFELDER})
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


def kennung(model) -> dict:
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
    Meldung sagen kann, welcher Lastfall anders ist."""
    knoten = np.asarray(model.nodes, float).reshape(-1, 3) if model.nn else np.zeros((0, 3))
    gruppen, einzeln = rechenkennung(model)
    return {"version": VERSION, "name": str(model.name), "nn": int(model.nn),
            "ne": int(len(model.elements)),
            "koordinaten": float(np.round(knoten.sum(), 6)) if knoten.size else 0.0,
            "knoten": knotenhash(model),
            "lastfaelle": sorted(model.load_cases),
            "elemente": elementhash(model),
            "rechnung": gruppen, "rechnung_fassung": RECHENKENNUNG_FASSUNG,
            "lastfaelle_einzeln": einzeln}


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
    jetzt = kennung(model)
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
            return False, "seit der Rechnung geändert: " + ", ".join(_gruppentext(g, k, jetzt) for g in anders), []
    else:
        fehlt.append("rechnung")
    return True, vorbehalt_text(fehlt), fehlt


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


def schreiben(pfad: str, model, analysis, fortschritt=None) -> int:
    """Die Analyse neben das Modell schreiben. Rueckgabe: Bytes."""
    if fortschritt:
        fortschritt(0.05, "Ergebnisse packen")
    inhalt = {"kennung": kennung(model)}
    info = getattr(analysis, "info", None) or {}
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
        if feld in ("model", "systeme", "modelle") + _ERGEBNISGRUPPEN:
            continue
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


def lesen(pfad: str, model, fortschritt=None):
    """Die Analyse zum Modell lesen; ValueError, wenn die Datei nicht passt."""
    from .solver import Analysis
    if fortschritt:
        fortschritt(0.05, "Ergebnisse lesen")
    with open(pfad, "rb") as fh:
        inhalt = _Leser(fh, model).load()
    ok, grund, fehlt = pruefen(inhalt.get("kennung"), model)
    # eine Kombination der Datei, die es im Modell nicht (mehr) gibt, wird
    # beim Namen genannt (R2-A1, G1) - auch neben den geaenderten Gruppen
    fremd = [n for n in (inhalt.get("combinations") or {}) if n not in model.combinations]
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
    # unter ihrem alten Namen. Die Umstellung beim Laden (R2-A2) wird die
    # Tabelle alt -> neu mitgeben.
    fremd = [n for n in (inhalt.get("combinations") or {}) if n not in model.combinations]
    if fremd:
        raise ValueError("Die Ergebnisdatei passt nicht zum Modell: Kombination "
                         + ", ".join(f"'{n}'" for n in fremd[:5]) + (" …" if len(fremd) > 5 else "")
                         + " gibt es im Modell nicht (umbenannt oder gelöscht)")
    an = Analysis(model)
    for gruppe in _ERGEBNISGRUPPEN:
        for name, d in (inhalt.get(gruppe) or {}).items():
            getattr(an, gruppe)[name] = _entpacken_results(d, model)
    for feld, wert in inhalt.items():
        if feld in ("kennung",) + _ERGEBNISGRUPPEN:
            continue
        setattr(an, feld, wert)
    # der Vorbehalt der alten Kennung (F06, N38) gilt fuer diese Analyse, bis
    # neu gerechnet wird: schreiben behaelt dann die alte Form der Kennung
    an.info.pop("kennung_vorbehalt", None)
    an.info.pop("kennung_fehlt", None)
    if vorbehalt:
        an.info["kennung_vorbehalt"] = vorbehalt
        an.info["kennung_fehlt"] = list(fehlt)
    _huellen_umhaengen(an, model)
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
