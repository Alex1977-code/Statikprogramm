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
    typ: "hex8" (ein Hexaeder je Zelle) oder "tet4" (fuenf Tetraeder je
    Zelle); jeder andere Wert ergibt einen ValueError.
    Rueckgabe: Knoten-Index-Array der Form (nx+1, ny+1, nz+1)."""
    # Pruefung vor dem ersten Knoten, damit ein abgewiesener Aufruf das Modell
    # nicht halb fuellt. Bis 23.09.2026 fiel jeder typ ausser "hex8" still in
    # die Fuenferzerlegung; die Web-Operation box reicht typ ungeprueft durch,
    # gemessen am Stand ec6448c ergaben "hex20", "tet10", "HEX8" und "quatsch"
    # bei 1x1x1 Zellen je 5 tet4 mit der Meldung „Quader erzeugt“.
    if typ not in ("hex8", "tet4"):
        raise ValueError(f"Elementtyp '{typ}' für den Quader nicht möglich: "
                         "nur hex8 oder tet4")
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
                    # Fuenf Tetraeder je Zelle: vier Eck-Tetraeder und eines in
                    # der Mitte. Die Diagonalen der sechs Zellseiten laufen
                    # alle durch die vier Ecken des Mitteltetraeders - in der
                    # Grundform durch 1,3,4,6. Die Nachbarzelle sieht dieselbe
                    # Seite von der anderen Seite, dort liefe die Diagonale
                    # bei gleicher Zerlegung durch die anderen beiden Ecken.
                    # Deshalb wechselt die Zerlegung schachbrettartig mit
                    # (i+j+k) % 2: die gespiegelte Form hat die Mitte 0,2,5,7
                    # und trifft damit die Diagonalen der Nachbarn. Ohne den
                    # Wechsel blieb jede innere Zellseite als Riss aus zwei
                    # freien Dreiecken stehen (gemessen 22.09.2026: 2x2x2
                    # Zellen 96 freie Dreiecke statt 48, 3x3x3 324 statt 108).
                    # Die gespiegelte Form ist die x-Spiegelung der Grundform
                    # (0<->1, 2<->3, 4<->5, 6<->7) mit zwei getauschten Knoten,
                    # damit jedes Tetraeder positiv orientiert bleibt.
                    if (i + j + k) % 2 == 0:
                        tets = [(0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6),
                                (1, 4, 5, 6), (3, 4, 6, 7)]
                    else:
                        tets = [(1, 0, 5, 2), (0, 3, 7, 2), (0, 2, 7, 5),
                                (0, 5, 7, 4), (2, 5, 6, 7)]
                    for tet in tets:
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
def doppelte_knoten(model: Model, tol: float = 1e-6) -> int:
    """Wie viele Knoten :func:`merge_nodes` entfernen wuerde - ohne etwas zu
    aendern (gleicher Schluessel). Fuer Befehle, die vor der Aenderung einen
    Rueckgaengig-Schritt anlegen und bei „nichts zu tun“ keinen hinterlassen
    sollen (Fehlerliste 06.10.2026, F32)."""
    from .importers import _common as C
    return C.count_duplicate_nodes(model, tol)


def merge_nodes(model: Model, tol: float = 1e-6) -> int:
    """Doppelte Knoten zusammenfuehren (z.B. nach mehrfachem Import).

    Jeder Verweis auf einen Knoten folgt: Elemente, Linien, Lager aller Arten,
    Lasten, Kontakt, Kopplungen, starre Koerper, Flaechenecken, Layer … - dieselben
    Verweisarten, die das Loeschen eines Knotens kennt
    (:meth:`Model._knotenverweise_abbilden`). Die Arbeit tut
    :func:`importers._common.merge_duplicate_nodes`, das jeden Import nach
    dem Einlesen zusammenfuehrt; ein gleich gewordener Knoten steht dort in
    einer Linie, einem Lager oder einer Gruppe einmal (Einflussflaechen
    summieren sich). Bis zum 07.10.2026 hatte dieses Modul eine eigene,
    kuerzere Fassung, die nur Elemente, Lager, Knotenlasten und Kontakt nachzog
    (N11): Linien, Kopplungen, starre Koerper und der Rest zeigten danach auf
    einen anderen Knoten - oder hinter das Ende der Knotenliste.

    Zusaetzlich fuehrt ein Kontaktpaar gleich gewordene Slave-Knoten nur einmal
    (sortiert), wie es dieses Modul immer tat."""
    from .importers import _common as C
    n_removed = C.merge_duplicate_nodes(model, tol)
    if n_removed:
        for cp in model.contact_pairs:
            cp.slave_nodes = sorted({int(n) for n in cp.slave_nodes})
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


#: Abstand, bis zu dem ein neuer Randknoten als deckungsgleich mit einem
#: Stuetzknoten der Kante gilt - bezogen auf die Laenge des Randabschnitts.
#: Am Bogen durch drei Punkte liegen beide 2,2e-16 m auseinander; 1e-6 der
#: Laenge (3 um an 3 m) verschiebt einen Netzknoten nirgends merklich.
STUETZKNOTEN_TOL = 1e-6


def _knoten_bei(model: Model, x, stuetz: list, tol: float) -> int:
    """Der Stuetzknoten aus ``stuetz``, der bei x liegt (Abstand <= tol) -
    sonst ein neuer Knoten bei x."""
    x = np.asarray(x, float)
    if stuetz:
        d = np.linalg.norm(model.nodes[stuetz] - x, axis=1)
        j = int(np.argmin(d))
        if d[j] <= tol:
            return int(stuetz[j])
    return int(model.add_node(*x))


def _verdichten(model: Model, kante: list[int], n: int, linie: str = "") -> list[int]:
    """Einen Randabschnitt auf n Elemente verfeinern (neue Zwischenknoten).

    Ist ``linie`` eine krumme Linie, folgen die neuen Knoten ihrer Kurve;
    sonst den Sehnen zwischen den vorhandenen Knoten.

    Faellt ein neuer Knoten auf einen Stuetzknoten der Kante - den mittleren
    Knoten eines Bogens durch drei Punkte, den Knick einer Polylinie -, ist
    er dieser Stuetzknoten. Bis zum 07.10.2026 entstand daneben ein
    deckungsgleicher neuer: der Stuetzknoten hing an keinem Element, lag
    aber auf der Linie und bekam von einer Linienlast seinen Anteil, der
    verloren ging (Viertelkreisring, sechs Teilungen: 261,8 von 3 141,5 N;
    Nachtrag N09).
    """
    P = model.nodes
    stuetz = [int(k) for k in kante[1:-1]]
    pts = _kurvenpunkte(model, linie, n)
    if pts is not None:
        # Die Kurve kann gegen die Knotenfolge laufen - am naeheren Ende anfangen
        if (np.linalg.norm(pts[0] - P[kante[0]])
                > np.linalg.norm(pts[-1] - P[kante[0]])):
            pts = pts[::-1]
        tol = STUETZKNOTEN_TOL * float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
        return ([int(kante[0])]
                + [_knoten_bei(model, x, stuetz, tol) for x in pts[1:-1]]
                + [int(kante[-1])])
    pts = P[kante]
    lang = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    if lang[-1] <= 0:
        return list(kante)
    tol = STUETZKNOTEN_TOL * float(lang[-1])
    ziel = np.linspace(0.0, lang[-1], n + 1)
    out = [int(kante[0])]
    for sl in ziel[1:-1]:
        k = int(np.searchsorted(lang, sl, side="right") - 1)
        k = min(max(k, 0), len(kante) - 2)
        t = (sl - lang[k]) / (lang[k + 1] - lang[k])
        out.append(_knoten_bei(model, pts[k] + t * (pts[k + 1] - pts[k]), stuetz, tol))
    out.append(int(kante[-1]))
    return out


#: Abtastung einer krummen Linie ohne geschlossene Form (Ellipse, Parabel,
#: Spline), auf der die Kantenmitte gesucht wird
KURVE_FEIN = 1024


def _kurvenmitte(model: Model, linie: str):
    """Funktion (Ecke a, Ecke b) -> Punkt der **wahren** Kurve der Linie auf
    halber Bogenlaenge zwischen a und b - oder None fuer eine Strecke.

    Bogen und Kreis rechnen geschlossen ueber den Winkel; die anderen Arten
    ueber eine feine Abtastung (KURVE_FEIN Abschnitte), auf der die Ecken
    ihre Lage bekommen und die Mitte dazwischen liegt."""
    ln = (getattr(model, "lines", {}) or {}).get(linie)
    if ln is None or (ln.typ or "polyline") == "polyline":
        return None
    try:
        kurve = ln.kurve(model)
    except Exception:            # noqa: BLE001 - wie _kurvenpunkte: dann die Sehne
        return None
    from .geometry import Bogen
    if isinstance(kurve, Bogen):
        m0 = np.asarray(kurve.mitte, float)
        e1, e2 = np.asarray(kurve.e1, float), np.asarray(kurve.e2, float)
        r, w = float(kurve.radius), float(kurve.winkel)
        voll = w >= 2 * np.pi - 1e-9

        def winkel(p):
            d = np.asarray(p, float) - m0
            t = float(np.arctan2(d @ e2, d @ e1)) % (2 * np.pi)
            # knapp vor dem Anfang (Rundung) ist der Anfang, nicht das Ende
            return t - 2 * np.pi if (not voll and t > w + 0.5 * (2 * np.pi - w)) else t

        def mitte(a, b):
            ta, tb = winkel(a), winkel(b)
            if voll and abs(tb - ta) > np.pi:       # ueber den Anfang des Kreises hinweg
                if ta < tb:
                    ta += 2 * np.pi
                else:
                    tb += 2 * np.pi
            t = 0.5 * (ta + tb)
            return m0 + r * (np.cos(t) * e1 + np.sin(t) * e2)
        return mitte
    try:
        X = np.asarray(kurve.punkte(KURVE_FEIN), float)
    except Exception:            # noqa: BLE001
        return None
    seg = np.diff(X, axis=0)
    L = np.linalg.norm(seg, axis=1)
    if len(X) < 2 or L.sum() <= 0:
        return None
    s0 = np.concatenate([[0.0], np.cumsum(L)])
    L2 = np.maximum(L * L, 1e-300)

    def lage(p):
        t = np.clip(((np.asarray(p, float) - X[:-1]) * seg).sum(axis=1) / L2, 0.0, 1.0)
        d = np.linalg.norm(X[:-1] + t[:, None] * seg - p, axis=1)
        k = int(np.argmin(d))
        return float(s0[k] + t[k] * L[k])

    def mitte(a, b):
        s = 0.5 * (lage(a) + lage(b))
        k = min(max(int(np.searchsorted(s0, s, side="right") - 1), 0), len(L) - 1)
        t = (s - s0[k]) / L[k] if L[k] > 0 else 0.0
        return X[k] + t * seg[k]
    return mitte


def _randmitten(model: Model, kette: list[int], kante: list[int], linie: str,
                kanten: dict) -> int:
    """Die Kantenmitten eines Randabschnitts vorab in ``kanten`` legen, damit
    :func:`kantenknoten` sie nimmt - fuer quadratische Elemente.

    Auf einer krummen Linie liegt die Mitte auf der Kurve, auf halber
    Bogenlaenge zwischen den Ecken. Bis zum 07.10.2026 setzte
    :func:`kantenknoten` sie auf die Sehnenmitte, am Viertelkreisring (R =
    2 m, sechs Teilungen) 17,1 mm neben den Bogen; Model.knoten_auf_linie und
    supports.lager_auf_netz fanden sie nicht, die Linienlast ging nur an die
    Ecken, das Linienlager hielt die Mitten nicht (Nachtrag N08). Faellt eine
    Mitte auf einen Stuetzknoten der Kante (``kante[1:-1]``, ungerade Teilung
    eines Bogens durch drei Punkte), ist sie dieser Knoten (N09). Eine
    gerade Kante ohne Stuetzknoten bleibt :func:`kantenknoten` ueberlassen.
    Rueckgabe: Zahl der gelegten Mitten."""
    mitte = _kurvenmitte(model, linie) if linie else None
    stuetz = [int(k) for k in kante[1:-1]]
    if mitte is None and not stuetz:
        return 0
    P = model.nodes
    tol = STUETZKNOTEN_TOL * float(np.linalg.norm(np.diff(P[[int(k) for k in kette]], axis=0),
                                                  axis=1).sum())
    n = 0
    for a, b in zip(kette[:-1], kette[1:]):
        a, b = int(a), int(b)
        key = (min(a, b), max(a, b))
        if key in kanten:
            continue
        P = model.nodes
        x = mitte(P[a], P[b]) if mitte is not None else 0.5 * (P[a] + P[b])
        kanten[key] = _knoten_bei(model, x, stuetz, tol)
        n += 1
    return n


def kantenknoten(model: Model, a: int, b: int, cache: dict = None) -> int:
    """Der Knoten in der Mitte der Kante a-b - je Kante nur einmal.

    Quadratische Elemente teilen ihre Kantenmitten mit dem Nachbarn; ohne
    ``cache`` entstuenden doppelte Knoten und das Netz fiele auseinander.
    Die Mitten der Randkanten einer Flaeche liegen schon im ``cache``, wenn
    die Randlinie krumm ist oder Stuetzknoten hat (:func:`_randmitten`);
    hier entsteht nur die Sehnenmitte.
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


def koerper_ordnung(model: Model, koerper, ordnung: int = 0) -> int:
    """Die Elementordnung **dieses** Koerpers: ``Volumenkoerper.ordnung``
    (1 oder 2) geht vor, sonst die des Aufrufs bzw. der Netzeinstellungen.

    Anweisung V1 (Loeser-Sitzung, 22.09.2026): tet10 dort, wo nachgewiesen
    wird, tet4 im Rest; welche Koerper das sind, sagt ``elementwahl`` oder der
    Anwender ueber das Feld am Koerper (Statik3D-Sitzung, 23.09.2026).
    """
    eigene = getattr(koerper, "ordnung", None)
    if eigene in (1, 2):
        return int(eigene)
    return netz_ordnung(model, ordnung)


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
        if ordnung >= 2:
            # Kantenmitten auf krummen Randlinien auf die Kurve (N08)
            for kette, (kante, linie) in zip((unten, rechts, oben, links), seiten):
                _randmitten(model, kette, kante, linie, kanten)
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


#: Linienarten, die eine Strecke sind. Alles andere (Bogen, Kreis, Ellipse,
#: Spline, Parabel) kruemmt sich und passt nicht in ein abgebildetes Netz.
GERADE_LINIEN = ("", "polyline", "line", "strecke", "gerade")


def _nur_gerade(model, flaechen) -> bool:
    """Sind alle Randlinien dieser Flaechen Strecken?"""
    for f in flaechen:
        raender = list(f.linien or []) + [x for loch in (f.oeffnungen or []) for x in loch]
        for nm in raender:
            ln = (model.lines or {}).get(nm)
            if ln is None:
                return False
            if str(getattr(ln, "typ", "polyline") or "polyline").lower() not in GERADE_LINIEN:
                return False
    return True


def _dreiflaechner(ringe, flaechen, model) -> bool:
    """Vier Randflaechen, die wirklich vier Dreiecke sind.

    ``len(knoten) == 4`` allein reicht nicht: ein **Zylinder** aus zwei
    Mantelflaechen (je 4 Knoten) und zwei Kreisen hat auch vier Randflaechen
    und vier Eckknoten - die Kreise liefern gar keinen Ring, weil sich ein aus
    zwei Boegen geschlossener Kreis nicht als Kette aus vier Strecken lesen
    laesst. Ohne diese Pruefung wurde der Zylinder als flacher Tetraeder
    gelesen, dessen vier Ecken auf zwei Kreisen liegen.
    """
    return (len(flaechen) == 4 and all(len(r) == 3 for r in ringe)
            and _nur_gerade(model, flaechen))


def _entartungspruefung():
    """Die gemeinsame Grenze - eine Stelle, an der „entartet“ definiert ist."""
    from .diagnose import entartetes_volumen
    from .model import OHNE_NETZ
    return entartetes_volumen, OHNE_NETZ


def _entartet(model, koerper, log, frei, h, cache, ordnung, fortschritt,
              grund: str, ohne_netz: str, karten: tuple = None) -> list:
    """Das abgebildete Muster hat gegriffen, der Koerper hat aber kein Volumen.

    Das heisst nicht, dass er keines **hat** - es heisst, dass das Muster
    nicht passt. Ein Zylinder aus zwei Mantelflaechen und zwei Kreisen sieht
    an den Eckknoten aus wie ein flacher Tetraeder. Darum uebernimmt hier der
    freie Vernetzer; erst wenn auch der nichts findet, bleibt der Koerper
    ohne Netz.
    """
    from .importers import _common as C
    if frei:
        C.say(log, f"Volumen {koerper.name}: {grund} - das abgebildete Muster passt "
                   "nicht, der freie Vernetzer übernimmt.")
        from .mesher3d import mesh_koerper_frei
        return mesh_koerper_frei(model, koerper, h=h, log=log, cache=cache,
                                 ordnung=ordnung, fortschritt=fortschritt, karten=karten)
    C.warn(log, f"Volumen {koerper.name}: {grund} - kein Körper, kein Element "
                "(freier Vernetzer abgeschaltet).")
    koerper.elemente = []
    koerper.kommentar = f"{ohne_netz} kein Rauminhalt ({grund})"
    koerper.netzgrund = "kein_volumen"
    return []


def _gerade_kanten(model: Model, koerper, order: list) -> bool:
    """Sind alle zwoelf Kanten des Sechsflaechners **gerade**? Nur dann bildet
    die trilineare Abbildung (:func:`_hex_netz`) den Koerper wirklich ab."""
    kanten = quader_kanten(model, koerper, order)
    if len(kanten) < 24:                      # je Kante zwei Richtungen
        return False
    for name in set(kanten.values()):
        ln = model.lines.get(name)
        if ln is None or (ln.typ or "polyline") != "polyline" or len(ln.nodes) != 2:
            return False
    return True


def mesh_koerper(model: Model, koerper, log: list = None, frei: bool = True,
                 h: float = 0.0, cache: dict = None, ordnung: int = 0,
                 fortschritt=None, karten: tuple = None) -> list[int]:
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
    Koerper ohne Netz. ``karten`` sind die modellweiten Netzkarten aus
    :func:`netzkarten`; ohne sie bildet der freie Vernetzer sie selbst - je
    Koerper, am Drehlager 48 x 1,5 s.
    """
    # Die Ordnung dieses Koerpers - ein Koerper mit Ordnung 2 bekommt tet10 und
    # geht darum an den freien Vernetzer, auch wenn er sonst abgebildet oder
    # gesweept wuerde: Sechsflaechner zweiter Ordnung neben tet4-Nachbarn
    # koppelt heute niemand (Anweisung V1, 22./23.09.2026).
    ordnung = koerper_ordnung(model, koerper, ordnung)
    # Der Grund einer gescheiterten Randtreue-Messung gilt nur fuer das Netz,
    # an dem sie scheiterte (F35); jeder Weg unten misst neu oder gar nicht
    koerper.randtreue_fehler = ""
    if ordnung >= 2 and frei and getattr(koerper, "ordnung", None) == 2:
        from .mesher3d import mesh_koerper_frei
        return mesh_koerper_frei(model, koerper, h=h, log=log, cache=cache,
                                 ordnung=ordnung, fortschritt=fortschritt, karten=karten)
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
        if order and not _gerade_kanten(model, koerper, order):
            # Sechs Vierecke mit acht Ecken - aber mit **krummen** Kanten. Der
            # abgebildete Pfad bildet trilinear zwischen den acht Ecken ab, und
            # das schneidet jede Rundung ab: ein Rohrbogen von 90 Grad
            # (Rechteckprofil, um die z-Achse gedreht) kam so auf **63,7 %**
            # seines Rauminhalts - ohne eine einzige Meldung, weil Huelle und
            # Guete tadellos aussehen (22.09.2026). Solche Koerper gehoeren dem
            # Sweep: er dreht die Lagen mit.
            C.say(log, f"Volumen {koerper.name}: sechs Vierecke mit acht Ecken, aber krumme Kanten - "
                       "nicht abgebildet (der trilineare Quader schnitte die Rundung ab).")
            order = None
        if order:
            X_hex = model.nodes[order]
            v_hex = float(_hex_volumen(X_hex))
            d_hex = float(np.linalg.norm(X_hex.max(axis=0) - X_hex.min(axis=0)))
            if entartetes_volumen(v_hex, d_hex):
                return _entartet(model, koerper, log, frei, h, cache, ordnung, fortschritt,
                                 f"die acht Eckknoten spannen kein Volumen auf "
                                 f"({abs(v_hex):.3e} m³ bei {d_hex * 1e3:.0f} mm Größe)",
                                 OHNE_NETZ, karten=karten)
            if v_hex < 0:
                order = order[4:] + order[:4]
            nx, ny, nz = (list(koerper.teilung) + [4, 4, 4])[:3]
            # Eine Linienvorgabe (sweep.lagenvorgabe: Kanten, die Nachbarn
            # gehoeren) geht vor der eigenen Teilung - je Richtung dieselbe.
            vorgabe = getattr(model, "linienvorgabe", None) or {}
            richtungen = quader_richtungen(quader_kanten(model, koerper, order))
            teil = [nx, ny, nz]
            for d in range(3):
                fest = [int(vorgabe[x]) for x in richtungen[d] if x in vorgabe]
                if fest:
                    teil[d] = max(fest)
            nx, ny, nz = teil
            ord_ = netz_ordnung(model, ordnung)
            # Die Kantenmitten (Ordnung 2) liegen im Cache unter "kanten", damit
            # der Nachbar an einer gemeinsamen Flaeche dieselben Knoten trifft.
            # Bis zum 25.09.2026 stand hier ``(cache or {})`` - ein noch leerer
            # Cache ist falsch-wertig, der erste Koerper schrieb in ein
            # Wegwerf-Dict, und jede Kantenmitte der gemeinsamen Flaeche gab es
            # zweimal (zwei Quader 4 x 4 x 4: 40 doppelte Knoten, Kragarm aus
            # zwei Koerpern +610 N/mm2 neben der Balkenloesung; test_sweep).
            kanten = cache.setdefault("kanten", {}) if cache is not None else None
            els = _hex_netz(model, order, max(1, nx), max(1, ny), max(1, nz), mat,
                            koerper.name, ord_, kanten, koerper=koerper, cache=cache)
            koerper.elemente = els
            koerper.kommentar = f"{len(els)} Hexaeder (abgebildet, {nx} x {ny} x {nz})"
            koerper.randtreue = 1.0
            koerper.netzgrund = ""
            koerper.netzkanten = []
            C.say(log, f"Volumen {koerper.name}: {len(els)} Hexaeder"
                       + (" (quadratisch, 20 Knoten)" if ord_ >= 2 else "")
                       + f" ({nx} x {ny} x {nz})")
            return els
    if len(knoten) == 4 and _dreiflaechner(ringe, flaechen, model):
        X = model.nodes[knoten]
        v = float(np.dot(np.cross(X[1] - X[0], X[2] - X[0]), X[3] - X[0]))
        d = float(np.linalg.norm(X.max(axis=0) - X.min(axis=0)))
        if entartetes_volumen(abs(v) / 6.0, d):
            return _entartet(model, koerper, log, frei, h, cache, ordnung, fortschritt,
                             f"die vier Eckknoten liegen in einer Ebene "
                             f"({abs(v) / 6.0:.3e} m³ bei {d * 1e3:.0f} mm Größe)",
                             OHNE_NETZ, karten=karten)
        nodes = knoten if v > 0 else [knoten[0], knoten[2], knoten[1], knoten[3]]
        els = [model.add_element("tet4", nodes, mat, group=koerper.name)]
        koerper.elemente = els
        C.say(log, f"Volumen {koerper.name}: ein Tetraeder")
        return els
    # Sweep: Grundflaeche mal Weg -> Hexaeder und Keile (statik3d.sweep).
    # Vor dem freien Vernetzer, denn er liefert das bessere Netz: rund ein
    # Element je Knoten statt vier (Auftrag Sechsflaechner, 20.09.2026).
    from . import sweep as SW
    if SW.betriebsart(model) != "aus" and koerper.name not in (getattr(model, "_sauber_abgelehnt", None) or {}):
        try:
            erk = SW.erkennen(model, koerper)
        except Exception as ex:               # noqa: BLE001 - dann der freie Vernetzer
            erk = None
            C.say(log, f"Volumen {koerper.name}: Sweep-Erkennung gescheitert ({str(ex)[:80]}) - "
                       "der freie Vernetzer übernimmt.")
        if erk is not None:
            els = SW.vernetzen(model, koerper, erk, h, log, cache, karten)
            if els:
                return els
        elif frei and SW.betriebsart(model) != "sauber":
            # Nicht als Ganzes Grundflaeche mal Weg: an Fussabdruecken in
            # Bloecke zerlegen - gesweepte Bloecke, wo es geht, Tetraeder fuer
            # den Rest, knotenkonform ueber die Schnittflaechen (statik3d.sweep).
            try:
                # Warum die Erkennung nicht griff - einmal je Koerper, mit
                # Zahlen. Ohne diese Zeile laesst sich nicht entscheiden,
                # welche Erweiterung sich lohnt (Nachtrag der Statik3D-Sitzung
                # vom 22.09.2026, Stufe 2).
                C.say(log, f"Volumen {koerper.name}: nicht gesweept - {SW.erkennen_warum_nicht(model, koerper)}.")
                els = SW.zerlegt_vernetzen(model, koerper, h, log, cache, karten, ordnung, fortschritt)
            except Exception as ex:           # noqa: BLE001 - dann der freie Vernetzer fuer das Ganze
                els = []
                C.warn(log, f"Volumen {koerper.name}: Zerlegen gescheitert ({str(ex)[:80]}) - "
                            "der freie Vernetzer übernimmt den ganzen Körper.")
            if els:
                return els
    if frei:
        from .mesher3d import mesh_koerper_frei
        return mesh_koerper_frei(model, koerper, h=h, log=log, cache=cache,
                                 ordnung=ordnung, fortschritt=fortschritt, karten=karten)
    C.warn(log, f"Volumen {koerper.name}: {len(flaechen)} Randflächen mit "
                f"{len(knoten)} Eckknoten - abgebildet vernetzen lassen sich nur "
                "Sechsflächner (6 Vierecke, 8 Knoten) und Tetraeder (4 Dreiecke, "
                "4 Knoten). Der freie Vernetzer ist abgeschaltet - nicht vernetzt.")
    koerper.kommentar = (f"{OHNE_NETZ} {len(flaechen)} Randflächen, {len(knoten)} Eckknoten - "
                         "freier Vernetzer abgeschaltet")
    koerper.netzgrund = "vernetzer_aus"
    return []


def abgebildet(model: Model, koerper, h: float = 0.0, karten: tuple = None, log: list = None) -> bool:
    """Wird der Koerper abgebildet vernetzt (Sechsflaechner, einzelner
    Tetraeder)? Das ist billig und bleibt im Hauptprozess; alles andere geht
    an den freien Vernetzer und darf in einen Arbeitsprozess. ``h``,
    ``karten`` und ``log`` braucht nur die Vorpruefung des Sweeps in der
    Betriebsart "sauber" (sweep.sweepbar)."""
    flaechen = [model.flaechen.get(x) for x in (koerper.flaechen or [])]
    if not flaechen or any(f is None for f in flaechen):
        return True
    ringe = [f.randknoten(model) for f in flaechen]
    knoten = {n for r in ringe for n in r}
    if len(flaechen) == 6 and len(knoten) == 8 and all(len(r) == 4 for r in ringe):
        return True
    if len(flaechen) == 4 and len(knoten) == 4:
        return True
    # Sweepbare Koerper sind billig (strukturiert) und muessen **vor** den
    # freien Koerpern laufen: ihre Flaechennetze bekommen die Nachbarn
    # vorgegeben (model.flaechennetze), die Arbeitsprozesse lesen das Modell
    # erst danach.
    from . import sweep as SW
    return SW.sweepbar(model, koerper, h=h, karten=karten, log=log)


# --------------------------------------------------------------------------
# Mehrere Volumen: parallel in Arbeitsprozessen
# --------------------------------------------------------------------------
_WORKER_MODEL = None
_WORKER_KARTEN = None


def netzkarten(model: Model, h: float = 0.0) -> tuple:
    """(h je Flaeche, h je Linie, gemeinsame Flaechen/Linien) - **modellweit**.

    Sie muessen einmal fuer das ganze Modell gebildet werden, nicht je
    Koerper: eine Flaeche, die zwei Bauteile teilen, bekommt sonst von jedem
    eine andere Teilung, ihre Knoten fallen nicht mehr zusammen und die Fuge
    faellt auseinander. Gemessen an zwei Prismen mit gemeinsamer Flaeche, bei
    denen nur einer sein Dickenmass anwendete: 13 der 33 Fugenknoten hingen
    frei in der Luft.
    """
    from . import mesher3d as M3
    h_flaechen, h_linien = M3.kantenlaengen_karte(model, h=h)
    return h_flaechen, h_linien, M3.gemeinsame_randflaechen(model)


def _modell_fuer_arbeiter_schreiben(model: Model, karten: tuple, pfad: str) -> None:
    """Modell und Netzkarten einmal in eine Datei - die Arbeitsprozesse lesen sie.

    Als Startargument des Pools blockierte das Modell jeden Prozessstart, bis
    das Kind es gelesen hatte: unter Windows (spawn) startet der Pool seine
    Prozesse nacheinander, und 1,7 MB Startargumente passen nicht in die
    Rohrleitung, bevor das Kind hochgefahren ist. Am Drehlager waren das
    31 x 0,83 s = 25,8 s, bevor der erste Arbeiter antwortete. Ein Pfad ist
    ein paar Byte: der Pool steht nach 1,8 s, die Arbeit beginnt nach 4,3 s.
    """
    import pickle
    with open(pfad, "wb") as f:
        pickle.dump((model, karten), f, protocol=pickle.HIGHEST_PROTOCOL)


def _koerper_arbeiter_init(pfad: str) -> None:
    """Jeder Arbeitsprozess liest das Modell einmal - die Geometrie genuegt -
    und dazu die modellweiten Netzkarten: er sieht immer nur **einen** Koerper
    und koennte sie selbst nicht bilden (siehe
    :func:`_modell_fuer_arbeiter_schreiben`)."""
    global _WORKER_MODEL, _WORKER_KARTEN
    import pickle
    with open(pfad, "rb") as f:
        _WORKER_MODEL, _WORKER_KARTEN = pickle.load(f)


def _koerper_arbeit(name: str, h: float) -> dict:
    """Die Rechenarbeit eines Koerpers im Arbeitsprozess (siehe
    :func:`statik3d.mesher3d.koerper_vorbereiten`)."""
    from . import mesher3d as M3
    k = _WORKER_MODEL.koerper[name]
    hf, hl, gem = _WORKER_KARTEN or ({}, {}, None)
    return M3.koerper_vorbereiten(_WORKER_MODEL, k, h=float(h or 0.0),
                                  h_linien=hl, h_flaechen=hf, gemeinsam=gem)


def prozesse_fuer_vernetzung() -> int:
    """Wie viele Arbeitsprozesse die Vernetzung nimmt: alle Kerne bis auf
    einen - der bleibt der Oberflaeche -, gedeckelt durch die Einstellung
    „Prozesse" (Berechnung → Einstellungen → Experten)."""
    from . import parallel as par
    return max(1, min(int(par.settings().workers), par.cpu_count() - 1))


def unbekannte(model: Model) -> int:
    """Die Zahl der Unbekannten, an der die Grenze misst: drei je Knoten des
    Modells (Verschiebung x, y, z), Kantenmitten quadratischer Elemente und
    Konstruktionsknoten der Geometrie eingeschlossen.

    Knoten von Schalen und Staeben haben sechs Freiheitsgrade und zaehlen hier
    auch nur drei; die Grenze zielt auf Volumennetze (Plan Fein smart,
    07.10.2026, S2: „die dreifache Summe“). Gezaehlt wird die Laenge des
    Knotenfelds - das kostet nichts und geht nach jedem Koerper."""
    return 3 * int(len(model.nodes))


def _neue_knoten_mindestens(erg, ordnung: int) -> int:
    """Wie viele Knoten ein fertiges, noch nicht eingebautes Ergebnis
    (:func:`mesher3d.koerper_vorbereiten`) mindestens anlegen wird - eine
    **untere Schranke**, damit sie nie ein Netz anhaelt, das passt.

    Gezaehlt werden nur Punkte im Inneren des Koerpers (Nummer ab der Zahl der
    Huellpunkte ``P``) und bei quadratischer Ordnung die Kanten mit wenigstens
    einem inneren Ende: beide gehoeren keinem Nachbarn. Huellpunkte koennen
    ein Nachbar oder eine Randlinie schon haben (mesher3d._knoten_anlegen);
    sie zaehlen erst beim Einbau."""
    if not isinstance(erg, dict) or erg.get("fehler") or erg.get("abgebrochen"):
        return 0
    TET, P = erg.get("TET"), erg.get("P")
    if TET is None or P is None:
        return 0
    TET = np.asarray(TET, np.int64).reshape(-1, 4)
    if not len(TET):
        return 0
    n_rand = len(P)
    innen = int(np.unique(TET[TET >= n_rand]).size)
    if ordnung >= 2:
        a = TET[:, [0, 0, 0, 1, 1, 2]].ravel()
        b = TET[:, [1, 2, 3, 2, 3, 3]].ravel()
        lo, hi = np.minimum(a, b), np.maximum(a, b)
        m = hi >= n_rand
        innen += int(np.unique(lo[m] * (int(TET.max()) + 1) + hi[m]).size)
    return innen


def _netz_zuruecksetzen(model: Model, koerper: list, n_el0: int, n_kn0: int,
                        cache: dict, log: list = None) -> None:
    """Das halbe Netz eines angehaltenen Laufs zuruecknehmen: alle Elemente
    ab ``n_el0`` (sie kamen in diesem Lauf dazu, add_element haengt an) und
    die Knoten ab ``n_kn0``, an denen danach nichts mehr haengt. Die
    Randseiten der Flaechen nimmt elemente_loeschen mit, die Netzkarten,
    Flaechennetze und Linienvorgaben bildet der naechste Lauf ohnehin neu;
    der Cache der gemeinsamen Knoten nennt geloeschte Knoten und wird leer."""
    from .importers import _common as C
    neu = list(range(int(n_el0), len(model.elements)))
    if neu:
        model.elemente_loeschen(neu)
    for k in koerper:
        k.elemente = []
    if int(model.nn) > n_kn0:
        model.netzknoten_loeschen(range(int(n_kn0), int(model.nn)))
    cache.clear()
    if len(model.elements) != n_el0 or int(model.nn) != n_kn0:
        C.warn(log, f"Netzgrenze: das halbe Netz ließ sich nicht ganz zurücknehmen "
                    f"({len(model.elements)} statt {n_el0} Elemente, {model.nn} statt {n_kn0} Knoten).")


def koerper_vernetzen(model: Model, koerper, hs: dict = None, log: list = None,
                      cache: dict = None, workers: int = None, fortschritt=None,
                      gewicht: dict = None, ordnung: int = 0, stufen=None,
                      hs_fuer=None) -> dict:
    """Mehrere Volumenkoerper vernetzen, mit der Grenze in Unbekannten.

    Die Arbeit macht :func:`_koerper_lauf` (unten beschrieben). Hier liegt
    die **Grenze** (``model.netz.hoechstens_unbekannte``, 0 = keine; Paket F2,
    07.10.2026): der Lauf zaehlt nach jedem eingebauten Koerper die
    Unbekannten (:func:`unbekannte`) und haelt **frueh** an, wenn sie die
    Grenze ueberschreiten - im parallelen Weg zaehlen die fertigen, noch nicht
    eingebauten Koerper mit ihrer unteren Schranke mit
    (:func:`_neue_knoten_mindestens`). Dann wird das halbe Netz
    zurueckgenommen und mit der naechsten, groeberen Stufe neu vernetzt -
    bis es passt (Entscheidung des Anwenders vom 07.10.2026: „selbsttaetig
    groeber“). Jede Vergroeberung steht im Protokoll mit Stufe, Grund und
    erreichter Zahl.

    ``stufen`` ist die Folge der Vergroeberung als Funktion
    ``einstellung(k) -> Netzeinstellungen | None`` fuer k = 1, 2, …: Stufe 0
    sind die eingestellten (wirksamen) Netzeinstellungen ``model.netz``
    selbst, None heisst „keine groebere Stufe“. Die Stufen von Fein liefert
    die Elementstufe (Paket F1); ohne ``stufen`` - Entwurf, Mittel - gibt es
    nur Stufe 0. Die **letzte** Stufe (die naechste ist None) wird ohne
    Anhalten fertig vernetzt; liegt sie ueber der Grenze, bleibt ihr Netz und
    das Protokoll warnt (``aus["grenze_warnung"]``). Ein Netz unter der Grenze
    ist Knoten fuer Knoten dasselbe wie ohne Grenze. Traegt eine Stufe einen
    Text in ``quelle``, nennt das Protokoll ihn neben der Stufennummer.

    ``hs_fuer(netz) -> {Name: h}`` gibt die Kantenlaenge je Koerper fuer eine
    groebere Stufe (Vorgabe: aus der Netzdichte, netzdichte.anwenden); fuer
    Stufe 0 gilt ``hs``. Waehrend einer Stufe steht ``model.netz`` auf ihren
    Einstellungen, danach wieder auf den eingestellten.

    Rueckgabe wie :func:`_koerper_lauf`, dazu "unbekannte" (am Ende), "stufe"
    (die vernetzte), "grenze" und bei Ueberschreitung "grenze_warnung".
    """
    from .importers import _common as C
    from .zahlen import zahl_text
    cache = {} if cache is None else cache
    koerper = list(koerper)
    grenze = int(getattr(getattr(model, "netz", None), "hoechstens_unbekannte", 0) or 0)
    if grenze <= 0 or not koerper:
        aus = _koerper_lauf(model, koerper, hs, log, cache, workers, fortschritt, gewicht, ordnung)
        aus.update(unbekannte=unbekannte(model), stufe=0, grenze=max(grenze, 0))
        return aus
    netz0 = model.netz
    n_el0, n_kn0 = len(model.elements), int(model.nn)
    k, netz_k, hs_k = 0, netz0, hs

    def stufentext(k_, n_):
        q = str(getattr(n_, "quelle", "") or "")
        return f"Stufe {k_}" + (f" ({q})" if k_ and q and q != str(getattr(netz0, "quelle", "") or "") else "")
    try:
        while True:
            naechste = stufen(k + 1) if stufen is not None else None
            ruf = fortschritt
            if k and fortschritt is not None:
                def ruf(anteil, text, _k=k):
                    return fortschritt(anteil, f"gröber vernetzt, Stufe {_k}: {text}")
            model.netz = netz_k
            aus = _koerper_lauf(model, koerper, hs_k, log, cache, workers, ruf, gewicht, ordnung,
                                grenze=grenze if naechste is not None else 0)
            if not (aus.get("ueber_grenze") and naechste is not None):
                break
            groesste = sorted((aus.get("knoten_je") or {}).items(), key=lambda x: -x[1])[:5]
            C.say(log, f"Netzgrenze: {stufentext(k, netz_k)} bei {aus['fertig']} von {len(koerper)} Volumen "
                       f"angehalten – {zahl_text(aus['unbekannte'])} Unbekannte über der Grenze von "
                       f"{zahl_text(grenze)} (Höchstzahl Unbekannte)"
                       + (f", davon mindestens {zahl_text(aus['unbekannte_vorab'])} aus fertigen, noch nicht "
                          "eingebauten Volumen" if aus.get("unbekannte_vorab") else "")
                       + (("; größte: " + ", ".join(f"{n} ({zahl_text(z)} Knoten)" for n, z in groesste))
                          if groesste else "")
                       + f". Das halbe Netz wird verworfen, vernetzt wird gröber mit {stufentext(k + 1, naechste)}.")
            _netz_zuruecksetzen(model, koerper, n_el0, n_kn0, cache, log)
            k, netz_k = k + 1, naechste
            hs_k = (hs_fuer or (lambda n_: _hs_aus_netz(model, n_, koerper)))(netz_k)
    finally:
        model.netz = netz0
    u = unbekannte(model)
    aus.update(unbekannte=u, stufe=k, grenze=grenze)
    if aus.get("abgebrochen"):
        return aus
    if u > grenze:
        text = (f"Das Netz hat {zahl_text(u)} Unbekannte und liegt über der Grenze von {zahl_text(grenze)} "
                f"(Netzeinstellungen → Höchstzahl Unbekannte)"
                + (f", auch in der gröbsten: {stufentext(k, netz_k)}." if k else
                   " – eine gröbere Stufe gibt es für diese Elemente nicht, das Netz bleibt, wie es ist.")
                + " Die Rechnung kann den Speicher übersteigen; gröber vernetzen oder die Grenze anheben.")
        C.warn(log, text)
        aus["grenze_warnung"] = text
    elif k:
        C.say(log, f"Netzgrenze: vernetzt mit {stufentext(k, netz_k)} – {zahl_text(u)} Unbekannte, "
                   f"unter der Grenze von {zahl_text(grenze)}.")
    return aus


def _hs_aus_netz(model: Model, netz, koerper: list) -> dict:
    """Die Kantenlaenge je Koerper fuer eine groebere Stufe - wie beim
    Vernetzen aus der Netzdichte, ohne die Teilung der Flaechen anzufassen."""
    from . import netzdichte as nd
    return nd.anwenden(model, netz, [], koerper)


def _koerper_lauf(model: Model, koerper, hs: dict = None, log: list = None,
                  cache: dict = None, workers: int = None, fortschritt=None,
                  gewicht: dict = None, ordnung: int = 0, grenze: int = 0) -> dict:
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

    ``grenze`` (Unbekannte, 0 = keine; Paket F2, 07.10.2026) haelt den Lauf
    an, sobald die Unbekannten des Modells (:func:`unbekannte`) sie
    ueberschreiten - gezaehlt nach jedem eingebauten Koerper und im
    parallelen Weg zusaetzlich mit den fertigen, noch nicht eingebauten
    (untere Schranke, :func:`_neue_knoten_mindestens`), damit die feste
    Einbaufolge den Halt nicht verzoegert. Laufende Prozesse werden beendet
    wie beim Abbruch; das halbe Netz nimmt :func:`koerper_vernetzen` zurueck.

    Rueckgabe {"elemente": Zahl, "fertig": Koerper mit Netz, "abgebrochen":
    bool, "prozesse": benutzte Prozesse, "ueber_grenze": bool, "unbekannte":
    Zahl beim Halt, "knoten_je": {Koerper: neue Knoten}}.
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
    aus = {"elemente": 0, "fertig": 0, "abgebrochen": False, "prozesse": 1,
           "ueber_grenze": False, "knoten_je": {}}
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

    def einbauen(k, els_oder_aus, n_vor: int = None):
        # n_vor: Knotenzahl vor dem Koerper - im seriellen und abgebildeten
        # Weg legt mesh_koerper die Knoten schon vor diesem Aufruf an
        nonlocal erledigt
        n_vor = int(model.nn) if n_vor is None else int(n_vor)
        if isinstance(els_oder_aus, dict):
            els = M3.koerper_einbauen(model, k, els_oder_aus, log, cache,
                                      koerper_ordnung(model, k, ordnung))
        else:
            els = els_oder_aus
        aus["elemente"] += len(els)
        aus["fertig"] += 1 if els else 0
        aus["knoten_je"][k.name] = int(model.nn) - n_vor
        erledigt += w_alle[k.name]

    def ueber(zusatz: int = 0) -> bool:
        """Liegt das Modell (dazu ``zusatz`` Knoten noch nicht eingebauter
        Koerper) ueber der Grenze? Dann steht es in ``aus``."""
        if grenze <= 0:
            return False
        u = unbekannte(model) + 3 * int(zusatz)
        if u <= grenze:
            return False
        aus["ueber_grenze"] = True
        aus["unbekannte"] = u
        aus["unbekannte_vorab"] = 3 * int(zusatz)
        return True

    def fertig_melden():
        if fortschritt is not None and not aus["abgebrochen"]:
            fortschritt(1.0, f"{aus['fertig']} von {len(koerper)} Volumen vernetzt")
        # Das Erfolgsmass des Auftrags Sechsflaechner: der Hexaederanteil
        from . import sweep as SW
        z = SW.hexaederanteil(model, koerper)
        if z["elemente"]:
            C.say(log, f"Volumen gesamt: {z['elemente']} Elemente auf {z['knoten']} Knoten "
                       f"({z['elemente_je_knoten']:.2f} je Knoten) - Hexaeder {z['hexaeder']} "
                       f"({z['anteil_hexaeder'] * 100:.1f} %), Keile {z['keile']}, "
                       f"Pyramiden {z['pyramiden']}, Tetraeder {z['tetraeder']}"
                       + (f"; Winkelfehler bis {z['winkelfehler_max']:.0f}°, "
                          f"{z['hexaeder_regelmaessig']} Hexaeder regelmäßig (≤ {SW.WINKELFEHLER_GRENZE:.1f}°)"
                          if z["hexaeder"] or z["keile"] else ""))

    # 1) Abgebildete Koerper gleich hier - das kostet nichts
    # Das Groessenfeld einmal je Lauf und **vor** den Karten: die
    # Linienteilung liest es schon beim Kartieren (Bogenwinkel an
    # Nebenflaechen). Es haengt am Modell und geht mit ihm in die
    # Arbeitsprozesse (netzfeld.aufbauen).
    from . import netzfeld
    model.groessenfeld = netzfeld.aufbauen(model, log=log)
    # Der Bogenwinkel je Linie aus den Vorgaben der Koerper - einmal je Lauf,
    # vor den Karten, und mit dem Modell in die Arbeitsprozesse
    from . import mesher3d as _M3
    _je_linie = _M3.bogenwinkel_je_linie(model)
    if _je_linie or _M3.bogenwinkel_vorgabe(model) != _M3.BOGENWINKEL:
        C.say(log, f"Bogenwinkel: Vorgabe {_M3.bogenwinkel_vorgabe(model):.0f}° je Abschnitt"
                   + (f", an {len(_je_linie)} Linien nach der Vorgabe eines Körpers" if _je_linie else ""))
    # Vorgegebene Flaechennetze (Sweep) - je Lauf neu; die abgebildeten und
    # gesweepten Koerper fuellen sie, die freien Koerper lesen sie.
    model.flaechennetze = {}
    model.linienvorgabe = {}
    model._sauber_abgelehnt = {}
    # Die modellweiten Netzkarten einmal je Lauf - fuer alle Pfade. Je Koerper
    # gebildet kosteten sie am Drehlager 48 x 1,5 s in der seriellen Phase.
    karten = netzkarten(model)
    # Die Lagen der sweepbaren Koerper vorab und modellweit: ihre Mantellinien
    # muessen in jedem Koerper gleich geteilt sein, auch in den Nachbarn
    # (sweep.lagenvorgabe). Vor dem ersten Netz, denn jede Linienteilung
    # liest es - im Hauptprozess wie in den Arbeitsprozessen (das Modell geht
    # erst danach an sie).
    from . import sweep as SW
    model.linienvorgabe = SW.lagenvorgabe(model, koerper, hs, karten, log)
    # Erst jetzt, mit den Karten: in der Betriebsart "sauber" prueft
    # sweep.sweepbar den Koerper vor, und nur ein sauber gesweepter bleibt
    # im Hauptprozess - der Rest ist frei und geht in die Arbeitsprozesse
    frei = [k for k in koerper if not abgebildet(model, k, h=float(hs.get(k.name, 0.0) or 0.0),
                                                 karten=karten, log=log)]
    for k in koerper:
        if k in frei:
            continue
        if not melden(f"{k.name} abgebildet"):
            aus["abgebrochen"] = True
            return aus
        n_vor = int(model.nn)
        einbauen(k, mesh_koerper(model, k, log, cache=cache,
                                 h=float(hs.get(k.name, 0.0) or 0.0), ordnung=ordnung,
                                 karten=karten), n_vor)
        if ueber():
            return aus
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
            n_vor = int(model.nn)
            els = mesh_koerper(model, k, log, cache=cache,
                               h=float(hs.get(k.name, 0.0) or 0.0), ordnung=ordnung,
                               fortschritt=ruf, karten=karten)
            einbauen(k, els, n_vor)
            if not els and log and any("abgebrochen" in z for z in log[-3:]):
                aus["abgebrochen"] = True
                break
            if ueber():
                break
        if not aus["ueber_grenze"]:
            fertig_melden()
        return aus
    # 2) Parallel: die Rechenarbeit in Arbeitsprozessen, der Einbau hier
    from . import parallel as par
    import os
    import tempfile
    aus["prozesse"] = w
    arbeiterdatei = ""
    try:
        ctx = par._context()
        # Der Arbeitsprozess sieht immer nur einen Koerper und koennte die
        # Netzkarten nicht bilden; Modell und Karten gehen ueber eine Datei,
        # nicht als Startargument.
        fd, arbeiterdatei = tempfile.mkstemp(prefix="statik3d_netz_", suffix=".pkl")
        os.close(fd)
        _modell_fuer_arbeiter_schreiben(model, karten, arbeiterdatei)
        pool = ctx.Pool(processes=w, initializer=_koerper_arbeiter_init,
                        initargs=(arbeiterdatei,))
    except Exception as ex:               # noqa: BLE001 - kein Prozess-Pool: seriell
        _datei_weg(arbeiterdatei)
        C.say(log, f"Arbeitsprozesse nicht verfügbar ({ex}) - die Volumen werden nacheinander vernetzt.")
        aus = _seriell_nach(model, frei, hs, log, cache, fortschritt, gewicht, ordnung,
                            aus, w_alle, summe, erledigt, karten=karten, ueber=ueber)
        if not aus["ueber_grenze"]:
            fertig_melden()
        return aus
    namen = {k.name: k for k in frei}
    offen = {}
    try:
        for k in frei:
            offen[k.name] = pool.apply_async(_koerper_arbeit,
                                             (k.name, float(hs.get(k.name, 0.0) or 0.0)))
        t_tick = 0.0
        # Eingebaut wird in der **festen** Folge von ``frei`` (gross zuerst),
        # nicht in der des Fertigwerdens: die Knoten- und Elementnummern
        # entstehen beim Einbau (mesher3d.koerper_einbauen), und zwei Laeufe
        # derselben Datei - oder zwei Maschinen mit verschiedener Kernzahl -
        # muessen dieselben Nummern ergeben. Vorher behielten am Drehlager
        # 18 von 3 731 Knoten ihre Nummer zwischen zwei Laeufen (Statik3D-
        # Sitzung, gemessen 22.09.2026); jeder Bericht mit einer Knotennummer
        # war damit unnachpruefbar. Gerechnet wird weiter parallel; nur der
        # Einbau wartet, bis der naechste in der Reihe fertig ist.
        reihe = [k.name for k in frei]
        vorab: dict = {}
        while offen:
            fertige = []
            while reihe and reihe[0] in offen and offen[reihe[0]].ready():
                fertige.append(reihe.pop(0))
            for name in fertige:
                r = offen.pop(name)
                try:
                    erg = r.get()
                except Exception as ex:       # noqa: BLE001
                    erg = {"fehler": f"Fehler im Arbeitsprozess: {ex}", "log": []}
                einbauen(namen[name], erg)
            if grenze > 0:
                # Die fertigen, noch nicht eingebauten Koerper zaehlen mit
                # ihrer unteren Schranke mit - sonst wartete der Halt auf den
                # grossen Koerper vorn in der Reihe (Plan Fein smart, S2)
                for name, r in offen.items():
                    if name not in vorab and r.ready():
                        try:
                            vorab[name] = _neue_knoten_mindestens(
                                r.get(), koerper_ordnung(model, namen[name], ordnung))
                        except Exception:     # noqa: BLE001 - der Fehler kommt beim Einbau
                            vorab[name] = 0
                if ueber(sum(vorab.get(n_, 0) for n_ in offen)):
                    break
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
        if aus["abgebrochen"] or aus["ueber_grenze"]:
            pool.terminate()
            if aus["abgebrochen"]:
                C.say(log, f"Vernetzen abgebrochen: {len(offen)} Volumen bleiben ohne Netz "
                           "(die Arbeitsprozesse wurden beendet).")
        else:
            pool.close()
        pool.join()
    except BaseException:
        pool.terminate()
        pool.join()
        raise
    finally:
        _datei_weg(arbeiterdatei)
    if not aus["ueber_grenze"]:
        fertig_melden()
    return aus


def _datei_weg(pfad: str) -> None:
    """Die Modelldatei der Arbeiter aufraeumen - auch nach Abbruch oder Fehler."""
    import os
    if pfad:
        try:
            os.remove(pfad)
        except OSError:
            pass


def _seriell_nach(model, frei, hs, log, cache, fortschritt, gewicht, ordnung,
                  aus, w_alle, summe, erledigt, karten: tuple = None, ueber=None):
    """Rueckfall ohne Prozess-Pool: die freien Koerper nacheinander;
    ``ueber()`` prueft nach jedem die Grenze in Unbekannten."""
    def melden(text, anteil_akt=0.0, w_akt=0.0):
        if fortschritt is None:
            return True
        return fortschritt((erledigt + anteil_akt * w_akt) / summe, text) is not False
    for k in frei:
        def ruf(anteil, text, _k=k):
            return melden(f"{_k.name}: {text}" if text else _k.name, anteil or 0.0, w_alle[_k.name])
        els = mesh_koerper(model, k, log, cache=cache, h=float(hs.get(k.name, 0.0) or 0.0),
                           ordnung=ordnung, fortschritt=ruf, karten=karten)
        aus["elemente"] += len(els)
        aus["fertig"] += 1 if els else 0
        erledigt += w_alle[k.name]
        if not els and log and any("abgebrochen" in z for z in log[-3:]):
            aus["abgebrochen"] = True
            break
        if ueber is not None and ueber():
            break
    aus["prozesse"] = 1
    return aus


#: Kanten des Hexaeders in der Knotenreihenfolge von hex20 (unten, oben, senkrecht)
HEX_KANTEN = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
              (0, 4), (1, 5), (2, 6), (3, 7))


QUADER_SEITEN = {0: (0, 1, 2, 3), 1: (4, 5, 6, 7), 2: (0, 1, 5, 4),
                 3: (1, 2, 6, 5), 4: (2, 3, 7, 6), 5: (3, 0, 4, 7)}
#: Lokale Ecken (r, s, t) -> Nummer in der hex8-Reihenfolge
QUADER_ECKNR = {(0, 0, 0): 0, (1, 0, 0): 1, (1, 1, 0): 2, (0, 1, 0): 3,
                (0, 0, 1): 4, (1, 0, 1): 5, (1, 1, 1): 6, (0, 1, 1): 7}


def quader_kanten(model: Model, koerper, ecken: list) -> dict:
    """{(lokale Ecke a, lokale Ecke b): Linienname} fuer die zwoelf Kanten eines
    Sechsflaechners mit den acht Eckknoten ``ecken`` (hex8-Reihenfolge)."""
    lokal = {int(n): i for i, n in enumerate(ecken)}
    aus = {}
    for fname in (koerper.flaechen or []):
        f = model.flaechen.get(fname)
        for lname in (f.linien or []) if f is not None else []:
            ln = model.lines.get(lname)
            if ln is None or len(ln.nodes) < 2:
                continue
            e0, e1 = lokal.get(int(ln.nodes[0])), lokal.get(int(ln.nodes[-1]))
            if e0 is None or e1 is None or e0 == e1:
                continue
            aus[(e0, e1)] = lname
            aus[(e1, e0)] = lname
    return aus


def quader_richtungen(kanten: dict) -> list:
    """Die Linien der drei Kantenrichtungen eines Sechsflaechners: [x-Kanten,
    y-Kanten, z-Kanten] (je vier Namen, fehlende ausgelassen)."""
    gruppen = [[(0, 1), (3, 2), (4, 5), (7, 6)], [(0, 3), (1, 2), (4, 7), (5, 6)],
               [(0, 4), (1, 5), (2, 6), (3, 7)]]
    return [[kanten[k] for k in g if k in kanten] for g in gruppen]


def _hex_netz(model: Model, ecken: list[int], nx: int, ny: int, nz: int,
              mat: str, gruppe: str, ordnung: int = 1, kanten: dict = None,
              koerper=None, cache: dict = None) -> list[int]:
    """Abgebildetes Hexaedernetz in einem Sechsflaechner (trilineare Abbildung);
    ``ordnung`` 2 gibt Hexaeder mit 20 Knoten (Kantenmitten dazu).

    Mit ``koerper`` bekommt das Netz, was ihm bis zum 21.09.2026 fehlte
    (gemessen an einem Quader 2 x 1 x 1 m mit Flaechenlast: Auflagerkraft
    0 kN statt p·A; Abnahme an einem Quader mit Tetraeder-Nachbarn: 21 doppelte
    Knoten):

    * die **Randseiten** der sechs Flaechen (Boden Seite 0, Deckel 1, dann
      s = 0, r = 1, s = 1, r = 0 als Seiten 2 bis 5) - Flaechenlast, Kontakt
      und Flaechenlager brauchen sie;
    * **gemeinsame Knoten** mit Nachbarn: Kanten- und Flaechenpunkte tragen
      dieselben Schluessel wie beim freien Vernetzer und beim Sweep
      (sweep._knoten_anlegen: Kennung ("L", Linie, k) in der Zaehlrichtung
      der Linie, (Flaeche, Koordinate) fuer Flaechenpunkte);
    * **vorgegebene Flaechennetze** (model.flaechennetze) fuer die sechs
      Flaechen, damit ein freier Nachbar dieselben Punkte trifft.
    """
    from . import sweep as SW
    P = model.nodes[ecken]
    ecknr = QUADER_ECKNR
    linien = quader_kanten(model, koerper, ecken) if koerper is not None else {}
    flaechen = {}
    if koerper is not None:
        for sname in (koerper.flaechen or []):
            f = model.flaechen.get(sname)
            if f is None:
                continue
            menge = {int(n) for n in f.randknoten(model)}
            for seite, ek in QUADER_SEITEN.items():
                if menge == {int(ecken[i]) for i in ek}:
                    flaechen[seite] = f
    n_rst = (nx, ny, nz)

    def kennung(i, j, k):
        """Kennung und Flaeche eines Gitterpunkts - Kante, Flaeche oder None."""
        r, s_, t = i / nx, j / ny, k / nz
        rand = [x in (0.0, 1.0) for x in (r, s_, t)]
        if sum(rand) == 3:
            return ("K", int(ecken[ecknr[(int(round(r)), int(round(s_)), int(round(t)))]])), None
        if sum(rand) == 2:
            achse = rand.index(False)
            fest = [int(round(x)) for x in (r, s_, t)]
            e0 = list(fest); e0[achse] = 0
            e1 = list(fest); e1[achse] = 1
            a_, b_ = ecknr[tuple(e0)], ecknr[tuple(e1)]
            name = linien.get((a_, b_))
            if name is None:
                return None, None
            lauf = (i, j, k)[achse]
            ln = model.lines[name]
            kk = lauf if int(ln.nodes[0]) == int(ecken[a_]) else n_rst[achse] - lauf
            return ("L", name, int(kk)), None
        if sum(rand) == 1:
            if rand[2]:
                seite = 0 if t == 0.0 else 1
            elif rand[1]:
                seite = 2 if s_ == 0.0 else 4
            else:
                seite = 5 if r == 0.0 else 3
            f = flaechen.get(seite)
            return None, (f.name if f is not None else None)
        return None, None

    X, kenn, fl, index = [], [], [], {}
    for i in range(nx + 1):
        for j in range(ny + 1):
            for k in range(nz + 1):
                r, s_, t = i / nx, j / ny, k / nz
                N = np.array([(1 - r) * (1 - s_) * (1 - t), r * (1 - s_) * (1 - t),
                              r * s_ * (1 - t), (1 - r) * s_ * (1 - t),
                              (1 - r) * (1 - s_) * t, r * (1 - s_) * t,
                              r * s_ * t, (1 - r) * s_ * t])
                ke, fname = kennung(i, j, k)
                index[(i, j, k)] = len(X)
                X.append(N @ P)
                kenn.append(ke)
                fl.append(fname)
    X = np.asarray(X, float)
    if koerper is not None:
        nr = SW._knoten_anlegen(model, koerper, X, kenn, fl, cache)
    else:
        nr = np.array([model.add_node(*x) for x in X], int)
        for (i, j, k), idx in index.items():
            r, s_, t = i / nx, j / ny, k / nz
            if r in (0.0, 1.0) and s_ in (0.0, 1.0) and t in (0.0, 1.0):
                nr[idx] = ecken[ecknr[(int(round(r)), int(round(s_)), int(round(t)))]]
    ids = np.zeros((nx + 1, ny + 1, nz + 1), dtype=int)
    for (i, j, k), idx in index.items():
        ids[i, j, k] = int(nr[idx])
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
    if koerper is None:
        return els
    # ---- Randseiten der sechs Flaechen ------------------------------------
    weg = set(int(e) for e in els)
    for f in flaechen.values():
        f.randseiten = [x for x in (f.randseiten or []) if int(x[0]) not in weg]
    e_idx = 0
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                e = els[e_idx]
                e_idx += 1
                for seite, treffer in ((0, k == 0), (1, k == nz - 1), (2, j == 0),
                                       (3, i == nx - 1), (4, j == ny - 1), (5, i == 0)):
                    if treffer and seite in flaechen:
                        flaechen[seite].randseiten.append([e, seite])
    # ---- Vorgegebene Flaechennetze fuer freie Nachbarn --------------------
    netze = getattr(model, "flaechennetze", None)
    if netze is None:
        netze = model.flaechennetze = {}
    for seite, f in flaechen.items():
        if seite in (0, 1):
            k0 = 0 if seite == 0 else nz
            gitter = [[(i, j, k0) for j in range(ny + 1)] for i in range(nx + 1)]
        elif seite in (2, 4):
            j0 = 0 if seite == 2 else ny
            gitter = [[(i, j0, k) for k in range(nz + 1)] for i in range(nx + 1)]
        else:
            i0 = 0 if seite == 5 else nx
            gitter = [[(i0, j, k) for k in range(nz + 1)] for j in range(ny + 1)]
        idx = [[index[g] for g in zeile] for zeile in gitter]
        FP = X[[q for zeile in idx for q in zeile]]
        FK = [kenn[q] for zeile in idx for q in zeile]
        n2 = len(idx[0])
        T = []
        for a_ in range(len(idx) - 1):
            for b_ in range(n2 - 1):
                p0, p1 = a_ * n2 + b_, a_ * n2 + b_ + 1
                p2, p3 = (a_ + 1) * n2 + b_ + 1, (a_ + 1) * n2 + b_
                if np.linalg.norm(FP[p0] - FP[p2]) <= np.linalg.norm(FP[p1] - FP[p3]):
                    T += [(p0, p1, p2), (p0, p2, p3)]
                else:
                    T += [(p0, p1, p3), (p1, p2, p3)]
        Q = [(a_ * n2 + b_, a_ * n2 + b_ + 1, (a_ + 1) * n2 + b_ + 1, (a_ + 1) * n2 + b_)
             for a_ in range(len(idx) - 1) for b_ in range(n2 - 1)]
        netze[f.name] = (FP.copy(), np.asarray(T, int).reshape(-1, 3), FK,
                         np.asarray(Q, int).reshape(-1, 4), np.zeros((0, 3), int))
    return els


# --------------------------------------------------------------------------
# Das ganze Modell vernetzen - ohne Oberflaeche
# --------------------------------------------------------------------------
def modell_vernetzen(model: Model, log: list = None, fortschritt=None, workers: int = None,
                     flaechen: list = None, koerper: list = None, hs: dict = None,
                     stufen=None) -> dict:
    """Flaechen und Volumen vernetzen und den Nachlauf ausfuehren - in
    derselben Folge wie die Oberflaeche (``gui.main._vernetzen``), aber
    ohne Qt: Netzdichte, Kontaktfugen zuruecksetzen, Flaechen, Volumen
    (parallel), Lasten verteilen, Kontaktfugen ausfuehren, starre Flaechen
    koppeln, Stabenden anschliessen, Lager auf das Netz.

    Das braucht, wer ohne Oberflaeche vernetzt: die Befehlszeile
    (``statik3d --vernetzen``), die adaptive Vernetzung
    (:mod:`statik3d.adaptiv`), die Pruefungen. ``hs`` ueberschreibt die
    Kantenlaenge je Volumen (Name -> m), sonst kommt sie aus der Netzdichte.

    Jeder Schritt misst sich selbst, wie in der Oberflaeche - am Drehlager
    lag die Zeit nicht im Netz (119,9 s), sondern im Nachlauf: Kontaktfugen
    203,6 s, Lasten verteilen 86,2 s (Protokoll vom 18.09.2026).

    ``stufen`` ist die Folge der Vergroeberung fuer die Grenze in Unbekannten
    (:func:`koerper_vernetzen`, Paket F2); ohne sie wird ueber der Grenze nur
    gewarnt. Rueckgabe {"elemente", "zeiten": {Schritt: s}, "abgebrochen",
    "prozesse", "unbekannte", "stufe"} und bei Ueberschreitung
    "grenze_warnung".
    """
    import time
    from . import fugen, netzdichte as nd, supports
    from .importers import _common as C
    log = [] if log is None else log
    netz = model.netz
    flaechen = list(model.flaechen.values()) if flaechen is None else list(flaechen)
    koerper = list(model.koerper.values()) if koerper is None else list(koerper)
    zeiten: dict = {}
    t0 = time.time()
    gewicht: dict = {}
    try:
        for name, _art, _h, n_, _grund, _teil in nd.vorschau(model, netz, flaechen, koerper)["zeilen"]:
            gewicht[name] = max(1.0, float(n_ or 0.0))
    except Exception:                       # noqa: BLE001 - dann zaehlt jedes Objekt gleich
        gewicht = {}
    # Die eigene Teilung jeder Flaeche bleibt erhalten (wie in der Oberflaeche)
    eigene_teilung = {f.name: list(f.teilung or []) for f in flaechen}
    hs_alle = nd.anwenden(model, netz, flaechen, koerper, log)
    if hs:
        hs_alle.update({k: float(v) for k, v in hs.items() if v})
    C.say(log, f"Netzeinstellungen: {netz.beschreibung()}")
    aus = {"elemente": 0, "abgebrochen": False, "prozesse": 1}
    try:
        fugen.kontaktfugen_zuruecksetzen(model, log)
        # Alte Netze in **einem** Zug entfernen: elemente_loeschen nummeriert
        # alles um, und je Objekt gerufen waere das am Drehlager 1483 Durchgaenge
        # ueber 640 000 Elemente.
        alt = [e for f in flaechen for e in (f.elemente or [])] + \
              [e for k in koerper for e in (k.elemente or [])]
        if alt:
            model.elemente_loeschen(alt)
            # Die Knoten des alten Netzes gleich mit: sonst stehen sie als
            # „Knoten ohne Element" in der Abnahme und als Freiheitsgrade
            # ohne Steifigkeit im Gleichungssystem (Platte mit Bohrung nach
            # einer adaptiven Runde: 10 143 verwaiste Knoten, 20.09.2026).
            # Ohne den Zusatz in model.py (Arbeitskopie einer anderen Sitzung)
            # bleiben sie liegen - das Protokoll sagt es.
            if hasattr(model, "netzknoten_loeschen"):
                weg = model.netzknoten_loeschen()
                if weg:
                    C.say(log, f"{weg} Knoten des alten Netzes entfernt")
            else:
                C.warn(log, "Die Knoten des alten Netzes bleiben stehen (Model.netzknoten_loeschen "
                            "fehlt in diesem Stand von model.py).")
        for f in flaechen:
            f.elemente = []
        for k in koerper:
            k.elemente = []
        kanten: dict = {}
        for f in flaechen:
            aus["elemente"] += len(mesh_flaeche(model, f, log, kanten=kanten))
        if koerper:
            # Eine groebere Stufe der Grenze bekommt ihre Kantenlaenge aus der
            # Netzdichte; was ``hs`` hier vorgibt, gilt auch dort
            def hs_fuer(netz_k):
                h_k = _hs_aus_netz(model, netz_k, koerper)
                h_k.update({k: float(v) for k, v in (hs or {}).items() if v})
                return h_k
            erg = koerper_vernetzen(model, koerper, hs=hs_alle, log=log, cache={},
                                    workers=workers, fortschritt=fortschritt, gewicht=gewicht,
                                    stufen=stufen, hs_fuer=hs_fuer)
            aus["elemente"] += erg["elemente"]
            aus["prozesse"] = erg.get("prozesse", 1)
            aus["abgebrochen"] = bool(erg.get("abgebrochen"))
            aus["stufe"] = erg.get("stufe", 0)
            if erg.get("grenze_warnung"):
                aus["grenze_warnung"] = erg["grenze_warnung"]
        zeiten["Netz erzeugen"] = time.time() - t0
        t0 = time.time()
        model.lasten_verteilen(log)
        zeiten["Lasten verteilen"] = time.time() - t0
        t0 = time.time()
        fugen.kontaktfugen_ausfuehren(model, log)
        zeiten["Kontaktfugen trennen"] = time.time() - t0
        t0 = time.time()
        fugen.starre_flaechen_koppeln(model, log)
        zeiten["Starre Flächen koppeln"] = time.time() - t0
        t0 = time.time()
        fugen.stabenden_koppeln(model, log)
        zeiten["Stabenden anschließen"] = time.time() - t0
        t0 = time.time()
        supports.lager_auf_netz(model, log)
        zeiten["Lager auf das Netz"] = time.time() - t0
    finally:
        for f in flaechen:
            if eigene_teilung.get(f.name):
                f.teilung = eigene_teilung[f.name]
    aus["zeiten"] = zeiten
    aus["unbekannte"] = unbekannte(model)
    lang = sorted(((k, v) for k, v in zeiten.items() if v >= 0.05), key=lambda x: -x[1])
    C.say(log, f"Vernetzt: {aus['elemente']} Elemente in {sum(zeiten.values()):.1f} s"
               + (f" auf {aus['prozesse']} Prozessen" if aus["prozesse"] > 1 else "")
               + (" - abgebrochen" if aus["abgebrochen"] else "")
               + ("; davon " + ", ".join(f"{k} {v:.1f} s" for k, v in lang) if lang else ""))
    return aus
