"""
Der Befehl „Stab“ im Sinn von RFEM (Plan-Teilpaket C14, 03.10.2026).

Antwort 2 des Anwenders vom 24.09.2026 (PLAN-OBERFLAECHE-2026-09-24.md,
Abschnitt 7a): „Der Befehl „Stab“ legt einen Stab mit Nachweis an, die
FE-Stabelemente stehen unter „FE-Netz“.“ Baum und Register hat Teilpaket 8c
umgestellt. Der Befehl legte bis zum 03.10.2026 weiter nur ein einzelnes
Stabelement an, das dann unter FE-Netz → Stabelemente stand und keinen
Nachweis bekam.

Geprüft wird am echten Hauptfenster (offscreen):

* Struktur → Stab, Start → Stab, die Taste S in der Ansicht, die Befehlssuche
  und am Zweig „Stäbe“ der Rechtsklick „Neu: Stab“ sowie der Doppelklick öffnen
  dieselbe Maske „Stab“. Zwei angeklickte Knoten legen einen Stab mit Nachweis
  (S…) samt seinem Stabelement (E…) an, mit Querschnitt und Werkstoff aus der
  Maske;
* der Stab steht unter Geometrie → Stäbe, sein Element unter FE-Netz →
  Stabelemente; ein Rahmen aus drei solchen Stäben rechnet genau wie derselbe
  Rahmen aus drei einzelnen Stabelementen (Verschiebungen, Auflagerkräfte,
  Stabendkräfte), und der Nachweis nach EC3 kennt die Stäbe;
* Netz → Stabelement und Rechtsklick „Neu: Stabelement“ legen ein einzelnes
  Element an, keinen Stab. Einen Stab aus vorhandenen Stabelementen bildet
  Struktur → Nachweisstäbe ▾ → „Stab aus Stabelementen…“ (bis zum 03.10.2026
  der Rechtsklick „Neu: Stab“);
* Maskentitel, Löschfragen, Statuszeile, Protokoll, Rückgängig und die Angaben
  zum Modell unterscheiden „Stab S…“ und „Stabelement E…“;
* kein Tastenkürzel ist doppelt, die Taste S gehört dem Stab, das Stabelement
  hat keine Taste;
* das Handbuch beschreibt beides, mit dem Stand vorher.

Aufruf:  python -m tests.test_befehl_stab
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_befehlstab_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}

MAT, SEC = "S355", "HEB 300"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _fenster():
    if "w" in _FENSTER:
        # Tastendruecke wirken nur im aktiven Fenster
        _FENSTER["w"].activateWindow()
        _FENSTER["app"].processEvents()
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w.activateWindow()
    app.processEvents()
    # Rueckfragen und Meldungen nie auf dem Bildschirm stehen lassen
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    w.error = lambda msg, *a, **k: w.fehler_liste.append(str(msg))
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    _FENSTER.update(w=w, app=app)
    return w, app


def _modell(w, app):
    """Ein leeres Modell mit S355, HEB 300 und vier Knoten eines Rahmens:
    K0 (0, 0, 0), K1 (0, 0, 4), K2 (6, 0, 4), K3 (6, 0, 0)."""
    import numpy as np
    from statik3d.model import Material, Section
    w.new_model()
    m = w.model
    m.add_material(Material.steel(MAT))
    m.add_section(Section.from_profile(SEC))
    for p in ((0, 0, 0), (0, 0, 4), (6, 0, 4), (6, 0, 0)):
        m.add_node(*p)
    w.refresh_all()
    app.processEvents()
    w.maskenrand.schliessen()
    w._auswahl_leeren()
    w.selection = np.array([], dtype=int)
    w.fehler_liste.clear()
    app.processEvents()
    return m


def _maske(w):
    return w.maskenrand.maske if w.maskenrand.offen() else None


def _titel(w) -> str:
    mk = _maske(w)
    return mk.titel if mk is not None else ""


def _statuszeile(w) -> str:
    return w.statusBar().currentMessage()


# ---------------------------------------------------------------------------
# 1. Fuenf Wege zum Befehl „Stab“
# ---------------------------------------------------------------------------
def _start_knopf(w, aktion):
    from PySide6 import QtWidgets
    reg = w.ribbon._register["Start"]
    return [b for b in reg.findChildren(QtWidgets.QToolButton) if b.defaultAction() is aktion]


def _zweig(w, gruppe, text):
    g = w.baum.gruppe(gruppe)
    if g is None:
        return None
    return next((g.child(i) for i in range(g.childCount()) if g.child(i).text(0) == text), None)


def _wege(w, app):
    """Die Wege zum Befehl „Stab“: (Name, Ausloeser)."""
    from PySide6 import QtCore, QtTest

    def ribbon():
        w.ribbon.aktion("Struktur", "Stab").trigger()

    def start():
        knoepfe = _start_knopf(w, w.ribbon.aktion("Struktur", "Stab"))
        w.ribbon.zeigen("Start")
        app.processEvents()
        knoepfe[0].click()

    def taste():
        ia = w.plotter.interactor
        ia.setFocus()
        app.processEvents()
        QtTest.QTest.keyClick(ia, QtCore.Qt.Key_S)

    def suche():
        r = w.ribbon
        r.suche.setText("Stab")
        r._liste_nachziehen("Stab")
        b = next(b for b in r.finden("Stab") if b.register == "Struktur" and b.text == "Stab")
        r._treffer_gewaehlt(r.anzeige(b))
        r._vervollstaendigung.popup().hide()

    def baum_neu():
        w.baum.neu.emit("staebe")             # Rechtsklick „Neu: Stab …“

    def baum_doppelklick():
        it = _zweig(w, "geometrie", "Stäbe")
        w.baum.setCurrentItem(it)
        w.baum.itemDoubleClicked.emit(it, 0)

    return (("Ribbon Struktur → Stab", ribbon), ("Register Start → Stab", start),
            ("Taste S in der Ansicht", taste), ("Befehlssuche „Stab“", suche),
            ("Rechtsklick „Neu: Stab“ am Zweig Stäbe", baum_neu),
            ("Doppelklick auf den Zweig Stäbe", baum_doppelklick))


def test_wege_zum_stab():
    w, app = _fenster()
    for name, ausloesen in _wege(w, app):
        m = _modell(w, app)
        ne0, nm0 = len(m.elements), len(m.members)
        ausloesen()
        app.processEvents()
        mk = _maske(w)
        if not check(f"{name}: öffnet die Maske „Stab“ mit zwei Knoten zum Anklicken",
                     mk is not None and mk.titel == "Stab" and mk.n_knoten == 2, repr(_titel(w))):
            continue
        mk.setzen("mat", MAT)
        mk.setzen("sec", SEC)
        mk.knoten_angeklickt(1)
        mk.knoten_angeklickt(2)
        app.processEvents()
        mem = m.members.get("S1")
        e = m.elements[ne0] if len(m.elements) > ne0 else None
        check(f"{name}: zwei Klicks legen den Stab S1 mit Nachweis samt Stabelement E{ne0} an",
              len(m.members) == nm0 + 1 and len(m.elements) == ne0 + 1 and mem is not None
              and list(mem.elements) == [ne0] and mem.design and e is not None
              and list(e.nodes) == [1, 2] and e.typ == "beam",
              f"Stäbe {nm0} -> {len(m.members)} {sorted(m.members)}, Elemente {ne0} -> {len(m.elements)}")
        check(f"{name}: … mit Querschnitt und Werkstoff aus der Maske, ohne Fehler",
              e is not None and e.sec == SEC and e.mat == MAT and not w.fehler_liste,
              f"{getattr(e, 'sec', None)} / {getattr(e, 'mat', None)} {w.fehler_liste[:1]}")
        check(f"{name}: die Maske bleibt für den nächsten Stab offen", _maske(w) is mk and mk.gewaehlt == [])
        w.maskenrand.schliessen()
        app.processEvents()


def test_fachwerkstab_und_zweiter_stab():
    w, app = _fenster()
    m = _modell(w, app)
    w.ribbon.aktion("Struktur", "Stab").trigger()
    app.processEvents()
    mk = _maske(w)
    mk.setzen("mat", MAT)
    mk.setzen("sec", SEC)
    mk.knoten_angeklickt(0)
    mk.knoten_angeklickt(1)
    mk.setzen("fachwerk", True)
    mk.knoten_angeklickt(1)
    mk.knoten_angeklickt(2)
    app.processEvents()
    check("Zweiter Stab in derselben Maske: S2 mit eigenem Stabelement E1",
          sorted(m.members) == ["S1", "S2"] and list(m.members["S2"].elements) == [1]
          and len(m.elements) == 2, str({k: v.elements for k, v in m.members.items()}))
    check("„Fachwerkstab (nur N)“: das Stabelement des Stabs ist ein Fachwerkstab",
          m.elements[1].typ == "truss" and m.elements[0].typ == "beam",
          str([e.typ for e in m.elements]))
    # ohne Werkstoff kein Stab, der beim Rechnen erst scheitert
    mk.setzen("fachwerk", False)
    w.fehler_liste.clear()
    w._maske_stab_anlegen({"knoten": [2, 3], "mat": "", "sec": SEC, "fachwerk": False})
    check("Ohne Werkstoff: kein Stab und kein Element, eine Meldung sagt es",
          len(m.members) == 2 and len(m.elements) == 2 and any("Werkstoff" in f for f in w.fehler_liste),
          str(w.fehler_liste))
    w.maskenrand.schliessen()


# ---------------------------------------------------------------------------
# 2. Baum: Geometrie → Stäbe, FE-Netz → Stabelemente
# ---------------------------------------------------------------------------
def test_stab_im_baum():
    w, app = _fenster()
    m = _modell(w, app)
    w._maske_stab_anlegen({"knoten": [1, 2], "mat": MAT, "sec": SEC})
    app.processEvents()
    st = _zweig(w, "geometrie", "Stäbe")
    se = _zweig(w, "fe_netz", "Stabelemente")
    staebe = [w.baum._schluessel(st.child(i)) for i in range(st.childCount())] if st is not None else []
    elemente = [w.baum._schluessel(se.child(i)) for i in range(se.childCount())] if se is not None else []
    check("Der neue Stab steht unter Geometrie → Stäbe (S1)", staebe == [("stab", "S1")], str(staebe))
    check("… sein Element unter FE-Netz → Stabelemente (E0)", elemente == [("stabelement", "0")]
          and se.child(0).text(0) == "E0", str(elemente))
    check("… und das Element gehört zum Stab", list(m.members["S1"].elements) == [0])


# ---------------------------------------------------------------------------
# 3. Rechnung: ein Stab rechnet wie dasselbe Element
# ---------------------------------------------------------------------------
def _rahmen(w, app, anlegen):
    """Zweigelenkrahmen 6 m x 4 m: Fuesse eingespannt, H = 10 kN am linken
    Eckknoten, V = 40 kN am rechten; drei Stuecke ueber ``anlegen``."""
    m = _modell(w, app)
    m.support(0, "all")
    m.support(3, "all")
    g = next(iter(m.load_cases))
    m.load_node(1, Fx=10e3, case=g)
    m.load_node(2, Fz=-40e3, case=g)
    for a, b in ((0, 1), (1, 2), (2, 3)):
        anlegen({"knoten": [a, b], "mat": MAT, "sec": SEC, "fachwerk": False})
    app.processEvents()
    return m, g


def test_rechnet_wie_das_element():
    import numpy as np
    from statik3d import solver
    w, app = _fenster()
    m_el, g = _rahmen(w, app, w._maske_stabelement_anlegen)
    an_el = solver.solve_all(m_el, design=False)
    m_st, _g = _rahmen(w, app, w._maske_stab_anlegen)
    check("Vorbereitung: drei Stabelemente ohne Stab, drei Stäbe mit je einem Stabelement",
          len(m_el.elements) == 3 and not m_el.members and len(m_st.elements) == 3
          and sorted(m_st.members) == ["S1", "S2", "S3"]
          and all(len(s.elements) == 1 for s in m_st.members.values()),
          f"{len(m_el.members)} / {sorted(m_st.members)}")
    an_st = solver.solve_all(m_st, design=True)
    r_el, r_st = an_el.cases[g], an_st.cases[g]
    du = float(np.max(np.abs(r_el.u - r_st.u)))
    dr = float(np.max(np.abs(r_el.reactions - r_st.reactions)))
    de = max(float(np.max(np.abs(np.asarray(r_el.beam_end[i]) - np.asarray(r_st.beam_end[i]))))
             for i in range(3))
    umax = float(np.max(np.abs(r_el.u)))
    check("Gleiche Verschiebungen (Unterschied 0, |u|max > 0)", du == 0.0 and umax > 0,
          f"max |Δu| = {du:.3e}, |u|max = {umax:.3e}")
    check("Gleiche Auflagerkräfte und Stabendkräfte (Unterschied 0)", dr == 0.0 and de == 0.0,
          f"ΔR {dr:.3e} N, ΔF {de:.3e}")
    namen = sorted(getattr(an_st.design, "members", {}) or {}) if an_st.design is not None else []
    check("Der Nachweis nach EC3 kennt die drei Stäbe", namen == ["S1", "S2", "S3"], str(namen))


# ---------------------------------------------------------------------------
# 4. Das einzelne Stabelement bleibt erreichbar; Stab aus Stabelementen
# ---------------------------------------------------------------------------
def test_stabelement():
    w, app = _fenster()
    m = _modell(w, app)
    befehle = [b for b in w.ribbon.befehle if b.text == "Stabelement"]
    check("Netz → Stabelement: ein Befehl in der Gruppe „Elemente“ des Registers Netz",
          [(b.register, b.gruppe) for b in befehle] == [("Netz", "Elemente")],
          str([(b.register, b.gruppe) for b in befehle]))
    if not befehle:
        return
    befehle[0].aktion.trigger()
    app.processEvents()
    mk = _maske(w)
    if not check("… öffnet die Maske „Stabelement“ mit zwei Knoten zum Anklicken",
                 mk is not None and mk.titel == "Stabelement" and mk.n_knoten == 2, repr(_titel(w))):
        return
    mk.setzen("mat", MAT)
    mk.setzen("sec", SEC)
    mk.knoten_angeklickt(0)
    mk.knoten_angeklickt(1)
    app.processEvents()
    check("… zwei Klicks legen ein Stabelement an und keinen Stab",
          len(m.elements) == 1 and not m.members and list(m.elements[0].nodes) == [0, 1]
          and m.elements[0].sec == SEC, f"{len(m.elements)} Elemente, Stäbe {sorted(m.members)}")
    w.maskenrand.schliessen()
    # Rechtsklick „Neu: Stabelement …“ am Zweig Stabelemente
    w.baum.neu.emit("stabelemente")
    app.processEvents()
    check("Rechtsklick „Neu: Stabelement“: Maske „Neu: Stabelement E1“",
          _titel(w) == "Neu: Stabelement E1", repr(_titel(w)))
    mk = _maske(w)
    if mk is not None:
        mk.setzen("kn", "1, 2")
        mk.setzen("mat", MAT)
        mk.setzen("sec", SEC)
        mk.anwenden()
        app.processEvents()
    check("… OK legt das Stabelement E1 an, keinen Stab",
          len(m.elements) == 2 and list(m.elements[1].nodes) == [1, 2] and not m.members,
          f"{len(m.elements)} Elemente, Stäbe {sorted(m.members)}, {w.fehler_liste[:1]}")
    w.maskenrand.schliessen()


def test_stab_aus_stabelementen():
    w, app = _fenster()
    m = _modell(w, app)
    for a, b in ((0, 1), (1, 2)):
        w._maske_stabelement_anlegen({"knoten": [a, b], "mat": MAT, "sec": SEC})
    befehle = [b for b in w.ribbon.befehle if b.text == "Stab aus Stabelementen…"]
    check("Struktur → Nachweisstäbe ▾ → „Stab aus Stabelementen…“ gibt es",
          [(b.register, b.gruppe) for b in befehle] == [("Struktur", "Stäbe")],
          str([(b.register, b.gruppe) for b in befehle]))
    if not befehle:
        return
    befehle[0].aktion.trigger()
    app.processEvents()
    mk = _maske(w)
    check("… öffnet die Maske „Neu: Stab S1“ mit den Elementnummern",
          mk is not None and mk.titel == "Neu: Stab S1" and "elemente" in mk.werte(), repr(_titel(w)))
    if mk is None:
        return
    mk.setzen("elemente", "0, 1")
    mk.anwenden()
    app.processEvents()
    check("… OK bildet den Stab S1 aus E0 und E1, ohne neues Element",
          list(m.members.get("S1").elements if "S1" in m.members else []) == [0, 1] and len(m.elements) == 2,
          f"{ {k: v.elements for k, v in m.members.items()} }, {len(m.elements)} Elemente")
    w.maskenrand.schliessen()


# ---------------------------------------------------------------------------
# 5. Begriffe: Titel, Loeschfragen, Statuszeile, Protokoll, Angaben
# ---------------------------------------------------------------------------
def test_begriffe():
    w, app = _fenster()
    m = _modell(w, app)
    n_log = len(w.log.toPlainText().splitlines())
    w._maske_stab_anlegen({"knoten": [1, 2], "mat": MAT, "sec": SEC})
    app.processEvents()
    zeile = w.log.toPlainText().splitlines()[n_log:]
    check("Statuszeile nach „Stab“: Stab S1 mit Stabelement E0",
          "Stab S1" in _statuszeile(w) and "Stabelement E0" in _statuszeile(w), repr(_statuszeile(w)))
    check("… dieselbe Zeile im Protokoll", zeile == [_statuszeile(w)], str(zeile))
    check("… Rückgängig heißt „Stab S1 angelegt“", w._undo[-1][0] == "Stab S1 angelegt", repr(w._undo[-1][0]))
    w._maske_stabelement_anlegen({"knoten": [2, 3], "mat": MAT, "sec": SEC})
    app.processEvents()
    check("Statuszeile nach „Stabelement“: Stabelement E1, kein Stab",
          _statuszeile(w).startswith("Stabelement E1") and "S2" not in _statuszeile(w) and len(m.members) == 1,
          repr(_statuszeile(w)))
    check("… Rückgängig heißt „Stabelement angelegt“", w._undo[-1][0] == "Stabelement angelegt",
          repr(w._undo[-1][0]))
    # Maskentitel
    w._objektmaske("stabelement", "0")
    app.processEvents()
    check("Maske eines Stabelements: „Stabelement E0“", _titel(w) == "Stabelement E0", repr(_titel(w)))
    w._objektmaske("stab", "S1")
    app.processEvents()
    check("Maske eines Stabs: „Stab S1“", _titel(w) == "Stab S1", repr(_titel(w)))
    w.maskenrand.schliessen()
    # Loeschfragen (Nein: nichts geloescht)
    fragen = []
    w._bestaetigen = lambda text: (fragen.append(text), False)[1]
    try:
        w._baum_loeschen("stabelement", "0")
        w._baum_loeschen("stab", "S1")
    finally:
        del w._bestaetigen
    check("Löschfrage am Stabelement: „Stabelement E0 wirklich löschen?“",
          fragen[:1] == ["Stabelement E0 wirklich löschen?"], str(fragen[:1]))
    check("Löschfrage am Stab: „Stab S1 (seine Stabelemente bleiben) wirklich löschen?“",
          fragen[1:2] == ["Stab S1 (seine Stabelemente bleiben) wirklich löschen?"], str(fragen[1:2]))
    check("… mit Nein bleibt beides", "S1" in m.members and len(m.elements) == 2)
    folgen = w._loesch_folgen([("stab", ["S1"])])
    check("Entf in der Ansicht mit gewähltem Stab: „Stäbe: ihre Stabelemente bleiben stehen …“",
          "Stäbe: ihre Stabelemente bleiben stehen" in folgen, repr(folgen))
    # Angaben zum Modell
    angaben = w.modellangaben()
    namen = [k for k, _v in angaben]
    werte = dict(angaben)
    check("Angaben zum Modell: „Stäbe“ (1) und gleich danach „Stabelemente“ (2)",
          "Stäbe" in namen and namen.index("Stabelemente") == namen.index("Stäbe") + 1
          and werte["Stäbe"] == "1" and werte["Stabelemente"] == "2", str(namen[:6]))
    text = w._leeren_text(m, False)
    check("Rückfrage „Modell leeren“ nennt „Stäbe (1)“", "Stäbe (1)" in text, text[:160])
    # Fehlermeldung der Maske „Neu: Stabelement“
    w.fehler_liste.clear()
    w._objekt_uebernehmen("stabelement", str(len(m.elements)),
                          {"kn": "1, 1", "typ": "Balken", "mat": MAT, "sec": SEC}, True)
    check("Neu: Stabelement mit zweimal demselben Knoten: „Ein Stabelement braucht …“",
          any(f.startswith("Ein Stabelement braucht") for f in w.fehler_liste), str(w.fehler_liste))
    # Linie mit Stabelementen
    w.maske_linie()
    app.processEvents()
    mk = _maske(w)
    haken = mk._felder.get("staebe") if mk is not None else None
    check("Maske „Linie“: der Haken heißt „Stabelemente daraus erzeugen“",
          haken is not None and haken.text() == "Stabelemente daraus erzeugen",
          repr(haken.text() if haken is not None else None))
    if mk is not None:
        mk.setzen("teilung", 2)
        mk.knoten_angeklickt(0)
        mk.knoten_angeklickt(3)
        mk.anwenden()                       # die Polylinie braucht zwei, die Maske nimmt drei
        app.processEvents()
    check("… die Statuszeile sagt „2 Stabelemente erzeugt“", "2 Stabelemente erzeugt" in _statuszeile(w),
          repr(_statuszeile(w)))
    w.maskenrand.schliessen()


# ---------------------------------------------------------------------------
# 6. Tastenkuerzel
# ---------------------------------------------------------------------------
def test_kuerzel():
    from PySide6 import QtCore, QtGui
    from statik3d.gui import kuerzelliste as kl
    w, app = _fenster()
    folgen = {}
    for b in w.ribbon.befehle:
        if not b.aktion.shortcut().isEmpty():
            folgen.setdefault(b.aktion.shortcut().toString(), []).append(b.text)
    for a in w.actions():
        if not a.shortcut().isEmpty() and not any(b.aktion is a for b in w.ribbon.befehle):
            folgen.setdefault(a.shortcut().toString(), []).append(a.text())
    doppelt = {k: v for k, v in folgen.items() if len(v) > 1}
    check("Kein Tastenkürzel doppelt (Ribbon und Fenster)", not doppelt and len(folgen) > 20, str(doppelt))
    strg_umschalt = sorted(k for k in folgen if k.startswith("Ctrl+Shift+"))
    check("Strg+Umschalt: kein Kürzel für Stab oder Stabelement, keines doppelt",
          not any(t in ("Stab", "Stabelement") for k in strg_umschalt for t in folgen[k]),
          str({k: folgen[k] for k in strg_umschalt}))
    stab = w.ribbon.aktion("Struktur", "Stab")
    el = next((b.aktion for b in w.ribbon.befehle if b.text == "Stabelement"), None)
    check("„Stab“ und „Stabelement“ tragen kein Ribbon-Kürzel (die Taste S ist eine Einzeltaste)",
          stab.shortcut().isEmpty() and el is not None and el.shortcut().isEmpty())
    einzeln = [k for k in folgen if QtGui.QKeySequence(k).count() == 1
               and len(k) == 1 and k.isalpha()]
    check("Kein Ribbon-Kürzel ist ein einzelner Buchstabe (die Einzeltasten gehören der Ansicht)",
          not einzeln, str(einzeln))
    tasten = {QtGui.QKeySequence(k).toString(): v for k, v in w.ANSICHT_TASTEN.items()}
    check("Taste S in der Ansicht: der Befehl „Stab“ (maske_stab), keine Taste für das Stabelement",
          tasten.get("S") == "maske_stab" and "maske_stabelement" not in w.ANSICHT_TASTEN.values()
          and len(set(w.ANSICHT_TASTEN)) == len(w.ANSICHT_TASTEN), str(tasten))
    s_zeilen = [z for z in kl.WEITERE_TASTEN if z[1] == "S"]
    check("Kürzelliste: genau eine Zeile für S, sie nennt den Stab mit Nachweis und sein Stabelement",
          len(s_zeilen) == 1 and "Stab mit Nachweis" in s_zeilen[0][3] and "Stabelement" in s_zeilen[0][3],
          str(s_zeilen))
    hinweis = stab.toolTip()
    check("Hinweis am Knopf „Stab“: Stab mit Nachweis samt Stabelement, Taste S",
          "Stab mit Nachweis" in hinweis and "Stabelement" in hinweis and "Taste S" in hinweis, repr(hinweis))
    _ = QtCore


# ---------------------------------------------------------------------------
# 7. Handbuch
# ---------------------------------------------------------------------------
def test_handbuch():
    from tests.handbuch import absatz
    a = absatz("**Der Befehl „Stab“ legt einen Stab mit Nachweis an**")
    check("Handbuch: Befehl „Stab“ wie in RFEM, alle Wege, Stab aus Stabelementen",
          "Struktur → Stab" in a and "Taste S" in a and "Neu: Stab" in a and "Stabelement" in a
          and "Stab aus Stabelementen" in a and "Netz → Stabelement" in a, a[:100])
    check("Handbuch: … rechnet wie das Element, mit dem Stand vorher („Bis zum 03.10.2026 …“)",
          "rechnet genau wie" in a and "Bis zum 03.10.2026" in a, a[-160:])
    # eine Tabellenzeile (absatz() nimmt die ganze Tabelle)
    from tests.handbuch import DOCS
    with open(os.path.join(DOCS, "Benutzerhandbuch.md"), encoding="utf-8") as f:
        s = next((z for z in f.read().splitlines() if z.startswith("| **S** |")), "")
    check("Handbuch: Taste S legt den Stab mit Nachweis an", "Stab mit Nachweis" in s, s)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_wege_zum_stab, test_fachwerkstab_und_zweiter_stab, test_stab_im_baum,
              test_rechnet_wie_das_element, test_stabelement, test_stab_aus_stabelementen,
              test_begriffe, test_kuerzel, test_handbuch):
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
    # Kein w.close(): die Rueckfrage „Ungespeicherte Änderungen“ bliebe stehen
    os._exit(0 if n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
