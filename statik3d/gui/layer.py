"""Die Layerliste: ein Fenster mit allen Layern (16.09.2026).

Layer sind benannte Objektgruppen - in RFEM die Objektselektionen. Hier wird
je Layer angehakt, ob er im Bild ist (sichtbar) und ob er gesperrt ist
(nicht waehlbar, nicht aenderbar). Jede Aenderung wirkt sofort; das Fenster
ist nicht modal und bleibt neben der Ansicht stehen.

Die Arbeit selbst tut das Hauptfenster (layer_sichtbar_setzen,
layer_gesperrt_setzen, layer_aus_auswahl, ...): so gilt fuer Ribbon,
Modellbaum und dieses Fenster derselbe Weg.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class LayerFenster(QtWidgets.QDialog):
    SPALTEN = ("Layer", "sichtbar", "gesperrt", "Inhalt", "Herkunft")

    def __init__(self, fenster):
        super().__init__(fenster)
        self.fenster = fenster
        self.setWindowTitle("Layerliste")
        self.setModal(False)
        self.setMinimumSize(620, 380)
        lay = QtWidgets.QVBoxLayout(self)
        hinweis = QtWidgets.QLabel(
            "Haken bei „sichtbar“ blendet den Layer ein oder aus, „gesperrt“ macht seine "
            "Objekte unwählbar und unveränderbar. Ein Objekt darf in mehreren Layern liegen; "
            "ausgeblendet oder gesperrt ist es, sobald einer seiner Layer es ist. "
            "Der Name lässt sich in der Tabelle ändern (Doppelklick).")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        self.tabelle = QtWidgets.QTableWidget(0, len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.itemChanged.connect(self._geaendert)
        lay.addWidget(self.tabelle)
        knoepfe = QtWidgets.QGridLayout()
        self.knoepfe: dict = {}
        befehle = (
            ("Neu aus Auswahl", self._neu, "Die Auswahl in der Ansicht als neuen Layer anlegen"),
            ("Auswahl hinzufügen", self._hinzufuegen, "Die Auswahl in den markierten Layer aufnehmen"),
            ("Auswahl herausnehmen", self._herausnehmen, "Die Auswahl aus dem markierten Layer nehmen"),
            ("Objekte wählen", self._waehlen, "Die Objekte des markierten Layers in der Ansicht auswählen"),
            ("Nur diesen zeigen", self._nur, "Alles andere ausblenden"),
            ("Alle zeigen", self._alle, "Alle Layer sichtbar"),
            ("Löschen", self._loeschen, "Den markierten Layer löschen - die Objekte bleiben"),
            ("Schließen", self.close, ""),
        )
        for i, (text, fn, tip) in enumerate(befehle):
            b = QtWidgets.QPushButton(text)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, f=fn: f())
            knoepfe.addWidget(b, i // 4, i % 4)
            self.knoepfe[text] = b
        lay.addLayout(knoepfe)
        self._still = False
        self.fuellen()

    # -- Inhalt ------------------------------------------------------------
    def fuellen(self, markieren: str = "") -> None:
        """Die Tabelle aus dem Modell neu aufbauen; ``markieren`` bleibt gewaehlt."""
        m = self.fenster.model
        aktuell = markieren or self.gewaehlt()
        self._still = True
        try:
            t = self.tabelle
            t.setRowCount(0)
            zeilen = sorted((getattr(m, "layer", None) or {}).items(), key=lambda kv: kv[0].lower())
            for zeile, (name, L) in enumerate(zeilen):
                t.insertRow(zeile)
                it = QtWidgets.QTableWidgetItem(name)
                it.setData(QtCore.Qt.UserRole, name)
                t.setItem(zeile, 0, it)
                for spalte, an in ((1, L.sichtbar), (2, L.gesperrt)):
                    h = QtWidgets.QTableWidgetItem("")
                    h.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled
                               | QtCore.Qt.ItemIsSelectable)
                    h.setCheckState(QtCore.Qt.Checked if an else QtCore.Qt.Unchecked)
                    t.setItem(zeile, spalte, h)
                for spalte, text in ((3, L.bezug()),
                                     (4, "RFEM-Objektselektion" if L.quelle == "rfem" else (L.kommentar or ""))):
                    x = QtWidgets.QTableWidgetItem(text)
                    x.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                    t.setItem(zeile, spalte, x)
                if name == aktuell:
                    t.selectRow(zeile)
            t.resizeColumnsToContents()
        finally:
            self._still = False
        self.knoepfe["Objekte wählen"].setEnabled(bool(m.layer))
        self.knoepfe["Nur diesen zeigen"].setEnabled(bool(m.layer))
        self.knoepfe["Löschen"].setEnabled(bool(m.layer))

    def gewaehlt(self) -> str:
        """Der Name des markierten Layers - oder leer."""
        z = self.tabelle.currentRow()
        it = self.tabelle.item(z, 0) if z >= 0 else None
        return str(it.data(QtCore.Qt.UserRole) or "") if it is not None else ""

    def zeile_von(self, name: str) -> int:
        for z in range(self.tabelle.rowCount()):
            it = self.tabelle.item(z, 0)
            if it is not None and str(it.data(QtCore.Qt.UserRole) or "") == name:
                return z
        return -1

    # -- Aenderungen in der Tabelle --------------------------------------
    def _geaendert(self, item) -> None:
        if self._still:
            return
        it0 = self.tabelle.item(item.row(), 0)
        name = str(it0.data(QtCore.Qt.UserRole) or "") if it0 is not None else ""
        if not name:
            return
        if item.column() == 1:
            self.fenster.layer_sichtbar_setzen(name, item.checkState() == QtCore.Qt.Checked)
        elif item.column() == 2:
            self.fenster.layer_gesperrt_setzen(name, item.checkState() == QtCore.Qt.Checked)
        elif item.column() == 0:
            neu = item.text().strip()
            if neu and neu != name:
                ok = self.fenster.layer_umbenennen(name, neu)
                self.fuellen(neu if ok else name)
            else:
                self.fuellen(name)

    # -- Knoepfe -------------------------------------------------------------
    def _mit_layer(self, fn) -> None:
        name = self.gewaehlt()
        if not name:
            self.fenster.info("Zuerst einen Layer in der Liste markieren")
            return
        fn(name)

    def _neu(self) -> None:
        self.fenster.layer_aus_auswahl()

    def _hinzufuegen(self) -> None:
        self._mit_layer(self.fenster.layer_auswahl_hinzufuegen)

    def _herausnehmen(self) -> None:
        self._mit_layer(self.fenster.layer_auswahl_entfernen)

    def _waehlen(self) -> None:
        self._mit_layer(self.fenster.layer_objekte_waehlen)

    def _nur(self) -> None:
        self._mit_layer(self.fenster.layer_nur_zeigen)

    def _alle(self) -> None:
        self.fenster.layer_alle_zeigen()

    def _loeschen(self) -> None:
        self._mit_layer(self.fenster.layer_loeschen)
