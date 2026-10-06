"""Ergebnisse neben der Modelldatei speichern und wieder laden.

Bis zum 12.09.2026 hielt die Modelldatei nur das Modell: nach dem Öffnen war
jede Rechnung weg - am Drehlager 18 Minuten je Lastfall. Jetzt schreibt das
Programm beim Speichern die Analyse (Lastfälle, Kombinationen, Umhüllende,
Nachweise) in eine zweite Datei ``<modell>.ergebnisse`` und liest sie beim
Öffnen wieder ein, wenn sie zum Modell passt (Kennung: Knoten- und
Elementzahl, Summe der Koordinaten, Lastfallnamen, seit dem 24.09.2026 ein
Hash der Elemente).

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


def kennung(model) -> dict:
    """Woran die Ergebnisdatei erkennt, dass sie zu diesem Modell gehoert.

    „elemente“ (24.09.2026): Element 0 loeschen und einen Stab [0,5] anlegen
    aendert weder Knoten- und Elementzahl noch die Koordinatensumme - die
    alte Datei passte dann zum neuen Modell, die Werte standen an anderen
    Elementen (Gegenpruefung von 97be9ff). Die Dateiversion bleibt 1: alte
    Dateien ohne den Eintrag werden weiter gelesen (passt prueft ihn nur, wo
    er steht), und ein aelteres Programm uebergeht den zusaetzlichen.

    „modellfassung“ (R2-A2, 06.10.2026): die Fassung der Modelldatei, zu der
    die Namen der Ergebnisse gehoeren. Eine Datei ohne den Eintrag stammt von
    vor der Umstellung auf LF/LK/EK und traegt die alten Namen; lesen
    schluesselt sie mit der Tabelle der Umstellung um (_namen_umschluesseln)."""
    from .model import FORMAT_VERSION
    knoten = np.asarray(model.nodes, float).reshape(-1, 3) if model.nn else np.zeros((0, 3))
    return {"version": VERSION, "name": str(model.name), "nn": int(model.nn),
            "ne": int(len(model.elements)),
            "koordinaten": float(np.round(knoten.sum(), 6)) if knoten.size else 0.0,
            "lastfaelle": sorted(model.load_cases),
            "elemente": elementhash(model),
            "modellfassung": FORMAT_VERSION}


def passt(k: dict, model) -> tuple:
    """(True, "") wenn die Kennung zum Modell passt, sonst (False, Grund)."""
    jetzt = kennung(model)
    if not isinstance(k, dict):
        return False, "keine Kennung"
    if int(k.get("version", 0)) != VERSION:
        return False, f"Dateiversion {k.get('version')} statt {VERSION}"
    for feld, text in (("nn", "Knotenzahl"), ("ne", "Elementzahl")):
        if k.get(feld) != jetzt[feld]:
            return False, f"{text} {k.get(feld)} statt {jetzt[feld]}"
    if abs(float(k.get("koordinaten", 0.0)) - jetzt["koordinaten"]) > 1e-6 * max(1.0, abs(jetzt["koordinaten"])):
        return False, "die Knotenkoordinaten sind andere"
    if list(k.get("lastfaelle", [])) != jetzt["lastfaelle"]:
        return False, "die Lastfälle sind andere"
    if "elemente" in k and k["elemente"] != jetzt["elemente"]:
        return False, "die Elemente sind andere (Typ oder Knoten)"
    return True, ""


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
#: Theorie II. Ordnung (Th2Info.kombination)
_NAMENSFELDER = ("kombination", "combo")
#: Listen solcher Namen (DesignResults/AnschlussResults.combinations,
#: GZG-/Beul-/Einleitungs-/VolumenResults.kombinationen) - bei Theorie II./III.
#: Ordnung ist ``kombinationen`` ein Woerterbuch {Name: Info}
_LISTENFELDER = ("kombinationen", "combinations")
#: Freie Texte, in denen ein Name nach seinem Klartext steht („Kombination K1
#: nicht nachgewiesen“, „Ergebnis 'K1' fehlt“)
_TEXTFELDER = ("warnungen", "warnings", "hinweise")
#: Nachweise und Ergebnisse der Analyse, die Namen tragen koennen
_NACHWEISE = (("design", "Nachweise EC3"), ("gzg", "Verformungsnachweise (GZG)"),
              ("beulen", "Beulnachweise"), ("lasteinleitung", "Lasteinleitung"),
              ("volumen", "Volumennachweise"), ("joints", "Anschlüsse"),
              ("fatigue", "Ermüdung"), ("schwingung", "Schwingung"),
              ("knicklaengen", "Knicklängen"), ("theorie2", "Theorie II. Ordnung"),
              ("theorie3", "Theorie III. Ordnung"))


def _namen_umschluesseln(an, model, tab: dict) -> None:
    """Eine Ergebnisdatei von vor Fassung 9 auf die Namen der Umstellung
    beim Laden bringen (Model._namen_umstellen, Paket R2-A2) - dieselben
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
        hinweise.insert(0, "Ergebnisse aus einer Datei vor Fassung 9 - unter den neuen Namen geladen "
                           "(Tabelle alt → neu beim Öffnen), dieselben Zahlen ohne Neurechnung")
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
    k = inhalt.get("kennung")
    # R2-A2: eine Datei ohne „modellfassung“ (vor Fassung 9) traegt die alten
    # Namen. Hat das Laden das Modell umgestellt, schluesselt die Tabelle
    # alt -> neu sie um; sonst passen ihre Namen nicht zum Modell, und sie
    # wird verworfen, statt Ergebnisse unter fremden Namen zu zeigen (am
    # Drehlager - nur Ergebniskombinationen, keine Kombination in der Datei -
    # liess die Pruefung auf fremde Kombinationen unten sie sonst durch).
    tab = None
    if isinstance(k, dict) and int(k.get("modellfassung", 0) or 0) < 9:
        tab = getattr(model, "_umbenennung", None)
        if tab is None:
            raise ValueError("Die Ergebnisdatei passt nicht zum Modell: sie trägt die Namen von vor der "
                             "Umstellung auf LF/LK/EK, das Modell schon die neuen – neu rechnen")
        lf = tab.get("lastfaelle") or {}
        k = dict(k, lastfaelle=sorted(lf.get(n, n) for n in k.get("lastfaelle", [])))
    ok, grund = passt(k, model)
    if not ok:
        raise ValueError(f"Die Ergebnisdatei passt nicht zum Modell: {grund}")
    if fortschritt:
        fortschritt(0.6, "Ergebnisse entpacken")
    # Ergebnisse folgen jedem Namen (R2-A1, Nachbesserung G1, 04.10.2026): die
    # Kennung vergleicht nur die Lastfallnamen. Eine Kombination der Datei, die
    # das Modell nicht (mehr) hat - umbenannt oder geloescht, nachdem die
    # Datei geschrieben war -, liess die Ergebnisliste beim Oeffnen mit
    # KeyError scheitern (gui/main.py, _fill_result_selector) und stand sonst
    # unter ihrem alten Namen. Seit R2-A2 mit der Tabelle alt -> neu.
    ko = (tab.get("kombinationen") or {}) if tab is not None else {}
    fremd = [n for n in (inhalt.get("combinations") or {})
             if (ko.get(n) if tab is not None else n) not in model.combinations]
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
