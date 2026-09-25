"""
Nicht-modale Eingabemasken am Rand der Ansicht („Maske oder Klick").

Die Vorgabe (Kap. 3.8) verlangt fuer jeden Erzeuge-Befehl ein **kompaktes,
nicht-modales Eingabefenster** am Rand des Viewports - und gleichzeitig einen
Klick-Modus in der Ansicht. Beide Wege sind gleichwertig:

* Werte in die Maske tippen und **Anwenden** (Eingabetaste) erzeugt das Objekt;
  die Maske bleibt offen und ist gleich fuer das naechste bereit,
* oder in der Ansicht klicken: die angeklickten Knoten laufen in die Maske und
  loesen, sobald genug beisammen sind, dasselbe Erzeugen aus.

Die uebrigen Angaben (Querschnitt, Material, Dicke, Lastfall) gelten fuer alle
folgenden Objekte, bis man sie aendert. **Esc** schliesst, **Eingabe** bestaetigt.

Die Maske schwebt ueber der Ansicht und blockiert sie nicht - kein Dialog legt
sich vor das Modell (harte Regel 5 der Vorgabe).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6 import QtCore, QtGui, QtWidgets

from . import design as dsg


def listeneintraege(text: str) -> list:
    """Die Eintraege eines Listenfeldes - Kommas trennen, Leeres faellt weg."""
    return [x.strip() for x in str(text or "").split(",") if x.strip()]


def listenhinweis(text: str, hinweis: str = "") -> str:
    """Der Hinweis am Zeiger: Anzahl und die **ganze** Liste, umbrochen.

    Zehn Namen je Zeile - so bleibt auch eine Liste mit hundert Eintraegen
    lesbar, und keiner wird mitten im Namen abgeschnitten.
    """
    teile = listeneintraege(text)
    if not teile:
        return hinweis or "leer"
    zeilen = [", ".join(teile[i:i + 10]) for i in range(0, len(teile), 10)]
    kopf = f"{len(teile)} Einträge:"
    return "\n".join(([hinweis] if hinweis else []) + [kopf] + zeilen)


@dataclass
class Feld:
    """Ein Eingabefeld der Maske."""
    name: str
    text: str
    art: str = "zahl"            # zahl | ganz | text | liste | wahl | mehrfach | haken | info
    wert: object = 0.0
    werte: list = field(default_factory=list)   # fuer art="wahl" und "mehrfach"
    breite: int = 78
    hinweis: str = ""


class Rollflaeche(QtWidgets.QScrollArea):
    """Die rollbare Mitte einer Maske (24.09.2026).

    Eine gewoehnliche QScrollArea meldet hoechstens 24 Schriftzeilen Hoehe als
    Wunschgroesse; eine Maske mit 15 Feldern rollte dann schon in einem
    leeren, hohen rechten Bereich. Diese hier wuenscht sich die volle Hoehe
    ihres Inhalts - sie rollt nur, wenn der Platz wirklich fehlt - und
    verlangt als Mindesthoehe nur wenige Zeilen. Die Mindestbreite bleibt die
    des Inhalts (plus Rollbalken): waagerecht wird nie gerollt, so wie vorher.
    """

    #: Mindesthoehe der Mitte in Bildpunkten: etwa zwei Feldzeilen
    MINDESTHOEHE = 56

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("maskenrolle")
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        # Die Flaeche selbst nimmt keinen Fokus: Tab geht von Feld zu Feld
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.viewport().setAutoFillBackground(False)

    def setWidget(self, w: QtWidgets.QWidget) -> None:
        super().setWidget(w)
        w.setAutoFillBackground(False)
        # Aendert sich der Inhalt (Felder ein- oder ausgeblendet, eine
        # abgeleitete Maske setzt ihren Teil ein), muss die Wunschhoehe neu
        # gelesen werden - die QScrollArea selbst merkt das nicht
        w.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.widget() and ev.type() == QtCore.QEvent.LayoutRequest:
            self.updateGeometry()
        return super().eventFilter(obj, ev)

    def _balken(self) -> int:
        return self.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent, None, self)

    def sizeHint(self) -> QtCore.QSize:
        w = self.widget()
        if w is None:
            return super().sizeHint()
        s = w.sizeHint().expandedTo(w.minimumSizeHint())
        return QtCore.QSize(s.width() + self._balken(), s.height())

    #: True: die Mitte verlangt ihre volle Hoehe (rollt nicht). Das Fenster
    #: setzt es, wenn die ganze Maske passt, sobald der untere Bereich bis auf
    #: seine Mindesthoehe kleiner wird (MainWindow._fensterhoehe_halten)
    ganz_zeigen = False

    def minimumSizeHint(self) -> QtCore.QSize:
        w = self.widget()
        if w is None:
            return super().minimumSizeHint()
        voll = max(0, w.sizeHint().height())
        return QtCore.QSize(w.minimumSizeHint().width() + self._balken(),
                            voll if self.ganz_zeigen else min(self.MINDESTHOEHE, voll))

    #: Tasten, mit denen eine QScrollArea rollt, ein Feld sie aber nicht braucht
    _ROLLTASTEN = (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down,
                   QtCore.Qt.Key_PageUp, QtCore.Qt.Key_PageDown)

    def keyPressEvent(self, ev):
        # Pfeil auf/ab in einem Textfeld rollte die Mitte weg, und das Feld mit
        # der Schreibmarke verschwand aus dem Bild (24.09.2026). Steht der
        # Fokus in der Mitte, rollen diese Tasten nicht - wie vor dem
        # Rollbereich; Tab und Mausrad rollen weiter.
        fw = QtWidgets.QApplication.focusWidget()
        w = self.widget()
        if (ev.key() in self._ROLLTASTEN and fw is not None and w is not None
                and w.isAncestorOf(fw)):
            ev.ignore()
            return
        super().keyPressEvent(ev)


class Hinweiszeile(QtWidgets.QLabel):
    """Umbrechende Hinweiszeile im Kopf einer Maske (24.09.2026).

    Ein Dock rechnet nicht mit heightForWidth: die Mindesthoehe eines
    umbrechenden QLabel ist die einer Zeile, bei Wind (1064 px breit) fehlte
    so die dritte Zeile, und Qt quetschte den Fuss darunter, bis sich die
    Knoepfe ueberlappten. Diese Zeile meldet als Mindesthoehe die Hoehe, die
    sie bei ihrer jetzigen Breite wirklich braucht.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self._hfw = -1

    def _gelegt(self) -> bool:
        # Erst wenn die Zeile sichtbar ist, hat sie eine vom Layout gesetzte
        # Breite - vorher (100 px Vorgabe) waere die Hoehe viel zu gross
        return self.wordWrap() and self.isVisible() and self.width() > 40

    def minimumSizeHint(self) -> QtCore.QSize:
        s = super().minimumSizeHint()
        if self._gelegt():
            s.setHeight(max(s.height(), self.heightForWidth(self.width())))
        return s

    def _pruefen(self) -> None:
        h = self.heightForWidth(self.width()) if self._gelegt() else -1
        if h != self._hfw:
            self._hfw = h
            self.updateGeometry()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._pruefen()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._pruefen()

    def setText(self, text: str) -> None:
        super().setText(text)
        self._pruefen()


class Maske(QtWidgets.QFrame):
    """Eine nicht-modale Eingabemaske.

    angewendet(dict)  - „Anwenden" gedrueckt oder genug Knoten angeklickt
    geschlossen()     - Maske zu (Esc oder Kreuz)
    """

    angewendet = QtCore.Signal(dict)
    geschlossen = QtCore.Signal()
    abgebrochen = QtCore.Signal()
    #: Ein Feld hat die Tastatur bekommen (Name des Feldes). Das Fenster
    #: schaltet darueber die Auswahl per Maus auf dieses Feld („bei Klick in
    #: Feld Auswahl per Maus", 15.09.2026).
    feld_fokussiert = QtCore.Signal(str)
    #: Wird gerufen, wenn Esc in einem scharfen Feld nur den Klickmodus
    #: beenden soll (statt die Maske zu schliessen); None = schliessen.
    klick_beenden = None
    #: Klickmodus fuer Objekte der Ansicht: "" (keiner), "linie", "flaeche"
    #: oder "objekt" (Flaeche oder Volumen). Ist er gesetzt, gehen Klicks auf
    #: solche Objekte an objekt_angeklickt(art, name) statt in die Auswahl.
    objekt_modus: str = ""

    def objekt_angeklickt(self, art: str, name: str):
        """Ein Objekt der Ansicht wurde im Klickmodus getroffen (wird je Maske
        als Instanzattribut ueberschrieben)."""

    def __init__(self, titel: str, felder: list, parent=None, knoten: int = 0,
                 hinweis: str = "", knopf: str = "Anwenden", abbrechen: str = "",
                 zusatz: list = None, punkte: bool = False):
        super().__init__(parent)
        self.setObjectName("maske")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.titel = titel
        self.n_knoten = int(knoten)
        # punkte=True: die Maske sammelt Weltpunkte (Fang auf Knoten, Kanten,
        # Linien, Raster, Arbeitsebene) statt Knotennummern - Messen und
        # Bemassen legen dafuer keine Knoten an
        self.punkte = bool(punkte)
        self.gewaehlt_punkte: list = []
        self.gewaehlt: list[int] = []
        self._felder: dict[str, QtWidgets.QWidget] = {}
        #: Listenfelder: Name -> (Beschriftung, Titel, Hinweis). Ueber sie
        #: wird die Anzahl in der Beschriftung nachgefuehrt, wenn der Wert
        #: sich aendert (etwa weil Flaechen in der Ansicht angeklickt wurden).
        self._listen: dict[str, tuple] = {}

        # Gemeinsamer Rahmen (24.09.2026, Paket 1 des Oberflaechenplans):
        # fester Kopf (Titel, Hinweiszeile), rollbare Mitte (die Felder),
        # fester Fuss (die Knoepfe). Ohne Rollbereich zog eine lange Maske
        # (Wind, Wasserdruck, Knotenlager) das Hauptfenster bis 1749 px hoch
        # und „Übernehmen“ lag unter dem Bildschirmrand.
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        kopf = QtWidgets.QHBoxLayout()
        t = QtWidgets.QLabel(titel)
        t.setObjectName("maskentitel")
        kopf.addWidget(t)
        kopf.addStretch(1)
        zu = QtWidgets.QToolButton(self)
        zu.setText("✕")
        zu.setObjectName("maskezu")
        # Im Hauptfenster schliesst Esc die Maske nicht (Esc ist dort das
        # Kuerzel „Alles deselektieren“) - darum ohne „(Esc)“ im Hinweis
        # (24.09.2026)
        zu.setToolTip("Maske schließen")
        # Nur per Tab (nicht per Klick) fokussierbar und ans Ende der
        # Tab-Folge gesetzt (tabfolge_setzen): Tab geht vom Kopf direkt ins
        # erste Feld, und ohne Maus laesst sich die Maske trotzdem schliessen
        # - Masken ohne „Abbrechen“ hatten sonst gar keinen Weg (24.09.2026)
        zu.setFocusPolicy(QtCore.Qt.TabFocus)
        zu.clicked.connect(self.schliessen)
        kopf.addWidget(zu)
        lay.addLayout(kopf)
        self.btn_zu = zu
        #: Widget, das den Fokus zuletzt per Mausklick bekam (siehe
        #: _fokus_gewechselt)
        self._mausfokus = None

        # Die Hinweiszeile steht unter dem Titel: dort liest man zuerst, was
        # die Maske will - und sie rollt nicht mit weg
        self.lbl_hinweis = Hinweiszeile(hinweis or self._klickhinweis(), self)
        self.lbl_hinweis.setObjectName("maskenhinweis")
        self.lbl_hinweis.setWordWrap(True)
        lay.addWidget(self.lbl_hinweis)

        self.rolle = Rollflaeche(self)
        self.mitte = QtWidgets.QWidget()
        self.mitte.setObjectName("maskenmitte")
        self.mitte_lay = QtWidgets.QVBoxLayout(self.mitte)
        # 2 px oben und unten: der orange Rahmen eines scharfen Feldes bleibt
        # auch am Rand der Rollflaeche ganz zu sehen
        self.mitte_lay.setContentsMargins(0, 2, 0, 2)
        self.mitte_lay.setSpacing(6)
        self.rolle.setWidget(self.mitte)
        lay.addWidget(self.rolle, 1)

        gitter = QtWidgets.QGridLayout()
        gitter.setContentsMargins(0, 0, 0, 0)
        gitter.setHorizontalSpacing(6)
        gitter.setVerticalSpacing(4)
        for i, f in enumerate(felder):
            w = self._bauen(f)
            self._felder[f.name] = w
            w.setProperty("feldname", f.name)
            w.installEventFilter(self)
            if f.art == "haken":
                gitter.addWidget(w, i, 0, 1, 2)
            else:
                if f.art == "liste":
                    lb = QtWidgets.QLabel(f"{f.text} ({len(listeneintraege(str(f.wert)))})")
                    lb.setToolTip(listenhinweis(str(f.wert), f.hinweis or f.text))
                    self._listen[f.name] = (lb, f.text, f.hinweis or f.text)
                else:
                    lb = QtWidgets.QLabel(f.text)
                    lb.setToolTip(f.hinweis or f.text)
                gitter.addWidget(lb, i, 0)
                gitter.addWidget(w, i, 1)
        self.mitte_lay.addLayout(gitter)
        # Kurze Masken stehen oben, ihre Zeilen werden nicht auseinandergezogen
        self.mitte_lay.addStretch(0)

        fuss = QtWidgets.QVBoxLayout()
        fuss.setSpacing(6)
        knoepfe = QtWidgets.QHBoxLayout()
        self.btn_anwenden = QtWidgets.QPushButton(knopf, self)
        self.btn_anwenden.setDefault(True)
        self.btn_anwenden.clicked.connect(self.anwenden)
        knoepfe.addWidget(self.btn_anwenden)
        self.btn_abbrechen = None
        if abbrechen:
            # Ein neues Objekt braucht ein "Abbrechen", das es wieder wegnimmt
            self.btn_abbrechen = QtWidgets.QPushButton(abbrechen, self)
            self.btn_abbrechen.clicked.connect(self.abbrechen)
            knoepfe.addWidget(self.btn_abbrechen)
        if self.n_knoten:
            b = QtWidgets.QPushButton("Auswahl leeren", self)
            b.clicked.connect(self.auswahl_leeren)
            knoepfe.addWidget(b)
        fuss.addLayout(knoepfe)
        # Weitere Knoepfe (Situation: Auswahl deaktivieren / aktivieren,
        # Löschen …) - auch sie stehen im festen Fuss
        self.zusatzknoepfe: dict[str, QtWidgets.QPushButton] = {}
        if zusatz:
            zeile = QtWidgets.QHBoxLayout()
            for text, ruf in zusatz:
                b = QtWidgets.QPushButton(text, self)
                b.clicked.connect(lambda _c=False, r=ruf: r())
                zeile.addWidget(b)
                self.zusatzknoepfe[text] = b
            fuss.addLayout(zeile)
        lay.addLayout(fuss)
        self.setMinimumWidth(232)
        self.tabfolge_setzen()
        # Das Feld mit dem Fokus in der Rollflaeche sichtbar halten - auch bei
        # Klick, Programmfokus und Tab aus dem Fuss zurueck in die Felder
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._fokus_gewechselt)

    # -- Rahmen ---------------------------------------------------------
    def inhalt_einfuegen(self, w: QtWidgets.QWidget, dehnung: int = 0) -> QtWidgets.QWidget:
        """Eigenen Inhalt einer abgeleiteten Maske in die rollbare Mitte setzen
        (unter die Felder, ueber den Fuss). Die Tab-Folge wird nachgezogen."""
        # vor den Abschlussstrecker, der kurze Masken oben haelt
        self.mitte_lay.insertWidget(max(0, self.mitte_lay.count() - 1), w, dehnung)
        self.tabfolge_setzen()
        return w

    def _fussknoepfe(self) -> list:
        knoepfe = [self.btn_anwenden]
        if self.btn_abbrechen is not None:
            knoepfe.append(self.btn_abbrechen)
        knoepfe += [b for b in self.findChildren(QtWidgets.QPushButton)
                    if b.text() == "Auswahl leeren" and not self.rolle.isAncestorOf(b)]
        knoepfe += list(self.zusatzknoepfe.values())
        return knoepfe

    def tabfolge_setzen(self) -> None:
        """Tab von oben nach unten: erst alles in der Mitte in der Reihenfolge
        des Aufbaus, dann die Knoepfe des Fusses (24.09.2026). Ohne das kam
        bei der Ermuedungsmaske zuerst „Übernehmen“ und dann erst die Tabelle,
        weil ihr Inhalt nach den Knoepfen gebaut wird."""
        tab = QtCore.Qt.FocusPolicy.TabFocus.value
        # isAncestorOf laesst die Aufklapplisten der Auswahlfelder weg: sie
        # sind eigene Fenster und gehoeren nicht in die Tab-Folge der Maske
        folge = [w for w in self.mitte.findChildren(QtWidgets.QWidget)
                 if (w.focusPolicy().value & tab) == tab and self.mitte.isAncestorOf(w)]
        for w in folge:
            # FocusIn mitlesen (Grund des Fokus, siehe _fokus_gewechselt)
            w.installEventFilter(self)
            if isinstance(w, self._RADWIDGETS):
                # Das Mausrad ueber einer Auswahlliste verstellte ihren Wert
                # stillschweigend, statt die Mitte zu rollen (24.09.2026:
                # Windzone 2 -> 3). Ohne Fokus geht das Rad an die
                # Rollflaeche (eventFilter); StrongFocus: das Rad allein
                # gibt ihr keinen Fokus.
                w.setFocusPolicy(QtCore.Qt.StrongFocus)
        folge += [b for b in self._fussknoepfe() if b not in folge]
        # Das ✕ zuletzt: ohne Maus erreichbar, ohne Tab vom Kopf abzufangen
        folge.append(self.btn_zu)
        for a, b in zip(folge, folge[1:]):
            QtWidgets.QWidget.setTabOrder(a, b)

    #: Felder, die das Mausrad selbst verstellen wuerde
    _RADWIDGETS = (QtWidgets.QComboBox, QtWidgets.QAbstractSpinBox)

    def _fokus_gewechselt(self, _alt, neu) -> None:
        """Bekommt ein Widget der Mitte den Fokus, rollt die Mitte es ins Bild
        (Tab, Enter, Fokus aus dem Programm) - nicht bei einem Mausklick.

        Beim Klick auf ein halb sichtbares Feld rollte die Mitte es beim
        Druecken ins Bild; das Loslassen traf dann neben das Feld, und ein
        Haken blieb unverstellt (24.09.2026). Wer klickt, sieht das Feld
        ohnehin."""
        try:
            if neu is not None and neu is self._mausfokus:
                return
            if neu is not None and self.isVisible() and self.mitte.isAncestorOf(neu):
                # Das ganze Feld, nicht nur die Schreibmarke: ensureWidgetVisible
                # nimmt bei Textfeldern nur das Rechteck der Marke, und der
                # untere Rand des Feldes blieb dann abgeschnitten
                p = neu.mapTo(self.mitte, QtCore.QPoint(0, 0))
                r = QtCore.QRect(p, neu.size())
                halb = max(1, self.rolle.viewport().height() // 2)
                self.rolle.ensureVisible(r.center().x(), r.center().y(), 0,
                                         min(r.height() // 2 + 6, halb))
        except RuntimeError:            # Maske schon freigegeben
            pass

    # -- Aufbau ----------------------------------------------------------
    def _bauen(self, f: Feld) -> QtWidgets.QWidget:
        if f.art == "info":
            # Nur zum Lesen: Anzahl, kleinste und groesste Nummer, Bezuege
            w = QtWidgets.QLabel(str(f.wert), self)
            w.setObjectName("maskeninfo")
            w.setWordWrap(True)
            w.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            return w
        if f.art == "haken":
            w = QtWidgets.QCheckBox(f.text, self)
            w.setChecked(bool(f.wert))
            return w
        if f.art == "wahl":
            w = QtWidgets.QComboBox(self)
            w.addItems([str(x) for x in f.werte])
            if f.wert:
                w.setCurrentText(str(f.wert))
            return w
        if f.art == "mehrfach":
            # Mehrere aus einer Liste: Haken setzen statt Namen tippen. Der
            # Wert ist wie beim Listenfeld die Namen, durch Komma - so bleibt
            # alles, was Listen liest (Stellungen, Situationen), unveraendert.
            w = QtWidgets.QListWidget(self)
            gewaehlt = set(listeneintraege(str(f.wert)))
            for name in f.werte:
                it = QtWidgets.QListWidgetItem(str(name))
                it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
                it.setCheckState(QtCore.Qt.Checked if str(name) in gewaehlt else QtCore.Qt.Unchecked)
                w.addItem(it)
            w.setMaximumHeight(min(21 * max(len(f.werte), 1) + 8, 150))
            w.setToolTip(f.hinweis or "Anklicken wählt aus, noch einmal wählt ab")
            return w
        w = QtWidgets.QLineEdit(str(f.wert), self)
        w.setFixedWidth(f.breite)
        if f.art in ("zahl", "ganz"):
            w.setValidator(QtGui.QIntValidator() if f.art == "ganz"
                           else QtGui.QDoubleValidator(-1e30, 1e30, 10))
        if f.art == "liste":
            # Ein einzeiliges Feld steht sonst am **Ende** der Zeile: aus
            # „F249, F236, ..., F69, F64, F71, F98, F46, F52" bleibt
            # „9, F64, F71, F98, F46, F52" sichtbar - das liest sich wie neun
            # Flaechen, davon fuenf genannt, und verleitet zu der falschen
            # Diagnose, es fehlten welche. Darum von vorn anzeigen; die
            # vollstaendige Liste steht im Hinweis am Zeiger.
            w.setCursorPosition(0)
            w.setToolTip(listenhinweis(str(f.wert), f.hinweis))
        w.returnPressed.connect(self.anwenden)
        return w

    def _klickhinweis(self) -> str:
        # „✕ schließt“ statt „Esc schließt“ (24.09.2026): im Hauptfenster ist
        # Esc das Kuerzel „Alles deselektieren“ und schliesst keine Maske -
        # der Hinweis steht jetzt oben, wo man ihn zuerst liest
        if not self.n_knoten:
            return "Werte eintragen und „Anwenden“ – die Maske bleibt offen."
        if self.punkte:
            if self.n_knoten >= 20:
                return ("In der Ansicht Punkte der Reihe nach anklicken (Knoten, Kanten, "
                        "Linien, Raster) – „Anwenden“ beendet. ✕ schließt.")
            return (f"In der Ansicht {self.n_knoten} Punkt{'e' if self.n_knoten > 1 else ''} "
                    "anklicken (Knoten, Kanten, Linien, Raster, Arbeitsebene). ✕ schließt.")
        return (f"In der Ansicht {self.n_knoten} Knoten anklicken – oder die "
                "Nummern eintragen. ✕ schließt.")

    # -- Werte -----------------------------------------------------------
    def werte(self) -> dict:
        out: dict = {}
        for name, w in self._felder.items():
            if isinstance(w, QtWidgets.QLabel):
                out[name] = w.text()
            elif isinstance(w, QtWidgets.QCheckBox):
                out[name] = w.isChecked()
            elif isinstance(w, QtWidgets.QComboBox):
                out[name] = w.currentText()
            elif isinstance(w, QtWidgets.QListWidget):
                out[name] = ", ".join(w.item(i).text() for i in range(w.count())
                                      if w.item(i).checkState() == QtCore.Qt.Checked)
            else:
                t = w.text().replace(",", ".").strip()
                if w.validator() is None:
                    out[name] = w.text().strip()
                else:
                    try:
                        out[name] = float(t) if t else 0.0
                    except ValueError:
                        out[name] = 0.0
        out["knoten"] = list(self.gewaehlt)
        if self.punkte:
            out["punkte"] = [[float(x) for x in p] for p in self.gewaehlt_punkte]
        return out

    def setzen(self, name: str, wert):
        w = self._felder.get(name)
        if w is None:
            return
        if isinstance(w, QtWidgets.QCheckBox):
            w.setChecked(bool(wert))
        elif isinstance(w, QtWidgets.QComboBox):
            w.setCurrentText(str(wert))
        elif isinstance(w, QtWidgets.QListWidget):
            gewaehlt = set(listeneintraege(str(wert)))
            for i in range(w.count()):
                it = w.item(i)
                it.setCheckState(QtCore.Qt.Checked if it.text() in gewaehlt else QtCore.Qt.Unchecked)
        elif isinstance(w, QtWidgets.QLabel):
            w.setText(str(wert))
        else:
            w.setText(f"{wert:g}" if isinstance(wert, float) else str(wert))
            eintrag = self._listen.get(name)
            if eintrag is not None:
                lb, titel, hinweis = eintrag
                teile = listeneintraege(w.text())
                lb.setText(f"{titel} ({len(teile)})")
                lb.setToolTip(listenhinweis(w.text(), hinweis))
                w.setToolTip(listenhinweis(w.text(), hinweis))
                w.setCursorPosition(0)

    def auswahlliste(self, namen: list):
        """Auswahlfeld neu fuellen und die bisherige Wahl behalten."""
        for w in self._felder.values():
            if isinstance(w, QtWidgets.QComboBox):
                pass
        return namen

    # -- Klick-Modus -----------------------------------------------------
    def knoten_angeklickt(self, i: int):
        """Ein Knoten wurde in der Ansicht angeklickt."""
        if not self.n_knoten:
            return
        if i in self.gewaehlt:
            self.gewaehlt.remove(i)
        else:
            self.gewaehlt.append(i)
        self._zeige_auswahl()
        if len(self.gewaehlt) >= self.n_knoten:
            self.anwenden()

    def punkt_angeklickt(self, p):
        """Ein Weltpunkt wurde in der Ansicht angeklickt (Maske mit punkte=True)."""
        if not self.n_knoten or not self.punkte:
            return
        self.gewaehlt_punkte.append([float(x) for x in p])
        self._zeige_auswahl()
        if len(self.gewaehlt_punkte) >= self.n_knoten:
            self.anwenden()

    def auswahl_leeren(self):
        self.gewaehlt.clear()
        self.gewaehlt_punkte.clear()
        self._zeige_auswahl()

    def _zeige_auswahl(self):
        if not self.n_knoten:
            return
        if self.punkte:
            n = len(self.gewaehlt_punkte)
            if not n:
                self.lbl_hinweis.setText(self._klickhinweis())
            else:
                p = self.gewaehlt_punkte[-1]
                ziel = f"{n} von {self.n_knoten}" if self.n_knoten < 20 else f"{n}, „Anwenden“ beendet"
                self.lbl_hinweis.setText(f"Punkt {n}: ({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f})  ({ziel})")
            return
        n = len(self.gewaehlt)
        liste = ", ".join(str(i + 1) for i in self.gewaehlt) or "keiner"
        self.lbl_hinweis.setText(
            f"Gewählt: {liste}  ({n} von {self.n_knoten})"
            if n else self._klickhinweis())

    # -- Bedienung -------------------------------------------------------
    def anwenden(self):
        self.angewendet.emit(self.werte())

    def abbrechen(self):
        """Abbrechen: erst melden (das Fenster nimmt ein neues Objekt zurueck),
        dann schliessen."""
        self.abgebrochen.emit()
        self.schliessen()

    def schliessen(self):
        self.hide()
        self.geschlossen.emit()

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_Escape:
            if self.objekt_modus and callable(self.klick_beenden):
                # Esc im scharfen Feld: erst den Klickmodus beenden, die
                # Maske bleibt - ein zweites Esc schliesst sie
                self.klick_beenden()
                return
            self.schliessen()
            return
        if ev.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and self._enter():
            return
        super().keyPressEvent(ev)

    def _enter(self) -> bool:
        """Enter = Hauptknopf, von jedem Feld aus (24.09.2026).

        Hier kommt Enter nur an, wenn das Feld es nicht selbst braucht. Ein
        Textfeld mit eigenem returnPressed hat den Hauptknopf schon ausgeloest
        (QLineEdit reicht Enter danach weiter) - dort nichts tun, sonst liefe
        „Anlegen“ zweimal. Ein Knopf mit dem Fokus wird selbst gedrueckt:
        Enter auf „Abbrechen“ bricht ab.
        """
        fw = QtWidgets.QApplication.focusWidget()
        if fw is not None and not self.isAncestorOf(fw):
            fw = None
        if isinstance(fw, QtWidgets.QAbstractItemView):
            # Tabelle oder Liste (Ermuedungskollektiv, Mehrfachwahl): Enter
            # blaettert dort nur und uebernimmt nichts - sonst lief ohne
            # Aenderung eine Rueckgaengig-Sicherung und refresh_all
            # (24.09.2026)
            return False
        if isinstance(fw, QtWidgets.QLineEdit):
            try:
                if fw.receivers(QtCore.SIGNAL("returnPressed()")) > 0:
                    return True
            except (TypeError, RuntimeError):
                return True
        if isinstance(fw, QtWidgets.QPushButton) and fw is not self.btn_anwenden:
            fw.click()
            return True
        if self.btn_anwenden.isEnabled():
            self.btn_anwenden.click()
        return True

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.FocusIn:
            # Vor focusChanged zugestellt: _fokus_gewechselt weiss so, ob der
            # Fokus per Maus kam
            self._mausfokus = obj if ev.reason() == QtCore.Qt.MouseFocusReason else None
            name = obj.property("feldname")
            if name:
                self.feld_fokussiert.emit(str(name))
        elif (ev.type() == QtCore.QEvent.Wheel and isinstance(obj, self._RADWIDGETS)
              and not obj.hasFocus()):
            # nicht verstellen, sondern die Mitte rollen: ausdruecklich an die
            # Rollflaeche geben - ein nur ignoriertes Ereignis wandert bloss
            # dann zu den Eltern, wenn es vom System kommt
            if self.mitte.isAncestorOf(obj):
                QtCore.QCoreApplication.sendEvent(self.rolle.viewport(), ev)
            return True
        return super().eventFilter(obj, ev)

    def klickfeld_markieren(self, name) -> None:
        """Das Feld, das ein Klick in der Ansicht gerade fuellt, orange
        einrahmen - alle anderen normal. ``None`` nimmt jeden Rahmen weg."""
        for feld, w in self._felder.items():
            if isinstance(w, QtWidgets.QLabel):
                continue
            w.setStyleSheet("border: 2px solid #ff8800; background: #fff6e5;"
                            if feld == name else "")


class Maskenrand(QtCore.QObject):
    """Haelt die eine offene Erzeuge-Maske **im rechten Bereich**.

    Es ist immer hoechstens **eine** Maske offen: ein Erzeuge-Befehl loest den
    vorigen ab. Frueher schwebte sie ueber der Ansicht; das verdeckte gerade
    das, was man zum Anklicken braucht, und stand ausserdem woanders als alle
    anderen Eingaben. Jetzt sitzt sie oben im rechten Eingabebereich - dort,
    wo die Einstellungen zu dem stehen, was man gerade erzeugt.

    ``ziel`` ist das Layout im rechten Bereich, in das die Maske kommt. Ohne
    Ziel faellt sie auf das alte Schweben ueber der Ansicht zurueck (der Test
    baut das Fenster ohne rechten Bereich).
    """

    def __init__(self, ansicht: QtWidgets.QWidget, ziel: QtWidgets.QBoxLayout = None):
        super().__init__(ansicht)
        self.ansicht = ansicht
        self.ziel = ziel
        self.maske: Maske | None = None
        ansicht.installEventFilter(self)

    def setze_ziel(self, ziel: QtWidgets.QBoxLayout):
        self.ziel = ziel

    def zeigen(self, maske: Maske, fokus: bool = True) -> Maske:
        """Die Maske rechts zeigen; mit ``fokus`` bekommt sie die Tastatur.

        **Ohne ``fokus`` bleibt die Tastatur, wo sie war.** Das ist der
        Unterschied zwischen einer Maske, die der Benutzer *bestellt* hat
        (Ribbon „Neu …": er will gleich tippen), und einer, die nur die
        *Folge* einer Auswahl ist (ein Klick im Modellbaum oder in einer
        Tabelle). Im zweiten Fall nahm die Maske dem Modellbaum die Tastatur
        weg - und genau dann taten die Pfeiltasten nichts mehr, obwohl der
        Baum sie kann.
        """
        self.schliessen()
        self.maske = maske
        maske.geschlossen.connect(self._vergessen)
        if self.ziel is not None:
            # Eine lange Maske (Querschnitte) meldet eine Dehnung an und
            # bekommt damit den groesseren Teil der Hoehe. Alle anderen stehen
            # oben buendig in ihrer natuerlichen Hoehe (24.09.2026): ohne
            # AlignTop bekam die Maske den ganzen Bereich, und ihre Zeilen
            # wurden auseinandergezogen. Fehlt Platz, rollt ihre Mitte -
            # das Fenster waechst nicht mehr.
            dehnung = int(getattr(maske, "dehnung", 0) or 0)
            if dehnung:
                self.ziel.insertWidget(0, maske, dehnung)
            else:
                self.ziel.insertWidget(0, maske, 0, QtCore.Qt.AlignTop)
            maske.show()
            # Die Tab-Folge erst hier noch einmal setzen: allein (ohne
            # Fenster) ist die Kette ein Ring, und Qt haelt „Übernehmen“ nach
            # dem letzten Feld dann schon fuer richtig einsortiert - im
            # Fenster folgten sonst auf das letzte Feld die Widgets dahinter
            ordnen = getattr(maske, "tabfolge_setzen", None)
            if callable(ordnen):
                ordnen()
            if fokus:
                maske.setFocus()
        else:
            maske.setParent(self.ansicht)
            maske.show()
            maske.raise_()
            if fokus:
                maske.setFocus()
            self._platzieren()
        return maske

    def schliessen(self):
        if self.maske is not None:
            m, self.maske = self.maske, None
            if self.ziel is not None:
                self.ziel.removeWidget(m)
            m.hide()
            # Auch eine ersetzte Maske ist „zu“: wer auf ihr Schliessen hoert
            # (etwa die Vorschau einer Stellung, die Elemente ausblendet),
            # muss es erfahren - sonst blieben die Elemente ausgeblendet
            try:
                m.geschlossen.emit()
            except (RuntimeError, AttributeError):
                pass
            m.deleteLater()

    def _vergessen(self):
        self.maske = None

    def offen(self) -> bool:
        return self.maske is not None and self.maske.isVisible()

    def knoten_angeklickt(self, i: int) -> bool:
        """True, wenn die Maske den Klick verbraucht hat."""
        if not self.offen() or not self.maske.n_knoten:
            return False
        self.maske.knoten_angeklickt(i)
        return True

    def will_punkte(self) -> bool:
        """Sammelt die offene Maske Weltpunkte statt Knoten?"""
        return self.offen() and bool(self.maske.n_knoten) and bool(getattr(self.maske, "punkte", False))

    def objekt_modus(self) -> str:
        """Klickmodus der offenen Maske ("" = keiner): Linien, Flaechen oder
        Objekte gehen dann an die Maske statt in die Auswahl."""
        return str(getattr(self.maske, "objekt_modus", "") or "") if self.offen() else ""

    def punkt_angeklickt(self, p) -> bool:
        """Einen Weltpunkt an die Maske geben; True, wenn sie ihn genommen hat."""
        if not self.will_punkte():
            return False
        self.maske.punkt_angeklickt(p)
        return True

    def _platzieren(self):
        if self.maske is None or self.ziel is not None:
            return
        g = self.maske.sizeHint()
        b = self.ansicht.width()
        # nie hoeher als die Ansicht - die Mitte der Maske rollt (24.09.2026)
        h = max(self.maske.minimumSizeHint().height(),
                min(g.height(), self.ansicht.height() - 24))
        self.maske.setGeometry(max(8, b - g.width() - 14), 12, g.width(), h)

    def eventFilter(self, obj, ev):
        if obj is self.ansicht and ev.type() == QtCore.QEvent.Resize:
            self._platzieren()
        return False


#: Zusatz zum Stilblatt: Aussehen der Masken
STIL = """
QFrame#maske {{ background: {flaeche}; border: 1px solid {linie};
    border-radius: 10px; }}
QLabel#maskentitel {{ font-weight: 600; font-size: 13px; }}
QLabel#maskenhinweis {{ color: {matt}; font-size: 11px; }}
/* rollbare Mitte: durchsichtig, damit sie wie die Maske aussieht */
QScrollArea#maskenrolle {{ background: transparent; border: 0; }}
QWidget#maskenmitte {{ background: transparent; }}
QToolButton#maskezu {{ border: 0; color: {matt}; font-size: 13px;
    padding: 0 4px; }}
QToolButton#maskezu:hover {{ color: {schlecht}; }}

/* Glasleiste ueber der Ansicht: durchscheinend, damit das Modell darunter
   sichtbar bleibt. */
QFrame#glasleiste {{ background: rgba(255, 255, 255, 200);
    border: 1px solid rgba(0, 0, 0, 30); border-radius: 9px; }}
QToolButton#glasknopf {{ background: transparent; border: 0; border-radius: 6px;
    padding: 3px; color: {text}; }}
QToolButton#glasknopf:hover {{ background: {akzent_hell}; color: {akzent}; }}
QToolButton#glasknopf:checked {{ background: {akzent}; color: #fff; }}
QFrame#glastrenner {{ color: rgba(0, 0, 0, 40); }}
QComboBox#glasliste {{ background: rgba(255, 255, 255, 230); color: {text};
    border: 1px solid rgba(0, 0, 0, 40); border-radius: 6px;
    padding: 2px 6px; font-size: 12px; }}
QComboBox#glasliste:hover {{ border-color: {akzent}; }}
QComboBox#glasliste::drop-down {{ border: 0; width: 16px; }}
Ansichtswuerfel {{ background: transparent; }}
"""


def stil() -> str:
    return STIL.format(**dsg.FARBEN)


# ==========================================================================
# Glasleiste und Ansichtswuerfel ueber der Ansicht
# ==========================================================================
class Glasleiste(QtWidgets.QFrame):
    """Schmale, durchscheinende Leiste **mittig oben** ueber der Ansicht.

    Sie traegt als Symbole, was man beim Modellieren staendig umschaltet -
    Darstellungsart, was sichtbar ist, was gefangen wird, was ein Klick
    trifft - und liegt dabei ueber dem Bild, statt Platz wegzunehmen. Alle
    Knoepfe fuehren dieselben Aktionsobjekte wie das Ribbon; hier stehen sie
    nur naeher an der Maus. Der Klartext erscheint beim Ueberfahren.
    """

    #: Symbolgroesse der Knoepfe
    SYMBOL = 20

    def __init__(self, ansicht: QtWidgets.QWidget):
        super().__init__(ansicht)
        self.setObjectName("glasleiste")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.lay = QtWidgets.QHBoxLayout(self)
        self.lay.setContentsMargins(6, 3, 6, 3)
        self.lay.setSpacing(2)
        self.knoepfe: dict[str, QtWidgets.QToolButton] = {}
        self.listen: dict[str, QtWidgets.QComboBox] = {}

    def knopf(self, aktion: QtGui.QAction, symbol: str = "",
              schluessel: str = "") -> QtWidgets.QToolButton:
        """Ein Symbolknopf fuer eine Aktion. ``symbol`` ist der Name aus
        :mod:`symbole`; fehlt er, wird er aus der Beschriftung geraten."""
        from . import symbole as sym
        if symbol or aktion.icon().isNull():
            aktion.setIcon(sym.fuer_befehl(aktion.text(), "", symbol))
        b = QtWidgets.QToolButton(self)
        b.setDefaultAction(aktion)
        b.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        b.setIconSize(QtCore.QSize(self.SYMBOL, self.SYMBOL))
        b.setObjectName("glasknopf")
        b.setAutoRaise(True)
        if not aktion.toolTip():
            aktion.setToolTip(aktion.text())
        self.lay.addWidget(b)
        self.knoepfe[schluessel or aktion.text()] = b
        return b

    def liste(self, hinweis: str = "", schluessel: str = "",
              breite: int = 190) -> QtWidgets.QComboBox:
        """Eine Aufklappliste in der Leiste - fuer das, was man **auswaehlt**,
        nicht umschaltet.

        Ein Symbolknopf kann nur an oder aus; ein Lastfall unter dreissig
        braucht eine Liste. Sie sieht aus wie die Knoepfe daneben (flach,
        durchscheinend) und traegt denselben Namen im Formularblatt.
        """
        cb = QtWidgets.QComboBox(self)
        cb.setObjectName("glasliste")
        cb.setToolTip(hinweis)
        cb.setMinimumWidth(breite)
        cb.setMaxVisibleItems(24)
        cb.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.lay.addWidget(cb)
        self.listen[schluessel or hinweis] = cb
        return cb

    def trenner(self):
        f = QtWidgets.QFrame(self)
        f.setFrameShape(QtWidgets.QFrame.VLine)
        f.setObjectName("glastrenner")
        self.lay.addWidget(f)

    def widget(self, w: QtWidgets.QWidget) -> QtWidgets.QWidget:
        w.setParent(self)
        self.lay.addWidget(w)
        return w


class Ansichtswuerfel(QtWidgets.QWidget):
    """Ansichtswuerfel oben rechts - er **dreht sich mit** der Ansicht.

    Gezeichnet wird der Wuerfel so, wie die Kamera gerade auf das Modell
    schaut: dieselbe Drehung, dieselben sichtbaren Seiten. Man sieht also
    immer, wo +X, +Y und +Z liegen. Drei Griffe:

    * **Klick auf eine Seite** stellt die Ansicht senkrecht auf diese Seite.
    * **Ziehen mit der Maus** dreht die Ansicht - wie am Modell selbst, nur
      dass man dabei nicht das Modell verdeckt.
    * Die Zeile darunter: +x, +y, +z, -x, -y, -z und iso.

    Die Drehmatrix der Kamera holt sich der Wuerfel ueber ``kamera`` - eine
    Funktion, die die 3x3-Matrix Welt -> Bild liefert (oder None).
    """

    gewaehlt = QtCore.Signal(str)          # Blickrichtung ("+x", "iso", ...)
    gedreht = QtCore.Signal(float, float)  # Ziehen: (dx, dy) in Bildpunkten

    #: Ecken des Einheitswuerfels
    ECKEN = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
             (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
    #: Seiten: (Beschriftung, Blickrichtung, Normale, Eckenfolge)
    SEITEN = [
        ("+X", "+x", (1, 0, 0), [1, 2, 6, 5]),
        ("-X", "-x", (-1, 0, 0), [0, 4, 7, 3]),
        ("+Y", "+y", (0, 1, 0), [2, 3, 7, 6]),
        ("-Y", "-y", (0, -1, 0), [0, 1, 5, 4]),
        ("+Z", "+z", (0, 0, 1), [4, 5, 6, 7]),
        ("-Z", "-z", (0, 0, -1), [0, 3, 2, 1]),
    ]
    #: (Beschriftung, Blickrichtung, Hinweis) der Zeile unter dem Wuerfel
    RICHTUNGEN = [
        ("+x", "+x", "Ansicht von +X (auf die Seite +X)"),
        ("+y", "+y", "Ansicht von +Y"),
        ("+z", "+z", "Ansicht von +Z (Draufsicht)"),
        ("-x", "-x", "Ansicht von -X"),
        ("-y", "-y", "Ansicht von -Y"),
        ("-z", "-z", "Ansicht von -Z (Untersicht)"),
        ("iso", "iso", "Isometrische Ansicht"),
    ]

    WUERFEL = 88          # Kantenlaenge des Wuerfelfeldes
    ZEILE = 20            # Hoehe der Richtungszeile
    ZIEHEN = 4            # ab so vielen Bildpunkten Bewegung gilt ein Klick als Ziehen

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.WUERFEL + 74, self.WUERFEL + self.ZEILE + 6)
        self.setCursor(QtCore.Qt.OpenHandCursor)
        self.setMouseTracking(True)
        self.setToolTip("Ansichtswürfel: eine Seite anklicken oder mit der Maus "
                        "ziehen, um die Ansicht zu drehen.")
        self._unter = ""
        self._start = None
        self._zuletzt = None
        self._gezogen = False
        self.kamera = None               # -> 3x3 Drehmatrix Welt -> Bild oder None

    # -- Geometrie -------------------------------------------------------
    def _matrix(self):
        R = None
        if callable(self.kamera):
            try:
                R = self.kamera()
            except Exception:           # noqa: BLE001
                R = None
        if R is None:
            # Ohne Kamera: die uebliche Schraegansicht von vorne rechts oben
            a, b = math.radians(-35.0), math.radians(30.0)
            Rx = [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]]
            Rz = [[math.cos(b), -math.sin(b), 0], [math.sin(b), math.cos(b), 0], [0, 0, 1]]
            R = [[sum(Rx[i][k] * Rz[k][j] for k in range(3)) for j in range(3)]
                 for i in range(3)]
        return R

    def _wuerfelfeld(self) -> QtCore.QRectF:
        x = (self.width() - self.WUERFEL) / 2.0
        return QtCore.QRectF(x, 0.0, self.WUERFEL, self.WUERFEL)

    def _projektion(self):
        """Ecken im Bild und Seiten mit Sichtbarkeit und Tiefe."""
        R = self._matrix()
        r = self._wuerfelfeld()
        mx, my = r.center().x(), r.center().y()
        mass = 0.29 * self.WUERFEL
        bild = []
        for e in self.ECKEN:
            v = [sum(R[i][k] * e[k] for k in range(3)) for i in range(3)]
            bild.append((mx + mass * v[0], my - mass * v[1], v[2]))
        seiten = []
        for text, richtung, n, ecken in self.SEITEN:
            nz = sum(R[2][k] * n[k] for k in range(3))
            tiefe = sum(bild[i][2] for i in ecken) / 4.0
            poly = QtGui.QPolygonF([QtCore.QPointF(bild[i][0], bild[i][1]) for i in ecken])
            seiten.append((tiefe, nz, text, richtung, poly))
        seiten.sort(key=lambda t: t[0])       # hinten zuerst zeichnen
        return seiten

    def _felder(self):
        """Die Schaltflaechen der Richtungszeile als (Rechteck, Text, Richtung)."""
        n = len(self.RICHTUNGEN)
        b = self.width() / n
        y = self.WUERFEL + 4
        for i, (text, richtung, _hinweis) in enumerate(self.RICHTUNGEN):
            yield QtCore.QRectF(i * b, y, b - 1, self.ZEILE), text, richtung

    def _treffer(self, pos) -> str:
        p = QtCore.QPointF(pos)
        for _t, nz, _text, richtung, poly in reversed(self._projektion()):
            if nz > 0 and poly.containsPoint(p, QtCore.Qt.OddEvenFill):
                return richtung
        for rect, _t, richtung in self._felder():
            if rect.contains(p):
                return richtung
        return ""

    # -- Bedienung -------------------------------------------------------
    def mouseMoveEvent(self, ev):
        pos = ev.position() if hasattr(ev, "position") else QtCore.QPointF(ev.pos())
        if self._start is not None and ev.buttons() & QtCore.Qt.LeftButton:
            d = pos - self._zuletzt
            if not self._gezogen:
                weg = pos - self._start
                if abs(weg.x()) + abs(weg.y()) >= self.ZIEHEN:
                    self._gezogen = True
                    self.setCursor(QtCore.Qt.ClosedHandCursor)
            if self._gezogen:
                self._zuletzt = pos
                self.gedreht.emit(float(d.x()), float(d.y()))
            return
        neu = self._treffer(pos)
        if neu != self._unter:
            self._unter = neu
            for text, richtung, hinweis in self.RICHTUNGEN:
                if richtung == neu:
                    self.setToolTip(hinweis)
                    break
            self.update()

    def leaveEvent(self, _ev):
        self._unter = ""
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
            return
        pos = ev.position() if hasattr(ev, "position") else QtCore.QPointF(ev.pos())
        self._start = pos
        self._zuletzt = pos
        self._gezogen = False

    def mouseReleaseEvent(self, ev):
        if ev.button() != QtCore.Qt.LeftButton or self._start is None:
            return
        pos = ev.position() if hasattr(ev, "position") else QtCore.QPointF(ev.pos())
        gezogen = self._gezogen
        self._start = None
        self._gezogen = False
        self.setCursor(QtCore.Qt.OpenHandCursor)
        if not gezogen:
            r = self._treffer(pos)
            if r:
                self.gewaehlt.emit(r)

    # -- Zeichnen --------------------------------------------------------
    #: Lichtrichtung im Bild (x nach rechts, y nach oben, z zum Betrachter)
    LICHT = (-0.35, 0.55, 0.76)
    #: Grundfarben der Seiten je Achse: x rot-, y gruen-, z blaustichig, wie
    #: das Achsenkreuz - so erkennt man die Seite auch ohne Text
    SEITENFARBEN = {"x": (222, 214, 206), "y": (208, 222, 208), "z": (206, 214, 228)}

    def _seitenfarbe(self, richtung: str, n_bild, hell: bool) -> QtGui.QColor:
        if hell:
            return QtGui.QColor(dsg.FARBEN["akzent"])
        grund = self.SEITENFARBEN.get(richtung.strip("+-").lower(), (214, 216, 220))
        L = self.LICHT
        lnorm = math.sqrt(sum(x * x for x in L))
        cos = sum(n_bild[i] * L[i] for i in range(3)) / lnorm
        schatt = 0.58 + 0.42 * max(0.0, cos)
        return QtGui.QColor(*[int(min(255, c * schatt + 18)) for c in grund])

    def paintEvent(self, _ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        f = p.font()
        f.setPointSize(8)
        f.setBold(True)
        p.setFont(f)
        linie = QtGui.QColor(dsg.FARBEN["linie"])
        R = self._matrix()
        feld = self._wuerfelfeld()
        # Weicher Schatten unter dem Wuerfel
        schatten = QtGui.QRadialGradient(feld.center().x(), feld.bottom() - 6,
                                         self.WUERFEL * 0.48)
        schatten.setColorAt(0.0, QtGui.QColor(0, 0, 0, 55))
        schatten.setColorAt(1.0, QtGui.QColor(0, 0, 0, 0))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QBrush(schatten))
        p.drawEllipse(QtCore.QPointF(feld.center().x(), feld.bottom() - 6),
                      self.WUERFEL * 0.46, self.WUERFEL * 0.13)
        seiten = self._projektion()
        normalen = {richtung: n for _t, richtung, n, _e in self.SEITEN}
        for _tiefe, nz, text, richtung, poly in seiten:
            if nz <= 0:
                continue
            hell = richtung == self._unter
            n = normalen.get(richtung, (0, 0, 1))
            n_bild = [sum(R[i][k] * n[k] for k in range(3)) for i in range(3)]
            farbe = self._seitenfarbe(richtung, n_bild, hell)
            # leichter Verlauf ueber die Seite: oben heller, unten dunkler
            br = poly.boundingRect()
            verlauf = QtGui.QLinearGradient(br.topLeft(), br.bottomLeft())
            verlauf.setColorAt(0.0, farbe.lighter(108))
            verlauf.setColorAt(1.0, farbe.darker(108))
            p.setBrush(QtGui.QBrush(verlauf))
            p.setPen(QtGui.QPen(QtGui.QColor(30, 40, 55, 150) if not hell else linie, 1.0))
            p.drawPolygon(poly)
            if nz > 0.3:
                # Beschriftung mit feinem Schatten, dann klar lesbar auf hell und dunkel
                rect = poly.boundingRect()
                f.setPointSize(9 if nz > 0.7 else 8)
                p.setFont(f)
                p.setPen(QtGui.QColor(255, 255, 255, 110))
                p.drawText(rect.translated(0.5, 0.5), QtCore.Qt.AlignCenter, text)
                p.setPen(QtGui.QColor("#ffffff" if hell else "#1c2a3a"))
                p.drawText(rect, QtCore.Qt.AlignCenter, text)
        # Glanzkante: die sichtbaren Aussenkanten etwas heller nachziehen
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 90), 1.0))
        p.setBrush(QtCore.Qt.NoBrush)
        for _tiefe, nz, _text, _richtung, poly in seiten:
            if nz > 0:
                p.drawPolyline(poly)
        # Die Richtungszeile: runde Knoepfe
        for rect, text, richtung in self._felder():
            hell = richtung == self._unter
            r2 = rect.adjusted(0.5, 1.0, -0.5, -1.0)
            p.setBrush(QtGui.QColor(dsg.FARBEN["akzent"] if hell else "#f7f9fb"))
            p.setPen(QtGui.QPen(QtGui.QColor(dsg.FARBEN["akzent"]) if hell else linie, 1.0))
            p.drawRoundedRect(r2, 5, 5)
            p.setPen(QtGui.QColor("#ffffff" if hell else dsg.FARBEN["text"]))
            f.setPointSize(7 if len(text) > 2 else 8)
            p.setFont(f)
            p.drawText(r2, QtCore.Qt.AlignCenter, text)
        p.end()


class Ansichtsrand(QtCore.QObject):
    """Haelt Glasleiste und Ansichtswuerfel an ihrem Platz ueber der Ansicht.

    Die Glasleiste steht **mittig oben**, der Wuerfel oben rechts.
    """

    def __init__(self, ansicht: QtWidgets.QWidget, leiste: Glasleiste,
                 wuerfel: Ansichtswuerfel):
        super().__init__(ansicht)
        self.ansicht = ansicht
        self.leiste = leiste
        self.wuerfel = wuerfel
        ansicht.installEventFilter(self)
        self.platzieren()

    def platzieren(self):
        """Leiste mittig oben, Wuerfel oben rechts - und nie uebereinander.

        In einem schmalen Fenster reicht die mittige Leiste bis unter den
        Wuerfel; dann rueckt sie so weit nach links, wie es geht.
        """
        b = self.ansicht.width()
        g = self.leiste.sizeHint()
        # feste Groesse des Wuerfels (setFixedSize) - sizeHint waere -1
        w = max(1, self.wuerfel.width())
        h = max(1, self.wuerfel.height())
        wx = max(12, b - w - 14)
        wy = 12
        x = (b - g.width()) // 2
        if x + g.width() > wx - 8:
            x = wx - 8 - g.width()
        if x < 12:
            # Leiste und Wuerfel passen nicht nebeneinander: der Wuerfel
            # rueckt unter die Leiste, ueberschneiden darf sich nichts.
            x = 12
            wy = 10 + g.height() + 8
        self.leiste.setGeometry(x, 10, g.width(), g.height())
        self.leiste.raise_()
        self.wuerfel.setGeometry(wx, wy, w, h)
        self.wuerfel.raise_()

    def eventFilter(self, obj, ev):
        if obj is self.ansicht and ev.type() == QtCore.QEvent.Resize:
            self.platzieren()
        return False


# ==========================================================================
# Gummiband: das Auswahlfenster ueber der Ansicht
# ==========================================================================
class Gummiband(QtWidgets.QWidget):
    """Das Auswahlfenster: ein durchscheinendes Rechteck ueber der Ansicht.

    Die erste Ecke setzt die linke Maustaste, die zweite die rechte. Von
    links nach rechts aufgezogen (blau, durchgezogen) zaehlt nur, was ganz
    im Fenster liegt; von rechts nach links (gruen, gestrichelt) auch alles,
    was das Fenster nur anschneidet - die Farben, wie sie CAD-Anwender
    kennen. Das Band faengt keine Mausereignisse; die Ansicht darunter
    bekommt sie weiter.
    """

    def __init__(self, ansicht: QtWidgets.QWidget):
        super().__init__(ansicht)
        self.setObjectName("gummiband")
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.kreuzend = False
        self.hide()

    def setzen(self, p1: QtCore.QPoint, p2: QtCore.QPoint, kreuzend: bool):
        """Die beiden Ecken (Bildpunkte der Ansicht, y von oben) uebernehmen."""
        self.kreuzend = bool(kreuzend)
        r = QtCore.QRect(QtCore.QPoint(p1), QtCore.QPoint(p2)).normalized()
        self.setGeometry(r.adjusted(-1, -1, 2, 2))
        self.update()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, False)
        farbe = QtGui.QColor(dsg.FARBEN["gut"] if self.kreuzend else dsg.FARBEN["akzent"])
        stift = QtGui.QPen(farbe, 1,
                           QtCore.Qt.DashLine if self.kreuzend else QtCore.Qt.SolidLine)
        fuellung = QtGui.QColor(farbe)
        fuellung.setAlpha(38)
        p.setPen(stift)
        p.setBrush(fuellung)
        p.drawRect(self.rect().adjusted(1, 1, -2, -2))
        p.end()

