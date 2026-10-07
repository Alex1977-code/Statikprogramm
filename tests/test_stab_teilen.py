"""
Teilen eines Stabelements: Gelenke und Elementlasten bleiben, wo sie waren
(Nachpruefung von C14, 06.10.2026).

„Freie Stabenden anschließen…“ (hicad_szn.an_staebe_anschliessen) teilt das
Element, auf dessen Achse ein freies Stabende trifft, und meldet die Teilung
an Model.stabelement_geteilt. Bis zum 06.10.2026 blieb dabei alles am alten,
verkuerzten Element haengen:

* ein Gelenk an seinem Ende wanderte an die Teilstelle (am Ende von E1 bei
  x = 6 m, danach bei x = 4 m), und das neue Element bekam keins;
* eine Elementlast (load_beam) wirkte nur noch auf dem verkuerzten Teil
  (Summe der Auflagerkraefte z 82000 statt 84000 N).

Jeder Fall teilt E1 eines 8-m-Balkens bei x = 4 m und vergleicht danach
Verschiebungen, Auflagerkraefte und Schnittgroessen an den alten Orten mit
dem Stand vor dem Teilen (1e-9 relativ). Der Querstab, der die Teilung
ausloest, haengt danach unbelastet als Kragarm am Balken und aendert dort
nichts. Die meisten Faelle rechnen ohne Schubflaechen; test_mit_schubflaechen
wiederholt die Lastfaelle mit dem HEB 200 samt Schubflaechen. Bis zum
07.10.2026 folgten die Ersatzknotenlasten einer Trapez- oder Teillast dort den
Bernoulli-Ansatzfunktionen, die Steifigkeit aber der Schubverformung, und
schon ein zusaetzlicher Knoten aenderte die Rechnung (N01 nennt bis 3e-3; die
Faelle dieser Suite mit Schubflaechen am 07.10.2026 bis 2,0e-3 in u; Nachtrag
N01, tests/test_nachtrag_q3.py). Die Summe der
Auflagerkraefte blieb auch dann; das prueft der Fall mit HEB 200 samt
Schubflaechen.

Aufruf:  python -m tests.test_stab_teilen
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_stab_teilen_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
MAT, SEC = "S355", "HEB 200"
TOL = 1e-9
#: Stellen entlang der Balkenachse [m], an denen die Schnittgroessen verglichen werden
STELLEN = [float(x) for x in np.arange(0.0, 8.0 + 1e-9, 0.25)] + [3.9995, 4.0005, 4.9995, 5.0005]


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
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _balken(querstab, m=None, *, schub=False, umgekehrt=False, roll=0.0, gelenk=None,
            lasten=(), linienlast=False, querstab_fest=False):
    """Balken 8 m: Stab S1 aus E0 (0-2 m), E1 (2-6 m) und E2 (6-8 m),
    eingespannt bei x = 0, bei x = 8 m quer gehalten.

    ``querstab``: dazu ein Querstab, dessen eines Ende 5 mm neben der Achse bei
    x = 4 m endet - „Freie Stabenden anschließen…“ teilt E1 dort. Sein anderes
    Ende ist frei (``querstab_fest``: eingespannt), er bekommt keine Last.
    ``umgekehrt``: E1 laeuft gegen den Stab, von x = 6 nach x = 2 m.
    ``gelenk``: (Ende von E1 0/1, {FHG: "free" oder Federsteifigkeit}).
    ``lasten``: Elementlasten auf E1 (Schluesselwoerter fuer load_beam).
    ``linienlast``: Linienlast des Stabs S1 (sie ging schon richtig mit, C14 G4).
    """
    from statik3d.model import Model, Material, Section
    m = m if m is not None else Model("Teilen")
    m.add_material(Material.steel(MAT))
    m.add_section(Section.from_profile(SEC))
    if not schub:
        m.sections[SEC].Asy = 0.0
        m.sections[SEC].Asz = 0.0
    for x in (0, 2, 6, 8):
        m.add_node(x, 0, 0)
    m.support(0, "all")
    m.support(3, [1, 2, 3])
    g = next(iter(m.load_cases))
    e1 = [2, 1] if umgekehrt else [1, 2]
    els = [m.add_element("beam", ab, MAT, SEC) for ab in ([0, 1], e1, [2, 3])]
    m.elements[1].roll = float(roll)
    m.add_member("S1", els)
    if gelenk:
        ende, fhg = gelenk
        m.add_hinge("G1", end=ende, **fhg)
        m.apply_hinge(1, "G1")
    for kw in lasten:
        m.load_beam(1, case=g, **kw)
    if linienlast:
        m.add_linienlast("S1", [0, -3e3, -10e3], case=g)
        m.lasten_verteilen()
    if querstab:
        a = m.add_node(4, 0.005, 0)
        b = m.add_node(4, 3, 0)
        if querstab_fest:
            m.support(b, "all")
        m.add_element("beam", [b, a], MAT, SEC)
    return m, g


def _schnitt(m, r, p):
    """Schnittgroessen am Punkt p der Balkenachse als globale Vektoren (F, M)
    am Schnittufer, dessen Normale in +x zeigt - unabhaengig davon, wie das
    Element dort laeuft. Gleichgewicht am Teilstab wie solver.beam_station_forces."""
    from statik3d import assemble as asm
    from statik3d.elements import beam3d as bm
    X = np.asarray(m.nodes, float)
    p = np.asarray(p, float)
    for i in m.members["S1"].elements:
        e = m.elements[int(i)]
        a, b = X[int(e.nodes[0])], X[int(e.nodes[1])]
        T3, L = bm.local_axes(a, b, e.roll)
        x = float((p - a) @ T3[0])
        if -1e-12 <= x <= L + 1e-12 and np.linalg.norm(a + x * T3[0] - p) < 1e-9:
            fl = r.beam_end[int(i)]
            Q, Mq = asm.lastresultierende(r.beam_q.get(int(i)), np.array([x]))
            N, Vy, Vz = -fl[0] - Q[0, 0], -fl[1] - Q[0, 1], -fl[2] - Q[0, 2]
            Mt, My, Mz = -fl[3], -fl[4] - fl[2] * x - Mq[0, 2], -fl[5] + fl[1] * x + Mq[0, 1]
            s = 1.0 if T3[0][0] > 0 else -1.0
            return np.concatenate([s * (T3.T @ [N, Vy, Vz]), s * (T3.T @ [Mt, My, Mz])])
    raise ValueError(f"kein Element von S1 bei {p}")


def _rel(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    s = float(np.max(np.abs(a))) if a.size else 0.0
    return float(np.max(np.abs(b - a))) / s if s > 0 else float("inf")


def _rechnen(m, g):
    from statik3d import solver
    return solver.solve_all(m, design=False).cases[g]


def _gelenke(m):
    """[(x des Elementendes, freie FHG 0..5, Federn)] aller Stabelemente von S1,
    nach x geordnet - wo die Gelenke liegen, unabhaengig von der Nummer."""
    X = np.asarray(m.nodes, float)
    out = []
    for i in m.members["S1"].elements:
        e = m.elements[int(i)]
        for j in (0, 1):
            frei = sorted(int(d) - 6 * j for d in e.hinges if 6 * j <= int(d) < 6 * j + 6)
            fed = sorted((int(d) - 6 * j, float(k)) for d, k in e.hinge_springs if 6 * j <= int(d) < 6 * j + 6)
            if frei or fed:
                out.append((round(float(X[int(e.nodes[j])][0]), 9), frei, fed))
    return sorted(out)


def _vergleich(titel, **kw):
    """Vor dem Teilen (ohne Querstab) gegen nach dem Teilen (Querstab
    angeschlossen, E1 bei x = 4 m geteilt): Verschiebungen und
    Auflagerkraefte der vier alten Knoten, Schnittgroessen an STELLEN."""
    from statik3d.importers import hicad_szn
    m0, g = _balken(False, **kw)
    r0 = _rechnen(m0, g)
    m1, g = _balken(True, **kw)
    vorher_gelenke = _gelenke(m1)
    res = hicad_szn.an_staebe_anschliessen(m1, 0.01, [])
    r1 = _rechnen(m1, g)
    U0, U1 = np.asarray(r0.u)[:4], np.asarray(r1.u)[:4]
    R0, R1 = np.asarray(r0.reactions)[:4], np.asarray(r1.reactions)[:4]
    S0 = np.array([_schnitt(m0, r0, (x, 0, 0)) for x in STELLEN])
    S1 = np.array([_schnitt(m1, r1, (x, 0, 0)) for x in STELLEN])
    d = {"u": _rel(U0[:, :3], U1[:, :3]), "phi": _rel(U0[:, 3:], U1[:, 3:]),
         "R": _rel(R0, R1), "F": _rel(S0[:, :3], S1[:, :3]), "M": _rel(S0[:, 3:], S1[:, 3:])}
    ok = (res["geteilt"] == 1 and len(m1.members["S1"].elements) == 4
          and all(v <= TOL for v in d.values()))
    check(f"{titel}: an den alten Orten gleich wie vor dem Teilen (1e-9 relativ)", ok,
          " ".join(f"{k} {v:.1e}" for k, v in d.items()))
    return m0, m1, vorher_gelenke


# ---------------------------------------------------------------------------
# Fehler 1: Gelenke bleiben am alten Ort
# ---------------------------------------------------------------------------
def test_gelenk_am_ende():
    _m0, m1, vorher = _vergleich("Gelenk am Ende von E1 (x = 6 m)",
                                 gelenk=(1, {"phiy": "free", "phiz": "free"}), linienlast=True)
    nachher = _gelenke(m1)
    check("… das Gelenk liegt weiter bei x = 6 m (am neuen Element), bei x = 4 m keins",
          vorher == [(6.0, [4, 5], [])] and nachher == vorher, f"vorher {vorher}, nachher {nachher}")
    neu = len(m1.elements) - 1
    check("… und gehört im Gelenkverzeichnis zum neuen Element (Stellungen schalten es dort ab)",
          m1.hinges["G1"].elemente == [neu], str(m1.hinges["G1"].elemente))


def test_gelenk_am_anfang():
    _m0, m1, vorher = _vergleich("Gelenk am Anfang von E1 (x = 2 m)",
                                 gelenk=(0, {"phiy": "free", "phiz": "free"}), linienlast=True)
    nachher = _gelenke(m1)
    check("… das Gelenk bleibt bei x = 2 m am alten Element, bei x = 4 m keins",
          vorher == [(2.0, [4, 5], [])] and nachher == vorher and m1.hinges["G1"].elemente == [1],
          f"vorher {vorher}, nachher {nachher}, G1 an {m1.hinges['G1'].elemente}")


def test_federgelenk():
    _m0, m1, vorher = _vergleich("Federgelenk am Ende von E1 (φy 5000 kNm/rad, φz frei)",
                                 gelenk=(1, {"phiy": 5e6, "phiz": "free"}), linienlast=True)
    nachher = _gelenke(m1)
    check("… Feder und Freigabe liegen weiter bei x = 6 m",
          vorher == [(6.0, [5], [(4, 5e6)])] and nachher == vorher, f"vorher {vorher}, nachher {nachher}")


def test_gedrehtes_element():
    _m0, m1, vorher = _vergleich("gedrehtes Element (Drehwinkel 30°), Gelenk φz am Ende",
                                 roll=np.radians(30.0), gelenk=(1, {"phiz": "free"}), linienlast=True)
    nachher = _gelenke(m1)
    rolls = [round(float(m1.elements[int(i)].roll), 12) for i in m1.members["S1"].elements]
    check("… das Gelenk liegt weiter bei x = 6 m, beide Teile mit 30°",
          nachher == vorher == [(6.0, [5], [])] and rolls[1] == rolls[2] == round(np.radians(30.0), 12),
          f"{nachher}, Drehwinkel {rolls}")


def test_gegenlaeufiges_element():
    # E1 laeuft von x = 6 nach x = 2 m: sein Ende liegt bei x = 2 m
    _m0, m1, vorher = _vergleich("gegenläufiges Element, Gelenk am Ende (x = 2 m)", umgekehrt=True,
                                 gelenk=(1, {"phiy": "free", "phiz": "free"}), linienlast=True)
    nachher = _gelenke(m1)
    check("… das Gelenk liegt weiter bei x = 2 m, bei x = 4 m keins",
          vorher == [(2.0, [4, 5], [])] and nachher == vorher, f"vorher {vorher}, nachher {nachher}")
    _m0, m1, vorher = _vergleich("gegenläufiges Element, Gelenk am Anfang (x = 6 m)", umgekehrt=True,
                                 gelenk=(0, {"phiy": "free", "phiz": "free"}), linienlast=True)
    nachher = _gelenke(m1)
    check("… das Gelenk bleibt bei x = 6 m",
          vorher == [(6.0, [4, 5], [])] and nachher == vorher, f"vorher {vorher}, nachher {nachher}")


# ---------------------------------------------------------------------------
# Fehler 2: Elementlasten gehen auf beide Teile
# ---------------------------------------------------------------------------
def _lasten_von(m, g, elemente):
    return [(int(bl.elem), round(float(bl.a), 9), None if bl.b is None else round(float(bl.b), 9))
            for bl in m.load_cases[g].beam_loads if int(bl.elem) in elemente and not getattr(bl, "_geo", False)]


def test_gleichmaessige_elementlast():
    _m0, m1, _ = _vergleich("gleichmäßige Elementlast auf E1",
                            lasten=[dict(qy=-1e3, qz=-4e3)])
    g = next(iter(m1.load_cases))
    neu = len(m1.elements) - 1
    check("… je eine Elementlast auf beiden Teilen, jede über das ganze Teil",
          _lasten_von(m1, g, {1, neu}) == [(1, 0.0, None), (neu, 0.0, None)], str(_lasten_von(m1, g, {1, neu})))


def test_trapez_elementlast():
    _vergleich("Trapez-Elementlast über ganz E1 (1 → 5 kN/m)",
               lasten=[dict(qz=-1e3, q2=[0, -2e3, -5e3])])
    _vergleich("Trapez-Teillast über die Teilstelle (0,5 bis 3,5 m)",
               lasten=[dict(qz=-2e3, q2=[0, 0, -6e3], a=0.5, b=3.5)])
    _vergleich("Trapez-Teillast nur auf dem neuen Teil (2,5 m bis Ende)",
               lasten=[dict(qy=1e3, qz=-2e3, q2=[0, 0, -6e3], a=2.5)])


def test_einzellast():
    e = 1e-3        # halbe Breite des kurzen Abschnitts [m]; F = q * 2e = 8 kN
    def einzel(c):
        return dict(qz=-8e3 / (2 * e), a=c - e, b=c + e)
    _vergleich("Einzellast in der Mitte von E1 (auf der Teilstelle)", lasten=[einzel(2.0)])
    _vergleich("Einzellast nahe der Teilstelle, davor (1,995 m)", lasten=[einzel(1.995)])
    _vergleich("Einzellast nahe der Teilstelle, dahinter (2,005 m)", lasten=[einzel(2.005)])
    _vergleich("Einzellast in der Mitte des neuen Teils (3 m)", lasten=[einzel(3.0)])


def test_elementlast_lokal():
    _vergleich("lokale Trapez-Elementlast auf dem gedrehten Element (30°)", roll=np.radians(30.0),
               lasten=[dict(qy=-1e3, qz=-2e3, q2=[0, -3e3, -1e3], system="local")])
    _vergleich("Teillast auf dem gegenläufigen Element (0,5 bis 3 m ab x = 6 m)", umgekehrt=True,
               lasten=[dict(qz=-2e3, q2=[0, 0, -6e3], a=0.5, b=3.0)])
    _vergleich("alles zusammen: Gelenk, Linienlast und Elementlasten", roll=np.radians(15.0),
               gelenk=(1, {"phiy": 5e6, "phiz": "free"}), linienlast=True,
               lasten=[dict(qz=-1e3), dict(qy=-2e3, q2=[0, -1e3, 0], a=1.0, b=3.5, system="local")])


def test_neues_element_gegenlaeufig():
    """Model.stabelement_geteilt direkt, das neue Teil laeuft gegen das alte
    (ein anderer Aufrufer koennte so teilen): Gelenk und lokale Last gehen
    trotzdem an den richtigen Ort. Fuer gleiche Querschnittslage hat das
    gegenlaeufige Teil den Drehwinkel mit umgekehrtem Vorzeichen."""
    kw = dict(roll=np.radians(20.0), gelenk=(1, {"phiy": "free", "phiz": "free"}),
              lasten=[dict(qy=-1e3, qz=-2e3, q2=[0, -3e3, -1e3], a=0.5, b=3.5, system="local")])
    m0, g = _balken(False, **kw)
    r0 = _rechnen(m0, g)
    m1, g = _balken(False, **kw)
    k = m1.add_node(4, 0, 0)
    e = m1.elements[1]
    hinten = int(e.nodes[-1])
    e.nodes = [int(e.nodes[0]), k]
    neu = m1.add_element("beam", [hinten, k], MAT, SEC, roll=-e.roll)
    m1.stabelement_geteilt(1, neu)
    r1 = _rechnen(m1, g)
    d = {"u": _rel(np.asarray(r0.u)[:4], np.asarray(r1.u)[:4]),
         "R": _rel(np.asarray(r0.reactions)[:4], np.asarray(r1.reactions)[:4])}
    S0 = np.array([_schnitt(m0, r0, (x, 0, 0)) for x in STELLEN])
    S1 = np.array([_schnitt(m1, r1, (x, 0, 0)) for x in STELLEN])
    d.update(F=_rel(S0[:, :3], S1[:, :3]), M=_rel(S0[:, 3:], S1[:, 3:]))
    check("neues Teil gegenläufig: Gelenk am Anfang des neuen Teils, an den alten Orten gleich (1e-9)",
          all(v <= TOL for v in d.values()) and sorted(m1.elements[neu].hinges) == [4, 5]
          and not m1.elements[1].hinges, " ".join(f"{k} {v:.1e}" for k, v in d.items())
          + f" Gelenk neu {m1.elements[neu].hinges}")


def test_mit_schubflaechen():
    """Dieselben Lasten mit Schubflaechen (HEB 200, Nachtrag N01): seit dem
    07.10.2026 sind die Ersatzknotenlasten die des Stabes mit Schubverformung,
    das Teilen aendert dann auch hier nichts (vorher bis 2e-3)."""
    _vergleich("mit Schubflächen: Trapez-Elementlast über ganz E1", schub=True,
               lasten=[dict(qz=-1e3, q2=[0, -2e3, -5e3])])
    _vergleich("mit Schubflächen: Trapez-Teillast über die Teilstelle", schub=True,
               lasten=[dict(qz=-2e3, q2=[0, 0, -6e3], a=0.5, b=3.5)])
    _vergleich("mit Schubflächen: Einzellast nahe der Teilstelle (1,995 m)", schub=True,
               lasten=[dict(qz=-8e3 / 2e-3, a=1.994, b=1.996)])
    # am alten Stand die groesste Abweichung der Faelle dieser Suite: u 2,0e-3
    _vergleich("mit Schubflächen: Einzellast in der Mitte des neuen Teils (3 m)", schub=True,
               lasten=[dict(qz=-8e3 / 2e-3, a=2.999, b=3.001)])
    _vergleich("mit Schubflächen: lokale Trapez-Teillast, gedreht, mit Gelenk", schub=True,
               roll=np.radians(15.0), gelenk=(1, {"phiy": 5e6, "phiz": "free"}), linienlast=True,
               lasten=[dict(qz=-1e3), dict(qy=-2e3, q2=[0, -1e3, 0], a=1.0, b=3.5, system="local")])


def test_summe_auflager_mit_schub():
    """Der gemeldete Fall: HEB 200 mit Schubflaechen, Linienlast 10 kN/m auf
    S1 und 1 kN/m direkt auf E1: Summe der Auflagerkraefte z 84000 N."""
    from statik3d import solver
    from statik3d.importers import hicad_szn
    m, g = _balken(True, schub=True, lasten=[dict(qz=-1e3)], gelenk=(1, {"phiy": "free"}),
                   linienlast=True, querstab_fest=False)
    m.load_cases[g].linienlasten[0].q = [0, 0, -10e3]
    m.lasten_verteilen()

    def rz(mm):
        an = solver.solve_all(mm, design=False)
        return float(np.asarray(an.cases[g].reactions).reshape(-1, 6)[:, 2].sum())
    m0, _ = _balken(False, schub=True, lasten=[dict(qz=-1e3)], gelenk=(1, {"phiy": "free"}), linienlast=True)
    m0.load_cases[g].linienlasten[0].q = [0, 0, -10e3]
    m0.lasten_verteilen()
    vor = rz(m0)
    hicad_szn.an_staebe_anschliessen(m, 0.01, [])
    nach = rz(m)
    check("HEB 200 mit Schub: Summe der Auflagerkräfte z vor und nach dem Teilen 84000 N",
          abs(vor - 84000.0) < 1e-6 and abs(nach - 84000.0) < 1e-6, f"vorher {vor:.3f} N, nachher {nach:.3f} N")
    check("… das Gelenk liegt weiter bei x = 6 m", _gelenke(m) == [(6.0, [4], [])], str(_gelenke(m)))


# ---------------------------------------------------------------------------
# Rueckgaengig
# ---------------------------------------------------------------------------
def _stand(m):
    """Alles, was das Teilen anfasst, als vergleichbarer Wert."""
    return (np.asarray(m.nodes, float).round(12).tolist(),
            [(e.typ, [int(n) for n in e.nodes], sorted(int(d) for d in e.hinges),
              sorted((int(d), float(k)) for d, k in e.hinge_springs), float(e.roll)) for e in m.elements],
            {n: [int(e) for e in mem.elements] for n, mem in m.members.items()},
            {n: sorted(int(e) for e in (h.elemente or [])) for n, h in m.hinges.items()},
            {c: [(int(bl.elem), [float(v) for v in bl.q], None if bl.q2 is None else [float(v) for v in bl.q2],
                  float(bl.a), None if bl.b is None else float(bl.b), bl.system, bool(getattr(bl, "_geo", False)))
                 for bl in lc.beam_loads] for c, lc in m.load_cases.items()})


def test_rueckgaengig():
    from PySide6 import QtWidgets
    w, app = _fenster()
    w.new_model()
    _balken(True, w.model, gelenk=(1, {"phiy": "free", "phiz": "free"}), linienlast=True,
            lasten=[dict(qz=-1e3), dict(qz=-8e3 / 2e-3, a=2.999, b=3.001)], querstab_fest=True)
    g = next(iter(w.model.load_cases))
    w.refresh_all()
    app.processEvents()
    vorher = _stand(w.model)
    r0 = _rechnen(w.model, g)
    alt = QtWidgets.QInputDialog.getDouble
    QtWidgets.QInputDialog.getDouble = staticmethod(lambda *a, **k: (10.0, True))
    try:
        w.staebe_anschliessen()
    finally:
        QtWidgets.QInputDialog.getDouble = alt
    app.processEvents()
    geteilt = _stand(w.model)
    neu = len(w.model.elements) - 1
    check("„Freie Stabenden anschließen…“ in der Oberfläche: Gelenk und Lasten auf dem neuen Element",
          geteilt != vorher and sorted(w.model.elements[neu].hinges) == [10, 11]
          and not w.model.elements[1].hinges
          and sum(1 for bl in w.model.load_cases[g].beam_loads
                  if int(bl.elem) == neu and not getattr(bl, "_geo", False)) == 2,
          f"E{neu}: {w.model.elements[neu].hinges}, E1: {w.model.elements[1].hinges}")
    w.undo()
    app.processEvents()
    check("Rückgängig stellt Knoten, Elemente, Gelenke, Stäbe und Elementlasten wieder her",
          _stand(w.model) == vorher, "")
    r1 = _rechnen(w.model, g)
    d = max(_rel(r0.u, r1.u), _rel(r0.reactions, r1.reactions))
    check("… und die Rechnung danach ist dieselbe wie vorher", d <= TOL, f"{d:.1e}")


def test_handbuch():
    """Der Handbuchsatz nennt, was test_summe_auflager_mit_schub misst."""
    from tests.handbuch import absatz
    a = absatz("**Was beim Stab mit Nachweis zu beachten ist**")
    check("Handbuch: Gelenke und Elementlasten gehen beim Teilen mit, Stand vor dem 06.10.2026",
          "Seit dem 06.10.2026 gehen beim Teilen auch die Gelenke und die Elementlasten" in a
          and "an der Teilstelle entsteht kein Gelenk" in a and "anteilig auf beiden Teilen" in a
          and "Bis zum 06.10.2026 wanderte ein Gelenk am Ende des Elements an die Teilstelle" in a
          and "82 statt 84 kN" in a, a[:100])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_gelenk_am_ende, test_gelenk_am_anfang, test_federgelenk, test_gedrehtes_element,
              test_gegenlaeufiges_element, test_gleichmaessige_elementlast, test_trapez_elementlast,
              test_einzellast, test_elementlast_lokal, test_neues_element_gegenlaeufig,
              test_mit_schubflaechen, test_summe_auflager_mit_schub, test_rueckgaengig, test_handbuch):
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
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
