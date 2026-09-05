"""
Ribbon: die Befehlsleiste des Programmfensters.

Ein Ribbon ist eine Registerleiste, in der die Befehle nach Arbeitsschritt
geordnet stehen - Datei, Start, Geometrie, Struktur, Lager, Lasten, Netz,
Berechnung, Nachweise, Ergebnisse, Bericht, Ansicht, Extras. Jedes Register
enthaelt **Gruppen**, jede Gruppe grosse Knoepfe fuer die Hauptbefehle und
kleine fuer die Nebenbefehle.

Der Grundsatz der Vorgabe lautet: **jede Funktion existiert genau einmal**.
Darum gibt es hier keine Menueleiste und keine zweite Werkzeugleiste daneben;
was im Ribbon steht, steht nirgends sonst. Drei Ausnahmen sind ausdruecklich
gewollt und keine Doppelung, weil sie denselben Befehl nur schneller erreichbar
machen:

* die **Schnellzugriffsleiste** (Speichern, Rueckgaengig, Wiederholen,
  Berechnen, Auswahl aufheben) - dieselben Aktionsobjekte, nicht neue Befehle,
* die **Tastenkuerzel**,
* die **Befehlssuche** rechts im Ribbon.

Aufbau::

    ribbon = Ribbon(fenster)
    start = ribbon.register("Start")
    g = start.gruppe("Zwischenablage")
    g.gross("Rueckgaengig", "↶", self.undo, "Ctrl+Z", "Letzte Aenderung zuruecknehmen")
    g.klein("Wiederholen", self.redo, "Ctrl+Y")

Jeder Befehl wird zentral vermerkt; die Suche findet ihn ueber Registername,
Gruppe und Beschriftung.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6 import QtCore, QtGui, QtWidgets

from . import design as dsg
from . import symbole as sym


@dataclass
class Befehl:
    """Ein Befehl des Ribbons - fuer die Suche und die Schnellzugriffsleiste."""
    register: str
    gruppe: str
    text: str
    aktion: QtGui.QAction
    hinweis: str = ""

    def suchtext(self) -> str:
        return f"{self.text} {self.register} {self.gruppe} {self.hinweis}".lower()


#: Hoehe des Knopffelds einer Gruppe [px]. Jede Gruppe ist gleich hoch, und
#: der Gruppenname steht darunter immer auf derselben Hoehe - ein Register,
#: das beim Umschalten in der Hoehe springt, ist eine Zumutung.
INHALT_HOEHE = 68
TITEL_HOEHE = 16
#: Symbolgroessen der Knoepfe
SYMBOL_GROSS = 28
SYMBOL_KLEIN = 16


class Gruppe(QtWidgets.QWidget):
    """Eine Gruppe im Ribbon: Knoepfe oben, Gruppenname unten.

    Jeder Knopf traegt ein Symbol **und** seine Beschriftung; beim Ueberfahren
    erscheint der Hinweis mit dem Tastenkuerzel. Das Symbol kommt aus
    :mod:`symbole` - nach Name, sonst nach der Beschriftung geraten.
    """

    def __init__(self, name: str, ribbon: "Ribbon", register: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbongruppe")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._name = name
        self._ribbon = ribbon
        self._register = register
        aussen = QtWidgets.QVBoxLayout(self)
        aussen.setContentsMargins(6, 3, 6, 2)
        aussen.setSpacing(2)
        # Das Knopffeld hat eine feste Hoehe; darunter sitzt der Titel. So
        # steht der Titel in jeder Gruppe und jedem Register auf derselben Hoehe.
        self.feld = QtWidgets.QWidget(self)
        self.feld.setFixedHeight(INHALT_HOEHE)
        self.reihe = QtWidgets.QHBoxLayout(self.feld)
        self.reihe.setContentsMargins(0, 0, 0, 0)
        self.reihe.setSpacing(3)
        aussen.addWidget(self.feld)
        titel = QtWidgets.QLabel(name)
        titel.setObjectName("gruppentitel")
        titel.setAlignment(QtCore.Qt.AlignHCenter)
        titel.setFixedHeight(TITEL_HOEHE)
        aussen.addWidget(titel)
        self.setFixedHeight(INHALT_HOEHE + TITEL_HOEHE + 3 + 2 + 2)
        self.spalte: QtWidgets.QVBoxLayout | None = None

    # -- Knoepfe ---------------------------------------------------------
    def _aktion(self, text: str, fn, kuerzel: str, hinweis: str) -> QtGui.QAction:
        a = QtGui.QAction(text, self)
        if fn is not None:
            a.triggered.connect(lambda _=False, f=fn: f())
        if kuerzel:
            a.setShortcut(QtGui.QKeySequence(kuerzel))
            a.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        h = hinweis or text
        a.setToolTip(f"{h}" + (f"   ({kuerzel})" if kuerzel else ""))
        self._ribbon.merken(Befehl(self._register, self._name, text, a, hinweis))
        return a

    def gross(self, text: str, zeichen: str = "", fn=None, kuerzel: str = "",
              hinweis: str = "", rolle: str = "", symbol: str = "") -> QtGui.QAction:
        """Hauptbefehl: Symbol ueber der Beschriftung.

        ``zeichen`` ist das alte Schriftzeichen; es dient nur noch dazu, das
        Symbol zu raten, wenn ``symbol`` nicht genannt ist.
        """
        a = self._aktion(text, fn, kuerzel, hinweis)
        a.setIcon(sym.fuer_befehl(text, zeichen, symbol))
        b = QtWidgets.QToolButton(self)
        b.setDefaultAction(a)
        b.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        b.setIconSize(QtCore.QSize(SYMBOL_GROSS, SYMBOL_GROSS))
        b.setText(text)
        b.setObjectName("ribbongross")
        if rolle:
            b.setProperty("rolle", rolle)
        b.setMinimumWidth(58)
        b.setMaximumWidth(124)
        b.setFixedHeight(INHALT_HOEHE)
        self.spalte = None
        self.reihe.addWidget(b, 0, QtCore.Qt.AlignTop)
        return a

    def klein(self, text: str, fn=None, kuerzel: str = "", hinweis: str = "",
              zeichen: str = "", symbol: str = "") -> QtGui.QAction:
        """Nebenbefehl: Symbol neben der Beschriftung, bis zu drei uebereinander."""
        a = self._aktion(text, fn, kuerzel, hinweis)
        a.setIcon(sym.fuer_befehl(text, zeichen, symbol))
        b = QtWidgets.QToolButton(self)
        b.setDefaultAction(a)
        b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        b.setIconSize(QtCore.QSize(SYMBOL_KLEIN, SYMBOL_KLEIN))
        b.setText(text)
        b.setObjectName("ribbonklein")
        b.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        b.setFixedHeight((INHALT_HOEHE - 4) // 3)
        if self.spalte is None or self.spalte.count() >= 3:
            self.spalte = QtWidgets.QVBoxLayout()
            self.spalte.setContentsMargins(0, 0, 0, 0)
            self.spalte.setSpacing(2)
            self.spalte.setAlignment(QtCore.Qt.AlignTop)
            self.reihe.addLayout(self.spalte)
        self.spalte.addWidget(b)
        return a

    def schalter(self, text: str, fn=None, an: bool = False, hinweis: str = "",
                 symbol: str = "") -> QtGui.QAction:
        """Ein Nebenbefehl zum Ein- und Ausschalten."""
        a = self.klein(text, None, "", hinweis, symbol=symbol)
        a.setCheckable(True)
        a.setChecked(an)
        if fn is not None:
            a.toggled.connect(lambda z, f=fn: f(z))
        return a

    def widget(self, w: QtWidgets.QWidget):
        """Ein eigenes Bedienelement in die Gruppe stellen (z. B. Auswahlfeld)."""
        self.spalte = None
        self.reihe.addWidget(w, 0, QtCore.Qt.AlignVCenter)
        return w


class Register(QtWidgets.QWidget):
    """Ein Register des Ribbons: eine Reihe von Gruppen."""

    #: Hoehe jedes Registers - dieselbe fuer alle, damit nichts springt
    HOEHE = INHALT_HOEHE + TITEL_HOEHE + 3 + 2 + 2 + 4

    def __init__(self, name: str, ribbon: "Ribbon", parent=None):
        super().__init__(parent)
        self._name = name
        self._ribbon = ribbon
        self.lay = QtWidgets.QHBoxLayout(self)
        self.lay.setContentsMargins(4, 2, 4, 2)
        self.lay.setSpacing(0)
        self.lay.setAlignment(QtCore.Qt.AlignTop)
        self.lay.addStretch(1)
        self.setFixedHeight(self.HOEHE)

    def gruppe(self, name: str) -> Gruppe:
        g = Gruppe(name, self._ribbon, self._name, self)
        self.lay.insertWidget(self.lay.count() - 1, g)
        trenner = QtWidgets.QFrame(self)
        trenner.setObjectName("ribbontrenner")
        trenner.setFrameShape(QtWidgets.QFrame.VLine)
        self.lay.insertWidget(self.lay.count() - 1, trenner)
        return g


class Ribbon(QtWidgets.QWidget):
    """Die Befehlsleiste mit Schnellzugriff, Registern und Befehlssuche."""

    #: ausgeloest, wenn die Suche einen Befehl ausfuehrt
    gesucht = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbon")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.befehle: list[Befehl] = []
        self._register: dict[str, Register] = {}
        self._kontext: Register | None = None
        self._kontext_name = ""

        aussen = QtWidgets.QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.setSpacing(0)

        # Schnellzugriff und Suche stehen in einer Zeile ueber den Registern
        kopf = QtWidgets.QHBoxLayout()
        kopf.setContentsMargins(8, 3, 8, 0)
        kopf.setSpacing(4)
        self.schnellzugriff = QtWidgets.QToolBar(self)
        self.schnellzugriff.setObjectName("schnellzugriff")
        self.schnellzugriff.setIconSize(QtCore.QSize(18, 18))
        self.schnellzugriff.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        kopf.addWidget(self.schnellzugriff)
        kopf.addStretch(1)
        self.suche = QtWidgets.QLineEdit(self)
        self.suche.setObjectName("befehlssuche")
        self.suche.setPlaceholderText("Befehl suchen …")
        self.suche.setClearButtonEnabled(True)
        self.suche.setFixedWidth(220)
        self.suche.returnPressed.connect(self._suche_ausfuehren)
        kopf.addWidget(self.suche)
        aussen.addLayout(kopf)

        self.tabs = QtWidgets.QTabWidget(self)
        self.tabs.setObjectName("ribbontabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        aussen.addWidget(self.tabs)
        self._vervollstaendigung = QtWidgets.QCompleter([], self)
        self._vervollstaendigung.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self._vervollstaendigung.setFilterMode(QtCore.Qt.MatchContains)
        self.suche.setCompleter(self._vervollstaendigung)

    # -- Aufbau ----------------------------------------------------------
    def register(self, name: str) -> Register:
        if name in self._register:
            return self._register[name]
        r = Register(name, self, self)
        self._register[name] = r
        self.tabs.addTab(r, name)
        return r

    def kontext(self, name: str) -> Register:
        """Ein kontextabhaengiges Register ganz rechts anlegen oder holen.

        Es erscheint, sobald etwas ausgewaehlt ist, und traegt die Befehle, die
        auf die Auswahl passen (Vorgabe Kap. 3.2 und 16.1 Nr. 7).
        """
        if self._kontext is not None and self._kontext_name == name:
            return self._kontext
        self.kontext_aus()
        r = Register(name, self, self)
        self._kontext, self._kontext_name = r, name
        i = self.tabs.addTab(r, name)
        self.tabs.tabBar().setTabTextColor(i, QtGui.QColor(dsg.FARBEN["akzent2"]))
        return r

    def kontext_aus(self):
        """Das kontextabhaengige Register wieder entfernen."""
        if self._kontext is None:
            return
        i = self.tabs.indexOf(self._kontext)
        if i >= 0:
            self.tabs.removeTab(i)
        namen = {b.aktion for b in self.befehle if b.register == self._kontext_name}
        self.befehle = [b for b in self.befehle if b.aktion not in namen]
        self._kontext.deleteLater()
        self._kontext, self._kontext_name = None, ""

    def kontext_zeigen(self) -> bool:
        if self._kontext is None:
            return False
        self.tabs.setCurrentWidget(self._kontext)
        return True

    def merken(self, b: Befehl):
        self.befehle.append(b)
        self._vervollstaendigung.setModel(
            QtCore.QStringListModel(sorted(x.text for x in self.befehle)))

    def zeigen(self, name: str) -> bool:
        """Ein Register nach vorn holen."""
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == name:
                self.tabs.setCurrentIndex(i)
                return True
        return False

    def schnell(self, *aktionen: QtGui.QAction):
        """Aktionen in die Schnellzugriffsleiste legen - dieselben Objekte."""
        for a in aktionen:
            if a is not None:
                self.schnellzugriff.addAction(a)

    # -- Suche -----------------------------------------------------------
    def finden(self, text: str) -> list[Befehl]:
        t = (text or "").strip().lower()
        if not t:
            return []
        genau = [b for b in self.befehle if b.text.lower() == t]
        return genau or [b for b in self.befehle if t in b.suchtext()]

    def _suche_ausfuehren(self):
        treffer = self.finden(self.suche.text())
        if not treffer:
            self.gesucht.emit("")
            return
        b = treffer[0]
        self.zeigen(b.register)
        self.suche.clear()
        self.gesucht.emit(b.text)
        b.aktion.trigger()


#: Zusatz zum Stilblatt: Aussehen des Ribbons
STIL = """
QWidget#ribbon {{ background: {flaeche}; border-bottom: 1px solid {linie}; }}
QTabWidget#ribbontabs::pane {{ border: 0; border-top: 1px solid {linie};
    background: {flaeche}; }}
QTabWidget#ribbontabs > QTabBar::tab {{ background: transparent; border: 0;
    padding: 6px 14px; margin: 0 1px; color: {matt}; font-weight: 600; }}
QTabWidget#ribbontabs > QTabBar::tab:selected {{ color: {akzent};
    border-bottom: 2px solid {akzent}; }}
QTabWidget#ribbontabs > QTabBar::tab:hover {{ color: {text}; }}
QWidget#ribbongruppe {{ background: transparent; }}
QLabel#gruppentitel {{ color: {matt}; font-size: 10px; }}
QFrame#ribbontrenner {{ color: {linie}; margin: 4px 3px 2px; }}
QToolButton#ribbongross {{ border: 1px solid transparent; border-radius: 8px;
    padding: 4px 6px; font-size: 11px; }}
QToolButton#ribbongross:hover {{ background: {akzent_hell}; border-color: {linie}; }}
QToolButton#ribbongross[rolle="start"] {{ background: {akzent}; color: #fff;
    border-color: {akzent}; font-weight: 600; }}
QToolButton#ribbongross[rolle="start"]:hover {{ background: #0f4f9a; }}
QToolButton#ribbonklein {{ border: 1px solid transparent; border-radius: 6px;
    padding: 1px 8px 1px 4px; font-size: 12px; text-align: left; }}
QToolButton#ribbonklein:hover {{ background: {akzent_hell}; border-color: {linie}; }}
QToolButton#ribbonklein:checked {{ background: {akzent_hell}; color: {akzent};
    border-color: {akzent}; }}
QToolBar#schnellzugriff {{ background: transparent; border: 0; spacing: 2px; }}
QToolBar#schnellzugriff QToolButton {{ border: 1px solid transparent;
    border-radius: 6px; padding: 3px 4px; color: {matt}; }}
QToolBar#schnellzugriff QToolButton:hover {{ background: {akzent_hell};
    color: {akzent}; }}
QLineEdit#befehlssuche {{ padding: 3px 8px; border: 1px solid {linie};
    border-radius: 6px; background: {grund}; font-size: 12px; }}
"""


def stil() -> str:
    return STIL.format(**dsg.FARBEN)
