"""Vorspannung je Anker in der Oberflaeche (16.10.2026): Zuordnungsdialog und Maskenfelder.

Der Zuordnungsdialog zeigt je Gruppe gleicher Vorspannungen an denselben
Staeben (statik3d.vorspannung.gruppen_finden) die Kraft, die nach elastischer
Verkuerzung wirkt, und laesst den Anwender jede Gruppe einem Zustand (keine
Zuordnung, Zeitpunkt 0, Zeitpunkt ∞) und einer Definition zuordnen. Erst
„Übernehmen“ stellt die Lastfaelle auf Verweise um (vorspannung.zuordnen);
„Abbrechen“ laesst alles, wie es ist.
"""
from __future__ import annotations

import re

from PySide6 import QtCore, QtWidgets

from .. import vorspannung as vsp
from ..model import VORSPANN_ENDWERT_ABSOLUT, VORSPANN_ENDWERT_VERLUST, VORSPANN_ZUSTAND_0, VORSPANN_ZUSTAND_INF
from . import zahlenfeld as zf

ZUSTAND_WAHL = (("", "keine Zuordnung (bleibt, wie es ist)"), (VORSPANN_ZUSTAND_0, "Zeitpunkt 0"),
                (VORSPANN_ZUSTAND_INF, "Zeitpunkt ∞"))
ENDWERT_WAHL = ((VORSPANN_ENDWERT_ABSOLUT, "P_∞ absolut"), (VORSPANN_ENDWERT_VERLUST, "Verlust ΔP_t"))

SPALTEN = ("Vorspannung in den Lastfällen", "wirksam nach elastischer Verkürzung", "Zustand", "Definition",
           "Wert [kN]", "Δs [mm]", "Spanngruppe", "Endwert (∞)")


def staebe_lesen(text: str, model=None) -> list:
    """Stabnamen aus „S1–S16, S20“ (Bereiche mit – oder -) oder „S1, S2“;
    mit ``model`` nur die, die es gibt, in der Reihenfolge des Textes."""
    out = []
    for teil in re.split(r"[,;]\s*", str(text or "").strip()):
        teil = teil.strip()
        if not teil:
            continue
        m = re.match(r"^(\D*)(\d+)\s*[–-]\s*(\D*)(\d+)$", teil)
        if m and (m.group(3) in ("", m.group(1))):
            a, b = int(m.group(2)), int(m.group(4))
            namen = [f"{m.group(1)}{i}" for i in range(min(a, b), max(a, b) + 1)]
        else:
            namen = [teil]
        for n in namen:
            if n not in out and (model is None or n in (getattr(model, "members", None) or {})):
                out.append(n)
    return out


class ZuordnungDialog(QtWidgets.QDialog):
    """Gruppen der Vorspannung den Zustaenden und Definitionen zuordnen."""

    def __init__(self, model, ergebnisse: dict = None, parent=None, gruppen: list = None):
        super().__init__(parent)
        self.setWindowTitle("Vorspannung je Anker zuordnen")
        self.model = model
        self.gruppen = list(gruppen if gruppen is not None else vsp.gruppen_finden(model, ergebnisse))
        lay = QtWidgets.QVBoxLayout(self)
        erkl = QtWidgets.QLabel(
            "Die Vorspannungen an denselben Stäben sind nach Wert zu Gruppen gefasst. Je Gruppe steht die "
            "Kraft, die nach elastischer Verkürzung wirkt. Ordnen Sie jede Gruppe einem Zeitpunkt und einer "
            "Definition zu: Zeitpunkt 0 setzt die Pressenkraft P_max und den Schlupf Δs (P₀ rechnet das "
            "Programm), Zeitpunkt ∞ den Endwert P_∞ absolut oder den Verlust ΔP_t. Erst „Übernehmen“ stellt "
            "die Lastfälle auf Verweise um; eine Gruppe ohne Zuordnung bleibt, wie sie ist.")
        erkl.setWordWrap(True)
        lay.addWidget(erkl)
        self.tabelle = QtWidgets.QTableWidget(len(self.gruppen), len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(list(SPALTEN))
        self.tabelle.verticalHeader().setVisible(False)
        namen = list(vsp.definitionen(model)) or ["V1"]
        self.zeilen = []
        for r, g in enumerate(self.gruppen):
            t = QtWidgets.QTableWidgetItem(vsp.gruppe_text(g))
            t.setFlags(t.flags() & ~QtCore.Qt.ItemIsEditable)
            t.setToolTip(", ".join(g["faelle"][:40]) + (" …" if len(g["faelle"]) > 40 else ""))
            self.tabelle.setItem(r, 0, t)
            x = QtWidgets.QTableWidgetItem(vsp.x_text(g) or "–")
            x.setFlags(x.flags() & ~QtCore.Qt.ItemIsEditable)
            self.tabelle.setItem(r, 1, x)
            zst = QtWidgets.QComboBox()
            for k, text in ZUSTAND_WAHL:
                zst.addItem(text, k)
            dfn = QtWidgets.QComboBox()
            dfn.setEditable(True)
            dfn.addItems(namen)
            wert = zf.Zahlenfeld(0.0, 90)
            ds = zf.Zahlenfeld(float(g.get("schlupf", 0.0)) * 1e3, 70)
            sg = QtWidgets.QSpinBox()
            sg.setRange(1, 99)
            ew = QtWidgets.QComboBox()
            for k, text in ENDWERT_WAHL:
                ew.addItem(text, k)
            for c, w in ((2, zst), (3, dfn), (4, wert), (5, ds), (6, sg), (7, ew)):
                self.tabelle.setCellWidget(r, c, w)
            z = {"zustand": zst, "definition": dfn, "wert": wert, "schlupf": ds, "spanngruppe": sg, "endwert": ew}
            self.zeilen.append(z)
            zst.currentIndexChanged.connect(lambda _i, r_=r: self._zustand_gewechselt(r_))
            ew.currentIndexChanged.connect(lambda _i, r_=r: self._endwert_gewechselt(r_))
            self._freigeben(r)
        self.tabelle.resizeColumnsToContents()
        lay.addWidget(self.tabelle)
        self.meldung = QtWidgets.QLabel("")
        self.meldung.setWordWrap(True)
        lay.addWidget(self.meldung)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.button(QtWidgets.QDialogButtonBox.Ok).setText("Übernehmen")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.resize(1200, 160 + 34 * max(3, len(self.gruppen)))
        self.ergebnis = None

    # -- Zeilen ---------------------------------------------------------
    def _zustand(self, r: int) -> str:
        return str(self.zeilen[r]["zustand"].currentData() or "")

    def _freigeben(self, r: int) -> None:
        z = self._zustand(r)
        w = self.zeilen[r]
        for k in ("definition", "wert"):
            w[k].setEnabled(bool(z))
        for k in ("schlupf", "spanngruppe"):
            w[k].setEnabled(z == VORSPANN_ZUSTAND_0)
        w["endwert"].setEnabled(z == VORSPANN_ZUSTAND_INF)
        w["wert"].setToolTip({VORSPANN_ZUSTAND_0: "Pressenkraft P_max [kN]",
                              VORSPANN_ZUSTAND_INF: "P_∞ [kN] bzw. Verlust ΔP_t [kN]"}.get(z, ""))

    def _zustand_gewechselt(self, r: int) -> None:
        z = self._zustand(r)
        v = vsp.vorschlag(self.gruppen[r], z)
        w = self.zeilen[r]
        if z == VORSPANN_ZUSTAND_0:
            w["wert"].setzen(round(v["P_max"] / 1e3, 3))
            w["schlupf"].setzen(round(float(v["schlupf"]) * 1e3, 6))
        elif z == VORSPANN_ZUSTAND_INF:
            self._endwert_gewechselt(r)
        self._freigeben(r)

    def _endwert_gewechselt(self, r: int) -> None:
        if self._zustand(r) != VORSPANN_ZUSTAND_INF:
            return
        w = self.zeilen[r]
        verlust = w["endwert"].currentData() == VORSPANN_ENDWERT_VERLUST
        w["wert"].setzen(0.0 if verlust else round(self.gruppen[r]["N0"] / 1e3, 3))

    def setzen(self, r: int, zustand: str, definition: str = None, wert_kn: float = None,
               schlupf_mm: float = None, spanngruppe: int = None, endwert: str = None) -> None:
        """Eine Zeile setzen (wie der Anwender es tut; Tests und Skripte)."""
        w = self.zeilen[r]
        w["zustand"].setCurrentIndex([k for k, _t in ZUSTAND_WAHL].index(zustand))
        if endwert is not None:
            w["endwert"].setCurrentIndex([k for k, _t in ENDWERT_WAHL].index(endwert))
        if definition is not None:
            w["definition"].setCurrentText(definition)
        if wert_kn is not None:
            w["wert"].setzen(wert_kn)
        if schlupf_mm is not None:
            w["schlupf"].setzen(schlupf_mm)
        if spanngruppe is not None:
            w["spanngruppe"].setValue(int(spanngruppe))

    def zeile_zu(self, art: str, N0: float) -> int:
        """Die Zeile der Gruppe mit dieser Art und diesem Wert [N] (-1: keine)."""
        for r, g in enumerate(self.gruppen):
            if g["art"] == art and abs(g["N0"] - float(N0)) <= 1e-6 * max(abs(float(N0)), 1.0):
                return r
        return -1

    def eintraege(self) -> list:
        """Die Eintraege fuer vorspannung.zuordnen (Kraefte in N, Schlupf in m).
        Ungueltige Zahlen: zl.Eingabefehler."""
        out = []
        for r, g in enumerate(self.gruppen):
            w = self.zeilen[r]
            z = self._zustand(r)
            e = {"gruppe": g, "zustand": z, "definition": w["definition"].currentText().strip()}
            if z == VORSPANN_ZUSTAND_0:
                e.update(P_max=w["wert"].wert() * 1e3, schlupf=w["schlupf"].wert() / 1e3,
                         spanngruppe=int(w["spanngruppe"].value()))
            elif z == VORSPANN_ZUSTAND_INF:
                ew = str(w["endwert"].currentData() or VORSPANN_ENDWERT_ABSOLUT)
                e["endwert"] = ew
                if ew == VORSPANN_ENDWERT_VERLUST:
                    e["dP_t"] = w["wert"].wert() * 1e3
                else:
                    e["P_inf"] = w["wert"].wert() * 1e3
            out.append(e)
        return out

    def _ok(self) -> None:
        """Erst pruefen (vorspannung.zuordnung_pruefen, aendert nichts), dann
        schliessen; der Aufrufer stellt danach das Modell um."""
        from .. import zahlen as zl
        try:
            eintraege = self.eintraege()
            vsp.zuordnung_pruefen(self.model, eintraege)
        except (ValueError, zl.Eingabefehler) as ex:
            self.meldung.setText(f"Nicht übernommen: {ex}")
            return
        self.ergebnis = eintraege
        self.accept()


def anwenden(model, eintraege: list) -> dict:
    """Die Eintraege des Dialogs am Modell ausfuehren (vorspannung.zuordnen)."""
    return vsp.zuordnen(model, eintraege)
