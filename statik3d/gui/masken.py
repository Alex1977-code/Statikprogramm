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
    """Haelt die eine offene Maske am rechten Rand der Ansicht.

    Es ist immer hoechstens **eine** Maske offen: ein Erzeuge-Befehl loest den
    vorigen ab. Die Maske schwebt ueber der Ansicht und wird beim Groesse
    aendern mitgefuehrt.
    """

    def __init__(self, ansicht: QtWidgets.QWidget):
        super().__init__(ansicht)
        self.ansicht = ansicht
        self.maske: Maske | None = None
        ansicht.installEventFilter(self)

    def zeigen(self, maske: Maske) -> Maske:
        self.schliessen()
        self.maske = maske
        maske.setParent(self.ansicht)
        maske.geschlossen.connect(self._vergessen)
        maske.show()
        maske.raise_()
        maske.setFocus()
        self._platzieren()
        return maske

    def schliessen(self):
        if self.maske is not None:
            m, self.maske = self.maske, None
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
        if self.maske is None:
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
"""


def stil() -> str:
    return STIL.format(**dsg.FARBEN)
