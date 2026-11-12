"""
Projizierte Flaechenlast mit negativem Wert an Volumen (Befund A3 der
Pruefagenten, 09.11.2026).

Eine Last „auf die Projektion“ wirkt mit der Kraft p · A_proj · d (d = Richtung
bzw. Achse des Lastbezugs). Getroffen wird die Seite, der die **Kraft**
zugewandt ist: Aussennormale n mit n · (p d) < 0. Bis zum 09.11.2026 nahm der
Windschatten d ohne das Vorzeichen von p - „global Z, p = −5 kN/m²“ (Schnee)
traf die Unterseite eines Blocks statt das Dach. Die Summe stimmte, der
Angriffspunkt nicht.

Erwartung am Block 1,0 × 0,5 × 0,2 m, Grundriss 0,5 m²:
  * p = −5 kN/m² global Z → Dach z = 0,2, ΣF = (0; 0; −2,5) kN
  * gleich der alten Eingabe Richtung (0; 0; −1), p = +5 kN/m²
  * gleich Richtung (0; 0; +1), p = −5 kN/m²
  * p = +5 kN/m² global Z → Unterseite z = 0, ΣF = (0; 0; +2,5) kN
jeweils mit linearen und quadratischen Elementen.

Aufruf:  python -m tests.test_projiziert_vorzeichen
"""
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


def _block(ordnung):
    from statik3d.model import Model, Material
    m = Model("Block")
    m.add_material(Material.steel("S235"))
    x1, y1, z1 = 1.0, 0.5, 0.2
    P = np.array([[0, 0, 0], [x1, 0, 0], [x1, y1, 0], [0, y1, 0],
                  [0, 0, z1], [x1, 0, z1], [x1, y1, z1], [0, y1, z1]], float)
    m.add_nodes(P)
    n = {"i": 0}

    def linie(a, b):
        n["i"] += 1
        m.add_line(f"L{n['i']}", [a, b])
        return f"L{n['i']}"
    R = [[linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [linie(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Dach", R[1], material="S235")
    seiten = []
    for i in range(4):
        m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235")
        seiten.append(f"M{i}")
    k = m.add_koerper("K", ["Boden", "Dach"] + seiten, material="S235")
    k.teilung = [4, 2, 2]
    m.netz.ordnung = ordnung
    m.add_load_case("LF1", "Q")
    return m


def _lauf(ordnung, p, **kw):
    from statik3d import mesher, solver
    m = _block(ordnung)
    m.add_geometrielast("K", p, art="koerper", case="LF1", projiziert=True, **kw)
    mesher.modell_vernetzen(m, log=[], workers=1)
    m.lasten_verteilen()
    fl = m.case("LF1").face_loads
    zs = sorted({round(float(m._seitenmitte(f.elem, f.face)[2]), 4) for f in fl})
    F = np.asarray(solver.case_loads(m, {"LF1": 1.0}, None)[0], float).reshape(m.nn, -1)[:, :3]
    return zs, F.sum(axis=0), m


def test_block():
    for o in (1, 2):
        art = "linear" if o == 1 else "quadratisch"
        faelle = (
            ("global Z, p = −5 kN/m²", dict(p=-5000.0, bezug="global", achse="z"), [0.2], -2500.0),
            ("Richtung (0; 0; −1), p = +5 kN/m²", dict(p=5000.0, richtung=[0, 0, -1]), [0.2], -2500.0),
            ("Richtung (0; 0; +1), p = −5 kN/m²", dict(p=-5000.0, richtung=[0, 0, 1]), [0.2], -2500.0),
            ("global Z, p = +5 kN/m²", dict(p=5000.0, bezug="global", achse="z"), [0.0], 2500.0),
        )
        for text, kw, z_soll, fz in faelle:
            p = kw.pop("p")
            zs, S, _ = _lauf(o, p, **kw)
            check(f"{art}: {text} trifft z = {z_soll[0]:.1f}, ΣFz = {fz / 1e3:+.3f} kN",
                  zs == z_soll and np.allclose(S, [0.0, 0.0, fz], atol=1e-6),
                  f"belastet z = {zs}, ΣF = {np.round(S / 1e3, 6)} kN")


def test_schale_unveraendert():
    """An Schalen wirkte die projizierte Last schon vorher mit p A |n.d|, das
    Vorzeichen von p bestimmt die Richtung - daran aendert sich nichts."""
    import math
    from statik3d import mesher, solver
    from statik3d.model import Model, Material, ShellProp
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01, "S235"))
    m.add_load_case("LF1", "Q")
    h = math.tan(math.radians(30.0))
    for p in [(0, 0, 0), (2, 0, 0), (2, 1, h), (0, 1, h)]:
        m.add_node(*p)
    for j in range(4):
        m.add_line(f"L{j}", [j, (j + 1) % 4])
    m.add_flaeche("D", [f"L{j}" for j in range(4)], material="S235", dicke="D10")
    m.add_geometrielast("D", -5000.0, case="LF1", bezug="global", achse="z", projiziert=True)
    mesher.modell_vernetzen(m, log=[])
    m.lasten_verteilen()
    S = np.asarray(solver.case_loads(m, {"LF1": 1.0}, None)[0], float).reshape(m.nn, -1)[:, :3].sum(axis=0)
    check("Dachschale 30°, global Z, p = −5 kN/m² projiziert: ΣF = (0; 0; −10,000) kN",
          np.allclose(S / 1e3, [0, 0, -10.0], atol=1e-6), f"ΣF = {np.round(S / 1e3, 6)} kN")


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("projiziert_vorzeichen")
    _, _, m_neg = _lauf(1, -5000.0, bezug="global", achse="z")
    _, _, m_pos = _lauf(1, 5000.0, richtung=[0, 0, -1])
    check("Verfahrenstabelle: „projiziert_vorzeichen“ Fehlerkorrektur Stand 9, nur p < 0 an Volumen",
          mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and mk.wechsel[-1].stand == 9
          and rv.VERFAHRENSSTAND >= 9 and mk.betrifft(m_neg) and not mk.betrifft(m_pos))


def main():
    for t in (test_block, test_schale_unveraendert, test_verfahrenstabelle):
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
