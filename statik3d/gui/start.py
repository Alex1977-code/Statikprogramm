"""Startbild: was man sieht, waehrend Statik3D laedt.

Das Windows-Programm ist eine einzige Datei von 200 MB. Beim Start packt es
sich aus, laedt Qt, VTK, numpy und scipy und baut die Oberflaeche - zusammen
zehn bis dreissig Sekunden, in denen sonst nichts zu sehen waere und man ein
zweites Mal doppelklickt. Darum zwei Stufen:

1. Der Packer (PyInstaller) zeigt ``packaging/splash.png`` schon waehrend
   des Auspackens, bevor Python ueberhaupt laeuft (Modul ``pyi_splash``).
2. Sobald Qt geladen ist, uebernimmt :class:`Startbild` (ein QSplashScreen)
   mit demselben Bild und meldet, was gerade geladen wird; das Packer-Bild
   wird dabei geschlossen. Steht das Hauptfenster, geht auch das Startbild.

Das Bild wird gezeichnet, nicht geladen (``startbild``); ``make_icon.py``
rendert daraus die PNG-Datei fuer den Packer.
"""
from PySide6 import QtCore, QtGui, QtWidgets

from . import symbole as sym

BREITE, HOEHE = 520, 300
#: Zeile, in der die Meldungen stehen (auch fuer den Packer: text_pos)
MELDUNG_Y = HOEHE - 40
#: Schrift des Startbilds - auf Windows Segoe UI, sonst ersetzt Qt sie
SCHRIFT = "Segoe UI"


def schrift(punkt: int, fett: bool = False) -> QtGui.QFont:
    f = QtGui.QFont(SCHRIFT)
    f.setPointSize(punkt)
    f.setBold(fett)
    return f


def schrift_vorhanden() -> bool:
    """Ob Qt eine echte Schrift hat.

    Ohne Schriftdatenbank - die Plattform ``offscreen`` auf Windows hat keine,
    solange ``QT_QPA_FONTDIR`` nicht gesetzt ist - zeichnet Qt jedes Zeichen als
    Kaestchen gleicher Breite. Ein so gerendertes Startbild des Packers zeigte
    statt „Statik3D“ acht Kaestchen. Eine echte Schrift erkennt man daran,
    dass ein „i“ schmaler ist als ein „W“.
    """
    if not QtGui.QFontDatabase.families():
        return False
    fm = QtGui.QFontMetrics(schrift(12))
    return fm.horizontalAdvance("i") < fm.horizontalAdvance("W")


def startbild(version: str = "", stand: str = "") -> QtGui.QPixmap:
    """Das Startbild: Programmsymbol, Name, Fassung, unten Platz fuer Meldungen."""
    pm = QtGui.QPixmap(BREITE, HOEHE)
    pm.fill(QtGui.QColor("#16243a"))
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
    verlauf = QtGui.QLinearGradient(0, 0, BREITE, HOEHE)
    verlauf.setColorAt(0.0, QtGui.QColor("#2b4d7a"))
    verlauf.setColorAt(0.6, QtGui.QColor("#1b2f4d"))
    verlauf.setColorAt(1.0, QtGui.QColor("#101c2e"))
    p.fillRect(pm.rect(), QtGui.QBrush(verlauf))
    # Lichtkante oben
    glanz = QtGui.QLinearGradient(0, 0, 0, HOEHE * 0.5)
    glanz.setColorAt(0.0, QtGui.QColor(255, 255, 255, 34))
    glanz.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    p.fillRect(QtCore.QRectF(0, 0, BREITE, HOEHE * 0.5), QtGui.QBrush(glanz))
    # Programmsymbol links
    p.drawPixmap(36, 46, sym.programmbild(128))
    # Name und Untertitel
    p.setFont(schrift(30, True))
    p.setPen(QtGui.QColor("#ffffff"))
    p.drawText(QtCore.QRect(190, 52, BREITE - 210, 50), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
               "Statik3D")
    p.setFont(schrift(11))
    p.setPen(QtGui.QColor("#c9d6e6"))
    p.drawText(QtCore.QRect(192, 102, BREITE - 212, 70), QtCore.Qt.AlignLeft | QtCore.Qt.TextWordWrap,
               "Statik, Nachweise nach Eurocode 3\nund Ermüdung für Stahlbau\nund Stahlwasserbau")
    fassung = f"Version {version}" if version else ""
    if stand:
        fassung += (" · " if fassung else "") + f"Stand {stand}"
    if fassung:
        p.setFont(schrift(10))
        p.setPen(QtGui.QColor("#f3c744"))
        p.drawText(QtCore.QRect(192, 178, BREITE - 212, 24), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                   fassung)
    # Fussleiste fuer die Meldungen
    p.fillRect(QtCore.QRect(0, HOEHE - 56, BREITE, 56), QtGui.QColor(0, 0, 0, 70))
    p.fillRect(QtCore.QRect(0, HOEHE - 57, BREITE, 1), QtGui.QColor(255, 255, 255, 40))
    p.end()
    return pm


def packer_melden(text: str):
    """Text auf dem Packer-Startbild (nur in der exe vorhanden)."""
    try:
        import pyi_splash          # noqa: PLC0415 - gibt es nur in der exe
        pyi_splash.update_text(text)
    except Exception:               # noqa: BLE001
        pass


def packer_schliessen():
    """Das Packer-Startbild schliessen, sobald Qt uebernimmt (oder bei --selbsttest)."""
    try:
        import pyi_splash          # noqa: PLC0415
        pyi_splash.close()
    except Exception:               # noqa: BLE001
        pass


class Startbild(QtWidgets.QSplashScreen):
    """Das Startbild mit Meldungen: „Grafik und Rechenkern werden geladen …“."""

    def __init__(self, version: str = None, stand: str = None):
        if version is None:
            try:
                from .. import __version__ as version
            except Exception:       # noqa: BLE001
                version = ""
        if stand is None:
            try:
                from ..update import build_info
                stand = (build_info().get("sha") or "")[:7]
            except Exception:       # noqa: BLE001
                stand = ""
        super().__init__(startbild(version, stand))
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, False)

    def show(self):
        super().show()
        self.melden("Statik3D wird gestartet …")
        # Ab jetzt zeigt Qt das Bild - das des Packers kann weg
        packer_schliessen()

    def melden(self, text: str):
        """Eine Zeile unten links - und das Bild dabei wirklich zeichnen."""
        self.showMessage(text, QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom, QtGui.QColor("#dfe8f2"))
        QtWidgets.QApplication.processEvents()

    def drawContents(self, p: QtGui.QPainter):
        p.setFont(schrift(10))
        p.setPen(QtGui.QColor("#dfe8f2"))
        p.drawText(QtCore.QRect(24, MELDUNG_Y - 6, BREITE - 48, 28),
                   QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, self.message())

    def fertig(self, fenster: QtWidgets.QWidget):
        """Das Hauptfenster steht: Startbild weg (und das des Packers, falls noch da)."""
        self.finish(fenster)
        packer_schliessen()
