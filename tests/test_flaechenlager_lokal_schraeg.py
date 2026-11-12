"""
Flaechenlager in Flaechenachsen auf schraegen, gekruemmten und beidseitigen
Flaechen (Befunde A12 und A13 der Pruefagenten, Entscheidung des Anwenders
vom 09.11.2026).

Ein Flaechenlager in Flaechenachsen wirkt je Flaeche entlang EINER globalen
Achse (supports.normalengruppen). Weicht die Normale der Flaeche um mehr als
1 Grad von dieser Achse ab, ist die Lagerrichtung falsch. Bis zum 09.11.2026
stand das nur im Protokoll der Vernetzung, gerechnet wurde trotzdem. Jetzt
meldet Model.check einen FEHLER, und alle Aufrufer sperren damit die Rechnung.

S  Starrer Quader 2 x 1 x 0,5 m, um die y-Achse geneigt, auf Bettung in
   Flaechenachsen (Normale c_n, in der Flaeche c_n/10), Last senkrecht.
   Soll: Starrkoerper auf Winkler-Bettung mit der WAHREN Normalen,
   K = Int B^T D B dA (Gauss 3 x 3, exakt). Bei 0 und 0,5 Grad kein FEHLER
   und die Rechnung trifft das Soll auf 1 %; bei 10 Grad FEHLER mit dem
   Winkel - die Rechnung laege dort um mehr als 5 Grad in der Richtung
   daneben (Beleg, warum gesperrt wird).
G  Dieselbe schraege Flaeche mit gleicher Feder in allen drei Richtungen:
   kein FEHLER (die Achse spielt keine Rolle), und die Rechnung trifft das
   Soll mit D = c*I. Dasselbe Lager auf globalen Achsen: kein FEHLER.
Z  Zylinder mit radialer Bettung auf dem Mantel: FEHLER „gekrümmt“.
T  Zwei Bloecke mit gemeinsamer Trennflaeche, die Trennflaeche im Lager:
   FEHLER „zwischen den Körpern“ (die Facetten zeigen nach beiden Seiten).
P  Schalenplatte 4 x 3 m (shell4, shell8) in mehreren Hoehen, senkrecht und
   0,7 Grad geneigt: kein FEHLER (Befund 4 vom 11.11.2026); 10 Grad: FEHLER;
   ein Element von Hand gespiegelt: seit dem 12.11.2026 kein FEHLER mehr
   und dieselben Lagerknoten und Auflagerkraefte wie ungespiegelt
   (Anwender: „die lage von schalenelementen sollte der user frei bestimmen
   können und sie dürfte grundsätzlich nicht an der berechnung ändern“).
U  Unvernetztes Modell: die Pruefung bleibt still und wirft nichts.

Aufruf:  python -m tests.test_flaechenlager_lokal_schraeg
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []

KANTEN = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
SEITEN = {"Boden": ["K1", "K2", "K3", "K4"], "Deckel": ["K5", "K6", "K7", "K8"],
          "S1": ["K1", "K10", "K5", "K9"], "S2": ["K2", "K11", "K6", "K10"],
          "S3": ["K3", "K12", "K7", "K11"], "S4": ["K4", "K9", "K8", "K12"]}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


def _fehler(m, lager):
    return [z for z in m.check() if z.startswith("FEHLER") and f"Flächenlager '{lager}'" in z]


def _skew(v):
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])


def _quader(alpha_grad, cn=1e8, ct=None, lokal=True, vernetzen=True):
    """Geneigter starrer Quader auf Bettung; Rueckgabe (Modell, Drehmatrix)."""
    from statik3d.model import Model, Material, DofBehaviour
    from statik3d import mesher, supports
    a = np.radians(alpha_grad)
    R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    P = np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0],
                  [0, 0, .5], [2, 0, .5], [2, 1, .5], [0, 1, .5]], float) @ R.T
    m = Model("Klotz")
    m.add_material(Material("M", E=210e12, nu=0.0))
    m.add_nodes(P)
    for i, (p, q) in enumerate(KANTEN):
        m.add_line(f"K{i + 1}", [p, q])
    for n, ls in SEITEN.items():
        m.add_flaeche(n, ls, material="M")
    m.add_koerper("V1", list(SEITEN), material="M")
    m.netz.ziellaenge = 0.25
    m.netz.ordnung = 1
    m.netz.intelligent = False
    ct = cn / 10 if ct is None else ct
    ss = m.add_surface_support(name="S")
    ss.flaechen = ["Boden"]
    ss.lokal = lokal
    ss.behaviour[2] = DofBehaviour("spring", cn)
    ss.behaviour[0] = DofBehaviour("spring", ct)
    ss.behaviour[1] = DofBehaviour("spring", ct)
    if vernetzen:
        mesher.modell_vernetzen(m, [], workers=1)
        supports.lager_auf_netz(m, [])
    return m, R


def _ist_soll(m, R, cn=1e8, ct=None, P=100e3):
    """Mittlere Verschiebung aller Knoten: Rechnung und Starrkoerper-Soll [m]."""
    import contextlib
    import io
    from statik3d import solver
    ct = cn / 10 if ct is None else ct
    nn = m.nn
    for i in range(nn):
        m.load_node(i, Fz=-P / nn)
    r = solver.solve_static(m, workers=1)
    n = R @ np.array([0, 0, -1.0])
    D = cn * np.outer(n, n) + ct * (np.eye(3) - np.outer(n, n))
    x0 = m.nodes.mean(axis=0)
    g, w = np.polynomial.legendre.leggauss(3)
    K = np.zeros((6, 6))
    for gi, wi in zip(g, w):
        for gj, wj in zip(g, w):
            p = R @ np.array([1 + gi, 0.5 + 0.5 * gj, 0.0])
            B = np.hstack([np.eye(3), -_skew(p - x0)])
            K += B.T @ D @ B * wi * wj * 1.0 * 0.5
    F = np.zeros(6)
    F[2] = -P
    F[3:] = np.cross(m.nodes - x0, np.tile([0, 0, -P / nn], (nn, 1))).sum(axis=0)
    return r.u[:, :3].mean(axis=0), np.linalg.solve(K, F)[:3]


def _winkel(a, b):
    c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def test_schraege_ebene():
    for alpha in (0.0, 0.5):
        m, R = _quader(alpha)
        f = _fehler(m, "S")
        ist, soll = _ist_soll(m, R)
        abw = abs(np.linalg.norm(ist) / np.linalg.norm(soll) - 1) * 100
        check(f"S Quader {alpha:g}° geneigt: kein FEHLER, |u| trifft das Soll auf 1 %",
              not f and abw < 1.0, f"|u| {np.linalg.norm(ist) * 1e3:.4f} mm, Soll {np.linalg.norm(soll) * 1e3:.4f} mm")
    m, R = _quader(10.0)
    f = _fehler(m, "S")
    check("S Quader 10° geneigt: genau ein FEHLER, nennt Fläche, Winkel 10,0° und Achse z",
          len(f) == 1 and "Fläche Boden" in f[0] and "10,0° schräg zur Achse z" in f[0], f[0][:110] if f else "kein FEHLER")
    check("… und sagt, was zu tun ist (Fläche herausnehmen oder globale Achsen)",
          len(f) == 1 and "Nehmen Sie die Fläche aus dem Lager" in f[0] and "globale Achsen" in f[0])
    ist, soll = _ist_soll(m, R)
    w = _winkel(ist, soll)
    check("… Beleg: die Rechnung läge in der Richtung um mehr als 5° neben dem Soll",
          w > 5.0, f"Winkel Ist/Soll {w:.1f}°".replace(".", ","))
    m, R = _quader(1.5)
    check("S Quader 1,5° geneigt: FEHLER (Grenze 1°)", len(_fehler(m, "S")) == 1)


def test_gleiche_feder():
    m, R = _quader(10.0, ct=1e8)
    f = _fehler(m, "S")
    ist, soll = _ist_soll(m, R, ct=1e8)
    abw = float(np.linalg.norm(ist - soll) / np.linalg.norm(soll)) * 100
    check("G 10° geneigt, gleiche Feder in allen drei Richtungen: kein FEHLER, u trifft das Soll auf 1 %",
          not f and abw < 1.0, f"Abweichung {abw:.3f} %".replace(".", ","))
    m, R = _quader(10.0, lokal=False)
    check("G 10° geneigt, Lager auf globalen Achsen: kein FEHLER", not _fehler(m, "S"))


def test_zylinder():
    from statik3d.model import Model, Material, DofBehaviour
    from statik3d import mesher
    r, h = 0.05, 0.3
    m = Model("Zyl")
    m.add_material(Material("M", E=210e12, nu=0.0))

    def kreis(tag, z):
        p = m.add_node(-r, 0, z)
        q = m.add_node(r, 0, z)
        m.add_line(tag + "1", [p, q], "arc", punkte=[(-r, 0, z), (0, r, z), (r, 0, z)])
        m.add_line(tag + "2", [q, p], "arc", punkte=[(r, 0, z), (0, -r, z), (-r, 0, z)])
        return p, q, tag + "1", tag + "2"
    pu, qu, u1, u2 = kreis("U", 0.0)
    po, qo, o1, o2 = kreis("O", h)
    m.add_line("V1", [pu, po])
    m.add_line("V2", [qu, qo])
    m.add_flaeche("M1", [u1, "V2", o1, "V1"], material="M")
    m.add_flaeche("M2", [u2, "V1", o2, "V2"], material="M")
    m.add_flaeche("Bo", [u1, u2], material="M")
    m.add_flaeche("De", [o1, o2], material="M")
    m.add_koerper("Z", ["Bo", "De", "M1", "M2"], material="M")
    m.netz.ziellaenge = 0.02
    m.netz.dichte = "eigene"
    ss = m.add_surface_support(name="Radial")
    ss.flaechen = ["M1", "M2"]
    ss.lokal = True
    ss.behaviour[2] = DofBehaviour("spring", 1e9)
    mesher.modell_vernetzen(m, [], workers=1)
    f = _fehler(m, "Radial")
    check("Z Zylindermantel radial gebettet: je Mantelfläche ein FEHLER „gekrümmt“",
          len(f) == 2 and all("ist gekrümmt" in z for z in f) and "Fläche M1" in f[0] and "Fläche M2" in f[1],
          f[0][:100] if f else "kein FEHLER")
    ss.flaechen = ["Bo"]
    from statik3d import supports
    supports.lager_auf_netz(m, [])
    check("Z ebener Boden desselben Zylinders im Lager: kein FEHLER", not _fehler(m, "Radial"))


def test_trennflaeche():
    from statik3d.model import Model, Material, DofBehaviour
    from statik3d import mesher
    m = Model("B")
    m.add_material(Material.steel("S235"))
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
                  [0, 0, 2], [1, 0, 2], [1, 1, 2], [0, 1, 2.]])
    m.add_nodes(P)
    z = [0]

    def L(a, c):
        z[0] += 1
        m.add_line(f"L{z[0]}", [a, c])
        return f"L{z[0]}"
    R = [[L(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4, 8)]
    V01 = [L(i, i + 4) for i in range(4)]
    V12 = [L(i + 4, i + 8) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Dach", R[2], material="S235")
    m.add_flaeche("Fuge", R[1], material="S235")
    un = [m.add_flaeche(f"MU{i}", [R[0][i], V01[(i + 1) % 4], R[1][i], V01[i]], material="S235").name
          for i in range(4)]
    ob = [m.add_flaeche(f"MO{i}", [R[1][i], V12[(i + 1) % 4], R[2][i], V12[i]], material="S235").name
          for i in range(4)]
    m.add_koerper("Unten", ["Boden", "Fuge"] + un, material="S235")
    m.add_koerper("Oben", ["Fuge", "Dach"] + ob, material="S235")
    m.netz.ziellaenge = 0.5
    ss = m.add_surface_support(name="Halt")
    ss.flaechen = ["Boden", "Fuge"]
    ss.lokal = True
    ss.behaviour[2] = DofBehaviour("rigid", failure="zug")
    mesher.modell_vernetzen(m, [], workers=1)
    f = _fehler(m, "Halt")
    check("T Trennfläche zweier Körper im Lager: ein FEHLER, nennt Fläche und beide Körper; Boden bleibt frei davon",
          len(f) == 1 and "Fläche Fuge" in f[0] and "zwischen den Körpern Oben und Unten" in f[0],
          f[0][:120] if f else "kein FEHLER")


def _platte(ordnung=1, z0=0.0, neig_grad=0.0, ebene="xy"):
    """Schalenplatte 4 x 3 m (shell4/shell8) auf Hoehe z0, um y geneigt, im
    Flaechenlager in Flaechenachsen mit Ausfall bei Zug (Befund 4)."""
    from statik3d.model import Model, Material, ShellProp, DofBehaviour
    from statik3d import mesher
    import contextlib
    import io
    a = np.radians(neig_grad)
    m = Model("P")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.01))
    m.netz.ordnung = ordnung
    E = np.array([[0, 0, 0], [4, 0, 0], [4, 3, 0], [0, 3, 0]], float)
    E[:, 2] = z0 + E[:, 0] * np.tan(a)
    if ebene == "yz":                  # senkrechte Platte, Normale x
        E = E[:, [2, 0, 1]]
    m.add_nodes(E)
    for i in range(4):
        m.add_line(f"L{i}", [i, (i + 1) % 4])
    m.add_flaeche("P", [f"L{i}" for i in range(4)], material="S235", dicke="t10")
    ss = m.add_surface_support(name="B")
    ss.flaechen = ["P"]
    ss.lokal = True
    ss.behaviour[2] = DofBehaviour("rigid", failure="zug")
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1)
    return m


def test_schalenplatte():
    """Befund 4 (11.11.2026): die Normale einer Schale kommt aus ihrer
    Knotenreihenfolge, nicht aus Knoten in ihrer eigenen Ebene. Bis dahin
    zeigten auf z = 0,37 bei shell4 37 von 130 Facetten nach +z, der Rest
    nach -z, und Model.check sperrte die Rechnung mit „Facetten nach beiden
    Seiten“."""
    from statik3d import supports
    for ordnung in (1, 2):
        for z0, neig, ebene in ((0.0, 0.0, "xy"), (0.37, 0.0, "xy"), (-1.25, 0.0, "xy"), (3.0, 0.0, "xy"),
                                (0.13, 0.7, "xy"), (0.37, 0.0, "yz")):
            m = _platte(ordnung, z0, neig, ebene)
            f = _fehler(m, "B")
            _fac, N, _s = supports._facettennormalen(m, m.flaechen["P"])
            N = np.asarray(N)
            ach = 2 if ebene == "xy" else 0
            plus, minus = int((N[:, ach] > 0).sum()), int((N[:, ach] < 0).sum())
            typ = sorted({e.typ for e in m.elements})
            check(f"P {typ[0]} Platte {ebene} auf {z0:g} m, {neig:g}° geneigt: alle Facetten eine Seite, kein FEHLER",
                  not f and min(plus, minus) == 0 and len(N) > 0,
                  f"+{'xyz'[ach]} {plus}, -{'xyz'[ach]} {minus}" + (f"; {f[0][:70]}" if f else ""))
            g = supports.normalengruppen(m, [m.flaechen["P"]], log=[])
            check(f"… normalengruppen: eine Gruppe, Achse {'xyz'[ach]}",
                  len(g) == 1 and g[0][0] == ach, str([x[:2] for x in g]))
    # die echten Fehlerfaelle bleiben: schraeg ueber der Grenze
    m = _platte(1, 0.37, 10.0)
    f = _fehler(m, "B")
    check("P Schalenplatte 10° geneigt auf 0,37 m: FEHLER „schräg“ bleibt",
          len(f) == 1 and "10,0° schräg zur Achse z" in f[0], f[0][:90] if f else "kein FEHLER")
    # ein einzelnes Element von Hand gespiegelt: bis zum 12.11.2026 FEHLER
    # „Facetten nach beiden Seiten“. Die Lage der Schalenelemente waehlt der
    # Anwender frei; das Lager einer Schalenflaeche ohne Koerper liegt ohnehin
    # unten (normalengruppen) - kein FEHLER, und gerechnet wird gleich
    import contextlib
    import io
    from statik3d import solver
    for ordnung, perm in ((1, [0, 3, 2, 1]), (2, [0, 3, 2, 1, 7, 6, 5, 4])):
        erg = []
        for spiegeln in (False, True):
            m = _platte(ordnung, 0.37)
            m.fix(0, [0, 1, 5])
            m.fix(1, [1])
            el = m.elements[int(m.flaechen["P"].elemente[0])]
            if spiegeln:
                el.nodes = [el.nodes[i] for i in perm]
            f = _fehler(m, "B")
            g = supports.normalengruppen(m, [m.flaechen["P"]], log=[])
            R = np.zeros(1)
            if ordnung == 1:
                # shell8 rechnet am Flaechenlager nicht (QuadratischeSeiten) -
                # dort nur Meldung und Lagerknoten
                k = int(np.argmin(np.linalg.norm(m.nodes[:, :2] - [2.0, 1.5], axis=1)))
                m.load_node(k, Fz=-1e4)
                with contextlib.redirect_stdout(io.StringIO()):
                    r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
                R = np.asarray(r.reactions)[:, 2].copy()
            erg.append((f, g, R, el.typ))
        (f0, g0, R0, typ), (f1, g1, R1, _t) = erg
        gleich = (len(g0) == len(g1) == 1 and g0[0][:2] == g1[0][:2]
                  and sorted(g0[0][2]) == sorted(g1[0][2]))
        dR = float(np.abs(R1 - R0).max())
        check(f"P {typ}: ein Element gespiegelt: kein FEHLER, dieselben Lagerknoten"
              + (", Auflagerkräfte gleich" if ordnung == 1 else " (shell8 rechnet am Flächenlager nicht)")
              + " (vorher FEHLER „Facetten nach beiden Seiten“)",
              not f1 and not f0 and gleich and dR < 1e-6 * max(float(np.abs(R0).max()), 1.0)
              and (ordnung == 2 or abs(R1.sum() - 1e4) < 1e-6 * 1e4),
              (f1[0][:80] if f1 else "kein FEHLER") + f"; Gruppen {[x[:2] for x in g1]}; ΔR {dR:.2e} N, "
              f"ΣR {R1.sum():.1f} N")


def test_unvernetzt():
    m, _R = _quader(10.0, vernetzen=False)
    try:
        f = _fehler(m, "S")
        ok = not f
    except Exception as ex:          # noqa: BLE001
        ok, f = False, [str(ex)]
    check("U unvernetzt: die Prüfung bleibt still und wirft nichts", ok, f[0][:80] if f else "")
    from statik3d import supports
    check("U Grenze steht als Konstante im Lagermodul (1 Grad)", getattr(supports, "LOKAL_WINKEL_GRENZE", None) == 1.0)


def main():
    for t in (test_schraege_ebene, test_gleiche_feder, test_zylinder, test_trennflaeche, test_schalenplatte,
              test_unvernetzt):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
