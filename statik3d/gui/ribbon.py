"""
Ribbon: die Befehlsleiste des Programmfensters.

Ein Ribbon ist eine Registerleiste, in der die Befehle nach Arbeitsschritt
geordnet stehen - Datei, Start, Geometrie, Struktur, Lager, Lasten, Netz,
Berechnung, Ergebnisse, Nachweise, Bericht, Ansicht, Extras (seit 02.10.2026
vor den Nachweisen: nach dem Rechnen kommt das Ergebnis). Jedes Register
enthaelt **Gruppen**, jede Gruppe grosse Knoepfe fuer die Hauptbefehle und
kleine fuer die Nebenbefehle.

Der Grundsatz der Vorgabe lautet: **jede Funktion existiert genau einmal**.
Darum gibt es hier keine Menueleiste und keine zweite Werkzeugleiste daneben;
was im Ribbon steht, steht nirgends sonst. Vier Ausnahmen sind ausdruecklich
gewollt und keine Doppelung, weil sie denselben Befehl nur schneller erreichbar
machen:

* die **Schnellzugriffsleiste** (Speichern, Rueckgaengig, Wiederholen,
  Berechnen, Auswahl aufheben) - dieselben Aktionsobjekte, nicht neue Befehle,
* die **Tastenkuerzel** - sie haengen am Fenster und gelten darum in jedem
  Register; jede Tastenfolge gehoert genau einem Befehl (:meth:`Ribbon.kuerzel_setzen`),
* die **Befehlssuche** rechts im Ribbon (Strg+F setzt den Cursor hinein),
* das Register **Start**: der Arbeitsablauf zeigt Befehle aus anderen Registern
  noch einmal als Knopf (:meth:`Gruppe.nochmal`) - dieselbe Aktion, kein neuer
  Befehl und kein neues Kuerzel (Teilpaket 12d, 03.10.2026).

Aufbau::

    ribbon = Ribbon(fenster)
    start = ribbon.register("Start")
    g = start.gruppe("Bearbeiten")
    g.gross("Rueckgaengig", "↶", self.undo, "Ctrl+Z", "Letzte Aenderung zuruecknehmen")
    g.klein("Wiederholen", self.redo, "Ctrl+Y")

Jeder Befehl wird zentral vermerkt; die Suche findet ihn ueber Registername,
Gruppe und Beschriftung.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from PySide6 import QtCore, QtGui, QtWidgets

from . import design as dsg
from . import symbole as sym
from .sprache import kuerzel_text


#: Suchwoerter, die ein Befehl nicht im Namen traegt, mit denen man ihn aber
#: sucht (24.09.2026): wer „Import“ sucht, meint „Übernehmen“. Sie zaehlen
#: wie der Befehlsname.
SYNONYME = {
    "Übernehmen": "Import Importieren Einlesen RFEM IFC",
    "Exportieren": "Export Ausgeben",
    "Kombinationen automatisch…": "Kombination Lastkombination Überlagerung Überlagern",
    "DIN 19704: Kombinationen": "Kombination Lastkombination Überlagerung Überlagern",
    "Stellung anlegen…": "Stellung Situation Verschlussstellung",
    "Alle Stellungen": "Stellung Situation Verschlussstellung",
    "Modell leeren (Eigenschaften behalten)…": "Alle Elemente löschen",
    "Befehlssuche": "Befehl Befehle suchen Suche",
    "Tastenkürzel": "Kürzel Tastatur Tasten Shortcut",
}
#: Loeschende Befehle erkennt die Suche am Namen - sie laufen nie direkt aus ihr
LOESCHWOERTER = re.compile(r"lösch|leeren|verwerf|entfern")
#: Befehle, die trotz Loeschwort im Namen nur Ansicht oder Tabelle leeren und
#: darum aus der Suche laufen duerfen (Gegenpruefung 25.09.2026: die Suche
#: sperrte sie mit der Begruendung „ersetzt oder löscht Modellinhalt“)
NUR_ANSICHT = frozenset({"Filter leeren", "Sonden löschen", "Messungen löschen"})


def woerter(text: str) -> list:
    return re.findall(r"\w+", (text or "").lower())


def wort_passt(suchwort: str, wort: str) -> bool:
    """Suche am Wortanfang: „spiel“ trifft „Spiel geben“, nicht „Beispiel“.
    Ein Wort, das bis auf eine kurze Endung gleich ist, trifft auch
    („Stellungen“ -> „Stellung“)."""
    return wort.startswith(suchwort) or (len(wort) >= 5 and suchwort.startswith(wort)
                                         and len(suchwort) - len(wort) <= 2)


@dataclass
class Befehl:
    """Ein Befehl des Ribbons - fuer die Suche und die Schnellzugriffsleiste."""
    register: str
    gruppe: str
    text: str
    aktion: QtGui.QAction
    hinweis: str = ""
    #: ersetzt oder leert das Modell (Ribbon.vorsicht) - nie direkt aus der Suche
    vorsicht: bool = False
    #: Ort, wenn der Befehl nicht in einem Register steht (die Befehlssuche
    #: oben rechts, 03.10.2026); leer = „Register › Gruppe“
    ort: str = ""

    def ort_text(self) -> str:
        """Wo der Befehl zu finden ist - fuer die Trefferliste und die Kuerzelliste."""
        return self.ort or f"{self.register} › {self.gruppe}"

    def suchtext(self) -> str:
        return f"{self.text} {self.register} {self.gruppe} {self.hinweis}".lower()

    def namenswoerter(self) -> list:
        return woerter(self.text) + woerter(SYNONYME.get(self.text, ""))

    def alle_woerter(self) -> list:
        return self.namenswoerter() + woerter(f"{self.register} {self.gruppe} {self.hinweis}")

    def nicht_aus_suche(self) -> bool:
        return self.vorsicht or (self.text not in NUR_ANSICHT
                                 and bool(LOESCHWOERTER.search(self.text.lower())))


#: Hoehe des Knopffelds einer Gruppe [px]. Jede Gruppe ist gleich hoch, und
#: der Gruppenname steht darunter immer auf derselben Hoehe - ein Register,
#: das beim Umschalten in der Hoehe springt, ist eine Zumutung.
INHALT_HOEHE = 68
TITEL_HOEHE = 16
#: Symbolgroessen der Knoepfe
SYMBOL_GROSS = 28
SYMBOL_KLEIN = 16
#: Hoechstbreite eines grossen Knopfs. 124 px kuerzten „Volumen aus Flächen“
#: (braucht 125 px, 25.09.2026) auch dann, wenn das Register Platz hatte.
GROSS_MAX = 140


class Startknopf(QtWidgets.QToolButton):
    """Der blaue Startknopf („Berechnen“) mit weissem Symbol.

    Die Aktion behaelt ihr blaues Symbol - sie steht auch im Schnellzugriff
    auf hellem Grund. QToolButton holt das Symbol bei jeder Aenderung der
    Aktion (gesperrt/frei waehrend der Rechnung) neu von ihr; darum setzt
    dieser Knopf danach sein eigenes wieder (25.09.2026)."""

    def __init__(self, parent=None, symbol: str = "berechnen"):
        super().__init__(parent)
        self._eigen = sym.symbol_weiss(symbol)

    def setDefaultAction(self, a):
        super().setDefaultAction(a)
        self.setIcon(self._eigen)

    def actionEvent(self, ev):
        super().actionEvent(ev)
        if ev.type() == QtCore.QEvent.ActionChanged:
            self.setIcon(self._eigen)


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
    def _aktion(self, text: str, fn, kuerzel: str, hinweis: str, ort: str = "") -> QtGui.QAction:
        a = QtGui.QAction(text, self)
        if fn is not None:
            a.triggered.connect(lambda _=False, f=fn: f())
        if kuerzel:
            self._ribbon.kuerzel_setzen(a, kuerzel)
        h = hinweis or text
        # Der Hinweis nennt das Kuerzel deutsch („Strg+Z“); der Schluessel
        # der Tastenfolge (kuerzel_setzen) bleibt „Ctrl+Z“ (02.10.2026)
        a.setToolTip(f"{h}" + (f"   ({kuerzel_text(kuerzel)})" if kuerzel else ""))
        self._ribbon.merken(Befehl(self._register, self._name, text, a, hinweis, ort=ort))
        return a

    def gross(self, text: str, zeichen: str = "", fn=None, kuerzel: str = "",
              hinweis: str = "", rolle: str = "", symbol: str = "") -> QtGui.QAction:
        """Hauptbefehl: Symbol ueber der Beschriftung.

        ``zeichen`` ist das alte Schriftzeichen; es dient nur noch dazu, das
        Symbol zu raten, wenn ``symbol`` nicht genannt ist.
        """
        a = self._aktion(text, fn, kuerzel, hinweis)
        a.setIcon(sym.fuer_befehl(text, zeichen, symbol))
        self._grosser_knopf(a, text, rolle)
        return a

    def _grosser_knopf(self, a: QtGui.QAction, text: str, rolle: str = "") -> QtWidgets.QToolButton:
        """Der grosse Knopf zu einer Aktion (Symbol ueber der Beschriftung)."""
        b = Startknopf(self) if rolle == "start" else QtWidgets.QToolButton(self)
        b.setDefaultAction(a)
        b.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        b.setIconSize(QtCore.QSize(SYMBOL_GROSS, SYMBOL_GROSS))
        b.setText(text)
        b.setObjectName("ribbongross")
        if rolle:
            b.setProperty("rolle", rolle)
        b.setMinimumWidth(58)
        b.setMaximumWidth(GROSS_MAX)
        b.setFixedHeight(INHALT_HOEHE)
        self.spalte = None
        self.reihe.addWidget(b, 0, QtCore.Qt.AlignTop)
        return b

    def nochmal(self, aktion: QtGui.QAction, rolle: str = "") -> QtGui.QAction:
        """Einen Befehl, der in einem anderen Register steht, hier noch einmal
        als grossen Knopf zeigen (Teilpaket 12d, 03.10.2026: das Register
        Start als Arbeitsablauf).

        Es ist **dieselbe** Aktion, kein neuer Befehl: Symbol, Hinweis,
        Tastenkuerzel, Sperre und - bei einem Schalter - der Haken kommen von
        ihr, der Klick fuehrt dieselbe Funktion aus. Darum legt diese Methode
        weder einen ``Befehl`` an (die Suche fuehrt weiter zum Original) noch
        ein Kuerzel (Qt loest bei zwei Aktionen mit derselben Tastenfolge gar
        nichts aus, siehe :meth:`Ribbon.kuerzel_setzen`)."""
        self._grosser_knopf(aktion, aktion.text(), rolle)
        return aktion

    def klein(self, text: str, fn=None, kuerzel: str = "", hinweis: str = "",
              zeichen: str = "", symbol: str = "", anzeige: str = "") -> QtGui.QAction:
        """Nebenbefehl: Symbol neben der Beschriftung, bis zu drei uebereinander.

        ``text`` ist der Name des Befehls fuer Suche und Trefferliste,
        ``anzeige`` (wenn gesetzt) die kuerzere Beschriftung auf dem Knopf -
        in einer Gruppe, deren Titel schon sagt, worum es geht („Kombinationen“:
        „EN 1990…“ statt „Kombinationen automatisch…“; 02.10.2026)."""
        a = self._aktion(text, fn, kuerzel, hinweis)
        a.setIcon(sym.fuer_befehl(text, zeichen, symbol))
        if anzeige:
            a.setText(anzeige)
            a.setIconText(anzeige)
        b = QtWidgets.QToolButton(self)
        b.setDefaultAction(a)
        b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        b.setIconSize(QtCore.QSize(SYMBOL_KLEIN, SYMBOL_KLEIN))
        b.setText(anzeige or text)
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
                 symbol: str = "", kuerzel: str = "") -> QtGui.QAction:
        """Ein Nebenbefehl zum Ein- und Ausschalten."""
        a = self.klein(text, None, kuerzel, hinweis, symbol=symbol)
        a.setCheckable(True)
        a.setChecked(an)
        if fn is not None:
            a.toggled.connect(lambda z, f=fn: f(z))
        return a

    def menue(self, text: str, eintraege: list, hinweis: str = "", symbol: str = "") -> list:
        """Ein grosser Knopf mit Menue: ``eintraege`` = [(Text, Befehl, Hinweis)].

        Jeder Eintrag ist ein Befehl wie jeder andere (Suche, Menuedurchgang),
        er hat nur keinen eigenen Knopf. Zurueck kommen die Aktionen."""
        menu = self.menueknopf(text, hinweis, symbol)
        return [self.eintrag(menu, t, fn, hinweis=h) for t, fn, h in eintraege]

    # Menueknoepfe (25.09.2026, Paket 7): das Register „Ansicht“ brauchte mit
    # 40 Einzelknoepfen 3341 px und kuerzte bei 1366 px 39 Beschriftungen.
    # Ein Menueknopf fasst eine Schar gleichartiger Schalter zusammen; jeder
    # Eintrag bleibt ein Befehl mit Suche, Kuerzel und Hinweis.
    def menueknopf(self, text: str, hinweis: str = "", symbol: str = "") -> QtWidgets.QMenu:
        """Einen grossen Knopf mit Menue anlegen; zurueck kommt das (leere)
        Menue, die Eintraege setzt :meth:`eintrag`."""
        b = QtWidgets.QToolButton(self)
        b.setText(text)
        b.setIcon(sym.fuer_befehl(text, "", symbol))
        b.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        b.setIconSize(QtCore.QSize(SYMBOL_GROSS, SYMBOL_GROSS))
        b.setObjectName("ribbongross")
        b.setToolTip(hinweis or text)
        b.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(b)
        menu.setTitle(text.replace("▾", "").strip())
        menu.setToolTipsVisible(True)
        b.setMenu(menu)
        b.setMinimumWidth(58)
        b.setMaximumWidth(GROSS_MAX)
        b.setFixedHeight(INHALT_HOEHE)
        self.spalte = None
        self.reihe.addWidget(b, 0, QtCore.Qt.AlignTop)
        return menu

    def eintrag(self, menu: QtWidgets.QMenu, text: str, fn=None, kuerzel: str = "",
                hinweis: str = "", symbol: str = "", schalter: bool = False,
                an: bool = False, anzeige: str = "") -> QtGui.QAction:
        """Ein Befehl im Menue eines Menueknopfs.

        ``text`` ist sein Name fuer Suche und Menuedurchgang, ``anzeige`` (wenn
        gesetzt) die kurze Zeile im Menue - „Löschen“ im Menue „Beulfeld ▾“
        heisst in der Suche weiter „Beulfeld löschen“. ``schalter=True``: ein
        Schalter, ``fn`` bekommt dann den neuen Zustand."""
        a = self._aktion(text, None if schalter else fn, kuerzel, hinweis)
        if symbol or schalter:
            a.setIcon(sym.fuer_befehl(text, "", symbol))
        if anzeige:
            a.setText(anzeige)
            a.setIconText(anzeige)
        if schalter:
            a.setCheckable(True)
            a.setChecked(an)
            if fn is not None:
                a.toggled.connect(lambda z, f=fn: f(z))
        menu.addAction(a)
        return a

    def nur_suche(self, text: str, fn=None, kuerzel: str = "", hinweis: str = "",
                  symbol: str = "", ort: str = "") -> QtGui.QAction:
        """Ein Befehl ohne Knopf: die Befehlssuche findet ihn weiter.

        Fuer Doppelungen, die aus dem Ribbon fallen (25.09.2026): „Tabelle …“
        (die Tabelle hat unten ihren Reiter), „Flächen/Volumen vernetzen“
        (= Netz → Vernetzen), „Querschnitt/Dicke zuweisen…“ und „Gelenke
        setzen…“ (= Kontextregister „Auswahl“). ``ort`` nennt, wo es den Befehl
        statt eines Knopfs gibt („Kopfzeile oben rechts“ fuer die Befehlssuche);
        die Suche holt dann kein Register nach vorn."""
        a = self._aktion(text, fn, kuerzel, hinweis, ort)
        a.setIcon(sym.fuer_befehl(text, "", symbol))
        return a

    def widget(self, w: QtWidgets.QWidget):
        """Ein eigenes Bedienelement in die Gruppe stellen (z. B. Auswahlfeld)."""
        self.spalte = None
        self.reihe.addWidget(w, 0, QtCore.Qt.AlignVCenter)
        return w

    def in_spalte(self, w: QtWidgets.QWidget, neue_spalte: bool = False) -> QtWidgets.QWidget:
        """Ein Bedienelement (Auswahlfeld) in die Spalte der kleinen Knoepfe,
        so hoch wie einer von ihnen - drei stehen uebereinander;
        ``neue_spalte`` beginnt eine neue Spalte."""
        w.setFixedHeight((INHALT_HOEHE - 4) // 3)
        w.setProperty("ribbonzeile", True)
        if neue_spalte or self.spalte is None or self.spalte.count() >= 3:
            self.spalte = QtWidgets.QVBoxLayout()
            self.spalte.setContentsMargins(0, 0, 0, 0)
            self.spalte.setSpacing(2)
            self.spalte.setAlignment(QtCore.Qt.AlignTop)
            self.reihe.addLayout(self.spalte)
        self.spalte.addWidget(w)
        return w

    def beschriftet(self, text: str, feld: QtWidgets.QWidget, neue_spalte: bool = False) -> QtWidgets.QLabel:
        """Ein Auswahlfeld mit sichtbarer Beschriftung links davon, in der
        Spalte der kleinen Knoepfe (Teilpaket 12c, 03.10.2026).

        Bis dahin trugen die Felder im Kontextregister nur einen Tooltip: wer
        drei Aufklapplisten nebeneinander sah, musste raten, welche der
        Querschnitt ist. Die Beschriftung ist ein QLabel mit dem Feld als
        Buddy; alle Beschriftungen einer Gruppe sind gleich breit, damit die
        Felder untereinander buendig stehen. Rueckgabe: die Beschriftung."""
        zeile = QtWidgets.QWidget(self.feld)
        lay = QtWidgets.QHBoxLayout(zeile)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        name = QtWidgets.QLabel(text, zeile)
        name.setObjectName("ribbonfeldname")
        name.setBuddy(feld)
        lay.addWidget(name)
        lay.addWidget(feld, 1)
        feld.setFixedHeight((INHALT_HOEHE - 4) // 3)
        feld.setProperty("ribbonzeile", True)
        # Schriftbreite der Beschriftung: der Stil setzt 12 px, gemessen wird
        # mit derselben Schrift, sonst kuerzte ein schmaleres Label den Text
        schrift = QtGui.QFont(name.font())
        schrift.setPixelSize(12)
        name.setFont(schrift)
        self._feldnamen = getattr(self, "_feldnamen", [])
        self._feldnamen.append(name)
        breit = max(QtGui.QFontMetrics(schrift).horizontalAdvance(n.text()) for n in self._feldnamen) + 2
        for n in self._feldnamen:
            n.setMinimumWidth(breit)
        self.in_spalte(zeile, neue_spalte)
        return name


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

    def gruppe(self, name: str, sichtbar: bool = True) -> Gruppe:
        """Eine Gruppe anlegen. ``sichtbar=False``: eine Gruppe nur fuer die
        Befehlssuche (Gruppe.nur_suche) - ohne Platz im Register."""
        g = Gruppe(name, self._ribbon, self._name, self)
        if not sichtbar:
            g.hide()
            return g
        self.lay.insertWidget(self.lay.count() - 1, g)
        trenner = QtWidgets.QFrame(self)
        trenner.setObjectName("ribbontrenner")
        trenner.setFrameShape(QtWidgets.QFrame.VLine)
        self.lay.insertWidget(self.lay.count() - 1, trenner)
        return g


class _KlickDraussen(QtCore.QObject):
    """Ereignisfilter an der Anwendung, nur solange ein Register vorlaeufig
    offen ist (Ribbon._klick_draussen, 25.09.2026)."""

    def __init__(self, ribbon):
        super().__init__(ribbon)
        self.ribbon = ribbon

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.MouseButtonPress:
            self.ribbon._druck_irgendwo(obj, ev)
        return False


class Ribbon(QtWidgets.QWidget):
    """Die Befehlsleiste mit Schnellzugriff, Registern und Befehlssuche."""

    #: ausgeloest, wenn die Suche einen Befehl ausfuehrt
    gesucht = QtCore.Signal(str)
    #: ein Hinweis der Suche fuer die Statuszeile (Trefferliste, nicht ausgefuehrt)
    meldung = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbon")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.befehle: list[Befehl] = []
        self._register: dict[str, Register] = {}
        self._kontext: Register | None = None
        self._kontext_name = ""
        #: woraus das Kontextregister gebaut ist (die Arten der Auswahl); wechselt
        #: nur die Zahl, bleibt das Register stehen und nur sein Reiter aendert sich
        self._kontext_schluessel = None
        #: das zuletzt benutzte Register ausser dem Kontextregister - dorthin geht
        #: es zurueck, wenn das Kontextregister verschwindet, waehrend es vorn lag
        self._zuletzt = ""
        self._kontext_entfernt = False

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
        self._aussen, self._kopfreihe = aussen, kopf

        self.tabs = QtWidgets.QTabWidget(self)
        self.tabs.setObjectName("ribbontabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        aussen.addWidget(self.tabs)
        self.tabs.currentChanged.connect(self._reiter_gewechselt)
        self._suche_einrichten()
        self._einklappen_einrichten()

    def kopf_abgeben(self):
        """Schnellzugriff und Suche aus der eigenen Zeile herausgeben (25.09.2026).

        Das Programmfenster stellt beide in die dunkle Kopfzeile: die eigene
        Zeile ueber den Registern kostete 31 px Hoehe, in denen links vier
        Symbole und rechts ein Suchfeld standen. Es bleiben dieselben Objekte
        (ribbon.schnellzugriff, ribbon.suche) - Kuerzel, Suche und Pruefungen
        finden sie weiter. Rueckgabe: (Schnellzugriff, Suche)."""
        reihe = getattr(self, "_kopfreihe", None)
        if reihe is not None:
            for w in (self.schnellzugriff, self.suche):
                reihe.removeWidget(w)
            self._aussen.removeItem(reihe)
            reihe.deleteLater()
            self._kopfreihe = None
        return self.schnellzugriff, self.suche

    # -- Einklappen (25.09.2026) -------------------------------------------
    # Das eingeklappte Ribbon zeigt nur die Registerzeile: 99 px mehr fuer
    # die Ansicht. Wie in Office: Doppelklick auf einen Reiter oder Strg+F1
    # schaltet um; ein einfacher Klick auf einen Reiter klappt das Register
    # nur vorlaeufig auf, bis ein Befehl daraus gelaufen ist.
    #: ausgeloest, wenn das Ribbon ein- oder ausgeklappt wird (bleibend)
    eingeklappt_geaendert = QtCore.Signal(bool)

    def _einklappen_einrichten(self):
        self._eingeklappt = False
        self._vorlaeufig = False
        # Der Stapel der Register ist ein Kind des QTabWidget ohne eigenen
        # Zugriff - ausgeblendet bleibt nur die Reiterzeile
        self._stapel = self.tabs.findChild(QtWidgets.QStackedWidget)
        self._doppel = False
        self._klick_draussen_an = False
        self.tabs.tabBarDoubleClicked.connect(self._reiter_doppelt)
        self.tabs.tabBarClicked.connect(self._reiter_geklickt)

    def _reiter_doppelt(self, _i: int) -> None:
        """Doppelklick auf einen Reiter schaltet das Einklappen um.

        QTabBar sendet nach tabBarDoubleClicked selbst noch einmal
        tabBarClicked (Gegenpruefung 25.09.2026, echter Doppelklick): der
        oeffnete das eben eingeklappte Register gleich wieder vorlaeufig, und
        sichtbar aenderte sich nichts. Dieser eine Klick zaehlt nicht."""
        self._doppel = True
        QtCore.QTimer.singleShot(0, self._doppel_vergessen)
        self.einklappen(not self._eingeklappt)

    def _doppel_vergessen(self) -> None:
        self._doppel = False

    def eingeklappt(self) -> bool:
        """Bleibend eingeklappt (ein vorlaeufig offenes Register zaehlt nicht)."""
        return self._eingeklappt

    def einklappen(self, an: bool = True) -> None:
        """Das Ribbon bleibend ein- (an) oder ausklappen."""
        an = bool(an)
        self._vorlaeufig = False
        geaendert = an != self._eingeklappt
        self._eingeklappt = an
        self._stapel_zeigen(not an)
        if geaendert:
            self.eingeklappt_geaendert.emit(an)

    def _stapel_zeigen(self, sichtbar: bool) -> None:
        # Ein Klick neben das vorlaeufig offene Register schliesst es wie in
        # Office (Gegenpruefung 25.09.2026: es blieb nach einem Klick in die
        # Ansicht offen und nahm ihr 99 px); gehorcht wird nur solange
        self._klick_draussen(self._eingeklappt and sichtbar)
        if self._stapel is None:
            return
        self._stapel.setVisible(sichtbar)
        if sichtbar:
            self.tabs.setMaximumHeight(16777215)
        else:
            # QTabWidget rechnet seine Wunschhoehe mit dem verborgenen Stapel
            self.tabs.setMaximumHeight(self.tabs.tabBar().sizeHint().height())
        self.updateGeometry()

    def _klick_draussen(self, an: bool) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None or bool(an) == self._klick_draussen_an:
            return
        self._klick_draussen_an = bool(an)
        if getattr(self, "_draussen_filter", None) is None:
            self._draussen_filter = _KlickDraussen(self)
        if an:
            app.installEventFilter(self._draussen_filter)
        else:
            app.removeEventFilter(self._draussen_filter)

    def _druck_irgendwo(self, obj, ev) -> None:
        """Ein Mausdruck irgendwo im Programm, waehrend das Register vorlaeufig
        offen ist: liegt er neben dem Ribbon, klappt es zu.

        Menues und Listen, die aus dem Ribbon aufgehen, sind eigene Fenster:
        waehrend eines solchen Aufklappers zaehlt nichts. Ob der Druck neben
        dem Ribbon lag, sagt die Lage, nicht das Empfaengerobjekt (ein nicht
        angenommener Druck wandert zu den Eltern weiter, auch aus dem Ribbon
        heraus)."""
        if not isinstance(obj, QtWidgets.QWidget):
            return
        try:
            punkt = ev.globalPosition().toPoint()
        except AttributeError:
            return
        if (QtWidgets.QApplication.activePopupWidget() is None and obj.window() is self.window()
                and not self.rect().contains(self.mapFromGlobal(punkt))):
            self._vorlaeufig = False
            self._stapel_zeigen(False)

    def _reiter_geklickt(self, _i: int) -> None:
        """Eingeklappt: ein Klick auf einen Reiter zeigt das Register, bis ein
        Befehl daraus laeuft (oder ein zweiter Klick es wieder schliesst)."""
        if self._doppel:
            # der Klick, den QTabBar nach einem Doppelklick selbst sendet
            self._doppel = False
            return
        if not self._eingeklappt:
            return
        if self._vorlaeufig and _i == self.tabs.currentIndex():
            self._vorlaeufig = False
            self._stapel_zeigen(False)
            return
        self._vorlaeufig = True
        self._stapel_zeigen(True)

    def vorlaeufig_offen(self) -> bool:
        return self._eingeklappt and self._vorlaeufig

    def _nach_befehl(self) -> None:
        """Ein Befehl ist gelaufen: ein vorlaeufig aufgeklapptes Register klappt
        wieder zu."""
        if self._eingeklappt and self._vorlaeufig:
            self._vorlaeufig = False
            self._stapel_zeigen(False)

    # -- Aufbau ----------------------------------------------------------
    def register(self, name: str) -> Register:
        if name in self._register:
            return self._register[name]
        r = Register(name, self, self)
        self._register[name] = r
        self.tabs.addTab(r, name)
        return r

    def kontext(self, name: str, schluessel=None) -> Register:
        """Ein kontextabhaengiges Register ganz rechts anlegen oder holen.

        Es erscheint, sobald etwas ausgewaehlt ist, und traegt die Befehle, die
        auf die Auswahl passen (Vorgabe Kap. 3.2 und 16.1 Nr. 7). Gleicher Name
        und gleicher ``schluessel`` (woraus es gebaut ist): dasselbe Register.
        Ein anderes ersetzt das alte und liegt dann vorn, wenn das alte vorn
        lag - bis 03.10.2026 sprang die Ansicht dabei auf den Nachbarn.
        """
        if (self._kontext is not None and self._kontext_name == name
                and self._kontext_schluessel == schluessel):
            return self._kontext
        war_vorn = self._kontext is not None and self.tabs.currentWidget() is self._kontext
        self.kontext_aus(nach_vorn=False)
        r = Register(name, self, self)
        self._kontext, self._kontext_name = r, name
        self._kontext_schluessel = schluessel
        i = self.tabs.addTab(r, name)
        self.tabs.tabBar().setTabTextColor(i, QtGui.QColor(dsg.FARBEN["akzent2"]))
        if war_vorn:
            self.tabs.setCurrentWidget(r)
        return r

    def kontext_schluessel(self):
        """Woraus das Kontextregister gebaut ist (None ohne Register)."""
        return self._kontext_schluessel if self._kontext is not None else None

    def kontext_benennen(self, name: str, hinweis: str = "") -> bool:
        """Den Reiter des Kontextregisters umbenennen, ohne es neu zu bauen.

        Die Auswahl wechselt bei jedem Klick ihre Zahl; die Befehle sind
        dieselben. Neu bauen hiess: Register weg, Register neu - und lag es
        vorn, stand der Anwender mitten im Klicken in einem anderen Register.
        ``hinweis``: Tooltip des Reiters (die volle Aufstellung)."""
        if self._kontext is None:
            return False
        alt = self._kontext_name
        i = self.tabs.indexOf(self._kontext)
        if name != alt:
            # die Befehle haengen mit ihrem Registernamen in der Suche und in
            # kontext_aus - sie ziehen mit
            for b in self.befehle:
                if b.register == alt:
                    b.register = name
            self._kontext._name = name
            for g in self._kontext.findChildren(Gruppe):
                g._register = name
            self._kontext_name = name
            self.tabs.setTabText(i, name)
        self.tabs.setTabToolTip(i, hinweis)
        return True

    def _reiter_gewechselt(self, i: int) -> None:
        """Das zuletzt benutzte Register merken (nie das Kontextregister)."""
        if self._kontext_entfernt:
            return
        w = self.tabs.widget(i)
        if w is not None and w is not self._kontext:
            self._zuletzt = self.tabs.tabText(i)

    def kontext_aus(self, nach_vorn: bool = True):
        """Das kontextabhaengige Register wieder entfernen.

        Lag es vorn, kommt das zuletzt benutzte Register nach vorn, sonst
        „Start“ - Qt nahm bis 03.10.2026 den linken Nachbarn, „Extras“.
        ``nach_vorn=False``: nicht umschalten (das Register wird gleich durch
        ein neues ersetzt)."""
        if self._kontext is None:
            return
        war_vorn = self.tabs.currentWidget() is self._kontext
        i = self.tabs.indexOf(self._kontext)
        self._kontext_entfernt = True        # Qt waehlt beim Entfernen selbst einen Reiter
        try:
            if i >= 0:
                self.tabs.removeTab(i)
        finally:
            self._kontext_entfernt = False
        namen = {b.aktion for b in self.befehle if b.register == self._kontext_name}
        self.befehle = [b for b in self.befehle if b.aktion not in namen]
        self._kontext.deleteLater()
        self._kontext, self._kontext_name, self._kontext_schluessel = None, "", None
        if war_vorn and nach_vorn:
            if not (self._zuletzt and self.zeigen(self._zuletzt)):
                if not self.zeigen("Start") and self.tabs.count():
                    self.tabs.setCurrentIndex(0)

    def kontext_zeigen(self) -> bool:
        if self._kontext is None:
            return False
        self.tabs.setCurrentWidget(self._kontext)
        return True

    def kuerzel_setzen(self, a: QtGui.QAction, kuerzel: str) -> bool:
        """Das Tastenkuerzel eines Befehls anlegen - einmal je Tastenfolge.

        Die Aktion wird zusaetzlich dem Fenster zugeordnet. Qt haelt ein
        anwendungsweites Kuerzel nur fuer aktiv, solange eines der Widgets
        seiner Aktion sichtbar ist - und der Knopf im hinteren Register ist
        es nicht (gemessen 12.09.2026 mit QTest.keyClick: Strg+A waehlte im
        Register „Ansicht“ 0 von 17 Knoten, im Register „Start“ 17 von 17;
        ebenso stumm ausserhalb ihres Registers waren Strg+N/O/I/E/Q, Strg+R,
        Strg+B, Strg+Umschalt+C und Umschalt+F1..F7). Das Fenster ist immer
        sichtbar; ein modaler Dialog sperrt die Kuerzel wie bisher.

        Traegt schon ein Befehl die Tastenfolge, bekommt der neue keine: zwei
        aktive Aktionen mit demselben Kuerzel loesen in Qt gar nichts aus
        („QAction::event: Ambiguous shortcut overload“) - so tat Esc nichts,
        sobald das Kontextregister „Auswahl“ mit seiner Kopie von „Alles
        deselektieren“ vorn lag. Der Hinweis am Knopf nennt das Kuerzel
        trotzdem, denn die Taste tut, was der Knopf tut. Gibt zurueck, ob das
        Kuerzel vergeben wurde.
        """
        seq = QtGui.QKeySequence(kuerzel)
        if any(b.aktion.shortcut() == seq for b in self.befehle):
            return False
        a.setShortcut(seq)
        a.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        self.window().addAction(a)
        return True

    def kuerzel_liste(self) -> list:
        """Die Befehle, die ein Tastenkuerzel tragen, in der Reihenfolge der
        Register (02.10.2026) - die Liste unter Extras → Tastenkuerzel.

        Sie entsteht aus den Befehlen, nicht aus einem Text von Hand: ein
        neues Kuerzel steht beim naechsten Oeffnen der Liste darin. Ein Befehl
        ohne Kuerzel fehlt - auch die zweite Schaltflaeche „Alles
        deselektieren“ im Kontextregister, der :meth:`kuerzel_setzen` die
        Tastenfolge verweigert hat (jede Tastenfolge gehoert genau einem Befehl)."""
        reihe = {self.tabs.tabText(i): i for i in range(self.tabs.count())}
        tragen = [b for b in self.befehle if not b.aktion.shortcut().isEmpty()]
        # stabil: innerhalb eines Registers bleibt die Reihenfolge des Aufbaus
        return sorted(tragen, key=lambda b: reihe.get(b.register, len(reihe)))

    def aktion(self, register: str, text: str) -> QtGui.QAction:
        """Die Aktion des Befehls ``text`` im Register ``register``.

        Wer einen Befehl noch einmal zeigen will (:meth:`Gruppe.nochmal`),
        holt sich hier das Original, statt es beim Aufbau in eine Variable
        zu legen. Fehlt der Befehl oder gibt es ihn dort zweimal, meldet das
        ein ``KeyError`` beim Start des Programms - ein umbenannter Befehl
        faellt so sofort auf und laeuft nicht still ins Leere."""
        treffer = [b.aktion for b in self.befehle if b.register == register and b.text == text]
        if len(treffer) != 1:
            raise KeyError(f"Befehl „{text}“ im Register {register}: {len(treffer)} Treffer")
        return treffer[0]

    def suche_fokussieren(self) -> None:
        """Strg+F: den Cursor in die Befehlssuche setzen. Was schon darin
        steht, ist markiert - der naechste Buchstabe ersetzt es."""
        self.suche.setFocus(QtCore.Qt.ShortcutFocusReason)
        self.suche.selectAll()

    def merken(self, b: Befehl):
        self.befehle.append(b)
        # ein vorlaeufig aufgeklapptes Register klappt nach dem Befehl zu
        b.aktion.triggered.connect(lambda *_a: self._nach_befehl())

    def vorsicht(self, *aktionen: QtGui.QAction):
        """Diese Befehle ersetzen oder leeren das Modell: die Suche fuehrt sie
        nie aus, sie zeigt nur ihr Register."""
        for b in self.befehle:
            if b.aktion in aktionen:
                b.vorsicht = True

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
    # Bis zum 24.09.2026 fuehrte Enter den ersten Treffer irgendwo in Name,
    # Register, Gruppe oder Hinweis aus: „Spiel“ lud das Beispiel Rahmen
    # (Gruppe „Beispiele“ enthaelt „spiel“), „Kombination“ rechnete
    # (Hinweis von „Berechnen“). Jetzt: Suche am Wortanfang, Treffer im
    # Befehlsnamen zuerst, Enter nur bei genau einem Treffer im Namen, sonst
    # die Trefferliste; Modellersetzendes und Loeschendes nie direkt.
    def _suche_einrichten(self):
        """Die Trefferliste: der vorhandene Vervollstaendiger, aber mit der
        eigenen Treffermenge (Wortanfang, Synonyme) statt Qts Teiltext."""
        self._anzeige: dict[str, Befehl] = {}
        self._vervollstaendigung = QtWidgets.QCompleter([], self)
        self._vervollstaendigung.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self._vervollstaendigung.setCompletionMode(QtWidgets.QCompleter.UnfilteredPopupCompletion)
        self._vervollstaendigung.setMaxVisibleItems(14)
        # setWidget statt setCompleter: das Feld soll den gewaehlten Text nicht
        # uebernehmen und nicht selbst filtern, die Liste kommt von finden()
        self._vervollstaendigung.setWidget(self.suche)
        self._vervollstaendigung.activated[str].connect(self._treffer_gewaehlt)
        self.suche.textEdited.connect(self._liste_nachziehen)
        # Enter bei offener Liste behandelt allein _popup_taste (25.09.2026):
        # QCompleter gab die Taste zuerst ans Suchfeld (returnPressed ->
        # _suche_ausfuehren) und aktivierte danach die aktuelle Zeile - ein
        # Befehl mit einem Namenstreffer lief zweimal (Schalter blieb aus),
        # bei mehreren Treffern lief die erste Listenzeile. Ein spaeter
        # installierter Filter kommt vor dem des Vervollstaendigers dran.
        self._zeile_gewaehlt = False
        self._vervollstaendigung.popup().installEventFilter(self)

    def eventFilter(self, obj, ev):
        popup = getattr(self, "_vervollstaendigung", None)
        popup = popup.popup() if popup is not None else None
        if obj is popup and ev.type() == QtCore.QEvent.KeyPress:
            k = ev.key()
            if k in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down, QtCore.Qt.Key_PageUp,
                     QtCore.Qt.Key_PageDown):
                self._zeile_gewaehlt = True          # der Anwender waehlt eine Zeile
            elif k in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                self._popup_taste()
                return True
        return super().eventFilter(obj, ev)

    def _popup_taste(self):
        """Enter bei offener Trefferliste: die mit den Pfeiltasten gewaehlte
        Zeile ausfuehren, sonst wie Enter im Suchfeld (nur bei genau einem
        Namenstreffer, sonst bleibt die Liste stehen)."""
        idx = self._vervollstaendigung.popup().currentIndex()
        if self._zeile_gewaehlt and idx.isValid():
            return self._treffer_gewaehlt(str(idx.data()))
        return self._suche_ausfuehren()

    @staticmethod
    def anzeige(b: Befehl) -> str:
        """Die Zeile eines Befehls in der Trefferliste - mit Ort, denn manche
        Namen gibt es mehrfach („Einstellungen“)."""
        return f"{b.text}   ({b.ort_text()})"

    def namenstreffer(self, text: str) -> list:
        """Befehle, in deren Namen (oder Synonymen) jedes Suchwort am
        Wortanfang steht."""
        such = woerter(text)
        if not such:
            return []
        return [b for b in self.befehle
                if all(any(wort_passt(w, x) for x in b.namenswoerter()) for w in such)]

    def finden(self, text: str) -> list[Befehl]:
        """Alle Treffer: gleichlautender Name, dann Treffer im Namen, dann in
        Register, Gruppe und Hinweis - jeweils am Wortanfang."""
        such = woerter(text)
        if not such:
            return []
        t = (text or "").strip().lower()
        genau = [b for b in self.befehle if b.text.lower() == t]
        namen = [b for b in self.namenstreffer(text) if b not in genau]
        rest = [b for b in self.befehle if b not in genau and b not in namen
                and all(any(wort_passt(w, x) for x in b.alle_woerter()) for w in such)]
        return genau + namen + rest

    def _liste_nachziehen(self, text: str = None):
        """Beim Tippen: die Trefferliste auf den eingegebenen Text setzen."""
        text = self.suche.text() if text is None else text
        treffer = self.finden(text)
        self._anzeige = {self.anzeige(b): b for b in treffer}
        self._vervollstaendigung.setModel(QtCore.QStringListModel(list(self._anzeige), self._vervollstaendigung))
        self._zeile_gewaehlt = False
        if treffer:
            self._vervollstaendigung.complete()
            # complete() macht Zeile 0 zur aktuellen - keine Zeile ist gewaehlt,
            # bis der Anwender eine mit den Pfeiltasten oder der Maus nimmt
            self._vervollstaendigung.popup().setCurrentIndex(QtCore.QModelIndex())
        else:
            self._vervollstaendigung.popup().hide()
        return treffer

    def _suche_ausfuehren(self):
        """Enter im Suchfeld."""
        text = self.suche.text().strip()
        if not text:
            return
        if text in self._anzeige:                  # eine Zeile der Liste steht im Feld
            return self._ausfuehren(self._anzeige[text])
        treffer = self.finden(text)
        if not treffer:
            self._vervollstaendigung.popup().hide()
            self.gesucht.emit("")
            return
        namen = self.namenstreffer(text)
        if len(namen) == 1:
            return self._ausfuehren(namen[0])
        self._liste_nachziehen(text)
        self.meldung.emit(f"Befehlssuche: {len(treffer)} Treffer für „{text}“ – "
                          "den gemeinten in der Liste wählen")

    def _treffer_gewaehlt(self, zeile: str):
        """Eine Zeile der Trefferliste gewaehlt (Enter oder Klick) - nur aus
        der gezeigten Liste: der Rueckgriff ueber alle Befehle fand den
        Befehl auch nach einer schon ausgefuehrten Suche noch einmal."""
        b = self._anzeige.get(zeile)
        if b is not None:
            self._ausfuehren(b)

    def _ausfuehren(self, b: Befehl):
        self._vervollstaendigung.popup().hide()
        if not b.ort:
            self.zeigen(b.register)
        self.suche.clear()
        self._anzeige = {}
        if b.nicht_aus_suche():
            self.meldung.emit(f"„{b.text}“ ersetzt oder löscht Modellinhalt und läuft darum nicht "
                              f"direkt aus der Suche – der Knopf steht im Register {b.register} › {b.gruppe}")
            return
        self.gesucht.emit(b.text)
        b.aktion.trigger()


#: Zusatz zum Stilblatt: Aussehen des Ribbons
STIL = """
QWidget#ribbon {{ background: {flaeche}; border-bottom: 1px solid {linie}; }}
QTabWidget#ribbontabs::pane {{ border: 0; border-top: 1px solid {linie};
    background: {flaeche}; }}
/* Reiter 9 px statt 14 px Innenabstand (25.09.2026): mit dem Kontextregister
   „Auswahl: 12 Knoten“ brauchte die Registerzeile 1371 px - bei 1280 px
   erschienen Rollpfeile, und gerade dieser Reiter lag dahinter. Mit 10 px
   waeren es offscreen 1243 px, unter Windows bis 2,9 % mehr - zu knapp. */
QTabWidget#ribbontabs > QTabBar::tab {{ background: transparent; border: 0;
    padding: 6px 9px; margin: 0 1px; color: {matt}; font-weight: 600; }}
QTabWidget#ribbontabs > QTabBar::tab:selected {{ color: {akzent};
    border-bottom: 2px solid {akzent}; }}
QTabWidget#ribbontabs > QTabBar::tab:hover {{ color: {text}; }}
QWidget#ribbongruppe {{ background: transparent; }}
QLabel#gruppentitel {{ color: {matt}; font-size: 10px; }}
/* Beschriftung eines Auswahlfelds im Kontextregister (Gruppe.beschriftet) */
QLabel#ribbonfeldname {{ color: {matt}; font-size: 12px; }}
QLabel#kontextgewaehlt {{ color: {text}; font-size: 12px; }}
QFrame#ribbontrenner {{ color: {linie}; margin: 4px 3px 2px; }}
QToolButton#ribbongross {{ border: 1px solid transparent; border-radius: 8px;
    padding: 4px 6px; font-size: 11px; }}
QToolButton#ribbongross:hover {{ background: {akzent_hell}; border-color: {linie}; }}
QToolButton#ribbongross:checked {{ background: {akzent_hell}; color: {akzent};
    border-color: {akzent}; }}
QToolButton#ribbongross::menu-indicator {{ image: none; width: 0px; }}
QToolButton#ribbongross[rolle="start"] {{ background: {akzent}; color: #fff;
    border-color: {akzent}; font-weight: 600; }}
QToolButton#ribbongross[rolle="start"]:hover {{ background: #0f4f9a; }}
QToolButton#ribbonklein {{ border: 1px solid transparent; border-radius: 6px;
    padding: 1px 8px 1px 4px; font-size: 12px; text-align: left; }}
QToolButton#ribbonklein:hover {{ background: {akzent_hell}; border-color: {linie}; }}
QToolButton#ribbonklein:checked {{ background: {akzent_hell}; color: {akzent};
    border-color: {akzent}; }}
/* Auswahlfelder in der Spalte der kleinen Knoepfe: so hoch wie diese (21 px),
   das allgemeine Feld (5 px Innenabstand) waere 29 px hoch (25.09.2026) */
QComboBox[ribbonzeile="true"], QDoubleSpinBox[ribbonzeile="true"] {{
    padding: 1px 6px; border-radius: 6px; font-size: 12px; }}
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
