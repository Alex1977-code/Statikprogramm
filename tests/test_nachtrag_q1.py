"""
Paket Q1 des Nachtrags zur Fehlerliste (07.10.2026): ein Ergebnis gilt nur zum
Modell, mit dem es gerechnet wurde.

* N38: Die Kennung der Ergebnisdatei prüfte bis zum 07.10.2026 nur Knoten,
  Elemente (Typ und Knoten) und die Namen der Lastfälle - weder Lasten noch
  Werkstoffe noch Lager. Beleg (p6_werkzeug/probe_last_export.py): g_z
  verdoppelt, Modell als .json exportiert (die Ergebnisdatei bleibt), Öffnen
  - „passt“, gezeigt uz −15,2543 statt −15,6466 mm. Jetzt trägt die Kennung
  je Gruppe der Rechenangaben einen Hash (ergebnisse.rechenkennung), der
  Anzeige, Kommentare und Layer nicht enthält und nach Speichern und Laden
  derselbe ist; die Meldung beim Öffnen nennt die geänderten Gruppen.
* N39: _ergebnis_neu_vermerken vermerkte auch ein Ergebnis als ungespeichert,
  das als „anders“ gilt und darum gar nicht gespeichert wird; die Rückfrage
  vor dem Beenden nannte es trotzdem.
* N40: Änderungen aus dem Browser wurden während einer Rechnung am Desktop
  nicht abgewiesen.

Aufruf:  python -m tests.test_nachtrag_q1
"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_q1_"), "einstellungen.json")

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
    # keine Rueckfragen (Abnahme des Netzes, Knoepfe) und keine Meldungsfenster
    w._fragen_knoepfe = lambda *a, **k: True
    w._fragen = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _warten(app, fertig, dauer=120.0):
    t0 = time.time()
    while not fertig() and time.time() - t0 < dauer:
        app.processEvents()
        time.sleep(0.02)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.005)


class _Langsam:
    """solve_all rechnet und haelt dann an, bis ``weiter`` gesetzt ist: so
    laeuft die Hintergrundrechnung noch, waehrend die Pruefung bedient (wie
    in tests.test_fehler_p6)."""

    def __enter__(self):
        import statik3d.solver as slv
        self.slv, self.orig = slv, slv.solve_all
        self.gerechnet, self.weiter = threading.Event(), threading.Event()

        def langsam(*a, **k):
            r = self.orig(*a, **k)
            self.gerechnet.set()
            self.weiter.wait(60)
            return r
        slv.solve_all = langsam
        return self

    def __exit__(self, *_a):
        self.slv.solve_all = self.orig
        self.weiter.set()
        return False


def _rechnung_starten(w, app, l):
    w.cb_analysis.setCurrentIndex(0)                  # alle Lastfaelle + Kombinationen
    w.do_solve("all")
    _warten(app, l.gerechnet.is_set)
    return w._rechnet()


def _rechnung_beenden(w, app, l):
    l.weiter.set()
    _warten(app, lambda: not w._rechnet())


def _leeren(w):
    w._leiste_weg()
    if w.maskenrand.maske is not None:
        w._maske_verwerfen(w.maskenrand.maske)


# ---------------------------------------------------------------------------
# Ein Modell mit allem, woran die Kennung haengt
# ---------------------------------------------------------------------------
def _basis():
    """Die Halle (Lastfaelle, Kombinationen, Staebe mit Nachweis) und dazu ein
    unvernetzter Quader aus Linien, Flaechen und einem Volumen, Linien- und
    Flaechenlager, ein Gelenk, eine Kopplung, ein Kontaktlager, eine Masse,
    eine Situation, eine Linienlast eines Lastgenerierers, ein Layer und ein
    Berichtseintrag."""
    from statik3d.examples_lib import build_example
    from statik3d.model import ContactSupport, Kopplung, Berichtseintrag, Layer, Situation
    m = build_example("hall")
    mat = next(iter(m.materials))
    k = [m.add_node(100.0 + x, y, z) for z in (0.0, 1.0) for (x, y) in ((0, 0), (1, 0), (1, 1), (0, 1))]
    linien = {"B1": (0, 1), "B2": (1, 2), "B3": (2, 3), "B4": (3, 0),
              "T1": (4, 5), "T2": (5, 6), "T3": (6, 7), "T4": (7, 4),
              "S1": (0, 4), "S2": (1, 5), "S3": (2, 6), "S4": (3, 7)}
    for n, (a, b) in linien.items():
        m.add_line(n, [k[a], k[b]])
    m.lines["B1"].comment = "Unterkante vorn"
    for n, rand in (("unten", ["B1", "B2", "B3", "B4"]), ("oben", ["T1", "T2", "T3", "T4"]),
                    ("vorn", ["B1", "S2", "T1", "S1"]), ("rechts", ["B2", "S3", "T2", "S2"]),
                    ("hinten", ["B3", "S4", "T3", "S3"]), ("links", ["B4", "S1", "T4", "S4"])):
        m.add_flaeche(n, rand, material=mat, dicke=0.01, kommentar="Quaderseite")
    m.add_koerper("Q1", ["unten", "oben", "vorn", "rechts", "hinten", "links"], material=mat,
                  kommentar="Probekoerper")
    m.add_line_support([k[0], k[1]], name="LL1", uz=dict(typ="rigid"))
    fl = m.add_surface_support(name="FL1", uz=dict(typ="spring", stiffness=1e7))
    fl.flaechen = ["unten"]
    m.add_hinge("G1", end=1, phiy="free")
    m.kopplungen.append(Kopplung(k[2], k[3], [[1.0, 0.0, 0.0]], [1e8]))
    m.contact_supports.append(ContactSupport(node=k[4], direction=[0.0, 0.0, 1.0]))
    m.add_punktmasse(k[5], 120.0, name="M1", kommentar="Antrieb")
    m.situationen["Bau"] = Situation("Bau", "", [0], "Bauzustand")
    ll = m.add_linienlast("B1", [0.0, 0.0, -1000.0], art="linie", case="W_links")
    ll.erzeuger, ll.kommentar = "Wind W1", "Wind W1: Sog"
    m.layer["Quader"] = Layer("Quader", knoten=list(k))
    m.bericht.append(Berichtseintrag(name="Bild 1", quelle="case:LF1", beschriftung="Verformung"))
    m.supports[0].name = "Fuß links"
    return m


def _mit_stellung(m):
    """Eine Stellung, die das Lager „Fuß links“ abschaltet: dann rechnet der
    Name des Lagers mit (MainWindow._lagernamen_rechnen)."""
    from statik3d.bridges.positions import Stellung
    m.stellungen.append(Stellung("offen", lager_aus=["Fuß links"], faelle=list(m.load_cases)))
    return m


def _rechenaenderungen():
    """(Gruppe in der Meldung, was, Aenderung am Modell) - jede aendert die
    Rechnung."""
    def lc(m, n):
        return m.load_cases[n]

    def erstes(d):
        return d[next(iter(d))]
    return [
        ("Lasten (LF1)", "Eigengewicht g_z verdoppelt",
         lambda m: lc(m, "LF1").gravity.__setitem__(2, 2 * lc(m, "LF1").gravity[2])),
        ("Lasten (S)", "eine Stablast von S um 10 % größer",
         lambda m: setattr(lc(m, "S").beam_loads[0], "q", [1.1 * x for x in lc(m, "S").beam_loads[0].q])),
        ("Lasten (W_links)", "Linienlast des Lastgenerierers (Wind W1) geändert",
         lambda m: setattr(lc(m, "W_links").linienlasten[-1], "q", [0.0, 0.0, -1500.0])),
        ("Lastfalleigenschaften (LF1)", "LF1 nach Theorie II. Ordnung",
         lambda m: setattr(lc(m, "LF1"), "theorie", "II")),
        ("Kombinationen", "ein Faktor einer Kombination",
         lambda m: erstes(m.combinations).factors.__setitem__(
             next(iter(erstes(m.combinations).factors)),
             1.5 * erstes(m.combinations).factors[next(iter(erstes(m.combinations).factors))])),
        ("Werkstoffe", "E-Modul um 1 % größer",
         lambda m: setattr(erstes(m.materials), "E", 1.01 * erstes(m.materials).E)),
        ("Querschnitte", "Fläche A eines Querschnitts um 1 % größer",
         lambda m: setattr(erstes(m.sections), "A", 1.01 * erstes(m.sections).A)),
        ("Elementeigenschaften", "Stab 0 um 0,1 rad gedreht",
         lambda m: setattr(m.elements[0], "roll", 0.1)),
        ("Elementeigenschaften", "Stab 0 mit Momentengelenk",
         lambda m: setattr(m.elements[0], "hinges", [4])),
        ("Lager", "Knotenlager 0 in einer Richtung frei",
         lambda m: setattr(m.supports[0], "dofs", list(m.supports[0].dofs)[1:])),
        ("Lager", "Flächenlager weicher",
         lambda m: m.surface_supports[0].behaviour[2].__setattr__("stiffness", 5e6)),
        ("Gelenke", "Gelenk G1: φy Feder statt frei",
         lambda m: m.hinges["G1"].typ.__setitem__(4, "spring")),
        ("Gelenke", "Kopplung steifer",
         lambda m: setattr(m.kopplungen[0], "steifigkeiten", [2e8])),
        ("Kontakt", "Kontaktlager mit Reibung",
         lambda m: setattr(m.contact_supports[0], "mu", 0.3)),
        ("Massen", "Punktmasse schwerer",
         lambda m: setattr(m.punktmassen[0], "masse", 240.0)),
        ("Stellungen", "Situation schaltet ein weiteres Element ab",
         lambda m: m.situationen["Bau"].deaktiviert.append(1)),
        ("Rechenart", "Plastizität eingeschaltet",
         lambda m: setattr(m.plastizitaet, "an", True)),
        ("Rechenart", "Bemessung nach Theorie II. Ordnung",
         lambda m: setattr(m.design, "theorie2", not m.design.theorie2)),
        ("Nachweise", "Knicklängenbeiwert eines Stabes verdoppelt",
         lambda m: setattr(erstes(m.members), "beta_y", 2 * erstes(m.members).beta_y)),
        ("Linien, Flächen und Volumen", "Flächendicke",
         lambda m: setattr(m.flaechen["unten"], "dicke", 0.02)),
    ]


def _anzeigeaenderungen():
    """(was, Aenderung) - nur Anzeige, Kommentar, Layer: die Rechnung bleibt."""
    from statik3d.model import Berichtseintrag, Layer
    return [
        ("Kommentar einer Linie", lambda m: setattr(m.lines["B1"], "comment", "anders")),
        ("Kommentar einer Fläche", lambda m: setattr(m.flaechen["unten"], "kommentar", "Boden")),
        ("Kommentar eines Volumens", lambda m: setattr(m.koerper["Q1"], "kommentar", "Block")),
        ("Beschreibung, Bezeichnung und Nummer eines Lastfalls",
         lambda m: (setattr(m.load_cases["S"], "description", "Schnee nach Zone 2"),
                    setattr(m.load_cases["S"], "bezeichnung", "Schnee"),
                    setattr(m.load_cases["S"], "nummer", 77))),
        ("Beschreibung, Bezeichnung und Nummer einer Kombination",
         lambda m: [setattr(c, a, v) for c in list(m.combinations.values())[:1]
                    for a, v in (("description", "neu"), ("bezeichnung", "GZT neu"), ("nummer", 99))]),
        ("Kommentar einer Linienlast (Verteilen überschreibt ihn)",
         lambda m: setattr(m.load_cases["W_links"].linienlasten[-1], "kommentar", "1 Elementlast")),
        ("Kommentar einer Punktmasse", lambda m: setattr(m.punktmassen[0], "kommentar", "Motor")),
        ("Beschreibung einer Situation", lambda m: setattr(m.situationen["Bau"], "beschreibung", "Montage")),
        ("Größe des Lagersymbols", lambda m: setattr(m.supports[0], "groesse", 2.5)),
        ("Name eines Knotenlagers (keine Stellung nennt Lager)",
         lambda m: setattr(m.supports[0], "name", "Fuß West")),
        ("Name eines Linienlagers", lambda m: setattr(m.line_supports[0], "name", "Rand")),
        ("ein weiterer Layer, Layer unsichtbar",
         lambda m: (m.layer.__setitem__("Neu", Layer("Neu", knoten=[0])),
                    setattr(m.layer["Quader"], "sichtbar", False))),
        ("ein weiterer Berichtseintrag", lambda m: m.bericht.append(Berichtseintrag(name="Bild 2"))),
        ("Einheiten der Ansicht", lambda m: setattr(m.einheiten, next(iter(vars(m.einheiten))),
                                                     _anders(getattr(m.einheiten, next(iter(vars(m.einheiten))))))),
        ("aktiver Lastfall", lambda m: setattr(m, "active_case", "S")),
        ("Projektangaben und Modellname",
         lambda m: (m.meta.__setitem__("projekt", "Probe"), setattr(m, "name", "Halle 2"))),
        ("Netzvorgabe (das Netz selbst bleibt)", lambda m: setattr(m.netz, "ziellaenge", 0.123)),
    ]


def _anders(x):
    if isinstance(x, bool):
        return not x
    if isinstance(x, (int, float)):
        return x + 1
    return str(x) + "x"


def test_n38_beleg():
    """Der Beleg: Lastfall LF1 mit doppeltem g_z als .json exportiert, die
    Ergebnisdatei bleibt daneben - Oeffnen laedt das alte Ergebnis nicht und
    sagt, dass die Lasten von LF1 anders sind."""
    from statik3d import ergebnisse as erg, solver
    from statik3d.exporters import export_model
    w, app = _fenster()
    me = w.meldungen
    w.load_example("frame"); app.processEvents()
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    d = tempfile.mkdtemp(prefix="q1_n38_")
    p = os.path.join(d, "rahmen.json")
    w.path = p
    w.save_model(); app.processEvents()
    m = w.model
    lf = m.active_case
    g0 = float(m.load_cases[lf].gravity[2])
    m.load_cases[lf].gravity[2] = 2 * g0
    export_model(m, p)
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    an = w.analysis
    detail = f"analysis {'da' if an is not None else 'None'}"
    if an is not None:
        frisch = solver.solve_all(w.model, design=False).cases[lf].u
        k = int(np.argmax(np.abs(frisch[:, 2])))
        detail += f", uz aus Datei {an.cases[lf].u[k, 2] * 1e3:.4f} mm, zum Modell {frisch[k, 2] * 1e3:.4f} mm"
    check("N38: g_z verdoppelt, als .json exportiert, geöffnet: altes Ergebnis nicht geladen",
          os.path.exists(erg.pfad_zu(p)) and an is None and w.current_result() is None, detail)
    check("… der Hinweis nennt die Gruppe und den Lastfall: „Lasten (LF1)“",
          me.hinweis_mit("Ergebnisdatei nicht geladen", f"Lasten ({lf})", "neu rechnen"), str(me.alle[-1:]))
    # Gegenprobe: dasselbe ohne Aenderung laedt das Ergebnis wieder
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    w.save_model(); app.processEvents()
    export_model(w.model, p)
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("… Gegenprobe: unverändert exportiert und geöffnet, das Ergebnis kommt ohne Vorbehalt",
          w.analysis is not None and w._analyse_passt() == "passt" and not me.hinweis_mit("Vorbehalt")
          and not me.hinweis_mit("nicht geladen"), str(me.alle[-1:]))


def test_n38_gruppen():
    """Jede Gruppe der Rechenangaben: eine Aenderung am Modell laesst die
    Kennung nicht mehr passen, und der Grund nennt die Gruppe."""
    from statik3d import ergebnisse as erg
    k0 = erg.kennung(_basis())
    for gruppe, was, aendern in _rechenaenderungen():
        m = _basis()
        aendern(m)
        ok, grund = erg.passt(k0, m)
        check(f"N38: {was} -> passt nicht, Grund nennt „{gruppe}“", not ok and gruppe in grund, grund)
    m = _mit_stellung(_basis())
    k1 = erg.kennung(m)
    m.supports[0].name = "Fuß West"
    ok, grund = erg.passt(k1, m)
    check("N38: Lagername, den eine Stellung nennt, umbenannt -> passt nicht (Lager)",
          not ok and "Lager" in grund, grund)


def test_n38_anzeige_zaehlt_nicht():
    """Anzeige, Kommentare und Layer aendern die Kennung nicht."""
    from statik3d import ergebnisse as erg
    k0 = erg.kennung(_basis())
    for was, aendern in _anzeigeaenderungen():
        m = _basis()
        aendern(m)
        ok, grund = erg.passt(k0, m)
        check(f"N38: nur Anzeige: {was} -> passt, ohne Vorbehalt", ok and grund == "", grund)


def test_n38_ungenutzte_eigenschaften():
    """Werkstoffe, Querschnitte und Dicken, die nichts nennt, rechnen nicht mit:
    das Oeffnen im Fenster legt einem Modell ohne Dicken die Vorgabe
    „t = 10 mm“ an (MainWindow.__init_defaults). Erst wenn ein Element sie
    benutzt, aendert sich die Kennung."""
    from statik3d import ergebnisse as erg
    from statik3d.model import Material, Section, ShellProp
    m = _basis()
    k0 = erg.kennung(m)
    m.add_shell_prop(ShellProp("t = 10 mm", 0.010))
    m.add_section(Section.from_profile("HEB 200"))
    m.add_material(Material.steel("S235"))
    ok, grund = erg.passt(k0, m)
    check("N38: ungenutzte Dicke, ungenutzter Querschnitt und Werkstoff dazu -> passt, ohne Vorbehalt",
          ok and grund == "", grund)
    m.materials["S235"].E *= 1.1
    ok, grund = erg.passt(k0, m)
    check("… E-Modul des ungenutzten Werkstoffs geändert -> passt weiter", ok and grund == "", grund)
    m.elements[0].mat = "S235"
    ok, grund = erg.passt(k0, m)
    check("… Stab 0 bekommt diesen Werkstoff -> passt nicht (Werkstoffe, Elementeigenschaften)",
          not ok and "Werkstoffe" in grund and "Elementeigenschaften" in grund, grund)


def test_n38_fenster_ohne_vorgaben():
    """Ein Modell, das ohne die Vorgaben des Fensters gerechnet wurde (hier
    _modell_setzen, ebenso aus dem Browser), findet seine Ergebnisdatei nach
    Speichern und Oeffnen passend - das Oeffnen legt „t = 10 mm“ an
    (gefunden im Gesamtlauf: test_namen_lf_lk G1)."""
    from statik3d import solver
    from statik3d.examples_lib import build_example
    w, app = _fenster()
    me = w.meldungen
    w._modell_setzen(build_example("frame")); w.refresh_all(); app.processEvents()
    dicken = sorted(w.model.shells)
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    p = os.path.join(tempfile.mkdtemp(prefix="q1_vorgaben_"), "rahmen.json")
    w.path = p
    w.save_model(); app.processEvents()
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("N38: ohne Dicken gerechnet, gespeichert, geöffnet (Vorgabe „t = 10 mm“ dazu): Ergebnis geladen",
          not dicken and "t = 10 mm" in w.model.shells and w.analysis is not None
          and w._analyse_passt() == "passt" and not me.hinweis_mit("nicht geladen"),
          f"Dicken vorher {dicken}, nachher {sorted(w.model.shells)}, {me.alle[-1:]}")
    _leeren(w)


def test_n38_beschriftungsfelder():
    """Die vorhandene Zerlegung der Oberflaeche (MainWindow.BESCHRIFTUNGSFELDER:
    „Übernehmen“ behaelt die Ergebnisse) und die Kennung sagen dasselbe:
    jedes Beschriftungsfeld, auf dem Weg der Maske geaendert, laesst die
    Rechenkennung, wie sie ist."""
    from statik3d import ergebnisse as erg
    w, app = _fenster()
    w._modell_setzen(_basis()); w.refresh_all(); app.processEvents()
    proben = {
        "berichtseintrag": ("0", {"name": "Bild 9", "beschriftung": "neu", "bemerkung": "b", "text": "t"}),
        "linie": ("B1", {"kommentar": "Kante"}),
        "geoflaeche": ("unten", {"kommentar": "Boden"}),
        "geokoerper_einzeln": ("Q1", {"kommentar": "Block"}),
        "lastfall": ("S", {"beschreibung": "Schnee nach Zone 3"}),
        "lager_einzeln": ("0", {"name": "Fuß Ost", "groesse": 2.0}),
        "linienlager_einzeln": ("0", {"name": "Rand 2"}),
        "flaechenlager_einzeln": ("0", {"name": "Bettung 2"}),
    }
    check("N38: jede Art aus BESCHRIFTUNGSFELDER hat eine Probe",
          set(proben) == set(w.BESCHRIFTUNGSFELDER), str(sorted(set(w.BESCHRIFTUNGSFELDER) ^ set(proben))))
    for art, (name, werte) in proben.items():
        vorher = erg.kennung(w.model).get("rechnung")
        try:
            w._beschriftung_uebernehmen(art, name, werte, set(werte))
            app.processEvents()
            fehler = ""
        except Exception as ex:          # noqa: BLE001
            fehler = f"{type(ex).__name__}: {ex}"
        nachher = erg.kennung(w.model).get("rechnung")
        check(f"N38: Beschriftung „{art}“ übernommen -> Rechenkennung gleich",
              not fehler and vorher is not None and vorher == nachher,
              fehler or ("" if vorher == nachher else str({g for g in (vorher or {})
                                                           if (vorher or {}).get(g) != (nachher or {}).get(g)})))
    _leeren(w)


def test_n38_rundlauf():
    """Gleiches Modell nach Speichern und Laden -> gleiche Kennung, in jeder
    Gruppe: alle Beispiele und das Modell mit allem (_basis, mit Stellung)."""
    from statik3d import ergebnisse as erg, examples_lib
    from statik3d.model import Model
    d = tempfile.mkdtemp(prefix="q1_rund_")
    modelle = [(n, examples_lib.build_example(n)) for n in examples_lib.EXAMPLES]
    modelle.append(("Halle mit Quader und Stellung", _mit_stellung(_basis())))
    for name, m in modelle:
        p = os.path.join(d, "m.json")
        k = erg.kennung(m)
        m.save(p)
        m2 = Model.load(p)
        k2 = erg.kennung(m2)
        m2.save(p)
        k3 = erg.kennung(Model.load(p))
        ok, grund = erg.passt(k, m2)
        check(f"N38: {name}: Kennung im Speicher = nach Speichern und Laden (zweimal)",
              "rechnung" in k and k == k2 == k3 and ok and grund == "",
              grund or str([g for g in (k.get("rechnung") or {})
                            if (k.get("rechnung") or {}).get(g) != (k2.get("rechnung") or {}).get(g)]))
        check(f"… {name}: auch nach Model.copy()", erg.kennung(m.copy()) == k)


def _kennung_der_datei(pfad, model):
    from statik3d import ergebnisse as erg
    with open(pfad, "rb") as fh:
        return erg._Leser(fh, model).load().get("kennung") or {}


def test_n38_alte_datei():
    """Eine Ergebnisdatei mit der Kennung vom 06.10.2026 (Knotenhash, aber
    keine Rechenangaben) wird wie in P6 mit Vorbehalt geladen, und der
    Hinweis sagt, was sie nicht prueft. Speichern ohne neue Rechnung behaelt
    die alte Form, eine neue Rechnung schreibt die neue."""
    from statik3d import ergebnisse as erg, solver
    w, app = _fenster()
    me = w.meldungen
    w.load_example("frame"); app.processEvents()
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    d = tempfile.mkdtemp(prefix="q1_alt_")
    p = os.path.join(d, "alt.json")
    ep = erg.pfad_zu(p)
    w.path = p
    neu = erg.kennung

    def alt(model):
        k = dict(neu(model))
        for f in ("rechnung", "rechnung_fassung", "lastfaelle_einzeln"):
            k.pop(f, None)                     # so schrieb das Programm am 06.10.2026
        return k
    erg.kennung = alt
    try:
        w.save_model(); app.processEvents()
    finally:
        erg.kennung = neu
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("N38: Ergebnisdatei ohne Rechenangaben in der Kennung: geladen, mit Vorbehalt",
          w.analysis is not None and me.hinweis_mit("mit Vorbehalt", "Lasten", "Werkstoffe", "Lager",
                                                    "neu rechnen"),
          f"analysis {'da' if w.analysis is not None else 'None'}, {me.alle[-1:]}")
    w.save_model(); app.processEvents()
    k1 = _kennung_der_datei(ep, w.model)
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("… wieder gespeichert ohne neue Rechnung: alte Form bleibt, der Vorbehalt kommt wieder",
          "rechnung" not in k1 and "knoten" in k1 and w.analysis is not None and me.hinweis_mit("mit Vorbehalt"),
          f"rechnung in der Kennung {'rechnung' in k1}, {me.alle[-1:]}")
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    w.save_model(); app.processEvents()
    k2 = _kennung_der_datei(ep, w.model)
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("… nach neuer Rechnung gespeichert: neue Kennung, ohne Vorbehalt geladen",
          "rechnung" in k2 and w.analysis is not None and not me.hinweis_mit("mit Vorbehalt"),
          f"rechnung in der Kennung {'rechnung' in k2}, {me.alle[-1:]}")


# ---------------------------------------------------------------------------
# N39
# ---------------------------------------------------------------------------
def test_n39_anders_nicht_ungespeichert():
    """Ein Ergebnis, das als „anders“ gilt (Modell waehrend der Rechnung
    geaendert), wird nicht gespeichert - die Rueckfrage vor dem Beenden nennt
    es darum nicht; die Aenderung am Modell nennt sie."""
    from statik3d import ergebnisse as erg
    w, app = _fenster()
    d = tempfile.mkdtemp(prefix="q1_n39_")
    # Gegenprobe zuerst: ohne Aenderung waehrend der Rechnung gilt das
    # Ergebnis als ungespeichert, und Speichern schreibt es
    w.load_example("frame"); app.processEvents()
    with _Langsam() as l:
        _rechnung_starten(w, app, l)
        _rechnung_beenden(w, app, l)
    check("N39 Gegenprobe: nichts geändert -> „Ergebnisse der letzten Rechnung“ ungespeichert",
          w._analyse_passt() == "passt" and "Ergebnisse der letzten Rechnung" in w.ungespeichert(),
          repr(w.ungespeichert()))
    w.load_example("frame"); app.processEvents()
    with _Langsam() as l:
        laeuft = _rechnung_starten(w, app, l)
        w.toggle_gravity(False); app.processEvents()
        _rechnung_beenden(w, app, l)
    grund = w.ungespeichert()
    check("N39: Modell während der Rechnung geändert: Ergebnis „anders“, nicht als ungespeichert genannt",
          laeuft and w.analysis is not None and w._analyse_passt() == "anders"
          and "Ergebnis" not in grund and "Änderungen am Modell" in grund, repr(grund))
    # die echte Rueckfrage, ohne Fenster: der Testschalter (tests/__init__.py)
    # stellte sie sonst gar nicht erst (wie tests.test_ungespeichert._Fragen)
    gefragt = []
    alt_env = os.environ.pop("STATIK3D_UNGESPEICHERT", None)
    w._frage_speichern_verwerfen = lambda anlass, g: (gefragt.append(g), "abbrechen")[1]
    try:
        w.close(); app.processEvents()
    finally:
        w.__dict__.pop("_frage_speichern_verwerfen", None)
        if alt_env is not None:
            os.environ["STATIK3D_UNGESPEICHERT"] = alt_env
    check("… die Rückfrage vor dem Beenden nennt nur die Änderungen am Modell",
          len(gefragt) == 1 and "Ergebnis" not in gefragt[0] and "Änderungen am Modell" in gefragt[0]
          and w.isVisible(), str(gefragt))
    p = os.path.join(d, "r.json")
    w.path = p
    w.save_model(); app.processEvents()
    check("… Speichern schreibt wirklich keine Ergebnisdatei (die Rückfrage hatte recht)",
          not os.path.exists(erg.pfad_zu(p)) and not w.ungespeichert(), repr(w.ungespeichert()))
    _leeren(w)


# ---------------------------------------------------------------------------
# N40
# ---------------------------------------------------------------------------
def test_n40_browser_waehrend_rechnung():
    """Waehrend einer Rechnung am Desktop weist der Browser jede Aenderung ab
    (409, die Meldung nennt die Rechnung); danach geht sie durch. Das
    Ergebnis passt dann zum Modell."""
    from statik3d.web.server import State, ApiError, apply_op
    from statik3d.examples_lib import build_example
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    st = State()
    st.bound = w
    w.web_state, w.web_version = st, st.version
    lf = w.model.active_case
    try:
        g0 = float(w.model.load_cases[lf].gravity[2])
        modell = w.model
        with _Langsam() as l:
            laeuft = _rechnung_starten(w, app, l)
            for titel, tun in (
                    ("Eigengewicht ändern", lambda: apply_op(st, {"op": "gravity", "case": lf, "gz": 2 * g0})),
                    ("Knoten anlegen", lambda: apply_op(st, {"op": "add_node", "x": 1, "y": 2, "z": 3})),
                    ("„Beispiel“ ersetzt das Modell", lambda: setattr(st, "model", build_example("truss")))):
                fehler = None
                try:
                    tun()
                except ApiError as ex:
                    fehler = ex
                check(f"N40: Browser während der Rechnung: {titel} abgewiesen (409, nennt die Rechnung)",
                      laeuft and fehler is not None and getattr(fehler, "status", 0) == 409
                      and "Rechnung" in str(fehler) and w.model is modell
                      and float(w.model.load_cases[lf].gravity[2]) == g0,
                      f"rechnet {laeuft}, {str(fehler)[:90] if fehler else 'nicht abgewiesen'}")
            _rechnung_beenden(w, app, l)
        check("… das Ergebnis passt zum Modell (nichts kam durch)",
              w.analysis is not None and w._analyse_passt() == "passt", w._analyse_passt())
        try:
            apply_op(st, {"op": "gravity", "case": lf, "gz": 2 * g0})
            frei = True
        except ApiError as ex:
            frei = str(ex)
        check("… nach der Rechnung geht die Änderung aus dem Browser durch",
              frei is True and float(w.model.load_cases[lf].gravity[2]) == 2 * g0, str(frei))
    finally:
        w.web_state = None
    _leeren(w)


def test_n40_browser_mitten_in_einer_aenderung():
    """Startet die Rechnung, waehrend eine Aenderung aus dem Browser noch
    laeuft (sie haelt das Schloss des Web-Servers), wartet der Start, bis sie
    fertig ist - die Rechnung liest dann ein fertiges Modell."""
    from statik3d.web.server import State
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    st = State()
    st.bound = w
    w.web_state, w.web_version = st, st.version
    try:
        gestartet = []
        frei = threading.Event()

        def browser():
            with st.lock:
                gestartet.append(time.time())
                frei.wait(0.5)

        t = threading.Thread(target=browser)
        t.start()
        while not gestartet:
            time.sleep(0.005)
        weiter = threading.Event()
        bekommen = []

        def lauf(progress=None):
            bekommen.append(time.time())
            weiter.wait(30)
            return "Ergebnis"
        w._run_background(lauf, lambda r: None, "Probelauf")
        _warten(app, lambda: bool(bekommen), 10.0)
        t.join()
        check("N40: Rechnung startet erst, wenn die laufende Änderung aus dem Browser fertig ist",
              bool(bekommen) and bekommen[0] >= gestartet[0] + 0.45,
              f"Start {bekommen[0] - gestartet[0]:.2f} s nach Beginn der Änderung" if bekommen else "kein Start")
        weiter.set()
        _warten(app, lambda: not w._rechnet())
        check("… danach ist der Browser wieder frei", not getattr(w, "web_sperrgrund", ""),
              repr(getattr(w, "web_sperrgrund", "")))
    finally:
        w.web_state = None


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_n38_beleg, test_n38_gruppen, test_n38_anzeige_zaehlt_nicht, test_n38_ungenutzte_eigenschaften,
              test_n38_fenster_ohne_vorgaben, test_n38_beschriftungsfelder, test_n38_rundlauf, test_n38_alte_datei, test_n39_anders_nicht_ungespeichert,
              test_n40_browser_waehrend_rechnung, test_n40_browser_mitten_in_einer_aenderung):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
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
