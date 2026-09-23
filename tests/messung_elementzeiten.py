"""
Messung A8: Zeitangaben im Quelltext der Volumenelemente nachmessen.

Je Element in Mikrosekunden, an verzerrten Wuerfeln (dieselbe Form wie die
Angaben vom 21.09.2026): k_tet4 einzeln, k_hex8 einzeln, Stapel ueber den
Dehnungsoperator (hex8, tet10), Spannungen stress_points einzeln gegen
spannungen_stapel. **Nur auf ruhiger Maschine** (ansagen), Einkern:
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1.

Kein Test. Aufruf:  python -m tests.messung_elementzeiten [n]
"""
from __future__ import annotations

import sys
import time

import numpy as np

from statik3d.elements import solid as sl
from statik3d.model import Material, Model

E, NU = 210e9, 0.3
W8 = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
               [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)


def wuerfel(n, rng):
    return np.stack([W8 + rng.uniform(-0.08, 0.08, (8, 3)) for _ in range(n)])


def zeit(f, wdh=3):
    best = np.inf
    for _ in range(wdh):
        t0 = time.perf_counter()
        f()
        best = min(best, time.perf_counter() - t0)
    return best


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    n = int(argv[0]) if argv else 2000
    rng = np.random.default_rng(1)
    X8 = wuerfel(n, rng)
    tets = X8[:, [0, 1, 3, 4], :]
    U8 = rng.normal(0, 1e-4, (n, 24))
    zeilen = []
    zeilen.append(("k_tet4 einzeln", zeit(lambda: [sl.k_tet4(x, E, NU) for x in tets[:n // 4]]) / (n // 4)))
    zeilen.append(("k_hex8 einzeln", zeit(lambda: [sl.k_hex8(x, E, NU) for x in X8[:n // 4]]) / (n // 4)))
    zeilen.append(("k_hex8_stapel", zeit(lambda: sl.k_hex8_stapel(X8, E, NU)) / n))
    zeilen.append(("stress_points hex8 einzeln",
                   zeit(lambda: [sl.stress_points("hex8", x, E, NU, u) for x, u in
                                 zip(X8[:n // 4], U8[:n // 4])]) / (n // 4)))
    zeilen.append(("spannungen_hex8_stapel", zeit(lambda: sl.spannungen_hex8_stapel(X8, E, NU, U8)) / n))
    # tet10 ueber ein Modell (der Stapel braucht Elementnummern)
    m = Model("zeiten")
    m.add_material(Material("S", E=E, nu=NU))
    nat = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)
    kanten = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]
    for _ in range(n):
        Xe = nat + rng.uniform(-0.08, 0.08, (4, 3))
        Xe = np.vstack([Xe] + [0.5 * (Xe[a] + Xe[b]) for a, b in kanten])
        ids = m.add_nodes(Xe)
        m.add_element("tet10", [int(i) for i in ids], "S")
    D = sl.D_matrix(E, NU)
    zeilen.append(("k_tet10 einzeln", zeit(lambda: [sl.k_tet10(m.nodes[e.nodes], E, NU)
                                                    for e in m.elements[:n // 4]]) / (n // 4)))
    zeilen.append(("tet10 Stapel (Operator)",
                   zeit(lambda: [sl.steifigkeit_aus_operator(op, D)
                                 for op in sl.dehnungsoperator(m, "tet10", range(n))]) / n))
    for name, t in zeilen:
        print(f"{name:32s} {t * 1e6:9.1f} µs je Element")


if __name__ == "__main__":
    main()
