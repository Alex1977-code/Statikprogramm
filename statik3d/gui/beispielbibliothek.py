"""Dialog „Beispielbibliothek“ (seit 09.11.2026).

Links die Beispiele nach Stabwerk, Flächentragwerk und Volumen (eigene
Dateien mit ihrer Gruppe), rechts Beschreibung und Parametertabelle mit Wert,
Einheit und Grenzen. „Übernehmen“ prüft die Werte und schließt den Dialog;
das Hauptfenster baut das Modell danach mit der üblichen Rückfrage, wenn etwas
ungespeichert ist. Ein Wert außerhalb der Grenzen sperrt „Übernehmen“ und
steht rot mit Grund unter der Tabelle; nie wird still begrenzt.
"""
from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

from .. import beispiele as bib
from .. import zahlen as zl

ROT = "#c0392b"


def _zahl(x) -> str:
    if x is None or x in (float("inf"), float("-inf")):
        return ""
    return zl.zahl_text(float(x), tausender=False)


class BeispielDialog(QtWidgets.QDialog):
    """Nach exec() ``ergebnis`` = (Beispiel, Werte) oder None."""

    def __init__(self, parent=None, ordner: str | None = None):
        super().__init__(parent)
        self.setObjectName("beispielbibliothek")
        self.setWindowTitle("Beispielbibliothek")
        self.resize(900, 560)
        self.ergebnis = None
        self.ordner = ordner or bib.benutzerordner()
        self.beispiele, self.dateifehler = bib.alle(self.ordner)
        self._aktuell = None

        lay = QtWidgets.QVBoxLayout(self)
        teil = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.baum = QtWidgets.QTreeWidget()
        self.baum.setHeaderHidden(True)
        self.baum.setMinimumWidth(230)
        teil.addWidget(self.baum)

        rechts = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(rechts)
        rl.setContentsMargins(6, 0, 0, 0)
        self.titel = QtWidgets.QLabel("")
        f = self.titel.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.2)
        self.titel.setFont(f)
        rl.addWidget(self.titel)
        self.text = QtWidgets.QLabel("")
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        rl.addWidget(self.text)
        self.tabelle = QtWidgets.QTableWidget(0, 5)
        self.tabelle.setHorizontalHeaderLabels(["Parameter", "Wert", "Einheit", "von", "bis"])
        self.tabelle.verticalHeader().setVisible(False)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        for i in range(1, 5):
            kopf.setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeToContents)
        self.tabelle.itemChanged.connect(self._geaendert)
        rl.addWidget(self.tabelle, 1)
        self.fehler = QtWidgets.QLabel("")
        self.fehler.setWordWrap(True)
        self.fehler.setStyleSheet(f"color: {ROT}")
        rl.addWidget(self.fehler)
        teil.addWidget(rechts)
        teil.setStretchFactor(1, 1)
        lay.addWidget(teil, 1)

        hinweis = QtWidgets.QLabel(
            f"Eigene Beispiele: Python-Dateien im Ordner {self.ordner}. Das Programm führt diese Dateien "
            "beim Öffnen der Bibliothek aus – legen Sie dort nur eigene Dateien ab. Aufbau siehe "
            "Benutzerhandbuch, Abschnitt Beispielbibliothek.")
        hinweis.setWordWrap(True)
        hinweis.setObjectName("bibliothekhinweis")
        lay.addWidget(hinweis)
        self.dateifehler_text = QtWidgets.QLabel("")
        self.dateifehler_text.setWordWrap(True)
        self.dateifehler_text.setStyleSheet(f"color: {ROT}")
        if self.dateifehler:
            self.dateifehler_text.setText(
                "Nicht geladen: " + "; ".join(f"{os.path.basename(p)} – {g}" for p, g in self.dateifehler))
        self.dateifehler_text.setVisible(bool(self.dateifehler))
        lay.addWidget(self.dateifehler_text)

        knoepfe = QtWidgets.QHBoxLayout()
        self.b_ordner = QtWidgets.QPushButton("Ordner öffnen")
        self.b_ordner.setToolTip("Den Ordner für eigene Beispiele im Explorer öffnen (er wird angelegt, "
                                 "wenn es ihn noch nicht gibt)")
        self.b_ordner.clicked.connect(self._ordner_oeffnen)
        knoepfe.addWidget(self.b_ordner)
        self.b_vorgabe = QtWidgets.QPushButton("Vorgabewerte")
        self.b_vorgabe.setToolTip("Die Werte des gewählten Beispiels auf die Vorgabe zurücksetzen")
        self.b_vorgabe.clicked.connect(self._vorgaben)
        knoepfe.addWidget(self.b_vorgabe)
        knoepfe.addStretch(1)
        self.b_ok = QtWidgets.QPushButton("Übernehmen")
        self.b_ok.setDefault(True)
        self.b_ok.setToolTip("Das Beispiel mit diesen Werten als neues Modell aufbauen (ersetzt das offene "
                             "Modell; ist etwas ungespeichert, fragt das Programm vorher)")
        self.b_ok.clicked.connect(self._uebernehmen)
        b_ab = QtWidgets.QPushButton("Schließen")
        b_ab.clicked.connect(self.reject)
        knoepfe.addWidget(self.b_ok)
        knoepfe.addWidget(b_ab)
        lay.addLayout(knoepfe)

        self._baum_fuellen()
        self.baum.currentItemChanged.connect(lambda cur, _alt: self._zeigen(cur))
        erstes = self._eintraege[0] if self._eintraege else None
        if erstes is not None:
            self.baum.setCurrentItem(erstes)

    # ------------------------------------------------------------------
    def _baum_fuellen(self):
        self._eintraege = []
        gruppen = list(bib.GRUPPEN) + sorted({b.gruppe for b in self.beispiele} - set(bib.GRUPPEN))
        for g in gruppen:
            liste = [b for b in self.beispiele if b.gruppe == g]
            if not liste:
                continue
            knoten = QtWidgets.QTreeWidgetItem(self.baum, [g])
            knoten.setFlags(knoten.flags() & ~QtCore.Qt.ItemIsSelectable)
            for b in liste:
                it = QtWidgets.QTreeWidgetItem(knoten, [b.titel + ("  (eigene Datei)" if b.eigen else "")])
                it.setData(0, QtCore.Qt.UserRole, b)
                if b.eigen:
                    it.setToolTip(0, b.datei)
                self._eintraege.append(it)
            knoten.setExpanded(True)

    def beispiel_waehlen(self, schluessel: str) -> bool:
        """Ein Beispiel nach Schluessel waehlen (auch fuer die Pruefungen)."""
        for it in self._eintraege:
            if it.data(0, QtCore.Qt.UserRole).schluessel == schluessel:
                self.baum.setCurrentItem(it)
                return True
        return False

    def _zeigen(self, it):
        b = it.data(0, QtCore.Qt.UserRole) if it is not None else None
        if b is None:
            return
        self._aktuell = b
        self.titel.setText(b.titel)
        self.text.setText(b.beschreibung + (f"\n\nDatei: {b.datei}" if b.eigen else ""))
        self.tabelle.blockSignals(True)
        self.tabelle.setRowCount(len(b.parameter))
        for r, p in enumerate(b.parameter):
            zellen = [p.titel, _zahl(p.wert), p.einheit, _zahl(p.min), _zahl(p.max)]
            for c, t in enumerate(zellen):
                z = QtWidgets.QTableWidgetItem(t)
                if c != 1:
                    z.setFlags(z.flags() & ~QtCore.Qt.ItemIsEditable)
                else:
                    z.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                    z.setToolTip(f"{p.titel}: {_zahl(p.min)} bis {_zahl(p.max)} {p.einheit}".strip())
                self.tabelle.setItem(r, c, z)
        self.tabelle.blockSignals(False)
        self._geaendert()

    def _vorgaben(self):
        if self._aktuell is not None:
            it = self.baum.currentItem()
            self._zeigen(it)

    def wert_setzen(self, name: str, text: str):
        """Einen Wert wie von Hand eintragen (fuer die Pruefungen)."""
        b = self._aktuell
        for r, p in enumerate(b.parameter):
            if p.name == name:
                self.tabelle.item(r, 1).setText(text)
                return
        raise KeyError(name)

    def werte(self) -> dict:
        """Die eingetragenen Werte, geprueft; ValueError mit allen Gruenden."""
        b = self._aktuell
        if b is None:
            raise ValueError("kein Beispiel gewählt")
        roh, fehler = {}, []
        for r, p in enumerate(b.parameter):
            t = self.tabelle.item(r, 1).text() if self.tabelle.item(r, 1) else ""
            les = zl.lesen(t, p.ganzzahl)
            if les.status != zl.GUELTIG:
                fehler.append(f"{p.titel}: „{t}“ ist keine gültige Zahl")
                continue
            roh[p.name] = les.wert
        if fehler:
            raise ValueError("; ".join(fehler))
        return b.werte_pruefen(roh)

    def _geaendert(self, *_):
        b = self._aktuell
        if b is None:
            return
        try:
            self.werte()
            self.fehler.setText("")
            ok = True
        except ValueError as ex:
            self.fehler.setText(str(ex))
            ok = False
        self.b_ok.setEnabled(ok)
        # die Zeile mit dem falschen Wert rot hinterlegen
        self.tabelle.blockSignals(True)
        for r, p in enumerate(b.parameter):
            z = self.tabelle.item(r, 1)
            if z is None:
                continue
            les = zl.lesen(z.text(), p.ganzzahl)
            gut = les.status == zl.GUELTIG
            if gut:
                try:
                    p.pruefen(les.wert)
                except ValueError:
                    gut = False
            z.setBackground(QtGui.QBrush() if gut else QtGui.QColor(255, 220, 215))
        self.tabelle.blockSignals(False)

    def _uebernehmen(self):
        try:
            w = self.werte()
        except ValueError as ex:
            self.fehler.setText(str(ex))
            return
        self.ergebnis = (self._aktuell, w)
        self.accept()

    def _ordner_oeffnen(self):
        try:
            os.makedirs(self.ordner, exist_ok=True)
        except OSError as ex:
            self.fehler.setText(f"Ordner nicht anlegbar: {ex}")
            return
        if os.environ.get("STATIK3D_KEIN_BROWSER"):
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self.ordner))
