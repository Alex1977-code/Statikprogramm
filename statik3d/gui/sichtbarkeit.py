"""Ausblenden ohne Neuaufbau der Oberflaeche (Ansichtspaket B, 14.10.2026).

Bis zum 14.10.2026 baute jedes Ausblenden das Gitter neu: ``to_grid`` lief in
Python ueber alle Elemente, ``extract_surface`` ueber alle Tetraeder. Am
Drehlager (617 241 Elemente, 1 015 610 Knoten, 108 Koerper) kostete das
allein 2,2 bis 3,6 s je Ausblenden (Profil vom 14.10.2026).

Hier entsteht die Oberflaeche **je Koerper** einmal je Modellstand
(:class:`Teiloberflaeche`). Die Koerper werden dafuer voneinander geloest
(jeder bekommt eigene Punkte), und **ein** ``extract_surface`` liefert die
Haeute aller Koerper zugleich. Eine Flaeche, die zwei Koerper teilen (eine
haftende Fuge mit gemeinsamen Knoten), steht darin zweimal - einmal je
Koerper; die beiden sind als Partner vermerkt. Was sichtbar ist, ist dann nur
noch eine Zellauswahl:

* die Zelle gehoert zu einem sichtbaren Element, und
* sie hat keinen Partner, oder dessen Element ist ausgeblendet (dann liegt
  die Fuge frei, wie bei ``extract_surface`` ueber das Restgitter).

Das ist genau dann dieselbe Oberflaeche wie ``oberflaeche(to_grid(ausser=…))``,
wenn von jedem Koerper entweder alle oder keine Volumenelemente ausgeblendet
sind - ein halber Koerper haette innere Flaechen frei, die keine
Koerperhaut kennt. :meth:`Teiloberflaeche.teil` gibt dann ``None`` zurueck,
und die Ansicht baut das Gitter wie bisher. Gleiche Zellen und gleiches Bild
prueft ``tests/test_ausblenden_ohne_neuaufbau.py``.
"""
from __future__ import annotations

import numpy as np
import pyvista as pv
from vtkmodules.util.numpy_support import numpy_to_vtkIdTypeArray, vtk_to_numpy
from vtkmodules.vtkCommonDataModel import vtkCellArray

#: Zellarten einer PolyData in der Reihenfolge, in der VTK ihre Zellen zaehlt
_ARTEN = ("GetVerts", "GetLines", "GetPolys", "GetStrips")
_SETZEN = ("SetVerts", "SetLines", "SetPolys", "SetStrips")


def _zellfelder(pd):
    """[(offsets, connectivity)] je Zellart der PolyData als numpy."""
    aus = []
    for art in _ARTEN:
        ca = getattr(pd, art)()
        if ca is None or ca.GetNumberOfCells() == 0:
            aus.append((np.zeros(1, np.int64), np.zeros(0, np.int64)))
            continue
        aus.append((vtk_to_numpy(ca.GetOffsetsArray()).astype(np.int64, copy=False),
                    vtk_to_numpy(ca.GetConnectivityArray()).astype(np.int64, copy=False)))
    return aus


def polydata_teil(felder, n_zellen_je_art, punkte_knoten, X, behalten, zellwerte: dict):
    """Eine PolyData aus den Zellen mit ``behalten`` - die Punkte zusammengelegt
    je Modellknoten wie bei ``extract_surface`` ueber das Restgitter.

    ``felder``: :func:`_zellfelder` der Quelle, ``punkte_knoten`` je Punkt der
    Quelle sein Modellknoten, ``X`` die Modellknoten, ``zellwerte`` die
    Zellfelder der Quelle (je Zelle). Rueckgabe (PolyData, Knoten je Punkt)."""
    teile = []
    start = 0
    for (off, conn), n in zip(felder, n_zellen_je_art):
        b = behalten[start:start + n]
        start += n
        if n == 0 or not b.any():
            teile.append(None)
            continue
        laengen = np.diff(off)
        je_eintrag = np.repeat(b, laengen)
        teile.append((np.concatenate([[0], np.cumsum(laengen[b])]).astype(np.int64),
                      punkte_knoten[conn[je_eintrag]]))
    # Punkte je benutztem Modellknoten, aufsteigend - ueber eine Maske statt
    # unique/searchsorted (am Drehlager 0,5 s fuer 2,2 Mio. Eintraege)
    n_x = len(X)
    da = np.zeros(n_x, bool)
    for t in teile:
        if t is not None:
            da[t[1]] = True
    knoten = np.flatnonzero(da)
    rang = np.cumsum(da, dtype=np.int64) - 1
    pd = pv.PolyData()
    pd.points = np.asarray(X, float)[knoten] if len(knoten) else np.zeros((0, 3))
    for t, setzen in zip(teile, _SETZEN):
        if t is None:
            continue
        ca = vtkCellArray()
        ca.SetData(numpy_to_vtkIdTypeArray(t[0], deep=True),
                   numpy_to_vtkIdTypeArray(rang[t[1]], deep=True))
        getattr(pd, setzen)(ca)
    for name, werte in zellwerte.items():
        pd.cell_data[name] = np.asarray(werte)[behalten]
    pd.point_data["vtkOriginalPointIds"] = knoten
    return pd, knoten


class Teiloberflaeche:
    """Die Haeute aller Koerper eines Gitters - einmal je Modellstand.

    ``grid`` ist :func:`viewport.to_grid` ohne Ausnahmen (``cell_data["elem"]``),
    ``gruppe_je_element`` die Gruppe jedes Modellelements: Koerper 0 … K-1,
    Volumenelemente ohne Koerper eine eigene Gruppe, alles andere (Schalen,
    Staebe) die Gruppe -1 - deren Zellen gehen ohnehin unveraendert durch
    ``extract_surface`` und lassen sich einzeln ausblenden.
    """

    def __init__(self, grid, X, gruppe_je_element, volumen_vtk, alle_typen: bool = False):
        #: Enthaelt das Gitter alle Elementtypen (fuer den Geist, der keine
        #: Sichtbarkeitsschalter kennt)?
        self.alle_typen = bool(alle_typen)
        self.X = np.asarray(X, float)
        self.n_elemente = len(gruppe_je_element)
        self.gruppe_je_element = np.asarray(gruppe_je_element, np.int64)
        elem = np.asarray(grid.cell_data["elem"], np.int64)
        typ = np.asarray(grid.celltypes)
        ist_vol = np.isin(typ, list(volumen_vtk))
        gruppe = self.gruppe_je_element[elem].copy()
        gruppe[~ist_vol] = -1
        #: Volumenelemente je Gruppe (fuer die Pruefung „ganz oder gar nicht")
        self.vol_element = np.zeros(self.n_elemente, bool)
        self.vol_element[elem[ist_vol]] = True
        g_vol = gruppe[ist_vol]
        self.n_gruppen = int(g_vol.max()) + 1 if len(g_vol) else 0
        self.groesse = np.bincount(g_vol, minlength=self.n_gruppen) if len(g_vol) else np.zeros(0, int)
        # Die Gruppen voneinander loesen: je (Gruppe, Knoten) ein eigener Punkt
        off = np.asarray(grid.cell_offsets if hasattr(grid, "cell_offsets") else grid.offset, np.int64)
        conn = np.asarray(grid.cell_connectivity, np.int64)
        laengen = np.diff(off)
        nn = len(self.X)
        schl = (np.repeat(gruppe, laengen) + 1) * nn + conn
        eindeutig, neu = np.unique(schl, return_inverse=True)
        knoten = eindeutig % nn
        cells = np.empty(len(conn) + len(laengen), np.int64)
        kopf = off[:-1] + np.arange(len(laengen))
        cells[kopf] = laengen
        maske = np.ones(len(cells), bool)
        maske[kopf] = False
        cells[maske] = neu
        gel = pv.UnstructuredGrid(cells, typ, self.X[knoten])
        gel.cell_data["elem"] = elem
        gel.point_data["_knoten"] = knoten.astype(float)
        haut = gel.extract_surface(pass_pointid=False, pass_cellid=False, algorithm="dataset_surface")
        self.punkte_knoten = np.rint(np.asarray(haut.point_data["_knoten"], float)).astype(np.int64)
        self.elem = np.asarray(haut.cell_data["elem"], np.int64)
        self.felder = _zellfelder(haut)
        self.n_je_art = [int(len(off_) - 1) for off_, _c in self.felder]
        self.n_zellen = int(sum(self.n_je_art))
        self.partner = self._partner(gruppe_der_zelle=np.where(
            self.vol_element[self.elem], self.gruppe_je_element[self.elem], -1))
        self._letzt = None

    def _partner(self, gruppe_der_zelle) -> np.ndarray:
        """Je Zelle die Zelle derselben Flaeche in einer anderen Gruppe, sonst -1."""
        partner = np.full(self.n_zellen, -1, np.int64)
        basis = self.n_je_art[0] + self.n_je_art[1]
        off, conn = self.felder[2]
        if self.n_je_art[2] == 0:
            return partner
        laengen = np.diff(off)
        for k in np.unique(laengen):
            zellen = np.flatnonzero(laengen == k)
            idx = off[zellen][:, None] + np.arange(k)[None, :]
            M = np.sort(self.punkte_knoten[conn[idx]], axis=1)
            folge = np.lexsort(M.T[::-1])
            Ms = M[folge]
            gleich = np.all(Ms[1:] == Ms[:-1], axis=1)
            a = zellen[folge[:-1][gleich]] + basis
            b = zellen[folge[1:][gleich]] + basis
            andere = gruppe_der_zelle[a] != gruppe_der_zelle[b]
            partner[a[andere]] = b[andere]
            partner[b[andere]] = a[andere]
        return partner

    def sicht_maske(self, ausser) -> np.ndarray:
        """Je Modellelement: sichtbar (nicht in ``ausser``)?"""
        sicht = np.ones(self.n_elemente, bool)
        weg = np.fromiter((int(i) for i in ausser), np.int64, len(ausser)) if len(ausser) else \
            np.zeros(0, np.int64)
        sicht[weg[(weg >= 0) & (weg < self.n_elemente)]] = False
        return sicht

    def ganze_gruppen(self, sicht: np.ndarray) -> bool:
        """Sind von jeder Gruppe alle oder keine Volumenelemente sichtbar?"""
        if not self.n_gruppen:
            return True
        weg = np.flatnonzero(~sicht & self.vol_element)
        if not len(weg):
            return True
        n = np.bincount(self.gruppe_je_element[weg], minlength=self.n_gruppen)
        return bool(np.all((n == 0) | (n == self.groesse)))

    def sichtbare_zellen(self, sicht: np.ndarray) -> np.ndarray:
        behalten = sicht[self.elem]
        p = self.partner
        hat = p >= 0
        behalten[hat] &= ~sicht[self.elem[p[hat]]]
        return behalten

    def teil(self, ausser):
        """(Oberflaeche, Knoten je Punkt) ohne die Elemente ``ausser`` - oder
        None, wenn das nicht dieselbe Oberflaeche waere wie neu gebildet."""
        return self.teil_maske(self.sicht_maske(ausser))

    def teil_maske(self, sicht: np.ndarray):
        """Wie :meth:`teil`, die sichtbaren Elemente als Maske."""
        if not self.ganze_gruppen(sicht):
            return None
        behalten = self.sichtbare_zellen(sicht)
        if not behalten.any():
            return None
        return polydata_teil(self.felder, self.n_je_art, self.punkte_knoten, self.X, behalten,
                             {"elem": self.elem})

    def gruppenhaut(self, elemente, X=None):
        """Die Haut genau dieser Elemente, wenn sie ganze Gruppen sind (fuer
        die Hervorhebung eines gewaehlten Koerpers) - sonst None. ``X``: die
        Knotenlage des Bildes (verformt), sonst die Modellknoten."""
        el = np.unique(np.asarray([int(e) for e in elemente if 0 <= int(e) < self.n_elemente], np.int64))
        if not len(el) or not self.vol_element[el].all() or not self.n_gruppen:
            return None
        n = np.bincount(self.gruppe_je_element[el], minlength=self.n_gruppen)
        if not np.all((n == 0) | (n == self.groesse)):
            return None
        drin = np.zeros(self.n_elemente, bool)
        drin[el] = True
        zellen = drin[self.elem]
        if not zellen.any():
            return None
        lage = self.X if X is None or len(X) != len(self.X) else np.asarray(X, float)
        return polydata_teil(self.felder, self.n_je_art, self.punkte_knoten, lage, zellen,
                             {"elem": self.elem})[0]
