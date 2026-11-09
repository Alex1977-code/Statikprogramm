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
    for t in (test_schraege_ebene, test_gleiche_feder, test_zylinder, test_trennflaeche, test_unvernetzt):
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
