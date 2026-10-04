"""
Hinweis statt Fehlerfenster (Plan-Paket 9b, 03.10.2026).

* ``hinweis(text)`` ist eine eigene Meldungsart fuer Bedienhinweise: fehlende
  Auswahl, ungueltige Eingabe, „gibt es schon“. Er oeffnet kein modales
  Fenster, sondern steht in der Statuszeile (gelb hinterlegt), in der
  Meldungszeile der offenen Maske (gelb) und im Protokoll mit „HINWEIS:“.
* Echte Fehler (Ausnahmen, Datei nicht lesbar, Rechnung gescheitert) kommen
  weiter mit ``error()`` als rotes Fenster „Fehler“, waehrend einer Rechnung als
  Protokollzeile (_modal_gesperrt).
* Die Stellen in offenen Masken und Tabellen melden mit ``hinweis()`` - eine
  Stichprobe aus verschiedenen Masken und Tabellen.
* Zusammenspiel mit dem Aenderungsmerker (Paket 13m): ein Hinweis waehrend
  „Übernehmen“ zaehlt wie ein Fehler - das „Übernehmen“ ist gescheitert, Maske,
  Punkt im Titel und Leiste bleiben stehen, der Wunsch wartet.
* Das gemeinsame Abfangmuster der Pruefungen (tests/meldungen.py) sieht beide
  Arten und wertet sie getrennt aus.
* Nachbesserung nach der Gegenpruefung (03.10.2026): der Hinweis bleibt
  waehrend einer Rechnung vorn in der Statuszeile (L1); ungueltige Eingaben
  der Objektmaske sind Hinweise, Programm- und Datenfehler bleiben Fehler
  (L2, S3); der Rueckbau ueberschreibt den Hinweis nicht (S1); in die
  Meldungszeile einer Maske kommt nur ihr eigener Hinweis (S2); jede
  Feldaenderung nimmt ihn weg (H1); der Rechtsklick meldet mit Hinweis (H2).

Aufruf:  python -m tests.test_hinweise
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
# Beispiel laden ohne die Rueckfrage „Ungespeicherte Änderungen“
os.environ["STATIK3D_UNGESPEICHERT"] = "verwerfen"
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_hinweise_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
#: modale Fenster, die sich oeffnen wollten: (Art, Text)
MODAL = []
PUNKT = "● "


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _modal_abfangen():
    """Jedes modale Fenster wird aufgezeichnet statt gezeigt. error() und
    hinweis() bleiben die echten Methoden des Fensters."""
    from PySide6 import QtWidgets
    B = QtWidgets.QMessageBox

    def melden(art, rueck):
        def f(*a, **_k):
            text = next((str(x) for x in a[2:3]), "")
            MODAL.append((art, text))
            return rueck
        return f
    B.critical = melden("critical", B.Ok)
    B.warning = melden("warning", B.Ok)
    B.information = melden("information", B.Ok)
    B.question = melden("question", B.No)
    QtWidgets.QDialog.exec = lambda self, *a, **k: (MODAL.append(("exec", type(self).__name__)), 0)[1]
    D = QtWidgets.QFileDialog
    D.getOpenFileName = staticmethod(lambda *a, **k: (MODAL.append(("datei", "öffnen")), ("", ""))[1])
    D.getSaveFileName = staticmethod(lambda *a, **k: (MODAL.append(("datei", "speichern")), ("", ""))[1])


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _modal_abfangen()
    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    app.processEvents()
    _FENSTER.update(w=w, app=app)
    return w, app


def _ruhe(app, n=3):
    for _ in range(n):
        app.processEvents()


def _halle(w, app):
    """Der Hallenrahmen, ohne Maske, Auswahl und Rueckgaengig-Schritte."""
    import numpy as np
    w.load_example("hall")
    _ruhe(app)
    _aufraeumen(w, app)
    w.selection = np.array([], dtype=int)
    w._undo.clear()
    w._redo.clear()
    MODAL.clear()


def _aufraeumen(w, app):
    leiste = getattr(w, "aenderungsleiste", None)
    if leiste is not None and leiste.isVisible():
        knopf = _knopf(w, "Verwerfen")
        if knopf is not None:
            knopf.click()
    w.maskenrand.schliessen()
    w._auswahl_leeren()
    _ruhe(app)


def _maske(w):
    return w.maskenrand.maske if w.maskenrand.offen() else None


def _titel(mk) -> str:
    lb = getattr(mk, "lbl_titel", None)
    return lb.text() if lb is not None else ""


def _leiste(w):
    leiste = getattr(w, "aenderungsleiste", None)
    return leiste if leiste is not None and leiste.isVisible() else None


def _knopf(w, text):
    from PySide6 import QtWidgets
    leiste = getattr(w, "aenderungsleiste", None)
    if leiste is None:
        return None
    return next((b for b in leiste.findChildren(QtWidgets.QPushButton) if b.text() == text), None)


def _druecken(w, app, text) -> bool:
    b = _knopf(w, text)
    if b is None or not b.isVisible():
        return False
    b.click()
    _ruhe(app)
    return True


def _neue_zeilen(w, vorher: str) -> list:
    return w.log.toPlainText()[len(vorher):].strip().splitlines()


def _meldungszeile(mk):
    """Text und Sichtbarkeit der Meldungszeile ueber den Knoepfen der Maske."""
    lb = getattr(mk, "lbl_zahlmeldung", None)
    if lb is None:
        return "", False, ""
    return lb.text(), lb.isVisible(), lb.styleSheet()


# ---------------------------------------------------------------------------
def test_hinweis_in_der_maske():
    from statik3d.gui import zahlenfeld as zf
    w, app = _fenster()
    _halle(w, app)
    w.maske_lager()
    _ruhe(app)
    mk = _maske(w)
    vorher = w.log.toPlainText()
    MODAL.clear()
    erg = mk.anwenden()             # ohne gewaehlte Knoten
    _ruhe(app)
    text = "Zuerst Knoten in der Ansicht wählen"
    check("Lager ohne Auswahl, „Lager setzen“: kein modales Fenster",
          not MODAL, str(MODAL))
    check("… die Statuszeile zeigt den Hinweis",
          text in w.statusBar().currentMessage(), repr(w.statusBar().currentMessage()))
    check("… die Statuszeile ist dabei gelb hinterlegt",
          "#fff6d0" in w.statusBar().styleSheet(), repr(w.statusBar().styleSheet()))
    t, sichtbar, stil = _meldungszeile(mk)
    check("… die Meldungszeile der Maske zeigt ihn, gelb",
          sichtbar and text in t and zf.GELB in stil, f"{t!r}, sichtbar {sichtbar}")
    neu = _neue_zeilen(w, vorher)
    check("… im Protokoll steht „HINWEIS: …“ (keine FEHLER-Zeile)",
          f"HINWEIS: {text}" in neu and not any(z.startswith("FEHLER") for z in neu), str(neu[-3:]))
    check("… „Übernehmen“ gilt als gescheitert, die Maske bleibt offen",
          erg is False and _maske(w) is mk, f"{erg!r}, {getattr(_maske(w), 'titel', None)!r}")
    # die naechste Meldung der Statuszeile nimmt das Gelb wieder weg
    w.statusBar().showMessage("Bereit")
    _ruhe(app)
    check("… eine andere Meldung der Statuszeile nimmt das Gelb wieder weg",
          "#fff6d0" not in w.statusBar().styleSheet(), repr(w.statusBar().styleSheet()))
    # das naechste „Übernehmen“ beginnt ohne den alten Hinweis
    import numpy as np
    w.selection = np.array([1], dtype=int)
    mk.setzen("d0", False)
    mk.setzen("d1", False)
    mk.setzen("d2", False)
    mk.anwenden()
    _ruhe(app)
    t, sichtbar, _stil = _meldungszeile(mk)
    check("… nächstes „Übernehmen“: nur noch der neue Hinweis („Kein Freiheitsgrad angekreuzt“)",
          sichtbar and t == "Kein Freiheitsgrad angekreuzt" and not MODAL, f"{t!r}, {MODAL}")
    _aufraeumen(w, app)


def test_hinweis_ohne_maske():
    w, app = _fenster()
    _halle(w, app)
    vorher = w.log.toPlainText()
    MODAL.clear()
    w.hinweis("Probehinweis ohne Maske")
    _ruhe(app)
    check("hinweis() ohne Maske: kein modales Fenster, Statuszeile und Protokoll",
          not MODAL and "Probehinweis ohne Maske" in w.statusBar().currentMessage()
          and "HINWEIS: Probehinweis ohne Maske" in _neue_zeilen(w, vorher),
          f"{MODAL}, {w.statusBar().currentMessage()!r}")
    # eine Tabelle: „Ändern“ im Register Stellungen ohne gewaehlte Zeile
    vorher = w.log.toPlainText()
    w.stellung_aendern()
    _ruhe(app)
    check("Tabelle Stellungen, „Ändern“ ohne Zeile: Hinweis ohne Fenster",
          not MODAL and "HINWEIS: Zuerst eine Stellung in der Liste wählen" in _neue_zeilen(w, vorher),
          f"{MODAL}, {_neue_zeilen(w, vorher)[-2:]}")


def test_fehler_bleibt_ein_fenster():
    w, app = _fenster()
    _halle(w, app)
    vorher = w.log.toPlainText()
    MODAL.clear()
    w.error("Probefehler")
    _ruhe(app)
    check("error(): das rote Fenster „Fehler“ kommt weiter, dazu die FEHLER-Zeile",
          ("critical", "Probefehler") in MODAL and "FEHLER: Probefehler" in _neue_zeilen(w, vorher),
          str(MODAL))
    # eine echte Fehlerstelle bleibt error(): ein Dokument fehlt
    MODAL.clear()
    w.open_doc("gibt_es_nicht_9b.md")
    _ruhe(app)
    check("eine echte Fehlerstelle (Dokument nicht gefunden) bleibt ein Fenster",
          any(a == "critical" and "Dokument nicht gefunden" in t for a, t in MODAL), str(MODAL))
    # waehrend einer Rechnung: weder Fehler noch Hinweis oeffnen ein Fenster
    MODAL.clear()
    w._rechnet_gerade = True
    try:
        vorher = w.log.toPlainText()
        w.hinweis("Hinweis während der Rechnung")
        w.error("Fehler während der Rechnung")
        _ruhe(app)
        neu = _neue_zeilen(w, vorher)
    finally:
        w._rechnet_gerade = False
    check("während einer Rechnung: kein modales Fenster, beide stehen im Protokoll",
          not MODAL and "HINWEIS: Hinweis während der Rechnung" in neu
          and "FEHLER: Fehler während der Rechnung" in neu, f"{MODAL}, {neu[-3:]}")


def test_stichprobe_umgestellter_stellen():
    """Mindestens zehn umgestellte Stellen aus verschiedenen Masken und
    Tabellen: jede meldet jetzt einen Hinweis, keinen Fehler, kein Fenster."""
    import numpy as np
    from PySide6 import QtCore
    from tests.meldungen import abfangen
    w, app = _fenster()
    _halle(w, app)
    faelle = []

    def fall(name, text, aufruf):
        _aufraeumen(w, app)
        w.selection = np.array([], dtype=int)
        MODAL.clear()
        m = abfangen(w)
        try:
            aufruf()
            _ruhe(app)
        finally:
            m.zurueck()
        ok = m.hinweis_mit(text) and not m.fehler and not MODAL
        faelle.append(ok)
        check(f"{name}: Hinweis „{text[:40]}“", ok, f"Hinweise {m.hinweise[:2]}, Fehler {m.fehler[:2]}, {MODAL}")

    def maske_und_uebernehmen(oeffnen, setzen=None, auswahl=None):
        def f():
            oeffnen()
            _ruhe(app)
            mk = _maske(w)
            for k, v in (setzen or {}).items():
                mk.setzen(k, v)
            if auswahl is not None:
                w.selection = np.array(auswahl, dtype=int)
            mk.anwenden()
        return f

    fall("Maske Lager (ohne Auswahl)", "Zuerst Knoten in der Ansicht wählen",
         maske_und_uebernehmen(w.maske_lager))
    fall("Maske Knotenlast (alles null)", "Alle Werte sind null",
         maske_und_uebernehmen(w.maske_knotenlast, auswahl=[1]))
    fall("Maske Knoten (Nummer 999)", "Nummer 999 gibt es nicht",
         maske_und_uebernehmen(lambda: w._objektmaske("knoten", "1"), {"nr": 999}))
    fall("Maske Lastfall (Name doppelt)", "Lastfall „S“ gibt es schon",
         lambda: w._eigenschaften_uebernehmen("lastfall", "LF1", {"name": "S"}))
    fall("Maske Kombination (Formel ohne Doppelpunkt)", "bitte als „Lastfall: Faktor“ schreiben",
         lambda: w._eigenschaften_uebernehmen("kombination", "GZT1", {"name": "GZT1", "faktoren": "LF1 1.35"}))
    fall("Maske Situation (ohne Namen)", "Bitte einen eigenen Namen für die Situation eingeben",
         lambda: w._situation_uebernehmen(None, {"name": ""}))
    fall("Maske Subsystem (ohne Namen)", "Bitte einen eigenen Namen für das Subsystem eingeben",
         lambda: w._subsystem_anlegen({"name": ""}))
    fall("Maske Linienlast (ohne Auswahl)", "Zuerst Stäbe oder Linien in der Ansicht wählen",
         lambda: w._linienlast_aufbringen({"qz": -1.0}))
    fall("Maske Temperaturlast (ΔT null)", "ΔT ist null",
         lambda: w._temperaturlast_aufbringen({"dT": 0.0, "dTz": 0.0}))
    fall("Maske Spiel (Spiel null)", "Spiel größer als null eintragen",
         lambda: w._spiel_anwenden({"spiel": "0"}, [], [], {}))
    fall("Maske Gelenk (Feder ohne Steifigkeit)", "Steifigkeit größer als null eingeben",
         lambda: w._eigenschaften_uebernehmen("gelenk", "G1", {"name": "G1", "typ0": "Feder", "k0": 0.0},
                                              True))

    def ohne_zeile(tbl):
        v = getattr(tbl, "view", tbl)
        v.setCurrentIndex(QtCore.QModelIndex())
        if hasattr(v, "clearSelection"):
            v.clearSelection()
    fall("Tabelle Lasten, „Löschen“ ohne Zeile", "Zuerst eine Zeile wählen",
         lambda: (ohne_zeile(w.tbl_last), w.last_loeschen()))
    fall("Tabelle Werkstoffe, „Löschen“ ohne Zeile", "Zuerst eine Zeile wählen",
         lambda: (ohne_zeile(w.tbl_mat), w._delete_row(w.tbl_mat, w.model.materials)))
    fall("Tabelle Beulfelder, „Ändern“ ohne Zeile", "Zuerst ein Beulfeld in der Tabelle wählen",
         lambda: (ohne_zeile(w.tbl_beul), w.edit_beulfeld()))
    fall("Tabelle Stellungen, „Entfernen“ ohne Zeile", "Zuerst eine Stellung in der Liste wählen",
         w.stellung_entfernen)

    def layer_doppelt():
        from statik3d.model import Layer
        for n in ("L9b_1", "L9b_2"):
            w.model.layer.setdefault(n, Layer(n))
        w.layer_umbenennen("L9b_1", "L9b_2")
    fall("Layerliste, Umbenennen auf einen vorhandenen Namen", "Layer „L9b_2“ gibt es schon",
         layer_doppelt)
    check("Stichprobe: mindestens zehn Stellen aus Masken und Tabellen melden einen Hinweis",
          sum(faelle) >= 10 and all(faelle), f"{sum(faelle)} von {len(faelle)}")
    _aufraeumen(w, app)


def test_13m_hinweis_laesst_alles_stehen():
    w, app = _fenster()
    _halle(w, app)
    # Knotenmaske, x geaendert, Nummer ungueltig - ueber die Leiste uebernommen
    w._objektmaske("knoten", "1")
    _ruhe(app)
    mk = _maske(w)
    x_alt = float(w.model.nodes[1][0])
    mk.setzen("x", 7.5)
    mk.setzen("nr", 999)
    _ruhe(app)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    check("Vorbereitung: geänderte Maske K1, die Leiste steht", _leiste(w) is not None and _maske(w) is mk,
          f"Leiste {_leiste(w) is not None}")
    schritte = len(w._undo)
    vorher = w.log.toPlainText()
    MODAL.clear()
    _druecken(w, app, "Übernehmen")
    neu = _neue_zeilen(w, vorher)
    check("„Übernehmen“ in der Leiste, die Maske weist mit einem Hinweis ab (kein Fenster)",
          not MODAL and any(z.startswith("HINWEIS: Nummer 999 gibt es nicht") for z in neu),
          f"{MODAL}, {neu[-2:]}")
    check("… Maske, Punkt im Titel und Leiste bleiben, der Wunsch (Knoten K2) wartet",
          _maske(w) is mk and _titel(mk).startswith(PUNKT) and _leiste(w) is not None
          and mk.titel == "Knoten K1", f"{getattr(_maske(w), 'titel', None)!r}, {_titel(mk)!r}")
    check("… das Modell ist unverändert, kein Rückgängig-Schritt",
          float(w.model.nodes[1][0]) == x_alt and len(w._undo) == schritte,
          f"x = {w.model.nodes[1][0]}, Schritte {schritte} -> {len(w._undo)}")
    _aufraeumen(w, app)

    # ein Handler, der nur hinweis() ruft - auch nach dem Schreiben
    def halb(werte):
        w.merken("halber Schritt")
        w.model.add_node(77.0, 0.0, 0.0)
        w.hinweis("simuliert: nach dem Schreiben mit einem Hinweis abgewiesen")
    w._maske_knoten_anlegen = halb
    try:
        w.maske_knoten()
        _ruhe(app)
        mk = _maske(w)
        mk.setzen("x", 1.0)
        _ruhe(app)
        nn, schritte = w.model.nn, len(w._undo)
        stand0 = w._fehlerstand()
        MODAL.clear()
        erg = mk.anwenden()
        _ruhe(app)
        check("Handler schreibt und weist dann mit hinweis() ab: gescheitert, Modell wie vorher",
              erg is False and w.model.nn == nn and len(w._undo) == schritte and not MODAL,
              f"{erg!r}, nn {nn} -> {w.model.nn}, Schritte {schritte} -> {len(w._undo)}, {MODAL}")
        check("… der Punkt im Titel bleibt, der Hinweis zählt im Fehlerzähler",
              _titel(mk) == PUNKT + mk.titel and w._fehlerstand() == stand0 + 1,
              f"{_titel(mk)!r}, Zähler {stand0} -> {w._fehlerstand()}")
    finally:
        del w._maske_knoten_anlegen
    _aufraeumen(w, app)


def test_abfangmuster():
    """tests/meldungen.py: beide Arten gemeinsam, getrennt auswertbar - eine
    alte Sammelliste bekommt beide, damit „nichts gemeldet“ streng bleibt."""
    from unittest import mock
    from tests.meldungen import abfangen, aus_attrappe
    w, app = _fenster()
    _halle(w, app)
    alt = []
    m = abfangen(w, alt)
    MODAL.clear()
    w.error("F1")
    w.hinweis("H1")
    m.zurueck()
    check("abfangen(): Fehler und Hinweis getrennt, die Sammelliste hat beide, kein Fenster",
          m.fehler == ["F1"] and m.hinweise == ["H1"] and alt == ["F1", "H1"] and not MODAL
          and m.hinweis_mit("H1") and not m.hinweis_mit("F1") and m.zuletzt_hinweis("H1"),
          f"{m!r}, {alt}, {MODAL}")
    check("… zurueck(): danach sind es wieder die Methoden des Fensters",
          "error" not in vars(w) and "hinweis" not in vars(w), str([k for k in ("error", "hinweis") if k in vars(w)]))
    s = mock.MagicMock()
    s.error("F2")
    s.hinweis("H2")
    a = aus_attrappe(s)
    check("aus_attrappe(): Fehler und Hinweise einer MagicMock-Attrappe",
          a.fehler == ["F2"] and a.hinweise == ["H2"], repr(a))


# ---------------------------------------------------------------------------
# Nachbesserung nach der Gegenpruefung (03.10.2026), je ein Fall
def test_l1_hinweis_waehrend_der_rechnung():
    """L1: Balken und Uhr schreiben die Statuszeile in Zehntelsekunden neu - ein
    frischer Hinweis bleibt bis zum Ablauf vorn stehen, gelb; das Protokoll
    springt nicht nach vorn."""
    import time
    w, app = _fenster()
    _halle(w, app)
    reiter = w.bottom_tabs.currentIndex()
    w._rechnet_gerade = True
    w._rechnung_t0 = time.time()
    w._rechnung_name = "Berechnung"
    try:
        w.hinweis("Probehinweis während der Rechnung")
        w._rechnung_fortschritt("Lastfall 3 von 7", 0.4)
        nach_fortschritt = w.statusBar().currentMessage()
        w._rechnung_tick()
        nach_tick = w.statusBar().currentMessage()
        w._fortschritt(None, "Vernetzen")
        nach_vernetzen = w.statusBar().currentMessage()
        gelb = "#fff6d0" in w.statusBar().styleSheet()
        check("Rechnung läuft: der Hinweis bleibt vorn, vor Fortschritt, Uhr und Vernetzen, gelb",
              all(t.startswith("Hinweis: Probehinweis während der Rechnung")
                  for t in (nach_fortschritt, nach_tick, nach_vernetzen))
              and "Lastfall 3 von 7" in nach_fortschritt and gelb and not MODAL,
              f"{nach_fortschritt!r} | {nach_tick!r} | {nach_vernetzen!r} | gelb {gelb}")
        check("… das Protokoll springt nicht nach vorn (der Reiter unten bleibt)",
              w.bottom_tabs.currentIndex() == reiter, f"{reiter} -> {w.bottom_tabs.currentIndex()}")
        w._hinweis_bis = time.time() - 1.0          # abgelaufen
        w._rechnung_fortschritt("Lastfall 4 von 7", 0.5)
        t = w.statusBar().currentMessage()
        check("… nach dem Ablauf steht wieder nur der Fortschritt, ohne Gelb",
              t.startswith("Berechnung: Lastfall 4 von 7") and "#fff6d0" not in w.statusBar().styleSheet(),
              repr(t))
    finally:
        w._rechnet_gerade = False
        w.progress_bar.setRange(0, 0)
        w.statusBar().clearMessage()
    # eine echte Rechnung im Hintergrund (Hallenrahmen): ihre Zeilen kommen auch
    # ueber info() - der Hinweis bleibt trotzdem vorn (gemessen: ohne den Schutz
    # war er nach 0,3 s weg)
    _halle(w, app)
    w._fragen_knoepfe = lambda *a, **k: True
    w.do_solve()
    _ruhe(app)
    lief = w._rechnet()
    w.tbl_stellung.setCurrentCell(-1, -1)
    w.stellung_aendern()            # Tabelle Stellungen ohne Zeile: Hinweis
    t0 = time.time()
    texte = []
    while time.time() - t0 < 3.0 or (w._rechnet() and time.time() - t0 < 60.0):
        app.processEvents()
        time.sleep(0.02)
        if not texte or texte[-1] != w.statusBar().currentMessage():
            texte.append(w.statusBar().currentMessage())
    ohne = [t for t in texte if not t.startswith("Hinweis: Zuerst eine Stellung in der Liste wählen")]
    check("Rechnung am Hallenrahmen: der Hinweis steht bis zum Ende vorn in jeder Zeile",
          lief and not w._rechnet() and len(texte) >= 2 and not ohne,
          f"lief {lief}, {len(texte)} Texte, ohne Hinweis {ohne[:2]}")


def test_l2_eingabefehler_als_hinweis():
    """L2: eine ungueltige Eingabe in der Objektmaske (Versatz, Stabknoten) ist
    ein Hinweis wie beim ψ des Lastfalls - kein rotes Fenster."""
    from tests.meldungen import abfangen
    w, app = _fenster()
    _halle(w, app)
    for feld, eingabe, text in (("ex_a", "1.000, 0", "1.000"), ("ex_a", "1; 2; 3", "2 Werte erwartet"),
                                ("kn", "0, 1, x", "„x“ ist keine ganze Zahl")):
        _aufraeumen(w, app)
        w._objektmaske("stabelement", "0")
        _ruhe(app)
        mk = _maske(w)
        vorher = list(w.model.elements[0].nodes), list(w.model.elements[0].exzentrizitaet or [])
        mk.setzen(feld, eingabe)
        MODAL.clear()
        m = abfangen(w)
        try:
            erg = mk.anwenden()
            _ruhe(app)
        finally:
            m.zurueck()
        nachher = list(w.model.elements[0].nodes), list(w.model.elements[0].exzentrizitaet or [])
        check(f"Stabelement „{feld}“ = „{eingabe}“: Hinweis ohne Fenster, Element unverändert",
              m.hinweis_mit(text) and not m.fehler and not MODAL and erg is False and nachher == vorher,
              f"Hinweise {m.hinweise[:1]}, Fehler {m.fehler[:1]}, {MODAL}, {erg!r}")
    _aufraeumen(w, app)
    from statik3d import zahlen as zl
    check("zahlen: der Eingabefehler ist ein ValueError (bisherige except ValueError fangen ihn)",
          issubclass(zl.Eingabefehler, ValueError) and isinstance(_wirft(zl.feldwert, "1.000"), zl.Eingabefehler)
          and isinstance(_wirft(zl.zahlenliste, "1, 2, 3", 2, "Versatz"), zl.Eingabefehler))


def _wirft(f, *a):
    try:
        f(*a)
    except Exception as ex:        # noqa: BLE001
        return ex
    return None


def test_s3_programmfehler_bleiben_fehler():
    """S3: Schweißnaht - eine mehrdeutige Zahl ist ein Hinweis, eine unbekannte
    Nahtart aus swn.kerbfall ein Fehler (Fenster)."""
    from statik3d.schweissnaehte import Schweissnaht
    from tests.meldungen import abfangen
    w, app = _fenster()
    _halle(w, app)
    MODAL.clear()
    m = abfangen(w)
    try:
        w._schweissnaht_anlegen({"name": "N9", "kf_vorgabe": "1.000"}, Schweissnaht("N9"))
    finally:
        m.zurueck()
    check("Schweißnaht, Kerbfall-Vorgabe „1.000“: Hinweis (Eingabe)",
          m.hinweis_mit("Eingabe", "1.000") and not m.fehler, f"{m!r}")
    MODAL.clear()
    w._schweissnaht_anlegen({"name": "N9", "art": "Quatschnaht"}, Schweissnaht("N9"))
    _ruhe(app)
    check("Schweißnaht, unbekannte Nahtart (aus swn.kerbfall): weiter das rote Fenster",
          any(a == "critical" and "Quatschnaht" in t for a, t in MODAL), str(MODAL))
    MODAL.clear()
    m = abfangen(w)
    try:
        w._netzeinstellungen_setzen({"nachbessern": "MMG3D (nicht installiert)"})
    finally:
        m.zurueck()
    check("Netzeinstellungen, nicht installierte Nachbesserung: Hinweis (Eingabe)",
          m.hinweis_mit("nicht installiert") and not m.fehler, f"{m!r}")


def test_s1_rueckbau_ueberschreibt_den_hinweis_nicht():
    """S1: geprueft wird vor merken - die Statuszeile behaelt den Hinweis; wo
    der Rueckbau doch laeuft, haengt sich sein Satz an."""
    w, app = _fenster()
    _halle(w, app)
    w.maske_temperaturlast()
    _ruhe(app)
    mk = _maske(w)
    schritte = len(w._undo)
    mk.anwenden()                   # ohne Auswahl, „alle Elemente“ nicht angekreuzt
    _ruhe(app)
    t = w.statusBar().currentMessage()
    check("Temperaturlast ohne Auswahl: die Statuszeile zeigt den Hinweis, kein Rückgängig-Schritt",
          "Zuerst Stäbe, Flächen oder Volumen wählen" in t and len(w._undo) == schritte, repr(t))
    _aufraeumen(w, app)
    w.model.add_punktmasse(0, 1.0)
    w.refresh_all()
    _ruhe(app)
    w._objektmaske("punktmasse", "0")
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("node", 999)
    schritte, n_pm = len(w._undo), len(w.model.punktmassen)
    mk.anwenden()
    _ruhe(app)
    t = w.statusBar().currentMessage()
    check("Punktmasse auf Knoten 999: Hinweis in der Statuszeile, nichts angelegt, kein Schritt",
          "Knoten 999 gibt es nicht" in t and len(w.model.punktmassen) == n_pm
          and w.model.punktmassen[0].node == 0 and len(w._undo) == schritte, repr(t))
    _aufraeumen(w, app)

    # ein Handler, der erst merkt und dann mit einem Hinweis abweist
    def halb(werte):
        w.merken("halber Schritt")
        w.model.add_node(77.0, 0.0, 0.0)
        w.hinweis("simuliert: nach dem Merken abgewiesen")
    w._maske_knoten_anlegen = halb
    try:
        w.maske_knoten()
        _ruhe(app)
        mk = _maske(w)
        mk.setzen("x", 1.0)
        mk.anwenden()
        _ruhe(app)
        t = w.statusBar().currentMessage()
        check("Rückbau nach einem Hinweis: der Satz hängt sich an, der Hinweis bleibt vorn und gelb",
              t.startswith("Hinweis: simuliert: nach dem Merken abgewiesen") and "nicht übernommen" in t
              and "#fff6d0" in w.statusBar().styleSheet(), repr(t))
    finally:
        del w._maske_knoten_anlegen
    _aufraeumen(w, app)


def test_s2_hinweis_nur_in_der_eigenen_maske():
    """S2: ein Hinweis aus einer Tabelle steht nicht in der Zeile einer fremden
    offenen Maske; der Hinweis eines Maskenknopfs steht in ihrer."""
    w, app = _fenster()
    _halle(w, app)
    w.maske_lager()
    _ruhe(app)
    mk = _maske(w)
    w.stellung_aendern()            # Tabelle Stellungen, keine Zeile gewählt
    _ruhe(app)
    t, sichtbar, _s = _meldungszeile(mk)
    check("Hinweis der Tabelle Stellungen bei offener Maske „Lager“: nicht in deren Meldungszeile",
          not sichtbar and "Stellung" not in t
          and "Zuerst eine Stellung in der Liste wählen" in w.statusBar().currentMessage(),
          f"{t!r}, sichtbar {sichtbar}")
    _aufraeumen(w, app)
    w._objektmaske("lager_einzeln", "0")
    _ruhe(app)
    mk = _maske(w)
    MODAL.clear()
    mk.zusatzknoepfe["Bettung übernehmen"].click()     # „Bettung“ steht auf „–“
    _ruhe(app)
    t, sichtbar, _s = _meldungszeile(mk)
    check("Knopf „Bettung übernehmen“ ohne Wahl: Hinweis in der Meldungszeile der eigenen Maske",
          sichtbar and "Erst „auf Beton“ oder „an Beton“ wählen" in t and not MODAL, f"{t!r}, {MODAL}")
    _aufraeumen(w, app)


def test_h1_feldaenderung_nimmt_den_hinweis():
    """H1: jede Aenderung in einem Feld nimmt den Hinweis aus der Meldungszeile -
    auch ein Haken, nicht nur ein Zahlenfeld, das seinen Zustand wechselt."""
    w, app = _fenster()
    _halle(w, app)
    w.maske_lager()
    _ruhe(app)
    mk = _maske(w)
    mk.anwenden()                   # ohne Auswahl: Hinweis
    _ruhe(app)
    vorher = _meldungszeile(mk)[1]
    mk.setzen("d3", True)           # ein Haken
    _ruhe(app)
    t, sichtbar, _s = _meldungszeile(mk)
    check("Hinweis in der Maske, dann einen Haken setzen: der Hinweis geht",
          vorher and not sichtbar, f"vorher {vorher}, nachher {t!r} sichtbar {sichtbar}")
    _aufraeumen(w, app)
    w.maske_knotenlast()
    _ruhe(app)
    mk = _maske(w)
    import numpy as np
    w.selection = np.array([1], dtype=int)
    mk.anwenden()                   # alles null: Hinweis
    _ruhe(app)
    vorher = _meldungszeile(mk)[1]
    mk._felder["Fz"].setText("-5")  # gültig nach gültig: der Zustand des Felds bleibt
    _ruhe(app)
    t, sichtbar, _s = _meldungszeile(mk)
    check("… ebenso eine gültige Zahl statt einer gültigen Zahl",
          vorher and not sichtbar, f"vorher {vorher}, nachher {t!r} sichtbar {sichtbar}")
    _aufraeumen(w, app)


def test_h2_rechtsklick_meldet_mit_hinweis():
    """H2: die Bedienhinweise des Rechtsklicks kommen als Hinweis."""
    from tests.meldungen import abfangen
    w, app = _fenster()
    _halle(w, app)
    m = abfangen(w)
    try:
        w._rechnet_gerade = True
        ok1 = w._eintrag_gilt(None)
        w._rechnet_gerade = False
        ok2 = w._eintrag_gilt(("anderer Stand",))
    finally:
        w._rechnet_gerade = False
        m.zurueck()
    check("Rechtsklick-Eintrag während der Rechnung und nach einer Modelländerung: je ein Hinweis",
          ok1 is False and ok2 is False and m.hinweis_mit("Rechnung läuft")
          and m.hinweis_mit("seit das Menü aufging") and not m.fehler, f"{m!r}")


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_hinweis_in_der_maske, test_hinweis_ohne_maske, test_fehler_bleibt_ein_fenster,
              test_stichprobe_umgestellter_stellen, test_13m_hinweis_laesst_alles_stehen,
              test_abfangmuster, test_l1_hinweis_waehrend_der_rechnung,
              test_l2_eingabefehler_als_hinweis, test_s3_programmfehler_bleiben_fehler,
              test_s1_rueckbau_ueberschreibt_den_hinweis_nicht,
              test_s2_hinweis_nur_in_der_eigenen_maske, test_h1_feldaenderung_nimmt_den_hinweis,
              test_h2_rechtsklick_meldet_mit_hinweis):
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
    code = main()
    sys.stdout.flush()
    # ohne Aufraeumen beenden: kein Fenster und keine Rueckfrage bleibt stehen
    os._exit(code)
