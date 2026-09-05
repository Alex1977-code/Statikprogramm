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
    "Voll": ("■", "gefuellte Flaechen, Staebe mit ihrer Querschnittskontur"),
    "Transparent": ("◧", "durchscheinend - man sieht die innen liegenden Teile; "
                         "Staebe mit Querschnittskontur"),
    "Hidden-Line": ("◫", "weisse Flaechen mit dunklen Kanten, wie eine Zeichnung; "
                         "Staebe als Linie"),
    "Drahtmodell": ("▦", "nur die Kanten; Staebe als Linie"),
}

#: Symbolname je Darstellungsart
DARSTELLUNG_SYMBOL = {"Voll": "voll", "Transparent": "transparent",
                      "Hidden-Line": "hiddenline", "Drahtmodell": "draht"}

#: Bei diesen Darstellungsarten bekommt der Stab seine Querschnittskontur
KOERPERLICH = ("Voll", "Transparent")


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


def add_linien(plotter, model: Model, hervor: list = None, ausser=None):
    """Die Linien des Modells zeichnen.

    Linien sind Geometrie, keine Elemente - sie wurden bisher gar nicht
    dargestellt. In einem aus RFEM uebernommenen Modell besteht die Geometrie
    fast nur aus Linien; ohne sie sieht man ein leeres Bild und haelt den
    Import fuer gescheitert.

    Krumme Linien werden auf ihrer **wahren Kurve** gezeichnet, nicht als
    Sehne durch die Stuetzknoten - sonst wird aus einer Bohrung eine Strecke.
    """
    linien = getattr(model, "lines", {}) or {}
    if not linien:
        return
    hervor = set(hervor or [])
    ausser = set(ausser or ())
    pts, zellen = [], []
    for name, ln in linien.items():
        if name in hervor or name in ausser:
            continue
        idx = [int(n) for n in ln.nodes if 0 <= int(n) < model.nn]
        if len(idx) < 2:
            continue
        X = model.nodes[idx]
        if (ln.typ or "polyline") != "polyline":
            try:
                X = np.asarray(ln.punkte(model, TEILUNG_KURVE), float)
            except Exception:            # noqa: BLE001 - dann eben die Sehne
                X = model.nodes[idx]
        basis = len(pts)
        pts.extend(X)
        for i in range(len(X) - 1):
            zellen.extend([2, basis + i, basis + i + 1])
    if pts:
        plotter.add_mesh(pv.PolyData(np.asarray(pts, float), lines=np.asarray(zellen)),
                         color=FARBE_LINIE, line_width=2, name="linien")


FARBE_LINIE = "#7a8a99"

#: So viele Abschnitte bekommt eine krumme Linie beim Zeichnen
TEILUNG_KURVE = 16


def coons_flaeche(seiten: list, n: int = None):
    """Eine Coons-Flaeche zwischen vier Randseiten: (Punkte, Dreiecke).

    Der Mantel einer Bohrung oder eines Bolzens ist in RFEM eine Flaeche aus
    zwei Boegen und zwei Geraden. Ihr Rand liegt nicht in einer Ebene; als
    ein Vieleck laesst sie sich nicht zeichnen - VTK findet dafuer keine
    Dreiecke, und die Flaeche fehlt im Bild. Die transfinite Interpolation
    (Coons) spannt zwischen den vier Seiten eine Flaeche auf, die genau durch
    alle vier Raender geht:

        P(u,v) = (1-v) c_u(u) + v c_o(u) + (1-u) c_l(v) + u c_r(v)
                 - [(1-u)(1-v) P00 + u(1-v) P10 + (1-u) v P01 + u v P11]

    ``seiten`` sind die vier Randseiten im Umlauf (Ende = Anfang der
    naechsten); ``n`` erzwingt eine Teilung je Richtung, sonst folgt sie der
    Abtastung der Seiten. Rueckgabe: Punkte (k, 3)
    und Dreiecke (m, 3) als Indizes. Bei weniger oder mehr als vier Seiten
    (None, None).
    """
    if len(seiten) != 4:
        return None, None
    # Teilung je Richtung aus der Abtastung der Seiten: ein Zylindermantel
    # braucht entlang der Boegen 16 Stuecke, entlang der Geraden eines - er
    # ist eine Regelflaeche. 512 Dreiecke je Flaeche waeren bei 800 Mantel-
    # flaechen 400000; so sind es 25000.
    if n is None:
        n_u = int(min(24, max(1, max(len(seiten[0]), len(seiten[2])) - 1)))
        n_v = int(min(24, max(1, max(len(seiten[1]), len(seiten[3])) - 1)))
    else:
        n_u = n_v = int(n)

    def gleichmaessig(kurve, n):
        """Die Kurve auf n+1 Punkte gleicher Bogenlaenge bringen."""
        K = np.asarray(kurve, float)
        if len(K) < 2:
            return np.repeat(K[:1], n + 1, axis=0)
        laenge = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(K, axis=0), axis=1))])
        if laenge[-1] <= 0:
            return np.repeat(K[:1], n + 1, axis=0)
        t = np.linspace(0.0, laenge[-1], n + 1)
        return np.stack([np.interp(t, laenge, K[:, k]) for k in range(3)], axis=1)

    unten = gleichmaessig(seiten[0], n_u)            # u: 0 -> 1 bei v = 0
    rechts = gleichmaessig(seiten[1], n_v)           # v: 0 -> 1 bei u = 1
    oben = gleichmaessig(seiten[2][::-1], n_u)       # u: 0 -> 1 bei v = 1
    links = gleichmaessig(seiten[3][::-1], n_v)      # v: 0 -> 1 bei u = 0
    P00, P10, P01, P11 = unten[0], unten[-1], oben[0], oben[-1]
    u = np.linspace(0.0, 1.0, n_u + 1)[:, None, None]  # (n_u+1, 1, 1)
    v = np.linspace(0.0, 1.0, n_v + 1)[None, :, None]  # (1, n_v+1, 1)
    P = ((1 - v) * unten[:, None, :] + v * oben[:, None, :]
         + (1 - u) * links[None, :, :] + u * rechts[None, :, :]
         - ((1 - u) * (1 - v) * P00 + u * (1 - v) * P10
            + (1 - u) * v * P01 + u * v * P11))
    punkte = P.reshape(-1, 3)
    idx = np.arange((n_u + 1) * (n_v + 1)).reshape(n_u + 1, n_v + 1)
    a, b, c, d = idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]
    dreiecke = np.concatenate([np.stack([a, b, c], axis=-1).reshape(-1, 3),
                               np.stack([a, c, d], axis=-1).reshape(-1, 3)])
    return punkte, dreiecke


def flaechen_dreiecke(ring, seiten=None):
    """Eine Flaeche fuers Bild: (Punkte, Zellen als VTK-Liste).

    Eben: das Randpolygon als **eine** Zelle. Krumm mit vier Seiten: eine
    Coons-Flaeche aus Dreiecken. Sonst ein Faecher um den Schwerpunkt - das
    ist fuer eine schwach gewoelbte Flaeche mit fuenf Seiten besser als gar
    nichts.
    """
    from ..model import polygon_eben
    ring = np.asarray(ring, float)
    if len(ring) < 3:
        return None, None
    if polygon_eben(ring):
        return ring, [len(ring), *range(len(ring))]
    if seiten is not None and len(seiten) == 4:
        P, D = coons_flaeche(seiten)
        if P is not None:
            zellen = np.hstack([np.full((len(D), 1), 3), D]).ravel().tolist()
            return P, zellen
    mitte = ring.mean(axis=0)
    P = np.vstack([ring, mitte[None, :]])
    k = len(ring)
    zellen = []
    for i in range(k):
        zellen += [3, i, (i + 1) % k, k]
    return P, zellen


def add_geometrie(plotter, model: Model, groesse: float = 1.0, raender: dict = None,
                  seiten: dict = None, flaechen_an: bool = True, koerper_an: bool = True,
                  ausser_flaechen=None, ausser_koerper=None):
    """Flaechen und Volumenkoerper zeichnen, die **noch nicht vernetzt** sind.

    Ein Objekt, das man nicht sieht, kann man auch nicht anklicken. Eine eben
    aus Linien erzeugte Flaeche traegt noch keine Elemente; sie wird darum als
    durchscheinendes Polygon gezeichnet, ein noch nicht vernetzter
    Volumenkoerper zusaetzlich mit farbigen Randkanten.

    **Alles in je einem Netz**: ein aus RFEM uebernommenes Volumenmodell hat
    leicht ueber tausend Flaechen. Je Flaeche ein eigener Darsteller braucht
    Minuten und macht die Ansicht unbedienbar; gebuendelt sind es zwei.
    ``raender`` nimmt bereits berechnete Randpolygone entgegen
    ({Flaechenname: Punktfolge}), ``seiten`` die Randseiten je Linie
    ({Flaechenname: [Punktfolgen]}) - beide werden gefuellt, wenn sie fehlen,
    damit sie nicht zweimal ermittelt werden. Es sind **Punkte**, keine
    Knotennummern: eine Bohrung oder eine Buchse besteht aus zwei Halbboegen
    zwischen denselben zwei Knoten - ueber die Knoten allein waere davon
    nichts zu sehen.

    Krumme Flaechen (Zylindermantel: zwei Boegen, zwei Geraden) werden als
    Coons-Flaeche aus Dreiecken gezeichnet - als ein Vieleck fehlten sie im
    Bild, und die Volumen wirkten offen. Jede Zelle traegt in
    ``cell_data["flaeche"]`` die Nummer ihrer Flaeche in ``model.flaechen``
    (fuer den Fang auf Flaechen).

    ``flaechen_an``/``koerper_an`` sind die Sichtbarkeitsschalter,
    ``ausser_flaechen``/``ausser_koerper`` die ausgeblendeten Namen.
    """
    flaechen = getattr(model, "flaechen", {}) or {}
    if not flaechen:
        return
    raender = raender if raender is not None else {}
    seiten = seiten if seiten is not None else {}
    ausser_flaechen = set(ausser_flaechen or ())
    ausser_koerper = set(ausser_koerper or ())
    koerper = getattr(model, "koerper", {}) or {}
    # Flaechen eines ausgeblendeten Koerpers sind mit ihm weg
    for kn in ausser_koerper:
        k = koerper.get(kn)
        if k is not None:
            ausser_flaechen.update(k.flaechen)
    if not koerper_an:
        for k in koerper.values():
            ausser_flaechen.update(k.flaechen)

    def ring_von(name, f):
        r = raender.get(name)
        if r is None:
            r = f.randpunkte(model)
            raender[name] = r
        return r

    def seiten_von(name, f):
        r = seiten.get(name)
        if r is None:
            try:
                r = f.randseiten_punkte(model)
            except Exception:            # noqa: BLE001
                r = []
            seiten[name] = r
        return r

    pts: list = []
    zellen: list = []
    zelle_flaeche: list = []
    for nr, (name, f) in enumerate(flaechen.items()):
        if f.elemente or name in ausser_flaechen:
            continue
        if not flaechen_an and not any(name in k.flaechen for k in koerper.values()):
            continue
        ring = ring_von(name, f)
        if len(ring) < 3:
            continue
        P, Z = flaechen_dreiecke(ring, seiten_von(name, f))
        if P is None:
            continue
        basis = len(pts)
        pts.extend(np.asarray(P, float))
        i = 0
        n_zellen = 0
        while i < len(Z):
            k = int(Z[i])
            zellen.append(k)
            zellen.extend(int(z) + basis for z in Z[i + 1:i + 1 + k])
            i += k + 1
            n_zellen += 1
        zelle_flaeche.extend([nr] * n_zellen)
    if pts:
        pd = pv.PolyData(np.asarray(pts, float), faces=np.asarray(zellen))
        pd.cell_data["flaeche"] = np.asarray(zelle_flaeche, int)
        plotter.add_mesh(pd, color="#7fb3d5", opacity=0.45, show_edges=True,
                         edge_color="#20638f", line_width=1, name="geo_flaechen")
    # Randkanten der noch nicht vernetzten Volumenkoerper - ebenfalls gebuendelt
    if not koerper_an:
        return
    kpts: list = []
    klines: list = []
    for kn, k in koerper.items():
        if k.elemente or kn in ausser_koerper:
            continue
        for fname in k.flaechen:
            f = flaechen.get(fname)
            if f is None or f.elemente:
                continue
            ring = ring_von(fname, f)
            if len(ring) < 3:
                continue
            basis = len(kpts)
            P = np.asarray(ring, float)
            kpts.extend(np.vstack([P, P[:1]]))
            for i in range(len(P)):
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
        X = np.asarray(f.randpunkte(model), float)
        if len(X) < 3:
            continue
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
        teile = [np.asarray((getattr(model, "flaechen", {}) or {})[fn].randpunkte(model), float)
                 for fn in k.flaechen if fn in (getattr(model, "flaechen", {}) or {})]
        teile = [t for t in teile if len(t)]
        if not teile:
            continue
        X = np.vstack(teile)
        if len(X) < 4:
            continue
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


#: Elementtypen je Sichtbarkeitsschalter
TYPEN_STAEBE = ("beam", "truss")
TYPEN_FLAECHEN = ("shell3", "shell4")
TYPEN_VOLUMEN = ("tet4", "tet10", "hex8")


def to_grid(model: Model, typen=None, ausser=None) -> pv.UnstructuredGrid:
    """Das Elementnetz als VTK-Gitter.

    ``typen`` beschraenkt auf Elementtypen (Sichtbarkeitsschalter Staebe,
    Flaechen, Volumen), ``ausser`` blendet einzelne Elemente aus. Die
    Elementnummern stehen als ``cell_data["elem"]`` am Gitter - nur so lassen
    sich Zellwerte (Ausnutzung je Element) auf ein gefiltertes Gitter legen.
    Die Punkte sind immer **alle** Modellknoten, damit Knotenwerte
    (Verschiebungen) unveraendert passen.
    """
    cells, types, idx = [], [], []
    ausser = ausser or ()
    for i, e in enumerate(model.elements):
        if typen is not None and e.typ not in typen:
            continue
        if i in ausser:
            continue
        ct, n = CELL_MAP[e.typ]
        cells.append(n)
        cells.extend(e.nodes[:n])
        types.append(ct)
        idx.append(i)
    if not cells:
        return pv.UnstructuredGrid()
    g = pv.UnstructuredGrid(np.array(cells), np.array(types),
                            np.asarray(model.nodes, float))
    g.cell_data["elem"] = np.asarray(idx, int)
    return g


# --------------------------------------------------------------------------
# Staebe mit ihrer Querschnittskontur
# --------------------------------------------------------------------------
def querschnitt_umriss(sec) -> np.ndarray:
    """Der Umriss eines Querschnitts als (n, 2)-Punktfolge in (y, z).

    Lokale Achsen wie im Stabelement: y = starke Achse (Flanschbreite b liegt
    entlang y), z in der Stegebene (Hoehe h entlang z). Der Umriss ist ein
    geschlossenes Vieleck ohne Ausrundungen - fuer das Bild reicht das, und
    die Kanten bleiben scharf.
    """
    typ = str(getattr(sec, "typ", "") or "free")
    h = float(getattr(sec, "h", 0.0) or 0.0)
    b = float(getattr(sec, "b", 0.0) or 0.0)
    tw = float(getattr(sec, "tw", 0.0) or 0.0)
    tf = float(getattr(sec, "tf", 0.0) or 0.0)
    if typ == "I" and h > 0 and b > 0 and tw > 0 and tf > 0:
        y, z = b / 2, h / 2
        s = tw / 2
        return np.array([(-y, -z), (y, -z), (y, -z + tf), (s, -z + tf), (s, z - tf),
                         (y, z - tf), (y, z), (-y, z), (-y, z - tf), (-s, z - tf),
                         (-s, -z + tf), (-y, -z + tf)])
    if typ == "U" and h > 0 and b > 0 and tw > 0 and tf > 0:
        # Steg links, Flansche nach +y; Bezug ist die Schwerachse (yc)
        yc = float(getattr(sec, "yc", 0.0) or b / 3)
        z = h / 2
        return np.array([(-yc, -z), (b - yc, -z), (b - yc, -z + tf), (tw - yc, -z + tf),
                         (tw - yc, z - tf), (b - yc, z - tf), (b - yc, z), (-yc, z)])
    if typ == "L" and h > 0 and b > 0 and tw > 0:
        yc = float(getattr(sec, "yc", 0.0) or b / 4)
        zc = float(getattr(sec, "zc", 0.0) or h / 4)
        t = tw
        return np.array([(-yc, -zc), (b - yc, -zc), (b - yc, -zc + t), (t - yc, -zc + t),
                         (t - yc, h - zc), (-yc, h - zc)])
    if typ == "T" and h > 0 and b > 0 and tw > 0 and tf > 0:
        zc = float(getattr(sec, "zc", 0.0) or h / 3)
        y, s = b / 2, tw / 2
        return np.array([(-s, -zc), (s, -zc), (s, h - zc - tf), (y, h - zc - tf),
                         (y, h - zc), (-y, h - zc), (-y, h - zc - tf), (-s, h - zc - tf)])
    if typ in ("CHS", "circle") and h > 0:
        t = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        return np.column_stack([h / 2 * np.cos(t), h / 2 * np.sin(t)])
    if typ in ("RHS", "rect") and h > 0 and b > 0:
        y, z = b / 2, h / 2
        return np.array([(-y, -z), (y, -z), (y, z), (-y, z)])
    # Unbekannt: ein Quadrat mit der Flaeche des Querschnitts - besser als
    # nichts, und ehrlich, weil es keine Form vortaeuscht, die niemand kennt.
    A = float(getattr(sec, "A", 0.0) or 0.0)
    a = np.sqrt(max(A, 1e-8)) / 2
    if h > 0 and b > 0:
        a_y, a_z = b / 2, h / 2
    else:
        a_y = a_z = a
    return np.array([(-a_y, -a_z), (a_y, -a_z), (a_y, a_z), (-a_y, a_z)])


def stab_koerper(model: Model, elems, u=None, faktor: float = 0.0) -> "pv.PolyData | None":
    """Stabelemente als Koerper: die Querschnittskontur ueber die Stablaenge.

    Bei Voll- und Transparentdarstellung ist ein Stab mehr als eine Linie -
    man soll sehen, welches Profil dort liegt und wie es gedreht ist (Rollwinkel
    des Elements). Jede Elementseite traegt in ``cell_data["elem"]`` ihre
    Elementnummer und jeder Punkt in ``point_data["knoten"]`` den Knoten des
    Stabendes, zu dem er gehoert - damit lassen sich Ergebnisfarben genauso
    auflegen wie auf das Netz. ``u`` und ``faktor`` verschieben die Stabenden
    mit der (ueberhoehten) Verformung.
    """
    pts: list = []
    faces: list = []
    elem_of_face: list = []
    knoten_of_pt: list = []
    for i in elems:
        e = model.elements[int(i)]
        if e.typ not in TYPEN_STAEBE or len(e.nodes) < 2:
            continue
        sec = model.sections.get(e.sec) if e.sec else None
        if sec is None:
            continue
        n0, n1 = int(e.nodes[0]), int(e.nodes[-1])
        X0 = np.asarray(model.nodes[n0], float)
        X1 = np.asarray(model.nodes[n1], float)
        try:
            T3, L = bm.local_axes(X0, X1, getattr(e, "roll", 0.0) or 0.0)
        except ValueError:
            continue
        if u is not None and faktor:
            X0 = X0 + faktor * np.asarray(u[n0, :3], float)
            X1 = X1 + faktor * np.asarray(u[n1, :3], float)
        ring = querschnitt_umriss(sec)
        k = len(ring)
        if k < 3:
            continue
        ey, ez = T3[1], T3[2]
        basis = len(pts)
        for X, nd in ((X0, n0), (X1, n1)):
            for y, z in ring:
                pts.append(X + y * ey + z * ez)
                knoten_of_pt.append(nd)
        # Mantel: je Kante ein Viereck
        for j in range(k):
            a, b = basis + j, basis + (j + 1) % k
            faces.extend([4, a, b, b + k, a + k])
            elem_of_face.append(int(i))
        # Stirnseiten
        faces.append(k)
        faces.extend(range(basis, basis + k))
        elem_of_face.append(int(i))
        faces.append(k)
        faces.extend(range(basis + k, basis + 2 * k))
        elem_of_face.append(int(i))
    if not pts:
        return None
    pd = pv.PolyData(np.asarray(pts, float), faces=np.asarray(faces))
    pd.cell_data["elem"] = np.asarray(elem_of_face, int)
    pd.point_data["knoten"] = np.asarray(knoten_of_pt, int)
    return pd


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


#: Schnittgroessen eines Stabes in der Reihenfolge, in der sie angezeigt werden
SCHNITTGROESSEN = ("N", "Vy", "Vz", "Mt", "My", "Mz")

#: Einheit und Umrechnung je Schnittgroesse
SG_EINHEIT = {"N": ("kN", 1e3), "Vy": ("kN", 1e3), "Vz": ("kN", 1e3),
              "Mt": ("kNm", 1e3), "My": ("kNm", 1e3), "Mz": ("kNm", 1e3)}


def schnittgroessen_grenzen(model: Model, res, groessen=SCHNITTGROESSEN) -> dict:
    """{Groesse: (kleinster Wert, Element, groesster Wert, Element)}.

    Gesucht wird ueber **alle Nachweisstellen**, nicht nur die Stabenden: das
    groesste Feldmoment liegt in der Regel dazwischen. Bei einer Umhuellenden
    stehen die Grenzwerte schon in ``res.beam``; dann werden sie genommen.
    """
    out: dict = {}
    st = res.stations() if hasattr(res, "stations") else None
    quelle = st if st else getattr(res, "beam", None)
    if not quelle:
        return out
    for q in groessen:
        klein = gross = None
        for i, d in quelle.items():
            v = np.asarray(d.get(q), float)
            if not v.size:
                continue
            a, b = float(np.nanmin(v)), float(np.nanmax(v))
            if klein is None or a < klein[0]:
                klein = (a, i)
            if gross is None or b > gross[0]:
                gross = (b, i)
        if klein is not None:
            out[q] = (klein[0], klein[1], gross[0], gross[1])
    return out


def _stabname(model: Model, elem: int, breite: int = 12) -> str:
    """Der Stab, zu dem ein Element gehoert - sonst die Elementnummer.

    Auf *breite* gekuerzt: die Kennwerte stehen im Bild, und eine Zeile, die
    ueber das Modell laeuft, ist keine Hilfe.
    """
    name = f"El. {elem}"
    for nm, mem in (model.members or {}).items():
        if elem in (mem.elements or []):
            name = str(nm)
            break
    # Der Text geht an eine VTK-Schrift; die kennt nur Latin-1, darum ".."
    # statt eines Auslassungszeichens.
    return name if len(name) <= breite else name[:breite - 2] + ".."


def kennwerte(model: Model, res, util: dict = None, groesse: str = "",
              ueberschrift: str = "") -> list:
    """Die Kennzahlen des gezeigten Ergebnisses als Textzeilen.

    Das sind die Zahlen, nach denen zuerst gefragt wird: groesste Ausnutzung,
    kleinste und groesste Verformung, kleinste und groesste Schnittgroesse -
    jeweils **mit dem Ort**, denn ein Zahlenwert ohne Ort ist kein Ergebnis.
    Steht in *groesse* eine Schnittgroesse, wird nur diese ausgeschrieben.

    Die Zeilen sind auf feste Spalten gesetzt (Schreibmaschinenschrift), damit
    die Zahlen im Bild untereinander stehen und die Zeile nicht ueber das
    Modell laeuft.
    """
    zeilen = []
    if ueberschrift:
        zeilen.append(str(ueberschrift))
    def zeile(name, lo, ort_lo, hi, ort_hi, einheit):
        return (f"{name:<6s}{lo:>10s} {ort_lo:<11s}{hi:>10s} {ort_hi:<11s}"
                f"[{einheit}]")

    u = displacement_of(res)
    if u is not None and len(u):
        mag = np.linalg.norm(u[:, :3], axis=1)
        k = int(np.nanargmax(mag)) if np.isfinite(mag).any() else 0
        zeilen.append(zeile("u", "", "", f"{mag[k] * 1000:.3f}",
                            f"Knoten {k}", "mm"))
        for j, nm in enumerate(("ux", "uy", "uz")):
            zeilen.append(zeile(nm, f"{u[:, j].min() * 1000:.3f}", "",
                                f"{u[:, j].max() * 1000:.3f}", "", "mm"))
    reihe = (groesse,) if groesse in SCHNITTGROESSEN else SCHNITTGROESSEN
    grenzen = schnittgroessen_grenzen(model, res, reihe)
    for q in reihe:
        if q not in grenzen:
            continue
        lo, e_lo, hi, e_hi = grenzen[q]
        eh, f = SG_EINHEIT[q]
        zeilen.append(zeile(q, f"{lo / f:.3f}", _stabname(model, e_lo, 10),
                            f"{hi / f:.3f}", _stabname(model, e_hi, 10), eh))
    # Verdrehungen - nur wo es Staebe oder Schalen gibt, sonst sind sie null
    if u is not None and len(u) and u.shape[1] >= 6 and np.abs(u[:, 3:6]).max() > 0:
        for j, nm in enumerate(("phix", "phiy", "phiz")):
            zeilen.append(zeile(nm, f"{u[:, 3 + j].min() * 1000:.3f}", "",
                                f"{u[:, 3 + j].max() * 1000:.3f}", "", "mrad"))
    # Auflagerkraefte: kleinste und groesste je Richtung mit Knoten
    R = getattr(res, "reactions", None)
    if R is None and getattr(res, "r_min", None) is not None:
        R = None
        rmin, rmax = res.r_min, res.r_max
        for j, (nm, eh, f) in enumerate((("Rx", "kN", 1e3), ("Ry", "kN", 1e3),
                                          ("Rz", "kN", 1e3), ("Mx", "kNm", 1e3),
                                          ("My", "kNm", 1e3), ("Mz", "kNm", 1e3))):
            if not np.any(rmin[:, j]) and not np.any(rmax[:, j]):
                continue
            a, b = int(np.argmin(rmin[:, j])), int(np.argmax(rmax[:, j]))
            zeilen.append(zeile(nm, f"{rmin[a, j] / f:.2f}", f"Knoten {a}",
                                f"{rmax[b, j] / f:.2f}", f"Knoten {b}", eh))
    elif R is not None and len(R):
        for j, (nm, eh, f) in enumerate((("Rx", "kN", 1e3), ("Ry", "kN", 1e3),
                                          ("Rz", "kN", 1e3), ("Mx", "kNm", 1e3),
                                          ("My", "kNm", 1e3), ("Mz", "kNm", 1e3))):
            if j >= R.shape[1] or not np.any(R[:, j]):
                continue
            a, b = int(np.argmin(R[:, j])), int(np.argmax(R[:, j]))
            zeilen.append(zeile(nm, f"{R[a, j] / f:.2f}", f"Knoten {a}",
                                f"{R[b, j] / f:.2f}", f"Knoten {b}", eh))
    vm = getattr(res, "node_vm_max", None)
    if vm is None:
        vm = getattr(res, "node_vm", None)
    if vm is not None and len(vm) and np.isfinite(vm).any():
        k = int(np.nanargmax(vm))
        zeilen.append(zeile("sig_v", "", "", f"{float(vm[k]) / 1e6:.1f}",
                            f"Knoten {k}", "N/mm²"))
    werte = dict(util or {})
    if not werte:
        for i, d in (getattr(res, "beam_forces", None) or {}).items():
            if d.get("util") is not None:
                werte[i] = d["util"]
    if werte:
        i = max(werte, key=lambda k: werte[k])
        zeilen.append(f"max. Ausnutzung {werte[i]:.3f} an {_stabname(model, i)}"
                      + ("  - ueberschritten!" if werte[i] > 1.0 else ""))
    return zeilen


def kopfzeile(model: Model, res, ergebnisname: str = "", faerbung: str = "",
              verlauf: str = "", faktor: float = 0.0, lastfall: str = "") -> list:
    """Was die Ansicht gerade zeigt - fuer die Ecke oben links.

    Ohne Ergebnis: das Modell und der aktive Lastfall mit seinen Lasten. Mit
    Ergebnis: der Lastfall, die Kombination oder die Umhuellende, danach die
    Faerbung, der Schnittgroessenverlauf und die Ueberhoehung. Ein Bild ohne
    diese Zeile ist im Statikdokument nicht pruefbar.
    """
    zeilen = []
    if res is None:
        lc = None
        try:
            lc = model.case(lastfall) if lastfall else model.case()
        except Exception:                   # noqa: BLE001
            lc = None
        if lc is not None:
            n = getattr(lc, "n_loads", 0)
            zeilen.append(f"Lastfall {lc.name}" + (f" ({n} Lasten)" if n else ""))
        else:
            zeilen.append(model.name or "Modell")
        return zeilen
    name = ergebnisname or getattr(res, "name", "") or "Ergebnis"
    if name.startswith("Kombination "):
        kurz = name.split(":")[0]
        formel = name[len(kurz) + 1:].strip()
        zeilen.append(kurz)
        if formel:
            zeilen.append("  " + formel)
    else:
        zeilen.append(name)
    teile = []
    if faerbung and not faerbung.startswith("keine"):
        teile.append(f"Färbung {faerbung}")
    if verlauf and verlauf in SCHNITTGROESSEN:
        teile.append(f"Verlauf {verlauf}")
    if faktor:
        teile.append(f"Überhöhung x{faktor:.1f}")
    if teile:
        zeilen.append("  " + " · ".join(teile))
    return zeilen
