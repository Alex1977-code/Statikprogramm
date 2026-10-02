"""Fenster mit der Liste aller Tastenkuerzel (Extras -> Tastenkuerzel).

Die Liste wird bei jedem Oeffnen aus den Befehlen des Ribbons erzeugt
(``Ribbon.kuerzel_liste``): Befehl, Kuerzel mit den Namen der Tasten auf der
deutschen Tastatur (``sprache.kuerzel_text``) und der Ort im Ribbon. Sie wird
nicht von Hand gepflegt - ein neues Kuerzel steht beim naechsten Oeffnen
darin, und ein Kuerzel, das nicht gilt, steht nicht darin.

Das Fenster ist **nicht modal**: das Programm bleibt bedienbar, die Liste kann
neben der Ansicht stehen bleiben. Ein Filterfeld blendet Zeilen aus (Befehl,
Kuerzel oder Ort).
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .sprache import kuerzel_text


class Kuerzelliste(QtWidgets.QDialog):
    """Nicht modales Fenster: Befehl | Kürzel | Ort."""

    SPALTEN = ("Befehl", "Kürzel", "Ort")

    def __init__(self, parent=None, befehle=()):
        super().__init__(parent)
        self.setWindowTitle("Tastenkürzel")
        self.setModal(False)
        self.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)
        self.resize(560, 560)

        hinweis = QtWidgets.QLabel(
            "Jede Tastenfolge gehört genau einem Befehl und gilt in jedem Register, "
            "solange das Programmfenster aktiv ist. Die Liste entsteht aus den Befehlen "
            "des Ribbons.")
        hinweis.setWordWrap(True)

        self.filter = QtWidgets.QLineEdit(self)
        self.filter.setPlaceholderText("Filter: Befehl, Kürzel oder Ort …")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._filtern)

        self.tabelle = QtWidgets.QTableWidget(0, len(self.SPALTEN), self)
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        kopf.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        kopf.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)

        self.btn_zu = QtWidgets.QPushButton("Schließen")
        self.btn_zu.clicked.connect(self.close)
        unten = QtWidgets.QHBoxLayout()
        unten.addStretch(1)
        unten.addWidget(self.btn_zu)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(hinweis)
        lay.addWidget(self.filter)
        lay.addWidget(self.tabelle, 1)
        lay.addLayout(unten)
        self.befehle_setzen(befehle)

    def befehle_setzen(self, befehle) -> None:
        """Die Zeilen aus den Befehlen (``Ribbon.kuerzel_liste``) füllen."""
        befehle = list(befehle)
        self.tabelle.setRowCount(len(befehle))
        for zeile, b in enumerate(befehle):
            werte = (b.text, kuerzel_text(b.aktion.shortcut()), f"{b.register} › {b.gruppe}")
            for spalte, text in enumerate(werte):
                self.tabelle.setItem(zeile, spalte, QtWidgets.QTableWidgetItem(text))
        self._filtern(self.filter.text())

    def _filtern(self, text: str) -> None:
        """Zeilen ausblenden, in denen der Text in keiner Spalte vorkommt
        (Groß- und Kleinschreibung gleich)."""
        such = (text or "").strip().lower()
        for zeile in range(self.tabelle.rowCount()):
            zellen = " ".join(self.tabelle.item(zeile, s).text().lower()
                              for s in range(self.tabelle.columnCount()))
            self.tabelle.setRowHidden(zeile, bool(such) and such not in zellen)
