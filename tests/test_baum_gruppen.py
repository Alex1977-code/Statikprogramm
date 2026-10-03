"""
Der Modellbaum nach Gruppen (Teilpaket 8c der Oberflaechenplanung, 03.10.2026).

Antworten des Anwenders vom 24.09.2026 (PLAN-OBERFLAECHE-2026-09-24.md):

* 2. „Stab“ im Sinn von RFEM: der Zweig „Stäbe“ zeigt die Stäbe mit Nachweis,
  die FE-Stabelemente stehen unter „FE-Netz“; das Register „Stäbe“ unten heißt
  „Elemente“;
* 3. der Zweig „Knoten“ zeigt nur Konstruktionsknoten, das FE-Netz steht als
  eine Zählzeile;
* 4. der Baum ist nach Gruppen geordnet, Eigenschaften vor der Geometrie,
  Nachweise gebündelt.

Geprüft werden die Reihenfolge der Gruppen und ihrer Zweige, der Platz für
„Detailmodelle (Volumen)“, dass kein früherer Zweig verloren geht (Arten und
Einträge am Stand 68db45b gezählt), die Knoten an einem vernetzten Modell,
Stäbe und Stabelemente am richtigen Ort, das Register „Elemente“ samt
Baumklick und der Aufklappzustand nach ``refresh_all``.

Nachbesserung nach der Gegenprüfung (03.10.2026): der Zweig „Knoten“
versteckt keinen Knoten, an dem eine Last, ein Lager, eine Punktmasse, ein
Dämpfer, ein Spaltelement, eine Lasteinleitung, ein starrer Körper oder eine
Feder hängt, und keinen Knoten einer Stabkette (Beispiele „frame“, „contact“,
„hall“, vernetzte Platte; Kriterium in statik3d.knotenrollen); der Stand
„Konstruktionsknoten/alle Knoten“ hält eine Auswahl fest; der Zwischenspeicher
hält zwei Modelle; der Baum braucht pyvista nicht.

Aufruf:  python -m tests.test_baum_gruppen
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_baum_gruppen_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


# ---------------------------------------------------------------------------
# Hilfen: nur ueber Datenrollen und Texte, damit sie auch am Stand vor der
# Aenderung laufen (Gegenprobe)
# ---------------------------------------------------------------------------
def _element(it):
    from PySide6 import QtCore
    art = str(it.data(0, QtCore.Qt.UserRole) or "")
    key = it.data(0, QtCore.Qt.UserRole + 1)
    return art, (str(key) if key is not None else it.text(0))


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


def _kinder(it):
    return [it.child(i) for i in range(it.childCount())]


def _zweig(baum, text, art=None):
    """Der erste Zweig (kein Eintrag) mit diesem Text, sonst None."""
    for i in _alle(baum):
        if i.text(0) == text and not _ist_eintrag(i) and (art is None or _element(i)[0] == art):
            return i
    return None


def _unter(eltern, text):
    for k in _kinder(eltern) if eltern is not None else []:
        if k.text(0) == text:
            return k
    return None


def _reiches_modell():
    """Hallenrahmen mit allem, was einen eigenen Zweig erzeugt (wie die Probe
    am Stand 68db45b, aus der ARTEN_VORHER und EINTRAEGE_VORHER stammen)."""
    from statik3d.examples_lib import build_example
    from statik3d.model import Flaeche, Volumenkoerper
    from statik3d.wasserdruck import Wasserdruck
    from statik3d.schweissnaehte import Schweissnaht
    m = build_example("hall")
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
    m.add_fatigue_load("FL1", "LF1")
    return m


STELLUNGEN = [{"name": "S1", "winkel": 0.0}]
ERGEBNISSE = {"Lastfälle": [("LF1", "3,2 mm", "LF1", "Lastfall LF1")]}


def _baum(m, hoehe=600):
    from statik3d.gui import design as dsg
    app = _app()
    b = dsg.Modellbaum()
    b.resize(360, hoehe)
    b.show()
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    app.processEvents()
    return b, app


# ---------------------------------------------------------------------------
# 1. Gruppen und ihre Reihenfolge
# ---------------------------------------------------------------------------
GRUPPEN_SOLL = ["Eigenschaften", "Geometrie", "Lager und Verbindungen", "Einwirkungen", "FE-Netz",
                "Systeme und Stellungen", "Nachweise", "Ergebnisse", "Bericht und Unterlagen",
                "Hilfsobjekte"]
#: Die Zweige je Gruppe am reichen Modell, in dieser Folge
ZWEIGE_SOLL = {
    "Eigenschaften": ["Werkstoffe", "Querschnitte", "Dicken"],
    "Geometrie": ["Knoten", "Linien", "Stäbe", "Flächen", "Volumen"],
    "Lager und Verbindungen": ["Lager", "Verbindungen", "Gelenke", "Liniengelenke", "Kontaktbedingungen"],
    "Einwirkungen": ["Lastfälle", "Kombinationen", "Ermüdungslasten", "Lastgenerierer"],
    "FE-Netz": ["Netzknoten", "Stabelemente", "Flächenelemente", "Volumenelemente"],
    "Systeme und Stellungen": ["Subsysteme", "Stellungen", "Situationen"],
    "Nachweise": ["Schweißnähte", "Anschlüsse", "Verformungsnachweise", "Beulfelder",
                  "Volumenbereiche", "Lasteinleitung"],
    "Bericht und Unterlagen": ["Bericht", "Unterlagen"],
    "Hilfsobjekte": ["Bemaßungen", "Layer"],
}


def test_reihenfolge_der_gruppen():
    from statik3d.gui import design as dsg
    m = _reiches_modell()
    b, app = _baum(m)
    wurzel = b.topLevelItem(0)
    oben = [k.text(0) for k in _kinder(wurzel)]
    check("oberste Ebene: Eigenschaften vor Geometrie, Lager, Einwirkungen, FE-Netz, Stellungen, "
          "Nachweise, Ergebnisse, Bericht, Hilfsobjekte", oben == GRUPPEN_SOLL, str(oben))
    nicht_fett = [k.text(0) for k in _kinder(wurzel) if not k.font(0).bold()]
    check("jede Gruppe der obersten Ebene steht fett", not nicht_fett, str(nicht_fett))
    for gruppe, soll in ZWEIGE_SOLL.items():
        g = _unter(wurzel, gruppe)
        ist = [k.text(0) for k in _kinder(g) if not _ist_eintrag(k)] if g is not None else None
        check(f"Gruppe „{gruppe}“: {', '.join(soll)}", ist == soll, str(ist))
    gruppen = getattr(dsg.Modellbaum, "GRUPPEN", None)
    check("die Reihenfolge steht an einer Stelle (Modellbaum.GRUPPEN) und der Baum folgt ihr",
          gruppen is not None and [t for _k, t in gruppen] == oben, str(gruppen))
    if gruppen is not None:
        g = getattr(b, "gruppe", None)
        gef = {k: (g(k).text(0) if g is not None and g(k) is not None else None) for k, _t in gruppen}
        check("Modellbaum.gruppe(Kennung) findet jede Gruppe",
              all(gef[k] == t for k, t in gruppen), str(gef))
    # Platz fuer „Detailmodelle (Volumen)“ (Vorgabe FCM-Volumenloeser, Abschnitt 15.1:
    # „auf gleicher Ebene wie die Stellungen als Subsysteme“)
    folge = getattr(dsg.Modellbaum, "SYSTEM_ZWEIGE", None)
    check("Platz für „Detailmodelle (Volumen)“: nach den Subsystemen, vor den Stellungen",
          folge is not None and list(folge) == ["subsysteme", "detailmodelle", "stellungen", "situationen"],
          str(folge))
    g = _unter(wurzel, "Systeme und Stellungen")
    arten = [_element(k)[0] for k in _kinder(g)] if g is not None else []
    check("… die gebauten Zweige der Gruppe folgen dieser Reihenfolge (Detailmodelle noch nicht gebaut)",
          folge is not None and arten == [a for a in folge if a != "detailmodelle"], str(arten))
    b.close()


# ---------------------------------------------------------------------------
# 2. Nichts geht verloren: Arten und Eintraege wie am Stand 68db45b
# ---------------------------------------------------------------------------
#: Zweigarten am reichen Modell, Stand 68db45b (Probe vom 03.10.2026)
ARTEN_VORHER = {
    "anschluesse", "anschluss_neu", "bemassung_neu", "bemassungen", "bericht", "bericht_neu",
    "beulfelder", "daempfer", "dicken", "ergebnisse", "ermuedungslast_neu", "ermuedungslasten",
    "federn", "flaechen", "flaechenlager", "gelenk_neu", "gelenke", "generierer", "geoflaechen",
    "geokoerper", "grenzschichten", "knoten", "kombinationen", "kontakt", "kontaktbedingung_neu",
    "kontaktbedingungen", "lager", "lasteinleitung", "lastfaelle", "layer_neu", "layerliste",
    "linien", "liniengelenke", "linienlager", "modell", "punktmassen", "querschnitte",
    "schweissnaehte", "schweissnaht_neu", "situation_neu", "situationen", "stabelemente", "staebe",
    "starrkoerper", "stellung_neu", "stellungen", "subsystem_neu", "subsysteme", "unterlage_neu",
    "unterlagen", "verformung_neu", "verformungen", "volumen", "volumenbereiche", "wasserdruck_neu",
    "werkstoffe", "wind_neu"}
#: Zahl der Eintraege je Art, Stand 68db45b (alle 19 Knoten der Halle sind Konstruktionsknoten)
EINTRAEGE_VORHER = {
    "beulfeld": 1, "daempfer": 1, "ergebnis": 1, "ergebnisgruppe": 1, "ermuedungslast": 2,
    "feder": 1, "flaechenlager_einzeln": 1, "geoflaeche": 1, "geokoerper_einzeln": 1,
    "grenzschicht": 1, "knoten": 19, "kombination": 72, "lager_einzeln": 21, "lastart": 6,
    "lasteinleitung_einzeln": 1, "lastfall": 5, "liniengelenk": 1, "linienlager_einzeln": 1,
    "punktmasse": 1, "querschnitt": 2, "schweissnaht": 1, "situation": 1, "stab": 3,
    "stabelement": 18, "starrkoerper": 1, "stellung": 1, "subsystem": 1, "volumenbereich": 1,
    "wasserdruck": 1, "werkstoff": 1}


def test_nichts_geht_verloren():
    m = _reiches_modell()
    b, app = _baum(m)
    zweige, eintraege = {}, {}
    for i in _alle(b):
        art, name = _element(i)
        (eintraege if _ist_eintrag(i) else zweige).setdefault(art, []).append(name)
    fehlt = sorted(ARTEN_VORHER - set(zweige))
    check("jede frühere Zweigart steht noch im Baum", not fehlt, str(fehlt))
    neu = sorted(set(zweige) - ARTEN_VORHER)
    check("neu ist nur die Zählzeile „Netzknoten“ (die Gruppen tragen die Art „modell“)",
          neu == ["netzknoten"], str(neu))
    anders = {a: (n, len(eintraege.get(a, []))) for a, n in EINTRAEGE_VORHER.items()
              if len(eintraege.get(a, [])) != n}
    check("jede Eintragsart hat so viele Einträge wie vorher", not anders, str(anders))
    check("… mit denselben Schlüsseln: Stäbe (Namen) und Stabelemente (Nummern)",
          sorted(eintraege.get("stab", [])) == sorted(m.members)
          and eintraege.get("stabelement") == [str(i) for i, e in enumerate(m.elements)
                                                if e.typ in ("beam", "truss", "seil")],
          f"{eintraege.get('stab')} / {len(eintraege.get('stabelement', []))}")
    neue_eintraege = sorted(set(eintraege) - set(EINTRAEGE_VORHER))
    check("keine neue Eintragsart", not neue_eintraege, str(neue_eintraege))
    b.close()


# ---------------------------------------------------------------------------
# 3. Das Hauptfenster
# ---------------------------------------------------------------------------
def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from statik3d.gui.main import MainWindow
    app = _app()
    w = MainWindow()
    w.resize(1500, 900)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    w.error = lambda msg, *a, **k: (w.fehler_liste.append(str(msg)),
                                    w.log.appendPlainText("FEHLER: " + str(msg)))
    _FENSTER.update(w=w, app=app)
    return w, app


def _vernetztes_modell(w, app, objekte=False):
    """Platte 4 m x 2 m aus vier Linien, vernetzt; dazu ein Stab aus zwei
    Elementen und ein Knotenlager. ``objekte``: an je einem reinen Netzknoten
    eine Knotenlast, eine Punktmasse, ein Dämpfer, ein einseitiges Lager, ein
    Spaltelement, eine Lasteinleitung, ein Slave eines starren Körpers und ein
    Federende; zurück kommt dann auch {Objekt: Knoten}."""
    w.new_model()
    app.processEvents()
    m = w.model
    mat = list(m.materials)[0]
    dicke = list(m.shells)[0]
    sec = list(m.sections)[0]
    ids = [m.add_node(0, 0, 0), m.add_node(4, 0, 0), m.add_node(4, 2, 0), m.add_node(0, 2, 0)]
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
        m.add_line(f"L{i}", [ids[a], ids[b]])
    f = m.add_flaeche("F1", ["L0", "L1", "L2", "L3"], dicke=dicke, material=mat, teilung=[4, 4])
    w._vernetzen([f], [])
    oben = m.add_node(0, 0, 1)
    spitze = m.add_node(0, 0, 2)
    e1 = m.add_element("beam", [ids[0], oben], mat, sec)
    e2 = m.add_element("beam", [oben, spitze], mat, sec)
    m.add_member("St1", [e1, e2])
    m.support(ids[1], "all", name="Lager A")
    an = {}
    if objekte:
        from statik3d import knotenrollen as kr
        rein = [int(n) for n in np.flatnonzero(kr.netzknoten_maske(m))]
        lc = next(iter(m.load_cases))
        frei = [m.add_node(9, 0, float(k)) for k in range(3)]
        an["Knotenlast"] = rein[0]
        m.load_node(rein[0], Fz=-1e3, case=lc)
        an["Punktmasse"] = rein[1]
        m.add_punktmasse(rein[1], 250.0, [1.0, 2.0, 3.0])
        an["Dämpfer"] = rein[2]
        m.add_daempfer(rein[2], -1, [40.0, 0, 0, 0, 0, 0])
        an["einseitiges Lager"] = rein[3]
        m.add_contact_support(rein[3], (0, 0, 1))
        an["Spaltelement"] = rein[4]
        m.add_gap_element(rein[4], frei[0], direction=(0, 0, -1), gap=0.003)
        an["Lasteinleitung"] = rein[5]
        m.add_lasteinleitung("LE1", rein[5])
        an["Slave eines starren Körpers"] = rein[6]
        m.add_starrkoerper(frei[1], [rein[6]], "RBE2")
        an["Federende"] = rein[7]
        m.add_feder_prop("FD", [1e6, 1e6, 1e6, 0, 0, 0])
        m.add_element("feder", [rein[7], frei[2]], mat, "FD")
        an["unbelegter Netzknoten"] = rein[8]
    w.refresh_all()
    app.processEvents()
    if objekte:
        return m, ids, oben, spitze, an
    return m, ids, oben, spitze


def test_knoten_nur_konstruktion():
    from statik3d import knotenrollen as kr
    from statik3d.gui import viewport as vp
    w, app = _fenster()
    m, ids, oben, spitze, an = _vernetztes_modell(w, app, objekte=True)
    b = w.baum
    kons = {int(i) for i in kr.konstruktionsknoten(m)}
    check("Vorbereitung: die Platte ist vernetzt, es gibt Netz- und Konstruktionsknoten",
          len(m.flaechen["F1"].elemente) > 0 and set(ids) <= kons and spitze in kons
          and 0 < len(kons) < m.nn,
          f"{len(m.flaechen['F1'].elemente)} Elemente, {len(kons)} von {m.nn} Knoten Konstruktion")
    check("Ansicht und Baum fragen dasselbe Kriterium (viewport = knotenrollen)",
          {int(i) for i in vp.konstruktionsknoten(m)} == kons)
    kn = _zweig(b, "Knoten", "knoten")
    eintraege = {int(_element(k)[1]) for k in _kinder(kn) if _ist_eintrag(k)} if kn is not None else set()
    check("Zweig „Knoten“ zeigt genau die Konstruktionsknoten",
          eintraege == kons, f"{len(eintraege)} Einträge, {len(kons)} Konstruktionsknoten, "
                             f"zu viel {sorted(eintraege - kons)[:5]}, fehlt {sorted(kons - eintraege)[:5]}")
    fehlt = sorted(was for was, n in an.items() if was != "unbelegter Netzknoten" and n not in eintraege)
    check("… mit jedem Netzknoten, an dem Last, Punktmasse, Dämpfer, einseitiges Lager, Spaltelement, "
          "Lasteinleitung, starrer Körper oder Feder hängt", not fehlt and len(an) == 9, str(fehlt))
    check("… mit dem Zwischenknoten des Stabs aus zwei Elementen (Stabketten sind Konstruktion)",
          oben in eintraege, str(oben))
    check("… und ohne den Netzknoten, an dem nichts hängt",
          an["unbelegter Netzknoten"] not in eintraege, str(an["unbelegter Netzknoten"]))
    check("… sein Zähler nennt die Konstruktionsknoten", kn is not None and kn.text(1) == str(len(kons)),
          kn.text(1) if kn is not None else "")
    netz = _zweig(b, "FE-Netz")
    zz = _unter(netz, "Netzknoten")
    check("unter „FE-Netz“ stehen die Netzknoten als eine Zählzeile ohne Einträge",
          zz is not None and zz.childCount() == 0 and not _ist_eintrag(zz)
          and zz.text(1) == str(m.nn - len(kons)),
          f"{zz.text(1) if zz is not None else None} statt {m.nn - len(kons)}")
    n_sch = sum(1 for e in m.elements if e.typ.startswith("shell"))
    fe = _unter(netz, "Flächenelemente")
    check("… daneben die Flächenelemente mit ihrer Zahl", fe is not None and fe.text(1) == str(n_sch),
          fe.text(1) if fe is not None else "")
    w._baum_geklickt("netzknoten", "Netzknoten")
    app.processEvents()
    tu = w.tab_unten
    check("Klick auf die Zählzeile holt die Knotentabelle (dort stehen alle Knoten)",
          tu.tabText(tu.currentIndex()) == "Knoten", tu.tabText(tu.currentIndex()))


def test_staebe_im_sinn_von_rfem():
    w, app = _fenster()
    w.load_example("hall")
    app.processEvents()
    m = w.model
    b = w.baum
    geo = _zweig(b, "Geometrie")
    st = _unter(geo, "Stäbe")
    check("Geometrie → „Stäbe“ sind die Stäbe mit Nachweis (Art „staebe“)",
          st is not None and _element(st)[0] == "staebe" and st.text(1) == str(len(m.members)),
          str(_element(st) if st is not None else None))
    namen = sorted(_element(k)[1] for k in _kinder(st) if _ist_eintrag(k)) if st is not None else []
    check("… darunter genau die Stäbe, keine Stabelemente und keine Unterzweige",
          st is not None and namen == sorted(m.members) and st.childCount() == len(m.members),
          str(namen))
    netz = _zweig(b, "FE-Netz")
    se = _unter(netz, "Stabelemente")
    n_stab = [str(i) for i, e in enumerate(m.elements) if e.typ in ("beam", "truss", "seil")]
    check("FE-Netz → „Stabelemente“ (Art „stabelemente“) mit allen Stabelementen E…",
          se is not None and _element(se)[0] == "stabelemente"
          and [_element(k)[1] for k in _kinder(se)] == n_stab
          and all(k.text(0).startswith("E") for k in _kinder(se)),
          f"{se.childCount() if se is not None else None} von {len(n_stab)}")
    nw = _zweig(b, "Nachweise")
    check("die Schweißnähte stehen gebündelt unter „Nachweise“",
          _unter(nw, "Schweißnähte") is not None and _element(_unter(nw, "Schweißnähte"))[0] == "schweissnaehte")
    check("„Stäbe mit Nachweis“ gibt es nicht mehr als eigenen Zweig (er heißt „Stäbe“)",
          _zweig(b, "Stäbe mit Nachweis") is None and st is not None)
    # Seit 8b (03.10.2026) waehlt der Klick auf einen Zweig nichts; die
    # Uebersicht nennt die Stäbe bzw. Stabelemente in ihrer Liste
    w.clear_selection()
    app.processEvents()
    w._baum_geklickt("staebe", "Stäbe")
    app.processEvents()
    mk = w.maskenrand.maske
    from PySide6 import QtWidgets
    lw = mk.findChild(QtWidgets.QTreeWidget, "uebersichtliste") if mk is not None else None
    zeilen = [lw.topLevelItem(i).text(0) for i in range(lw.topLevelItemCount())] if lw is not None else []
    check("Klick auf „Stäbe“: Übersicht „Stäbe“ mit den Stäben in der Liste, gewählt wird nichts",
          not w.sel_staebe and mk is not None and mk.titel == "Stäbe" and sorted(zeilen) == sorted(m.members),
          f"{w.sel_staebe} {mk.titel if mk else None} {zeilen}")
    w._baum_geklickt("stabelemente", "Stabelemente")
    app.processEvents()
    mk = w.maskenrand.maske
    lw = mk.findChild(QtWidgets.QTreeWidget, "uebersichtliste") if mk is not None else None
    zeilen = [lw.topLevelItem(i).text(0) for i in range(lw.topLevelItemCount())] if lw is not None else []
    check("Klick auf „Stabelemente“: Übersicht „Stabelemente“ mit den Stabelementen, nichts leuchtet",
          not w.leuchtet and mk is not None and mk.titel == "Stabelemente"
          and zeilen == [f"E{i}" for i in n_stab][:len(zeilen)] and zeilen,
          f"{len(w.leuchtet)} {mk.titel if mk else None} {zeilen[:3]}")
    check("Rechtsklick → Neu heißt „Stab“ an den Stäben und „Stabelement“ an den Stabelementen",
          b.NEU_ARTEN.get("staebe") == "Stab" and b.NEU_ARTEN.get("stabelemente") == "Stabelement",
          f"{b.NEU_ARTEN.get('staebe')} / {b.NEU_ARTEN.get('stabelemente')}")
    w.clear_selection()


def test_register_elemente():
    w, app = _fenster()
    w.load_example("hall")
    app.processEvents()
    tu = w.tab_unten
    modell = tu.tabellen("Modell")
    check("Gruppe Modell: das Register heißt „Elemente“", "Elemente" in modell, str(modell))
    check("… und nicht mehr „Stäbe“", "Elemente" in modell and "Stäbe" not in modell, str(modell))
    check("„Elemente“ ist die Elementtabelle (auch ihr CSV-Name)",
          w.tabelle_zeigen("Elemente") and tu.currentWidget() is not None
          and tu.currentWidget().isAncestorOf(w.tbl_elem) and w.tbl_elem.titel == "Elemente",
          f"{tu.tabText(tu.currentIndex())} {w.tbl_elem.titel!r}")
    for art, text in (("stabelemente", "Stabelemente"), ("flaechen", "Flächenelemente"),
                      ("volumen", "Volumenelemente")):
        w.tabelle_zeigen("Knoten")
        app.processEvents()
        w._baum_geklickt(art, text)
        app.processEvents()
        check(f"Baumklick „{text}“ holt das Register „Elemente“",
              tu.tabText(tu.currentIndex()) == "Elemente", tu.tabText(tu.currentIndex()))
    alle = {tu.tabText(k) for k in range(tu.count())}
    fehlt = sorted({v for v in w.BAUM_TABELLE.values() if v not in alle})
    check("jede Tabelle, die der Baum nennt (BAUM_TABELLE), gibt es unten", not fehlt, str(fehlt))
    w.clear_selection()


def _pfade(baum):
    return {baum.pfad_von(i): i.isExpanded() for i in _alle(baum) if i.childCount()}


def test_aufklappzustand_nach_refresh_all():
    w, app = _fenster()
    w.load_example("hall")
    app.processEvents()
    b = w.baum
    b.topLevelItem(0).setExpanded(True)
    for gruppe, zweig in (("Geometrie", "Stäbe"), ("FE-Netz", "Stabelemente"), ("Nachweise", "Schweißnähte"),
                          ("Hilfsobjekte", "Bemaßungen")):
        g = _zweig(b, gruppe)
        if g is not None:
            g.setExpanded(True)
            z = _unter(g, zweig)
            if z is not None:
                z.setExpanded(True)
    lv = _zweig(b, "Lager und Verbindungen")
    if lv is not None:
        lv.setExpanded(False)
    riegel = None
    st = _unter(_zweig(b, "Geometrie"), "Stäbe")
    for k in _kinder(st) if st is not None else []:
        if _element(k) == ("stab", "Riegel"):
            riegel = k
    if riegel is not None:
        b.clearSelection()
        riegel.setSelected(True)
        b.setCurrentItem(riegel)
    app.processEvents()
    vorher = _pfade(b)
    check("Vorbereitung: Gruppen und Zweige darin aufgeklappt, „Lager und Verbindungen“ zu, Riegel gewählt",
          lv is not None and riegel is not None and sum(vorher.values()) >= 8, f"offen {sum(vorher.values())}")
    # alte Pfade (vor 8c hingen Knoten und Stäbe direkt an der Wurzel) verfallen still
    alt = ((("modell", ""), ("knoten", "")), (("modell", ""), ("stabelemente", ""), ("staebe", "")))
    for p in alt:
        b._offen[p] = True
    w.refresh_all()
    app.processEvents()
    nachher = _pfade(b)
    falsch = sorted({p[-1] for p in vorher if nachher.get(p) != vorher[p]})
    check("refresh_all: jeder Zweig behält seinen Zustand, auch in den neuen Gruppen", not falsch, str(falsch[:6]))
    cur = b.currentItem()
    check("refresh_all: der gewählte Stab bleibt gewählt",
          cur is not None and _element(cur) == ("stab", "Riegel") and cur.isSelected(),
          str(_element(cur) if cur is not None else None))
    kn = _zweig(b, "Knoten", "knoten")
    check("ein gemerkter Zustand mit altem Pfad wirkt nicht (Knoten bleibt zu, kein Fehler)",
          kn is not None and not kn.isExpanded() and not any(b.pfad_von(i) in alt for i in _alle(b)),
          str(kn.isExpanded() if kn is not None else None))
    # Grundzustand: jeder Pfad darin gibt es im Baum, und mit den Gruppen ist Lager und Stellungen zu sehen
    b.zustand_vergessen()
    w.refresh_all()
    app.processEvents()
    pfade = {b.pfad_von(i) for i in _alle(b) if i.childCount()}
    tot = sorted(p[-1] for p in b.GRUNDZUSTAND_OFFEN if p not in pfade)
    check("jeder Pfad des Grundzustands steht im Baum (kein toter Eintrag nach dem Umbau)", not tot, str(tot))
    offen = sorted(i.text(0) for i in _alle(b) if i.childCount() and i.isExpanded())
    soll = sorted([b.topLevelItem(0).text(0), "Geometrie", "Lager und Verbindungen", "Lager",
                   "Systeme und Stellungen", "Stellungen"])
    check("Grundzustand: Wurzel, Geometrie, Lager und Verbindungen mit Lager, Systeme und Stellungen "
          "mit Stellungen offen", offen == soll, str(offen))


# ---------------------------------------------------------------------------
# 4. Zeit: keine neue Schleife je Aufbau
# ---------------------------------------------------------------------------
def test_zaehlzeile_kostet_keine_schleife():
    """Der teure Teil des Kriteriums (die Knoten der Flächen- und
    Körpernetze) kommt aus dem Zwischenspeicher (knotenrollen.netz_teile,
    einmal je Netzstand); ein zweiter Aufbau rechnet ihn nicht neu. Der
    Speicher hält zwei Modelle - das Modell und seine Stellungskopie
    verdrängen sich nicht. Und der Zweig baut nur die Konstruktionsknoten."""
    import copy
    from statik3d import knotenrollen as kr
    w, app = _fenster()
    m, ids, oben, spitze = _vernetztes_modell(w, app)
    b = w.baum
    b.fuellen(m)
    vorher = id(kr._ZWISCHENSPEICHER.get(id(m), (None, None))[1])
    b.fuellen(m)
    nachher = id(kr._ZWISCHENSPEICHER.get(id(m), (None, None))[1])
    check("zweiter Aufbau: die Netzteile kommen aus dem Zwischenspeicher",
          id(m) in kr._ZWISCHENSPEICHER and vorher == nachher, f"{vorher} -> {nachher}")
    kopie = copy.deepcopy(m)
    kr.konstruktionsknoten(kopie)
    b.fuellen(m)
    check("eine Stellungskopie verdrängt das Modell nicht (zwei Modelle im Speicher)",
          id(kopie) in kr._ZWISCHENSPEICHER and id(m) in kr._ZWISCHENSPEICHER
          and id(kr._ZWISCHENSPEICHER[id(m)][1]) == vorher, str(len(kr._ZWISCHENSPEICHER)))
    kn = _zweig(b, "Knoten", "knoten")
    n_kons = len(kr.konstruktionsknoten(m))
    check("der Zweig „Knoten“ baut nur so viele Zeilen, wie es Konstruktionsknoten gibt",
          kn is not None and kn.childCount() == n_kons < m.nn, f"{kn.childCount() if kn else None} von {m.nn}")


def test_knoten_an_den_beispielen():
    """Gegenprüfung 03.10.2026: am Beispiel „contact“ fehlte der einzige
    Lastknoten K10, am Beispiel „frame“ schrumpfte der Zweig nach „Stäbe
    automatisch erkennen“ von 17 auf 4 - die Zwischenknoten jeder Stabkette
    galten als Netz."""
    from statik3d.examples_lib import build_example

    def knoten(b):
        kn = _zweig(b, "Knoten", "knoten")
        return {int(_element(k)[1]) for k in _kinder(kn) if _ist_eintrag(k)} if kn is not None else set()

    m = build_example("frame")
    b, app = _baum(m)
    vorher = knoten(b)
    m.auto_members()
    b.fuellen(m)
    app.processEvents()
    nachher = knoten(b)
    check("frame: alle 17 Knoten im Zweig, auch nach „Stäbe automatisch erkennen“",
          len(vorher) == m.nn == 17 and nachher == vorher and len(m.members) >= 3,
          f"vorher {len(vorher)}, nachher {len(nachher)}, Stäbe {len(m.members)}")
    m = build_example("contact")
    b.fuellen(m)
    app.processEvents()
    last = {int(l.node) for lc in m.load_cases.values() for l in lc.nodal_loads}
    k = knoten(b)
    check("contact: der Lastknoten K10 und alle 14 Knoten stehen im Zweig",
          last == {10} and last <= k and len(k) == m.nn == 14, f"{sorted(k)}")
    m = build_example("hall")
    b.fuellen(m)
    app.processEvents()
    check("hall: alle 19 Knoten stehen im Zweig", len(knoten(b)) == m.nn == 19, str(len(knoten(b))))
    b.close()


def test_stand_haelt_die_auswahl():
    """Der Stand „Konstruktionsknoten/alle Knoten“ (UserRole+4) am Zweig
    „Knoten“: ein Schalenelement samt seinem nun freien Knoten löschen,
    dessen Nummer vor dem gewählten Knoten liegt. Die Zahl der
    Konstruktionsknoten bleibt, die Nummern dahinter rücken auf. Danach darf
    nicht der Knoten gewählt sein, der jetzt die alte Nummer trägt
    (Ablauf der Gegenprüfung, stand_pruefung.py)."""
    from PySide6 import QtCore
    from statik3d import knotenrollen as kr
    from statik3d.gui import design as dsg
    w, app = _fenster()
    m, ids, oben, spitze = _vernetztes_modell(w, app)
    ka = m.add_node(20, 0, 0)
    m.add_node(21, 0, 0)
    m.add_node(22, 0, 0)
    b = dsg.Modellbaum()
    b.resize(360, 600)
    b.show()
    b.fuellen(m)
    app.processEvents()
    n_kons0, nn0 = len(kr.konstruktionsknoten(m)), m.nn
    ok = b.eintrag_waehlen("knoten", str(ka))
    xa = m.nodes[ka].copy()
    schalen = [i for i, e in enumerate(m.elements) if e.typ.startswith("shell")]
    zaehl = {}
    for i in schalen:
        for n in m.elements[i].nodes:
            zaehl[int(n)] = zaehl.get(int(n), 0) + 1
    linien = {int(n) for ln in m.lines.values() for n in ln.nodes}
    kand = next(((i, int(n)) for i in schalen for n in m.elements[i].nodes
                 if zaehl[int(n)] == 1 and int(n) not in linien and int(n) < ka), None)
    check("Vorbereitung: K_a gewählt, ein Knoten nur an einem Schalenelement gefunden",
          ok and kand is not None, str(kand))
    if kand is None:
        b.close()
        return
    e, _n = kand
    knoten_e = {int(x) for x in m.elements[e].nodes}
    m.elemente_loeschen([e])
    belegt = {int(x) for el in m.elements for x in el.nodes}
    m.knoten_loeschen_viele(sorted(knoten_e - belegt))
    n_kons1 = len(kr.konstruktionsknoten(m))
    check("Vorbereitung: gleich viele Konstruktionsknoten, weniger Knoten, Nummern gerückt",
          n_kons1 == n_kons0 and 1 <= nn0 - m.nn <= 2 and np.allclose(m.nodes[ka - (nn0 - m.nn)], xa),
          f"Konstruktion {n_kons0} -> {n_kons1}, Knoten {nn0} -> {m.nn}")
    b.fuellen(m)
    app.processEvents()
    gew = [(i.data(0, QtCore.Qt.UserRole), i.data(0, QtCore.Qt.UserRole + 1)) for i in b.selectedItems()]
    falsch = [k for a, k in gew if a == "knoten" and not np.allclose(m.nodes[int(k)], xa)]
    check("nach dem Neuaufbau ist kein nachgerückter Knoten gewählt (der Stand nennt auch alle Knoten)",
          not falsch, f"gewählt {gew}")
    b.close()


def test_kriterium_ohne_pyvista():
    """Der Baum fragt statik3d.knotenrollen, nicht die Ansicht: ein reiner
    Baumaufbau lädt pyvista nicht (bis 03.10.2026 zog er gui.viewport nach)."""
    import subprocess
    code = ("import sys; from PySide6 import QtWidgets; app = QtWidgets.QApplication([]); "
            "from statik3d.gui import design as d; from statik3d.examples_lib import build_example; "
            "b = d.Modellbaum(); b.fuellen(build_example('plate')); "
            "print('PYVISTA', 'pyvista' in sys.modules, 'statik3d.gui.viewport' in sys.modules)")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONUTF8="1")
    stamm = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lauf = subprocess.run([sys.executable, "-c", code], cwd=stamm, env=env, capture_output=True,
                          text=True, timeout=300)
    zeile = next((z for z in lauf.stdout.splitlines() if z.startswith("PYVISTA")), "")
    check("Baumaufbau ohne pyvista und ohne gui.viewport", zeile == "PYVISTA False False",
          zeile or lauf.stderr[-300:])


# ---------------------------------------------------------------------------
# 5. Handbuch
# ---------------------------------------------------------------------------
def test_handbuch():
    from tests.handbuch import absatz
    a = absatz("**Der Baum ist nach Gruppen geordnet**")
    check("Handbuch: Gruppen im Ablauf, Stab im Sinn von RFEM, Konstruktionsknoten, Zählzeile",
          "Eigenschaften" in a and "Hilfsobjekte" in a and "Stab mit Nachweis" in a
          and "Knoten der Konstruktion" in a and "Zählzeile" in a and "FE-Netz" in a, a[:80])
    check("Handbuch: Kriterium der Konstruktionsknoten (Stäbe, Lasten, Massen, Federn; geteilte Stabzüge)",
          "alle Knoten von Stäben" in a and "Punktmasse" in a and "Feder" in a
          and "geteilten Stabzugs" in a and "K10" in a, a[:80])
    check("Handbuch: … mit dem Stand vorher („Bis zum 03.10.2026 …“)",
          "Bis zum 03.10.2026 hingen Knoten, Linien, Stäbe" in a and "Stäbe mit Nachweis" in a, a[-120:])
    g = absatz("der Baum im Grundzustand.")
    check("Handbuch: Grundzustand mit Geometrie, Lager und Verbindungen, Systeme und Stellungen",
          "*Geometrie*" in g and "*Lager und Verbindungen*" in g and "Bis zum 03.10.2026" in g, g[:80])
    t = absatz("| Modell | Knoten, Linien, Flächen, Volumenkörper, Elemente")
    check("Handbuch: Tabelle „Elemente“ (bis 03.10.2026 „Stäbe“)",
          "Bis zum 03.10.2026 hieß sie „Stäbe“".lower() in t.lower(), t[:80])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    tests = [test_reihenfolge_der_gruppen, test_nichts_geht_verloren, test_knoten_nur_konstruktion,
             test_staebe_im_sinn_von_rfem, test_register_elemente, test_aufklappzustand_nach_refresh_all,
             test_zaehlzeile_kostet_keine_schleife, test_knoten_an_den_beispielen,
             test_stand_haelt_die_auswahl, test_kriterium_ohne_pyvista, test_handbuch]
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
