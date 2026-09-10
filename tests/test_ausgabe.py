"""
Ausgabe der Pruefungen: UTF-8, auch wenn stdout keine Konsole ist.

Unter Windows kodiert Python 3.11 eine weitergeleitete Ausgabe (Pipe, Datei,
run_all) mit der ANSI-Codeseite, hier cp1252. 26 von 53 Suiten drucken Zeichen
ausserhalb davon (Minus U+2212, Hochzahlen, Vergleichszeichen, Pfeile,
griechische Buchstaben), und ein UnicodeEncodeError riss die Pruefung, obwohl
die Rechnung stimmte. tests/__init__.py stellt die Ausgabe des Testprozesses
auf UTF-8 und gibt PYTHONUTF8=1 an Kindprozesse weiter.

Geprueft wird das am Kindprozess: er bekommt weder PYTHONUTF8 noch
PYTHONIOENCODING, seine Ausgabe geht in eine Pipe, und er muss die Zeichen
unversehrt als UTF-8 liefern. Ohne tests/__init__.py endet er unter Windows
mit UnicodeEncodeError.

Aufruf:  python -m tests.test_ausgabe
"""
import os
import subprocess
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)

PROBE = "Minus − Hochzahl ⁴ Vergleich ≤ ≥ Pfeil → Wurzel √ Umlaut äöü"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FEHLER'} {name:60s} {detail}")
    return bool(ok)


def _kind(argumente):
    """Die Suite selbst als Kindprozess, ohne UTF-8-Vorgaben aus der Umgebung."""
    umgebung = {k: v for k, v in os.environ.items()
                if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    return subprocess.run([sys.executable, "-m", "tests.test_ausgabe"] + argumente,
                          cwd=WURZEL, env=umgebung, capture_output=True)


def test_kind_druckt_utf8():
    r = _kind(["--probe"])
    fehler = r.stderr.decode("utf-8", "replace").strip().splitlines()
    check("Kindprozess endet ohne Fehler", r.returncode == 0,
          fehler[-1] if fehler else f"Exit-Code {r.returncode}")
    zeilen = r.stdout.decode("utf-8", "replace").splitlines()
    check("die Ausgabe ist UTF-8 und unversehrt", zeilen[:1] == [PROBE],
          f"{len(r.stdout)} Bytes")
    check("Kindprozesse des Kindes bekommen PYTHONUTF8=1", zeilen[1:2] == ["PYTHONUTF8=1"],
          zeilen[1] if len(zeilen) > 1 else "keine zweite Zeile")


def test_kind_stderr_utf8():
    r = _kind(["--probe-stderr"])
    check("stderr des Kindes ist UTF-8", r.stderr.decode("utf-8", "replace").strip() == PROBE,
          f"{len(r.stderr)} Bytes")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--probe" in argv:
        print(PROBE)
        print(f"PYTHONUTF8={os.environ.get('PYTHONUTF8', '-')}")
        return 0
    if "--probe-stderr" in argv:
        print(PROBE, file=sys.stderr)
        return 0
    print("=" * 92)
    print("STATIK3D - Ausgabe der Pruefungen (UTF-8 ohne Konsole)")
    print("=" * 92)
    for t in (test_kind_druckt_utf8, test_kind_stderr_utf8):
        print(f"\n--- {t.__name__} ---")
        t()
    bestanden = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 92)
    print(f"Ergebnis: {bestanden}/{len(RESULTS)} Pruefungen bestanden")
    durchgefallen = [n for n, ok in RESULTS if not ok]
    if durchgefallen:
        print(f"FEHLGESCHLAGEN: {durchgefallen}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
