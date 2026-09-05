"""
Statik3D - grafische Oberflaeche.

Start:  python -m statik3d.gui
"""
from __future__ import annotations

import os
import sys
import traceback

os.environ.setdefault("QT_API", "pyside6")

import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets

import pyvista as pv
from pyvistaqt import QtInteractor

from ..model import Model, Material, Section, ShellProp, DOF_NAMES, Member
from .. import solver, mesher, parallel, __version__
from .dialogs import (NumEdit, row, MaterialDialog, SectionDialog, LoadCaseDialog,
                      CombinationDialog, AutoCombinationDialog, FatigueLoadDialog, MemberDialog,
                      DesignSettingsDialog, ContactPairDialog, ImportDialog, ReportDialog,
                      SupportNonlinearDialog, JointDialog,
                      VerformungsgrenzeDialog, BeulfeldDialog,
                      VolumenbereichDialog,
                      LasteinleitungDialog, parse_int_list)
from . import dialogs as dg
from .worker import SolveWorker
from . import ribbon as rib
from . import masken as msk
from . import tabellen as tab
from .tabellen import Spalte
from .. import ks
from . import viewport as vp
from . import design as dsg
from .viewport import to_grid  # noqa: F401  (Kompatibilitaet)

FIELDS = ["|u| Verschiebung", "ux", "uy", "uz", "Vergleichsspannung",
          "Ausnutzung EC3", "Ausnutzung Ermüdung", "Ausnutzung elastisch", "keine Färbung"]
DIAGRAMS = ["kein Verlauf", "N", "Vy", "Vz", "Mt", "My", "Mz"]
#: Zeilenhoehe der Kennwerte im Bild [Bildpunkte] bei Schriftgroesse 8
ZEILENHOEHE = 15


# ==========================================================================
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1600, 980)
        self.model = Model("Neues Modell")
        self.__init_defaults()
        self.analysis: solver.Analysis | None = None
        self.results: solver.Results | None = None     # Modal/Knicken
        self.selection = np.array([], dtype=int)
        self.path = None
        self.worker = None
        #: Darstellungsart des Viewports und Groesse der Lagersymbole
        self.darstellung = "Voll"
        self.lagergroesse = 1.0
        #: Was ein Klick in der Ansicht trifft. Die Geometriekette geht von
        #: Knoten ueber Linien und Flaechen zu Volumen; jede Stufe braucht
        #: darum ihre eigene Auswahl.
        self.auswahlart = "Knoten"
        self.sel_linien: list[str] = []
        self.sel_flaechen: list[str] = []
        self.sel_koerper: list[str] = []
        self.sel_staebe: list[str] = []
        #: Elemente, die aus dem Modellbaum heraus aufleuchten
        self.leuchtet: list[int] = []
        #: Sicht: was ausgeblendet ist - Elemente (Nummern), Linien, Flaechen
        #: und Koerper (Namen) - und die Schritte davor, damit "Vorherige
        #: Sicht" zurueckgehen kann.
        self.versteckt = {"elemente": set(), "linien": set(), "flaechen": set(),
                          "koerper": set()}
        self._sicht_verlauf: list = []
        self._sicht_stand = None

        self.setStyleSheet(dsg.stil() + rib.stil() + msk.stil() + tab.stil())
        self._undo_init()
        self._ks_init()
        self._build_viewport()
        self._build_panels()
        self._build_bottom()
        self.kopf = dsg.Kopfzeile(self)
        self._build_ribbon()
        self._build_glasleiste()
        self._build_update_button()
        self._refresh_kopf()
        self._build_baum()
        self._refresh_title()
        self._build_statusleiste()
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(180)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.refresh_all()

    def _build_statusleiste(self):
        """Statusleiste nach Vorgabe: Fang, Koordinatensystem, Einheiten,
        Netz- und Solverstatus. Der Modellumfang steht im Modellbaum, die
        Fassung unter Extras → Info (Vorgabe Kap. 16.1 Nr. 4 und 5)."""
        sb = self.statusBar()
        sb.showMessage("Bereit")
        self.lbl_fang = QtWidgets.QLabel("Fang: aus")
        self.lbl_ks = QtWidgets.QLabel("KS: global")
        self.lbl_einheiten = QtWidgets.QLabel("m · N · Pa")
        self.lbl_netz = QtWidgets.QLabel("Netz: –")
        self.lbl_solver = QtWidgets.QLabel("Solver: bereit")
        for w in (self.lbl_fang, self.lbl_ks, self.lbl_einheiten,
                  self.lbl_netz, self.lbl_solver):
            w.setObjectName("statusfeld")
            sb.addPermanentWidget(w)
        # Der Update-Hinweis erscheint nur, wenn eine neuere Fassung vorliegt.
        self.lbl_version = QtWidgets.QLabel()
        self.lbl_version.setVisible(False)
        sb.addPermanentWidget(self.lbl_version)

    def _refresh_status(self):
        """Netz- und Solverstand in der Statusleiste."""
        if not hasattr(self, "lbl_netz"):
            return
        self.lbl_ks.setText(f"KS: {self.ks_aktiv}")
        arten = getattr(self, "fang_arten", None) or []
        if getattr(self, "fang_an", False) and arten:
            fang = ("alle" if set(arten) >= set(ks.FANGARTEN)
                    else ", ".join(ks.FANG_TEXT.get(a, a) for a in arten))
        else:
            fang = "aus"
        self.lbl_fang.setText(f"Fang: {fang}"
                              + f" · {self.arbeitsebene.ebene}"
                              + (f" · Raster {self.arbeitsebene.raster:g} m"
                                 if self.arbeitsebene.raster > 0 else ""))
        if hasattr(self, "cb_ks") and self.cb_ks.count() != len(self.ks_liste):
            self.cb_ks.blockSignals(True)
            self.cb_ks.clear()
            self.cb_ks.addItems(list(self.ks_liste))
            self.cb_ks.setCurrentText(self.ks_aktiv)
            self.cb_ks.blockSignals(False)
        m = self.model
        self.lbl_netz.setText(f"Netz: {m.nn} Knoten · {len(m.elements)} Elemente"
                              if m.nn else "Netz: leer")
        if self.analysis is not None:
            n = len(self.analysis.cases) + len(self.analysis.combinations)
            self.lbl_solver.setText(f"Solver: {n} Ergebnisse")
        elif self.results is not None:
            self.lbl_solver.setText("Solver: Ergebnis vorhanden")
        else:
            self.lbl_solver.setText("Solver: bereit")

    def __init_defaults(self):
        if not self.model.materials:
            self.model.add_material(Material.steel("S235"))
            self.model.add_material(Material.steel("S355"))
        if not self.model.sections:
            self.model.add_section(Section.from_profile("IPE 200"))
            self.model.add_section(Section.from_profile("HEB 200"))
        if not self.model.shells:
            self.model.add_shell_prop(ShellProp("t = 10 mm", 0.010))

    # ------------------------------------------------------------------
    def _build_viewport(self):
        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.plotter = QtInteractor(central)
        self.plotter.set_background("white")
        lay.addWidget(self.plotter.interactor, 1)
        self.setCentralWidget(central)
        # Die nicht-modalen Masken schweben ueber der Ansicht (Vorgabe 3.8)
        self.maskenrand = msk.Maskenrand(central)
        try:
            # pickable_window=True: der Rueckruf kommt auch, wenn der Klick
            # keinen Koerper trifft. Ob etwas getroffen ist, entscheiden wir
            # selbst - in Bildschirmpunkten, nicht ueber die VTK-Trefferprobe.
            self.plotter.enable_point_picking(callback=self._picked, show_message=False,
                                              left_clicking=True, show_point=False,
                                              pickable_window=True)
        except Exception:
            pass
        # Rechtsklick: Kontextmenue zu dem, was unter dem Zeiger liegt
        try:
            self.plotter.interactor.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self.plotter.interactor.customContextMenuRequested.connect(self._viewport_menu)
        except Exception:
            pass
        # Mausrad: zum Zeiger zoomen statt zur Bildmitte
        try:
            self.plotter.interactor.installEventFilter(self)
        except Exception:
            pass
        # Beim Drehen eines grossen Modells bleiben Nebendarsteller kurz weg
        try:
            stil = self.plotter.iren.style
            fuegen = getattr(stil, "add_observer", None) or stil.AddObserver
            fuegen("StartInteractionEvent", self._interaktion_beginnt)
            fuegen("EndInteractionEvent", self._interaktion_endet)
        except Exception:
            pass

    #: Zoomfaktor je Rasterschritt des Mausrades
    RADSCHRITT = 1.15

    def eventFilter(self, obj, ereignis):
        """Das Mausrad selbst behandeln, damit es zum Zeiger zoomt.

        VTK zoomt von Haus aus auf die Bildmitte; wer sich eine Schweissnaht
        ansehen will, muss sie danach jedes Mal wieder in die Mitte schieben.
        Das Ereignis wird darum hier abgefangen (und mit ``True`` verbraucht,
        damit VTK nicht ein zweites Mal zoomt).
        """
        try:
            if (obj is self.plotter.interactor
                    and ereignis.type() == QtCore.QEvent.Wheel):
                self._rad(ereignis)
                return True
        except Exception:                   # noqa: BLE001
            return False
        return super().eventFilter(obj, ereignis)

    def _rad(self, ereignis) -> None:
        """Ein Mausradschritt: zoomen und den Punkt unter dem Zeiger festhalten."""
        try:
            grad = ereignis.angleDelta().y()
        except Exception:                   # noqa: BLE001
            grad = 0
        if not grad:
            return
        try:
            pos = ereignis.position()
            x_qt, y_qt = pos.x(), pos.y()
        except Exception:                   # noqa: BLE001
            x_qt, y_qt = ereignis.x(), ereignis.y()
        self.zoom_zum_zeiger(self.RADSCHRITT ** (grad / 120.0), x_qt, y_qt)

    def _bildpunkt_in_welt(self, x: float, y: float):
        """Weltpunkt unter dem Fensterpunkt (x, y), in der Tiefe des Zielpunktes.

        Ohne Trefferprobe: der Punkt liegt in der Ebene durch den Zielpunkt der
        Kamera, senkrecht zur Blickrichtung. Genau der muss beim Zoomen unter
        dem Zeiger stehen bleiben - auch dann, wenn dort gar nichts ist.
        """
        try:
            ren = self.plotter.renderer
            kam = ren.GetActiveCamera()
            ren.SetWorldPoint(*kam.GetFocalPoint(), 1.0)
            ren.WorldToDisplay()
            z = ren.GetDisplayPoint()[2]
            ren.SetDisplayPoint(float(x), float(y), float(z))
            ren.DisplayToWorld()
            w = ren.GetWorldPoint()
            if abs(w[3]) < 1e-12:
                return None
            return np.array(w[:3], float) / w[3]
        except Exception:                   # noqa: BLE001
            return None

    def zoom_zum_zeiger(self, faktor: float, x_qt: float, y_qt: float) -> None:
        """Um ``faktor`` zoomen, ohne dass sich der Punkt unter dem Zeiger bewegt.

        Gemessen wird zweimal derselbe Fensterpunkt - einmal vor und einmal
        nach dem Zoom. Die Kamera wird um die Differenz verschoben; damit
        bleibt liegen, was unter dem Zeiger lag. Das gilt fuer beide
        Projektionen: perspektivisch faehrt die Kamera vor, parallel wird der
        Massstab geaendert.
        """
        if not faktor or faktor <= 0:
            return
        try:
            ren = self.plotter.renderer
            kam = ren.GetActiveCamera()
            hoehe = self.plotter.render_window.GetSize()[1]
            x = float(x_qt)
            y = float(hoehe - 1 - y_qt)     # Qt zaehlt von oben, VTK von unten
            vorher = self._bildpunkt_in_welt(x, y)
            if kam.GetParallelProjection():
                kam.SetParallelScale(max(kam.GetParallelScale() / faktor, 1e-12))
            else:
                kam.Dolly(faktor)
            nachher = self._bildpunkt_in_welt(x, y)
            if vorher is not None and nachher is not None:
                d = vorher - nachher
                kam.SetPosition(*(np.asarray(kam.GetPosition(), float) + d))
                kam.SetFocalPoint(*(np.asarray(kam.GetFocalPoint(), float) + d))
            ren.ResetCameraClippingRange()
            self._kamera_steht = True
            self.plotter.render()
        except Exception:                   # noqa: BLE001
            pass

    def darstellung_setzen(self, name: str):
        """Darstellungsart umschalten (Voll, Transparent, Hidden-Line, Draht)."""
        if name not in vp.DARSTELLUNGEN:
            return
        self.darstellung = name
        for k, a in getattr(self, "act_darstellung", {}).items():
            if a.isChecked() != (k == name):
                a.setChecked(k == name)
        self.statusBar().showMessage(f"Darstellung: {name} – "
                                     f"{vp.DARSTELLUNGEN[name][1]}", 4000)
        self.redraw()

    def _lagergroesse_geschoben(self, wert: int):
        self.lagergroesse = max(0.2, wert / 10.0)
        self.redraw()

    def lagergroesse_zuruecksetzen(self):
        """Grundgroesse fuer alle Lager - auch die einzeln eingestellten."""
        self.lagergroesse = 1.0
        for s in self.model.supports:
            s.groesse = 1.0
        if hasattr(self, "sl_lager"):
            self.sl_lager.blockSignals(True)
            self.sl_lager.setValue(10)
            self.sl_lager.blockSignals(False)
        self.redraw()

    def _weltpunkt(self, x: int, y: int):
        """Weltkoordinate unter dem Mauszeiger - oder None, wenn dort nichts ist.

        Qt zaehlt die Bildschirmzeilen von oben, VTK von unten; darum wird y
        gespiegelt. Der Picker liefert nur dann einen Punkt, wenn wirklich ein
        Koerper getroffen wurde - ein Klick ins Leere gibt None.
        """
        try:
            from vtkmodules.vtkRenderingCore import vtkPropPicker
        except Exception:                       # noqa: BLE001
            try:
                from vtk import vtkPropPicker   # aeltere VTK-Pakete
            except Exception:                   # noqa: BLE001
                return None
        try:
            iren = self.plotter.interactor
            h = iren.height()
            picker = vtkPropPicker()
            if picker.Pick(float(x), float(h - 1 - y), 0.0, self.plotter.renderer):
                return np.asarray(picker.GetPickPosition(), float)
        except Exception:                       # noqa: BLE001
            return None
        return None

    def _viewport_menu(self, pos):
        """Rechtsklick im Viewport: was unter dem Zeiger liegt, steht oben."""
        m = self.model
        punkt = self._weltpunkt(pos.x(), pos.y())
        idx = vp.support_at(m, punkt, m.characteristic_size(), self.lagergroesse) \
            if m.nn else None
        menu = QtWidgets.QMenu(self)
        if idx is not None:
            s = m.supports[idx]
            name = s.name or f"Lager {idx + 1}"
            titel = menu.addAction(f"{name}  (Knoten {s.node})")
            titel.setEnabled(False)
            menu.addSeparator()
            menu.addAction("Größe dieses Lagers…",
                           lambda i=idx: self.lagergroesse_einstellen(i))
            menu.addAction("Größe aller Lager…",
                           lambda: self.lagergroesse_einstellen(None))
            menu.addAction("Lager bearbeiten…",
                           lambda i=idx: self.lager_bearbeiten(i))
            menu.addAction("Lager löschen",
                           lambda i=idx: self.lager_loeschen(i))
            menu.addSeparator()
        else:
            menu.addAction("Größe aller Lager…",
                           lambda: self.lagergroesse_einstellen(None))
            menu.addSeparator()
        for name, (zeichen, hinweis) in vp.DARSTELLUNGEN.items():
            a = menu.addAction(f"{zeichen}  {name}",
                               lambda n=name: self.darstellung_setzen(n))
            a.setCheckable(True)
            a.setChecked(self.darstellung == name)
            a.setToolTip(hinweis)
        menu.addSeparator()
        a = menu.addAction("FE-Netz zeigen", lambda: (
            self.act_edges.setChecked(not self.act_edges.isChecked())))
        a.setCheckable(True)
        a.setChecked(self.act_edges.isChecked())
        a = menu.addAction("Knoten zeigen", lambda: (
            self.act_knoten.setChecked(not self.act_knoten.isChecked())))
        a.setCheckable(True)
        a.setChecked(self.act_knoten.isChecked())
        menu.addSeparator()
        menu.addAction("Zoom alles", self.zoom_alles)
        menu.exec(self.plotter.interactor.mapToGlobal(pos))

    def lagergroesse_einstellen(self, idx=None):
        """Symbolgroesse eines Lagers oder aller Lager einstellen."""
        if idx is None:
            wert, ok = QtWidgets.QInputDialog.getDouble(
                self, "Größe aller Lager", "Faktor (1,0 = Grundgröße):",
                float(self.lagergroesse), 0.2, 6.0, 2)
            if not ok:
                return
            self.lagergroesse = float(wert)
            if hasattr(self, "sl_lager"):
                self.sl_lager.blockSignals(True)
                self.sl_lager.setValue(int(round(wert * 10)))
                self.sl_lager.blockSignals(False)
            self.redraw()
            return
        if not (0 <= idx < len(self.model.supports)):
            return
        s = self.model.supports[idx]
        name = s.name or f"Lager {idx + 1}"
        wert, ok = QtWidgets.QInputDialog.getDouble(
            self, f"Größe: {name}", "Faktor (1,0 = Grundgröße):",
            float(getattr(s, "groesse", 1.0) or 1.0), 0.2, 6.0, 2)
        if not ok:
            return
        self.merken(f"Lagergröße {name}")
        s.groesse = float(wert)
        self.redraw()

    def lager_loeschen(self, idx: int):
        if not (0 <= idx < len(self.model.supports)):
            return
        s = self.model.supports[idx]
        name = s.name or f"Lager {idx + 1}"
        if QtWidgets.QMessageBox.question(
                self, "Lager löschen", f"{name} an Knoten {s.node} löschen?") \
                != QtWidgets.QMessageBox.Yes:
            return
        self.merken(f"Lager {name} gelöscht")
        del self.model.supports[idx]
        self.refresh_all()

    def lager_bearbeiten(self, idx: int):
        """Das angeklickte Lager in der Lagermaske zeigen."""
        if not (0 <= idx < len(self.model.supports)):
            return
        s = self.model.supports[idx]
        self.selection = np.array([int(s.node)], dtype=int)
        self.maske_zeigen("Lager/Lasten")
        self.redraw()

    AUSWAHLARTEN = ["Knoten", "Linie", "Fläche", "Volumen", "Stab"]

    def auswahlart_setzen(self, art: str):
        """Umschalten, was ein Klick in der Ansicht trifft."""
        if art not in self.AUSWAHLARTEN:
            return
        self.auswahlart = art
        for feld in (getattr(self, "cb_auswahlart", None),
                     getattr(self, "cb_auswahlart_glas", None)):
            if feld is not None and feld.currentText() != art:
                feld.blockSignals(True)
                feld.setCurrentText(art)
                feld.blockSignals(False)
        self.statusBar().showMessage(f"Auswahl: {art}", 3000)

    def _objekt_umschalten(self, liste: list, name: str, was: str):
        """Ein Objekt der Auswahl zufuegen oder herausnehmen."""
        if name in liste:
            liste.remove(name)
        else:
            liste.append(name)
        self.lbl_sel.setText(f"{len(liste)} {was} ausgewählt"
                             + (f" ({', '.join(liste[:6])}"
                                + (" …" if len(liste) > 6 else "") + ")" if liste else ""))
        self.redraw()

    #: Fangradius um den Mauszeiger [Bildschirmpunkte]. In Pixeln, nicht in
    #: Metern: was man sieht, will man treffen - unabhaengig davon, wie weit
    #: man gerade hineingezoomt hat.
    FANGRADIUS = 14

    def _zeigerposition(self):
        """Mausposition im Fenster (VTK zaehlt von unten) - oder None."""
        try:
            x, y = self.plotter.iren.interactor.GetEventPosition()
            return float(x), float(y)
        except Exception:                   # noqa: BLE001
            return None

    def _projizieren(self, punkte):
        """Weltpunkte -> Fensterkoordinaten [Pixel] und Sichtbarkeit.

        Genommen wird die zusammengesetzte Projektionsmatrix der Kamera; das
        ist genau die Abbildung, die auch das Bild erzeugt. Auf ihr fusst der
        Fang: der Abstand wird dort gemessen, wo der Anwender ihn sieht.
        """
        P = np.atleast_2d(np.asarray(punkte, float))
        if not len(P):
            return np.zeros((0, 2)), np.zeros(0, bool)
        ren = self.plotter.renderer
        kam = ren.GetActiveCamera()
        breite, hoehe = self.plotter.render_window.GetSize()
        M = kam.GetCompositeProjectionTransformMatrix(ren.GetTiledAspectRatio(),
                                                      -1.0, 1.0)
        A = np.array([[M.GetElement(i, j) for j in range(4)] for i in range(4)])
        H = np.hstack([P, np.ones((len(P), 1))]) @ A.T
        w = H[:, 3]
        gut = np.abs(w) > 1e-12
        ndc = np.zeros((len(P), 3))
        ndc[gut] = H[gut, :3] / w[gut, None]
        xy = np.stack([(ndc[:, 0] * 0.5 + 0.5) * breite,
                       (ndc[:, 1] * 0.5 + 0.5) * hoehe], axis=1)
        sichtbar = gut & (w > 0) & (np.abs(ndc[:, 2]) <= 1.0)
        return xy, sichtbar

    def _naechster_am_zeiger(self, punkte, radius: float = None):
        """(Nummer, Abstand in Pixeln) des Punktes unter dem Zeiger - oder None."""
        zp = self._zeigerposition()
        P = np.atleast_2d(np.asarray(punkte, float))
        if zp is None or not len(P):
            return None
        xy, sichtbar = self._projizieren(P)
        d = np.linalg.norm(xy - np.asarray(zp, float), axis=1)
        d[~sichtbar] = np.inf
        i = int(np.argmin(d))
        r = self.FANGRADIUS if radius is None else radius
        return (i, float(d[i])) if d[i] <= r else None

    def _strecken_treffer(self, A, B, radius: float = None):
        """(Nummer, Lage t, Abstand) der Strecke A[i]-B[i] unter dem Zeiger.

        Gemessen wird in Bildschirmpunkten; t ist die Lage des Fusspunkts auf
        der Strecke (0 = A, 1 = B). None, wenn keine Strecke nah genug liegt.
        """
        zp = self._zeigerposition()
        A = np.atleast_2d(np.asarray(A, float))
        B = np.atleast_2d(np.asarray(B, float))
        if zp is None or not len(A):
            return None
        a, sa = self._projizieren(A)
        b, sb = self._projizieren(B)
        q = np.asarray(zp, float)
        ab = b - a
        L2 = np.einsum("ij,ij->i", ab, ab)
        t = np.zeros(len(a))
        gut = L2 > 1e-12
        t[gut] = np.clip(np.einsum("ij,ij->i", q - a, ab)[gut] / L2[gut], 0.0, 1.0)
        fuss = a + t[:, None] * ab
        d = np.linalg.norm(q - fuss, axis=1)
        d[~(sa | sb)] = np.inf
        i = int(np.argmin(d))
        r = self.FANGRADIUS if radius is None else radius
        return (i, float(t[i]), float(d[i])) if d[i] <= r else None

    def _strecken_am_zeiger(self, A, B, radius: float = None):
        """(Nummer, Abstand) der Strecke A[i]-B[i] unter dem Zeiger - oder None."""
        t = self._strecken_treffer(A, B, radius)
        return (t[0], t[2]) if t is not None else None

    def _fusspunkt_am_zeiger(self, A, B, radius: float = None):
        """Der Weltpunkt auf der Strecke unter dem Zeiger - oder None.

        Der Fusspunkt wird im Bild bestimmt und ueber seine Lage t auf die
        Strecke im Raum uebertragen; bei Parallelprojektion ist das genau, bei
        Perspektive auf einen Bruchteil der Streckenlaenge.
        """
        t = self._strecken_treffer(A, B, radius)
        if t is None:
            return None
        A = np.atleast_2d(np.asarray(A, float))
        B = np.atleast_2d(np.asarray(B, float))
        return A[t[0]] + t[1] * (B[t[0]] - A[t[0]])

    def _fangpunkt(self):
        """Was der Fang unter dem Zeiger findet: (Punkt, Art, Knotennummer).

        Die Reihenfolge ist verbindlich - ein Knoten geht der Kantenmitte vor,
        die einer Linie, die einem Stab, der eine Flaeche, die einem Volumen,
        und das Raster kommt zuletzt. Gemessen wird in Bildschirmpunkten; genau
        darum trifft der Fang das, was man sieht. Jede Art laesst sich einzeln
        abschalten (Ribbon "Fang", Glasleiste).
        """
        m = self.model
        arten = self.fang_arten if getattr(self, "fang_an", False) else ("knoten",)
        if "knoten" in arten and m.nn:
            treffer = self._naechster_am_zeiger(m.nodes)
            if treffer is not None:
                return m.nodes[treffer[0]], "knoten", treffer[0]
        if "mitte" in arten and len(m.elements):
            A, B = self._stabstrecken()
            if len(A):
                mitten = 0.5 * (A + B)
                treffer = self._naechster_am_zeiger(mitten)
                if treffer is not None:
                    return mitten[treffer[0]], "mitte", -1
        if "linie" in arten and getattr(m, "lines", None):
            A, B, _ = self._linienstrecken()
            if len(A):
                punkt = self._fusspunkt_am_zeiger(A, B)
                if punkt is not None:
                    return punkt, "linie", -1
        if "stab" in arten and len(m.elements):
            A, B = self._stabstrecken()
            if len(A):
                punkt = self._fusspunkt_am_zeiger(A, B)
                if punkt is not None:
                    return punkt, "stab", -1
        if "flaeche" in arten or "volumen" in arten:
            treffer = self._oberflaechenfang(arten)
            if treffer is not None:
                return treffer[0], treffer[1], -1
        if "raster" in arten and getattr(self.arbeitsebene, "raster", 0) > 0:
            frei = self._arbeitsebenenpunkt()
            if frei is not None:
                r = self.arbeitsebene.rasterpunkt(frei)
                treffer = self._naechster_am_zeiger(r[None, :])
                if treffer is not None:
                    return r, "raster", -1
        return None, "", -1

    def _linienstrecken(self):
        """Alle Linien als Strecken: (A, B, Linienname je Strecke).

        Krumme Linien sind abgetastet. Einmal je Modellstand aufgebaut - bei
        dreitausend Linien darf das nicht bei jedem Klick geschehen.
        """
        m = self.model
        stand = (id(m), len(m.lines or {}), m.nn,
                 hash(np.asarray(m.nodes, float).tobytes()) if m.nn else 0)
        if getattr(self, "_linienstrecken_stand", None) == stand:
            return self._linienstrecken_zwischen
        A, B, namen = [], [], []
        for name, ln in (m.lines or {}).items():
            idx = [int(n) for n in ln.nodes if 0 <= int(n) < m.nn]
            if len(idx) < 2:
                continue
            X = m.nodes[idx]
            if (ln.typ or "polyline") != "polyline":
                try:
                    X = np.asarray(ln.punkte(m, vp.TEILUNG_KURVE), float)
                except Exception:           # noqa: BLE001
                    X = m.nodes[idx]
            A.append(X[:-1])
            B.append(X[1:])
            namen += [name] * (len(X) - 1)
        out = (np.vstack(A) if A else np.zeros((0, 3)),
               np.vstack(B) if B else np.zeros((0, 3)), namen)
        self._linienstrecken_stand = stand
        self._linienstrecken_zwischen = out
        return out

    def _stabstrecken(self):
        """Anfangs- und Endpunkte aller Stabelemente (A, B) - je Modellstand einmal."""
        m = self.model
        stand = (id(m), len(m.elements), m.nn,
                 hash(np.asarray(m.nodes, float).tobytes()) if m.nn else 0)
        if getattr(self, "_stabstrecken_stand", None) == stand:
            return self._stabstrecken_zwischen
        paare = [(int(e.nodes[0]), int(e.nodes[-1])) for e in m.elements
                 if e.typ in vp.TYPEN_STAEBE and len(e.nodes) >= 2]
        if paare:
            idx = np.asarray(paare, int)
            out = (m.nodes[idx[:, 0]], m.nodes[idx[:, 1]])
        else:
            out = (np.zeros((0, 3)), np.zeros((0, 3)))
        self._stabstrecken_stand = stand
        self._stabstrecken_zwischen = out
        return out

    def _zellentreffer(self):
        """Was der VTK-Zellenpicker unter dem Zeiger trifft.

        Auf den Netz- und Geometriedarstellern (Elemente, Stabkoerper,
        Flaechen ohne Netz). Rueckgabe (Darstellername, Zellennummer, Punkt,
        Daten des Darstellers) oder None. So trifft ein Klick genau das, was
        man sieht - auch auf einem Zylindermantel.
        """
        zp = self._zeigerposition()
        if zp is None:
            return None
        try:
            from vtkmodules.vtkRenderingCore import vtkCellPicker
        except Exception:                       # noqa: BLE001
            try:
                from vtk import vtkCellPicker   # aeltere VTK-Pakete
            except Exception:                   # noqa: BLE001
                return None
        try:
            akteure = dict(self.plotter.renderer.actors)
        except Exception:                       # noqa: BLE001
            return None
        namen = [n for n in akteure
                 if n.startswith(("model_", "result_")) or n == "geo_flaechen"]
        if not namen:
            return None
        picker = vtkCellPicker()
        picker.SetTolerance(0.001)
        picker.PickFromListOn()
        for n in namen:
            picker.AddPickList(akteure[n])
        try:
            if not picker.Pick(float(zp[0]), float(zp[1]), 0.0, self.plotter.renderer):
                return None
        except Exception:                       # noqa: BLE001
            return None
        punkt = np.asarray(picker.GetPickPosition(), float)
        akteur, zelle = picker.GetActor(), int(picker.GetCellId())
        if akteur is None or zelle < 0:
            return None
        adresse = akteur.GetAddressAsString("vtkProp")
        name = next((n for n in namen
                     if akteure[n].GetAddressAsString("vtkProp") == adresse), "")
        try:
            daten = pv.wrap(akteur.GetMapper().GetInput())
        except Exception:                       # noqa: BLE001
            return None
        return name, zelle, punkt, daten

    def _elementzuordnung(self) -> dict:
        """{Element: Stab}, {Element: Flaeche}, {Element: Koerper} - je Modellstand."""
        m = self.model
        stand = (id(m), len(m.elements), len(m.members), len(m.flaechen), len(m.koerper))
        if getattr(self, "_zuordnung_stand", None) == stand:
            return self._zuordnung
        zu_stab = {int(e): n for n, mem in m.members.items() for e in (mem.elements or [])}
        zu_flaeche = {int(e): n for n, f in m.flaechen.items() for e in (f.elemente or [])}
        zu_koerper = {int(e): n for n, k in m.koerper.items() for e in (k.elemente or [])}
        self._zuordnung = {"stab": zu_stab, "flaeche": zu_flaeche, "koerper": zu_koerper}
        self._zuordnung_stand = stand
        return self._zuordnung

    def _objekt_am_zeiger(self, art: str):
        """Name der Flaeche, des Volumens oder des Stabes unter dem Zeiger.

        Ueber den Zellenpicker: getroffene Zelle -> Element -> Objekt, oder
        auf der Geometrie ohne Netz -> Flaeche -> (Koerper). None, wenn dort
        nichts Passendes liegt.
        """
        treffer = self._zellentreffer()
        if treffer is None:
            return None
        name, zelle, _punkt, daten = treffer
        m = self.model
        zu = self._elementzuordnung()
        if name == "geo_flaechen":
            fl = daten.cell_data.get("flaeche")
            if fl is None or zelle >= len(fl):
                return None
            fname = list(m.flaechen)[int(fl[zelle])]
            if art == "Fläche":
                return fname
            if art == "Volumen":
                return next((kn for kn, k in m.koerper.items() if fname in k.flaechen), None)
            return None
        el = daten.cell_data.get("elem")
        if el is None or zelle >= len(el):
            return None
        elem = int(el[zelle])
        if art == "Stab":
            return zu["stab"].get(elem)
        if art == "Fläche":
            return zu["flaeche"].get(elem)
        if art == "Volumen":
            return zu["koerper"].get(elem)
        return None

    def _oberflaechenfang(self, arten):
        """Der Punkt auf einer Flaeche oder einem Volumen unter dem Zeiger.

        Genommen wird die **gezeichnete Oberflaeche** selbst (Zellenpicker):
        so faengt man auf einem Zylindermantel oder einer Schale genau dort,
        wo der Zeiger steht. Rueckgabe (Punkt, Art) mit Art "flaeche" oder
        "volumen" - je nachdem, was getroffen ist und welche Fangarten an
        sind - oder None.
        """
        treffer = self._zellentreffer()
        if treffer is None:
            return None
        name, zelle, punkt, daten = treffer
        m = self.model
        koerper = getattr(m, "koerper", {}) or {}
        if name == "geo_flaechen":
            fl = daten.cell_data.get("flaeche")
            if fl is None or zelle >= len(fl):
                return None
            fname = list(m.flaechen)[int(fl[zelle])]
            if "flaeche" in arten:
                return punkt, "flaeche"
            if "volumen" in arten and any(fname in k.flaechen for k in koerper.values()):
                return punkt, "volumen"
            return None
        el = daten.cell_data.get("elem")
        if el is None or zelle >= len(el):
            return None
        typ = m.elements[int(el[zelle])].typ
        if typ in vp.TYPEN_VOLUMEN:
            if "volumen" in arten:
                return punkt, "volumen"
            if "flaeche" in arten:
                # die Aussenflaeche eines Koerpers ist eine Flaeche
                return punkt, "flaeche"
        elif typ in vp.TYPEN_FLAECHEN and "flaeche" in arten:
            return punkt, "flaeche"
        return None

    def _fangen(self, punkt):
        """Einen **gegebenen** Weltpunkt auf die naechste markante Stelle ziehen.

        Fuer die Eingabe ueber Zahlen und als Rueckfall. Was unter dem
        Mauszeiger liegt, beantwortet :meth:`_fangpunkt` - dort wird in
        Bildschirmpunkten gemessen, nicht in Metern.
        """
        if not getattr(self, "fang_an", False):
            return ks.Fangtreffer(np.asarray(punkt, float))
        kanten = [(int(e.nodes[0]), int(e.nodes[-1])) for e in self.model.elements
                  if e.typ in ("beam", "truss")][:4000]
        weite = 0.03 * max(self.model.characteristic_size(), 1e-6)
        return ks.fangen(punkt, self.model.nodes if self.model.nn else None,
                         kanten, self.arbeitsebene, weite, self.fang_arten)

    def _arbeitsebenenpunkt(self):
        """Wo der Sehstrahl unter dem Zeiger die Arbeitsebene trifft.

        Der Strahl wird aus zwei entprojizierten Fensterpunkten gebildet -
        einem auf der vorderen, einem auf der hinteren Klippebene.
        """
        zp = self._zeigerposition()
        if zp is None:
            return None
        ren = self.plotter.renderer
        punkte = []
        for tiefe in (0.0, 1.0):
            ren.SetDisplayPoint(zp[0], zp[1], tiefe)
            ren.DisplayToWorld()
            w = np.asarray(ren.GetWorldPoint(), float)
            if abs(w[3]) < 1e-12:
                return None
            punkte.append(w[:3] / w[3])
        richtung = punkte[1] - punkte[0]
        if float(np.linalg.norm(richtung)) < 1e-12:
            return None
        return self.arbeitsebene.schnitt(punkte[0], richtung)

    def _picked(self, point, *args):
        art = getattr(self, "auswahlart", "Knoten")
        if art != "Knoten":
            m = self.model
            size = m.characteristic_size()
            if art == "Linie":
                name = self._linie_am_zeiger() or vp.line_at(m, point, size)
                return self._objekt_umschalten(self.sel_linien, name, "Linien") \
                    if name else self.info("Dort liegt keine Linie")
            # Erst das, was gezeichnet ist (Zellenpicker) - das trifft auch
            # Zylindermaentel und Stabkoerper; die geometrische Suche ist der
            # Rueckfall, wenn der Klick knapp danebenliegt.
            if art == "Fläche":
                name = self._objekt_am_zeiger("Fläche") or vp.flaeche_at(m, point, size)
                return self._objekt_umschalten(self.sel_flaechen, name, "Flächen") \
                    if name else self.info("Dort liegt keine Fläche")
            if art == "Volumen":
                name = self._objekt_am_zeiger("Volumen") or vp.koerper_at(m, point, size)
                return self._objekt_umschalten(self.sel_koerper, name, "Volumen") \
                    if name else self.info("Dort liegt kein Volumenkörper")
            if art == "Stab":
                name = (self._stab_am_zeiger() or self._objekt_am_zeiger("Stab")
                        or vp.member_at(m, point))
                return self._objekt_umschalten(self.sel_staebe, name, "Stäbe") \
                    if name else self.info("Dort liegt kein Stab")
        if self.model.nn == 0:
            return
        p, fangart, i = self._fangpunkt()
        if p is None:
            return
        if i < 0:
            # Kantenmitte oder Rasterpunkt: erst wenn eine Maske einen Punkt
            # erwartet, wird daraus ein Knoten - sonst blieben Streuknoten liegen.
            if not (self.maskenrand.offen() and getattr(self.maskenrand.maske, "n_knoten", 0)):
                return self.statusBar().showMessage(
                    f"Gefangen: {fangart} bei {np.round(p, 4)} - "
                    "es ist keine Maske offen, die einen Punkt erwartet", 4000)
            self.merken("Knoten aus Fang")
            i = int(self.model.add_node(*p))
        # Ist eine Erzeuge-Maske offen, geht der Klick an sie: „Maske oder Klick“
        if self.maskenrand.knoten_angeklickt(i):
            self.redraw()
            return
        if i in self.selection:
            self.selection = self.selection[self.selection != i]
        else:
            self.selection = np.append(self.selection, i)
        self.lbl_sel.setText(f"{len(self.selection)} Knoten ausgewählt (zuletzt {i}: "
                             f"{np.round(self.model.nodes[i], 3)})")
        self._auswahl_register()
        self.redraw()

    def _linie_am_zeiger(self):
        """Name der Linie unter dem Zeiger - in Bildschirmpunkten gemessen."""
        A, B, namen = self._linienstrecken()
        if not len(A):
            return None
        treffer = self._strecken_am_zeiger(A, B)
        return namen[treffer[0]] if treffer is not None else None

    def _stab_am_zeiger(self):
        """Name des Stabes unter dem Zeiger - in Bildschirmpunkten gemessen."""
        m = self.model
        A, B, namen = [], [], []
        for name, mem in (m.members or {}).items():
            for e in (mem.elements or []):
                if e >= len(m.elements):
                    continue
                idx = [int(x) for x in m.elements[e].nodes]
                if len(idx) < 2:
                    continue
                A.append(m.nodes[idx[0]])
                B.append(m.nodes[idx[-1]])
                namen.append(name)
        if not A:
            return None
        treffer = self._strecken_am_zeiger(np.asarray(A), np.asarray(B))
        return namen[treffer[0]] if treffer is not None else None

    def _build_glasleiste(self):
        """Die durchscheinende Schnellleiste und der Ansichtswuerfel.

        Beides liegt **ueber** der Ansicht und nimmt keinen Platz weg. Die
        Knoepfe fuehren dieselben Aktionsobjekte wie das Ribbon - es sind
        keine zweiten Befehle, nur ein kuerzerer Weg fuer das, was man beim
        Modellieren staendig braucht. Alles als Symbol; der Klartext kommt
        beim Ueberfahren.
        """
        central = self.centralWidget()
        leiste = msk.Glasleiste(central)
        # Darstellungsart
        for name in vp.DARSTELLUNGEN:
            leiste.knopf(self.act_darstellung[name], vp.DARSTELLUNG_SYMBOL[name], name)
        leiste.trenner()
        # Was sichtbar ist
        for a, symbol, schluessel in ((self.act_knoten, "knoten", "knoten"),
                                      (self.act_linien, "linien", "linien"),
                                      (self.act_staebe, "staebe", "staebe"),
                                      (self.act_flaechen, "flaechen", "flaechen"),
                                      (self.act_volumen, "volumen", "volumen"),
                                      (self.act_edges, "netz", "netz"),
                                      (self.act_loads, "lasten", "lasten")):
            leiste.knopf(a, symbol, schluessel)
        leiste.trenner()
        # Sicht: nur die Auswahl, Auswahl weg, zurueck, alles
        for a, symbol, schluessel in ((self.act_nur_auswahl, "sicht_nur_auswahl", "nur_auswahl"),
                                      (self.act_auswahl_weg_sicht, "sicht_ausblenden", "ausblenden"),
                                      (self.act_sicht_zurueck, "sicht_zurueck", "zurueck"),
                                      (self.act_alles_zeigen, "sicht_alles", "alles")):
            leiste.knopf(a, symbol, schluessel)
        leiste.trenner()
        # Fang: Hauptschalter und je Art
        leiste.knopf(self.act_fang, "fang", "fang")
        for art in ("knoten", "linie", "stab", "flaeche", "volumen"):
            leiste.knopf(self.act_fangart[art], f"fang_{art}", f"fang_{art}")
        # Kein Auswahlfeld mehr in der Leiste: die Auswahlart steht im Ribbon
        # (Start) und folgt dem Modellbaum; die Leiste bleibt schmal.
        self.cb_auswahlart_glas = None
        leiste.adjustSize()
        wuerfel = msk.Ansichtswuerfel(central)
        wuerfel.kamera = self._kamera_matrix
        wuerfel.gewaehlt.connect(self.blickrichtung)
        wuerfel.gedreht.connect(self._wuerfel_gedreht)
        self.glasleiste = leiste
        self.ansichtswuerfel = wuerfel
        self.ansichtsrand = msk.Ansichtsrand(central, leiste, wuerfel)
        # Der Wuerfel dreht sich mit der Ansicht: ein leichter Takt schaut
        # nach, ob sich die Kamera bewegt hat, und zeichnet ihn dann neu.
        self._kamera_stand = None
        self._wuerfel_takt = QtCore.QTimer(self)
        self._wuerfel_takt.setInterval(120)
        self._wuerfel_takt.timeout.connect(self._wuerfel_nachfuehren)
        self._wuerfel_takt.start()

    def _kamera_matrix(self):
        """Die 3x3-Drehmatrix Welt -> Bild der Kamera - fuer den Wuerfel."""
        try:
            M = self.plotter.renderer.GetActiveCamera().GetViewTransformMatrix()
            return [[float(M.GetElement(i, j)) for j in range(3)] for i in range(3)]
        except Exception:                   # noqa: BLE001
            return None

    def _wuerfel_nachfuehren(self):
        R = self._kamera_matrix()
        stand = tuple(round(x, 4) for zeile in (R or []) for x in zeile)
        if stand != self._kamera_stand:
            self._kamera_stand = stand
            if getattr(self, "ansichtswuerfel", None) is not None:
                self.ansichtswuerfel.update()

    def _wuerfel_gedreht(self, dx: float, dy: float):
        """Ziehen auf dem Wuerfel dreht die Kamera um den Blickpunkt."""
        try:
            kam = self.plotter.renderer.GetActiveCamera()
            kam.Azimuth(-0.6 * dx)
            kam.Elevation(0.6 * dy)
            kam.OrthogonalizeViewUp()
            self.plotter.renderer.ResetCameraClippingRange()
            self._kamera_steht = True
            self.plotter.render()
        except Exception as ex:             # noqa: BLE001
            self.log.appendPlainText(f"Ansicht drehen: {ex}")

    #: Ab so vielen Knoten und Elementen wird beim Drehen vereinfacht gezeichnet
    SCHNELLDREHEN_AB = 20000
    #: Darsteller, die beim Drehen eines grossen Modells kurz wegbleiben
    NEBENDARSTELLER = ("knoten", "knoten_frei", "linien", "geo_volumen", "geo_raender",
                       "nlabels", "elabels", "loads", "lastfenster", "temp_warm",
                       "temp_kalt", "zwang", "zwang_drehung", "undeformed_netz",
                       "undeformed_stabkoerper")

    def _interaktion_beginnt(self, *_):
        """Drehen, Schieben, Zoomen beginnt: bei einem grossen Modell bleiben
        die Nebendarsteller (Knotenpunkte, Linien, Nummern, Lasten) und die
        Netzkanten weg, bis die Maus losgelassen wird. Ein Modell mit
        370000 Tetraedern ruckelte sonst und blieb zwischendurch haengen."""
        m = self.model
        if len(m.elements) + m.nn < self.SCHNELLDREHEN_AB or getattr(self, "_vereinfacht", None):
            return
        weg, kanten = [], []
        try:
            for name, a in dict(self.plotter.renderer.actors).items():
                if name in self.NEBENDARSTELLER:
                    if a.GetVisibility():
                        a.VisibilityOff()
                        weg.append(a)
                elif name.startswith(("model_", "result_")) and hasattr(a, "GetProperty"):
                    p = a.GetProperty()
                    if p.GetEdgeVisibility():
                        p.EdgeVisibilityOff()
                        kanten.append(p)
        except Exception:                       # noqa: BLE001
            pass
        self._vereinfacht = (weg, kanten)

    def _interaktion_endet(self, *_):
        """Maus losgelassen: alles wieder zeigen."""
        v = getattr(self, "_vereinfacht", None)
        if not v:
            return
        self._vereinfacht = None
        weg, kanten = v
        for a in weg:
            a.VisibilityOn()
        for p in kanten:
            p.EdgeVisibilityOn()
        try:
            self.plotter.render()
        except Exception:                       # noqa: BLE001
            pass

    #: Blickrichtung -> (Richtung, in die geschaut wird; "oben" im Bild; Klartext)
    BLICKRICHTUNGEN = {
        "oben": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0), "Draufsicht (von +Z)"),
        "unten": ((0.0, 0.0, 1.0), (0.0, -1.0, 0.0), "Untersicht (von −Z)"),
        "vorne": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), "Vorderansicht (von −Y)"),
        "hinten": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0), "Rückansicht (von +Y)"),
        "rechts": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), "Ansicht von rechts (von +X)"),
        "links": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), "Ansicht von links (von −X)"),
        # Die Achsennamen des Wuerfels: "von +X" heisst, die Kamera steht auf
        # der Seite +X und schaut in Richtung -X.
        "+x": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), "Ansicht von +X"),
        "-x": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), "Ansicht von -X"),
        "+y": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0), "Ansicht von +Y"),
        "-y": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), "Ansicht von -Y"),
        "+z": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0), "Ansicht von +Z (Draufsicht)"),
        "-z": ((0.0, 0.0, 1.0), (0.0, -1.0, 0.0), "Ansicht von -Z (Untersicht)"),
        # Die alten Namen bleiben gueltig - Ribbon und Tastenkuerzel nutzen sie
        "xy": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0), "Draufsicht (XY)"),
        "xz": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), "Vorderansicht (XZ)"),
        "yz": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), "Seitenansicht (YZ)"),
    }

    def blickrichtung(self, richtung: str):
        """Blickrichtung setzen - vom Ansichtswuerfel oder aus dem Ribbon.

        „kehren" dreht die laufende Ansicht um 180 Grad um den Blickpunkt: aus
        jeder beliebigen Schraegansicht wird ihre Rueckansicht. Das ist der
        schnelle Weg auf die Rueckseite, den eine Drehscheibe nicht hat - die
        muesste erst eine halbe Umdrehung machen und kann ausserdem nur um die
        Hochachse.
        """
        if richtung == "iso":
            self.plotter.view_isometric()
            self.zoom_alles()
            self.statusBar().showMessage("Isometrisch", 3000)
            return
        if richtung == "kehren":
            try:
                pos, blick, oben = self.plotter.camera_position
                pos = np.asarray(pos, float)
                blick = np.asarray(blick, float)
                self.plotter.camera_position = [
                    (blick - (pos - blick)).tolist(), blick.tolist(), oben]
                self._kamera_steht = True
                self.plotter.render()
                self.statusBar().showMessage("Ansicht umgekehrt – Rückseite", 3000)
            except Exception as ex:         # noqa: BLE001
                self.log.appendPlainText(f"Ansicht umkehren: {ex}")
            return
        eintrag = self.BLICKRICHTUNGEN.get(richtung)
        if eintrag is None:
            return
        blickvektor, oben, text = eintrag
        m = self.model
        mitte = (m.nodes.mean(axis=0) if m.nn else np.zeros(3))
        weite = max(m.characteristic_size(), 1e-6) * 3.0
        pos = mitte - np.asarray(blickvektor, float) * weite
        self.plotter.camera_position = [pos.tolist(), mitte.tolist(), list(oben)]
        self.zoom_alles()
        self.statusBar().showMessage(text, 3000)

    def _build_ribbon(self):
        """Die Befehlsleiste. Jeder Befehl steht hier - und nur hier.

        Ersetzt Menueleiste und Werkzeugleiste des Bestands; die Doppelung aus
        oberer Leiste und rechter Registerleiste entfaellt damit (Vorgabe
        Kap. 16.1 Nr. 1 und 2).
        """
        rb = rib.Ribbon(self)
        self.ribbon = rb
        rb.gesucht.connect(lambda t: self.info(f"Befehl „{t}“ ausgeführt")
                           if t else self.info("Kein Befehl gefunden"))

        # -- Datei -------------------------------------------------------
        r = rb.register("Datei")
        g = r.gruppe("Projekt")
        self.act_neu = g.gross("Neu", "▢", self.new_model, "Ctrl+N",
                               "Leeres Modell anlegen")
        g.gross("Öffnen", "▤", self.open_model, "Ctrl+O", "Modell aus Datei laden")
        self.act_speichern = g.gross("Speichern", "▣", self.save_model, "Ctrl+S",
                                     "Modell speichern")
        g.klein("Speichern unter…", lambda: self.save_model(True))
        g.klein("Projektangaben…", lambda: self.maske_zeigen("Projekt"),
                hinweis="Projekt, Bauteil, Position, Bearbeiter")
        g = r.gruppe("Austausch")
        g.gross("Übernehmen", "⇤", self.import_file, "Ctrl+I",
                "Aus RFEM 6, HiCAD, IFC, DXF, SAF, INP, BDF, STEP übernehmen")
        g.gross("Exportieren", "⇥", self.export_model, "Ctrl+E",
                "SDNF, DSTV-NC, IFC, SAF, DXF, STL, VTK, HiCAD")
        g.klein("Ergebnisse als CSV…", self.export_csv)
        g.klein("Netz + Ergebnisse als VTK…", self.export_vtk)
        g = r.gruppe("Beispiele")
        for key, label in (("frame", "Rahmen"), ("truss", "Fachwerk"),
                           ("plate", "Platte"), ("solid", "Konsole"),
                           ("hall", "Hallenrahmen"), ("gate", "Stauwand"),
                           ("contact", "Kontakt"), ("friction", "Reibung")):
            g.klein(label, lambda k=key: self.load_example(k),
                    hinweis=f"Beispiel {label} laden")
        g = r.gruppe("Sitzung")
        g.klein("Beenden", self.close, "Ctrl+Q")

        # -- Start -------------------------------------------------------
        r = rb.register("Start")
        g = r.gruppe("Zwischenablage")
        self.act_undo = g.gross("Rückgängig", "↶", self.undo, "Ctrl+Z",
                                "Letzte Änderung zurücknehmen")
        self.act_redo = g.gross("Wiederholen", "↷", self.redo, "Ctrl+Y",
                                "Zurückgenommene Änderung wiederholen")
        g = r.gruppe("Auswahl")
        self.act_auswahl_weg = g.gross("Auswahl aufheben", "✕", self.clear_selection,
                                       "Esc", "Alle gewählten Knoten abwählen")
        g.klein("Alles auswählen", self.select_all, "Ctrl+A")
        g.klein("Auswahl umkehren", self.invert_selection)
        g = r.gruppe("Modell prüfen")
        g.gross("Prüfen", "⚑", self.do_check, "", "Modell auf Fehler prüfen")
        g.klein("Doppelte Knoten zusammenführen", self.do_merge)
        g.klein("Freie Stabenden anschließen…", self.staebe_anschliessen)
        g.klein("Stäbe automatisch erkennen", self.auto_members)
        g = r.gruppe("Berechnen")
        self.act_rechnen = g.gross("Berechnen", "▶", lambda: self.do_solve("all"),
                                   "F5", "Alle Lastfälle und Kombinationen rechnen",
                                   rolle="start")

        # -- Geometrie ---------------------------------------------------
        r = rb.register("Geometrie")
        g = r.gruppe("Knoten")
        g.gross("Knoten", "•", self.maske_knoten, "",
                "Knoten über Koordinaten anlegen oder in der Ansicht klicken")
        g.klein("Knoten löschen", self.delete_nodes)
        g = r.gruppe("Linien")
        g.gross("Linie", "◜", self.maske_linie, "",
                "Polylinie, Bogen, Kreis, Spline oder Parabel")
        g.klein("Linie aus Knoten…", self.add_linie,
                hinweis="Aus den ausgewählten Knoten eine Linie machen")
        # Die Kette wie in RFEM: aus Knoten Linien, aus Linien Flaechen, aus
        # Flaechen Volumen. Jede Stufe nimmt, was in der Ansicht ausgewaehlt ist.
        g = r.gruppe("Flächen und Volumen")
        g.gross("Fläche aus Linien", "▱", self.add_flaeche_aus_auswahl, "",
                "Aus den ausgewählten Linien eine Fläche bilden")
        g.gross("Volumen aus Flächen", "▣", self.add_koerper_aus_auswahl, "",
                "Aus den ausgewählten Flächen einen Volumenkörper bilden")
        g.klein("Vernetzen", self.geometrie_vernetzen,
                hinweis="Die ausgewählten – sonst alle – Flächen und Körper vernetzen")
        g.klein("Netz löschen", self.netz_loeschen_geometrie,
                hinweis="Das Netz entfernen, die Geometrie bleibt")
        g.klein("Kontaktfugen ausführen", self.kontaktfugen_ausfuehren,
                hinweis="Die Netze an den Kontaktbedingungen trennen "
                        "(geschieht beim Vernetzen von selbst)")
        g = r.gruppe("Auswahl in der Ansicht")
        self.cb_auswahlart = QtWidgets.QComboBox()
        self.cb_auswahlart.addItems(self.AUSWAHLARTEN)
        self.cb_auswahlart.setMinimumWidth(110)
        self.cb_auswahlart.setToolTip("Was ein Klick in der Ansicht trifft")
        self.cb_auswahlart.currentTextChanged.connect(self.auswahlart_setzen)
        g.widget(self.cb_auswahlart)
        g.klein("Auswahl aufheben", self.clear_selection)
        g = r.gruppe("Koordinatensystem")
        self.cb_ks = QtWidgets.QComboBox()
        self.cb_ks.setMinimumWidth(120)
        self.cb_ks.currentTextChanged.connect(self.ks_waehlen)
        g.widget(self.cb_ks)
        g.klein("Neues KS…", self.ks_neu)
        g.klein("Aus drei Knoten", self.ks_aus_auswahl)
        g = r.gruppe("Arbeitsebene")
        self.cb_ebene = QtWidgets.QComboBox()
        self.cb_ebene.addItems(list(ks.EBENEN))
        self.cb_ebene.currentTextChanged.connect(
            lambda t: self.arbeitsebene_setzen(ebene=t))
        g.widget(self.cb_ebene)
        self.sp_raster = QtWidgets.QDoubleSpinBox()
        self.sp_raster.setRange(0.0, 100.0)
        self.sp_raster.setSingleStep(0.1)
        self.sp_raster.setValue(0.5)
        self.sp_raster.setSuffix(" m")
        self.sp_raster.setToolTip("Rasterweite der Arbeitsebene (0 = kein Raster)")
        self.sp_raster.valueChanged.connect(
            lambda v: self.arbeitsebene_setzen(raster=v))
        g.widget(self.sp_raster)
        self.act_fang = g.schalter("Fang", self.fang_umschalten, True,
                                   "Fang ein- und ausschalten (F3)")
        self.act_fang.setShortcut(QtGui.QKeySequence("F3"))
        self.act_fang.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        # Was gefangen wird, muss man beim Modellieren staendig umstellen -
        # darum je Fangart ein eigener Schalter mit Taste, nicht ein Dialog.
        self.act_fangart = {}
        for art, text, kuerzel, symbol in (
                ("knoten", "auf Knoten", "Shift+F1", "fang_knoten"),
                ("mitte", "auf Kantenmitte", "Shift+F2", "fang_mitte"),
                ("raster", "auf Raster", "Shift+F3", "fang_raster"),
                ("linie", "auf Linien", "Shift+F4", "fang_linie"),
                ("stab", "auf Stäbe", "Shift+F5", "fang_stab"),
                ("flaeche", "auf Flächen", "Shift+F6", "fang_flaeche"),
                ("volumen", "auf Volumen", "Shift+F7", "fang_volumen")):
            a = g.schalter(text, lambda z, k=art: self.fangart_umschalten(k, z),
                           art in self.fang_arten, f"Fang {text} ({kuerzel})",
                           symbol=symbol)
            a.setShortcut(QtGui.QKeySequence(kuerzel))
            a.setShortcutContext(QtCore.Qt.ApplicationShortcut)
            self.act_fangart[art] = a
        g = r.gruppe("Netzgeneratoren")
        g.gross("Stabzug", "╱", lambda: self.maske_zeigen("Netz"),
                hinweis="Stabzug zwischen zwei Punkten")
        g.gross("Platte", "▦", lambda: self.maske_zeigen("Netz"),
                hinweis="Rechteckplatte aus Schalen")
        g.gross("Quader", "▩", lambda: self.maske_zeigen("Netz"),
                hinweis="Quader aus Volumenelementen")

        # -- Struktur ----------------------------------------------------
        r = rb.register("Struktur")
        g = r.gruppe("Elemente")
        g.gross("Stab", "╲", self.maske_stab, "",
                "Zwei Knoten anklicken oder ihre Nummern eintragen")
        g.gross("Schale", "◫", self.maske_schale, "",
                "Drei oder vier Knoten in der Ansicht anklicken")
        g.klein("Elemente löschen", self.delete_elements)
        g = r.gruppe("Eigenschaften")
        g.gross("Querschnitte", "⌶", lambda: self.tabelle_zeigen("Querschnitte"),
                hinweis="Querschnitte aus der Profildatenbank")
        g.gross("Werkstoffe", "⬗", lambda: self.tabelle_zeigen("Werkstoffe"),
                hinweis="Werkstoffe und ihre Kennwerte")
        g.klein("Schalendicken", lambda: self.tabelle_zeigen("Dicken"))
        g.klein("Zuweisen an Auswahl…", lambda: self.maske_zeigen("Auswahl"))
        g.klein("Gelenke setzen…", lambda: self.maske_zeigen("Auswahl"))
        g = r.gruppe("Stäbe für Nachweise")
        g.gross("Stäbe", "≣", lambda: self.maske_zeigen("Nachweise"),
                hinweis="Stäbe mit Knick- und Kipplängen")

        # -- Lager / Gelenke / Kontakt -----------------------------------
        r = rb.register("Lager / Kontakt")
        g = r.gruppe("Lager")
        g.gross("Knotenlager", "△", self.maske_lager, "",
                "Knoten wählen, Freiheitsgrade ankreuzen")
        g.klein("Linienlager…", self.line_support_dialog)
        g.klein("Flächenlager…", self.surface_support_dialog)
        g.klein("Nichtlinearität…", self.support_nonlinear_dialog)
        g = r.gruppe("Kontakt")
        g.gross("Kontakt", "⇹", lambda: self.maske_zeigen("Kontakt"),
                hinweis="Einseitiges Lager, Spaltelement, Kontaktpaar")
        g.klein("Kontakt löschen", self.clear_contact)
        g = r.gruppe("Anschlüsse")
        g.gross("Anschluss", "⊞", self.add_joint,
                hinweis="Kopfplatte, Laschenstoß oder Diagonalanschluss am gewählten "
                        "Stabende anlegen. Der Anschluss gehört danach zum Modell und "
                        "wird bei jeder Berechnung nachgewiesen.")
        g.klein("Anschlüsse zeigen", self.show_joints,
                hinweis="Alle Anschlüsse mit ihren Nachweisen im Klartext")
        g.klein("Tabelle Anschlüsse", lambda: self.tabelle_zeigen("Anschlüsse"))
        g.klein("Anschluss löschen", self.delete_joint)

        # -- Lasten ------------------------------------------------------
        r = rb.register("Lasten")
        g = r.gruppe("Lastfälle")
        g.gross("Lastfälle", "≔", lambda: self.maske_zeigen("Lastfälle"),
                hinweis="Lastfälle anlegen und verwalten")
        g.klein("Kombinationen automatisch…", self.auto_combinations)
        g.klein("Ermüdungslast…", self.fatigue_load_dialog)
        g = r.gruppe("Lasten")
        g.gross("Knotenlast", "", self.maske_knotenlast, "",
                "Knoten wählen, Kräfte und Momente eintragen", symbol="knotenlast")
        g.gross("Linienlast", "", self.maske_linienlast, "",
                "Streckenlast auf gewählte Stäbe oder Linien: gleichmäßig, "
                "trapezförmig oder abschnittsweise (von/bis)", symbol="linienlast")
        g.gross("Flächenlast", "", self.maske_flaechenlast, "",
                "Flächenlast auf gewählte Flächen oder Volumen: gleichmäßig oder "
                "linear veränderlich, senkrecht oder in einer Richtung",
                symbol="flaechenlast")
        g.gross("Temperatur", "", self.maske_temperaturlast, "",
                "Temperaturänderung auf gewählte Stäbe, Flächen oder Volumen",
                symbol="temperatur")
        g.gross("Zwangsverformung", "", self.maske_zwangsverformung, "",
                "Vorgegebene Verschiebung oder Verdrehung an gewählten gelagerten "
                "Knoten (Setzung)", symbol="zwang")
        g = r.gruppe("Weitere")
        g.klein("Eigengewicht", lambda: self.maske_zeigen("Lager/Lasten"),
                hinweis="Eigengewicht im aktiven Lastfall ein- und ausschalten")
        g.klein("Stablast auf Elemente", lambda: self.maske_zeigen("Lager/Lasten"),
                hinweis="Streckenlast unmittelbar auf Stabelemente (Elementnummern)")
        g.klein("Tabelle Lasten", lambda: self.tabelle_zeigen("Lasten"),
                hinweis="Alle Lasten des Modells unten in der Tabelle")

        # -- Netz --------------------------------------------------------
        r = rb.register("Netz")
        g = r.gruppe("Netz")
        g.gross("Netz erzeugen", "⬢", lambda: self.maske_zeigen("Netz"),
                hinweis="Netzgeneratoren und Elementerzeugung")
        g.klein("Netz löschen", self.clear_mesh)

        # -- Berechnung --------------------------------------------------
        r = rb.register("Berechnung")
        g = r.gruppe("Rechnen")
        g.widget(self._ribbon_knopf(self.act_rechnen, "▶", "start"))
        g.klein("Nur aktiver Lastfall", lambda: self.do_solve("case"))
        g.klein("Eigenschwingungen", lambda: self.do_solve("modal"))
        g.klein("Knicken", lambda: self.do_solve("buckling"))
        g = r.gruppe("Stellungen")
        g.gross("Alle Stellungen", "⟳", self.stellungen_rechnen,
                hinweis="Jede Stellung rechnen und die Umhüllende bilden")
        g.klein("DIN 19704: Kombinationen", self.din19704_bilden)
        g = r.gruppe("Einstellungen")
        g.gross("Einstellungen", "⚙", lambda: self.maske_zeigen("Berechnung"),
                hinweis="Analyseart, Prozesse, Rechnerfarm")
        g.klein("Bedienung im Browser…", self.start_web_server)

        # -- Nachweise ---------------------------------------------------
        r = rb.register("Nachweise")
        g = r.gruppe("Führen")
        g.gross("Nachweise EC3", "✓", self.do_design,
                hinweis="Querschnitt und Stabilität nach EN 1993-1-1")
        g.gross("Ermüdung", "∿", self.do_fatigue,
                hinweis="Nachweis nach EN 1993-1-9")
        g = r.gruppe("Einstellungen")
        g.gross("Konfiguration", "⚙", self.design_settings,
                hinweis="Teilsicherheitsbeiwerte und Nachweisstellen")
        g.klein("Stäbe und Knicklängen…", lambda: self.maske_zeigen("Nachweise"))

        # -- Ergebnisse --------------------------------------------------
        g = r.gruppe("Verformung (GZG)")
        g.gross("Verformung", "↧", self.add_verformungsgrenze,
                hinweis="Grenzwert der Verformung festlegen: Durchbiegung eines Stabes, "
                        "Verschiebung eines Knotens oder zweier Knoten gegeneinander")
        g.klein("Tabelle Verformungen", lambda: self.tabelle_zeigen("Verformungen"))
        g.klein("Grenze ändern…", self.edit_verformungsgrenze)
        g.klein("Grenze löschen", self.delete_verformungsgrenze)
        g = r.gruppe("Beulen (EC3-1-5)")
        g.gross("Beulfeld", "▦", self.add_beulfeld,
                hinweis="Die gewählten Flächenelemente zu einem Beulfeld "
                        "zusammenfassen und nach Abschnitt 10 nachweisen")
        g.klein("Tabelle Beulfelder", lambda: self.tabelle_zeigen("Beulfelder"))
        g.klein("Beulfeld ändern…", self.edit_beulfeld)
        g.klein("Beulfeld löschen", self.delete_beulfeld)
        g.gross("Volumen", "◧", self.add_volumenbereich,
                hinweis="Die gewählten Volumenelemente zu einem Bereich für den "
                        "Spannungsnachweis zusammenfassen (6.2.1(5))")
        g.klein("Tabelle Volumen", lambda: self.tabelle_zeigen("Volumen"))
        g.klein("Volumenbereich ändern…", self.edit_volumenbereich)
        g.klein("Volumenbereich löschen", self.delete_volumenbereich)
        g.gross("Lasteinleitung", "↡", self.add_lasteinleitung,
                hinweis="Beulnachweis des Stegs unter einer örtlich eingeleiteten "
                        "Querkraft (Abschnitt 6)")
        g.klein("Tabelle Lasteinleitung", lambda: self.tabelle_zeigen("Lasteinleitung"))

        r = rb.register("Ergebnisse")
        g = r.gruppe("Auswahl")
        g.gross("Ergebnisse", "∿", lambda: self.maske_zeigen("Ergebnisse"),
                hinweis="Ergebnis, Färbung, Verlauf und Überhöhung wählen")
        self.act_kennwerte = g.schalter(
            "Kennwerte im Bild", lambda _z: self.redraw(), True,
            "Größte Ausnutzung, kleinste und größte Verformung und "
            "Schnittgrößen als Text in der Ansicht – sie kommen so auch in "
            "den Bericht")
        g = r.gruppe("Tabellen")
        for name in ("Stabkräfte", "Auflagerkräfte", "Umhüllende",
                     "Nachweise EC3", "Ermüdung", "Kontakt"):
            g.klein(name, lambda n=name: self.tabelle_zeigen(n),
                    hinweis=f"Tabelle {name} unten zeigen")
        g = r.gruppe("Tabelle ausgeben")
        g.gross("Excel", "▦", lambda: self.tabelle_ausgeben("xlsx"),
                hinweis="Die Tabelle, die unten vorn liegt, als xlsx speichern "
                        "(nur die gefilterten Zeilen)")
        g.klein("CSV…", lambda: self.tabelle_ausgeben("csv"),
                hinweis="Als CSV speichern (Semikolon, deutsches Dezimalkomma)")
        g.klein("In die Zwischenablage", lambda: self.tabelle_ausgeben("clip"),
                "Ctrl+Shift+C", "Die sichtbaren Zeilen kopieren")
        g.klein("Filter leeren", self.tabelle_filter_leeren,
                hinweis="Alle Kopfzeilenfilter der vorderen Tabelle löschen")

        # -- Bericht -----------------------------------------------------
        r = rb.register("Bericht")
        g = r.gruppe("Bericht")
        g.gross("Bericht", "≡", self.make_report, "Ctrl+R",
                "Statischen Bericht als HTML oder PDF erzeugen")
        g = r.gruppe("Ergebnisse übernehmen")
        g.gross("Ansicht übernehmen", "⎘", self.ansicht_in_bericht, "Ctrl+B",
                "Die Ansicht, so wie sie gerade steht, als Bild in den Bericht "
                "aufnehmen – samt Ergebnis, Färbung und Verlauf")
        g.klein("Übernommene Bilder", lambda: self.tabelle_zeigen("Bericht"),
                hinweis="Die Tabelle „Bericht“ unten zeigen")
        g.klein("Alle Bilder verwerfen", self.bericht_leeren)

        # -- Ansicht -----------------------------------------------------
        r = rb.register("Ansicht")
        g = r.gruppe("Blickrichtung")
        g.gross("Isometrisch", "◲", lambda: self.blickrichtung("iso"), symbol="iso")
        g.klein("XY (Draufsicht)", lambda: self.blickrichtung("+z"), symbol="wuerfel")
        g.klein("XZ (Ansicht)", lambda: self.blickrichtung("-y"), symbol="wuerfel")
        g.klein("YZ (Seitenansicht)", lambda: self.blickrichtung("+x"), symbol="wuerfel")
        g.klein("Rückseite (180°)", lambda: self.blickrichtung("kehren"),
                hinweis="Die laufende Ansicht umkehren – zeigt die Rückseite",
                symbol="kehren")
        g.klein("Zoom alles", self.zoom_alles, symbol="zoom")
        g = r.gruppe("Darstellung")
        # Die vier Darstellungsarten liegen als eigene Knoepfe nebeneinander und
        # auf Strg+1..Strg+4 - Umschalten soll ein Griff sein, kein Klickweg
        # durch ein Auswahlfeld. (F5 ist „Berechnen", F9 das FE-Netz.)
        self.act_darstellung = {}
        gruppe = QtGui.QActionGroup(self)
        gruppe.setExclusive(True)
        for i, (name, (zeichen, hinweis)) in enumerate(vp.DARSTELLUNGEN.items()):
            a = g.gross(name, zeichen,
                        lambda n=name: self.darstellung_setzen(n),
                        f"Ctrl+{1 + i}", hinweis)
            a.setCheckable(True)
            a.setChecked(name == self.darstellung)
            gruppe.addAction(a)
            self.act_darstellung[name] = a
        g = r.gruppe("Anzeigen")
        self.act_edges = g.schalter("FE-Netz", lambda z: self.redraw(), True,
                                    "Die Elementkanten des Netzes zeigen (F9)")
        self.act_edges.setShortcut(QtGui.QKeySequence("F9"))
        self.act_edges.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        self.act_knoten = g.schalter("Knoten", lambda z: self.redraw(), True,
                                     "Die gesetzten Knoten als Punkte zeigen",
                                     symbol="knoten")
        self.act_linien = g.schalter("Linien", lambda z: self.redraw(), True,
                                     "Die Linien des Modells zeigen (Geometrie, "
                                     "keine Elemente)", symbol="linien")
        self.act_staebe = g.schalter("Stäbe", lambda z: self.redraw(), True,
                                     "Stabelemente zeigen - bei Voll und Transparent "
                                     "mit ihrer Querschnittskontur", symbol="staebe")
        self.act_flaechen = g.schalter("Flächen", lambda z: self.redraw(), True,
                                       "Flächen und Schalenelemente zeigen",
                                       symbol="flaechen")
        self.act_volumen = g.schalter("Volumen", lambda z: self.redraw(), True,
                                      "Volumenkörper und Volumenelemente zeigen",
                                      symbol="volumen")
        self.act_nodes = g.schalter("Knotennummern", lambda z: self.redraw(),
                                    symbol="nummern")
        self.act_elems = g.schalter("Elementnummern", lambda z: self.redraw(),
                                    symbol="nummern")
        self.act_loads = g.schalter("Lasten", lambda z: self.redraw(), True,
                                    symbol="lasten")
        self.act_members = g.schalter("Stäbe farbig", lambda z: self.redraw(),
                                      symbol="farbig")
        g = r.gruppe("Sicht")
        # Was man nicht sieht, stoert nicht: die Auswahl allein zeigen, die
        # Auswahl ausblenden, einen Schritt zurueck, alles wieder her.
        self.act_nur_auswahl = g.klein("Nur Auswahl zeigen", self.nur_auswahl_zeigen,
                                       hinweis="Alles ausser der Auswahl ausblenden",
                                       symbol="sicht_nur_auswahl")
        self.act_auswahl_weg_sicht = g.klein("Auswahl ausblenden", self.auswahl_ausblenden,
                                             hinweis="Die ausgewählten Objekte ausblenden",
                                             symbol="sicht_ausblenden")
        self.act_sicht_zurueck = g.klein("Vorherige Sicht", self.sicht_zurueck,
                                         hinweis="Den letzten Ausblendeschritt zurücknehmen",
                                         symbol="sicht_zurueck")
        self.act_alles_zeigen = g.klein("Alles zeigen", self.alles_zeigen,
                                        hinweis="Alle ausgeblendeten Objekte wieder zeigen",
                                        symbol="sicht_alles")
        g = r.gruppe("Symbole")
        self.sl_lager = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_lager.setRange(2, 60)
        self.sl_lager.setValue(int(round(self.lagergroesse * 10)))
        self.sl_lager.setFixedWidth(110)
        self.sl_lager.setToolTip("Größe aller Lagersymbole")
        self.sl_lager.valueChanged.connect(self._lagergroesse_geschoben)
        g.widget(QtWidgets.QLabel("Lager"))
        g.widget(self.sl_lager)
        g.klein("Lagergröße zurücksetzen", self.lagergroesse_zuruecksetzen,
                hinweis="Alle Lagersymbole auf die Grundgröße")

        # -- Extras ------------------------------------------------------
        r = rb.register("Extras")
        g = r.gruppe("Handbücher")
        g.gross("Handbuch", "❓", lambda: self.open_doc("Benutzerhandbuch.md"))
        g.klein("Theoriehandbuch", lambda: self.open_doc("Theoriehandbuch.md"))
        g.klein("Schnittstellen", lambda: self.open_doc("Schnittstellen.md"))
        g.klein("Rechnerfarm", lambda: self.open_doc("Rechnerfarm.md"))
        g = r.gruppe("Programm")
        g.gross("Info", "ⓘ", self.about,
                hinweis="Fassung, Build und Gültigkeitsbereich")
        g.klein("Nach Update suchen…", self.check_update)

        rb.schnell(self.act_speichern, self.act_undo, self.act_redo,
                   self.act_rechnen, self.act_auswahl_weg)
        self._undo_knoepfe()
        self.setMenuWidget(dsg.kopfhalter(self, self.kopf, rb))

    @staticmethod
    def _ribbon_knopf(aktion, zeichen: str, rolle: str = ""):
        """Denselben Befehl ein zweites Mal als Knopf zeigen (kein neuer Befehl)."""
        from . import symbole as sym
        b = QtWidgets.QToolButton()
        if aktion.icon().isNull():
            aktion.setIcon(sym.fuer_befehl(aktion.text(), zeichen))
        b.setDefaultAction(aktion)
        b.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        b.setIconSize(QtCore.QSize(rib.SYMBOL_GROSS, rib.SYMBOL_GROSS))
        b.setText(aktion.text())
        b.setObjectName("ribbongross")
        if rolle:
            b.setProperty("rolle", rolle)
        b.setMinimumWidth(58)
        b.setFixedHeight(rib.INHALT_HOEHE)
        return b

    # ------------------------------------------------------------------
    def _build_panels(self):
        dock = QtWidgets.QDockWidget("Eingaben", self)
        dock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea)
        dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.addTab(self._scroll(self._tab_model()), "Modell")
        self.tabs.addTab(self._scroll(self._tab_mesh()), "Netz")
        self.tabs.addTab(self._scroll(self._tab_bc()), "Lager/Lasten")
        self.tabs.addTab(self._scroll(self._tab_cases()), "Lastfälle")
        self.tabs.addTab(self._scroll(self._tab_stellungen()), "Stellungen")
        self.tabs.addTab(self._scroll(self._tab_contact()), "Kontakt")
        self.tabs.addTab(self._scroll(self._tab_design()), "Nachweise")
        self.tabs.addTab(self._scroll(self._tab_solve()), "Berechnung")
        self.tabs.addTab(self._scroll(self._tab_results()), "Ergebnisse")
        self.tabs.setMinimumWidth(470)
        # Die Registerleiste entfaellt: sichtbar ist immer genau eine Maske,
        # gewaehlt ueber den Befehl im Ribbon. Der Docktitel nennt sie.
        self.tabs.tabBar().setVisible(False)
        # Darueber der Platz fuer die Erzeuge-Maske (Knoten, Linie, Fläche …).
        # Sie schwebt nicht mehr ueber der Ansicht, sondern steht hier - dort,
        # wo alle Einstellungen stehen.
        halter = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(halter)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self.tabs, 1)
        self.maskenplatz = lay
        self.maskenrand.setze_ziel(lay)
        dock.setWidget(halter)
        self.eingaben_dock = dock
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)

    # ------------------------------------------------------------------
    # Erscheinungsbild: Kopfzeile, Werkzeugleiste, Modellbaum
    # ------------------------------------------------------------------
    def register_zeigen(self, name: str) -> bool:
        """Ein Register des Ribbons nach vorn holen."""
        return self.ribbon.zeigen(name) if hasattr(self, "ribbon") else False

    def maske_zeigen(self, name: str) -> bool:
        """Die Eingabemaske mit diesem Namen rechts zeigen.

        Es ist immer nur **eine** Maske sichtbar; die Registerleiste des
        Bestands entfaellt damit (Vorgabe Kap. 16.1 Nr. 1).
        """
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == name:
                self.tabs.setCurrentIndex(i)
                if hasattr(self, "eingaben_dock"):
                    self.eingaben_dock.setWindowTitle(name)
                    self.eingaben_dock.show()
                    self.eingaben_dock.raise_()
                return True
        return False

    def maske_erzeugen(self, maske):
        """Eine Erzeuge-Maske im rechten Bereich zeigen und ihn aufklappen."""
        self.maskenrand.zeigen(maske)
        if hasattr(self, "eingaben_dock"):
            self.eingaben_dock.setWindowTitle(getattr(maske, "titel", "") or "Erzeugen")
            self.eingaben_dock.show()
            self.eingaben_dock.raise_()
        return maske

    def _build_baum(self):
        """Modellbaum links: was im Modell steckt."""
        dock = QtWidgets.QDockWidget("Modellbaum", self)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea)
        dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        self.baum = dsg.Modellbaum(dock)
        self.baum.angeklickt.connect(self._baum_geklickt)
        self.baum.bearbeiten.connect(self._baum_bearbeiten)
        dock.setWidget(self.baum)
        # Der Baum traegt jetzt Namen und Zusatzangabe nebeneinander (Knoten mit
        # Koordinaten, Lager mit Wirkung); unter 290 px bleibt vom Namen nichts.
        dock.setMinimumWidth(290)
        dock.setMaximumWidth(420)
        self.baum_dock = dock
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)

    #: Zweig des Modellbaums -> Register der Eingaben
    #: Zweig des Modellbaums -> Register der Eingaben rechts.
    #: Es gelten nur die Register, die es wirklich gibt: Modell, Netz,
    #: Lager/Lasten, Lastfaelle, Stellungen, Kontakt, Nachweise, Berechnung,
    #: Ergebnisse.
    BAUM_ZIEL = {
        "modell": "Modell",
        "querschnitte": "Modell", "querschnitt": "Modell",
        "werkstoffe": "Modell", "werkstoff": "Modell",
        "dicken": "Modell", "dicke": "Modell",
        "elemente": "Netz", "stabelemente": "Netz", "flaechen": "Netz",
        "volumen": "Netz",
        "lager": "Lager/Lasten", "lager_einzeln": "Lager/Lasten",
        "linienlager": "Lager/Lasten", "linienlager_einzeln": "Lager/Lasten",
        "flaechenlager": "Lager/Lasten", "flaechenlager_einzeln": "Lager/Lasten",
        "lasten": "Lager/Lasten", "last": "Lager/Lasten",
        "lastfaelle": "Lastfälle", "lastfall": "Lastfälle",
        "kombinationen": "Lastfälle", "kombination": "Lastfälle",
        "kontakt": "Kontakt",
        "staebe": "Nachweise", "stab": "Nachweise",
        "stellungen": "Stellungen", "stellung": "Stellungen",
        "ergebnisse": "Ergebnisse", "ergebnisgruppe": "Ergebnisse",
        "ergebnis": "Ergebnisse", "nachweis": "Ergebnisse",
        "bericht": "Ergebnisse", "berichtseintrag": "Ergebnisse",
    }

    #: Zweige, zu denen es kein festes Register gibt: sie oeffnen die
    #: Erzeuge-Maske, die dazu gehoert - ebenfalls rechts.
    BAUM_MASKE = {
        "knoten": "maske_knoten",
        "linien": "maske_linie", "linie": "maske_linie",
        "gelenke": "add_hinge", "gelenk": "add_hinge",
    }

    #: Zweige des Modellbaums, die eine Tabelle unten zeigen statt eine Maske
    BAUM_TABELLE = {"querschnitte": "Querschnitte", "werkstoffe": "Werkstoffe",
                    "querschnitt": "Querschnitte", "werkstoff": "Werkstoffe",
                    "dicken": "Dicken", "dicke": "Dicken",
                    "knoten": "Knoten", "elemente": "Elemente",
                    "stabelemente": "Elemente", "flaechen": "Elemente",
                    "volumen": "Elemente", "linien": "Linien", "linie": "Linien",
                    "lager": "Lager", "lager_einzeln": "Lager",
                    "linienlager": "Lager", "linienlager_einzeln": "Lager",
                    "flaechenlager": "Lager", "flaechenlager_einzeln": "Lager",
                    "gelenke": "Gelenke", "gelenk": "Gelenke",
                    "lasten": "Lasten", "last": "Lasten",
                    "geoflaechen": "Flächen", "geoflaeche": "Flächen",
                    "geokoerper": "Volumenkörper",
                    "geokoerper_einzeln": "Volumenkörper",
                    "berichtseintrag": "Bericht", "bericht": "Bericht",
                    "kontaktbedingungen": "Kontaktbedingungen",
                    "kontaktbedingung": "Kontaktbedingungen",
                    "anschluesse": "Anschlüsse", "anschluss": "Anschlüsse",
                    "verformungen": "Verformungen", "verformung": "Verformungen",
                    "beulfelder": "Beulfelder", "beulfeld": "Beulfelder",
                    "lasteinleitung": "Lasteinleitung",
                    "lasteinleitung_einzeln": "Lasteinleitung",
                    "volumenbereiche": "Volumen", "volumenbereich": "Volumen"}

    #: Elementarten je Zweig - fuer die Auswahl im Viewport
    BAUM_ELEMENTARTEN = {"stabelemente": ("beam", "truss"),
                         "flaechen": ("shell3", "shell4"),
                         "volumen": ("tet4", "tet10", "hex8")}

    def _baum_geklickt(self, art: str, name: str):
        if art == "stellung_neu":
            return self.neue_stellung()
        if art == "bericht_neu":
            return self.ansicht_in_bericht()
        if art == "ergebnis":
            return self.ergebnis_zeigen(name)
        if art in ("ergebnisse", "ergebnisgruppe"):
            return self.maske_zeigen("Ergebnisse")
        if art == "berichtseintrag":
            return self.tabelle_zeigen("Bericht")
        if art == "last" and name in self.model.load_cases:
            self.cb_lastfilter.setCurrentText(name)
        elif art == "lasten":
            self.cb_lastfilter.setCurrentText("(alle)")
        if art == "anschluss_neu":
            return self.add_joint()
        if art == "verformung_neu":
            return self.add_verformungsgrenze()
        if art == "stellung":
            self._stellung_gewaehlt(name.split("·", 1)[-1].strip())
        if art == "anschluss":
            self._anschluss_gewaehlt(name)
        if art == "verformung":
            self.tabelle_zeigen("Verformungen")
            self.tbl_gzg.markieren([name])
            self._tabelle_verformung(name)
        # Ein Zweig, der ein Objekt meint, zeigt es auch in der Ansicht.
        self._baum_auswaehlen(art, name)
        # Links waehlen, rechts einstellen: der Zweig holt seine Tabelle nach
        # vorn UND oeffnet die Maske, die dazu gehoert. Frueher war es
        # entweder-oder; wer eine Fläche anklickte, sah die Tabelle, aber die
        # Einstellungen musste er sich selbst suchen.
        tab = self.BAUM_TABELLE.get(art)
        if tab:
            self.tabelle_zeigen(tab)
        ziel = self.BAUM_ZIEL.get(art)
        if ziel:
            self.maske_zeigen(ziel)
            return
        befehl = self.BAUM_MASKE.get(art)
        if befehl and hasattr(self, befehl) and art not in ("gelenk", "gelenke"):
            getattr(self, befehl)()

    def _baum_auswaehlen(self, art: str, name: str):
        """Was im Baum angeklickt wurde, im Viewport hervorheben."""
        m = self.model
        knoten: list[int] = []
        if art == "knoten" and name.isdigit():
            knoten = [int(name)]
        elif art in self.BAUM_ELEMENTARTEN:
            typen = (name,) if name in self.BAUM_ELEMENTARTEN[art] \
                else self.BAUM_ELEMENTARTEN[art]
            for e in m.elements:
                if e.typ in typen:
                    knoten += [int(x) for x in e.nodes]
        elif art == "linie" and name in m.lines:
            knoten = [int(x) for x in m.lines[name].nodes]
        elif art == "geoflaeche" and name in m.flaechen:
            f = m.flaechen[name]
            knoten = list(f.randknoten(m)) or self._linienknoten(f.linien)
            for i in (f.elemente or []):
                knoten += [int(x) for x in m.elements[i].nodes]
            if name not in self.sel_flaechen:
                self.sel_flaechen = [name]
        elif art == "geokoerper_einzeln" and name in m.koerper:
            k = m.koerper[name]
            for fn in k.flaechen:
                f = m.flaechen.get(fn)
                if f is not None:
                    knoten += list(f.randknoten(m)) or self._linienknoten(f.linien)
            for i in (k.elemente or []):
                knoten += [int(x) for x in m.elements[i].nodes]
            if name not in self.sel_koerper:
                self.sel_koerper = [name]
        elif art == "lager_einzeln" and name.isdigit() \
                and int(name) < len(m.supports):
            knoten = [int(m.supports[int(name)].node)]
        elif art == "linienlager_einzeln" and name.isdigit() \
                and int(name) < len(m.line_supports):
            knoten = [int(x) for x in m.line_supports[int(name)].nodes]
        elif art == "flaechenlager_einzeln" and name.isdigit() \
                and int(name) < len(m.surface_supports):
            knoten = [int(x) for x in m.surface_supports[int(name)].nodes]
        elif art == "stab" and name in m.members:
            for i in m.members[name].elements:
                knoten += [int(x) for x in m.elements[i].nodes]
        else:
            return
        knoten = [n for n in dict.fromkeys(knoten) if 0 <= n < m.nn]
        self.selection = np.array(knoten, dtype=int)
        # Was im Baum angeklickt wurde, leuchtet in der Ansicht auf: die
        # Elemente des Objekts bekommen eine eigene Hervorhebung, nicht nur
        # die Knotenpunkte.
        self.leuchtet = self._elemente_zu(art, name)
        self.lbl_sel.setText(f"{len(knoten)} Knoten ausgewählt (Modellbaum)")
        self.redraw()

    def _linienknoten(self, linien) -> list[int]:
        """Die Knoten der genannten Linien - Rueckfall, wenn der Rand nicht
        als Polygon schliesst (Kreis aus zwei Halbboegen)."""
        m = self.model
        return [int(n) for nm in linien if nm in m.lines
                for n in m.lines[nm].nodes]

    def _elemente_zu(self, art: str, name: str) -> list[int]:
        """Die Elemente, die zu einem Zweig des Modellbaums gehoeren."""
        m = self.model
        if art in self.BAUM_ELEMENTARTEN:
            typen = (name,) if name in self.BAUM_ELEMENTARTEN[art] \
                else self.BAUM_ELEMENTARTEN[art]
            return [i for i, e in enumerate(m.elements) if e.typ in typen]
        if art == "geoflaeche" and name in m.flaechen:
            return list(m.flaechen[name].elemente or [])
        if art == "geokoerper_einzeln" and name in m.koerper:
            return list(m.koerper[name].elemente or [])
        if art == "stab" and name in m.members:
            return list(m.members[name].elements or [])
        if art == "linie" and name in m.lines:
            kn = set(int(x) for x in m.lines[name].nodes)
            return [i for i, e in enumerate(m.elements)
                    if e.typ in ("beam", "truss") and kn.issuperset(e.nodes)]
        return []

    #: Zweig des Modellbaums -> Befehl, den der Doppelklick ausfuehrt
    BAUM_NEU = {"querschnitte": "add_section", "werkstoffe": "add_material",
                "dicken": "add_shell_prop", "lastfaelle": "add_case",
                "kombinationen": "add_combination", "staebe": "auto_members",
                "anschluesse": "add_joint", "verformungen": "add_verformungsgrenze",
                "beulfelder": "add_beulfeld", "volumenbereiche": "add_volumenbereich",
                "lasteinleitung": "add_lasteinleitung", "gelenke": "add_hinge",
                "linien": "add_linie", "lager": "add_support_dialog",
                "geoflaechen": "add_flaeche_aus_auswahl",
                "geokoerper": "add_koerper_aus_auswahl",
                "bericht": "ansicht_in_bericht"}

    def _baum_bearbeiten(self, art: str, name: str):
        """Doppelklick im Modellbaum: das Objekt oeffnen, nicht nur zeigen.

        Ein Zweig, der eine Art meint (etwa „Werkstoffe"), legt ein neues an;
        ein Zweig, der ein einzelnes Objekt meint, oeffnet dieses.
        """
        try:
            if art == "knoten" and name.isdigit():
                return self.knoten_bearbeiten(int(name))
            if art == "linie":
                return self.linie_bearbeiten(name)
            if art == "geoflaeche":
                return self.flaeche_bearbeiten(name)
            if art == "geokoerper_einzeln":
                return self.koerper_bearbeiten(name)
            if art == "ergebnis":
                self.ergebnis_zeigen(name)
                return self.ansicht_in_bericht()
            if art == "berichtseintrag":
                return self.berichtseintrag_bearbeiten(name)
            if art == "querschnitt":
                return self.querschnitt_bearbeiten(name)
            if art == "werkstoff":
                return self.werkstoff_bearbeiten(name)
            if art == "dicke":
                return self.dicke_bearbeiten(name)
            if art in ("lager_einzeln", "linienlager_einzeln", "flaechenlager_einzeln"):
                return self.lagerobjekt_bearbeiten(art, name)
            if art == "gelenk":
                return self.gelenk_bearbeiten(name)
            if art == "lastfall":
                return self.lastfall_bearbeiten(name)
            if art == "kombination":
                return self.kombination_bearbeiten(name)
            if art == "stab":
                self._tabelle_stab(name)
                return self.edit_member()
            if art == "anschluss":
                return self._anschluss_gewaehlt(name)
            if art == "verformung":
                self._tabelle_verformung(name)
                return self.edit_verformungsgrenze()
            if art == "beulfeld":
                self._tabelle_beulfeld(name)
                return self.edit_beulfeld()
            if art == "volumenbereich":
                self._tabelle_volumen(name)
                return self.edit_volumenbereich()
            if art == "lasteinleitung_einzeln":
                self._tabelle_lasteinleitung(name)
                return self.edit_lasteinleitung()
            befehl = self.BAUM_NEU.get(art)
            if befehl and hasattr(self, befehl):
                return getattr(self, befehl)()
        except Exception as ex:      # noqa: BLE001 - ein Doppelklick darf nie stuerzen
            self.error(f"{art}: {ex}")
        # Kein eigener Weg: wie ein einfacher Klick behandeln
        self._baum_geklickt(art, name)

    # ---- Bearbeiten einzelner Modellobjekte ---------------------------
    def knoten_bearbeiten(self, i: int):
        if not (0 <= i < self.model.nn):
            return
        d = dg.KnotenDialog(self, self.model.nodes[i], i)
        if d.exec():
            self.merken(f"Knoten {i} verschoben")
            self.model.nodes[i] = np.asarray(d.werte(), float)
            self.refresh_all()

    def add_linie(self):
        """Neue Linie aus der aktuellen Auswahl (oder leer)."""
        from ..model import Line
        vorlage = Line(self._freier_name("L1", self.model.lines),
                       [int(n) for n in self.selection])
        d = dg.LinienDialog(self, vorlage, self.model.nn)
        if d.exec():
            w = d.werte()
            if len(w["nodes"]) < 2:
                return self.error("Eine Linie braucht mindestens zwei Knoten.")
            self.merken(f"Linie {w['name']}")
            self.model.add_line(w["name"], w["nodes"], w["typ"])
            self.model.lines[w["name"]].comment = w["comment"]
            self.refresh_all()

    def linie_bearbeiten(self, name: str):
        ln = self.model.lines.get(name)
        if ln is None:
            return self.add_linie()
        d = dg.LinienDialog(self, ln, self.model.nn)
        if not d.exec():
            return
        w = d.werte()
        if len(w["nodes"]) < 2:
            return self.error("Eine Linie braucht mindestens zwei Knoten.")
        self.merken(f"Linie {name}")
        del self.model.lines[name]
        self.model.add_line(w["name"], w["nodes"], w["typ"])
        self.model.lines[w["name"]].comment = w["comment"]
        self.refresh_all()

    # ---- Ergebnisse aus dem Modellbaum -----------------------------------
    #: Schluesselwort im Baum -> Tabelle unten
    NACHWEIS_TABELLE = {"design": "Nachweise EC3", "fatigue": "Ermüdung",
                        "gzg": "Verformungen", "beulen": "Beulfelder",
                        "lasteinleitung": "Lasteinleitung", "volumen": "Volumen",
                        "joints": "Anschlüsse"}

    def ergebnis_zeigen(self, schluessel: str):
        """Ein Ergebnis aus dem Baum in der Ansicht einstellen."""
        art, _, wert = (schluessel or "").partition(":")
        if art == "schnittgroesse":
            i = self.cb_diagram.findText(wert)
            if i >= 0:
                self.cb_diagram.setCurrentIndex(i)     # zeichnet neu
                self.info(f"Schnittgrößenverlauf {wert}")
            return
        if art == "nachweis":
            tabelle = self.NACHWEIS_TABELLE.get(wert)
            if tabelle and self.tabelle_zeigen(tabelle):
                return
            return self.show_design() if hasattr(self, "show_design") else None
        for i in range(self.cb_result.count()):
            d = self.cb_result.itemData(i)
            if not d:
                continue
            if art == "modal" or art == "buckling":
                break
            if d[0] == art and str(d[1]) == wert:
                self.cb_result.setCurrentIndex(i)
                self.maske_zeigen("Ergebnisse")
                return
        if art in ("modal", "buckling") and self.cb_mode.count():
            self.cb_mode.setCurrentIndex(min(int(wert or 0), self.cb_mode.count() - 1))
            self.maske_zeigen("Ergebnisse")
            return
        self.info(f"Ergebnis „{schluessel}“ ist nicht (mehr) vorhanden - neu rechnen")

    def _aktuelle_quelle(self) -> str:
        """Der Schluessel des Ergebnisses, das gerade in der Ansicht steht."""
        d = self.cb_result.currentData()
        if d:
            art, wert = d[0], d[1]
            if art in ("env", "combo", "case"):
                return f"{art}:{wert}"
        r = self.current_result()
        if r is not None and getattr(r, "modes", None) is not None:
            return f"modal:{self.cb_mode.currentIndex()}"
        if r is not None and getattr(r, "buckling_modes", None) is not None:
            return f"buckling:{self.cb_mode.currentIndex()}"
        return "modell:"

    def ansicht_in_bericht(self):
        """Die Ansicht so, wie sie gerade steht, in den Bericht uebernehmen.

        Aufgenommen wird das Bild **und** die Einstellung, aus der es
        entstanden ist - Ergebnis, Faerbung, Verlauf, Ueberhoehung. Im Bericht
        steht damit nicht nur eine Grafik, sondern auch, was sie zeigt.
        """
        import base64
        import tempfile
        import os as _os
        try:
            fd, tmp = tempfile.mkstemp(suffix=".png")
            _os.close(fd)
            self.plotter.screenshot(tmp)
            with open(tmp, "rb") as fh:
                bild = base64.b64encode(fh.read()).decode("ascii")
            _os.unlink(tmp)
        except Exception as ex:      # noqa: BLE001
            return self.error(f"Die Ansicht ließ sich nicht aufnehmen: {ex}")
        from ..model import Berichtseintrag
        quelle = self._aktuelle_quelle()
        e = Berichtseintrag(
            name=f"Bild {len(self.model.bericht) + 1}", quelle=quelle,
            feld=self.cb_field.currentText(), verlauf=self.cb_diagram.currentText(),
            ueberhoehung=float(self.sl_scale.value()), bild=bild)
        e.beschriftung = e.bezug()
        self.merken("Ansicht in den Bericht übernommen")
        self.model.bericht.append(e)
        self.refresh_all()
        self.tabelle_zeigen("Bericht")
        self.info(f"„{e.name}“ in den Bericht übernommen ({e.bezug()})")

    def berichtseintrag_bearbeiten(self, nummer: str):
        """Beschriftung und Bemerkung eines Berichtsbildes."""
        try:
            i = int(nummer)
        except (TypeError, ValueError):
            return
        if not (0 <= i < len(self.model.bericht)):
            return
        e = self.model.bericht[i]
        d = dg.BerichtseintragDialog(self, e)
        if d.exec():
            self.merken(f"Berichtsbild {e.name}")
            d.apply(e)
            self.refresh_all()

    def bericht_leeren(self):
        if not self.model.bericht:
            return self.info("Es wurde noch kein Bild übernommen")
        if QtWidgets.QMessageBox.question(
                self, "Bilder verwerfen",
                f"{len(self.model.bericht)} übernommene Bilder löschen?") \
                != QtWidgets.QMessageBox.Yes:
            return
        self.merken("Berichtsbilder verworfen")
        self.model.bericht.clear()
        self.refresh_all()

    def berichtseintrag_loeschen(self):
        i = self._zeilenzahl(self.tbl_bericht)
        if not (0 <= i < len(self.model.bericht)):
            return self.error("Zuerst eine Zeile wählen")
        self.merken(f"Berichtsbild {self.model.bericht[i].name} gelöscht")
        del self.model.bericht[i]
        self.refresh_all()

    def berichtseintrag_schieben(self, richtung: int):
        i = self._zeilenzahl(self.tbl_bericht)
        j = i + richtung
        if not (0 <= i < len(self.model.bericht)) or not (0 <= j < len(self.model.bericht)):
            return
        self.merken("Reihenfolge im Bericht")
        b = self.model.bericht
        b[i], b[j] = b[j], b[i]
        self.refresh_all()
        self.tbl_bericht.view.selectRow(j)

    # ---- Geometriekette: Knoten -> Linien -> Flaechen -> Volumen ---------
    def add_flaeche_aus_auswahl(self):
        """Aus den ausgewaehlten Linien eine Flaeche machen.

        Der Rand muss schliessen; sonst waere die Flaeche nicht bestimmt und
        das Programm sagt das, statt zu raten.
        """
        linien = list(self.sel_linien)
        if len(linien) < 3:
            return self.error("Erst mindestens drei Linien auswählen "
                              "(Auswahl auf „Linie“ stellen und in der Ansicht "
                              "anklicken).")
        name = self._freier_name("F1", self.model.flaechen)
        d = dg.FlaechenDialog(self, self.model, linien=linien, name=name)
        if not d.exec():
            return
        w = d.werte()
        try:
            self.merken(f"Fläche {w['name']}")
            f = self.model.add_flaeche(w["name"], w["linien"], dicke=w["dicke"],
                                       material=w["material"], teilung=w["teilung"],
                                       kommentar=w["kommentar"])
        except (KeyError, ValueError) as ex:
            self.undo()
            return self.error(str(ex))
        if w["vernetzen"]:
            self._vernetzen([f], [])
        self.sel_linien.clear()
        self.refresh_all()

    def flaeche_bearbeiten(self, name: str):
        f = self.model.flaechen.get(name)
        if f is None:
            return self.add_flaeche_aus_auswahl()
        d = dg.FlaechenDialog(self, self.model, flaeche=f)
        if not d.exec():
            return
        w = d.werte()
        self.merken(f"Fläche {name}")
        self._netz_loeschen(f.elemente)
        del self.model.flaechen[name]
        try:
            neu = self.model.add_flaeche(w["name"], w["linien"], dicke=w["dicke"],
                                         material=w["material"], teilung=w["teilung"],
                                         kommentar=w["kommentar"])
        except (KeyError, ValueError) as ex:
            self.undo()
            return self.error(str(ex))
        for k in self.model.koerper.values():
            k.flaechen = [w["name"] if x == name else x for x in k.flaechen]
        if w["vernetzen"]:
            self._vernetzen([neu], [])
        self.refresh_all()

    def add_koerper_aus_auswahl(self):
        """Aus den ausgewaehlten Flaechen einen Volumenkoerper machen."""
        flaechen = list(self.sel_flaechen)
        if len(flaechen) < 4:
            return self.error("Erst mindestens vier Flächen auswählen "
                              "(Auswahl auf „Fläche“ stellen und in der Ansicht "
                              "anklicken).")
        name = self._freier_name("V1", self.model.koerper)
        d = dg.KoerperDialog(self, self.model, flaechen=flaechen, name=name)
        if not d.exec():
            return
        w = d.werte()
        try:
            self.merken(f"Volumen {w['name']}")
            k = self.model.add_koerper(w["name"], w["flaechen"],
                                       material=w["material"], teilung=w["teilung"],
                                       kommentar=w["kommentar"])
        except (KeyError, ValueError) as ex:
            self.undo()
            return self.error(str(ex))
        if w["vernetzen"]:
            self._vernetzen([], [k])
        self.sel_flaechen.clear()
        self.refresh_all()

    def koerper_bearbeiten(self, name: str):
        k = self.model.koerper.get(name)
        if k is None:
            return self.add_koerper_aus_auswahl()
        d = dg.KoerperDialog(self, self.model, koerper=k)
        if not d.exec():
            return
        w = d.werte()
        self.merken(f"Volumen {name}")
        self._netz_loeschen(k.elemente)
        del self.model.koerper[name]
        try:
            neu = self.model.add_koerper(w["name"], w["flaechen"],
                                         material=w["material"], teilung=w["teilung"],
                                         kommentar=w["kommentar"])
        except (KeyError, ValueError) as ex:
            self.undo()
            return self.error(str(ex))
        if w["vernetzen"]:
            self._vernetzen([], [neu])
        self.refresh_all()

    def _netz_loeschen(self, elemente: list):
        """Die Elemente eines Objekts entfernen und alle Verweise nachziehen.

        Elementnummern sind Positionen in einer Liste; loescht man eine, wandern
        alle dahinter. Darum werden hier Stabzuege, Lasten, Bereiche und die
        Netze der anderen Objekte in einem Zug mitgefuehrt.
        """
        weg = sorted({int(e) for e in (elemente or [])}, reverse=True)
        if not weg:
            return
        m = self.model
        wegmenge = set(weg)
        neu_nr = {}
        k = 0
        for i in range(len(m.elements)):
            if i in wegmenge:
                continue
            neu_nr[i] = k
            k += 1
        m.elements = [e for i, e in enumerate(m.elements) if i not in wegmenge]

        def um(liste):
            return [neu_nr[i] for i in (liste or []) if i in neu_nr]

        for mem in m.members.values():
            mem.elements = um(mem.elements)
        for f in m.flaechen.values():
            f.elemente = um(f.elemente)
            # Die Randseiten zeigen auf Element **und** lokale Seite; ohne sie
            # nachzuziehen haenge jede Flaechenlast auf einem Volumen falsch.
            f.randseiten = [[neu_nr[int(e)], int(seite)]
                            for e, seite in (f.randseiten or [])
                            if int(e) in neu_nr]
        for kb in m.koerper.values():
            kb.elemente = um(kb.elemente)
        for vb in m.volumenbereiche.values():
            vb.elemente = um(vb.elemente)
        for lc in m.load_cases.values():
            lc.beam_loads = [l for l in lc.beam_loads if l.elem in neu_nr]
            for l in lc.beam_loads:
                l.elem = neu_nr[l.elem]
            lc.face_loads = [l for l in lc.face_loads if l.elem in neu_nr]
            for l in lc.face_loads:
                l.elem = neu_nr[l.elem]
            lc.temp_loads = [l for l in lc.temp_loads if l.elem in neu_nr]
            for l in lc.temp_loads:
                l.elem = neu_nr[l.elem]

    def _vernetzen(self, flaechen: list, koerper: list) -> int:
        """Flaechen und Koerper vernetzen und das Protokoll fuehren."""
        from .. import fugen
        log = []
        n = 0
        # Was aus Kontaktbedingungen entstanden ist, gehoert zum alten Netz.
        fugen.kontaktfugen_zuruecksetzen(self.model, log)
        for f in flaechen:
            self._netz_loeschen(f.elemente)
            f.elemente = []
            n += len(mesher.mesh_flaeche(self.model, f, log))
        # Ein Woerterbuch fuer alle Koerper dieses Laufs: Koerper, die sich
        # eine Randflaeche teilen, bekommen dort dieselben Knoten. Ohne das
        # stuende jeder Koerper fuer sich und das Modell zerfiele.
        cache: dict = {}
        for k in koerper:
            self._netz_loeschen(k.elemente)
            k.elemente = []
            n += len(mesher.mesh_koerper(self.model, k, log, cache=cache))
        # Lasten, die an Flaechen und Koerpern haengen, koennen jetzt wirken
        self.model.lasten_verteilen(log)
        # und die Kontaktfugen koennen jetzt getrennt werden - ohne sie rechnet
        # das Modell dort durchverbunden, also zu steif.
        fugen.kontaktfugen_ausfuehren(self.model, log)
        for z in log:
            self.log.appendPlainText(z)
        if n:
            self.analysis = None
            self.results = None
        return n

    def geometrie_vernetzen(self):
        """Die ausgewaehlten - sonst alle - Flaechen und Koerper vernetzen."""
        m = self.model
        flaechen = [m.flaechen[x] for x in self.sel_flaechen if x in m.flaechen] \
            or list(m.flaechen.values())
        koerper = [m.koerper[x] for x in self.sel_koerper if x in m.koerper] \
            or list(m.koerper.values())
        if not flaechen and not koerper:
            return self.error("Es gibt keine Flächen oder Volumenkörper zum Vernetzen.")
        self.merken("Geometrie vernetzt")
        n = self._vernetzen(flaechen, koerper)
        self.refresh_all()
        self.info(f"{n} Elemente erzeugt" if n else
                  "Nichts vernetzt - das Protokoll sagt, warum")

    def kontaktfugen_ausfuehren(self):
        """Die Netze an den Kontaktbedingungen trennen."""
        from .. import fugen
        m = self.model
        if not (getattr(m, "kontaktbedingungen", {}) or {}):
            return self.error("Das Modell hat keine Kontaktbedingungen.")
        self.merken("Kontaktfugen ausgeführt")
        log = []
        ges = fugen.kontaktfugen_ausfuehren(m, log)
        for z in log:
            self.log.appendPlainText(z)
        if ges["fugen"]:
            self.analysis = None
            self.results = None
        self.refresh_all()
        self.info(f"{ges['fugen']} Kontaktfugen ausgeführt, {ges['offen']} offen"
                  if ges["fugen"] else
                  "Keine Kontaktfuge ausgeführt - das Protokoll sagt, warum")

    def netz_loeschen_geometrie(self):
        """Das Netz der Flaechen und Koerper entfernen, die Geometrie bleibt."""
        m = self.model
        els = [e for f in m.flaechen.values() for e in (f.elemente or [])]
        els += [e for k in m.koerper.values() for e in (k.elemente or [])]
        if not els:
            return self.error("Es liegt kein Netz aus Flächen oder Volumen vor.")
        self.merken("Netz der Geometrie gelöscht")
        self._netz_loeschen(els)
        for f in m.flaechen.values():
            f.elemente = []
        for k in m.koerper.values():
            k.elemente = []
        self.analysis = None
        self.results = None
        self.refresh_all()

    def querschnitt_bearbeiten(self, name: str):
        sec = self.model.sections.get(name)
        if sec is None:
            return self.add_section()
        d = dg.SectionDialog(self, sec)
        if not d.exec():
            return
        try:
            neu = d.result_section()
        except Exception as ex:      # noqa: BLE001
            return self.error(ex)
        self.merken(f"Querschnitt {name}")
        del self.model.sections[name]
        self.model.add_section(neu)
        if neu.name != name:
            for e in self.model.elements:
                if e.sec == name:
                    e.sec = neu.name
            for mm in self.model.members.values():
                if getattr(mm, "section", "") == name:
                    mm.section = neu.name
        self.refresh_all()

    def werkstoff_bearbeiten(self, name: str):
        mat = self.model.materials.get(name)
        if mat is None:
            return self.add_material()
        d = dg.MaterialDialog(self, mat)
        if not d.exec():
            return
        neu = d.result_material()
        self.merken(f"Werkstoff {name}")
        del self.model.materials[name]
        self.model.add_material(neu)
        if neu.name != name:
            for e in self.model.elements:
                if e.mat == name:
                    e.mat = neu.name
        self.refresh_all()

    def dicke_bearbeiten(self, name: str):
        prop = self.model.shells.get(name)
        if prop is None:
            return self.add_shell_prop()
        d = dg.DickeDialog(self, prop)
        if not d.exec():
            return
        neu_name, t = d.werte()
        self.merken(f"Dicke {name}")
        del self.model.shells[name]
        self.model.add_shell_prop(ShellProp(neu_name, t))
        if neu_name != name:
            for e in self.model.elements:
                if e.sec == name:
                    e.sec = neu_name
        self.refresh_all()

    def add_hinge(self):
        d = dg.GelenkDialog(self)
        if not d.exec():
            return
        from ..model import MemberHinge
        w = d.werte()
        self.merken(f"Gelenk {w['name']}")
        self.model.hinges[w["name"]] = MemberHinge(**w)
        self.refresh_all()

    def gelenk_bearbeiten(self, name: str):
        h = self.model.hinges.get(name)
        if h is None:
            return self.add_hinge()
        d = dg.GelenkDialog(self, h)
        if not d.exec():
            return
        w = d.werte()
        self.merken(f"Gelenk {name}")
        if w["name"] != name:
            del self.model.hinges[name]
        from ..model import MemberHinge
        self.model.hinges[w["name"]] = MemberHinge(**w)
        self.refresh_all()

    def lastfall_bearbeiten(self, name: str):
        lc = self.model.load_cases.get(name)
        if lc is None:
            return self.add_load_case()
        d = dg.LoadCaseDialog(self, lc, self.model.load_cases)
        if not d.exec():
            return
        nm, cat, desc, grp = d.values()
        self.merken(f"Lastfall {name}")
        lc.category, lc.description, lc.exclusive_group = cat, desc, grp
        if nm != name and nm not in self.model.load_cases:
            self.model.load_cases = {(nm if k == name else k): v
                                     for k, v in self.model.load_cases.items()}
            lc.name = nm
            for c in self.model.combinations.values():
                if name in c.factors:
                    c.factors[nm] = c.factors.pop(name)
            if self.model.active_case == name:
                self.model.active_case = nm
        self.refresh_all()

    def kombination_bearbeiten(self, name: str):
        c = self.model.combinations.get(name)
        if c is None:
            return self.add_combination()
        d = dg.CombinationDialog(self, self.model, c)
        if not d.exec():
            return
        self.merken(f"Kombination {name}")
        neu = d.result()
        if neu.name != name:
            del self.model.combinations[name]
        self.model.combinations[neu.name] = neu
        self.refresh_all()

    def add_support_dialog(self):
        """Neues Knotenlager an den ausgewaehlten Knoten."""
        if not len(self.selection):
            return self.error("Erst die Knoten auswählen, die gelagert werden sollen.")
        from ..model import Support
        vorlage = Support(int(self.selection[0]), [0, 1, 2])
        d = dg.SupportNonlinearDialog(self, vorlage, "Knotenlager", stammdaten=True)
        if not d.exec():
            return
        self.merken("Lager angelegt")
        for n in self.selection:
            s = self.model.support(int(n), [])
            d.apply(s)
        self.refresh_all()

    def lagerobjekt_bearbeiten(self, art: str, name: str):
        if not name.isdigit():
            return
        i = int(name)
        liste, titel = {"lager_einzeln": (self.model.supports, "Knotenlager"),
                        "linienlager_einzeln": (self.model.line_supports, "Linienlager"),
                        "flaechenlager_einzeln": (self.model.surface_supports,
                                                  "Flächenlager")}[art]
        if not (0 <= i < len(liste)):
            return
        d = dg.SupportNonlinearDialog(self, liste[i], titel, stammdaten=True)
        if d.exec():
            self.merken(f"{titel} bearbeitet")
            d.apply(liste[i])
            self.refresh_all()

    def _refresh_kopf(self):
        """Kopfzeile auf den Stand bringen: Bauteil, Version, Zustand."""
        if not hasattr(self, "kopf"):
            return
        from .. import update as upd
        try:
            ver = upd.version_label()
        except Exception:            # noqa: BLE001 - die Kopfzeile darf nie scheitern
            ver = __version__
        m = self.model
        bauteil = m.meta.get("Bauteil") or m.name or "Neues Modell"
        teile = [bauteil, f"Statik3D {ver}"]
        norm = m.meta.get("Norm")
        if norm:
            teile.insert(1, norm)
        stellungen = getattr(self, "stellungen", None) or []
        modell = f"{m.nn} Knoten · {len(m.elements)} Elemente"
        if stellungen:
            modell += f" · {len(stellungen)} Stellungen"
        if self.analysis is not None:
            info = getattr(self.analysis, "info", {}) or {}
            t = info.get("time") or info.get("dauer")
            zustand = "berechnet" + (f" · {float(t):.1f} s" if t else "")
            art = "gut"
        elif self.results is not None:
            zustand, art = "Ergebnis vorhanden", "gut"
        else:
            zustand, art = "bereit", "matt"
        self.kopf.setzen(" · ".join(teile), modell, zustand, art)

    def _refresh_baum(self):
        if hasattr(self, "baum"):
            self.baum.fuellen(self.model, self._stellungen_liste(),
                              self._ergebnisliste())

    def _ergebnisliste(self) -> dict:
        """Was gerechnet vorliegt, nach Art geordnet: {Gruppe: [(Text, Zusatz, Schluessel)]}.

        Die Schluessel sind dieselben, die das Auswahlfeld der Ergebnismaske
        fuehrt - Baum und Maske zeigen damit immer dasselbe.
        """
        out: dict[str, list] = {}
        an = self.analysis
        if an is not None:
            m = self.model
            out["Umhüllende"] = [(f"Umhüllende {k}", "", f"env:{k}")
                                 for k in getattr(an, "envelopes", {})]
            out["Kombinationen"] = [
                (k, m.combinations[k].formula() if k in m.combinations else "",
                 f"combo:{k}") for k in getattr(an, "combinations", {})]
            out["Lastfälle"] = [(k, m.load_cases[k].category
                                 if k in m.load_cases else "", f"case:{k}")
                                for k in getattr(an, "cases", {})]
            nachweise = []
            for feld, text in (("design", "Nachweise EC3"), ("fatigue", "Ermüdung"),
                               ("gzg", "Verformungen (GZG)"), ("beulen", "Beulen"),
                               ("lasteinleitung", "Lasteinleitung"),
                               ("volumen", "Volumen"), ("joints", "Anschlüsse"),
                               ("theorie2", "Theorie II. Ordnung")):
                erg = getattr(an, feld, None)
                if erg is None:
                    continue
                kurz = ""
                try:
                    kurz = str(erg.summary()).splitlines()[0][:60]
                except Exception:      # noqa: BLE001
                    pass
                nachweise.append((text, kurz, f"nachweis:{feld}"))
            out["Nachweise"] = nachweise
        r = self.current_result() if an is not None else None
        if r is not None and (getattr(r, "beam_end", None) or getattr(r, "beam", None)):
            # Die Schnittgroessen gehoeren in den Baum: dort sucht man sie,
            # und ein Klick stellt gleich den Verlauf in der Ansicht ein.
            grenzen = vp.schnittgroessen_grenzen(self.model, r)
            reihe = []
            for q in vp.SCHNITTGROESSEN:
                if q not in grenzen:
                    continue
                lo, _e1, hi, _e2 = grenzen[q]
                eh, f = vp.SG_EINHEIT[q]
                reihe.append((q, f"{lo / f:+.3g} … {hi / f:+.3g} {eh}",
                              f"schnittgroesse:{q}"))
            if reihe:
                reihe.append(("kein Verlauf", "Verlauf ausblenden",
                              "schnittgroesse:kein Verlauf"))
                out["Schnittgrößen"] = reihe
        r = self.results
        if r is not None:
            if getattr(r, "modes", None) is not None:
                out["Eigenformen"] = [
                    (f"Eigenform {i + 1}",
                     f"{r.freqs[i]:.3f} Hz" if getattr(r, "freqs", None) is not None
                     else "", f"modal:{i}") for i in range(len(r.modes))]
            if getattr(r, "buckling_modes", None) is not None:
                out["Knickfiguren"] = [
                    (f"Knickfigur {i + 1}",
                     f"α = {r.factors[i]:.3f}" if getattr(r, "factors", None) is not None
                     else "", f"buckling:{i}") for i in range(len(r.buckling_modes))]
        return {k: v for k, v in out.items() if v}


    def _stellungen_liste(self) -> list:
        """Stellungen als einfache Liste fuer Baum und Filmstreifen."""
        st = getattr(self, "stellungen", None) or []
        u = getattr(self, "umhuellende", None)
        erg = {}
        fuehrt = ""
        if u is not None:
            for e in u.reihe.ergebnisse:
                erg[e.stellung.name] = None if e.fehler else float(e.eta)
            besser = [e for e in u.reihe.ergebnisse if not e.fehler]
            if besser:
                fuehrt = max(besser, key=lambda e: e.eta).stellung.name
        return [{"name": s.name, "winkel": float(s.winkel),
                 "eta": erg.get(s.name), "fuehrt": s.name == fuehrt} for s in st]

    @staticmethod
    def _scroll(w):
        s = QtWidgets.QScrollArea()
        s.setWidgetResizable(True)
        s.setWidget(w)
        return s

    def _eingabetabelle(self, tbl, *knoepfe) -> QtWidgets.QWidget:
        """Eine Eingabetabelle mit ihrer Werkzeugzeile fuer den unteren Bereich.

        Die Knoepfe standen frueher als breite Schaltflaechen unter der
        Tabelle; bei zehn Tabellen wurde daraus eine Knopfwand, die mehr Platz
        brauchte als die Zeilen. Jetzt sind es schmale Werkzeugknoepfe in einer
        Zeile - dieselben Befehle, ein Drittel der Hoehe.
        """
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        lay.addWidget(tbl, 1)
        if knoepfe:
            zeile = QtWidgets.QHBoxLayout()
            zeile.setContentsMargins(4, 0, 4, 2)
            zeile.setSpacing(4)
            for k in knoepfe:
                if isinstance(k, QtWidgets.QPushButton):
                    b = QtWidgets.QToolButton(w)
                    b.setText(k.text())
                    b.setToolTip(k.toolTip() or k.text())
                    b.setObjectName("tabellenknopf")
                    b.clicked.connect(k.click)
                    k.setVisible(False)
                    k.setParent(w)
                    zeile.addWidget(b)
                elif isinstance(k, QtWidgets.QWidget):
                    zeile.addWidget(k)
                else:
                    lbl = QtWidgets.QLabel(str(k))
                    lbl.setObjectName("tabellenzahl")
                    zeile.addWidget(lbl)
            zeile.addStretch(1)
            halter = QtWidgets.QWidget(w)
            halter.setLayout(zeile)
            lay.addWidget(halter)
        return w

    def _build_eingabetabellen(self, tabs):
        """Werkstoffe, Querschnitte und Dicken als Tabellen unten.

        Im Bestand standen sie zusaetzlich im rechten Panel - dieselbe Angabe
        an zwei Stellen (Vorgabe Kap. 16.1 Nr. 6). Der Modellbaum verweist
        darauf, die Tabelle selbst steht nur noch hier.

        Die hellen Spalten sind **editierbar**: hineinklicken, Wert tippen,
        Eingabetaste. Gerechnet werden darf dabei (``= 210/1,1``). Jede
        Aenderung geht ueber ``merken`` und ist damit ruecknehmbar.
        """
        self.tbl_mat = tab.Datentabelle([
            Spalte("Name", hinweis="Bezeichnung des Werkstoffs"),
            Spalte("E", "GPa", "zahl", 1, True, hinweis="Elastizitätsmodul"),
            Spalte("ν", "", "zahl", 2, True, hinweis="Querdehnzahl (0 … 0,5)"),
            Spalte("ρ", "kg/m³", "zahl", 0, True, hinweis="Dichte"),
            Spalte("fy", "MPa", "zahl", 0, True, hinweis="Streckgrenze"),
            Spalte("Sorte", "", "text", 3, True,
                   hinweis="Stahlsorte nach EN 10025 für die Nachweise")],
            "Werkstoffe", self)
        self.tbl_mat.modell.aendern = self._mat_aendern
        b1 = QtWidgets.QPushButton("Werkstoff hinzufügen…")
        b1.clicked.connect(self.add_material)
        bd = QtWidgets.QPushButton("Löschen")
        bd.clicked.connect(lambda: self._delete_row(self.tbl_mat, self.model.materials))
        tabs.addTab(self._eingabetabelle(self.tbl_mat, b1, bd), "Werkstoffe")

        self.tbl_sec = tab.Datentabelle([
            Spalte("Name", hinweis="Bezeichnung des Querschnitts"),
            Spalte("Typ", hinweis="I, RHS, CHS, rect, circle, free"),
            Spalte("A", "cm²", "zahl", 2, True, hinweis="Querschnittsfläche"),
            Spalte("Iy", "cm⁴", "zahl", 1, True, hinweis="Trägheitsmoment um die starke Achse"),
            Spalte("Iz", "cm⁴", "zahl", 1, True, hinweis="Trägheitsmoment um die schwache Achse"),
            Spalte("It", "cm⁴", "zahl", 1, True, hinweis="Torsionsträgheitsmoment"),
            Spalte("Wpl,y", "cm³", "zahl", 1, True, hinweis="plastisches Widerstandsmoment"),
            Spalte("h", "mm", "zahl", 1, hinweis="Höhe (aus der Profildatenbank)"),
            Spalte("b", "mm", "zahl", 1, hinweis="Breite (aus der Profildatenbank)")],
            "Querschnitte", self)
        self.tbl_sec.modell.aendern = self._sec_aendern
        b2 = QtWidgets.QPushButton("Querschnitt hinzufügen (Profildatenbank)…")
        b2.clicked.connect(self.add_section)
        bd2 = QtWidgets.QPushButton("Löschen")
        bd2.clicked.connect(lambda: self._delete_row(self.tbl_sec, self.model.sections))
        tabs.addTab(self._eingabetabelle(self.tbl_sec, b2, bd2), "Querschnitte")

        self.tbl_shell = tab.Datentabelle([
            Spalte("Name", hinweis="Bezeichnung der Dicke"),
            Spalte("t", "m", "zahl", 4, True, hinweis="Dicke des Flächenelements")],
            "Dicken", self)
        self.tbl_shell.modell.aendern = self._shell_aendern
        self.ed_t = NumEdit(0.01, 80)
        b3 = QtWidgets.QPushButton("Dicke hinzufügen")
        b3.clicked.connect(self.add_shell_prop)
        tabs.addTab(self._eingabetabelle(self.tbl_shell, "t [m]", self.ed_t, b3), "Dicken")
        self._build_modelltabellen(tabs)

    def _build_modelltabellen(self, tabs):
        """Die modellierten Objekte selbst als Tabellen unten.

        Knoten, Linien, Elemente, Lager, Gelenke, Lastfaelle und Kombinationen
        stehen hier vollstaendig, filterbar und - wo es einen Sinn ergibt -
        editierbar. Der Modellbaum links sagt, **was** es gibt; hier steht,
        **womit**. Ein Klick auf eine Zeile waehlt das Objekt in der Ansicht,
        ein Doppelklick oeffnet seine Maske.
        """
        # ---- Knoten -------------------------------------------------------
        self.tbl_knoten = tab.Datentabelle([
            Spalte("Knoten", "", "ganz", hinweis="Knotennummer"),
            Spalte("x", "m", "zahl", 4, True), Spalte("y", "m", "zahl", 4, True),
            Spalte("z", "m", "zahl", 4, True),
            Spalte("Elemente", "", "ganz",
                   hinweis="Wie viele Elemente an dem Knoten hängen (0 = nur gesetzt)"),
            Spalte("Lager", "", "text", hinweis="Name des Lagers an diesem Knoten")],
            "Knoten", self, mit_kennwerten=True)
        self.tbl_knoten.modell.aendern = self._knoten_aendern
        self.tbl_knoten.zeile_gewaehlt.connect(self._tabelle_knoten)
        self.tbl_knoten.view.doubleClicked.connect(
            lambda _i: self.knoten_bearbeiten(self._zeilenzahl(self.tbl_knoten)))
        bk = QtWidgets.QPushButton("Knoten löschen")
        bk.clicked.connect(self.knoten_loeschen)
        tabs.addTab(self._eingabetabelle(self.tbl_knoten, bk), "Knoten")

        # ---- Linien -------------------------------------------------------
        self.tbl_linie = tab.Datentabelle([
            Spalte("Linie"), Spalte("Art"), Spalte("Knoten", "", "ganz"),
            Spalte("Länge", "m", "zahl", 3), Spalte("Folge"), Spalte("Bemerkung")],
            "Linien", self)
        self.tbl_linie.zeile_gewaehlt.connect(
            lambda w: self._baum_auswaehlen("linie", str(w)))
        self.tbl_linie.view.doubleClicked.connect(
            lambda _i: self.linie_bearbeiten(str(self._tabellenschluessel(self.tbl_linie))))
        bl1 = QtWidgets.QPushButton("Linie hinzufügen…")
        bl1.clicked.connect(self.add_linie)
        bl2 = QtWidgets.QPushButton("Löschen")
        bl2.clicked.connect(lambda: self._delete_row(self.tbl_linie, self.model.lines))
        tabs.addTab(self._eingabetabelle(self.tbl_linie, bl1, bl2), "Linien")

        # ---- Elemente -----------------------------------------------------
        self.tbl_elem = tab.Datentabelle([
            Spalte("Element", "", "ganz"), Spalte("Art"),
            Spalte("Knoten"), Spalte("Werkstoff", "", "text", 3, True),
            Spalte("Querschnitt / Dicke", "", "text", 3, True),
            Spalte("Drehung", "°", "zahl", 1, True,
                   hinweis="Verdrehung der lokalen Achsen um die Stabachse"),
            Spalte("Länge / Fläche", "", "zahl", 4),
            Spalte("Gelenke", "", "text")],
            "Elemente", self, mit_kennwerten=True)
        self.tbl_elem.modell.aendern = self._elem_aendern
        self.tbl_elem.zeile_gewaehlt.connect(self._tabelle_element)
        be = QtWidgets.QPushButton("Element löschen")
        be.clicked.connect(self.element_loeschen)
        tabs.addTab(self._eingabetabelle(self.tbl_elem, be), "Elemente")

        # ---- Lager --------------------------------------------------------
        self.tbl_lager = tab.Datentabelle([
            Spalte("Nr", "", "ganz"), Spalte("Art"), Spalte("Name", "", "text", 3, True),
            Spalte("Knoten"), Spalte("Wirkung"),
            Spalte("Nichtlinear", "", "text",
                   hinweis="Ausfall, Schlupf oder Reibung an einem Freiheitsgrad"),
            Spalte("Symbol", "", "zahl", 2, True,
                   hinweis="Größe des Lagersymbols in der Ansicht (1,0 = Grundgröße)")],
            "Lager", self)
        self.tbl_lager.modell.aendern = self._lager_aendern
        self.tbl_lager.zeile_gewaehlt.connect(self._tabelle_lager)
        self.tbl_lager.view.doubleClicked.connect(self._lagerzeile_bearbeiten)
        bg1 = QtWidgets.QPushButton("Lager hinzufügen…")
        bg1.clicked.connect(self.add_support_dialog)
        bg2 = QtWidgets.QPushButton("Löschen")
        bg2.clicked.connect(self.lagerzeile_loeschen)
        tabs.addTab(self._eingabetabelle(self.tbl_lager, bg1, bg2), "Lager")

        # ---- Gelenke ------------------------------------------------------
        self.tbl_gelenk = tab.Datentabelle([
            Spalte("Gelenk"), Spalte("Lage"), Spalte("Freigegeben"),
            Spalte("Federn", "kN/m bzw. kNm/rad"),
            Spalte("Beschreibung")], "Gelenke", self)
        self.tbl_gelenk.view.doubleClicked.connect(
            lambda _i: self.gelenk_bearbeiten(str(self._tabellenschluessel(self.tbl_gelenk))))
        bh1 = QtWidgets.QPushButton("Gelenk hinzufügen…")
        bh1.clicked.connect(self.add_hinge)
        bh2 = QtWidgets.QPushButton("Löschen")
        bh2.clicked.connect(lambda: self._delete_row(self.tbl_gelenk, self.model.hinges))
        tabs.addTab(self._eingabetabelle(self.tbl_gelenk, bh1, bh2), "Gelenke")

        # ---- Lastfaelle und Kombinationen ---------------------------------
        self.tbl_lastfall = tab.Datentabelle([
            Spalte("Lastfall"), Spalte("Einwirkung"), Spalte("Beschreibung", "", "text", 3, True),
            Spalte("Lasten", "", "ganz"), Spalte("Eigengewicht", "m/s²", "zahl", 2),
            Spalte("Ausschlussgruppe")], "Lastfälle", self)
        self.tbl_lastfall.modell.aendern = self._lastfall_aendern
        self.tbl_lastfall.view.doubleClicked.connect(
            lambda _i: self.lastfall_bearbeiten(str(self._tabellenschluessel(self.tbl_lastfall))))
        bf1 = QtWidgets.QPushButton("Lastfall hinzufügen…")
        bf1.clicked.connect(self.add_case)
        tabs.addTab(self._eingabetabelle(self.tbl_lastfall, bf1), "Lastfälle")

        self.tbl_geoflaeche = tab.Datentabelle([
            Spalte("Fläche"), Spalte("Randlinien"), Spalte("Dicke"),
            Spalte("Werkstoff"), Spalte("Teilung"),
            Spalte("Elemente", "", "ganz"), Spalte("Fläche", "m²", "zahl", 4),
            Spalte("Bemerkung")], "Flächen", self, mit_kennwerten=True)
        self.tbl_geoflaeche.zeile_gewaehlt.connect(
            lambda w: self._baum_geklickt("geoflaeche", str(w)))
        self.tbl_geoflaeche.view.doubleClicked.connect(
            lambda _i: self.flaeche_bearbeiten(
                str(self._tabellenschluessel(self.tbl_geoflaeche))))
        bq1 = QtWidgets.QPushButton("Fläche aus Linien…")
        bq1.clicked.connect(self.add_flaeche_aus_auswahl)
        bq2 = QtWidgets.QPushButton("Vernetzen")
        bq2.clicked.connect(self.geometrie_vernetzen)
        bq3 = QtWidgets.QPushButton("Löschen")
        bq3.clicked.connect(lambda: self._geometrie_loeschen(
            self.tbl_geoflaeche, self.model.flaechen))
        tabs.addTab(self._eingabetabelle(self.tbl_geoflaeche, bq1, bq2, bq3), "Flächen")

        self.tbl_geokoerper = tab.Datentabelle([
            Spalte("Volumenkörper"), Spalte("Randflächen"), Spalte("Werkstoff"),
            Spalte("Teilung"), Spalte("Elemente", "", "ganz"),
            Spalte("Volumen", "m³", "zahl", 5), Spalte("Bemerkung")],
            "Volumenkörper", self, mit_kennwerten=True)
        self.tbl_geokoerper.zeile_gewaehlt.connect(
            lambda w: self._baum_geklickt("geokoerper_einzeln", str(w)))
        self.tbl_geokoerper.view.doubleClicked.connect(
            lambda _i: self.koerper_bearbeiten(
                str(self._tabellenschluessel(self.tbl_geokoerper))))
        bv1 = QtWidgets.QPushButton("Volumen aus Flächen…")
        bv1.clicked.connect(self.add_koerper_aus_auswahl)
        bv2 = QtWidgets.QPushButton("Vernetzen")
        bv2.clicked.connect(self.geometrie_vernetzen)
        bv3 = QtWidgets.QPushButton("Löschen")
        bv3.clicked.connect(lambda: self._geometrie_loeschen(
            self.tbl_geokoerper, self.model.koerper))
        tabs.addTab(self._eingabetabelle(self.tbl_geokoerper, bv1, bv2, bv3),
                    "Volumenkörper")

        # ---- Lasten -------------------------------------------------------
        self.tbl_last = tab.Datentabelle([
            Spalte("Nr", "", "ganz"), Spalte("Lastfall"), Spalte("Art"),
            Spalte("Ziel", "", "text", hinweis="Knoten bzw. Element"),
            Spalte("Größe", "", "text",
                   hinweis="Knotenlast kN/kNm, Streckenlast kN/m, "
                           "Flächenlast kN/m², Temperatur K"),
            Spalte("Richtung"), Spalte("Bemerkung")],
            "Lasten", self, mit_kennwerten=False)
        self.tbl_last.zeile_gewaehlt.connect(self._tabelle_last)
        self.cb_lastfilter = QtWidgets.QComboBox()
        self.cb_lastfilter.setMinimumWidth(140)
        self.cb_lastfilter.setToolTip("Lasten welches Lastfalls anzeigen")
        self.cb_lastfilter.currentTextChanged.connect(
            lambda _t: self.refresh_modelltabellen())
        bl_1 = QtWidgets.QPushButton("Knotenlast…")
        bl_1.clicked.connect(self.maske_knotenlast)
        bl_2 = QtWidgets.QPushButton("Löschen")
        bl_2.clicked.connect(self.last_loeschen)
        tabs.addTab(self._eingabetabelle(self.tbl_last, "Lastfall",
                                         self.cb_lastfilter, bl_1, bl_2), "Lasten")

        self.tbl_bericht = tab.Datentabelle([
            Spalte("Nr", "", "ganz"), Spalte("Name", "", "text", 3, True),
            Spalte("Zeigt"), Spalte("Bildunterschrift", "", "text", 3, True),
            Spalte("Bemerkung", "", "text", 3, True),
            Spalte("Bild", "kB", "zahl", 0)], "Bericht", self)
        self.tbl_bericht.modell.aendern = self._bericht_aendern
        self.tbl_bericht.view.doubleClicked.connect(
            lambda _i: self.berichtseintrag_bearbeiten(
                str(self._zeilenzahl(self.tbl_bericht))))
        bb1 = QtWidgets.QPushButton("Ansicht übernehmen")
        bb1.clicked.connect(self.ansicht_in_bericht)
        bb2 = QtWidgets.QPushButton("▲")
        bb2.setToolTip("Nach oben")
        bb2.clicked.connect(lambda: self.berichtseintrag_schieben(-1))
        bb3 = QtWidgets.QPushButton("▼")
        bb3.setToolTip("Nach unten")
        bb3.clicked.connect(lambda: self.berichtseintrag_schieben(+1))
        bb4 = QtWidgets.QPushButton("Löschen")
        bb4.clicked.connect(self.berichtseintrag_loeschen)
        tabs.addTab(self._eingabetabelle(self.tbl_bericht, bb1, bb2, bb3, bb4),
                    "Bericht")

        self.tbl_freigabe = tab.Datentabelle([
            Spalte("Kontaktbedingung"), Spalte("Typ"), Spalte("Ort"),
            Spalte("Flächen", "", "ganz"), Spalte("Volumen", "", "ganz"),
            Spalte("Objekte", "", "ganz"), Spalte("Wirkung je FHG"),
            Spalte("Trennung ausgeführt", "", "text",
                   hinweis="Solange „nein“, rechnet das Modell an der Fuge "
                           "durchverbunden - also zu steif")],
            "Kontaktbedingungen", self)
        self.tbl_freigabe.zeile_gewaehlt.connect(
            lambda w: self.info(f"Kontaktbedingung {w}"))
        tabs.addTab(self._eingabetabelle(self.tbl_freigabe), "Kontaktbedingungen")

        self.tbl_kombi = tab.Datentabelle([
            Spalte("Kombination"), Spalte("Typ"), Spalte("Formel"),
            Spalte("Beschreibung")], "Kombinationen", self)
        self.tbl_kombi.view.doubleClicked.connect(
            lambda _i: self.kombination_bearbeiten(str(self._tabellenschluessel(self.tbl_kombi))))
        bc1 = QtWidgets.QPushButton("Kombination hinzufügen…")
        bc1.clicked.connect(self.add_combination)
        bc2 = QtWidgets.QPushButton("Löschen")
        bc2.clicked.connect(lambda: self._delete_row(self.tbl_kombi, self.model.combinations))
        tabs.addTab(self._eingabetabelle(self.tbl_kombi, bc1, bc2), "Kombinationen")

    # ---- Inhalt der Modelltabellen --------------------------------------
    def _zeilenzahl(self, tbl) -> int:
        """Der erste Spaltenwert der gewaehlten Zeile als ganze Zahl (-1 = keine).

        Ueber ``_tabellenschluessel``, damit Sortierung und Filter richtig
        umgerechnet werden - die sichtbare Zeile ist nicht die Modellzeile.
        """
        w = self._tabellenschluessel(tbl)
        try:
            return int(float(w))
        except (TypeError, ValueError):
            return -1

    def _lagerliste(self) -> list:
        """[(Art, Objekt)] aller Lager in der Reihenfolge der Tabelle."""
        m = self.model
        return ([("Knotenlager", x) for x in m.supports]
                + [("Linienlager", x) for x in m.line_supports]
                + [("Flächenlager", x) for x in m.surface_supports])

    @staticmethod
    def _wirkung(obj) -> tuple[str, str]:
        """(gehaltene Freiheitsgrade, Nichtlinearitaeten) eines Lagers."""
        namen = ["ux", "uy", "uz", "φx", "φy", "φz"]
        haelt, nl = [], []
        for d in range(6):
            b = obj.dof_behaviour(d)
            if b.acts:
                haelt.append(namen[d] + ("" if b.typ == "rigid"
                                         else f"={b.stiffness:.3g}"))
            if b.failure:
                nl.append(f"{namen[d]}: Ausfall bei {b.failure.capitalize()}")
            if b.slip:
                nl.append(f"{namen[d]}: Schlupf {b.slip * 1e3:g} mm")
            if b.mu:
                nl.append(f"{namen[d]}: μ = {b.mu:g}")
        return ", ".join(haelt) or "frei", "; ".join(nl)

    def refresh_modelltabellen(self):
        m = self.model
        self._raender_stand = None
        self._inhalte_stand = None
        if not hasattr(self, "tbl_knoten"):
            return
        # Knoten
        anzahl = np.zeros(m.nn, int)
        for e in m.elements:
            for n in e.nodes:
                if 0 <= int(n) < m.nn:
                    anzahl[int(n)] += 1
        lagername = {}
        for i, sp in enumerate(m.supports):
            lagername.setdefault(int(sp.node), sp.name or f"Lager {i + 1}")
        self._fill(self.tbl_knoten,
                   [[i, float(m.nodes[i][0]), float(m.nodes[i][1]), float(m.nodes[i][2]),
                     int(anzahl[i]), lagername.get(i, "")] for i in range(m.nn)])
        # Linien
        zeilen = []
        for name, ln in m.lines.items():
            pts = [int(x) for x in ln.nodes if 0 <= int(x) < m.nn]
            laenge = float(sum(np.linalg.norm(m.nodes[b] - m.nodes[a])
                               for a, b in zip(pts[:-1], pts[1:]))) if len(pts) > 1 else 0.0
            folge = ", ".join(str(x) for x in pts[:10]) + (" …" if len(pts) > 10 else "")
            zeilen.append([name, ln.typ, len(pts), laenge, folge, ln.comment])
        self._fill(self.tbl_linie, zeilen)
        # Elemente
        zeilen = []
        for i, e in enumerate(m.elements):
            X = m.nodes[[int(n) for n in e.nodes]]
            if e.typ in ("beam", "truss"):
                mass = float(np.linalg.norm(X[1] - X[0]))
            elif e.typ in ("shell3", "shell4"):
                mass = vp.polygon_flaeche(X)
            else:
                from ..elements import solid as _so
                try:
                    mass = float(_so.solid_volume(e.typ, X))
                except Exception:      # noqa: BLE001
                    mass = 0.0
            zeilen.append([i, e.typ, ", ".join(str(int(n)) for n in e.nodes), e.mat,
                           e.sec or "", np.degrees(e.roll), mass,
                           ", ".join(str(h) for h in (e.hinges or []))])
        self._fill(self.tbl_elem, zeilen)
        # Lager
        zeilen = []
        for i, (art, obj) in enumerate(self._lagerliste()):
            haelt, nl = self._wirkung(obj)
            if hasattr(obj, "node"):
                ort = str(obj.node)
            else:
                ns = [str(int(n)) for n in getattr(obj, "nodes", [])]
                ort = ", ".join(ns[:8]) + (f" … ({len(ns)})" if len(ns) > 8 else "")
            zeilen.append([i, art, getattr(obj, "name", "") or "", ort, haelt, nl,
                           float(getattr(obj, "groesse", 1.0) or 1.0)])
        self._fill(self.tbl_lager, zeilen)
        # Gelenke
        namen = ["ux", "uy", "uz", "φx", "φy", "φz"]
        zeilen = []
        for name, h in m.hinges.items():
            frei = ", ".join(namen[d] for d, t in enumerate(h.typ) if t == "free")
            fed = ", ".join(f"{namen[d]}={k / 1e3:g}"
                            for d, (t, k) in enumerate(zip(h.typ, h.stiffness))
                            if t == "spring" and k)
            zeilen.append([name, "Anfang" if h.end == 0 else "Ende",
                           frei or "biegesteif", fed, h.describe()])
        self._fill(self.tbl_gelenk, zeilen)
        # Lastfaelle
        self._fill(self.tbl_lastfall,
                   [[name, f"{lc.category}", lc.description, lc.n_loads,
                     float(lc.gravity[2]) if len(lc.gravity) > 2 else 0.0,
                     getattr(lc, "exclusive_group", "") or ""]
                    for name, lc in m.load_cases.items()])
        self._fill(self.tbl_kombi,
                   [[name, c.typ, c.formula(), c.description]
                    for name, c in m.combinations.items()])
        from .viewport import polygon_flaeche as _pf
        from ..elements import solid as _so
        zeilen = []
        for name, f in (getattr(m, "flaechen", {}) or {}).items():
            if f.elemente:
                A = sum(_pf(m.nodes[[int(n) for n in m.elements[i].nodes]])
                        for i in f.elemente if i < len(m.elements))
            else:
                # Fein abgetastet, nicht ueber das Anzeigepolygon: eine
                # Bohrung waere sonst um ein halbes Prozent zu klein.
                A = self._inhalte().get(name, 0.0)
            zeilen.append([name, ", ".join(f.linien), f.dicke, f.material,
                           " × ".join(str(x) for x in f.teilung),
                           len(f.elemente or []), A, f.kommentar])
        self._fill(self.tbl_geoflaeche, zeilen)
        zeilen = []
        for name, k in (getattr(m, "koerper", {}) or {}).items():
            V = 0.0
            for i in (k.elemente or []):
                if i < len(m.elements):
                    e = m.elements[i]
                    try:
                        V += float(_so.solid_volume(e.typ, m.nodes[[int(x) for x in e.nodes]]))
                    except Exception:      # noqa: BLE001
                        pass
            zeilen.append([name, ", ".join(k.flaechen), k.material,
                           " × ".join(str(x) for x in k.teilung),
                           len(k.elemente or []), V, k.kommentar])
        self._fill(self.tbl_geokoerper, zeilen)
        self._lasten_fuellen()
        self._fill(self.tbl_bericht,
                   [[i, x.name, x.bezug(), x.beschriftung, x.bemerkung,
                     len(x.bild or "") * 3 / 4096]
                    for i, x in enumerate(getattr(m, "bericht", None) or [])])
        self._fill(self.tbl_freigabe,
                   [[name, x.typ, x.ort, len(x.flaechen), len(x.volumen), x.ziele,
                     x.describe(), x.art_der_trennung(m)]
                    for name, x in (getattr(m, "kontaktbedingungen", {}) or {}).items()])

    #: Richtungsnamen der Knotenlast
    LASTRICHTUNG = ["Fx", "Fy", "Fz", "Mx", "My", "Mz"]

    def _lasten_fuellen(self):
        """Die Lasten aller (oder eines) Lastfaelle in die Tabelle schreiben."""
        m = self.model
        cb = self.cb_lastfilter
        namen = ["(alle)"] + list(m.load_cases)
        if [cb.itemText(i) for i in range(cb.count())] != namen:
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(namen)
            cb.setCurrentText(cur if cur in namen else "(alle)")
            cb.blockSignals(False)
        nur = cb.currentText()
        zeilen = []
        i = 0
        for lcname, lc in m.load_cases.items():
            if nur not in ("(alle)", "", lcname):
                continue
            if any(lc.gravity):
                zeilen.append([i, lcname, "Eigengewicht", "ganzes Modell",
                               f"{float(lc.gravity[2]):.2f} m/s²", "global Z", ""])
                i += 1
            # Aus Objektlasten abgeleitete Elementlasten (_geo) stehen nicht
            # in der Tabelle: bei einem Volumenmodell waeren es Hunderttausende,
            # und sie entstehen beim Verteilen neu. Die Objektlast steht dafuer.
            for l in lc.eigene("nodal_loads"):
                teile = [f"{self.LASTRICHTUNG[k]} = {v / 1e3:.3f}"
                         for k, v in enumerate(l.F) if v]
                zeilen.append([i, lcname, "Knotenlast", f"K{l.node}",
                               ", ".join(teile) or "0",
                               "global", ""])
                i += 1
            for l in lc.eigene("beam_loads"):
                q = ", ".join(f"{v / 1e3:.3f}" for v in l.q)
                abschnitt = (f"von {l.a:g} m" + (f" bis {l.b:g} m" if l.b is not None else "")
                             if getattr(l, "teilweise", False) else "")
                zeilen.append([i, lcname, "Streckenlast", f"E{l.elem}",
                               f"q = ({q}) kN/m", l.system,
                               " ".join(x for x in ("veränderlich" if l.q2 is not None else "",
                                                    abschnitt) if x)])
                i += 1
            for l in lc.eigene("face_loads"):
                zeilen.append([i, lcname, "Flächenlast", f"E{l.elem}",
                               f"p = {l.p / 1e3:.4f} kN/m²",
                               "Richtungsvektor" if l.direction else "lokal z", ""])
                i += 1
            for l in lc.eigene("temp_loads"):
                zeilen.append([i, lcname, "Temperatur", f"E{l.elem}",
                               f"ΔT = {l.dT:.2f} K",
                               f"ΔT_z = {l.dT_z:.2f} K" if l.dT_z else "gleichmäßig",
                               ""])
                i += 1
            for l in lc.geometrielasten:
                ziel = ("Fläche " if l.art == "flaeche" else "Volumen ") + str(l.ziel)
                if getattr(l, "lastart", "druck") == "temperatur":
                    zeilen.append([i, lcname, "Temperatur", ziel, f"ΔT = {l.dT:.2f} K",
                                   f"ΔT_z = {l.dT_z:.2f} K" if l.dT_z else "gleichmäßig",
                                   l.kommentar or "noch nicht vernetzt"])
                else:
                    if l.verlauf:
                        P = l.verlauf.get("punkte") or []
                        wert = "linear " + " → ".join(f"{float(x[3]) / 1e3:.3g}" for x in P) + " kN/m²"
                    else:
                        wert = f"p = {l.p / 1e3:.4f} kN/m²"
                    richtung = ("(" + ", ".join(f"{x:g}" for x in l.richtung) + ")"
                                if l.richtung else "senkrecht")
                    if l.projiziert:
                        richtung += " projiziert"
                    zeilen.append([i, lcname, "Flächenlast", ziel, wert, richtung,
                                   (("Fenster " if l.bereich else "")
                                    + (l.kommentar or "noch nicht vernetzt"))])
                i += 1
            for l in lc.linienlasten:
                ziel = ("Stab " if l.art == "stab" else "Linie ") + str(l.ziel)
                q = ", ".join(f"{v / 1e3:.3f}" for v in l.q)
                wert = f"q = ({q}) kN/m"
                if l.q2 is not None and list(l.q2) != list(l.q):
                    wert += " → (" + ", ".join(f"{v / 1e3:.3f}" for v in l.q2) + ")"
                abschnitt = ""
                if l.von or l.bis is not None:
                    abschnitt = f"von {l.von:g} m" + (f" bis {l.bis:g} m" if l.bis is not None
                                                      else " bis Ende")
                zeilen.append([i, lcname, "Linienlast", ziel, wert, l.system,
                               " ".join(x for x in (abschnitt, l.kommentar or "") if x)])
                i += 1
            for l in lc.zwangsverformungen:
                zeilen.append([i, lcname, "Zwangsverformung", f"K{l.node}",
                               l.bezug().split(": ", 1)[-1], "global", ""])
                i += 1
        self._fill(self.tbl_last, zeilen)

    def _lastzeiger(self, nr: int):
        """(Lastfall, Listenname, Index) zu einer Zeilennummer der Lasttabelle."""
        m = self.model
        nur = self.cb_lastfilter.currentText()
        i = 0
        for lcname, lc in m.load_cases.items():
            if nur not in ("(alle)", "", lcname):
                continue
            if any(lc.gravity):
                if i == nr:
                    return lc, "gravity", 0
                i += 1
            for liste in ("nodal_loads", "beam_loads", "face_loads", "temp_loads",
                          "geometrielasten", "linienlasten", "zwangsverformungen"):
                for k, l in enumerate(getattr(lc, liste)):
                    if getattr(l, "_geo", False):
                        continue
                    if i == nr:
                        return lc, liste, k
                    i += 1
        return None, "", -1

    def _tabelle_last(self, wert):
        """Zeile der Lasttabelle angeklickt: Ziel in der Ansicht waehlen."""
        try:
            nr = int(float(wert))
        except (TypeError, ValueError):
            return
        lc, liste, k = self._lastzeiger(nr)
        if lc is None or liste in ("", "gravity"):
            return
        obj = getattr(lc, liste)[k]
        m = self.model
        if liste in ("nodal_loads", "zwangsverformungen"):
            self._set_selection([int(obj.node)])
        elif liste == "geometrielasten":
            self.sel_flaechen = [obj.ziel] if obj.art == "flaeche" else []
            self.sel_koerper = [obj.ziel] if obj.art != "flaeche" else []
            self.redraw()
        elif liste == "linienlasten":
            self.sel_staebe = [obj.ziel] if obj.art == "stab" else []
            self.sel_linien = [obj.ziel] if obj.art != "stab" else []
            self.redraw()
        elif 0 <= int(obj.elem) < len(m.elements):
            self._set_selection([int(n) for n in m.elements[int(obj.elem)].nodes])

    def last_loeschen(self):
        nr = self._zeilenzahl(self.tbl_last)
        lc, liste, k = self._lastzeiger(nr)
        if lc is None or not liste:
            return self.error("Zuerst eine Zeile wählen")
        self.merken("Last gelöscht")
        if liste == "gravity":
            lc.gravity = [0.0, 0.0, 0.0]
        else:
            del getattr(lc, liste)[k]
            if liste in ("geometrielasten", "linienlasten"):
                # die daraus abgeleiteten Elementlasten gehen mit
                self.model.lasten_verteilen()
        self.analysis = None
        self.results = None
        self.refresh_all()

    # ---- Editieren in den Modelltabellen ---------------------------------
    def _knoten_aendern(self, z: int, k: int, wert) -> bool:
        i = int(self.tbl_knoten.modell.zeilen[z][0])
        if not (0 <= i < self.model.nn) or k not in (1, 2, 3):
            return False
        self.merken(f"Knoten {i} verschoben")
        self.model.nodes[i][k - 1] = float(wert)
        self._zelle_uebernommen(f"Knoten {i}: {'xyz'[k - 1]} = {float(wert):g} m")
        self.redraw()
        return True

    def _elem_aendern(self, z: int, k: int, wert) -> bool:
        i = int(self.tbl_elem.modell.zeilen[z][0])
        if not (0 <= i < len(self.model.elements)):
            return False
        e = self.model.elements[i]
        if k == 3:
            if str(wert) not in self.model.materials:
                self.info(f"Werkstoff „{wert}“ gibt es nicht - nicht übernommen")
                return False
            self.merken(f"Element {i}")
            e.mat = str(wert)
        elif k == 4:
            vorrat = self.model.sections if e.typ in ("beam", "truss") else self.model.shells
            if str(wert) not in vorrat:
                self.info(f"„{wert}“ steht nicht in der Liste - nicht übernommen")
                return False
            self.merken(f"Element {i}")
            e.sec = str(wert)
        elif k == 5:
            if e.typ not in ("beam", "truss"):
                return False
            self.merken(f"Element {i}")
            e.roll = float(np.radians(float(wert)))
        else:
            return False
        self._zelle_uebernommen(f"Element {i}: "
                                f"{self.tbl_elem.modell.spalten[k].kopf()} = {wert}")
        self.redraw()
        return True

    def _lager_aendern(self, z: int, k: int, wert) -> bool:
        i = int(self.tbl_lager.modell.zeilen[z][0])
        liste = self._lagerliste()
        if not (0 <= i < len(liste)) or k not in (2, 6):
            return False
        obj = liste[i][1]
        if k == 6 and not hasattr(obj, "groesse"):
            self.info("Nur Knotenlager tragen eine eigene Symbolgröße")
            return False
        self.merken("Lager bearbeitet")
        if k == 2:
            obj.name = str(wert).strip()
        else:
            obj.groesse = max(0.05, float(wert))
        self._zelle_uebernommen(f"Lager {i}: "
                                f"{self.tbl_lager.modell.spalten[k].kopf()} = {wert}")
        self.redraw()
        return True

    def _bericht_aendern(self, z: int, k: int, wert) -> bool:
        i = int(self.tbl_bericht.modell.zeilen[z][0])
        if not (0 <= i < len(self.model.bericht)) or k not in (1, 3, 4):
            return False
        self.merken("Bericht bearbeitet")
        e = self.model.bericht[i]
        if k == 1:
            e.name = str(wert).strip() or e.name
        elif k == 3:
            e.beschriftung = str(wert)
        else:
            e.bemerkung = str(wert)
        self._zelle_uebernommen(f"Berichtsbild {e.name}")
        return True

    def _lastfall_aendern(self, z: int, k: int, wert) -> bool:
        name = str(self.tbl_lastfall.modell.zeilen[z][0])
        lc = self.model.load_cases.get(name)
        if lc is None or k != 2:
            return False
        self.merken(f"Lastfall {name}")
        lc.description = str(wert)
        self._zelle_uebernommen(f"Lastfall {name}: Beschreibung = {wert}")
        return True

    # ---- Auswahl und Loeschen in den Modelltabellen ----------------------
    def _tabelle_lager(self, wert):
        try:
            i = int(float(wert))
        except (TypeError, ValueError):
            return
        liste = self._lagerliste()
        if not (0 <= i < len(liste)):
            return
        obj = liste[i][1]
        ns = [int(obj.node)] if hasattr(obj, "node") else \
            [int(n) for n in getattr(obj, "nodes", [])]
        self._set_selection([n for n in ns if 0 <= n < self.model.nn])

    def _lagerzeile_bearbeiten(self, *_a):
        i = self._zeilenzahl(self.tbl_lager)
        liste = self._lagerliste()
        if not (0 <= i < len(liste)):
            return
        art = {"Knotenlager": "lager_einzeln", "Linienlager": "linienlager_einzeln",
               "Flächenlager": "flaechenlager_einzeln"}[liste[i][0]]
        versatz = {"lager_einzeln": 0,
                   "linienlager_einzeln": len(self.model.supports),
                   "flaechenlager_einzeln": len(self.model.supports)
                   + len(self.model.line_supports)}[art]
        self.lagerobjekt_bearbeiten(art, str(i - versatz))

    def lagerzeile_loeschen(self):
        i = self._zeilenzahl(self.tbl_lager)
        liste = self._lagerliste()
        if not (0 <= i < len(liste)):
            return self.error("Zuerst eine Zeile wählen")
        art, obj = liste[i]
        self.merken(f"{art} gelöscht")
        for gruppe in (self.model.supports, self.model.line_supports,
                       self.model.surface_supports):
            if obj in gruppe:
                gruppe.remove(obj)
                break
        self.refresh_all()

    def _geometrie_loeschen(self, tbl, mapping: dict):
        """Eine Flaeche oder einen Koerper samt Netz entfernen."""
        key = self._tabellenschluessel(tbl)
        if key is None or key not in mapping:
            return self.error("Zuerst eine Zeile wählen")
        obj = mapping[key]
        if mapping is self.model.flaechen:
            benutzt = [k for k, x in self.model.koerper.items() if key in x.flaechen]
            if benutzt:
                return self.error(f"„{key}“ berandet noch {', '.join(benutzt)} – "
                                  "erst den Volumenkörper löschen.")
        self.merken(f"„{key}“ gelöscht")
        self._netz_loeschen(obj.elemente)
        del mapping[key]
        self.analysis = None
        self.results = None
        self.refresh_all()

    def knoten_loeschen(self):
        """Den gewaehlten Knoten entfernen - nur, wenn kein Element daran haengt.

        Ein Knoten mitten im Netz laesst sich nicht einfach herausnehmen: alle
        Elementnummern dahinter wuerden sich verschieben. Darum wird nur ein
        freier Knoten geloescht, und das wird auch gesagt.
        """
        i = self._zeilenzahl(self.tbl_knoten)
        m = self.model
        if not (0 <= i < m.nn):
            return self.error("Zuerst eine Zeile wählen")
        if any(i in [int(n) for n in e.nodes] for e in m.elements):
            return self.error(f"An Knoten {i} hängt mindestens ein Element - "
                              "erst das Element löschen.")
        self.merken(f"Knoten {i} gelöscht")
        m.nodes = np.delete(m.nodes, i, axis=0)
        for e in m.elements:
            e.nodes = [(n - 1 if n > i else n) for n in e.nodes]
        for ln in m.lines.values():
            ln.nodes = [(n - 1 if n > i else n) for n in ln.nodes if n != i]
        m.supports = [sp for sp in m.supports if sp.node != i]
        for sp in m.supports:
            if sp.node > i:
                sp.node -= 1
        for grp in (m.line_supports, m.surface_supports):
            for x in grp:
                x.nodes = [(n - 1 if n > i else n) for n in x.nodes if n != i]
        for lc in m.load_cases.values():
            lc.nodal_loads = [l for l in lc.nodal_loads if l.node != i]
            for l in lc.nodal_loads:
                if l.node > i:
                    l.node -= 1
        self.selection = np.array([], dtype=int)
        self.refresh_all()

    def element_loeschen(self):
        i = self._zeilenzahl(self.tbl_elem)
        m = self.model
        if not (0 <= i < len(m.elements)):
            return self.error("Zuerst eine Zeile wählen")
        self.merken(f"Element {i} gelöscht")
        del m.elements[i]
        for mem in m.members.values():
            mem.elements = [(e - 1 if e > i else e) for e in mem.elements if e != i]
        for lc in m.load_cases.values():
            lc.beam_loads = [l for l in lc.beam_loads if l.elem != i]
            for l in lc.beam_loads:
                if l.elem > i:
                    l.elem -= 1
            lc.face_loads = [l for l in lc.face_loads if l.elem != i]
            for l in lc.face_loads:
                if l.elem > i:
                    l.elem -= 1
        self.refresh_all()

    # ---- Editieren in den Eingabetabellen ------------------------------
    def _pruefen(self, wert: float, unten=None, oben=None, was: str = "Wert") -> bool:
        """Grenzen eines eingetippten Wertes.

        Ein unmoeglicher Wert wird nicht uebernommen; die Zelle behaelt ihren
        alten Inhalt. Gemeldet wird das in der Statuszeile und im Protokoll -
        ein Meldungsfenster bei jedem Vertipper waere im Weg.
        """
        if unten is not None and wert <= unten:
            self.info(f"{was}: {wert:g} ist nicht größer als {unten:g} - nicht übernommen")
            return False
        if oben is not None and wert >= oben:
            self.info(f"{was}: {wert:g} ist nicht kleiner als {oben:g} - nicht übernommen")
            return False
        return True

    def _zelle_uebernommen(self, was: str):
        """Nachlauf einer Zellaenderung: Ergebnisse verwerfen, Baum auffrischen."""
        self.analysis = None
        self.results = None
        self._undo_knoepfe()
        self._refresh_baum()
        self.info(was)

    def _mat_aendern(self, z: int, k: int, wert) -> bool:
        name = str(self.tbl_mat.modell.zeilen[z][0])
        v = self.model.materials.get(name)
        if v is None or k == 0:
            return False
        if k == 5:                       # Stahlsorte ist Text
            self.merken(f"Werkstoff {name}")
            v.grade = str(wert).strip().upper()
            self._zelle_uebernommen(f"Werkstoff {name}: Sorte = {v.grade}")
            return True
        w = float(wert)
        if k == 1 and not self._pruefen(w, unten=0.0, was="E-Modul"):
            return False
        if k == 2 and not self._pruefen(w, unten=-1.0, oben=0.5, was="Querdehnzahl"):
            return False
        if k in (3, 4) and not self._pruefen(w, unten=-1e-9, was=self.tbl_mat.modell.spalten[k].name):
            return False
        self.merken(f"Werkstoff {name}")
        if k == 1:
            v.E = w * 1e9
        elif k == 2:
            v.nu = w
        elif k == 3:
            v.rho = w
        elif k == 4:
            v.fy = w * 1e6
        self._zelle_uebernommen(f"Werkstoff {name}: "
                                f"{self.tbl_mat.modell.spalten[k].kopf()} = {wert}")
        return True

    #: Spalte der Querschnittstabelle -> (Feld, Faktor auf SI, Bezeichnung)
    SEC_FELDER = {2: ("A", 1e-4, "Fläche A"), 3: ("Iy", 1e-8, "Iy"),
                  4: ("Iz", 1e-8, "Iz"), 5: ("It", 1e-8, "It"),
                  6: ("Wpl_y", 1e-6, "Wpl,y")}

    def _sec_aendern(self, z: int, k: int, wert) -> bool:
        name = str(self.tbl_sec.modell.zeilen[z][0])
        v = self.model.sections.get(name)
        if v is None or k not in self.SEC_FELDER:
            return False
        feld, faktor, was = self.SEC_FELDER[k]
        if not self._pruefen(float(wert), unten=0.0, was=was):
            return False
        self.merken(f"Querschnitt {name}")
        setattr(v, feld, float(wert) * faktor)
        if v.typ != "free":
            v.typ = "free"          # von Hand geaendert: keine Profilgeometrie mehr
            self.tbl_sec.modell.zeilen[z][1] = "free"
        self._zelle_uebernommen(f"Querschnitt {name}: {was} = {wert}")
        return True

    def _shell_aendern(self, z: int, k: int, wert) -> bool:
        name = str(self.tbl_shell.modell.zeilen[z][0])
        v = self.model.shells.get(name)
        if v is None or k != 1:
            return False
        if not self._pruefen(float(wert), unten=0.0, was="Dicke"):
            return False
        self.merken(f"Dicke {name}")
        v.t = float(wert)
        self._zelle_uebernommen(f"Dicke {name}: t = {float(wert):g} m")
        return True

    def _build_ergebnistabellen(self, tabs):
        """Die Ergebnistabellen: filterbar, sortierbar, mit Max- und Min-Zeile.

        Ein Klick auf eine Zeile waehlt das Element beziehungsweise den Knoten
        in der Ansicht; umgekehrt markiert eine Auswahl in der Ansicht die
        zugehoerigen Zeilen (Vorgabe Kap. 3.6).
        """
        kN, kNm = "kN", "kNm"
        self.tbl_beam = tab.Datentabelle([
            Spalte("Element", "", "ganz"),
            Spalte("N1", kN, "zahl", 2), Spalte("N2", kN, "zahl", 2),
            Spalte("Vz1", kN, "zahl", 2), Spalte("Vz2", kN, "zahl", 2),
            Spalte("My1", kNm, "zahl", 2), Spalte("My2", kNm, "zahl", 2),
            Spalte("Mz max", kNm, "zahl", 2),
            Spalte("σ", "MPa", "zahl", 1),
            Spalte("Ausn.", "", "zahl", 3, hinweis="Ausnutzung; Filter z. B. > 0,9")],
            "Stabkraefte", self, mit_kennwerten=True)
        self.tbl_beam.zeile_gewaehlt.connect(self._tabelle_element)
        tabs.addTab(self.tbl_beam, "Stabkräfte")

        self.tbl_react = tab.Datentabelle([
            Spalte("Knoten", "", "ganz"),
            Spalte("Rx", kN, "zahl", 2), Spalte("Ry", kN, "zahl", 2),
            Spalte("Rz", kN, "zahl", 2), Spalte("Mx", kNm, "zahl", 2),
            Spalte("My", kNm, "zahl", 2), Spalte("Mz", kNm, "zahl", 2)],
            "Auflagerkraefte", self, mit_kennwerten=True)
        self.tbl_react.zeile_gewaehlt.connect(self._tabelle_knoten)
        tabs.addTab(self.tbl_react, "Auflagerkräfte")

        self.tbl_env = tab.Datentabelle([
            Spalte("Element", "", "ganz"), Spalte("Größe"),
            Spalte("min", "", "zahl", 2), Spalte("Kombination"),
            Spalte("max", "", "zahl", 2), Spalte("Kombination ")],
            "Umhuellende", self, mit_kennwerten=True)
        self.tbl_env.zeile_gewaehlt.connect(self._tabelle_element)
        tabs.addTab(self.tbl_env, "Umhüllende")

        self.tbl_design = tab.Datentabelle([
            Spalte("Stab"), Spalte("Querschnitt"), Spalte("Material"),
            Spalte("L", "m", "zahl", 2), Spalte("Klasse", "", "ganz"),
            Spalte("Ausnutzung", "", "zahl", 3, hinweis="Filter z. B. > 1 zeigt alle Überschreitungen"),
            Spalte("maßgebender Nachweis"), Spalte("Kombination"),
            Spalte("x", "m", "zahl", 2), Spalte("Status")],
            "Nachweise_EC3", self, mit_kennwerten=True)
        self.tbl_design.zeile_gewaehlt.connect(self._tabelle_stab)
        tabs.addTab(self.tbl_design, "Nachweise EC3")

        self.tbl_fat = tab.Datentabelle([
            Spalte("Stab"), Spalte("Kerbfall", "MPa", "zahl", 0),
            Spalte("γ_Mf", "", "zahl", 2),
            Spalte("max Δσ", "MPa", "zahl", 1), Spalte("Δσ_E,2", "MPa", "zahl", 1),
            Spalte("D (Miner)", "", "zahl", 3), Spalte("D Schub", "", "zahl", 3),
            Spalte("Ausnutzung", "", "zahl", 3), Spalte("maßgebend")],
            "Ermuedung", self, mit_kennwerten=True)
        self.tbl_fat.zeile_gewaehlt.connect(self._tabelle_stab)
        tabs.addTab(self.tbl_fat, "Ermüdung")

        self.tbl_contact = tab.Datentabelle([
            Spalte("Knoten", "", "ganz"), Spalte("Art"), Spalte("Status"),
            Spalte("Fn", kN, "zahl", 2), Spalte("Ft", kN, "zahl", 2),
            Spalte("Spalt", "mm", "zahl", 3)],
            "Kontakt", self, mit_kennwerten=True)
        self.tbl_contact.zeile_gewaehlt.connect(self._tabelle_knoten)
        tabs.addTab(self.tbl_contact, "Kontakt")

        # Anschluesse: Eingabe und Ergebnis in einer Tabelle. Vor der Rechnung
        # stehen Typ und Ort, danach zusaetzlich Ausnutzung und Status.
        self.tbl_joint = tab.Datentabelle([
            Spalte("Anschluss"), Spalte("Typ"), Spalte("Ort"),
            Spalte("Stab"), Spalte("Querschnitt"),
            Spalte("S_j,ini", "MNm/rad", "zahl", 1,
                   hinweis="Anfangssteifigkeit nach dem Komponentenverfahren (6.3.1)"),
            Spalte("Klasse", hinweis="starr, nachgiebig oder gelenkig (5.2.2.5)"),
            Spalte("M_j,Rd", "kNm", "zahl", 1,
                   hinweis="Momententragfähigkeit des Anschlusses (6.2.7)"),
            Spalte("in der Rechnung",
                   hinweis="wie der Anschluss im Modell sitzt: starr, Drehfeder, Gelenk"),
            Spalte("Ausnutzung", "", "zahl", 3,
                   hinweis="Tragfähigkeit nach EN 1993-1-8; Filter z. B. > 1"),
            Spalte("maßgebender Nachweis"), Spalte("Kombination"),
            Spalte("D (Ermüdung)", "", "zahl", 3,
                   hinweis="Schädigungssumme nach Palmgren-Miner"),
            Spalte("Status")], "Anschluesse", self, mit_kennwerten=True)
        self.tbl_joint.zeile_gewaehlt.connect(self._tabelle_anschluss)
        b_neu = QtWidgets.QPushButton("Anschluss anlegen…")
        b_neu.clicked.connect(self.add_joint)
        b_zeig = QtWidgets.QPushButton("Nachweise zeigen")
        b_zeig.clicked.connect(self.show_joints)
        b_weg = QtWidgets.QPushButton("Löschen")
        b_weg.clicked.connect(self.delete_joint)
        tabs.addTab(self._eingabetabelle(self.tbl_joint, b_neu, b_zeig, b_weg),
                    "Anschlüsse")

        # Verformungsnachweise (GZG): Grenzwert und Ergebnis in einer Tabelle
        self.tbl_gzg = tab.Datentabelle([
            Spalte("Nachweis"), Spalte("Bezug"), Spalte("Größe"),
            Spalte("Situation"),
            Spalte("Wert", "mm", "zahl", 2,
                   hinweis="größte Verformung über alle GZG-Kombinationen"),
            Spalte("Grenzwert"),
            Spalte("Ausnutzung", "", "zahl", 3, hinweis="Filter z. B. > 1"),
            Spalte("Kombination"), Spalte("Stelle"), Spalte("Status")],
            "Verformungen", self, mit_kennwerten=True)
        self.tbl_gzg.zeile_gewaehlt.connect(self._tabelle_verformung)
        v1 = QtWidgets.QPushButton("Verformungsgrenze…")
        v1.clicked.connect(self.add_verformungsgrenze)
        v2 = QtWidgets.QPushButton("Ändern…")
        v2.clicked.connect(self.edit_verformungsgrenze)
        v3 = QtWidgets.QPushButton("Löschen")
        v3.clicked.connect(self.delete_verformungsgrenze)
        tabs.addTab(self._eingabetabelle(self.tbl_gzg, v1, v2, v3), "Verformungen")

        # Beulfelder (EN 1993-1-5, Abschnitt 10)
        self.tbl_beul = tab.Datentabelle([
            Spalte("Beulfeld"), Spalte("Elemente", "", "ganz"),
            Spalte("a", "m", "zahl", 2), Spalte("b", "m", "zahl", 2),
            Spalte("t", "mm", "zahl", 1),
            Spalte("σ_x", "MPa", "zahl", 1), Spalte("σ_z", "MPa", "zahl", 1),
            Spalte("τ", "MPa", "zahl", 1),
            Spalte("λ̄_p", "", "zahl", 3, hinweis="Schlankheit des Beulfeldes"),
            Spalte("Ausnutzung", "", "zahl", 3, hinweis="Gl. (10.5); Filter z. B. > 1"),
            Spalte("Kombination"), Spalte("Status")],
            "Beulfelder", self, mit_kennwerten=True)
        self.tbl_beul.zeile_gewaehlt.connect(self._tabelle_beulfeld)
        c1 = QtWidgets.QPushButton("Beulfeld aus Auswahl…")
        c1.setToolTip("Die gewählten Flächenelemente zu einem Beulfeld zusammenfassen")
        c1.clicked.connect(self.add_beulfeld)
        c2 = QtWidgets.QPushButton("Löschen")
        c2.clicked.connect(self.delete_beulfeld)
        c3 = QtWidgets.QPushButton("Ändern…")
        c3.clicked.connect(self.edit_beulfeld)
        tabs.addTab(self._eingabetabelle(self.tbl_beul, c1, c3, c2), "Beulfelder")

        # Volumenbereiche (EN 1993-1-1, 6.2.1(5))
        self.tbl_vol = tab.Datentabelle([
            Spalte("Bereich"), Spalte("Elemente", "", "ganz"),
            Spalte("Material"), Spalte("f_y", "MPa", "zahl", 0),
            Spalte("σ_1", "MPa", "zahl", 1), Spalte("σ_3", "MPa", "zahl", 1),
            Spalte("σ_v", "MPa", "zahl", 1,
                   hinweis="Vergleichsspannung nach von Mises"),
            Spalte("h", "", "zahl", 2,
                   hinweis="Mehrachsigkeit σ_m/σ_v; bei dreiachsigem Zug kritisch"),
            Spalte("Ausnutzung", "", "zahl", 3, hinweis="σ_v/(f_y/γ_M0); Filter z. B. > 1"),
            Spalte("Kombination"), Spalte("Status")],
            "Volumen", self, mit_kennwerten=True)
        self.tbl_vol.zeile_gewaehlt.connect(self._tabelle_volumen)
        w1 = QtWidgets.QPushButton("Bereich aus Auswahl…")
        w1.setToolTip("Die gewählten Volumenelemente zu einem Bereich zusammenfassen")
        w1.clicked.connect(self.add_volumenbereich)
        w2 = QtWidgets.QPushButton("Löschen")
        w2.clicked.connect(self.delete_volumenbereich)
        w3 = QtWidgets.QPushButton("Ändern…")
        w3.clicked.connect(self.edit_volumenbereich)
        tabs.addTab(self._eingabetabelle(self.tbl_vol, w1, w3, w2), "Volumen")

        # Lasteinleitung (EN 1993-1-5, Abschnitt 6)
        self.tbl_le = tab.Datentabelle([
            Spalte("Stelle"), Spalte("Bezug"), Spalte("Typ"),
            Spalte("F_Ed", "kN", "zahl", 1), Spalte("F_Rd", "kN", "zahl", 1),
            Spalte("l_y", "mm", "zahl", 0),
            Spalte("λ̄_F", "", "zahl", 3), Spalte("χ_F", "", "zahl", 3),
            Spalte("Ausnutzung", "", "zahl", 3), Spalte("Kombination"),
            Spalte("Status")], "Lasteinleitung", self, mit_kennwerten=True)
        self.tbl_le.zeile_gewaehlt.connect(self._tabelle_lasteinleitung)
        d1 = QtWidgets.QPushButton("Lasteinleitung…")
        d1.clicked.connect(self.add_lasteinleitung)
        d2 = QtWidgets.QPushButton("Ändern…")
        d2.clicked.connect(self.edit_lasteinleitung)
        d3 = QtWidgets.QPushButton("Löschen")
        d3.clicked.connect(self.delete_lasteinleitung)
        tabs.addTab(self._eingabetabelle(self.tbl_le, d1, d2, d3), "Lasteinleitung")

    #: Ergebnistabellen in der Reihenfolge des unteren Bereichs
    ERGEBNISTABELLEN = ("tbl_beam", "tbl_react", "tbl_env", "tbl_design",
                        "tbl_fat", "tbl_contact")

    def _build_bottom(self):
        dock = QtWidgets.QDockWidget("Protokoll und Tabellen", self)
        dock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        self.unten_dock = dock
        tabs = QtWidgets.QTabWidget()
        self.tab_unten = tabs
        # Der untere Bereich traegt Protokoll, Eingabe- und Ergebnistabellen -
        # mehr Register, als nebeneinander passen. Die Leiste bekommt darum
        # Blaetterknoepfe; gefunden wird eine Tabelle ohnehin ueber den
        # Modellbaum links, der sie nach vorn holt.
        tabs.setUsesScrollButtons(True)
        tabs.tabBar().setElideMode(QtCore.Qt.ElideNone)
        tabs.tabBar().setExpanding(False)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family: monospace; font-size: 11px;")
        tabs.addTab(self.log, "Protokoll")
        self._build_eingabetabellen(tabs)
        self._build_ergebnistabellen(tabs)
        self._register_ordnen(tabs)
        self.bottom_tabs = tabs
        dock.setWidget(tabs)
        dock.setMinimumHeight(190)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock)

    #: Reihenfolge der Register unten - dieselbe wie im Modellbaum links.
    #: Der Baum sagt, was es gibt; hier steht dasselbe als Tabelle. Beides in
    #: derselben Folge zu halten spart das Suchen.
    REGISTER_FOLGE = ["Protokoll",
                      "Knoten", "Linien", "Flächen", "Volumenkörper", "Elemente",
                      "Werkstoffe", "Querschnitte", "Dicken",
                      "Lager", "Gelenke", "Kontaktbedingungen",
                      "Lastfälle", "Lasten", "Kombinationen",
                      "Stabkräfte", "Auflagerkräfte", "Umhüllende",
                      "Nachweise EC3", "Ermüdung", "Kontakt", "Anschlüsse",
                      "Verformungen", "Beulfelder", "Volumen", "Lasteinleitung",
                      "Bericht"]

    def _register_ordnen(self, tabs):
        """Die Register unten in die Reihenfolge des Modellbaums bringen."""
        bar = tabs.tabBar()
        for ziel, name in enumerate(self.REGISTER_FOLGE):
            jetzt = next((i for i in range(tabs.count())
                          if tabs.tabText(i) == name), None)
            if jetzt is not None and jetzt != ziel:
                bar.moveTab(jetzt, ziel)

    # ---- Tab 1: Modell ------------------------------------------------
    def _tab_model(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.addWidget(QtWidgets.QLabel("<b>Projekt</b>"))
        self.ed_meta = {}
        g = QtWidgets.QGridLayout()
        for i, (k, label) in enumerate((("projekt", "Projekt"), ("bauteil", "Bauteil"),
                                        ("position", "Position"), ("bearbeiter", "Bearbeiter"))):
            e = QtWidgets.QLineEdit()
            e.editingFinished.connect(lambda k=k, e=e: self.model.meta.__setitem__(k, e.text()))
            self.ed_meta[k] = e
            g.addWidget(QtWidgets.QLabel(label), i // 2, 2 * (i % 2))
            g.addWidget(e, i // 2, 2 * (i % 2) + 1)
        lay.addLayout(g)

        # „Elemente ändern“ steht jetzt im Register „Auswahl: n Knoten“, das
        # erscheint, sobald etwas gewählt ist (Vorgabe Kap. 16.1 Nr. 7).
        self.ed_elist = QtWidgets.QLineEdit()          # bleibt als Eingabeweg
        self.ed_elist.hide()
        self.ed_hinge = QtWidgets.QComboBox()
        self.ed_hinge.addItems(["Gelenk: keines", "Gelenk Anfang (My, Mz)",
                                "Gelenk Ende (My, Mz)", "Gelenk beide Enden",
                                "Vollgelenk beide Enden (Mt, My, Mz)"])
        self.ed_hinge.hide()


        lay.addStretch()
        return w

    # ---- Tab 2: Netz --------------------------------------------------
    def _tab_mesh(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.cb_mat = QtWidgets.QComboBox()
        self.cb_sec = QtWidgets.QComboBox()
        self.cb_shell = QtWidgets.QComboBox()
        lay.addWidget(row("Material", self.cb_mat))
        lay.addWidget(row("Querschnitt", self.cb_sec, "Dicke", self.cb_shell))

        g = QtWidgets.QGroupBox("Stabzug (wird als Stab für Nachweise registriert)")
        gl = QtWidgets.QVBoxLayout(g)
        self.beam_p1 = [NumEdit(0, 65) for _ in range(3)]
        self.beam_p2 = [NumEdit(v, 65) for v in (5, 0, 0)]
        self.beam_n = QtWidgets.QSpinBox(); self.beam_n.setRange(1, 500); self.beam_n.setValue(4)
        self.beam_truss = QtWidgets.QCheckBox("Fachwerkstab")
        gl.addWidget(row("von x,y,z", *self.beam_p1))
        gl.addWidget(row("bis x,y,z", *self.beam_p2))
        bb = QtWidgets.QPushButton("Stäbe erzeugen")
        bb.clicked.connect(self.make_beams)
        gl.addWidget(row("Teilung", self.beam_n, self.beam_truss, bb))
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Platte / Scheibe (xy-Ebene)")
        gl = QtWidgets.QVBoxLayout(g)
        self.pl = [NumEdit(v, 65) for v in (4.0, 3.0, 0.0)]
        self.pn = [QtWidgets.QSpinBox() for _ in range(2)]
        for s in self.pn:
            s.setRange(1, 400); s.setValue(10)
        self.pl_quad = QtWidgets.QCheckBox("Vierecke"); self.pl_quad.setChecked(True)
        gl.addWidget(row("lx, ly, z", *self.pl))
        bp = QtWidgets.QPushButton("Schalennetz erzeugen")
        bp.clicked.connect(self.make_plate)
        gl.addWidget(row("nx, ny", *self.pn, self.pl_quad, bp))
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Quader (Volumen)")
        gl = QtWidgets.QVBoxLayout(g)
        self.bl = [NumEdit(v, 65) for v in (2.0, 0.4, 0.4)]
        self.bo = [NumEdit(0.0, 65) for _ in range(3)]
        self.bn = [QtWidgets.QSpinBox() for _ in range(3)]
        for s, v in zip(self.bn, (10, 3, 3)):
            s.setRange(1, 200); s.setValue(v)
        self.b_typ = QtWidgets.QComboBox(); self.b_typ.addItems(["hex8", "tet4"])
        gl.addWidget(row("lx, ly, lz", *self.bl))
        gl.addWidget(row("Ursprung", *self.bo))
        bq = QtWidgets.QPushButton("Volumennetz erzeugen")
        bq.clicked.connect(self.make_box)
        gl.addWidget(row("nx, ny, nz", *self.bn, self.b_typ, bq))
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Import")
        gl = QtWidgets.QVBoxLayout(g)
        gl.addWidget(QtWidgets.QLabel("DXF, IFC (Statikmodell: InfoCAD, RFEM), SAF (.xlsx), "
                                      "RFEM-Tabellen, Abaqus/CalculiX .inp, Nastran .bdf,\n"
                                      "STEP/IGES/STL (gmsh) - siehe Datei → Importieren"))
        bi = QtWidgets.QPushButton("Datei importieren…")
        bi.clicked.connect(self.import_file)
        gl.addWidget(bi)
        if not mesher.HAVE_GMSH:
            lbl = QtWidgets.QLabel("gmsh nicht installiert (CAD-Import)  →  pip install gmsh")
            lbl.setStyleSheet("color:#a00")
            gl.addWidget(lbl)
        lay.addWidget(g)

        bm_ = QtWidgets.QPushButton("Doppelte Knoten zusammenführen")
        bm_.clicked.connect(self.do_merge)
        bd = QtWidgets.QPushButton("Netz löschen")
        bd.clicked.connect(self.clear_mesh)
        lay.addWidget(row(bm_, bd))
        lay.addStretch()
        return w

    # ---- Tab 3: Lager / Lasten ---------------------------------------
    def _tab_bc(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        g = QtWidgets.QGroupBox("Knotenauswahl (Klick im Fenster oder Koordinatenfenster)")
        gl = QtWidgets.QVBoxLayout(g)
        self.sel = [QtWidgets.QLineEdit() for _ in range(6)]
        for e, t in zip(self.sel, ["x min", "x max", "y min", "y max", "z min", "z max"]):
            e.setPlaceholderText(t)
            e.setFixedWidth(62)
        gl.addWidget(row("x", self.sel[0], self.sel[1], "y", self.sel[2], self.sel[3]))
        bs = QtWidgets.QPushButton("Auswählen")
        bs.clicked.connect(self.do_select)
        ba = QtWidgets.QPushButton("Alle")
        ba.clicked.connect(self.select_all)
        bn = QtWidgets.QPushButton("Keine")
        bn.clicked.connect(self.select_none)
        gl.addWidget(row("z", self.sel[4], self.sel[5], bs, ba, bn))
        self.ed_selnodes = QtWidgets.QLineEdit()
        self.ed_selnodes.setPlaceholderText("Knoten-Nr., z.B. 0, 4-6")
        bsn = QtWidgets.QPushButton("Nr. auswählen")
        bsn.clicked.connect(self.select_numbers)
        gl.addWidget(row(self.ed_selnodes, bsn))
        self.lbl_sel = QtWidgets.QLabel("0 Knoten ausgewählt")
        gl.addWidget(self.lbl_sel)
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Lager auf Auswahl")
        gl = QtWidgets.QVBoxLayout(g)
        self.cb_dof = [QtWidgets.QCheckBox(n) for n in DOF_NAMES]
        gl.addWidget(row(*self.cb_dof[:3]))
        gl.addWidget(row(*self.cb_dof[3:]))
        self.ed_spring = NumEdit(0.0, 90)
        gl.addWidget(row("Federsteifigkeit [N/m] (0 = starr)", self.ed_spring))
        b1 = QtWidgets.QPushButton("Lager setzen")
        b1.clicked.connect(self.set_support)
        b2 = QtWidgets.QPushButton("Einspannung")
        b2.clicked.connect(lambda: self.set_support(all_dofs=True))
        b3 = QtWidgets.QPushButton("Gelenkig")
        b3.clicked.connect(lambda: self.set_support(pinned=True))
        b4 = QtWidgets.QPushButton("Lager entfernen")
        b4.clicked.connect(self.remove_support)
        gl.addWidget(row(b1, b2, b3, b4))
        b5 = QtWidgets.QPushButton("Nichtlinearität…")
        b5.setToolTip("Ausfall bei Zug/Druck, Schlupf, Reibung und Grenzkraft je Freiheitsgrad")
        b5.clicked.connect(self.support_nonlinear)
        b6 = QtWidgets.QPushButton("Linienlager…")
        b6.setToolTip("Lager entlang der gewählten Knoten, Steifigkeit je Meter")
        b6.clicked.connect(self.add_line_support)
        b7 = QtWidgets.QPushButton("Flächenlager…")
        b7.setToolTip("Bettung auf den Elementen im Feld 'Elemente', Steifigkeit je m²")
        b7.clicked.connect(self.add_surface_support)
        gl.addWidget(row(b5, b6, b7))
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Lasten auf Auswahl → aktiver Lastfall")
        gl = QtWidgets.QVBoxLayout(g)
        self.lbl_active = QtWidgets.QLabel("aktiver Lastfall: LF1")
        self.lbl_active.setStyleSheet("font-weight:bold; color:#0a5")
        gl.addWidget(self.lbl_active)
        self.ld = [NumEdit(0, 70) for _ in range(6)]
        gl.addWidget(row("Fx,Fy,Fz [N]", *self.ld[:3]))
        gl.addWidget(row("Mx,My,Mz [Nm]", *self.ld[3:]))
        self.ld_split = QtWidgets.QCheckBox("Summe gleichmäßig verteilen")
        self.ld_split.setChecked(True)
        bl = QtWidgets.QPushButton("Knotenlast aufbringen")
        bl.clicked.connect(self.add_load)
        gl.addWidget(row(self.ld_split, bl))
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Element- und Flächenlasten → aktiver Lastfall")
        gl = QtWidgets.QVBoxLayout(g)
        self.q = [NumEdit(0, 62) for _ in range(3)]
        self.q2 = [NumEdit(0, 62) for _ in range(3)]
        self.q_local = QtWidgets.QCheckBox("lokal")
        self.q_trap = QtWidgets.QCheckBox("trapezförmig (q2 am Ende)")
        gl.addWidget(row("q [N/m]", *self.q, self.q_local))
        gl.addWidget(row("q2 [N/m]", *self.q2, self.q_trap))
        self.ed_qelems = QtWidgets.QLineEdit()
        self.ed_qelems.setPlaceholderText("Element-Nr. (leer = alle Stäbe / Stäbe an Auswahl)")
        bq = QtWidgets.QPushButton("Streckenlast")
        bq.clicked.connect(self.add_beam_load)
        gl.addWidget(row(self.ed_qelems, bq))
        self.p_face = NumEdit(-1000.0, 80)
        self.p_dir = QtWidgets.QComboBox()
        self.p_dir.addItems(["normal zur Fläche", "global x", "global y", "global z"])
        bf = QtWidgets.QPushButton("Flächenlast auf alle Schalen")
        bf.clicked.connect(self.add_face_load)
        gl.addWidget(row("p [N/m²]", self.p_face, self.p_dir, bf))
        self.ed_dT = NumEdit(0.0, 70)
        self.ed_dTz = NumEdit(0.0, 70)
        bt = QtWidgets.QPushButton("Temperatur auf alle Elemente")
        bt.clicked.connect(self.add_temp_load)
        gl.addWidget(row("ΔT [K]", self.ed_dT, "ΔT oben-unten", self.ed_dTz, bt))
        self.cb_g = QtWidgets.QCheckBox("Eigengewicht (g = 9,81 m/s² in −z) im aktiven Lastfall")
        self.cb_g.toggled.connect(self.toggle_gravity)
        gl.addWidget(self.cb_g)
        lay.addWidget(g)

        bc = QtWidgets.QPushButton("Lasten des aktiven Lastfalls löschen")
        bc.clicked.connect(self.clear_loads)
        bc2 = QtWidgets.QPushButton("Alle Lager löschen")
        bc2.clicked.connect(self.clear_supports)
        lay.addWidget(row(bc, bc2))
        lay.addStretch()
        return w

    # ---- Tab 4: Lastfaelle / Kombinationen ----------------------------
    def _tab_cases(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.addWidget(QtWidgets.QLabel("<b>Lastfälle</b> (Doppelklick = bearbeiten, Auswahl = aktiv)"))
        self.tbl_lc = QtWidgets.QTableWidget(0, 5)
        self.tbl_lc.setHorizontalHeaderLabels(["Name", "Kategorie", "ψ0/ψ1/ψ2", "Lasten", "Beschreibung"])
        self.tbl_lc.horizontalHeader().setStretchLastSection(True)
        self.tbl_lc.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tbl_lc.itemSelectionChanged.connect(self._case_selected)
        self.tbl_lc.itemDoubleClicked.connect(lambda *_: self.edit_case())
        self.tbl_lc.setMaximumHeight(170)
        lay.addWidget(self.tbl_lc)
        b1 = QtWidgets.QPushButton("Neu…"); b1.clicked.connect(self.add_case)
        b2 = QtWidgets.QPushButton("Bearbeiten…"); b2.clicked.connect(self.edit_case)
        b3 = QtWidgets.QPushButton("Löschen"); b3.clicked.connect(self.remove_case)
        b4 = QtWidgets.QPushButton("Kopieren"); b4.clicked.connect(self.copy_case)
        lay.addWidget(row(b1, b2, b4, b3))

        lay.addWidget(QtWidgets.QLabel("<b>Kombinationen</b>"))
        self.tbl_comb = QtWidgets.QTableWidget(0, 4)
        self.tbl_comb.setHorizontalHeaderLabels(["Name", "Typ", "Formel", "Beschreibung"])
        self.tbl_comb.horizontalHeader().setStretchLastSection(True)
        self.tbl_comb.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tbl_comb.itemDoubleClicked.connect(lambda *_: self.edit_combination())
        lay.addWidget(self.tbl_comb, 1)
        b5 = QtWidgets.QPushButton("Automatisch (DIN EN 1990)…"); b5.clicked.connect(self.auto_combinations)
        b6 = QtWidgets.QPushButton("Manuell…"); b6.clicked.connect(self.add_combination)
        b7 = QtWidgets.QPushButton("Löschen"); b7.clicked.connect(self.remove_combination)
        b8 = QtWidgets.QPushButton("Alle löschen"); b8.clicked.connect(self.clear_combinations)
        lay.addWidget(row(b5, b6, b7, b8))

        lay.addWidget(QtWidgets.QLabel("<b>Ermüdungslasten</b> (Lastwechsel zwischen zwei Zuständen)"))
        self.tbl_fatl = QtWidgets.QTableWidget(0, 4)
        self.tbl_fatl.setHorizontalHeaderLabels(["Name", "oben", "unten", "Lastspiele"])
        self.tbl_fatl.horizontalHeader().setStretchLastSection(True)
        self.tbl_fatl.setMaximumHeight(110)
        lay.addWidget(self.tbl_fatl)
        b9 = QtWidgets.QPushButton("Neu…"); b9.clicked.connect(self.add_fatigue_load)
        b10 = QtWidgets.QPushButton("Löschen"); b10.clicked.connect(self.remove_fatigue_load)
        lay.addWidget(row(b9, b10))
        return w

    # ---- Tab 5: Kontakt ----------------------------------------------
    # ------------------------------------------------------------------
    # Register: Stellungen beweglicher Bruecken
    # ------------------------------------------------------------------
    def _tab_stellungen(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)

        g = QtWidgets.QGroupBox("Stellungen des Systems")
        gl = QtWidgets.QVBoxLayout(g)
        self.tbl_stellung = QtWidgets.QTableWidget(0, 6)
        self.tbl_stellung.setHorizontalHeaderLabels(
            ["Stellung", "Winkel [°]", "Lager aus", "Lastfälle", "η", "u max [mm]"])
        self.tbl_stellung.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tbl_stellung.itemSelectionChanged.connect(self._stellung_zeile)
        self.tbl_stellung.setMinimumHeight(150)
        gl.addWidget(self.tbl_stellung)
        b1 = QtWidgets.QPushButton("+ Stellung")
        b1.clicked.connect(self.neue_stellung)
        b2 = QtWidgets.QPushButton("Ändern")
        b2.clicked.connect(self.stellung_aendern)
        b3 = QtWidgets.QPushButton("Entfernen")
        b3.clicked.connect(self.stellung_entfernen)
        gl.addWidget(row(b1, b2, b3))
        b = QtWidgets.QPushButton("▶ Alle Stellungen rechnen")
        b.setObjectName("start")
        b.clicked.connect(self.stellungen_rechnen)
        gl.addWidget(b)
        self.lbl_umh = QtWidgets.QLabel("noch nicht gerechnet")
        self.lbl_umh.setWordWrap(True)
        gl.addWidget(self.lbl_umh)
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("DIN 19704 / ZTV-ING")
        gl = QtWidgets.QVBoxLayout(g)
        b = QtWidgets.QPushButton("Kombinationen nach DIN 19704 bilden")
        b.clicked.connect(self.din19704_bilden)
        gl.addWidget(b)
        self.txt_regelwerk = QtWidgets.QPlainTextEdit()
        self.txt_regelwerk.setReadOnly(True)
        self.txt_regelwerk.setStyleSheet("font-family: monospace; font-size: 11px;")
        self.txt_regelwerk.setMinimumHeight(160)
        self.txt_regelwerk.setPlainText(
            "Die Beiwerte sind Voreinstellungen und gegen die geltende Fassung der "
            "Norm zu bestätigen. Nach dem Bilden stehen hier alle Werte mit ihrem "
            "Zustand und die ZTV-ING-Prüfliste.")
        gl.addWidget(self.txt_regelwerk)
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    def _stellungen_obj(self) -> list:
        if not hasattr(self, "stellungen"):
            self.stellungen = []
        return self.stellungen

    def refresh_stellungen(self):
        if not hasattr(self, "tbl_stellung"):
            return
        u = getattr(self, "umhuellende", None)
        erg = {}
        if u is not None:
            for e in u.reihe.ergebnisse:
                erg[e.stellung.name] = e
        rows = []
        for s in self._stellungen_obj():
            e = erg.get(s.name)
            rows.append([s.name, f"{s.winkel:g}", ", ".join(s.lager_aus) or "–",
                         ", ".join(s.faelle) or "alle",
                         "–" if e is None or e.fehler else f"{e.eta:.3f}",
                         "–" if e is None or e.fehler else f"{e.u_max * 1e3:.3f}"])
        self._fill(self.tbl_stellung, rows)
        if u is not None:
            self.lbl_umh.setText(
                (f"Umhüllende über alle Stellungen: η = {u.eta:.3f}"
                 + (f" – maßgebend {u.massgebende_stellung}"
                    if u.massgebende_stellung else "")
                 + f"; größte Verformung {u.u_max * 1e3:.3f} mm").replace(".", ","))
        elif self._stellungen_obj():
            self.lbl_umh.setText(f"{len(self._stellungen_obj())} Stellungen angelegt – "
                                 "noch nicht gerechnet")

    def _stellung_zeile(self):
        z = self.tbl_stellung.currentRow()
        st = self._stellungen_obj()
        if 0 <= z < len(st):
            self._stellung_gewaehlt(st[z].name)

    def _stellung_gewaehlt(self, name: str):
        """Stellung auswaehlen: Zeile markieren und im Filmstreifen hervorheben."""
        self.gewaehlte_stellung = name
        st = self._stellungen_obj()
        for i, s in enumerate(st):
            if s.name == name and hasattr(self, "tbl_stellung"):
                if self.tbl_stellung.currentRow() != i:
                    self.tbl_stellung.blockSignals(True)
                    self.tbl_stellung.selectRow(i)
                    self.tbl_stellung.blockSignals(False)
                break

    def neue_stellung(self):
        from .dialogs import StellungDialog
        d = StellungDialog(self, None, self.model)
        if d.exec():
            s = d.stellung()
            liste = self._stellungen_obj()
            liste[:] = [x for x in liste if x.name != s.name]
            liste.append(s)
            liste.sort(key=lambda x: x.winkel)
            self.umhuellende = None
            self.info(f"Stellung {s.name} angelegt ({s.beschriftung()})")
            self.refresh_all()

    def stellung_aendern(self):
        from .dialogs import StellungDialog
        z = self.tbl_stellung.currentRow()
        liste = self._stellungen_obj()
        if not (0 <= z < len(liste)):
            return self.error("Zuerst eine Stellung in der Liste wählen")
        d = StellungDialog(self, liste[z], self.model)
        if d.exec():
            liste[z] = d.stellung()
            liste.sort(key=lambda x: x.winkel)
            self.umhuellende = None
            self.refresh_all()

    def stellung_entfernen(self):
        z = self.tbl_stellung.currentRow()
        liste = self._stellungen_obj()
        if not (0 <= z < len(liste)):
            return self.error("Zuerst eine Stellung in der Liste wählen")
        name = liste.pop(z).name
        self.umhuellende = None
        self.info(f"Stellung {name} entfernt")
        self.refresh_all()

    def stellungen_rechnen(self):
        from ..bridges.positions import Stellungsreihe
        liste = self._stellungen_obj()
        if not liste:
            return self.error("Es ist keine Stellung angelegt")
        reihe = Stellungsreihe(self.model, self.model.name)
        for s in liste:
            reihe.add(s)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            umh = reihe.rechnen(kombinationen=True, nachweise=True)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.stellungsreihe = reihe
        self.umhuellende = umh
        for z in reihe.log:
            self.info(z)
        self.info(f"{len(liste)} Stellungen gerechnet: eta = {umh.eta:.3f}"
                  + (f", maßgebend {umh.massgebende_stellung}"
                     if umh.massgebende_stellung else ""))
        self.refresh_all()

    def din19704_bilden(self):
        from ..bridges.din19704 import Regelwerk, pruefliste
        rw = getattr(self, "regelwerk", None) or Regelwerk()
        self.regelwerk = rw
        log: list = []
        namen = rw.kombinationen(self.model, log=log)
        for z in log:
            self.info(z)
        offen = rw.offen()
        text = [rw.bericht(), "", "ZTV-ING, bewegliche Brücken:"]
        for thema, ok, hinweis in pruefliste(getattr(self, "stellungsreihe", None),
                                             self.model):
            text.append(f"  {'erfüllt ' if ok else 'offen   '} {thema}: {hinweis}")
        self.txt_regelwerk.setPlainText("\n".join(text))
        self.info(f"{len(namen)} Kombinationen nach DIN 19704 gebildet"
                  + (f"; {len(offen)} Beiwerte sind noch zu bestätigen" if offen else ""))
        self.refresh_all()

    def _tab_contact(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        g = QtWidgets.QGroupBox("Einseitiges Lager (nur Druck) auf Auswahl")
        gl = QtWidgets.QVBoxLayout(g)
        self.cs_dir = [NumEdit(v, 60) for v in (0, 0, 1)]
        self.cs_gap = NumEdit(0.0, 70)
        self.cs_k = NumEdit(0.0, 90)
        self.cs_mu = NumEdit(0.0, 60)
        gl.addWidget(row("Stützrichtung", *self.cs_dir, "Spalt [m]", self.cs_gap))
        gl.addWidget(row("Steifigkeit [N/m] (0 = starr)", self.cs_k, "μ", self.cs_mu))
        b = QtWidgets.QPushButton("Einseitiges Lager setzen")
        b.clicked.connect(self.add_contact_support)
        gl.addWidget(b)
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Spaltelement Knoten-Knoten (genau 2 Knoten auswählen)")
        gl = QtWidgets.QVBoxLayout(g)
        self.ge_gap = NumEdit(0.0, 70)
        self.ge_k = NumEdit(0.0, 90)
        self.ge_mu = NumEdit(0.0, 60)
        self.ge_dir = [NumEdit(0, 55) for _ in range(3)]
        gl.addWidget(row("Spalt [m]", self.ge_gap, "Steifigkeit", self.ge_k, "μ", self.ge_mu))
        gl.addWidget(row("Richtung a→b (0,0,0 = aus Geometrie)", *self.ge_dir))
        b = QtWidgets.QPushButton("Spaltelement erzeugen")
        b.clicked.connect(self.add_gap_element)
        gl.addWidget(b)
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Kontaktpaar Knoten-Fläche (Slave = Auswahl)")
        gl = QtWidgets.QVBoxLayout(g)
        b = QtWidgets.QPushButton("Kontaktpaar definieren…")
        b.clicked.connect(self.add_contact_pair)
        gl.addWidget(b)
        lay.addWidget(g)

        lay.addWidget(QtWidgets.QLabel("<b>Kontaktdefinitionen</b>"))
        self.tbl_cdef = QtWidgets.QTableWidget(0, 3)
        self.tbl_cdef.setHorizontalHeaderLabels(["Art", "Knoten / Name", "Parameter"])
        self.tbl_cdef.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.tbl_cdef, 1)
        bdel = QtWidgets.QPushButton("Ausgewählte Definition löschen")
        bdel.clicked.connect(self.remove_contact)
        ball = QtWidgets.QPushButton("Alle löschen")
        ball.clicked.connect(self.clear_contact)
        lay.addWidget(row(bdel, ball))
        lay.addWidget(QtWidgets.QLabel(
            "Hinweis: Kontakt macht die Berechnung nichtlinear (Penalty-Verfahren, "
            "Aktivmengen-Iteration).\nKombinationen werden dann einzeln (parallel/Farm) gelöst."))
        return w

    # ---- Tab 6: Nachweise ---------------------------------------------
    def _tab_design(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.addWidget(QtWidgets.QLabel("<b>Stäbe</b> (Doppelklick = Nachweisparameter)"))
        self.tbl_mem = QtWidgets.QTableWidget(0, 7)
        self.tbl_mem.setHorizontalHeaderLabels(["Stab", "Elemente", "L [m]", "Querschnitt", "βy / βz",
                                                "L_LT", "Kerbfall"])
        self.tbl_mem.horizontalHeader().setStretchLastSection(True)
        self.tbl_mem.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tbl_mem.itemDoubleClicked.connect(lambda *_: self.edit_member())
        lay.addWidget(self.tbl_mem, 1)
        b1 = QtWidgets.QPushButton("Automatisch erkennen"); b1.clicked.connect(self.auto_members)
        b2 = QtWidgets.QPushButton("Aus Element-Nr.…"); b2.clicked.connect(self.member_from_elements)
        b3 = QtWidgets.QPushButton("Bearbeiten…"); b3.clicked.connect(self.edit_member)
        b4 = QtWidgets.QPushButton("Löschen"); b4.clicked.connect(self.remove_member)
        lay.addWidget(row(b1, b2, b3, b4))
        self.ed_member_elems = QtWidgets.QLineEdit()
        self.ed_member_elems.setPlaceholderText("Element-Nr. für neuen Stab, z.B. 8-17")
        lay.addWidget(self.ed_member_elems)
        bs = QtWidgets.QPushButton("Einstellungen Nachweise (γM, Verfahren)…")
        bs.clicked.connect(self.design_settings)
        lay.addWidget(bs)
        g = QtWidgets.QGroupBox("Nachweise führen (nach der Berechnung)")
        gl = QtWidgets.QVBoxLayout(g)
        bd = QtWidgets.QPushButton("Nachweise EC3 (Querschnitt + Stabilität)")
        bd.clicked.connect(self.do_design)
        bf = QtWidgets.QPushButton("Ermüdungsnachweis EN 1993-1-9")
        bf.clicked.connect(self.do_fatigue)
        gl.addWidget(row(bd, bf))
        self.lbl_design = QtWidgets.QLabel("noch keine Nachweise")
        self.lbl_design.setWordWrap(True)
        gl.addWidget(self.lbl_design)
        lay.addWidget(g)
        return w

    # ---- Tab 7: Berechnung -------------------------------------------
    def _tab_solve(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.cb_analysis = QtWidgets.QComboBox()
        self.cb_analysis.addItems(["Alle Lastfälle + Kombinationen (+ Umhüllende)",
                                   "Nur aktiver Lastfall",
                                   "Eigenschwingungen (Modalanalyse)",
                                   "Knicken / Beulen (Stabtragwerke)"])
        self.sp_modes = QtWidgets.QSpinBox()
        self.sp_modes.setRange(1, 50); self.sp_modes.setValue(6)
        lay.addWidget(row("Analyse", self.cb_analysis))
        lay.addWidget(row("Anzahl Eigenformen", self.sp_modes))
        self.cb_do_design = QtWidgets.QCheckBox("anschließend Nachweise EC3"); self.cb_do_design.setChecked(True)
        self.cb_do_fat = QtWidgets.QCheckBox("anschließend Ermüdungsnachweis"); self.cb_do_fat.setChecked(True)
        lay.addWidget(row(self.cb_do_design, self.cb_do_fat))

        g = QtWidgets.QGroupBox("Parallelisierung")
        gl = QtWidgets.QVBoxLayout(g)
        self.sp_workers = QtWidgets.QSpinBox()
        self.sp_workers.setRange(1, 256); self.sp_workers.setValue(parallel.settings().workers)
        gl.addWidget(row(f"Prozesse (Kerne, {parallel.cpu_count()} verfügbar)", self.sp_workers))
        self.cb_backend = QtWidgets.QComboBox()
        self.cb_backend.addItems(["lokal (Mehrkern)", "Rechnerfarm"])
        self.ed_farm_host = QtWidgets.QLineEdit(parallel.settings().farm_host)
        self.ed_farm_port = QtWidgets.QLineEdit(str(parallel.settings().farm_port))
        self.ed_farm_port.setFixedWidth(60)
        self.ed_farm_key = QtWidgets.QLineEdit(parallel.settings().farm_key)
        self.ed_farm_key.setEchoMode(QtWidgets.QLineEdit.Password)
        gl.addWidget(row("Backend", self.cb_backend))
        gl.addWidget(row("Farm-Server", self.ed_farm_host, "Port", self.ed_farm_port))
        gl.addWidget(row("Schlüssel", self.ed_farm_key))
        bst = QtWidgets.QPushButton("Farm-Status")
        bst.clicked.connect(self.farm_status)
        bsv = QtWidgets.QPushButton("Lokalen Server + Worker starten")
        bsv.clicked.connect(self.farm_start_local)
        gl.addWidget(row(bst, bsv))
        gl.addWidget(QtWidgets.QLabel("Worker auf anderen Rechnern:  python -m statik3d.farm worker "
                                      "--host <Server> --port 5555 --key <Schlüssel>"))
        lay.addWidget(g)

        bchk = QtWidgets.QPushButton("Modell prüfen")
        bchk.clicked.connect(self.do_check)
        lay.addWidget(bchk)
        self.btn_solve = QtWidgets.QPushButton("BERECHNEN  (F5)")
        self.btn_solve.setStyleSheet("font-weight:bold; padding:8px;")
        self.btn_solve.clicked.connect(lambda: self.do_solve())
        lay.addWidget(self.btn_solve)
        self.txt_summary = QtWidgets.QPlainTextEdit()
        self.txt_summary.setReadOnly(True)
        self.txt_summary.setStyleSheet("font-family: monospace; font-size: 11px;")
        lay.addWidget(self.txt_summary, 1)
        return w

    # ---- Tab 8: Ergebnisse -------------------------------------------
    def _tab_results(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.cb_result = QtWidgets.QComboBox()
        self.cb_result.currentIndexChanged.connect(self.show_results)
        lay.addWidget(row("Ergebnis", self.cb_result))
        self.cb_field = QtWidgets.QComboBox()
        self.cb_field.addItems(FIELDS)
        self.cb_field.currentIndexChanged.connect(self.redraw)
        lay.addWidget(row("Färbung", self.cb_field))
        self.cb_diagram = QtWidgets.QComboBox()
        self.cb_diagram.addItems(DIAGRAMS)
        self.cb_diagram.currentIndexChanged.connect(self.redraw)
        lay.addWidget(row("Schnittgrößenverlauf", self.cb_diagram))
        self.cb_mode = QtWidgets.QComboBox()
        self.cb_mode.currentIndexChanged.connect(self.redraw)
        lay.addWidget(row("Eigenform", self.cb_mode))
        self.sl_scale = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_scale.setRange(0, 100); self.sl_scale.setValue(30)
        self.sl_scale.valueChanged.connect(self.redraw)
        self.lbl_scale = QtWidgets.QLabel("")
        lay.addWidget(row("Überhöhung", self.sl_scale))
        lay.addWidget(self.lbl_scale)
        self.cb_undeformed = QtWidgets.QCheckBox("unverformtes System anzeigen"); self.cb_undeformed.setChecked(True)
        self.cb_undeformed.toggled.connect(self.redraw)
        lay.addWidget(self.cb_undeformed)
        self.txt_res = QtWidgets.QPlainTextEdit()
        self.txt_res.setReadOnly(True)
        self.txt_res.setStyleSheet("font-family: monospace; font-size: 11px;")
        lay.addWidget(self.txt_res, 1)
        b1 = QtWidgets.QPushButton("CSV…"); b1.clicked.connect(self.export_csv)
        b2 = QtWidgets.QPushButton("VTK…"); b2.clicked.connect(self.export_vtk)
        b3 = QtWidgets.QPushButton("Statischer Bericht…"); b3.clicked.connect(self.make_report)
        lay.addWidget(row(b1, b2, b3))
        return w

    # ==================================================================
    # Hilfen
    # ==================================================================
    def info(self, msg):
        self.log.appendPlainText(str(msg))
        self.statusBar().showMessage(str(msg), 5000)

    def error(self, msg):
        QtWidgets.QMessageBox.critical(self, "Fehler", str(msg))
        self.log.appendPlainText("FEHLER: " + str(msg))

    def _fill(self, tbl, rows, header=None):
        """Zeilen in eine Tabelle schreiben - alte QTableWidget oder Datentabelle.

        Die Datentabelle bringt ihre Spalten selbst mit; *header* gilt nur noch
        fuer die einfachen Tabellen des rechten Panels.
        """
        if isinstance(tbl, tab.Datentabelle):
            tbl.setzen(rows)
            return
        if header:
            tbl.setColumnCount(len(header))
            tbl.setHorizontalHeaderLabels(header)
        tbl.setRowCount(len(rows))
        for r, vals in enumerate(rows):
            for c, s in enumerate(vals):
                it = QtWidgets.QTableWidgetItem(str(s))
                it.setFlags(it.flags() & ~QtCore.Qt.ItemIsEditable)
                tbl.setItem(r, c, it)
        tbl.resizeColumnsToContents()

    @staticmethod
    def _tabellenschluessel(tbl):
        """Der Wert der ersten Spalte in der gewaehlten Zeile (oder None)."""
        if isinstance(tbl, tab.Datentabelle):
            i = tbl.view.currentIndex()
            if not i.isValid():
                return None
            w = tbl.filter.data(tbl.filter.index(i.row(), 0), QtCore.Qt.UserRole)
            return None if w is None else str(w)
        r = tbl.currentRow()
        if r < 0 or tbl.item(r, 0) is None:
            return None
        return tbl.item(r, 0).text()

    def _delete_row(self, tbl, mapping: dict):
        key = self._tabellenschluessel(tbl)
        if key is None:
            return self.error("Zuerst eine Zeile wählen")
        if key not in mapping:
            return
        if len(mapping) <= 1:
            return self.error(f"„{key}“ ist der letzte Eintrag und bleibt bestehen")
        self.merken(f"„{key}“ gelöscht")
        del mapping[key]
        self.refresh_all()

    # ---- Tabelle und Ansicht auseinander halten ------------------------
    def _tabelle_element(self, wert):
        """Zeile mit Elementnummer angeklickt: das Element in der Ansicht waehlen."""
        try:
            e = int(float(wert))
        except (TypeError, ValueError):
            return
        if 0 <= e < len(self.model.elements):
            self._set_selection([int(n) for n in self.model.elements[e].nodes])

    def _tabelle_knoten(self, wert):
        """Zeile mit Knotennummer angeklickt."""
        try:
            n = int(float(wert))
        except (TypeError, ValueError):
            return
        if 0 <= n < self.model.nn:
            self._set_selection([n])

    def _tabelle_stab(self, wert):
        """Zeile eines Stabes (Nachweise) angeklickt: alle seine Knoten waehlen."""
        mem = self.model.members.get(str(wert))
        if mem is None:
            return
        kn = {int(n) for i in mem.elements if i < len(self.model.elements)
              for n in self.model.elements[i].nodes}
        self._set_selection(sorted(kn))

    def add_verformungsgrenze(self):
        """Einen Verformungsnachweis (GZG) festlegen."""
        d = VerformungsgrenzeDialog(self, self.model,
                                    knoten=[int(n) for n in self.selection[:2]])
        if not d.exec():
            return
        name, kw = d.result()
        if not name:
            return self.error("Der Nachweis braucht einen Namen")
        if name in self.model.verformungsgrenzen:
            return self.error(f"„{name}“ gibt es schon")
        self.merken(f"Verformungsnachweis {name}")
        try:
            self.model.add_verformungsgrenze(name, **kw)
        except Exception as ex:          # noqa: BLE001
            return self.error(ex)
        self.info(f"Verformungsnachweis „{name}“ angelegt "
                  f"({self.model.verformungsgrenzen[name].bezug()}, Grenze "
                  f"{self.model.verformungsgrenzen[name].grenztext()})")
        self.refresh_all()

    def edit_verformungsgrenze(self):
        key = self._tabellenschluessel(self.tbl_gzg)
        g = self.model.verformungsgrenzen.get(key) if key else None
        if g is None:
            return self.error("Zuerst einen Nachweis in der Tabelle wählen")
        d = VerformungsgrenzeDialog(self, self.model, g)
        if not d.exec():
            return
        name, kw = d.result()
        self.merken(f"Verformungsnachweis {key}")
        del self.model.verformungsgrenzen[key]
        try:
            self.model.add_verformungsgrenze(name or key, **kw)
        except Exception as ex:          # noqa: BLE001
            self.undo()
            return self.error(ex)
        self.info(f"Verformungsnachweis „{name or key}“ geändert")
        self.refresh_all()

    def delete_verformungsgrenze(self):
        key = self._tabellenschluessel(self.tbl_gzg)
        if not key or key not in self.model.verformungsgrenzen:
            return self.error("Zuerst einen Nachweis in der Tabelle wählen")
        self.merken(f"Verformungsnachweis {key} gelöscht")
        del self.model.verformungsgrenzen[key]
        self.info(f"Verformungsnachweis „{key}“ entfernt")
        self.refresh_all()

    def add_beulfeld(self):
        """Die gewählten Flächenelemente zu einem Beulfeld zusammenfassen."""
        sel = set(int(n) for n in self.selection)
        if not sel:
            return self.error("Zuerst die Knoten des Blechfeldes auswählen")
        els = [i for i, e in enumerate(self.model.elements)
               if e.typ.startswith("shell") and set(int(n) for n in e.nodes) <= sel]
        if not els:
            return self.error("In der Auswahl liegt kein vollständiges Flächenelement")
        d = BeulfeldDialog(self, self.model, elemente=els)
        d.ed_name.setText(self._freier_name("Beulfeld", self.model.beulfelder))
        if not d.exec():
            return
        name, kw = d.result()
        if not name:
            return self.error("Das Beulfeld braucht einen Namen")
        if name in self.model.beulfelder:
            return self.error(f"„{name}“ gibt es schon")
        self.merken(f"Beulfeld {name}")
        try:
            bf = self.model.add_beulfeld(name, els, **kw)
        except Exception as ex:          # noqa: BLE001
            return self.error(ex)
        self.info(f"Beulfeld „{name}“ aus {len(bf.elemente)} Elementen angelegt "
                  f"({bf.bezug()}) - es wird ab jetzt bei jeder Berechnung "
                  "nachgewiesen")
        self.refresh_all()

    def edit_beulfeld(self):
        key = self._tabellenschluessel(self.tbl_beul)
        bf = self.model.beulfelder.get(key) if key else None
        if bf is None:
            return self.error("Zuerst ein Beulfeld in der Tabelle wählen")
        d = BeulfeldDialog(self, self.model, bf)
        if not d.exec():
            return
        name, kw = d.result()
        self.merken(f"Beulfeld {key}")
        elemente = list(bf.elemente)
        del self.model.beulfelder[key]
        try:
            self.model.add_beulfeld(name or key, elemente, **kw)
        except Exception as ex:          # noqa: BLE001
            self.undo()
            return self.error(ex)
        self.info(f"Beulfeld „{name or key}“ geändert")
        self.refresh_all()

    # ---- Lasteinleitung (EN 1993-1-5, Abschnitt 6) ---------------------
    def add_lasteinleitung(self):
        """Eine Lasteinleitungsstelle festlegen."""
        kn = int(self.selection[0]) if len(self.selection) else 0
        d = LasteinleitungDialog(self, self.model, knoten=kn)
        d.ed_name.setText(self._freier_name("Lasteinleitung",
                                            self.model.lasteinleitungen))
        if not d.exec():
            return
        name, kw = d.result()
        if not name:
            return self.error("Der Nachweis braucht einen Namen")
        if name in self.model.lasteinleitungen:
            return self.error(f"„{name}“ gibt es schon")
        self.merken(f"Lasteinleitung {name}")
        try:
            le = self.model.add_lasteinleitung(name, **kw)
        except Exception as ex:          # noqa: BLE001
            return self.error(ex)
        self.info(f"Lasteinleitung „{name}“ an {le.bezug()} angelegt")
        self.refresh_all()

    def edit_lasteinleitung(self):
        key = self._tabellenschluessel(self.tbl_le)
        le = self.model.lasteinleitungen.get(key) if key else None
        if le is None:
            return self.error("Zuerst eine Stelle in der Tabelle wählen")
        d = LasteinleitungDialog(self, self.model, le)
        if not d.exec():
            return
        name, kw = d.result()
        self.merken(f"Lasteinleitung {key}")
        del self.model.lasteinleitungen[key]
        try:
            self.model.add_lasteinleitung(name or key, **kw)
        except Exception as ex:          # noqa: BLE001
            self.undo()
            return self.error(ex)
        self.info(f"Lasteinleitung „{name or key}“ geändert")
        self.refresh_all()

    def delete_lasteinleitung(self):
        key = self._tabellenschluessel(self.tbl_le)
        if not key or key not in self.model.lasteinleitungen:
            return self.error("Zuerst eine Stelle in der Tabelle wählen")
        self.merken(f"Lasteinleitung {key} gelöscht")
        del self.model.lasteinleitungen[key]
        self.info(f"Lasteinleitung „{key}“ entfernt")
        self.refresh_all()

    def _tabelle_lasteinleitung(self, wert):
        le = self.model.lasteinleitungen.get(str(wert))
        if le is not None and 0 <= le.knoten < self.model.nn:
            self._set_selection([int(le.knoten)])

    def refresh_lasteinleitungen(self):
        """Die Tabelle der Lasteinleitungsstellen aufbauen."""
        if not hasattr(self, "tbl_le"):
            return
        erg = (getattr(self.analysis, "lasteinleitung", None)
               if self.analysis is not None else None)
        zeilen = []
        for name, le in self.model.lasteinleitungen.items():
            c = erg.stellen.get(name) if erg is not None else None
            w = (c.werte or {}) if c is not None else {}
            zeilen.append([name, le.bezug(), le.typ,
                           (c.F_Ed / 1e3 if c is not None and not c.fehler else ""),
                           (c.F_Rd / 1e3 if c is not None and not c.fehler else ""),
                           (w.get("l_y", 0.0) * 1e3 if w else ""),
                           (w.get("lambda_F", 0.0) if w else ""),
                           (w.get("chi_F", 0.0) if w else ""),
                           (c.util if c is not None else ""),
                           (c.kombination if c is not None else ""),
                           (c.status() if c is not None else "nicht gerechnet")])
        self._fill(self.tbl_le, zeilen)

    def delete_beulfeld(self):
        key = self._tabellenschluessel(self.tbl_beul)
        if not key or key not in self.model.beulfelder:
            return self.error("Zuerst ein Beulfeld in der Tabelle wählen")
        self.merken(f"Beulfeld {key} gelöscht")
        del self.model.beulfelder[key]
        self.info(f"Beulfeld „{key}“ entfernt")
        self.refresh_all()

    # ---------------------------------------------------- Volumenbereiche
    def add_volumenbereich(self):
        """Die gewählten Volumenelemente zu einem Bereich zusammenfassen."""
        sel = set(int(n) for n in self.selection)
        if not sel:
            return self.error("Zuerst die Knoten des Volumenbereichs auswählen")
        els = [i for i, e in enumerate(self.model.elements)
               if e.typ in ("tet4", "tet10", "hex8")
               and set(int(n) for n in e.nodes) <= sel]
        if not els:
            return self.error("In der Auswahl liegt kein vollständiges "
                              "Volumenelement (tet4, tet10 oder hex8)")
        d = VolumenbereichDialog(self, self.model, elemente=els)
        d.ed_name.setText(self._freier_name("Bereich", self.model.volumenbereiche))
        if d.exec() != QtWidgets.QDialog.Accepted:
            return
        name, kw = d.result()
        if not name:
            return self.error("Der Volumenbereich braucht einen Namen")
        if name in self.model.volumenbereiche:
            return self.error(f"„{name}“ gibt es schon")
        self.merken(f"Volumenbereich {name}")
        vb = self.model.add_volumenbereich(name, els, **kw)
        self.info(f"Volumenbereich „{name}“ aus {len(vb.elemente)} Elementen "
                  "angelegt (Nachweis nach 6.2.1(5))")
        self.refresh_all()
        self.tabelle_zeigen("Volumen")

    def edit_volumenbereich(self):
        key = self._tabellenschluessel(self.tbl_vol)
        vb = self.model.volumenbereiche.get(key) if key else None
        if vb is None:
            return self.error("Zuerst einen Volumenbereich in der Tabelle wählen")
        d = VolumenbereichDialog(self, self.model, vb)
        if d.exec() != QtWidgets.QDialog.Accepted:
            return
        name, kw = d.result()
        self.merken(f"Volumenbereich {key}")
        for k, v in kw.items():
            setattr(vb, k, v)
        if name and name != key:
            del self.model.volumenbereiche[key]
            vb.name = name
            self.model.volumenbereiche[name] = vb
        self.info(f"Volumenbereich „{name or key}“ geändert")
        self.refresh_all()

    def delete_volumenbereich(self):
        key = self._tabellenschluessel(self.tbl_vol)
        if not key or key not in self.model.volumenbereiche:
            return self.error("Zuerst einen Volumenbereich in der Tabelle wählen")
        self.merken(f"Volumenbereich {key} gelöscht")
        del self.model.volumenbereiche[key]
        self.info(f"Volumenbereich „{key}“ entfernt")
        self.refresh_all()

    def _tabelle_volumen(self, wert):
        vb = self.model.volumenbereiche.get(str(wert))
        if vb is None:
            return
        kn = {int(n) for i in vb.elemente if i < len(self.model.elements)
              for n in self.model.elements[i].nodes}
        self._set_selection(sorted(kn))

    def refresh_volumen(self):
        """Die Tabelle der Volumenbereiche aufbauen."""
        if not hasattr(self, "tbl_vol"):
            return
        erg = getattr(self.analysis, "volumen", None) if self.analysis is not None else None
        zeilen = []
        for name, vb in self.model.volumenbereiche.items():
            c = erg.bereiche.get(name) if erg is not None else None
            w = (c.werte or {}) if c is not None else {}
            zeilen.append([name, len(vb.elemente),
                           (c.material if c is not None else ""),
                           (c.fy / 1e6 if c is not None and c.fy else ""),
                           (w.get("s1", 0.0) / 1e6 if w else ""),
                           (w.get("s3", 0.0) / 1e6 if w else ""),
                           (w.get("sigma_v", 0.0) / 1e6 if w else ""),
                           (w.get("h", 0.0) if w else ""),
                           (c.util if c is not None and not c.singular else ""),
                           (c.kombination if c is not None else ""),
                           (c.status() if c is not None else "nicht gerechnet")])
        self._fill(self.tbl_vol, zeilen)

    def _tabelle_beulfeld(self, wert):
        bf = self.model.beulfelder.get(str(wert))
        if bf is None:
            return
        kn = {int(n) for i in bf.elemente if i < len(self.model.elements)
              for n in self.model.elements[i].nodes}
        self._set_selection(sorted(kn))

    def refresh_beulfelder(self):
        """Die Tabelle der Beulfelder aufbauen."""
        if not hasattr(self, "tbl_beul"):
            return
        erg = getattr(self.analysis, "beulen", None) if self.analysis is not None else None
        zeilen = []
        for name, bf in self.model.beulfelder.items():
            c = erg.felder.get(name) if erg is not None else None
            w = (c.werte or {}) if c is not None else {}
            zeilen.append([name, len(bf.elemente),
                           (c.a if c is not None else bf.a),
                           (c.b if c is not None else bf.b),
                           ((c.t if c is not None else bf.t) * 1e3),
                           (w.get("sigma_x", 0.0) / 1e6 if w else ""),
                           (w.get("sigma_z", 0.0) / 1e6 if w else ""),
                           (w.get("tau", 0.0) / 1e6 if w else ""),
                           (w.get("lambda_p", 0.0) if w else ""),
                           (c.util if c is not None else ""),
                           (c.kombination if c is not None else ""),
                           (c.status() if c is not None else "nicht gerechnet")])
        self._fill(self.tbl_beul, zeilen)

    def _tabelle_verformung(self, wert):
        """Zeile angeklickt: den Bezug in der Ansicht wählen."""
        g = self.model.verformungsgrenzen.get(str(wert))
        if g is None:
            return
        if g.art == "stab":
            mem = self.model.members.get(g.stab)
            if mem is not None:
                kn = {int(n) for i in mem.elements if i < len(self.model.elements)
                      for n in self.model.elements[i].nodes}
                self._set_selection(sorted(kn))
        elif g.knoten:
            self._set_selection([int(n) for n in g.knoten
                                 if 0 <= int(n) < self.model.nn])

    def refresh_verformungen(self):
        """Die Tabelle der Verformungsnachweise aufbauen."""
        if not hasattr(self, "tbl_gzg"):
            return
        from ..gzg import SITUATIONEN
        erg = getattr(self.analysis, "gzg", None) if self.analysis is not None else None
        zeilen = []
        for name, g in self.model.verformungsgrenzen.items():
            c = erg.checks.get(name) if erg is not None else None
            zeilen.append([name, g.bezug(), g.groesse,
                           SITUATIONEN.get(g.situation, g.situation or "alle GZG"),
                           (c.wert * 1e3 if c is not None and not c.fehler else ""),
                           (c.grenztext if c is not None else g.grenztext()),
                           (c.util if c is not None else ""),
                           (c.kombination if c is not None else ""),
                           (c.stelle if c is not None else ""),
                           (c.status() if c is not None else "nicht gerechnet")])
        self._fill(self.tbl_gzg, zeilen)

    def _tabelle_anschluss(self, wert):
        """Zeile eines Anschlusses angeklickt: seinen Stab in der Ansicht wählen."""
        j = self.model.joints.get(str(wert))
        if j is not None and 0 <= j.elem < len(self.model.elements):
            self._set_selection([int(n) for n in self.model.elements[j.elem].nodes])

    def refresh_joints(self):
        """Die Anschlusstabelle aufbauen - mit Nachweisen, sobald gerechnet wurde."""
        if not hasattr(self, "tbl_joint"):
            return
        m = self.model
        erg = getattr(self.analysis, "joints", None) if self.analysis is not None else None
        from ..joints.anschluss import KURZ
        zeilen = []
        for name, j in m.joints.items():
            e = m.elements[j.elem] if 0 <= j.elem < len(m.elements) else None
            stab = next((n for n, mm in m.members.items() if j.elem in mm.elements), "")
            c = erg.joints.get(name) if erg is not None else None
            g = getattr(c, "gelenk", None) if c is not None else None
            import math as _m
            S = float(getattr(g, "S_j_ini", 0.0) or 0.0) if g is not None else None
            zeilen.append([name, KURZ.get(j.typ, j.typ), j.ort(), stab,
                           (e.sec if e is not None else "") or "",
                           "" if S is None else ("∞" if not _m.isfinite(S) else S / 1e6),
                           getattr(g, "klasse", "") if g is not None else "",
                           (g.M_j_Rd / 1e3 if g is not None and g.M_j_Rd else ""),
                           (c.modelliert if c is not None else ""),
                           c.util if c is not None else "",
                           (c.massgebend or c.fehler) if c is not None else "",
                           c.kombination if c is not None else "",
                           (c.D if c.D else "") if c is not None else "",
                           c.status() if c is not None else "nicht gerechnet"])
        self._fill(self.tbl_joint, zeilen)

    def _tabellen_markieren(self):
        """Umgekehrter Weg: die Auswahl der Ansicht in den Tabellen zeigen."""
        if not hasattr(self, "tbl_beam"):
            return
        sel = {int(n) for n in self.selection}
        m = self.model
        el = []
        if sel and len(m.elements) <= 50000:
            el = [i for i, e in enumerate(m.elements)
                  if {int(n) for n in e.nodes} <= sel]
        self.tbl_beam.markieren(el)
        self.tbl_env.markieren(el)
        self.tbl_react.markieren(sorted(sel))
        self.tbl_contact.markieren(sorted(sel))
        dabei = set(el)
        staebe = [mem.name for mem in m.members.values()
                  if mem.elements and set(mem.elements) <= dabei]
        self.tbl_design.markieren(staebe)
        self.tbl_fat.markieren(staebe)
        if hasattr(self, "tbl_joint"):
            self.tbl_joint.markieren([n for n, j in m.joints.items() if j.elem in dabei])

    def refresh_all(self):
        m = self.model
        for k, e in self.ed_meta.items():
            e.setText(m.meta.get(k, ""))
        self._fill(self.tbl_mat, [[k, v.E / 1e9, v.nu, v.rho, (v.fy or 0.0) / 1e6,
                                   v.grade] for k, v in m.materials.items()])
        self._fill(self.tbl_sec, [[k, v.typ, v.A * 1e4, v.Iy * 1e8, v.Iz * 1e8,
                                   v.It * 1e8, v.Wpl_y * 1e6, v.h * 1e3, v.b * 1e3]
                                  for k, v in m.sections.items()])
        self._fill(self.tbl_shell, [[k, v.t] for k, v in m.shells.items()])
        self.refresh_modelltabellen()
        for cb, keys in ((self.cb_mat, m.materials), (self.cb_sec, m.sections),
                         (self.cb_shell, m.shells),
                         (getattr(self, "cb_assign_sec", None), m.sections),
                         (getattr(self, "cb_assign_mat", None), m.materials)):
            if cb is None:
                continue
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear(); cb.addItems(list(keys))
            if cur in keys:
                cb.setCurrentText(cur)
            cb.blockSignals(False)
        self._refresh_status()
        self.refresh_cases()
        self.refresh_contact()
        self.refresh_members()
        self.refresh_joints()
        self.refresh_verformungen()
        self.refresh_beulfelder()
        self.refresh_volumen()
        self.refresh_lasteinleitungen()
        self.refresh_lasteinleitungen()
        self.refresh_stellungen()
        self._refresh_kopf()
        self._refresh_baum()
        self.redraw()

    def refresh_cases(self):
        m = self.model
        rows = []
        for lc in m.load_cases.values():
            p = lc.psi_factors
            rows.append([lc.name, lc.category, f"{p[0]:g}/{p[1]:g}/{p[2]:g}", lc.n_loads,
                         lc.description + (f"  [Gruppe {lc.exclusive_group}]" if lc.exclusive_group else "")])
        self.tbl_lc.blockSignals(True)
        self._fill(self.tbl_lc, rows)
        names = list(m.load_cases)
        if m.active_case in names:
            self.tbl_lc.selectRow(names.index(m.active_case))
        self.tbl_lc.blockSignals(False)
        self.lbl_active.setText(f"aktiver Lastfall: {m.active_case} ({m.case().category})")
        self.cb_g.blockSignals(True)
        self.cb_g.setChecked(bool(np.any(m.gravity)))
        self.cb_g.blockSignals(False)
        self._fill(self.tbl_comb, [[c.name, c.typ, c.formula(), c.description]
                                   for c in m.combinations.values()])
        self._fill(self.tbl_fatl, [[f.name, f.case_max, f.case_min or "0", f"{f.cycles:g}"]
                                   for f in m.fatigue_loads.values()])

    def refresh_contact(self):
        m = self.model
        rows = []
        for c in m.contact_supports:
            rows.append(["Einseitiges Lager", c.node, f"Richtung {c.direction}, Spalt {c.gap:g}, "
                         f"k {c.stiffness:g}, μ {c.mu:g}"])
        for g in m.gap_elements:
            rows.append(["Spaltelement", f"{g.node_a} - {g.node_b}",
                         f"Spalt {g.gap:g}, k {g.stiffness:g}, μ {g.mu:g}"])
        for c in m.contact_pairs:
            rows.append(["Kontaktpaar", c.name, f"{len(c.slave_nodes)} Slave-Knoten, "
                         f"{len(c.master_elements)} Master-Elemente, μ {c.mu:g}"])
        self._fill(self.tbl_cdef, rows)

    def refresh_members(self):
        m = self.model
        rows = []
        for mem in m.members.values():
            e0 = m.elements[mem.elements[0]] if mem.elements else None
            rows.append([mem.name, f"{mem.elements[0]}-{mem.elements[-1]}" if mem.elements else "",
                         f"{m.member_length(mem):.2f}", e0.sec if e0 else "",
                         f"{mem.beta_y:g} / {mem.beta_z:g}",
                         f"{mem.L_LT:g}" if mem.L_LT else "L",
                         f"{mem.detail_category/1e6:.0f}" if mem.detail_category else "-"])
        self._fill(self.tbl_mem, rows)

    # ---- Modell ------------------------------------------------------
    def add_material(self):
        d = MaterialDialog(self)
        if d.exec():
            self.model.add_material(d.result_material())
            self.refresh_all()

    def add_section(self):
        d = SectionDialog(self)
        if d.exec():
            try:
                self.model.add_section(d.result_section())
            except Exception as ex:
                return self.error(ex)
            self.refresh_all()

    def add_shell_prop(self):
        t = self.ed_t.value()
        if t > 0:
            self.model.add_shell_prop(ShellProp(f"t = {t*1000:g} mm", t))
            self.refresh_all()

    def _elements_from_text(self, text: str) -> list[int]:
        text = text.strip()
        if text:
            return parse_int_list(text, len(self.model.elements))
        if len(self.selection):
            sel = set(int(n) for n in self.selection)
            return [i for i, e in enumerate(self.model.elements) if sel.issuperset(e.nodes)]
        return []

    def assign_props(self):
        els = self._elements_from_text(self.ed_elist.text())
        if not els:
            return self.error("Keine Elemente angegeben (Nr. eintragen oder alle Knoten der Elemente auswählen)")
        for i in els:
            e = self.model.elements[i]
            if e.typ in ("beam", "truss"):
                e.sec = self.cb_assign_sec.currentText()
            e.mat = self.cb_assign_mat.currentText()
        self.info(f"{len(els)} Elemente geändert")
        self.refresh_all()

    def set_hinges(self):
        els = self._elements_from_text(self.ed_elist.text())
        if not els:
            return self.error("Keine Elemente angegeben")
        k = self.ed_hinge.currentIndex()
        h = {0: [], 1: [4, 5], 2: [10, 11], 3: [4, 5, 10, 11], 4: [3, 4, 5, 9, 10, 11]}[k]
        for i in els:
            if self.model.elements[i].typ == "beam":
                self.model.elements[i].hinges = list(h)
        self.info(f"Gelenke an {len(els)} Elementen gesetzt")
        self.refresh_all()

    # ---- Netz --------------------------------------------------------
    def _mat(self):
        return self.cb_mat.currentText()

    def make_beams(self):
        try:
            e0 = len(self.model.elements)
            ids = mesher.line_of_beams(self.model, self._mat(), self.cb_sec.currentText(),
                                       [e.value() for e in self.beam_p1],
                                       [e.value() for e in self.beam_p2],
                                       self.beam_n.value())
            if self.beam_truss.isChecked():
                for e in self.model.elements[e0:]:
                    e.typ = "truss"
            self.model.add_member(f"S{len(self.model.members)+1}", list(range(e0, len(self.model.elements))))
            mesher.merge_nodes(self.model)
            self.refresh_all()
        except Exception as ex:
            self.error(str(ex))

    def make_plate(self):
        try:
            mesher.grid_plate(self.model, self._mat(), self.cb_shell.currentText(),
                              self.pl[0].value(), self.pl[1].value(),
                              self.pn[0].value(), self.pn[1].value(),
                              origin=(0, 0, self.pl[2].value()),
                              quad=self.pl_quad.isChecked())
            mesher.merge_nodes(self.model)
            self.refresh_all()
        except Exception as ex:
            self.error(str(ex))

    def make_box(self):
        try:
            mesher.grid_box(self.model, self._mat(),
                            *[e.value() for e in self.bl],
                            *[s.value() for s in self.bn],
                            origin=tuple(e.value() for e in self.bo),
                            typ=self.b_typ.currentText())
            mesher.merge_nodes(self.model)
            self.refresh_all()
        except Exception as ex:
            self.error(str(ex))

    def import_file(self):
        try:
            from .. import importers
            filt = importers.file_filter()
        except Exception:
            filt = "Alle Dateien (*)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Importieren", "", filt)
        if not path:
            return
        d = ImportDialog(self, path, self.model)
        if not d.exec():
            return
        opt = d.options()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            from .. import importers
            msgs: list[str] = []
            target = self.model if d.append.isChecked() else None
            if target is None:
                self._protokoll_neu(f"Import: {path}")
            m = importers.import_file(path, model=target, log=msgs, **opt)
            for s in msgs:
                self.log.appendPlainText("  " + s)
            self.model = m
            self.__init_defaults()
            if d.members.isChecked() and not m.members:
                m.auto_members()
            self.analysis = None
            self.results = None
            self.selection = np.array([], dtype=int)
            self.refresh_all()
            self.zoom_alles()
            self.info(f"Import: {m.nn} Knoten, {len(m.elements)} Elemente, "
                      f"{len(m.load_cases)} Lastfälle, {len(m.members)} Stäbe")
        except Exception as ex:
            self.log.appendPlainText(traceback.format_exc())
            self.error(f"{ex}")
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def do_merge(self):
        n = mesher.merge_nodes(self.model)
        self.info(f"{n} doppelte Knoten entfernt")
        self.refresh_all()

    def clear_mesh(self):
        old = self.model
        self.model = Model(old.name)
        self.model.materials = dict(old.materials)
        self.model.sections = dict(old.sections)
        self.model.shells = dict(old.shells)
        self.model.meta = dict(old.meta)
        self.__init_defaults()
        self.analysis = None
        self.results = None
        self.selection = np.array([], dtype=int)
        self.refresh_all()

    # ---- Rueckgaengig / Wiederholen ----------------------------------
    #: so viele Schritte werden vorgehalten
    SCHRITTE = 50

    def _undo_init(self):
        self._undo: list = []
        self._redo: list = []

    def merken(self, was: str):
        """Den Stand vor einer Aenderung sichern.

        Gesichert wird das ganze Modell - das ist einfach, verlaesslich und
        macht jede Aenderung umkehrbar, auch Netz, Lasten und Lager. Die Liste
        ist auf SCHRITTE begrenzt, damit grosse Modelle den Speicher nicht
        auffressen.
        """
        if not hasattr(self, "_undo"):
            self._undo_init()
        self._undo.append((was, self.model.copy()))
        del self._undo[:-self.SCHRITTE]
        self._redo.clear()
        self._undo_knoepfe()

    def undo(self):
        if not getattr(self, "_undo", None):
            return self.info("Nichts rückgängig zu machen")
        was, m = self._undo.pop()
        self._redo.append((was, self.model.copy()))
        self._modell_setzen(m)
        self.info(f"Rückgängig: {was}")

    def redo(self):
        if not getattr(self, "_redo", None):
            return self.info("Nichts zu wiederholen")
        was, m = self._redo.pop()
        self._undo.append((was, self.model.copy()))
        self._modell_setzen(m)
        self.info(f"Wiederholt: {was}")

    def _modell_setzen(self, m):
        self.model = m
        self.analysis = None
        self.results = None
        self.selection = np.array([], dtype=int)
        self._undo_knoepfe()
        self.refresh_all()

    def _undo_knoepfe(self):
        if not hasattr(self, "act_undo"):
            return
        u, r = getattr(self, "_undo", []), getattr(self, "_redo", [])
        self.act_undo.setEnabled(bool(u))
        self.act_redo.setEnabled(bool(r))
        self.act_undo.setToolTip(f"Rückgängig: {u[-1][0]}" if u
                                 else "Nichts rückgängig zu machen")
        self.act_redo.setToolTip(f"Wiederholen: {r[-1][0]}" if r
                                 else "Nichts zu wiederholen")

    # ---- Koordinatensystem, Arbeitsebene, Fang -----------------------
    def _ks_init(self):
        self.ks_liste = {"global": ks.Koordinatensystem.global_ks()}
        self.ks_aktiv = "global"
        self.arbeitsebene = ks.Arbeitsebene(self.ks_liste["global"], "xy", 0.0, 0.5)
        self.fang_an = True
        self.fang_arten = list(ks.FANGARTEN)

    def ks(self) -> "ks.Koordinatensystem":
        return self.ks_liste.get(self.ks_aktiv) or self.ks_liste["global"]

    def ks_neu(self):
        """Ein Koordinatensystem über drei Punkte oder Drehwinkel anlegen."""
        m = msk.Maske("Koordinatensystem", [
            msk.Feld("name", "Name", "text", f"KS{len(self.ks_liste)}", breite=110),
            msk.Feld("art", "Art", "wahl", "kartesisch", list(ks.ARTEN)),
            msk.Feld("x", "Ursprung x [m]"), msk.Feld("y", "y [m]"), msk.Feld("z", "z [m]"),
            msk.Feld("a", "Drehung um x [°]"), msk.Feld("b", "um y [°]"),
            msk.Feld("c", "um z [°]")],
            knopf="Anlegen",
            hinweis="Ursprung und Drehwinkel eintragen – oder drei Knoten in der "
                    "Ansicht wählen und „Aus Auswahl“ im Ribbon.")
        m.angewendet.connect(self._ks_anlegen)
        self.maske_erzeugen(m)

    def _ks_anlegen(self, w: dict):
        name = (w.get("name") or "KS").strip()
        k = ks.Koordinatensystem.aus_winkeln(name, (w["x"], w["y"], w["z"]),
                                             w["a"], w["b"], w["c"], w.get("art"))
        self.ks_liste[name] = k
        self.ks_aktiv = name
        self.arbeitsebene.ks = k
        self.info(f"Koordinatensystem {k.beschreibung()}")
        self._refresh_status()

    def ks_aus_auswahl(self):
        """Aus drei gewählten Knoten ein Koordinatensystem machen."""
        if len(self.selection) < 3:
            return self.error("Drei Knoten wählen: Ursprung, x-Richtung, xy-Ebene")
        p = [self.model.nodes[int(i)] for i in self.selection[:3]]
        name = f"KS{len(self.ks_liste)}"
        try:
            k = ks.Koordinatensystem.aus_punkten(name, p[0], p[1], p[2])
        except ValueError:
            return self.error("Die drei Knoten liegen auf einer Geraden – so lässt "
                              "sich keine Ebene aufspannen. Einen Knoten außerhalb "
                              "der Geraden wählen.")
        self.ks_liste[name] = k
        self.ks_aktiv = name
        self.arbeitsebene.ks = k
        self.info(f"Koordinatensystem {k.beschreibung()}")
        self._refresh_status()

    def ks_waehlen(self, name: str):
        if name in self.ks_liste:
            self.ks_aktiv = name
            self.arbeitsebene.ks = self.ks_liste[name]
            self._refresh_status()

    def arbeitsebene_setzen(self, ebene: str = None, versatz: float = None,
                            raster: float = None):
        if ebene:
            self.arbeitsebene.ebene = ebene
        if versatz is not None:
            self.arbeitsebene.versatz = float(versatz)
        if raster is not None:
            self.arbeitsebene.raster = float(raster)
        self.info("Arbeitsebene: " + self.arbeitsebene.beschreibung())
        self._refresh_status()

    def fang_umschalten(self, an: bool):
        self.fang_an = bool(an)
        self._refresh_status()

    def fangart_umschalten(self, art: str, an: bool):
        """Eine einzelne Fangart zu- oder abschalten."""
        arten = [x for x in self.fang_arten if x != art]
        if an:
            arten = [x for x in ks.FANGARTEN if x == art or x in arten]
        self.fang_arten = arten
        if not arten and self.fang_an:
            # Ohne Fangart faengt nichts - dann ist der Fang aus, und das
            # soll auch dranstehen.
            self.act_fang.setChecked(False)
        self._refresh_status()

    # ---- Linien ------------------------------------------------------
    def maske_linie(self):
        """Linie anlegen: Art wählen, Knoten anklicken oder Werte eintragen."""
        arten = [("polyline", "Polylinie (2+ Knoten)"), ("arc", "Bogen (3 Knoten)"),
                 ("circle", "Kreis (Mitte + Radius)"), ("spline", "Spline (3+ Knoten)"),
                 ("parabola", "Parabel (Anfang, Ende, Stich)")]
        m = msk.Maske("Linie", [
            # Vorgabe ist die gerade Linie - sie ist der haeufigste Fall; ein
            # Bogen war als Vorgabe eine Falle.
            msk.Feld("art", "Art", "wahl", "Polylinie (2+ Knoten)",
                     [t for _k, t in arten]),
            msk.Feld("mat", "Material", "wahl", self._erst(self.model.materials),
                     list(self.model.materials)),
            msk.Feld("sec", "Querschnitt", "wahl", self._erst(self.model.sections),
                     list(self.model.sections)),
            msk.Feld("teilung", "Teilung", "ganz", 8, breite=60),
            msk.Feld("radius", "Radius / Stich [m]", "zahl", 2.0),
            msk.Feld("staebe", "Stäbe daraus erzeugen", "haken", True)],
            knoten=3, knopf="Linie anlegen")
        m._arten = dict((t, k) for k, t in arten)
        m.angewendet.connect(self._maske_linie_anlegen)
        self.maske_erzeugen(m)

    def _maske_linie_anlegen(self, w: dict):
        from .. import geometry as geo
        maske = self.maskenrand.maske
        art = getattr(maske, "_arten", {}).get(w.get("art"), "polyline")
        kn = list(w.get("knoten") or [])
        noetig = {"polyline": 2, "arc": 3, "circle": 1, "spline": 3, "parabola": 2}[art]
        if len(kn) < noetig:
            return self.error(f"{noetig} Knoten in der Ansicht anklicken")
        self.merken(f"Linie ({art})")
        name = f"L{len(self.model.lines) + 1}"
        teilung = max(int(w.get("teilung") or 8), 1)
        try:
            if art == "circle":
                p = self.model.nodes[kn[0]]
                _u, _v2, n = self.arbeitsebene.achsen()
                self.model.add_line(name, [kn[0]], "circle", mitte=tuple(float(x) for x in p),
                                    radius=float(w.get("radius") or 1.0),
                                    normale=tuple(float(x) for x in n), teilung=teilung)
            elif art == "parabola":
                a, e = self.model.nodes[kn[0]], self.model.nodes[kn[1]]
                _u, _v2, n = self.arbeitsebene.achsen()
                self.model.add_line(name, kn[:2], "parabola",
                                    anfang=tuple(float(x) for x in a),
                                    ende=tuple(float(x) for x in e),
                                    stich=float(w.get("radius") or 0.0),
                                    richtung=tuple(float(x) for x in n), teilung=teilung)
            else:
                self.model.add_line(name, kn[:max(noetig, len(kn))], art, teilung=teilung)
            ln = self.model.lines[name]
            laenge = ln.laenge(self.model)
            n_el = 0
            if w.get("staebe"):
                n_el = len(self.model.line_to_beams(name, w["mat"], w["sec"], teilung))
        except (geo.GeometrieFehler, ValueError, KeyError) as ex:
            self._undo.pop()
            return self.error(str(ex))
        self.info(f"{ln.kurve(self.model).beschreibung()}: {name}, "
                  f"L = {laenge:.3f} m"
                  + (f", {n_el} Stäbe erzeugt" if n_el else ""))
        if maske is not None:
            maske.auswahl_leeren()
        self.refresh_all()

    # ---- Nicht-modale Masken („Maske oder Klick“) --------------------
    def maske_knoten(self):
        """Knoten anlegen: Koordinaten tippen oder in der Ansicht klicken."""
        m = msk.Maske("Knoten", [
            msk.Feld("x", "x [m]"), msk.Feld("y", "y [m]"), msk.Feld("z", "z [m]")],
            hinweis="Koordinaten eintragen und „Anlegen“ – die Maske bleibt offen.",
            knopf="Anlegen")
        m.angewendet.connect(self._maske_knoten_anlegen)
        self.maske_erzeugen(m)

    def _maske_knoten_anlegen(self, w: dict):
        i = self.model.add_node(w["x"], w["y"], w["z"])
        self.info(f"Knoten {i + 1} angelegt bei "
                  f"({w['x']:g}, {w['y']:g}, {w['z']:g}) m")
        self.refresh_all()

    def maske_stab(self):
        """Stab anlegen: zwei Knoten anklicken oder ihre Nummern eintragen."""
        m = msk.Maske("Stab", [
            msk.Feld("mat", "Material", "wahl", self._erst(self.model.materials),
                     list(self.model.materials)),
            msk.Feld("sec", "Querschnitt", "wahl", self._erst(self.model.sections),
                     list(self.model.sections)),
            msk.Feld("fachwerk", "Fachwerkstab (nur N)", "haken", False)],
            knoten=2, knopf="Stab anlegen")
        m.angewendet.connect(self._maske_stab_anlegen)
        self.maske_erzeugen(m)

    def _maske_stab_anlegen(self, w: dict):
        kn = w["knoten"]
        if len(kn) < 2:
            return self.error("Zwei Knoten in der Ansicht anklicken")
        typ = "truss" if w.get("fachwerk") else "beam"
        self.model.add_element(typ, [kn[0], kn[1]], w["mat"], w["sec"])
        self.info(f"{'Fachwerkstab' if typ == 'truss' else 'Stab'} "
                  f"{kn[0] + 1}–{kn[1] + 1} mit {w['sec']} angelegt")
        if self.maskenrand.maske is not None:
            self.maskenrand.maske.auswahl_leeren()
        self.refresh_all()

    def maske_schale(self):
        """Schale anlegen: drei oder vier Knoten anklicken."""
        m = msk.Maske("Schale", [
            msk.Feld("mat", "Material", "wahl", self._erst(self.model.materials),
                     list(self.model.materials)),
            msk.Feld("dicke", "Dicke", "wahl", self._erst(self.model.shells),
                     list(self.model.shells)),
            msk.Feld("vier", "Viereck (4 Knoten)", "haken", True)],
            knoten=4, knopf="Schale anlegen")
        m.angewendet.connect(self._maske_schale_anlegen)
        self.maske_erzeugen(m)

    def _maske_schale_anlegen(self, w: dict):
        kn = w["knoten"]
        n = 4 if w.get("vier") else 3
        if len(kn) < n:
            return self.error(f"{n} Knoten in der Ansicht anklicken")
        self.model.add_element("shell4" if n == 4 else "shell3", kn[:n],
                               w["mat"], w["dicke"])
        self.info(f"Schale aus {n} Knoten angelegt")
        if self.maskenrand.maske is not None:
            self.maskenrand.maske.auswahl_leeren()
        self.refresh_all()

    def maske_lager(self):
        """Lager setzen: Knoten anklicken, Freiheitsgrade in der Maske."""
        felder = [msk.Feld(f"d{i}", DOF_NAMES[i], "haken", i < 3) for i in range(6)]
        m = msk.Maske("Lager", felder, knoten=0, knopf="Lager setzen",
                      hinweis="Knoten in der Ansicht wählen, Freiheitsgrade "
                              "ankreuzen und „Lager setzen“.")
        m.angewendet.connect(self._maske_lager_setzen)
        self.maske_erzeugen(m)

    def _maske_lager_setzen(self, w: dict):
        if not len(self.selection):
            return self.error("Zuerst Knoten in der Ansicht wählen")
        dofs = [i for i in range(6) if w.get(f"d{i}")]
        if not dofs:
            return self.error("Kein Freiheitsgrad angekreuzt")
        for i in self.selection:
            self.model.support(int(i), dofs)
        self.info(f"Lager an {len(self.selection)} Knoten: "
                  + ", ".join(DOF_NAMES[d] for d in dofs))
        self.refresh_all()

    def maske_knotenlast(self):
        """Knotenlast aufbringen: Knoten wählen, Kräfte in der Maske."""
        felder = [msk.Feld(k, f"{k} [kN{'m' if k.startswith('M') else ''}]")
                  for k in ("Fx", "Fy", "Fz", "Mx", "My", "Mz")]
        felder.append(msk.Feld("fall", "Lastfall", "wahl", self.model.active_case,
                               list(self.model.load_cases)))
        m = msk.Maske("Knotenlast", felder, knoten=0, knopf="Last aufbringen",
                      hinweis="Knoten in der Ansicht wählen, Werte eintragen "
                              "und „Last aufbringen“.")
        m.angewendet.connect(self._maske_last_aufbringen)
        self.maske_erzeugen(m)

    def _maske_last_aufbringen(self, w: dict):
        if not len(self.selection):
            return self.error("Zuerst Knoten in der Ansicht wählen")
        werte = {k: w.get(k, 0.0) * 1e3 for k in ("Fx", "Fy", "Fz", "Mx", "My", "Mz")}
        if not any(werte.values()):
            return self.error("Alle Werte sind null")
        for i in self.selection:
            self.model.load_node(int(i), case=w.get("fall") or None, **werte)
        self.info(f"Knotenlast auf {len(self.selection)} Knoten "
                  f"im Lastfall {w.get('fall')}")
        self.refresh_all()

    # ---- Linien-, Flaechen-, Temperatur- und Zwangslasten ------------
    def _lastfallfeld(self):
        return msk.Feld("fall", "Lastfall", "wahl", self.model.active_case,
                        list(self.model.load_cases))

    def maske_linienlast(self):
        """Linienlast auf Staebe oder Linien: gleichmaessig, trapezfoermig,
        abschnittsweise."""
        felder = [msk.Feld("qx", "q_x [kN/m]"), msk.Feld("qy", "q_y [kN/m]"),
                  msk.Feld("qz", "q_z [kN/m]", wert=-10.0),
                  msk.Feld("trapez", "trapezförmig (q2 am Ende)", "haken", False),
                  msk.Feld("q2x", "q2_x [kN/m]"), msk.Feld("q2y", "q2_y [kN/m]"),
                  msk.Feld("q2z", "q2_z [kN/m]"),
                  msk.Feld("system", "Bezug", "wahl", "global", ["global", "lokal (Stab)"]),
                  msk.Feld("von", "Abschnitt von [m]", wert=0.0),
                  msk.Feld("bis", "bis [m] (0 = Ende)", wert=0.0),
                  self._lastfallfeld()]
        m = msk.Maske("Linienlast", felder, knopf="Last aufbringen",
                      hinweis="Stäbe oder Linien in der Ansicht wählen (Auswahlart „Stab“ "
                              "oder „Linie“), Werte eintragen, „Last aufbringen“. q gilt "
                              "bei „von“, q2 bei „bis“; von/bis in Metern vom Anfang.")
        m.angewendet.connect(self._linienlast_aufbringen)
        self.maske_erzeugen(m)

    def _linienlast_aufbringen(self, w: dict):
        ziele = [(n, "stab") for n in self.sel_staebe] + [(n, "linie") for n in self.sel_linien]
        if not ziele:
            return self.error("Zuerst Stäbe oder Linien in der Ansicht wählen "
                              "(Auswahlart „Stab“ oder „Linie“)")
        q = [float(w.get(k, 0.0) or 0.0) * 1e3 for k in ("qx", "qy", "qz")]
        q2 = ([float(w.get(k, 0.0) or 0.0) * 1e3 for k in ("q2x", "q2y", "q2z")]
              if w.get("trapez") else None)
        if not any(q) and not (q2 and any(q2)):
            return self.error("Alle Werte sind null")
        von = float(w.get("von", 0.0) or 0.0)
        bis = float(w.get("bis", 0.0) or 0.0) or None
        system = "local" if str(w.get("system", "")).startswith("lokal") else "global"
        fall = w.get("fall") or None
        self.merken("Linienlast")
        for name, art in ziele:
            self.model.add_linienlast(name, q, art=art, q2=q2, system=system,
                                      von=von, bis=bis, case=fall)
        n = self.model.lasten_verteilen()
        self.analysis = None
        self.results = None
        self.info(f"Linienlast auf {len(ziele)} Objekte im Lastfall "
                  f"{fall or self.model.active_case} ({n} Elementlasten)")
        self.refresh_all()

    #: Richtungen einer Flaechenlast in der Maske
    LASTRICHTUNGEN = ["senkrecht zur Fläche (Druck)", "global x", "global y", "global z",
                      "global −x", "global −y", "global −z"]
    LASTRICHTUNG_VEKTOR = {"global x": (1, 0, 0), "global y": (0, 1, 0), "global z": (0, 0, 1),
                           "global −x": (-1, 0, 0), "global −y": (0, -1, 0),
                           "global −z": (0, 0, -1)}

    def maske_flaechenlast(self):
        """Flaechenlast auf Flaechen oder Volumen: gleichmaessig oder linear."""
        felder = [msk.Feld("p", "p [kN/m²]", wert=5.0,
                           hinweis="positiv drückt in den Körper (Druck)"),
                  msk.Feld("richtung", "Richtung", "wahl", self.LASTRICHTUNGEN[0],
                           list(self.LASTRICHTUNGEN)),
                  msk.Feld("projiziert", "auf die Projektion (Schnee, Wind)", "haken", False),
                  msk.Feld("verlauf", "Verlauf", "wahl", "gleichmäßig",
                           ["gleichmäßig", "linear von Punkt A nach B"]),
                  msk.Feld("p2", "p bei B [kN/m²]", wert=0.0),
                  msk.Feld("ax", "A x [m]"), msk.Feld("ay", "A y [m]"), msk.Feld("az", "A z [m]"),
                  msk.Feld("bx", "B x [m]"), msk.Feld("by", "B y [m]"), msk.Feld("bz", "B z [m]"),
                  self._lastfallfeld()]
        m = msk.Maske("Flächenlast", felder, knopf="Last aufbringen",
                      hinweis="Flächen oder Volumen in der Ansicht wählen (Auswahlart "
                              "„Fläche“ oder „Volumen“). Die Last hängt am Objekt und "
                              "wirkt auf dem Netz, auch nach dem Neuvernetzen. Linear: "
                              "p bei A, „p bei B“ bei B, dazwischen und darüber hinaus "
                              "linear (Wasserdruck, Erddruck).")
        m.angewendet.connect(self._flaechenlast_aufbringen)
        self.maske_erzeugen(m)

    def _flaechenlast_aufbringen(self, w: dict):
        ziele = [(n, "flaeche") for n in self.sel_flaechen] + [(n, "koerper") for n in self.sel_koerper]
        if not ziele:
            return self.error("Zuerst Flächen oder Volumen in der Ansicht wählen "
                              "(Auswahlart „Fläche“ oder „Volumen“)")
        p = float(w.get("p", 0.0) or 0.0) * 1e3
        richtung = self.LASTRICHTUNG_VEKTOR.get(str(w.get("richtung", "")))
        verlauf = None
        if str(w.get("verlauf", "")).startswith("linear"):
            A = [float(w.get(k, 0.0) or 0.0) for k in ("ax", "ay", "az")]
            B = [float(w.get(k, 0.0) or 0.0) for k in ("bx", "by", "bz")]
            if np.allclose(A, B):
                return self.error("Die Punkte A und B liegen aufeinander - so gibt es "
                                  "keinen Verlauf")
            verlauf = {"art": "linear",
                       "punkte": [[*A, p], [*B, float(w.get("p2", 0.0) or 0.0) * 1e3]]}
        elif not p:
            return self.error("p ist null")
        fall = w.get("fall") or None
        self.merken("Flächenlast")
        for name, art in ziele:
            self.model.add_geometrielast(name, p, art=art, richtung=richtung, case=fall,
                                         projiziert=bool(w.get("projiziert")),
                                         verlauf=verlauf)
        n = self.model.lasten_verteilen()
        self.analysis = None
        self.results = None
        self.info(f"Flächenlast auf {len(ziele)} Objekte im Lastfall "
                  f"{fall or self.model.active_case}"
                  + (f" ({n} Elementlasten)" if n else " - wirkt, sobald vernetzt ist"))
        self.refresh_all()

    def maske_temperaturlast(self):
        """Temperaturaenderung auf Staebe, Flaechen oder Volumen."""
        felder = [msk.Feld("dT", "ΔT [K]", wert=20.0),
                  msk.Feld("dTz", "ΔT_z oben − unten [K] (Stäbe)", wert=0.0),
                  msk.Feld("alle", "alle Elemente des Modells", "haken", False),
                  self._lastfallfeld()]
        m = msk.Maske("Temperaturlast", felder, knopf="Last aufbringen",
                      hinweis="Stäbe, Flächen oder Volumen in der Ansicht wählen. Bei "
                              "Flächen und Volumen hängt die Temperatur am Objekt und "
                              "wirkt auf allen Elementen, auch nach dem Neuvernetzen.")
        m.angewendet.connect(self._temperaturlast_aufbringen)
        self.maske_erzeugen(m)

    def _temperaturlast_aufbringen(self, w: dict):
        dT = float(w.get("dT", 0.0) or 0.0)
        dTz = float(w.get("dTz", 0.0) or 0.0)
        if not dT and not dTz:
            return self.error("ΔT ist null")
        fall = w.get("fall") or None
        m = self.model
        n_el = 0
        objekte = 0
        self.merken("Temperaturlast")
        if w.get("alle"):
            for i in range(len(m.elements)):
                m.load_temp(i, dT, dTz, case=fall)
                n_el += 1
        else:
            for name in self.sel_staebe:
                mem = m.members.get(name)
                for e in (mem.elements if mem else []):
                    if 0 <= int(e) < len(m.elements):
                        m.load_temp(int(e), dT, dTz, case=fall)
                        n_el += 1
                objekte += 1
            for name in self.sel_flaechen:
                m.add_geometrielast(name, art="flaeche", lastart="temperatur", dT=dT,
                                    dT_z=dTz, case=fall)
                objekte += 1
            for name in self.sel_koerper:
                m.add_geometrielast(name, art="koerper", lastart="temperatur", dT=dT,
                                    dT_z=dTz, case=fall)
                objekte += 1
            if not objekte:
                return self.error("Zuerst Stäbe, Flächen oder Volumen wählen - oder "
                                  "„alle Elemente“ ankreuzen")
            n_el += m.lasten_verteilen()
        self.analysis = None
        self.results = None
        self.info(f"Temperatur ΔT = {dT:g} K auf {objekte or 'alle'} Objekte "
                  f"({n_el} Elemente) im Lastfall {fall or m.active_case}")
        self.refresh_all()

    def maske_zwangsverformung(self):
        """Vorgegebene Verschiebung/Verdrehung an gelagerten Knoten."""
        felder = [msk.Feld("ux", "u_x [mm]"), msk.Feld("uy", "u_y [mm]"),
                  msk.Feld("uz", "u_z [mm]", wert=-5.0),
                  msk.Feld("px", "φ_x [mrad]"), msk.Feld("py", "φ_y [mrad]"),
                  msk.Feld("pz", "φ_z [mrad]"),
                  msk.Feld("lager", "fehlende Lager dafür setzen", "haken", True),
                  self._lastfallfeld()]
        m = msk.Maske("Zwangsverformung", felder, knoten=0, knopf="Vorgeben",
                      hinweis="Knoten in der Ansicht wählen. Eine Verschiebung lässt "
                              "sich nur erzwingen, wo ein Lager hält - fehlende Lager "
                              "werden gesetzt, wenn angekreuzt. Nur die Werte ungleich "
                              "null werden vorgegeben.")
        m.angewendet.connect(self._zwangsverformung_aufbringen)
        self.maske_erzeugen(m)

    def _zwangsverformung_aufbringen(self, w: dict):
        if not len(self.selection):
            return self.error("Zuerst Knoten in der Ansicht wählen")
        werte = [float(w.get(k, 0.0) or 0.0) * 1e-3 for k in ("ux", "uy", "uz", "px", "py", "pz")]
        dofs = [d for d, v in enumerate(werte) if v]
        if not dofs:
            return self.error("Alle Werte sind null")
        fall = w.get("fall") or None
        m = self.model
        self.merken("Zwangsverformung")
        gesetzt = 0
        for n in self.selection:
            m.add_zwangsverformung(int(n), dofs, werte, case=fall)
        if w.get("lager", True):
            ohne = m.zwang_ohne_lager(fall)
            je_knoten: dict = {}
            for n, d in ohne:
                je_knoten.setdefault(n, []).append(d)
            for n, ds in je_knoten.items():
                m.support(int(n), sorted(set(ds)))
                gesetzt += 1
        self.analysis = None
        self.results = None
        self.info(f"Zwangsverformung an {len(self.selection)} Knoten im Lastfall "
                  f"{fall or m.active_case}"
                  + (f" - an {gesetzt} Knoten dafür Lager gesetzt" if gesetzt else ""))
        self.refresh_all()

    @staticmethod
    def _erst(d: dict) -> str:
        return next(iter(d), "")

    # ---- Kontextabhaengiges Register „Auswahl“ ------------------------
    def _auswahl_register(self):
        """Register „Auswahl: Knoten“ zeigen, solange etwas gewählt ist.

        Damit entfaellt der Bereich „Elemente ändern“ im rechten Panel
        (Vorgabe Kap. 16.1 Nr. 7): die Befehle stehen dort, wo die Auswahl ist.
        """
        if not hasattr(self, "ribbon"):
            return
        n = len(self.selection)
        if not n:
            self.ribbon.kontext_aus()
            return
        r = self.ribbon.kontext(f"Auswahl: {n} Knoten")
        if r.lay.count() > 1:      # schon gefuellt, nur der Name aendert sich
            return
        g = r.gruppe("Zuweisen")
        self.cb_assign_sec = QtWidgets.QComboBox()
        self.cb_assign_mat = QtWidgets.QComboBox()
        self.cb_assign_sec.addItems(list(self.model.sections))
        self.cb_assign_mat.addItems(list(self.model.materials))
        g.widget(self.cb_assign_sec)
        g.widget(self.cb_assign_mat)
        g.gross("Zuweisen", "⇄", self.assign_props,
                hinweis="Querschnitt und Material den Elementen der Auswahl geben")
        g = r.gruppe("Elemente")
        g.gross("Gelenke", "○", lambda: self.maske_zeigen("Netz"),
                hinweis="Gelenke an den Stabenden setzen")
        g.klein("Elemente löschen", self.delete_elements)
        g.klein("Knoten löschen", self.delete_nodes)
        g = r.gruppe("Randbedingungen")
        g.gross("Lager", "△", self.maske_lager, hinweis="Lager an der Auswahl")
        g.gross("Last", "↓", self.maske_knotenlast, hinweis="Knotenlast auf die Auswahl")
        g = r.gruppe("Auswahl")
        g.klein("Auswahl aufheben", self.clear_selection, "Esc")
        g.klein("Auswahl umkehren", self.invert_selection)

    # ---- Befehle des Ribbons -----------------------------------------
    def clear_selection(self):
        """Auswahl aufheben - Knoten wie Objekte."""
        for liste in (self.sel_linien, self.sel_flaechen, self.sel_koerper,
                      self.sel_staebe):
            liste.clear()
        self.leuchtet = []
        self._set_selection([])

    def select_all(self):
        self._set_selection(np.arange(self.model.nn, dtype=int))

    def invert_selection(self):
        alle = np.arange(self.model.nn, dtype=int)
        self._set_selection(np.setdiff1d(alle, self.selection))

    def delete_nodes(self):
        """Die gewählten Knoten und die daran hängenden Elemente entfernen."""
        if not len(self.selection):
            return self.error("Zuerst Knoten wählen")
        weg = set(int(i) for i in self.selection)
        m = self.model
        behalten = [e for e in m.elements if not (set(int(n) for n in e.nodes) & weg)]
        n_el = len(m.elements) - len(behalten)
        m.elements = behalten
        m.supports = [x for x in m.supports if int(x.node) not in weg]
        for lc in m.load_cases.values():
            lc.nodal_loads = [l for l in lc.nodal_loads if int(l.node) not in weg]
        self.info(f"{len(weg)} Knoten und {n_el} Elemente entfernt "
                  "(die Knotennummern bleiben bestehen)")
        self._set_selection([])
        self.refresh_all()

    def delete_elements(self):
        """Alle Elemente entfernen, deren Knoten sämtlich gewählt sind."""
        if not len(self.selection):
            return self.error("Zuerst Knoten wählen")
        sel = set(int(i) for i in self.selection)
        m = self.model
        vorher = len(m.elements)
        m.elements = [e for e in m.elements
                      if not set(int(n) for n in e.nodes) <= sel]
        self.info(f"{vorher - len(m.elements)} Elemente entfernt")
        self.refresh_all()

    def staebe_anschliessen(self):
        """Freie Stabenden auf die Achse des nächsten Stabes loten."""
        from ..importers import hicad_szn as Z
        radius, ok = QtWidgets.QInputDialog.getDouble(
            self, "Freie Stabenden anschließen",
            "Suchradius [mm] – aus CAD übernommene Querstäbe enden an der\n"
            "Außenkante des angeschlossenen Bauteils:", 60.0, 1.0, 1000.0, 0)
        if not ok:
            return
        log: list = []
        r = Z.an_staebe_anschliessen(self.model, radius * 1e-3, log)
        Z.zusammenhang(self.model, log)
        for z in log:
            self.info(z)
        if not r["angeschlossen"]:
            self.info(f"Kein freies Stabende innerhalb von {radius:g} mm")
        self.refresh_all()

    def support_nonlinear_dialog(self):
        self.support_nonlinear()

    def line_support_dialog(self):
        self.add_line_support()

    def surface_support_dialog(self):
        self.add_surface_support()

    def fatigue_load_dialog(self):
        self.add_fatigue_load()

    def aktive_tabelle(self):
        """Die Datentabelle, die unten gerade vorn liegt (oder None)."""
        w = self.tab_unten.currentWidget() if hasattr(self, "tab_unten") else None
        if isinstance(w, tab.Datentabelle):
            return w
        return w.findChild(tab.Datentabelle) if w is not None else None

    def tabelle_ausgeben(self, art: str):
        """Die vordere Tabelle ausgeben - immer nur das, was der Filter zeigt."""
        t = self.aktive_tabelle()
        if t is None:
            return self.error("Unten liegt gerade keine Tabelle vorn")
        if art == "clip":
            t.in_zwischenablage()
            return self.info(f"{t.sichtbar()} Zeilen in der Zwischenablage")
        pfad = t.export_xlsx() if art == "xlsx" else t.export_csv()
        if pfad:
            self.info(f"{t.sichtbar()} Zeilen geschrieben: {pfad}")
        return pfad

    def tabelle_filter_leeren(self):
        t = self.aktive_tabelle()
        if t is None:
            return self.error("Unten liegt gerade keine Tabelle vorn")
        t.filter_leeren()

    def tabelle_zeigen(self, name: str) -> bool:
        """Eine Tabelle im unteren Bereich nach vorn holen."""
        for i in range(self.tab_unten.count()):
            if self.tab_unten.tabText(i) == name:
                self.tab_unten.setCurrentIndex(i)
                self.unten_dock.show()
                return True
        return False

    # ---- Auswahl / Randbedingungen -----------------------------------
    def _sel_val(self, i):
        t = self.sel[i].text().replace(",", ".").strip()
        return float(t) if t else None

    def _set_selection(self, sel):
        self.selection = np.asarray(sel, dtype=int)
        self.lbl_sel.setText(f"{len(self.selection)} Knoten ausgewählt")
        self._auswahl_register()
        self._tabellen_markieren()
        self.redraw()

    def do_select(self):
        self._set_selection(mesher.select_nodes(
            self.model, self._sel_val(0), self._sel_val(1), self._sel_val(2),
            self._sel_val(3), self._sel_val(4), self._sel_val(5), tol=1e-6))

    def select_all(self):
        self._set_selection(np.arange(self.model.nn))

    def select_none(self):
        self._set_selection([])

    def select_numbers(self):
        self._set_selection(parse_int_list(self.ed_selnodes.text(), self.model.nn))

    def set_support(self, all_dofs=False, pinned=False):
        if not len(self.selection):
            return self.error("Keine Knoten ausgewählt")
        if all_dofs:
            dofs = [0, 1, 2, 3, 4, 5]
        elif pinned:
            dofs = [0, 1, 2]
        else:
            dofs = [i for i, c in enumerate(self.cb_dof) if c.isChecked()]
        if not dofs:
            return self.error("Keine Freiheitsgrade angehakt")
        k = self.ed_spring.value()
        for n in self.selection:
            self.model.fix(int(n), dofs, stiffness=[k] * len(dofs) if k > 0 else None)
        self.refresh_all()

    def support_nonlinear(self):
        """Nichtlinearitaet des Lagers an den gewaehlten Knoten einstellen."""
        if not len(self.selection):
            return self.error("Keine Knoten ausgewählt")
        n = int(self.selection[0])
        sup = next((s for s in self.model.supports if s.node == n), None)
        if sup is None:
            sup = self.model.support(n, [])
        d = SupportNonlinearDialog(self, sup, "Knotenlager")
        if not d.exec():
            return
        beh = d.behaviours()
        for node in self.selection:
            s = next((x for x in self.model.supports if x.node == int(node)), None)
            if s is None:
                s = self.model.support(int(node), [])
            s.behaviour = {k: v for k, v in beh.items()}
            s.dofs = sorted({k for k, v in beh.items() if v.acts})
        self.info(f"Nichtlinearität an {len(self.selection)} Lagern gesetzt")
        self.refresh_all()

    # ---- Anschluesse ----------------------------------------------------
    def _selected_beam_end(self):
        """(Element, Ende) aus der Auswahl bestimmen.

        Ausgewaehlt wird ein Knoten; gesucht wird das Stabelement, das dort
        endet. Liegen mehrere an, wird das erste genommen und gemeldet.
        """
        if not len(self.selection):
            raise ValueError("Bitte den Knoten am Stabende auswählen")
        n = int(self.selection[0])
        for i, e in enumerate(self.model.elements):
            if e.typ not in ("beam", "truss"):
                continue
            if int(e.nodes[0]) == n:
                return i, 0
            if int(e.nodes[1]) == n:
                return i, 1
        raise ValueError(f"An Knoten {n + 1} endet kein Stabelement")

    def _end_forces(self, elem: int, end: int) -> dict:
        """Schnittgroessen am Stabende aus dem letzten Ergebnis (sonst 0)."""
        r = self.current_result()
        if r is None or not getattr(r, "beam_end", None):
            return {}
        v = r.beam_end.get(int(elem))
        if v is None:
            return {}
        o = 0 if end == 0 else 6
        vz = float(v[o + 2])
        return {"N": float(v[o + 0]) * (-1.0 if end == 0 else 1.0),
                "Vz": vz, "My": float(v[o + 4])}

    def add_joint(self):
        """Anschluss am gewaehlten Stabende anlegen - er gehoert ins Modell.

        Der Anschluss wird als ``model.Joint`` gespeichert: er ueberlebt
        Speichern, Laden und Rueckgaengig, steht im Modellbaum und in der
        Tabelle und wird bei jeder Berechnung mit nachgewiesen.
        """
        from ..joints import anschluss as ans
        try:
            elem, end = self._selected_beam_end()
        except ValueError as ex:
            return self.error(str(ex))
        d = JointDialog(self, self.model, elem, end, self._end_forces(elem, end))
        if not d.exec():
            return
        t = d.result_template()
        if t is None:
            return self.error("Es liegt kein gültiger Vorschlag vor")
        name = self._freier_name(t.name, self.model.joints)
        self.merken(f"Anschluss {name}")
        j = ans.als_joint(t, name)
        j.stuetze = d.stuetze()
        j.rahmen = d.rahmen()
        j.modellierung = d.modellierung()
        if d.kraefte_fest():
            j.kraefte = {k: v for k, v in d.forces().items()
                         if k in ans.KRAEFTE.get(j.typ, ())}
        self.model.joints[name] = j
        kind = d.fe_kind()
        if kind:
            log = []
            teil = t.build(kind=kind, log=log)
            teil.meta["bauteil"] = name
            path = os.path.join(os.path.dirname(self.path or "."),
                                f"{name.replace(' ', '_')}.json")
            try:
                teil.save(path)
                log.append(f"Teilmodell gespeichert: {path}")
            except OSError as ex:
                log.append(f"Teilmodell konnte nicht gespeichert werden: {ex}")
            QtWidgets.QMessageBox.information(
                self, "Teilmodell des Anschlusses", "\n".join(log))
        self.info(f"Anschluss „{name}“ angelegt ({j.ort()}) - er wird ab jetzt "
                  "bei jeder Berechnung nachgewiesen")
        self.refresh_all()

    @staticmethod
    def _freier_name(vorschlag: str, vorhanden) -> str:
        """Einen noch nicht vergebenen Namen finden."""
        name = vorschlag or "Anschluss"
        if name not in vorhanden:
            return name
        i = 2
        while f"{name} {i}" in vorhanden:
            i += 1
        return f"{name} {i}"

    def delete_joint(self):
        """Den in der Tabelle gewaehlten Anschluss entfernen."""
        key = self._tabellenschluessel(self.tbl_joint)
        if key is None or key not in self.model.joints:
            return self.error("Zuerst einen Anschluss in der Tabelle wählen")
        self.merken(f"Anschluss {key} gelöscht")
        del self.model.joints[key]
        self.info(f"Anschluss „{key}“ entfernt")
        self.refresh_all()

    def _anschluss_gewaehlt(self, name: str):
        """Anschluss im Baum angeklickt: Zeile markieren und Stab waehlen."""
        j = self.model.joints.get(name)
        if j is None:
            return
        self.tabelle_zeigen("Anschlüsse")
        self.tbl_joint.markieren([name])
        if 0 <= j.elem < len(self.model.elements):
            self._set_selection([int(n) for n in self.model.elements[j.elem].nodes])

    def show_joints(self):
        """Die Nachweise der Anschlüsse im Klartext zeigen."""
        if not self.model.joints:
            return self.error("Es wurde noch kein Anschluss angelegt")
        an = getattr(self, "analysis", None)
        erg = getattr(an, "joints", None) if an is not None else None
        if erg is None:
            from ..joints import anschluss as ans
            text = "\n\n".join(
                ans.vorlage(self.model, j).describe() for j in self.model.joints.values())
            text += "\n\nNoch nicht gerechnet - „Berechnen“ (F5) führt die Nachweise."
        else:
            teile = []
            for c in erg.joints.values():
                zeilen = [f"{c.name} ({c.ort}) - {c.status()}", "=" * 78, c.beschreibung, ""]
                if c.fehler:
                    zeilen.append("nicht geführt: " + c.fehler)
                from ..joints.design import Check as _JCheck
                for ch in c.checks:
                    f = _JCheck.FAKTOR.get(ch["einheit"], 1.0)
                    zeilen.append(f"{'OK ' if ch['eta'] <= 1 else 'NICHT ERFÜLLT'} "
                                  f"{ch['name']:42s} {ch['E'] * f:9.1f} / {ch['R'] * f:9.1f} "
                                  f"{ch['einheit']}  eta = {ch['eta']:.3f}")
                for e in c.ermuedung:
                    zeilen.append(f"{'OK ' if e['ok'] else 'NICHT ERFÜLLT'} Ermüdung "
                                  f"Kerbfall {e['kerbfall']:.0f}: D = {e['schaedigung']:.3f}")
                if c.kombination:
                    zeilen.append(f"maßgebend: {c.massgebend} in {c.kombination}")
                teile.append("\n".join(zeilen))
            text = "\n\n".join(teile) + "\n\n" + erg.summary()
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Anschlüsse")
        lay = QtWidgets.QVBoxLayout(dlg)
        t = QtWidgets.QPlainTextEdit(text)
        t.setReadOnly(True)
        f = t.font()
        f.setFamily("Courier New")
        t.setFont(f)
        t.setMinimumSize(820, 520)
        lay.addWidget(t)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec()

    def add_line_support(self):
        """Linienlager entlang der gewaehlten Knoten (in Auswahlreihenfolge)."""
        if len(self.selection) < 2:
            return self.error("Mindestens zwei Knoten auswählen (Reihenfolge = Linienzug)")
        d = SupportNonlinearDialog(self, None, "Linienlager")
        if not d.exec():
            return
        ls = self.model.add_line_support([int(n) for n in self.selection])
        ls.behaviour = d.behaviours()
        self.info(f"Linienlager über {len(self.selection)} Knoten angelegt")
        self.refresh_all()

    def add_surface_support(self):
        """Flaechenlager (Bettung) auf den gewaehlten Elementen."""
        els = self._elements_from_text(self.ed_elist.text())
        if not els:
            return self.error("Keine Elemente angegeben (Feld 'Elemente')")
        d = SupportNonlinearDialog(self, None, "Flächenlager (Bettung)")
        if not d.exec():
            return
        ss = self.model.add_surface_support(els)
        ss.behaviour = d.behaviours()
        self.info(f"Flächenlager auf {len(els)} Elementen angelegt")
        self.refresh_all()

    def remove_support(self):
        sel = set(int(n) for n in self.selection)
        self.model.supports = [s for s in self.model.supports if s.node not in sel]
        self.refresh_all()

    def add_load(self):
        if not len(self.selection):
            return self.error("Keine Knoten ausgewählt")
        v = np.array([e.value() for e in self.ld])
        if self.ld_split.isChecked():
            v = v / len(self.selection)
        for n in self.selection:
            self.model.load_node(int(n), *v)
        self.refresh_all()

    def add_beam_load(self):
        q = [e.value() for e in self.q]
        q2 = [e.value() for e in self.q2] if self.q_trap.isChecked() else None
        els = self._elements_from_text(self.ed_qelems.text())
        if not els:
            els = [i for i, e in enumerate(self.model.elements) if e.typ in ("beam", "truss")]
        n = 0
        for i in els:
            if self.model.elements[i].typ in ("beam", "truss"):
                self.model.load_beam(i, *q, system="local" if self.q_local.isChecked() else "global", q2=q2)
                n += 1
        self.info(f"Streckenlast auf {n} Stäbe ({self.model.active_case})")
        self.refresh_all()

    def add_face_load(self):
        p = self.p_face.value()
        k = self.p_dir.currentIndex()
        direction = None if k == 0 else [(1, 0, 0), (0, 1, 0), (0, 0, 1)][k - 1]
        n = 0
        for i, e in enumerate(self.model.elements):
            if e.typ in ("shell3", "shell4"):
                self.model.load_face(i, p, direction=direction)
                n += 1
        self.info(f"Flächenlast auf {n} Schalen ({self.model.active_case})")
        self.refresh_all()

    def add_temp_load(self):
        dT, dTz = self.ed_dT.value(), self.ed_dTz.value()
        els = self._elements_from_text(self.ed_qelems.text()) or list(range(len(self.model.elements)))
        for i in els:
            self.model.load_temp(i, dT, dTz)
        self.info(f"Temperaturlast auf {len(els)} Elemente")
        self.refresh_all()

    def toggle_gravity(self, on):
        self.model.set_gravity(-9.81 if on else 0.0)
        self.refresh_cases()

    def clear_loads(self):
        lc = self.model.case()
        for liste in ("nodal_loads", "beam_loads", "face_loads", "temp_loads",
                      "geometrielasten", "linienlasten", "zwangsverformungen"):
            getattr(lc, liste).clear()
        lc.gravity = [0.0, 0.0, 0.0]
        self.analysis = None
        self.results = None
        self.refresh_all()

    def clear_supports(self):
        self.model.supports.clear()
        self.refresh_all()

    # ---- Lastfaelle --------------------------------------------------
    def _case_selected(self):
        r = self.tbl_lc.currentRow()
        names = list(self.model.load_cases)
        if 0 <= r < len(names):
            self.model.active_case = names[r]
            self.lbl_active.setText(f"aktiver Lastfall: {names[r]} ({self.model.case().category})")
            self.cb_g.blockSignals(True)
            self.cb_g.setChecked(bool(np.any(self.model.gravity)))
            self.cb_g.blockSignals(False)
            self.redraw()

    def add_case(self):
        d = LoadCaseDialog(self, existing=list(self.model.load_cases))
        if d.exec():
            name, cat, desc, grp = d.values()
            if name in self.model.load_cases:
                return self.error(f"Lastfall '{name}' existiert bereits")
            self.model.add_load_case(name, cat, desc, exclusive_group=grp)
            self.refresh_all()

    def edit_case(self):
        lc = self.model.case()
        d = LoadCaseDialog(self, lc, list(self.model.load_cases))
        if d.exec():
            name, cat, desc, grp = d.values()
            old = lc.name
            lc.category, lc.description, lc.exclusive_group = cat, desc, grp
            if name != old:
                self.model.load_cases = {(name if k == old else k): v for k, v in self.model.load_cases.items()}
                lc.name = name
                for c in self.model.combinations.values():
                    if old in c.factors:
                        c.factors[name] = c.factors.pop(old)
                self.model.active_case = name
            self.refresh_all()

    def copy_case(self):
        import copy
        lc = self.model.case()
        new = copy.deepcopy(lc)
        new.name = lc.name + "_Kopie"
        self.model.load_cases[new.name] = new
        self.model.active_case = new.name
        self.refresh_all()

    def remove_case(self):
        self.model.remove_load_case(self.model.active_case)
        self.refresh_all()

    def auto_combinations(self):
        d = AutoCombinationDialog(self, self.model.design)
        if d.exec():
            from ..combinations import generate_combinations
            ds = self.model.design
            ds.combination_rule = "6.10ab" if d.rule.currentIndex() == 1 else "6.10"
            ds.gamma_G_sup = d.gG.value() or 1.35
            ds.gamma_Q = d.gQ.value() or 1.5
            try:
                cs = generate_combinations(self.model, d.uls.isChecked(), d.sls.isChecked(),
                                           d.acc.isChecked(), g_favourable=d.gfav.isChecked(),
                                           replace=d.replace.isChecked())
            except Exception as ex:
                return self.error(ex)
            self.info(f"{len(cs)} Kombinationen erzeugt")
            self.refresh_all()

    def add_combination(self):
        d = CombinationDialog(self, self.model)
        if d.exec():
            c = d.result()
            self.model.combinations[c.name] = c
            self.refresh_all()

    def edit_combination(self):
        r = self.tbl_comb.currentRow()
        names = list(self.model.combinations)
        if 0 <= r < len(names):
            c = self.model.combinations[names[r]]
            d = CombinationDialog(self, self.model, c)
            if d.exec():
                new = d.result()
                del self.model.combinations[names[r]]
                self.model.combinations[new.name] = new
                self.refresh_all()

    def remove_combination(self):
        r = self.tbl_comb.currentRow()
        names = list(self.model.combinations)
        if 0 <= r < len(names):
            del self.model.combinations[names[r]]
            self.refresh_all()

    def clear_combinations(self):
        self.model.combinations.clear()
        self.refresh_all()

    def add_fatigue_load(self):
        d = FatigueLoadDialog(self, self.model)
        if d.exec():
            name, cmax, cmin, n, f = d.values()
            self.model.add_fatigue_load(name or f"E{len(self.model.fatigue_loads)+1}", cmax, cmin, n, f)
            self.refresh_all()

    def remove_fatigue_load(self):
        r = self.tbl_fatl.currentRow()
        names = list(self.model.fatigue_loads)
        if 0 <= r < len(names):
            del self.model.fatigue_loads[names[r]]
            self.refresh_all()

    # ---- Kontakt -----------------------------------------------------
    def add_contact_support(self):
        if not len(self.selection):
            return self.error("Keine Knoten ausgewählt")
        d = [e.value() for e in self.cs_dir]
        if not any(d):
            return self.error("Stützrichtung angeben")
        for n in self.selection:
            self.model.add_contact_support(int(n), d, self.cs_gap.value(), self.cs_k.value(),
                                           self.cs_mu.value())
        self.refresh_all()

    def add_gap_element(self):
        if len(self.selection) != 2:
            return self.error("Genau zwei Knoten auswählen (a, b)")
        d = [e.value() for e in self.ge_dir]
        self.model.add_gap_element(int(self.selection[0]), int(self.selection[1]),
                                   d if any(d) else None, self.ge_gap.value(), self.ge_k.value(),
                                   self.ge_mu.value())
        self.refresh_all()

    def add_contact_pair(self):
        if not len(self.selection):
            return self.error("Slave-Knoten auswählen")
        d = ContactPairDialog(self, self.model, len(self.selection))
        if d.exec():
            els = d.master_elements(self.model)
            if not els:
                return self.error("Keine Master-Elemente")
            self.model.add_contact_pair(d.name.text() or "Kontakt", [int(n) for n in self.selection],
                                        els, stiffness=d.k.value(), mu=d.mu.value(), gap=d.gap.value(),
                                        search_radius=d.radius.value() or None,
                                        flip_normal=d.flip.isChecked())
            self.refresh_all()

    def remove_contact(self):
        r = self.tbl_cdef.currentRow()
        m = self.model
        n1, n2 = len(m.contact_supports), len(m.gap_elements)
        if r < 0:
            return
        if r < n1:
            del m.contact_supports[r]
        elif r < n1 + n2:
            del m.gap_elements[r - n1]
        elif r - n1 - n2 < len(m.contact_pairs):
            del m.contact_pairs[r - n1 - n2]
        self.refresh_all()

    def clear_contact(self):
        self.model.contact_supports.clear(); self.model.gap_elements.clear(); self.model.contact_pairs.clear()
        self.refresh_all()

    # ---- Nachweise ---------------------------------------------------
    def auto_members(self):
        n = len(self.model.auto_members())
        self.info(f"{n} Stäbe erkannt (gesamt {len(self.model.members)})")
        self.refresh_all()

    def member_from_elements(self):
        els = parse_int_list(self.ed_member_elems.text(), len(self.model.elements))
        els = [i for i in els if self.model.elements[i].typ in ("beam", "truss")]
        if not els:
            return self.error("Keine Stabelemente angegeben")
        self.model.add_member(f"S{len(self.model.members)+1}", els)
        self.refresh_all()

    def edit_member(self):
        r = self.tbl_mem.currentRow()
        names = list(self.model.members)
        if 0 <= r < len(names):
            mem = self.model.members[names[r]]
            d = MemberDialog(self, mem, self.model.member_length(mem))
            if d.exec():
                d.apply(mem)
                self.refresh_all()

    def remove_member(self):
        r = self.tbl_mem.currentRow()
        names = list(self.model.members)
        if 0 <= r < len(names):
            del self.model.members[names[r]]
            self.refresh_all()

    def design_settings(self):
        d = DesignSettingsDialog(self, self.model.design)
        if d.exec():
            d.apply(self.model.design)

    def do_design(self):
        if self.analysis is None:
            return self.error("Zuerst 'Alle Lastfälle + Kombinationen' berechnen")
        if not self.model.members:
            return self.error("Keine Stäbe definiert (Nachweise → Stäbe automatisch erkennen)")
        from ..ec3.design import check_members
        self._run_background(lambda progress: check_members(self.model, self.analysis, progress=progress),
                             self._design_done, "Nachweise EC3")

    def _design_done(self, res):
        self.analysis.design = res
        self.info(res.summary())
        self.show_results()

    def do_fatigue(self):
        if self.analysis is None:
            return self.error("Zuerst berechnen")
        if not self.model.fatigue_loads:
            return self.error("Keine Ermüdungslasten definiert (Lastfälle → Ermüdungslasten)")
        from ..ec3.fatigue import check_fatigue
        self._run_background(lambda progress: check_fatigue(self.model, self.analysis, progress=progress),
                             self._fatigue_done, "Ermüdung")

    def _fatigue_done(self, res):
        self.analysis.fatigue = res
        self.info(res.summary())
        self.show_results()

    # ---- Berechnung --------------------------------------------------
    def do_check(self):
        msgs = self.model.check()
        self.log.appendPlainText("--- Modellprüfung ---")
        self.log.appendPlainText("\n".join(msgs) if msgs else "keine Auffälligkeiten")
        self.bottom_tabs.setCurrentIndex(0)

    def _apply_parallel_settings(self):
        parallel.configure(workers=self.sp_workers.value(),
                           backend="farm" if self.cb_backend.currentIndex() == 1 else "local",
                           farm_host=self.ed_farm_host.text().strip() or "127.0.0.1",
                           farm_port=int(self.ed_farm_port.text() or 5555),
                           farm_key=self.ed_farm_key.text() or "statik3d")

    def farm_status(self):
        self._apply_parallel_settings()
        try:
            from ..farm import FarmClient
            c = FarmClient(parallel.settings().farm_host, parallel.settings().farm_port,
                           parallel.settings().farm_key)
            st = c.status()
            lines = [c.describe()]
            for k, v in st["workers"].items():
                lines.append(f"  {k}: {'aktiv' if v.get('alive') else 'inaktiv'}, "
                             f"{v.get('jobs', 0)} Aufträge, Rechner {v.get('host', '?')}")
            QtWidgets.QMessageBox.information(self, "Rechnerfarm", "\n".join(lines))
        except Exception as ex:
            self.error(f"Farm nicht erreichbar: {ex}")

    def farm_start_local(self):
        self._apply_parallel_settings()
        try:
            from .. import farm
            st = parallel.settings()
            farm.start_server_thread("0.0.0.0", st.farm_port, st.farm_key)
            farm.start_worker_threads("127.0.0.1", st.farm_port, st.farm_key,
                                      n=max(1, self.sp_workers.value()), name="gui")
            self.cb_backend.setCurrentIndex(1)
            self.info(f"Lokaler Farm-Server auf Port {st.farm_port} mit {self.sp_workers.value()} Workern "
                      f"gestartet. Weitere Rechner: python -m statik3d.farm worker --host <diese IP> "
                      f"--port {st.farm_port} --key <Schlüssel>")
        except Exception as ex:
            self.error(f"Farm-Start fehlgeschlagen: {ex}")

    def _run_background(self, func, on_done, label):
        if self.worker is not None and self.worker.isRunning():
            return self.error("Es läuft bereits eine Berechnung")
        self.btn_solve.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log.appendPlainText(f"\n--- {label} gestartet ({parallel.describe()}) ---")
        self.worker = SolveWorker(func)
        self.worker.progress.connect(self.info)
        self.worker.finished_ok.connect(lambda r: self._bg_done(on_done, r))
        self.worker.failed.connect(self._bg_failed)
        self.worker.start()

    def _bg_done(self, on_done, result):
        self.btn_solve.setEnabled(True)
        self.progress_bar.setVisible(False)
        try:
            on_done(result)
        except Exception as ex:
            self.log.appendPlainText(traceback.format_exc())
            self.error(str(ex))

    def _bg_failed(self, msg, tb):
        self.btn_solve.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.log.appendPlainText(tb)
        self.error(msg)

    def do_solve(self, kind: str = None):
        msgs = [m for m in self.model.check() if m.startswith("FEHLER")]
        if msgs:
            return self.error("\n".join(msgs))
        self._apply_parallel_settings()
        if kind is None:
            kind = ["all", "case", "modal", "buckling"][self.cb_analysis.currentIndex()]
        model = self.model
        nmodes = self.sp_modes.value()
        design = self.cb_do_design.isChecked() and bool(model.members)
        fatigue = self.cb_do_fat.isChecked() and bool(model.fatigue_loads)
        if kind == "all":
            func = lambda p: solver.solve_all(model, progress=p, design=design, fatigue=fatigue)
        elif kind == "case":
            func = lambda p: solver.solve_static(model, p)
        elif kind == "modal":
            func = lambda p: solver.solve_modal(model, nmodes, p)
        else:
            func = lambda p: solver.solve_buckling(model, nmodes, p)
        self._run_background(func, lambda r: self._solve_done(kind, r), "Berechnung")

    def _solve_done(self, kind, r):
        if kind == "all":
            self.analysis = r
            self.results = None
            text = r.summary()
        else:
            self.results = r
            if kind == "case":
                self.analysis = solver.Analysis(self.model, cases={r.name: r})
                self.analysis.envelopes["CASES"] = solver.Envelope(self.model, self.analysis.cases,
                                                                   "Umhüllende Lastfälle")
                self.results = None
            text = r.summary()
        self.log.appendPlainText(text)
        self.txt_summary.setPlainText(text)
        self._fill_result_selector()
        self.tabs.setCurrentIndex(7)
        self.show_results()
        # Die Ergebnisse stehen jetzt auch im Modellbaum - er muss davon wissen.
        self._refresh_baum()
        self._refresh_kopf()

    # ---- Ergebnisse --------------------------------------------------
    def _fill_result_selector(self):
        self.cb_result.blockSignals(True)
        self.cb_result.clear()
        if self.results is not None:
            self.cb_result.addItem(self.results.name, ("single", None))
        elif self.analysis is not None:
            an = self.analysis
            for k in an.envelopes:
                self.cb_result.addItem(f"Umhüllende {k}", ("env", k))
            for k in an.combinations:
                self.cb_result.addItem(f"Kombination {k}: {self.model.combinations[k].formula()}", ("combo", k))
            for k in an.cases:
                self.cb_result.addItem(f"Lastfall {k}", ("case", k))
        self.cb_result.blockSignals(False)

    def current_result(self):
        """Aktuell gewaehltes Ergebnisobjekt (Results oder Envelope) oder None."""
        if self.results is not None:
            return self.results
        if self.analysis is None or self.cb_result.count() == 0:
            return None
        kind, key = self.cb_result.currentData()
        an = self.analysis
        if kind == "env":
            return an.envelopes.get(key)
        if kind == "combo":
            return an.combinations.get(key)
        if kind == "case":
            return an.cases.get(key)
        return None

    def _ausnutzung_map(self) -> dict | None:
        """Die Ausnutzung je Element - EC3 vor Ermuedung, sonst nichts."""
        an = self.analysis
        if an is None:
            return None
        if getattr(an, "design", None) is not None:
            return an.design.util_by_element()
        if getattr(an, "fatigue", None) is not None:
            return an.fatigue.util_by_element(self.model)
        return None

    def _util_map(self, field: str) -> dict | None:
        an = self.analysis
        if an is None:
            return None
        if field.startswith("Ausnutzung EC3") and an.design is not None:
            return an.design.util_by_element()
        if field.startswith("Ausnutzung Erm") and an.fatigue is not None:
            return an.fatigue.util_by_element(self.model)
        return None

    def show_results(self):
        r = self.current_result()
        self.cb_mode.blockSignals(True)
        self.cb_mode.clear()
        if r is not None and getattr(r, "freqs", None) is not None:
            self.cb_mode.addItems([f"{i+1}. Form  f = {f:.3f} Hz" for i, f in enumerate(r.freqs)])
        elif r is not None and getattr(r, "buckling_factors", None) is not None:
            self.cb_mode.addItems([f"{i+1}. Form  η = {f:.3f}" for i, f in enumerate(r.buckling_factors)])
        self.cb_mode.blockSignals(False)
        if r is None:
            self.txt_res.setPlainText("")
            self.redraw()
            return
        lines = [r.summary()]
        an = self.analysis
        if an is not None and an.design is not None:
            lines.append(an.design.summary())
            self._fill(self.tbl_design, an.design.table()[1:], an.design.table()[0])
        if an is not None and an.fatigue is not None:
            lines.append(an.fatigue.summary())
            self._fill(self.tbl_fat, an.fatigue.table()[1:], an.fatigue.table()[0])
            self.lbl_design.setText(an.design.summary() if an.design else "")
        if an is not None and an.design is not None:
            self.lbl_design.setText(an.design.summary() + ("\n" + an.fatigue.summary() if an.fatigue else ""))
        if an is not None and an.joints is not None:
            lines.append(an.joints.summary())
        if an is not None and an.gzg is not None:
            lines.append(an.gzg.summary())
        if an is not None and an.beulen is not None:
            lines.append(an.beulen.summary())
        if an is not None and an.lasteinleitung is not None:
            lines.append(an.lasteinleitung.summary())
        if an is not None and getattr(an, "volumen", None) is not None:
            lines.append(an.volumen.summary())
        if an is not None and getattr(an, "theorie2", None) is not None \
                and an.theorie2.kombinationen:
            lines.append(an.theorie2.summary())
        self.refresh_joints()
        self.refresh_verformungen()
        self.refresh_beulfelder()
        self.refresh_volumen()
        self.txt_res.setPlainText("\n".join(lines))
        # Tabellen
        if hasattr(r, "beam_forces"):
            util_map = self._util_map("Ausnutzung EC3") or {}
            rows = []
            for e, d in sorted(r.beam_forces.items()):
                u = util_map.get(e, d["util"])
                rows.append([e, d["N"][0] / 1e3, d["N"][1] / 1e3,
                             d["Vz"][0] / 1e3, d["Vz"][1] / 1e3,
                             d["My"][0] / 1e3, d["My"][1] / 1e3,
                             max(abs(d["Mz"][0]), abs(d["Mz"][1])) / 1e3,
                             d["sig_max"] / 1e6, float(u) if u is not None else "-"])
            self._fill(self.tbl_beam, rows)
            react = []
            for s in sorted({s.node for s in self.model.supports} | {c.node for c in self.model.contact_supports}):
                R = r.reactions[s]
                react.append([s] + [float(v) / 1e3 for v in R])
            self._fill(self.tbl_react, react)
            self._fill(self.tbl_contact, [[c["node"], c["kind"], c["status"], c["Fn"] / 1e3,
                                           c["Ft"] / 1e3, c["gap"] * 1e3] for c in r.contact])
            self._fill(self.tbl_env, [])
        elif hasattr(r, "extreme_table"):
            rows = [[e, k, mn / 1e3, c1, mx / 1e3, c2] for e, k, mn, c1, mx, c2 in r.extreme_table()]
            self._fill(self.tbl_env, rows)
            self._fill(self.tbl_beam, [])
            react = []
            for s in sorted({s.node for s in self.model.supports}):
                react.append([s] + [f"{r.r_min[s, i]/1e3:.2f} / {r.r_max[s, i]/1e3:.2f}" for i in range(6)])
            self._fill(self.tbl_react, react)
        self.redraw()

    def _raender(self) -> dict:
        """{Flaechenname: Randpunkte} - einmal je Modellstand berechnet.

        Das Randpolygon einer Flaeche entsteht aus ihren Linien; bei ueber
        tausend Flaechen darf das nicht bei jedem Neuzeichnen und jeder
        Tabellenzeile neu geschehen. Es sind Punkte, keine Knotennummern:
        krumme Randlinien werden auf ihrer wahren Kurve abgetastet, sonst
        faellt eine Bohrung aus zwei Halbboegen in ihre Sehne zusammen.
        """
        m = self.model
        stand = (id(m), len(m.flaechen), len(m.lines), m.nn)
        if getattr(self, "_raender_stand", None) != stand:
            self._raender_stand = stand
            self._raender_zwischen = {name: f.randpunkte(m)
                                      for name, f in m.flaechen.items()}
        return self._raender_zwischen

    def _randseiten(self) -> dict:
        """{Flaechenname: [Punktfolge je Randlinie]} - fuer krumme Flaechen.

        Wird von ``add_geometrie`` bei Bedarf gefuellt (Coons-Flaechen der
        Zylindermaentel) und wie die Raender je Modellstand gehalten.
        """
        m = self.model
        stand = (id(m), len(m.flaechen), len(m.lines), m.nn)
        if getattr(self, "_randseiten_stand", None) != stand:
            self._randseiten_stand = stand
            self._randseiten_zwischen = {}
        return self._randseiten_zwischen

    def _linien_netz(self):
        """Das Liniennetz je Modellstand, Auswahl und Sicht einmal."""
        m = self.model
        stand = (id(m), len(m.lines or {}), m.nn,
                 hash(np.asarray(m.nodes, float).tobytes()) if m.nn else 0,
                 tuple(self.sel_linien), frozenset(self.versteckt["linien"]))
        if getattr(self, "_liniennetz_stand", None) == stand:
            return self._liniennetz
        self._liniennetz = vp.linien_netz(m, self.sel_linien, self.versteckt["linien"])
        self._liniennetz_stand = stand
        return self._liniennetz

    class _Stille:
        """Waehrend des Aufbaus nicht nach jedem Darsteller neu zeichnen.

        pyvista rendert bei jedem add_mesh; bei vierzehn Darstellern sind das
        vierzehn Bilder je Klick. Hier wird render() fuer die Dauer des
        Aufbaus stillgelegt, am Ende zeichnet redraw einmal.
        """

        def __init__(self, plotter):
            self.plotter = plotter

        def __enter__(self):
            self.plotter.render = lambda *a, **k: None
            return self

        def __exit__(self, *exc):
            try:
                del self.plotter.render
            except AttributeError:
                pass
            return False

    def _geometrie_netze(self):
        """Die Netze der Geometrie ohne Elemente - je Modellstand und Sicht einmal.

        Der Aufbau (Coons-Flaechen der Zylindermaentel) kostet beim Drehlager
        eine Sekunde; er darf nicht bei jedem Klick anfallen.
        """
        m = self.model
        stand = (id(m), len(m.flaechen), len(m.koerper), len(m.lines), m.nn,
                 hash(np.asarray(m.nodes, float).tobytes()) if m.nn else 0,
                 len(m.elements), sum(len(f.elemente) for f in m.flaechen.values()),
                 self.act_flaechen.isChecked(), self.act_volumen.isChecked(),
                 frozenset(self.versteckt["flaechen"]), frozenset(self.versteckt["koerper"]))
        if getattr(self, "_geonetze_stand", None) == stand:
            return self._geonetze
        self._geonetze = vp.geometrie_netze(m, raender=self._raender(), seiten=self._randseiten(),
                                            flaechen_an=self.act_flaechen.isChecked(),
                                            koerper_an=self.act_volumen.isChecked(),
                                            ausser_flaechen=self.versteckt["flaechen"],
                                            ausser_koerper=self.versteckt["koerper"])
        self._geonetze_stand = stand
        return self._geonetze

    def _inhalte(self) -> dict:
        """{Flaechenname: Flaecheninhalt [m^2]} - einmal je Modellstand.

        Fein abgetastet (siehe Flaeche.inhalt); bei ueber tausend Flaechen
        dauert das rund drei Sekunden und darf nicht bei jeder Tabellenzeile
        von vorn geschehen.
        """
        m = self.model
        stand = (id(m), len(m.flaechen), len(m.lines), m.nn)
        if getattr(self, "_inhalte_stand", None) != stand:
            self._inhalte_stand = stand
            self._inhalte_zwischen = {name: f.inhalt(m)
                                      for name, f in m.flaechen.items()}
        return self._inhalte_zwischen

    def _auswahl_zeichnen(self):
        """Ausgewaehlte Linien, Flaechen, Koerper und Staebe hervorheben."""
        m = self.model
        pl = self.plotter
        # Aus dem Modellbaum heraus Gewaehltes leuchtet auf
        leuchtet = [i for i in (getattr(self, "leuchtet", None) or [])
                    if 0 <= i < len(m.elements)]
        if leuchtet:
            try:
                teil = vp.to_grid(m).extract_cells(np.asarray(leuchtet, int))
                pl.add_mesh(teil, color="#ff8800", opacity=0.85, show_edges=True,
                            edge_color="#c05000", line_width=5, name="leuchtet")
            except Exception as ex:      # noqa: BLE001
                self.log.appendPlainText(f"Hervorhebung: {ex}")
        # Alle Umrisse der Auswahl in **einem** Darsteller: ein Koerper mit 144
        # Flaechen brauchte sonst 144 add_mesh-Aufrufe je Klick.
        zuege: list = []
        for name in self.sel_linien:
            ln = m.lines.get(name)
            if ln is None:
                continue
            idx = [int(n) for n in ln.nodes if 0 <= int(n) < m.nn]
            if len(idx) > 1:
                X = m.nodes[idx]
                if (ln.typ or "polyline") != "polyline":
                    try:
                        X = np.asarray(ln.punkte(m, vp.TEILUNG_KURVE), float)
                    except Exception:      # noqa: BLE001 - dann eben die Sehne
                        X = m.nodes[idx]
                zuege.append(np.asarray(X, float))
        raender = self._raender()
        for name in self.sel_flaechen:
            f = m.flaechen.get(name)
            if f is None:
                continue
            P = np.asarray(raender.get(name, f.randpunkte(m)), float)
            if len(P) >= 3:
                zuege.append(np.vstack([P, P[:1]]))
        for name in self.sel_koerper:
            k = m.koerper.get(name)
            if k is None:
                continue
            for fn in k.flaechen:
                f = m.flaechen.get(fn)
                if f is None:
                    continue
                P = np.asarray(raender.get(fn, f.randpunkte(m)), float)
                if len(P) >= 3:
                    zuege.append(np.vstack([P, P[:1]]))
        for name in self.sel_staebe:
            mem = m.members.get(name)
            if mem is None:
                continue
            for e in (mem.elements or []):
                if e < len(m.elements):
                    idx = [int(n) for n in m.elements[e].nodes]
                    zuege.append(m.nodes[[idx[0], idx[-1]]])
        if zuege:
            pts: list = []
            lines: list = []
            for X in zuege:
                basis = len(pts)
                pts.extend(X)
                for j in range(len(X) - 1):
                    lines.extend([2, basis + j, basis + j + 1])
            pl.add_mesh(pv.PolyData(np.asarray(pts, float), lines=np.asarray(lines)),
                        color="#ff8800", line_width=6, name="auswahl")

    def _scale(self, u):
        umax = np.abs(u[:, :3]).max() if u.size else 0.0
        if umax <= 0:
            return 0.0, 0.0
        target = 0.08 * self.model.characteristic_size() * self.sl_scale.value() / 30.0
        return target / umax, umax

    def _gitter(self, typen, ausser):
        """Das gefilterte Elementnetz und je Punkt seine Knotennummer.

        Einmal je Modellstand: bei 370000 Tetraedern dauert der Aufbau ueber
        eine Sekunde, das darf nicht bei jedem Klick geschehen. Volumen werden
        auf ihre **Oberflaeche** gebracht - gezeichnet wird ohnehin nur sie,
        und der Fang auf der Oberflaeche bleibt damit bezahlbar.
        """
        m = self.model
        stand = (id(m), len(m.elements), m.nn,
                 hash(np.asarray(m.nodes, float).tobytes()) if m.nn else 0,
                 tuple(typen), frozenset(ausser))
        if getattr(self, "_gitter_stand", None) == stand:
            return self._gitter_zwischen
        grid = vp.to_grid(m, typen=typen, ausser=ausser)
        kidx = np.arange(m.nn)
        if grid.n_cells:
            try:
                volumen_typen = {vp.CELL_MAP[t][0] for t in vp.TYPEN_VOLUMEN
                                 if t in vp.CELL_MAP}
                if np.isin(grid.celltypes, list(volumen_typen)).any():
                    flaeche = grid.extract_surface(pass_pointid=True, pass_cellid=True,
                                                   algorithm="dataset_surface")
                    kidx = np.asarray(flaeche.point_data["vtkOriginalPointIds"], int)
                    grid = flaeche
            except Exception as ex:             # noqa: BLE001
                self.log.appendPlainText(f"Oberfläche: {ex}")
        self._gitter_stand = stand
        self._gitter_zwischen = (grid, kidx)
        return grid, kidx

    #: Lage der Farbskalen: senkrecht am rechten Rand, Ergebnis aussen, der
    #: Schnittgroessenverlauf daneben. Unten links stehen die Kennwerte, unten
    #: rechts das Achsenkreuz.
    FARBSKALA = {"vertical": True, "position_x": 0.905, "position_y": 0.18,
                 "height": 0.5, "width": 0.055, "title_font_size": 13,
                 "label_font_size": 11, "fmt": "%.3g"}
    FARBSKALA_VERLAUF = dict(FARBSKALA, position_x=0.83)
    #: Platz, den der Ansichtswuerfel mit seiner Knopfzeile oben rechts braucht [px]
    WUERFEL_PLATZ = 165

    def _farbskala(self, verlauf: bool = False) -> dict:
        """Lage der Farbskala - so hoch, dass sie unter dem Wuerfel bleibt.

        In einem niedrigen Fenster reicht der Ansichtswuerfel weit herunter;
        die Skala wird dann kuerzer, statt unter seine Knopfzeile zu laufen.
        """
        skala = dict(self.FARBSKALA_VERLAUF if verlauf else self.FARBSKALA)
        try:
            hoch = float(self.plotter.render_window.GetSize()[1])
        except Exception:                   # noqa: BLE001
            hoch = 0.0
        if hoch > 0:
            frei = 1.0 - self.WUERFEL_PLATZ / hoch - skala["position_y"] - 0.08
            skala["height"] = float(min(skala["height"], max(0.22, frei)))
        return skala
    #: Schriftgroessen der Texte im Bild (pyvista verdoppelt sie in Pixel)
    SCHRIFT_KOPF = 7
    SCHRIFT_KENNWERTE = 6

    def redraw(self):
        # Die Kamera muss das Neuzeichnen ueberleben. plotter.clear() nimmt
        # alle Darsteller weg; das naechste add_mesh setzt die Kamera dann von
        # sich aus zurueck - man haette nach jedem Klick wieder die
        # Gesamtansicht vor sich und muesste sich neu hindrehen.
        kamera = None
        if getattr(self, "_kamera_steht", False):
            try:
                kamera = self.plotter.camera_position
            except Exception:               # noqa: BLE001
                kamera = None
        try:
            self.plotter.clear()
        except Exception:
            return
        self._vereinfacht = None
        m = self.model
        self._sicht_pruefen()
        if m.nn == 0:
            self._kamera_setzen(kamera)
            self.plotter.render()
            return
        with self._Stille(self.plotter):
            r = self._aufbauen(m)
        self._kamera_setzen(kamera)
        self.plotter.render()

    def _aufbauen(self, m):
        """Alle Darsteller der Ansicht aufbauen (ohne Zwischenbilder)."""
        show_edges = self.act_edges.isChecked()
        modus = getattr(self, "darstellung", "Voll")
        size = m.characteristic_size()
        r = self.current_result()
        u = None
        modal = False
        if r is not None:
            if getattr(r, "modes", None) is not None and self.cb_mode.count():
                u = r.modes[min(self.cb_mode.currentIndex(), len(r.modes) - 1)]
                modal = True
            elif getattr(r, "buckling_modes", None) is not None and self.cb_mode.count():
                u = r.buckling_modes[min(self.cb_mode.currentIndex(), len(r.buckling_modes) - 1)]
                modal = True
            else:
                u = vp.displacement_of(r)
        s = 0.0
        if u is not None:
            s, umax = self._scale(u)
            self.lbl_scale.setText(f"Faktor {s:.1f}   |  max = {umax*1000:.3f} mm"
                                   if not modal else f"Faktor {s:.1f} (normierte Eigenform)")

        # Was ins Bild kommt: die Sichtbarkeitsschalter Staebe, Flaechen,
        # Volumen und die ausgeblendeten Elemente. Bei Voll und Transparent
        # bekommen die Staebe ihre Querschnittskontur - dann kommen sie nicht
        # als Linie ins Gitter, sondern als eigener Koerper.
        typen = [t for t in vp.CELL_MAP
                 if t not in vp.TYPEN_STAEBE + vp.TYPEN_FLAECHEN + vp.TYPEN_VOLUMEN]
        staebe_an = self.act_staebe.isChecked()
        if staebe_an:
            typen += list(vp.TYPEN_STAEBE)
        if self.act_flaechen.isChecked():
            typen += list(vp.TYPEN_FLAECHEN)
        if self.act_volumen.isChecked():
            typen += list(vp.TYPEN_VOLUMEN)
        ausser = set(self.versteckt["elemente"])
        koerper_elems: list = []
        if staebe_an and modus in vp.KOERPERLICH:
            koerper_elems = [i for i, e in enumerate(m.elements)
                             if e.typ in vp.TYPEN_STAEBE and i not in ausser
                             and e.sec and e.sec in m.sections]
        grid, kidx = self._gitter(typen, ausser | set(koerper_elems))
        netze = []
        if grid.n_cells:
            netze.append((grid, kidx, "netz"))
        if koerper_elems:
            try:
                pd = vp.stab_koerper(m, koerper_elems)
                if pd is not None:
                    netze.append((pd, np.asarray(pd.point_data["knoten"], int), "stabkoerper"))
            except Exception as ex:         # noqa: BLE001
                self.log.appendPlainText(f"Stabkörper: {ex}")

        field = self.cb_field.currentText()
        point_scalars = cell_scalars = None
        name = ""
        clim = None
        if u is not None and not modal:
            point_scalars, cell_scalars, name = vp.result_field(m, r, field, self._util_map(field))
            if point_scalars is not None:
                ps = np.asarray(point_scalars, float)
                if np.isfinite(ps).any():
                    clim = [float(np.nanmin(ps)), float(np.nanmax(ps))]
        col = None
        if u is None and self.act_members.isChecked() and m.members:
            col = np.full(len(m.elements), np.nan)
            for k, mem in enumerate(m.members.values()):
                for e in mem.elements:
                    if 0 <= e < len(col):
                        col[e] = k % 12
        for netz, kn, nm in netze:
            eidx = np.asarray(netz.cell_data["elem"], int)
            breit = 3 if nm == "netz" else 1
            # Die Kanten eines Stabkoerpers sind Facetten des Profils, kein
            # FE-Netz - ein Rundstab mit 24 Mantelkanten wuerde schwarz.
            show_edges = self.act_edges.isChecked() and nm == "netz"
            if u is not None:
                warped = netz.copy()
                warped.points = netz.points + s * u[kn, :3]
                if self.cb_undeformed.isChecked():
                    self.plotter.add_mesh(netz, style="wireframe", color="#c8c8c8",
                                          opacity=0.35, line_width=1,
                                          name=f"undeformed_{nm}")
                if point_scalars is not None:
                    warped.point_data[name] = np.asarray(point_scalars)[kn]
                    self.plotter.add_mesh(warped, scalars=name, cmap="turbo", clim=clim,
                                          scalar_bar_args=dict(self._farbskala(), title=name),
                                          name=f"result_{nm}",
                                          **dict({"line_width": breit},
                                                 **vp.darstellung(modus, show_edges, True)))
                elif cell_scalars is not None and np.isfinite(np.asarray(cell_scalars, float)[eidx]).any():
                    warped.cell_data[name] = np.asarray(cell_scalars, float)[eidx]
                    self.plotter.add_mesh(warped, scalars=name, cmap="RdYlGn_r", clim=[0, 1.2],
                                          nan_color="#9fb8d0",
                                          scalar_bar_args=dict(self._farbskala(), title=name),
                                          name=f"result_{nm}",
                                          **dict({"line_width": 5 if nm == "netz" else 1},
                                                 **vp.darstellung(modus, show_edges, True)))
                else:
                    # ohne Werte fuer diesen Teil (etwa Schalen bei der
                    # Stabausnutzung): in der Farbe fuer "kein Wert"
                    farbe = "#9fb8d0" if cell_scalars is not None else "#4488cc"
                    self.plotter.add_mesh(warped, name=f"result_{nm}",
                                          **dict({"color": farbe, "line_width": breit},
                                                 **vp.darstellung(modus, show_edges)))
            elif col is not None:
                farbig = netz.copy()
                farbig.cell_data["Stab"] = col[eidx]
                self.plotter.add_mesh(farbig, scalars="Stab", cmap="tab20",
                                      nan_color="#8fb8d8", show_scalar_bar=False,
                                      name=f"model_{nm}",
                                      **dict({"line_width": 4 if nm == "netz" else 1},
                                             **vp.darstellung(modus, show_edges, True)))
            else:
                self.plotter.add_mesh(netz, name=f"model_{nm}",
                                      **dict({"color": "#8fb8d8", "line_width": breit},
                                             **vp.darstellung(modus, show_edges)))
        if u is not None and not modal:
            # Schnittgroessenverlauf
            q = self.cb_diagram.currentText()
            if q in vp.SCHNITTGROESSEN and (hasattr(r, "beam_end") or hasattr(r, "beam")):
                try:
                    sc = vp.diagram_scale(m, r, q) * self.sl_scale.value() / 30.0
                    pd = vp.beam_diagram(m, r, q, sc)
                    if pd is not None:
                        unit = "kN" if q in ("N", "Vy", "Vz") else "kNm"
                        pd["wert"] = pd["wert"] / 1e3
                        self.plotter.add_mesh(pd, scalars="wert", cmap="coolwarm", line_width=2,
                                              scalar_bar_args=dict(self._farbskala(True),
                                                                   title=f"{q} [{unit}]"),
                                              name="diagram")
                except Exception as ex:
                    self.log.appendPlainText(f"Verlauf: {ex}")
            if getattr(r, "contact", None):
                vp.add_contact_markers(self.plotter, m, r.contact, size)

        try:
            vp.add_supports(self.plotter, m, size, self.lagergroesse)
            if self.act_linien.isChecked():
                vp.add_linien(self.plotter, m, self.sel_linien,
                              ausser=self.versteckt["linien"], netz=self._linien_netz())
            vp.add_geometrie(self.plotter, m, modus=modus, netze=self._geometrie_netze())
            if getattr(self, "act_knoten", None) is None or self.act_knoten.isChecked():
                vp.add_nodes(self.plotter, m)
            self._auswahl_zeichnen()
            if self.act_loads.isChecked() and (u is None or not modal):
                vp.add_loads(self.plotter, m, m.case(), size, raender=self._raender(),
                             seiten=self._randseiten())
        except Exception as ex:
            self.log.appendPlainText(f"Darstellung: {ex}")
        if self.act_nodes.isChecked() and m.nn <= 3000:
            self.plotter.add_point_labels(m.nodes, [str(i) for i in range(m.nn)], font_size=10,
                                          point_size=1, shape=None, always_visible=True, name="nlabels")
        if self.act_elems.isChecked() and len(m.elements) <= 3000:
            cen = np.array([m.nodes[e.nodes].mean(axis=0) for e in m.elements])
            self.plotter.add_point_labels(cen, [str(i) for i in range(len(m.elements))], font_size=9,
                                          text_color="#a04000", point_size=1, shape=None,
                                          always_visible=True, name="elabels")
        if len(self.selection):
            self.plotter.add_points(m.nodes[self.selection], color="#ff8800", point_size=11,
                                    render_points_as_spheres=True, name="selection")
        self._kopfzeile_zeichnen(r, s if (u is not None and not modal) else 0.0)
        self._kennwerte_zeichnen(r)
        try:
            # Achsenkreuz unten rechts - unten links stehen die Kennwerte
            self.plotter.add_axes(viewport=(0.86, 0.0, 1.0, 0.16))
        except Exception:
            try:
                self.plotter.show_axes()
            except Exception:
                pass
        return r

    def _kopfzeile_zeichnen(self, r, faktor: float = 0.0) -> list:
        """Oben links: was die Ansicht zeigt.

        Ohne Ergebnis der aktive Lastfall, mit Ergebnis der Lastfall, die
        Kombination oder die Umhuellende samt Faerbung, Verlauf und
        Ueberhoehung. Ein Bild ohne diese Zeile ist im Statikdokument nicht
        pruefbar - man wuesste nicht, wovon es die Verformung zeigt.
        """
        zeigen = getattr(self, "act_kennwerte", None) is None or self.act_kennwerte.isChecked()
        self._kopfzeile_zeilen = []
        if not zeigen:
            return []
        try:
            if r is not None and self.results is not None:
                name = self.cb_mode.currentText() if self.cb_mode.count() else "Eigenform"
            elif r is not None:
                name = self.cb_result.currentText()
            else:
                name = ""
            zeilen = vp.kopfzeile(self.model, r, name,
                                  self.cb_field.currentText() if r is not None else "",
                                  self.cb_diagram.currentText() if r is not None else "",
                                  faktor)
        except Exception as ex:             # noqa: BLE001
            self.log.appendPlainText(f"Kopfzeile: {ex}")
            return []
        if not zeilen:
            return []
        self._kopfzeile_zeilen = zeilen
        try:
            # Oben links, aber **unterhalb** der Glasleiste: in einem schmalen
            # Fenster reicht die Leiste bis in die linke Ecke. VTK zaehlt die
            # Bildzeilen von unten.
            hoch = self.plotter.render_window.GetSize()[1]
            rand = (self.glasleiste.height() + 16) if getattr(self, "glasleiste", None) \
                else 46
            zh = int(self.SCHRIFT_KOPF * 2 * 1.25)
            y = hoch - rand - zh * len(zeilen)
            self.plotter.add_text("\n".join(zeilen), position=(12, max(y, 6)),
                                  font_size=self.SCHRIFT_KOPF, font="courier",
                                  color="#203040", name="kopfzeile")
        except Exception as ex:             # noqa: BLE001
            self.log.appendPlainText(f"Kopfzeile: {ex}")
        return zeilen

    def _kennwerte_zeichnen(self, r) -> list:
        """Die Kennzahlen des Ergebnisses als Text unten links in die Ansicht.

        Sie gehoeren ins **Bild**, nicht nur in eine Tabelle: wer eine Ansicht
        in den Bericht uebernimmt, hat die Zahlen damit gleich dabei - groesste
        Ausnutzung, kleinste und groesste Verformung, Verdrehung,
        Schnittgroesse, Auflagerkraft und Spannung, jeweils mit dem Ort. Die
        Farbskalen stehen rechts, damit sich nichts ueberdeckt.
        """
        zeigen = getattr(self, "act_kennwerte", None) is None or self.act_kennwerte.isChecked()
        if r is None or not zeigen:
            self._kennwerte_zeilen = []
            return []
        try:
            # Die Ausnutzung gehoert immer dazu - auch wenn gerade nach der
            # Verformung eingefaerbt wird. Sonst muesste man erst umschalten,
            # um die Zahl zu sehen, nach der zuerst gefragt wird.
            zeilen = vp.kennwerte(self.model, r, self._ausnutzung_map(),
                                  self.cb_diagram.currentText())
        except Exception as ex:             # noqa: BLE001
            self.log.appendPlainText(f"Kennwerte: {ex}")
            self._kennwerte_zeilen = []
            return []
        self._kennwerte_zeilen = zeilen
        if not zeilen:
            return []
        try:
            self.plotter.add_text("\n".join(zeilen), position=(12, 10),
                                  font_size=self.SCHRIFT_KENNWERTE, font="courier",
                                  color="#203040", name="kennwerte")
        except Exception as ex:             # noqa: BLE001
            self.log.appendPlainText(f"Kennwerte: {ex}")
        return zeilen

    def _kamera_setzen(self, kamera):
        """Die vor dem Neuzeichnen gemerkte Kamera wieder aufsetzen."""
        if kamera is not None:
            try:
                self.plotter.camera_position = kamera
                return
            except Exception:               # noqa: BLE001
                pass
        try:
            self.plotter.reset_camera()
            self._kamera_steht = True
        except Exception:                   # noqa: BLE001
            pass

    def zoom_alles(self):
        """Alles ins Bild holen - und zwar nur, wenn man es verlangt."""
        try:
            self.plotter.reset_camera()
            self._kamera_steht = True
            self.plotter.render()
        except Exception:                   # noqa: BLE001
            pass

    # ---- Sicht: ausblenden und wieder zeigen --------------------------
    def _ausgewaehlte_elemente(self) -> set:
        """Die Elementnummern zu allem, was gerade ausgewaehlt ist.

        Staebe ueber ihre Elemente, Flaechen und Koerper ueber ihr Netz,
        gewaehlte Knoten ueber die Elemente, die an ihnen haengen.
        """
        m = self.model
        elems: set = set()
        for name in self.sel_staebe:
            mem = m.members.get(name)
            if mem is not None:
                elems.update(int(e) for e in (mem.elements or []))
        for name in self.sel_flaechen:
            f = m.flaechen.get(name)
            if f is not None:
                elems.update(int(e) for e in f.elemente)
        for name in self.sel_koerper:
            k = m.koerper.get(name)
            if k is not None:
                elems.update(int(e) for e in k.elemente)
        if len(self.selection):
            knoten = {int(i) for i in self.selection}
            for i, e in enumerate(m.elements):
                if knoten.intersection(int(n) for n in e.nodes):
                    elems.add(i)
        return {e for e in elems if 0 <= e < len(m.elements)}

    def _sicht_merken(self):
        self._sicht_verlauf.append({k: set(v) for k, v in self.versteckt.items()})
        del self._sicht_verlauf[:-20]

    def _sicht_knoepfe(self):
        """Zurueck geht nur, wenn es einen Schritt gibt; Alles zeigen nur,
        wenn etwas ausgeblendet ist."""
        a = getattr(self, "act_sicht_zurueck", None)
        if a is not None:
            a.setEnabled(bool(self._sicht_verlauf))
        a = getattr(self, "act_alles_zeigen", None)
        if a is not None:
            a.setEnabled(any(self.versteckt.values()))

    def _sicht_pruefen(self):
        """Ein anderes Modell oder ein neues Netz: die Ausblendung passt nicht mehr."""
        m = self.model
        stand = (id(m), len(m.elements))
        if stand == self._sicht_stand:
            return
        alt = self._sicht_stand
        self._sicht_stand = stand
        if alt is None or alt[0] != stand[0]:
            self.versteckt = {k: set() for k in self.versteckt}
            self._sicht_verlauf = []
        else:
            # gleiches Modell, anderes Netz: die Elementnummern sind neu
            self.versteckt["elemente"] = set()
            for schritt in self._sicht_verlauf:
                schritt["elemente"] = set()
        self._sicht_knoepfe()

    def _auswahl_leeren(self):
        self.selection = np.array([], dtype=int)
        self.sel_linien, self.sel_flaechen = [], []
        self.sel_koerper, self.sel_staebe = [], []
        self._auswahl_register()

    def nur_auswahl_zeigen(self):
        """Alles ausser der Auswahl ausblenden - die Auswahl bleibt allein im Bild."""
        m = self.model
        elems = self._ausgewaehlte_elemente()
        flaechen = set(self.sel_flaechen)
        koerper = set(self.sel_koerper)
        for name in self.sel_koerper:
            k = m.koerper.get(name)
            if k is not None:
                flaechen.update(k.flaechen)
        linien = set(self.sel_linien)
        for name in flaechen:
            f = m.flaechen.get(name)
            if f is not None:
                linien.update(f.linien)
                for o in (f.oeffnungen or []):
                    linien.update(o)
        if not (elems or linien or flaechen or koerper):
            return self.error("Erst etwas auswählen - dann bleibt nur das im Bild.")
        self._sicht_merken()
        self.versteckt["elemente"] = set(range(len(m.elements))) - elems
        self.versteckt["linien"] = set(m.lines or {}) - linien
        self.versteckt["flaechen"] = set(m.flaechen or {}) - flaechen
        self.versteckt["koerper"] = set(m.koerper or {}) - koerper
        self._sicht_knoepfe()
        teile = [f"{n} {was}" for n, was in ((len(elems), "Elemente"), (len(koerper), "Körper"),
                                             (len(flaechen), "Flächen"), (len(linien), "Linien"))
                 if n]
        self.info("Nur die Auswahl im Bild (" + ", ".join(teile) + ") - "
                  "„Alles zeigen“ holt den Rest zurück")
        self.redraw()

    def auswahl_ausblenden(self):
        """Die ausgewaehlten Objekte aus dem Bild nehmen."""
        m = self.model
        elems = self._ausgewaehlte_elemente()
        if not (elems or self.sel_linien or self.sel_flaechen or self.sel_koerper):
            return self.error("Erst auswählen, was aus dem Bild soll.")
        self._sicht_merken()
        self.versteckt["elemente"] |= elems
        self.versteckt["linien"] |= set(self.sel_linien)
        self.versteckt["flaechen"] |= set(self.sel_flaechen)
        self.versteckt["koerper"] |= set(self.sel_koerper)
        for name in self.sel_koerper:
            k = m.koerper.get(name)
            if k is not None:
                self.versteckt["flaechen"].update(k.flaechen)
        teile = [f"{n} {was}" for n, was in ((len(elems), "Elemente"),
                                             (len(self.sel_koerper), "Körper"),
                                             (len(self.sel_flaechen), "Flächen"),
                                             (len(self.sel_linien), "Linien")) if n]
        self._auswahl_leeren()
        self._sicht_knoepfe()
        self.info("Ausgeblendet: " + ", ".join(teile) + " - „Vorherige Sicht“ holt sie zurück")
        self.redraw()

    def sicht_zurueck(self):
        """Den letzten Ausblendeschritt zuruecknehmen."""
        if not self._sicht_verlauf:
            return self.info("Keine vorherige Sicht - es ist nichts ausgeblendet worden")
        self.versteckt = self._sicht_verlauf.pop()
        self._sicht_knoepfe()
        self.info("Vorherige Sicht")
        self.redraw()

    def alles_zeigen(self):
        """Alle ausgeblendeten Objekte wieder ins Bild holen."""
        if not any(self.versteckt.values()):
            return self.info("Es ist nichts ausgeblendet")
        self._sicht_merken()
        self.versteckt = {k: set() for k in self.versteckt}
        self._sicht_knoepfe()
        self.info("Alles wieder im Bild")
        self.redraw()

    # ---- Datei -------------------------------------------------------
    def _protokoll_neu(self, titel: str):
        """Das Protokoll leeren - ein neues Modell faengt mit leerem Blatt an.

        Sonst steht unter dem eben geladenen Modell noch die Berechnung des
        vorigen, und man liest Zahlen, die nicht zu diesem Modell gehoeren.
        """
        try:
            from datetime import datetime
            self.log.clear()
            self.log.appendPlainText(f"--- {titel}  ({datetime.now():%d.%m.%Y %H:%M}) ---")
        except Exception:                   # noqa: BLE001
            pass

    def new_model(self):
        self._protokoll_neu("Neues Modell")
        self.model = Model("Neues Modell")
        self.__init_defaults()
        self.analysis = None
        self.results = None
        self.selection = np.array([], dtype=int)
        self.path = None
        self.refresh_all()
        self._refresh_title()

    def open_model(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Modell öffnen", "", "Statik3D (*.json)")
        if p:
            try:
                self._protokoll_neu(f"Modell geöffnet: {p}")
                self.model = Model.load(p)
                self.__init_defaults()
                self.analysis = None
                self.results = None
                self.selection = np.array([], dtype=int)
                self.path = p
                self.refresh_all()
                self._refresh_title()
                self.zoom_alles()
            except Exception as ex:
                self.error(str(ex))

    def save_model(self, ask=False):
        p = self.path
        if ask or not p:
            p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Modell speichern",
                                                         self.path or "modell.json", "Statik3D (*.json)")
        if p:
            self.model.save(p)
            self.path = p
            self._refresh_title()
            self.info(f"gespeichert: {p}")

    def export_model(self):
        """Modell in ein fremdes Format schreiben (Endung bestimmt das Format)."""
        from ..exporters import export_model as _ex, file_filter as _ff, FORMATS
        vor = os.path.splitext(self.path)[0] if self.path else self.model.name
        p, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Modell exportieren", vor + ".sdnf", _ff())
        if not p:
            return
        ext = os.path.splitext(p)[1].lower()
        if ext not in FORMATS:
            return self.error(
                f"Die Endung '{ext or '(keine)'}' gehört zu keinem Ausgabeformat.\n"
                "Möglich: " + ", ".join(sorted(FORMATS)))
        log = []
        try:
            out = _ex(self.model, p, results=self.current_result(), log=log)
        except Exception as ex:      # noqa: BLE001
            return self.error(f"Export fehlgeschlagen: {ex}")
        for z in log:
            self.log.appendPlainText(z)
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Export")
        box.setText("\n".join(log) or f"Geschrieben: {out}")
        b_open = box.addButton("Ordner öffnen", QtWidgets.QMessageBox.ActionRole)
        box.addButton(QtWidgets.QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is b_open:
            ordner = out if os.path.isdir(out) else os.path.dirname(os.path.abspath(out))
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(ordner))
        self.info(f"exportiert: {out}")

    def export_csv(self):
        r = self.current_result()
        if r is None or not hasattr(r, "beam_forces"):
            return self.error("Kein Einzelergebnis gewählt (Lastfall oder Kombination)")
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "CSV", "ergebnisse.csv", "CSV (*.csv)")
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"Ergebnis;{r.name}\nKnoten;x;y;z;ux;uy;uz;rx;ry;rz;Rx;Ry;Rz\n")
            for i in range(self.model.nn):
                x, y, z = self.model.nodes[i]
                f.write(f"{i};{x:.6f};{y:.6f};{z:.6f};"
                        + ";".join(f"{v:.6e}" for v in r.u[i]) + ";"
                        + ";".join(f"{v:.4f}" for v in r.reactions[i, :3]) + "\n")
            if r.beam_forces:
                f.write("\nElement;N1;N2;Vy1;Vy2;Vz1;Vz2;Mt1;My1;My2;Mz1;Mz2;sigma\n")
                for e, d in sorted(r.beam_forces.items()):
                    f.write(f"{e};{d['N'][0]:.3f};{d['N'][1]:.3f};{d['Vy'][0]:.3f};{d['Vy'][1]:.3f};"
                            f"{d['Vz'][0]:.3f};{d['Vz'][1]:.3f};{d['Mt'][0]:.3f};{d['My'][0]:.3f};"
                            f"{d['My'][1]:.3f};{d['Mz'][0]:.3f};{d['Mz'][1]:.3f};{d['sig_max']:.3f}\n")
        self.info(f"exportiert: {p}")

    def export_vtk(self):
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "VTK", "modell.vtu", "VTK (*.vtu)")
        if not p:
            return
        g = vp.to_grid(self.model)
        r = self.current_result()
        if r is not None:
            u = vp.displacement_of(r)
            if u is not None:
                g.point_data["u"] = u[:, :3]
            try:
                vm = r.node_vm if hasattr(r, "node_vm") else r.node_vm_max
                g.point_data["vonMises"] = np.nan_to_num(vm)
            except Exception:
                pass
        g.save(p)
        self.info(f"exportiert: {p}  (z.B. in ParaView zu öffnen)")

    def make_report(self):
        if self.analysis is None and self.results is None:
            return self.error("Zuerst berechnen")
        base = os.path.splitext(self.path)[0] if self.path else "bericht"
        d = ReportDialog(self, self.model, base + "_bericht.html")
        if not d.exec():
            return
        d.apply_meta(self.model)
        path = d.path.text().strip()
        if not path:
            return self.error("Kein Dateiname")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            from ..report import write_report
            write_report(self.model, self.analysis if self.analysis is not None else self.results,
                         path, fmt=d.format(), **d.options())
            self.info(f"Bericht geschrieben: {path}")
            if d.format() == "html":
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(os.path.abspath(path)))
        except Exception as ex:
            self.log.appendPlainText(traceback.format_exc())
            self.error(str(ex))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    # ---- Beispiele / Hilfe -------------------------------------------
    def load_example(self, which):
        from ..examples_lib import build_example
        try:
            self._protokoll_neu(f"Beispiel '{which}'")
            self.model = build_example(which)
            self.__init_defaults()
            self.analysis = None
            self.results = None
            self.selection = np.array([], dtype=int)
            self.path = None
            self.refresh_all()
            self.plotter.view_isometric()
            self.zoom_alles()
            self.info(f"Beispiel '{which}' geladen - jetzt BERECHNEN (F5)")
        except Exception as ex:
            self.log.appendPlainText(traceback.format_exc())
            self.error(str(ex))

    def open_doc(self, name):
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        p = os.path.join(here, "docs", name)
        if os.path.exists(p):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(p))
        else:
            self.error(f"Dokument nicht gefunden: {p}")

    # ---- Web-Server (Browser / Handy) ---------------------------------
    def start_web_server(self):
        """Startet den Web-Server fuer das aktuelle Modell; Handy und GUI teilen sich
        Modell und Ergebnisse (State.bound = dieses Fenster)."""
        if getattr(self, "web_server", None) is not None:
            return self._web_info()
        port, ok = QtWidgets.QInputDialog.getInt(self, "Browser / Handy", "Port:", 8080, 1024, 65535)
        if not ok:
            return
        key, ok = QtWidgets.QInputDialog.getText(
            self, "Browser / Handy", "Zugangsschlüssel (leer = ohne Schlüssel):", text="statik")
        if not ok:
            return
        try:
            from ..web import start_server_thread
            self.web_server, self.web_thread, self.web_state = start_server_thread(
                host="0.0.0.0", port=port, key=key.strip() or None, bound=self)
        except OSError as ex:
            self.web_server = None
            return self.error(f"Web-Server konnte nicht starten (Port {port} belegt?): {ex}")
        self.web_version = self.web_state.version
        self.web_timer = QtCore.QTimer(self)
        self.web_timer.timeout.connect(self._web_poll)
        self.web_timer.start(1000)
        self.info(f"Web-Server gestartet: {self.web_server.url}")
        self._web_info()

    def stop_web_server(self):
        srv = getattr(self, "web_server", None)
        if srv is None:
            return
        try:
            timer = getattr(self, "web_timer", None)
            if timer is not None:
                timer.stop()
            srv.shutdown()
            srv.server_close()
        finally:
            self.web_server = None
            self.info("Web-Server beendet")

    def _web_info(self):
        srv, st = self.web_server, self.web_state
        text = (f"Auf dem Handy oder Tablet im Browser öffnen (gleiches WLAN):\n\n{srv.url}\n\n"
                + (f"Zugangsschlüssel: {st.key}\n\n" if st.key else "Kein Zugangsschlüssel.\n\n")
                + f"Auf diesem Rechner: {srv.local_url}\n\n"
                "Handy und PC arbeiten am selben Modell; Änderungen und Ergebnisse erscheinen auf beiden Seiten.")
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Bedienung im Browser / auf dem Handy")
        box.setText(text)
        box.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        b_open = box.addButton("Im Browser öffnen", QtWidgets.QMessageBox.ActionRole)
        b_stop = box.addButton("Server beenden", QtWidgets.QMessageBox.DestructiveRole)
        box.addButton(QtWidgets.QMessageBox.Close)
        box.exec()
        if box.clickedButton() is b_open:
            url = srv.local_url + (f"?key={st.key}" if st.key else "")
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
        elif box.clickedButton() is b_stop:
            self.stop_web_server()

    def _web_poll(self):
        """Aenderungen vom Handy in die Oberflaeche uebernehmen."""
        st = getattr(self, "web_state", None)
        if st is None or st.version == self.web_version:
            return
        if self.worker is not None and self.worker.isRunning():
            return
        self.web_version = st.version
        try:
            self.selection = self.selection[self.selection < self.model.nn]
            self.refresh_all()
            self._fill_result_selector()
            self.show_results()
            self.info("Aktualisiert (Änderung aus dem Browser)")
        except Exception:      # noqa: BLE001
            self.log.appendPlainText(traceback.format_exc())

    def closeEvent(self, event):
        self.stop_web_server()
        super().closeEvent(event)

    # ---- Fensterrahmen: Version und Modell -----------------------------
    def _refresh_title(self):
        """Fenstertitel: Programm, Fassung und geöffnetes Modell."""
        from .. import update as upd
        try:
            ver = upd.version_label()
        except Exception:            # noqa: BLE001 - Titel darf nie scheitern
            ver = __version__
        name = os.path.basename(self.path) if getattr(self, "path", None) else \
            (self.model.name if getattr(self, "model", None) else "")
        self.setWindowTitle(f"Statik3D {ver}" + (f" - {name}" if name else "")
                            + " - FEM mit Lastfällen, Kontakt und EC3-Nachweisen")

    def _refresh_version_label(self):
        from .. import update as upd
        try:
            b = upd.build_info()
            txt = upd.version_label(long=True)
        except Exception:            # noqa: BLE001
            b, txt = {}, __version__
        self.lbl_version.setText("Version " + txt)
        self.lbl_version.setToolTip(
            "Statik3D " + txt + "\n"
            + ("Programmdatei (exe)" if b.get("kind") == "exe" else "Quellcode")
            + "\n" + str(b.get("dir", "")))

    # ---- Update (neueste Version von GitHub) ---------------------------
    def _build_update_button(self):
        from .. import update as upd
        self.btn_update = QtWidgets.QToolButton()
        self.btn_update.setText("Update suchen")
        self.btn_update.setToolTip(upd.describe())
        self.btn_update.clicked.connect(lambda: self.check_update())
        self.btn_update.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.btn_update.customContextMenuRequested.connect(lambda _p: self.update_report())
        self.btn_update.setVisible(False)
        self.statusBar().addPermanentWidget(self.btn_update)
        self._update_worker = None
        if os.environ.get("STATIK3D_NO_UPDATE_CHECK") != "1":
            QtCore.QTimer.singleShot(4000, lambda: self.check_update(quiet=True))

    def update_report(self):
        """Vollstaendiger Update-Befund zum Weitergeben (rechte Maustaste am Knopf)."""
        from .. import update as upd
        box = QtWidgets.QDialog(self)
        box.setWindowTitle("Update-Befund")
        lay = QtWidgets.QVBoxLayout(box)
        txt = QtWidgets.QPlainTextEdit()
        txt.setReadOnly(True)
        f = txt.font()
        f.setFamily("Courier New")
        txt.setFont(f)
        txt.setPlainText("Befund wird erstellt …")
        txt.setMinimumSize(720, 380)
        lay.addWidget(txt)
        zeile = QtWidgets.QHBoxLayout()
        b_copy = QtWidgets.QPushButton("In die Zwischenablage")
        b_copy.clicked.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(txt.toPlainText()))
        zeile.addWidget(b_copy)
        b_dl = QtWidgets.QPushButton("Download im Browser öffnen")
        b_dl.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(
            QtCore.QUrl(upd.DOWNLOAD_URL)))
        zeile.addWidget(b_dl)
        zeile.addStretch(1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(box.reject)
        zeile.addWidget(bb)
        lay.addLayout(zeile)
        self._run_update_worker(lambda progress: upd.diagnose(),
                                txt.setPlainText,
                                lambda m: txt.setPlainText(f"Befund fehlgeschlagen: {m}"))
        box.exec()

    def _run_update_worker(self, func, on_done, on_failed):
        if self._update_worker is not None and self._update_worker.isRunning():
            return
        w = SolveWorker(func)
        w.progress.connect(self.info)
        w.finished_ok.connect(on_done)
        w.failed.connect(lambda msg, tb: on_failed(msg))
        self._update_worker = w
        w.start()

    def check_update(self, quiet: bool = False):
        """Neueste Version bei GitHub erfragen (Hintergrund).

        Der Knopf in der Statusleiste erscheint nur, wenn es wirklich etwas zu
        holen gibt; sonst bleibt die Leiste den Arbeitsangaben vorbehalten.
        """
        from .. import update as upd
        # Ist der Austausch schon vorbereitet (heruntergeladen, aber das
        # Schliessen wurde abgelehnt), nicht erneut 200 MB laden, sondern den
        # Austausch anstossen.
        bat = getattr(self, "_update_bat", "")
        if bat and os.path.isfile(bat) and getattr(self, "_austausch_starten", None):
            if self.close():
                self._austausch_starten()
            return
        self.btn_update.setEnabled(False)
        if not quiet:
            self.btn_update.setVisible(True)
            self.btn_update.setText("Update wird gesucht…")

        def done(info):
            self.btn_update.setEnabled(True)
            self.btn_update.setVisible(bool(info.available) or not quiet)
            self.btn_update.setToolTip(info.message)
            if info.available:
                self.btn_update.setText("Update verfügbar")
                self.btn_update.setStyleSheet("font-weight:bold;color:#b8551e")
                self.info(info.message)
                if not quiet:
                    self._offer_update(info)
            else:
                self.btn_update.setText("Aktuell")
                self.btn_update.setStyleSheet("")
                if not quiet:
                    b = upd.build_info()
                    QtWidgets.QMessageBox.information(
                        self, "Update",
                        info.message
                        + f"\n\nInstalliert: {upd.version_label(long=True)}"
                        + f"\nNeueste Fassung: Build {info.latest_sha[:7] or '-'}"
                        + "\n\nMit der rechten Maustaste auf diesen Knopf gibt es den "
                          "vollständigen Befund zum Weitergeben.")

        def failed(msg):
            self.btn_update.setEnabled(True)
            self.btn_update.setText("Update suchen")
            if not quiet:
                self.error(f"Update-Prüfung fehlgeschlagen: {msg}")
            else:
                self.log.appendPlainText(f"Update-Prüfung: {msg}")

        self._run_update_worker(lambda progress: upd.check(), done, failed)

    def _offer_update(self, info):
        from .. import update as upd
        text = info.message + "\n\n"
        if info.kind == "exe":
            text += (f"Die neue Statik3D.exe ({info.size / 1e6:.0f} MB) wird heruntergeladen. "
                     "Statik3D wird danach beendet, ausgetauscht und neu gestartet.")
        else:
            text += ("Die Programmdateien werden aktualisiert (git pull bzw. Download von GitHub). "
                     "Statik3D startet danach neu.")
        text += "\n\nUngespeicherte Änderungen bitte vorher speichern."
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Update")
        box.setText(text)
        b_go = box.addButton("Jetzt aktualisieren", QtWidgets.QMessageBox.AcceptRole)
        box.addButton("Später", QtWidgets.QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not b_go:
            return
        self.btn_update.setEnabled(False)
        self.btn_update.setText("Update läuft…")
        self.progress_bar.setVisible(True)

        def run(progress):
            def prog(done, total):
                progress(f"Download {done / 1e6:.1f} / {total / 1e6:.1f} MB" if total
                         else f"Download {done / 1e6:.1f} MB")
            # restart=False: erst herunterladen und das Austauschskript
            # schreiben, aber noch nicht starten. Das Skript wartet darauf,
            # dass sich Statik3D beendet - es darf deshalb nicht laufen,
            # solange noch ein Dialog offen ist oder das Schliessen scheitert.
            return upd.apply(info, prog, restart=info.kind != "exe")

        def done(msg):
            self.progress_bar.setVisible(False)
            self.log.appendPlainText(msg)
            if info.kind != "exe":
                QtWidgets.QMessageBox.information(self, "Update", msg)
                return
            self.btn_update.setText("Statik3D wird beendet…")
            self._update_bat = upd.helper_path()
            # Erst schliessen (das fragt bei ungespeicherten Aenderungen nach).
            # Nur wenn das Fenster wirklich zu ist, laeuft der Austausch an.
            if not self.close():
                self.btn_update.setEnabled(True)
                self.btn_update.setText("Update bereit")
                self.log.appendPlainText(
                    "Der Austausch wartet: Statik3D wurde nicht beendet. "
                    "Über „Update bereit“ erneut auslösen.")
                return
            self._austausch_starten()

        def _austausch_starten(self=self):
            try:
                upd.start_helper(self._update_bat)
            except Exception as ex:            # noqa: BLE001
                QtWidgets.QMessageBox.warning(
                    None, "Update",
                    f"{ex}\n\nDie neue Fassung liegt bereit. Nach dem Beenden "
                    "von Statik3D das Skript ausführen:\n" + self._update_bat)
                return
            QtWidgets.QApplication.quit()

        self._austausch_starten = _austausch_starten

        def failed(msg):
            self.progress_bar.setVisible(False)
            self.btn_update.setEnabled(True)
            self.btn_update.setText("Update verfügbar")
            self.error(f"Update fehlgeschlagen: {msg}")

        self._run_update_worker(run, done, failed)

    def about(self):
        QtWidgets.QMessageBox.information(
            self, "Über Statik3D",
            f"<b>Statik3D {__version__}</b> - Finite-Elemente-Berechnung<br><br>"
            "Elemente: 3D-Balken/Fachwerk (Gelenke), Schale (CST+DKT), Tet4/Tet10/Hex8<br>"
            "Analysen: Lastfälle + Kombinationen (DIN EN 1990), Umhüllende, Modalanalyse, "
            "lineares Knicken, Kontakt (einseitige Lager, Spalt, Knoten-Fläche mit Reibung)<br>"
            "Nachweise: DIN EN 1993-1-1 (Querschnitt, Knicken, Biegedrillknicken, Interaktion), "
            "DIN EN 1993-1-9 (Ermüdung)<br>"
            "Import: DXF, IFC, SAF, RFEM-Tabellen, Abaqus, Nastran, STEP/IGES/STL<br>"
            "Parallel: Mehrkern und Rechnerfarm<br><br>"
            "<b>Gültigkeitsbereich:</b> kleine Verformungen, linear-elastisches Material, "
            "Kontakt als Penalty-Näherung ohne Lastgeschichte.<br>"
            "Das Programm ist gegen analytische Lösungen und Handrechnungen verifiziert, aber "
            "<b>nicht bauaufsichtlich geprüft</b>. Die Verantwortung für die Nachweise liegt "
            "beim Anwender.<br><br>Einheiten: m, N, Pa, kg/m³")


# ==========================================================================
def main(app=None, splash=None):
    """Die Oberflaeche starten.

    ``app`` und ``splash`` kommen aus run_gui.py: die Anwendung ist dort schon
    angelegt, damit das Startbild steht, waehrend dieses Modul (und mit ihm
    pyvista, VTK, numpy, scipy) geladen wird.
    """
    app = app or QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    try:
        from . import symbole as sym
        app.setWindowIcon(sym.programmsymbol())
    except Exception:                       # noqa: BLE001 - dann ohne Symbol
        pass
    if splash is not None:
        try:
            splash.melden("Oberfläche wird aufgebaut …")
        except Exception:                   # noqa: BLE001
            pass
    win = MainWindow()
    try:
        win.setWindowIcon(app.windowIcon())
    except Exception:                       # noqa: BLE001
        pass
    win.show()
    if splash is not None:
        try:
            splash.fertig(win)
        except Exception:                   # noqa: BLE001
            pass
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
