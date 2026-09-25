"""Fenster „Rechenhilfe“: dieser Rechner rechnet für einen Arbeitsplatz mit.

Statt ``python -m statik3d.farm worker --host ... --key ...`` auf der
Kommandozeile: ``Statik3D.exe --rechenhilfe`` (oder im Hauptfenster Extras →
Als Rechenhilfe arbeiten…) öffnet dieses Fenster. „Arbeitsplatz suchen“
lauscht auf die UDP-Ankündigung des Farm-Servers (farm.server_suchen),
„Verbinden“ prüft die Verbindung mit dem Schlüssel, lädt MUMPS nach, wenn es
fehlt (der Arbeitsplatz könnte es als Löser verlangen), und startet die
Worker als eigene Prozesse (farm.start_worker_prozesse). Der Stand
(Aufträge, Verbindung) wird alle zwei Sekunden vom Server geholt.
"""
from __future__ import annotations

import os
import sys

from PySide6 import QtCore, QtWidgets

from .. import farm, parallel
from .. import zahlen as zl
from .worker import SolveWorker


class RechenhilfeFenster(QtWidgets.QWidget):
    """Nicht-modal; steht allein (--rechenhilfe) oder neben dem Hauptfenster."""

    def __init__(self, parent=None, host: str = "", port: int = 5555, key: str = "",
                 kerne: int = 0, prozesse: bool = True, suchport: int = None):
        super().__init__(parent, QtCore.Qt.Window)
        self.setWindowTitle("Statik3D – Rechenhilfe")
        self.setMinimumWidth(560)
        self.prozesse = bool(prozesse)          # Tests: Threads statt Prozesse
        self.suchport = suchport
        self.worker = None
        self._stoppen = None
        self._namen: list = []
        self.gefunden: list = []
        lay = QtWidgets.QVBoxLayout(self)
        kopf = QtWidgets.QLabel(
            "Dieser Rechner rechnet für einen Arbeitsplatz mit. Dort: Berechnung → Einstellungen → "
            "„Rechnerfarm einschalten“. Hier: „Arbeitsplatz suchen“ (oder Adresse eintragen), gleicher "
            "Schlüssel, „Verbinden“. Beide Rechner brauchen denselben Programmstand.")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        gitter = QtWidgets.QGridLayout()
        self.cb_server = QtWidgets.QComboBox()
        self.cb_server.setEditable(True)
        self.cb_server.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.cb_server.currentIndexChanged.connect(self._server_gewaehlt)
        if host:
            self.cb_server.setEditText(host)
        self.b_suchen = QtWidgets.QPushButton("Arbeitsplatz suchen")
        self.b_suchen.clicked.connect(self.suchen)
        self.sp_port = QtWidgets.QSpinBox()
        self.sp_port.setRange(1, 65535)
        self.sp_port.setValue(int(port or 5555))
        self.ed_key = QtWidgets.QLineEdit(key or parallel.settings().farm_key)
        self.ed_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self.sp_kerne = QtWidgets.QSpinBox()
        self.sp_kerne.setRange(1, 256)
        self.sp_kerne.setValue(int(kerne or max(1, parallel.cpu_count() - 1)))
        gitter.addWidget(QtWidgets.QLabel("Arbeitsplatz (Name oder IP)"), 0, 0)
        gitter.addWidget(self.cb_server, 0, 1)
        gitter.addWidget(self.b_suchen, 0, 2)
        gitter.addWidget(QtWidgets.QLabel("Port"), 1, 0)
        gitter.addWidget(self.sp_port, 1, 1)
        gitter.addWidget(QtWidgets.QLabel("Schlüssel"), 2, 0)
        gitter.addWidget(self.ed_key, 2, 1)
        gitter.addWidget(QtWidgets.QLabel("Rechenprozesse (Kerne)"), 3, 0)
        gitter.addWidget(self.sp_kerne, 3, 1)
        lay.addLayout(gitter)
        zeile = QtWidgets.QHBoxLayout()
        self.b_verbinden = QtWidgets.QPushButton("Verbinden")
        self.b_verbinden.clicked.connect(self.verbinden)
        self.b_trennen = QtWidgets.QPushButton("Trennen")
        self.b_trennen.clicked.connect(self.trennen)
        self.b_trennen.setEnabled(False)
        zeile.addWidget(self.b_verbinden)
        zeile.addWidget(self.b_trennen)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.lbl_stand = QtWidgets.QLabel("nicht verbunden")
        self.lbl_stand.setWordWrap(True)
        lay.addWidget(self.lbl_stand)
        self.protokoll = QtWidgets.QPlainTextEdit()
        self.protokoll.setReadOnly(True)
        self.protokoll.setMinimumHeight(140)
        lay.addWidget(self.protokoll)
        self.takt = QtCore.QTimer(self)
        self.takt.setInterval(2000)
        self.takt.timeout.connect(self._stand_holen)

    # -- Hilfen ------------------------------------------------------------
    def melden(self, text: str):
        self.protokoll.appendPlainText(str(text))

    @property
    def verbunden(self) -> bool:
        return self._stoppen is not None

    def host(self) -> str:
        return self.cb_server.currentText().strip()

    def _server_gewaehlt(self, i: int):
        d = self.cb_server.itemData(i)
        if isinstance(d, dict):
            self.cb_server.setEditText(str(d["host"]))
            self.sp_port.setValue(int(d["port"]))

    # -- Suchen ------------------------------------------------------------
    def suchen(self, sekunden: float = 3.0):
        if self.worker is not None and self.worker.isRunning():
            return
        self.melden(f"Suche Arbeitsplätze im Netz ({zl.zahl_text(sekunden, punkt=True)} s) …")
        self.b_suchen.setEnabled(False)
        self.worker = SolveWorker(lambda progress: farm.server_suchen(sekunden, self.suchport))
        self.worker.finished_ok.connect(self._gefunden)
        self.worker.failed.connect(lambda msg, _tb: (self.b_suchen.setEnabled(True), self.melden(f"Suche: {msg}")))
        self.worker.start()

    def _gefunden(self, liste):
        self.b_suchen.setEnabled(True)
        self.gefunden = list(liste or [])
        if not self.gefunden:
            self.melden("Kein Arbeitsplatz gefunden - dort „Rechnerfarm einschalten“, oder Adresse eintragen "
                        "(die Ankündigung ist ein UDP-Rundruf auf Port 5556; eine Firewall kann ihn stoppen).")
            return
        self.cb_server.blockSignals(True)
        self.cb_server.clear()
        for d in self.gefunden:
            self.cb_server.addItem(f"{d['name']} ({d['host']}:{d['port']}, Stand {d['stand'] or '?'})", d)
        self.cb_server.blockSignals(False)
        self.cb_server.setCurrentIndex(0)
        self._server_gewaehlt(0)
        eigen = farm.build_sha()
        for d in self.gefunden:
            self.melden(f"gefunden: {d['name']} {d['host']}:{d['port']}, Version {d['version']}, Stand {d['stand'] or '?'}"
                        + (" - ACHTUNG: anderer Programmstand als hier" if eigen and d["stand"] and d["stand"] != eigen else ""))

    # -- Verbinden / Trennen ------------------------------------------------
    def verbinden(self):
        if self.verbunden or (self.worker is not None and self.worker.isRunning()):
            return
        host, port, key = self.host(), int(self.sp_port.value()), self.ed_key.text()
        if not host:
            self.melden("Bitte den Arbeitsplatz eintragen oder suchen.")
            return
        n = int(self.sp_kerne.value())
        self.b_verbinden.setEnabled(False)
        self.melden(f"Verbinde mit {host}:{port} …")

        def lauf(progress):
            farm._connect(host, port, key, timeout=8.0)      # Schluessel und Erreichbarkeit
            hinweise = []
            if sys.platform.startswith("win"):
                from .. import werkzeuge
                werkzeuge.aktivieren()
                try:
                    import mumps                              # noqa: F401
                except ImportError:
                    progress("MUMPS fehlt hier - wird nachgeladen (der Arbeitsplatz könnte es verlangen) …")
                    try:
                        s = werkzeuge.installieren("mumps", fortschritt=progress)
                        hinweise.append(f"MUMPS {s.get('version', '?')} nachgeladen")
                    except Exception as ex:                   # noqa: BLE001 - dann eben ohne
                        hinweise.append(f"MUMPS nicht nachgeladen: {ex}")
            return hinweise

        self.worker = SolveWorker(lauf)
        self.worker.progress.connect(self.melden)
        self.worker.finished_ok.connect(lambda hinweise: self._starten(host, port, key, n, hinweise))
        self.worker.failed.connect(self._verbindung_fehlgeschlagen)
        self.worker.start()

    def _verbindung_fehlgeschlagen(self, msg, _tb=None):
        self.b_verbinden.setEnabled(True)
        self.melden(f"Keine Verbindung: {msg}")
        self.lbl_stand.setText("nicht verbunden - Adresse, Port und Schlüssel prüfen; am Arbeitsplatz "
                               "muss die Rechnerfarm eingeschaltet und Port 5555 in der Firewall frei sein")

    def _starten(self, host, port, key, n, hinweise):
        for h in hinweise or []:
            self.melden(h)
        name = f"{__import__('platform').node()}-Rechenhilfe"
        try:
            if self.prozesse:
                self._stoppen, procs = farm.start_worker_prozesse(host, port, key, n, name)
                self._namen = [f"{name}#{i + 1}" for i in range(n)]
            else:
                stop, ths = farm.start_worker_threads(host, port, key, n, name)
                self._stoppen = stop.set
                self._namen = [f"{name}#{i + 1}" for i in range(n)]
        except Exception as ex:                               # noqa: BLE001
            return self._verbindung_fehlgeschlagen(str(ex))
        self.host_aktiv, self.port_aktiv, self.key_aktiv = host, port, key
        self.b_trennen.setEnabled(True)
        self.melden(f"Verbunden: {n} Rechenprozess{'e' if n > 1 else ''} arbeiten für {host}:{port}")
        self.lbl_stand.setText(f"verbunden mit {host}:{port} - {n} Prozesse, 0 Aufträge erledigt")
        self.takt.start()

    def _stand_holen(self):
        if not self.verbunden:
            return
        try:
            st = farm.FarmClient(self.host_aktiv, self.port_aktiv, self.key_aktiv).status()
        except Exception as ex:                               # noqa: BLE001
            self.lbl_stand.setText(f"Verbindung gestört: {ex}")
            return
        meine = {k: v for k, v in st["workers"].items() if k in self._namen}
        aktiv = sum(1 for v in meine.values() if v.get("alive"))
        erledigt = sum(int(v.get("jobs", 0)) for v in meine.values())
        self.lbl_stand.setText(f"verbunden mit {self.host_aktiv}:{self.port_aktiv} - {aktiv} von {len(self._namen)} "
                               f"Prozessen aktiv, {erledigt} Aufträge erledigt, {st['queued']} wartend")

    def trennen(self):
        self.takt.stop()
        if self._stoppen is not None:
            try:
                self._stoppen()
            except Exception as ex:                           # noqa: BLE001
                self.melden(f"Beim Trennen: {ex}")
            self._stoppen = None
        self._namen = []
        self.b_trennen.setEnabled(False)
        self.b_verbinden.setEnabled(True)
        self.lbl_stand.setText("nicht verbunden")
        self.melden("Getrennt.")

    def closeEvent(self, ev):
        self.trennen()
        super().closeEvent(ev)


def main(argv=None) -> int:
    """``Statik3D.exe --rechenhilfe [--host H] [--port P] [--key K] [--kerne N]``:
    nur das Rechenhilfe-Fenster, ohne Hauptfenster. Mit ``--host`` wird sofort
    verbunden."""
    import argparse
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--rechenhilfe", action="store_true")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--key", default="")
    ap.add_argument("--kerne", "--cores", type=int, default=0)
    a, _rest = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    try:
        from . import symbole as sym
        app.setWindowIcon(sym.programmsymbol())
    except Exception:                                         # noqa: BLE001
        pass
    parallel.einstellungen_laden()
    f = RechenhilfeFenster(None, a.host, a.port, a.key, a.kerne)
    f.show()
    if a.host:
        QtCore.QTimer.singleShot(200, f.verbinden)
    else:
        QtCore.QTimer.singleShot(200, f.suchen)
    if os.environ.get("STATIK3D_KEIN_EXEC") == "1":          # Pruefungen
        return 0
    return app.exec()
