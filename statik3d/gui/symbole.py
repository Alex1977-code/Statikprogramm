"""
Symbole der Oberflaeche - gezeichnet, nicht geladen.

Jedes Symbol ist eine kleine Zeichenvorschrift auf einem 24 x 24 grossen
Feld und wird mit QPainter in der gewuenschten Groesse gemalt. Das hat drei
Gruende gegenueber Bilddateien:

* **Scharf in jeder Groesse** - Ribbon (28 px), Glasleiste (20 px) und
  Schnellzugriff (16 px) bekommen dieselbe Vorschrift, nichts wird skaliert.
* **Eine Farbwelt** - die Symbole nehmen die Farben aus ``design.FARBEN``;
  auf einem eingeschalteten Knopf (blauer Grund) werden sie weiss.
* **Nichts zum Verlieren** - keine Dateien, die in der exe fehlen koennten.

Benutzung::

    from . import symbole as sym
    knopf.setIcon(sym.symbol("knoten"))          # nach Name
    aktion.setIcon(sym.fuer_befehl("Speichern"))  # nach Beschriftung geraten

Ein Name, den es nicht gibt, ergibt kein leeres Bild, sondern eine runde
Plakette mit dem Anfangsbuchstaben - so hat jeder Befehl ein Symbol, und man
sieht sofort, welchem noch eine eigene Zeichnung fehlt.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui

from . import design as dsg

#: Kantenlaenge des Zeichenfelds - alle Vorschriften rechnen in diesem Mass
FELD = 24.0
#: Groessen, in denen ein Symbol vorgehalten wird (logische Bildpunkte)
GROESSEN = (16, 20, 24, 28, 32, 48)

_ZWISCHEN: dict = {}


# --------------------------------------------------------------------------
# Zeichenhilfen
# --------------------------------------------------------------------------
class Stift:
    """Der Malkasten einer Vorschrift: Painter, Farben, Grundformen."""

    def __init__(self, p: QtGui.QPainter, farbe: QtGui.QColor,
                 akzent: QtGui.QColor, breite: float = 1.8):
        self.p = p
        self.farbe = farbe
        self.akzent = akzent
        self.breite = breite

    def stift(self, farbe=None, breite: float = None, gestrichelt: bool = False):
        pen = QtGui.QPen(farbe or self.farbe, breite or self.breite)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        if gestrichelt:
            pen.setStyle(QtCore.Qt.DashLine)
            pen.setDashPattern([2.2, 2.2])
        self.p.setPen(pen)
        self.p.setBrush(QtCore.Qt.NoBrush)

    def fuellung(self, farbe=None, rand=None):
        self.p.setBrush(QtGui.QBrush(farbe or self.farbe))
        self.p.setPen(QtGui.QPen(rand, 1.2) if rand is not None else QtCore.Qt.NoPen)

    def linie(self, x1, y1, x2, y2):
        self.p.drawLine(QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2))

    def zug(self, punkte, schliessen: bool = False):
        poly = QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in punkte])
        if schliessen:
            self.p.drawPolygon(poly)
        else:
            self.p.drawPolyline(poly)

    def kreis(self, x, y, r):
        self.p.drawEllipse(QtCore.QPointF(x, y), r, r)

    def rechteck(self, x, y, b, h, radius: float = 0.0):
        r = QtCore.QRectF(x, y, b, h)
        if radius:
            self.p.drawRoundedRect(r, radius, radius)
        else:
            self.p.drawRect(r)

    def pfeil(self, x1, y1, x2, y2, kopf: float = 3.2):
        """Linie mit Spitze am Ende (x2, y2)."""
        self.linie(x1, y1, x2, y2)
        a = math.atan2(y2 - y1, x2 - x1)
        for w in (a + 2.6, a - 2.6):
            self.linie(x2, y2, x2 + kopf * math.cos(w), y2 + kopf * math.sin(w))

    def text(self, s: str, groesse: float = 9.5, fett: bool = True,
             rect=None, farbe=None):
        f = self.p.font()
        f.setPointSizeF(groesse)
        f.setBold(fett)
        self.p.setFont(f)
        self.p.setPen(farbe or self.farbe)
        self.p.drawText(rect or QtCore.QRectF(0, 0, FELD, FELD),
                        QtCore.Qt.AlignCenter, s)


# --------------------------------------------------------------------------
# Die Vorschriften. Jede zeichnet in ein 24 x 24 grosses Feld.
# --------------------------------------------------------------------------
def _wuerfel_umriss(s: Stift, fuellen: bool = False, durchsichtig: bool = False):
    """Ein Quader in Schraegansicht - Grundform vieler Symbole."""
    vorn = [(4, 9), (14, 9), (14, 20), (4, 20)]
    oben = [(4, 9), (9, 4), (19, 4), (14, 9)]
    rechts = [(14, 9), (19, 4), (19, 15), (14, 20)]
    if fuellen:
        s.fuellung(s.farbe if not durchsichtig else _mit_alpha(s.farbe, 70))
        for teil in (vorn, oben, rechts):
            s.zug(teil, True)
    s.stift()
    for teil in (vorn, oben, rechts):
        s.zug(teil, True)
    if durchsichtig:
        s.stift(gestrichelt=True, breite=1.2)
        s.linie(4, 20, 9, 15)
        s.linie(9, 15, 9, 4)
        s.linie(9, 15, 19, 15)


def _mit_alpha(c: QtGui.QColor, a: int) -> QtGui.QColor:
    d = QtGui.QColor(c)
    d.setAlpha(a)
    return d


def z_voll(s: Stift):
    _wuerfel_umriss(s, fuellen=True)


def z_transparent(s: Stift):
    _wuerfel_umriss(s, fuellen=True, durchsichtig=True)


def z_hiddenline(s: Stift):
    s.fuellung(QtGui.QColor("#ffffff"), s.farbe)
    for teil in ([(4, 9), (14, 9), (14, 20), (4, 20)],
                 [(4, 9), (9, 4), (19, 4), (14, 9)],
                 [(14, 9), (19, 4), (19, 15), (14, 20)]):
        s.zug(teil, True)


def z_draht(s: Stift):
    s.stift(breite=1.5)
    for teil in ([(4, 9), (14, 9), (14, 20), (4, 20)],
                 [(4, 9), (9, 4), (19, 4), (14, 9)],
                 [(14, 9), (19, 4), (19, 15), (14, 20)]):
        s.zug(teil, True)
    s.linie(4, 20, 9, 15)
    s.linie(9, 15, 9, 4)
    s.linie(9, 15, 19, 15)


def z_knoten(s: Stift):
    s.fuellung()
    for x, y in ((6, 18), (18, 18), (12, 6)):
        s.kreis(x, y, 2.6)


def z_linien(s: Stift):
    s.stift()
    s.linie(4, 19, 13, 7)
    s.linie(13, 7, 20, 14)
    s.fuellung()
    for x, y in ((4, 19), (13, 7), (20, 14)):
        s.kreis(x, y, 1.9)


def z_staebe(s: Stift):
    # Ein Traeger mit I-Profil am Ende
    s.stift(breite=2.6)
    s.linie(3, 15, 17, 8)
    s.stift(breite=1.4)
    s.linie(17, 5, 21, 5)
    s.linie(17, 11, 21, 11)
    s.linie(19, 5, 19, 11)


def z_flaechen(s: Stift):
    s.fuellung(_mit_alpha(s.farbe, 90), s.farbe)
    s.zug([(3, 16), (10, 6), (21, 8), (14, 19)], True)


def z_volumen(s: Stift):
    _wuerfel_umriss(s, fuellen=True)


def z_netz(s: Stift):
    s.stift(breite=1.4)
    for i in range(4):
        s.linie(4, 4 + i * 5.33, 20, 4 + i * 5.33)
        s.linie(4 + i * 5.33, 4, 4 + i * 5.33, 20)


def z_lasten(s: Stift):
    s.stift()
    s.linie(4, 5, 20, 5)
    for x in (6, 12, 18):
        s.pfeil(x, 6, x, 17, 2.8)


def z_nummern(s: Stift):
    s.text("#", 11)


def z_fang(s: Stift):
    # Ein Fadenkreuz mit Fangkreis
    s.stift(breite=1.5)
    s.kreis(12, 12, 6)
    s.linie(12, 2.5, 12, 8)
    s.linie(12, 16, 12, 21.5)
    s.linie(2.5, 12, 8, 12)
    s.linie(16, 12, 21.5, 12)
    s.fuellung(s.akzent)
    s.kreis(12, 12, 1.8)


def _fangkreis(s: Stift):
    s.stift(s.akzent, 1.4, gestrichelt=True)
    s.kreis(15.5, 15.5, 6.0)


def z_fang_knoten(s: Stift):
    _fangkreis(s)
    s.fuellung()
    s.kreis(15.5, 15.5, 2.6)
    s.stift(breite=1.4)
    s.linie(3, 20, 15.5, 15.5)
    s.linie(15.5, 15.5, 21, 5)


def z_fang_linie(s: Stift):
    _fangkreis(s)
    s.stift(breite=2.0)
    s.linie(3, 20, 21, 7)
    s.fuellung(s.akzent)
    s.kreis(15.5, 15.5 - 3.3, 1.6)


def z_fang_stab(s: Stift):
    _fangkreis(s)
    s.stift(breite=3.0)
    s.linie(3, 19, 16, 13)
    s.fuellung(s.akzent)
    s.kreis(16, 13, 1.8)


def z_fang_flaeche(s: Stift):
    _fangkreis(s)
    s.fuellung(_mit_alpha(s.farbe, 80), s.farbe)
    s.zug([(3, 17), (9, 5), (19, 7), (14, 19)], True)
    s.fuellung(s.akzent)
    s.kreis(11.3, 12.0, 1.8)


def z_fang_volumen(s: Stift):
    _fangkreis(s)
    s.stift(breite=1.4)
    for teil in ([(3, 9), (12, 9), (12, 19), (3, 19)],
                 [(3, 9), (7, 5), (16, 5), (12, 9)],
                 [(12, 9), (16, 5), (16, 15), (12, 19)]):
        s.zug(teil, True)
    s.fuellung(s.akzent)
    s.kreis(9.5, 12, 1.8)


def z_fang_mitte(s: Stift):
    s.stift(breite=2.0)
    s.linie(3, 17, 21, 7)
    s.fuellung(s.akzent)
    s.kreis(12, 12, 2.4)
    s.stift(s.akzent, 1.2)
    s.linie(12, 6, 12, 18)


def z_fang_raster(s: Stift):
    s.stift(breite=1.1, gestrichelt=True)
    for i in range(4):
        s.linie(4, 4 + i * 5.33, 20, 4 + i * 5.33)
        s.linie(4 + i * 5.33, 4, 4 + i * 5.33, 20)
    s.fuellung(s.akzent)
    s.kreis(9.33, 9.33, 2.2)


def z_iso(s: Stift):
    _wuerfel_umriss(s)
    s.text("iso", 6.5, True, QtCore.QRectF(0, 15, 24, 9))


def z_kehren(s: Stift):
    s.stift()
    p = QtGui.QPainterPath()
    p.arcMoveTo(QtCore.QRectF(5, 5, 14, 14), 30)
    p.arcTo(QtCore.QRectF(5, 5, 14, 14), 30, 300)
    s.p.drawPath(p)
    s.pfeil(17.5, 7.5, 19.2, 5.2, 3.0)


def z_zoom(s: Stift):
    s.stift()
    s.kreis(10, 10, 6)
    s.linie(14.5, 14.5, 21, 21)
    s.linie(7, 10, 13, 10)
    s.linie(10, 7, 10, 13)


def z_neu(s: Stift):
    s.stift()
    s.zug([(6, 3), (14, 3), (19, 8), (19, 21), (6, 21)], True)
    s.linie(14, 3, 14, 8)
    s.linie(14, 8, 19, 8)
    s.stift(s.akzent, 2.0)
    s.linie(9.5, 14.5, 15.5, 14.5)
    s.linie(12.5, 11.5, 12.5, 17.5)


def z_oeffnen(s: Stift):
    s.stift()
    s.zug([(3, 6), (9, 6), (11, 8), (20, 8), (20, 19), (3, 19)], True)
    s.fuellung(_mit_alpha(s.akzent, 90), s.akzent)
    s.zug([(5, 11), (22, 11), (20, 19), (3, 19)], True)


def z_speichern(s: Stift):
    s.stift()
    s.rechteck(4, 4, 16, 16, 2)
    s.fuellung(s.farbe)
    s.rechteck(8, 4, 8, 5)
    s.stift()
    s.rechteck(7.5, 13, 9, 7)


def z_speichern_unter(s: Stift):
    z_speichern(s)
    s.stift(s.akzent, 2.0)
    s.pfeil(20, 3, 20, 9, 2.6)


def z_import(s: Stift):
    s.stift()
    s.zug([(4, 14), (4, 21), (20, 21), (20, 14)])
    s.stift(s.akzent, 2.2)
    s.pfeil(12, 3, 12, 15, 3.4)


def z_export(s: Stift):
    s.stift()
    s.zug([(4, 14), (4, 21), (20, 21), (20, 14)])
    s.stift(s.akzent, 2.2)
    s.pfeil(12, 15, 12, 3, 3.4)


def z_beispiel(s: Stift):
    s.stift()
    s.zug([(4, 20), (4, 8), (12, 3), (20, 8), (20, 20)])
    s.linie(4, 20, 20, 20)
    s.fuellung(s.akzent)
    s.rechteck(10, 13, 4, 7)


def z_rueckgaengig(s: Stift):
    s.stift(breite=2.0)
    p = QtGui.QPainterPath()
    p.moveTo(6, 10)
    p.cubicTo(6, 10, 19, 6, 19, 14)
    p.cubicTo(19, 19, 12, 19, 9, 19)
    s.p.drawPath(p)
    s.fuellung()
    s.zug([(3, 10), (9, 5), (9, 15)], True)


def z_wiederholen(s: Stift):
    s.p.save()
    s.p.translate(FELD, 0)
    s.p.scale(-1, 1)
    z_rueckgaengig(s)
    s.p.restore()


def z_loeschen(s: Stift):
    s.stift()
    s.linie(5, 7, 19, 7)
    s.linie(9, 7, 9, 4)
    s.linie(9, 4, 15, 4)
    s.linie(15, 4, 15, 7)
    s.zug([(6.5, 7), (7.5, 21), (16.5, 21), (17.5, 7)])
    s.stift(breite=1.3)
    s.linie(10, 10, 10.5, 18)
    s.linie(14, 10, 13.5, 18)


def z_auswahl_weg(s: Stift):
    s.stift(breite=1.5, gestrichelt=True)
    s.rechteck(4, 4, 16, 16, 2)
    s.stift(s.akzent, 2.2)
    s.linie(8, 8, 16, 16)
    s.linie(16, 8, 8, 16)


def z_suchen(s: Stift):
    s.stift()
    s.kreis(10, 10, 6)
    s.linie(14.5, 14.5, 21, 21)


def z_knoten_neu(s: Stift):
    s.fuellung()
    s.kreis(9, 14, 3.4)
    s.stift(s.akzent, 2.0)
    s.linie(15, 7, 21, 7)
    s.linie(18, 4, 18, 10)


def z_linie_neu(s: Stift):
    s.stift(breite=2.0)
    s.linie(3, 20, 15, 8)
    s.fuellung()
    s.kreis(3, 20, 2.2)
    s.kreis(15, 8, 2.2)
    s.stift(s.akzent, 2.0)
    s.linie(16, 17, 22, 17)
    s.linie(19, 14, 19, 20)


def z_flaeche_neu(s: Stift):
    s.fuellung(_mit_alpha(s.farbe, 80), s.farbe)
    s.zug([(3, 17), (8, 6), (17, 7), (12, 19)], True)
    s.stift(s.akzent, 2.0)
    s.linie(16, 17, 22, 17)
    s.linie(19, 14, 19, 20)


def z_volumen_neu(s: Stift):
    s.stift(breite=1.5)
    for teil in ([(3, 9), (12, 9), (12, 19), (3, 19)],
                 [(3, 9), (7, 5), (16, 5), (12, 9)],
                 [(12, 9), (16, 5), (16, 15), (12, 19)]):
        s.zug(teil, True)
    s.stift(s.akzent, 2.0)
    s.linie(16, 19, 22, 19)
    s.linie(19, 16, 19, 22)


def z_stab(s: Stift):
    z_staebe(s)


def z_stabzug(s: Stift):
    s.stift(breite=2.4)
    s.linie(3, 12, 21, 12)
    s.fuellung()
    for x in (3, 9, 15, 21):
        s.kreis(x, 12, 1.8)


def z_platte(s: Stift):
    s.fuellung(_mit_alpha(s.farbe, 70), s.farbe)
    s.zug([(3, 15), (9, 7), (21, 9), (15, 17)], True)
    s.stift(breite=1.0)
    s.linie(6, 11, 18, 13)
    s.linie(9, 7, 6, 15 - 3)
    s.linie(12, 8, 9.5, 16)
    s.linie(15, 8.5, 12.5, 16.5)


def z_quader(s: Stift):
    _wuerfel_umriss(s)
    s.stift(breite=1.0)
    s.linie(9, 9, 9, 20)
    s.linie(4, 14.5, 14, 14.5)


def z_werkstoff(s: Stift):
    s.stift()
    s.rechteck(4, 4, 16, 16, 2)
    s.stift(breite=1.2)
    for i in range(1, 4):
        s.linie(4, 4 + i * 4, 20, 4 + i * 4)
        s.linie(4 + i * 4, 4, 4 + i * 4, 20)


def z_querschnitt(s: Stift):
    s.fuellung()
    s.rechteck(5, 4, 14, 3.5)
    s.rechteck(5, 16.5, 14, 3.5)
    s.rechteck(10.3, 7.5, 3.4, 9)


def z_dicke(s: Stift):
    s.fuellung(_mit_alpha(s.farbe, 80), s.farbe)
    s.zug([(3, 13), (9, 6), (21, 8), (15, 15)], True)
    s.stift()
    s.linie(3, 13, 3, 17)
    s.linie(3, 17, 15, 19)
    s.linie(15, 19, 15, 15)
    s.linie(15, 19, 21, 12)


def z_lager(s: Stift):
    s.fuellung()
    s.zug([(12, 5), (19, 15), (5, 15)], True)
    s.stift()
    s.linie(3, 18, 21, 18)
    s.stift(breite=1.2)
    for x in (5, 9, 13, 17):
        s.linie(x, 18, x - 2, 21)


def z_gelenk(s: Stift):
    s.stift(breite=2.2)
    s.linie(3, 16, 10, 10)
    s.linie(14, 10, 21, 16)
    s.fuellung(QtGui.QColor("#ffffff"), s.farbe)
    s.kreis(12, 9.5, 3)


def z_kontakt(s: Stift):
    s.fuellung()
    s.rechteck(4, 4, 16, 6)
    s.stift()
    s.rechteck(4, 15, 16, 5)
    s.stift(s.akzent, 1.6)
    s.pfeil(8, 11, 8, 14, 2.2)
    s.pfeil(16, 11, 16, 14, 2.2)


def z_last(s: Stift):
    s.stift(s.akzent, 2.4)
    s.pfeil(12, 3, 12, 15, 3.6)
    s.stift()
    s.linie(4, 19, 20, 19)


def z_lastfall(s: Stift):
    z_lasten(s)
    s.text("1", 6.5, True, QtCore.QRectF(13, 15, 10, 9))


def z_kombination(s: Stift):
    s.stift(breite=1.6)
    s.rechteck(3, 5, 8, 8, 1.5)
    s.rechteck(13, 11, 8, 8, 1.5)
    s.stift(s.akzent, 1.6)
    s.linie(11, 9, 13, 15)
    s.text("+", 8, True, QtCore.QRectF(12, 1, 10, 10), s.akzent)


def z_temperatur(s: Stift):
    s.stift(breite=1.6)
    s.rechteck(9.5, 3, 5, 12, 2.5)
    s.fuellung(s.akzent)
    s.kreis(12, 18, 3.8)
    s.rechteck(11, 8, 2, 8)


def z_eigengewicht(s: Stift):
    s.text("g", 12, True)
    s.stift(s.akzent, 1.6)
    s.pfeil(19, 5, 19, 12, 2.4)


def z_vernetzen(s: Stift):
    s.stift(breite=1.4)
    s.zug([(3, 17), (9, 6), (21, 8), (15, 19)], True)
    s.linie(9, 6, 15, 19)
    s.linie(3, 17, 12, 12.5)
    s.linie(12, 12.5, 21, 8)


def z_netz_loeschen(s: Stift):
    s.stift(breite=1.2)
    for i in range(4):
        s.linie(4, 4 + i * 5.33, 20, 4 + i * 5.33)
        s.linie(4 + i * 5.33, 4, 4 + i * 5.33, 20)
    s.stift(QtGui.QColor(dsg.FARBEN["schlecht"]), 2.4)
    s.linie(6, 6, 18, 18)
    s.linie(18, 6, 6, 18)


def z_berechnen(s: Stift):
    s.fuellung(s.akzent)
    s.zug([(6, 4), (20, 12), (6, 20)], True)


def z_modal(s: Stift):
    s.stift(breite=1.8)
    p = QtGui.QPainterPath()
    p.moveTo(3, 12)
    p.cubicTo(7, 2, 10, 2, 12, 12)
    p.cubicTo(14, 22, 17, 22, 21, 12)
    s.p.drawPath(p)
    s.stift(breite=1.0, gestrichelt=True)
    s.linie(3, 12, 21, 12)


def z_knicken(s: Stift):
    s.stift(breite=2.2)
    p = QtGui.QPainterPath()
    p.moveTo(12, 21)
    p.cubicTo(5, 15, 5, 9, 12, 3)
    s.p.drawPath(p)
    s.stift(s.akzent, 2.0)
    s.pfeil(12, 0.5 + 0, 12, 3, 2.6)
    s.stift()
    s.linie(8, 21, 16, 21)


def z_theorie2(s: Stift):
    s.text("II", 11, True)


def z_farm(s: Stift):
    s.stift(breite=1.5)
    for x, y in ((4, 4), (14, 4), (4, 14), (14, 14)):
        s.rechteck(x, y, 6, 6, 1)
    s.stift(s.akzent, 1.4)
    s.linie(10, 7, 14, 7)
    s.linie(7, 10, 7, 14)
    s.linie(17, 10, 17, 14)
    s.linie(10, 17, 14, 17)


def z_nachweis(s: Stift):
    s.stift(breite=1.6)
    s.rechteck(5, 3, 14, 18, 2)
    s.stift(QtGui.QColor(dsg.FARBEN["gut"]), 2.4)
    s.zug([(8, 12), (11, 15.5), (16.5, 8.5)])


def z_ermuedung(s: Stift):
    s.stift(breite=1.8)
    p = QtGui.QPainterPath()
    p.moveTo(3, 12)
    for i in range(3):
        x = 3 + i * 6
        p.cubicTo(x + 1.5, 4, x + 4.5, 4, x + 6, 12) if i % 2 == 0 else \
            p.cubicTo(x + 1.5, 20, x + 4.5, 20, x + 6, 12)
    s.p.drawPath(p)


def z_anschluss(s: Stift):
    s.stift(breite=2.4)
    s.linie(3, 8, 12, 8)
    s.linie(12, 4, 12, 20)
    s.fuellung(s.akzent)
    for y in (7, 13):
        s.kreis(15.5, y, 1.7)


def z_beulen(s: Stift):
    s.stift(breite=1.6)
    p = QtGui.QPainterPath()
    p.moveTo(4, 18)
    p.cubicTo(8, 18, 8, 8, 12, 8)
    p.cubicTo(16, 8, 16, 18, 20, 18)
    s.p.drawPath(p)
    s.stift(s.akzent, 1.8)
    s.pfeil(2, 21, 6, 21, 2.4)
    s.pfeil(22, 21, 18, 21, 2.4)


def z_verformung(s: Stift):
    s.stift(breite=1.2, gestrichelt=True)
    s.linie(3, 8, 21, 8)
    s.stift(breite=2.0)
    p = QtGui.QPainterPath()
    p.moveTo(3, 8)
    p.cubicTo(8, 17, 16, 17, 21, 8)
    s.p.drawPath(p)


def z_woelb(s: Stift):
    z_querschnitt(s)
    s.stift(s.akzent, 1.6)
    s.pfeil(2, 6, 5, 3, 2.2)
    s.pfeil(22, 18, 19, 21, 2.2)


def z_ergebnisse(s: Stift):
    s.stift(breite=1.8)
    p = QtGui.QPainterPath()
    p.moveTo(3, 16)
    p.cubicTo(7, 4, 10, 4, 12, 12)
    p.cubicTo(14, 20, 17, 20, 21, 8)
    s.p.drawPath(p)
    s.stift(breite=1.0)
    s.linie(3, 20, 21, 20)


def z_tabelle(s: Stift):
    s.stift(breite=1.4)
    s.rechteck(3, 4, 18, 16, 1.5)
    s.linie(3, 9, 21, 9)
    s.linie(3, 14.5, 21, 14.5)
    s.linie(9, 4, 9, 20)
    s.linie(15, 4, 15, 20)


def z_bericht(s: Stift):
    s.stift(breite=1.6)
    s.zug([(6, 3), (14, 3), (19, 8), (19, 21), (6, 21)], True)
    s.stift(breite=1.3)
    for y in (11, 14, 17):
        s.linie(9, y, 16, y)


def z_bild(s: Stift):
    s.stift(breite=1.6)
    s.rechteck(3, 5, 18, 14, 1.5)
    s.fuellung(s.akzent)
    s.kreis(8, 10, 1.8)
    s.fuellung()
    s.zug([(5, 18), (11, 11), (15, 15), (18, 12), (20, 18)], True)


def z_excel(s: Stift):
    z_tabelle(s)
    s.text("X", 7, True, QtCore.QRectF(11, 11, 12, 12), s.akzent)


def z_csv(s: Stift):
    s.stift(breite=1.4)
    s.zug([(6, 3), (14, 3), (19, 8), (19, 21), (6, 21)], True)
    s.text("csv", 6, True, QtCore.QRectF(4, 10, 18, 9))


def z_zwischenablage(s: Stift):
    s.stift(breite=1.6)
    s.rechteck(5, 5, 14, 16, 2)
    s.fuellung()
    s.rechteck(9, 3, 6, 4, 1)
    s.stift(breite=1.2)
    for y in (11, 14, 17):
        s.linie(8, y, 16, y)


def z_filter(s: Stift):
    s.fuellung()
    s.zug([(3, 5), (21, 5), (14, 13), (14, 20), (10, 18), (10, 13)], True)


def z_handbuch(s: Stift):
    s.stift(breite=1.6)
    s.zug([(4, 4), (12, 6), (20, 4), (20, 19), (12, 21), (4, 19)], True)
    s.linie(12, 6, 12, 21)


def z_info(s: Stift):
    s.stift(breite=1.6)
    s.kreis(12, 12, 8.5)
    s.text("i", 11, True)


def z_update(s: Stift):
    s.stift(breite=2.0)
    p = QtGui.QPainterPath()
    p.arcMoveTo(QtCore.QRectF(5, 5, 14, 14), 60)
    p.arcTo(QtCore.QRectF(5, 5, 14, 14), 60, 270)
    s.p.drawPath(p)
    s.pfeil(17.5, 6.6, 20.5, 3.6, 3.0)
    s.stift(s.akzent, 2.0)
    s.pfeil(12, 9, 12, 15, 2.6)


def z_einstellungen(s: Stift):
    s.stift(breite=2.0)
    for i in range(8):
        a = i * math.pi / 4
        s.linie(12 + 6 * math.cos(a), 12 + 6 * math.sin(a),
                12 + 9 * math.cos(a), 12 + 9 * math.sin(a))
    s.fuellung(QtGui.QColor("#ffffff"), s.farbe)
    s.kreis(12, 12, 5)
    s.fuellung(s.farbe)
    s.kreis(12, 12, 2)


def z_handy(s: Stift):
    s.stift(breite=1.6)
    s.rechteck(7, 3, 10, 18, 2)
    s.fuellung()
    s.kreis(12, 18.5, 0.9)
    s.stift(breite=1.0)
    s.linie(10, 5, 14, 5)


def z_ks(s: Stift):
    s.stift(s.akzent, 1.8)
    s.pfeil(6, 18, 20, 18, 3.0)
    s.stift(QtGui.QColor(dsg.FARBEN["gut"]), 1.8)
    s.pfeil(6, 18, 6, 4, 3.0)
    s.stift(breite=1.8)
    s.pfeil(6, 18, 14, 10, 3.0)


def z_ebene(s: Stift):
    s.fuellung(_mit_alpha(s.farbe, 60), s.farbe)
    s.zug([(3, 16), (9, 8), (21, 10), (15, 18)], True)
    s.stift(s.akzent, 1.8)
    s.pfeil(12, 13, 12, 3, 2.8)


def z_raster(s: Stift):
    z_fang_raster(s)


def z_auswahl(s: Stift):
    s.fuellung()
    s.zug([(5, 3), (5, 18), (9, 14), (12, 21), (15, 19.5), (12, 13), (17, 13)], True)


def z_ansicht(s: Stift):
    s.stift(breite=1.6)
    p = QtGui.QPainterPath()
    p.moveTo(2, 12)
    p.cubicTo(7, 4, 17, 4, 22, 12)
    p.cubicTo(17, 20, 7, 20, 2, 12)
    s.p.drawPath(p)
    s.fuellung()
    s.kreis(12, 12, 3)


def z_farbig(s: Stift):
    for i, farbe in enumerate(("#1467c6", "#2e8b3a", "#e5701c", "#c62828")):
        s.fuellung(QtGui.QColor(farbe))
        s.rechteck(3 + i * 4.5, 6, 4, 12)


def z_symbolgroesse(s: Stift):
    s.fuellung()
    s.zug([(8, 4), (12, 10), (4, 10)], True)
    s.zug([(15, 8), (21, 18), (9, 18)], True)


def z_stern(s: Stift):
    s.fuellung(s.akzent)
    pts = []
    for i in range(10):
        r = 9 if i % 2 == 0 else 4
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((12 + r * math.cos(a), 12 + r * math.sin(a)))
    s.zug(pts, True)


def z_pfeil_rechts(s: Stift):
    s.stift(breite=2.2)
    s.pfeil(4, 12, 20, 12, 4.0)


def z_haus(s: Stift):
    s.stift(breite=1.8)
    s.zug([(3, 12), (12, 4), (21, 12)])
    s.zug([(6, 11), (6, 20), (18, 20), (18, 11)])


def z_kopfplatte(s: Stift):
    s.fuellung()
    s.rechteck(10, 3, 3, 18)
    s.stift(breite=2.4)
    s.linie(2, 12, 10, 12)
    s.fuellung(s.akzent)
    for y in (7, 17):
        s.kreis(16.5, y, 1.7)


def z_schweissnaht(s: Stift):
    s.stift(breite=2.4)
    s.linie(3, 18, 21, 18)
    s.linie(12, 18, 12, 4)
    s.fuellung(s.akzent)
    s.zug([(9, 18), (12, 14), (15, 18)], True)


def z_bruecke(s: Stift):
    s.stift(breite=1.8)
    s.linie(2, 15, 22, 15)
    p = QtGui.QPainterPath()
    p.moveTo(3, 15)
    p.cubicTo(7, 3, 17, 3, 21, 15)
    s.p.drawPath(p)
    s.stift(breite=1.2)
    for x in (7, 12, 17):
        s.linie(x, 15, x, 15 - (7 if x == 12 else 4.5))


def z_wuerfel(s: Stift):
    _wuerfel_umriss(s)
    s.text("Z", 6, True, QtCore.QRectF(9, 3, 10, 7))


def z_sicht_nur_auswahl(s: Stift):
    # Ein Auge, davor ein gefuelltes (gewaehltes) Stueck; der Rest gestrichelt
    s.stift(breite=1.2, gestrichelt=True)
    s.rechteck(3, 4, 18, 16, 1.5)
    s.fuellung(s.akzent)
    s.rechteck(8, 9, 8, 6, 1)


def z_sicht_ausblenden(s: Stift):
    s.fuellung(_mit_alpha(s.farbe, 70), s.farbe)
    s.rechteck(3, 4, 18, 16, 1.5)
    s.stift(QtGui.QColor(dsg.FARBEN["schlecht"]), 2.2)
    s.linie(7, 7, 17, 17)
    s.linie(17, 7, 7, 17)


def z_sicht_zurueck(s: Stift):
    s.stift(breite=1.2, gestrichelt=True)
    s.rechteck(3, 4, 18, 16, 1.5)
    s.stift(s.akzent, 2.2)
    p = QtGui.QPainterPath()
    p.moveTo(16, 8)
    p.cubicTo(9, 8, 8, 12, 8, 15)
    s.p.drawPath(p)
    s.pfeil(8, 11, 8, 15.5, 2.8)


def z_sicht_alles(s: Stift):
    s.stift(breite=1.6)
    p = QtGui.QPainterPath()
    p.moveTo(2, 12)
    p.cubicTo(7, 4, 17, 4, 22, 12)
    p.cubicTo(17, 20, 7, 20, 2, 12)
    s.p.drawPath(p)
    s.fuellung(s.akzent)
    s.kreis(12, 12, 3.2)


VORSCHRIFTEN = {n[2:]: f for n, f in list(globals().items())
                if n.startswith("z_") and callable(f)}

#: Beschriftung (kleingeschrieben, Teilwort) -> Symbolname. Die Reihenfolge
#: zaehlt: der erste Treffer gewinnt, darum stehen die genaueren vorn.
RATEN = [
    ("rückgängig", "rueckgaengig"), ("wiederholen", "wiederholen"),
    ("speichern unter", "speichern_unter"), ("speichern", "speichern"),
    ("öffnen", "oeffnen"), ("neu", "neu"), ("import", "import"),
    ("export", "export"), ("beispiel", "beispiel"),
    ("auswahl aufheben", "auswahl_weg"), ("nur auswahl", "sicht_nur_auswahl"),
    ("auswahl ausblenden", "sicht_ausblenden"), ("vorherige sicht", "sicht_zurueck"),
    ("alles zeigen", "sicht_alles"), ("auswahl", "auswahl"),
    ("löschen", "loeschen"), ("netz löschen", "netz_loeschen"),
    ("vernetz", "vernetzen"), ("fe-netz", "netz"), ("netz", "netz"),
    ("kontaktfuge", "kontakt"), ("kontakt", "kontakt"),
    ("volumen aus", "volumen_neu"), ("fläche aus", "flaeche_neu"),
    ("knoten", "knoten_neu"), ("linie", "linie_neu"),
    ("fläche", "flaeche_neu"), ("volumen", "volumen_neu"),
    ("stabzug", "stabzug"), ("stäbe", "staebe"), ("stab", "stab"),
    ("platte", "platte"), ("quader", "quader"),
    ("werkstoff", "werkstoff"), ("material", "werkstoff"),
    ("querschnitt", "querschnitt"), ("dicke", "dicke"),
    ("lager", "lager"), ("gelenk", "gelenk"),
    ("eigengewicht", "eigengewicht"), ("temperatur", "temperatur"),
    ("kombination", "kombination"), ("lastfall", "lastfall"), ("last", "last"),
    ("berechnen", "berechnen"), ("rechnen", "berechnen"),
    ("modal", "modal"), ("eigenform", "modal"), ("knick", "knicken"),
    ("theorie ii", "theorie2"), ("ii. ordnung", "theorie2"),
    ("farm", "farm"), ("parallel", "farm"),
    ("ermüdung", "ermuedung"), ("anschluss", "anschluss"),
    ("kopfplatte", "kopfplatte"), ("schweiß", "schweissnaht"),
    ("beul", "beulen"), ("verformung", "verformung"), ("gzg", "verformung"),
    ("wölb", "woelb"), ("nachweis", "nachweis"),
    ("ergebnis", "ergebnisse"), ("tabelle", "tabelle"),
    ("bericht", "bericht"), ("ansicht übernehmen", "bild"), ("kennwerte", "tabelle"),
    ("bild", "bild"),
    ("excel", "excel"), ("csv", "csv"), ("zwischenablage", "zwischenablage"),
    ("filter", "filter"), ("handbuch", "handbuch"), ("theoriehandbuch", "handbuch"),
    ("schnittstellen", "handbuch"), ("rechnerfarm", "farm"),
    ("info", "info"), ("update", "update"), ("einstellung", "einstellungen"),
    ("handy", "handy"), ("browser", "handy"), ("web", "handy"),
    ("koordinatensystem", "ks"), ("ks ", "ks"), ("aus auswahl", "ks"),
    ("ebene", "ebene"), ("raster", "raster"), ("fang", "fang"),
    ("isometrisch", "iso"), ("rückseite", "kehren"), ("zoom", "zoom"),
    ("draufsicht", "wuerfel"), ("ansicht)", "wuerfel"), ("seitenansicht", "wuerfel"),
    ("voll", "voll"), ("transparent", "transparent"), ("hidden", "hiddenline"),
    ("draht", "draht"), ("farbig", "farbig"), ("symbol", "symbolgroesse"),
    ("brücke", "bruecke"), ("lasteinleitung", "last"),
    ("lasten", "lasten"), ("nummer", "nummern"), ("linien", "linien"),
]

#: Alte Schriftzeichen -> Symbolname (fuer Aufrufe, die nur ein Zeichen geben)
ZEICHEN = {
    "▢": "neu", "▤": "oeffnen", "▣": "speichern", "↶": "rueckgaengig",
    "↷": "wiederholen", "▶": "berechnen", "∿": "ergebnisse", "≡": "bericht",
    "⎘": "bild", "▦": "netz", "▩": "quader", "╱": "stabzug", "▱": "flaeche_neu",
    "◲": "iso", "❓": "handbuch", "ⓘ": "info", "•": "knoten", "↓": "lasten",
    "⊹": "fang", "⤢": "zoom", "■": "voll", "◧": "transparent", "◫": "hiddenline",
}


# --------------------------------------------------------------------------
# Schnittstelle
# --------------------------------------------------------------------------
def name_fuer(text: str, zeichen: str = "") -> str:
    """Den Symbolnamen zu einer Beschriftung raten."""
    t = (text or "").strip().lower()
    for teil, name in RATEN:
        if teil in t:
            return name
    if zeichen in ZEICHEN:
        return ZEICHEN[zeichen]
    return ""


def _malen(name: str, groesse: int, farbe: QtGui.QColor,
           akzent: QtGui.QColor, text: str = "") -> QtGui.QPixmap:
    dpr = 2.0
    pm = QtGui.QPixmap(int(groesse * dpr), int(groesse * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
    p.scale(groesse / FELD, groesse / FELD)
    s = Stift(p, farbe, akzent)
    vorschrift = VORSCHRIFTEN.get(name)
    if vorschrift is not None:
        vorschrift(s)
    else:
        # Plakette mit Anfangsbuchstaben: jeder Befehl hat ein Symbol, und man
        # sieht, welchem noch eine eigene Zeichnung fehlt.
        s.fuellung(_mit_alpha(farbe, 40), farbe)
        s.kreis(12, 12, 9.5)
        s.text((text or name or "?")[:1].upper(), 11, True)
    p.end()
    return pm


def symbol(name: str, text: str = "") -> QtGui.QIcon:
    """Das Symbol zu einem Namen - in allen Groessen, dunkel und (an) weiss."""
    schluessel = (name, text[:1] if name not in VORSCHRIFTEN else "")
    ic = _ZWISCHEN.get(schluessel)
    if ic is not None:
        return ic
    dunkel = QtGui.QColor(dsg.FARBEN["text"])
    akzent = QtGui.QColor(dsg.FARBEN["akzent"])
    weiss = QtGui.QColor("#ffffff")
    hell = QtGui.QColor("#cfe3fb")
    ic = QtGui.QIcon()
    for g in GROESSEN:
        ic.addPixmap(_malen(name, g, dunkel, akzent, text), QtGui.QIcon.Normal,
                     QtGui.QIcon.Off)
        ic.addPixmap(_malen(name, g, weiss, hell, text), QtGui.QIcon.Normal,
                     QtGui.QIcon.On)
        ic.addPixmap(_malen(name, g, weiss, hell, text), QtGui.QIcon.Active,
                     QtGui.QIcon.On)
        ic.addPixmap(_malen(name, g, _mit_alpha(dunkel, 90), _mit_alpha(akzent, 90),
                            text), QtGui.QIcon.Disabled, QtGui.QIcon.Off)
    _ZWISCHEN[schluessel] = ic
    return ic


def fuer_befehl(text: str, zeichen: str = "", name: str = "") -> QtGui.QIcon:
    """Das Symbol zu einem Befehl: nach Name, sonst nach Beschriftung geraten."""
    return symbol(name or name_fuer(text, zeichen), text)


def hat_zeichnung(name: str) -> bool:
    return name in VORSCHRIFTEN


# ==========================================================================
# Programmsymbol: Fenster, Taskleiste und exe
# ==========================================================================
def programmbild(groesse: int = 256) -> QtGui.QPixmap:
    """Das Programmsymbol als Bild - ein Zweigelenkrahmen unter Last.

    Gezeichnet, nicht geladen: auf dunkelblauem Grund ein goldener Rahmen mit
    Firstpunkt, zwei gruene Gelenklager, ein orangefarbener Lastpfeil und die
    Momentenlinie des Riegels als rote Parabel. Die Formen sind grob genug,
    dass das Symbol auch mit 16 Bildpunkten in der Taskleiste noch als Rahmen
    zu erkennen ist; ab 32 Bildpunkten kommen die feinen Teile dazu.
    """
    g = int(groesse)
    pm = QtGui.QPixmap(g, g)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    r = g * 0.2
    # Grund: dunkles Blau mit Lichtkante oben links
    verlauf = QtGui.QLinearGradient(0, 0, g, g)
    verlauf.setColorAt(0.0, QtGui.QColor("#2b4d7a"))
    verlauf.setColorAt(0.55, QtGui.QColor("#1b2f4d"))
    verlauf.setColorAt(1.0, QtGui.QColor("#101c2e"))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QBrush(verlauf))
    p.drawRoundedRect(QtCore.QRectF(0, 0, g, g), r, r)
    if g >= 32:
        glanz = QtGui.QLinearGradient(0, 0, 0, g * 0.5)
        glanz.setColorAt(0.0, QtGui.QColor(255, 255, 255, 46))
        glanz.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
        p.setBrush(QtGui.QBrush(glanz))
        p.drawRoundedRect(QtCore.QRectF(g * 0.04, g * 0.04, g * 0.92, g * 0.46),
                          r * 0.8, r * 0.8)
    # Rahmen: zwei Stiele, zwei Riegelhaelften zum First
    x0, x1 = g * 0.22, g * 0.78
    yb, yt, ym = g * 0.80, g * 0.46, g * 0.30
    dick = max(1.5, g * 0.062)
    gold = QtGui.QColor("#f3c744")
    stift = QtGui.QPen(gold, dick, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap,
                       QtCore.Qt.RoundJoin)
    p.setPen(stift)
    p.setBrush(QtCore.Qt.NoBrush)
    weg = QtGui.QPainterPath(QtCore.QPointF(x0, yb))
    weg.lineTo(x0, yt)
    weg.lineTo(g * 0.5, ym)
    weg.lineTo(x1, yt)
    weg.lineTo(x1, yb)
    p.drawPath(weg)
    if g >= 32:
        # Momentenlinie des Riegels: rote Parabel unter dem Riegel
        rot = QtGui.QPen(QtGui.QColor("#e9573f"), max(1.0, g * 0.03))
        p.setPen(rot)
        p.setBrush(QtGui.QBrush(QtGui.QColor(233, 87, 63, 90)))
        mom = QtGui.QPainterPath(QtCore.QPointF(x0, yt))
        mom.quadTo(QtCore.QPointF(g * 0.5, yt + g * 0.22), QtCore.QPointF(x1, yt))
        mom.lineTo(g * 0.5, ym)
        mom.closeSubpath()
        p.drawPath(mom)
    # Lager: gruene Dreiecke unter den Stielen
    gruen = QtGui.QColor("#5fd068")
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(gruen)
    t = g * 0.085
    for x in (x0, x1):
        p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(x, yb - dick * 0.1),
                                       QtCore.QPointF(x - t, yb + 1.5 * t),
                                       QtCore.QPointF(x + t, yb + 1.5 * t)]))
    # Last: orangefarbener Pfeil auf den First
    orange = QtGui.QColor("#ff9f43")
    p.setPen(QtGui.QPen(orange, dick * 0.8, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    p.drawLine(QtCore.QPointF(g * 0.5, g * 0.06), QtCore.QPointF(g * 0.5, g * 0.19))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(orange)
    p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(g * 0.5 - t * 0.9, g * 0.17),
                                   QtCore.QPointF(g * 0.5 + t * 0.9, g * 0.17),
                                   QtCore.QPointF(g * 0.5, g * 0.26)]))
    p.end()
    return pm


def programmsymbol() -> QtGui.QIcon:
    """Das Programmsymbol als QIcon in allen gaengigen Groessen."""
    icon = QtGui.QIcon()
    for g in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(programmbild(g))
    return icon
