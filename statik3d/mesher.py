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


# ---------------------------------------------------------------------------
# Schalenflaechen mit gemeinsamen Randlinien (09.11.2026)
# ---------------------------------------------------------------------------
def _ist_schale(model: Model, f) -> bool:
    """Bekommt die Flaeche ein eigenes Schalennetz (Dicke, eigene Steifigkeit)?"""
    if getattr(f, "steifigkeit", ""):
        return False
    traegt = getattr(model, "flaeche_traegt", None)
    return bool(f.dicke) or traegt is None or bool(traegt(f.name))

# ---------------------------------------------------------------------------
# Teilen im Netz: Knoten auf Linie, Linie in Flaeche (Befund A19, 09.11.2026)
# ---------------------------------------------------------------------------
#: Fangbereich fuer fremde Knoten und Linien - derselbe wie in der Abnahme
#: (diagnose._abnahme_schalen_ohne_linie)
TEIL_FANG = 1e-3
#: kuerzestes Teilstueck einer im Netz geteilten Linie
TEIL_MIN = 1e-3


class _Netzgeometrie:
    """Das Modell, wie der Schalenvernetzer es sieht: dieselben Knoten und
    Linien, dazu die **Teilstuecke** der Linien, die im Netz an einem fremden
    Knoten geteilt werden. Die Teilstuecke stehen nur hier - ``model.lines``
    bleibt, wie der Anwender es angelegt hat (Entscheidung vom 09.11.2026:
    geteilt wird nur im Netz, nicht in der Geometrie)."""

    def __init__(self, model, teilstuecke: dict):
        import collections
        self.__dict__["_modell"] = model
        self.__dict__["lines"] = collections.ChainMap(dict(teilstuecke), model.lines)

    def __getattr__(self, name):
        return getattr(self.__dict__["_modell"], name)


def _strecken_kreuzen(p, q, a, b) -> bool:
    """Trifft das **Innere** der ebenen Strecke p-q die Strecke a-b
    (Enden von a-b eingeschlossen)? Parallele Strecken: nein."""
    r, t = q - p, b - a
    det = float(r[0] * t[1] - r[1] * t[0])
    if abs(det) <= 1e-12 * float(np.linalg.norm(r) * np.linalg.norm(t)):
        return False
    w = a - p
    lam = float(w[0] * t[1] - w[1] * t[0]) / det
    mue = float(w[0] * r[1] - w[1] * r[0]) / det
    return 1e-9 < lam < 1 - 1e-9 and -1e-9 <= mue <= 1 + 1e-9


def _teilplan(model: Model, schalen: list) -> dict:
    """Wo beruehren sich Schalenflaechen, ohne eine Linie zu teilen - und wie
    wird dort **im Netz** geteilt (wie in RFEM Knoten auf Linie und Linie in
    Flaeche)? Entscheidung des Anwenders vom 09.11.2026 zum Befund A19 der
    Pruefagenten: am Stoss ohne gemeinsame Linie hingen zehn doppelte Knoten
    lose nebeneinander (0,7421 statt 0,1429 mm), die Rippe auf der ungeteilten
    Platte trug nichts (33,089 statt 0,517 mm).

    (a) **Knoten auf Linie**: liegt ein Linienknoten einer anderen Flaeche im
        Innern einer geraden Randlinie (zwei Knoten), wird die Linie dort in
        Teilstuecke zerlegt. Ein Teilstueck, das es zwischen genau diesen
        Knoten schon als Linie gibt, **ist** diese Linie - so teilen die
        Flaechen beiderseits ihre Netzknoten wie an einer gemeinsamen Linie.
    (b) **Linie in Flaeche**: liegt ein gerades Stueck einer anderen, nicht
        in derselben Ebene liegenden Flaeche ganz in einer ebenen Flaeche
        (Enden an Randknoten oder im Innern), wird es dort Zwangslinie des
        Netzes.

    Verbunden wird nur, was genau passt (Abstand bis 1e-6 der Laenge, wie die
    Stuetzknoten); was im Fangbereich von 1 mm daneben liegt (schleifend), was
    nur teilweise in der Flaeche liegt oder den Rand ohne Knoten kreuzt, bleibt
    unverbunden und steht mit dem Grund in ``warnungen``. Gekruemmte Linien
    und Linien mit Zwischenknoten werden nicht geteilt.

    Rueckgabe: ``teilstuecke`` {Name: Line} (nur fuer :class:`_Netzgeometrie`),
    ``ersetzt`` (Linienliste -> Linienliste im Netz), ``zwang`` {Flaeche:
    [Linien]}, ``geteilt`` (Flaechen, die deshalb frei vernetzt werden),
    ``beteiligt`` (alle Flaechen an einer Stelle), ``meldungen``, ``warnungen``."""
    from .model import Line, _randstuecke
    ersatz: dict = {}
    umlegen: dict = {}

    def ersetzt(namen) -> list:
        aus = []
        for x in namen or []:
            aus.extend(ersatz.get(x) or [umlegen.get(x, x)])
        return aus
    plan = {"teilstuecke": {}, "ersetzt": ersetzt, "zwang": {}, "geteilt": set(), "beteiligt": set(),
            "meldungen": [], "warnungen": [], "aktiv": False}
    lines = getattr(model, "lines", None) or {}
    if len(schalen) < 2 or not lines:
        return plan
    from scipy.spatial import cKDTree
    from . import mesher3d as M3
    X = np.asarray(model.nodes, float)
    nn = len(X)

    def linien_von(f) -> list:
        return list(f.linien or []) + [y for loch in (f.oeffnungen or []) for y in loch]

    def gerade(ln) -> bool:
        return str(getattr(ln, "typ", "polyline") or "polyline").lower() in GERADE_LINIEN

    def mm(x: float) -> str:
        return f"{x * 1e3:.3f}".replace(".", ",")

    def fl(namen) -> str:
        namen = sorted(namen)
        return ("Fläche " if len(namen) == 1 else "Flächen ") + ", ".join(namen)

    def stelle(*mengen):
        for m in mengen:
            plan["beteiligt"].update(m)

    besitzer: dict = {}                       # Linie -> Flaechen
    for f in schalen:
        for x in dict.fromkeys(linien_von(f)):
            ln = lines.get(x)
            if ln is not None and len(ln.nodes) >= 2 and all(0 <= int(k) < nn for k in ln.nodes):
                besitzer.setdefault(x, []).append(f.name)
    kn_besitzer: dict = {}                    # Knoten -> Flaechen
    for x, wem in besitzer.items():
        ln = lines[x]
        kn = ln.nodes if gerade(ln) else (ln.nodes[0], ln.nodes[-1])
        for k in kn:
            kn_besitzer.setdefault(int(k), set()).update(wem)
    if not kn_besitzer:
        return plan

    # ---- (a) Knoten auf Linie -------------------------------------------
    K = np.array(sorted(kn_besitzer), int)
    baum = cKDTree(X[K])
    ketten: dict = {}                         # Linie -> [a, k1, ..., b]
    for x, wem in besitzer.items():
        ln = lines[x]
        if not gerade(ln):
            continue
        kn = [int(k) for k in ln.nodes]
        treffer = []
        for a, b in zip(kn[:-1], kn[1:]):
            d = X[b] - X[a]
            L2 = float(d @ d)
            if L2 <= 0:
                continue
            for j in baum.query_ball_point(0.5 * (X[a] + X[b]), 0.5 * np.sqrt(L2) + TEIL_FANG):
                k = int(K[j])
                if k in kn:
                    continue
                fremd = kn_besitzer[k] - set(wem)
                if not fremd:
                    continue
                t = float((X[k] - X[a]) @ d) / L2
                if not 1e-6 < t < 1 - 1e-6:
                    continue
                ab = float(np.linalg.norm(X[k] - (X[a] + t * d)))
                if ab < TEIL_FANG:
                    treffer.append((t, k, ab, fremd))
        if not treffer:
            continue
        treffer.sort(key=lambda z: (z[0], z[1]))
        if len(kn) > 2:
            for _t, k, _ab, fremd in treffer:
                stelle(wem, fremd)
                plan["warnungen"].append(
                    f"Knoten {k + 1} ({fl(fremd)}) liegt auf der Linie {x} ({fl(wem)}): die Linie hat "
                    "Zwischenknoten und wird im Netz nicht geteilt – dort nicht verbunden.")
            continue
        a, b = kn
        ell = float(np.linalg.norm(X[b] - X[a]))
        tol = STUETZKNOTEN_TOL * ell + 1e-9
        kette, gruende = [a], []
        for _t, k, ab, fremd in treffer:
            stelle(wem, fremd)
            if ab > tol:
                plan["warnungen"].append(
                    f"Knoten {k + 1} ({fl(fremd)}) liegt {mm(ab)} mm neben der Linie {x} ({fl(wem)}) – "
                    f"schleifend, über der Toleranz von {mm(tol)} mm: dort nicht verbunden.")
                continue
            nachbar = next((m for m in (kette[-1], b)
                            if float(np.linalg.norm(X[k] - X[m])) < TEIL_MIN), None)
            if nachbar is not None:
                plan["warnungen"].append(
                    f"Knoten {k + 1} ({fl(fremd)}) liegt auf der Linie {x} ({fl(wem)}) weniger als 1 mm "
                    f"neben dem Knoten {nachbar + 1}: das Teilstück wäre zu kurz – dort nicht verbunden.")
                continue
            kette.append(k)
            gruende.append(
                f"Linie {x} ({fl(wem)}) im Netz am Knoten {k + 1} geteilt (Knoten auf Linie): dort "
                f"{'schließt' if len(fremd) == 1 else 'schließen'} {fl(fremd)} an – gemeinsamer Netzknoten.")
        if len(kette) > 1:
            kette.append(b)
            ketten[x] = kette
            plan["geteilt"].update(wem)
            plan["meldungen"].extend(gruende)
    # Teilstuecke benennen: gibt es die Linie zwischen den zwei Knoten schon, ist sie es
    paar_linien: dict = {}
    for x in besitzer:
        ln = lines[x]
        if x not in ketten and gerade(ln) and len(ln.nodes) == 2:
            paar_linien.setdefault(frozenset(int(k) for k in ln.nodes), []).append(x)
    paar: dict = {}
    for x, kette in ketten.items():
        namen = []
        for i, (u, v) in enumerate(zip(kette[:-1], kette[1:])):
            key = frozenset((u, v))
            if key not in paar:
                vorhanden = paar_linien.get(key)
                if vorhanden:
                    paar[key] = vorhanden[0]
                    for y in vorhanden[1:]:      # Doppellinien zwischen denselben Knoten
                        umlegen[y] = vorhanden[0]
                else:
                    name = f"{x} (Teil {i + 1})"
                    while name in lines or name in plan["teilstuecke"]:
                        name += "'"
                    plan["teilstuecke"][name] = Line(name=name, nodes=[int(u), int(v)], typ="polyline")
                    paar[key] = name
            namen.append(paar[key])
        ersatz[x] = namen

    # ---- (b) Linie in Flaeche -------------------------------------------
    geo = _Netzgeometrie(model, plan["teilstuecke"])
    glines = geo.lines
    lage: dict = {}
    for f in schalen:
        vr = ersetzt(f.linien)
        vl = [ersetzt(loch) for loch in (f.oeffnungen or [])]
        ringe3 = []
        for i, namen in enumerate([vr] + vl):
            st = _randstuecke(geo, namen)
            pts = []
            for name, kn in st or []:
                ln = glines[name]
                if gerade(ln):
                    pts.extend(X[int(k)] for k in kn[:-1])
                    continue
                P = M3._linienpunkte(geo, name, 16)
                if len(P) < 2:
                    pts = []
                    break
                if np.linalg.norm(P[0] - X[int(kn[0])]) > np.linalg.norm(P[-1] - X[int(kn[0])]):
                    P = P[::-1]
                pts.extend(P[:-1])
            if len(pts) >= 3:
                ringe3.append(np.asarray(pts, float))
            elif i == 0:
                break                          # kein geschlossener Aussenrand
        if not ringe3:
            continue
        alle = np.vstack(ringe3)
        c, e1, e2, n, abw = M3.ausgleichsebene(alle)
        gr = float(np.linalg.norm(alle - c, axis=1).max())
        namen_v = set(vr) | {y for loch in vl for y in loch}
        lage[f.name] = {
            "eben": gr > 0 and abw <= M3.EBENHEIT * gr, "c": c, "e1": e1, "e2": e2, "n": n, "gr": gr,
            "namen": namen_v,
            "knoten": {int(k) for y in namen_v if y in glines for k in glines[y].nodes},
            "ringe": [np.stack([(R - c) @ e1, (R - c) @ e2], axis=1) for R in ringe3],
            "lo": alle.min(axis=0), "hi": alle.max(axis=0)}
    stuecke: dict = {}                        # gerades Stueck -> (Knoten, Knoten, Flaechen)
    for f in schalen:
        for x in dict.fromkeys(ersetzt(linien_von(f))):
            ln = glines.get(x)
            if ln is None or not gerade(ln) or len(ln.nodes) != 2:
                continue
            if not all(0 <= int(k) < nn for k in ln.nodes):
                continue
            stuecke.setdefault(x, (int(ln.nodes[0]), int(ln.nodes[1]), []))[2].append(f.name)
    namen_s = list(stuecke)
    PA = X[[stuecke[x][0] for x in namen_s]] if namen_s else np.zeros((0, 3))
    PB = X[[stuecke[x][1] for x in namen_s]] if namen_s else np.zeros((0, 3))
    proben = np.linspace(0.1, 0.9, 9)[:, None]
    for fa in schalen:
        la = lage.get(fa.name)
        if la is None or not la["eben"] or not namen_s:
            continue
        da = (PA - la["c"]) @ la["n"]
        db = (PB - la["c"]) @ la["n"]
        nah = (np.abs(da) < TEIL_FANG) & (np.abs(db) < TEIL_FANG)
        nah &= np.all(np.maximum(PA, PB) >= la["lo"] - TEIL_FANG, axis=1)
        nah &= np.all(np.minimum(PA, PB) <= la["hi"] + TEIL_FANG, axis=1)
        tol = STUETZKNOTEN_TOL * la["gr"] + 1e-9
        ringe = la["ringe"]
        angenommen = []
        for i in np.nonzero(nah)[0]:
            x = namen_s[int(i)]
            if x in la["namen"]:
                continue
            u, v, wem = stuecke[x]
            fremd = [w for w in wem if w != fa.name
                     and not (w in lage and lage[w]["eben"]
                              and abs(float(lage[w]["n"] @ la["n"])) >= 0.999)]
            if not fremd:
                continue
            u2 = np.array([(X[u] - la["c"]) @ la["e1"], (X[u] - la["c"]) @ la["e2"]])
            v2 = np.array([(X[v] - la["c"]) @ la["e1"], (X[v] - la["c"]) @ la["e2"]])
            S = u2 + proben * (v2 - u2)
            drin = M3._in_polygon_2d(S, ringe)
            ds = M3.randstreckenabstand(S, ringe)
            if not np.any(drin & (ds > tol)):
                continue                       # ausserhalb oder auf dem Rand: keine Stelle
            stelle([fa.name], fremd)
            wo = f"Linie {x} ({fl(fremd)}) in der Fläche {fa.name}"
            neben = max(abs(float(da[i])), abs(float(db[i])))
            if neben > tol:
                plan["warnungen"].append(
                    f"{wo}: sie liegt bis {mm(neben)} mm neben der Ebene der Fläche – schleifend, über "
                    f"der Toleranz von {mm(tol)} mm: dort nicht verbunden.")
                continue
            grund = ""
            for k, k2 in ((u, u2), (v, v2)):
                if k in la["knoten"]:
                    continue
                if float(M3.randstreckenabstand(k2[None, :], ringe)[0]) <= TEIL_FANG:
                    grund = (f"ihr Ende am Knoten {k + 1} liegt auf dem Rand der Fläche, der dort "
                             "keinen Knoten hat")
                elif not bool(M3._in_polygon_2d(k2[None, :], ringe)[0]):
                    grund = "sie liegt nur teilweise in der Fläche"
                if grund:
                    break
            if not grund:
                kreuzt = any(_strecken_kreuzen(u2, v2, R[j], R[(j + 1) % len(R)])
                             for R in ringe for j in range(len(R)))
                if kreuzt or not np.all(drin) or np.any(ds <= tol):
                    grund = "sie liegt nur teilweise in der Fläche (sie kreuzt oder berührt den Rand ohne Knoten)"
            if not grund:
                for y, a2, b2 in angenommen:
                    if _strecken_kreuzen(u2, v2, a2, b2) or _strecken_kreuzen(a2, b2, u2, v2):
                        grund = f"sie kreuzt die Zwangslinie {y} ohne gemeinsamen Knoten"
                        break
            if grund:
                plan["warnungen"].append(f"{wo}: {grund} – dort nicht verbunden.")
                continue
            angenommen.append((x, u2, v2))
            plan["meldungen"].append(
                f"Fläche {fa.name}: Linie {x} ({fl(fremd)}) liegt in der Fläche und wird im Netz zur "
                "Zwangslinie (Linie in Fläche) – gemeinsame Netzknoten.")
        if angenommen:
            plan["zwang"][fa.name] = [x for x, _a, _b in angenommen]
            plan["geteilt"].add(fa.name)
    plan["aktiv"] = bool(ersatz or umlegen or plan["zwang"])
    return plan


def flaechen_teilstellen(model: Model) -> list:
    """Namen der Schalenflaechen, die der Vernetzer an einem fremden Knoten
    oder an einer fremden Linie im Netz teilt (:func:`_teilplan`)."""
    schalen = [f for f in (getattr(model, "flaechen", None) or {}).values() if _ist_schale(model, f)]
    return sorted(_teilplan(model, schalen)["geteilt"])


def _gruppe_und_plan(model: Model, flaechen) -> tuple:
    """(gemeinsam zu vernetzende Schalenflaechen, Teilplan) - siehe
    :func:`gemeinsame_schalen` und :func:`_teilplan`."""
    schalen = [f for f in flaechen if _ist_schale(model, f)]
    plan = _teilplan(model, schalen)
    ersetzt = plan["ersetzt"]

    def alle_linien(f):
        return (ersetzt(f.linien) + [y for loch in (f.oeffnungen or []) for y in ersetzt(loch)]
                + list(plan["zwang"].get(f.name, [])))
    zahl: dict = {}
    for f in schalen:
        for x in set(alle_linien(f)):
            zahl[x] = zahl.get(x, 0) + 1
    gruppe = [f for f in schalen
              if any(zahl.get(x, 0) > 1 for x in alle_linien(f)) or len(f.linien or []) == 3
              or any(f.oeffnungen or []) or f.name in plan["beteiligt"]]
    return gruppe, plan


def gemeinsame_schalen(model: Model, flaechen) -> list:
    """Die Schalenflaechen, die gemeinsam vernetzt werden muessen.

    Das sind alle, die eine Randlinie (auch eine Oeffnungslinie) mit einer
    anderen Schalenflaeche teilen, und alle mit genau drei Randlinien.
    Entscheidung des Anwenders vom 09.11.2026: „flächen mit gemeinsamer
    randlinie sollen verbunden sein“ und „fläche mit drei randlinien soll
    sich an gewünschter netzgröße orientieren“. Bis dahin legte jede Flaeche
    auf ihren Randlinien eigene Zwischenknoten an: zwei Flaechen hingen nur an
    den Linienenden zusammen (Platte 4 m aus zwei Flaechen: 398 statt 149,6 mm
    Durchbiegung), und eine Dreiecksflaeche wurde ein einziges Element.

    Dazu jede Flaeche mit Oeffnung (Befund A18 der Pruefagenten, 09.11.2026):
    mesh_flaeche kennt keine Oeffnungen und vernetzte eine einzelne Scheibe
    mit Kreisloch ueber den Aussenrand - das Loch war gefuellt (Netzflaeche
    4,0000 statt 3,9686 m2), am Lochrand keine Kerbspannung. Der freie Weg
    hier spart das Loch aus.

    Dazu jede Flaeche, die eine andere beruehrt, ohne eine Linie mit ihr zu
    teilen (Befund A19, Entscheidung vom 09.11.2026): ein fremder Knoten auf
    ihrer Randlinie oder eine fremde Linie in ihr - dort wird im Netz geteilt
    (:func:`_teilplan`), und die Flaechen beiderseits gehoeren zusammen."""
    return _gruppe_und_plan(model, flaechen)[0]


def unverbundene_schalenlinien(model: Model) -> list:
    """Gemeinsame Randlinien vernetzter Schalenflaechen, an denen die Netze
    nicht dieselben Knoten haben - ein Netz von vor dem 09.11.2026 (Vernetzer
    ohne gemeinsame Linienknoten) oder ein von Hand zusammengesetztes.

    Rueckgabe [(Linie, Flaeche A, Flaeche B, Knoten nur auf einer Seite), ...].
    Je Linie werden die Netzknoten auf ihr (Model.knoten_auf_linie) mit den
    Knoten jeder anliegenden Flaeche geschnitten; verbunden ist die Linie, wenn
    jede Flaeche dieselben Linienknoten traegt. Entscheidung des Anwenders vom
    09.11.2026: alte, unverbundene Schalennetze beim Oeffnen erkennen und zum
    Neuvernetzen auffordern."""
    schalen = [f for f in (getattr(model, "flaechen", None) or {}).values()
               if _ist_schale(model, f) and f.elemente]
    if len(schalen) < 2 or not len(model.elements):
        return []
    knoten_von = {}
    an_linie: dict = {}
    for f in schalen:
        knoten_von[f.name] = {int(k) for e in f.elemente if 0 <= int(e) < len(model.elements)
                              for k in model.elements[int(e)].nodes}
        for x in set(list(f.linien or []) + [y for loch in (f.oeffnungen or []) for y in loch]):
            an_linie.setdefault(x, []).append(f.name)
    out = []
    cache: dict = {}
    X = model.nodes
    for linie, namen in an_linie.items():
        if len(namen) < 2 or linie not in model.lines:
            continue
        ln = model.lines[linie]
        kand = sorted(set().union(*(knoten_von[n] for n in namen)))
        if str(ln.typ or "") in GERADE_LINIEN and len(ln.nodes) == 2 and kand:
            # gerade Linie: Abstand zur Strecke, nur unter den Knoten der anliegenden
            # Flaechen (knoten_auf_linie tastet fein ab und sucht im ganzen Modell -
            # am Stemmtor 167 s fuer 591 Linien)
            p, q = X[int(ln.nodes[0])], X[int(ln.nodes[1])]
            d = q - p
            L2 = float(d @ d)
            if L2 <= 0:
                continue
            K = np.asarray(kand, int)
            t = (X[K] - p) @ d / L2
            r = np.linalg.norm(X[K] - (p + t[:, None] * d), axis=1)
            tol = STUETZKNOTEN_TOL * np.sqrt(L2) + 1e-12
            auf = {int(k) for k in K[(r <= tol) & (t >= -1e-9) & (t <= 1 + 1e-9)]}
        else:
            try:
                auf = {int(k) for k, _s in model.knoten_auf_linie(linie, cache=cache)}
            except Exception:               # noqa: BLE001 - eine Linie ohne Kurve sperrt nichts
                continue
        seiten = [(n, auf & knoten_von[n]) for n in namen]
        a, ka = seiten[0]
        for b, kb in seiten[1:]:
            if ka != kb:
                out.append((linie, a, b, len(ka ^ kb)))
    return out


def _h_eigene_teilung(model: Model, f) -> float:
    """Kantenlaenge aus der eigenen Teilung der Flaeche (Netzdichte aus)."""
    from .netzdichte import _seitenlaengen
    L = _seitenlaengen(model, f)
    t = list(f.teilung or [])
    if L is None or len(t) < 2 or min(t) < 1:
        return 0.0
    return min(L[0] / t[0], L[1] / t[1])


def schalen_gemeinsam_vernetzen(model: Model, flaechen, hs: dict = None, log: list = None,
                                kanten: dict = None, ordnung: int = 0,
                                dreiecke: bool = None) -> dict:
    """Schalenflaechen mit gemeinsamen Randlinien zusammenhaengend vernetzen.

    Jede Randlinie bekommt **eine** Teilung (mesher3d.Linienteilung) und ihre
    Zwischenknoten nur einmal; alle Flaechen an der Linie benutzen dieselben
    Knoten. Die Teilung einer Linie folgt der feinsten Kantenlaenge der
    Flaechen an ihr (``hs``: Name -> h aus der Netzdichte). Eine Flaeche aus
    vier Randlinien mit gleich geteilten Gegenseiten wird abgebildet
    vernetzt (Vierecke wie bisher); jede andere - drei Randlinien, mehr als
    vier, Oeffnungen - frei mit Dreiecken in ihrer Kantenlaenge
    (mesher3d.flaechennetz). Rueckgabe {Flaechenname: Elementnummern}; nur die
    Flaechen aus :func:`gemeinsame_schalen` werden hier vernetzt, alle
    anderen bleiben bei :func:`mesh_flaeche`.

    Beruehren sich Flaechen, ohne eine Linie zu teilen, wird **im Netz**
    geteilt (:func:`_teilplan`, Befund A19, 09.11.2026): die Randlinie am
    fremden Knoten, die Flaeche an der fremden Linie (Zwangslinie). So eine
    Flaeche wird frei mit Dreiecken vernetzt. Die Linien und Flaechen des
    Modells bleiben, wie sie sind; jede Stelle steht im Protokoll, und was
    sich nicht sauber teilen laesst, steht dort mit dem Grund als Warnung."""
    import copy
    from . import mesher3d as M3
    from .importers import _common as C
    gruppe, plan = _gruppe_und_plan(model, flaechen)
    if not gruppe:
        return {}
    # Die Geometrie, wie das Netz sie sieht: Teilstuecke statt geteilter Linien
    geo = _Netzgeometrie(model, plan["teilstuecke"]) if plan["aktiv"] else model
    sicht: dict = {}
    for f in gruppe:
        v = f
        if plan["aktiv"]:
            v = copy.copy(f)
            v.linien = plan["ersetzt"](f.linien)
            v.oeffnungen = [plan["ersetzt"](loch) for loch in (f.oeffnungen or [])]
        sicht[f.name] = v
    zwang = plan["zwang"]
    for zeile in plan["meldungen"]:
        C.say(log, zeile)
    for zeile in plan["warnungen"]:
        C.warn(log, zeile)
    hs = dict(hs or {})
    kanten = {} if kanten is None else kanten
    if dreiecke is None:
        dreiecke = int(getattr(getattr(model, "netz", None), "form", 2) or 0) == 0
    ordnung = netz_ordnung(model, ordnung)
    ueber = bool(getattr(getattr(model, "netz", None), "teilung_uebersteuern", True))
    hf: dict = {}
    for f in gruppe:
        h = 0.0 if ueber else _h_eigene_teilung(model, f)
        if h <= 0:
            h = float(hs.get(f.name, 0.0) or 0.0)
        if h <= 0:
            from .netzdichte import elementlaenge
            h = float(elementlaenge(model, model.netz, f)["h"])
        hf[f.name] = max(h, 1e-6)
    h_lin: dict = {}
    for f in gruppe:
        v = sicht[f.name]
        for x in (list(v.linien or []) + [y for loch in (v.oeffnungen or []) for y in loch]
                  + list(zwang.get(f.name, []))):
            h_lin[x] = min(h_lin.get(x, hf[f.name]), hf[f.name])
    namen_f = frozenset(f.name for f in gruppe)
    teil = M3.Linienteilung(geo, [sicht[f.name] for f in gruppe], max(hf.values()), h_linien=h_lin,
                            h_flaechen=hf, gemeinsam=(namen_f, frozenset(h_lin)), eben_binden=True)
    for erste, k, grenze in getattr(teil, "gekappt", []) or []:
        C.warn(log, f"Linie {erste} und ihre Gegenseiten: {k} Abschnitte gefordert, auf {grenze} begrenzt")

    def abgebildet_moeglich(f) -> bool:
        if f.name in plan["geteilt"]:
            return False                     # im Netz geteilt: frei, mit Zwangsknoten
        f = sicht[f.name]
        if len(f.linien or []) != 4 or f.oeffnungen:
            return False
        st = M3.seiten_im_umlauf(geo, f.linien)
        if not st or len(st) != 4:
            return False
        n = [teil.n.get(x, 1) for x, _k in st]
        return n[0] == n[2] and n[1] == n[3]

    # 1. Freie Netze in der Ebene - fehlt eine Randstrecke, wird ihre Linie
    #    nachgeteilt, und zwar fuer alle Flaechen daran (darum neu fuer alle)
    frei: dict = {}
    zwang_offen: dict = {}
    for _runde in range(4):
        frei, fehlt_alle, zwang_offen = {}, set(), {}
        for f in gruppe:
            if abgebildet_moeglich(f):
                continue
            zw = zwang.get(f.name)
            if zw:
                P, T, meldung, fehlt, kenn = M3.flaechennetz(geo, sicht[f.name], teil, zwang=zw)
                zwang_offen[f.name] = [x for x in (fehlt or []) if x in zw]
            else:
                P, T, meldung, fehlt, kenn = M3.flaechennetz(geo, sicht[f.name], teil)
            frei[f.name] = (P, T, meldung, kenn)
            fehlt_alle.update(fehlt or [])
        if not fehlt_alle or not teil.verfeinern(sorted(fehlt_alle)):
            break
    # 2. Knoten: jede Kennung (Linienpunkt oder Linienende) nur einmal
    knoten_von: dict = {}

    def knoten(kennung, p):
        if kennung is None:
            return int(model.add_node(*np.asarray(p, float)))
        if kennung[0] == "K":
            return int(kennung[1])
        if kennung not in knoten_von:
            knoten_von[kennung] = int(model.add_node(*np.asarray(p, float)))
        return knoten_von[kennung]

    def mitten(ring_ids, herkunft):
        """Quadratisch: Kantenmitten auf krummen Randlinien auf die Kurve."""
        if ordnung < 2:
            return
        n = len(ring_ids)
        i = 0
        while i < n:
            j = i
            while j < n and herkunft[j] == herkunft[i]:
                j += 1
            kette = [ring_ids[k % n] for k in range(i, j + 1)]
            linie = herkunft[i]
            _randmitten(model, kette, [int(x) for x in geo.lines[linie].nodes], linie, kanten)
            i = j

    out: dict = {}
    n_vier = n_drei = 0
    for f in gruppe:
        mat = f.material or C.ensure_material(model, log=log)
        prop = f.dicke or C.ensure_shell_prop(model, log=log)
        zug = M3._linienzug(teil, geo, sicht[f.name].linien or [])
        if zug is None:
            C.warn(log, f"Fläche {f.name}: die Linien bilden keinen geschlossenen Rand.")
            f.elemente = []
            continue
        R, herkunft, kenn = zug
        ring = [knoten(k, p) for k, p in zip(kenn, R)]
        # Normale aus dem Umlauf (Newell) - die freien Dreiecke drehen wie er
        nrm = np.zeros(3)
        for i in range(len(R)):
            nrm += np.cross(R[i], R[(i + 1) % len(R)])
        mitten(ring, herkunft)
        els = []
        if f.name not in frei:
            # abgebildet: die vier Randlinien als Ketten im Umlauf
            grenzen = [0] + [i for i in range(1, len(ring)) if herkunft[i] != herkunft[i - 1]]
            ketten = []
            for s in range(4):
                a = grenzen[s]
                b = grenzen[s + 1] if s < 3 else len(ring)
                ketten.append([ring[k % len(ring)] for k in range(a, b + 1)])
            ids = transfinit(model, ketten[0], ketten[2][::-1], ketten[3][::-1], ketten[1])
            for i in range(ids.shape[0] - 1):
                for j in range(ids.shape[1] - 1):
                    els.extend(_flaechenelemente(model, [int(ids[i, j]), int(ids[i + 1, j]),
                                                         int(ids[i + 1, j + 1]), int(ids[i, j + 1])],
                                                 mat, prop, f.name, dreiecke, ordnung, kanten))
            n_vier += 1
            C.say(log, f"Fläche {f.name}: {len(els)} "
                       + ("Dreieckelemente" if dreiecke else "Viereckelemente")
                       + (" (quadratisch)" if ordnung >= 2 else "")
                       + f" ({ids.shape[0] - 1} x {ids.shape[1] - 1}), Randknoten gemeinsam mit den Nachbarflächen")
        else:
            P, T, meldung, kp = frei[f.name]
            if meldung or not len(T):
                C.warn(log, f"Fläche {f.name}: nicht vernetzt ({meldung or 'kein Netz in der Ebene'}).")
                f.elemente = []
                continue
            ids = [knoten(kp[i] if i < len(kp) else None, P[i]) for i in range(len(P))]
            X = model.nodes
            for t in T:
                a, b, c = ids[int(t[0])], ids[int(t[1])], ids[int(t[2])]
                if float(np.cross(X[b] - X[a], X[c] - X[a]) @ nrm) < 0:
                    b, c = c, b
                els.append(_dreieck(model, [a, b, c], mat, prop, f.name, ordnung, kanten))
            n_drei += 1
            C.say(log, f"Fläche {f.name}: {len(els)} Dreieckelemente"
                       + (" (quadratisch)" if ordnung >= 2 else "")
                       + f" frei vernetzt, h = {teil.h_fuer(f) * 1e3:.0f} mm, "
                       "Randknoten gemeinsam mit den Nachbarflächen")
            for x in zwang_offen.get(f.name, []):
                C.warn(log, f"Fläche {f.name}: die Zwangslinie {x} ist im Netz nicht durchgehend "
                            "Elementkante – dort nicht verbunden.")
        f.elemente = els
        out[f.name] = els
    C.say(log, f"{len(out)} Flächen mit gemeinsamen Randlinien zusammenhängend vernetzt "
               f"({n_vier} abgebildet, {n_drei} frei)")
    if plan["meldungen"]:
        C.say(log, f"{len(plan['meldungen'])} "
                   + ("Stelle" if len(plan["meldungen"]) == 1 else "Stellen")
                   + " ohne gemeinsame Linie im Netz verbunden (Knoten auf Linie, Linie in Fläche); "
                     "Knoten, Linien und Flächen des Modells bleiben unverändert.")
    return out


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
            teil, achsen = quader_teilung(model, koerper, order)
            # Eine Linienvorgabe (sweep.lagenvorgabe: Kanten, die Nachbarn
            # gehoeren) geht vor der eigenen Teilung - je Richtung dieselbe.
            vorgabe = getattr(model, "linienvorgabe", None) or {}
            richtungen = quader_richtungen(quader_kanten(model, koerper, order))
            vom_nachbarn = False
            for d in range(3):
                fest = [int(vorgabe[x]) for x in richtungen[d] if x in vorgabe]
                if fest:
                    vom_nachbarn = vom_nachbarn or max(fest) != teil[d]
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
            # in x, y, z angeben, wie die Teilung eingegeben wird (A14)
            xyz = [nx, ny, nz]
            if sorted(achsen) == [0, 1, 2]:
                for k_, a_ in enumerate(achsen):
                    xyz[a_] = (nx, ny, nz)[k_]
            zahl = f"{xyz[0]} x {xyz[1]} x {xyz[2]}"
            koerper.kommentar = f"{len(els)} Hexaeder (abgebildet, {zahl})"
            koerper.randtreue = 1.0
            koerper.netzgrund = ""
            koerper.netzkanten = []
            # Woher die Zahl kommt, steht dabei (Befund C3 der Pruefagenten,
            # 09.11.2026): der abgebildete Quader folgt seiner eigenen Teilung,
            # die Netzdichte (Ziellaenge) wirkt an ihm nicht - das Protokoll
            # kuendigte davor „≈ 3472 Elemente“ an, entstanden sind 64.
            C.say(log, f"Volumen {koerper.name}: {len(els)} Hexaeder"
                       + (" (quadratisch, 20 Knoten)" if ord_ >= 2 else "")
                       + f" ({zahl}) – abgebildeter Quader, geteilt nach der Teilung des Körpers"
                       + (" und der Teilung gemeinsamer Kanten" if vom_nachbarn else "")
                       + ", nicht nach der Netzdichte")
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


def quader_abgebildet(model: Model, koerper) -> bool:
    """Geht der Koerper in :func:`mesh_koerper` den ersten Weg - **abgebildeter
    Quader** (sechs Vierecke, acht Ecken, gerade Kanten, mit Rauminhalt)?

    Dann bestimmt seine eigene Teilung [nx, ny, nz] die Elementzahl, und die
    Netzdichte (Ziellaenge) wirkt an ihm nicht. Das Protokoll der Netzdichte
    fragt hier nach, damit es keine Elementzahl ankuendigt, die nicht entsteht
    (Befund C3 der Pruefagenten, 09.11.2026). Die Bedingungen sind dieselben
    wie dort; geaendert wird hier nichts."""
    if getattr(koerper, "ordnung", None) == 2:
        return False                    # tet10: freier Vernetzer (Anweisung V1)
    flaechen = [model.flaechen.get(x) for x in (koerper.flaechen or [])]
    if len(flaechen) != 6 or any(f is None for f in flaechen):
        return False
    try:
        ringe = [f.randknoten(model) for f in flaechen]
        knoten = {n for r in ringe for n in r}
        if len(knoten) != 8 or any(len(r) != 4 for r in ringe):
            return False
        from .importers.rfem6_db import _hex_order, _hex_volumen
        order = _hex_order(ringe)
        if not order or not _gerade_kanten(model, koerper, order):
            return False
        entartetes_volumen, _ohne = _entartungspruefung()
        X = model.nodes[order]
        return not entartetes_volumen(float(_hex_volumen(X)),
                                      float(np.linalg.norm(X.max(axis=0) - X.min(axis=0))))
    except Exception:                   # noqa: BLE001 - im Zweifel die alte Zeile
        return False


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
    „Prozesse" (Berechnung → Einstellungen → Gleichungslöser (Experte))."""
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


#: Befund A16 der Pruefagenten, Entscheidung des Anwenders vom 09.11.2026:
#: zwei Koerper mit je einer eigenen, deckungsgleichen Trennflaeche ohne
#: Kontaktbedingung werden dort als **eine** gemeinsame Flaeche vernetzt
#: (:func:`koerper_vernetzen`). False vernetzt wie bis zum 09.11.2026 - jede
#: Flaeche fuer sich, die Koerper haengen nur an den Randlinien zusammen.
TRENNFLAECHEN_ZUSAMMENLEGEN = True


def _kontakt_nennt_trennstelle(model: Model, fa: str, fb: str, ka: str, kb_: str) -> str:
    """Name der Kontaktbedingung, die die Trennstelle nennt - "" ohne.

    Genannt ist die Stelle, wenn eine Bedingung eine der beiden Flaechen
    fuehrt (freigegebene Flaechen oder Gegenflaechen) oder die beiden Koerper
    als geloesten Koerper und Gegenkoerper - die Eingabe nur mit Koerpern, die
    fugen.kontaktfuge_ausfuehren seit dem 09.11.2026 ausfuehrt (Befund A17).
    Eine in der Quelldatei deaktivierte Bedingung nennt die Stelle auch: was
    der Anwender als Fuge angelegt hat, wird nicht still zum Verbund."""
    for name, kb in (getattr(model, "kontaktbedingungen", None) or {}).items():
        fl = set(getattr(kb, "flaechennamen", None) or []) | set(getattr(kb, "gegenflaechen", None) or [])
        if fa in fl or fb in fl:
            return str(name)
        los = set(getattr(kb, "koerpernamen", None) or [])
        gegen = set(getattr(kb, "gegenkoerper", None) or [])
        if (ka in los and kb_ in gegen) or (kb_ in los and ka in gegen):
            return str(name)
    return ""


def trennstellen(model: Model) -> list:
    """Die Stellen, an denen zwei Koerper je eine **eigene** Flaeche ueber
    denselben Randlinien (und Oeffnungen) haben - deckungsgleiche
    Trennflaechen (Befund A16 der Pruefagenten, 09.11.2026).

    Je Stelle ein Woerterbuch: ``flaechen`` (fa, fb), ``koerper`` (ka, kb) -
    fa gehoert ka, fb gehoert kb -, ``kontakt`` (Name der Kontaktbedingung,
    die die Stelle nennt, sonst "") und ``hindernis`` (warum die beiden
    Flaechen nicht als eine vernetzt werden koennen, sonst ""). Dieselbe
    Liste lesen der Vernetzer (:func:`koerper_vernetzen`) und die Abnahme
    (diagnose._abnahme_deckungsgleiche_flaechen)."""
    koerper = getattr(model, "koerper", None) or {}
    flaechen = getattr(model, "flaechen", None) or {}
    if len(koerper) < 2:
        return []
    je_rand: dict = {}
    for k in koerper.values():
        for fn in dict.fromkeys(k.flaechen or []):
            f = flaechen.get(fn)
            if f is None or not (f.linien or []):
                continue
            rand = (frozenset(f.linien),
                    frozenset(frozenset(o) for o in (getattr(f, "oeffnungen", None) or [])))
            je_rand.setdefault(rand, []).append((fn, k.name))
    aus = []
    for liste in je_rand.values():
        if len({fn for fn, _k in liste}) < 2:
            continue
        for i, (fa, ka) in enumerate(liste):
            for fb, kb_ in liste[i + 1:]:
                if fa == fb or ka == kb_:
                    continue
                hindernis = ""
                if len(liste) != 2:
                    hindernis = (f"an der Stelle liegen {len(liste)} Körperflächen über denselben Randlinien, "
                                 "nicht zwei")
                else:
                    a, b = flaechen[fa], flaechen[fb]
                    if (a.typ or "eben") != (b.typ or "eben"):
                        hindernis = f"die Flächen haben verschiedene Geometriearten ({a.typ} und {b.typ})"
                    elif (set(getattr(a, "integrierte_knoten", None) or [])
                          != set(getattr(b, "integrierte_knoten", None) or [])
                          or set(getattr(a, "integrierte_linien", None) or [])
                          != set(getattr(b, "integrierte_linien", None) or [])):
                        hindernis = "die Flächen haben verschiedene integrierte Knoten oder Linien"
                    elif a.ecken and b.ecken and set(a.ecken) != set(b.ecken):
                        hindernis = "die Flächen haben verschiedene Eckknoten"
                aus.append({"flaechen": (fa, fb), "koerper": (ka, kb_),
                            "kontakt": _kontakt_nennt_trennstelle(model, fa, fb, ka, kb_),
                            "hindernis": hindernis})
    return aus


def trennstelle_knoten(model: Model, flaeche: str, koerper: str) -> set:
    """Die Knoten der Elementseiten des Koerpers, die auf der Flaeche liegen
    (aus ``Flaeche.randseiten``; Ecken und Seitenmitten)."""
    from .elements import solid as sl
    f = (getattr(model, "flaechen", None) or {}).get(flaeche)
    k = (getattr(model, "koerper", None) or {}).get(koerper)
    if f is None or k is None:
        return set()
    els = {int(e) for e in (k.elemente or [])}
    knoten: set = set()
    for e, seite in (f.randseiten or []):
        e = int(e)
        if e not in els or not 0 <= e < len(model.elements):
            continue
        el = model.elements[e]
        seiten = sl.FLAECHEN.get(el.typ)
        if seiten and 0 <= int(seite) < len(seiten):
            knoten.update(int(el.nodes[j]) for j in seiten[int(seite)])
    return knoten


def trennstelle_getrennt(model: Model, stelle: dict) -> bool:
    """Ist das **vorhandene** Netz an der Trennstelle getrennt - beide Koerper
    vernetzt, aber ihre Seiten auf den beiden Flaechen haben nicht dieselben
    Knoten? Ohne Netz in einem der beiden Koerper ist nichts getrennt."""
    (fa, fb), (ka, kb_) = stelle["flaechen"], stelle["koerper"]
    koerper = getattr(model, "koerper", None) or {}
    if not (getattr(koerper.get(ka), "elemente", None) and getattr(koerper.get(kb_), "elemente", None)):
        return False
    na = trennstelle_knoten(model, fa, ka)
    nb = trennstelle_knoten(model, fb, kb_)
    return not na or na != nb


def _trennstellen_des_laufs(model: Model, koerper: list, log: list = None) -> list:
    """Die Trennstellen, die dieser Lauf als eine gemeinsame Flaeche vernetzt:
    ohne Kontaktbedingung, ohne Hindernis, beide Koerper im Lauf. Was aus den
    letzten beiden Gruenden getrennt bleibt, steht im Protokoll."""
    from .importers import _common as C
    im_lauf = {k.name for k in koerper}
    aus = []
    belegt: set = set()
    for s in trennstellen(model):
        (fa, fb), (ka, kb_) = s["flaechen"], s["koerper"]
        if s["kontakt"] or not (ka in im_lauf or kb_ in im_lauf):
            continue
        grund = s["hindernis"]
        if not grund and not (ka in im_lauf and kb_ in im_lauf):
            fehlt = kb_ if ka in im_lauf else ka
            grund = f"der Körper {fehlt} wird in diesem Lauf nicht mit vernetzt"
        if not grund and (fa in belegt or fb in belegt):
            grund = "eine der beiden Flächen ist schon mit einer anderen zusammengelegt"
        if grund:
            C.warn(log, f"Trennfläche nicht zusammengelegt: Die Körper {ka} und {kb_} haben an derselben Stelle "
                        f"je eine eigene Fläche ({fa} und {fb}) ohne Kontaktbedingung, aber {grund}. Die Körper "
                        "bleiben dort nur über die Randlinien verbunden.")
            continue
        belegt.update((fa, fb))
        aus.append(s)
    return aus


def _randseiten_aufteilen(model: Model, stellen: list) -> None:
    """Nach dem Vernetzen als eine Flaeche: die Elementseiten des zweiten
    Koerpers stehen bei der Flaeche des ersten - sie gehen an seine eigene
    Flaeche zurueck, damit Lasten, Lager und Kontakt auf jeder der beiden
    Flaechen ihre Seiten finden wie bisher."""
    for s in stellen:
        (fa, fb), (_ka, kb_) = s["flaechen"], s["koerper"]
        a, b = model.flaechen.get(fa), model.flaechen.get(fb)
        k = model.koerper.get(kb_)
        if a is None or b is None or k is None:
            continue
        els = {int(e) for e in (k.elemente or [])}
        zu_b = [x for x in (a.randseiten or []) if int(x[0]) in els]
        if not zu_b:
            continue
        a.randseiten = [x for x in a.randseiten if int(x[0]) not in els]
        b.randseiten = [x for x in (b.randseiten or []) if int(x[0]) not in els] + zu_b


def koerper_vernetzen(model: Model, koerper, hs: dict = None, log: list = None,
                      cache: dict = None, workers: int = None, fortschritt=None,
                      gewicht: dict = None, ordnung: int = 0, stufen=None,
                      hs_fuer=None) -> dict:
    """Mehrere Volumenkoerper vernetzen - der gemeinsame Einstieg der
    Oberflaeche und von :func:`modell_vernetzen` (Befehlszeile, Skripte).

    Die Arbeit macht :func:`_koerper_vernetzen_grenze` (mit der Grenze in
    Unbekannten, dort beschrieben). Hier liegen die **deckungsgleichen
    Trennflaechen** (Befund A16 der Pruefagenten, Entscheidung des Anwenders
    vom 09.11.2026): haben zwei Koerper je eine eigene Flaeche ueber denselben
    Randlinien und nennt keine Kontaktbedingung die Stelle
    (:func:`trennstellen`), werden beide als **eine** gemeinsame Flaeche
    vernetzt - gemeinsame Knoten wie an einer Flaeche, die beiden Koerpern
    gehoert. Bis dahin teilten sich solche Koerper nur die Knoten der
    Randlinien (die Knoten im Flaecheninneren sind je Flaechenname gemeinsam),
    und zwei Wuerfel uebereinander unter Zug verformten sich 52 % mehr als ein
    Block.

    Die Geometrie bleibt, wie sie ist: nur fuer die Dauer des Vernetzens steht
    in der Flaechenliste des zweiten Koerpers die Flaeche des ersten - so
    greift alles, was es fuer gemeinsame Flaechen gibt (abgebildeter Quader,
    Sweep, freies Netz, Arbeitsprozesse, Netzkarten). Danach ist die Liste
    wieder die alte, und die Elementseiten des zweiten Koerpers stehen bei
    seiner eigenen Flaeche. Jede zusammengelegte Stelle steht mit Namen im
    Protokoll. Haben die beiden Seiten danach **nicht** dieselben Knoten
    (zwei abgebildete Quader mit verschiedener Teilung), wird das Netz
    zurueckgenommen und ohne diese Stelle neu erzeugt - getrennt wie bisher,
    und das Protokoll sagt, warum. ``aus["zusammengelegt"]`` nennt die
    Stellen als (Flaeche, Flaeche, Koerper, Koerper).
    """
    cache = {} if cache is None else cache
    koerper = list(koerper)

    def lauf():
        return _koerper_vernetzen_grenze(model, koerper, hs=hs, log=log, cache=cache, workers=workers,
                                         fortschritt=fortschritt, gewicht=gewicht, ordnung=ordnung,
                                         stufen=stufen, hs_fuer=hs_fuer)
    stellen = _trennstellen_des_laufs(model, koerper, log) if TRENNFLAECHEN_ZUSAMMENLEGEN else []
    if not stellen:
        return lauf()
    import copy
    from .importers import _common as C
    n_el0, n_kn0 = len(model.elements), int(model.nn)
    cache0 = copy.deepcopy(cache) if cache else {}
    while True:
        # Geometrie nur leihweise aendern: die Flaechenliste des zweiten Koerpers
        alt = []
        for s in stellen:
            fa, fb = s["flaechen"]
            k = model.koerper[s["koerper"][1]]
            alt.append((k, k.flaechen))
            k.flaechen = [fa if fn == fb else fn for fn in k.flaechen]
        try:
            aus = lauf()
        finally:
            for k, liste in reversed(alt):
                k.flaechen = liste
        _randseiten_aufteilen(model, stellen)
        if aus.get("abgebrochen"):
            return aus
        passt, passt_nicht = [], []
        for s in stellen:
            (fa, fb), (ka, kb_) = s["flaechen"], s["koerper"]
            if not (model.koerper[ka].elemente and model.koerper[kb_].elemente):
                continue                   # ein Koerper blieb ohne Netz: nichts zu verbinden
            na, nb = trennstelle_knoten(model, fa, ka), trennstelle_knoten(model, fb, kb_)
            if na and na == nb:
                passt.append((s, len(na)))
            else:
                passt_nicht.append(s)
                C.warn(log, f"Trennfläche nicht zusammengelegt: Die Netze der Körper {ka} und {kb_} passen an "
                            f"den Flächen {fa} und {fb} nicht zusammen (als eine Fläche vernetzt: {len(na)} "
                            f"Knoten von {ka}, {len(nb)} von {kb_}, {len(na & nb)} gemeinsam). Die Körper "
                            "werden dort getrennt vernetzt und bleiben nur über die Randlinien verbunden. "
                            "Für einen durchgehenden Verbund brauchen beide Körper an der Fläche dasselbe "
                            "Netz (gleiche Teilung, gleiche Elementart), für eine Fuge eine Kontaktbedingung "
                            "anlegen.")
        if not passt_nicht:
            break
        stellen = [s for s in stellen if s not in passt_nicht]
        _netz_zuruecksetzen(model, koerper, n_el0, n_kn0, cache, log)
        cache.update(copy.deepcopy(cache0))
        if not stellen:
            return lauf()
    for s, n in passt:
        (fa, fb), (ka, kb_) = s["flaechen"], s["koerper"]
        C.say(log, f"Trennfläche zusammengelegt: Die Körper {ka} und {kb_} haben an derselben Stelle je eine "
                   f"eigene Fläche ({fa} und {fb}) über denselben Randlinien, und keine Kontaktbedingung nennt "
                   f"sie. Beide Flächen sind als eine gemeinsame Fläche vernetzt ({n} gemeinsame Knoten); die "
                   "Geometrie bleibt unverändert. Für eine Fuge eine Kontaktbedingung anlegen.")
    aus["zusammengelegt"] = [(s["flaechen"][0], s["flaechen"][1], s["koerper"][0], s["koerper"][1])
                             for s, _n in passt]
    return aus


def _koerper_vernetzen_grenze(model: Model, koerper, hs: dict = None, log: list = None,
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
    Text in ``quelle``, nennt das Protokoll ihn neben der Stufennummer. Eine
    Stufe mit denselben Einstellungen wie die vorige (bis auf ``quelle``)
    wird uebersprungen und das Protokoll sagt es (seit 08.10.2026).

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

    def naechste_nach(k_, netz_):
        """(j, Einstellungen) der naechsten Stufe nach k_, die anders vernetzt
        als ``netz_`` - None ohne groebere. Eine Stufe mit denselben
        Einstellungen (bis auf den Text ``quelle``) baute dasselbe Netz noch
        einmal und wird uebersprungen (Anschluss von Fein, 08.10.2026: die
        Stufen 1 und 2 von Fein vergroebern nur die Boegen an Kontakt- und
        Lagerflaechen - ein Modell ohne solche Boegen haette sie umsonst bis
        zur Grenze vernetzt)."""
        j = k_ + 1
        n_ = stufen(j) if stufen is not None else None
        while n_ is not None and _gleich_vernetzt(n_, netz_):
            j += 1
            n_ = stufen(j)
        return j, n_

    def uebersprungen(k_, j_):
        if j_ <= k_ + 2:
            return "" if j_ <= k_ + 1 else (f"; Stufe {k_ + 1} ergäbe dasselbe Netz wie Stufe {k_} und wird "
                                            "übersprungen")
        bis = f"{k_ + 1} und {j_ - 1}" if j_ == k_ + 3 else f"{k_ + 1} bis {j_ - 1}"
        return f"; Stufen {bis} ergäben dasselbe Netz wie Stufe {k_} und werden übersprungen"
    try:
        while True:
            j, naechste = naechste_nach(k, netz_k)
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
                       + f". Das halbe Netz wird verworfen, vernetzt wird gröber mit {stufentext(j, naechste)}"
                       + uebersprungen(k, j) + ".")
            _netz_zuruecksetzen(model, koerper, n_el0, n_kn0, cache, log)
            k, netz_k = j, naechste
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


def _gleich_vernetzt(a, b) -> bool:
    """Vernetzen zwei Stufen der Grenze gleich - dieselben Netzeinstellungen
    bis auf den Text ``quelle``?"""
    from dataclasses import is_dataclass, replace
    if a is b:
        return True
    if not (is_dataclass(a) and is_dataclass(b)) or type(a) is not type(b):
        return False
    try:
        return replace(a, quelle="") == replace(b, quelle="")
    except (TypeError, ValueError):
        return False


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


def quader_teilung(model: Model, koerper, ecken: list) -> tuple:
    """(Teilung je Quaderrichtung, Achse je Richtung) eines abgebildeten
    Sechsflaechners mit den Eckknoten ``ecken`` (hex8-Reihenfolge, schon
    positiv orientiert) - die Richtungen wie in :func:`quader_richtungen`
    (Ecke 0->1, 0->3, 0->4).

    Die Teilung [nx, ny, nz] gilt in den globalen Achsen x, y, z (Befund A14
    der Pruefagenten, 09.11.2026). Die Richtungen des Quaders folgen der
    Reihenfolge seiner Flaechen; bis dahin bekam die erste nx, gleich wohin
    sie zeigte (Kragarm 2 x 0,1 x 0,2 m mit [2, 3, 5]: 5 x 3 x 2 Elemente,
    Durchbiegung 74 statt 97 % der Balkenloesung). Jetzt bekommt jede
    Richtung die Zahl der Achse, der sie am naechsten liegt; zeigen zwei
    Richtungen zur selben Achse (schiefer Quader), bleibt es bei der
    Reihenfolge. Vernetzer (:func:`mesh_koerper`) und Lagenvorgabe des Sweeps
    (sweep.lagenvorgabe) lesen die Teilung hier - bis zum 11.11.2026 las die
    Lagenvorgabe sie roh in der Flaechenreihenfolge und ueberschrieb die
    richtig zugeordnete Teilung (Befund 36: [2, 3, 5] wurde 2 x 2 x 4).
    """
    teil_xyz = (list(getattr(koerper, "teilung", None) or []) + [4, 4, 4])[:3]
    teil = list(teil_xyz)
    Xo = model.nodes[ecken]
    achsen = [int(np.argmax(np.abs(Xo[j] - Xo[0]))) for j in (1, 3, 4)]
    if sorted(achsen) == [0, 1, 2]:
        teil = [int(teil_xyz[a]) for a in achsen]
    return teil, achsen


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
            # Kandidaten fuers Loeschen sind nur die Knoten der alten Netze: ein Knoten
            # ohne Element, den dieses Netz nie trug (Geometriepunkt, Knoten aus einem
            # RFEM-Import), bleibt stehen - der Anwender entscheidet (16.10.2026,
            # Model.freie_knoten_entfernen)
            alte_knoten = {int(x) for e in alt if 0 <= int(e) < len(model.elements)
                           for x in model.elements[int(e)].nodes}
            model.elemente_loeschen(alt)
            # Die Knoten des alten Netzes gleich mit: sonst stehen sie als
            # „Knoten ohne Element" in der Abnahme und als Freiheitsgrade
            # ohne Steifigkeit im Gleichungssystem (Platte mit Bohrung nach
            # einer adaptiven Runde: 10 143 verwaiste Knoten, 20.09.2026).
            # Ohne den Zusatz in model.py (Arbeitskopie einer anderen Sitzung)
            # bleiben sie liegen - das Protokoll sagt es.
            if hasattr(model, "netzknoten_loeschen"):
                weg = model.netzknoten_loeschen(alte_knoten)
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
        gemeinsam = schalen_gemeinsam_vernetzen(model, flaechen, hs_alle, log, kanten)
        for f in flaechen:
            if f.name in gemeinsam:
                aus["elemente"] += len(gemeinsam[f.name])
                continue
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
        # Seitenmitten an Kontakt- und Lagerseiten binden und auf die Sehne
        # setzen (Q1, 08.10.2026) - im Netz, das die Ansicht zeigt
        t0 = time.time()
        from . import assemble as _asm
        try:
            _asm.mittelknoten_auf_sehne(model, log)
        except fugen.QuadratischeSeiten as ex:
            # Das Netz bleibt; die Rechnung bricht an derselben Stelle laut ab
            C.warn(log, f"Seitenmitten: {ex}")
        zeiten["Seitenmitten binden"] = time.time() - t0
    finally:
        for f in flaechen:
            if eigene_teilung.get(f.name):
                f.teilung = eigene_teilung[f.name]
    aus["zeiten"] = zeiten
    aus["unbekannte"] = unbekannte(model)
    # Das Netz merkt sich seine Einstellung (statik3d.netzhinweis); ein
    # abgebrochener Lauf hat kein vollstaendiges Netz, an dem sie gilt
    if aus["elemente"] and not aus["abgebrochen"]:
        from . import netzhinweis as _nh
        _nh.merken(model)
    lang = sorted(((k, v) for k, v in zeiten.items() if v >= 0.05), key=lambda x: -x[1])
    C.say(log, f"Vernetzt: {aus['elemente']} Elemente in {sum(zeiten.values()):.1f} s"
               + (f" auf {aus['prozesse']} Prozessen" if aus["prozesse"] > 1 else "")
               + (" - abgebrochen" if aus["abgebrochen"] else "")
               + ("; davon " + ", ".join(f"{k} {v:.1f} s" for k, v in lang) if lang else ""))
    return aus
