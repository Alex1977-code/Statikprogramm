"""
Der Modellbaum bleibt ruhig (Teilpaket 8a der Oberflaechenplanung, 02.10.2026).

Befund der Analyse vom 24.09.2026: nach jedem „Übernehmen“ klappen Stäbe,
Lager, Lastfälle und Ergebnisse wieder zu. Ursachen im Quelltext:

* der Baum merkte sich den Zustand ueber den **Text** des Eintrags und stellte
  nur acht fest verdrahtete Zweige wieder her;
* drei Namen (``st``, ``fl``, ``lg``) hielten je zwei verschiedene Zweige, so
  dass „Stäbe“, „Flächen“ und „Lager“ nie, „Stellungen“ mit der falschen
  Vorgabe und der „Lastgenerierer“ statt „Lager“ mit „offen“ behandelt wurden;
* Rollposition und gewählter Eintrag gingen mit jedem Neuaufbau verloren;
* ein neues Modell erbte den Zustand des vorigen, soweit der Text gleich war.

Geprueft wird der Baum allein (synthetische Modelle, schnell) und das echte
Hauptfenster offscreen (refresh_all, „Übernehmen“ einer Maske, Rückgängig,
Neu, Beispiel laden, Öffnen). Dazu die Schriftregel (grau = leer, normal =
gefüllt, fett nur für Gruppen) und das Warnzeichen an Volumen ohne Netz.

Aufruf:  python -m tests.test_baum_ruhig
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_baum_ruhig_"), "einstellungen.json")

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
# Hilfen: unabhaengig von den Namen im Baum selbst, damit sie auch am Stand
# vor der Aenderung laufen (Gegenprobe)
# ---------------------------------------------------------------------------
def _element(it):
    from PySide6 import QtCore
    art = str(it.data(0, QtCore.Qt.UserRole) or "")
    key = it.data(0, QtCore.Qt.UserRole + 1)
    return art, (str(key) if key is not None else it.text(0))


def _kennung(it):
    """Art und Schlüssel (bei Zweigen der feste Text) von der Wurzel an."""
    teile = []
    while it is not None:
        teile.append(_element(it))
        it = it.parent()
    return tuple(reversed(teile))


def _alle(baum):
    from PySide6 import QtWidgets
    out = []
    it = QtWidgets.QTreeWidgetItemIterator(baum)
    while it.value():
        out.append(it.value())
        it += 1
    return out


def _zweige(baum) -> dict:
    """{Kennung: aufgeklappt} aller Einträge, unter denen etwas hängt."""
    return {_kennung(i): i.isExpanded() for i in _alle(baum) if i.childCount()}


def _text_zu_kennung(baum) -> dict:
    return {i.text(0): _kennung(i) for i in _alle(baum) if i.childCount()}


def _finden(baum, text, art=None):
    for i in _alle(baum):
        if i.text(0) == text and (art is None or _element(i)[0] == art):
            return i
    return None


def _farbe(it):
    from PySide6 import QtGui
    v = it.data(0, 9)       # Qt.ForegroundRole
    return v.color().name() if isinstance(v, QtGui.QBrush) else None


def _reiches_modell():
    """Hallenrahmen mit allem, was zusätzliche Zweige erzeugt: Flächenlager
    (der Name ``fl`` war doppelt), Lastgenerierer (``lg``), Stellungen (``st``),
    Volumen und Flächen."""
    from statik3d.examples_lib import build_example
    from statik3d.model import Flaeche, Volumenkoerper
    from statik3d.wasserdruck import Wasserdruck
    m = build_example("hall")
    m.add_surface_support([0], name="FL1", uz=dict(typ="spring", stiffness=1e7))
    m.add_line_support([0, 1], name="LL1", uz=dict(typ="spring", stiffness=1e7))
    m.flaechen["F1"] = Flaeche("F1", ["L1"])
    m.koerper["V1"] = Volumenkoerper("V1", flaechen=["F1"] * 6, material="S355")
    m.wasserdruecke["W1"] = Wasserdruck("W1", h_ow=2.0)
    return m


STELLUNGEN = [{"name": "S1", "winkel": 0.0}, {"name": "S2", "winkel": 30.0}]
ERGEBNISSE = {"Lastfälle": [("LF1", "3,2 mm", "LF1", "Lastfall LF1"),
                            ("LF2", "1,1 mm", "LF2", "Lastfall LF2")]}


def _baum(hoehe=300):
    from statik3d.gui import design as dsg
    app = _app()
    b = dsg.Modellbaum()
    b.resize(320, hoehe)
    b.show()
    app.processEvents()
    return b, app


# ---------------------------------------------------------------------------
# 1. Aufklappzustand: jeder Zweig behält seinen Zustand
# ---------------------------------------------------------------------------
def test_jeder_zweig_behaelt_seinen_zustand():
    m = _reiches_modell()
    b, app = _baum()
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    zweige = [i for i in _alle(b) if i.childCount()]
    check("Vorbereitung: der Baum hat Zweige mit Kindern, auch Flächenlager und Lastgenerierer",
          len(zweige) >= 25 and _finden(b, "Flächenlager") is not None
          and _finden(b, "Lastgenerierer") is not None,
          f"{len(zweige)} Zweige")
    for muster, titel in ((lambda k: True, "alle offen"), (lambda k: k % 2 == 0, "jeder zweite offen"),
                          (lambda k: False, "alle zu")):
        zweige = [i for i in _alle(b) if i.childCount()]       # nach jedem Aufbau neu
        for k, i in enumerate(zweige):
            i.setExpanded(muster(k))
        vorher = _zweige(b)
        b.fuellen(m, STELLUNGEN, ERGEBNISSE)
        app.processEvents()
        nachher = _zweige(b)
        falsch = sorted({k[-1][1] for k in vorher if nachher.get(k) != vorher[k]})
        check(f"Aufklappzustand bleibt nach dem Neuaufbau, {titel}", not falsch,
              ("verändert: " + ", ".join(falsch[:8])) if falsch else f"{len(vorher)} Zweige")


def test_drei_doppelte_namen():
    """st, fl, lg: jeder der sechs Zweige behält seinen Zustand für sich allein."""
    m = _reiches_modell()
    b, app = _baum()
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    namen = ["Stäbe", "Flächen", "Flächenlager", "Lager", "Stellungen", "Lastgenerierer"]
    fehlt = [n for n in namen if _finden(b, n) is None]
    check("alle sechs Zweige sind da", not fehlt, str(fehlt))
    # je einer allein aufklappen, alle anderen zu: nach dem Neuaufbau genau er
    for name in namen:
        for i in _alle(b):
            if i.childCount():
                i.setExpanded(False)
        b.topLevelItem(0).setExpanded(True)
        _finden(b, name).setExpanded(True)
        b.fuellen(m, STELLUNGEN, ERGEBNISSE)
        app.processEvents()
        offen = sorted(i.text(0) for i in _alle(b)
                       if i.childCount() and i.isExpanded() and i.text(0) in namen)
        check(f"nur „{name}“ aufgeklappt: nach dem Neuaufbau genau das", offen == [name],
              f"offen: {offen}")


def test_gleicher_text_an_zwei_stellen():
    """„Lastfälle“ und „Kombinationen“ gibt es zweimal: als Zweig unter
    „Einwirkungen“ und als Gruppe unter „Ergebnisse“. Der Zustand gehört zum
    Pfad, nicht zum Text."""
    m = _reiches_modell()
    ergebnisse = {"Lastfälle": [("LF1", "3,2 mm", "LF1", "Lastfall LF1")],
                  "Kombinationen": [("GZT1", "5,1 mm", "GZT1", "Kombination GZT1")]}
    b, app = _baum()
    b.fuellen(m, STELLUNGEN, ergebnisse)
    for text in ("Lastfälle", "Kombinationen"):
        gleich = [i for i in _alle(b) if i.text(0) == text and i.childCount()]
        check(f"Vorbereitung: „{text}“ gibt es zweimal mit Kindern", len(gleich) == 2,
              str([_element(i)[0] for i in gleich]))
        if len(gleich) != 2:
            return
    # der Zweig unter „Einwirkungen“ offen, die Ergebnisgruppe zu - und umgekehrt
    for zweig_offen in (True, False):
        for text in ("Lastfälle", "Kombinationen"):
            for i in _alle(b):
                if i.text(0) == text and i.childCount():
                    i.setExpanded((_element(i)[0] != "ergebnisgruppe") == zweig_offen)
        vorher = _zweige(b)
        b.fuellen(m, STELLUNGEN, ergebnisse)
        app.processEvents()
        nachher = _zweige(b)
        falsch = sorted((k[-1][0], k[-1][1]) for k in vorher if nachher.get(k) != vorher[k])
        check("Zweig „Lastfälle“/„Kombinationen“ "
              + ("offen, Ergebnisgruppe zu" if zweig_offen else "zu, Ergebnisgruppe offen")
              + ": nach dem Neuaufbau unverändert", not falsch, str(falsch[:4]))


def test_wurzel_traegt_den_modellnamen_nicht_als_schluessel():
    m = _reiches_modell()
    b, app = _baum()
    b.fuellen(m, STELLUNGEN)
    b.topLevelItem(0).setExpanded(False)
    m.name = "Anderer Name"
    b.fuellen(m, STELLUNGEN)
    check("Modell umbenannt: die Wurzel bleibt, wie sie war (zu)",
          b.topLevelItem(0).text(0) == "Anderer Name" and not b.topLevelItem(0).isExpanded())


def test_pfade_sind_eindeutig():
    """Zwei Zweige mit gleichem Pfad teilten sich den Zustand."""
    m = _reiches_modell()
    b, app = _baum()
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    pfad = getattr(b, "pfad_von", None)
    check("der Baum nennt den Pfad eines Eintrags (Modellbaum.pfad_von)", pfad is not None)
    if pfad is None:
        return
    pfade = [pfad(i) for i in _alle(b) if i.childCount()]
    doppelt = sorted({p[-1] for p in pfade if pfade.count(p) > 1})
    check("alle Zweige mit Kindern haben einen eigenen Pfad", not doppelt, str(doppelt))
    check("… auch Eigenschaften und Einwirkungen (beide tragen die Art „modell“)",
          len(set(pfad(i) for i in _alle(b) if i.text(0) in ("Eigenschaften", "Einwirkungen"))) == 2,
          str([pfad(i)[-1] for i in _alle(b) if i.text(0) in ("Eigenschaften", "Einwirkungen")]))


# ---------------------------------------------------------------------------
# 2. Grundzustand nach Neu / Öffnen / Beispiel: nichts wird vererbt
# ---------------------------------------------------------------------------
def test_grundzustand_im_baum():
    m = _reiches_modell()
    b, app = _baum()
    vergessen = getattr(b, "zustand_vergessen", None)
    check("der Baum kann seinen Zustand vergessen (Modellbaum.zustand_vergessen)", vergessen is not None)
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    for i in _alle(b):
        if i.childCount():
            i.setExpanded(True)
    if vergessen is None:
        return
    vergessen()
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    app.processEvents()
    offen = sorted(i.text(0) for i in _alle(b) if i.childCount() and i.isExpanded())
    check("nach dem Vergessen gilt der Grundzustand: Wurzel, Lager und Stellungen offen, sonst zu",
          offen == sorted([m.name, "Lager", "Stellungen"]), str(offen))
    # und es bleibt ein ganz gewöhnlicher Zustand: der nächste Neuaufbau erhält ihn
    _finden(b, "Lager").setExpanded(False)
    _finden(b, "Knoten").setExpanded(True)
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    check("… danach wird wieder erhalten (Lager zu, Knoten offen)",
          not _finden(b, "Lager").isExpanded() and _finden(b, "Knoten").isExpanded())


# ---------------------------------------------------------------------------
# 3. Rollposition und gewählter Eintrag
# ---------------------------------------------------------------------------
def test_rollposition_folgt_dem_eintrag():
    m = _reiches_modell()
    b, app = _baum(260)
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    for name in ("Einwirkungen", "Lastfälle", "Kombinationen", "Lager", "Knotenlager"):
        _finden(b, name, None if name != "Lastfälle" else "lastfaelle").setExpanded(True)
    app.processEvents()
    sb = b.verticalScrollBar()
    check("Vorbereitung: der Baum rollt", sb.maximum() > 20, f"max {sb.maximum()}")
    sb.setValue(sb.maximum() // 2)
    app.processEvents()
    oben = b.itemAt(4, 4)
    ort = _kennung(oben)
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    app.processEvents()
    jetzt = b.itemAt(4, 4)
    check("Rollposition bleibt: derselbe Eintrag steht oben",
          jetzt is not None and _kennung(jetzt) == ort,
          f"{ort[-1]} -> {_kennung(jetzt)[-1] if jetzt is not None else None}")
    # darüber kommt eine Zeile dazu (ein neuer Lastfall): der Eintrag bleibt oben
    oben = b.itemAt(4, 4)
    while oben is not None and _element(oben)[0] != "kombination":
        sb.setValue(sb.value() + 1)
        oben = b.itemAt(4, 4)
        if sb.value() >= sb.maximum():
            break
    ort = _kennung(oben) if oben is not None else None
    m.add_load_case("Neu", "Q", activate=False)
    m.load_node(0, Fz=-1e3, case="Neu")
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    app.processEvents()
    jetzt = b.itemAt(4, 4)
    check("kommt oberhalb eine Zeile dazu, steht trotzdem derselbe Eintrag oben",
          ort is not None and jetzt is not None and _kennung(jetzt) == ort,
          f"{ort[-1] if ort else None} -> {_kennung(jetzt)[-1] if jetzt is not None else None}")


def test_gewaehlter_eintrag_bleibt():
    from PySide6 import QtCore
    m = _reiches_modell()
    b, app = _baum(260)
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    gemeldet = []
    b.angeklickt.connect(lambda a, n: gemeldet.append((a, n)))
    b.mehrfach.connect(lambda a, n: gemeldet.append((a, tuple(n))))   # nur dieser Baum, kein Fenster
    lf = next(iter(m.load_cases))
    for name in ("Einwirkungen", "Lastfälle"):
        _finden(b, name).setExpanded(True)
    ok = b.eintrag_waehlen("lastfall", lf)
    check("Vorbereitung: der Lastfall ist gewählt", ok and b.currentItem() is not None
          and _element(b.currentItem()) == ("lastfall", lf))
    vorher = _kennung(b.currentItem())
    gemeldet.clear()
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    app.processEvents()
    jetzt = b.currentItem()
    check("nach dem Neuaufbau ist derselbe Eintrag aktuell und gewählt",
          jetzt is not None and _kennung(jetzt) == vorher and jetzt.isSelected()
          and len(b.selectedItems()) == 1,
          str(_kennung(jetzt)[-1] if jetzt is not None else None))
    check("… ohne dass der Baum eine Auswahl meldet (sonst öffnete sich die Maske neu)",
          not gemeldet, str(gemeldet))
    check("… und die Aufklappung davor ist dieselbe (Lastfälle offen)",
          _finden(b, "Lastfälle").isExpanded())
    # mehrere Einträge
    namen = list(m.load_cases)[:3]
    b.clearSelection()
    for n in namen:
        _finden(b, n, "lastfall").setSelected(True)
    b.setCurrentItem(_finden(b, namen[0], "lastfall"), 0, QtCore.QItemSelectionModel.NoUpdate)
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    app.processEvents()
    gew = sorted(_element(i)[1] for i in b.selectedItems())
    check("mehrere gewählte Einträge bleiben gewählt", gew == sorted(namen), str(gew))
    # ein gelöschter Eintrag: keine Auswahl, kein Fehler
    b.clearSelection()
    b.eintrag_waehlen("lastfall", namen[-1])
    del m.load_cases[namen[-1]]
    for c in list(m.combinations):
        del m.combinations[c]
    try:
        b.fuellen(m, STELLUNGEN, ERGEBNISSE)
        ok = True
    except Exception as ex:               # noqa: BLE001
        ok = False
        print(ex)
    check("ein inzwischen gelöschter gewählter Eintrag stört den Neuaufbau nicht",
          ok and not [i for i in b.selectedItems() if _element(i)[1] == namen[-1]])


def test_kosten_haengen_nicht_an_der_listenlaenge():
    """Zeitkriterium am Drehlager: gemerkt wird über die Zweige, nicht über die
    Kinder. Gezählt werden die Zugriffe auf Einträge (Schleifen über 5000
    Knoten würden sich sofort zeigen)."""
    from PySide6 import QtWidgets
    from statik3d.model import Model
    m = Model()
    m.name = "Viele Knoten"
    m.nodes = np.random.rand(5000, 3)
    b, app = _baum(400)
    b.fuellen(m)
    _finden(b, "Knoten").setExpanded(True)
    app.processEvents()
    b.eintrag_waehlen("knoten", "4200")
    aufrufe = {"n": 0}
    orig = {}

    def zaehlend(name):
        f = getattr(QtWidgets.QTreeWidgetItem, name)
        orig[name] = f

        def g(self, *a, **k):
            aufrufe["n"] += 1
            return f(self, *a, **k)
        setattr(QtWidgets.QTreeWidgetItem, name, g)

    try:
        # Nicht ``data`` und die anderen virtuellen Methoden: Shiboken ruft die
        # Python-Fassung aus C++ wieder auf (Zugriffsverletzung). Die Schleife
        # über alle Kinder braucht ``child``, ``isExpanded`` und ``text``.
        for name in ("isExpanded", "child", "childCount", "text", "parent"):
            zaehlend(name)
        aufrufe["n"] = 0
        b.fuellen(m)
        n_gesamt = aufrufe["n"]
    finally:
        for name, f in orig.items():
            setattr(QtWidgets.QTreeWidgetItem, name, f)
    app.processEvents()
    check("Neuaufbau mit 5000 Knoten greift weniger als 1000-mal auf Einträge zu (keine Schleife über alle)",
          n_gesamt < 1000, f"{n_gesamt} Zugriffe")
    check("… und der gewählte Knoten K4200 ist danach wieder gewählt",
          b.currentItem() is not None and _element(b.currentItem()) == ("knoten", "4200"))
    # Strg+A in der Knotenliste: 300 gewählt - der Baum merkt dann nur den aktuellen
    from PySide6 import QtCore
    kn = _finden(b, "Knoten", "knoten")
    b.clearSelection()
    for i in range(300):
        kn.child(i).setSelected(True)
    b.setCurrentItem(kn.child(10), 0, QtCore.QItemSelectionModel.NoUpdate)
    b.fuellen(m)
    app.processEvents()
    check("300 gewählte Knoten: nach dem Neuaufbau nur der aktuelle (K10) gewählt, nicht 300 Sucherei",
          [_element(i) for i in b.selectedItems()] == [("knoten", "10")],
          str([_element(i) for i in b.selectedItems()][:3]))


# ---------------------------------------------------------------------------
# 4. Schriftregel
# ---------------------------------------------------------------------------
GRUPPEN = {"Eigenschaften", "Einwirkungen", "Lager", "Verbindungen", "Kontaktbedingungen",
           "Ergebnisse"}


def _zaehlzweige(baum):
    """Alle Zweige mit Zähler oder als Gruppe: bis Tiefe 2, ohne „+ …“ und Listeneinträge."""
    out = []
    for i in _alle(baum):
        tiefe = len(_kennung(i)) - 1
        if tiefe > 2 or i.text(0).startswith("+") or i.text(0).startswith("…"):
            continue
        art = _element(i)[0]
        if baum._ist_eintrag(i) and art not in ("ergebnisgruppe",):
            continue
        out.append(i)
    return out


def test_schriftregel():
    from statik3d.gui import design as dsg
    from statik3d.model import Model
    zweig_ohne_zaehler = {"Eigenschaften", "Einwirkungen"}
    for titel, m in (("Modell mit allem", _reiches_modell()), ("leeres Modell", Model())):
        b, app = _baum(900)
        b.fuellen(m, STELLUNGEN if titel != "leeres Modell" else [],
                  ERGEBNISSE if titel != "leeres Modell" else None)
        z = _zaehlzweige(b)
        fett_falsch, grau_falsch, normal_falsch = [], [], []
        for i in z:
            wurzel = i.parent() is None
            soll_fett = wurzel or i.text(0) in GRUPPEN
            if i.font(0).bold() != soll_fett:
                fett_falsch.append(f"{i.text(0)}:{'fett' if i.font(0).bold() else 'normal'}")
            zahl = i.text(1)
            if i.text(0) == "Ergebnisse" and not zahl:
                zahl = "0"                  # ohne Ergebnisse steht kein Zähler da
            if wurzel or i.text(0) in zweig_ohne_zaehler or not zahl.isdigit():
                continue
            farbe = _farbe(i)
            if int(zahl) == 0 and farbe != dsg.FARBEN["matt"]:
                grau_falsch.append(f"{i.text(0)}:{farbe}")
            if int(zahl) > 0 and farbe not in (None, dsg.FARBEN["warn"]):
                normal_falsch.append(f"{i.text(0)}:{farbe}")
        check(f"{titel}: fett nur für Gruppen (Wurzel, Eigenschaften, Einwirkungen, Lager, "
              "Verbindungen, Kontaktbedingungen, Ergebnisse)", not fett_falsch, ", ".join(fett_falsch[:8]))
        check(f"{titel}: Zähler 0 steht grau", not grau_falsch, ", ".join(grau_falsch[:8]))
        check(f"{titel}: gefüllte Zweige stehen in der Normalfarbe (nicht blau)", not normal_falsch,
              ", ".join(normal_falsch[:8]))
        b.close()


# ---------------------------------------------------------------------------
# 5. Volumen ohne Netz
# ---------------------------------------------------------------------------
def test_volumen_ohne_netz():
    from statik3d.gui import design as dsg
    from statik3d.model import Model, Volumenkoerper
    m = Model()
    m.name = "Volumen"
    flaechen = [f"F{j}" for j in range(6)]

    def koerper(name, **kw):
        m.koerper[name] = Volumenkoerper(name, flaechen=list(flaechen), material="S355", **kw)

    koerper("V1", elemente=[0, 1, 2])                                    # vernetzt
    koerper("V2", netzgrund="gescheitert", kommentar="ohne Netz: Hülle nicht geschlossen (9 Kanten offen)")
    koerper("V3", netzgrund="kein_volumen", kommentar="ohne Netz: kein Rauminhalt (alle Randknoten in einer Ebene)")
    koerper("V4")                                                        # nie versucht
    koerper("V5", netzgrund="abgebrochen", kommentar="ohne Netz: Vernetzen abgebrochen")
    koerper("V6", netzgrund="vernetzer_aus")
    b, app = _baum(500)
    b.fuellen(m)
    vol = _finden(b, "Volumen", "geokoerper")
    eintraege = {_element(vol.child(i))[1]: vol.child(i) for i in range(vol.childCount())
                 if b._ist_eintrag(vol.child(i))}
    check("alle sechs Körper stehen als Einträge unter „Volumen“", sorted(eintraege) == [f"V{i}" for i in range(1, 7)],
          str(sorted(eintraege)))
    if len(eintraege) != 6:
        return
    warn, matt = dsg.FARBEN["warn"], dsg.FARBEN["matt"]
    v1, v2, v3, v4, v5, v6 = (eintraege[f"V{i}"] for i in range(1, 7))
    check("mit Netz: Name ohne Zeichen, Normalfarbe", v1.text(0) == "V1" and _farbe(v1) is None,
          f"{v1.text(0)!r} {_farbe(v1)}")
    for it, grund in ((v2, "Hülle nicht geschlossen"), (v5, "abgebrochen"), (v6, "abgeschaltet")):
        check(f"{_element(it)[1]}: Vernetzung gescheitert → ⚠ vor dem Namen, Warnfarbe, Grund im Hinweis",
              it.text(0).startswith("⚠ ") and _farbe(it) == warn and grund in it.toolTip(0),
              f"{it.text(0)!r} {_farbe(it)} {it.toolTip(0)!r}")
    check("V3: Hilfskörper ohne Rauminhalt → grau, kein ⚠, der Hinweis sagt es",
          "⚠" not in v3.text(0) and _farbe(v3) == matt and "Hilfskörper" in v3.toolTip(0),
          f"{v3.text(0)!r} {_farbe(v3)} {v3.toolTip(0)!r}")
    check("V4: nie vernetzt ist der Normalfall → ○, Normalfarbe, kein ⚠",
          v4.text(0) == "V4 ○" and _farbe(v4) is None, f"{v4.text(0)!r} {_farbe(v4)}")
    check("der Zweig „Volumen“ trägt die Warnfarbe, solange ein Körper gescheitert ist",
          _farbe(vol) == warn, str(_farbe(vol)))
    # ohne Mangel: Zweig in Normalfarbe
    for k in ("V2", "V5", "V6"):
        del m.koerper[k]
    b.fuellen(m)
    vol = _finden(b, "Volumen", "geokoerper")
    check("ohne gescheiterten Körper steht der Zweig in der Normalfarbe", _farbe(vol) is None,
          str(_farbe(vol)))
    b.close()


# ---------------------------------------------------------------------------
# 5. Nachbesserung 02.10.2026 (Gegenpruefung): grau nur, wenn alles darunter leer ist
# ---------------------------------------------------------------------------
def _unterzweig_gefuellt(baum, i) -> bool:
    for k in range(i.childCount()):
        c = i.child(k)
        if c.text(0).startswith("+") or baum._ist_eintrag(c):
            continue
        if c.text(1).isdigit() and int(c.text(1)) > 0:
            return True
    return False


def test_grau_nur_wenn_der_zweig_leer_ist():
    """„Volumen 0“ über „Volumenelemente 960“ (Beispiel Quader, Platte, Block
    mit Reibung, Stauwand: Elemente ohne Körper) stand grau - grau heißt leer."""
    from statik3d.examples_lib import build_example
    from statik3d.gui import design as dsg
    b, app = _baum(900)
    gefunden = []
    for name in ("solid", "plate", "friction", "gate"):
        m = build_example(name)
        b.fuellen(m)
        app.processEvents()
        for i in _alle(b):
            if not i.childCount() or i.text(1) != "0" or b._ist_eintrag(i):
                continue
            gefuellt = _unterzweig_gefuellt(b, i)
            if gefuellt:
                gefunden.append(f"{name}: {i.text(0)}")
            ist_grau = _farbe(i) == dsg.FARBEN["matt"]
            check(f"{name}: „{i.text(0)} 0“ steht " + ("normal, ein Unterzweig hat Inhalt" if gefuellt
                                                       else "grau, alles darunter ist leer"),
                  ist_grau == (not gefuellt), f"Farbe {_farbe(i)}")
    check("Vorbereitung: es gab Zweige mit Zähler 0 über gefülltem Unterzweig",
          any("Volumen" in g for g in gefunden) and any("Flächen" in g for g in gefunden),
          str(gefunden))
    # ganz leer bleibt grau
    from statik3d.model import Model
    b.fuellen(Model())
    app.processEvents()
    vol = _finden(b, "Volumen", "geokoerper")
    check("ohne Körper und ohne Volumenelemente steht „Volumen“ grau", _farbe(vol) == dsg.FARBEN["matt"],
          str(_farbe(vol)))
    b.close()


# ---------------------------------------------------------------------------
# 6. Auswahl nach dem Löschen nummerierter Einträge
# ---------------------------------------------------------------------------
def test_auswahl_nach_loeschen_nummerierter_eintraege():
    """Knoten, Lager, Stabelemente … tragen ihre laufende Nummer als Schlüssel;
    nach dem Löschen rücken die Nummern auf. Die Auswahl darf dann nicht still
    auf das nachgerückte Objekt fallen (ein zweites Entf löschte die falschen)."""
    from PySide6 import QtCore
    m = _reiches_modell()
    b, app = _baum(500)
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    for name in ("Lager", "Knotenlager"):
        _finden(b, name).setExpanded(True)
    kl = _finden(b, "Knotenlager")
    n0 = len(m.supports)
    check("Vorbereitung: mindestens sechs Knotenlager", n0 >= 6, str(n0))
    b.clearSelection()
    for k in range(kl.childCount()):
        if _element(kl.child(k))[1] in ("1", "2", "3"):          # „Lager 2 bis 4“
            kl.child(k).setSelected(True)
    b.setCurrentItem(kl.child(2), 0, QtCore.QItemSelectionModel.NoUpdate)
    check("Vorbereitung: drei Lager gewählt", len(b.selectedItems()) == 3, str(len(b.selectedItems())))
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    check("unverändert neu aufgebaut: dieselben drei Lager bleiben gewählt",
          sorted(_element(i)[1] for i in b.selectedItems()) == ["1", "2", "3"])
    del m.supports[1:4]                                      # gelöscht, die Nummern rücken auf
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    app.processEvents()
    gew = [_element(i) for i in b.selectedItems()]
    cur = b.currentItem()
    check("Lager 2 bis 4 gelöscht: nichts Nachgerücktes ist gewählt", not gew, str(gew))
    check("… und der aktuelle Eintrag ist kein nachgerücktes Lager",
          cur is None or _element(cur)[0] != "lager_einzeln", str(_element(cur) if cur is not None else None))
    # Knoten in einer gedeckelten Liste: die Zahl der Zeilen bleibt gleich, die Zahl der Knoten nicht
    from statik3d.gui import design as dsg
    from statik3d.model import Model
    m2 = Model()
    m2.name = "Gross"
    m2.nodes = np.random.rand(dsg.BAUM_MAX + 300, 3)
    b.fuellen(m2)
    _finden(b, "Knoten", "knoten").setExpanded(True)
    b.eintrag_waehlen("knoten", "5")
    m2.nodes = np.delete(m2.nodes, 1, axis=0)
    b.fuellen(m2)
    check("Knoten gelöscht (Liste auf 20 000 Zeilen gedeckelt): K5 wird nicht still neu gewählt",
          not b.selectedItems(), str([_element(i) for i in b.selectedItems()]))
    # nicht nummerierte Arten behalten ihre Auswahl auch nach dem Löschen eines anderen
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    namen = list(m.load_cases)
    for name in ("Einwirkungen", "Lastfälle"):
        _finden(b, name).setExpanded(True)
    b.eintrag_waehlen("lastfall", namen[0])
    del m.load_cases[namen[-1]]
    b.fuellen(m, STELLUNGEN, ERGEBNISSE)
    check("ein Lastfall (Schlüssel = Name) bleibt gewählt, wenn ein anderer gelöscht wird",
          [_element(i) for i in b.selectedItems()] == [("lastfall", namen[0])],
          str([_element(i) for i in b.selectedItems()]))
    b.close()


# ---------------------------------------------------------------------------
# 7. Das Hauptfenster
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


VORGABE_NAMEN = ["Stäbe", "Lager", "Knotenlager", "Einwirkungen", "Lastfälle", "Kombinationen",
                 "Eigenschaften", "Querschnitte", "Stellungen", "Gelenke", "Subsysteme"]


def _zustand_setzen(w, app):
    """Ein Zustand wie bei der Arbeit: viele Zweige offen, der Baum gerollt,
    ein Lastfall gewählt. Gibt (offene Pfade, oberster Eintrag, Auswahl) zurück."""
    b = w.baum
    for name in VORGABE_NAMEN:
        i = _finden(b, name)
        if i is not None:
            i.setExpanded(True)
    app.processEvents()
    lf = next(iter(w.model.load_cases))
    b.eintrag_waehlen("lastfall", lf)
    app.processEvents()
    sb = b.verticalScrollBar()
    sb.setValue(sb.maximum() // 2)
    app.processEvents()
    oben = b.itemAt(4, 4)
    return _zweige(b), (_kennung(oben) if oben is not None else None), lf


def test_fenster_refresh_all_haelt_den_zustand():
    w, app = _fenster()
    w.load_example("hall")
    app.processEvents()
    b = w.baum
    vorher, oben, lf = _zustand_setzen(w, app)
    check("Vorbereitung: der Baum rollt und viele Zweige sind offen",
          b.verticalScrollBar().maximum() > 10 and sum(vorher.values()) >= 10,
          f"max {b.verticalScrollBar().maximum()}, offen {sum(vorher.values())}")
    gemeldet = []

    def melden(a, n):
        gemeldet.append((a, n))

    b.angeklickt.connect(melden)
    w.refresh_all()
    app.processEvents()
    b.angeklickt.disconnect(melden)
    nachher = _zweige(b)
    falsch = sorted({k[-1][1] for k in vorher if nachher.get(k) != vorher[k]})
    check("refresh_all: alle aufgeklappten Zweige bleiben aufgeklappt", not falsch, ", ".join(falsch[:8]))
    jetzt = b.itemAt(4, 4)
    check("refresh_all: die Rollposition bleibt (derselbe Eintrag steht oben)",
          oben is not None and jetzt is not None and _kennung(jetzt) == oben,
          f"{oben[-1] if oben else None} -> {_kennung(jetzt)[-1] if jetzt is not None else None}")
    cur = b.currentItem()
    check("refresh_all: der gewählte Lastfall bleibt gewählt",
          cur is not None and _element(cur) == ("lastfall", lf) and cur.isSelected(),
          str(_element(cur) if cur is not None else None))
    check("refresh_all: ohne dass der Baum erneut eine Auswahl meldet", not gemeldet, str(gemeldet))


def test_fenster_uebernehmen_und_rueckgaengig():
    w, app = _fenster()
    w.load_example("hall")
    app.processEvents()
    b = w.baum
    vorher, oben, lf = _zustand_setzen(w, app)
    w._objektmaske("lastfall", lf)
    app.processEvents()
    mk = w.maskenrand.maske
    ok = mk is not None
    if ok:
        mk.setzen("beschreibung", "geändert in der Maske")
        mk.anwenden()
        app.processEvents()
    nachher = _zweige(b)
    falsch = sorted({k[-1][1] for k in vorher if nachher.get(k) != vorher[k]})
    check("„Übernehmen“ einer Maske: Aufklappzustand bleibt", ok and not falsch,
          ", ".join(falsch[:8]) if ok else "keine Maske")
    check("… die Beschreibung steht im Modell (die Maske hat wirklich übernommen)",
          w.model.load_cases[lf].description == "geändert in der Maske",
          w.model.load_cases[lf].description)
    # Rückgängig ersetzt das ganze Modell durch eine Kopie. Der Zustand wird
    # neu gesetzt: am Stand vor 8a war er nach dem „Übernehmen“ schon weg und
    # der Vergleich damit wertlos.
    vorher, oben, lf = _zustand_setzen(w, app)
    check("Rückgängig, Vorbereitung: viele Zweige offen", sum(vorher.values()) >= 10,
          f"offen {sum(vorher.values())}")
    w.merken("Test")
    w.model.add_load_case("Extra", "Q", activate=False)
    w.refresh_all()
    app.processEvents()
    w.undo()
    app.processEvents()
    nachher = _zweige(b)
    falsch = sorted({k[-1][1] for k in vorher if nachher.get(k) != vorher[k]})
    check("Rückgängig: Aufklappzustand bleibt", not falsch and "Extra" not in w.model.load_cases,
          ", ".join(falsch[:8]))
    jetzt = b.itemAt(4, 4)
    check("Rückgängig: derselbe Eintrag steht oben (die Rolle bleibt)",
          jetzt is not None and _kennung(jetzt) == oben,
          f"{oben[-1] if oben else None} -> {_kennung(jetzt)[-1] if jetzt is not None else None}")
    check("Rückgängig: die Auswahl des Baums ist verworfen (die Ansicht leert ihre auch)",
          not b.selectedItems() and b.currentItem() is None and len(w.selection) == 0,
          str([_element(i) for i in b.selectedItems()]))
    # Wiederholen ebenso
    vorher, oben, lf = _zustand_setzen(w, app)
    check("Wiederholen, Vorbereitung: ein Lastfall ist gewählt", len(b.selectedItems()) == 1)
    w.redo()
    app.processEvents()
    nachher = _zweige(b)
    falsch = sorted({k[-1][1] for k in vorher if nachher.get(k) != vorher[k]})
    check("Wiederholen: Aufklappzustand bleibt, die Auswahl ist verworfen",
          not falsch and not b.selectedItems(), ", ".join(falsch[:8]))


def _grundzustand(w):
    b = w.baum
    offen = sorted(i.text(0) for i in _alle(b) if i.childCount() and i.isExpanded())
    wurzel = b.topLevelItem(0).text(0)
    return offen, sorted([wurzel, "Lager", "Stellungen"])


def test_fenster_neues_modell_erbt_nichts():
    w, app = _fenster()
    b = w.baum
    wege = []

    def neu():
        w.new_model()

    def beispiel():
        w.load_example("frame")

    def oeffnen():
        p = os.path.join(tempfile.mkdtemp(prefix="statik3d_baum_"), "modell.json")
        w.model.save(p)
        w.modell_laden(p, fragen=False)

    for titel, weg in (("Neu", neu), ("Beispiel laden", beispiel), ("Öffnen", oeffnen)):
        w.load_example("hall")
        app.processEvents()
        vorher, oben, lf = _zustand_setzen(w, app)
        sb = b.verticalScrollBar()
        check(f"{titel}: Vorbereitung (Zustand gesetzt, Baum gerollt)",
              sb.value() > 0 and b.currentItem() is not None, f"Rolle {sb.value()}")
        weg()
        app.processEvents()
        offen, erwartet = _grundzustand(w)
        # Zweige, die es im neuen Modell nicht gibt, fehlen in der Liste von selbst
        erwartet = [e for e in erwartet if e in [i.text(0) for i in _alle(b)]]
        check(f"{titel}: Grundzustand (Wurzel, Lager, Stellungen offen, alles andere zu)",
              offen == erwartet, f"offen {offen}")
        check(f"{titel}: nichts gewählt, Rolle ganz oben",
              not b.selectedItems() and b.verticalScrollBar().value() == 0,
              f"gewählt {len(b.selectedItems())}, Rolle {b.verticalScrollBar().value()}")


def test_fenster_web_ersetzt_das_modell():
    """Die Web-Befehle (Neu, Beispiel, Modell ersetzen, Import) tauschen das
    Modell des Fensters über State.bound aus; ``_web_poll`` ruft nur
    refresh_all. Ohne Server nachgestellt: ein Stellvertreter für den Stand
    und ein neues Modellobjekt."""
    from types import SimpleNamespace
    from statik3d.examples_lib import build_example
    w, app = _fenster()
    b = w.baum
    w.load_example("hall")
    app.processEvents()
    vorher, oben, lf = _zustand_setzen(w, app)
    w.web_state = SimpleNamespace(version=1)
    w.web_version = 0
    try:
        w.model.meta["Bemerkung"] = "im Browser geändert"   # dasselbe Modell, nur geändert
        w._web_poll()
        app.processEvents()
        nachher = _zweige(b)
        falsch = sorted({k[-1][1] for k in vorher if nachher.get(k) != vorher[k]})
        check("Web: dasselbe Modell geändert → Aufklappzustand und Auswahl bleiben",
              not falsch and b.currentItem() is not None, ", ".join(falsch[:8]))
        w.model = build_example("frame")              # wie replace_model / Beispiel / Neu im Browser
        w.web_state.version = 2
        w._web_poll()
        app.processEvents()
        offen, erwartet = _grundzustand(w)
        erwartet = [e for e in erwartet if e in [i.text(0) for i in _alle(b)]]
        check("Web: anderes Modell → Grundzustand, nichts gewählt, Rolle oben",
              offen == erwartet and not b.selectedItems() and b.verticalScrollBar().value() == 0,
              f"offen {offen}, gewählt {len(b.selectedItems())}")
    finally:
        w.web_state = None


def main():
    tests = [test_jeder_zweig_behaelt_seinen_zustand, test_drei_doppelte_namen,
             test_gleicher_text_an_zwei_stellen, test_wurzel_traegt_den_modellnamen_nicht_als_schluessel,
             test_pfade_sind_eindeutig, test_grundzustand_im_baum, test_rollposition_folgt_dem_eintrag,
             test_gewaehlter_eintrag_bleibt, test_kosten_haengen_nicht_an_der_listenlaenge,
             test_schriftregel, test_volumen_ohne_netz, test_grau_nur_wenn_der_zweig_leer_ist,
             test_auswahl_nach_loeschen_nummerierter_eintraege,
             test_fenster_refresh_all_haelt_den_zustand, test_fenster_uebernehmen_und_rueckgaengig,
             test_fenster_neues_modell_erbt_nichts,
             test_fenster_web_ersetzt_das_modell]
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
    sys.exit(0 if ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
