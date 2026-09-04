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


def mesh_flaeche(model: Model, flaeche, log: list = None) -> list[int]:
    """Eine Flaeche in Schalenelemente umsetzen.

    Vier Randabschnitte geben ein abgebildetes Vierecknetz mit der in
    ``flaeche.teilung`` genannten Elementzahl; drei Abschnitte ein Dreiecknetz.
    Jede andere Randform wird benannt und nicht vernetzt.
    """
    from .importers import _common as C
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
                els.append(model.add_element(
                    "shell4", [int(ids[i, j]), int(ids[i + 1, j]),
                               int(ids[i + 1, j + 1]), int(ids[i, j + 1])],
                    mat, prop, group=flaeche.name))
        flaeche.elemente = els
        C.say(log, f"Fläche {flaeche.name}: {len(els)} Viereckelemente ({nu} x {nv})")
        return els
    if len(ring) == 3:
        els = [model.add_element("shell3", ring, mat, prop, group=flaeche.name)]
        flaeche.elemente = els
        C.say(log, f"Fläche {flaeche.name}: ein Dreieckelement")
        return els
    C.warn(log, f"Fläche {flaeche.name}: Rand aus {len(flaeche.linien)} Linien und "
                f"{len(ring)} Knoten - für ein abgebildetes Netz sind vier "
                "Randabschnitte nötig. Nicht vernetzt.")
    return []


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


def mesh_koerper(model: Model, koerper, log: list = None, frei: bool = True,
                 h: float = 0.0, cache: dict = None, ordnung: int = 0) -> list[int]:
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
    Randflaechen zwischen mehreren Koerpern.
    """
    from .importers import _common as C
    from .model import _rand_aus_linien          # noqa: F401  (Doku)
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
            if _hex_volumen(model.nodes[order]) < 0:
                order = order[4:] + order[:4]
            nx, ny, nz = (list(koerper.teilung) + [4, 4, 4])[:3]
            els = _hex_netz(model, order, max(1, nx), max(1, ny), max(1, nz), mat,
                            koerper.name)
            koerper.elemente = els
            C.say(log, f"Volumen {koerper.name}: {len(els)} Hexaeder "
                       f"({nx} x {ny} x {nz})")
            return els
    if len(flaechen) == 4 and len(knoten) == 4:
        X = model.nodes[knoten]
        v = float(np.dot(np.cross(X[1] - X[0], X[2] - X[0]), X[3] - X[0]))
        nodes = knoten if v > 0 else [knoten[0], knoten[2], knoten[1], knoten[3]]
        els = [model.add_element("tet4", nodes, mat, group=koerper.name)]
        koerper.elemente = els
        C.say(log, f"Volumen {koerper.name}: ein Tetraeder")
        return els
    if frei:
        from .mesher3d import mesh_koerper_frei
        return mesh_koerper_frei(model, koerper, h=h, log=log, cache=cache,
                                 ordnung=ordnung)
    C.warn(log, f"Volumen {koerper.name}: {len(flaechen)} Randflächen mit "
                f"{len(knoten)} Eckknoten - abgebildet vernetzen lassen sich nur "
                "Sechsflächner (6 Vierecke, 8 Knoten) und Tetraeder (4 Dreiecke, "
                "4 Knoten). Der freie Vernetzer ist abgeschaltet - nicht vernetzt.")
    return []


def _hex_netz(model: Model, ecken: list[int], nx: int, ny: int, nz: int,
              mat: str, gruppe: str) -> list[int]:
    """Abgebildetes Hexaedernetz in einem Sechsflaechner (trilineare Abbildung)."""
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
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                c = [ids[i, j, k], ids[i + 1, j, k], ids[i + 1, j + 1, k],
                     ids[i, j + 1, k], ids[i, j, k + 1], ids[i + 1, j, k + 1],
                     ids[i + 1, j + 1, k + 1], ids[i, j + 1, k + 1]]
                els.append(model.add_element("hex8", [int(x) for x in c], mat,
                                             group=gruppe))
    return els
