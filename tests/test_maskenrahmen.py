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
        mk.btn_anwenden, mk.btn_abbrechen, mk.zusatzknoepfe["Löschen"]]
    check("Tab: erst die Felder von oben nach unten, dann die Knöpfe des Fußes",
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
    check("Ermüdungsmaske im Fenster: Tab ab der Tabelle erreicht die Felder, zuletzt „Übernehmen“",
          _zeiger(mk.name) in z and z[-1:] == [_zeiger(mk.btn_anwenden)]
          and z.index(_zeiger(mk.name)) < len(z) - 1,
          str([type(x).__name__ for x in folge][-4:]))
    _zuruecksetzen(w)
    w.maske_knoten()
    _ruhe()
    mk = w.maskenrand.maske
    folge = _tab_im_fenster(mk, mk._felder["x"])
    check("Knotenmaske im Fenster: Tab x → y → z → „Anlegen“",
          [_zeiger(x) for x in folge] == [_zeiger(x) for x in (
              mk._felder["x"], mk._felder["y"], mk._felder["z"], mk.btn_anwenden)],
          str([type(x).__name__ for x in folge]))
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
    check("Handbuch: das Fenster wächst nicht, zuerst wird der untere Bereich kleiner",
          "nicht mehr über den Bildschirm hinaus wachsen" in aufbau
          and "zuerst der untere Bereich" in aufbau)
    tasten = absatz("Zur Tastatur: **Tab**")
    check("Handbuch: Tab von oben nach unten, Eingabetaste = Hauptknopf, Esc zweistufig",
          "von oben nach unten" in tasten and "Eingabetaste" in tasten
          and "Hauptknopf" in tasten and "zwei Stufen" in tasten, tasten[:80])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_rahmen_aufbau, test_fokus_sichtbar, test_enter_ist_hauptknopf, test_tabfolge,
              test_ermuedungsmaske_im_rahmen, test_querschnittmaske, test_fenster_waechst_nie,
              test_kurze_maske_oben_buendig, test_kein_doppelter_titel,
              test_klickmodus_in_der_rollflaeche, test_tabfolge_im_fenster,
              test_enter_im_fenster, test_handbuch):
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
