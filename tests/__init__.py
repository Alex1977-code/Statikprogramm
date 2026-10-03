"""Pruefsuiten von Statik3D:  python -m tests.<suite>,  python -m tests.run_all

Beim Import wird die Ausgabe des Prozesses auf UTF-8 gestellt. Unter Windows
kodiert Python bis 3.14 eine weitergeleitete Ausgabe (Pipe, Datei, run_all)
mit der ANSI-Codeseite, hier cp1252. 26 von 53 Suiten drucken Zeichen
ausserhalb davon (Minus U+2212, Hochzahlen, Vergleichszeichen, Pfeile,
griechische Buchstaben), und ein UnicodeEncodeError riss die Pruefung, obwohl
die Rechnung stimmte (test_netzguete am 10.09.2026: 40/41 statt 40/40).

Kindprozesse (Farm, Web-Server, Prozess-Pool, run_all) bekommen PYTHONUTF8=1
mit, damit sie sich verhalten wie unter Linux, wo UTF-8 ohnehin die Vorgabe
ist. Ein laufender Interpreter laesst sich nicht mehr in den UTF-8-Modus
schalten, darum werden die eigenen Stroeme umgestellt. Nachweis:
tests/test_ausgabe.py.
"""
import os
import sys

os.environ["PYTHONUTF8"] = "1"

for _strom in (sys.stdout, sys.stderr):
    if (_strom is not None and hasattr(_strom, "reconfigure")
            and (_strom.encoding or "").replace("-", "").lower() != "utf8"):
        _strom.reconfigure(encoding="utf-8", errors="replace")

# Die Oberflaeche fragt vor Neu, Oeffnen, Beispiel, Import und Beenden nach
# Ungespeichertem (Speichern/Verwerfen/Abbrechen, 24.09.2026). Der Rauchtest
# ruft diese Befehle weit ueber hundertmal nach Aenderungen auf; eine modale
# Frage hielte jede Pruefung mit Hauptfenster an. Der Testschalter antwortet
# „verwerfen“ - wie sich die Pruefungen vorher verhielten. Die Frage selbst
# prueft tests/test_ungespeichert.py, dort ist der Schalter jeweils aus.
os.environ.setdefault("STATIK3D_UNGESPEICHERT", "verwerfen")

# Vorgemerkte Loeschungen vor os._exit nachholen (Plan-Teilpaket C15,
# 03.10.2026). Die Pruefungen enden mit os._exit, damit keine Rueckfrage stehen
# bleibt. In einer Pruefung laeuft aber keine Ereignisschleife: processEvents
# ausserhalb von exec loescht nichts, und jedes deleteLater einer geschlossenen
# Maske, eines Menues oder eines Fensters bleibt bis zum Ende vorgemerkt.
# Endet der Prozess so, stuerzt er beim Beenden ab („Windows fatal exception:
# access violation“, oft mit Exitcode 0), wenn am Sender ein Lambda haengt
# (PySide haengt dafuer eine eigene Verbindung an destroyed) oder wenn es ein
# Fenster ist, das schon zu sehen war. Gemessen mit PySide6 6.11.2: drei
# solche Widgets in reinem PySide6 6 von 6 Laeufen, eine geschlossene
# Stab-Maske im Programm 4 von 4, ui/block-c 9653460 mit test_stab_nachweis
# 12 von 12; wird vorher wirklich geloescht, 0 von 6. Darum fuehrt os._exit in
# den Pruefungen zuerst aus, was die Ereignisschleife des Programms getan
# haette - nur mit einer QApplication und im Hauptfaden, sonst ruft es gleich
# das echte os._exit. Das Programm selbst ersetzt os._exit nicht: dort laeuft
# die Schleife. Nachweis: tests/test_beenden_ohne_absturz.py.
_os_exit_echt = os._exit


def _os_exit_nach_loeschen(code=0):
    """os._exit der Pruefungen: vorgemerkte deleteLater vorher ausfuehren."""
    try:
        import threading
        qt = sys.modules.get("PySide6.QtCore")
        im_hauptfaden = threading.current_thread() is threading.main_thread()
        if qt is not None and im_hauptfaden and qt.QCoreApplication.instance() is not None:
            qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.DeferredDelete)
    except Exception:  # noqa: BLE001 - das Ende darf daran nicht scheitern
        pass
    _os_exit_echt(code)


if getattr(os._exit, "__name__", "") != _os_exit_nach_loeschen.__name__:
    os._exit = _os_exit_nach_loeschen
