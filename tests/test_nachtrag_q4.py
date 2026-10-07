"""
Nachtrag zur Fehlerliste vom 06.10.2026, Paket Q4 (07.10.2026): Teilen und
parallele Elemente.

* N02 Teilen: ``Model.stabelement_geteilt`` ließ am neuen Teil alles zurück,
  was nicht Gelenk oder Elementlast war. Gemessen am Balken 8 m (Element E1
  von x = 2 bis 6 m, bei x = 4 m geteilt, HEB 200 ohne Schubflächen): das
  neue Element hatte ``line`` "", ``nur`` "", ``woelb`` False, keine
  Exzentrizität und keine Temperaturlast, das alte behielt den Versatz seines
  Endes an der Teilstelle; ein Anschluss (Joint) am Ende blieb am alten Teil,
  dessen Ende jetzt an der Teilstelle liegt. Die Rechnung wich entsprechend ab
  (Temperatur dT 40 K auf E1: Verschiebung 50 %, Versatz (0, 0, 0,2) an
  beiden Enden mit 10 kN/m: 10 %). Geprüft wird je Feld, dass die Rechnung an
  den alten Orten gleich bleibt (1e-9 relativ) und dass die Felder am
  richtigen Teil stehen.
* N03 Browser-Stabzug: der Stabzug im Browser (web/server.py, Operation
  ``line_of_beams``) legte ohne Prüfung parallele Elemente über eine
  vorhandene Kette und nie einen Stab an. Er ruft jetzt dieselbe Funktion wie
  die Oberfläche (``Model.stabzug_anlegen``), mit derselben Prüfung.
* N04 Linie und Stabelement: „Linie → Stabelemente erzeugen“ prüfte gar
  nichts (auch bei gleichen Endknoten), „Netz → Stabelement“ nur bei gleichen
  Endknoten (_stabelemente_zwischen). Beide nutzen jetzt die Prüfung des
  Befehls „Stab“ (``Model.stabelemente_auf_strecken``): das Stabelement
  warnt weiter nur in der Statuszeile, die Linie legt keine Linie an.

Aufruf:  python -m tests.test_nachtrag_q4
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
    tempfile.mkdtemp(prefix="statik3d_nachtrag_q4_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
MAT, SEC = "S355", "HEB 200"
TOL = 1e-9


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
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
    # Rueckfragen und Meldungen nie auf dem Bildschirm stehen lassen
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    meld = abfangen(w, w.fehler_liste)
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    _FENSTER.update(w=w, app=app, meld=meld)
    return w, app


# ---------------------------------------------------------------------------
# N02: Elementfelder beim Teilen
# ---------------------------------------------------------------------------
def _balken(x=(0.0, 2.0, 6.0, 8.0)):
    """Balken 8 m: Stab S1 aus E0, E1 (x = 2 bis 6 m) und E2, bei x = 0 eingespannt,
    bei x = 8 m quer gehalten. HEB 200 ohne Schubflaechen: so folgt die Teilung
    der Last-Ersatzkraefte den Bernoulli-Ansaetzen (wie tests.test_stab_teilen)."""
    from statik3d.model import Model, Material, Section
    m = Model("Q4")
    m.add_material(Material.steel(MAT))
    m.add_section(Section.from_profile(SEC))
    m.sections[SEC].Asy = 0.0
    m.sections[SEC].Asz = 0.0
    for xx in x:
        m.add_node(xx, 0, 0)
    m.support(0, "all")
    m.support(3, [1, 2, 3])
    g = next(iter(m.load_cases))
    els = [m.add_element("beam", ab, MAT, SEC) for ab in ([0, 1], [1, 2], [2, 3])]
    m.add_member("S1", els)
    return m, g


def _teilen(m, i=1, x=4.0, gegen=False):
    """Das Element ``i`` bei x teilen wie ein Aufrufer von stabelement_geteilt:
    ein neuer Knoten, das alte Element verkuerzt, das neue Teil vom alten Ende zum
    neuen Knoten (``gegen``: gegen die Richtung des alten, mit umgekehrtem Drehwinkel,
    sodass die Querschnittslage gleich bleibt)."""
    k = m.add_node(x, 0, 0)
    e = m.elements[i]
    hinten = int(e.nodes[-1])
    e.nodes = [int(e.nodes[0]), k]
    neu = m.add_element("beam", [hinten, k] if gegen else [k, hinten], e.mat, e.sec,
                        roll=-e.roll if gegen else e.roll, group=e.group)
    m.stabelement_geteilt(i, neu)
    return neu


def _rechnen(m, g):
    from statik3d import solver
    return solver.solve_all(m, design=False).cases[g]


def _rel(a, b, skala=None):
    a, b = np.asarray(a, float), np.asarray(b, float)
    s = float(np.max(np.abs(a))) if skala is None else float(skala)
    return float(np.max(np.abs(b - a))) / s if s > 0 else float("inf")


def _gleich(bau, titel, skala_R=None, **kw):
    """Das Modell ``bau(m, g)`` ungeteilt gegen dasselbe bei x = 4 m geteilt:
    Verschiebungen und Auflagerkraefte der vier alten Knoten (1e-9 relativ)."""
    m0, g = _balken()
    bau(m0, g)
    r0 = _rechnen(m0, g)
    m1, g = _balken()
    bau(m1, g)
    neu = _teilen(m1, **kw)
    r1 = _rechnen(m1, g)
    U0, U1 = np.asarray(r0.u)[:4], np.asarray(r1.u)[:4]
    R0, R1 = np.asarray(r0.reactions)[:4], np.asarray(r1.reactions)[:4]
    du, dr = _rel(U0, U1), _rel(R0, R1, skala_R)
    check(f"{titel}: an den alten Orten gleich wie vor dem Teilen (1e-9 relativ)",
          du <= TOL and dr <= TOL,
          f"u {du:.1e}, R {dr:.1e}, max|u| {np.abs(U0).max():.2e}")
    return m1, g, neu


def test_n02_felder():
    """line und woelb am Balken, nur am Fachwerkstab, laenge0 am Seil."""
    m, g = _balken()
    m.elements[1].line = "L7"
    m.stab_woelb_setzen(1, True)
    neu = _teilen(m)
    ea, en = m.elements[1], m.elements[neu]
    check("N02 Feld line: das neue Teil gehört zur selben Linie (L7), das alte auch",
          en.line == "L7" and ea.line == "L7", f"neu {en.line!r}, alt {ea.line!r}")
    check("N02 Feld woelb: Wölbkrafttorsion gilt auch am neuen Teil (Querschnitt mit Iw > 0)",
          en.woelb is True and ea.woelb is True and m.stab_woelbt(en),
          f"neu {en.woelb}, alt {ea.woelb}, stab_woelbt {m.stab_woelbt(en)}")
    # was das neue Teil schon traegt, bleibt
    m, g = _balken()
    m.elements[1].line = "L7"
    k = m.add_node(4, 0, 0)
    e = m.elements[1]
    hinten = int(e.nodes[-1])
    e.nodes = [int(e.nodes[0]), k]
    neu = m.add_element("beam", [k, hinten], MAT, SEC, line="eigene")
    m.stabelement_geteilt(1, neu)
    check("… was das neue Teil selbst trägt, überschreibt die Teilung nicht (line „eigene“)",
          m.elements[neu].line == "eigene", repr(m.elements[neu].line))

    # nur: Fachwerkstab, der nur Zug aufnimmt
    from statik3d.model import Model, Material, Section
    mt = Model("Q4 nur")
    mt.add_material(Material.steel(MAT))
    mt.add_section(Section.from_profile(SEC))
    for xx in (0.0, 4.0):
        mt.add_node(xx, 0, 0)
    mt.add_element("truss", [0, 1], MAT, SEC, nur="zug")
    k = mt.add_node(1.0, 0, 0)
    mt.elements[0].nodes = [0, k]
    neu = mt.add_element("truss", [k, 1], MAT, SEC)
    mt.stabelement_geteilt(0, neu)
    check("N02 Feld nur: ein Fachwerkstab „nur Zug“ bleibt auf beiden Teilen „nur Zug“",
          mt.elements[0].nur == "zug" and mt.elements[neu].nur == "zug",
          f"alt {mt.elements[0].nur!r}, neu {mt.elements[neu].nur!r}")
    check("… das Modell kennt den Ausfallstab (hat_ausfallstaebe)", mt.hat_ausfallstaebe())

    # laenge0: Seil, ungedehnte Laenge 4,2 m auf der Sehne von 4 m, geteilt bei 1 m
    ms = Model("Q4 Seil")
    ms.add_material(Material.steel(MAT))
    ms.add_section(Section.from_profile(SEC))
    for xx in (0.0, 4.0):
        ms.add_node(xx, 0, 0)
    ms.add_element("seil", [0, 1], MAT, SEC, laenge0=4.2)
    k = ms.add_node(1.0, 0, 0)
    ms.elements[0].nodes = [0, k]
    neu = ms.add_element("seil", [k, 1], MAT, SEC)
    ms.stabelement_geteilt(0, neu)
    la, ln = ms.elements[0].laenge0, ms.elements[neu].laenge0
    check("N02 Feld laenge0: die ungedehnte Länge 4,2 m teilt sich im Verhältnis der Sehnen (1,05 und 3,15 m)",
          abs(la - 1.05) < 1e-12 and abs(ln - 3.15) < 1e-12 and abs(la + ln - 4.2) < 1e-12,
          f"alt {la}, neu {ln}")
    # laenge0 = 0 (Sehnenlaenge) bleibt 0 auf beiden
    ms2 = Model("Q4 Seil 0")
    ms2.add_material(Material.steel(MAT))
    ms2.add_section(Section.from_profile(SEC))
    for xx in (0.0, 4.0):
        ms2.add_node(xx, 0, 0)
    ms2.add_element("seil", [0, 1], MAT, SEC)
    k = ms2.add_node(1.0, 0, 0)
    ms2.elements[0].nodes = [0, k]
    neu = ms2.add_element("seil", [k, 1], MAT, SEC)
    ms2.stabelement_geteilt(0, neu)
    check("… laenge0 = 0 (Sehnenlänge) bleibt 0",
          ms2.elements[0].laenge0 == 0.0 and ms2.elements[neu].laenge0 == 0.0,
          f"{ms2.elements[0].laenge0}, {ms2.elements[neu].laenge0}")


def test_n02_temperatur():
    def dT(m, g):
        m.load_temp(1, 40.0, 0.0, case=g)

    def dTz(m, g):
        m.load_temp(1, 0.0, 25.0, case=g)

    def beide(m, g):
        m.load_temp(1, 30.0, 12.0, case=g)
        m.load_beam(1, qz=-10e3, case=g)
    # statisch bestimmt: die Auflagerkraefte sind ~0, der Massstab ist E A alpha dT
    mat = _balken()[0].materials[MAT]
    sec = _balken()[0].sections[SEC]
    skala = mat.E * sec.A * mat.alpha * 40.0
    m1, g, neu = _gleich(dT, "N02 Temperatur: ΔT = 40 K auf E1", skala_R=skala)
    check("… das neue Teil trägt dieselbe Temperaturlast wie das alte",
          [(t.elem, t.dT, t.dT_z) for t in m1.load_cases[g].temp_loads] == [(1, 40.0, 0.0), (neu, 40.0, 0.0)],
          str([(t.elem, t.dT, t.dT_z) for t in m1.load_cases[g].temp_loads]))
    _gleich(dTz, "N02 Temperatur: Gradient ΔT_z = 25 K über die Höhe auf E1")
    _gleich(beide, "N02 Temperatur mit Gradient und Elementlast zusammen")
    # eine aus Objektlasten abgeleitete Temperaturlast (_geo) legt lasten_verteilen neu
    m, g = _balken()
    m.load_temp(1, 40.0, 0.0, case=g)
    m.load_cases[g].temp_loads[0]._geo = True
    neu = _teilen(m)
    check("… eine abgeleitete Temperaturlast (_geo) wird nicht kopiert, sie legt lasten_verteilen neu",
          len(m.load_cases[g].temp_loads) == 1, str(len(m.load_cases[g].temp_loads)))


def test_n02_exzentrizitaet():
    def gleich(m, g):
        m.elements[1].exzentrizitaet = [[0.0, 0.0, 0.2], [0.0, 0.0, 0.2]]
        m.load_beam(1, qz=-10e3, case=g)
    m1, g, neu = _gleich(gleich, "N02 Versatz (0, 0, 0,2) an beiden Enden, 10 kN/m")
    check("… der Versatz gilt auf beiden Teilen, auch an der Teilstelle (die Achse bleibt parallel)",
          m1.elements[1].exzentrizitaet == [[0.0, 0.0, 0.2], [0.0, 0.0, 0.2]]
          and m1.elements[neu].exzentrizitaet == [[0.0, 0.0, 0.2], [0.0, 0.0, 0.2]],
          f"alt {m1.elements[1].exzentrizitaet}, neu {m1.elements[neu].exzentrizitaet}")

    def ungleich(m, g):
        m.elements[1].exzentrizitaet = [[0.0, 0.1, 0.1], [0.0, 0.3, 0.4]]
        m.load_beam(1, qz=-10e3, qy=-3e3, case=g)
    m1, g, neu = _gleich(ungleich, "N02 Versatz (0, 0,1, 0,1) am Anfang, (0, 0,3, 0,4) am Ende")
    ea, en = m1.elements[1].exzentrizitaet, m1.elements[neu].exzentrizitaet
    soll_a = [[0.0, 0.1, 0.1], [0.0, 0.2, 0.25]]
    soll_n = [[0.0, 0.2, 0.25], [0.0, 0.3, 0.4]]
    check("… jedes Ende behält seinen Versatz, die Teilstelle bekommt den Wert dazwischen (gerade Achse)",
          np.allclose(ea, soll_a, atol=1e-15) and np.allclose(en, soll_n, atol=1e-15),
          f"alt {ea}, neu {en}")

    def nur_ende(m, g):
        m.elements[1].exzentrizitaet = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.4]]
        m.load_beam(1, qz=-10e3, case=g)
    m1, g, neu = _gleich(nur_ende, "N02 Versatz nur am Ende von E1 (x = 6 m)")
    check("… der Versatz des Endes sitzt am Teil mit dem Ende (neu), an der Teilstelle der halbe",
          np.allclose(m1.elements[1].exzentrizitaet, [[0, 0, 0], [0, 0, 0.2]], atol=1e-15)
          and np.allclose(m1.elements[neu].exzentrizitaet, [[0, 0, 0.2], [0, 0, 0.4]], atol=1e-15),
          f"alt {m1.elements[1].exzentrizitaet}, neu {m1.elements[neu].exzentrizitaet}")

    # gegenlaeufiges neues Teil bei gedrehtem Element: der Versatz folgt den Achsen des neuen Teils
    def gedreht(m, g):
        m.elements[1].roll = np.radians(30.0)
        m.elements[1].exzentrizitaet = [[0.0, 0.1, 0.2], [0.0, 0.3, 0.1]]
        m.load_beam(1, qz=-10e3, qy=-2e3, case=g)
    m1, g, neu = _gleich(gedreht, "N02 gedrehtes Element (30°), neues Teil gegenläufig, Versatz in y und z",
                         gegen=True)
    from statik3d.elements import beam3d as bm
    X = np.asarray(m1.nodes, float)

    def global_ende(i, j):
        """Der Versatz am Ende j von Element i als globaler Vektor."""
        e = m1.elements[i]
        if len(e.exzentrizitaet) <= j:
            return np.full(3, np.nan)
        T3, _ = bm.local_axes(X[int(e.nodes[0])], X[int(e.nodes[1])], e.roll)
        return T3.T @ np.asarray(e.exzentrizitaet[j], float)
    # alt: Anfang bei x = 2 m (Originalwert), Teilstelle = Ende; neu (gegenlaeufig): Anfang bei x = 6 m
    T3o = bm.local_axes(np.array([2.0, 0, 0]), np.array([6.0, 0, 0]), np.radians(30.0))[0]
    r_s, r_e = T3o.T @ [0.0, 0.1, 0.2], T3o.T @ [0.0, 0.3, 0.1]
    r_m = 0.5 * (r_s + r_e)
    ok = (np.allclose(global_ende(1, 0), r_s, atol=1e-13) and np.allclose(global_ende(1, 1), r_m, atol=1e-13)
          and np.allclose(global_ende(neu, 0), r_e, atol=1e-13) and np.allclose(global_ende(neu, 1), r_m, atol=1e-13))
    check("… als globale Vektoren sitzen die Versätze an denselben Orten wie vor dem Teilen",
          ok, f"{[np.round(global_ende(i, j), 6).tolist() for i, j in ((1, 0), (1, 1), (neu, 0), (neu, 1))]}")


def test_n02_anschluss():
    from statik3d.model import Joint
    m, g = _balken()
    m.joints["J1"] = Joint("J1", "kopfplatte", elem=1, end=1)    # Ende von E1 bei x = 6 m
    m.joints["J2"] = Joint("J2", "kopfplatte", elem=1, end=0)    # Anfang von E1 bei x = 2 m
    m.joints["J3"] = Joint("J3", "kopfplatte", elem=2, end=0)    # ein anderes Element
    neu = _teilen(m)
    j = {n: (jo.elem, jo.end) for n, jo in m.joints.items()}
    check("N02 Anschluss am Ende von E1 (x = 6 m) geht an das neue Teil, dessen Ende dort liegt",
          j["J1"] == (neu, 1), f"{j}")
    check("… der Anschluss am Anfang (x = 2 m) und der am anderen Element bleiben",
          j["J2"] == (1, 0) and j["J3"] == (2, 0), f"{j}")
    ort = m.joints["J1"]
    X = np.asarray(m.nodes, float)
    x_ende = float(X[int(m.elements[ort.elem].nodes[ort.end])][0])
    check("… und sitzt weiter bei x = 6 m (nicht an der Teilstelle bei x = 4 m)",
          abs(x_ende - 6.0) < 1e-12, f"x = {x_ende}")
    # gegenlaeufiges neues Teil: das alte Ende liegt am Anfang (Endindex 0)
    m, g = _balken()
    m.joints["J1"] = Joint("J1", "kopfplatte", elem=1, end=1)
    neu = _teilen(m, gegen=True)
    check("… läuft das neue Teil gegen das alte, ist es sein Anfang (Ende 0)",
          (m.joints["J1"].elem, m.joints["J1"].end) == (neu, 0), f"{m.joints['J1'].elem, m.joints['J1'].end}")


def test_n02_ueber_staebe_anschliessen():
    """Der echte Weg: „Freie Stabenden anschließen…“ (hicad_szn.an_staebe_anschliessen)."""
    from statik3d.importers import hicad_szn
    m, g = _balken()
    m.elements[1].line = "L7"
    m.elements[1].exzentrizitaet = [[0.0, 0.0, 0.2], [0.0, 0.0, 0.2]]
    m.load_temp(1, 40.0, 0.0, case=g)
    a = m.add_node(4, 0.005, 0)
    b = m.add_node(4, 3, 0)
    m.add_element("beam", [b, a], MAT, SEC)
    res = hicad_szn.an_staebe_anschliessen(m, 0.01, [])
    neu = len(m.elements) - 1
    en = m.elements[neu]
    check("N02 über „Freie Stabenden anschließen…“: das neue Teil trägt Linie, Versatz und Temperaturlast",
          res["geteilt"] == 1 and en.line == "L7" and en.exzentrizitaet == [[0.0, 0.0, 0.2], [0.0, 0.0, 0.2]]
          and any(t.elem == neu for t in m.load_cases[g].temp_loads),
          f"geteilt {res['geteilt']}, Linie {en.line!r}, Versatz {en.exzentrizitaet}")


def test_n02_handbuch():
    from tests.handbuch import absatz
    a = absatz("**Was beim Stab mit Nachweis zu beachten ist**")
    check("Handbuch N02: Seit dem 07.10.2026 gehen auch Exzentrizität, Temperaturlasten, Anschlüsse und "
          "die übrigen Felder mit, Stand davor genannt",
          "Seit dem 07.10.2026 gehen beim Teilen außerdem" in a and "Exzentrizität" in a
          and "Temperaturlasten" in a and "Anschlüsse" in a and "ungedehnte Länge" in a
          and "Bis zum 07.10.2026 blieb das neue Teil ohne" in a, a[:100])


# ---------------------------------------------------------------------------
# N03: der Stabzug im Browser
# ---------------------------------------------------------------------------
def _kette(frei=True, m=None):
    """Drei Knoten K0 K1 K2 auf der x-Achse (0, 3, 6 m) und zwei Elemente E0, E1;
    ``frei=False``: jedes Element gehoert einem Stab (S1, S2). ``m``: in dieses
    Modell bauen (das des Fensters) statt in ein neues."""
    from statik3d.model import Model, Material, Section
    m = m if m is not None else Model("Kette")
    m.add_material(Material.steel(MAT))
    m.add_section(Section.from_profile(SEC))
    for x in (0, 3, 6):
        m.add_node(x, 0, 0)
    m.add_element("beam", [0, 1], MAT, SEC)
    m.add_element("beam", [1, 2], MAT, SEC)
    if not frei:
        m.add_member("S1", [0])
        m.add_member("S2", [1])
    return m


def _abbild(m):
    return (np.asarray(m.nodes, float).round(12).tolist(),
            [(e.typ, [int(n) for n in e.nodes], e.mat, e.sec) for e in m.elements],
            {k: list(v.elements) for k, v in m.members.items()})


def _op(m, **kw):
    from statik3d.web.server import State, apply_op
    st = State(m)
    return st, apply_op(st, dict(op="line_of_beams", mat=MAT, sec=SEC, **kw))


def test_n03_browser_ueber_staebe():
    """Der Stabzug über zwei Stäbe: abgewiesen, Modell unverändert, mit demselben Hinweis wie die Oberfläche."""
    from statik3d.web.server import ApiError
    m = _kette(frei=False)
    vorher = _abbild(m)
    text = ""
    try:
        _op(m, p1=[0, 0, 0], p2=[6, 0, 0], n=2)
    except ApiError as ex:
        text = str(ex)
    check("N03 Browser: Stabzug über S1 und S2 wird abgewiesen, der Hinweis nennt Elemente und Stäbe",
          "Stabelement E0 von Stab S1" in text and "Stabelement E1 von Stab S2" in text
          and "kein Stabzug angelegt" in text, repr(text))
    check("… und das Modell bleibt unverändert (Knoten, Elemente, Stäbe)", _abbild(m) == vorher,
          f"{len(m.elements)} Elemente, {m.nn} Knoten, {list(m.members)}")
    # derselbe Weg in der Oberflaeche sagt dasselbe
    w, app = _fenster()
    meld = _FENSTER["meld"]
    _gui_kette(w, app, frei=False)
    w._stabzug_anlegen(MAT, SEC, [0, 0, 0], [6, 0, 0], 2)
    check("… die Oberfläche weist mit demselben Hinweis ab",
          meld.hinweis_mit(text) and len(w.model.elements) == 2, str(meld.hinweise))


def test_n03_browser_ueber_freie_kette():
    """Der Stabzug über freie Elemente nimmt sie in den Stab, ohne neues Element."""
    m = _kette(frei=True)
    st, r = _op(m, p1=[0, 0, 0], p2=[6, 0, 0], n=2)
    m = st.model
    check("N03 Browser: Stabzug über die freie Kette E0, E1 legt keine neuen Elemente an",
          len(m.elements) == 2 and m.nn == 3 and r.get("elems") == [], f"{len(m.elements)} Elemente, elems {r.get('elems')}")
    check("… aber den Stab S1 aus genau E0 und E1", {k: list(v.elements) for k, v in m.members.items()} == {"S1": [0, 1]},
          str({k: list(v.elements) for k, v in m.members.items()}))
    check("… die Antwort nennt Stab und Elemente",
          r.get("member") == "S1" and "vorhandenen Stabelemente E0 und E1 im Stab S1" in r.get("message", ""),
          repr(r.get("message")))


def test_n03_browser_legt_stab_an():
    """Der Stabzug auf freier Strecke: Elemente und ein Stab wie in der Oberfläche."""
    m = _kette(frei=True)
    st, r = _op(m, p1=[0, 5, 0], p2=[6, 5, 0], n=3)
    m = st.model
    check("N03 Browser: Stabzug auf freier Strecke legt 3 neue Elemente an (E2 bis E4) und 4 Knoten dazu",
          len(m.elements) == 5 and m.nn == 7 and r.get("elems") == [2, 3, 4], f"{len(m.elements)} Elemente, {m.nn} Knoten, {r.get('elems')}")
    check("… dazu den Stab S1 aus den drei neuen Elementen",
          {k: list(v.elements) for k, v in m.members.items()} == {"S1": [2, 3, 4]},
          str({k: list(v.elements) for k, v in m.members.items()}))
    check("… der Stab hat die Länge des Stabzugs (6 m) und der Name steht in der Antwort",
          "S1" in m.members and abs(m.member_length(m.members["S1"]) - 6.0) < 1e-12 and r.get("member") == "S1",
          f"{list(m.members)}, {r.get('member')}")
    # ein zweiter Stabzug bekommt S2; Fachwerkstab auf Wunsch
    st2, r2 = _op(st.model, p1=[0, 8, 0], p2=[6, 8, 0], n=2, fachwerk=True)
    mm = st2.model
    check("… ein zweiter Stabzug bekommt S2; „fachwerk“ legt Fachwerkstäbe an",
          list(mm.members) == ["S1", "S2"] and {mm.elements[i].typ for i in mm.members["S2"].elements} == {"truss"},
          f"{list(mm.members)}")


def test_n03_gleich_wie_oberflaeche():
    """Dieselben Strecken, auf beiden Wegen: gleiche Elemente, gleiche Stäbe, gleicher Text."""
    from statik3d.web.server import ApiError
    w, app = _fenster()
    meld = _FENSTER["meld"]
    faelle = (("auf freier Strecke", True, [0, 5, 0], [6, 5, 0], 3),
              ("über die freie Kette", True, [0, 0, 0], [6, 0, 0], 2),
              ("teilweise über die Kette (Abschnitte schneiden E0)", True, [0, 0, 0], [6, 0, 0], 3),
              ("über zwei Stäbe", False, [0, 0, 0], [6, 0, 0], 2),
              ("zur Hälfte über der Kette, zur Hälfte frei", True, [3, 0, 0], [9, 0, 0], 2))
    for titel, frei, p1, p2, n in faelle:
        _gui_kette(w, app, frei=frei)
        w._stabzug_anlegen(MAT, SEC, p1, p2, n)
        oberflaeche = (_abbild(w.model), list(meld.hinweise), w.statusBar().currentMessage())
        mw = _kette(frei)
        try:
            st, r = _op(mw, p1=p1, p2=p2, n=n)
            browser = (_abbild(st.model), [], r["message"])
        except ApiError as ex:
            browser = (_abbild(mw), [str(ex)], "")
        gleich = oberflaeche[0] == browser[0]
        if oberflaeche[1]:         # abgewiesen: derselbe Hinweis
            gleich = gleich and oberflaeche[1] == browser[1]
        else:                      # angelegt: dieselbe Meldung
            gleich = gleich and oberflaeche[2] == browser[2]
        check(f"N03 Oberfläche und Browser, Stabzug {titel}: gleiche Knoten, Elemente, Stäbe und Meldung",
              gleich, f"{oberflaeche[0][2]} / {browser[0][2]}; {(oberflaeche[1] or [oberflaeche[2]])[0][:60]!r}")


def test_n03_handbuch():
    from tests.handbuch import absatz
    a = absatz("**Was beim Stab mit Nachweis zu beachten ist**")
    check("Handbuch N03: der Stabzug im Browser prüft wie die Oberfläche und legt einen Stab an, Stand davor genannt",
          "Seit dem 07.10.2026 prüft auch der Stabzug im Browser" in a
          and "Bis zum 07.10.2026 legte der Stabzug im Browser" in a, a[:100])


# ---------------------------------------------------------------------------
# N04: Linie und Stabelement
# ---------------------------------------------------------------------------
def _gui_kette(w, app, frei=True):
    """Ein neues Modell im Fenster mit der Kette aus _kette, frische Stapel und leere Meldungen."""
    w.maskenrand.schliessen()
    w.new_model()
    _kette(frei, w.model)
    w.refresh_all()
    w._undo_init()
    w._undo_knoepfe()
    app.processEvents()
    _FENSTER["meld"].leeren()
    w.fehler_liste.clear()
    return w.model


def _linie(w, kn, teilung, staebe=True, art="Polylinie (2+ Knoten)"):
    w._maske_linie_anlegen({"art": art, "knoten": kn, "staebe": staebe, "mat": MAT, "sec": SEC,
                            "teilung": teilung})


def test_n04_stabelement_ueber_kette():
    w, app = _fenster()
    meld = _FENSTER["meld"]
    m = _gui_kette(w, app)
    w._maske_stabelement_anlegen({"knoten": [0, 2], "mat": MAT, "sec": SEC})
    s = w.statusBar().currentMessage()
    check("N04 „Stabelement“ K0–K2 über die Kette E0, E1: angelegt, die Statuszeile warnt und nennt beide",
          len(m.elements) == 3 and "Achtung" in s and "E0 und E1" in s
          and "zwei parallele Elemente tragen doppelt" in s, f"{len(m.elements)} Elemente, {s!r}")
    m = _gui_kette(w, app)
    w._maske_stabelement_anlegen({"knoten": [0, 1], "mat": MAT, "sec": SEC})
    s = w.statusBar().currentMessage()
    check("… gleiche Endknoten wie bisher: derselbe Satz („lag schon Stabelement E0“)",
          len(m.elements) == 3 and "zwischen K0 und K1 lag schon Stabelement E0; zwei parallele Elemente tragen doppelt" in s,
          repr(s))
    m = _gui_kette(w, app)
    m.add_node(0, 4, 0)
    w._maske_stabelement_anlegen({"knoten": [0, 3], "mat": MAT, "sec": SEC})
    s = w.statusBar().currentMessage()
    check("… ein Stabelement auf freier Strecke: keine Warnung",
          len(m.elements) == 3 and "Achtung" not in s, repr(s))
    m = _gui_kette(w, app)
    m.add_node(9, 0, 0)
    w._maske_stabelement_anlegen({"knoten": [0, 3], "mat": MAT, "sec": SEC})
    s = w.statusBar().currentMessage()
    check("… ein Stabelement K0–K3 (0 bis 9 m) über die Kette plus freie Strecke: warnt und nennt E0 und E1",
          "Achtung" in s and "E0 und E1" in s, repr(s))
    # derselbe Weg ueber die Maske „Neu: Stabelement“ des Rechtsklicks
    m = _gui_kette(w, app)
    w.log.clear()
    w._objekt_uebernehmen("stabelement", str(len(m.elements)),
                          {"kn": "0, 2", "typ": "Balken", "mat": MAT, "sec": SEC}, True)
    check("… ebenso die Maske „Neu: Stabelement“ (Rechtsklick): angelegt, das Protokoll warnt und nennt beide",
          len(m.elements) == 3 and "Achtung: zwischen K0 und K2 lagen schon die Stabelemente E0 und E1"
          in w.log.toPlainText(), f"{len(m.elements)} Elemente, {w.log.toPlainText()[-160:]!r}")
    # nur teilweise ueberdeckt: ein Element K1–K2 liegt auf der Strecke K0–K2 zur Haelfte
    m = _gui_kette(w, app)
    del m.elements[0]
    w._maske_stabelement_anlegen({"knoten": [0, 2], "mat": MAT, "sec": SEC})
    s = w.statusBar().currentMessage()
    check("… liegt nur ein Stabelement (E0 = K1–K2) auf der Strecke: warnt mit dem einen",
          "Achtung" in s and "Stabelement E0" in s and "zwei parallele Elemente tragen doppelt" in s, repr(s))


def test_n04_linie_ueber_kette():
    w, app = _fenster()
    meld = _FENSTER["meld"]
    m = _gui_kette(w, app)
    n_undo, vorher = len(w._undo), _abbild(m)
    _linie(w, [0, 2], 2)
    check("N04 „Linie“ K0–K2 mit Stabelementen über die Kette E0, E1: keine Linie, keine Elemente, Modell unverändert",
          _abbild(m) == vorher and not m.lines and len(w._undo) == n_undo,
          f"{len(m.elements)} Elemente, Linien {list(m.lines)}, Schritte {n_undo} -> {len(w._undo)}")
    check("… der Hinweis nennt E0 und E1 und sagt, was zu tun ist (Haken abwählen)",
          meld.hinweis_mit("liegen schon die Stabelemente E0 und E1", "Stabelemente daraus erzeugen"),
          str(meld.hinweise))
    # gleiche Endknoten, eine Teilung
    meld.leeren()
    _linie(w, [0, 1], 1)
    check("… gleiche Endknoten (K0–K1): ebenso abgewiesen, der Hinweis nennt das eine Element",
          not m.lines and len(m.elements) == 2 and meld.hinweis_mit("liegt schon Stabelement E0"), str(meld.hinweise))
    # ohne Haken: die Linie ist nur Geometrie
    meld.leeren()
    _linie(w, [0, 2], 2, staebe=False)
    check("… ohne den Haken „Stabelemente daraus erzeugen“: die Linie wird angelegt, es entstehen keine Elemente",
          list(m.lines) == ["L1"] and len(m.elements) == 2 and not meld.eintraege,
          f"Linien {list(m.lines)}, {len(m.elements)} Elemente, {meld}")
    # Elemente gehoeren schon einem Stab
    m = _gui_kette(w, app, frei=False)
    meld.leeren()
    _linie(w, [0, 2], 2)
    check("… gehören die Elemente schon zu Stäben, gilt dasselbe",
          not m.lines and len(m.elements) == 2 and meld.hinweis_mit("liegen schon die Stabelemente E0 und E1"),
          str(meld.hinweise))


def test_n04_linie_frei():
    w, app = _fenster()
    meld = _FENSTER["meld"]
    m = _gui_kette(w, app)
    m.add_node(0, 5, 0)
    m.add_node(6, 5, 0)
    _linie(w, [3, 4], 3)
    s = w.statusBar().currentMessage()
    check("N04 „Linie“ auf freier Strecke: wie bisher 3 Stabelemente, kein Hinweis",
          list(m.lines) == ["L1"] and len(m.elements) == 5 and not meld.eintraege
          and "3 Stabelemente erzeugt" in s, f"Linien {list(m.lines)}, {len(m.elements)} Elemente, {meld}, {s!r}")
    # eine Linie ueber einem Teil: die Kette liegt nur auf dem ersten Stueck (K0–K2), die Linie geht weiter
    m = _gui_kette(w, app)
    m.add_node(9, 0, 0)
    meld.leeren()
    _linie(w, [0, 3], 3)
    check("… eine Linie K0–K3 (0 bis 9 m, Teilung 3), deren erste zwei Abschnitte auf der Kette liegen: abgewiesen",
          not m.lines and len(m.elements) == 2 and meld.hinweis_mit("liegen schon die Stabelemente E0 und E1"),
          f"Linien {list(m.lines)}, {len(m.elements)} Elemente, {meld.hinweise}")
    # ein Bogen ueber freiem Raum: Knoten ausserhalb der Kette
    m = _gui_kette(w, app)
    m.add_node(0, 0, 1)
    m.add_node(3, 0, 2)
    m.add_node(6, 0, 1)
    meld.leeren()
    _linie(w, [3, 4, 5], 4, art="Bogen (3 Knoten)")
    check("… ein Bogen über die Knoten oberhalb der Kette: angelegt, mit Elementen",
          list(m.lines) == ["L1"] and len(m.elements) == 6 and not meld.eintraege,
          f"Linien {list(m.lines)}, {len(m.elements)} Elemente, {meld}")


def test_n04_handbuch():
    from tests.handbuch import absatz
    a = absatz("**Was beim Stab mit Nachweis zu beachten ist**")
    check("Handbuch N04: Stabelement warnt auch über Ketten, die Linie legt dort nichts an, Stand davor genannt",
          "Seit dem 07.10.2026" in a and "Netz → Stabelement" in a and "Geometrie → Linie" in a
          and "Bis zum 07.10.2026 prüfte" in a, a[:100])
    b = absatz("Mit „Stabelemente daraus erzeugen“")
    check("Handbuch N04: bei den Linien steht, dass der Haken über vorhandenen Stabelementen nichts anlegt",
          "Seit dem 07.10.2026" in b and "liegen dort schon Stabelemente" in b, b[:100])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_n02_felder, test_n02_temperatur, test_n02_exzentrizitaet, test_n02_anschluss,
              test_n02_ueber_staebe_anschliessen, test_n02_handbuch,
              test_n03_browser_ueber_staebe, test_n03_browser_ueber_freie_kette,
              test_n03_browser_legt_stab_an, test_n03_gleich_wie_oberflaeche, test_n03_handbuch,
              test_n04_stabelement_ueber_kette, test_n04_linie_ueber_kette, test_n04_linie_frei,
              test_n04_handbuch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:")
        for n in failed:
            print("  -", n)
    sys.stdout.flush()
    os._exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
