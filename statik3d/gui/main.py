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
                      parse_int_list)
from .worker import SolveWorker
from . import viewport as vp
from .viewport import to_grid  # noqa: F401  (Kompatibilitaet)

FIELDS = ["|u| Verschiebung", "ux", "uy", "uz", "Vergleichsspannung",
          "Ausnutzung EC3", "Ausnutzung Ermüdung", "Ausnutzung elastisch", "keine Färbung"]
DIAGRAMS = ["kein Verlauf", "N", "Vy", "Vz", "Mt", "My", "Mz"]


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

        self._build_viewport()
        self._build_panels()
        self._build_bottom()
        self._build_menu()
        self._refresh_title()
        self.statusBar().showMessage("Bereit")
        self.lbl_version = QtWidgets.QLabel()
        self.lbl_version.setToolTip("Installierte Fassung von Statik3D")
        self.statusBar().addPermanentWidget(self.lbl_version)
        self._refresh_version_label()
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(180)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.refresh_all()

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
        self.plotter = QtInteractor(central)
        self.plotter.set_background("white")
        lay.addWidget(self.plotter.interactor)
        self.setCentralWidget(central)
        try:
            self.plotter.enable_point_picking(callback=self._picked, show_message=False,
                                              left_clicking=True, show_point=False,
                                              pickable_window=False)
        except Exception:
            pass

    def _picked(self, point, *args):
        try:
            p = np.asarray(point, float).ravel()[:3]
        except Exception:
            return
        if self.model.nn == 0:
            return
        d = np.linalg.norm(self.model.nodes - p, axis=1)
        i = int(np.argmin(d))
        if d[i] > 0.05 * self.model.characteristic_size():
            return
        if i in self.selection:
            self.selection = self.selection[self.selection != i]
        else:
            self.selection = np.append(self.selection, i)
        self.lbl_sel.setText(f"{len(self.selection)} Knoten ausgewählt (zuletzt {i}: "
                             f"{np.round(self.model.nodes[i], 3)})")
        self.redraw()

    def _build_menu(self):
        mb = self.menuBar()
        f = mb.addMenu("&Datei")
        f.addAction("Neu", self.new_model, "Ctrl+N")
        f.addAction("Öffnen…", self.open_model, "Ctrl+O")
        f.addAction("Speichern", self.save_model, "Ctrl+S")
        f.addAction("Speichern unter…", lambda: self.save_model(True))
        f.addSeparator()
        f.addAction("Importieren (RFEM 6, HiCAD, DXF, IFC, SAF, INP, BDF, STEP…)…",
                    self.import_file, "Ctrl+I")
        f.addAction("Exportieren (SDNF, DSTV-NC, IFC, SAF, DXF, STL, VTK, HiCAD…)…",
                    self.export_model, "Ctrl+E")
        f.addAction("Ergebnisse als CSV…", self.export_csv)
        f.addAction("Netz + Ergebnisse als VTK…", self.export_vtk)
        f.addSeparator()
        f.addAction("Statischer Bericht…", self.make_report, "Ctrl+R")
        f.addSeparator()
        f.addAction("Beenden", self.close)

        e = mb.addMenu("&Bearbeiten")
        e.addAction("Modell prüfen", self.do_check)
        e.addAction("Doppelte Knoten zusammenführen", self.do_merge)
        e.addAction("Stäbe automatisch erkennen", self.auto_members)
        e.addAction("Kombinationen automatisch erzeugen…", self.auto_combinations)
        e.addAction("Einstellungen Nachweise…", self.design_settings)

        b = mb.addMenu("&Beispiele")
        for key, label in (("frame", "Rahmen (Stabwerk)"), ("truss", "Fachwerkträger"),
                           ("plate", "Platte (Schalen)"), ("solid", "Konsole (Volumen)"),
                           ("hall", "Hallenrahmen: Lastfälle, Kombinationen, EC3, Ermüdung"),
                           ("gate", "Stauwand (Stahlwasserbau): Schalen + Riegel, Wasserdruck"),
                           ("contact", "Kontakt: abhebendes Lager + Anschlag"),
                           ("friction", "Kontakt: Block mit Reibung (Volumen)")):
            b.addAction(label, lambda k=key: self.load_example(k))

        c = mb.addMenu("Be&rechnung")
        c.addAction("Alle Lastfälle + Kombinationen", lambda: self.do_solve("all"), "F5")
        c.addAction("Nur aktiver Lastfall", lambda: self.do_solve("case"))
        c.addAction("Eigenschwingungen", lambda: self.do_solve("modal"))
        c.addAction("Knicken", lambda: self.do_solve("buckling"))
        c.addSeparator()
        c.addAction("Nachweise EC3 (nach Berechnung)", self.do_design)
        c.addAction("Ermüdungsnachweis (nach Berechnung)", self.do_fatigue)
        c.addSeparator()
        c.addAction("Bedienung im Browser / auf dem Handy…", self.start_web_server)

        v = mb.addMenu("&Ansicht")
        v.addAction("Isometrisch", lambda: (self.plotter.view_isometric(), self.plotter.reset_camera()))
        v.addAction("XY (Draufsicht)", self.plotter.view_xy)
        v.addAction("XZ (Ansicht)", self.plotter.view_xz)
        v.addAction("YZ (Seitenansicht)", self.plotter.view_yz)
        v.addAction("Zoom alles", self.plotter.reset_camera)
        v.addSeparator()
        self.act_edges = v.addAction("Kanten anzeigen"); self.act_edges.setCheckable(True); self.act_edges.setChecked(True)
        self.act_nodes = v.addAction("Knotennummern"); self.act_nodes.setCheckable(True)
        self.act_elems = v.addAction("Elementnummern"); self.act_elems.setCheckable(True)
        self.act_loads = v.addAction("Lasten des aktiven Lastfalls"); self.act_loads.setCheckable(True); self.act_loads.setChecked(True)
        self.act_members = v.addAction("Stäbe farbig"); self.act_members.setCheckable(True)
        for a in (self.act_edges, self.act_nodes, self.act_elems, self.act_loads, self.act_members):
            a.triggered.connect(self.redraw)

        h = mb.addMenu("&Hilfe")
        h.addAction("Benutzerhandbuch", lambda: self.open_doc("Benutzerhandbuch.md"))
        h.addAction("Theoriehandbuch", lambda: self.open_doc("Theoriehandbuch.md"))
        h.addAction("Schnittstellen (Import)", lambda: self.open_doc("Schnittstellen.md"))
        h.addAction("Rechnerfarm", lambda: self.open_doc("Rechnerfarm.md"))
        h.addSeparator()
        h.addAction("Nach Update suchen…", self.check_update)
        h.addAction("Über / Gültigkeitsbereich", self.about)
        self._build_update_button()

    # ------------------------------------------------------------------
    def _build_panels(self):
        dock = QtWidgets.QDockWidget("Eingaben", self)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea)
        dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.addTab(self._scroll(self._tab_model()), "Modell")
        self.tabs.addTab(self._scroll(self._tab_mesh()), "Netz")
        self.tabs.addTab(self._scroll(self._tab_bc()), "Lager/Lasten")
        self.tabs.addTab(self._scroll(self._tab_cases()), "Lastfälle")
        self.tabs.addTab(self._scroll(self._tab_contact()), "Kontakt")
        self.tabs.addTab(self._scroll(self._tab_design()), "Nachweise")
        self.tabs.addTab(self._scroll(self._tab_solve()), "Berechnung")
        self.tabs.addTab(self._scroll(self._tab_results()), "Ergebnisse")
        self.tabs.setMinimumWidth(470)
        dock.setWidget(self.tabs)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)

    @staticmethod
    def _scroll(w):
        s = QtWidgets.QScrollArea()
        s.setWidgetResizable(True)
        s.setWidget(w)
        return s

    def _build_bottom(self):
        dock = QtWidgets.QDockWidget("Protokoll und Tabellen", self)
        dock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        tabs = QtWidgets.QTabWidget()
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family: monospace; font-size: 11px;")
        tabs.addTab(self.log, "Protokoll")
        self.tbl_beam = QtWidgets.QTableWidget(0, 10)
        self.tbl_beam.setHorizontalHeaderLabels(
            ["Element", "N1 [kN]", "N2 [kN]", "Vz1 [kN]", "Vz2 [kN]", "My1 [kNm]", "My2 [kNm]",
             "Mz max [kNm]", "σ [MPa]", "Ausn."])
        tabs.addTab(self.tbl_beam, "Stabkräfte")
        self.tbl_react = QtWidgets.QTableWidget(0, 7)
        self.tbl_react.setHorizontalHeaderLabels(["Knoten", "Rx [kN]", "Ry [kN]", "Rz [kN]",
                                                  "Mx [kNm]", "My [kNm]", "Mz [kNm]"])
        tabs.addTab(self.tbl_react, "Auflagerkräfte")
        self.tbl_env = QtWidgets.QTableWidget(0, 6)
        self.tbl_env.setHorizontalHeaderLabels(["Element", "Größe", "min", "Kombination", "max", "Kombination"])
        tabs.addTab(self.tbl_env, "Umhüllende")
        self.tbl_design = QtWidgets.QTableWidget(0, 10)
        tabs.addTab(self.tbl_design, "Nachweise EC3")
        self.tbl_fat = QtWidgets.QTableWidget(0, 9)
        tabs.addTab(self.tbl_fat, "Ermüdung")
        self.tbl_contact = QtWidgets.QTableWidget(0, 6)
        self.tbl_contact.setHorizontalHeaderLabels(["Knoten", "Art", "Status", "Fn [kN]", "Ft [kN]", "Spalt [mm]"])
        tabs.addTab(self.tbl_contact, "Kontakt")
        self.bottom_tabs = tabs
        dock.setWidget(tabs)
        dock.setMinimumHeight(190)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock)

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

        lay.addWidget(QtWidgets.QLabel("<b>Materialien</b>"))
        self.tbl_mat = QtWidgets.QTableWidget(0, 5)
        self.tbl_mat.setHorizontalHeaderLabels(["Name", "E [GPa]", "ν", "ρ", "fy [MPa]"])
        self.tbl_mat.horizontalHeader().setStretchLastSection(True)
        self.tbl_mat.setMaximumHeight(120)
        lay.addWidget(self.tbl_mat)
        b1 = QtWidgets.QPushButton("Material hinzufügen…")
        b1.clicked.connect(self.add_material)
        bd = QtWidgets.QPushButton("Löschen")
        bd.clicked.connect(lambda: self._delete_row(self.tbl_mat, self.model.materials))
        lay.addWidget(row(b1, bd))

        lay.addWidget(QtWidgets.QLabel("<b>Stabquerschnitte</b>"))
        self.tbl_sec = QtWidgets.QTableWidget(0, 5)
        self.tbl_sec.setHorizontalHeaderLabels(["Name", "Typ", "A [cm²]", "Iy [cm⁴]", "Wpl,y [cm³]"])
        self.tbl_sec.horizontalHeader().setStretchLastSection(True)
        self.tbl_sec.setMaximumHeight(120)
        lay.addWidget(self.tbl_sec)
        b2 = QtWidgets.QPushButton("Querschnitt hinzufügen (Profildatenbank)…")
        b2.clicked.connect(self.add_section)
        bd2 = QtWidgets.QPushButton("Löschen")
        bd2.clicked.connect(lambda: self._delete_row(self.tbl_sec, self.model.sections))
        lay.addWidget(row(b2, bd2))

        lay.addWidget(QtWidgets.QLabel("<b>Schalendicken</b>"))
        self.tbl_shell = QtWidgets.QTableWidget(0, 2)
        self.tbl_shell.setHorizontalHeaderLabels(["Name", "t [m]"])
        self.tbl_shell.horizontalHeader().setStretchLastSection(True)
        self.tbl_shell.setMaximumHeight(90)
        lay.addWidget(self.tbl_shell)
        self.ed_t = NumEdit(0.01, 80)
        b3 = QtWidgets.QPushButton("Dicke hinzufügen")
        b3.clicked.connect(self.add_shell_prop)
        lay.addWidget(row("t [m]", self.ed_t, b3))

        lay.addWidget(QtWidgets.QLabel("<b>Elemente ändern</b>"))
        self.ed_elist = QtWidgets.QLineEdit()
        self.ed_elist.setPlaceholderText("Element-Nr., z.B. 0-7, 12 (leer = Auswahl-Knoten)")
        self.cb_assign_sec = QtWidgets.QComboBox()
        self.cb_assign_mat = QtWidgets.QComboBox()
        ba = QtWidgets.QPushButton("Zuweisen")
        ba.clicked.connect(self.assign_props)
        lay.addWidget(self.ed_elist)
        lay.addWidget(row("Querschnitt", self.cb_assign_sec, "Material", self.cb_assign_mat, ba))
        self.ed_hinge = QtWidgets.QComboBox()
        self.ed_hinge.addItems(["Gelenk: keines", "Gelenk Anfang (My, Mz)", "Gelenk Ende (My, Mz)",
                                "Gelenk beide Enden", "Vollgelenk beide Enden (Mt, My, Mz)"])
        bh = QtWidgets.QPushButton("Gelenke setzen")
        bh.clicked.connect(self.set_hinges)
        lay.addWidget(row(self.ed_hinge, bh))

        self.lbl_info = QtWidgets.QLabel()
        self.lbl_info.setStyleSheet("color:#444")
        self.lbl_info.setWordWrap(True)
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

        g = QtWidgets.QGroupBox("Anschluss")
        gl = QtWidgets.QVBoxLayout(g)
        b8 = QtWidgets.QPushButton("Anschluss anlegen…")
        b8.setToolTip("Anschlusstyp wählen und auf ein Stabende anwenden: Kopfplatte,\n"
                      "Laschenstoß oder Diagonalanschluss. Der Vorschlag folgt aus\n"
                      "Profil und Schnittgrößen und lässt sich ändern.")
        b8.clicked.connect(self.add_joint)
        b9 = QtWidgets.QPushButton("Anschlüsse zeigen")
        b9.setToolTip("Angelegte Anschlüsse mit Nachweisen auflisten")
        b9.clicked.connect(self.show_joints)
        gl.addWidget(row(b8, b9))
        self.lbl_joints = QtWidgets.QLabel("keine Anschlüsse")
        self.lbl_joints.setWordWrap(True)
        gl.addWidget(self.lbl_joints)
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

    def _fill(self, tbl: QtWidgets.QTableWidget, rows, header=None):
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

    def _delete_row(self, tbl, mapping: dict):
        r = tbl.currentRow()
        if r < 0:
            return
        key = tbl.item(r, 0).text()
        if key in mapping and len(mapping) > 1:
            del mapping[key]
            self.refresh_all()

    def refresh_all(self):
        m = self.model
        for k, e in self.ed_meta.items():
            e.setText(m.meta.get(k, ""))
        self._fill(self.tbl_mat, [[k, f"{v.E/1e9:g}", f"{v.nu:g}", f"{v.rho:g}",
                                   f"{(v.fy or 0)/1e6:g}"] for k, v in m.materials.items()])
        self._fill(self.tbl_sec, [[k, v.typ, f"{v.A*1e4:.2f}", f"{v.Iy*1e8:.1f}",
                                   f"{v.Wpl_y*1e6:.1f}"] for k, v in m.sections.items()])
        self._fill(self.tbl_shell, [[k, f"{v.t:g}"] for k, v in m.shells.items()])
        for cb, keys in ((self.cb_mat, m.materials), (self.cb_sec, m.sections),
                         (self.cb_shell, m.shells), (self.cb_assign_sec, m.sections),
                         (self.cb_assign_mat, m.materials)):
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear(); cb.addItems(list(keys))
            if cur in keys:
                cb.setCurrentText(cur)
            cb.blockSignals(False)
        kinds = {}
        for e in m.elements:
            kinds[e.typ] = kinds.get(e.typ, 0) + 1
        n_loads = sum(lc.n_loads for lc in m.load_cases.values())
        self.lbl_info.setText(
            f"Knoten: {m.nn}   Elemente: {len(m.elements)}   "
            + ", ".join(f"{k}: {v}" for k, v in kinds.items())
            + f"\nLager: {len(m.supports)}   Lasten gesamt: {n_loads}   Lastfälle: {len(m.load_cases)}   "
              f"Kombinationen: {len(m.combinations)}   Stäbe: {len(m.members)}   "
              f"Kontakt: {len(m.contact_supports) + len(m.gap_elements) + len(m.contact_pairs)}"
            + (f"\nLinienlager: {len(m.line_supports)}   Flächenlager: {len(m.surface_supports)}   "
               f"Gelenkdefinitionen: {len(m.hinges)}" if (m.line_supports or m.surface_supports
                                                          or m.hinges) else ""))
        self.refresh_cases()
        self.refresh_contact()
        self.refresh_members()
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
            self.plotter.reset_camera()
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

    # ---- Auswahl / Randbedingungen -----------------------------------
    def _sel_val(self, i):
        t = self.sel[i].text().replace(",", ".").strip()
        return float(t) if t else None

    def _set_selection(self, sel):
        self.selection = np.asarray(sel, dtype=int)
        self.lbl_sel.setText(f"{len(self.selection)} Knoten ausgewählt")
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
        """Anschluss am gewaehlten Stabende anlegen."""
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
        if not hasattr(self, "joints"):
            self.joints = []
        t._forces = {k: d.sp[k].value() * 1e3 for k in d.sp}
        if isinstance(t, type(t)) and t.__class__.__name__ == "Gusset":
            t._forces = {"N": t._forces.get("N", 0.0)}
        self.joints.append(t)
        kind = d.fe_kind()
        if kind:
            log = []
            teil = t.build(kind=kind, log=log)
            teil.meta["bauteil"] = t.name
            path = os.path.join(os.path.dirname(self.path or "."),
                                f"{t.name.replace(' ', '_')}.json")
            try:
                teil.save(path)
                log.append(f"Teilmodell gespeichert: {path}")
            except OSError as ex:
                log.append(f"Teilmodell konnte nicht gespeichert werden: {ex}")
            QtWidgets.QMessageBox.information(
                self, "Teilmodell des Anschlusses", "\n".join(log))
        self._refresh_joints()
        self.info(f"Anschluss '{t.name}' angelegt")

    def _refresh_joints(self):
        js = getattr(self, "joints", [])
        if not js:
            self.lbl_joints.setText("keine Anschlüsse")
            return
        zeilen = []
        for t in js:
            try:
                j = t.design(**getattr(t, "_forces", {}))
                zeilen.append(f"{t.name}: eta = {j.eta:.2f} ({j.massgebend})")
            except Exception:            # noqa: BLE001
                zeilen.append(t.name)
        self.lbl_joints.setText("\n".join(zeilen))

    def show_joints(self):
        js = getattr(self, "joints", [])
        if not js:
            return self.error("Es wurde noch kein Anschluss angelegt")
        text = "\n\n".join(t.describe() for t in js)
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Anschlüsse")
        box.setText(text)
        box.exec()

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
        lc.nodal_loads.clear(); lc.beam_loads.clear(); lc.face_loads.clear(); lc.temp_loads.clear()
        lc.gravity = [0.0, 0.0, 0.0]
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
        self.txt_res.setPlainText("\n".join(lines))
        # Tabellen
        if hasattr(r, "beam_forces"):
            util_map = self._util_map("Ausnutzung EC3") or {}
            rows = []
            for e, d in sorted(r.beam_forces.items()):
                u = util_map.get(e, d["util"])
                rows.append([e, f"{d['N'][0]/1e3:.2f}", f"{d['N'][1]/1e3:.2f}",
                             f"{d['Vz'][0]/1e3:.2f}", f"{d['Vz'][1]/1e3:.2f}",
                             f"{d['My'][0]/1e3:.2f}", f"{d['My'][1]/1e3:.2f}",
                             f"{max(abs(d['Mz'][0]), abs(d['Mz'][1]))/1e3:.2f}",
                             f"{d['sig_max']/1e6:.1f}", f"{u:.3f}" if u is not None else "-"])
            self._fill(self.tbl_beam, rows)
            react = []
            for s in sorted({s.node for s in self.model.supports} | {c.node for c in self.model.contact_supports}):
                R = r.reactions[s]
                react.append([s] + [f"{v/1e3:.2f}" for v in R])
            self._fill(self.tbl_react, react)
            self._fill(self.tbl_contact, [[c["node"], c["kind"], c["status"], f"{c['Fn']/1e3:.2f}",
                                           f"{c['Ft']/1e3:.2f}", f"{c['gap']*1e3:.3f}"] for c in r.contact])
            self._fill(self.tbl_env, [])
        elif hasattr(r, "extreme_table"):
            rows = [[e, k, f"{mn/1e3:.2f}", c1, f"{mx/1e3:.2f}", c2] for e, k, mn, c1, mx, c2 in r.extreme_table()]
            self._fill(self.tbl_env, rows)
            self._fill(self.tbl_beam, [])
            react = []
            for s in sorted({s.node for s in self.model.supports}):
                react.append([s] + [f"{r.r_min[s, i]/1e3:.2f} / {r.r_max[s, i]/1e3:.2f}" for i in range(6)])
            self._fill(self.tbl_react, react)
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
        m = self.model
        if m.nn == 0:
            self.plotter.render()
            return
        grid = vp.to_grid(m)
        show_edges = self.act_edges.isChecked()
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

        if grid.n_cells:
            if u is not None:
                s, umax = self._scale(u)
                self.lbl_scale.setText(f"Faktor {s:.1f}   |  max = {umax*1000:.3f} mm"
                                       if not modal else f"Faktor {s:.1f} (normierte Eigenform)")
                warped = grid.copy()
                warped.points = grid.points + s * u[:, :3]
                if self.cb_undeformed.isChecked():
                    self.plotter.add_mesh(grid, style="wireframe", color="#c8c8c8",
                                          opacity=0.35, line_width=1, name="undeformed")
                field = self.cb_field.currentText()
                point_scalars = cell_scalars = None
                name = ""
                if not modal:
                    point_scalars, cell_scalars, name = vp.result_field(m, r, field, self._util_map(field))
                if point_scalars is not None:
                    warped.point_data[name] = point_scalars
                    self.plotter.add_mesh(warped, scalars=name, cmap="turbo", show_edges=show_edges,
                                          line_width=3, scalar_bar_args={"title": name}, name="result")
                elif cell_scalars is not None:
                    warped.cell_data[name] = cell_scalars
                    self.plotter.add_mesh(warped, scalars=name, cmap="RdYlGn_r", clim=[0, 1.2],
                                          show_edges=show_edges, line_width=5, nan_color="#9fb8d0",
                                          scalar_bar_args={"title": name}, name="result")
                else:
                    self.plotter.add_mesh(warped, color="#4488cc", show_edges=show_edges,
                                          line_width=3, name="result")
                # Schnittgroessenverlauf
                q = self.cb_diagram.currentText()
                if q in ("N", "Vy", "Vz", "Mt", "My", "Mz") and not modal and \
                        (hasattr(r, "beam_end") or hasattr(r, "beam")):
                    try:
                        sc = vp.diagram_scale(m, r, q) * self.sl_scale.value() / 30.0
                        pd = vp.beam_diagram(m, r, q, sc)
                        if pd is not None:
                            unit = "kN" if q in ("N", "Vy", "Vz") else "kNm"
                            pd["wert"] = pd["wert"] / 1e3
                            self.plotter.add_mesh(pd, scalars="wert", cmap="coolwarm", line_width=2,
                                                  scalar_bar_args={"title": f"{q} [{unit}]"},
                                                  name="diagram")
                    except Exception as ex:
                        self.log.appendPlainText(f"Verlauf: {ex}")
                if getattr(r, "contact", None):
                    vp.add_contact_markers(self.plotter, m, r.contact, size)
            else:
                if self.act_members.isChecked() and m.members:
                    col = np.full(len(m.elements), np.nan)
                    for k, mem in enumerate(m.members.values()):
                        for e in mem.elements:
                            col[e] = k % 12
                    grid.cell_data["Stab"] = col
                    self.plotter.add_mesh(grid, scalars="Stab", cmap="tab20", show_edges=show_edges,
                                          line_width=4, nan_color="#8fb8d8", show_scalar_bar=False,
                                          name="model")
                else:
                    self.plotter.add_mesh(grid, color="#8fb8d8", show_edges=show_edges,
                                          line_width=3, name="model")

        try:
            vp.add_supports(self.plotter, m, size)
            if self.act_loads.isChecked() and (u is None or not modal):
                vp.add_loads(self.plotter, m, m.case(), size)
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
        try:
            self.plotter.show_axes()
        except Exception:
            pass
        self.plotter.render()

    # ---- Datei -------------------------------------------------------
    def new_model(self):
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
                self.model = Model.load(p)
                self.__init_defaults()
                self.analysis = None
                self.results = None
                self.selection = np.array([], dtype=int)
                self.path = p
                self.refresh_all()
                self._refresh_title()
                self.plotter.reset_camera()
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
            self.model = build_example(which)
            self.__init_defaults()
            self.analysis = None
            self.results = None
            self.selection = np.array([], dtype=int)
            self.path = None
            self.refresh_all()
            self.plotter.reset_camera()
            self.plotter.view_isometric()
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
        """Neueste Version bei GitHub erfragen (Hintergrund); bei quiet nur den Knopf faerben."""
        from .. import update as upd
        self.btn_update.setEnabled(False)
        self.btn_update.setText("Update wird gesucht…")

        def done(info):
            self.btn_update.setEnabled(True)
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
            return upd.apply(info, prog, restart=True)

        def done(msg):
            self.progress_bar.setVisible(False)
            self.log.appendPlainText(msg)
            QtWidgets.QMessageBox.information(self, "Update", msg)
            self.close()
            QtWidgets.QApplication.quit()

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
def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
