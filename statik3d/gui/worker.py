"""Hintergrund-Berechnung (QThread), damit die Oberflaeche bedienbar bleibt."""
from __future__ import annotations

import time
import traceback

from PySide6 import QtCore


class Abgebrochen(Exception):
    """Der Anwender hat die Rechnung angehalten.

    Geworfen aus dem Fortschritts-Rueckruf des Workers, sobald
    :meth:`SolveWorker.abbrechen` gerufen wurde - der Rechenkern haelt damit
    beim naechsten Fortschrittsaufruf an, ohne dass er selbst etwas vom
    Abbrechen wissen muss. Eine laufende Faktorisierung laeuft zu Ende (am
    Drehlager, 1 028 724 FHG, bis 13 s), erst danach greift der Abbruch.
    """


class SolveWorker(QtCore.QThread):
    """Fuehrt eine Funktion func(progress) im Hintergrund aus.

    ``progress`` nimmt den Text und - wo der Rechenkern ihn kennt - den
    Anteil (0…1). Aus dem Anteil macht die Oberflaeche einen Balken mit
    Prozentzahl; ohne ihn bleibt es beim Text im Protokoll.

    Signale: ``finished_ok(ergebnis)``, ``failed(meldung, traceback)``,
    ``abgebrochen(dauer_s)``. Nach :meth:`abbrechen` kommt genau eines der
    beiden letzten - auch wenn der Rechenkern die Ausnahme in eine eigene
    verpackt hat, entscheidet das Abbruch-Flag, nicht der Typ.
    """
    progress = QtCore.Signal(str)
    fortschritt = QtCore.Signal(str, float)
    finished_ok = QtCore.Signal(object)
    failed = QtCore.Signal(str, str)
    abgebrochen = QtCore.Signal(float)

    def __init__(self, func, parent=None):
        super().__init__(parent)
        self._func = func
        self._abbruch = False
        self._t0 = 0.0

    def abbrechen(self) -> None:
        """Anhalten anfordern; wirkt beim naechsten Fortschrittsaufruf."""
        self._abbruch = True

    @property
    def abbruch_angefordert(self) -> bool:
        return self._abbruch

    def run(self):
        self._t0 = time.time()

        def melden(text, anteil=None):
            if self._abbruch:
                raise Abgebrochen(str(text))
            self.progress.emit(str(text))
            if anteil is not None:
                self.fortschritt.emit(str(text), float(anteil))

        try:
            result = self._func(melden)
        except Abgebrochen:
            self.abgebrochen.emit(time.time() - self._t0)
            return
        except Exception as ex:   # Fehler an die GUI melden
            if self._abbruch:
                # Der Kern hat die Abbruch-Ausnahme verpackt (RuntimeError
                # aus einem Pool, ValueError aus einer Nachbearbeitung) -
                # gewollt war trotzdem der Abbruch, kein Fehler.
                self.abgebrochen.emit(time.time() - self._t0)
                return
            self.failed.emit(str(ex), traceback.format_exc())
            return
        # Kam der Abbruch erst nach dem letzten Fortschrittsaufruf, ist das
        # Ergebnis vollstaendig - dann gilt es.
        self.finished_ok.emit(result)
