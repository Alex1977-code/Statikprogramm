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

Nachbesserung nach der Gegenpruefung (03.10.2026): weil jetzt jeder Stab ein
Stab mit Nachweis ist, werden alte Schwachstellen zum Regelfall. Geprueft wird:

* F1: ein Stab, dessen Element geloescht wurde, bleibt leer; „Prüfen“ meldet
  ihn, der Nachweis uebergeht ihn mit Meldung, F5 bricht nicht mehr ab, und
  die Rueckfragen sagen es vorher;
* F2: „Stab“ zwischen zwei Knoten mit vorhandenem Stabelement legt kein
  zweites an (Rechnung gleich, Nachweis wie „Stab aus Stabelementen“), auf
  einem Element eines Stabs weist er ab;
* F3: Ketten kollinearer Staebe mit freiem Zwischenknoten - Warnung in
  „Prüfen“ und im Nachweis, „Stäbe zusammenfassen“ (Stuetze: 6 m, 0,7969),
  die Meldung von „Stäbe automatisch erkennen“;
* F4: Teilen eines Elements fuehrt den Stab nach; F5: Namen ueberschreiben
  keinen Stab; S2: ein Element gehoert zu hoechstens einem Stab; L1, L2: der
  Rechtsklick und der Browser sagen „Stabelement“.

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
        from PySide6 import QtWidgets
        texte = [lb.text() for lb in mk.findChildren(QtWidgets.QLabel)]
        check(f"{name}: Hinweiszeile „es entsteht ein Stab mit Nachweis …“ auch nach dem Anlegen; Feld „Werkstoff“",
              "es entsteht ein Stab mit Nachweis (S…) samt seinem Stabelement" in mk.lbl_hinweis.text()
              and "Werkstoff" in texte and "Material" not in texte, mk.lbl_hinweis.text()[:60])
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
    check("Statuszeile nach „Stab“: „Stab S1 mit Stabelement E0 angelegt: K1–K2, HEB 300“ (Knoten wie im Baum)",
          _statuszeile(w) == "Stab S1 mit Stabelement E0 angelegt: K1–K2, HEB 300", repr(_statuszeile(w)))
    check("… dieselbe Zeile im Protokoll", zeile == [_statuszeile(w)], str(zeile))
    check("… Rückgängig heißt „Stab S1 angelegt“", w._undo[-1][0] == "Stab S1 angelegt", repr(w._undo[-1][0]))
    w.undo()
    app.processEvents()
    check("… und nimmt Stab und Stabelement in einem Schritt zurück", not w.model.members and not w.model.elements,
          f"{sorted(w.model.members)} {len(w.model.elements)}")
    w.redo()
    app.processEvents()
    m = w.model
    check("… Wiederholen bringt beide wieder", list(m.members.get("S1").elements if "S1" in m.members else [])
          == [0] and len(m.elements) == 1, str(sorted(m.members)))
    w._maske_stabelement_anlegen({"knoten": [2, 3], "mat": MAT, "sec": SEC})
    app.processEvents()
    check("Statuszeile nach „Stabelement“: „Stabelement E1 angelegt: K2–K3, HEB 300“, kein Stab",
          _statuszeile(w) == "Stabelement E1 angelegt: K2–K3, HEB 300" and len(m.members) == 1,
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
    check("Löschfrage am Stabelement: „Stabelement E0 wirklich löschen?“ und was mit seinem Stab S1 geschieht",
          fragen[:1] == ["Stabelement E0 wirklich löschen?\n\nStab S1 bleibt ohne Stabelement stehen und wird nicht "
                         "nachgewiesen – danach löschen oder neu zeichnen."], str(fragen[:1]))
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
    check("Strg+Umschalt: kein Kürzel für Stab oder Stabelement",
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
          tasten.get("S") == "maske_stab" and "maske_stabelement" not in w.ANSICHT_TASTEN.values(), str(tasten))
    # echte Doppelpruefung: jede Einzeltaste der Ansicht steht genau einmal in der
    # Kuerzelliste, und kein Kuerzel des Ribbons oder Fensters ist dieselbe Taste
    liste = [z[1] for z in kl.WEITERE_TASTEN if z[2] == "Ansicht" and len(z[1]) == 1]
    check("Einzeltasten: jede genau einmal in der Kürzelliste, keine zugleich Kürzel eines Befehls",
          sorted(liste) == sorted(tasten) and len(set(liste)) == len(liste)
          and not set(tasten) & set(folgen), f"{sorted(liste)} / {sorted(tasten)} / {sorted(set(tasten) & set(folgen))}")
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
    from tests.handbuch import absatz, DOCS
    a = absatz("**Der Befehl „Stab“ legt einen Stab mit Nachweis an**")
    check("Handbuch: Befehl „Stab“ wie in RFEM, alle Wege, Stab aus Stabelementen",
          "Struktur → Stab" in a and "Taste S" in a and "Neu: Stab" in a and "Stabelement" in a
          and "Stab aus Stabelementen" in a and "Netz → Stabelement" in a, a[:100])
    check("Handbuch: … rechnet wie das Element, mit dem Stand vorher („Bis zum 03.10.2026 …“)",
          "rechnet genau wie" in a and "Bis zum 03.10.2026" in a, a[-160:])
    n = absatz("**Was beim Stab mit Nachweis zu beachten ist**")
    check("Handbuch: vorhandenes Element, leerer Stab, Kette, „Stäbe zusammenfassen“, alte Modelle, Entf",
          "schon ein Stabelement ohne Stab" in n and "ohne Stabelement" in n and "freien Zwischenknoten" in n
          and "Stäbe zusammenfassen" in n and "Stab aus Stabelementen" in n and "Entf" in n
          and "0,7969" in n, n[:100])
    k = absatz("Stäbe (Kette von Stabelementen) legt der Befehl")
    check("Handbuch Kapitel 8: jeder gezeichnete Stab ist ein Stab, Knicklänge, Warnung, zusammenfassen",
          "Knicklänge" in k and "Stäbe zusammenfassen" in k and "Kette" in k, k[:100])
    d = absatz("**Ein Doppelklick auf einen Zweig**")
    check("Handbuch: Doppelklick auf „Stäbe“ öffnet die Maske „Stab“, der zweite Knotenklick legt an",
          "Maske *Stab*" in d and "zweite" in d, d[:100])
    with open(os.path.join(DOCS, "Benutzerhandbuch.md"), encoding="utf-8") as f:
        web = next((z for z in f.read().splitlines() if z.startswith("| **Modell** | Projektdaten")), "")
    check("Handbuch, Browser: „Elemente (Stabelement, Schale, …)“", "Elemente (Stabelement, Schale" in web, web[:120])
    # eine Tabellenzeile (absatz() nimmt die ganze Tabelle)
    from tests.handbuch import DOCS
    with open(os.path.join(DOCS, "Benutzerhandbuch.md"), encoding="utf-8") as f:
        s = next((z for z in f.read().splitlines() if z.startswith("| **S** |")), "")
    check("Handbuch: Taste S legt den Stab mit Nachweis an", "Stab mit Nachweis" in s, s)


# ---------------------------------------------------------------------------
# 8. Nachbesserung nach der Gegenpruefung (03.10.2026): F1 bis F5, L1, L2, S2
# ---------------------------------------------------------------------------
def _rahmen_staebe(w, app, anlegen=None):
    """Der Rahmen aus _rahmen, die drei Stuecke mit dem Befehl „Stab“."""
    return _rahmen(w, app, anlegen or w._maske_stab_anlegen)


def _rechnen_wie_f5(w, app):
    """Berechnen wie mit F5 (do_solve im Hintergrund), Rueckfragen beantwortet."""
    import time
    w._trotzdem_rechnen = lambda *a, **k: True
    w._abnahme_bestaetigen = lambda *a, **k: True
    w._vor_rechnung_vernetzen = lambda *a, **k: True
    n0 = len(w.log.toPlainText().splitlines())
    try:
        w.do_solve("all")
        t0 = time.time()
        while time.time() - t0 < 120:
            app.processEvents()
            if not w._rechnung_laeuft():
                break
            time.sleep(0.05)
        for _ in range(20):
            app.processEvents()
    finally:
        for name in ("_trotzdem_rechnen", "_abnahme_bestaetigen", "_vor_rechnung_vernetzen"):
            w.__dict__.pop(name, None)
    return w.log.toPlainText().splitlines()[n0:]


def test_leerer_stab():
    """F1: das Element eines Stabs geloescht - der Stab bleibt leer stehen."""
    from statik3d import solver
    w, app = _fenster()
    m, g = _rahmen_staebe(w, app)
    fragen = []
    w._bestaetigen = lambda text: (fragen.append(text), True)[1]
    try:
        folgen = w._loesch_folgen([("element", [1])])
        w._baum_loeschen("stabelement", "1")
    finally:
        del w._bestaetigen
    app.processEvents()
    check("Rückfrage beim Löschen des Stabelements E1: Stab S2 bleibt leer und wird nicht nachgewiesen",
          len(fragen) == 1 and fragen[0].startswith("Stabelement E1 wirklich löschen?")
          and "Stab S2 bleibt ohne Stabelement stehen und wird nicht nachgewiesen" in fragen[0], str(fragen))
    check("… ebenso die Rückfrage von Entf in der Ansicht (Auswahlart Netz)",
          "Stab S2 bleibt ohne Stabelement stehen" in folgen, repr(folgen))
    check("Vorbereitung: S2 ist leer, S1 und S3 haben ihr Element",
          m.members["S2"].elements == [] and len(m.members["S1"].elements) == 1, str({k: v.elements for k, v in m.members.items()}))
    pruefung = m.check()
    check("„Prüfen“ meldet den leeren Stab", any(z.startswith("WARNUNG: Stab S2 hat kein Stabelement") for z in pruefung),
          str(pruefung))
    an = solver.solve_all(m, design=True)
    # seit Runde 2 (G2) steht S2 als nicht geführt im Ergebnis, nicht nur als Warnzeile
    check("Nachweis EC3: S1 und S3 nachgewiesen, S2 als nicht geführt (kein Stabelement), kein „alle erfüllt“",
          sorted(an.design.members) == ["S1", "S2", "S3"] and an.design.members["S2"].fehler
          and "nicht geführt: S2 (kein Stabelement" in an.design.summary()
          and "alle erfuellt" not in an.design.summary(), an.design.summary()[-160:])
    neu = _rechnen_wie_f5(w, app)
    check("Berechnen (F5) bricht nicht ab: Ergebnis und Nachweis da, die Meldung im Protokoll",
          w.analysis is not None and getattr(w.analysis, "design", None) is not None
          and not any("IndexError" in z or z.startswith("FEHLER") for z in neu)
          and any("nicht geführt: S2 (kein Stabelement" in z for z in neu), str(neu[-4:]))


def test_kein_paralleles_element():
    """F2: „Stab“ zwischen zwei Knoten, die schon ein Stabelement verbindet."""
    import numpy as np
    from statik3d import solver
    w, app = _fenster()
    m, g = _rahmen(w, app, w._maske_stabelement_anlegen)
    u0 = solver.solve_all(m, design=False).cases[g].u
    w._maske_stab_anlegen({"knoten": [0, 1], "mat": MAT, "sec": SEC})
    s1 = _statuszeile(w)
    w._maske_stab_anlegen({"knoten": [3, 2], "mat": MAT, "sec": SEC})
    check("„Stab“ über vorhandenen Stabelementen: kein neues Element, die Stäbe nehmen E0 und E2",
          len(m.elements) == 3 and {k: list(v.elements) for k, v in m.members.items()} == {"S1": [0], "S2": [2]},
          f"{len(m.elements)} {({k: v.elements for k, v in m.members.items()})}")
    check("… die Statuszeile sagt es", "Stab S1 um das vorhandene Stabelement E0 angelegt: K0–K1" in s1, repr(s1))
    an = solver.solve_all(m, design=True)
    du = float(np.max(np.abs(an.cases[g].u - u0)))
    check("Rechnung wie vorher: Verschiebungen gleich (Unterschied 0)", du == 0.0, f"max |Δu| = {du:.3e}")
    ref, _g = _rahmen(w, app, w._maske_stabelement_anlegen)
    for nm, el in (("S1", "0"), ("S2", "2")):
        w._objekt_uebernehmen("stab", nm, {"name": nm, "elemente": el, "design": True}, True)
    an_ref = solver.solve_all(ref, design=True)
    eta = {k: round(float(x.util), 6) for k, x in an.design.members.items()}
    eta_ref = {k: round(float(x.util), 6) for k, x in an_ref.design.members.items()}
    check("Nachweis wie „Stab aus Stabelementen“ an denselben Elementen", eta == eta_ref and len(eta) == 2,
          f"{eta} / {eta_ref}")
    # derselbe Ort noch einmal: abgewiesen
    m = w.model
    w._maske_stab_anlegen({"knoten": [1, 2], "mat": MAT, "sec": SEC})
    w.fehler_liste.clear()
    n_el, n_st = len(m.elements), len(m.members)
    w._maske_stab_anlegen({"knoten": [2, 1], "mat": MAT, "sec": SEC})
    check("Noch einmal „Stab“ auf K1–K2 (gehört schon zu S3): abgewiesen, mit Hinweis",
          len(m.elements) == n_el and len(m.members) == n_st
          and any("liegt schon Stabelement E1 von Stab S3" in f for f in w.fehler_liste), str(w.fehler_liste))
    w._maske_stabelement_anlegen({"knoten": [1, 2], "mat": MAT, "sec": SEC})
    check("„Stabelement“ parallel zu E1: angelegt, aber nicht still (Statuszeile)",
          len(m.elements) == n_el + 1 and "zwei parallele Elemente tragen doppelt" in _statuszeile(w),
          repr(_statuszeile(w)))


def _stuetze(w, app, ab=(0, 2, 4, 6)):
    """Die Stuetze aus der Gegenpruefung (pruef_stuetze): HEB 200, 6 m aus drei
    Staeben, unten eingespannt, oben seitlich gehalten, 600 kN Druck."""
    from statik3d.model import Material, Section
    w.new_model()
    m = w.model
    m.add_material(Material.steel(MAT))
    m.add_section(Section.from_profile("HEB 200"))
    for z in ab:
        m.add_node(0, 0, z)
    m.support(0, "all")
    m.support(len(ab) - 1, [0, 1])
    g = next(iter(m.load_cases))
    m.load_node(len(ab) - 1, Fz=-600e3, case=g)
    for a in range(len(ab) - 1):
        w._maske_stab_anlegen({"knoten": [a, a + 1], "mat": MAT, "sec": "HEB 200"})
    app.processEvents()
    return m, g


def test_kette_und_zusammenfassen():
    """F3: Warnung bei freien Ketten, „Stäbe zusammenfassen“, Meldung von „automatisch erkennen“."""
    from PySide6 import QtWidgets
    from statik3d import solver
    w, app = _fenster()
    m, g = _stuetze(w, app)
    warn = [z for z in m.check() if "bilden eine Kette" in z]
    # eine Warnung je Kette, nicht je Stoss (Runde 2, G5)
    check("„Prüfen“ warnt einmal für die Kette S1–S3 mit den freien Stößen K1 und K2",
          warn == ["WARNUNG: Stäbe S1, S2 und S3 bilden eine Kette mit freien Zwischenknoten K1 und K2 – "
                   "Knicklänge prüfen oder „Stäbe zusammenfassen“"], str(warn))
    n0 = len(w.log.toPlainText().splitlines())
    w.do_check()
    check("… auch im Protokoll von „Prüfen“", any("bilden eine Kette" in z for z in
                                                  w.log.toPlainText().splitlines()[n0:]))
    an = solver.solve_all(m, design=True)
    s = an.design.summary()
    eta = {k: round(float(x.util), 4) for k, x in an.design.members.items()}
    check("Nachweis EC3: drei Stäbe je 2 m, Ausnutzung 0,2856, die Warnung im Protokoll, Urteil unberührt",
          eta == {"S1": 0.2856, "S2": 0.2856, "S3": 0.2856}
          and "WARNUNG (Knicklänge): Stäbe S1, S2 und S3 bilden eine Kette" in s and not an.design.warnungen,
          f"{eta} {s[-120:]!r}")
    w.auto_members()
    st = _statuszeile(w)
    check("„Stäbe automatisch erkennen“: 3 Stabelemente gehören schon zu Stäben, Verweis auf „zusammenfassen“",
          "3 Stabelemente gehören schon zu Stäben und wurden übergangen" in st and "Stäbe zusammenfassen" in st,
          repr(st))
    befehle = [b for b in w.ribbon.befehle if b.text == "Stäbe zusammenfassen"]
    check("Struktur → Nachweisstäbe ▾ → „Stäbe zusammenfassen“", [(b.register, b.gruppe) for b in befehle]
          == [("Struktur", "Stäbe")], str([(b.register, b.gruppe) for b in befehle]))
    w.sel_staebe = ["S1", "S2", "S3"]
    menu = QtWidgets.QMenu()
    w._auswahlmenue(menu)
    sub = next((a.menu() for a in menu.actions() if a.text() == "Stäbe (3)"), None)
    check("Rechtsklick der Auswahl: „Stäbe (3)“ → „Stäbe zusammenfassen“",
          sub is not None and "Stäbe zusammenfassen" in [a.text() for a in sub.actions()],
          str([a.text() for a in sub.actions()] if sub else None))
    n_undo = len(w._undo)
    if befehle:
        befehle[0].aktion.trigger()
        app.processEvents()
    check("Zusammengefasst: ein Stab S1 aus E0, E1, E2, L = 6 m, ein Rückgängig-Schritt",
          {k: list(v.elements) for k, v in m.members.items()} == {"S1": [0, 1, 2]}
          and abs(m.member_length(m.members["S1"]) - 6.0) < 1e-12 and len(w._undo) == n_undo + 1,
          f"{({k: v.elements for k, v in m.members.items()})} {_statuszeile(w)!r}")
    an = solver.solve_all(m, design=True)
    mc = an.design.members.get("S1")
    check("… Nachweis: L = 6 m, Ausnutzung 0,7969 wie vor dem 03.10.2026 (ein Stab aus drei Elementen)",
          mc is not None and abs(mc.L - 6.0) < 1e-9 and round(float(mc.util), 4) == 0.7969,
          f"L {getattr(mc, 'L', None)} η {getattr(mc, 'util', None)}")
    check("… und keine Warnung mehr", not [z for z in m.check() if "bilden eine Kette" in z])
    w.undo()
    app.processEvents()
    m = w.model
    check("Rückgängig: wieder S1, S2, S3 mit je einem Element",
          {k: list(v.elements) for k, v in m.members.items()} == {"S1": [0], "S2": [1], "S3": [2]},
          str({k: v.elements for k, v in m.members.items()}))
    # gehalten oder quer angeschlossen: keine Warnung
    m.support(1, [0, 1])
    m.add_node(2, 0, 4)
    m.add_element("beam", [2, 4], MAT, "HEB 200")
    check("Lager an K1, Querstab an K2: keine Warnung", not m.stabketten_frei(), str(m.stabketten_frei()))


def test_zusammenfassen_grenzen():
    """Was „Stäbe zusammenfassen“ abweist, und Linienlasten gehen mit."""
    import numpy as np
    from statik3d import solver
    w, app = _fenster()
    m, g = _stuetze(w, app)
    m.add_node(2, 0, 6)
    w._maske_stab_anlegen({"knoten": [3, 4], "mat": MAT, "sec": "HEB 200"})   # S4 knickt an K3 ab
    for namen, grund in ((["S1"], "Mindestens zwei Stäbe"),
                         (["S1", "S3"], "nicht in einer offenen Kette"),
                         (["S3", "S4"], "nicht auf einer Geraden")):
        w.fehler_liste.clear()
        w.staebe_zusammenfassen(namen)
        check(f"„Stäbe zusammenfassen“ mit {namen}: abgewiesen („{grund}“), nichts geändert",
              any(grund in f for f in w.fehler_liste) and len(m.members) == 4, str(w.fehler_liste))
    # gegen die Kette gezeichnet
    m, g = _stuetze(w, app)
    m.members["S2"].elements = []
    e = w.model.add_element("beam", [2, 1], MAT, "HEB 200")
    m.members["S2"].elements = [e]
    w.fehler_liste.clear()
    w.staebe_zusammenfassen(["S1", "S2"])
    check("Ein Stab gegen die Kette gezeichnet: abgewiesen mit Hinweis", any("gegen die Kette" in f for f in w.fehler_liste),
          str(w.fehler_liste))
    # verwendet von einem Verformungsnachweis
    m, g = _stuetze(w, app)
    m.add_verformungsgrenze("V1", art="stab", stab="S2")
    w.fehler_liste.clear()
    w.staebe_zusammenfassen(["S1", "S2"])
    check("S2 hat einen Verformungsnachweis: abgewiesen, der Grund nennt ihn",
          any("Verformungsnachweis V1" in f for f in w.fehler_liste) and "S2" in m.members, str(w.fehler_liste))
    # Linienlasten gehen mit, die Rechnung bleibt
    from statik3d.model import Material, Section
    w.new_model()
    m = w.model
    m.add_material(Material.steel(MAT))
    m.add_section(Section.from_profile("IPE 300"))
    for x in (0, 3, 7):
        m.add_node(x, 0, 0)
    m.support(0, "all")
    m.support(2, [1, 2])
    for a, b in ((0, 1), (1, 2)):
        w._maske_stab_anlegen({"knoten": [a, b], "mat": MAT, "sec": "IPE 300"})
    g = next(iter(m.load_cases))
    # verschiedene Lasten an den Staeben: abgewiesen (Runde 2, G1 - bis dahin
    # gingen sie verschoben mit)
    m.add_linienlast("S1", [0, 0, -5e3], case=g)                      # bis zum Ende
    m.add_linienlast("S2", [0, 0, -8e3], case=g, von=1.0, bis=2.5, q2=[0, 0, -2e3])
    m.lasten_verteilen()
    w.fehler_liste.clear()
    w.staebe_zusammenfassen(["S2", "S1"])
    check("Verschiedene Linienlasten an S1 und S2: abgewiesen, der Grund nennt beide",
          sorted(m.members) == ["S1", "S2"] and any("Lasten am Stab verschieden: S1 Linienlast" in f
                                                    and "S2 Linienlast" in f for f in w.fehler_liste),
          str(w.fehler_liste))
    # gleiche Linienlasten an beiden: sie gehen mit, die Rechnung bleibt
    m.load_cases[g].linienlasten = []
    m.add_linienlast("S1", [0, 0, -8e3], case=g, von=1.0, bis=2.5, q2=[0, 0, -2e3])
    m.add_linienlast("S2", [0, 0, -8e3], case=g, von=1.0, bis=2.5, q2=[0, 0, -2e3])
    m.lasten_verteilen()
    u0 = solver.solve_all(m, design=False).cases[g].u
    name = w.staebe_zusammenfassen(["S2", "S1"])
    lasten = [(ll.ziel, round(ll.von, 9), round(ll.bis, 9)) for ll in m.load_cases[g].linienlasten]
    check("Gleiche Linienlasten auf den zusammengefassten Stab verschoben (1–2,5 m und 4–5,5 m)",
          name == "S1" and lasten == [("S1", 1.0, 2.5), ("S1", 4.0, 5.5)], str(lasten))
    u1 = solver.solve_all(m, design=False).cases[g].u
    du = float(np.max(np.abs(u1 - u0)))
    check("… die Rechnung bleibt (Verschiebungen gleich bis auf 1e-12 relativ)",
          du <= 1e-12 * float(np.max(np.abs(u0))) and float(np.max(np.abs(u0))) > 0,
          f"max |Δu| = {du:.3e} bei |u|max = {float(np.max(np.abs(u0))):.3e}")


def test_teilen_im_stab():
    """F4: „Freie Stabenden anschließen…“ teilt das Element eines Stabs - das
    neue Element kommt in denselben Stab, an seine Stelle entlang der Achse."""
    from statik3d.importers import hicad_szn
    from statik3d.model import Material, Section
    w, app = _fenster()
    w.new_model()
    m = w.model
    m.add_material(Material.steel(MAT))
    m.add_section(Section.from_profile(SEC))
    for p in ((0, 0, 0), (6, 0, 0), (3, 0, 2), (3, 0, 0.0005)):
        m.add_node(*p)
    w._maske_stab_anlegen({"knoten": [0, 1], "mat": MAT, "sec": SEC})
    w._maske_stabelement_anlegen({"knoten": [2, 3], "mat": MAT, "sec": SEC})
    r = hicad_szn.an_staebe_anschliessen(m, 0.01, [])
    check("Freies Stabende angeschlossen, das Element von S1 geteilt", r["geteilt"] == 1 and len(m.elements) == 3,
          str(r))
    check("… das neue Element E2 gehört zu S1, dahinter; L bleibt 6 m",
          list(m.members["S1"].elements) == [0, 2] and abs(m.member_length(m.members["S1"]) - 6.0) < 1e-9,
          f"{m.members['S1'].elements} L {m.member_length(m.members['S1']):.4f}")
    # Reihenfolge an jeder Stelle einer Kette
    for teil, erwartet in ((0, [0, 9, 1, 2]), (1, [0, 1, 9, 2]), (2, [0, 1, 2, 9])):
        w.new_model()
        mm = w.model
        mm.add_material(Material.steel(MAT))
        mm.add_section(Section.from_profile(SEC))
        for x in (0, 2, 4, 6):
            mm.add_node(x, 0, 0)
        mid = mm.add_node(2 * teil + 1, 0, 0)
        els = [mm.add_element("beam", [i, i + 1], MAT, SEC) for i in range(3)]
        mm.add_member("S1", els)
        hinten = int(mm.elements[teil].nodes[-1])
        mm.elements[teil].nodes = [int(mm.elements[teil].nodes[0]), mid]
        while len(mm.elements) < 9:
            mm.add_element("beam", [0, 1], MAT, SEC)      # Platzhalter, damit das neue E9 heisst
        neu = mm.add_element("beam", [mid, hinten], MAT, SEC)
        mm.stabelement_geteilt(teil, neu)
        check(f"Teilen von E{teil} in einer Kette aus drei: E9 steht dahinter", list(mm.members["S1"].elements) == erwartet,
              str(mm.members["S1"].elements))


def test_namen():
    """F5: neue Staebe ueberschreiben keinen vorhandenen."""
    w, app = _fenster()
    m, g = _rahmen_staebe(w, app)
    w._bestaetigen = lambda text: True
    try:
        w._baum_loeschen("stab", "S1")
    finally:
        del w._bestaetigen
    alt, alt3 = list(m.members["S2"].elements), list(m.members["S3"].elements)
    m.add_node(0, 0, 8)
    m.add_node(0, 0, 12)
    m.add_element("beam", [1, 4], MAT, SEC)
    m.add_element("beam", [4, 5], MAT, SEC)
    w.auto_members()
    check("„Stäbe automatisch erkennen“ nach dem Löschen von S1: neuer Stab S4 (E0, E3, E4), S2 und S3 bleiben",
          sorted(m.members) == ["S2", "S3", "S4"] and list(m.members["S2"].elements) == alt
          and list(m.members["S3"].elements) == alt3
          and len(m.members["S4"].elements) == 3, str({k: v.elements for k, v in m.members.items()}))
    m.add_node(9, 0, 0)
    e = m.add_element("beam", [3, 6], MAT, SEC)
    w.ed_member_elems.setText(str(e))
    w.member_from_elements()
    check("„Aus Element-Nr.…“: der nächste freie Name S5", "S5" in m.members and list(m.members["S5"].elements) == [e]
          and list(m.members["S2"].elements) == alt, str(sorted(m.members)))
    w.fehler_liste.clear()
    w.ed_member_elems.setText(str(e))
    w.member_from_elements()
    check("„Aus Element-Nr.…“ mit einem Element von S5: abgewiesen", len(m.members) == 4
          and any("gehört schon zu Stab S5" in f for f in w.fehler_liste), str(w.fehler_liste))


def test_rechtsklick_stabelement():
    """L1: der Rechtsklick nennt ein Stabelement „Stabelement E…“."""
    from PySide6 import QtWidgets
    from statik3d.model import ShellProp
    w, app = _fenster()
    m, g = _rahmen_staebe(w, app)
    m.add_shell_prop(ShellProp("T10", 0.01))
    s = m.add_element("shell3", [0, 1, 2], MAT, "T10")
    check("Titel: „Stabelement E1“ für ein Stabelement, „Element E3“ für eine Schale",
          w._ziel_titel(("element", 1)) == "Stabelement E1" and w._ziel_titel(("element", s)) == f"Element E{s}",
          f"{w._ziel_titel(('element', 1))} / {w._ziel_titel(('element', s))}")
    menu = QtWidgets.QMenu()
    w._objektmenue(menu, ("element", 1), False, w._menuestand())
    texte = [a.text() for a in menu.actions() if a.text()]
    check("… und „Stabelement löschen“ im Menü", texte[0] == "Stabelement E1" and "Stabelement löschen" in texte,
          str(texte))


def test_web_stabelement():
    """L2: „+ Stab“ im Browser legt nur ein Element an - es heisst dort so."""
    stamm = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(stamm, "statik3d", "web", "static", "app.js"), encoding="utf-8") as f:
        js = f.read()
    zeile = next((z for z in js.splitlines() if 'data-op="add_element"' in z and "Balken" in z), "")
    check("Web: die Form „add_element“ heißt „Stabelement zwischen zwei Knoten“, Knopf „+ Stabelement“",
          "<h3>Stabelement zwischen zwei Knoten</h3>" in zeile and ">+ Stabelement</button>" in zeile, zeile[:120])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_wege_zum_stab, test_fachwerkstab_und_zweiter_stab, test_stab_im_baum,
              test_rechnet_wie_das_element, test_stabelement, test_stab_aus_stabelementen,
              test_begriffe, test_kuerzel, test_handbuch, test_leerer_stab, test_kein_paralleles_element,
              test_kette_und_zusammenfassen, test_zusammenfassen_grenzen, test_teilen_im_stab, test_namen,
              test_rechtsklick_stabelement, test_web_stabelement):
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
