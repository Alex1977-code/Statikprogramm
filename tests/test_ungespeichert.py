"""
Nichts geht ungefragt verloren (Paket 3 des Oberflaechenplans, 24.09.2026).

Geprueft wird mit dem echten Hauptfenster offscreen:

* der Merker fuer ungespeicherte Aenderungen (Stern im Fenstertitel) ueber
  alle Aenderungswege: merken(), Rueckgaengig/Wiederholen, zurueckgenommene
  Rueckgaengig-Punkte, Tabelleneingabe, Textfelder, Registerknoepfe ohne
  merken() (Alle Lager loeschen, Eigengewicht, Temperatur), Aenderungen am
  Modell ohne jeden Vermerk (Sicherheitsnetz Modellsignatur) und eine
  fertige Rechnung;
* die Rueckfrage Speichern / Verwerfen / Abbrechen vor Neu, Oeffnen,
  Beispiel, Import und Beenden - mit dem Testschalter STATIK3D_UNGESPEICHERT;
* Beenden waehrend einer Rechnung;
* „Beispiel öffnen ▾“, „Modell leeren (Eigenschaften behalten)…“ (mit und
  ohne Rueckgaengig), „Alle Kontakte löschen…“;
* die Befehlssuche (Wortanfang, Synonyme, Trefferliste, nichts
  Modellersetzendes oder Loeschendes direkt);
* der Rueckgaengig-Knopf nennt, was er zuruecknimmt;
* Doppelklick auf einen Zweig im Modellbaum: rechte Anlegemaske „Neu …“,
  nichts wird angelegt (Antwort 11 des Anwenders).

Nachbesserung nach der Gegenpruefung (25.09.2026): die Suche mit echten
Tasten (Enter lief doppelt bzw. auf der ersten Zeile), die Loeschfragen mit
echtem Fenster und Enter (Vorgabe Abbrechen) und ihr Text (was wirklich
verschwindet, ungespeicherte Ergebnisse), keine Modellwechsel waehrend einer
Rechnung (auch unveraendert) und kein fremdes Ergebnis danach, Speichern bei
gescheiterter Ergebnisdatei, Projektangaben am grossen Modell ohne
Modellkopie, und je Rueckgaengig-/Vermerk-Weg eine Pruefung, die ohne ihn
reisst (Ruecknahme: scratchpad p3_mutanten.py).

Aufruf:  python -m tests.test_ungespeichert
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_ungespeichert_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
TMP = tempfile.mkdtemp(prefix="statik3d_ungespeichert_modelle_")
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
    w.error = lambda msg: w.log.appendPlainText("FEHLER: " + str(msg))
    _FENSTER.update(w=w, app=app)
    return w, app


class _Fragen:
    """Ersatz fuer die Rueckfrage mit drei Antworten: zeichnet auf, antwortet
    wie vorgegeben. Der Testschalter STATIK3D_UNGESPEICHERT ist dabei aus -
    er wuerde die Frage sonst gar nicht erst stellen."""

    def __init__(self, w, antwort="abbrechen"):
        self.w, self.antwort, self.gefragt = w, antwort, []
        self.alt_env = None

    def __enter__(self):
        self.alt_env = os.environ.pop("STATIK3D_UNGESPEICHERT", None)
        self.w._frage_speichern_verwerfen = lambda anlass, grund: (
            self.gefragt.append((anlass, grund)), self.antwort)[1]
        return self

    def __exit__(self, *_a):
        self.w.__dict__.pop("_frage_speichern_verwerfen", None)
        if self.alt_env is not None:
            os.environ["STATIK3D_UNGESPEICHERT"] = self.alt_env


def _knopf_fragen(w, antwort: bool):
    """_fragen_knoepfe ersetzen: aufzeichnen und mit ``antwort`` antworten."""
    gefragt = []
    w._fragen_knoepfe = lambda titel, text, ja="Ja", nein="Abbrechen", vorgabe="ja": (
        gefragt.append((titel, text, ja, nein, vorgabe)), antwort)[1]
    return gefragt


def _modal_taste(app, taste, protokoll, versuche=100):
    """Sobald ein modales Fenster offen ist: Titel und Vorgabeknopf merken,
    dann ``taste`` druecken - wie am Desktop. Nach ``versuche`` x 30 ms ohne
    Fenster gibt der Zeitgeber auf, damit er keine spaetere Frage trifft."""
    from PySide6 import QtCore, QtTest, QtWidgets

    def los(rest=versuche):
        d = QtWidgets.QApplication.activeModalWidget()
        if d is None:
            if rest > 0:
                QtCore.QTimer.singleShot(30, lambda: los(rest - 1))
            return
        vorgabe = (d.defaultButton().text() if isinstance(d, QtWidgets.QMessageBox) and d.defaultButton()
                   else None)
        protokoll.append((d.windowTitle(), vorgabe, getattr(d, "text", lambda: "")()))
        QtTest.QTest.keyClick(d, taste)
    QtCore.QTimer.singleShot(30, los)


def _tippen(w, app, text, taste=None, runter=0):
    """Befehlssuche mit echten Tasten: ``text`` tippen, ``runter`` mal Pfeil
    runter, dann ``taste`` (Vorgabe Enter). Jede Taste geht dorthin, wo sie
    am Desktop ankommt: an die offene Trefferliste, sonst ans Suchfeld.
    Rueckgabe: (Liste vor Enter aktiv?, Liste danach offen?)."""
    from PySide6 import QtCore, QtGui, QtTest, QtWidgets
    rb = w.ribbon
    taste = QtCore.Qt.Key_Return if taste is None else taste
    rb.suche.setFocus(); rb.suche.clear(); app.processEvents()
    for ch in text:
        ziel = QtWidgets.QApplication.activePopupWidget() or rb.suche
        if ch.isascii():
            QtTest.QTest.keyClicks(ziel, ch)
        else:
            # QTest.keyClicks bricht an Umlauten hart ab (Prozessende) - ein
            # Tastenereignis mit Text, wie es die Tastatur liefert
            for typ in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                QtWidgets.QApplication.sendEvent(ziel, QtGui.QKeyEvent(typ, 0, QtCore.Qt.NoModifier, ch))
        app.processEvents()
    for _ in range(runter):
        QtTest.QTest.keyClick(QtWidgets.QApplication.activePopupWidget() or rb.suche, QtCore.Qt.Key_Down)
        app.processEvents()
    pop = rb._vervollstaendigung.popup()
    aktiv = QtWidgets.QApplication.activePopupWidget() is pop
    QtTest.QTest.keyClick(QtWidgets.QApplication.activePopupWidget() or rb.suche, taste)
    app.processEvents()
    offen = pop.isVisible()
    pop.hide(); app.processEvents()
    return aktiv, offen


def _stern(w) -> bool:
    return "*" in w.windowTitle()


def _fingerabdruck(m) -> str:
    """Was Model.save schriebe - ohne den aktiven Lastfall (eine Anzeigewahl)."""
    d = m.to_dict()
    d.pop("active_case", None)
    return json.dumps(d, sort_keys=True, default=str)


# --------------------------------------------------------------------------
def test_merker_und_stern():
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    check("nach dem Laden eines Beispiels: nichts ungespeichert, kein Stern",
          not w.ungespeichert() and not _stern(w), w.windowTitle())
    # reine Anzeige: Ergebnisfeld, Baumklick, Lastfallwahl - keine Aenderung
    w._baum_geklickt("lastfaelle", "Lastfälle"); app.processEvents()
    w.redraw(); app.processEvents()
    check("Anzeigen und Baumklick sind keine Änderung", not w.ungespeichert() and not _stern(w))
    # merken()-Weg: Tabelleneingabe Knotenkoordinate
    w.tabelle_zeigen("Knoten"); app.processEvents()
    mdl = w.tbl_knoten.modell
    z = next(i for i, r in enumerate(mdl.zeilen) if str(r[0]) == "1")
    idx = mdl.index(z, 1)
    faktor = mdl.anzeige(1)[0] or 1.0
    ok = mdl.setData(idx, str((float(w.model.nodes[1][0]) + 0.25) * faktor))
    app.processEvents()
    check("Tabelleneingabe: Merker und Stern im Titel",
          ok and w.ungespeichert() and _stern(w), w.windowTitle())
    w.undo(); app.processEvents()
    check("Rückgängig bis zum gespeicherten Stand: kein Stern mehr",
          not w.ungespeichert() and not _stern(w), w.windowTitle())
    w.redo(); app.processEvents()
    check("Wiederholen: wieder ungespeichert", w.ungespeichert() and _stern(w))
    w.undo(); app.processEvents()
    # zurueckgenommener Rueckgaengig-Punkt: Loeschen eines Lastfalls, den es
    # nicht gibt - merken() und sofort wieder vom Stapel
    w._bestaetigen = lambda text: True
    try:
        w._baum_loeschen("lastfall", "GIBTSNICHT"); app.processEvents()
    finally:
        del w._bestaetigen
    check("zurückgenommener Rückgängig-Punkt: kein Merker",
          not w.ungespeichert() and not _stern(w), w.windowTitle())
    # Textfeld Projektangaben (editingFinished ohne merken)
    e = w.ed_meta["projekt"]
    e.setText("Brücke Nord"); e.editingFinished.emit(); app.processEvents()
    check("Textfeld Projekt: ungespeichert", w.ungespeichert() and w.model.meta.get("projekt") == "Brücke Nord")
    w.undo(); app.processEvents()
    check("… und rückgängig zu machen", w.model.meta.get("projekt", "") != "Brücke Nord"
          and not w.ungespeichert())
    e.setText(w.model.meta.get("projekt", "")); e.editingFinished.emit(); app.processEvents()
    check("… derselbe Text noch einmal bestätigt ist keine Änderung", not w.ungespeichert())
    # Registerknoepfe, die bisher nichts vermerkten
    w.cb_g.setChecked(not w.cb_g.isChecked()); app.processEvents()
    check("Eigengewicht an/aus (Register, ohne merken()): ungespeichert", w.ungespeichert() and _stern(w))
    w.load_example("frame"); app.processEvents()
    # Sicherheitsnetz: eine Aenderung ohne jeden Vermerk (neuer Knoten)
    w.model.add_node(9.0, 9.0, 9.0)
    w.refresh_all(); app.processEvents()
    check("Modelländerung ohne merken(): die Modellsignatur fängt sie (Stern)",
          w.ungespeichert() and _stern(w), w.windowTitle())
    # Speichern: kein Stern mehr
    p = os.path.join(TMP, "merker.json")
    w.path = p
    ok = w.save_model()
    app.processEvents()
    check("Speichern: Datei geschrieben, kein Stern, nichts ungespeichert",
          ok is True and os.path.exists(p) and not w.ungespeichert() and not _stern(w), w.windowTitle())


def test_ergebnis_ungespeichert():
    w, app = _fenster()
    from statik3d import solver
    w.load_example("frame"); app.processEvents()
    an = solver.solve_all(w.model, design=False)
    # der Weg einer Hintergrundrechnung: _bg_done ruft _solve_done
    w._bg_done(lambda r: w._solve_done("all", r), an)
    app.processEvents()
    grund = w.ungespeichert()
    check("fertige Rechnung: die Ergebnisse gelten als ungespeichert", "Ergebnis" in grund, grund)
    p = os.path.join(TMP, "ergebnis.json")
    w.path = p
    w.save_model(); app.processEvents()
    check("… nach dem Speichern nicht mehr", not w.ungespeichert(), w.ungespeichert())


def test_rueckfrage():
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    with _Fragen(w, "abbrechen") as f:
        w.new_model(); app.processEvents()
        check("unverändert: Neu fragt nicht", f.gefragt == [] and w.model.nn == 0, str(f.gefragt))
    w.load_example("frame"); app.processEvents()
    w.model.add_node(5.0, 0.0, 0.0); w.refresh_all(); app.processEvents()
    nn = w.model.nn
    with _Fragen(w, "abbrechen") as f:
        w.new_model(); app.processEvents()
        check("geändert, Abbrechen: gefragt (Anlass Neu), Modell bleibt",
              len(f.gefragt) == 1 and f.gefragt[0][0] == "Neu" and w.model.nn == nn, str(f.gefragt))
        w.load_example("truss"); app.processEvents()
        check("… Beispiel öffnen fragt ebenso und bleibt stehen",
              len(f.gefragt) == 2 and "Beispiel" in f.gefragt[1][0] and w.model.nn == nn, str(f.gefragt[1:]))
        p_alt = os.path.join(TMP, "anderes.json")
        from statik3d.examples_lib import build_example
        build_example("truss").save(p_alt)
        from PySide6 import QtWidgets
        alt_dlg = QtWidgets.QFileDialog.getOpenFileName
        QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (p_alt, ""))
        try:
            w.open_model(); app.processEvents()
        finally:
            QtWidgets.QFileDialog.getOpenFileName = alt_dlg
        check("… Öffnen fragt ebenso (vor dem Dateidialog) und bleibt stehen",
              len(f.gefragt) == 3 and f.gefragt[2][0] == "Öffnen" and w.model.nn == nn, str(f.gefragt[2:]))
        w.close(); app.processEvents()
        check("… Beenden fragt, Abbrechen lässt das Fenster offen",
              len(f.gefragt) == 4 and f.gefragt[3][0] == "Beenden" and w.isVisible(), str(f.gefragt[3:]))
    with _Fragen(w, "verwerfen") as f:
        w.load_example("truss"); app.processEvents()
        check("Verwerfen: das Beispiel ersetzt das Modell",
              len(f.gefragt) == 1 and w.model.nn != nn and not w.ungespeichert(), str(w.model.nn))
    # Speichern mit Pfad: die Aenderung steht danach in der Datei
    p = os.path.join(TMP, "speichern.json")
    w.path = p
    w.model.add_node(7.0, 0.0, 0.0); w.refresh_all(); app.processEvents()
    nn2 = w.model.nn
    with _Fragen(w, "speichern") as f:
        w.new_model(); app.processEvents()
    from statik3d.model import Model
    gelesen = Model.load(p) if os.path.exists(p) else None
    check("Speichern: erst gespeichert (mit der Änderung), dann Neu",
          len(f.gefragt) == 1 and gelesen is not None and gelesen.nn == nn2 and w.model.nn == 0,
          f"{gelesen.nn if gelesen else None} / {nn2}")
    # Speichern ohne Pfad, Dateidialog abgebrochen: nichts geht verloren
    w.load_example("frame"); app.processEvents()
    w.model.add_node(8.0, 0.0, 0.0); w.refresh_all(); app.processEvents()
    nn3 = w.model.nn
    from PySide6 import QtWidgets
    alt_s = QtWidgets.QFileDialog.getSaveFileName
    QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
    try:
        with _Fragen(w, "speichern") as f:
            w.new_model(); app.processEvents()
    finally:
        QtWidgets.QFileDialog.getSaveFileName = alt_s
    check("Speichern, Dateidialog abgebrochen: Neu unterbleibt, das Modell bleibt",
          len(f.gefragt) == 1 and w.model.nn == nn3 and w.ungespeichert(), str(w.model.nn))
    # Testschalter: gesetzt, fragt nichts und antwortet wie verlangt
    os.environ["STATIK3D_UNGESPEICHERT"] = "abbrechen"
    gefragt = []
    w._frage_speichern_verwerfen = lambda a, g: (gefragt.append(a), "verwerfen")[1]
    try:
        w.new_model(); app.processEvents()
    finally:
        del w._frage_speichern_verwerfen
        os.environ["STATIK3D_UNGESPEICHERT"] = "verwerfen"
    check("Testschalter STATIK3D_UNGESPEICHERT=abbrechen: kein Fenster, Neu unterbleibt",
          gefragt == [] and w.model.nn == nn3, str(gefragt))
    w.new_model(); app.processEvents()
    check("Testschalter =verwerfen: Neu ohne Fenster, danach kein Stern",
          w.model.nn == 0 and not w.ungespeichert() and not _stern(w), w.windowTitle())
    # Oeffnen nach Verwerfen: das Modell der Datei ist nichts Ungespeichertes
    w.load_example("frame"); app.processEvents()
    w.model.add_node(8.0, 1.0, 0.0); w.refresh_all(); app.processEvents()
    p_auf = os.path.join(TMP, "oeffnen.json")
    from statik3d.examples_lib import build_example
    build_example("truss").save(p_auf)
    ok = w.modell_laden(p_auf); app.processEvents()
    check("Öffnen nach Verwerfen: kein Stern, nichts ungespeichert",
          ok and not w.ungespeichert() and not _stern(w), w.windowTitle())


def test_rueckfrage_fenster():
    """Das Fenster selbst: drei Knoepfe mit deutschen Verben, Esc = Abbrechen."""
    w, app = _fenster()
    from PySide6 import QtWidgets
    box, knoepfe = w._ungespeichert_box("Neu", "Änderungen am Modell")
    texte = {k: b.text() for k, b in knoepfe.items()}
    check("Rückfrage: Knöpfe Speichern / Verwerfen / Abbrechen",
          texte == {"speichern": "Speichern", "verwerfen": "Verwerfen", "abbrechen": "Abbrechen"}, str(texte))
    check("… Vorgabe Speichern, Esc heißt Abbrechen",
          box.defaultButton() is knoepfe["speichern"] and box.escapeButton() is knoepfe["abbrechen"])
    check("… der Text nennt den Anlass und das Modell", "Neu" in box.text() and "speichern" in box.text().lower(),
          box.text()[:80])
    box.deleteLater()
    # ein Fenster, das niemand beantwortet (Dialog-exec ersetzt): Abbrechen
    alt = QtWidgets.QMessageBox.exec
    QtWidgets.QMessageBox.exec = lambda self, *a, **k: 0
    try:
        antwort = w._frage_speichern_verwerfen("Neu", "Änderungen am Modell")
    finally:
        QtWidgets.QMessageBox.exec = alt
    check("… ohne Antwort gilt Abbrechen", antwort == "abbrechen", antwort)


def test_import_fragt():
    w, app = _fenster()
    from PySide6 import QtWidgets
    from statik3d.gui import main as G
    w.load_example("frame"); app.processEvents()
    w.model.add_node(4.0, 4.0, 0.0); w.refresh_all(); app.processEvents()
    nn = w.model.nn
    alt_open = QtWidgets.QFileDialog.getOpenFileName
    alt_dlg = G.ImportDialog

    class _Dlg:
        def __init__(self, *a, **k):
            self.append = type("_H", (), {"isChecked": lambda s: False})()
            self.members = type("_H", (), {"isChecked": lambda s: False})()

        def exec(self):
            return 1

        def options(self):
            return {}
    p = os.path.join(TMP, "import.json")
    open(p, "w").close()
    QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (p, ""))
    G.ImportDialog = _Dlg
    try:
        with _Fragen(w, "abbrechen") as f:
            w.import_file(); app.processEvents()
    finally:
        QtWidgets.QFileDialog.getOpenFileName = alt_open
        G.ImportDialog = alt_dlg
    check("Import, der das Modell ersetzt: Rückfrage, Abbrechen lässt das Modell stehen",
          len(f.gefragt) == 1 and "Import" in f.gefragt[0][0] and w.model.nn == nn, str(f.gefragt))


def test_beenden_waehrend_rechnung():
    from PySide6 import QtCore, QtWidgets
    from statik3d.gui.main import MainWindow
    _w0, app = _fenster()
    w = MainWindow()
    w.show(); app.processEvents()

    class _Rechnung(QtCore.QThread):
        def __init__(self):
            super().__init__()
            self.halt = False
            self.abbruch_angefordert = False

        def abbrechen(self):
            self.abbruch_angefordert = True
            self.halt = True

        def run(self):
            while not self.halt:
                self.msleep(5)
    r = _Rechnung()
    w.worker = r
    r.start()
    gefragt = []
    w._frage_rechnung_beenden = lambda: (gefragt.append(1), False)[1]
    w.close(); app.processEvents()
    check("Beenden während der Rechnung fragt; Nein: Fenster offen, Rechnung läuft",
          gefragt == [1] and w.isVisible() and r.isRunning())
    w._frage_rechnung_beenden = lambda: (gefragt.append(2), True)[1]
    w.close(); app.processEvents()
    check("… Ja: Abbruch angefordert", gefragt == [1, 2] and r.abbruch_angefordert)
    r.wait(3000)
    for _ in range(20):
        app.processEvents()
    check("… nach dem Anhalten schließt das Fenster", not w.isVisible() and not r.isRunning())
    box, b_ja = w._rechnung_beenden_box()
    texte = [b.text() for b in box.buttons()]
    check("… das Fenster fragt „Rechnung abbrechen und beenden?“ mit Verbknöpfen",
          "abbrechen und beenden" in box.text() and "Abbrechen und beenden" in texte
          and "Weiterrechnen" in texte, str(texte))
    box.deleteLater()
    w.deleteLater()


def test_beispiel_knopf():
    w, app = _fenster()
    from PySide6 import QtWidgets
    bsp = [b for b in w.ribbon.befehle if b.gruppe == "Beispiele"]
    check("acht Beispiele als Befehle (die Suche findet sie)", len(bsp) == 8, str([b.text for b in bsp]))
    knoepfe = [k for k in w.ribbon.findChildren(QtWidgets.QToolButton)
               if k.defaultAction() in [b.aktion for b in bsp]]
    check("… kein Beispiel hat mehr einen eigenen Knopf im Ribbon", not knoepfe, str(len(knoepfe)))
    menue = [k for k in w.ribbon.findChildren(QtWidgets.QToolButton) if k.text() == "Beispiel öffnen ▾"]
    aktionen = menue[0].menu().actions() if menue and menue[0].menu() else []
    check("ein Knopf „Beispiel öffnen ▾“ mit den acht Beispielen im Menü",
          len(menue) == 1 and [a.text() for a in aktionen] == [b.text for b in bsp],
          str([a.text() for a in aktionen]))
    w.new_model(); app.processEvents()
    aktionen[0].trigger(); app.processEvents()
    check("… ein Eintrag lädt das Beispiel", w.model.nn > 0, str(w.model.nn))


def test_modell_leeren():
    w, app = _fenster()
    texte = {(b.register, b.text) for b in w.ribbon.befehle}
    check("„Alle Elemente löschen“ heißt „Modell leeren (Eigenschaften behalten)…“",
          not any(t == "Alle Elemente löschen" for _r, t in texte)
          and any(t == "Modell leeren (Eigenschaften behalten)…" for _r, t in texte), "")
    check("… und steht nicht mehr im Register Netz",
          not any(r == "Netz" and t.startswith("Modell leeren") for r, t in texte),
          str([r for r, t in texte if t.startswith("Modell leeren")]))
    w.load_example("hall"); app.processEvents()
    ne, n_mat = len(w.model.elements), len(w.model.materials)
    gefragt = _knopf_fragen(w, False)
    w.clear_mesh(); app.processEvents()
    check("Modell leeren fragt; Abbrechen lässt alles stehen",
          len(gefragt) == 1 and len(w.model.elements) == ne, str(gefragt[:1])[:100])
    gefragt = _knopf_fragen(w, True)
    w.clear_mesh(); app.processEvents()
    check("… bestätigt: leer, Werkstoffe bleiben",
          len(w.model.elements) == 0 and len(w.model.materials) == n_mat and w.ungespeichert())
    check("… Rückgängig-Knopf nennt es", w.act_undo.toolTip().startswith("Rückgängig: Modell geleert"),
          w.act_undo.toolTip())
    w.undo(); app.processEvents()
    check("… und Rückgängig holt das Modell zurück", len(w.model.elements) == ne)
    # grosses Modell: keine Kopie, Rueckfrage sagt es
    w.MODELL_LEEREN_KOPIE_BIS = 5
    try:
        gefragt = _knopf_fragen(w, True)
        w.clear_mesh(); app.processEvents()
    finally:
        del w.MODELL_LEEREN_KOPIE_BIS
    check("großes Modell: die Rückfrage sagt „nicht rückgängig“, kein Rückgängig danach",
          len(gefragt) == 1 and "nicht rückgängig" in gefragt[0][1] and len(w.model.elements) == 0
          and not w.act_undo.isEnabled(), gefragt[0][1][:120] if gefragt else "")
    w.__dict__.pop("_fragen_knoepfe", None)


def test_modell_leeren_rueckfrage():
    """Gegenpruefung 25.09.2026: Enter leerte das Modell (Vorgabeknopf
    „Modell leeren“, auch ohne Rueckgaengig), und der Text verschwieg Stäbe
    mit Nachweis, Ermüdungslasten, Kontakte und ungespeicherte Ergebnisse."""
    w, app = _fenster()
    from PySide6 import QtCore
    from statik3d import solver
    from statik3d.model import Model
    w.__dict__.pop("_fragen_knoepfe", None)
    w.load_example("hall"); app.processEvents()
    ne = len(w.model.elements)
    for grenze in (None, 5):
        if grenze:
            w.MODELL_LEEREN_KOPIE_BIS = grenze
        prot = []
        _modal_taste(app, QtCore.Qt.Key_Return, prot)
        try:
            w.clear_mesh(); app.processEvents()
        finally:
            w.__dict__.pop("MODELL_LEEREN_KOPIE_BIS", None)
        art = "ohne Rückgängig" if grenze else "mit Rückgängig"
        check(f"Modell leeren ({art}), echtes Fenster + Enter: Vorgabe Abbrechen, das Modell bleibt",
              len(prot) == 1 and prot[0][1] == "Abbrechen" and len(w.model.elements) == ne,
              f"{[p[:2] for p in prot]}, Elemente {ne} -> {len(w.model.elements)}")
    prot = []
    n_l = len(w.model.supports)
    _modal_taste(app, QtCore.Qt.Key_Return, prot)
    w.clear_supports(); app.processEvents()
    check("Alle Lager löschen, echtes Fenster + Enter: die Lager bleiben",
          len(prot) == 1 and prot[0][1] == "Abbrechen" and len(w.model.supports) == n_l,
          f"{[p[:2] for p in prot]}")
    w.load_example("contact"); app.processEvents()
    gefragt = _knopf_fragen(w, False)
    w.clear_contact(); app.processEvents()
    check("Alle Kontakte löschen: Vorgabe Abbrechen", gefragt and gefragt[0][4] == "nein", str(gefragt[:1])[:80])
    w.clear_mesh(); app.processEvents()
    text = gefragt[-1][1] if len(gefragt) == 2 else ""
    check("Text nennt einseitige Lager und Spaltelemente", "einseitige Lager (1)" in text
          and "Spaltelemente (1)" in text, text[:160])
    w.load_example("gate"); app.processEvents()
    gefragt = _knopf_fragen(w, False)
    w.clear_mesh(); app.processEvents()
    text = gefragt[0][1] if gefragt else ""
    check("Text nennt Stäbe mit Nachweis und Ermüdungslasten",
          "Stäbe mit Nachweis (3)" in text and "Ermüdungslasten (1)" in text and gefragt[0][4] == "nein",
          text[:200])
    check("… ohne Rechnung kein Wort von Ergebnissen", "Ergebnis" not in text)
    an = solver.solve_all(w.model, design=False)
    w._bg_done(lambda r: w._solve_done("all", r), an); app.processEvents()
    w.clear_mesh(); app.processEvents()
    text = gefragt[-1][1] if len(gefragt) == 2 else ""
    check("ungespeicherte Ergebnisse: der Text sagt, dass sie verloren gehen",
          "nicht gespeichert" in text and "Rückgängig holt sie nicht" in text, text[-160:])
    w.__dict__.pop("_fragen_knoepfe", None)
    m = Model("Groß")
    m.nodes = np.zeros((158780, 3))
    text = w._leeren_text(m, True)
    check("Knotenzahl mit Leerzeichen gegliedert", "158 780 Knoten" in text, text[:80])


def test_kontakte_und_lager_loeschen():
    w, app = _fenster()
    texte = [b.text for b in w.ribbon.befehle]
    check("„Kontakt löschen“ heißt „Alle Kontakte löschen…“",
          "Alle Kontakte löschen…" in texte and "Kontakt löschen" not in texte)
    w.load_example("contact"); app.processEvents()
    m = w.model
    n_k = len(m.contact_supports) + len(m.gap_elements) + len(m.contact_pairs)
    gefragt = _knopf_fragen(w, False)
    w.clear_contact(); app.processEvents()
    n_k2 = len(m.contact_supports) + len(m.gap_elements) + len(m.contact_pairs)
    check("Alle Kontakte löschen fragt; Abbrechen lässt sie stehen",
          n_k > 0 and len(gefragt) == 1 and n_k2 == n_k, f"{n_k} -> {n_k2}")
    gefragt = _knopf_fragen(w, True)
    w.clear_contact(); app.processEvents()
    check("… bestätigt: gelöscht, Rückgängig nennt es",
          len(w.model.contact_supports) + len(w.model.gap_elements) + len(w.model.contact_pairs) == 0
          and w.act_undo.toolTip().startswith("Rückgängig: Kontakte gelöscht"), w.act_undo.toolTip())
    n_l = len(w.model.supports)
    gefragt = _knopf_fragen(w, False)
    w.clear_supports(); app.processEvents()
    check("Alle Lager löschen fragt; Abbrechen lässt sie stehen",
          n_l > 0 and len(gefragt) == 1 and len(w.model.supports) == n_l, str(gefragt[:1])[:80])
    gefragt = _knopf_fragen(w, True)
    w.clear_supports(); app.processEvents()
    check("… bestätigt: gelöscht und ungespeichert", len(w.model.supports) == 0 and w.ungespeichert())
    w.undo(); app.processEvents()
    check("… und rückgängig zu machen", len(w.model.supports) == n_l)
    # frisches Beispiel: kein voriger Rueckgaengig-Punkt, der die Lager schon
    # enthielte - die Pruefung darueber bestand auch ohne merken()
    w.load_example("frame"); app.processEvents()
    n_l = len(w.model.supports)
    _knopf_fragen(w, True)
    w.clear_supports(); app.processEvents()
    check("frisches Beispiel: Alle Lager löschen, Rückgängig nennt es und holt sie zurück",
          w.act_undo.toolTip().startswith("Rückgängig: Alle Knotenlager gelöscht"), w.act_undo.toolTip())
    w.undo(); app.processEvents()
    check("… die Lager sind wieder da", n_l > 0 and len(w.model.supports) == n_l, f"{n_l} / {len(w.model.supports)}")
    w.__dict__.pop("_fragen_knoepfe", None)


def test_rueckgaengig_knopf_nennt():
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    w._meta_setzen("projekt", "Probe"); app.processEvents()
    tip = w.act_undo.toolTip()
    check("der Knopf nennt den Schritt", tip.startswith("Rückgängig: Projektangabe Projekt"), tip)
    w._bestaetigen = lambda text: True
    try:
        w.auswahl_loeschen("unbekannt", ["a"]); app.processEvents()
    finally:
        del w._bestaetigen
    check("zurückgenommener Punkt: der Knopf nennt wieder den vorigen Schritt, nicht den verworfenen",
          w.act_undo.toolTip() == tip and "unbekannt" not in w.act_undo.toolTip(),
          f"{tip!r} -> {w.act_undo.toolTip()!r}")
    check("… mit Tastenkürzel", "Strg+Z" in tip or "Ctrl+Z" in tip, tip)


def test_befehlssuche():
    w, app = _fenster()
    rb = w.ribbon
    namen = [b.text for b in rb.finden("spiel")]
    check("Suche am Wortanfang: „spiel“ findet keine Beispiele",
          not any(b.gruppe == "Beispiele" for b in rb.finden("spiel")), str(namen[:6]))
    check("Synonym: „Import“ findet „Übernehmen“", "Übernehmen" in [b.text for b in rb.finden("Import")],
          str([b.text for b in rb.finden("Import")][:5]))
    kombi = [b.text for b in rb.finden("Kombination")]
    check("Synonym/Wortanfang: „Kombination“ findet EN 1990 und DIN 19704",
          "Kombinationen automatisch…" in kombi and "DIN 19704: Kombinationen" in kombi, str(kombi[:6]))
    check("„Überlagerung“ findet die Kombinationen",
          "Kombinationen automatisch…" in [b.text for b in rb.finden("Überlagerung")])
    check("Synonym: „Stellung“ findet „Stellung anlegen…“",
          "Stellung anlegen…" in [b.text for b in rb.finden("Stellung")])
    check("Treffer im Befehlsnamen zuerst: „berechnen“ -> „Berechnen“",
          rb.finden("berechnen")[0].text == "Berechnen")
    check("kein Treffer bleibt leer", rb.finden("gibtsnicht") == [])
    # Enter bei mehreren Treffern: nichts ausfuehren, Trefferliste zeigen
    w.load_example("frame"); app.processEvents()
    fp = _fingerabdruck(w.model)
    ausgeloest = []
    for b in rb.befehle:
        b.aktion.triggered.connect(lambda _c=False, t=b.text: ausgeloest.append(t))
    rb.suche.setText("Lager")
    rb._suche_ausfuehren(); app.processEvents()
    check("Enter bei mehreren Treffern: nichts ausgeführt, die Trefferliste erscheint",
          ausgeloest == [] and rb._vervollstaendigung.popup().isVisible()
          and rb._vervollstaendigung.completionCount() > 1,
          f"{ausgeloest} / {rb._vervollstaendigung.completionCount()}")
    rb._vervollstaendigung.popup().hide()
    # „Spiel“ lud frueher das Beispiel Rahmen (erster Treffer)
    w.load_example("hall"); app.processEvents()
    n_hall = w.model.nn
    rb.suche.setText("Spiel")
    rb._suche_ausfuehren(); app.processEvents()
    rb._vervollstaendigung.popup().hide()
    check("„Spiel“ + Enter lädt kein Beispiel mehr", w.model.nn == n_hall
          and not any(t in ("Rahmen", "Fachwerk") for t in ausgeloest), str(ausgeloest))
    # genau ein Treffer im Namen: ausfuehren
    ausgeloest.clear()
    rb.suche.setText("Projektangaben")
    rb._suche_ausfuehren(); app.processEvents()
    check("genau ein Treffer im Befehlsnamen: Enter führt ihn aus",
          ausgeloest == ["Projektangaben…"], str(ausgeloest))
    # modellersetzend / loeschend: nie direkt. Die Rueckfrage mit Knoepfen
    # ist ersetzt und stimmt zu: liefe ein Befehl doch, risse die Pruefung,
    # statt an einem modalen Fenster zu haengen (Gegenpruefung 25.09.2026)
    ausgeloest.clear()
    fp = _fingerabdruck(w.model)
    _knopf_fragen(w, True)
    try:
        for text in ("Neu", "Modell leeren", "Alle Kontakte löschen…", "Rahmen"):
            rb.suche.setText(text)
            rb._suche_ausfuehren(); app.processEvents()
            rb._vervollstaendigung.popup().hide()
    finally:
        w.__dict__.pop("_fragen_knoepfe", None)
    check("„Neu“, „Modell leeren“, „Alle Kontakte löschen…“, Beispiel: nie direkt aus der Suche",
          ausgeloest == [] and _fingerabdruck(w.model) == fp, str(ausgeloest))
    check("… das Register des Befehls steht vorn, die Statuszeile sagt warum",
          "Suche" in w.statusBar().currentMessage(), w.statusBar().currentMessage()[:90])
    # aus der Trefferliste gewaehlt: ein gewoehnlicher Befehl laeuft
    ausgeloest.clear()
    rb._liste_nachziehen("Projektangaben")
    eintrag = rb.anzeige(next(b for b in rb.befehle if b.text == "Projektangaben…"))
    rb._treffer_gewaehlt(eintrag); app.processEvents()
    check("aus der Trefferliste gewählt: der Befehl läuft", ausgeloest == ["Projektangaben…"], str(ausgeloest))
    ausgeloest.clear()
    rb._liste_nachziehen("Neu")
    eintrag = rb.anzeige(next(b for b in rb.befehle if b.text == "Neu"))
    rb._treffer_gewaehlt(eintrag); app.processEvents()
    check("… „Neu“ aus der Liste gewählt: läuft trotzdem nicht", ausgeloest == [], str(ausgeloest))
    rb._vervollstaendigung.popup().hide()
    # reine Ansichtsbefehle mit „löschen/leeren“ im Namen laufen aus der Suche
    # (bis zum 25.09.2026 gesperrt: „ersetzt oder löscht Modellinhalt“)
    befehle = {b.text: b for b in rb.befehle}
    ansicht = [t for t in ("Filter leeren", "Sonden löschen", "Messungen löschen") if t in befehle]
    check("„Filter leeren“, „Sonden löschen“, „Messungen löschen“ sind nicht gesperrt",
          len(ansicht) == 3 and not any(befehle[t].nicht_aus_suche() for t in ansicht), str(ansicht))
    check("… „Alle Kontakte löschen…“ bleibt gesperrt",
          "Alle Kontakte löschen…" in befehle and befehle["Alle Kontakte löschen…"].nicht_aus_suche())


def test_befehlssuche_tastatur():
    """Die Suche mit echten Tasten (Gegenpruefung 25.09.2026): Enter bei
    offener Liste ging erst ans Suchfeld, dann an die aktuelle Listenzeile -
    ein Befehl lief zweimal (Schalter blieb aus, zwei Schritte zurueck), bei
    mehreren Treffern lief die erste Zeile."""
    w, app = _fenster()
    from PySide6 import QtCore
    rb = w.ribbon
    w.load_example("frame"); app.processEvents()
    ausgeloest = []
    zaehler = []
    for b in rb.befehle:
        f = (lambda _c=False, t=b.text: ausgeloest.append(t))
        b.aktion.triggered.connect(f)
        zaehler.append((b.aktion, f))
    try:
        aktiv, offen = _tippen(w, app, "Lager")
        check("„Lager“ + Enter (mehrere Treffer): nichts ausgeführt, die Liste bleibt offen",
              aktiv and ausgeloest == [] and offen, f"Liste aktiv {aktiv}, {ausgeloest}, offen {offen}")
        vorher = w.act_kontakte.isChecked()
        ausgeloest.clear()
        aktiv, _o = _tippen(w, app, "Kontakte zeigen")
        check("„Kontakte zeigen“ + Enter: genau einmal ausgelöst, der Schalter ist umgelegt",
              aktiv and ausgeloest == ["Kontakte zeigen"] and w.act_kontakte.isChecked() != vorher,
              f"{ausgeloest}, {vorher} -> {w.act_kontakte.isChecked()}")
        if w.act_kontakte.isChecked() != vorher:
            w.act_kontakte.setChecked(vorher)
        for t in ("Schritt 1", "Schritt 2", "Schritt 3"):
            w._meta_setzen("projekt", t)
        n_undo = len(w._undo)
        ausgeloest.clear()
        _tippen(w, app, "Rückgängig")
        check("„Rückgängig“ + Enter nimmt genau einen Schritt zurück",
              ausgeloest == ["Rückgängig"] and len(w._undo) == n_undo - 1
              and w.model.meta.get("projekt") == "Schritt 2",
              f"{ausgeloest}, Stapel {n_undo} -> {len(w._undo)}, {w.model.meta.get('projekt')!r}")
        ausgeloest.clear()
        # eine Zeile unterhalb der ersten, deren Befehl aus der Suche laufen darf
        treffer = rb.finden("Lager")
        i = next(i for i, b in enumerate(treffer) if i > 0 and not b.nicht_aus_suche())
        _tippen(w, app, "Lager", runter=i + 1)
        check(f"{i + 1}x Pfeil runter + Enter führt genau die gewählte Zeile einmal aus",
              ausgeloest == [treffer[i].text], f"{ausgeloest} (erwartet {treffer[i].text!r})")
        ausgeloest.clear()
        _tippen(w, app, "Neu", taste=QtCore.Qt.Key_Enter)
        check("… „Neu“ + Enter (Zifferblock): nichts ausgeführt", ausgeloest == [], str(ausgeloest))
    finally:
        for a, f in zaehler:
            try:
                a.triggered.disconnect(f)
            except (RuntimeError, TypeError):
                pass
        w.ribbon.suche.clear()


def test_doppelklick_zweig():
    w, app = _fenster()
    from PySide6 import QtWidgets
    w.load_example("frame"); app.processEvents()
    modal = []
    alt = QtWidgets.QDialog.exec
    QtWidgets.QDialog.exec = lambda self, *a, **k: (modal.append(type(self).__name__), 0)[1]

    def finden(text):
        it = QtWidgets.QTreeWidgetItemIterator(w.baum)
        while it.value():
            if it.value().text(0) == text:
                return it.value()
            it += 1

    def doppel(text):
        item = finden(text)
        if item is None:
            return None
        w.baum.setCurrentItem(item)
        w.baum.itemDoubleClicked.emit(item, 0)
        app.processEvents()
        return getattr(getattr(w.maskenrand, "maske", None), "titel", "")
    try:
        fp = _fingerabdruck(w.model)
        titel = doppel("Stäbe mit Nachweis")
        check("Doppelklick „Stäbe mit Nachweis“: nichts angelegt, rechts „Neu: Stab …“",
              _fingerabdruck(w.model) == fp and len(w.model.members) == 0
              and str(titel).startswith("Neu: Stab"), str(titel))
        for text, erwartet in (("Werkstoffe", "Neu: Werkstoff"), ("Lastfälle", "Neu: Lastfall"),
                               ("Kombinationen", "Neu: Kombination"), ("Linien", "Neu: Linie")):
            modal.clear()
            titel = doppel(text)
            check(f"Doppelklick „{text}“: rechte Anlegemaske, nicht modal, nichts angelegt",
                  str(titel).startswith(erwartet) and not modal and _fingerabdruck(w.model) == fp,
                  f"{titel} {modal}")
        w.maskenrand.schliessen(); app.processEvents()
        n_b = len(w.model.bericht or [])
        titel = doppel("Bericht")
        check("Doppelklick „Bericht“: kein Berichtsbild", len(w.model.bericht or []) == n_b
              and _fingerabdruck(w.model) == fp, str(len(w.model.bericht or [])))
        modal.clear()
        doppel("Verformungsnachweise")
        check("Zweig ohne Anlegemaske („Verformungsnachweise“): kein modaler Dialog, nichts angelegt",
              not modal and _fingerabdruck(w.model) == fp, str(modal))
        n = w.model.nn
        doppel("Knoten")
        check("Doppelklick „Knoten“: kein Knoten angelegt", w.model.nn == n and _fingerabdruck(w.model) == fp)
    finally:
        QtWidgets.QDialog.exec = alt
    check("… nach allen Doppelklicks nichts ungespeichert", not w.ungespeichert(), w.ungespeichert())


def _laufende_rechnung():
    """Ein Rechenfaden, der laeuft, bis ``halt`` gesetzt wird."""
    from PySide6 import QtCore

    class _Rechnung(QtCore.QThread):
        def __init__(self):
            super().__init__()
            self.halt = False
            self.abbruch_angefordert = False

        def abbrechen(self):
            self.abbruch_angefordert = True
            self.halt = True

        def run(self):
            while not self.halt:
                self.msleep(5)
    return _Rechnung()


def test_waehrend_rechnung_kein_neues_modell():
    """Gegenpruefung 25.09.2026: bei unveraendertem Modell liefen Neu,
    Beispiel, Oeffnen und Import waehrend einer Rechnung ohne Rueckfrage -
    die Rechnung ging verloren, ihr Ergebnis traf das neue Modell. Der
    Testschalter steht dabei auf „verwerfen“ (tests/__init__.py): auch er
    darf das nicht erlauben."""
    w, app = _fenster()
    from PySide6 import QtWidgets
    from statik3d.gui import main as G
    os.environ["STATIK3D_UNGESPEICHERT"] = "verwerfen"
    w.load_example("gate"); app.processEvents()
    fp, name = _fingerabdruck(w.model), w.model.name
    check("Vorbereitung: nichts ungespeichert", not w.ungespeichert())
    r = _laufende_rechnung()
    alt_worker = w.worker
    w.worker = r
    r.start()
    dialoge = []
    alt_open = QtWidgets.QFileDialog.getOpenFileName
    alt_dlg = G.ImportDialog
    p = os.path.join(TMP, "waehrend.json")
    from statik3d.examples_lib import build_example
    build_example("truss").save(p)

    class _Dlg:
        def __init__(self, *a, **k):
            self.append = type("_H", (), {"isChecked": lambda s: False})()
            self.members = type("_H", (), {"isChecked": lambda s: False})()

        def exec(self):
            return 1

        def options(self):
            return {}
    QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (dialoge.append(1), (p, ""))[1])
    G.ImportDialog = _Dlg
    try:
        w.new_model(); app.processEvents()
        ok_neu = _fingerabdruck(w.model) == fp
        w.load_example("truss"); app.processEvents()
        ok_bsp = _fingerabdruck(w.model) == fp
        w.open_model(); app.processEvents()
        ok_auf = _fingerabdruck(w.model) == fp and not dialoge
        n_dlg = len(dialoge)
        w.import_file(); app.processEvents()
        ok_imp = _fingerabdruck(w.model) == fp
    finally:
        QtWidgets.QFileDialog.getOpenFileName = alt_open
        G.ImportDialog = alt_dlg
        r.abbrechen()
        r.wait(3000)
        w.worker = alt_worker
    check("Neu während der Rechnung: unterbleibt, das Modell bleibt", ok_neu and w.model.name == name)
    check("… Beispiel öffnen ebenso", ok_bsp)
    check("… Öffnen ebenso, ohne Dateidialog", ok_auf, f"{n_dlg} Dateidialoge")
    check("… Import (ersetzend) ebenso", ok_imp)
    check("… die Statuszeile sagt warum", "nach der Rechnung" in w.statusBar().currentMessage(),
          w.statusBar().currentMessage()[:90])


def test_fremdes_ergebnis_verworfen():
    """Zweite Sicherung: eine Rechnung, deren Modell inzwischen ersetzt ist,
    liefert kein Ergebnis an das neue Modell (vorher KeyError und fremde
    „ungespeicherte Ergebnisse“ am neuen Modell)."""
    w, app = _fenster()
    from statik3d import solver
    w.load_example("gate"); app.processEvents()
    an = solver.solve_all(w.model, design=False)
    w._rechnung_modellwechsel = w._modellwechsel      # wie _run_background beim Start
    w.load_example("frame"); app.processEvents()
    zeilen = w.log.toPlainText().count("FEHLER")
    w._bg_done(lambda r: w._solve_done("all", r), an); app.processEvents()
    check("Ergebnis zu einem ersetzten Modell: verworfen, kein Fehler, nichts ungespeichert",
          w.analysis is None and not w.ungespeichert() and w.log.toPlainText().count("FEHLER") == zeilen,
          w.ungespeichert())
    check("… das Protokoll sagt es", "Ergebnis verworfen" in w.log.toPlainText())
    an2 = solver.solve_all(w.model, design=False)
    w._rechnung_modellwechsel = w._modellwechsel
    w._bg_done(lambda r: w._solve_done("all", r), an2); app.processEvents()
    check("… zum offenen Modell kommt es an", w.analysis is not None and "Ergebnis" in w.ungespeichert())


def test_teilergebnis_ungespeichert():
    w, app = _fenster()
    import time
    from statik3d import solver
    w.load_example("frame"); app.processEvents()
    an = solver.solve_all(w.model, design=False)
    ex = type("_Ausnahme", (), {"teilanalyse": an})()
    alt = w.worker
    w.worker = type("_ProbeWorker", (), {"ausnahme": ex, "abbruch_angefordert": True})()
    w._rechnung_name = "Probe-Teillauf"
    w._rechnung_t0 = time.time()
    w._rechnet_gerade = True
    try:
        w._bg_abgebrochen(1.0); app.processEvents()
    finally:
        w.worker = alt
    check("Teilergebnis nach Abbruch gilt als ungespeichert", "Ergebnis" in w.ungespeichert() and _stern(w),
          w.ungespeichert())


def test_beschriftung_rueckgaengig():
    """Zusammenfuehrung Paket 3 + Paket 4 (25.09.2026): ein reiner
    Beschriftungsschritt (Lagername in der Tabelle) traegt im Rueckgaengig-
    Stapel wie jeder Schritt den Aenderungsstand. Rueckgaengig setzt den Stand
    zurueck UND behaelt die Ergebnisse - und damit auch deren Merker
    „ungespeichert“; erst ein Schritt, der die Ergebnisse verwirft, loescht ihn."""
    w, app = _fenster()
    from statik3d import solver
    from statik3d.gui.main import _Beschriftungsschritt
    w.load_example("frame"); app.processEvents()
    an = solver.solve_all(w.model, design=False)
    w._bg_done(lambda r: w._solve_done("all", r), an)
    app.processEvents()
    w.path = os.path.join(TMP, "beschriftung.json")
    w.save_model(); app.processEvents()
    check("gerechnet und gespeichert: nichts ungespeichert",
          w.analysis is not None and not w.ungespeichert(), w.ungespeichert())
    ok = w._lager_aendern(0, 2, "Fuß Probe")
    app.processEvents()
    e = w._undo[-1] if w._undo else ()
    check("Lagername in der Tabelle: Eintrag (was, modell, stand), als Beschriftung markiert",
          ok and len(e) == 3 and isinstance(e[0], _Beschriftungsschritt), repr(e[:1]) + f" {len(e)}")
    check("… Ergebnisse bleiben, das Modell ist geändert",
          w.analysis is not None and w.ungespeichert() == "Änderungen am Modell", w.ungespeichert())
    w.undo(); app.processEvents()
    check("Rückgängig der Beschriftung: Ergebnisse bleiben, Stand wieder „gespeichert“",
          w.analysis is not None and not w.ungespeichert() and not _stern(w), repr(w.ungespeichert()))
    r = w._redo[-1] if w._redo else ()
    check("… der Wiederholen-Eintrag ist dreiteilig und bleibt Beschriftung",
          len(r) == 3 and isinstance(r[0], _Beschriftungsschritt), f"{len(r)}")
    w.redo(); app.processEvents()
    check("Wiederholen: Ergebnisse bleiben, wieder ungespeichert",
          w.analysis is not None and w.ungespeichert() == "Änderungen am Modell", w.ungespeichert())
    w.undo(); app.processEvents()
    # frische, ungespeicherte Ergebnisse: Rueckgaengig einer Beschriftung
    # darf ihren Merker nicht loeschen
    an = solver.solve_all(w.model, design=False)
    w._bg_done(lambda r_: w._solve_done("all", r_), an)
    app.processEvents()
    w._lager_aendern(0, 2, "Fuß Probe 2"); app.processEvents()
    w.undo(); app.processEvents()
    check("ungespeicherte Ergebnisse: nach Rückgängig der Beschriftung weiter „ungespeichert“",
          w.analysis is not None and "Ergebnis" in w.ungespeichert(), repr(w.ungespeichert()))
    # ein rechnender Schritt verwirft die Ergebnisse samt Merker
    w.merken("Probe: rechnender Schritt")
    w.model.add_node(7.0, 7.0, 7.0)
    w.undo(); app.processEvents()
    check("Rückgängig eines rechnenden Schritts: Ergebnisse und ihr Merker verworfen",
          w.analysis is None and not w._ergebnis_ungespeichert, repr(w.ungespeichert()))


def test_speichern_ergebnis_scheitert():
    """Gegenpruefung 25.09.2026: scheiterte die Ergebnisdatei, galt alles als
    gespeichert - „Speichern“ in der Rueckfrage beendete danach ohne sie."""
    w, app = _fenster()
    from statik3d import ergebnisse as erg
    from statik3d import solver
    w.load_example("frame"); app.processEvents()
    an = solver.solve_all(w.model, design=False)
    w._bg_done(lambda r: w._solve_done("all", r), an); app.processEvents()
    w.path = os.path.join(TMP, "voll.json")
    alt = erg.schreiben

    def voll(*a, **k):
        raise OSError("Datenträger voll")
    erg.schreiben = voll
    # kein echter Dateidialog: ohne die Kur ginge „Neu“ unten durch, und das
    # letzte Speichern stuende ohne Pfad da - die Pruefung soll reissen, nicht haengen
    from PySide6 import QtWidgets
    alt_s = QtWidgets.QFileDialog.getSaveFileName
    QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
    try:
        ok = w.save_model(); app.processEvents()
        check("Ergebnisdatei gescheitert: save_model meldet False, Ergebnisse bleiben ungespeichert (Stern)",
              ok is False and "Ergebnis" in w.ungespeichert() and _stern(w), f"{ok} {w.ungespeichert()!r}")
        with _Fragen(w, "speichern") as f:
            w.new_model(); app.processEvents()
        check("… „Speichern“ in der Rückfrage vor Neu hält dann an, die Ergebnisse bleiben",
              len(f.gefragt) == 1 and w.analysis is not None and w.model.nn > 0)
    finally:
        erg.schreiben = alt
    try:
        ok = w.save_model(); app.processEvents()
    finally:
        QtWidgets.QFileDialog.getSaveFileName = alt_s
    check("… gelingt das Speichern, ist nichts mehr ungespeichert", ok is True and not w.ungespeichert())


def test_projektangabe_grosses_modell():
    """Projektangaben kopieren oberhalb PROJEKTANGABE_KOPIE_BIS nicht das
    ganze Modell (Drehlager: 11 s und Verdraengung der Rueckgaengig-Punkte)."""
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    n_undo = len(w._undo)
    w.PROJEKTANGABE_KOPIE_BIS = 5
    try:
        w._meta_setzen("projekt", "Großes Modell")
    finally:
        del w.PROJEKTANGABE_KOPIE_BIS
    check("großes Modell: kein Rückgängig-Punkt, aber ungespeichert",
          len(w._undo) == n_undo and w.ungespeichert() and w.model.meta.get("projekt") == "Großes Modell",
          f"Stapel {n_undo} -> {len(w._undo)}")


def test_rueckgaengig_wege():
    """Die Wege, die seit Paket 3 einen Rueckgaengig-Punkt anlegen: jeder
    nennt seinen Schritt und nimmt ihn zurueck - je auf einem frischen
    Beispiel, damit kein aelterer Punkt die Pruefung traegt."""
    w, app = _fenster()
    import copy
    from PySide6 import QtWidgets
    from statik3d.gui import main as G

    def frisch(bsp):
        w.load_example(bsp); app.processEvents()
        return w.model

    def geprueft(name, anfang, zustand, vorher):
        tip = w.act_undo.toolTip()
        w.undo(); app.processEvents()
        check(f"{name}: Rückgängig nennt „{anfang}“ und nimmt es zurück",
              tip.startswith("Rückgängig: " + anfang) and zustand() == vorher, f"{tip!r}")

    def lasten():
        lc = w.model.case()
        return sum(len(getattr(lc, a, []) or []) for a in ("nodal_loads", "beam_loads", "face_loads",
                                                          "temp_loads", "linienlasten"))
    m = frisch("frame")
    vorher = lasten()
    w.clear_loads(); app.processEvents()
    geprueft("Lasten löschen", "Lasten von", lasten, vorher)
    m = frisch("frame")
    n = len(m.supports)
    w.selection = np.array([m.supports[0].node])
    w.remove_support(); app.processEvents()
    geprueft("Lager entfernen", "Lager entfernt", lambda: len(w.model.supports), n)
    m = frisch("hall")
    namen = list(m.combinations)
    w.clear_combinations(); app.processEvents()
    geprueft("Alle Kombinationen löschen", "Alle Kombinationen gelöscht",
             lambda: list(w.model.combinations), namen)
    frisch("hall")
    w.refresh_all(); app.processEvents()
    w.tbl_comb.setCurrentCell(0, 0)
    w.remove_combination(); app.processEvents()
    geprueft("Kombination löschen", f"Kombination {namen[0]} gelöscht", lambda: list(w.model.combinations), namen)
    m = frisch("hall")
    w.tbl_comb.setCurrentCell(0, 0)
    neu = copy.deepcopy(m.combinations[namen[0]])
    neu.name = "KNEU"

    class _Dlg:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return 1

        def result(self):
            return neu
    alt = G.CombinationDialog
    G.CombinationDialog = _Dlg
    try:
        w.edit_combination(); app.processEvents()
    finally:
        G.CombinationDialog = alt
    geprueft("Kombination ändern", "Kombination KNEU", lambda: sorted(w.model.combinations), sorted(namen))
    m = frisch("gate")
    vorher = sorted(m.combinations)
    w.din19704_bilden(); app.processEvents()
    geaendert = sorted(w.model.combinations) != vorher
    geprueft("DIN 19704", "Kombinationen nach DIN 19704", lambda: sorted(w.model.combinations), vorher)
    check("… (DIN 19704 hat Kombinationen gebildet)", geaendert)
    w.new_model(); app.processEvents()
    m = w.model
    mat, sec = next(iter(m.materials)), next(iter(m.sections))
    k = [m.add_node(0, 0, 0), m.add_node(0, 0, 2), m.add_node(0.03, 0, 1), m.add_node(1, 0, 1)]
    m.add_element("beam", [k[0], k[1]], mat, sec)
    m.add_element("beam", [k[2], k[3]], mat, sec)
    w.refresh_all(); w._undo_init(); w._undo_knoepfe()
    n_el = len(m.elements)
    alt_d = QtWidgets.QInputDialog.getDouble
    QtWidgets.QInputDialog.getDouble = staticmethod(lambda *a, **k: (60.0, True))
    try:
        w.staebe_anschliessen(); app.processEvents()
    finally:
        QtWidgets.QInputDialog.getDouble = alt_d
    angeschlossen = len(w.model.elements) != n_el
    geprueft("Freie Stabenden anschließen", "Freie Stabenden angeschlossen",
             lambda: len(w.model.elements), n_el)
    check("… (ein Stabende wurde angeschlossen)", angeschlossen)


def test_weitere_wege():
    """Wege der Pruefliste, die in der Rueckgaengig-Pruefung nicht vorkommen:
    leere Punkte werden zurueckgenommen, Plastizitaet, Berichtsdialog und
    Browser vermerken die Aenderung (Gegenpruefung 25.09.2026: ohne Pruefung)."""
    w, app = _fenster()
    import types
    from statik3d.gui import main as G
    w.load_example("hall"); app.processEvents()
    w.auto_members(); app.processEvents()          # die Staebe gibt es schon
    check("Stäbe erkennen ohne neue Stäbe: kein Rückgängig-Punkt, nichts ungespeichert",
          len(w._undo) == 0 and not w.ungespeichert(), f"{len(w._undo)} {w.ungespeichert()!r}")
    w.load_example("plate"); app.processEvents()
    w.do_kerbfaelle(); app.processEvents()
    check("Kerbfälle ohne Vorschlag: kein Rückgängig-Punkt, nichts ungespeichert",
          len(w._undo) == 0 and not w.ungespeichert(), f"{len(w._undo)} {w.ungespeichert()!r}")
    w.cb_plast.setChecked(not w.cb_plast.isChecked())
    w._plast_uebernehmen(); app.processEvents()
    check("Plastizität umgeschaltet: ungespeichert", w.ungespeichert())
    w.cb_plast.setChecked(not w.cb_plast.isChecked())
    w.load_example("plate"); app.processEvents()

    class _Bericht:
        def __init__(self, *a, **k):
            self.path = types.SimpleNamespace(text=lambda: "")

        def exec(self):
            return 1

        def apply_meta(self, m):
            m.meta["projekt"] = "Aus dem Berichtsdialog"
    alt = G.ReportDialog
    G.ReportDialog = _Bericht
    try:
        w.make_report(); app.processEvents()
    finally:
        G.ReportDialog = alt
    check("Projektangabe aus dem Berichtsdialog: ungespeichert",
          w.model.meta.get("projekt") == "Aus dem Berichtsdialog" and w.ungespeichert())
    w.load_example("plate"); app.processEvents()
    alt = {k: w.__dict__[k] for k in ("web_state", "web_version") if k in w.__dict__}
    w.web_version = 0
    w.web_state = types.SimpleNamespace(version=1)
    try:
        w._web_poll(); app.processEvents()
    finally:
        for k in ("web_state", "web_version"):
            w.__dict__.pop(k, None)
        w.__dict__.update(alt)
    check("Änderung aus dem Browser: ungespeichert", w.ungespeichert())


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_merker_und_stern, test_ergebnis_ungespeichert, test_rueckfrage, test_rueckfrage_fenster,
              test_import_fragt, test_beispiel_knopf, test_modell_leeren, test_modell_leeren_rueckfrage,
              test_kontakte_und_lager_loeschen, test_rueckgaengig_knopf_nennt, test_befehlssuche,
              test_befehlssuche_tastatur, test_doppelklick_zweig, test_waehrend_rechnung_kein_neues_modell,
              test_fremdes_ergebnis_verworfen, test_teilergebnis_ungespeichert,
              test_speichern_ergebnis_scheitert, test_projektangabe_grosses_modell, test_rueckgaengig_wege,
              test_weitere_wege, test_beschriftung_rueckgaengig,
              test_beenden_waehrend_rechnung):
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
    sys.exit(main())
