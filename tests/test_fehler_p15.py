"""
Fehlerliste P15 (06.10.2026): Meldungen und Anzeigen - F35, F36, F37, F38,
F39, F45 und F46.

* F35: Scheitert die Messung der Randtreue, war sie bisher 0,0 % - die
  Netzabnahme vor dem Rechnen meldete trotzdem „bestanden“, und netzguete
  wertete die 0,0 als Messwert und vernetzte zweimal vergeblich feiner.
* F36: Bei „Nur aktiver Lastfall“ und ``--analyse lastfall`` fehlte der
  Hinweis, dass die Knotendilatation bei nu ausserhalb [0; 0,5) nicht greift.
* F37: Wich PARDISO fuer ein Ergebnis auf SuperLU aus, nannte der Bericht
  unter den Berechnungsgrundlagen trotzdem „Gleichungslöser: pardiso“.
* F38: Zu einer Eigen- oder Knickform standen unter „|u|“ Zahlen, die zu
  keiner gezeigten Form gehoeren (Eigenform 0, Knickform der statische Wert).
* F39: Zusammenfassung, Bericht und Rechenliste meldeten „nicht konvergiert“,
  wenn nur der elastische Vorlauf gedeckelt war und der letzte Lauf
  konvergiert ist.
* F45: Das Ebenen-Werkzeug der freien Schnittebene folgte dem Schieber im
  Ribbon nicht.
* F46: Der Zwischenspeicher „Knoten -> Bauteile“ der Netzabnahme galt,
  solange die Elementzahl gleich blieb.

    python -m tests.test_fehler_p15
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_p15_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}


def check(name, ok, info=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:<78s} {info}")
    return bool(ok)


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


def _wirft(*_a, **_k):
    raise MemoryError("Probe F35")


# ---------------------------------------------------------------------------
# F35
# ---------------------------------------------------------------------------
def test_f35_randtreue_nicht_gemessen():
    from statik3d import diagnose as dg
    from statik3d import mesher
    from statik3d import mesher3d as M3
    from statik3d import vernetzer_extern as vx
    from statik3d.model import Material, Model
    from tests.test_diagnose import _extrudiert

    # (a) netzguete: „nicht gemessen“ ist kein Messwert unter der Grenze
    Pn = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1.]])
    TET = np.array([[0, 1, 2, 3]])
    T = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]])
    echt = M3.randtreue
    M3.randtreue = _wirft
    try:
        tb = M3._netzbericht(Pn, TET, Pn, T)
    finally:
        M3.randtreue = echt
    mass = M3.netzguete(tb, {"volumen": tb["volumen"]})
    check("F35 netzguete: nicht gemessene Randtreue zählt nicht als gerissen",
          bool(tb.get("randtreue_fehler")) and not any("Randtreue" in g for g in mass["gerissen"]),
          f"Fehler {tb.get('randtreue_fehler')!r}, gerissen {mass['gerissen']}")

    # (b) die Abnahme vor dem Rechnen nennt die ungepruefte Randtreue
    L = [(0, 0), (2, 0), (2, 0.5), (0.5, 0.5), (0.5, 2), (0, 2)]
    m = Model("L")
    m.add_material(Material.steel("S235"))
    k = _extrudiert(m, L, 0.0, 0.4)
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1, hs={"K": 0.25})
    check("Aufbau: der Körper ist vernetzt", len(k.elemente) > 0, f"{len(k.elemente)} Elemente")
    k.randtreue = 0.0
    k.randtreue_fehler = "MemoryError: Probe F35"
    bef = [b for b in dg.abnahme(m, warnungen=True) if "Randtreue" in b.pruefung]
    check("F35 Abnahme: WARNUNG „Randtreue nicht geprüft“ mit dem Grund",
          len(bef) == 1 and bef[0].pruefung == "Randtreue nicht geprüft"
          and bef[0].stufe == "WARNUNG" and "MemoryError" in bef[0].text,
          str([(b.pruefung, b.stufe, b.text[:90]) for b in bef]) or "kein Befund")
    k.randtreue_fehler = ""
    bef = [b for b in dg.abnahme(m, warnungen=True) if "Randtreue" in b.pruefung]
    check("F35 Gegenprobe: 0 ohne gescheiterte Messung (etwa ein Import) bleibt ohne Befund",
          not bef, str([b.pruefung for b in bef]))
    k.randtreue_fehler = "MemoryError: Probe F35"
    m2 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("F35 der Grund übersteht Speichern und Laden",
          getattr(m2.koerper["K"], "randtreue_fehler", None) == "MemoryError: Probe F35",
          repr(getattr(m2.koerper["K"], "randtreue_fehler", None)))

    # (c) der echte Weg: fremder Vernetzer, randtreue() wirft
    if not vx.gmsh_verfuegbar():
        print("  (gmsh nicht installiert - der echte Weg bleibt ungeprüft)")
        return
    m = Model("L")
    m.add_material(Material.steel("S235"))
    k = _extrudiert(m, L, 0.0, 0.4)
    m.netz.sweep = False
    m.netz.vernetzer = "gmsh"
    log = []
    M3.randtreue = _wirft
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mesher.modell_vernetzen(m, log, workers=1, hs={"K": 0.25})
    finally:
        M3.randtreue = echt
    nach = [z for z in log if "nachvernetzt" in z]
    check("F35 gmsh: kein vergebliches Nachvernetzen wegen der nicht gemessenen Randtreue",
          not nach and len(k.elemente) > 0, (nach[0] if nach else f"{len(k.elemente)} Elemente")[:120])
    check("F35 gmsh: der Körper trägt den Grund",
          "MemoryError" in str(getattr(k, "randtreue_fehler", "")),
          repr(getattr(k, "randtreue_fehler", None)))
    bef = [b for b in dg.abnahme(m, warnungen=True) if "Randtreue" in b.pruefung]
    check("F35 gmsh: die Abnahme meldet nicht „bestanden“, sondern „Randtreue nicht geprüft“",
          [b.pruefung for b in bef] == ["Randtreue nicht geprüft"],
          str([(b.pruefung, b.stufe) for b in bef]) or "bestanden (keine Befunde)")


# ---------------------------------------------------------------------------
# F36
# ---------------------------------------------------------------------------
def test_f36_dilatation_nur_lastfall():
    from statik3d import cli, solver
    from tests.test_dilatation import _kragtraeger
    m, _w = _kragtraeger(-0.1, h=0.2)
    m.knotendilatation = True
    r = solver.solve_static(m)
    z = [x for x in r.summary().splitlines() if x.startswith("Knotendilatation:")]
    check("F36 Nur aktiver Lastfall: die Zusammenfassung des Ergebnisses nennt den Hinweis",
          len(z) == 1 and "Querdehnzahl -0.1" in z[0], z[0][:90] if z else "fehlt")
    d = tempfile.mkdtemp(prefix="p15_f36_")
    p = os.path.join(d, "krag.json")
    m.save(p)
    puffer = io.StringIO()
    with contextlib.redirect_stdout(puffer):
        rc = cli.main([p, "--analyse", "lastfall", "--still"])
    aus = puffer.getvalue()
    check("F36 --analyse lastfall: die Kommandozeile nennt ihn",
          rc == 0 and "Knotendilatation:" in aus,
          f"rc {rc}, " + next((x for x in aus.splitlines() if "Knotendilatation" in x), "fehlt")[:80])
    an = solver.solve_all(m)
    check("F36 Gegenprobe: alle Lastfälle - in der Gesamtzusammenfassung genau einmal",
          an.summary().count("Knotendilatation:") == 1, str(an.summary().count("Knotendilatation:")))


# ---------------------------------------------------------------------------
# F37
# ---------------------------------------------------------------------------
def _gleichungsloeser_zeile(html: str) -> str:
    z = re.findall(r"<li>(Gleichungslöser: .*?)</li>", html, re.S)
    return re.sub(r"<[^>]+>", "", z[0]) if z else ""


def test_f37_rechenverfahren_nennt_ausweichen():
    import pypardiso
    from statik3d import parallel, solver
    from statik3d.report.html import Report
    from tests.test_situationen import _balken_mit_rolle
    m, _ids, _sec = _balken_mit_rolle()
    an0 = solver.solve_all(m, workers=1, design=False)
    z0 = _gleichungsloeser_zeile(Report(m, an0).html())
    check("F37 Gegenprobe: ohne Ausweichen steht nur der Löser da",
          z0.startswith("Gleichungslöser: ") and "ausgewichen" not in z0, z0[:120])
    alt_backend = parallel.settings().solver_backend
    parallel.configure(solver_backend="auto")
    echt = pypardiso.PyPardisoSolver.factorize
    n = {"n": 0}

    def erst_echt(self, A):
        n["n"] += 1
        if n["n"] == 1:
            return echt(self, A)
        raise RuntimeError("Probe F37: PARDISO verweigert (Teilausfall)")

    m, _ids, _sec = _balken_mit_rolle()
    pypardiso.PyPardisoSolver.factorize = erst_echt
    try:
        an = solver.solve_all(m, workers=1, design=False)
    finally:
        pypardiso.PyPardisoSolver.factorize = echt
        parallel.configure(solver_backend=alt_backend)
    ausgewichen = [k for k, r in an.all_results().items() if solver.ausweich_paare(r.info or {})]
    check("Aufbau: Teilausfall - an.info['solver'] ist pardiso, ein Ergebnis wich aus",
          an.info.get("solver") == "pardiso" and ausgewichen,
          f"{an.info.get('solver')}, ausgewichen {ausgewichen}")
    z = _gleichungsloeser_zeile(Report(m, an).html())
    check("F37 Berechnungsgrundlagen: „Gleichungslöser: pardiso … ausgewichen auf SuperLU“",
          z.startswith("Gleichungslöser: pardiso") and "ausgewichen auf SuperLU" in z, z[:160])


# ---------------------------------------------------------------------------
# F38
# ---------------------------------------------------------------------------
def test_f38_kennwerte_bei_formen():
    from statik3d import examples_lib, solver
    from statik3d.gui import viewport as vp
    m = examples_lib.build_example("frame")
    st = solver.solve_static(m)
    u_st = float(np.max(np.linalg.norm(st.u[:, :3], axis=1))) * 1e3
    z = [x for x in vp.kennwerte(m, st, feld="|u| Verschiebung") if x.startswith("u ")]
    check("F38 Gegenprobe: zum Lastfall steht |u| mit Zahl und Knoten",
          len(z) == 1 and "Knoten" in z[0] and "normiert" not in z[0], z[0] if z else "keine Zeile")
    for art, r in (("Eigenform", solver.solve_modal(m, 3)), ("Knickform", solver.solve_buckling(m, 3))):
        for feld in ("|u| Verschiebung", "ux", "uz", None):
            zz = vp.kennwerte(m, r, feld=feld)
            u_z = [x for x in zz if x.split() and x.split()[0] in ("u", "ux", "uy", "uz")]
            phi = [x for x in zz if x.startswith("phi")]
            check(f"F38 {art}, Färbung {feld or 'alles'}: „normierte Form“ statt einer Zahl",
                  u_z and all("normierte Form" in x and "Knoten" not in x for x in u_z) and not phi,
                  str(u_z + phi)[:110])
        zz = " ".join(vp.kennwerte(m, r, feld="|u| Verschiebung"))
        check(f"F38 {art}: der statische Größtwert {u_st:.2f} mm steht nicht da",
              f"{u_st:.2f}" not in zz, zz[:110])


# ---------------------------------------------------------------------------
# F39
# ---------------------------------------------------------------------------
def _fliessender_block():
    from statik3d import plastizitaet as pl
    from statik3d import solver
    from statik3d.examples_lib import block_friction_example
    m0 = block_friction_example()
    r0 = solver.solve_static(m0)
    q0 = max(pl.vergleichsspannung(np.asarray(v, float)) for i, v in r0.solid_res.items()
             if m0.elements[i].mat == "S235")
    m = block_friction_example()
    m.materials["S235"].fy = 0.6 * q0
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.05, laststufen=2,
                                     iterationen=40, toleranz=1e-4, kontakt="verschachtelt")
    return m


def _rechnen(m, nur_vorlauf: bool):
    """solve_all mit Deckel 1 der Reibungsnachpruefung - nur im elastischen
    Vorlauf (wie tests.test_rechenliste.test_vorlauf_mit_deckel) oder in
    jedem Lauf. Rueckgabe (Analyse, Meldungen)."""
    from statik3d import contact as _ct
    from statik3d import solver
    alt_max, alt_pr = _ct.MAX_CYCLES, solver._plastizitaet_rechnen

    def plastisch_ohne_deckel(*a, **k):
        _ct.MAX_CYCLES = alt_max
        return alt_pr(*a, **k)

    meldungen = []
    _ct.MAX_CYCLES = 1
    if nur_vorlauf:
        solver._plastizitaet_rechnen = plastisch_ohne_deckel
    try:
        an = solver.solve_all(m, progress=lambda t, *a: meldungen.append(t), workers=1, design=False)
    finally:
        _ct.MAX_CYCLES = alt_max
        solver._plastizitaet_rechnen = alt_pr
    return an, [t for t in meldungen if isinstance(t, str)]


def _rechenliste_nach_lauf(w, app, posten, meldungen, an) -> dict:
    """Die Rechenliste so fuettern, wie es eine Hintergrundrechnung tut
    (_rechenliste_oeffnen haengt sie an die Signale des Workers)."""
    from statik3d.gui.worker import SolveWorker
    w.worker = SolveWorker(lambda progress: None)
    try:
        w._rechenliste_oeffnen(posten)
        f = w.rechenliste
        for t in meldungen:
            w.worker.progress.emit(t)
        w.worker.finished_ok.emit(an)
        app.processEvents()
        S = type(f)
        aus = {f.tabelle.item(i, 0).text(): (f.tabelle.item(i, S.S_ZUSTAND).text(),
                                            f.tabelle.item(i, S.S_MELDUNG).text())
               for i in range(f.tabelle.rowCount())}
        f.close()
        return aus
    finally:
        w.worker = None


def test_f39_nur_vorlauf_gedeckelt():
    from statik3d.gui.rechenliste import posten_aus_modell, zustand_aus_info
    from statik3d.report.html import Report
    m = _fliessender_block()
    an, meldungen = _rechnen(m, nur_vorlauf=True)
    r = an.cases["LF1"]
    check("Aufbau: allein der Vorlauf gedeckelt, der letzte Lauf konvergiert",
          r.info.get("contact_vorlauf_nicht_konvergiert") == 1
          and r.info.get("contact_converged") is False
          and zustand_aus_info(r.info) == "konvergiert",
          f"Vorlauf {r.info.get('contact_vorlauf_nicht_konvergiert')}, "
          f"contact_converged {r.info.get('contact_converged')}, {zustand_aus_info(r.info)}")
    zeile = next((x for x in r.summary().splitlines() if x.startswith("Kontakt-Iterationen")), "")
    check("F39 Zusammenfassung: nicht „NICHT konvergiert“",
          zeile and "NICHT konvergiert" not in zeile, zeile)
    check("F39 … der gedeckelte Vorlauf darf als Hinweis stehen", "Vorlauf" in zeile, zeile)
    rep = Report(m, an)
    html = rep.html()
    warn = "\n".join(getattr(rep, "_warnings", []) or [])
    text = re.sub(r"<[^>]+>", " ", html)
    check("F39 Bericht: keine Zeile „nicht konvergiert“ zu LF1",
          "NICHT konvergiert" not in text and "(nicht konvergiert)" not in text
          and "Iteration nicht konvergiert" not in warn,
          next((x.strip()[:100] for x in text.split("  ") if "nicht konvergiert" in x.lower()), "")
          or next((x[:100] for x in warn.splitlines() if "Iteration nicht" in x), ""))
    w, app = _fenster()
    zust = _rechenliste_nach_lauf(w, app, posten_aus_modell(m, "all"), meldungen, an)
    check("F39 Rechenliste: LF1 steht auf „konvergiert“, nicht auf „nicht konvergiert“",
          zust.get("LF1", ("", ""))[0] == "konvergiert", str(zust))
    check("F39 … mit dem Vorlauf als Hinweis in der Meldung",
          "Vorlauf" in zust.get("LF1", ("", ""))[1], str(zust))


def test_f39_gegenprobe_wirklich_gedeckelt():
    from statik3d.gui.rechenliste import posten_aus_modell, zustand_aus_info
    from statik3d.report.html import Report
    from statik3d.examples_lib import block_friction_example
    m = block_friction_example()
    an, meldungen = _rechnen(m, nur_vorlauf=False)
    r = an.cases["LF1"]
    check("Aufbau: ohne Fließen und mit Deckel - der einzige Lauf ist gedeckelt",
          zustand_aus_info(r.info).startswith("NICHT konvergiert"), zustand_aus_info(r.info))
    zeile = next((x for x in r.summary().splitlines() if x.startswith("Kontakt-Iterationen")), "")
    check("F39 Gegenprobe Zusammenfassung: „NICHT konvergiert“ bleibt", "NICHT konvergiert" in zeile,
          zeile)
    rep = Report(m, an)
    html = rep.html()
    warn = "\n".join(getattr(rep, "_warnings", []) or [])
    check("F39 Gegenprobe Bericht: Tabelle und Warnung nennen es",
          "(nicht konvergiert)" in html and "Iteration nicht konvergiert" in warn,
          f"Tabelle {'(nicht konvergiert)' in html}, Warnung {'Iteration nicht konvergiert' in warn}")
    w, app = _fenster()
    zust = _rechenliste_nach_lauf(w, app, posten_aus_modell(m, "all"), meldungen, an)
    check("F39 Gegenprobe Rechenliste: „nicht konvergiert“ bleibt",
          zust.get("LF1", ("", ""))[0] == "nicht konvergiert", str(zust))


# ---------------------------------------------------------------------------
# F45
# ---------------------------------------------------------------------------
def test_f45_werkzeug_folgt_dem_schieber():
    w, app = _fenster()
    w.load_example("frame")
    app.processEvents()
    X = np.asarray(w.model.nodes, float).reshape(-1, 3)
    lo, hi = X.min(axis=0), X.max(axis=0)
    mitte = 0.5 * (lo + hi)
    ecken = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    for normale in ((1.0, 0.0, 0.0), (1.0, 0.0, 1.0)):
        n = np.asarray(normale, float) / np.linalg.norm(normale)
        w.schnitt_frei = {"normale": tuple(n), "ursprung": tuple(mitte)}
        w.cb_schnittachse.setCurrentText("y")
        app.processEvents()
        w.cb_schnittachse.setCurrentText("frei")
        app.processEvents()
        mk = w.maskenrand.maske
        if mk is None or getattr(mk, "titel", "") != "Schnittebene":
            check("Aufbau: Maske „Schnittebene“", False, str(getattr(mk, "titel", None)))
            return
        mk.setzen("widget", True)
        mk.anwenden()
        app.processEvents()
        wz = getattr(w, "_schnittwidget", None)
        check(f"Aufbau n = {normale}: das Ebenen-Werkzeug steht (offscreen ohne Bild)",
              wz is not None and w.schnitt is not None and w.schnitt[0] == "frei", str(w.schnitt))
        if wz is None:
            return
        # Normale und Ursprung, wie die Maske sie uebernommen hat (sie
        # schreibt die Zahlen mit sechs Stellen)
        n = np.asarray(w.schnitt[3], float)
        o0 = np.asarray(w.schnitt[4], float)
        s = ecken @ n
        for wert in (80, 20, 50):
            w.sl_schnitt.setValue(wert)
            app.processEvents()
            soll = o0 + (wert / 100.0 - 0.5) * float(s.max() - s.min()) * n
            o = np.asarray(wz.GetOrigin(), float)
            nw = np.asarray(wz.GetNormal(), float)
            abst = abs(float((o - soll) @ n))
            check(f"F45 n = {normale}, Schieber {wert}: das Werkzeug liegt in der Schnittebene",
                  w.schnitt[1] == wert / 100.0 and abst < 1e-9 * max(1.0, float(np.abs(hi - lo).max()))
                  and np.allclose(nw, n, atol=1e-9),
                  f"Abstand {abst:.4g} m, Ursprung {np.round(o, 4)}, Soll {np.round(soll, 4)}")
        w._schnittwidget_entfernen()
        w.maskenrand.schliessen()
        app.processEvents()
    w.act_schnitt.setChecked(False)
    w.cb_schnittachse.setCurrentText("y")
    app.processEvents()


# ---------------------------------------------------------------------------
# F46
# ---------------------------------------------------------------------------
def test_f46_knotenkarte_nach_umhaengen():
    from statik3d import diagnose as dg
    from statik3d.model import Material, Model
    m = Model("F46")
    m.add_material(Material.steel("S235"))
    p = [m.add_node(x, y, z) for x, y, z in
         ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (2, 0, 0), (3, 0, 0), (2, 1, 0), (2, 0, 1))]
    e0 = m.add_element("tet4", p[0:4], "S235", group="A")
    e1 = m.add_element("tet4", p[4:8], "S235", group="B")
    check("Aufbau: Knoten 0 gehört zu A", dg._koerper_des_knotens(m, p[0]) == {"A"},
          str(dg._koerper_des_knotens(m, p[0])))
    # Eine Fuge haengt Element e1 an Knoten 0 um - die Elementzahl bleibt
    m.elements[e1].nodes = [p[0], p[5], p[6], p[7]]
    check("F46 umgehängtes Element: Knoten 0 gehört jetzt zu A und B",
          dg._koerper_des_knotens(m, p[0]) == {"A", "B"}, str(dg._koerper_des_knotens(m, p[0])))
    check("F46 … und Knoten 4 zu keinem mehr", dg._koerper_des_knotens(m, p[4]) == set(),
          str(dg._koerper_des_knotens(m, p[4])))
    m.elements[e0].group = "C"
    check("F46 neue Gruppe bei gleichen Knoten: Knoten 1 gehört zu C",
          dg._koerper_des_knotens(m, p[1]) == {"C"}, str(dg._koerper_des_knotens(m, p[1])))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1500, exit=True)
    for t in (test_f35_randtreue_nicht_gemessen, test_f36_dilatation_nur_lastfall,
              test_f37_rechenverfahren_nennt_ausweichen, test_f38_kennwerte_bei_formen,
              test_f39_nur_vorlauf_gedeckelt, test_f39_gegenprobe_wirklich_gedeckelt,
              test_f45_werkzeug_folgt_dem_schieber, test_f46_knotenkarte_nach_umhaengen):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    sys.stdout.flush()
    return 0 if not failed else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
