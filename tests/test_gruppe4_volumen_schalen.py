"""
Gruppe 4 der Befundliste (Befunde A14, A15, A16, A19, A20 der Pruefagenten,
09.11.2026).

A14 Teilung [2, 3, 5] eines abgebildeten Quaders 2 x 0,1 x 0,2 m gilt in x, y,
    z, gleich in welcher Reihenfolge die Flaechen stehen (vorher folgte sie der
    Flaechenreihenfolge). Gezaehlt: verschiedene Koordinaten je Achse.
A15 Innendruck p auf eine gekruemmte Viertelzylinderseite (tet10): die Summe
    der Lastvektoren ist p mal die Projektion (Stokes) - unabhaengig von der
    Facettierung; zweiter Weg: Seite fuer Seite mit der oertlichen Normale
    (solid.flaechenlast_knoten ohne Richtung).
A16 Zwei Koerper mit eigenen, deckungsgleichen Trennflaechen ohne
    Kontaktbedingung: WARNUNG „Trennfläche doppelt“; mit gemeinsamer
    Trennflaeche keine.
A19 Schalenflaechen ohne gemeinsame Linie: Knoten auf der Linie einer
    anderen Flaeche und Rippe auf ungeteilter Platte - je eine WARNUNG, wenn
    das Netz dort nicht verbunden ist (Netz von frueher: jede Flaeche fuer
    sich); mit geteilter Linie bzw. Flaeche keine. Seit dem 09.11.2026 teilt
    der Vernetzer solche Stellen im Netz (tests/test_flaechen_teilen.py):
    neu vernetzt keine Warnung mehr. Die Abnahme sieht deshalb auf das Netz;
    vorher pruefte diese Stelle am unvernetzten Modell.
A20 Patchtest Zug 10 N/mm² in x auf einer Flaeche aus Dreiecken mit
    beliebig gedrehten Elementachsen: σ_x = 10, σ_y = 0 an jedem Knoten
    (vorher 0,8 bis 9,3); zweiter Weg die Hauptspannung σ_1 = 10 (invariant).
Dazu die Verfahrenstabelle Stand 18-20.

Aufruf:  python -m tests.test_gruppe4_volumen_schalen
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _quader(m, name, x0, x1, y0, y1, z0, z1, reihenfolge=None):
    P = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    b = m.nn
    m.add_nodes(np.asarray(P, float))
    z = [0]

    def L(a, c):
        z[0] += 1
        n = f"{name}L{z[0]}"
        m.add_line(n, [b + a, b + c])
        return n
    R0 = [L(i, (i + 1) % 4) for i in range(4)]
    R1 = [L(4 + i, 4 + (i + 1) % 4) for i in range(4)]
    V = [L(i, 4 + i) for i in range(4)]
    namen = [f"{name}B", f"{name}D"] + [f"{name}M{i}" for i in range(4)]
    m.add_flaeche(namen[0], R0, material="S235")
    m.add_flaeche(namen[1], R1, material="S235")
    for i in range(4):
        m.add_flaeche(namen[2 + i], [R0[i], V[(i + 1) % 4], R1[i], V[i]], material="S235")
    if reihenfolge == "umgedreht":
        namen = namen[::-1]
    elif reihenfolge == "gemischt":
        namen = [namen[2], namen[0], namen[5], namen[1], namen[3], namen[4]]
    return namen


def test_a14():
    from statik3d.model import Model, Material
    from statik3d import mesher
    erg = {}
    for art in ("normal", "umgedreht", "gemischt"):
        m = Model("Q")
        m.add_material(Material.steel("S235"))
        namen = _quader(m, "Q", 0, 2.0, 0, 0.1, 0, 0.2, art)
        m.add_koerper("Q", namen, material="S235")
        m.koerper["Q"].teilung = [2, 3, 5]
        m.netz.ziellaenge = 0.05
        mesher.modell_vernetzen(m, [], workers=1)
        X = np.asarray(m.nodes)
        erg[art] = [len(np.unique(np.round(X[:, d], 9))) - 1 for d in range(3)]
    check("A14 Teilung [2, 3, 5] in x, y, z bei jeder Flächenreihenfolge", all(v == [2, 3, 5] for v in erg.values()),
          str(erg))


def _a15_modell():
    from statik3d.model import Model, Material
    m = Model("Rohr")
    m.add_material(Material.steel("S235"))
    ri, ra, H = 0.1, 0.2, 0.02
    pk = {}

    def k(p):
        key = tuple(round(c, 9) for c in p)
        if key not in pk:
            pk[key] = m.add_node(*p)
        return pk[key]
    s2 = math.sqrt(0.5)
    namen = []
    for z in (0.0, H):
        for r in (ri, ra):
            a, c = k((r, 0, z)), k((0, r, z))
            m.add_line(f"B{r}{z}", [a, c], "arc", punkte=[(r, 0, z), (r * s2, r * s2, z), (0, r, z)])
    for r in (ri, ra):
        m.add_line(f"V{r}x", [k((r, 0, 0)), k((r, 0, H))])
        m.add_line(f"V{r}y", [k((0, r, 0)), k((0, r, H))])
    for z in (0.0, H):
        m.add_line(f"Rx{z}", [k((ri, 0, z)), k((ra, 0, z))])
        m.add_line(f"Ry{z}", [k((0, ri, z)), k((0, ra, z))])
    m.add_flaeche("Innen", [f"B{ri}0.0", f"V{ri}y", f"B{ri}{H}", f"V{ri}x"], material="S235", typ="regelflaeche")
    m.add_flaeche("Aussen", [f"B{ra}0.0", f"V{ra}y", f"B{ra}{H}", f"V{ra}x"], material="S235", typ="regelflaeche")
    m.add_flaeche("Unten", ["Rx0.0", f"B{ra}0.0", "Ry0.0", f"B{ri}0.0"], material="S235")
    m.add_flaeche("Oben", [f"Rx{H}", f"B{ra}{H}", f"Ry{H}", f"B{ri}{H}"], material="S235")
    m.add_flaeche("SchnittX", ["Rx0.0", f"V{ra}x", f"Rx{H}", f"V{ri}x"], material="S235")
    m.add_flaeche("SchnittY", ["Ry0.0", f"V{ra}y", f"Ry{H}", f"V{ri}y"], material="S235")
    m.add_koerper("R", ["Innen", "Aussen", "Unten", "Oben", "SchnittX", "SchnittY"], material="S235")
    return m, ri, H


def test_a15_druck():
    from statik3d import mesher, assemble as asm
    from statik3d.elements import solid as sl
    m, ri, H = _a15_modell()
    m.netz.ziellaenge = 0.02
    m.netz.ordnung = 2
    p = 1e6
    m.add_geometrielast("Innen", -p, "flaeche", case="LF1")
    mesher.modell_vernetzen(m, [], workers=1)
    X = np.asarray(m.nodes)
    F = np.zeros(3)
    F2 = np.zeros(3)
    n = 0
    for fl in m.case("LF1").face_loads:
        e = m.elements[int(fl.elem)]
        if e.typ != "tet10":
            continue
        n += 1
        f = asm.solid_face_pressure(m, e, fl.p, int(fl.face), getattr(fl, "direction", None))
        F += f.reshape(-1, 3).sum(0)
        P = X[[e.nodes[i] for i in sl.FLAECHEN[e.typ][int(fl.face)]]]
        s = sl.flaechenlast_knoten(P, fl.p, None).sum(0)
        if np.dot(s, X[e.nodes].mean(0) - P.mean(0)) < 0:
            s = -s
        F2 += s
    soll = p * ri * H
    check("A15 Innendruck auf gekrümmter tet10-Seite: ΣF_x = p·r_i·H (Projektion) auf 0,01 %",
          n > 0 and abs(abs(F[0]) / soll - 1) < 1e-4 and abs(abs(F[1]) / soll - 1) < 1e-4,
          f"{n} Seiten, F = ({F[0] / 1e3:.4f}; {F[1] / 1e3:.4f}) kN, Soll {soll / 1e3:.4f} kN")
    check("… zweiter Weg mit örtlicher Normale je Seite: dieselbe Summe", np.allclose(np.abs(F), np.abs(F2), rtol=1e-9),
          f"({F2[0] / 1e3:.4f}; {F2[1] / 1e3:.4f}) kN")


def _zwei_bloecke(eigene):
    from statik3d.model import Model, Material
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
    if eigene:
        m.add_flaeche("FugeU", R[1], material="S235")
        m.add_flaeche("FugeO", R[1], material="S235")
        fu, fo = "FugeU", "FugeO"
    else:
        m.add_flaeche("Fuge", R[1], material="S235")
        fu = fo = "Fuge"
    un = [m.add_flaeche(f"MU{i}", [R[0][i], V01[(i + 1) % 4], R[1][i], V01[i]], material="S235").name for i in range(4)]
    ob = [m.add_flaeche(f"MO{i}", [R[1][i], V12[(i + 1) % 4], R[2][i], V12[i]], material="S235").name for i in range(4)]
    m.add_koerper("Unten", ["Boden", fu] + un, material="S235")
    m.add_koerper("Oben", [fo, "Dach"] + ob, material="S235")
    return m


def test_a16():
    from statik3d import diagnose as dg
    w = [b for b in dg._abnahme_deckungsgleiche_flaechen(_zwei_bloecke(True))]
    check("A16 eigene deckungsgleiche Trennflächen ohne Kontakt: WARNUNG „Trennfläche doppelt“",
          len(w) == 1 and w[0].stufe == "WARNUNG" and "FugeU" in w[0].text and "FugeO" in w[0].text,
          w[0].text[:100] if w else "")
    check("… gemeinsame Trennfläche: keine Warnung", not dg._abnahme_deckungsgleiche_flaechen(_zwei_bloecke(False)))
    m = _zwei_bloecke(True)
    m.add_kontaktbedingung("K", flaechennamen=["FugeO"], gegenflaechen=["FugeU"])
    check("… mit Kontaktbedingung an den Flächen: keine Warnung", not dg._abnahme_deckungsgleiche_flaechen(m))


def _schalen(art):
    from statik3d.model import Model, Material, ShellProp
    m = Model("S")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t", 0.01))
    if art in ("stoss_eins", "stoss_geteilt"):
        k = [m.add_node(*p) for p in [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (2, 1, 0),
                                       (3, 0, 0), (3, 1, 0), (3, 2, 0)]]
        m.add_line("R0", [k[0], k[1]]); m.add_line("R2", [k[2], k[3]]); m.add_line("R3", [k[3], k[0]])
        m.add_line("S1", [k[1], k[4]]); m.add_line("S2", [k[4], k[2]])
        if art == "stoss_geteilt":
            m.add_flaeche("F", ["R0", "S1", "S2", "R2", "R3"], material="S235")
        else:
            m.add_line("R1", [k[1], k[2]])
            m.add_flaeche("F", ["R0", "R1", "R2", "R3"], material="S235")
        m.add_line("G0", [k[1], k[5]]); m.add_line("G1r", [k[5], k[6]]); m.add_line("Gm", [k[6], k[4]])
        m.add_line("H1r", [k[6], k[7]]); m.add_line("H2", [k[7], k[2]])
        m.add_flaeche("G1", ["G0", "G1r", "Gm", "S1"], material="S235")
        m.add_flaeche("G2", ["Gm", "H1r", "H2", "S2"], material="S235")
        return m
    k = [m.add_node(*p) for p in [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (0, 1, 0), (2, 1, 0),
                                   (0, 1, -0.2), (2, 1, -0.2)]]
    m.add_line("R0", [k[0], k[1]]); m.add_line("R2", [k[2], k[3]])
    m.add_line("L1", [k[0], k[4]]); m.add_line("L2", [k[4], k[3]]); m.add_line("Q1", [k[1], k[5]])
    m.add_line("Q2", [k[5], k[2]]); m.add_line("M", [k[4], k[5]])
    if art == "rippe_geteilt":
        m.add_flaeche("P1", ["R0", "Q1", "M", "L1"], material="S235")
        m.add_flaeche("P2", ["M", "Q2", "R2", "L2"], material="S235")
    else:
        m.add_line("L", [k[0], k[3]]); m.add_line("Q", [k[1], k[2]])
        m.add_flaeche("P", ["R0", "Q", "R2", "L"], material="S235")
    m.add_line("U", [k[6], k[7]]); m.add_line("V0", [k[4], k[6]]); m.add_line("V1", [k[5], k[7]])
    m.add_flaeche("Rippe", ["M", "V1", "U", "V0"], material="S235")
    return m


def test_a19():
    from statik3d import diagnose as dg, mesher
    arten = ("stoss_eins", "stoss_geteilt", "rippe_ungeteilt", "rippe_geteilt")
    n, neu = {}, {}
    for a in arten:
        m = _schalen(a)                       # Netz von frueher: jede Flaeche fuer sich vernetzt
        for f in m.flaechen.values():
            mesher.mesh_flaeche(m, f, [])
        n[a] = len(dg._abnahme_schalen_ohne_linie(m))
        m = _schalen(a)                       # neu vernetzt: der Vernetzer teilt im Netz
        mesher.modell_vernetzen(m, [], workers=1)
        neu[a] = len(dg._abnahme_schalen_ohne_linie(m))
    check("A19 Stoß ohne gemeinsame Linie und Rippe auf ungeteilter Platte, Netz von früher: je eine WARNUNG, "
          "geteilt keine",
          n["stoss_eins"] >= 1 and n["rippe_ungeteilt"] >= 1 and n["stoss_geteilt"] == 0 and n["rippe_geteilt"] == 0,
          str(n))
    check("A19 dieselben Modelle neu vernetzt (im Netz geteilt): keine WARNUNG", not any(neu.values()), str(neu))


def test_a20():
    from statik3d.model import Model, Material, ShellProp
    from statik3d import solver, spannungen
    m = Model("Patch")
    m.add_material(Material("St", E=210e9, nu=0.3, rho=0.0, fy=355e6))
    m.add_shell_prop(ShellProp("t", 0.01))
    rng = np.random.default_rng(3)
    nx = ny = 4
    ids = np.zeros((nx + 1, ny + 1), int)
    for i in range(nx + 1):
        for j in range(ny + 1):
            ids[i, j] = m.add_node(i * 0.25, j * 0.25, 0.0)
    for i in range(nx):
        for j in range(ny):
            a, b, c, d = ids[i, j], ids[i + 1, j], ids[i + 1, j + 1], ids[i, j + 1]
            for tri in ([a, b, c], [a, c, d]):
                tri = list(np.roll(tri, int(rng.integers(0, 3))))     # Elementachsen beliebig gedreht
                m.add_element("shell3", tri, "St", "t")
    for j in range(ny + 1):
        m.fix(int(ids[0, j]), [0])
        m.load_node(int(ids[nx, j]), Fx=10e6 * 0.01 * 1.0 * (0.5 if j in (0, ny) else 1.0) * 0.25)
    m.fix(int(ids[0, 0]), [1, 2, 3, 4, 5])
    for i in range(nx + 1):
        for j in range(ny + 1):
            m.fix(int(ids[i, j]), [2, 3, 4, 5])
    r = solver.solve_static(m)
    sx = spannungen.je_knoten(m, r, "flaechen", "sx", "oben")
    sy = spannungen.je_knoten(m, r, "flaechen", "sy", "oben")
    s1 = spannungen.je_knoten(m, r, "flaechen", "s1", "oben")
    check("A20 Patchtest Zug 10 N/mm², Elementachsen beliebig: σ_x = 10, σ_y = 0 an jedem Knoten",
          np.allclose(sx, 10.0, atol=1e-6) and np.allclose(sy, 0.0, atol=1e-6),
          f"σ_x {np.nanmin(sx):.4f} … {np.nanmax(sx):.4f}, σ_y {np.nanmin(sy):.4f} … {np.nanmax(sy):.4f}")
    check("… zweiter Weg Hauptspannung σ_1 = 10 (unabhängig von den Achsen)", np.allclose(s1, 10.0, atol=1e-6),
          f"{np.nanmin(s1):.4f} … {np.nanmax(s1):.4f}")


def test_verfahren():
    from statik3d import rechenverfahren as rv
    ok = all(rv.merkmal(n) is not None and rv.merkmal(n).wechsel[-1].stand == s
             for n, s in (("flaechen_achsen", 18), ("quader_teilung_achsen", 19), ("flaechenlast_gekruemmt", 20)))
    check("Verfahrenstabelle: A20/A14/A15 Fehlerkorrektur Stand 18/19/20", ok and rv.VERFAHRENSSTAND >= 20)


def main():
    for t in (test_a14, test_a15_druck, test_a16, test_a19, test_a20, test_verfahren):
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
