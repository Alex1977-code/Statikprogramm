"""
Qt auf Deutsch (Plan-Schritt 11a, 02.10.2026).

Bis zum 02.10.2026 lud das Programm keinen QTranslator: Qt-eigene Texte
erschienen englisch - die Standardknoepfe „OK/Cancel/Yes/No“ in jeder
QMessageBox, das Kontextmenue der Textfelder („Undo/Redo/Cut/Copy/Paste/
Select All“), QDialogButtonBox, Farbauswahl. Die Kuerzel in den Hinweisen der
Knoepfe standen als „Ctrl+Z“ und „Shift+F1“.

* ``statik3d.gui.sprache.uebersetzer_laden`` laedt qtbase_de und qt_de (erst
  aus QLibraryInfo, dann aus dem PySide6-Ordner, dann aus sys._MEIPASS der
  exe); fehlt die Datei, geht es still weiter und die Rueckgabe traegt eine
  Meldung fuer das Protokoll; zweimal gerufen laedt es nichts doppelt;
* der Programmstart (``gui.main.main``) und die Rechenhilfe rufen es;
* ``kuerzel_text`` schreibt Kuerzel fuer die Anzeige deutsch („Strg+Umschalt+C“,
  „Entf“, „Pos1“) - unabhaengig davon, ob der Uebersetzer geladen ist; die
  Kuerzel selbst (QAction.setShortcut) bleiben „Ctrl+…“;
* in den Hinweisen des Ribbons, der Glasleiste und der Rueckgaengig-Knoepfe
  steht kein „Ctrl+“ und kein „Shift+“ mehr.

Aufruf:  python -m tests.test_qt_deutsch
"""
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_qtdeutsch_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from statik3d.gui.main import MainWindow
    app = _app()
    w = MainWindow()
    w.show()
    app.processEvents()
    _FENSTER.update(w=w, app=app)
    return w, app


def _uebersetzer_entfernen(app):
    """Alle Uebersetzer dieser Pruefung wieder aus der Anwendung nehmen."""
    from PySide6 import QtCore
    for t in app.findChildren(QtCore.QTranslator):
        app.removeTranslator(t)
        t.setParent(None)


def _fenster_merken(app) -> list:
    """Die jetzigen Hauptebenen-Fenster - als Liste von Objekten, nicht von
    id(): topLevelWidgets() liefert fuer C++-eigene Fenster Huellen, die gleich
    wieder freigegeben werden, und ein neues Fenster kann deren id erben."""
    return list(app.topLevelWidgets())


def _neue_fenster(app, alt, klasse) -> list:
    return [w for w in app.topLevelWidgets() if isinstance(w, klasse) and not any(w is x for x in alt)]


def _anzahl_uebersetzer(app) -> int:
    from PySide6 import QtCore
    return len(app.findChildren(QtCore.QTranslator))


def _abbrechen():
    from PySide6 import QtCore
    return QtCore.QCoreApplication.translate("QPlatformTheme", "Cancel")


def _knopftexte():
    from PySide6 import QtWidgets
    S = QtWidgets.QMessageBox
    mb = S(S.Question, "t", "x", S.Yes | S.No | S.Cancel | S.Save | S.Discard)
    return sorted(b.text() for b in mb.buttons())


def _menuetexte(feld):
    return [a.text() for a in feld.createStandardContextMenu().actions() if a.text()]


# -------------------------------------------------------------------------
def test_kuerzeltext_tabelle():
    """Die Anzeige eines Kuerzels, ohne Uebersetzer und mit allen Tasten."""
    from PySide6 import QtGui
    from statik3d.gui import sprache
    tabelle = [
        ("Ctrl+N", "Strg+N"), ("Ctrl+Shift+C", "Strg+Umschalt+C"),
        ("Shift+F1", "Umschalt+F1"), ("Ctrl+F1", "Strg+F1"), ("Alt+F4", "Alt+F4"),
        ("F5", "F5"), ("Esc", "Esc"), ("Escape", "Esc"),
        ("Del", "Entf"), ("Delete", "Entf"), ("Ctrl+Del", "Strg+Entf"),
        ("Ins", "Einfg"), ("Home", "Pos1"), ("End", "Ende"),
        ("PgUp", "Bild auf"), ("PgDown", "Bild ab"),
        ("Backspace", "Rücktaste"), ("Return", "Eingabe"), ("Enter", "Eingabe"),
        ("Space", "Leertaste"),
        ("Left", "Pfeil links"), ("Right", "Pfeil rechts"), ("Up", "Pfeil auf"), ("Down", "Pfeil ab"),
        ("Ctrl++", "Strg++"), ("Ctrl+-", "Strg+-"), ("Ctrl+1", "Strg+1"),
        ("Ctrl+K, Ctrl+C", "Strg+K, Strg+C"), ("", ""),
    ]
    falsch = [(e, sprache.kuerzel_text(e), s) for e, s in tabelle if sprache.kuerzel_text(e) != s]
    check(f"Kürzel-Anzeige: {len(tabelle)} Fälle (Strg, Umschalt, Entf, Pos1, Bild auf/ab, Pfeile …)",
          not falsch, str(falsch[:4]))
    f = sprache.kuerzel_text(QtGui.QKeySequence("Ctrl+Shift+C"))
    check("… auch aus einer QKeySequence", f == "Strg+Umschalt+C", f)
    check("… ein Ctrl- oder Shift-Rest bleibt nirgends stehen",
          not any(re.search(r"Ctrl|Shift", sprache.kuerzel_text(e)) for e, _s in tabelle))
    check("… ein unbekannter Tastenname bleibt, wie er ist", sprache.kuerzel_text("Ctrl+Foo") == "Strg+Foo",
          sprache.kuerzel_text("Ctrl+Foo"))


def test_uebersetzer_laden():
    """Vorher englisch, nach dem Laden deutsch; zweimal gerufen laedt es nichts doppelt."""
    from PySide6 import QtGui, QtWidgets
    from statik3d.gui import sprache
    app = _app()
    _uebersetzer_entfernen(app)
    check("vorher (ohne Übersetzer): „Cancel“ und englische Standardknöpfe",
          _abbrechen() == "Cancel" and "&Yes" in _knopftexte(), f"{_abbrechen()!r} {_knopftexte()}")
    check("vorher: Kontextmenü der Textfelder englisch (Undo, Select All)",
          any("Undo" in t for t in _menuetexte(QtWidgets.QLineEdit("a"))))

    erg = sprache.uebersetzer_laden(app)
    check("geladen: qtbase (und qt), keine Meldung", "qtbase" in erg.geladen and not erg.meldung,
          f"{erg.geladen} {erg.meldung!r}")
    check("„Cancel“ heißt „Abbrechen“ (QPlatformTheme)", _abbrechen() == "Abbrechen", _abbrechen())
    kn = _knopftexte()
    check("Standardknöpfe der QMessageBox deutsch (Ja, Nein, Abbrechen, Speichern, Verwerfen)",
          kn == sorted(["&Ja", "&Nein", "Abbrechen", "Speichern", "Verwerfen"]), str(kn))
    S = QtWidgets.QDialogButtonBox
    bb = S(S.Ok | S.Cancel | S.Close | S.Apply | S.Reset)
    tx = sorted(b.text() for b in bb.buttons())
    check("QDialogButtonBox deutsch (Anwenden, Schließen, Zurücksetzen, Abbrechen)",
          tx == sorted(["OK", "Schließen", "Abbrechen", "Zurücksetzen", "Anwenden"]), str(tx))
    for name, feld in (("QLineEdit", QtWidgets.QLineEdit("abc")),
                       ("QPlainTextEdit", QtWidgets.QPlainTextEdit("abc"))):
        m = _menuetexte(feld)
        gesamt = " | ".join(m).replace("&", "")          # ohne Mnemonik-Zeichen
        check(f"Kontextmenü {name}: Rückgängig, Ausschneiden, Kopieren, Einfügen, Alles auswählen",
              all(w in gesamt for w in ("Rückgängig", "Ausschneiden", "Kopieren", "Einfügen", "Alles auswählen"))
              and not re.search(r"Undo|Redo|Cut|Copy|Paste|Select All", gesamt), gesamt)
        check(f"… mit „Strg+Z“, nicht „Ctrl+Z“", "Strg+Z" in gesamt and "Ctrl" not in gesamt, gesamt)
    d = QtWidgets.QColorDialog()
    d.setOption(QtWidgets.QColorDialog.DontUseNativeDialog, True)
    ft = sorted({b.text().replace("&", "") for b in d.findChildren(QtWidgets.QPushButton) if b.text()}
                | {x.text().replace("&", "") for x in d.findChildren(QtWidgets.QLabel) if x.text().strip()})
    check("Farbauswahl deutsch (Grundfarben, Abbrechen, Rot, Grün)",
          all(w in ft for w in ("Grundfarben", "Abbrechen", "Rot:", "Grün:")) and "Cancel" not in ft, str(ft))
    nt = QtGui.QKeySequence("Ctrl+Z").toString(QtGui.QKeySequence.NativeText)
    check("Menü-Kürzel (NativeText) deutsch: Strg+Z", nt == "Strg+Z", nt)
    pt = QtGui.QKeySequence("Ctrl+Z").toString(QtGui.QKeySequence.PortableText)
    check("PortableText bleibt „Ctrl+Z“ (der Schlüssel ändert sich nicht)", pt == "Ctrl+Z", pt)

    n = _anzahl_uebersetzer(app)
    erg2 = sprache.uebersetzer_laden(app)
    check("zweimal gerufen: kein Übersetzer doppelt, gleiche Auskunft",
          _anzahl_uebersetzer(app) == n and n == len(erg.geladen) and erg2.geladen == erg.geladen,
          f"{n} {erg.geladen} {erg2.geladen}")
    check("ohne Anwendung gerufen: nimmt die laufende", sprache.uebersetzer_laden().geladen == erg.geladen)
    _uebersetzer_entfernen(app)


def test_fehlende_datei_still_mit_meldung():
    from statik3d.gui import sprache
    app = _app()
    _uebersetzer_entfernen(app)
    leer = tempfile.mkdtemp(prefix="statik3d_keinqm_")
    try:
        erg = sprache.uebersetzer_laden(app, orte=[leer, os.path.join(leer, "gibtsnicht")])
    except Exception as ex:     # noqa: BLE001
        check("fehlende Datei: keine Ausnahme", False, repr(ex))
        return
    check("fehlende Datei: nichts geladen, eine Meldung für das Protokoll mit dem Dateinamen",
          not erg.geladen and "qtbase_de.qm" in erg.meldung and "\n" not in erg.meldung,
          f"{erg.geladen} {erg.meldung!r}")
    check("… Qt bleibt englisch, das Programm läuft weiter", _abbrechen() == "Cancel" and _anzahl_uebersetzer(app) == 0,
          _abbrechen())
    # nur qt_de fehlt: keine Meldung, qtbase genuegt
    teil = tempfile.mkdtemp(prefix="statik3d_nurbase_")
    quelle = [o for o in sprache.suchorte() if os.path.isfile(os.path.join(o, "qtbase_de.qm"))]
    check("im Entwicklungsbaum liegt qtbase_de.qm in einem der Suchorte", bool(quelle), str(sprache.suchorte()))
    if quelle:
        shutil.copy(os.path.join(quelle[0], "qtbase_de.qm"), teil)
        erg = sprache.uebersetzer_laden(app, orte=[teil])
        check("nur qtbase_de vorhanden: geladen, ohne Meldung (qt_de ist nur Zugabe)",
              erg.geladen == ("qtbase",) and not erg.meldung and _abbrechen() == "Abbrechen",
              f"{erg.geladen} {erg.meldung!r}")
    _uebersetzer_entfernen(app)


def test_suchorte_und_exe():
    """Reihenfolge der Suchorte; in der exe (sys._MEIPASS) wird gefunden."""
    from PySide6 import QtCore
    import PySide6
    from statik3d.gui import sprache
    app = _app()
    _uebersetzer_entfernen(app)
    orte = [os.path.normcase(os.path.normpath(o)) for o in sprache.suchorte()]
    qt = os.path.normcase(os.path.normpath(QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.TranslationsPath)))
    pak = os.path.normcase(os.path.normpath(os.path.join(os.path.dirname(PySide6.__file__), "translations")))
    # QLibraryInfo und der Paketordner sind in einer pip-Umgebung derselbe
    # Ordner und zaehlen dann einmal; sonst kommt QLibraryInfo zuerst
    check("Suchorte: erst QLibraryInfo, dann der PySide6-Ordner",
          orte[0] == qt and pak in orte and (qt == pak or orte.index(pak) >= 1), str(orte))
    check("… keine Doppelten", len(orte) == len(set(orte)), str(orte))
    linux = os.path.normcase(os.path.normpath(os.path.join(os.path.dirname(PySide6.__file__), "Qt", "translations")))
    check("Suchorte: für Linux auch PySide6/Qt/translations (pip-Paket)", linux in orte, str(orte))

    exe = tempfile.mkdtemp(prefix="statik3d_meipass_")
    ziel = os.path.join(exe, "PySide6", "translations")
    os.makedirs(ziel)
    quelle = next((o for o in sprache.suchorte() if os.path.isfile(os.path.join(o, "qtbase_de.qm"))), None)
    if quelle is None:
        check("qtbase_de.qm für die exe-Nachbildung gefunden", False)
        return
    shutil.copy(os.path.join(quelle, "qtbase_de.qm"), ziel)
    hatte = hasattr(sys, "_MEIPASS")
    alt = getattr(sys, "_MEIPASS", None)
    sys._MEIPASS = exe
    try:
        orte2 = [os.path.normcase(os.path.normpath(o)) for o in sprache.suchorte()]
        check("mit sys._MEIPASS: PySide6/translations der exe steht in den Suchorten",
              os.path.normcase(os.path.normpath(ziel)) in orte2, str(orte2))
        ziel_linux = os.path.normcase(os.path.normpath(os.path.join(exe, "PySide6", "Qt", "translations")))
        check("… und für Linux PySide6/Qt/translations der exe", ziel_linux in orte2, str(orte2))
        erg = sprache.uebersetzer_laden(app, orte=[ziel])
        check("aus dem Ordner der exe geladen", erg.geladen == ("qtbase",) and _abbrechen() == "Abbrechen",
              f"{erg.geladen} {_abbrechen()}")
    finally:
        if hatte:
            sys._MEIPASS = alt
        else:
            del sys._MEIPASS
        _uebersetzer_entfernen(app)


def test_programmstart_laedt_uebersetzer():
    """gui.main.main() laedt den Uebersetzer - ohne Ereignisschleife gerufen."""
    import statik3d.gui.main as gm
    app = _app()
    _uebersetzer_entfernen(app)
    check("vor dem Start: englisch", _abbrechen() == "Cancel", _abbrechen())
    app.exec = lambda *a, **k: 0          # die Schleife selbst gehoert nicht zur Pruefung
    code = "kein SystemExit"
    vorher0 = _fenster_merken(app)
    try:
        gm.main(app=app)
    except SystemExit as ex:
        code = ex.code
    check("main() lief bis zum Ende der Ereignisschleife", code == 0, str(code))
    check("nach dem Start: „Abbrechen“ und deutsche Standardknöpfe",
          _abbrechen() == "Abbrechen" and "&Ja" in _knopftexte(), f"{_abbrechen()!r} {_knopftexte()}")
    # das Fenster, das main() mit geladenem Uebersetzer gebaut hat: Hinweise
    # deutsch, Tastenfolgen weiter „Ctrl+…“ und wirksam
    fenster0 = _neue_fenster(app, vorher0, gm.MainWindow)
    check("main() hat genau ein Hauptfenster gebaut", len(fenster0) == 1, str(len(fenster0)))
    if fenster0:
        _hinweise_und_kuerzel(fenster0[0], app, "mit Übersetzer, Fenster aus main()", True)
    for w in app.topLevelWidgets():
        if w.isVisible():
            w.hide()
    # fehlt die Datei: der Start laeuft trotzdem, im Protokoll steht eine Zeile
    from statik3d.gui import sprache
    _uebersetzer_entfernen(app)
    vorher = _fenster_merken(app)
    leer = tempfile.mkdtemp(prefix="statik3d_keinqm_")
    echt = sprache.suchorte
    sprache.suchorte = lambda: [leer]
    code = "kein SystemExit"
    try:
        gm.main(app=app)
    except SystemExit as ex:
        code = ex.code
    finally:
        sprache.suchorte = echt
    neu = _neue_fenster(app, vorher, gm.MainWindow)
    protokoll = neu[0].log.toPlainText() if neu else ""
    check("ohne Übersetzungsdatei startet das Programm trotzdem (Code 0), Qt bleibt englisch",
          code == 0 and bool(neu) and _abbrechen() == "Cancel", f"{code} {len(neu)} {_abbrechen()}")
    check("… im Protokoll steht eine Zeile „Hinweis: Qt-Übersetzung qtbase_de.qm nicht gefunden …“",
          "Hinweis: Qt-Übersetzung qtbase_de.qm nicht gefunden" in protokoll, protokoll[-160:])
    for w in app.topLevelWidgets():
        if w.isVisible():
            w.hide()
    # die Rechenhilfe (eigener Start, eigene Anwendung) laedt ihn ebenso
    from statik3d.gui import rechenhilfe

    def rechenhilfe_starten(orte=None):
        _uebersetzer_entfernen(app)
        echt = sprache.suchorte
        if orte is not None:
            sprache.suchorte = lambda: orte
        # main() haelt sein Fenster nur in einer lokalen Variablen (es laeuft
        # sonst in app.exec()); ohne Ereignisschleife waere es nach der
        # Rueckkehr weg - darum merkt sich die Pruefung die Fenster
        gemerkt = []
        Echt = rechenhilfe.RechenhilfeFenster

        class Merker(Echt):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                gemerkt.append(self)
        rechenhilfe.RechenhilfeFenster = Merker
        os.environ["STATIK3D_KEIN_EXEC"] = "1"
        try:
            rechenhilfe.main(["--rechenhilfe"])
        finally:
            del os.environ["STATIK3D_KEIN_EXEC"]
            sprache.suchorte = echt
            rechenhilfe.RechenhilfeFenster = Echt
        text = gemerkt[0].protokoll.toPlainText() if gemerkt else ""
        for w in gemerkt:
            w.hide()
        return len(gemerkt), text
    n, text = rechenhilfe_starten()
    check("Rechenhilfe: Qt-Texte deutsch, im Protokollfeld kein Hinweis",
          n == 1 and _abbrechen() == "Abbrechen" and "Hinweis" not in text, f"{n} {_abbrechen()!r} {text!r}")
    n, text = rechenhilfe_starten([leer])
    check("Rechenhilfe ohne Übersetzungsdatei (leerer Suchort): läuft, Qt englisch",
          n == 1 and _abbrechen() == "Cancel", f"{n} {_abbrechen()!r}")
    check("… ihr Protokollfeld nennt den Grund („Hinweis: Qt-Übersetzung qtbase_de.qm nicht gefunden …“)",
          "Hinweis: Qt-Übersetzung qtbase_de.qm nicht gefunden" in text, text)
    for w in app.topLevelWidgets():
        w.hide()
    _uebersetzer_entfernen(app)


def _hinweise_und_kuerzel(w, app, kopf, uebersetzt):
    """Die Hinweise am Fenster ``w`` zeigen Strg/Umschalt, die Tastenfolgen
    bleiben „Ctrl+…“ und loesen weiter aus. ``uebersetzt``: ob der Qt-Uebersetzer
    beim Bau des Fensters schon geladen war."""
    from PySide6 import QtCore, QtGui, QtTest
    Qt = QtCore.Qt
    p = f"[{kopf}] "
    rb = w.ribbon
    befehle = list(rb.befehle)
    mit_ctrl = [(b.text, b.aktion.toolTip()) for b in befehle if re.search(r"Ctrl|Shift\+", b.aktion.toolTip())]
    check(p + f"Ribbon: in keinem der {len(befehle)} Befehlshinweise steht „Ctrl“ oder „Shift+“",
          not mit_ctrl, str(mit_ctrl[:3]))
    alle = [a for a in w.findChildren(QtGui.QAction)]
    mit_ctrl = [(a.text(), a.toolTip()) for a in alle if re.search(r"Ctrl|Shift\+", a.toolTip())]
    check(p + f"alle {len(alle)} Aktionen des Fensters: kein „Ctrl“ im Hinweis", not mit_ctrl, str(mit_ctrl[:3]))
    mit_strg = [b for b in befehle if "Strg+" in b.aktion.toolTip()]
    check(p + "… dafür steht „Strg+“ in vielen Hinweisen (Neu, Öffnen, Speichern, Darstellungen …)",
          len(mit_strg) >= 10, str(len(mit_strg)))

    def tip(name):
        b = next((b for b in befehle if b.text == name), None)
        return b.aktion.toolTip() if b is not None else None
    t = tip("Neu")
    check(p + "Neu: Hinweis nennt „(Strg+N)“", t is not None and t.endswith("(Strg+N)"), repr(t))
    umsch = [b for b in befehle if "Umschalt+F1" in b.aktion.toolTip()]
    check(p + "Fang auf Knoten: „Umschalt+F1“ im Hinweis", len(umsch) >= 1, str([b.aktion.toolTip() for b in umsch]))
    kopie = [b for b in befehle if "Strg+Umschalt+C" in b.aktion.toolTip()]
    check(p + "Tabelle kopieren: „Strg+Umschalt+C“ im Hinweis", len(kopie) >= 1)
    t = w.anordnung.act_ribbon.toolTip()
    check(p + "Ribbon einklappen: „Strg+F1“, einmal und ohne „Ctrl“", t.count("Strg+F1") == 1 and "Ctrl" not in t, repr(t))

    # die Tastenfolgen selbst bleiben (Schluessel „Ctrl+…“)
    seq = lambda a: a.shortcut().toString(QtGui.QKeySequence.PortableText)
    soll = {"Neu": "Ctrl+N", "Öffnen": "Ctrl+O", "Speichern": "Ctrl+S"}
    ist = {n: next((seq(b.aktion) for b in befehle if b.text == n), None) for n in soll}
    check(p + "Kürzel unverändert: Strg+N, Strg+O, Strg+S bleiben „Ctrl+…“", ist == soll, str(ist))
    check(p + "Strg+F1 gehört weiter dem Schalter „Ribbon einklappen“",
          w.anordnung.act_ribbon.shortcut() == QtGui.QKeySequence("Ctrl+F1"), seq(w.anordnung.act_ribbon))
    check(p + "Strg+Z, Strg+Y unverändert",
          seq(w.act_undo) == "Ctrl+Z" and seq(w.act_redo) == "Ctrl+Y", f"{seq(w.act_undo)} {seq(w.act_redo)}")
    # Taste und Umschalter, nicht der Text: so sieht Qt die Tastenfolge
    kombi = lambda mod, taste: QtGui.QKeySequence(QtCore.QKeyCombination(mod, taste))
    erwartet = {"Neu": kombi(Qt.ControlModifier, Qt.Key_N), "Öffnen": kombi(Qt.ControlModifier, Qt.Key_O),
                "Speichern": kombi(Qt.ControlModifier, Qt.Key_S)}
    ist = {n: next((b.aktion.shortcut() for b in befehle if b.text == n), None) for n in erwartet}
    check(p + "Strg+N/O/S sind Strg-Taste plus Buchstabe (QKeyCombination), unabhängig vom Text",
          ist == erwartet, str({n: v.toString() if v else v for n, v in ist.items()}))
    nativ = w.act_undo.shortcut().toString(QtGui.QKeySequence.NativeText)
    check(p + "Anzeigetext der Aktion (NativeText): " + ("„Strg+Z“" if uebersetzt else "„Ctrl+Z“ ohne Übersetzer"),
          nativ == ("Strg+Z" if uebersetzt else "Ctrl+Z"), nativ)

    # Rueckgaengig/Wiederholen schreiben ihren Hinweis nach jedem Schritt neu
    w.load_example("frame"); app.processEvents()
    w._meta_setzen("projekt", "Probe"); app.processEvents()
    t = w.act_undo.toolTip()
    check(p + "Rückgängig nach einem Schritt: „Rückgängig: … (Strg+Z)“",
          t.startswith("Rückgängig: ") and t.endswith("(Strg+Z)") and "Ctrl" not in t, repr(t))
    w.undo(); app.processEvents()
    t = w.act_redo.toolTip()
    check(p + "Wiederholen nach Rückgängig: „(Strg+Y)“", t.endswith("(Strg+Y)") and "Ctrl" not in t, repr(t))

    # und sie loesen wirklich aus: echter Tastendruck ins Fenster
    # (Strg+A wählt alle Knoten, Strg+F1 klappt das Ribbon ein)
    # zwei sichtbare Hauptfenster tragen dasselbe Kuerzel: Qt meldet „Ambiguous
    # shortcut overload“ und loest nichts aus - darum die anderen verstecken
    for x in app.topLevelWidgets():
        if x is not w and isinstance(x, type(w)) and x.isVisible():
            x.hide()
    w.show(); w.activateWindow(); app.processEvents()
    w.load_example("frame"); app.processEvents()
    vor = len(w.selection)
    QtTest.QTest.keyClick(w, Qt.Key_A, Qt.ControlModifier); app.processEvents()
    check(p + "Strg+A löst aus: wählt alle Knoten",
          vor == 0 and len(w.selection) == len(w.model.nodes) > 0, f"{vor} -> {len(w.selection)} von {len(w.model.nodes)}")
    a = w.anordnung.act_ribbon
    vorher = a.isChecked()
    QtTest.QTest.keyClick(w, Qt.Key_F1, Qt.ControlModifier); app.processEvents()
    zwischen = a.isChecked()
    QtTest.QTest.keyClick(w, Qt.Key_F1, Qt.ControlModifier); app.processEvents()
    check(p + "Strg+F1 löst aus: schaltet „Ribbon einklappen“ um und wieder zurück",
          zwischen != vorher and a.isChecked() == vorher, f"{vorher} -> {zwischen} -> {a.isChecked()}")


def test_hinweise_ohne_ctrl():
    """Die Hinweise aller Befehle zeigen Strg/Umschalt, die Kuerzel selbst
    bleiben - an einem Fenster, das ohne Uebersetzer gebaut wurde."""
    w, app = _fenster()
    _hinweise_und_kuerzel(w, app, "ohne Übersetzer", False)


def test_rueckfrage_tasten():
    """Mit dem Uebersetzer bestaetigt in „Ja/Nein“ die Taste J (vorher Y), N bleibt N."""
    from PySide6 import QtCore, QtTest, QtWidgets
    from statik3d.gui import sprache
    app = _app()
    _uebersetzer_entfernen(app)

    def druck(taste):
        S = QtWidgets.QMessageBox
        mb = S(S.Question, "t", "x", S.Yes | S.No)
        erg = []
        mb.buttonClicked.connect(lambda b: erg.append(b.text().replace("&", "")))
        mb.show(); app.processEvents()
        QtTest.QTest.keyClick(mb, taste)
        QtTest.QTest.qWait(400)          # animateClick wartet 100 ms
        mb.close()
        return erg
    Key = QtCore.Qt
    vorher = (druck(Key.Key_Y), druck(Key.Key_J), druck(Key.Key_N))
    check("ohne Übersetzer: Y bestätigt „Yes“, J tut nichts, N wählt „No“",
          vorher == (["Yes"], [], ["No"]), str(vorher))
    sprache.uebersetzer_laden(app)
    nachher = (druck(Key.Key_Y), druck(Key.Key_J), druck(Key.Key_N))
    check("mit Übersetzer: J bestätigt „Ja“, Y tut nichts, N wählt „Nein“",
          nachher == ([], ["Ja"], ["Nein"]), str(nachher))
    _uebersetzer_entfernen(app)


def test_handbuch():
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "Benutzerhandbuch.md")
    b = open(pfad, encoding="utf-8").read()
    i = b.find("Qt-Texte auf Deutsch")
    absatz = b[i:i + 2500] if i >= 0 else ""
    check("Handbuch: Qt-Texte auf Deutsch (Standardknöpfe, Kontextmenü der Textfelder, Strg statt Ctrl)",
          i >= 0 and "Bis zum 02.10.2026" in absatz and "Abbrechen" in absatz and "Ctrl" in absatz
          and "Umschalt" in absatz and "qtbase_de.qm" in absatz and "Protokoll" in absatz, "")
    check("Handbuch: das Beispiel ist „Ctrl+N“ am Knopf Neu (Rückgängig sagte schon vorher Strg+Z)",
          "„Ctrl+N“ am Knopf *Neu*" in absatz and "schon vorher" in absatz and "„Ctrl+Z“" not in absatz, "")
    check("Handbuch: in Rückfragen bestätigt jetzt die Taste J (vorher Y), N bleibt N",
          "Taste J" in absatz and "Taste Y" in absatz and "Taste N" in absatz, "")


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_kuerzeltext_tabelle, test_uebersetzer_laden, test_rueckfrage_tasten,
              test_fehlende_datei_still_mit_meldung, test_suchorte_und_exe, test_hinweise_ohne_ctrl,
              test_programmstart_laedt_uebersetzer, test_handbuch):
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
