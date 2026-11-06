"""Dialog „Als Bolzen nachweisen…“ (06.11.2026), offscreen, ohne Hauptfenster.

Geprueft: Auswertung der Eingaben (Pflichtangaben), der Dialog mit Vorbelegung aus
einer bestehenden Festlegung, Festlegen/Aufheben als Ergebnis, und dass der Eintrag
im Rechtsklickmenue der Volumen und die Methode mit Rueckgaengig (merken) im
Hauptfenster stehen. Der Eintrag selbst wird in der Desktop-Pruefung des
Gesamtlaufs bedient (hier nicht).

Aufruf:  python -m tests.test_bolzen_dialog
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6 import QtWidgets                                          # noqa: E402

from statik3d.gui import bolzen_dialog as BD                           # noqa: E402
from tests.test_bolzen_nachweis import kuenstlich                      # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {str(detail)[:170]}")
    return ok


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    check("lesen: 25 und Werkstoff -> 0,025 m", BD.lesen("25", "S355") == (0.025, "S355"), "")
    check("lesen: Komma „25,4“", abs(BD.lesen("25,4", "S355")[0] - 0.0254) < 1e-12, "")
    for d, w, text in (("", "S355", "Durchmesser"), ("0", "S355", "größer"), ("25", BD.KEIN_WERKSTOFF, "Werkstoff"),
                       ("25", "", "Werkstoff")):
        try:
            BD.lesen(d, w)
            check(f"lesen({d!r}, {w!r}) abgewiesen", False, "kein Fehler")
        except ValueError as ex:
            check(f"lesen({d!r}, {w!r}) abgewiesen: {text}", text in str(ex), str(ex))
    check("Scherfuge: leer -> None, „35,5“ -> 0,0355 m", BD.lesen_fuge(" ") is None and abs(BD.lesen_fuge("35,5") - 0.0355) < 1e-12, "")
    for t, grund in (("x", "keine Zahl"), ("-1", "negativ")):
        try:
            BD.lesen_fuge(t)
            check(f"Scherfuge {t!r} abgewiesen", False, "kein Fehler")
        except ValueError as ex:
            check(f"Scherfuge {t!r} abgewiesen: {grund}", grund in str(ex), str(ex))
    m, _res = kuenstlich()
    dlg = BD.BolzenDialog(m, ["Stift"])
    check("Dialog ohne Festlegung: Werkstoff steht auf „bitte wählen“, Aufheben gesperrt",
          dlg.w.currentText() == BD.KEIN_WERKSTOFF and not dlg.b_auf.isEnabled() and dlg.d.text() == "", "")
    dlg._festlegen()
    check("Festlegen ohne Angaben: kein Ergebnis, Meldung im Dialog", dlg.ergebnis is None and "Durchmesser" in dlg.fehler.text(),
          dlg.fehler.text())
    dlg.d.setText("25")
    dlg.w.setCurrentText("Stift490")
    dlg._festlegen()
    check("mit beiden Angaben: Ergebnis „festlegen“, Werte (0,025 m, Stift490)",
          dlg.ergebnis == "festlegen" and dlg.werte() == (0.025, "Stift490"), dlg.ergebnis)
    dlg.fuge.setText("x")
    dlg.ergebnis = None
    dlg._festlegen()
    check("Festlegen mit unsinniger Scherfuge: kein Ergebnis, Meldung im Dialog",
          dlg.ergebnis is None and "keine Zahl" in dlg.fehler.text(), dlg.fehler.text())
    m.koerper["Stift"].bolzen = {"d": 0.025, "werkstoff": "Stift490", "fuge": 0.035}
    dlg3 = BD.BolzenDialog(m, ["Stift"])
    check("Dialog zeigt die gespeicherte Scherfuge", dlg3.fuge.text() == "35" and abs(dlg3.scherfuge() - 0.035) < 1e-12, dlg3.fuge.text())
    m.koerper["Stift"].bolzen = {"d": 0.025, "werkstoff": "Stift490"}
    dlg2 = BD.BolzenDialog(m, ["Stift"])
    check("Dialog mit Festlegung: vorbelegt, Aufheben möglich",
          dlg2.d.text() == "25" and dlg2.w.currentText() == "Stift490" and dlg2.b_auf.isEnabled(), "")
    dlg2._aufheben()
    check("Aufheben: Ergebnis „aufheben“", dlg2.ergebnis == "aufheben", "")
    quelle = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "statik3d", "gui", "main.py"), encoding="utf-8").read()
    check("Rechtsklickmenue der Volumen: „Als Bolzen nachweisen…“",
          'art == "volumen"' in quelle and 'sub.addAction("Als Bolzen nachweisen…"' in quelle, "")
    i = quelle.index("def bolzen_festlegen(self, namen")
    rumpf = quelle[i:i + 2500]
    check("Methode merkt den Schritt (Strg+Z) und legt nur mit beiden Angaben fest",
          'self.merken("Als Bolzen nachweisen")' in rumpf and "dlg.werte()" in rumpf, "")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
