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
from dataclasses import dataclass, field

from PySide6 import QtCore, QtGui, QtWidgets

from . import design as dsg


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


def als_csv(kopf: list, zeilen: list, trenner: str = ";") -> str:
    """Tabelle als CSV-Text (deutsches Dezimalkomma, Semikolon als Trenner)."""
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=trenner, lineterminator="\n")
    schreiber.writerow(kopf)
    for z in zeilen:
        schreiber.writerow([str(x).replace(".", ",")
                            if isinstance(x, float) else x for x in z])
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
    out = []
    for z in zeilen:
        neu = list(z)
        for k, w in enumerate(neu):
            if k < len(arten) and arten[k] in ("zahl", "ganz") and isinstance(w, str):
                x = _zahl(w)
                if x is not None:
                    neu[k] = int(x) if arten[k] == "ganz" else x
        out.append(neu)
    return out


def kennwerte(zeilen: list, spalten: list) -> tuple:
    """Max- und Min-Zeile einer Ergebnistabelle (nur ueber Zahlenspalten)."""
    if not zeilen:
        return [], []
    hoch, tief = ["Max"], ["Min"]
    for k in range(1, len(spalten)):
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

    def wahlwerte(self, zeile=None) -> list:
        if self.werte_fn is not None:
            try:
                return [str(v) for v in self.werte_fn(zeile)]
            except Exception:               # noqa: BLE001
                return [str(v) for v in self.werte]
        return [str(v) for v in self.werte]

    def kopf(self) -> str:
        return f"{self.name} [{self.einheit}]" if self.einheit else self.name


class TabellenModell(QtCore.QAbstractTableModel):
    """Zeilen und Spalten; Aenderungen laufen ueber einen Rueckruf."""

    #: (Zeile, Spalte, neuer Wert) - der Rueckruf liefert True, wenn uebernommen
    geaendert = QtCore.Signal(int, int, object)

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
            return wert
        if isinstance(wert, (int, float)) and not isinstance(wert, bool):
            f, _e, nk = self.anzeige(k)
            return round(float(wert) * f, int(nk) + 6)
        paar = _paar(wert)
        if paar is not None:
            f, _e, nk = self.anzeige(k)
            if f != 1.0:
                return " / ".join(f"{x * f:.{nk}f}" for x in paar)
        return wert

    def zeilen_angezeigt(self, zeilen: list) -> list:
        """Zeilen in Anzeigeeinheiten - fuer Zwischenablage, CSV und Excel."""
        return [[self.angezeigt(k, w) if k < len(self.spalten) else w
                 for k, w in enumerate(z)] for z in zeilen]

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

    def data(self, index, rolle=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        z, k = index.row(), index.column()
        wert = self.zeilen[z][k] if k < len(self.zeilen[z]) else ""
        if rolle in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            sp = self.spalten[k]
            if sp.art == "zahl" and isinstance(wert, (int, float)):
                f, _e, nk = self.anzeige(k)
                if rolle == QtCore.Qt.EditRole:
                    return f"{self.angezeigt(k, wert):g}"
                return f"{float(wert) * f:.{nk}f}".replace(".", ",")
            if sp.art == "zahl" and rolle == QtCore.Qt.DisplayRole and _paar(wert) is not None:
                f, _e, nk = self.anzeige(k)
                if f != 1.0:
                    return " / ".join(f"{x * f:.{nk}f}".replace(".", ",") for x in _paar(wert))
            if rolle == QtCore.Qt.EditRole:
                return str(wert)
            if sp.art == "ganz" and isinstance(wert, (int, float)):
                return str(int(wert))
            return str(wert)
        if rolle == QtCore.Qt.TextAlignmentRole and self.spalten[k].art != "text":
            return int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        if rolle == QtCore.Qt.UserRole:
            # Sortieren, Filtern und Markieren in der Anzeigeeinheit
            if self.spalten[k].art in ("zahl", "ganz"):
                z = _zahl(wert)
                return wert if z is None else self.angezeigt(k, z)
            return wert
        return None

    def flags(self, index):
        f = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        if index.isValid() and self.spalten[index.column()].editierbar:
            f |= QtCore.Qt.ItemIsEditable
        return f

    def setData(self, index, wert, rolle=QtCore.Qt.EditRole) -> bool:
        if rolle != QtCore.Qt.EditRole or not index.isValid():
            return False
        z, k = index.row(), index.column()
        sp = self.spalten[k]
        try:
            neu = formel(str(wert)) if sp.art in ("zahl", "ganz") else str(wert)
        except ValueError:
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
        self.endResetModel()


class WahlDelegate(QtWidgets.QStyledItemDelegate):
    """Aufklappliste fuer Spalten mit art == "wahl" (Werkstoff, Querschnitt,
    Dicke, Nahtart …); alle anderen Spalten bekommen den Standard-Editor."""

    def __init__(self, tabelle):
        super().__init__(tabelle.view)
        self.tabelle = tabelle

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


class Datentabelle(QtWidgets.QWidget):
    """Tabelle mit Kopfzeilenfilter, Sortierung, Spaltenwahl und Export."""

    #: Zeile angeklickt - der erste Spaltenwert (meist die Objektnummer)
    zeile_gewaehlt = QtCore.Signal(object)
    #: mehrere Zeilen markiert (Umschalt/Strg): die Werte der ersten Spalte
    zeilen_gewaehlt = QtCore.Signal(list)
    #: Hoehe der Filterzeile
    FILTER_HOEHE = 22
    #: Breiter wird keine Spalte aus ihrem Inhalt (eine Elementliste mit
    #: tausend Nummern bekommt sonst eine Spalte ueber die ganze Wand)
    SPALTE_MAX = 360

    def __init__(self, spalten: list, titel: str = "", parent=None,
                 mit_kennwerten: bool = False):
        super().__init__(parent)
        self.titel = titel
        self.modell = TabellenModell(spalten, [], self)
        self.filter = Filtermodell(self)
        self.filter.setSourceModel(self.modell)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        # Werkzeugzeile
        werkzeug = QtWidgets.QHBoxLayout()
        werkzeug.setContentsMargins(4, 2, 4, 0)
        self.lbl_zeilen = QtWidgets.QLabel("0 Zeilen")
        self.lbl_zeilen.setObjectName("tabellenzahl")
        werkzeug.addWidget(self.lbl_zeilen)
        werkzeug.addStretch(1)
        for text, fn, hinweis in (
                ("Spalten…", self._spaltenwahl, "Spalten ein- und ausblenden"),
                ("Filter leeren", self.filter_leeren, "Alle Kopfzeilenfilter löschen"),
                ("Kopieren", self.in_zwischenablage, "Sichtbare Zeilen in die Zwischenablage"),
                ("CSV…", self.export_csv, "Sichtbare Zeilen als CSV speichern"),
                ("Excel…", self.export_xlsx, "Sichtbare Zeilen als xlsx speichern")):
            b = QtWidgets.QToolButton(self)
            b.setText(text)
            b.setToolTip(hinweis)
            b.setObjectName("tabellenknopf")
            b.clicked.connect(fn)
            werkzeug.addWidget(b)
        lay.addLayout(werkzeug)

        # Filterzeile: ein Feld je Spalte, ueber der Kopfzeile ausgerichtet.
        # Bewusst **ohne Layout**: ein Layout machte die Summe der Spalten-
        # breiten zur Mindestbreite der Tabelle - und ueber den Reiterstapel
        # zur Mindestbreite des Fensters, das mit jeder breiten Spalte wuchs
        # und sich dann nicht mehr verkleinern liess. Die Felder werden in
        # _filterbreiten auf die Kopfzeile gelegt und mit ihr gerollt.
        self.filterzeile = QtWidgets.QWidget(self)
        self.filterzeile.setFixedHeight(self.FILTER_HOEHE)
        self.filterzeile.setMinimumWidth(0)
        self.filterzeile.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.felder: list[QtWidgets.QLineEdit] = []
        for k, sp in enumerate(spalten):
            e = QtWidgets.QLineEdit(self.filterzeile)
            e.setObjectName("tabellenfilter")
            e.setPlaceholderText(sp.name[:14])
            e.setToolTip("Filter: > 0,9   1..5   = HEB 200   !Riegel")
            e.textChanged.connect(lambda t, i=k: self._filter(i, t))
            self.felder.append(e)
        lay.addWidget(self.filterzeile)

        self.view = QtWidgets.QTableView(self)
        self.view.setModel(self.filter)
        self.view.setSortingEnabled(True)
        # setSortingEnabled setzt den Pfeil auf Spalte 0 *absteigend* - die
        # Tabelle stuende sonst von Anfang an verkehrt herum.
        self.view.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.view.setAlternatingRowColors(True)
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

        # Fusszeile: Max und Min der *sichtbaren* Zeilen. Sie steht in einer
        # eigenen Ansicht, damit Sortieren und Filtern sie nicht verschieben.
        self.kennwerte_zeigen = bool(mit_kennwerten)
        self.fussmodell = TabellenModell(spalten, [], self)
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
    def setzen(self, zeilen: list, mit_kennwerten: bool = None):
        """Neue Zeilen. Text in Zahlenspalten wird zu Zahlen."""
        if mit_kennwerten is not None:
            self.kennwerte_zeigen = bool(mit_kennwerten)
        self.modell.setzen(zahlen_wandeln(zeilen, self.modell.spalten))
        self._spaltenbreiten()
        self._nachfuehren()

    def _spaltenbreiten(self):
        """Spaltenbreiten aus dem Inhalt, nach oben gedeckelt."""
        self.view.resizeColumnsToContents()
        for k in range(self.modell.columnCount()):
            if self.view.columnWidth(k) > self.SPALTE_MAX:
                self.view.setColumnWidth(k, self.SPALTE_MAX)

    def sichtbare_zeilen(self) -> list:
        out = []
        for r in range(self.filter.rowCount()):
            q = self.filter.mapToSource(self.filter.index(r, 0))
            out.append(list(self.modell.zeilen[q.row()]))
        return out

    def zeilenzahl(self) -> int:
        """Wie viele Zeilen die Tabelle enthaelt (ohne Ruecksicht auf den Filter)."""
        return self.modell.rowCount()

    def sichtbar(self) -> int:
        """Wie viele Zeilen der Filter uebrig laesst."""
        return self.filter.rowCount()

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
        ziel = {self._schluessel(x) for x in (werte or [])}
        sm = self.view.selectionModel()
        sm.clearSelection()
        auswahl = QtCore.QItemSelection()
        letzte, n = -1, 0
        for r in range(self.filter.rowCount()):
            i = self.filter.index(r, 0)
            if self._schluessel(self.filter.data(i, QtCore.Qt.UserRole)) in ziel:
                auswahl.select(i, self.filter.index(r, self.filter.columnCount() - 1))
                n += 1
                if letzte < 0:
                    letzte = r
        if n:
            sm.select(auswahl, QtCore.QItemSelectionModel.Select
                      | QtCore.QItemSelectionModel.Rows)
            self.view.scrollTo(self.filter.index(letzte, 0),
                               QtWidgets.QAbstractItemView.EnsureVisible)
        return n

    # -- Bedienung -------------------------------------------------------
    def _filter(self, spalte: int, text: str):
        self.filter.setze_filter(spalte, text)
        self._nachfuehren()

    def filter_leeren(self):
        """Alle Kopfzeilenfilter loeschen."""
        for e in self.felder:
            e.blockSignals(True)
            e.clear()
            e.blockSignals(False)
        self.filter.leeren()
        self._nachfuehren()

    def _nachfuehren(self):
        n, m = self.filter.rowCount(), self.modell.rowCount()
        self.lbl_zeilen.setText(f"{n} von {m} Zeilen" if n != m else f"{m} Zeilen")
        self._kennwerte()
        self._filterbreiten()

    def _kennwerte(self):
        """Max- und Min-Zeile aus dem, was gerade zu sehen ist."""
        if not self.kennwerte_zeigen:
            self.fuss.hide()
            return
        sicht = self.sichtbare_zeilen()
        hoch, tief = kennwerte(sicht, self.modell.spalten)
        self.fussmodell.setzen([hoch, tief] if hoch else [])
        self.fuss.setVisible(bool(hoch))

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
        if self.kennwerte_zeigen and z:
            hoch, tief = kennwerte(z, self.modell.spalten)
            z = z + [hoch, tief]
        return self.modell.zeilen_angezeigt(z)

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


#: Zusatz zum Stilblatt
STIL = """
QLineEdit#tabellenfilter {{ border: 1px solid {linie}; border-radius: 4px;
    padding: 1px 4px; font-size: 11px; background: {grund}; }}
QLineEdit#tabellenfilter:focus {{ border-color: {akzent}; background: {flaeche}; }}
QToolButton#tabellenknopf {{ border: 1px solid {linie}; border-radius: 6px;
    padding: 2px 8px; font-size: 12px; background: {flaeche}; }}
QToolButton#tabellenknopf:hover {{ background: {akzent_hell}; color: {akzent}; }}
QLabel#tabellenzahl {{ color: {matt}; font-size: 12px; }}
QTableView#tabellenfuss {{ background: {akzent_hell}; border: 0;
    border-top: 1px solid {linie}; font-weight: 600; color: {text}; }}
"""


def stil() -> str:
    return STIL.format(**dsg.FARBEN)
