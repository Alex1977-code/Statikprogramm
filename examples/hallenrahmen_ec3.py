"""Hallenrahmen: Lastfaelle, automatische Kombinationen, Umhuellende,
Nachweise nach EC3 und Ermuedung, statischer Bericht."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.examples_lib import hall_frame_example
from statik3d import solver
from statik3d.report import write_report

m = hall_frame_example()
print(f"{len(m.load_cases)} Lastfaelle, {len(m.combinations)} Kombinationen, {len(m.members)} Staebe")
an = solver.solve_all(m, design=True, fatigue=True, progress=print)
print()
print(an.summary())
print()
for row in an.design.table():
    print(" | ".join(f"{str(c):>14s}" for c in row))
mc = an.design.members["Riegel"]
print("\nMassgebend Riegel:", mc.governing["name"], mc.governing["combo"],
      f"x = {mc.governing['x']:.2f} m, Ausnutzung {mc.util:.3f}")
print(mc.governing["text"])
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hallenrahmen_bericht.html")
write_report(m, an, out)
print("Bericht:", out)
