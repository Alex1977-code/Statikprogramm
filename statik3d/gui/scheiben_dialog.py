"""Dialog „Scheiben einleiten“ (seit 16.10.2026, statik3d.scheibeneinleitung).

Je Gruppe gleicher Bohrung (oder je Scheibe) eine Zeile: Einleitung „Lochrand
starr (bisher)“ oder „Kreisring verteilend (RBE3, flächenanteilig)“, Innen-Ø
(leer = Bohrung aus der Geometrie), Außen-Ø (vorbelegt mit dem Normmaß als
Annahme), Herkunft des Maßes und die mittlere Pressung F/A_Ring aus der
Vorspannung mit ihrem Verhältnis zu f_y. Ein eingetragenes Außenmaß löscht das
Kennzeichen „Annahme“. Umgestellt wird nur mit „Übernehmen“ oder „Alle auf
Kreisring“; die Geometrie bleibt unberührt (Regel des Anwenders: RFEM-Importe
nicht selbstständig in der Geometrie ändern). Die Auswertung der Zeilen
(:func:`eintraege`) ist ohne Qt pruefbar.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .. import scheibeneinleitung as SCH

SPALTEN = ("Scheiben", "Anzahl", "Stab Ø [mm]", "Bohrung Ø [mm]", "Einleitung", "Innen-Ø [mm]",
           "Außen-Ø [mm]", "Maß", "Pressung F/A_Ring", "Hinweis")


def _mm(x: float) -> str:
    return f"{float(x) * 1e3:.1f}".replace(".", ",")


def _lesen_mm(text: str):
    """mm-Text -> m; leer -> None; ungueltig -> ValueError."""
    t = str(text or "").strip().replace(",", ".")
    if not t:
        return None
    return float(t) * 1e-3


def zeilen_bilden(scheiben: list, je_gruppe: bool) -> list:
    """Die Zeilen der Tabelle: je Gruppe gleicher Bohrung und gleichen Stabs
    (bzw. je Scheibe) {"titel", "namen", "z" (erste Scheibe), "art",
    "d_innen_text", "d_aussen_text", "mass", "pressung", "hinweis"}. Eine
    Gruppe mit unterschiedlichen Einstellungen zeigt die der ersten Scheibe
    und sagt es im Hinweis."""
    if je_gruppe:
        teile = SCH.gruppen(scheiben)
    else:
        teile = [(z["name"], [z]) for z in scheiben]
    aus = []
    for titel, liste in teile:
        z = liste[0]
        gemischt = len({(x["einleitung"], round(x["d_aussen"] * 1e6), x["annahme"]) for x in liste}) > 1
        ring = z["einleitung"] == SCH.RING
        da = z["d_aussen"] if ring else z["vorschlag"]
        mass = ("Annahme: " + (z["quelle"] if ring else z["vorschlag_quelle"])
                if (not ring or z["annahme"]) else (z["quelle"] or "eingetragen"))
        hinweise = [x["hinweis"] for x in liste if x["hinweis"]]
        aus.append({"titel": titel if je_gruppe else f"{z['name']} ({z['stab']})", "namen": [x["name"] for x in liste],
                    "z": z, "art": z["einleitung"],
                    "d_innen_text": "" if not ring or not (z["d_innen"] and abs(z["d_innen"] - z["d_bohrung"]) > 1e-9)
                    else _mm(z["d_innen"]),
                    "d_aussen_text": _mm(da) if da else "", "annahme": (not ring) or z["annahme"],
                    "mass": mass, "pressung": SCH.pressung_text(z),
                    "hinweis": "; ".join(dict.fromkeys(hinweise + (["unterschiedlich eingestellt"] if gemischt else [])))})
    return aus


def eintraege(zeilen: list, gelesen: list) -> list:
    """Aus den Tabellenzeilen und dem Gelesenen [(art, Innen-Text, Außen-Text)]
    die Umstellungen [(namen, art, d_innen, d_aussen oder None = Normmaß)].
    Ein Außen-Ø, der dem vorbelegten Normmaß gleicht, bleibt Annahme; ein
    anderer gilt als eingetragen. Wirft ValueError bei unlesbaren Zahlen."""
    aus = []
    for zl, (art, t_in, t_aus) in zip(zeilen, gelesen):
        if art == SCH.LOCHRAND:
            aus.append((zl["namen"], SCH.LOCHRAND, 0.0, None))
            continue
        di = _lesen_mm(t_in) or 0.0
        da = _lesen_mm(t_aus)
        if da is not None and zl["annahme"] and str(t_aus).strip() == zl["d_aussen_text"]:
            da = None                               # das vorbelegte Normmass: Annahme bleibt
        aus.append((zl["namen"], SCH.RING, di, da))
    return aus


def anwenden(model, umstellungen: list) -> dict:
    """Die Umstellungen ausfuehren; Rueckgabe wie scheibeneinleitung.umstellen,
    ueber alle Zeilen zusammengefasst."""
    ges = {"vorher": {}, "umgestellt": [], "offen": []}
    for namen, art, di, da in umstellungen:
        e = SCH.umstellen(model, namen, art, d_aussen=da, d_innen=di)
        for k, v in e["vorher"].items():
            ges["vorher"].setdefault(k, v)
        ges["umgestellt"] += e["umgestellt"]
        ges["offen"] += e["offen"]
    return ges


class ScheibenDialog(QtWidgets.QDialog):
    """Die Tabelle der Scheiben; ``ergebnis`` nach exec(): "uebernehmen",
    "alle" oder None."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scheiben einleiten")
        self.model = model
        self.scheiben = SCH.scheiben(model)
        self.ergebnis = None
        lay = QtWidgets.QVBoxLayout(self)
        text = QtWidgets.QLabel(
            "Starre Scheiben über einer Bohrung (aus RFEM): „Lochrand starr (bisher)“ hängt die ganze "
            "Kraft als Linie an den Lochrand. „Kreisring verteilend“ leitet sie über die Auflage von "
            "Mutter bzw. Scheibe ein (RBE3, flächenanteilig). Innen-Ø leer = Bohrung; der Außen-Ø ist "
            "mit dem Normmaß vorbelegt und bleibt eine Annahme, bis Sie ein Maß aus der Zeichnung "
            "eintragen. Die Geometrie ändert sich nicht.")
        text.setWordWrap(True)
        lay.addWidget(text)
        kopf = QtWidgets.QHBoxLayout()
        kopf.addWidget(QtWidgets.QLabel("Zeilen:"))
        self.cb_modus = QtWidgets.QComboBox()
        self.cb_modus.addItems(["je Gruppe gleicher Bohrung", "je Scheibe"])
        self.cb_modus.currentIndexChanged.connect(self._fuellen)
        kopf.addWidget(self.cb_modus)
        kopf.addStretch(1)
        lay.addLayout(kopf)
        self.tabelle = QtWidgets.QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(list(SPALTEN))
        self.tabelle.verticalHeader().setVisible(False)
        lay.addWidget(self.tabelle)
        knoepfe = QtWidgets.QHBoxLayout()
        self.b_alle = QtWidgets.QPushButton("Alle auf Kreisring (Normmaße als Annahme)")
        self.b_alle.clicked.connect(self._alle)
        knoepfe.addWidget(self.b_alle)
        knoepfe.addStretch(1)
        self.b_ok = QtWidgets.QPushButton("Übernehmen")
        self.b_ok.clicked.connect(self._uebernehmen)
        b_ab = QtWidgets.QPushButton("Abbrechen")
        b_ab.clicked.connect(self.reject)
        knoepfe.addWidget(self.b_ok)
        knoepfe.addWidget(b_ab)
        lay.addLayout(knoepfe)
        self.resize(1100, 420)
        self._fuellen()

    def _fuellen(self):
        self.zeilen = zeilen_bilden(self.scheiben, self.cb_modus.currentIndex() == 0)
        t = self.tabelle
        t.setRowCount(len(self.zeilen))
        for i, zl in enumerate(self.zeilen):
            z = zl["z"]
            werte = (zl["titel"], str(len(zl["namen"])), _mm(z["d_stab"]) if z["d_stab"] else "–",
                     _mm(z["d_bohrung"]))
            for k, w in enumerate(werte):
                it = QtWidgets.QTableWidgetItem(w)
                it.setFlags(it.flags() & ~QtCore.Qt.ItemIsEditable)
                t.setItem(i, k, it)
            cb = QtWidgets.QComboBox()
            cb.addItems([SCH.TEXTE[SCH.LOCHRAND], SCH.TEXTE[SCH.RING]])
            cb.setCurrentIndex(1 if zl["art"] == SCH.RING else 0)
            t.setCellWidget(i, 4, cb)
            t.setItem(i, 5, QtWidgets.QTableWidgetItem(zl["d_innen_text"]))
            t.setItem(i, 6, QtWidgets.QTableWidgetItem(zl["d_aussen_text"]))
            for k, w in ((7, zl["mass"]), (8, zl["pressung"]), (9, zl["hinweis"])):
                it = QtWidgets.QTableWidgetItem(w)
                it.setFlags(it.flags() & ~QtCore.Qt.ItemIsEditable)
                t.setItem(i, k, it)
        t.resizeColumnsToContents()

    def gelesen(self) -> list:
        """[(art, Innen-Text, Außen-Text)] je Zeile."""
        aus = []
        for i in range(self.tabelle.rowCount()):
            cb = self.tabelle.cellWidget(i, 4)
            art = SCH.RING if cb.currentIndex() == 1 else SCH.LOCHRAND
            aus.append((art, (self.tabelle.item(i, 5) or QtWidgets.QTableWidgetItem("")).text(),
                        (self.tabelle.item(i, 6) or QtWidgets.QTableWidgetItem("")).text()))
        return aus

    def umstellungen(self) -> list:
        return eintraege(self.zeilen, self.gelesen())

    def _uebernehmen(self):
        try:
            self.umstellungen()
        except ValueError as ex:
            QtWidgets.QMessageBox.warning(self, "Scheiben einleiten", f"Maß nicht lesbar: {ex}")
            return
        self.ergebnis = "uebernehmen"
        self.accept()

    def _alle(self):
        self.ergebnis = "alle"
        self.accept()
