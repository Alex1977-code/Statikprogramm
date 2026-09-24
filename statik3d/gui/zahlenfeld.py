"""
Das Zahlenfeld der Oberflaeche - Masken, Register und Dialoge (24.09.2026).

Die Regel selbst steht in :mod:`statik3d.zahlen` (ohne Qt). Hier sitzt nur,
was man sieht und bedient:

* **ungueltig** („2.000.000“): roter Rahmen, die Meldung am Feld, der
  Hauptknopf („Übernehmen“, „OK“, „Last aufbringen“) ist gesperrt; nie
  wird daraus still 0.
* **mehrdeutig** („33.000“): gelber Hinweis „33,000 – gemeint 33 000?“, bis
  bestaetigt ist - mit dem Haken im Feld, oder indem man die Eingabetaste
  bzw. den Hauptknopf ein zweites Mal drueckt. Wer 33 000 meint, schreibt
  es mit Leerzeichen.
* **gueltig**: nach dem Verlassen steht die Zahl formatiert da (Komma,
  Tausender mit Leerzeichen, nie „2e+06“).

Bis zum 24.09.2026 sassen hier der QDoubleValidator und
``float(text.replace(",", "."))`` - der Validator folgt dem Gebietsschema
des Systems und liess beim Tippen „2.000.000“ zu „2.000000“ werden, die Maske
las daraus 2,0; „33.000“ wurde still 33.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .. import zahlen as zl

ROT = "#c0392b"
GELB = "#e0a800"

#: Die zuletzt gezeigte Meldung (fuer die Pruefungen: ein Hinweis am Zeiger
#: laesst sich offscreen nicht lesen)
LETZTE_MELDUNG = [""]


class Eingabefehler(ValueError):
    """Ein Zahlenfeld enthaelt keine gueltige Zahl."""


class Zahlvalidator(QtGui.QValidator):
    """Laesst beim Tippen nur Zeichen zu, die in einer Zahl vorkommen koennen.

    Eine unfertige oder ungueltige Zahl („2.000.000“) bleibt stehen
    (Intermediate) - das Feld zeigt sie rot, statt Zeichen zu verschlucken."""

    def __init__(self, ganz: bool = False, parent=None):
        super().__init__(parent)
        self.ganz = bool(ganz)

    def validate(self, text, pos):
        if any(z not in zl.ZEICHEN for z in text):
            return QtGui.QValidator.Invalid, text, pos
        if zl.lesen(text, self.ganz).status == zl.UNGUELTIG:
            return QtGui.QValidator.Intermediate, text, pos
        return QtGui.QValidator.Acceptable, text, pos


def _haken_symbol() -> QtGui.QIcon:
    bild = QtGui.QPixmap(16, 16)
    bild.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(bild)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setPen(QtGui.QPen(QtGui.QColor("#2e7d32"), 2.2))
    p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(3, 8.5), QtCore.QPointF(6.5, 12),
                                    QtCore.QPointF(13, 4)]))
    p.end()
    return QtGui.QIcon(bild)


class Zahlenfeld(QtWidgets.QLineEdit):
    """Einzeiliges Zahlenfeld nach der Regel in :mod:`statik3d.zahlen`."""

    #: Zustand (gueltig, ungueltig, mehrdeutig, bestaetigt) hat sich geaendert
    zustand_geaendert = QtCore.Signal()

    def __init__(self, wert=0.0, breite: int = None, ganz: bool = False, parent=None):
        super().__init__(parent)
        self.ganz = bool(ganz)
        #: Text, dessen Mehrdeutigkeit bestaetigt ist bzw. schon gemeldet wurde
        self._bestaetigt = None
        self._gewarnt = None
        #: Die Eingabetaste bestaetigt selbst (zweites Druecken). In einer
        #: Maske macht das deren „Anwenden“ - dort False.
        self.selbst_bestaetigen = True
        self._klickfeld = False
        self._hinweis = ""
        self._zustand = None
        self._faktor = None             # Einheitenfaktor der Anzeige (Register)
        self._groesse = ""
        self._einheiten = None
        self.lesung = zl.Lesung(zl.LEER)
        self.setValidator(Zahlvalidator(self.ganz, self))
        self._haken = self.addAction(_haken_symbol(), QtWidgets.QLineEdit.TrailingPosition)
        self._haken.setVisible(False)
        self._haken.triggered.connect(self.bestaetigen)
        self.textChanged.connect(self._pruefen)
        self.editingFinished.connect(self._formatieren)
        self.returnPressed.connect(self._eingabetaste)
        if breite:
            self.setFixedWidth(int(breite))
        self.setzen(wert)

    # -- Werte -------------------------------------------------------------
    def setzen(self, wert) -> None:
        """Wert zeigen: Zahlen formatiert, Text so, wie er ist, None leer."""
        if wert is None:
            self.setText("")
        elif isinstance(wert, (int, float)) and not isinstance(wert, bool):
            self.setText(zl.zahl_text(int(round(wert)) if self.ganz else wert))
        else:
            # Ein Text vom Programm („1e-05“, numpy-Zahl): gilt er eindeutig,
            # steht er formatiert da - nie wissenschaftlich
            les = zl.lesen(str(wert), self.ganz)
            self.setText(zl.zahl_text(les.wert) if les.status == zl.GUELTIG else str(wert))

    def wert(self, leer=0.0) -> float:
        """Die Zahl; ein leeres Feld liefert ``leer``. Eingabefehler bei einer
        ungueltigen Eingabe - nie still 0. Eine mehrdeutige Eingabe gilt als
        Dezimalzahl; wer sie erst bestaetigen lassen will, fragt vorher
        :func:`freigeben`."""
        les = self.lesung
        if les.status == zl.LEER:
            return leer
        if les.status == zl.UNGUELTIG:
            raise Eingabefehler(les.meldung)
        return float(les.wert)

    def ungueltig(self) -> bool:
        return self.lesung.status == zl.UNGUELTIG

    def offene_frage(self) -> bool:
        """Mehrdeutig und noch nicht bestaetigt?"""
        return self.lesung.status == zl.FRAGE and self.text() != self._bestaetigt

    def bestaetigen(self) -> None:
        """Die mehrdeutige Eingabe so nehmen, wie sie dasteht (33,000)."""
        if self.lesung.status == zl.FRAGE:
            self._bestaetigt = self.text()
            self._pruefen()

    def meldung(self) -> str:
        if self.ungueltig():
            return self.lesung.meldung
        if self.offene_frage():
            return (f"{self.lesung.meldung} Gelesen wird {zl.zahl_text(self.lesung.wert)}. "
                    "Noch einmal bestätigen (Haken im Feld, Eingabetaste oder Knopf) – oder "
                    f"{zl.zahl_text(self.lesung.vorschlag)} mit Leerzeichen schreiben.")
        return ""

    # -- Einheit (Register Lager/Lasten und Kontakt) ------------------------
    def einheit_binden(self, groesse: str, quelle) -> None:
        """Die Anzeige folgt der Einheiteneinstellung: ``groesse`` ist die Art
        aus :mod:`statik3d.einheiten` (kraft, moment, strecke, flaechenlast,
        laenge), ``quelle()`` liefert die Einheiten. Der Feldwert gilt als
        SI-Wert, der bisher in SI stand."""
        si = self.wert(None)
        self._groesse, self._einheiten = str(groesse), quelle
        self._faktor = self._einheitenfaktor()
        if si is not None:
            self.setzen(si * self._faktor)

    def _einheitenfaktor(self) -> float:
        try:
            return float(self._einheiten().faktor(self._groesse))
        except Exception:                   # noqa: BLE001
            return 1.0

    def einheit(self) -> str:
        try:
            return self._einheiten().einheit(self._groesse) if self._einheiten else ""
        except Exception:                   # noqa: BLE001
            return ""

    def si(self, leer=0.0) -> float:
        """Der Wert in SI (N, m, N/m ...), aus der angezeigten Einheit."""
        v = self.wert(None)
        if v is None:
            return leer
        # auf 15 Stellen: 1,5 kN / 0,001 soll 1500 N ergeben, nicht
        # 1499,9999999999998 (der Faktor 0,001 ist binaer nicht exakt)
        return float(f"{v / (self._faktor or 1.0):.15g}")

    def si_setzen(self, wert_si: float) -> None:
        self.setzen(float(wert_si) * (self._faktor or 1.0))

    def einheiten_nachfuehren(self) -> None:
        """Nach geaenderten Einheiten dieselbe Groesse in der neuen Einheit
        zeigen (aus -10 kN werden -10 000 N)."""
        if self._einheiten is None:
            return
        neu = self._einheitenfaktor()
        if neu == self._faktor:
            return
        try:
            si = self.si(None)
        except Eingabefehler:
            self._faktor = neu
            return
        self._faktor = neu
        if si is not None:
            self.si_setzen(si)

    # -- Anzeige -----------------------------------------------------------
    def setToolTip(self, text: str) -> None:           # noqa: N802 - Qt-Name
        self._hinweis = str(text or "")
        self._stil()

    def markieren(self, an: bool) -> None:
        """Orange Rahmen, wenn ein Klick in der Ansicht dieses Feld fuellt."""
        self._klickfeld = bool(an)
        self._stil()

    def _stil(self) -> None:
        if self.ungueltig():
            stil = f"border: 2px solid {ROT}; background: #fdecea;"
        elif self.offene_frage():
            stil = f"border: 2px solid {GELB}; background: #fff6d0;"
        elif self._klickfeld:
            stil = "border: 2px solid #ff8800; background: #fff6e5;"
        else:
            stil = ""
        if self.styleSheet() != stil:
            self.setStyleSheet(stil)
        text = self.meldung() or self._hinweis
        if super().toolTip() != text:
            super().setToolTip(text)
        self._haken.setVisible(self.offene_frage())

    def _pruefen(self, *_a) -> None:
        self.lesung = zl.lesen(self.text(), self.ganz)
        if self.lesung.status != zl.FRAGE:
            self._gewarnt = None
        # auch eine neue Meldung zaehlt: aus „2.000.“ wird beim Weitertippen
        # „2.000.000“, und die Maske soll dann „2 000 000“ vorschlagen
        zustand = (self.lesung.status, self.offene_frage(), self.lesung.meldung)
        self._stil()
        if zustand != self._zustand:
            self._zustand = zustand
            self.zustand_geaendert.emit()
            self._waechter_rufen()

    def _formatieren(self) -> None:
        if self.lesung.status == zl.GUELTIG:
            text = zl.zahl_text(self.lesung.wert)
            if text != self.text():
                self.setText(text)

    def _eingabetaste(self) -> None:
        if not self.selbst_bestaetigen or not self.offene_frage():
            return
        if self._gewarnt == self.text():
            self.bestaetigen()
        else:
            self._gewarnt = self.text()
            _zeigen(self, self.meldung())

    def _waechter_rufen(self) -> None:
        w = self.parentWidget()
        while w is not None:
            for waechter in list(getattr(w, "_zahlwaechter", []) or []):
                waechter.aktualisieren()
            w = w.parentWidget()


def _zeigen(feld: QtWidgets.QWidget, text: str) -> None:
    LETZTE_MELDUNG[0] = text
    try:
        QtWidgets.QToolTip.showText(feld.mapToGlobal(QtCore.QPoint(0, feld.height())), text, feld)
    except Exception:                       # noqa: BLE001
        pass


def felder_in(bereich) -> list:
    """Die Zahlenfelder eines Bereichs (Widget) oder einer Liste."""
    if isinstance(bereich, QtWidgets.QWidget):
        liste = bereich.findChildren(Zahlenfeld)
        if isinstance(bereich, Zahlenfeld):
            liste = [bereich] + list(liste)
        return list(liste)
    return [f for f in (bereich or []) if isinstance(f, Zahlenfeld)]


def freigeben(bereich, melden=None) -> bool:
    """Vor dem Uebernehmen pruefen: True, wenn alle Zahlenfelder gelesen
    werden duerfen.

    Ungueltig: Meldung, Fokus ins Feld, False. Mehrdeutig: beim ersten Mal
    Meldung und False, beim zweiten Mal (derselbe Text) gilt es als
    bestaetigt. ``melden(text)`` zeigt die Meldung zusaetzlich (Maske,
    Statusleiste)."""
    felder = [f for f in felder_in(bereich) if f.isEnabled()]

    def sagen(feld, text):
        _zeigen(feld, text)
        if callable(melden):
            melden(text)
    for f in felder:
        if f.ungueltig():
            f.setFocus()
            sagen(f, f.meldung())
            return False
    offen = [f for f in felder if f.offene_frage()]
    for f in offen:
        if f._gewarnt == f.text():
            f.bestaetigen()
    rest = [f for f in offen if f.offene_frage()]
    if rest:
        for f in rest:
            f._gewarnt = f.text()
        rest[0].setFocus()
        sagen(rest[0], rest[0].meldung())
        return False
    return True


class Waechter(QtCore.QObject):
    """Sperrt Knoepfe, solange ein Zahlenfeld im Bereich ungueltig ist.

    ``frage_sperrt``: auch eine unbestaetigte Mehrdeutigkeit sperrt - fuer
    Dialoge, deren OK sich nicht abfangen laesst (dort bestaetigen Haken oder
    zweite Eingabetaste). Die Felder werden bei jeder Pruefung neu gesucht;
    ein Feld meldet sich bei allen Waechtern seiner Eltern."""

    def __init__(self, bereich: QtWidgets.QWidget, knoepfe: list, frage_sperrt: bool = False):
        super().__init__(bereich)
        self.bereich = bereich
        self.knoepfe = [k for k in knoepfe if k is not None]
        self.frage_sperrt = bool(frage_sperrt)
        self._gesperrt: set = set()
        liste = list(getattr(bereich, "_zahlwaechter", []) or [])
        liste.append(self)
        bereich._zahlwaechter = liste
        self.aktualisieren()

    def gesperrt(self) -> bool:
        for f in felder_in(self.bereich):
            if not f.isEnabled():
                continue
            if f.ungueltig() or (self.frage_sperrt and f.offene_frage()):
                return True
        return False

    def aktualisieren(self) -> None:
        sperre = self.gesperrt()
        for k in self.knoepfe:
            try:
                if sperre and k.isEnabled():
                    k.setEnabled(False)
                    self._gesperrt.add(id(k))
                elif not sperre and id(k) in self._gesperrt:
                    k.setEnabled(True)
                    self._gesperrt.discard(id(k))
            except RuntimeError:
                pass
