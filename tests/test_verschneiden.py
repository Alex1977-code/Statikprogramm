"""Schnittlinien zweier Flaechen (statik3d/verschneiden.py)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import verschneiden as vs                        # noqa: E402
from statik3d.model import Material, Model                     # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:64s} {detail}")
    return bool(ok)


def _rechteck(m, name, P):
    basis = m.nn
    m.add_nodes(P)
    L = []
    for i in range(4):
        m.add_line(f"{name}L{i}", [basis + i, basis + (i + 1) % 4])
        L.append(f"{name}L{i}")
    return m.add_flaeche(name, L, material="S235")


def _modell() -> Model:
    m = Model("V")
    m.add_material(Material.steel("S235"))
    _rechteck(m, "F1", [[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0]])                  # z = 0
    _rechteck(m, "F2", [[1, -1, -1], [1, 2, -1], [1, 2, 1], [1, -1, 1]])              # x = 1
    _rechteck(m, "F3", [[0, 0, 5], [2, 0, 5], [2, 1, 5], [0, 1, 5]])                  # z = 5, weit weg
    _rechteck(m, "F4", [[0.5, 0.2, 0], [1.5, 0.2, 0], [1.5, 0.8, 0], [0.5, 0.8, 0]])  # in z = 0, koplanar
    # Viertelzylinder r = 1 um z, Hoehe 1, und eine Ebene z = 0,5 quer dazu
    b0 = m.nn
    m.add_nodes([[1, 0, 0], [np.sqrt(0.5), np.sqrt(0.5), 0], [0, 1, 0],
                 [1, 0, 1], [np.sqrt(0.5), np.sqrt(0.5), 1], [0, 1, 1]])
    m.add_line("B1", [b0, b0 + 1, b0 + 2], "arc")
    m.add_line("B2", [b0 + 3, b0 + 4, b0 + 5], "arc")
    m.add_line("V1", [b0, b0 + 3])
    m.add_line("V2", [b0 + 2, b0 + 5])
    m.add_flaeche("Z1", ["B1", "V2", "B2", "V1"], material="S235", typ="regelflaeche")
    _rechteck(m, "E1", [[-2, -2, 0.5], [2, -2, 0.5], [2, 2, 0.5], [-2, 2, 0.5]])
    return m


def _laenge(Z) -> float:
    return float(np.linalg.norm(np.diff(np.asarray(Z, float), axis=0), axis=1).sum())


def test_ebene_flaechen():
    m = _modell()
    z = vs.schnittlinien(m, m.flaechen["F1"], m.flaechen["F2"])
    check("zwei senkrechte Rechtecke: eine Schnittlinie von (1,0,0) nach (1,1,0), Länge 1",
          len(z) == 1 and abs(_laenge(z[0]) - 1.0) < 1e-9
          and {tuple(np.round(z[0][0], 9)), tuple(np.round(z[0][-1], 9))} == {(1, 0, 0), (1, 1, 0)}, str(z))
    check("… ausgedünnt bleiben nur die beiden Enden", len(vs.ausduennen(z[0])) == 2, str(vs.ausduennen(z[0])))
    check("weit auseinander: keine Schnittlinie", not vs.schnittlinien(m, m.flaechen["F1"], m.flaechen["F3"]))
    check("aufeinanderliegend (koplanar): keine Schnittlinie", not vs.schnittlinien(m, m.flaechen["F1"], m.flaechen["F4"]))
    z = vs.schnittlinien(m, m.flaechen["F2"], m.flaechen["F1"])
    check("die Reihenfolge der Flächen ändert nichts", len(z) == 1 and abs(_laenge(z[0]) - 1.0) < 1e-9)


def test_zylinder_und_ebene():
    m = _modell()
    z = vs.schnittlinien(m, m.flaechen["Z1"], m.flaechen["E1"])
    check("Viertelzylinder und Ebene z = 0,5: ein Bogen", len(z) == 1 and len(z[0]) >= 5, str([len(x) for x in z]))
    Z = z[0]
    r = np.hypot(Z[:, 0], Z[:, 1])
    check("… alle Punkte bei z = 0,5 auf dem Radius 1 (Abtastung: 1 %)",
          np.allclose(Z[:, 2], 0.5, atol=1e-9) and abs(r - 1.0).max() < 1e-2, f"r {r.min():.4f}..{r.max():.4f}")
    check("… über 90° von (1,0) nach (0,1), Bogenlänge π/2 auf 1 %",
          abs(_laenge(Z) - np.pi / 2) < 0.016
          and {tuple(np.round(Z[0][:2], 6)), tuple(np.round(Z[-1][:2], 6))} == {(1, 0), (0, 1)},
          f"Länge {_laenge(Z):.4f}, Enden {Z[0]} {Z[-1]}")


def test_verketten():
    S = np.array([[[0, 0, 0], [1, 0, 0]], [[2, 0, 0], [1, 0, 0]], [[2, 0, 0], [3, 0, 0]],
                  [[5, 0, 0], [6, 0, 0]], [[6, 0, 0], [6, 1, 0]], [[6, 1, 0], [5, 0, 0]]], float)
    z = vs.verketten(S, 1e-9)
    offen = [x for x in z if not np.allclose(x[0], x[-1])]
    zu = [x for x in z if np.allclose(x[0], x[-1])]
    check("verketten: ein offener Zug aus drei Strecken (0 → 3) und ein geschlossenes Dreieck",
          len(offen) == 1 and len(offen[0]) == 4 and abs(_laenge(offen[0]) - 3.0) < 1e-9
          and len(zu) == 1 and len(zu[0]) == 4, str([len(x) for x in z]))


def main():
    for t in (test_ebene_flaechen, test_zylinder_und_ebene, test_verketten):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
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
