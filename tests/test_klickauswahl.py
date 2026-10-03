"""
Klick in der Ansicht: ersetzen oder dazunehmen (Plan-Teilpaket 14b, 03.10.2026).

Entscheidungen des Anwenders:

* Antwort 7 vom 24.09.2026: „Linksklick ersetzt die Auswahl, Strg+Klick fügt
  hinzu, wie in RFEM und Windows. Heute schaltet jeder Klick hinzu oder weg.“
* E5 vom 01.10.2026: das Auswahlfenster ersetzt die Auswahl, mit Strg fügt es
  hinzu.

Stand davor (am Quelltext und offscreen gemessen): jeder Klick schaltete das
getroffene Objekt in seiner Art hinzu oder weg, die Auswahl der anderen Arten
blieb stehen; das Auswahlfenster nahm die Treffer immer dazu; Strg tat nichts.
Je Klick lief die Ansicht einmal neu auf (redraw), das Kontextregister aber
zweimal (``_auswahl_register`` und noch einmal in ``redraw``), beim Klick ins
Leere auch der rechte Bereich zweimal.

Geprueft wird mit dem echten Hauptfenster (offscreen). Die Klicks gehen als
Qt-Mausereignisse mit den Tasten an die Ansicht (wie „Klick und Ziehen“ in
``tests/test_gui_smoke.py``); VTK sieht den Zeiger dort, wo der Klick liegt.
Offscreen hat das Renderfenster die Groesse 0 x 0 (gemessen), jeder Weltpunkt
landete auf dem Bildpunkt (0, 0). Die Pruefung bildet darum die Draufsicht
selbst ab (``_projizieren``, 30 Bildpunkte je Meter); Fang, Stab- und
Linienfinder und das Auswahlfenster rechnen damit wie im Programm. Der
Zellenpicker braucht ein gezeichnetes Bild - fuer die Flaechen steht ein
Ersatz, der nach der Lage des Zeigers entscheidet.

* Klick ersetzt, Strg+Klick nimmt dazu, Strg+Klick auf Gewaehltes nimmt es
  heraus - fuer Knoten, Staebe und Flaechen;
* intelligente Auswahl: die Fortsetzung kommt mit, die alte Auswahl geht;
  Umschalt+Klick ersetzt mit der Kette, Strg+Umschalt+Klick nimmt sie dazu;
* Auswahlfenster: ohne Strg ersetzt, mit Strg dazu;
* Klick ins Leere hebt die Auswahl auf, mit Strg bleibt sie;
* Klickfeld einer Maske, Messen und Sonde verhalten sich wie vorher;
* ein Klick zeichnet die Ansicht genau einmal, das Kontextregister laeuft
  einmal, nichts ruft refresh_all.

Aufruf:  python -m tests.test_klickauswahl
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_klickauswahl_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    # Rueckfragen nie anzeigen (Neu mit ungespeicherten Aenderungen)
    w._fragen_knoepfe = lambda *a, **k: True
    w._bestaetigen = lambda *a, **k: True
    w._frage_speichern_verwerfen = lambda *a, **k: "verwerfen"
    w.fehler_liste = []
    w.error = lambda msg, *a, **k: w.fehler_liste.append(str(msg))
    _FENSTER.update(w=w, app=app)
    return w, app


#: Knoten des Pruefmodells
K = {"K0": (0, 0, 0), "K1": (4, 0, 0), "K2": (8, 0, 0), "K3": (12, 0, 0),
     "K4": (0, 5, 0), "K5": (4, 5, 0)}


#: Draufsicht der Pruefung: Bildpunkte je Meter und Lage des Ursprungs (VTK-Bildpunkte)
MASS, X0, Y0 = 30.0, 60.0, 40.0
#: Flaechen des Pruefmodells: Name -> (x von, x bis, y von, y bis)
FLAECHEN = {"F1": (0.0, 4.0, 9.0, 13.0), "F2": (8.0, 12.0, 9.0, 13.0)}


def _draufsicht(w):
    """Die Abbildung Welt -> Bildpunkte fuer offscreen (siehe oben) und ein
    Ersatz fuer den Zellenpicker: die Flaeche, ueber der der Zeiger steht."""
    def projizieren(punkte):
        P = np.atleast_2d(np.asarray(punkte, float))
        if not len(P):
            return np.zeros((0, 2)), np.zeros(0, bool)
        return np.stack([X0 + MASS * P[:, 0], Y0 + MASS * P[:, 1]], axis=1), np.ones(len(P), bool)

    def objekt_am_zeiger(art):
        zp = w._zeigerposition()
        if zp is None or art != "Fläche":
            return None
        x, y = (zp[0] - X0) / MASS, (zp[1] - Y0) / MASS
        return next((name for name, (x1, x2, y1, y2) in FLAECHEN.items()
                     if x1 < x < x2 and y1 < y < y2), None)
    w._projizieren = projizieren
    w._objekt_am_zeiger = objekt_am_zeiger


def _modell(w, app):
    """Drei Staebe in einer Reihe (S1-S2-S3, eine eindeutige Kette), ein Stab
    abseits (S4) und zwei vernetzte Flaechen F1 und F2 nebeneinander."""
    from statik3d.model import Member as Mb
    w.new_model()
    m = w.model
    m.netz.teilung_uebersteuern = False
    mat, sec = list(m.materials)[0], list(m.sections)[0]
    n = {name: m.add_node(*p) for name, p in K.items()}
    for name, (a, b) in (("S1", ("K0", "K1")), ("S2", ("K1", "K2")), ("S3", ("K2", "K3")),
                         ("S4", ("K4", "K5"))):
        e = m.add_element("beam", [n[a], n[b]], mat, sec)
        m.members[name] = Mb(name, elements=[e])
    for name, (x0, _x1, y0, _y1) in FLAECHEN.items():
        ecken = [m.add_node(x0 + dx, y0 + dy, 0.0) for dx, dy in ((0, 0), (4, 0), (4, 4), (0, 4))]
        linien = []
        for j in range(4):
            ln = f"{name}L{j}"
            m.add_line(ln, [ecken[j], ecken[(j + 1) % 4]])
            linien.append(ln)
        f = m.add_flaeche(name, linien, dicke=list(m.shells)[0], material=mat, teilung=[4, 4])
        w._vernetzen([f], [])
    w.refresh_all()
    w.auswahlart_setzen("Knoten")
    _draufsicht(w)
    app.processEvents()
    return m, n


def _maus(w, app, typ, pos, knopf, knoepfe, tasten):
    from PySide6 import QtCore, QtGui, QtWidgets
    ev = QtGui.QMouseEvent(typ, pos, pos, knopf, knoepfe, tasten)
    QtWidgets.QApplication.sendEvent(w.plotter.interactor, ev)
    app.processEvents()


def _qt(w, P):
    """Weltpunkt -> (VTK-Anzeigepunkt, Qt-Bildpunkt der Ansicht)."""
    from PySide6 import QtCore
    xy, _s = w._projizieren(np.atleast_2d(np.asarray(P, float)))
    x, y = float(xy[0, 0]), float(xy[0, 1])
    s = w._pixelmass()
    h = w.plotter.interactor.height()
    return (x, y), QtCore.QPointF(x / s, h - 1 - y / s)


def _tasten(strg=False, umschalt=False):
    from PySide6 import QtCore
    t = QtCore.Qt.NoModifier
    if strg:
        t |= QtCore.Qt.ControlModifier
    if umschalt:
        t |= QtCore.Qt.ShiftModifier
    return t


def klick(w, app, P, strg=False, umschalt=False):
    """Linksklick (Druecken und Loslassen ohne Zug) auf den Weltpunkt P."""
    from PySide6 import QtCore
    (x, y), pos = _qt(w, P)
    # VTK sieht den Zeiger hier - wie nach der Mausbewegung dorthin
    w.plotter.iren.interactor.SetEventInformation(int(round(x)), int(round(y)))
    t = _tasten(strg, umschalt)
    _maus(w, app, QtCore.QEvent.MouseButtonPress, pos, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, t)
    _maus(w, app, QtCore.QEvent.MouseButtonRelease, pos, QtCore.Qt.LeftButton, QtCore.Qt.NoButton, t)


def fenster(w, app, P1, P2, strg=False):
    """Auswahlfenster mit gedrueckter linker Taste von P1 nach P2 aufziehen."""
    from PySide6 import QtCore
    _xy1, q1 = _qt(w, P1)
    _xy2, q2 = _qt(w, P2)
    t = _tasten(strg)
    _maus(w, app, QtCore.QEvent.MouseButtonPress, q1, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, t)
    mitte = QtCore.QPointF(0.5 * (q1.x() + q2.x()), 0.5 * (q1.y() + q2.y()))
    for q in (mitte, q2):
        _maus(w, app, QtCore.QEvent.MouseMove, q, QtCore.Qt.NoButton, QtCore.Qt.LeftButton, t)
    _maus(w, app, QtCore.QEvent.MouseButtonRelease, q2, QtCore.Qt.LeftButton, QtCore.Qt.NoButton, t)


def _mitte(m, a, b):
    return 0.5 * (np.asarray(m.nodes[a], float) + np.asarray(m.nodes[b], float))


def _knoten(w):
    return sorted(int(i) for i in w.selection)


def _leeren(w, app):
    w.maskenrand.schliessen()
    w.clear_selection()
    app.processEvents()


# ---------------------------------------------------------------------------
def test_knoten():
    w, app = _fenster()
    m, n = _modell(w, app)
    _leeren(w, app)
    w.sel_staebe.append("S4")              # eine andere Art ist schon gewaehlt
    klick(w, app, m.nodes[n["K1"]])
    check("Knoten: Klick wählt K1 und ersetzt die Auswahl (der Stab S4 geht)",
          _knoten(w) == [n["K1"]] and not w.sel_staebe, f"{_knoten(w)} {w.sel_staebe}")
    klick(w, app, m.nodes[n["K2"]])
    check("… Klick auf K2: nur noch K2 gewählt", _knoten(w) == [n["K2"]], str(_knoten(w)))
    klick(w, app, m.nodes[n["K1"]], strg=True)
    check("… Strg+Klick auf K1 fügt hinzu: K1 und K2", _knoten(w) == sorted([n["K1"], n["K2"]]),
          str(_knoten(w)))
    klick(w, app, m.nodes[n["K2"]], strg=True)
    check("… Strg+Klick auf das gewählte K2 nimmt es heraus: K1", _knoten(w) == [n["K1"]], str(_knoten(w)))
    klick(w, app, m.nodes[n["K1"]])
    check("… Klick ohne Strg auf das gewählte K1 lässt es gewählt (kein Umschalten mehr)",
          _knoten(w) == [n["K1"]], str(_knoten(w)))
    check("… das Kontextregister zählt mit („Auswahl: 1 Knoten“)",
          w.ribbon._kontext is not None and w.ribbon.tabs.tabText(w.ribbon.tabs.indexOf(w.ribbon._kontext))
          == "Auswahl: 1 Knoten")
    _leeren(w, app)


def test_stab():
    w, app = _fenster()
    m, n = _modell(w, app)
    _leeren(w, app)
    alt = w.act_klug.isChecked()
    w.auswahlart_setzen("Stab")
    try:
        w.act_klug.setChecked(False)
        w.selection = np.array([n["K4"]], int)     # Knoten gewaehlt, gleich ersetzt
        klick(w, app, _mitte(m, n["K0"], n["K1"]))
        check("Stab: Klick wählt S1 und ersetzt die Auswahl (Knoten K4 geht)",
              w.sel_staebe == ["S1"] and not len(w.selection), f"{w.sel_staebe} {_knoten(w)}")
        klick(w, app, _mitte(m, n["K4"], n["K5"]))
        check("… Klick auf S4: nur noch S4", w.sel_staebe == ["S4"], str(w.sel_staebe))
        klick(w, app, _mitte(m, n["K0"], n["K1"]), strg=True)
        check("… Strg+Klick auf S1 fügt hinzu", sorted(w.sel_staebe) == ["S1", "S4"], str(w.sel_staebe))
        klick(w, app, _mitte(m, n["K4"], n["K5"]), strg=True)
        check("… Strg+Klick auf das gewählte S4 nimmt es heraus", w.sel_staebe == ["S1"], str(w.sel_staebe))
        # Intelligente Auswahl: die Fortsetzung kommt mit, die alte Auswahl geht
        w.act_klug.setChecked(True)
        klick(w, app, _mitte(m, n["K4"], n["K5"]))
        klick(w, app, _mitte(m, n["K1"], n["K2"]))
        check("intelligente Auswahl: Klick auf S2 holt die Kette S1–S3, S4 geht",
              sorted(w.sel_staebe) == ["S1", "S2", "S3"], str(w.sel_staebe))
        klick(w, app, _mitte(m, n["K4"], n["K5"]), strg=True)
        check("… Strg+Klick auf S4 nimmt ihn dazu", sorted(w.sel_staebe) == ["S1", "S2", "S3", "S4"],
              str(w.sel_staebe))
        klick(w, app, _mitte(m, n["K0"], n["K1"]), strg=True)
        check("… Strg+Klick auf das gewählte S1 nimmt die ganze Kette heraus", w.sel_staebe == ["S4"],
              str(w.sel_staebe))
        # Umschalt erzwingt die Kette (Schalter aus) und ersetzt wie ein Klick
        w.act_klug.setChecked(False)
        klick(w, app, _mitte(m, n["K1"], n["K2"]), umschalt=True)
        check("Umschalt+Klick (Schalter aus): die Kette S1–S3 ersetzt die Auswahl (S4 geht)",
              sorted(w.sel_staebe) == ["S1", "S2", "S3"], str(w.sel_staebe))
        klick(w, app, _mitte(m, n["K4"], n["K5"]))
        klick(w, app, _mitte(m, n["K2"], n["K3"]), strg=True, umschalt=True)
        check("Strg+Umschalt+Klick nimmt die Kette dazu (S4 bleibt)",
              sorted(w.sel_staebe) == ["S1", "S2", "S3", "S4"], str(w.sel_staebe))
        klick(w, app, _mitte(m, n["K2"], n["K3"]))
        check("ein Klick ohne Taste: nur der eine Stab", w.sel_staebe == ["S3"], str(w.sel_staebe))
    finally:
        w.act_klug.setChecked(alt)
        w.auswahlart_setzen("Knoten")
    # Auswahlart Knoten, Klick auf einen Stab: die Art springt um, die Knoten gehen
    w.selection = np.array([n["K4"]], int)
    w.sel_staebe.clear()
    w.act_klug.setChecked(False)
    try:
        klick(w, app, _mitte(m, n["K1"], n["K2"]) + [0.6, 0.0, 0.0])
        check("Auswahlart Knoten, Klick auf die Stabachse: Stab S2 gewählt, Art Stab, Knoten weg",
              w.auswahlart == "Stab" and w.sel_staebe == ["S2"] and not len(w.selection),
              f"{w.auswahlart} {w.sel_staebe} {_knoten(w)}")
        w.auswahlart_setzen("Knoten")
        w.selection = np.array([n["K4"]], int)
        klick(w, app, _mitte(m, n["K2"], n["K3"]) + [0.6, 0.0, 0.0], strg=True)
        check("… mit Strg: S3 kommt dazu, der Knoten K4 bleibt",
              w.sel_staebe == ["S2", "S3"] and _knoten(w) == [n["K4"]], f"{w.sel_staebe} {_knoten(w)}")
    finally:
        w.act_klug.setChecked(alt)
        w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_flaeche():
    w, app = _fenster()
    m, n = _modell(w, app)
    _leeren(w, app)
    w.auswahlart_setzen("Fläche")
    try:
        f1, f2 = np.array([2.0, 11.0, 0.0]), np.array([10.0, 11.0, 0.0])
        w.sel_staebe.append("S1")
        klick(w, app, f1)
        check("Fläche: Klick wählt F1 und ersetzt die Auswahl (S1 geht)",
              w.sel_flaechen == ["F1"] and not w.sel_staebe, f"{w.sel_flaechen} {w.sel_staebe}")
        klick(w, app, f2)
        check("… Klick auf F2: nur noch F2", w.sel_flaechen == ["F2"], str(w.sel_flaechen))
        klick(w, app, f1, strg=True)
        check("… Strg+Klick auf F1 fügt hinzu", sorted(w.sel_flaechen) == ["F1", "F2"], str(w.sel_flaechen))
        klick(w, app, f2, strg=True)
        check("… Strg+Klick auf das gewählte F2 nimmt es heraus", w.sel_flaechen == ["F1"], str(w.sel_flaechen))
    finally:
        w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_fenster():
    w, app = _fenster()
    m, n = _modell(w, app)
    _leeren(w, app)
    w.sel_staebe.append("S4")
    w.selection = np.array([n["K4"]], int)
    links_unten = np.asarray(m.nodes[n["K0"]], float) + [-1.0, -1.0, 0.0]
    rechts_oben = np.asarray(m.nodes[n["K2"]], float) + [1.0, 1.0, 0.0]
    fenster(w, app, links_unten, rechts_oben)
    check("Auswahlfenster ohne Strg ersetzt: genau K0, K1, K2 (K4 und S4 gehen)",
          _knoten(w) == sorted([n["K0"], n["K1"], n["K2"]]) and not w.sel_staebe and w._fenster_ecke is None,
          f"{_knoten(w)} {w.sel_staebe}")
    fenster(w, app, np.asarray(m.nodes[n["K4"]], float) + [-1.0, -1.0, 0.0],
            np.asarray(m.nodes[n["K4"]], float) + [1.0, 1.0, 0.0], strg=True)
    check("… mit Strg aufgezogen: K4 kommt dazu",
          _knoten(w) == sorted([n["K0"], n["K1"], n["K2"], n["K4"]]), str(_knoten(w)))
    leer_a = np.array([5.0, 6.0, 0.0])
    fenster(w, app, leer_a, leer_a + [2.0, 1.5, 0.0], strg=True)
    check("… ein leeres Fenster mit Strg lässt die Auswahl stehen", len(_knoten(w)) == 4, str(_knoten(w)))
    fenster(w, app, leer_a, leer_a + [2.0, 1.5, 0.0])
    check("… ein leeres Fenster ohne Strg hebt sie auf (wie der Klick ins Leere)",
          not len(w.selection) and not w.sel_staebe, str(_knoten(w)))
    _leeren(w, app)


def test_klick_ins_leere():
    w, app = _fenster()
    m, n = _modell(w, app)
    _leeren(w, app)
    leer = np.array([6.0, 6.5, 0.0])
    w.selection = np.array([n["K1"]], int)
    w.sel_staebe.append("S4")
    klick(w, app, leer, strg=True)
    check("Strg+Klick ins Leere: die Auswahl bleibt (Strg nimmt nie etwas weg)",
          _knoten(w) == [n["K1"]] and w.sel_staebe == ["S4"], f"{_knoten(w)} {w.sel_staebe}")
    klick(w, app, leer)
    check("Klick ins Leere ohne Taste hebt die Auswahl auf (wie bisher)",
          not len(w.selection) and not w.sel_staebe, f"{_knoten(w)} {w.sel_staebe}")
    _leeren(w, app)


def test_maske_messen_sonde():
    """Klickfeld einer Maske, Messen und Sonde: wie vorher, auch ohne Strg
    ersetzt ein solcher Klick die Auswahl nicht."""
    w, app = _fenster()
    m, n = _modell(w, app)
    _leeren(w, app)
    # Klickfeld: die Maske „Lot“ nimmt eine Flaeche ins Feld „Objekt“
    w.selection = np.array([n["K4"]], int)
    w.maske_lot()
    app.processEvents()
    mk = w.maskenrand.maske
    mk.feld_fokussiert.emit("objekt")
    app.processEvents()
    check("Maske Lot: Klickfeld „Objekt“ scharf (Klickmodus Fläche)", w.maskenrand.objekt_modus() == "flaeche",
          repr(w.maskenrand.objekt_modus()))
    klick(w, app, np.array([10.0, 11.0, 0.0]))
    check("… Klick auf F2 füllt das Feld, die Knotenauswahl bleibt",
          mk.werte().get("objekt") == "F2" and _knoten(w) == [n["K4"]] and not w.sel_flaechen,
          f"{mk.werte().get('objekt')!r} {_knoten(w)} {w.sel_flaechen}")
    klick(w, app, np.array([2.0, 11.0, 0.0]))
    check("… ein zweiter Klick (ohne Strg) auf F1 ebenso", mk.werte().get("objekt") == "F1"
          and _knoten(w) == [n["K4"]], f"{mk.werte().get('objekt')!r} {_knoten(w)}")
    w.maskenrand.schliessen()
    app.processEvents()
    # Messen: der Klick gibt der Maske den Punkt
    w.sel_staebe.append("S4")
    w.messen("abstand")
    app.processEvents()
    mk = w.maskenrand.maske
    nn0 = m.nn
    klick(w, app, m.nodes[n["K1"]])
    klick(w, app, m.nodes[n["K2"]])
    check("Messen: zwei Klicks, zwei Punkte für die Maske, kein Knoten neu, Auswahl unverändert",
          len(mk.gewaehlt_punkte) == 2 or bool(w.messungen), f"{len(mk.gewaehlt_punkte)} {len(w.messungen)}")
    check("… die Auswahl (S4) bleibt, nichts Neues gewählt",
          w.sel_staebe == ["S4"] and m.nn == nn0, f"{w.sel_staebe} {_knoten(w)} {m.nn}/{nn0}")
    w.maskenrand.schliessen()
    w.messungen_loeschen()
    app.processEvents()
    # Sonde: der Klick setzt eine Marke statt zu waehlen
    w.act_sonde.setChecked(True)
    try:
        vorher = (_knoten(w), list(w.sel_staebe))
        klick(w, app, m.nodes[n["K2"]])
        check("Sonde: Klick setzt eine Marke am Knoten, die Auswahl bleibt, wie sie war",
              len(w.sonden) == 1 and w.sonden[0]["knoten"] == n["K2"]
              and (_knoten(w), list(w.sel_staebe)) == vorher and w.sel_staebe == ["S4"],
              f"{w.sonden} {w.sel_staebe} {_knoten(w)}")
    finally:
        w.act_sonde.setChecked(False)
        w.sonden = []
    _leeren(w, app)


# ---------------------------------------------------------------------------
class _Zaehler:
    """Zaehlt waehrend eines Klicks, was zeichnet oder nachzieht."""
    NAMEN = ("redraw", "refresh_all", "_aufbauen", "_kontext_abgleichen", "_info_zeigen",
             "_tabellen_markieren", "_refresh_baum", "refresh_modelltabellen")

    def __init__(self, w):
        self.w = w
        self.z = {}

    def __enter__(self):
        w, z = self.w, self.z
        for name in self.NAMEN:
            orig = getattr(w, name)

            def huelle(*a, _o=orig, _n=name, **k):
                z[_n] = z.get(_n, 0) + 1
                return _o(*a, **k)
            setattr(w, name, huelle)
        # plotter.render auf der Klasse: _Stille legt ihn waehrend des Aufbaus
        # still und nimmt die eigene Huelle danach wieder weg
        self.klasse = type(w.plotter)
        self.render_alt = self.klasse.render

        def render(pl, *a, **k):
            z["render"] = z.get("render", 0) + 1
            return self.render_alt(pl, *a, **k)
        self.klasse.render = render
        # der Takt von pyvistaqt zeichnet fuenfmal je Sekunde von selbst - das
        # ist kein Neuzeichnen durch den Klick
        self.takt = getattr(w.plotter, "render_timer", None)
        if self.takt is not None:
            self.takt.stop()
        return self

    def __exit__(self, *exc):
        for name in self.NAMEN:
            self.w.__dict__.pop(name, None)
        self.klasse.render = self.render_alt
        if self.takt is not None:
            self.takt.start()
        return False

    def __getitem__(self, name):
        return self.z.get(name, 0)


def test_ein_neuzeichnen_je_klick():
    w, app = _fenster()
    m, n = _modell(w, app)
    _leeren(w, app)

    def einmal(titel, f, info_hoechstens=1):
        app.processEvents()
        with _Zaehler(w) as z:
            f()
            app.processEvents()
        ok = (z["redraw"] == 1 and z["_aufbauen"] == 1 and z["render"] == 1 and z["refresh_all"] == 0
              and z["_kontext_abgleichen"] == 1 and z["_info_zeigen"] <= info_hoechstens
              and z["_tabellen_markieren"] <= 1 and z["_refresh_baum"] == 0
              and z["refresh_modelltabellen"] == 0)
        check(f"ein Neuzeichnen: {titel}", ok, ", ".join(f"{k}={v}" for k, v in sorted(z.z.items())))

    w.sel_staebe.append("S4")
    einmal("Klick auf einen Knoten (ersetzt)", lambda: klick(w, app, m.nodes[n["K1"]]))
    einmal("Strg+Klick auf einen Knoten", lambda: klick(w, app, m.nodes[n["K2"]], strg=True))
    einmal("Strg+Klick auf einen gewählten Knoten", lambda: klick(w, app, m.nodes[n["K2"]], strg=True))
    # die Art springt um (Knoten -> Stab), waehrend ein Objekt unter dem Zeiger leuchtet
    w._hover_stand = ("Knoten", int(n["K1"]))
    einmal("Klick auf einen Stab in Auswahlart Knoten (Art springt, Hervorhebung weg)",
           lambda: klick(w, app, _mitte(m, n["K1"], n["K2"]) + [0.6, 0.0, 0.0]))
    w.auswahlart_setzen("Stab")
    einmal("Klick auf einen Stab", lambda: klick(w, app, _mitte(m, n["K4"], n["K5"])))
    einmal("Strg+Klick auf einen Stab (Kette)", lambda: klick(w, app, _mitte(m, n["K0"], n["K1"]), strg=True))
    w.auswahlart_setzen("Fläche")
    einmal("Klick auf eine Fläche", lambda: klick(w, app, np.array([2.0, 11.0, 0.0])))
    w.auswahlart_setzen("Knoten")
    einmal("Auswahlfenster", lambda: fenster(w, app, np.asarray(m.nodes[n["K0"]], float) + [-1, -1, 0],
                                             np.asarray(m.nodes[n["K2"]], float) + [1, 1, 0]))
    einmal("Klick ins Leere (hebt die Auswahl auf)", lambda: klick(w, app, np.array([6.0, 6.5, 0.0])))
    w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_handbuch():
    from tests.handbuch import absatz
    t = absatz("**Klick ersetzt, Strg+Klick nimmt dazu.**")
    check("Handbuch: Klick ersetzt, Strg+Klick nimmt dazu, Stand bis zum 03.10.2026",
          "Strg" in t and "Bis zum 03.10.2026" in t and "Umschalt" in t, t[:90])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_knoten, test_stab, test_flaeche, test_fenster, test_klick_ins_leere,
              test_maske_messen_sonde, test_ein_neuzeichnen_je_klick, test_handbuch):
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
    # os._exit: kein Schliessen des Fensters, keine Rueckfrage „Ungespeicherte Änderungen“
    rc = main()
    os._exit(rc)
