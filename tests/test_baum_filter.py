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
    QtWidgets.QMenu.exec = lambda self, *a, **k: (MODAL.append(("menue", "")), None)[1]


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
    f.setText("k1")
    _ruhe(app)
    sicht = _sichtbare_eintraege(b)
    knoten = sorted(k for a, k in sicht if a == "knoten")
    erwartet = sorted(str(i) for i in range(m.nn) if "k1" in f"k{i}" and _finden(b, "knoten", i) is not None)
    check("Filter „k1“ (Teiltext, ohne Groß/Klein): sichtbar sind genau die Knoten mit „k1“ im Namen",
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
    f.setText("K1")
    _ruhe(app)
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
    f.setText("S2")
    _ruhe(app)
    s2 = _sichtbare_eintraege(b)
    f.setText("")
    _ruhe(app)
    check("Ein leeres Feld stellt den Aufklappzustand ebenso wieder her",
          ("stab", "S2") in s2 and _aufklappung(b) == vorher and not [i for i in _alle(b) if i.isHidden()],
          str(s2[:3]))
    f.hide()


def test_filter_gekuerzt():
    """Hinter „… N weitere“ sucht der Filter mit und zeigt die Treffer."""
    from statik3d.gui import design as dsg
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
        f.setText(f"K{n['K5']}")
        _ruhe(app)
        sicht = _sichtbare_eintraege(b)
        check(f"Filter „K{n['K5']}“ bei gekürztem Zweig: die Zeile hinter „… N weitere“ ist sichtbar",
              ("knoten", str(n["K5"])) in sicht, str(sicht[:6]))
        w.refresh_all()
        _ruhe(app)
        check("… auch nach dem Neuaufbau", ("knoten", str(n["K5"])) in _sichtbare_eintraege(b))
        f.setText("")
        _ruhe(app)
        kn = _zweig(b, "Knoten", "knoten")
        texte = [kn.child(i).text(0) for i in range(kn.childCount())]
        check("… Filter leer: der Zweig zeigt wieder drei Einträge und die Sammelzeile",
              len(texte) == 4 and texte[-1].endswith(" weitere") and not kn.child(3).isHidden(), str(texte))
        # Obergrenze der nachgeladenen Treffer: Taste für Taste darf „K“ das
        # Kontingent nicht für „K5“ verbrauchen
        alt_fm = getattr(dsg.Modellbaum, "FILTER_MAX", None)
        dsg.Modellbaum.FILTER_MAX = 2
        try:
            f.setText("K")
            _ruhe(app)
            kn = _zweig(b, "Knoten", "knoten")
            zeilen = [kn.child(i).text(0) for i in range(kn.childCount()) if not kn.child(i).isHidden()]
            # „K“ passt auch auf den Zweig „Knoten“ selbst: er zeigt alles
            check("Filter „K“ mit Obergrenze 2: zwei Treffer hinter der Sammelzeile nachgeladen (K3, K4)",
                  zeilen[:5] == ["K0", "K1", "K2", "K3", "K4"] and zeilen[-1].endswith(" weitere")
                  and len(zeilen) == 6, str(zeilen))
            f.setText(f"K{n['K5']}")
            _ruhe(app)
            check(f"… weiter getippt („K{n['K5']}“): K{n['K5']} kommt trotz der Obergrenze, K3 und K4 gehen",
                  ("knoten", str(n["K5"])) in _sichtbare_eintraege(b)
                  and _finden(b, "knoten", 3) is None and _finden(b, "knoten", 4) is None,
                  str(_sichtbare_eintraege(b)[:5]))
            # Obergrenze 0: nichts nachgeladen, die Sammelzeile nennt die Treffer
            from statik3d import knotenrollen as kr
            dsg.Modellbaum.FILTER_MAX = 0
            f.setText("")
            f.setText(f"K{n['K5']}")
            _ruhe(app)
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
            f.setText("")
            _ruhe(app)
    finally:
        dsg.BAUM_MAX = alt
        if f is not None:
            f.setText("")
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
        f.setText("k")
        f.setFocus()
        _ruhe(app)
        QtTest.QTest.keyClick(f, QtCore.Qt.Key_F, QtCore.Qt.ControlModifier)
        _ruhe(app)
        check("Strg+F in der Filterzeile bleibt dort und markiert den Text",
              _fokus() is f and f.selectedText() == "k" and not suche.hasFocus(), repr(f.selectedText()))
        QtTest.QTest.keyClick(f, QtCore.Qt.Key_Escape)
        _ruhe(app)
    # in der Ansicht
    _ansicht_fokussieren(w, app)
    suche.setText("kombi")
    QtTest.QTest.keyClick(w, QtCore.Qt.Key_F, QtCore.Qt.ControlModifier)
    _ruhe(app)
    check("Strg+F in der Ansicht: die Befehlssuche wie bisher, die Filterzeile bleibt zu",
          _fokus() is suche and suche.selectedText() == "kombi" and (f is None or f.isHidden()), str(_fokus()))
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


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    tests = [test_verzeichnis_statt_suche, test_gekuerzter_zweig_baum, test_ansicht_waehlt_baumzeile,
             test_ansicht_gekuerzter_zweig, test_keine_maske_beim_nachfuehren, test_filter,
             test_filter_gekuerzt, test_strg_f, test_liste_und_handbuch]
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
