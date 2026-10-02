"""
Kleinigkeiten der Oberflaeche (Teilpaket 11f, 02.10.2026).

* **Pfeile**: Aufklappliste und Drehfeld zeigen unter dem Stilblatt einen Pfeil
  (``QComboBox::drop-down { border: 0 }`` hatte Qt den eigenen Pfeil
  abgenommen). Das Stilblatt nennt die Bilder, die Bilder gibt es, laden und
  stehen in der exe (Spec, pyproject); gezeichnet sind die Pfeile im
  Unterteilbereich der Felder wirklich zu sehen - gemessen an dunklen Punkten
  im Pfeilbereich des Stils, nicht am Wortlaut des Stilblatts.
* **Titel**: „Modell – Statik3D 2.1.0“ (Halbgeviertstrich) in der Kopfzeile
  und im Fenstertitel; der Stern fuer Ungespeichertes bleibt.
* **Beispiel = Neu**: ein Beispiel hinterlaesst denselben sauberen Zustand
  wie „Neu“ (Auswahl, leuchtende Elemente, Netzguete, Maske rechts, Umhuellende
  und Stellungsreihe des vorigen Modells).
* **Hinweise** stehen auch am Eingabefeld und am Haken, nicht nur an der
  Beschriftung - und ueberschreiben nicht, was das Feld selbst meldet.

Aufruf:  python -m tests.test_kleinigkeiten
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_kleinigkeiten_"), "einstellungen.json")

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyle("Fusion")                  # wie main(): dasselbe Stilgrundwerk
    return app


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from statik3d.gui.main import MainWindow
    app = _app()
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    w.error = lambda msg, *a, **k: (w.fehler_liste.append(str(msg)), w.log.appendPlainText("FEHLER: " + str(msg)))
    _FENSTER.update(w=w, app=app)
    return w, app


def _text(pfad):
    with open(os.path.join(WURZEL, pfad), encoding="utf-8") as f:
        return f.read()


# --------------------------------------------------------------------------
# 1. Pfeile
# --------------------------------------------------------------------------
def _dunkle_punkte(bild, rechteck, grenze=170) -> int:
    """Punkte im Rechteck, die dunkler sind als der Rand (Linie #dde3e8,
    Helligkeit 228) und der Grund (weiss): der Pfeil ist #66717c (113)."""
    from PySide6 import QtGui
    n = 0
    for y in range(max(rechteck.top(), 0), min(rechteck.bottom(), bild.height() - 1) + 1):
        for x in range(max(rechteck.left(), 0), min(rechteck.right(), bild.width() - 1) + 1):
            if QtGui.QColor(bild.pixel(x, y)).lightness() < grenze:
                n += 1
    return n


def _pfeilbereiche(feld):
    """(Name, Rechteck in Feldkoordinaten) der Pfeilbereiche, so wie der Stil
    sie legt: Pfeil der Aufklappliste, oberer und unterer Pfeil des Drehfelds."""
    from PySide6 import QtWidgets
    S = QtWidgets.QStyle
    if isinstance(feld, QtWidgets.QComboBox):
        opt = QtWidgets.QStyleOptionComboBox()
        feld.initStyleOption(opt)
        return [("Pfeil", feld.style().subControlRect(S.CC_ComboBox, opt, S.SC_ComboBoxArrow, feld))]
    opt = QtWidgets.QStyleOptionSpinBox()
    feld.initStyleOption(opt)
    return [("auf", feld.style().subControlRect(S.CC_SpinBox, opt, S.SC_SpinBoxUp, feld)),
            ("ab", feld.style().subControlRect(S.CC_SpinBox, opt, S.SC_SpinBoxDown, feld))]


def _kern(r, kante=8):
    """Das Quadrat in der Mitte eines Pfeilbereichs: dort sitzt der Pfeil. Der
    Rand des Bereichs bleibt draussen - er enthaelt den blauen Rahmen eines
    Feldes mit Fokus und die Trennlinien, die Qt zwischen Drehfeldknoepfen
    zeichnet (ohne den Pfeil gemessen: 10 bzw. 25 dunkle Punkte am Rand)."""
    from PySide6 import QtCore
    c = r.center()
    return QtCore.QRect(c.x() - kante // 2, c.y() - kante // 2, kante, kante)


def _pfeile_gemessen(felder, mindestens=6, grenze=170):
    """Je Feld und Pfeilbereich die dunklen Punkte in der Mitte; (ok, Berichtszeile).
    ``grenze`` 205 zaehlt auch den grauen Pfeil eines gesperrten Feldes."""
    ok, teile = True, []
    for f in felder:
        bild = f.grab().toImage()
        for name, r in _pfeilbereiche(f):
            n = _dunkle_punkte(bild, _kern(r), grenze)
            teile.append(f"{type(f).__name__}.{name}={n}")
            ok = ok and n >= mindestens
    return ok, " ".join(teile)


def test_pfeile_im_stilblatt():
    from PySide6 import QtGui
    from statik3d.gui import design as dsg
    _app()
    css = dsg.stil()
    for regel in ("QComboBox::down-arrow", "QSpinBox::up-arrow", "QSpinBox::down-arrow",
                  "QDoubleSpinBox::up-arrow", "QDoubleSpinBox::down-arrow"):
        check(f"Stilblatt hat die Regel {regel}", regel in css)
    urls = set(re.findall(r'url\("?([^")]+)"?\)', css))
    check("Stilblatt nennt Bilder für die Pfeile", len(urls) >= 2, str(sorted(urls)))
    for u in sorted(urls):
        px = QtGui.QPixmap(u)
        check(f"Bild lädt: {os.path.basename(u)}", os.path.isfile(u) and not px.isNull() and px.width() > 0,
              f"{px.width()} x {px.height()}")
    # Die Bilder muessen in die exe und ins Paket: Spec und pyproject
    spec, proj = _text("packaging/Statik3D.spec"), _text("pyproject.toml")
    check("exe-Rezept sammelt statik3d/gui/bilder ein",
          re.search(r'"statik3d",\s*"gui",\s*"bilder"', spec) is not None)
    check("pyproject nimmt gui/bilder ins Paket",
          re.search(r'"statik3d\.gui"\s*=\s*\[[^\]]*bilder', proj) is not None)


def test_pfeile_sichtbar():
    from PySide6 import QtWidgets
    from statik3d.gui import design as dsg, masken as msk, ribbon as rib, tabellen as tab
    app = _app()
    halter = QtWidgets.QWidget()
    halter.setStyleSheet(dsg.stil() + rib.stil() + msk.stil() + tab.stil())    # wie das Hauptfenster
    lay = QtWidgets.QHBoxLayout(halter)
    cb = QtWidgets.QComboBox()
    cb.addItems(["abc", "def"])
    sp, ds = QtWidgets.QSpinBox(), QtWidgets.QDoubleSpinBox()
    # das schmale Feld der Ribbonzeile (21 px hoch): die Pfeile muessen auch dort passen
    rz = QtWidgets.QDoubleSpinBox()
    rz.setProperty("ribbonzeile", True)
    for f in (sp, ds, rz):
        f.setValue(5)          # mittendrin: am Minimum (Vorgabe 0) ist der untere Pfeil grau
    rc = QtWidgets.QComboBox()
    rc.setProperty("ribbonzeile", True)
    rc.addItems(["a"])
    felder = (cb, sp, ds, rz, rc)
    for f in felder:
        f.setFixedWidth(120)
        lay.addWidget(f)
    # so hoch wie die kleinen Knoepfe der Ribbonspalte (Stilregel ribbonzeile,
    # 25.09.2026: 21 px statt 29 px des allgemeinen Feldes)
    rz.setFixedHeight(21)
    rc.setFixedHeight(21)
    halter.resize(760, 60)
    halter.show()
    app.processEvents()
    check("Ribbonfelder sind 21 px hoch", rz.height() == 21 and rc.height() == 21,
          f"{rz.height()} und {rc.height()}")
    ok, bericht = _pfeile_gemessen(felder)
    check("Aufklappliste und Drehfeld zeichnen ihre Pfeile (dunkle Punkte im Pfeilbereich)", ok, bericht)
    halter.close()


def _bereich(feld, name):
    return dict(_pfeilbereiche(feld))[name]


def _zaehle(feld, name, grenze):
    """Punkte im Kern des Pfeilbereichs ``name``, dunkler als ``grenze``."""
    return _dunkle_punkte(feld.grab().toImage(), _kern(_bereich(feld, name)), grenze)


def test_pfeile_gesperrt_und_am_anschlag():
    """Ein gesperrtes Feld und ein Drehfeld am Anschlag zeigen den Pfeil grau
    (#a9b6c2, Helligkeit 181), nicht dunkel (#66717c, 113): dunkle Punkte unter
    170 gibt es dann keine, graue unter 205 aber noch."""
    from PySide6 import QtWidgets
    from statik3d.gui import design as dsg, masken as msk, ribbon as rib, tabellen as tab
    app = _app()
    halter = QtWidgets.QWidget()
    halter.setStyleSheet(dsg.stil() + rib.stil() + msk.stil() + tab.stil())
    lay = QtWidgets.QHBoxLayout(halter)
    cb = QtWidgets.QComboBox()
    cb.addItems(["abc"])
    sp, ds = QtWidgets.QSpinBox(), QtWidgets.QDoubleSpinBox()
    sp.setRange(0, 10)
    sp.setValue(5)
    for f in (cb, sp, ds):
        f.setFixedWidth(120)
        lay.addWidget(f)
    halter.resize(420, 60)
    halter.show()
    app.processEvents()

    def lage(f, name):
        return (_zaehle(f, name, 170), _zaehle(f, name, 205))

    dunkel, hell = lage(cb, "Pfeil")
    check("Aufklappliste freigegeben: dunkler Pfeil", dunkel >= 6, f"{dunkel} dunkel, {hell} ab 205")
    cb.setEnabled(False)
    app.processEvents()
    dunkel, hell = lage(cb, "Pfeil")
    check("Aufklappliste gesperrt: grauer Pfeil, kein dunkler", dunkel == 0 and hell >= 6,
          f"{dunkel} dunkel, {hell} unter 205")
    for f in (sp, ds):
        f.setEnabled(False)
    app.processEvents()
    ok = all(lage(f, n)[0] == 0 and lage(f, n)[1] >= 6 for f in (sp, ds) for n in ("auf", "ab"))
    check("Drehfeld gesperrt: beide Pfeile grau", ok,
          str([lage(f, n) for f in (sp, ds) for n in ("auf", "ab")]))
    sp.setEnabled(True)
    sp.setValue(0)
    app.processEvents()
    auf, ab = lage(sp, "auf"), lage(sp, "ab")
    check("Drehfeld am Minimum: oben dunkel, unten grau", auf[0] >= 6 and ab[0] == 0 and ab[1] >= 6,
          f"auf {auf}, ab {ab}")
    sp.setValue(10)
    app.processEvents()
    auf, ab = lage(sp, "auf"), lage(sp, "ab")
    check("Drehfeld am Maximum: oben grau, unten dunkel", ab[0] >= 6 and auf[0] == 0 and auf[1] >= 6,
          f"auf {auf}, ab {ab}")
    halter.close()


def _knopf_gemalt(feld, aktiv, gedrueckt=False):
    """Das Drehfeld mit dem Stil gemalt, als faehre die Maus ueber ``aktiv``
    (Aufwaertsknopf oder Abwaertsknopf); ``gedrueckt``: die Taste ist unten."""
    from PySide6 import QtGui, QtWidgets
    S = QtWidgets.QStyle
    opt = QtWidgets.QStyleOptionSpinBox()
    feld.initStyleOption(opt)
    opt.activeSubControls = aktiv
    if aktiv != S.SC_None:
        opt.state |= S.State_MouseOver
    if gedrueckt:
        opt.state |= S.State_Sunken
    bild = QtGui.QImage(feld.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
    bild.fill(QtGui.QColor("white"))
    p = QtGui.QPainter(bild)
    feld.style().drawComplexControl(S.CC_SpinBox, opt, p, feld)
    p.end()
    return bild


def test_drehfeldknoepfe_melden_zurueck():
    """Die Knoepfe des Drehfelds tragen keinen Rahmen mehr (sonst zeichnet Qt
    Trennlinien); ihre Rueckmeldung beim Ueberfahren und Druecken kommt darum
    aus dem Stilblatt: eine andere Flaeche als im Ruhezustand."""
    from PySide6 import QtGui, QtWidgets
    from statik3d.gui import design as dsg
    S = QtWidgets.QStyle
    app = _app()
    sp = QtWidgets.QDoubleSpinBox()
    sp.setStyleSheet(dsg.stil())
    sp.setRange(0, 100)
    sp.setValue(50)
    sp.setFixedWidth(120)
    sp.show()
    app.processEvents()
    for knopf, sc in (("auf", S.SC_SpinBoxUp), ("ab", S.SC_SpinBoxDown)):
        r = _bereich(sp, knopf)
        # ein Punkt im Knopf neben dem Pfeil, nicht in der Rundung der Ecke
        x, y = r.left() + 2, r.center().y()
        ruhe = QtGui.QColor(_knopf_gemalt(sp, S.SC_None).pixel(x, y)).name()
        ueber = QtGui.QColor(_knopf_gemalt(sp, sc).pixel(x, y)).name()
        druck = QtGui.QColor(_knopf_gemalt(sp, sc, True).pixel(x, y)).name()
        check(f"Knopf {knopf}: beim Überfahren eine andere Fläche als in Ruhe", ueber != ruhe,
              f"Ruhe {ruhe}, Überfahren {ueber}")
        check(f"Knopf {knopf}: beim Drücken eine dritte Fläche", druck not in (ruhe, ueber),
              f"Ruhe {ruhe}, Überfahren {ueber}, Drücken {druck}")
    sp.close()


def test_pfeile_im_hauptfenster():
    """Alle sichtbaren Aufklapplisten und Drehfelder des Hauptfensters, auch die
    der Glasleiste (eigene Regel ``QComboBox#glasliste::drop-down``)."""
    from PySide6 import QtWidgets
    w, app = _fenster()
    w.load_example("frame")
    w._objektmaske("stabelement", "0")            # Aufklapplisten der Maske rechts sichtbar
    app.processEvents()
    # das echte Drehfeld der Arbeitsebene (sp_raster) liegt in einem Register
    # des Ribbons: Register durchgehen, bis es sichtbar ist
    for i in range(w.ribbon.tabs.count()):
        w.ribbon.zeigen(w.ribbon.tabs.tabText(i))
        app.processEvents()
        if w.sp_raster.isVisible():
            break
    check("das Drehfeld der Arbeitsebene (sp_raster) ist sichtbar", w.sp_raster.isVisible(),
          w.ribbon.tabs.tabText(w.ribbon.tabs.currentIndex()))
    felder = [f for f in w.findChildren(QtWidgets.QAbstractSpinBox) + w.findChildren(QtWidgets.QComboBox)
              if f.isVisible() and f.width() > 40 and f.height() > 14
              and f.parentWidget() is not None and f.parentWidget().objectName() != "qt_scrollarea_viewport"
              and f.objectName() not in ("qt_spinbox_lineedit",)]
    glas = [f for f in felder if f.objectName() == "glasliste"]
    check("… und gemessen wird auch sp_raster", w.sp_raster in felder)
    check("das Hauptfenster hat sichtbare Aufklapplisten und Drehfelder", len(felder) >= 3, str(len(felder)))
    check("… darunter die Liste der Glasleiste", len(glas) >= 1, str(len(glas)))
    schlecht = []
    for f in felder:
        ok, bericht = _pfeile_gemessen([f], mindestens=4, grenze=205)    # dunkel oder grau (Anschlag, gesperrt)
        if not ok:
            schlecht.append(f"{type(f).__name__}#{f.objectName()}: {bericht}")
    check("jedes davon zeigt seinen Pfeil", not schlecht, "; ".join(schlecht[:4]))


# --------------------------------------------------------------------------
# 2. Titel
# --------------------------------------------------------------------------
def test_titel():
    from statik3d.gui.main import __version__
    from statik3d import update as upd
    w, app = _fenster()
    try:
        ver = upd.version_label()
    except Exception:           # noqa: BLE001
        ver = __version__
    w.new_model()
    w.model.name = "Hallenrahmen"
    w.model.meta.pop("Bauteil", None)
    w.model.meta.pop("Norm", None)
    w.path = None
    w._refresh_kopf()
    w._refresh_title()
    app.processEvents()
    check("Kopfzeile: „Hallenrahmen – Statik3D <Fassung>“", w.kopf.titel.text() == f"Hallenrahmen – Statik3D {ver}",
          w.kopf.titel.text())
    check("Fenstertitel: „Hallenrahmen – Statik3D <Fassung>“", w.windowTitle() == f"Hallenrahmen – Statik3D {ver}",
          w.windowTitle())
    w._aenderung()
    app.processEvents()
    check("geändertes Modell: Stern hinter dem Namen", w.windowTitle() == f"Hallenrahmen* – Statik3D {ver}",
          w.windowTitle())
    w.model.meta["Norm"] = "EN 1993-1-1"
    w._refresh_kopf()
    check("mit Norm: „Hallenrahmen · EN 1993-1-1 – Statik3D <Fassung>“",
          w.kopf.titel.text() == f"Hallenrahmen · EN 1993-1-1 – Statik3D {ver}", w.kopf.titel.text())
    w.model.meta.pop("Norm", None)
    w.path = os.path.join(tempfile.gettempdir(), "halle.json")
    w._refresh_title()
    check("mit Datei: der Dateiname steht vorn", w.windowTitle() == f"halle.json* – Statik3D {ver}", w.windowTitle())
    w.new_model()
    check("nach Neu: Titel ohne Stern, Name des neuen Modells",
          w.windowTitle() == f"Neues Modell – Statik3D {ver}", w.windowTitle())


# --------------------------------------------------------------------------
# 3. Beispiel = Neu
# --------------------------------------------------------------------------
def _stoerstand(w, app):
    """Ein Modell mit allem, was ein Modellwechsel wegraeumen muss."""
    import numpy as np
    from statik3d.model import Material, Section
    from statik3d.bridges.positions import Stellung
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    n = [m.add_node(4.0 * i, 0.0, 0.0) for i in range(3)]
    for i in range(2):
        m.add_element("beam", [n[i], n[i + 1]], "S355", "HEB 300")
    m.support(n[0], "all", name="Einspannung")
    g = next(iter(m.load_cases))
    m.load_node(n[-1], Fz=-5e3, case=g)
    m.stellungen.append(Stellung("S1", 0.0, "geschlossen", faelle=list(m.load_cases)))
    w.refresh_all()
    app.processEvents()
    w.stellungen_rechnen()                     # Umhuellende und Stellungsreihe dieses Modells
    w.merken("Teststand")                      # ein Schritt im Rueckgaengig-Stapel
    w.sel_linien[:] = ["L1"]
    w.sel_staebe[:] = ["1"]
    w.selection = np.array([0, 1])
    w.netzguete_feld = {"werte": [1.0], "mass": "formguete"}
    # etwas ausgeblendet, dann eine Stellungsmaske mit Vorschau: ihr Schliessen
    # stellt die Sicht „von vorher“ wieder her (_situation_vorschau(None))
    w.versteckt["elemente"] = {0}
    w._objektmaske("stellung", "S1")           # Maske rechts offen, mit Vorschau
    app.processEvents()
    w.leuchtet = [0]                           # nach der Maske: die Vorschau setzt es selbst


def _stoerstand_da(w):
    """(ok, Text): ist der Stoerstand wirklich da - sonst prueft ein Vergleich
    danach nichts."""
    z = _zustand(w)
    ok = bool(z["Maske rechts offen"] and z["Umhüllende vorhanden"] and z["Stellungsreihe vorhanden"]
              and z["Auswahl Linien"] and z["Auswahl Stäbe"] and z["leuchtende Elemente"]
              and z["Rückgängig-Stapel"] >= 1 and z["Netzgüte-Färbung"] is not None
              and z["Auswahl Knoten"] and z["Sicht-Rest"] == {0}
              and z["Docktitel"] != "Eingaben" and z["Text Umhüllende"] != "noch nicht gerechnet")
    return ok, str({k: z[k] for k in ("Maske rechts offen", "Docktitel", "Sicht-Rest", "Rückgängig-Stapel",
                                      "Auswahl Linien", "Auswahl Stäbe", "leuchtende Elemente")})


def _zustand(w):
    return {
        "Auswahl Knoten": len(w.selection), "Auswahl Linien": list(w.sel_linien),
        "Auswahl Stäbe": list(w.sel_staebe), "leuchtende Elemente": list(w.leuchtet),
        "Netzgüte-Färbung": w.netzguete_feld,
        "Maske rechts offen": w.maskenrand.offen(), "rechts zeigt": w.rechts_zeigt(),
        "Docktitel": w.eingaben_dock.windowTitle(),
        "Umhüllende vorhanden": getattr(w, "umhuellende", None) is not None,
        "Stellungsreihe vorhanden": getattr(w, "stellungsreihe", None) is not None,
        "Text Umhüllende": w.lbl_umh.text(),
        "Rückgängig-Stapel": len(w._undo), "Analyse": w.analysis, "Ergebnis": w.results,
        "Pfad": w.path, "ungespeichert": w.ungespeichert(),
        "ausgeblendete Elemente": sorted(w.versteckt["elemente"]),
        "Sicht-Rest": getattr(w, "_situation_sicht_alt", None),
    }


def test_beispiel_raeumt_auf_wie_neu():
    from statik3d.gui.main import __version__
    from statik3d import update as upd
    w, app = _fenster()
    _stoerstand(w, app)
    ok, text = _stoerstand_da(w)
    check("Vorbedingung vor Neu: der Störstand ist da (Maske, Umhüllende, Auswahl, Stapel, Sicht)", ok, text)
    w.new_model()
    app.processEvents()
    neu = _zustand(w)
    _stoerstand(w, app)
    ok, text = _stoerstand_da(w)
    check("Vorbedingung vor Beispiel: der Störstand ist da", ok, text)
    w.load_example("frame")
    app.processEvents()
    bsp = _zustand(w)
    for k in neu:
        check(f"nach Beispiel wie nach Neu: {k}", bsp[k] == neu[k], f"Beispiel {bsp[k]!r}  Neu {neu[k]!r}"[:150])
    check("im Beispiel ist nichts ausgeblendet (die Sicht des vorigen Modells kam nicht zurück)",
          not bsp["ausgeblendete Elemente"] and bsp["Sicht-Rest"] is None,
          f"{bsp['ausgeblendete Elemente']} / {bsp['Sicht-Rest']}")
    check("Neu selbst ist sauber (keine Umhüllende, keine Maske, keine Auswahl)",
          not neu["Umhüllende vorhanden"] and not neu["Stellungsreihe vorhanden"]
          and not neu["Maske rechts offen"] and not neu["Auswahl Linien"] and neu["Netzgüte-Färbung"] is None
          and neu["Text Umhüllende"] == "noch nicht gerechnet", str(neu)[:150])
    try:
        ver = upd.version_label()
    except Exception:           # noqa: BLE001
        ver = __version__
    check("nach Beispiel: Fenstertitel nennt das Beispielmodell, ohne Stern",
          w.windowTitle() == f"{w.model.name} – Statik3D {ver}" and w.model.name != "Neues Modell", w.windowTitle())
    check("nach Beispiel: das Beispielmodell ist da", len(w.model.elements) > 0 and w.model.nn > 0,
          f"{w.model.nn} Knoten, {len(w.model.elements)} Elemente")


def _gleich_wie_neu(name, neu, danach, ausser=()):
    for k in neu:
        if k in ausser:
            continue
        check(f"{name}: {k} wie nach Neu", danach[k] == neu[k], f"{danach[k]!r}  Neu {neu[k]!r}"[:150])


def test_oeffnen_raeumt_auf_wie_neu():
    """Das Oeffnen einer Datei (modell_laden) raeumt wie Neu auf - bis
    02.10.2026 liess es Maske, Umhuellende, Auswahl und Netzguete stehen."""
    w, app = _fenster()
    w.load_example("frame")
    datei = os.path.join(tempfile.mkdtemp(prefix="statik3d_klein_oeffnen_"), "rahmen.json")
    w.model.save(datei)
    w.new_model()
    neu = _zustand(w)
    _stoerstand(w, app)
    ok, text = _stoerstand_da(w)
    check("Vorbedingung vor Öffnen: der Störstand ist da", ok, text)
    check("Datei geladen", w.modell_laden(datei, fragen=False) is True)
    app.processEvents()
    geoeffnet = _zustand(w)
    _gleich_wie_neu("nach Öffnen", neu, geoeffnet, ausser=("Pfad",))
    check("nach Öffnen: der Pfad ist die Datei, nichts ist ungespeichert",
          w.path == datei and geoeffnet["ungespeichert"] == "", f"{w.path} / {geoeffnet['ungespeichert']!r}")
    check("nach Öffnen: Fenstertitel nennt die Datei, ohne Stern", w.windowTitle().startswith("rahmen.json – "),
          w.windowTitle())


def test_import_ohne_anhaengen():
    """Import ohne Anhaengen: aufgeraeumt wie Neu, und der Pfad der zuvor
    geoeffneten Datei ist weg - sonst schriebe Strg+S das importierte Modell
    ungefragt ueber diese Datei (bis 02.10.2026)."""
    from PySide6 import QtWidgets
    from statik3d.gui import dialogs as dg
    from tests.test_rfem6 import make_rf6
    w, app = _fenster()
    tmp = tempfile.mkdtemp(prefix="statik3d_klein_import_")
    w.load_example("frame")
    alt = os.path.join(tmp, "alt.json")
    w.model.save(alt)
    with open(alt, "rb") as f:
        alt_inhalt = f.read()
    w.new_model()
    neu = _zustand(w)
    f_rf6 = make_rf6(os.path.join(tmp, "b.rf6"), nodes=[(0, 0, 0), (2, 0, 0)], lines=[[1, 2]],
                     members=[(1, None, None)],
                     supports=[("Fest", (float("inf"),) * 6, (0,) * 6, None, [1])])
    _stoerstand(w, app)
    w.path = alt                               # zuvor geoeffnet: alt.json
    w._refresh_title()
    ok, text = _stoerstand_da(w)
    check("Vorbedingung vor Import: der Störstand ist da, Pfad = alt.json", ok and w.path == alt, text)
    alt_fk, alt_open, alt_exec = w._fragen_knoepfe, QtWidgets.QFileDialog.getOpenFileName, dg.ImportDialog.exec
    alt_save = QtWidgets.QFileDialog.getSaveFileName
    w._fragen_knoepfe = lambda *a, **k: False
    QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (f_rf6, ""))
    dg.ImportDialog.exec = lambda self: 1
    try:
        w.import_file()
        app.processEvents()
        importiert = _zustand(w)
        _gleich_wie_neu("nach Import", neu, importiert, ausser=("ungespeichert", "Rückgängig-Stapel", "Text Umhüllende"))
        check("nach Import: der Pfad ist weg (Strg+S fragt nach dem Dateinamen)", w.path is None, str(w.path))
        check("nach Import: der Titel nennt nicht mehr alt.json", "alt.json" not in w.windowTitle(), w.windowTitle())
        check("nach Import: das Modell gilt als ungespeichert", bool(importiert["ungespeichert"]),
              repr(importiert["ungespeichert"]))
        gefragt = []
        QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (gefragt.append(a), ("", ""))[1])
        w.save_model()
        check("Strg+S nach dem Import fragt nach dem Dateinamen", len(gefragt) == 1, str(len(gefragt)))
        with open(alt, "rb") as f:
            check("alt.json ist unverändert", f.read() == alt_inhalt)
    finally:
        w._fragen_knoepfe = alt_fk
        QtWidgets.QFileDialog.getOpenFileName = alt_open
        QtWidgets.QFileDialog.getSaveFileName = alt_save
        dg.ImportDialog.exec = alt_exec


# --------------------------------------------------------------------------
# 4. Hinweise am Feld und am Haken
# --------------------------------------------------------------------------
def test_hinweise_am_feld():
    from PySide6 import QtWidgets
    from statik3d.gui import masken as msk
    app = _app()
    F = msk.Feld
    mk = msk.Maske("Probe", [
        F("z", "Zahl", "zahl", 1.0, hinweis="H-zahl"), F("g", "Ganz", "ganz", 2, hinweis="H-ganz"),
        F("t", "Text", "text", "a", hinweis="H-text"), F("l", "Liste", "liste", "a, b", hinweis="H-liste"),
        F("w", "Wahl", "wahl", "x", ["x", "y"], hinweis="H-wahl"),
        F("m", "Mehrfach", "mehrfach", "a", ["a", "b"], hinweis="H-mehrfach"),
        F("h", "Haken", "haken", True, hinweis="H-haken"), F("i", "Info", "info", "Text", hinweis="H-info"),
        F("o", "Ohne", "text", "q"), F("oz", "Ohne Zahl", "zahl", 3.0)])
    mk.show()
    app.processEvents()
    fe = mk._felder
    for name, erwartet in (("z", "H-zahl"), ("g", "H-ganz"), ("t", "H-text"), ("w", "H-wahl"),
                           ("m", "H-mehrfach"), ("h", "H-haken"), ("i", "H-info")):
        check(f"Hinweis am Feld „{name}“ ({type(fe[name]).__name__})", fe[name].toolTip() == erwartet,
              repr(fe[name].toolTip()))
    check("Listenfeld: sein eigener Hinweis nennt den Hinweis und die Einträge",
          "H-liste" in fe["l"].toolTip() and "2 Einträge" in fe["l"].toolTip(), repr(fe["l"].toolTip()))
    check("Feld ohne Hinweis bleibt ohne", fe["o"].toolTip() == "" and fe["oz"].toolTip() == "",
          f"{fe['o'].toolTip()!r} {fe['oz'].toolTip()!r}")
    labels = {lb.text(): lb for lb in mk.findChildren(QtWidgets.QLabel)}
    check("die Beschriftung behält ihren Hinweis", labels["Zahl"].toolTip() == "H-zahl"
          and labels["Wahl"].toolTip() == "H-wahl", repr(labels["Zahl"].toolTip()))
    # Die Meldung eines Zahlenfelds geht vor - der Hinweis kommt zurueck, wenn die Eingabe stimmt
    z = fe["z"]
    z.setText("abc")
    z.fertig()
    meldung = z.toolTip()
    check("ungültige Zahl: am Feld steht die Meldung, nicht der Hinweis",
          meldung and meldung != "H-zahl", repr(meldung))
    z.setText("2")
    z.fertig()
    check("danach steht wieder der Hinweis", z.toolTip() == "H-zahl", repr(z.toolTip()))
    mk.setzen("l", "x, y, z")
    check("Listenfeld nach setzen: Hinweis und neue Einträge", "H-liste" in fe["l"].toolTip()
          and "3 Einträge" in fe["l"].toolTip(), repr(fe["l"].toolTip()))
    mk.close()


def test_hinweise_in_echten_masken():
    """Alle Felder einiger Masken des Programms: wo die Beschriftung einen
    Hinweis traegt, traegt ihn auch das Feld (bei Listen: im eigenen Hinweis)."""
    w, app = _fenster()
    w.load_example("frame")
    app.processEvents()
    m = w.model
    gepruft, fehlt, masken = 0, [], []
    arten = (("stabelement", "0"), ("lager", "0"), ("knoten", "0"), ("linie", next(iter(m.lines), "")),
             ("stab", next(iter(m.members), "")), ("lastfall", next(iter(m.load_cases), "")))
    for art, name in arten:
        if not name:
            continue
        try:
            mk = w._objektmaske(art, name)
        except Exception as ex:                       # noqa: BLE001
            print(f"  Maske {art} {name}: Ausnahme {ex}")
            continue
        app.processEvents()
        mk = w.maskenrand.maske
        if mk is None or not getattr(mk, "_hinweise", None):
            continue
        masken.append(f"{art}:{len(mk._hinweise)}")
        for fname, hinweis in mk._hinweise.items():
            w_ = mk._felder.get(fname)
            gepruft += 1
            if w_ is None or hinweis not in w_.toolTip():
                fehlt.append(f"{art}.{fname}")
    check("echte Masken mit Hinweisen gefunden (Stab, …)", gepruft >= 5, f"{gepruft} Felder in {masken}")
    check("jedes Feld mit Hinweis zeigt ihn auch am Feld", not fehlt, ", ".join(fehlt[:8]))


def test_handbuch():
    # Zeilenumbrueche und Mehrfachleerzeichen eingeebnet: die Saetze stehen
    # im Handbuch umbrochen
    hb = " ".join(_text("docs/Benutzerhandbuch.md").split())
    for name, satz in (("Pfeile", "**Aufklapplisten und Drehfelder** zeigen rechts ihren Pfeil"),
                       ("Titel", "„Hallenrahmen – Statik3D 2.1.0“"),
                       ("Beispiel, Öffnen, Import", "ebenso das *Öffnen* einer Datei und der *Import* ohne Anhängen"),
                       ("graue Pfeile", "zeigen den Pfeil grau"),
                       ("Hinweise", "Der **Hinweis** zu einem Feld erscheint")):
        check(f"Handbuch beschreibt: {name}", satz in hb)
    for name, satz in (("Kopfzeile", "Bis zum 02.10.2026 hieß die Kopfzeile"),
                       ("Pfeile", "Bis zum 02.10.2026 fehlte der Pfeil"),
                       ("Hinweise", "Bis zum 02.10.2026 stand er nur an der Beschriftung"),
                       ("Beispiel", "Bis zum 02.10.2026 räumte nur *Neu* so auf"),
                       ("Import", "Bis zum 02.10.2026 blieb der Pfad stehen")):
        check(f"Handbuch nennt den Stand vorher: {name}", satz in hb)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_pfeile_im_stilblatt, test_pfeile_sichtbar, test_pfeile_gesperrt_und_am_anschlag,
              test_drehfeldknoepfe_melden_zurueck, test_pfeile_im_hauptfenster, test_titel,
              test_beispiel_raeumt_auf_wie_neu, test_oeffnen_raeumt_auf_wie_neu, test_import_ohne_anhaengen,
              test_hinweise_am_feld, test_hinweise_in_echten_masken, test_handbuch):
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
