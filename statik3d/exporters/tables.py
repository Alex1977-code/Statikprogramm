"""
Export als Tabellen im RFEM-Aufbau (CSV je Blatt in einem Ordner).

Die Blattnamen und Spaltenueberschriften entsprechen dem Tabellenexport von
RFEM/RSTAB, sodass die Dateien von Statik3D selbst und von RFEM wieder gelesen
werden koennen.
"""
from __future__ import annotations

import csv
import os

import numpy as np

from ..model import Model
from . import _common as C

BLAETTER = ["1.1 Knoten", "1.2 Linien", "1.3 Materialien", "1.4 Querschnitte",
            "1.7 Stäbe", "1.10 Flächen", "1.13 Knotenlager",
            "2.1 Lastfälle", "3.1 Knotenlasten", "3.2 Stablasten"]


def write_tables(model: Model, path: str, results=None, log: list = None,
                 delimiter: str = ";", **_) -> str:
    ordner = path if not os.path.splitext(path)[1] else os.path.splitext(path)[0]
    os.makedirs(ordner, exist_ok=True)

    def schreibe(name, kopf, zeilen):
        p = os.path.join(ordner, f"{name}.csv")
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=delimiter)
            w.writerow(kopf)
            w.writerows(zeilen)
        return len(zeilen)

    n = schreibe("1.1 Knoten", ["Knoten Nr.", "X [m]", "Y [m]", "Z [m]"],
                 [[i + 1, f"{p[0]:.6f}", f"{p[1]:.6f}", f"{p[2]:.6f}"]
                  for i, p in enumerate(model.nodes)])
    schreibe("1.2 Linien", ["Nr.", "Typ", "Knotenliste"],
             [[i + 1, ln.typ, ",".join(str(x + 1) for x in ln.nodes)]
              for i, ln in enumerate(model.lines.values())])
    schreibe("1.3 Materialien",
             ["Material Nr.", "Name", "E [N/m2]", "G [N/m2]", "nu", "rho [kg/m3]",
              "alpha [1/K]", "f_y [N/m2]", "f_u [N/m2]"],
             [[i + 1, name, f"{m.E:.6g}", f"{m.G:.6g}", f"{m.nu:.4g}",
               f"{m.rho:.6g}", f"{m.alpha:.4g}",
               f"{m.fy:.6g}" if m.fy else "", f"{m.fu:.6g}" if m.fu else ""]
              for i, (name, m) in enumerate(model.materials.items())])
    schreibe("1.4 Querschnitte",
             ["Querschnitt Nr.", "Bezeichnung", "Material Nr.", "A [m2]", "I_y [m4]",
              "I_z [m4]", "I_t [m4]", "h [m]", "b [m]"],
             [[i + 1, name, 1, f"{s.A:.6g}", f"{s.Iy:.6g}", f"{s.Iz:.6g}",
               f"{s.It:.6g}", f"{s.h:.4g}", f"{s.b:.4g}"]
              for i, (name, s) in enumerate(model.sections.items())])
    staebe = []
    for k, (name, elems) in enumerate(C.member_chains(model), 1):
        na, nb = C.chain_ends(model, elems)
        e = model.elements[elems[0]]
        staebe.append([k, name, na + 1, nb + 1, e.sec or "", e.mat,
                       f"{np.degrees(float(e.roll)):.4f}",
                       f"{C.chain_length(model, elems):.4f}"])
    # Spaltennamen so, wie der RFEM-Tabellenimport sie erwartet
    schreibe("1.7 Stäbe", ["Stab Nr.", "Name", "Knoten Nr. Anfang", "Knoten Nr. Ende",
                           "Querschnitt Nr.", "Material", "Drehung [Grad]", "Länge [m]"],
             staebe)
    schreibe("1.10 Flächen", ["Nr.", "Typ", "Knotenliste", "Dicke [m]", "Material"],
             [[i + 1, e.typ, ",".join(str(int(x) + 1) for x in e.nodes),
               f"{model.shells[e.sec].t:.5g}" if e.sec in model.shells else "", e.mat]
              for i, e in enumerate(model.elements) if e.typ.startswith("shell")])
    schreibe("1.13 Knotenlager",
             ["Nr.", "Knoten", "Name", "ux", "uy", "uz", "phix", "phiy", "phiz"],
             [[i + 1, s.node + 1, s.name or ""]
              + [s.dof_behaviour(d).describe() for d in range(6)]
              for i, s in enumerate(model.supports)])
    schreibe("2.1 Lastfälle",
             ["Nr.", "Bezeichnung", "Einwirkungskategorie", "Beschreibung",
              "Eigengewicht z [m/s2]"],
             [[i + 1, name, lc.category, lc.description,
               f"{float(np.asarray(lc.gravity, float)[2]):.4g}"]
              for i, (name, lc) in enumerate(model.load_cases.items())])
    kl = []
    for name, lc in model.load_cases.items():
        for l in lc.nodal_loads:
            kl.append([name, l.node + 1] + [f"{float(v):.6g}" for v in l.F])
    schreibe("3.1 Knotenlasten",
             ["Lastfall", "Knoten", "F_X [N]", "F_Y [N]", "F_Z [N]",
              "M_X [Nm]", "M_Y [Nm]", "M_Z [Nm]"], kl)
    sl = []
    for name, lc in model.load_cases.items():
        for l in lc.beam_loads:
            sl.append([name, l.elem + 1, l.system]
                      + [f"{float(v):.6g}" for v in l.q])
    schreibe("3.2 Stablasten",
             ["Lastfall", "Stab", "System", "q_x [N/m]", "q_y [N/m]", "q_z [N/m]"], sl)
    C.say(log, f"Tabellen geschrieben: {len(BLAETTER)} Blätter, {n} Knoten -> {ordner}")
    return ordner
