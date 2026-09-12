"""Darstellung des Modells und der Ergebnisse im 3D-Viewport (pyvista)."""
from __future__ import annotations

import numpy as np
import pyvista as pv

from ..model import Model, NDOF
from ..elements import beam3d as bm
from .. import mesher
from .. import elemente as EL

VTK_LINE, VTK_TRI, VTK_QUAD, VTK_TETRA, VTK_HEX, VTK_TET10 = 3, 5, 9, 10, 12, 24


def kanten_vor_flaechen() -> bool:
    """Linien gewinnen gegen die Flaeche, auf der sie liegen.

    Eine Bauteilkante ist zweimal da: als Rand der Flaeche **und** als Linie
    des Modells. Beide liegen auf demselben Fleck im Tiefenspeicher, und ohne
    Regel entscheidet dort die Rundung, welche von beiden gewinnt - Bildpunkt
    fuer Bildpunkt. In der gefuellten Ansicht des Drehlagermodells liess das
    die Umrisse ausfransen und stellenweise ganz verschwinden: Bohrungen,
    Rippen und Blechkanten waren nicht mehr zu sehen, obwohl sie gezeichnet
    wurden. Im Drahtmodell fiel es nicht auf - dort gibt es keine Flaeche,
    gegen die eine Linie verlieren koennte.

    VTK kennt dafuer den Polygonversatz: die Flaechen ruecken um Bruchteile
    einer Tiefenstufe nach hinten, die Linien nach vorn. Die Einstellung gilt
    fuer **alle** Abbilder (sie ist eine Klasseneigenschaft von vtkMapper),
    darum steht sie hier einmal und nicht an 40 Zeichenbefehlen.

    Gibt zurueck, ob die Einstellung steht - damit ein Test es nachsehen kann.
    """
    try:
        import vtk
    except ImportError:                  # noqa: BLE001 - ohne VTK kein Bild
        return False
    vtk.vtkMapper.SetResolveCoincidentTopologyToPolygonOffset()
    # Flaechen nach hinten (Faktor 2, 2 Tiefenstufen), Linien 4 Stufen nach
    # vorn. Mehr braucht es nicht: schon eine Stufe entscheidet den Streit,
    # mehr liesse eine Linie vor einer Flaeche schweben, die davor liegt.
    vtk.vtkMapper.SetResolveCoincidentTopologyPolygonOffsetFaces(1)
    vtk.vtkMapper.SetResolveCoincidentTopologyPolygonOffsetParameters(2.0, 2.0)
    vtk.vtkMapper.SetResolveCoincidentTopologyLineOffsetParameters(0.0, -4.0)
    return vtk.vtkMapper.GetResolveCoincidentTopology() != 0


KANTEN_VORN = kanten_vor_flaechen()

#: Elementtyp -> (VTK-Zelltyp, Knotenzahl) aus dem Elementverzeichnis. Die
#: Grenzschichten ohne Dicke werden als (flacher) Keil bzw. Hexaeder gezeichnet.
CELL_MAP = {t: (a.vtk, a.knoten) for t, a in EL.ELEMENTE.items()}

STATUS_COLOR = {"offen": "#9e9e9e", "Kontakt": "#1565c0", "Haften": "#2e7d32", "Gleiten": "#e65100"}

#: Farben der Modellsymbole
FARBE_KNOTEN = "#2f4f6f"
FARBE_KNOTEN_FREI = "#e07000"      # Knoten, der (noch) an keinem Element haengt
FARBE_LAGER = "#207020"
#: Farbe je Lagerart (12.09.2026, "man erkennt das optisch schlecht"): die
#: Farbe sagt auf einen Blick, was das Lager haelt
FARBEN_LAGERART = {"fest": "#1f3b73", "gelenkig": "#1e7b34", "gleitend": "#d97706",
                   "feder": "#7c3aed", "drehlager": "#5b6b7b", "frei": "#9aa4ae"}
FARBE_LAGER_NICHTLINEAR = "#b00020"
#: Grundmass der Lagersymbole als Anteil der Modellgroesse (bis 12.09.2026
#: 0,012 - die Symbole gingen im Bild unter, siehe Benutzerhandbuch Lager)
LAGER_GRUNDMASS = 0.015
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


#: Bis zu diesem Winkel gilt die Ecke zwischen zwei Randseiten als glatt - die
#: beiden Seiten sind dann geometrisch eine.
GLATTE_ECKE = 15.0


def seiten_an_ecken(seiten: list, ecken) -> list:
    """Den Rand an den **benannten** Eckpunkten in vier Seiten zerlegen.

    RFEM beschreibt ein Viereck nicht nur ueber seine Randlinien, sondern
    zusaetzlich ueber vier ausdrueckliche Eckknoten - im Drehlagermodell bei
    allen 782 Vierecken genau vier, auch bei den vieren, deren Rand aus
    **fuenf** Linien besteht. Damit ist nichts zu raten: die Ecken sagen, wo
    zu teilen ist. Nur wenn sie fehlen, faellt es auf
    :func:`seiten_zusammenfassen` zurueck, das die flachste Ecke sucht.

    Rueckgabe die vier Seiten im Umlauf, oder eine leere Liste, wenn sich der
    Rand nicht so zerlegen laesst.
    """
    S = [np.asarray(x, float) for x in (seiten or []) if len(np.asarray(x, float)) >= 2]
    E = np.asarray(ecken, float).reshape(-1, 3) if ecken is not None else np.zeros((0, 3))
    if len(E) != 4 or len(S) < 4:
        return []
    alle = np.vstack(S)
    tol = 1e-6 * float(np.linalg.norm(alle.max(axis=0) - alle.min(axis=0)) or 1.0)
    tol = max(tol, 1e-12)
    beginn = [i for i, x in enumerate(S)
              if float(np.linalg.norm(E - x[0], axis=1).min()) <= tol]
    if len(beginn) != 4:
        return []
    aus = []
    for k in range(4):
        i, j = beginn[k], beginn[(k + 1) % 4]
        anzahl = (j - i) % len(S) or len(S)
        kette = S[i]
        for t in range(1, anzahl):
            kette = np.vstack([kette, S[(i + t) % len(S)][1:]])
        aus.append(kette)
    return aus


def seiten_zusammenfassen(seiten: list, ziel: int = 4) -> list:
    """Randseiten an glatten Ecken zusammenfassen, bis ``ziel`` uebrig sind.

    RFEM teilt eine gerade Kante schon einmal in zwei Linien. Im
    Drehlagermodell hat der Mantel des Bolzens (F589, F590, F1670, F1671)
    darum fuenf Randseiten: eine seiner beiden Geraden besteht aus einem
    1-mm- und einem 68-mm-Stueck, die in derselben Richtung weiterlaufen.
    Geometrisch ist es eine Vierseitflaeche. Ohne das Zusammenfassen faellt
    sie auf den Faecher um den Schwerpunkt zurueck, und dessen Dreiecke laufen
    bei einem Halbkreis quer durch den Koerper - die Sehne statt des Bogens.
    Genau das war im Bild von V30 zu sehen.

    Zusammengefasst wird immer die **flachste** Ecke, und nur, solange sie
    flacher als :data:`GLATTE_ECKE` ist: eine echte Kante bleibt eine Kante.
    Bleiben danach mehr als ``ziel`` Seiten, kommt die Liste unveraendert
    zurueck.
    """
    S = [np.asarray(x, float) for x in (seiten or []) if len(np.asarray(x, float)) >= 2]
    if len(S) != len(seiten or []):
        return list(seiten or [])
    grenze = np.cos(np.deg2rad(GLATTE_ECKE))
    while len(S) > ziel:
        bester, wert = -1, grenze
        for i in range(len(S)):
            j = (i + 1) % len(S)
            a = S[i][-1] - S[i][-2]
            b = S[j][1] - S[j][0]
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na <= 0 or nb <= 0:
                continue
            c = float(a @ b) / (na * nb)
            if c > wert:
                bester, wert = i, c
        if bester < 0:
            break
        j = (bester + 1) % len(S)
        S[bester] = np.vstack([S[bester], S[j][1:]])
        S.pop(j)
    return S


def eben_mit_loechern(ring, loecher):
    """Ebene Flaeche mit Innenraendern in Dreiecke teilen: (Punkte, Dreiecke).

    Ohne das geht das Randpolygon als **eine** Zelle an VTK, und VTK fuellt
    sie: ein Ring erscheint als Scheibe, eine Bohrung verschwindet. Am
    Drehlagermodell betrifft das alle 100 Flaechen mit Oeffnungen - und daran
    ist die Beurteilung der Geometrie mehrfach haengengeblieben, obwohl
    Huelle und Netz nachweislich stimmen.

    Trianguliert wird mit demselben Verfahren wie im Vernetzer
    (:func:`mesher3d._dreiecke_2d`), nur ohne Innenpunkte: fuers Bild
    genuegen die Randpunkte, und dann stehen die Punkte des Ergebnisses in
    derselben Reihenfolge wie die uebergebenen Ringe - sie lassen sich also
    unmittelbar in den Raum zuruecknehmen.

    Rueckgabe (None, None), wenn sich nichts bilden laesst.
    """
    from ..mesher3d import _dreiecke_2d
    A = np.asarray(ring, float)
    ringe3 = [A] + [np.asarray(L, float) for L in (loecher or []) if len(L) >= 3]
    if len(ringe3) < 2 or len(A) < 3:
        return None, None
    # Lokales Achsenkreuz aus der Newell-Normalen des Aussenrands
    n = np.cross(A, np.roll(A, -1, axis=0)).sum(axis=0)
    nl = float(np.linalg.norm(n))
    if nl <= 0:
        return None, None
    n = n / nl
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    t1 = np.cross(n, ref)
    t1 /= np.linalg.norm(t1) or 1.0
    t2 = np.cross(n, t1)
    o = A[0]
    ringe2 = [np.column_stack([(R - o) @ t1, (R - o) @ t2]) for R in ringe3]
    try:
        P2, T, _ = _dreiecke_2d(ringe2, 0.0)
    except Exception:                    # noqa: BLE001 - ein Bild darf nie sperren
        return None, None
    P3 = np.vstack(ringe3)
    if not len(T) or len(P2) != len(P3):
        return None, None
    return P3, np.asarray(T, int)


def flaechen_dreiecke(ring, seiten=None, loecher=None, typ: str = "", ecken=None):
    """Eine Flaeche fuers Bild: (Punkte, Zellen als VTK-Liste).

    Eben ohne Loecher: das Randpolygon als **eine** Zelle. Eben mit Loechern:
    Dreiecke, Aussenrand minus Innenraender (:func:`eben_mit_loechern`).
    Krumm mit vier Seiten: eine Coons-Flaeche aus Dreiecken; mehr Seiten
    werden an den benannten Ecken zerlegt (:func:`seiten_an_ecken`) oder sonst
    an ihren glatten Ecken zusammengefasst (:func:`seiten_zusammenfassen`).
    Sonst ein Faecher um den Schwerpunkt - das ist fuer eine schwach
    gewoelbte Flaeche besser als gar nichts, fuer eine stark gekruemmte aber
    falsch: seine Dreiecke laufen durch den Koerper. Im Drehlagermodell faellt
    keine der 1375 Flaechen mehr in den Faecher.

    **Was eben ist, sagt die Quelldatei - und die Geometrie.** ``typ`` ist die
    Geometrieart (``"eben"``, ``"regelflaeche"``, ``"beschnitten"``); gewoelbt
    gezeichnet wird, was **eines von beiden** sagt. Beide koennen nur in eine
    Richtung irren, darum ergaenzen sie sich: der Typ ist bei einer von Hand
    gebauten Flaeche die blosse Vorgabe „eben" und weiss nichts. Der
    geometrische Test kann eine gewoelbte Flaeche fuer eben halten, wenn er zu
    grobe Punkte bekommt - befragt man die vier Eckknoten von F1693, liegen
    sie alle in der Ebene x = 0, obwohl die Flaeche sich bis x = 12,5 mm
    woelbt: die halbe Wand einer Bohrung, gezeichnet als Platte quer durch die
    Bohrung. Eine ebene Flaeche fuer gewoelbt halten kann er nicht. Am
    Drehlagermodell stimmen beide Wege in allen 1375 Faellen ueberein.
    """
    from ..model import polygon_eben
    ring = np.asarray(ring, float)
    if len(ring) < 3:
        return None, None
    # Gewoelbt, wenn die Quelldatei es sagt **oder** die abgetasteten
    # Randpunkte es zeigen. Beides zusammen, weil beide Wege nur in **eine**
    # Richtung irren koennen: der Typ ist bei einer von Hand gebauten Flaeche
    # schlicht die Vorgabe "eben" und weiss nichts; der geometrische Test kann
    # eine gewoelbte Flaeche fuer eben halten, wenn er zu grob abgetastete
    # Punkte bekommt - eine ebene fuer gewoelbt kann er nicht halten. Am
    # Drehlagermodell stimmen beide in allen 1375 Faellen ueberein: 589 Plane
    # eben, 782 Quadrangle und 4 Trimmed gewoelbt.
    krumm = str(typ) in ("regelflaeche", "beschnitten") or not polygon_eben(ring)
    if not krumm:
        if loecher:
            P, D = eben_mit_loechern(ring, loecher)
            if P is not None:
                return P, np.hstack([np.full((len(D), 1), 3), D]).ravel().tolist()
        return ring, [len(ring), *range(len(ring))]
    if seiten is not None and len(seiten) != 4:
        seiten = (seiten_an_ecken(seiten, ecken)
                  or (seiten_zusammenfassen(list(seiten)) if len(seiten) > 4
                      else list(seiten)))
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
                    ausser_flaechen=None, ausser_koerper=None, log: list = None):
    """Die Netze der Geometrie ohne Elemente: (Flaechen, Raender, Koerperkanten).

    „Ohne Elemente" heisst: die Flaeche traegt selbst keine und gehoert auch
    zu keinem vernetzten Koerper. Wo ein Netz steht, wird das Netz gezeichnet.

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
    # Wo ein Netz steht, wird das Netz gezeichnet. Die Randflaechen eines
    # vernetzten Koerpers liegen deckungsgleich auf seiner Netzhaut; beide zu
    # malen heisst, dass um jeden Bildpunkt zwei Dreiecke streiten und mal das
    # eine, mal das andere gewinnt. Am Drehlagermodell waren das 39103
    # Geometriedreiecke ueber 489376 Elementen, jedes Mal 1,5 Sekunden Aufbau.
    # Eine Flaeche, die auch an einem **unvernetzten** Koerper haengt, bleibt:
    # dort gibt es kein Netz, das sie ersetzen koennte.
    vom_netz = {fn for k in koerper.values() if k.elemente for fn in k.flaechen}
    vom_netz -= {fn for k in koerper.values() if not k.elemente for fn in k.flaechen}

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

    #: Innenraender je Flaeche. Eigener Zwischenspeicher, damit das Abtasten
    #: der Oeffnungsringe nicht bei jedem Bildaufbau anfaellt.
    loecher: dict = {}

    def loecher_von(name, f):
        r = loecher.get(name)
        if r is None:
            try:
                r = f.oeffnungspunkte(model)
            except Exception:            # noqa: BLE001
                r = []
            loecher[name] = r
        return r

    def ecken_von(f):
        """Die vier benannten Eckpunkte einer Flaeche - oder None."""
        e = [int(x) for x in (getattr(f, "ecken", None) or [])]
        if len(e) != 4 or max(e) >= len(model.nodes):
            return None
        return model.nodes[e]

    #: Gewoelbte Flaechen mit Oeffnungen: dort sind die Loecher im Bild nicht
    #: ausgespart. Im Drehlagermodell kommt das nicht vor - alle 100 Flaechen
    #: mit Oeffnungen sind eben. Traefe es zu, waere es ein Fehler mit Namen
    #: und keine stille Auslassung.
    krumm_mit_loch: list = []
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
        if name in vom_netz:
            # Die Umrisse bleiben - sie liegen als Linien ueber dem Netz und
            # zeigen, wo die Bauteilkanten laufen. Nur die Flaeche selbst
            # zeichnet das Netz.
            continue
        loch = loecher_von(name, f)
        if loch and str(getattr(f, "typ", "")) in ("regelflaeche", "beschnitten"):
            krumm_mit_loch.append(name)
        P, Z = flaechen_dreiecke(ring, seiten_von(name, f), loch,
                                 typ=str(getattr(f, "typ", "") or ""),
                                 ecken=ecken_von(f))
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
    if krumm_mit_loch and log is not None:
        log.append(f"WARNUNG: {len(krumm_mit_loch)} gewölbte Flächen tragen Öffnungen "
                   f"(z. B. {', '.join(krumm_mit_loch[:4])}) - dort sind die Löcher "
                   "im Bild nicht ausgespart. Am Drehlagermodell kommt das nicht vor: "
                   "alle 100 Flächen mit Öffnungen sind eben.")
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
    el = element_at(model, punkt, TYPEN_STAEBE)
    if el is None:
        return None
    for name, mem in (model.members or {}).items():
        if el in (mem.elements or []):
            return name
    return None


#: Elementtypen je Sichtbarkeitsschalter
TYPEN_STAEBE = EL.STAB_TYPEN + ("feder",)
TYPEN_FLAECHEN = EL.SCHALEN_TYPEN + EL.EBENE_TYPEN
TYPEN_VOLUMEN = EL.VOLUMEN_TYPEN + ("grenzschicht6", "grenzschicht8")


#: Achsen der Schnittebene: Name -> Normale
SCHNITTACHSEN = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def schneiden(grid, achse: str, lage: float, umgekehrt: bool = False):
    """Das Gitter an einer Ebene aufschneiden - Blick ins Innere.

    Gezeichnet wird von einem Volumennetz immer nur die **Aussenhaut**: die
    inneren Tetraederflaechen liegen zwischen zwei Elementen und werden in
    keinem FE-Programm gezeichnet. Wer beim Zoomen durch die Oberflaeche
    faehrt, sieht darum die Innenseite der gegenueberliegenden Haut - das
    sieht hohl aus, ist es aber nicht.

    Ein Schnitt zeigt, was wirklich drin steht: Fuellung, Netzdichte und
    Elementform im Inneren mit einem Blick. ``lage`` ist der Anteil 0 … 1
    laengs der Achse durch den Huellquader; ``umgekehrt`` dreht die Seite, die
    stehenbleibt.

    Rueckgabe das geschnittene Gitter - oder das unveraenderte, wenn der
    Schnitt nichts uebrig liesse (dann waere die Ansicht leer, und das ist
    keine Auskunft).
    """
    if grid is None or not getattr(grid, "n_cells", 0):
        return grid
    n = SCHNITTACHSEN.get(str(achse).lower())
    if n is None:
        return grid
    b = grid.bounds
    k = {"x": 0, "y": 1, "z": 2}[str(achse).lower()]
    lo, hi = float(b[2 * k]), float(b[2 * k + 1])
    t = min(max(float(lage), 0.0), 1.0)
    ursprung = [0.0, 0.0, 0.0]
    ursprung[k] = lo + t * (hi - lo)
    try:
        teil = grid.clip(normal=n, origin=ursprung, invert=not umgekehrt)
    except Exception:                       # noqa: BLE001 - dann eben ungeschnitten
        return grid
    return teil if getattr(teil, "n_cells", 0) else grid


def to_grid(model: Model, typen=None, ausser=None, nur=None) -> pv.UnstructuredGrid:
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
        if nur is not None and i not in nur:
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


def teilnetz(model: Model, elemente) -> pv.UnstructuredGrid:
    """Ein Gitter aus **nur** den genannten Elementen.

    :func:`to_grid` laeuft ueber alle Elemente des Modells. Wer ein einzelnes
    Volumen aufleuchten lassen will, zahlt damit bei 389.000 Tetraedern ueber
    eine Sekunde je Mausbewegung - fuer ein paar hundert Zellen. Hier wird nur
    ueber die genannten Elemente gelaufen; die Punkte bleiben alle
    Modellknoten, damit Knotenwerte weiter passen.
    """
    cells, types, idx = [], [], []
    n_el = len(model.elements)
    for i in elemente:
        i = int(i)
        if not 0 <= i < n_el:
            continue
        e = model.elements[i]
        art = CELL_MAP.get(e.typ)
        if art is None:
            continue
        ct, n = art
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


def lager_art(support) -> str:
    """Die Lagerart fuer Farbe und Beschriftung: fest (alles gehalten),
    gelenkig (alle Verschiebungen, Verdrehungen frei), gleitend (eine
    Verschiebung frei), feder (mindestens eine Feder), drehlager (nur
    Verdrehungen gehalten) oder frei."""
    fest, federn = _fhg_lage(support)
    T = {d for d in fest if d < 3}
    if federn:
        return "feder"
    if T == {0, 1, 2} and {3, 4, 5} <= fest:
        return "fest"
    if T == {0, 1, 2}:
        return "gelenkig"
    if T:
        return "gleitend"
    if fest:
        return "drehlager"
    return "frei"


def lager_farbe(support) -> str:
    return FARBEN_LAGERART.get(lager_art(support), FARBE_LAGER)


def lager_text(support) -> str:
    """Kurztext fuer die Lagerbeschriftung: fest, gelenkig, sonst die
    gehaltenen Freiheitsgrade (u x y z, r x y z), Federn mit k, nichtlineare
    Wirkung (Ausfall, Schlupf, Reibung, Grenzkraft) mit einem Stern."""
    art = lager_art(support)
    fest, federn = _fhg_lage(support)
    if art == "fest":
        text = "fest"
    elif art == "gelenkig":
        text = "gelenkig"
    else:
        teile = []
        u = "".join("xyz"[d] for d in sorted(fest) if d < 3)
        r = "".join("xyz"[d - 3] for d in sorted(fest) if d >= 3)
        if u:
            teile.append("u" + u)
        if r:
            teile.append("r" + r)
        ku = "".join("xyz"[d] for d in sorted(federn) if d < 3)
        kr = "".join("xyz"[d - 3] for d in sorted(federn) if d >= 3)
        if ku:
            teile.append("ku" + ku)
        if kr:
            teile.append("kr" + kr)
        text = " ".join(teile) or "frei"
    if getattr(support, "nonlinear", False):
        text += " *"
    return text


def lager_texte(model: Model, nur=None) -> tuple:
    """(Punkte, Texte) der Lagerbeschriftung fuer die Knotenlager."""
    sicht = None if nur is None else {int(i) for i in nur}
    punkte, texte = [], []
    for s in model.supports:
        n = int(s.node)
        if not (0 <= n < model.nn) or (sicht is not None and n not in sicht):
            continue
        punkte.append(model.nodes[n])
        texte.append(lager_text(s))
    return punkte, texte


def _grundplatte(d: float, z: float, breite: float) -> list:
    """Platte mit Schraffur darunter - der Boden des klassischen Lagerbilds,
    an dem man ein Lager sofort erkennt."""
    teile = [pv.Cube(center=(0, 0, z), x_length=breite, y_length=breite, z_length=0.12 * d)]
    n = 5
    for k in range(n):
        x = -0.5 * breite + (k + 0.5) * breite / n
        # kurzer Strich schraeg unter der Platte (45 Grad in der x-z-Ebene)
        strich = pv.Cylinder(center=(x - 0.15 * d, 0, z - 0.32 * d), direction=(1, 0, -1),
                             radius=0.035 * d, height=0.5 * d)
        teile.append(strich)
    return teile


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
        teile.extend(_grundplatte(d, -1.26 * d, 2.2 * d))
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
            teile.extend(_grundplatte(d, -2.4 * d, max(lx, ly))[1:])
        elif grund == "pyramide":
            # gelenkiges Lager: Grundplatte mit Schraffur unter der Pyramide
            teile.extend(_grundplatte(d, -2.06 * d, 2.2 * d))
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
    return LAGER_GRUNDMASS * model.characteristic_size() * max(float(faktor), 0.05)


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


def _ringflaeche(P) -> float:
    """Inhalt eines ebenen Vielecks (Newell) - auch mit vielen Ecken."""
    P = np.asarray(P, float)
    if len(P) < 3:
        return 0.0
    return 0.5 * float(np.linalg.norm(np.cross(P, np.roll(P, -1, axis=0)).sum(axis=0)))


def _ringnormale(P) -> np.ndarray:
    P = np.asarray(P, float)
    n = np.cross(P, np.roll(P, -1, axis=0)).sum(axis=0)
    ln = float(np.linalg.norm(n))
    return n / ln if ln > 0 else np.array([0.0, 0.0, 1.0])


def _polygon_abtasten(P: np.ndarray, abstand: float) -> np.ndarray:
    """Punkte im Inneren eines beliebigen ebenen Vielecks im Raster *abstand*
    (Rand einer Geometrieflaeche, auch krumm abgetastet)."""
    from ..fugen import _punkte_im_polygon
    P = np.asarray(P, float)
    if len(P) < 3:
        return np.zeros((0, 3))
    n = _ringnormale(P)
    c = P.mean(axis=0)
    kanten = np.diff(np.vstack([P, P[:1]]), axis=0)
    u = kanten[int(np.argmax(np.linalg.norm(kanten, axis=1)))]
    u = u - (u @ n) * n
    lu = float(np.linalg.norm(u))
    if lu <= 0:
        return np.zeros((0, 3))
    u = u / lu
    v = np.cross(n, u)
    P2 = np.column_stack([(P - c) @ u, (P - c) @ v])
    h = max(float(abstand), 1e-9)
    xs = np.arange(P2[:, 0].min() + 0.5 * h, P2[:, 0].max(), h)
    ys = np.arange(P2[:, 1].min() + 0.5 * h, P2[:, 1].max(), h)
    if not len(xs) or not len(ys):
        return np.atleast_2d(c)
    X, Y = np.meshgrid(xs, ys)
    Q2 = np.column_stack([X.ravel(), Y.ravel()])
    innen = _punkte_im_polygon(P2, Q2)
    if not innen.any():
        return np.atleast_2d(c)
    Q2 = Q2[innen]
    return c + Q2[:, :1] * u + Q2[:, 1:] * v


def _flaeche_abtasten(P: np.ndarray, abstand: float) -> np.ndarray:
    """Punkte im Inneren eines Drei- oder Vierecks im Raster *abstand*;
    ein Vieleck mit mehr Ecken (Rand einer Geometrieflaeche) im Raster
    ueber seine Ebene."""
    P = np.asarray(P, float)
    if len(P) > 4:
        return _polygon_abtasten(P, abstand)
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


#: Hoechstzahl der Symbole je Linien- oder Flaechenlager - ein Glyphensatz
#: je Richtung, darum bleiben auch zwoelftausend Pyramiden fluessig
LAGERSYMBOLE_MAX = 12000


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


def _flaechenlager_geometrie(model: Model, ss) -> list:
    """[(Randpunkte, Normale)] der Geometrieflaechen eines Flaechenlagers.

    Ein aus RFEM uebernommenes Flaechenlager liegt auf Flaechen der
    Geometrie; seine Knoten sind nur die Eckknoten. Damit die Symbole die
    ganze Flaeche belegen - und die Lagerdichte wirkt -, kommt der Rand von
    der Flaeche selbst. Die Normale zeigt bei einer Flaeche eines Koerpers
    aus dem Koerper heraus, sonst nach unten.
    """
    flaechen = getattr(model, "flaechen", {}) or {}
    koerper = getattr(model, "koerper", {}) or {}
    namen = [n for n in (getattr(ss, "flaechen", None) or []) if n in flaechen]
    if not namen:
        return []
    mitten: dict = {}
    for kn, k in koerper.items():
        if not any(fn in namen for fn in k.flaechen):
            continue
        ringe = []
        for fn in k.flaechen:
            f = flaechen.get(fn)
            if f is not None:
                try:
                    R = np.asarray(f.randpunkte(model), float)
                except Exception:       # noqa: BLE001
                    continue
                if len(R):
                    ringe.append(R)
        if ringe:
            mitten[kn] = np.vstack(ringe).mean(axis=0)
    out = []
    for name in namen:
        f = flaechen[name]
        try:
            P = np.asarray(f.randpunkte(model), float)
        except Exception:               # noqa: BLE001
            continue
        if len(P) < 3:
            continue
        n = _ringnormale(P)
        kn = next((kn for kn, k in koerper.items() if name in k.flaechen and kn in mitten), None)
        if kn is not None:
            if float(n @ (P.mean(axis=0) - mitten[kn])) < 0:
                n = -n
        elif n[2] > 0:
            n = -n
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
            # ohne belegte Elemente: die Geometrieflaechen des Lagers
            flaechen = _flaechenlager_geometrie(model, obj)
        if not flaechen:
            nodes = [int(n) for n in (obj.nodes or []) if 0 <= int(n) < model.nn]
            pts = model.nodes[nodes] if nodes else np.zeros((0, 3))
            return pts, np.tile([0.0, 0.0, -1.0], (len(pts), 1))
        gesamt = sum(_ringflaeche(P) for P, _n in flaechen)
        if gesamt > 0 and gesamt / abstand ** 2 > LAGERSYMBOLE_MAX:
            abstand = float(np.sqrt(gesamt / LAGERSYMBOLE_MAX))
        pts, ri = [], []
        for P, n in flaechen:
            Q = _flaeche_abtasten(P, abstand)
            pts.append(Q)
            ri.append(np.tile(n, (len(Q), 1)))
        return (np.vstack(pts) if pts else np.zeros((0, 3)),
                np.vstack(ri) if ri else np.zeros((0, 3)))
    P = _linienlager_kurve(model, obj)
    if P is None:
        nodes = [int(n) for n in (obj.nodes or []) if 0 <= int(n) < model.nn]
        if not nodes:
            return np.zeros((0, 3)), np.zeros((0, 3))
        P = model.nodes[nodes]
    L = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum()) if len(P) > 1 else 0.0
    if L / abstand > LAGERSYMBOLE_MAX:
        abstand = L / LAGERSYMBOLE_MAX
    pts = _polylinie_abtasten(P, abstand)
    return pts, np.tile([0.0, 0.0, -1.0], (len(pts), 1))


def _linienlager_kurve(model: Model, ls):
    """Der Linienzug eines Linienlagers auf seinen Geometrielinien - krumme
    Linien auf ihrer wahren Kurve; None, wenn das Lager keine Linien kennt."""
    linien = getattr(model, "lines", {}) or {}
    namen = [n for n in (getattr(ls, "linien", None) or []) if n in linien]
    if not namen:
        return None
    teile = []
    for name in namen:
        ln = linien[name]
        try:
            Q = np.asarray(ln.punkte(model, TEILUNG_KURVE), float)
        except Exception:               # noqa: BLE001
            idx = [int(n) for n in ln.nodes if 0 <= int(n) < model.nn]
            Q = model.nodes[idx] if len(idx) > 1 else None
        if Q is not None and len(Q) > 1:
            teile.append(Q)
    return np.vstack(teile) if teile else None


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
    d0 = LAGER_GRUNDMASS * size * max(float(faktor), 0.05)
    sicht = None if nur is None else {int(i) for i in nur}

    def da(n) -> bool:
        return 0 <= int(n) < model.nn and (sicht is None or int(n) in sicht)

    # Knotenlager: nach Symbol, Groesse und Farbe (Lagerart) buendeln - ein
    # Glyphensatz je Art; nichtlineare Lager bekommen eine rote Kugel am Knoten
    gruppen: dict[tuple, list] = {}
    nichtlinear = []
    for s in model.supports:
        if not da(s.node):
            continue
        g = round(float(getattr(s, "groesse", 1.0) or 1.0), 3)
        gruppen.setdefault((lager_symbol(s), g, lager_farbe(s)), []).append(s.node)
        if getattr(s, "nonlinear", False):
            nichtlinear.append(int(s.node))
    for i, ((key, g, farbe), nodes) in enumerate(sorted(gruppen.items(), key=str)):
        pts = model.nodes[nodes]
        plotter.add_mesh(pv.PolyData(pts).glyph(geom=lagerglyph(key, d0 * g),
                                                scale=False, orient=False),
                         color=farbe, name=f"supports{i}")
    if nichtlinear:
        plotter.add_mesh(pv.PolyData(model.nodes[nichtlinear]).glyph(
            geom=pv.Sphere(radius=0.45 * d0), scale=False, orient=False),
            color=FARBE_LAGER_NICHTLINEAR, name="supports_nichtlinear")
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
        d0 = LAGER_GRUNDMASS * size * max(float(faktor), 0.05) * float(getattr(s, "groesse", 1.0) or 1.0)
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
    radius = max(1.5 * LAGER_GRUNDMASS * size * max(float(faktor), 0.05), 0.01 * size,
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
FARBE_VORSPANNUNG = "#8030c0"   # Vorspannung: Pfeile, die den Stab spannen
FARBE_ZWANG = "#1e8a40"         # Zwangsverformung
FARBE_LAST_HERVOR = "#ffb000"   # die angeklickte Last
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


#: Farbe der freien Bewegungen (Singularitaeten) - dasselbe Warnorange wie
#: beim Knoten ohne Element: „hier fehlt etwas".
FARBE_BEWEGUNG = "#e07000"


def _querachsen(achse) -> tuple:
    """Zwei Einheitsvektoren e1, e2 quer zu ``achse`` mit e1 x e2 = achse."""
    a = np.asarray(achse, float)
    a = a / (np.linalg.norm(a) or 1.0)
    h = np.array([0.0, 0.0, 1.0]) if abs(a[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = np.cross(h, a)
    e1 = e1 / (np.linalg.norm(e1) or 1.0)
    return e1, np.cross(a, e1)


def _ringpfeil(mitte, achse, radius: float) -> list:
    """Ein Drehpfeil um ``achse`` durch ``mitte``: Bogen und Spitze.

    Ein gerader Pfeil kann eine Drehung nicht zeigen - er wuerde als
    Verschiebung gelesen. Der Bogen laeuft ueber 270 Grad, damit die
    Drehrichtung auch von schraeg ablesbar bleibt, und im Rechtsschraubensinn
    um die Achse: so, wie omega gezaehlt ist.
    """
    a = np.asarray(achse, float)
    if np.linalg.norm(a) <= 0 or radius <= 0:
        return []
    e1, e2 = _querachsen(a)
    t = np.linspace(0.0, 1.5 * np.pi, 48)
    P = (np.asarray(mitte, float)
         + radius * (np.outer(np.cos(t), e1) + np.outer(np.sin(t), e2)))
    bogen = pv.lines_from_points(P).tube(radius=0.06 * radius)
    tang = P[-1] - P[-2]
    tang = tang / (np.linalg.norm(tang) or 1.0)
    spitze = pv.Cone(center=P[-1] + 0.15 * radius * tang, direction=tang,
                     height=0.3 * radius, radius=0.13 * radius)
    return [bogen, spitze]


def add_singularitaet(plotter, model: Model, sing, size: float,
                      name: str = "result_singular") -> None:
    """Eine freie Bewegung zeigen: betroffene Knoten, Pfeil und Drehpfeil.

    ``sing`` ist eine :class:`statik3d.singular.Singularitaet`; ``None``
    loescht die Darstellung wieder. Gezeichnet wird am Bezugspunkt - bei einer
    Verschiebung der Schwerpunkt des Teils, bei einer Drehung ein Punkt auf
    der Drehachse -, damit das Sinnbild dort steht, wo die Bewegung ansetzt.
    """
    for n in (name, f"{name}_knoten"):
        try:
            plotter.remove_actor(n)
        except Exception:                 # noqa: BLE001 - war noch nicht da
            pass
    if sing is None:
        return
    kn = np.asarray(getattr(sing, "knoten", None) or [], int)
    kn = kn[(kn >= 0) & (kn < model.nn)]
    if len(kn):
        plotter.add_mesh(pv.PolyData(model.nodes[kn]), color=FARBE_BEWEGUNG,
                         point_size=9, render_points_as_spheres=True,
                         name=f"{name}_knoten")
    p = np.asarray(getattr(sing, "bezug", None) if getattr(sing, "bezug", None)
                   is not None else np.zeros(3), float)
    lang = 0.25 * float(size or 1.0)
    t = np.asarray(getattr(sing, "t", None) if getattr(sing, "t", None)
                   is not None else np.zeros(3), float)
    w = np.asarray(getattr(sing, "omega", None) if getattr(sing, "omega", None)
                   is not None else np.zeros(3), float)
    teile = []
    if float(np.linalg.norm(t)) > 1e-9:
        teile.append(pv.Arrow(start=p, direction=t / np.linalg.norm(t),
                              scale=lang, tip_length=0.3, shaft_radius=0.02))
    if float(np.linalg.norm(w)) > 1e-12:
        teile += _ringpfeil(p, w, 0.45 * lang)
    if teile:
        plotter.add_mesh(teile[0].merge(teile[1:]) if len(teile) > 1 else teile[0],
                         color=FARBE_BEWEGUNG, name=name)


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


#: Hoechstzahl der Ergebniswerte im Bild - mehr liest niemand, und
#: 1,8 Mio. Marken am Drehlager wuerden die Ansicht sperren
WERTE_MAX = 200


def _wertzahl(v: float, nachkomma: int = 1) -> str:
    """Ergebniswert als kurze Zahl mit Vorzeichen, deutsches Komma."""
    s = f"{float(v):.{nachkomma}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return (s or "0").replace(".", ",")


def ergebniswerte(model: Model, res, point_scalars, arten, quantity: str = "",
                  filter_: str = "extrem", schwelle: float = 0.0, n_te: int = 1,
                  auswahl: dict = None, versteckt: set = None, nachkomma: int = 1) -> tuple:
    """(Punkte, Texte) der Ergebniswerte im Bild (analog ANSYS Probe/Labels).

    arten: Teilmenge von {"staebe", "flaechen", "volumen"}.
    Staebe: mit Schnittgroesse ``quantity`` (N, Vy, Vz, Mt, My, Mz) die Werte
    an den Nachweisstellen aus res.stations - Filter ``extrem`` nimmt je
    Element die kleinste und groesste, ``enden`` beide Enden, ``alle`` jede
    Stelle; ohne Schnittgroesse den Faerbungswert (point_scalars) in der
    Elementmitte. Flaechen: der Faerbungswert je Element (Mittel der Knoten)
    in der Elementmitte. Volumen: je Volumenkoerper der betragsgroesste
    Faerbungswert an seinem Ort - ein Wert je Koerper, nicht je Element.

    ``schwelle`` laesst nur |Wert| >= schwelle stehen (0 = alle), ``n_te``
    jeden n-ten Wert, ``auswahl`` {"elemente": set, "staebe": set,
    "flaechen": set, "koerper": set} nur die gewaehlten Objekte (Filter
    ``auswahl``). Hoechstens WERTE_MAX Marken - die betragsgroessten.
    """
    ps = None if point_scalars is None else np.asarray(point_scalars, float)
    X = np.asarray(model.nodes, float)
    versteckt = versteckt or set()
    auswahl = auswahl or {}
    nur_auswahl = filter_ == "auswahl"
    punkte, texte, betrag = [], [], []

    def nimm(p, v):
        if v is None or not np.isfinite(v):
            return
        if schwelle > 0 and abs(v) < schwelle:
            return
        punkte.append(np.asarray(p, float))
        texte.append(_wertzahl(v, nachkomma))
        betrag.append(abs(float(v)))

    zu_stab = {int(e): n for n, mem in model.members.items() for e in (mem.elements or [])}
    zu_flaeche = {int(e): n for n, f in model.flaechen.items() for e in (f.elemente or [])}
    if "staebe" in arten:
        q = quantity if quantity in SCHNITTGROESSEN else ""
        st = None
        if q and hasattr(res, "stations"):
            try:
                st = res.stations()
            except Exception:                    # noqa: BLE001
                st = None
        _eh, faktor = SG_EINHEIT.get(q, ("", 1.0))
        for i, e in enumerate(model.elements):
            if e.typ not in TYPEN_STAEBE or i in versteckt:
                continue
            if nur_auswahl and i not in auswahl.get("elemente", ()) \
                    and zu_stab.get(i) not in auswahl.get("staebe", ()):
                continue
            n1, n2 = int(e.nodes[0]), int(e.nodes[-1])
            if st is not None and i in st and q in st[i]:
                s = st[i]
                xs = np.asarray(s["x"], float)
                L = float(s.get("L", 0.0)) or float(np.linalg.norm(X[n2] - X[n1])) or 1.0
                vals = np.asarray(s[q], float) / faktor
                if not len(vals):
                    continue
                if filter_ == "alle":
                    idx = range(len(vals))
                elif filter_ == "enden":
                    idx = sorted({0, len(vals) - 1})
                else:
                    idx = sorted({int(np.argmin(vals)), int(np.argmax(vals))})
                for k in idx:
                    tt = xs[k] / L
                    nimm(X[n1] + tt * (X[n2] - X[n1]), vals[k])
            elif ps is not None:
                v = np.nanmean([ps[n1], ps[n2]]) if np.isfinite([ps[n1], ps[n2]]).any() else np.nan
                nimm(0.5 * (X[n1] + X[n2]), v)
    if "flaechen" in arten and ps is not None:
        for i, e in enumerate(model.elements):
            if e.typ not in TYPEN_FLAECHEN or i in versteckt:
                continue
            if nur_auswahl and i not in auswahl.get("elemente", ()) \
                    and zu_flaeche.get(i) not in auswahl.get("flaechen", ()):
                continue
            kn = np.asarray(e.nodes, int)
            w = ps[kn]
            if not np.isfinite(w).any():
                continue
            nimm(X[kn].mean(axis=0), float(np.nanmean(w)))
    if "volumen" in arten and ps is not None:
        koerper = [(n, k) for n, k in model.koerper.items() if getattr(k, "elemente", None)]
        gruppen = []
        if koerper:
            for n, k in koerper:
                if nur_auswahl and n not in auswahl.get("koerper", ()):
                    continue
                el = k.elemente
                schritt = max(1, len(el) // 50000)
                gruppen.append((n, el[::schritt]))
        else:
            el = [i for i, e in enumerate(model.elements) if e.typ in TYPEN_VOLUMEN]
            if el:
                gruppen.append(("", el[:: max(1, len(el) // 50000)]))
        import itertools
        for n, el in gruppen:
            kn = np.unique(np.fromiter(itertools.chain.from_iterable(
                model.elements[i].nodes for i in el), int))
            w = ps[kn]
            ok = np.isfinite(w)
            if not ok.any():
                continue
            j = int(np.nanargmax(np.abs(np.where(ok, w, 0.0))))
            v = float(w[j])
            if schwelle > 0 and abs(v) < schwelle:
                continue
            punkte.append(X[kn[j]])
            texte.append((f"{n}: " if n else "") + _wertzahl(v, nachkomma))
            betrag.append(abs(v))
    if not punkte:
        return [], []
    order = list(range(len(punkte)))
    if n_te and n_te > 1:
        order = order[::int(n_te)]
    if len(order) > WERTE_MAX:
        order = sorted(order, key=lambda k: -betrag[k])[:WERTE_MAX]
        order.sort()
    return [punkte[k] for k in order], [texte[k] for k in order]


#: Lastart der Beschriftung -> Groesse in einheiten.Einheiten
LASTARTEN = {"kraft": "kraft", "moment": "moment", "strecke": "strecke",
             "flaeche": "flaechenlast", "temperatur": "temperatur", "zwang": "zwang",
             "vorspannung": "kraft"}
#: hoechstens so viele Lastwerte je Lastart beschriften
LASTWERTE_MAX = 60


def add_loads(plotter, model: Model, case, size: float, raender: dict = None,
              seiten: dict = None, beschriften: bool = False, textgroesse: int = 10,
              einheiten=None, ausser=None, knoten=None, ausser_flaechen=None,
              ausser_linien=None, merker: list = None, hervor=None) -> list:
    """Alle Lasten eines Lastfalls ins Bild. Rueckgabe: die Einheiten der
    gezeichneten Lastarten (fuer die Kopfzeile), z. B. ["kN", "kN/m²"].

    ``beschriften`` schreibt die Lastgroesse als Zahl an die Pfeile (Knoten-
    lasten, Strecken- und Flaechenlasten, Objektlasten je Flaeche, Temperatur,
    Zwangsverformung); die Einheit steht in der Kopfzeile. ``einheiten``
    (einheiten.Einheiten, sonst ``model.einheiten``) bestimmt Einheit und
    Nachkommastellen der Zahlen. Lasten auf ausgeblendeten Teilen bleiben
    weg: ``ausser`` (Elementnummern), ``knoten`` (die sichtbaren Knoten, sonst
    alle), ``ausser_flaechen`` und ``ausser_linien`` (Namen). ``merker`` (eine Liste) sammelt je gezeichnetem
    Lastsymbol (Listenname, Index der Last, Punkt) - damit ein Klick in der
    Ansicht die Last findet (:func:`last_at`); ``hervor`` (Menge von
    (Listenname, Index)) zeichnet diese Lasten hervorgehoben.

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
    hervor = {(str(a), int(b)) for a, b in (hervor or ())}
    h_pts, h_vec, h_punkte = [], [], []

    def merke(liste, k, punkt, vec_=None):
        """Ein Lastsymbol fuer den Klick merken - und hervorheben, wenn gewaehlt."""
        if merker is not None:
            merker.append((liste, int(k), np.asarray(punkt, float)))
        if (liste, int(k)) in hervor:
            if vec_ is not None:
                h_pts.append(np.asarray(punkt, float))
                h_vec.append(np.asarray(vec_, float))
            else:
                h_punkte.append(np.asarray(punkt, float))

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
    for k_l, l in enumerate(case.nodal_loads):
        if getattr(l, "_geo", False) or not knoten_da(l.node):
            continue
        f = np.asarray(l.F[:3], float)
        if np.any(f) and 0 <= int(l.node) < model.nn:
            pts.append(model.nodes[int(l.node)])
            vec.append(f)
            merken("kraft", model.nodes[int(l.node)], lz(np.linalg.norm(f), "kraft"))
            merke("nodal_loads", k_l, model.nodes[int(l.node)], f)
        mo = np.asarray(l.F[3:6], float) if len(l.F) >= 6 else np.zeros(3)
        if np.any(mo) and 0 <= int(l.node) < model.nn:
            merken("moment", model.nodes[int(l.node)], lz(np.linalg.norm(mo), "moment"))
            if not np.any(f):
                merke("nodal_loads", k_l, model.nodes[int(l.node)])
    for k_l, bl in enumerate(case.beam_loads):
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
                merke("beam_loads", k_l, pts[-1], q)
        if np.any(q1) or np.any(q2):
            merken("strecke", X[0] + (0.5 * (a + b) / L) * (X[-1] - X[0]),
                   spanne(np.linalg.norm(q1), np.linalg.norm(q2), "strecke"))
    for k_l, fl in enumerate(case.face_loads):
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
        merke("face_loads", k_l, mitte, d * fl.p)
    # ---- Objektlasten auf der Geometrie -------------------------------------
    warm, kalt = [], []
    rahmen_pts, rahmen_lines = [], []
    for k_l, gl in enumerate(getattr(case, "geometrielasten", []) or []):
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
                for m_ in mitten:
                    merke("geometrielasten", k_l, m_)
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
                merke("geometrielasten", k_l, m_, d_ * p)
            if werte:
                merken("flaeche", mitten.mean(axis=0), spanne(min(werte), max(werte), "flaeche", "…"))
    for k_l, ll in enumerate(getattr(case, "linienlasten", []) or []):
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
                    merke("linienlasten", k_l, pts[-1], q)
            s0 += L
    _pfeile(plotter, pts, vec, size, "loads")
    if rahmen_pts:
        plotter.add_mesh(pv.PolyData(np.asarray(rahmen_pts, float),
                                     lines=np.asarray(rahmen_lines)),
                         color=FARBE_LAST, line_width=2, name="lastfenster")
    # ---- Temperatur auf Elementen -------------------------------------------
    for k_l, tl in enumerate(case.temp_loads):
        if getattr(tl, "_geo", False) or not 0 <= int(tl.elem) < len(model.elements) \
                or int(tl.elem) in weg_e:
            continue
        e = model.elements[tl.elem]
        c = model.nodes[[int(n) for n in e.nodes]].mean(axis=0)
        (warm if tl.dT >= 0 else kalt).append(c)
        merken("temperatur", c, f"ΔT {_lastzahl(tl.dT, 1)}")
        merke("temp_loads", k_l, c)
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
    for k_l, zv in enumerate(getattr(case, "zwangsverformungen", []) or []):
        if not knoten_da(zv.node):
            continue
        X = model.nodes[int(zv.node)]
        u = np.array([float(zv.u[k]) if k in zv.dofs else 0.0 for k in range(3)])
        if np.any(u):
            zpts.append(X)
            zvec.append(u)
            merken("zwang", X, eh.zahl(np.linalg.norm(u), "zwang"))
            merke("zwangsverformungen", k_l, X, u)
        if any(k in zv.dofs and zv.u[k] for k in (3, 4, 5)):
            ringe.append(X)
            if not np.any(u):
                merke("zwangsverformungen", k_l, X)
    _pfeile(plotter, zpts, zvec, size, "zwang", FARBE_ZWANG)
    if ringe:
        plotter.add_points(np.asarray(ringe, float), color=FARBE_ZWANG, point_size=13,
                           render_points_as_spheres=True, name="zwang_drehung")
    # ---- Vorspannung: an beiden Enden ein Pfeil nach aussen (Zug im Bauteil) --
    vpts, vvec = [], []
    for k_l, v in enumerate(getattr(case, "vorspannungen", []) or []):
        enden = vorspannung_enden(model, v, weg_e)
        if enden is None:
            continue
        a, b = enden
        d = b - a
        L = float(np.linalg.norm(d))
        if L <= 0:
            continue
        d = d / L
        Fv = float(v.kraft)
        vpts += [a, b]
        vvec += [-d * Fv, d * Fv]
        merke("vorspannungen", k_l, a, -d * Fv)
        merke("vorspannungen", k_l, b, d * Fv)
        merken("vorspannung", 0.5 * (a + b), "F_v " + lz(abs(Fv), "vorspannung"))
    _pfeile(plotter, vpts, vvec, size, "vorspannung", FARBE_VORSPANNUNG)
    # ---- die angeklickte Last: dieselben Symbole in der Hervorhebungsfarbe ----
    if h_pts:
        _pfeile(plotter, h_pts, h_vec, size, "last_hervor", FARBE_LAST_HERVOR)
    if h_punkte:
        plotter.add_points(np.asarray(h_punkte, float), color=FARBE_LAST_HERVOR, point_size=16,
                           render_points_as_spheres=True, name="last_hervor_punkte")
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


def last_at(punkt, merker, size: float):
    """Die Last unter dem Zeiger: (Listenname, Index) des naechsten gezeichneten
    Lastsymbols (aus ``merker`` von :func:`add_loads`) im Umkreis einer
    Pfeillaenge - oder None."""
    if punkt is None or not merker:
        return None
    p = np.asarray(punkt, float).ravel()[:3]
    P = np.array([x[2] for x in merker], float).reshape(-1, 3)
    d = np.linalg.norm(P - p, axis=1)
    j = int(np.argmin(d))
    if d[j] > 0.08 * max(float(size), 1e-9):
        return None
    return str(merker[j][0]), int(merker[j][1])


def vorspannung_enden(model: Model, v, weg_e=None):
    """Anfang und Ende des vorgespannten Bauteils (Stab: seine Endknoten,
    Koerper: die Achse durch den Schwerpunkt) - oder None."""
    weg = set(weg_e or ())
    if getattr(v, "art", "stab") == "stab":
        mem = (getattr(model, "members", None) or {}).get(v.ziel)
        elems = [int(e) for e in (mem.elements if mem else [])
                 if 0 <= int(e) < len(model.elements) and int(e) not in weg]
        if not elems:
            return None
        return (np.asarray(model.nodes[int(model.elements[elems[0]].nodes[0])], float),
                np.asarray(model.nodes[int(model.elements[elems[-1]].nodes[-1])], float))
    k = (getattr(model, "koerper", None) or {}).get(v.ziel)
    elems = [int(e) for e in (k.elemente if k else []) if 0 <= int(e) < len(model.elements)]
    if not elems:
        return None
    knoten = sorted({int(x) for e in elems for x in model.elements[e].nodes})
    P = model.nodes[knoten]
    if v.achse is not None and float(np.linalg.norm(v.achse)) > 0:
        ax = np.asarray(v.achse, float)
        ax = ax / float(np.linalg.norm(ax))
    else:
        ax = np.zeros(3)
        ax[int(np.argmax(np.ptp(P, axis=0)))] = 1.0
    c = P.mean(axis=0)
    t = (P - c) @ ax
    return c + ax * float(t.min()), c + ax * float(t.max())


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
        if e.typ not in TYPEN_STAEBE:
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


def result_field(model: Model, res, field: str, util: dict = None, seite: str = "max"):
    """(Knotenskalare oder None, Zellskalare oder None, Name).

    Spannungsgroessen (spannungen.FELDER: Grund-, Haupt-, Vergleichs- und
    Kontaktspannungen je Art) gibt es zu Lastfall und Kombination; eine
    Umhuellende fuehrt keine Komponenten - dann bleibt es ohne Faerbung.
    ``seite`` gilt fuer Flaechen: max, oben oder unten."""
    from .. import spannungen as spn
    nn = model.nn
    ak = spn.feld(field)
    if ak is not None:
        art, groesse = ak
        if not hasattr(res, "solid_res") or not hasattr(res, "beam_forces"):
            return None, None, ""
        return spn.je_knoten(model, res, art, groesse, seite), None, spn.beschriftung(art, groesse, seite)
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
