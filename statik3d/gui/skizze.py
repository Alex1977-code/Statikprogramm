"""Das Skizzenfenster: Linien, Kreise, Boegen, Bemassungen und Text auf einem
Blatt, mit Raster und Fang - ein rudimentaeres CAD (16.09.2026, "analog
InfoCAD"). Rechnen, Fang, Treffer und das Bild fuer den Bericht liegen in
statik3d.skizze; hier steht nur die Bedienung.

Bedienung: links klicken setzt Punkte des Werkzeugs, rechts (oder Esc)
bricht das angefangene Element ab, das Rad zoomt zum Zeiger, die mittlere
Taste schiebt das Blatt. Der Fang rastet an Enden, Mitten, Mittelpunkten
und Quadranten ein, sonst greift das Raster. Entf loescht das gewaehlte
Element, Strg+Z nimmt den letzten Schritt zurueck.
"""
from __future__ import annotations

import base64
import copy
import math

from PySide6 import QtCore, QtGui, QtWidgets

from .. import skizze as sk

#: Werkzeuge: Schluessel -> (Beschriftung, Hinweis, Zahl der Klicks)
WERKZEUGE = (
    ("auswahl", "Auswählen", "Element anklicken; Entf löscht es", 1),
    ("linie", "Linie", "Anfang und Ende klicken - die nächste Linie beginnt am Ende (rechts: Schluss)", 2),
    ("kreis", "Kreis", "Mittelpunkt, dann einen Punkt auf dem Kreis klicken", 2),
    ("bogen", "Bogen", "Anfang, Ende, dann einen Punkt auf dem Bogen klicken", 3),
    ("bemassung", "Maß", "Zwei Punkte, dann die Lage der Maßlinie klicken", 3),
    ("text", "Text", "Stelle klicken, dann den Text eingeben", 1),
)
FANGRADIUS_PX = 9.0


class Blatt(QtWidgets.QWidget):
    """Die Zeichenflaeche: zeichnet die Skizze (in Blatt-mm) und meldet Klicks."""
    geklickt = QtCore.Signal(float, float)
    bewegt = QtCore.Signal(float, float)
    abgebrochen = QtCore.Signal()

    def __init__(self, fenster: "SkizzenFenster"):
        super().__init__(fenster)
        self.fenster = fenster
        self.px_je_mm = 3.0
        self.versatz = QtCore.QPointF(24.0, 24.0)
        self.bild: QtGui.QPixmap | None = None
        self.vorschau: dict | None = None
        self.hervor = -1
        self.raster_an = True
        self.fang_an = True
        self.zeiger = None                 # (x, y, Art) des Fangs unter dem Zeiger
        self._schiebe_start = None
        self.setMouseTracking(True)
        self.setMinimumSize(480, 320)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setCursor(QtCore.Qt.CrossCursor)

    # -- Koordinaten ---------------------------------------------------------
    @property
    def skizze(self) -> dict:
        return self.fenster.skizze

    def mm_von(self, pos) -> tuple:
        return ((float(pos.x()) - self.versatz.x()) / self.px_je_mm,
                (float(pos.y()) - self.versatz.y()) / self.px_je_mm)

    def px_von(self, x: float, y: float) -> QtCore.QPointF:
        return QtCore.QPointF(self.versatz.x() + x * self.px_je_mm, self.versatz.y() + y * self.px_je_mm)

    def einrasten(self, p) -> tuple:
        """Fang vor Raster: der naechste Fangpunkt im Umkreis, sonst das Raster."""
        self.zeiger = None
        if self.fang_an:
            f = sk.fangen(self.skizze, p, FANGRADIUS_PX / self.px_je_mm)
            if f is not None:
                self.zeiger = f
                return (f[0], f[1])
        if self.raster_an:
            return sk.rastern(p, float(self.skizze.get("raster") or 0.0))
        return (float(p[0]), float(p[1]))

    def einpassen(self) -> None:
        s = self.skizze
        b, h = float(s.get("breite", 297)), float(s.get("hoehe", 210))
        if b <= 0 or h <= 0:
            return
        self.px_je_mm = max(0.2, min((self.width() - 48) / b, (self.height() - 48) / h))
        self.versatz = QtCore.QPointF((self.width() - b * self.px_je_mm) / 2,
                                      (self.height() - h * self.px_je_mm) / 2)
        self.update()

    def bild_setzen(self, png_base64: str) -> None:
        self.bild = None
        if png_base64:
            pm = QtGui.QPixmap()
            if pm.loadFromData(base64.b64decode(png_base64)):
                self.bild = pm
        self.update()

    # -- Maus ------------------------------------------------------------------
    def wheelEvent(self, ev):
        grad = ev.angleDelta().y()
        if not grad:
            return
        faktor = 1.15 ** (grad / 120.0)
        pos = ev.position()
        vor = self.mm_von(pos)
        self.px_je_mm = max(0.1, min(60.0, self.px_je_mm * faktor))
        # der Punkt unter dem Zeiger bleibt liegen
        self.versatz = QtCore.QPointF(float(pos.x()) - vor[0] * self.px_je_mm,
                                      float(pos.y()) - vor[1] * self.px_je_mm)
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            x, y = self.einrasten(self.mm_von(ev.position()))
            self.geklickt.emit(x, y)
        elif ev.button() == QtCore.Qt.MiddleButton:
            self._schiebe_start = (ev.position(), QtCore.QPointF(self.versatz))
        elif ev.button() == QtCore.Qt.RightButton:
            self.abgebrochen.emit()
        self.setFocus()

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.MiddleButton:
            self._schiebe_start = None

    def mouseMoveEvent(self, ev):
        if self._schiebe_start is not None:
            start, versatz = self._schiebe_start
            d = ev.position() - start
            self.versatz = QtCore.QPointF(versatz.x() + d.x(), versatz.y() + d.y())
            self.update()
            return
        x, y = self.einrasten(self.mm_von(ev.position()))
        self.bewegt.emit(x, y)
        self.update()

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_Escape:
            self.abgebrochen.emit()
        elif ev.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            self.fenster.loeschen()
        else:
            super().keyPressEvent(ev)

    # -- Zeichnen ----------------------------------------------------------------
    def paintEvent(self, _ev):
        s = self.skizze
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QtGui.QColor("#e9ecef"))
        b, h = float(s.get("breite", 297)), float(s.get("hoehe", 210))
        p.save()
        p.translate(self.versatz)
        p.scale(self.px_je_mm, self.px_je_mm)
        p.fillRect(QtCore.QRectF(0, 0, b, h), QtGui.QColor("#ffffff"))
        if self.bild is not None and s.get("bild"):
            r = s["bild"]
            p.drawPixmap(QtCore.QRectF(float(r.get("x", 0)), float(r.get("y", 0)),
                                       float(r.get("breite", b)), float(r.get("hoehe", h))),
                         self.bild, QtCore.QRectF(self.bild.rect()))
        raster = float(s.get("raster") or 0.0)
        if self.raster_an and raster > 0 and raster * self.px_je_mm >= 4:
            stift = QtGui.QPen(QtGui.QColor("#dfe3e8"))
            stift.setWidthF(0.0)
            stift.setCosmetic(True)
            p.setPen(stift)
            x = 0.0
            while x <= b + 1e-9:
                p.drawLine(QtCore.QPointF(x, 0), QtCore.QPointF(x, h))
                x += raster
            y = 0.0
            while y <= h + 1e-9:
                p.drawLine(QtCore.QPointF(0, y), QtCore.QPointF(b, y))
                y += raster
        rahmen = QtGui.QPen(QtGui.QColor("#9aa0a6"))
        rahmen.setWidthF(0.0)
        rahmen.setCosmetic(True)
        p.setPen(rahmen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRect(QtCore.QRectF(0, 0, b, h))
        for i, el in enumerate(s.get("elemente", [])):
            self._element(p, el, hervor=(i == self.hervor))
        if self.vorschau is not None:
            self._element(p, self.vorschau, vorschau=True)
        if self.zeiger is not None:
            x, y, _art = self.zeiger
            stift = QtGui.QPen(QtGui.QColor("#1e88e5"))
            stift.setWidthF(0.0)
            stift.setCosmetic(True)
            p.setPen(stift)
            r = 4.0 / self.px_je_mm
            p.drawRect(QtCore.QRectF(x - r, y - r, 2 * r, 2 * r))
        p.restore()
        p.end()

    def _element(self, p: QtGui.QPainter, el: dict, hervor: bool = False, vorschau: bool = False) -> None:
        art = el.get("art")
        farbe = QtGui.QColor("#ff8800" if hervor else ("#1e88e5" if vorschau else "#1a1a1a"))
        stift = QtGui.QPen(farbe)
        stift.setWidthF(sk.STRICH.get(art, 0.35) * (2.0 if hervor else 1.0))
        stift.setCapStyle(QtCore.Qt.RoundCap)
        if vorschau:
            stift.setStyle(QtCore.Qt.DashLine)
        p.setPen(stift)
        p.setBrush(QtCore.Qt.NoBrush)
        if art == "linie":
            p.drawLine(QtCore.QPointF(*el["p1"]), QtCore.QPointF(*el["p2"]))
        elif art == "kreis":
            m, r = el["mitte"], float(el["r"])
            p.drawEllipse(QtCore.QPointF(*m), r, r)
        elif art == "bogen":
            m, r = el["mitte"], float(el["r"])
            rect = QtCore.QRectF(float(m[0]) - r, float(m[1]) - r, 2 * r, 2 * r)
            spanne = sk.bogen_spanne(el["von"], el["bis"])
            p.drawArc(rect, int(round(float(el["von"]) * 16)), int(round(spanne * 16)))
        elif art == "bemassung":
            self._bemassung(p, el, farbe)
        elif art == "text":
            self._text(p, float(el["p"][0]), float(el["p"][1]), str(el.get("text", "")),
                       float(el.get("groesse", 3.5)), float(el.get("winkel", 0.0)), farbe)

    def _text(self, p, x, y, text, groesse, winkel, farbe, mitte=False) -> None:
        p.save()
        p.translate(x, y)
        if winkel:
            p.rotate(-winkel)
        p.scale(groesse / 10.0, groesse / 10.0)
        f = QtGui.QFont("Arial")
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QtGui.QPen(farbe))
        if mitte:
            w = QtGui.QFontMetricsF(f).horizontalAdvance(text)
            p.drawText(QtCore.QPointF(-w / 2, 0), text)
        else:
            p.drawText(QtCore.QPointF(0, 0), text)
        p.restore()

    def _bemassung(self, p, el, farbe) -> None:
        d1, d2, n = sk.bemassungslinie(el)
        p1, p2 = el["p1"], el["p2"]
        a = float(el.get("abstand", 8.0))
        s = 1.0 if a >= 0 else -1.0
        for q, d in ((p1, d1), (p2, d2)):
            e = (d[0] + n[0] * sk.UEBERSTAND * s, d[1] + n[1] * sk.UEBERSTAND * s)
            p.drawLine(QtCore.QPointF(*q), QtCore.QPointF(*e))
        p.drawLine(QtCore.QPointF(*d1), QtCore.QPointF(*d2))
        L = sk.abstand(d1, d2)
        grad = 0.0
        if L > 1e-9:
            rx, ry = (d2[0] - d1[0]) / L, (d2[1] - d1[1]) / L
            p.setBrush(QtGui.QBrush(farbe))
            for spitze, rich in ((d1, (rx, ry)), (d2, (-rx, -ry))):
                bx = sk.PFEIL * 0.18
                pts = [QtCore.QPointF(spitze[0], spitze[1]),
                       QtCore.QPointF(spitze[0] + rich[0] * sk.PFEIL - rich[1] * bx,
                                      spitze[1] + rich[1] * sk.PFEIL + rich[0] * bx),
                       QtCore.QPointF(spitze[0] + rich[0] * sk.PFEIL + rich[1] * bx,
                                      spitze[1] + rich[1] * sk.PFEIL - rich[0] * bx)]
                p.drawPolygon(QtGui.QPolygonF(pts))
            p.setBrush(QtCore.Qt.NoBrush)
            grad = -math.degrees(math.atan2(-ry, rx))
            if grad > 90.0 or grad <= -90.0:
                grad += 180.0
        mx, my = (d1[0] + d2[0]) / 2 + n[0] * 1.2 * s, (d1[1] + d2[1]) / 2 + n[1] * 1.2 * s
        self._text(p, mx, my, sk.bemassung_text(el, self.skizze), sk.MASSSCHRIFT, -grad, farbe, mitte=True)


class SkizzenFenster(QtWidgets.QDialog):
    """Fenster zum Zeichnen einer Skizze (Unterlage art "skizze")."""
    angewendet = QtCore.Signal(dict)

    def __init__(self, fenster, unterlage=None, ansicht_png=None):
        super().__init__(fenster)
        self.fenster = fenster
        self.ansicht_png = ansicht_png
        self.setWindowTitle("Skizze")
        self.setModal(False)
        self.resize(1000, 700)
        u = unterlage
        self.name_alt = getattr(u, "name", "") if u is not None else ""
        self.skizze = sk.pruefen(copy.deepcopy(getattr(u, "skizze", None) or {}))
        self.daten = getattr(u, "daten", "") if u is not None else ""
        self.werkzeug = "linie"
        self.punkte: list = []
        self._undo: list = []
        self._aufbau(u)
        self.blatt.bild_setzen(self.daten)
        QtCore.QTimer.singleShot(0, self.blatt.einpassen)

    # -- Aufbau -----------------------------------------------------------------
    def _aufbau(self, u) -> None:
        lay = QtWidgets.QVBoxLayout(self)
        leiste = QtWidgets.QToolBar()
        leiste.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self.akt_werkzeug: dict = {}
        gruppe = QtGui.QActionGroup(self)
        gruppe.setExclusive(True)
        for schl, text, hinweis, _n in WERKZEUGE:
            a = QtGui.QAction(text, self)
            a.setCheckable(True)
            a.setToolTip(hinweis)
            a.triggered.connect(lambda _c=False, s=schl: self.werkzeug_setzen(s))
            gruppe.addAction(a)
            leiste.addAction(a)
            self.akt_werkzeug[schl] = a
        self.akt_werkzeug[self.werkzeug].setChecked(True)
        leiste.addSeparator()
        a = leiste.addAction("Löschen", self.loeschen)
        a.setToolTip("Das gewählte Element löschen (Entf)")
        a = leiste.addAction("Zurück", self.rueckgaengig)
        a.setToolTip("Den letzten Schritt zurücknehmen (Strg+Z)")
        leiste.addSeparator()
        self.akt_raster = leiste.addAction("Raster")
        self.akt_raster.setCheckable(True)
        self.akt_raster.setChecked(True)
        self.akt_raster.setToolTip("Punkte auf das Raster runden (Schritt rechts)")
        self.akt_raster.toggled.connect(self._raster_umschalten)
        self.akt_fang = leiste.addAction("Fang")
        self.akt_fang.setCheckable(True)
        self.akt_fang.setChecked(True)
        self.akt_fang.setToolTip("An Enden, Mitten, Mittelpunkten und Quadranten einrasten")
        self.akt_fang.toggled.connect(self._fang_umschalten)
        leiste.addSeparator()
        a = leiste.addAction("Ansicht", self.ansicht_uebernehmen)
        a.setToolTip("Die 3D-Ansicht, wie sie gerade steht, als Bild hinter die Skizze legen")
        a.setEnabled(callable(self.ansicht_png))
        a = leiste.addAction("Bild…", self.bild_laden)
        a.setToolTip("Ein Bild (PNG, JPG) hinter die Skizze legen")
        a = leiste.addAction("Ohne Bild", self.bild_entfernen)
        a.setToolTip("Das Hintergrundbild entfernen")
        a = leiste.addAction("Einpassen", lambda: self.blatt.einpassen())
        a.setToolTip("Das ganze Blatt ins Fenster")
        lay.addWidget(leiste)

        form = QtWidgets.QHBoxLayout()
        self.ed_name = QtWidgets.QLineEdit(self.name_alt or "")
        self.ed_name.setPlaceholderText("Name der Skizze")
        self.ed_name.setMinimumWidth(140)
        form.addWidget(QtWidgets.QLabel("Name"))
        form.addWidget(self.ed_name)
        form.addWidget(QtWidgets.QLabel("Maßstab 1 mm ="))
        self.sp_massstab = QtWidgets.QDoubleSpinBox()
        self.sp_massstab.setRange(0.001, 100000.0)
        self.sp_massstab.setDecimals(3)
        self.sp_massstab.setValue(float(self.skizze.get("massstab", 1.0)))
        self.sp_massstab.setSuffix(" mm")
        self.sp_massstab.setToolTip("Was ein Millimeter auf dem Blatt am Bauteil ist - die Maßzahlen rechnen damit")
        self.sp_massstab.valueChanged.connect(self._kopf_geaendert)
        form.addWidget(self.sp_massstab)
        form.addWidget(QtWidgets.QLabel("Maße in"))
        self.cb_einheit = QtWidgets.QComboBox()
        self.cb_einheit.addItems(list(sk.EINHEITEN))
        self.cb_einheit.setCurrentText(self.skizze.get("einheit", "mm"))
        self.cb_einheit.currentTextChanged.connect(self._kopf_geaendert)
        form.addWidget(self.cb_einheit)
        form.addWidget(QtWidgets.QLabel("Blatt"))
        self.sp_breite = QtWidgets.QDoubleSpinBox()
        self.sp_breite.setRange(20, 5000)
        self.sp_breite.setDecimals(0)
        self.sp_breite.setValue(float(self.skizze.get("breite", 297)))
        self.sp_breite.setSuffix(" mm")
        self.sp_breite.valueChanged.connect(self._kopf_geaendert)
        form.addWidget(self.sp_breite)
        form.addWidget(QtWidgets.QLabel("×"))
        self.sp_hoehe = QtWidgets.QDoubleSpinBox()
        self.sp_hoehe.setRange(20, 5000)
        self.sp_hoehe.setDecimals(0)
        self.sp_hoehe.setValue(float(self.skizze.get("hoehe", 210)))
        self.sp_hoehe.setSuffix(" mm")
        self.sp_hoehe.valueChanged.connect(self._kopf_geaendert)
        form.addWidget(self.sp_hoehe)
        form.addWidget(QtWidgets.QLabel("Raster"))
        self.sp_raster = QtWidgets.QDoubleSpinBox()
        self.sp_raster.setRange(0, 100)
        self.sp_raster.setDecimals(1)
        self.sp_raster.setValue(float(self.skizze.get("raster", 5.0)))
        self.sp_raster.setSuffix(" mm")
        self.sp_raster.valueChanged.connect(self._kopf_geaendert)
        form.addWidget(self.sp_raster)
        form.addStretch(1)
        lay.addLayout(form)

        self.blatt = Blatt(self)
        self.blatt.geklickt.connect(self._klick)
        self.blatt.bewegt.connect(self._bewegt)
        self.blatt.abgebrochen.connect(self.abbrechen)
        lay.addWidget(self.blatt, 1)

        unten = QtWidgets.QHBoxLayout()
        self.ed_beschriftung = QtWidgets.QLineEdit(getattr(u, "beschriftung", "") if u is not None else "")
        self.ed_beschriftung.setPlaceholderText("Bildunterschrift im Bericht")
        unten.addWidget(QtWidgets.QLabel("Beschriftung"))
        unten.addWidget(self.ed_beschriftung, 1)
        self.lbl_status = QtWidgets.QLabel("")
        unten.addWidget(self.lbl_status, 1)
        for text, fn in (("Übernehmen", self.uebernehmen), ("OK", self.ok), ("Schließen", self.close)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(fn)
            unten.addWidget(b)
        lay.addLayout(unten)
        self._hinweis()

    # -- Zustand -------------------------------------------------------------------
    def keyPressEvent(self, ev):
        """Strg+Z nimmt den letzten Schritt zurueck, Esc bricht das Element ab
        (und schliesst nicht den Dialog). Ohne QAction-Kuerzel: das gaelte
        sonst als Kuerzel des Hauptfensters (Oberflaechenpruefung)."""
        if ev.matches(QtGui.QKeySequence.Undo):
            self.rueckgaengig()
            return
        if ev.key() == QtCore.Qt.Key_Escape:
            self.abbrechen()
            return
        super().keyPressEvent(ev)

    def werkzeug_setzen(self, schl: str) -> None:
        self.werkzeug = schl
        self.punkte = []
        self.blatt.vorschau = None
        if schl != "auswahl":
            self.blatt.hervor = -1
        self.akt_werkzeug[schl].setChecked(True)
        self._hinweis()
        self.blatt.update()

    def _hinweis(self, zusatz: str = "") -> None:
        for schl, text, hinweis, _n in WERKZEUGE:
            if schl == self.werkzeug:
                self.lbl_status.setText(f"{text}: {hinweis}" + (f"   {zusatz}" if zusatz else ""))
                return

    def _kopf_geaendert(self, *_a) -> None:
        s = self.skizze
        s["massstab"] = float(self.sp_massstab.value())
        s["einheit"] = self.cb_einheit.currentText()
        s["breite"] = float(self.sp_breite.value())
        s["hoehe"] = float(self.sp_hoehe.value())
        s["raster"] = float(self.sp_raster.value())
        self.blatt.update()

    def _raster_umschalten(self, an: bool) -> None:
        self.blatt.raster_an = bool(an)
        self.blatt.update()

    def _fang_umschalten(self, an: bool) -> None:
        self.blatt.fang_an = bool(an)
        self.blatt.update()

    def _merken(self) -> None:
        self._undo.append(copy.deepcopy(self.skizze["elemente"]))
        del self._undo[:-50]

    def rueckgaengig(self) -> None:
        if not self._undo:
            return
        self.skizze["elemente"] = self._undo.pop()
        self.punkte = []
        self.blatt.vorschau = None
        self.blatt.hervor = -1
        self.blatt.update()

    def abbrechen(self) -> None:
        """Rechtsklick oder Esc: das angefangene Element verwerfen."""
        self.punkte = []
        self.blatt.vorschau = None
        if self.werkzeug == "auswahl":
            self.blatt.hervor = -1
        self._hinweis()
        self.blatt.update()

    def loeschen(self) -> None:
        i = self.blatt.hervor
        if 0 <= i < len(self.skizze["elemente"]):
            self._merken()
            del self.skizze["elemente"][i]
            self.blatt.hervor = -1
            self.blatt.update()

    def element_anfuegen(self, el: dict) -> None:
        """Ein fertiges Element in die Skizze (auch von aussen, fuer Pruefungen)."""
        self._merken()
        self.skizze["elemente"].append(el)
        self.blatt.update()

    # -- Werkzeuge -----------------------------------------------------------------
    def _klick(self, x: float, y: float) -> None:
        p = (float(x), float(y))
        w = self.werkzeug
        if w == "auswahl":
            self.blatt.hervor = sk.element_bei(self.skizze, p, 6.0 / self.blatt.px_je_mm)
            self._hinweis("gewählt" if self.blatt.hervor >= 0 else "nichts getroffen")
            self.blatt.update()
            return
        if w == "text":
            text, ok = QtWidgets.QInputDialog.getText(self, "Text", "Text:")
            if ok and text.strip():
                self.element_anfuegen({"art": "text", "p": [p[0], p[1]], "text": text.strip(), "groesse": 3.5})
            return
        self.punkte.append(p)
        if w == "linie" and len(self.punkte) == 2:
            a, b = self.punkte
            if sk.abstand(a, b) > 1e-9:
                self.element_anfuegen({"art": "linie", "p1": [a[0], a[1]], "p2": [b[0], b[1]]})
            self.punkte = [b]                       # die naechste Linie haengt an
        elif w == "kreis" and len(self.punkte) == 2:
            m, q = self.punkte
            r = sk.abstand(m, q)
            if r > 1e-9:
                self.element_anfuegen({"art": "kreis", "mitte": [m[0], m[1]], "r": r})
            self.punkte = []
        elif w == "bogen" and len(self.punkte) == 3:
            b = sk.bogen_durch_drei_punkte(*self.punkte)
            if b is not None:
                m, r, von, bis = b
                self.element_anfuegen({"art": "bogen", "mitte": [m[0], m[1]], "r": r, "von": von, "bis": bis})
            self.punkte = []
        elif w == "bemassung" and len(self.punkte) == 3:
            a, b, c = self.punkte
            el = {"art": "bemassung", "p1": [a[0], a[1]], "p2": [b[0], b[1]],
                  "abstand": self._massabstand(a, b, c), "text": ""}
            if sk.abstand(a, b) > 1e-9:
                self.element_anfuegen(el)
            self.punkte = []
        self.blatt.vorschau = None
        self._hinweis(f"{len(self.punkte)} Punkt(e) gesetzt" if self.punkte else "")
        self.blatt.update()

    @staticmethod
    def _massabstand(a, b, c) -> float:
        """Vorzeichenbehafteter Abstand des Klicks c von der Strecke a-b (links positiv)."""
        L = sk.abstand(a, b)
        if L < 1e-12:
            return 8.0
        nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L
        return (c[0] - a[0]) * nx + (c[1] - a[1]) * ny

    def _bewegt(self, x: float, y: float) -> None:
        p = (float(x), float(y))
        s = self.skizze
        vor = None
        w = self.werkzeug
        if w == "linie" and len(self.punkte) == 1:
            a = self.punkte[0]
            vor = {"art": "linie", "p1": [a[0], a[1]], "p2": [p[0], p[1]]}
            L = sk.abstand(a, p) * float(s.get("massstab", 1.0))
            self._hinweis(f"Länge {sk.masstext(L, s.get('einheit', 'mm'))} {s.get('einheit', 'mm')}")
        elif w == "kreis" and len(self.punkte) == 1:
            m = self.punkte[0]
            vor = {"art": "kreis", "mitte": [m[0], m[1]], "r": sk.abstand(m, p)}
        elif w == "bogen" and len(self.punkte) == 1:
            a = self.punkte[0]
            vor = {"art": "linie", "p1": [a[0], a[1]], "p2": [p[0], p[1]]}
        elif w == "bogen" and len(self.punkte) == 2:
            b = sk.bogen_durch_drei_punkte(self.punkte[0], self.punkte[1], p)
            if b is not None:
                m, r, von, bis = b
                vor = {"art": "bogen", "mitte": [m[0], m[1]], "r": r, "von": von, "bis": bis}
        elif w == "bemassung" and len(self.punkte) == 1:
            a = self.punkte[0]
            vor = {"art": "linie", "p1": [a[0], a[1]], "p2": [p[0], p[1]]}
        elif w == "bemassung" and len(self.punkte) == 2:
            a, b = self.punkte
            vor = {"art": "bemassung", "p1": [a[0], a[1]], "p2": [b[0], b[1]],
                   "abstand": self._massabstand(a, b, p), "text": ""}
        self.blatt.vorschau = vor
        z = self.blatt.zeiger
        self.lbl_status.setToolTip("")
        fang = f"  Fang: {z[2]}" if z else ""
        if vor is None:
            self._hinweis(f"x = {p[0]:.1f}  y = {p[1]:.1f} mm{fang}".replace(".", ","))

    # -- Bild -------------------------------------------------------------------------
    def _bild_einpassen(self, breite_px: int, hoehe_px: int) -> None:
        """Das Blatt bekommt das Seitenverhaeltnis des Bildes, das Bild fuellt es."""
        if breite_px <= 0 or hoehe_px <= 0:
            return
        b = float(self.skizze.get("breite", 297))
        h = round(b * hoehe_px / breite_px)
        self.sp_hoehe.setValue(h)
        self.skizze["hoehe"] = float(h)
        self.skizze["bild"] = {"x": 0.0, "y": 0.0, "breite": b, "hoehe": float(h)}

    def ansicht_uebernehmen(self) -> None:
        if not callable(self.ansicht_png):
            return
        png = self.ansicht_png()
        if not png:
            return
        self.bild_setzen_png(png)

    def bild_setzen_png(self, png_base64: str) -> None:
        pm = QtGui.QPixmap()
        if not pm.loadFromData(base64.b64decode(png_base64)):
            QtWidgets.QMessageBox.warning(self, "Bild", "Das Bild lässt sich nicht lesen.")
            return
        self.daten = png_base64
        self._bild_einpassen(pm.width(), pm.height())
        self.blatt.bild_setzen(png_base64)
        self.blatt.einpassen()

    def bild_laden(self) -> None:
        pfad, _f = QtWidgets.QFileDialog.getOpenFileName(self, "Bild hinter die Skizze", "",
                                                         "Bilder (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not pfad:
            return
        bild = QtGui.QImage(pfad)
        if bild.isNull():
            QtWidgets.QMessageBox.warning(self, "Bild", "Das Bild lässt sich nicht lesen.")
            return
        puffer = QtCore.QBuffer()
        puffer.open(QtCore.QIODevice.WriteOnly)
        bild.save(puffer, "PNG")
        self.bild_setzen_png(base64.b64encode(bytes(puffer.data())).decode("ascii"))

    def bild_entfernen(self) -> None:
        self.daten = ""
        self.skizze["bild"] = None
        self.blatt.bild_setzen("")

    # -- Ergebnis ---------------------------------------------------------------------
    def werte(self) -> dict:
        self._kopf_geaendert()
        return {"name": self.ed_name.text().strip() or self.name_alt or "Skizze",
                "name_alt": self.name_alt, "skizze": copy.deepcopy(self.skizze),
                "daten": self.daten, "beschriftung": self.ed_beschriftung.text().strip()}

    def uebernehmen(self) -> None:
        d = self.werte()
        self.angewendet.emit(d)
        self.name_alt = d["name"]

    def ok(self) -> None:
        self.uebernehmen()
        self.accept()
