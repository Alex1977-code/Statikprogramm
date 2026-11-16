"""
Doku ohne Steuerzeichen (Abschluss Runde k10e).

Befund: Im Doku-Commit 84c962d3 standen im Benutzerhandbuch an 43 Stellen
die Steuerzeichen U+0001 und U+0002 statt Zahl und Einheit („Summe der
Auflagerkräfte ␁ ␂ statt ␁ ␂ N“). Ursache war das Hilfsskript, das die
Absätze umbrach: Seine Ersetzung zum Schutz von „Zahl Einheit“ vor dem
Zeilenumbruch enthielt statt der Rückverweise auf die Gruppen 1 und 2 die
Bytes 0x01 und 0x02, so dass re.sub die letzte Ziffer und die Einheit durch
Steuerzeichen ersetzte. Die Prüfläufe der Rechnung bemerken so etwas nicht.

Diese Prüfung liest jede Markdown-Datei unter Versionskontrolle und
verlangt, dass kein Steuerzeichen außer Tabulator, Zeilenvorschub und
Wagenrücklauf darin steht. Dazu prüft sie an den damals beschädigten
Stellen den richtigen Wortlaut (Leerraum vereinheitlicht, weil die Absätze
umbrochen sind) und die beiden Nachträge in den Release-Notes vom 16.11.

Aufruf:  python -m tests.test_doku_steuerzeichen_k10e
"""
import os
import subprocess
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = []

ERLAUBT = {"\t", "\n", "\r"}
STEUER = {chr(c) for c in range(32)} - ERLAUBT | {chr(127)}


def check(name, ok, info=""):
    RESULTS.append((name, bool(ok)))
    print(f"[{'OK' if ok else 'FEHLER'}] {name}" + (f"  ({info})" if info else ""))


def _md_dateien():
    try:
        aus = subprocess.run(["git", "-C", WURZEL, "ls-files", "*.md"], capture_output=True,
                             text=True, check=True).stdout.split("\n")
        dateien = [d for d in aus if d.strip()]
    except Exception:                    # noqa: BLE001 - ohne git: Ordner docs durchsuchen
        dateien = []
    if not dateien:
        for wurzel, _, namen in os.walk(os.path.join(WURZEL, "docs")):
            for n in namen:
                if n.endswith(".md"):
                    dateien.append(os.path.relpath(os.path.join(wurzel, n), WURZEL))
    return sorted(dateien)


def _lesen(rel):
    with open(os.path.join(WURZEL, rel), "rb") as f:
        return f.read().decode("utf-8")


def _eben(t):
    return " ".join(t.split())


def test_keine_steuerzeichen():
    dateien = _md_dateien()
    check("Markdown-Dateien gefunden", len(dateien) >= 20, f"{len(dateien)} Dateien")
    check("Benutzerhandbuch dabei", "docs/Benutzerhandbuch.md" in dateien)
    for rel in dateien:
        t = _lesen(rel)
        stellen = [(i, ord(ch)) for i, ch in enumerate(t) if ch in STEUER]
        info = ""
        if stellen:
            i, c = stellen[0]
            zeile = t.count("\n", 0, i) + 1
            info = f"{len(stellen)} Steuerzeichen, erstes U+{c:04X} in Zeile {zeile}"
        check(f"{rel} ohne Steuerzeichen", not stellen, info)


# Richtiger Wortlaut an den Stellen, die 84c962d3 beschädigt hatte
HANDBUCH = [
    "Summe der Auflagerkräfte 1 000 statt 6 000 N",
    "Kragarm 3 m mit 1 kN: 0 statt 0,5357 mm und Summe der Auflagerkräfte 0 statt 1 000 N",
    "Eigenfrequenz von 441 statt 21,7 Hz",
    "Feder von 10 000 N/m",
    "mindestens in 10 Teile",
    "IPE 300, 6 m, 300 kN Druck, Endmomente 6 kNm",
    "54,21 statt 54,29 kNm",
    "in zwei Elementen 52,33 kNm",
    "200 kN",
    "15,00 statt 16,66 kNm",
    "21,7 % zu hoch",
    "mindestens 10 Teile, nach Theorie III. Ordnung in mindestens 20 Teile",
    "0 statt 11,47 kNm",
    "bis rund 28 N/mm²",
    "unter 0,1 % der Last",
    "Kragarm 10 m mit 0,1 N",
    "(0,02 m oder 0,005 m)",
    "(7,7 %)",
    "bis 2 % daneben",
    "höchstens 0,001 N bzw. 0,001 Nm",
    "M_Ed 60,0 statt 63,2 kNm",
    "10 000-mal so steif",
    "100 000 000-mal so steif",
    "um höchstens 0,002 %",
    "Scheinformen mit 0 Hz",
    "mindestens 1 000 000 000 000 000 N/m",
    "höchstens 0,000003 mm",
    "(bis 4 000)",
    "(bis 3 000)",
    "um mehr als 1 %",
    "Über 60 000 Freiheitsgraden",
]


def test_handbuch_wortlaut():
    t = _eben(_lesen("docs/Benutzerhandbuch.md"))
    for s in HANDBUCH:
        check(f"Handbuch enthält „{s}“", _eben(s) in t)


def test_release_notes_1611():
    t = _eben(_lesen("docs/RELEASE-NOTES-2026-11-16.md"))
    check("Scheibe 413,96 als nur auf einem Weg gemessen gekennzeichnet",
          "413,96 statt 414,55 (nur auf einem Weg gemessen)" in t)
    check("Stand 78: Kombinationen mit α_cr „auto“ neu zu rechnen",
          "sowie Kombinationen mit α_cr „auto“, deren Hinweise einen Fehler des "
          "Eigenwertlösers nennen" in t)


def main():
    for t in (test_keine_steuerzeichen, test_handbuch_wortlaut, test_release_notes_1611):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
