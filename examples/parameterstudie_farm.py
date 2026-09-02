"""Parameterstudie als verteilte Auftraege (lokaler Prozess-Pool oder Rechnerfarm):
Riegelprofil des Hallenrahmens variieren und die Ausnutzung vergleichen.

    python examples/parameterstudie_farm.py                 # lokal, alle Kerne
    python examples/parameterstudie_farm.py --farm host:5555 --key geheim
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import statik3d.jobs  # noqa: F401  (Registry)
from statik3d.parallel import Job, run_jobs, register_job, configure
from statik3d.examples_lib import hall_frame_example


@register_job("riegel_variante")
def _variante(model: dict, profil: str):
    from statik3d.model import Model, Section
    from statik3d import solver
    m = Model.from_dict(model)
    m.add_section(Section.from_profile(profil, "Riegel"))
    for i in m.members["Riegel"].elements:
        m.elements[i].sec = "Riegel"
    an = solver.solve_all(m, design=True)
    mc = an.design.members["Riegel"]
    return {"profil": profil, "util": mc.util, "nachweis": mc.governing["name"],
            "u_max_mm": float(an.envelopes["SLS_CH"].umag_max.max() * 1e3)}


if __name__ == "__main__":
    if "--farm" in sys.argv:
        host, _, port = sys.argv[sys.argv.index("--farm") + 1].partition(":")
        key = sys.argv[sys.argv.index("--key") + 1] if "--key" in sys.argv else "statik3d"
        configure(backend="farm", farm_host=host, farm_port=int(port or 5555), farm_key=key)
    m = hall_frame_example()
    profile = ["IPE 400", "IPE 450", "IPE 500", "IPE 550", "IPE 600", "HEA 400", "HEB 400"]
    jobs = [Job("riegel_variante", {"model": m.to_dict(), "profil": p}, label=p) for p in profile]
    for r in run_jobs(jobs, progress=lambda a, b: print(f"  {a}/{b} fertig")):
        if r.ok:
            d = r.result
            print(f"{d['profil']:8s}  Ausnutzung {d['util']:.3f}  ({d['nachweis']})  "
                  f"max u = {d['u_max_mm']:.1f} mm   [{r.worker}, {r.seconds:.1f} s]")
        else:
            print("FEHLER:", r.error.splitlines()[0])
