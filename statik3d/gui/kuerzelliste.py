"""Fenster mit der Liste aller Tastenkuerzel (Extras -> Tastenkuerzel).

Die Liste wird bei jedem Oeffnen aus den Befehlen des Ribbons erzeugt
(``Ribbon.kuerzel_liste``): Befehl, Kuerzel mit den Namen der Tasten auf der
deutschen Tastatur (``sprache.kuerzel_text``) und der Ort im Ribbon. Sie wird
nicht von Hand gepflegt - ein neues Kuerzel steht beim naechsten Oeffnen
darin, und ein Kuerzel, das nicht gilt, steht nicht darin.

Dahinter steht der Abschnitt „Weitere Tasten“: Tasten ohne Befehl im Ribbon,
die ein Fenster selbst abfaengt (Modellbaum, Masken, Skizzenfenster, Esc).
Fuer sie gibt es keine Befehlsliste, aus der man sie erzeugen koennte; sie
stehen darum in ``WEITERE_TASTEN`` - ``tests/test_ribbon_ordnung.py`` drueckt
sie echt und prueft, dass sie tun, was hier steht.

Das Fenster ist **nicht modal**: das Programm bleibt bedienbar, die Liste kann
neben der Ansicht stehen bleiben. Ein Filterfeld blendet Zeilen aus (Befehl,
Kuerzel oder Ort).

Weil die Ribbon-Kuerzel Anwendungskuerzel sind (``Ribbon.kuerzel_setzen``),
haetten Esc und Strg+F im Listenfenster im Hauptfenster gewirkt: Esc haette die
Auswahl aufgehoben oder einen laufenden Vorgang abgebrochen, Strg+F den Cursor
in die Befehlssuche des Hauptfensters gesetzt. Das Fenster nimmt beide Tasten
darum selbst an (``ShortcutOverride``): Esc schliesst es, Strg+F setzt den
Cursor in sein Filterfeld (Gegenpruefung 03.10.2026).
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .sprache import kuerzel_text

#: Tasten ohne Befehl im Ribbon: (Befehl, Taste, Ort, Hinweis). Esc steht hier
#: nur als Abbruch: Esc in der rechten Maske und im Skizzenfenster tut nichts
#: Eigenes, weil das Hauptfenster die Taste als Kuerzel verbraucht (gemessen
#: 03.10.2026) - eine Taste, die nicht tut, was die Liste sagt, gehoert nicht
#: hinein. Dasselbe gilt fuer Strg+Z im Skizzenfenster.
WEITERE_TASTEN = (
    ("Eintrag löschen", "Entf, Rücktaste", "Modellbaum",
     "Der gewählte Eintrag; sind mehrere derselben Art gewählt, alle. Der Fokus muss im Baum stehen."),
    ("Eintrag bearbeiten", "Eingabetaste", "Modellbaum",
     "Öffnet die Maske des gewählten Eintrags, wie ein Doppelklick."),
    ("Erster / letzter Eintrag", "Pos1, Ende", "Modellbaum",
     "Springt zum ersten beziehungsweise zum letzten Eintrag des Baums."),
    ("Maske übernehmen", "Eingabetaste", "Maske rechts",
     "Löst den Hauptknopf der Maske aus, von jedem Feld aus; in einer Tabelle oder Liste der Maske "
     "blättert die Eingabetaste nur."),
    ("Laufenden Vorgang abbrechen", "Esc", "Programmfenster",
     "Vernetzen, Berechnung, Nachweise, Wind und Wasserdruck (Vorgänge mit Balken und Abbrechen-Knopf) "
     "und ein aufgezogenes Auswahlfenster. Steht das Klickfeld einer Maske scharf (orange), beendet Esc "
     "zuerst das Klicken. Läuft nichts, wirkt Esc wie „Alles deselektieren“."),
    ("Gewähltes Element löschen", "Entf, Rücktaste", "Skizzenfenster",
     "Das in der Skizze hervorgehobene Element."),
)


class Kuerzelliste(QtWidgets.QDialog):
    """Nicht modales Fenster: Befehl | Kürzel | Ort."""

    SPALTEN = ("Befehl", "Kürzel", "Ort")

    def __init__(self, parent=None, befehle=()):
        super().__init__(parent)
        self.setWindowTitle("Tastenkürzel")
        self.setModal(False)
        self.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)
        self.resize(560, 600)
        #: Zahl der Zeilen mit einem Befehl; dahinter folgen Trennzeile und
        #: die weiteren Tasten
        self.n_befehle = 0
        self._kopf_zeile = -1

        self.hinweis = QtWidgets.QLabel(
            "Jede Tastenfolge gehört genau einem Befehl. Sie gilt in jedem Register, solange das "
            "Programmfenster oder eines seiner nicht modalen Fenster aktiv ist; unter einem modalen "
            "Dialog (Rückfrage, Dateiauswahl) ruhen die Kürzel. Die Liste entsteht aus den Befehlen "
            "des Ribbons; darunter stehen die Tasten ohne Befehl. In diesem Fenster schließt Esc die "
            "Liste, und Strg+F setzt den Cursor ins Filterfeld.")
        self.hinweis.setWordWrap(True)

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
        lay.addWidget(self.hinweis)
        lay.addWidget(self.filter)
        lay.addWidget(self.tabelle, 1)
        lay.addLayout(unten)
        # Das Ereignis „ShortcutOverride“ geht zuerst an das Widget mit dem Fokus;
        # die beiden Felder fragen es hier ab, falls es nicht bis zum Fenster steigt
        self.filter.installEventFilter(self)
        self.tabelle.installEventFilter(self)
        self.befehle_setzen(befehle)

    def befehle_setzen(self, befehle) -> None:
        """Die Zeilen füllen: die Befehle (``Ribbon.kuerzel_liste``), dann die
        Trennzeile und ``WEITERE_TASTEN``."""
        befehle = list(befehle)
        self.n_befehle = len(befehle)
        self._kopf_zeile = self.n_befehle
        self.tabelle.clearSpans()
        self.tabelle.setRowCount(self.n_befehle + 1 + len(WEITERE_TASTEN))
        for zeile, b in enumerate(befehle):
            self._zeile(zeile, (b.text, kuerzel_text(b.aktion.shortcut()), b.ort_text()),
                        b.hinweis or b.text)
        # Trennzeile über alle drei Spalten
        kopf = QtWidgets.QTableWidgetItem("Weitere Tasten (ohne Befehl im Ribbon)")
        schrift = kopf.font()
        schrift.setBold(True)
        kopf.setFont(schrift)
        kopf.setFlags(QtCore.Qt.ItemIsEnabled)
        kopf.setToolTip("Tasten, die ein Fenster selbst abfängt: Modellbaum, Masken, Skizzenfenster, Esc. "
                        "Sie gelten im Programmfenster und in seinen nicht modalen Fenstern, "
                        "nicht unter einem modalen Dialog.")
        self.tabelle.setItem(self._kopf_zeile, 0, kopf)
        for spalte in (1, 2):
            leer = QtWidgets.QTableWidgetItem("")
            leer.setFlags(QtCore.Qt.ItemIsEnabled)
            self.tabelle.setItem(self._kopf_zeile, spalte, leer)
        self.tabelle.setSpan(self._kopf_zeile, 0, 1, len(self.SPALTEN))
        for i, (name, taste, ort, hinweis) in enumerate(WEITERE_TASTEN):
            self._zeile(self._kopf_zeile + 1 + i, (name, taste, ort), hinweis)
        self._filtern(self.filter.text())

    def _zeile(self, zeile: int, werte: tuple, hinweis: str) -> None:
        for spalte, text in enumerate(werte):
            item = QtWidgets.QTableWidgetItem(text)
            item.setToolTip(hinweis)
            self.tabelle.setItem(zeile, spalte, item)

    def _filtern(self, text: str) -> None:
        """Zeilen ausblenden, in denen der Text in keiner Spalte vorkommt
        (Groß- und Kleinschreibung gleich). Die Trennzeile bleibt, solange
        nichts gefiltert wird oder eine weitere Taste übrig ist."""
        such = (text or "").strip().lower()
        weitere_sichtbar = False
        for zeile in range(self.tabelle.rowCount()):
            if zeile == self._kopf_zeile:
                continue
            zellen = " ".join(self.tabelle.item(zeile, s).text().lower()
                              for s in range(self.tabelle.columnCount()))
            weg = bool(such) and such not in zellen
            self.tabelle.setRowHidden(zeile, weg)
            if zeile > self._kopf_zeile and not weg:
                weitere_sichtbar = True
        if self._kopf_zeile >= 0:
            self.tabelle.setRowHidden(self._kopf_zeile, bool(such) and not weitere_sichtbar)

    # -- Esc und Strg+F gehören diesem Fenster ---------------------------------
    @staticmethod
    def _gehoert_mir(ev) -> bool:
        """Esc und Strg+F: die beiden Tasten, die als Anwendungskürzel sonst im
        Hauptfenster gewirkt hätten."""
        if ev.type() != QtCore.QEvent.ShortcutOverride:
            return False
        taste, umschalter = ev.key(), ev.modifiers()
        if taste == QtCore.Qt.Key_Escape and umschalter == QtCore.Qt.NoModifier:
            return True
        return taste == QtCore.Qt.Key_F and umschalter == QtCore.Qt.ControlModifier

    def event(self, ev):
        if self._gehoert_mir(ev):
            ev.accept()          # kein Kürzel: der Tastendruck kommt als KeyPress an
            return True
        return super().event(ev)

    def eventFilter(self, obj, ev):
        if self._gehoert_mir(ev):
            ev.accept()
            return True
        return super().eventFilter(obj, ev)

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_F and ev.modifiers() == QtCore.Qt.ControlModifier:
            self.filter.setFocus(QtCore.Qt.ShortcutFocusReason)
            self.filter.selectAll()
            return
        super().keyPressEvent(ev)       # Esc: QDialog schließt das Fenster
