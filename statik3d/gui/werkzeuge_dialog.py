"""Dialog „Vernetzer und Nachbesserer“: gmsh, Netgen und MMG3D auf Wunsch
nachladen oder wieder entfernen (:mod:`statik3d.werkzeuge`).

Der Download laeuft im Hintergrund (SolveWorker), der Dialog zeigt Schritt
und Balken; das Ergebnis geht als Signal ``geaendert(key)`` an das
Hauptfenster, das es protokolliert und die Netzeinstellungen neu aufbaut.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .. import parallel
from .. import werkzeuge as wz
from .worker import SolveWorker


class WerkzeugeDialog(QtWidgets.QDialog):
    geaendert = QtCore.Signal(str)

    HINWEIS = ("gmsh (GPL), Netgen (LGPL), MMG3D (LGPL) und der Gleichungslöser MUMPS (CeCILL-C) kommen nicht "
               "mit Statik3D. Auf Wunsch lädt das Programm sie von ihrer Quelle in die Benutzerdaten – es gelten "
               "die Lizenzen der jeweiligen Werkzeuge; der Lizenztext von MUMPS liegt im nachgeladenen Paket "
               "unter mumps/LIZENZ. Vernetzer tetraedern Volumen (Netzeinstellungen → Vernetzer), der "
               "Nachbesserer MMG3D optimiert das fertige Tetraedernetz bei fester Hülle (Netzeinstellungen → "
               "Nachbesserung), MUMPS steht danach unter Berechnung → Einstellungen → Gleichungslöser. Ist das "
               "Kästchen unten an, lädt das Programm MUMPS beim Start ohne Rückfrage nach, wenn es fehlt.")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vernetzer, Nachbesserer und Gleichungslöser")
        self.setMinimumWidth(760)
        self.worker = None
        self.knoepfe: dict[str, QtWidgets.QPushButton] = {}
        lay = QtWidgets.QVBoxLayout(self)
        kopf = QtWidgets.QLabel(self.HINWEIS + f"\nAblage: {wz.ordner()}")
        kopf.setWordWrap(True)
        kopf.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        lay.addWidget(kopf)

        self.tabelle = QtWidgets.QTableWidget(0, 6, self)
        self.tabelle.setHorizontalHeaderLabels(["Werkzeug", "Aufgabe", "Lizenz", "Quelle", "Stand", ""])
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.tabelle.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tabelle.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        lay.addWidget(self.tabelle)

        self.lbl_schritt = QtWidgets.QLabel("")
        self.lbl_schritt.setWordWrap(True)
        lay.addWidget(self.lbl_schritt)
        self.balken = QtWidgets.QProgressBar(self)
        self.balken.setRange(0, 1000)
        self.balken.setVisible(False)
        lay.addWidget(self.balken)
        self.protokoll = QtWidgets.QPlainTextEdit(self)
        self.protokoll.setReadOnly(True)
        self.protokoll.setMaximumHeight(110)
        lay.addWidget(self.protokoll)

        self.cb_nachladen = QtWidgets.QCheckBox("MUMPS beim Programmstart nachladen, wenn es fehlt", self)
        self.cb_nachladen.setChecked(bool(parallel.settings().mumps_nachladen))
        self.cb_nachladen.setToolTip("Ohne Rückfrage, Fortschritt in der Statuszeile; ein Fehler (kein Netz) "
                                     "steht als eine Zeile im Protokoll, beim nächsten Start neuer Versuch")
        self.cb_nachladen.toggled.connect(self._nachladen_setzen)
        lay.addWidget(self.cb_nachladen)

        zeile = QtWidgets.QHBoxLayout()
        b_ordner = QtWidgets.QPushButton("Ordner öffnen")
        b_ordner.setToolTip("Den Werkzeugordner im Dateimanager zeigen")
        b_ordner.clicked.connect(self._ordner_oeffnen)
        zeile.addWidget(b_ordner)
        zeile.addStretch(1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        zeile.addWidget(bb)
        lay.addLayout(zeile)
        self._fuellen()

    # -- Tabelle -----------------------------------------------------------
    def _fuellen(self):
        st = wz.stand_alle()
        self.tabelle.setRowCount(len(wz.WERKZEUGE))
        self.knoepfe.clear()
        for i, (key, w) in enumerate(wz.WERKZEUGE.items()):
            s = st.get(key)
            if s:
                stand = f"Version {s.get('version', '?')} vom {str(s.get('datum', ''))[:10]}"
                if s.get("neustart"):
                    stand += " (wirksam nach Neustart)"
            else:
                stand = f"nicht installiert (etwa {w.groesse_mb} MB)"
            for j, text in enumerate((w.name, w.aufgabe, w.lizenz, w.quelle, stand)):
                it = QtWidgets.QTableWidgetItem(text)
                if j == 4:
                    it.setForeground(QtGui.QBrush(QtGui.QColor("#1b6e1b" if s else "#7a2e2e")))
                self.tabelle.setItem(i, j, it)
            b = QtWidgets.QPushButton("Entfernen" if s else "Installieren", self)
            b.setToolTip(f"{w.name} aus dem Werkzeugordner löschen" if s
                         else f"{w.name} von {w.quelle} laden ({w.lizenz})")
            b.clicked.connect(lambda _c=False, k=key: self.klick(k))
            self.tabelle.setCellWidget(i, 5, b)
            self.knoepfe[key] = b
        self.tabelle.resizeColumnsToContents()
        self.tabelle.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.tabelle.resizeRowsToContents()

    def _melden(self, text: str):
        self.protokoll.appendPlainText(str(text))

    def _knoepfe(self, an: bool):
        for b in self.knoepfe.values():
            b.setEnabled(an)

    def _nachladen_setzen(self, an: bool):
        parallel.configure(mumps_nachladen=bool(an))
        try:
            parallel.einstellungen_speichern()
        except OSError as ex:
            self._melden(f"Einstellung nicht gespeichert: {ex}")

    def _ordner_oeffnen(self):
        import os
        os.makedirs(wz.ordner(), exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(wz.ordner()))

    # -- Installieren / Entfernen -----------------------------------------
    def klick(self, key: str):
        if self.worker is not None and self.worker.isRunning():
            return
        if wz.stand(key):
            self.entfernen(key)
        else:
            self.installieren(key)

    def installieren(self, key: str):
        w = wz.WERKZEUGE[key]
        self._melden(f"{w.name} wird geladen: {w.quelle} ({w.lizenz}) …")
        self._knoepfe(False)
        self.balken.setValue(0)
        self.balken.setVisible(True)
        self.worker = SolveWorker(lambda progress: wz.installieren(key, fortschritt=progress))
        self.worker.progress.connect(self.lbl_schritt.setText)
        self.worker.fortschritt.connect(lambda _t, a: self.balken.setValue(int(round(1000 * a))))
        self.worker.finished_ok.connect(lambda s, k=key: self._fertig(k, s))
        self.worker.failed.connect(lambda msg, _tb, k=key: self._fehler(k, msg))
        self.worker.start()

    def _fertig(self, key: str, s: dict):
        w = wz.WERKZEUGE[key]
        self._melden(f"{w.name} {s.get('version', '?')} installiert"
                     + (" – wirksam nach dem Neustart des Programms" if s.get("neustart") else "")
                     + f" ({wz.werkzeug_ordner(key)})")
        self.lbl_schritt.setText("")
        self.balken.setVisible(False)
        self._fuellen()
        self.geaendert.emit(key)

    def _fehler(self, key: str, msg: str):
        w = wz.WERKZEUGE[key]
        self._melden(f"{w.name}: Installation fehlgeschlagen – {msg}")
        self.lbl_schritt.setText("")
        self.balken.setVisible(False)
        self._fuellen()
        QtWidgets.QMessageBox.warning(self, "Installation fehlgeschlagen", f"{w.name}: {msg}")

    def entfernen(self, key: str):
        try:
            msg = wz.entfernen(key)
        except wz.WerkzeugFehler as ex:
            msg = f"{wz.WERKZEUGE[key].name}: {ex}"
        self._melden(msg)
        self._fuellen()
        self.geaendert.emit(key)
