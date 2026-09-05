"""
Erscheinungsbild des Programmfensters (Entwurf „Werkbank").

Hier steht alles, was nur mit dem Aussehen und der Anordnung zu tun hat:
die Farben, das Stilblatt fuer Qt, die dunkle Kopfzeile, die Werkzeugleiste,
der Modellbaum und der Filmstreifen der Stellungen. Die Rechen- und
Eingabelogik bleibt in main.py.

Die Aufteilung folgt dem Entwurf: oben die dunkle Kopfzeile mit Programmname,
Bauteil und Zustand, darunter die Werkzeugleiste, dann drei Spalten -
Modellbaum links, 3D-Ansicht mit dem Filmstreifen der Stellungen in der Mitte,
die Eingaben rechts - und unten Protokoll und Tabellen.
"""
from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

#: Farben des Entwurfs
FARBEN = {
    "kopf": "#1c2733",
    "kopf_text": "#ffffff",
    "kopf_matt": "#b9c4cf",
    "grund": "#f4f6f8",
    "flaeche": "#ffffff",
    "linie": "#dde3e8",
    "text": "#1d2731",
    "matt": "#66717c",
    "akzent": "#1467c6",
    "akzent_hell": "#eaf2fc",
    "akzent2": "#e5701c",
    "gut": "#2e8b3a",
    "schlecht": "#c62828",
    "warn": "#b7791f",
    "ansicht": "#e9edf1",
}

#: Stilblatt fuer das ganze Fenster
STIL = """
QMainWindow, QWidget {{ background: {grund}; color: {text};
    font-family: "Segoe UI", -apple-system, Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px; }}
/* Kopfbereich: der Grund kommt vom Behaelter, die Beschriftungen bleiben
   durchsichtig - sonst zieht die allgemeine QWidget-Regel oben sie hell. */
QWidget#kopfhalter {{ background: {kopf}; }}
Kopfzeile {{ background: {kopf}; }}
Kopfzeile QLabel {{ background: transparent; color: {kopf_matt}; }}
Filmstreifen {{ background: {flaeche}; border-top: 1px solid {linie}; }}
Filmstreifen > QLabel {{ background: transparent; }}
QMenuBar {{ background: {kopf}; color: {kopf_matt}; border: 0; padding: 2px 6px; }}
QMenuBar::item {{ background: transparent; padding: 5px 10px; border-radius: 6px; }}
QMenuBar::item:selected, QMenuBar::item:pressed {{ background: #39485a; color: #fff; }}
QMenuBar::item:disabled {{ color: #6b7885; }}
QMenu {{ background: {flaeche}; border: 1px solid {linie}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {akzent_hell}; color: {akzent}; }}
QMenu::separator {{ height: 1px; background: {linie}; margin: 4px 6px; }}

QToolBar {{ background: {flaeche}; border: 0; border-bottom: 1px solid {linie};
    spacing: 6px; padding: 6px 10px; }}
QToolBar QToolButton {{ background: #f7f9fb; border: 1px solid {linie};
    border-radius: 8px; padding: 6px 11px; font-weight: 600; color: {text}; }}
QToolBar QToolButton:hover {{ background: {akzent_hell}; border-color: {akzent};
    color: {akzent}; }}
QToolBar QToolButton:checked {{ background: {akzent_hell}; border-color: {akzent};
    color: {akzent}; }}
QToolBar QToolButton#start {{ background: {akzent}; border-color: {akzent};
    color: #fff; padding: 6px 13px; }}
QToolBar QToolButton#start:hover {{ background: #0f4f9a; }}

QDockWidget {{ titlebar-close-icon: none; titlebar-normal-icon: none; }}
QDockWidget::title {{ background: {flaeche}; color: {matt}; padding: 7px 10px;
    border-bottom: 1px solid {linie}; text-transform: uppercase;
    font-size: 11px; font-weight: 600; letter-spacing: 0.5px; }}

QTabWidget::pane {{ border: 0; border-top: 1px solid {linie}; background: {flaeche}; }}
QTabBar {{ background: {flaeche}; }}
QTabBar::tab {{ background: transparent; color: {matt}; padding: 8px 12px;
    border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {akzent}; border-bottom: 2px solid {akzent}; }}
QTabBar::tab:hover {{ color: {text}; }}
QTabBar#gruppenleiste {{ background: {grund}; border-bottom: 1px solid {linie}; }}
QTabBar#gruppenleiste::tab {{ padding: 5px 14px; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.4px; color: {matt};
    border-bottom: 2px solid transparent; }}
QTabBar#gruppenleiste::tab:selected {{ color: {akzent}; background: {flaeche};
    border-bottom: 2px solid {akzent}; }}
QTabWidget#tabellenregister::pane {{ border-top: 0; }}
QTabWidget#tabellenregister QTabBar::tab {{ padding: 5px 11px; font-weight: 500; }}

QGroupBox {{ background: {flaeche}; border: 1px solid {linie}; border-radius: 10px;
    margin-top: 12px; padding: 10px 10px 8px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
    color: {text}; }}

QPushButton {{ background: #f7f9fb; border: 1px solid {linie}; border-radius: 8px;
    padding: 7px 12px; font-weight: 600; min-height: 20px; }}
QPushButton:hover {{ background: {akzent_hell}; border-color: {akzent}; color: {akzent}; }}
QPushButton:pressed {{ background: #dce9f8; }}
QPushButton:disabled {{ color: #a9b6c2; background: #f2f4f6; }}
QPushButton[rolle="start"] {{ background: {akzent}; border-color: {akzent}; color: #fff; }}
QPushButton[rolle="start"]:hover {{ background: #0f4f9a; }}
QPushButton[rolle="warn"] {{ background: {akzent2}; border-color: {akzent2}; color: #fff; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {flaeche}; border: 1px solid {linie}; border-radius: 8px;
    padding: 5px 7px; selection-background-color: {akzent}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {akzent}; }}
QComboBox::drop-down {{ border: 0; width: 18px; }}
QCheckBox, QRadioButton {{ spacing: 6px; }}

QTableWidget, QTreeWidget, QListWidget {{ background: {flaeche};
    border: 1px solid {linie}; border-radius: 8px; gridline-color: {linie};
    selection-background-color: {akzent_hell}; selection-color: {text}; }}
QHeaderView::section {{ background: #f0f3f6; color: {text}; border: 0;
    border-bottom: 1px solid {linie}; border-right: 1px solid {linie};
    padding: 5px 8px; font-weight: 600; }}
QTreeWidget {{ border: 0; }}
QTreeWidget::item {{ padding: 3px 2px; }}

QScrollArea {{ border: 0; background: {grund}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #c5cdd5; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #c5cdd5; border-radius: 5px; min-width: 24px; }}

QStatusBar {{ background: {flaeche}; border-top: 1px solid {linie}; color: {matt}; }}
QStatusBar::item {{ border: 0; }}
QProgressBar {{ border: 1px solid {linie}; border-radius: 6px; background: {grund};
    height: 14px; text-align: center; }}
QProgressBar::chunk {{ background: {akzent}; border-radius: 5px; }}
QSplitter::handle {{ background: {linie}; }}
QToolTip {{ background: {kopf}; color: #fff; border: 0; padding: 5px 7px; }}
"""


def stil() -> str:
    return STIL.format(**FARBEN)


class Marke(QtWidgets.QLabel):
    """Rundes Etikett wie im Entwurf (z. B. „5 Stellungen", „berechnet")."""

    def __init__(self, text: str = "", art: str = "matt", parent=None):
        super().__init__(text, parent)
        self.setArt(art)

    def setArt(self, art: str):
        farbe = {"matt": ("#39485a", "#e6edf3"), "gut": (FARBEN["gut"], "#fff"),
                 "warn": (FARBEN["akzent2"], "#fff"),
                 "schlecht": (FARBEN["schlecht"], "#fff"),
                 "akzent": (FARBEN["akzent"], "#fff")}.get(art, ("#39485a", "#e6edf3"))
        self.setStyleSheet(f"background:{farbe[0]}; color:{farbe[1]}; border-radius:10px;"
                           f"padding:3px 10px; font-size:12px;")


def kopfhalter(parent, *widgets) -> QtWidgets.QWidget:
    """Behaelter fuer Kopfzeile und Menueleiste, durchgehend dunkel.

    Ohne eigenen Grund zeichnet Qt hier die Fensterfarbe; unter Windows wird die
    Zeile dadurch weiss, sobald ein Menue geoeffnet ist.
    """
    w = QtWidgets.QWidget(parent)
    w.setObjectName("kopfhalter")
    w.setAttribute(QtCore.Qt.WA_StyledBackground, True)
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    for x in widgets:
        lay.addWidget(x)
    return w


class Kopfzeile(QtWidgets.QWidget):
    """Dunkle Kopfzeile: Programmname, Bauteil und Zustand."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setFixedHeight(40)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 12, 0)
        lay.setSpacing(12)
        self.logo = QtWidgets.QLabel("Statik3D")
        self.logo.setStyleSheet(f"color:{FARBEN['kopf_text']}; font-weight:700;"
                                "font-size:16px; letter-spacing:.3px;")
        self.titel = QtWidgets.QLabel("")
        self.titel.setStyleSheet(f"color:{FARBEN['kopf_matt']}; font-size:13px;")
        lay.addWidget(self.logo)
        lay.addWidget(self.titel, 1)
        self.marke_modell = Marke("", "matt")
        self.marke_zustand = Marke("bereit", "matt")
        lay.addWidget(self.marke_modell)
        lay.addWidget(self.marke_zustand)

    def setzen(self, titel: str, modell: str = "", zustand: str = "",
               art: str = "matt"):
        self.titel.setText(titel)
        self.marke_modell.setText(modell)
        self.marke_modell.setVisible(bool(modell))
        if zustand:
            self.marke_zustand.setText(zustand)
            self.marke_zustand.setArt(art)
        self.marke_zustand.setVisible(bool(zustand))


class Stellungskarte(QtWidgets.QFrame):
    """Eine Karte des Filmstreifens: Kennung, Winkel, Name und Ausnutzung."""

    geklickt = QtCore.Signal(str)

    def __init__(self, kennung: str, name: str, winkel: float, eta=None,
                 fuehrt: bool = False, parent=None):
        super().__init__(parent)
        self.name = name
        self.fuehrt = bool(fuehrt)
        self.aktiv = False
        self.setFixedWidth(140)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._faerben()
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(9, 7, 9, 7)
        lay.setSpacing(2)
        oben = QtWidgets.QHBoxLayout()
        kn = QtWidgets.QLabel(kennung + (" ★" if fuehrt else ""))
        kn.setStyleSheet(f"background:{FARBEN['kopf']}; color:#fff; border-radius:4px;"
                         "padding:2px 6px; font-size:11px; font-weight:600;")
        oben.addWidget(kn)
        oben.addStretch(1)
        if eta is not None:
            farbe = (FARBEN["schlecht"] if eta > 1 else
                     FARBEN["warn"] if eta > 0.85 else FARBEN["gut"])
            e = QtWidgets.QLabel(f"η {eta:.2f}".replace(".", ","))
            e.setStyleSheet(f"background:{farbe}; color:#fff; border-radius:9px;"
                            "padding:2px 7px; font-size:11px; font-weight:600;")
            oben.addWidget(e)
        lay.addLayout(oben)
        gr = QtWidgets.QLabel(f"{winkel:.1f}°".replace(".", ","))
        gr.setStyleSheet("font-size:19px; font-weight:600; border:0;")
        lay.addWidget(gr)
        nm = QtWidgets.QLabel(name)
        nm.setStyleSheet(f"color:{FARBEN['matt']}; font-size:12px; border:0;")
        nm.setToolTip(name)
        lay.addWidget(nm)

    def _faerben(self):
        """Rand nach Zustand: gewaehlt (Akzent), massgebend (Akzent 2), sonst Linie."""
        rand = (FARBEN["akzent"] if self.aktiv else
                FARBEN["akzent2"] if self.fuehrt else FARBEN["linie"])
        dicke = 2 if self.aktiv else 1
        self.setStyleSheet(
            f"QFrame {{ background:{FARBEN['flaeche']}; border:{dicke}px solid {rand};"
            f"border-radius:10px; }}")

    def setzen_aktiv(self, an: bool):
        if bool(an) != self.aktiv:
            self.aktiv = bool(an)
            self._faerben()

    def mousePressEvent(self, ev):
        self.geklickt.emit(self.name)
        super().mousePressEvent(ev)


class Filmstreifen(QtWidgets.QWidget):
    """Die Stellungen des Systems als Karten unter der Ansicht."""

    gewaehlt = QtCore.Signal(str)
    neu = QtCore.Signal()
    rechnen = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        aussen = QtWidgets.QVBoxLayout(self)
        aussen.setContentsMargins(12, 8, 12, 10)
        aussen.setSpacing(6)
        kopf = QtWidgets.QHBoxLayout()
        t = QtWidgets.QLabel("STELLUNGEN DES SYSTEMS")
        t.setStyleSheet(f"color:{FARBEN['matt']}; font-size:11px; font-weight:600;"
                        "letter-spacing:.5px;")
        kopf.addWidget(t)
        self.lbl_umh = QtWidgets.QLabel("")
        self.lbl_umh.setStyleSheet(f"color:{FARBEN['matt']}; font-size:12px;")
        kopf.addStretch(1)
        kopf.addWidget(self.lbl_umh)
        b_neu = QtWidgets.QPushButton("+ Stellung")
        b_neu.clicked.connect(self.neu.emit)
        b_rech = QtWidgets.QPushButton("▶ rechnen")
        b_rech.setProperty("rolle", "start")
        b_rech.clicked.connect(self.rechnen.emit)
        kopf.addWidget(b_neu)
        kopf.addWidget(b_rech)
        aussen.addLayout(kopf)
        self.bereich = QtWidgets.QScrollArea()
        self.bereich.setWidgetResizable(True)
        self.bereich.setFixedHeight(96)
        self.bereich.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.bereich.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.inhalt = QtWidgets.QWidget()
        self.reihe = QtWidgets.QHBoxLayout(self.inhalt)
        self.reihe.setContentsMargins(0, 0, 0, 0)
        self.reihe.setSpacing(8)
        self.reihe.addStretch(1)
        self.bereich.setWidget(self.inhalt)
        aussen.addWidget(self.bereich)

    def fuellen(self, stellungen: list, umhuellende: str = ""):
        """stellungen: [{name, winkel, eta, fuehrt}]"""
        while self.reihe.count():
            p = self.reihe.takeAt(0)
            if p.widget():
                # Nur ausblenden und zum Loeschen vormerken: setParent(None)
                # wuerde die Karte zu einem eigenen Fenster machen.
                p.widget().hide()
                p.widget().deleteLater()
        if not stellungen:
            hin = QtWidgets.QLabel("noch keine Stellung angelegt – „+ Stellung“")
            hin.setStyleSheet(f"color:{FARBEN['matt']};")
            self.reihe.addWidget(hin)
        for i, s in enumerate(stellungen, 1):
            k = Stellungskarte(f"S{i}", s.get("name", ""), float(s.get("winkel", 0.0)),
                               s.get("eta"), bool(s.get("fuehrt")))
            k.geklickt.connect(self.gewaehlt.emit)
            self.reihe.addWidget(k)
        self.reihe.addStretch(1)
        self.lbl_umh.setText(umhuellende)
        if getattr(self, "_gewaehlt", ""):
            self.waehlen(self._gewaehlt)

    def waehlen(self, name: str):
        """Die Karte dieser Stellung hervorheben, die anderen zuruecknehmen."""
        self._gewaehlt = name
        for k in self.inhalt.findChildren(Stellungskarte):
            k.setzen_aktiv(k.name == name)


def _kurz(punkt) -> str:
    """Koordinaten knapp: „2 | 0 | 0". Rundungsschrott wie 1.2e-16 wird zu 0."""
    teile = []
    for v in np.asarray(punkt, float).ravel()[:3]:
        v = 0.0 if abs(v) < 1e-12 else float(v)
        teile.append(f"{v:.4g}")
    return " | ".join(teile)


#: Wie viele Einzeleintraege ein Zweig hoechstens ausklappt. Darueber steht
#: eine Sammelzeile; die vollstaendige Liste steht in der Tabelle unten, wo
#: sie gefiltert und sortiert werden kann.
#: So viele Eintraege je Zweig - alle Knoten, Linien, Staebe, Flaechen und
#: Volumen stehen numerisch untereinander; erst jenseits dieser Zahl kommt
#: der Verweis auf die Tabelle.
BAUM_MAX = 20000


def _natuerlich(name) -> list:
    """Sortierschluessel, der Zahlen als Zahlen liest: K2 vor K10, F9 vor F10."""
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(name))]



class Modellbaum(QtWidgets.QTreeWidget):
    """Der Modellbaum links: **alles**, was im Modell modelliert werden kann.

    Knoten, Linien, Staebe, Flaechen, Volumen, Lager (Knoten, Linie, Flaeche),
    Gelenke, Kontaktbedingungen, Querschnitte, Werkstoffe, Dicken, Lastfaelle,
    Kombinationen und die Nachweisobjekte stehen hier mit ihrer Anzahl.

    Ein **Klick** waehlt den Zweig aus (und zeigt die zugehoerige Tabelle oder
    Maske), ein **Doppelklick** oeffnet ihn zum Bearbeiten. Beides laeuft ueber
    zwei Signale, damit das Fenster entscheidet, was daraus wird.
    """

    angeklickt = QtCore.Signal(str, str)      # (Art, Name)
    bearbeiten = QtCore.Signal(str, str)      # (Art, Name) - Doppelklick
    neu = QtCore.Signal(str)                  # Zweigart: ein neues Objekt anlegen
    loeschen = QtCore.Signal(str, str)        # (Art, Name): Objekt loeschen

    #: Zweige, unter denen sich per Rechtsklick ein neues Objekt anlegen laesst
    NEU_ARTEN = {"querschnitte": "Querschnitt", "subsysteme": "Subsystem",
                 "situationen": "Situation", "generierer": "Wasserdruck",
                 "knoten": "Knoten", "linien": "Linie", "stabelemente": "Stab",
                 "staebe": "Stab mit Nachweis", "geoflaechen": "Fläche",
                 "geokoerper": "Volumen", "schweissnaehte": "Schweißnaht",
                 "bemassungen": "Linearmaß"}
    #: Eintraege, die sich per Rechtsklick oder Entf loeschen lassen
    LOESCH_ARTEN = {"querschnitt", "knoten", "linie", "stabelement", "stab", "geoflaeche",
                    "geokoerper_einzeln", "subsystem", "situation", "wasserdruck", "wind",
                    "schweissnaht", "bemassung"}
    #: Eintragsart -> Zweigart (fuer "Neu" aus einem Eintrag heraus)
    ELTERNART = {"knoten": "knoten", "linie": "linien", "stabelement": "stabelemente",
                 "stab": "staebe", "geoflaeche": "geoflaechen",
                 "geokoerper_einzeln": "geokoerper", "querschnitt": "querschnitte",
                 "subsystem": "subsysteme", "situation": "situationen",
                 "wasserdruck": "generierer", "wind": "generierer",
                 "schweissnaht": "schweissnaehte", "bemassung": "bemassungen"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        self.setRootIsDecorated(True)
        self.setIndentation(14)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        # Die zweite Spalte traegt Zusatzangaben (Anzahl, Koordinaten, Bezug).
        # Ohne Deckel frisst eine lange Angabe die ganze Breite und der Name in
        # Spalte 0 verschwindet - der Baum waere dann unlesbar.
        self.header().setMaximumSectionSize(120)
        self.setTextElideMode(QtCore.Qt.ElideRight)
        self.itemClicked.connect(self._klick)
        self.itemDoubleClicked.connect(self._doppelklick)

    @staticmethod
    def _schluessel(item) -> tuple[str, str]:
        art = str(item.data(0, QtCore.Qt.UserRole) or "")
        name = item.data(0, QtCore.Qt.UserRole + 1)
        return art, str(name if name is not None else item.text(0))

    @staticmethod
    def _ist_eintrag(item) -> bool:
        """Ein Eintrag meint ein einzelnes Objekt (traegt einen Schluessel);
        ein Zweig meint die Art."""
        return item is not None and item.data(0, QtCore.Qt.UserRole + 1) is not None

    def _klick(self, item, _spalte):
        art, name = self._schluessel(item)
        if art:
            self.angeklickt.emit(art, name)

    def _menu(self, pos):
        """Rechtsklick: Neu am Zweig, Bearbeiten und Loeschen am Eintrag."""
        item = self.itemAt(pos)
        if item is None:
            return
        art, name = self._schluessel(item)
        menu = QtWidgets.QMenu(self)
        eintrag = self._ist_eintrag(item)
        zweigart = self.ELTERNART.get(art, art) if eintrag else art
        if zweigart in self.NEU_ARTEN:
            a = menu.addAction(f"Neu: {self.NEU_ARTEN[zweigart]} …")
            a.triggered.connect(lambda _c=False, z=zweigart: self.neu.emit(z))
        if eintrag and art in self.LOESCH_ARTEN:
            b = menu.addAction("Bearbeiten …")
            b.triggered.connect(lambda _c=False: self.bearbeiten.emit(art, name))
            menu.addSeparator()
            d = menu.addAction("Löschen (Entf)")
            d.triggered.connect(lambda _c=False: self.loeschen.emit(art, name))
        if menu.actions():
            menu.exec(self.viewport().mapToGlobal(pos))

    def keyPressEvent(self, ev):
        if ev.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            item = self.currentItem()
            if item is not None and self._ist_eintrag(item):
                art, name = self._schluessel(item)
                if art in self.LOESCH_ARTEN:
                    self.loeschen.emit(art, name)
                    return
        super().keyPressEvent(ev)

    def _doppelklick(self, item, _spalte):
        art, name = self._schluessel(item)
        if art:
            self.bearbeiten.emit(art, name)

    def _zweig(self, eltern, text, zahl="", art="", fett=False, farbe=None,
               schluessel=None, hinweis=""):
        it = QtWidgets.QTreeWidgetItem(eltern, [text, str(zahl)])
        it.setData(0, QtCore.Qt.UserRole, art)
        if schluessel is not None:
            it.setData(0, QtCore.Qt.UserRole + 1, str(schluessel))
        if fett:
            f = it.font(0)
            f.setBold(True)
            it.setFont(0, f)
        it.setForeground(1, QtGui.QColor(FARBEN["matt"]))
        if farbe:
            it.setForeground(0, QtGui.QColor(farbe))
        if hinweis:
            it.setToolTip(0, hinweis)
        return it

    def _liste(self, eltern, eintraege, art, sammelart=""):
        """Eintraege unter einen Zweig haengen, gedeckelt auf BAUM_MAX."""
        for i, (text, zahl, key, tip) in enumerate(eintraege):
            if i >= BAUM_MAX:
                self._zweig(eltern, f"… {len(eintraege) - BAUM_MAX} weitere",
                            "", sammelart or art, farbe=FARBEN["matt"],
                            hinweis="Die vollständige Liste steht in der "
                                    "Tabelle unten – dort mit Filter.")
                break
            self._zweig(eltern, text, zahl, art, schluessel=key, hinweis=tip)

    # -- Beschriftungen ---------------------------------------------------
    @staticmethod
    def _lagertext(support) -> str:
        namen = ["ux", "uy", "uz", "φx", "φy", "φz"]
        teile = []
        for d in range(6):
            b = support.dof_behaviour(d)
            if getattr(b, "acts", False):
                teile.append(namen[d])
        return ", ".join(teile) or "frei"

    def fuellen(self, model, stellungen: list = None, ergebnisse: dict = None):
        offen = {}

        def merken(it):
            offen[it.text(0)] = it.isExpanded()
            for i in range(it.childCount()):
                merken(it.child(i))

        for i in range(self.topLevelItemCount()):
            merken(self.topLevelItem(i))
        self.clear()
        wurzel = self._zweig(self, model.name or "Modell", f"{model.nn} Kn",
                             "modell", fett=True)

        # ---- Knoten, Linien, Staebe, Flaechen, Volumen ---------------------
        # Je ein eigener Zweig, alle Eintraege numerisch untereinander - ohne
        # Gruppen "Geometrie" und "Elemente" dazwischen. Unter "Staebe" stehen
        # die Stabelemente und, als erster Eintrag, die Staebe mit Nachweis.
        kn = self._zweig(wurzel, "Knoten", model.nn, "knoten", fett=True,
                         hinweis="Klick wählt alle Knoten, ein Eintrag den einen. "
                                 "Rechtsklick: Neu, Löschen.")
        self._liste(kn, [(f"K{i}", _kurz(model.nodes[i]), str(i),
                          "Knoten {}: x = {:.4f}  y = {:.4f}  z = {:.4f} m".format(
                              i, *model.nodes[i]))
                         for i in range(model.nn)], "knoten")
        lin = self._zweig(wurzel, "Linien", len(model.lines), "linien", fett=True)
        self._liste(lin, [(name, f"{ln.typ} · {len(ln.nodes)}", name,
                           f"{name}: {ln.typ} über {len(ln.nodes)} Knoten")
                          for name, ln in sorted(model.lines.items(),
                                                 key=lambda kv: _natuerlich(kv[0]))],
                    "linie", "linien")
        stab_els = [(i, e) for i, e in enumerate(model.elements) if e.typ in ("beam", "truss")]
        st = self._zweig(wurzel, "Stäbe", len(stab_els), "stabelemente", fett=True,
                         hinweis="Stabelemente (Balken und Fachwerkstäbe); darunter "
                                 "die Stäbe mit Nachweis")
        mem = self._zweig(st, "Stäbe mit Nachweis", len(model.members), "staebe",
                          hinweis="Physische Stäbe (Ketten von Stabelementen) für die "
                                  "Nachweise nach EC3")
        self._liste(mem, [(name, f"{len(mm.elements)} El", name,
                           f"{name}: {len(mm.elements)} Elemente")
                          for name, mm in sorted(model.members.items(),
                                                 key=lambda kv: _natuerlich(kv[0]))],
                    "stab", "staebe")
        naehte = getattr(model, "schweissnaehte", {}) or {}
        nz = self._zweig(st, "Schweißnähte", len(naehte), "schweissnaehte",
                         farbe=FARBEN["akzent"] if naehte else None,
                         hinweis="Nahtart, Lage und Ausführung → Kerbfall nach EN 1993-1-9; "
                                 "„äquivalent“ = Ersatznaht für alle nicht einzeln "
                                 "modellierten Nähte. Rechtsklick: Neu, Löschen.")
        self._liste(nz, [(name, x.bezug(), name, f"Schweißnaht {name}: {x.bezug()}")
                         for name, x in naehte.items()], "schweissnaht", "schweissnaehte")
        self._zweig(nz, "+ Schweißnaht anlegen", "", "schweissnaht_neu", farbe=FARBEN["akzent"])
        self._liste(st, [(f"E{i}", (e.sec or "") if e.typ == "beam" else f"Fachwerk {e.sec or ''}",
                          str(i), "Element {}: {} K{}–K{}, {}, {}".format(
                              i, "Balken" if e.typ == "beam" else "Fachwerkstab",
                              e.nodes[0], e.nodes[-1], e.sec or "-", e.mat or "-"))
                         for i, e in stab_els], "stabelement", "stabelemente")
        gf = getattr(model, "flaechen", {}) or {}
        fl = self._zweig(wurzel, "Flächen", len(gf), "geoflaechen", fett=True)
        n_schalen = sum(1 for e in model.elements if e.typ in ("shell3", "shell4"))
        if n_schalen:
            self._zweig(fl, "Flächenelemente", n_schalen, "flaechen",
                        hinweis="Schalenelemente aller Flächen")
        self._liste(fl, [(name + ("" if x.elemente else " ○"), x.bezug(), name,
                          f"{name}: {x.bezug()}"
                          + ("" if x.elemente else "\nnoch nicht vernetzt"))
                         for name, x in sorted(gf.items(), key=lambda kv: _natuerlich(kv[0]))],
                    "geoflaeche", "geoflaechen")
        gk = getattr(model, "koerper", {}) or {}
        vo = self._zweig(wurzel, "Volumen", len(gk), "geokoerper", fett=True)
        n_vol = sum(1 for e in model.elements if e.typ in ("tet4", "tet10", "hex8"))
        if n_vol:
            self._zweig(vo, "Volumenelemente", n_vol, "volumen",
                        hinweis="Volumenelemente (Tetraeder, Hexaeder) aller Körper")
        self._liste(vo, [(name + ("" if x.elemente else " ○"), x.bezug(), name,
                          f"{name}: {x.bezug()}"
                          + ("" if x.elemente else "\nnoch nicht vernetzt"))
                         for name, x in sorted(gk.items(), key=lambda kv: _natuerlich(kv[0]))],
                    "geokoerper_einzeln", "geokoerper")

        # ---- Bemassungen ---------------------------------------------------
        bms = getattr(model, "bemassungen", {}) or {}
        bz = self._zweig(wurzel, "Bemaßungen", len(bms), "bemassungen", fett=bool(bms),
                         hinweis="Linearmaße, Maßketten, Höhenkoten, Winkel und Radien "
                                 "(Register Messen); Klick bearbeitet, Entf löscht")
        self._liste(bz, [(name, x.bezug(), name, f"{name}: {x.bezug()}")
                         for name, x in bms.items()], "bemassung", "bemassungen")
        self._zweig(bz, "+ Linearmaß anlegen", "", "bemassung_neu", farbe=FARBEN["akzent"])

        # ---- Eigenschaften ----------------------------------------------
        eig = self._zweig(wurzel, "Eigenschaften", "", "modell", fett=True)
        qs = self._zweig(eig, "Querschnitte", len(model.sections), "querschnitte")
        self._liste(qs, [(name, getattr(x, "typ", "") or "", name,
                          f"{name}: A = {getattr(x, 'A', 0) * 1e4:.1f} cm²")
                         for name, x in model.sections.items()], "querschnitt",
                    "querschnitte")
        wk = self._zweig(eig, "Werkstoffe", len(model.materials), "werkstoffe")
        self._liste(wk, [(name, getattr(x, "grade", "") or "", name,
                          f"{name}: E = {getattr(x, 'E', 0) / 1e9:.0f} GPa")
                         for name, x in model.materials.items()], "werkstoff",
                    "werkstoffe")
        dk = self._zweig(eig, "Dicken", len(model.shells), "dicken")
        self._liste(dk, [(name, f"{getattr(x, 't', 0) * 1e3:g} mm", name,
                          f"{name}: t = {getattr(x, 't', 0) * 1e3:g} mm")
                         for name, x in model.shells.items()], "dicke", "dicken")

        # ---- Lager und Kopplungen ---------------------------------------
        n_lager = (len(model.supports) + len(model.line_supports)
                   + len(model.surface_supports))
        lg = self._zweig(wurzel, "Lager", n_lager, "lager", fett=True)
        kl = self._zweig(lg, "Knotenlager", len(model.supports), "lager")
        self._liste(kl, [(x.name or f"Lager {i + 1}", f"K{x.node}", str(i),
                          f"Knoten {x.node}: {self._lagertext(x)}")
                         for i, x in enumerate(model.supports)], "lager_einzeln",
                    "lager")
        if model.line_supports:
            ll = self._zweig(lg, "Linienlager", len(model.line_supports),
                             "linienlager")
            self._liste(ll, [(x.name or f"Linienlager {i + 1}",
                              f"{len(x.nodes)} Kn", str(i),
                              f"{len(x.nodes)} Knoten: {self._lagertext(x)}")
                             for i, x in enumerate(model.line_supports)],
                        "linienlager_einzeln", "linienlager")
        if model.surface_supports:
            fl = self._zweig(lg, "Flächenlager", len(model.surface_supports),
                             "flaechenlager")
            self._liste(fl, [(x.name or f"Flächenlager {i + 1}",
                              f"{len(x.nodes)} Kn", str(i),
                              f"{len(x.nodes)} Knoten: {self._lagertext(x)}")
                             for i, x in enumerate(model.surface_supports)],
                        "flaechenlager_einzeln", "flaechenlager")
        if model.hinges:
            gk = self._zweig(wurzel, "Gelenke", len(model.hinges), "gelenke")
            self._liste(gk, [(name, ", ".join(["ux", "uy", "uz", "φx", "φy", "φz"][d]
                                              for d in h.released()) or "starr",
                              name, f"{name}: freigegeben {h.released()}")
                             for name, h in model.hinges.items()], "gelenk", "gelenke")
        # Kontaktbedingungen: die Flaechenkontakte (in RFEM heissen sie
        # "Flaechenfreigaben") und die knotenweisen Bedingungen stehen unter
        # einem Zweig - es ist dieselbe Sache auf zwei Ebenen.
        flaechenkontakte = getattr(model, "kontaktbedingungen", {}) or {}
        n_kontakt = (len(flaechenkontakte) + len(model.contact_supports)
                     + len(model.gap_elements) + len(model.contact_pairs))
        if n_kontakt:
            offen_noch = sum(1 for x in flaechenkontakte.values() if not x.ausgefuehrt)
            kt = self._zweig(wurzel, "Kontaktbedingungen", n_kontakt, "kontakt",
                             fett=True,
                             farbe=FARBEN["warn"] if offen_noch else FARBEN["akzent"],
                             hinweis="Kontaktfugen zwischen Flächen und Körpern "
                                     "(in RFEM „Flächenfreigaben“) sowie die "
                                     "knotenweisen Bedingungen.")
            if flaechenkontakte:
                fk = self._zweig(kt, "Flächenkontakte", len(flaechenkontakte),
                                 "kontaktbedingungen",
                                 farbe=FARBEN["warn"] if offen_noch else None,
                                 hinweis="Solange die Trennung nicht ausgeführt "
                                         "ist, rechnet das Modell dort "
                                         "durchverbunden – also zu steif.")
                self._liste(fk, [(name + ("" if x.ausgefuehrt else " ⚠"), x.bezug(),
                                  name, f"{name}: {x.describe()}"
                                  + ("" if x.ausgefuehrt
                                     else "\nTrennung nicht ausgeführt – hier zu steif."))
                                 for name, x in flaechenkontakte.items()],
                            "kontaktbedingung", "kontaktbedingungen")
            if model.contact_supports:
                self._zweig(kt, "einseitige Lager", len(model.contact_supports),
                            "kontakt", schluessel="supports")
            if model.gap_elements:
                self._zweig(kt, "Spaltelemente", len(model.gap_elements),
                            "kontakt", schluessel="gaps")
            if model.contact_pairs:
                self._zweig(kt, "Kontaktpaare", len(model.contact_pairs),
                            "kontakt", schluessel="pairs")

        # ---- Einwirkungen -------------------------------------------------
        ew = self._zweig(wurzel, "Einwirkungen", "", "modell", fett=True)
        lf = self._zweig(ew, "Lastfälle", len(model.load_cases), "lastfaelle")
        self._liste(lf, [(name, f"{lc.category} · {lc.n_loads}"
                          + (f" · {lc.situation}" if getattr(lc, "situation", "") else "")
                          + (f" · {lc.theorie.upper()}. O." if getattr(lc, "theorie", "") else ""),
                          name, f"{name}: {lc.description or lc.category}, "
                          f"{lc.n_loads} Lasten"
                          + (f", Situation {lc.situation}" if getattr(lc, "situation", "") else ""))
                         for name, lc in model.load_cases.items()], "lastfall",
                    "lastfaelle")
        n_lasten = sum(lc.n_loads for lc in model.load_cases.values())
        la = self._zweig(ew, "Lasten", n_lasten, "lasten",
                         hinweis="Alle Lasten aller Lastfälle – die Tabelle "
                                 "unten zeigt sie einzeln")
        for name, lc in model.load_cases.items():
            if lc.n_loads:
                self._zweig(la, name, lc.n_loads, "last", schluessel=name)
        kb = self._zweig(ew, "Kombinationen", len(model.combinations), "kombinationen")
        self._liste(kb, [(name, " · ".join(x for x in (getattr(c, "situation", "") or "",
                                                       (f"{c.theorie.upper()}. O."
                                                        if getattr(c, "theorie", "") else "")) if x),
                          name,
                          name + (f": Situation {c.situation}" if getattr(c, "situation", "") else ""))
                         for name, c in model.combinations.items()], "kombination",
                    "kombinationen")

        # ---- Lastgenerierer -------------------------------------------------
        wds = getattr(model, "wasserdruecke", {}) or {}
        winde = getattr(model, "winde", {}) or {}
        lg = self._zweig(ew, "Lastgenerierer", len(wds) + len(winde), "generierer",
                         fett=bool(wds or winde), farbe=FARBEN["akzent"] if (wds or winde) else None,
                         hinweis="Wasserdruck (statisch, überströmt, unterströmt) und Wind "
                                 "(DIN EN 1991-1-4) je Situation")
        self._liste(lg, [(name, x.bezug(), name, f"Wasserdruck {name}: {x.bezug()}")
                         for name, x in wds.items()], "wasserdruck", "generierer")
        self._liste(lg, [(name, x.bezug(), name, f"Wind {name}: {x.bezug()}")
                         for name, x in winde.items()], "wind", "generierer")
        self._zweig(lg, "+ Wasserdruck anlegen", "", "wasserdruck_neu", farbe=FARBEN["akzent"])
        self._zweig(lg, "+ Wind anlegen", "", "wind_neu", farbe=FARBEN["akzent"])

        # ---- Ergebnisse -------------------------------------------------
        # Ergebnisse gehoeren in denselben Baum wie das Modell: was gerechnet
        # wurde, steht dort, wo man es sucht. Ein Klick stellt das Ergebnis in
        # der Ansicht ein, ein Doppelklick uebernimmt es in den Bericht.
        erg = ergebnisse or {}
        anzahl = sum(len(v) for v in erg.values())
        ew2 = self._zweig(wurzel, "Ergebnisse", anzahl or "", "ergebnisse",
                          fett=bool(anzahl),
                          farbe=FARBEN["akzent"] if anzahl else FARBEN["matt"],
                          hinweis="Klick zeigt das Ergebnis, Doppelklick "
                                  "übernimmt es in den Bericht")
        if not anzahl:
            self._zweig(ew2, "noch nicht gerechnet", "", "ergebnisse",
                        farbe=FARBEN["matt"])
        for gruppe, eintraege in erg.items():
            if not eintraege:
                continue
            z = self._zweig(ew2, gruppe, len(eintraege), "ergebnisgruppe",
                            schluessel=gruppe)
            self._liste(z, [(text, zusatz, key, text)
                            for text, zusatz, key in eintraege],
                        "ergebnis", "ergebnisgruppe")
        eintraege = list(getattr(model, "bericht", None) or [])
        bz = self._zweig(wurzel, "Bericht", len(eintraege), "bericht",
                         fett=bool(eintraege),
                         farbe=FARBEN["akzent"] if eintraege else None,
                         hinweis="Die aus der Ansicht übernommenen Ergebnisse")
        self._liste(bz, [(x.name or f"Bild {i + 1}", x.bezug(), str(i),
                          f"{x.name}: {x.bezug()}")
                         for i, x in enumerate(eintraege)], "berichtseintrag",
                    "bericht")
        self._zweig(bz, "+ Ansicht übernehmen", "", "bericht_neu",
                    farbe=FARBEN["akzent"])

        # ---- Stellungen ----------------------------------------------------
        # Stellungen stehen ausschliesslich hier (Vorgabe Kap. 16.1 Nr. 3);
        # der Zweig traegt die Schaltflaeche zum Anlegen.
        st = self._zweig(wurzel, "Stellungen", len(stellungen or []), "stellungen",
                         fett=bool(stellungen),
                         farbe=FARBEN["akzent"] if stellungen else None)
        for i, x in enumerate(stellungen or [], 1):
            eta = x.get("eta")
            text = f"S{i} · {x.get('name', '')}" + (" ★" if x.get("fuehrt") else "")
            zweig = self._zweig(st, text, f"{float(x.get('winkel', 0)):.0f}°",
                                "stellung", schluessel=x.get("name", ""))
            if eta is not None:
                zweig.setToolTip(0, f"Ausnutzung η = {float(eta):.3f}".replace(".", ","))
        self._zweig(st, "+ Stellung anlegen", "", "stellung_neu",
                    farbe=FARBEN["akzent"])
        st.setExpanded(True)

        # ---- Subsysteme und Situationen ------------------------------------
        # Das Gesamtsystem und die Grundstellung sind immer da; alles weitere
        # legt der Anwender an (Rechtsklick: Neu, oder der Eintrag "+ …").
        from ..model import GRUNDSTELLUNG, GESAMTSYSTEM
        subs = getattr(model, "subsysteme", {}) or {}
        sz = self._zweig(wurzel, "Subsysteme", 1 + len(subs), "subsysteme", fett=bool(subs),
                         farbe=FARBEN["akzent"] if subs else None,
                         hinweis="Teile des Tragwerks mit allem, was dazugehört; "
                                 "Berührungselemente gehören beiden")
        self._zweig(sz, GESAMTSYSTEM, f"{len(model.elements)} El", "subsystem",
                    schluessel=GESAMTSYSTEM, hinweis="die ganze Struktur")
        self._liste(sz, [(name, f"{len(s.elemente)} El", name, f"{name}: {s.bezug()}")
                         for name, s in subs.items()], "subsystem", "subsysteme")
        self._zweig(sz, "+ Subsystem anlegen", "", "subsystem_neu", farbe=FARBEN["akzent"])
        sits = getattr(model, "situationen", {}) or {}
        siz = self._zweig(wurzel, "Situationen", 1 + len(sits), "situationen",
                          fett=bool(sits), farbe=FARBEN["akzent"] if sits else None,
                          hinweis="Stellung und wirksame Elemente; Lastfälle und "
                                  "Kombinationen nennen ihre Situation")
        self._zweig(siz, GRUNDSTELLUNG, "alles aktiv", "situation", schluessel=GRUNDSTELLUNG,
                    hinweis="unbewegt, alle Elemente wirken")
        self._liste(siz, [(name, s.bezug(), name, f"{name}: {s.bezug()}")
                          for name, s in sits.items()], "situation", "situationen")
        self._zweig(siz, "+ Situation anlegen", "", "situation_neu", farbe=FARBEN["akzent"])

        # ---- Nachweisobjekte -------------------------------------------------
        # Anschluesse gehoeren zum Modell und stehen darum hier - der Zweig
        # traegt wie bei den Stellungen die Schaltflaeche zum Anlegen.
        an = self._zweig(wurzel, "Anschlüsse", len(getattr(model, "joints", {}) or {}),
                         "anschluesse", fett=bool(getattr(model, "joints", None)),
                         farbe=FARBEN["akzent"] if getattr(model, "joints", None) else None)
        self._liste(an, [(name, j.ort(), name, f"{name}: {j.typ} an {j.ort()}")
                         for name, j in (getattr(model, "joints", {}) or {}).items()],
                    "anschluss", "anschluesse")
        self._zweig(an, "+ Anschluss anlegen", "", "anschluss_neu",
                    farbe=FARBEN["akzent"])
        grenzen = getattr(model, "verformungsgrenzen", {}) or {}
        vf = self._zweig(wurzel, "Verformungsnachweise", len(grenzen), "verformungen",
                         fett=bool(grenzen),
                         farbe=FARBEN["akzent"] if grenzen else None)
        self._liste(vf, [(name, g.grenztext(), name,
                          f"{g.bezug()}: {g.groesse} ≤ {g.grenztext()}")
                         for name, g in grenzen.items()], "verformung", "verformungen")
        self._zweig(vf, "+ Verformungsgrenze", "", "verformung_neu",
                    farbe=FARBEN["akzent"])
        felder = getattr(model, "beulfelder", {}) or {}
        if felder:
            bl = self._zweig(wurzel, "Beulfelder", len(felder), "beulfelder", fett=True,
                             farbe=FARBEN["akzent"])
            self._liste(bl, [(name, x.bezug(), name, f"{name}: {x.bezug()}")
                             for name, x in felder.items()], "beulfeld", "beulfelder")
        bereiche = getattr(model, "volumenbereiche", {}) or {}
        if bereiche:
            vb = self._zweig(wurzel, "Volumenbereiche", len(bereiche),
                             "volumenbereiche", fett=True, farbe=FARBEN["akzent"])
            self._liste(vb, [(name, x.bezug(), name, f"{name}: {x.bezug()}")
                             for name, x in bereiche.items()], "volumenbereich",
                        "volumenbereiche")
        stellen = getattr(model, "lasteinleitungen", {}) or {}
        if stellen:
            li = self._zweig(wurzel, "Lasteinleitung", len(stellen), "lasteinleitung",
                             fett=True, farbe=FARBEN["akzent"])
            self._liste(li, [(name, x.bezug(), name, f"{name}: {x.bezug()}")
                             for name, x in stellen.items()], "lasteinleitung_einzeln",
                        "lasteinleitung")
        wurzel.setExpanded(offen.get(wurzel.text(0), True))
        for zweig, vorgabe in ((kn, False), (lin, False), (st, False), (fl, False),
                               (vo, False), (eig, False), (lg, True), (ew, False)):
            zweig.setExpanded(offen.get(zweig.text(0), vorgabe))


# ==========================================================================
# Tabellenbereich unten: Gruppen, darunter die Tabellen
# ==========================================================================
class Tabellenbereich(QtWidgets.QWidget):
    """Der untere Bereich in zwei Ebenen: **Gruppe → Tabelle**.

    27 Register nebeneinander liest niemand mehr. Oben steht darum eine
    schmale Leiste mit den Gruppen (Protokoll, Modell, Eigenschaften, Lager,
    Lasten, Ergebnisse, Nachweise, Bericht), darunter die Tabellen der
    gewaehlten Gruppe als Register. Eine Gruppe mit nur einer Tabelle zeigt
    keine zweite Leiste.

    Nach aussen verhaelt sich der Bereich wie ein flaches ``QTabWidget``
    (``count``, ``tabText``, ``setCurrentIndex``, ``currentIndex``,
    ``currentWidget``, ``addTab``): wer eine Tabelle nach vorn holt, muss
    ihre Gruppe nicht kennen. Die Reihenfolge innerhalb einer Gruppe ist die
    der Vorgabe, nicht die des Anlegens.
    """

    #: Gruppe fuer Tabellen, die keiner Gruppe zugeordnet sind
    SONST = "Weitere"

    def __init__(self, gruppen, parent=None):
        super().__init__(parent)
        self.gruppen: list[tuple[str, list[str]]] = [(g, list(n)) for g, n in gruppen]
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.leiste = QtWidgets.QTabBar(self)
        self.leiste.setObjectName("gruppenleiste")
        self.leiste.setExpanding(False)
        self.leiste.setDrawBase(False)
        self.leiste.setUsesScrollButtons(True)
        self.leiste.setElideMode(QtCore.Qt.ElideNone)
        self.stapel = QtWidgets.QStackedWidget(self)
        self.seiten: dict[str, QtWidgets.QTabWidget] = {}
        for g, _ in self.gruppen:
            self._gruppe_anlegen(g)
        self.leiste.currentChanged.connect(self.stapel.setCurrentIndex)
        lay.addWidget(self.leiste)
        lay.addWidget(self.stapel, 1)

    # ---- Aufbau ----------------------------------------------------------
    def _gruppe_anlegen(self, g: str) -> QtWidgets.QTabWidget:
        seite = QtWidgets.QTabWidget(self.stapel)
        seite.setObjectName("tabellenregister")
        seite.setUsesScrollButtons(True)
        seite.tabBar().setExpanding(False)
        seite.tabBar().setElideMode(QtCore.Qt.ElideNone)
        seite.tabBar().setVisible(False)
        self.seiten[g] = seite
        self.stapel.addWidget(seite)
        self.leiste.addTab(g)
        return seite

    def gruppe_von(self, name: str) -> str:
        for g, namen in self.gruppen:
            if name in namen:
                return g
        return self.SONST

    def gruppennamen(self) -> list[str]:
        return [self.leiste.tabText(i) for i in range(self.leiste.count())]

    def tabellen(self, gruppe: str) -> list[str]:
        seite = self.seiten.get(gruppe)
        return [seite.tabText(i) for i in range(seite.count())] if seite else []

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
        seite.tabBar().setVisible(seite.count() > 1)
        return self.indexOf(w)

    # ---- flache Sicht (wie ein QTabWidget) ---------------------------------
    def _eintraege(self) -> list[tuple[str, QtWidgets.QWidget, str, int]]:
        out = []
        for i in range(self.leiste.count()):
            g = self.leiste.tabText(i)
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
        g = self.leiste.tabText(self.leiste.currentIndex())
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
        return self.leiste.tabText(self.leiste.currentIndex())

    def setCurrentIndex(self, k: int):
        e = self._eintraege()
        if not 0 <= k < len(e):
            return
        _name, _w, g, j = e[k]
        self.leiste.setCurrentIndex(self.gruppennamen().index(g))
        self.seiten[g].setCurrentIndex(j)

    def zeigen(self, name: str) -> bool:
        """Die Tabelle mit diesem Namen nach vorn holen (Gruppe folgt)."""
        for k, (n, _w, _g, _j) in enumerate(self._eintraege()):
            if n == name:
                self.setCurrentIndex(k)
                return True
        return False

    def tabBar(self) -> QtWidgets.QTabBar:
        return self.leiste
