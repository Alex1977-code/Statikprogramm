"""Export als Abaqus/CalculiX-Eingabedatei (.inp)."""
from __future__ import annotations

import numpy as np

from ..model import Model
from . import _common as C

#: Statik3D-Element -> Abaqus-Elementart. Die ebenen Elemente bekommen ihren
#: Namen aus dem Zustand (Scheibe CPS, ebener Dehnungszustand CPE,
#: rotationssymmetrisch CAX), siehe :func:`abq_typ`.
ABQ = {"beam": "B31", "truss": "T3D2", "seil": "T3D2",
       "shell3": "S3", "shell4": "S4", "shell6": "STRI65", "shell8": "S8R",
       "tet4": "C3D4", "tet10": "C3D10", "hex8": "C3D8", "hex20": "C3D20",
       "pent6": "C3D6", "pent15": "C3D15", "pyr5": "C3D5"}
#: Ebene Elemente: (Zustand, Knotenzahl) -> Abaqus-Name
ABQ_EBENE = {("spannung", 3): "CPS3", ("spannung", 4): "CPS4", ("spannung", 6): "CPS6",
             ("spannung", 8): "CPS8", ("dehnung", 3): "CPE3", ("dehnung", 4): "CPE4",
             ("dehnung", 6): "CPE6", ("dehnung", 8): "CPE8", ("rotation", 3): "CAX3",
             ("rotation", 4): "CAX4", ("rotation", 6): "CAX6", ("rotation", 8): "CAX8"}


def abq_typ(e) -> str:
    """Abaqus-Elementart eines Elements ("" = nicht exportierbar)."""
    if e.typ.startswith("ebene"):
        return ABQ_EBENE.get((getattr(e, "zustand", "spannung"), len(e.nodes)), "")
    return ABQ.get(e.typ, "")


def write_inp(model: Model, path: str, results=None, log: list = None, **_) -> str:
    z = [f"** Statik3D-Export: {model.name}", "*NODE"]
    for i, p in enumerate(model.nodes, 1):
        z.append(f"{i}, {p[0]:.8g}, {p[1]:.8g}, {p[2]:.8g}")
    gruppen: dict[str, list] = {}
    for i, e in enumerate(model.elements, 1):
        art = abq_typ(e)
        if not art:
            continue
        gruppen.setdefault((art, e.mat, e.sec or ""), []).append((i, e))
    for (art, mat, sec), items in gruppen.items():
        setname = f"E_{art}_{_safe(mat)}_{_safe(sec)}"
        z.append(f"*ELEMENT, TYPE={art}, ELSET={setname}")
        for i, e in items:
            z.append(f"{i}, " + ", ".join(str(int(n) + 1) for n in e.nodes))
    for name, m in model.materials.items():
        z.append(f"*MATERIAL, NAME={_safe(name)}")
        z.append("*ELASTIC")
        z.append(f"{m.E:.8g}, {m.nu:.8g}")
        z.append("*DENSITY")
        z.append(f"{m.rho:.8g}")
        z.append("*EXPANSION")
        z.append(f"{m.alpha:.8g}")
    for (art, mat, sec), items in gruppen.items():
        setname = f"E_{art}_{_safe(mat)}_{_safe(sec)}"
        if art in ("B31", "T3D2"):
            s = model.sections.get(sec)
            A = s.A if s else 1e-3
            if art == "T3D2":
                z.append(f"*SOLID SECTION, ELSET={setname}, MATERIAL={_safe(mat)}")
                z.append(f"{A:.8g}")
            else:
                z.append(f"*BEAM GENERAL SECTION, ELSET={setname}, "
                         f"MATERIAL={_safe(mat)}, SECTION=GENERAL")
                z.append(f"{A:.8g}, {(s.Iy if s else 1e-6):.8g}, 0.0, "
                         f"{(s.Iz if s else 1e-6):.8g}, {(s.It if s else 1e-6):.8g}")
                z.append("0.0, 0.0, -1.0")
        elif art.startswith("S"):
            p = model.shells.get(sec)
            z.append(f"*SHELL SECTION, ELSET={setname}, MATERIAL={_safe(mat)}")
            z.append(f"{(p.t if p else 0.01):.8g}")
        else:
            z.append(f"*SOLID SECTION, ELSET={setname}, MATERIAL={_safe(mat)}")
    if model.supports:
        z.append("*BOUNDARY")
        for s in model.supports:
            for d in sorted(s.dofs):
                z.append(f"{s.node + 1}, {d + 1}, {d + 1}, 0.0")
    for name, lc in model.load_cases.items():
        z.append(f"*STEP, NAME={_safe(name)}")
        z.append("*STATIC")
        if np.any(np.asarray(lc.gravity, float)):
            g = np.asarray(lc.gravity, float)
            gn = float(np.linalg.norm(g))
            z.append("*DLOAD")
            z.append(f"ALL, GRAV, {gn:.8g}, {g[0]/gn:.6g}, {g[1]/gn:.6g}, {g[2]/gn:.6g}")
        if lc.nodal_loads:
            z.append("*CLOAD")
            for nl in lc.nodal_loads:
                for k, v in enumerate(float(x) for x in nl.F):
                    if v:
                        z.append(f"{nl.node + 1}, {k + 1}, {v:.8g}")
        z.append("*NODE FILE")
        z.append("U, RF")
        z.append("*EL FILE")
        z.append("S, E")
        z.append("*END STEP")
    with open(path, "w", encoding="ascii", errors="replace") as f:
        f.write("\n".join(z) + "\n")
    C.say(log, f"Abaqus-Eingabedatei geschrieben: {model.nn} Knoten, "
               f"{sum(len(v) for v in gruppen.values())} Elemente -> {path}")
    return path


def _safe(t: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in str(t))[:60] or "X"
