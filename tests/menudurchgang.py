"""Menuedurchgang: jeden Befehl des Menuebands an einem Modell ausloesen.

    python -m tests.menudurchgang MODELL.json [--ab NR] [--waechter SEK]

Kein Teil von run_all - ein Werkzeug fuer die Pruefsitzung am echten Modell.
Dialoge werden global auf "Abbrechen" gesetzt, Rueckfragen verneint; je
Befehl stehen Dauer, Meldungen (info/error), neue Protokollzeilen und ein
etwaiger Traceback in <MODELL>_menudurchgang.jsonl - Zeile fuer Zeile, damit
ein Haenger (Waechter, Vorgabe 300 s je Befehl) nichts verschluckt; der
Waechter schreibt den Traceback des haengenden Befehls nach
<MODELL>_menudurchgang_waechter.log und beendet den Lauf. Mit --ab NR geht es
nach einem Abbruch weiter (die Ergebnisdatei wird fortgeschrieben).

Erster Durchgang am Drehlager (11.09.2026, 203 Befehle): 138 in Ordnung, 32
erwartbare Hinweise, keine Ausnahme, zwei Haenger - "Alles auswaehlen"
(Tabellenmarkierung) und "Aus Knickfigur" (Knickrechnung im GUI-Thread) -
und drei Befehle mit 113 s durch die Rueckgaengig-Sicherung. Alle behoben.
"""
import argparse
import faulthandler
import json
import os

os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")     # kein Browser aus dem Durchgang
import sys
import time
import traceback

os.environ["STATIK3D_NO_UPDATE_CHECK"] = "1"
sys.path.insert(0, os.getcwd())
_ARGS = argparse.ArgumentParser(description="Menuedurchgang an einem Modell")
_ARGS.add_argument("modell", help="Statik3D-Modell (.json)")
_ARGS.add_argument("--ab", type=int, default=1, help="ab diesem Befehl (Nummer) weitermachen")
_ARGS.add_argument("--waechter", type=int, default=300, help="Sekunden je Befehl, dann Abbruch")
ARGS = _ARGS.parse_args() if __name__ == "__main__" else None
MODELL = ARGS.modell if ARGS else ""
AUSGABE = os.path.splitext(MODELL)[0] + "_menudurchgang.jsonl"
WAECHTER = os.path.splitext(MODELL)[0] + "_menudurchgang_waechter.log"

# Befehle, die hier nicht ausgeloest werden - mit Grund
UEBERSPRINGEN = {
    "Neu": "ersetzt das Modell", "Öffnen": "ersetzt das Modell",
    "Speichern": "schriebe drehlager.json", "Speichern unter…": "Dateidialog, dann Schreiben",
    "Beenden": "beendet das Programm",
    "Rahmen": "Beispiel ersetzt das Modell", "Fachwerk": "Beispiel ersetzt das Modell",
    "Platte": "Beispiel ersetzt das Modell", "Konsole": "Beispiel ersetzt das Modell",
    "Hallenrahmen": "Beispiel ersetzt das Modell", "Stauwand": "Beispiel ersetzt das Modell",
    "Abhebendes Lager": "Beispiel ersetzt das Modell", "Reibung": "Beispiel ersetzt das Modell",
    "Berechnen": "Rechnung 2 Mio. Elemente x 422 Lastfaelle",
    "Nur aktiver Lastfall": "Rechnung mit Kontakt, 2 Mio. Elemente",
    "Eigenschwingungen": "Rechnung", "Knicken": "Rechnung", "Alle Stellungen": "Rechnung",
    "Vernetzen": "Vernetzung 4 min", "Flächen vernetzen": "Vernetzung", "Volumen vernetzen": "Vernetzung",
    "Netz löschen": "zerstoert das Netz", "Alle Elemente löschen": "zerstoert das Netz",
    "Kontaktfugen ausführen": "aendert das Netz",
    "Doppelte Knoten zusammenführen": "aendert das Modell (400 000 Knoten)",
    "Freie Bewegungen suchen": "Gleichungssystem 2 Mio. Elemente",
    "Bedienung im Browser…": "startet einen Server",
    "Rückgängig": "Zustand", "Wiederholen": "Zustand",
    "Nach Update suchen…": "Netz, ersetzt die exe",
    "Aus Knickfigur": "Knickrechnung am ganzen Modell (laeuft im Hintergrund, Minuten)",
}
START = ARGS.ab if ARGS else 1
WAECHTER_SEK = ARGS.waechter if ARGS else 300


def main():
    from PySide6 import QtWidgets, QtCore
    import numpy as np
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    # Alle Dialoge: Abbrechen / Nein / leer
    QtWidgets.QDialog.exec = lambda self, *a, **k: 0
    QtWidgets.QDialog.exec_ = lambda self, *a, **k: 0
    QtWidgets.QMessageBox.question = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.StandardButton.No)
    QtWidgets.QMessageBox.information = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Ok)
    QtWidgets.QMessageBox.warning = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Ok)
    QtWidgets.QMessageBox.critical = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Ok)
    QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
    QtWidgets.QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
    QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
    QtWidgets.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
    QtWidgets.QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
    QtWidgets.QInputDialog.getInt = staticmethod(lambda *a, **k: (0, False))
    QtWidgets.QInputDialog.getDouble = staticmethod(lambda *a, **k: (0.0, False))
    QtWidgets.QInputDialog.getItem = staticmethod(lambda *a, **k: ("", False))

    from statik3d.gui.main import MainWindow
    from statik3d.model import Model
    w = MainWindow()
    w.show()
    app.processEvents()
    meldungen: list = []
    w._fragen = lambda titel, text: (meldungen.append(("frage", f"{titel}: {text}")), False)[1]
    w.error = lambda msg: meldungen.append(("error", str(msg)))
    w.info = lambda msg: meldungen.append(("info", str(msg)))

    out = open(AUSGABE, "a" if START > 1 else "w", encoding="utf-8")

    def schreibe(d):
        out.write(json.dumps(d, ensure_ascii=False) + "\n")
        out.flush()

    # Modell laden wie "Oeffnen"
    t0 = time.time()
    w.model = Model.load(MODELL)
    w._MainWindow__init_defaults()
    w.analysis = None
    w.results = None
    w.selection = np.array([], dtype=int)
    w.path = MODELL
    w.refresh_all()
    w._refresh_title()
    w.zoom_alles()
    app.processEvents()
    schreibe({"schritt": "laden", "dauer": round(time.time() - t0, 1), "elemente": len(w.model.elements),
              "lastfaelle": len(w.model.load_cases), "kombinationen": len(w.model.combinations)})
    print(f"[laden] {time.time() - t0:.0f} s, {len(w.model.elements)} Elemente", flush=True)

    befehle = list(w.ribbon.befehle)
    for i, b in enumerate(befehle, 1):
        kennung = f"{b.register} > {b.gruppe} > {b.text}"
        if i < START:
            continue
        if b.text in UEBERSPRINGEN or b.register.startswith("Auswahl"):
            schreibe({"nr": i, "register": b.register, "gruppe": b.gruppe, "text": b.text,
                      "status": "uebersprungen", "grund": UEBERSPRINGEN.get(b.text, "Kontextregister")})
            continue
        meldungen.clear()
        vorher = w.log.toPlainText()
        with open(WAECHTER, "a", encoding="utf-8") as wf:
            wf.write(f"\n=== {i}/{len(befehle)} {kennung}\n")
        wdatei = open(WAECHTER, "a", encoding="utf-8")
        faulthandler.dump_traceback_later(WAECHTER_SEK, exit=True, file=wdatei)
        t = time.time()
        fehler = ""
        try:
            if b.aktion.isCheckable():
                b.aktion.trigger()
                app.processEvents()
                b.aktion.trigger()          # zuruecksetzen
            else:
                b.aktion.trigger()
            for _ in range(3):
                app.processEvents()
        except Exception:               # noqa: BLE001
            fehler = traceback.format_exc()
        finally:
            faulthandler.cancel_dump_traceback_later()
            wdatei.close()
        dauer = round(time.time() - t, 2)
        neu = w.log.toPlainText()[len(vorher):].strip()
        traceback_im_protokoll = "Traceback" in neu
        status = "ausnahme" if fehler else ("traceback im protokoll" if traceback_im_protokoll
                                           else ("fehlermeldung" if any(a == "error" for a, _ in meldungen)
                                                 else "ok"))
        schreibe({"nr": i, "register": b.register, "gruppe": b.gruppe, "text": b.text, "status": status,
                  "dauer": dauer, "meldungen": list(meldungen), "protokoll": neu[-1500:], "fehler": fehler})
        print(f"[{i}/{len(befehle)}] {status:22s} {dauer:7.2f} s  {kennung}", flush=True)
        # Offene Masken/Fenster schliessen, damit der naechste Befehl frisch startet
        try:
            if hasattr(w, "maskenrand") and hasattr(w.maskenrand, "schliessen"):
                w.maskenrand.schliessen()
        except Exception:               # noqa: BLE001
            pass
        for top in QtWidgets.QApplication.topLevelWidgets():
            if top is not w and top.isVisible() and isinstance(top, (QtWidgets.QDialog, QtWidgets.QMainWindow)):
                top.close()
        app.processEvents()
    out.close()
    print("Durchgang beendet", flush=True)


if __name__ == "__main__":
    main()
