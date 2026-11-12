"""
Lage der Schalenelemente: Ausrichten zur Flaechennormalen (12.11.2026,
statik3d/schalenlage.py).

Auftrag des Anwenders: „die lage von schalenelementen sollte der user frei
bestimmen können und sie dürfte grundsätzlich nicht an der berechnung
ändern“. Freigegeben: Alle Schalenelemente einer Flaeche werden zur Normalen
ihrer Flaeche (Randumlauf wie beim Vernetzen) ausgerichtet - beim Vernetzen,
beim Import, vor den Lastgeneratoren und vor jeder Rechnung. Was am Element in
seinen lokalen Achsen haengt (Elementlast in lokal z, dT_z, Schichtfolge und
Faserwinkel eines Laminats), dreht mit; Lasten auf der Flaeche werden neu
verteilt. Elemente ohne Flaeche werden je zusammenhaengendem Stueck zum
Element mit der kleinsten Nummer ausgerichtet.

Nachstellung am Stand eb88ecc: gelenkig gelagerte Platte 1 x 1 m, t = 10 mm,
8 x 8 shell4, Flaechenlast 10 kN/m² auf der Flaeche. Ungespiegelt w_Mitte =
2,10421 mm und ΣR_z = 10 000 N; ein Element gespiegelt 2,07988 mm und
9 687,5 N (die Last dieses Elements wirkt verkehrt herum), drei Elemente
1,92881 mm und 9 062,5 N.

Zwei Wege je Wert: dasselbe Modell ungespiegelt (gleiche Verschiebungen und
Auflagerkraefte bis auf Rundung) und die Navier-Loesung der gelenkig
gelagerten Quadratplatte w = 0,00406235 q a⁴ / D.

Aufruf:  python -m tests.test_schalenlage_ausrichten
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
A, T, E, NU, P = 1.0, 0.01, 210e9, 0.3, 1.0e4
#: so spiegelt der Anwender ein Element: Umlauf rueckwaerts, Knoten 0 bleibt
SPIEGEL = {"shell3": [0, 2, 1], "shell4": [0, 3, 2, 1], "shell6": [0, 2, 1, 5, 4, 3],
           "shell8": [0, 3, 2, 1, 7, 6, 5, 4]}
#: Spiegeln mit getauschten Knoten 0 und 1: z kehrt sich um, x bleibt auf der
#: Kante 0-1 (umgekehrt), y bleibt - fuer den Laminatvergleich, bei dem die
#: Faserrichtung an x haengt
TAUSCH01 = {"shell3": [1, 0, 2], "shell4": [1, 0, 3, 2], "shell6": [1, 0, 2, 3, 5, 4],
            "shell8": [1, 0, 3, 2, 4, 7, 6, 5]}
TYPEN = (("shell4", 1, False), ("shell8", 2, False), ("shell3", 1, True), ("shell6", 2, True))
GESPIEGELT = (5, 6, 20)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def _spiegeln(m, e, muster=None):
    el = m.elements[e]
    el.nodes = [el.nodes[j] for j in (muster or SPIEGEL)[el.typ]]


def _normale(m, e):
    X = m.nodes[m.elements[e].nodes[:3]]
    n = np.cross(X[1] - X[0], X[2] - X[0])
    return n / np.linalg.norm(n)


def platte(ordnung=1, dreiecke=False, spiegel=(), prop=None, n=8, dT=0.0, nach_verteilen=False,
           muster=None):
    """Gelenkig gelagerte Quadratplatte a = 1 m aus der Flaeche F (Rand
    gegen den Uhrzeigersinn, Normale +z), Flaechenlast P auf F."""
    from statik3d.model import Model, Material, ShellProp
    from statik3d import mesher
    m = Model("P")
    m.add_material(Material("S", E=E, nu=NU, rho=0.0, fy=355e6, alpha=1.2e-5))
    m.add_shell_prop(ShellProp("t", T))
    for p in (prop or []):
        m.add_shell_prop(p)
    m.add_nodes([[0, 0, 0], [A, 0, 0], [A, A, 0], [0, A, 0]])
    for i in range(4):
        m.add_line(f"L{i + 1}", [i, (i + 1) % 4], "polyline")
    f = m.add_flaeche("F", ["L1", "L2", "L3", "L4"], material="S", dicke="t", teilung=[n, n])
    mesher.mesh_flaeche(m, f, dreiecke=dreiecke, ordnung=ordnung)
    X = m.nodes
    for k in range(m.nn):
        x, y = X[k, 0], X[k, 1]
        if min(x, A - x, y, A - y) < 1e-9:
            m.fix(k, [2])
    m.fix(0, [0, 1])
    m.fix(1, [1])
    m.fix(3, [0])
    if not nach_verteilen:
        for e in spiegel:
            _spiegeln(m, f.elemente[e], muster)
    m.add_geometrielast("F", P)
    if dT:
        m.add_geometrielast("F", lastart="temperatur", dT=dT)
    m.lasten_verteilen()
    if nach_verteilen:
        for e in spiegel:
            _spiegeln(m, f.elemente[e], muster)
    return m, f


def _mitte(m):
    return int(np.argmin(np.linalg.norm(m.nodes - [A / 2, A / 2, 0], axis=1)))


def _abw(r1, r2):
    du = float(np.max(np.abs(r1.u - r2.u))) / float(np.max(np.abs(r1.u)))
    dr = float(np.max(np.abs(r1.reactions - r2.reactions))) / float(np.max(np.abs(r1.reactions)))
    return du, dr


# --------------------------------------------------------------------------
def test_wenden_je_typ():
    """Das Umdrehen selbst: z kehrt sich um, die lokale x-Achse bleibt auf
    ihrer Kante und kehrt sich ebenfalls um (Knoten 0 und 1 tauschen), y
    bleibt. Die Steifigkeit ist dieselbe (umnummeriert)."""
    try:
        from statik3d import schalenlage as SL
    except ImportError as ex:
        check("Modul statik3d.schalenlage vorhanden", False, str(ex))
        return
    from statik3d.elements import shell_rm
    ecken3 = np.array([[0.0, 0, 0], [1.2, 0.1, 0], [0.3, 0.9, 0]])
    ecken4 = np.array([[0.0, 0, 0], [1.1, 0.05, 0], [1.2, 0.8, 0], [-0.1, 0.9, 0]])

    def mitten(P, kanten):
        return np.array([0.5 * (P[a] + P[b]) for a, b in kanten])
    P = {"shell3": ecken3, "shell4": ecken4,
         "shell6": np.vstack([ecken3, mitten(ecken3, [(0, 1), (1, 2), (2, 0)])]),
         "shell8": np.vstack([ecken4, mitten(ecken4, [(0, 1), (1, 2), (2, 3), (3, 0)])])}
    for typ, X in P.items():
        w = SL.WENDEN[typ]
        T0 = shell_rm.schalen_frame(X)[0]
        T1 = shell_rm.schalen_frame(X[w])[0]
        ok_ach = (np.allclose(T1[2], -T0[2]) and np.allclose(T1[0], -T0[0]) and np.allclose(T1[1], T0[1]))
        K0 = shell_rm.k_schale(typ, X, E, NU, T)
        K1 = shell_rm.k_schale(typ, X[w], E, NU, T)
        idx = np.concatenate([np.arange(6 * j, 6 * j + 6) for j in w])
        dk = float(np.max(np.abs(K1 - K0[np.ix_(idx, idx)]))) / float(np.max(np.abs(K0)))
        # die Seitenmitten bleiben Mitten ihrer Kanten
        ok_mitte = True
        if typ in ("shell6", "shell8"):
            ne = 3 if typ == "shell6" else 4
            Q = X[w]
            ok_mitte = all(np.allclose(Q[ne + k], 0.5 * (Q[k] + Q[(k + 1) % ne])) for k in range(ne))
        check(f"{typ}: gewendet z' = -z, x' = -x, y' = y, Seitenmitten passend, K gleich",
              ok_ach and ok_mitte and dk < 1e-10, f"|ΔK|/|K| = {dk:.1e}")


def test_platte_gespiegelt():
    """Gespiegelte Elemente in einer vernetzten Flaeche: beim Rechnen
    ausgerichtet - Verschiebungen und Auflagerkraefte wie ungespiegelt, ΣR_z =
    P a², w_Mitte wie Navier (Weg 2)."""
    from statik3d import solver
    D = E * T ** 3 / (12 * (1 - NU ** 2))
    w_navier = 0.00406235 * P * A ** 4 / D
    for typ, o, dr in TYPEN:
        m0, _f0 = platte(o, dr)
        r0 = solver.solve_static(m0)
        for nach in (False, True):
            m1, f1 = platte(o, dr, GESPIEGELT, nach_verteilen=nach)
            r1 = solver.solve_static(m1)
            du, drr = _abw(r0, r1)
            w = float(r1.u[_mitte(m1), 2])
            rz = float(-r1.reactions[:, 2].sum())
            einheitlich = all(_normale(m1, e)[2] > 0.999 for e in f1.elemente)
            wann = "nach dem Verteilen" if nach else "vor dem Verteilen"
            check(f"{typ}: 3 Elemente {wann} gespiegelt - u und R wie ungespiegelt",
                  du < 1e-8 and drr < 1e-8, f"Δu {du:.1e}, ΔR {drr:.1e}")
            check(f"{typ}: … ΣR_z = P a² = 10 000 N, w_Mitte wie Navier ±2 %, alle Normalen +z",
                  abs(rz - P * A * A) < 1e-6 * P and abs(w / w_navier - 1) < 0.02 and einheitlich,
                  f"ΣR_z {rz:.3f} N, w {w * 1e3:.5f} mm, Navier {w_navier * 1e3:.5f} mm")


def test_elementlast_und_dTz():
    """Elementlast in lokal z und dT_z an einem gespiegelten Element wirken
    nach dem Ausrichten physikalisch gleich: Modell B traegt am gespiegelten
    Element -p und -dT_z (dieselbe Last wie +p, +dT_z am ungespiegelten
    Element in A). Dazu die Flaechenlast, die nur nach dem Ausrichten
    stimmt."""
    from statik3d import solver
    k = 5
    for typ, o, dr in (("shell4", 1, False), ("shell8", 2, False), ("shell3", 1, True)):
        mA, fA = platte(o, dr)
        mA.load_face(fA.elemente[k], 3.0e4)
        mA.load_temp(fA.elemente[k], 0.0, dT_z=25.0)
        mB, fB = platte(o, dr, (k,), nach_verteilen=True)
        mB.load_face(fB.elemente[k], -3.0e4)
        mB.load_temp(fB.elemente[k], 0.0, dT_z=-25.0)
        rA = solver.solve_static(mA)
        rB = solver.solve_static(mB)
        du, drr = _abw(rA, rB)
        lc = mB.case()
        fl = [x for x in lc.face_loads if x.elem == fB.elemente[k] and not getattr(x, "_geo", False)]
        tl = [x for x in lc.temp_loads if x.elem == fB.elemente[k]]
        check(f"{typ}: Elementlast lokal z und ΔT_z am gespiegelten Element - u und R wie ungespiegelt",
              du < 1e-8 and drr < 1e-8, f"Δu {du:.1e}, ΔR {drr:.1e}")
        check(f"{typ}: … nach dem Ausrichten p = +30 kN/m², ΔT_z = +25 K, Normale +z",
              len(fl) == 1 and abs(fl[0].p - 3.0e4) < 1e-9 and len(tl) == 1
              and abs(tl[0].dT_z - 25.0) < 1e-12 and _normale(mB, fB.elemente[k])[2] > 0.999,
              f"p {[x.p for x in fl]}, ΔT_z {[x.dT_z for x in tl]}")


def test_laminat_unsymmetrisch():
    """Unsymmetrisches Laminat mit schraeger orthotroper Lage: in B ist das
    Element mit getauschten Knoten 0 und 1 gespiegelt (z' = -z, x' = -x,
    y' = y) und traegt den Aufbau in umgekehrter Folge mit -winkel - also
    physikalisch denselben. Nach dem Ausrichten ist es derselbe Aufbau wie in
    A, die Rechnung gleich (mit Flaechenlast und Temperatur, die die
    Kopplung B != 0 weckt).

    C: gespiegelt wie ein Anwender (Umlauf rueckwaerts, Knoten 0 bleibt) mit
    dem Aufbau L - der steht dann physikalisch verkehrt. Weg 2 (D) von Hand:
    das Element ungespiegelt mit dem Aufbau, den L am gespiegelten Element
    darstellt (Folge umgekehrt, Winkel g - a, siehe unten)."""
    from statik3d import solver
    from statik3d.model import ShellProp
    unten = {"t": 0.004, "E": 210e9, "nu": 0.3, "winkel": 0.0}
    oben = {"t": 0.006, "E1": 70e9, "E2": 10e9, "nu12": 0.3, "G12": 5e9, "G13": 5e9, "G23": 4e9,
            "winkel": 0.5}
    gewendet = [dict(oben, winkel=-0.5), dict(unten, winkel=-0.0)]
    k = 5
    for typ, o, dr in (("shell4", 1, False), ("shell8", 2, False), ("shell6", 2, True)):
        props = [ShellProp("L", 0.01, lagen=[unten, oben]), ShellProp("L umgekehrt", 0.01, lagen=gewendet)]
        mA, fA = platte(o, dr, prop=props, dT=30.0)
        for e in fA.elemente:
            mA.elements[e].sec = "L"
        mB, fB = platte(o, dr, (k,), prop=props, dT=30.0, nach_verteilen=True, muster=TAUSCH01)
        for e in fB.elemente:
            mB.elements[e].sec = "L"
        mB.elements[fB.elemente[k]].sec = "L umgekehrt"
        rA = solver.solve_static(mA)
        rB = solver.solve_static(mB)
        du, drr = _abw(rA, rB)
        check(f"{typ}: unsymmetrisches Laminat, Element gespiegelt mit umgekehrtem Aufbau - u, R wie A",
              du < 1e-8 and drr < 1e-8, f"Δu {du:.1e}, ΔR {drr:.1e}")
        check(f"{typ}: … nach dem Ausrichten traegt es wieder den Aufbau L",
              mB.elements[fB.elemente[k]].sec == "L", mB.elements[fB.elemente[k]].sec)
        # Gegenrichtung: gespiegelt mit L (der Aufbau steht dann physikalisch
        # verkehrt) - das Ausrichten legt einen gewendeten Aufbau an und
        # aendert die Rechnung nicht. Zwei Aufbauten: isotrop unsymmetrisch
        # (Stahl 4 mm unten, Aluminium 6 mm oben; exakt) und mit der
        # orthotropen Lage - dort liegt die x-Achse des ausgerichteten
        # Elements an einer anderen Kante als im Weg von Hand, und die
        # Rechnung mit orthotropem Aufbau haengt schon vor dieser Kur um
        # 1e-5 bis 1e-4 von der Wahl der x-Achse ab (gemessen mit zyklisch
        # verschobenen Knoten ohne Spiegeln); Grenze darum 1e-3, falsch
        # gewendet waeren es 2e-2 bis 9e-2.
        from statik3d import schalenlage as SL
        from statik3d.elements import shell_rm
        alu = {"t": 0.006, "E": 70e9, "nu": 0.33, "winkel": 0.0}
        for art, lagen, grenze in (("isotrop", [unten, alu], 1e-8), ("orthotrop", [unten, oben], 1e-3)):
            pL = [ShellProp("L", 0.01, lagen=lagen)]
            mC, fC = platte(o, dr, (k,), prop=pL, dT=30.0, nach_verteilen=True)
            for e in fC.elemente:
                mC.elements[e].sec = "L"
            mD, fD = platte(o, dr, (), prop=pL, dT=30.0)
            for e in fD.elemente:
                mD.elements[e].sec = "L"
            # gespiegelt liegt x' an der Kante zu Knoten SPIEGEL[1] (Winkel g
            # zur alten x-Achse), z' = -z, y' = z' x x'; die Faser
            # cos a x' + sin a y' liegt bei g - a, die Folge kehrt sich um
            el = mD.elements[fD.elemente[k]]
            X = mD.nodes[el.nodes]
            T0 = shell_rm.schalen_frame(X)[0]
            v = X[SPIEGEL[el.typ][1]] - X[0]
            g = float(np.arctan2(v @ T0[1], v @ T0[0]))
            von_hand = [dict(x, winkel=g - float(x.get("winkel", 0.0))) for x in reversed(lagen)]
            mD.add_shell_prop(ShellProp("L von Hand", 0.01, lagen=von_hand))
            el.sec = "L von Hand"
            rC = solver.solve_static(mC)
            rD = solver.solve_static(mD)
            du, drr = _abw(rD, rC)
            neu = mC.shells.get(mC.elements[fC.elemente[k]].sec)
            soll_w = [-float(x.get("winkel", 0.0)) for x in reversed(lagen)]
            check(f"{typ}: gespiegelt mit L ({art}) - gewendeter Aufbau angelegt, Rechnung wie von Hand "
                  f"gewendet (Grenze {grenze:g})",
                  du < grenze and drr < grenze and neu is not None and neu.name != "L"
                  and np.allclose([x.get("winkel", 0.0) for x in neu.lagen], soll_w, atol=1e-12)
                  and SL.schalen_ausrichten(mC) == [],
                  f"Δu {du:.1e}, ΔR {drr:.1e}, Aufbau {neu.name if neu else None}")


def test_meldung():
    """Die Meldung nennt Flaeche und Elementnummern (ab 0); ein zweiter
    Aufruf findet nichts mehr."""
    try:
        from statik3d import schalenlage as SL
    except ImportError as ex:
        check("Meldung: Modul statik3d.schalenlage vorhanden", False, str(ex))
        return
    m, f = platte(1, False, GESPIEGELT)
    nummern = [f.elemente[e] for e in GESPIEGELT]
    z = SL.schalen_ausrichten(m)
    text = " ".join(z)
    check("Meldung nennt Fläche F und die Elemente 5, 6, 20",
          len(z) == 1 and "Fläche F" in text and ", ".join(str(x) for x in nummern) in text, text)
    check("… zweiter Aufruf: nichts mehr umzudrehen", SL.schalen_ausrichten(m) == [])
    # ueber die Rechnung: die Meldung steht im Ergebnis und im Fortschritt
    from statik3d import solver
    m2, _f2 = platte(1, False, GESPIEGELT)
    zeilen = []
    r = solver.solve_static(m2, progress=lambda t, *a: zeilen.append(str(t)))
    im_info = " ".join(r.info.get("schalenlage", []) or [])
    check("… die Rechnung meldet es im Ergebnis und im Fortschritt",
          "Fläche F" in im_info and any("Fläche F" in z_ and "5, 6, 20" in z_ for z_ in zeilen), im_info)


BDF = """\
$ Zwei getrennte Stuecke aus Schalen, Elemente teils verkehrt herum
GRID,1,,0.0,0.0,0.0
GRID,2,,1.0,0.0,0.0
GRID,3,,2.0,0.0,0.0
GRID,4,,0.0,1.0,0.0
GRID,5,,1.0,1.0,0.0
GRID,6,,2.0,1.0,0.0
GRID,7,,0.0,2.0,0.0
GRID,8,,1.0,2.0,0.0
GRID,9,,2.0,2.0,0.0
GRID,11,,5.0,0.0,0.0
GRID,12,,6.0,0.0,0.0
GRID,13,,6.0,1.0,0.0
GRID,14,,5.0,1.0,0.0
GRID,15,,7.0,0.0,0.0
GRID,16,,7.0,1.0,0.0
CQUAD4,1,1,1,2,5,4
CQUAD4,2,1,2,3,6,5
CQUAD4,3,1,4,7,8,5
CQUAD4,4,1,5,6,9,8
CQUAD4,21,1,11,14,13,12
CTRIA3,22,1,12,15,16
CTRIA3,23,1,12,16,13
PSHELL,1,1,0.01,1
MAT1,1,2.1+11,,0.3,7850.0
PLOAD4,1,1,1000.0
PLOAD4,1,2,1000.0
PLOAD4,1,3,1000.0
PLOAD4,1,4,1000.0
PLOAD4,1,22,500.0
ENDDATA
"""


def test_nastran_stueckweise():
    """Ein Nastran-Netz ohne Flaechen: je zusammenhaengendem Stueck zum
    Element mit der kleinsten Nummer ausgerichtet, mit Meldung. Stueck 1:
    Element 2 (EID 3) liegt verkehrt (Normale -z); Stueck 2: das kleinste
    Element (EID 21) zeigt nach -z, EID 22 und 23 nach +z. Die PLOAD4-Lasten
    behalten ihre physikalische Richtung: ΣF_z = 2000 N (3 x +1000 - 1000) in
    Stueck 1 und +250 N (500 N/m² auf 0,5 m²) in Stueck 2."""
    from statik3d.importers import import_file
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "stuecke.bdf")
        with open(p, "w") as fh:
            fh.write(BDF)
        log = []
        m = import_file(p, log=log)
    nz = {i: _normale(m, i)[2] for i in range(len(m.elements))}
    stueck1 = [0, 1, 2, 3]
    stueck2 = [4, 5, 6]

    def kraft(elems):
        F = np.zeros(3)
        for lc in m.load_cases.values():
            for fl in lc.face_loads:
                if fl.elem in elems:
                    X = m.nodes[m.elements[fl.elem].nodes]
                    if len(X) == 4:
                        n = 0.5 * np.cross(X[2] - X[0], X[3] - X[1])
                    else:
                        n = 0.5 * np.cross(X[1] - X[0], X[2] - X[0])
                    F += fl.p * n
        return F
    text = " ".join(str(z) for z in log)
    check("Nastran: Stück 1 einheitlich zu Element 0 (+z), Stück 2 zu Element 4 (-z)",
          all(nz[i] > 0.999 for i in stueck1) and all(nz[i] < -0.999 for i in stueck2),
          str({i: round(v, 3) for i, v in nz.items()}))
    check("Nastran: PLOAD4 behält die Richtung - ΣF_z 2000 N und 250 N",
          abs(kraft(stueck1)[2] - 2000.0) < 1e-9 and abs(kraft(stueck2)[2] - 250.0) < 1e-9,
          f"{kraft(stueck1)[2]:.3f} N, {kraft(stueck2)[2]:.3f} N")
    check("Nastran: Meldung nennt die Elemente 2 sowie 5, 6 und die Bezugselemente 0 und 4",
          "ohne Fläche" in text and "Element 0" in text and "Element 4" in text
          and "2" in text and "5, 6" in text, text[-400:])


def test_lastgenerator_und_vernetzen():
    """Wasserdruck und Wind richten die Schalen vor dem Erzeugen aus; das
    Vernetzen liefert einheitliche Elemente (auch frei vernetzt, gemeinsame
    Randlinien)."""
    try:
        from statik3d import schalenlage as SL
    except ImportError as ex:
        check("Lastgenerator: Modul statik3d.schalenlage vorhanden", False, str(ex))
        return
    from statik3d import wasserdruck as WD, wind as WI
    import inspect
    check("Wasserdruck und Wind rufen das Ausrichten zu Beginn von lasten_erzeugen",
          "schalen_ausrichten" in inspect.getsource(WD.lasten_erzeugen)
          and "schalen_ausrichten" in inspect.getsource(WI.lasten_erzeugen))
    from statik3d import mesher
    m, f = platte(1, False)
    m.netz.form = 0
    mesher.modell_vernetzen(m, [])
    check("Vernetzen: alle Elemente der Fläche zeigen zur Flächennormalen",
          f.elemente and all(_normale(m, e)[2] > 0.999 for e in f.elemente) and SL.schalen_ausrichten(m) == [],
          f"{len(f.elemente)} Elemente")


def test_verfahrenstabelle():
    """Stand 31 als Fehlerkorrektur; betroffen nur Modelle mit uneinheitlich
    orientierten Schalen."""
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("schalenlage")
    m_gut, _ = platte(1, False)
    m_schlecht, _ = platte(1, False, (5,))
    check("Verfahrenstabelle: „schalenlage“ Stand 31, Fehlerkorrektur",
          mk is not None and mk.wechsel[-1].stand == 31 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.VERFAHRENSSTAND >= 31, f"Stand {rv.VERFAHRENSSTAND}")
    check("… betroffen: ein Element gespiegelt ja, einheitlich nein",
          mk is not None and mk.betrifft(m_schlecht) and not mk.betrifft(m_gut))


def main():
    for t in (test_wenden_je_typ, test_platte_gespiegelt, test_elementlast_und_dTz,
              test_laminat_unsymmetrisch, test_meldung, test_nastran_stueckweise,
              test_lastgenerator_und_vernetzen, test_verfahrenstabelle):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
