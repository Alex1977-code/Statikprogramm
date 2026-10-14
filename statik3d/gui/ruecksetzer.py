"""Rücksetzer-Knöpfe unten rechts in der Ansicht und die Sichttasten H
(Ansichtspaket B, 14.10.2026; Vorbild ediBIM ``desktop/ruecksetzer.ts`` und
``desktop/tasten.ts``).

Ausgeblendetes und ein Schnitt sind Zustände, die man im Bild nicht sieht -
man sieht nur, dass etwas fehlt. Der Rückweg gehört darum dorthin, wo man ihn
braucht: ein Knopf „N Teile einblenden“ und ein Knopf „Schnitt aus“ unten
rechts, **nur solange** es etwas zurückzunehmen gibt. Ihre Reihenfolge ist fest
(Schnitt über Teile), damit derselbe Knopf nicht je nach Vorgeschichte einen
anderen Platz hat.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

#: Tasten der Ansicht: Befehl -> (Taste, Umschalt, Alt). Statik3D hat keine
#: umstellbare Tastenbelegung (die Kürzel des Ribbons und die Einzeltasten K S
#: L B F sind fest); die Belegung steht darum hier an einer Stelle.
#: Gelesen wird ``key()`` von Qt - auf der deutschen Tastatur ist das der
#: Buchstabe der Taste, mit Umschalt wie ohne.
SICHT_TASTEN = {"ausblenden": (QtCore.Qt.Key_H, False, False),
                "isolieren": (QtCore.Qt.Key_H, True, False),
                "einblenden": (QtCore.Qt.Key_H, False, True)}
#: So stehen die Tasten im Hinweis der Befehle
SICHT_TASTEN_TEXT = {"ausblenden": "H", "isolieren": "Umschalt+H", "einblenden": "Alt+H"}


def sicht_befehl(ereignis) -> str:
    """Der Befehl zu einem Tastenereignis - oder "" (Strg/Meta: nie)."""
    try:
        mod = ereignis.modifiers()
        if mod & (QtCore.Qt.ControlModifier | QtCore.Qt.MetaModifier):
            return ""
        umschalt = bool(mod & QtCore.Qt.ShiftModifier)
        alt = bool(mod & QtCore.Qt.AltModifier)
        k = int(ereignis.key())
    except Exception:                       # noqa: BLE001
        return ""
    for befehl, (taste, u, a) in SICHT_TASTEN.items():
        if k == int(taste) and u == umschalt and a == alt:
            return befehl
    return ""


class SichtTasten(QtCore.QObject):
    """Ereignisfilter an der Ansicht: H, Umschalt+H, Alt+H rufen ``ausloesen``.

    Ein eigener Filter statt eines Zweigs im Filter des Fensters: der kommt
    als letzter dazu und sieht die Taste darum zuerst. Alt+H wird schon beim
    ``ShortcutOverride`` angenommen, sonst nähme Qt es als Kürzel."""

    def __init__(self, ansicht: QtWidgets.QWidget, ausloesen):
        super().__init__(ansicht)
        self.ansicht = ansicht
        self.ausloesen = ausloesen
        ansicht.installEventFilter(self)

    def eventFilter(self, obj, ev):
        t = ev.type()
        if obj is self.ansicht and t in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress):
            befehl = sicht_befehl(ev)
            if befehl:
                if t == QtCore.QEvent.ShortcutOverride:
                    ev.accept()
                    return True
                if not ev.isAutoRepeat():
                    self.ausloesen(befehl)
                return True
        return False


class RadBeobachter(QtCore.QObject):
    """Meldet jeden Radschritt an der Ansicht, bevor das Fenster zoomt - und
    laesst das Ereignis durch. So wird beim Radzoom wie beim Drehen vereinfacht
    gezeichnet, ohne den Zoom selbst anzufassen."""

    def __init__(self, ansicht: QtWidgets.QWidget, melden):
        super().__init__(ansicht)
        self.ansicht = ansicht
        self.melden = melden
        ansicht.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.ansicht and ev.type() == QtCore.QEvent.Wheel:
            try:
                self.melden()
            except Exception:               # noqa: BLE001 - der Zoom geht vor
                pass
        return False


class Ruecksetzer(QtWidgets.QWidget):
    """Die Knöpfe „Schnitt aus“ und „N Teile einblenden“ unten rechts."""

    schnitt_aus = QtCore.Signal()
    teile_einblenden = QtCore.Signal()
    #: Abstand zum Rand [px]
    RAND = 10
    #: Rechts frei für ein Achsenkreuz unten rechts. Seit Paket C (14.10.2026)
    #: hat die Ansicht keines mehr (das Gizmo oben rechts zeigt die Achsen, nur
    #: das Berichtsbild trägt ein kleines); die Ecke ist frei, darum 0. Bis
    #: zur Zusammenführung 0,14 (``add_axes``, viewport 0,86 … 1,0).
    RECHTS_FREI = 0.0

    def __init__(self, ansicht: QtWidgets.QWidget):
        super().__init__(ansicht)
        self.ansicht = ansicht
        self.setObjectName("ruecksetzer")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        stil = ("QPushButton { background: rgba(255,255,255,235); color: #1f3b73; border: 1px solid #8fa3c0;"
                " border-radius: 4px; padding: 3px 10px; }"
                " QPushButton:hover { background: #e8f0fb; }")
        self.btn_schnitt = QtWidgets.QPushButton("Schnitt aus")
        self.btn_schnitt.setToolTip("Der Schnitt ist an - ausschalten und das ganze Modell zeigen")
        self.btn_teile = QtWidgets.QPushButton("")
        for b in (self.btn_schnitt, self.btn_teile):
            b.setStyleSheet(stil)
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.setFocusPolicy(QtCore.Qt.NoFocus)
            lay.addWidget(b, 0, QtCore.Qt.AlignRight)
        self.btn_schnitt.clicked.connect(self.schnitt_aus)
        self.btn_teile.clicked.connect(self.teile_einblenden)
        self._zuletzt = None
        ansicht.installEventFilter(self)
        self.aktualisieren(0, False)

    def aktualisieren(self, teile: int, schnitt: bool, was: str = "") -> None:
        """Knöpfe nach dem Zustand: ``teile`` ausgeblendete Teile, ``schnitt``
        an oder aus; ``was`` nennt im Hinweis, was ausgeblendet ist."""
        stand = (int(teile), bool(schnitt), was)
        if stand == self._zuletzt:
            return
        self._zuletzt = stand
        self.btn_schnitt.setVisible(bool(schnitt))
        self.btn_teile.setVisible(teile > 0)
        if teile > 0:
            self.btn_teile.setText("1 Teil einblenden" if teile == 1 else f"{teile:,} Teile einblenden".replace(",", "."))
            self.btn_teile.setToolTip((f"Ausgeblendet: {was} - " if was else "")
                                      + "alles wieder einblenden (Alt+H)")
        self.setVisible(bool(schnitt) or teile > 0)
        self.adjustSize()
        self.platzieren()

    def platzieren(self) -> None:
        g = self.sizeHint()
        b, h = self.ansicht.width(), self.ansicht.height()
        x = int(b - g.width() - self.RAND - self.RECHTS_FREI * b)
        y = int(h - g.height() - self.RAND)
        self.setGeometry(max(self.RAND, x), max(self.RAND, y), g.width(), g.height())
        self.raise_()

    def eventFilter(self, obj, ev):
        if obj is self.ansicht and ev.type() == QtCore.QEvent.Resize:
            self.platzieren()
        return False
