"""
Kommandozeilen-Betrieb (ohne GUI).

    python -m statik3d.cli modell.json --analyse statik --csv ergebnisse.csv
    python -m statik3d.cli --beispiel frame --analyse knicken
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from .model import Model
from . import solver
from .examples_lib import build_example, EXAMPLES


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Statik3D - FEM-Berechnung ohne GUI")
    ap.add_argument("datei", nargs="?", help="Modelldatei (.json)")
    ap.add_argument("--beispiel", choices=list(EXAMPLES),
                    help="statt einer Datei ein eingebautes Beispiel rechnen")
    ap.add_argument("--analyse", default="statik",
                    choices=["statik", "eigenformen", "knicken"])
    ap.add_argument("--moden", type=int, default=6)
    ap.add_argument("--csv", help="Knotenergebnisse als CSV schreiben")
    ap.add_argument("--vtk", help="Netz + Ergebnisse als .vtu schreiben (ParaView)")
    a = ap.parse_args(argv)

    if a.beispiel:
        m = build_example(a.beispiel)
    elif a.datei:
        m = Model.load(a.datei)
    else:
        ap.error("Bitte eine Modelldatei oder --beispiel angeben")

    problems = [x for x in m.check() if x.startswith("FEHLER")]
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2

    if a.analyse == "statik":
        r = solver.solve_static(m, print)
    elif a.analyse == "eigenformen":
        r = solver.solve_modal(m, a.moden, print)
    else:
        r = solver.solve_buckling(m, a.moden, print)

    print()
    print(r.summary())

    if a.csv:
        with open(a.csv, "w", encoding="utf-8") as f:
            f.write("Knoten;x;y;z;ux;uy;uz;rx;ry;rz\n")
            for i in range(m.nn):
                x, y, z = m.nodes[i]
                f.write(f"{i};{x:.6f};{y:.6f};{z:.6f};"
                        + ";".join(f"{v:.6e}" for v in r.u[i]) + "\n")
        print(f"CSV geschrieben: {a.csv}")

    if a.vtk:
        from .gui.main import to_grid
        g = to_grid(m)
        g.point_data["u"] = r.u[:, :3]
        if r.node_vm is not None:
            g.point_data["vonMises"] = np.nan_to_num(r.node_vm)
        g.save(a.vtk)
        print(f"VTK geschrieben: {a.vtk}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
