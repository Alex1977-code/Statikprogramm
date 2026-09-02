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
