"""Dialoge der Statik3D-Oberflaeche."""
from __future__ import annotations

import os

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ..model import (Model, Material, Section, LoadCase, Combination, Member,
                     ACTION_CATEGORIES, STEEL_GRADES, DesignSettings)
from .. import profiles
from ..ec3.fatigue import DETAIL_CATEGORIES, DETAIL_EXAMPLES


class NumEdit(QtWidgets.QLineEdit):
    def __init__(self, value=0.0, width=80):
        super().__init__(f"{value:g}")
        self.setValidator(QtGui.QDoubleValidator(-1e30, 1e30, 12))
        self.setFixedWidth(width)

    def value(self) -> float:
        t = self.text().replace(",", ".").strip()
        try:
            return float(t)
        except ValueError:
            return 0.0

    def set(self, v):
        self.setText(f"{v:g}")


def row(*widgets) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        lay.addWidget(QtWidgets.QLabel(x) if isinstance(x, str) else x)
    lay.addStretch()
    return w


def buttons(dialog: QtWidgets.QDialog) -> QtWidgets.QDialogButtonBox:
    bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    bb.accepted.connect(dialog.accept)
    bb.rejected.connect(dialog.reject)
    return bb


# ==========================================================================
class MaterialDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, mat: Material = None):
        super().__init__(parent)
        self.setWindowTitle("Material")
        m = mat or Material.steel("S355")
        self.grade = QtWidgets.QComboBox()
        self.grade.addItems(list(STEEL_GRADES) + ["benutzerdefiniert"])
        self.grade.setCurrentText(m.grade if m.grade in STEEL_GRADES else "benutzerdefiniert")
        self.grade.currentTextChanged.connect(self._grade_changed)
        self.name = QtWidgets.QLineEdit(m.name)
        self.E = NumEdit(m.E / 1e9, 100)
        self.nu = NumEdit(m.nu, 100)
        self.rho = NumEdit(m.rho, 100)
        self.alpha = NumEdit(m.alpha * 1e6, 100)
        self.fy = NumEdit((m.fy or 0) / 1e6, 100)
        self.fu = NumEdit((m.fu or 0) / 1e6, 100)
        f = QtWidgets.QFormLayout(self)
        f.addRow("Stahlsorte", self.grade)
        f.addRow("Name", self.name)
        f.addRow("E-Modul [GPa]", self.E)
        f.addRow("Querdehnzahl [-]", self.nu)
        f.addRow("Dichte [kg/m³]", self.rho)
        f.addRow("Wärmedehnzahl [1e-6/K]", self.alpha)
        f.addRow("Streckgrenze fy [MPa]", self.fy)
        f.addRow("Zugfestigkeit fu [MPa]", self.fu)
        f.addRow(buttons(self))

    def _grade_changed(self, g):
        if g in STEEL_GRADES:
            m = Material.steel(g)
            self.name.setText(g)
            self.E.set(m.E / 1e9); self.nu.set(m.nu); self.rho.set(m.rho)
            self.fy.set(m.fy / 1e6); self.fu.set(m.fu / 1e6)

    def result_material(self) -> Material:
        fy = self.fy.value() * 1e6
        fu = self.fu.value() * 1e6
        g = self.grade.currentText()
        return Material(self.name.text() or "Mat", self.E.value() * 1e9, self.nu.value(),
                        self.rho.value(), self.alpha.value() * 1e-6,
                        fy if fy > 0 else None, fu if fu > 0 else None,
                        g if g in STEEL_GRADES else "")


class SectionDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Querschnitt")
        self.resize(460, 320)
        self.name = QtWidgets.QLineEdit("")
        self.tabs = QtWidgets.QTabWidget()
        # --- Profildatenbank ---
        w = QtWidgets.QWidget()
        f = QtWidgets.QFormLayout(w)
        self.country = QtWidgets.QComboBox()
        for code, bez, norm, _fams in profiles.countries():
            self.country.addItem(f"{bez} - {norm}", code)
        self.country.currentIndexChanged.connect(self._fill_families)
        self.family = QtWidgets.QComboBox()
        self.family.currentTextChanged.connect(self._fill_profiles)
        self.profile = QtWidgets.QComboBox()
        self.profile.currentTextChanged.connect(self._show_props)
        self.props = QtWidgets.QLabel("")
        self.props.setStyleSheet("font-family: monospace")
        f.addRow("Land / Norm", self.country)
        f.addRow("Reihe", self.family)
        f.addRow("Profil", self.profile)
        f.addRow(self.props)
        self._fill_families()
        self.tabs.addTab(w, "Datenbank (nach Land)")
        # --- parametrisch ---
        w2 = QtWidgets.QWidget()
        f2 = QtWidgets.QFormLayout(w2)
        self.typ = QtWidgets.QComboBox()
        self.typ.addItems(["Rechteck b×h", "Kreis d", "Rohr d/t (CHS)",
                           "Doppel-T h/b/tw/tf/r (geschweißt)", "Hohlprofil h/b/t (RHS)",
                           "frei (A, Iy, Iz, It)"])
        self.p = [NumEdit(v, 70) for v in (0.2, 0.1, 0.008, 0.012, 0.0)]
        self.free = [NumEdit(v, 90) for v in (1e-2, 1e-5, 1e-5, 1e-5)]
        f2.addRow("Typ", self.typ)
        f2.addRow("Parameter [m]", row(*self.p))
        f2.addRow("A / Iy / Iz / It", row(*self.free))
        self.tabs.addTab(w2, "Parametrisch")
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(row("Name (leer = Profilname)", self.name))
        lay.addWidget(self.tabs)
        lay.addWidget(buttons(self))
        self._fill_profiles(self.family.currentText())

    def _fill_families(self):
        code = self.country.currentData() or "EU"
        self.family.blockSignals(True)
        self.family.clear()
        for fam in profiles.families(code):
            self.family.addItem(f"{fam} - {profiles.FAMILY_INFO.get(fam, (fam,))[0]}", fam)
        self.family.blockSignals(False)
        self._fill_profiles()

    def _fill_profiles(self, _text=None):
        fam = self.family.currentData() or "IPE"
        self.profile.blockSignals(True)
        self.profile.clear()
        try:
            self.profile.addItems(profiles.list_profiles(fam))
        except KeyError:
            pass
        self.profile.blockSignals(False)
        self._show_props(self.profile.currentText())

    def _show_props(self, name):
        if not name:
            return
        try:
            s = profiles.make_section(name)
            self.props.setText(
                f"A = {s.A*1e4:.1f} cm²   Iy = {s.Iy*1e8:.0f} cm⁴   Iz = {s.Iz*1e8:.0f} cm⁴\n"
                f"It = {s.It*1e8:.1f} cm⁴   Wpl,y = {s.Wpl_y*1e6:.0f} cm³   Wpl,z = {s.Wpl_z*1e6:.0f} cm³\n"
                f"{s.describe()}")
        except Exception as ex:
            self.props.setText(str(ex))

    def result_section(self) -> Section:
        n = self.name.text().strip()
        if self.tabs.currentIndex() == 0:
            return profiles.make_section(self.profile.currentText(), n or None)
        n = n or "Q"
        v = [x.value() for x in self.p]
        i = self.typ.currentIndex()
        if i == 0:
            return Section.rectangle(n, v[0], v[1])
        if i == 1:
            return Section.circle(n, v[0])
        if i == 2:
            return Section.pipe(n, v[0], v[1])
        if i == 3:
            return Section.i_profile(n, v[0], v[1], v[2], v[3], v[4], fabrication="welded")
        if i == 4:
            return Section.rhs(n, v[0], v[1], v[2])
        a = [x.value() for x in self.free]
        return Section(n, A=a[0], Iy=a[1], Iz=a[2], It=a[3])


# ==========================================================================
class LoadCaseDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, lc: LoadCase = None, existing=()):
        super().__init__(parent)
        self.setWindowTitle("Lastfall")
        self.name = QtWidgets.QLineEdit(lc.name if lc else f"LF{len(existing)+1}")
        self.cat = QtWidgets.QComboBox()
        for k, (desc, psi) in ACTION_CATEGORIES.items():
            self.cat.addItem(f"{k}: {desc}  (ψ {psi[0]}/{psi[1]}/{psi[2]})", k)
        if lc:
            self.cat.setCurrentIndex(list(ACTION_CATEGORIES).index(lc.category))
        self.desc = QtWidgets.QLineEdit(lc.description if lc else "")
        self.group = QtWidgets.QLineEdit(lc.exclusive_group if lc else "")
        self.group.setPlaceholderText("z.B. 'Wind' - Lastfälle einer Gruppe wirken nie gemeinsam")
        f = QtWidgets.QFormLayout(self)
        f.addRow("Name", self.name)
        f.addRow("Einwirkung", self.cat)
        f.addRow("Beschreibung", self.desc)
        f.addRow("Ausschlussgruppe", self.group)
        f.addRow(buttons(self))

    def values(self):
        return (self.name.text().strip() or "LF", self.cat.currentData(),
                self.desc.text(), self.group.text().strip())


class CombinationDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, model: Model = None, combo: Combination = None):
        super().__init__(parent)
        self.setWindowTitle("Kombination")
        self.name = QtWidgets.QLineEdit(combo.name if combo else f"K{len(model.combinations)+1}")
        self.typ = QtWidgets.QComboBox()
        self.typ.addItems(["ULS", "EQU", "ACC", "SLS_CH", "SLS_FR", "SLS_QP", "USER"])
        if combo:
            self.typ.setCurrentText(combo.typ)
        self.desc = QtWidgets.QLineEdit(combo.description if combo else "")
        self.factors = {}
        f = QtWidgets.QFormLayout(self)
        f.addRow("Name", self.name)
        f.addRow("Typ", self.typ)
        f.addRow("Beschreibung", self.desc)
        for k in model.load_cases:
            e = NumEdit(combo.factors.get(k, 0.0) if combo else 0.0, 80)
            self.factors[k] = e
            f.addRow(f"Faktor {k}", e)
        f.addRow(buttons(self))

    def result(self) -> Combination:
        return Combination(self.name.text().strip() or "K",
                           {k: e.value() for k, e in self.factors.items() if e.value()},
                           self.typ.currentText(), self.desc.text())


class AutoCombinationDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, ds: DesignSettings = None):
        super().__init__(parent)
        self.setWindowTitle("Kombinationen automatisch erzeugen (DIN EN 1990)")
        self.rule = QtWidgets.QComboBox()
        self.rule.addItems(["6.10 (Deutschland, NA)", "6.10a / 6.10b"])
        if ds and ds.combination_rule == "6.10ab":
            self.rule.setCurrentIndex(1)
        self.uls = QtWidgets.QCheckBox("GZT (STR/GEO)"); self.uls.setChecked(True)
        self.sls = QtWidgets.QCheckBox("GZG (charakteristisch, häufig, quasi-ständig)"); self.sls.setChecked(True)
        self.acc = QtWidgets.QCheckBox("außergewöhnlich"); self.acc.setChecked(True)
        self.gfav = QtWidgets.QCheckBox("ständige Lasten auch günstig (γG = 1,0)"); self.gfav.setChecked(True)
        self.replace = QtWidgets.QCheckBox("vorhandene automatische Kombinationen ersetzen"); self.replace.setChecked(True)
        self.gG = NumEdit(ds.gamma_G_sup if ds else 1.35, 70)
        self.gQ = NumEdit(ds.gamma_Q if ds else 1.5, 70)
        f = QtWidgets.QFormLayout(self)
        f.addRow("Regel", self.rule)
        f.addRow("γG,sup / γQ", row(self.gG, self.gQ))
        for c in (self.uls, self.sls, self.acc, self.gfav, self.replace):
            f.addRow(c)
        f.addRow(buttons(self))


class FatigueLoadDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, model: Model = None):
        super().__init__(parent)
        self.setWindowTitle("Ermüdungslast (Lastwechsel)")
        self.name = QtWidgets.QLineEdit(f"E{len(model.fatigue_loads)+1}")
        cases = list(model.load_cases) + list(model.combinations)
        self.cmax = QtWidgets.QComboBox(); self.cmax.addItems(cases)
        self.cmin = QtWidgets.QComboBox(); self.cmin.addItems(["(Nullzustand)"] + cases)
        self.cycles = NumEdit(2e6, 100)
        self.factor = NumEdit(1.0, 80)
        f = QtWidgets.QFormLayout(self)
        f.addRow("Name", self.name)
        f.addRow("Oberer Zustand (Lastfall/Kombination)", self.cmax)
        f.addRow("Unterer Zustand", self.cmin)
        f.addRow("Lastspiele n", self.cycles)
        f.addRow("Faktor (z.B. dynamischer Beiwert)", self.factor)
        f.addRow(buttons(self))

    def values(self):
        cmin = self.cmin.currentText()
        return (self.name.text().strip(), self.cmax.currentText(),
                None if cmin.startswith("(") else cmin, self.cycles.value(), self.factor.value())


# ==========================================================================
class MemberDialog(QtWidgets.QDialog):
    """Nachweisparameter eines Stabes."""

    def __init__(self, parent=None, member: Member = None, L: float = 1.0):
        super().__init__(parent)
        self.setWindowTitle(f"Stab {member.name}: Nachweisparameter")
        m = member
        self.design = QtWidgets.QCheckBox("nachweisen"); self.design.setChecked(m.design)
        self.beta_y = NumEdit(m.beta_y, 70); self.beta_z = NumEdit(m.beta_z, 70)
        self.Lcr_y = NumEdit(m.Lcr_y or 0.0, 70); self.Lcr_z = NumEdit(m.Lcr_z or 0.0, 70)
        self.L_LT = NumEdit(m.L_LT or 0.0, 70)
        self.kz = NumEdit(m.k_z, 60); self.kw = NumEdit(m.k_w, 60)
        self.C1 = NumEdit(m.C1 or 0.0, 60)
        self.loadpos = QtWidgets.QComboBox(); self.loadpos.addItems(["shear_centre", "top", "bottom"])
        self.loadpos.setCurrentText(m.load_position)
        self.lt = QtWidgets.QCheckBox("Biegedrillknicken nachweisen"); self.lt.setChecked(m.lt_check)
        self.sway_y = QtWidgets.QCheckBox("verschieblich um y"); self.sway_y.setChecked(m.sway_y)
        self.sway_z = QtWidgets.QCheckBox("verschieblich um z"); self.sway_z.setChecked(m.sway_z)
        self.cat = QtWidgets.QComboBox()
        self.cat.addItem("kein Ermüdungsnachweis", None)
        for c in DETAIL_CATEGORIES:
            self.cat.addItem(f"{c}: {DETAIL_EXAMPLES.get(c, '')}", c)
        if m.detail_category:
            idx = self.cat.findData(int(round(m.detail_category / 1e6)))
            self.cat.setCurrentIndex(max(idx, 0))
        self.cat_s = QtWidgets.QComboBox()
        self.cat_s.addItems(["100", "80"])
        if m.detail_category_shear:
            self.cat_s.setCurrentText(f"{m.detail_category_shear/1e6:.0f}")
        self.consequence = QtWidgets.QComboBox(); self.consequence.addItems(["low", "high"])
        self.consequence.setCurrentText(m.consequence)
        self.assessment = QtWidgets.QComboBox(); self.assessment.addItems(["damage_tolerant", "safe_life"])
        self.assessment.setCurrentText(m.assessment)
        f = QtWidgets.QFormLayout(self)
        f.addRow(QtWidgets.QLabel(f"<b>Stablänge L = {L:.3f} m, Elemente: {m.elements}</b>"))
        f.addRow(self.design)
        f.addRow("Knicklängenbeiwert βy / βz", row(self.beta_y, self.beta_z))
        f.addRow("Knicklänge Lcr,y / Lcr,z [m] (0 = β·L)", row(self.Lcr_y, self.Lcr_z))
        f.addRow("Abstand seitl. Halterungen L_LT [m] (0 = L)", self.L_LT)
        f.addRow("kz / kw / C1 (0 = automatisch)", row(self.kz, self.kw, self.C1))
        f.addRow("Lastangriff (Mcr)", self.loadpos)
        f.addRow(self.lt)
        f.addRow(row(self.sway_y, self.sway_z))
        f.addRow("Kerbfall Δσc [MPa]", self.cat)
        f.addRow("Kerbfall Schub Δτc [MPa]", self.cat_s)
        f.addRow("Schadensfolge / Konzept", row(self.consequence, self.assessment))
        f.addRow(buttons(self))

    def apply(self, m: Member):
        m.design = self.design.isChecked()
        m.beta_y = self.beta_y.value() or 1.0
        m.beta_z = self.beta_z.value() or 1.0
        m.Lcr_y = self.Lcr_y.value() or None
        m.Lcr_z = self.Lcr_z.value() or None
        m.L_LT = self.L_LT.value() or None
        m.k_z = self.kz.value() or 1.0
        m.k_w = self.kw.value() or 1.0
        m.C1 = self.C1.value() or None
        m.load_position = self.loadpos.currentText()
        m.lt_check = self.lt.isChecked()
        m.sway_y = self.sway_y.isChecked()
        m.sway_z = self.sway_z.isChecked()
        c = self.cat.currentData()
        m.detail_category = float(c) * 1e6 if c else None
        m.detail_category_shear = float(self.cat_s.currentText()) * 1e6
        m.consequence = self.consequence.currentText()
        m.assessment = self.assessment.currentText()


class DesignSettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, ds: DesignSettings = None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen Nachweise (DIN EN 1993-1-1/NA)")
        self.gM0 = NumEdit(ds.gamma_M0, 70); self.gM1 = NumEdit(ds.gamma_M1, 70)
        self.gM2 = NumEdit(ds.gamma_M2, 70); self.gFf = NumEdit(ds.gamma_Ff, 70)
        self.lt = QtWidgets.QComboBox(); self.lt.addItems(["general", "rolled"])
        self.lt.setCurrentText(ds.lt_method)
        self.stations = QtWidgets.QSpinBox(); self.stations.setRange(2, 51); self.stations.setValue(ds.stations)
        f = QtWidgets.QFormLayout(self)
        f.addRow("γM0 / γM1 / γM2", row(self.gM0, self.gM1, self.gM2))
        f.addRow("γFf (Ermüdung)", self.gFf)
        f.addRow("Biegedrillknicken: 6.3.2.2 (general) / 6.3.2.3 (rolled)", self.lt)
        f.addRow("Nachweisstellen je Element", self.stations)
        f.addRow(QtWidgets.QLabel("Interaktion: Anhang B (Methode 2)"))
        # --- Theorie II. Ordnung (EN 1993-1-1, 5.2 und 5.3)
        self.th2 = QtWidgets.QComboBox()
        self.th2.addItem("aus - nur Theorie I. Ordnung", "aus")
        self.th2.addItem("automatisch nach 5.2.1(3) (α_cr < Grenze)", "auto")
        self.th2.addItem("ein - immer am verformten System", "ein")
        i = self.th2.findData(getattr(ds, "theorie2", "aus"))
        self.th2.setCurrentIndex(max(i, 0))
        self.imp = QtWidgets.QCheckBox("Ersatzimperfektionen nach 5.3.2 ansetzen")
        self.imp.setChecked(bool(getattr(ds, "imperfektionen", True)))
        self.th2_pl = QtWidgets.QCheckBox(
            "plastische Berechnung (Grenze α_cr = 15 statt 10)")
        self.th2_pl.setChecked(bool(getattr(ds, "th2_plastisch", False)))
        self.th2_alle = QtWidgets.QCheckBox(
            "Vorkrümmung für alle gedrückten Stäbe (5.3.2(6) übergehen)")
        self.th2_alle.setChecked(bool(getattr(ds, "th2_alle_vorkruemmungen", False)))
        f.addRow(QtWidgets.QLabel("<b>Theorie II. Ordnung (5.2 und 5.3)</b>"))
        f.addRow("Berechnung", self.th2)
        f.addRow(self.imp)
        f.addRow(self.th2_pl)
        f.addRow(self.th2_alle)
        hint = QtWidgets.QLabel(
            "Nach Theorie II. Ordnung gilt keine Superposition: jede Kombination\n"
            "wird einzeln am verformten System gerechnet. Das dauert länger.")
        hint.setStyleSheet("color: #555;")
        f.addRow(hint)
        f.addRow(buttons(self))

    def apply(self, ds: DesignSettings):
        ds.gamma_M0 = self.gM0.value() or 1.0
        ds.gamma_M1 = self.gM1.value() or 1.1
        ds.gamma_M2 = self.gM2.value() or 1.25
        ds.gamma_Ff = self.gFf.value() or 1.0
        ds.lt_method = self.lt.currentText()
        ds.stations = self.stations.value()
        ds.theorie2 = self.th2.currentData()
        ds.imperfektionen = self.imp.isChecked()
        ds.th2_plastisch = self.th2_pl.isChecked()
        ds.th2_alle_vorkruemmungen = self.th2_alle.isChecked()


# ==========================================================================
class ContactPairDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, model: Model = None, n_selected: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Kontaktpaar Knoten - Fläche")
        self.name = QtWidgets.QLineEdit(f"Kontakt{len(model.contact_pairs)+1}")
        self.master = QtWidgets.QComboBox()
        groups = sorted({e.group for e in model.elements})
        self.master.addItem("alle Schalenelemente", ("shells", None))
        self.master.addItem("alle Volumenelemente (Oberfläche)", ("solids", None))
        for g in groups:
            self.master.addItem(f"Elementgruppe '{g}'", ("group", g))
        self.master.addItem("Element-Nr. (Liste)", ("list", None))
        self.elist = QtWidgets.QLineEdit()
        self.elist.setPlaceholderText("z.B. 0-15, 20, 22")
        self.k = NumEdit(0.0, 90)
        self.mu = NumEdit(0.0, 70)
        self.gap = NumEdit(0.0, 70)
        self.radius = NumEdit(0.0, 70)
        self.flip = QtWidgets.QCheckBox("Normale umkehren")
        f = QtWidgets.QFormLayout(self)
        f.addRow(QtWidgets.QLabel(f"Slave-Knoten: aktuelle Auswahl ({n_selected} Knoten)"))
        f.addRow("Name", self.name)
        f.addRow("Master-Fläche", self.master)
        f.addRow("Element-Liste", self.elist)
        f.addRow("Kontaktsteifigkeit [N/m] (0 = automatisch)", self.k)
        f.addRow("Reibungsbeiwert μ", self.mu)
        f.addRow("Spalt / Versatz [m]", self.gap)
        f.addRow("Suchradius [m] (0 = automatisch)", self.radius)
        f.addRow(self.flip)
        f.addRow(buttons(self))

    def master_elements(self, model: Model) -> list[int]:
        kind, g = self.master.currentData()
        if kind == "shells":
            return [i for i, e in enumerate(model.elements) if e.typ.startswith("shell")]
        if kind == "solids":
            return [i for i, e in enumerate(model.elements) if e.typ in ("tet4", "tet10", "hex8")]
        if kind == "group":
            return [i for i, e in enumerate(model.elements) if e.group == g]
        return parse_int_list(self.elist.text(), len(model.elements))


def parse_int_list(text: str, n_max: int = None) -> list[int]:
    out = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    if n_max is not None:
        out = [i for i in out if 0 <= i < n_max]
    return sorted(set(out))


# ==========================================================================
class SupportNonlinearDialog(QtWidgets.QDialog):
    """Nichtlinearitaet eines Lagers je Freiheitsgrad: Ausfall bei Zug/Druck,
    Schlupf, Reibbeiwert, Grenzkraft."""

    DOFS = ["ux", "uy", "uz", "phix", "phiy", "phiz"]

    def __init__(self, parent=None, support=None, kind: str = "Knotenlager"):
        super().__init__(parent)
        self.setWindowTitle(f"{kind}: Wirkung je Freiheitsgrad")
        self.resize(760, 330)
        self.support = support
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel(
            "Das Lager wirkt entlang der positiven Achse. Bewegt sich der Knoten in das Lager "
            "hinein, entsteht <b>Druck</b>; zieht er daran, <b>Zug</b>.<br>"
            "Steifigkeit: Knotenlager [kN/m] bzw. [kNm/rad], Linienlager je m, Flächenlager je m²."))
        self.tbl = QtWidgets.QTableWidget(6, 6)
        self.tbl.setHorizontalHeaderLabels(
            ["Wirkung", "Steifigkeit", "Ausfall", "Schlupf [mm]", "Reibung μ", "μ bezogen auf"])
        self.tbl.setVerticalHeaderLabels(self.DOFS)
        self.rows = []
        for d in range(6):
            typ = QtWidgets.QComboBox(); typ.addItems(["frei", "starr", "Feder"])
            k = NumEdit(0.0, 90)
            fail = QtWidgets.QComboBox()
            fail.addItems(["-", "bei Zug (nur Druck)", "bei Druck (nur Zug)"])
            slip = NumEdit(0.0, 80)
            mu = NumEdit(0.0, 70)
            ref = QtWidgets.QComboBox(); ref.addItems(["-"] + self.DOFS[:3])
            for c, wdg in enumerate((typ, k, fail, slip, mu, ref)):
                self.tbl.setCellWidget(d, c, wdg)
            self.rows.append((typ, k, fail, slip, mu, ref))
        lay.addWidget(self.tbl)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                        | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        if support is not None:
            self.load(support)

    def load(self, support):
        for d, (typ, k, fail, slip, mu, ref) in enumerate(self.rows):
            b = support.dof_behaviour(d)
            typ.setCurrentIndex({"free": 0, "rigid": 1, "spring": 2}[b.typ])
            k.setText(f"{b.stiffness / 1e3:g}")
            fail.setCurrentIndex({"": 0, "zug": 1, "druck": 2}[b.failure])
            slip.setText(f"{b.slip * 1000:g}")
            mu.setText(f"{b.mu:g}")
            ref.setCurrentIndex(0 if b.mu_ref is None else int(b.mu_ref) + 1)

    def behaviours(self) -> dict:
        """{FHG: DofBehaviour} aus der Tabelle."""
        from ..model import DofBehaviour
        out = {}
        for d, (typ, k, fail, slip, mu, ref) in enumerate(self.rows):
            b = DofBehaviour(["free", "rigid", "spring"][typ.currentIndex()],
                             k.value() * 1e3,
                             ["", "zug", "druck"][fail.currentIndex()],
                             slip.value() / 1000.0, mu.value(),
                             None if ref.currentIndex() == 0 else ref.currentIndex() - 1)
            if b.acts or b.failure or b.slip or b.mu:
                out[d] = b
        return out

    def apply(self, support):
        support.behaviour = self.behaviours()
        support.dofs = sorted({d for d, b in support.behaviour.items() if b.acts})
        return support


class ImportDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, path: str = "", model: Model = None):
        super().__init__(parent)
        self.setWindowTitle("Import: " + os.path.basename(path))
        ext = os.path.splitext(path)[1].lower()
        self.unit = QtWidgets.QComboBox()
        self.unit.addItems(["mm (×0,001)", "cm (×0,01)", "m (×1)"])
        self.unit.setCurrentIndex(0 if ext in (".dxf",) else 2)
        self.append = QtWidgets.QCheckBox("an vorhandenes Modell anhängen")
        self.section = QtWidgets.QComboBox()
        self.section.addItems(list(model.sections) + profiles.list_profiles("IPE")[:6]
                              + profiles.list_profiles("HEA")[:6])
        self.material = QtWidgets.QComboBox()
        self.material.addItems(list(model.materials) or ["S235"])
        self.shell = QtWidgets.QComboBox()
        self.shell.addItems(list(model.shells))
        self.cad_size = NumEdit(0.05, 80)
        self.cad_order = QtWidgets.QComboBox(); self.cad_order.addItems(["Tet10 (quadratisch)", "Tet4 (linear)"])
        self.cad_dim = QtWidgets.QComboBox(); self.cad_dim.addItems(["Volumen (3D)", "Schale (2D)"])
        self.subdiv = QtWidgets.QSpinBox(); self.subdiv.setRange(1, 50); self.subdiv.setValue(1)
        self.members = QtWidgets.QCheckBox("Stäbe automatisch erkennen (für EC3)"); self.members.setChecked(True)
        f = QtWidgets.QFormLayout(self)
        f.addRow("Längeneinheit der Datei", self.unit)
        f.addRow("Standard-Querschnitt (Linien → Stäbe)", self.section)
        f.addRow("Standard-Material", self.material)
        f.addRow("Standard-Schalendicke", self.shell)
        f.addRow("Stabteilung je Linie", self.subdiv)
        if ext in (".step", ".stp", ".iges", ".igs", ".brep", ".stl"):
            f.addRow("Netzweite [m] (gmsh)", row(self.cad_size, self.cad_order))
            f.addRow("Vernetzung", self.cad_dim)
        f.addRow(self.append)
        f.addRow(self.members)
        f.addRow(buttons(self))
        self.ext = ext

    def options(self) -> dict:
        scale = [1e-3, 1e-2, 1.0][self.unit.currentIndex()]
        opt = {"unit_scale": scale, "section": self.section.currentText(),
               "mat": self.material.currentText(), "material": self.material.currentText(),
               "shell_prop": self.shell.currentText(), "subdivide": self.subdiv.value(),
               "size": self.cad_size.value(),
               "order": 2 if self.cad_order.currentIndex() == 0 else 1,
               "dim": 3 if self.cad_dim.currentIndex() == 0 else 2}
        return opt


class ReportDialog(QtWidgets.QDialog):
    OPTIONS = [("model_tables", "Knoten-/Elementtabellen"), ("materials", "Materialien"),
               ("sections", "Querschnitte"), ("supports", "Lager"), ("load_cases", "Lastfälle"),
               ("combinations", "Kombinationen"), ("figures", "Systemgrafiken"),
               ("results_cases", "Ergebnisse je Lastfall"),
               ("results_combinations", "Ergebnisse je Kombination"),
               ("envelopes", "Umhüllende"), ("member_diagrams", "Schnittgrößenverläufe"),
               ("design", "Nachweise EC3"), ("fatigue", "Ermüdung"), ("contact", "Kontakt"),
               ("modal", "Eigenfrequenzen"), ("buckling", "Knicken")]

    def __init__(self, parent=None, model: Model = None, path: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Statischer Bericht")
        self.meta = {}
        f = QtWidgets.QFormLayout(self)
        for k, label in (("projekt", "Projekt"), ("bauteil", "Bauteil"), ("position", "Position"),
                         ("auftraggeber", "Auftraggeber"), ("bearbeiter", "Bearbeiter")):
            e = QtWidgets.QLineEdit(model.meta.get(k, ""))
            self.meta[k] = e
            f.addRow(label, e)
        self.fmt = QtWidgets.QComboBox()
        self.fmt.addItems(["HTML (druckbar, Browser → PDF)", "PDF (reportlab)", "Markdown"])
        f.addRow("Format", self.fmt)
        self.path = QtWidgets.QLineEdit(path)
        b = QtWidgets.QPushButton("…")
        b.clicked.connect(self._browse)
        f.addRow("Datei", row(self.path, b))
        self.checks = {}
        grid = QtWidgets.QGridLayout()
        for i, (k, label) in enumerate(self.OPTIONS):
            c = QtWidgets.QCheckBox(label); c.setChecked(True)
            self.checks[k] = c
            grid.addWidget(c, i // 2, i % 2)
        f.addRow(grid)
        f.addRow(buttons(self))

    def _browse(self):
        ext = [".html", ".pdf", ".md"][self.fmt.currentIndex()]
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Bericht", self.path.text() or f"bericht{ext}",
                                                     f"Bericht (*{ext})")
        if p:
            self.path.setText(p)

    def apply_meta(self, model: Model):
        for k, e in self.meta.items():
            model.meta[k] = e.text()

    def options(self) -> dict:
        return {k: c.isChecked() for k, c in self.checks.items()}

    def format(self) -> str:
        return ["html", "pdf", "md"][self.fmt.currentIndex()]


# --------------------------------------------------------------------------
class JointDialog(QtWidgets.QDialog):
    """Anschluss anlegen: Typ waehlen, Stabende bestimmen, Vorschlag aendern.

    Der Vorschlag entsteht aus Profil und Schnittgroessen; alle Werte lassen
    sich danach von Hand aendern. Die Nachweise werden sofort mitgerechnet.
    """

    def __init__(self, parent, model, elem: int, end: int, forces: dict = None):
        super().__init__(parent)
        from ..joints.templates import TYPES, propose
        from ..joints.bolts import SIZES, GRADES, HOLE_TYPES, CATEGORIES
        self.setWindowTitle("Anschluss")
        self.model = model
        self.elem = int(elem)
        self.end = int(end)
        self.f0 = dict(forces or {})
        self.template = None
        self._propose = propose

        lay = QtWidgets.QVBoxLayout(self)
        kopf = QtWidgets.QFormLayout()
        self.cb_typ = QtWidgets.QComboBox()
        for key, (_cls, text) in TYPES.items():
            self.cb_typ.addItem(text, key)
        kopf.addRow("Anschlusstyp", self.cb_typ)
        e = model.elements[self.elem]
        kopf.addRow("Stab", QtWidgets.QLabel(
            f"Element {self.elem + 1}, {e.sec or '-'} aus {e.mat}, "
            f"Ende {'A' if self.end == 0 else 'E'}"))

        self.sp = {}
        for key, text, val, step in (("N", "N [kN]", self.f0.get("N", 0.0) / 1e3, 10.0),
                                     ("Vz", "V_z [kN]", self.f0.get("Vz", 0.0) / 1e3, 10.0),
                                     ("My", "M_y [kNm]", self.f0.get("My", 0.0) / 1e3, 10.0)):
            s = QtWidgets.QDoubleSpinBox()
            s.setRange(-1e6, 1e6)
            s.setDecimals(1)
            s.setSingleStep(step)
            s.setValue(val)
            kopf.addRow(text, s)
            self.sp[key] = s

        self.cb_size = QtWidgets.QComboBox()
        self.cb_size.addItem("automatisch", "")
        for k in SIZES:
            self.cb_size.addItem(k, k)
        kopf.addRow("Schraube", self.cb_size)
        self.cb_grade = QtWidgets.QComboBox()
        for k in GRADES:
            self.cb_grade.addItem(k, k)
        self.cb_grade.setCurrentText("10.9")
        kopf.addRow("Festigkeitsklasse", self.cb_grade)
        self.cb_hole = QtWidgets.QComboBox()
        for k, v in HOLE_TYPES.items():
            self.cb_hole.addItem(v[0], k)
        kopf.addRow("Lochart", self.cb_hole)
        self.cb_cat = QtWidgets.QComboBox()
        for k, v in CATEGORIES.items():
            self.cb_cat.addItem(f"{k} - {v}", k)
        kopf.addRow("Kategorie", self.cb_cat)
        self.sp_mu = QtWidgets.QDoubleSpinBox()
        self.sp_mu.setRange(0.0, 0.7)
        self.sp_mu.setSingleStep(0.05)
        self.sp_mu.setDecimals(2)
        self.sp_mu.setValue(0.50)
        kopf.addRow("Reibbeiwert mu", self.sp_mu)

        # -- Momenten-Rotations-Verhalten (EN 1993-1-8, Kap. 5 und 6.3) ----
        self.cb_stuetze = QtWidgets.QComboBox()
        self.cb_stuetze.addItem("keine Stütze angeschlossen", "")
        for k in model.sections:
            self.cb_stuetze.addItem(k, k)
        self.cb_stuetze.setToolTip(
            "Querschnitt der Stütze, an die angeschlossen wird. Ohne ihn entfallen\n"
            "die Komponenten k_1 bis k_4 (Stützensteg auf Schub, Druck und Zug,\n"
            "Stützenflansch auf Biegung); S_j,ini ist dann eine obere Schranke.")
        kopf.addRow("Stützenquerschnitt", self.cb_stuetze)
        self.cb_rahmen = QtWidgets.QComboBox()
        self.cb_rahmen.addItem("ausgesteift (k_b = 8)", "ausgesteift")
        self.cb_rahmen.addItem("nicht ausgesteift (k_b = 25)", "nicht ausgesteift")
        self.cb_rahmen.setToolTip("Grenze der Steifigkeitsklassifizierung nach 5.2.2.5")
        kopf.addRow("Rahmen", self.cb_rahmen)
        self.cb_modell = QtWidgets.QComboBox()
        for text, key in (("automatisch (nach Klassifizierung)", "automatisch"),
                          ("starr", "starr"), ("Drehfeder S_j", "feder"),
                          ("gelenkig", "gelenkig")):
            self.cb_modell.addItem(text, key)
        self.cb_modell.setToolTip(
            "Wie der Anschluss in der Berechnung sitzt.\n"
            "„automatisch“ folgt der Klassifizierung: starr bleibt starr,\n"
            "nachgiebig wird zur Drehfeder S_j = S_j,ini/η (5.1.2(4)),\n"
            "gelenkig wird zum Momentengelenk.")
        kopf.addRow("in der Berechnung", self.cb_modell)
        lay.addLayout(kopf)
        for w in (self.cb_stuetze, self.cb_rahmen):
            w.currentIndexChanged.connect(self.update_proposal)

        btn = QtWidgets.QPushButton("Vorschlag berechnen")
        btn.clicked.connect(self.update_proposal)
        lay.addWidget(btn)

        self.txt = QtWidgets.QPlainTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setMinimumSize(720, 380)
        f = self.txt.font()
        f.setFamily("Courier New")
        self.txt.setFont(f)
        lay.addWidget(self.txt)

        self.cb_fest = QtWidgets.QCheckBox(
            "Diese Schnittgrößen festhalten (sonst aus der Rechnung, über alle "
            "GZT-Kombinationen)")
        self.cb_fest.setToolTip(
            "Aus: der Anschluss wird bei jeder Berechnung mit den Stabend-\n"
            "schnittgrößen jeder GZT-Kombination geführt, die ungünstigste ist\n"
            "maßgebend. Ein: es gelten dauerhaft die oben eingetragenen Werte.")
        lay.addWidget(self.cb_fest)

        zeile = QtWidgets.QHBoxLayout()
        self.cb_fe = QtWidgets.QComboBox()
        self.cb_fe.addItem("Teilmodell: Schalen (2D-FE)", "2d")
        self.cb_fe.addItem("Teilmodell: Volumen (3D-FE)", "3d")
        self.cb_fe.addItem("kein Teilmodell", "")
        self.cb_fe.setCurrentIndex(self.cb_fe.count() - 1)
        zeile.addWidget(self.cb_fe)
        zeile.addStretch(1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                        | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        zeile.addWidget(bb)
        lay.addLayout(zeile)
        self.cb_typ.currentIndexChanged.connect(self.update_proposal)
        self.update_proposal()

    def _bolt(self):
        from ..joints.bolts import Bolt
        size = self.cb_size.currentData()
        if not size:
            return None
        return Bolt(size, self.cb_grade.currentData(),
                    hole=self.cb_hole.currentData(),
                    category=self.cb_cat.currentData(), mu=self.sp_mu.value())

    def stuetze(self) -> dict:
        name = self.cb_stuetze.currentData()
        return {"section": name} if name else {}

    def rahmen(self) -> str:
        return self.cb_rahmen.currentData()

    def modellierung(self) -> str:
        return self.cb_modell.currentData()

    def update_proposal(self):
        kind = self.cb_typ.currentData()
        kw = {k: self.sp[k].value() * 1e3 for k in self.sp}
        b = self._bolt()
        try:
            self.template = self._propose(kind, self.model, self.elem, self.end,
                                          bolt=b, **kw)
            j = (self.template.design(N=kw["N"])
                 if kind == "diagonale"
                 else self.template.design(**kw))
            text = self.template.describe() + "\n\n" + j.report()
            text += "\n\n" + self._gelenktext()
            self.txt.setPlainText(text)
        except Exception as ex:      # noqa: BLE001
            self.template = None
            self.txt.setPlainText(f"Vorschlag nicht moeglich: {ex}")

    def _gelenktext(self) -> str:
        """Steifigkeit, Klasse und Rotationsvermoegen des Vorschlags."""
        from ..joints.anschluss import stuetze_aufloesen
        from ..model import Joint
        import math
        j = Joint("x", "", int(self.elem), int(self.end),
                  stuetze=self.stuetze(), rahmen=self.rahmen())
        st = stuetze_aufloesen(self.model, j)
        if st.get("fehler"):
            st = {}
        try:
            g = self.template.momenten_rotation(stuetze=st, rahmen=self.rahmen())
        except Exception as ex:      # noqa: BLE001
            return f"Momenten-Rotations-Verhalten nicht bestimmbar: {ex}"
        S = "unendlich" if not math.isfinite(g.S_j_ini) else f"{g.S_j_ini / 1e6:.1f} MNm/rad"
        z = ["Momenten-Rotations-Verhalten (EN 1993-1-8, Kap. 5 und 6.3)",
             "=" * 78,
             f"S_j,ini = {S}"
             + (f", Rechenwert S_j = {g.S_j / 1e6:.1f} MNm/rad (eta = {g.eta:g})"
                if math.isfinite(g.S_j) and g.S_j > 0 else ""),
             f"Klasse:  {g.beschreibung()}",
             f"M_j,Rd = {g.M_j_Rd / 1e3:.1f} kNm ({g.tragklasse or '-'})",
             f"Rotationsvermoegen: {'ausreichend' if g.rotation_ok else 'nicht nachgewiesen'}"
             f" - {g.rotation_grund}"]
        for h in g.hinweise:
            z.append("Hinweis: " + h)
        return "\n".join(z)

    def result_template(self):
        return self.template

    def forces(self) -> dict:
        """Die eingestellten Schnittgroessen [N bzw. Nm]."""
        return {k: self.sp[k].value() * 1e3 for k in self.sp}

    def kraefte_fest(self) -> bool:
        """Sollen die eingetragenen Schnittgroessen dauerhaft gelten?"""
        return self.cb_fest.isChecked()

    def fe_kind(self) -> str:
        return self.cb_fe.currentData()


class BeulfeldDialog(QtWidgets.QDialog):
    """Ein Beulfeld festlegen: ebenes Blechfeld oder Zylinderschale, mit Steifen."""

    def __init__(self, parent, model, feld=None, elemente=None):
        super().__init__(parent)
        from ..ec3.schalenbeulen import QUALITAET, C_XB
        self.setWindowTitle("Beulfeld" + (f" {feld.name}" if feld else ""))
        self.model = model
        self._elemente = list(feld.elemente) if feld else list(elemente or [])
        f = feld
        lay = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.ed_name = QtWidgets.QLineEdit(f.name if f else "")
        form.addRow("Name", self.ed_name)
        form.addRow("Elemente", QtWidgets.QLabel(
            f"{len(self._elemente)} Flächenelemente aus der Auswahl"))
        self.cb_art = QtWidgets.QComboBox()
        self.cb_art.addItem("ebenes Blechfeld (EN 1993-1-5, Abschnitt 10)", "eben")
        self.cb_art.addItem("Zylinderschale (EN 1993-1-6, Abschnitt 8.5)", "zylinder")
        if f:
            self.cb_art.setCurrentIndex(max(0, self.cb_art.findData(f.art)))
        form.addRow("Art", self.cb_art)

        self.cb_rand = QtWidgets.QComboBox()
        self.cb_rand.addItem("beidseitig gestützt (z. B. Steg zwischen den Flanschen)",
                             "beidseitig")
        self.cb_rand.addItem("einseitig gestützt (ein Rand frei)", "einseitig")
        if f:
            self.cb_rand.setCurrentIndex(max(0, self.cb_rand.findData(f.rand)))
        form.addRow("Lagerung der Ränder", self.cb_rand)
        self.cb_endsteife = QtWidgets.QCheckBox("starre Endquersteife (Tab. 5.1)")
        self.cb_endsteife.setChecked(bool(f.starre_endsteife) if f else False)
        form.addRow("", self.cb_endsteife)

        self.ed_r = NumEdit((f.r * 1e3) if f else 0.0, 90)
        self.ed_l = NumEdit((f.l * 1e3) if f else 0.0, 90)
        self.lbl_r = QtWidgets.QLabel("Radius r [mm] (0 = aus der Geometrie)")
        self.lbl_l = QtWidgets.QLabel("Beullänge l [mm] (0 = aus der Geometrie)")
        form.addRow(self.lbl_r, self.ed_r)
        form.addRow(self.lbl_l, self.ed_l)
        self.cb_qual = QtWidgets.QComboBox()
        for k, (q, text) in QUALITAET.items():
            self.cb_qual.addItem(f"{text} (Q = {q:g})", k)
        if f:
            self.cb_qual.setCurrentIndex(max(0, self.cb_qual.findData(f.qualitaet)))
        else:
            self.cb_qual.setCurrentIndex(1)
        self.lbl_qual = QtWidgets.QLabel("Herstelltoleranzklasse")
        form.addRow(self.lbl_qual, self.cb_qual)
        self.cb_bc = QtWidgets.QComboBox()
        for k in C_XB:
            self.cb_bc.addItem(k, k)
        if f:
            self.cb_bc.setCurrentIndex(max(0, self.cb_bc.findData(f.randbedingung)))
        self.lbl_bc = QtWidgets.QLabel("Randbedingung der Schale")
        form.addRow(self.lbl_bc, self.cb_bc)

        self.ed_text = QtWidgets.QLineEdit(f.beschreibung if f else "")
        form.addRow("Beschreibung", self.ed_text)
        lay.addLayout(form)

        g = QtWidgets.QGroupBox("Steifen (leer = unversteiftes Feld)")
        gl = QtWidgets.QVBoxLayout(g)
        self.tbl = QtWidgets.QTableWidget(0, 7)
        self.tbl.setHorizontalHeaderLabels(
            ["Art", "Lage [mm]", "A_sl [cm²]", "I_sl [cm⁴]", "I_T [cm⁴]",
             "I_p [cm⁴]", "Name"])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setMinimumHeight(130)
        gl.addWidget(self.tbl)
        b1 = QtWidgets.QPushButton("Längssteife")
        b1.clicked.connect(lambda: self._zeile("laengs"))
        b2 = QtWidgets.QPushButton("Quersteife")
        b2.clicked.connect(lambda: self._zeile("quer"))
        b3 = QtWidgets.QPushButton("Zeile entfernen")
        b3.clicked.connect(self._weg)
        gl.addWidget(row(b1, b2, b3))
        gl.addWidget(QtWidgets.QLabel(
            "Lage: Längssteife ab gedrücktem Rand, Quersteife = Abstand zur nächsten.\n"
            "A_sl = Steife allein, I_sl = Steife mit mitwirkendem Blech.\n"
            "I_T und I_p nur für das Drillknicken nach 9.2.1 nötig."))
        lay.addWidget(g)
        for st in (f.steifen if f else []):
            self._zeile(getattr(st, "art", "laengs"), st)

        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                        | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.cb_art.currentIndexChanged.connect(self._umschalten)
        self._umschalten()

    def _umschalten(self):
        zyl = self.cb_art.currentData() == "zylinder"
        for w in (self.ed_r, self.ed_l, self.cb_qual, self.cb_bc, self.lbl_r,
                  self.lbl_l, self.lbl_qual, self.lbl_bc):
            w.setVisible(zyl)
        for w in (self.cb_rand, self.cb_endsteife):
            w.setEnabled(not zyl)

    def _zeile(self, art: str, st=None):
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        cb = QtWidgets.QComboBox()
        cb.addItems(["laengs", "quer"])
        cb.setCurrentText(art)
        self.tbl.setCellWidget(r, 0, cb)
        werte = [(st.lage * 1e3 if st else 0.0), (st.A_sl * 1e4 if st else 0.0),
                 (st.I_sl * 1e8 if st else 0.0), (st.I_T * 1e8 if st else 0.0),
                 (st.I_p * 1e8 if st else 0.0)]
        for k, v in enumerate(werte, start=1):
            self.tbl.setItem(r, k, QtWidgets.QTableWidgetItem(f"{v:g}"))
        self.tbl.setItem(r, 6, QtWidgets.QTableWidgetItem(
            (st.name if st else "") or f"S{r + 1}"))

    def _weg(self):
        r = self.tbl.currentRow()
        if r >= 0:
            self.tbl.removeRow(r)

    def steifen(self) -> list:
        from ..model import Beulsteife
        out = []
        for r in range(self.tbl.rowCount()):
            def z(k):
                it = self.tbl.item(r, k)
                try:
                    return float((it.text() if it else "0").replace(",", "."))
                except ValueError:
                    return 0.0
            cb = self.tbl.cellWidget(r, 0)
            nm = self.tbl.item(r, 6)
            out.append(Beulsteife(cb.currentText() if cb else "laengs",
                                  lage=z(1) * 1e-3, A_sl=z(2) * 1e-4,
                                  I_sl=z(3) * 1e-8, I_T=z(4) * 1e-8,
                                  I_p=z(5) * 1e-8,
                                  name=(nm.text() if nm else "")))
        return out

    def result(self) -> tuple:
        """(Name, Angaben) fuer model.add_beulfeld."""
        return self.ed_name.text().strip(), {
            "art": self.cb_art.currentData(),
            "rand": self.cb_rand.currentData(),
            "starre_endsteife": self.cb_endsteife.isChecked(),
            "steifen": self.steifen(),
            "r": self.ed_r.value() * 1e-3, "l": self.ed_l.value() * 1e-3,
            "qualitaet": self.cb_qual.currentData(),
            "randbedingung": self.cb_bc.currentData(),
            "beschreibung": self.ed_text.text().strip()}


class LasteinleitungDialog(QtWidgets.QDialog):
    """Eine Lasteinleitungsstelle festlegen (EN 1993-1-5, Abschnitt 6)."""

    def __init__(self, parent, model, stelle=None, knoten=None):
        super().__init__(parent)
        from ..ec3.beulen import EINLEITUNGSARTEN
        self.setWindowTitle("Lasteinleitung" + (f" {stelle.name}" if stelle else ""))
        self.model = model
        st = stelle
        lay = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.ed_name = QtWidgets.QLineEdit(st.name if st else "")
        form.addRow("Name", self.ed_name)
        self.sp_knoten = QtWidgets.QSpinBox()
        self.sp_knoten.setRange(0, max(model.nn - 1, 0))
        self.sp_knoten.setValue(int(st.knoten) if st else int(knoten or 0))
        form.addRow("Knoten", self.sp_knoten)
        self.cb_stab = QtWidgets.QComboBox()
        self.cb_stab.addItem("(Stab am Knoten suchen)", "")
        for k in model.members:
            self.cb_stab.addItem(k, k)
        if st and st.stab:
            self.cb_stab.setCurrentText(st.stab)
        form.addRow("Stab (Querschnitt)", self.cb_stab)
        self.cb_quelle = QtWidgets.QComboBox()
        self.cb_quelle.addItem("Knotenlast der Kombination", "last")
        self.cb_quelle.addItem("Auflagerkraft", "auflager")
        if st:
            self.cb_quelle.setCurrentIndex(max(0, self.cb_quelle.findData(st.quelle)))
        form.addRow("Kraft aus", self.cb_quelle)
        self.cb_typ = QtWidgets.QComboBox()
        for k, text in EINLEITUNGSARTEN.items():
            self.cb_typ.addItem(f"{k} – {text}", k)
        if st:
            self.cb_typ.setCurrentIndex(max(0, self.cb_typ.findData(st.typ)))
        form.addRow("Art (Bild 6.1)", self.cb_typ)
        self.ed_ss = NumEdit((st.s_s * 1e3) if st else 100.0, 90)
        form.addRow("Lasteinleitungslänge s_s [mm]", self.ed_ss)
        self.ed_a = NumEdit((st.a * 1e3) if st else 0.0, 90)
        form.addRow("Abstand der Quersteifen a [mm] (0 = keine)", self.ed_a)
        self.ed_c = NumEdit((st.c * 1e3) if st else 0.0, 90)
        form.addRow("Abstand vom Trägerende c [mm] (nur Art c)", self.ed_c)
        self.cb_richtung = QtWidgets.QComboBox()
        for i, n in enumerate(("x", "y", "z")):
            self.cb_richtung.addItem(f"Kraft in {n}", i)
        self.cb_richtung.setCurrentIndex(int(st.richtung) if st else 2)
        form.addRow("Richtung", self.cb_richtung)
        self.ed_text = QtWidgets.QLineEdit(st.beschreibung if st else "")
        form.addRow("Beschreibung", self.ed_text)
        lay.addLayout(form)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                        | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def result(self) -> tuple:
        return self.ed_name.text().strip(), {
            "knoten": int(self.sp_knoten.value()),
            "stab": self.cb_stab.currentData(),
            "quelle": self.cb_quelle.currentData(),
            "typ": self.cb_typ.currentData(),
            "s_s": self.ed_ss.value() * 1e-3, "a": self.ed_a.value() * 1e-3,
            "c": self.ed_c.value() * 1e-3,
            "richtung": int(self.cb_richtung.currentData()),
            "beschreibung": self.ed_text.text().strip()}


class VerformungsgrenzeDialog(QtWidgets.QDialog):
    """Einen Verformungsnachweis (GZG) festlegen.

    Drei Bezuege: die Durchbiegung eines Stabes (bezogen auf die Sehne), die
    Verschiebung eines Knotens oder die Verschiebung zweier Knoten
    gegeneinander - letzteres fuer Dichtungen, Fuehrungen und Fugen.
    """

    def __init__(self, parent, model, grenze=None, knoten=None):
        super().__init__(parent)
        from ..model import VERFORMUNGSGROESSEN
        from ..gzg import SITUATIONEN
        self.setWindowTitle("Verformungsnachweis" + (f" {grenze.name}" if grenze else ""))
        self.model = model
        g = grenze
        lay = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.ed_name = QtWidgets.QLineEdit(g.name if g else "")
        self.ed_name.setPlaceholderText("z. B. Durchbiegung Riegel")
        form.addRow("Name", self.ed_name)

        self.cb_art = QtWidgets.QComboBox()
        for text, key in (("Stab – Durchbiegung bezogen auf die Sehne", "stab"),
                          ("Knoten – Verschiebung gegenüber der Ausgangslage", "knoten"),
                          ("Punktpaar – zwei Knoten gegeneinander", "punktpaar")):
            self.cb_art.addItem(text, key)
        if g:
            self.cb_art.setCurrentIndex(max(0, self.cb_art.findData(g.art)))
        form.addRow("Bezug", self.cb_art)

        self.cb_stab = QtWidgets.QComboBox()
        self.cb_stab.addItems(list(model.members))
        if g and g.stab:
            self.cb_stab.setCurrentText(g.stab)
        form.addRow("Stab", self.cb_stab)

        vor = ", ".join(str(int(n)) for n in (g.knoten if g else (knoten or [])))
        self.ed_knoten = QtWidgets.QLineEdit(vor)
        self.ed_knoten.setPlaceholderText("Knotennummern, z. B. 12 oder 12, 34")
        form.addRow("Knoten", self.ed_knoten)

        self.cb_groesse = QtWidgets.QComboBox()
        for k, text in VERFORMUNGSGROESSEN.items():
            self.cb_groesse.addItem(f"{k} – {text}", k)
        if g:
            self.cb_groesse.setCurrentIndex(max(0, self.cb_groesse.findData(g.groesse)))
        form.addRow("Größe", self.cb_groesse)

        self.cb_grenzart = QtWidgets.QComboBox()
        self.cb_grenzart.addItem("L / x (bezogen auf die Länge)", "L/x")
        self.cb_grenzart.addItem("absoluter Wert", "absolut")
        if g:
            self.cb_grenzart.setCurrentIndex(max(0, self.cb_grenzart.findData(g.grenzart)))
        form.addRow("Art der Grenze", self.cb_grenzart)

        # absolute Grenzen werden in mm beziehungsweise mrad eingegeben
        vor_wert = (g.wert * 1e3 if g and g.grenzart == "absolut"
                    else (g.wert if g else 300.0))
        self.ed_wert = NumEdit(vor_wert, 90)
        self.lbl_wert = QtWidgets.QLabel("Nenner x")
        form.addRow(self.lbl_wert, self.ed_wert)

        self.cb_sit = QtWidgets.QComboBox()
        for k, text in SITUATIONEN.items():
            self.cb_sit.addItem(f"{text} ({k})", k)
        self.cb_sit.addItem("alle GZG-Kombinationen", "")
        if g:
            self.cb_sit.setCurrentIndex(max(0, self.cb_sit.findData(g.situation)))
        form.addRow("Bemessungssituation", self.cb_sit)

        self.ed_wc = NumEdit((g.ueberhoehung * 1e3) if g else 0.0, 90)
        form.addRow("Überhöhung w_c [mm]", self.ed_wc)
        self.ed_text = QtWidgets.QLineEdit(g.beschreibung if g else "")
        form.addRow("Beschreibung", self.ed_text)
        lay.addLayout(form)

        self.hinweis = QtWidgets.QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet("color:#66717c;")
        lay.addWidget(self.hinweis)

        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                        | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for w in (self.cb_art, self.cb_grenzart):
            w.currentIndexChanged.connect(self._umschalten)
        self._umschalten()

    def _umschalten(self):
        art = self.cb_art.currentData()
        self.cb_stab.setEnabled(art == "stab")
        self.ed_knoten.setEnabled(art != "stab")
        lx = self.cb_grenzart.currentData() == "L/x"
        self.lbl_wert.setText("Nenner x" if lx else "Grenzwert [mm bzw. mrad]")
        if lx and art == "knoten":
            self.hinweis.setText("L/x braucht eine Bezugslänge – für einen einzelnen "
                                 "Knoten einen absoluten Grenzwert wählen.")
        elif art == "punktpaar":
            self.hinweis.setText("Zwei Knotennummern angeben. Nachgewiesen wird ihre "
                                 "Verschiebung gegeneinander – für Dichtungen, "
                                 "Führungen und Fugen (DIN 19704).")
        elif art == "stab":
            self.hinweis.setText("Die Durchbiegung wird auf die Sehne zwischen den "
                                 "Stabenden bezogen und aus der Momentenlinie gewonnen.")
        else:
            self.hinweis.setText("Verschiebung des Knotens gegenüber der Ausgangslage.")

    def result(self):
        """(Name, Angaben) fuer model.add_verformungsgrenze - oder eine Ausnahme."""
        art = self.cb_art.currentData()
        knoten = parse_int_list(self.ed_knoten.text())
        wert = self.ed_wert.value()
        if self.cb_grenzart.currentData() == "absolut":
            wert = wert * 1e-3          # mm bzw. mrad -> m bzw. rad
        return self.ed_name.text().strip(), {
            "art": art, "stab": self.cb_stab.currentText() if art == "stab" else "",
            "knoten": knoten, "groesse": self.cb_groesse.currentData(),
            "grenzart": self.cb_grenzart.currentData(), "wert": wert,
            "situation": self.cb_sit.currentData(),
            "ueberhoehung": self.ed_wc.value() * 1e-3,
            "beschreibung": self.ed_text.text().strip()}


class StellungDialog(QtWidgets.QDialog):
    """Eine Stellung des Systems anlegen oder aendern (bewegliche Bruecken).

    Jede Stellung ist ein eigener Rechenlauf: welche Lager greifen, welche
    Lastfaelle gelten, um welchen Winkel das bewegte Bauteil gedreht ist und
    welches Antriebsmoment es haelt.
    """

    def __init__(self, parent=None, stellung=None, model=None):
        super().__init__(parent)
        self.setWindowTitle("Stellung" + (f" {stellung.name}" if stellung else " anlegen"))
        self._model = model
        s = stellung
        lay = QtWidgets.QVBoxLayout(self)

        self.ed_name = QtWidgets.QLineEdit(s.name if s else "")
        self.ed_winkel = NumEdit(s.winkel if s else 0.0, 80)
        lay.addWidget(row("Name", self.ed_name, "Stellungswinkel [°]", self.ed_winkel))
        self.ed_text = QtWidgets.QLineEdit(s.beschreibung if s else "")
        lay.addWidget(row("Beschreibung", self.ed_text))

        g = QtWidgets.QGroupBox("Lager und Lastfälle in dieser Stellung")
        gl = QtWidgets.QVBoxLayout(g)
        self.ed_aus = QtWidgets.QLineEdit(", ".join(s.lager_aus) if s else "")
        self.ed_aktiv = QtWidgets.QLineEdit(", ".join(s.lager_aktiv) if s else "")
        gl.addWidget(row("Lager aus (Namen, Komma)", self.ed_aus))
        gl.addWidget(row("nur diese Lager aktiv (leer = alle)", self.ed_aktiv))
        self.ed_faelle = QtWidgets.QLineEdit(", ".join(s.faelle) if s else "")
        gl.addWidget(row("Lastfälle (leer = alle)", self.ed_faelle))
        if model is not None and model.load_cases:
            hint = QtWidgets.QLabel("vorhanden: " + ", ".join(list(model.load_cases)[:12]))
            hint.setStyleSheet("color:#66717c; font-size:11px;")
            hint.setWordWrap(True)
            gl.addWidget(hint)
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Bewegtes Bauteil drehen")
        gl = QtWidgets.QVBoxLayout(g)
        self.ed_dreh = NumEdit(s.dreh_winkel if s else 0.0, 80)
        self.ed_gruppen = QtWidgets.QLineEdit(", ".join(s.dreh_gruppen) if s else "")
        gl.addWidget(row("Drehwinkel [°]", self.ed_dreh,
                         "Gruppen (leer = alles ohne Lager)", self.ed_gruppen))
        a = s.dreh_achse if s else (0.0, 1.0, 0.0)
        p = s.dreh_punkt if s else (0.0, 0.0, 0.0)
        self.ed_achse = [NumEdit(v, 60) for v in a]
        self.ed_punkt = [NumEdit(v, 70) for v in p]
        gl.addWidget(row("Drehachse", *self.ed_achse))
        gl.addWidget(row("Punkt auf der Achse [m]", *self.ed_punkt))
        lay.addWidget(g)

        g = QtWidgets.QGroupBox("Antriebsmoment (hält die Stellung)")
        gl = QtWidgets.QVBoxLayout(g)
        kn, mv = (s.antrieb if (s and s.antrieb) else (None, (0.0, 0.0, 0.0)))
        self.ed_knoten = QtWidgets.QLineEdit("" if kn is None else str(int(kn) + 1))
        self.ed_moment = [NumEdit(v / 1e3, 80) for v in mv]
        gl.addWidget(row("Knoten (Nummer, leer = kein Antrieb)", self.ed_knoten))
        gl.addWidget(row("Mx [kNm]", self.ed_moment[0], "My", self.ed_moment[1],
                         "Mz", self.ed_moment[2]))
        lay.addWidget(g)
        lay.addWidget(buttons(self))

    @staticmethod
    def _liste(text: str) -> list:
        return [x.strip() for x in text.split(",") if x.strip()]

    def stellung(self):
        from ..bridges.positions import Stellung
        antrieb = None
        t = self.ed_knoten.text().strip()
        if t:
            try:
                antrieb = (int(float(t.replace(",", "."))) - 1,
                           [e.value() * 1e3 for e in self.ed_moment])
            except ValueError:
                antrieb = None
        return Stellung(
            name=self.ed_name.text().strip() or "Stellung",
            winkel=self.ed_winkel.value(),
            beschreibung=self.ed_text.text().strip(),
            lager_aktiv=self._liste(self.ed_aktiv.text()),
            lager_aus=self._liste(self.ed_aus.text()),
            faelle=self._liste(self.ed_faelle.text()),
            dreh_achse=tuple(e.value() for e in self.ed_achse),
            dreh_punkt=tuple(e.value() for e in self.ed_punkt),
            dreh_winkel=self.ed_dreh.value(),
            dreh_gruppen=self._liste(self.ed_gruppen.text()),
            antrieb=antrieb)
