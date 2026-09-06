"""
Vernetzung.

Zwei Wege:
  1. gmsh (optional, 'pip install gmsh'): Import von STEP/IGES/BREP/STL und
     automatische Vernetzung mit Tet4/Tet10 bzw. Dreiecksschalen.
  2. Eingebaute strukturierte Netzgeneratoren fuer Quader, Platten und
     Rotationskoerper - ohne Zusatzabhaengigkeit.
"""
from __future__ import annotations

import numpy as np

from .model import Model
from .elements.solid import normalize_tet10

try:
    import gmsh  # noqa
    HAVE_GMSH = True
except Exception:
    HAVE_GMSH = False

# gmsh-Elementtypen
GMSH_TRI3, GMSH_QUAD4, GMSH_TET4, GMSH_HEX8, GMSH_TRI6, GMSH_TET10 = 2, 3, 4, 5, 9, 11


# --------------------------------------------------------------------------
def _gmsh_extract(model: Model, mat: str, shell_prop: str, dim: int, order: int):
    node_tags, coords, _ = gmsh.model.mesh.getNodes()
    coords = np.asarray(coords, float).reshape(-1, 3)
    tag2idx = {}
    base = model.nn
    model.nodes = np.vstack([model.nodes, coords]) if model.nn else coords.copy()
    for i, t in enumerate(node_tags):
        tag2idx[int(t)] = base + i

    etypes, etags, enodes = gmsh.model.mesh.getElements(dim=dim)
    n_added = 0
    for et, tags, nds in zip(etypes, etags, enodes):
        nds = np.asarray(nds, dtype=np.int64)
        if et == GMSH_TET4:
            conn = nds.reshape(-1, 4)
            for row in conn:
                model.add_element("tet4", [tag2idx[int(t)] for t in row], mat)
        elif et == GMSH_TET10:
            conn = nds.reshape(-1, 10)
            for row in conn:
                ids = [tag2idx[int(t)] for t in row]
                ids = normalize_tet10(ids, model.nodes[ids])
                model.add_element("tet10", ids, mat)
        elif et == GMSH_HEX8:
            conn = nds.reshape(-1, 8)
            for row in conn:
                model.add_element("hex8", [tag2idx[int(t)] for t in row], mat)
        elif et == GMSH_TRI3:
            conn = nds.reshape(-1, 3)
            for row in conn:
                model.add_element("shell3", [tag2idx[int(t)] for t in row],
                                  mat, shell_prop)
        elif et == GMSH_QUAD4:
            conn = nds.reshape(-1, 4)
            for row in conn:
                model.add_element("shell4", [tag2idx[int(t)] for t in row],
                                  mat, shell_prop)
        else:
            continue
        n_added += len(nds) // {GMSH_TET4: 4, GMSH_TET10: 10, GMSH_HEX8: 8,
                                GMSH_TRI3: 3, GMSH_QUAD4: 4}[et]
    return n_added


def mesh_cad(model: Model, path: str, mat: str, size: float = 0.0,
             order: int = 2, dim: int = 3, shell_prop: str = None,
             size_min: float = 0.0) -> int:
    """CAD-Datei (STEP/IGES/BREP/STL) importieren und vernetzen.

    dim=3 -> Volumennetz (Tet4/Tet10), dim=2 -> Schalennetz (Dreiecke).
    size=0 -> gmsh waehlt automatisch.
    """
    if not HAVE_GMSH:
        raise RuntimeError("gmsh ist nicht installiert. Bitte 'pip install gmsh'.")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("import")
        gmsh.merge(path)
        if path.lower().endswith((".stl", ".ply")):
            gmsh.model.mesh.classifySurfaces(np.pi / 6, True, True)
            gmsh.model.mesh.createGeometry()
            if dim == 3:
                s = gmsh.model.getEntities(2)
                loop = gmsh.model.geo.addSurfaceLoop([e[1] for e in s])
                gmsh.model.geo.addVolume([loop])
                gmsh.model.geo.synchronize()
        else:
            gmsh.model.occ.synchronize()
        if size > 0:
            gmsh.option.setNumber("Mesh.MeshSizeMax", size)
            gmsh.option.setNumber("Mesh.MeshSizeMin", size_min if size_min > 0 else size / 4)
        gmsh.model.mesh.generate(dim)
        if order == 2 and dim == 3:
            gmsh.model.mesh.setOrder(2)
        return _gmsh_extract(model, mat, shell_prop, dim, order)
    finally:
        gmsh.finalize()


def mesh_box_gmsh(model: Model, mat: str, lx, ly, lz, size, order=2,
                  origin=(0, 0, 0)) -> int:
    """Quader mit gmsh vernetzen (Tetraeder)."""
    if not HAVE_GMSH:
        raise RuntimeError("gmsh ist nicht installiert.")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("box")
        gmsh.model.occ.addBox(origin[0], origin[1], origin[2], lx, ly, lz)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.model.mesh.generate(3)
        if order == 2:
            gmsh.model.mesh.setOrder(2)
        return _gmsh_extract(model, mat, None, 3, order)
    finally:
        gmsh.finalize()


# --------------------------------------------------------------------------
# Eingebaute strukturierte Netze (ohne gmsh)
# --------------------------------------------------------------------------
def grid_box(model: Model, mat: str, lx, ly, lz, nx, ny, nz,
             origin=(0, 0, 0), typ="hex8") -> np.ndarray:
    """Strukturiertes Hexaeder- oder Tetraedernetz eines Quaders.
    Rueckgabe: Knoten-Index-Array der Form (nx+1, ny+1, nz+1)."""
    ox, oy, oz = origin
    ids = np.zeros((nx + 1, ny + 1, nz + 1), dtype=int)
    for i in range(nx + 1):
        for j in range(ny + 1):
            for k in range(nz + 1):
                ids[i, j, k] = model.add_node(ox + i * lx / nx,
                                              oy + j * ly / ny,
                                              oz + k * lz / nz)
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                c = [ids[i, j, k], ids[i + 1, j, k], ids[i + 1, j + 1, k],
                     ids[i, j + 1, k], ids[i, j, k + 1], ids[i + 1, j, k + 1],
                     ids[i + 1, j + 1, k + 1], ids[i, j + 1, k + 1]]
                if typ == "hex8":
                    model.add_element("hex8", c, mat)
                else:
                    for tet in [(0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6),
                                (1, 4, 5, 6), (3, 4, 6, 7)]:
                        model.add_element("tet4", [c[x] for x in tet], mat)
    return ids


def grid_plate(model: Model, mat: str, prop: str, lx, ly, nx, ny,
               origin=(0, 0, 0), quad=True) -> np.ndarray:
    """Strukturiertes Schalennetz in der xy-Ebene."""
    ox, oy, oz = origin
    ids = np.zeros((nx + 1, ny + 1), dtype=int)
    for i in range(nx + 1):
        for j in range(ny + 1):
            ids[i, j] = model.add_node(ox + i * lx / nx, oy + j * ly / ny, oz)
    for i in range(nx):
        for j in range(ny):
            n1, n2 = ids[i, j], ids[i + 1, j]
            n3, n4 = ids[i + 1, j + 1], ids[i, j + 1]
            if quad:
                model.add_element("shell4", [n1, n2, n3, n4], mat, prop)
            else:
                model.add_element("shell3", [n1, n2, n3], mat, prop)
                model.add_element("shell3", [n1, n3, n4], mat, prop)
    return ids


def line_of_beams(model: Model, mat: str, sec: str, p1, p2, n: int) -> list[int]:
    """Kette von n Balkenelementen zwischen zwei Punkten."""
    p1 = np.asarray(p1, float)
    p2 = np.asarray(p2, float)
    ids = [model.add_node(*(p1 + (p2 - p1) * i / n)) for i in range(n + 1)]
    for i in range(n):
        model.add_element("beam", [ids[i], ids[i + 1]], mat, sec)
    return ids


# --------------------------------------------------------------------------
def merge_nodes(model: Model, tol: float = 1e-6) -> int:
    """Doppelte Knoten zusammenfuehren (z.B. nach mehrfachem Import)."""
    if model.nn == 0:
        return 0
    key = np.round(model.nodes / tol).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True,
                                  return_inverse=True)
    order = np.argsort(first)
    remap = np.zeros(len(first), dtype=int)
    remap[order] = np.arange(len(first))
    new_index = remap[inverse]
    n_removed = model.nn - len(first)
    if n_removed == 0:
        return 0
    new_nodes = np.zeros((len(first), 3))
    new_nodes[new_index] = model.nodes
    model.nodes = new_nodes
    for e in model.elements:
        e.nodes = [int(new_index[n]) for n in e.nodes]
    for s in model.supports:
        s.node = int(new_index[s.node])
    for lc in model.load_cases.values():
        for l in lc.nodal_loads:
            l.node = int(new_index[l.node])
    for c in model.contact_supports:
        c.node = int(new_index[c.node])
    for g in model.gap_elements:
        g.node_a = int(new_index[g.node_a])
        g.node_b = int(new_index[g.node_b])
    for cp in model.contact_pairs:
        cp.slave_nodes = sorted({int(new_index[n]) for n in cp.slave_nodes})
        cp.master_faces = [[int(new_index[n]) for n in f] for f in cp.master_faces]
    return n_removed


def surface_facets(model: Model) -> list[tuple]:
    """Aussenflaechen eines Volumennetzes (fuer Anzeige und Flaechenlasten)."""
    faces = {}
    face_def = {
        "tet4": [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)],
        "tet10": [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)],
        "hex8": [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
                 (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    }
    for e in model.elements:
        if e.typ not in face_def:
            continue
        for f in face_def[e.typ]:
            nodes = tuple(e.nodes[i] for i in f)
            key = tuple(sorted(nodes))
            if key in faces:
                del faces[key]
            else:
                faces[key] = nodes
    return list(faces.values())


def select_nodes(model: Model, xmin=None, xmax=None, ymin=None, ymax=None,
                 zmin=None, zmax=None, tol: float = 1e-9) -> np.ndarray:
    """Knoten in einem Koordinatenfenster auswaehlen."""
    p = model.nodes
    m = np.ones(len(p), dtype=bool)
    for i, (lo, hi) in enumerate([(xmin, xmax), (ymin, ymax), (zmin, zmax)]):
        if lo is not None:
            m &= p[:, i] >= lo - tol
        if hi is not None:
            m &= p[:, i] <= hi + tol
    return np.where(m)[0]


# ==========================================================================
# Geometriekette: Flaechen und Volumenkoerper vernetzen
#
# Aus Knoten werden Linien, aus Linien Flaechen, aus Flaechen Volumenkoerper -
# dieselbe Kette wie in RFEM. Die Objekte sind reine Geometrie; erst hier
# entsteht daraus ein Netz.
#
# Ohne allgemeinen Vernetzer geht das fuer die abbildbaren Topologien:
#   Flaeche  4 Randabschnitte  -> abgebildetes Vierecknetz (transfinit)
#            3 Randabschnitte  -> abgebildetes Dreiecknetz
#   Koerper  6 Randflaechen    -> abgebildetes Hexaedernetz
#            4 Randflaechen    -> Tetraeder
# Alles andere wird benannt und **nicht** vernetzt - eine sichtbare Luecke ist
# besser als ein stillschweigend falsches Netz.
# ==========================================================================
def _abschnitte(ring: list[int], n: int) -> list[list[int]] | None:
    """Ein Randpolygon in n gleich lange Abschnitte teilen.

    Der Rand kommt als geschlossener Knotenumlauf. Fuer ein abgebildetes Netz
    muessen die gegenueberliegenden Abschnitte gleich viele Knoten haben; das
    ist genau dann der Fall, wenn die Knotenzahl durch n teilbar ist.
    """
    m = len(ring)
    if n <= 0 or m < n or m % n:
        return None
    k = m // n
    return [[ring[(i * k + j) % m] for j in range(k + 1)] for i in range(n)]


def _kanten_gleich_lang(kanten: list[list[int]]) -> bool:
    return len({len(k) for k in kanten}) == 1


def transfinit(model: Model, unten, oben, links, rechts) -> np.ndarray:
    """Abgebildetes Punktnetz zwischen vier Randkurven (Coons-Fleck).

    ``unten``/``oben`` laufen in derselben Richtung, ebenso ``links``/``rechts``.
    Rueckgabe: Feld der Knotennummern (len(unten) x len(links)).
    """
    nu, nv = len(unten), len(links)
    ids = np.zeros((nu, nv), dtype=int)
    P = model.nodes
    for i in range(nu):
        for j in range(nv):
            if j == 0:
                ids[i, j] = unten[i]
                continue
            if j == nv - 1:
                ids[i, j] = oben[i]
                continue
            if i == 0:
                ids[i, j] = links[j]
                continue
            if i == nu - 1:
                ids[i, j] = rechts[j]
                continue
            u, v = i / (nu - 1), j / (nv - 1)
            # Coons: Summe der beiden Linearinterpolationen minus die Ecken
            p = ((1 - v) * P[unten[i]] + v * P[oben[i]]
                 + (1 - u) * P[links[j]] + u * P[rechts[j]]
                 - ((1 - u) * (1 - v) * P[unten[0]] + u * (1 - v) * P[unten[-1]]
                    + (1 - u) * v * P[oben[0]] + u * v * P[oben[-1]]))
            ids[i, j] = model.add_node(*p)
    return ids


def _kurvenpunkte(model: Model, linie: str, n: int) -> np.ndarray | None:
    """n+1 Punkte auf der **wahren** Kurve einer Linie - oder None.

    Eine Randlinie kann ein Bogen, ein Kreis, eine Ellipse, eine Parabel oder
    ein Spline sein. Verfeinert man dann nur zwischen den Stuetzknoten, laufen
    die neuen Knoten auf den Sehnen und die Flaeche wird an ihrem Rand zu
    klein. Darum wird hier die Linie selbst nach ihren Punkten gefragt.
    """
    ln = (getattr(model, "lines", {}) or {}).get(linie)
    if ln is None or (ln.typ or "polyline") == "polyline":
        return None
    try:
        pts = np.asarray(ln.kurve(model).punkte(max(n, 2)), float)
    except Exception:            # noqa: BLE001 - eine krumme Linie darf nie das
        return None              # Vernetzen verhindern; dann eben die Sehnen
    if len(pts) < 2:
        return None
    # Auf n+1 Punkte gleicher Bogenlaenge bringen
    lang = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    if lang[-1] <= 0:
        return None
    ziel = np.linspace(0.0, lang[-1], n + 1)
    out = np.empty((n + 1, 3))
    for i, sl in enumerate(ziel):
        k = min(max(int(np.searchsorted(lang, sl, side="right") - 1), 0), len(pts) - 2)
        t = (sl - lang[k]) / (lang[k + 1] - lang[k])
        out[i] = pts[k] + t * (pts[k + 1] - pts[k])
    return out


def _verdichten(model: Model, kante: list[int], n: int, linie: str = "") -> list[int]:
    """Einen Randabschnitt auf n Elemente verfeinern (neue Zwischenknoten).

    Ist ``linie`` eine krumme Linie, folgen die neuen Knoten ihrer Kurve;
    sonst den Sehnen zwischen den vorhandenen Knoten.
    """
    P = model.nodes
    pts = _kurvenpunkte(model, linie, n)
    if pts is not None:
        # Die Kurve kann gegen die Knotenfolge laufen - am naeheren Ende anfangen
        if (np.linalg.norm(pts[0] - P[kante[0]])
                > np.linalg.norm(pts[-1] - P[kante[0]])):
            pts = pts[::-1]
        return ([int(kante[0])]
                + [model.add_node(*x) for x in pts[1:-1]]
                + [int(kante[-1])])
    pts = P[kante]
    lang = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    if lang[-1] <= 0:
        return list(kante)
    ziel = np.linspace(0.0, lang[-1], n + 1)
    out = [int(kante[0])]
    for sl in ziel[1:-1]:
        k = int(np.searchsorted(lang, sl, side="right") - 1)
        k = min(max(k, 0), len(kante) - 2)
        t = (sl - lang[k]) / (lang[k + 1] - lang[k])
        out.append(model.add_node(*(pts[k] + t * (pts[k + 1] - pts[k]))))
    out.append(int(kante[-1]))
    return out


def kantenknoten(model: Model, a: int, b: int, cache: dict = None) -> int:
    """Der Knoten in der Mitte der Kante a-b - je Kante nur einmal.

    Quadratische Elemente teilen ihre Kantenmitten mit dem Nachbarn; ohne
    ``cache`` entstuenden doppelte Knoten und das Netz fiele auseinander.
    """
    a, b = int(a), int(b)
    key = (min(a, b), max(a, b))
    if cache is not None and key in cache:
        return int(cache[key])
    P = 0.5 * (model.nodes[a] + model.nodes[b])
    i = int(model.add_node(*P))
    if cache is not None:
        cache[key] = i
    return i


def netz_ordnung(model: Model, ordnung: int = 0) -> int:
    """1 = lineare, 2 = quadratische Elemente (aus den Netzeinstellungen)."""
    if ordnung and ordnung > 0:
        return int(ordnung)
    return max(1, int(getattr(getattr(model, "netz", None), "ordnung", 1) or 1))


def mesh_flaeche(model: Model, flaeche, log: list = None, dreiecke: bool = None,
                 ordnung: int = 0, kanten: dict = None) -> list[int]:
    """Eine Flaeche in Schalenelemente umsetzen.

    Vier Randabschnitte geben ein abgebildetes Vierecknetz mit der in
    ``flaeche.teilung`` genannten Elementzahl; drei Abschnitte ein Dreiecknetz.
    Jede andere Randform wird benannt und nicht vernetzt. ``dreiecke`` teilt
    jedes Viereck in zwei Dreiecke (None = nach Netzeinstellungen ``form``).
    """
    from .importers import _common as C
    if not flaeche.dicke and hasattr(model, "flaeche_traegt") and not model.flaeche_traegt(flaeche.name):
        # Randflaeche eines Volumenkoerpers ohne Dicke: kein Schalennetz - die
        # Tetraeder des Koerpers tragen (siehe Model.flaeche_traegt).
        flaeche.elemente = []
        return []
    if dreiecke is None:
        dreiecke = int(getattr(getattr(model, "netz", None), "form", 2) or 0) == 0
    ordnung = netz_ordnung(model, ordnung)
    kanten = {} if kanten is None else kanten
    ring = flaeche.randknoten(model)
    if not ring:
        C.warn(log, f"Fläche {flaeche.name}: die Linien bilden keinen geschlossenen Rand.")
        return []
    mat = flaeche.material or C.ensure_material(model, log=log)
    prop = flaeche.dicke or C.ensure_shell_prop(model, log=log)
    nu = max(1, int(flaeche.teilung[0] if flaeche.teilung else 4))
    nv = max(1, int(flaeche.teilung[1] if len(flaeche.teilung) > 1 else nu))
    # Die Linien sagen selbst, wo die vier Randabschnitte liegen; nur wenn das
    # nicht geht, wird der Umlauf gleichmaessig geviertelt.
    seiten = _seiten_aus_linien(model, flaeche)
    if seiten is None:
        vier = _abschnitte(ring, 4)
        seiten = [(k, "") for k in vier] if vier and _kanten_gleich_lang(vier) else None
    if seiten is not None and len(seiten) == 4:
        unten = _verdichten(model, seiten[0][0], nu, seiten[0][1])
        rechts = _verdichten(model, seiten[1][0], nv, seiten[1][1])
        oben = _verdichten(model, seiten[2][0][::-1], nu, seiten[2][1])
        links = _verdichten(model, seiten[3][0][::-1], nv, seiten[3][1])
        ids = transfinit(model, unten, oben, links, rechts)
        els = []
        for i in range(ids.shape[0] - 1):
            for j in range(ids.shape[1] - 1):
                a, b, c, d = (int(ids[i, j]), int(ids[i + 1, j]),
                              int(ids[i + 1, j + 1]), int(ids[i, j + 1]))
                els.extend(_flaechenelemente(model, [a, b, c, d], mat, prop,
                                             flaeche.name, dreiecke, ordnung, kanten))
        flaeche.elemente = els
        C.say(log, f"Fläche {flaeche.name}: {len(els)} "
                   + ("Dreieckelemente" if dreiecke else "Viereckelemente")
                   + (" (quadratisch)" if ordnung >= 2 else "") + f" ({nu} x {nv})")
        return els
    if len(ring) == 3:
        els = [_dreieck(model, ring, mat, prop, flaeche.name, ordnung, kanten)]
        flaeche.elemente = els
        C.say(log, f"Fläche {flaeche.name}: ein Dreieckelement")
        return els
    C.warn(log, f"Fläche {flaeche.name}: Rand aus {len(flaeche.linien)} Linien und "
                f"{len(ring)} Knoten - für ein abgebildetes Netz sind vier "
                "Randabschnitte nötig. Nicht vernetzt.")
    return []


def _dreieck(model: Model, knoten, mat, prop, gruppe: str, ordnung: int, kanten: dict) -> int:
    """Ein Dreieckelement: shell3 (linear) oder shell6 (quadratisch)."""
    a, b, c = [int(x) for x in knoten[:3]]
    if ordnung < 2:
        return model.add_element("shell3", [a, b, c], mat, prop, group=gruppe)
    m1 = kantenknoten(model, a, b, kanten)
    m2 = kantenknoten(model, b, c, kanten)
    m3 = kantenknoten(model, c, a, kanten)
    return model.add_element("shell6", [a, b, c, m1, m2, m3], mat, prop, group=gruppe)


def _viereck(model: Model, knoten, mat, prop, gruppe: str, ordnung: int, kanten: dict) -> int:
    """Ein Viereckelement: shell4 (linear) oder shell8 (quadratisch)."""
    a, b, c, d = [int(x) for x in knoten[:4]]
    if ordnung < 2:
        return model.add_element("shell4", [a, b, c, d], mat, prop, group=gruppe)
    m = [kantenknoten(model, *p, kanten) for p in ((a, b), (b, c), (c, d), (d, a))]
    return model.add_element("shell8", [a, b, c, d] + m, mat, prop, group=gruppe)


def _flaechenelemente(model: Model, viereck, mat, prop, gruppe: str, dreiecke: bool,
                      ordnung: int, kanten: dict) -> list[int]:
    """Ein Viereck des abgebildeten Netzes als ein Viereck- oder zwei
    Dreieckelemente, linear oder quadratisch."""
    a, b, c, d = [int(x) for x in viereck]
    if dreiecke:
        return [_dreieck(model, [a, b, c], mat, prop, gruppe, ordnung, kanten),
                _dreieck(model, [a, c, d], mat, prop, gruppe, ordnung, kanten)]
    return [_viereck(model, [a, b, c, d], mat, prop, gruppe, ordnung, kanten)]


def _seiten_aus_linien(model: Model, flaeche):
    """Die vier Randabschnitte aus den Linien selbst, wenn es genau vier sind.

    Rueckgabe [(Knoten, Linienname)] im Umlauf - der Name wird gebraucht, um
    eine krumme Kante spaeter auf ihrer wahren Kurve zu verfeinern.
    """
    if len(flaeche.linien) != 4:
        return None
    stuecke = [([int(n) for n in model.lines[x].nodes], x) for x in flaeche.linien]
    kette = [stuecke.pop(0)]
    while stuecke:
        ende = kette[-1][0][-1]
        for i, (st, name) in enumerate(stuecke):
            if st[0] == ende:
                kette.append((st, name))
            elif st[-1] == ende:
                kette.append((st[::-1], name))
            else:
                continue
            stuecke.pop(i)
            break
        else:
            return None
    return kette if kette[-1][0][-1] == kette[0][0][0] else None


def _entartungspruefung():
    """Die gemeinsame Grenze - eine Stelle, an der „entartet“ definiert ist."""
    from .diagnose import entartetes_volumen
    from .model import OHNE_NETZ
    return entartetes_volumen, OHNE_NETZ


def mesh_koerper(model: Model, koerper, log: list = None, frei: bool = True,
                 h: float = 0.0, cache: dict = None, ordnung: int = 0,
                 fortschritt=None) -> list[int]:
    """Einen Volumenkoerper in Volumenelemente umsetzen.

    Sechs Vierseit-Randflaechen mit acht Eckknoten geben ein **abgebildetes**
    Hexaedernetz, vier Dreiecke mit vier Knoten einen Tetraeder - das sind die
    beiden Faelle, in denen die Elemente der Geometrie folgen, ohne dass etwas
    genaehert wird. Jede andere Form geht an den **freien Vernetzer**
    (:mod:`statik3d.mesher3d`), der die Randflaechen in Dreiecke teilt, die
    Huelle auf Dichtheit prueft und sie mit Tetraedern fuellt.

    ``frei=False`` schaltet das ab; dann bleibt alles ohne Netz, was sich
    nicht abgebildet vernetzen laesst. ``h`` ist die angestrebte Kantenlaenge
    (0 = aus den Netzeinstellungen), ``cache`` teilt die Knoten gemeinsamer
    Randflaechen zwischen mehreren Koerpern. ``fortschritt(anteil, text)``
    wird waehrend der freien Vernetzung gerufen (Anteil 0 … 1 an diesem
    Koerper, None = nur die Zeit zaehlt); antwortet es mit False, bleibt der
    Koerper ohne Netz.
    """
    from .importers import _common as C
    from .model import _rand_aus_linien          # noqa: F401  (Doku)
    entartetes_volumen, OHNE_NETZ = _entartungspruefung()
    flaechen = [model.flaechen.get(x) for x in koerper.flaechen]
    if any(f is None for f in flaechen):
        C.warn(log, f"Volumen {koerper.name}: eine Randfläche fehlt.")
        return []
    mat = koerper.material or C.ensure_material(model, log=log)
    ringe = [f.randknoten(model) for f in flaechen]
    knoten = sorted({n for r in ringe for n in r})
    if len(flaechen) == 6 and len(knoten) == 8 and all(len(r) == 4 for r in ringe):
        from .importers.rfem6_db import _hex_order, _hex_volumen
        order = _hex_order(ringe)
        if order:
            X_hex = model.nodes[order]
            v_hex = float(_hex_volumen(X_hex))
            d_hex = float(np.linalg.norm(X_hex.max(axis=0) - X_hex.min(axis=0)))
            if entartetes_volumen(v_hex, d_hex):
                C.warn(log, f"Volumen {koerper.name}: die acht Eckknoten spannen kein "
                            f"Volumen auf ({abs(v_hex):.3e} m³) - kein Körper, kein "
                            "Netz. In der Quelldatei ist das ein Hilfsobjekt ohne "
                            "Dicke; es trägt nichts.")
                koerper.elemente = []
                koerper.kommentar = (f"{OHNE_NETZ} kein Rauminhalt (Eckknoten spannen kein "
                                     f"Volumen auf, {abs(v_hex):.3e} m³ bei "
                                     f"{d_hex * 1e3:.0f} mm Größe)")
                return []
            if v_hex < 0:
                order = order[4:] + order[:4]
            nx, ny, nz = (list(koerper.teilung) + [4, 4, 4])[:3]
            ord_ = netz_ordnung(model, ordnung)
            els = _hex_netz(model, order, max(1, nx), max(1, ny), max(1, nz), mat,
                            koerper.name, ord_, (cache or {}).setdefault("kanten", {})
                            if cache is not None else None)
            koerper.elemente = els
            C.say(log, f"Volumen {koerper.name}: {len(els)} Hexaeder"
                       + (" (quadratisch, 20 Knoten)" if ord_ >= 2 else "")
                       + f" ({nx} x {ny} x {nz})")
            return els
    if len(flaechen) == 4 and len(knoten) == 4:
        X = model.nodes[knoten]
        v = float(np.dot(np.cross(X[1] - X[0], X[2] - X[0]), X[3] - X[0]))
        d = float(np.linalg.norm(X.max(axis=0) - X.min(axis=0)))
        if entartetes_volumen(abs(v) / 6.0, d):
            # Vier Punkte in einer Ebene sind kein Koerper. In Dateien aus
            # RFEM stehen solche Null-Volumen als Hilfsobjekte; ein Element
            # daraus haette keine Steifigkeit und braechte spaeter die ganze
            # Rechnung zu Fall.
            C.warn(log, f"Volumen {koerper.name}: die vier Eckknoten liegen in einer "
                        f"Ebene (Volumen {abs(v) / 6.0:.3e} m³) - kein Körper, kein "
                        "Element. In der Quelldatei ist das ein Hilfsobjekt ohne "
                        "Dicke; es trägt nichts.")
            koerper.elemente = []
            koerper.kommentar = (f"{OHNE_NETZ} kein Rauminhalt (Eckknoten in einer Ebene, "
                                 f"{abs(v) / 6.0:.3e} m³ bei {d * 1e3:.0f} mm Größe)")
            return []
        nodes = knoten if v > 0 else [knoten[0], knoten[2], knoten[1], knoten[3]]
        els = [model.add_element("tet4", nodes, mat, group=koerper.name)]
        koerper.elemente = els
        C.say(log, f"Volumen {koerper.name}: ein Tetraeder")
        return els
    if frei:
        from .mesher3d import mesh_koerper_frei
        return mesh_koerper_frei(model, koerper, h=h, log=log, cache=cache,
                                 ordnung=ordnung, fortschritt=fortschritt)
    C.warn(log, f"Volumen {koerper.name}: {len(flaechen)} Randflächen mit "
                f"{len(knoten)} Eckknoten - abgebildet vernetzen lassen sich nur "
                "Sechsflächner (6 Vierecke, 8 Knoten) und Tetraeder (4 Dreiecke, "
                "4 Knoten). Der freie Vernetzer ist abgeschaltet - nicht vernetzt.")
    koerper.kommentar = (f"{OHNE_NETZ} {len(flaechen)} Randflächen, {len(knoten)} Eckknoten - "
                         "freier Vernetzer abgeschaltet")
    return []


def abgebildet(model: Model, koerper) -> bool:
    """Wird der Koerper abgebildet vernetzt (Sechsflaechner, einzelner
    Tetraeder)? Das ist billig und bleibt im Hauptprozess; alles andere geht
    an den freien Vernetzer und darf in einen Arbeitsprozess."""
    flaechen = [model.flaechen.get(x) for x in (koerper.flaechen or [])]
    if not flaechen or any(f is None for f in flaechen):
        return True
    ringe = [f.randknoten(model) for f in flaechen]
    knoten = {n for r in ringe for n in r}
    if len(flaechen) == 6 and len(knoten) == 8 and all(len(r) == 4 for r in ringe):
        return True
    return len(flaechen) == 4 and len(knoten) == 4


# --------------------------------------------------------------------------
# Mehrere Volumen: parallel in Arbeitsprozessen
# --------------------------------------------------------------------------
_WORKER_MODEL = None


def _koerper_arbeiter_init(model: Model) -> None:
    """Jeder Arbeitsprozess bekommt das Modell einmal - die Geometrie genuegt."""
    global _WORKER_MODEL
    _WORKER_MODEL = model


def _koerper_arbeit(name: str, h: float) -> dict:
    """Die Rechenarbeit eines Koerpers im Arbeitsprozess (siehe
    :func:`statik3d.mesher3d.koerper_vorbereiten`)."""
    from . import mesher3d as M3
    k = _WORKER_MODEL.koerper[name]
    return M3.koerper_vorbereiten(_WORKER_MODEL, k, h=float(h or 0.0))


def prozesse_fuer_vernetzung() -> int:
    """Wie viele Arbeitsprozesse die Vernetzung nimmt: alle Kerne bis auf
    einen - der bleibt der Oberflaeche -, gedeckelt durch die Einstellung
    „Prozesse" (Berechnung → Einstellungen)."""
    from . import parallel as par
    return max(1, min(int(par.settings().workers), par.cpu_count() - 1))


def koerper_vernetzen(model: Model, koerper, hs: dict = None, log: list = None,
                      cache: dict = None, workers: int = None, fortschritt=None,
                      gewicht: dict = None, ordnung: int = 0) -> dict:
    """Mehrere Volumenkoerper vernetzen - die freie Vernetzung parallel.

    Die Rechenarbeit je Koerper (:func:`mesher3d.koerper_vorbereiten`) laeuft
    in ``workers`` Arbeitsprozessen (Vorgabe: alle Kerne bis auf einen, siehe
    :func:`prozesse_fuer_vernetzung`); der Einbau ins Modell
    (:func:`mesher3d.koerper_einbauen`) geschieht im aufrufenden Prozess, in
    der Reihenfolge des Fertigwerdens. Abgebildete Koerper (Sechsflaechner,
    Tetraeder) werden gleich hier vernetzt. Mit einem Prozess oder einem
    einzigen freien Koerper laeuft alles seriell - dann mit Fortschritt
    **innerhalb** des Koerpers.

    ``hs`` ist {Name: Kantenlaenge} aus der Netzdichte, ``gewicht`` {Name:
    geschaetzte Elementzahl} fuer die Reihenfolge (grosse zuerst) und den
    Balken. ``fortschritt(anteil, text)`` bekommt den Anteil 0 … 1 an der
    ganzen Volumenarbeit und beendet mit False alles - laufende Prozesse
    werden abgebrochen, das bisher Eingebaute bleibt.

    Rueckgabe {"elemente": Zahl, "fertig": Koerper mit Netz, "abgebrochen":
    bool, "prozesse": benutzte Prozesse}.
    """
    import time
    from . import mesher3d as M3
    from .importers import _common as C
    hs = hs or {}
    gewicht = gewicht or {}
    cache = {} if cache is None else cache
    koerper = list(koerper)
    if ordnung <= 0:
        ordnung = int(getattr(getattr(model, "netz", None), "ordnung", 1) or 1)
    aus = {"elemente": 0, "fertig": 0, "abgebrochen": False, "prozesse": 1}
    if not koerper:
        return aus
    # Balken: nach geschaetzter Elementzahl gewichtet, nicht nach Stueckzahl -
    # ein Lagerbock mit 90 000 Tetraedern und eine Buchse mit 150 sind nicht
    # gleich viel Arbeit.
    w_alle = {k.name: max(1.0, float(gewicht.get(k.name, 1.0) or 1.0)) for k in koerper}
    summe = sum(w_alle.values())
    erledigt = 0.0

    def melden(text: str, anteil_akt: float = 0.0, w_akt: float = 0.0) -> bool:
        if fortschritt is None:
            return True
        return fortschritt((erledigt + anteil_akt * w_akt) / summe, text) is not False

    def einbauen(k, els_oder_aus):
        nonlocal erledigt
        if isinstance(els_oder_aus, dict):
            els = M3.koerper_einbauen(model, k, els_oder_aus, log, cache, ordnung)
        else:
            els = els_oder_aus
        aus["elemente"] += len(els)
        aus["fertig"] += 1 if els else 0
        erledigt += w_alle[k.name]

    def fertig_melden():
        if fortschritt is not None and not aus["abgebrochen"]:
            fortschritt(1.0, f"{aus['fertig']} von {len(koerper)} Volumen vernetzt")

    frei = [k for k in koerper if not abgebildet(model, k)]
    # 1) Abgebildete Koerper gleich hier - das kostet nichts
    for k in koerper:
        if k in frei:
            continue
        if not melden(f"{k.name} abgebildet"):
            aus["abgebrochen"] = True
            return aus
        einbauen(k, mesh_koerper(model, k, log, cache=cache,
                                 h=float(hs.get(k.name, 0.0) or 0.0), ordnung=ordnung))
    if not frei:
        fertig_melden()
        return aus
    # Grosse zuerst: so wartet am Ende nicht ein Prozess allein auf den Lagerbock
    frei.sort(key=lambda k: -w_alle[k.name])
    w = prozesse_fuer_vernetzung() if workers is None else int(workers)
    w = max(1, min(w, len(frei)))
    if w <= 1:
        for k in frei:
            def ruf(anteil, text, _k=k):
                return melden(f"{_k.name}: {text}" if text else _k.name,
                              anteil or 0.0, w_alle[_k.name])
            if not melden(f"{k.name}: Randhülle bilden", 0.0, w_alle[k.name]):
                aus["abgebrochen"] = True
                break
            els = mesh_koerper(model, k, log, cache=cache,
                               h=float(hs.get(k.name, 0.0) or 0.0), ordnung=ordnung,
                               fortschritt=ruf)
            einbauen(k, els)
            if not els and log and any("abgebrochen" in z for z in log[-3:]):
                aus["abgebrochen"] = True
                break
        fertig_melden()
        return aus
    # 2) Parallel: die Rechenarbeit in Arbeitsprozessen, der Einbau hier
    from . import parallel as par
    aus["prozesse"] = w
    try:
        ctx = par._context()
        pool = ctx.Pool(processes=w, initializer=_koerper_arbeiter_init, initargs=(model,))
    except Exception as ex:               # noqa: BLE001 - kein Prozess-Pool: seriell
        C.say(log, f"Arbeitsprozesse nicht verfügbar ({ex}) - die Volumen werden nacheinander vernetzt.")
        aus = _seriell_nach(model, frei, hs, log, cache, fortschritt, gewicht, ordnung,
                            aus, w_alle, summe, erledigt)
        fertig_melden()
        return aus
    namen = {k.name: k for k in frei}
    offen = {}
    try:
        for k in frei:
            offen[k.name] = pool.apply_async(_koerper_arbeit,
                                             (k.name, float(hs.get(k.name, 0.0) or 0.0)))
        t_tick = 0.0
        while offen:
            fertige = [name for name, r in offen.items() if r.ready()]
            for name in fertige:
                r = offen.pop(name)
                try:
                    erg = r.get()
                except Exception as ex:       # noqa: BLE001
                    erg = {"fehler": f"Fehler im Arbeitsprozess: {ex}", "log": []}
                einbauen(namen[name], erg)
            laufend = [n for n in offen][:w]
            if not melden(f"{aus['fertig']} von {len(koerper)} Volumen fertig, "
                          f"{len(offen)} in Arbeit auf {w} Prozessen"
                          + (" (" + ", ".join(laufend) + (" …" if len(offen) > w else "") + ")"
                             if laufend else "")):
                aus["abgebrochen"] = True
                break
            if offen:
                time.sleep(0.1)
                t_tick += 0.1
        if aus["abgebrochen"]:
            pool.terminate()
            C.say(log, f"Vernetzen abgebrochen: {len(offen)} Volumen bleiben ohne Netz "
                       "(die Arbeitsprozesse wurden beendet).")
        else:
            pool.close()
        pool.join()
    except BaseException:
        pool.terminate()
        pool.join()
        raise
    fertig_melden()
    return aus


def _seriell_nach(model, frei, hs, log, cache, fortschritt, gewicht, ordnung,
                  aus, w_alle, summe, erledigt):
    """Rueckfall ohne Prozess-Pool: die freien Koerper nacheinander."""
    def melden(text, anteil_akt=0.0, w_akt=0.0):
        if fortschritt is None:
            return True
        return fortschritt((erledigt + anteil_akt * w_akt) / summe, text) is not False
    for k in frei:
        def ruf(anteil, text, _k=k):
            return melden(f"{_k.name}: {text}" if text else _k.name, anteil or 0.0, w_alle[_k.name])
        els = mesh_koerper(model, k, log, cache=cache, h=float(hs.get(k.name, 0.0) or 0.0),
                           ordnung=ordnung, fortschritt=ruf)
        aus["elemente"] += len(els)
        aus["fertig"] += 1 if els else 0
        erledigt += w_alle[k.name]
        if not els and log and any("abgebrochen" in z for z in log[-3:]):
            aus["abgebrochen"] = True
            break
    aus["prozesse"] = 1
    return aus


#: Kanten des Hexaeders in der Knotenreihenfolge von hex20 (unten, oben, senkrecht)
HEX_KANTEN = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
              (0, 4), (1, 5), (2, 6), (3, 7))


def _hex_netz(model: Model, ecken: list[int], nx: int, ny: int, nz: int,
              mat: str, gruppe: str, ordnung: int = 1, kanten: dict = None) -> list[int]:
    """Abgebildetes Hexaedernetz in einem Sechsflaechner (trilineare Abbildung);
    ``ordnung`` 2 gibt Hexaeder mit 20 Knoten (Kantenmitten dazu)."""
    P = model.nodes[ecken]
    ids = np.zeros((nx + 1, ny + 1, nz + 1), dtype=int)
    ecknr = {(0, 0, 0): 0, (1, 0, 0): 1, (1, 1, 0): 2, (0, 1, 0): 3,
             (0, 0, 1): 4, (1, 0, 1): 5, (1, 1, 1): 6, (0, 1, 1): 7}
    for i in range(nx + 1):
        for j in range(ny + 1):
            for k in range(nz + 1):
                r, s, t = i / nx, j / ny, k / nz
                schluessel = (int(round(r)), int(round(s)), int(round(t)))
                if (r in (0.0, 1.0) and s in (0.0, 1.0) and t in (0.0, 1.0)):
                    ids[i, j, k] = ecken[ecknr[schluessel]]
                    continue
                N = np.array([(1 - r) * (1 - s) * (1 - t), r * (1 - s) * (1 - t),
                              r * s * (1 - t), (1 - r) * s * (1 - t),
                              (1 - r) * (1 - s) * t, r * (1 - s) * t,
                              r * s * t, (1 - r) * s * t])
                ids[i, j, k] = model.add_node(*(N @ P))
    els = []
    kanten = {} if kanten is None else kanten
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                c = [int(ids[i, j, k]), int(ids[i + 1, j, k]), int(ids[i + 1, j + 1, k]),
                     int(ids[i, j + 1, k]), int(ids[i, j, k + 1]), int(ids[i + 1, j, k + 1]),
                     int(ids[i + 1, j + 1, k + 1]), int(ids[i, j + 1, k + 1])]
                if ordnung >= 2:
                    c = c + [kantenknoten(model, c[a], c[b], kanten) for a, b in HEX_KANTEN]
                    els.append(model.add_element("hex20", c, mat, group=gruppe))
                else:
                    els.append(model.add_element("hex8", c, mat, group=gruppe))
    return els
