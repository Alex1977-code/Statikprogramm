"""Darstellung des Modells und der Ergebnisse im 3D-Viewport (pyvista)."""
from __future__ import annotations

import numpy as np
import pyvista as pv

from ..model import Model, NDOF
from ..elements import beam3d as bm
from .. import mesher

VTK_LINE, VTK_TRI, VTK_QUAD, VTK_TETRA, VTK_HEX, VTK_TET10 = 3, 5, 9, 10, 12, 24

CELL_MAP = {
    "beam": (VTK_LINE, 2), "truss": (VTK_LINE, 2),
    "shell3": (VTK_TRI, 3), "shell4": (VTK_QUAD, 4),
    "tet4": (VTK_TETRA, 4), "tet10": (VTK_TET10, 10), "hex8": (VTK_HEX, 8),
}

STATUS_COLOR = {"offen": "#9e9e9e", "Kontakt": "#1565c0", "Haften": "#2e7d32", "Gleiten": "#e65100"}

#: Farben der Modellsymbole
FARBE_KNOTEN = "#2f4f6f"
FARBE_KNOTEN_FREI = "#e07000"      # Knoten, der (noch) an keinem Element haengt
FARBE_LAGER = "#207020"
FARBE_LINIENLAGER = "#1f6f4f"
FARBE_FLAECHENLAGER = "#2a7f9f"
FARBE_KONTAKT = "#c8a000"

#: Darstellungsarten des Viewports: Name -> (Zeichen, Erklaerung)
DARSTELLUNGEN = {
    "Voll": ("■", "gefuellte Flaechen"),
    "Transparent": ("◧", "durchscheinend - man sieht die innen liegenden Teile"),
    "Hidden-Line": ("◫", "weisse Flaechen mit dunklen Kanten, wie eine Zeichnung"),
    "Drahtmodell": ("▦", "nur die Kanten"),
}


def darstellung(modus: str, netz: bool, farbig: bool = False) -> dict:
    """Angaben fuer ``add_mesh`` zu einer Darstellungsart.

    ``netz`` schaltet die Elementkanten (das FE-Netz) zu, ``farbig`` sagt, dass
    der Aufrufer eine Farbskala legt - dann darf hier keine feste Farbe stehen.
    """
    if modus == "Drahtmodell":
        return {"style": "wireframe", "line_width": 2}
    if modus == "Transparent":
        return {"opacity": 0.35, "show_edges": netz}
    if modus == "Hidden-Line":
        d = {"show_edges": True, "edge_color": "#202020", "line_width": 2,
             "lighting": False}
        if not farbig:
            d["color"] = "#ffffff"
        return d
    return {"show_edges": netz}


def unbelegte_knoten(model: Model) -> np.ndarray:
    """Knoten, die an keinem Element haengen (nur gesetzte Punkte)."""
    getragen = np.zeros(model.nn, bool)
    for e in model.elements:
        idx = [int(i) for i in e.nodes if 0 <= int(i) < model.nn]
        if idx:
            getragen[idx] = True
    return np.flatnonzero(~getragen)


#: Anteil freier Knoten, ab dem die Hervorhebung sinnlos wird
FREI_ANTEIL = 0.25


def add_nodes(plotter, model: Model, groesse: float = 1.0):
    """Alle gesetzten Knoten als Punkte zeichnen.

    Ein eben gesetzter Knoten haengt an keinem Element und war darum bisher
    im Viewport gar nicht zu sehen - das Modell wuchs unsichtbar. Solche
    Knoten bekommen hier eine eigene Farbe und einen groesseren Punkt, damit
    man beim Modellieren sieht, wo man schon war.

    Die Hervorhebung soll den **einen vergessenen** Knoten zeigen. In einem aus
    RFEM uebernommenen Modell haengen fast alle Knoten an Flaechen und Volumen
    statt an Elementen; waeren sie alle orange, uebertoente die Markierung das
    ganze Bauteil und sagte nichts mehr. Ueberschreiten die freien Knoten den
    Anteil ``FREI_ANTEIL``, werden darum alle Knoten gleich gezeichnet.
    """
    if model.nn == 0:
        return
    frei = unbelegte_knoten(model)
    d = max(3.0, 7.0 * float(groesse))
    if len(frei) > FREI_ANTEIL * model.nn:
        plotter.add_points(model.nodes, color=FARBE_KNOTEN, point_size=d,
                           render_points_as_spheres=True, name="knoten")
        return
    fest = np.setdiff1d(np.arange(model.nn), frei, assume_unique=False)
    if len(fest):
        plotter.add_points(model.nodes[fest], color=FARBE_KNOTEN, point_size=d,
                           render_points_as_spheres=True, name="knoten")
    if len(frei):
        plotter.add_points(model.nodes[frei], color=FARBE_KNOTEN_FREI,
                           point_size=d + 4, render_points_as_spheres=True,
                           name="knoten_frei")


def polygon_flaeche(punkte) -> float:
    """Flaeche eines ebenen Polygons im Raum (Newell-Formel)."""
    P = np.asarray(punkte, float)
    if len(P) < 3:
        return 0.0
    n = np.zeros(3)
    for a, b in zip(P, np.roll(P, -1, axis=0)):
        n += np.cross(a, b)
    return float(np.linalg.norm(n)) / 2.0


def add_linien(plotter, model: Model, hervor: list = None):
    """Die Linien des Modells zeichnen.

    Linien sind Geometrie, keine Elemente - sie wurden bisher gar nicht
    dargestellt. In einem aus RFEM uebernommenen Modell besteht die Geometrie
    fast nur aus Linien; ohne sie sieht man ein leeres Bild und haelt den
    Import fuer gescheitert.
    """
    linien = getattr(model, "lines", {}) or {}
    if not linien:
        return
    hervor = set(hervor or [])
    pts, zellen = [], []
    for name, ln in linien.items():
        if name in hervor:
            continue
        idx = [int(n) for n in ln.nodes if 0 <= int(n) < model.nn]
        if len(idx) < 2:
            continue
        basis = len(pts)
        pts.extend(model.nodes[idx])
        for i in range(len(idx) - 1):
            zellen.extend([2, basis + i, basis + i + 1])
    if pts:
        plotter.add_mesh(pv.PolyData(np.asarray(pts, float), lines=np.asarray(zellen)),
                         color=FARBE_LINIE, line_width=2, name="linien")


FARBE_LINIE = "#7a8a99"


def add_geometrie(plotter, model: Model, groesse: float = 1.0, raender: dict = None):
    """Flaechen und Volumenkoerper zeichnen, die **noch nicht vernetzt** sind.

    Ein Objekt, das man nicht sieht, kann man auch nicht anklicken. Eine eben
    aus Linien erzeugte Flaeche traegt noch keine Elemente; sie wird darum als
    durchscheinendes Polygon gezeichnet, ein noch nicht vernetzter
    Volumenkoerper zusaetzlich mit farbigen Randkanten.

    **Alles in je einem Netz**: ein aus RFEM uebernommenes Volumenmodell hat
    leicht ueber tausend Flaechen. Je Flaeche ein eigener Darsteller braucht
    Minuten und macht die Ansicht unbedienbar; gebuendelt sind es zwei.
    ``raender`` nimmt bereits berechnete Randpolygone entgegen
    ({Flaechenname: [Knoten]}), damit sie nicht zweimal ermittelt werden.
    """
    flaechen = getattr(model, "flaechen", {}) or {}
    if not flaechen:
        return
    raender = raender if raender is not None else {}

    def ring_von(name, f):
        r = raender.get(name)
        if r is None:
            r = f.randknoten(model)
            raender[name] = r
        return r

    pts: list = []
    faces: list = []
    for name, f in flaechen.items():
        if f.elemente:
            continue
        ring = ring_von(name, f)
        if len(ring) < 3:
            continue
        basis = len(pts)
        pts.extend(model.nodes[ring])
        faces.append(len(ring))
        faces.extend(range(basis, basis + len(ring)))
    if pts:
        plotter.add_mesh(pv.PolyData(np.asarray(pts, float), faces=np.asarray(faces)),
                         color="#7fb3d5", opacity=0.45, show_edges=True,
                         edge_color="#20638f", line_width=1, name="geo_flaechen")
    # Randkanten der noch nicht vernetzten Volumenkoerper - ebenfalls gebuendelt
    kpts: list = []
    klines: list = []
    for k in (getattr(model, "koerper", {}) or {}).values():
        if k.elemente:
            continue
        for fname in k.flaechen:
            f = flaechen.get(fname)
            if f is None or f.elemente:
                continue
            ring = ring_von(fname, f)
            if len(ring) < 3:
                continue
            basis = len(kpts)
            kpts.extend(model.nodes[ring + [ring[0]]])
            for i in range(len(ring)):
                klines.extend([2, basis + i, basis + i + 1])
    if kpts:
        plotter.add_mesh(pv.PolyData(np.asarray(kpts, float),
                                     lines=np.asarray(klines)),
                         color="#8e44ad", line_width=2, name="geo_volumen")


def line_at(model: Model, punkt, size: float):
    """Name der Linie, die dem Punkt am naechsten liegt - oder None."""
    if punkt is None or not model.lines:
        return None
    p = np.asarray(punkt, float).ravel()[:3]
    tol = 0.03 * size
    best, bestd = None, None
    for name, ln in model.lines.items():
        idx = [int(n) for n in ln.nodes if 0 <= int(n) < model.nn]
        if len(idx) < 2:
            continue
        X = model.nodes[idx]
        for a, b in zip(X[:-1], X[1:]):
            d = b - a
            L2 = float(d @ d)
            t = 0.0 if L2 <= 0 else max(0.0, min(1.0, float((p - a) @ d) / L2))
            dist = float(np.linalg.norm(p - (a + t * d)))
            if dist <= tol and (bestd is None or dist < bestd):
                best, bestd = name, dist
    return best


def element_at(model: Model, punkt, typen=None):
    """Nummer des Elements, dessen Mittelpunkt dem Punkt am naechsten liegt."""
    if punkt is None or not model.elements:
        return None
    p = np.asarray(punkt, float).ravel()[:3]
    best, bestd = None, None
    for i, e in enumerate(model.elements):
        if typen and e.typ not in typen:
            continue
        idx = [int(n) for n in e.nodes if 0 <= int(n) < model.nn]
        if not idx:
            continue
        d = float(np.linalg.norm(model.nodes[idx].mean(axis=0) - p))
        if bestd is None or d < bestd:
            best, bestd = i, d
    return best


def flaeche_at(model: Model, punkt, size: float):
    """Name der Flaeche unter dem Zeiger - vernetzt oder nicht."""
    el = element_at(model, punkt, ("shell3", "shell4"))
    if el is not None:
        for name, f in (getattr(model, "flaechen", {}) or {}).items():
            if el in (f.elemente or []):
                return name
        g = getattr(model.elements[el], "group", "")
        if g in (getattr(model, "flaechen", {}) or {}):
            return g
    # noch nicht vernetzt: ueber den Schwerpunkt des Randpolygons
    if punkt is None:
        return None
    p = np.asarray(punkt, float).ravel()[:3]
    best, bestd = None, None
    for name, f in (getattr(model, "flaechen", {}) or {}).items():
        ring = f.randknoten(model)
        if len(ring) < 3:
            continue
        X = model.nodes[ring]
        d = float(np.linalg.norm(X.mean(axis=0) - p))
        r = float(np.linalg.norm(X - X.mean(axis=0), axis=1).max())
        if d <= max(r, 0.02 * size) and (bestd is None or d < bestd):
            best, bestd = name, d
    return best


def koerper_at(model: Model, punkt, size: float):
    """Name des Volumenkoerpers unter dem Zeiger."""
    el = element_at(model, punkt, ("tet4", "tet10", "hex8"))
    if el is not None:
        for name, k in (getattr(model, "koerper", {}) or {}).items():
            if el in (k.elemente or []):
                return name
        g = getattr(model.elements[el], "group", "")
        if g in (getattr(model, "koerper", {}) or {}):
            return g
    if punkt is None:
        return None
    p = np.asarray(punkt, float).ravel()[:3]
    best, bestd = None, None
    for name, k in (getattr(model, "koerper", {}) or {}).items():
        idx = sorted({n for fn in k.flaechen
                      for n in ((getattr(model, "flaechen", {}) or {})
                                .get(fn).randknoten(model)
                                if (getattr(model, "flaechen", {}) or {}).get(fn) else [])})
        if len(idx) < 4:
            continue
        X = model.nodes[idx]
        d = float(np.linalg.norm(X.mean(axis=0) - p))
        r = float(np.linalg.norm(X - X.mean(axis=0), axis=1).max())
        if d <= max(r, 0.02 * size) and (bestd is None or d < bestd):
            best, bestd = name, d
    return best


def member_at(model: Model, punkt):
    """Name des Stabes (Stabzug), dessen Element unter dem Zeiger liegt."""
    el = element_at(model, punkt, ("beam", "truss"))
    if el is None:
        return None
    for name, mem in (model.members or {}).items():
        if el in (mem.elements or []):
            return name
    return None


def to_grid(model: Model) -> pv.UnstructuredGrid:
    cells, types = [], []
    for e in model.elements:
        ct, n = CELL_MAP[e.typ]
        cells.append(n)
        cells.extend(e.nodes[:n])
        types.append(ct)
    if not cells:
        return pv.UnstructuredGrid()
    return pv.UnstructuredGrid(np.array(cells), np.array(types),
                               np.asarray(model.nodes, float))


def util_colors(values: np.ndarray):
    """Farbskala Ausnutzung: gruen -> gelb -> rot (>1 dunkelrot)."""
    return "RdYlGn_r"


def support_shape(support) -> str:
    """Symbolart eines Lagers aus seinen Freiheitsgraden.

    Ein Wuerfel steht fuer die Einspannung (alle sechs Freiheitsgrade), ein
    Kegel fuer das gelenkige Lager, ein Zylinder fuer ein Federlager. So sagt
    das Symbol, was es haelt - erst dadurch ist seine Groesse eine Angabe und
    nicht nur Zierde.
    """
    dofs = set(int(d) for d in getattr(support, "dofs", []) or [])
    beh = getattr(support, "behaviour", None) or {}
    for b in beh.values():
        typ = getattr(b, "typ", None) or (b.get("typ") if isinstance(b, dict) else None)
        if typ == "spring":
            return "feder"
    if getattr(support, "stiffness", None) and any(support.stiffness):
        return "feder"
    if dofs >= {0, 1, 2, 3, 4, 5}:
        return "einspannung"
    return "gelenk"


def _glyph(shape: str, d: float):
    if shape == "einspannung":
        return pv.Cube(x_length=1.6 * d, y_length=1.6 * d, z_length=1.2 * d,
                       center=(0, 0, -0.6 * d))
    if shape == "feder":
        return pv.Cylinder(direction=(0, 0, 1), height=2 * d, radius=0.7 * d,
                           center=(0, 0, -d))
    return pv.Cone(direction=(0, 0, 1), height=2 * d, radius=d, center=(0, 0, -d))


def support_size(model: Model, faktor: float = 1.0) -> float:
    """Grundgroesse der Lagersymbole [m]."""
    return 0.012 * model.characteristic_size() * max(float(faktor), 0.05)


def add_supports(plotter, model: Model, size: float, faktor: float = 1.0):
    """Knoten-, Linien- und Flaechenlager sowie Kontaktlager zeichnen.

    ``faktor`` skaliert alle Symbole, ``Support.groesse`` zusaetzlich das
    einzelne Lager (Rechtsklick auf das Lager im Viewport).
    """
    d0 = 0.012 * size * max(float(faktor), 0.05)
    # Nach Symbolart und Groesse buendeln: ein Glyphensatz je Kombination
    gruppen: dict[tuple, list] = {}
    for s in model.supports:
        g = round(float(getattr(s, "groesse", 1.0) or 1.0), 3)
        gruppen.setdefault((support_shape(s), g), []).append(s.node)
    for i, ((shape, g), nodes) in enumerate(sorted(gruppen.items())):
        pts = model.nodes[nodes]
        plotter.add_mesh(pv.PolyData(pts).glyph(geom=_glyph(shape, d0 * g),
                                                scale=False, orient=False),
                         color=FARBE_LAGER, name=f"supports{i}")
    for j, ls in enumerate(getattr(model, "line_supports", []) or []):
        nodes = [int(n) for n in ls.nodes if 0 <= int(n) < model.nn]
        if not nodes:
            continue
        plotter.add_mesh(pv.PolyData(model.nodes[nodes]).glyph(
            geom=_glyph("gelenk", 0.6 * d0), scale=False, orient=False),
            color=FARBE_LINIENLAGER, name=f"lsupports{j}")
    for j, ss in enumerate(getattr(model, "surface_supports", []) or []):
        nodes = [int(n) for n in ss.nodes if 0 <= int(n) < model.nn]
        if not nodes:
            continue
        plotter.add_mesh(pv.PolyData(model.nodes[nodes]).glyph(
            geom=_glyph("feder", 0.5 * d0), scale=False, orient=False),
            color=FARBE_FLAECHENLAGER, name=f"fsupports{j}")
    if model.contact_supports:
        pts = model.nodes[[c.node for c in model.contact_supports]]
        plotter.add_mesh(pv.PolyData(pts).glyph(geom=_glyph("gelenk", d0),
                                                scale=False, orient=False),
                         color=FARBE_KONTAKT, name="csupports")


def support_at(model: Model, punkt, size: float, faktor: float = 1.0):
    """Das Lager, das am dichtesten an ``punkt`` liegt - oder None.

    Der Fangbereich ist die Symbolgroesse selbst: was man anklickt, muss man
    auch sehen.
    """
    if punkt is None or not model.supports:
        return None
    p = np.asarray(punkt, float).ravel()[:3]
    best, bestd = None, None
    for i, s in enumerate(model.supports):
        if not (0 <= int(s.node) < model.nn):
            continue
        d0 = 0.012 * size * max(float(faktor), 0.05) * float(getattr(s, "groesse", 1.0) or 1.0)
        dist = float(np.linalg.norm(model.nodes[int(s.node)] - p))
        if dist <= max(2.5 * d0, 0.01 * size) and (bestd is None or dist < bestd):
            best, bestd = i, dist
    return best


def add_loads(plotter, model: Model, case, size: float):
    """Knotenlasten (Pfeile) und Streckenlasten (Pfeilreihen) eines Lastfalls."""
    pts, vec = [], []
    for l in case.nodal_loads:
        f = np.asarray(l.F[:3], float)
        if np.any(f):
            pts.append(model.nodes[l.node])
            vec.append(f)
    for bl in case.beam_loads:
        e = model.elements[bl.elem]
        X = model.nodes[e.nodes]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        q1 = np.asarray(bl.q, float)
        q2 = np.asarray(bl.q2, float) if bl.q2 is not None else q1
        if bl.system == "local":
            q1, q2 = T3.T @ q1, T3.T @ q2
        for t in np.linspace(0.1, 0.9, 4):
            q = (1 - t) * q1 + t * q2
            if np.any(q):
                pts.append(X[0] + t * (X[1] - X[0]))
                vec.append(q)
    if not pts:
        return
    pd = pv.PolyData(np.array(pts))
    v = np.array(vec, float)
    v = v / (np.abs(v).max() or 1.0) * 0.06 * size
    # Pfeile zeigen auf den Angriffspunkt: Startpunkt = Punkt - Vektor
    pd.points = pd.points - v
    pd["v"] = v
    plotter.add_mesh(pd.glyph(orient="v", scale="v", factor=1.0), color="#c02020", name="loads")


def add_contact_markers(plotter, model: Model, contact: list, size: float):
    if not contact:
        return
    for status, color in STATUS_COLOR.items():
        nodes = [c["node"] for c in contact if c["status"] == status]
        if nodes:
            plotter.add_points(model.nodes[nodes], color=color, point_size=12,
                               render_points_as_spheres=True, name=f"contact_{status}")


def beam_diagram(model: Model, res, quantity: str, scale: float, n: int = 9):
    """Schnittgroessenverlauf als Polylinien (PolyData) mit Skalarwerten."""
    st = res.stations(n) if hasattr(res, "stations") else None
    pts, lines, vals = [], [], []
    base = 0
    for i, e in enumerate(model.elements):
        if e.typ not in ("beam", "truss"):
            continue
        X = model.nodes[e.nodes]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        if st is not None:
            if i not in st:
                continue
            x = st[i]["x"]
            v = st[i][quantity]
        else:   # Envelope: max/min
            d = res.beam.get(i)
            if d is None:
                continue
            x = d["x"]
            v = np.where(np.abs(d[quantity][1]) >= np.abs(d[quantity][0]),
                         d[quantity][1], d[quantity][0])
        # Richtung: My, Vz, N in lokale z; Mz, Vy in lokale y; Mt in z
        direction = T3[1] if quantity in ("Mz", "Vy") else T3[2]
        sign = -1.0 if quantity in ("My",) else 1.0     # Momente auf der Zugseite antragen
        P0 = X[0] + np.outer(x, T3[0])
        P1 = P0 + np.outer(sign * v * scale, direction)
        k = len(x)
        for j in range(k):
            pts.append(P0[j]); pts.append(P1[j])
            lines.extend([2, base + 2 * j, base + 2 * j + 1])
            vals.extend([v[j], v[j]])
        for j in range(k - 1):
            lines.extend([2, base + 2 * j + 1, base + 2 * j + 3])
        base += 2 * k
    if not pts:
        return None
    pd = pv.PolyData(np.array(pts), lines=np.array(lines))
    pd["wert"] = np.array(vals)
    return pd


def diagram_scale(model: Model, res, quantity: str, n: int = 9) -> float:
    st = res.stations(n) if hasattr(res, "stations") else None
    vmax = 0.0
    if st is not None:
        for d in st.values():
            vmax = max(vmax, float(np.abs(d[quantity]).max()))
    else:
        for d in res.beam.values():
            vmax = max(vmax, float(np.abs(d[quantity][0]).max()), float(np.abs(d[quantity][1]).max()))
    if vmax <= 0:
        return 0.0
    return 0.08 * model.characteristic_size() / vmax


def result_field(model: Model, res, field: str, util: dict = None):
    """(Knotenskalare oder None, Zellskalare oder None, Name)."""
    nn = model.nn
    if field.startswith("|u|"):
        u = res.u if hasattr(res, "u") and res.u is not None else None
        if u is None and hasattr(res, "u_max"):
            return getattr(res, "umag_max") * 1000, None, "|u| max [mm]"
        return np.linalg.norm(u[:, :3], axis=1) * 1000, None, "|u| [mm]"
    if field in ("ux", "uy", "uz"):
        k = "xyz".index(field[1])
        if hasattr(res, "u") and res.u is not None:
            return res.u[:, k] * 1000, None, field + " [mm]"
        return np.where(np.abs(res.u_max[:, k]) > np.abs(res.u_min[:, k]),
                        res.u_max[:, k], res.u_min[:, k]) * 1000, None, field + " extrem [mm]"
    if field.startswith("Vergleich"):
        if hasattr(res, "node_vm_max"):
            return np.nan_to_num(res.node_vm_max) / 1e6, None, "σv max [MPa]"
        return np.nan_to_num(res.node_vm) / 1e6, None, "σv [MPa]"
    if field.startswith("Ausnutzung") and util:
        c = np.full(len(model.elements), np.nan)
        for i, v in util.items():
            c[i] = v
        return None, c, "Ausnutzung [-]"
    if field.startswith("Ausnutzung"):
        if hasattr(res, "util"):
            c = np.full(len(model.elements), np.nan)
            for i, v in res.util.items():
                if v is not None:
                    c[i] = v
            return None, c, "Ausnutzung elastisch [-]"
        c = np.full(len(model.elements), np.nan)
        for i, d in res.beam_forces.items():
            if d["util"] is not None:
                c[i] = d["util"]
        return None, c, "Ausnutzung elastisch [-]"
    return None, None, ""


def displacement_of(res):
    if hasattr(res, "u") and res.u is not None:
        return res.u
    if hasattr(res, "u_max"):
        return np.where(np.abs(res.u_max) > np.abs(res.u_min), res.u_max, res.u_min)
    return None
