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
# Lager folgen dem Netz
# --------------------------------------------------------------------------
def _ringflaeche(P) -> float:
    """Inhalt eines ebenen Vielecks (Newell)."""
    P = np.asarray(P, float)
    if len(P) < 3:
        return 0.0
    n = np.cross(P, np.roll(P, -1, axis=0)).sum(axis=0)
    return 0.5 * float(np.linalg.norm(n))


def _geometrieknoten(model: Model, f) -> list[int]:
    """Die Knoten der Randlinien einer Flaeche (Eckknoten der Geometrie)."""
    out: list[int] = []
    for ln in (f.linien or []):
        line = (model.lines or {}).get(ln)
        for n in (line.nodes if line is not None else []):
            n = int(n)
            if 0 <= n < model.nn and n not in out:
                out.append(n)
    return out


def _facetten_geometrisch(model: Model, f) -> list:
    """Die Aussenfacetten eines vernetzten Koerpers, die auf der ebenen
    Flaeche *f* liegen - fuer Netze, die keine Randseiten je Flaeche
    fuehren (abgebildete Hexaedernetze). Rueckgabe [(Element, Knoten, None)].
    """
    from .fugen import _punkte_im_polygon
    koerper = getattr(model, "koerper", {}) or {}
    k = next((k for k in koerper.values() if f.name in k.flaechen and k.elemente), None)
    if k is None:
        return []
    try:
        P = np.asarray(f.randpunkte(model), float)
    except Exception:                   # noqa: BLE001
        return []
    if len(P) < 3:
        return []
    n = np.cross(P, np.roll(P, -1, axis=0)).sum(axis=0)
    ln = float(np.linalg.norm(n))
    if ln <= 0:
        return []
    n = n / ln
    c = P.mean(axis=0)
    groesse = float(np.linalg.norm(P - c, axis=1).max()) or 1.0
    tol = 1e-6 * groesse + 1e-9
    if np.abs((P - c) @ n).max() > 1e-3 * groesse:
        return []                       # krumme Flaeche: keine Ebene
    kanten = np.diff(np.vstack([P, P[:1]]), axis=0)
    u = kanten[int(np.argmax(np.linalg.norm(kanten, axis=1)))]
    u = u - (u @ n) * n
    u = u / (np.linalg.norm(u) or 1.0)
    v = np.cross(n, u)
    P2 = np.column_stack([(P - c) @ u, (P - c) @ v])
    # Aussenfacetten des Koerpers: nur einmal belegte Seiten
    gezaehlt: dict = {}
    for ei in k.elemente:
        ei = int(ei)
        if not 0 <= ei < len(model.elements):
            continue
        for seite in element_faces(model, ei, -1):
            key = tuple(sorted(int(x) for x in seite))
            gezaehlt[key] = None if key in gezaehlt else (ei, [int(x) for x in seite])
    aussen = [x for x in gezaehlt.values() if x is not None]
    if not aussen:
        return []
    out = []
    for ei, nd in aussen:
        X = model.nodes[nd]
        if np.abs((X - c) @ n).max() > tol:
            continue
        s = X.mean(axis=0) - c
        if _punkte_im_polygon(P2, np.array([[s @ u, s @ v]]), rand=tol)[0]:
            out.append((ei, nd, None))
    return out


def _nur_in_der_ebene(model: Model, f, facetten: list) -> list:
    """Bei einer **ebenen** Flaeche nur die Facetten, die in ihrer Ebene liegen.

    Die Randseiten eines Koerpers werden je Flaeche gefuehrt; an den Kanten
    einer Platte koennen dabei auch Seitenfacetten an der Deckflaeche
    haengen. Fuer die Bettung zaehlt nur, was auf der Flaeche liegt - sonst
    waere die Einflussflaeche um die Seitenflaechen zu gross. Krumme Flaechen
    bleiben, wie sie sind.
    """
    if not facetten:
        return facetten
    try:
        P = np.asarray(f.randpunkte(model), float)
    except Exception:                   # noqa: BLE001
        return facetten
    if len(P) < 3:
        return facetten
    n = np.cross(P, np.roll(P, -1, axis=0)).sum(axis=0)
    ln = float(np.linalg.norm(n))
    if ln <= 0:
        return facetten
    n = n / ln
    c = P.mean(axis=0)
    groesse = float(np.linalg.norm(P - c, axis=1).max()) or 1.0
    if np.abs((P - c) @ n).max() > 1e-3 * groesse:
        return facetten                 # krumm: keine Ebene
    tol = 1e-4 * groesse + 1e-9
    out = []
    for e, nd, nf in facetten:
        X = model.nodes[[int(x) for x in nd]]
        if np.abs((X - c) @ n).max() <= tol:
            out.append((e, nd, nf))
    return out


def flaechen_einflussflaechen(model: Model, flaechen: list) -> dict[int, float]:
    """Einflussflaeche je Knoten auf diesen Geometrieflaechen.

    Vernetzte Flaechen: aus den Facetten des Netzes (Schalenelemente, oder
    die Randseiten der Volumen auf der Flaeche; fehlen sie am Netz, die
    Aussenfacetten des Koerpers in der Ebene der Flaeche) - jede Facette gibt
    ihren Inhalt gleichmaessig an ihre Knoten. Flaechen ohne Netz: die
    Eckknoten der Randlinien, der Flaecheninhalt gleich verteilt (wie beim
    Import).
    """
    from .fugen import _dreiecke_der_fuge
    trib: dict[int, float] = {}
    for f in flaechen:
        facetten = _dreiecke_der_fuge(model, [f])
        if not facetten and not (f.elemente or f.randseiten):
            facetten = _facetten_geometrisch(model, f)
        facetten = _nur_in_der_ebene(model, f, facetten)
        if facetten:
            for _e, nd, _n in facetten:
                nd = [int(x) for x in nd]
                P = model.nodes[nd]
                A = _triangle_area(P[:3]) if len(nd) == 3 \
                    else _triangle_area(P[[0, 1, 2]]) + _triangle_area(P[[0, 2, 3]])
                for n in nd:
                    trib[n] = trib.get(n, 0.0) + A / len(nd)
            continue
        ecken = _geometrieknoten(model, f)
        if not ecken:
            continue
        try:
            A = float(f.inhalt(model))
        except Exception:               # noqa: BLE001 - offener Rand: kein Inhalt
            A = 0.0
        for n in ecken:
            trib[n] = trib.get(n, 0.0) + A / len(ecken)
    return trib


def knoten_auf_linie(model: Model, P: np.ndarray, tol: float) -> list[int]:
    """Alle Knoten, die auf dem Linienzug P liegen - in Reihenfolge der Linie."""
    P = np.atleast_2d(np.asarray(P, float))
    if len(P) < 2 or not model.nn:
        return []
    from scipy.spatial import cKDTree
    baum = cKDTree(model.nodes)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    lage: dict[int, float] = {}
    for k in range(len(P) - 1):
        a, b = P[k], P[k + 1]
        d = b - a
        L2 = float(d @ d)
        if L2 <= 0:
            continue
        kand = baum.query_ball_point(0.5 * (a + b), 0.5 * np.sqrt(L2) + tol)
        if not kand:
            continue
        Q = model.nodes[kand]
        t = np.clip(((Q - a) @ d) / L2, 0.0, 1.0)
        abstand = np.linalg.norm(Q - (a + t[:, None] * d), axis=1)
        for i, ti, di in zip(kand, t, abstand):
            if di <= tol:
                s = cum[k] + ti * seg[k]
                if int(i) not in lage or s < lage[int(i)]:
                    lage[int(i)] = float(s)
    return [n for n, _s in sorted(lage.items(), key=lambda x: x[1])]


def lager_auf_netz(model: Model, log: list = None) -> dict:
    """Linien- und Flaechenlager von der Geometrie auf das Netz bringen.

    Ein aus RFEM uebernommenes Flaechenlager kennt seine Flaechen; seine
    Knoten sind zunaechst nur die Eckknoten der Geometrie, der Inhalt der
    Flaeche gleich verteilt. Nach dem Vernetzen liegen auf der Flaeche viele
    Netzknoten - die Bettung muss auf **sie** wirken, sonst haengt die
    Platte zwischen vier Eckfedern. Hier bekommt jedes Lager mit
    Flaechenangabe seine Knoten und Einflussflaechen aus dem Netz seiner
    Flaechen (Schalenelemente oder Randseiten der Volumen); Flaechen ohne
    Netz behalten die Eckknoten. Ein Linienlager mit Linienangabe bekommt
    alle Netzknoten auf seinen Linien, in Reihenfolge der Linie - auch auf
    einem Bogen. Das Ergebnis haengt nur von Geometrie und Netz ab; der
    Aufruf ist beliebig wiederholbar (nach dem Vernetzen, nach dem Loeschen
    des Netzes, vor jeder Rechnung).

    Rueckgabe {"flaechenlager": n, "linienlager": n} - so viele Lager haben
    ihre Knoten aus dem Netz bekommen.
    """
    flaechen = getattr(model, "flaechen", {}) or {}
    linien = getattr(model, "lines", {}) or {}
    n_f = n_l = 0
    for ss in (model.surface_supports or []):
        namen = [n for n in (getattr(ss, "flaechen", None) or []) if n in flaechen]
        if not namen:
            continue
        trib = flaechen_einflussflaechen(model, [flaechen[n] for n in namen])
        if not trib:
            continue
        ss.nodes = sorted(trib)
        ss.areas = [trib[n] for n in ss.nodes]
        ss.elements = []
        n_f += 1
    if model.nn:
        groesse = float(np.ptp(np.asarray(model.nodes, float), axis=0).max() or 1.0)
    else:
        groesse = 1.0
    for ls in (model.line_supports or []):
        namen = [n for n in (getattr(ls, "linien", None) or []) if n in linien]
        if not namen:
            continue
        kette: list[int] = []
        for name in namen:
            ln = linien[name]
            try:
                P = np.asarray(ln.punkte(model, 64), float)
            except Exception:           # noqa: BLE001 - Linie ohne Kurve: die Knoten
                idx = [int(n) for n in ln.nodes if 0 <= int(n) < model.nn]
                P = model.nodes[idx] if len(idx) > 1 else np.zeros((0, 3))
            if len(P) < 2:
                continue
            L = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
            tol = max(2e-3 * L, 1e-6 * groesse)
            for n in knoten_auf_linie(model, P, tol):
                if n not in kette:
                    kette.append(n)
        if kette:
            ls.nodes = kette
            n_l += 1
    if log is not None and (n_f or n_l):
        log.append(f"  Lager auf dem Netz: {n_f} Flächenlager, {n_l} Linienlager")
    return {"flaechenlager": n_f, "linienlager": n_l}


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
    # Lager mit Geometriebezug folgen dem Netz - was gerade vernetzt ist
    if any(getattr(x, "flaechen", None) for x in (model.surface_supports or [])) \
            or any(getattr(x, "linien", None) for x in (model.line_supports or [])):
        lager_auf_netz(model)
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
