"""Beispielbibliothek (seit 09.11.2026, Freigabe des Anwenders „9 ja“).

Jedes Beispiel hat einen Titel, eine Gruppe (Stabwerk, Flächentragwerk,
Volumen), eine kurze Beschreibung, eine Parameterliste mit Wert, Einheit und
Grenzen und eine Funktion ``bauen(werte)``, die das Modell erzeugt. Die Werte
stehen in der Einheit der Parametertabelle (m, mm, kN, kN/m², Grad).

Eingebaut sind die acht Beispiele, die es vorher im Menü „Beispiel öffnen“
gab, und die sechs Testmodelle vom 09.11.2026. Mit den Vorgabewerten entsteht
jeweils dasselbe Modell wie vorher (tests/test_beispielbibliothek.py).

Eigene Beispiele: eine Python-Datei im Ordner ``Dokumente\\Statik3D\\Beispiele``
mit ``TITEL``, ``GRUPPE``, ``BESCHREIBUNG``, ``PARAMETER`` (Liste von
``(name, titel, wert, einheit, min, max)``) und ``def bauen(werte)``. Das
Programm führt diese Dateien aus, wenn die Bibliothek geöffnet wird; darum
gehören dort nur eigene Dateien hinein. Eine fehlerhafte Datei verhindert
nichts, sie steht mit dem Grund in der Liste ``fehler``.
"""
from __future__ import annotations

import glob
import importlib.util
import math
import os
import sys
import traceback
from dataclasses import dataclass, field
from typing import Callable

GRUPPEN = ("Stabwerk", "Flächentragwerk", "Volumen")


@dataclass
class Parameter:
    name: str
    titel: str
    wert: float
    einheit: str = ""
    min: float = -math.inf
    max: float = math.inf
    ganzzahl: bool = False

    def pruefen(self, w) -> float:
        """Den Wert lesen und gegen die Grenzen pruefen; ValueError mit Grund."""
        try:
            x = float(w)
        except (TypeError, ValueError):
            raise ValueError(f"{self.titel}: keine Zahl") from None
        if not math.isfinite(x):
            raise ValueError(f"{self.titel}: keine Zahl")
        if self.ganzzahl:
            if abs(x - round(x)) > 1e-9:
                raise ValueError(f"{self.titel}: ganze Zahl erwartet")
            x = int(round(x))
        if x < self.min or x > self.max:
            from ..zahlen import zahl_text
            raise ValueError(f"{self.titel}: {zahl_text(x)} {self.einheit} liegt außerhalb "
                             f"{zahl_text(self.min)} bis {zahl_text(self.max)} {self.einheit}".replace("  ", " "))
        return x


@dataclass
class Beispiel:
    schluessel: str
    titel: str
    gruppe: str
    beschreibung: str
    parameter: list = field(default_factory=list)
    bauen_fn: Callable = None
    #: Datei bei eigenen Beispielen, sonst ""
    datei: str = ""
    #: Querpruefungen ueber mehrere Werte: fn(werte) -> Liste von Meldungen
    pruefen_fn: Callable = None

    @property
    def eigen(self) -> bool:
        return bool(self.datei)

    def vorgaben(self) -> dict:
        return {p.name: p.wert for p in self.parameter}

    def werte_pruefen(self, werte: dict | None = None) -> dict:
        """Vollstaendige, gepruefte Werte; ValueError mit allen Gruenden."""
        werte = dict(werte or {})
        fehler, aus = [], {}
        for p in self.parameter:
            try:
                aus[p.name] = p.pruefen(werte.get(p.name, p.wert))
            except ValueError as ex:
                fehler.append(str(ex))
        if not fehler and self.pruefen_fn is not None:
            fehler += list(self.pruefen_fn(aus) or [])
        if fehler:
            raise ValueError("; ".join(fehler))
        return aus

    def bauen(self, werte: dict | None = None):
        """Das Modell mit gepruefter Eingabe bauen. Im Modell stehen danach
        das Beispiel und seine Werte (meta["beispiel"])."""
        w = self.werte_pruefen(werte)
        m = self.bauen_fn(dict(w))
        if m is None or not hasattr(m, "nodes"):
            raise ValueError(f"Beispiel „{self.titel}“: bauen() gab kein Modell zurück")
        m.meta["beispiel"] = {"schluessel": self.schluessel, "titel": self.titel,
                              "werte": {p.name: w[p.name] for p in self.parameter},
                              "einheiten": {p.name: p.einheit for p in self.parameter}}
        return m


def eingebaute() -> list:
    from .eingebaut import BEISPIELE
    return list(BEISPIELE)


def benutzerordner() -> str:
    """``Dokumente\\Statik3D\\Beispiele`` (der Ordner muss nicht bestehen).
    STATIK3D_BEISPIELE setzt einen anderen Ordner (Pruefungen)."""
    eigen = os.environ.get("STATIK3D_BEISPIELE")
    if eigen:
        return eigen
    dok = ""
    if sys.platform == "win32":
        try:
            import ctypes
            puffer = ctypes.create_unicode_buffer(260)
            # CSIDL_PERSONAL = 5: „Dokumente“, auch wenn er umgeleitet ist
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, puffer) == 0:
                dok = puffer.value
        except Exception:                 # noqa: BLE001
            dok = ""
    if not dok:
        dok = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(dok, "Statik3D", "Beispiele")


def _parameter_aus(eintrag) -> Parameter:
    if isinstance(eintrag, Parameter):
        return eintrag
    if isinstance(eintrag, dict):
        return Parameter(**eintrag)
    t = tuple(eintrag)
    if len(t) < 3:
        raise ValueError(f"Parameter {t!r}: mindestens (name, titel, wert)")
    p = Parameter(str(t[0]), str(t[1]), float(t[2]), *(t[3:4]),
                  *([float(x) for x in t[4:6]]))
    if len(t) > 6:
        p.ganzzahl = bool(t[6])
    return p


def aus_datei(pfad: str) -> Beispiel:
    """Ein eigenes Beispiel aus einer Python-Datei laden (fuehrt sie aus)."""
    stamm = os.path.splitext(os.path.basename(pfad))[0]
    modname = "statik3d_eigenes_beispiel_" + "".join(c if c.isalnum() else "_" for c in stamm)
    spec = importlib.util.spec_from_file_location(modname, pfad)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    bauen = getattr(mod, "bauen", None)
    if not callable(bauen):
        raise ValueError("die Funktion bauen(werte) fehlt")
    titel = str(getattr(mod, "TITEL", stamm))
    gruppe = str(getattr(mod, "GRUPPE", "Eigene"))
    parameter = [_parameter_aus(p) for p in getattr(mod, "PARAMETER", [])]
    namen = [p.name for p in parameter]
    if len(set(namen)) != len(namen):
        raise ValueError("Parameternamen doppelt")
    for p in parameter:
        p.pruefen(p.wert)                 # der Vorgabewert muss in den Grenzen liegen
    pr = getattr(mod, "pruefen", None)
    return Beispiel(f"datei:{stamm}", titel, gruppe, str(getattr(mod, "BESCHREIBUNG", "")),
                    parameter, bauen, datei=os.path.abspath(pfad),
                    pruefen_fn=pr if callable(pr) else None)


def aus_ordner(ordner: str | None = None):
    """(Beispiele, Fehler) aus dem Ordner; Fehler = [(Datei, Grund)]."""
    ordner = ordner or benutzerordner()
    beispiele, fehler = [], []
    if not os.path.isdir(ordner):
        return beispiele, fehler
    for pfad in sorted(glob.glob(os.path.join(ordner, "*.py"))):
        if os.path.basename(pfad).startswith("_"):
            continue
        try:
            beispiele.append(aus_datei(pfad))
        except Exception as ex:           # noqa: BLE001
            zeile = traceback.extract_tb(ex.__traceback__)
            ort = next((f" (Zeile {z.lineno})" for z in reversed(zeile)
                        if os.path.abspath(z.filename) == os.path.abspath(pfad)), "")
            fehler.append((pfad, f"{type(ex).__name__}: {ex}{ort}"))
    return beispiele, fehler


def alle(ordner: str | None = None, eigene: bool = True):
    """(eingebaute + eigene Beispiele, Fehler der eigenen Dateien)."""
    bsp = eingebaute()
    fehler = []
    if eigene:
        e, fehler = aus_ordner(ordner)
        bsp += e
    return bsp, fehler


def finden(schluessel: str) -> Beispiel:
    for b in eingebaute():
        if b.schluessel == schluessel:
            return b
    raise KeyError(f"Beispiel '{schluessel}' unbekannt")
