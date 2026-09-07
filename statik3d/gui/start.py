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


# ==========================================================================
# Die 3D-Szene des Startbilds
# ==========================================================================
# Gerechnet, nicht gemalt. Die Halle steht als Weltkoordinaten da und wird
# zentralperspektivisch abgebildet; Fluchten, Verdeckung und Schattierung
# ergeben sich daraus von selbst. Bewusst ohne numpy: das Startbild soll
# erscheinen, *bevor* die schweren Pakete geladen sind - das ist sein Zweck.
#
# Statisch ist das Bild ein vollstaendiges System, kein huebsches Gestaenge:
#
# * Drei **Zweigelenkrahmen** in der Querrichtung, jeder an beiden Stielfuessen
#   gelenkig gelagert - sechs Lager, nicht vier.
# * **Pfetten** an Traufe und First verbinden die Rahmen.
# * **Dach- und Wandverband** im Endfeld: ohne sie waere die Halle in
#   Laengsrichtung eine Verschieblichkeit, also gerade kein Tragwerk. Genau
#   das faellt auf einem Startbild fuer ein Statikprogramm auf.
#
# Die Farbe der Dachhaut ist kein Verlauf nach Gefuehl, sondern das Ergebnis
# des Programms selbst: siehe DACH_M.

#: Blickpunkt, Ziel und Brennweite der Szene
AUGE, ZIEL, BRENN = (13.5, -21.0, 13.0), (0.0, 4.6, 1.2), 1.30
#: Richtung des Lichts (auf die Flaechen zu), von oben links vorn
LICHT = (-0.45, -0.72, 0.53)
#: Abmessungen der Halle [m]: halbe Spannweite, Traufe, First, Feldweite
SPANN, TRAUFE, FIRST, FELD = 5.2, 3.6, 5.8, 4.6

#: |M| je Riegelelement des Zweigelenkrahmens unter Gleichlast, auf den
#: Groesstwert bezogen - Traufe links ueber den First zur Traufe rechts,
#: acht Elemente je Dachhaelfte.
#:
#: **Mit dem Loeser dieses Programms gerechnet**, nicht geschaetzt:
#: tests/test_startbild.py stellt das System noch einmal auf, rechnet es und
#: vergleicht. Der Test prueft zugleich, dass es wirklich ein Zweigelenk-
#: rahmen ist (M = 0 an beiden Fuessen), dass die Auflagerkraefte die Last
#: tragen und dass die Horizontalschuebe sich aufheben.
DACH_M = (1.000, 0.580, 0.226, 0.283, 0.438, 0.527, 0.550, 0.550,
          0.550, 0.550, 0.527, 0.438, 0.283, 0.226, 0.580, 1.000)

#: Die Farbskala der Ergebnisdarstellung: Blau - Gruen - Gelb - Rot
RAMPE = ((0.00, (47, 111, 176)), (0.38, (55, 148, 110)),
         (0.68, (201, 162, 39)), (1.00, (181, 83, 60)))


def _minus(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _skalar(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _einheit(a):
    L = _skalar(a, a) ** 0.5
    return (a[0] / L, a[1] / L, a[2] / L) if L > 1e-12 else (0.0, 0.0, 0.0)


def _mische(A, B, t):
    return (A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t,
            A[2] + (B[2] - A[2]) * t)


def _rampe(t: float) -> QtGui.QColor:
    """Wert 0…1 auf die Farbskala abbilden (linear zwischen den Stuetzstellen)."""
    t = max(0.0, min(1.0, float(t)))
    for (t0, c0), (t1, c1) in zip(RAMPE, RAMPE[1:]):
        if t <= t1:
            f = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return QtGui.QColor(*[int(x + (y - x) * f) for x, y in zip(c0, c1)])
    return QtGui.QColor(*RAMPE[-1][1])


def _kamera(hoehe: float, mitte):
    """Zentralprojektion Welt -> Bild. Rueckgabe f(P) -> (x, y, tiefe)."""
    vor = _einheit(_minus(ZIEL, AUGE))
    rechts = _einheit(_kreuz(vor, (0.0, 0.0, 1.0)))
    oben = _kreuz(rechts, vor)
    massstab = BRENN * hoehe

    def ab(P):
        d = _minus(P, AUGE)
        t = max(0.1, _skalar(d, vor))
        return (mitte[0] + massstab * _skalar(d, rechts) / t,
                mitte[1] - massstab * _skalar(d, oben) / t, t)
    return ab


def _schattiert(grund: QtGui.QColor, ecken) -> QtGui.QColor:
    """Lambert-Schattierung aus der Flaechennormalen."""
    n = _einheit(_kreuz(_minus(ecken[1], ecken[0]), _minus(ecken[2], ecken[0])))
    f = 0.36 + 0.64 * max(0.0, abs(_skalar(LICHT, n)))
    return QtGui.QColor(min(255, int(grund.red() * f)),
                        min(255, int(grund.green() * f)),
                        min(255, int(grund.blue() * f)))


def _rahmenpunkte(y: float):
    """Die fuenf Knoten eines Rahmens: Fuss, Traufe, First, Traufe, Fuss."""
    return [(-SPANN, y, 0.0), (-SPANN, y, TRAUFE), (0.0, y, FIRST),
            (SPANN, y, TRAUFE), (SPANN, y, 0.0)]


def _szene(p: QtGui.QPainter, breite: int, hoehe: int) -> None:
    """Die Halle zeichnen: Boden, Schatten, Dachhaut, Staebe, Verband, Lager."""
    ab = _kamera(hoehe, (breite * 0.66, hoehe * 0.50))
    ys = [0.0, FELD, 2 * FELD]
    rahmen = [_rahmenpunkte(y) for y in ys]

    def bild(P):
        q = ab(P)
        return QtCore.QPointF(q[0], q[1])

    # ---- Bodenraster: die Fluchten geben dem Bild die Tiefe ---------------
    p.setBrush(QtCore.Qt.NoBrush)
    for i in range(-5, 6):
        p.setPen(QtGui.QPen(QtGui.QColor(120, 165, 220, 30), 1.0))
        p.drawLine(bild((i * 2.2, -6.0, 0.0)), bild((i * 2.2, 17.0, 0.0)))
    for j in range(-3, 9):
        p.setPen(QtGui.QPen(QtGui.QColor(120, 165, 220, max(0, 36 - 2 * j)), 1.0))
        p.drawLine(bild((-11.0, j * 2.2, 0.0)), bild((11.0, j * 2.2, 0.0)))

    # ---- Schlagschatten ---------------------------------------------------
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor(0, 0, 0, 62))
    p.drawPolygon(QtGui.QPolygonF([bild(P) for P in (
        (-SPANN - 1.2, ys[0] - 0.4, 0.0), (SPANN + 0.3, ys[0] - 0.4, 0.0),
        (SPANN + 1.6, ys[-1] + 0.7, 0.0), (-SPANN - 0.1, ys[-1] + 0.7, 0.0))]))

    # ---- Dachhaut: je Riegelelement ein Feld, eingefaerbt mit |M| ---------
    felder = []
    for seite in (0, 1):
        i0 = 1 + seite                      # 1: Traufe links -> First
        for iu in range(8):                 # acht Elemente je Dachhaelfte
            for iv in range(len(ys) - 1):
                u0, u1 = iu / 8.0, (iu + 1) / 8.0
                A, B = rahmen[0][i0], rahmen[0][i0 + 1]
                ecken = []
                for u, k in ((u0, iv), (u1, iv), (u1, iv + 1), (u0, iv + 1)):
                    P = _mische(A, B, u)
                    ecken.append((P[0], ys[k], P[2]))
                pr = [ab(P) for P in ecken]
                felder.append((sum(q[2] for q in pr) / 4.0, ecken, pr,
                               DACH_M[seite * 8 + iu]))
    for _t, ecken, pr, wert in sorted(felder, key=lambda f: -f[0]):
        p.setBrush(_schattiert(_rampe(wert), ecken))
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 22), 0.8))
        p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(q[0], q[1]) for q in pr]))

    gold = QtGui.QColor("#f3c744")

    def vordergrund(P):
        """1 vorn, 0 hinten - danach werden Dicke und Deckkraft abgestuft."""
        return 1.0 - min(0.62, (ab(P)[2] - 14.0) / 26.0)

    # ---- Dach- und Wandverband im Endfeld ---------------------------------
    # Ohne sie waere die Halle in Laengsrichtung verschieblich. Sie liegen im
    # ersten Feld und sind duenner gezeichnet als die Rahmen - so, wie ein
    # Verband auch gebaut wird.
    p.setPen(QtGui.QPen(QtGui.QColor(200, 214, 232, 120), 1.4,
                        QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    for i in (1, 2, 3):                     # Traufe links, First, Traufe rechts
        if i < 3:
            p.drawLine(bild(rahmen[0][i]), bild(rahmen[1][i + 1]))
            p.drawLine(bild(rahmen[0][i + 1]), bild(rahmen[1][i]))
    for i in (0, 4):                        # Wandverband in beiden Seitenwaenden
        p.drawLine(bild(rahmen[0][i]), bild(rahmen[1][1 if i == 0 else 3]))
        p.drawLine(bild(rahmen[0][1 if i == 0 else 3]), bild(rahmen[1][i]))

    # ---- Pfetten ----------------------------------------------------------
    p.setPen(QtGui.QPen(QtGui.QColor(243, 199, 68, 160), 1.9,
                        QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    for i in (1, 2, 3):
        p.drawLine(bild(rahmen[0][i]), bild(rahmen[-1][i]))

    # ---- Die Rahmen selbst: hinten duenn und blass, vorn kraeftig ---------
    for k in range(len(ys)):
        v = vordergrund(rahmen[k][2])
        p.setPen(QtGui.QPen(QtGui.QColor(gold.red(), gold.green(), gold.blue(),
                                         int(95 + 160 * v)),
                            max(1.3, 4.8 * v), QtCore.Qt.SolidLine,
                            QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        p.setBrush(QtCore.Qt.NoBrush)
        weg = QtGui.QPainterPath()
        for j, P in enumerate(rahmen[k]):
            (weg.moveTo if j == 0 else weg.lineTo)(bild(P))
        p.drawPath(weg)

    # ---- Knoten als kleine Kugeln ----------------------------------------
    for k in range(len(ys)):
        v = vordergrund(rahmen[k][2])
        for P in rahmen[k]:
            mp, r = bild(P), max(1.5, 3.8 * v)
            kugel = QtGui.QRadialGradient(mp - QtCore.QPointF(r * 0.3, r * 0.35), r * 1.6)
            kugel.setColorAt(0.0, QtGui.QColor("#fff6d0"))
            kugel.setColorAt(1.0, QtGui.QColor("#c08a12"))
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QBrush(kugel))
            p.drawEllipse(mp, r, r)

    # ---- Lager: an ALLEN sechs Stielfuessen, gelenkig -------------------
    # Ein Zweigelenkrahmen hat zwei Gelenke - drei Rahmen also sechs Lager.
    # Vorher standen dort vier, und das faellt jedem auf, der so etwas rechnet.
    for k in range(len(ys)):
        v = vordergrund(rahmen[k][2])
        for P in (rahmen[k][0], rahmen[k][4]):
            q, d = bild(P), max(3.2, 6.4 * v)
            p.setBrush(QtGui.QColor(78, 192, 122, int(150 + 105 * v)))
            p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 70), 1.0))
            p.drawPolygon(QtGui.QPolygonF([
                q, QtCore.QPointF(q.x() - d, q.y() + d * 1.35),
                QtCore.QPointF(q.x() + d, q.y() + d * 1.35)]))
            # Der Strich unter dem Dreieck: die Auflagerlinie
            p.setPen(QtGui.QPen(QtGui.QColor(78, 192, 122, int(120 + 90 * v)), 1.6))
            p.drawLine(QtCore.QPointF(q.x() - d * 1.4, q.y() + d * 1.5),
                       QtCore.QPointF(q.x() + d * 1.4, q.y() + d * 1.5))


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
    # Die Halle in Zentralprojektion - sie traegt das Bild
    _szene(p, BREITE, HOEHE)
    # Damit der Text vor der Szene lesbar bleibt: nach links hin abdunkeln
    schleier = QtGui.QLinearGradient(0, 0, BREITE * 0.62, 0)
    schleier.setColorAt(0.0, QtGui.QColor(16, 28, 46, 232))
    schleier.setColorAt(0.62, QtGui.QColor(16, 28, 46, 190))
    schleier.setColorAt(1.0, QtGui.QColor(16, 28, 46, 0))
    p.fillRect(QtCore.QRectF(0, 0, BREITE * 0.62, HOEHE), QtGui.QBrush(schleier))
    # Programmsymbol klein ueber dem Namen
    p.drawPixmap(34, 44, sym.programmbild(46))
    # Name - mit einem Schatten darunter, damit er von der Flaeche abhebt
    p.setFont(schrift(30, True))
    p.setPen(QtGui.QColor(0, 0, 0, 120))
    p.drawText(QtCore.QRect(35, 100, BREITE - 60, 50), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
               "Statik3D")
    p.setPen(QtGui.QColor("#ffffff"))
    p.drawText(QtCore.QRect(34, 98, BREITE - 60, 50), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
               "Statik3D")
    p.setFont(schrift(11))
    p.setPen(QtGui.QColor("#c9d6e6"))
    p.drawText(QtCore.QRect(36, 146, 290, 70), QtCore.Qt.AlignLeft | QtCore.Qt.TextWordWrap,
               "Statik, Nachweise nach Eurocode 3\nund Ermüdung für Stahlbau\nund Stahlwasserbau")
    fassung = f"Version {version}" if version else ""
    if stand:
        fassung += (" · " if fassung else "") + f"Stand {stand}"
    if fassung:
        p.setFont(schrift(10))
        p.setPen(QtGui.QColor("#f3c744"))
        p.drawText(QtCore.QRect(36, 216, 290, 24), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
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
