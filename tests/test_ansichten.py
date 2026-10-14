"""
Ansichtspaket C (Entscheidung des Anwenders vom 13.10.2026, gebaut 14.10.2026):
gespeicherte Ansichten im Modell und eine Schnittbox mit Griffen.

* Datei: Ansichten stehen nur in der Datei, wenn es welche gibt - eine Datei
  ohne sie bleibt Zeichen fuer Zeichen; sie zaehlen nicht fuer die Rechnung;
* Ansicht speichern und aufrufen ergibt dieselbe Kamera (Lage, Ziel, Oben,
  Projektion, Massstab), dasselbe Ausgeblendete, denselben Schnitt (Ebene und
  Box), dieselbe Darstellung und dasselbe Ergebnis;
* geloeschte Objekte und ein neues Netz werden beim Aufruf uebersprungen und
  genannt;
* Modellbaum „Ansichten“ (Hilfsobjekte): anlegen, aufrufen, umbenennen,
  loeschen; Ribbon „Ansicht speichern“;
* Berichtsbild aus einer gespeicherten Ansicht;
* Schnittbox: sichtbare Zellen nur innerhalb, auf dem Schnitt die
  Ergebnisfarben (lineares Pruef-Feld exakt, Verschiebung wie VTK-Probe),
  ebenso bei der Schnittebene; Griffe ziehen, Mindestrest, Mausrad ueber einem
  Griff schiebt fein und zoomt nicht; „Schnitt aus“ stellt alles wieder her.

Offscreen zeichnet VTK nicht (Fenstergroesse 0 x 0): ``plotter.render`` ist
ausgeschaltet, fuer die Griffe bekommt das Renderfenster die Groesse der
Ansicht, Bildschirmpunkte rechnet die Pruefung aus der Kamera. Das echte Bild
prueft die Hauptsitzung auf dem Desktop.

Aufruf:  python -m tests.test_ansichten
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_ansichten_"), "einstellungen.json")
os.environ.pop("STATIK3D_FENSTER", None)

import numpy as np                                      # noqa: E402

RESULTS = []
_FENSTER = {}
TMP = tempfile.mkdtemp(prefix="statik3d_ansichten_dateien_")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _modell():
    """tet10-Wuerfel 1 m, unten fest, oben 1 MN/m² Druck."""
    from tests.test_fugen import _wuerfel
    m = _wuerfel(0.25, 2)
    for i in np.flatnonzero(np.abs(np.asarray(m.nodes)[:, 2]) < 1e-9):
        m.fix(int(i), [0, 1, 2])
    m.add_geometrielast("Deckel", 1.0e6, "flaeche", case="LF1")
    m.lasten_verteilen()
    return m


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d import solver
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen = lambda *a, **k: True
    w._fragen_knoepfe = lambda *a, **k: True
    w._bestaetigen = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    # Offscreen zeichnet VTK nicht (test_ansicht_gizmo: ein Zeichenaufruf mit
    # gesetzter Groesse stuerzte ab)
    w.plotter.render = lambda *a, **k: None
    m = _modell()
    an = solver.solve_all(m)
    w._modell_setzen(m)
    w._solve_done("all", an)
    app.processEvents()
    for k in range(w.cb_result.count()):
        d = w.cb_result.itemData(k)
        if d and d[0] == "case" and d[1] == "LF1":
            w.cb_result.setCurrentIndex(k)
    app.processEvents()
    _FENSTER.update(w=w, app=app)
    return w, app


def _kamera(w):
    k = w.plotter.renderer.GetActiveCamera()
    return (np.asarray(k.GetPosition(), float), np.asarray(k.GetFocalPoint(), float),
            np.asarray(k.GetViewUp(), float), bool(k.GetParallelProjection()), float(k.GetParallelScale()))


def _gleiche_kamera(a, b) -> bool:
    return (np.allclose(a[0], b[0], atol=1e-9) and np.allclose(a[1], b[1], atol=1e-9)
            and np.allclose(a[2], b[2], atol=1e-9) and a[3] == b[3] and abs(a[4] - b[4]) < 1e-9)


def _gitter(w):
    return w._gitter_zwischen[0], w._gitter_zwischen[1]


def _volle_flaechenzahl(w):
    """Zellen der Oberflaeche ohne Schnitt (wie _gitter ohne Ebene und Box)."""
    from statik3d.gui import viewport as vp
    g = vp.to_grid(w.model)
    f, _k = vp.oberflaeche(g)
    return int(f.n_cells)


# --------------------------------------------------------------------------
# 1. Datei
# --------------------------------------------------------------------------
def test_datei():
    from statik3d.model import Model, Ansicht
    from statik3d import ergebnisse as eg
    m = _modell()
    a_pfad = os.path.join(TMP, "ohne.json")
    m.save(a_pfad)
    m2 = Model.load(a_pfad)
    b_pfad = os.path.join(TMP, "ohne_2.json")
    m2.save(b_pfad)
    roh_a, roh_b = open(a_pfad, "rb").read(), open(b_pfad, "rb").read()
    check("Modell ohne Ansichten: kein Schlüssel „ansichten“ in der Datei, Laden und Speichern bitgleich",
          b'"ansichten"' not in roh_a and roh_a == roh_b, f"{len(roh_a)} / {len(roh_b)} Bytes")
    kennung_ohne = eg.rechenkennung(m2)
    m2.ansichten["A1"] = Ansicht(name="A1", kamera={"position": [1.0, 2.0, 3.0], "ziel": [0.5, 0.5, 0.5],
                                                     "oben": [0.0, 0.0, 1.0], "ortho": True, "massstab": 0.7,
                                                     "blickwinkel": 30.0},
                                 versteckt={"elemente": [1, 2], "flaechen": ["M1"], "geist": True},
                                 schnitt={"box": [0.1, 0.9, 0.0, 1.0, 0.2, 0.8]},
                                 darstellung={"art": "Transparent"}, netz=[len(m2.elements), m2.nn],
                                 kommentar="Prüfung")
    check("Ansichten zählen nicht für die Rechnung (Kennung der Ergebnisdatei unverändert)",
          eg.rechenkennung(m2) == kennung_ohne)
    c_pfad = os.path.join(TMP, "mit.json")
    m2.save(c_pfad)
    d = json.load(open(c_pfad, encoding="utf-8"))
    m3 = Model.load(c_pfad)
    from dataclasses import asdict
    check("mit Ansicht: „ansichten“ steht in der Datei und kommt beim Laden gleich zurück",
          "ansichten" in d and list(m3.ansichten) == ["A1"]
          and asdict(m3.ansichten["A1"]) == asdict(m2.ansichten["A1"]),
          str(list(d)[-3:]))
    del m3.ansichten["A1"]
    e_pfad = os.path.join(TMP, "wieder_ohne.json")
    m3.save(e_pfad)
    check("Ansicht wieder gelöscht: die Datei ist bitgleich mit der ursprünglichen",
          open(e_pfad, "rb").read() == roh_a)
    # Eine Datei aus dem Bestand des Programms (Beispiel), wie sie ist
    from statik3d.importers import anhaengen as A
    check("Anhängen kennt „ansichten“ (nicht übertragen, mit Grund)", "ansichten" in A.NICHT_UEBERTRAGEN)


# --------------------------------------------------------------------------
# 2. Speichern und aufrufen
# --------------------------------------------------------------------------
def _zustand(w):
    return {"kamera": _kamera(w), "versteckt": {k: set(v) for k, v in w.versteckt.items()},
            "geist": bool(w.geist), "schnitt": w.schnitt, "box": w.schnittbox_grenzen(),
            "darstellung": w.darstellung, "feld": w.cb_field.currentText(),
            "quelle": w._aktuelle_quelle(), "flaechen_an": w.act_flaechen.isChecked(),
            "schnitt_haken": w.act_schnitt.isChecked(), "box_haken": w.act_schnittbox.isChecked()}


def test_speichern_aufrufen():
    w, app = _fenster()
    m = w.model
    # einen Zustand einstellen
    w.blickrichtung("iso")
    w.projektion_setzen(True, merken=False)
    w.versteckt["elemente"] = set(range(0, 40))
    w.versteckt["flaechen"] = {"M1"}
    w.geist = True
    w.cb_schnittachse.setCurrentText("x")
    w.sl_schnitt.setValue(40)
    w.act_schnitt.setChecked(True)
    w.schnittbox_setzen([0.05, 0.95, 0.1, 0.9, 0.0, 0.8])
    w.darstellung_setzen("Transparent")
    i = w.cb_field.findText("Verschiebung uz") if w.cb_field.findText("Verschiebung uz") >= 0 else 1
    w.cb_field.setCurrentIndex(i)
    w.redraw()
    app.processEvents()
    vorher = _zustand(w)
    zellen_vorher = int(_gitter(w)[0].n_cells)
    a = w.ansicht_speichern("Detail oben")
    check("Ansicht gespeichert: im Modell unter ihrem Namen", "Detail oben" in m.ansichten and a is not None)
    # alles verstellen
    w.blickrichtung("+z")
    w.projektion_setzen(False, merken=False)
    w.alles_zeigen()
    w.geist = False
    w.schnitt_aus()
    w.darstellung_setzen("Voll")
    w.cb_field.setCurrentIndex(0)
    app.processEvents()
    zwischen = _zustand(w)
    check("… danach verstellt (andere Kamera, nichts ausgeblendet, kein Schnitt)",
          not _gleiche_kamera(zwischen["kamera"], vorher["kamera"]) and zwischen["box"] is None
          and zwischen["schnitt"] is None and not any(zwischen["versteckt"].values()))
    fehlt = w.ansicht_aufrufen("Detail oben")
    app.processEvents()
    nach = _zustand(w)
    check("Aufrufen: dieselbe Kamera (Lage, Ziel, Oben, Parallelprojektion, Maßstab)",
          _gleiche_kamera(nach["kamera"], vorher["kamera"]),
          f"{np.round(nach['kamera'][0], 4).tolist()} / {np.round(vorher['kamera'][0], 4).tolist()}")
    check("… dieselben ausgeblendeten Teile und der Geist",
          nach["versteckt"] == vorher["versteckt"] and nach["geist"] == vorher["geist"])
    check("… derselbe Schnitt: Ebene (mit Haken) und Box (mit Haken)",
          nach["schnitt"] == vorher["schnitt"] and nach["box"] == vorher["box"]
          and nach["schnitt_haken"] and nach["box_haken"], f"{nach['schnitt']} {nach['box']}")
    check("… dieselbe Darstellung und dasselbe Ergebnis mit Färbung",
          nach["darstellung"] == "Transparent" and nach["feld"] == vorher["feld"]
          and nach["quelle"] == vorher["quelle"], f"{nach['darstellung']} {nach['feld']} {nach['quelle']}")
    check("… nichts übersprungen, das Bild zeigt dieselben Zellen",
          not fehlt and int(_gitter(w)[0].n_cells) == zellen_vorher, f"{fehlt} {zellen_vorher}")
    # ueber die Datei
    from statik3d.model import Model
    pfad = os.path.join(TMP, "fenster.json")
    m.save(pfad)
    m2 = Model.load(pfad)
    from dataclasses import asdict
    check("… und nach Speichern und Laden der Datei ist die Ansicht dieselbe",
          asdict(m2.ansichten["Detail oben"]) == asdict(m.ansichten["Detail oben"]))
    w.schnitt_aus()
    w.alles_zeigen()


def test_geloeschte_objekte():
    from statik3d.model import Ansicht
    w, app = _fenster()
    m = w.model
    w.meldungen.eintraege.clear()
    m.ansichten["Alt"] = Ansicht(name="Alt", versteckt={"flaechen": ["M2", "F99"], "elemente": [5, 10 ** 7],
                                                         "layer_nur": "L_weg"},
                                 netz=[len(m.elements), m.nn])
    fehlt = w.ansicht_aufrufen("Alt")
    hinweise = " ".join(w.meldungen.hinweise)
    check("gelöschte Objekte: übersprungen und genannt (Fläche F99, 1 Element, Layer L_weg)",
          "Fläche F99" in hinweise and "1 Element" in hinweise and "Layer L_weg" in hinweise
          and w.versteckt["flaechen"] == {"M2"} and w.versteckt["elemente"] == {5}, hinweise[:160])
    m.ansichten["Netz"] = Ansicht(name="Netz", versteckt={"elemente": [5, 6]}, netz=[3, 4])
    w.meldungen.eintraege.clear()
    w.ansicht_aufrufen("Netz")
    hinweise = " ".join(w.meldungen.hinweise)
    check("… ein neues Netz: Elementnummern übersprungen und gesagt warum",
          "Netz seither geändert" in hinweise and not w.versteckt["elemente"], hinweise[:120])
    del m.ansichten["Alt"], m.ansichten["Netz"]
    w.alles_zeigen()


# --------------------------------------------------------------------------
# 3. Modellbaum und Ribbon
# --------------------------------------------------------------------------
def _baumzeile(w, art, name=None):
    from PySide6 import QtCore
    for it in w.baum.findItems("*", QtCore.Qt.MatchWildcard | QtCore.Qt.MatchRecursive):
        a, n = w.baum._schluessel(it)
        if a == art and (name is None or n == name):
            return it
    return None


def test_baum_und_ribbon():
    w, app = _fenster()
    m = w.model
    w._refresh_baum()
    zweig = _baumzeile(w, "ansichten")
    eltern = zweig.parent().text(0) if zweig is not None and zweig.parent() is not None else ""
    check("Modellbaum: Zweig „Ansichten“ unter „Hilfsobjekte“",
          zweig is not None and zweig.text(0) == "Ansichten" and eltern == "Hilfsobjekte", eltern)
    check("… mit dem Eintrag „Detail oben“ und der Zeile „+ Ansicht speichern“",
          _baumzeile(w, "ansicht", "Detail oben") is not None and _baumzeile(w, "ansicht_neu") is not None)
    soll = _kamera(w)
    w.blickrichtung("+y")
    w._baum_geklickt("ansicht", "Detail oben")
    app.processEvents()
    check("Klick auf die Ansicht im Baum ruft sie auf (Kamera wie gespeichert)",
          _gleiche_kamera(_kamera(w), soll))
    n0 = len(m.ansichten)
    w._baum_geklickt("ansicht_neu", "")
    app.processEvents()
    check("„+ Ansicht speichern“ speichert die jetzige Ansicht als „Ansicht 1“",
          len(m.ansichten) == n0 + 1 and "Ansicht 1" in m.ansichten, str(list(m.ansichten)))
    w.act_ansicht_speichern.trigger()
    app.processEvents()
    check("Ribbon Ansicht → Sicht ▾ → „Ansicht speichern“ legt „Ansicht 2“ an",
          "Ansicht 2" in m.ansichten, str(list(m.ansichten)))
    # Neu-Maske: erst OK speichert
    n1 = len(m.ansichten)
    w._baum_neu("ansichten")
    app.processEvents()
    mk = w.maskenrand.maske
    check("Rechtsklick „Neu: Ansicht …“: rechts die Anlegemaske, noch nichts gespeichert",
          mk is not None and mk.titel == "Neu: Ansicht" and len(m.ansichten) == n1
          and w.baum.NEU_ARTEN.get("ansichten") == "Ansicht", getattr(mk, "titel", None))
    mk.setzen("name", "Mit Auswahl")
    mk.setzen("auswahl", True)
    w.selection = np.array([3, 4], int)
    mk.angewendet.emit(mk.werte())
    app.processEvents()
    a = m.ansichten.get("Mit Auswahl")
    check("… OK speichert, wahlweise mit der Auswahl", a is not None and a.auswahl.get("knoten") == [3, 4],
          str(a.auswahl if a else None))
    # Umbenennen ueber die Maske des Eintrags (Doppelklick)
    w._baum_bearbeiten("ansicht", "Ansicht 1")
    app.processEvents()
    mk = w.maskenrand.maske
    check("Doppelklick auf eine Ansicht: ihre Maske (Name, Bemerkung, Aufrufen, In den Bericht)",
          mk is not None and mk.titel == "Ansicht Ansicht 1"
          and {"Aufrufen", "Überschreiben", "In den Bericht"} <= set(mk.zusatzknoepfe),
          getattr(mk, "titel", None))
    platz = list(m.ansichten).index("Ansicht 1")
    w._maske_ansicht_anwenden("Ansicht 1", {"name": "Draufsicht", "kommentar": "von oben"})
    app.processEvents()
    check("… umbenennen: „Ansicht 1“ heißt „Draufsicht“, die Reihenfolge bleibt",
          "Draufsicht" in m.ansichten and "Ansicht 1" not in m.ansichten
          and m.ansichten["Draufsicht"].name == "Draufsicht"
          and m.ansichten["Draufsicht"].kommentar == "von oben"
          and list(m.ansichten).index("Draufsicht") == platz, str(list(m.ansichten)))
    w._baum_loeschen("ansicht", "Ansicht 2")
    app.processEvents()
    check("Löschen im Baum (Rechtsklick/Entf): weg",
          "Ansicht 2" not in m.ansichten and "ansicht" in w.baum.LOESCH_ARTEN, str(list(m.ansichten)))


# --------------------------------------------------------------------------
# 4. Berichtsbild
# --------------------------------------------------------------------------
def test_berichtsbild():
    from statik3d.gui import viewport as vp
    w, app = _fenster()
    m = w.model
    if "Detail oben" not in m.ansichten:
        check("Berichtsbild (Ansicht „Detail oben“ fehlt)", False)
        return
    aufnahmen = []

    def foto(pfad, *a, **k):
        ren = w.plotter.renderer
        aw = getattr(ren, "axes_widget", None)
        aufnahmen.append({"kamera": _kamera(w), "achsen": aw is not None and bool(aw.GetEnabled()),
                          "ausschnitt": tuple(aw.GetViewport()) if aw is not None else None,
                          "box": w.schnittbox_grenzen()})
        open(pfad, "wb").write(b"PNG-Probe")
    w.plotter.screenshot = foto
    try:
        w.blickrichtung("-x")
        n = len(m.bericht)
        w.ansicht_in_bericht(ansicht="Detail oben")
        app.processEvents()
        soll = m.ansichten["Detail oben"]
        a0 = aufnahmen[-1] if aufnahmen else {}
        check("Berichtsbild aus der gespeicherten Ansicht: aufgenommen mit ihrer Kamera und Box",
              len(m.bericht) == n + 1 and a0 and np.allclose(a0["kamera"][0], soll.kamera["position"])
              and a0["box"] == tuple(soll.schnitt["box"]), str(a0.get("box")))
        check("… die Bildunterschrift nennt die Ansicht", "Ansicht Detail oben" in m.bericht[-1].beschriftung,
              m.bericht[-1].beschriftung)
        # Neu: Berichtsbild mit Auswahl der Ansicht
        w.berichtsbild_neu()
        app.processEvents()
        mk = w.maskenrand.maske
        werte = []
        if mk is not None and "ansicht" in getattr(mk, "_felder", {}):
            cb = mk._felder["ansicht"]
            werte = [cb.itemText(i) for i in range(cb.count())] if hasattr(cb, "itemText") else []
        check("„Neu: Berichtsbild“ bietet die gespeicherten Ansichten an",
              "Detail oben" in werte and w.BERICHT_JETZT in werte, str(werte))
        if mk is not None and werte:
            w.blickrichtung("+x")
            mk.setzen("ansicht", "Detail oben")
            mk.angewendet.emit(mk.werte())
            app.processEvents()
            check("… mit OK: das Bild zeigt diese Ansicht",
                  np.allclose(aufnahmen[-1]["kamera"][0], soll.kamera["position"]))
    finally:
        del w.plotter.screenshot


# --------------------------------------------------------------------------
# 5. Schnittbox und Werte auf dem Schnitt
# --------------------------------------------------------------------------
def _pruef_feld(X):
    X = np.asarray(X, float)
    return 1.5 * X[:, 0] - 2.0 * X[:, 1] + 0.7 * X[:, 2] + 3.0


def _ergebnis_auf_schnitt(w, app, was: str):
    """Pruef-Feld (linear) und Verschiebung an den gezeichneten Punkten."""
    from statik3d.gui import viewport as vp
    import pyvista as pv
    m = w.model
    alt = vp.result_field
    vp.result_field = lambda mm, r, field, *a, **k: (_pruef_feld(mm.nodes), None, "Prüffeld [-]")
    try:
        w.redraw()
        app.processEvents()
    finally:
        vp.result_field = alt
    grid, kidx = _gitter(w)
    akt = w.plotter.renderer.actors.get("result_netz")
    if akt is None:
        return check(f"{was}: Ergebnisdarsteller „result_netz“ fehlt", False,
                     f"{sorted(w.plotter.renderer.actors)[:12]} veraltet={getattr(w, '_ergebnis_veraltet', None)} "
                     f"an={w.ergebnisse_sichtbar()} {w._aktuelle_quelle()} | {w.log.toPlainText()[-300:]}")
    ds = akt.GetMapper().GetInput()
    import pyvista as _pv
    ds = _pv.wrap(ds)
    werte = np.asarray(ds.point_data["Prüffeld [-]"], float) if "Prüffeld [-]" in ds.point_data else None
    P = np.asarray(grid.points, float)
    # lineares Feld: exakt bis auf die einfache Genauigkeit der Schnittpunkte
    ok_f = werte is not None and len(werte) == len(P) and np.abs(werte - _pruef_feld(P)).max() < 1e-5
    check(f"{was}: auf dem Schnitt die richtigen Farbwerte (lineares Feld exakt, {len(P)} Punkte)",
          ok_f, f"max. Abweichung {np.abs(werte - _pruef_feld(P)).max():.3g}" if werte is not None
          and len(werte) == len(P) else "keine Werte")
    # Verschiebung: gegen die Probe von VTK im ungeschnittenen Netz
    r = w.current_result()
    u = np.asarray(r.u, float)[:, :3] if hasattr(r, "u") else None
    s = float(getattr(w, "_ueberhoehung_faktor", 0.0) or 0.0)
    if u is not None and s:
        g0 = vp.to_grid(m)
        g0.point_data["u"] = u
        probe = pv.PolyData(P).sample(g0, tolerance=1e-9)
        u_p = np.asarray(probe.point_data["u"], float)
        d = np.asarray(ds.points, float) - P
        fehler = np.abs(d - s * u_p).max() / max(1e-30, s * np.abs(u).max())
        # die gezeichneten Punkte sind einfach genau (float32): ~1e-6 der Verformung;
        # eine falsche Knotenzuordnung laege bei der Groessenordnung 1
        check(f"{was}: Verformung der Schnittpunkte wie die VTK-Probe des ganzen Netzes",
              fehler < 1e-4, f"rel. Abweichung {fehler:.2e}")


def test_schnittbox():
    from statik3d.gui import schnitt as sn
    w, app = _fenster()
    w.schnitt_aus() if w.schnitt_aktiv() else None
    w.alles_zeigen() if any(w.versteckt.values()) else None
    w.darstellung_setzen("Voll")
    w.redraw()
    voll = _volle_flaechenzahl(w)
    check("ohne Schnitt: das ganze Modell (Zellen der Oberfläche)", int(_gitter(w)[0].n_cells) == voll,
          f"{_gitter(w)[0].n_cells} / {voll}")
    w.act_schnittbox.setChecked(True)
    app.processEvents()
    box = w.schnittbox_grenzen()
    X = np.asarray(w.model.nodes, float)
    check("Schnittbox an: anfangs um alles Sichtbare (1 % Luft), nichts weggeschnitten",
          box is not None and all(box[2 * k] < X[:, k].min() and box[2 * k + 1] > X[:, k].max() for k in range(3))
          and int(_gitter(w)[0].n_cells) == voll, str(box))
    mk = w.maskenrand.maske
    check("… rechts die Maske „Schnittbox“ mit dem Bereich (x … , y … , z …)",
          mk is not None and mk.titel == "Schnittbox" and "x " in str(mk.werte().get("bereich", ""))
          and "z " in str(mk.werte().get("bereich", "")), str(mk.werte().get("bereich") if mk else None))
    b = [0.2, 0.8, 0.15, 0.85, 0.3, 0.7]
    w.schnittbox_setzen(b)
    grid, _k = _gitter(w)
    P = np.asarray(grid.points, float)
    # der Schnitt von VTK gibt die Punkte in einfacher Genauigkeit aus (~6e-8)
    t = 1e-6
    drin = ((P[:, 0] >= b[0] - t) & (P[:, 0] <= b[1] + t) & (P[:, 1] >= b[2] - t)
            & (P[:, 1] <= b[3] + t) & (P[:, 2] >= b[4] - t) & (P[:, 2] <= b[5] + t))
    check("Schnittbox: sichtbare Zellen nur innerhalb (jeder Punkt der Oberfläche in der Box)",
          grid.n_cells > 0 and drin.all(), f"{grid.n_cells} Zellen, {int((~drin).sum())} Punkte außen")
    check("… die Box schneidet bis an ihre Grenzen (die Oberfläche reicht an alle sechs Seiten)",
          np.allclose(grid.bounds, b, atol=1e-6), str(np.round(grid.bounds, 6).tolist()))
    _ergebnis_auf_schnitt(w, app, "Schnittbox")
    # Mindestrest
    m_ = w.schnittbox.modellgrenzen()
    b2 = sn.seite_setzen(b, "x+", -5.0, m_)
    check("Eine Seite lässt sich nicht über die andere ziehen: es bleibt 1 % Rest",
          abs(b2[1] - (b[0] + sn.REST * (m_[1] - m_[0]))) < 1e-12, str(b2[:2]))
    # Griffe ziehen
    _griffe_ziehen(w, app)
    # Schnittebene: dieselben richtigen Werte (bis 14.10.2026 falsch)
    w.schnitt_aus()
    w.cb_schnittachse.setCurrentText("x")
    w.sl_schnitt.setValue(37)
    w.act_schnitt.setChecked(True)
    app.processEvents()
    _ergebnis_auf_schnitt(w, app, "Schnittebene x")
    # Schnitt aus
    w.schnittbox_setzen([0.2, 0.8, 0.15, 0.85, 0.3, 0.7])
    check("Ebene und Box zusammen: „Schnitt aus“ ist bedienbar", w.act_schnitt_aus.isEnabled())
    w.act_schnitt_aus.trigger()
    app.processEvents()
    check("„Schnitt aus“: keine Ebene, keine Box, beide Haken weg, das ganze Modell wieder im Bild",
          w.schnitt is None and w.schnittbox_grenzen() is None and not w.act_schnitt.isChecked()
          and not w.act_schnittbox.isChecked() and int(_gitter(w)[0].n_cells) == voll
          and not w.act_schnitt_aus.isEnabled() and "schnittbox_rahmen" not in w.plotter.renderer.actors,
          f"{_gitter(w)[0].n_cells} / {voll}")


def _maus(app, wid, typ, pos, knopf, knoepfe):
    from PySide6 import QtCore, QtGui
    pos = QtCore.QPointF(pos)
    ev = QtGui.QMouseEvent(typ, pos, QtCore.QPointF(wid.mapToGlobal(pos.toPoint())),
                           knopf, knoepfe, QtCore.Qt.NoModifier)
    app.sendEvent(wid, ev)


def _rad(app, wid, pos, grad=120):
    from PySide6 import QtCore, QtGui
    pos = QtCore.QPointF(pos)
    ev = QtGui.QWheelEvent(pos, QtCore.QPointF(wid.mapToGlobal(pos.toPoint())), QtCore.QPoint(0, 0),
                           QtCore.QPoint(0, grad), QtCore.Qt.NoButton, QtCore.Qt.NoModifier,
                           QtCore.Qt.NoScrollPhase, False)
    app.sendEvent(wid, ev)


def _qt_punkt(w, P):
    """Qt-Bildpunkt eines Weltpunkts (Umkehrung von MainWindow._qt_nach_vtk)."""
    from PySide6 import QtCore
    ren = w.plotter.renderer
    ren.SetWorldPoint(float(P[0]), float(P[1]), float(P[2]), 1.0)
    ren.WorldToDisplay()
    x, y = ren.GetDisplayPoint()[:2]
    s = w._pixelmass()
    h = w.plotter.interactor.height()
    return QtCore.QPointF(x / s, h - 1 - y / s)


def _griffe_ziehen(w, app):
    from PySide6 import QtCore
    from statik3d.gui import schnitt as sn
    ia = w.plotter.interactor
    s = w._pixelmass()
    w.plotter.render_window.SetSize(int(ia.width() * s), int(ia.height() * s))
    w.blickrichtung("iso")
    app.processEvents()
    b0 = list(w.schnittbox_grenzen())
    G = sn.griffe(b0)["x+"]
    start = _qt_punkt(w, G)
    ziel = _qt_punkt(w, G + np.array([-0.2, 0.0, 0.0]))
    zeichnen = []
    alt = w.redraw
    w.redraw = lambda *a, **k: (zeichnen.append(1), alt(*a, **k))
    kam0 = _kamera(w)
    try:
        _maus(app, ia, QtCore.QEvent.MouseButtonPress, start, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        druck_zug = w.schnittbox._zug is not None
        for k in range(1, 6):
            p = start + (ziel - start) * (k / 5.0)
            _maus(app, ia, QtCore.QEvent.MouseMove, p, QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
        waehrend = list(w.schnittbox_grenzen())
        n_zeichnen = len(zeichnen)
        _maus(app, ia, QtCore.QEvent.MouseButtonRelease, ziel, QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        app.processEvents()
    finally:
        w.redraw = alt
    b1 = list(w.schnittbox_grenzen())
    check("Griff „x+“ gezogen: nur diese Seite folgt der Maus (um 0,2 m nach innen)",
          druck_zug and abs(b1[1] - (b0[1] - 0.2)) < 2e-3 and b1[0] == b0[0] and b1[2:] == b0[2:],
          f"{np.round(b0, 4).tolist()} -> {np.round(b1, 4).tolist()}")
    check("… beim Ziehen nur Rahmen und Griffe nachgezogen, geschnitten beim Loslassen (einmal)",
          n_zeichnen == 0 and len(zeichnen) == 1 and waehrend[1] < b0[1], f"{n_zeichnen} / {len(zeichnen)}")
    check("… das Ziehen am Griff dreht die Ansicht nicht", _gleiche_kamera(_kamera(w), kam0))
    grid, _k = _gitter(w)
    check("… danach endet das Bild an der neuen Seite", abs(grid.bounds[1] - b1[1]) < 1e-6,
          f"{grid.bounds[1]:.4f} / {b1[1]:.4f}")
    # Mausrad ueber einem Griff: fein schieben, nicht zoomen
    G = sn.griffe(b1)["z-"]
    p = _qt_punkt(w, G)
    m_ = w.schnittbox.modellgrenzen()
    _rad(app, ia, p, 120)
    b2 = list(w.schnittbox_grenzen())
    schritt = sn.RADSCHRITT * (m_[5] - m_[4])
    check("Mausrad über dem Griff „z-“: die Seite rückt fein nach außen (0,5 % der Höhe), kein Zoom",
          abs(b2[4] - (b1[4] - schritt)) < 1e-12 and _gleiche_kamera(_kamera(w), kam0),
          f"{b1[4]:.5f} -> {b2[4]:.5f}")
    _rad(app, ia, p, -240)
    b3 = list(w.schnittbox_grenzen())
    check("… zurückgedreht nach innen", abs(b3[4] - (b2[4] + 2 * schritt)) < 1e-12)
    # offscreen gibt es keinen Tiefenpuffer (test_ansicht_gizmo): der Zoom nimmt
    # dann den Punkt in der Brennebene
    alt_tief = w._oberflaeche_unter_zeiger
    w._oberflaeche_unter_zeiger = lambda x, y: None
    try:
        _rad(app, ia, QtCore.QPointF(5, 5), 120)
    finally:
        w._oberflaeche_unter_zeiger = alt_tief
    check("Mausrad neben den Griffen zoomt wie immer, die Box bleibt",
          list(w.schnittbox_grenzen()) == b3 and not _gleiche_kamera(_kamera(w), kam0))
    app.processEvents()


def main():
    tests = [test_datei, test_speichern_aufrufen, test_geloeschte_objekte, test_baum_und_ribbon,
             test_berichtsbild, test_schnittbox]
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} lief durch", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    sys.stdout.flush()
    os._exit(0 if n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
