"""
Export nach SDNF - Steel Detailing Neutral Format.

Geschrieben wird die Fassung 3.0 mit den Paketen 00 (Kopf), 10 (lineare
Bauteile mit beiden Endpunkten, Profil, Werkstoff, Verdrehung), 20 (Bleche mit
vier Eckpunkten und Dicke) und 99 (Ende). HiCAD, Tekla, SDS/2 und Advance Steel
lesen das Format.

    from statik3d.exporters.sdnf import write_sdnf
    write_sdnf(m, "bauwerk.sdnf")
"""
from __future__ import annotations

import math
import os
from datetime import datetime

import numpy as np

from ..model import Model
from . import _common as C

#: Bauteilart in Paket 10 (SDNF): 1 Traeger, 2 Stuetze, 3 Strebe
def _member_type(model: Model, elems: list) -> int:
    p1 = model.nodes[model.elements[elems[0]].nodes[0]]
    p2 = model.nodes[model.elements[elems[-1]].nodes[1]]
    d = np.asarray(p2, float) - np.asarray(p1, float)
    n = np.linalg.norm(d)
    if n <= 0:
        return 1
    steil = abs(float(d[2])) / n
    if steil > 0.85:
        return 2
    return 1 if steil < 0.15 else 3


def write_sdnf(model: Model, path: str, results=None, log: list = None,
               unit: str = "mm", projekt: str = "", **_) -> str:
    """Modell als SDNF schreiben. Rueckgabe: Pfad."""
    faktor = {"mm": 1000.0, "m": 1.0, "inch": 1.0 / 0.0254}.get(unit, 1000.0)
    kennzahl = {"mm": 1, "inch": 2}.get(unit, 1)
    ketten = C.member_chains(model)
    dreiecke = C.shell_elements(model)
    zeilen = []
    zeilen.append("Packet 00")
    zeilen.append('"Statik3D" "2.1" "Statik3D FEM"')
    zeilen.append(f'"{projekt or model.meta.get("projekt") or model.name}" '
                  f'"{model.meta.get("position") or ""}" '
                  f'"{model.meta.get("bearbeiter") or ""}"')
    zeilen.append(f'"{datetime.now().strftime("%Y-%m-%d %H:%M")}"')
    zeilen.append(str(kennzahl))

    zeilen.append("Packet 10")
    zeilen.append(str(len(ketten)))
    for i, (name, elems) in enumerate(ketten, 1):
        na, nb = C.chain_ends(model, elems)
        p1 = np.asarray(model.nodes[na], float) * faktor
        p2 = np.asarray(model.nodes[nb], float) * faktor
        e = model.elements[elems[0]]
        sec = e.sec or "unbekannt"
        mat = C.steel_grade(model, e.mat)
        typ = _member_type(model, elems)
        zeilen.append(f'"{name}" 0 {typ} 0 "{sec}" "{mat}" "{name}"')
        zeilen.append(" ".join(f"{v:.4f}" for v in (*p1, *p2)))
        zeilen.append(f"{math.degrees(float(e.roll)):.4f} 0.0000 0.0000")

    if dreiecke:
        zeilen.append("Packet 20")
        zeilen.append(str(len(dreiecke)))
        for k, i in enumerate(dreiecke, 1):
            el = model.elements[i]
            n = [int(x) for x in el.nodes]
            if len(n) == 3:
                n = n + [n[2]]
            pts = [np.asarray(model.nodes[x], float) * faktor for x in n[:4]]
            t = model.shells[el.sec].t if el.sec in model.shells else 0.010
            mat = C.steel_grade(model, el.mat)
            zeilen.append(f'"B{k}" 0 0 0 "{el.sec or "Blech"}" "{mat}"')
            zeilen.append(" ".join(f"{v:.4f}" for p in pts for v in p))
            zeilen.append(f"{t * faktor:.4f}")

    zeilen.append("Packet 99")
    with open(path, "w", encoding="latin-1", errors="replace") as f:
        f.write("\n".join(zeilen) + "\n")
    C.say(log, f"SDNF geschrieben: {len(ketten)} Bauteile, {len(dreiecke)} Bleche "
               f"-> {path}")
    return path
