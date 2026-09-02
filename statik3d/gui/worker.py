"""Hintergrund-Berechnung (QThread), damit die Oberflaeche bedienbar bleibt."""
from __future__ import annotations

import traceback

from PySide6 import QtCore


class SolveWorker(QtCore.QThread):
    """Fuehrt eine Funktion func(progress) im Hintergrund aus."""
    progress = QtCore.Signal(str)
    finished_ok = QtCore.Signal(object)
    failed = QtCore.Signal(str, str)

    def __init__(self, func, parent=None):
        super().__init__(parent)
        self._func = func

    def run(self):
        try:
            result = self._func(self.progress.emit)
            self.finished_ok.emit(result)
        except Exception as ex:   # Fehler an die GUI melden
            self.failed.emit(str(ex), traceback.format_exc())
