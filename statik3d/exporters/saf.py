"""
Export nach SAF - Structural Analysis Format (Excel).

Geschrieben werden die Blaetter, die der SAF-Import wieder liest und die RFEM 6,
SCIA, Allplan und AxisVM erwarten: Knoten, Stabzuege, Staebe, Flaechen,
Querschnitte, Materialien, Lager, Lastfaelle, Lastgruppen und Lasten.
"""
from __future__ import annotations

import numpy as np

from ..model import Model
from ..importers.xlsx_reader import write_xlsx
from . import _common as C

#: Lagerbedingung -> SAF-Schluesselwort (die Federsteifigkeit steht in der
#: eigenen Spalte "Stiffness ...", so wie SAF es fuehrt)
def _cond(beh) -> str:
    if beh.typ == "rigid":
        return "Rigid"
    if beh.typ == "spring":
        return "Flexible"
    return "Free"


def write_saf(model: Model, path: str, results=None, log: list = None, **_) -> str:
    blaetter: dict[str, list[list]] = {}

    blaetter["StructuralPointConnection"] = [
        ["Name", "Coordinate X", "Coordinate Y", "Coordinate Z"]] + [
        [f"N{i + 1}", float(p[0]), float(p[1]), float(p[2])]
        for i, p in enumerate(model.nodes)]

    mats = [["Name", "Material type", "Quality", "Unit mass", "E modulus",
             "Poisson coefficient", "G modulus", "Thermal expansion",
             "Yield strength", "Ultimate strength"]]
    for name, m in model.materials.items():
        mats.append([name, "Steel", m.grade or name, float(m.rho), float(m.E),
                     float(m.nu), float(m.G), float(m.alpha),
                     float(m.fy or 0.0), float(m.fu or 0.0)])
    blaetter["StructuralMaterial"] = mats

    secs = [["Name", "Material", "Form code", "A", "I y", "I z", "I t",
             "Height", "Width", "Web thickness", "Flange thickness"]]
    for name, s in model.sections.items():
        secs.append([name, next(iter(model.materials), ""), s.typ, float(s.A),
                     float(s.Iy), float(s.Iz), float(s.It), float(s.h),
                     float(s.b), float(s.tw), float(s.tf)])
    blaetter["StructuralCrossSection"] = secs

    kurven = [["Name", "Cross-section", "Material", "Begin node", "End node",
               "Rotation", "Length", "Type"]]
    for name, elems in C.member_chains(model):
        na, nb = C.chain_ends(model, elems)
        e = model.elements[elems[0]]
        kurven.append([name, e.sec or "", e.mat, f"N{na + 1}", f"N{nb + 1}",
                       float(np.degrees(e.roll)), C.chain_length(model, elems), "Beam"])
    blaetter["StructuralCurveMember"] = kurven

    flaechen = [["Name", "Material", "Thickness", "Nodes", "Type"]]
    for i in C.shell_elements(model):
        e = model.elements[i]
        t = model.shells[e.sec].t if e.sec in model.shells else 0.010
        flaechen.append([f"S{i + 1}", e.mat, float(t),
                         ";".join(f"N{int(n) + 1}" for n in e.nodes), "Plate"])
    blaetter["StructuralSurfaceMember"] = flaechen

    # Spaltennamen nach SAF: ux uy uz fix fiy fiz, dazu die Steifigkeiten
    lager = [["Name", "Node", "ux", "uy", "uz", "fix", "fiy", "fiz",
              "Stiffness X", "Stiffness Y", "Stiffness Z",
              "Stiffness fix", "Stiffness fiy", "Stiffness fiz",
              "Coordinate system"]]
    for i, sup in enumerate(model.supports, 1):
        b = [sup.dof_behaviour(d) for d in range(6)]
        lager.append([sup.name or f"Sn{i}", f"N{sup.node + 1}"]
                     + [_cond(x) for x in b]
                     + [float(x.stiffness) if x.typ == "spring" else "" for x in b]
                     + ["Global"])
    blaetter["StructuralPointSupport"] = lager

    faelle = [["Name", "Load group", "Load type", "Action type", "Description"]]
    for name, lc in model.load_cases.items():
        faelle.append([name, lc.category, "Static", lc.category, lc.description])
    blaetter["StructuralLoadCase"] = faelle

    kombis = [["Name", "Category", "Load case", "Coefficient"]]
    for name, c in model.combinations.items():
        for lf, f in c.factors.items():
            kombis.append([name, c.typ, lf, float(f)])
    blaetter["StructuralLoadCombination"] = kombis

    lasten = [["Name", "Load case", "Node", "Fx", "Fy", "Fz", "Mx", "My", "Mz"]]
    k = 0
    for name, lc in model.load_cases.items():
        for l in lc.nodal_loads:
            k += 1
            lasten.append([f"F{k}", name, f"N{l.node + 1}"]
                          + [float(v) for v in l.F])
    blaetter["StructuralPointAction"] = lasten

    stab = [["Name", "Load case", "Member", "Direction", "q x", "q y", "q z", "System"]]
    k = 0
    for name, lc in model.load_cases.items():
        for l in lc.beam_loads:
            k += 1
            stab.append([f"Q{k}", name, f"E{l.elem + 1}", "Global"]
                        + [float(v) for v in l.q] + [l.system])
    blaetter["StructuralCurveAction"] = stab

    write_xlsx(path, blaetter)
    C.say(log, f"SAF geschrieben: {len(blaetter)} Blätter, {model.nn} Knoten, "
               f"{len(kurven) - 1} Stäbe -> {path}")
    return path
