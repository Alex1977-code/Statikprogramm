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


def add_nodes(plotter, model: Model, groesse: float = 1.0, nur=None):
    """Alle gesetzten Knoten als Punkte zeichnen - oder nur die in ``nur``
    (Knotennummern), wenn Teile des Modells ausgeblendet sind.

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
    alle = np.arange(model.nn)
    if nur is not None:
        alle = np.asarray(sorted(int(i) for i in nur if 0 <= int(i) < model.nn), int)
        frei = np.intersect1d(frei, alle)
        if not len(alle):
            return
    d = max(3.0, 7.0 * float(groesse))
    if len(frei) > FREI_ANTEIL * model.nn:
        plotter.add_points(model.nodes[alle], color=FARBE_KNOTEN, point_size=d,
                           render_points_as_spheres=True, name="knoten")
        return
    fest = np.setdiff1d(alle, frei, assume_unique=False)
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


def linien_netz(model: Model, hervor: list = None, ausser=None):
    """Alle Linien als ein Liniennetz (PolyData) - oder None.

    Reine Daten, damit sie je Modellstand einmal entstehen: 1356 Boegen
    abzutasten kostet eine halbe Sekunde, und das fiel bisher bei jedem Klick an.
    """
    linien = getattr(model, "lines", {}) or {}
    if not linien:
        return None
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
    if not pts:
        return None
    return pv.PolyData(np.asarray(pts, float), lines=np.asarray(zellen))


def add_linien(plotter, model: Model, hervor: list = None, ausser=None, netz=None):
    """Die Linien des Modells zeichnen.

    Linien sind Geometrie, keine Elemente - sie wurden bisher gar nicht
    dargestellt. In einem aus RFEM uebernommenen Modell besteht die Geometrie
    fast nur aus Linien; ohne sie sieht man ein leeres Bild und haelt den
    Import fuer gescheitert.

    Krumme Linien werden auf ihrer **wahren Kurve** gezeichnet, nicht als
    Sehne durch die Stuetzknoten - sonst wird aus einer Bohrung eine Strecke.
    """
    if netz is None:
        netz = linien_netz(model, hervor, ausser)
    if netz is not None:
        plotter.add_mesh(netz, color=FARBE_LINIE, line_width=2, name="linien")


FARBE_LINIE = "#7a8a99"
FARBE_MASS = "#1d2731"
FARBE_MESSUNG = "#e5701c"


def add_bemassungen(plotter, model: Model, groesse: float, blick=None, messungen=None):
    """Bemassungen des Modells (dunkel) und voruebergehende Messungen (orange):
    Strecken als Linien, Masstexte als Beschriftungen, immer sichtbar."""
    from .. import bemassung as bm
    einst = model.bemassung_einstellungen() if hasattr(model, "bemassung_einstellungen") \
        else bm.BemassungEinstellung()

    def zeichnen(geos, name, farbe):
        segs = [s for g in geos for s in g["linien"]]
        texte = [x for g in geos for x in g["texte"]]
        if segs:
            pts = np.array([np.asarray(q, float) for a, b in segs for q in (a, b)], float)
            pd = pv.PolyData(pts)
            pd.lines = np.hstack([[2, 2 * i, 2 * i + 1] for i in range(len(segs))])
            plotter.add_mesh(pd, color=farbe, line_width=2, name=name)
        if texte:
            plotter.add_point_labels(np.array([np.asarray(q, float) for q, _ in texte]),
                                     [str(x) for _, x in texte], font_size=int(einst.textgroesse),
                                     text_color=farbe, shape=None, show_points=False,
                                     always_visible=True, name=name + "_text")

    bms = getattr(model, "bemassungen", {}) or {}
    if bms:
        zeichnen([bm.geometrie(b, einst, groesse, blick) for b in bms.values()], "bemassung",
                 einst.farbe or FARBE_MASS)
    if messungen:
        zeichnen([bm.messung_geometrie(x["art"], x["punkte"], einst, groesse, blick) for x in messungen],
                 "messung", FARBE_MESSUNG)

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


#: Wie Flaechen und Volumen ohne Netz je Darstellungsart gezeichnet werden:
#: (Flaeche zeichnen, Angaben fuer add_mesh, Randlinien zeichnen, Randfarbe)
GEOMETRIE_DARSTELLUNG = {
    "Voll": (True, {"color": "#7fb3d5", "opacity": 1.0}, True, "#20638f"),
    "Transparent": (True, {"color": "#7fb3d5", "opacity": 0.45}, True, "#20638f"),
    "Hidden-Line": (True, {"color": "#ffffff", "opacity": 1.0, "lighting": False}, True, "#202020"),
    "Drahtmodell": (False, {}, True, "#20638f"),
}


def geometrie_netze(model: Model, raender: dict = None, seiten: dict = None,
                    flaechen_an: bool = True, koerper_an: bool = True,
                    ausser_flaechen=None, ausser_koerper=None):
    """Die Netze der Geometrie ohne Elemente: (Flaechen, Raender, Koerperkanten).

    Reine Daten, kein Zeichnen - damit sie je Modellstand **einmal** entstehen
    (bei 786 Zylindermaenteln kostet der Aufbau eine Sekunde, und die darf
    nicht bei jedem Klick anfallen). Jedes Ergebnis kann None sein.
    """
    flaechen = getattr(model, "flaechen", {}) or {}
    if not flaechen:
        return None, None, None
    raender = raender if raender is not None else {}
    seiten = seiten if seiten is not None else {}
    ausser_flaechen = set(ausser_flaechen or ())
    ausser_koerper = set(ausser_koerper or ())
    koerper = getattr(model, "koerper", {}) or {}
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
    rpts: list = []
    rlines: list = []
    for nr, (name, f) in enumerate(flaechen.items()):
        if f.elemente or name in ausser_flaechen:
            continue
        if not flaechen_an and not any(name in k.flaechen for k in koerper.values()):
            continue
        ring = ring_von(name, f)
        if len(ring) < 3:
            continue
        basis = len(rpts)
        P = np.asarray(ring, float)
        rpts.extend(np.vstack([P, P[:1]]))
        for i in range(len(P)):
            rlines.extend([2, basis + i, basis + i + 1])
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
    pd_f = pd_r = pd_k = None
    if pts:
        pd_f = pv.PolyData(np.asarray(pts, float), faces=np.asarray(zellen))
        pd_f.cell_data["flaeche"] = np.asarray(zelle_flaeche, int)
    if rpts:
        pd_r = pv.PolyData(np.asarray(rpts, float), lines=np.asarray(rlines))
    if koerper_an:
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
            pd_k = pv.PolyData(np.asarray(kpts, float), lines=np.asarray(klines))
    return pd_f, pd_r, pd_k


def add_geometrie(plotter, model: Model, groesse: float = 1.0, raender: dict = None,
                  seiten: dict = None, flaechen_an: bool = True, koerper_an: bool = True,
                  ausser_flaechen=None, ausser_koerper=None, modus: str = "Transparent",
                  netze=None):
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

    ``modus`` ist die Darstellungsart der Ansicht - sie gilt auch fuer
    Flaechen und Volumen ohne Netz: Voll deckend, Transparent durchscheinend,
    Hidden-Line weiss mit dunklen Randlinien, Drahtmodell nur die Randlinien.
    Die Kanten der Dreiecke einer Coons-Flaeche sind kein Netz und werden
    nie gezeichnet; die Raender kommen aus den Randlinien der Flaechen.
    """
    if netze is None:
        netze = geometrie_netze(model, raender, seiten, flaechen_an, koerper_an,
                                ausser_flaechen, ausser_koerper)
    pd_f, pd_r, pd_k = netze
    flaeche_zeichnen, angaben, rand_zeichnen, randfarbe = GEOMETRIE_DARSTELLUNG.get(
        modus, GEOMETRIE_DARSTELLUNG["Transparent"])
    if pd_f is not None and flaeche_zeichnen:
        plotter.add_mesh(pd_f, show_edges=False, name="geo_flaechen", **angaben)
    if pd_r is not None and rand_zeichnen:
        plotter.add_mesh(pd_r, color=randfarbe, line_width=1, name="geo_raender")
    if pd_k is not None:
        plotter.add_mesh(pd_k, color="#8e44ad" if modus != "Hidden-Line" else "#202020",
                         line_width=2, name="geo_volumen")


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


# ---- Lagersymbole ------------------------------------------------------
def _fhg_lage(support) -> tuple:
    """(starr gehaltene FHG, Feder-FHG) eines Lagers als Mengen 0..5."""
    fest, federn = set(), set()
    for d in range(6):
        try:
            b = support.dof_behaviour(d)
        except Exception:               # noqa: BLE001
            continue
        typ = getattr(b, "typ", None) or (b.get("typ") if isinstance(b, dict) else "free")
        if typ == "rigid":
            fest.add(d)
        elif typ == "spring":
            federn.add(d)
    return fest, federn


def support_shape(support) -> str:
    """Grobe Symbolart eines Lagers: einspannung, gelenk oder feder."""
    fest, federn = _fhg_lage(support)
    if federn:
        return "feder"
    if fest >= {0, 1, 2, 3, 4, 5}:
        return "einspannung"
    return "gelenk"


def lager_symbol(support) -> tuple:
    """Der Schluessel des Lagersymbols - das klassische Bild der Statik:

    * Einspannung: Wuerfel.
    * gehaltene Verschiebung: Pyramide, Spitze am Knoten; ist eine der
      uebrigen Verschiebungen frei, steht sie auf einer **Gleitebene**, die
      sich in die freie Richtung streckt (Rollenlager).
    * freie Verdrehung: **Kugel** an der Spitze (alle Verdrehungen frei),
      **Zylinder** in Richtung der Achse (genau eine Verdrehung frei).
    * Feder: Schraubenfeder in Richtung des Freiheitsgrads, Drehfeder als
      Spirale um seine Achse.

    Rueckgabe (achse, grundform, verdrehung, freie Verschiebungen, Federn):
    achse 0/1/2 sagt, in welche Richtung das Symbol unter den Knoten zeigt.
    """
    fest, federn = _fhg_lage(support)
    T = {d for d in fest if d < 3}
    R = {d for d in fest if d >= 3}
    Tf = {d for d in federn if d < 3}
    Rf = {d for d in federn if d >= 3}
    if 2 in T or 2 in Tf:
        achse = 2
    elif T:
        achse = min(T)
    elif Tf:
        achse = min(Tf)
    else:
        achse = 2
    if T == {0, 1, 2} and R == {3, 4, 5}:
        return (2, "einspannung", "", (), ())
    if T:
        grund = "pyramide"
    elif Tf:
        grund = "federlager"
    elif R or Rf:
        grund = "drehlager"
    else:
        grund = "frei"
    frei_R = {3, 4, 5} - R - Rf
    if len(frei_R) == 1:
        dreh = f"zyl{min(frei_R) - 3}"
    elif frei_R:
        dreh = "kugel"
    else:
        dreh = ""
    frei_T = tuple(sorted({0, 1, 2} - T - Tf - {achse})) if (T or Tf) else ()
    return (achse, grund, dreh, frei_T, tuple(sorted(federn)))


def _drehung_auf(richtung) -> np.ndarray:
    """Drehmatrix, die die lokale Symbolachse -z auf die Richtung *richtung* legt."""
    v = np.asarray(richtung, float).ravel()[:3]
    n = np.linalg.norm(v)
    if n <= 0:
        return np.eye(3)
    v = v / n
    a = np.array([0.0, 0.0, -1.0])
    c = float(np.dot(a, v))
    if c > 1 - 1e-9:
        return np.eye(3)
    if c < -1 + 1e-9:
        return np.diag([1.0, -1.0, -1.0])      # um x um 180 Grad
    k = np.cross(a, v)
    s_ = np.linalg.norm(k)
    k = k / s_
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]], float)
    return np.eye(3) + s_ * K + (1 - c) * (K @ K)


def _helix(laenge: float, radius: float, windungen: float = 3.0, n: int = 60) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n)
    return np.column_stack([radius * np.cos(2 * np.pi * windungen * t),
                            radius * np.sin(2 * np.pi * windungen * t), -laenge * t])


def _spirale(r0: float, r1: float, windungen: float = 2.5, n: int = 60) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n)
    r = r0 + (r1 - r0) * t
    return np.column_stack([r * np.cos(2 * np.pi * windungen * t),
                            r * np.sin(2 * np.pi * windungen * t), np.zeros(n)])


def _achsen_rahmen(u) -> np.ndarray:
    """Drehmatrix, die -z auf u legt (fuer Federn in Richtung u)."""
    return _drehung_auf(u)


def lagerglyph(key: tuple, d: float, richtung=None) -> pv.PolyData:
    """Das Symbol zu einem Schluessel aus :func:`lager_symbol`, Grundmass d.

    ``richtung`` legt die Symbolachse frei (Flaechenlager: die Normale der
    gebetteten Flaeche); sonst zeigt sie in -e_achse (unter den Knoten).
    """
    achse, grund, dreh, frei_T, federn = key
    ez = -np.eye(3)[int(achse)] if richtung is None else np.asarray(richtung, float)
    R = _drehung_auf(ez)

    def lokal(g: int) -> np.ndarray:
        return R.T @ np.eye(3)[g]

    teile = []
    if grund == "einspannung":
        teile.append(pv.Cube(x_length=1.6 * d, y_length=1.6 * d, z_length=1.2 * d,
                             center=(0, 0, -0.6 * d)))
    else:
        if grund == "pyramide":
            teile.append(pv.Cone(direction=(0, 0, 1), height=2 * d, radius=d,
                                 center=(0, 0, -d), resolution=4))
        elif grund == "drehlager":
            teile.append(pv.Cube(x_length=0.9 * d, y_length=0.9 * d, z_length=0.9 * d))
        frei_lokal = {int(np.argmax(np.abs(lokal(g)))) for g in frei_T}
        if frei_lokal or grund == "federlager":
            # Gleitebene: die Platte streckt sich in die freie Richtung
            lx = 3.2 * d if 0 in frei_lokal else 1.9 * d
            ly = 3.2 * d if 1 in frei_lokal else 1.9 * d
            teile.append(pv.Cube(center=(0, 0, -2.25 * d), x_length=lx, y_length=ly, z_length=0.16 * d))
            if frei_lokal and grund == "pyramide":
                # zwei Rollen zwischen Pyramide und Ebene
                for sx in (-0.55 * d, 0.55 * d):
                    if 0 in frei_lokal:
                        teile.append(pv.Cylinder(center=(sx, 0, -2.08 * d), direction=(0, 1, 0),
                                                 radius=0.08 * d, height=1.2 * d))
                    else:
                        teile.append(pv.Cylinder(center=(0, sx, -2.08 * d), direction=(1, 0, 0),
                                                 radius=0.08 * d, height=1.2 * d))
        if dreh == "kugel":
            teile.append(pv.Sphere(radius=0.42 * d, center=(0, 0, 0)))
        elif dreh.startswith("zyl"):
            g = int(dreh[3:])
            teile.append(pv.Cylinder(center=(0, 0, 0), direction=tuple(lokal(g)),
                                     radius=0.36 * d, height=1.5 * d))
        for f in federn:
            if f < 3:
                u = lokal(f)
                if abs(u[2]) > 0.7:
                    # Feder in Symbolachse: von der Spitze bis zur Ebene
                    pts = _helix(2.0 * d, 0.45 * d, 3.5)
                    teile.append(pv.Spline(pts, 80).tube(radius=0.07 * d))
                else:
                    # seitliche Feder: vom Knoten weg, mit Endplatte
                    Ru = _achsen_rahmen(u)
                    pts = _helix(1.6 * d, 0.28 * d, 3.0) @ Ru.T
                    teile.append(pv.Spline(pts, 70).tube(radius=0.06 * d))
                    platte = pv.Cube(center=(0, 0, -1.7 * d), x_length=0.9 * d, y_length=0.9 * d,
                                     z_length=0.12 * d)
                    platte.points = platte.points @ Ru.T
                    teile.append(platte)
            else:
                # Drehfeder: Spirale um die Achse des Freiheitsgrads
                u = lokal(f - 3)
                Ru = _achsen_rahmen(u)
                pts = _spirale(0.15 * d, 0.7 * d) @ Ru.T
                teile.append(pv.Spline(pts, 70).tube(radius=0.06 * d))
        if not teile:
            teile.append(pv.Sphere(radius=0.3 * d))
    mesh = pv.merge(teile) if len(teile) > 1 else teile[0]
    mesh = mesh.triangulate() if not mesh.is_all_triangles else mesh
    mesh.points = np.asarray(mesh.points, float) @ R.T
    return mesh


def _glyph(shape: str, d: float):
    """Die alten drei Grundformen - fuer Kontaktlager und den Rueckfall."""
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


def lager_abstand(size: float, dichte: float = 1.0) -> float:
    """Abstand der Symbole eines Linien- oder Flaechenlagers [m]: die
    Lagerdichte 1,0 setzt alle 5 % der Modellgroesse ein Symbol."""
    return 0.05 * size / max(float(dichte), 0.05)


def _polylinie_abtasten(P: np.ndarray, abstand: float) -> np.ndarray:
    """Punkte entlang eines Linienzugs, gleichmaessig im Abstand *abstand*
    (Anfang und Ende immer dabei)."""
    P = np.atleast_2d(np.asarray(P, float))
    if len(P) < 2:
        return P
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    L = float(seg.sum())
    if L <= 0:
        return P[:1]
    n = max(1, int(np.ceil(L / max(abstand, 1e-9))))
    s = np.linspace(0.0, L, n + 1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    out = []
    for si in s:
        k = min(int(np.searchsorted(cum, si, side="right")) - 1, len(seg) - 1)
        k = max(k, 0)
        t = 0.0 if seg[k] <= 0 else (si - cum[k]) / seg[k]
        out.append(P[k] + t * (P[k + 1] - P[k]))
    return np.asarray(out, float)


def _flaeche_abtasten(P: np.ndarray, abstand: float) -> np.ndarray:
    """Punkte im Inneren eines Drei- oder Vierecks im Raster *abstand*."""
    P = np.asarray(P, float)
    if len(P) == 3:
        A, B, C = P
        l = max(np.linalg.norm(B - A), np.linalg.norm(C - A), np.linalg.norm(C - B))
        k = max(1, int(np.ceil(l / max(abstand, 1e-9))))
        out = []
        for i in range(k):
            for j in range(k - i):
                u = (i + 1.0 / 3.0) / k
                v = (j + 1.0 / 3.0) / k
                out.append(A + u * (B - A) + v * (C - A))
        return np.asarray(out, float)
    A, B, C, D = P[:4]
    lu = max(np.linalg.norm(B - A), np.linalg.norm(C - D))
    lv = max(np.linalg.norm(D - A), np.linalg.norm(C - B))
    ku = max(1, int(np.ceil(lu / max(abstand, 1e-9))))
    kv = max(1, int(np.ceil(lv / max(abstand, 1e-9))))
    out = []
    for i in range(ku):
        for j in range(kv):
            u = (i + 0.5) / ku
            v = (j + 0.5) / kv
            out.append((1 - u) * (1 - v) * A + u * (1 - v) * B + u * v * C + (1 - u) * v * D)
    return np.asarray(out, float)


#: Hoechstzahl der Symbole je Linien- oder Flaechenlager
LAGERSYMBOLE_MAX = 4000


def _flaechenlager_flaechen(model: Model, ss) -> list:
    """[(Punkte der Flaeche, Normale nach aussen)] eines Flaechenlagers - die
    belegten Aussenflaechen seiner Elemente."""
    from ..supports import element_faces
    gezaehlt: dict = {}
    mitte: dict = {}
    for ei in (ss.elements or []):
        ei = int(ei)
        if not 0 <= ei < len(model.elements):
            continue
        e = model.elements[ei]
        for f in element_faces(model, ei, ss.face):
            key = tuple(sorted(int(n) for n in f))
            if key in gezaehlt:
                gezaehlt[key] = None
            else:
                gezaehlt[key] = [int(n) for n in f]
                mitte[key] = model.nodes[[int(n) for n in e.nodes]].mean(axis=0)
    out = []
    for key, f in gezaehlt.items():
        if f is None:
            continue
        P = model.nodes[f]
        n = np.cross(P[1] - P[0], P[2] - P[0])
        ln = np.linalg.norm(n)
        if ln <= 0:
            continue
        n = n / ln
        e = model.elements[0] if False else None      # noqa: F841 - nur der Lesbarkeit halber
        if len(f) >= 3 and np.dot(n, P.mean(axis=0) - mitte[key]) < 0:
            n = -n                                     # Volumen: nach aussen
        elif abs(np.dot(n, P.mean(axis=0) - mitte[key])) < 1e-12 and n[2] > 0:
            n = -n                                     # Schale: nach unten weisend
        out.append((P, n))
    return out


def lager_punkte(model: Model, obj, size: float, dichte: float = 1.0) -> tuple:
    """(Punkte, Richtungen) der Symbole eines Linien- oder Flaechenlagers.

    Linienlager: entlang des Linienzugs im Abstand der Lagerdichte, Richtung
    -z. Flaechenlager: im Raster ueber die belegten Flaechen seiner Elemente,
    Richtung die Flaechennormale nach aussen; ohne Elemente an den Knoten.
    """
    abstand = lager_abstand(size, dichte)
    if hasattr(obj, "elements"):
        flaechen = _flaechenlager_flaechen(model, obj)
        if not flaechen:
            nodes = [int(n) for n in (obj.nodes or []) if 0 <= int(n) < model.nn]
            pts = model.nodes[nodes] if nodes else np.zeros((0, 3))
            return pts, np.tile([0.0, 0.0, -1.0], (len(pts), 1))
        gesamt = sum(_polygonflaeche(P) for P, _n in flaechen)
        if gesamt > 0 and gesamt / abstand ** 2 > LAGERSYMBOLE_MAX:
            abstand = float(np.sqrt(gesamt / LAGERSYMBOLE_MAX))
        pts, ri = [], []
        for P, n in flaechen:
            Q = _flaeche_abtasten(P, abstand)
            pts.append(Q)
            ri.append(np.tile(n, (len(Q), 1)))
        return (np.vstack(pts) if pts else np.zeros((0, 3)),
                np.vstack(ri) if ri else np.zeros((0, 3)))
    nodes = [int(n) for n in (obj.nodes or []) if 0 <= int(n) < model.nn]
    if not nodes:
        return np.zeros((0, 3)), np.zeros((0, 3))
    P = model.nodes[nodes]
    L = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum()) if len(P) > 1 else 0.0
    if L / abstand > LAGERSYMBOLE_MAX:
        abstand = L / LAGERSYMBOLE_MAX
    pts = _polylinie_abtasten(P, abstand)
    return pts, np.tile([0.0, 0.0, -1.0], (len(pts), 1))


def _polygonflaeche(P) -> float:
    P = np.asarray(P, float)
    if len(P) < 3:
        return 0.0
    if len(P) == 3:
        return 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))
    return 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0]))
                       + np.linalg.norm(np.cross(P[2] - P[0], P[3] - P[0])))


def _richtungsgruppen(pts: np.ndarray, ri: np.ndarray) -> dict:
    """Punkte nach gerundeter Richtung buendeln (26 Richtungen): ein
    Glyphensatz je Richtung statt einer Drehung je Punkt."""
    gruppen: dict = {}
    for p, r in zip(pts, ri):
        q = tuple(int(x) for x in np.round(np.asarray(r, float) / max(np.abs(r).max(), 1e-12)))
        if q == (0, 0, 0):
            q = (0, 0, -1)
        gruppen.setdefault(q, []).append(p)
    return gruppen


def add_supports(plotter, model: Model, size: float, faktor: float = 1.0, nur=None,
                 dichte: float = 1.0):
    """Knoten-, Linien- und Flaechenlager sowie Kontaktlager zeichnen.

    ``faktor`` skaliert alle Symbole, ``Support.groesse`` zusaetzlich das
    einzelne Lager (Rechtsklick auf das Lager im Viewport). ``nur`` (Knoten-
    nummern) beschraenkt die Lager auf die sichtbaren Knoten, wenn Teile des
    Modells ausgeblendet sind. ``dichte`` ist die Lagerdichte: wie dicht die
    Symbole eines Linien- oder Flaechenlagers ueber die Linie bzw. Flaeche
    verteilt sind (1,0 = alle 5 % der Modellgroesse eines).
    """
    d0 = 0.012 * size * max(float(faktor), 0.05)
    sicht = None if nur is None else {int(i) for i in nur}

    def da(n) -> bool:
        return 0 <= int(n) < model.nn and (sicht is None or int(n) in sicht)

    # Knotenlager: nach Symbol und Groesse buendeln - ein Glyphensatz je Art
    gruppen: dict[tuple, list] = {}
    for s in model.supports:
        if not da(s.node):
            continue
        g = round(float(getattr(s, "groesse", 1.0) or 1.0), 3)
        gruppen.setdefault((lager_symbol(s), g), []).append(s.node)
    for i, ((key, g), nodes) in enumerate(sorted(gruppen.items(), key=str)):
        pts = model.nodes[nodes]
        plotter.add_mesh(pv.PolyData(pts).glyph(geom=lagerglyph(key, d0 * g),
                                                scale=False, orient=False),
                         color=FARBE_LAGER, name=f"supports{i}")
    # Linienlager: Symbole entlang der ganzen Linie und die Linie selbst
    for j, ls in enumerate(getattr(model, "line_supports", []) or []):
        nodes = [int(n) for n in ls.nodes if da(n)]
        if not nodes:
            continue
        pts, _ri = lager_punkte(model, ls, size, dichte)
        if not len(pts):
            continue
        key = lager_symbol(ls)
        plotter.add_mesh(pv.PolyData(pts).glyph(geom=lagerglyph(key, 0.55 * d0),
                                                scale=False, orient=False),
                         color=FARBE_LINIENLAGER, name=f"lsupports{j}")
        P = model.nodes[nodes]
        if len(P) > 1:
            plotter.add_mesh(pv.lines_from_points(P), color=FARBE_LINIENLAGER, line_width=4,
                             name=f"lsupports_linie{j}")
    # Flaechenlager: Symbole im Raster ueber die gebettete Flaeche, in
    # Richtung ihrer Normale
    for j, ss in enumerate(getattr(model, "surface_supports", []) or []):
        pts, ri = lager_punkte(model, ss, size, dichte)
        if not len(pts):
            continue
        if sicht is not None:
            nodes = {int(n) for n in (ss.nodes or [])}
            for ei in (ss.elements or []):
                if 0 <= int(ei) < len(model.elements):
                    nodes.update(int(n) for n in model.elements[int(ei)].nodes)
            if nodes and not (nodes & sicht):
                continue
        key = lager_symbol(ss)
        for k, (q, punkte) in enumerate(sorted(_richtungsgruppen(pts, ri).items())):
            plotter.add_mesh(pv.PolyData(np.asarray(punkte, float)).glyph(
                geom=lagerglyph(key, 0.45 * d0, richtung=np.asarray(q, float)),
                scale=False, orient=False),
                color=FARBE_FLAECHENLAGER, name=f"fsupports{j}_{k}")
    kontakt = [c.node for c in model.contact_supports if da(c.node)]
    if kontakt:
        pts = model.nodes[kontakt]
        plotter.add_mesh(pv.PolyData(pts).glyph(geom=_glyph("gelenk", d0),
                                                scale=False, orient=False),
                         color=FARBE_KONTAKT, name="csupports")


def support_at(model: Model, punkt, size: float, faktor: float = 1.0):
    """Das Knotenlager, das am dichtesten an ``punkt`` liegt - oder None.

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


def lager_at(model: Model, punkt, size: float, faktor: float = 1.0, dichte: float = 1.0):
    """Das Lager unter dem Zeiger: ("lager", i), ("linienlager", j) oder
    ("flaechenlager", k) - oder None. Knotenlager ueber ihr Symbol, Linien-
    und Flaechenlager ueber ihre Symbole entlang der Linie bzw. Flaeche."""
    if punkt is None or not model.nn:
        return None
    i = support_at(model, punkt, size, faktor)
    if i is not None:
        return ("lager", int(i))
    p = np.asarray(punkt, float).ravel()[:3]
    radius = max(1.5 * 0.012 * size * max(float(faktor), 0.05), 0.01 * size,
                 0.6 * lager_abstand(size, dichte))
    best, bestd = None, None
    for art, liste in (("linienlager", getattr(model, "line_supports", []) or []),
                       ("flaechenlager", getattr(model, "surface_supports", []) or [])):
        for j, obj in enumerate(liste):
            pts, _ri = lager_punkte(model, obj, size, dichte)
            if not len(pts):
                continue
            dist = float(np.linalg.norm(pts - p, axis=1).min())
            if dist <= radius and (bestd is None or dist < bestd):
                best, bestd = (art, j), dist
    return best


#: Farben der Lastsymbole
FARBE_LAST = "#c02020"          # Kraefte, Momente, Strecken- und Flaechenlasten
FARBE_LAST_WARM = "#e06a10"     # Temperatur: Erwaermung
FARBE_LAST_KALT = "#2060c0"     # Temperatur: Abkuehlung
FARBE_ZWANG = "#1e8a40"         # Zwangsverformung
#: Hoechstzahl der Pfeile je Lastart - mehr sieht man nicht, es kostet nur
PFEILE_MAX = 6000


def _pfeile(plotter, pts, vec, size: float, name: str, farbe: str = FARBE_LAST):
    """Pfeile, deren Spitze auf dem Angriffspunkt steht; Laenge nach Betrag."""
    if not len(pts):
        return
    P = np.asarray(pts, float).reshape(-1, 3)
    V = np.asarray(vec, float).reshape(-1, 3)
    if len(P) > PFEILE_MAX:
        wahl = np.linspace(0, len(P) - 1, PFEILE_MAX).astype(int)
        P, V = P[wahl], V[wahl]
    groesst = float(np.abs(V).max()) or 1.0
    V = V / groesst * 0.06 * size
    pd = pv.PolyData(P - V)
    pd["v"] = V
    plotter.add_mesh(pd.glyph(orient="v", scale="v", factor=1.0), color=farbe, name=name)


def _dreiecksmitten(model: Model, f, raender: dict = None, seiten: dict = None,
                    hoechstens: int = 24):
    """Punkte und Normalen auf einer Flaeche (mit oder ohne Netz) fuer Lastpfeile."""
    ring = (raender or {}).get(f.name)
    if ring is None:
        ring = f.randpunkte(model)
    if len(ring) < 3:
        return np.zeros((0, 3)), np.zeros((0, 3))
    sd = (seiten or {}).get(f.name)
    if sd is None:
        try:
            sd = f.randseiten_punkte(model)
        except Exception:                # noqa: BLE001
            sd = []
    P, Z = flaechen_dreiecke(ring, sd)
    if P is None:
        return np.zeros((0, 3)), np.zeros((0, 3))
    P = np.asarray(P, float)
    mitten, normalen = [], []
    i = 0
    while i < len(Z):
        k = int(Z[i])
        idx = [int(z) for z in Z[i + 1:i + 1 + k]]
        i += k + 1
        Q = P[idx]
        c = Q.mean(axis=0)
        n = np.zeros(3)
        for j in range(k):
            n += np.cross(Q[j], Q[(j + 1) % k])
        ln = float(np.linalg.norm(n))
        if ln <= 0:
            continue
        n = n / ln
        if k > 3:
            # ebenes Vieleck: mehrere Pfeile ueber die Flaeche verteilt
            for t in (0.5,) if k <= 4 else (0.5,):
                mitten.append(c)
                normalen.append(n)
        else:
            mitten.append(c)
            normalen.append(n)
    mitten = np.asarray(mitten, float).reshape(-1, 3)
    normalen = np.asarray(normalen, float).reshape(-1, 3)
    if len(mitten) > hoechstens:
        wahl = np.linspace(0, len(mitten) - 1, hoechstens).astype(int)
        mitten, normalen = mitten[wahl], normalen[wahl]
    return mitten, normalen


def _lastzahl(v: float, nachkomma: int = 2) -> str:
    """Lastgroesse als kurze Zahl: 12.5, 3, 0.25 - ohne Nachkommanullen."""
    s = f"{abs(float(v)):.{nachkomma}f}".rstrip("0").rstrip(".")
    return s or "0"


#: Lastart der Beschriftung -> Groesse in einheiten.Einheiten
LASTARTEN = {"kraft": "kraft", "moment": "moment", "strecke": "strecke",
             "flaeche": "flaechenlast", "temperatur": "temperatur", "zwang": "zwang"}
#: hoechstens so viele Lastwerte je Lastart beschriften
LASTWERTE_MAX = 60


def add_loads(plotter, model: Model, case, size: float, raender: dict = None,
              seiten: dict = None, beschriften: bool = False, textgroesse: int = 10,
              einheiten=None, ausser=None, knoten=None, ausser_flaechen=None,
              ausser_linien=None) -> list:
    """Alle Lasten eines Lastfalls ins Bild. Rueckgabe: die Einheiten der
    gezeichneten Lastarten (fuer die Kopfzeile), z. B. ["kN", "kN/m²"].

    ``beschriften`` schreibt die Lastgroesse als Zahl an die Pfeile (Knoten-
    lasten, Strecken- und Flaechenlasten, Objektlasten je Flaeche, Temperatur,
    Zwangsverformung); die Einheit steht in der Kopfzeile. ``einheiten``
    (einheiten.Einheiten, sonst ``model.einheiten``) bestimmt Einheit und
    Nachkommastellen der Zahlen. Lasten auf ausgeblendeten Teilen bleiben
    weg: ``ausser`` (Elementnummern), ``knoten`` (die sichtbaren Knoten, sonst
    alle), ``ausser_flaechen`` und ``ausser_linien`` (Namen).

    * Knotenlasten: rote Pfeile auf den Knoten
    * Streckenlasten auf Elementen (auch abschnittsweise): Pfeilreihen
    * Flaechenlasten auf Elementseiten: Pfeile an den Seitenmitten
    * Objektlasten (Geometrielasten, Linienlasten) auf der **Geometrie** -
      auch ohne Netz, so sieht man die Lasten eines eben eingelesenen
      RFEM-Modells; die daraus abgeleiteten Elementlasten (``_geo``) werden
      nicht ein zweites Mal gezeichnet
    * Lastfenster einer freien Rechtecklast als Rahmen
    * Temperaturlasten: Punkte (orange warm, blau kalt) am Element oder
      auf der Flaeche
    * Zwangsverformungen: gruene Pfeile am Knoten (Verschiebung), gruene
      Ringe fuer Verdrehungen
    """
    if case is None:
        return []
    from ..einheiten import Einheiten
    eh = einheiten or getattr(model, "einheiten", None) or Einheiten()
    weg_e = {int(i) for i in (ausser or ())}
    weg_f = set(ausser_flaechen or ())
    weg_l = set(ausser_linien or ())
    sicht_k = None if knoten is None else {int(i) for i in knoten}

    def knoten_da(n) -> bool:
        return 0 <= int(n) < model.nn and (sicht_k is None or int(n) in sicht_k)
    arten: list = []
    texte: dict = {}            # Lastart -> [(Punkt, Text)]

    def merken(art, punkt, text):
        if art not in arten:
            arten.append(art)
        texte.setdefault(art, []).append((np.asarray(punkt, float), text))

    def lz(wert_si, art):
        """Lastgroesse (SI) als kurze Zahl in der eingestellten Einheit."""
        return eh.zahl(abs(float(wert_si)), LASTARTEN[art], eh.nk_last)

    def spanne(a_si, b_si, art, pfeil="→"):
        return lz(a_si, art) if abs(a_si - b_si) < 1e-9 * max(1.0, abs(a_si)) \
            else f"{lz(a_si, art)}{pfeil}{lz(b_si, art)}"

    # ---- Kraefte: Knoten, Strecken, Elementseiten -------------------------
    pts, vec = [], []
    for l in case.nodal_loads:
        if getattr(l, "_geo", False) or not knoten_da(l.node):
            continue
        f = np.asarray(l.F[:3], float)
        if np.any(f) and 0 <= int(l.node) < model.nn:
            pts.append(model.nodes[int(l.node)])
            vec.append(f)
            merken("kraft", model.nodes[int(l.node)], lz(np.linalg.norm(f), "kraft"))
        mo = np.asarray(l.F[3:6], float) if len(l.F) >= 6 else np.zeros(3)
        if np.any(mo) and 0 <= int(l.node) < model.nn:
            merken("moment", model.nodes[int(l.node)], lz(np.linalg.norm(mo), "moment"))
    for bl in case.beam_loads:
        if getattr(bl, "_geo", False) or not 0 <= int(bl.elem) < len(model.elements) \
                or int(bl.elem) in weg_e:
            continue
        e = model.elements[bl.elem]
        X = model.nodes[e.nodes]
        T3, L = bm.local_axes(X[0], X[-1], getattr(e, "roll", 0.0) or 0.0)
        q1 = np.asarray(bl.q, float)
        q2 = np.asarray(bl.q2, float) if bl.q2 is not None else q1
        if bl.system == "local":
            q1, q2 = T3.T @ q1, T3.T @ q2
        a = max(0.0, float(getattr(bl, "a", 0.0) or 0.0))
        b = L if getattr(bl, "b", None) is None else min(float(bl.b), L)
        if b <= a or L <= 0:
            continue
        for t in np.linspace(0.1, 0.9, 4):
            x = a + t * (b - a)
            q = (1 - t) * q1 + t * q2
            if np.any(q):
                pts.append(X[0] + (x / L) * (X[-1] - X[0]))
                vec.append(q)
        if np.any(q1) or np.any(q2):
            merken("strecke", X[0] + (0.5 * (a + b) / L) * (X[-1] - X[0]),
                   spanne(np.linalg.norm(q1), np.linalg.norm(q2), "strecke"))
    for fl in case.face_loads:
        if getattr(fl, "_geo", False) or not 0 <= int(fl.elem) < len(model.elements) \
                or int(fl.elem) in weg_e:
            continue
        mitte = model._seitenmitte(fl.elem, fl.face)
        if fl.direction is not None:
            d = np.asarray(fl.direction, float)
            d = d / (np.linalg.norm(d) or 1.0)
        else:
            n = model._seitennormale(fl.elem, fl.face)
            if n is None:
                e = model.elements[fl.elem]
                X = model.nodes[e.nodes]
                n = np.cross(X[1] - X[0], X[2] - X[0])
                n = n / (np.linalg.norm(n) or 1.0)
            d = -n            # positiv drueckt in den Koerper hinein
        pts.append(mitte)
        vec.append(d * fl.p)
        merken("flaeche", mitte, lz(fl.p, "flaeche"))
    # ---- Objektlasten auf der Geometrie -------------------------------------
    warm, kalt = [], []
    rahmen_pts, rahmen_lines = [], []
    for gl in getattr(case, "geometrielasten", []) or []:
        if gl.art == "flaeche":
            f = model.flaechen.get(gl.ziel)
            flaechen = [f] if f is not None else []
        else:
            k = model.koerper.get(gl.ziel)
            flaechen = [model.flaechen[n] for n in (k.flaechen if k else [])
                        if n in model.flaechen]
        flaechen = [f for f in flaechen if f.name not in weg_f]
        if not flaechen:
            continue
        if gl.bereich and gl.bereich.get("art") == "rechteck":
            o = np.asarray(gl.bereich.get("ursprung", [0, 0, 0]), float)
            u = np.asarray(gl.bereich.get("u", [1, 0, 0]), float)
            v = np.asarray(gl.bereich.get("v", [0, 1, 0]), float)
            von = np.asarray(gl.bereich.get("von", [0, 0]), float)
            bis = np.asarray(gl.bereich.get("bis", [0, 0]), float)
            ecken = [o + von[0] * u + von[1] * v, o + bis[0] * u + von[1] * v,
                     o + bis[0] * u + bis[1] * v, o + von[0] * u + bis[1] * v]
            basis = len(rahmen_pts)
            rahmen_pts.extend(ecken)
            for j in range(4):
                rahmen_lines.extend([2, basis + j, basis + (j + 1) % 4])
        for f in flaechen:
            mitten, normalen = _dreiecksmitten(model, f, raender, seiten)
            if not len(mitten):
                continue
            if gl.bereich:
                halten = np.array([gl.trifft(m_) for m_ in mitten], bool)
                mitten, normalen = mitten[halten], normalen[halten]
                if not len(mitten):
                    continue
            if getattr(gl, "lastart", "druck") == "temperatur":
                (warm if gl.dT >= 0 else kalt).extend(mitten)
                merken("temperatur", mitten.mean(axis=0), f"ΔT {_lastzahl(gl.dT, 1)}")
                continue
            if gl.richtung:
                d = np.asarray(gl.richtung, float)
                d = d / (np.linalg.norm(d) or 1.0)
                D = np.repeat(d[None, :], len(mitten), axis=0)
                if gl.projiziert:
                    # nur die zugewandten Seiten tragen die Last
                    c = normalen @ d
                    halten = c < 0
                    mitten, D = mitten[halten], D[halten]
                    if not len(mitten):
                        continue
            else:
                D = -normalen       # positiv drueckt hinein
            werte = []
            for m_, d_ in zip(mitten, D):
                p = gl.wert(m_) if getattr(gl, "verlauf", None) else gl.p
                pts.append(m_)
                vec.append(d_ * p)
                werte.append(float(p))
            if werte:
                merken("flaeche", mitten.mean(axis=0), spanne(min(werte), max(werte), "flaeche", "…"))
    for ll in getattr(case, "linienlasten", []) or []:
        q1 = np.asarray(ll.q, float)
        q2 = np.asarray(ll.q2, float) if ll.q2 is not None else q1
        if ll.art == "stab":
            mem = model.members.get(ll.ziel)
            if mem is None or all(int(e) in weg_e for e in (mem.elements or [])):
                continue
            stuecke = []
            for e in mem.elements or []:
                if 0 <= int(e) < len(model.elements):
                    el = model.elements[int(e)]
                    stuecke.append((model.nodes[int(el.nodes[0])], model.nodes[int(el.nodes[-1])],
                                    getattr(el, "roll", 0.0) or 0.0))
        else:
            if ll.ziel in weg_l:
                continue
            ln = model.lines.get(ll.ziel)
            if ln is None:
                continue
            idx = [int(n) for n in ln.nodes if 0 <= int(n) < model.nn]
            if len(idx) < 2:
                continue
            X = model.nodes[idx]
            if (ln.typ or "polyline") != "polyline":
                try:
                    X = np.asarray(ln.punkte(model, TEILUNG_KURVE), float)
                except Exception:        # noqa: BLE001
                    pass
            stuecke = [(X[k], X[k + 1], 0.0) for k in range(len(X) - 1)]
        if not stuecke:
            continue
        laengen = [float(np.linalg.norm(B - A)) for A, B, _ in stuecke]
        gesamt = sum(laengen)
        A_ = max(0.0, float(ll.von))
        B_ = gesamt if ll.bis is None else min(float(ll.bis), gesamt)
        if B_ <= A_ or gesamt <= 0:
            continue
        n_pfeile = max(4, min(40, int(gesamt / max(size, 1e-9) * 40)))
        # Beschriftung in der Mitte des belasteten Abschnitts
        mitte_s = 0.5 * (A_ + B_)
        lauf = 0.0
        for (A, B, roll), L in zip(stuecke, laengen):
            if lauf <= mitte_s <= lauf + L and L > 0:
                merken("strecke", A + (mitte_s - lauf) / L * (B - A),
                       spanne(np.linalg.norm(q1), np.linalg.norm(q2), "strecke"))
                break
            lauf += L
        s0 = 0.0
        for (A, B, roll), L in zip(stuecke, laengen):
            if L <= 0:
                s0 += L
                continue
            for x in np.linspace(s0, s0 + L, max(2, int(round(n_pfeile * L / gesamt)) + 1))[:-1] \
                    + 0.5 * L / max(2, int(round(n_pfeile * L / gesamt)) + 1):
                if x < A_ or x > B_:
                    continue
                t = (x - A_) / (B_ - A_)
                q = (1 - t) * q1 + t * q2
                if ll.system == "local" and ll.art == "stab":
                    T3, _ = bm.local_axes(A, B, roll)
                    q = T3.T @ q
                if np.any(q):
                    pts.append(A + (x - s0) / L * (B - A))
                    vec.append(q)
            s0 += L
    _pfeile(plotter, pts, vec, size, "loads")
    if rahmen_pts:
        plotter.add_mesh(pv.PolyData(np.asarray(rahmen_pts, float),
                                     lines=np.asarray(rahmen_lines)),
                         color=FARBE_LAST, line_width=2, name="lastfenster")
    # ---- Temperatur auf Elementen -------------------------------------------
    for tl in case.temp_loads:
        if getattr(tl, "_geo", False) or not 0 <= int(tl.elem) < len(model.elements) \
                or int(tl.elem) in weg_e:
            continue
        e = model.elements[tl.elem]
        c = model.nodes[[int(n) for n in e.nodes]].mean(axis=0)
        (warm if tl.dT >= 0 else kalt).append(c)
        merken("temperatur", c, f"ΔT {_lastzahl(tl.dT, 1)}")
    d = max(4.0, 0.012 * size)
    for punkte, farbe, name in ((warm, FARBE_LAST_WARM, "temp_warm"),
                                (kalt, FARBE_LAST_KALT, "temp_kalt")):
        if punkte:
            P = np.asarray(punkte, float).reshape(-1, 3)
            if len(P) > PFEILE_MAX:
                P = P[np.linspace(0, len(P) - 1, PFEILE_MAX).astype(int)]
            plotter.add_points(P, color=farbe, point_size=9, render_points_as_spheres=True,
                               name=name)
    # ---- Zwangsverformungen -------------------------------------------------
    zpts, zvec, ringe = [], [], []
    for zv in getattr(case, "zwangsverformungen", []) or []:
        if not knoten_da(zv.node):
            continue
        X = model.nodes[int(zv.node)]
        u = np.array([float(zv.u[k]) if k in zv.dofs else 0.0 for k in range(3)])
        if np.any(u):
            zpts.append(X)
            zvec.append(u)
            merken("zwang", X, eh.zahl(np.linalg.norm(u), "zwang"))
        if any(k in zv.dofs and zv.u[k] for k in (3, 4, 5)):
            ringe.append(X)
    _pfeile(plotter, zpts, zvec, size, "zwang", FARBE_ZWANG)
    if ringe:
        plotter.add_points(np.asarray(ringe, float), color=FARBE_ZWANG, point_size=13,
                           render_points_as_spheres=True, name="zwang_drehung")
    # ---- Lastwerte als Zahlen ----------------------------------------------
    if beschriften and texte:
        punkte, zeilen = [], []
        for art, liste in texte.items():
            if len(liste) > LASTWERTE_MAX:
                wahl = np.linspace(0, len(liste) - 1, LASTWERTE_MAX).astype(int)
                liste = [liste[i] for i in wahl]
            for q, s in liste:
                punkte.append(q)
                zeilen.append(s)
        if punkte:
            plotter.add_point_labels(np.asarray(punkte, float), zeilen, font_size=int(textgroesse),
                                     text_color=FARBE_LAST, shape=None, show_points=False,
                                     always_visible=True, name="lastwerte")
    return [eh.einheit(LASTARTEN[a]) for a in arten if a in LASTARTEN]


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
              ueberschrift: str = "", einheiten=None) -> list:
    """Die Kennzahlen des gezeigten Ergebnisses als Textzeilen.

    Das sind die Zahlen, nach denen zuerst gefragt wird: groesste Ausnutzung,
    kleinste und groesste Verformung, kleinste und groesste Schnittgroesse -
    jeweils **mit dem Ort**, denn ein Zahlenwert ohne Ort ist kein Ergebnis.
    Steht in *groesse* eine Schnittgroesse, wird nur diese ausgeschrieben.

    Die Zeilen sind auf feste Spalten gesetzt (Schreibmaschinenschrift), damit
    die Zahlen im Bild untereinander stehen und die Zeile nicht ueber das
    Modell laeuft. Einheiten und Nachkommastellen kommen aus *einheiten*
    (einheiten.Einheiten, sonst ``model.einheiten``).
    """
    from ..einheiten import Einheiten
    E = einheiten or getattr(model, "einheiten", None) or Einheiten()
    zeilen = []
    if ueberschrift:
        zeilen.append(str(ueberschrift))
    def zeile(name, lo, ort_lo, hi, ort_hi, einheit):
        return (f"{name:<6s}{lo:>10s} {ort_lo:<11s}{hi:>10s} {ort_hi:<11s}"
                f"[{einheit}]")

    def z(wert_si, art):
        return E.text(wert_si, art, mit_einheit=False)

    u = displacement_of(res)
    if u is not None and len(u):
        mag = np.linalg.norm(u[:, :3], axis=1)
        k = int(np.nanargmax(mag)) if np.isfinite(mag).any() else 0
        zeilen.append(zeile("u", "", "", z(mag[k], "verformung"),
                            f"Knoten {k}", E.einheit("verformung")))
        for j, nm in enumerate(("ux", "uy", "uz")):
            zeilen.append(zeile(nm, z(u[:, j].min(), "verformung"), "",
                                z(u[:, j].max(), "verformung"), "", E.einheit("verformung")))
    reihe = (groesse,) if groesse in SCHNITTGROESSEN else SCHNITTGROESSEN
    grenzen = schnittgroessen_grenzen(model, res, reihe)
    for q in reihe:
        if q not in grenzen:
            continue
        lo, e_lo, hi, e_hi = grenzen[q]
        art = "moment" if q in ("Mt", "My", "Mz") else "kraft"
        zeilen.append(zeile(q, z(lo, art), _stabname(model, e_lo, 10),
                            z(hi, art), _stabname(model, e_hi, 10), E.einheit(art)))
    # Verdrehungen - nur wo es Staebe oder Schalen gibt, sonst sind sie null
    if u is not None and len(u) and u.shape[1] >= 6 and np.abs(u[:, 3:6]).max() > 0:
        for j, nm in enumerate(("phix", "phiy", "phiz")):
            zeilen.append(zeile(nm, f"{u[:, 3 + j].min() * 1000:.3f}", "",
                                f"{u[:, 3 + j].max() * 1000:.3f}", "", "mrad"))
    # Auflagerkraefte: kleinste und groesste je Richtung mit Knoten
    R = getattr(res, "reactions", None)
    reakt = (("Rx", "kraft"), ("Ry", "kraft"), ("Rz", "kraft"),
             ("Mx", "moment"), ("My", "moment"), ("Mz", "moment"))
    if R is None and getattr(res, "r_min", None) is not None:
        R = None
        rmin, rmax = res.r_min, res.r_max
        for j, (nm, art) in enumerate(reakt):
            if not np.any(rmin[:, j]) and not np.any(rmax[:, j]):
                continue
            a, b = int(np.argmin(rmin[:, j])), int(np.argmax(rmax[:, j]))
            zeilen.append(zeile(nm, z(rmin[a, j], art), f"Knoten {a}",
                                z(rmax[b, j], art), f"Knoten {b}", E.einheit(art)))
    elif R is not None and len(R):
        for j, (nm, art) in enumerate(reakt):
            if j >= R.shape[1] or not np.any(R[:, j]):
                continue
            a, b = int(np.argmin(R[:, j])), int(np.argmax(R[:, j]))
            zeilen.append(zeile(nm, z(R[a, j], art), f"Knoten {a}",
                                z(R[b, j], art), f"Knoten {b}", E.einheit(art)))
    vm = getattr(res, "node_vm_max", None)
    if vm is None:
        vm = getattr(res, "node_vm", None)
    if vm is not None and len(vm) and np.isfinite(vm).any():
        k = int(np.nanargmax(vm))
        zeilen.append(zeile("sig_v", "", "", z(float(vm[k]), "spannung"),
                            f"Knoten {k}", E.einheit("spannung")))
    werte = dict(util or {})
    if not werte:
        for i, d in (getattr(res, "beam_forces", None) or {}).items():
            if d.get("util") is not None:
                werte[i] = d["util"]
    if werte:
        i = max(werte, key=lambda k: werte[k])
        zeilen.append(f"max. Ausnutzung {werte[i]:.{E.nk_ausnutzung}f} an {_stabname(model, i)}"
                      + ("  - ueberschritten!" if werte[i] > 1.0 else ""))
    return zeilen


def kopfzeile(model: Model, res, ergebnisname: str = "", faerbung: str = "",
              verlauf: str = "", faktor: float = 0.0, lastfall: str = "",
              einheiten: list = None) -> list:
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
        if einheiten:
            zeilen.append("  [" + ", ".join(einheiten) + "]")
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
    if einheiten:
        zeilen.append("  Lasten [" + ", ".join(einheiten) + "]")
    return zeilen
