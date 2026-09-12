"""Ergebnisse neben der Modelldatei speichern und wieder laden.

Bis zum 12.09.2026 hielt die Modelldatei nur das Modell: nach dem Öffnen war
jede Rechnung weg - am Drehlager 18 Minuten je Lastfall. Jetzt schreibt das
Programm beim Speichern die Analyse (Lastfälle, Kombinationen, Umhüllende,
Nachweise) in eine zweite Datei ``<modell>.ergebnisse`` und liest sie beim
Öffnen wieder ein, wenn sie zum Modell passt (Kennung: Knoten- und
Elementzahl, Summe der Koordinaten, Lastfallnamen).

Form: ein Pickle (Protokoll 5). Das Modell selbst steht nicht in der Datei -
jede Referenz auf das Modell (Results.model, Envelope.model, Nachweise) wird
beim Schreiben durch eine Marke ersetzt und beim Lesen auf das geladene
Modell gesetzt (persistent_id). Die grossen Woerterbuecher je Element
(solid_res, shell_res, beam_end, ...) werden als (Nummern, Matrix) gepackt:
1,8 Mio. einzelne Arrays wuerden das Pickle um Hunderte MB aufblaehen.
Rechenzwischenwerte (Results._cache) werden nicht geschrieben.
"""
from __future__ import annotations

import io
import os
import pickle

import numpy as np

DATEIENDUNG = ".ergebnisse"
VERSION = 1
_MODELLMARKE = "STATIK3D_MODELL"
#: Woerterbuecher je Element, die als (Nummern, Matrix) gepackt werden
_JE_ELEMENT = ("beam_end", "beam_q", "shell_res", "solid_res", "feder_res",
               "grenzschicht_res", "bimomente")


def pfad_zu(modellpfad: str) -> str:
    """``modell.json`` -> ``modell.ergebnisse``."""
    return os.path.splitext(str(modellpfad))[0] + DATEIENDUNG


def kennung(model) -> dict:
    """Woran die Ergebnisdatei erkennt, dass sie zu diesem Modell gehoert."""
    knoten = np.asarray(model.nodes, float).reshape(-1, 3) if model.nn else np.zeros((0, 3))
    return {"version": VERSION, "name": str(model.name), "nn": int(model.nn),
            "ne": int(len(model.elements)),
            "koordinaten": float(np.round(knoten.sum(), 6)) if knoten.size else 0.0,
            "lastfaelle": sorted(model.load_cases)}


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
        return False, "die Lastfaelle sind andere"
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
    inhalt = {"kennung": kennung(model), "cases": {}, "combinations": {}}
    for gruppe in ("cases", "combinations"):
        for name, res in (getattr(analysis, gruppe, None) or {}).items():
            inhalt[gruppe][name] = _packen_results(res)
    for feld, wert in vars(analysis).items():
        # systeme: Faktorisierungen (SuperLU/Pardiso, nicht picklebar, nach dem
        # Laden wertlos); modelle: die Modellkopien je Stellung - sie entstehen
        # bei der naechsten Rechnung neu
        if feld in ("model", "cases", "combinations", "systeme", "modelle"):
            continue
        inhalt[feld] = wert
    if fortschritt:
        fortschritt(0.4, "Ergebnisse schreiben")
    with open(pfad, "wb") as fh:
        _Schreiber(fh, model).dump(inhalt)
    if fortschritt:
        fortschritt(1.0, "Ergebnisse geschrieben")
    return os.path.getsize(pfad)


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
    for gruppe in ("cases", "combinations"):
        for name, d in (inhalt.get(gruppe) or {}).items():
            getattr(an, gruppe)[name] = _entpacken_results(d, model)
    for feld, wert in inhalt.items():
        if feld in ("kennung", "cases", "combinations"):
            continue
        setattr(an, feld, wert)
    if fortschritt:
        fortschritt(1.0, "Ergebnisse geladen")
    return an


def groesse_text(n_bytes: int) -> str:
    if n_bytes >= 1e9:
        return f"{n_bytes / 1e9:.2f} GB"
    if n_bytes >= 1e6:
        return f"{n_bytes / 1e6:.1f} MB"
    return f"{n_bytes / 1e3:.0f} kB"
