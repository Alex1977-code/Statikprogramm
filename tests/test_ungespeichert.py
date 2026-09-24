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
    w._fragen_knoepfe = lambda titel, text, ja="Ja", nein="Abbrechen": (
        gefragt.append((titel, text, ja, nein)), antwort)[1]
    return gefragt


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
    check("Testschalter =verwerfen: Neu ohne Fenster", w.model.nn == 0)


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
    # modellersetzend / loeschend: nie direkt
    ausgeloest.clear()
    fp = _fingerabdruck(w.model)
    for text in ("Neu", "Modell leeren", "Alle Kontakte löschen…", "Rahmen"):
        rb.suche.setText(text)
        rb._suche_ausfuehren(); app.processEvents()
        rb._vervollstaendigung.popup().hide()
    check("„Neu“, „Modell leeren“, „Alle Kontakte löschen…“, Beispiel: nie direkt aus der Suche",
          ausgeloest == [] and _fingerabdruck(w.model) == fp, str(ausgeloest))
    check("… das Register des Befehls steht vorn, die Statuszeile sagt warum",
          "Suche" in w.statusBar().currentMessage(), w.statusBar().currentMessage()[:90])
    # aus der Trefferliste gewaehlt: ein gewoehnlicher Befehl laeuft
    ausgeloest.clear()
    eintrag = rb.anzeige(next(b for b in rb.befehle if b.text == "Projektangaben…"))
    rb._treffer_gewaehlt(eintrag); app.processEvents()
    check("aus der Trefferliste gewählt: der Befehl läuft", ausgeloest == ["Projektangaben…"], str(ausgeloest))
    ausgeloest.clear()
    eintrag = rb.anzeige(next(b for b in rb.befehle if b.text == "Neu"))
    rb._treffer_gewaehlt(eintrag); app.processEvents()
    check("… „Neu“ aus der Liste gewählt: läuft trotzdem nicht", ausgeloest == [], str(ausgeloest))


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


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_merker_und_stern, test_ergebnis_ungespeichert, test_rueckfrage, test_rueckfrage_fenster,
              test_import_fragt, test_beispiel_knopf, test_modell_leeren,
              test_kontakte_und_lager_loeschen, test_rueckgaengig_knopf_nennt, test_befehlssuche,
              test_doppelklick_zweig, test_beenden_waehrend_rechnung):
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
