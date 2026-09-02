"""Kontakt: abhebendes Lager mit Anschlag und Block mit Reibung."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.examples_lib import contact_example, block_friction_example
from statik3d import solver

for build in (contact_example, block_friction_example):
    m = build()
    r = solver.solve_static(m, progress=print)
    print()
    print(r.summary())
    for c in r.contact[:12]:
        print(f"  Knoten {c['node']:4d}  {c['kind']:8s}  {c['status']:8s}  "
              f"Fn = {c['Fn']/1e3:7.2f} kN  Ft = {c['Ft']/1e3:6.2f} kN  Spalt = {c['gap']*1e3:8.4f} mm")
    print("-" * 70)
