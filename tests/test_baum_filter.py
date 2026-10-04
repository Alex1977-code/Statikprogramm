"""
Ansicht -> Baum und Filterzeile (Teilpaket 8d der Oberflaechenplanung, 03.10.2026).

Plan vom 24.09.2026, Paket 8: „Ansicht → Baum: Eine Auswahl in der Ansicht
markiert den Eintrag im Baum, ohne ihm die Tastatur zu geben“ und
„Filterzeile: Sie steht über dem Baum (Strg+F)“. Plan vom 01.10.2026, Zeile
8d: ohne Fokuswechsel und mit Suchverzeichnis statt linearer Suche ueber bis
zu 20 000 Eintraege. Entscheidung der Hauptsitzung zu Strg+F: hat der
Modellbaum oder seine Filterzeile den Fokus, oeffnet Strg+F die Filterzeile,
sonst bleibt es die Befehlssuche (Paket 12a).

Stand davor (am Quelltext gelesen, 2b4c64c): ein Klick in der Ansicht liess den
Baum stehen; nur „Im Baum zeigen“ (Rechtsklick, 14c) suchte den Eintrag, und
zwar mit einer Schleife ueber alle Eintraege des Baums (``_alle_eintraege``),
und legte die Tastatur in den Baum. Einen Eintrag hinter der Sammelzeile
„… N weitere“ fand die Suche nicht. Eine Filterzeile gab es nicht.

Geprueft wird der Baum allein (schnell, mit Zaehlung der Zugriffe auf Zeilen)
und das echte Hauptfenster offscreen mit Mausereignissen an die Ansicht wie in
``tests/test_klickauswahl.py`` (die Draufsicht bildet die Pruefung selbst ab,
das Renderfenster ist offscreen 0 x 0):

* ein Klick in der Ansicht waehlt die Baumzeile und macht sie sichtbar, die
  Tastatur bleibt in der Ansicht; Strg+Klick markiert mehrere, ein Klick ins
  Leere hebt die Markierung auf; ein Netzknoten markiert die Zaehlzeile;
* in einem gekuerzten Zweig wird die Zeile nachgeladen, nie still nichts;
* dabei wird keine Maske angelegt, geoeffnet oder an der Leiste
  „Übernehmen | Verwerfen“ angehalten, und der Baum meldet keinen Klick;
* das Suchverzeichnis: ``eintrag_waehlen`` greift nicht auf jede Zeile zu und
  ist nach jedem Neuaufbau gueltig;
* die Filterzeile: Teiltext ohne Gross/Klein, Eltern sichtbar und aufgeklappt,
  Esc und ein leeres Feld stellen den Aufklappzustand wieder her, der Filter
  ueberlebt einen Neuaufbau und findet auch Eintraege hinter „… N weitere“;
* Strg+F: im Baum und in der Filterzeile die Filterzeile, in der Ansicht und
  in einer Maske die Befehlssuche; die Liste der Tastenkuerzel und das
  Handbuch nennen beides.

Nachbesserung nach der Gegenpruefung von 4976a91 (NACHBESSERUNG-8D.md, Abnahme
D1 bis D13): der Baum wirkt nie auf etwas, das der Filter ausblendet (G1), der
Filter trifft Eintraege und Zweige, nie Wurzel und Gruppen (G2), die Markierung
folgt jeder Auswahl der Ansicht (G3), getippt wird nach einer Ruhezeit gefiltert
und nachgeladene Zeilen stehen in der Nummernfolge (G4), Kontextmenues werden
wirksam abgefangen und Eingaben als Tastenereignisse getippt (G5).

Aufruf:  python -m tests.test_baum_filter
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
    tempfile.mkdtemp(prefix="statik3d_baum_filter_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}
#: modale Fenster, die sich oeffnen wollten (es darf keines geben)
MODAL = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _ruhe(app, n=3):
    for _ in range(n):
        app.processEvents()


def _modal_abfangen():
    """Kein modales Fenster bleibt stehen: jedes wird aufgezeichnet und sofort
    beantwortet."""
    from PySide6 import QtWidgets
    B = QtWidgets.QMessageBox

    def melden(art, rueck):
        def f(*a, **_k):
            MODAL.append((art, next((str(x) for x in a[2:3]), "")))
            return rueck
        return f
    B.critical = melden("critical", B.Ok)
    B.warning = melden("warning", B.Ok)
    B.information = melden("information", B.Ok)
    B.question = melden("question", B.No)
    QtWidgets.QDialog.exec = lambda self, *a, **k: (MODAL.append(("exec", type(self).__name__)), 0)[1]
    # Kontextmenues: nicht hier - der Klassen-Patch QMenu.exec greift unter
    # PySide6 6.11.2 nicht; _menues_abfangen tauscht die Klasse (Nachbesserung 8d)


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from statik3d.gui.main import MainWindow
    app = _app()
    _modal_abfangen()
    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    _ruhe(app)
    w._fragen_knoepfe = lambda *a, **k: True
    w._bestaetigen = lambda *a, **k: True
    w._frage_speichern_verwerfen = lambda *a, **k: "verwerfen"
    w.fehler_liste = []
    w.error = lambda msg, *a, **k: w.fehler_liste.append(str(msg))
    _FENSTER.update(w=w, app=app)
    return w, app


# ---------------------------------------------------------------------------
# Hilfen ueber Datenrollen - sie laufen auch am Stand vor 8d (Gegenprobe)
# ---------------------------------------------------------------------------
def _element(it):
    from PySide6 import QtCore
    art = str(it.data(0, QtCore.Qt.UserRole) or "")
    key = it.data(0, QtCore.Qt.UserRole + 1)
    return art, (str(key) if key is not None else it.text(0))


def _alle(baum):
    from PySide6 import QtWidgets
    out = []
    it = QtWidgets.QTreeWidgetItemIterator(baum)
    while it.value():
        out.append(it.value())
        it += 1
    return out


def _finden(baum, art, key):
    return next((i for i in _alle(baum) if _element(i) == (str(art), str(key))), None)


def _zweig(baum, text, art=None):
    from PySide6 import QtCore
    return next((i for i in _alle(baum) if i.text(0) == text and i.data(0, QtCore.Qt.UserRole + 1) is None
                 and (art is None or _element(i)[0] == art)), None)


def _pfad(it):
    teile = []
    while it is not None:
        teile.append(_element(it))
        it = it.parent()
    return tuple(reversed(teile))


def _sichtbar(baum, it) -> bool:
    """Die Zeile steht im Bild: sie und alle Eltern sind nicht ausgeblendet,
    die Eltern sind aufgeklappt, und ihr Rechteck liegt im sichtbaren Teil."""
    if it is None or it.isHidden():
        return False
    p = it.parent()
    while p is not None:
        if p.isHidden() or not p.isExpanded():
            return False
        p = p.parent()
    r = baum.visualItemRect(it)
    return r.isValid() and baum.viewport().rect().intersects(r)


def _gewaehlt(baum):
    return sorted(_element(i) for i in baum.selectedItems())


def _aktuell(baum):
    it = baum.currentItem()
    return _element(it) if it is not None else None


def _aufklappung(baum) -> dict:
    return {_pfad(i): i.isExpanded() for i in _alle(baum) if i.childCount()}


def _baum(hoehe=400):
    from statik3d.gui import design as dsg
    app = _app()
    b = dsg.Modellbaum()
    b.resize(320, hoehe)
    b.show()
    app.processEvents()
    return b, app


class _Zaehler:
    """Zaehlt die Zugriffe auf Baumzeilen (wie tests.test_baum_ruhig: nur
    nicht-virtuelle Methoden, sonst ruft Shiboken die Python-Fassung aus C++)."""
    NAMEN = ("isExpanded", "child", "childCount", "text", "parent")

    def __init__(self):
        self.n = 0
        self._orig = {}

    def __enter__(self):
        from PySide6 import QtWidgets
        for name in self.NAMEN:
            f = getattr(QtWidgets.QTreeWidgetItem, name)
            self._orig[name] = f

            def g(item, *a, _f=f, **k):
                self.n += 1
                return _f(item, *a, **k)
            setattr(QtWidgets.QTreeWidgetItem, name, g)
        return self

    def __exit__(self, *_a):
        from PySide6 import QtWidgets
        for name, f in self._orig.items():
            setattr(QtWidgets.QTreeWidgetItem, name, f)


class _Spion:
    """Empfaenger fuer die Signale des Baums - eine gebundene Methode, die die
    Pruefung wieder trennt."""

    def __init__(self):
        self.gesehen = []

    def melden(self, *a):
        self.gesehen.append(a)


# ---------------------------------------------------------------------------
# 1. Suchverzeichnis: der Baum allein
# ---------------------------------------------------------------------------
def test_verzeichnis_statt_suche():
    """``eintrag_waehlen`` geht nicht ueber alle Zeilen (am Drehlager bis zu
    20 000 je Liste) und ist nach jedem Neuaufbau gueltig."""
    from statik3d.model import Model
    m = Model()
    m.name = "Viele Knoten"
    m.nodes = np.random.rand(5000, 3)
    b, app = _baum()
    b.fuellen(m)
    app.processEvents()
    with _Zaehler() as z:
        ok = b.eintrag_waehlen("knoten", "4990")
    check("eintrag_waehlen findet K4990 unter 5000 Knoten",
          ok and _aktuell(b) == ("knoten", "4990") and _gewaehlt(b) == [("knoten", "4990")], str(_aktuell(b)))
    check("… mit weniger als 50 Zugriffen auf Zeilen (keine Schleife über alle Einträge)",
          z.n < 50, f"{z.n} Zugriffe")
    check("… und macht die Zeile sichtbar", _sichtbar(b, b.currentItem()))
    # nach dem Neuaufbau: ein neuer Knoten ist zu finden, ein geloeschter nicht mehr
    m.nodes = np.vstack([m.nodes, [[9.0, 9.0, 9.0]]])
    b.fuellen(m)
    app.processEvents()
    with _Zaehler() as z:
        ok = b.eintrag_waehlen("knoten", "5000")
    check("nach dem Neuaufbau findet das Verzeichnis den neuen Knoten K5000, ohne Schleife",
          ok and _aktuell(b) == ("knoten", "5000") and z.n < 50, f"{ok}, {z.n} Zugriffe")
    m.nodes = m.nodes[:100]
    b.fuellen(m)
    app.processEvents()
    check("… und meldet einen Knoten, den es nicht mehr gibt, als nicht gefunden",
          b.eintrag_waehlen("knoten", "4990") is False)
    b.close()


def test_gekuerzter_zweig_baum():
    """Hinter der Sammelzeile „… N weitere“: die Zeile wird nachgeladen."""
    from statik3d.gui import design as dsg
    from statik3d.model import Model
    m = Model()
    m.name = "Kurz"
    m.nodes = np.array([[float(i), 0.0, 0.0] for i in range(12)])
    for i in range(10):
        m.add_line(f"L{i + 1}", [i, i + 1])
    alt = dsg.BAUM_MAX
    dsg.BAUM_MAX = 3
    b, app = _baum()
    try:
        b.fuellen(m)
        app.processEvents()
        kn = _zweig(b, "Knoten", "knoten")
        sammel = [kn.child(i).text(0) for i in range(kn.childCount())]
        check("Vorbereitung: der Zweig Knoten zeigt drei Einträge und „… 9 weitere“",
              sammel == ["K0", "K1", "K2", "… 9 weitere"], str(sammel))
        ok = b.eintrag_waehlen("knoten", "7")
        it = b.currentItem()
        check("ein Knoten hinter „… 9 weitere“ (K7) wird nachgeladen und gewählt, nicht still nichts",
              ok and it is not None and _element(it) == ("knoten", "7") and it.parent() is kn
              and it.text(0) == "K7" and "x =" in it.toolTip(0), str(_aktuell(b)))
        texte = [kn.child(i).text(0) for i in range(kn.childCount())]
        check("… er steht vor der Sammelzeile, und die zählt einen weniger",
              texte == ["K0", "K1", "K2", "K7", "… 8 weitere"], str(texte))
        ok = b.eintrag_waehlen("linie", "L9")
        check("… ebenso eine Linie (L9)", ok and _aktuell(b) == ("linie", "L9"), str(_aktuell(b)))
        check("… ein Eintrag, den es nicht gibt, bleibt „nicht gefunden“ (K99, L99)",
              b.eintrag_waehlen("knoten", "99") is False and b.eintrag_waehlen("linie", "L99") is False)
        b.eintrag_waehlen("knoten", "7")
        b.fuellen(m)
        app.processEvents()
        check("nach dem Neuaufbau ist der nachgeladene Knoten K7 wieder gewählt",
              _aktuell(b) == ("knoten", "7") and _gewaehlt(b) == [("knoten", "7")], str(_aktuell(b)))
    finally:
        dsg.BAUM_MAX = alt
        b.close()


# ---------------------------------------------------------------------------
# 2. Ansicht -> Baum im echten Fenster
# ---------------------------------------------------------------------------
#: Knoten des Pruefmodells (wie tests.test_klickauswahl)
K = {"K0": (0, 0, 0), "K1": (4, 0, 0), "K2": (8, 0, 0), "K3": (12, 0, 0),
     "K4": (0, 5, 0), "K5": (4, 5, 0)}
MASS, X0, Y0 = 30.0, 60.0, 40.0
FLAECHEN = {"F1": (0.0, 4.0, 9.0, 13.0), "F2": (8.0, 12.0, 9.0, 13.0)}


def _draufsicht(w):
    """Die Abbildung Welt -> Bildpunkte fuer offscreen und ein Ersatz fuer den
    Zellenpicker (wie tests.test_klickauswahl)."""
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
    """Vier Staebe (S1-S3 in einer Reihe, S4 abseits), zwei vernetzte Flaechen
    F1 und F2 mit Netzknoten im Innern, ein Knotenlager an K0."""
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
    m.fix(n["K0"], "all")
    w.refresh_all()
    w.auswahlart_setzen("Knoten")
    _draufsicht(w)
    _ruhe(app)
    return m, n


def _qt(w, P):
    from PySide6 import QtCore
    xy, _s = w._projizieren(np.atleast_2d(np.asarray(P, float)))
    x, y = float(xy[0, 0]), float(xy[0, 1])
    s = w._pixelmass()
    h = w.plotter.interactor.height()
    return (x, y), QtCore.QPointF(x / s, h - 1 - y / s)


def _maus(w, app, typ, pos, knopf, knoepfe, tasten):
    from PySide6 import QtGui, QtWidgets
    ev = QtGui.QMouseEvent(typ, pos, pos, knopf, knoepfe, tasten)
    QtWidgets.QApplication.sendEvent(w.plotter.interactor, ev)
    app.processEvents()


def klick(w, app, P, strg=False):
    """Linksklick (Druecken und Loslassen ohne Zug) auf den Weltpunkt P."""
    from PySide6 import QtCore
    (x, y), pos = _qt(w, P)
    w.plotter.iren.interactor.SetEventInformation(int(round(x)), int(round(y)))
    t = QtCore.Qt.ControlModifier if strg else QtCore.Qt.NoModifier
    _maus(w, app, QtCore.QEvent.MouseButtonPress, pos, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, t)
    _maus(w, app, QtCore.QEvent.MouseButtonRelease, pos, QtCore.Qt.LeftButton, QtCore.Qt.NoButton, t)


def _fokus():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.focusWidget()


def _ansicht_fokussieren(w, app):
    w.activateWindow()
    w.plotter.interactor.setFocus()
    _ruhe(app)


def test_ansicht_waehlt_baumzeile():
    w, app = _fenster()
    m, n = _modell(w, app)
    b = w.baum
    _ansicht_fokussieren(w, app)
    b.clearSelection()
    klick(w, app, m.nodes[n["K1"]])
    check("Vorbereitung: der Klick wählt K1 in der Ansicht", sorted(int(i) for i in w.selection) == [n["K1"]],
          str(list(w.selection)))
    check("Ansicht → Baum: der Klick auf K1 wählt die Baumzeile K1",
          _aktuell(b) == ("knoten", str(n["K1"])) and _gewaehlt(b) == [("knoten", str(n["K1"]))],
          f"aktuell {_aktuell(b)}, gewählt {_gewaehlt(b)}")
    check("… und macht sie sichtbar (Zweig aufgeklappt, Zeile im Bild)", _sichtbar(b, b.currentItem()))
    check("… ohne Fokuswechsel: die Tastatur bleibt in der Ansicht",
          _fokus() is w.plotter.interactor and not b.hasFocus(), str(_fokus()))
    # Stab
    klick(w, app, 0.5 * (m.nodes[n["K1"]] + m.nodes[n["K2"]]))
    check("Klick auf den Stab S2: die Baumzeile S2 ist gewählt, sonst nichts",
          w.sel_staebe == ["S2"] and _aktuell(b) == ("stab", "S2") and _gewaehlt(b) == [("stab", "S2")],
          f"{w.sel_staebe}, {_gewaehlt(b)}")
    klick(w, app, 0.5 * (m.nodes[n["K4"]] + m.nodes[n["K5"]]), strg=True)
    check("… Strg+Klick auf S4: beide Zeilen gewählt, S4 ist die aktuelle",
          _gewaehlt(b) == [("stab", "S2"), ("stab", "S4")] and _aktuell(b) == ("stab", "S4"),
          f"{_gewaehlt(b)}, {_aktuell(b)}")
    check("… die Tastatur bleibt in der Ansicht", _fokus() is w.plotter.interactor, str(_fokus()))
    # Flaeche (die Mitte von F1 trifft in der Auswahlart Knoten einen Netzknoten - darum Fläche)
    w.auswahlart_setzen("Fläche")
    klick(w, app, (1.5, 10.5, 0.0))
    check("Klick auf die Fläche F1: die Baumzeile F1 ist gewählt",
          w.sel_flaechen == ["F1"] and _aktuell(b) == ("geoflaeche", "F1") and _sichtbar(b, b.currentItem()),
          f"{w.sel_flaechen}, {_aktuell(b)}")
    # Netzknoten: er steht nicht einzeln im Baum - die Zaehlzeile „Netzknoten“
    w.auswahlart_setzen("Knoten")
    innen = int(np.argmin(np.linalg.norm(m.nodes - np.array([2.0, 11.0, 0.0]), axis=1)))
    from statik3d import knotenrollen as kr
    check("Vorbereitung: der Knoten in der Mitte von F1 ist ein Netzknoten",
          innen not in set(int(i) for i in kr.konstruktionsknoten(m)), str(innen))
    w._ziel_waehlen(("knoten", innen))
    _ruhe(app)
    it = b.currentItem()
    check("ein Netzknoten markiert die Zählzeile „FE-Netz → Netzknoten“, nicht still nichts",
          it is not None and _element(it)[0] == "netzknoten" and it.isSelected() and _sichtbar(b, it),
          str(_aktuell(b)))
    # Klick ins Leere
    klick(w, app, (30.0, 30.0, 0.0))
    check("Klick ins Leere: die Ansicht hebt die Auswahl auf, der Baum markiert nichts mehr",
          not len(w.selection) and not _gewaehlt(b), str(_gewaehlt(b)))
    check("… die Tastatur bleibt in der Ansicht", _fokus() is w.plotter.interactor, str(_fokus()))


def test_ansicht_gekuerzter_zweig():
    """Liegt der Knoten hinter „… N weitere“, wird seine Zeile nachgeladen."""
    from statik3d.gui import design as dsg
    w, app = _fenster()
    m, n = _modell(w, app)
    alt = dsg.BAUM_MAX
    dsg.BAUM_MAX = 3
    try:
        w.refresh_all()
        _ruhe(app)
        b = w.baum
        kn = _zweig(b, "Knoten", "knoten")
        sammel = kn.child(kn.childCount() - 1).text(0) if kn is not None and kn.childCount() else ""
        check("Vorbereitung: der Zweig Knoten ist auf drei Einträge gekürzt",
              kn is not None and kn.childCount() == 4 and sammel.endswith(" weitere"), sammel)
        _ansicht_fokussieren(w, app)
        klick(w, app, m.nodes[n["K5"]])
        it = b.currentItem()
        check("Klick auf K5 hinter „… N weitere“: die Zeile K5 ist nachgeladen, gewählt und sichtbar",
              it is not None and _element(it) == ("knoten", str(n["K5"])) and it.isSelected()
              and _sichtbar(b, it), str(_aktuell(b)))
        check("… die Tastatur bleibt in der Ansicht", _fokus() is w.plotter.interactor, str(_fokus()))
        w.refresh_all()
        _ruhe(app)
        check("… nach einem Neuaufbau ist K5 weiter gewählt", _aktuell(b) == ("knoten", str(n["K5"]))
              and _gewaehlt(b) == [("knoten", str(n["K5"]))], str(_aktuell(b)))
    finally:
        dsg.BAUM_MAX = alt
        w.refresh_all()
        _ruhe(app)


def test_keine_maske_beim_nachfuehren():
    """Das Nachfuehren ist kein Klick im Baum: keine Maske wird angelegt,
    geoeffnet oder an der Leiste „Übernehmen | Verwerfen“ angehalten (die
    13m-Regel ``_maskenweg`` gilt fuer Klicks des Anwenders im Baum)."""
    w, app = _fenster()
    m, n = _modell(w, app)
    b = w.baum
    werkstoff = next(iter(m.materials))
    w._objektmaske("werkstoff", werkstoff)
    _ruhe(app)
    mk = w.maskenrand.maske
    from PySide6 import QtWidgets
    feld = next((f for f in getattr(mk, "_felder", {}).values()
                 if isinstance(f, QtWidgets.QLineEdit) and f.isEnabled() and not f.isReadOnly()), None)
    if feld is not None:
        feld.setText(feld.text() + "1")
        _ruhe(app)
    geaendert = bool(mk is not None and mk.geaenderte_felder())
    check("Vorbereitung: rechts steht die Werkstoffmaske mit einer nicht übernommenen Änderung",
          mk is not None and geaendert, str(getattr(mk, "titel", None)))
    erzeugt, gehalten = [], []
    alt_erzeugen, alt_halten = w.maske_erzeugen, w._maskenwechsel_halten

    def erzeugen(*a, **k):
        erzeugt.append(getattr(a[0], "titel", "?") if a else "?")
        return alt_erzeugen(*a, **k)

    def halten(*a, **k):
        gehalten.append(a[1:2])
        return alt_halten(*a, **k)
    spion = _Spion()
    b.angeklickt.connect(spion.melden)
    b.mehrfach.connect(spion.melden)
    b.bearbeiten.connect(spion.melden)
    w.maske_erzeugen, w._maskenwechsel_halten = erzeugen, halten
    try:
        _ansicht_fokussieren(w, app)
        klick(w, app, m.nodes[n["K2"]])
        klick(w, app, m.nodes[n["K3"]], strg=True)
    finally:
        w.maske_erzeugen, w._maskenwechsel_halten = alt_erzeugen, alt_halten
        b.angeklickt.disconnect(spion.melden)
        b.mehrfach.disconnect(spion.melden)
        b.bearbeiten.disconnect(spion.melden)
    check("Vorbereitung: der Baum ist nachgeführt (K2 und K3 gewählt)",
          _gewaehlt(b) == sorted([("knoten", str(n["K2"])), ("knoten", str(n["K3"]))]), str(_gewaehlt(b)))
    check("Nachführen: der Baum meldet keinen Klick (angeklickt, mehrfach, bearbeiten)",
          not spion.gesehen, str(spion.gesehen[:3]))
    check("… keine Maske angelegt oder geöffnet", not erzeugt, str(erzeugt))
    check("… nicht an der Leiste „Übernehmen | Verwerfen“ angehalten",
          not gehalten and not (getattr(w, "aenderungsleiste", None) is not None
                                and w.aenderungsleiste.isVisible()), str(gehalten))
    check("… die geänderte Werkstoffmaske steht unverändert rechts",
          w.maskenrand.maske is mk and bool(mk.geaenderte_felder()), str(getattr(w.maskenrand.maske, "titel", None)))
    check("… kein modales Fenster", not MODAL, str(MODAL[:2]))
    # aufraeumen: die Aenderung verwerfen
    leiste = getattr(w, "aenderungsleiste", None)
    if leiste is not None and leiste.isVisible():
        from PySide6 import QtWidgets
        k = next((x for x in leiste.findChildren(QtWidgets.QPushButton) if x.text() == "Verwerfen"), None)
        if k is not None:
            k.click()
    w.maskenrand.schliessen()
    _ruhe(app)


# ---------------------------------------------------------------------------
# 3. Filterzeile
# ---------------------------------------------------------------------------
def _sichtbare_eintraege(baum):
    from PySide6 import QtCore
    out = []
    for i in _alle(baum):
        if i.data(0, QtCore.Qt.UserRole + 1) is None:
            continue
        p, ok = i, True
        while p is not None:
            if p.isHidden():
                ok = False
                break
            p = p.parent()
        if ok:
            out.append(_element(i))
    return out


def _filterzeile(w):
    return getattr(w, "baum_filter", None)


def _warten(app, ms=320):
    """Die Ruhezeit der Filterzeile (150 ms) abwarten."""
    from PySide6 import QtTest
    QtTest.QTest.qWait(ms)
    _ruhe(app)


def _tippen(app, f, text):
    """Text in die Filterzeile tippen - als Tastenereignisse, nicht mit setText
    (Nachbesserung 8d, G5); was darin stand, wird ueberschrieben. Danach die
    Ruhezeit abwarten."""
    from PySide6 import QtCore, QtTest
    f.selectAll()
    if text:
        QtTest.QTest.keyClicks(f, text)
    else:
        QtTest.QTest.keyClick(f, QtCore.Qt.Key_Backspace)
    _warten(app)


import contextlib  # noqa: E402


@contextlib.contextmanager
def _menues_abfangen():
    """Kontextmenues wirksam abfangen: die Klasse ``QtWidgets.QMenu`` wird fuer
    die Dauer gegen eine Unterklasse getauscht, deren ``exec`` die Eintraege
    aufzeichnet. Der Klassen-Patch ``QtWidgets.QMenu.exec = lambda …`` greift
    unter PySide6 6.11.2 nicht (Gegenpruefung 8d, p_menu): das echte Menue
    oeffnete sich, und die Pruefung sah nichts. :func:`test_d11_rechtsklick`
    prueft beides."""
    from PySide6 import QtWidgets
    gesehen = []
    alt = QtWidgets.QMenu

    class Menue(alt):
        def exec(self, *a, **k):
            gesehen.append([x.text() for x in self.actions()])
            return None
    QtWidgets.QMenu = Menue
    try:
        yield gesehen
    finally:
        QtWidgets.QMenu = alt


def test_filter():
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    m, n = _modell(w, app)
    ziel = m.nn + 120                       # 120 freie Knoten der Konstruktion dazu
    while m.nn < ziel:
        m.add_node(50.0 + m.nn, 50.0, 0.0)
    w.refresh_all()
    _ruhe(app)
    b = w.baum
    f = _filterzeile(w)
    check("Über dem Modellbaum steht eine Filterzeile (zu Beginn zu)",
          f is not None and f.isHidden() and f.parentWidget() is b.parentWidget(), str(f))
    if f is None:
        return
    # ein Aufklappzustand, den der Filter nicht kennt
    gr = _zweig(b, "Geometrie", "modell")
    for name in ("Linien", "Stäbe"):
        z = _zweig(b, name)
        if z is not None:
            z.setExpanded(name == "Linien")
    _zweig(b, "Knoten", "knoten").setExpanded(False)
    vorher = _aufklappung(b)
    b.setFocus()
    w.activateWindow()
    _ruhe(app)
    QtTest.QTest.keyClick(b, QtCore.Qt.Key_F, QtCore.Qt.ControlModifier)
    _ruhe(app)
    _tippen(app, f, "k1")
    sicht = _sichtbare_eintraege(b)
    knoten = sorted(k for a, k in sicht if a == "knoten")
    erwartet = sorted(str(i) for i in range(m.nn) if "k1" in f"k{i}" and _finden(b, "knoten", i) is not None)
    check("Filter „k1“ (getippt, Teiltext, ohne Groß/Klein): sichtbar sind genau die Knoten mit „k1“ im Namen",
          knoten == erwartet and len(erwartet) >= 5, f"{knoten} / {erwartet}")
    check("… und nichts, was nicht passt (keine Linie, kein Stab)",
          all("k1" in _finden(b, a, k).text(0).lower() for a, k in sicht if _finden(b, a, k) is not None)
          and not [x for x in sicht if x[0] in ("linie", "stab")], str([x for x in sicht if x[0] != "knoten"][:4]))
    k1 = _finden(b, "knoten", n["K1"])
    check("… die Eltern sind sichtbar und aufgeklappt (Knoten, Geometrie, Wurzel)",
          k1 is not None and _sichtbar(b, k1) and gr is not None and not gr.isHidden() and gr.isExpanded(),
          str(_pfad(k1) if k1 is not None else None))
    lin = _zweig(b, "Linien")
    check("… ein Zweig ohne Treffer ist ausgeblendet (Linien)", lin is not None and lin.isHidden())
    _tippen(app, f, "K1")
    check("„K1“ groß geschrieben findet dasselbe",
          sorted(k for a, k in _sichtbare_eintraege(b) if a == "knoten") == erwartet)
    # Neuaufbau mit Filter
    w.refresh_all()
    _ruhe(app)
    knoten2 = sorted(k for a, k in _sichtbare_eintraege(b) if a == "knoten")
    lin = _zweig(b, "Linien")
    check("Der Filter überlebt einen Neuaufbau (refresh_all): Text bleibt, dieselben Zeilen sichtbar",
          f.text() == "K1" and knoten2 == erwartet and lin is not None and lin.isHidden(), str(knoten2))
    # Esc stellt den Aufklappzustand wieder her
    f.setFocus()
    _ruhe(app)
    QtTest.QTest.keyClick(f, QtCore.Qt.Key_Escape)
    _ruhe(app)
    nachher = _aufklappung(b)
    check("Esc in der Filterzeile: Filter leer, alle Zeilen wieder sichtbar",
          f.text() == "" and not [i for i in _alle(b) if i.isHidden()], str(f.text()))
    check("… der Aufklappzustand von vorher ist wieder da (Linien offen, Stäbe und Knoten zu)",
          nachher == vorher, str({k[-1]: (vorher.get(k), v) for k, v in nachher.items() if vorher.get(k) != v}))
    check("… Esc hebt im Feld nur den Filter auf, nicht die Auswahl oder einen Vorgang",
          f.isHidden() and b.hasFocus(), f"Feld zu {f.isHidden()}, Baum hat den Fokus {b.hasFocus()}")
    # ein leeres Feld wirkt wie Esc
    f.show()
    f.setFocus()
    _tippen(app, f, "S2")
    s2 = _sichtbare_eintraege(b)
    _tippen(app, f, "")
    check("Ein leeres Feld stellt den Aufklappzustand ebenso wieder her",
          ("stab", "S2") in s2 and _aufklappung(b) == vorher and not [i for i in _alle(b) if i.isHidden()],
          str(s2[:3]))
    f.hide()


def test_filter_gekuerzt():
    """Hinter „… N weitere“ sucht der Filter mit und zeigt die Treffer."""
    from statik3d.gui import design as dsg
    from statik3d import knotenrollen as kr
    w, app = _fenster()
    m, n = _modell(w, app)
    f = _filterzeile(w)
    alt = dsg.BAUM_MAX
    dsg.BAUM_MAX = 3
    try:
        w.refresh_all()
        _ruhe(app)
        b = w.baum
        if f is None:
            check("Filterzeile vorhanden", False)
            return
        f.show()
        f.setFocus()
        _tippen(app, f, f"K{n['K5']}")
        sicht = _sichtbare_eintraege(b)
        check(f"Filter „K{n['K5']}“ bei gekürztem Zweig: die Zeile hinter „… N weitere“ ist sichtbar",
              ("knoten", str(n["K5"])) in sicht, str(sicht[:6]))
        w.refresh_all()
        _ruhe(app)
        check("… auch nach dem Neuaufbau", ("knoten", str(n["K5"])) in _sichtbare_eintraege(b))
        _tippen(app, f, "")
        kn = _zweig(b, "Knoten", "knoten")
        texte = [kn.child(i).text(0) for i in range(kn.childCount())]
        check("… Filter leer: der Zweig zeigt wieder drei Einträge und die Sammelzeile",
              len(texte) == 4 and texte[-1].endswith(" weitere") and not kn.child(3).isHidden(), str(texte))
        # Obergrenze: mehr Treffer hinter der Sammelzeile als FILTER_MAX laden
        # nichts nach, die Sammelzeile nennt sie; weiter getippt kommen sie
        alt_fm = getattr(dsg.Modellbaum, "FILTER_MAX", None)
        dsg.Modellbaum.FILTER_MAX = 2
        rest = len([int(x) for x in kr.konstruktionsknoten(m)]) - 3
        try:
            _tippen(app, f, "K")
            kn = _zweig(b, "Knoten", "knoten")
            texte = [kn.child(i).text(0) for i in range(kn.childCount())]
            sammel = [kn.child(i).text(0) for i in range(kn.childCount())
                      if not kn.child(i).isHidden() and kn.child(i).text(0).startswith("… ")]
            check(f"Filter „K“ mit Obergrenze 2: {rest} Treffer hinter der Sammelzeile, keiner nachgeladen",
                  texte[:3] == ["K0", "K1", "K2"] and len(texte) == 4 and sammel == [f"… {rest} weitere Treffer"],
                  f"{texte} / {sammel}")
            _tippen(app, f, f"K{n['K5']}")
            check(f"… weiter getippt („K{n['K5']}“): K{n['K5']} kommt, nichts sonst nachgeladen",
                  ("knoten", str(n["K5"])) in _sichtbare_eintraege(b)
                  and _finden(b, "knoten", 3) is None and _finden(b, "knoten", 4) is None,
                  str(_sichtbare_eintraege(b)[:5]))
            # Obergrenze 0: nichts nachgeladen, die Sammelzeile nennt die Treffer
            dsg.Modellbaum.FILTER_MAX = 0
            _tippen(app, f, "")
            _tippen(app, f, f"K{n['K5']}")
            such = f"k{n['K5']}"
            erw = sum(1 for i in [int(x) for x in kr.konstruktionsknoten(m)][3:] if such in f"k{i}")
            kn = _zweig(b, "Knoten", "knoten")
            sammel = [kn.child(i).text(0) for i in range(kn.childCount())
                      if not kn.child(i).isHidden() and kn.child(i).text(0).startswith("… ")]
            check(f"Obergrenze 0: nichts nachgeladen, die Sammelzeile sagt „… {erw} weitere Treffer“",
                  sammel == [f"… {erw} weitere Treffer"] and ("knoten", str(n["K5"])) not in _sichtbare_eintraege(b),
                  str(sammel))
        finally:
            if alt_fm is not None:
                dsg.Modellbaum.FILTER_MAX = alt_fm
            _tippen(app, f, "")
    finally:
        dsg.BAUM_MAX = alt
        if f is not None:
            _tippen(app, f, "")
            f.hide()
        w.refresh_all()
        _ruhe(app)


# ---------------------------------------------------------------------------
# 4. Strg+F
# ---------------------------------------------------------------------------
def test_strg_f():
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    _modell(w, app)
    b, f, suche = w.baum, _filterzeile(w), w.ribbon.suche
    w.activateWindow()
    _ruhe(app)
    check("Vorbereitung: das Fenster ist aktiv (Kürzel wirken)", w.isActiveWindow())
    # im Baum
    b.setFocus()
    _ruhe(app)
    QtTest.QTest.keyClick(b, QtCore.Qt.Key_F, QtCore.Qt.ControlModifier)
    _ruhe(app)
    check("Strg+F im Modellbaum öffnet die Filterzeile und setzt den Cursor hinein",
          f is not None and f.isVisible() and _fokus() is f and not suche.hasFocus(), str(_fokus()))
    if f is not None:
        QtTest.QTest.keyClicks(f, "k")
        _warten(app)
        QtTest.QTest.keyClick(f, QtCore.Qt.Key_F, QtCore.Qt.ControlModifier)
        _ruhe(app)
        check("Strg+F in der Filterzeile bleibt dort und markiert den Text",
              _fokus() is f and f.selectedText() == "k" and not suche.hasFocus(), repr(f.selectedText()))
        QtTest.QTest.keyClick(f, QtCore.Qt.Key_Escape)
        _ruhe(app)
    # D12: in der Ansicht - der Tastendruck geht an die Ansicht mit dem Fokus darin
    _ansicht_fokussieren(w, app)
    suche.setText("kombi")
    ia = w.plotter.interactor
    vorher = _fokus()
    QtTest.QTest.keyClick(ia, QtCore.Qt.Key_F, QtCore.Qt.ControlModifier)
    _ruhe(app)
    check("D12: Strg+F mit dem Fokus in der Ansicht (an die Ansicht geschickt): die Befehlssuche, "
          "die Filterzeile bleibt zu",
          vorher is ia and _fokus() is suche and suche.selectedText() == "kombi" and (f is None or f.isHidden()),
          f"{vorher} -> {_fokus()}")
    suche.clear()
    # in einer Maske
    w.maske_knoten()
    _ruhe(app)
    mk = w.maskenrand.maske
    feld = next(iter(mk._felder.values()))
    feld.setFocus()
    _ruhe(app)
    QtTest.QTest.keyClick(feld, QtCore.Qt.Key_F, QtCore.Qt.ControlModifier)
    _ruhe(app)
    check("Strg+F in einem Feld der Maske: die Befehlssuche wie bisher",
          _fokus() is suche and (f is None or f.isHidden()), str(_fokus()))
    w.maskenrand.schliessen()
    _ruhe(app)


# ---------------------------------------------------------------------------
# 5. Nachbesserung (Gegenpruefung 4976a91): D1 bis D13
# ---------------------------------------------------------------------------
def _stabmodell(w, app, name="Neues Modell"):
    """Zwoelf Knoten in einer Reihe, acht Staebe S1 bis S8, Lastfall LF1,
    Knotenlager an K0 (wie die Gegenpruefung, p2_filter)."""
    from statik3d.model import Member as Mb
    w.new_model()
    m = w.model
    m.name = name
    mat, sec = list(m.materials)[0], list(m.sections)[0]
    kn = [m.add_node(float(i), 0.0, 0.0) for i in range(12)]
    for j in range(8):
        e = m.add_element("beam", [kn[j], kn[j + 1]], mat, sec)
        m.members[f"S{j + 1}"] = Mb(f"S{j + 1}", elements=[e])
    m.add_load_case("LF1", "Q")
    m.fix(kn[0], "all")
    w.refresh_all()
    _ruhe(app)
    return m, kn


class _Fragen:
    """Rueckfragen des Fensters aufzeichnen und mit Nein beantworten."""

    def __init__(self, w):
        self.w, self.texte = w, []
        self.alt = w._bestaetigen
        w._bestaetigen = self.fragen

    def fragen(self, text, *_a, **_k):
        self.texte.append(str(text).split("\n")[0])
        return False

    def zurueck(self):
        self.w._bestaetigen = self.alt


def _ohne_filter(app, f):
    if f is not None:
        f.setFocus()
        _tippen(app, f, "")
        f.hide()


def test_d1_d2_tasten_im_gefilterten_baum():
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    m, kn = _stabmodell(w, app)
    b, f = w.baum, _filterzeile(w)
    if f is None:
        check("D1: Filterzeile vorhanden", False)
        return
    fragen = _Fragen(w)
    geoeffnet = []
    alt_om = w._objektmaske
    w._objektmaske = lambda art, name, *a, **k: (geoeffnet.append((art, str(name))), alt_om(art, name, *a, **k))[1]
    try:
        s2 = _finden(b, "stab", "S2")
        w.activateWindow()
        b.setFocus()
        b.scrollToItem(s2)
        _ruhe(app)
        QtTest.QTest.mouseClick(b.viewport(), K.LeftButton, K.NoModifier, b.visualItemRect(s2).center())
        _ruhe(app)
        QtTest.QTest.keyClick(b, K.Key_F, K.ControlModifier)
        _ruhe(app)
        QtTest.QTest.keyClicks(f, "S1")
        _warten(app)
        QtTest.QTest.keyClick(f, K.Key_Down)
        _ruhe(app)
        cur = b.currentItem()
        check("D1: nach Klick auf S2, Strg+F, „S1“ und Pfeil nach unten ist S1 aktuell, keine "
              "ausgeblendete aktuelle Zeile",
              cur is not None and _element(cur) == ("stab", "S1") and _sichtbar(b, cur)
              and not [i for i in _alle(b) if i is cur and i.isHidden()],
              f"{_aktuell(b)}, sichtbar {_sichtbar(b, cur) if cur is not None else None}")
        fragen.texte.clear()
        QtTest.QTest.keyClick(b, K.Key_Delete)
        _ruhe(app)
        check("D1: Entf danach - die Rückfrage nennt S1, nie S2",
              len(fragen.texte) == 1 and "S1" in fragen.texte[0] and "S2" not in fragen.texte[0]
              and "S2" in m.members, str(fragen.texte))
        geoeffnet.clear()
        QtTest.QTest.keyClick(b, K.Key_Return)
        _ruhe(app)
        mk = w.maskenrand.maske
        check("D2: die Eingabetaste öffnet die Maske von S1",
              geoeffnet[-1:] == [("stab", "S1")] and mk is not None and "S1" in str(getattr(mk, "titel", "")),
              f"{geoeffnet}, {getattr(mk, 'titel', None)}")
    finally:
        w._objektmaske = alt_om
        fragen.zurueck()
        _ohne_filter(app, f)
        w.maskenrand.schliessen()
        _ruhe(app)


def test_d3_entf_nur_sichtbares():
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    m, kn = _stabmodell(w, app)
    b, f = w.baum, _filterzeile(w)
    if f is None:
        check("D3: Filterzeile vorhanden", False)
        return
    fragen = _Fragen(w)
    try:
        w.auswahlart_setzen("Stab")
        w._ziel_waehlen(("stab", "S1"))
        w._ziel_waehlen(("stab", "S2"), ersetzen=False)
        w._ziel_waehlen(("stab", "S3"), ersetzen=False)
        _ruhe(app)
        f.show()
        f.setFocus()
        _tippen(app, f, "S1")
        w.activateWindow()
        b.setFocus()
        _ruhe(app)
        fragen.texte.clear()
        QtTest.QTest.keyClick(b, QtCore.Qt.Key_Delete)
        _ruhe(app)
        check("D3: S1 bis S3 in der Ansicht gewählt, Filter „S1“, Entf im Baum - die Rückfrage nennt nur S1",
              len(fragen.texte) == 1 and "S1" in fragen.texte[0] and "S2" not in fragen.texte[0]
              and "S3" not in fragen.texte[0], str(fragen.texte))
    finally:
        fragen.zurueck()
        _ohne_filter(app, f)


def test_d4_ausgeblendetes_objekt():
    w, app = _fenster()
    m, n = _modell(w, app)
    b, f = w.baum, _filterzeile(w)
    if f is None:
        check("D4: Filterzeile vorhanden", False)
        return
    try:
        f.show()
        f.setFocus()
        _tippen(app, f, "S1")
        _ansicht_fokussieren(w, app)
        klick(w, app, m.nodes[n["K3"]])
        k3 = _finden(b, "knoten", n["K3"])
        meldung = w.statusBar().currentMessage()
        check("D4: Filter „S1“, Klick in der Ansicht auf K3 - die Ansicht wählt K3",
              sorted(int(i) for i in w.selection) == [n["K3"]], str(list(w.selection)))
        check("D4: … der Baum markiert nichts und hat keine aktuelle Zeile",
              not [i for i in _alle(b) if i.isSelected()] and b.currentItem() is None,
              f"markiert {[_element(i) for i in _alle(b) if i.isSelected()]}, aktuell {_aktuell(b)}, "
              f"K3 markiert {k3.isSelected() if k3 is not None else None}")
        check("D4: … die Statuszeile sagt „K3 ist durch den Filter „S1“ ausgeblendet“",
              f"K{n['K3']} ist durch den Filter „S1“ ausgeblendet" in meldung, repr(meldung))
    finally:
        _ohne_filter(app, f)


def _treffer_regel(b, such):
    """(sichtbar, soll) - die sichtbaren Zeilen und die, die nach G2 sichtbar
    sein sollen: Treffer (ab Ebene 2, Name passt, keine Sammelzeile) und ihre
    Eltern; Wurzel und Gruppen nie als Treffer."""
    from PySide6 import QtCore

    def ebene(it):
        e, p = 0, it.parent()
        while p is not None:
            e, p = e + 1, p.parent()
        return e
    treffer = [i for i in _alle(b) if ebene(i) >= 2 and such in i.text(0).lower()
               and not i.data(0, QtCore.Qt.UserRole + 5)]
    soll = set()
    for t in treffer:
        p = t
        while p is not None:
            soll.add(id(p))
            p = p.parent()
    sicht = {id(i) for i in _alle(b) if _sichtbar_gefiltert(i)}
    return sicht, soll, treffer


def _sichtbar_gefiltert(it):
    p = it
    while p is not None:
        if p.isHidden():
            return False
        p = p.parent()
    return True


def test_d5_d6_wurzel_und_gruppen():
    w, app = _fenster()
    m, kn = _stabmodell(w, app, "Neues Modell")
    b, f = w.baum, _filterzeile(w)
    if f is None:
        check("D5: Filterzeile vorhanden", False)
        return
    try:
        f.show()
        f.setFocus()
        for such in ("modell", "e", "s"):
            _tippen(app, f, such)
            sicht, soll, treffer = _treffer_regel(b, such)
            zuviel = [i.text(0) for i in _alle(b) if id(i) in sicht - soll]
            fehlt = [i.text(0) for i in _alle(b) if id(i) in soll - sicht]
            check(f"D5: Modell „Neues Modell“, Filter „{such}“ - sichtbar sind nur Treffer (Einträge, Zweige) "
                  "und ihre Eltern; Wurzel und Gruppen allein machen nichts sichtbar",
                  not zuviel and not fehlt, f"{len(treffer)} Treffer, zu viel {zuviel[:5]}, fehlt {fehlt[:5]}")
        _tippen(app, f, "")
        m.name = "Drehlager V34"
        w.refresh_all()
        _ruhe(app)
        _tippen(app, f, "lager")
        lager = _zweig(b, "Lager", "lager")
        kl = _zweig(b, "Knotenlager", "lager")
        s235 = next((i for i in _alle(b) if _element(i)[0] == "werkstoff"), None)
        check("D6: Modell „Drehlager V34“, Filter „lager“ - die Zweige „Lager“ und „Knotenlager“ sichtbar "
              "und zugeklappt",
              lager is not None and kl is not None and _sichtbar_gefiltert(lager) and _sichtbar_gefiltert(kl)
              and not lager.isExpanded() and not kl.isExpanded(),
              f"Lager sichtbar {lager is not None and _sichtbar_gefiltert(lager)} offen "
              f"{lager.isExpanded() if lager is not None else None}, Knotenlager offen "
              f"{kl.isExpanded() if kl is not None else None}")
        check("D6: … der Werkstoff ausgeblendet",
              s235 is not None and not _sichtbar_gefiltert(s235), str(s235.text(0) if s235 is not None else None))
    finally:
        _ohne_filter(app, f)


def _grosses_modell(n, staebe=0):
    from statik3d.model import Model, Member as Mb
    m = Model()
    m.name = "Gross"
    m.nodes = np.random.default_rng(1).random((n, 3)) * 100.0
    for i in range(staebe):
        e = m.add_element("beam", [2 * i, 2 * i + 1], "S235", "IPE 200")
        m.members[f"S{i + 1}"] = Mb(f"S{i + 1}", elements=[e])
    return m


def test_d7_kein_nachladen_wegen_zweignamen():
    from statik3d.gui import design as dsg
    m = _grosses_modell(21000)
    b, app = _baum(800)
    try:
        b.fuellen(m)
        app.processEvents()
        kn = _zweig(b, "Knoten", "knoten")
        n0 = kn.childCount()
        b.filtern("k")
        app.processEvents()
        n1 = kn.childCount()
        sammel = kn.child(n1 - 1)
        check("D7: 21 000 Knoten, Filter „k“ - hinter „… N weitere“ wird nichts nachgeladen",
              n0 == dsg.BAUM_MAX + 1 and n1 == n0, f"Zeilen vorher {n0}, nachher {n1}")
        check("D7: … der Zweig „Knoten“ bleibt zu, die Sammelzeile nennt die Treffer",
              not kn.isExpanded() and not kn.isHidden() and sammel.text(0) == "… 1000 weitere Treffer"
              and not sammel.isHidden(), f"offen {kn.isExpanded()}, {sammel.text(0)!r}")
    finally:
        b.close()


def test_d8_markierung_wie_ansicht():
    w, app = _fenster()
    m, n = _modell(w, app)
    b = w.baum

    def markiert():
        return sorted(_element(i) for i in _alle(b) if i.isSelected())

    def soll():
        out = set()
        for i in [int(x) for x in w.selection]:
            z = _finden(b, "knoten", i)
            out.add(_element(z) if z is not None else ("netzknoten", "Netzknoten"))
        return sorted(out)
    _ansicht_fokussieren(w, app)
    klick(w, app, m.nodes[n["K1"]])
    w.select_all()
    _ruhe(app)
    check(f"D8: Klick K1, dann Alles auswählen ({len(w.selection)} Knoten) - der Baum markiert genau die "
          "Auswahl der Ansicht", len(w.selection) == m.nn and markiert() == soll(),
          f"Baum {len(markiert())} Zeilen, soll {len(soll())}: {markiert()[:4]}")
    w.invert_selection()
    _ruhe(app)
    check("D8: … Auswahl umkehren (leer) - der Baum markiert nichts und hat keine aktuelle Zeile",
          not len(w.selection) and not markiert() and b.currentItem() is None,
          f"{markiert()[:4]}, aktuell {_aktuell(b)}")
    klick(w, app, m.nodes[n["K3"]])
    w._tabelle_knoten(str(n["K4"]))
    _ruhe(app)
    check("D8: Klick K3, dann Klick in die Tabelle Knoten auf K4 - der Baum markiert K4",
          sorted(int(i) for i in w.selection) == [n["K4"]] and markiert() == [("knoten", str(n["K4"]))]
          and _aktuell(b) == ("knoten", str(n["K4"])), f"Ansicht {list(w.selection)}, Baum {markiert()}")
    # mehr als 200: nichts
    ziel = m.nn + 120
    while m.nn < ziel:
        m.add_node(80.0 + m.nn, 80.0, 0.0)
    w.refresh_all()
    _ruhe(app)
    w.select_all()
    _ruhe(app)
    check(f"D8: Alles auswählen mit {m.nn} Knoten (mehr als 200) - der Baum markiert nichts",
          len(w.selection) == m.nn > 200 and not markiert() and b.currentItem() is None,
          f"{len(markiert())} markiert, aktuell {_aktuell(b)}")
    w.clear_selection()
    _ruhe(app)


def test_d9_aufheben_dann_entf():
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    m, n = _modell(w, app)
    b = w.baum
    fragen = _Fragen(w)
    try:
        frei = m.add_node(20.0, 0.0, 0.0)       # ein freier Knoten: ohne Filter loeschbar
        w.refresh_all()
        _ruhe(app)
        _ansicht_fokussieren(w, app)
        klick(w, app, m.nodes[frei])
        check(f"D9: Vorbereitung - Klick auf K{frei} markiert ihn im Baum", _aktuell(b) == ("knoten", str(frei)),
              str(_aktuell(b)))
        w.clear_selection()                     # „Auswahl aufheben“ (Esc, Glasleiste)
        _ruhe(app)
        nn = m.nn
        b.setFocus(QtCore.Qt.TabFocusReason)    # Tab in den Baum
        _ruhe(app)
        fragen.texte.clear()
        QtTest.QTest.keyClick(b, QtCore.Qt.Key_Delete)
        _ruhe(app)
        check("D9: Klick auf den Knoten, Auswahl aufheben, Tab in den Baum, Entf - keine Rückfrage, nichts gelöscht",
              not fragen.texte and m.nn == nn, f"{fragen.texte}, aktuell {_aktuell(b)}")
    finally:
        fragen.zurueck()


def test_d10_reihenfolge_nachgeladen():
    from statik3d.gui import design as dsg
    from statik3d.model import Model
    m = Model()
    m.name = "Kurz"
    m.nodes = np.array([[float(i), 0.0, 0.0] for i in range(12)])
    alt = dsg.BAUM_MAX
    dsg.BAUM_MAX = 3
    b, app = _baum()
    try:
        b.fuellen(m)
        app.processEvents()
        b.eintrag_waehlen("knoten", "10")
        b.eintrag_waehlen("knoten", "3")
        kn = _zweig(b, "Knoten", "knoten")
        texte = [kn.child(i).text(0) for i in range(kn.childCount())]
        check("D10: K10 und dann K3 hinter der Sammelzeile nachgeladen - Reihenfolge K0, K1, K2, K3, K10",
              texte == ["K0", "K1", "K2", "K3", "K10", "… 7 weitere"], str(texte))
    finally:
        dsg.BAUM_MAX = alt
        b.close()


def test_d11_rechtsklick():
    from PySide6 import QtCore, QtGui, QtWidgets
    w, app = _fenster()
    m, kn = _stabmodell(w, app)
    b, f = w.baum, _filterzeile(w)
    # Gegenprobe des Abfangens: der Klassen-Patch greift nicht, der Tausch der Klasse schon
    gerufen = []
    alt_exec = QtWidgets.QMenu.exec
    QtWidgets.QMenu.exec = lambda self, *a, **k: (gerufen.append("klasse"), None)[1]
    try:
        probe = QtWidgets.QMenu()
        probe.addAction("x")
        QtCore.QTimer.singleShot(200, probe.close)
        probe.exec(QtCore.QPoint(10, 10))
    finally:
        QtWidgets.QMenu.exec = alt_exec
    with _menues_abfangen() as gesehen:
        probe = QtWidgets.QMenu()
        probe.addAction("y")
        QtCore.QTimer.singleShot(200, probe.close)
        probe.exec(QtCore.QPoint(10, 10))
    check("D11: Gegenprobe - der Klassen-Patch QMenu.exec greift nicht, der Tausch der Klasse greift",
          not gerufen and gesehen == [["y"]], f"Klassen-Patch {gerufen}, Tausch {gesehen}")
    if f is None:
        check("D11: Filterzeile vorhanden", False)
        return
    try:
        w.auswahlart_setzen("Stab")
        w._ziel_waehlen(("stab", "S1"))
        w._ziel_waehlen(("stab", "S2"), ersetzen=False)
        w._ziel_waehlen(("stab", "S3"), ersetzen=False)
        f.show()
        f.setFocus()
        _tippen(app, f, "S1")
        s1 = _finden(b, "stab", "S1")
        b.scrollToItem(s1)
        _ruhe(app)
        pos = b.visualItemRect(s1).center()
        with _menues_abfangen() as gesehen:
            ev = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, pos, b.viewport().mapToGlobal(pos))
            QtWidgets.QApplication.sendEvent(b.viewport(), ev)
            _ruhe(app)
        check("D11: Rechtsklick auf S1 im gefilterten Baum (S1 bis S3 gewählt) - das Menü wurde abgefangen, "
              "Einträge wie in 8b, nichts für die ausgeblendeten S2 und S3",
              gesehen == [["Neu: Stab …", "Bearbeiten …", "", "Löschen (Entf)"]], str(gesehen))
    finally:
        _ohne_filter(app, f)


def test_d13_ruhezeit():
    import time
    from PySide6 import QtTest
    from statik3d.gui import design as dsg
    m = _grosses_modell(20000, staebe=5000)
    b, app = _baum(800)
    halter = None
    try:
        b.fuellen(m)
        app.processEvents()
        if not hasattr(dsg, "Baumfilter"):
            check("D13: Filterzeile vorhanden", False)
            return
        f = dsg.Baumfilter(b)
        f.show()
        app.processEvents()
        laeufe = []
        alt = b._filter_anwenden

        def zaehlend():
            alt()
            laeufe.append(time.perf_counter())
        b._filter_anwenden = zaehlend
        t0 = time.perf_counter()
        QtTest.QTest.keyClicks(f, "S12")
        sofort = len(laeufe)
        while not laeufe and time.perf_counter() - t0 < 2.0:
            app.processEvents()
        QtTest.QTest.qWait(300)
        app.processEvents()
        dauer = (laeufe[0] - t0) if laeufe else None
        sicht = sorted(k for a, k in _sichtbare_eintraege(b) if a == "stab")
        check("D13: 20 000 Knoten, „S12“ rasch getippt - kein Filterlauf je Taste, genau einer nach der Ruhezeit",
              sofort == 0 and len(laeufe) == 1, f"während des Tippens {sofort}, insgesamt {len(laeufe)}")
        check("D13: … Gesamtzeit vom ersten Tastendruck bis zum gefilterten Baum unter 0,5 s",
              dauer is not None and dauer < 0.5, f"{dauer:.3f} s" if dauer is not None else "kein Lauf")
        check("D13: … und der Baum zeigt S12, S120 … S129, S1200 … S1299",
              len(sicht) == 111 and "S12" in sicht, f"{len(sicht)} Stäbe")
        halter = f
    finally:
        b.close()
        if halter is not None:
            halter.close()


def test_s4_esc_zeigt_gewaehlte_zeile():
    """G4, S4: nach Esc ist die gewaehlte Zeile sichtbar, auch wenn ihr Zweig vor
    dem Filter zu war."""
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    m, kn = _stabmodell(w, app)
    b, f = w.baum, _filterzeile(w)
    if f is None:
        check("S4: Filterzeile vorhanden", False)
        return
    try:
        _zweig(b, "Stäbe", "staebe").setExpanded(False)
        w.activateWindow()
        b.setFocus()
        _ruhe(app)
        QtTest.QTest.keyClick(b, QtCore.Qt.Key_F, QtCore.Qt.ControlModifier)
        QtTest.QTest.keyClicks(f, "S8")              # „S3“ traefe zuerst den Werkstoff S355
        _warten(app)
        QtTest.QTest.keyClick(f, QtCore.Qt.Key_Down)
        _ruhe(app)
        f.setFocus()
        QtTest.QTest.keyClick(f, QtCore.Qt.Key_Escape)
        _ruhe(app)
        s8 = _finden(b, "stab", "S8")
        check("S4: S8 im Filter gewählt (Pfeil nach unten), Esc - S8 ist sichtbar, obwohl „Stäbe“ vor dem "
              "Filter zu war", s8 is not None and s8.isSelected() and _sichtbar(b, s8), f"{_aktuell(b)}")
    finally:
        _ohne_filter(app, f)
        w.maskenrand.schliessen()
        _ruhe(app)


def test_liste_und_handbuch():
    from statik3d.gui import kuerzelliste as kl
    zeilen = [z for z in kl.WEITERE_TASTEN if z[1] == "Strg+F"]
    check("Liste der Tastenkürzel: Strg+F im Modellbaum steht unter „Weitere Tasten“",
          any(z[2] == "Modellbaum" and "Filterzeile" in z[3] and "Befehlssuche" in z[3] for z in zeilen),
          str(zeilen))
    esc = [z for z in kl.WEITERE_TASTEN if z[1] == "Esc" and "Filterzeile" in z[2]]
    check("… ebenso Esc in der Filterzeile", len(esc) == 1, str(esc))
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs",
                        "Benutzerhandbuch.md")
    with open(pfad, encoding="utf-8") as fh:
        t = " ".join(fh.read().split())     # Zeilenumbrueche wie Leerzeichen
    check("Handbuch: Ansicht → Baum ohne Fokuswechsel, mit dem Stand davor",
          "markiert die Zeile im Modellbaum" in t and "Tastatur bleibt in der Ansicht" in t
          and "Bis zum 03.10.2026 ließ ein Klick in der Ansicht den Baum stehen" in t)
    check("Handbuch: Filterzeile mit Strg+F, Esc und Neuaufbau",
          "Filterzeile über dem Modellbaum" in t and "Strg+F im Modellbaum" in t
          and "überlebt" in t and "… N weitere" in t)
    check("Handbuch: die Nachbesserung (Ruhezeit, Wurzel und Gruppen nie Treffer, nichts Ausgeblendetes, "
          "Auswahlbefehle und Tabellen, Stand der ersten Fassung)",
          "150 Millisekunden" in t and "nie selbst Treffer" in t and "K3 ist durch den Filter „S1“ ausgeblendet" in t
          and "Die Markierung im Baum zeigt immer die Auswahl der Ansicht" in t
          and "In der ersten Fassung vom 03.10.2026 filterte jeder Buchstabe sofort" in t)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    tests = [test_verzeichnis_statt_suche, test_gekuerzter_zweig_baum, test_ansicht_waehlt_baumzeile,
             test_ansicht_gekuerzter_zweig, test_keine_maske_beim_nachfuehren, test_filter,
             test_filter_gekuerzt, test_strg_f,
             # Nachbesserung nach der Gegenpruefung (D1 bis D13, S4)
             test_d1_d2_tasten_im_gefilterten_baum, test_d3_entf_nur_sichtbares, test_d4_ausgeblendetes_objekt,
             test_d5_d6_wurzel_und_gruppen, test_d7_kein_nachladen_wegen_zweignamen, test_d8_markierung_wie_ansicht,
             test_d9_aufheben_dann_entf, test_d10_reihenfolge_nachgeladen, test_d11_rechtsklick, test_d13_ruhezeit,
             test_s4_esc_zeigt_gewaehlte_zeile,
             test_liste_und_handbuch]
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:                 # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} läuft ohne Ausnahme", False, repr(ex))
    ok = sum(1 for _n, o in RESULTS if o)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    os._exit(0 if ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
