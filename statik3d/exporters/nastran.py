"""Export als Nastran Bulk Data (.bdf), Kurzfeldformat (8 Spalten)."""
from __future__ import annotations

import numpy as np

from ..model import Model
from . import _common as C


def _f(v) -> str:
    """Zahl im 8 Zeichen breiten Kurzfeld."""
    s = f"{v:8.5g}"
    if len(s) > 8:
        s = f"{v:8.2e}"
    return s[:8].rjust(8)


def _i(v) -> str:
    return f"{int(v):8d}"[:8]


def write_bdf(model: Model, path: str, results=None, log: list = None, **_) -> str:
    z = ["$ Statik3D-Export: " + model.name, "SOL 101", "CEND",
         "TITLE = " + model.name[:60], "DISP = ALL", "STRESS = ALL",
         "SPC = 1"]
    faelle = list(model.load_cases)
    for k, name in enumerate(faelle, 1):
        z.append(f"SUBCASE {k}")
        z.append(f"  LABEL = {name[:60]}")
        z.append(f"  LOAD = {k}")
    z.append("BEGIN BULK")
    for i, p in enumerate(model.nodes, 1):
        z.append("GRID    " + _i(i) + "        " + _f(p[0]) + _f(p[1]) + _f(p[2]))
    mat_id = {n: i for i, n in enumerate(model.materials, 1)}
    for name, m in model.materials.items():
        z.append("MAT1    " + _i(mat_id[name]) + _f(m.E) + "        "
                 + _f(m.nu) + _f(m.rho) + _f(m.alpha))
    prop_id: dict[tuple, int] = {}
    def pid(key):
        if key not in prop_id:
            prop_id[key] = len(prop_id) + 1
        return prop_id[key]
    eid = 0
    karten = []
    for e in model.elements:
        eid += 1
        n = [int(x) + 1 for x in e.nodes]
        mid = mat_id.get(e.mat, 1)
        if e.typ in ("beam", "truss"):
            s = model.sections.get(e.sec)
            p = pid(("bar", e.sec, e.mat))
            karten.append("CBAR    " + _i(eid) + _i(p) + _i(n[0]) + _i(n[1])
                          + _f(0.0) + _f(0.0) + _f(1.0))
            z.append("PBAR    " + _i(p) + _i(mid) + _f(s.A if s else 1e-3)
                     + _f(s.Iy if s else 1e-6) + _f(s.Iz if s else 1e-6)
                     + _f(s.It if s else 1e-6))
        elif e.typ == "shell3":
            t = model.shells.get(e.sec)
            p = pid(("shell", e.sec, e.mat))
            karten.append("CTRIA3  " + _i(eid) + _i(p) + _i(n[0]) + _i(n[1]) + _i(n[2]))
            z.append("PSHELL  " + _i(p) + _i(mid) + _f(t.t if t else 0.01))
        elif e.typ == "shell4":
            t = model.shells.get(e.sec)
            p = pid(("shell", e.sec, e.mat))
            karten.append("CQUAD4  " + _i(eid) + _i(p) + _i(n[0]) + _i(n[1])
                          + _i(n[2]) + _i(n[3]))
            z.append("PSHELL  " + _i(p) + _i(mid) + _f(t.t if t else 0.01))
        elif e.typ in ("tet4", "tet10"):
            p = pid(("solid", e.mat))
            karten.append("CTETRA  " + _i(eid) + _i(p) + "".join(_i(x) for x in n[:4]))
            z.append("PSOLID  " + _i(p) + _i(mid))
        elif e.typ == "hex8":
            p = pid(("solid", e.mat))
            karten.append("CHEXA   " + _i(eid) + _i(p) + "".join(_i(x) for x in n[:6]))
            karten.append("        " + _i(n[6]) + _i(n[7]))
            z.append("PSOLID  " + _i(p) + _i(mid))
        else:
            eid -= 1
    # doppelte PBAR/PSHELL/PSOLID entfernen, Reihenfolge erhalten
    gesehen = set()
    z = [k for k in z if not (k.startswith(("PBAR", "PSHELL", "PSOLID"))
                              and (k in gesehen or gesehen.add(k)))]
    z.extend(karten)
    for s in model.supports:
        code = "".join(str(d + 1) for d in sorted(s.dofs))
        if code:
            z.append("SPC1    " + _i(1) + code.ljust(8) + _i(s.node + 1))
    for k, name in enumerate(faelle, 1):
        lc = model.load_cases[name]
        for nl in lc.nodal_loads:
            F = tuple(float(v) for v in nl.F[:3])
            if any(F):
                nrm = float(np.linalg.norm(F))
                z.append("FORCE   " + _i(k) + _i(nl.node + 1) + "        " + _f(nrm)
                         + _f(F[0] / nrm) + _f(F[1] / nrm) + _f(F[2] / nrm))
            M = tuple(float(v) for v in nl.F[3:6])
            if any(M):
                nrm = float(np.linalg.norm(M))
                z.append("MOMENT  " + _i(k) + _i(nl.node + 1) + "        " + _f(nrm)
                         + _f(M[0] / nrm) + _f(M[1] / nrm) + _f(M[2] / nrm))
        g = np.asarray(lc.gravity, float)
        if np.any(g):
            gn = float(np.linalg.norm(g))
            z.append("GRAV    " + _i(k) + "        " + _f(gn)
                     + _f(g[0] / gn) + _f(g[1] / gn) + _f(g[2] / gn))
    z.append("ENDDATA")
    with open(path, "w", encoding="ascii", errors="replace") as f:
        f.write("\n".join(z) + "\n")
    C.say(log, f"Nastran Bulk Data geschrieben: {model.nn} Knoten, {eid} Elemente "
               f"-> {path}")
    return path
