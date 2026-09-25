"""
Fensteraufteilung: mehr Platz fuer die Ansicht (Paket 5 des Oberflaechenplans, 25.09.2026).

Befund (offscreen am Stand 562dc3a gemessen, maximiert): die Ansicht bekam bei
1920 x 1080 1142 x 470 px (26 % der Fensterflaeche), bei 1366 x 768 588 x 158
px (9 %), bei 1280 x 720 (150 % Skalierung) 502 x 124 px (7 %). Die Docks
hatten feste Masse (Baum 290, rechts 472, unten 357 px), der untere Bereich
lief unter Baum und rechtem Bereich durch, Kopfzeile und Ribbon nahmen 218 px,
die Windmaske zog den rechten Bereich auf 1170 px, und bei 1280 x 720 wuchs das
Fenster mit ihr ueber den Bildschirm (729 px).

Geprueft wird:

* ohne Fenster: Sollmasse, Pruefen eines gespeicherten Eintrags gegen die
  Bildschirme (Fassung, Lage, Dockmasse), einstellungen.json behaelt fremde
  Schluessel;
* im Hauptfenster (offscreen): eine dunkle Kopfzeile mit Schnellzugriff und
  Suche, Modellumfang in der Statusleiste, Ecken fuer Baum und rechten
  Bereich, keine Titelzeile unten, Startregister „Start“, Sollmasse und ihr
  Nachfuehren, Ribbon einklappen (Doppelklick, Strg+F1, vorlaeufig per Klick),
  Ansicht → Fenster (Zonen, Nur Ansicht, Anordnung zurücksetzen),
  Kompaktstufe, breite Masken rollen waagerecht, die Trennlinie des
  Anwenders gilt, Speichern mit Fassungskennung;
* in eigenen Prozessen mit festem Bildschirm (offscreen:configfile): die
  Abnahme des Plans bei 1920 x 1080, 1366 x 768, 125 % und 150 %
  (QT_SCALE_FACTOR und logische Aufloesung 1536 x 864 bzw. 1280 x 720) mit
  langen Masken; der Start aus einer gespeicherten Anordnung; und
  STATIK3D_FENSTER=fest haelt den alten Stand.

Zur Abnahme „Ansicht >= 45 % der Fensterflaeche bei 1920 x 1080“ (Plan 4a):
mit den Sollmassen der Antwort 9 (Baum 16 %, rechts 460 px, unten 25 %)
bleiben bei 1916 x 1076 hoechstens 1137 x 610 px = 34 %; 45 % der Flaeche
gingen nur mit einem unteren Bereich von rund 110 px. Geprueft wird darum das
Zielbild aus Kap. 2 (mindestens 50 % der Breite und 45 % der Hoehe) und
mindestens 30 % der Flaeche auf allen Bildschirmen.

Aufruf:  python -m tests.test_fensteraufteilung
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
#: Kindprozesse (eigener Bildschirm) bekommen Umgebung und Einstellungsdatei
#: vom Elternprozess - nur der Elternprozess setzt sie hier
KIND = any(a in sys.argv for a in ("--messen", "--fest", "--gespeichert"))
if not KIND:
    os.environ.pop("STATIK3D_FENSTER", None)
    _TMP = tempfile.mkdtemp(prefix="statik3d_fenster_")
    os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(_TMP, "einstellungen.json")

STAMM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _ruhe(n: int = 4):
    app = _app()
    for _ in range(n):
        app.processEvents()


# --------------------------------------------------------------------------
# Ohne Fenster
# --------------------------------------------------------------------------
def test_sollmasse_und_pruefen():
    from statik3d.gui import fenster as fen
    s = fen.soll(1920, 1080)
    check("Sollmasse bei 1920 x 1080: Baum 16 % (307 px), rechts 460 px, unten 25 % (270 px)",
          s == {"baum": 307, "rechts": 460, "unten": 270}, str(s))
    schirm = [(0, 0, 1920, 1040)]
    gut = {"fassung": fen.FASSUNG, "geometrie": [100, 80, 1400, 900], "maximiert": False,
           "bildschirm": [1920, 1040], "baum": 300, "rechts": 520, "unten": 250,
           "zonen": {"baum": True, "rechts": False, "unten": True}, "ribbon_eingeklappt": True}
    g = fen.pruefen(gut, schirm)
    check("gültiger Eintrag: Lage, Dockmaße, Zonen und Ribbon gelten",
          g is not None and g["geometrie"] == [100, 80, 1400, 900] and not g["maximiert"]
          and g["docks"] == {"baum": 300, "rechts": 520, "unten": 250}
          and g["zonen"]["rechts"] is False and g["ribbon"] is True, str(g))
    check("andere Fassung: der Eintrag gilt nicht",
          fen.pruefen(dict(gut, fassung=fen.FASSUNG + 1), schirm) is None)
    g = fen.pruefen(dict(gut, geometrie=[2500, 80, 1400, 900]), schirm)
    check("Fenster außerhalb aller Bildschirme (Bildschirm abgezogen): maximiert starten",
          g is not None and g["geometrie"] is None and g["maximiert"], str(g))
    g = fen.pruefen(dict(gut, geometrie=[0, 0, 1600, 1100]), schirm)
    check("Fenster höher als der Bildschirm: maximiert starten",
          g is not None and g["geometrie"] is None and g["maximiert"], str(g))
    g = fen.pruefen(gut, [(0, 0, 1366, 728)])
    check("gespeichert auf 1920er, jetzt 1366er Bildschirm: Sollmaße statt der gespeicherten",
          g is not None and g["docks"] is None and g["geometrie"] is None, str(g))
    g = fen.pruefen(dict(gut, rechts=1500), schirm)
    check("unsinnige Dockmaße (rechts 1500 px) gelten nicht", g is not None and g["docks"] is None, str(g))


def test_einstellungen_behalten_schluessel():
    from statik3d import parallel
    from statik3d.gui import fenster as fen
    p = os.environ["STATIK3D_EINSTELLUNGEN"]
    if os.path.exists(p):
        os.remove(p)
    fen.schreiben({"geometrie": [0, 0, 800, 600], "maximiert": True})
    parallel.einstellungen_speichern()
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    check("Löser-Einstellungen speichern lässt den Eintrag „fenster“ stehen",
          isinstance(d.get("fenster"), dict) and "solver_threads" in d, str(sorted(d)))
    fen.schreiben({"geometrie": [0, 0, 900, 700], "maximiert": False})
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    check("… und das Fenster speichern die Löser-Einstellungen, mit Fassungskennung",
          "solver_threads" in d and d["fenster"]["fassung"] == fen.FASSUNG
          and d["fenster"]["geometrie"] == [0, 0, 900, 700], str(d.get("fenster")))
    os.remove(p)


# --------------------------------------------------------------------------
# Im Hauptfenster (offscreen)
# --------------------------------------------------------------------------
_F = {}


def _fenster():
    if "w" in _F:
        return _F["w"]
    from statik3d.gui.main import MainWindow
    from PySide6 import QtWidgets
    _app()
    w = MainWindow()
    w._fragen_knoepfe = lambda *a, **k: True
    w.error = lambda *a, **k: None
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    _F["register_start"] = w.ribbon.tabs.tabText(w.ribbon.tabs.currentIndex())
    w.show()
    _ruhe()
    _F["w"] = w
    return w


def _groesse(w, b, h):
    w.resize(b, h)
    _ruhe(6)


def _ansicht(w):
    c = w.centralWidget()
    return c.width(), c.height()


def test_kopfzeile():
    w = _fenster()
    _groesse(w, 1920, 1080)
    rb = w.ribbon
    check("Schnellzugriff und Befehlssuche stehen in der dunklen Kopfzeile",
          w.kopf.isAncestorOf(rb.schnellzugriff) and w.kopf.isAncestorOf(rb.suche)
          and rb.schnellzugriff.isVisible() and rb.suche.isVisible())
    check("das Ribbon hat keine eigene Zeile mehr über den Registern",
          rb.height() - rb.tabs.height() <= 2, f"Ribbon {rb.height()}, Register {rb.tabs.height()}")
    kopf = w.menuWidget().height()
    check("Kopfzeile und Ribbon zusammen höchstens 170 px (vorher 218 px)", kopf <= 170, f"{kopf} px")
    check("Befehlssuche und Schnellzugriff: dieselben Objekte wie zuvor",
          rb.suche.objectName() == "befehlssuche" and rb.schnellzugriff.objectName() == "schnellzugriff"
          and len(rb.schnellzugriff.actions()) == 4)
    bild = w.kopf.grab().toImage()
    farbe = bild.pixelColor(max(1, rb.suche.x() - 20), bild.height() // 2)
    check("die Kopfzeile bleibt dunkel (neben der Suche)",
          farbe.red() < 90 and farbe.green() < 90 and farbe.blue() < 110,
          f"RGB {farbe.red()},{farbe.green()},{farbe.blue()}")
    from statik3d.bridges.positions import Stellung
    w._stellungen_obj()[:] = [Stellung(name="S1", winkel=0.0), Stellung(name="S2", winkel=30.0)]
    w.refresh_all()
    _ruhe()
    check("der Modellumfang steht nur in der Statusleiste (mit Stellungen), nicht mehr oben",
          not w.kopf.marke_modell.isVisible() and w.lbl_netz.text().startswith("Netz:")
          and "2 Stellungen" in w.lbl_netz.text(), w.lbl_netz.text())
    w._stellungen_obj()[:] = []
    w.refresh_all()


def test_startregister():
    w = _fenster()
    check("das Ribbon startet im Register „Start“", _F["register_start"] == "Start", _F["register_start"])
    del w


def test_ecken_und_titel():
    from PySide6 import QtCore
    w = _fenster()
    _groesse(w, 1920, 1080)
    w.anordnung.zuruecksetzen()
    _ruhe(6)
    Q = QtCore.Qt
    check("Ecken: links gehören dem Baum, rechts dem rechten Bereich",
          w.corner(Q.TopLeftCorner) == Q.LeftDockWidgetArea and w.corner(Q.BottomLeftCorner) == Q.LeftDockWidgetArea
          and w.corner(Q.TopRightCorner) == Q.RightDockWidgetArea
          and w.corner(Q.BottomRightCorner) == Q.RightDockWidgetArea)
    b, r, u = w.baum_dock.geometry(), w.eingaben_dock.geometry(), w.unten_dock.geometry()
    check("Baum und rechter Bereich reichen über die volle Höhe (bis unter den unteren Bereich)",
          b.bottom() >= u.bottom() - 1 and r.bottom() >= u.bottom() - 1 and b.top() == r.top(),
          f"Baum {b.top()}..{b.bottom()}, rechts {r.top()}..{r.bottom()}, unten {u.top()}..{u.bottom()}")
    check("der untere Bereich steht nur unter der Ansicht",
          u.left() > b.right() and u.right() < r.left() and u.width() == w.centralWidget().width(),
          f"unten {u.left()}..{u.right()}, Ansicht {w.centralWidget().width()} px")
    tb = w.unten_dock.titleBarWidget()
    check("keine Titelzeile „Protokoll und Tabellen“ mehr; der Name bleibt am Dock",
          tb is not None and tb.height() <= 1 and w.unten_dock.windowTitle() == "Protokoll und Tabellen",
          f"{None if tb is None else tb.height()}")


def test_sollmasse_im_fenster():
    w = _fenster()
    _groesse(w, 1920, 1080)
    w.anordnung.zuruecksetzen()
    _ruhe(6)
    bb, rr, uu = w.baum_dock.width(), w.eingaben_dock.width(), w.unten_dock.height()
    check("1920 x 1080: Baum 16 % der Breite, rechts 460 px, unten 25 % der Höhe (je ±6 px)",
          abs(bb - 307) <= 6 and abs(rr - 460) <= 6 and abs(uu - 270) <= 6, f"{bb} / {rr} / {uu}")
    _groesse(w, 1700, 1000)
    bb, rr, uu = w.baum_dock.width(), w.eingaben_dock.width(), w.unten_dock.height()
    check("das Fenster wird kleiner (1700 x 1000): die Maße folgen anteilig (272 / 460 / 250 px)",
          abs(bb - 272) <= 6 and abs(rr - 460) <= 6 and abs(uu - 250) <= 6, f"{bb} / {rr} / {uu}")
    _groesse(w, 1920, 1080)


def test_ribbon_einklappen():
    from PySide6 import QtGui
    w = _fenster()
    _groesse(w, 1920, 1080)
    rb = w.ribbon
    rb.einklappen(False)
    _ruhe()
    h0, a0 = w.menuWidget().height(), _ansicht(w)[1]
    rb.tabs.tabBarDoubleClicked.emit(rb.tabs.currentIndex())
    _ruhe(6)
    h1, a1 = w.menuWidget().height(), _ansicht(w)[1]
    check("Doppelklick auf einen Reiter klappt das Ribbon ein: mindestens 80 px mehr für die Ansicht",
          rb.eingeklappt() and h0 - h1 >= 80 and a1 - a0 >= 80, f"Kopf {h0} -> {h1}, Ansicht {a0} -> {a1}")
    check("… Schalter „Ribbon einklappen“ zieht mit", w.anordnung.act_ribbon.isChecked())
    i = rb.tabs.indexOf(rb._register["Geometrie"])
    rb.tabs.setCurrentIndex(i)
    rb.tabs.tabBarClicked.emit(i)
    _ruhe()
    offen = rb.vorlaeufig_offen() and w.menuWidget().height() >= h0 - 2
    befehl = next(b for b in rb.befehle if b.register == "Geometrie" and b.text == "Knoten")
    befehl.aktion.trigger()
    _ruhe(4)
    check("eingeklappt: ein Klick auf einen Reiter öffnet das Register, bis ein Befehl daraus lief",
          offen and not rb.vorlaeufig_offen() and rb.eingeklappt()
          and w.menuWidget().height() <= h1 + 2, f"offen {offen}, danach {w.menuWidget().height()}")
    if w.maskenrand.offen():
        w.maskenrand.schliessen()
    a = w.anordnung.act_ribbon
    check("Strg+F1 gehört dem Schalter „Ribbon einklappen“",
          a.shortcut() == QtGui.QKeySequence("Ctrl+F1") and a in w.actions(), a.shortcut().toString())
    a.trigger()
    _ruhe(4)
    check("Strg+F1 (der Befehl) klappt wieder aus", not rb.eingeklappt()
          and abs(w.menuWidget().height() - h0) <= 2, f"{w.menuWidget().height()}")
    rb.tabs.setCurrentIndex(rb.tabs.indexOf(rb._register["Start"]))


def test_fenstermenue():
    w = _fenster()
    _groesse(w, 1920, 1080)
    an = w.anordnung
    an.zuruecksetzen()
    _ruhe(6)
    namen = {b.text for b in w.ribbon.befehle if b.register == "Ansicht" and b.gruppe == "Fenster"}
    soll = {"Modellbaum zeigen", "Rechten Bereich zeigen", "Unteren Bereich zeigen", "Ribbon einklappen",
            "Nur Ansicht", "Anordnung zurücksetzen"}
    check("Ansicht → Fenster: Schalter je Zone, Ribbon einklappen, Nur Ansicht, Anordnung zurücksetzen",
          soll <= namen, str(sorted(namen)))
    b0 = _ansicht(w)[0]
    an.act_zone["baum"].trigger()
    _ruhe(6)
    check("Schalter Modellbaum: der Baum geht aus, die Ansicht wird breiter",
          w.baum_dock.isHidden() and _ansicht(w)[0] > b0 + 250, f"{b0} -> {_ansicht(w)[0]}")
    an.act_zone["baum"].trigger()
    _ruhe(6)
    check("… und wieder an", not w.baum_dock.isHidden() and abs(_ansicht(w)[0] - b0) <= 8,
          f"{_ansicht(w)[0]}")
    w.unten_dock.hide()
    _ruhe()
    check("wird ein Bereich anders ausgeblendet, zieht der Schalter mit",
          not an.act_zone["unten"].isChecked())
    w.unten_dock.show()
    _ruhe(6)
    an.act_nur_ansicht.trigger()
    _ruhe(6)
    bb, hh = _ansicht(w)
    check("Nur Ansicht: Baum, rechts und unten aus, Ribbon eingeklappt, die Ansicht nimmt fast alles",
          all(d.isHidden() for d in (w.baum_dock, w.eingaben_dock, w.unten_dock)) and w.ribbon.eingeklappt()
          and bb >= w.width() - 4 and hh >= w.height() - 130, f"Ansicht {bb} x {hh} im Fenster {w.width()} x {w.height()}")
    an.act_nur_ansicht.trigger()
    _ruhe(6)
    check("Nur Ansicht noch einmal: alles wie vorher",
          not any(d.isHidden() for d in (w.baum_dock, w.eingaben_dock, w.unten_dock))
          and not w.ribbon.eingeklappt() and abs(_ansicht(w)[0] - b0) <= 8, f"{_ansicht(w)}")
    from PySide6 import QtCore
    w.baum_dock.hide()
    w.ribbon.einklappen(True)
    w.resizeDocks([w.eingaben_dock], [700], QtCore.Qt.Horizontal)
    _ruhe()
    an.act_zuruecksetzen.trigger()
    _ruhe(6)
    check("Anordnung zurücksetzen: alle Bereiche da, Ribbon offen, Sollmaße",
          not w.baum_dock.isHidden() and not w.ribbon.eingeklappt()
          and abs(w.eingaben_dock.width() - 460) <= 6 and abs(w.baum_dock.width() - 307) <= 6,
          f"Baum {w.baum_dock.width()}, rechts {w.eingaben_dock.width()}")


def test_kompaktstufe():
    w = _fenster()
    an = w.anordnung
    _groesse(w, 1920, 1080)
    an.zuruecksetzen()
    _ruhe(6)
    breite_wuerfel = w.ansichtswuerfel.width()
    check("1920 x 1080: keine Kompaktstufe", not an.kompakt and w._farbskala().get("vertical") is True)
    _groesse(w, 1366, 768)
    kopf = w.menuWidget().height()
    check("1366 x 768 (unter 900 px Höhe): Kompaktstufe, Ribbon eingeklappt",
          an.kompakt and w.ribbon.eingeklappt() and kopf <= 80, f"Kopf {kopf} px")
    check("… unten nur die Registerzeile (höchstens 40 px)",
          w.unten_dock.height() <= 40 and an.unten_eingeklappt(), f"{w.unten_dock.height()} px")
    check("… der Ansichtswürfel ist kleiner, die Farbskala waagerecht",
          w.ansichtswuerfel.width() < breite_wuerfel and w._farbskala().get("vertical") is False,
          f"Würfel {breite_wuerfel} -> {w.ansichtswuerfel.width()} px")
    bb, hh = _ansicht(w)
    check("… die Ansicht hat mindestens 30 % der Fensterfläche",
          bb * hh >= 0.30 * w.width() * w.height(), f"{bb} x {hh} = {100 * bb * hh / (w.width() * w.height()):.1f} %")
    w.tab_unten.leiste.tabBarClicked.emit(1)
    _ruhe(6)
    check("ein Klick auf eine Gruppe unten klappt den Bereich auf",
          not an.unten_eingeklappt() and w.unten_dock.height() >= 150, f"{w.unten_dock.height()} px")
    w.tab_unten.leiste.tabBarDoubleClicked.emit(1)
    _ruhe(6)
    check("… ein Doppelklick auf die Leiste wieder zu", an.unten_eingeklappt() and w.unten_dock.height() <= 40,
          f"{w.unten_dock.height()} px")
    _groesse(w, 1920, 1080)
    check("zurück auf 1920 x 1080: Ribbon offen, unten wieder da, Würfel und Farbskala wie vorher",
          not an.kompakt and not w.ribbon.eingeklappt() and not an.unten_eingeklappt()
          and abs(w.unten_dock.height() - 270) <= 6 and w.ansichtswuerfel.width() == breite_wuerfel
          and w._farbskala().get("vertical") is True, f"unten {w.unten_dock.height()} px")
    _groesse(w, 1200, 1000)
    check("schmales Fenster (1200 x 1000): die Ansicht bliebe unter 700 px breit - Kompaktstufe",
          an.kompakt, f"Ansicht {_ansicht(w)}")
    _groesse(w, 1920, 1080)


def test_breite_maske_rollt():
    from PySide6 import QtCore
    w = _fenster()
    _groesse(w, 1920, 1080)
    w.anordnung.zuruecksetzen()
    _ruhe(6)
    b0 = _ansicht(w)[0]
    w.maske_wind()
    _ruhe(8)
    mk = w.maskenrand.maske
    rechts = w.eingaben_dock.width()
    rolle = mk.rolle
    knopf = mk.btn_anwenden
    unten = knopf.mapTo(w, QtCore.QPoint(0, knopf.height())).y()
    check("Windmaske: der rechte Bereich bleibt bei etwa 460 px (vorher 1170 px), die Ansicht behält ihre Breite",
          rechts <= 480 and _ansicht(w)[0] >= b0 - 20, f"rechts {rechts}, Ansicht {b0} -> {_ansicht(w)[0]}")
    hb = rolle.horizontalScrollBar()
    check("… ihre breiten Zeilen rollen waagerecht (Rollbalken sichtbar)",
          hb.maximum() > 0 and hb.isVisible(), f"Rollweg {hb.maximum()} px, Balken sichtbar {hb.isVisible()}")
    check("… „Übernehmen“ bleibt im Fenster sichtbar", unten <= w.height() and not knopf.visibleRegion().isEmpty(),
          f"Unterkante {unten} von {w.height()}")
    w.maskenrand.schliessen()
    _ruhe()


def test_trennlinie_des_anwenders():
    from PySide6 import QtCore, QtTest
    w = _fenster()
    _groesse(w, 1920, 1080)
    an = w.anordnung
    an.zuruecksetzen()
    _ruhe(6)
    b = w.baum_dock.geometry()
    punkt = QtCore.QPoint(b.right() + 2, b.center().y())
    frei = w.childAt(punkt) is None
    QtTest.QTest.mousePress(w, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, punkt)
    QtTest.QTest.mouseRelease(w, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, punkt)
    _ruhe()
    check("ein Druck auf die Trennlinie: ab jetzt gelten die Maße des Anwenders",
          frei and not an.automatisch, f"Trennlinie frei {frei}")
    w.resizeDocks([w.eingaben_dock], [540], QtCore.Qt.Horizontal)
    _ruhe()
    _groesse(w, 1800, 1050)
    check("… eine neue Fenstergröße setzt sie nicht auf die Sollmaße zurück",
          abs(w.eingaben_dock.width() - 540) <= 8, f"rechts {w.eingaben_dock.width()} px")
    p = an.speichern()
    with open(p, encoding="utf-8") as f:
        e = json.load(f)["fenster"]
    check("beim Beenden gemerkt: Fassung, Größe, Aufteilung, Zonen, Ribbon",
          e["fassung"] == 1 and e["geometrie"][2:] == [1800, 1050] and abs(e["rechts"] - 540) <= 8
          and e["zonen"] == {"baum": True, "rechts": True, "unten": True}
          and e["ribbon_eingeklappt"] is False, str(e))
    an.zuruecksetzen()
    _ruhe(6)
    check("Anordnung zurücksetzen: die Maße folgen wieder der Fenstergröße",
          an.automatisch and abs(w.eingaben_dock.width() - 460) <= 6, f"{w.eingaben_dock.width()}")
    p = an.speichern()
    with open(p, encoding="utf-8") as f:
        e = json.load(f)["fenster"]
    check("… und gespeichert werden dann keine festen Dockmaße", e["rechts"] is None and e["baum"] is None, str(e))
    _groesse(w, 1920, 1080)


# --------------------------------------------------------------------------
# Eigene Prozesse mit festem Bildschirm
# --------------------------------------------------------------------------
#: Masken, die vorher das Fenster wachsen liessen oder breite Zeilen haben
LANGE_MASKEN = [
    ("Wind", "maske_wind", ()),
    ("Wasserdruck", "maske_wasserdruck", ()),
    ("Neu: Kontaktbedingung", "_baum_neu", ("kontaktbedingungen",)),
    ("Lager 1", "_baum_geklickt", ("lager_einzeln", "1")),
    ("Neuer Querschnitt", "_baum_neu", ("querschnitte",)),
    ("Ermüdungslasten", "maske_ermuedungslasten", ()),
    ("Netzeinstellungen", "maske_netzeinstellungen", ()),
]


def _kind_messen():
    """Im eigenen Prozess: starten wie main(), messen, lange Masken oeffnen."""
    from PySide6 import QtCore, QtWidgets
    from statik3d.gui import main as gm
    app = _app()
    w = gm.MainWindow()
    w._fragen_knoepfe = lambda *a, **k: True
    w.error = lambda *a, **k: None
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    gm.fenster_starten(w)
    _ruhe(12)
    scr = w.screen().availableGeometry()

    def mass():
        c = w.centralWidget()
        return {"fenster": [w.width(), w.height()], "rahmen_h": w.frameGeometry().height(),
                "ansicht": [c.width(), c.height()], "maximiert": w.isMaximized(),
                "kompakt": w.anordnung.kompakt, "rechts": w.eingaben_dock.width()}
    erg = {"schirm": [scr.width(), scr.height()], "start": mass(), "masken": []}
    w.load_example("frame")
    _ruhe(6)
    for text, meth, args in LANGE_MASKEN:
        try:
            getattr(w, meth)(*args)
        except Exception as ex:        # noqa: BLE001
            erg["masken"].append({"text": text, "fehler": str(ex)[:80]})
            continue
        _ruhe(6)
        mk = w.maskenrand.maske if w.maskenrand.offen() else None
        if mk is None:
            erg["masken"].append({"text": text, "fehler": "keine Maske"})
            continue
        # die Querschnittmaske hat ihren eigenen Rahmen: Hauptknopf „Anlegen“
        k = getattr(mk, "btn_anwenden", None) or getattr(mk, "btn_norm", None)
        unten = k.mapTo(w, QtCore.QPoint(0, k.height())).y()
        erg["masken"].append(dict(mass(), text=text, knopf=bool(unten <= w.height() and not k.visibleRegion().isEmpty())))
        w.maskenrand.schliessen()
        _ruhe()
    print("MESSUNG " + json.dumps(erg), flush=True)


def _bildschirm_lauf(breite, hoehe, skala=1.0, env_extra=None, arg="--messen", einstellungen=None):
    d = tempfile.mkdtemp(prefix="statik3d_fenster_schirm_")
    with open(os.path.join(d, "bildschirm.json"), "w", encoding="utf-8") as f:
        json.dump({"screens": [{"name": "s", "x": 0, "y": 0, "width": int(breite), "height": int(hoehe),
                                "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}, f)
    env = dict(os.environ)
    # der Pfad ist relativ: der Doppelpunkt nach dem Laufwerk zerlegte sonst
    # den Plattformparameter (wie tests/test_maskenrahmen.py)
    env["QT_QPA_PLATFORM"] = "offscreen:configfile=bildschirm.json"
    env.pop("QT_SCALE_FACTOR", None)
    if float(skala) != 1.0:
        env["QT_SCALE_FACTOR"] = str(skala)
    env["PYTHONPATH"] = STAMM + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    env["STATIK3D_EINSTELLUNGEN"] = os.path.join(d, "einstellungen.json")
    if einstellungen is not None:
        with open(env["STATIK3D_EINSTELLUNGEN"], "w", encoding="utf-8") as f:
            json.dump(einstellungen, f)
    env.pop("STATIK3D_FENSTER", None)
    env.update(env_extra or {})
    lauf = subprocess.run([sys.executable, "-m", "tests.test_fensteraufteilung", arg], cwd=d, env=env,
                          capture_output=True, text=True, timeout=900)
    z = [x for x in lauf.stdout.splitlines() if x.startswith("MESSUNG ")]
    if not z:
        print(lauf.stdout[-1500:], lauf.stderr[-2500:])
        return None
    return json.loads(z[0][8:])


#: (Beschreibung, physische Breite, Hoehe, Skalierung)
BILDSCHIRME = [
    ("1920 x 1080", 1920, 1080, 1.0),
    ("1366 x 768", 1366, 768, 1.0),
    ("1920 x 1080 bei 125 % (QT_SCALE_FACTOR)", 1920, 1080, 1.25),
    ("1920 x 1080 bei 150 % (QT_SCALE_FACTOR)", 1920, 1080, 1.5),
    ("logisch 1536 x 864 (125 %)", 1536, 864, 1.0),
    ("logisch 1280 x 720 (150 %)", 1280, 720, 1.0),
]


def test_abnahme_bildschirme():
    """Plan 4a: Ansicht, Fensterhoehe, „Übernehmen“ - je Bildschirm."""
    for text, b, h, s in BILDSCHIRME:
        print(f"     … {text}", flush=True)
        e = _bildschirm_lauf(b, h, s)
        if e is None:
            check(f"{text}: Messlauf", False)
            continue
        st, sb, sh = e["start"], e["schirm"][0], e["schirm"][1]
        fb, fh = st["fenster"]
        ab, ah = st["ansicht"]
        anteil = ab * ah / (fb * fh)
        detail = (f"Schirm {sb}x{sh}, Fenster {fb}x{fh}, Ansicht {ab}x{ah} = {100 * anteil:.1f} % "
                  f"(B {100 * ab / fb:.0f} %, H {100 * ah / fh:.0f} %), kompakt {st['kompakt']}")
        # Rahmen: bei 125 % rundet die Plattform ihn auf 865 von 864 px (am
        # alten Stand genauso) - 2 px Spiel fuer die Rundung der Skalierung
        check(f"{text}: startet maximiert, nicht höher als der Bildschirm",
              st["maximiert"] and fh <= sh and st["rahmen_h"] <= sh + 2, detail)
        if (sb, sh) == (1920, 1080):
            check(f"{text}: Ansicht ≥ 50 % der Breite und ≥ 45 % der Höhe (Zielbild Kap. 2)",
                  ab >= 0.5 * fb and ah >= 0.45 * fh, detail)
        check(f"{text}: Ansicht ≥ 30 % der Fensterfläche", anteil >= 0.30, detail)
        maengel = []
        for m in e["masken"]:
            if "fehler" in m:
                maengel.append(f"{m['text']}: {m['fehler']}")
            elif (not m["knopf"] or m["fenster"][1] > sh or m["rahmen_h"] > sh + 2 or m["rechts"] > 480
                  or m["ansicht"][0] < 0.9 * ab):
                maengel.append(f"{m['text']}: Knopf {m['knopf']}, Fenster {m['fenster']}, rechts {m['rechts']}, "
                               f"Ansicht {m['ansicht']}")
        check(f"{text}: {len(LANGE_MASKEN)} lange/breite Masken - „Übernehmen“ sichtbar, Fenster wächst nicht, "
              "rechts ≤ 480 px", not maengel, "; ".join(maengel[:3]))


def _kind_fest():
    from PySide6 import QtCore
    from statik3d.gui import main as gm
    app = _app()
    w = gm.MainWindow()
    gm.fenster_starten(w)
    _ruhe(10)
    Q = QtCore.Qt
    erg = {"fenster": [w.width(), w.height()], "maximiert": w.isMaximized(),
           "ecke_unten_links": int(w.corner(Q.BottomLeftCorner).value),
           "unten_titel": w.unten_dock.titleBarWidget() is None,
           "tabs_min": w.tabs.minimumWidth(), "baum_min": w.baum_dock.minimumWidth()}
    w.resize(1366, 768)
    _ruhe(10)
    erg["kompakt_1366"] = w.anordnung.kompakt
    erg["gespeichert"] = w.anordnung.speichern()
    erg["register"] = w.ribbon.tabs.tabText(w.ribbon.tabs.currentIndex())
    del app
    print("MESSUNG " + json.dumps(erg), flush=True)


def test_fest_haelt_alten_stand():
    from PySide6 import QtCore
    e = _bildschirm_lauf(1920, 1080, env_extra={"STATIK3D_FENSTER": "fest"}, arg="--fest")
    if not check("STATIK3D_FENSTER=fest: Messlauf", e is not None):
        return
    check("fest: 1600 x 980, nicht maximiert, Ecke unten links beim unteren Bereich, Docktitel, "
          "Mindestbreiten 470/290 px",
          e["fenster"] == [1600, 980] and not e["maximiert"]
          and e["ecke_unten_links"] == int(QtCore.Qt.BottomDockWidgetArea.value) and e["unten_titel"]
          and e["tabs_min"] == 470 and e["baum_min"] == 290, str(e))
    check("fest: keine Kompaktstufe bei 1366 x 768, nichts gespeichert",
          e["kompakt_1366"] is False and e["gespeichert"] is None, str(e))


def _kind_gespeichert():
    from statik3d.gui import main as gm
    _app()
    w = gm.MainWindow()
    gm.fenster_starten(w)
    _ruhe(12)
    erg = {"geometrie": [w.x(), w.y(), w.width(), w.height()], "maximiert": w.isMaximized(),
           "rechts": w.eingaben_dock.width(), "baum_sichtbar": not w.baum_dock.isHidden(),
           "ribbon": w.ribbon.eingeklappt(), "eigene_masse": bool(w.anordnung._ziel)}
    print("MESSUNG " + json.dumps(erg), flush=True)


def test_start_aus_gespeichertem():
    eintrag = {"fassung": 1, "geometrie": [60, 40, 1500, 950], "maximiert": False, "bildschirm": [1920, 1080],
               "baum": 280, "rechts": 520, "unten": 260, "zonen": {"baum": False, "rechts": True, "unten": True},
               "ribbon_eingeklappt": True}
    e = _bildschirm_lauf(1920, 1080, arg="--gespeichert", einstellungen={"fenster": eintrag, "solver_threads": 2})
    if not check("Start aus einstellungen.json: Messlauf", e is not None):
        return
    check("gespeicherte Größe, Lage und Aufteilung gelten (1500 x 950, rechts 520 px, Baum aus, Ribbon eingeklappt)",
          e["geometrie"][2:] == [1500, 950] and not e["maximiert"] and abs(e["rechts"] - 520) <= 8
          and not e["baum_sichtbar"] and e["ribbon"] and e["eigene_masse"], str(e))
    e = _bildschirm_lauf(1366, 768, arg="--gespeichert", einstellungen={"fenster": eintrag})
    check("dasselbe auf einem 1366 x 768-Bildschirm: passt nicht - maximiert, Sollmaße",
          e is not None and e["maximiert"] and abs(e["rechts"] - 460) <= 8 and not e["eigene_masse"], str(e))
    e = _bildschirm_lauf(1920, 1080, arg="--gespeichert",
                         einstellungen={"fenster": dict(eintrag, fassung=99)})
    check("andere Fassungskennung: maximiert mit Sollmaßen, der Eintrag gilt nicht",
          e is not None and e["maximiert"] and e["baum_sichtbar"] and not e["ribbon"], str(e))


def test_handbuch():
    from tests.handbuch import absatz
    a = absatz("**Fensteraufteilung**")
    check("Handbuch: maximiert, 16 %, 460 px, 25 %, volle Höhe, keine Titelzeile unten",
          "maximiert" in a and "16 %" in a and "460 px" in a and "25 %" in a and "volle Höhe" in a
          and "Titelzeile" in a, a[:80])
    b = absatz("**Ansicht → Fenster**")
    check("Handbuch: Ansicht → Fenster mit Zonen, Nur Ansicht, Strg+F1, Anordnung zurücksetzen, Speichern",
          "Nur Ansicht" in b and "Strg+F1" in b and "Anordnung zurücksetzen" in b
          and "einstellungen.json" in b and "Doppelklick" in b, b[:80])
    c = absatz("**Kompaktstufe**")
    check("Handbuch: Kompaktstufe unter 900 px oder 700 × 400 px, Registerzeile, Würfel, Farbskala",
          "900 px" in c and "700 × 400" in c and "Registerzeile" in c and "Würfel" in c
          and "waagerecht" in c, c[:80])
    d = absatz("Oben eine dunkle Kopfzeile")
    check("Handbuch: Kopfzeile mit Schnellzugriff und Suche, Modellumfang in der Statusleiste",
          "Schnellzugriff" in d and "Befehlssuche" in d and "Statusleiste" in d, d[:80])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1500, exit=True)
    if "--messen" in sys.argv:
        _kind_messen()
        return 0
    if "--fest" in sys.argv:
        _kind_fest()
        return 0
    if "--gespeichert" in sys.argv:
        _kind_gespeichert()
        return 0
    for t in (test_sollmasse_und_pruefen, test_einstellungen_behalten_schluessel, test_startregister,
              test_kopfzeile, test_ecken_und_titel, test_sollmasse_im_fenster, test_ribbon_einklappen,
              test_fenstermenue, test_kompaktstufe, test_breite_maske_rollt, test_trennlinie_des_anwenders,
              test_fest_haelt_alten_stand, test_start_aus_gespeichertem, test_abnahme_bildschirme,
              test_handbuch):
        print(f"\n--- {t.__name__} ---", flush=True)
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
