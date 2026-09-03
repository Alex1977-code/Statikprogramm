"""
Lager auf Knotenfreiheitsgrade umlegen.

Knotenlager, Linienlager und Flaechenlager werden einheitlich in eine Liste von
NodalDof-Eintraegen umgerechnet (je Knoten und Freiheitsgrad). Linienlager
werden ueber die Einflusslaenge (halbe Nachbarabschnitte), Flaechenlager ueber
die Einflussflaeche der Knoten verteilt.

    from statik3d import supports
    entries = supports.expand(model)         # alle Lager als Knoten-FHG
    lin, nlin = supports.split(entries)      # linear (Sperrung/Feder) / nichtlinear

Die linearen Anteile setzt assemble.py um (Sperrung bzw. Federsteifigkeit), die
nichtlinearen contact.py (Ausfall bei Zug/Druck, Schlupf, Reibung, Grenzkraft).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .model import Model, NDOF, DOF_NAMES, DofBehaviour


@dataclass
class NodalDof:
    """Ein Lager-Freiheitsgrad an einem Knoten mit absoluter Steifigkeit."""
    node: int
    dof: int                       # 0..5
    typ: str = "rigid"             # rigid | spring
    stiffness: float = 0.0         # [N/m] bzw. [Nm/rad] (absolut)
    failure: str = ""              # '' | 'zug' | 'druck'
    slip: float = 0.0
    mu: float = 0.0
    mu_ref: Optional[int] = None
    limit: float = 0.0
    value: float = 0.0             # vorgegebene Verschiebung (nur starr, linear)
    label: str = ""
    source: str = "node"           # node | line | surface

    @property
    def index(self) -> int:
        return NDOF * self.node + self.dof

    @property
    def nonlinear(self) -> bool:
        return bool(self.failure) or self.mu > 0 or self.slip > 0 or self.limit > 0

    def describe(self) -> str:
        return f"{self.label} {DOF_NAMES[self.dof]}"


# --------------------------------------------------------------------------
# Einflusslaengen und -flaechen
# --------------------------------------------------------------------------
def tributary_lengths(model: Model, nodes: list[int]) -> dict[int, float]:
    """Einflusslaenge je Knoten eines Linienzugs (halbe Nachbarabschnitte)."""
    nodes = [int(n) for n in nodes]
    out = {n: 0.0 for n in nodes}
    if len(nodes) < 2:
        return out
    P = model.nodes[nodes]
    for i in range(len(nodes) - 1):
        L = float(np.linalg.norm(P[i + 1] - P[i]))
        out[nodes[i]] += 0.5 * L
        out[nodes[i + 1]] += 0.5 * L
    return out


def _triangle_area(P) -> float:
    return 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))


def element_faces(model: Model, elem: int, face: int = -1) -> list[list[int]]:
    """Knotenlisten der belegten Flaechen eines Elements.
    Schalen: das Element selbst. Volumen: die gewaehlte Flaeche (face = -1: alle)."""
    from .assemble import SOLID_FACES
    e = model.elements[elem]
    if e.typ in ("shell3", "shell4"):
        return [list(e.nodes)]
    faces = SOLID_FACES.get(e.typ)
    if not faces:
        return []
    if face is None or face < 0:
        return [[int(e.nodes[k]) for k in f] for f in faces]
    if face >= len(faces):
        return []
    return [[int(e.nodes[k]) for k in faces[face]]]


def tributary_areas(model: Model, elements: list[int], face: int = -1) -> dict[int, float]:
    """Einflussflaeche je Knoten (Flaeche gleichmaessig auf die Eckknoten verteilt).
    Bei face = -1 an Volumen werden nur die Aussenflaechen belegt (innere Flaechen
    kommen doppelt vor und werden verworfen)."""
    out: dict[int, float] = {}
    counted: dict[tuple, list] = {}
    for ei in elements:
        if ei < 0 or ei >= len(model.elements):
            continue
        for f in element_faces(model, ei, face):
            key = tuple(sorted(f))
            if key in counted:
                counted[key] = None          # innen: von zwei Elementen belegt
            else:
                counted[key] = f
    for f in counted.values():
        if f is None:
            continue
        P = model.nodes[f]
        A = _triangle_area(P[:3]) if len(f) == 3 else _triangle_area(P[[0, 1, 2]]) + _triangle_area(P[[0, 2, 3]])
        for n in f:
            out[int(n)] = out.get(int(n), 0.0) + A / len(f)
    return out


# --------------------------------------------------------------------------
# Expansion
# --------------------------------------------------------------------------
def _entry(node: int, dof: int, b: DofBehaviour, factor: float, label: str,
           source: str, value: float = 0.0) -> Optional[NodalDof]:
    if not b.acts:
        return None
    k = b.stiffness * factor if b.typ == "spring" else 0.0
    if b.typ == "spring" and k <= 0:
        return None
    return NodalDof(int(node), int(dof), b.typ, k, b.failure, b.slip, b.mu, b.mu_ref,
                    b.limit * factor if b.limit else 0.0, value, label, source)


def expand(model: Model, log: list = None) -> list[NodalDof]:
    """Alle Lager als Knoten-FHG. Mehrfach belegte FHG werden zusammengefasst:
    starr schlaegt Feder, Federn addieren sich."""
    out: list[NodalDof] = []
    for si, s in enumerate(model.supports):
        label = s.name or f"Knotenlager {s.node}"
        for dof in range(NDOF):
            b = s.dof_behaviour(dof)
            val = 0.0
            if s.values and dof in s.dofs:
                val = float(s.values[s.dofs.index(dof)])
            e = _entry(s.node, dof, b, 1.0, label, "node", val)
            if e is not None:
                out.append(e)
    for ls in model.line_supports:
        nodes = list(ls.nodes)
        if not nodes and ls.line and ls.line in model.lines:
            nodes = list(model.lines[ls.line].nodes)
        trib = tributary_lengths(model, nodes)
        if nodes and not any(trib.values()) and log is not None:
            log.append(f"Linienlager '{ls.name}': Laenge 0 - keine Wirkung")
        for n in nodes:
            for dof in range(NDOF):
                e = _entry(n, dof, ls.dof_behaviour(dof), trib.get(n, 0.0),
                           ls.name or "Linienlager", "line")
                if e is not None:
                    out.append(e)
    for ss in model.surface_supports:
        trib = dict(zip([int(n) for n in ss.nodes], [float(a) for a in ss.areas])) \
            if ss.nodes and len(ss.nodes) == len(ss.areas) else tributary_areas(model, ss.elements, ss.face)
        if not trib and log is not None:
            log.append(f"Flaechenlager '{ss.name}': keine Flaeche gefunden")
        for n, A in trib.items():
            for dof in range(NDOF):
                e = _entry(n, dof, ss.dof_behaviour(dof), A, ss.name or "Flaechenlager", "surface")
                if e is not None:
                    out.append(e)
    return _merge(out)


def _merge(entries: list[NodalDof]) -> list[NodalDof]:
    """Mehrfach belegte (Knoten, FHG): lineare Federn addieren, starr gewinnt.
    Nichtlineare Eintraege bleiben einzeln erhalten (sie wirken nebeneinander)."""
    lin: dict[tuple, NodalDof] = {}
    out: list[NodalDof] = []
    for e in entries:
        if e.nonlinear:
            out.append(e)
            continue
        key = (e.node, e.dof)
        cur = lin.get(key)
        if cur is None:
            lin[key] = e
        elif cur.typ == "rigid" or e.typ == "rigid":
            if e.typ == "rigid" and cur.typ != "rigid":
                lin[key] = e
        else:
            cur.stiffness += e.stiffness
    return list(lin.values()) + out


def split(entries: list[NodalDof]):
    """(lineare, nichtlineare) Eintraege."""
    return [e for e in entries if not e.nonlinear], [e for e in entries if e.nonlinear]


def summary(model: Model) -> str:
    entries = expand(model)
    lin, nlin = split(entries)
    n_fix = sum(1 for e in lin if e.typ == "rigid")
    n_spring = sum(1 for e in lin if e.typ == "spring")
    kinds: dict[str, int] = {}
    for e in nlin:
        k = e.failure or ("Reibung" if e.mu else "Schlupf" if e.slip else "Grenzkraft")
        kinds[k] = kinds.get(k, 0) + 1
    s = (f"Lager: {n_fix} starre FHG, {n_spring} Federn, {len(nlin)} nichtlineare FHG"
         + (" (" + ", ".join(f"{v}x {k}" for k, v in sorted(kinds.items())) + ")" if kinds else ""))
    if model.line_supports:
        s += f"; {len(model.line_supports)} Linienlager"
    if model.surface_supports:
        s += f", {len(model.surface_supports)} Flaechenlager"
    return s
