"""
Paket P6 der Fehlerliste vom 06.10.2026: ein Ergebnis gilt nur, wenn es zum
aktuellen Modell gehoert.

* F05: Die Rechnung laeuft auf dem Modell des Fensters. Bis zum 06.10.2026
  liess sich waehrend der Rechnung jede Maske uebernehmen; eine Last- oder
  Eigengewichtsaenderung galt danach als „passt“, das alte Ergebnis wurde
  gezeigt und gespeichert (Beleg fl_a\\t3\\probe_b.py, log_o24_3.txt). Jetzt ist
  „Übernehmen“ einer Maske waehrend der Rechnung gesperrt (Hinweis, die
  Eingaben bleiben stehen), eine reine Ansichtsmaske bleibt bedienbar. Aendert
  ein anderer Weg das Modell waehrend der Rechnung, passt ihr Ergebnis nicht:
  kein Bild, Kopfzeile „neu rechnen“, keine Ergebnisdatei. Ein Lauf ohne
  Modellstand (Nachweise, freie Bewegungen) wird dann verworfen.
* F06: Die Kennung der Ergebnisdatei verglich die Knotenkoordinaten nur als
  Summe: ein Knoten um (+0,3; 0; -0,3) m verschoben, das Modell als .json
  exportiert - beim Oeffnen „passt“ mit den Verschiebungen des alten Stands
  (Beleg fl_a\\t3\\probe_a.py, o24_2). Jetzt traegt die Kennung einen Hash der
  Knotenmatrix, und eine Datei mit der alten Kennung wird nicht still geladen.

Aufruf:  python -m tests.test_fehler_p6
"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_p6_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}


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
    # keine Rueckfragen (Abnahme des Netzes, Knoepfe) und keine Meldungsfenster
    w._fragen_knoepfe = lambda *a, **k: True
    w._fragen = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _warten(app, fertig, dauer=120.0):
    t0 = time.time()
    while not fertig() and time.time() - t0 < dauer:
        app.processEvents()
        time.sleep(0.02)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.005)


class _Langsam:
    """solve_all rechnet und haelt dann an, bis ``weiter`` gesetzt ist: so
    laeuft die Hintergrundrechnung noch, waehrend die Pruefung bedient. Das
    Ergebnis ist da schon fertig - wie im Beleg o24_3."""

    def __enter__(self):
        import statik3d.solver as slv
        self.slv, self.orig = slv, slv.solve_all
        self.gerechnet, self.weiter = threading.Event(), threading.Event()

        def langsam(*a, **k):
            r = self.orig(*a, **k)
            self.gerechnet.set()
            self.weiter.wait(60)
            return r
        slv.solve_all = langsam
        return self

    def __exit__(self, *_a):
        self.slv.solve_all = self.orig
        self.weiter.set()
        return False


def _rechnung_starten(w, app, l):
    w.cb_analysis.setCurrentIndex(0)                  # alle Lastfaelle + Kombinationen
    w.do_solve("all")
    _warten(app, l.gerechnet.is_set)
    return w._rechnet()


def _rechnung_beenden(w, app, l):
    l.weiter.set()
    _warten(app, lambda: not w._rechnet())


def _leeren(w):
    """Leiste und Maske weg, damit der naechste Teil frei anfaengt."""
    w._leiste_weg()
    if w.maskenrand.maske is not None:
        w._maske_verwerfen(w.maskenrand.maske)


def _uz(w, an, lf):
    """(uz gezeigt, uz frisch zum Modell von jetzt) am Knoten mit dem groessten uz [mm]."""
    from statik3d import solver
    frisch = solver.solve_all(w.model, design=False).cases[lf].u
    k = int(np.argmax(np.abs(frisch[:, 2])))
    return float(an.cases[lf].u[k, 2]) * 1e3, float(frisch[k, 2]) * 1e3


# ---------------------------------------------------------------------------
# F05
# ---------------------------------------------------------------------------
def test_f05_maske_gesperrt():
    """Lastfallmaske waehrend der Rechnung: „Übernehmen“ weist ab, nach der
    Rechnung geht es; das Ergebnis passt zum Modell, das gerechnet wurde."""
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    lf = w.model.active_case
    g0 = float(w.model.load_cases[lf].gravity[2])
    me = w.meldungen
    with _Langsam() as l:
        laeuft = _rechnung_starten(w, app, l)
        u0 = len(getattr(w, "_undo", []))
        me.leeren()
        mk = w._objektmaske("lastfall", lf) or w.maskenrand.maske
        mk.setzen("g_z", 2 * g0)
        ok = mk.anwenden(); app.processEvents()
        g_jetzt = float(w.model.load_cases[lf].gravity[2])
        check("F05: Lastfallmaske während der Rechnung: „Übernehmen“ gesperrt, g_z bleibt",
              laeuft and ok is False and g_jetzt == g0 and len(w._undo) == u0,
              f"rechnet {laeuft}, gelungen {ok}, g_z {g_jetzt}, Rückgängig {u0} -> {len(w._undo)}")
        check("… ein Hinweis sagt es, die Eingabe bleibt in der Maske stehen",
              me.hinweis_mit("Rechnung läuft", "erst nach der Rechnung übernehmen") and mk is w.maskenrand.maske
              and abs(float(mk.werte().get("g_z")) - 2 * g0) < 1e-9,
              f"{me.hinweise[-1:]}, g_z in der Maske {mk.werte().get('g_z')}")
        _rechnung_beenden(w, app, l)
    gezeigt, frisch = _uz(w, w.analysis, lf)
    check("… nach der Rechnung: „passt“, und das Ergebnis ist das des Modells (uz gleich)",
          w._analyse_passt() == "passt" and abs(gezeigt - frisch) < 1e-9,
          f"{w._analyse_passt()}, uz gezeigt {gezeigt:.4f} mm, zum Modell {frisch:.4f} mm")
    ok = mk.anwenden(); app.processEvents()
    check("… nach der Rechnung übernimmt dieselbe Maske, das Ergebnis gilt dann nicht mehr",
          ok is True and float(w.model.load_cases[lf].gravity[2]) == 2 * g0
          and (w.analysis is None or w._analyse_passt() != "passt"),
          f"gelungen {ok}, g_z {w.model.load_cases[lf].gravity[2]}, "
          f"analysis {'da' if w.analysis is not None else 'None'}")
    _leeren(w)


def test_f05_ansichtsmaske_frei():
    """Eine Maske, die nur die Ansicht stellt („Darstellung“, Knopf
    „Schließen“), bleibt waehrend der Rechnung bedienbar."""
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    me = w.meldungen
    with _Langsam() as l:
        laeuft = _rechnung_starten(w, app, l)
        me.leeren()
        w.maske_darstellung(); app.processEvents()
        mk = w.maskenrand.maske
        titel = getattr(mk, "titel", "")
        ok = mk.anwenden(); app.processEvents()
        check("F05: Maske „Darstellung“ während der Rechnung: „Schließen“ wirkt, kein Hinweis",
              laeuft and titel == "Darstellung" and ok is True and not w.maskenrand.offen() and not me.alle,
              f"rechnet {laeuft}, {titel!r}, gelungen {ok}, offen {w.maskenrand.offen()}, {me.alle[-1:]}")
        _rechnung_beenden(w, app, l)
    _leeren(w)


def test_f05_anderer_weg_macht_ungueltig():
    """Aendert ein Weg ausserhalb einer Maske das Modell waehrend der
    Rechnung (hier der Haken Eigengewicht im Register Lager/Lasten), passt ihr
    Ergebnis nicht: kein Bild, Kopfzeile, keine Ergebnisdatei."""
    from statik3d import ergebnisse as erg
    from statik3d.gui import viewport as vp
    w, app = _fenster()
    d = tempfile.mkdtemp(prefix="p6_f05_")
    # Gegenprobe: nichts geaendert -> „passt“, die Datei wird geschrieben
    w.load_example("frame"); app.processEvents()
    with _Langsam() as l:
        _rechnung_starten(w, app, l)
        _rechnung_beenden(w, app, l)
    p0 = os.path.join(d, "ohne.json")
    w.path = p0
    w.save_model(); app.processEvents()
    check("F05 Gegenprobe: nichts geändert während der Rechnung -> „passt“, Ergebnisdatei geschrieben",
          w._analyse_passt() == "passt" and os.path.exists(erg.pfad_zu(p0)), w._analyse_passt())
    _leeren(w)
    # Eigengewicht aus waehrend der Rechnung
    w.load_example("frame"); app.processEvents()
    lf = w.model.active_case
    n_log = len(w.log.toPlainText().splitlines())
    with _Langsam() as l:
        laeuft = _rechnung_starten(w, app, l)
        w.toggle_gravity(False); app.processEvents()
        g_jetzt = float(w.model.load_cases[lf].gravity[2])
        _rechnung_beenden(w, app, l)
    an = w.analysis
    passt = w._analyse_passt()
    gezeigt, frisch = _uz(w, an, lf) if an is not None else (float("nan"), float("nan"))
    check("F05: Eigengewicht während der Rechnung ausgeschaltet -> Ergebnis „anders“, nicht im Bild",
          laeuft and g_jetzt == 0.0 and an is not None and passt == "anders" and not w.plotter.scalar_bars,
          f"g_z {g_jetzt}, {passt}, {len(w.plotter.scalar_bars)} Skalen; uz gerechnet {gezeigt:.4f} mm, "
          f"zum Modell {frisch:.4f} mm")
    kopf = list(getattr(w, "_kopfzeile_zeilen", None) or [])
    neu = w.log.toPlainText().splitlines()[n_log:]
    check("… die Kopfzeile sagt „neu rechnen“, das Protokoll nennt den Grund",
          any(vp.ERGEBNIS_VERALTET in z for z in kopf)
          and any("während der Rechnung geändert" in z for z in neu),
          f"{kopf[-1:]}, {[z for z in neu if 'während der Rechnung' in z][:1]}")
    p = os.path.join(d, "mit.json")
    w.path = p
    w.save_model(); app.processEvents()
    check("… Speichern schreibt keine Ergebnisdatei", not os.path.exists(erg.pfad_zu(p)),
          str(os.path.exists(erg.pfad_zu(p))))
    _leeren(w)


def test_f05_lauf_ohne_stand_verworfen():
    """Ein Hintergrundlauf ohne Modellstand (Nachweise EC3, Ermuedung, freie
    Bewegungen) haengt sein Ergebnis an das Modell von jetzt. Wurde das
    Modell waehrend des Laufs geaendert, wird es verworfen."""
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    for aendern in (False, True):
        weiter = threading.Event()
        bekommen = []

        def lauf(progress=None):
            weiter.wait(30)
            return "Ergebnis"
        w._run_background(lauf, bekommen.append, "Probelauf")
        app.processEvents()
        laeuft = w._rechnet()
        if aendern:
            w.toggle_gravity(False); app.processEvents()
        weiter.set()
        _warten(app, lambda: not w._rechnet())
        if aendern:
            check("F05: Lauf ohne Modellstand, Modell währenddessen geändert -> Ergebnis verworfen",
                  laeuft and bekommen == [] and "während der Rechnung geändert" in w.log.toPlainText(),
                  f"rechnet {laeuft}, bekommen {bekommen}")
        else:
            check("F05 Gegenprobe: Lauf ohne Modellstand, nichts geändert -> Ergebnis kommt an",
                  laeuft and bekommen == ["Ergebnis"], f"rechnet {laeuft}, bekommen {bekommen}")


# ---------------------------------------------------------------------------
# F06
# ---------------------------------------------------------------------------
def test_f06_knotenlage():
    """Knoten verschoben, Summe gleich, Modell ohne Ergebnisdatei neu
    geschrieben (Export als .json): Oeffnen laedt das alte Ergebnis nicht."""
    from statik3d import ergebnisse as erg, solver
    from statik3d.exporters import export_model
    w, app = _fenster()
    me = w.meldungen
    w.load_example("frame"); app.processEvents()
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    d = tempfile.mkdtemp(prefix="p6_f06_")
    p = os.path.join(d, "rahmen.json")
    w.path = p
    gespeichert = w.save_model(); app.processEvents()
    ep = erg.pfad_zu(p)
    m = w.model
    k_alt = erg.kennung(m)
    k = int(np.argmin(np.linalg.norm(m.nodes - np.array([3.0, 0.0, 4.0]), axis=1)))
    s0 = float(np.asarray(m.nodes).sum())
    m.nodes[k] = m.nodes[k] + np.array([0.3, 0.0, -0.3])
    s1 = float(np.asarray(m.nodes).sum())
    ok_direkt, grund = erg.passt(k_alt, m)
    check("F06: Kennung erkennt einen verschobenen Knoten bei gleicher Koordinatensumme",
          abs(s0 - s1) < 1e-9 and not ok_direkt and "Knotenkoordinaten" in grund,
          f"Knoten {k}, Summe {s0:.6f} -> {s1:.6f}, passt {ok_direkt} ({grund})")
    export_model(m, p)                               # Modelldatei neu, Ergebnisdatei bleibt
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("… Öffnen nach Export als .json: kein Ergebnis geladen",
          gespeichert and os.path.exists(ep) and w.analysis is None and w.current_result() is None,
          f"gespeichert {gespeichert}, Datei {os.path.exists(ep)}, "
          f"analysis {'da' if w.analysis is not None else 'None'}")
    check("… ein Hinweis sagt, warum die Ergebnisdatei nicht geladen wurde",
          me.hinweis_mit("Ergebnisdatei nicht geladen", "Knotenkoordinaten"), str(me.alle[-1:]))


def _kennung_der_datei(pfad, model):
    from statik3d import ergebnisse as erg
    with open(pfad, "rb") as fh:
        return erg._Leser(fh, model).load().get("kennung") or {}


def test_f06_alte_kennung():
    """Eine Ergebnisdatei mit der Kennung von vor dem 06.10.2026 (nur die
    Summe der Koordinaten) wird nicht still als passend geladen: sie kommt
    mit einem Hinweis, der den Vorbehalt nennt. Speichern ohne neue Rechnung
    behaelt die alte Form der Kennung (der Vorbehalt bleibt), erst eine neue
    Rechnung schreibt die neue."""
    from statik3d import ergebnisse as erg, solver
    w, app = _fenster()
    me = w.meldungen
    w.load_example("frame"); app.processEvents()
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    d = tempfile.mkdtemp(prefix="p6_f06_alt_")
    p = os.path.join(d, "alt.json")
    ep = erg.pfad_zu(p)
    w.path = p
    neu = erg.kennung

    def alt(model):
        k = dict(neu(model))
        k.pop("knoten", None)                     # so schrieb das Programm bis zum 06.10.2026
        return k
    erg.kennung = alt
    try:
        w.save_model(); app.processEvents()
    finally:
        erg.kennung = neu
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("F06: Ergebnisdatei mit alter Kennung (nur Koordinatensumme): geladen, aber mit Hinweis",
          w.analysis is not None and me.hinweis_mit("mit Vorbehalt", "06.10.2026", "neu rechnen"),
          f"analysis {'da' if w.analysis is not None else 'None'}, {me.alle[-1:]}")
    w.save_model(); app.processEvents()
    k1 =_kennung_der_datei(ep, w.model)
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("… wieder gespeichert ohne neue Rechnung: alte Form bleibt, der Hinweis kommt wieder",
          "knoten" not in k1 and w.analysis is not None and me.hinweis_mit("mit Vorbehalt"),
          f"knoten in der Kennung {'knoten' in k1}, {me.alle[-1:]}")
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    w.save_model(); app.processEvents()
    k2 = _kennung_der_datei(ep, w.model)
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("… nach neuer Rechnung gespeichert: neue Kennung, ohne Vorbehalt geladen",
          "knoten" in k2 and w.analysis is not None and not me.hinweis_mit("mit Vorbehalt"),
          f"knoten in der Kennung {'knoten' in k2}, {me.alle[-1:]}")


def test_f06_rundlauf():
    """Speichern und Oeffnen ohne Aenderung: die Kennung passt fuer alle
    Beispiele, auch mit -0.0 in den Koordinaten; Ergebnisse kommen wieder."""
    from statik3d import ergebnisse as erg, examples_lib, solver
    from statik3d.model import Model
    d = tempfile.mkdtemp(prefix="p6_f06_rund_")
    for name in ("frame", "truss", "hall", "gate", "contact"):
        m = examples_lib.build_example(name)
        if m.nn:
            m.nodes[0, 0] = -0.0 if m.nodes[0, 0] == 0.0 else m.nodes[0, 0]
        p = os.path.join(d, f"{name}.json")
        m.save(p)
        k = erg.kennung(m)
        ok, grund = erg.passt(k, Model.load(p))
        check(f"F06: {name}: Kennung nach Speichern und Laden passt", ok and "knoten" in k,
              grund or str(k.get("knoten")))
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    p = os.path.join(d, "rahmen.json")
    w.path = p
    w.save_model(); app.processEvents()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("F06: Rahmen mit Ergebnis gespeichert und geöffnet: Ergebnis wieder da und „passt“",
          w.analysis is not None and w._analyse_passt() == "passt",
          f"analysis {'da' if w.analysis is not None else 'None'}")


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_f05_maske_gesperrt, test_f05_ansichtsmaske_frei, test_f05_anderer_weg_macht_ungueltig,
              test_f05_lauf_ohne_stand_verworfen, test_f06_knotenlage, test_f06_alte_kennung,
              test_f06_rundlauf):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    sys.stdout.flush()
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
