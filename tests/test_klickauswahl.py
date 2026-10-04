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

Geprueft wird mit dem echten Hauptfenster (offscreen), auf zwei Wegen:

* Klicks als Qt-Mausereignisse mit den Tasten an die Ansicht (wie „Klick und
  Ziehen“ in ``tests/test_gui_smoke.py``), VTK sieht den Zeiger dort, wo der
  Klick liegt - fuer Knoten, Staebe, Flaechen, das Auswahlfenster und den
  Zeitpunkt der Tasten;
* ``_mit_tasten(Tasten, _picked, Weltpunkt)`` fuer die Arten, die den
  Weltpunkt des Klicks brauchen (Linie, Volumen, Netz, Knoten-, Linien- und
  Flaechenlager, Last): offscreen liefert ``_weltpunkt`` immer None.

Offscreen **ungeprueft** bleiben: ``_weltpunkt`` und der ``vtkPropPicker``
dahinter (offscreen immer None), der Zellenpicker ``_zellentreffer`` (braucht
ein gezeichnetes Bild; hier steht ein Ersatz, der nach der Lage des Zeigers
entscheidet) und die echte Kamera: das Renderfenster hat offscreen die Groesse
0 x 0 (gemessen), jeder Weltpunkt landete auf dem Bildpunkt (0, 0). Die
Pruefung bildet darum die Draufsicht selbst ab (``_projizieren``, 30 Bildpunkte
je Meter); Fang, Stab- und Linienfinder und das Auswahlfenster rechnen damit wie
im Programm. Das prueft die Oberflaechenpruefung auf dem Desktop.

Geprueft wird:

* Klick ersetzt die ganze Auswahl (alle Arten, auch was aus dem Baum leuchtet),
  Strg+Klick nimmt dazu, Strg+Klick auf Gewaehltes nimmt es heraus - fuer
  Knoten, Stab, Linie, Flaeche, Volumen, Netz, Knoten-, Linien- und
  Flaechenlager und Last;
* intelligente Auswahl: die Fortsetzung kommt mit, die alte Auswahl geht;
  Umschalt+Klick ersetzt mit der Kette, Strg+Umschalt+Klick nimmt sie dazu;
* Strg und Umschalt zaehlen, wenn sie beim Druecken oder beim Loslassen
  gedrueckt waren; Strg auf der zweiten Fensterecke per Rechtsklick; Doppelklick;
* Auswahlfenster: ohne Strg ersetzt, mit Strg dazu; in der Auswahlart Last
  bleibt die Auswahl;
* Klick ins Leere hebt die Auswahl auf (auch was nur aus dem Baum leuchtet),
  mit Strg bleibt sie und mit ihr der Vermerk „nur leuchten“ (Entf);
* die Tabellen markieren nach dem Klick, was gewaehlt ist;
* die unveraenderte Maske einer abgewaehlten Last geht zu, eine geaenderte bleibt;
* Klickfeld einer Maske, Messen und Sonde verhalten sich wie vorher;
* ein Klick zeichnet die Ansicht genau einmal, Kontextregister und Tabellen
  laufen einmal, nichts ruft refresh_all.

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
    # Fehler und Hinweise gemeinsam abfangen (tests/meldungen.py, Paket 9b): die
    # Liste bekommt beide, w.meldungen wertet sie getrennt aus
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste)
    _FENSTER.update(w=w, app=app)
    return w, app


#: Knoten des Pruefmodells
K = {"K0": (0, 0, 0), "K1": (4, 0, 0), "K2": (8, 0, 0), "K3": (12, 0, 0),
     "K4": (0, 5, 0), "K5": (4, 5, 0)}
#: Draufsicht der Pruefung: Bildpunkte je Meter und Lage des Ursprungs (VTK-Bildpunkte)
MASS, X0, Y0 = 30.0, 60.0, 40.0
#: Flaechen des Pruefmodells: Name -> (x von, x bis, y von, y bis)
FLAECHEN = {"F1": (0.0, 4.0, 9.0, 13.0), "F2": (8.0, 12.0, 9.0, 13.0)}
#: Volumen des Pruefmodells: Name -> seine Flaeche (fuer den Ersatz des Zellenpickers)
VOLUMEN = {"V1": "F1", "V2": "F2"}


def _draufsicht(w):
    """Die Abbildung Welt -> Bildpunkte fuer offscreen (siehe oben) und ein
    Ersatz fuer den Zellenpicker: Flaeche oder Volumen, ueber dem der Zeiger steht."""
    def projizieren(punkte):
        P = np.atleast_2d(np.asarray(punkte, float))
        if not len(P):
            return np.zeros((0, 2)), np.zeros(0, bool)
        return np.stack([X0 + MASS * P[:, 0], Y0 + MASS * P[:, 1]], axis=1), np.ones(len(P), bool)

    def objekt_am_zeiger(art):
        zp = w._zeigerposition()
        if zp is None or art not in ("Fläche", "Volumen"):
            return None
        x, y = (zp[0] - X0) / MASS, (zp[1] - Y0) / MASS
        fl = next((name for name, (x1, x2, y1, y2) in FLAECHEN.items()
                   if x1 < x < x2 and y1 < y < y2), None)
        if art == "Fläche" or fl is None:
            return fl
        return next((v for v, f in VOLUMEN.items() if f == fl and v in w.model.koerper), None)
    w._projizieren = projizieren
    w._objekt_am_zeiger = objekt_am_zeiger


def _modell(w, app):
    """Drei Staebe in einer Reihe (S1-S2-S3, eine eindeutige Kette), ein Stab
    abseits (S4), zwei vernetzte Flaechen F1 und F2 nebeneinander, ein Volumen
    auf jeder, ein Knotenlager an K0, ein Linienlager auf der Kante F1L0, ein
    Flaechenlager auf F2 und Knotenlasten an K3 und K5."""
    from statik3d.model import Member as Mb, NodalLoad, Volumenkoerper
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
    for v, fl in VOLUMEN.items():
        m.koerper[v] = Volumenkoerper(v, [fl])
    m.fix(n["K0"], "all")
    m.add_line_support([int(x) for x in m.lines["F1L0"].nodes], uz=dict(typ="rigid"))
    fl = m.add_surface_support([int(e) for e in m.flaechen["F2"].elemente], uz=dict(typ="rigid"))
    fl.flaechen = ["F2"]                   # die Symbole liegen auf der Geometrieflaeche (wie aus RFEM)
    lc = m.load_cases[m.active_case]
    lc.nodal_loads.append(NodalLoad(n["K3"], [0, 0, -1e3, 0, 0, 0]))
    lc.nodal_loads.append(NodalLoad(n["K5"], [0, 0, -2e3, 0, 0, 0]))
    w.refresh_all()
    w.auswahlart_setzen("Knoten")
    _draufsicht(w)
    app.processEvents()
    return m, n


def _maus(w, app, typ, pos, knopf, knoepfe, tasten):
    from PySide6 import QtGui, QtWidgets
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


def _zeiger(w, P):
    """VTK sieht den Zeiger auf dem Weltpunkt P - wie nach der Mausbewegung dorthin."""
    (x, y), pos = _qt(w, P)
    w.plotter.iren.interactor.SetEventInformation(int(round(x)), int(round(y)))
    return pos


def klick(w, app, P, strg=False, umschalt=False, druck=None, los=None, doppel=False):
    """Linksklick (Druecken und Loslassen ohne Zug) auf den Weltpunkt P.
    ``druck``/``los``: eigene Tasten beim Druecken und beim Loslassen; ``doppel``:
    das Druecken kommt als zweiter Druck eines Doppelklicks."""
    from PySide6 import QtCore
    pos = _zeiger(w, P)
    t = _tasten(strg, umschalt)
    druck = t if druck is None else druck
    los = t if los is None else los
    typ = QtCore.QEvent.MouseButtonDblClick if doppel else QtCore.QEvent.MouseButtonPress
    _maus(w, app, typ, pos, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, druck)
    _maus(w, app, QtCore.QEvent.MouseButtonRelease, pos, QtCore.Qt.LeftButton, QtCore.Qt.NoButton, los)


def waehlen(w, app, art, P, strg=False, umschalt=False):
    """Der Klick der Auswahlart *art* auf den Weltpunkt P ueber ``_mit_tasten``
    und ``_picked`` - fuer die Arten, die den Weltpunkt des Klicks brauchen."""
    w.auswahlart_setzen(art)
    _zeiger(w, P)
    w._mit_tasten(_tasten(strg, umschalt), w._picked, np.asarray(P, float))
    app.processEvents()


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


def _alles(w):
    """Die gesamte Auswahl samt dem, was aus dem Baum leuchtet; leere Arten fehlen."""
    d = {"knoten": _knoten(w)}
    for k in ("linien", "staebe", "flaechen", "koerper", "elemente", "lager", "lasten"):
        d[k] = list(getattr(w, "sel_" + k, None) or [])
    d["leuchtet"] = list(getattr(w, "leuchtet", None) or [])
    d["leuchtet_kontakt"] = getattr(w, "leuchtet_kontakt", "")
    return {k: v for k, v in d.items() if v}


def _vorbelegen(w, n, fall):
    """Eine Auswahl aller Arten, wie Baum und Tabelle sie hinterlassen koennen."""
    w.maskenrand.schliessen()
    w.selection = np.array([n["K4"]], int)
    w.sel_staebe[:] = ["S4"]
    w.sel_linien[:] = ["F2L2"]
    w.sel_flaechen[:] = ["F2"]
    w.sel_koerper[:] = ["V2"]
    w.sel_elemente[:] = [1]
    w.sel_lager[:] = [("lager", 0)]
    w.sel_lasten[:] = [(fall, "nodal_loads", 1)]
    w.leuchtet = [0, 1]
    w.leuchtet_kontakt = "Fuge"


def _leeren(w, app):
    w.maskenrand.schliessen()
    w.clear_selection()
    app.processEvents()


def _maske(w):
    mr = w.maskenrand
    return mr.maske.titel if mr.offen() and mr.maske is not None else None


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
    # Klick auf einen Knoten ersetzt alles, auch Lager, Lasten und was aus dem Baum leuchtet
    _vorbelegen(w, n, w.model.active_case)
    klick(w, app, m.nodes[n["K1"]])
    check("… Klick ersetzt jede Art (Lager, Lasten, Elemente, Leuchten aus dem Baum)",
          _alles(w) == {"knoten": [n["K1"]]}, str(_alles(w)))
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


def test_weitere_arten():
    """Linie, Volumen, Netz, Knoten-, Linien- und Flaechenlager, Last - ueber
    _mit_tasten und _picked (der Weltpunkt des Klicks kommt offscreen nicht)."""
    from statik3d.gui import viewport as vp
    w, app = _fenster()
    m, n = _modell(w, app)
    fall = m.active_case
    alt = w.act_klug.isChecked()
    try:
        # Linie, intelligente Auswahl an: der Ring einer Flaeche
        w.act_klug.setChecked(True)
        ring1, ring2 = [f"F1L{j}" for j in range(4)], [f"F2L{j}" for j in range(4)]
        _vorbelegen(w, n, fall)
        waehlen(w, app, "Linie", [2.0, 9.0, 0.0])
        ist = _alles(w)
        check("Linie: Klick ersetzt alles, die Kette (Ring von F1) ist gewählt",
              set(ist) == {"linien"} and sorted(ist["linien"]) == ring1, str(ist))
        waehlen(w, app, "Linie", [10.0, 9.0, 0.0], strg=True)
        check("… Strg+Klick nimmt den zweiten Ring dazu", sorted(w.sel_linien) == sorted(ring1 + ring2),
              str(w.sel_linien))
        waehlen(w, app, "Linie", [10.0, 9.0, 0.0], strg=True)
        check("… Strg+Klick auf Gewähltes nimmt den Ring heraus", sorted(w.sel_linien) == ring1, str(w.sel_linien))
        waehlen(w, app, "Linie", [2.0, 9.0, 0.0])
        check("… Klick ohne Strg auf den gewählten Ring: er bleibt gewählt", sorted(w.sel_linien) == ring1,
              str(w.sel_linien))
        # Volumen
        _vorbelegen(w, n, fall)
        waehlen(w, app, "Volumen", [2.0, 11.0, 0.0])
        check("Volumen: Klick ersetzt alles", _alles(w) == {"koerper": ["V1"]}, str(_alles(w)))
        waehlen(w, app, "Volumen", [10.0, 11.0, 0.0], strg=True)
        check("… Strg+Klick nimmt V2 dazu", w.sel_koerper == ["V1", "V2"], str(w.sel_koerper))
        waehlen(w, app, "Volumen", [2.0, 11.0, 0.0], strg=True)
        check("… Strg+Klick auf das gewählte V1 nimmt es heraus", _alles(w) == {"koerper": ["V2"]},
              str(_alles(w)))
        # Netz (der Elementfinder steht fuer den Zellenpicker)
        alt_el = w._element_am_zeiger
        try:
            _vorbelegen(w, n, fall)
            w._element_am_zeiger = lambda: 5
            waehlen(w, app, "Netz", [2.0, 11.0, 0.0])
            check("Netz: Klick ersetzt alles", _alles(w) == {"elemente": [5]}, str(_alles(w)))
            w._element_am_zeiger = lambda: 6
            waehlen(w, app, "Netz", [2.0, 11.0, 0.0], strg=True)
            check("… Strg+Klick nimmt Element 6 dazu", _alles(w) == {"elemente": [5, 6]}, str(_alles(w)))
            w._element_am_zeiger = lambda: 5
            waehlen(w, app, "Netz", [2.0, 11.0, 0.0], strg=True)
            check("… Strg+Klick auf das gewählte Element 5 nimmt es heraus", _alles(w) == {"elemente": [6]},
                  str(_alles(w)))
        finally:
            w._element_am_zeiger = alt_el
        # Lager: Knotenlager an K0, Linienlager auf F1L0, Flaechenlager auf F2
        size = m.characteristic_size()
        p_ll = vp.lager_punkte(m, m.line_supports[0], size, w.lagerdichte)[0][0]
        p_fl = vp.lager_punkte(m, m.surface_supports[0], size, w.lagerdichte)[0][0]
        _vorbelegen(w, n, fall)
        w.sel_lager[:] = [("flaechenlager", 0)]
        waehlen(w, app, "Lager", m.nodes[n["K0"]])
        check("Knotenlager: Klick ersetzt alles (auch das Flächenlager)", _alles(w) == {"lager": [("lager", 0)]},
              str(_alles(w)))
        waehlen(w, app, "Lager", p_ll, strg=True)
        check("Linienlager: Strg+Klick nimmt es dazu", w.sel_lager == [("lager", 0), ("linienlager", 0)],
              str(w.sel_lager))
        waehlen(w, app, "Lager", p_fl, strg=True)
        check("Flächenlager: Strg+Klick nimmt es dazu",
              w.sel_lager == [("lager", 0), ("linienlager", 0), ("flaechenlager", 0)], str(w.sel_lager))
        waehlen(w, app, "Lager", p_ll, strg=True)
        check("… Strg+Klick auf das gewählte Linienlager nimmt es heraus",
              w.sel_lager == [("lager", 0), ("flaechenlager", 0)], str(w.sel_lager))
        waehlen(w, app, "Lager", p_fl)
        check("Flächenlager: Klick ohne Strg: nur das Flächenlager", _alles(w) == {"lager": [("flaechenlager", 0)]},
              str(_alles(w)))
        # Last: zwei Knotenlasten
        _vorbelegen(w, n, fall)
        w.auswahlart_setzen("Last")
        w.redraw()
        app.processEvents()
        punkte = [x for x in (getattr(w, "_lastpunkte", None) or []) if x[0] == "nodal_loads"]
        if check("Last: die zwei Knotenlasten stehen als Symbole im Bild", len(punkte) >= 2, str(len(punkte))):
            (liste, k, P), (liste2, k2, P2) = punkte[0][:3], punkte[1][:3]
            waehlen(w, app, "Last", P)
            check("Last: Klick ersetzt alles", _alles(w) == {"lasten": [(fall, liste, int(k))]}, str(_alles(w)))
            waehlen(w, app, "Last", P2, strg=True)
            check("… Strg+Klick nimmt die zweite Last dazu, rechts steht ihre Maske",
                  w.sel_lasten == [(fall, liste, int(k)), (fall, liste2, int(k2))]
                  and _maske(w) == f"Knotenlast K{m.load_cases[fall].nodal_loads[int(k2)].node} ({fall})",
                  f"{w.sel_lasten} {_maske(w)!r}")
            waehlen(w, app, "Last", P2, strg=True)
            check("… Strg+Klick auf die gewählte zweite Last nimmt sie heraus, Statuszeile in der Einzahl",
                  w.sel_lasten == [(fall, liste, int(k))] and w.lbl_sel.text() == "1 Last ausgewählt",
                  f"{w.sel_lasten} {w.lbl_sel.text()!r}")
    finally:
        w.act_klug.setChecked(alt)
        w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_lastmaske():
    """Die Maske einer Last, die nicht mehr gewaehlt ist: unveraendert geht sie
    zu, geaendert bleibt sie stehen."""
    w, app = _fenster()
    m, n = _modell(w, app)
    fall = m.active_case
    _leeren(w, app)
    w.auswahlart_setzen("Last")
    w.redraw()
    app.processEvents()
    punkte = [x for x in (getattr(w, "_lastpunkte", None) or []) if x[0] == "nodal_loads"]
    if not check("Lastmaske: zwei Knotenlasten im Bild", len(punkte) >= 2, str(len(punkte))):
        return
    P, P2 = punkte[0][2], punkte[1][2]
    try:
        waehlen(w, app, "Last", P)
        offen = _maske(w)
        waehlen(w, app, "Knoten", m.nodes[n["K1"]])
        check("Klick auf einen Knoten: die unveränderte Lastmaske geht zu",
              offen is not None and _maske(w) is None and _knoten(w) == [n["K1"]], f"{offen!r} -> {_maske(w)!r}")
        waehlen(w, app, "Last", P)
        waehlen(w, app, "Last", P2, strg=True)
        waehlen(w, app, "Last", P2, strg=True)
        check("Strg+Klick nimmt die Last heraus: ihre unveränderte Maske geht zu",
              len(w.sel_lasten) == 1 and _maske(w) is None, f"{w.sel_lasten} {_maske(w)!r}")
        waehlen(w, app, "Last", P)
        mk = w.maskenrand.maske
        mk.setzen("Fz", -7.0)
        app.processEvents()
        waehlen(w, app, "Knoten", m.nodes[n["K1"]])
        check("… eine geänderte Lastmaske bleibt stehen (nicht übernommene Werte gehen nicht verloren)",
              w.maskenrand.maske is mk and w.maskenrand.offen() and not w.sel_lasten,
              f"{_maske(w)!r} {w.sel_lasten}")
    finally:
        w.maskenrand.schliessen()
        w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_tasten_zeitpunkt():
    """Strg und Umschalt beim Druecken oder Loslassen; Rechtsklick als zweite
    Fensterecke mit Strg; Doppelklick; nach einer Ausnahme stehen keine Tasten."""
    from PySide6 import QtCore
    w, app = _fenster()
    m, n = _modell(w, app)
    T0, TS = _tasten(), _tasten(strg=True)
    _leeren(w, app)
    klick(w, app, m.nodes[n["K1"]])
    klick(w, app, m.nodes[n["K2"]], druck=T0, los=TS)
    check("Strg nur beim Loslassen: zählt als Strg (K1 und K2)", _knoten(w) == sorted([n["K1"], n["K2"]]),
          str(_knoten(w)))
    klick(w, app, m.nodes[n["K3"]], druck=TS, los=T0)
    check("Strg nur beim Drücken: zählt ebenso als Strg (K1, K2 und K3)",
          _knoten(w) == sorted([n["K1"], n["K2"], n["K3"]]), str(_knoten(w)))
    klick(w, app, m.nodes[n["K4"]])
    check("… danach ein Klick ohne Taste: nur K4 (die Taste vom Drücken bleibt nicht stehen)",
          _knoten(w) == [n["K4"]], str(_knoten(w)))
    alt = w.act_klug.isChecked()
    w.act_klug.setChecked(False)
    w.auswahlart_setzen("Stab")
    try:
        klick(w, app, _mitte(m, n["K1"], n["K2"]), druck=_tasten(umschalt=True), los=T0)
        check("Umschalt nur beim Drücken (Schalter aus): die Kette S1–S3", sorted(w.sel_staebe) == ["S1", "S2", "S3"],
              str(w.sel_staebe))
    finally:
        w.act_klug.setChecked(alt)
        w.auswahlart_setzen("Knoten")
    # Ausnahme waehrend des Klicks: keine Taste bleibt stehen
    alt_picked = w._picked

    def kaputt(*a, **k):
        raise RuntimeError("Absicht")
    w._picked = kaputt
    try:
        klick(w, app, m.nodes[n["K1"]], strg=True, umschalt=True)
    finally:
        w._picked = alt_picked
    check("nach einer Ausnahme im Klick stehen Strg und Umschalt nicht mehr",
          not getattr(w, "_klick_strg", False) and not getattr(w, "_klick_umschalt", False),
          f"{getattr(w, '_klick_strg', None)} {getattr(w, '_klick_umschalt', None)}")
    klick(w, app, m.nodes[n["K2"]])
    check("… der nächste Klick ohne Taste ersetzt (nur K2)", _knoten(w) == [n["K2"]], str(_knoten(w)))
    # Rechtsklick als zweite Ecke des Auswahlfensters, mit Strg
    _leeren(w, app)
    w.selection = np.array([n["K4"]], int)
    p1 = _zeiger(w, np.asarray(m.nodes[n["K0"]], float) + [-1, -1, 0])
    p2 = _zeiger(w, np.asarray(m.nodes[n["K2"]], float) + [1, 1, 0])
    _maus(w, app, QtCore.QEvent.MouseButtonPress, p1, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, T0)
    for q in (QtCore.QPointF(0.5 * (p1.x() + p2.x()), 0.5 * (p1.y() + p2.y())), p2):
        _maus(w, app, QtCore.QEvent.MouseMove, q, QtCore.Qt.NoButton, QtCore.Qt.LeftButton, T0)
    ecke = w._fenster_ecke is not None
    _maus(w, app, QtCore.QEvent.MouseButtonPress, p2, QtCore.Qt.RightButton,
          QtCore.Qt.LeftButton | QtCore.Qt.RightButton, TS)
    check("Fenster, mit Strg+Rechtsklick abgeschlossen: kommt dazu (K4 bleibt)",
          ecke and _knoten(w) == sorted([n["K0"], n["K1"], n["K2"], n["K4"]]), f"Ecke {ecke} {_knoten(w)}")
    _maus(w, app, QtCore.QEvent.MouseButtonRelease, p2, QtCore.Qt.RightButton, QtCore.Qt.LeftButton, T0)
    _maus(w, app, QtCore.QEvent.MouseButtonRelease, p2, QtCore.Qt.LeftButton, QtCore.Qt.NoButton, T0)
    check("… das Loslassen danach ändert nichts", _knoten(w) == sorted([n["K0"], n["K1"], n["K2"], n["K4"]]),
          str(_knoten(w)))
    # Doppelklick: der erste Klick waehlt, der zweite Druck tut nichts
    _leeren(w, app)
    w.selection = np.array([n["K4"]], int)
    klick(w, app, m.nodes[n["K1"]])
    klick(w, app, m.nodes[n["K1"]], doppel=True)
    check("Doppelklick auf K1: nur K1 gewählt", _knoten(w) == [n["K1"]], str(_knoten(w)))
    klick(w, app, m.nodes[n["K2"]], strg=True)
    klick(w, app, m.nodes[n["K2"]], strg=True, doppel=True)
    check("Strg+Doppelklick auf K2: K2 kommt dazu und bleibt", _knoten(w) == sorted([n["K1"], n["K2"]]),
          str(_knoten(w)))
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
    # Auswahlart Last: das Fenster fasst keine Lasten - die Auswahl bleibt
    w.selection = np.array([n["K4"]], int)
    w.sel_staebe.append("S4")
    w.auswahlart_setzen("Last")
    try:
        fenster(w, app, [-1.0, -1.0, 0.0], [13.0, 14.0, 0.0])
        check("Auswahlart Last: ein Fenster über alles lässt die Auswahl stehen und sagt es",
              _knoten(w) == [n["K4"]] and w.sel_staebe == ["S4"] and not w.sel_lasten
              and "Last" in w.statusBar().currentMessage(), f"{_alles(w)} {w.statusBar().currentMessage()!r}")
    finally:
        w.auswahlart_setzen("Knoten")
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
    w.leuchtet = [0, 1]
    w.leuchtet_kontakt = "Fuge"
    klick(w, app, leer)
    check("Klick ins Leere nimmt auch, was nur aus dem Baum leuchtet",
          not w.leuchtet and not w.leuchtet_kontakt, f"{w.leuchtet} {w.leuchtet_kontakt!r}")
    _leeren(w, app)


def test_vermerk_nur_leuchten():
    """Nach einer Zeile der Lasttabelle leuchtet das Ziel nur, gewaehlt ist die
    Last (Entf loescht nur sie). Was die Auswahl nicht aendert, laesst den Vermerk."""
    w, app = _fenster()
    m, n = _modell(w, app)
    _leeren(w, app)
    w._tabelle_last(0)
    app.processEvents()
    vorher = w._loeschgruppen()
    check("Lasttabelle: Ziel leuchtet, Entf löscht nur die Last", [a for a, _ in vorher] == ["last"],
          str(vorher))
    klick(w, app, np.array([6.0, 6.5, 0.0]), strg=True)
    check("Strg+Klick ins Leere ändert nicht, was Entf löscht", w._loeschgruppen() == vorher,
          f"{vorher} -> {w._loeschgruppen()}")
    w.act_sonde.setChecked(True)
    try:
        klick(w, app, m.nodes[n["K1"]])
        check("ein Sondenklick ebenso nicht", w._loeschgruppen() == vorher and len(w.sonden) == 1,
              f"{w._loeschgruppen()} {len(w.sonden)}")
    finally:
        w.act_sonde.setChecked(False)
        w.sonden = []
    klick(w, app, m.nodes[n["K1"]])
    check("ein Klick auf einen Knoten wählt ihn wirklich: Entf löscht ihn", w._loeschgruppen() == [("knoten", [n["K1"]])],
          str(w._loeschgruppen()))
    _leeren(w, app)


def test_tabelle_folgt():
    """Nach dem Klick markieren die Tabellen, was gewaehlt ist - nicht mehr die
    Zeile davor."""
    w, app = _fenster()
    m, n = _modell(w, app)
    _leeren(w, app)
    t = w.tbl_knoten

    def markiert():
        zeilen = sorted({i.row() for i in t.view.selectionModel().selectedRows()})
        return sorted(int(t.filter.index(r, 0).data()) for r in zeilen)

    r3 = next(r for r in range(t.filter.rowCount()) if str(t.filter.index(r, 0).data()) == str(n["K3"]))
    t.view.selectRow(r3)
    t._geklickt(t.filter.index(r3, 0))
    app.processEvents()
    vorher = (_knoten(w), markiert())
    klick(w, app, m.nodes[n["K1"]])
    check("Knotentabelle: nach dem Klick auf K1 ist K1 markiert, nicht mehr K3",
          vorher == ([n["K3"]], [n["K3"]]) and markiert() == [n["K1"]], f"vorher {vorher}, jetzt {markiert()}")
    klick(w, app, m.nodes[n["K2"]], strg=True)
    check("… nach Strg+Klick auf K2: K1 und K2 markiert", markiert() == sorted([n["K1"], n["K2"]]), str(markiert()))
    klick(w, app, np.array([6.0, 6.5, 0.0]))
    check("… nach dem Klick ins Leere: keine Zeile markiert", markiert() == [], str(markiert()))
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
    # Messen: jeder Klick gibt der Maske einen Punkt; nach dem zweiten steht die Messung
    w.sel_staebe.append("S4")
    w.messen("abstand")
    app.processEvents()
    mk = w.maskenrand.maske
    nn0 = m.nn
    klick(w, app, m.nodes[n["K1"]])
    punkte_1 = [list(np.round(p, 6)) for p in mk.gewaehlt_punkte]
    klick(w, app, m.nodes[n["K2"]])
    messung = w.messungen[-1] if w.messungen else {}
    check("Messen: zwei Klicks, zwei Punkte für die Maske (K1, K2), daraus die Messung, kein Knoten neu",
          punkte_1 == [list(np.round(m.nodes[n["K1"]], 6))] and len(w.messungen) == 1
          and np.allclose(np.asarray(messung.get("punkte"), float), [m.nodes[n["K1"]], m.nodes[n["K2"]]])
          and m.nn == nn0, f"{punkte_1} {messung.get('punkte')} {m.nn}/{nn0}")
    check("… die Auswahl (Knoten K4, Stab S4) bleibt, wie sie war",
          w.sel_staebe == ["S4"] and _knoten(w) == [n["K4"]], f"{w.sel_staebe} {_knoten(w)}")
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

    def einmal(titel, f):
        app.processEvents()
        with _Zaehler(w) as z:
            f()
            app.processEvents()
        ok = (z["redraw"] == 1 and z["_aufbauen"] == 1 and z["render"] == 1 and z["refresh_all"] == 0
              and z["_kontext_abgleichen"] == 1 and z["_info_zeigen"] == 1
              and z["_tabellen_markieren"] == 1 and z["_refresh_baum"] == 0
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
    check("… Strg beim Drücken oder Loslassen, Lasten schon vorher ersetzt, die Lastmaske geht zu",
          "beim Drücken oder beim Loslassen" in t and "Bei Lasten ersetzte" in t
          and "unveränderte Maske" in t, t[-160:])
    last = absatz("**Lasten anklicken.**")
    check("Handbuch: die Zeile der Lastentabelle lässt die anderen Arten stehen",
          "anderer Arten bleiben stehen" in last, last[-160:])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_knoten, test_stab, test_flaeche, test_weitere_arten, test_lastmaske, test_tasten_zeitpunkt,
              test_fenster, test_klick_ins_leere, test_vermerk_nur_leuchten, test_tabelle_folgt,
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
