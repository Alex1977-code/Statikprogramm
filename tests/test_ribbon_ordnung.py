"""
Ribbon-Ordnung im Kleinen (Plan-Paket 12a, 02.10.2026).

* Registerfolge: „Ergebnisse“ steht vor „Nachweise“ (nach dem Rechnen kommt
  das Ergebnis, danach der Nachweis);
* Gruppe „Kombinationen“ im Register Lasten: die Kombinationen nach EN 1990
  und nach DIN 19704 stehen beieinander (bis dahin eine in „Lasten“, die
  andere in „Berechnung“);
* Gruppe „Fugen / Passungen“ im Register Lager / Kontakt: Kontaktbedingung,
  Kontaktfugen, Passung, Übermaß, Spiel geben und Spalt / Toleranz (bis dahin
  verteilt auf Lasten, Geometrie, Netz und Lager / Kontakt);
* F1 öffnet das Handbuch, Strg+F setzt den Cursor in die Befehlssuche;
* Extras → Tastenkürzel zeigt die Liste aller Kürzel, aus den Befehlen des
  Ribbons erzeugt - nicht von Hand gepflegt; kein Kürzel steht zweimal.

Jede Aktion bleibt mit gleicher Funktion erreichbar: die Prüfung nennt die
umgezogenen Befehle und verlangt, dass jeder genau einmal im Ribbon steht.

Aufruf:  python -m tests.test_ribbon_ordnung
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_ribbonordnung_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}

#: Befehle, die in eine neue Gruppe gezogen wurden: Text -> (Register, Gruppe)
KOMBINATIONEN = {
    "Kombinationen automatisch…": ("Lasten", "Kombinationen"),
    "DIN 19704: Kombinationen": ("Lasten", "Kombinationen"),
}
FUGEN = {
    "Kontaktbedingung…": ("Lager / Kontakt", "Fugen / Passungen"),
    "Kontaktfugen ausführen": ("Lager / Kontakt", "Fugen / Passungen"),
    "Passung": ("Lager / Kontakt", "Fugen / Passungen"),
    "Übermaß": ("Lager / Kontakt", "Fugen / Passungen"),
    "Spiel geben": ("Lager / Kontakt", "Fugen / Passungen"),
    "Spalt / Toleranz": ("Lager / Kontakt", "Fugen / Passungen"),
}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _fenster():
    if "w" in _FENSTER:
        # nach einem Listen- oder Skizzenfenster ist das Hauptfenster nicht mehr aktiv; Kürzel und
        # Tastendrücke wirken nur im aktiven Fenster (ohne Aktivierung legte die Eingabetaste in
        # einer Maske zweimal an: Zeilenschluss des Felds und Hauptknopf)
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


def _register(w) -> list:
    tabs = w.ribbon.tabs
    return [tabs.tabText(i) for i in range(tabs.count())]


def _befehle(w, text: str) -> list:
    return [b for b in w.ribbon.befehle if b.text == text]


def _gruppen(w, register: str) -> list:
    """(Titel, Zahl der Knoepfe, Zahl aller Bedienelemente) je Gruppe eines
    Registers, in Reihenfolge - Auswahlfelder zaehlen nur bei den Elementen."""
    from PySide6 import QtWidgets
    reg = w.ribbon._register[register]
    aus = []
    for g in reg.findChildren(QtWidgets.QWidget, "ribbongruppe"):
        if g.isHidden():
            continue
        titel = g.findChild(QtWidgets.QLabel, "gruppentitel").text()
        aus.append((titel, len(g.findChildren(QtWidgets.QToolButton)),
                    len(g.feld.findChildren(QtWidgets.QWidget))))
    return aus


def test_registerfolge():
    w, _app = _fenster()
    reg = _register(w)
    check("Register: Ergebnisse steht vor Nachweise",
          "Ergebnisse" in reg and "Nachweise" in reg and reg.index("Ergebnisse") < reg.index("Nachweise"),
          str(reg))
    check("… die Folge Berechnung, Ergebnisse, Nachweise, Bericht ohne andere dazwischen",
          reg[reg.index("Berechnung"):reg.index("Berechnung") + 4]
          == ["Berechnung", "Ergebnisse", "Nachweise", "Bericht"], str(reg))
    check("… alle fünfzehn Register sind noch da",
          len(reg) == 15 and len(set(reg)) == 15, str(len(reg)))


def test_gruppe_kombinationen():
    w, _app = _fenster()
    for text, (register, gruppe) in KOMBINATIONEN.items():
        bs = _befehle(w, text)
        check(f"„{text}“ gibt es genau einmal, in {register} › {gruppe}",
              len(bs) == 1 and (bs[0].register, bs[0].gruppe) == (register, gruppe),
              str([(b.register, b.gruppe) for b in bs]))
    # beide Knoepfe in derselben Gruppe, in derselben Spalte (untereinander)
    from PySide6 import QtWidgets
    knoepfe = []
    for text in KOMBINATIONEN:
        akt = _befehle(w, text)[0].aktion
        for b in w.ribbon._register["Lasten"].findChildren(QtWidgets.QToolButton):
            if b.defaultAction() is akt:
                knoepfe.append(b)
    check("… beide als Knopf im Register Lasten, im selben Elternfeld der Gruppe",
          len(knoepfe) == 2 and knoepfe[0].parentWidget() is knoepfe[1].parentWidget()
          and knoepfe[0].geometry().x() == knoepfe[1].geometry().x(),
          str([k.text() for k in knoepfe]))
    # Auf dem Knopf steht kurz, was der Gruppentitel nicht sagt; mit den vollen
    # Namen waere das Register Lasten bei 1280 px zu breit (1293 px gemessen,
    # erlaubt 1241 px) - die Breite selbst prueft tests.test_glasleiste_ribbon
    check("… auf den Knöpfen steht „EN 1990…“ und „DIN 19704“, in der Suche der volle Name",
          [k.text() for k in knoepfe] == ["EN 1990…", "DIN 19704"]
          and all(_befehle(w, t)[0].text == t for t in KOMBINATIONEN),
          str([k.text() for k in knoepfe]))
    check("… der Hinweis am Knopf nennt die Norm genau (EN 1990 6.10, DIN 19704 Lastfallklassen)",
          len(knoepfe) == 2 and "EN 1990" in knoepfe[0].toolTip() and "6.10" in knoepfe[0].toolTip()
          and "DIN 19704" in knoepfe[1].toolTip() and "Lastfallklassen" in knoepfe[1].toolTip(),
          knoepfe[0].toolTip()[:50] if knoepfe else "kein Knopf")
    titel = [t for t, _n, _e in _gruppen(w, "Lasten")]
    check("Lasten: die Gruppen Lastfälle, Kombinationen, Lasten, Generierer, Weitere",
          "Kombinationen" in titel and titel.index("Lastfälle") < titel.index("Kombinationen")
          < titel.index("Lasten"), str(titel))
    st = [t for t, _n, _e in _gruppen(w, "Berechnung")]
    check("Berechnung: „DIN 19704: Kombinationen“ steht dort nicht mehr",
          not any(b.register == "Berechnung" and "19704" in b.text for b in w.ribbon.befehle), str(st))


def test_gruppe_fugen_passungen():
    w, _app = _fenster()
    for text, (register, gruppe) in FUGEN.items():
        bs = _befehle(w, text)
        check(f"„{text}“ gibt es genau einmal, in {register} › {gruppe}",
              len(bs) == 1 and (bs[0].register, bs[0].gruppe) == (register, gruppe),
              str([(b.register, b.gruppe) for b in bs]))
    gr = _gruppen(w, "Lager / Kontakt")
    titel = [t for t, _n, _e in gr]
    check("Lager / Kontakt: Lager, Kontakt, Fugen / Passungen, Anschlüsse",
          titel == ["Lager", "Kontakt", "Fugen / Passungen", "Anschlüsse"], str(titel))
    fug = {t: n for t, n, _e in gr}.get("Fugen / Passungen", 0)
    check("… die Gruppe trägt genau sechs Knöpfe", fug == 6, str(fug))
    # keine leere Gruppe in irgendeinem Register (Netz › Weiteres war nach dem
    # Umzug von „Kontaktfugen ausführen“ leer)
    leer = [f"{r} › {t}" for r in _register(w) for t, _n, e in _gruppen(w, r) if e == 0]
    check("kein Register hat eine Gruppe ohne Knopf", not leer, str(leer))


def test_f1_handbuch():
    from PySide6 import QtCore, QtGui, QtTest
    w, app = _fenster()
    f1 = [b for b in w.ribbon.befehle if b.aktion.shortcut().toString() == "F1"]
    check("F1 trägt genau einen Befehl, „Handbuch“",
          [b.text for b in f1] == ["Handbuch"], str([b.text for b in f1]))
    if len(f1) != 1:
        return
    a = f1[0].aktion
    check("… er gilt im ganzen Fenster (Anwendungskürzel, am Fenster)",
          a.shortcutContext() == QtCore.Qt.ApplicationShortcut and a in w.actions())
    check("… und der Hinweis nennt das Kürzel („F1“)", "F1" in a.toolTip(), a.toolTip())
    aufrufe = []
    w._browser = lambda url: (aufrufe.append(url.toString()), False)[1]
    w.ribbon.zeigen("Ansicht")
    w.plotter.interactor.setFocus()
    app.processEvents()
    # echter Tastendruck, wenn das Fenster aktiv ist (offscreen ist es das)
    if w.isActiveWindow():
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_F1)
    else:
        a.trigger()
    app.processEvents()
    check("F1 im Register „Ansicht“ öffnet das Benutzerhandbuch (ohne wirklich einen Browser zu starten)",
          len(aufrufe) == 1 and aufrufe[0].endswith("Benutzerhandbuch.md"),
          str(aufrufe) + ("" if w.isActiveWindow() else " (Aktion direkt ausgelöst)"))
    # Umschalt+F1 bleibt der Fang auf Knoten
    fang = w.act_fangart["knoten"]
    check("Umschalt+F1 bleibt der Fang auf Knoten (eigene Tastenfolge)",
          fang.shortcut().toString() == "Shift+F1" and fang is not a)


def test_strg_f_befehlssuche():
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    strg_f = [b for b in w.ribbon.befehle if b.aktion.shortcut().toString() == "Ctrl+F"]
    check("Strg+F trägt genau einen Befehl, „Befehlssuche“",
          [b.text for b in strg_f] == ["Befehlssuche"], str([b.text for b in strg_f]))
    if len(strg_f) != 1:
        return
    a = strg_f[0].aktion
    check("… er gilt im ganzen Fenster und der Hinweis nennt „Strg+F“",
          a.shortcutContext() == QtCore.Qt.ApplicationShortcut and a in w.actions()
          and "Strg+F" in a.toolTip(), a.toolTip())
    suche = w.ribbon.suche
    suche.setText("kombi")
    w.ribbon.zeigen("Ansicht")
    w.plotter.interactor.setFocus()
    app.processEvents()
    check("Vorbereitung: der Fokus liegt in der Ansicht, nicht in der Suche", not suche.hasFocus())
    if w.isActiveWindow():
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_F, QtCore.Qt.ControlModifier)
    else:
        a.trigger()
    app.processEvents()
    check("Strg+F setzt den Cursor in die Befehlssuche",
          suche.hasFocus(), "" if w.isActiveWindow() else "(Aktion direkt ausgelöst)")
    check("… und markiert, was schon darin steht (gleich überschreibbar)",
          suche.selectedText() == "kombi", repr(suche.selectedText()))
    suche.clear()
    # die Suche findet den Befehl selbst auch unter seinem Namen
    check("Die Befehlssuche findet „Befehlssuche“ (und „suchen“)",
          any(b.text == "Befehlssuche" for b in w.ribbon.finden("befehlssuche"))
          and any(b.text == "Befehlssuche" for b in w.ribbon.finden("such")))


def _aktionen_mit_kuerzel(w) -> list:
    from PySide6 import QtGui
    return [a for a in w.findChildren(QtGui.QAction) if not a.shortcut().isEmpty()]


def test_kuerzelliste():
    from PySide6 import QtWidgets
    from statik3d.gui.sprache import kuerzel_text
    w, app = _fenster()
    bs = _befehle(w, "Tastenkürzel")
    check("Extras: der Befehl „Tastenkürzel“ steht im Register Extras, genau einmal",
          len(bs) == 1 and bs[0].register == "Extras", str([(b.register, b.gruppe) for b in bs]))
    if len(bs) != 1:
        return
    w.ribbon.zeigen("Extras")
    bs[0].aktion.trigger()
    app.processEvents()
    dlg = getattr(w, "_kuerzelliste", None)
    check("Der Befehl öffnet die Liste, nicht modal (das Programm bleibt bedienbar)",
          dlg is not None and dlg.isVisible() and not dlg.isModal(),
          str(dlg and (dlg.isVisible(), dlg.isModal())))
    if dlg is None:
        return
    tbl = dlg.tabelle
    # die Zeilen der Befehle; dahinter steht der Abschnitt „Weitere Tasten“
    zeilen = [[tbl.item(r, c).text() for c in range(tbl.columnCount())] for r in range(dlg.n_befehle)]
    kopf = [tbl.horizontalHeaderItem(c).text() for c in range(tbl.columnCount())]
    check("Spalten: Befehl, Kürzel, Ort", kopf == ["Befehl", "Kürzel", "Ort"], str(kopf))
    # unabhaengig gezaehlt: jede Aktion des Fensters, die ein Kuerzel traegt
    erwartet = sorted(kuerzel_text(a.shortcut()) for a in _aktionen_mit_kuerzel(w))
    gezeigt = sorted(z[1] for z in zeilen)
    check("Die Liste führt alle Aktionen mit Kürzel - gezählt am Fenster, nicht am Ribbon",
          gezeigt == erwartet and len(zeilen) >= 30, f"{len(zeilen)} Zeilen, erwartet {len(erwartet)}")
    check("… kein Kürzel steht zweimal", len(set(gezeigt)) == len(gezeigt),
          str(sorted({k for k in gezeigt if gezeigt.count(k) > 1})))
    je = {z[1]: z for z in zeilen}
    check("… Handbuch steht mit F1, Befehlssuche mit Strg+F (deutsch geschrieben)",
          je.get("F1", [""])[0] == "Handbuch" and je.get("Strg+F", [""])[0] == "Befehlssuche",
          str((je.get("F1"), je.get("Strg+F"))))
    check("… Neu steht mit Strg+N, der Fang auf Knoten mit Umschalt+F1, Ribbon einklappen mit Strg+F1",
          je.get("Strg+N", [""])[0] == "Neu" and je.get("Umschalt+F1", [""])[0] == "auf Knoten"
          and je.get("Strg+F1", [""])[0] == "Ribbon einklappen",
          str((je.get("Strg+N"), je.get("Umschalt+F1"), je.get("Strg+F1"))))
    check("… „Ctrl“ kommt nirgends vor (die Liste nennt die Tasten der deutschen Tastatur)",
          not any("Ctrl" in z[1] or "Shift" in z[1] for z in zeilen))
    check("… die Spalte Ort nennt Register › Gruppe",
          je.get("F1", ["", "", ""])[2] == "Extras › Handbücher", str(je.get("F1")))
    # das Fenster zeigt, was jetzt gilt: ein neues Kuerzel erscheint beim naechsten Oeffnen
    from PySide6 import QtGui
    probe = QtGui.QAction("Probe", w)
    bis = len(w.ribbon.befehle)
    w.ribbon.kuerzel_setzen(probe, "Ctrl+Alt+P")
    from statik3d.gui import ribbon as rib
    w.ribbon.merken(rib.Befehl("Extras", "Probe", "Probe", probe))
    dlg.close()
    bs[0].aktion.trigger()
    app.processEvents()
    dlg = w._kuerzelliste
    tbl = dlg.tabelle
    namen = [tbl.item(r, 0).text() for r in range(tbl.rowCount())]
    check("Die Liste wird bei jedem Öffnen neu aus den Befehlen erzeugt (Probe-Befehl erscheint)",
          "Probe" in namen, str(len(namen)))
    del w.ribbon.befehle[bis:]
    probe.setShortcut(QtGui.QKeySequence())
    w.removeAction(probe)
    probe.deleteLater()
    dlg.close()
    # Filter
    bs[0].aktion.trigger()
    app.processEvents()
    dlg = w._kuerzelliste
    filt = dlg.filter
    filt.setText("handbuch")
    app.processEvents()
    sichtbar = [dlg.tabelle.item(r, 0).text() for r in range(dlg.tabelle.rowCount())
                if not dlg.tabelle.isRowHidden(r)]
    check("Das Filterfeld blendet Zeilen aus („handbuch“ lässt nur das Handbuch stehen)",
          sichtbar == ["Handbuch"], str(sichtbar))
    filt.setText("strg+f1")
    sichtbar = [dlg.tabelle.item(r, 1).text() for r in range(dlg.tabelle.rowCount())
                if not dlg.tabelle.isRowHidden(r)]
    check("… auch nach dem Kürzel („strg+f1“)", sichtbar == ["Strg+F1"], str(sichtbar))
    dlg.close()


def test_kuerzel_ohne_doppelte():
    w, _app = _fenster()
    folgen = {}
    for a in _aktionen_mit_kuerzel(w):
        folgen.setdefault(a.shortcut().toString(), []).append(a.text())
    doppelt = {k: v for k, v in folgen.items() if len(v) > 1}
    check("kein Kürzel doppelt belegt (auch nicht F1 und Strg+F)", not doppelt, str(doppelt))
    check("… die bisherigen Kürzel sind geblieben (F3, F5, F9, Strg+1, Umschalt+F7, Esc, Strg+F1)",
          all(k in folgen for k in ("F3", "F5", "F9", "Ctrl+1", "Shift+F7", "Esc", "Ctrl+F1")),
          str(sorted(folgen)))


def test_befehle_vollstaendig():
    """Jeder umgezogene Befehl ist weiter da; die Befehlssuche nennt den neuen Ort."""
    w, _app = _fenster()
    treffer = w.ribbon.finden("Spiel geben")
    check("Befehlssuche: „Spiel geben“ nennt Lager / Kontakt › Fugen / Passungen",
          treffer and w.ribbon.anzeige(treffer[0]) == "Spiel geben   (Lager / Kontakt › Fugen / Passungen)",
          w.ribbon.anzeige(treffer[0]) if treffer else "-")
    treffer = w.ribbon.finden("DIN 19704: Kombinationen")
    check("Befehlssuche: „DIN 19704: Kombinationen“ nennt Lasten › Kombinationen",
          treffer and w.ribbon.anzeige(treffer[0]) == "DIN 19704: Kombinationen   (Lasten › Kombinationen)",
          w.ribbon.anzeige(treffer[0]) if treffer else "-")
    treffer = w.ribbon.finden("überlagerung")
    texte = {b.text for b in treffer}
    check("… „Überlagerung“ findet weiter beide Kombinationsbefehle",
          {"Kombinationen automatisch…", "DIN 19704: Kombinationen"} <= texte, str(sorted(texte)[:4]))


def _liste_oeffnen(w, app):
    """Extras → Tastenkürzel auslösen, das Listenfenster zurückgeben (aktiv)."""
    w.ribbon.zeigen("Extras")
    _befehle(w, "Tastenkürzel")[0].aktion.trigger()
    app.processEvents()
    dlg = w._kuerzelliste
    dlg.activateWindow()
    app.processEvents()
    return dlg


def _vorgang_vorspiegeln(w, an: bool):
    """Einen Vorgang mit Balken und Abbrechen-Knopf vorspiegeln (Esc im
    Programmfenster bricht ihn ab, ``_esc_abbrechen``) oder wegnehmen."""
    if an:
        w._abbruch = False
        w._abbrechen_knopf("Probe")
        w.progress_bar.setVisible(True)
    else:
        w.btn_abbrechen.setVisible(False)
        w.progress_bar.setVisible(False)
        w._abbruch = False


def test_listenfenster_nimmt_esc_und_strg_f():
    """Die Ribbon-Kürzel sind Anwendungskürzel: im nicht modalen Listenfenster
    wirkte Esc im Hauptfenster (Auswahl aufheben, Vorgang abbrechen) statt das
    Fenster zu schließen, und Strg+F sprang in die Befehlssuche des
    Hauptfensters statt ins eigene Filterfeld (Gegenprüfung 03.10.2026)."""
    import numpy as np
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    w.load_example("frame")
    app.processEvents()
    for ziel_name in ("tabelle", "filter"):
        dlg = _liste_oeffnen(w, app)
        check(f"Vorbereitung ({ziel_name}): das Listenfenster ist das aktive Fenster", dlg.isActiveWindow())
        ziel = getattr(dlg, ziel_name)
        ziel.setFocus()
        w.selection = np.arange(3)
        _vorgang_vorspiegeln(w, True)
        QtTest.QTest.keyClick(ziel, QtCore.Qt.Key_Escape)
        app.processEvents()
        check(f"Esc im Listenfenster (Fokus: {ziel_name}) schließt es", not dlg.isVisible())
        check("… die Auswahl im Modell bleibt und der laufende Vorgang wird nicht abgebrochen",
              len(w.selection) == 3 and w._abbruch is False,
              f"Auswahl {len(w.selection)}, Abbruch {w._abbruch}")
        _vorgang_vorspiegeln(w, False)
    dlg = _liste_oeffnen(w, app)
    for ziel_name in ("tabelle", "filter"):
        ziel = getattr(dlg, ziel_name)
        dlg.filter.setText("Abc")
        ziel.setFocus()
        w.ribbon.suche.clearFocus()
        app.processEvents()
        QtTest.QTest.keyClick(ziel, QtCore.Qt.Key_F, QtCore.Qt.ControlModifier)
        app.processEvents()
        check(f"Strg+F im Listenfenster (Fokus: {ziel_name}) setzt den Cursor ins eigene Filterfeld",
              dlg.filter.hasFocus() and not w.ribbon.suche.hasFocus(),
              f"Filter {dlg.filter.hasFocus()}, Befehlssuche {w.ribbon.suche.hasFocus()}")
        check("… und markiert, was schon darin steht", dlg.filter.selectedText() == "Abc",
              repr(dlg.filter.selectedText()))
    dlg.close()
    # das Hauptfenster behält seine Kürzel: Esc bricht dort den Vorgang ab, Strg+F springt in die Suche
    w.activateWindow()
    app.processEvents()
    w.selection = np.arange(3)
    _vorgang_vorspiegeln(w, True)
    w.plotter.interactor.setFocus()
    app.processEvents()
    QtTest.QTest.keyClick(w, QtCore.Qt.Key_Escape)
    app.processEvents()
    check("Hauptfenster unverändert: Esc bricht den laufenden Vorgang ab, die Auswahl bleibt",
          w._abbruch is True and len(w.selection) == 3, f"Abbruch {w._abbruch}, Auswahl {len(w.selection)}")
    _vorgang_vorspiegeln(w, False)
    QtTest.QTest.keyClick(w, QtCore.Qt.Key_F, QtCore.Qt.ControlModifier)
    app.processEvents()
    check("Hauptfenster unverändert: Strg+F setzt den Cursor in die Befehlssuche", w.ribbon.suche.hasFocus())
    w.selection = np.arange(0)


#: Tasten ohne Befehl im Ribbon (Abschnitt „Weitere Tasten“ der Liste)
WEITERE = {
    ("Eintrag löschen", "Entf, Rücktaste", "Modellbaum"),
    ("Eintrag bearbeiten", "Eingabetaste", "Modellbaum"),
    ("Erster / letzter Eintrag", "Pos1, Ende", "Modellbaum"),
    # Teilpaket 8d (03.10.2026): Strg+F im Baum, Esc in seiner Filterzeile
    ("Modellbaum filtern", "Strg+F", "Modellbaum"),
    ("Filter aufheben", "Esc", "Filterzeile des Modellbaums"),
    ("Maske übernehmen", "Eingabetaste", "Maske rechts"),
    ("Laufenden Vorgang abbrechen", "Esc", "Programmfenster"),
    # Paket 14a (03.10.2026): Entf und die Einzeltasten in der Ansicht, die Tasten des Skizzenfensters
    ("Auswahl löschen", "Entf", "Ansicht"),
    ("Knoten anlegen", "K", "Ansicht"),
    ("Stab anlegen", "S", "Ansicht"),
    ("Lager setzen", "L", "Ansicht"),
    ("Last aufbringen", "B", "Ansicht"),
    ("Fläche aus Linien", "F", "Ansicht"),
    ("Schritt zurück, wiederholen", "Strg+Z, Strg+Y", "Skizzenfenster"),
    ("Element abbrechen", "Esc", "Skizzenfenster"),
    ("Gewähltes Element löschen", "Entf, Rücktaste", "Skizzenfenster"),
}


def test_weitere_tasten_in_der_liste():
    w, app = _fenster()
    dlg = _liste_oeffnen(w, app)
    tbl = dlg.tabelle
    zeilen = [[tbl.item(r, c).text() for c in range(tbl.columnCount())] for r in range(tbl.rowCount())]
    kopf = [i for i, z in enumerate(zeilen) if z[0].startswith("Weitere Tasten")]
    check("Die Liste hat einen Abschnitt „Weitere Tasten“ hinter den Befehlen",
          len(kopf) == 1 and kopf[0] == dlg.n_befehle, f"Trennzeile {kopf}, Befehle {dlg.n_befehle}")
    if len(kopf) != 1:
        dlg.close()
        return
    weitere = {tuple(z) for z in zeilen[kopf[0] + 1:]}
    check("… mit allen Tasten ohne Befehl: Modellbaum, Maske, Esc, Ansicht, Skizzenfenster",
          weitere == WEITERE, str(sorted(weitere ^ WEITERE))[:200])
    check("… die Trennzeile steht über alle drei Spalten", tbl.columnSpan(kopf[0], 0) == 3)
    text = dlg.hinweis.text()
    check("Der Hinweis im Fenster nennt, wo die Kürzel gelten: Programmfenster und seine nicht modalen "
          "Fenster, nicht unter modalen Dialogen",
          "nicht modalen" in text and "modale" in text and "Dialog" in text, text[:120])
    tip = tbl.item(kopf[0], 0).toolTip()
    check("… die Trennzeile sagt dasselbe von ihren Tasten (Hinweis an der Zeile)",
          "Programmfenster" in tip and "nicht modalen" in tip and "modalen Dialog" in tip, tip[:100])
    dlg.close()


def test_weitere_tasten_wirken():
    """Was der Abschnitt „Weitere Tasten“ verspricht, tut die Taste wirklich
    (echte Tastendrücke im aktiven Fenster)."""
    from PySide6 import QtCore, QtTest, QtWidgets
    w, app = _fenster()
    K = QtCore.Qt
    w.load_example("frame")
    app.processEvents()
    # Modellbaum: Pos1 / Ende, Eingabetaste
    b = w.baum
    b.setFocus()
    alle = b._alle_eintraege()
    QtTest.QTest.keyClick(b, K.Key_Home)
    ersten = b.currentItem() is alle[0]
    QtTest.QTest.keyClick(b, K.Key_End)
    check("Modellbaum: Pos1 geht zum ersten, Ende zum letzten Eintrag",
          ersten and b.currentItem() is alle[-1] and len(alle) > 2, str(len(alle)))
    ziel = next(i for i in alle if b._schluessel(i)[0])
    b.setCurrentItem(ziel)
    gesehen = []
    b.bearbeiten.connect(lambda art, name: gesehen.append((art, name)))
    # der Befehl öffnet für Knoten einen modalen Dialog: der bliebe in der Prüfung stehen
    exec_alt = QtWidgets.QDialog.exec
    QtWidgets.QDialog.exec = lambda self, *a, **k: 0
    try:
        QtTest.QTest.keyClick(b, K.Key_Return)
    finally:
        QtWidgets.QDialog.exec = exec_alt
    check("Modellbaum: die Eingabetaste bearbeitet den gewählten Eintrag",
          gesehen == [b._schluessel(ziel)], str(gesehen))
    # Modellbaum: Strg+F öffnet die Filterzeile, Esc in ihr hebt den Filter auf (8d)
    f = getattr(w, "baum_filter", None)
    w.activateWindow()
    b.setFocus()
    app.processEvents()
    QtTest.QTest.keyClick(b, K.Key_F, K.ControlModifier)
    app.processEvents()
    check("Modellbaum: Strg+F öffnet die Filterzeile, nicht die Befehlssuche",
          f is not None and f.isVisible() and QtWidgets.QApplication.focusWidget() is f
          and not w.ribbon.suche.hasFocus(), str(QtWidgets.QApplication.focusWidget()))
    if f is not None:
        f.setText("zzz")
        app.processEvents()
        QtTest.QTest.keyClick(f, K.Key_Escape)
        app.processEvents()
        check("Filterzeile des Modellbaums: Esc hebt den Filter auf, schließt sie, der Baum hat die Tastatur",
              f.text() == "" and f.isHidden() and QtWidgets.QApplication.focusWidget() is b
              and not [i for i in b._alle_eintraege() if i.isHidden()],
              f"{f.text()!r}, {f.isHidden()}, {QtWidgets.QApplication.focusWidget()}")
    # Maske: Eingabetaste übernimmt (Esc gehört dem Programmfenster, siehe die Prüfung oben)
    w.maske_knoten()
    app.processEvents()
    mk = w.maskenrand.maske
    felder = list(mk._felder.values())
    for f in felder:
        f.setText("7")
    n0 = w.model.nn
    felder[-1].setFocus()
    QtTest.QTest.keyClick(felder[-1], K.Key_Return)
    app.processEvents()
    check("Maske: die Eingabetaste übernimmt (Knoten angelegt)", w.model.nn == n0 + 1, f"{n0} -> {w.model.nn}")
    # Skizzenfenster: Entf löscht das gewählte Element
    f = w.unterlage_skizze_neu()
    app.processEvents()
    f.activateWindow()
    f.element_anfuegen({"art": "linie", "p1": [0, 0], "p2": [10, 0]})
    f.blatt.hervor = 0
    QtTest.QTest.keyClick(f.blatt, K.Key_Delete)
    check("Skizzenfenster: Entf löscht das gewählte Element", len(f.skizze["elemente"]) == 0,
          str(len(f.skizze["elemente"])))
    f.close()


def test_ort_der_befehlssuche():
    """Die Befehlssuche steht nicht im Register Extras, sondern oben rechts."""
    w, app = _fenster()
    b = _befehle(w, "Befehlssuche")[0]
    check("Ort der Befehlssuche in der Trefferliste: „Kopfzeile oben rechts“",
          w.ribbon.anzeige(b) == "Befehlssuche   (Kopfzeile oben rechts)", w.ribbon.anzeige(b))
    dlg = _liste_oeffnen(w, app)
    tbl = dlg.tabelle
    je = {tbl.item(r, 1).text(): tbl.item(r, 2).text() for r in range(dlg.n_befehle)}
    check("… und in der Kürzelliste", je.get("Strg+F") == "Kopfzeile oben rechts", str(je.get("Strg+F")))
    dlg.close()
    w.activateWindow()
    app.processEvents()
    w.ribbon.suche.clear()
    w.ribbon.zeigen("Berechnung")
    w.ribbon._anzeige = {w.ribbon.anzeige(b): b}
    w.ribbon._ausfuehren(b)
    app.processEvents()
    check("… die Suche führt den Befehl aus (Cursor in der Suche), ohne das Register Extras nach vorn zu holen",
          w.ribbon.suche.hasFocus()
          and w.ribbon.tabs.tabText(w.ribbon.tabs.currentIndex()) == "Berechnung",
          w.ribbon.tabs.tabText(w.ribbon.tabs.currentIndex()))


def test_lastenheft_nennt_den_neuen_ort():
    from statik3d.model import Model
    from statik3d.bridges import lastenheft as lh
    absatz = " ".join(b[1] for b in lh.Lastenheft(Model()).kapitel_kombinationen() if b[0] == "p")
    check("Lastenheft: „Kombinationen nach DIN 19704 bilden“ steht in Lasten › Kombinationen",
          "Lasten › Kombinationen" in absatz and "DIN 19704“" in absatz, absatz[-90:])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_registerfolge, test_gruppe_kombinationen, test_gruppe_fugen_passungen,
              test_f1_handbuch, test_strg_f_befehlssuche, test_kuerzelliste,
              test_kuerzel_ohne_doppelte, test_befehle_vollstaendig,
              test_listenfenster_nimmt_esc_und_strg_f, test_weitere_tasten_in_der_liste,
              test_weitere_tasten_wirken, test_ort_der_befehlssuche,
              test_lastenheft_nennt_den_neuen_ort):
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
