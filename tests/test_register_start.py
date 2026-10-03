"""
Das Register Start als Arbeitsablauf (Plan-Teilpaket 12d, 03.10.2026).

Bis zum 03.10.2026 trug das Register Start die Gruppen Zwischenablage,
Auswahl, Modell prüfen und Berechnen - Rückgängig, Wiederholen, die
Auswahlbefehle und die Modellprüfung, aber keinen der Befehle, mit denen man
ein Modell aufbaut. Die standen verstreut in sechs anderen Registern. Jetzt
steht der Ablauf in einer Reihe, von links nach rechts:

    Modell     Knoten, Stab
    Lager      Knotenlager
    Lasten     Linienlast, Lastfälle
    Netz       Vernetzen
    Prüfen     Prüfen (und die drei Prüfwerkzeuge)
    Rechnen    Berechnen
    Auswerten  Ergebnisse, Nachweise EC3, Bericht
    Bearbeiten Rückgängig, Wiederholen und die Auswahl, in einem Menü

Geprüft wird am echten Hauptfenster (offscreen):

* die elf Ablaufbefehle stehen in dieser Reihenfolge und in diesen Gruppen;
* **dieselben Befehle, keine neuen**: jeder Knopf führt dieselbe Aktion wie sein
  Original (derselbe Python-Gegenstand), mit demselben Symbol und Hinweis; ein
  Klick ruft dieselbe Funktion auf wie der Klick im Original, die Masken
  öffnen sich gleich (die schweren Funktionen - Vernetzen, Berechnen,
  Nachweise, Bericht - zeichnet die Prüfung nur auf, statt sie zu rechnen);
* kein Tastenkürzel wird doppelt vergeben: kein Befehl ist hinzugekommen, an
  F5, Strg+R, Strg+A, Strg+Z und Esc hängt genau eine Aktion, und echte
  Tastendrücke lösen sie aus, ohne dass Qt „Ambiguous shortcut“ meldet;
* kein früherer Befehl des Registers Start ist verschwunden: jeder steht noch im
  Register, sichtbar oder im Menü „Bearbeiten ▾“, und die Befehle, die auch in
  der Schnellzugriffsleiste oder der Glasleiste stehen, dort als dieselbe
  Aktion; ein Schalter an zwei Stellen zeigt an beiden denselben Zustand;
* das Register passt bei 1366 px und bei 1280 px (1920 px bei 150 % Skalierung)
  ohne gekürzte Beschriftung und ohne Rollpfeile - gemessen wie in
  ``tests.test_glasleiste_ribbon``;
* das Programm startet im Register Start, nach der Rechnung steht das Ribbon
  auf Ergebnisse.

Aufruf:  python -m tests.test_register_start
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
# Offscreen findet Qt unter Windows sonst keine Schrift und misst jedes Zeichen
# als Kasten (siehe tests.test_glasleiste_ribbon); mit den Schriften des Systems
# misst es dieselbe Segoe UI wie der Desktop.
if sys.platform.startswith("win"):
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                                                         "Fonts"))
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_registerstart_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
#: Aufrufe der aufgezeichneten Funktionen: (Name, Argumente) in der Reihenfolge
AUFRUFE = []

#: Die elf Ablaufbefehle, wie der Anwender sie nennt: (Knopf in Start, Gruppe in
#: Start, Register des Originals, Funktion, Argumente). „Prüfen“ gibt es nur im
#: Register Start; „Berechnen“ steht außerdem im Register Berechnung (derselbe
#: Befehl, ein zweiter Knopf).
ABLAUF = (
    ("Knoten", "Modell", "Geometrie", "maske_knoten", ()),
    ("Stab", "Modell", "Struktur", "maske_stab", ()),
    ("Knotenlager", "Lager", "Lager / Kontakt", "maske_lager", ()),
    ("Linienlast", "Lasten", "Lasten", "maske_linienlast", ()),
    ("Lastfälle", "Lasten", "Lasten", "maske_zeigen", ("Lastfälle",)),
    ("Vernetzen", "Netz", "Netz", "geometrie_vernetzen", ()),
    ("Prüfen", "Prüfen", "", "do_check", ()),
    ("Berechnen", "Rechnen", "Berechnung", "do_solve", ("all",)),
    ("Ergebnisse", "Auswerten", "Ergebnisse", "maske_zeigen", ("Ergebnisse",)),
    ("Nachweise EC3", "Auswerten", "Nachweise", "do_design", ()),
    ("Bericht", "Auswerten", "Bericht", "make_report", ()),
)
#: Die Gruppen von links nach rechts
GRUPPEN = ["Modell", "Lager", "Lasten", "Netz", "Prüfen", "Rechnen", "Auswerten", "Bearbeiten"]
#: Funktionen, die die Prüfung nur aufzeichnet: sie rechnen, vernetzen oder
#: öffnen Dateidialoge. Die übrigen laufen wirklich (sie öffnen eine Maske).
NUR_AUFZEICHNEN = ("geometrie_vernetzen", "do_solve", "do_design", "make_report")
AUFZEICHNEN = ("maske_knoten", "maske_stab", "maske_lager", "maske_linienlast", "maske_zeigen",
               "do_check", *NUR_AUFZEICHNEN)

#: Die Befehle des Registers Start vor dem 03.10.2026 (Stand 68db45b)
FRUEHER = ("Rückgängig", "Wiederholen", "Alles deselektieren", "Alles auswählen", "Auswahl umkehren",
           "Intelligente Auswahl", "Prüfen", "Doppelte Knoten zusammenführen",
           "Freie Stabenden anschließen…", "Freie Bewegungen suchen", "Berechnen")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _aufzeichnen():
    """Die Funktionen der Ablaufbefehle in MainWindow durch Aufzeichner ersetzen -
    **bevor** das Fenster entsteht: die Aktionen des Ribbons halten die gebundene
    Methode, die sie beim Aufbau vorfinden."""
    from statik3d.gui.main import MainWindow
    for name in AUFZEICHNEN:
        original = getattr(MainWindow, name)

        def ersatz(self, *a, _n=name, _o=original, **k):
            AUFRUFE.append((_n, a))
            if _n not in NUR_AUFZEICHNEN:
                return _o(self, *a, **k)
            return None
        setattr(MainWindow, name, ersatz)


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    _aufzeichnen()
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    # Rückfragen und Meldungen nie auf dem Bildschirm stehen lassen
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    # Fehler und Hinweise gemeinsam abfangen (tests/meldungen.py, Paket 9b): die
    # Liste bekommt beide, w.meldungen wertet sie getrennt aus
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste)
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    w.activateWindow()
    app.processEvents()
    # der Zustand des frisch gestarteten Fensters, bevor etwas anderes ihn ändert
    _FENSTER["start_register"] = w.ribbon.tabs.tabText(w.ribbon.tabs.currentIndex())
    w.load_example("hall")
    _ruhe()
    _FENSTER.update(w=w, app=app)
    return w, app


def _ruhe(n: int = 4):
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance()
    for _ in range(n):
        app.processEvents()


def _aktiv_machen(w) -> bool:
    """Das Hauptfenster zum aktiven Fenster machen: Qt löst Kürzel und
    QTest-Tastendrücke nur im aktiven Fenster aus. Erst ein paar Versuche mit
    show, raise_ und activateWindow; klappt es nicht, sagt die Prüfung es laut
    (kein stilles Ausweichen auf aktion.trigger())."""
    for _ in range(6):
        if w.isActiveWindow():
            return True
        w.show()
        w.raise_()
        w.activateWindow()
        _ruhe()
    return w.isActiveWindow()


def _start_offen(w):
    """Das Register Start aufgeklappt und vorn, wirklich sichtbar. Nach einer
    Größenänderung schaltet die Fensteraufteilung die Kompaktstufe über einen
    Zeitgeber (fenster.Fensteranordnung.nachfuehren) und klappt das Ribbon ein -
    kommt sie nach dem Aufklappen, wäre das Register beim Messen verborgen.
    Darum erst ausruhen, dann aufklappen, und nachsehen."""
    rb = w.ribbon
    _ruhe(10)
    reg = rb._register["Start"]
    for _ in range(4):
        if rb.eingeklappt():
            rb.einklappen(False)
        rb.zeigen("Start")
        _ruhe(10)
        if reg.isVisible():
            break
    return reg


def _start(w):
    """Das Register Start, aufgeklappt und vorn, und seine Knöpfe von links nach
    rechts (bei gleichem x von oben nach unten): [(Knopf, Gruppe, x)]."""
    from PySide6 import QtCore, QtWidgets
    reg = _start_offen(w)
    aus = []
    for b in reg.findChildren(QtWidgets.QToolButton):
        g = b.parent()
        while g is not None and g.objectName() != "ribbongruppe":
            g = g.parent()
        p = b.mapTo(reg, QtCore.QPoint(0, 0))
        aus.append((p.x(), p.y(), b, g._name if g is not None else "?"))
    aus.sort(key=lambda t: (t[0], t[1]))
    return reg, [(b, gruppe, x) for x, _y, b, gruppe in aus]


def _befehl(w, register: str, text: str) -> list:
    return [b for b in w.ribbon.befehle if b.register == register and b.text == text]


def _knopf_in(w, register: str, aktion):
    """Der Knopf im Register, der diese Aktion führt (kein Menüeintrag)."""
    from PySide6 import QtWidgets
    reg = w.ribbon._register[register]
    return [b for b in reg.findChildren(QtWidgets.QToolButton) if b.defaultAction() is aktion]


def _traegt(knopf, aktion) -> bool:
    """Führt dieser Knopf die Aktion - selbst oder in seinem Menü?"""
    if knopf.defaultAction() is aktion:
        return True
    stapel = [knopf.menu()] if knopf.menu() is not None else []
    while stapel:
        m = stapel.pop()
        for a in m.actions():
            if a is aktion:
                return True
            if a.menu() is not None:
                stapel.append(a.menu())
    return False


def _zustand(w) -> tuple:
    """Was rechts zu sehen ist: offene Maske samt Feldern, Titel des Docks,
    Eingabe-Register."""
    rand = w.maskenrand
    mk = rand.maske if rand.offen() else None
    felder = sorted(getattr(mk, "_felder", None) or {}) if mk is not None else []
    return (getattr(mk, "titel", None), felder, w.eingaben_dock.windowTitle(),
            w.tabs.tabText(w.tabs.currentIndex()) if w.tabs.isVisible() else None)


def _grundzustand(w):
    if w.maskenrand.offen():
        w.maskenrand.schliessen()
    _ruhe()
    AUFRUFE.clear()


# --------------------------------------------------------------------------
def test_reihenfolge():
    from PySide6 import QtWidgets
    w, _app = _fenster()
    w.resize(1920, 1080)
    _ruhe()
    reg, knoepfe = _start(w)
    erwartet = [t for t, *_r in ABLAUF]
    gefunden = [b.text() for b, _g, _x in knoepfe if b.text() in erwartet]
    check("Start: die elf Ablaufbefehle stehen von links nach rechts in der genannten Reihenfolge",
          gefunden == erwartet, f"{gefunden}")
    titel = sorted((lb.mapTo(reg, lb.rect().topLeft()).x(), lb.text())
                   for lb in reg.findChildren(QtWidgets.QLabel, "gruppentitel") if lb.isVisible())
    check("… in beschrifteten Gruppen: Modell, Lager, Lasten, Netz, Prüfen, Rechnen, Auswerten, Bearbeiten",
          [t for _x, t in titel] == GRUPPEN, str([t for _x, t in titel]))
    falsch = []
    for text, gruppe, *_r in ABLAUF:
        b = next((b for b, g, _x in knoepfe if b.text() == text), None)
        g = next((g for b_, g, _x in knoepfe if b_ is b), None)
        if g != gruppe:
            falsch.append(f"{text}: {g} statt {gruppe}")
    check("… jeder Befehl in seiner Gruppe (Knoten und Stab: Modell; Linienlast und Lastfälle: Lasten; "
          "Ergebnisse, Nachweise EC3 und Bericht: Auswerten)", not falsch, "; ".join(falsch))
    gross = [b.text() for b, _g, _x in knoepfe if b.objectName() == "ribbongross"]
    check("… die elf sind große Knöpfe; danach, am Ende des Registers, das Menü „Bearbeiten ▾“",
          all(b.objectName() == "ribbongross" for b, _g, _x in knoepfe if b.text() in erwartet)
          and gross[-1] == "Bearbeiten ▾", str(gross))


def test_dieselben_befehle():
    w, app = _fenster()
    w.resize(1920, 1080)
    _ruhe()
    reg, knoepfe = _start(w)
    nach_text = {b.text(): b for b, _g, _x in knoepfe}
    # Kein neuer Befehl: Start vermerkt genau die Befehle, die es vorher hatte
    # (Befehlssuche und Kürzelliste führen weiter zu den Originalen), und jeder
    # der anderen Ablaufbefehle ist in seinem Register genau einmal vermerkt.
    # (Der Schalter „Knoten“ in Ansicht heißt ebenso wie der Befehl in Geometrie.)
    # (Dazu kommt nur der Sucheintrag „Bearbeiten ▾“: er klappt das Menü auf.)
    in_start = sorted(b.text for b in w.ribbon.befehle if b.register == "Start")
    check("kein Befehl ist hinzugekommen: das Register Start vermerkt seine elf früheren Befehle und "
          "als Sucheintrag das Menü „Bearbeiten ▾“", in_start == sorted([*FRUEHER, "Bearbeiten ▾"]),
          str(in_start))
    # (Berechnen ist in Start vermerkt; sein zweiter Knopf in Berechnung ist kein Befehl)
    zu_viel = [f"{t} in {r}" for t, _g, r, *_x in ABLAUF if r not in ("", "Berechnung")
               and len(_befehl(w, r, t)) != 1]
    check("… jeder Ablaufbefehl aus einem anderen Register ist dort genau einmal vermerkt",
          not zu_viel, str(zu_viel))
    leer = _zustand_leer(w)
    for text, _gruppe, register, funktion, argumente in ABLAUF:
        start_knopf = nach_text.get(text)
        if not check(f"{text}: es gibt den Knopf im Register Start", start_knopf is not None):
            continue
        # „Prüfen“ gibt es nur in Start, „Berechnen“ ist dort zu Hause (ein zweiter Knopf in Berechnung)
        original = _befehl(w, register if register not in ("", "Berechnung") else "Start", text)
        aktion = original[0].aktion if len(original) == 1 else None
        zweite = _knopf_in(w, register, aktion) if register and aktion is not None else []
        check(f"{text}: derselbe Befehl wie im Original ({register or 'nur in Start'}) - dieselbe Aktion, "
              "derselbe Hinweis, dasselbe Symbol",
              aktion is not None and start_knopf.defaultAction() is aktion
              and (not register or (len(zweite) == 1 and zweite[0].toolTip() == start_knopf.toolTip()
                                    and zweite[0].icon().cacheKey() == start_knopf.icon().cacheKey()))
              and not start_knopf.icon().isNull() and bool(start_knopf.toolTip()),
              f"{len(original)} Befehl(e), {len(zweite)} Knopf im Original")
        # der Klick: dieselbe Funktion, dieselbe Maske
        _grundzustand(w)
        n_log = len(w.log.toPlainText())
        start_knopf.click()
        _ruhe()
        a_start, z_start = list(AUFRUFE), _zustand(w)
        neu = w.log.toPlainText()[n_log:]
        if not register:                       # Prüfen: es gibt kein anderes Original
            check(f"{text}: der Klick ruft {funktion} auf (Modellprüfung im Protokoll)",
                  a_start == [(funktion, argumente)] and "Modellprüfung" in neu, f"{a_start} {neu[:40]!r}")
            continue
        if len(zweite) != 1:
            continue
        _grundzustand(w)
        zweite[0].click()
        _ruhe()
        a_orig, z_orig = list(AUFRUFE), _zustand(w)
        if funktion in NUR_AUFZEICHNEN:
            check(f"{text}: der Klick ruft {funktion}{argumente} auf, genau wie im Original",
                  a_start == a_orig == [(funktion, argumente)], f"{a_start} / {a_orig}")
        else:
            check(f"{text}: der Klick ruft {funktion} auf und öffnet dieselbe Maske wie im Original",
                  (funktion, argumente) in a_start and a_start == a_orig and z_start == z_orig
                  and z_start != leer, f"{z_start} / {z_orig}")
    _grundzustand(w)
    w.ribbon.zeigen("Start")


def _zustand_leer(w) -> tuple:
    """Der Zustand ohne offene Maske (zum Vergleich: ein Klick muss etwas bewirkt haben)."""
    _grundzustand(w)
    return _zustand(w)


def test_berechnen_zwei_knoepfe():
    """„Berechnen“ gibt es als blauen Startknopf zweimal (Start, Berechnung): eine
    dritte Kopie bemängelt tests.test_glasleiste_ribbon; hier steht, dass beide
    dieselbe Aktion führen."""
    from PySide6 import QtWidgets
    w, _app = _fenster()
    knoepfe = [b for b in w.ribbon.findChildren(QtWidgets.QToolButton)
               if b.defaultAction() is w.act_rechnen and b.property("rolle") == "start"]
    orte = sorted(_register_von(w, k) for k in knoepfe)
    check("Berechnen: je ein blauer Startknopf in Start und Berechnung, beide auf derselben Aktion",
          orte == ["Berechnung", "Start"], f"{len(knoepfe)} Knöpfe in {orte}")


def _register_von(w, knopf) -> str:
    p = knopf.parent()
    while p is not None and p not in w.ribbon._register.values():
        p = p.parent()
    return next((n for n, r in w.ribbon._register.items() if r is p), "?")


def test_kuerzel():
    import numpy as np
    from PySide6 import QtCore, QtGui, QtTest
    w, app = _fenster()
    aktionen = [a for a in w.findChildren(QtGui.QAction) if not a.shortcut().isEmpty()]
    folgen = {}
    for a in aktionen:
        folgen.setdefault(a.shortcut().toString(), []).append(a.text())
    doppelt = {k: v for k, v in folgen.items() if len(v) > 1}
    check("kein Tastenkürzel doppelt: je Tastenfolge genau eine Aktion am Fenster", not doppelt, str(doppelt))
    mit = [b for b in w.ribbon.befehle if not b.aktion.shortcut().isEmpty()]
    check("… und im Ribbon trägt jede Tastenfolge genau einen Befehl",
          len({b.aktion.shortcut().toString() for b in mit}) == len(mit), str(len(mit)))
    reg, knoepfe = _start(w)
    for text, kuerzel in (("Berechnen", "F5"), ("Bericht", "Ctrl+R")):
        k = next((b for b, _g, _x in knoepfe if b.text() == text), None)
        check(f"„{text}“ im Register Start trägt {kuerzel} - die Aktion, die schon das Kürzel hat",
              k is not None and k.defaultAction().shortcut().toString() == kuerzel
              and folgen.get(kuerzel) == [text],
              f"{k and k.defaultAction().shortcut().toString()} / {folgen.get(kuerzel)}")
    neue = []
    for t, _g, r, *_x in ABLAUF:
        if t in ("Berechnen", "Bericht"):
            continue
        bs = _befehl(w, r if r not in ("", "Berechnung") else "Start", t)
        if len(bs) != 1 or not bs[0].aktion.shortcut().isEmpty():
            neue.append(t)
    check("… die übrigen neun Ablaufbefehle haben kein Kürzel bekommen", not neue, str(neue))
    # echte Tastendrücke: ohne Doppelung löst Qt jede Taste genau einmal aus
    meldungen = []
    alt = QtCore.qInstallMessageHandler(lambda _t, _c, m: meldungen.append(m))
    try:
        aktiv = _aktiv_machen(w)
        check("Vorbereitung: das Hauptfenster ist das aktive Fenster, echte Tastendrücke kommen an",
              aktiv, "isActiveWindow() ist auch nach raise_() und activateWindow() falsch")
        w.ribbon.zeigen("Start")
        w.plotter.interactor.setFocus()
        _ruhe()
        for (taste, mod, fn, arg, aktion) in (
                (QtCore.Qt.Key_F5, QtCore.Qt.NoModifier, "do_solve", ("all",), w.act_rechnen),
                (QtCore.Qt.Key_R, QtCore.Qt.ControlModifier, "make_report", (),
                 _befehl(w, "Bericht", "Bericht")[0].aktion)):
            AUFRUFE.clear()
            QtTest.QTest.keyClick(w, taste, mod)
            _ruhe()
            check(f"{aktion.shortcut().toString()} im Register Start ruft {fn} genau einmal auf",
                  AUFRUFE == [(fn, arg)], f"{AUFRUFE}, Fenster aktiv: {w.isActiveWindow()}")
        w.selection = np.arange(0)
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        _ruhe()
        check("Strg+A (jetzt im Menü „Bearbeiten ▾“) wählt alle Knoten",
              len(w.selection) == w.model.nn and w.model.nn > 0, f"{len(w.selection)} von {w.model.nn}")
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_Escape)
        _ruhe()
        check("Esc (Alles deselektieren, ebenfalls im Menü) hebt die Auswahl auf", len(w.selection) == 0,
              str(len(w.selection)))
    finally:
        QtCore.qInstallMessageHandler(alt)
    check("Qt meldete bei keiner dieser Tasten „Ambiguous shortcut“",
          not [m for m in meldungen if "mbiguous" in m], str([m for m in meldungen if "mbiguous" in m]))
    # Gegenprobe der Prüfung selbst: eine zweite Aktion mit F5 blockiert die Taste.
    # Sähe der Aufbau des Registers so etwas vor, schlüge der Test oben an. Sie
    # läuft immer: ist das Fenster nicht aktiv, schlägt sie fehl und sagt es.
    _aktiv_machen(w)
    probe = QtGui.QAction("Probe F5", w)
    probe.setShortcut(QtGui.QKeySequence("F5"))
    probe.setShortcutContext(QtCore.Qt.ApplicationShortcut)
    w.addAction(probe)
    gemeldet = []
    alt = QtCore.qInstallMessageHandler(lambda _t, _c, m: gemeldet.append(m))
    try:
        AUFRUFE.clear()
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_F5)
        _ruhe()
    finally:
        QtCore.qInstallMessageHandler(alt)
        probe.setShortcut(QtGui.QKeySequence())
        w.removeAction(probe)
        probe.deleteLater()
    check("Gegenprobe der Prüfung: eine zweite Aktion mit F5 wird als „Ambiguous shortcut“ gemeldet, "
          "und die Taste tut dann nichts", any("mbiguous" in m for m in gemeldet) and not AUFRUFE,
          f"{[m[:50] for m in gemeldet][:2]}, Aufrufe {AUFRUFE}, Fenster aktiv: {w.isActiveWindow()}")
    AUFRUFE.clear()


def test_nichts_verschwunden():
    from PySide6 import QtWidgets
    w, app = _fenster()
    w.resize(1920, 1080)
    _ruhe()
    reg, knoepfe = _start(w)
    sichtbar = [b for b, _g, _x in knoepfe if b.isVisibleTo(reg)]
    ohne_befehl, nicht_erreichbar = [], []
    for text in FRUEHER:
        bs = _befehl(w, "Start", text)
        if len(bs) != 1:
            ohne_befehl.append(f"{text} ({len(bs)})")
            continue
        if not any(_traegt(k, bs[0].aktion) for k in sichtbar):
            nicht_erreichbar.append(text)
    check(f"jeder der {len(FRUEHER)} früheren Befehle des Registers Start ist weiter als Befehl vermerkt",
          not ohne_befehl, "; ".join(ohne_befehl))
    check("… und steht im Register Start: als Knopf oder im Menü „Bearbeiten ▾“ (nicht nur in der Suche)",
          not nicht_erreichbar, "; ".join(nicht_erreichbar))
    menue = next((b for b in sichtbar if b.text() == "Bearbeiten ▾"), None)
    if not check("das Menü „Bearbeiten ▾“ steht im Register Start", menue is not None):
        return
    drin = [a.text() for a in menue.menu().actions() if not a.isSeparator()]
    check("„Bearbeiten ▾“: Rückgängig, Wiederholen, Alles deselektieren, Alles auswählen, Auswahl umkehren, "
          "Intelligente Auswahl", drin == ["Rückgängig", "Wiederholen", "Alles deselektieren", "Alles auswählen",
                                          "Auswahl umkehren", "Intelligente Auswahl"], str(drin))
    # dieselbe Aktion wie in Schnellzugriff und Glasleiste
    schnell = list(w.ribbon.schnellzugriff.actions())
    check("Rückgängig und Wiederholen stehen auch oben in der Schnellzugriffsleiste - dieselben Aktionen "
          "wie im Menü", w.act_undo in schnell and w.act_redo in schnell
          and _befehl(w, "Start", "Rückgängig")[0].aktion is w.act_undo
          and _befehl(w, "Start", "Wiederholen")[0].aktion is w.act_redo)
    kn = w.glasleiste.knoepfe
    check("Alles deselektieren und Intelligente Auswahl stehen auch in der Glasleiste - dieselben Aktionen",
          kn["auswahl_weg"].defaultAction() is w.act_auswahl_weg
          and kn["auswahl_klug"].defaultAction() is w.act_klug
          and _befehl(w, "Start", "Alles deselektieren")[0].aktion is w.act_auswahl_weg
          and _befehl(w, "Start", "Intelligente Auswahl")[0].aktion is w.act_klug)
    # ein Schalter an zwei Stellen: derselbe Zustand
    eintrag = next(a for a in menue.menu().actions() if a.text() == "Intelligente Auswahl")
    start_an = eintrag.isChecked()
    kn["auswahl_klug"].click()
    _ruhe()
    check("Intelligente Auswahl: ein Klick in der Glasleiste schaltet den Eintrag im Menü mit "
          "(derselbe Zustand an beiden Stellen)",
          eintrag.isCheckable() and eintrag.isChecked() != start_an and kn["auswahl_klug"].isChecked() == eintrag.isChecked()
          and w.act_klug.isChecked() == eintrag.isChecked(), f"{start_an} -> {eintrag.isChecked()}")
    eintrag.trigger()
    _ruhe()
    check("… und umgekehrt: der Menüeintrag schaltet die Glasleiste zurück",
          eintrag.isChecked() == start_an and kn["auswahl_klug"].isChecked() == start_an)
    check("Das Menü „Bearbeiten ▾“ trägt ein eigenes Symbol (einen Bleistift), nicht den Auswahlpfeil von "
          "„Alles auswählen“",
          menue.icon().cacheKey() != next(a for a in menue.menu().actions()
                                          if a.text() == "Alles auswählen").icon().cacheKey()
          and not menue.icon().isNull())
    # die Prüfwerkzeuge sind Knöpfe geblieben
    check("Die drei Prüfwerkzeuge stehen weiter als Knöpfe in der Gruppe „Prüfen“",
          all(any(b.text() == t and g == "Prüfen" for b, g, _x in knoepfe)
              for t in ("Doppelte Knoten zusammenführen", "Freie Stabenden anschließen…",
                        "Freie Bewegungen suchen")))
    # Die Befehlssuche nennt den neuen Ort
    treffer = [w.ribbon.anzeige(b) for b in w.ribbon.finden("Alles auswählen") if b.text == "Alles auswählen"]
    check("Befehlssuche: „Alles auswählen“ steht in Start › Bearbeiten",
          treffer == ["Alles auswählen   (Start › Bearbeiten)"], str(treffer))


def test_bearbeiten_menue():
    """Das Menü „Bearbeiten ▾“ verhält sich wie vorher die Knöpfe: Rückgängig und
    Wiederholen sind grau, solange nichts zu tun ist, nennen den Schritt im
    Hinweis, und Strg+Z und Strg+Y nehmen genau einen Schritt zurück oder
    wiederholen ihn. Esc bei offenem Menü schließt nur das Menü."""
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    w.resize(1920, 1080)
    _ruhe()
    reg, knoepfe = _start(w)
    knopf = next((b for b, _g, _x in knoepfe if b.text() == "Bearbeiten ▾"), None)
    if not check("das Menü „Bearbeiten ▾“ steht im Register Start", knopf is not None):
        return
    menue = knopf.menu()
    eintrag = {a.text(): a for a in menue.actions() if not a.isSeparator()}
    w._undo, w._redo = [], []
    w._undo_knoepfe()
    _ruhe()
    check("nichts zu tun: Rückgängig und Wiederholen im Menü sind grau, der Hinweis sagt es",
          not eintrag["Rückgängig"].isEnabled() and not eintrag["Wiederholen"].isEnabled()
          and "Nichts rückgängig" in eintrag["Rückgängig"].toolTip(),
          f"{eintrag['Rückgängig'].isEnabled()} {eintrag['Wiederholen'].isEnabled()} "
          f"{eintrag['Rückgängig'].toolTip()!r}")
    n0 = w.model.nn
    w.merken("Knoten angelegt")
    w.model.add_node(1.0, 2.0, 3.0)
    _ruhe()
    tip = eintrag["Rückgängig"].toolTip()
    check("nach merken(): Rückgängig ist frei, der Hinweis nennt den Schritt und das Kürzel",
          eintrag["Rückgängig"].isEnabled() and not eintrag["Wiederholen"].isEnabled()
          and tip.startswith("Rückgängig: Knoten angelegt") and "(Strg+Z)" in tip, repr(tip))
    meldungen = []
    alt = QtCore.qInstallMessageHandler(lambda _t, _c, m: meldungen.append(m))
    try:
        aktiv = _aktiv_machen(w)
        check("Vorbereitung: das Hauptfenster ist das aktive Fenster, echte Tastendrücke kommen an",
              aktiv, "isActiveWindow() ist auch nach raise_() und activateWindow() falsch")
        w.plotter.interactor.setFocus()
        _ruhe()
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
        _ruhe()
        nach_z = (w.model.nn, len(w._undo), len(w._redo))
        check("Strg+Z nimmt genau einen Schritt zurück (der Knoten ist weg, ein Schritt zum Wiederholen)",
              nach_z == (n0, 0, 1), f"Knoten {nach_z[0]} (vorher {n0}), Rückgängig {nach_z[1]}, "
                                    f"Wiederholen {nach_z[2]}")
        check("… dann ist Wiederholen frei, Rückgängig wieder grau",
              eintrag["Wiederholen"].isEnabled() and not eintrag["Rückgängig"].isEnabled()
              and eintrag["Wiederholen"].toolTip().startswith("Wiederholen: "),
              repr(eintrag["Wiederholen"].toolTip()))
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_Y, QtCore.Qt.ControlModifier)
        _ruhe()
        nach_y = (w.model.nn, len(w._undo), len(w._redo))
        check("Strg+Y stellt genau diesen Schritt wieder her (Knoten wieder da)",
              nach_y == (n0 + 1, 1, 0), f"Knoten {nach_y[0]}, Rückgängig {nach_y[1]}, Wiederholen {nach_y[2]}")
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
        _ruhe()
    finally:
        QtCore.qInstallMessageHandler(alt)
    check("Qt meldete bei Strg+Z und Strg+Y kein „Ambiguous shortcut“",
          not [m for m in meldungen if "mbiguous" in m], str([m for m in meldungen if "mbiguous" in m]))
    # Esc bei offenem Menü schließt das Menü und hebt die Auswahl nicht auf
    w._set_selection([0, 1, 2])
    _ruhe()
    ausgeloest = []

    def esc_gelaufen(*_a):
        ausgeloest.append(1)
    w.act_auswahl_weg.triggered.connect(esc_gelaufen)
    menue.popup(knopf.mapToGlobal(QtCore.QPoint(0, knopf.height())))
    _ruhe()
    offen = menue.isVisible()
    QtTest.QTest.keyClick(menue, QtCore.Qt.Key_Escape)
    _ruhe()
    check("Esc bei offenem Menü „Bearbeiten ▾“ schließt nur das Menü: die Auswahl bleibt, "
          "„Alles deselektieren“ läuft nicht",
          offen and not menue.isVisible() and len(w.selection) == 3 and not ausgeloest,
          f"offen {offen}, danach sichtbar {menue.isVisible()}, Auswahl {len(w.selection)}, "
          f"Esc-Aktion {len(ausgeloest)}x")
    w.act_auswahl_weg.triggered.disconnect(esc_gelaufen)
    w._set_selection([])
    _ruhe()


def test_suche():
    """Die Befehlssuche findet die verschobenen Befehle weiter: unter den alten
    Gruppennamen (Auswahl, Zwischenablage, Modell prüfen) und unter dem Namen
    des Menüs. „Bearbeiten“ führt in die Trefferliste mit dem Menü an erster
    Stelle, Enter führt nicht allein Unterlagen › Skizze › Bearbeiten aus."""
    w, app = _fenster()
    rb = w.ribbon

    def texte(frage):
        return [b.text for b in rb.finden(frage)]
    t = texte("Auswahl")
    check("„Auswahl“ findet Alles auswählen und Alles deselektieren (Gruppe bis zum 03.10.2026) "
          "und weiter Auswahl umkehren und Intelligente Auswahl",
          {"Alles auswählen", "Alles deselektieren", "Auswahl umkehren", "Intelligente Auswahl"} <= set(t),
          str(t[:8]))
    t = texte("Zwischenablage")
    check("„Zwischenablage“ findet Rückgängig und Wiederholen", {"Rückgängig", "Wiederholen"} <= set(t), str(t))
    t = texte("Modell prüfen")
    check("„Modell prüfen“ findet die drei Prüfwerkzeuge",
          {"Doppelte Knoten zusammenführen", "Freie Stabenden anschließen…", "Freie Bewegungen suchen"} <= set(t),
          str(t))
    check("… die alten Gruppennamen zählen wie Gruppennamen: Enter führt davon nichts allein aus "
          "(kein Namenstreffer)",
          not [b for b in rb.namenstreffer("Zwischenablage") if b.text in ("Rückgängig", "Wiederholen")]
          and not rb.namenstreffer("Modell prüfen"), str([b.text for b in rb.namenstreffer("Modell prüfen")]))
    treffer = rb.finden("Bearbeiten")
    check("„Bearbeiten“: der Treffer in Start steht vorn, die Skizze (Unterlagen) danach",
          [(b.register, b.text) for b in treffer[:2]] == [("Start", "Bearbeiten ▾"), ("Unterlagen", "Bearbeiten")],
          str([(b.register, b.text) for b in treffer[:3]]))
    ausgefuehrt, gemeldet = [], []
    rb.gesucht.connect(ausgefuehrt.append)
    rb.meldung.connect(gemeldet.append)
    try:
        rb.suche.setText("Bearbeiten")
        rb._suche_ausfuehren()
        _ruhe()
    finally:
        rb.gesucht.disconnect(ausgefuehrt.append)
        rb.meldung.disconnect(gemeldet.append)
    check("„Bearbeiten“ + Enter führt nichts aus (zwei Namenstreffer), die Trefferliste erscheint",
          not ausgefuehrt and any("Treffer" in m for m in gemeldet),
          f"ausgeführt {ausgefuehrt}, Meldung {gemeldet[-1:]}")
    rb._vervollstaendigung.popup().hide()
    rb.suche.clear()
    # ein Klick auf den Treffer: Start nach vorn, das Menü klappt auf
    w.resize(1920, 1080)
    rb.zeigen("Datei")
    _ruhe()
    rb._ausfuehren(treffer[0])
    _ruhe()
    vorn = rb.tabs.tabText(rb.tabs.currentIndex())
    from PySide6 import QtWidgets
    knopf = next(b for b in rb._register["Start"].findChildren(QtWidgets.QToolButton)
                 if b.text() == "Bearbeiten ▾")
    check("der Treffer „Bearbeiten ▾“ holt Start nach vorn und klappt das Menü auf",
          vorn == "Start" and knopf.menu().isVisible(), f"Register {vorn}, Menü sichtbar {knopf.menu().isVisible()}")
    knopf.menu().hide()
    _ruhe()


# --------------------------------------------------------------------------
# Breite bei 1366 und 1280 px
# --------------------------------------------------------------------------
def _schrift_ok(w) -> bool:
    from PySide6 import QtGui, QtWidgets
    knopf = w.ribbon.findChildren(QtWidgets.QToolButton)[0]
    return QtGui.QFontInfo(knopf.font()).family() == "Segoe UI"


def _start_messen(w):
    """(Wunschbreite, Breite des Registers, gekürzte Texte, Rollpfeile) des
    **aufgeklappten** Registers Start. Seit Paket 5 ist das Ribbon bei 1366 x 768
    eingeklappt (Kompaktstufe); gemessen wird so, wie man es nach einem Klick auf
    den Reiter sieht."""
    from PySide6 import QtWidgets
    from tests import test_glasleiste_ribbon as gl
    rb = w.ribbon
    _ruhe(10)
    war_zu = rb.eingeklappt()
    vorher = rb.tabs.currentIndex()
    reg = _start_offen(w)
    pfeile = [k for k in rb.tabs.tabBar().findChildren(QtWidgets.QToolButton) if k.isVisible()]
    aus = (reg.sizeHint().width(), reg.width(), gl._gekuerzt(reg), len(pfeile), reg.isVisible())
    rb.tabs.setCurrentIndex(vorher)
    if war_zu:
        rb.einklappen(True)
    _ruhe()
    return aus


def test_breite():
    from tests import test_glasleiste_ribbon as gl
    w, _app = _fenster()
    if sys.platform.startswith("win"):
        if not check("Schrift wie auf dem Desktop (Segoe UI) - sonst misst die Prüfung Kästen",
                     _schrift_ok(w), "QT_QPA_FONTDIR fehlt?"):
            return
    for breite, hoehe in gl.BREITEN:
        w.resize(breite, hoehe)
        _ruhe()
        hint, ist, gekuerzt, pfeile, sichtbar = _start_messen(w)
        check(f"{breite} px: das Register Start ist beim Messen sichtbar und so breit wie das Fenster",
              sichtbar and abs(ist - w.width()) <= 4, f"Register {ist} px, Fenster {w.width()} px")
        check(f"{breite} px: Start braucht höchstens {gl.RESERVE:.0%} der Breite",
              hint <= gl.RESERVE * ist, f"Wunschbreite {hint} px, erlaubt {int(gl.RESERVE * ist)} px")
        check(f"{breite} px: keine gekürzte Beschriftung (QFontMetrics) und keine Rollpfeile",
              not gekuerzt and pfeile == 0, f"{gekuerzt[:3]}, {pfeile} Pfeile")
    w.resize(1920, 1080)
    _ruhe()


def test_150_prozent():
    """Eigener Prozess mit QT_SCALE_FACTOR=1.5: Fenster 1280 x 720 logisch =
    1920 x 1080 Bildpunkte."""
    import subprocess
    stamm = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["QT_SCALE_FACTOR"] = "1.5"
    env["PYTHONPATH"] = stamm + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    r = subprocess.run([sys.executable, "-m", "tests.test_register_start", "--skaliert"],
                       cwd=stamm, env=env, capture_output=True, text=True, timeout=600,
                       encoding="utf-8", errors="replace")
    zeilen = [z for z in r.stdout.splitlines() if z.startswith("SKALIERT")]
    print("\n".join(zeilen[-4:]) or r.stdout[-800:] + r.stderr[-800:])
    ergebnis = [z for z in zeilen if z.startswith("SKALIERT ERGEBNIS")]
    check("150 % (QT_SCALE_FACTOR=1.5, 1280 px logisch): Start nicht gekürzt, nicht zu breit",
          r.returncode == 0 and ergebnis and ergebnis[-1].endswith("0 gekuerzt, 0 zu breit"),
          (ergebnis[-1] if ergebnis else r.stderr[-160:]))


def _skaliert_lauf() -> int:
    from tests import test_glasleiste_ribbon as gl
    w, app = _fenster()
    print(f"SKALIERT dpr={app.primaryScreen().devicePixelRatio()} schrift_ok={_schrift_ok(w)}", flush=True)
    w.resize(1280, 720)
    _ruhe()
    hint, ist, gekuerzt, pfeile, sichtbar = _start_messen(w)
    zu_breit = hint > gl.RESERVE * ist
    for z in gekuerzt:
        print(f"SKALIERT {z}", flush=True)
    print(f"SKALIERT Start {hint} von {ist} px, {pfeile} Rollpfeile", flush=True)
    print(f"SKALIERT ERGEBNIS Register Start, {len(gekuerzt)} gekuerzt, {int(zu_breit)} zu breit", flush=True)
    return 0 if not gekuerzt and not zu_breit and not pfeile and sichtbar and _schrift_ok(w) else 1


# --------------------------------------------------------------------------
def test_start_und_f5():
    from statik3d import solver
    w, app = _fenster()
    check("das Programm startet im Register Start", _FENSTER["start_register"] == "Start",
          _FENSTER["start_register"])
    w.ribbon.zeigen("Start")
    _ruhe()
    an = solver.solve_all(w.model, design=bool(w.model.members))
    w._solve_done("all", an)
    _ruhe()
    vorn = w.ribbon.tabs.tabText(w.ribbon.tabs.currentIndex())
    check("nach der Rechnung (F5) steht das Ribbon auf „Ergebnisse“, wie bisher", vorn == "Ergebnisse", vorn)
    w.ribbon.zeigen("Start")


def test_handbuch():
    from tests.handbuch import absatz
    zeile = absatz("| **Start** |")
    reihenfolge = ("Knoten", "Stab", "Knotenlager", "Linienlast", "Lastfälle", "Vernetzen", "Prüfen",
                   "Berechnen", "Ergebnisse", "Nachweise EC3", "Bericht")
    pos = [zeile.find(t) for t in reihenfolge]
    check("Handbuch: die Tabelle der Register nennt für Start die elf Befehle in der Reihenfolge des Ablaufs",
          all(p >= 0 for p in pos) and pos == sorted(pos), zeile[:100])
    a = absatz("**Das Register Start ist der Arbeitsablauf")
    check("Handbuch: Start als Ablauf - Gruppen, dieselben Aktionen, Menü „Bearbeiten ▾“, Schnellzugriff, "
          "früherer Stand",
          all(s in a for s in ("Modell", "Auswerten", "dieselben", "Bearbeiten ▾", "Schnellzugriff",
                               "Bis zum 03.10.2026")), a[:100])
    check("Handbuch: bei 1366 × 768 ist das Ribbon eingeklappt (Kompaktstufe), jeder Ablaufschritt kostet "
          "zwei Klicks",
          all(s in a for s in ("1366 × 768", "eingeklappt", "Kompaktstufe", "zwei Klicks")), a[:80])
    check("Handbuch: die Befehlssuche findet die umgezogenen Befehle unter den alten Gruppennamen, "
          "„Bearbeiten“ nennt das Menü zuerst",
          all(s in a for s in ("Befehlssuche", "„Auswahl“", "„Zwischenablage“", "„Modell prüfen“", "„Bearbeiten“")),
          a[:80])
    e = absatz("Das Register **Start** fasst die häufigsten Befehle")
    check("Handbuch, Kapitel „Arbeitsablauf“: die Reihe in Start ist eine Auswahl, nicht die Liste noch einmal - "
          "„Netz“ meint dort Stabzüge und Platten, Nachweise EC3 steht hinter dem Berechnen",
          all(s in e for s in ("Reihenfolge, in der man ein Modell aufbaut und auswertet", "„Netz“ meint dort",
                               "hinter dem Berechnen", "Nachweise EC3"))
          and "Befehle dieser Schritte" not in e, e[:80])
    b = absatz("zerfällt zunächst in Teile")
    c = absatz("*Register Start →")
    d = absatz("Der Schalter in der Glasleiste (auch *Start →")
    check("Handbuch: die Verweise nennen die Gruppe „Prüfen“ und das Menü „Bearbeiten ▾“, nicht mehr "
          "„Modell prüfen“ und „Auswahl“ im Register Start",
          "Start → Prüfen" in b and "Start → Prüfen" in c and "Start → Bearbeiten ▾" in d
          and "Modell prüfen" not in b + c, f"{b[:60]} | {c[:50]} | {d[:50]}")


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    if "--skaliert" in sys.argv:
        code = _skaliert_lauf()
        sys.stdout.flush()
        os._exit(code)
    for t in (test_reihenfolge, test_dieselben_befehle, test_berechnen_zwei_knoepfe, test_kuerzel,
              test_bearbeiten_menue, test_nichts_verschwunden, test_suche, test_breite, test_150_prozent, test_start_und_f5, test_handbuch):
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
    os._exit(0 if n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    sys.exit(main())
