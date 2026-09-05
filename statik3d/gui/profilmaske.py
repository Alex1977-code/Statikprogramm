"""
Querschnitte anlegen: Normprofile, Parameterprofile und der freie Editor.

Die Maske steht rechts im Eingabebereich (Modellbaum „Querschnitte → Neu“,
Ribbon „Querschnitt hinzufügen“). Von oben nach unten:

1. **Normprofile** aus der Profildatenbank - nach Art (Doppel-T, U, Hohl, T,
   L), Land und Reihe, mit Kennwerten und Bild.
2. **Eigene Profile** mit Parametern: Rechteck, Kreis, Rohr, Rechteckrohr,
   geschweisstes Doppel-T, U, T, Winkel, Kasten - oder frei nach
   Steifigkeiten.
3. **Profil frei erstellen …**: der Editor, in dem ein Profil aus
   Standardprofilen, Knoten und Elementen (Blechstreifen) und Flaechen
   (Polygone, auch mit Loechern) zusammengesetzt wird - mit Bild und
   Kennwerten, die bei jeder Aenderung mitlaufen.

Alle Masse in **mm** (die Datenhaltung rechnet in m); Winkel in Grad.
"""
from __future__ import annotations

import math
import re

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from . import design as dsg
from .dialogs import NumEdit
from .. import profiles, sections
from ..model import Section

MM = 1e-3

#: Art der Normprofile -> Reihen der Datenbank
TYPEN = [("Doppel-T", ("IPE", "HEA", "HEB", "HEM", "UB", "UC", "W")),
         ("U", ("UPN", "UPE", "PFC", "C")),
         ("Hohl", ("SHS", "RHS", "CHS", "HSS", "PIPE")),
         ("T", ("IPET", "HEAT", "HEBT")),
         ("L", ("L", "LU"))]

#: Selbst erstellbare Profile: (Bezeichnung, Parameter [mm], Vorgaben)
PARAMETER = [
    ("Rechteck", ("b", "h"), (200.0, 300.0)),
    ("Kreis", ("d",), (200.0,)),
    ("Rundrohr", ("d", "t"), (168.3, 5.0)),
    ("Rechteckrohr", ("h", "b", "t"), (200.0, 100.0, 6.0)),
    ("Doppel-T geschweißt", ("h", "b", "tw", "tf"), (300.0, 150.0, 8.0, 12.0)),
    ("U geschweißt", ("h", "b", "tw", "tf"), (200.0, 80.0, 6.0, 10.0)),
    ("T geschweißt", ("h", "b", "tw", "tf"), (150.0, 150.0, 7.0, 10.0)),
    ("Winkel", ("h", "b", "t"), (100.0, 100.0, 10.0)),
    ("Kasten aus Blechen", ("h", "b", "tw", "tf"), (400.0, 300.0, 10.0, 15.0)),
    ("frei (Steifigkeiten)", ("A [cm²]", "Iy [cm⁴]", "Iz [cm⁴]", "It [cm⁴]"),
     (10.0, 1000.0, 500.0, 10.0)),
]


def parameterprofil(art: str, werte, name: str = "") -> Section:
    """Ein Parameterprofil: ``art`` aus PARAMETER, ``werte`` in mm (beim
    freien Profil in cm² und cm⁴). Ohne Namen entsteht einer aus den Massen."""
    v = [float(x) for x in werte]
    m = [x * MM for x in v]
    masse = "x".join(f"{x:g}" for x in v)
    if art == "Rechteck":
        return Section.rectangle(name or f"R {masse}", m[0], m[1])
    if art == "Kreis":
        return Section.circle(name or f"K {masse}", m[0])
    if art == "Rundrohr":
        return Section.pipe(name or f"Rohr {masse}", m[0], m[1], fabrication="welded")
    if art == "Rechteckrohr":
        return Section.rhs(name or f"RR {masse}", m[0], m[1], m[2])
    if art == "Doppel-T geschweißt":
        return Section.i_profile(name or f"I {masse}", m[0], m[1], m[2], m[3],
                                 fabrication="welded")
    if art == "U geschweißt":
        return Section.channel(name or f"U {masse}", m[0], m[1], m[2], m[3],
                               fabrication="welded")
    if art == "T geschweißt":
        return Section.tee(name or f"T {masse}", m[0], m[1], m[2], m[3], fabrication="welded")
    if art == "Winkel":
        return Section.angle(name or f"L {masse}", m[0], m[1], m[2], fabrication="welded")
    if art == "Kasten aus Blechen":
        return sections.box_from_plates(name or f"Kasten {masse}", m[0], m[1], m[2], m[3])
    if art.startswith("frei"):
        return Section(name or "Q", A=v[0] * 1e-4, Iy=v[1] * 1e-8, Iz=v[2] * 1e-8,
                       It=v[3] * 1e-8)
    raise ValueError(f"Profilart „{art}“ unbekannt")


def kennwerte(sec: Section) -> str:
    """Die Kennwerte eines Querschnitts, mehrzeilig, in cm-Einheiten."""
    zeilen = [f"A = {sec.A * 1e4:.2f} cm²   Iy = {sec.Iy * 1e8:.1f} cm⁴   Iz = {sec.Iz * 1e8:.1f} cm⁴",
              f"It = {sec.It * 1e8:.2f} cm⁴   Wel,y = {sec.Wel_y * 1e6:.1f} cm³   "
              f"Wel,z = {sec.Wel_z * 1e6:.1f} cm³"]
    if sec.Wpl_y > sec.Wel_y * 1.0001:
        zeilen.append(f"Wpl,y = {sec.Wpl_y * 1e6:.1f} cm³   Wpl,z = {sec.Wpl_z * 1e6:.1f} cm³")
    if abs(sec.alpha) > 1e-6:
        zeilen.append(f"Hauptachsen um {math.degrees(sec.alpha):+.2f}° gedreht "
                      f"(Iy, Iz sind Hauptwerte)")
    if sec.typ in ("composite", "poly", "seg", "L", "U", "T"):
        zeilen.append(f"Schwerpunkt yc = {sec.yc * 1e3:.1f} mm, zc = {sec.zc * 1e3:.1f} mm")
    zeilen.append(sec.describe())
    return "\n".join(zeilen)


# ==========================================================================
# Bild eines Querschnitts
# ==========================================================================
class Profilbild(QtWidgets.QWidget):
    """Zeichnet den Umriss eines Querschnitts massstaeblich: y nach rechts,
    z nach oben, der Schwerpunkt als Kreuz. Loecher bleiben frei."""

    def __init__(self, parent=None, hoehe: int = 150):
        super().__init__(parent)
        self.setMinimumHeight(hoehe)
        self.setMinimumWidth(120)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.umrisse: list = []
        self.text = ""

    def zeigen(self, sec: Section | None, nachschlagen=None):
        try:
            self.umrisse = sections.umriss(sec, nachschlagen) if sec is not None else []
            self.text = "" if sec is not None else "–"
        except Exception as ex:                    # noqa: BLE001
            self.umrisse, self.text = [], str(ex)
        self.update()

    def paintEvent(self, _ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QtGui.QColor(dsg.FARBEN["flaeche"]))
        rand = 14
        if not self.umrisse:
            p.setPen(QtGui.QColor(dsg.FARBEN["matt"]))
            p.drawText(self.rect(), QtCore.Qt.AlignCenter, self.text or "–")
            p.end()
            return
        alle = np.vstack([np.asarray(u, float) for u, _ in self.umrisse])
        lo, hi = alle.min(axis=0), alle.max(axis=0)
        lo = np.minimum(lo, 0.0)
        hi = np.maximum(hi, 0.0)
        spann = np.maximum(hi - lo, 1e-9)
        w, h = max(self.width() - 2 * rand, 10), max(self.height() - 2 * rand, 10)
        s = min(w / spann[0], h / spann[1])
        cy, cz = (lo + hi) / 2.0

        def X(y):
            return rand + w / 2.0 + (y - cy) * s

        def Y(z):
            return rand + h / 2.0 - (z - cz) * s

        pfad = QtGui.QPainterPath()
        pfad.setFillRule(QtCore.Qt.WindingFill)
        for P, loch in self.umrisse:
            P = np.asarray(P, float)
            # Umlaufsinn: Aussen gegen den Uhrzeiger, Loecher mit - so bleiben
            # Loecher bei ueberlappenden Teilen frei
            flaeche = 0.5 * float(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]))
            if (flaeche < 0) != bool(loch):
                P = P[::-1]
            poly = QtGui.QPolygonF([QtCore.QPointF(X(y), Y(z)) for y, z in P])
            pfad.addPolygon(poly)
            pfad.closeSubpath()
        p.setPen(QtGui.QPen(QtGui.QColor(dsg.FARBEN["akzent"]), 1.3))
        p.setBrush(QtGui.QColor(dsg.FARBEN["akzent_hell"]))
        p.drawPath(pfad)
        # Schwerpunkt und Achsen
        p.setPen(QtGui.QPen(QtGui.QColor(dsg.FARBEN["akzent2"]), 1.0))
        x0, y0 = X(0.0), Y(0.0)
        p.drawLine(QtCore.QPointF(x0 - 7, y0), QtCore.QPointF(x0 + 7, y0))
        p.drawLine(QtCore.QPointF(x0, y0 - 7), QtCore.QPointF(x0, y0 + 7))
        p.setPen(QtGui.QColor(dsg.FARBEN["matt"]))
        f = p.font()
        f.setPointSizeF(8.0)
        p.setFont(f)
        p.drawText(QtCore.QPointF(self.width() - rand + 2, y0 + 4), "y")
        p.drawText(QtCore.QPointF(x0 + 4, rand - 3), "z")
        if self.text:
            p.drawText(self.rect().adjusted(4, 0, -4, -2), QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft,
                       self.text)
        p.end()


# ==========================================================================
# Die Maske rechts
# ==========================================================================
class QuerschnittMaske(QtWidgets.QFrame):
    """Rechts: Normprofile, darunter Parameterprofile, darunter der freie Editor.

    angewendet(Section) - ein Querschnitt soll ins Modell
    geschlossen()       - Maske zu
    """

    angewendet = QtCore.Signal(object)
    geschlossen = QtCore.Signal()

    def __init__(self, parent=None, vorhandene: dict | None = None):
        super().__init__(parent)
        self.setObjectName("maske")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.titel = "Neuer Querschnitt"
        self.n_knoten = 0                       # die Maske braucht keine Klicks in der Ansicht
        self.dehnung = 3                        # rechts den groesseren Teil der Hoehe
        self.vorhandene = dict(vorhandene or {})

        aussen = QtWidgets.QVBoxLayout(self)
        aussen.setContentsMargins(10, 8, 10, 10)
        aussen.setSpacing(6)
        kopf = QtWidgets.QHBoxLayout()
        t = QtWidgets.QLabel(self.titel)
        t.setObjectName("maskentitel")
        kopf.addWidget(t)
        kopf.addStretch(1)
        zu = QtWidgets.QToolButton(self)
        zu.setText("✕")
        zu.setObjectName("maskezu")
        zu.setToolTip("Maske schließen (Esc)")
        zu.clicked.connect(self.schliessen)
        kopf.addWidget(zu)
        aussen.addLayout(kopf)

        self.lbl_vorhanden = QtWidgets.QLabel("")
        self.lbl_vorhanden.setObjectName("maskenhinweis")
        self.lbl_vorhanden.setWordWrap(True)
        aussen.addWidget(self.lbl_vorhanden)
        self.vorhandene_zeigen(self.vorhandene)

        self.ed_name = QtWidgets.QLineEdit()
        self.ed_name.setPlaceholderText("leer = Profilname")
        zeile = QtWidgets.QHBoxLayout()
        zeile.addWidget(QtWidgets.QLabel("Name"))
        zeile.addWidget(self.ed_name, 1)
        aussen.addLayout(zeile)

        # Der Inhalt ist laenger als der rechte Bereich hoch: scrollen
        rolle = QtWidgets.QScrollArea(self)
        rolle.setWidgetResizable(True)
        rolle.setFrameShape(QtWidgets.QFrame.NoFrame)
        rolle.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        rolle.setMinimumHeight(340)
        inhalt = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(inhalt)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(8)
        lay.addWidget(self._norm_gruppe())
        lay.addWidget(self._parameter_gruppe())
        self.btn_frei = QtWidgets.QPushButton("Profil frei erstellen …")
        self.btn_frei.setProperty("rolle", "start")
        self.btn_frei.setToolTip("Ein Profil aus Standardprofilen, Knoten und Elementen "
                                 "(Blechstreifen) und Flächen frei zusammensetzen")
        self.btn_frei.clicked.connect(self.frei_erstellen)
        lay.addWidget(self.btn_frei)
        lay.addStretch(1)
        rolle.setWidget(inhalt)
        aussen.addWidget(rolle, 1)

        self.lbl_hinweis = QtWidgets.QLabel(
            "Normprofil oder Parameterprofil wählen und „Anlegen“ - oder das Profil "
            "frei zusammensetzen. Esc schließt.")
        self.lbl_hinweis.setObjectName("maskenhinweis")
        self.lbl_hinweis.setWordWrap(True)
        aussen.addWidget(self.lbl_hinweis)
        self.setMinimumWidth(300)
        self._typ_gewaehlt()
        self._art_gewechselt()

    # ---- Normprofile -----------------------------------------------------
    def _norm_gruppe(self) -> QtWidgets.QGroupBox:
        g = QtWidgets.QGroupBox("Normprofile (Datenbank)")
        gl = QtWidgets.QVBoxLayout(g)
        gl.setSpacing(5)
        self.cb_land = QtWidgets.QComboBox()
        for code, bez, norm, _f in profiles.countries():
            self.cb_land.addItem(f"{bez} – {norm}", code)
        self.cb_land.currentIndexChanged.connect(self._typ_gewaehlt)
        gl.addWidget(self.cb_land)
        typen = QtWidgets.QHBoxLayout()
        typen.setSpacing(3)
        self.typknoepfe: dict[str, QtWidgets.QToolButton] = {}
        self.typgruppe = QtWidgets.QButtonGroup(self)
        self.typgruppe.setExclusive(True)
        for i, (typ, _fams) in enumerate(TYPEN):
            b = QtWidgets.QToolButton()
            b.setText(typ)
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setToolTip({"Doppel-T": "IPE, HEA, HEB, HEM, UB, UC, W",
                          "U": "UPN, UPE, PFC, C", "Hohl": "SHS, RHS, CHS, HSS, PIPE",
                          "T": "halbierte Doppel-T: IPET, HEAT, HEBT",
                          "L": "Winkel gleich- und ungleichschenklig"}.get(typ, typ))
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self.typgruppe.addButton(b, i)
            self.typknoepfe[typ] = b
            typen.addWidget(b)
        self.typgruppe.idClicked.connect(lambda _i: self._typ_gewaehlt())
        gl.addLayout(typen)
        self.cb_reihe = QtWidgets.QComboBox()
        self.cb_reihe.currentIndexChanged.connect(self._reihe_gewaehlt)
        self.cb_profil = QtWidgets.QComboBox()
        self.cb_profil.currentTextChanged.connect(self._profil_gewaehlt)
        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(4)
        form.addRow("Reihe", self.cb_reihe)
        form.addRow("Profil", self.cb_profil)
        gl.addLayout(form)
        self.bild_norm = Profilbild(hoehe=130)
        gl.addWidget(self.bild_norm)
        self.lbl_norm = QtWidgets.QLabel("")
        self.lbl_norm.setObjectName("maskeninfo")
        self.lbl_norm.setWordWrap(True)
        gl.addWidget(self.lbl_norm)
        self.btn_norm = QtWidgets.QPushButton("Anlegen")
        self.btn_norm.clicked.connect(self.anwenden_norm)
        gl.addWidget(self.btn_norm)
        return g

    def typ(self) -> str:
        for typ, b in self.typknoepfe.items():
            if b.isChecked():
                return typ
        return TYPEN[0][0]

    def _typ_gewaehlt(self):
        """Art oder Land gewechselt: die Reihen dazu."""
        land = self.cb_land.currentData() or "EU"
        fams_typ = dict(TYPEN)[self.typ()]
        im_land = [f for f in profiles.families(land) if f in fams_typ]
        # Gibt es die Art in dem Land nicht (T nur europaeisch), alle Reihen der Art
        reihen = im_land or [f for f in fams_typ if f in profiles.FAMILIES]
        self.cb_reihe.blockSignals(True)
        self.cb_reihe.clear()
        for fam in reihen:
            self.cb_reihe.addItem(f"{fam} – {profiles.FAMILY_INFO.get(fam, (fam,))[0]}", fam)
        self.cb_reihe.blockSignals(False)
        self._reihe_gewaehlt()

    def _reihe_gewaehlt(self):
        fam = self.cb_reihe.currentData()
        self.cb_profil.blockSignals(True)
        self.cb_profil.clear()
        if fam:
            try:
                self.cb_profil.addItems(profiles.list_profiles(fam))
            except KeyError:
                pass
        self.cb_profil.blockSignals(False)
        self._profil_gewaehlt()

    def _profil_gewaehlt(self, _text=None):
        name = self.cb_profil.currentText()
        if not name:
            self.bild_norm.zeigen(None)
            self.lbl_norm.setText("")
            return
        try:
            sec = profiles.make_section(name)
            self.bild_norm.zeigen(sec)
            self.lbl_norm.setText(kennwerte(sec))
        except Exception as ex:                # noqa: BLE001
            self.bild_norm.zeigen(None)
            self.lbl_norm.setText(str(ex))

    def norm_section(self) -> Section:
        # Der Name ist die Bezeichnung, wie sie in der Liste steht („CHS
        # 168.3x5“), nicht die intern normierte Schreibweise
        bez = self.cb_profil.currentText()
        return profiles.make_section(bez, self.ed_name.text().strip() or bez)

    def anwenden_norm(self):
        try:
            sec = self.norm_section()
        except Exception as ex:                # noqa: BLE001
            self.lbl_norm.setText(str(ex))
            return
        self.angewendet.emit(sec)

    # ---- Parameterprofile ------------------------------------------------
    def _parameter_gruppe(self) -> QtWidgets.QGroupBox:
        g = QtWidgets.QGroupBox("Eigene Profile (Parameter in mm)")
        gl = QtWidgets.QVBoxLayout(g)
        gl.setSpacing(5)
        self.cb_art = QtWidgets.QComboBox()
        self.cb_art.addItems([a for a, _p, _v in PARAMETER])
        self.cb_art.currentIndexChanged.connect(self._art_gewechselt)
        gl.addWidget(self.cb_art)
        gitter = QtWidgets.QGridLayout()
        gitter.setContentsMargins(0, 0, 0, 0)
        gitter.setHorizontalSpacing(6)
        self.par_lbl: list[QtWidgets.QLabel] = []
        self.par: list[NumEdit] = []
        for i in range(4):
            lb = QtWidgets.QLabel("")
            e = NumEdit(0.0, 74)
            e.textChanged.connect(self._parameter_vorschau)
            gitter.addWidget(lb, i // 2, 2 * (i % 2))
            gitter.addWidget(e, i // 2, 2 * (i % 2) + 1)
            self.par_lbl.append(lb)
            self.par.append(e)
        gl.addLayout(gitter)
        self.bild_param = Profilbild(hoehe=120)
        gl.addWidget(self.bild_param)
        self.lbl_param = QtWidgets.QLabel("")
        self.lbl_param.setObjectName("maskeninfo")
        self.lbl_param.setWordWrap(True)
        gl.addWidget(self.lbl_param)
        self.btn_param = QtWidgets.QPushButton("Anlegen")
        self.btn_param.clicked.connect(self.anwenden_parameter)
        gl.addWidget(self.btn_param)
        return g

    def art(self) -> str:
        return self.cb_art.currentText()

    def _art_gewechselt(self):
        art, felder, vorgaben = PARAMETER[self.cb_art.currentIndex()]
        for i in range(4):
            sichtbar = i < len(felder)
            self.par_lbl[i].setVisible(sichtbar)
            self.par[i].setVisible(sichtbar)
            if sichtbar:
                self.par_lbl[i].setText(felder[i])
                self.par[i].blockSignals(True)
                self.par[i].set(vorgaben[i])
                self.par[i].blockSignals(False)
        self._parameter_vorschau()

    def parameter_section(self) -> Section:
        art, felder, _v = PARAMETER[self.cb_art.currentIndex()]
        werte = [self.par[i].value() for i in range(len(felder))]
        return parameterprofil(art, werte, self.ed_name.text().strip())

    def _parameter_vorschau(self, _t=None):
        try:
            sec = self.parameter_section()
            self.bild_param.zeigen(sec)
            self.lbl_param.setText(kennwerte(sec))
        except Exception as ex:                # noqa: BLE001
            self.bild_param.zeigen(None)
            self.lbl_param.setText(str(ex))

    def anwenden_parameter(self):
        try:
            sec = self.parameter_section()
        except Exception as ex:                # noqa: BLE001
            self.lbl_param.setText(str(ex))
            return
        self.angewendet.emit(sec)

    # ---- frei ------------------------------------------------------------
    def frei_erstellen(self):
        d = ProfilEditor(self.window(), vorhandene=self.vorhandene,
                         name=self.ed_name.text().strip())
        if d.exec():
            sec = d.ergebnis()
            if sec is not None:
                self.angewendet.emit(sec)
        return d

    # ---- allgemein ---------------------------------------------------------
    def vorhandene_zeigen(self, sections_: dict):
        self.vorhandene = dict(sections_ or {})
        namen = list(self.vorhandene)
        if namen:
            self.lbl_vorhanden.setText(
                f"{len(namen)} Querschnitte im Modell: " + ", ".join(namen[:8])
                + (" …" if len(namen) > 8 else ""))
        else:
            self.lbl_vorhanden.setText("Noch kein Querschnitt im Modell.")

    def schliessen(self):
        self.hide()
        self.geschlossen.emit()

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_Escape:
            return self.schliessen()
        super().keyPressEvent(ev)


# ==========================================================================
# Freier Profileditor
# ==========================================================================
def _tabelle(spalten: list[str], hoehe: int = 96) -> QtWidgets.QTableWidget:
    t = QtWidgets.QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.verticalHeader().setVisible(False)
    # Spalten teilen sich die Breite: die Kopfzeile bleibt lesbar
    t.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
    t.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    t.setMinimumHeight(hoehe)
    return t


def _zahl(text: str, vorgabe: float = 0.0) -> float:
    try:
        return float(str(text).replace(",", ".").strip())
    except ValueError:
        return vorgabe


class ProfilEditor(QtWidgets.QDialog):
    """Ein Profil **frei** zusammensetzen.

    Links vier Tabellen: Standardprofile (Profil, Lage dy/dz, Drehung,
    Spiegeln), Knoten (Nr, y, z), Elemente (von, bis, t: Blechstreifen
    zwischen zwei Knoten) und Flächen (Knotenfolge als Polygon, wahlweise
    Loch). Rechts das Bild und die Kennwerte; beides läuft bei jeder
    Änderung mit. OK übernimmt das Profil.
    """

    def __init__(self, parent=None, vorhandene: dict | None = None, name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Profil frei erstellen")
        self.resize(900, 620)
        self.vorhandene = dict(vorhandene or {})
        self.sec: Section | None = None
        self._still = False

        haupt = QtWidgets.QHBoxLayout(self)
        links = QtWidgets.QVBoxLayout()
        links.setSpacing(6)

        # --- Standardprofile ---------------------------------------------
        links.addWidget(QtWidgets.QLabel("<b>Standardprofile</b> (Lage des Schwerpunkts dy, dz in mm)"))
        self.tb_teile = _tabelle(["Profil", "dy [mm]", "dz [mm]", "Drehung [°]", "Spiegeln"])
        links.addWidget(self.tb_teile)
        z = QtWidgets.QHBoxLayout()
        self.cb_profilwahl = QtWidgets.QComboBox()
        self.cb_profilwahl.setEditable(True)
        self.cb_profilwahl.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        for n in self.vorhandene:
            self.cb_profilwahl.addItem(n)
        for fam in ("IPE", "HEA", "HEB", "HEM", "IPET", "HEAT", "HEBT", "UPE", "UPN",
                    "L", "LU", "SHS", "RHS", "CHS"):
            try:
                self.cb_profilwahl.addItems(profiles.list_profiles(fam))
            except KeyError:
                pass
        z.addWidget(self.cb_profilwahl, 1)
        b = QtWidgets.QPushButton("+ Profil")
        b.clicked.connect(self.teil_zufuegen)
        z.addWidget(b)
        b = QtWidgets.QPushButton("−")
        b.setToolTip("Gewählte Zeile entfernen")
        b.clicked.connect(lambda: self._zeile_weg(self.tb_teile))
        z.addWidget(b)
        links.addLayout(z)

        # --- Knoten, Elemente, Flaechen ----------------------------------
        zeile = QtWidgets.QHBoxLayout()
        self.tb_knoten = _tabelle(["Nr", "y [mm]", "z [mm]"], 120)
        self.tb_elemente = _tabelle(["von", "bis", "t [mm]"], 120)
        self.tb_flaechen = _tabelle(["Knoten (Folge)", "Loch"], 120)
        for titel, tb, plus in (("<b>Knoten</b>", self.tb_knoten, self.knoten_zufuegen),
                                ("<b>Elemente</b> (Blechstreifen)", self.tb_elemente, self.element_zufuegen),
                                ("<b>Flächen</b> (Polygon aus Knoten)", self.tb_flaechen, self.flaeche_zufuegen)):
            sp = QtWidgets.QVBoxLayout()
            sp.addWidget(QtWidgets.QLabel(titel))
            sp.addWidget(tb)
            kn = QtWidgets.QHBoxLayout()
            b = QtWidgets.QPushButton("+")
            b.clicked.connect(plus)
            kn.addWidget(b)
            b = QtWidgets.QPushButton("−")
            b.clicked.connect(lambda _c=False, t=tb: self._zeile_weg(t))
            kn.addWidget(b)
            kn.addStretch(1)
            sp.addLayout(kn)
            zeile.addLayout(sp)
        links.addLayout(zeile)
        haupt.addLayout(links, 3)

        # --- rechts: Bild, Kennwerte, Name, Knoepfe --------------------------
        rechts = QtWidgets.QVBoxLayout()
        self.bild = Profilbild(hoehe=260)
        rechts.addWidget(self.bild, 1)
        self.lbl_werte = QtWidgets.QLabel("Noch nichts angegeben.")
        self.lbl_werte.setObjectName("maskeninfo")
        self.lbl_werte.setWordWrap(True)
        self.lbl_werte.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        rechts.addWidget(self.lbl_werte)
        nz = QtWidgets.QHBoxLayout()
        nz.addWidget(QtWidgets.QLabel("Name"))
        self.ed_name = QtWidgets.QLineEdit(name)
        self.ed_name.setPlaceholderText("Profil")
        nz.addWidget(self.ed_name, 1)
        rechts.addLayout(nz)
        hinweis = QtWidgets.QLabel(
            "y nach rechts, z nach oben; Masse in mm. Elemente sind Blechstreifen der Dicke t "
            "zwischen zwei Knoten, Flächen geschlossene Polygone (Loch = wird abgezogen). "
            "It: Elemente offen (Σ L·t³/3), Flächen nach Saint-Venant.")
        hinweis.setObjectName("maskenhinweis")
        hinweis.setWordWrap(True)
        rechts.addWidget(hinweis)
        self.knoepfe = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                                  | QtWidgets.QDialogButtonBox.Cancel)
        self.knoepfe.accepted.connect(self.accept)
        self.knoepfe.rejected.connect(self.reject)
        rechts.addWidget(self.knoepfe)
        haupt.addLayout(rechts, 2)

        for tb in (self.tb_teile, self.tb_knoten, self.tb_elemente, self.tb_flaechen):
            tb.itemChanged.connect(lambda _it: self.aktualisieren())
        self.ed_name.textChanged.connect(lambda _t: self.aktualisieren())
        self.aktualisieren()

    # ---- Zeilen ------------------------------------------------------------
    def _zeile(self, tb: QtWidgets.QTableWidget, werte, haken: int | None = None,
               gesetzt: bool = False):
        self._still = True
        r = tb.rowCount()
        tb.insertRow(r)
        for c, v in enumerate(werte):
            it = QtWidgets.QTableWidgetItem("" if v is None else str(v))
            if c == haken:
                it.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled
                            | QtCore.Qt.ItemIsSelectable)
                it.setCheckState(QtCore.Qt.Checked if gesetzt else QtCore.Qt.Unchecked)
                it.setText("")
            tb.setItem(r, c, it)
        self._still = False

    def _zeile_weg(self, tb: QtWidgets.QTableWidget):
        r = tb.currentRow()
        if r < 0:
            r = tb.rowCount() - 1
        if r >= 0:
            tb.removeRow(r)
            self.aktualisieren()

    def teil_zufuegen(self, profil: str = "", dy: float = 0.0, dz: float = 0.0,
                      drehung: float = 0.0, spiegeln: bool = False):
        name = profil or self.cb_profilwahl.currentText().strip()
        if not name:
            return
        self._zeile(self.tb_teile, [name, f"{dy:g}", f"{dz:g}", f"{drehung:g}", ""], 4, spiegeln)
        self.aktualisieren()

    def knoten_zufuegen(self, nr=None, y: float = 0.0, z: float = 0.0):
        if nr is None:
            vorhanden = [int(_zahl(self.tb_knoten.item(r, 0).text(), 0))
                         for r in range(self.tb_knoten.rowCount()) if self.tb_knoten.item(r, 0)]
            nr = (max(vorhanden) + 1) if vorhanden else 1
        self._zeile(self.tb_knoten, [str(int(nr)), f"{y:g}", f"{z:g}"])
        self.aktualisieren()

    def element_zufuegen(self, von=None, bis=None, t: float = 10.0):
        nrn = [int(_zahl(self.tb_knoten.item(r, 0).text(), 0))
               for r in range(self.tb_knoten.rowCount()) if self.tb_knoten.item(r, 0)]
        if von is None:
            von = nrn[-2] if len(nrn) >= 2 else (nrn[0] if nrn else 1)
        if bis is None:
            bis = nrn[-1] if nrn else 2
        self._zeile(self.tb_elemente, [str(int(von)), str(int(bis)), f"{t:g}"])
        self.aktualisieren()

    def flaeche_zufuegen(self, knoten=None, loch: bool = False):
        if knoten is None:
            knoten = [int(_zahl(self.tb_knoten.item(r, 0).text(), 0))
                      for r in range(self.tb_knoten.rowCount()) if self.tb_knoten.item(r, 0)]
        text = ", ".join(str(int(k)) for k in knoten)
        self._zeile(self.tb_flaechen, [text, ""], 1, loch)
        self.aktualisieren()

    def setze(self, teile=(), knoten=None, elemente=(), flaechen=()):
        """Den Editor fuellen (Masse in m wie in der Datenhaltung)."""
        self._still = True
        for tb in (self.tb_teile, self.tb_knoten, self.tb_elemente, self.tb_flaechen):
            tb.setRowCount(0)
        self._still = False
        for t in teile:
            if isinstance(t, dict):
                self.teil_zufuegen(str(t.get("profil", "")), float(t.get("dy", 0)) / MM,
                                   float(t.get("dz", 0)) / MM, float(t.get("drehung", 0)),
                                   bool(t.get("spiegeln", False)))
            else:
                t = list(t) + [0.0, 0.0, 0.0, False][len(t) - 1:]
                self.teil_zufuegen(str(t[0]), float(t[1]) / MM, float(t[2]) / MM,
                                   float(t[3]), bool(t[4]))
        for nr, (y, z) in sorted((knoten or {}).items()):
            self.knoten_zufuegen(int(nr), float(y) / MM, float(z) / MM)
        for a, b, t in elemente:
            self.element_zufuegen(int(a), int(b), float(t) / MM)
        for f in flaechen:
            if isinstance(f, dict):
                self.flaeche_zufuegen([int(i) for i in f.get("knoten", [])], bool(f.get("loch", False)))
            else:
                self.flaeche_zufuegen([int(i) for i in f[0]], bool(f[1]) if len(f) > 1 else False)
        self.aktualisieren()

    def laden(self, sec: Section) -> bool:
        """Ein frei erstelltes Profil wieder oeffnen."""
        inhalt = sections.editor_inhalt(sec)
        if inhalt is None:
            return False
        self.ed_name.setText(sec.name)
        self.setze(inhalt.get("teile", ()), inhalt.get("knoten", {}),
                   inhalt.get("elemente", ()), inhalt.get("flaechen", ()))
        return True

    # ---- Lesen und Rechnen -------------------------------------------------
    def _text(self, tb, r, c) -> str:
        it = tb.item(r, c)
        return it.text() if it is not None else ""

    def _haken(self, tb, r, c) -> bool:
        it = tb.item(r, c)
        return it is not None and it.checkState() == QtCore.Qt.Checked

    def inhalt(self) -> dict:
        """Der Tabelleninhalt in Datenhaltungs-Einheiten (m)."""
        teile = []
        for r in range(self.tb_teile.rowCount()):
            name = self._text(self.tb_teile, r, 0).strip()
            if not name:
                continue
            teile.append({"profil": name,
                          "dy": _zahl(self._text(self.tb_teile, r, 1)) * MM,
                          "dz": _zahl(self._text(self.tb_teile, r, 2)) * MM,
                          "drehung": _zahl(self._text(self.tb_teile, r, 3)),
                          "spiegeln": self._haken(self.tb_teile, r, 4)})
        knoten = {}
        for r in range(self.tb_knoten.rowCount()):
            nr = self._text(self.tb_knoten, r, 0).strip()
            if nr:
                knoten[int(_zahl(nr))] = (_zahl(self._text(self.tb_knoten, r, 1)) * MM,
                                          _zahl(self._text(self.tb_knoten, r, 2)) * MM)
        elemente = []
        for r in range(self.tb_elemente.rowCount()):
            a, b = self._text(self.tb_elemente, r, 0).strip(), self._text(self.tb_elemente, r, 1).strip()
            if a and b:
                elemente.append((int(_zahl(a)), int(_zahl(b)),
                                 _zahl(self._text(self.tb_elemente, r, 2)) * MM))
        flaechen = []
        for r in range(self.tb_flaechen.rowCount()):
            nrn = [int(_zahl(x)) for x in re.split(r"[,;\s]+", self._text(self.tb_flaechen, r, 0)) if x]
            if nrn:
                flaechen.append({"knoten": nrn, "loch": self._haken(self.tb_flaechen, r, 1)})
        return {"teile": teile, "knoten": knoten, "elemente": elemente, "flaechen": flaechen}

    def aktualisieren(self):
        if self._still:
            return
        inhalt = self.inhalt()
        name = self.ed_name.text().strip() or "Profil"
        try:
            self.sec = sections.build_free(name, inhalt["teile"], inhalt["knoten"],
                                           inhalt["elemente"], inhalt["flaechen"],
                                           nachschlagen=self.vorhandene.get)
            self.bild.zeigen(self.sec, self.vorhandene.get)
            self.lbl_werte.setText(kennwerte(self.sec))
            self.lbl_werte.setStyleSheet("")
        except Exception as ex:                # noqa: BLE001
            self.sec = None
            self.bild.zeigen(None)
            self.lbl_werte.setText(str(ex))
            self.lbl_werte.setStyleSheet(f"color: {dsg.FARBEN['schlecht']}")
        self.knoepfe.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(self.sec is not None)

    def ergebnis(self) -> Section | None:
        self.aktualisieren()
        return self.sec
