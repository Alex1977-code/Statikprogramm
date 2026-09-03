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
QMenuBar {{ background: {kopf}; color: {kopf_matt}; border: 0; padding: 2px 6px; }}
QMenuBar::item {{ background: transparent; padding: 5px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: #39485a; color: #fff; }}
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


class Kopfzeile(QtWidgets.QWidget):
    """Dunkle Kopfzeile: Programmname, Bauteil und Zustand."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"Kopfzeile {{ background:{FARBEN['kopf']}; }}")
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
        self.setStyleSheet(f"Filmstreifen {{ background:{FARBEN['flaeche']};"
                           f"border-top:1px solid {FARBEN['linie']}; }}")
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


class Modellbaum(QtWidgets.QTreeWidget):
    """Der Modellbaum links: was im Modell steckt, mit Anzahl."""

    angeklickt = QtCore.Signal(str, str)      # (Art, Name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        self.setRootIsDecorated(True)
        self.setIndentation(14)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.itemClicked.connect(self._klick)

    def _klick(self, item, _spalte):
        art = item.data(0, QtCore.Qt.UserRole) or ""
        if art:
            self.angeklickt.emit(str(art), item.text(0))

    def _zweig(self, eltern, text, zahl="", art="", fett=False, farbe=None):
        it = QtWidgets.QTreeWidgetItem(eltern, [text, str(zahl)])
        it.setData(0, QtCore.Qt.UserRole, art)
        if fett:
            f = it.font(0)
            f.setBold(True)
            it.setFont(0, f)
        it.setForeground(1, QtGui.QColor(FARBEN["matt"]))
        if farbe:
            it.setForeground(0, QtGui.QColor(farbe))
        return it

    def fuellen(self, model, stellungen: list = None):
        offen = {self.topLevelItem(i).text(0): self.topLevelItem(i).isExpanded()
                 for i in range(self.topLevelItemCount())}
        self.clear()
        wurzel = self._zweig(self, model.name or "Modell", f"{model.nn} Kn",
                             "modell", fett=True)
        arten: dict = {}
        for e in model.elements:
            arten[e.typ] = arten.get(e.typ, 0) + 1
        el = self._zweig(wurzel, "Elemente", len(model.elements), "elemente")
        for k, v in sorted(arten.items(), key=lambda x: -x[1]):
            self._zweig(el, k, v, "elemente")
        self._zweig(wurzel, "Querschnitte", len(model.sections), "querschnitte")
        self._zweig(wurzel, "Werkstoffe", len(model.materials), "werkstoffe")
        self._zweig(wurzel, "Lager", len(model.supports), "lager")
        self._zweig(wurzel, "Lastfälle", len(model.load_cases), "lastfaelle")
        self._zweig(wurzel, "Kombinationen", len(model.combinations), "kombinationen")
        n_kontakt = (len(model.contact_supports) + len(model.gap_elements)
                     + len(model.contact_pairs))
        if n_kontakt:
            self._zweig(wurzel, "Kontakt", n_kontakt, "kontakt")
        if stellungen:
            st = self._zweig(wurzel, "Stellungen", len(stellungen), "stellungen",
                             fett=True, farbe=FARBEN["akzent"])
            for i, s in enumerate(stellungen, 1):
                self._zweig(st, f"S{i} · {s.get('name', '')}",
                            f"{float(s.get('winkel', 0)):.0f}°", "stellung")
            st.setExpanded(True)
        if model.members:
            mem = self._zweig(wurzel, "Stäbe für Nachweise", len(model.members), "staebe")
            for name, mm in list(model.members.items())[:60]:
                self._zweig(mem, name, getattr(mm, "section", "") or "", "stab")
        wurzel.setExpanded(offen.get(wurzel.text(0), True))
        el.setExpanded(offen.get("Elemente", True))
