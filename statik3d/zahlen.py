"""
Zahlen lesen und schreiben - eine Regel fuer alle Eingabefelder (24.09.2026).

Bis zum 24.09.2026 lasen die Masken mit dem QDoubleValidator und
``float(text.replace(",", "."))``: „33.000“ (E_cm) wurde still zu 33,
„2.000.000“ Lastspiele zu 0 - zweimal gemessen (gui_analyse/validator_probe2.py
und validator_probe3.py). Der Qt-Validator folgt ausserdem dem Gebietsschema
des Systems und naehme dort Tausenderpunkte an. Darum gibt es hier **eine**
Regel, die Masken, Register, Dialoge, Tabellenzellen und die Ermuedungsmaske
gemeinsam benutzen:

* Komma und Punkt sind Dezimaltrenner, hoechstens einer je Zahl.
* Leerzeichen (auch schmale und geschuetzte) trennen Tausender, nur in
  Dreiergruppen: „2 000 000“.
* Mehrere Trenner („2.000.000“, „1.000,5“) sind ungueltig - nie wird daraus
  still eine andere Zahl oder 0.
* Genau drei Stellen nach einem einzelnen Punkt hinter einer ein- bis
  dreistelligen Zahl („33.000“) ist mehrdeutig: gelesen wird 33,000, aber
  die Eingabe muss bestaetigt werden („33,000 – gemeint 33 000?“).
* Exponenten („2e6“, „1,5e5“) werden gelesen; geschrieben wird nie
  wissenschaftlich.

Das Modul kennt kein Qt: Bericht und Modell (lastspiele_text) duerfen die
Oberflaeche nicht laden.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

#: Zustaende einer gelesenen Eingabe
LEER = "leer"
GUELTIG = "gueltig"
FRAGE = "frage"          # mehrdeutig („33.000“) - gilt erst nach Bestaetigung
UNGUELTIG = "ungueltig"

#: Leerzeichen, die als Tausendertrennung gelten: normales, geschuetztes
#: (U+00A0), schmales (U+2009) und schmales geschuetztes (U+202F)
LEERZEICHEN = (" ", " ", " ", " ")

#: Zeichen, die in einem Zahlenfeld ueberhaupt vorkommen duerfen - alles
#: andere nimmt das Feld schon beim Tippen nicht an
ZEICHEN = frozenset("0123456789+-.,eE") | frozenset(LEERZEICHEN)

#: Stellen beim Schreiben: 15 gueltige Ziffern sind die volle Genauigkeit
#: einer Gleitkommazahl ohne das Rauschen der 16./17. Stelle (0,1 + 0,2 zeigt
#: 0,3 und nicht 0,30000000000000004)
STELLEN = 15

_GRUPPE_VORN = re.compile(r"\d{1,3}")
_GRUPPE = re.compile(r"\d{3}")
TAUSENDERPUNKT = re.compile(r"^[+-]?\d{1,3}(\.\d{3})+$")


@dataclass(frozen=True)
class Lesung:
    """Ergebnis von :func:`lesen`.

    ``wert`` ist bei FRAGE die Lesart mit Dezimaltrenner (33.0), ``vorschlag``
    die mit Tausendertrennung (33000.0)."""
    status: str
    wert: float | None = None
    meldung: str = ""
    vorschlag: float | None = None

    @property
    def ungueltig(self) -> bool:
        return self.status == UNGUELTIG


def _normal(text) -> str:
    t = str(text if text is not None else "")
    for z in LEERZEICHEN[1:]:
        t = t.replace(z, " ")
    return t.strip()


def _gruppen_ok(teil: str, vorn: bool) -> bool:
    """Sind die Leerzeichen in ``teil`` Tausendertrennungen?

    Vor dem Komma: erste Gruppe 1-3 Ziffern, jede weitere genau 3 („2 000“).
    Nach dem Komma: jede Gruppe ausser der letzten genau 3 („0,123 45“)."""
    gruppen = teil.split(" ")
    if any(not g for g in gruppen):
        return False
    if vorn:
        return bool(_GRUPPE_VORN.fullmatch(gruppen[0])) and all(_GRUPPE.fullmatch(g) for g in gruppen[1:])
    return all(_GRUPPE.fullmatch(g) for g in gruppen[:-1]) and bool(_GRUPPE_VORN.fullmatch(gruppen[-1]))


def _beispiel(t: str) -> str:
    """Die vermutlich gemeinte Schreibweise fuer die Meldung."""
    if TAUSENDERPUNKT.match(t.replace(" ", "")):
        return zahl_text(float(t.replace(".", "").replace(" ", "")))
    return "1 234,5"


def lesen(text, ganz: bool = False) -> Lesung:
    """Eine Eingabe nach der Zahlenfeld-Regel lesen (siehe Modulkopf)."""
    roh = str(text if text is not None else "").strip()
    t = _normal(text)
    if not t:
        return Lesung(LEER)
    if any(z not in ZEICHEN for z in t):
        return Lesung(UNGUELTIG, meldung=f"„{roh}“ ist keine Zahl.")
    m = re.fullmatch(r"(?P<man>[^eE]*?)(?:[eE](?P<exp>[+-]?\d+))?", t)
    if m is None:
        return Lesung(UNGUELTIG, meldung=f"„{roh}“ ist keine Zahl (Exponent z. B. 2e6).")
    man, exp = m.group("man"), m.group("exp")
    if man.count(",") + man.count(".") > 1:
        return Lesung(UNGUELTIG, meldung=(
            f"„{roh}“: höchstens ein Dezimaltrenner (Komma oder Punkt). "
            f"Tausender mit Leerzeichen schreiben, z. B. {_beispiel(man)}."))
    vz = ""
    if man[:1] in "+-":
        vz, man = man[0], man[1:]
    trenner = "," if "," in man else "." if "." in man else ""
    vorn, _, hinten = man.partition(trenner) if trenner else (man, "", "")
    if not (vorn or hinten) or not all(z.isdigit() or z == " " for z in vorn + hinten):
        return Lesung(UNGUELTIG, meldung=f"„{roh}“ ist keine Zahl.")
    if (" " in vorn and not _gruppen_ok(vorn, True)) or (" " in hinten and not _gruppen_ok(hinten, False)):
        return Lesung(UNGUELTIG, meldung=(
            f"„{roh}“: Leerzeichen nur zwischen Dreiergruppen (Tausender), z. B. 2 000 000."))
    ziffern_vorn, ziffern_hinten = vorn.replace(" ", ""), hinten.replace(" ", "")
    try:
        wert = float(f"{vz}{ziffern_vorn or '0'}.{ziffern_hinten or '0'}" + (f"e{exp}" if exp else ""))
    except (ValueError, OverflowError):
        return Lesung(UNGUELTIG, meldung=f"„{roh}“ ist keine Zahl.")
    if not math.isfinite(wert):
        return Lesung(UNGUELTIG, meldung=f"„{roh}“ ist zu groß.")
    if ganz and wert != round(wert):
        return Lesung(UNGUELTIG, meldung=f"„{roh}“: hier ist eine ganze Zahl verlangt.")
    if (trenner == "." and exp is None and " " not in vorn
            and re.fullmatch(r"[1-9]\d{0,2}", vorn) and re.fullmatch(r"\d{3}", hinten)):
        alt = float(f"{vz}{vorn}{hinten}")
        return Lesung(FRAGE, wert, f"{vz}{vorn},{hinten} – gemeint {zahl_text(alt)}?", alt)
    return Lesung(GUELTIG, wert)


def ergaenzbar(text, ganz: bool = False) -> bool:
    """Ist eine ungueltige Eingabe nur unfertig - wird sie mit weiteren
    Ziffern gueltig („-“, „1e“, „2 0“, „2 000 0“)?

    Beim Tippen zeigt das Zahlenfeld solche Zwischenstaende neutral statt
    rot (24.09.2026: bei jeder negativen Last flackerten Rahmen und
    Meldung). „2.000.000“ bleibt rot: keine Ziffer macht es gueltig."""
    if lesen(text, ganz).status != UNGUELTIG:
        return False
    return any(lesen(f"{text}{z}", ganz).status in (GUELTIG, FRAGE) for z in ("0", "00", "000"))


def zahl_wert(text, ganz: bool = False) -> float:
    """Die Zahl einer Eingabe; ValueError, wenn sie leer oder ungueltig ist.

    Eine mehrdeutige Eingabe („1.000“) gilt hier als Dezimalzahl - wer sie
    anders behandeln muss (Lastspiele), fragt :func:`lesen`."""
    lesung = lesen(text, ganz)
    if lesung.status == LEER:
        raise ValueError("leer")
    if lesung.status == UNGUELTIG:
        raise ValueError(lesung.meldung)
    return float(lesung.wert)


def feldwert(wert, vorgabe=None, ganz: bool = False):
    """Eine Zahl aus einem Maskenwert, einer Liste oder einer Zelle (25.09.2026).

    Eine Zahl bleibt, wie sie ist (das Zahlenfeld hat sie schon gelesen und
    eine Mehrdeutigkeit bestaetigen lassen); leer oder None liefert
    ``vorgabe``; Text wird nach der Regel gelesen. Anders als
    :func:`zahl_wert` wird eine mehrdeutige Eingabe („1.000“) hier
    **abgewiesen**: an diesen Stellen gibt es keine zweite Bestaetigung, und
    bis 25.09.2026 wurde sie still 1 (``float(text.replace(",", "."))``,
    Werkstoffmaske f_y „1.000“ -> 1 N/mm²)."""
    if wert is None or isinstance(wert, bool):
        return vorgabe
    if isinstance(wert, (int, float, np.integer, np.floating)):
        return float(wert)
    les = lesen(wert, ganz)
    if les.status == LEER:
        return vorgabe
    if les.status == UNGUELTIG:
        raise ValueError(les.meldung)
    if les.status == FRAGE:
        roh = str(wert).strip()
        raise ValueError(f"„{roh}“ ist mehrdeutig ({les.meldung}) – "
                         f"{zahl_text(les.wert, tausender=False)} oder {zahl_text(les.vorschlag)} schreiben.")
    return float(les.wert)


#: Trenner einer Zahlenliste („1,5, 2“, „1; 2“, „1 2“): Semikolon,
#: Leerraum oder ein Komma, dem keine Ziffer folgt - „1,5“ bleibt eine Zahl
LISTENTRENNER = re.compile(r"[;\s]+|,(?![0-9])")


def zahlenliste(text) -> list:
    """Mehrere Zahlen in einem Textfeld (Stab-Versatz y, z; Ersatzachse;
    Gewichte), jede nach :func:`feldwert` (25.09.2026).

    In einer Liste trennen Leerzeichen die Eintraege - Tausender mit
    Leerzeichen gibt es hier nicht. Ein mehrdeutiger oder ungueltiger Eintrag
    wirft ValueError, statt still wegzufallen oder 1 zu werden."""
    teile = [t.strip() for t in LISTENTRENNER.split(str(text or "").strip()) if t.strip()]
    return [feldwert(t) for t in teile]


def zahl_text(x, tausender: bool = True, stellen: int = STELLEN) -> str:
    """Eine Zahl zum Lesen: Dezimalkomma, nie wissenschaftlich, Tausender mit
    Leerzeichen (``tausender``), bis ``stellen`` gueltige Ziffern.

    2e6 -> „2 000 000“, 1234.5678 -> „1 234,5678“, 1e-5 -> „0,00001“,
    0.1 + 0.2 -> „0,3“. Ohne ``tausender`` fuer Felder, die ein fremder
    Leser (Tabellenzelle, Formel) ohne Leerzeichen erwartet."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not math.isfinite(x):
        return "–"
    if x == 0.0:
        return "0"
    if x == round(x) and abs(x) < 1e15:
        s = str(int(round(x)))
    else:
        s = np.format_float_positional(x, precision=int(stellen), unique=False,
                                       fractional=False, trim="-")
    vz = "-" if s.startswith("-") else ""
    vorn, _, hinten = s.lstrip("-").partition(".")
    if tausender and len(vorn) > 3:
        vorn = f"{int(vorn):,}".replace(",", " ")
    return vz + vorn + ("," + hinten if hinten else "")
