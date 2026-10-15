"""Reibung an Lagern aus RFEM 6 nur mit Reibungsart (15.10.2026).

RFEM 6 fuehrt Reibung an einem Lager als eigene Art der Nichtlinearitaet
(Schnittstelle RFEM 6.15, proto-Dateien unter tools/WebServiceGrpc/proto):

* Flaechenlager (surface_support.proto): die Nichtlinearitaet von u_z ist
  1 „Ausfall bei negativer Kontaktspannung“ oder 2 „... positiver ...“, die
  Art dazu (negative/positive_nonlinearity_type, in der Datenbank
  negative/positiveNonlinearityDefinitionType) 0 „einseitige Wirkung“,
  1 „Fliessen der Kontaktspannung“ oder 2 „Reibung in der Ebene xy“; der
  Beiwert steht in negative/positive_friction_coefficient.
* Linienlager (line_support.proto): Kennzahl 8/9 „Reibung Richtung 1/2“ je
  Freiheitsgrad, Knotenlager (nodal_support.proto) dazu 10 „1-2“ und
  11 „1+2“.

Das Feld des Reibbeiwerts traegt in jeder RFEM-Datei einen Wert, am
Drehlager 0,1 an allen sechs Flaechenlagertypen, auch an den linearen - es
ist der Vorgabewert des Feldes. Bis zum 15.10.2026 setzte der Import ihn
trotzdem an, sobald irgendeine Nichtlinearitaet aktiv war: aus dem
Flaechenlager „Starr“ (Ausfall bei Zug, in der Flaeche frei) wurde ein Lager,
das in der Flaeche bis mu * N starr haftet. Seither gilt der Beiwert nur mit
einer Reibungsart; sonst gilt der Freiheitsgrad nach seiner Federkonstanten
(0 = frei), und das Protokoll nennt den nicht angesetzten Beiwert gebuendelt.

Ein frueher gespeichertes Modell bekommt beim Oeffnen nur einen Hinweis mit
der Aktion „Lager aus RFEM nachlesen…“, die der Anwender ausloest.

Am Drehlager (STATIK3D_DREHLAGER_RF6 oder der Pfad unter RFEM_Modelle, nur
lesend): „Starr“ in der Flaeche frei, der Hinweis steht im Protokoll.

Aufruf:  python -m tests.test_rfem6_lagerreibung
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_lagerreibung_"), "einstellungen.json")

from statik3d.importers import rfem6_db as R6                      # noqa: E402
from statik3d.model import Model, DofBehaviour                     # noqa: E402
from tests.test_rfem6 import INF, make_rf6                         # noqa: E402

RESULTS = []
_FENSTER = {}
AKTION = "Lager aus RFEM nachlesen…"
#: der Satz im Importprotokoll (gebuendelt)
SATZ = "ohne Reibungsart"


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def _datei(tmp, name, flaechenlager=(), knotenlager=(), linienlager=()):
    """Eine Flaeche 2 x 2 m mit Randlinien; ``flaechenlager`` als
    (Name, Federn, Nichtlinearitaet, mu, Art) an der Flaeche, Knotenlager an
    Knoten 1, Linienlager an Linie 1."""
    sup = [(n, k, nl, fr, [1]) for n, k, nl, fr in knotenlager]
    lsup = [(n, k, nl, fr, [1]) for n, k, nl, fr in linienlager]
    srf = [(n, k, nl, mu, [1], art) for n, k, nl, mu, art in flaechenlager]
    return make_rf6(
        os.path.join(tmp, name),
        nodes=[(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)],
        lines=[[1, 2], [2, 3], [3, 4], [4, 1]],
        members=[(1, 1, None)],
        supports=sup, line_supports=lsup,
        surfaces=[[1, 2, 3, 4]], surface_supports=srf)


#: Federn eines Flaechenlagers wie „Starr“ am Drehlager: in der Flaeche 0,
#: senkrecht 2,5e11 N/m^3 (mit Ausfall ab 1e11 „starr mit Ausfall“)
STARR = (0.0, 0.0, 2.5e11, 0.0, 0.0)


def test_flaechenlager():
    print("\n--- Flaechenlager: Reibbeiwert nur mit Reibungsart ---")
    tmp = tempfile.mkdtemp()
    try:
        # (a) Ausfall bei Zug, Art „einseitige Wirkung“, Beiwert 0,1 im Feld
        log = []
        m = R6.read_rf6(_datei(tmp, "a.rf6", flaechenlager=[("Starr", STARR, 1, 0.1, 0)]), log=log)
        ss = m.surface_supports[0]
        b0, b1, b2 = (ss.dof_behaviour(d) for d in range(3))
        check("(a) Ausfall bei Zug + Beiwert 0,1: ux in der Flaeche frei, ohne Reibung",
              b0.typ == "free" and b0.mu == 0.0, b0.describe() + f", mu = {b0.mu}")
        check("(a) ... ebenso uy", b1.typ == "free" and b1.mu == 0.0, b1.describe())
        check("(a) uz starr mit Ausfall bei Zug wie bisher", b2.typ == "rigid" and b2.failure == "zug",
              b2.describe())
        zeilen = [z.strip() for z in log if SATZ in z]
        check("(a) das Protokoll nennt den nicht angesetzten Beiwert in einem Satz",
              len(zeilen) == 1 and "Starr" in zeilen[0] and "0,1" in zeilen[0], str(zeilen)[:220])
        check("(a) keine Zeile „Reibung mu = 0.1 in x und y“ mehr",
              not any("Reibung mu = 0.1 in x und y" in z for z in log))
        check("(a) das Modell weiss, dass der Import die Regel kennt (kein Hinweis beim Oeffnen)",
              bool(m.meta.get(R6.LAGERREIBUNG_MERKMAL)), str(m.meta.get(R6.LAGERREIBUNG_MERKMAL)))

        # (b) Ausfall bei Zug mit Art „Reibung in der Ebene xy“
        log = []
        m = R6.read_rf6(_datei(tmp, "b.rf6", flaechenlager=[("Gleit", STARR, 1, 0.1, 2)]), log=log)
        ss = m.surface_supports[0]
        b0, b1 = ss.dof_behaviour(0), ss.dof_behaviour(1)
        check("(b) Reibungsart + 0,1: Reibung 0,1 in ux und uy, bezogen auf uz",
              abs(b0.mu - 0.1) < 1e-6 and abs(b1.mu - 0.1) < 1e-6 and b0.mu_ref == 2 and b1.mu_ref == 2,
              f"{b0.mu:g}/{b1.mu:g}, ref {b0.mu_ref}/{b1.mu_ref}")
        check("(b) ... haftet starr bis mu * N", b0.typ == "rigid" and b1.typ == "rigid", f"{b0.typ}/{b1.typ}")
        check("(b) kein Satz zum nicht angesetzten Beiwert", not any(SATZ in z for z in log))

        # (b') Ausfall bei Druck (Kennzahl 2): die Art steht im positiven Feld
        m = R6.read_rf6(_datei(tmp, "b2.rf6", flaechenlager=[("GleitD", STARR, 2, 0.2, (0, 2))]), log=[])
        b0 = m.surface_supports[0].dof_behaviour(0)
        check("(b') Ausfall bei Druck + Reibungsart im positiven Feld: Reibung 0,2",
              abs(b0.mu - 0.2) < 1e-6, f"mu = {b0.mu:g}")

        # (c) linear (keine Nichtlinearitaet) mit Beiwert im Feld: wie bisher
        log = []
        m = R6.read_rf6(_datei(tmp, "c.rf6", flaechenlager=[("Linear", (0.0, 5e6, INF, 0.0, 0.0), 0, 0.1, 0)]),
                        log=log)
        ss = m.surface_supports[0]
        b0, b1, b2 = (ss.dof_behaviour(d) for d in range(3))
        check("(c) linear: ux frei, uy Feder 5e6, uz starr, keine Reibung",
              b0.typ == "free" and b1.typ == "spring" and abs(b1.stiffness - 5e6) < 1e-6
              and b2.typ == "rigid" and b0.mu == b1.mu == b2.mu == 0.0,
              f"{b0.describe()} | {b1.describe()} | {b2.describe()}")
        check("(c) kein Satz zum Beiwert (das alte Verhalten setzte ihn ohne Nichtlinearitaet nie an)",
              not any(SATZ in z for z in log))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_knoten_linienlager():
    print("\n--- Knoten- und Linienlager: Reibbeiwert nur mit Reibungsart ---")
    tmp = tempfile.mkdtemp()
    try:
        # Beiwert in Spalte XZ (ux, bezogen auf uz) und YZ (uy) - einmal ohne,
        # einmal mit Reibungsart (Kennzahl 9 „Reibung Richtung 2“)
        fr = (0.0, 0.3, 0.0, 0.25, 0.0, 0.0)
        log = []
        f = _datei(tmp, "k.rf6",
                   knotenlager=[("OhneArt", (0.0, 0.0, INF, 0.0, 0.0, 0.0), (0, 0, 1, 0, 0, 0), fr)],
                   linienlager=[("LinieOhneArt", (0.0, 0.0, INF, 0.0, 0.0, 0.0), (0, 0, 1, 0, 0, 0), fr)])
        m = R6.read_rf6(f, log=log)
        s = [x for x in m.supports if x.name == "OhneArt"][0]
        bx, by = s.dof_behaviour(0), s.dof_behaviour(1)
        check("Knotenlager ohne Reibungsart: ux/uy frei, ohne Reibung",
              bx.typ == "free" and by.typ == "free" and bx.mu == by.mu == 0.0,
              f"{bx.describe()} | {by.describe()}")
        ls = m.line_supports[0]
        lx = ls.dof_behaviour(0)
        check("Linienlager ohne Reibungsart: ux frei, ohne Reibung", lx.typ == "free" and lx.mu == 0.0,
              lx.describe())
        zeilen = [z.strip() for z in log if SATZ in z]
        check("ein Satz nennt beide Lager gebuendelt",
              len(zeilen) == 1 and "OhneArt" in zeilen[0] and "LinieOhneArt" in zeilen[0], str(zeilen)[:220])

        log = []
        f = _datei(tmp, "k2.rf6",
                   knotenlager=[("MitArt", (0.0, 0.0, INF, 0.0, 0.0, 0.0), (9, 9, 1, 0, 0, 0), fr)],
                   linienlager=[("LinieMitArt", (0.0, 0.0, INF, 0.0, 0.0, 0.0), (8, 0, 1, 0, 0, 0), fr)])
        m = R6.read_rf6(f, log=log)
        s = [x for x in m.supports if x.name == "MitArt"][0]
        bx, by = s.dof_behaviour(0), s.dof_behaviour(1)
        check("Knotenlager mit Reibungsart (Kennzahl 9): Reibung 0,3/0,25 auf uz, starr bis mu * N",
              abs(bx.mu - 0.3) < 1e-12 and abs(by.mu - 0.25) < 1e-12 and bx.mu_ref == 2
              and bx.typ == by.typ == "rigid", f"{bx.describe()} | {by.describe()}")
        ls = m.line_supports[0]
        lx, ly = ls.dof_behaviour(0), ls.dof_behaviour(1)
        check("Linienlager: ux mit Reibungsart (8) mit Reibung, uy ohne Art frei",
              abs(lx.mu - 0.3) < 1e-12 and ly.typ == "free" and ly.mu == 0.0, f"{lx.describe()} | {ly.describe()}")
        zeilen = [z.strip() for z in log if SATZ in z]
        check("... der Satz nennt nur uy des Linienlagers",
              len(zeilen) == 1 and "LinieMitArt" in zeilen[0] and "„MitArt“" not in zeilen[0], str(zeilen)[:220])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _alt(tmp):
    """Modell aus (a) + (b) + eigenem Lager, gespeichert so, wie der Import es
    bis zum 15.10.2026 anlegte: „Starr“ in ux/uy starr mit mu = 0,1."""
    rf6 = _datei(tmp, "alt.rf6", flaechenlager=[("Starr", STARR, 1, 0.1, 0), ("Gleit", STARR, 1, 0.1, 2),
                                               ("Eigen", STARR, 1, 0.1, 0)])
    m = R6.read_rf6(rf6, log=[])
    for ss in m.surface_supports:
        mu = 0.3 if ss.name == "Eigen" else 0.1        # „Eigen“: vom Anwender auf 0,3 gestellt
        for d in (0, 1):
            ss.behaviour[d] = DofBehaviour("rigid", mu=mu, mu_ref=2)
    m.meta.pop(R6.LAGERREIBUNG_MERKMAL, None)
    m.meta["quelle"] = rf6
    pfad = os.path.join(tmp, "alt.json")
    m.save(pfad)
    return pfad, rf6


def _mu(m, name, d=0):
    return [ss for ss in m.surface_supports if ss.name == name][0].dof_behaviour(d)


def test_gespeichertes_modell():
    print("\n--- Gespeichertes Modell von vor dem 15.10.2026: Hinweis, Nachlesen auf Anweisung ---")
    tmp = tempfile.mkdtemp()
    try:
        pfad, rf6 = _alt(tmp)
        alt = Model.load(pfad)
        h = [x for x in alt.importhinweise if x.get("art") == "lagerreibung"]
        check("beim Oeffnen: ein Hinweis zur Lagerreibung", len(h) == 1 and not h[0].get("erledigt"),
              h[0].get("text", "")[:200] if h else "kein Hinweis")
        check("... mit der Aktion als Vorschlag und der RFEM-Datei",
              h and AKTION.rstrip("…") in str(h[0].get("vorschlag", "")) and h[0].get("datei") == rf6,
              str(h[0].get("vorschlag", ""))[:120] if h else "")
        # die Liste nennt je Lager Freiheitsgrade und Beiwert (15.10.2026) und den Stand der RFEM-Datei
        txt = h[0].get("text", "") if h else ""
        check("... die Liste nennt je Lager Freiheitsgrade und Beiwert",
              "Starr (ux, uy μ = 0,1)" in txt and "Gleit (ux, uy μ = 0,1)" in txt
              and "Eigen (ux, uy μ = 0,3)" in txt, txt[:260])
        zeile = next((z for z in alt._ladehinweise if "Reibung" in z), "")
        check("... die Protokollzeile sagt, ob die RFEM-Datei noch da liegt (der gespeicherte Text nicht)",
              "Die RFEM-Datei liegt noch unter" in zeile and "RFEM-Datei liegt" not in txt, zeile[-260:])
        check("... und im Protokoll des Oeffnens", any("Reibung" in z and "RFEM" in z for z in alt._ladehinweise),
              next((z[:160] for z in alt._ladehinweise if "Reibung" in z), "-"))
        check("von selbst wird nichts umgestellt", _mu(alt, "Starr").mu == 0.1 and _mu(alt, "Starr").typ == "rigid")
        log = []
        aus = R6.lager_aus_rfem(alt, log=log)
        b0, b1 = _mu(alt, "Starr", 0), _mu(alt, "Starr", 1)
        check("Nachlesen: „Starr“ in ux/uy frei, ohne Reibung", b0.typ == b1.typ == "free" and b0.mu == b1.mu == 0.0,
              f"{b0.describe()} | {b1.describe()}")
        check("Nachlesen: uz von „Starr“ bleibt starr mit Ausfall",
              _mu(alt, "Starr", 2).typ == "rigid" and _mu(alt, "Starr", 2).failure == "zug")
        check("Nachlesen: „Gleit“ (Reibungsart in RFEM) behaelt mu = 0,1", abs(_mu(alt, "Gleit").mu - 0.1) < 1e-6,
              _mu(alt, "Gleit").describe())
        check("Nachlesen: „Eigen“ (vom Anwender auf 0,3 gestellt) bleibt", abs(_mu(alt, "Eigen").mu - 0.3) < 1e-12,
              _mu(alt, "Eigen").describe())
        check("Nachlesen nennt die Lager", aus.get("ohne_reibung") == ["Starr"] and aus.get("mit_reibung") == ["Gleit"]
              and aus.get("eigen") == ["Eigen"], str({k: v for k, v in aus.items() if k != "datei"}))
        check("... und schreibt eine Zeile ins Protokoll", any("nachgelesen" in z and "Starr" in z for z in log),
              str(log[-1:])[:200])
        check("Nachlesen: der Hinweis ist erledigt",
              all(x.get("erledigt") for x in alt.importhinweise if x.get("art") == "lagerreibung"))
        alt.save(pfad)
        wieder = Model.load(pfad)
        check("nach dem Speichern: kein neuer Hinweis, die Einstellung bleibt",
              not any(x.get("art") == "lagerreibung" and not x.get("erledigt") for x in wieder.importhinweise)
              and _mu(wieder, "Starr").typ == "free")
        # liegt die RFEM-Datei nicht mehr da, sagt es schon die Protokollzeile beim Oeffnen
        pfad3, rf3 = _alt(tempfile.mkdtemp(dir=tmp))
        os.remove(rf3)
        zeile3 = next((z for z in Model.load(pfad3)._ladehinweise if "Reibung" in z), "")
        check("RFEM-Datei nicht mehr da: die Protokollzeile sagt es und nennt den Pfad der Maske",
              "liegt nicht mehr unter" in zeile3 and "Maske „Lager aus RFEM“" in zeile3, zeile3[-300:])
        # fehlt die RFEM-Datei, sagt es das Nachlesen und aendert nichts
        pfad2, _ = _alt(tempfile.mkdtemp(dir=tmp))
        alt2 = Model.load(pfad2)
        try:
            R6.lager_aus_rfem(alt2, pfad=os.path.join(tmp, "fehlt.rf6"))
            check("fehlende RFEM-Datei: Fehler mit Grund", False, "kein Fehler")
        except FileNotFoundError as ex:
            check("fehlende RFEM-Datei: Fehler mit Grund, nichts umgestellt",
                  "fehlt.rf6" in str(ex) and _mu(alt2, "Starr").mu == 0.1, str(ex)[:100])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ohne_rfem_kein_hinweis():
    print("\n--- Ein Modell, das nicht aus RFEM 6 kommt, bekommt keinen Hinweis ---")
    tmp = tempfile.mkdtemp()
    try:
        m = Model("eigen")
        a = m.add_node(0, 0, 0)
        m.support(a, [0, 1, 2], name="Gleitlager")
        m.supports[0].set_behaviour(0, typ="rigid", mu=0.2, mu_ref=2)
        pfad = os.path.join(tmp, "eigen.json")
        m.save(pfad)
        neu = Model.load(pfad)
        check("kein Hinweis zur Lagerreibung", not any(x.get("art") == "lagerreibung" for x in neu.importhinweise))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _aktion(w):
    from PySide6 import QtGui
    return next((a for a in w.findChildren(QtGui.QAction) if a.text() == AKTION), None)


def test_oberflaeche():
    print("\n--- Oberflaeche: Hinweis beim Oeffnen, Datei › Austausch › „Aus RFEM nachlesen ▾“ › „Lager aus RFEM nachlesen…“ ---")
    w, app = _fenster()
    tmp = tempfile.mkdtemp()
    try:
        pfad, rf6 = _alt(tmp)
        w.modell_laden(pfad, fragen=False); app.processEvents()
        status = w.statusBar().currentMessage()
        check("beim Oeffnen: die Statuszeile nennt den Weg", AKTION.rstrip("…") in status, status[:160])
        check("von selbst wird nichts umgestellt", _mu(w.model, "Starr").mu == 0.1)
        a = _aktion(w)
        if not check(f"Register Datei › Austausch: „{AKTION}“", a is not None):
            return
        a.trigger(); app.processEvents()
        mk = w.maskenrand.maske
        check("die Aktion oeffnet rechts die Maske „Lager aus RFEM“",
              mk is not None and getattr(mk, "titel", "") == "Lager aus RFEM", getattr(mk, "titel", "-"))
        if mk is None:
            return
        werte = mk.werte()
        check("... mit dem Hinweis aus dem Import und der RFEM-Datei",
              "Reibung" in str(werte.get("hinweise", "")) and str(werte.get("pfad", "")) == rf6,
              f"{str(werte.get('hinweise', ''))[:80]} | {werte.get('pfad')}")
        n_meld = len(w.meldungen.alle)
        n_log = len(w.log.toPlainText().splitlines())
        mk.anwenden(); app.processEvents()
        neu = w.log.toPlainText().splitlines()[n_log:]
        check("„Lager nachlesen“: „Starr“ in ux/uy frei, „Gleit“ behaelt die Reibung",
              _mu(w.model, "Starr").typ == "free" and abs(_mu(w.model, "Gleit").mu - 0.1) < 1e-6,
              f"{_mu(w.model, 'Starr').describe()} | {_mu(w.model, 'Gleit').describe()}")
        check("... ohne Fehler und Hinweis, das Protokoll nennt das Ergebnis",
              len(w.meldungen.alle) == n_meld and any("nachgelesen" in z for z in neu), str(neu[-2:])[:200])
        w.undo(); app.processEvents()
        check("Rueckgaengig nimmt das Nachlesen zurueck", _mu(w.model, "Starr").mu == 0.1,
              _mu(w.model, "Starr").describe())
        # fehlende Datei: ein Hinweis, nichts umgestellt
        a.trigger(); app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("pfad", os.path.join(tmp, "gibt_es_nicht.rf6"))
        n_f = len(w.meldungen.fehler)
        mk.anwenden(); app.processEvents()
        check("fehlende RFEM-Datei: ein Hinweis mit der Datei, kein Fehlerfenster, nichts umgestellt",
              w.meldungen.hinweis_mit("gibt_es_nicht.rf6") and len(w.meldungen.fehler) == n_f
              and _mu(w.model, "Starr").mu == 0.1, str(w.meldungen.hinweise[-1:])[:160])
        mk.abbrechen(); app.processEvents()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_drehlager():
    rf6 = os.environ.get("STATIK3D_DREHLAGER_RF6") or os.path.join(
        os.path.expanduser("~"), "Desktop", "Statik3D", "RFEM_Modelle", "Lindaunis", "Drehlager_V15_4_export.rf6")
    if not os.path.exists(rf6):
        print(f"\n--- Drehlager: {rf6} nicht vorhanden, uebersprungen ---")
        return
    print(f"\n--- Drehlager {os.path.basename(rf6)}: Import (nur lesend) ---")
    log = []
    m = R6.read_rf6(rf6, log=log)
    ss = [s for s in m.surface_supports if s.name == "Starr"]
    if not check("Drehlager: Flaechenlager „Starr“ vorhanden", len(ss) == 1, str(len(ss))):
        return
    b = [ss[0].dof_behaviour(d) for d in range(3)]
    check("Drehlager: „Starr“ in der Flaeche frei, ohne Reibung",
          b[0].typ == b[1].typ == "free" and b[0].mu == b[1].mu == 0.0, f"{b[0].describe()} | {b[1].describe()}")
    check("Drehlager: „Starr“ senkrecht starr mit Ausfall bei Zug", b[2].typ == "rigid" and b[2].failure == "zug",
          b[2].describe())
    zeilen = [z.strip() for z in log if SATZ in z]
    for z in zeilen:
        print(f"     {z}")
    check("Drehlager: genau ein Satz zum nicht angesetzten Beiwert, mit „Starr“",
          len(zeilen) == 1 and "Starr" in zeilen[0], str(len(zeilen)))
    mit_mu = [(s.name, d) for s in m.surface_supports for d in range(3) if s.dof_behaviour(d).mu]
    mit_mu += [(s.name, d) for s in m.supports + m.line_supports for d in range(6) if s.dof_behaviour(d).mu]
    check("Drehlager: kein Lager traegt Reibung", not mit_mu, str(mit_mu[:6]))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_flaechenlager, test_knoten_linienlager, test_gespeichertes_modell,
              test_ohne_rfem_kein_hinweis, test_oberflaeche, test_drehlager):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
