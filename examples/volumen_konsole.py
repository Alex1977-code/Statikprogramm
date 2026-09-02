"""Volumenmodell einer Konsole, Ausgabe der hoechstbeanspruchten Elemente."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

from statik3d.examples_lib import solid_example
from statik3d import solver

m = solid_example()
r = solver.solve_static(m)
print(r.summary())
print()
top = sorted(r.solid_stress.items(), key=lambda kv: -kv[1]["vM"])[:5]
print("hoechstbeanspruchte Elemente:")
for e, d in top:
    c = m.nodes[m.elements[e].nodes].mean(axis=0)
    print(f"  Element {e:5d}  Schwerpunkt ({c[0]:.3f}, {c[1]:.3f}, {c[2]:.3f})  "
          f"sigma_v = {d['vM']/1e6:7.2f} MPa   "
          f"Hauptspannungen = {np.round(d['principal']/1e6, 2)} MPa")
