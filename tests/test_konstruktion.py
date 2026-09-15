"""Lot und Projektion auf Ebene, Flaeche und Linie (statik3d/konstruktion.py)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import konstruktion as ko                        # noqa: E402
from statik3d.model import Material, Model, ShellProp          # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:64s} {detail}")
    return bool(ok)


def _nah(a, b, tol=1e-9) -> bool:
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), atol=tol))


def _modell() -> Model:
    """Eine ebene Flaeche z = 0 (2 x 1), ein Kreis, eine gewoelbte Flaeche
    (Viertelzylinder r = 1 um die z-Achse, Hoehe 1) aus zwei Boegen."""
    m = Model("K")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("d10", 0.01))
    m.add_nodes([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0],
                 [1, 0, 0], [np.sqrt(0.5), np.sqrt(0.5), 0], [0, 1, 0],
                 [1, 0, 1], [np.sqrt(0.5), np.sqrt(0.5), 1], [0, 1, 1]])
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
        m.add_line(f"L{i + 1}", [a, b])
    m.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke="d10", material="S235")
    m.add_line("K1", typ="circle", mitte=(5.0, 5.0, 0.0), radius=1.0, normale=(0, 0, 1))
    m.add_line("B1", [4, 5, 6], "arc")
    m.add_line("B2", [7, 8, 9], "arc")
    m.add_line("V1", [4, 7])
    m.add_line("V2", [6, 9])
    m.add_flaeche("Z1", ["B1", "V2", "B2", "V1"], material="S235", typ="regelflaeche")
    return m


def test_ebene():
    check("Lot auf z = 0: (1, 2, 3) → (1, 2, 0)", _nah(ko.lot_auf_ebene((1, 2, 3), (0, 0, 0), (0, 0, 1)), [1, 2, 0]))
    check("… auf eine geneigte Ebene (Normale (1,0,1) durch den Ursprung): (2, 0, 0) → (1, 0, -1)",
          _nah(ko.lot_auf_ebene((2, 0, 0), (0, 0, 0), (1, 0, 1)), [1, 0, -1]))
    m = _modell()
    e = ko.ebene_der_flaeche(m, m.flaechen["F1"])
    check("Ebene der ebenen Fläche: Ursprung (1, 0,5, 0), Normale ±z",
          e is not None and _nah(e[0], [1, 0.5, 0]) and abs(abs(float(e[1][2])) - 1) < 1e-12, str(e))
    check("die gewölbte Fläche hat keine Ebene", ko.ebene_der_flaeche(m, m.flaechen["Z1"]) is None)
    o, n, ab = ko.ebene_der_punkte([[0, 0, 0], [1, 0, 0], [1, 1, 0.01], [0, 1, 0]])
    # die Newell-Ebene durch den Schwerpunkt kippt mit: der groesste Abstand ist
    # ein Viertel der Abweichung (gemessen 0,0025 bei 0,01)
    check("Ausgleichsebene nennt den größten Abstand (0,0025 bei 10 mm Abweichung einer Ecke)",
          0.002 < ab < 0.003, f"{ab}")


def test_strecken_und_linien():
    F, t = ko.fusspunkte_auf_strecken((1, 1, 0), [[0, 0, 0], [3, 0, 0]], [[2, 0, 0], [4, 0, 0]])
    check("Lot auf die Strecke (0,0,0)-(2,0,0): Fußpunkt (1,0,0) bei t = 0,5",
          _nah(F[0], [1, 0, 0]) and abs(t[0] - 0.5) < 1e-12, str((F[0], t[0])))
    check("… auf die Strecke (3,0,0)-(4,0,0): daneben (t < 0), auf den Anfang geklemmt",
          _nah(F[1], [3, 0, 0]) and t[1] < 0, str((F[1], t[1])))
    check("der nächste Fußpunkt ist der auf der ersten Strecke",
          _nah(ko.lot_auf_strecken((1, 1, 0), [[0, 0, 0], [3, 0, 0]], [[2, 0, 0], [4, 0, 0]]), [1, 0, 0]))
    check("leeres Feld: None", ko.lot_auf_strecken((0, 0, 0), np.zeros((0, 3)), np.zeros((0, 3))) is None)
    m = _modell()
    q = ko.lot_auf_linie(m, m.lines["K1"], (8, 5, 2))
    check("Lot auf den Kreis (Mitte (5,5,0), r = 1) von (8, 5, 2): (6, 5, 0) auf 3 mm genau (abgetastet)",
          q is not None and abs(q[0] - 6.0) < 3e-3 and abs(q[1] - 5.0) < 3e-3 and abs(q[2]) < 1e-9, str(q))
    q = ko.lot_auf_linie(m, m.lines["L1"], (1, -2, 5))
    check("Lot auf die gerade Linie L1: (1, 0, 0)", _nah(q, [1, 0, 0]), str(q))


def test_flaeche():
    m = _modell()
    q = ko.lot_auf_flaeche(m, m.flaechen["F1"], (1.5, 0.25, 4.0))
    check("Lot auf die ebene Fläche: (1,5, 0,25, 0)", _nah(q, [1.5, 0.25, 0]), str(q))
    q = ko.lot_auf_flaeche(m, m.flaechen["F1"], (3.0, 0.5, 1.0))
    check("… außerhalb ihres Umrisses: der nächste Punkt des Randes (2, 0,5, 0)", _nah(q, [2, 0.5, 0]), str(q))
    q = ko.lot_auf_flaeche(m, m.flaechen["Z1"], (3.0, 0.0, 0.5))
    check("Lot auf den Viertelzylinder von (3, 0, 0,5): auf dem Mantel bei (1, 0, 0,5), auf 1 % genau",
          q is not None and abs(np.hypot(q[0], q[1]) - 1.0) < 1e-2 and abs(q[2] - 0.5) < 1e-9 and abs(q[1]) < 5e-2, str(q))
    q = ko.lot_auf_flaeche(m, m.flaechen["Z1"], (0.3, 0.3, 0.5))
    check("… von innen (0,3, 0,3, 0,5): auf dem Mantel in Richtung 45°",
          q is not None and abs(np.hypot(q[0], q[1]) - 1.0) < 1e-2 and abs(q[0] - q[1]) < 5e-2, str(q))


def main():
    for t in (test_ebene, test_strecken_und_linien, test_flaeche):
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
