"""
Nachtrag zur Fehlerliste vom 06.10.2026, Paket Q10 (07.10.2026): N10, N20, N21, N34, N35.
(N19, das Stellungsformular im Browser, steht in tests/test_web.py und tests/render_check.js.)

* N10 - Die Layerliste blieb nach Rueckgaengig, Wiederholen, Neu und Oeffnen
  veraltet: _modell_setzen und refresh_all riefen LayerFenster.fuellen() nicht
  auf (nach „Layer anlegen“ und w.undo() stand der Layer noch in der Tabelle).
* N20 - Ein Stab in der Maske auf einen vorhandenen Namen umbenannt: _objekt_
  uebernehmen legte den Rueckgaengig-Schritt an, bevor Model.stab_umbenennen den
  Namen abwies (ValueError, als rotes Fenster „Fehler“ gemeldet). Der Rahmen des
  „Uebernehmen“ nahm den Schritt in der Maske wieder weg; wer die Funktion selbst
  ruft, behielt einen leeren Schritt. Jetzt wird vor dem Merken geprueft und als
  Hinweis gemeldet, wie beim Anlegen.
* N21 - Der Modellbaum meldete Sperrgruende beim Loeschen (Stab mit
  Verformungsnachweis, benutzter Knoten, ...) als rotes ``error``; nach der
  9b-Regel ist das ein Bedienhinweis.
* N34 - Die Zusatzknoepfe im Fuss einer Maske standen in einer Zeile ohne
  Umbruch: die Wasserdruckmaske zeigte sechs Knoepfe zu je 68 px, gebraucht
  wurden 91 bis 159 px (Segoe UI), bei 1920 x 1000 und bei 1366 x 740 gleich.
  Jetzt bricht die Reihe um (masken.Knopfzeilen). Gemessen wird mit
  nachgeladener Schrift; ohne Segoe UI sind die Breiten Kaestchenwerte (die
  Pruefung gilt dann trotzdem, die Zahlen sind aber andere).
* N35 - Der Kopfkommentar von masken.py sagte „Esc schliesst“, im Programmfenster
  gehoert Esc aber dem Kuerzel „Alles deselektieren“. Der Esc-Zweig in
  Maske.keyPressEvent bleibt (eine Maske ohne Hauptfenster und ein zugeschicktes
  Tastenereignis erreichen ihn), der Kommentar sagt es.

Aufruf:  python -m tests.test_nachtrag_q10
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_UNGESPEICHERT"] = "verwerfen"
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_nachtrag_q10_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
#: Ausnahmen, die waehrend der Pruefung ueber sys.excepthook liefen
AUSNAHMEN = []

#: Schriften wie scratchpad/mit_schrift.py (Beleg der Fehlerliste)
SCHRIFTEN = ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "segoeuii.ttf", "segoeuil.ttf",
             "seguisym.ttf", "arial.ttf", "consola.ttf", "cour.ttf")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _schrift_laden() -> bool:
    """Segoe UI und verwandte Schriften nachladen (vor dem Fenster). True,
    wenn danach Segoe UI bekannt ist: offscreen kennt Qt sonst keine Schrift
    und misst Kaestchen, etwa doppelt so breit."""
    from PySide6 import QtGui
    _app()
    for f in SCHRIFTEN:
        pfad = os.path.join("C:/Windows/Fonts", f)
        if os.path.exists(pfad):
            QtGui.QFontDatabase.addApplicationFont(pfad)
    return "Segoe UI" in QtGui.QFontDatabase.families()


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    app = _app()
    _FENSTER["schrift"] = _schrift_laden()
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    app.processEvents()
    # Rueckfragen und Meldungen nie auf dem Bildschirm stehen lassen
    w._fragen_knoepfe = lambda *a, **k: True
    w._bestaetigen = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste)
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    alt = sys.excepthook

    def haken(t, v, tb):
        AUSNAHMEN.append(f"{t.__name__}: {v}")
        alt(t, v, tb)
    sys.excepthook = haken
    _FENSTER.update(w=w, app=app)
    return w, app


def _ruhe(app, n=3):
    for _ in range(n):
        app.processEvents()


def _rahmen(w):
    """Ein kleines Modell: zwei Staebe S1 (E0), S2 (E1) auf drei Knoten, ein freier
    Knoten 3, ein Lager am Knoten 0; frische Rueckgaengig-Stapel."""
    from statik3d.model import Material, Section, Member
    w.maskenrand.schliessen()
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 200"))
    n = [m.add_node(3.0 * i, 0.0, 0.0) for i in range(3)]
    e0 = m.add_element("beam", [n[0], n[1]], "S355", "HEB 200")
    e1 = m.add_element("beam", [n[1], n[2]], "S355", "HEB 200")
    m.members["S1"] = Member("S1", [e0])
    m.members["S2"] = Member("S2", [e1])
    m.fix(n[0], "all")
    m.add_node(9.0, 9.0, 9.0)
    w.refresh_all()
    w._undo_init()
    w._undo_knoepfe()
    _ruhe(_FENSTER["app"])
    return m


# ---------------------------------------------------------------- N10 ----
def _zeilen(f) -> list:
    """Die Namen in der ersten Spalte der Layerliste."""
    return [f.tabelle.item(z, 0).text() for z in range(f.tabelle.rowCount())]


def test_n10_layerliste_folgt_dem_modell():
    import numpy as np
    from statik3d.model import Model, Material, Section
    w, app = _fenster()
    _rahmen(w)
    # Kontrolle: ohne offene Layerliste legt Rueckgaengig kein Fenster an
    w._layer_fenster = None
    w.selection = np.array([0, 1], dtype=int)
    w.layer_aus_auswahl("Vorab")
    w.undo()
    _ruhe(app)
    check("Kontrolle: Rückgängig ohne Layerliste legt keine an", w._layer_fenster is None)

    w.selection = np.array([0, 1], dtype=int)
    w.layerliste_zeigen()
    _ruhe(app)
    f = w._layer_fenster
    w.layer_aus_auswahl("Deckel")
    _ruhe(app)
    check("Layer angelegt: Liste und Modell stimmen überein", _zeilen(f) == ["Deckel"] == list(w.model.layer),
          f"Liste {_zeilen(f)}, Modell {list(w.model.layer)}")
    w.undo()
    _ruhe(app)
    check("nach Rückgängig im Hauptfenster: die Liste ist leer wie das Modell",
          _zeilen(f) == [] and list(w.model.layer) == [], f"Liste {_zeilen(f)}, Modell {list(w.model.layer)}")
    w.redo()
    _ruhe(app)
    check("nach Wiederholen: der Layer steht wieder in der Liste",
          _zeilen(f) == ["Deckel"] and list(w.model.layer) == ["Deckel"],
          f"Liste {_zeilen(f)}, Modell {list(w.model.layer)}")
    # Kontrolle: ein zweiter Layer, dann Rueckgaengig - der erste bleibt markiert
    w.selection = np.array([2], dtype=int)
    w.layer_aus_auswahl("Zweiter")
    _ruhe(app)
    f.tabelle.selectRow(f.zeile_von("Deckel"))
    w.undo()
    _ruhe(app)
    check("Kontrolle: Rückgängig nimmt „Zweiter“ aus der Liste, die Markierung bleibt bei „Deckel“",
          _zeilen(f) == ["Deckel"] and f.gewaehlt() == "Deckel", f"Liste {_zeilen(f)}, markiert {f.gewaehlt()!r}")

    w.new_model()
    _ruhe(app)
    check("nach Neu: die Liste ist leer", _zeilen(f) == [] and not w.model.layer,
          f"Liste {_zeilen(f)}, Modell {list(w.model.layer)}")

    # Oeffnen: eine Datei mit zwei Layern
    m2 = Model("Mit Layern")
    m2.add_material(Material.steel("S355"))
    m2.add_section(Section.from_profile("HEB 200"))
    for x in (0, 3, 6):
        m2.add_node(x, 0, 0)
    m2.layer_anlegen("Süd", knoten=[0, 1])
    m2.layer_anlegen("Nord", knoten=[2])
    pfad = os.path.join(tempfile.mkdtemp(prefix="q10_layer_"), "mit_layern.json")
    m2.save(pfad)
    ok = w.modell_laden(pfad, fragen=False)
    _ruhe(app)
    check("nach Öffnen: die Liste zeigt die Layer der Datei",
          ok and sorted(_zeilen(f)) == ["Nord", "Süd"] and set(w.model.layer) == {"Nord", "Süd"},
          f"Liste {_zeilen(f)}, Modell {list(w.model.layer)}")
    w.new_model()
    _ruhe(app)
    f.close()


# ---------------------------------------------------------------- N20 ----
def test_n20_umbenennen_auf_vorhandenen_namen():
    from tests.meldungen import abfangen
    w, app = _fenster()
    m = _rahmen(w)
    # die Funktion selbst (ohne den Rahmen des „Uebernehmen“ einer Maske)
    mel = abfangen(w)
    n0 = len(w._undo)
    stand0 = w._stand
    w._objekt_uebernehmen("stab", "S2", {"name": "S1", "elemente": "1", "design": True})
    _ruhe(app)
    mel.zurueck()
    check("Stab S2 → „S1“ (Funktion): ein Hinweis „gibt es schon“, kein rotes Fenster",
          mel.hinweis_mit("S1", "gibt es schon") and not mel.fehler, str(mel.eintraege))
    check("… kein leerer Rückgängig-Schritt, der Änderungsstand bleibt",
          len(w._undo) == n0 and w._stand == stand0, f"Schritte {n0} -> {len(w._undo)}")
    check("… beide Stäbe heißen weiter wie vorher", list(m.members) == ["S1", "S2"], str(list(m.members)))

    # dasselbe in der Maske
    n0 = len(w._undo)
    w._objektmaske("stab", "S2")
    _ruhe(app)
    mk = w.maskenrand.maske
    mk.setzen("name", "S1")
    mel = abfangen(w)
    ok = mk.anwenden()
    _ruhe(app)
    mel.zurueck()
    check("Stab S2 → „S1“ (Maske): „Übernehmen“ scheitert mit einem Hinweis, kein rotes Fenster",
          ok is False and mel.hinweis_mit("S1", "gibt es schon") and not mel.fehler,
          f"ok {ok}, {mel.eintraege}")
    check("… kein Schritt, die Namen bleiben", len(w._undo) == n0 and list(m.members) == ["S1", "S2"],
          f"Schritte {n0} -> {len(w._undo)}")
    w.maskenrand.schliessen()

    # Kontrolle: ein freier Name geht, genau ein Schritt
    n0 = len(w._undo)
    mel = abfangen(w)
    w._objekt_uebernehmen("stab", "S2", {"name": "Riegel", "elemente": "1", "design": True})
    _ruhe(app)
    mel.zurueck()
    check("Kontrolle: Stab S2 → „Riegel“ geht, genau ein Schritt, keine Meldung",
          list(m.members) == ["S1", "Riegel"] and len(w._undo) == n0 + 1 and not mel.alle,
          f"{list(m.members)}, Schritte {n0} -> {len(w._undo)}, {mel.eintraege}")
    w.maskenrand.schliessen()


# ---------------------------------------------------------------- N21 ----
def test_n21_sperrgrund_beim_loeschen_ist_hinweis():
    from tests.meldungen import abfangen
    w, app = _fenster()
    m = _rahmen(w)
    m.add_verformungsgrenze("VG1", art="stab", stab="S2", wert=300.0)
    w.refresh_all()
    w._undo_init()
    w._undo_knoepfe()
    for art, name, teil in (("stab", "S2", "VG1"), ("knoten", "1", "wird benutzt von")):
        mel = abfangen(w)
        n0 = len(w._undo)
        nn0, st0 = m.nn, list(m.members)
        w._baum_loeschen(art, name)
        _ruhe(app)
        mel.zurueck()
        check(f"Modellbaum, {art} {name}: der Sperrgrund kommt als Hinweis, kein rotes Fenster",
              mel.hinweis_mit(teil) and not mel.fehler, str(mel.eintraege))
        check(f"… {art} {name} bleibt, kein Rückgängig-Schritt",
              m.nn == nn0 and list(m.members) == st0 and len(w._undo) == n0,
              f"Knoten {nn0} -> {m.nn}, Schritte {n0} -> {len(w._undo)}")
    # Kontrolle: ein freier Knoten wird geloescht, ohne Meldung der Sperre
    mel = abfangen(w)
    n0 = len(w._undo)
    nn0 = m.nn
    w._baum_loeschen("knoten", str(nn0 - 1))
    _ruhe(app)
    mel.zurueck()
    check("Kontrolle: ein freier Knoten geht, ein Schritt, weder Hinweis noch Fehler",
          m.nn == nn0 - 1 and len(w._undo) == n0 + 1 and not mel.alle, f"{m.nn}, {mel.eintraege}")
    # Kontrolle: mehrere auf einmal - die Gruende stehen in der Zusammenfassung, nichts Rotes
    mel = abfangen(w)
    w._baum_viele_loeschen("stab", ["S2"])
    _ruhe(app)
    mel.zurueck()
    check("Kontrolle: mehrere auf einmal - der Grund steht in der Zusammenfassung, kein rotes Fenster",
          not mel.fehler and "S2" in list(m.members), str(mel.eintraege))


# ---------------------------------------------------------------- N35 ----
def test_n35_esc_kommentar():
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtTest import QTest
    from statik3d.gui import masken as msk
    from statik3d.gui import profilmaske as pm
    kopf = msk.__doc__ or ""
    check("Kopfkommentar von masken.py: der Satz „Esc schliesst, Eingabe bestaetigt“ steht nicht mehr da",
          "**Esc** schliesst, **Eingabe**" not in kopf and "Eingabe** bestaetigt" in kopf)
    check("… er sagt, was im Programmfenster gilt: Esc ist „Alles deselektieren“, ✕ schliesst",
          "Alles deselektieren" in kopf and "✕" in kopf)
    check("Maske: die Klassenbeschreibung nennt nicht mehr „Esc oder Kreuz“",
          "Esc oder Kreuz" not in (msk.Maske.__doc__ or ""))

    # die Gruende, den Esc-Zweig zu behalten: er wird erreicht, solange es kein
    # Hauptfenster gibt (sein Kuerzel gilt in der ganzen Anwendung, siehe unten)
    assert "w" not in _FENSTER, "N35 muss vor allen Pruefungen mit Hauptfenster laufen"
    app = _app()
    allein = msk.Maske("allein", [msk.Feld("x", "x", "zahl", 1.0)])
    allein.show()
    app.processEvents()
    zu = []
    allein.geschlossen.connect(lambda: zu.append(1))
    QtWidgets.QApplication.sendEvent(allein, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape,
                                                             QtCore.Qt.NoModifier))
    check("Esc an einer Maske ohne Hauptfenster schließt sie (der Zweig bleibt)",
          not allein.isVisible() and len(zu) == 1)
    q = pm.QuerschnittMaske()
    q.show()
    app.processEvents()
    zq = []
    q.geschlossen.connect(lambda: zq.append(1))
    QtWidgets.QApplication.sendEvent(q, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape,
                                                        QtCore.Qt.NoModifier))
    check("Esc an der Querschnittmaske ohne Hauptfenster schließt sie (der Zweig bleibt)",
          not q.isVisible() and len(zq) == 1)
    # ... und mit Hauptfenster erreicht ihn kein Esc: weder ein Tastendruck in
    # einem Feld der Maske noch ein zugeschicktes Ereignis (QApplication.notify
    # fragt das Kuerzel „Alles deselektieren“ auch dafuer ab)
    w, app = _fenster()
    _rahmen(w)
    w.maske_knoten()
    _ruhe(app)
    mk = w.maskenrand.maske
    feld = next(iter(mk._felder.values()))
    w.activateWindow()
    feld.setFocus()
    _ruhe(app)
    QTest.keyClick(feld, QtCore.Qt.Key_Escape)
    _ruhe(app)
    check("Programmfenster: ein Tastendruck Esc schließt keine Maske (Kürzel „Alles deselektieren“)",
          w.maskenrand.maske is mk and w.maskenrand.offen())
    QtWidgets.QApplication.sendEvent(mk, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape,
                                                         QtCore.Qt.NoModifier))
    _ruhe(app)
    check("… auch ein an die Maske geschicktes Esc nicht", w.maskenrand.maske is mk and w.maskenrand.offen())
    w.querschnitt_neu()
    _ruhe(app)
    q2 = w.maskenrand.maske
    zeile = q2.findChildren(QtWidgets.QLineEdit)[0]
    zeile.setFocus()
    _ruhe(app)
    QTest.keyClick(zeile, QtCore.Qt.Key_Escape)
    _ruhe(app)
    check("… und in der Querschnittmaske schließt ein Tastendruck Esc ebenso nichts",
          w.maskenrand.maske is q2 and w.maskenrand.offen())
    w.maskenrand.schliessen()
    _ruhe(app)


# ---------------------------------------------------------------- N34 ----
#: Zusatzknoepfe der Masken des Programms (Texte aus main.py und elementmasken.py)
GRUPPEN = {
    "Layer": ["Layerliste …"],
    "Stab": ["Nachweisparameter …"],
    "Verbindung": ["Löschen"],
    "Lastfall": ["Lasten in der Tabelle"],
    "Querschnitte": ["Neu aus Profil …"],
    "Liniengelenk": ["Auf gewählte Stäbe setzen"],
    "Stellung": ["Auswahl deaktivieren", "Auswahl aktivieren", "Alle aktivieren"],
    "Lager": ["Bettung übernehmen", "Schlupf, Reibung …", "Lager löschen"],
    "Geofläche": ["Randlinien anklicken"],
    "Geokörper": ["Randflächen anklicken"],
    "Kontaktbedingung": ["Spalt-Vorschau", "Kontaktfugen ausführen"],
    "Subsystem": ["Auswahl neu lesen"],
    "Situation": ["Alle Lastfälle und Kombinationen"],
    "Lastart": ["Diese Lasten löschen"],
    "Last": ["Löschen"],
    "Ermüdung": ["Auswahl übernehmen", "Kerbfall ermitteln"],
    "Vernetzer": ["Vernetzer installieren…"],
    "Netzgüte": ["Schlechte wählen", "Aus"],
    "Wasserdruck": ["Auswahl übernehmen", "Benetzt anklicken", "Dichtlinie anklicken", "OW-Fläche anklicken",
                    "UW-Fläche anklicken", "Kennwerte"],
    "Wind": ["Auswahl übernehmen", "Kennwerte"],
    "Elementübersicht": ["Fingerabdruck", "Färbung aus", "Alles zeigen"],
    # nur zum Messen: mehr Knoepfe und laengere Texte, als das Programm hat
    "Probe: acht Knöpfe": ["Auswahl übernehmen", "Benetzt anklicken", "Dichtlinie anklicken",
                           "OW-Fläche anklicken", "UW-Fläche anklicken", "Kennwerte", "Alles zeigen", "Aus"],
    "Probe: langer Text": ["Schlupf, Reibung, Grenzkraft …", "Alle Lastfälle und Kombinationen"],
}


def _rechteck(b, mk):
    from PySide6 import QtCore
    p = b.mapTo(mk, QtCore.QPoint(0, 0))
    return QtCore.QRect(p, b.size())


def _lage(mk) -> dict:
    """Wie die Zusatzknoepfe einer Maske liegen: abgeschnitten (Breite oder Hoehe
    kleiner als der Wunsch), ausserhalb der Maske, einander oder dem Hauptknopf
    im Weg."""
    knoepfe = dict(mk.zusatzknoepfe)
    ab, drausen, im_weg = [], [], []
    rechtecke = {t: _rechteck(b, mk) for t, b in knoepfe.items()}
    haupt = _rechteck(mk.btn_anwenden, mk)
    for t, b in knoepfe.items():
        sh = b.sizeHint()
        if b.width() < sh.width() or b.height() < sh.height():
            ab.append(f"{t} {b.width()}x{b.height()}/{sh.width()}x{sh.height()}")
        if not mk.rect().contains(rechtecke[t]):
            drausen.append(t)
    namen = list(knoepfe)
    for i, a in enumerate(namen):
        for c in namen[i + 1:]:
            if rechtecke[a].intersects(rechtecke[c]):
                im_weg.append(f"{a} / {c}")
        if rechtecke[a].intersects(haupt):
            im_weg.append(f"{a} / {mk.btn_anwenden.text()}")
    zeilen = len({r.y() for r in rechtecke.values()})
    return {"abgeschnitten": ab, "ausserhalb": drausen, "im_weg": im_weg, "zeilen": zeilen,
            "breiten": "; ".join(f"„{t}“ {b.width()}/{b.sizeHint().width()}" for t, b in knoepfe.items())}


def _lage_gut(lage) -> bool:
    return not (lage["abgeschnitten"] or lage["ausserhalb"] or lage["im_weg"])


def test_n34_zusatzknoepfe_brechen_um():
    from statik3d.gui import masken as msk
    w, app = _fenster()
    _rahmen(w)
    schrift = _FENSTER.get("schrift")
    print(f"     {'mit Segoe UI' if schrift else 'ohne Segoe UI - Breiten sind Kästchenwerte'}")
    for breite, hoehe in ((1920, 1000), (1366, 740)):
        w.resize(breite, hoehe)
        _ruhe(app)
        schlecht = []
        for name, texte in GRUPPEN.items():
            mk = msk.Maske(f"Probe {name}", [], zusatz=[(t, (lambda: None)) for t in texte])
            w.maske_erzeugen(mk)
            _ruhe(app, 5)
            lage = _lage(mk)
            if name in ("Wasserdruck", "Probe: acht Knöpfe"):
                print(f"     {name}: Maske {mk.width()} px, {lage['zeilen']} Zeile(n): {lage['breiten']}")
            if not _lage_gut(lage):
                schlecht.append(f"[{name}] {lage}")
        w.maskenrand.schliessen()
        _ruhe(app)
        check(f"{breite} x {hoehe}: bei keiner Maske ist ein Zusatzknopf abgeschnitten, außerhalb oder im Weg",
              not schlecht, "; ".join(schlecht)[:700])

        # die echten Masken
        w.maske_wasserdruck(None)
        _ruhe(app, 5)
        mk = w.maskenrand.maske
        lage = _lage(mk)
        check(f"{breite} x {hoehe}: echte Wasserdruckmaske - alle sechs Knöpfe ganz, nicht übereinander",
              len(mk.zusatzknoepfe) == 6 and _lage_gut(lage), f"{lage['zeilen']} Zeilen; {lage['breiten']}; {lage}")
        # die Maske hat dabei ihren Hauptknopf nicht verloren
        check("… „Lasten erzeugen“ bleibt in der Maske sichtbar und ganz",
              mk.rect().contains(_rechteck(mk.btn_anwenden, mk))
              and mk.btn_anwenden.width() >= mk.btn_anwenden.sizeHint().width(),
              f"{_rechteck(mk.btn_anwenden, mk)} in {mk.rect()}")
        w.maskenrand.schliessen()
        _ruhe(app)
        w.maske_wind(None)
        _ruhe(app, 5)
        mk = w.maskenrand.maske
        lage = _lage(mk)
        check(f"{breite} x {hoehe}: echte Windmaske - Knöpfe ganz", len(mk.zusatzknoepfe) == 2 and _lage_gut(lage),
              lage["breiten"])
        w.maskenrand.schliessen()
        _ruhe(app)
        w._objektmaske("lager_einzeln", "0")
        _ruhe(app, 5)
        mk = w.maskenrand.maske
        lage = _lage(mk)
        check(f"{breite} x {hoehe}: echte Lagermaske - Knöpfe ganz", len(mk.zusatzknoepfe) == 3 and _lage_gut(lage),
              lage["breiten"])
        w.maskenrand.schliessen()
        _ruhe(app)
    w.resize(1600, 1000)
    _ruhe(app)


def test_n34_knopfzeilen_fuer_sich():
    """Die Reihe allein: Zeilen nach Breite, beim Verbreitern wieder weniger."""
    from PySide6 import QtWidgets
    from statik3d.gui import masken as msk
    app = _app()
    zv = msk.Knopfzeilen.zeilen_verteilen
    breiten = [159, 132, 141, 152, 151, 91]
    check("Verteilen: sechs Knöpfe in 438 px ergeben drei Zeilen zu zwei",
          zv(breiten, 438, 6) == [[0, 1], [2, 3], [4, 5]], str(zv(breiten, 438, 6)))
    check("… in 1000 px eine Zeile", zv(breiten, 1000, 6) == [[0, 1, 2, 3, 4, 5]])
    check("… in 100 px jeder Knopf allein (zu breit bleibt zu breit, kein Absturz)",
          zv(breiten, 100, 6) == [[0], [1], [2], [3], [4], [5]])
    check("… ohne Knöpfe keine Zeile", zv([], 438, 6) == [])
    check("… genau passend (159 + 6 + 132 = 297) bleibt in einer Zeile, einen Bildpunkt weniger bricht um",
          zv([159, 132], 297, 6) == [[0, 1]] and zv([159, 132], 296, 6) == [[0], [1]])

    reihe = msk.Knopfzeilen()
    for t in ("Auswahl übernehmen", "Benetzt anklicken", "Dichtlinie anklicken",
              "OW-Fläche anklicken", "UW-Fläche anklicken", "Kennwerte"):
        reihe.aufnehmen(QtWidgets.QPushButton(t, reihe))
    reihe.resize(440, 200)
    reihe.show()
    _ruhe(app, 5)
    ys = {b.y() for b in reihe.knoepfe()}
    check("440 px breit: mehrere Zeilen, kein Knopf schmaler als sein Wunsch",
          len(ys) >= 2 and all(b.width() >= b.sizeHint().width() for b in reihe.knoepfe()),
          f"{len(ys)} Zeilen, " + "; ".join(f"{b.width()}/{b.sizeHint().width()}" for b in reihe.knoepfe()))
    check("… jede Zeile füllt die Breite aus (der Rand des letzten Knopfs liegt bei 440)",
          max(b.x() + b.width() for b in reihe.knoepfe()) == 440,
          str(max(b.x() + b.width() for b in reihe.knoepfe())))
    h3 = reihe.minimumSizeHint().height()
    reihe.resize(2000, 200)
    _ruhe(app, 5)
    check("2000 px breit: eine Zeile, die gemeldete Höhe wird kleiner",
          len({b.y() for b in reihe.knoepfe()}) == 1 and reihe.minimumSizeHint().height() < h3,
          f"Höhe {h3} -> {reihe.minimumSizeHint().height()}")
    reihe.resize(300, 200)
    _ruhe(app, 5)
    check("300 px breit: wieder mehrere Zeilen, und die Höhe wächst mit",
          len({b.y() for b in reihe.knoepfe()}) >= 3 and reihe.minimumSizeHint().height() >= h3,
          f"{len({b.y() for b in reihe.knoepfe()})} Zeilen, Höhe {reihe.minimumSizeHint().height()}")
    # ein ausgeblendeter Knopf nimmt keinen Platz weg
    reihe.resize(440, 200)
    _ruhe(app, 5)
    list(reihe.knoepfe())[0].hide()
    _ruhe(app, 5)
    sichtbar = [b for b in reihe.knoepfe() if not b.isHidden()]
    check("ein ausgeblendeter Knopf nimmt keinen Platz weg: die übrigen rücken auf",
          bool(sichtbar) and min(b.y() for b in sichtbar) == 0 and min(b.x() for b in sichtbar) == 0,
          f"{[(b.x(), b.y()) for b in sichtbar]}")
    reihe.close()


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    # test_n35 zuerst: sein Teil ohne Hauptfenster braucht, dass es noch keines gibt
    for t in (test_n35_esc_kommentar, test_n10_layerliste_folgt_dem_modell,
              test_n20_umbenennen_auf_vorhandenen_namen, test_n21_sperrgrund_beim_loeschen_ist_hinweis,
              test_n34_knopfzeilen_fuer_sich, test_n34_zusatzknoepfe_brechen_um):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    check("keine Ausnahme über sys.excepthook", not AUSNAHMEN, "; ".join(AUSNAHMEN)[:300])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    # Kein w.close(): die Rueckfrage „Ungespeicherte Änderungen“ bliebe stehen
    os._exit(0 if n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
