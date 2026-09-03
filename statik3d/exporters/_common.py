"""Gemeinsame Hilfen der Exporter."""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from ..model import Model


def say(log: Optional[list], msg: str) -> None:
    if log is not None:
        log.append(msg)


def beam_elements(model: Model) -> list[int]:
    return [i for i, e in enumerate(model.elements) if e.typ in ("beam", "truss")]


def shell_elements(model: Model) -> list[int]:
    return [i for i, e in enumerate(model.elements) if e.typ.startswith("shell")]


def solid_elements(model: Model) -> list[int]:
    return [i for i, e in enumerate(model.elements) if e.typ in ("tet4", "tet10", "hex8")]


def member_chains(model: Model) -> list[tuple[str, list[int]]]:
    """[(Name, Elementliste)] der Staebe; Elemente ohne Stab kommen einzeln dazu."""
    out = []
    belongs = set()
    for name, mem in model.members.items():
        els = [int(e) for e in mem.elements]
        out.append((name, els))
        belongs.update(els)
    for i in beam_elements(model):
        if i not in belongs:
            out.append((f"E{i + 1}", [i]))
    return out


def chain_ends(model: Model, elems: list[int]) -> tuple[int, int]:
    """Anfangs- und Endknoten einer Elementkette."""
    if not elems:
        raise ValueError("leere Elementkette")
    zaehler: dict[int, int] = {}
    for i in elems:
        for n in model.elements[i].nodes[:2]:
            zaehler[int(n)] = zaehler.get(int(n), 0) + 1
    enden = [n for n, c in zaehler.items() if c == 1]
    if len(enden) == 2:
        p = model.nodes[enden]
        return (enden[0], enden[1]) if p[0].tolist() <= p[1].tolist() else (enden[1], enden[0])
    first = model.elements[elems[0]].nodes
    last = model.elements[elems[-1]].nodes
    return int(first[0]), int(last[1])


def chain_length(model: Model, elems: list[int]) -> float:
    return float(sum(model.element_length(i) for i in elems))


def material_of(model: Model, elem: int) -> str:
    return model.elements[elem].mat


def section_of(model: Model, elem: int) -> str:
    return model.elements[elem].sec or ""


def steel_grade(model: Model, name: str) -> str:
    m = model.materials.get(name)
    if m is None:
        return "S235"
    return m.grade or name


def triangles(model: Model) -> list[tuple[int, int, int]]:
    """Alle Schalenelemente als Dreiecke (Vierecke aufgeteilt)."""
    out = []
    for i in shell_elements(model):
        n = [int(x) for x in model.elements[i].nodes]
        if len(n) >= 3:
            out.append((n[0], n[1], n[2]))
        if len(n) == 4:
            out.append((n[0], n[2], n[3]))
    return out


def solid_faces(model: Model) -> list[tuple]:
    """Aussenflaechen der Volumenelemente (Facetten, die nur einmal vorkommen)."""
    from .. import mesher
    try:
        return mesher.surface_facets(model)
    except Exception:            # noqa: BLE001
        return []


def bbox(model: Model):
    return model.bbox()
