"""
Oberflaechenpaket B (Bestellung des Anwenders vom 08.11.2026): Lasten.

Anlass: „ich habe gerade -5kn/m2 als flächenlast augetragen und z-achse zeigt
nach oben und die fläche verformt sich nach oben; das ist verwirrend; p sollte
global und lokal einstellbar sein; es sollte n eigene koordinatensysteme
anlegbar sein auf welche auch die lasten bezogen werden können; die Lasten
müssen viel deutlicher im viewport erkennbar sein so dass der user optisch
prüfen kann und es druckfähig ist für die doku“.

0. Ursache: ohne Bezug wirkt die Flaechenlast senkrecht zur Flaeche, bei einer
   Schale in Richtung der Elementnormalen - und die folgt dem Umlauf der
   Randlinien. Die Ansicht zeigte die Pfeile bei Schalen gegen die Normale,
   also entgegen der Rechnung.
1. Lastbezug je Last: global, lokal, eigenes Koordinatensystem; Vorgabe der
   Maske global Z mit -5 kN/m². Alte Dateien bleiben Zeichen fuer Zeichen und
   im Lastvektor gleich (tests/daten/lastbezug_2a969a9, erzeugt auf 2a969a9).
2. Lokale Flaechenachsen anzeigbar (Ansicht → Anzeigen → Flächenachsen).
3. Eigene Koordinatensysteme im Modellbaum unter Eigenschaften, Maske rechts,
   Loeschen nur ohne Verweis.
4. Druckfaehige Lastdarstellung: Pfeilfeld, Umriss, Pfeilreihe mit Linie, je
   Lastart eigener Massstab, „Lasten beschriften“ mit Einheit und Komma.

Aufruf:  python -m tests.test_paket_b
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(tempfile.mkdtemp(prefix="statik3d_paket_b_"),
                                                    "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}
HIER = os.path.dirname(os.path.abspath(__file__))
ALT = os.path.join(HIER, "daten", "lastbezug_2a969a9")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _platten(m=None):
    """Zwei Platten 2 m x 1 m (S235, 10 mm): P1 mit dem Rand im Gegenuhrzeigersinn
    (Normale +Z), P2 im Uhrzeigersinn (Normale -Z), dazu die Linie G (0,2,0)-(4,2,0)."""
    from statik3d.model import Model, Material, ShellProp
    m = m or Model()
    if "S235" not in m.materials:
        m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01, "S235"))
    for dx, name, umlauf in ((0.0, "P1", (0, 1, 2, 3)), (3.0, "P2", (0, 3, 2, 1))):
        b = m.nn
        for p in ((0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)):
            m.add_node(p[0] + dx, p[1], p[2])
        linien = []
        for j in range(4):
            m.add_line(f"{name}L{j}", [b + umlauf[j], b + umlauf[(j + 1) % 4]])
            linien.append(f"{name}L{j}")
        m.add_flaeche(name, linien, material="S235", dicke="D10")
    a = m.add_node(0.0, 2.0, 0.0)
    b = m.add_node(4.0, 2.0, 0.0)
    m.add_line("G", [a, b])
    if "LF1" not in m.load_cases:
        m.add_load_case("LF1", "Q")
    return m


def _summe(m, fall="LF1"):
    from statik3d import solver
    F = np.asarray(solver.case_loads(m, {fall: 1.0}, None)[0], float)
    return F.reshape(-1, 6)[:, :3].sum(axis=0) if F.size == 6 * m.nn else F.reshape(-1, 3).sum(axis=0)


def _nur(m, gl_index, fall="LF1"):
    """Kraftsumme nur einer Geometrielast des Lastfalls."""
    import copy
    mm = copy.deepcopy(m)
    lc = mm.load_cases[fall]
    lc.geometrielasten = [lc.geometrielasten[gl_index]]
    lc.linienlasten = []
    mm.lasten_verteilen()
    return _summe(mm, fall)


# ---------------------------------------------------------------------------
# 0. Ursache
# ---------------------------------------------------------------------------
def test_ursache():
    from statik3d import mesher
    from statik3d.gui import viewport as vp
    m = _platten()
    m.add_geometrielast("P1", -5000.0, case="LF1")
    m.add_geometrielast("P2", -5000.0, case="LF1")
    mesher.modell_vernetzen(m, log=[])
    f1, f2 = _nur(m, 0), _nur(m, 1)
    check("Ursache: ohne Bezug wirkt −5 kN/m² bei Rand im Gegenuhrzeigersinn nach unten (−10 kN)",
          np.isclose(f1[2], -10000.0), f"F_z = {f1[2] / 1e3:.2f} kN")
    check("… und bei Rand im Uhrzeigersinn nach OBEN (+10 kN) - das sah der Anwender",
          np.isclose(f2[2], 10000.0), f"F_z = {f2[2] / 1e3:.2f} kN")
    # die Ansicht zeigt die Pfeile so, wie gerechnet wird
    lc = m.load_cases["LF1"]
    abgel = {}
    for fl in lc.face_loads:
        if getattr(fl, "_geo_quelle", None) is not None:
            abgel.setdefault(id(fl._geo_quelle), []).append(fl)
    try:
        ok = []
        for k, (gl, F) in enumerate(zip(lc.geometrielasten, (f1, f2))):
            feld = vp._pfeilfeld(m, gl, m.flaechen[gl.ziel], abgel.get(id(gl), []), None, None,
                                 m.characteristic_size(), 49)
            Vz = (feld[1][:, 2] * feld[2]) if feld is not None else np.zeros(1)
            ok.append(bool(len(Vz)) and np.all(np.sign(Vz) == np.sign(F[2])))
        check("Ansicht: die Pfeile beider Platten zeigen in die Richtung, mit der gerechnet wird "
              "(vorher bei Schalen gegen die Normale)", all(ok), str(ok))
    except AttributeError as ex:
        check("Ansicht: Pfeilrichtung wie gerechnet", False, repr(ex)[:80])


# ---------------------------------------------------------------------------
# 1. Lastbezug
# ---------------------------------------------------------------------------
def test_bezug_modell():
    from statik3d import mesher
    m = _platten()
    try:
        m.add_koordinatensystem("KS1", winkel=[90.0, 0.0, 0.0])
        m.add_geometrielast("P1", -5000.0, case="LF1", bezug="global", achse="z")     # 0
        m.add_geometrielast("P2", -5000.0, case="LF1", bezug="global", achse="z")     # 1
        m.add_geometrielast("P1", -5000.0, case="LF1", bezug="lokal", achse="z")      # 2
        m.add_geometrielast("P2", -5000.0, case="LF1", bezug="lokal", achse="z")      # 3
        m.add_geometrielast("P2", 2000.0, case="LF1", bezug="lokal", achse="x")       # 4
        m.add_geometrielast("P1", 1000.0, case="LF1", bezug="ks", achse="x", ks="KS1")  # 5
        m.add_linienlast("G", [0.0, 0.0, -3000.0], art="linie", case="LF1", ks="KS1")
    except TypeError as ex:
        check("Lastbezug im Modell (bezug, achse, ks; add_koordinatensystem)", False, repr(ex)[:80])
        return
    mesher.modell_vernetzen(m, log=[])
    s = [_nur(m, i) for i in range(6)]
    check("global Z, −5 kN/m²: beide Platten −10 kN, gleich welcher Randumlauf",
          np.allclose(s[0], [0, 0, -10000.0]) and np.allclose(s[1], [0, 0, -10000.0]),
          f"{s[0][2] / 1e3:.2f} / {s[1][2] / 1e3:.2f} kN")
    check("lokal z folgt der Flächennormalen: P1 (Normale +Z) −10 kN, P2 (Normale −Z) +10 kN",
          np.allclose(s[2], [0, 0, -10000.0]) and np.allclose(s[3], [0, 0, 10000.0]),
          f"{s[2][2] / 1e3:.2f} / {s[3][2] / 1e3:.2f} kN")
    check("lokal x = globale X in die Fläche projiziert: 2 kN/m² auf P2 sind +4 kN in X",
          np.allclose(s[4], [4000.0, 0, 0], atol=1e-6), str(np.round(s[4], 3)))
    check("eigenes KS (um Z 90° gedreht): 1 kN/m² in seiner x-Achse sind +2 kN in globaler Y",
          np.allclose(s[5], [0, 2000.0, 0], atol=1e-6), str(np.round(s[5], 3)))
    import copy
    mm = copy.deepcopy(m)
    mm.load_cases["LF1"].geometrielasten = []
    mm.lasten_verteilen()
    sl = _summe(mm)
    check("Linienlast in KS1: q_z = −3 kN/m auf 4 m sind −12 kN in Z (KS1 dreht nur um Z)",
          np.allclose(sl, [0, 0, -12000.0], atol=1e-6), str(np.round(sl, 3)))
    mm.koordinatensysteme["KS1"].winkel = [0.0, 0.0, 90.0]     # um x gedreht: z_KS = −Y
    mm.lasten_verteilen()
    sl = _summe(mm)
    check("… KS1 um x 90° gedreht: dieselbe Last wirkt +12 kN in Y (z_KS = −Y)",
          np.allclose(sl, [0, 12000.0, 0], atol=1e-6), str(np.round(sl, 3)))
    # Speichern und Laden
    from statik3d.model import Model
    d = m.to_dict()
    m2 = Model.from_dict(json.loads(json.dumps(d)))
    check("Speichern und Laden: Koordinatensystem, Bezug und Lastvektor bleiben",
          json.dumps(m2.to_dict(), sort_keys=True) == json.dumps(d, sort_keys=True)
          and np.allclose(_summe(m2), _summe(m)), str(list(m2.koordinatensysteme)))
    gl = d["load_cases"][-1]["geometrielasten"]
    check("Die Datei führt lastbezug/achse/ks nur bei Lasten mit Bezug",
          all(("lastbezug" in x) == bool(x.get("lastbezug")) for x in gl) and gl[0].get("lastbezug") == "global",
          str([x.get("lastbezug") for x in gl]))
    # drei Punkte
    try:
        k = m.add_koordinatensystem("KS2", art="punkte", ursprung=[1, 1, 0], punkt_x=[1, 3, 0], punkt_xy=[0, 1, 0])
        A = k.achsen()
        check("Koordinatensystem aus drei Punkten: x = +Y, y = −X, z = +Z",
              np.allclose(A, [[0, 1, 0], [-1, 0, 0], [0, 0, 1]], atol=1e-12), str(np.round(A, 6).tolist()))
        try:
            m.add_koordinatensystem("KS3", art="punkte", punkt_x=[1, 0, 0], punkt_xy=[2, 0, 0])
            check("Drei Punkte auf einer Geraden werden abgewiesen", False)
        except ValueError:
            check("Drei Punkte auf einer Geraden werden abgewiesen", "KS3" not in m.koordinatensysteme)
    except TypeError as ex:
        check("Koordinatensystem aus drei Punkten", False, repr(ex)[:80])


def test_alte_datei():
    """Eine Datei vom Stand 2a969a9 (vor dem Lastbezug) bleibt beim Speichern
    Zeichen fuer Zeichen gleich, und ihr Lastvektor ist derselbe."""
    from statik3d.model import Model
    from statik3d import solver
    m = Model.load(os.path.join(ALT, "alt.modell"))
    t = os.path.join(tempfile.mkdtemp(prefix="paket_b_"), "neu.json")
    m.save(t)
    with open(os.path.join(ALT, "alt.modell"), "rb") as f:
        a = f.read()
    with open(t, "rb") as f:
        b = f.read()
    check("Alte Datei (2a969a9): Laden und Speichern ergibt dieselbe Datei, Zeichen für Zeichen",
          a == b, f"{len(a)} / {len(b)} Bytes")
    F = np.asarray(solver.case_loads(m, {"LF1": 1.0}, None)[0], float)
    with open(os.path.join(ALT, "lastvektor.json"), encoding="utf-8") as f:
        F0 = np.asarray(json.load(f), float)
    check("… und derselbe Lastvektor (senkrecht, Richtung, projiziert, linear, Linien- und Stablast)",
          F.shape == F0.shape and np.allclose(F, F0, rtol=0, atol=1e-9),
          f"größte Abweichung {np.abs(F - F0).max() if F.shape == F0.shape else 'Form'} N")
    check("… keine der alten Lasten hat einen Bezug", not any(
        getattr(g, "lastbezug", "") for lc in m.load_cases.values() for g in lc.geometrielasten))


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
def _fenster():
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if "w" in _FENSTER:
        return _FENSTER["w"], app
    from statik3d.gui.main import MainWindow
    w = MainWindow()
    w.resize(1500, 900)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w._bestaetigen = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w)
    return w, app


def _ruhe(app, n=3):
    for _ in range(n):
        app.processEvents()


def _modell(w, app):
    from statik3d import mesher
    w.new_model()
    _platten(w.model)
    mesher.modell_vernetzen(w.model, log=[])
    w.refresh_all()
    w.maskenrand.schliessen()
    w.sel_flaechen, w.sel_linien = [], []
    w.fehler_liste.clear()
    _ruhe(app)
    return w.model


def _maske(w):
    return w.maskenrand.maske if w.maskenrand.offen() else None


def _baumzeilen(w):
    from PySide6 import QtCore, QtWidgets
    out = []
    it = QtWidgets.QTreeWidgetItemIterator(w.baum)
    while it.value():
        x = it.value()
        eltern = x.parent()
        out.append((str(x.data(0, QtCore.Qt.UserRole) or ""), x.text(0),
                    eltern.text(0) if eltern is not None else ""))
        it += 1
    return out


def test_maske_flaechenlast():
    w, app = _fenster()
    m = _modell(w, app)
    w.sel_flaechen = ["P1", "P2"]
    w.maske_flaechenlast()
    _ruhe(app)
    mk = _maske(w)
    v = mk.werte() if mk is not None else {}
    check("Maske Flächenlast: Vorgabe Bezug global, Achse z, p = −5 kN/m²",
          v.get("bezug") == "global" and v.get("achse") == "z" and abs(float(v.get("p", 0)) + 5.0) < 1e-12,
          str({k: v.get(k) for k in ("bezug", "achse", "p")}))
    if mk is None:
        return
    mk.anwenden()
    _ruhe(app)
    lc = m.case()
    gl = lc.geometrielasten
    check("… „Last aufbringen“ auf P1 und P2: zwei Lasten global Z",
          len(gl) == 2 and all(g.lastbezug == "global" and g.achse == "z" for g in gl),
          str([(g.ziel, g.lastbezug, g.achse) for g in gl]))
    s = _summe(m, lc.name)
    check("… beide wirken nach unten: zusammen −20 kN (2 × 2 m² × −5 kN/m²)",
          np.allclose(s, [0, 0, -20000.0]), f"F_z = {s[2] / 1e3:.2f} kN")
    w.undo()
    _ruhe(app)
    m = w.model                  # Rueckgaengig setzt ein Modell aus dem Stapel ein
    check("… Rückgängig nimmt beide zurück", not m.case().geometrielasten)
    w.maskenrand.schliessen()
    # aeltere Aufrufer (Feld „richtung“, ohne „bezug“) wie bisher
    w.sel_flaechen = ["P2"]
    w._flaechenlast_aufbringen({"p": -5.0, "richtung": "senkrecht zur Fläche (Druck)", "fall": lc.name})
    g = m.case().geometrielasten[-1]
    check("Aufruf ohne Feld „bezug“ (bisheriger Weg): Last ohne Bezug, wirkt wie bisher (+10 kN auf P2)",
          g.lastbezug == "" and g.richtung is None and np.isclose(_summe(m, lc.name)[2], 10000.0))
    # Maske der einzelnen Last: Bezug sichtbar, unveraendert uebernehmen aendert nichts
    w._lastmaske(lc.name, "geometrielasten", 0)
    _ruhe(app)
    mk = _maske(w)
    v = mk.werte() if mk is not None else {}
    check("Maske der Last zeigt den bisherigen Bezug „senkrecht zur Fläche (wie bisher …)“",
          str(v.get("bezug", "")).startswith("senkrecht zur Fläche (wie bisher"), str(v.get("bezug")))
    vorher = json.dumps(m.to_dict(netz=False)["load_cases"], sort_keys=True)
    if mk is not None:
        mk.anwenden()
        _ruhe(app)
    check("… „Übernehmen“ ohne Änderung lässt die Last, wie sie war",
          json.dumps(m.to_dict(netz=False)["load_cases"], sort_keys=True) == vorher)
    mk = _maske(w)
    if mk is not None:
        mk.setzen("bezug", "global")
        mk.anwenden()
        _ruhe(app)
    g = m.case().geometrielasten[0]
    check("… auf „global“ umgestellt: Bezug global Z, wirkt −10 kN",
          g.lastbezug == "global" and np.isclose(_summe(m, lc.name)[2], -10000.0), f"{g.lastbezug!r}")
    w.maskenrand.schliessen()


def test_koordinatensysteme_baum():
    w, app = _fenster()
    m = _modell(w, app)
    zeilen = _baumzeilen(w)
    check("Modellbaum: „Koordinatensysteme“ unter „Eigenschaften“",
          ("koordinatensysteme", "Koordinatensysteme", "Eigenschaften") in zeilen,
          str([z for z in zeilen if z[2] == "Eigenschaften"]))
    check("… mit der Zeile „+ Koordinatensystem anlegen“",
          ("koordinatensystem_neu", "+ Koordinatensystem anlegen", "Koordinatensysteme") in zeilen)
    w._baum_geklickt("koordinatensystem_neu", "+ Koordinatensystem anlegen")
    _ruhe(app)
    mk = _maske(w)
    check("Klick darauf öffnet rechts „Neu: Koordinatensystem KS1“, ohne anzulegen",
          mk is not None and mk.titel == "Neu: Koordinatensystem KS1" and not m.koordinatensysteme,
          repr(getattr(mk, "titel", None)))
    if mk is None:
        return
    mk.setzen("art", "drei Punkte")
    for k, x in (("ox", 1.0), ("oy", 0.0), ("oz", 0.0), ("pxx", 1.0), ("pxy", 5.0), ("pxz", 0.0),
                 ("pex", 0.0), ("pey", 0.0), ("pez", 0.0)):
        mk.setzen(k, x)
    mk.anwenden()
    _ruhe(app)
    k = m.koordinatensysteme.get("KS1")
    check("OK legt KS1 an: x = +Y, y = −X, z = +Z (Ursprung (1, 0, 0), Punkt auf x (1, 5, 0), "
          "Punkt in xy (0, 0, 0))",
          k is not None and np.allclose(k.achsen(), [[0, 1, 0], [-1, 0, 0], [0, 0, 1]], atol=1e-12),
          str(None if k is None else np.round(k.achsen(), 6).tolist()))
    check("… und steht im Baum", ("koordinatensystem", "KS1", "Koordinatensysteme") in _baumzeilen(w))
    # Flaechenlast in KS1 ueber die Maske
    w.sel_flaechen = ["P1"]
    w.maske_flaechenlast()
    _ruhe(app)
    mk = _maske(w)
    wahlen = []
    if mk is not None:
        from PySide6 import QtWidgets
        cb = mk.findChildren(QtWidgets.QComboBox)
        wahlen = [c.itemText(i) for c in cb for i in range(c.count())]
    check("Die Maske Flächenlast bietet KS1 als Bezug an", "KS1 (eigenes KS)" in wahlen, str(wahlen[:8]))
    if mk is not None:
        mk.setzen("bezug", "KS1 (eigenes KS)")
        mk.setzen("achse", "x")
        mk.setzen("p", 1.0)
        mk.anwenden()
        _ruhe(app)
    g = m.case().geometrielasten
    check("… die Last bezieht sich auf KS1 und wirkt +2 kN in Y",
          len(g) == 1 and g[0].lastbezug == "ks" and g[0].ks == "KS1"
          and np.allclose(_summe(m, m.active_case), [0, 2000.0, 0], atol=1e-6),
          str(np.round(_summe(m, m.active_case), 3)))
    # Linienlast in KS1
    w.sel_flaechen, w.sel_linien = [], ["G"]
    w._linienlast_aufbringen({"qx": 0.0, "qy": 0.0, "qz": -1.0, "system": "KS1 (eigenes KS)",
                              "fall": m.active_case})
    ll = m.case().linienlasten
    check("Linienlast mit Bezug KS1 (Maske Linienlast)",
          len(ll) == 1 and ll[0].system == "ks" and ll[0].ks == "KS1", str([(x.system, x.ks) for x in ll]))
    # Loeschen mit Verweis: abgewiesen, Hinweis nennt die Lasten
    w.fehler_liste.clear()
    w._baum_loeschen("koordinatensystem", "KS1")
    _ruhe(app)
    text = " ".join(str(x) for x in w.fehler_liste)
    check("Löschen von KS1 mit zwei Lasten darauf: abgewiesen, der Hinweis nennt beide",
          "KS1" in m.koordinatensysteme and "Flächenlast P1" in text and "Linienlast G" in text, text[:120])
    # Umbenennen zieht die Verweise mit
    w._objektmaske("koordinatensystem", "KS1")
    _ruhe(app)
    mk = _maske(w)
    if mk is not None:
        mk.setzen("name", "Dach")
        mk.anwenden()
        _ruhe(app)
    check("Umbenennen in „Dach“: beide Lasten verweisen mit",
          "Dach" in m.koordinatensysteme and m.case().geometrielasten[0].ks == "Dach"
          and m.case().linienlasten[0].ks == "Dach")
    m.case().geometrielasten.clear()
    m.case().linienlasten.clear()
    w._baum_loeschen("koordinatensystem", "Dach")
    _ruhe(app)
    check("Ohne Verweis lässt es sich löschen", not m.koordinatensysteme)
    w.undo()
    _ruhe(app)
    check("… Rückgängig holt es zurück", "Dach" in w.model.koordinatensysteme)
    w.maskenrand.schliessen()


class _Aufnahme:
    """Ein Plotter, der nur mitschreibt (add_mesh, add_point_labels)."""
    def __init__(self):
        self.netze, self.texte = {}, {}

    def add_mesh(self, netz, name="", **k):
        self.netze[name] = (netz, k)

    def add_point_labels(self, punkte, texte, name="", **k):
        self.texte[name] = (np.asarray(punkte, float), list(texte), k)

    def __getattr__(self, n):
        return lambda *a, **k: None


def test_lastbild():
    from statik3d import mesher
    from statik3d.gui import viewport as vp
    m = _platten()
    m.add_geometrielast("P1", -2500.0, case="LF1", bezug="global", achse="z")
    m.add_linienlast("G", [0.0, 0.0, -4000.0], art="linie", case="LF1")
    k = m.nn
    m.add_node(8.0, 0.0, 0.0)
    m.load_node(k, Fz=-100000.0)
    mesher.modell_vernetzen(m, log=[])
    size = m.characteristic_size()
    p = _Aufnahme()
    vp.add_loads(p, m, m.case("LF1"), size, beschriften=True, merker=[])
    texte = p.texte.get("lastwerte", (None, []))[1]
    check("Lasten beschriften: Flächenlast mit Vorzeichen, Komma, Einheit und Bezug „−2,5 kN/m² (global Z)“",
          "−2,5 kN/m² (global Z)" in texte, str(texte))
    check("… Linienlast „4 kN/m“, Knotenlast „100 kN“ mit Einheit",
          "4 kN/m" in texte and "100 kN" in texte, str(texte))
    check("… nirgends wissenschaftliche Schreibweise", not any("e+" in t or "e-" in t for t in texte))
    lab = p.texte.get("lastwerte", (None, [], {}))[2]
    check("… auf weißem Feld (für Druck und Bildexport)",
          lab.get("shape") == "rounded_rect" and lab.get("shape_color") == "white", str(lab)[:80])
    # je Lastart eigener Massstab: die Lastflaeche von 2,5 kN/m² steht um die volle
    # Pfeillaenge ueber der Platte, obwohl 100 kN am Knoten haengen
    fl = p.netze.get("flaechenlasten", (None,))[0]
    hoehe = float(np.asarray(fl.points)[:, 2].mean()) if fl is not None else 0.0
    soll = getattr(vp, "LASTPFEIL_LAENGE", -1) * size
    check("Je Lastart eigener Maßstab: Lastfläche 2,5 kN/m² volle Pfeillänge über der Platte "
          "(trotz 100 kN Knotenlast)", np.isclose(hoehe, soll, rtol=1e-9) and soll > 0,
          f"{hoehe:.4f} m gegen {soll:.4f} m")
    check("Umriss der Lastfläche als Linie und Linie an den Pfeilenden der Linienlast",
          "lastumriss" in p.netze and "lastlinien" in p.netze, str(sorted(p.netze)))
    pk = p.netze.get("loads", (None,))[0]
    n_pfeile = sum(1 for x in vp._pfeilfeld(m, m.case("LF1").geometrielasten[0], m.flaechen["P1"],
                                            [f for f in m.case("LF1").face_loads
                                             if getattr(f, "_geo_quelle", None) is m.case("LF1").geometrielasten[0]],
                                            None, None, size, 49)[0]) if hasattr(vp, "_pfeilfeld") else 0
    check("Flächenlast als Pfeilfeld über die Fläche (mehr als ein Pfeil je Element-/Vieleckmitte)",
          pk is not None and n_pfeile >= 20, f"{n_pfeile} Pfeile auf P1")


def test_flaechenachsen():
    w, app = _fenster()
    m = _modell(w, app)
    a = getattr(w, "act_flaechenachsen", None)
    check("Ansicht → Anzeigen: Schalter „Flächenachsen“, aus als Vorgabe",
          a is not None and a.text() == "Flächenachsen" and not a.isChecked())
    if a is None:
        return
    a.setChecked(True)
    _ruhe(app)
    akt = dict(w.plotter.renderer.actors)
    check("… an: Pfeile x, y, z je Fläche und die Buchstaben",
          all(f"flaechenachsen_{c}" in akt for c in "xyz"), str([k for k in akt if "achsen" in k]))
    from statik3d.lastbezug import flaechenachsen_bild
    z1, z2 = flaechenachsen_bild(m, m.flaechen["P1"])[3], flaechenachsen_bild(m, m.flaechen["P2"])[3]
    check("… z von P1 zeigt nach +Z, von P2 nach −Z (so rechnet „lokal z“)",
          np.allclose(z1, [0, 0, 1]) and np.allclose(z2, [0, 0, -1]), f"{z1} {z2}")
    a.setChecked(False)
    _ruhe(app)
    check("… aus: weg", not any(k.startswith("flaechenachsen") for k in w.plotter.renderer.actors))
    check("Schalter „Lasten beschriften“ (bisher „Lastwerte“)", w.act_lastwerte.text() == "Lasten beschriften")


def test_bilder():
    """Zwei Bildschirmfotos der Lastdarstellung fuer den Bericht (keine Pruefung
    ausser: geschrieben). Ziel: STATIK3D_PAKET_B_BILDER, sonst nichts."""
    ziel = os.environ.get("STATIK3D_PAKET_B_BILDER")
    if not ziel:
        return
    from statik3d import mesher
    w, app = _fenster()
    m = _modell(w, app)
    m.add_koordinatensystem("KS1", winkel=[30.0, 0.0, 0.0])
    m.add_geometrielast("P1", -5000.0, bezug="global", achse="z")
    m.add_geometrielast("P2", 2500.0, bezug="lokal", achse="z")
    m.add_linienlast("G", [0.0, -2000.0, -3000.0], art="linie", ks="KS1")
    m.load_node(int(m.lines["G"].nodes[1]), Fz=-20000.0)
    mesher.modell_vernetzen(m, log=[])
    w.resize(1900, 1250)
    w.refresh_all()
    w.act_flaechenachsen.setChecked(True)
    _ruhe(app, 6)
    w.blickrichtung("iso") if hasattr(w, "blickrichtung") else None
    try:
        w.zoom_alles()
    except Exception:            # noqa: BLE001
        pass
    _ruhe(app, 6)
    os.makedirs(ziel, exist_ok=True)
    w.plotter.screenshot(os.path.join(ziel, "paket_b_lasten_iso.png"))
    w.act_flaechenachsen.setChecked(False)
    try:
        w.blickrichtung("-y")
        w.zoom_alles()
    except Exception:            # noqa: BLE001
        pass
    _ruhe(app, 6)
    w.plotter.screenshot(os.path.join(ziel, "paket_b_lasten_vorn.png"))
    check("Bildschirmfotos geschrieben", os.path.exists(os.path.join(ziel, "paket_b_lasten_iso.png")))


def test_handbuch():
    from tests.handbuch import absatz
    a = absatz("**Lastbezug: global, lokal oder eigenes Koordinatensystem.**")
    check("Handbuch: Lastbezug, Vorgabe global Z, eigene Koordinatensysteme, alte Dateien",
          "global Z" in a and "Koordinatensystem" in a and "Zeichen für Zeichen" in a, a[:80])
    b = absatz("**Lasten im Bild, druckfähig.**")
    check("Handbuch: Pfeilfeld, eigener Maßstab je Lastart, Lasten beschriften",
          "Pfeilfeld" in b and "Maßstab" in b and "Lasten beschriften" in b, b[:80])


def main():
    for t in (test_ursache, test_bezug_modell, test_alte_datei, test_lastbild, test_maske_flaechenlast,
              test_koordinatensysteme_baum, test_flaechenachsen, test_bilder, test_handbuch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    w = _FENSTER.get("w")
    if w is not None:
        w.close()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
