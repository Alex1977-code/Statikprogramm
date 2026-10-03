"""
Fachbegriffe statt Schluessel: Kombinationstypen und Umhuellende im Klartext
(03.10.2026, Teilpaket 11b des Oberflaechenplans).

Intern heissen die Typen einer Kombination ``ULS``, ``EQU``, ``ACC``,
``SLS_CH``, ``SLS_FR``, ``SLS_QP``, ``FAT`` und ``USER`` (``Combination.typ``,
Dateiformat, Importe), die Umhuellenden der Analyse ebenso, dazu ``CASES`` fuer
die Umhuellende der Lastfaelle (``Analysis.envelopes``). Diese Schluessel
bleiben, wie sie sind. Der Anwender liest den Klartext aus diesem Modul, und
zwar in zwei Formen:

* **kurz** - fuer Auswahllisten, Modellbaum, Kopfzeile der Ansicht, Tabellen
  und Meldungen: „GZT (STR/GEO)“, „GZG charakteristisch“, „Umhüllende GZT“;
* **lang** - fuer Bericht und Hinweise am Zeiger: „Grenzzustand der
  Tragfähigkeit (GZT)“.

Die Kurzformen folgen DIN EN 1990 und der deutschen Gewohnheit:

* GZT und GZG sind die Abkuerzungen der deutschen Fassung (Grenzzustand der
  Tragfaehigkeit, der Gebrauchstauglichkeit); ULS/SLS sagt dort niemand.
* Die Nachweisarten im GZT nennt EN 1990, 6.4.1 selbst mit EQU (Lagesicherheit),
  STR (Tragwerk), GEO (Baugrund) und FAT (Ermuedung). Die Kombination ``ULS``
  ist die Grundkombination nach Gl. 6.10 fuer STR und GEO - darum „GZT
  (STR/GEO)“, und ``EQU`` heisst „GZT (EQU)“.
* ``ACC`` ist die Kombination der aussergewoehnlichen Bemessungssituation
  (Gl. 6.11), ``FAT`` die Ermuedung, ``USER`` eine frei angelegte Kombination.
* Im GZG unterscheidet EN 1990, 6.5.3 die charakteristische, die haeufige
  und die quasi-staendige Kombination (Gl. 6.14 bis 6.16).
* Die Umhuellende ``ULS`` sammelt alle Kombinationen des GZT (``ULS``,
  ``EQU``, ``ACC`` und ``USER``, siehe solver.solve_all) - sie heisst darum
  „Umhüllende GZT“ ohne Nachweisart.

Die Kurzformen der Kombinationstypen und die Langformen der Umhuellenden sind
genau die Texte, die der Bericht seit jeher schreibt (report/html.py,
COMBO_TYPES und ENVELOPE_NAMES); der Bericht nimmt sie seitdem von hier und
schreibt dasselbe wie vorher.

Was kein bekannter Schluessel ist, erscheint unveraendert - etwa die
Umhuellende einer RFEM-Ergebniskombination, die unter dem Namen der
Kombination steht („Umhüllende EK3“).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Begriff:
    """Ein Fachbegriff in kurzer und langer Form."""
    kurz: str
    lang: str


#: Typ einer Kombination (Combination.typ) -> Begriff. Die Reihenfolge ist die
#: der Auswahllisten.
KOMBINATIONSTYPEN: dict[str, Begriff] = {
    "ULS": Begriff("GZT (STR/GEO)",
                   "Grenzzustand der Tragfähigkeit (GZT), Versagen von Tragwerk und "
                   "Baugrund (STR/GEO), ständige und vorübergehende "
                   "Bemessungssituation nach DIN EN 1990, Gl. 6.10"),
    "EQU": Begriff("GZT (EQU)",
                   "Grenzzustand der Tragfähigkeit (GZT), Verlust der Lagesicherheit "
                   "(EQU) nach DIN EN 1990"),
    "ACC": Begriff("außergewöhnlich",
                   "Grenzzustand der Tragfähigkeit (GZT), außergewöhnliche "
                   "Bemessungssituation nach DIN EN 1990, Gl. 6.11"),
    "SLS_CH": Begriff("GZG charakteristisch",
                      "Grenzzustand der Gebrauchstauglichkeit (GZG), charakteristische "
                      "Kombination nach DIN EN 1990, Gl. 6.14"),
    "SLS_FR": Begriff("GZG häufig",
                      "Grenzzustand der Gebrauchstauglichkeit (GZG), häufige "
                      "Kombination nach DIN EN 1990, Gl. 6.15"),
    "SLS_QP": Begriff("GZG quasi-ständig",
                      "Grenzzustand der Gebrauchstauglichkeit (GZG), quasi-ständige "
                      "Kombination nach DIN EN 1990, Gl. 6.16"),
    "FAT": Begriff("Ermüdung",
                   "Ermüdung (FAT) - nur für den Ermüdungsnachweis nach "
                   "DIN EN 1993-1-9, nicht in den Querschnittsnachweisen im GZT"),
    "USER": Begriff("benutzerdefiniert",
                    "benutzerdefinierte Kombination - geht in die Umhüllende GZT ein"),
}

#: Umhuellende der Analyse (Analysis.envelopes) -> Begriff
UMHUELLENDE: dict[str, Begriff] = {
    "ULS": Begriff("Umhüllende GZT", "Grenzzustand der Tragfähigkeit (GZT)"),
    "SLS_CH": Begriff("Umhüllende GZG charakteristisch",
                      "Gebrauchstauglichkeit, charakteristisch"),
    "SLS_FR": Begriff("Umhüllende GZG häufig", "Gebrauchstauglichkeit, häufig"),
    "SLS_QP": Begriff("Umhüllende GZG quasi-ständig",
                      "Gebrauchstauglichkeit, quasi-ständig"),
    "FAT": Begriff("Umhüllende Ermüdung", "Ermüdung"),
    "CASES": Begriff("Umhüllende Lastfälle", "Lastfälle"),
}

#: Kurzform je Kombinationstyp - fuer Tabellenspalten (Spalte.klartext)
TYP_KURZ: dict[str, str] = {k: b.kurz for k, b in KOMBINATIONSTYPEN.items()}


def typ_kurz(typ) -> str:
    """„GZT (STR/GEO)“ zu ``ULS`` - ein unbekannter Typ bleibt, wie er ist."""
    b = KOMBINATIONSTYPEN.get(str(typ))
    return b.kurz if b is not None else str(typ)


def typ_lang(typ) -> str:
    """Die lange Form eines Kombinationstyps (Bericht, Hinweis am Zeiger)."""
    b = KOMBINATIONSTYPEN.get(str(typ))
    return b.lang if b is not None else str(typ)


def typ_schluessel(text) -> str:
    """Der Schluessel zu einem Text aus einer Auswahlliste: aus „GZT
    (STR/GEO)“ wird ``ULS``. Ein Schluessel bleibt Schluessel, ein
    unbekannter Text bleibt, wie er ist."""
    t = str(text or "").strip()
    if t in KOMBINATIONSTYPEN:
        return t
    for k, b in KOMBINATIONSTYPEN.items():
        if t == b.kurz or t == b.lang:
            return k
    return t


def umhuellende_kurz(key) -> str:
    """„Umhüllende GZT“ zu ``ULS`` - fuer Listen, Baum, Kopfzeile. Eine
    unbekannte Umhuellende (etwa die einer RFEM-Ergebniskombination) heisst
    „Umhüllende <Name>“."""
    b = UMHUELLENDE.get(str(key))
    return b.kurz if b is not None else f"Umhüllende {key}"


def umhuellende_lang(key) -> str:
    """„Grenzzustand der Tragfähigkeit (GZT)“ zu ``ULS`` - wofuer die
    Umhuellende steht (Bericht, Hinweis am Zeiger). Unbekannt: der Name."""
    b = UMHUELLENDE.get(str(key))
    return b.lang if b is not None else str(key)
