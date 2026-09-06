"""Hintergrund-Berechnung (QThread), damit die Oberflaeche bedienbar bleibt."""
from __future__ import annotations

import traceback

from PySide6 import QtCore


class SolveWorker(QtCore.QThread):
    """Fuehrt eine Funktion func(progress) im Hintergrund aus.

    ``progress`` nimmt den Text und - wo der Rechenkern ihn kennt - den
    Anteil (0…1). Aus dem Anteil macht die Oberflaeche einen Balken mit
    Prozentzahl; ohne ihn bleibt es beim Text im Protokoll.
    """
    progress = QtCore.Signal(str)
    fortschritt = QtCore.Signal(str, float)
    finished_ok = QtCore.Signal(object)
    failed = QtCore.Signal(str, str)

    def __init__(self, func, parent=None):
        super().__init__(parent)
        self._func = func

    def run(self):
        def melden(text, anteil=None):
            self.progress.emit(str(text))
            if anteil is not None:
                self.fortschritt.emit(str(text), float(anteil))

        try:
            result = self._func(melden)
            self.finished_ok.emit(result)
        except Exception as ex:   # Fehler an die GUI melden
            self.failed.emit(str(ex), traceback.format_exc())
