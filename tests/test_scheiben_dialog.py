"""Scheiben einleiten: Dialog, Rueckgaengig und Startabfrage (seit 16.10.2026).

* Der Dialog „Scheiben einleiten“ zeigt je Gruppe gleicher Bohrung (oder je
  Scheibe) Einleitung, Innen- und Außen-Ø, die Herkunft des Maßes (Annahme
  mit Norm) und die mittlere Pressung F/A_Ring mit ihrem Verhaeltnis zu f_y.
* Ein eingetragenes Außenmaß loescht das Kennzeichen „Annahme“; das
  vorbelegte Normmaß bleibt Annahme.
* „Alle auf Kreisring“ stellt um und koppelt am Netz neu, Rueckgaengig
  (Strg+Z) stellt zurueck. Die Geometrie bleibt dabei bitgleich (Regel des
  Anwenders: RFEM-Importe nicht selbststaendig in der Geometrie aendern).
* Vor einer plastischen Rechnung mit Lochrand-Scheibe: der Dialog mit
  Abbrechen, Trotzdem rechnen, Auf Kreisring umstellen. Elastisch fragt nichts.

Aufruf:  python -m tests.test_scheiben_dialog
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_scheiben_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
FEHLER = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {str(detail)[:200]}")
    return ok


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, FEHLER)
    _FENSTER.update(w=w, app=app)
    return w, app


def _ins_fenster(w, app, m):
    w.model = m
    w._MainWindow__init_defaults()
    w.analysis = None
    w.results = None
    w.refresh_all()
    app.processEvents()


def geometrie(m) -> tuple:
    """Die Geometrie als Bytes: Knoten, Linien, Flaechen (ohne Einleitung und
    Kommentar der Kopplung), Koerper, Netz."""
    import json
    from dataclasses import asdict
    fl = {}
    for n, f in m.flaechen.items():
        d = asdict(f)
        d.pop("einleitung", None)
        d.pop("kommentar", None)
        fl[n] = d
    return (np.asarray(m.nodes, float).tobytes(),
            json.dumps({n: asdict(x) for n, x in m.lines.items()}, sort_keys=True, default=str),
            json.dumps(fl, sort_keys=True, default=str),
            json.dumps({n: asdict(x) for n, x in m.koerper.items()}, sort_keys=True, default=str),
            json.dumps([(e.typ, [int(x) for x in e.nodes]) for e in m.elements]))


def test_dialog():
    print("\n--- Dialog „Scheiben einleiten“ ---")
    from statik3d import scheibeneinleitung as SCH
    from statik3d.gui import scheiben_dialog as SD
    from tests.test_scheibe_kreisring import blech, ring_sk
    w, app = _fenster()
    m = blech(h=0.006, ordnung=1)
    _ins_fenster(w, app, m)
    dlg = SD.ScheibenDialog(w.model, w)
    t = dlg.tabelle
    text = [t.item(0, k).text() if t.item(0, k) else "" for k in range(t.columnCount())]
    check("eine Zeile je Gruppe: Bohrung 20, Stab 20, Lochrand, Normmaß 37 als Annahme ISO 7089",
          t.rowCount() == 1 and t.cellWidget(0, 4).currentIndex() == 0 and text[6] == "37,0"
          and text[7].startswith("Annahme: ISO 7089 M20"), f"{text}")
    check("… mit der mittleren Pressung F/A_Ring und dem Verhältnis zu f_y",
          "N/mm²" in text[8] and "f_y" in text[8], text[8])
    t.cellWidget(0, 4).setCurrentIndex(1)
    u = dlg.umstellungen()
    check("Kreisring mit vorbelegtem Maß: Normmaß, bleibt Annahme", u == [(["F1"], SCH.RING, 0.0, None)], f"{u}")
    t.item(0, 6).setText("40")
    u = dlg.umstellungen()
    check("eingetragenes Außenmaß 40 mm: gilt als eingetragen",
          len(u) == 1 and u[0][1] == SCH.RING and abs(u[0][3] - 0.040) < 1e-12, f"{u}")
    dlg.cb_modus.setCurrentIndex(1)
    check("je Scheibe: eine Zeile mit Namen und Stab", dlg.tabelle.rowCount() == 1
          and dlg.tabelle.item(0, 0).text() == "F1 (S1)", dlg.tabelle.item(0, 0).text())
    dlg.deleteLater()

    print("\n--- Alle auf Kreisring, Rückgängig, Geometrie bitgleich ---")
    vorher = geometrie(w.model)
    w.log.clear()
    erg = w._scheiben_umstellen(alle=True)
    log = w.log.toPlainText()
    check("umgestellt, am Netz neu gekoppelt, Protokoll mit Annahme und Pressung",
          erg["umgestellt"] == ["F1"] and len(ring_sk(w.model)) == 1 and "über einen Kreisring" in log
          and "Annahme ISO 7089 M20" in log and "Rückgängig" in log, log[-300:])
    check("die Geometrie bleibt bitgleich (Knoten, Linien, Flächen, Körper, Netz)",
          geometrie(w.model) == vorher, "")
    w.undo()
    app.processEvents()
    check("Rückgängig: wieder Lochrand, wieder starr gekoppelt",
          w.model.flaechen["F1"].einleitung == {} and not ring_sk(w.model)
          and any(str(k.gruppe) == "starr F1" for k in w.model.kopplungen), "")
    check("… und die Geometrie wie vorher", geometrie(w.model) == vorher, "")
    u = SD.eintraege(SD.zeilen_bilden(SCH.scheiben(w.model), True), [(SCH.RING, "", "41,5")])
    w._scheiben_umstellen(umstellungen=u)
    e = w.model.flaechen["F1"].einleitung
    check("über die Tabelle eingetragen: Kreisring 41,5 mm ohne „Annahme“",
          e.get("art") == "ring" and abs(e["d_aussen"] - 0.0415) < 1e-12 and e["annahme"] is False
          and len(ring_sk(w.model)) == 1, f"{e}")
    check("… Geometrie bitgleich", geometrie(w.model) == vorher, "")


def test_startabfrage():
    print("\n--- Vor der plastischen Rechnung ---")
    from tests.test_scheibe_kreisring import blech, ring_sk
    w, app = _fenster()
    gefragt = []

    def frage(antwort):
        def f(h):
            gefragt.append(h)
            return antwort
        return f
    m = blech(h=0.006, ordnung=1, plast=False)
    _ins_fenster(w, app, m)
    w._plastisch_frage = frage("abbrechen")
    check("elastisch: keine Abfrage", w._plastisch_einleitung_bestaetigen() and not gefragt, "")
    w.model.plastizitaet.an = True
    w.log.clear()
    ok = w._plastisch_einleitung_bestaetigen()
    check("plastisch mit Lochrand: Abfrage, Abbrechen hält an, Protokoll deutlich",
          not ok and len(gefragt) == 1 and gefragt[0]["lochrand"] == ["F1"]
          and "WARNUNG – BITTE LESEN" in w.log.toPlainText(), gefragt[0]["text"][:200] if gefragt else "")
    w._plastisch_frage = frage("rechnen")
    check("Trotzdem rechnen: läuft, das Protokoll vermerkt die Bestätigung",
          w._plastisch_einleitung_bestaetigen() and "vom Anwender bestätigt" in w.log.toPlainText(), "")
    w._plastisch_frage = frage("kreisring")
    ok = w._plastisch_einleitung_bestaetigen()
    check("Auf Kreisring umstellen: umgestellt, gekoppelt, es wird gerechnet",
          ok and w.model.flaechen["F1"].einleitung.get("art") == "ring" and len(ring_sk(w.model)) == 1, "")
    n = len(gefragt)
    check("danach fragt nichts mehr (keine Kraft ohne Fläche)",
          w._plastisch_einleitung_bestaetigen() and len(gefragt) == n, "")


def main():
    for t in (test_dialog, test_startabfrage):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
