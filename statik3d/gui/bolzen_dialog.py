"""Dialog „Als Bolzen nachweisen…“ (seit 06.11.2026, statik3d.ec3.bolzen).

Der Anwender legt einen oder mehrere Volumenkoerper als Bolzen fest: Durchmesser
(Pflicht, leer ist nicht erlaubt) und Werkstoff (Pflicht, aus den vorhandenen
Werkstoffen; kein Vorgabewert). Ohne beides gibt es keinen Bolzennachweis; das
Programm leitet nichts aus dem Namen oder der Form des Koerpers ab. „Festlegung
aufheben“ nimmt die Markierung zurueck. Die Auswertung (:func:`lesen`) ist ohne
Qt pruefbar.
"""
from __future__ import annotations

from PySide6 import QtWidgets

from .. import zahlen as zl

KEIN_WERKSTOFF = "– bitte wählen –"


def lesen(d_text: str, werkstoff: str):
    """(d [m], Werkstoff) aus den Eingaben; ValueError mit Grund bei fehlender
    Angabe."""
    t = str(d_text or "").strip().replace(",", ".")
    if not t:
        raise ValueError("Durchmesser fehlt")
    d = float(t) * 1e-3
    if d <= 0:
        raise ValueError("Durchmesser muss größer als 0 sein")
    if not werkstoff or werkstoff == KEIN_WERKSTOFF:
        raise ValueError("Werkstoff fehlt")
    return d, werkstoff


def lesen_fuge(text: str):
    """Lage der Scherfuge [m] ab dem Bolzenanfang; leer = None (das Programm bestimmt sie
    aus den Kontaktbereichen). ValueError mit Grund bei unsinniger Eingabe."""
    t = str(text or "").strip().replace(",", ".")
    if not t:
        return None
    try:
        s = float(t) * 1e-3
    except ValueError:
        raise ValueError("Lage der Scherfuge ist keine Zahl") from None
    if s < 0:
        raise ValueError("Lage der Scherfuge darf nicht negativ sein")
    return s


class BolzenDialog(QtWidgets.QDialog):
    """``ergebnis`` nach exec(): "festlegen", "aufheben" oder None."""

    def __init__(self, model, namen: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Als Bolzen nachweisen")
        self.ergebnis = None
        lay = QtWidgets.QVBoxLayout(self)
        text = QtWidgets.QLabel(
            f"Nachweis als Bolzen nach EN 1993-1-8, 3.13 (Tab. 3.10) für: {', '.join(namen[:6])}"
            f"{' …' if len(namen) > 6 else ''}. Durchmesser und Werkstoff des Bolzens gibt der Anwender an; "
            "f_u und f_y kommen allein aus diesem Werkstoff. Ohne beide Angaben wird nicht nachgewiesen. "
            "Die Querkraft kommt aus den Kontaktkräften der Lastfälle, das Biegemoment ist netzabhängig.")
        text.setWordWrap(True)
        lay.addWidget(text)
        form = QtWidgets.QFormLayout()
        self.d = QtWidgets.QLineEdit()
        self.d.setPlaceholderText("z. B. 25")
        form.addRow("Durchmesser d [mm]", self.d)
        self.w = QtWidgets.QComboBox()
        self.w.addItems([KEIN_WERKSTOFF] + list(model.materials))
        form.addRow("Werkstoff des Bolzens", self.w)
        self.fuge = QtWidgets.QLineEdit()
        self.fuge.setPlaceholderText("leer: aus den Kontaktbereichen")
        self.fuge.setToolTip("Nur nötig, wenn der Nachweis danach fragt. Abstand vom Bolzenanfang; der Anfang ist "
                             "das Ende mit der kleineren Koordinate in der Hauptrichtung der Bolzenachse.")
        form.addRow("Lage der Scherfuge [mm]", self.fuge)
        lay.addLayout(form)
        vorhanden = [model.koerper[n].bolzen for n in namen if n in model.koerper and model.koerper[n].bolzen]
        if vorhanden:
            b = vorhanden[0]
            self.d.setText(zl.zahl_text(float(b.get('d', 0.0)) * 1e3, tausender=False))
            i = self.w.findText(str(b.get("werkstoff", "")))
            if i >= 0:
                self.w.setCurrentIndex(i)
            if b.get("fuge") is not None:
                self.fuge.setText(zl.zahl_text(float(b["fuge"]) * 1e3, tausender=False))
        self.fehler = QtWidgets.QLabel("")
        lay.addWidget(self.fehler)
        knoepfe = QtWidgets.QHBoxLayout()
        self.b_auf = QtWidgets.QPushButton("Festlegung aufheben")
        self.b_auf.setEnabled(bool(vorhanden))
        self.b_auf.clicked.connect(self._aufheben)
        knoepfe.addWidget(self.b_auf)
        knoepfe.addStretch(1)
        self.b_ok = QtWidgets.QPushButton("Festlegen")
        self.b_ok.clicked.connect(self._festlegen)
        b_ab = QtWidgets.QPushButton("Abbrechen")
        b_ab.clicked.connect(self.reject)
        knoepfe.addWidget(self.b_ok)
        knoepfe.addWidget(b_ab)
        lay.addLayout(knoepfe)

    def werte(self):
        return lesen(self.d.text(), self.w.currentText())

    def scherfuge(self):
        return lesen_fuge(self.fuge.text())

    def _festlegen(self):
        try:
            self.werte()
            self.scherfuge()
        except ValueError as ex:
            self.fehler.setText(str(ex))
            return
        self.ergebnis = "festlegen"
        self.accept()

    def _aufheben(self):
        self.ergebnis = "aufheben"
        self.accept()
