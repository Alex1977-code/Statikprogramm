"""
Tabellen mit Filter, Sortierung, Export - und editierbar wie in RFEM.

Die Vorgabe verlangt (Kap. 3.6): Kopfzeilenfilter, Sortieren, Spalten ein- und
ausblenden, Synchronisation mit der Ansicht, Export nach Excel, CSV und in die
Zwischenablage, Eingabetabellen zum Tippen mit Formeln, Ergebnistabellen mit
Max- und Min-Zeile - und das alles auch bei sehr vielen Zeilen fluessig.

Der rechnende Teil steht bewusst in **reinen Funktionen** (``passt``,
``formel``, ``als_csv``), damit er ohne Oberflaeche geprueft werden kann; die
Qt-Klassen setzen nur darauf auf.

Filterausdruecke in der Kopfzeile:

    ====================  ==================================================
    ``> 0.9``             groesser als
    ``>= 0.9`` ``< 10``   entsprechend; auch ``<=`` und ``!=``
    ``= 3``               genau gleich (Zahl oder Text)
    ``1..5``              Bereich einschliesslich der Grenzen
    ``HEB``               Text kommt vor (ohne Ruecksicht auf Gross/Klein)
    ``!HEB``              Text kommt **nicht** vor
    ====================  ==================================================

In editierbaren Zellen darf gerechnet werden: ``= 2*3,5`` ergibt 7. Erlaubt
sind die vier Grundrechenarten, Klammern, Potenz und die Konstante pi - mehr
nicht, damit aus einer Tabellenzelle kein Programm wird.
"""
from __future__ import annotations

import ast
import csv
import io
import math
import operator
import re

import numpy as np
from dataclasses import dataclass, field

from PySide6 import QtCore, QtGui, QtWidgets

from . import design as dsg
from .. import zahlen as zl
from .. import elemente as _EL


# --------------------------------------------------------------------------
# Reine Funktionen: Filter, Formel, Export
# --------------------------------------------------------------------------
#: Vergleichszeichen des Kopfzeilenfilters
VERGLEICHE = (("<=", operator.le), (">=", operator.ge), ("!=", operator.ne),
              ("<", operator.lt), (">", operator.gt), ("=", operator.eq))


_PAAR = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)\s*/\s*"
                   r"(-?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)\s*$")


def _paar(wert):
    """„min / max“-Text einer Umhuellenden als zwei Zahlen, sonst None."""
    if not isinstance(wert, str):
        return None
    m = _PAAR.match(wert)
    if not m:
        return None
    return (float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", ".")))


def _zahl(x):
    """Der Wert als Zahl - oder None, wenn er keine ist."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    t = str(x).replace(",", ".").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


#: Ampel der Nachweistabellen (24.09.2026, Paket 2 des Oberflaechenplans):
#: bis AMPEL_GRENZE_GELB normal, darueber bis 1,0 gelb hinterlegt, ueber 1,0
#: rot und fett. Anlass: an der Stauwand stand D = 1,094 in der Tabelle
#: Ermuedung genauso da wie 0,035 - sicherheitsrelevant und leicht zu
#: uebersehen. „ueber 1,0“ wie die Status der Nachweise (util <= 1.0 ist
#: „erfüllt“), damit Farbe und Status nie verschiedenes sagen.
AMPEL_GRENZE_GELB = 0.9
AMPEL_ROT = "#c62828"
AMPEL_GELB = "#fff0b3"


def ampelstufe(wert) -> str:
    """„rot“, „gelb“ oder „“ fuer eine Zelle einer Ampelspalte.

    Zahlen: ueber 1,0 rot, ueber 0,9 bis 1,0 gelb. Text: rot, wenn „NICHT“
    darin steht (Status „NICHT erfüllt“) - gross geschrieben, damit „nicht
    geführt“ und „nicht gerechnet“ ohne Farbe bleiben: sie sind offen, nicht
    ueberschritten."""
    if isinstance(wert, str) and "NICHT" in wert:
        return "rot"
    z = _zahl(wert) if wert is not None else None
    if z is None or not math.isfinite(z):
        return ""
    if z > 1.0:
        return "rot"
    if z > AMPEL_GRENZE_GELB:
        return "gelb"
    return ""


def festkomma(x, nk: int) -> str:
    """Zahl als Tabellentext: *nk* Nachkommastellen, Dezimalkomma, nie ein
    Vorzeichen vor einer Null.

    Anlass (02.10.2026, Teilpaket 10a): ``f"{-0.0004:.2f}"`` schreibt „-0.00“ -
    der Wert ist auf null gerundet und hat dann kein Vorzeichen mehr. Gezeigt
    wird er als „0,00“. Was keine endliche Zahl ist (leere Kontaktflaeche:
    p = Fn / 0), steht als „–“ da und nicht als „nan“."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not math.isfinite(x):
        return "–"
    s = f"{x:.{max(0, int(nk))}f}"
    if s.startswith("-") and not s.strip("-0.,"):
        s = s[1:]
    return s.replace(".", ",")


def passt(wert, ausdruck: str) -> bool:
    """Erfuellt der Wert den Filterausdruck?"""
    a = (ausdruck or "").strip()
    if not a:
        return True
    if a.startswith("!"):
        return not passt(wert, a[1:].strip()) if a[1:].strip() else True
    bereich = re.fullmatch(r"\s*(-?[\d.,]+)\s*\.\.\s*(-?[\d.,]+)\s*", a)
    if bereich:
        z = _zahl(wert)
        lo, hi = _zahl(bereich.group(1)), _zahl(bereich.group(2))
        if z is None or lo is None or hi is None:
            return False
        return min(lo, hi) <= z <= max(lo, hi)
    for zeichen, fn in VERGLEICHE:
        if a.startswith(zeichen):
            rest = a[len(zeichen):].strip()
            z, r = _zahl(wert), _zahl(rest)
            if z is not None and r is not None:
                return bool(fn(z, r))
            # Textvergleich nur fuer = und !=
            if fn is operator.eq:
                return str(wert).strip().lower() == rest.lower()
            if fn is operator.ne:
                return str(wert).strip().lower() != rest.lower()
            return False
    return a.lower() in str(wert).lower()


#: erlaubte Rechenarten in einer Zelle
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def formel(text: str) -> float:
    """Eine Zelleneingabe auswerten. „= 2*3,5“ ergibt 7,0.

    Ohne führendes Gleichheitszeichen wird nur die Zahl gelesen. Erlaubt sind
    die Grundrechenarten, Klammern, Potenz und pi.
    """
    t = (text or "").strip()
    if not t:
        return 0.0
    if not t.startswith("="):
        z = _zahl(t)
        if z is None:
            raise ValueError(f"„{t}“ ist keine Zahl")
        return z
    quelle = t[1:].replace(",", ".").strip()

    def werten(k):
        if isinstance(k, ast.Constant):
            if isinstance(k.value, (int, float)) and not isinstance(k.value, bool):
                return float(k.value)
            raise ValueError("Nur Zahlen sind erlaubt")
        if isinstance(k, ast.Name):
            if k.id in ("pi", "PI"):
                return math.pi
            raise ValueError(f"„{k.id}“ ist in einer Zelle nicht erlaubt")
        if isinstance(k, ast.UnaryOp) and type(k.op) in _OPS:
            return _OPS[type(k.op)](werten(k.operand))
        if isinstance(k, ast.BinOp) and type(k.op) in _OPS:
            return _OPS[type(k.op)](werten(k.left), werten(k.right))
        raise ValueError("Nur + - * / ** und Klammern sind erlaubt")

    try:
        return float(werten(ast.parse(quelle, mode="eval").body))
    except ZeroDivisionError:
        raise ValueError("Teilung durch null")
    except (SyntaxError, TypeError) as ex:
        raise ValueError(f"Formel nicht lesbar: {ex}")


def _csv_zahl(x: float) -> str:
    """Eine Gleitkommazahl fuer CSV: Dezimalkomma, nie wissenschaftlich
    („1e-05“ wird „0,00001“, 02.10.2026, Teilpaket 10a)."""
    s = str(x)
    if "e" in s or "E" in s:
        s = np.format_float_positional(x, trim="-")
    return s.replace(".", ",")


def als_csv(kopf: list, zeilen: list, trenner: str = ";") -> str:
    """Tabelle als CSV-Text (deutsches Dezimalkomma, Semikolon als Trenner)."""
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=trenner, lineterminator="\n")
    schreiber.writerow(kopf)
    for z in zeilen:
        schreiber.writerow([_csv_zahl(x) if isinstance(x, float) else x for x in z])
    return puffer.getvalue()


def als_xlsx(pfad: str, blatt: str, kopf: list, zeilen: list) -> str:
    """Tabelle als Excel-Datei schreiben (eigener Schreiber, ohne Fremdpaket)."""
    from ..importers.xlsx_reader import write_xlsx
    write_xlsx(pfad, {blatt[:31] or "Tabelle": [list(kopf)] + [list(z) for z in zeilen]})
    return pfad


def zahlen_wandeln(zeilen: list, spalten: list) -> list:
    """In Zahlenspalten aus „12,5“ eine 12.5 machen.

    Die Ergebnisse kommen aus dem Rechenteil teils schon als Text. Damit
    Sortieren, Filtern und der Excel-Export mit echten Zahlen arbeiten, wird
    hier zurueckverwandelt, was sich zurueckverwandeln laesst; alles andere
    („-“, „nicht gefuehrt“) bleibt stehen.
    """
    arten = [sp.art for sp in spalten]
    out = [list(z) for z in zeilen]
    # Nur Text muss gewandelt werden - was schon Zahl ist, bleibt ungeprueft.
    # Bei 490 000 Zeilen mit je acht Zahlen kostete die Pruefung jeder Zelle
    # sonst zehn Sekunden.
    for k, art in enumerate(arten):
        if art not in ("zahl", "ganz"):
            continue
        ganz = art == "ganz"
        for neu in out:
            if k < len(neu):
                w = neu[k]
                if w.__class__ is str:
                    x = _zahl(w)
                    if x is not None:
                        neu[k] = int(x) if ganz else x
    return out


def _schluessel_wert(x):
    """Zahl und Text auf einen Nenner bringen: 3, „3“ und 3.0 sind dasselbe."""
    z = _zahl(x)
    return z if z is not None else str(x)


def kennwerte(zeilen: list, spalten: list) -> tuple:
    """Max- und Min-Zeile einer Ergebnistabelle (nur ueber Zahlenspalten).

    Spaltenweise mit numpy: die Zellenschleife (_zahl je Zelle) kostete am
    Drehlager 44 s je Modellstand fuer 1,8 Mio. Elementzeilen (12.09.2026);
    Spalten, die sich nicht in einem Zug wandeln lassen, gehen den alten Weg.

    Textspalten bleiben leer, auch wenn ihr Text wie eine Zahl aussieht: bis
    zur Nachbesserung vom 03.10.2026 (10c) stand unter „Komb.“ bei Lastfaellen
    „1“ und „2“ als Max „2.0“ - eine Zahl, die nichts bedeutet.
    """
    if not zeilen:
        return [], []
    hoch, tief = ["Max"], ["Min"]
    n_sp = len(spalten)
    breit = all(len(r) >= n_sp for r in zeilen) if len(zeilen) <= 1000 else (len(zeilen[0]) >= n_sp)
    for k in range(1, n_sp):
        if spalten[k].art not in ("zahl", "ganz"):
            hoch.append("")
            tief.append("")
            continue
        werte = None
        if breit:
            try:
                col = np.array([r[k] for r in zeilen], dtype=object)
                if col.dtype == object and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                               for x in col[:200]):
                    w = col.astype(float)
                    w = w[np.isfinite(w)]
                    werte = w if len(w) else None
                    if werte is not None:
                        hoch.append(float(werte.max()))
                        tief.append(float(werte.min()))
                        continue
            except (ValueError, TypeError, IndexError):
                werte = None
        werte = [z for z in (_zahl(r[k]) for r in zeilen if k < len(r)) if z is not None]
        hoch.append(max(werte) if werte else "")
        tief.append(min(werte) if werte else "")
    return hoch, tief


# --------------------------------------------------------------------------
# Qt-Teil
# --------------------------------------------------------------------------
@dataclass
class Spalte:
    """Eine Spalte der Tabelle."""
    name: str
    einheit: str = ""
    art: str = "text"           # text | zahl | ganz | wahl
    nachkomma: int = 3
    editierbar: bool = False
    werte: list = field(default_factory=list)
    hinweis: str = ""
    #: fn(zeile) -> Liste der Wahlwerte, wenn sie von der Zeile oder vom
    #: Modellstand abhaengen (Werkstoffe, Querschnitte, Dicken)
    werte_fn: object = None
    #: Ampel in Nachweistabellen (Ausnutzung, D, Status): siehe ampelstufe
    ampel: bool = False
    #: Schluessel -> Klartext einer Textspalte („beam“ -> „Balken 3D“). Die
    #: Zeilen behalten den Schluessel (Wahllisten und Rueckrufe lesen ihn);
    #: gezeigt, sortiert, gefiltert und exportiert wird der Klartext
    #: (02.10.2026, Teilpaket 10a). Was nicht im Verzeichnis steht, bleibt wie es ist.
    klartext: dict = None
    #: Die Zelle nennt ein Ergebnis (die massgebende Kombination): ein Klick
    #: darauf zeigt es (Datentabelle.ergebnis_gewaehlt; 03.10.2026, Teilpaket 10c)
    ergebnis: bool = False
    #: Die Summenzeile Σ addiert diese Spalte (Datentabelle.summe_setzen, 10c)
    summe: bool = False

    def text_von(self, wert):
        """Der Klartext zu *wert* - oder *wert* selbst."""
        if self.klartext:
            return self.klartext.get(str(wert), wert)
        return wert

    def wahlwerte(self, zeile=None) -> list:
        if self.werte_fn is not None:
            try:
                return [str(v) for v in self.werte_fn(zeile)]
            except Exception:               # noqa: BLE001
                return [str(v) for v in self.werte]
        return [str(v) for v in self.werte]

    def kopf(self) -> str:
        return f"{self.name} [{self.einheit}]" if self.einheit else self.name


#: Zellfarben einer Eingabetabelle (02.10.2026, Teilpaket 10a): wo man tippen
#: darf, steht reines Weiss, wo nicht, ein helles Grau. Vorher waren beide durch
#: die Zebrastreifen der Zeilen gemischt und die Bearbeitbarkeit nicht zu sehen.
#: Die Farben stehen mit den uebrigen der Oberflaeche in design.FARBEN.
ZELLE_EDIT = dsg.FARBEN["zelle_edit"]
ZELLE_FEST = dsg.FARBEN["zelle_fest"]


#: Klartext der Schluessel, die Tabellen heute noch zeigten (02.10.2026,
#: Teilpaket 10a). Gespeichert und gerechnet wird weiter mit dem Schluessel.
#: Elementarten aus dem Elementverzeichnis, ohne die Klammer **am Ende** mit den
#: Verfahrensangaben: „Balken 3D (12 FHG, Timoshenko-Schub …)“ wird „Balken 3D“.
def _elementart_texte() -> dict:
    """Kurzer Klartext je Elementart - und jeder Klartext nur einmal.

    Eine Klammer mitten im Namen bleibt stehen: „Keil (Prisma), linear“ und
    „Keil (Prisma), quadratisch“ duerfen nicht beide „Keil“ heissen (erste
    Fassung vom 02.10.2026 schnitt am ersten „ (“ ab). Faellt trotzdem ein
    Kurzname auf zwei Arten, etwa bei einer neuen Elementart, steht fuer beide
    der volle Name aus dem Verzeichnis."""
    kurz = {t: re.sub(r"\s*\([^)]*\)$", "", a.name) for t, a in _EL.ELEMENTE.items()}
    haeufigkeit: dict = {}
    for k in kurz.values():
        haeufigkeit[k] = haeufigkeit.get(k, 0) + 1
    return {t: (k if haeufigkeit[k] == 1 else _EL.ELEMENTE[t].name) for t, k in kurz.items()}


ELEMENTART_TEXT = _elementart_texte()
LINIENART_TEXT = {"polyline": "Polylinie", "arc": "Bogen", "circle": "Kreis",
                  "ellipse": "Ellipse", "spline": "Spline", "parabola": "Parabel"}
QUERSCHNITTSART_TEXT = {"I": "I-Profil", "I2": "Doppel-T unsymmetrisch", "U": "U-Profil",
                        "T": "T-Profil", "L": "Winkel", "Z": "Z-Profil", "Hut": "Hutprofil",
                        "Kreuz": "Kreuzprofil", "RHS": "Rechteckhohlprofil (RHS)",
                        "CHS": "Rohr (CHS)", "rect": "Rechteck", "circle": "Kreis",
                        "poly": "Polygon", "composite": "zusammengesetzt", "free": "frei"}
#: Art einer Kontaktbedingung im Ergebnis (contact.Constraint.kind)
KONTAKTART_TEXT = {"support": "Einseitiges Lager", "gap": "Spaltelement",
                   "surface": "Kontaktfläche", "dof": "Lagerbedingung (Verschiebung)",
                   "dof_rot": "Lagerbedingung (Drehung)"}
#: Bezugssystem einer Stab- oder Linienlast
LASTSYSTEM_TEXT = {"global": "global", "local": "lokal"}


#: Rollen und Ausrichtungen als Konstanten fuer TabellenModell.data und
#: flags, die Qt fuer jede Zelle beim Messen und Zeichnen mehrfach aufruft. Der
#: Zugriff ueber den Kurznamen (QtCore.Qt.DisplayRole) geht in PySide6 ueber
#: einen Rueckfall und kostet 2,1 µs, ueber die Aufzaehlung 0,1 µs, der Test
#: „rolle in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole)“ 4,4 µs statt 0,03 µs
#: (gemessen 03.10.2026, Teilpaket 10c). Ein Wechsel auf die Umhuellende am
#: Drehlager (Stabkraefte mit 64 Zeilen und 18 Spalten) kostete ohne
#: Neuzeichnen 0,51 bis 0,65 s, davon 0,26 s in data(); mit den Konstanten
#: 0,24 bis 0,37 s (am Stand 7a4a895, Stabkraefte dort leer: 0,39 bis 0,50 s;
#: scratchpad/c10c_zeit.py).
_ROLLE = QtCore.Qt.ItemDataRole
R_ANZEIGE, R_EDIT, R_USER = _ROLLE.DisplayRole, _ROLLE.EditRole, _ROLLE.UserRole
R_VORDER, R_HINTER, R_SCHRIFT = _ROLLE.ForegroundRole, _ROLLE.BackgroundRole, _ROLLE.FontRole
R_TIP, R_AUSRICHTUNG = _ROLLE.ToolTipRole, _ROLLE.TextAlignmentRole
_ROLLEN_TEXT = (R_ANZEIGE, R_EDIT)
_ROLLEN_FARBE = (R_VORDER, R_HINTER, R_SCHRIFT)
_ROLLEN_VERWEIS = (R_VORDER, R_SCHRIFT, R_TIP)
#: alle Rollen, auf die data() etwas sagt - die uebrigen gleich mit None
_ROLLEN_DATEN = frozenset(_ROLLEN_TEXT + _ROLLEN_FARBE + (R_TIP, R_AUSRICHTUNG, R_USER))
_AUSRICHTUNG = QtCore.Qt.AlignmentFlag
_RECHTS = int(_AUSRICHTUNG.AlignRight | _AUSRICHTUNG.AlignVCenter)
_FLAGS = QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
_FLAGS_EDIT = _FLAGS | QtCore.Qt.ItemFlag.ItemIsEditable


class TabellenModell(QtCore.QAbstractTableModel):
    """Zeilen und Spalten; Aenderungen laufen ueber einen Rueckruf."""

    #: (Zeile, Spalte, neuer Wert) - der Rueckruf liefert True, wenn uebernommen
    geaendert = QtCore.Signal(int, int, object)
    #: Eine Eingabe wurde nicht uebernommen - warum (24.09.2026: vorher
    #: schluckte die Zelle „2.000.000“ ohne ein Wort)
    meldung = QtCore.Signal(str)

    def __init__(self, spalten: list, zeilen: list = None, parent=None):
        super().__init__(parent)
        self.spalten = list(spalten)
        self.zeilen = [list(z) for z in (zeilen or [])]
        self.aendern = None          # fn(zeile, spalte, wert) -> bool
        #: fn() -> einheiten.Einheiten oder None. Die Zeilen stehen in den
        #: Grundeinheiten der Spalten (kN, kNm, m, mm, N/mm² ...); gezeigt,
        #: gefiltert, bearbeitet und exportiert wird in den eingestellten
        #: Einheiten mit deren Nachkommastellen.
        self.einheiten_quelle = None
        #: Zellen nach Bearbeitbarkeit einfaerben (nur Eingabetabellen, siehe
        #: Datentabelle: gesetzt, wenn mindestens eine Spalte editierbar ist)
        self.zellfarben = False
        #: Zeilen in der Reihenfolge, in der sie gesetzt wurden - damit die
        #: Modellreihenfolge nach einer Spaltensortierung wiederkommt
        self._ur = None
        #: Verweise auf Ergebnisse (Spalte.ergebnis, herkunft): Namen, die ein
        #: eigenes Ergebnis haben - nur sie sehen aus wie ein Verweis und
        #: schalten beim Klick; None: jeder Name. Die Fusszeile zeigt nie
        #: Verweise (verweise False). Nachbesserung 10c, 03.10.2026.
        self.ergebnisnamen = None
        self.verweise = True
        #: {(Schluessel der Zeile, Spalte): Name des massgebenden Ergebnisses}
        #: fuer Zahlenzellen, die eines haben (Auflager einer Umhuellenden)
        self.herkunft: dict = {}

    # -- Einheiten -------------------------------------------------------
    def anzeige(self, k: int) -> tuple:
        """(Faktor Grundeinheit -> Anzeige, Einheitentext, Nachkommastellen)
        der Spalte *k*."""
        sp = self.spalten[k]
        e = self.einheiten_quelle() if self.einheiten_quelle is not None else None
        if e is None or sp.art != "zahl":
            return 1.0, sp.einheit, sp.nachkomma
        return e.anzeige(sp.einheit, sp.nachkomma)

    def kopf(self, k: int) -> str:
        sp = self.spalten[k]
        _f, einheit, _nk = self.anzeige(k)
        return f"{sp.name} [{einheit}]" if einheit else sp.name

    def angezeigt(self, k: int, wert):
        """Zahlenwert der Spalte *k* in der Anzeigeeinheit (Text bleibt Text;
        ein „min / max“-Paar wird als Paar umgerechnet)."""
        if self.spalten[k].art != "zahl":
            return self.spalten[k].text_von(wert)
        if isinstance(wert, (int, float)) and not isinstance(wert, bool):
            f, _e, nk = self.anzeige(k)
            # + 0.0: aus „-0.0“ wird „0.0“ (auch ein auf null gerundeter Wert)
            return round(float(wert) * f, int(nk) + 6) + 0.0
        paar = _paar(wert)
        if paar is not None:
            f, _e, nk = self.anzeige(k)
            return " / ".join(festkomma(x * f, nk) for x in paar)
        return wert

    def _export_wert(self, k: int, w):
        """Ein Wert fuer Zwischenablage, CSV und Excel: in der Anzeigeeinheit, eine
        nicht endliche Zahl (nan, inf) als **leeres Feld**. Die Anzeige zeigt dafuer
        „–“; im Export stoert ein Text in einer Zahlenspalte (Excel liest sie dann
        nicht mehr als Zahlen), und ``nan`` als Zahl in einer xlsx-Zelle ist ungueltig."""
        x = self.angezeigt(k, w) if k < len(self.spalten) else w
        if isinstance(x, float) and not math.isfinite(x):
            return ""
        return x

    def zeilen_angezeigt(self, zeilen: list) -> list:
        """Zeilen in Anzeigeeinheiten - fuer Zwischenablage, CSV und Excel."""
        return [[self._export_wert(k, w) for k, w in enumerate(z)] for z in zeilen]

    def einheiten_aktualisieren(self):
        """Nach geaenderten Einheiten Kopf und Zellen neu zeichnen."""
        if self.columnCount():
            self.headerDataChanged.emit(QtCore.Qt.Horizontal, 0, self.columnCount() - 1)
        if self.rowCount() and self.columnCount():
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(self.rowCount() - 1, self.columnCount() - 1))

    # -- Qt --------------------------------------------------------------
    def rowCount(self, _eltern=QtCore.QModelIndex()) -> int:
        return len(self.zeilen)

    def columnCount(self, _eltern=QtCore.QModelIndex()) -> int:
        return len(self.spalten)

    def headerData(self, i, richtung, rolle=QtCore.Qt.DisplayRole):
        if rolle == QtCore.Qt.DisplayRole:
            if richtung == QtCore.Qt.Horizontal:
                return self.kopf(i)
            return str(i + 1)
        if rolle == QtCore.Qt.ToolTipRole and richtung == QtCore.Qt.Horizontal:
            return self.spalten[i].hinweis or self.kopf(i)
        return None

    def data(self, index, rolle=R_ANZEIGE):
        # Rollen ueber die Konstanten R_… vor der Klasse: je Zelle fragt Qt
        # hier sieben, acht Rollen ab, und der Kurzname QtCore.Qt.DisplayRole
        # kostet in PySide6 je Zugriff 2,1 µs statt 0,1 µs (10c)
        if rolle not in _ROLLEN_DATEN or not index.isValid():
            return None
        z, k = index.row(), index.column()
        wert = self.zeilen[z][k] if k < len(self.zeilen[z]) else ""
        if rolle in _ROLLEN_TEXT:
            sp = self.spalten[k]
            if sp.art == "zahl" and isinstance(wert, (int, float)):
                f, _e, nk = self.anzeige(k)
                if rolle == R_EDIT:
                    # Volle Genauigkeit mit Komma (24.09.2026): „:g“ kuerzte
                    # auf sechs Stellen - F2 und Enter machten aus 1234,5678 m
                    # still 1234,57 m (gui_analyse/unten/editrolle2.py)
                    return zl.zahl_text(float(wert) * f, tausender=False)
                return festkomma(float(wert) * f, nk)
            if sp.art == "zahl" and rolle == R_ANZEIGE and _paar(wert) is not None:
                # auch ohne Umrechnung neu geschrieben: der Rechenteil liefert
                # „-0.00 / 1.23“ mit Punkt (Auflager der Umhuellenden)
                f, _e, nk = self.anzeige(k)
                return " / ".join(festkomma(x * f, nk) for x in _paar(wert))
            if rolle == R_EDIT:
                return str(wert)
            if sp.klartext:
                return str(sp.text_von(wert))
            if sp.art == "ganz" and isinstance(wert, (int, float)):
                return str(int(wert))
            return str(wert)
        if rolle in _ROLLEN_VERWEIS and self.verweise and (self.spalten[k].ergebnis or self.herkunft):
            # Die massgebende Kombination sieht aus wie ein Verweis, wo ein
            # Klick sie zeigt (10c) - sonst ahnt niemand, dass die Zelle mehr
            # kann als die uebrigen. Ein Name ohne eigenes Ergebnis (die
            # Alternative „EK1 [4]“) bleibt gewoehnlicher Text.
            name = self.ergebnisname(z, k)
            if name:
                verweis = self.ist_verweis(name)
                if rolle == R_TIP:
                    if self.spalten[k].ergebnis:
                        return (f"Klick zeigt das Ergebnis {name} – im Bild und in den Tabellen"
                                if verweis else None)
                    return (f"maßgebend: {name}"
                            + (" – ein Klick zeigt dieses Ergebnis" if verweis else ""))
                if verweis and rolle == R_VORDER:
                    return QtGui.QBrush(QtGui.QColor(dsg.FARBEN["akzent"]))
                if verweis and rolle == R_SCHRIFT:
                    f = QtGui.QFont()
                    f.setUnderline(True)
                    return f
        if rolle in _ROLLEN_FARBE:
            # Nur die Anzeige: Zwischenablage, CSV und Excel lesen die Zeilen
            # und bleiben ohne Farbe (24.09.2026)
            if not self.spalten[k].ampel:
                if rolle == R_HINTER and self.zellfarben:
                    # Eingabetabelle: weiss = hier darf man tippen, grau = nicht
                    return QtGui.QBrush(QtGui.QColor(
                        ZELLE_EDIT if self.spalten[k].editierbar else ZELLE_FEST))
                return None
            stufe = ampelstufe(wert)
            if stufe == "rot":
                if rolle == R_VORDER:
                    return QtGui.QBrush(QtGui.QColor(AMPEL_ROT))
                if rolle == R_SCHRIFT:
                    f = QtGui.QFont()
                    f.setBold(True)
                    return f
            elif stufe == "gelb" and rolle == R_HINTER:
                return QtGui.QBrush(QtGui.QColor(AMPEL_GELB))
            return None
        if rolle == R_AUSRICHTUNG and self.spalten[k].art != "text":
            return _RECHTS
        if rolle == R_USER:
            # Sortieren, Filtern und Markieren in der Anzeigeeinheit
            if self.spalten[k].art in ("zahl", "ganz"):
                z = _zahl(wert)
                return wert if z is None else self.angezeigt(k, z)
            return self.spalten[k].text_von(wert)
        return None

    def ergebnisname(self, z: int, k: int) -> str:
        """Der Name des Ergebnisses, auf das die Zelle (z, k) verweist - der
        Text einer Spalte „Komb.“ oder die Herkunft einer Zahlenzelle; „“
        ohne Verweis."""
        zeile = self.zeilen[z] if 0 <= z < len(self.zeilen) else ()
        if self.spalten[k].ergebnis:
            name = str(zeile[k]).strip() if k < len(zeile) else ""
        elif self.herkunft and zeile:
            name = str(self.herkunft.get((_schluessel_wert(zeile[0]), k), ""))
        else:
            return ""
        return "" if name in ("–", "-") else name

    def ist_verweis(self, name: str) -> bool:
        """Hat *name* ein eigenes Ergebnis, das ein Klick zeigen kann?"""
        return bool(name) and self.verweise and (self.ergebnisnamen is None
                                                 or name in self.ergebnisnamen)

    def flags(self, index):
        if index.isValid() and self.spalten[index.column()].editierbar:
            return _FLAGS_EDIT
        return _FLAGS

    def setData(self, index, wert, rolle=QtCore.Qt.EditRole) -> bool:
        if rolle != QtCore.Qt.EditRole or not index.isValid():
            return False
        z, k = index.row(), index.column()
        sp = self.spalten[k]
        if str(wert) == str(self.data(index, QtCore.Qt.EditRole)):
            # Zelle geoeffnet und ohne Aenderung verlassen: nichts tun - kein
            # Rueckgaengig-Schritt, keine verworfenen Ergebnisse (24.09.2026)
            return False
        text = str(wert).strip()
        if sp.art in ("zahl", "ganz") and text and not text.startswith("="):
            # Dieselbe Regel wie in Masken und Dialogen (statik3d/zahlen.py):
            # „2.000.000“ ist ungueltig, „33.000“ mehrdeutig - beides wird
            # nicht still zu einer anderen Zahl
            les = zl.lesen(text, sp.art == "ganz")
            if les.status == zl.UNGUELTIG:
                self.meldung.emit(f"{sp.name}: {les.meldung} Nicht übernommen.")
                return False
            if les.status == zl.FRAGE:
                self.meldung.emit(f"{sp.name}: {les.meldung} Nicht übernommen – bitte "
                                  f"{zl.zahl_text(les.wert, tausender=False)} oder "
                                  f"{zl.zahl_text(les.vorschlag)} schreiben.")
                return False
        try:
            if sp.art not in ("zahl", "ganz"):
                neu = str(wert)
            elif not text or text.startswith("="):
                neu = formel(text)          # leer = 0 wie bisher, „= 2*3,5“
            else:
                neu = zl.zahl_wert(text, sp.art == "ganz")
        except ValueError as ex:
            if sp.art in ("zahl", "ganz"):
                self.meldung.emit(f"{sp.name}: {ex} Nicht übernommen.")
            return False
        if sp.art == "ganz":
            neu = int(round(neu))
        elif sp.art == "zahl":
            # eingegeben in der Anzeigeeinheit, gespeichert in der Grundeinheit
            f, _e, _nk = self.anzeige(k)
            if f and f != 1.0:
                neu = float(neu) / f
        if self.aendern is not None and not self.aendern(z, k, neu):
            return False
        while len(self.zeilen[z]) <= k:
            self.zeilen[z].append("")
        self.zeilen[z][k] = neu
        self.dataChanged.emit(index, index)
        self.geaendert.emit(z, k, neu)
        return True

    # -- Daten -----------------------------------------------------------
    def setzen(self, zeilen: list):
        self.beginResetModel()
        self.zeilen = [list(z) for z in zeilen]
        self._ur = list(self.zeilen)
        self._index = None
        self._sortieren()
        self.endResetModel()

    #: (Spalte, Richtung) der aktuellen Sortierung - Spalte -1: unsortiert
    sortierung = (-1, QtCore.Qt.AscendingOrder)

    def sortieren(self, spalte: int, richtung=QtCore.Qt.AscendingOrder):
        """Zeilen nach einer Spalte ordnen - einmal in Python statt ueber
        Millionen lessThan-Aufrufe des Proxys (490 000 Zeilen: Sekunden statt
        Minuten). Zahlen der Groesse nach vor dem Text, der ohne Ruecksicht auf
        Gross- und Kleinschreibung. Markierungen wandern mit ihren Zeilen."""
        self.sortierung = (int(spalte), richtung)
        folge = self._sortfolge()
        if folge is None:
            # Spalte -1 („nicht sortiert“): die Reihenfolge wiederherstellen,
            # in der die Zeilen gesetzt wurden - die Modellreihenfolge
            ur = self._ur
            if int(spalte) >= 0 or ur is None or len(ur) != len(self.zeilen):
                return
            pos = {id(z): i for i, z in enumerate(self.zeilen)}
            if len(pos) != len(ur) or any(id(z) not in pos for z in ur):
                return
            folge = [pos[id(z)] for z in ur]
        self.layoutAboutToBeChanged.emit()
        alt = self.persistentIndexList()
        self.zeilen = [self.zeilen[i] for i in folge]
        self._index = None
        if alt:
            neu_von_alt = {a: n for n, a in enumerate(folge)}
            self.changePersistentIndexList(
                alt, [self.index(neu_von_alt.get(i.row(), i.row()), i.column()) for i in alt])
        self.layoutChanged.emit()

    def _sortfolge(self):
        """Zeilennummern in sortierter Reihenfolge - None, wenn nichts zu tun ist."""
        k, richtung = self.sortierung
        if k < 0 or k >= len(self.spalten) or not self.zeilen:
            return None

        zeilen = self.zeilen
        absteigend = richtung == QtCore.Qt.DescendingOrder
        # Absteigend stehen Zeilen ohne Zahl trotzdem hinten, wie in Excel:
        # die Nachweistabellen starten absteigend nach Ausnutzung, und ein
        # „–“ (nicht gefuehrt) oder eine leere Zelle (nicht gerechnet) stand
        # sonst ueber dem groessten Wert (24.09.2026). Dafuer tauscht die
        # Gruppenkennung - eine einzige Sortierung wie bisher; zwei Listen
        # mit Tupeln je Zeile kosteten an 2 Mio. Zeilen rund die Haelfte mehr
        # Zeit und ein Drittel mehr Speicher (Gegenpruefung 25.09.2026).
        g_zahl, g_text = (1, 0) if absteigend else (0, 1)

        # Klartext-Spalte: nach dem gezeigten Wort sortieren. Ohne Klartext kostet
        # das je Zeile nur die Abfrage einer lokalen Variablen (bei 2 Mio.
        # Zeilen zaehlt jeder Aufruf).
        klar = self.spalten[k].klartext

        def schluessel(r):
            z = zeilen[r]
            wert = z[k] if k < len(z) else ""
            if klar:
                wert = klar.get(str(wert), wert)
            zahl = _zahl(wert)
            if zahl is not None:
                return (g_zahl, zahl, [])
            # Kein reiner Zahlwert: dann natuerlich sortieren, damit „V2“ vor
            # „V10“ steht und nicht dahinter.
            return (g_text, 0.0, dsg.natuerlich(wert))

        return sorted(range(len(zeilen)), key=schluessel, reverse=absteigend)

    def _sortieren(self):
        folge = self._sortfolge()
        if folge is not None:
            self.zeilen = [self.zeilen[i] for i in folge]

    def zeile_zu(self, schluessel) -> list:
        """Alle Zeilen, deren erste Spalte diesen Schluessel traegt - ueber ein
        Verzeichnis, das beim ersten Zugriff entsteht. Bei 490 000 Zeilen kostet
        die Suche sonst je Klick Sekunden."""
        if getattr(self, "_index", None) is None:
            idx: dict = {}
            for r, z in enumerate(self.zeilen):
                if z:
                    idx.setdefault(_schluessel_wert(z[0]), []).append(r)
            self._index = idx
        return self._index.get(_schluessel_wert(schluessel), [])


class WahlDelegate(QtWidgets.QStyledItemDelegate):
    """Aufklappliste fuer Spalten mit art == "wahl" (Werkstoff, Querschnitt,
    Dicke, Nahtart …); alle anderen Spalten bekommen den Standard-Editor."""

    def __init__(self, tabelle):
        super().__init__(tabelle.view)
        self.tabelle = tabelle

    def initStyleOption(self, option, index):
        """Eine markierte Zelle mit Zellfarbe zeigt die Auswahlfarbe der Palette.

        Die Zellfarben der Eingabetabellen (weiss, grau) und das Gelb der Ampel
        kommen als BackgroundRole aus dem Modell und landen als
        ``option.backgroundBrush`` in der Stiloption. Der Windows-11-Stil legt
        die Auswahl dann nur als schwachen Hauch und schmalen Strich am linken
        Zellrand darueber: am Desktop sah die markierte Zeile aus wie die
        anderen, mit und ohne Fokus (Sichtpruefung 02.10.2026, zweimal - auch
        mit geleerter Brush). Darum wird die Zellfarbe einer markierten Zelle
        ausdruecklich durch die Auswahlfarbe der Palette ersetzt (aktiv oder,
        ohne Fokus, inaktiv) und die Schrift durch die Auswahlschrift - wie die
        Zeilen ohne Zellfarbe es vorher zeigten. Zellen ohne Zellfarbe (Tabellen
        mit Zebrastreifen) zeichnet der Stil weiter selbst."""
        super().initStyleOption(option, index)
        if (option.state & QtWidgets.QStyle.StateFlag.State_Selected
                and option.backgroundBrush.style() != QtCore.Qt.BrushStyle.NoBrush):
            gruppe = (QtGui.QPalette.ColorGroup.Active
                      if option.state & QtWidgets.QStyle.StateFlag.State_Active
                      else QtGui.QPalette.ColorGroup.Inactive)
            option.backgroundBrush = option.palette.brush(gruppe, QtGui.QPalette.ColorRole.Highlight)
            schrift = option.palette.brush(gruppe, QtGui.QPalette.ColorRole.HighlightedText)
            option.palette.setBrush(QtGui.QPalette.ColorRole.Text, schrift)
            option.palette.setBrush(QtGui.QPalette.ColorRole.WindowText, schrift)

    def _spalte(self, index):
        q = self.tabelle.filter.mapToSource(index)
        sp = self.tabelle.modell.spalten[q.column()]
        zeile = self.tabelle.modell.zeilen[q.row()] if q.row() < len(self.tabelle.modell.zeilen) else None
        return sp, zeile

    def createEditor(self, parent, option, index):
        sp, zeile = self._spalte(index)
        if sp.art != "wahl":
            return super().createEditor(parent, option, index)
        cb = QtWidgets.QComboBox(parent)
        cb.addItems(sp.wahlwerte(zeile))
        cb.setEditable(False)
        return cb

    def setEditorData(self, editor, index):
        if isinstance(editor, QtWidgets.QComboBox):
            editor.setCurrentText(str(index.data(QtCore.Qt.EditRole) or ""))
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QtWidgets.QComboBox):
            model.setData(index, editor.currentText(), QtCore.Qt.EditRole)
            return
        super().setModelData(editor, model, index)


class Filtermodell(QtCore.QSortFilterProxyModel):
    """Kopfzeilenfilter je Spalte, dazu die Sortierung."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ausdruecke: dict[int, str] = {}
        self.setSortRole(QtCore.Qt.UserRole)

    def setze_filter(self, spalte: int, ausdruck: str):
        if ausdruck.strip():
            self.ausdruecke[spalte] = ausdruck
        else:
            self.ausdruecke.pop(spalte, None)
        self.invalidateFilter()

    def leeren(self):
        self.ausdruecke.clear()
        self.invalidateFilter()

    def sort(self, spalte: int, richtung=QtCore.Qt.AscendingOrder):
        """Sortiert wird im Quellmodell (ein Python-Sort), der Proxy bleibt
        unsortiert - so fragt Qt nicht fuer jeden Vergleich zweimal data() ab."""
        q = self.sourceModel()
        if q is not None and hasattr(q, "sortieren"):
            q.sortieren(spalte, richtung)
            # Immer aufsteigend: bei Spalte -1 und absteigend kehrt Qt die
            # Quellfolge um - die absteigend sortierte Quelle stand so
            # sichtbar wieder aufsteigend da, der rote Wert unten
            # (Gegenpruefung 25.09.2026, seit dem Sortieren in der Quelle)
            super().sort(-1, QtCore.Qt.AscendingOrder)
            return
        super().sort(spalte, richtung)

    def lessThan(self, links, rechts) -> bool:
        """Zahlen der Groesse nach, Text ohne Ruecksicht auf Gross- und
        Kleinschreibung. Was keine Zahl ist, steht hinter den Zahlen."""
        a = self.sourceModel().data(links, QtCore.Qt.UserRole)
        b = self.sourceModel().data(rechts, QtCore.Qt.UserRole)
        za, zb = _zahl(a), _zahl(b)
        if za is not None and zb is not None:
            return za < zb
        if za is not None:
            return True
        if zb is not None:
            return False
        return str(a).lower() < str(b).lower()

    def filterAcceptsRow(self, zeile, eltern) -> bool:
        q = self.sourceModel()
        for k, a in self.ausdruecke.items():
            if k >= q.columnCount():
                continue
            wert = q.data(q.index(zeile, k, eltern), QtCore.Qt.UserRole)
            if not passt(wert, a):
                return False
        return True


def zeilenbereiche(zeilen) -> list:
    """Zeilennummern zu zusammenhaengenden Bereichen (erste, letzte), sortiert,
    ohne Doppelte: [5, 1, 2, 3, 9, 10] -> [(1, 3), (5, 5), (9, 10)]."""
    aus: list = []
    for r in sorted({int(z) for z in zeilen}):
        if aus and r == aus[-1][1] + 1:
            aus[-1][1] = r
        else:
            aus.append([r, r])
    return [(a, b) for a, b in aus]


class Datentabelle(QtWidgets.QWidget):
    """Tabelle mit Filterzeile auf Knopfdruck, Sortierung, Spaltenwahl und Export."""

    #: Zeile angeklickt - der erste Spaltenwert (meist die Objektnummer)
    zeile_gewaehlt = QtCore.Signal(object)
    #: mehrere Zeilen markiert (Umschalt/Strg): die Werte der ersten Spalte
    zeilen_gewaehlt = QtCore.Signal(list)
    #: Zeilenzahl, Filter oder Filterzeile geaendert - der untere Bereich zieht
    #: daran den Zaehler am Reiter und den Knopf Filter nach (03.10.2026, 10b)
    stand_geaendert = QtCore.Signal()
    #: Klick auf eine Zelle, die auf ein Ergebnis verweist (Spalte.ergebnis
    #: oder herkunft): sein Name (03.10.2026, Teilpaket 10c). Gesendet vor
    #: zeile_gewaehlt, damit beides zusammen nur einmal zeichnet
    ergebnis_gewaehlt = QtCore.Signal(str)
    #: Ein Satz fuer die Statuszeile (etwa: eine Sortierung entfaellt mit
    #: ihrer Spalte, spalten_setzen)
    hinweis = QtCore.Signal(str)
    #: Hoehe der Filterzeile
    FILTER_HOEHE = 22
    #: Breiter wird keine Spalte aus ihrem Inhalt (eine Elementliste mit
    #: tausend Nummern bekommt sonst eine Spalte ueber die ganze Wand)
    SPALTE_MAX = 360
    #: Max und Min erst ab so vielen Zeilen (03.10.2026, Teilpaket 10b): bei
    #: zwei, drei Zeilen liest man das Groesste selbst ab, und die beiden
    #: Zeilen (46 px) sind dort so hoch wie die Tabelle selbst
    KENNWERTE_AB = 5
    #: Tooltip der Filterfelder - die Filtersprache steht in ``passt``
    FILTER_HINWEIS = "Filter: > 0,9   1..5   = HEB 200   HEB   !Riegel"

    def __init__(self, spalten: list, titel: str = "", parent=None,
                 mit_kennwerten: bool = False, modellreihenfolge: bool = False):
        super().__init__(parent)
        self.titel = titel
        self.modell = TabellenModell(spalten, [], self)
        # Eingabetabelle (mindestens eine editierbare Spalte): Zellen weiss
        # oder grau statt Zebrastreifen
        self.modell.zellfarben = any(sp.editierbar for sp in spalten)
        self.modell.meldung.connect(self._meldung)
        #: die zuletzt gezeigte Meldung einer abgewiesenen Eingabe
        self.letzte_meldung = ""
        #: was eine leere Tabelle sagt: wie sie sich fuellt (10b)
        self.leertext = ""
        self.filter = Filtermodell(self)
        self.filter.setSourceModel(self.modell)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        # Werkzeugzeile einer Tabelle, die allein steht. Im unteren Bereich
        # gehen Zeilenzahl und Knoepfe in dessen Kopfzeile auf (kopf_abgeben,
        # 03.10.2026, Teilpaket 10b); lbl_zeilen fuehrt den Text dann weiter
        # als Tooltip des Zaehlers am Reiter.
        self.werkzeug = QtWidgets.QWidget(self)
        werkzeug = QtWidgets.QHBoxLayout(self.werkzeug)
        werkzeug.setContentsMargins(4, 2, 4, 0)
        self.lbl_zeilen = QtWidgets.QLabel("0 Zeilen")
        self.lbl_zeilen.setObjectName("tabellenzahl")
        # Ein langer Hinweis („Kontaktkräfte gibt es zu Lastfall oder
        # Kombination …") darf dem Fenster keine Mindestbreite aufzwingen: der
        # untere Bereich verlangte sonst 798 statt 496 px (13.09.2026). Der
        # ganze Text steht am Zeiger.
        self.lbl_zeilen.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.lbl_zeilen.setMinimumWidth(0)
        werkzeug.addWidget(self.lbl_zeilen, 1)
        werkzeug.addStretch(1)
        for text, fn, hinweis in (
                ("Spalten…", self._spaltenwahl, "Spalten ein- und ausblenden"),
                ("Filter", None, "Filterzeile ein- und ausblenden - ausblenden hebt den Filter auf"),
                ("Kopieren", self.in_zwischenablage, "Sichtbare Zeilen in die Zwischenablage"),
                ("CSV…", self.export_csv, "Sichtbare Zeilen als CSV speichern"),
                ("Excel…", self.export_xlsx, "Sichtbare Zeilen als xlsx speichern")):
            b = QtWidgets.QToolButton(self.werkzeug)
            b.setText(text)
            b.setToolTip(hinweis)
            b.setObjectName("tabellenknopf")
            if fn is None:
                b.setCheckable(True)
                b.clicked.connect(lambda an: self.filterzeile_zeigen(an, fokus=True))
                self.btn_filter = b
            else:
                b.clicked.connect(fn)
            werkzeug.addWidget(b)
        lay.addWidget(self.werkzeug)

        # Filterzeile: ein Feld je Spalte, ueber der Kopfzeile ausgerichtet.
        # Bewusst **ohne Layout**: ein Layout machte die Summe der Spalten-
        # breiten zur Mindestbreite der Tabelle - und ueber den Reiterstapel
        # zur Mindestbreite des Fensters, das mit jeder breiten Spalte wuchs
        # und sich dann nicht mehr verkleinern liess. Die Felder werden in
        # _filterbreiten auf die Kopfzeile gelegt und mit ihr gerollt.
        # Seit 03.10.2026 (10b) erscheint sie auf Knopfdruck: immer offen nahm
        # sie jeder Tabelle 22 px, auch wenn niemand filterte.
        self.filterzeile = QtWidgets.QWidget(self)
        self.filterzeile.setFixedHeight(self.FILTER_HOEHE)
        self.filterzeile.setMinimumWidth(0)
        self.filterzeile.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.felder: list[QtWidgets.QLineEdit] = []
        self._filterfelder_anlegen(spalten)
        self.filterzeile.hide()
        lay.addWidget(self.filterzeile)

        self.view = QtWidgets.QTableView(self)
        self.view.setModel(self.filter)
        self.view.setSortingEnabled(True)
        # setSortingEnabled setzt den Pfeil auf Spalte 0 *absteigend* - die
        # Tabelle stuende sonst von Anfang an verkehrt herum.
        if modellreihenfolge:
            # Lastfaelle und Kombinationen stehen in der Reihenfolge des
            # Modells (der Anwender legt sie so an und liest sie so), nicht
            # nach Name: bei „GZT1 … GZT40“ stand sonst jede Kombination dort,
            # wo ihr Name hinfaellt. Ein Klick auf den Spaltenkopf sortiert
            # wie gewohnt, der dritte Klick bringt die Modellreihenfolge zurueck.
            self.view.sortByColumn(-1, QtCore.Qt.AscendingOrder)
            kopf_ = self.view.horizontalHeader()
            if hasattr(kopf_, "setSortIndicatorClearable"):      # Qt 6.1 und neuer
                kopf_.setSortIndicatorClearable(True)
        else:
            self.view.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.modellreihenfolge = bool(modellreihenfolge)
        # Zebrastreifen nur, wo die Zellen nicht nach Bearbeitbarkeit gefaerbt sind
        self.view.setAlternatingRowColors(not self.modell.zellfarben)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        # Umschalt markiert einen Bereich, Strg nimmt einzelne Zeilen dazu
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        kopf = self.view.horizontalHeader()
        kopf.setSectionsMovable(True)
        kopf.setStretchLastSection(False)
        # Nur die ersten Zeilen bestimmen die Spaltenbreite - sonst laeuft das
        # Messen bei zehntausenden Zeilen laenger als das Rechnen.
        kopf.setResizeContentsPrecision(100)
        kopf.setMinimumSectionSize(46)
        # Die Objektnummer steht in der ersten Spalte; eine zweite Zaehlung
        # links waere nach dem Sortieren nur verwirrend.
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(22)
        self.view.setWordWrap(False)
        self.view.clicked.connect(self._geklickt)
        # Wahlspalten bekommen eine Aufklappliste, alles andere den Standard
        self.view.setItemDelegate(WahlDelegate(self))
        lay.addWidget(self.view, 1)
        # Eine leere Tabelle sagt, wie sie sich fuellt (10b): „0 Zeilen“ unter
        # einer leeren Kopfzeile liess offen, ob noch etwas kommt. Der Satz
        # liegt mitten in der Tabelle und nimmt keine Maus an.
        self.lbl_leer = QtWidgets.QLabel(self.view.viewport())
        self.lbl_leer.setObjectName("tabelleleer")
        self.lbl_leer.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_leer.setWordWrap(True)
        self.lbl_leer.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.lbl_leer.hide()
        self.view.viewport().installEventFilter(self)

        # Fusszeile: Max und Min der *sichtbaren* Zeilen, darunter auf Wunsch
        # die Summenzeile Σ (10c). Sie steht in einer eigenen Ansicht, damit
        # Sortieren und Filtern sie nicht verschieben.
        self.kennwerte_zeigen = bool(mit_kennwerten)
        #: Summenzeile: None, "summe" (Spalten mit Spalte.summe) oder ein Satz
        self._summe = None
        self.fussmodell = TabellenModell(spalten, [], self)
        self.fussmodell.verweise = False         # Max/Min/Σ verweisen auf nichts
        self.fuss = QtWidgets.QTableView(self)
        self.fuss.setObjectName("tabellenfuss")
        self.fuss.setModel(self.fussmodell)
        self.fuss.horizontalHeader().setVisible(False)
        self.fuss.verticalHeader().setVisible(False)
        self.fuss.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.fuss.setFocusPolicy(QtCore.Qt.NoFocus)
        self.fuss.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.fuss.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.fuss.verticalHeader().setDefaultSectionSize(22)
        self.fuss.setWordWrap(False)
        self.fuss.setFixedHeight(2 * 22 + 2)
        self.fuss.hide()
        lay.addWidget(self.fuss)
        # Statt einer Summe ein Satz (Auflager einer Umhuellenden): eine eigene
        # Zeile ueber die Breite der Tabelle, die nicht mit ihr waagerecht rollt
        # und einen zu langen Satz mit „…“ kuerzt; der ganze steht am Zeiger.
        # Bis zur Nachbesserung vom 03.10.2026 (10c) war er eine Zeile des
        # Fusses ueber alle Spalten: bei 1366 x 768 lagen von 1001 px Text
        # 622 px im Bild, der Rest nur durch Rollen (Segoe UI gemessen).
        self.lbl_summe = Satzzeile(self)
        self.lbl_summe.setObjectName("tabellensumme")
        self.lbl_summe.hide()
        lay.addWidget(self.lbl_summe)

        self.view.horizontalHeader().sectionResized.connect(
            lambda *_a: self._filterbreiten())
        self.view.horizontalHeader().sectionMoved.connect(
            lambda *_a: self._filterbreiten())
        self.view.horizontalScrollBar().valueChanged.connect(
            self.fuss.horizontalScrollBar().setValue)
        self.view.horizontalScrollBar().valueChanged.connect(
            lambda *_a: self._filterbreiten())
        self.modell.modelReset.connect(self._nachfuehren)
        self.filter.rowsInserted.connect(lambda *_a: self._nachfuehren())
        self.filter.rowsRemoved.connect(lambda *_a: self._nachfuehren())

    # -- Daten -----------------------------------------------------------
    #: Ab so vielen Zeilen wird eine Tabelle, die gerade nicht zu sehen ist,
    #: erst beim Anzeigen gefuellt: am Drehlager kostete das Fuellen der
    #: Elementtabelle (1,8 Mio. Zeilen) 61 s bei jedem Modellstand - fuer ein
    #: Register, das dabei hinten lag (12.09.2026)
    VERZOEGERT_AB = 50000

    def setzen(self, zeilen: list, mit_kennwerten: bool = None):
        """Neue Zeilen. Text in Zahlenspalten wird zu Zahlen. Eine grosse
        Tabelle, die nicht zu sehen ist, merkt sich die Zeilen und fuellt sich
        beim Anzeigen (showEvent)."""
        if mit_kennwerten is not None:
            self.kennwerte_zeigen = bool(mit_kennwerten)
        if len(zeilen) > self.VERZOEGERT_AB and not self.isVisible():
            self._ausstehend = zeilen
            gefiltert = ", gefiltert" if self.filter_wirkt() else ""
            self.lbl_zeilen.setText(f"{len(zeilen)} Zeilen{gefiltert} – wird beim Anzeigen gefüllt")
            self.lbl_leer.hide()
            # der Zaehler am Reiter nimmt die Zahl, ohne die Tabelle zu fuellen
            self.stand_geaendert.emit()
            return
        self._ausstehend = None
        self.modell.setzen(zahlen_wandeln(zeilen, self.modell.spalten))
        self._spaltenbreiten()
        self._nachfuehren()

    def _filterfelder_anlegen(self, spalten: list) -> None:
        # Die Spalte steht als Eigenschaft am Feld, verbunden wird eine
        # gebundene Methode und kein Lambda: spalten_setzen ersetzt die Felder
        # mit deleteLater, und ein Lambda an einem geloeschten Feld ist die
        # Art Verbindung, die beim Beenden Zugriffsverletzungen macht
        for k, sp in enumerate(spalten):
            e = QtWidgets.QLineEdit(self.filterzeile)
            e.setObjectName("tabellenfilter")
            e.setPlaceholderText(sp.name[:14])
            e.setToolTip(self.FILTER_HINWEIS)
            e.setProperty("spalte", k)
            e.textChanged.connect(self._filterfeld_geaendert)
            self.felder.append(e)

    def _filterfeld_geaendert(self, text: str) -> None:
        e = self.sender()
        k = e.property("spalte") if e is not None else None
        if k is not None:
            self._filter(int(k), text)

    @staticmethod
    def _spaltenschluessel(spalten: list) -> list:
        """(Name, wievielte Spalte dieses Namens) - „Komb.“ steht mehrfach da."""
        gezaehlt: dict = {}
        aus = []
        for sp in spalten:
            gezaehlt[sp.name] = gezaehlt.get(sp.name, 0) + 1
            aus.append((sp.name, gezaehlt[sp.name]))
        return aus

    @staticmethod
    def _spaltenkennung(spalten: list) -> list:
        return [(sp.name, sp.einheit, sp.art, sp.nachkomma, sp.ergebnis, sp.summe) for sp in spalten]

    def spalten_setzen(self, spalten: list, melden: bool = True) -> bool:
        """Andere Spalten fuer dieselbe Tabelle (03.10.2026, Teilpaket 10c).

        Die Stab- und Auflagerkraefte zeigen zu einem Lastfall oder einer
        Kombination andere Spalten als zu einer Umhuellenden (min und max je
        Groesse). Die Tabelle bleibt dieselbe - ihr Reiter, ihre Verbindungen
        zur Ansicht und ihr Platz im unteren Bereich -, neu angelegt werden
        Spalten, Filterfelder und Fusszeile; die Zeilen sind danach leer.
        Filter und Sortierung bleiben fuer jede Spalte, die es in beiden
        Fassungen gibt (gleicher Name, bei „Komb.“ an gleicher Stelle unter
        den gleichnamigen); faellt die gefilterte oder sortierte Spalte weg,
        sagt das Signal ``hinweis`` es (nicht mit *melden* False, etwa beim
        Leeren nach verworfenen Ergebnissen). Bis zur Nachbesserung vom 03.10.2026
        (10c) ging jeder Filter verloren - auch der auf „Element“. False, wenn
        es schon diese Spalten sind - dann geschieht nichts."""
        neu = list(spalten)
        if self._spaltenkennung(neu) == self._spaltenkennung(self.modell.spalten):
            return False
        alt_schl = self._spaltenschluessel(self.modell.spalten)
        neu_schl = self._spaltenschluessel(neu)
        kopf = self.view.horizontalHeader()
        k_alt = kopf.sortIndicatorSection()
        sort_alt = alt_schl[k_alt] if 0 <= k_alt < len(alt_schl) else None
        richtung = kopf.sortIndicatorOrder()
        filter_alt = {alt_schl[k]: e.text() for k, e in enumerate(self.felder)
                      if k < len(alt_schl) and e.text().strip()}
        offen = self.filterzeile_offen()
        if self.filter_wirkt():
            self.filter.leeren()
        self._ausstehend = None
        for mdl in (self.modell, self.fussmodell):
            mdl.beginResetModel()
            mdl.spalten = list(neu)
            mdl.zeilen = []
            mdl._ur = []
            mdl._index = None
            mdl.herkunft = {}
            mdl.endResetModel()
        for e in self.felder:
            e.textChanged.disconnect(self._filterfeld_geaendert)
            e.hide()
            e.deleteLater()
        self.felder = []
        self._filterfelder_anlegen(neu)
        for k in range(len(neu)):
            self.view.setColumnHidden(k, False)
            self.fuss.setColumnHidden(k, False)
        weg = []
        for schl, text in filter_alt.items():
            if schl in neu_schl:
                self.felder[neu_schl.index(schl)].setText(text)
            else:
                weg.append(f"Filter auf „{schl[0]}“")
        if sort_alt in neu_schl:
            self.view.sortByColumn(neu_schl.index(sort_alt), richtung)
        else:
            if sort_alt is not None and not (k_alt == 0 and richtung == QtCore.Qt.AscendingOrder):
                weg.append(f"Sortierung nach „{sort_alt[0]}“")
            if not self.modellreihenfolge:
                self.view.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.filterzeile.setVisible(offen or self.filter_wirkt())
        self._spaltenbreiten()
        self._nachfuehren()
        if weg and melden:
            self.hinweis.emit(" und ".join(weg) + (" entfällt" if len(weg) == 1 else " entfallen")
                              + " – die Spalte gibt es beim gezeigten Ergebnis nicht")
        return True

    def summe_setzen(self, art=None, erklaerung: str = "") -> None:
        """Die Summenzeile Σ unter der Tabelle (03.10.2026, Teilpaket 10c).

        ``"summe"``: die Spalten mit ``Spalte.summe`` ueber die sichtbaren
        Zeilen addiert - mit Filter die gefilterten, wie Max und Min. Ein Text
        steht als Satz in einer eigenen Zeile unter dem Fuss (etwa bei einer
        Umhuellenden, warum es dort keine Summe gibt), *erklaerung* am Zeiger;
        er geht nicht in den Export. None: keine Summenzeile."""
        self._summe = art or None
        self._summe_erklaerung = str(erklaerung or "")
        self._kennwerte()

    def _summenzeile(self, sicht: list) -> list:
        """Die Zeile Σ zu den sichtbaren Zeilen (leer, wenn es keine gibt
        oder sie ein Satz ist)."""
        if self._summe != "summe" or not sicht:
            return []
        n = len(self.modell.spalten)
        zeile = ["Σ"]
        for k in range(1, n):
            if not self.modell.spalten[k].summe:
                zeile.append("")
                continue
            werte = [x for x in (_zahl(r[k]) for r in sicht if k < len(r)) if x is not None]
            werte = [x for x in werte if math.isfinite(x)]
            zeile.append(float(math.fsum(werte)) if werte else "")
        return zeile

    def ausstehend(self) -> bool:
        """Wartet die Tabelle noch auf ihre Zeilen?"""
        return getattr(self, "_ausstehend", None) is not None

    def nachholen(self) -> bool:
        """Ausstehende Zeilen jetzt setzen (beim Anzeigen oder vor einem Export)."""
        z = getattr(self, "_ausstehend", None)
        if z is None:
            return False
        self._ausstehend = None
        self.modell.setzen(zahlen_wandeln(z, self.modell.spalten))
        self._spaltenbreiten()
        self._nachfuehren()
        marken = getattr(self, "_ausstehende_marken", None)
        if marken:
            self._ausstehende_marken = None
            self.markieren(marken)
        return True

    def showEvent(self, ev):
        super().showEvent(ev)
        if getattr(self, "_ausstehend", None) is not None:
            QtCore.QTimer.singleShot(0, self.nachholen)
        elif getattr(self, "_breiten_offen", False):
            self._spaltenbreiten()

    #: Ab so vielen Zeilen kommen die Spaltenbreiten aus einer Stichprobe -
    #: Qt misst sonst jede Zelle, bei 490 000 Zeilen dauert das Minuten
    STICHPROBE_AB = 3000

    def _spaltenbreiten(self):
        """Spaltenbreiten aus dem Inhalt, nach oben gedeckelt.

        Eine Tabelle, die gerade nicht zu sehen ist, misst erst beim Anzeigen
        (showEvent; 03.10.2026, Teilpaket 10c). Qt misst jede Zelle ueber den
        Delegaten, in PySide rund 0,2 ms je Zelle: seit die Stabkraefte einer
        Umhuellenden gefuellt sind (18 Spalten), kostete ein Wechsel auf die
        Umhuellende am Drehlager ohne Neuzeichnen 0,65 bis 0,98 s statt 0,39 bis
        0,50 s - zum grossen Teil fuer Tabellen, die hinten lagen
        (scratchpad/c10c_zeit.py)."""
        if not self.isVisible():
            self._breiten_offen = True
            return
        self._breiten_offen = False
        n_z = self.modell.rowCount()
        if n_z <= self.STICHPROBE_AB:
            self.view.resizeColumnsToContents()
        else:
            fm = QtGui.QFontMetrics(self.view.font())
            schritt = max(1, n_z // 300)
            for k in range(self.modell.columnCount()):
                breite = fm.horizontalAdvance(str(self.modell.kopf(k))) + 28
                for r in range(0, n_z, schritt):
                    text = self.modell.data(self.modell.index(r, k), QtCore.Qt.DisplayRole)
                    if text:
                        breite = max(breite, fm.horizontalAdvance(str(text)) + 16)
                self.view.setColumnWidth(k, breite)
        for k in range(self.modell.columnCount()):
            if self.view.columnWidth(k) > self.SPALTE_MAX:
                self.view.setColumnWidth(k, self.SPALTE_MAX)

    def sichtbare_zeilen(self) -> list:
        out = []
        for r in range(self.filter.rowCount()):
            q = self.filter.mapToSource(self.filter.index(r, 0))
            out.append(list(self.modell.zeilen[q.row()]))
        return out

    def absteigend_nach(self, name: str) -> bool:
        """Die Tabelle nach der Spalte *name* absteigend ordnen - auch alle
        Zeilen, die spaeter kommen. Die Nachweistabellen starten so nach
        Ausnutzung, der groesste Wert oben (24.09.2026). False, wenn es die
        Spalte nicht gibt."""
        namen = [sp.name for sp in self.modell.spalten]
        if name not in namen:
            return False
        self.view.sortByColumn(namen.index(name), QtCore.Qt.DescendingOrder)
        return True

    def zeilenzahl(self) -> int:
        """Wie viele Zeilen die Tabelle enthaelt (ohne Ruecksicht auf den Filter)."""
        return self.modell.rowCount()

    def sichtbar(self) -> int:
        """Wie viele Zeilen der Filter uebrig laesst."""
        return self.filter.rowCount()

    def zaehler(self) -> tuple:
        """(Zeilen, davon sichtbar) fuer den Zaehler am Reiter - ohne die
        Tabelle zu fuellen: eine, die noch auf das Anzeigen wartet (ab
        VERZOEGERT_AB Zeilen, am Drehlager etwa die Knoten), nennt die Zahl
        ihrer ausstehenden Zeilen. Wirkt dabei ein Filter, steht die Zahl der
        sichtbaren Zeilen erst nach dem Fuellen fest: dann None statt der
        Gesamtzahl. Bis zur Nachbesserung vom 03.10.2026 stand dort die
        Gesamtzahl - Reiter „19“ und „19 von 19 sichtbar“, waehrend Export und
        Tabelle gefiltert waren."""
        z = getattr(self, "_ausstehend", None)
        if z is not None:
            return len(z), (None if self.filter_wirkt() else len(z))
        return self.modell.rowCount(), self.filter.rowCount()

    def kennwerte_aktiv(self) -> bool:
        """Stehen Max und Min unter der Tabelle? Nur an Ergebnistabellen
        (``mit_kennwerten``) und erst ab KENNWERTE_AB Zeilen - gezaehlt ohne
        Filter, damit die beiden Zeilen beim Filtern nicht kommen und gehen."""
        return bool(self.kennwerte_zeigen) and self.modell.rowCount() >= self.KENNWERTE_AB

    def leertext_setzen(self, text: str) -> None:
        """Was die Tabelle sagt, solange sie leer ist: wie sie sich fuellt
        („Noch keine Lasten – Lasten → Knotenlast …“)."""
        self.leertext = str(text or "")
        self._leer_nachfuehren()

    def kopf_abgeben(self) -> None:
        """Zeilenzahl und Knoepfe stehen ab jetzt in der Kopfzeile des unteren
        Bereichs (Tabellenbereich), nicht mehr in einer eigenen Zeile."""
        self.werkzeug.hide()

    # -- Filterzeile -----------------------------------------------------
    def filterzeile_offen(self) -> bool:
        return not self.filterzeile.isHidden()

    def filter_wirkt(self) -> bool:
        """Laesst ein Filterausdruck Zeilen weg (oder koennte er es)?"""
        return bool(self.filter.ausdruecke)

    def filterzeile_zeigen(self, an: bool = True, fokus: bool = False) -> None:
        """Die Filterzeile ein- oder ausblenden (Knopf Filter, 10b).

        Ausblenden hebt die Filter auf - wie das Ausschalten des Autofilters
        in Excel. Ein Filter, der wirkt, steht so immer sichtbar ueber der
        Tabelle, und niemand haelt gefilterte Zeilen fuer alle. *fokus*: das
        Feld der gewaehlten Spalte bekommt die Eingabe."""
        an = bool(an)
        if not an and self.filter_wirkt():
            self.filter_leeren()
        self.filterzeile.setVisible(an)
        if an:
            self._filterbreiten()
            if fokus:
                k = self.view.currentIndex().column()
                k = k if 0 <= k < len(self.felder) and not self.view.isColumnHidden(k) else next(
                    (i for i in range(len(self.felder)) if not self.view.isColumnHidden(i)), -1)
                if k >= 0:
                    self.felder[k].setFocus()
        self._filterknopf_nachziehen()
        self.stand_geaendert.emit()

    def _filterknopf_nachziehen(self) -> None:
        b = self.btn_filter
        b.blockSignals(True)
        b.setChecked(self.filterzeile_offen())
        b.blockSignals(False)
        b.setText("Filter aktiv" if self.filter_wirkt() else "Filter")

    def _leer_nachfuehren(self) -> None:
        """Den Satz in der leeren Tabelle setzen: der Hinweis zum gezeigten
        Ergebnis (hinweis_setzen) vor dem allgemeinen Satz; laesst der Filter
        nichts uebrig, sagt sie das."""
        n, m = self.filter.rowCount(), self.modell.rowCount()
        text = ""
        if self.ausstehend():
            text = ""
        elif m == 0:
            text = getattr(self, "_hinweis", "") or self.leertext
        elif n == 0:
            text = ("Die Zeile passt nicht zum Filter." if m == 1
                    else f"Keine der {zl.zahl_text(m)} Zeilen passt zum Filter.")
        self.lbl_leer.setText(text)
        self.lbl_leer.setVisible(bool(text))

    def eventFilter(self, obj, ev):
        if obj is self.view.viewport() and ev.type() == QtCore.QEvent.Resize:
            self.lbl_leer.setGeometry(obj.rect().adjusted(12, 4, -12, -4))
        return super().eventFilter(obj, ev)

    def kopfzeile(self) -> list:
        return [self.modell.kopf(k) for k in range(len(self.modell.spalten))]

    def einheiten_setzen(self, quelle):
        """*quelle*: fn() -> einheiten.Einheiten (oder None fuer Grundeinheiten).
        Kopf, Zellen, Filter, Fusszeile und Export folgen den Einheiten."""
        self.modell.einheiten_quelle = quelle
        self.fussmodell.einheiten_quelle = quelle
        self.einheiten_aktualisieren()

    def einheiten_aktualisieren(self):
        self.modell.einheiten_aktualisieren()
        self.fussmodell.einheiten_aktualisieren()
        self.filter.invalidate()
        self._spaltenbreiten()
        self._nachfuehren()

    @staticmethod
    def _schluessel(x):
        """Zahl und Text auf einen Nenner bringen: 3, „3“ und 3.0 sind dasselbe."""
        z = _zahl(x)
        return z if z is not None else str(x)

    def markieren(self, werte) -> int:
        """Zeilen markieren, deren erste Spalte in *werte* steht.

        Die erste getroffene Zeile wird ins Bild geholt - so findet man die
        angeklickten Elemente in einer langen Tabelle wieder.
        """
        if getattr(self, "_ausstehend", None) is not None:
            # Tabelle noch nicht gefuellt (verzoegert): Marken merken, sie
            # werden mit dem Nachholen gesetzt
            self._ausstehende_marken = list(werte or [])
            return 0
        sm = self.view.selectionModel()
        sm.clearSelection()
        zeilen: list = []
        # Ueber das Verzeichnis des Modells statt ueber alle Zeilen des Filters:
        # so kostet ein Klick in der Ansicht auch bei 490 000 Zeilen nichts
        for wert in (werte or []):
            for r_q in self.modell.zeile_zu(wert):
                i = self.filter.mapFromSource(self.modell.index(r_q, 0))
                if i.isValid():
                    zeilen.append(i.row())
        if not zeilen:
            return 0
        # Zusammenhaengende Zeilen als **ein** Bereich. Je Zeile ein eigener
        # Bereich liess "Alles auswaehlen" am Drehlager (400 000 Knoten) ueber
        # fuenf Minuten in Qt haengen: die Auswahl fuehrt Hunderttausende
        # Einzelbereiche quadratisch zusammen. Die Knotentabelle ist so ein
        # einziger Bereich, 200 000 Zeilen dauern Sekundenbruchteile.
        auswahl = QtCore.QItemSelection()
        letzte_spalte = self.filter.columnCount() - 1
        for a, b in zeilenbereiche(zeilen):
            auswahl.select(self.filter.index(a, 0), self.filter.index(b, letzte_spalte))
        sm.select(auswahl, QtCore.QItemSelectionModel.Select
                  | QtCore.QItemSelectionModel.Rows)
        # Erst den aufgeschobenen Aufbau der Ansicht nachholen: gleich nach dem
        # Neufuellen (Klick auf eine Kombinationszelle) war der Rollbereich
        # noch 0, scrollTo blieb bei 0 stehen, und die markierte Zeile 17 von
        # 18 lag ausserhalb des Sichtfensters (Gegenpruefung 03.10.2026, 10c)
        self.view.doItemsLayout()
        self.view.scrollTo(self.filter.index(min(zeilen), 0),
                           QtWidgets.QAbstractItemView.EnsureVisible)
        return len(zeilen)

    # -- Bedienung -------------------------------------------------------
    def _filter(self, spalte: int, text: str):
        self.filter.setze_filter(spalte, text)
        if text.strip() and self.filterzeile.isHidden():
            # ein Filter, der wirkt, bleibt sichtbar - auch wenn er nicht
            # ueber den Knopf gesetzt wurde
            self.filterzeile.show()
        self._nachfuehren()

    def filter_leeren(self):
        """Alle Kopfzeilenfilter loeschen."""
        for e in self.felder:
            e.blockSignals(True)
            e.clear()
            e.blockSignals(False)
        self.filter.leeren()
        self._nachfuehren()

    def _meldung(self, text: str) -> None:
        """Eine abgewiesene Zelleingabe erklaeren - am Zeiger ueber der Zelle."""
        self.letzte_meldung = str(text)
        try:
            idx = self.view.currentIndex()
            rect = self.view.visualRect(idx) if idx.isValid() else QtCore.QRect()
            QtWidgets.QToolTip.showText(self.view.viewport().mapToGlobal(rect.bottomLeft()),
                                        self.letzte_meldung, self.view)
        except Exception:                   # noqa: BLE001
            pass

    def hinweis_setzen(self, text: str = "") -> None:
        """Ein Satz neben der Zeilenzahl, solange die Tabelle leer ist - warum
        sie leer ist und wo die Werte stehen (12.09.2026: „Stabkräfte 0 Zeilen“
        bei einer Umhüllenden, deren Extremwerte im Register Umhüllende
        liegen). Seit 03.10.2026 (10b) steht er mitten in der leeren Tabelle,
        vor dem allgemeinen Satz (leertext_setzen)."""
        self._hinweis = str(text or "")
        self._nachfuehren()

    def _nachfuehren(self):
        n, m = self.filter.rowCount(), self.modell.rowCount()
        # „1 Zeile“ statt „1 Zeilen“ (Teilpaket 11c, 03.10.2026)
        text = (f"{n} von {m} {'Zeile' if m == 1 else 'Zeilen'}" if n != m
                else f"{m} {'Zeile' if m == 1 else 'Zeilen'}")
        hinweis = getattr(self, "_hinweis", "")
        if m == 0 and hinweis:
            text += " – " + hinweis
        self.lbl_zeilen.setText(text)
        self.lbl_zeilen.setToolTip(text)
        self._leer_nachfuehren()
        self._filterknopf_nachziehen()
        self._kennwerte()
        self._filterbreiten()
        self.stand_geaendert.emit()

    def _kennwerte(self):
        """Max- und Min-Zeile aus dem, was gerade zu sehen ist - darunter die
        Summenzeile Σ, wenn die Tabelle eine hat (summe_setzen, 10c)."""
        aktiv = self.kennwerte_aktiv()
        if not aktiv and self._summe is None:
            self.fuss.hide()
            self.lbl_summe.hide()
            return
        # Ohne wirksamen Filter direkt aus dem Modell - der Weg ueber den
        # Filter fragt jede Zeile einzeln ab und kostet bei grossen Tabellen Sekunden
        if self.filter.rowCount() == self.modell.rowCount():
            sicht = self.modell.zeilen
        else:
            sicht = self.sichtbare_zeilen()
        zeilen = []
        if aktiv:
            hoch, tief = kennwerte(sicht, self.modell.spalten)
            if hoch:
                zeilen = [hoch, tief]
        summe = self._summenzeile(sicht)
        if summe:
            zeilen.append(summe)
        self.fussmodell.setzen(zeilen)
        self.fuss.setFixedHeight(len(zeilen) * 22 + 2)
        self.fuss.setVisible(bool(zeilen))
        satz = self._summe not in (None, "summe") and bool(sicht)
        if satz:
            self.lbl_summe.satz_setzen(f"Σ  {self._summe}",
                                       getattr(self, "_summe_erklaerung", "") or str(self._summe))
        self.lbl_summe.setVisible(satz)

    def _filterbreiten(self):
        """Filterfelder und Fusszeile auf die Spalten legen - Lage und Breite
        wie die Kopfzeile, auch nach Rollen und Umsortieren der Spalten."""
        kopf = self.view.horizontalHeader()
        x0 = self.view.frameWidth()
        if self.view.verticalHeader().isVisible():
            x0 += self.view.verticalHeader().width()
        h = self.filterzeile.height()
        for k, e in enumerate(self.felder):
            versteckt = self.view.isColumnHidden(k)
            e.setVisible(not versteckt)
            if not versteckt:
                x = x0 + kopf.sectionViewportPosition(k)
                e.setGeometry(x + 1, 1, max(30, kopf.sectionSize(k) - 2), max(16, h - 2))
            self.fuss.setColumnHidden(k, versteckt)
            self.fuss.setColumnWidth(k, kopf.sectionSize(k))
        # dieselbe Reihenfolge wie die Kopfzeile: bis zur Nachbesserung vom
        # 03.10.2026 (10c) blieb der Fuss beim Verschieben einer Spalte stehen,
        # und unter „Rz“ standen Max, Min und Σ von Rx
        fk = self.fuss.horizontalHeader()
        for v in range(min(kopf.count(), fk.count())):
            k = kopf.logicalIndex(v)
            if fk.visualIndex(k) != v:
                fk.moveSection(fk.visualIndex(k), v)

    def _spaltenwahl(self):
        m = QtWidgets.QMenu(self)
        for k, sp in enumerate(self.modell.spalten):
            a = m.addAction(self.modell.kopf(k))
            a.setCheckable(True)
            a.setChecked(not self.view.isColumnHidden(k))
            a.toggled.connect(lambda an, i=k: (self.view.setColumnHidden(i, not an),
                                               self._filterbreiten()))
        m.exec(QtGui.QCursor.pos())

    def _geklickt(self, index):
        wert = self.filter.data(self.filter.index(index.row(), 0), QtCore.Qt.UserRole)
        werte = self.gewaehlte_schluessel()
        # Eine Zelle, die auf ein eigenes Ergebnis verweist (10c): zuerst das
        # melden, dann die Zeile - so kann das Fenster beides in einem Bild
        # zeichnen (Nachbesserung 03.10.2026: vorher zweimal je Klick)
        k = index.column()
        if 0 <= k < len(self.modell.spalten) and len(werte) <= 1:
            q = self.filter.mapToSource(index)
            name = self.modell.ergebnisname(q.row(), k)
            if self.modell.ist_verweis(name):
                self.ergebnis_gewaehlt.emit(name)
        if len(werte) > 1:
            self.zeilen_gewaehlt.emit(werte)
        else:
            self.zeile_gewaehlt.emit(werte[0] if werte else wert)

    def gewaehlte_schluessel(self) -> list:
        """Die erste Spalte aller markierten Zeilen, in Tabellenreihenfolge."""
        sm = self.view.selectionModel()
        if sm is None:
            return []
        zeilen = sorted({i.row() for i in sm.selectedRows()}
                        | {i.row() for i in sm.selectedIndexes()})
        return [self.filter.data(self.filter.index(r, 0), QtCore.Qt.UserRole) for r in zeilen]

    # -- Export ----------------------------------------------------------
    def zeilen_fuer_export(self) -> list:
        """Was gerade zu sehen ist, samt Max- und Min-Zeile - in den
        Anzeigeeinheiten, so wie der Kopf sie nennt."""
        z = self.sichtbare_zeilen()
        dazu = []
        if self.kennwerte_aktiv() and z:
            hoch, tief = kennwerte(z, self.modell.spalten)
            dazu = [hoch, tief]
        if self._summe == "summe":
            # die Summe als Zahlen; ein Satz statt der Summe bleibt in der Ansicht
            dazu += [s for s in (self._summenzeile(z),) if s]
        return self.modell.zeilen_angezeigt(z + dazu)

    def text(self) -> str:
        return als_csv(self.kopfzeile(), self.zeilen_fuer_export())

    def in_zwischenablage(self):
        QtWidgets.QApplication.clipboard().setText(self.text())
        return self.text()

    def export_csv(self, pfad: str = ""):
        if not pfad:
            pfad, _f = QtWidgets.QFileDialog.getSaveFileName(
                self, "Tabelle als CSV", f"{self.titel or 'tabelle'}.csv",
                "CSV (*.csv)")
        if not pfad:
            return ""
        with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
            f.write(self.text())
        return pfad

    def export_xlsx(self, pfad: str = ""):
        if not pfad:
            pfad, _f = QtWidgets.QFileDialog.getSaveFileName(
                self, "Tabelle als Excel", f"{self.titel or 'tabelle'}.xlsx",
                "Excel (*.xlsx)")
        if not pfad:
            return ""
        return als_xlsx(pfad, self.titel or "Tabelle", self.kopfzeile(),
                        self.zeilen_fuer_export())


# --------------------------------------------------------------------------
# Der untere Bereich: eine Kopfzeile, darunter die Tabelle
# --------------------------------------------------------------------------
class Knopfzeile(QtWidgets.QScrollArea):
    """Die Knopfzeile unter einer Eingabetabelle; reicht die Breite nicht,
    rollt sie allein waagerecht (03.10.2026, Teilpaket 10b).

    Bis dahin machte die breiteste Knopfzeile (Bericht, sieben Knoepfe) den
    ganzen unteren Bereich so breit: bei 1024 x 700 rollte er am Stand 5734a94
    samt Kopfzeile um 250 px, bei jeder Tabelle (Segoe UI, offscreen mit
    nachgeladener Schrift gemessen; bei 1366 x 768 rollte er nicht). Jetzt
    rollt nur die Zeile, die zu breit ist; sie wird dann um den Rollbalken
    hoeher."""

    def __init__(self, inhalt: QtWidgets.QWidget, parent=None):
        super().__init__(parent)
        self.setWidget(inhalt)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.horizontalScrollBar().rangeChanged.connect(lambda *_a: self.updateGeometry())

    def rollt(self) -> bool:
        return self.horizontalScrollBar().maximum() > 0

    def _hoehe(self) -> int:
        h = self.widget().sizeHint().height()
        if self.rollt():
            h += self.horizontalScrollBar().sizeHint().height()
        return h

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(self.widget().sizeHint().width(), self._hoehe())

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(60, self._hoehe())


class Gruppenwahl(QtWidgets.QComboBox):
    """Die Gruppe als Aufklappfeld im Kopf unten - so breit wie der Name der
    gewaehlten Gruppe, nicht wie der laengste (03.10.2026, Teilpaket 10b).
    Mit Segoe UI ist es 69 px (Lager) bis 120 px (Eigenschaften) breit, das
    Protokoll 91 px; mit dem laengsten Namen waeren es immer 120 px - Platz,
    der den Reitern daneben fehlt. Die Liste zeigt weiter alle Namen ganz."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        # nie breiter als der Name: steht daneben kein Reiter (Protokoll),
        # zog das Layout das Feld sonst ueber den ganzen Kopf (Gegenpruefung
        # 03.10.2026, Segoe UI: 626 px statt 91 px bei 1366 x 768)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.currentIndexChanged.connect(lambda _i: self.updateGeometry())

    def sizeHint(self) -> QtCore.QSize:
        s = super().sizeHint()
        if self.count() == 0:
            return s
        fm = self.fontMetrics()
        laengster = max(fm.horizontalAdvance(self.itemText(i)) for i in range(self.count()))
        return QtCore.QSize(s.width() - laengster + fm.horizontalAdvance(self.currentText()), s.height())

    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()


class Kurzwahl(QtWidgets.QComboBox):
    """Ein Aufklappfeld, das geschlossen nur den Namen des Eintrags zeigt - den
    Text bis zum ersten „: “ („Kombination GZT7“ statt „Kombination GZT7:
    1.35·LF1 + 1.5·S + …“) - und so breit ist wie dieser, hoechstens BREIT_MAX
    (03.10.2026, Teilpaket 10c: die Ergebniswahl im Kopf unten). Die Liste
    zeigt die Eintraege ganz.

    Mit Segoe UI nahm ein Feld fuer 16 Zeichen samt Etikett „Ergebnis“ 239 px
    im Kopf und machte ihn 2 px hoeher, die Kurzwahl mit „Kombination GZT1“
    148 px ohne Zuwachs (Stil wie die Gruppenwahl); bei 1920 x 1080 sind so
    von den neun Reitern der Nachweise sechs statt fuenf ganz zu sehen
    (offscreen mit nachgeladener Schrift, scratchpad/c10c_mess.py)."""

    #: breiter wird das Feld nicht; ein laengerer Name wird gekuerzt (…)
    BREIT_MAX = 220
    #: so schmal darf es werden, wenn der Platz knapp ist (Platz fuer
    #: „Kombinat…“); wie breit es ist, setzt der Kopf (Tabellenbereich)
    MIN_TEXT = "Kombinat…"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.currentIndexChanged.connect(self._index_geaendert)

    def _index_geaendert(self, _i: int) -> None:
        self.updateGeometry()

    @staticmethod
    def kurz(text) -> str:
        return str(text or "").split(": ", 1)[0]

    def _textbreite(self) -> int:
        fm = self.fontMetrics()
        return min(self.BREIT_MAX, fm.horizontalAdvance(self.kurz(self.currentText())) + 2)

    def _groesse(self, textbreite: int) -> QtCore.QSize:
        opt = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(opt)
        inhalt = QtCore.QSize(max(40, textbreite), self.fontMetrics().height())
        s = self.style().sizeFromContents(QtWidgets.QStyle.CT_ComboBox, opt, inhalt, self)
        return QtCore.QSize(s.width(), super().sizeHint().height())

    def sizeHint(self) -> QtCore.QSize:
        return self._groesse(self._textbreite())

    def minimumSizeHint(self) -> QtCore.QSize:
        return self._groesse(min(self._textbreite(), self.fontMetrics().horizontalAdvance(self.MIN_TEXT)))

    def paintEvent(self, ev):
        # wie QComboBox::paintEvent, nur mit dem kurzen Text
        p = QtWidgets.QStylePainter(self)
        p.setPen(self.palette().color(QtGui.QPalette.Text))
        opt = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(opt)
        p.drawComplexControl(QtWidgets.QStyle.CC_ComboBox, opt)
        r = self.style().subControlRect(QtWidgets.QStyle.CC_ComboBox, opt,
                                        QtWidgets.QStyle.SC_ComboBoxEditField, self)
        opt.currentText = self.fontMetrics().elidedText(self.kurz(opt.currentText),
                                                       QtCore.Qt.ElideRight, max(10, r.width()))
        p.drawControl(QtWidgets.QStyle.CE_ComboBoxLabel, opt)


class Satzzeile(QtWidgets.QLabel):
    """Ein Satz in einer Zeile: zu lang, wird er mit „…“ gekuerzt; der ganze
    steht am Zeiger (die Zeile Σ der Auflager einer Umhuellenden, 10c)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._voll = ""
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setFixedHeight(22)

    def satz_setzen(self, text: str, erklaerung: str = "") -> None:
        self._voll = str(text or "")
        self.setToolTip(str(erklaerung or text or ""))
        self._kuerzen()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._kuerzen()

    def _kuerzen(self) -> None:
        breit = self.contentsRect().width()
        text = (self.fontMetrics().elidedText(self._voll, QtCore.Qt.ElideRight, breit)
                if breit > 0 else self._voll)
        if text != self.text():
            self.setText(text)


class Gruppenseite(QtWidgets.QTabWidget):
    """Die Seite einer Gruppe im unteren Bereich. Ihre Reiter stehen im Kopf
    (Reiterleiste), die eigene Leiste ist verborgen - und zaehlt hier auch
    nicht zur Mindesthoehe. QTabWidget rechnet eine verborgene Leiste mit
    (nur eine automatisch verborgene nicht): mit dem Stilblatt 29 px, die der
    Seite nie zugute kamen. Seit der Summenzeile Σ der Auflagerkraefte
    (03.10.2026, 10c) war die Seite damit in der Kompaktstufe hoeher als der
    Bereich, und von Max, Min und Σ fehlten unten 13 px (Kaestchenwert bei
    1280 x 720; mit Segoe UI 21 px)."""

    def minimumSizeHint(self) -> QtCore.QSize:
        s = super().minimumSizeHint()
        if self.tabBar().isHidden():
            s.setHeight(max(0, s.height() - self.tabBar().minimumSizeHint().height()))
        return s


def reiter_frei(leiste: QtWidgets.QTabBar) -> QtCore.QRect:
    """Der Teil einer QTabBar, den ihre Rollpfeile nicht verdecken."""
    links, rechts = 0, leiste.width()
    for pfeil in leiste.findChildren(QtWidgets.QToolButton):
        if pfeil.parent() is not leiste or not pfeil.isVisible():
            continue
        g = pfeil.geometry()
        if g.center().x() < leiste.width() / 2:
            links = max(links, g.right() + 1)
        else:
            rechts = min(rechts, g.left())
    return QtCore.QRect(links, 0, max(0, rechts - links), leiste.height())


#: Schrift leerer Reiter (Teilpaket 10b, Nachbesserung 03.10.2026): 3,2 : 1
#: gegen den Grund des Kopfes (#f4f6f8) - die Schrift gefuellter Reiter (matt,
#: #66717c) hat 4,6 : 1. Der erste Schleier ueber der Schrift kam laut
#: Gegenpruefung auf etwa 1,6 : 1, und ein gewaehlter leerer Reiter war kaum
#: von den anderen zu unterscheiden.
REITER_LEER = "#808a94"
#: ... und gewaehlt: ein helleres Akzentblau, 3,2 : 1 (Akzent #1467c6: 5,1 : 1)
REITER_LEER_GEWAEHLT = "#5a8bd0"


class Reiterleiste(QtWidgets.QTabBar):
    """Die Reiter der gewaehlten Gruppe im Kopf des unteren Bereichs, jeder mit
    seiner Zeilenzahl (03.10.2026, Teilpaket 10b).

    Die Zahl steht als kleine Marke rechts am Reiter und nicht im Text: der
    Text bleibt der Name der Tabelle, den Befehle und Pruefungen woertlich
    vergleichen. Leere Reiter sind grau (REITER_LEER), ein gewaehlter leerer
    Reiter hellblau mit dem Strich des gewaehlten. Die Schriftfarbe der Reiter
    setzt das Stilblatt (QTabBar::tab) und uebergeht dabei setTabTextColor -
    offscreen geprueft, kein einziger Bildpunkt in der gesetzten Farbe. Darum
    zeichnet der Stil bei leeren Reitern Form und Strich ohne Text
    (initStyleOption), und paintEvent schreibt den Namen in der eigenen Farbe
    an dieselbe Stelle (SE_TabBarTabText)."""

    RECHTS = QtWidgets.QTabBar.ButtonPosition.RightSide

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tabellenreiter")
        self.setExpanding(False)
        self.setDrawBase(False)
        # Reicht die Breite nicht, rollen die Reiter mit Pfeilen - gekuerzt
        # wird kein Name
        self.setUsesScrollButtons(True)
        self.setElideMode(QtCore.Qt.ElideNone)
        #: waehrend paintEvent: leere Reiter ohne Text an den Stil geben
        self._ohne_leertext = False

    def zahl_setzen(self, j: int, gesamt: int, sichtbar, hinweis: str = "") -> None:
        """Die Marke am Reiter *j*: „19“, gefiltert „5/19“, leer grau.
        ``sichtbar`` None: ein Filter wirkt, aber wie viele Zeilen er uebrig
        laesst, steht erst nach dem Fuellen fest - dann „?/19“, nie eine
        falsche Zahl (Nachbesserung 03.10.2026)."""
        if not 0 <= j < self.count():
            return
        if sichtbar is None:
            text = f"?/{zl.zahl_text(gesamt)}"
        elif sichtbar == gesamt:
            text = zl.zahl_text(gesamt)
        else:
            text = f"{zl.zahl_text(sichtbar)}/{zl.zahl_text(gesamt)}"
        leer = gesamt == 0
        marke = self.tabButton(j, self.RECHTS)
        neu = not isinstance(marke, QtWidgets.QLabel)
        if neu:
            marke = QtWidgets.QLabel(self)
            marke.setObjectName("reiterzahl")
            marke.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        elif marke.text() == text and self.ist_leer(j) == leer and marke.toolTip() == hinweis:
            return
        marke.setText(text)
        marke.setToolTip(hinweis)
        marke.setProperty("leer", leer)
        marke.setProperty("gefiltert", sichtbar != gesamt)
        marke.style().unpolish(marke)
        marke.style().polish(marke)
        marke.adjustSize()
        self.setTabData(j, leer)
        self.setTabToolTip(j, f"{self.tabText(j)}: {hinweis}" if hinweis else self.tabText(j))
        if neu:
            self.setTabButton(j, self.RECHTS, marke)
        else:
            # Reiter neu vermessen - die Marke ist breiter oder schmaler geworden
            self.setTabText(j, self.tabText(j))
        self.update()

    def minimumSizeHint(self) -> QtCore.QSize:
        """Mindestens so breit, dass der breiteste Reiter samt Rollpfeilen ganz
        zu sehen ist. QTabBar verlangt sonst nur Platz fuer die Pfeile und ein
        Stueck: mit Segoe UI blieben ihr bei 1024 x 700 so 123 px, und bei 13
        Tabellen war der gewaehlte Reiter nicht ganz zu sehen („Kontaktbedingungen“
        braucht 146 px), waehrend die Knoepfe rechts ihren Platz behielten. So
        weichen zuerst die Knoepfe ins Menue „»“."""
        s = super().minimumSizeHint()
        if self.count() == 0:
            return s
        # so breit legt QTabBar ihre Pfeile an (layoutTabs)
        pfeil = self.style().pixelMetric(QtWidgets.QStyle.PM_TabBarScrollButtonWidth, None, self)
        breit = max(self.tabSizeHint(j).width() for j in range(self.count()))
        return QtCore.QSize(max(s.width(), breit + 2 * max(pfeil, 12)), s.height())

    def zahl(self, j: int) -> str:
        """Der Text der Marke am Reiter *j* („“ ohne Marke)."""
        marke = self.tabButton(j, self.RECHTS) if 0 <= j < self.count() else None
        return marke.text() if isinstance(marke, QtWidgets.QLabel) else ""

    def ist_leer(self, j: int) -> bool:
        return bool(self.tabData(j)) if 0 <= j < self.count() else False

    def initStyleOption(self, option, index) -> None:
        super().initStyleOption(option, index)
        if self._ohne_leertext and self.ist_leer(index):
            option.text = ""

    def paintEvent(self, ev):
        leere = [j for j in range(self.count()) if self.ist_leer(j)]
        self._ohne_leertext = bool(leere)
        try:
            super().paintEvent(ev)
        finally:
            self._ohne_leertext = False
        if not leere:
            return
        p = QtGui.QPainter(self)
        try:
            # die Schrift der Reiter: Gewicht 500 wie im Stilblatt (::tab)
            f = QtGui.QFont(self.font())
            f.setWeight(QtGui.QFont.Weight.Medium)
            p.setFont(f)
            frei = reiter_frei(self)
            p.setClipRect(frei)
            for j in leere:
                opt = QtWidgets.QStyleOptionTab()
                self.initStyleOption(opt, j)
                r = self.style().subElementRect(QtWidgets.QStyle.SE_TabBarTabText, opt, self)
                p.setPen(QtGui.QColor(REITER_LEER_GEWAEHLT if j == self.currentIndex() else REITER_LEER))
                p.drawText(r, int(QtCore.Qt.AlignCenter), opt.text)
        finally:
            p.end()


class Tabellenbereich(QtWidgets.QWidget):
    """Der untere Bereich: **eine Kopfzeile**, darunter die Tabelle.

    Die Kopfzeile (03.10.2026, Teilpaket 10b) traegt in einer Zeile die Gruppe
    als Aufklappfeld (Protokoll, Modell, Eigenschaften, Lager, Lasten,
    Ergebnisse, Nachweise, Bericht), die Reiter der Tabellen dieser Gruppe mit
    ihrer Zeilenzahl und die Knoepfe Spalten, Filter, Kopieren, CSV und Excel
    fuer die Tabelle vorn. Bis dahin standen untereinander eine Gruppenleiste,
    die Register der Gruppe, je Tabelle eine Werkzeugzeile und eine immer
    offene Filterzeile: von 270 px unten blieben bei 1920 x 1080 der
    Knotentabelle 78 px (zwei Zeilen) und den Stabkraeften 108 px (drei
    Zeilen), jetzt sind es 207 px und 188 px (je sieben Zeilen; Segoe UI,
    offscreen mit nachgeladener Schrift gemessen, tests/test_unten_kopfzeile.py).

    Reicht die Breite nicht fuer Knoepfe mit Text, stehen nur ihre Symbole da
    (der Tooltip nennt sie); reicht sie auch dafuer nicht, nimmt die
    Werkzeugleiste den Rest in ihr Menue „»“. Die Reiter rollen dann mit
    Pfeilen, gekuerzt wird kein Name.

    Nach aussen verhaelt sich der Bereich wie ein flaches ``QTabWidget``
    (``count``, ``tabText``, ``setCurrentIndex``, ``currentIndex``,
    ``currentWidget``, ``addTab``): wer eine Tabelle nach vorn holt, muss
    ihre Gruppe nicht kennen. Die Reihenfolge innerhalb einer Gruppe ist die
    der Vorgabe, nicht die des Anlegens. Bis zum 03.10.2026 stand die Klasse
    in design.py (dort bleibt der Name als Verweis).
    """

    #: Gruppe fuer Tabellen, die keiner Gruppe zugeordnet sind
    SONST = "Weitere"
    #: Ein Knopf, der die Tabelle sichtbar braucht (Filter, Spalten), wurde
    #: bedient - die Fensteranordnung klappt dann einen eingeklappten Bereich auf
    bedient = QtCore.Signal()
    #: Klick bzw. Doppelklick auf eine freie Stelle des Kopfes - wie auf einen
    #: Reiter: die Fensteranordnung klappt auf bzw. um. So geht das auch in
    #: der Gruppe Protokoll, die keinen Reiter hat (Nachbesserung 03.10.2026)
    kopf_geklickt = QtCore.Signal()
    kopf_doppelt = QtCore.Signal()

    def __init__(self, gruppen, parent=None):
        super().__init__(parent)
        from . import symbole
        self.gruppen: list[tuple[str, list[str]]] = [(g, list(n)) for g, n in gruppen]
        #: Seite (Widget eines Reiters) -> ihre Datentabelle
        self._tabellen: dict = {}
        #: Widget -> seine eigene Groessenregel (siehe _groessen_regeln)
        self._politik: dict = {}
        self._aufbau = False
        #: Feld im Kopf neben der Gruppe, nur in einigen Gruppen (kopf_zusatz_setzen)
        self._zusatz = None
        self._zusatz_gruppen: set = set()
        self._zusatz_an = False
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.kopf = QtWidgets.QWidget(self)
        self.kopf.setObjectName("unterkopf")
        self.kopf.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        kl = QtWidgets.QHBoxLayout(self.kopf)
        kl.setContentsMargins(4, 2, 4, 2)
        kl.setSpacing(6)
        self.gruppenwahl = Gruppenwahl(self.kopf)
        self.gruppenwahl.setObjectName("gruppenwahl")
        self.gruppenwahl.setToolTip("Gruppe der Tabellen unten")
        self.reiter = Reiterleiste(self.kopf)
        self.werkzeug = QtWidgets.QToolBar(self.kopf)
        self.werkzeug.setObjectName("tabellenwerkzeug")
        self.werkzeug.setIconSize(QtCore.QSize(16, 16))
        self.werkzeug.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.werkzeug.setMovable(False)
        self.werkzeug.setFloatable(False)

        def knopf(text, symbol, hinweis, fn, pruefbar=False):
            a = QtGui.QAction(symbole.symbol(symbol), text, self)
            a.setToolTip(hinweis)
            a.setCheckable(pruefbar)
            a.triggered.connect(fn)
            self.werkzeug.addAction(a)
            return a
        self.act_spalten = knopf("Spalten…", "tabelle", "Spalten ein- und ausblenden",
                                 lambda: self._an_tabelle("_spaltenwahl", zeigen=True))
        self.act_filter = knopf("Filter", "filter", "", self._filter_geschaltet, pruefbar=True)
        self.act_kopieren = knopf("Kopieren", "zwischenablage", "Sichtbare Zeilen in die Zwischenablage",
                                  lambda: self._an_tabelle("in_zwischenablage"))
        self.act_csv = knopf("CSV…", "csv", "Sichtbare Zeilen als CSV speichern",
                             lambda: self._an_tabelle("export_csv"))
        self.act_excel = knopf("Excel…", "excel", "Sichtbare Zeilen als Excel-Datei (xlsx) speichern",
                               lambda: self._an_tabelle("export_xlsx"))
        kl.addWidget(self.gruppenwahl, 0, QtCore.Qt.AlignVCenter)
        kl.addWidget(self.reiter, 1, QtCore.Qt.AlignVCenter)
        # ohne Reiter (Protokoll) haelt der Leerraum das Feld links; sonst
        # stand es mitten im Kopf (mit Segoe UI gesehen, Nachbesserung 10b)
        kl.addStretch(0)
        kl.addWidget(self.werkzeug, 0, QtCore.Qt.AlignVCenter)

        self.stapel = QtWidgets.QStackedWidget(self)
        self.seiten: dict[str, QtWidgets.QTabWidget] = {}
        for g, _ in self.gruppen:
            self._gruppe_anlegen(g)
        self.gruppenwahl.currentIndexChanged.connect(self._gruppe_gewechselt)
        self.reiter.currentChanged.connect(self._reiter_gewechselt)
        self.kopf.installEventFilter(self)
        lay.addWidget(self.kopf)
        lay.addWidget(self.stapel, 1)
        self._reiter_aufbauen()

    # ---- Aufbau ----------------------------------------------------------
    def _gruppe_anlegen(self, g: str) -> QtWidgets.QTabWidget:
        seite = Gruppenseite(self.stapel)
        seite.setObjectName("tabellenregister")
        # die Reiter stehen im Kopf, die Seite zeigt keine eigenen
        seite.tabBar().setVisible(False)
        seite.currentChanged.connect(lambda _j, g=g: self._seite_gewechselt(g))
        self.seiten[g] = seite
        self.stapel.addWidget(seite)
        self.gruppenwahl.addItem(g)
        return seite

    def gruppe_von(self, name: str) -> str:
        for g, namen in self.gruppen:
            if name in namen:
                return g
        return self.SONST

    def gruppennamen(self) -> list[str]:
        return [self.gruppenwahl.itemText(i) for i in range(self.gruppenwahl.count())]

    def tabellen(self, gruppe: str) -> list[str]:
        seite = self.seiten.get(gruppe)
        return [seite.tabText(i) for i in range(seite.count())] if seite else []

    @staticmethod
    def _datentabelle_in(w):
        if isinstance(w, Datentabelle):
            return w
        return w.findChild(Datentabelle) if w is not None else None

    def addTab(self, w: QtWidgets.QWidget, name: str) -> int:
        g = self.gruppe_von(name)
        seite = self.seiten.get(g)
        if seite is None:
            self.gruppen.append((g, []))
            seite = self._gruppe_anlegen(g)
        folge = dict(self.gruppen).get(g, [])
        rang = folge.index(name) if name in folge else len(folge)
        pos = 0
        for i in range(seite.count()):
            t = seite.tabText(i)
            if (folge.index(t) if t in folge else len(folge)) <= rang:
                pos = i + 1
        seite.insertTab(pos, w, name)
        t = self._datentabelle_in(w)
        if t is not None:
            self._tabellen[w] = t
            t.kopf_abgeben()
            t.stand_geaendert.connect(lambda w=w: self._stand_geaendert(w))
        if g == self.currentGroup():
            self._reiter_aufbauen()
        self._groessen_regeln()
        return self.indexOf(w)

    def _groessen_regeln(self) -> None:
        """Nur die Seite vorn bestimmt die Mindestgroesse des Bereichs.

        QStackedWidget und QTabWidget nehmen sonst das Groesste aller Seiten:
        mit Segoe UI am Stand 5734a94 gemessen war der Inhalt unten in der
        Kompaktstufe 260 px hoch im 217 px hohen Bereich - von Max und Min der
        Stabkraefte waren 3 von 46 px zu sehen -, und bei 1024 x 700 rollte
        der Bereich samt Kopfzeile um 250 px, weil die breiteste Knopfzeile
        (Bericht) jede Tabelle so breit machte. Seiten, die nicht vorn liegen,
        bekommen darum die Groessenregel Ignored - so zaehlen sie in
        QStackedLayout nicht zur Mindestgroesse -, die vordere behaelt ihre
        eigene."""
        aus = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        vorn_g = self.stapel.currentWidget()

        def regel(w, vorn: bool):
            if w is None:
                return
            if w not in self._politik:
                self._politik[w] = w.sizePolicy()
            w.setSizePolicy(self._politik[w] if vorn else aus)
        for seite in self.seiten.values():
            regel(seite, seite is vorn_g)
            for j in range(seite.count()):
                regel(seite.widget(j), seite is vorn_g and j == seite.currentIndex())
            seite.updateGeometry()
        self.stapel.updateGeometry()
        self.updateGeometry()

    # ---- Kopfzeile -------------------------------------------------------
    def kopf_zusatz_setzen(self, w: QtWidgets.QWidget, gruppen) -> None:
        """Ein Feld im Kopf gleich rechts neben der Gruppe, zu sehen nur in den
        Gruppen *gruppen* (03.10.2026, Teilpaket 10c: die Ergebniswahl in
        Ergebnisse und Nachweise).

        Im Kopf und nicht in einer Zeile darunter: eine eigene Zeile nahm der
        Tabelle 29 px - bei 1920 x 1080 sah man von den Stabkraeften 5 statt 7
        Zeilen (159 statt 188 px), in der Kompaktstufe bei 1366 x 768 von den
        Nachweisen EC3 3 statt 5 (130 statt 159 px; Segoe UI, offscreen mit
        nachgeladener Schrift, scratchpad/c10c_mess.py). Im Kopf kostet es
        keine Hoehe. Die Breite geht den Reitern ab, die dann mit Pfeilen
        rollen (bei 1366 x 768 ist von den fuenf Reitern der Ergebnisse einer
        statt drei ganz zu sehen, der gewaehlte immer), und den Knoepfen, die
        zuerst zu Symbolen und dann ins Menue „»“ weichen - wie sonst bei
        schmalem Fenster auch. Wie breit es wird, regelt _zusatz_einpassen."""
        self._zusatz = w
        self._zusatz_gruppen = set(gruppen)
        w.setParent(self.kopf)
        self.kopf.layout().insertWidget(1, w, 0, QtCore.Qt.AlignVCenter)
        self._zusatz_nachziehen()

    def kopf_zusatz_zeigen(self, an: bool) -> None:
        """Das Feld im Kopf zeigen (in seinen Gruppen) oder ganz verbergen -
        und neu einpassen: es kann breiter oder schmaler geworden sein
        (Kurzwahl, anderer Eintrag)."""
        self._zusatz_an = bool(an)
        self._zusatz_nachziehen()

    def _zusatz_nachziehen(self) -> None:
        if self._zusatz is not None:
            self._zusatz_einpassen()
            self._knopfart_waehlen()

    def _verfuegbar(self) -> int:
        """Die Breite, die der Bereich zeigen kann: in einer Rollflaeche die
        ihres Sichtfensters - der Bereich selbst wird dort so breit wie sein
        Inhalt verlangt."""
        p = self.parentWidget()
        rolle = p.parentWidget() if p is not None else None
        if isinstance(rolle, QtWidgets.QAbstractScrollArea) and p is rolle.viewport():
            return p.width()
        return self.width()

    def zusatz_platz(self) -> int:
        """Wie viel Platz das Feld im Kopf hat [px]: die Breite des Bereichs
        abzueglich Gruppe, des breitesten Reiters samt Pfeilen und der
        Mindestbreite der Knoepfe (Menue „»“)."""
        kl = self.kopf.layout()
        m = kl.contentsMargins()
        andere = (m.left() + m.right() + 3 * kl.spacing() + self.gruppenwahl.sizeHint().width()
                  + (0 if self.reiter.isHidden() else self.reiter.minimumSizeHint().width())
                  + (0 if self.werkzeug.isHidden() else self.werkzeug.minimumSizeHint().width()))
        return self._verfuegbar() - andere

    def _zusatz_einpassen(self) -> None:
        """Das Feld bekommt seine volle Breite, solange daneben Gruppe, der
        breiteste Reiter samt Pfeilen und das Menue „»“ Platz haben; sonst so
        viel, wie bleibt (der Name wird gekuerzt), und unter seiner
        Mindestbreite gar keinen. Der Kopf wird so nie breiter als der
        Bereich, der sonst samt Kopf waagerecht rollte: ohne Schrift (Kaestchen
        statt Segoe UI) rollte er, selbst mit dem Feld auf seiner Mindestbreite,
        bei 1366 x 768 um 29 px und bei 1280 x 720 um 115 px (Kaestchenwerte,
        tests/test_unten_kopfzeile.py). Vor den Knoepfen hat das Feld Vorrang -
        sie weichen erst zu Symbolen, dann ins Menue."""
        w = self._zusatz
        if w is None:
            return
        breite = 0
        if self._zusatz_an and self.currentGroup() in self._zusatz_gruppen:
            platz = self.zusatz_platz()
            if platz >= w.minimumSizeHint().width():
                breite = min(w.sizeHint().width(), platz)
        if breite and w.minimumWidth() != breite:
            w.setFixedWidth(breite)
        if w.isHidden() == bool(breite):
            w.setVisible(bool(breite))

    def _gruppe_gewechselt(self, i: int) -> None:
        if 0 <= i < self.stapel.count():
            self.stapel.setCurrentIndex(i)
        self._zusatz_nachziehen()
        self._reiter_aufbauen()
        self._groessen_regeln()

    def _reiter_aufbauen(self) -> None:
        """Die Reiter der gewaehlten Gruppe in den Kopf legen, mit Zaehlern.
        Eine Gruppe mit nur einem Eintrag, der keine Tabelle ist (Protokoll),
        zeigt keinen Reiter - das Aufklappfeld sagt dasselbe."""
        seite = self.seiten.get(self.currentGroup())
        rb = self.reiter
        einzeln = seite is None or (seite.count() <= 1 and self._tabellen.get(seite.widget(0)) is None)
        # erst sichtbar, dann fuellen: eine verborgene QTabBar vermisst ihre
        # Reiter nicht und holt den gewaehlten dann nicht ins Bild
        rb.setVisible(not einzeln)
        self._aufbau = True
        rb.blockSignals(True)
        try:
            while rb.count():
                rb.removeTab(rb.count() - 1)
            if seite is not None:
                for j in range(seite.count()):
                    rb.addTab(seite.tabText(j))
                    t = self._tabellen.get(seite.widget(j))
                    if t is not None:
                        gesamt, sichtbar = t.zaehler()
                        rb.zahl_setzen(j, gesamt, sichtbar, t.lbl_zeilen.text())
                rb.setCurrentIndex(max(0, seite.currentIndex()))
        finally:
            rb.blockSignals(False)
            self._aufbau = False
        rb.updateGeometry()
        self._kopf_nachziehen()
        self._reiter_ins_bild()
        # ... und noch einmal, wenn der Kopf die Reiter neu verteilt hat
        QtCore.QTimer.singleShot(0, self._reiter_ins_bild)

    def _reiter_ins_bild(self) -> None:
        """Den gewaehlten Reiter in den sichtbaren Teil rollen. QTabBar tut das
        bei setCurrentIndex nur mit der Breite, die sie gerade hat - nach dem
        Umbau der Reiter einer Gruppe stand der gewaehlte sonst hinter den
        Pfeilen (offscreen mit Kaestchen statt Schrift gesehen: „Lasteinleitung“
        bei 1366 x 768)."""
        rb = self.reiter
        try:
            j = rb.currentIndex()
        except RuntimeError:                # beim Beenden schon geloescht
            return
        if rb.isHidden() or rb.count() < 2 or j < 0 or reiter_frei(rb).contains(rb.tabRect(j)):
            return
        rb.blockSignals(True)
        try:
            rb.setCurrentIndex(1 if j == 0 else 0)
            rb.setCurrentIndex(j)
        finally:
            rb.blockSignals(False)

    def _reiter_gewechselt(self, j: int) -> None:
        if self._aufbau:
            return
        seite = self.seiten.get(self.currentGroup())
        if seite is not None and 0 <= j < seite.count() and seite.currentIndex() != j:
            seite.setCurrentIndex(j)

    def _seite_gewechselt(self, g: str) -> None:
        self._groessen_regeln()
        if g != self.currentGroup() or self._aufbau:
            return
        j = self.seiten[g].currentIndex()
        if self.reiter.currentIndex() != j and 0 <= j < self.reiter.count():
            self.reiter.blockSignals(True)
            self.reiter.setCurrentIndex(j)
            self.reiter.blockSignals(False)
        self._kopf_nachziehen()
        self._reiter_ins_bild()

    def _stand_geaendert(self, w) -> None:
        """Zeilenzahl, Filter oder Filterzeile einer Tabelle geaendert."""
        t = self._tabellen.get(w)
        seite = self.seiten.get(self.currentGroup())
        j = seite.indexOf(w) if seite is not None else -1
        if t is None or j < 0 or self._aufbau:
            return
        gesamt, sichtbar = t.zaehler()
        self.reiter.zahl_setzen(j, gesamt, sichtbar, t.lbl_zeilen.text())
        if w is self.currentWidget():
            self._filterknopf_nachziehen()
        self._knopfart_waehlen()

    def aktive_tabelle(self):
        """Die Datentabelle vorn (oder None - etwa beim Protokoll)."""
        return self._tabellen.get(self.currentWidget())

    def _kopf_nachziehen(self) -> None:
        self.werkzeug.setVisible(self.aktive_tabelle() is not None)
        self._filterknopf_nachziehen()
        self._knopfart_waehlen()

    def _filterknopf_nachziehen(self) -> None:
        """Der Knopf Filter zeigt den Stand der Tabelle vorn: gedrueckt, wenn
        ihre Filterzeile offen ist, „Filter aktiv“ und hervorgehoben, wenn ein
        Filter Zeilen weglaesst."""
        t = self.aktive_tabelle()
        a = self.act_filter
        wirkt = bool(t is not None and t.filter_wirkt())
        a.blockSignals(True)
        a.setChecked(bool(t is not None and t.filterzeile_offen()))
        a.blockSignals(False)
        text = "Filter aktiv" if wirkt else "Filter"
        if wirkt:
            gesamt, sichtbar = t.zaehler()
            wie_viele = (f"{zl.zahl_text(sichtbar)} von {zl.zahl_text(gesamt)} Zeilen sichtbar"
                         if sichtbar is not None else
                         f"wie viele der {zl.zahl_text(gesamt)} Zeilen er übrig lässt, zeigt die "
                         "Tabelle beim Anzeigen")
            tip = (f"Filter aktiv: {wie_viele}. "
                   "Ein Klick blendet die Filterzeile aus und hebt den Filter auf.")
        else:
            tip = ("Filterzeile ein- und ausblenden - ausblenden hebt den Filter auf. "
                   + Datentabelle.FILTER_HINWEIS)
        if a.text() != text:
            a.setText(text)
        a.setToolTip(tip)
        b = self.werkzeug.widgetForAction(a)
        if b is not None and b.property("aktiv") != wirkt:
            b.setProperty("aktiv", wirkt)
            b.style().unpolish(b)
            b.style().polish(b)

    def _filter_geschaltet(self, an: bool) -> None:
        t = self.aktive_tabelle()
        if t is None:
            return
        self.bedient.emit()
        t.filterzeile_zeigen(bool(an), fokus=True)
        self._filterknopf_nachziehen()

    def _an_tabelle(self, methode: str, zeigen: bool = False):
        t = self.aktive_tabelle()
        if t is None:
            return None
        if zeigen:
            self.bedient.emit()
        t.nachholen()
        return getattr(t, methode)()

    def _werkzeugbreite(self, art) -> int:
        """Breite der Knopfleiste in der Darstellung *art* [px] - aus den
        Knoepfen selbst (ein QToolButton vermisst sich nach dem Umstellen
        sofort, die Leiste erst nach dem naechsten Zeichnen)."""
        summe, n = 0, 0
        for a in self.werkzeug.actions():
            b = self.werkzeug.widgetForAction(a)
            if b is None:
                continue
            alt = b.toolButtonStyle()
            if alt != art:
                b.setToolButtonStyle(art)
            summe += b.sizeHint().width()
            n += 1
            if alt != art:
                b.setToolButtonStyle(alt)
        lay = self.werkzeug.layout()
        m = lay.contentsMargins() if lay is not None else QtCore.QMargins()
        abstand = lay.spacing() if lay is not None else 0
        return summe + max(0, abstand) * max(0, n - 1) + m.left() + m.right() + 4

    def _knopfart_waehlen(self) -> None:
        """Knoepfe mit Text, wenn Gruppe, alle Reiter und die Knoepfe in die
        Zeile passen; sonst nur Symbole mit Tooltip."""
        # zuerst das Feld neben der Gruppe (es hat Vorrang vor den Knoepfen)
        self._zusatz_einpassen()
        if self.werkzeug.isHidden() or not self.kopf.isVisible():
            return
        kl = self.kopf.layout()
        m = kl.contentsMargins()
        frei = (self.kopf.width() - m.left() - m.right() - 2 * kl.spacing()
                - self.gruppenwahl.sizeHint().width()
                - (0 if self.reiter.isHidden() else self.reiter.sizeHint().width()))
        if self._zusatz is not None and not self._zusatz.isHidden():
            frei -= self._zusatz.minimumWidth() + kl.spacing()
        mit_text = QtCore.Qt.ToolButtonTextBesideIcon
        art = mit_text if frei >= self._werkzeugbreite(mit_text) else QtCore.Qt.ToolButtonIconOnly
        if art != self.werkzeug.toolButtonStyle():
            self.werkzeug.setToolButtonStyle(art)

    def eventFilter(self, obj, ev):
        if obj is self.kopf:
            typ = ev.type()
            if typ in (QtCore.QEvent.Resize, QtCore.QEvent.Show):
                self._knopfart_waehlen()
            elif typ == QtCore.QEvent.MouseButtonPress and ev.button() == QtCore.Qt.LeftButton:
                self.kopf_geklickt.emit()
            elif typ == QtCore.QEvent.MouseButtonDblClick and ev.button() == QtCore.Qt.LeftButton:
                self.kopf_doppelt.emit()
        return super().eventFilter(obj, ev)

    # ---- flache Sicht (wie ein QTabWidget) ---------------------------------
    def _eintraege(self) -> list[tuple[str, QtWidgets.QWidget, str, int]]:
        out = []
        for g in self.gruppennamen():
            seite = self.seiten[g]
            for j in range(seite.count()):
                out.append((seite.tabText(j), seite.widget(j), g, j))
        return out

    def count(self) -> int:
        return len(self._eintraege())

    def tabText(self, k: int) -> str:
        e = self._eintraege()
        return e[k][0] if 0 <= k < len(e) else ""

    def widget(self, k: int):
        e = self._eintraege()
        return e[k][1] if 0 <= k < len(e) else None

    def indexOf(self, w) -> int:
        for k, (_n, wi, _g, _j) in enumerate(self._eintraege()):
            if wi is w:
                return k
        return -1

    def currentIndex(self) -> int:
        g = self.currentGroup()
        seite = self.seiten.get(g)
        if seite is None:
            return -1
        j = seite.currentIndex()
        for k, (_n, _w, gr, jj) in enumerate(self._eintraege()):
            if gr == g and jj == j:
                return k
        return -1

    def currentWidget(self):
        seite = self.stapel.currentWidget()
        return seite.currentWidget() if isinstance(seite, QtWidgets.QTabWidget) else None

    def currentGroup(self) -> str:
        return self.gruppenwahl.currentText()

    def setCurrentIndex(self, k: int):
        e = self._eintraege()
        if not 0 <= k < len(e):
            return
        _name, _w, g, j = e[k]
        self.gruppenwahl.setCurrentIndex(self.gruppennamen().index(g))
        self.seiten[g].setCurrentIndex(j)

    def zeigen(self, name: str) -> bool:
        """Die Tabelle mit diesem Namen nach vorn holen (Gruppe folgt)."""
        for k, (n, _w, _g, _j) in enumerate(self._eintraege()):
            if n == name:
                self.setCurrentIndex(k)
                return True
        return False

    def tabBar(self) -> QtWidgets.QTabBar:
        return self.reiter


#: Zusatz zum Stilblatt
STIL = """
QLineEdit#tabellenfilter {{ border: 1px solid {linie}; border-radius: 4px;
    padding: 1px 4px; font-size: 11px; background: {grund}; }}
QLineEdit#tabellenfilter:focus {{ border-color: {akzent}; background: {flaeche}; }}
QToolButton#tabellenknopf {{ border: 1px solid {linie}; border-radius: 6px;
    padding: 2px 8px; font-size: 12px; background: {flaeche}; }}
QToolButton#tabellenknopf:hover {{ background: {akzent_hell}; color: {akzent}; }}
QToolButton#tabellenknopf:checked {{ background: {akzent_hell}; color: {akzent};
    border-color: {akzent}; }}
QLabel#tabellenzahl {{ color: {matt}; font-size: 12px; }}
QTableView#tabellenfuss {{ background: {akzent_hell}; border: 0;
    border-top: 1px solid {linie}; font-weight: 600; color: {text}; }}
QLabel#tabelleleer {{ color: {matt}; font-size: 12px; background: transparent; }}
QLabel#tabellensumme {{ background: {akzent_hell}; border-top: 1px solid {linie};
    font-weight: 600; color: {text}; padding: 0px 6px; }}
QWidget#unterkopf {{ background: {grund}; border-bottom: 1px solid {linie}; }}
QComboBox#gruppenwahl {{ padding: 2px 8px; border-radius: 6px; font-weight: 600; }}
QComboBox#ergebniswahl {{ padding: 2px 8px; border-radius: 6px; }}
QTabBar#tabellenreiter {{ background: transparent; }}
QTabBar#tabellenreiter::tab {{ padding: 5px 8px; font-weight: 500; }}
QLabel#reiterzahl {{ color: {matt}; font-size: 10px; background: transparent; }}
QLabel#reiterzahl[leer="true"] {{ color: {reiter_leer}; }}
QLabel#reiterzahl[gefiltert="true"] {{ color: {akzent2}; font-weight: 600; }}
QToolBar#tabellenwerkzeug {{ background: transparent; border: 0; padding: 0px; spacing: 3px; }}
QToolBar#tabellenwerkzeug QToolButton {{ padding: 2px 6px; border-radius: 6px;
    font-weight: 500; }}
QToolBar#tabellenwerkzeug QToolButton[aktiv="true"] {{ background: {akzent2};
    border-color: {akzent2}; color: #ffffff; }}
"""


def stil() -> str:
    return STIL.format(**dsg.FARBEN, reiter_leer=REITER_LEER)
