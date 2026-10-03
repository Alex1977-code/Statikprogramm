"""
Tasten und Fokus (Plan-Paket 14a, 03.10.2026).

Zusage an den Anwender vom 24.09.2026 (Vorschlag Tastenkuerzel, Antwort 10):
„In der Ansicht, wenn sie den Fokus hat, genuegt eine einzelne Taste. Nie wirkt
sie in einem Textfeld.“ Und: „Entf = Auswahl loeschen (mit Rueckfrage)“.

* Entf in der 3D-Ansicht loescht alles Gewaehlte nach **einer** Rueckfrage, die
  nennt, was geloescht wird („2 Stäbe und 3 Knoten“), in **einem**
  Rueckgaengig-Schritt. Im Modellbaum bleibt Entf beim Baum, im Textfeld und in
  der Tabelle tut die Ansicht nichts.
* Die Einzeltasten K (Knoten), S (Stab), L (Lager), B (Belastung) und F (Flaeche)
  rufen den Befehl auf - nur bei Fokus in der Ansicht, nie in einem Textfeld,
  einer Tabelle oder einer Maske, nie mit Strg oder Umschalt.
* Das Skizzenfenster nimmt Strg+Z, Strg+Y, Esc, Entf und Ruecktaste selbst an:
  die Ribbon-Kuerzel sind Anwendungskuerzel und galten bis dahin auch dort -
  Strg+Z nahm den letzten **Modell**schritt zurueck (gemessen: Knoten 18 -> 17,
  die Skizze blieb), Esc hob die Modellauswahl auf (3 -> 0).

Aufruf:  python -m tests.test_tasten_fokus
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_tastenfokus_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _fenster():
    if "w" in _FENSTER:
        # Kuerzel und Tastendruecke wirken nur im aktiven Fenster
        _FENSTER["w"].activateWindow()
        _FENSTER["app"].processEvents()
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w.activateWindow()
    app.processEvents()
    w.fehler_liste = []
    # Fehler und Hinweise gemeinsam abfangen (tests/meldungen.py, Paket 9b): die
    # Liste bekommt beide, w.meldungen wertet sie getrennt aus
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste)
    _FENSTER.update(w=w, app=app)
    return w, app


def _halle(w, app):
    """Die Halle (3 Staebe, 19 Knoten) und drei freie Knoten dazu: so gibt es
    Gewaehltes, das sich loeschen laesst (freie Knoten) und eines, das haengt."""
    import numpy as np
    w.load_example("hall")
    app.processEvents()
    for i in range(3):
        w.model.add_node(50.0 + i, 0.0, 0.0)
    w.refresh_all()
    app.processEvents()
    w.maskenrand.schliessen()
    w._auswahl_leeren()
    w.selection = np.array([], dtype=int)
    w._undo.clear()
    w._redo.clear()
    return w.model.nn


def _waehlen(w, staebe=(), knoten=()):
    import numpy as np
    w._auswahl_vergessen()
    w.sel_staebe = list(staebe)
    w.selection = np.array(list(knoten), dtype=int)


def _fragen(w, antwort=True) -> list:
    """Die Rueckfrage vor dem Loeschen aufzeichnen und beantworten."""
    gestellt = []

    def frage(text):
        gestellt.append(text)
        return antwort
    w._bestaetigen = frage
    return gestellt


def _ohne_fragen(w):
    w.__dict__.pop("_bestaetigen", None)


def _ansicht(w, app):
    """Die 3D-Ansicht hat den Fokus."""
    ia = w.plotter.interactor
    ia.setFocus()
    app.processEvents()
    return ia


def _maske(w) -> str:
    return w.maskenrand.maske.titel if w.maskenrand.offen() and w.maskenrand.maske is not None else ""


# ---------------------------------------------------------------------------
def test_entf_in_der_ansicht():
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    n0 = _halle(w, app)
    ia = _ansicht(w, app)
    fragen = _fragen(w, True)
    try:
        _waehlen(w, staebe=["Stiel links", "Riegel"], knoten=[n0 - 3, n0 - 2, n0 - 1])
        schritte = len(w._undo)
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Entf in der Ansicht: genau eine Rückfrage für alles Gewählte", len(fragen) == 1, str(fragen))
        text = fragen[0] if fragen else ""
        check("… sie nennt, was gelöscht wird: „2 Stäbe und 3 Knoten“",
              "2 Stäbe und 3 Knoten" in text, text)
        check("… beide Stäbe und alle drei Knoten sind weg",
              set(w.model.members) == {"Stiel rechts"} and w.model.nn == n0 - 3,
              f"{sorted(w.model.members)}, {w.model.nn} Knoten")
        check("… ein einziger Rückgängig-Schritt", len(w._undo) == schritte + 1, f"{schritte} -> {len(w._undo)}")
        check("… die Auswahl ist leer, kein Fehler gemeldet",
              not w.sel_staebe and not len(w.selection) and not w.fehler_liste, str(w.fehler_liste))
        w.undo()
        app.processEvents()
        check("Rückgängig holt Stäbe und Knoten mit einem Schritt zurück",
              len(w.model.members) == 3 and w.model.nn == n0, f"{len(w.model.members)} Stäbe, {w.model.nn} Knoten")

        # Nein: nichts geschieht, die Auswahl bleibt
        fragen.clear()
        w._bestaetigen = lambda t: (fragen.append(t), False)[1]
        _waehlen(w, staebe=["Riegel"], knoten=[n0 - 1])
        schritte = len(w._undo)
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Antwort „Nein“: nichts gelöscht, kein Schritt, die Auswahl bleibt",
              len(fragen) == 1 and "Riegel" in w.model.members and w.model.nn == n0
              and len(w._undo) == schritte and w.sel_staebe == ["Riegel"] and len(w.selection) == 1,
              f"{len(fragen)} Frage(n), {w.model.nn} Knoten, Auswahl {w.sel_staebe}")

        # nichts gewählt: keine Frage, ein stiller Hinweis in der Statuszeile
        fragen.clear()
        w._bestaetigen = lambda t: (fragen.append(t), True)[1]
        _waehlen(w)
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Nichts gewählt: keine Rückfrage, nichts geändert, die Statuszeile sagt es",
              not fragen and w.model.nn == n0 and len(w.model.members) == 3
              and "gewählt" in w.statusBar().currentMessage(), repr(w.statusBar().currentMessage()))

        # ein Knoten, an dem etwas hängt, bleibt - mit Grund; der Rest geht in einem Schritt
        fragen.clear()
        _waehlen(w, staebe=["Riegel"], knoten=[0, n0 - 1])
        schritte = len(w._undo)
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Knoten mit Element bleibt, der freie Knoten und der Stab gehen - eine Frage, ein Schritt",
              len(fragen) == 1 and "Riegel" not in w.model.members and w.model.nn == n0 - 1
              and len(w._undo) == schritte + 1, f"{len(fragen)} Frage(n), {w.model.nn} Knoten, {len(w._undo) - schritte} Schritt(e)")
        check("… das Protokoll nennt, was nicht gelöscht wurde",
              "nicht gelöscht" in w.log.toPlainText()[-600:], w.log.toPlainText()[-120:])
        w.undo()
        app.processEvents()

        # nur ein benutzter Knoten: nichts zu löschen, der Schritt wird zurückgenommen
        _waehlen(w, knoten=[0])
        schritte, nn = len(w._undo), w.model.nn
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Nur ein benutzter Knoten gewählt: nichts gelöscht, kein Rückgängig-Schritt bleibt zurück",
              w.model.nn == nn and len(w._undo) == schritte, f"{nn} -> {w.model.nn}, Schritte {schritte} -> {len(w._undo)}")
    finally:
        _ohne_fragen(w)
        w._auswahl_leeren()


def test_entf_lager_und_last():
    """Lager und Lasten gehören zur Auswahl: Entf löscht das gewählte Lager, nicht
    seinen Knoten, und die gewählte Last."""
    import numpy as np
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    n0 = _halle(w, app)
    ia = _ansicht(w, app)
    fragen = _fragen(w, True)
    try:
        n_lager = len(w.model.supports)
        w._auswahl_vergessen()
        w.sel_lager = [("lager", 0)]
        w.selection = np.array([int(w.model.supports[0].node)], dtype=int)   # Baum und Tabelle wählen den Knoten mit
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Entf: das gewählte Lager geht, sein Knoten bleibt",
              len(fragen) == 1 and "1 Knotenlager" in fragen[0] and len(w.model.supports) == n_lager - 1
              and w.model.nn == n0, f"{fragen}, {len(w.model.supports)} Lager, {w.model.nn} Knoten")
        fragen.clear()
        w._auswahl_vergessen()
        fall = next(f for f, lc in w.model.load_cases.items() if lc.beam_loads or lc.nodal_loads)
        lc = w.model.load_cases[fall]
        liste = "beam_loads" if lc.beam_loads else "nodal_loads"
        n_last = len(getattr(lc, liste))
        w.sel_lasten = [(fall, liste, 0)]
        schritte = len(w._undo)
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Entf: die gewählte Last geht, mit einer Frage und einem Schritt",
              len(fragen) == 1 and "1 Last" in fragen[0] and len(getattr(lc, liste)) == n_last - 1
              and len(w._undo) == schritte + 1, f"{fragen}, {n_last} -> {len(getattr(lc, liste))}")
        check("… ohne Fehlermeldung", not w.fehler_liste, str(w.fehler_liste))
    finally:
        _ohne_fragen(w)
        w._auswahl_leeren()


def test_entf_nur_bei_fokus_in_der_ansicht():
    """Im Textfeld, in der Tabelle und im Baum löscht die Ansicht nichts."""
    from PySide6 import QtCore, QtTest, QtWidgets
    K = QtCore.Qt
    w, app = _fenster()
    n0 = _halle(w, app)
    fragen = _fragen(w, True)
    try:
        # Textfeld (Befehlssuche): Entf löscht dort ein Zeichen, nicht die Auswahl
        _waehlen(w, staebe=["Riegel"], knoten=[n0 - 1])
        w.ribbon.suche.setText("abc")
        w.ribbon.suche.setFocus()
        w.ribbon.suche.setCursorPosition(0)
        app.processEvents()
        QtTest.QTest.keyClick(w.ribbon.suche, K.Key_Delete)
        app.processEvents()
        check("Entf im Textfeld (Befehlssuche) löscht das Zeichen, keine Rückfrage, die Auswahl bleibt",
              w.ribbon.suche.text() == "bc" and not fragen and w.sel_staebe == ["Riegel"]
              and "Riegel" in w.model.members, f"{w.ribbon.suche.text()!r}, {fragen}")
        w.ribbon.suche.clear()
        # Tabelle unten
        w.tabelle_zeigen("Knoten")
        app.processEvents()
        tabelle = next(t for t in w.findChildren(QtWidgets.QTableView)
                       if t.isVisible() and t.objectName() != "tabellenfuss")
        tabelle.setFocus()
        app.processEvents()
        QtTest.QTest.keyClick(tabelle, K.Key_Delete)
        app.processEvents()
        check("Entf in der Tabelle unten: die Ansicht löscht nichts, keine Rückfrage",
              not fragen and "Riegel" in w.model.members and w.model.nn == n0, f"{fragen}, {w.model.nn}")
        # Modellbaum: Entf gehört dem Baum - eine Frage, und es ist die des Baums
        b = w.baum
        alle = b._alle_eintraege()
        knoten = next(i for i in alle if b._schluessel(i) == ("knoten", str(n0 - 1)))
        b.setFocus()
        b.setCurrentItem(knoten)
        app.processEvents()
        fragen.clear()
        QtTest.QTest.keyClick(b, K.Key_Delete)
        app.processEvents()
        check("Entf im Modellbaum: der Baum löscht seinen Eintrag - genau eine Frage, die des Baums",
              len(fragen) == 1 and fragen[0].startswith(f"Knoten K{n0 - 1} ") and w.model.nn == n0 - 1,
              f"{fragen}, {w.model.nn} Knoten")
    finally:
        _ohne_fragen(w)
        w._auswahl_leeren()


# ---------------------------------------------------------------------------
def test_einzeltasten_in_der_ansicht():
    import numpy as np
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    _halle(w, app)
    ia = _ansicht(w, app)

    def druecken(taste, umschalter=K.NoModifier):
        w.maskenrand.schliessen()
        app.processEvents()
        ia.setFocus()
        app.processEvents()
        QtTest.QTest.keyClick(ia, taste, umschalter)
        app.processEvents()

    for taste, titel in ((K.Key_K, "Knoten"), (K.Key_S, "Stab"), (K.Key_L, "Lager")):
        _waehlen(w)
        druecken(taste)
        check(f"Taste {chr(int(taste))} in der Ansicht öffnet die Maske „{titel}“", _maske(w) == titel,
              repr(_maske(w)))
    # B: je nach Auswahl Knoten-, Linien- oder Flächenlast
    for was, titel in (("nichts", "Knotenlast"), ("knoten", "Knotenlast"), ("stab", "Linienlast"),
                       ("linie", "Linienlast"), ("flaeche", "Flächenlast"), ("volumen", "Flächenlast")):
        _waehlen(w, knoten=[0] if was == "knoten" else [])
        if was == "stab":
            w.sel_staebe = ["Riegel"]
        elif was == "linie":
            w.sel_linien = ["L1"]
        elif was == "flaeche":
            w.sel_flaechen = ["F1"]
        elif was == "volumen":
            w.sel_koerper = ["V1"]
        druecken(K.Key_B)
        check(f"Taste B mit gewähltem „{was}“ öffnet die Maske „{titel}“", _maske(w) == titel, repr(_maske(w)))
    _waehlen(w, knoten=[0])
    w.sel_staebe = ["Riegel"]
    druecken(K.Key_B)
    check("B mit Knoten und Stab zugleich: die Linienlast (Stäbe und Linien gehen vor)",
          _maske(w) == "Linienlast", repr(_maske(w)))
    # F: Fläche aus den gewählten Linien
    _waehlen(w)
    w.fehler_liste.clear()
    druecken(K.Key_F)
    check("Taste F ruft „Fläche aus Linien“: ohne drei gewählte Linien sagt es das",
          any("drei Linien" in f for f in w.fehler_liste), str(w.fehler_liste))
    aufrufe = []
    w.add_flaeche_aus_auswahl = lambda: aufrufe.append("F")
    try:
        druecken(K.Key_F)
    finally:
        del w.add_flaeche_aus_auswahl
    check("… und läuft über den Befehl selbst", aufrufe == ["F"], str(aufrufe))

    # nie mit Strg, Umschalt oder Alt
    _waehlen(w)
    for umschalter, name in ((K.ControlModifier, "Strg"), (K.ShiftModifier, "Umschalt"), (K.AltModifier, "Alt")):
        druecken(K.Key_K, umschalter)
        check(f"{name}+K in der Ansicht öffnet keine Maske", _maske(w) == "", repr(_maske(w)))
    # die übrigen Buchstaben bleiben stumm (VTK bekommt sie nicht: r setzte die Kamera zurück)
    w.fehler_liste.clear()
    druecken(K.Key_R)
    druecken(K.Key_W)
    druecken(K.Key_Q)
    check("andere Buchstaben (R, W, Q) tun in der Ansicht weiter nichts, es gibt keinen Fehler",
          _maske(w) == "" and not w.fehler_liste, f"{_maske(w)!r}, {w.fehler_liste}")
    w.maskenrand.schliessen()
    w._auswahl_leeren()
    w.selection = np.array([], dtype=int)


def test_einzeltasten_nie_im_textfeld():
    """Im Textfeld, in der Tabelle und im Feld einer Maske wird der Buchstabe
    getippt oder bleibt wirkungslos - der Befehl läuft nicht."""
    from PySide6 import QtCore, QtTest, QtWidgets
    K = QtCore.Qt
    w, app = _fenster()
    _halle(w, app)
    w.maskenrand.schliessen()
    # Befehlssuche
    w.ribbon.suche.clear()
    w.ribbon.suche.setFocus()
    app.processEvents()
    for taste in (K.Key_K, K.Key_S, K.Key_L, K.Key_B, K.Key_F):
        QtTest.QTest.keyClick(w.ribbon.suche, taste)
    app.processEvents()
    check("Befehlssuche: K S L B F werden getippt, es öffnet sich keine Maske",
          w.ribbon.suche.text() == "kslbf" and _maske(w) == "", f"{w.ribbon.suche.text()!r}, {_maske(w)!r}")
    # die Trefferliste der Befehlssuche hält Tastatur und Fokus, bis sie zu ist, und danach
    # ist das Fenster nicht mehr aktiv - ohne beides nähme setFocus() den Fokus nicht an
    w.ribbon._vervollstaendigung.popup().hide()
    w.ribbon.suche.clear()
    w.ribbon.suche.clearFocus()
    w.activateWindow()
    app.processEvents()
    # Tabelle unten
    w.tabelle_zeigen("Knoten")
    app.processEvents()
    tabelle = next(t for t in w.findChildren(QtWidgets.QTableView)
                   if t.isVisible() and t.objectName() != "tabellenfuss")
    tabelle.setFocus()
    app.processEvents()
    for taste in (K.Key_K, K.Key_S, K.Key_L, K.Key_B):
        QtTest.QTest.keyClick(tabelle, taste)
    app.processEvents()
    check("Tabelle unten: die Buchstaben öffnen keine Maske", _maske(w) == "", repr(_maske(w)))
    # Feld einer Maske: die Knotenmaske bleibt die Knotenmaske
    ia = _ansicht(w, app)
    QtTest.QTest.keyClick(ia, K.Key_K)
    app.processEvents()
    check("Vorbereitung: K öffnet die Knotenmaske, ihr erstes Feld hat den Fokus",
          _maske(w) == "Knoten" and w.maskenrand.maske.isAncestorOf(QtWidgets.QApplication.focusWidget()),
          f"{_maske(w)!r}, {QtWidgets.QApplication.focusWidget()}")
    feld = QtWidgets.QApplication.focusWidget()
    for taste in (K.Key_S, K.Key_L, K.Key_B, K.Key_F, K.Key_K):
        QtTest.QTest.keyClick(feld, taste)
    app.processEvents()
    check("Im Feld der Maske bleibt die Maske, wie sie ist (kein Stab, kein Lager, keine Last)",
          _maske(w) == "Knoten", repr(_maske(w)))
    # Feld einer anderen Maske mit Textfeld: das Skizzenfenster hat eines (Name)
    f = w.unterlage_skizze_neu()
    app.processEvents()
    f.activateWindow()
    f.ed_name.clear()
    f.ed_name.setFocus()
    app.processEvents()
    w.maskenrand.schliessen()
    for taste in (K.Key_K, K.Key_S):
        QtTest.QTest.keyClick(f.ed_name, taste)
    app.processEvents()
    check("Textfeld im Skizzenfenster: die Buchstaben werden getippt, keine Maske im Hauptfenster",
          f.ed_name.text() == "ks" and _maske(w) == "", f"{f.ed_name.text()!r}, {_maske(w)!r}")
    f.close()
    w.activateWindow()
    app.processEvents()
    # zurück in die Ansicht: ein Klick legt den Fokus dorthin, danach wirkt die Taste wieder
    w.maskenrand.schliessen()
    w.ribbon.suche.setFocus()
    app.processEvents()
    QtTest.QTest.mouseClick(w.plotter.interactor, K.LeftButton, K.NoModifier, QtCore.QPoint(5, 5))
    app.processEvents()
    check("Ein Klick in die Ansicht legt den Fokus dorthin",
          QtWidgets.QApplication.focusWidget() is w.plotter.interactor,
          str(QtWidgets.QApplication.focusWidget()))
    QtTest.QTest.keyClick(w.plotter.interactor, K.Key_K)
    app.processEvents()
    check("… und die Taste K wirkt wieder", _maske(w) == "Knoten", repr(_maske(w)))
    w.maskenrand.schliessen()


# ---------------------------------------------------------------------------
def _skizze(w, app):
    import numpy as np
    from PySide6 import QtCore
    _halle(w, app)
    w.selection = np.arange(3)
    w.merken("Probeschritt")
    w.model.add_node(60.0, 0.0, 0.0)               # ein Modellschritt, den Strg+Z nicht anfassen darf
    f = w.unterlage_skizze_neu()
    app.processEvents()
    f.activateWindow()
    app.processEvents()
    f.blatt.setFocus()
    app.processEvents()
    return f


def test_skizzenfenster_nimmt_seine_tasten():
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    f = _skizze(w, app)
    nn, schritte = w.model.nn, len(w._undo)
    check("Vorbereitung: das Skizzenfenster ist aktiv, die Skizze hat den Fokus",
          f.isActiveWindow() and f.blatt.hasFocus(), f"aktiv {f.isActiveWindow()}, Fokus {f.blatt.hasFocus()}")
    f.element_anfuegen({"art": "linie", "p1": [0, 0], "p2": [10, 0]})
    f.element_anfuegen({"art": "linie", "p1": [0, 0], "p2": [0, 10]})
    QtTest.QTest.keyClick(f.blatt, K.Key_Z, K.ControlModifier)
    app.processEvents()
    check("Strg+Z im Skizzenfenster nimmt den letzten Skizzenschritt zurück",
          len(f.skizze["elemente"]) == 1, f"{len(f.skizze['elemente'])} Elemente")
    check("… und lässt das Modell unverändert (Knoten, Rückgängig-Stapel)",
          w.model.nn == nn and len(w._undo) == schritte, f"Knoten {nn} -> {w.model.nn}, Stapel {schritte} -> {len(w._undo)}")
    QtTest.QTest.keyClick(f.blatt, K.Key_Y, K.ControlModifier)
    app.processEvents()
    check("Strg+Y im Skizzenfenster stellt den Schritt wieder her",
          len(f.skizze["elemente"]) == 2, f"{len(f.skizze['elemente'])} Elemente")
    check("… ebenfalls ohne das Modell anzufassen",
          w.model.nn == nn and len(w._redo) == 0 and len(w._undo) == schritte,
          f"Knoten {w.model.nn}, Wiederholen-Stapel {len(w._redo)}")
    # Esc: bricht das angefangene Element ab, die Modellauswahl bleibt
    f.werkzeug_setzen("linie")
    f._klick(10.0, 10.0)
    check("Vorbereitung: ein Punkt der Linie ist gesetzt", len(f.punkte) == 1, str(len(f.punkte)))
    QtTest.QTest.keyClick(f.blatt, K.Key_Escape)
    app.processEvents()
    check("Esc im Skizzenfenster bricht das angefangene Element ab",
          len(f.punkte) == 0, f"{len(f.punkte)} Punkt(e)")
    check("… und lässt die Auswahl im Modell stehen (3 Knoten)", len(w.selection) == 3, str(len(w.selection)))
    check("… das Fenster bleibt offen", f.isVisible())
    # Entf und Rücktaste löschen das hervorgehobene Element
    f.blatt.hervor = 0
    QtTest.QTest.keyClick(f.blatt, K.Key_Delete)
    app.processEvents()
    n_nach_entf = len(f.skizze["elemente"])
    f.blatt.hervor = 0
    QtTest.QTest.keyClick(f.blatt, K.Key_Backspace)
    app.processEvents()
    check("Entf und Rücktaste löschen im Skizzenfenster je das gewählte Element (2 -> 1 -> 0)",
          n_nach_entf == 1 and len(f.skizze["elemente"]) == 0, f"{n_nach_entf}, {len(f.skizze['elemente'])}")
    check("… das Modell bleibt dabei unverändert", w.model.nn == nn and len(w._undo) == schritte)
    QtTest.QTest.keyClick(f.blatt, K.Key_Z, K.ControlModifier)
    app.processEvents()
    check("Strg+Z holt das gelöschte Element zurück", len(f.skizze["elemente"]) == 1,
          f"{len(f.skizze['elemente'])} Elemente")
    f.close()
    w.selection = w.selection[:0]


def test_skizzenfenster_textfelder_behalten_ihre_tasten():
    """In den Feldern des Skizzenfensters gehören Strg+Z, Entf und Rücktaste dem
    Feld (Text), Esc dem Fenster - nie dem Hauptfenster."""
    from PySide6 import QtCore, QtTest, QtWidgets
    K = QtCore.Qt
    w, app = _fenster()
    f = _skizze(w, app)
    nn, schritte = w.model.nn, len(w._undo)
    f.element_anfuegen({"art": "linie", "p1": [0, 0], "p2": [10, 0]})
    f.blatt.hervor = 0
    f.ed_name.setText("Abc")
    f.ed_name.setFocus()
    f.ed_name.setCursorPosition(3)
    app.processEvents()
    QtTest.QTest.keyClick(f.ed_name, K.Key_Backspace)
    check("Rücktaste im Namensfeld löscht das Zeichen, nicht das Element",
          f.ed_name.text() == "Ab" and len(f.skizze["elemente"]) == 1, f"{f.ed_name.text()!r}, {len(f.skizze['elemente'])}")
    f.ed_name.setCursorPosition(0)
    QtTest.QTest.keyClick(f.ed_name, K.Key_Delete)
    check("Entf im Namensfeld löscht das Zeichen, nicht das Element",
          f.ed_name.text() == "b" and len(f.skizze["elemente"]) == 1, f"{f.ed_name.text()!r}, {len(f.skizze['elemente'])}")
    f.ed_name.setText("")
    QtTest.QTest.keyClicks(f.ed_name, "xy")
    QtTest.QTest.keyClick(f.ed_name, K.Key_Z, K.ControlModifier)
    app.processEvents()
    check("Strg+Z im Namensfeld macht die Eingabe im Feld rückgängig, die Skizze und das Modell bleiben",
          len(f.skizze["elemente"]) == 1 and w.model.nn == nn and len(w._undo) == schritte,
          f"{f.ed_name.text()!r}, {len(f.skizze['elemente'])} Elemente, Knoten {w.model.nn}")
    QtTest.QTest.keyClick(f.ed_name, K.Key_Escape)
    app.processEvents()
    check("Esc im Namensfeld hebt die Auswahl im Modell nicht auf (3 Knoten bleiben)",
          len(w.selection) == 3, str(len(w.selection)))
    # ein Knopf des Fensters mit Fokus: Strg+Z gilt der Skizze, Esc lässt das Modell in Ruhe
    knopf = next(b for b in f.findChildren(QtWidgets.QPushButton) if b.text() == "Übernehmen")
    knopf.setFocus()
    app.processEvents()
    QtTest.QTest.keyClick(knopf, K.Key_Z, K.ControlModifier)
    app.processEvents()
    check("Strg+Z mit Fokus auf einem Knopf nimmt den Skizzenschritt zurück, nicht den des Modells",
          len(f.skizze["elemente"]) == 0 and w.model.nn == nn and len(w._undo) == schritte,
          f"{len(f.skizze['elemente'])} Elemente, Knoten {w.model.nn}")
    QtTest.QTest.keyClick(knopf, K.Key_Escape)
    app.processEvents()
    check("Esc mit Fokus auf einem Knopf: die Auswahl im Modell bleibt (3 Knoten), das Fenster auch",
          len(w.selection) == 3 and f.isVisible(), f"{len(w.selection)} Knoten")
    f.close()
    w.selection = w.selection[:0]


def test_skizzenfenster_ohne_hauptfenster_wirkung_auf_andere_tasten():
    """Gegenprobe: die Tasten, die das Skizzenfenster nicht annimmt, gelten weiter
    für das Programm (Strg+A wählt alle Knoten) - wir haben nichts übernommen,
    was nicht in der Liste steht."""
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    f = _skizze(w, app)
    n_vorher = len(w.selection)
    QtTest.QTest.keyClick(f.blatt, K.Key_A, K.ControlModifier)
    app.processEvents()
    check("Strg+A gilt im Skizzenfenster weiter fürs Programm (alle Knoten gewählt)",
          len(w.selection) == w.model.nn and n_vorher == 3, f"{n_vorher} -> {len(w.selection)} von {w.model.nn}")
    f.close()
    w.selection = w.selection[:0]


# ---------------------------------------------------------------------------
def test_liste_und_code_stimmen_ueberein():
    """Die Liste „Weitere Tasten“ nennt genau die Einzeltasten, die der Code kennt."""
    from PySide6 import QtCore
    from statik3d.gui import kuerzelliste as kl
    from statik3d.gui.main import MainWindow
    in_liste = {t for (_n, t, ort, _h) in kl.WEITERE_TASTEN if ort == "Ansicht" and len(t) == 1}
    im_code = {chr(int(k)) for k in MainWindow.ANSICHT_TASTEN}
    check("Kürzelliste und Code nennen dieselben Einzeltasten (K S L B F)",
          in_liste == im_code == set("KSLBF"), f"{sorted(in_liste)} / {sorted(im_code)}")
    entf = [z for z in kl.WEITERE_TASTEN if z[2] == "Ansicht" and "Entf" in z[1]]
    check("… und Entf in der Ansicht steht darin", len(entf) == 1, str(entf))
    w, _app = _fenster()
    fehlt = []
    for register, text, taste in MainWindow.ANSICHT_TASTEN_BEFEHLE:
        bs = [b for b in w.ribbon.befehle if b.register == register and b.text == text]
        if len(bs) != 1 or f"Taste {taste} in der Ansicht" not in bs[0].aktion.toolTip():
            fehlt.append((register, text))
    check("Der Hinweis jedes dieser Befehle im Ribbon nennt die Taste („Taste K in der Ansicht“)",
          not fehlt, str(fehlt))
    skizze = {z[1] for z in kl.WEITERE_TASTEN if z[2] == "Skizzenfenster"}
    check("… das Skizzenfenster nennt Strg+Z, Strg+Y, Esc, Entf und Rücktaste",
          all(any(t in s for s in skizze) for t in ("Strg+Z", "Strg+Y", "Esc", "Entf", "Rücktaste")),
          str(sorted(skizze)))


# ---------------------------------------------------------------------------
# Nachzug 03.10.2026: Gegenpruefung der Taste Entf
# ---------------------------------------------------------------------------
def _linienlast_auf_riegel(w, app):
    """Die Halle mit einer Linienlast auf dem Riegel (Lastfall LF1): der Riegel
    ist das belastete Objekt, das bei Klick auf „Linienlasten“ leuchtet."""
    n0 = _halle(w, app)
    w.model.add_linienlast("Riegel", [0.0, 0.0, -1e3], art="stab", case="LF1")
    w.model.lasten_verteilen()
    w.refresh_all()
    app.processEvents()
    return n0


def test_entf_nimmt_nur_hervorgehobenes_nicht_mit():
    """Der Klick auf „Linienlasten“ im Baum und auf eine Zeile der Lasttabelle
    schreibt die belasteten Objekte in die Auswahl, damit sie leuchten. Entf löschte
    sie mit („1 Stab wirklich löschen?“ nach dem Klick auf die Lasten)."""
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    # Weg 1: Klick auf die Lastart im Baum
    _linienlast_auf_riegel(w, app)
    ia = w.plotter.interactor
    fragen = _fragen(w, True)
    try:
        w._lastart_geklickt("LF1|linie")
        app.processEvents()
        check("Vorbereitung (Baum): der Riegel leuchtet, ohne dass ihn jemand gewählt hat",
              w.sel_staebe == ["Riegel"], str(w.sel_staebe))
        _ansicht(w, app)
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Entf nach dem Klick auf „Linienlasten“: der Stab bleibt, gefragt wird nach den Lasten",
              "Riegel" in w.model.members and len(fragen) == 1 and "Linienlast" in fragen[0]
              and "Stab" not in fragen[0], f"{sorted(w.model.members)}, {fragen}")
        check("… und die Linienlast ist weg (die Frage galt ihr)",
              not w.model.load_cases["LF1"].linienlasten, str(len(w.model.load_cases["LF1"].linienlasten)))
        # Weg 2: eine Zeile der Lasttabelle
        w.undo()
        app.processEvents()
        fragen.clear()
        w.cb_lastfilter.setCurrentText("LF1")
        w._lasten_fuellen()
        nr = next(i for i in range(200) if w._lastzeiger(i)[1] == "linienlasten")
        w._tabelle_last(nr)
        app.processEvents()
        check("Vorbereitung (Tabelle): Riegel leuchtet, die Last ist gewählt",
              w.sel_staebe == ["Riegel"] and len(w.sel_lasten) == 1, f"{w.sel_staebe}, {w.sel_lasten}")
        _ansicht(w, app)
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Entf nach dem Klick auf eine Lastzeile: nur die Last wird gelöscht, der Stab bleibt",
              len(fragen) == 1 and fragen[0].startswith("1 Last wirklich") and "Stab" not in fragen[0]
              and "Riegel" in w.model.members and not w.model.load_cases["LF1"].linienlasten,
              f"{fragen}, {sorted(w.model.members)}")
        # Gegenprobe: wer den Stab selbst wählt, löscht ihn
        w.undo()
        app.processEvents()
        fragen.clear()
        w._lastart_geklickt("LF1|linie")
        w.clear_selection()
        _waehlen(w, staebe=["Riegel"])
        _ansicht(w, app)
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Gegenprobe: nach einer echten Wahl (Alles deselektieren, dann Stab gewählt) löscht Entf den Stab",
              len(fragen) == 1 and fragen[0].startswith("1 Stab wirklich") and "Riegel" not in w.model.members,
              f"{fragen}, {sorted(w.model.members)}")
        # Gegenprobe: eine Änderung am Modell beendet den Vermerk
        w.undo()
        app.processEvents()
        fragen.clear()
        w._lastart_geklickt("LF1|linie")
        w._aenderung()
        _ansicht(w, app)
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Gegenprobe: nach einer Änderung des Modells gilt die Auswahl wieder als gewählt",
              len(fragen) == 1 and fragen[0].startswith("1 Stab wirklich"), str(fragen))
    finally:
        _ohne_fragen(w)
        w._auswahl_leeren()


def test_ansicht_nimmt_den_fokus_nur_per_linksklick():
    """pyvistaqt stellt WheelFocus ein: auch Mausrad, mittlere und rechte Taste legten die
    Tastatur in die Ansicht. Wer dann in einem Feld weitertippte („S355“), löste die
    Einzeltasten aus."""
    from PySide6 import QtCore, QtTest, QtWidgets
    K = QtCore.Qt
    w, app = _fenster()
    _halle(w, app)
    ia = w.plotter.interactor
    check("Die Ansicht nimmt keinen Fokus an (kein Rad, kein Tab)", ia.focusPolicy() == K.NoFocus,
          str(ia.focusPolicy()))

    def zum_feld():
        w.ribbon.suche.clear()
        w.ribbon.suche.setFocus()
        app.processEvents()
        return QtWidgets.QApplication.focusWidget() is w.ribbon.suche

    zum_feld()
    QtTest.QTest.mousePress(ia, K.MiddleButton, K.NoModifier, QtCore.QPoint(10, 10))
    QtTest.QTest.mouseRelease(ia, K.MiddleButton, K.NoModifier, QtCore.QPoint(60, 60))
    app.processEvents()
    check("Mittlere Taste (Drehen) in der Ansicht: der Fokus bleibt im Textfeld",
          QtWidgets.QApplication.focusWidget() is w.ribbon.suche, str(QtWidgets.QApplication.focusWidget()))
    QtTest.QTest.mousePress(ia, K.RightButton, K.NoModifier, QtCore.QPoint(10, 10))
    QtTest.QTest.mouseRelease(ia, K.RightButton, K.NoModifier, QtCore.QPoint(60, 60))   # gezogen: kein Menü
    app.processEvents()
    check("Rechte Taste (Schieben) in der Ansicht: der Fokus bleibt im Textfeld",
          QtWidgets.QApplication.focusWidget() is w.ribbon.suche, str(QtWidgets.QApplication.focusWidget()))
    QtTest.QTest.keyClicks(QtWidgets.QApplication.focusWidget(), "S355")
    app.processEvents()
    check("Danach getippt: „S355“ steht im Feld, keine Maske hat sich geöffnet",
          w.ribbon.suche.text().lower() == "s355" and _maske(w) == "",
          f"{w.ribbon.suche.text()!r}, {_maske(w)!r}")
    w.ribbon._vervollstaendigung.popup().hide()
    w.ribbon.suche.clear()
    w.ribbon.suche.clearFocus()
    w.activateWindow()
    app.processEvents()
    zum_feld()
    QtTest.QTest.mouseClick(ia, K.LeftButton, K.NoModifier, QtCore.QPoint(5, 5))
    app.processEvents()
    check("Der Linksklick legt die Tastatur in die Ansicht",
          QtWidgets.QApplication.focusWidget() is ia, str(QtWidgets.QApplication.focusWidget()))
    QtTest.QTest.keyClick(ia, K.Key_K)
    app.processEvents()
    check("… und die Einzeltaste wirkt danach", _maske(w) == "Knoten", repr(_maske(w)))
    w.maskenrand.schliessen()


def test_einzeltaste_ersetzt_keine_geaenderte_maske():
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    _halle(w, app)
    ia = _ansicht(w, app)
    w.maske_knoten()
    app.processEvents()
    mk = w.maskenrand.maske
    feld = next(iter(mk._felder))
    _ansicht(w, app)
    QtTest.QTest.keyClick(ia, K.Key_S)
    app.processEvents()
    check("Unveränderte Maske: die Einzeltaste ersetzt sie (S: Stab)", _maske(w) == "Stab", repr(_maske(w)))
    w.maske_knoten()
    app.processEvents()
    mk = w.maskenrand.maske
    mk.setzen(feld, 12.5)
    app.processEvents()
    check("Vorbereitung: die Maske „Knoten“ meldet eine nicht übernommene Änderung",
          bool(mk.geaenderte_felder()), str(mk.geaenderte_felder()))
    w.statusBar().clearMessage()
    w.fehler_liste.clear()
    for taste in (K.Key_S, K.Key_L, K.Key_B, K.Key_F, K.Key_K):
        _ansicht(w, app)
        QtTest.QTest.keyClick(ia, taste)
    app.processEvents()
    check("Maske mit Änderung: keine Einzeltaste ersetzt sie, die Eingabe bleibt",
          w.maskenrand.maske is mk and _maske(w) == "Knoten" and bool(mk.geaenderte_felder()),
          f"{_maske(w)!r}, {mk.geaenderte_felder()}")
    check("… die Statuszeile sagt, warum", "nicht übernommene Änderungen" in w.statusBar().currentMessage(),
          repr(w.statusBar().currentMessage()))
    # Seit Paket 13m (03.10.2026) halten K, S, L und B an der Leiste „Übernehmen |
    # Verwerfen“ oben rechts, wie jeder andere Weg; F oeffnet keine Maske (den
    # Flaechendialog) und wirkt wie ohne offene Maske - ohne drei Linien die Meldung
    leiste = getattr(w, "aenderungsleiste", None)
    check("… K, S, L, B: oben rechts die Leiste „Übernehmen | Verwerfen“ (Paket 13m)",
          leiste is not None and leiste.isVisible())
    check("… F öffnet keine Maske und wirkt wie ohne Maske: ohne drei Linien die Meldung",
          any("drei Linien" in f for f in w.fehler_liste), str(w.fehler_liste))
    w.fehler_liste.clear()
    w.maskenrand.schliessen()


def test_entf_und_tasten_waehrend_der_rechnung():
    """Die Rechnung liest das Modell; Entf und die Befehle der Einzeltasten ändern es
    (F öffnete den Flächendialog, ein modales Fenster während der Rechnung)."""
    from PySide6 import QtCore, QtTest, QtWidgets
    K = QtCore.Qt

    class _Laeuft:
        def isRunning(self):
            return True

    w, app = _fenster()
    n0 = _halle(w, app)
    ia = _ansicht(w, app)
    fragen = _fragen(w, True)
    gerufen = []
    exec_alt = QtWidgets.QDialog.exec
    QtWidgets.QDialog.exec = lambda self, *a, **k: (gerufen.append(type(self).__name__), 0)[1]
    alt = w.worker
    w.worker = _Laeuft()
    try:
        _waehlen(w, staebe=["Riegel"], knoten=[n0 - 1])
        w.sel_linien = ["L1", "L2", "L3"]
        w.statusBar().clearMessage()
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Entf während einer Rechnung: keine Rückfrage, nichts gelöscht, die Statuszeile sagt es",
              not fragen and "Riegel" in w.model.members and w.model.nn == n0
              and "Rechnung läuft" in w.statusBar().currentMessage(), f"{fragen}, {w.statusBar().currentMessage()!r}")
        for taste in (K.Key_K, K.Key_S, K.Key_L, K.Key_B, K.Key_F):
            QtTest.QTest.keyClick(ia, taste)
        app.processEvents()
        check("K S L B F während einer Rechnung: keine Maske, kein modales Fenster, kein Fehlerfenster",
              _maske(w) == "" and not gerufen and not w.fehler_liste, f"{_maske(w)!r}, {gerufen}, {w.fehler_liste}")
    finally:
        w.worker = alt
        QtWidgets.QDialog.exec = exec_alt
        _ohne_fragen(w)
        w._auswahl_leeren()
    # Gegenprobe: ohne Rechnung wirken sie wieder
    QtTest.QTest.keyClick(ia, K.Key_K)
    app.processEvents()
    check("Gegenprobe: ohne laufende Rechnung öffnet K wieder die Maske", _maske(w) == "Knoten", repr(_maske(w)))
    w.maskenrand.schliessen()
    w._rechnet_gerade = True
    try:
        QtTest.QTest.keyClick(ia, K.Key_K)
        app.processEvents()
        check("Auch das Merkmal „rechnet gerade“ sperrt sie", _maske(w) == "", repr(_maske(w)))
    finally:
        w._rechnet_gerade = False


def test_rueckfrage_nennt_die_folgen():
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    n0 = _halle(w, app)
    ia = _ansicht(w, app)
    fragen = _fragen(w, False)
    try:
        _waehlen(w, staebe=["Riegel"], knoten=[n0 - 1])
        w.sel_linien = ["L1"]
        w.sel_flaechen = ["F1"]
        w.results = None
        w.analysis = None
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        text = fragen[0] if fragen else ""
        check("Die Rückfrage nennt die Folgen: Stab (Stabelemente bleiben), Linie, Fläche (Elemente gehen mit), "
              "Knoten", "Stäbe: ihre Stabelemente bleiben stehen" in text and "Linienlasten" in text
              and "nehmen ihre Elemente mit" in text and "sein Lager" in text and "Knotenlasten" in text,
              text.replace("\n", " | "))
        check("… die erste Zeile ist die Frage mit den Zahlen",
              text.splitlines()[0] == "1 Fläche, 1 Stab, 1 Linie und 1 Knoten wirklich löschen?", text.splitlines()[0] if text else "")
        check("… ohne Ergebnisse steht nichts von Ergebnissen darin", "Ergebnisse" not in text)
        fragen.clear()
        w.results = {"probe": 1}
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        text = fragen[0] if fragen else ""
        check("Mit Ergebnissen: sie werden verworfen, und Rückgängig holt sie nicht zurück",
              "Ergebnisse werden verworfen" in text and "Rückgängig holt sie nicht zurück" in text,
              text.replace("\n", " | "))
        fragen.clear()
        w.results = None
        _waehlen(w, knoten=[n0 - 1])
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        text = fragen[0] if fragen else ""
        check("Nur Knoten gewählt: kein Wort über Stäbe und Flächen",
              "Stäbe" not in text and "Flächen" not in text and "sein Lager" in text, text.replace("\n", " | "))
        fragen.clear()
        w.maske_knoten()
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen(next(iter(mk._felder)), 3.0)
        _ansicht(w, app)
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        text = fragen[0] if fragen else ""
        check("Eine offene Maske mit nicht übernommenen Änderungen wird genannt: sie wird geschlossen",
              "nicht übernommene Änderungen" in text and "Knoten" in text and "geschlossen" in text,
              text.replace("\n", " | "))
    finally:
        _ohne_fragen(w)
        w.results = None
        w.maskenrand.schliessen()
        w._auswahl_leeren()


def test_nichts_geloescht_laesst_die_stapel_in_ruhe():
    """Ging nichts weg, hatte merken() trotzdem den Wiederholen-Stapel geleert und
    bei großen Modellen alte Schritte verdrängt."""
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    n0 = _halle(w, app)
    ia = _ansicht(w, app)
    fragen = _fragen(w, True)
    try:
        w._undo.clear()
        w._undo.append(("alt", w.model.copy(), w._stand))
        w._redo.clear()
        w._redo.append(("Wiederholen-Probe", w.model.copy(), w._stand))
        stand = w._stand
        # nur benutzte Knoten: es wird gar nicht erst gefragt
        _waehlen(w, knoten=[0, 1])
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Nur benutzte Knoten gewählt: keine Rückfrage, nichts geschieht, die Statuszeile oder das Protokoll nennt den Grund",
              not fragen and w.model.nn == n0 and "benutzt" in w.log.toPlainText()[-300:],
              f"{fragen}, {w.log.toPlainText()[-120:]!r}")
        check("… Rückgängig- und Wiederholen-Stapel und Änderungsstand unverändert",
              len(w._undo) == 1 and len(w._redo) == 1 and w._stand == stand,
              f"{len(w._undo)} / {len(w._redo)}, Stand {stand} -> {w._stand}")
        # gefragt wird, aber der Löschweg scheitert (ein Stab, den es nicht gibt)
        w.sel_staebe = ["Phantom"]
        w.selection = w.selection[:0]
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Gewählt ist etwas, das sich nicht löschen lässt: gefragt wird, aber es bleibt nichts zurück",
              len(fragen) == 1 and len(w._undo) == 1 and len(w._redo) == 1 and w._stand == stand,
              f"{len(fragen)} Frage(n), Stapel {len(w._undo)} / {len(w._redo)}, Stand {stand} -> {w._stand}")
        # Gegenprobe: wird etwas gelöscht, gibt es genau einen Schritt, und Wiederholen ist leer
        fragen.clear()
        _waehlen(w, staebe=["Riegel"])
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        check("Gegenprobe: wird wirklich etwas gelöscht, gibt es einen Schritt mehr und nichts zu wiederholen",
              len(w._undo) == 2 and len(w._redo) == 0 and "Riegel" not in w.model.members,
              f"Stapel {len(w._undo)} / {len(w._redo)}")
        w.undo()
        app.processEvents()
        check("… Rückgängig holt den Stab zurück", "Riegel" in w.model.members)
    finally:
        _ohne_fragen(w)
        w._auswahl_leeren()
        w._undo.clear()
        w._redo.clear()


def test_entf_grosse_auswahl_ist_schnell():
    """Strg+A, Entf an einem vernetzten Modell: je Knoten ein Durchgang durch alle
    Elemente und alle Verweise war quadratisch."""
    import time
    from PySide6 import QtCore, QtTest
    from statik3d import mesher
    K = QtCore.Qt
    w, app = _fenster()
    n0 = _halle(w, app)
    m = w.model
    ia = _ansicht(w, app)
    fragen = _fragen(w, True)
    try:
        # 5000 freie Knoten, jeder mit Lager und Knotenlast (alt: 2000 Knoten 1,3 s, quadratisch)
        erste = m.nn
        n_lager = len(m.supports)
        for i in range(5000):
            k = m.add_node(100.0 + i, 0.0, 0.0)
            m.support(k, [0, 1, 2])
            m.load_node(k, Fz=-1e3, case="LF1")
        w.refresh_all()
        app.processEvents()
        _waehlen(w, knoten=range(erste, m.nn))
        t0 = time.time()
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        dt = time.time() - t0
        check("5000 freie Knoten mit Lager und Last: Entf löscht alle in unter 2 s",
              w.model.nn == n0 and len(w.model.supports) == n_lager and dt < 2.0,
              f"{dt:.2f} s, {w.model.nn} Knoten, {len(w.model.supports)} Lager")
        # eine Kette mit 4000 Elementen, alle Knoten gewählt (Strg+A): alle hängen an Elementen
        w.undo()
        m = w.model
        mat, sec = next(iter(m.materials)), next(iter(m.sections))
        erste = m.nn
        mesher.line_of_beams(m, mat, sec, (200.0, 0, 0), (4200.0, 0, 0), 4000)
        w.refresh_all()
        app.processEvents()
        fragen.clear()
        _waehlen(w, knoten=range(erste, m.nn))
        nn, schritte = w.model.nn, len(w._undo)
        t0 = time.time()
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        dt = time.time() - t0
        check("4001 Knoten einer Kette mit 4000 Elementen gewählt: unter 2 s, es wird gar nicht erst gefragt",
              not fragen and w.model.nn == nn and len(w._undo) == schritte and dt < 2.0,
              f"{dt:.2f} s, {len(fragen)} Frage(n)")
        check("… das Protokoll nennt den Grund („benutzt von … Elemente“)",
              "benutzt von" in w.log.toPlainText()[-400:] and "Nichts gelöscht" in w.log.toPlainText()[-400:],
              w.log.toPlainText()[-160:])
    finally:
        _ohne_fragen(w)
        w._auswahl_leeren()
        w._undo.clear()


def test_entf_teils_benutzte_knoten():
    """Nur Knoten gewaehlt, ein Teil haengt an Elementen: die Rueckfrage nennt nur die
    freien und sagt, wie viele bleiben; geloescht werden nur die freien. Am Drehlager
    fragte Entf nach Strg+A „133066 Knoten wirklich löschen?“ und loeschte 62 freie
    (gemessen 03.10.2026)."""
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    n0 = _halle(w, app)                       # 19 Knoten an Staeben, 3 freie
    ia = _ansicht(w, app)
    fragen = _fragen(w, True)
    try:
        _waehlen(w, knoten=range(n0))
        QtTest.QTest.keyClick(ia, K.Key_Delete)
        app.processEvents()
        f = fragen[-1] if fragen else ""
        check("Strg+A-artig, 3 von 22 Knoten frei: die Rückfrage nennt 3 Knoten, nicht 22",
              f.startswith("3 Knoten wirklich löschen?") and "22 Knoten" not in f.split("?")[0], f[:120])
        check("… und sagt, dass 19 der 22 bleiben", "19 der 22 gewählten Knoten bleiben stehen" in f, f[:200])
        check("… gelöscht sind genau die 3 freien", w.model.nn == n0 - 3, str(w.model.nn))
        check("… die Meldung nennt beides",
              "3 Knoten gelöscht" in w.log.toPlainText()[-400:]
              and "19 der 22 gewählten Knoten bleiben stehen" in w.log.toPlainText()[-400:],
              w.log.toPlainText()[-200:])
    finally:
        _ohne_fragen(w)
        w._auswahl_leeren()
        w._undo.clear()


def test_stab_loeschen_ueberall_gleich():
    """Entf in der Ansicht, Rechtsklick und Baum nehmen die abgeleiteten Elementlasten
    eines Stabs mit (``Model.stab_loeschen``): dieselbe Last, dieselbe Rechnung."""
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    fragen = _fragen(w, True)
    ia = w.plotter.interactor

    def geo(m, elemente):
        return [b for b in m.load_cases["LF1"].beam_loads
                if getattr(b, "_geo", False) and int(b.elem) in elemente]
    try:
        for weg in ("Entf", "Rechtsklick", "Baum"):
            _linienlast_auf_riegel(w, app)
            elemente = {int(e) for e in w.model.members["Riegel"].elements}
            n_vor = len(geo(w.model, elemente))
            if weg == "Entf":
                _waehlen(w, staebe=["Riegel"])
                _ansicht(w, app)
                QtTest.QTest.keyClick(ia, K.Key_Delete)
            elif weg == "Rechtsklick":
                w.auswahl_loeschen("stab", ["Riegel"])
            else:
                w._baum_loeschen("stab", "Riegel")
            app.processEvents()
            check(f"Stab löschen per {weg}: seine abgeleiteten Elementlasten sind weg",
                  n_vor > 0 and "Riegel" not in w.model.members and not geo(w.model, elemente),
                  f"{n_vor} -> {len(geo(w.model, elemente))} Elementlasten")
    finally:
        _ohne_fragen(w)
        w._auswahl_leeren()


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_entf_in_der_ansicht, test_entf_lager_und_last, test_entf_nur_bei_fokus_in_der_ansicht,
              test_einzeltasten_in_der_ansicht, test_einzeltasten_nie_im_textfeld,
              test_skizzenfenster_nimmt_seine_tasten, test_skizzenfenster_textfelder_behalten_ihre_tasten,
              test_skizzenfenster_ohne_hauptfenster_wirkung_auf_andere_tasten,
              test_liste_und_code_stimmen_ueberein,
              test_entf_nimmt_nur_hervorgehobenes_nicht_mit, test_ansicht_nimmt_den_fokus_nur_per_linksklick,
              test_einzeltaste_ersetzt_keine_geaenderte_maske, test_entf_und_tasten_waehrend_der_rechnung,
              test_rueckfrage_nennt_die_folgen, test_nichts_geloescht_laesst_die_stapel_in_ruhe,
              test_entf_grosse_auswahl_ist_schnell, test_entf_teils_benutzte_knoten,
              test_stab_loeschen_ueberall_gleich):
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
