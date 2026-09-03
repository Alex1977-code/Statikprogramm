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
                      VerformungsgrenzeDialog, parse_int_list)
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

        self.setStyleSheet(dsg.stil() + rib.stil() + msk.stil() + tab.stil())
        self._undo_init()
        self._ks_init()
        self._build_viewport()
        self._build_panels()
        self._build_bottom()
        self.kopf = dsg.Kopfzeile(self)
        self._build_ribbon()
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
        self.lbl_fang.setText("Fang: " + ("an" if getattr(self, "fang_an", False)
                                          else "aus")
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
                                   "Auf Knoten, Kantenmitte und Raster fangen")
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
        g.gross("Knotenlast", "↓", self.maske_knotenlast, "",
                "Knoten wählen, Kräfte und Momente eintragen")
        g.gross("Stablast", "⇊", lambda: self.maske_zeigen("Lager/Lasten"),
                hinweis="Streckenlast auf Stabelemente")
        g.klein("Flächenlast", lambda: self.maske_zeigen("Lager/Lasten"))
        g.klein("Temperaturlast", lambda: self.maske_zeigen("Lager/Lasten"))
        g.klein("Eigengewicht", lambda: self.maske_zeigen("Lager/Lasten"))

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

        r = rb.register("Ergebnisse")
        g = r.gruppe("Auswahl")
        g.gross("Ergebnisse", "∿", lambda: self.maske_zeigen("Ergebnisse"),
                hinweis="Ergebnis, Färbung, Verlauf und Überhöhung wählen")
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

        # -- Ansicht -----------------------------------------------------
        r = rb.register("Ansicht")
        g = r.gruppe("Blickrichtung")
        g.gross("Isometrisch", "◲", lambda: (self.plotter.view_isometric(),
                                             self.plotter.reset_camera()))
        g.klein("XY (Draufsicht)", self.plotter.view_xy)
        g.klein("XZ (Ansicht)", self.plotter.view_xz)
        g.klein("YZ (Seitenansicht)", self.plotter.view_yz)
        g.klein("Zoom alles", self.plotter.reset_camera)
        g = r.gruppe("Anzeigen")
        self.act_edges = g.schalter("Kanten", lambda z: self.redraw(), True)
        self.act_nodes = g.schalter("Knotennummern", lambda z: self.redraw())
        self.act_elems = g.schalter("Elementnummern", lambda z: self.redraw())
        self.act_loads = g.schalter("Lasten", lambda z: self.redraw(), True)
        self.act_members = g.schalter("Stäbe farbig", lambda z: self.redraw())

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
        b = QtWidgets.QToolButton()
        b.setDefaultAction(aktion)
        b.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        b.setText(f"{zeichen}\n{aktion.text()}")
        b.setObjectName("ribbongross")
        if rolle:
            b.setProperty("rolle", rolle)
        b.setMinimumWidth(56)
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
        dock.setWidget(self.tabs)
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

    def _build_baum(self):
        """Modellbaum links: was im Modell steckt."""
        dock = QtWidgets.QDockWidget("Modellbaum", self)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea)
        dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        self.baum = dsg.Modellbaum(dock)
        self.baum.angeklickt.connect(self._baum_geklickt)
        dock.setWidget(self.baum)
        dock.setMinimumWidth(230)
        dock.setMaximumWidth(340)
        self.baum_dock = dock
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)

    #: Zweig des Modellbaums -> Register der Eingaben
    BAUM_ZIEL = {
        "modell": "Modell", "elemente": "Netz", "querschnitte": "Modell",
        "werkstoffe": "Modell", "lager": "Lager/Lasten", "lastfaelle": "Lastfälle",
        "kombinationen": "Lastfälle", "kontakt": "Kontakt", "staebe": "Nachweise",
        "stab": "Nachweise", "stellungen": "Stellungen", "stellung": "Stellungen",
    }

    #: Zweige des Modellbaums, die eine Tabelle unten zeigen statt eine Maske
    BAUM_TABELLE = {"querschnitte": "Querschnitte", "werkstoffe": "Werkstoffe",
                    "anschluesse": "Anschlüsse", "anschluss": "Anschlüsse",
                    "verformungen": "Verformungen", "verformung": "Verformungen"}

    def _baum_geklickt(self, art: str, name: str):
        if art == "stellung_neu":
            return self.neue_stellung()
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
        tab = self.BAUM_TABELLE.get(art)
        if tab:
            return self.tabelle_zeigen(tab)
        ziel = self.BAUM_ZIEL.get(art)
        if ziel:
            self.maske_zeigen(ziel)

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
            self.baum.fuellen(self.model, self._stellungen_liste())


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
        """Eine Eingabetabelle mit ihren Knoepfen fuer den unteren Bereich."""
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(tbl, 1)
        if knoepfe:
            lay.addWidget(row(*knoepfe))
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

    #: Ergebnistabellen in der Reihenfolge des unteren Bereichs
    ERGEBNISTABELLEN = ("tbl_beam", "tbl_react", "tbl_env", "tbl_design",
                        "tbl_fat", "tbl_contact")

    def _build_bottom(self):
        dock = QtWidgets.QDockWidget("Protokoll und Tabellen", self)
        dock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        self.unten_dock = dock
        tabs = QtWidgets.QTabWidget()
        self.tab_unten = tabs
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family: monospace; font-size: 11px;")
        tabs.addTab(self.log, "Protokoll")
        self._build_eingabetabellen(tabs)
        self._build_ergebnistabellen(tabs)
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
        self.maskenrand.zeigen(m)

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

    def _fangen(self, punkt):
        """Einen Punkt auf die nächste markante Stelle ziehen."""
        if not getattr(self, "fang_an", False):
            return ks.Fangtreffer(np.asarray(punkt, float))
        kanten = [(int(e.nodes[0]), int(e.nodes[-1])) for e in self.model.elements
                  if e.typ in ("beam", "truss")][:4000]
        weite = 0.03 * max(self.model.characteristic_size(), 1e-6)
        return ks.fangen(punkt, self.model.nodes if self.model.nn else None,
                         kanten, self.arbeitsebene, weite, self.fang_arten)

    # ---- Linien ------------------------------------------------------
    def maske_linie(self):
        """Linie anlegen: Art wählen, Knoten anklicken oder Werte eintragen."""
        arten = [("polyline", "Polylinie (2+ Knoten)"), ("arc", "Bogen (3 Knoten)"),
                 ("circle", "Kreis (Mitte + Radius)"), ("spline", "Spline (3+ Knoten)"),
                 ("parabola", "Parabel (Anfang, Ende, Stich)")]
        m = msk.Maske("Linie", [
            msk.Feld("art", "Art", "wahl", "Bogen (3 Knoten)", [t for _k, t in arten]),
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
        self.maskenrand.zeigen(m)

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
        self.maskenrand.zeigen(m)

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
        self.maskenrand.zeigen(m)

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
        self.maskenrand.zeigen(m)

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
        self.maskenrand.zeigen(m)

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
        self.maskenrand.zeigen(m)

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
        """Auswahl aufheben."""
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
        if an is not None and an.joints is not None:
            lines.append(an.joints.summary())
        if an is not None and an.gzg is not None:
            lines.append(an.gzg.summary())
        self.refresh_joints()
        self.refresh_verformungen()
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
