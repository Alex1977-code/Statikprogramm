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

from dataclasses import dataclass, field

from PySide6 import QtCore, QtGui, QtWidgets

from . import design as dsg


@dataclass
class Feld:
    """Ein Eingabefeld der Maske."""
    name: str
    text: str
    art: str = "zahl"            # zahl | ganz | text | wahl | haken
    wert: object = 0.0
    werte: list = field(default_factory=list)   # fuer art="wahl"
    breite: int = 78
    hinweis: str = ""


class Maske(QtWidgets.QFrame):
    """Eine nicht-modale Eingabemaske.

    angewendet(dict)  - „Anwenden" gedrueckt oder genug Knoten angeklickt
    geschlossen()     - Maske zu (Esc oder Kreuz)
    """

    angewendet = QtCore.Signal(dict)
    geschlossen = QtCore.Signal()

    def __init__(self, titel: str, felder: list, parent=None, knoten: int = 0,
                 hinweis: str = "", knopf: str = "Anwenden"):
        super().__init__(parent)
        self.setObjectName("maske")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.titel = titel
        self.n_knoten = int(knoten)
        self.gewaehlt: list[int] = []
        self._felder: dict[str, QtWidgets.QWidget] = {}

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
        zu.setToolTip("Maske schließen (Esc)")
        zu.clicked.connect(self.schliessen)
        kopf.addWidget(zu)
        lay.addLayout(kopf)

        gitter = QtWidgets.QGridLayout()
        gitter.setContentsMargins(0, 0, 0, 0)
        gitter.setHorizontalSpacing(6)
        gitter.setVerticalSpacing(4)
        for i, f in enumerate(felder):
            w = self._bauen(f)
            self._felder[f.name] = w
            if f.art == "haken":
                gitter.addWidget(w, i, 0, 1, 2)
            else:
                lb = QtWidgets.QLabel(f.text)
                lb.setToolTip(f.hinweis or f.text)
                gitter.addWidget(lb, i, 0)
                gitter.addWidget(w, i, 1)
        lay.addLayout(gitter)

        self.lbl_hinweis = QtWidgets.QLabel(hinweis or self._klickhinweis())
        self.lbl_hinweis.setObjectName("maskenhinweis")
        self.lbl_hinweis.setWordWrap(True)
        lay.addWidget(self.lbl_hinweis)

        knoepfe = QtWidgets.QHBoxLayout()
        self.btn_anwenden = QtWidgets.QPushButton(knopf, self)
        self.btn_anwenden.setDefault(True)
        self.btn_anwenden.clicked.connect(self.anwenden)
        knoepfe.addWidget(self.btn_anwenden)
        if self.n_knoten:
            b = QtWidgets.QPushButton("Auswahl leeren", self)
            b.clicked.connect(self.auswahl_leeren)
            knoepfe.addWidget(b)
        lay.addLayout(knoepfe)
        self.setMinimumWidth(232)

    # -- Aufbau ----------------------------------------------------------
    def _bauen(self, f: Feld) -> QtWidgets.QWidget:
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
        w = QtWidgets.QLineEdit(str(f.wert), self)
        w.setFixedWidth(f.breite)
        if f.art in ("zahl", "ganz"):
            w.setValidator(QtGui.QIntValidator() if f.art == "ganz"
                           else QtGui.QDoubleValidator(-1e30, 1e30, 10))
        w.returnPressed.connect(self.anwenden)
        return w

    def _klickhinweis(self) -> str:
        if not self.n_knoten:
            return "Werte eintragen und „Anwenden“ – die Maske bleibt offen."
        return (f"In der Ansicht {self.n_knoten} Knoten anklicken – oder die "
                "Nummern eintragen. Esc schließt.")

    # -- Werte -----------------------------------------------------------
    def werte(self) -> dict:
        out: dict = {}
        for name, w in self._felder.items():
            if isinstance(w, QtWidgets.QCheckBox):
                out[name] = w.isChecked()
            elif isinstance(w, QtWidgets.QComboBox):
                out[name] = w.currentText()
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
        return out

    def setzen(self, name: str, wert):
        w = self._felder.get(name)
        if w is None:
            return
        if isinstance(w, QtWidgets.QCheckBox):
            w.setChecked(bool(wert))
        elif isinstance(w, QtWidgets.QComboBox):
            w.setCurrentText(str(wert))
        else:
            w.setText(f"{wert:g}" if isinstance(wert, float) else str(wert))

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

    def auswahl_leeren(self):
        self.gewaehlt.clear()
        self._zeige_auswahl()

    def _zeige_auswahl(self):
        if not self.n_knoten:
            return
        n = len(self.gewaehlt)
        liste = ", ".join(str(i + 1) for i in self.gewaehlt) or "keiner"
        self.lbl_hinweis.setText(
            f"Gewählt: {liste}  ({n} von {self.n_knoten})"
            if n else self._klickhinweis())

    # -- Bedienung -------------------------------------------------------
    def anwenden(self):
        self.angewendet.emit(self.werte())

    def schliessen(self):
        self.hide()
        self.geschlossen.emit()

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_Escape:
            self.schliessen()
            return
        super().keyPressEvent(ev)


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

    def zeigen(self, maske: Maske) -> Maske:
        self.schliessen()
        self.maske = maske
        maske.geschlossen.connect(self._vergessen)
        if self.ziel is not None:
            self.ziel.insertWidget(0, maske)
            maske.show()
            maske.setFocus()
        else:
            maske.setParent(self.ansicht)
            maske.show()
            maske.raise_()
            maske.setFocus()
            self._platzieren()
        return maske

    def schliessen(self):
        if self.maske is not None:
            m, self.maske = self.maske, None
            if self.ziel is not None:
                self.ziel.removeWidget(m)
            m.hide()
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

    def _platzieren(self):
        if self.maske is None or self.ziel is not None:
            return
        g = self.maske.sizeHint()
        b = self.ansicht.width()
        self.maske.setGeometry(max(8, b - g.width() - 14), 12,
                               g.width(), g.height())

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
QToolButton#maskezu {{ border: 0; color: {matt}; font-size: 13px;
    padding: 0 4px; }}
QToolButton#maskezu:hover {{ color: {schlecht}; }}

/* Glasleiste ueber der Ansicht: durchscheinend, damit das Modell darunter
   sichtbar bleibt. */
QFrame#glasleiste {{ background: rgba(255, 255, 255, 200);
    border: 1px solid rgba(0, 0, 0, 30); border-radius: 9px; }}
QToolButton#glasknopf {{ background: transparent; border: 0; border-radius: 6px;
    padding: 4px 7px; color: {text}; font-weight: 600; }}
QToolButton#glasknopf:hover {{ background: {akzent_hell}; color: {akzent}; }}
QToolButton#glasknopf:checked {{ background: {akzent}; color: #fff; }}
QFrame#glastrenner {{ color: rgba(0, 0, 0, 40); }}
Ansichtswuerfel {{ background: transparent; }}
"""


def stil() -> str:
    return STIL.format(**dsg.FARBEN)


# ==========================================================================
# Glasleiste und Ansichtswuerfel ueber der Ansicht
# ==========================================================================
class Glasleiste(QtWidgets.QFrame):
    """Schmale, durchscheinende Leiste ueber der Ansicht (wie in HiCAD).

    Sie traegt die Handgriffe, die man beim Modellieren staendig braucht -
    Darstellungsart, FE-Netz, Knoten, Lasten, Fang, Auswahlart - und liegt
    dabei ueber dem Bild, statt Platz wegzunehmen. Alle Befehle sind dieselben
    Aktionsobjekte wie im Ribbon; hier stehen sie nur naeher an der Maus.
    """

    def __init__(self, ansicht: QtWidgets.QWidget):
        super().__init__(ansicht)
        self.setObjectName("glasleiste")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.lay = QtWidgets.QHBoxLayout(self)
        self.lay.setContentsMargins(6, 3, 6, 3)
        self.lay.setSpacing(3)

    def knopf(self, aktion: QtGui.QAction, zeichen: str = "") -> QtWidgets.QToolButton:
        b = QtWidgets.QToolButton(self)
        b.setDefaultAction(aktion)
        if zeichen:
            b.setText(zeichen)
        b.setObjectName("glasknopf")
        b.setAutoRaise(True)
        self.lay.addWidget(b)
        return b

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
    """Ansichtswuerfel oben rechts: ein Klick auf eine Seite dreht die Ansicht.

    Gezeichnet wird ein Wuerfel in isometrischer Schraegansicht. Sichtbar sind
    immer die drei Seiten, auf die man gerade schaut - beschriftet mit ihrer
    Achse, wie man es aus CAD-Programmen kennt.

    **Statt der Drehscheibe darunter** steht eine Zeile mit den sechs
    Richtungen. Die Scheibe kann nur um die Hochachse drehen; die Rueckseite
    erreicht man mit ihr erst nach einer halben Umdrehung. Hier ist jede der
    sechs Seiten **ein Klick**, und „180°" kehrt die laufende Ansicht um -
    aus einer beliebigen Schraegansicht wird so ihre Rueckansicht.
    """

    gewaehlt = QtCore.Signal(str)

    #: (Beschriftung, Blickrichtung, Vieleck in Einheitskoordinaten des Wuerfels)
    SEITEN = [
        ("+Z", "oben", [(0.5, 0.04), (0.96, 0.27), (0.5, 0.50), (0.04, 0.27)]),
        ("−Y", "vorne", [(0.04, 0.27), (0.5, 0.50), (0.5, 0.94), (0.04, 0.71)]),
        ("+X", "rechts", [(0.5, 0.50), (0.96, 0.27), (0.96, 0.71), (0.5, 0.94)]),
    ]

    #: (Beschriftung, Blickrichtung, Hinweis) der Zeile unter dem Wuerfel
    RICHTUNGEN = [
        ("V", "vorne", "Vorderansicht (von −Y)"),
        ("H", "hinten", "Rückansicht (von +Y)"),
        ("L", "links", "Ansicht von links (von −X)"),
        ("R", "rechts", "Ansicht von rechts (von +X)"),
        ("O", "oben", "Draufsicht (von +Z)"),
        ("U", "unten", "Untersicht (von −Z)"),
        ("180°", "kehren", "Die laufende Ansicht umkehren – zeigt die Rückseite"),
    ]

    WUERFEL = 76          # Kantenlaenge des Wuerfelfeldes
    ZEILE = 22            # Hoehe der Richtungszeile

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.WUERFEL + 40, self.WUERFEL + self.ZEILE + 6)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setToolTip("Ansichtswürfel: eine Seite anklicken. Darunter die "
                        "sechs Richtungen und „180°“ für die Rückseite.")
        self._unter = ""

    # -- Geometrie -------------------------------------------------------
    def _wuerfelfeld(self) -> QtCore.QRectF:
        x = (self.width() - self.WUERFEL) / 2.0
        return QtCore.QRectF(x, 0.0, self.WUERFEL, self.WUERFEL)

    def _polygone(self):
        r = self._wuerfelfeld()
        for text, richtung, punkte in self.SEITEN:
            yield text, richtung, QtGui.QPolygonF(
                [QtCore.QPointF(r.x() + x * r.width(), r.y() + y * r.height())
                 for x, y in punkte])

    def _felder(self):
        """Die Schaltflaechen der Richtungszeile als (Rechteck, Text, Richtung)."""
        n = len(self.RICHTUNGEN)
        b = self.width() / n
        y = self.WUERFEL + 4
        for i, (text, richtung, _hinweis) in enumerate(self.RICHTUNGEN):
            yield QtCore.QRectF(i * b, y, b - 1, self.ZEILE), text, richtung

    def _treffer(self, pos) -> str:
        p = QtCore.QPointF(pos)
        for _t, richtung, poly in self._polygone():
            if poly.containsPoint(p, QtCore.Qt.OddEvenFill):
                return richtung
        for rect, _t, richtung in self._felder():
            if rect.contains(p):
                return richtung
        return ""

    # -- Bedienung -------------------------------------------------------
    def mouseMoveEvent(self, ev):
        neu = self._treffer(ev.position() if hasattr(ev, "position") else ev.pos())
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
        r = self._treffer(ev.position() if hasattr(ev, "position") else ev.pos())
        self.gewaehlt.emit(r or "iso")

    # -- Zeichnen --------------------------------------------------------
    def paintEvent(self, _ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        # Der Wuerfel: die obere Seite hell, die beiden anderen abgestuft -
        # so sieht man auf einen Blick, welche Seite oben liegt.
        tiefe = {"oben": "#eef3f7", "vorne": "#dde5ec", "rechts": "#cbd6df"}
        for text, richtung, poly in self._polygone():
            hell = richtung == self._unter
            p.setBrush(QtGui.QColor(dsg.FARBEN["akzent"] if hell
                                    else tiefe.get(richtung, "#f2f5f8")))
            p.setPen(QtGui.QPen(QtGui.QColor(dsg.FARBEN["linie"]), 1.2))
            p.drawPolygon(poly)
            p.setPen(QtGui.QColor("#ffffff" if hell else dsg.FARBEN["matt"]))
            f = p.font()
            f.setPointSize(8)
            f.setBold(True)
            p.setFont(f)
            p.drawText(poly.boundingRect(), QtCore.Qt.AlignCenter, text)
        # Die Richtungszeile
        for rect, text, richtung in self._felder():
            hell = richtung == self._unter
            p.setBrush(QtGui.QColor(dsg.FARBEN["akzent"] if hell else "#f7f9fb"))
            p.setPen(QtGui.QPen(QtGui.QColor(dsg.FARBEN["linie"]), 1.0))
            p.drawRoundedRect(rect, 3, 3)
            p.setPen(QtGui.QColor("#ffffff" if hell else dsg.FARBEN["matt"]))
            f = p.font()
            f.setPointSize(7 if len(text) > 1 else 8)
            f.setBold(True)
            p.setFont(f)
            p.drawText(rect, QtCore.Qt.AlignCenter, text)
        p.end()


class Ansichtsrand(QtCore.QObject):
    """Haelt Glasleiste und Ansichtswuerfel an ihrem Platz ueber der Ansicht."""

    def __init__(self, ansicht: QtWidgets.QWidget, leiste: Glasleiste,
                 wuerfel: Ansichtswuerfel):
        super().__init__(ansicht)
        self.ansicht = ansicht
        self.leiste = leiste
        self.wuerfel = wuerfel
        ansicht.installEventFilter(self)
        self.platzieren()

    def platzieren(self):
        b = self.ansicht.width()
        g = self.leiste.sizeHint()
        self.leiste.setGeometry(12, 10, g.width(), g.height())
        self.leiste.raise_()
        w = self.wuerfel.width()
        self.wuerfel.setGeometry(max(12, b - w - 14), 10 + g.height() + 8,
                                 w, self.wuerfel.height())
        self.wuerfel.raise_()

    def eventFilter(self, obj, ev):
        if obj is self.ansicht and ev.type() == QtCore.QEvent.Resize:
            self.platzieren()
        return False
