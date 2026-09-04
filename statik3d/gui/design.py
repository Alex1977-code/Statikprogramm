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
BAUM_MAX = 60


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

    def __init__(self, parent=None):
        super().__init__(parent)
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

    def _klick(self, item, _spalte):
        art, name = self._schluessel(item)
        if art:
            self.angeklickt.emit(art, name)

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

        # ---- Geometrie ---------------------------------------------------
        geo = self._zweig(wurzel, "Geometrie", "", "modell", fett=True)
        kn = self._zweig(geo, "Knoten", model.nn, "knoten")
        self._liste(kn, [(f"K{i}", _kurz(model.nodes[i]), str(i),
                          "Knoten {}: x = {:.4f}  y = {:.4f}  z = {:.4f} m".format(
                              i, *model.nodes[i]))
                         for i in range(model.nn)], "knoten")
        lin = self._zweig(geo, "Linien", len(model.lines), "linien")
        self._liste(lin, [(name, f"{ln.typ} · {len(ln.nodes)}", name,
                           f"{name}: {ln.typ} über {len(ln.nodes)} Knoten")
                          for name, ln in model.lines.items()], "linie", "linien")
        # Die Geometriekette: aus Linien Flaechen, aus Flaechen Volumen.
        # Was noch kein Netz traegt, ist matt - so sieht man auf einen Blick,
        # was noch gerechnet werden kann und was nicht.
        gf = getattr(model, "flaechen", {}) or {}
        fl = self._zweig(geo, "Flächen", len(gf), "geoflaechen")
        self._liste(fl, [(name + ("" if x.elemente else " ○"), x.bezug(), name,
                          f"{name}: {x.bezug()}"
                          + ("" if x.elemente else "\nnoch nicht vernetzt"))
                         for name, x in gf.items()], "geoflaeche", "geoflaechen")
        gk = getattr(model, "koerper", {}) or {}
        vo = self._zweig(geo, "Volumenkörper", len(gk), "geokoerper")
        self._liste(vo, [(name + ("" if x.elemente else " ○"), x.bezug(), name,
                          f"{name}: {x.bezug()}"
                          + ("" if x.elemente else "\nnoch nicht vernetzt"))
                         for name, x in gk.items()], "geokoerper_einzeln", "geokoerper")

        # ---- Elemente ----------------------------------------------------
        arten: dict = {}
        for e in model.elements:
            arten[e.typ] = arten.get(e.typ, 0) + 1
        el = self._zweig(wurzel, "Elemente", len(model.elements), "elemente", fett=True)
        stab = sum(arten.get(k, 0) for k in ("beam", "truss"))
        flae = sum(arten.get(k, 0) for k in ("shell3", "shell4"))
        voll = sum(arten.get(k, 0) for k in ("tet4", "tet10", "hex8"))
        if stab:
            z = self._zweig(el, "Stäbe", stab, "stabelemente",
                            hinweis="Balken- und Fachwerkelemente")
            for k in ("beam", "truss"):
                if arten.get(k):
                    self._zweig(z, {"beam": "Balken", "truss": "Fachwerkstab"}[k],
                                arten[k], "stabelemente", schluessel=k)
        if flae:
            z = self._zweig(el, "Flächen", flae, "flaechen",
                            hinweis="Schalenelemente")
            for k in ("shell3", "shell4"):
                if arten.get(k):
                    self._zweig(z, {"shell3": "Dreieck", "shell4": "Viereck"}[k],
                                arten[k], "flaechen", schluessel=k)
        if voll:
            z = self._zweig(el, "Volumen", voll, "volumen",
                            hinweis="Volumenelemente (Tetraeder, Hexaeder)")
            for k in ("tet4", "tet10", "hex8"):
                if arten.get(k):
                    self._zweig(z, {"tet4": "Tetraeder (linear)",
                                    "tet10": "Tetraeder (quadratisch)",
                                    "hex8": "Hexaeder"}[k], arten[k], "volumen",
                                schluessel=k)
        if model.members:
            mem = self._zweig(el, "Stäbe für Nachweise", len(model.members), "staebe")
            self._liste(mem, [(name, getattr(mm, "section", "") or "", name,
                               f"{name}: {len(mm.elements)} Elemente")
                              for name, mm in model.members.items()], "stab", "staebe")

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
        freigaben = getattr(model, "flaechenfreigaben", {}) or {}
        if freigaben:
            offen_noch = sum(1 for x in freigaben.values() if not x.ausgefuehrt)
            ff = self._zweig(wurzel, "Flächenfreigaben", len(freigaben),
                             "flaechenfreigaben", fett=True,
                             farbe=FARBEN["warn"] if offen_noch else FARBEN["akzent"],
                             hinweis="Kontaktfugen aus RFEM. Solange die Trennung "
                                     "nicht ausgeführt ist, rechnet das Modell dort "
                                     "durchverbunden – also zu steif.")
            self._liste(ff, [(name + ("" if x.ausgefuehrt else " ⚠"), x.bezug(), name,
                              f"{name}: {x.describe()}"
                              + ("" if x.ausgefuehrt
                                 else "\nTrennung nicht ausgeführt – hier zu steif."))
                             for name, x in freigaben.items()], "flaechenfreigabe",
                        "flaechenfreigaben")
        n_kontakt = (len(model.contact_supports) + len(model.gap_elements)
                     + len(model.contact_pairs))
        if n_kontakt:
            kt = self._zweig(wurzel, "Kontaktbedingungen", n_kontakt, "kontakt",
                             fett=True, farbe=FARBEN["akzent"])
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
        self._liste(lf, [(name, f"{lc.category} · {lc.n_loads}", name,
                          f"{name}: {lc.description or lc.category}, "
                          f"{lc.n_loads} Lasten")
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
        self._liste(kb, [(name, getattr(c, "kind", "") or "", name, name)
                         for name, c in model.combinations.items()], "kombination",
                    "kombinationen")

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
        for zweig, vorgabe in ((geo, False), (el, True), (eig, False), (lg, True),
                               (ew, False)):
            zweig.setExpanded(offen.get(zweig.text(0), vorgabe))
