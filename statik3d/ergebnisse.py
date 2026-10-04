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
    er steht), und ein aelteres Programm uebergeht den zusaetzlichen."""
    knoten = np.asarray(model.nodes, float).reshape(-1, 3) if model.nn else np.zeros((0, 3))
    return {"version": VERSION, "name": str(model.name), "nn": int(model.nn),
            "ne": int(len(model.elements)),
            "koordinaten": float(np.round(knoten.sum(), 6)) if knoten.size else 0.0,
            "lastfaelle": sorted(model.load_cases),
            "elemente": elementhash(model)}


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
    ok, grund = passt(inhalt.get("kennung"), model)
    if not ok:
        raise ValueError(f"Die Ergebnisdatei passt nicht zum Modell: {grund}")
    if fortschritt:
        fortschritt(0.6, "Ergebnisse entpacken")
    an = Analysis(model)
    for gruppe in _ERGEBNISGRUPPEN:
        for name, d in (inhalt.get(gruppe) or {}).items():
            getattr(an, gruppe)[name] = _entpacken_results(d, model)
    for feld, wert in inhalt.items():
        if feld in ("kennung",) + _ERGEBNISGRUPPEN:
            continue
        setattr(an, feld, wert)
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
