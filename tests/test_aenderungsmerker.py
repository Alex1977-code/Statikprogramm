"""
Aenderungsmerker je Maske (Plan-Paket 13m, 03.10.2026; Antwort 5 des Anwenders
vom 24.09.2026: eine nicht-modale Leiste, nicht automatisch uebernehmen).

* Hat die offene Maske nicht uebernommene Aenderungen, traegt ihr Titel vorn
  einen Punkt („● Knoten K1“). Er kommt beim ersten Aendern, geht, wenn der
  Stand wieder dem beim Oeffnen entspricht, nach „Übernehmen“ und mit der
  Maske. Reine Anzeigefelder (Anzahl, Kennwerte) zaehlen nicht.
* Jeder Weg, der eine geaenderte Maske ersetzen wuerde - Baumklick, Doppelklick,
  Rechtsklick → Neu, Ribbon, Register, Einzeltaste, Ergebnismaske nach der
  Rechnung -, geht ueber eine Stelle: statt still zu ersetzen steht oben rechts
  die Leiste „„Knoten K1“ hat nicht übernommene Änderungen | Übernehmen |
  Verwerfen“. „Übernehmen“ uebernimmt auf dem normalen Weg und fuehrt dann den
  Wunsch aus, „Verwerfen“ verwirft und fuehrt ihn aus, ohne Knopfdruck bleibt
  alles. Scheitert „Übernehmen“, bleibt alles stehen.
* Eine unveraenderte Maske wird ersetzt wie bisher, ohne Leiste.

Nachbesserung nach der Gegenpruefung (03.10.2026), je ein Fall:
F1 gelungen oder gescheitert wird entschieden, wenn der Handler zurueckkehrt,
   auch wenn er eine Ereignisschleife dreht (Wasserdruck mit Fortschritt);
   Ablehnung, Abbruch und Ausnahme gelten als gescheitert, ein halber Schritt
   wird zurueckgenommen, die Knotenmaske prueft vor dem Schreiben;
F2 der Wunsch baut die Maske neu (Einheiten, Lastfall umbenannt), und jeder
   Weg, der eine Maske baut, haelt vorher an (Quelltextpruefung);
F3 Tabelle, Doppelklick und Rechtsklick halten, bevor die Auswahl umgestellt wird;
F4 der Wunsch meint das Objekt: die Last, den Knoten nach einem Nummerntausch;
   gibt es es nicht mehr, oeffnet sich nichts;
F5 Rueckgaengig und Wiederholen sind bei einer geaenderten Maske gesperrt;
L1 Neu, Beispiel, Import und Beenden gehen ueber die Leiste, Loeschwege nennen die Maske;
L2 „Gilt für“ zaehlt als Aenderung, der Fingerabdruck nicht.

Zweite Nachbesserung (03.10.2026), test_r2_*: waehrend eines Uebernehmens ist
die Oberflaeche gesperrt (Fehler 3, 4), ein Rueckbau stellt den Stand vom Beginn
her (Fehler 1, 2), der Wunsch findet sein Objekt ueber stabile Schluessel
(Fehler 5); Rueckgaengig, Wiederholen und Browser bauen eine unveraenderte
Maske neu (Luecke 1), Mehrfachwahl im Baum (2), Browser bei geaenderter Maske
(3), „Modell leeren“ (4), Sammelmaske, Zuweisen und Strg+Klick (Schwaechen).

Aufruf:  python -m tests.test_aenderungsmerker
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
    tempfile.mkdtemp(prefix="statik3d_aenderungsmerker_"), "einstellungen.json")

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
    """Kein modales Fenster darf erscheinen - jedes wird aufgezeichnet. error()
    bleibt dabei die echte Methode des Fensters (sie zaehlt die Meldung)."""
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
        _FENSTER["w"].activateWindow()
        _FENSTER["app"].processEvents()
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _modal_abfangen()
    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    app.processEvents()
    w.activateWindow()
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
    """Der angezeigte Titel der Maske (Text der Titelzeile)."""
    from PySide6 import QtWidgets
    if mk is None:
        return ""
    lb = getattr(mk, "lbl_titel", None)
    if lb is None:
        lb = next((x for x in mk.findChildren(QtWidgets.QLabel) if x.objectName() == "maskentitel"), None)
    return lb.text() if lb is not None else ""


def _leiste(w):
    leiste = getattr(w, "aenderungsleiste", None)
    return leiste if leiste is not None and leiste.isVisible() else None


def _leistentext(w) -> str:
    leiste = _leiste(w)
    if leiste is None:
        return ""
    from PySide6 import QtWidgets
    return " ".join(x.text() for x in leiste.findChildren(QtWidgets.QLabel))


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


def _k1_geaendert(w, app, x=7.5):
    """Maske „Knoten K1“ offen, x geaendert (nicht uebernommen)."""
    w._objektmaske("knoten", "1")
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("x", x)
    _ruhe(app)
    return mk


def _ansicht(w, app):
    ia = w.plotter.interactor
    ia.setFocus()
    app.processEvents()
    return ia


def _befehl(w, register, text):
    return next((b for b in w.ribbon.befehle if b.register == register and b.text == text), None)


def _rechnen(w):
    from statik3d import solver
    return solver.solve_all(w.model, design=bool(w.model.members))


# ---------------------------------------------------------------------------
def test_punkt_im_titel():
    from PySide6 import QtCore, QtTest, QtWidgets
    w, app = _fenster()
    _halle(w, app)
    w._objektmaske("knoten", "1")
    _ruhe(app)
    mk = _maske(w)
    check("Frisch geöffnet: der Titel ohne Punkt („Knoten K1“)", mk is not None and _titel(mk) == mk.titel,
          repr(_titel(mk)))
    feld = mk._felder["x"]
    alt = feld.text()
    feld.setFocus()
    _ruhe(app)
    feld.selectAll()
    QtTest.QTest.keyClicks(feld, "7,5")
    _ruhe(app)
    check("Beim Tippen erscheint der Punkt vorn: „● Knoten K1“", _titel(mk) == PUNKT + mk.titel, repr(_titel(mk)))
    check("… das Tippen bleibt ungestört: Text, Schreibmarke und Fokus im Feld",
          feld.text() == "7,5" and feld.cursorPosition() == 3
          and QtWidgets.QApplication.focusWidget() is feld,
          f"{feld.text()!r}, {feld.cursorPosition()}, {type(QtWidgets.QApplication.focusWidget()).__name__}")
    check("… der Name der Maske bleibt ohne Punkt (Meldungen nennen ihn)", mk.titel == "Knoten K1", mk.titel)
    feld.selectAll()
    QtTest.QTest.keyClicks(feld, alt)
    _ruhe(app)
    check("Wieder der Stand beim Öffnen: der Punkt geht", _titel(mk) == mk.titel, repr(_titel(mk)))
    mk.setzen("benutzt", "etwas anderes")
    _ruhe(app)
    check("Ein Anzeigefeld (hängt an …), das sich ändert, setzt keinen Punkt", _titel(mk) == mk.titel,
          repr(_titel(mk)))
    # Uebernehmen auf dem normalen Weg
    mk.setzen("x", 7.5)
    _ruhe(app)
    mk.anwenden()
    _ruhe(app)
    neu = _maske(w)
    check("„Übernehmen“: der Wert steht im Modell, die Maske danach ohne Punkt",
          abs(float(w.model.nodes[1][0]) - 7.5) < 1e-9 and neu is not None and _titel(neu) == neu.titel,
          f"x = {w.model.nodes[1][0]}, {_titel(neu)!r}")
    # Anlegemaske, die offen bleibt
    w.maske_knoten()
    _ruhe(app)
    mk = _maske(w)
    nn = w.model.nn
    mk.setzen("x", 3.0)
    _ruhe(app)
    check("Anlegemaske „Knoten“: nach dem Tippen mit Punkt", _titel(mk) == PUNKT + mk.titel, repr(_titel(mk)))
    mk.anwenden()
    _ruhe(app)
    check("… „Anlegen“ legt an, die Maske bleibt offen und verliert den Punkt",
          w.model.nn == nn + 1 and _maske(w) is mk and _titel(mk) == mk.titel,
          f"{nn} -> {w.model.nn}, {_titel(mk)!r}")
    # Gescheitertes Uebernehmen: der Punkt bleibt
    w._objektmaske("stabelement", "0")
    _ruhe(app)
    mk = _maske(w)
    vorher = list(w.model.elements[0].nodes)
    MODAL.clear()
    mk.setzen("kn", "0, 0")
    _ruhe(app)
    mk.anwenden()
    _ruhe(app)
    # seit 9b/C14 ein Hinweis in der Statuszeile statt eines Fensters
    check("Gescheitertes „Übernehmen“ (Prüfung): Hinweis ohne Fenster, Punkt und Maske bleiben",
          "zwei verschiedene" in w.statusBar().currentMessage() and not MODAL and _maske(w) is mk
          and _titel(mk) == PUNKT + mk.titel and list(w.model.elements[0].nodes) == vorher,
          f"{MODAL}, {w.statusBar().currentMessage()!r}, {_titel(mk)!r}")
    # Abbrechen (die geaenderte Stabmaske vorher weg, sonst haelt sie „Neu“ an)
    _aufraeumen(w, app)
    w.baum.neu.emit("lastfaelle")
    _ruhe(app)
    mk = _maske(w)
    titel_neu = mk.titel if mk is not None else ""
    if mk is not None and "name" in mk._felder:
        mk.setzen("name", "Schnee")
        _ruhe(app)
    check("Neu: Lastfall - geändert mit Punkt", mk is not None and titel_neu.startswith("Neu:")
          and _titel(mk) == PUNKT + titel_neu, repr(_titel(mk)))
    if mk is not None:
        mk.abbrechen()
        _ruhe(app)
    check("… „Abbrechen“: Maske zu, keine Leiste, kein Lastfall „Schnee“",
          _maske(w) is None and _leiste(w) is None and "Schnee" not in w.model.load_cases)
    _aufraeumen(w, app)


def test_signal_direkt_ausgeloest():
    """Die Pruefungen loesen ``angewendet`` oft selbst aus statt ueber anwenden()
    (test_gui_smoke: 14 Stellen). Auch dann ist es der normale Weg: die Objektmaske,
    die sich im Handler neu oeffnet, haelt nicht an, und nach der Ereignisschleife
    gilt der Stand einer offen bleibenden Maske als uebernommen."""
    w, app = _fenster()
    _halle(w, app)
    mk = _k1_geaendert(w, app, x=4.5)
    mk.angewendet.emit(mk.werte())
    neu = _maske(w)
    check("angewendet.emit an „Knoten K1“: übernommen, die frische Maske steht, keine Leiste",
          abs(float(w.model.nodes[1][0]) - 4.5) < 1e-9 and neu is not None and neu is not mk
          and _leiste(w) is None, f"x = {w.model.nodes[1][0]}, Leiste {_leiste(w) is not None}")
    w.maske_knoten()
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("x", 2.0)
    _ruhe(app)
    mk.angewendet.emit(mk.werte())
    _ruhe(app)
    check("… an der Anlegemaske „Knoten“: sie bleibt offen, nach der Ereignisschleife ohne Punkt",
          _maske(w) is mk and _titel(mk) == mk.titel, repr(_titel(mk)))
    w.maske_stab()
    _ruhe(app)
    check("… die nächste Maske ersetzt sie ohne Leiste", getattr(_maske(w), "titel", "") == "Stab"
          and _leiste(w) is None, repr(getattr(_maske(w), "titel", None)))
    # Den Handler direkt rufen (test_gui_smoke: w._objekt_uebernehmen(..., mk.werte()))
    mk = _k1_geaendert(w, app, x=5.5)
    w._objekt_uebernehmen("knoten", "1", mk.werte(), False)
    _ruhe(app)
    neu = _maske(w)
    check("_objekt_uebernehmen direkt: übernommen, die frische Maske „Knoten K1“ steht, keine Leiste",
          abs(float(w.model.nodes[1][0]) - 5.5) < 1e-9 and neu is not mk and getattr(neu, "titel", "") == "Knoten K1"
          and _leiste(w) is None, f"x = {w.model.nodes[1][0]}, Leiste {_leiste(w) is not None}")
    w._objektmaske("knoten", "2")
    _ruhe(app)
    check("… die nächste Objektmaske (K2) kommt ohne Leiste", getattr(_maske(w), "titel", "") == "Knoten K2"
          and _leiste(w) is None, repr(getattr(_maske(w), "titel", None)))
    _aufraeumen(w, app)


def test_wege_zeigen_die_leiste():
    """Baumklick, Doppelklick, Rechtsklick → Neu, Ribbon, Register, Einzeltaste und
    die Ergebnismaske nach der Rechnung ersetzen eine geaenderte Maske nicht still."""
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    _halle(w, app)
    x_alt = float(w.model.nodes[1][0])

    def pruefen(name, tun):
        mk = _k1_geaendert(w, app)
        nn = w.model.nn
        MODAL.clear()
        tun()
        _ruhe(app)
        text = _leistentext(w)
        check(f"{name}: die geänderte Maske bleibt, oben rechts die Leiste",
              _maske(w) is mk and bool(mk.geaenderte_felder()) and _leiste(w) is not None,
              f"Maske {getattr(_maske(w), 'titel', None)!r}, Leiste {_leiste(w) is not None}")
        check(f"… sie nennt die Maske: „Knoten K1“ hat nicht übernommene Änderungen",
              "„Knoten K1“" in text and "nicht übernommene Änderungen" in text, repr(text))
        check(f"… mit „Übernehmen“ und „Verwerfen“, nichts im Modell geändert, kein modales Fenster",
              _knopf(w, "Übernehmen") is not None and _knopf(w, "Verwerfen") is not None
              and float(w.model.nodes[1][0]) == x_alt and w.model.nn == nn and not MODAL,
              f"x {w.model.nodes[1][0]}, nn {nn} -> {w.model.nn}, {MODAL}")
        _aufraeumen(w, app)

    pruefen("Baumklick auf Knoten K2", lambda: w.baum.angeklickt.emit("knoten", "2"))
    # (der Doppelklick auf einen Knoten oeffnet noch den modalen Knotendialog und
    # ersetzt keine Maske; der auf einen Lastfall oeffnet dessen Maske)
    fall = next(iter(w.model.load_cases))
    pruefen(f"Doppelklick im Baum auf Lastfall {fall}", lambda: w.baum.bearbeiten.emit("lastfall", fall))
    pruefen("Rechtsklick → Neu am Zweig Knoten (legt nichts an, solange die Leiste steht)",
            lambda: w.baum.neu.emit("knoten"))
    stab = _befehl(w, "Struktur", "Stab")
    check("Ribbon-Befehl „Struktur → Stab“ gefunden", stab is not None)
    if stab is not None:
        pruefen("Ribbon-Befehl „Stab“", stab.aktion.trigger)
    pruefen("Register „Lastfälle“ (maske_zeigen)", lambda: w.maske_zeigen("Lastfälle"))
    pruefen("„Bearbeiten“ im Register Auswahl oder im Rechtsklick (Sammelmaske K2, K3)",
            lambda: w.sammelmaske("knoten", [2, 3]))
    fall = w.model.active_case
    w.model.load_node(5, Fz=-1e3, case=fall)
    k_last = len(w.model.load_cases[fall].nodal_loads) - 1
    pruefen("Klick auf eine Last (Ansicht, Auswahlart Last, oder Lasttabelle)",
            lambda: w._last_waehlen(fall, "nodal_loads", k_last))

    def taste():
        ia = _ansicht(w, app)
        QtTest.QTest.keyClick(ia, K.Key_S)
    pruefen("Einzeltaste S in der Ansicht", taste)
    an = _rechnen(w)
    n_log = []

    def rechnung():
        n_log.append(len(w.log.toPlainText().splitlines()))
        w._solve_done("all", an)
    pruefen("Ergebnismaske nach der Rechnung (F5)", rechnung)
    neu = w.log.toPlainText().splitlines()[n_log[0]:] if n_log else []
    check("… das Protokoll sagt es: die Maske bleibt, Übernehmen oder Verwerfen zeigt die Ergebnisse",
          any("bleibt" in z and "Änderungen" in z and "Verwerfen" in z for z in neu), str(neu[-3:]))
    w.analysis = w.results = None
    _aufraeumen(w, app)


def test_uebernehmen_fuehrt_den_wunsch_aus():
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    _halle(w, app)
    mk = _k1_geaendert(w, app, x=8.25)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    schritte = len(w._undo)
    ok = _druecken(w, app, "Übernehmen")
    neu = _maske(w)
    check("Baumklick, dann „Übernehmen“: K1 hat x = 8,25 im Modell",
          ok and abs(float(w.model.nodes[1][0]) - 8.25) < 1e-9, f"x = {w.model.nodes[1][0]}")
    check("… über den normalen Weg: ein Rückgängig-Schritt „Knoten K1“",
          len(w._undo) == schritte + 1 and "Knoten K1" in str(w._undo[-1][0]),
          str([u[0] for u in w._undo[-2:]]))
    check("… danach der Wunsch: rechts die Maske „Knoten K2“, ohne Punkt, Leiste weg",
          neu is not None and neu.titel == "Knoten K2" and _titel(neu) == neu.titel and _leiste(w) is None,
          f"{getattr(neu, 'titel', None)!r}, Leiste {_leiste(w) is not None}")
    # Einzeltaste: der Befehl laeuft danach
    mk = _k1_geaendert(w, app, x=9.0)
    _ansicht(w, app)
    QtTest.QTest.keyClick(w.plotter.interactor, K.Key_S)
    _ruhe(app)
    _druecken(w, app, "Übernehmen")
    check("Taste S, dann „Übernehmen“: x übernommen, rechts die Maske „Stab“",
          abs(float(w.model.nodes[1][0]) - 9.0) < 1e-9 and getattr(_maske(w), "titel", "") == "Stab",
          f"x = {w.model.nodes[1][0]}, {getattr(_maske(w), 'titel', None)!r}")
    # Der letzte Wunsch gilt
    mk = _k1_geaendert(w, app, x=9.5)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    w._baum_geklickt("knoten", "3")
    _ruhe(app)
    check("Zwei Wünsche hintereinander: die Leiste bleibt eine", _leiste(w) is not None and _maske(w) is mk)
    _druecken(w, app, "Übernehmen")
    check("… „Übernehmen“ führt den letzten aus (Knoten K3)", getattr(_maske(w), "titel", "") == "Knoten K3",
          repr(getattr(_maske(w), "titel", None)))
    # Nach der Rechnung
    an = _rechnen(w)
    mk = _k1_geaendert(w, app, x=10.0)
    w._solve_done("all", an)
    _ruhe(app)
    _druecken(w, app, "Übernehmen")
    check("Nach der Rechnung, dann „Übernehmen“: x übernommen, rechts das Register Ergebnisse",
          abs(float(w.model.nodes[1][0]) - 10.0) < 1e-9 and _maske(w) is None
          and w.eingaben_dock.windowTitle() == "Ergebnisse" and _leiste(w) is None,
          f"x = {w.model.nodes[1][0]}, Dock {w.eingaben_dock.windowTitle()!r}")
    w.analysis = w.results = None
    _aufraeumen(w, app)


def test_baumklick_laesst_die_auswahl_stehen():
    """Eine Anlegemaske wirkt auf die Auswahl der Ansicht (Knotenlast auf die
    gewaehlten Knoten). Der Baumklick, der an der Leiste haelt, darf die Auswahl
    nicht vorher umstellen - sonst brachte „Übernehmen“ die Last auf den eben
    angeklickten Knoten."""
    w, app = _fenster()
    _halle(w, app)
    w._set_selection([3, 4])
    _ruhe(app)
    w.maske_knotenlast()
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("Fz", -10.0)
    _ruhe(app)
    fall = mk.werte().get("fall") or w.model.active_case
    vorher = [int(nl.node) for nl in w.model.load_cases[fall].nodal_loads]
    w.baum.angeklickt.emit("knoten", "7")
    _ruhe(app)
    check("Knotenlast geändert, Baumklick auf K7: Leiste, die Auswahl bleibt bei K3 und K4",
          _leiste(w) is not None and sorted(int(i) for i in w.selection) == [3, 4],
          f"Auswahl {sorted(int(i) for i in w.selection)}")
    _druecken(w, app, "Übernehmen")
    neu = [int(nl.node) for nl in w.model.load_cases[fall].nodal_loads]
    dazu = sorted(set(neu) - set(vorher))
    check("… „Übernehmen“: die Last kommt auf K3 und K4, nicht auf K7; danach die Maske „Knoten K7“",
          dazu == [3, 4] and getattr(_maske(w), "titel", "") == "Knoten K7",
          f"neu an {dazu}, {getattr(_maske(w), 'titel', None)!r}")
    _aufraeumen(w, app)


def test_verwerfen_fuehrt_den_wunsch_aus():
    w, app = _fenster()
    _halle(w, app)
    x_alt = float(w.model.nodes[1][0])
    mk = _k1_geaendert(w, app, x=12.0)
    stab = _befehl(w, "Struktur", "Stab")
    stab.aktion.trigger()
    _ruhe(app)
    schritte = len(w._undo)
    ok = _druecken(w, app, "Verwerfen")
    check("Ribbon „Stab“, dann „Verwerfen“: das Modell bleibt (x wie vorher, kein Schritt)",
          ok and float(w.model.nodes[1][0]) == x_alt and len(w._undo) == schritte,
          f"x = {w.model.nodes[1][0]}, Schritte {schritte} -> {len(w._undo)}")
    check("… danach der Wunsch: rechts die Maske „Stab“, Leiste weg",
          getattr(_maske(w), "titel", "") == "Stab" and _leiste(w) is None,
          repr(getattr(_maske(w), "titel", None)))
    # Ergebnisse bleiben beim Verwerfen
    an = _rechnen(w)
    mk = _k1_geaendert(w, app, x=12.0)
    w._solve_done("all", an)
    _ruhe(app)
    _druecken(w, app, "Verwerfen")
    check("Nach der Rechnung, dann „Verwerfen“: Ergebnisse bleiben, rechts das Register Ergebnisse",
          w.analysis is not None and _maske(w) is None and w.eingaben_dock.windowTitle() == "Ergebnisse"
          and float(w.model.nodes[1][0]) == x_alt, w.eingaben_dock.windowTitle())
    w.analysis = w.results = None
    _aufraeumen(w, app)
    # Eine neue Maske mit „Abbrechen“: Verwerfen nimmt das neue Objekt zurueck wie Abbrechen
    nn = w.model.nn
    w.baum.neu.emit("knoten")
    _ruhe(app)
    mk = _maske(w)
    check("Rechtsklick → Neu am Zweig Knoten: der Knoten steht, Maske „Neu: …“",
          w.model.nn == nn + 1 and mk is not None and mk.titel.startswith("Neu:"),
          f"{nn} -> {w.model.nn}, {getattr(mk, 'titel', None)!r}")
    if mk is not None:
        mk.setzen("x", 4.0)
        _ruhe(app)
        w.baum.angeklickt.emit("knoten", "2")
        _ruhe(app)
        _druecken(w, app, "Verwerfen")
    check("… geändert, Baumklick, „Verwerfen“: wie „Abbrechen“ - der neue Knoten ist wieder weg",
          w.model.nn == nn and getattr(_maske(w), "titel", "") == "Knoten K2",
          f"{w.model.nn} Knoten, {getattr(_maske(w), 'titel', None)!r}")
    _aufraeumen(w, app)


def test_gescheitertes_uebernehmen_laesst_alles_stehen():
    w, app = _fenster()
    _halle(w, app)
    x_alt = float(w.model.nodes[1][0])
    w._objektmaske("knoten", "1")
    _ruhe(app)
    mk = _maske(w)
    mk._felder["x"].setText("1,2,3")
    _ruhe(app)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    schritte = len(w._undo)
    _druecken(w, app, "Übernehmen")
    check("Ungültige Zahl, „Übernehmen“: die Maske K1 bleibt, die Leiste auch, der Wunsch wartet",
          _maske(w) is mk and _leiste(w) is not None and float(w.model.nodes[1][0]) == x_alt
          and len(w._undo) == schritte, f"{getattr(_maske(w), 'titel', None)!r}, Leiste {_leiste(w) is not None}")
    check("… die Maske sagt, was nicht stimmt (Meldungszeile wie bei ihrem eigenen Knopf)",
          mk.lbl_zahlmeldung.isVisible() and bool(mk.lbl_zahlmeldung.text()), mk.lbl_zahlmeldung.text())
    mk._felder["x"].setText("2,5")
    _ruhe(app)
    _druecken(w, app, "Übernehmen")
    check("… verbessert und noch einmal „Übernehmen“: übernommen, dann Knoten K2",
          abs(float(w.model.nodes[1][0]) - 2.5) < 1e-9 and getattr(_maske(w), "titel", "") == "Knoten K2",
          f"x = {w.model.nodes[1][0]}, {getattr(_maske(w), 'titel', None)!r}")
    # Pruefung im Fenster schlaegt fehl
    w._objektmaske("stabelement", "0")
    _ruhe(app)
    mk = _maske(w)
    vorher = list(w.model.elements[0].nodes)
    mk.setzen("kn", "0, 0")
    _ruhe(app)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    MODAL.clear()
    schritte = len(w._undo)
    _druecken(w, app, "Übernehmen")
    check("Prüfung schlägt fehl: Hinweis ohne Fenster, Stab, Maske und Leiste bleiben, kein Schritt",
          "zwei verschiedene" in w.statusBar().currentMessage() and not MODAL
          and _maske(w) is mk and _leiste(w) is not None
          and list(w.model.elements[0].nodes) == vorher and len(w._undo) == schritte,
          f"{MODAL}, {getattr(_maske(w), 'titel', None)!r}")
    _aufraeumen(w, app)


def test_unveraenderte_maske_ohne_leiste():
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    _halle(w, app)
    w._objektmaske("knoten", "1")
    _ruhe(app)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    check("Unverändert, Baumklick: Knoten K2 ersetzt K1, keine Leiste",
          getattr(_maske(w), "titel", "") == "Knoten K2" and _leiste(w) is None)
    _befehl(w, "Struktur", "Stab").aktion.trigger()
    _ruhe(app)
    check("Unverändert, Ribbon „Stab“: die Maske Stab, keine Leiste",
          getattr(_maske(w), "titel", "") == "Stab" and _leiste(w) is None)
    QtTest.QTest.keyClick(_ansicht(w, app), K.Key_K)
    _ruhe(app)
    check("Unverändert, Taste K: die Maske Knoten, keine Leiste",
          getattr(_maske(w), "titel", "") == "Knoten" and _leiste(w) is None)
    an = _rechnen(w)
    w._solve_done("all", an)
    _ruhe(app)
    check("Unverändert, nach der Rechnung: rechts das Register Ergebnisse, keine Leiste",
          _maske(w) is None and w.eingaben_dock.windowTitle() == "Ergebnisse" and _leiste(w) is None,
          w.eingaben_dock.windowTitle())
    w.analysis = w.results = None
    _aufraeumen(w, app)


def test_ohne_knopfdruck_bleibt_alles():
    from PySide6 import QtTest
    w, app = _fenster()
    _halle(w, app)
    mk = _k1_geaendert(w, app)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    feld = mk._felder["y"]
    feld.setFocus()
    feld.selectAll()
    QtTest.QTest.keyClicks(feld, "1,25")
    _ruhe(app)
    check("Leiste steht, in der Maske lässt sich weiter tippen", feld.text() == "1,25" and _leiste(w) is not None
          and _maske(w) is mk, feld.text())
    mk.setzen("x", float(w.model.nodes[1][0]))
    mk.setzen("y", float(w.model.nodes[1][1]))
    _ruhe(app)
    check("Wieder unverändert: die Leiste geht, die Maske K1 bleibt (der Wunsch verfällt)",
          _leiste(w) is None and _maske(w) is mk and _titel(mk) == mk.titel)
    mk.setzen("x", 6.0)
    _ruhe(app)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    mk.btn_anwenden.click()
    _ruhe(app)
    check("Übernehmen in der Maske selbst: die Leiste geht, der Wunsch verfällt (K1 steht wieder rechts)",
          _leiste(w) is None and getattr(_maske(w), "titel", "") == "Knoten K1"
          and abs(float(w.model.nodes[1][0]) - 6.0) < 1e-9, repr(getattr(_maske(w), "titel", None)))
    mk = _k1_geaendert(w, app, x=6.5)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    mk.btn_zu.click()
    _ruhe(app)
    check("✕ schließt die Maske: die Leiste geht mit", _leiste(w) is None and _maske(w) is None)
    _aufraeumen(w, app)


def test_ort_der_leiste():
    w, app = _fenster()
    _halle(w, app)
    an = _rechnen(w)
    w._solve_done("all", an)
    _ruhe(app)
    mk = _k1_geaendert(w, app)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    leiste = _leiste(w)
    platz = w.maskenplatz
    st = getattr(w, "ergebnissteuerung", None)
    i_l = platz.indexOf(leiste) if leiste is not None else -1
    i_m = platz.indexOf(mk)
    i_s = platz.indexOf(st) if st is not None else -1
    check("Die Leiste steht oben im rechten Bereich: unter der Ergebnissteuerung, über der Maske",
          leiste is not None and 0 <= i_s < i_l < i_m, f"Steuerung {i_s}, Leiste {i_l}, Maske {i_m}")
    if leiste is not None:
        y_l = leiste.mapTo(w, leiste.rect().topLeft()).y()
        y_m = mk.mapTo(w, mk.rect().topLeft()).y()
        check("… auch auf dem Bildschirm über der Maske, nicht breiter als der rechte Bereich",
              y_l < y_m and leiste.width() <= w.eingaben_dock.width(),
              f"y {y_l} < {y_m}, Breite {leiste.width()} <= {w.eingaben_dock.width()}")
        check("… sie bleibt dort oben stehen wie die Ergebnissteuerung (bleibt_oben)",
              bool(leiste.property("bleibt_oben")))
    w.analysis = w.results = None
    _aufraeumen(w, app)
    # ausgeblendeter rechter Bereich: die Maske ist nicht zu, nur nicht zu sehen
    mk = _k1_geaendert(w, app)
    w.eingaben_dock.hide()
    _ruhe(app)
    _befehl(w, "Struktur", "Stab").aktion.trigger()
    _ruhe(app)
    check("Rechter Bereich ausgeblendet: der Befehl hält trotzdem an, die Leiste holt den Bereich zurück",
          w.maskenrand.maske is mk and _leiste(w) is not None and w.eingaben_dock.isVisible(),
          f"Dock sichtbar {w.eingaben_dock.isVisible()}, Leiste {_leiste(w) is not None}")
    _aufraeumen(w, app)
    w.eingaben_dock.show()
    # 1366 x 768 mit einer langen Maske: die Leiste laesst das Fenster nicht wachsen
    w.resize(1366, 768)
    _ruhe(app)
    w._objektmaske("lager_einzeln", "0")
    _ruhe(app)
    mk = _maske(w)
    feld = next((n for n, f in mk._felder.items() if type(f).__name__ == "Zahlenfeld"), None) if mk else None
    if feld is not None:
        mk.setzen(feld, 0.125)
        _ruhe(app)
    h0 = w.height()
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    check("1366 × 768, Maske Knotenlager geändert: die Leiste erscheint, das Fenster wächst nicht",
          _leiste(w) is not None and w.height() <= h0 and _maske(w) is mk
          and not mk.btn_anwenden.visibleRegion().isEmpty(),
          f"{h0} -> {w.height()}, Maske {getattr(mk, 'titel', None)!r}")
    _aufraeumen(w, app)
    w.resize(1600, 1000)
    _ruhe(app)


def test_waehrend_der_rechnung():
    """Waehrend einer Rechnung oeffnet das Programm nichts Modales: die Leiste
    erscheint ohne Fenster, eine Fehlermeldung beim Uebernehmen geht ins
    Protokoll, und kein Knopf der Leiste startet eine Rechnung."""

    class _Laeuft:
        def isRunning(self):
            return True

    w, app = _fenster()
    _halle(w, app)
    alt = w.worker
    w.worker = _Laeuft()
    w._rechnet_gerade = True
    try:
        w._objektmaske("stabelement", "0")
        _ruhe(app)
        mk = _maske(w)
        mk.setzen("kn", "0, 0")
        _ruhe(app)
        MODAL.clear()
        w.baum.angeklickt.emit("knoten", "2")
        _ruhe(app)
        check("Rechnung läuft: der Baumklick zeigt die Leiste, kein modales Fenster",
              _leiste(w) is not None and _maske(w) is mk and not MODAL, str(MODAL))
        n_log = len(w.log.toPlainText().splitlines())
        _druecken(w, app, "Übernehmen")
        neu = w.log.toPlainText().splitlines()[n_log:]
        check("… „Übernehmen“ scheitert: die Meldung steht im Protokoll, kein Fenster, alles bleibt",
              not MODAL and any("zwei verschiedene" in z for z in neu) and _maske(w) is mk
              and _leiste(w) is not None, f"{MODAL}, {neu[-2:]}")
        _druecken(w, app, "Verwerfen")
        check("… „Verwerfen“: der Wunsch läuft (Knoten K2), keine neue Rechnung, kein Fenster",
              getattr(_maske(w), "titel", "") == "Knoten K2" and isinstance(w.worker, _Laeuft) and not MODAL,
              f"{getattr(_maske(w), 'titel', None)!r}, {type(w.worker).__name__}, {MODAL}")
    finally:
        w.worker = alt
        w._rechnet_gerade = False
    _aufraeumen(w, app)


def test_entf_nennt_die_maske_weiter():
    """Entf fragt ohnehin (modal): die Rueckfrage nennt die Maske, „Ja“ verwirft sie."""
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    import numpy as np
    w, app = _fenster()
    _halle(w, app)
    w.model.add_node(60.0, 0.0, 0.0)
    w.refresh_all()
    _ruhe(app)
    frei = w.model.nn - 1
    mk = _k1_geaendert(w, app)
    gestellt = []
    w._bestaetigen = lambda text: (gestellt.append(text), False)[1]
    try:
        w._auswahl_vergessen()
        w.selection = np.array([frei], dtype=int)
        QtTest.QTest.keyClick(_ansicht(w, app), K.Key_Delete)
        _ruhe(app)
        text = gestellt[0] if gestellt else ""
        check("Entf mit geänderter Maske: die Rückfrage nennt „Knoten K1“ und ihre Änderungen",
              "„Knoten K1“" in text and "nicht übernommene Änderungen" in text, text.replace("\n", " | "))
        check("… „Nein“: nichts gelöscht, Maske bleibt, keine Leiste (Entf fragt selbst)",
              w.model.nn == frei + 1 and _maske(w) is mk and _leiste(w) is None)
    finally:
        w.__dict__.pop("_bestaetigen", None)
    _aufraeumen(w, app)


def test_frische_masken_ohne_punkt():
    """Keine Maske darf schon beim Oeffnen als geaendert gelten - sonst stuende die
    Leiste bei jedem Klick. Durchlauf ueber den Modellbaum und die Anlegemasken."""
    from statik3d.gui import masken as msk
    w, app = _fenster()
    _halle(w, app)
    w.model.add_load_case("Wind", "W", activate=False)
    from statik3d.bridges.positions import Stellung
    w.model.stellungen.append(Stellung("S1", 0.0, "geschlossen"))
    w.refresh_all()
    _ruhe(app)
    schlecht, geprueft = [], 0
    eintraege = [w.baum._schluessel(it) for it in w.baum._alle_eintraege()]
    for art, name in eintraege:
        if not art:
            continue
        w.maskenrand.schliessen()
        _ruhe(app, 1)
        w._baum_geklickt(art, name)
        _ruhe(app, 2)
        mk = _maske(w)
        if isinstance(mk, msk.Maske):
            geprueft += 1
            if mk.geaenderte_felder() or _titel(mk) != mk.titel:
                schlecht.append(f"{art}/{name}: {sorted(mk.geaenderte_felder())}")
    for befehl in ("maske_knoten", "maske_stab", "maske_lager", "maske_knotenlast", "maske_linie",
                   "maske_schale", "maske_vorspannung", "maske_schnittebene", "maske_einheiten",
                   "maske_darstellung", "maske_netzeinstellungen", "maske_netzguete", "maske_elementuebersicht",
                   "maske_schweissnaht", "maske_temperaturlast", "bemassung_einstellungen", "subsystem_neu"):
        w.maskenrand.schliessen()
        getattr(w, befehl)()
        _ruhe(app, 2)
        mk = _maske(w)
        if isinstance(mk, msk.Maske):
            geprueft += 1
            if mk.geaenderte_felder() or _titel(mk) != mk.titel:
                schlecht.append(f"{befehl}: {sorted(mk.geaenderte_felder())}")
    check(f"{geprueft} frisch geöffnete Masken (Baum und Anlegemasken): keine mit Punkt",
          geprueft >= 20 and not schlecht and _leiste(w) is None, "; ".join(schlecht[:6]))
    _aufraeumen(w, app)


def test_merker_kostet_kein_neuzeichnen():
    """Der Merker rechnet nur bei Feldaenderungen, nicht in refresh_all und redraw;
    viele Aenderungen auf einmal (alle Lastfaelle anhaken) rechnen einmal."""
    from PySide6 import QtCore
    from statik3d.gui import masken as msk
    w, app = _fenster()
    _halle(w, app)
    for i in range(200):
        w.model.add_load_case(f"LF_{i}", "Q", activate=False)
    from statik3d.bridges.positions import Stellung
    w.model.stellungen.append(Stellung("S1", 0.0, "geschlossen"))
    w.refresh_all()
    _ruhe(app)
    w._objektmaske("stellung", "S1")
    _ruhe(app)
    mk = _maske(w)
    aufrufe = []
    alt = msk.Maske.geaenderte_felder

    def zaehlen(self):
        aufrufe.append(1)
        return alt(self)
    msk.Maske.geaenderte_felder = zaehlen
    try:
        w.refresh_all()
        w.redraw()
        _ruhe(app)
        check("refresh_all und redraw mit offener Maske: der Merker rechnet nicht mit", not aufrufe,
              f"{len(aufrufe)} Aufrufe")
        aufrufe.clear()
        cb = mk._felder.get("faelle_alle")
        if cb is not None:
            cb.setChecked(not cb.isChecked())
        _ruhe(app)
        check("„Alle Lastfälle anhaken“ (über 200 Haken): der Merker rechnet höchstens zweimal, Punkt da",
              cb is not None and 1 <= len(aufrufe) <= 2 and _titel(mk) == PUNKT + mk.titel,
              f"{len(aufrufe)} Aufrufe, {_titel(mk)!r}")
    finally:
        msk.Maske.geaenderte_felder = alt
    _aufraeumen(w, app)


# ---------------------------------------------------------------------------
# Nachbesserung nach der Gegenpruefung (03.10.2026)
# ---------------------------------------------------------------------------
def _wasserdruck(w, app):
    """Ein Wasserdruck WD1 auf einer Flaeche FA (wie szenarien3.py der Gegenpruefung)."""
    from statik3d.wasserdruck import Wasserdruck
    m = w.model
    k = [m.add_node(*xyz) for xyz in ((0, 2, 0), (5, 2, 0), (5, 2, 3), (0, 2, 3))]
    m.add_line("LA1", [k[0], k[1]]); m.add_line("LA2", [k[1], k[2]])
    m.add_line("LA3", [k[2], k[3]]); m.add_line("LA4", [k[3], k[0]])
    m.add_flaeche("FA", ["LA1", "LA2", "LA3", "LA4"])
    m.wasserdruecke["WD1"] = Wasserdruck("WD1", flaechen=["FA"], h_ow=3.0)
    w.refresh_all()
    _ruhe(app)


def test_f1_entscheidung_nach_dem_handler():
    """Der Handler dreht eine Ereignisschleife (Fortschritt): bis d07b48f lief
    dort die 0-ms-Uhr, und ein gescheitertes Übernehmen galt als gelungen."""
    import statik3d.wasserdruck as wdm
    from statik3d import stroemung as strm
    w, app = _fenster()
    alt = wdm.lasten_erzeugen
    for art, titel in (("fehler", "Rechnung scheitert (Fehlermeldung)"),
                       ("abbruch", "Anwender bricht den Fortschritt ab")):
        _halle(w, app)
        _wasserdruck(w, app)
        w.maske_wasserdruck("WD1")
        _ruhe(app)
        mk = _maske(w)
        mk.setzen("h_ow", 4.5)
        _ruhe(app)
        w.baum.angeklickt.emit("knoten", "2")
        _ruhe(app)
        schleifen = []

        def ersatz(m, wd, fortschritt=None, art=art):
            from PySide6 import QtWidgets
            for _ in range(3):                  # wie der Fortschritt: die Ereignisschleife dreht
                QtWidgets.QApplication.processEvents()
                schleifen.append(1)
            if fortschritt is not None:
                fortschritt(0.5, "halb")
            if art == "fehler":
                raise ValueError("simuliert: Strömungsrechnung gescheitert")
            raise strm.Abgebrochen()
        wdm.lasten_erzeugen = ersatz
        try:
            _druecken(w, app, "Übernehmen")
        finally:
            wdm.lasten_erzeugen = alt
        check(f"{titel} über die Leiste (die Schleife drehte {len(schleifen)}-mal): Maske, Punkt und Leiste "
              "bleiben, kein Wunsch, h_ow unverändert",
              _maske(w) is mk and _titel(mk) == PUNKT + mk.titel and _leiste(w) is not None
              and w.model.wasserdruecke["WD1"].h_ow == 3.0 and len(schleifen) == 3,
              f"rechts {getattr(_maske(w), 'titel', None)!r}, Leiste {_leiste(w) is not None}, "
              f"h_ow {w.model.wasserdruecke['WD1'].h_ow}")
        _aufraeumen(w, app)
    # derselbe Weg ueber den eigenen Knopf: anwenden() sagt False, der Punkt bleibt
    _halle(w, app)
    _wasserdruck(w, app)
    w.maske_wasserdruck("WD1")
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("h_ow", 4.5)
    _ruhe(app)

    def abbruch(m, wd, fortschritt=None):
        from PySide6 import QtWidgets
        QtWidgets.QApplication.processEvents()
        raise strm.Abgebrochen()
    wdm.lasten_erzeugen = abbruch
    try:
        erg = mk.anwenden()
        _ruhe(app)
    finally:
        wdm.lasten_erzeugen = alt
    check("Abbruch über den eigenen Knopf: anwenden() = False, der Punkt bleibt",
          erg is False and _titel(mk) == PUNKT + mk.titel, f"{erg!r}, {_titel(mk)!r}")
    _aufraeumen(w, app)
    # umbenannt und abgebrochen: der alte Wasserdruck war vor der Rechnung schon
    # geloescht - danach steht er wieder da, und kein halber Schritt bleibt
    _halle(w, app)
    _wasserdruck(w, app)
    w.maske_wasserdruck("WD1")
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("name", "WD2")
    _ruhe(app)
    schritte = len(w._undo)
    wdm.lasten_erzeugen = abbruch
    try:
        erg = mk.anwenden()
        _ruhe(app)
    finally:
        wdm.lasten_erzeugen = alt
    check("Umbenannt und abgebrochen: WD1 steht wieder im Modell, WD2 nicht, kein Rückgängig-Schritt",
          erg is False and "WD1" in w.model.wasserdruecke and "WD2" not in w.model.wasserdruecke
          and len(w._undo) == schritte, f"{sorted(w.model.wasserdruecke)}, Schritte {schritte} -> {len(w._undo)}")
    _aufraeumen(w, app)


def test_f1_ausnahme_und_halber_schritt():
    w, app = _fenster()
    _halle(w, app)
    # eine Ausnahme im Handler (S2 der Gegenpruefung)

    def kaputt(_werte):
        raise TypeError("simulierter Programmfehler")
    w._maske_knoten_anlegen = kaputt
    try:
        w.maske_knoten()
        _ruhe(app)
        mk = _maske(w)
        mk.setzen("x", 3.25)
        _ruhe(app)
        w.baum.angeklickt.emit("knoten", "2")
        _ruhe(app)
        MODAL.clear()
        nn = w.model.nn
        _druecken(w, app, "Übernehmen")
        check("Ausnahme im Handler: gilt als gescheitert - Maske und Leiste bleiben, Meldung, kein Wunsch",
              _maske(w) is mk and _leiste(w) is not None and w.model.nn == nn
              and any("simulierter Programmfehler" in t for _a, t in MODAL), str(MODAL[-1:]))
    finally:
        del w._maske_knoten_anlegen
    _aufraeumen(w, app)
    # ein Handler, der erst schreibt und dann ablehnt: kein halber Zustand

    def halb(werte):
        w.merken("halber Schritt")
        w.model.add_node(77.0, 0.0, 0.0)
        w.error("simuliert: nach dem Schreiben abgelehnt")
    w._maske_knoten_anlegen = halb
    try:
        w.maske_knoten()
        _ruhe(app)
        mk = _maske(w)
        mk.setzen("x", 1.0)
        _ruhe(app)
        nn, schritte = w.model.nn, len(w._undo)
        erg = mk.anwenden()
        _ruhe(app)
        check("Handler schreibt und lehnt dann ab: das Modell ist wie vorher, kein Rückgängig-Schritt bleibt",
              erg is False and w.model.nn == nn and len(w._undo) == schritte and _titel(mk) == PUNKT + mk.titel,
              f"{erg!r}, nn {nn} -> {w.model.nn}, Schritte {schritte} -> {len(w._undo)}")
    finally:
        del w._maske_knoten_anlegen
    _aufraeumen(w, app)
    # Knotenmaske: x geaendert, Nummer ungueltig (U3) - erst pruefen, dann schreiben
    mk = _k1_geaendert(w, app, x=11.0)
    mk.setzen("nr", 999)
    _ruhe(app)
    schritte = len(w._undo)
    erg = mk.anwenden()
    _ruhe(app)
    check("Knotenmaske, Nummer 999 ungültig: x bleibt im Modell unverändert, kein Schritt",
          erg is False and float(w.model.nodes[1][0]) == 0.0 and len(w._undo) == schritte,
          f"x = {w.model.nodes[1][0]}, Schritte {schritte} -> {len(w._undo)}")
    _aufraeumen(w, app)


def test_f2_wunsch_baut_neu():
    from statik3d import einheiten as eh
    w, app = _fenster()
    _halle(w, app)
    # Einheiten (S3): die zweite Maske entsteht nach dem Übernehmen
    w.act_einheiten.trigger()
    _ruhe(app)
    mk = _maske(w)
    alt = w.model.einheiten.kraft
    neu = next(x for x in eh.WAHL["kraft"] if x != alt)
    mk.setzen("kraft", neu)
    _ruhe(app)
    w.act_einheiten.trigger()
    _ruhe(app)
    _druecken(w, app, "Übernehmen")
    mk2 = _maske(w)
    check(f"Ribbon „Einheiten“ wartet, „Übernehmen“: die neue Maske zeigt die übernommene Kraft ({neu})",
          w.model.einheiten.kraft == neu and mk2 is not None and mk2 is not mk and mk2.werte().get("kraft") == neu,
          f"Modell {w.model.einheiten.kraft}, Maske {mk2.werte().get('kraft') if mk2 else None}")
    _aufraeumen(w, app)
    # Lastfall umbenannt, Ribbon „Knotenlast“ wartet (U4)
    fall = w.model.active_case
    w._objektmaske("lastfall", fall)
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("name", fall + "_neu")
    _ruhe(app)
    _befehl(w, "Lasten", "Knotenlast").aktion.trigger()
    _ruhe(app)
    _druecken(w, app, "Übernehmen")
    mk2 = _maske(w)
    werte = mk2.werte() if mk2 is not None else {}
    liste = [mk2._felder["fall"].itemText(i) for i in range(mk2._felder["fall"].count())] if mk2 else []
    check("Lastfall umbenannt, Ribbon „Knotenlast“ wartet: die neue Maske kennt nur den neuen Namen",
          getattr(mk2, "titel", "") == "Knotenlast" and werte.get("fall") == fall + "_neu" and fall not in liste,
          f"fall {werte.get('fall')!r}, Liste {liste[:4]}")
    _aufraeumen(w, app)


def test_f2_jeder_bau_haelt_vorher():
    """Quelltextpruefung: jede Methode, die selbst maske_erzeugen ruft oder die
    Auswahl umstellt und eine Objektmaske oeffnet, haelt vorher an (_maskenweg)."""
    import ast
    import inspect
    from statik3d.gui import main as gm
    baum = ast.parse(inspect.getsource(gm))
    klasse = next(n for n in baum.body if isinstance(n, ast.ClassDef) and n.name == "MainWindow")

    def deko(f):
        return {getattr(d.func if isinstance(d, ast.Call) else d, "id", "") for d in f.decorator_list}

    def rufe(f):
        return {n.func.attr for n in ast.walk(f) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"}
    ohne, gesehen = [], 0
    for f in klasse.body:
        if not isinstance(f, ast.FunctionDef) or f.name == "maske_erzeugen":
            continue
        r = rufe(f)
        baut = "maske_erzeugen" in r
        waehlt_und_oeffnet = "_baum_objekt_waehlen" in r and bool(r & {"_objektmaske", "_lastmaske", "sammelmaske"})
        if baut or waehlt_und_oeffnet:
            gesehen += 1
            if "_maskenweg" not in deko(f):
                ohne.append(f"{f.name} (Zeile {f.lineno})")
    check(f"{gesehen} Wege bauen eine Maske oder wählen und öffnen: jeder hält vorher an (_maskenweg)",
          gesehen >= 50 and not ohne, "; ".join(ohne[:6]))
    check("… auch die Elementübersicht (Modul elementmasken) läuft über einen solchen Weg",
          getattr(gm.MainWindow.maske_elementuebersicht, "maskenweg", False))


def test_f2_spaete_stelle():
    """Kommt ein Weg ohne _maskenweg doch bis maske_erzeugen, erscheint die fertig
    gebaute Maske nie: im Ribbon-Befehl ist der Befehl der Wunsch, sonst gibt es
    keinen, und die Statuszeile sagt es."""
    from statik3d.gui import masken as msk
    w, app = _fenster()
    _halle(w, app)
    mk = _k1_geaendert(w, app)
    fremd = msk.Maske("Fremd", [msk.Feld("a", "a")])
    w.maske_erzeugen(fremd)
    _ruhe(app)
    check("Späte Stelle ohne Befehl: die fertige Maske erscheint nicht, Leiste ohne Wunsch, Statuszeile",
          _maske(w) is mk and _leiste(w) is not None and w._leiste_wunsch is None
          and "noch einmal wählen" in w.statusBar().currentMessage(), w.statusBar().currentMessage())
    _aufraeumen(w, app)
    mk = _k1_geaendert(w, app)
    gebaut = []

    def befehl():
        gebaut.append(1)
        w.maske_erzeugen(msk.Maske("Fremd", [msk.Feld("a", "a")]))
    w._befehl_ausfuehren(befehl)
    _ruhe(app)
    _druecken(w, app, "Übernehmen")
    check("… im Befehl aus Ribbon oder Menü: „Übernehmen“ führt den Befehl noch einmal aus, die Maske neu gebaut",
          len(gebaut) == 2 and getattr(_maske(w), "titel", "") == "Fremd", f"{len(gebaut)} Läufe")
    _aufraeumen(w, app)


def test_f3_auswahl_bleibt():
    w, app = _fenster()
    _halle(w, app)
    m = w.model
    # Rechtsklick „Lager bearbeiten…“ (L1 der Gegenpruefung)
    w._set_selection([3, 4])
    _ruhe(app)
    w.maske_knotenlast()
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("Fz", -12.0)
    _ruhe(app)
    fall = mk.werte().get("fall")
    vorher = len(m.load_cases[fall].nodal_loads)
    w.lager_bearbeiten(0)
    _ruhe(app)
    check("Rechtsklick „Lager bearbeiten…“: Leiste, die Auswahl bleibt bei K3, K4",
          _leiste(w) is not None and sorted(int(i) for i in w.selection) == [3, 4],
          str(sorted(int(i) for i in w.selection)))
    _druecken(w, app, "Übernehmen")
    dazu = sorted(int(nl.node) for nl in m.load_cases[fall].nodal_loads[vorher:])
    check("… „Übernehmen“: die Last kommt auf K3 und K4, danach das Knotenlager",
          dazu == [3, 4] and "lager" in getattr(_maske(w), "titel", "").lower(),
          f"{dazu}, {getattr(_maske(w), 'titel', None)!r}")
    _aufraeumen(w, app)
    # Lasttabelle: die Auswahl der Lastzeile kommt erst nach der Entscheidung
    m.load_node(9, Fz=-1e3, case=m.active_case)
    w.refresh_all()
    _ruhe(app)
    w._set_selection([3, 4])
    w.maske_knotenlast()
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("Fz", -13.0)
    _ruhe(app)
    k = len(m.load_cases[m.active_case].nodal_loads) - 1
    w._last_ziel_zeigen(m.active_case, "nodal_loads", k)
    _ruhe(app)
    check("Klick in der Lasttabelle: Leiste, die Auswahl bleibt bei K3, K4 (nicht K9 der Lastzeile)",
          _leiste(w) is not None and sorted(int(i) for i in w.selection) == [3, 4],
          str(sorted(int(i) for i in w.selection)))
    _aufraeumen(w, app)


def test_f4_wunsch_meint_das_objekt():
    w, app = _fenster()
    _halle(w, app)
    m = w.model
    fall = m.active_case
    ziel = next(k for k in m.load_cases if k != fall)
    lc = m.load_cases[fall]
    n0 = len(lc.nodal_loads)
    for node in (5, 6, 7, 8):
        m.load_node(node, Fz=-1e3 * node, case=fall)
    w.refresh_all()
    _ruhe(app)
    w._last_waehlen(fall, "nodal_loads", n0)            # Last an K5
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("fall", ziel)
    mk.setzen("Fz", -99.0)
    _ruhe(app)
    gewollt = lc.nodal_loads[n0 + 2]                   # Last an K7
    w._last_waehlen(fall, "nodal_loads", n0 + 2)
    _ruhe(app)
    _druecken(w, app, "Übernehmen")
    gezeigt = w.sel_lasten[0] if w.sel_lasten else None
    obj = (getattr(m.load_cases[gezeigt[0]], gezeigt[1])[gezeigt[2]] if gezeigt else None)
    check("Last verschoben, Wunsch „Last an K7“: rechts steht die Last an K7, nicht der alte Listenplatz",
          obj is gewollt and "K7" in getattr(_maske(w), "titel", ""),
          f"{getattr(_maske(w), 'titel', None)!r}, {gezeigt}")
    _aufraeumen(w, app)
    # Nummerntausch K1 <-> K2: Baumklick und Sammelmaske meinen danach den Knoten selbst
    x2 = tuple(float(v) for v in m.nodes[2])
    mk = _k1_geaendert(w, app, x=float(m.nodes[1][0]))
    mk.setzen("nr", 2)
    _ruhe(app)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    _druecken(w, app, "Übernehmen")
    neu = _maske(w)
    check("Knoten K1 bekommt die Nummer 2, Baumklick auf K2 wartete: rechts der angeklickte Knoten (jetzt K1)",
          getattr(neu, "titel", "") == "Knoten K1"
          and tuple(float(v) for v in m.nodes[1]) == x2, f"{getattr(neu, 'titel', None)!r}")
    _aufraeumen(w, app)
    mk = _k1_geaendert(w, app, x=float(m.nodes[1][0]))
    mk.setzen("nr", 2)
    _ruhe(app)
    w.sammelmaske("knoten", [2, 3])
    _ruhe(app)
    _druecken(w, app, "Übernehmen")
    sm = _maske(w)
    text = sm._felder["objekte"].text() if sm is not None and "objekte" in sm._felder else ""
    check("… ebenso die Sammelmaske K2, K3: nach dem Tausch zeigt sie K1 und K3",
          "K1" in text and "K3" in text and "K2" not in text, repr(text))
    _aufraeumen(w, app)
    # gibt es das Objekt nicht mehr, oeffnet sich nichts, und die Statuszeile sagt es
    weg = next(k for k in m.load_cases if k != m.active_case)
    b = w._bezug_merken("lastfall", weg)
    m.load_cases.pop(weg)
    gerufen = []
    w._bezug_ausfuehren(b, lambda n: gerufen.append(n))
    check("Objekt nach dem Übernehmen verschwunden: nichts geöffnet, die Statuszeile sagt es",
          not gerufen and "nicht mehr" in w.statusBar().currentMessage(), w.statusBar().currentMessage())


def test_f5_rueckgaengig_gesperrt():
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    _halle(w, app)
    w.merken("Knoten A")
    w.model.add_node(30.0, 0.0, 0.0)
    w.merken("Knoten B")
    w.model.add_node(40.0, 0.0, 0.0)
    w.undo()                                # ein Schritt zum Wiederholen
    w.refresh_all()
    _ruhe(app)
    nn = w.model.nn
    mk = _k1_geaendert(w, app, x=2.5)
    w.act_undo.trigger()
    _ruhe(app)
    check("Rückgängig bei geänderter Maske: gesperrt - nichts zurückgenommen, die Leiste steht",
          w.model.nn == nn and _leiste(w) is not None and _maske(w) is mk, f"nn {nn} -> {w.model.nn}")
    check("… die Statuszeile nennt die Maske", "Rückgängig ist gesperrt" in w.statusBar().currentMessage()
          and "Knoten K1" in w.statusBar().currentMessage(), w.statusBar().currentMessage())
    w.act_redo.trigger()
    _ruhe(app)
    check("… Wiederholen ebenso gesperrt", "Wiederholen ist gesperrt" in w.statusBar().currentMessage(),
          w.statusBar().currentMessage())
    _druecken(w, app, "Verwerfen")
    check("„Verwerfen“: die Maske ist zu, es wird nichts rückgängig gemacht (kein Wunsch)",
          _maske(w) is None and w.model.nn == nn, f"nn {w.model.nn}")
    w.act_undo.trigger()
    _ruhe(app)
    check("… danach wirkt Rückgängig wieder", w.model.nn == nn - 1, f"nn {w.model.nn}")
    # Strg+Z in einem Textfeld der Maske bleibt das Rueckgaengig des Felds
    mk = _k1_geaendert(w, app, x=2.5)
    feld = mk._felder["y"]
    feld.setFocus()
    _ruhe(app)
    feld.selectAll()
    QtTest.QTest.keyClicks(feld, "9")
    _ruhe(app)
    check("… die „9“ steht im Feld (sonst prüfte das Folgende nichts)", feld.text() == "9", repr(feld.text()))
    nn = w.model.nn
    QtTest.QTest.keyClick(feld, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
    _ruhe(app)
    check("Strg+Z im Feld der Maske: das Feld nimmt die Eingabe zurück, das Modell bleibt",
          feld.text() != "9" and w.model.nn == nn and _maske(w) is mk, f"{feld.text()!r}, nn {w.model.nn}")
    _aufraeumen(w, app)


def test_l1_modellwechsel_und_loeschen():
    import os as _os
    w, app = _fenster()
    _halle(w, app)
    w._als_gespeichert()
    alt_env = _os.environ.pop("STATIK3D_UNGESPEICHERT", None)
    fragen = []
    w._frage_speichern_verwerfen = lambda anlass, grund: (fragen.append(anlass), "verwerfen")[1]
    try:
        modell = w.model
        mk = _k1_geaendert(w, app, x=6.5)
        w.load_example("frame")
        _ruhe(app)
        check("Gespeichertes Modell, geänderte Maske, „Beispiel öffnen“: Leiste statt still schließen",
              _leiste(w) is not None and w.model is modell and _maske(w) is mk, f"Leiste {_leiste(w) is not None}")
        _druecken(w, app, "Übernehmen")
        check("… „Übernehmen“: übernommen, danach das Beispiel mit seiner eigenen Rückfrage",
              w.model is not modell and fragen == ["Beispiel öffnen"], f"Fragen {fragen}")
        fragen.clear()
        _halle(w, app)
        modell = w.model
        mk = _k1_geaendert(w, app, x=6.5)
        w.new_model()
        _ruhe(app)
        check("„Neu“: ebenso die Leiste, das Modell bleibt", _leiste(w) is not None and w.model is modell)
        _druecken(w, app, "Verwerfen")
        check("… „Verwerfen“: danach „Neu“", w.model is not modell and w.model.nn == 0, str(w.model.nn))
        _halle(w, app)
        mk = _k1_geaendert(w, app, x=6.5)
        MODAL.clear()
        w.import_file()
        _ruhe(app)
        check("„Importieren“: die Leiste kommt vor dem Dateidialog",
              _leiste(w) is not None and not any(a == "datei" for a, _t in MODAL), str(MODAL))
        _aufraeumen(w, app)
        mk = _k1_geaendert(w, app, x=6.5)
        w.close()
        _ruhe(app)
        check("Beenden: die Leiste steht, das Fenster bleibt offen", _leiste(w) is not None and w.isVisible())
        mk.setzen("x", float(w.model.nodes[1][0]))
        _ruhe(app)
        check("… wieder unverändert: die Leiste geht, der Wunsch (Beenden) verfällt",
              _leiste(w) is None and w.isVisible())
    finally:
        if alt_env is not None:
            _os.environ["STATIK3D_UNGESPEICHERT"] = alt_env
        w.__dict__.pop("_frage_speichern_verwerfen", None)
    _aufraeumen(w, app)
    # Loeschwege nennen die geaenderte Maske in ihrer Rueckfrage (nur der Text)
    _halle(w, app)
    frei = w.model.add_node(30.0, 0.0, 0.0)
    w.refresh_all()
    _ruhe(app)
    gestellt = []
    w._bestaetigen = lambda text: (gestellt.append(text), False)[1]
    try:
        for titel, tun in (("Löschen im Baum", lambda: w._baum_loeschen("knoten", str(frei))),
                           ("Rechtsklick „Löschen“", lambda: w.auswahl_loeschen("knoten", [frei])),
                           ("mehrere im Baum", lambda: w._baum_viele_loeschen("knoten", [str(frei)]))):
            mk = _k1_geaendert(w, app, x=8.0)
            gestellt.clear()
            tun()
            _ruhe(app)
            text = gestellt[0] if gestellt else ""
            check(f"{titel}: die Rückfrage nennt „Knoten K1“ und dass sie geschlossen wird",
                  "„Knoten K1“" in text and "nicht übernommene Änderungen" in text and "geschlossen" in text,
                  text.replace("\n", " | "))
            _aufraeumen(w, app)
    finally:
        w.__dict__.pop("_bestaetigen", None)
    _aufraeumen(w, app)


def test_l2_zustand_oder_anzeige():
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    _halle(w, app)
    w.maske_schweissnaht()
    _ruhe(app)
    mk = _maske(w)
    w.sel_staebe = [next(iter(w.model.members))]
    mk.zusatzknoepfe["Auswahl übernehmen"].click()
    _ruhe(app)
    check("Schweißnaht: „Auswahl übernehmen“ füllt „Gilt für“ - das zählt als Änderung, Punkt im Titel",
          "ziele" in mk.geaenderte_felder() and _titel(mk) == PUNKT + mk.titel, repr(_titel(mk)))
    QtTest.QTest.keyClick(_ansicht(w, app), QtCore.Qt.Key_K)
    _ruhe(app)
    check("… Taste K danach: die Leiste statt still ersetzen", _leiste(w) is not None and _maske(w) is mk)
    _aufraeumen(w, app)
    w.maske_elementuebersicht()
    _ruhe(app)
    mk = _maske(w)
    knopf = (getattr(mk, "zusatzknoepfe", {}) or {}).get("Fingerabdruck")
    if knopf is not None:
        knopf.click()
        _ruhe(app)
    check("Elementübersicht: „Fingerabdruck“ ist eine reine Anzeige - kein Punkt",
          mk is not None and knopf is not None and not mk.geaenderte_felder() and _titel(mk) == mk.titel,
          f"{sorted(mk.geaenderte_felder()) if mk else None}")
    _aufraeumen(w, app)

# ---------------------------------------------------------------------------
# Zweite Nachbesserung (03.10.2026): ein langes „Übernehmen“ dreht die
# Ereignisschleife (Wasserdruck, Wind). Solange ist die Oberflaeche gesperrt
# wie waehrend einer Rechnung, ein Rueckbau stellt genau den Stand vom Beginn
# dieses Uebernehmens her, und ein Wunsch findet sein Objekt ueber stabile
# Schluessel. Fehler 1 bis 4 laufen mit echter Ereignisschleife: der Ersatz
# der Stroemungsrechnung dreht sie wie der Fortschritt (vgl. pruef_a.py).

SPERRTEXT = "Übernehmen läuft – erst abwarten oder abbrechen"


def _wasserlasten(w, name="WD1") -> int:
    return sum(1 for lc in w.model.load_cases.values() for gl in lc.geometrielasten
               if gl.verlauf.get("art") == "wasser" and gl.verlauf.get("name") == name)


def _wd1_mit_lasten(w, app):
    """Hallenrahmen mit WD1, einmal echt gerechnet: es gibt Wasserlasten."""
    _halle(w, app)
    _wasserdruck(w, app)
    w.maske_wasserdruck("WD1")
    _ruhe(app)
    _maske(w).anwenden()
    _ruhe(app)
    _aufraeumen(w, app)
    w._undo.clear()
    w._redo.clear()


def _wd1_geaendert(w, app, h=4.5):
    w.maske_wasserdruck("WD1")
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("h_ow", h)
    _ruhe(app)
    return mk


def test_r2_fehler1_abbruch_am_ende():
    """Fehler 1 (A5): Abbruch bei der letzten Fortschrittsmeldung - die echte
    Rechnung hat dann schon geschrieben (alte Lasten weg, neue Lasten, h_ow)."""
    w, app = _fenster()
    for grenze in (92, 100):
        _wd1_mit_lasten(w, app)
        n0, h0, modell = _wasserlasten(w), w.model.wasserdruecke["WD1"].h_ow, w.model
        mk = _wd1_geaendert(w, app)
        echt = w._fortschritt
        werte = []

        def fortschritt(wert, text, sofort=False, e=echt, g=grenze):
            werte.append(wert)
            if wert is not None and int(wert) >= g:
                w._abbruch = True              # der Klick auf „Abbrechen“ in dieser Ereignisschleife
            return e(wert, text, sofort)
        w._fortschritt = fortschritt
        try:
            erg = mk.anwenden()
            _ruhe(app)
        finally:
            del w._fortschritt
        meldung = ([z for z in w.log.toPlainText().splitlines() if "abgebrochen" in z] or [""])[-1]
        check(f"Abbruch bei {grenze} %: Wasserlasten, h_ow und Stapel wie vorher - „unverändert“ stimmt",
              erg is False and _wasserlasten(w) == n0 and w.model.wasserdruecke["WD1"].h_ow == h0
              and not w._undo and "unverändert" in meldung and w.model is modell,
              f"Lasten {n0} -> {_wasserlasten(w)}, h_ow {h0} -> {w.model.wasserdruecke['WD1'].h_ow}, "
              f"Schritte {len(w._undo)}, Fortschritt bis {max((v for v in werte if v is not None), default=None)}")
        check(f"… die Maske bleibt mit h_ow = 4,5 und Punkt stehen",
              _maske(w) is mk and _titel(mk) == PUNKT + mk.titel and float(mk.werte()["h_ow"]) == 4.5,
              repr(_titel(_maske(w))))
        _aufraeumen(w, app)


def test_r2_fehler2_rueckbau_auf_den_beginn():
    """Fehler 2 (B1): der Rueckbau nimmt nie den obersten Schritt, sondern stellt
    genau den Stand vom Beginn des Uebernehmens her - Modell, Rueckgaengig- und
    Wiederholen-Stapel -, auch wenn waehrenddessen ein fremder Schritt entstand."""
    import statik3d.wasserdruck as wdm
    from statik3d import stroemung as strm
    from PySide6 import QtWidgets
    w, app = _fenster()
    alt = wdm.lasten_erzeugen
    for art in ("abbruch", "fehler"):
        _halle(w, app)
        _wasserdruck(w, app)
        frei = w.model.add_node(60.0, 0.0, 0.0)
        w.merken("Knoten A")
        w.model.add_node(70.0, 0.0, 0.0)
        w.merken("Knoten B")
        w.model.add_node(80.0, 0.0, 0.0)
        w.undo()                                # ein Schritt zum Wiederholen
        _ruhe(app)
        undo0, redo0, nn0, modell = [s[0] for s in w._undo], [s[0] for s in w._redo], w.model.nn, w.model
        mk = _wd1_geaendert(w, app)

        def ersatz(m, wd, fortschritt=None, art=art):
            QtWidgets.QApplication.processEvents()
            # waehrenddessen entsteht ein fremder Schritt (wie in pruef_b.py B1:
            # merken, dann schreiben - eine Tabellenzelle tut es so)
            w.merken(f"Knoten K{frei} verschoben")
            w.model.nodes[frei] = [61.0, 0.0, 0.0]
            if fortschritt is not None:
                fortschritt(0.5, "halb")
            if art == "fehler":
                raise ValueError("simuliert: Strömungsrechnung gescheitert")
            raise strm.Abgebrochen()
        wdm.lasten_erzeugen = ersatz
        try:
            erg = mk.anwenden()
            _ruhe(app)
        finally:
            wdm.lasten_erzeugen = alt
        check(f"{'Abbruch' if art == 'abbruch' else 'Fehler'} mit fremdem Schritt dazwischen: Modell, "
              "Rückgängig- und Wiederholen-Stapel genau wie zu Beginn",
              erg is False and float(w.model.nodes[frei][0]) == 60.0 and w.model.nn == nn0
              and [s[0] for s in w._undo] == undo0 and [s[0] for s in w._redo] == redo0 and w.model is modell,
              f"x {float(w.model.nodes[frei][0])}, nn {nn0} -> {w.model.nn}, Rückgängig {[s[0] for s in w._undo]}, "
              f"Wiederholen {[s[0] for s in w._redo]}")
        _aufraeumen(w, app)
        w.redo()
        _ruhe(app)
        check("… danach wirkt Wiederholen wie vor dem Übernehmen", w.model.nn == nn0 + 1, f"nn {w.model.nn}")


def test_r2_fehler3_gesperrt_waehrend_uebernehmen():
    """Fehler 3 (A7): waehrend ein „Übernehmen“ rechnet, ist die Oberflaeche
    gesperrt wie waehrend einer Rechnung - nur „Abbrechen“ wirkt."""
    import statik3d.wasserdruck as wdm
    from statik3d import stroemung as strm
    from statik3d.web.server import State
    from PySide6 import QtCore, QtTest, QtWidgets
    w, app = _fenster()
    _halle(w, app)
    _wasserdruck(w, app)
    w.merken("Knoten vorher")
    w.model.add_node(90.0, 0.0, 0.0)
    w.refresh_all()
    _ruhe(app)
    st = State()
    st.bound = w
    w.web_state, w.web_version = st, st.version
    nn0, modell = w.model.nn, w.model
    mk = _wd1_geaendert(w, app)
    alt = wdm.lasten_erzeugen
    gesehen = {}

    def status():
        return w.statusBar().currentMessage()

    def versuch(name, tun, bleibt):
        try:
            tun()
        except Exception as ex:                 # noqa: BLE001
            gesehen[name] = (False, f"Ausnahme {type(ex).__name__}: {ex}")
            return
        QtWidgets.QApplication.processEvents()
        gesehen[name] = (bool(bleibt()) and SPERRTEXT in status(), status()[:90])

    def ersatz(m, wd, fortschritt=None):
        if fortschritt is not None:
            fortschritt(0.3, "rechnet")
        versuch("Baumklick (Signal des Modellbaums)", lambda: w.baum.angeklickt.emit("knoten", "2"),
                lambda: _maske(w) is mk)
        versuch("Rückgängig (Strg+Z, Ribbon, Menü)", lambda: w.act_undo.trigger(),
                lambda: w.model is modell and w.model.nn == nn0)
        versuch("Ribbon-Befehl „Knotenlast“", lambda: _befehl(w, "Lasten", "Knotenlast").aktion.trigger(),
                lambda: _maske(w) is mk)
        versuch("„Neu“ (Modellwechsel)", lambda: w.new_model(), lambda: w.model is modell)
        versuch("Taste K in der Ansicht", lambda: w._ansicht_taste(
            QtGui_key(QtCore.Qt.Key_K)), lambda: _maske(w) is mk)
        # echte Eingaben gehen gar nicht erst durch: Tippen ins Feld, Klick in den Baum
        feld = mk._felder["h_ow"]
        vorher = feld.text()
        QtTest.QTest.keyClicks(feld, "7")
        QtWidgets.QApplication.processEvents()
        gesehen["Tippen in die laufende Maske"] = (feld.text() == vorher, feld.text())
        aktuell = w.baum.currentItem()
        vp = w.baum.viewport()
        QtTest.QTest.mouseClick(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(40, 40))
        QtWidgets.QApplication.processEvents()
        gesehen["Mausklick in den Modellbaum"] = (w.baum.currentItem() is aktuell and _maske(w) is mk, "")
        gesehen["Web: der Browser bekommt eine Meldung"] = (
            "Übernehmen" in str(getattr(w, "web_sperrgrund", "") or ""), str(getattr(w, "web_sperrgrund", "")))
        # Esc ist „Abbrechen“ - das wirkt
        QtTest.QTest.keyClick(_ansicht(w, app), QtCore.Qt.Key_Escape)
        QtWidgets.QApplication.processEvents()
        if fortschritt is not None and not fortschritt(0.6, "weiter"):
            raise strm.Abgebrochen()
        return alt(m, wd, fortschritt=fortschritt)
    wdm.lasten_erzeugen = ersatz
    try:
        erg = mk.anwenden()
        _ruhe(app)
    finally:
        wdm.lasten_erzeugen = alt
        w.web_state = None
    for name, (ok, detail) in gesehen.items():
        check(f"Während „Übernehmen“ rechnet: {name} abgewiesen", ok, detail)
    check("… nur „Abbrechen“ (Esc) wirkt: abgebrochen, die Maske steht mit h_ow = 4,5, Modell wie vorher",
          erg is False and _maske(w) is mk and float(mk.werte()["h_ow"]) == 4.5 and w.model is modell
          and w.model.nn == nn0 and w.model.wasserdruecke["WD1"].h_ow == 3.0,
          f"{erg!r}, rechts {getattr(_maske(w), 'titel', None)!r}")
    _aufraeumen(w, app)


def QtGui_key(taste):
    from PySide6 import QtCore, QtGui
    return QtGui.QKeyEvent(QtCore.QEvent.KeyPress, taste, QtCore.Qt.NoModifier)


def test_r2_fehler4_doppelter_knopfdruck():
    """Fehler 4 (A6): die Leiste ist waehrend des Laufs gesperrt - ein zweiter
    Klick auf „Übernehmen“ (Leiste oder Maske) rechnet nicht noch einmal."""
    import statik3d.wasserdruck as wdm
    from PySide6 import QtCore, QtTest, QtWidgets
    w, app = _fenster()
    _halle(w, app)
    _wasserdruck(w, app)
    alt = wdm.lasten_erzeugen
    mk = _wd1_geaendert(w, app)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    zahl = {"rechnung": 0}
    knopfzustand = []

    def ersatz(m, wd, fortschritt=None):
        zahl["rechnung"] += 1
        if zahl["rechnung"] == 1:
            knopf = _knopf(w, "Übernehmen")
            knopfzustand.append(knopf is not None and knopf.isEnabled())
            if knopf is not None:
                knopf.click()                                   # programmatisch
                QtTest.QTest.mouseClick(knopf, QtCore.Qt.LeftButton)   # und mit der Maus
            mk.anwenden()                                       # der Knopf der Maske selbst
            QtWidgets.QApplication.processEvents()
        return alt(m, wd, fortschritt=fortschritt)
    wdm.lasten_erzeugen = ersatz
    schritte = len(w._undo)
    try:
        _druecken(w, app, "Übernehmen")
    finally:
        wdm.lasten_erzeugen = alt
    check("Leiste „Übernehmen“ zweimal, Maskenknopf dazu: eine Rechnung, ein Schritt, dann der Wunsch",
          zahl["rechnung"] == 1 and len(w._undo) == schritte + 1
          and getattr(_maske(w), "titel", "") == "Knoten K2" and w.model.wasserdruecke["WD1"].h_ow == 4.5,
          f"Rechnungen {zahl['rechnung']}, Schritte +{len(w._undo) - schritte}, "
          f"rechts {getattr(_maske(w), 'titel', None)!r}")
    check("… die Leiste war während des Laufs gesperrt", knopfzustand == [False], str(knopfzustand))
    _aufraeumen(w, app)


def test_r2_fehler5_wunsch_nach_rueckbau():
    """Fehler 5 (A3): nach einem Rueckbau findet der Wunsch sein Objekt ueber
    stabile Schluessel; verschwundene Objekte heissen, wie der Anwender sie sieht."""
    import statik3d.wasserdruck as wdm
    w, app = _fenster()
    _halle(w, app)
    _wasserdruck(w, app)
    alt = wdm.lasten_erzeugen
    mk = _wd1_geaendert(w, app)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)

    def kaputt(m, wd, fortschritt=None):
        raise ValueError("simuliert: Eingabe passt nicht")
    wdm.lasten_erzeugen = kaputt
    try:
        _druecken(w, app, "Übernehmen")
    finally:
        wdm.lasten_erzeugen = alt
    erst = _maske(w) is mk and _leiste(w) is not None
    _druecken(w, app, "Übernehmen")
    check("Erstes Übernehmen scheitert mit Rückbau, zweites gelingt: der Wunsch öffnet Knoten K2",
          erst and getattr(_maske(w), "titel", "") == "Knoten K2" and w.model.wasserdruecke["WD1"].h_ow == 4.5,
          f"rechts {getattr(_maske(w), 'titel', None)!r}, Status {w.statusBar().currentMessage()[:80]!r}")
    _aufraeumen(w, app)
    # verschwundene Objekte: der Name, den der Anwender sieht
    m = w.model
    frei = m.add_node(55.0, 1.0, 2.0)
    for art, name, tun, erwartet in (
            ("knoten", str(frei), lambda: m.knoten_loeschen(frei), f"Knoten K{frei}"),
            ("geoflaeche", "FA", lambda: m.flaechen.pop("FA"), "Fläche FA")):
        b = w._bezug_merken(art, name)
        tun()
        gerufen = []
        w._bezug_ausfuehren(b, lambda n: gerufen.append(n))
        text = w.statusBar().currentMessage()
        check(f"Verschwunden: die Meldung sagt „{erwartet}“", not gerufen and erwartet in text, text)


def test_r2_luecke1_unveraenderte_maske_neu():
    """Lücke 1 (pruef_c U1): Rückgängig, Wiederholen und eine Änderung aus dem
    Browser bauen eine offene, unveraenderte Maske mit dem Stand von jetzt neu -
    oder schliessen sie, wenn es ihr Objekt nicht mehr gibt."""
    from PySide6 import QtCore, QtTest
    from statik3d.web.server import State
    w, app = _fenster()
    _halle(w, app)
    m = w.model
    a = m.add_node(30.0, 0.0, 0.0)
    m.add_node(40.0, 0.0, 0.0)
    w.refresh_all()
    _ruhe(app)
    w._bestaetigen = lambda text: True
    try:
        w._baum_loeschen("knoten", str(a))
        _ruhe(app)
    finally:
        w.__dict__.pop("_bestaetigen", None)
    w._objektmaske("knoten", str(a))                    # der Knoten bei x = 40, jetzt K{a}
    _ruhe(app)

    def stimmt():
        mk = _maske(w)
        if mk is None:
            return False, "keine Maske"
        nr = int(str(mk.titel).rsplit("K", 1)[-1])
        x = float(mk.werte()["x"])
        return x == float(w.model.nodes[nr][0]) and x == 40.0, f"{mk.titel}: x = {x}, Modell {float(w.model.nodes[nr][0])}"
    QtTest.QTest.keyClick(_ansicht(w, app), QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
    _ruhe(app)
    ok, detail = stimmt()
    check("Strg+Z unter der unveränderten Maske: sie zeigt den Stand von jetzt (derselbe Knoten, x = 40)",
          ok and w.model.nn == a + 2 - 0, detail)
    QtTest.QTest.keyClick(_ansicht(w, app), QtCore.Qt.Key_Y, QtCore.Qt.ControlModifier)
    _ruhe(app)
    ok, detail = stimmt()
    check("… Strg+Y ebenso", ok, detail)
    _aufraeumen(w, app)
    # Objekt weg: „Neu“ im Baum legt einen Knoten an, Rueckgaengig nimmt ihn zurueck
    w._baum_neu("knoten")
    _ruhe(app)
    mk = _maske(w)
    titel = getattr(mk, "titel", "")
    w.act_undo.trigger()
    _ruhe(app)
    check("Rückgängig nimmt den Knoten der offenen Maske zurück: sie ist zu, die Statuszeile sagt es",
          _maske(w) is None and "nicht mehr" in w.statusBar().currentMessage()
          and titel.replace("Neu: ", "") in w.statusBar().currentMessage(),
          f"{titel!r}: {w.statusBar().currentMessage()!r}")
    # eine Aenderung aus dem Browser
    _aufraeumen(w, app)
    w._objektmaske("knoten", "1")
    _ruhe(app)
    st = State()
    st.bound = w
    w.web_state, w.web_version = st, st.version
    try:
        st.model.nodes[1] = [9.0, 0.0, 0.0]
        st.touch()
        w._web_poll()
        _ruhe(app)
        mk = _maske(w)
        check("Änderung aus dem Browser unter der unveränderten Maske K1: sie zeigt x = 9",
              mk is not None and mk.titel == "Knoten K1" and float(mk.werte()["x"]) == 9.0,
              f"{getattr(mk, 'titel', None)!r} x = {mk.werte().get('x') if mk else None}")
    finally:
        w.web_state = None
    _aufraeumen(w, app)


def test_r2_luecke2_baum_mehrfach():
    """Lücke 2 (B4): Mehrfachwahl im Baum haelt an, bevor die Auswahl geleert wird."""
    import numpy as np
    w, app = _fenster()
    _halle(w, app)
    m = w.model
    w._set_selection([3, 4])
    _ruhe(app)
    w.maske_knotenlast()
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("Fz", -12.0)
    _ruhe(app)
    fall = mk.werte().get("fall")
    vorher = len(m.load_cases[fall].nodal_loads)
    w._baum_mehrfach("lastfall", list(m.load_cases)[:2])
    _ruhe(app)
    auswahl = sorted(int(i) for i in np.asarray(w.selection))
    check("Mehrfachwahl zweier Lastfälle bei geänderter Knotenlast: Leiste, die Auswahl K3, K4 bleibt",
          _leiste(w) is not None and auswahl == [3, 4] and _maske(w) is mk, f"Auswahl {auswahl}")
    _druecken(w, app, "Übernehmen")
    dazu = sorted(int(nl.node) for nl in m.load_cases[fall].nodal_loads[vorher:])
    check("… „Übernehmen“: die Lasten stehen an K3 und K4", dazu == [3, 4], str(dazu))
    _aufraeumen(w, app)
    # mehrere Knoten im Baum: ebenso anhalten, erst danach K5, K6 waehlen
    w._set_selection([3, 4])
    _ruhe(app)
    w.maske_knotenlast()
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("Fz", -13.0)
    _ruhe(app)
    vorher = len(m.load_cases[fall].nodal_loads)
    w._baum_mehrfach("knoten", ["5", "6"])
    _ruhe(app)
    auswahl = sorted(int(i) for i in np.asarray(w.selection))
    check("Mehrfachwahl K5, K6 im Baum bei geänderter Knotenlast: Leiste, die Auswahl K3, K4 bleibt",
          _leiste(w) is not None and auswahl == [3, 4] and _maske(w) is mk, f"Auswahl {auswahl}")
    _druecken(w, app, "Übernehmen")
    dazu = sorted(int(nl.node) for nl in m.load_cases[fall].nodal_loads[vorher:])
    auswahl = sorted(int(i) for i in np.asarray(w.selection))
    check("… „Übernehmen“: Lasten an K3 und K4, danach sind K5 und K6 gewählt",
          dazu == [3, 4] and auswahl == [5, 6], f"Lasten {dazu}, Auswahl {auswahl}")
    _aufraeumen(w, app)


def test_r2_luecke3_web_bei_geaenderter_maske():
    """Lücke 3 (B5): eine Änderung aus dem Browser wird abgewiesen, solange am
    Desktop eine geaenderte Maske offen ist - der Browser bekommt eine Meldung."""
    from statik3d.web.server import State, ApiError, apply_op
    from statik3d.examples_lib import build_example
    w, app = _fenster()
    _halle(w, app)
    st = State()
    st.bound = w
    w.web_state, w.web_version = st, st.version
    try:
        modell, nn0 = w.model, w.model.nn
        mk = _k1_geaendert(w, app, x=4.75)
        for titel, tun in (("Bearbeitung (Knoten anlegen)", lambda: apply_op(st, {"op": "add_node", "x": 1, "y": 2, "z": 3})),
                           ("„Beispiel“ ersetzt das Modell", lambda: setattr(st, "model", build_example("frame")))):
            fehler = None
            try:
                tun()
            except ApiError as ex:
                fehler = ex
            check(f"Browser: {titel} abgewiesen, die Meldung nennt die Maske",
                  fehler is not None and getattr(fehler, "status", 0) == 409 and "Knoten K1" in str(fehler)
                  and w.model is modell and w.model.nn == nn0 and _maske(w) is mk,
                  str(fehler)[:100])
        mk.setzen("x", float(w.model.nodes[1][0]))      # wieder unveraendert
        _ruhe(app)
        try:
            apply_op(st, {"op": "add_node", "x": 1, "y": 2, "z": 3})
            frei = True
        except ApiError as ex:
            frei = str(ex)
        check("… mit unveränderter Maske geht die Änderung aus dem Browser durch", frei is True and w.model.nn == nn0 + 1,
              str(frei))
    finally:
        w.web_state = None
    _aufraeumen(w, app)


def test_r2_luecke4_modell_leeren():
    """Lücke 4 (A9): „Modell leeren“ nennt die geaenderte Maske und schliesst sie."""
    w, app = _fenster()
    _halle(w, app)
    mk = _k1_geaendert(w, app, x=4.5)
    gefragt = []
    w._fragen_knoepfe = lambda titel, text, *a, **k: (gefragt.append(text), True)[1]
    try:
        w.clear_mesh()
        _ruhe(app)
    finally:
        del w._fragen_knoepfe
    text = gefragt[0] if gefragt else ""
    check("„Modell leeren“: die Rückfrage nennt „Knoten K1“ und dass sie geschlossen wird",
          "„Knoten K1“" in text and "geschlossen" in text, text.replace("\n", " | ")[-120:])
    check("… danach ist die Maske zu, keine Leiste", _maske(w) is None and _leiste(w) is None and w.model.nn == 0)
    _aufraeumen(w, app)


def test_r2_schwaechen():
    """Sammelmaske mit Teilfehler, Zuweisen und Strg+Klick ohne Maskenwechsel."""
    w, app = _fenster()
    _halle(w, app)
    echt = w._sammelfelder

    def sammelfelder(art, namen):
        neu = []
        for key, text, fart, les, schr, werte in echt(art, namen):
            if key == "x":
                def schr2(i, v, s=schr):
                    if int(i) == 3:
                        raise ValueError("K3 nimmt diesen Wert nicht (simuliert)")
                    return s(i, v)
                schr = schr2
            neu.append((key, text, fart, les, schr, werte))
        return neu
    w._sammelfelder = sammelfelder
    try:
        w.sammelmaske("knoten", [2, 3])
        _ruhe(app)
        mk = _maske(w)
        x2 = float(w.model.nodes[2][0])
        mk.setzen("x", 9.75)
        _ruhe(app)
        erg = mk.anwenden()
        _ruhe(app)
        letzte = w.log.toPlainText().splitlines()[-1]
        status = w.statusBar().currentMessage()
        check("Sammelmaske, K3 weist ab: zurückgenommen, Statuszeile und Protokoll sagen dasselbe",
              erg is False and float(w.model.nodes[2][0]) == x2 and status == letzte
              and "geändert" not in status, f"Status {status!r} | Protokoll {letzte!r}")
    finally:
        del w._sammelfelder
    _aufraeumen(w, app)
    # „Querschnitt zuweisen…“ ersetzt keine Maske: keine Leiste, der Fokus geht ins Feld
    w._set_selection([3, 4])
    _ruhe(app)
    mk = _k1_geaendert(w, app, x=4.5)
    w.zuweisen_zeigen("querschnitt")
    _ruhe(app)
    check("„Querschnitt zuweisen…“ bei geänderter Maske: keine Leiste, die Maske bleibt",
          _leiste(w) is None and _maske(w) is mk, f"Leiste {_leiste(w) is not None}")
    _aufraeumen(w, app)
    # Strg+Klick nimmt eine Last nur heraus: keine Leiste
    m = w.model
    fall = m.active_case
    n0 = len(m.load_cases[fall].nodal_loads)
    m.load_node(5, Fz=-1e3, case=fall)
    m.load_node(6, Fz=-2e3, case=fall)
    w.refresh_all()
    _ruhe(app)
    w._last_waehlen(fall, "nodal_loads", n0, ersetzen=True)
    w._last_waehlen(fall, "nodal_loads", n0 + 1, ersetzen=False)
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("Fz", -9.0)
    _ruhe(app)
    w._last_waehlen(fall, "nodal_loads", n0, ersetzen=False)
    _ruhe(app)
    check("Strg+Klick nimmt eine Last aus der Auswahl: keine Leiste, die Last ist heraus, die Maske bleibt",
          _leiste(w) is None and w.sel_lasten == [(fall, "nodal_loads", n0 + 1)] and _maske(w) is mk,
          f"Leiste {_leiste(w) is not None}, {w.sel_lasten}")
    _aufraeumen(w, app)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_punkt_im_titel, test_signal_direkt_ausgeloest, test_wege_zeigen_die_leiste,
              test_uebernehmen_fuehrt_den_wunsch_aus,
              test_baumklick_laesst_die_auswahl_stehen,
              test_verwerfen_fuehrt_den_wunsch_aus, test_gescheitertes_uebernehmen_laesst_alles_stehen,
              test_unveraenderte_maske_ohne_leiste, test_ohne_knopfdruck_bleibt_alles, test_ort_der_leiste,
              test_waehrend_der_rechnung, test_entf_nennt_die_maske_weiter, test_frische_masken_ohne_punkt,
              test_merker_kostet_kein_neuzeichnen,
              test_f1_entscheidung_nach_dem_handler, test_f1_ausnahme_und_halber_schritt, test_f2_wunsch_baut_neu,
              test_f2_jeder_bau_haelt_vorher, test_f2_spaete_stelle, test_f3_auswahl_bleibt, test_f4_wunsch_meint_das_objekt,
              test_f5_rueckgaengig_gesperrt, test_l1_modellwechsel_und_loeschen, test_l2_zustand_oder_anzeige,
              test_r2_fehler1_abbruch_am_ende, test_r2_fehler2_rueckbau_auf_den_beginn,
              test_r2_fehler3_gesperrt_waehrend_uebernehmen, test_r2_fehler4_doppelter_knopfdruck,
              test_r2_fehler5_wunsch_nach_rueckbau, test_r2_luecke1_unveraenderte_maske_neu,
              test_r2_luecke2_baum_mehrfach, test_r2_luecke3_web_bei_geaenderter_maske,
              test_r2_luecke4_modell_leeren, test_r2_schwaechen):
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
