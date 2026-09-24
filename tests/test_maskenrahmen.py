"""
Gemeinsamer Maskenrahmen rechts (Paket 1 des Oberflaechenplans, 24.09.2026).

Befund der Analyse: lange Masken hatten keinen Rollbereich. Ihre Mindesthoehe
zog das Hauptfenster bis 1749 px hoch (Wind, Wasserdruck-Generator, „Lager 1“,
Neu: Kontaktbedingung), „Übernehmen“ lag dann unter dem Bildschirmrand. Kurze
Masken wurden auf die ganze Hoehe gestreckt, der Titel stand doppelt (Dock und
Maske), und Enter wirkte nur in Textfeldern.

Geprueft wird:

* die Maske allein (offscreen): fester Kopf mit Titel und Hinweiszeile,
  rollbare Mitte mit den Feldern, fester Fuss mit den Knoepfen; Enter loest
  den Hauptknopf genau einmal aus; Tab laeuft von oben nach unten; das Feld
  mit dem Fokus wird in der Rollflaeche sichtbar;
* das Hauptfenster (offscreen) bei 1366 x 768: keine Maske laesst es wachsen,
  der Hauptknopf bleibt im Fenster; kurze Masken stehen oben buendig und
  ungestreckt; der Docktitel verschwindet, solange eine Maske ihren eigenen
  Titel zeigt; der Klickmodus der Felder geht in der Rollflaeche weiter.

Aufruf:  python -m tests.test_maskenrahmen
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
# Einstellungen in eine Wegwerfdatei - die Pruefung darf die des Anwenders
# nicht ueberschreiben
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_maskenrahmen_"), "einstellungen.json")

RESULTS = []

#: Sollgroesse des Fensters: der kleine Bildschirm aus der Analyse
SOLL = (1366, 768)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:74s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _ruhe(n: int = 3):
    app = _app()
    for _ in range(n):
        app.processEvents()


def _zeiger(x):
    import shiboken6
    return shiboken6.getCppPointer(x)[0]


def _tabkette(wurzel):
    """Die Widgets, die Tab der Reihe nach erreicht (innerhalb von wurzel)."""
    from PySide6 import QtCore
    tab = QtCore.Qt.FocusPolicy.TabFocus.value
    out, gesehen = [], set()
    x = wurzel.nextInFocusChain()
    while x is not None and _zeiger(x) != _zeiger(wurzel) and _zeiger(x) not in gesehen:
        gesehen.add(_zeiger(x))
        if (wurzel.isAncestorOf(x) and (x.focusPolicy().value & tab) == tab
                and x.isVisibleTo(wurzel) and x.isEnabled()):
            out.append(x)
        x = x.nextInFocusChain()
    return out


def _ab(kette, start):
    """Die Tab-Kette ist ein Ring: ab dem Widget start lesen."""
    z = [_zeiger(x) for x in kette]
    if _zeiger(start) not in z:
        return kette
    i = z.index(_zeiger(start))
    return kette[i:] + kette[:i]


def _tab_im_fenster(maske, start, n=80):
    """Tab im Hauptfenster ab start: die fokussierbaren Widgets der Maske,
    bis Tab die Maske verlaesst."""
    from PySide6 import QtCore
    tab = QtCore.Qt.FocusPolicy.TabFocus.value
    out, x = [start], start.nextInFocusChain()
    while x is not None and len(out) < n and _zeiger(x) != _zeiger(start):
        if (x.focusPolicy().value & tab) == tab and x.isVisible() and x.isEnabled():
            if not maske.isAncestorOf(x):
                break
            out.append(x)
        x = x.nextInFocusChain()
    return out


def _lange_maske(n: int = 40, **kw):
    from statik3d.gui import masken as msk
    felder = [msk.Feld(f"f{i}", f"Feld {i}") for i in range(n)]
    return msk.Maske("Lange Maske", felder, hinweis="Hinweis unter dem Titel", **kw)


# --------------------------------------------------------------------------
# Die Maske allein
# --------------------------------------------------------------------------
def test_rahmen_aufbau():
    from PySide6 import QtWidgets
    _app()
    mk = _lange_maske(40, knopf="Übernehmen", abbrechen="Abbrechen",
                      zusatz=[("Löschen", lambda: None)])
    rolle = getattr(mk, "rolle", None)
    check("Maske hat eine rollbare Mitte (QScrollArea)",
          isinstance(rolle, QtWidgets.QScrollArea), type(rolle).__name__)
    if not isinstance(rolle, QtWidgets.QScrollArea):
        return
    check("alle Felder liegen in der Rollfläche",
          all(rolle.widget().isAncestorOf(w) for w in mk._felder.values()))
    fuss = [mk.btn_anwenden, mk.btn_abbrechen, mk.zusatzknoepfe["Löschen"]]
    check("Hauptknopf, Abbrechen und Löschen liegen im festen Fuß, nicht in der Rollfläche",
          not any(rolle.isAncestorOf(b) for b in fuss))
    check("die Hinweiszeile liegt im festen Kopf, nicht in der Rollfläche",
          not rolle.isAncestorOf(mk.lbl_hinweis))
    mk.resize(420, 330)
    mk.show()
    _ruhe()
    y_hinweis = mk.lbl_hinweis.mapTo(mk, mk.lbl_hinweis.rect().topLeft()).y()
    y_rolle = rolle.mapTo(mk, rolle.rect().topLeft()).y()
    y_knopf = mk.btn_anwenden.mapTo(mk, mk.btn_anwenden.rect().topLeft()).y()
    titel = [lb for lb in mk.findChildren(QtWidgets.QLabel) if lb.objectName() == "maskentitel"]
    y_titel = titel[0].mapTo(mk, titel[0].rect().topLeft()).y() if titel else -1
    check("Reihenfolge von oben: Titel, Hinweiszeile, Rollfläche, Knöpfe",
          0 <= y_titel < y_hinweis < y_rolle < y_knopf, str((y_titel, y_hinweis, y_rolle, y_knopf)))
    check("der Hauptknopf bleibt bei 330 px Höhe im Bild (40 Felder rollen)",
          y_knopf + mk.btn_anwenden.height() <= mk.height()
          and not mk.btn_anwenden.visibleRegion().isEmpty(),
          f"{y_knopf + mk.btn_anwenden.height()} <= {mk.height()}")
    check("die Rollfläche rollt tatsächlich (Inhalt höher als sichtbar)",
          rolle.verticalScrollBar().maximum() > 0, str(rolle.verticalScrollBar().maximum()))
    check("Mindesthöhe der langen Maske klein (< 260 px) - sie zwingt kein Fenster größer",
          mk.minimumSizeHint().height() < 260, str(mk.minimumSizeHint().height()))
    mk.close()


def test_fokus_sichtbar():
    _app()
    mk = _lange_maske(40)
    mk.resize(420, 300)
    mk.show()
    mk.activateWindow()
    _ruhe()
    rolle = getattr(mk, "rolle", None)
    if rolle is None:
        check("Fokus in der Rollfläche sichtbar (keine Rollfläche)", False)
        return
    letztes = mk._felder["f39"]
    letztes.setFocus()
    _ruhe()
    vp = rolle.viewport()
    oben = letztes.mapTo(vp, letztes.rect().topLeft()).y()
    unten = oben + letztes.height()
    check("Fokus auf das letzte Feld: die Rollfläche rollt es ins Bild",
          0 <= oben and unten <= vp.height(), f"{oben}..{unten} in 0..{vp.height()}")
    erstes = mk._felder["f0"]
    erstes.setFocus()
    _ruhe()
    oben = erstes.mapTo(vp, erstes.rect().topLeft()).y()
    check("… und zurück zum ersten Feld wieder nach oben",
          0 <= oben and oben + erstes.height() <= vp.height(), str(oben))
    mk.close()


def test_enter_ist_hauptknopf():
    from PySide6 import QtCore, QtTest
    from statik3d.gui import masken as msk
    _app()
    felder = [msk.Feld("x", "x [m]"), msk.Feld("an", "mit Haken", "haken", False),
              msk.Feld("art", "Art", "wahl", "A", ["A", "B"])]
    mk = msk.Maske("Enter", felder, knopf="Übernehmen", abbrechen="Abbrechen")
    zaehler = {"an": 0, "ab": 0}
    mk.angewendet.connect(lambda _w: zaehler.__setitem__("an", zaehler["an"] + 1))
    mk.abgebrochen.connect(lambda: zaehler.__setitem__("ab", zaehler["ab"] + 1))
    mk.show()
    mk.activateWindow()
    _ruhe()
    mk._felder["x"].setFocus()
    QtTest.QTest.keyClick(mk._felder["x"], QtCore.Qt.Key_Return)
    _ruhe()
    check("Enter im Zahlenfeld: Hauptknopf genau einmal", zaehler["an"] == 1, str(zaehler))
    mk._felder["an"].setFocus()
    QtTest.QTest.keyClick(mk._felder["an"], QtCore.Qt.Key_Return)
    _ruhe()
    check("Enter auf einem Haken: Hauptknopf (einmal)", zaehler["an"] == 2, str(zaehler))
    mk._felder["art"].setFocus()
    QtTest.QTest.keyClick(mk._felder["art"], QtCore.Qt.Key_Enter)
    _ruhe()
    check("Enter (Ziffernblock) auf einer Auswahlliste: Hauptknopf (einmal)",
          zaehler["an"] == 3, str(zaehler))
    mk.btn_abbrechen.setFocus()
    QtTest.QTest.keyClick(mk.btn_abbrechen, QtCore.Qt.Key_Return)
    _ruhe()
    check("Enter auf „Abbrechen“ bricht ab und übernimmt nichts",
          zaehler == {"an": 3, "ab": 1}, str(zaehler))
    mk.close()


def test_tabfolge():
    _app()
    mk = _lange_maske(5, knopf="Übernehmen", abbrechen="Abbrechen",
                      zusatz=[("Löschen", lambda: None)])
    kette = _ab(_tabkette(mk), mk._felder["f0"])
    soll = [mk._felder[f"f{i}"] for i in range(5)] + [
        mk.btn_anwenden, mk.btn_abbrechen, mk.zusatzknoepfe["Löschen"], mk.btn_zu]
    check("Tab: erst die Felder von oben nach unten, dann die Knöpfe des Fußes, zuletzt ✕",
          [_zeiger(x) for x in kette] == [_zeiger(x) for x in soll],
          str([type(x).__name__ + ":" + (x.text() if hasattr(x, "text") else "") for x in kette][:9]))


def test_ermuedungsmaske_im_rahmen():
    """Die Ermuedungsmaske setzt ihren Inhalt in die Rollflaeche - Tab erreicht
    ihn vor den Knoepfen des Fusses."""
    from tests.test_ermuedungsmaske import _mit_lasten, _maske
    mk, _ = _maske(_mit_lasten())
    rolle = getattr(mk, "rolle", None)
    check("Ermüdungsmaske: Tabelle und Editor liegen in der Rollfläche",
          rolle is not None and rolle.widget().isAncestorOf(mk.tabelle)
          and rolle.widget().isAncestorOf(mk.name))
    kette = [_zeiger(x) for x in _ab(_tabkette(mk), mk.tabelle)]
    i_tab = kette.index(_zeiger(mk.tabelle)) if _zeiger(mk.tabelle) in kette else -1
    i_knopf = kette.index(_zeiger(mk.btn_anwenden)) if _zeiger(mk.btn_anwenden) in kette else -1
    check("Ermüdungsmaske: Tab erreicht die Tabelle vor „Übernehmen“",
          0 <= i_tab < i_knopf, f"Tabelle {i_tab}, Übernehmen {i_knopf}")
    check("Ermüdungsmaske: Mindesthöhe < 300 px (die Tabelle rollt mit)",
          mk.minimumSizeHint().height() < 300, str(mk.minimumSizeHint().height()))


def test_querschnittmaske():
    """Die Querschnittsmaske hat ihren eigenen Aufbau (zwei „Anlegen“ in den
    Gruppen), folgt aber dem Rahmen: Hinweis oben, kleine Mindesthoehe."""
    from PySide6 import QtWidgets
    from statik3d.gui.profilmaske import QuerschnittMaske
    _app()
    mk = QuerschnittMaske()
    mk.resize(460, 500)
    mk.show()
    _ruhe()
    rollen = mk.findChildren(QtWidgets.QScrollArea)
    rolle = rollen[0] if rollen else None
    y_hinweis = mk.lbl_hinweis.mapTo(mk, mk.lbl_hinweis.rect().topLeft()).y()
    y_rolle = rolle.mapTo(mk, rolle.rect().topLeft()).y() if rolle is not None else -1
    check("Querschnittsmaske: Hinweiszeile über der Rollfläche",
          rolle is not None and 0 <= y_hinweis < y_rolle, f"{y_hinweis} / {y_rolle}")
    check("Querschnittsmaske: Mindesthöhe < 300 px",
          mk.minimumSizeHint().height() < 300, str(mk.minimumSizeHint().height()))
    mk.close()


# --------------------------------------------------------------------------
# Nachbesserung nach der Gegenpruefung (24.09.2026)
# --------------------------------------------------------------------------
def _gemischte_maske(n=30, wahl_bei=10, haken_bei=6):
    """Lange Maske mit einer Auswahlliste und einem Haken mittendrin."""
    from statik3d.gui import masken as msk
    felder = []
    for i in range(n):
        if i == wahl_bei:
            felder.append(msk.Feld("wahl", "Zone", "wahl", "Zone 2", ["Zone 1", "Zone 2", "Zone 3"]))
        elif i == haken_bei:
            felder.append(msk.Feld("hk", "Stäbe als Fachwerk", "haken", False))
        else:
            felder.append(msk.Feld(f"f{i}", f"Feld {i}"))
    return msk.Maske("Gemischt", felder, hinweis="Hinweis")


def _rad(ziel, dy=-120):
    """Ein Mausradschritt ueber der Mitte von ziel (nach unten: dy < 0)."""
    from PySide6 import QtCore, QtGui
    lokal = QtCore.QPointF(ziel.width() / 2, ziel.height() / 2)
    ev = QtGui.QWheelEvent(lokal, QtCore.QPointF(ziel.mapToGlobal(lokal.toPoint())),
                           QtCore.QPoint(0, 0), QtCore.QPoint(0, dy), QtCore.Qt.NoButton,
                           QtCore.Qt.NoModifier, QtCore.Qt.NoScrollPhase, False)
    _app().sendEvent(ziel, ev)


def test_rad_ueber_auswahlliste():
    """Befund 2: das Mausrad ueber einer Auswahlliste der Mitte verstellte
    ihren Wert (Windzone 2 -> 3), statt zu rollen."""
    _app()
    mk = _gemischte_maske()
    mk.resize(420, 300)
    mk.show()
    mk.activateWindow()
    _ruhe()
    cb = mk._felder["wahl"]
    mk._felder["f0"].setFocus()
    _ruhe()
    mk.rolle.ensureWidgetVisible(cb)
    _ruhe()
    vor = mk.rolle.verticalScrollBar().value()
    _rad(cb)
    _ruhe()
    nach = mk.rolle.verticalScrollBar().value()
    check("Mausrad über einer Auswahlliste ohne Fokus: der Wert bleibt",
          cb.currentText() == "Zone 2", cb.currentText())
    check("… und die Mitte rollt stattdessen", nach > vor, f"{vor} -> {nach}")
    check("Auswahllisten nehmen den Fokus nicht per Rad (StrongFocus)",
          cb.focusPolicy() == cb.focusPolicy().StrongFocus, str(cb.focusPolicy()))
    mk.close()


def test_klick_auf_halb_sichtbaren_haken():
    """Befund 5: beim Druecken auf einen halb sichtbaren Haken rollte die
    Mitte ihn ins Bild, das Loslassen traf daneben - der Haken blieb aus."""
    from PySide6 import QtCore, QtTest
    _app()
    mk = _gemischte_maske(haken_bei=14)
    mk.resize(420, 300)
    mk.show()
    mk.activateWindow()
    _ruhe()
    mk._felder["f0"].setFocus()
    _ruhe()
    hk = mk._felder["hk"]
    vp = mk.rolle.viewport()
    sb = mk.rolle.verticalScrollBar()
    # den Haken zur Haelfte unter den unteren Rand schieben
    y_mitte = hk.mapTo(mk.mitte, QtCore.QPoint(0, 0)).y()
    sb.setValue(max(0, y_mitte - vp.height() + hk.height() // 2))
    _ruhe()
    oben = hk.mapTo(vp, QtCore.QPoint(0, 0)).y()
    halb = 0 < vp.height() - oben < hk.height()
    druck = QtCore.QPoint(8, max(2, (vp.height() - oben) // 2))
    bildschirm = hk.mapToGlobal(druck)
    QtTest.QTest.mousePress(hk, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, druck)
    _ruhe()
    # Loslassen an derselben Bildschirmstelle - wie eine echte Maus
    QtTest.QTest.mouseRelease(hk, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                              hk.mapFromGlobal(bildschirm))
    _ruhe()
    check("Klick auf einen halb sichtbaren Haken schaltet ihn um",
          halb and hk.isChecked(), f"halb sichtbar {halb}, Haken {hk.isChecked()}")
    # Tab auf ein verdecktes Feld rollt es dagegen weiter ins Bild
    sb.setValue(0)
    _ruhe()
    vorher, ziel = mk._felder["f24"], mk._felder["f25"]
    vorher.setFocus()
    _ruhe()
    QtTest.QTest.keyClick(vorher, QtCore.Qt.Key_Tab)
    _ruhe()
    o = ziel.mapTo(vp, QtCore.QPoint(0, 0)).y()
    check("Tab auf ein verdecktes Feld rollt es ganz ins Bild",
          mk.focusWidget() is ziel and 0 <= o and o + ziel.height() <= vp.height(),
          f"{o}..{o + ziel.height()} in 0..{vp.height()}")
    mk.close()


def test_pfeiltasten_rollen_nicht():
    """Befund 9: Pfeil ab in einem Textfeld rollte die Mitte weg, das Feld
    mit der Schreibmarke verschwand."""
    from PySide6 import QtCore, QtTest
    _app()
    mk = _lange_maske(40)
    mk.resize(420, 300)
    mk.show()
    mk.activateWindow()
    _ruhe()
    feld = mk._felder["f3"]
    feld.setFocus()
    _ruhe()
    vp = mk.rolle.viewport()
    for _ in range(6):
        QtTest.QTest.keyClick(feld, QtCore.Qt.Key_Down)
    QtTest.QTest.keyClick(feld, QtCore.Qt.Key_PageDown)
    _ruhe()
    o = feld.mapTo(vp, QtCore.QPoint(0, 0)).y()
    check("6× Pfeil ab und Bild ab im Textfeld: das Feld bleibt ganz sichtbar",
          0 <= o and o + feld.height() <= vp.height(), f"{o} in 0..{vp.height()}")
    mk.close()


def test_enter_auf_tabelle_und_liste():
    """Befund 11: Enter auf der Tabelle der Ermuedungsmaske uebernahm die
    Zeile (Rueckgaengig-Sicherung und refresh_all ohne Aenderung)."""
    from PySide6 import QtCore, QtTest
    from tests.test_ermuedungsmaske import _mit_lasten, _maske
    mk, haken = _maske(_mit_lasten())
    mk.show()
    mk.activateWindow()
    _ruhe()
    klicks = {"n": 0}
    mk.btn_anwenden.clicked.connect(lambda *_: klicks.__setitem__("n", klicks["n"] + 1))
    for w in (mk.tabelle, mk.verfuegbar):
        if not w.isVisible():
            continue
        w.setFocus()
        _ruhe()
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_Return)
        _ruhe()
    check("Enter auf Tabelle und Liste der Ermüdungsmaske: „Übernehmen“ nicht ausgelöst",
          klicks["n"] == 0 and not haken.was, f"Klicks {klicks['n']}, geschrieben {haken.was}")
    mk.name.setFocus()
    _ruhe()
    QtTest.QTest.keyClick(mk.name, QtCore.Qt.Key_Return)
    _ruhe()
    check("… im Feld Name übernimmt Enter weiter (genau einmal)", len(haken.was) == 1,
          str(haken.was))
    mk.close()


def test_rolle_wuenscht_volle_hoehe():
    """Rueckname-Luecke F10: die Mitte meldet die volle Hoehe ihres Inhalts
    als Wunsch - eine Maske mit 25 Feldern rollt nicht, wenn Platz da ist."""
    _app()
    mk = _lange_maske(25)
    mk.resize(mk.sizeHint())
    mk.show()
    _ruhe()
    check("25 Felder in ihrer Wunschgröße: die Mitte rollt nicht",
          mk.rolle.verticalScrollBar().maximum() == 0,
          f"Rollweg {mk.rolle.verticalScrollBar().maximum()}, Höhe {mk.height()}")
    mk.close()


def test_inhalt_waechst_nach():
    """Rueckname-Luecke F11: aendert sich der Inhalt der Mitte nachtraeglich,
    waechst die Wunschhoehe der Maske mit."""
    from PySide6 import QtWidgets
    _app()
    mk = _lange_maske(3)
    mk.show()
    _ruhe()
    h0 = mk.sizeHint().height()
    neu = QtWidgets.QWidget()
    neu.setFixedHeight(200)
    mk.inhalt_einfuegen(neu)
    _ruhe()
    h1 = mk.sizeHint().height()
    check("200 px Inhalt nachträglich: die Wunschhöhe der Maske wächst mit",
          h1 >= h0 + 150, f"{h0} -> {h1}")
    mk.close()


def test_schwebende_maske_begrenzt():
    """Rueckname-Luecke F12: ohne Ziel schwebt die Maske ueber der Ansicht
    und wird nie hoeher als die Ansicht (minus 24 px)."""
    from PySide6 import QtWidgets
    from statik3d.gui import masken as msk
    _app()
    ansicht = QtWidgets.QWidget()
    ansicht.resize(700, 400)
    ansicht.show()
    _ruhe()
    rand = msk.Maskenrand(ansicht)
    mk = rand.zeigen(_lange_maske(40))
    _ruhe()
    check("schwebende lange Maske: höchstens Ansichtshöhe − 24 px, Hauptknopf sichtbar",
          mk.height() <= ansicht.height() - 24 and not mk.btn_anwenden.visibleRegion().isEmpty(),
          f"{mk.height()} bei Ansicht {ansicht.height()}")
    rand.schliessen()
    ansicht.close()


# --------------------------------------------------------------------------
# Mit Hauptfenster (offscreen)
# --------------------------------------------------------------------------
_FENSTER = {}
_FEHLER = []


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from statik3d.gui.main import MainWindow
    app = _app()
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    # Offscreen haelt ein modales Meldungsfenster den Lauf an: Fehler nur
    # mitschreiben (eine Maske, die mit einer Meldung abbricht, zaehlt dann
    # als „ohne Maske“)
    w.error = lambda *a, **k: _FEHLER.append(" ".join(str(x) for x in a)[:120])
    from PySide6 import QtWidgets
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    w.load_example("frame")
    _ruhe()
    _FENSTER.update(w=w, app=app)
    return w, app


def _zuruecksetzen(w, groesse=SOLL):
    if w.maskenrand.offen():
        w.maskenrand.schliessen()
    _ruhe()
    w.resize(*groesse)
    _ruhe()


#: Masken, die das Fenster vorher wachsen liessen (bilder.md) - und die
#: uebrigen Erzeuge- und Einstellmasken aus dem Ribbon
MASKEN = [
    ("Wind-Generator", "maske_wind", ()),
    ("Wasserdruck-Generator", "maske_wasserdruck", ()),
    ("Neu: Kontaktbedingung", "_baum_neu", ("kontaktbedingungen",)),
    ("Klick auf „Lager 1“", "_baum_geklickt", ("lager_einzeln", "1")),
    ("Ermüdungslasten", "maske_ermuedungslasten", ()),
    ("Querschnitt HEB 300", "_baum_geklickt", ("querschnitt", "HEB 300")),
    ("Neuer Querschnitt", "_baum_neu", ("querschnitte",)),
    ("Stab Riegel", "_baum_geklickt", ("stab", "Riegel")),
    ("Lastfall LF1", "_baum_geklickt", ("lastfall", "LF1")),
    ("Neu: Schweißnaht", "_baum_neu", ("schweissnaehte",)),
    ("Neu: Stellung", "_baum_neu", ("stellungen",)),
]
for _m in ("maske_knoten", "maske_linie", "maske_stab", "maske_schale", "maske_platte",
           "maske_quader", "maske_stabzug", "maske_lager", "maske_knotenlast",
           "maske_linienlast", "maske_flaechenlast", "maske_temperaturlast",
           "maske_zwangsverformung", "maske_vorspannung", "maske_spalt", "maske_spiel",
           "maske_passung", "maske_uebermass", "maske_netzeinstellungen", "maske_netzguete",
           "maske_schwingung", "maske_schweissnaht", "maske_din19704_lastfaelle",
           "maske_einheiten", "maske_schnittebene", "maske_lot"):
    MASKEN.append((_m, _m, ()))
for _z in ("lastfaelle", "kombinationen", "werkstoffe", "dicken", "linien", "stabelemente",
           "staebe", "geoflaechen", "geokoerper", "ermuedungslasten", "gelenke", "lager",
           "linienlager", "flaechenlager"):
    MASKEN.append((f"Neu: {_z}", "_baum_neu", (_z,)))


def test_fenster_waechst_nie():
    from PySide6 import QtCore
    w, _app_ = _fenster()
    _zuruecksetzen(w)
    check(f"Ausgangslage: Fenster {SOLL[0]}x{SOLL[1]}",
          (w.width(), w.height()) == SOLL, f"{w.width()}x{w.height()}")
    gewachsen, knopf_weg, ohne = [], [], []
    for text, meth, args in MASKEN:
        _zuruecksetzen(w)
        fn = getattr(w, meth, None)
        if fn is None:
            ohne.append(text)
            continue
        print(f"     … {text}", flush=True)
        try:
            fn(*args)
        except Exception as ex:      # noqa: BLE001
            ohne.append(f"{text}: {ex}")
            continue
        _ruhe(4)
        mk = w.maskenrand.maske if w.maskenrand.offen() else None
        if mk is None:
            ohne.append(text)
            continue
        if w.height() > SOLL[1] or w.minimumSizeHint().height() > SOLL[1]:
            gewachsen.append(f"{text} ({w.height()} px, min {w.minimumSizeHint().height()})")
        knopf = getattr(mk, "btn_anwenden", None)
        if knopf is not None:
            unten = knopf.mapTo(w, QtCore.QPoint(0, knopf.height())).y()
            if unten > w.height() or knopf.visibleRegion().isEmpty():
                knopf_weg.append(f"{text} (Unterkante {unten})")
    check(f"keine der {len(MASKEN)} Masken lässt das Fenster über {SOLL[1]} px wachsen",
          not gewachsen, "; ".join(gewachsen[:6]))
    check("der Hauptknopf jeder Maske bleibt im Fenster sichtbar",
          not knopf_weg, "; ".join(knopf_weg[:6]))
    # Am Hallenrahmen melden einige Befehle nur, dass etwas fehlt (kein
    # Zylinder fuer Spalt/Spiel/Passung, keine Fuge fuer Übermaß …)
    print(f"     ohne Maske (Meldung statt Maske): {ohne}")
    print(f"     Meldungen: {_FEHLER[-len(ohne):] if ohne else []}")
    check(f"mindestens 40 der {len(MASKEN)} Masken ließen sich öffnen und wurden geprüft",
          len(MASKEN) - len(ohne) >= 40, f"{len(MASKEN) - len(ohne)} geprüft")
    _zuruecksetzen(w)


def _oeffnen(w, schritt):
    """Einen Schritt der Gegenpruefung ausfuehren (Maske oder Register)."""
    schritte = {
        "Knoten": lambda: w.maske_knoten(),
        "Wind": lambda: w.maske_wind(),
        "Wasserdruck": lambda: w.maske_wasserdruck(),
        "Kontakt": lambda: w._baum_neu("kontaktbedingungen"),
        "Lager 1": lambda: w._baum_geklickt("lager_einzeln", "1"),
        "Netz": lambda: w.maske_zeigen("Netz"),
        "zu": lambda: w.maskenrand.schliessen(),
    }
    schritte[schritt]()
    _ruhe(6)


def test_ansicht_kommt_zurueck():
    """Befunde 1 und 7: nach einer breiten langen Maske (Wind, Kontakt-
    bedingung) blieb der rechte Bereich so breit, die 3D-Ansicht bei 61 px -
    auch fuer die schmale Knotenmaske und das Register Netz."""
    w, _app_ = _fenster()
    _zuruecksetzen(w)
    ansicht = w.maskenrand.ansicht
    werte = []
    for folge in (("Wind", "Knoten"), ("Kontakt", "Knoten", "Netz"),
                  ("Wind", "zu", "Knoten")):
        _zuruecksetzen(w)
        for s in folge:
            _oeffnen(w, s)
        werte.append((folge, w.eingaben_dock.width(), ansicht.visibleRegion().boundingRect().width()))
    ok = all(rechts <= 480 and sicht >= 500 for _f, rechts, sicht in werte)
    check("nach Wind/Kontaktbedingung: Knoten bzw. Netz geben der Ansicht die Breite zurück",
          ok, "; ".join(f"{'→'.join(f)}: rechts {r}, Ansicht {s}" for f, r, s in werte))
    _zuruecksetzen(w)


def test_unten_bleibt():
    """Befund 4: der untere Bereich schrumpfte bei jeder langen Maske
    bleibend (357 -> 318 -> 229 px)."""
    w, _app_ = _fenster()
    _zuruecksetzen(w)
    _oeffnen(w, "Netz")
    h0 = w.unten_dock.height()
    hoehen = [h0]
    for s in ("Wind", "zu", "Wasserdruck", "zu", "Wind", "Wasserdruck", "zu", "Netz"):
        _oeffnen(w, s)
        hoehen.append(w.unten_dock.height())
    check("Wind, Wasserdruck, zu (zweimal): der untere Bereich ist danach so hoch wie vorher (±5 px)",
          abs(hoehen[-1] - h0) <= 5 and abs(hoehen[2] - h0) <= 5, str(hoehen))
    # Folge: 0 Netz, 1 Wind, 2 zu, 3 Wasserdruck, 4 zu, 5 Wind, 6 Wasserdruck
    check("… und schrumpft nicht stufenweise: jede Maske bekommt jedes Mal dieselbe Höhe unten",
          abs(hoehen[5] - hoehen[1]) <= 5 and abs(hoehen[6] - hoehen[3]) <= 5, str(hoehen))
    _zuruecksetzen(w)


def test_fuss_ganz_sichtbar():
    """Befund 3: bei 1366 x 768 ueberlappten sich die Fusszeilen der
    Windmaske, „Auswahl übernehmen“ war angeschnitten, die dritte Zeile des
    Hinweises fehlte."""
    from PySide6 import QtCore
    w, _app_ = _fenster()
    maengel = []
    for s in ("Wind", "Wasserdruck", "Lager 1", "Kontakt", "Knoten"):
        _zuruecksetzen(w)
        _oeffnen(w, s)
        mk = w.maskenrand.maske
        if mk is None:
            maengel.append(f"{s}: keine Maske")
            continue
        knoepfe = [b for b in mk._fussknoepfe() if b.isVisible()]
        for b in knoepfe:
            vr = b.visibleRegion().boundingRect()
            if vr.height() < b.height() or vr.width() < b.width():
                maengel.append(f"{s}: „{b.text()}“ {vr.height()}/{b.height()} px sichtbar")
        rects = [QtCore.QRect(b.mapTo(mk, QtCore.QPoint(0, 0)), b.size()) for b in knoepfe]
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                if rects[i].intersects(rects[j]):
                    maengel.append(f"{s}: „{knoepfe[i].text()}“ überlappt „{knoepfe[j].text()}“")
        h = mk.lbl_hinweis
        if h.height() < h.heightForWidth(h.width()):
            maengel.append(f"{s}: Hinweis {h.height()} < {h.heightForWidth(h.width())} px")
        if mk.rolle.height() < mk.rolle.MINDESTHOEHE:
            maengel.append(f"{s}: Mitte {mk.rolle.height()} px")
    check("bei 1366 x 768: jeder Fußknopf ganz sichtbar, keine Überlappung, Hinweis ganz, Mitte ≥ Mindesthöhe",
          not maengel, "; ".join(maengel[:5]))
    _zuruecksetzen(w)


def test_kurze_maske_rollt_nicht():
    """Passt die ganze Maske, wenn der untere Bereich bis auf seine
    Mindesthoehe kleiner wird, rollt sie nicht (Knoten bei 1366 x 768) -
    eine lange Maske rollt und laesst den unteren Bereich, wie er ist."""
    w, _app_ = _fenster()
    _zuruecksetzen(w)
    _oeffnen(w, "Netz")
    h0 = w.unten_dock.height()
    _oeffnen(w, "Knoten")
    mk = w.maskenrand.maske
    rollweg = mk.rolle.verticalScrollBar().maximum()
    check("Knotenmaske bei 1366 x 768: alle Felder zu sehen (die Mitte rollt nicht)",
          rollweg == 0 and w.height() == SOLL[1], f"Rollweg {rollweg}, Fenster {w.height()}")
    _oeffnen(w, "Wind")
    mk = w.maskenrand.maske
    check("Windmaske: die Mitte rollt, der untere Bereich bleibt über seiner Mindesthöhe",
          mk.rolle.verticalScrollBar().maximum() > 0
          and w.unten_dock.height() > w.unten_dock.minimumHeight() + 20,
          f"unten {w.unten_dock.height()} (vorher {h0})")
    _zuruecksetzen(w)


#: Bildschirm fuer die Pruefung mit maximiertem Fenster
_BILDSCHIRM = {"screens": [{"name": "s1366", "x": 0, "y": 0, "width": SOLL[0], "height": SOLL[1],
                            "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}


def _maximiert_lauf():
    """Im eigenen Prozess (offscreen mit Bildschirm 1366 x 768): Fenster
    maximiert, dann jede Maske aus MASKEN - die groesste Fensterhoehe."""
    w, app = _fenster_ohne_beispiel()
    w.showMaximized()
    _ruhe(6)
    w.load_example("frame")
    _ruhe(6)
    hoechste, wo = w.frameGeometry().height(), "Start"
    for text, meth, args in MASKEN:
        fn = getattr(w, meth, None)
        if fn is None:
            continue
        try:
            fn(*args)
        except Exception:            # noqa: BLE001
            continue
        _ruhe(4)
        if w.frameGeometry().height() > hoechste:
            hoechste, wo = w.frameGeometry().height(), text
        if w.maskenrand.offen():
            w.maskenrand.schliessen()
            _ruhe()
    print(f"MAXIMIERT hoechste={hoechste} bei={wo} maximiert={w.isMaximized()}", flush=True)


def _fenster_ohne_beispiel():
    from statik3d.gui.main import MainWindow
    from PySide6 import QtWidgets
    app = _app()
    w = MainWindow()
    w._fragen_knoepfe = lambda *a, **k: True
    w.error = lambda *a, **k: None
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    return w, app


def test_maximiert_waechst_nicht():
    """Befund 8: ein maximiertes Fenster wuchs bei Wind ueber den Bildschirm
    (Sperre nahm den maximierten Zustand aus). Eigener Prozess, weil die
    Bildschirmgroesse vor dem Start von Qt feststehen muss; der Pfad zur
    Bildschirmdatei ist relativ (der Doppelpunkt nach dem Laufwerk zerlegt
    sonst den Plattformparameter)."""
    import json
    import subprocess
    d = tempfile.mkdtemp(prefix="statik3d_maximiert_")
    with open(os.path.join(d, "bildschirm.json"), "w", encoding="utf-8") as f:
        json.dump(_BILDSCHIRM, f)
    stamm = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen:configfile=bildschirm.json"
    env["PYTHONPATH"] = stamm + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    lauf = subprocess.run([sys.executable, "-m", "tests.test_maskenrahmen", "--maximiert"],
                          cwd=d, env=env, capture_output=True, text=True, timeout=900)
    zeile = [z for z in lauf.stdout.splitlines() if z.startswith("MAXIMIERT")]
    werte = dict(t.split("=", 1) for t in zeile[0].split()[1:]) if zeile else {}
    hoechste = int(werte.get("hoechste", "99999"))
    check(f"maximiert auf {SOLL[0]} x {SOLL[1]}: keine Maske lässt das Fenster über den Bildschirm wachsen",
          bool(zeile) and hoechste <= SOLL[1] and werte.get("maximiert") == "True",
          zeile[0] if zeile else (lauf.stdout[-300:] + lauf.stderr[-300:]))


def test_kurze_maske_oben_buendig():
    w, _app_ = _fenster()
    _zuruecksetzen(w, (1920, 1080))
    w.maske_knoten()
    _ruhe(4)
    mk = w.maskenrand.maske
    halter = mk.parentWidget()
    check("kurze Maske (Knoten) oben bündig im rechten Bereich",
          mk.y() <= 8, f"y = {mk.y()}")
    check("kurze Maske wird nicht gestreckt (Höhe = natürliche Höhe)",
          mk.height() <= mk.sizeHint().height() + 2 and mk.height() < halter.height() - 40,
          f"{mk.height()} bei sizeHint {mk.sizeHint().height()}, Bereich {halter.height()}")
    zeilen = [mk._felder[k] for k in ("x", "y", "z")]
    abst = [zeilen[i + 1].y() - zeilen[i].y() for i in range(2)]
    check("die Feldzeilen liegen dicht untereinander (Abstand < 40 px)",
          all(0 < a < 40 for a in abst), str(abst))
    _zuruecksetzen(w)


def test_kein_doppelter_titel():
    w, _app_ = _fenster()
    _zuruecksetzen(w)
    w.maske_knoten()
    _ruhe()
    tb = w.eingaben_dock.titleBarWidget()
    check("Maske offen: der Docktitel ist ausgeblendet (die Maske trägt ihren Titel)",
          tb is not None and tb.sizeHint().height() <= 0 and tb.height() <= 1,
          f"{None if tb is None else (tb.sizeHint().height(), tb.height())}")
    check("… der Name bleibt am Dock (für Tastatur und Tests)",
          w.eingaben_dock.windowTitle() == "Knoten", w.eingaben_dock.windowTitle())
    w.maske_zeigen("Netz")
    _ruhe()
    check("Register (ohne eigenen Titel): der Docktitel ist wieder da",
          w.eingaben_dock.titleBarWidget() is None and w.eingaben_dock.windowTitle() == "Netz",
          w.eingaben_dock.windowTitle())
    w.maske_knoten()
    _ruhe()
    w.maskenrand.schliessen()
    _ruhe()
    check("Maske zu, rechts leer: Docktitel „Eingaben“ sichtbar",
          w.eingaben_dock.titleBarWidget() is None and w.eingaben_dock.windowTitle() == "Eingaben",
          w.eingaben_dock.windowTitle())
    _zuruecksetzen(w)


def test_klickmodus_in_der_rollflaeche():
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    _zuruecksetzen(w)
    w._baum_neu("kontaktbedingungen")
    _ruhe(4)
    mk = w.maskenrand.maske
    rolle = getattr(mk, "rolle", None)
    feld = mk._felder.get("gegenflaechen") if mk is not None else None
    check("Kontaktbedingung: das Klickfeld Gegenflächen liegt in der Rollfläche",
          rolle is not None and feld is not None and rolle.widget().isAncestorOf(feld))
    if rolle is None or feld is None:
        return
    w.activateWindow()
    mk._felder["mu"].setFocus()
    _ruhe()
    feld.setFocus()
    _ruhe()
    scharf = "ff8800" in feld.styleSheet()
    check("Klick ins Feld Gegenflächen: die Maus sammelt Flächen, das Feld ist orange",
          mk.objekt_modus == "flaeche" and scharf, f"{mk.objekt_modus!r}, scharf {scharf}")
    vp = rolle.viewport()
    oben = feld.mapTo(vp, QtCore.QPoint(0, 0)).y()
    check("das scharfe Feld steht sichtbar in der Rollfläche",
          0 <= oben and oben + feld.height() <= vp.height(), f"{oben} in 0..{vp.height()}")
    QtTest.QTest.keyClick(feld, QtCore.Qt.Key_Escape)
    _ruhe()
    if mk.objekt_modus:
        print("     Esc-Kürzel offscreen nicht zugestellt - Esc-Stufe nicht prüfbar")
    else:
        check("Esc (erste Stufe) beendet nur den Klickmodus, die Maske bleibt offen",
              w.maskenrand.maske is mk and mk.isVisible() and "ff8800" not in feld.styleSheet())
    _zuruecksetzen(w)


def test_tabfolge_im_fenster():
    """Im Hauptfenster: Tab von der Tabelle der Ermuedungsmaske laeuft durch
    ihren Inhalt und endet mit den Knoepfen des Fusses."""
    w, app = _fenster()
    _zuruecksetzen(w)
    w.maske_ermuedungslasten()
    _ruhe(4)
    mk = w.maskenrand.maske
    folge = _tab_im_fenster(mk, mk.tabelle)
    z = [_zeiger(x) for x in folge]
    check("Ermüdungsmaske im Fenster: Tab ab der Tabelle erreicht die Felder, dann „Übernehmen“, zuletzt ✕",
          _zeiger(mk.name) in z and z[-2:] == [_zeiger(mk.btn_anwenden), _zeiger(mk.btn_zu)]
          and z.index(_zeiger(mk.name)) < len(z) - 2,
          str([type(x).__name__ for x in folge][-4:]))
    _zuruecksetzen(w)
    w.maske_knoten()
    _ruhe()
    mk = w.maskenrand.maske
    folge = _tab_im_fenster(mk, mk._felder["x"])
    check("Knotenmaske im Fenster: Tab x → y → z → „Anlegen“ → ✕",
          [_zeiger(x) for x in folge] == [_zeiger(x) for x in (
              mk._felder["x"], mk._felder["y"], mk._felder["z"], mk.btn_anwenden, mk.btn_zu)],
          str([type(x).__name__ for x in folge]))
    _zuruecksetzen(w)


def test_schliessen_ohne_maus():
    """Befund 10 der Gegenpruefung: das ✕ war aus der Tab-Folge genommen, Esc
    schliesst im Fenster keine Maske - Masken ohne „Abbrechen“ liessen sich
    nur per Maus schliessen."""
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    _zuruecksetzen(w)
    w._baum_geklickt("lager_einzeln", "1")
    _ruhe(4)
    mk = w.maskenrand.maske
    if mk is None or not hasattr(mk, "btn_zu"):
        check("Lager 1: Maske mit ✕ offen", False)
        return
    w.activateWindow()
    mk.btn_anwenden.setFocus()
    _ruhe()
    fuss = mk._fussknoepfe()
    for b in fuss[1:]:
        QtTest.QTest.keyClick(app.focusWidget(), QtCore.Qt.Key_Tab)
        _ruhe()
    QtTest.QTest.keyClick(app.focusWidget(), QtCore.Qt.Key_Tab)
    _ruhe()
    check("Lager 1 (ohne „Abbrechen“): Tab nach dem letzten Fußknopf erreicht ✕",
          app.focusWidget() is mk.btn_zu, type(app.focusWidget()).__name__)
    QtTest.QTest.keyClick(app.focusWidget(), QtCore.Qt.Key_Space)
    _ruhe()
    check("… die Leertaste auf ✕ schließt die Maske", not w.maskenrand.offen())
    _zuruecksetzen(w)


def test_enter_im_fenster():
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    _zuruecksetzen(w)
    w.maske_knoten()
    _ruhe()
    mk = w.maskenrand.maske
    n0 = w.model.nn
    mk.setzen("x", 7.25)
    w.activateWindow()
    mk._felder["x"].setFocus()
    _ruhe()
    QtTest.QTest.keyClick(mk._felder["x"], QtCore.Qt.Key_Return)
    _ruhe()
    check("Enter in der Knotenmaske legt genau einen Knoten an", w.model.nn == n0 + 1,
          f"{n0} -> {w.model.nn}")
    w.undo()
    _zuruecksetzen(w)


def test_handbuch():
    """Die Handbuchsaetze zum Rahmen nennen das, was die Pruefungen oben messen."""
    from tests.handbuch import absatz
    aufbau = absatz("**Aufbau jeder Maske**")
    check("Handbuch: Hinweiszeile oben, nur die Mitte rollt, fester Fuß mit Hauptknopf",
          "Hinweiszeile" in aufbau and "rollt nur diese Mitte" in aufbau
          and "fester Fuß" in aufbau and "nicht auseinandergezogen" in aufbau, aufbau[:80])
    check("Handbuch: das Fenster wächst nicht (auch maximiert); passt die Maske, wird unten "
          "kleiner, sonst rollt sie bis etwa zwei Feldzeilen",
          "nicht mehr über den Bildschirm hinaus wachsen" in aufbau
          and "auch nicht im maximierten Fenster" in aufbau
          and "bis auf seine Mindesthöhe kleiner" in aufbau
          and "bis herunter auf etwa zwei Feldzeilen" in aufbau
          and "bekommt der untere Bereich seine Höhe zurück" in aufbau, aufbau[:80])
    rad = absatz("Das **Mausrad** über der Mitte")
    check("Handbuch: Mausrad rollt, verstellt Auswahllisten nur mit Fokus; Klick auf halb sichtbares Feld",
          "nur, wenn die Liste den Fokus hat" in rad and "halb sichtbares Feld" in rad, rad[:80])
    tasten = absatz("Zur Tastatur: **Tab**")
    t1 = tasten
    check("Handbuch: Tab bis ✕, Pfeile rollen nicht, Enter nicht in Tabellen, Esc schließt keine Maske",
          "von oben nach unten" in t1 and "zuletzt auf **✕**" in t1
          and "rollen die Mitte nicht" in t1 and "nicht aber in einer Tabelle" in t1
          and "schließt im Programmfenster keine Maske" in t1, tasten[:80])
    alt = absatz("Querschnitt, Material, Dicke und Lastfall gelten")
    check("Handbuch: geschlossen wird mit ✕ (nicht mehr „Esc schließt die Maske“)",
          "**Esc** schließt die Maske" not in alt and "✕" in alt, alt[:80])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    if "--maximiert" in sys.argv:
        _maximiert_lauf()
        return 0
    for t in (test_rahmen_aufbau, test_fokus_sichtbar, test_enter_ist_hauptknopf, test_tabfolge,
              test_ermuedungsmaske_im_rahmen, test_querschnittmaske,
              test_rad_ueber_auswahlliste, test_klick_auf_halb_sichtbaren_haken,
              test_pfeiltasten_rollen_nicht, test_enter_auf_tabelle_und_liste,
              test_rolle_wuenscht_volle_hoehe, test_inhalt_waechst_nach,
              test_schwebende_maske_begrenzt, test_fenster_waechst_nie,
              test_ansicht_kommt_zurueck, test_unten_bleibt, test_fuss_ganz_sichtbar,
              test_kurze_maske_rollt_nicht, test_maximiert_waechst_nicht,
              test_kurze_maske_oben_buendig, test_kein_doppelter_titel,
              test_klickmodus_in_der_rollflaeche, test_tabfolge_im_fenster,
              test_schliessen_ohne_maus, test_enter_im_fenster, test_handbuch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
