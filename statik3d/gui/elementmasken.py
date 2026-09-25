"""
Masken „Elemente wählen“ und „Elementübersicht“ im Register Netz, die
Rueckfrage beim Import und die Faerbung der Ansicht nach Elementtyp
(Paket E, 25.09.2026).

Die Logik ohne Oberflaeche steht in :mod:`statik3d.elementauswahl`; hier nur
der Aufbau in den Rahmen der rechten Masken (gui/masken.py) und die
Verbindung zum Hauptfenster. Das Hauptfenster ruft je Befehl eine Funktion
dieses Moduls - so bleibt main.py bei wenigen Zeilen an Ort und Stelle.
"""
from __future__ import annotations

import os

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .. import elementauswahl as ea
from .. import elemente as EL
from . import masken as msk

TITEL_WAHL = "Elemente wählen"
TITEL_UEBERSICHT = "Elementübersicht"
#: Spalten der Uebersicht
SPALTEN = ["Elementtyp", "Ansatz", "Anzahl", "Anteil", "Körper"]
#: Rolle der Zeilendaten im Baum: (Typ, Koerper oder None)
ROLLE = QtCore.Qt.UserRole
#: Bis zu so vielen Elementen steht der Fingerabdruck beim Oeffnen da
FINGERABDRUCK_SOFORT = 300_000


# --------------------------------------------------------------------------
# Elemente waehlen
# --------------------------------------------------------------------------
class Elementwahl(msk.Maske):
    """Die Haken je Familie; Unvertraegliches und Abgeleitetes grau mit Grund.

    ``haken`` {Schluessel: QCheckBox}; ``wahl()`` die angehakten
    anhakbaren Schluessel. „Übernehmen“ schreibt nur Elementansatz und
    Pyramiden in die Netzeinstellungen (elementauswahl.auf_netz)."""

    def __init__(self, netz, parent=None):
        # Wort seit 25.09.2026: bool("aus") waere wahr (ea.sweep_an)
        self.sweep = ea.sweep_an(netz)
        super().__init__(
            TITEL_WAHL, [], parent, knopf="Übernehmen",
            hinweis="Anhaken, was gerechnet werden soll - Unverträgliches wird grau, der Grund "
                    "steht am Zeiger. Die Wahl stellt den Elementansatz und die Pyramiden der "
                    "Netzeinstellungen und wirkt beim nächsten Vernetzen.",
            zusatz=[(f"Statik3D-Vorgabe ({ea.VORGABE_TEXT})", self.vorgabe_setzen)])
        inhalt = QtWidgets.QWidget(self)
        lay = QtWidgets.QVBoxLayout(inhalt)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.haken: dict = {}
        gruppen: dict = {}
        for key, gruppe, text in ea.HAKEN:
            g = gruppen.get(gruppe)
            if g is None:
                g = gruppen[gruppe] = QtWidgets.QGroupBox(gruppe, inhalt)
                QtWidgets.QVBoxLayout(g).setSpacing(2)
                lay.addWidget(g)
            cb = QtWidgets.QCheckBox(text, g)
            cb.setObjectName(f"haken_{key}")
            g.layout().addWidget(cb)
            self.haken[key] = cb
            if key == "hex20":
                # Der Sweep steht daneben, lesbar, nicht verstellbar: die
                # Elementwahl darf ihn nicht einschalten (Auftrag Paket E); einen
                # Haken in den Netzeinstellungen gibt es seit 25.09.2026 nicht mehr
                self.lbl_sweep = QtWidgets.QLabel(g)
                self.lbl_sweep.setObjectName("maskeninfo")
                self.lbl_sweep.setWordWrap(True)
                self.lbl_sweep.setText(
                    "Sweep (Sechsflächner): "
                    + ("an (aus der Datei) - gesweepte Körper werden hex8/pent6." if self.sweep else
                       "aus - keine Option der Oberfläche mehr; diese Wahl schaltet ihn "
                       "nicht ein."))
                g.layout().addWidget(self.lbl_sweep)
        self.lbl_vorschau = QtWidgets.QLabel(inhalt)
        self.lbl_vorschau.setObjectName("maskeninfo")
        self.lbl_vorschau.setWordWrap(True)
        lay.addWidget(self.lbl_vorschau)
        self.inhalt_einfuegen(inhalt)
        self._setzen(ea.wahl_aus_netz(netz))
        for key in ea.ANHAKBAR:
            self.haken[key].toggled.connect(lambda _an: self._nachfuehren())
        self._anfang = self._werte_roh()

    # -- Zustand ---------------------------------------------------------
    def wahl(self) -> set:
        return {k for k in ea.ANHAKBAR if self.haken[k].isChecked()}

    def _setzen(self, wahl: set) -> None:
        for k in ea.ANHAKBAR:
            cb = self.haken[k]
            cb.blockSignals(True)
            cb.setChecked(k in wahl)
            cb.blockSignals(False)
        self._nachfuehren()

    def _nachfuehren(self) -> None:
        """Grau, Haken und Tooltip aus elementauswahl.zustand."""
        z = ea.zustand(self.wahl(), self.sweep)
        for k, cb in self.haken.items():
            d = z[k]
            cb.blockSignals(True)
            if k not in ea.ANHAKBAR or not d["frei"]:
                cb.setChecked(bool(d["an"]))
            cb.setEnabled(bool(d["frei"]))
            cb.blockSignals(False)
            cb.setToolTip(d["grund"])
        self.lbl_vorschau.setText("So wird vernetzt:\n" + "\n".join(
            "• " + z_ for z_ in ea.vorschau(self.wahl(), self.sweep)))

    def vorgabe_setzen(self) -> None:
        """tet10 + VQ83: tet10 an, tet4 aus, Pyramiden wie bisher."""
        self._setzen({"tet10"} | ({"pyr5"} & self.wahl()))

    def werte(self) -> dict:
        w = super().werte()
        w["wahl"] = sorted(self.wahl())
        return w

    def _werte_roh(self) -> dict:
        w = msk.Maske._werte_roh(self)
        w["wahl"] = sorted(self.wahl()) if hasattr(self, "haken") else []
        return w


def maske_elementwahl(w):
    """Netz → Elemente wählen… (rechte Maske)."""
    maske = Elementwahl(w.model.netz)

    def uebernehmen(werte: dict):
        try:
            netz = ea.auf_netz(w.model.netz, set(werte.get("wahl") or ()))
        except ValueError as ex:
            return w.error(str(ex))
        w.merken("Elementwahl")
        w.model.netz = netz
        text = ea.wahl_text(ea.wahl_aus_netz(netz))
        z = ea.typen_zaehlen(w.model)
        vol = {t: n for t, n in z["typen"].items() if t in ("tet4", "tet10")}
        soll = "tet10" if netz.ordnung >= 2 else "tet4"
        rest = sum(n for t, n in vol.items() if t != soll)
        w.info(f"Elementwahl: {text} - wirkt beim nächsten Vernetzen"
               + (f"; das vorhandene Netz hat noch {rest} {'tet4' if soll == 'tet10' else 'tet10'}"
                  if rest else ""))
        w.refresh_all()
    maske.angewendet.connect(uebernehmen)
    return w.maske_erzeugen(maske)


# --------------------------------------------------------------------------
# Elementuebersicht
# --------------------------------------------------------------------------
def _farbfeld(farbe: str) -> QtGui.QIcon:
    pm = QtGui.QPixmap(12, 12)
    pm.fill(QtGui.QColor(farbe))
    return QtGui.QIcon(pm)


class Elementuebersicht(msk.Maske):
    """Tabelle Typ | Ansatz | Anzahl | Anteil | Koerper, je Typ aufklappbar
    nach Koerpern. Klick auf eine Zeile zeigt nur diese Elemente."""

    def __init__(self, model, parent=None, zusatz=None):
        self._model = model
        self.z = ea.zaehlung(model)
        F = msk.Feld
        from ..zahlen import zahl_text
        felder = [F("gesamt", "Elemente", "info", zahl_text(self.z["gesamt"])),
                  F("fingerabdruck", "Netz-Fingerabdruck", "info", "–",
                    hinweis="Hash über Typ und Knoten jedes Elements - derselbe steht in der "
                            "Kennung der Ergebnisdatei; Ergebnisse werden nur zu einem Netz mit "
                            "gleichem Fingerabdruck geladen")]
        super().__init__(
            TITEL_UEBERSICHT, felder, parent, knopf="Im Bild nach Elementtyp färben",
            hinweis="Welche Elemente das Netz hat, je Typ und je Körper. Klick auf eine Zeile "
                    "zeigt nur diese Elemente („Alles zeigen“ holt den Rest zurück).",
            zusatz=zusatz)
        self.baum = QtWidgets.QTreeWidget(self)
        self.baum.setObjectName("elementuebersicht")
        self.baum.setColumnCount(len(SPALTEN))
        self.baum.setHeaderLabels(SPALTEN)
        self.baum.setRootIsDecorated(True)
        self.baum.setUniformRowHeights(True)
        for zeile in ea.zeilen(model, self.z):
            je = zeile["koerper"]
            koerper = (", ".join(je) if len(je) <= 3 else f"{len(je)} Körper")
            it = QtWidgets.QTreeWidgetItem([zeile["name"], zeile["ansatz"], zahl_text(zeile["anzahl"]),
                                            zeile["anteil"], koerper])
            it.setIcon(0, _farbfeld(ea.farbe(zeile["typ"])))
            it.setData(0, ROLLE, (zeile["typ"], None))
            it.setToolTip(0, f"{zeile['typ']}: "
                          + str(getattr(EL.ELEMENTE.get(zeile["typ"]), "name", zeile["typ"])))
            for name, n in je.items():
                kind = QtWidgets.QTreeWidgetItem([name, "", zahl_text(n),
                                                  ea.anteil_text(n, self.z["gesamt"]), ""])
                kind.setData(0, ROLLE, (zeile["typ"], name))
                it.addChild(kind)
            self.baum.addTopLevelItem(it)
        for k in range(len(SPALTEN)):
            self.baum.resizeColumnToContents(k)
        self.baum.setMinimumHeight(min(60 + 22 * max(1, self.baum.topLevelItemCount()), 260))
        self.inhalt_einfuegen(self.baum, 1)

    def elemente(self, typ: str, koerper=None) -> list:
        """Die Elementnummern einer Zeile."""
        if koerper is None:
            return list(self.z["elemente"].get(typ, []))
        return [i for i in self.z["elemente"].get(typ, [])
                if (str(getattr(self._model.elements[i], "group", "") or "") or ea.OHNE_KOERPER) == koerper]


def maske_elementuebersicht(w):
    """Netz → Elementübersicht… (rechte Maske)."""
    m = w.model
    if not m.elements:
        return w.error("Kein Netz vorhanden - erst vernetzen (Netz → Vernetzen)")
    halter = {}

    def fingerabdruck():
        halter["m"].setzen("fingerabdruck", ea.fingerabdruck(m))

    def aus():
        faerbung_setzen(w, False)
    maske = Elementuebersicht(m, zusatz=[("Fingerabdruck", fingerabdruck), ("Färbung aus", aus),
                                         ("Alles zeigen", w.alles_zeigen)])
    halter["m"] = maske
    # Der Fingerabdruck kostet am Drehlager Sekunden (ein Hash ueber 1,8 Mio.
    # Elemente) - bis 300 000 Elemente gleich, darueber auf Knopfdruck
    if len(m.elements) <= FINGERABDRUCK_SOFORT:
        fingerabdruck()
    else:
        maske.setzen("fingerabdruck", "– (Knopf „Fingerabdruck“)")
    maske.angewendet.connect(lambda _w: faerbung_setzen(w, True))

    def zeile_geklickt(it, _spalte=0):
        d = it.data(0, ROLLE)
        if not d:
            return
        typ, koerper = d
        els = maske.elemente(typ, koerper)
        if not els:
            return
        w._auswahl_leeren()
        w.sel_elemente = els
        w.nur_auswahl_zeigen()
    maske.baum.itemClicked.connect(zeile_geklickt)
    return w.maske_erzeugen(maske)


# --------------------------------------------------------------------------
# Faerbung der Ansicht
# --------------------------------------------------------------------------
def faerbung_setzen(w, an: bool) -> None:
    """Die Ansicht nach Elementtyp faerben (an) oder nicht. Eine gezeigte
    Ergebnisfaerbung wird dafuer ausgeblendet, nicht verworfen (Schalter
    „Ergebnisse zeigen“); die Netzqualitaet faerbt nicht zugleich."""
    w.elementtyp_faerben = bool(an)
    if an:
        w.netzguete_feld = None
        a = getattr(w, "act_ergebnisse", None)
        if a is not None and a.isChecked() and w.current_result() is not None:
            a.setChecked(False)
        z = ea.typen_zaehlen(w.model)
        w.info("Nach Elementtyp gefärbt: " + ", ".join(
            f"{ea.kurzname(t)} {n}" for t, n in z["typen"].items()))
    else:
        w.info("Färbung nach Elementtyp aus")
    w.redraw()


def faerbung_fuer_ansicht(w, m):
    """Die Faerbung fuer _aufbauen - oder None, wenn sie aus ist. Einmal je
    Modellstand gerechnet (am Drehlager eine Schleife ueber 1,8 Mio.
    Elemente)."""
    if not getattr(w, "elementtyp_faerben", False) or not m.elements:
        return None
    stand = (id(m), len(m.elements), m.nn)
    if getattr(w, "_typfarben_stand", None) != stand:
        w._typfarben = ea.faerbung(m)
        w._typfarben_stand = stand
    return w._typfarben


def faerbung_zeichnen(w, netz, eidx, f: dict, nm: str, breite: int, darstellung: dict) -> None:
    """Ein Teilnetz nach Elementtyp gefaerbt, mit Legende (Typ und Anzahl)."""
    farbig = netz.copy()
    farbig.cell_data["Elementtyp"] = np.asarray(f["codes"], float)[eidx]
    n = len(f["farben"])
    w.plotter.add_mesh(farbig, scalars="Elementtyp", cmap=list(f["farben"]), n_colors=max(1, n),
                       clim=[-0.5, n - 0.5], annotations=dict(f["namen"]),
                       scalar_bar_args=dict(w._farbskala(), title="Elementtyp", n_labels=0,
                                            fmt="%.0f"),
                       name=f"model_{nm}", **dict({"line_width": breite}, **darstellung))


# --------------------------------------------------------------------------
# Rueckfrage beim Import
# --------------------------------------------------------------------------
def elementwahl_nach_import(w, m, path: str) -> str:
    """Nach dem Import in ein neues Modell: die Elementwahl festlegen.

    Gibt die Datei ein Elementfeld anders vor als Statik3D (heute nur die
    RFEM-6-Datei: die Elementform der Flaechen in mesh.xml), fragt das
    Programm - abschaltbar wie jede Rueckfrage (``w._fragen_knoepfe``).
    Was die Datei nicht vorgibt, bekommt die Statik3D-Vorgabe. Rueckgabe die
    Protokollzeile. Statik3D-Dateien (.json) behalten ihre eigene Wahl."""
    ext = os.path.splitext(str(path))[1].lower()
    if ext == ".json":
        return ""
    aus_datei: dict = {}
    datei = "Datei"
    if ext == ".rf6":
        from ..importers import rfem6_db
        aus_datei = rfem6_db.mesh_info(path)
        datei = "RFEM-Datei"
    abw = ea.abweichungen(aus_datei)
    datei_waehlen = False
    if abw:
        # Enter und Esc nehmen die Statik3D-Vorgabe (Anwender 23.09.2026:
        # „standard sollte tet10 und vq83 sein“)
        datei_waehlen = w._fragen_knoepfe("Elementwahl beim Import", ea.frage_text(datei, abw),
                                          ja="Datei-Vorgabe", nein="Statik3D-Vorgabe",
                                          vorgabe="nein")
    m.netz, zeile = ea.nach_import(m.netz, aus_datei, datei_waehlen, datei)
    if m.elements:
        z = ea.typen_zaehlen(m)
        zeile += (" - das eingelesene Netz bleibt, wie es ist: "
                  + ", ".join(f"{n} {ea.kurzname(t)}" for t, n in z["typen"].items()))
    return zeile
