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


@dataclass
class Feld:
    """Ein Eingabefeld der Maske."""
    name: str
    text: str
    art: str = "zahl"            # zahl | ganz | text | wahl | haken | info
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
    abgebrochen = QtCore.Signal()

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
        lay.addLayout(knoepfe)
        # Weitere Knoepfe (Situation: Auswahl deaktivieren / aktivieren)
        self.zusatzknoepfe: dict[str, QtWidgets.QPushButton] = {}
        if zusatz:
            zeile = QtWidgets.QHBoxLayout()
            for text, ruf in zusatz:
                b = QtWidgets.QPushButton(text, self)
                b.clicked.connect(lambda _c=False, r=ruf: r())
                zeile.addWidget(b)
                self.zusatzknoepfe[text] = b
            lay.addLayout(zeile)
        self.setMinimumWidth(232)

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
        if self.punkte:
            if self.n_knoten >= 20:
                return ("In der Ansicht Punkte der Reihe nach anklicken (Knoten, Kanten, "
                        "Linien, Raster) – „Anwenden“ beendet. Esc schließt.")
            return (f"In der Ansicht {self.n_knoten} Punkt{'e' if self.n_knoten > 1 else ''} "
                    "anklicken (Knoten, Kanten, Linien, Raster, Arbeitsebene). Esc schließt.")
        return (f"In der Ansicht {self.n_knoten} Knoten anklicken – oder die "
                "Nummern eintragen. Esc schließt.")

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
        elif isinstance(w, QtWidgets.QLabel):
            w.setText(str(wert))
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
            # Eine lange Maske (Querschnitte) meldet eine Dehnung an und
            # bekommt damit den groesseren Teil der Hoehe; die kurzen Masken
            # bleiben bei ihrer natuerlichen Hoehe
            self.ziel.insertWidget(0, maske, int(getattr(maske, "dehnung", 0)))
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

    def will_punkte(self) -> bool:
        """Sammelt die offene Maske Weltpunkte statt Knoten?"""
        return self.offen() and bool(self.maske.n_knoten) and bool(getattr(self.maske, "punkte", False))

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
    padding: 3px; color: {text}; }}
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

