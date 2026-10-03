"""
Klickregel im Modellbaum (Teilpaket 8b der Oberflaechenplanung, 03.10.2026).

Entscheidungen des Anwenders vom 24.09.2026 (PLAN-OBERFLAECHE-2026-09-24.md):

* Antwort 4: „Klick auf einen Zweig wählt nichts.“
* Antwort 11: „Doppelklick auf einen Zweig öffnet die rechte Anlegemaske
  „Neu …“, nicht-modal und ohne sofort anzulegen.“

Geprueft wird mit dem echten Hauptfenster offscreen und mit echten Mausklicks
in den Baum (QTest, ``clicked`` vor ``doubleClicked`` wie am Desktop):

* jeder Zweig, den der Baum zeigt - Gruppen, Unterzweige, Zaehlzeile
  „Netzknoten“, Sammelzeilen „… N weitere“, Ergebnisgruppen -, aendert beim
  einfachen Klick die Auswahl nicht, legt nichts an, oeffnet nichts Modales
  und zeigt rechts seine Uebersicht; die Liste der Zweige kommt aus dem Baum;
* die Uebersicht: Anzahl, Liste aus Name und Kennzahl, hoechstens
  UEBERSICHT_MAX Zeilen, darunter „… N weitere – alle in der Tabelle“ mit
  einem Knopf zur Tabelle, ohne Schleife ueber alle Eintraege;
* ein Klick in die Liste wirkt wie der Klick auf den Eintrag im Baum;
* der Doppelklick oeffnet die Anlegemaske, ohne anzulegen; ausgenommen sind
  Knoten, Layer, Unterlagen, Linien- und Flaechenlager;
* Lastfaelle und Kombinationen (Tabelle, Register, Liste), Bericht
  (Uebersicht, „Neu: Berichtsbild“ ohne sofortiges Bild);
* eine geaenderte Maske haelt den Zweigklick an der Leiste „Übernehmen |
  Verwerfen“ (Paket 13m);
* die Hinweise an den Zweigen und das Handbuch.

Aufruf:  python -m tests.test_baum_klickregel
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
# Beispiel laden ohne die Rueckfrage „Ungespeicherte Änderungen“
os.environ["STATIK3D_UNGESPEICHERT"] = "verwerfen"
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_baum_klickregel_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}
#: modale Fenster, die sich oeffnen wollten: (Art, Text)
MODAL = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _modal_abfangen():
    """Kein modales Fenster darf erscheinen - jedes wird aufgezeichnet und
    sofort beantwortet, damit nichts auf dem Bildschirm stehen bleibt."""
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
    QtWidgets.QInputDialog.getText = staticmethod(lambda *a, **k: (MODAL.append(("eingabe", "")), ("", False))[1])


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _modal_abfangen()
    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler = []
    w.error = lambda msg, *a, **k: (w.fehler.append(str(msg)), w.log.appendPlainText("FEHLER: " + str(msg)))
    _FENSTER.update(w=w, app=app)
    return w, app


def _ruhe(app, n=3):
    for _ in range(n):
        app.processEvents()


# ---------------------------------------------------------------------------
# Hilfen ueber Datenrollen und Texte - sie laufen auch am Stand vor 8b
# (Gegenprobe)
# ---------------------------------------------------------------------------
def _art(it):
    from PySide6 import QtCore
    return str(it.data(0, QtCore.Qt.UserRole) or "")


def _ist_eintrag(it):
    from PySide6 import QtCore
    return it.data(0, QtCore.Qt.UserRole + 1) is not None


def _alle(baum):
    from PySide6 import QtWidgets
    out = []
    it = QtWidgets.QTreeWidgetItemIterator(baum)
    while it.value():
        out.append(it.value())
        it += 1
    return out


def _ist_zweig(it):
    """Ein Zweig im Sinn von 8b: kein einzelnes Objekt (kein Schluessel) und
    keine Befehlszeile „+ …“; die Ergebnisgruppen (Verformungen, Lastfaelle,
    … unter „Ergebnisse“) tragen einen Schluessel und zaehlen trotzdem dazu."""
    if it.parent() is None:
        return False                    # die Wurzel zeigt das Register Modell (bleibt)
    art = _art(it)
    if art.endswith("_neu"):
        return False
    return not _ist_eintrag(it) or art == "ergebnisgruppe"


def _pfad(it):
    teile = []
    while it is not None:
        teile.append(it.text(0))
        it = it.parent()
    return tuple(reversed(teile))


def _finden(baum, pfad):
    for it in _alle(baum):
        if _pfad(it) == pfad:
            return it
    return None


def _zweig(baum, text, art=None):
    for it in _alle(baum):
        if it.text(0) == text and _ist_zweig(it) and (art is None or _art(it) == art):
            return it
    return None


def _eintrag(baum, art, schluessel):
    from PySide6 import QtCore
    for it in _alle(baum):
        if _art(it) == art and str(it.data(0, QtCore.Qt.UserRole + 1)) == str(schluessel):
            return it
    return None


def _klick(w, app, item, doppelt=False, zwischen=None):
    """Ein echter Mausklick (und auf Wunsch der Doppelklick danach) mitten
    auf die Zeile - so, wie Qt es am Desktop zustellt: Druecken, Loslassen
    (``itemClicked``), dann Doppelklick (``itemDoubleClicked``). ``zwischen``
    laeuft nach dem einfachen Klick und vor dem Doppelklick (der Zustand,
    den der Doppelklick vorfindet)."""
    from PySide6 import QtCore, QtTest
    b = w.baum
    p = item.parent()
    while p is not None:
        p.setExpanded(True)
        p = p.parent()
    b.scrollToItem(item)
    _ruhe(app)
    mitte = b.visualItemRect(item).center()
    QtTest.QTest.mouseClick(b.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, mitte)
    if doppelt:
        if zwischen is not None:
            _ruhe(app)
            zwischen()
        QtTest.QTest.mouseDClick(b.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, mitte)
    _ruhe(app)


def _fingerabdruck(m) -> str:
    """Was Model.save schriebe - ohne den aktiven Lastfall (eine Anzeigewahl)."""
    d = m.to_dict()
    d.pop("active_case", None)
    return json.dumps(d, sort_keys=True, default=str)


def _auswahl(w):
    return (tuple(int(x) for x in w.selection), tuple(w.sel_linien), tuple(w.sel_staebe),
            tuple(w.sel_flaechen), tuple(w.sel_koerper), tuple(getattr(w, "sel_lager", []) or []),
            tuple(getattr(w, "sel_elemente", []) or []), tuple(int(x) for x in (w.leuchtet or [])),
            w.auswahlart)


def _maske(w):
    return w.maskenrand.maske if w.maskenrand.offen() else None


def _uebersicht(w):
    """Die Uebersicht rechts (Maske mit ``uebersicht``), sonst None."""
    mk = _maske(w)
    return mk if mk is not None and getattr(mk, "uebersicht", None) is not None else None


def _liste(mk):
    from PySide6 import QtWidgets
    return mk.findChild(QtWidgets.QTreeWidget, "uebersichtliste") if mk is not None else None


def _zeilen(mk):
    lw = _liste(mk)
    if lw is None:
        return []
    return [(lw.topLevelItem(i).text(0), lw.topLevelItem(i).text(1)) for i in range(lw.topLevelItemCount())]


def _feld(mk, name):
    try:
        return mk.werte().get(name)
    except Exception:                   # noqa: BLE001
        return None


def _tabelle(w):
    tu = w.tab_unten
    return tu.tabText(tu.currentIndex())


def _aufraeumen(w, app):
    leiste = getattr(w, "aenderungsleiste", None)
    if leiste is not None and leiste.isVisible():
        from PySide6 import QtWidgets
        b = next((x for x in leiste.findChildren(QtWidgets.QPushButton) if x.text() == "Verwerfen"), None)
        if b is not None:
            b.click()
    w.maskenrand.schliessen()
    _ruhe(app)


def _reiches_modell(w, app):
    """Hallenrahmen mit allem, was einen eigenen Zweig erzeugt (wie
    tests.test_baum_gruppen), dazu zwei Berichtsbilder, einseitige Lager, ein
    Flaechenkontakt und Elemente fuer Flaechen- und Volumenelemente."""
    from statik3d.model import Flaeche, Volumenkoerper, Berichtseintrag
    from statik3d.wasserdruck import Wasserdruck
    from statik3d.schweissnaehte import Schweissnaht
    from statik3d.bridges.positions import Stellung
    w.load_example("hall")
    _ruhe(app)
    m = w.model
    m.add_surface_support([0], name="FL1", uz=dict(typ="spring", stiffness=1e7))
    m.add_line_support([0, 1], name="LL1", uz=dict(typ="spring", stiffness=1e7))
    m.flaechen["F1"] = Flaeche("F1", ["L1"])
    m.flaechen["F1"].gelenklinien = ["L1"]
    m.koerper["V1"] = Volumenkoerper("V1", flaechen=["F1"] * 6, material="S355")
    m.wasserdruecke["W1"] = Wasserdruck("W1", h_ow=2.0)
    m.schweissnaehte["N1"] = Schweissnaht("N1", art="Kehlnaht", a=5.0)
    m.add_feder_prop("FD", [1e6, 1e6, 1e6, 0, 0, 0])
    m.add_element("feder", [0, 1], "S355", "FD")
    m.add_punktmasse(1, 250.0, [1.0, 2.0, 3.0])
    m.add_daempfer(1, -1, [40.0, 0, 0, 0, 0, 0])
    m.add_starrkoerper(0, [1], "RBE2")
    m.add_grenzschicht_prop("GS", 1e9, 5e8)
    e_s = m.add_element("shell4", [0, 1, 2, 3], "S355", None)
    e_v = m.add_element("tet4", [0, 1, 2, 4], "S355", None)
    m.add_beulfeld("B1", [e_s])
    m.add_volumenbereich("VB1", [e_v])
    m.add_lasteinleitung("LE1", 0)
    m.add_contact_support(2)
    m.add_kontaktbedingung("KB1")
    m.bericht.append(Berichtseintrag(name="Bild A", quelle="case:LF1"))
    m.bericht.append(Berichtseintrag(name="Bild B", quelle="case:LF2"))
    m.stellungen.append(Stellung("S1", 0.0, "geschlossen"))
    w.refresh_all()
    _ruhe(app)
    return m


# ---------------------------------------------------------------------------
# 1. Jeder Zweig: der einfache Klick waehlt nichts und legt nichts an
# ---------------------------------------------------------------------------
def _zweige_klicken(w, app, zweige, wo):
    """Jeden Zweig (Pfad) einmal echt anklicken; zurueck die Pfade, bei denen
    etwas nicht stimmt, je Pruefung."""
    stab = next(iter(w.model.members))
    w._baum_geklickt("stab", stab)
    _ruhe(app)
    vorher = _auswahl(w)
    fp = _fingerabdruck(w.model)
    fehler = {"auswahl": [], "angelegt": [], "modal": [], "uebersicht": [], "punktfang": [], "fehlt": []}
    for pfad in zweige:
        it = _finden(w.baum, pfad)
        if it is None:
            fehler["fehlt"].append(pfad[-1])
            continue
        MODAL.clear()
        _klick(w, app, it)
        name = " → ".join(pfad[1:])
        if _auswahl(w) != vorher:
            fehler["auswahl"].append(name)
        if _fingerabdruck(w.model) != fp:
            fehler["angelegt"].append(name)
            fp = _fingerabdruck(w.model)
        if MODAL:
            fehler["modal"].append(f"{name} {MODAL[:1]}")
        if _uebersicht(w) is None:
            fehler["uebersicht"].append(f"{name} ({getattr(_maske(w), 'titel', w.rechts_zeigt())})")
        if w.maskenrand.will_punkte():
            fehler["punktfang"].append(name)
        _aufraeumen(w, app)
    return fehler, vorher


def test_jeder_zweig_waehlt_nichts():
    from statik3d.gui import design as dsg
    w, app = _fenster()
    alt_max = dsg.BAUM_MAX
    # Sammelzeilen „… N weitere“ schon bei wenigen Eintraegen (Knoten, Linien,
    # Stabelemente, Lager, Lastfaelle, Kombinationen)
    dsg.BAUM_MAX = 3
    try:
        _reiches_modell(w, app)
        alle = _alle(w.baum)
        zweige = [_pfad(it) for it in alle if _ist_zweig(it)]
        sammel = [p for p in zweige if p[-1].startswith("… ") and p[-1].endswith(" weitere")]
        gruppen = [p for p in zweige if len(p) == 2]
        check("der Baum zeigt die Zweige, um die es geht (Gruppen, Sammelzeilen, Zählzeile)",
              len(gruppen) == 10 and len(sammel) >= 4 and any(p[-1] == "Netzknoten" for p in zweige)
              and len(zweige) > 50, f"{len(zweige)} Zweige, {len(gruppen)} Gruppen, {len(sammel)} Sammelzeilen")
        fehler, _v = _zweige_klicken(w, app, zweige, "reich")
    finally:
        dsg.BAUM_MAX = alt_max
    check(f"alle {len(zweige)} Zweige gefunden und angeklickt", not fehler["fehlt"], str(fehler["fehlt"][:5]))
    check("ein Klick auf einen Zweig ändert die Auswahl nicht (Antwort 4)",
          not fehler["auswahl"], f"{len(fehler['auswahl'])}: {fehler['auswahl'][:6]}")
    check("… und legt nichts an", not fehler["angelegt"], str(fehler["angelegt"][:5]))
    check("… und öffnet nichts Modales", not fehler["modal"], str(fehler["modal"][:5]))
    check("… sondern zeigt rechts die Übersicht des Zweigs", not fehler["uebersicht"],
          f"{len(fehler['uebersicht'])}: {fehler['uebersicht'][:6]}")
    check("… und schaltet keinen Punktfang ein (Bemaßungen)", not fehler["punktfang"], str(fehler["punktfang"]))


def test_ergebniszweige():
    """Die Gruppe „Ergebnisse“, die Ergebnisgruppen und ihre Sammelzeilen."""
    from statik3d import solver
    from statik3d.gui import design as dsg
    w, app = _fenster()
    w.load_example("hall")
    _ruhe(app)
    an = solver.solve_all(w.model, design=bool(w.model.members))
    alt_max = dsg.BAUM_MAX
    dsg.BAUM_MAX = 3
    try:
        w._solve_done("all", an)
        _ruhe(app)
        w.refresh_all()
        _ruhe(app)
        erg = w.baum.gruppe("ergebnisse")
        zweige = [_pfad(it) for it in _alle(w.baum)
                  if _ist_zweig(it) and (it is erg or (erg is not None and _pfad(it)[:2] == _pfad(erg)))]
        check("unter „Ergebnisse“ stehen Ergebnisgruppen mit Sammelzeilen",
              len(zweige) >= 3 and any(p[-1].endswith(" weitere") for p in zweige), str([p[-1] for p in zweige]))
        fehler, _v = _zweige_klicken(w, app, zweige, "ergebnisse")
    finally:
        dsg.BAUM_MAX = alt_max
    check("Ergebniszweige: die Auswahl bleibt, nichts angelegt, nichts Modales",
          not fehler["auswahl"] and not fehler["angelegt"] and not fehler["modal"],
          str({k: v[:3] for k, v in fehler.items() if v}))
    check("… rechts die Übersicht der Gruppe", not fehler["uebersicht"], str(fehler["uebersicht"][:5]))
    vg = _zweig(w.baum, "Lastfälle", "ergebnisgruppe")
    if vg is not None:
        _klick(w, app, vg)
        mk = _uebersicht(w)
        zeilen = _zeilen(mk)
        check("Ergebnisgruppe „Lastfälle“: die Liste nennt die gerechneten Lastfälle",
              mk is not None and [z[0] for z in zeilen] == list(an.cases)[:len(zeilen)] and zeilen,
              str(zeilen[:3]))
        lw = _liste(mk)
        if lw is not None and lw.topLevelItemCount():
            _listenklick(app, lw, 0)
            check("… ein Klick in die Liste stellt das Ergebnis ein wie der Baum (Lastfall in der Ansicht)",
                  w._aktuelle_quelle() == f"case:{list(an.cases)[0]}", w._aktuelle_quelle())
    w.analysis = w.results = None
    _aufraeumen(w, app)


# ---------------------------------------------------------------------------
# 2. Die Uebersicht: Anzahl, Liste, Begrenzung, „weitere“
# ---------------------------------------------------------------------------
def _listenklick(app, lw, zeile):
    from PySide6 import QtCore, QtTest
    it = lw.topLevelItem(zeile)
    lw.scrollToItem(it)
    _ruhe(app)
    QtTest.QTest.mouseClick(lw.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                            lw.visualItemRect(it).center())
    _ruhe(app)


def _knotenmodell(w, app, n):
    """Ein Modell mit ``n`` frei gesetzten Knoten (alle Konstruktion) und
    drei Linien."""
    w.new_model()
    _ruhe(app)
    m = w.model
    m.add_nodes(np.array([[float(i), 0.0, 0.0] for i in range(n)]))
    for i in range(3):
        m.add_line(f"L{i + 1}", [i, i + 1])
    w.refresh_all()
    _ruhe(app)
    return m


def test_uebersicht_mit_liste():
    from statik3d.gui import design as dsg
    from PySide6 import QtWidgets
    w, app = _fenster()
    n = 2000
    m = _knotenmodell(w, app, n)
    gross = getattr(w, "UEBERSICHT_MAX", 40)
    kn = _zweig(w.baum, "Knoten", "knoten")
    zaehler = {"n": 0}
    alt = dsg.Modellbaum._schluessel

    def gezaehlt(item):
        zaehler["n"] += 1
        return alt(item)
    w.tabelle_zeigen("Linien")
    _ruhe(app)
    dsg.Modellbaum._schluessel = staticmethod(gezaehlt)
    try:
        _klick(w, app, kn)
    finally:
        dsg.Modellbaum._schluessel = staticmethod(alt)
    mk = _uebersicht(w)
    zeilen = _zeilen(mk)
    check(f"Zweig „Knoten“ ({n} Knoten): rechts die Übersicht „Knoten“ mit der Anzahl",
          mk is not None and mk.titel == "Knoten" and str(_feld(mk, "anzahl")) == str(n),
          f"{getattr(mk, 'titel', None)} {_feld(mk, 'anzahl')}")
    check(f"… mit einer Liste aus Name und Kennzahl, höchstens {gross} Zeilen",
          len(zeilen) == gross and zeilen[0][0] == "K0" and zeilen[0][1] != "" and zeilen[-1][0] == f"K{gross - 1}",
          f"{len(zeilen)} Zeilen, {zeilen[:2]} … {zeilen[-1:]}")
    weiter = mk.findChild(QtWidgets.QLabel, "uebersichtweitere") if mk is not None else None
    check(f"… darunter „… {n - gross} weitere – alle in der Tabelle“",
          weiter is not None and weiter.text() == f"… {n - gross} weitere – alle in der Tabelle",
          weiter.text() if weiter is not None else None)
    check("… und die Übersicht liest den Zweig nicht ganz (keine Schleife über alle Einträge)",
          zaehler["n"] < 4 * gross + len(w.baum._zweige) if hasattr(w.baum, "_zweige") else False,
          f"{zaehler['n']} Zeilen gelesen, der Zweig hat {kn.childCount() if kn is not None else '?'}")
    check("… und der Klick holt unten die Tabelle „Knoten“ nach vorn", _tabelle(w) == "Knoten", _tabelle(w))
    knopf = mk.findChild(QtWidgets.QPushButton, "uebersichttabelle") if mk is not None else None
    w.tabelle_zeigen("Linien")
    _ruhe(app)
    if knopf is not None:
        knopf.click()
        _ruhe(app)
    check("… der Knopf daneben holt die Tabelle „Knoten“ wieder (dort stehen alle)",
          knopf is not None and _tabelle(w) == "Knoten", _tabelle(w))
    li = _zweig(w.baum, "Linien", "linien")
    _klick(w, app, li)
    mk = _uebersicht(w)
    zeilen = _zeilen(mk)
    weiter = mk.findChild(QtWidgets.QLabel, "uebersichtweitere") if mk is not None else None
    check("Zweig „Linien“ (3): alle drei in der Liste, mit Kennzahl, ohne „weitere“",
          [z[0] for z in zeilen] == ["L1", "L2", "L3"] and all(z[1] for z in zeilen)
          and (weiter is None or not weiter.isVisible()) and _tabelle(w) == "Linien",
          f"{zeilen} {_tabelle(w)}")
    check("… mit dem Knopf „Neu …“ (Anlegemaske Linie)",
          mk is not None and mk.btn_anwenden.isVisible() and "Linie" in mk.btn_anwenden.text(),
          mk.btn_anwenden.text() if mk is not None else None)
    check("die Übersicht hat keine Eingabefelder und trägt darum nie den Punkt aus 13m",
          mk is not None and not mk.geaenderte_felder()
          and all(isinstance(x, QtWidgets.QLabel) for x in mk._felder.values()),
          str([type(x).__name__ for x in mk._felder.values()]) if mk is not None else "")
    geo = _zweig(w.baum, "Geometrie", "modell")
    _klick(w, app, geo)
    mk = _uebersicht(w)
    zeilen = _zeilen(mk)
    check("Gruppe „Geometrie“: die Liste nennt ihre Zweige mit Anzahl",
          [z[0] for z in zeilen] == ["Knoten", "Linien", "Stäbe", "Flächen", "Volumen"]
          and zeilen[0][1] == str(n) and zeilen[1][1] == "3", str(zeilen))
    _aufraeumen(w, app)


def _vernetztes_modell(w, app):
    """Platte 4 m x 2 m aus vier Linien, vernetzt, und ein Knotenlager (wie
    tests.test_baum_gruppen): die meisten Knoten sind Netzknoten."""
    w.new_model()
    _ruhe(app)
    m = w.model
    mat, dicke = list(m.materials)[0], list(m.shells)[0]
    ids = [m.add_node(0, 0, 0), m.add_node(4, 0, 0), m.add_node(4, 2, 0), m.add_node(0, 2, 0)]
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
        m.add_line(f"L{i}", [ids[a], ids[b]])
    f = m.add_flaeche("F1", ["L0", "L1", "L2", "L3"], dicke=dicke, material=mat, teilung=[8, 8])
    w._vernetzen([f], [])
    m.support(ids[1], "all", name="Lager A")
    w.refresh_all()
    _ruhe(app)
    return m


def test_knoten_wie_der_zweig():
    """Die Uebersicht „Knoten“ zaehlt und listet dieselben Knoten wie der
    Zweig - die Konstruktionsknoten aus 8c, nicht alle Knoten des Netzes; die
    Zaehlzeile „Netzknoten“ zeigt ihre Zahl und den Weg zur Tabelle, ohne Liste."""
    from statik3d.gui import viewport as vp
    from PySide6 import QtWidgets
    w, app = _fenster()
    m = _vernetztes_modell(w, app)
    kons = [int(i) for i in vp.konstruktionsknoten(m)]
    kn = _zweig(w.baum, "Knoten", "knoten")
    zweig_namen = [kn.child(i).text(0) for i in range(kn.childCount())] if kn is not None else []
    _klick(w, app, kn)
    mk = _uebersicht(w)
    zeilen = _zeilen(mk)
    check(f"vernetzte Platte: {len(kons)} Konstruktionsknoten von {m.nn} Knoten",
          0 < len(kons) < m.nn and kn is not None and kn.text(1) == str(len(kons)), kn.text(1) if kn else None)
    check("Übersicht „Knoten“: Anzahl wie der Zweig (Konstruktionsknoten), nicht alle Knoten",
          mk is not None and str(_feld(mk, "anzahl")) == str(len(kons)), str(_feld(mk, "anzahl")))
    check("… die Liste nennt dieselben Knoten wie der Zweig, in derselben Folge",
          [z[0] for z in zeilen] == zweig_namen[:len(zeilen)] and len(zeilen) == min(len(kons), w.UEBERSICHT_MAX)
          if hasattr(w, "UEBERSICHT_MAX") else False, f"{[z[0] for z in zeilen][:6]} / {zweig_namen[:6]}")
    nz = _zweig(w.baum, "Netzknoten", "netzknoten")
    w.tabelle_zeigen("Linien")
    _ruhe(app)
    _klick(w, app, nz)
    mk = _uebersicht(w)
    lw = _liste(mk)
    knopf = mk.findChild(QtWidgets.QPushButton, "uebersichttabelle") if mk is not None else None
    check("Zählzeile „Netzknoten“: Übersicht mit der Zahl der Netzknoten, ohne Liste, unten die Tabelle „Knoten“",
          mk is not None and str(_feld(mk, "anzahl")) == str(m.nn - len(kons))
          and (lw is None or not lw.isVisible()) and _tabelle(w) == "Knoten",
          f"{getattr(mk, 'titel', None)} {_feld(mk, 'anzahl')} {_tabelle(w)}")
    w.tabelle_zeigen("Linien")
    _ruhe(app)
    if knopf is not None:
        knopf.click()
        _ruhe(app)
    check("… mit einem Knopf zur Tabelle „Knoten“", knopf is not None and _tabelle(w) == "Knoten", _tabelle(w))
    _aufraeumen(w, app)


# ---------------------------------------------------------------------------
# 3. Ein Klick in die Liste wirkt wie der Klick auf den Eintrag im Baum
# ---------------------------------------------------------------------------
def _zustand(w):
    cur = w.baum.currentItem()
    mk = _maske(w)
    return (_auswahl(w), getattr(mk, "titel", None),
            (_art(cur), str(cur.text(0))) if cur is not None else None)


def test_listenklick_wie_baumklick():
    w, app = _fenster()
    _knotenmodell(w, app, 60)
    # Vergleich: der Klick auf K5 im Baum
    k5 = _eintrag(w.baum, "knoten", "5")
    _klick(w, app, k5)
    soll = _zustand(w)
    _aufraeumen(w, app)
    w.clear_selection()
    _ruhe(app)
    _klick(w, app, _zweig(w.baum, "Knoten", "knoten"))
    lw = _liste(_uebersicht(w))
    zeile = next((i for i in range(lw.topLevelItemCount()) if lw.topLevelItem(i).text(0) == "K5"), None) \
        if lw is not None else None
    if zeile is not None:
        _listenklick(app, lw, zeile)
    ist = _zustand(w)
    check("Klick auf „K5“ in der Liste: dieselbe Auswahl, dieselbe Maske, derselbe Eintrag im Baum",
          zeile is not None and ist == soll and soll[1] == "Knoten K5" and soll[0][0] == (5,),
          f"{ist} / {soll}")
    check("… und die Tastatur steht im Baum (weiterblättern mit den Pfeiltasten)",
          w.focusWidget() is w.baum, type(w.focusWidget()).__name__)
    # Eine Gruppe: die Zeile ist ein Zweig
    w.clear_selection()
    _ruhe(app)
    vorher = _auswahl(w)
    _klick(w, app, _zweig(w.baum, "Geometrie", "modell"))
    lw = _liste(_uebersicht(w))
    zeile = next((i for i in range(lw.topLevelItemCount()) if lw.topLevelItem(i).text(0) == "Linien"), None) \
        if lw is not None else None
    if zeile is not None:
        _listenklick(app, lw, zeile)
    mk = _uebersicht(w)
    cur = w.baum.currentItem()
    check("Gruppe „Geometrie“, Zeile „Linien“: die Übersicht „Linien“, der Zweig im Baum gewählt, "
          "die Auswahl bleibt",
          mk is not None and mk.titel == "Linien" and cur is not None and cur.text(0) == "Linien"
          and _auswahl(w) == vorher, f"{getattr(mk, 'titel', None)} {cur.text(0) if cur else None}")
    _aufraeumen(w, app)


# ---------------------------------------------------------------------------
# 4. Doppelklick: Anlegemaske ohne Anlegen, mit echter Klickfolge
# ---------------------------------------------------------------------------
def test_doppelklick_anlegemaske():
    w, app = _fenster()
    _reiches_modell(w, app)
    b = w.baum
    neu_arten = set(getattr(w, "BAUM_DOPPELKLICK_NEU", ()))
    ohne = {"knoten", "layerliste", "unterlagen", "linienlager", "flaechenlager"}
    check("Doppelklick-Anlegen gilt für jede Art mit „Neu“ im Rechtsklick, außer Knoten, Layer, Unterlagen, "
          "Linien- und Flächenlager", neu_arten == set(b.NEU_ARTEN) - ohne and "bericht" in neu_arten,
          str(sorted(set(b.NEU_ARTEN) - ohne - neu_arten)) + " / " + str(sorted(neu_arten & ohne)))
    folge = []
    b.itemClicked.connect(lambda it, _c: folge.append(("clicked", it.text(0))))
    b.itemDoubleClicked.connect(lambda it, _c: folge.append(("doubleClicked", it.text(0))))
    stab = next(iter(w.model.members))
    fp = _fingerabdruck(w.model)
    # die Zweige aus dem Baum, je Art der erste (Gruppen wie „Lager“ sind keine Anlegezweige)
    zweige = {}
    for it in _alle(b):
        if _ist_zweig(it) and _art(it) in b.NEU_ARTEN and not it.font(0).bold() \
                and not it.text(0).startswith("… "):
            zweige.setdefault(_art(it), _pfad(it))
    falsch, ausnahmen, vorab = [], [], []
    for art, pfad in sorted(zweige.items()):
        w._baum_geklickt("stab", stab)
        _ruhe(app)
        vorher = _auswahl(w)
        it = _finden(b, pfad)
        folge.clear()
        MODAL.clear()
        name = pfad[-1]

        def zwischen(name=name, vorher=vorher):
            # was der einfache Klick hinterlaesst, findet der Doppelklick vor:
            # die Uebersicht, sonst nichts - auch kein Leuchten weniger
            if not (_uebersicht(w) is not None and _auswahl(w) == vorher and not MODAL
                    and _fingerabdruck(w.model) == fp):
                vorab.append(f"{name}: {getattr(_maske(w), 'titel', None)} {MODAL[:1]}")
        _klick(w, app, it, doppelt=True, zwischen=zwischen)
        mk = _maske(w)
        ok_folge = [f[0] for f in folge] == ["clicked", "doubleClicked"]
        # die Anlegemaske darf ihre Vorschau zeigen (Stellung: die abgeschalteten
        # Elemente leuchten) - gewaehlt bleibt, was gewaehlt war
        gewaehlt = _auswahl(w)[:7] == vorher[:7] and _auswahl(w)[8] == vorher[8]
        nichts = _fingerabdruck(w.model) == fp and not MODAL
        if art in ohne:
            # die Ausnahmen: nach dem Doppelklick steht weiter die Uebersicht
            if not (ok_folge and nichts and _auswahl(w) == vorher and _uebersicht(w) is not None):
                ausnahmen.append(f"{name}: {folge} {MODAL[:1]} {getattr(mk, 'titel', None)}")
        elif not (ok_folge and nichts and gewaehlt and mk is not None and _uebersicht(w) is None):
            falsch.append(f"{name}: {folge} {MODAL[:1]} {getattr(mk, 'titel', None)} "
                          f"{'angelegt' if _fingerabdruck(w.model) != fp else ''}"
                          f"{'' if gewaehlt else ' Auswahl geändert'}")
        fp = _fingerabdruck(w.model)
        _aufraeumen(w, app)
    check(f"vor dem Doppelklick: der einfache Klick zeigt nur die Übersicht ({len(zweige)} Zweige) – nichts, "
          "was der Doppelklick zurücknehmen müsste", not vorab and len(zweige) > 15, str(vorab[:4]))
    check(f"Doppelklick auf {len(zweige) - len(ohne & set(zweige))} Zweige: erst „clicked“, dann "
          "„doubleClicked“; rechts die Anlegemaske, nichts angelegt, nichts Modales, Auswahl unverändert",
          not falsch and len(zweige) > 15, f"{len(falsch)}: {falsch[:4]}")
    check(f"… Knoten, Layer, Unterlagen, Linien- und Flächenlager ({len(ohne & set(zweige))}): die Übersicht "
          "bleibt, nichts angelegt", not ausnahmen and len(ohne & set(zweige)) == 5, str(ausnahmen[:3]))
    _aufraeumen(w, app)


# ---------------------------------------------------------------------------
# 5. Lastfaelle, Kombinationen, Bericht
# ---------------------------------------------------------------------------
def test_lastfaelle_kombinationen_bericht():
    w, app = _fenster()
    m = _reiches_modell(w, app)
    from PySide6 import QtWidgets
    for text, art, eintrag, tabelle, n in (("Lastfälle", "lastfaelle", "lastfall", "Lastfälle", len(m.load_cases)),
                                           ("Kombinationen", "kombinationen", "kombination", "Kombinationen",
                                            len(m.combinations))):
        w.tabelle_zeigen("Knoten")
        zw = _zweig(w.baum, text, art)
        im_baum = [zw.child(i).text(0) for i in range(zw.childCount())]
        _klick(w, app, zw)
        mk = _uebersicht(w)
        zeilen = _zeilen(mk)
        check(f"„{text}“ ({n}): Tabelle „{tabelle}“ unten, rechts die Übersicht mit der Liste wie im Baum",
              _tabelle(w) == tabelle and mk is not None and [z[0] for z in zeilen] == im_baum[:len(zeilen)]
              and len(zeilen) == min(n, getattr(w, "UEBERSICHT_MAX", 40)) and str(_feld(mk, "anzahl")) == str(n),
              f"{_tabelle(w)} {len(zeilen)} von {n}: {[z[0] for z in zeilen][:4]}")
        reg = mk.findChild(QtWidgets.QPushButton, "uebersichtregister") if mk is not None else None
        if reg is not None:
            reg.click()
            _ruhe(app)
        check(f"… der Knopf „Register „Lastfälle““ holt ihr Register",
              reg is not None and reg.text() == "Register „Lastfälle“" and w.rechts_zeigt() == "Lastfälle",
              f"{reg.text() if reg is not None else None} {w.rechts_zeigt()}")
        check(f"… BAUM_TABELLE und BAUM_ZIEL kennen Zweig und Eintrag",
              w.BAUM_TABELLE.get(art) == tabelle and w.BAUM_TABELLE.get(eintrag) == tabelle
              and w.BAUM_ZIEL.get(art) == "Lastfälle")
    # Bericht. Die Aufnahme der Ansicht ersetzt eine Probe (wie
    # tests.test_ergebnisdarstellung): offscreen liefert VTK kein Bild.
    w.plotter.screenshot = lambda pfad, *a, **k: open(pfad, "wb").write(b"PNG-Probe")
    fp = _fingerabdruck(m)
    n = len(m.bericht)
    _klick(w, app, _zweig(w.baum, "Bericht", "bericht"))
    mk = _uebersicht(w)
    zeilen = _zeilen(mk)
    check("„Bericht“: Übersicht mit seinen Bildern, unten die Tabelle „Bericht“",
          mk is not None and [z[0] for z in zeilen] == ["Bild A", "Bild B"] and _tabelle(w) == "Bericht",
          f"{zeilen} {_tabelle(w)}")
    check("… Rechtsklick „Neu: Berichtsbild …“ (NEU_ARTEN) und der Knopf „Neu …“ in der Übersicht",
          w.baum.NEU_ARTEN.get("bericht") == "Berichtsbild" and mk is not None
          and mk.btn_anwenden.isVisible() and "Berichtsbild" in mk.btn_anwenden.text(),
          f"{w.baum.NEU_ARTEN.get('bericht')} {mk.btn_anwenden.text() if mk is not None else None}")
    lw = _liste(mk)
    if lw is not None and lw.topLevelItemCount() > 1:
        _listenklick(app, lw, 1)
    mk2 = _maske(w)
    check("… ein Klick auf „Bild B“ in der Liste öffnet seine Maske",
          mk2 is not None and mk2.titel == "Berichtsbild 2", getattr(mk2, "titel", None))
    _klick(w, app, _zweig(w.baum, "Bericht", "bericht"), doppelt=True)
    mk = _maske(w)
    check("Doppelklick „Bericht“: rechts „Neu: Berichtsbild“, noch kein Bild angelegt",
          mk is not None and mk.titel == "Neu: Berichtsbild" and len(m.bericht) == n and _fingerabdruck(m) == fp
          and mk.btn_abbrechen is not None, f"{getattr(mk, 'titel', None)} {len(m.bericht)}")
    if mk is not None and mk.btn_abbrechen is not None:
        mk.btn_abbrechen.click()
        _ruhe(app)
    check("… Abbrechen legt nichts an", len(m.bericht) == n and _fingerabdruck(m) == fp, str(len(m.bericht)))
    w.baum.neu.emit("bericht")
    _ruhe(app)
    mk = _maske(w)
    if mk is not None and "name" in mk._felder:
        mk.setzen("name", "Bild C")
        mk.setzen("beschriftung", "Übersicht des Rahmens")
        mk.btn_anwenden.click()
        _ruhe(app)
    neu = m.bericht[-1] if len(m.bericht) > n else None
    check("… OK nimmt die Ansicht mit Name und Bildunterschrift aus der Maske auf",
          neu is not None and neu.name == "Bild C" and neu.beschriftung == "Übersicht des Rahmens"
          and bool(neu.bild), f"{len(m.bericht)} {getattr(neu, 'name', None)}")
    # „+ Ansicht übernehmen“ ist ein Befehl und legt beim Klick an (Entscheidung 8b)
    plus = next((it for it in _alle(w.baum) if _art(it) == "bericht_neu"), None)
    n2 = len(w.model.bericht)
    if plus is not None:
        _klick(w, app, plus)
    check("„+ Ansicht übernehmen“ bleibt ein Befehl: ein Klick nimmt die Ansicht auf (Rückgängig nimmt sie zurück)",
          len(w.model.bericht) == n2 + 1, f"{n2} -> {len(w.model.bericht)}")
    w.undo()
    _ruhe(app)
    # Rueckgaengig stellt das Modell als neues Objekt wieder her
    check("… Rückgängig nimmt das Bild zurück", len(w.model.bericht) == n2, str(len(w.model.bericht)))
    del w.plotter.screenshot
    _aufraeumen(w, app)


# ---------------------------------------------------------------------------
# 6. Mit geaenderter Maske haelt der Zweigklick an der Leiste (13m)
# ---------------------------------------------------------------------------
def test_geaenderte_maske_haelt():
    from PySide6 import QtWidgets
    w, app = _fenster()
    w.load_example("hall")
    _ruhe(app)
    _aufraeumen(w, app)
    x_alt = float(w.model.nodes[1][0])
    w._objektmaske("knoten", "1")
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("x", 7.5)
    _ruhe(app)
    vorher = _auswahl(w)
    _klick(w, app, _zweig(w.baum, "Linien", "linien"))
    leiste = getattr(w, "aenderungsleiste", None)
    check("geänderte Maske „Knoten K1“, Klick auf den Zweig „Linien“: die Maske bleibt, oben die Leiste",
          _maske(w) is mk and leiste is not None and leiste.isVisible() and _auswahl(w) == vorher
          and float(w.model.nodes[1][0]) == x_alt,
          f"{getattr(_maske(w), 'titel', None)} Leiste {leiste is not None and leiste.isVisible()}")
    b = next((x for x in leiste.findChildren(QtWidgets.QPushButton) if x.text() == "Verwerfen"), None) \
        if leiste is not None else None
    if b is not None:
        b.click()
        _ruhe(app)
    mk2 = _uebersicht(w)
    check("… „Verwerfen“: danach die Übersicht „Linien“, x unverändert, die Auswahl auch",
          mk2 is not None and mk2.titel == "Linien" and float(w.model.nodes[1][0]) == x_alt
          and _auswahl(w) == vorher, f"{getattr(_maske(w), 'titel', None)}")
    _aufraeumen(w, app)


# ---------------------------------------------------------------------------
# 7. Texte: Hinweise an den Zweigen, Docstring, Handbuch
# ---------------------------------------------------------------------------
def test_texte():
    from statik3d.gui import design as dsg
    w, app = _fenster()
    _reiches_modell(w, app)
    tips = {it.text(0): it.toolTip(0) for it in _alle(w.baum) if _ist_zweig(it)}
    alt = [t for t, tip in tips.items() if "Klick wählt alle" in tip or "Klick öffnet die Maske" in tip
           or "Doppelklick übernimmt" in tip or "Klick wählt die Objekte" in tip or "Klick bearbeitet" in tip]
    check("kein Hinweis an einem Zweig verspricht noch Auswahl oder Maske beim Klick", not alt, str(alt))
    check("… der Hinweis am Zweig „Knoten“ nennt die Übersicht und den Doppelklick",
          "Übersicht" in tips.get("Knoten", "") and "Doppelklick" in tips.get("Knoten", ""), tips.get("Knoten", ""))
    doc = dsg.Modellbaum.__doc__ or ""
    check("Docstring des Baums: ein Zweigklick wählt nichts, Doppelklick legt nicht an",
          "waehlt nichts" in doc and "Anlegemaske" in doc, doc[:120])
    from tests.handbuch import absatz
    a = absatz("**Ein Klick auf einen Zweig wählt nichts.**")
    check("Handbuch: der Zweigklick zeigt die Übersicht mit Liste und wählt nichts",
          "Übersicht" in a and "Liste" in a and "weitere" in a and "Bis zum 03.10.2026" in a, a[:100])
    d = absatz("**Ein Doppelklick auf einen Zweig**")
    check("Handbuch: Doppelklick mit den Ausnahmen Knoten, Layer, Unterlagen, Linien- und Flächenlager, "
          "Bericht mit „Neu: Berichtsbild“",
          "Layer" in d and "Unterlagen" in d and "Berichtsbild" in d and "Knoten" in d, d[:100])
    _aufraeumen(w, app)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    tests = [test_jeder_zweig_waehlt_nichts, test_ergebniszweige, test_uebersicht_mit_liste,
             test_knoten_wie_der_zweig, test_listenklick_wie_baumklick, test_doppelklick_anlegemaske,
             test_lastfaelle_kombinationen_bericht, test_geaenderte_maske_haelt, test_texte]
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
