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

from ..model import Model, Material, Section, ShellProp, DOF_NAMES
from .. import solver, mesher, assemble

VTK_LINE, VTK_TRI, VTK_QUAD, VTK_TETRA, VTK_HEX, VTK_TET10 = 3, 5, 9, 10, 12, 24

CELL_MAP = {
    "beam": (VTK_LINE, 2), "truss": (VTK_LINE, 2),
    "shell3": (VTK_TRI, 3), "shell4": (VTK_QUAD, 4),
    "tet4": (VTK_TETRA, 4), "tet10": (VTK_TET10, 10), "hex8": (VTK_HEX, 8),
}


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


# ==========================================================================
class NumEdit(QtWidgets.QLineEdit):
    def __init__(self, value=0.0, width=80):
        super().__init__(f"{value:g}")
        self.setValidator(QtGui.QDoubleValidator(-1e30, 1e30, 10))
        self.setFixedWidth(width)

    def value(self) -> float:
        t = self.text().replace(",", ".").strip()
        try:
            return float(t)
        except ValueError:
            return 0.0


def row(*widgets) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        lay.addWidget(QtWidgets.QLabel(x) if isinstance(x, str) else x)
    lay.addStretch()
    return w


# ==========================================================================
class MaterialDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, mat: Material = None):
        super().__init__(parent)
        self.setWindowTitle("Material")
        m = mat or Material("Neu")
        self.name = QtWidgets.QLineEdit(m.name)
        self.E = NumEdit(m.E / 1e9, 100)
        self.nu = NumEdit(m.nu, 100)
        self.rho = NumEdit(m.rho, 100)
        self.fy = NumEdit((m.fy or 0) / 1e6, 100)
        f = QtWidgets.QFormLayout(self)
        f.addRow("Name", self.name)
        f.addRow("E-Modul [GPa]", self.E)
        f.addRow("Querdehnzahl [-]", self.nu)
        f.addRow("Dichte [kg/m³]", self.rho)
        f.addRow("Streckgrenze [MPa]", self.fy)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def result_material(self) -> Material:
        fy = self.fy.value() * 1e6
        return Material(self.name.text() or "Mat", self.E.value() * 1e9,
                        self.nu.value(), self.rho.value(), fy=fy if fy > 0 else None)


class SectionDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Querschnitt")
        self.name = QtWidgets.QLineEdit("Q1")
        self.typ = QtWidgets.QComboBox()
        self.typ.addItems(["Rechteck b×h", "Kreis d", "Rohr d/t",
                           "Doppel-T h/b/tw/tf", "frei (A, Iy, Iz, It)"])
        self.p = [NumEdit(0.1, 80) for _ in range(4)]
        self.free = [NumEdit(v, 90) for v in (1e-2, 1e-5, 1e-5, 1e-5)]
        f = QtWidgets.QFormLayout(self)
        f.addRow("Name", self.name)
        f.addRow("Typ", self.typ)
        f.addRow("Parameter [m]", row(*self.p))
        f.addRow("A / Iy / Iz / It", row(*self.free))
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def result_section(self) -> Section:
        n = self.name.text() or "Q"
        v = [x.value() for x in self.p]
        i = self.typ.currentIndex()
        if i == 0:
            return Section.rectangle(n, v[0], v[1])
        if i == 1:
            return Section.circle(n, v[0])
        if i == 2:
            return Section.pipe(n, v[0], v[1])
        if i == 3:
            return Section.i_profile(n, v[0], v[1], v[2], v[3])
        a = [x.value() for x in self.free]
        return Section(n, A=a[0], Iy=a[1], Iz=a[2], It=a[3])


# ==========================================================================
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Statik3D - FEM fuer Stab-, Flaechen- und Volumentragwerke")
        self.resize(1500, 950)
        self.model = Model("Neues Modell")
        self.model.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
        self.model.add_section(Section.rectangle("R 100/200", 0.1, 0.2))
        self.model.add_shell_prop(ShellProp("t = 10 mm", 0.010))
        self.results: solver.Results | None = None
        self.selection = np.array([], dtype=int)
        self.path = None

        self._build_viewport()
        self._build_panels()
        self._build_menu()
        self.statusBar().showMessage("Bereit")
        self.refresh_all()

    # ------------------------------------------------------------------
    def _build_viewport(self):
        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(central)
        self.plotter.set_background("white")
        lay.addWidget(self.plotter.interactor)
        self.setCentralWidget(central)

    def _build_menu(self):
        mb = self.menuBar()
        f = mb.addMenu("&Datei")
        f.addAction("Neu", self.new_model)
        f.addAction("Oeffnen…", self.open_model)
        f.addAction("Speichern…", self.save_model)
        f.addSeparator()
        f.addAction("CAD importieren (STEP/IGES/STL)…", self.import_cad)
        f.addAction("Ergebnisse als CSV…", self.export_csv)
        f.addAction("Netz + Ergebnisse als VTK…", self.export_vtk)
        f.addSeparator()
        f.addAction("Beenden", self.close)

        b = mb.addMenu("&Beispiele")
        b.addAction("Rahmen (Stabwerk)", lambda: self.load_example("frame"))
        b.addAction("Platte (Schalen)", lambda: self.load_example("plate"))
        b.addAction("Konsole (Volumen)", lambda: self.load_example("solid"))

        v = mb.addMenu("&Ansicht")
        v.addAction("Isometrisch", lambda: (self.plotter.view_isometric(),
                                            self.plotter.reset_camera()))
        v.addAction("XY (Draufsicht)", self.plotter.view_xy)
        v.addAction("XZ (Ansicht)", self.plotter.view_xz)
        v.addAction("YZ (Seitenansicht)", self.plotter.view_yz)
        v.addSeparator()
        self.act_edges = v.addAction("Kanten anzeigen")
        self.act_edges.setCheckable(True)
        self.act_edges.setChecked(True)
        self.act_edges.triggered.connect(self.redraw)

        h = mb.addMenu("&Hilfe")
        h.addAction("Ueber / Gueltigkeitsbereich", self.about)

    # ------------------------------------------------------------------
    def _build_panels(self):
        dock = QtWidgets.QDockWidget("Eingaben", self)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea)
        dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._tab_model(), "Modell")
        tabs.addTab(self._tab_mesh(), "Netz")
        tabs.addTab(self._tab_bc(), "Lager/Lasten")
        tabs.addTab(self._tab_solve(), "Berechnung")
        tabs.addTab(self._tab_results(), "Ergebnisse")
        tabs.setMinimumWidth(430)
        dock.setWidget(tabs)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)

    # ---- Tab 1: Modell ------------------------------------------------
    def _tab_model(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)

        lay.addWidget(QtWidgets.QLabel("<b>Materialien</b>"))
        self.tbl_mat = QtWidgets.QTableWidget(0, 4)
        self.tbl_mat.setHorizontalHeaderLabels(["Name", "E [GPa]", "ν", "ρ"])
        self.tbl_mat.horizontalHeader().setStretchLastSection(True)
        self.tbl_mat.setMaximumHeight(140)
        lay.addWidget(self.tbl_mat)
        b1 = QtWidgets.QPushButton("Material hinzufuegen…")
        b1.clicked.connect(self.add_material)
        lay.addWidget(b1)

        lay.addWidget(QtWidgets.QLabel("<b>Stabquerschnitte</b>"))
        self.tbl_sec = QtWidgets.QTableWidget(0, 4)
        self.tbl_sec.setHorizontalHeaderLabels(["Name", "A [m²]", "Iy [m⁴]", "Iz [m⁴]"])
        self.tbl_sec.horizontalHeader().setStretchLastSection(True)
        self.tbl_sec.setMaximumHeight(140)
        lay.addWidget(self.tbl_sec)
        b2 = QtWidgets.QPushButton("Querschnitt hinzufuegen…")
        b2.clicked.connect(self.add_section)
        lay.addWidget(b2)

        lay.addWidget(QtWidgets.QLabel("<b>Schalendicken</b>"))
        self.tbl_shell = QtWidgets.QTableWidget(0, 2)
        self.tbl_shell.setHorizontalHeaderLabels(["Name", "t [m]"])
        self.tbl_shell.horizontalHeader().setStretchLastSection(True)
        self.tbl_shell.setMaximumHeight(110)
        lay.addWidget(self.tbl_shell)
        self.ed_t = NumEdit(0.01, 80)
        b3 = QtWidgets.QPushButton("Dicke hinzufuegen")
        b3.clicked.connect(self.add_shell_prop)
        lay.addWidget(row("t [m]", self.ed_t, b3))

        self.lbl_info = QtWidgets.QLabel()
        self.lbl_info.setStyleSheet("color:#444")
        lay.addWidget(self.lbl_info)
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

        g = QtWidgets.QGroupBox("Stabzug")
        gl = QtWidgets.QVBoxLayout(g)
        self.beam_p1 = [NumEdit(0, 65) for _ in range(3)]
        self.beam_p2 = [NumEdit(v, 65) for v in (5, 0, 0)]
        self.beam_n = QtWidgets.QSpinBox(); self.beam_n.setRange(1, 500); self.beam_n.setValue(4)
        gl.addWidget(row("von", *self.beam_p1))
        gl.addWidget(row("bis", *self.beam_p2))
        bb = QtWidgets.QPushButton("Staebe erzeugen")
        bb.clicked.connect(self.make_beams)
        gl.addWidget(row("Teilung", self.beam_n, bb))
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
        self.bn = [QtWidgets.QSpinBox() for _ in range(3)]
        for s, v in zip(self.bn, (10, 3, 3)):
            s.setRange(1, 200); s.setValue(v)
        self.b_typ = QtWidgets.QComboBox(); self.b_typ.addItems(["hex8", "tet4"])
        gl.addWidget(row("lx, ly, lz", *self.bl))
        bq = QtWidgets.QPushButton("Volumennetz erzeugen")
        bq.clicked.connect(self.make_box)
        gl.addWidget(row("nx, ny, nz", *self.bn, self.b_typ, bq))
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("CAD-Import (gmsh)")
        gl = QtWidgets.QVBoxLayout(g)
        self.mesh_size = NumEdit(0.05, 80)
        self.mesh_order = QtWidgets.QComboBox(); self.mesh_order.addItems(["Tet10 (quadratisch)", "Tet4 (linear)"])
        self.mesh_dim = QtWidgets.QComboBox(); self.mesh_dim.addItems(["Volumen (3D)", "Schale (2D)"])
        gl.addWidget(row("Netzweite [m]", self.mesh_size, self.mesh_order))
        bi = QtWidgets.QPushButton("STEP / IGES / STL importieren…")
        bi.clicked.connect(self.import_cad)
        gl.addWidget(row(self.mesh_dim, bi))
        if not mesher.HAVE_GMSH:
            lbl = QtWidgets.QLabel("gmsh nicht installiert  →  pip install gmsh")
            lbl.setStyleSheet("color:#a00")
            gl.addWidget(lbl)
        lay.addWidget(g)

        bm = QtWidgets.QPushButton("Doppelte Knoten zusammenfuehren")
        bm.clicked.connect(self.do_merge)
        bd = QtWidgets.QPushButton("Netz loeschen")
        bd.clicked.connect(self.clear_mesh)
        lay.addWidget(row(bm, bd))
        lay.addStretch()
        return w

    # ---- Tab 3: Lager / Lasten ---------------------------------------
    def _tab_bc(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)

        g = QtWidgets.QGroupBox("Knotenauswahl (Koordinatenfenster)")
        gl = QtWidgets.QVBoxLayout(g)
        self.sel = [QtWidgets.QLineEdit() for _ in range(6)]
        for e, t in zip(self.sel, ["x min", "x max", "y min", "y max", "z min", "z max"]):
            e.setPlaceholderText(t)
            e.setFixedWidth(70)
        gl.addWidget(row("x", self.sel[0], self.sel[1],
                         "y", self.sel[2], self.sel[3]))
        bs = QtWidgets.QPushButton("Auswaehlen")
        bs.clicked.connect(self.do_select)
        ba = QtWidgets.QPushButton("Alle")
        ba.clicked.connect(self.select_all)
        gl.addWidget(row("z", self.sel[4], self.sel[5], bs, ba))
        self.lbl_sel = QtWidgets.QLabel("0 Knoten ausgewaehlt")
        gl.addWidget(self.lbl_sel)
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Lager auf Auswahl")
        gl = QtWidgets.QVBoxLayout(g)
        self.cb_dof = [QtWidgets.QCheckBox(n) for n in DOF_NAMES]
        gl.addWidget(row(*self.cb_dof[:3]))
        gl.addWidget(row(*self.cb_dof[3:]))
        b1 = QtWidgets.QPushButton("Lager setzen")
        b1.clicked.connect(self.set_support)
        b2 = QtWidgets.QPushButton("Einspannung")
        b2.clicked.connect(lambda: self.set_support(all_dofs=True))
        b3 = QtWidgets.QPushButton("Gelenkig")
        b3.clicked.connect(lambda: self.set_support(pinned=True))
        gl.addWidget(row(b1, b2, b3))
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Knotenlasten auf Auswahl")
        gl = QtWidgets.QVBoxLayout(g)
        self.ld = [NumEdit(0, 70) for _ in range(6)]
        gl.addWidget(row("Fx,Fy,Fz [N]", *self.ld[:3]))
        gl.addWidget(row("Mx,My,Mz [Nm]", *self.ld[3:]))
        self.ld_split = QtWidgets.QCheckBox("Summe gleichmaessig verteilen")
        self.ld_split.setChecked(True)
        bl = QtWidgets.QPushButton("Last aufbringen")
        bl.clicked.connect(self.add_load)
        gl.addWidget(row(self.ld_split, bl))
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Element- und Flaechenlasten")
        gl = QtWidgets.QVBoxLayout(g)
        self.q = [NumEdit(0, 70) for _ in range(3)]
        bq = QtWidgets.QPushButton("auf alle Staebe")
        bq.clicked.connect(self.add_beam_load)
        gl.addWidget(row("q [N/m]", *self.q, bq))
        self.p_face = NumEdit(-1000.0, 80)
        bf = QtWidgets.QPushButton("auf alle Schalen")
        bf.clicked.connect(self.add_face_load)
        gl.addWidget(row("p [N/m²]", self.p_face, bf))
        self.cb_g = QtWidgets.QCheckBox("Eigengewicht (g = 9,81 m/s² in −z)")
        self.cb_g.toggled.connect(self.toggle_gravity)
        gl.addWidget(self.cb_g)
        lay.addWidget(g)

        bc = QtWidgets.QPushButton("Alle Lager und Lasten loeschen")
        bc.clicked.connect(self.clear_bc)
        lay.addWidget(bc)
        lay.addStretch()
        return w

    # ---- Tab 4: Berechnung -------------------------------------------
    def _tab_solve(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.cb_analysis = QtWidgets.QComboBox()
        self.cb_analysis.addItems(["Lineare Statik",
                                   "Eigenschwingungen (Modalanalyse)",
                                   "Knicken / Beulen (Stabtragwerke)"])
        self.sp_modes = QtWidgets.QSpinBox()
        self.sp_modes.setRange(1, 50); self.sp_modes.setValue(6)
        lay.addWidget(row("Analyse", self.cb_analysis))
        lay.addWidget(row("Anzahl Eigenformen", self.sp_modes))
        bchk = QtWidgets.QPushButton("Modell pruefen")
        bchk.clicked.connect(self.do_check)
        lay.addWidget(bchk)
        bs = QtWidgets.QPushButton("BERECHNEN")
        bs.setStyleSheet("font-weight:bold; padding:8px;")
        bs.clicked.connect(self.do_solve)
        lay.addWidget(bs)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family: monospace; font-size: 11px;")
        lay.addWidget(self.log, 1)
        return w

    # ---- Tab 5: Ergebnisse -------------------------------------------
    def _tab_results(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.cb_field = QtWidgets.QComboBox()
        self.cb_field.addItems(["|u| Verschiebung", "ux", "uy", "uz",
                                "Vergleichsspannung", "keine Faerbung"])
        self.cb_field.currentIndexChanged.connect(self.redraw)
        lay.addWidget(row("Anzeige", self.cb_field))

        self.cb_mode = QtWidgets.QComboBox()
        self.cb_mode.currentIndexChanged.connect(self.redraw)
        lay.addWidget(row("Eigenform", self.cb_mode))

        self.sl_scale = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_scale.setRange(0, 100); self.sl_scale.setValue(30)
        self.sl_scale.valueChanged.connect(self.redraw)
        self.lbl_scale = QtWidgets.QLabel("")
        lay.addWidget(row("Ueberhoehung", self.sl_scale))
        lay.addWidget(self.lbl_scale)

        self.txt_res = QtWidgets.QPlainTextEdit()
        self.txt_res.setReadOnly(True)
        self.txt_res.setStyleSheet("font-family: monospace; font-size: 11px;")
        lay.addWidget(self.txt_res, 1)

        self.tbl_res = QtWidgets.QTableWidget(0, 5)
        self.tbl_res.setHorizontalHeaderLabels(
            ["Element", "N [kN]", "Vz [kN]", "My [kNm]", "σ [MPa]"])
        lay.addWidget(self.tbl_res, 1)
        return w

    # ==================================================================
    # Aktionen
    # ==================================================================
    def info(self, msg):
        self.log.appendPlainText(msg)
        self.statusBar().showMessage(msg, 5000)

    def error(self, msg):
        QtWidgets.QMessageBox.critical(self, "Fehler", msg)
        self.log.appendPlainText("FEHLER: " + msg)

    def refresh_all(self):
        for tbl, data, cols in (
                (self.tbl_mat, self.model.materials,
                 lambda k, v: [k, f"{v.E/1e9:g}", f"{v.nu:g}", f"{v.rho:g}"]),
                (self.tbl_sec, self.model.sections,
                 lambda k, v: [k, f"{v.A:.4g}", f"{v.Iy:.4g}", f"{v.Iz:.4g}"]),
                (self.tbl_shell, self.model.shells,
                 lambda k, v: [k, f"{v.t:g}"])):
            tbl.setRowCount(len(data))
            for r, (k, v) in enumerate(data.items()):
                for c, s in enumerate(cols(k, v)):
                    tbl.setItem(r, c, QtWidgets.QTableWidgetItem(s))
        for cb, keys in ((self.cb_mat, self.model.materials),
                         (self.cb_sec, self.model.sections),
                         (self.cb_shell, self.model.shells)):
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear(); cb.addItems(list(keys))
            if cur in keys:
                cb.setCurrentText(cur)
            cb.blockSignals(False)
        kinds = {}
        for e in self.model.elements:
            kinds[e.typ] = kinds.get(e.typ, 0) + 1
        self.lbl_info.setText(
            f"Knoten: {self.model.nn}   Elemente: {len(self.model.elements)}   "
            + ", ".join(f"{k}: {v}" for k, v in kinds.items())
            + f"\nLager: {len(self.model.supports)}   "
              f"Knotenlasten: {len(self.model.nodal_loads)}   "
              f"Stablasten: {len(self.model.beam_loads)}   "
              f"Flaechenlasten: {len(self.model.face_loads)}")
        self.redraw()

    # ---- Modell ------------------------------------------------------
    def add_material(self):
        d = MaterialDialog(self)
        if d.exec():
            self.model.add_material(d.result_material())
            self.refresh_all()

    def add_section(self):
        d = SectionDialog(self)
        if d.exec():
            self.model.add_section(d.result_section())
            self.refresh_all()

    def add_shell_prop(self):
        t = self.ed_t.value()
        if t > 0:
            self.model.add_shell_prop(ShellProp(f"t = {t*1000:g} mm", t))
            self.refresh_all()

    # ---- Netz --------------------------------------------------------
    def _mat(self):
        return self.cb_mat.currentText()

    def make_beams(self):
        try:
            mesher.line_of_beams(self.model, self._mat(), self.cb_sec.currentText(),
                                 [e.value() for e in self.beam_p1],
                                 [e.value() for e in self.beam_p2],
                                 self.beam_n.value())
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
                            typ=self.b_typ.currentText())
            mesher.merge_nodes(self.model)
            self.refresh_all()
        except Exception as ex:
            self.error(str(ex))

    def import_cad(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "CAD-Datei", "", "CAD (*.step *.stp *.iges *.igs *.brep *.stl)")
        if not path:
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            n = mesher.mesh_cad(self.model, path, self._mat(),
                                size=self.mesh_size.value(),
                                order=2 if self.mesh_order.currentIndex() == 0 else 1,
                                dim=3 if self.mesh_dim.currentIndex() == 0 else 2,
                                shell_prop=self.cb_shell.currentText())
            self.info(f"{n} Elemente vernetzt")
            self.refresh_all()
        except Exception as ex:
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
        self.__init_defaults()
        self.results = None
        self.selection = np.array([], dtype=int)
        self.refresh_all()

    def __init_defaults(self):
        if not self.model.materials:
            self.model.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
        if not self.model.sections:
            self.model.add_section(Section.rectangle("R 100/200", 0.1, 0.2))
        if not self.model.shells:
            self.model.add_shell_prop(ShellProp("t = 10 mm", 0.010))

    # ---- Auswahl / Randbedingungen -----------------------------------
    def _sel_val(self, i):
        t = self.sel[i].text().replace(",", ".").strip()
        return float(t) if t else None

    def do_select(self):
        self.selection = mesher.select_nodes(
            self.model, self._sel_val(0), self._sel_val(1), self._sel_val(2),
            self._sel_val(3), self._sel_val(4), self._sel_val(5), tol=1e-6)
        self.lbl_sel.setText(f"{len(self.selection)} Knoten ausgewaehlt")
        self.redraw()

    def select_all(self):
        self.selection = np.arange(self.model.nn)
        self.lbl_sel.setText(f"{len(self.selection)} Knoten ausgewaehlt")
        self.redraw()

    def set_support(self, all_dofs=False, pinned=False):
        if not len(self.selection):
            return self.error("Keine Knoten ausgewaehlt")
        if all_dofs:
            dofs = [0, 1, 2, 3, 4, 5]
        elif pinned:
            dofs = [0, 1, 2]
        else:
            dofs = [i for i, c in enumerate(self.cb_dof) if c.isChecked()]
        if not dofs:
            return self.error("Keine Freiheitsgrade angehakt")
        for n in self.selection:
            self.model.fix(int(n), dofs)
        self.refresh_all()

    def add_load(self):
        if not len(self.selection):
            return self.error("Keine Knoten ausgewaehlt")
        v = np.array([e.value() for e in self.ld])
        if self.ld_split.isChecked():
            v = v / len(self.selection)
        for n in self.selection:
            self.model.load_node(int(n), *v)
        self.refresh_all()

    def add_beam_load(self):
        q = [e.value() for e in self.q]
        n = 0
        for i, e in enumerate(self.model.elements):
            if e.typ in ("beam", "truss"):
                self.model.load_beam(i, *q)
                n += 1
        self.info(f"Streckenlast auf {n} Staebe")
        self.refresh_all()

    def add_face_load(self):
        p = self.p_face.value()
        n = 0
        for i, e in enumerate(self.model.elements):
            if e.typ in ("shell3", "shell4"):
                self.model.load_face(i, p)
                n += 1
        self.info(f"Flaechenlast auf {n} Schalen")
        self.refresh_all()

    def toggle_gravity(self, on):
        self.model.set_gravity(-9.81 if on else 0.0)

    def clear_bc(self):
        self.model.supports.clear()
        self.model.nodal_loads.clear()
        self.model.beam_loads.clear()
        self.model.face_loads.clear()
        self.model.gravity[:] = 0
        self.cb_g.setChecked(False)
        self.refresh_all()

    # ---- Berechnung --------------------------------------------------
    def do_check(self):
        msgs = self.model.check()
        self.log.appendPlainText("--- Modellpruefung ---")
        self.log.appendPlainText("\n".join(msgs) if msgs else "keine Auffaelligkeiten")

    def do_solve(self):
        msgs = [m for m in self.model.check() if m.startswith("FEHLER")]
        if msgs:
            return self.error("\n".join(msgs))
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self.log.appendPlainText("\n--- Berechnung gestartet ---")
        try:
            i = self.cb_analysis.currentIndex()
            if i == 0:
                self.results = solver.solve_static(self.model, self.info)
            elif i == 1:
                self.results = solver.solve_modal(self.model, self.sp_modes.value(),
                                                  self.info)
            else:
                self.results = solver.solve_buckling(self.model, self.sp_modes.value(),
                                                     self.info)
            self.log.appendPlainText(self.results.summary())
            self.show_results()
        except Exception as ex:
            self.log.appendPlainText(traceback.format_exc())
            self.error(str(ex))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    # ---- Ergebnisse --------------------------------------------------
    def show_results(self):
        r = self.results
        self.cb_mode.blockSignals(True)
        self.cb_mode.clear()
        if r.freqs is not None:
            self.cb_mode.addItems([f"{i+1}. Form  f = {f:.3f} Hz"
                                   for i, f in enumerate(r.freqs)])
        elif r.buckling_factors is not None:
            self.cb_mode.addItems([f"{i+1}. Form  η = {f:.3f}"
                                   for i, f in enumerate(r.buckling_factors)])
        self.cb_mode.blockSignals(False)

        self.txt_res.setPlainText(r.summary())
        rows = sorted(r.beam_forces.items())
        self.tbl_res.setRowCount(len(rows))
        for i, (e, d) in enumerate(rows):
            vals = [str(e), f"{d['N'][0]/1e3:.2f}", f"{d['Vz'][0]/1e3:.2f}",
                    f"{max(abs(d['My'][0]), abs(d['My'][1]))/1e3:.2f}",
                    f"{d['sig_max']/1e6:.1f}"]
            for c, s in enumerate(vals):
                self.tbl_res.setItem(i, c, QtWidgets.QTableWidgetItem(s))
        self.redraw()

    def _scale(self, u):
        umax = np.abs(u[:, :3]).max() if u.size else 0.0
        if umax <= 0:
            return 0.0, 0.0
        target = 0.08 * self.model.characteristic_size() * self.sl_scale.value() / 30.0
        return target / umax, umax

    def redraw(self):
        try:
            self.plotter.clear()
        except Exception:
            return
        if self.model.nn == 0:
            self.plotter.render()
            return
        grid = to_grid(self.model)
        show_edges = self.act_edges.isChecked()

        u = None
        r = self.results
        if r is not None:
            if r.modes is not None and self.cb_mode.count():
                u = r.modes[min(self.cb_mode.currentIndex(), len(r.modes) - 1)]
            elif r.buckling_modes is not None and self.cb_mode.count():
                u = r.buckling_modes[min(self.cb_mode.currentIndex(),
                                         len(r.buckling_modes) - 1)]
            else:
                u = r.u

        if grid.n_cells:
            if u is not None:
                s, umax = self._scale(u)
                self.lbl_scale.setText(
                    f"Faktor {s:.1f}   |  max = {umax*1000:.3f} mm"
                    if r.freqs is None else f"Faktor {s:.1f} (normierte Eigenform)")
                warped = grid.copy()
                warped.points = grid.points + s * u[:, :3]
                self.plotter.add_mesh(grid, style="wireframe", color="#c8c8c8",
                                      opacity=0.35, line_width=1)
                field = self.cb_field.currentText()
                scalars = None
                name = ""
                if field.startswith("|u|"):
                    scalars = np.linalg.norm(u[:, :3], axis=1) * 1000
                    name = "|u| [mm]"
                elif field in ("ux", "uy", "uz"):
                    scalars = u[:, "xyz".index(field[1])] * 1000
                    name = field + " [mm]"
                elif field.startswith("Vergleich") and r.node_vm is not None:
                    scalars = np.nan_to_num(r.node_vm) / 1e6
                    name = "σv [MPa]"
                if scalars is not None:
                    warped.point_data[name] = scalars
                    self.plotter.add_mesh(warped, scalars=name, cmap="turbo",
                                          show_edges=show_edges, line_width=2,
                                          scalar_bar_args={"title": name})
                else:
                    self.plotter.add_mesh(warped, color="#4488cc",
                                          show_edges=show_edges, line_width=2)
            else:
                self.plotter.add_mesh(grid, color="#8fb8d8", show_edges=show_edges,
                                      line_width=2)

        # Lager
        if self.model.supports:
            pts = self.model.nodes[[s.node for s in self.model.supports]]
            d = 0.012 * self.model.characteristic_size()
            self.plotter.add_mesh(pv.PolyData(pts).glyph(
                geom=pv.Cone(direction=(0, 0, 1), height=2 * d, radius=d),
                scale=False, orient=False), color="#207020")
        # Lasten
        if self.model.nodal_loads:
            pts, vec = [], []
            for l in self.model.nodal_loads:
                f = np.asarray(l.F[:3], float)
                if np.any(f):
                    pts.append(self.model.nodes[l.node])
                    vec.append(f)
            if pts:
                pd = pv.PolyData(np.array(pts))
                v = np.array(vec)
                v = v / (np.abs(v).max() or 1.0) * 0.06 * self.model.characteristic_size()
                pd["v"] = v
                self.plotter.add_mesh(pd.glyph(orient="v", scale="v", factor=1.0),
                                      color="#c02020")
        # ausgewaehlte Knoten
        if len(self.selection):
            self.plotter.add_points(self.model.nodes[self.selection],
                                    color="#ff8800", point_size=9,
                                    render_points_as_spheres=True)
        try:
            self.plotter.show_axes()
        except Exception:
            pass
        self.plotter.render()

    # ---- Datei -------------------------------------------------------
    def new_model(self):
        self.model = Model("Neues Modell")
        self.__init_defaults()
        self.results = None
        self.selection = np.array([], dtype=int)
        self.refresh_all()

    def open_model(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Modell oeffnen", "",
                                                     "Statik3D (*.json)")
        if p:
            try:
                self.model = Model.load(p)
                self.results = None
                self.path = p
                self.refresh_all()
                self.plotter.reset_camera()
            except Exception as ex:
                self.error(str(ex))

    def save_model(self):
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Modell speichern",
                                                     self.path or "modell.json",
                                                     "Statik3D (*.json)")
        if p:
            self.model.save(p)
            self.path = p
            self.info(f"gespeichert: {p}")

    def export_csv(self):
        if not self.results:
            return self.error("Keine Ergebnisse vorhanden")
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "CSV", "ergebnisse.csv",
                                                     "CSV (*.csv)")
        if not p:
            return
        r = self.results
        with open(p, "w", encoding="utf-8") as f:
            f.write("Knoten;x;y;z;ux;uy;uz;rx;ry;rz;Rx;Ry;Rz\n")
            for i in range(self.model.nn):
                x, y, z = self.model.nodes[i]
                f.write(f"{i};{x:.6f};{y:.6f};{z:.6f};"
                        + ";".join(f"{v:.6e}" for v in r.u[i]) + ";"
                        + ";".join(f"{v:.4f}" for v in r.reactions[i, :3]) + "\n")
            if r.beam_forces:
                f.write("\nElement;N1;N2;Vy1;Vz1;Mt1;My1;Mz1;My2;Mz2;sigma\n")
                for e, d in sorted(r.beam_forces.items()):
                    f.write(f"{e};{d['N'][0]:.3f};{d['N'][1]:.3f};{d['Vy'][0]:.3f};"
                            f"{d['Vz'][0]:.3f};{d['Mt'][0]:.3f};{d['My'][0]:.3f};"
                            f"{d['Mz'][0]:.3f};{d['My'][1]:.3f};{d['Mz'][1]:.3f};"
                            f"{d['sig_max']:.3f}\n")
        self.info(f"exportiert: {p}")

    def export_vtk(self):
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "VTK", "modell.vtu",
                                                     "VTK (*.vtu)")
        if not p:
            return
        g = to_grid(self.model)
        if self.results is not None:
            g.point_data["u"] = self.results.u[:, :3]
            if self.results.node_vm is not None:
                g.point_data["vonMises"] = np.nan_to_num(self.results.node_vm)
        g.save(p)
        self.info(f"exportiert: {p}  (z.B. in ParaView zu oeffnen)")

    # ---- Beispiele ---------------------------------------------------
    def load_example(self, which):
        from ..examples_lib import build_example
        try:
            self.model = build_example(which)
            self.results = None
            self.selection = np.array([], dtype=int)
            self.refresh_all()
            self.plotter.reset_camera()
            self.plotter.view_isometric()
            self.info(f"Beispiel '{which}' geladen - jetzt auf BERECHNEN klicken")
        except Exception as ex:
            self.error(str(ex))

    def about(self):
        QtWidgets.QMessageBox.information(
            self, "Ueber Statik3D",
            "<b>Statik3D</b> - lineare Finite-Elemente-Berechnung<br><br>"
            "Elemente: 3D-Balken/Fachwerk, Schale (CST+DKT), Tet4/Tet10/Hex8<br>"
            "Analysen: lineare Statik, Modalanalyse, lineares Knicken<br><br>"
            "<b>Gueltigkeitsbereich:</b> kleine Verformungen, linear-elastisch, "
            "kein Kontakt, keine Plastizitaet.<br>"
            "Das Programm ist verifiziert gegen analytische Loesungen, aber "
            "<b>nicht bauaufsichtlich geprueft</b>. Fuer Nachweise im Sinne der "
            "Landesbauordnungen ist gepruefte Software zu verwenden.<br><br>"
            "Einheiten: m, N, Pa, kg/m³")


# ==========================================================================
def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
