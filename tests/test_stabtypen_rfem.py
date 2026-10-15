"""
Stabtypen aus RFEM nachlesen - die Aktion in der Oberfläche (14.10.2026).

Ein Modell, das vor dem 14.10.2026 aus RFEM 6 übernommen wurde, kennt seine
Zugstäbe, Druckstäbe und Seile nicht: der Import legte sie als Fachwerkstäbe
an, die Zug und Druck trugen. Beim Öffnen steht ein Importhinweis „zugstab“;
die Umstellung (rfem6_db.zugstaebe_aus_rfem) gab es bis dahin nur als
Funktion für die Konsole. Seither:

* Register Datei › Austausch › „Stabtypen aus RFEM nachlesen…“ (seit dem
  15.10.2026 im Menüknopf „Aus RFEM nachlesen ▾“) öffnet rechts
  die Maske „Stabtypen aus RFEM“ mit dem Hinweis aus dem Import und der
  RFEM-Datei; „Stabtypen nachlesen“ stellt um (ein Rückgängig-Schritt).
* Beim Öffnen eines solchen Modells nennt der Hinweis (Statuszeile und
  Protokoll) diesen Weg.
* Fehlt die RFEM-Datei, kommt ein Hinweis, und nichts wird umgestellt.

Aufruf:  python -m tests.test_stabtypen_rfem
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_stabtypen_rfem_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
AKTION = "Stabtypen aus RFEM nachlesen…"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
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
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _alte_datei(tmp):
    """Ein Modell aus RFEM 6 (Seil S1, Balken S2, Zugstab S3), gespeichert so,
    wie der Import es bis zum 14.10.2026 anlegte: Fachwerkstäbe ohne „trägt
    nur“, ohne die Merkmale des Imports."""
    from statik3d.importers import rfem6_db as R6
    from tests.test_stab_nachzug import _rf6_seil
    rf6 = _rf6_seil(tmp, mit_zugstab=True)
    m = R6.read_rf6(rf6, log=[])
    for e in m.elements:
        if e.typ == "seil":
            e.typ = "truss"
        e.nur = ""
    m.meta.pop("rfem_zugstaebe", None)
    m.meta.pop("rfem_seile", None)
    m.meta["quelle"] = rf6
    pfad = os.path.join(tmp, "alt.json")
    m.save(pfad)
    return pfad, rf6


def _arten(m, stab):
    return [(m.elements[i].typ, m.elements[i].nur) for i in m.members[stab].elements]


def _aktion(w):
    from PySide6 import QtGui
    return next((a for a in w.findChildren(QtGui.QAction) if a.text() == AKTION), None)


def test_hinweis_menue_und_umstellung():
    w, app = _fenster()
    tmp = tempfile.mkdtemp()
    try:
        pfad, rf6 = _alte_datei(tmp)
        n_log = len(w.log.toPlainText().splitlines())
        w.modell_laden(pfad, fragen=False); app.processEvents()
        neu = w.log.toPlainText().splitlines()[n_log:]
        check("beim Öffnen: das Protokoll nennt die Fachwerkstäbe und den Weg zur Umstellung",
              any("Aus RFEM 6 übernommen" in z and "Stabtypen aus RFEM nachlesen" in z for z in neu),
              next((z[:140] for z in neu if "RFEM 6" in z), "-"))
        status = w.statusBar().currentMessage()
        check("… und die Statuszeile, als Hinweis", "Stabtypen aus RFEM nachlesen" in status, status[:140])
        check("von selbst wird nichts umgestellt", _arten(w.model, "S1") == [("truss", "")])
        a = _aktion(w)
        check(f"Register Datei › Austausch: „{AKTION}“", a is not None)
        if a is None:
            return
        a.trigger(); app.processEvents()
        mk = w.maskenrand.maske
        check("die Aktion öffnet rechts die Maske „Stabtypen aus RFEM“",
              mk is not None and getattr(mk, "titel", "") == "Stabtypen aus RFEM", getattr(mk, "titel", "-"))
        if mk is None:
            return
        werte = mk.werte()
        check("… mit dem Hinweis aus dem Import und der RFEM-Datei",
              "Fachwerkst" in str(werte.get("hinweise", "")) and str(werte.get("pfad", "")) == rf6,
              f"{str(werte.get('hinweise', ''))[:80]} | {werte.get('pfad')}")
        n_log = len(w.log.toPlainText().splitlines())
        n_meld = len(w.meldungen.alle)
        mk.anwenden(); app.processEvents()
        neu = w.log.toPlainText().splitlines()[n_log:]
        check("„Stabtypen nachlesen“: Seil wird Seil, Zugstab nur Zug, Balken bleibt",
              _arten(w.model, "S1") == [("seil", "zug")] and _arten(w.model, "S3") == [("truss", "zug")]
              and _arten(w.model, "S2") == [("beam", "")], f"{_arten(w.model, 'S1')} {_arten(w.model, 'S3')}")
        check("… ohne Fehler und Hinweis, das Protokoll nennt das Ergebnis",
              len(w.meldungen.alle) == n_meld and any("nachgelesen" in z and "1 Zugstab nur Zug" in z and "1 Seil als Seil" in z
                                                  for z in neu),
              str(neu[-2:])[:200])
        check("… der Importhinweis ist erledigt",
              all(h.get("erledigt") for h in w.model.importhinweise if h.get("art") == "zugstab"))
        w.undo(); app.processEvents()
        check("Rückgängig nimmt die Umstellung zurück", _arten(w.model, "S1") == [("truss", "")]
              and _arten(w.model, "S3") == [("truss", "")], str(_arten(w.model, "S1")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fehlende_datei():
    w, app = _fenster()
    tmp = tempfile.mkdtemp()
    try:
        pfad, rf6 = _alte_datei(tmp)
        w.modell_laden(pfad, fragen=False); app.processEvents()
        a = _aktion(w)
        if not check(f"„{AKTION}“ vorhanden", a is not None):
            return
        a.trigger(); app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("pfad", os.path.join(tmp, "gibt_es_nicht.rf6"))
        n_f = len(w.meldungen.fehler)
        mk.anwenden(); app.processEvents()
        check("fehlende RFEM-Datei: ein Hinweis mit der Datei, kein Fehlerfenster",
              w.meldungen.hinweis_mit("gibt_es_nicht.rf6") and len(w.meldungen.fehler) == n_f,
              str(w.meldungen.hinweise[-1:])[:160])
        check("… und nichts umgestellt", _arten(w.model, "S1") == [("truss", "")]
              and _arten(w.model, "S3") == [("truss", "")])
        mk.abbrechen(); app.processEvents()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_hinweis_menue_und_umstellung, test_fehlende_datei):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
