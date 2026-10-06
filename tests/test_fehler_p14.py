"""
Rueckgaengig und Uebernehmen (Fehlerliste vom 06.10.2026, Paket P14: F31 bis F34, F43).

Grundsatz: Jede Aenderung am Modell ist genau ein Rueckgaengig-Schritt und
verwirft die Ergebnisse, die nicht mehr passen; eine verworfene Aenderung
hinterlaesst keinen Schritt. „Auswahl uebernehmen“ in einer Maske aendert wie
jedes andere Feld erst mit „Uebernehmen“ das Modell (Paket 13m).

Geprueft wird am echten Hauptfenster (offscreen):

* F31: „Auswahl uebernehmen“ (und die Klickmodi des Wasserdrucks) in einer
  vorhandenen Wind-, Schweissnaht- oder Wasserdruckmaske schrieben sofort ins
  Modellobjekt - ohne „Uebernehmen“, ohne Rueckgaengig-Schritt, und nach dem
  Schliessen standen Auswahl und Lasten nicht mehr beieinander;
* F32: „Staebe erzeugen“ ist seit 60fe253 ein Schritt; „Schalennetz erzeugen“,
  „Volumennetz erzeugen“, „Doppelte Knoten zusammenfuehren“ und die
  Temperaturlast im Register Lager/Lasten hatten keinen. „Doppelte Knoten
  zusammenfuehren“ ohne doppelte Knoten hinterlaesst keinen Schritt;
* F33: der Haken „Eigengewicht“ ist ein Schritt und verwirft die Ergebnisse;
* F34: im Layerfenster gehoeren Esc, Strg+Z und Strg+Y dem Fenster, nicht dem
  Hauptmodell;
* F43: „Abbrechen“ in „Neu: Knoten“ nimmt auch den Schritt „Knoten angelegt“ weg.

Aufruf:  python -m tests.test_fehler_p14
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_fehler_p14_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


def _fenster():
    if "w" in _FENSTER:
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
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste)
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.Yes)
    _FENSTER.update(w=w, app=app)
    return w, app


def _ruhe(app, n=3):
    for _ in range(n):
        app.processEvents()


def _modell(w, app):
    """Ein leeres Modell mit Werkstoff, Querschnitt und Schalendicke, frische Stapel."""
    from statik3d.model import Material, Section, ShellProp
    w.maskenrand.schliessen()
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 200"))
    m.add_shell_prop(ShellProp("t10", 0.01))
    w.refresh_all()
    w._undo_init()
    w._undo_knoepfe()
    _ruhe(app)
    return m


def _mast(m, x, name):
    """Ein Mast aus drei Stabelementen, unten fest eingespannt."""
    from statik3d.model import Member
    ids = [m.add_node(x, 0, i) for i in range(4)]
    el = [m.add_element("beam", [ids[i], ids[i + 1]], "S355", "HEB 200") for i in range(3)]
    m.members[name] = Member(name, el)
    m.fix(ids[0], "all")


def _linienziele(m, fall) -> set:
    return {ll.ziel for ll in m.load_cases[fall].linienlasten}


# ---------------------------------------------------------------------------
# F31: „Auswahl uebernehmen“
# ---------------------------------------------------------------------------
def test_f31_wind():
    from statik3d.wind import Wind
    from statik3d import wind as wm
    w, app = _fenster()
    m = _modell(w, app)
    _mast(m, 0, "Mast")
    _mast(m, 5, "Mast2")
    wm.lasten_erzeugen(m, Wind("W", zone=2, richtung=[1, 0, 0], staebe=["Mast"]))
    w.refresh_all()
    w._undo_init()
    w._undo_knoepfe()
    fall = m.winde["W"].lastfall
    n0 = len(w._undo)
    check("Vorbereitung: Wind W belastet den Mast", m.winde["W"].staebe == ["Mast"]
          and _linienziele(m, fall) == {"Mast"}, f"{m.winde['W'].staebe}, {_linienziele(m, fall)}")
    w.maske_wind("W")
    _ruhe(app)
    mk = w.maskenrand.maske
    w.sel_staebe = ["Mast2"]
    mk.zusatzknoepfe["Auswahl übernehmen"].click()
    _ruhe(app)
    m = w.model
    check("Wind: „Auswahl übernehmen“ lässt das Modellobjekt unverändert (Ziel weiter Mast)",
          m.winde["W"].staebe == ["Mast"], str(m.winde["W"].staebe))
    check("… und legt keinen Rückgängig-Schritt an", len(w._undo) == n0, f"{n0} -> {len(w._undo)}")
    check("… die Maske zeigt das neue Ziel und trägt den Punkt „nicht übernommen“",
          "Mast2" in str(mk.werte().get("ziele")) and "ziele" in mk.geaenderte_felder()
          and mk.lbl_titel.text().startswith("● "), f"{mk.werte().get('ziele')!r}")
    w.maskenrand.schliessen()
    _ruhe(app)
    m = w.model
    check("Wind: Maske ohne Übernehmen geschlossen - Ziel und Lasten liegen weiter beide auf dem Mast",
          m.winde["W"].staebe == ["Mast"] and _linienziele(m, fall) == {"Mast"} and len(w._undo) == n0,
          f"{m.winde['W'].staebe}, {_linienziele(m, fall)}, Schritte {len(w._undo)}")
    # mit Uebernehmen: ein Schritt, Ziel und Lasten wandern gemeinsam
    w.maske_wind("W")
    _ruhe(app)
    mk = w.maskenrand.maske
    w.sel_staebe = ["Mast2"]
    mk.zusatzknoepfe["Auswahl übernehmen"].click()
    _ruhe(app)
    erg = mk.anwenden()
    _ruhe(app)
    m = w.model
    check("Wind: „Übernehmen“ schreibt die neue Auswahl - ein Schritt, Ziel und Lasten auf Mast2",
          erg is True and m.winde["W"].staebe == ["Mast2"] and _linienziele(m, fall) == {"Mast2"}
          and len(w._undo) == n0 + 1, f"{erg}, {m.winde['W'].staebe}, {_linienziele(m, fall)}, {n0} -> {len(w._undo)}")
    w.maskenrand.schliessen()
    w.undo()
    _ruhe(app)
    m = w.model
    check("… Rückgängig bringt Ziel und Lasten gemeinsam zurück (Mast)",
          m.winde["W"].staebe == ["Mast"] and _linienziele(m, fall) == {"Mast"},
          f"{m.winde['W'].staebe}, {_linienziele(m, fall)}")


def _naht_modell(w, app):
    from statik3d.schweissnaehte import Schweissnaht
    m = _modell(w, app)
    for x in (0, 3, 6):
        m.add_node(x, 0, 0)
    e0 = m.add_element("beam", [0, 1], "S355", "HEB 200")
    e1 = m.add_element("beam", [1, 2], "S355", "HEB 200")
    m.add_member("S1", [e0])
    m.add_member("S2", [e1])
    m.schweissnaehte["N1"] = Schweissnaht("N1", staebe=["S1"])
    w.refresh_all()
    w._undo_init()
    w._undo_knoepfe()
    return m


def test_f31_schweissnaht():
    w, app = _fenster()
    _naht_modell(w, app)
    n0 = len(w._undo)
    w.maske_schweissnaht("N1")
    _ruhe(app)
    mk = w.maskenrand.maske
    w.sel_staebe = ["S2"]
    mk.zusatzknoepfe["Auswahl übernehmen"].click()
    _ruhe(app)
    check("Naht: „Auswahl übernehmen“ lässt das Modellobjekt unverändert (S1) und legt keinen Schritt an",
          w.model.schweissnaehte["N1"].staebe == ["S1"] and len(w._undo) == n0,
          f"{w.model.schweissnaehte['N1'].staebe}, Schritte {n0} -> {len(w._undo)}")
    check("… die Maske zeigt S2 und trägt den Punkt",
          "S2" in str(mk.werte().get("ziele")) and "ziele" in mk.geaenderte_felder(), f"{mk.werte().get('ziele')!r}")
    w.maskenrand.schliessen()
    _ruhe(app)
    check("Naht: ohne Übernehmen geschlossen - das Modell trägt weiter S1",
          w.model.schweissnaehte["N1"].staebe == ["S1"], str(w.model.schweissnaehte["N1"].staebe))
    w.maske_schweissnaht("N1")
    _ruhe(app)
    mk = w.maskenrand.maske
    w.sel_staebe = ["S2"]
    mk.zusatzknoepfe["Auswahl übernehmen"].click()
    erg = mk.anwenden()
    _ruhe(app)
    check("Naht: „Übernehmen“ schreibt S2 - ein Schritt",
          erg is True and w.model.schweissnaehte["N1"].staebe == ["S2"] and len(w._undo) == n0 + 1,
          f"{erg}, {w.model.schweissnaehte['N1'].staebe}, {n0} -> {len(w._undo)}")
    w.maskenrand.schliessen()
    w.undo()
    _ruhe(app)
    check("… Rückgängig bringt S1 zurück", w.model.schweissnaehte["N1"].staebe == ["S1"],
          str(w.model.schweissnaehte["N1"].staebe))


def _wasser_modell(w, app):
    from statik3d.wasserdruck import Wasserdruck
    m = _modell(w, app)
    for kenn, y in (("A", 2), ("B", 4)):
        k = [m.add_node(*xyz) for xyz in ((0, y, 0), (5, y, 0), (5, y, 3), (0, y, 3))]
        for i in range(4):
            m.add_line(f"L{kenn}{i + 1}", [k[i], k[(i + 1) % 4]])
        m.add_flaeche(f"F{kenn}", [f"L{kenn}{i}" for i in (1, 2, 3, 4)])
    m.wasserdruecke["WD1"] = Wasserdruck("WD1", flaechen=["FA"], h_ow=3.0)
    w.refresh_all()
    w._undo_init()
    w._undo_knoepfe()
    return m


def test_f31_wasserdruck():
    w, app = _fenster()
    _wasser_modell(w, app)
    n0 = len(w._undo)
    w.maske_wasserdruck("WD1")
    _ruhe(app)
    mk = w.maskenrand.maske
    w.sel_flaechen = ["FB"]
    mk.zusatzknoepfe["Auswahl übernehmen"].click()
    _ruhe(app)
    wd = w.model.wasserdruecke["WD1"]
    check("Wasserdruck: „Auswahl übernehmen“ lässt das Modellobjekt unverändert (Fläche FA), kein Schritt",
          wd.flaechen == ["FA"] and len(w._undo) == n0, f"{wd.flaechen}, Schritte {n0} -> {len(w._undo)}")
    check("… die Maske zeigt FB und trägt den Punkt",
          "FB" in str(mk.werte().get("ziele")) and "ziele" in mk.geaenderte_felder(), f"{mk.werte().get('ziele')!r}")
    # die Klickmodi schrieben ebenfalls ins Modellobjekt (benetzt, Dichtung)
    mk.zusatzknoepfe["Benetzt anklicken"].click()
    mk.objekt_angeklickt("flaeche", "FB")
    mk.zusatzknoepfe["Dichtlinie anklicken"].click()
    mk.objekt_angeklickt("linie", "LA1")
    _ruhe(app)
    wd = w.model.wasserdruecke["WD1"]
    check("… ebenso die Klickmodi „Benetzt anklicken“ und „Dichtlinie anklicken“: das Modell bleibt",
          wd.flaechen == ["FA"] and wd.dichtung == [] and len(w._undo) == n0,
          f"Flächen {wd.flaechen}, Dichtung {wd.dichtung}, Schritte {len(w._undo)}")
    w.maskenrand.schliessen()
    _ruhe(app)
    wd = w.model.wasserdruecke["WD1"]
    check("Wasserdruck: ohne Übernehmen geschlossen - Flächen und Dichtung wie vorher",
          wd.flaechen == ["FA"] and wd.dichtung == [], f"{wd.flaechen}, {wd.dichtung}")
    # mit Uebernehmen: die Auswahl gilt, ein Schritt (analytisch: keine Stroemungsrechnung)
    w.maske_wasserdruck("WD1")
    _ruhe(app)
    mk = w.maskenrand.maske
    mk.setzen("verfahren", w.WASSERVERFAHREN[1])
    w.sel_flaechen = ["FB"]
    mk.zusatzknoepfe["Auswahl übernehmen"].click()
    erg = mk.anwenden()
    _ruhe(app)
    wd = w.model.wasserdruecke["WD1"]
    check("Wasserdruck: „Übernehmen“ schreibt FB - ein Schritt",
          erg is True and wd.flaechen == ["FB"] and len(w._undo) == n0 + 1,
          f"{erg}, {wd.flaechen}, {n0} -> {len(w._undo)}; Meldungen {w.fehler_liste[-2:]}")
    # nach dem ersten Uebernehmen teilen Maske und Modell keine Listen mehr
    mk.zusatzknoepfe["Benetzt anklicken"].click()
    mk.objekt_angeklickt("flaeche", "FA")
    _ruhe(app)
    wd = w.model.wasserdruecke["WD1"]
    check("… auch danach schreibt ein weiterer Klick nicht am Modell vorbei (Modell bleibt FB)",
          wd.flaechen == ["FB"], str(wd.flaechen))
    w.maskenrand.schliessen()


# ---------------------------------------------------------------------------
# F32: Wege ohne Rueckgaengig-Schritt
# ---------------------------------------------------------------------------
def _vorschritt(w):
    """Ein Schritt davor: ein Strg+Z danach darf nur den eigenen nehmen."""
    w.merken("Vorher")
    w.model.add_node(50.0, 0.0, 0.0)


def test_f32_schalennetz_register():
    w, app = _fenster()
    _modell(w, app)
    _vorschritt(w)
    s0, ne0, nn0 = len(w._undo), len(w.model.elements), w.model.nn
    w.cb_shell.setCurrentText("t10")
    w.make_plate()
    _ruhe(app)
    check("Schalennetz erzeugen (Register Netz): ein Rückgängig-Schritt „Platte“ und Elemente da",
          len(w._undo) == s0 + 1 and len(w.model.elements) > ne0 and str(w._undo[-1][0]) == "Platte",
          f"Schritte {s0} -> {len(w._undo)}, Elemente {ne0} -> {len(w.model.elements)}")
    w.undo()
    _ruhe(app)
    check("… Strg+Z nimmt genau das Netz zurück, der Knoten davor bleibt",
          len(w.model.elements) == ne0 and w.model.nn == nn0 and len(w._undo) == s0,
          f"Elemente {len(w.model.elements)}, Knoten {w.model.nn} (vorher {nn0}), Schritte {len(w._undo)}")
    w.redo()
    _ruhe(app)
    check("… Strg+Y bringt es wieder", len(w.model.elements) > ne0)


def test_f32_volumennetz_register():
    w, app = _fenster()
    _modell(w, app)
    _vorschritt(w)
    s0, ne0, nn0 = len(w._undo), len(w.model.elements), w.model.nn
    w.make_box()
    _ruhe(app)
    check("Volumennetz erzeugen (Register Netz): ein Rückgängig-Schritt „Quader“ und Elemente da",
          len(w._undo) == s0 + 1 and len(w.model.elements) > ne0 and str(w._undo[-1][0]) == "Quader",
          f"Schritte {s0} -> {len(w._undo)}, Elemente {ne0} -> {len(w.model.elements)}")
    w.undo()
    _ruhe(app)
    check("… Strg+Z nimmt genau das Netz zurück, der Knoten davor bleibt",
          len(w.model.elements) == ne0 and w.model.nn == nn0 and len(w._undo) == s0,
          f"Elemente {len(w.model.elements)}, Knoten {w.model.nn} (vorher {nn0}), Schritte {len(w._undo)}")


def test_f32_stabzug_register():
    """Seit 60fe253 ein Schritt - die Wege des Registers Netz bleiben es."""
    w, app = _fenster()
    _modell(w, app)
    _vorschritt(w)
    s0, ne0 = len(w._undo), len(w.model.elements)
    w.cb_sec.setCurrentText("HEB 200")
    w.make_beams()
    _ruhe(app)
    check("Stäbe erzeugen (Register Netz): ein Schritt „Stabzug“", len(w._undo) == s0 + 1
          and len(w.model.elements) > ne0, f"Schritte {s0} -> {len(w._undo)}")
    w.undo()
    _ruhe(app)
    check("… Strg+Z nimmt nur den Stabzug zurück", len(w.model.elements) == ne0 and len(w._undo) == s0)


def test_f32_doppelte_knoten():
    from statik3d import solver
    w, app = _fenster()
    m = _modell(w, app)
    m.add_node(0, 0, 0)
    m.add_node(0, 0, 0)
    m.add_node(3, 0, 0)
    m.add_element("beam", [1, 2], "S355", "HEB 200")
    m.fix(1, "all")
    w.refresh_all()
    w._solve_done("all", solver.solve_all(w.model, design=False))
    _ruhe(app)
    s0 = len(w._undo)
    w.do_merge()
    _ruhe(app)
    check("Doppelte Knoten zusammenführen: Knoten 3 -> 2, ein Rückgängig-Schritt",
          w.model.nn == 2 and len(w._undo) == s0 + 1, f"Knoten {w.model.nn}, Schritte {s0} -> {len(w._undo)}")
    check("… die Ergebnisse gelten nicht mehr (die Knoten sind umnummeriert)",
          w.analysis is None and w.results is None)
    check("… der Rückgängig-Knopf nennt den Schritt", "Doppelte Knoten" in w.act_undo.toolTip(), w.act_undo.toolTip())
    w.undo()
    _ruhe(app)
    check("… Strg+Z bringt die doppelten Knoten zurück", w.model.nn == 3 and len(w._undo) == s0, str(w.model.nn))
    w.redo()
    _ruhe(app)
    check("… Strg+Y führt sie wieder zusammen", w.model.nn == 2, str(w.model.nn))
    # nichts zu tun: kein Schritt, die Stapel bleiben
    m = _modell(w, app)
    m.add_node(0, 0, 0)
    m.add_node(3, 0, 0)
    w.merken("Vorher")
    w.undo()                                    # der Wiederholen-Stapel hat einen Eintrag
    _ruhe(app)
    stand, s0, r0 = w._stand, len(w._undo), len(w._redo)
    w.do_merge()
    _ruhe(app)
    check("Doppelte Knoten zusammenführen ohne doppelte Knoten: kein Schritt, Wiederholen-Stapel und Stand bleiben",
          len(w._undo) == s0 and len(w._redo) == r0 == 1 and w._stand == stand,
          f"Schritte {s0} -> {len(w._undo)}, Wiederholen {r0} -> {len(w._redo)}, Stand {stand} -> {w._stand}")


def test_f32_temperaturlast_register():
    from statik3d import solver
    w, app = _fenster()
    m = _modell(w, app)
    m.add_node(0, 0, 0)
    m.add_node(3, 0, 0)
    m.add_element("beam", [0, 1], "S355", "HEB 200")
    m.fix(0, "all")
    w.refresh_all()
    w._solve_done("all", solver.solve_all(w.model, design=False))
    _vorschritt(w)
    s0 = len(w._undo)
    w.ed_dT.set(30.0)
    w.ed_qelems.setText("0")
    w.add_temp_load()
    _ruhe(app)
    lc = w.model.case()
    check("Temperaturlast (Register Lager/Lasten): eine Last und ein Rückgängig-Schritt",
          len(lc.temp_loads) == 1 and len(w._undo) == s0 + 1, f"{len(lc.temp_loads)} Last(en), Schritte {s0} -> {len(w._undo)}")
    check("… die Ergebnisse sind verworfen (sie gehörten zur Rechnung ohne Temperatur)",
          w.analysis is None and w.results is None)
    check("… der Rückgängig-Knopf nennt „Temperaturlast“", "Temperaturlast" in w.act_undo.toolTip(), w.act_undo.toolTip())
    w.undo()
    _ruhe(app)
    check("… Strg+Z nimmt genau die Temperaturlast zurück, der Knoten davor bleibt",
          len(w.model.case().temp_loads) == 0 and w.model.nn == 3 and len(w._undo) == s0,
          f"{len(w.model.case().temp_loads)} Last(en), Knoten {w.model.nn}")


# ---------------------------------------------------------------------------
# F33: Eigengewicht
# ---------------------------------------------------------------------------
def test_f33_eigengewicht():
    from statik3d import solver
    w, app = _fenster()
    m = _modell(w, app)
    m.add_node(0, 0, 0)
    m.add_node(4, 0, 0)
    m.add_element("beam", [0, 1], "S355", "HEB 200")
    m.fix(0, "all")
    w.refresh_all()
    w._solve_done("all", solver.solve_all(w.model, design=False))
    _ruhe(app)
    s0 = len(w._undo)
    check("Vorbereitung: ein Ergebnis liegt vor, kein Eigengewicht", w.analysis is not None
          and not w.cb_g.isChecked() and float(w.model.case().gravity[2]) == 0.0)
    w.cb_g.setChecked(True)
    _ruhe(app)
    check("Eigengewicht an: g_z = -9,81 und ein Rückgängig-Schritt",
          abs(float(w.model.case().gravity[2]) + 9.81) < 1e-12 and len(w._undo) == s0 + 1,
          f"g_z {w.model.case().gravity[2]}, Schritte {s0} -> {len(w._undo)}")
    check("… das Ergebnis ohne Eigengewicht gilt nicht mehr", w.analysis is None and w.results is None)
    check("… der Rückgängig-Knopf nennt „Eigengewicht“", "Eigengewicht" in w.act_undo.toolTip(), w.act_undo.toolTip())
    w.undo()
    _ruhe(app)
    check("… Strg+Z schaltet es wieder aus, und der Haken folgt",
          float(w.model.case().gravity[2]) == 0.0 and not w.cb_g.isChecked() and len(w._undo) == s0,
          f"g_z {w.model.case().gravity[2]}, Haken {w.cb_g.isChecked()}")
    w.redo()
    _ruhe(app)
    check("… Strg+Y schaltet es wieder an, und der Haken folgt",
          abs(float(w.model.case().gravity[2]) + 9.81) < 1e-12 and w.cb_g.isChecked())
    w._solve_done("all", solver.solve_all(w.model, design=False))
    s1 = len(w._undo)
    w.cb_g.setChecked(False)
    _ruhe(app)
    check("Eigengewicht aus: g_z = 0, ein weiterer Schritt, Ergebnis verworfen",
          float(w.model.case().gravity[2]) == 0.0 and len(w._undo) == s1 + 1 and w.analysis is None,
          f"Schritte {s1} -> {len(w._undo)}")
    s2, stand = len(w._undo), w._stand
    w.toggle_gravity(False)
    _ruhe(app)
    check("Schon aus und wieder „aus“: nichts ändert sich, kein Schritt", len(w._undo) == s2 and w._stand == stand,
          f"Schritte {s2} -> {len(w._undo)}")


# ---------------------------------------------------------------------------
# F34: Layerfenster
# ---------------------------------------------------------------------------
def _layerfenster(w, app):
    import numpy as np
    m = _modell(w, app)
    for x in (0, 2, 4):
        m.add_node(x, 0, 0)
    w.refresh_all()
    w._undo_init()
    w._undo_knoepfe()
    w.selection = np.array([0, 1], dtype=int)
    w.layerliste_zeigen()
    _ruhe(app)
    f = w._layer_fenster
    f.activateWindow()
    f.tabelle.setFocus()
    _ruhe(app)
    return f


def test_f34_layerfenster_nimmt_seine_tasten():
    from PySide6 import QtCore, QtTest
    K = QtCore.Qt
    w, app = _fenster()
    f = _layerfenster(w, app)
    check("Vorbereitung: das Layerfenster ist aktiv, die Tabelle hat den Fokus",
          f.isActiveWindow() and f.tabelle.hasFocus(), f"aktiv {f.isActiveWindow()}, Fokus {f.tabelle.hasFocus()}")
    # ein Modellschritt, der nicht zur Layerliste gehoert
    w.merken("Knoten angelegt")
    w.model.add_node(9.0, 0.0, 0.0)
    nn, s0 = w.model.nn, len(w._undo)
    QtTest.QTest.keyClick(f.tabelle, K.Key_Z, K.ControlModifier)
    _ruhe(app)
    check("Strg+Z im Layerfenster nimmt keinen Modellschritt zurück, der nicht zur Layerliste gehört",
          w.model.nn == nn and len(w._undo) == s0, f"Knoten {nn} -> {w.model.nn}, Schritte {s0} -> {len(w._undo)}")
    check("… und sagt, wo Rückgängig dafür gilt",
          w.meldungen.hinweis_mit("Layerliste", "Knoten angelegt"), str(w.meldungen.hinweise[-1:]))
    # ein Layerschritt: Strg+Z nimmt ihn zurueck, Strg+Y stellt ihn wieder her
    w.layer_aus_auswahl("Deckel")
    _ruhe(app)
    check("Vorbereitung: der Layer „Deckel“ ist angelegt, die Tabelle zeigt ihn",
          "Deckel" in w.model.layer and f.zeile_von("Deckel") >= 0)
    s1 = len(w._undo)
    f.activateWindow()
    f.tabelle.setFocus()
    _ruhe(app)
    QtTest.QTest.keyClick(f.tabelle, K.Key_Z, K.ControlModifier)
    _ruhe(app)
    check("Strg+Z im Layerfenster nimmt den Layerschritt zurück (Layer weg, Tabelle nachgeführt)",
          "Deckel" not in w.model.layer and len(w._undo) == s1 - 1 and f.zeile_von("Deckel") < 0
          and w.model.nn == nn, f"Layer {list(w.model.layer)}, Schritte {s1} -> {len(w._undo)}, Zeile {f.zeile_von('Deckel')}")
    f.activateWindow()
    f.tabelle.setFocus()
    _ruhe(app)
    QtTest.QTest.keyClick(f.tabelle, K.Key_Y, K.ControlModifier)
    _ruhe(app)
    check("Strg+Y im Layerfenster stellt ihn wieder her (Layer da, Tabelle nachgeführt)",
          "Deckel" in w.model.layer and len(w._undo) == s1 and f.zeile_von("Deckel") >= 0,
          f"Layer {list(w.model.layer)}, Schritte {len(w._undo)}")
    # Strg+Y ohne Layerschritt im Wiederholen-Stapel: nichts
    w.undo()                                    # nimmt „Layer Deckel“ zurueck
    w.undo()                                    # nimmt „Knoten angelegt“ zurueck
    _ruhe(app)
    f.activateWindow()
    f.tabelle.setFocus()
    _ruhe(app)
    nn2, r0 = w.model.nn, len(w._redo)
    QtTest.QTest.keyClick(f.tabelle, K.Key_Y, K.ControlModifier)
    _ruhe(app)
    check("Strg+Y im Layerfenster stellt keinen fremden Schritt wieder her (hier liegt „Knoten angelegt“ obenauf)",
          len(w._redo) == r0 and w.model.nn == nn2 and not w.model.layer,
          f"Wiederholen {r0} -> {len(w._redo)}, Knoten {nn2} -> {w.model.nn}, Layer {list(w.model.layer)}")
    # Esc: schliesst das Fenster, die Auswahl im Modell bleibt
    import numpy as np
    w.selection = np.array([0, 1], dtype=int)
    f.activateWindow()
    f.tabelle.setFocus()
    _ruhe(app)
    QtTest.QTest.keyClick(f.tabelle, K.Key_Escape)
    _ruhe(app)
    check("Esc im Layerfenster schließt das Fenster", not f.isVisible(), f"sichtbar {f.isVisible()}")
    check("… und hebt die Auswahl im Hauptfenster nicht auf (2 Knoten bleiben)",
          len(w.selection) == 2, f"{len(w.selection)} Knoten")


def test_f34_layerfenster_umbenennen_behaelt_esc():
    """Beim Umbenennen in der Tabelle gehören Strg+Z und Esc dem Feld; das
    Fenster bleibt offen, das Modell unberührt."""
    from PySide6 import QtCore, QtTest, QtWidgets
    K = QtCore.Qt
    w, app = _fenster()
    f = _layerfenster(w, app)
    w.layer_aus_auswahl("Deckel")
    _ruhe(app)
    nn, s0 = w.model.nn, len(w._undo)
    f.activateWindow()
    f.tabelle.setFocus()
    f.tabelle.editItem(f.tabelle.item(f.zeile_von("Deckel"), 0))
    _ruhe(app)
    ed = f.tabelle.findChild(QtWidgets.QLineEdit)
    check("Vorbereitung: die Zelle ist im Umbenennen, das Feld hat den Fokus", ed is not None and ed.hasFocus(),
          f"Feld {ed is not None}")
    if ed is None:
        return
    QtTest.QTest.keyClicks(ed, "xy")
    QtTest.QTest.keyClick(ed, K.Key_Z, K.ControlModifier)
    _ruhe(app)
    check("Strg+Z im Umbenennen macht die Eingabe im Feld rückgängig, das Modell bleibt",
          w.model.nn == nn and len(w._undo) == s0 and "Deckel" in w.model.layer, f"{ed.text()!r}")
    QtTest.QTest.keyClick(ed, K.Key_Escape)
    _ruhe(app)
    check("Esc im Umbenennen bricht nur das Umbenennen ab - das Fenster bleibt offen, der Name auch",
          f.isVisible() and "Deckel" in w.model.layer and len(w._undo) == s0,
          f"sichtbar {f.isVisible()}, Layer {list(w.model.layer)}")
    f.close()


# ---------------------------------------------------------------------------
# F43: Neu: Knoten
# ---------------------------------------------------------------------------
def test_f43_neu_knoten_abbrechen():
    w, app = _fenster()
    _modell(w, app)
    _vorschritt(w)
    nn0, s0, stand0 = w.model.nn, len(w._undo), w._stand
    w._baum_neu("knoten")
    _ruhe(app)
    mk = w.maskenrand.maske
    check("Vorbereitung: „Neu: Knoten“ legt den Knoten und den Schritt „Knoten angelegt“ an",
          w.model.nn == nn0 + 1 and len(w._undo) == s0 + 1 and str(w._undo[-1][0]) == "Knoten angelegt",
          f"Knoten {nn0} -> {w.model.nn}, Schritte {s0} -> {len(w._undo)}")
    mk.abbrechen()
    _ruhe(app)
    check("Abbrechen: der Knoten ist weg", w.model.nn == nn0, f"{w.model.nn}")
    check("… und der Schritt „Knoten angelegt“ auch (der Stapel ist wie vorher)",
          len(w._undo) == s0 and str(w._undo[-1][0]) == "Vorher", f"Schritte {s0} -> {len(w._undo)}, "
          f"oben {[str(e[0]) for e in w._undo][-2:]}")
    check("… der Rückgängig-Knopf nennt den Schritt davor", "Vorher" in w.act_undo.toolTip(), w.act_undo.toolTip())
    check("… und nichts gilt als ungespeichert dazugekommen", w._stand == stand0, f"{stand0} -> {w._stand}")
    check("… Strg+Z nimmt danach den Schritt davor, nicht einen leeren",
          (w.undo(), w.model.nn)[1] == nn0 - 1, f"Knoten {w.model.nn}")
    # „Verwerfen“ in der Aenderungsleiste ist derselbe Weg
    _modell(w, app)
    _vorschritt(w)
    s0 = len(w._undo)
    w._baum_neu("knoten")
    _ruhe(app)
    mk = w.maskenrand.maske
    w._maske_verwerfen(mk)
    _ruhe(app)
    check("„Verwerfen“ (Leiste): ebenfalls kein leerer Schritt", len(w._undo) == s0 and w.model.nn == 1,
          f"Schritte {s0} -> {len(w._undo)}, Knoten {w.model.nn}")
    # Uebernehmen bleibt ein Schritt, und Rueckgaengig nimmt den Knoten weg
    _modell(w, app)
    s0, nn0 = len(w._undo), w.model.nn
    w._baum_neu("knoten")
    _ruhe(app)
    mk = w.maskenrand.maske
    mk.setzen("x", 2.0)
    erg = mk.anwenden()
    _ruhe(app)
    check("„Übernehmen“ im neuen Knoten: ein Schritt, der Knoten steht bei x = 2",
          erg is True and len(w._undo) == s0 + 1 and w.model.nn == nn0 + 1 and float(w.model.nodes[-1][0]) == 2.0,
          f"{erg}, Schritte {s0} -> {len(w._undo)}")
    w.undo()
    _ruhe(app)
    check("… Rückgängig nimmt den Knoten wieder weg", w.model.nn == nn0, str(w.model.nn))
    w.maskenrand.schliessen()
    # ein anderer Schritt liegt inzwischen obenauf: das Entfernen ist dann ein eigener Schritt
    _modell(w, app)
    nn0 = w.model.nn
    w._baum_neu("knoten")
    _ruhe(app)
    mk = w.maskenrand.maske
    w.merken("Dazwischen")
    s1 = len(w._undo)
    mk.abbrechen()
    _ruhe(app)
    check("Liegt ein anderer Schritt obenauf, ist das Entfernen ein eigener Schritt „Knoten … entfernt“",
          w.model.nn == nn0 and len(w._undo) == s1 + 1 and "entfernt" in str(w._undo[-1][0]),
          f"Knoten {w.model.nn}, Schritte {s1} -> {len(w._undo)}, oben {str(w._undo[-1][0])!r}")
    w.undo()
    _ruhe(app)
    check("… und Rückgängig bringt den Knoten zurück", w.model.nn == nn0 + 1, str(w.model.nn))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_f31_wind, test_f31_schweissnaht, test_f31_wasserdruck,
              test_f32_schalennetz_register, test_f32_volumennetz_register, test_f32_stabzug_register,
              test_f32_doppelte_knoten, test_f32_temperaturlast_register,
              test_f33_eigengewicht,
              test_f34_layerfenster_nimmt_seine_tasten, test_f34_layerfenster_umbenennen_behaelt_esc,
              test_f43_neu_knoten_abbrechen):
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
