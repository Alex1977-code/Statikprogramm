"""
Ausblenden und Auswahl ohne Neuaufbau der Szene (Ansichtspaket B, 14.10.2026;
Entscheidung des Anwenders vom 13.10.2026 nach der Pruefung der ediBIM-Ansicht).

* Die Haut je Koerper (gui/sichtbarkeit.py) gibt **dieselben Zellen** wie die
  bisher je Ausblenden neu gebildete Oberflaeche - auch an einer Fuge mit
  gemeinsamen Knoten; ein halb ausgeblendeter Koerper faellt auf den alten
  Weg zurueck.
* Auswahlklick, Ausblenden (H), Isolieren (Umschalt+H), Alles einblenden
  (Alt+H) und Vorherige Sicht bauen die Szene nicht neu auf (kein
  ``_aufbauen``) und geben **dasselbe Bild** wie ein Neuaufbau.
* Mit Ergebnis oder Schnitt wird wie bisher neu aufgebaut.
* Modellbaum: Rechtsklick „Nur dieses zeigen / Alle einblenden / Ansicht
  darauf stellen“, Doppelklick = Ansicht darauf.
* Ruecksetzer-Knoepfe unten rechts nur, solange etwas aktiv ist.
* Radzoom zeichnet vereinfacht wie das Drehen.
* Lager je Art in einem Darsteller.

Aufruf:  python -m tests.test_ausblenden_ohne_neuaufbau
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_ausblenden_"), "einstellungen.json")

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
    w.resize(1280, 860)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _koerpermodell(m):
    """Zwei Tetraederkoerper A und B mit gemeinsamer Fuge (gemeinsame Knoten),
    ein getrennter Hexaederkoerper C, eine Schale S, zwei Linienlager und ein
    Flaechenlager. Rueckgabe {Name: Elemente}."""
    import pyvista as pv
    from statik3d.model import Material, Volumenkoerper
    m.add_material(Material.steel("S355"))
    g = pv.ImageData(dimensions=(9, 4, 4), spacing=(0.25, 0.3, 0.3)).cast_to_unstructured_grid().triangulate()
    X = np.asarray(g.points)
    kn = [m.add_node(*p) for p in X]
    conn = g.cells_dict[10]
    mitte = X[conn].mean(axis=1)
    teile = {"A": [], "B": [], "C": [], "S": []}
    for c, z in zip(conn, mitte):
        i = m.add_element("tet4", [kn[j] for j in c], "S355")
        teile["A" if z[0] < 1.0 else "B"].append(i)
    h = pv.ImageData(dimensions=(3, 3, 3), spacing=(0.3, 0.3, 0.3), origin=(3, 0, 0)).cast_to_unstructured_grid()
    kh = [m.add_node(*p) for p in np.asarray(h.points)]
    for c in h.cells_dict[11]:
        teile["C"].append(m.add_element("hex8", [kh[c[j]] for j in (0, 1, 3, 2, 4, 5, 7, 6)], "S355"))
    s = [m.add_node(0, -1, 0), m.add_node(1, -1, 0), m.add_node(1, -1, 1)]
    teile["S"].append(m.add_element("shell3", s, "S355"))
    for name in ("A", "B", "C"):
        m.koerper[name] = Volumenkoerper(name, [], elemente=list(teile[name]))
    m.support(kn[0], "all")
    m.support(kn[1], "pinned")
    m.add_line_support([kn[0], kn[4]], name="LL1", uz=dict(typ="spring", stiffness=1e7))
    m.add_line_support([kh[0], kh[1]], name="LL2", uz=dict(typ="spring", stiffness=1e7))
    m.add_surface_support(elements=teile["S"], name="FL1", uz=dict(typ="spring", stiffness=1e7))
    return teile


def _zellen(pd, kidx):
    el = np.asarray(pd.cell_data["elem"])
    return sorted((int(el[i]), tuple(sorted(int(kidx[j]) for j in pd.get_cell(i).point_ids)))
                  for i in range(pd.n_cells))


def _modell_im_fenster():
    w, app = _fenster()
    w.new_model()
    teile = _koerpermodell(w.model)
    w.refresh_all()
    app.processEvents()
    w.act_ergebnisse.setChecked(False)
    w.redraw()
    w.zoom_alles()
    app.processEvents()
    return w, app, teile


class _Zaehler:
    """Zaehlt die Aufrufe von _aufbauen (Neuaufbau der Szene) und redraw."""

    def __init__(self, w):
        self.w = w
        self.z = {"_aufbauen": 0, "redraw": 0}

    def __enter__(self):
        for name in self.z:
            orig = getattr(self.w, name)

            def huelle(*a, _o=orig, _n=name, **k):
                self.z[_n] += 1
                return _o(*a, **k)
            setattr(self.w, name, huelle)
        return self

    def __exit__(self, *exc):
        for name in self.z:
            self.w.__dict__.pop(name, None)
        return False


def _bild(w, app):
    """Das Bild der Ansicht. Offscreen hat das Fenster kein Zeichenfenster
    (``screenshot`` meldet „Render window is not current“); darum kommen alle
    Darsteller der Ansicht samt ihrer Kamera in einen eigenen Offscreen-Plotter."""
    import pyvista as pv
    from vtkmodules.vtkRenderingCore import vtkCamera
    app.processEvents()
    p = pv.Plotter(off_screen=True, window_size=(640, 480))
    p.set_background("white")
    p.renderer.SetActiveCamera(w.plotter.renderer.GetActiveCamera())
    props = list(w.plotter.renderer.actors.values())
    for a in props:
        p.renderer.AddViewProp(a)
    try:
        return np.asarray(p.screenshot(return_img=True), int)
    finally:
        for a in props:
            p.renderer.RemoveViewProp(a)
        p.renderer.SetActiveCamera(vtkCamera())
        p.close()


def _gleich_neu(w, app, titel):
    """Das Bild des Teil-Neuzeichnens gegen das Bild eines vollen Neuaufbaus."""
    import re

    def namen():
        # namenlose Darsteller (Achsenkreuz) heissen nach ihrer Adresse
        return sorted(re.sub(r"\(Addr=[0-9A-Fa-fx]+\)", "", n) for n in w.plotter.renderer.actors)
    a = _bild(w, app)
    namen_a = namen()
    w.redraw()
    b = _bild(w, app)
    namen_b = namen()
    anders = float(np.mean(np.any(a != b, axis=-1))) if a.shape == b.shape else 1.0
    modell = float(np.mean(np.any(b < 250, axis=-1)))
    check(f"{titel}: dasselbe Bild wie mit Neuaufbau", a.shape == b.shape and anders == 0.0 and modell > 0.02,
          f"{anders * 100:.3f} % der Bildpunkte anders, groesste Abweichung "
          f"{int(np.abs(a - b).max()) if a.shape == b.shape else '-'}; Modell auf {modell * 100:.1f} % des Bildes")
    check(f"{titel}: dieselben Darsteller", namen_a == namen_b,
          f"nur teil {sorted(set(namen_a) - set(namen_b))}, nur neu {sorted(set(namen_b) - set(namen_a))}")


# ---------------------------------------------------------------------------
def test_haut_gleiche_zellen():
    from statik3d.model import Model
    from statik3d.gui import viewport as vp, sichtbarkeit as sb
    m = Model()
    teile = _koerpermodell(m)
    typen = list(vp.CELL_MAP)
    volumen = {vp.CELL_MAP[t][0] for t in vp.TYPEN_VOLUMEN if t in vp.CELL_MAP}
    gruppe = np.full(len(m.elements), 3)
    for i, k in enumerate(m.koerper.values()):
        gruppe[k.elemente] = i
    haut = sb.Teiloberflaeche(vp.to_grid(m, typen=typen), m.nodes, gruppe, volumen, alle_typen=True)
    for titel, aus in (("nichts ausgeblendet", set()), ("A (Fuge mit B liegt frei)", set(teile["A"])),
                       ("B", set(teile["B"])), ("A und C", set(teile["A"]) | set(teile["C"])),
                       ("die Schale", set(teile["S"])), ("alles außer A", set(range(len(m.elements)))
                                                         - set(teile["A"]))):
        ref, kref = vp.oberflaeche(vp.to_grid(m, typen=typen, ausser=aus))
        pd, k = haut.teil(aus)
        a, b = _zellen(ref, kref), _zellen(pd, k)
        check(f"Haut je Körper, {titel}: dieselben Zellen wie neu gebildet", a == b and ref.n_points == pd.n_points,
              f"{len(a)} / {len(b)} Zellen, {ref.n_points} / {pd.n_points} Punkte")
    halb = set(teile["A"][: len(teile["A"]) // 2])
    check("ein halb ausgeblendeter Körper: Rückfall auf den Neuaufbau (None)", haut.teil(halb) is None)
    gh = haut.gruppenhaut(teile["A"])
    ref = vp.teilnetz(m, teile["A"]).extract_surface(pass_pointid=False, pass_cellid=False,
                                                    algorithm="dataset_surface")
    check("Hervorhebung eines Körpers aus der Haut: so viele Zellen wie seine eigene Oberfläche",
          gh is not None and gh.n_cells == ref.n_cells, f"{gh.n_cells if gh is not None else None} / {ref.n_cells}")


def test_auswahl_ohne_neuaufbau():
    from PySide6 import QtCore
    w, app, teile = _modell_im_fenster()
    w.auswahlart_setzen("Volumen", zeichnen=False)
    with _Zaehler(w) as z:
        w._mit_tasten(QtCore.Qt.NoModifier, lambda: w._objekt_umschalten(w.sel_koerper, "A", "Volumen",
                                                                           ersetzen=True))
        app.processEvents()
    check("Auswahlklick auf Körper A: kein Neuaufbau, ein redraw", z.z == {"_aufbauen": 0, "redraw": 1}, str(z.z))
    check("… die Hervorhebung ist ein eigener Darsteller", "auswahl_elemente" in w.plotter.renderer.actors,
          str(sorted(a for a in w.plotter.renderer.actors if a.startswith("auswahl"))))
    _gleich_neu(w, app, "Auswahlklick")
    with _Zaehler(w) as z:
        w._mit_tasten(QtCore.Qt.NoModifier, w._klick_ins_leere)
        app.processEvents()
    check("Klick ins Leere: kein Neuaufbau, die Hervorhebung ist weg",
          z.z["_aufbauen"] == 0 and "auswahl_elemente" not in w.plotter.renderer.actors, str(z.z))
    _gleich_neu(w, app, "Klick ins Leere")
    # eine Aenderung ohne Neuzeichnen (Darstellung umgestellt, ohne redraw):
    # der naechste Klick baut alles auf
    w.darstellung = "Transparent"
    with _Zaehler(w) as z:
        w._mit_tasten(QtCore.Qt.NoModifier, lambda: w._objekt_umschalten(w.sel_koerper, "B", "Volumen",
                                                                           ersetzen=True))
        app.processEvents()
    check("nach einer Änderung ohne Neuzeichnen baut der Klick die Szene neu auf (Schlüssel)",
          z.z["_aufbauen"] == 1, str(z.z))
    w.darstellung = "Voll"
    w.clear_selection()
    w.redraw()


def _taste(w, app, taste, mod):
    from PySide6 import QtCore, QtGui, QtWidgets
    for typ in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress):
        ev = QtGui.QKeyEvent(typ, taste, mod, "")
        QtWidgets.QApplication.sendEvent(w.plotter.interactor, ev)
    app.processEvents()


def test_tasten_und_ruecksetzer():
    from PySide6 import QtCore
    w, app, teile = _modell_im_fenster()
    w.auswahlart_setzen("Volumen", zeichnen=False)
    w.redraw()
    leer = _bild(w, app)
    w.sel_koerper[:] = ["A"]
    w.redraw()
    r_ = w.ruecksetzer
    check("Rücksetzer: ohne Ausgeblendetes und ohne Schnitt nicht zu sehen", not r_.isVisible())
    with _Zaehler(w) as z:
        _taste(w, app, QtCore.Qt.Key_H, QtCore.Qt.NoModifier)
    check("Taste H blendet die Auswahl aus - ohne Neuaufbau",
          w.versteckt["koerper"] == {"A"} and z.z["_aufbauen"] == 0, f"{w.versteckt['koerper']} {z.z}")
    netz = w.plotter.renderer.actors.get("model_netz")
    from statik3d.gui import viewport as vp
    ref, kref = vp.oberflaeche(vp.to_grid(w.model, typen=list(vp.CELL_MAP), ausser=set(teile["A"])))
    ds = netz.mapper.dataset if netz is not None else None
    check("… im Bild genau die Zellen des Neuaufbaus (A weg, Fuge von B frei)",
          ds is not None and _zellen(ds, np.asarray(ds.point_data["vtkOriginalPointIds"])) == _zellen(ref, kref),
          f"{ds.n_cells if ds is not None else None} / {ref.n_cells}")
    check("Rücksetzer: „1 Teil einblenden“ unten rechts",
          r_.isVisible() and r_.btn_teile.isVisible() and r_.btn_teile.text() == "1 Teil einblenden"
          and not r_.btn_schnitt.isVisible(), r_.btn_teile.text())
    zent = w.centralWidget()
    g = r_.geometry()
    check("… in der unteren rechten Ecke der Ansicht",
          g.bottom() > zent.height() - 40 and g.right() > zent.width() * 0.6, f"{g} in {zent.size()}")
    _gleich_neu(w, app, "Taste H")
    with _Zaehler(w) as z:
        w.sicht_zurueck()
        app.processEvents()
    check("Vorherige Sicht holt A zurück - ohne Neuaufbau",
          not w.versteckt["koerper"] and z.z["_aufbauen"] == 0, f"{w.versteckt['koerper']} {z.z}")
    check("… und das Bild ist wieder das vor dem Ausblenden", np.array_equal(_bild(w, app), leer))
    w.sel_koerper[:] = ["C"]
    w.redraw()
    with _Zaehler(w) as z:
        _taste(w, app, QtCore.Qt.Key_H, QtCore.Qt.ShiftModifier)
    check("Umschalt+H isoliert die Auswahl (A und B weg) - ohne Neuaufbau",
          w.versteckt["koerper"] == {"A", "B"} and z.z["_aufbauen"] == 0, f"{w.versteckt['koerper']} {z.z}")
    check("… der Rücksetzer zählt die ausgeblendeten Teile", r_.btn_teile.text() == "2 Teile einblenden"
          and "2 Körper" in r_.btn_teile.toolTip(), f"{r_.btn_teile.text()} | {r_.btn_teile.toolTip()}")
    _gleich_neu(w, app, "Umschalt+H")
    with _Zaehler(w) as z:
        _taste(w, app, QtCore.Qt.Key_H, QtCore.Qt.AltModifier)
    check("Alt+H blendet alles ein - ohne Neuaufbau",
          not any(w.versteckt.values()) and z.z["_aufbauen"] == 0, str(z.z))
    check("… der Rücksetzer ist wieder weg", not r_.isVisible())
    _gleich_neu(w, app, "Alt+H")
    # Knopf des Ruecksetzers
    w.sel_koerper[:] = ["B"]
    w.auswahl_ausblenden()
    r_.btn_teile.click()
    app.processEvents()
    check("Klick auf „1 Teil einblenden“ holt alles zurück", not any(w.versteckt.values()) and not r_.isVisible())
    # Schnitt: Knopf „Schnitt aus“, Ausblenden baut dann neu auf
    w.act_schnitt.setChecked(True)
    app.processEvents()
    check("Schnitt an: „Schnitt aus“ steht unten rechts", r_.isVisible() and r_.btn_schnitt.isVisible())
    w.sel_koerper[:] = ["C"]
    with _Zaehler(w) as z:
        w.auswahl_ausblenden()
        app.processEvents()
    check("mit Schnitt baut das Ausblenden neu auf (die Ebene liegt im Quader des Gezeichneten)",
          z.z["_aufbauen"] == 1, str(z.z))
    r_.btn_schnitt.click()
    app.processEvents()
    check("„Schnitt aus“ schaltet den Schnitt ab", w.schnitt is None and not w.act_schnitt.isChecked()
          and not r_.btn_schnitt.isVisible())
    w.alles_zeigen()
    # mit Ergebnis: Neuaufbau (Skala, Kennwerte, Marken haengen an den sichtbaren Knoten)
    w.redraw()
    w._szene_ergebnis = True
    w.sel_koerper[:] = ["C"]
    with _Zaehler(w) as z:
        w.auswahl_ausblenden()
        app.processEvents()
    check("mit gezeigtem Ergebnis baut das Ausblenden neu auf", z.z["_aufbauen"] == 1, str(z.z))
    w.alles_zeigen()
    tip = w.act_auswahl_weg_sicht.toolTip()
    check("der Befehl „Auswahl ausblenden“ nennt die Taste H", "Taste H in der Ansicht" in tip, tip)


def test_baum():
    from PySide6 import QtWidgets
    w, app, teile = _modell_im_fenster()
    b = w.baum
    menu = QtWidgets.QMenu()
    b._sichtmenue(menu, "geokoerper_einzeln", "A", ["A"])
    texte = [a.text() for a in menu.actions() if a.text()]
    check("Baum-Rechtsklick: „Nur dieses zeigen / Alle einblenden / Ansicht darauf stellen“",
          texte == ["Nur dieses zeigen", "Alle einblenden", "Ansicht darauf stellen"], str(texte))
    alle = [a for a in menu.actions() if a.text() == "Alle einblenden"][0]
    check("… „Alle einblenden“ gesperrt, solange nichts ausgeblendet ist", not alle.isEnabled())
    b.sicht.emit("nur", "geokoerper_einzeln", ["A"])
    app.processEvents()
    check("„Nur dieses zeigen“ an Körper A: B und C ausgeblendet", w.versteckt["koerper"] == {"B", "C"},
          str(w.versteckt["koerper"]))
    b.sicht.emit("alle", "geokoerper_einzeln", [])
    app.processEvents()
    check("„Alle einblenden“: nichts mehr ausgeblendet", not any(w.versteckt.values()))
    b.sicht.emit("ansicht", "geokoerper_einzeln", ["C"])
    app.processEvents()
    kam = w.plotter.renderer.GetActiveCamera()
    X = np.asarray(w.model.nodes)[sorted({int(n) for e in teile["C"] for n in w.model.elements[e].nodes})]
    mitte = 0.5 * (X.min(axis=0) + X.max(axis=0))
    check("„Ansicht darauf stellen“: der Blick zielt auf die Mitte von C",
          np.allclose(kam.GetFocalPoint(), mitte, atol=1e-9), f"{kam.GetFocalPoint()} / {mitte}")
    # Doppelklick auf den Eintrag
    w.zoom_alles()
    item = QtWidgets.QTreeWidgetItem(["B"])
    from PySide6 import QtCore
    item.setData(0, QtCore.Qt.UserRole, "geokoerper_einzeln")
    item.setData(0, QtCore.Qt.UserRole + 1, "B")
    bearbeitet = []
    b.bearbeiten.connect(lambda *a: bearbeitet.append(a))
    b._doppelklick(item, 0)
    app.processEvents()
    Xb = np.asarray(w.model.nodes)[sorted({int(n) for e in teile["B"] for n in w.model.elements[e].nodes})]
    check("Doppelklick auf einen Körper im Baum: Ansicht darauf, keine Bearbeiten-Maske",
          np.allclose(kam.GetFocalPoint(), 0.5 * (Xb.min(axis=0) + Xb.max(axis=0)), atol=1e-9) and not bearbeitet,
          f"{kam.GetFocalPoint()} {bearbeitet}")
    item.setData(0, QtCore.Qt.UserRole, "lastfall")
    item.setData(0, QtCore.Qt.UserRole + 1, "LF1")
    b._doppelklick(item, 0)
    check("… ein Lastfall öffnet weiter zum Bearbeiten", bearbeitet == [("lastfall", "LF1")], str(bearbeitet))


def test_radzoom_vereinfacht():
    from PySide6 import QtCore, QtGui, QtWidgets
    w, app, teile = _modell_im_fenster()
    w.SCHNELLDREHEN_AB = 0
    w.act_edges.setChecked(True)
    app.processEvents()
    knoten = w.plotter.renderer.actors.get("knoten")
    iren = w.plotter.interactor
    mitte = QtCore.QPointF(iren.width() / 2, iren.height() / 2)
    ev = QtGui.QWheelEvent(mitte, iren.mapToGlobal(mitte), QtCore.QPoint(0, 0), QtCore.QPoint(0, 120),
                           QtCore.Qt.NoButton, QtCore.Qt.NoModifier, QtCore.Qt.NoScrollPhase, False)
    QtWidgets.QApplication.sendEvent(iren, ev)
    netz = w.plotter.renderer.actors.get("model_netz")
    check("Radschritt: vereinfacht wie beim Drehen (Knoten weg, Netzkanten aus)",
          bool(w._vereinfacht) and knoten is not None and not knoten.GetVisibility()
          and not netz.GetProperty().GetEdgeVisibility(), str(w._vereinfacht is not None))
    ende = time.time() + 2.0
    while time.time() < ende and w._vereinfacht:
        app.processEvents()
        time.sleep(0.02)
    check("… ruht das Rad, ist alles wieder da",
          not w._vereinfacht and knoten.GetVisibility() and netz.GetProperty().GetEdgeVisibility())
    del w.SCHNELLDREHEN_AB


def test_lager_ein_darsteller():
    w, app, teile = _modell_im_fenster()
    namen = sorted(a for a in w.plotter.renderer.actors if "supports" in a)
    check("Lager je Art ein Darsteller (Knoten-, Linien-, Flächenlager), nicht je Lager",
          namen == ["fsupports", "lsupports", "lsupports_linie", "supports"], str(namen))
    farben = np.unique(np.asarray(w.plotter.renderer.actors["supports"].mapper.dataset.cell_data["farbe"]), axis=0)
    check("… zwei Lagerarten in einem Darsteller behalten ihre Farben", len(farben) == 2, str(farben.tolist()))


def test_handbuch():
    from tests.handbuch import absatz
    t = absatz("**Ausblenden ohne Neuaufbau.**")
    check("Handbuch: Ausblenden ohne Neuaufbau mit Tasten, Baum und Rücksetzer, Stand bis zum 14.10.2026",
          "Bis zum 14.10.2026" in t and "Umschalt+H" in t and "Alt+H" in t and "Nur dieses zeigen" in t
          and "Teile einblenden" in t, t[:120])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_haut_gleiche_zellen, test_auswahl_ohne_neuaufbau, test_tasten_und_ruecksetzer, test_baum,
              test_radzoom_vereinfacht, test_lager_ein_darsteller, test_handbuch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} lief durch", False, repr(ex))
    fehl = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(fehl)}/{len(RESULTS)} Prüfungen bestanden")
    sys.stdout.flush()
    os._exit(1 if fehl else 0)


if __name__ == "__main__":
    main()
