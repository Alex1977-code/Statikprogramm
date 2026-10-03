"""
Widgets loeschen, ohne dass das Programm beim Beenden abstuerzt (Plan-Teilpaket
C15, 03.10.2026).

Befund: Endet ein Prozess mit ``os._exit``, waehrend ein ``deleteLater`` noch
vorgemerkt ist, stuerzt er beim Beenden ab („Windows fatal exception: access
violation“, oft mit Exitcode 0). Zwei Wege fuehren dahin, gemessen am
03.10.2026 mit PySide6 6.11.2: ein Widget, an dessen Signal ein Lambda, eine
innere Funktion, ein functools.partial oder das ``emit`` eines anderen Signals
haengt (PySide haengt dafuer eine eigene Verbindung an ``destroyed``; drei
solche Widgets in reinem PySide6: 6 von 6 Laeufen, eine geschlossene Stab-Maske
im Programm: 4 von 4), und ein Fenster, das schon zu sehen war, auch ganz ohne
Verbindungen (ein geschlossener QDialog: 6 von 6). Wird vor dem Ende wirklich
geloescht, 0 von 6.

Vorgemerkt bleibt ein ``deleteLater``, wenn danach keine Ereignisschleife mehr
laeuft: in den Pruefungen - ``processEvents`` ausserhalb von ``exec`` loescht
nichts - und nach ``app.exec()``. Im laufenden Programm loescht die Schleife
gleich. Darum holt dieses Modul vor ``os._exit`` nach, was die Schleife getan
haette: es ersetzt ``os._exit`` einmal beim Import durch eine Fassung, die
zuerst alle vorgemerkten Loeschungen ausfuehrt
(``QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)``) und dann
beendet. Das gilt fuer jedes ``deleteLater`` - auch fuer die, die Qt selbst
vormerkt (``setCellWidget`` auf eine belegte Zelle, ``removeRow`` und ``clear``
an Tabellen mit Zell-Widgets).

**Getrennt wird nichts, und kein Fenster wird nativ zerstoert.** Die erste
Fassung von C15 trennte vor dem ``deleteLater`` alle Verbindungen
(``QObject.disconnect(obj, None, None, None)``) und gab Fenster mit
``destroy()`` frei. Das kappte auch Qts eigenes Aufraeumen an ``destroyed``:
Der Speicher wuchs um rund 300 kB je geschlossener Stab-Maske (Zwischenspeicher
des Stilblatts), Empfaenger, die nach dem Schliessen noch an der Reihe waren,
bekamen das Signal nicht mehr, und die Rauchpruefung stuerzte auf dem Desktop
beim normalen Ende ab (sys.exit, 3 von 3 Laeufen).

Wer ein Widget loescht, das das Programm gebaut hat, nimmt :func:`entsorgen`
statt ``deleteLater`` - die eine Stelle dafuer (tests/test_beenden_ohne_absturz.py
prueft das).
"""
from __future__ import annotations

import os

#: das echte os._exit
_OS_EXIT = os._exit


def _lebt(obj) -> bool:
    try:
        import shiboken6
        return obj is not None and shiboken6.isValid(obj)
    except Exception:                       # noqa: BLE001
        return obj is not None


def entsorgen(obj) -> None:
    """Ein Widget oder anderes QObject loeschen, das das Programm gebaut hat:
    ``deleteLater``. Liegt es beim Ende noch, loescht :func:`vorgemerkte_loeschen`
    es vor ``os._exit``."""
    if _lebt(obj):
        obj.deleteLater()


def vorgemerkte_loeschen() -> None:
    """Alle vorgemerkten ``deleteLater`` dieses Fadens jetzt ausfuehren - das,
    was die Ereignisschleife des Programms getan haette."""
    try:
        from PySide6 import QtCore
        if QtCore.QCoreApplication.instance() is not None:
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    except Exception:                       # noqa: BLE001
        # das Ende darf daran nicht scheitern
        pass


def _exit_nach_loeschen(code=0):
    """``os._exit`` mit vorher ausgefuehrten Loeschungen (siehe Moduldoku)."""
    vorgemerkte_loeschen()
    _OS_EXIT(code)


if getattr(os._exit, "__name__", "") != _exit_nach_loeschen.__name__:
    os._exit = _exit_nach_loeschen
