"""Rechteckplatte mit Flaechenlast, Konvergenzstudie."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

from statik3d.model import Model, Material, ShellProp
from statik3d import solver, mesher

a, t, q, E, nu = 2.0, 0.02, 10000.0, 210e9, 0.3
D = E * t**3 / (12 * (1 - nu**2))
exact = 0.00406 * q * a**4 / D

print(f"{'Netz':>8} {'w_max [mm]':>12} {'Abweichung':>12}")
for n in (4, 8, 16, 24):
    m = Model()
    m.add_material(Material("S", E=E, nu=nu))
    m.add_shell_prop(ShellProp("t", t))
    ids = mesher.grid_plate(m, "S", "t", a, a, n, n, quad=True)
    for i in range(n + 1):
        for j in range(n + 1):
            if i in (0, n) or j in (0, n):
                m.fix(int(ids[i, j]), [2])
    m.fix(int(ids[0, 0]), [0, 1]); m.fix(int(ids[n, 0]), [1])
    for e in range(len(m.elements)):
        m.load_face(e, -q)
    r = solver.solve_static(m)
    w = -r.u[ids[n // 2, n // 2], 2]
    print(f"{n:>4}x{n:<3} {w*1000:12.4f} {(w-exact)/exact*100:11.2f} %")
print(f"{'exakt':>8} {exact*1000:12.4f}")
