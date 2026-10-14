"""Schnittbox und Werte auf Schnittflaechen (Ansichtspaket C, 14.10.2026).

Vorbild ist die Schnittbox von ediBIM (``tools/schnittbox.ts``): sechs Ebenen
um alles Sichtbare, je Seite ein Ziehpunkt, das Mausrad ueber einem Griff
schiebt fein. Geschnitten wird wie bei der Schnittebene das Volumennetz
**vor** der Oberflaechenbildung (MainWindow._gitter) - so stehen auf den
Schnittflaechen die Elemente und ihre Ergebnisse.

Werte auf der Schnittflaeche
----------------------------
Ein Schnitt legt neue Punkte auf die Kanten bzw. ins Innere der Elemente.
Sie sind keine Modellknoten; ihre Werte (Verschiebung, Faerbung) kommen aus
den Knoten des Elements, in dem sie liegen, mit dessen Formfunktionen
(:func:`gewichte`). Bis zum 14.10.2026 nahm die Ansicht nach einem Schnitt die
Punktnummer des geschnittenen Gitters als Knotennummer: am tet10-Wuerfel
(Schnitt x bei 0,37) gehoerte **jeder** Punkt der Oberflaeche zu einem
falschen Knoten, bis 1,59 m daneben - Faerbung und Verformung des Schnitts
waren falsch (gemessen 14.10.2026, ans_werk/probe2.py).
"""
from __future__ import annotations

import numpy as np

#: Die sechs Seiten der Box: Name -> (Achse, Index in den Grenzen, Vorzeichen
#: der Aussennormalen)
SEITEN = {"x-": (0, 0, -1.0), "x+": (0, 1, 1.0), "y-": (1, 2, -1.0),
          "y+": (1, 3, 1.0), "z-": (2, 4, -1.0), "z+": (2, 5, 1.0)}
#: Kleinster Rest der Box je Achse als Anteil der Modellgroesse laengs der
#: Achse: eine Seite laesst sich nicht ueber die gegenueberliegende ziehen
REST = 0.01
#: So weit darf eine Seite ueber das Modell hinaus, als Anteil der Ausdehnung
UEBERSTAND = 0.05
#: Ein Radschritt (120/8 Grad) ueber einem Griff schiebt die Seite um diesen
#: Anteil der Modellausdehnung laengs ihrer Achse
RADSCHRITT = 0.005
#: Fangradius eines Griffs in Bildpunkten (logisch, mal Pixelmass)
GRIFF_RADIUS = 12.0
#: Farbe der Box und ihrer Griffe
FARBE = "#d08030"


def box_um(bounds, rand: float = 0.0) -> list:
    """Die Box um ``bounds`` (xmin, xmax, ymin, ymax, zmin, zmax), je Seite
    um ``rand`` mal die groesste Ausdehnung erweitert - sonst laege die
    Aussenhaut genau auf einer Schnittebene."""
    b = [float(v) for v in bounds]
    d = max(b[1] - b[0], b[3] - b[2], b[5] - b[4], 1e-12) * float(rand)
    return [b[0] - d, b[1] + d, b[2] - d, b[3] + d, b[4] - d, b[5] + d]


def box_gueltig(box) -> bool:
    try:
        b = [float(v) for v in box]
    except (TypeError, ValueError):
        return False
    return len(b) == 6 and all(np.isfinite(b)) and b[0] <= b[1] and b[2] <= b[3] and b[4] <= b[5]


def seite_setzen(box, seite: str, wert: float, modell) -> list:
    """Die Box mit der Seite ``seite`` auf ``wert`` - begrenzt: es bleibt je
    Achse mindestens :data:`REST` der Modellausdehnung, und keine Seite geht
    weiter als :data:`UEBERSTAND` ueber das Modell (``modell`` = dessen
    Grenzen) hinaus."""
    achse, i, vz = SEITEN[seite]
    b = [float(v) for v in box]
    m = [float(v) for v in modell]
    lo_m, hi_m = m[2 * achse], m[2 * achse + 1]
    aus = max(hi_m - lo_m, 1e-9 * max(1.0, max(abs(v) for v in m)))
    gross = max(m[1] - m[0], m[3] - m[2], m[5] - m[4], 1e-12)
    rest = REST * (aus if hi_m > lo_m else gross)
    rand = UEBERSTAND * max(aus, REST * gross)
    w = float(wert)
    if vz > 0:
        w = min(max(w, b[2 * achse] + rest), hi_m + rand)
    else:
        w = max(min(w, b[2 * achse + 1] - rest), lo_m - rand)
    b[i] = w
    return b


def griffe(box) -> dict:
    """Die Ziehpunkte: je Seite die Mitte der Seitenflaeche."""
    b = [float(v) for v in box]
    mitte = np.array([(b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2])
    aus = {}
    for name, (achse, i, _vz) in SEITEN.items():
        p = mitte.copy()
        p[achse] = b[i]
        aus[name] = p
    return aus


def bereich_text(box, faktor: float = 1.0, einheit: str = "m", stellen: int = 3) -> str:
    """„x 0,100 … 0,900 m · y … · z …“ - der Bereich der Box fuer die Anzeige."""
    from .. import zahlen as zl
    b = [float(v) * faktor for v in box]
    teile = []
    for k, a in enumerate("xyz"):
        lo, hi = round(b[2 * k], stellen) + 0.0, round(b[2 * k + 1], stellen) + 0.0
        teile.append(f"{a} {zl.zahl_text(lo, tausender=False)} … {zl.zahl_text(hi, tausender=False)}")
    return " · ".join(teile) + f" {einheit}"


# --------------------------------------------------------------------------
# Schneiden
# --------------------------------------------------------------------------
def _offsets(grid) -> np.ndarray:
    """Beginn jeder Zelle in der Verbindungsliste (n + 1 Eintraege)."""
    off = getattr(grid, "cell_offsets", None)
    if off is None:
        off = grid.offset
    return np.asarray(off, np.int64)


def _zellgrenzen(grid):
    """(min, max) je Zelle, (n, 3) - ueber die Verbindungsliste ohne Schleife."""
    conn = np.asarray(grid.cell_connectivity, np.int64)
    off = _offsets(grid)
    P = np.asarray(grid.points, float)[conn]
    start = off[:-1]
    return np.minimum.reduceat(P, start, axis=0), np.maximum.reduceat(P, start, axis=0)


def box_schneiden(grid, box):
    """Das Gitter auf die Box ``box`` (xmin, xmax, ymin, ymax, zmin, zmax)
    zuschneiden: Zellen ganz draussen fallen weg, Zellen ganz drinnen bleiben,
    wie sie sind, durchstossene werden an den Ebenen geschnitten, die sie
    kreuzen (wie viewport.schneiden, Tabellenschnitt von VTK). Punkt- und
    Zellfelder reisen mit (``elem``, ``_kn``).

    Rueckgabe das geschnittene Gitter; ein leeres, wenn nichts in der Box
    liegt (anders als bei der Ebene: die Box zeigt dann eben nichts)."""
    import pyvista as pv
    if grid is None or not getattr(grid, "n_cells", 0):
        return grid
    b = [float(v) for v in box]
    lo = np.array([b[0], b[2], b[4]])
    hi = np.array([b[1], b[3], b[5]])
    zmin, zmax = _zellgrenzen(grid)
    draussen = (zmax < lo).any(axis=1) | (zmin > hi).any(axis=1)
    drinnen = (zmin >= lo).all(axis=1) & (zmax <= hi).all(axis=1)
    if drinnen.all():
        return grid
    behalten = np.flatnonzero(~draussen)
    if not len(behalten):
        return pv.UnstructuredGrid()
    teil = grid.extract_cells(behalten) if len(behalten) < grid.n_cells else grid
    for k in range(3):
        for seite, wert, normale in ((0, lo[k], -1.0), (1, hi[k], 1.0)):
            # nur die Ebenen, die eine Zelle der Auswahl wirklich kreuzt
            if seite == 0 and not (zmin[behalten, k] < wert).any():
                continue
            if seite == 1 and not (zmax[behalten, k] > wert).any():
                continue
            n = [0.0, 0.0, 0.0]
            n[k] = normale
            o = [0.0, 0.0, 0.0]
            o[k] = float(wert)
            try:
                # invert=True laesst die Seite gegen die Normale stehen
                teil = teil.clip(normal=n, origin=o, invert=True)
            except Exception:               # noqa: BLE001 - dann eben grob
                pass
            if not getattr(teil, "n_cells", 0):
                return pv.UnstructuredGrid()
    if "vtkOriginalPointIds" in teil.point_data:
        del teil.point_data["vtkOriginalPointIds"]
    if "vtkOriginalCellIds" in teil.cell_data:
        del teil.cell_data["vtkOriginalCellIds"]
    return teil


# --------------------------------------------------------------------------
# Werte an den Punkten eines Schnitts
# --------------------------------------------------------------------------
#: VTK-Zelltypen der Tetraeder: linear und quadratisch
_TET, _QTET = 10, 24


def knotenfeld_setzen(grid) -> None:
    """Vor dem Schneiden: die Nummer jedes Punktes als Punktfeld ``_kn`` - der
    Schnitt traegt sie zu den Punkten, die bleiben (bei :func:`vp.to_grid`
    ist der Punkt der Modellknoten)."""
    grid.point_data["_kn"] = np.arange(grid.n_points, dtype=float)


def _tet_gewichte(X, P, quadratisch: bool):
    """Formfunktionen je Punkt P (m, 3) im Tetraeder mit den Ecken X (m, 4, 3)
    - linear (4) oder quadratisch mit den Kantenmitten in VTK-Folge (10)."""
    A = np.stack([X[:, 1] - X[:, 0], X[:, 2] - X[:, 0], X[:, 3] - X[:, 0]], axis=2)
    r = P - X[:, 0]
    try:
        l123 = np.linalg.solve(A, r[..., None])[..., 0]
    except np.linalg.LinAlgError:
        l123 = np.stack([np.linalg.lstsq(a, v, rcond=None)[0] for a, v in zip(A, r)])
    L = np.concatenate([1.0 - l123.sum(axis=1, keepdims=True), l123], axis=1)
    if not quadratisch:
        return L
    L0, L1, L2, L3 = L.T
    return np.stack([L0 * (2 * L0 - 1), L1 * (2 * L1 - 1), L2 * (2 * L2 - 1), L3 * (2 * L3 - 1),
                     4 * L0 * L1, 4 * L1 * L2, 4 * L0 * L2, 4 * L0 * L3, 4 * L1 * L3, 4 * L2 * L3],
                    axis=1)


def gewichte(grid0, geschnitten):
    """Je Punkt des geschnittenen Gitters sein Wert aus den Punkten von
    ``grid0`` (vor dem Schnitt, mit :func:`knotenfeld_setzen`).

    Rueckgabe ``(index, W)``: ``index`` je Punkt eine Nummer - ein Punkt von
    ``grid0`` behaelt seine (< n0), ein neuer Punkt des Schnitts bekommt
    ``n0 + j`` -, und ``W`` (scipy.sparse, j x n0) die Gewichte der neuen
    Punkte (Formfunktionen des Elements, in dem sie liegen); None ohne neue
    Punkte. Werte je Punkt: :func:`erweitert` (Werte je Punkt von grid0, W)
    an ``index``."""
    n0 = int(grid0.n_points)
    P = np.asarray(geschnitten.points, float)
    n = len(P)
    if "_kn" not in geschnitten.point_data:
        return np.arange(n, dtype=np.int64), None
    X0 = np.asarray(grid0.points, float)
    kf = np.asarray(geschnitten.point_data["_kn"], float)
    k = np.rint(kf).astype(np.int64)
    gross = float(np.ptp(X0, axis=0).max()) if len(X0) else 1.0
    tol = 1e-9 * max(gross, 1.0)
    alt = (np.abs(kf - k) < 1e-6) & (k >= 0) & (k < n0)
    alt[alt] = np.linalg.norm(P[alt] - X0[k[alt]], axis=1) <= tol
    index = np.where(alt, k, -1)
    neu = np.flatnonzero(~alt)
    if not len(neu):
        return index, None
    from scipy import sparse
    # je neuem Punkt eine Zelle des Schnitts, die ihn nutzt -> ihr Element
    conn = np.asarray(geschnitten.cell_connectivity, np.int64)
    off = _offsets(geschnitten)
    zelle = np.repeat(np.arange(len(off) - 1), np.diff(off))
    erste = np.full(n, -1, np.int64)
    erste[conn[::-1]] = zelle[::-1]          # die erste Zelle je Punkt
    elem_s = np.asarray(geschnitten.cell_data["elem"], np.int64)
    elem0 = np.asarray(grid0.cell_data["elem"], np.int64)
    zu_zelle0 = {int(e): i for i, e in enumerate(elem0)}
    conn0 = np.asarray(grid0.cell_connectivity, np.int64)
    off0 = _offsets(grid0)
    typ0 = np.asarray(grid0.celltypes, np.int64)
    zeilen, spalten, werte = [], [], []
    z0 = np.array([zu_zelle0.get(int(elem_s[erste[p]]), -1) if erste[p] >= 0 else -1 for p in neu],
                  np.int64)
    # Tetraeder je Typ auf einmal
    rest = np.ones(len(neu), bool)
    for t, nk in ((_TET, 4), (_QTET, 10)):
        sel = np.flatnonzero((z0 >= 0) & (typ0[np.maximum(z0, 0)] == t))
        if not len(sel):
            continue
        ids = np.stack([conn0[off0[z0[sel]] + j] for j in range(nk)], axis=1)
        G = _tet_gewichte(X0[ids[:, :4]], P[neu[sel]], nk == 10)
        zeilen.append(np.repeat(sel, nk))
        spalten.append(ids.ravel())
        werte.append(G.ravel())
        rest[sel] = False
    # uebrige Zellen (Hexaeder, Keile, Schalen, Stäbe): VTK rechnet die
    # Formfunktionen der Zelle selbst
    if rest.any():
        from vtkmodules.vtkCommonCore import reference
        nah = [0.0, 0.0, 0.0]
        sub = reference(0)
        pc = [0.0, 0.0, 0.0]
        d2 = reference(0.0)
        for j in np.flatnonzero(rest):
            c = int(z0[j])
            if c < 0:
                # ohne Zelle: der naechste Knoten (sollte nicht vorkommen)
                zeilen.append(np.array([j]))
                spalten.append(np.array([int(np.argmin(np.linalg.norm(X0 - P[neu[j]], axis=1)))]))
                werte.append(np.array([1.0]))
                continue
            zellobj = grid0.GetCell(c)
            m = zellobj.GetNumberOfPoints()
            w = [0.0] * m
            zellobj.EvaluatePosition(P[neu[j]].tolist(), nah, sub, pc, d2, w)
            ids = conn0[off0[c]:off0[c] + m]
            zeilen.append(np.full(m, j))
            spalten.append(np.asarray(ids, np.int64))
            werte.append(np.asarray(w, float))
    W = sparse.csr_matrix((np.concatenate(werte), (np.concatenate(zeilen), np.concatenate(spalten))),
                          shape=(len(neu), n0))
    index[neu] = n0 + np.arange(len(neu))
    return index, W


def erweitert(werte, W):
    """Werte je Punkt von grid0, dahinter die Werte der neuen Schnittpunkte
    (W @ werte) - so gilt ``erweitert(werte, W)[index]`` fuer jeden Punkt des
    geschnittenen Gitters. Ohne W die Werte selbst."""
    if W is None or werte is None:
        return werte
    a = np.asarray(werte)
    if a.ndim == 0 or len(a) != W.shape[1]:
        return a
    if a.dtype == bool or not np.issubdtype(a.dtype, np.number):
        return a
    a = a.astype(float, copy=False)
    zusatz = W @ a
    return np.concatenate([a, np.asarray(zusatz).reshape((W.shape[0],) + a.shape[1:])], axis=0)


# --------------------------------------------------------------------------
# Bedienung im Fenster
# --------------------------------------------------------------------------
class Schnittbox:
    """Die Schnittbox des Fensters: Grenzen, Rahmen und Griffe im Bild,
    Ziehen und Mausrad an einem Griff.

    Geschnitten wird in ``MainWindow._gitter`` (dort fragt
    ``schnittbox_grenzen`` hier nach). Beim Ziehen folgen nur Rahmen und
    Griffe der Maus; neu geschnitten wird beim Loslassen - am Drehlager ist
    ein Schnitt kein Mausschritt. Das Mausrad ueber einem Griff schiebt die
    Seite fein und schneidet, wenn das Rad ruht (:data:`RAD_RUHE_MS`)."""

    #: So lange nach dem letzten Radschritt wird geschnitten [ms]
    RAD_RUHE_MS = 300

    def __init__(self, fenster):
        self.w = fenster
        #: [xmin, xmax, ymin, ymax, zmin, zmax] oder None (aus)
        self.box = None
        #: laufender Zug an einem Griff: dict oder None
        self._zug = None
        self._rad_takt = None

    # -- Zustand ------------------------------------------------------------
    def grenzen(self):
        return tuple(float(v) for v in self.box) if self.box is not None else None

    def modellgrenzen(self) -> list:
        """Grenzen aller Modellknoten (an ihnen misst sich Rest und Ueberstand)."""
        X = np.asarray(self.w.model.nodes, float).reshape(-1, 3)
        if not len(X):
            return [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
        lo, hi = X.min(axis=0), X.max(axis=0)
        return [float(lo[0]), float(hi[0]), float(lo[1]), float(hi[1]), float(lo[2]), float(hi[2])]

    def sichtbare_grenzen(self) -> list:
        """Grenzen dessen, was gerade im Bild ist: die Knoten sichtbarer Teile."""
        m = self.w.model
        X = np.asarray(m.nodes, float).reshape(-1, 3)
        try:
            sicht = self.w._sichtbare_knoten()
        except Exception:                   # noqa: BLE001
            sicht = None
        if sicht is not None and len(sicht):
            X = X[np.asarray(sicht, int)]
        if not len(X):
            return self.modellgrenzen()
        lo, hi = X.min(axis=0), X.max(axis=0)
        return [float(lo[0]), float(hi[0]), float(lo[1]), float(hi[1]), float(lo[2]), float(hi[2])]

    def anfangsbox(self) -> list:
        """Die Box beim Einschalten: um alles Sichtbare, 1 % Luft je Seite."""
        return box_um(self.sichtbare_grenzen(), 0.01)

    def text(self) -> str:
        if self.box is None:
            return "Schnittbox aus"
        try:
            E = self.w._einheiten_modell()
            faktor = float(E.aus_si(1.0, "laenge"))
            einheit = E.einheit("laenge")
            stellen = int(E.nk("laenge"))
        except Exception:                   # noqa: BLE001
            faktor, einheit, stellen = 1.0, "m", 3
        return bereich_text(self.box, faktor, einheit, stellen)

    # -- Bild ---------------------------------------------------------------
    def zeichnen(self) -> None:
        """Rahmen und Griffe der Box (nach jedem Neuaufbau des Bildes)."""
        p = self.w.plotter
        for n in ("schnittbox_rahmen", "schnittbox_griffe"):
            try:
                p.remove_actor(n, render=False)
            except Exception:               # noqa: BLE001
                pass
        if self.box is None:
            return
        import pyvista as pv
        try:
            rahmen = pv.Box(bounds=self.box).extract_feature_edges(
                feature_angle=30, boundary_edges=True, manifold_edges=False, non_manifold_edges=False)
            p.add_mesh(rahmen, color=FARBE, line_width=2, pickable=False, name="schnittbox_rahmen",
                       reset_camera=False)
            pk = np.array(list(griffe(self.box).values()))
            p.add_points(pk, color=FARBE, point_size=13, render_points_as_spheres=True,
                         pickable=False, name="schnittbox_griffe", reset_camera=False)
        except Exception as ex:             # noqa: BLE001 - die Box ist Beiwerk
            self.w.log.appendPlainText(f"Schnittbox: {ex}")

    def _nachziehen(self) -> None:
        """Rahmen und Griffe auf die Box setzen, ohne neu zu schneiden."""
        self.zeichnen()
        try:
            self.w.plotter.render()
        except Exception:                   # noqa: BLE001
            pass
        self.w._schnittbox_anzeige()

    # -- Griffe -------------------------------------------------------------
    def _bildpunkt(self, P):
        ren = self.w.plotter.renderer
        ren.SetWorldPoint(float(P[0]), float(P[1]), float(P[2]), 1.0)
        ren.WorldToDisplay()
        d = ren.GetDisplayPoint()
        return np.array([d[0], d[1]], float), float(d[2])

    def griff_unter(self, x: float, y: float) -> str:
        """Der Griff unter dem Anzeigepunkt (x, y) (VTK, Geraetepixel) - oder ""."""
        if self.box is None:
            return ""
        r = GRIFF_RADIUS * self.w._pixelmass()
        best, beste = "", None
        for name, P in griffe(self.box).items():
            q, z = self._bildpunkt(P)
            d = float(np.hypot(q[0] - x, q[1] - y))
            if d <= r and (beste is None or (d, z) < beste):
                best, beste = name, (d, z)
        return best

    def druck(self, pos) -> bool:
        """Linke Taste gedrueckt: auf einem Griff beginnt ein Zug."""
        if self.box is None:
            return False
        x, y = self.w._qt_nach_vtk(pos)
        name = self.griff_unter(x, y)
        if not name:
            return False
        achse, i, _vz = SEITEN[name]
        P = griffe(self.box)[name]
        m = self.modellgrenzen()
        laenge = max(m[2 * achse + 1] - m[2 * achse], max(m[1] - m[0], m[3] - m[2], m[5] - m[4]) * 0.1,
                     1e-9)
        e = np.zeros(3)
        e[achse] = laenge
        q0, _z = self._bildpunkt(P)
        q1, _z = self._bildpunkt(P + e)
        self._zug = {"seite": name, "start": np.array([x, y]), "wert0": float(self.box[i]),
                     "bild": q1 - q0, "laenge": laenge}
        return True

    def ziehen(self, pos) -> bool:
        """Maus bewegt: die gegriffene Seite folgt ihr laengs ihrer Achse."""
        z = self._zug
        if z is None:
            return False
        x, y = self.w._qt_nach_vtk(pos)
        d = np.array([x, y]) - z["start"]
        s = z["bild"]
        ss = float(s @ s)
        t = float(d @ s) / ss if ss > 1e-12 else 0.0
        self.box = seite_setzen(self.box, z["seite"], z["wert0"] + t * z["laenge"], self.modellgrenzen())
        self._nachziehen()
        return True

    def los(self, pos) -> bool:
        """Losgelassen: jetzt wird geschnitten."""
        z = self._zug
        if z is None:
            return False
        self.ziehen(pos)
        self._zug = None
        self.w.statusBar().showMessage("Schnittbox: " + self.text(), 5000)
        self.w.redraw()
        return True

    def rad(self, ereignis) -> bool:
        """Mausrad ueber einem Griff: die Seite fein schieben (vorwaerts nach
        aussen, die Box waechst; zurueck nach innen). Sonst False - dann zoomt
        das Rad wie immer."""
        if self.box is None:
            return False
        try:
            grad = ereignis.angleDelta().y()
            pos = ereignis.position()
        except Exception:                   # noqa: BLE001
            return False
        if not grad:
            return False
        x, y = self.w._qt_nach_vtk(pos)
        name = self.griff_unter(x, y)
        if not name:
            return False
        self.schieben(name, grad / 120.0)
        return True

    def schieben(self, seite: str, schritte: float) -> None:
        """Die Seite um ``schritte`` Radschritte schieben (vorwaerts = nach
        aussen); geschnitten wird, wenn das Rad ruht."""
        achse, i, vz = SEITEN[seite]
        m = self.modellgrenzen()
        aus = max(m[2 * achse + 1] - m[2 * achse], 1e-3 * max(m[1] - m[0], m[3] - m[2], m[5] - m[4], 1e-9))
        self.box = seite_setzen(self.box, seite, self.box[i] + vz * schritte * RADSCHRITT * aus, m)
        self._nachziehen()
        self.w.statusBar().showMessage("Schnittbox: " + self.text(), 3000)
        if self._rad_takt is None:
            from PySide6 import QtCore
            self._rad_takt = QtCore.QTimer(self.w)
            self._rad_takt.setSingleShot(True)
            self._rad_takt.setInterval(self.RAD_RUHE_MS)
            self._rad_takt.timeout.connect(self.w.redraw)
        self._rad_takt.start()
