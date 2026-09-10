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
