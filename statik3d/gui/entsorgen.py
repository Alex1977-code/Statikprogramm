"""
Widgets loeschen, ohne dass das Programm beim Beenden abstuerzt (Plan-Teilpaket
C15, 03.10.2026).

PySide6 6.11 haengt an jeden Sender, an dessen Signal ein Lambda, eine innere
Funktion, ein functools.partial oder das ``emit`` eines anderen Signals haengt,
eine eigene Verbindung an ``destroyed`` (eine gebundene Methode bekommt keine).
Wartet ein solcher Sender bei ``os._exit`` noch auf sein ``deleteLater``, greift
PySide beim Beenden ins Leere: „Windows fatal exception: access violation“, oft
mit Exitcode 0. Liegen bleibt ein ``deleteLater`` immer dann, wenn keine
Ereignisschleife laeuft - in jeder Pruefung, denn ``processEvents`` ausserhalb
von ``exec`` loescht nichts. Gemessen am 03.10.2026 mit PySide6 6.11.2: reines
PySide6 mit drei liegengebliebenen Widgets 6 von 6 Laeufen, das Programm mit
einer einzigen geschlossenen Stab-Maske 4 von 4; wird wirklich geloescht (wie
im laufenden Programm), 0 von 6.

Darum trennt :func:`vor_dem_loeschen`, solange keine Ereignisschleife laeuft,
alle Verbindungen des Objekts und seiner Kinder auf der Seite von Qt
(``QObject.disconnect(obj, None, None, None)``). Das gibt das Lambda frei und
nimmt die Verbindung an ``destroyed`` mit; danach 0 von 8 Laeufen. Andere Wege
taugen nicht (gemessen): je Signal von Python aus trennen laesst die Verbindung
an ``destroyed`` stehen (8 von 8 stuerzten), alles ausser ``destroyed`` auf der
Seite von Qt trennen ebenso (6 von 6), und wer die Signale ueber
``metaObject()`` sucht oder PySides eigenes Objekt dafuer unter den Kindern der
Anwendung, haelt Huellen von Objekten, die Qt selbst gebaut hat - auch das
stuerzte beim Beenden.

**Im laufenden Programm wird nicht getrennt.** Dort loescht die
Ereignisschleife gleich, und an ``destroyed`` haengt auch Qts eigenes
Aufraeumen, etwa der Zwischenspeicher des Stilblatts: mit Trennen wuchs der
Speicher um rund 300 kB je geschlossener Stab-Maske (gemessen 295 und 299 kB
ueber je 300 Masken), ohne um 1 bis 3 kB; ohne Stilblatt am Fenster wuchs er
auch mit Trennen nicht.

Ein zweiter Weg zum selben Absturz betrifft Fenster (Kuerzelliste,
Rechenliste, Rueckfrage, Menue): ein Fenster, das schon zu sehen war und bei
``os._exit`` noch auf sein ``deleteLater`` wartet, stuerzt auch ganz ohne
Verbindungen ab (reines PySide6, ein geschlossener QDialog: 6 von 6). Gibt es
vorher mit ``destroy()`` seine Fensterressourcen ab, 0 von 5. Auch das tut
:func:`vor_dem_loeschen`, wenn keine Ereignisschleife laeuft.

Wer ein Widget loescht, das das Programm gebaut hat, nimmt :func:`entsorgen`
statt ``deleteLater`` (tests/test_beenden_ohne_absturz.py prueft das). Wer
etwas beim Schliessen erfahren will, haengt sich an ein eigenes Signal, das vor
dem Entsorgen kommt (etwa ``Maske.geschlossen``), nicht an ``destroyed``.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets


def _lebt(obj) -> bool:
    try:
        import shiboken6
        return obj is not None and shiboken6.isValid(obj)
    except Exception:                       # noqa: BLE001
        return obj is not None


def _ohne_ereignisschleife() -> bool:
    """Laeuft gerade keine Ereignisschleife? Dann bleibt ein ``deleteLater``
    liegen, bis eine laeuft - in einer Pruefung bis zum Ende."""
    return QtCore.QThread.currentThread().loopLevel() == 0


def signale_trennen(wurzel) -> int:
    """Alle Verbindungen trennen, deren Sender ``wurzel`` oder eines ihrer
    Kinder (ueber alle Ebenen) ist - auch die an ``destroyed``. Gibt die Zahl
    der Objekte zurueck."""
    if not _lebt(wurzel):
        return 0
    objekte = [wurzel] + list(wurzel.findChildren(QtCore.QObject))
    for o in objekte:
        QtCore.QObject.disconnect(o, None, None, None)
    return len(objekte)


def vor_dem_loeschen(obj) -> None:
    """Ein Objekt, das gleich geloescht wird, fuer ein liegenbleibendes
    ``deleteLater`` sichern: nur wenn keine Ereignisschleife laeuft, alle
    Signale trennen (:func:`signale_trennen`) und ein verborgenes Fenster seine
    Fensterressourcen abgeben lassen. Im laufenden Programm tut sie nichts."""
    if not _lebt(obj) or not _ohne_ereignisschleife():
        return
    signale_trennen(obj)
    if isinstance(obj, QtWidgets.QWidget) and obj.isWindow() and not obj.isVisible():
        try:
            obj.destroy()
        except (RuntimeError, TypeError):
            # ein Fenster, das Qt selbst gebaut hat (geschuetzte Methode):
            # es bleibt beim deleteLater allein
            pass


def entsorgen(obj) -> None:
    """:func:`vor_dem_loeschen`, dann ``deleteLater`` - der Weg fuer jedes
    Widget, das das Programm baut und wieder loescht."""
    if not _lebt(obj):
        return
    vor_dem_loeschen(obj)
    obj.deleteLater()
