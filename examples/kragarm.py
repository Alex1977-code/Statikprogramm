"""Minimalbeispiel: Kragarm, Vergleich mit Handrechnung."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material, Section
from statik3d import solver, mesher

m = Model("Kragarm")
m.add_material(Material("S355", E=210e9, nu=0.3, rho=7850, fy=355e6))
sec = m.add_section(Section.i_profile("HEA200", 0.190, 0.200, 0.0065, 0.010))

ids = mesher.line_of_beams(m, "S355", "HEA200", (0, 0, 0), (5, 0, 0), n=10)
m.fix(ids[0], "all")
m.load_node(ids[-1], Fz=-20000.0)

r = solver.solve_static(m)
print(r.summary())
print()
print(f"Einspannmoment   : {r.beam_forces[0]['My'][0]/1e3:8.2f} kNm  "
      f"(Handrechnung {20000*5/1e3:.2f} kNm)")
print(f"Spannung am Fuss : {r.beam_forces[0]['sig_max']/1e6:8.2f} MPa")
print(f"Ausnutzung       : {r.beam_forces[0]['util']:8.3f}")
