"""
Maske „Ermüdungslasten (Lastkollektiv)“ im rechten Bereich.

Bis zum 24.09.2026 gab es fuer Ermuedungslasten nur einen modalen Dialog,
der neu anlegen, aber nicht bearbeiten konnte, das Zaehlverfahren roh
(„spanne/rainflow/reservoir“) nannte und das Wort Palmgren-Miner nicht
kannte. Der Anwender fragte, wo Palmgren-Miner sei und ob man nicht jedem
Lastfall eine Lastspielzahl zuordnen koenne. Die Rechnung konnte das laengst
(ec3/fatigue.py summiert D = Σ n/N ueber alle Ermuedungslasten und Stufen am
selben Ort), nur die Oberflaeche zeigte es nicht.

Darum steht hier **das ganze Kollektiv als Tabelle**: jede Zeile ist eine
Ermuedungslast (FatigueLoad, unveraendert), darunter wird die gewaehlte
Zeile bearbeitet. „Zeile je Lastfall…“ legt je Lastfall eine Zeile gegen den
Nullzustand an - damit ist „jedem Lastfall eine Lastspielzahl“ ein Klick.

Die Maske schreibt nie selbst am Rueckgaengig-Stapel vorbei: jede Aenderung
laeuft ueber ``aendern(was, fn)``; das Hauptfenster setzt dort merken()
davor und refresh_all() dahinter.
"""
from __future__ import annotations

import math
import re
import weakref

from PySide6 import QtCore, QtGui, QtWidgets

from ..model import FatigueLoad, Model, ZAEHLVERFAHREN_TEXT
from . import masken as msk

TITEL = "Ermüdungslasten (Lastkollektiv)"

MINER_TEXT = ("Schadenssumme linear nach Palmgren-Miner (EN 1993-1-9, Anhang A): "
              "D = Σ nᵢ / Nᵢ über alle Zeilen und Stufen am selben Ort; Nachweis D ≤ 1. "
              "Jede Zeile ist ein Beitrag zum Kollektiv.")

REIHENFOLGE_TEXT = ("↑ / ↓ ordnen nur die Anzeige. Die Reihenfolge der Zeilen ändert die "
                    "Schadenssumme nicht.")

ART_ZWEI = "zwei"
ART_VERLAUF = "verlauf"
ARTEN = [(ART_ZWEI, "Zwei Zustände (Spannungsschwingbreite zwischen oberem und unterem Zustand)"),
         (ART_VERLAUF, "Zeitverlauf (Folge von Lastfällen, gezählt)")]

ZAEHLUNG_HINWEIS = (
    "Größte Spanne je Durchlauf: eine Stufe mit der Schwingbreite Maximum minus Minimum über "
    "alle Zustände, ein Spiel je Durchlauf. So bildet RFEM die Ermüdungsschwingbreite einer "
    "Ergebniskombination, und so kommen die Lasten aus dem RFEM-Import; die Reihenfolge spielt "
    "keine Rolle.\n"
    "Rainflow- und Reservoir-Zählung (EN 1993-1-9, Anhang A): für eine echte Zeitfolge "
    "(Überfahrt, Öffnungsvorgang, Betriebszyklus) - die Zwischenstufen tragen eigene, kleinere "
    "Spiele bei. Den Verlauf am größten Wert beginnen und enden lassen, dann zählen beide "
    "nur ganze Spiele.")

SPALTEN = ["Name", "Art", "Oberer Zustand / Verlauf", "Unterer Zustand", "Lastspiele n",
           "Zählverfahren", "Schwingbeiwert"]

ROT = "#c0392b"
GRUEN = "#2e7d32"

#: Leerzeichen, die beim Lesen einer Zahl wegfallen: normales, schmales
#: geschuetztes (U+202F), schmales (U+2009), geschuetztes (U+00A0)
_LEER = (" ", " ", " ", " ", "_")


# --------------------------------------------------------------------------
# Zahlen: nie wissenschaftlich (Anwender, 12.09.2026: „2e+06“ ist unlesbar)
# --------------------------------------------------------------------------
# Eine Schreibweise fuer Maske, Register, Baum und Bericht: im Modell.
from ..model import lastspiele_text  # noqa: E402,F401


def _ohne_leer(text) -> str:
    t = str(text or "")
    for z in _LEER:
        t = t.replace(z, "")
    return t


def zahl_lesen(text) -> float:
    """Eine Zahl lesen: Leerzeichen fallen weg, Komma ist Dezimalzeichen.
    ValueError, wenn es keine Zahl ist."""
    t = _ohne_leer(text).replace(",", ".")
    if not t:
        raise ValueError("leer")
    return float(t)


class TausenderpunktFehler(ValueError):
    """„500.000“ im Lastspielfeld: deutsch geschriebene Tausenderpunkte."""


#: „500.000“, „2.000.000“: Punkte als Tausendertrennung (ohne Komma, ohne e)
_TAUSENDERPUNKT = re.compile(r"^[+-]?\d{1,3}(\.\d{3})+$")


def lastspiele_lesen(text) -> float:
    """Eingabe lesen: „2 000 000“, „2000000“, „2e6“, „1,5e5“. ValueError, wenn
    es keine Zahl ist.

    „500.000“ wird abgewiesen statt als 500 gelesen: im Deutschen ist der
    Punkt die uebliche Tausendertrennung, float() naehme ihn als
    Dezimalpunkt - die Zeile zaehlte dann 1000-mal zu wenig Spiele (unsichere
    Seite), „2.000.000“ dagegen waere ein Fehler. Beides gleich behandeln.
    """
    if _TAUSENDERPUNKT.match(_ohne_leer(text)):
        raise TausenderpunktFehler("Tausender bitte mit Leerzeichen schreiben, z. B. 500 000 "
                                   "(der Punkt ist mehrdeutig)")
    return zahl_lesen(text)


def globale_lastspielzahl(model) -> float:
    """Wie ec3.fatigue._spiele: 0, wenn nichts eingestellt ist."""
    return float(getattr(model.design, "ermuedung_lastspiele", 2e6) or 0.0)


# --------------------------------------------------------------------------
# Texte je Zeile (Tabelle der Maske, Register Lastfaelle, Modellbaum)
# --------------------------------------------------------------------------
def art_text(f) -> str:
    return "Verlauf" if f.folge else "zwei Zustände"


def zustand_text(f, laenge: int = 60) -> str:
    if not f.folge:
        return f.case_max or ""
    t = ", ".join(f.folge)
    if len(t) <= laenge:
        return t
    return t[:laenge].rsplit(",", 1)[0] + f", … ({len(f.folge)} Glieder)"


def unten_text(f) -> str:
    return "" if f.folge else (f.case_min or "Nullzustand")


def _eigenes_n(f):
    """Eigene Lastspielzahl der Zeile (Verlauf: Durchlaeufe); None = global
    oder keine Zeile."""
    if f is None:
        return None
    eigen = f.wiederholungen if f.folge else f.cycles
    return None if eigen is None else float(eigen or 0.0)


def n_text(f, model) -> str:
    eigen = f.wiederholungen if f.folge else f.cycles
    if eigen is None:
        return f"global ({lastspiele_text(globale_lastspielzahl(model))})"
    if float(eigen or 0.0) == 0.0:
        return "0 (unwirksam)"
    return lastspiele_text(eigen)


def zaehlung_text(f) -> str:
    if not f.folge:
        return "–"
    z = getattr(f, "zaehlung", "spanne") or "spanne"
    return ZAEHLVERFAHREN_TEXT.get(z, z)


def kurztext(f, model) -> str:
    """Eine Zeile fuer Modellbaum und Register: was, gegen was, wie oft."""
    if f.folge:
        return f"Verlauf {zustand_text(f, 30)}, n = {n_text(f, model)}"
    return f"{f.case_max} gegen {f.case_min or 'Nullzustand'}, n = {n_text(f, model)}"


# --------------------------------------------------------------------------
# Pruefen und Schreiben (ohne Qt - auch fuer Tests)
# --------------------------------------------------------------------------
def pruefen(model, w: dict):
    """Die Werte der Maske pruefen. Rueckgabe (FatigueLoad, "") oder (None, Meldung).

    Geprueft wird **vor** dem Schreiben; bei einem Fehler aendert sich nichts.
    Der alte Dialog ueberschrieb einen doppelten Namen still
    (Model.add_fatigue_load) und nahm n <= 0 und einen Faktor <= 0 an.
    """
    name = str(w.get("name") or "").strip()
    alt = w.get("alt") or None
    if alt is not None and alt not in model.fatigue_loads:
        # Die Zeile im Editor ist nach Rueckgaengig oder Loeschen weg. Bis zum
        # 24.09.2026 legte „Übernehmen“ sie dann still neu an - nach dem
        # Rueckgaengig einer Umbenennung stand dieselbe Last zweimal im
        # Kollektiv, und D verdoppelte sich
        return None, (f"Die Zeile „{alt}“ gibt es nicht mehr (Rückgängig oder gelöscht) – "
                      "nichts übernommen. „Neue Zeile“ legt eine neue an.")
    if not name:
        return None, "Der Name fehlt – jede Zeile braucht einen eindeutigen Namen."
    if name != alt and name in model.fatigue_loads:
        return None, f"Ermüdungslast „{name}“ gibt es schon – bitte einen anderen Namen wählen."
    taugt = set(model.ermuedungszustaende())

    def bekannt(x):
        return x in model.load_cases or x in model.combinations

    verlauf = w.get("art") == ART_VERLAUF
    folge, oben, unten = [], "", None
    if verlauf:
        folge = [str(x) for x in (w.get("folge") or []) if str(x).strip()]
        if len(folge) < 2:
            return None, ("Ein Verlauf braucht mindestens zwei Lastfälle – sonst gibt es nichts "
                          "zu zählen.")
        unbekannt = [x for x in dict.fromkeys(folge) if not bekannt(x)]
        if unbekannt:
            return None, "Der Verlauf nennt Lastfälle, die es nicht gibt: " + ", ".join(unbekannt)
        # Eine oder-verknuepfte Ergebniskombination hat kein Einzelergebnis
        # und fehlte sonst im Nachweis (Befund B066, wie bisher im Dialog)
        oder = [x for x in dict.fromkeys(folge) if x not in taugt]
        if oder:
            return None, ("Der Verlauf nennt oder-verknüpfte Ergebniskombinationen: "
                          + ", ".join(f"{x} ({len(model.combinations[x].alternativen)} Alternativen)"
                                      for x in oder)
                          + ". Sie haben kein Einzelergebnis und fehlten sonst im Ermüdungsnachweis. "
                            "Stattdessen die Lastfälle ihrer Alternativen in den Verlauf schreiben.")
    else:
        oben = str(w.get("oben") or "")
        unten = w.get("unten") or None
        if not oben:
            return None, "Kein oberer Zustand gewählt – einen Lastfall oder eine Kombination wählen."
        for rolle, x in (("obere", oben), ("untere", unten)):
            if x and not bekannt(x):
                return None, f"Der {rolle} Zustand „{x}“ ist weder Lastfall noch Kombination."
            if x and x not in taugt:
                return None, (f"Der {rolle} Zustand „{x}“ ist eine oder-verknüpfte "
                              "Ergebniskombination – sie hat kein Einzelergebnis.")
    n = None
    if not w.get("global"):
        wort = "Die Zahl der Durchläufe" if verlauf else "Die Lastspielzahl"
        try:
            n = lastspiele_lesen(w.get("n"))
        except TausenderpunktFehler as ex:
            return None, f"{wort} „{w.get('n')}“: {ex}."
        except ValueError:
            return None, f"{wort} „{w.get('n')}“ ist keine Zahl (z. B. 2 000 000 oder 2e6)."
        # 0 heisst im Modell „unwirksam“: so legt der RFEM-Import Sammlungen
        # an, damit ihre Ereignisse nicht doppelt zaehlen (rfem6_db). Eine
        # Zeile, die schon 0 traegt, bleibt darum bearbeitbar (umbenennen,
        # Beiwert); vorher wies die Maske sie ab und riet zum globalen Haken,
        # der die Sammlung wirksam machte. Neu eintragen laesst sich 0 nicht
        # (Entwurf 24.09.: n <= 0 ist ein Fehler).
        if n == 0 and _eigenes_n(model.fatigue_loads.get(alt)) == 0.0:
            pass
        elif not math.isfinite(n) or n <= 0:
            return None, (f"{wort} muss größer als null sein (eingegeben: {w.get('n')}) – "
                          "oder den Haken „globale Lastspielzahl“ setzen.")
    try:
        faktor = zahl_lesen(w.get("faktor"))
    except ValueError:
        return None, f"Der Schwingbeiwert „{w.get('faktor')}“ ist keine Zahl."
    if not math.isfinite(faktor) or faktor <= 0:
        return None, "Der Schwingbeiwert muss größer als null sein (1 = ohne Zuschlag)."
    if verlauf:
        # n nur als Wiederholungen: der Dialog schrieb es bis zum 24.09.2026
        # zusaetzlich nach cycles, das beim Verlauf niemand liest
        fl = FatigueLoad(name, "", None, cycles=None, factor=faktor, folge=folge,
                         wiederholungen=n, zaehlung=str(w.get("zaehlung") or "spanne"))
    else:
        fl = FatigueLoad(name, oben, unten, cycles=n, factor=faktor)
    return fl, ""


def schreiben(model, fl: FatigueLoad, alt: str = None) -> list:
    """Die Zeile ins Modell schreiben; ``alt`` ist ihr bisheriger Name.

    Eine umbenannte Zeile bleibt an ihrer Stelle, und die Anschluesse, die
    sie beim alten Namen nennen (Joint.ermuedung), nennen sie beim neuen -
    sonst fiele sie dort still aus dem Nachweis. Eine leere Liste am
    Anschluss heisst „alle“ und bleibt leer. Rueckgabe: die nachgezogenen
    Anschluesse.
    """
    lasten = model.fatigue_loads
    if alt and alt in lasten:
        neu = {(fl.name if k == alt else k): (fl if k == alt else v) for k, v in lasten.items()}
        lasten.clear()
        lasten.update(neu)
    else:
        lasten[fl.name] = fl
    nachgezogen = []
    if alt and alt != fl.name:
        for j in getattr(model, "joints", {}).values():
            liste = list(getattr(j, "ermuedung", None) or [])
            if alt in liste:
                j.ermuedung = [fl.name if x == alt else x for x in liste]
                nachgezogen.append(j.name)
    return nachgezogen


def verschieben(model, name: str, schritt: int) -> bool:
    """Eine Zeile in der Reihenfolge verschieben (nur Anzeige - Palmgren-Miner
    summiert unabhaengig von der Reihenfolge)."""
    namen = list(model.fatigue_loads)
    if name not in namen:
        return False
    i = namen.index(name)
    j = i + int(schritt)
    if not 0 <= j < len(namen):
        return False
    namen[i], namen[j] = namen[j], namen[i]
    neu = {k: model.fatigue_loads[k] for k in namen}
    model.fatigue_loads.clear()
    model.fatigue_loads.update(neu)
    return True


# --------------------------------------------------------------------------
class Ermuedungsmaske(msk.Maske):
    """Die Maske selbst: Tabelle des Kollektivs, darunter die gewaehlte Zeile.

    ``modell``     Aufruf, der das aktuelle Modell liefert (nach Rueckgaengig
                   ist es ein anderes Objekt)
    ``aendern``    aendern(was, fn): fn() schreibt ins Modell; das Fenster
                   setzt merken() davor und refresh_all() dahinter
    ``protokoll``  protokoll(text): Zeile ins Protokoll
    ``auswahl``    diese Zeile beim Oeffnen bearbeiten
    ``neu``        mit einer neuen Zeile oeffnen
    """

    #: lange Maske: bekommt im rechten Bereich den groesseren Teil der Hoehe
    dehnung = 1

    def __init__(self, modell, aendern=None, protokoll=None, auswahl: str = None,
                 neu: bool = False, parent=None):
        self._modell = modell if callable(modell) else (lambda m=modell: m)
        self._aendern = aendern or (lambda _was, fn: fn())
        self._protokoll = protokoll or (lambda _t: None)
        #: Name der Zeile im Editor im Modell (None = neue Zeile)
        self._alt = None
        #: das Modellobjekt beim letzten Fuellen (schwach gehalten - eine
        #: Sicherung des Drehlagers ist 1,4 GB). Rueckgaengig und Wiederholen
        #: tauschen das Objekt aus; daran erkennt tabelle_fuellen, dass der
        #: Editor neu laden muss
        self._modell_ref = None
        super().__init__(TITEL, [], parent=parent, knopf="Übernehmen",
                         hinweis="Zeile in der Tabelle wählen, unten ändern und „Übernehmen“ – "
                                 "die Maske bleibt offen. Rückgängig nimmt jede Übernahme zurück.")
        self._aufbauen()
        m = self.modell()
        self.tabelle_fuellen()
        if neu or not m.fatigue_loads:
            self.neue_zeile()
        elif auswahl and auswahl in m.fatigue_loads:
            self.zeile_waehlen(auswahl)
        else:
            self.zeile_waehlen(next(iter(m.fatigue_loads)))

    def modell(self) -> Model:
        return self._modell()

    # -- Aufbau ------------------------------------------------------------
    def _aufbauen(self):
        inhalt = QtWidgets.QWidget(self)
        v = QtWidgets.QVBoxLayout(inhalt)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        self.lbl_miner = QtWidgets.QLabel(MINER_TEXT, inhalt)
        self.lbl_miner.setObjectName("maskeninfo")
        self.lbl_miner.setWordWrap(True)
        v.addWidget(self.lbl_miner)

        t = self.tabelle = QtWidgets.QTableWidget(0, len(SPALTEN), inhalt)
        t.setHorizontalHeaderLabels(SPALTEN)
        t.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        t.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        t.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        t.setMinimumHeight(130)
        t.currentCellChanged.connect(self._zeile_gewechselt)
        v.addWidget(t, 1)

        zeile = QtWidgets.QHBoxLayout()
        self.btn_neu = QtWidgets.QPushButton("Neue Zeile", inhalt)
        self.btn_neu.clicked.connect(self.neue_zeile)
        self.btn_je_lastfall = QtWidgets.QPushButton("Zeile je Lastfall…", inhalt)
        self.btn_je_lastfall.setToolTip("Je gewähltem Lastfall eine Zeile: oberer Zustand = "
                                        "Lastfall, unterer = Nullzustand, n = global – danach "
                                        "je Zeile die eigene Lastspielzahl eintragen.")
        self.btn_je_lastfall.clicked.connect(self._je_lastfall_zeigen)
        self.btn_loeschen = QtWidgets.QPushButton("Zeile löschen", inhalt)
        self.btn_loeschen.clicked.connect(self.zeile_loeschen)
        self.btn_hoch = QtWidgets.QPushButton("↑", inhalt)
        self.btn_hoch.setFixedWidth(28)
        self.btn_hoch.clicked.connect(self.zeile_hoch)
        self.btn_runter = QtWidgets.QPushButton("↓", inhalt)
        self.btn_runter.setFixedWidth(28)
        self.btn_runter.clicked.connect(self.zeile_runter)
        for b in (self.btn_neu, self.btn_je_lastfall, self.btn_loeschen, self.btn_hoch,
                  self.btn_runter):
            zeile.addWidget(b)
        zeile.addStretch(1)
        v.addLayout(zeile)
        self.lbl_reihenfolge = QtWidgets.QLabel(REIHENFOLGE_TEXT, inhalt)
        self.lbl_reihenfolge.setObjectName("maskenhinweis")
        self.lbl_reihenfolge.setWordWrap(True)
        v.addWidget(self.lbl_reihenfolge)

        # „Zeile je Lastfall…“: Auswahl in der Maske statt eines weiteren Dialogs
        p = self.je_lastfall_panel = QtWidgets.QFrame(inhalt)
        p.setFrameShape(QtWidgets.QFrame.StyledPanel)
        pl = QtWidgets.QVBoxLayout(p)
        pl.setContentsMargins(6, 6, 6, 6)
        hin = QtWidgets.QLabel("Je gewähltem Zustand eine Zeile: oben = Zustand, unten = "
                               "Nullzustand, n = global. Vorhandene Zeilen „Zustand gegen "
                               "Nullzustand“ bleiben, wie sie sind.", p)
        hin.setWordWrap(True)
        hin.setObjectName("maskenhinweis")
        pl.addWidget(hin)
        self.je_lastfall_liste = QtWidgets.QListWidget(p)
        self.je_lastfall_liste.setMaximumHeight(150)
        pl.addWidget(self.je_lastfall_liste)
        pz = QtWidgets.QHBoxLayout()
        self.btn_je_lastfall_alle = QtWidgets.QPushButton("alle", p)
        self.btn_je_lastfall_alle.clicked.connect(lambda: self._je_lastfall_alle(True))
        self.btn_je_lastfall_anlegen = QtWidgets.QPushButton("Zeilen anlegen", p)
        self.btn_je_lastfall_anlegen.clicked.connect(lambda: self.zeilen_je_lastfall())
        zu = QtWidgets.QPushButton("Abbrechen", p)
        zu.clicked.connect(p.hide)
        for b in (self.btn_je_lastfall_alle, self.btn_je_lastfall_anlegen, zu):
            pz.addWidget(b)
        pz.addStretch(1)
        pl.addLayout(pz)
        p.hide()
        v.addWidget(p)

        # -- die gewaehlte Zeile --------------------------------------------
        g = self.gruppe = QtWidgets.QGroupBox("Gewählte Zeile", inhalt)
        form = QtWidgets.QFormLayout(g)
        form.setContentsMargins(6, 6, 6, 6)
        self.name = QtWidgets.QLineEdit(g)
        self.name.returnPressed.connect(self.anwenden)
        form.addRow("Name", self.name)
        self.art = QtWidgets.QComboBox(g)
        for wert, text in ARTEN:
            self.art.addItem(text, wert)
        self.art.currentIndexChanged.connect(self._art_umschalten)
        form.addRow("Art", self.art)

        self.block_zwei = QtWidgets.QWidget(g)
        fz = QtWidgets.QFormLayout(self.block_zwei)
        fz.setContentsMargins(0, 0, 0, 0)
        self.oben = QtWidgets.QComboBox(self.block_zwei)
        self.unten = QtWidgets.QComboBox(self.block_zwei)
        fz.addRow("Oberer Zustand", self.oben)
        fz.addRow("Unterer Zustand", self.unten)
        form.addRow(self.block_zwei)

        self.block_verlauf = QtWidgets.QWidget(g)
        gv = QtWidgets.QGridLayout(self.block_verlauf)
        gv.setContentsMargins(0, 0, 0, 0)
        gv.addWidget(QtWidgets.QLabel("verfügbare Zustände", self.block_verlauf), 0, 0)
        gv.addWidget(QtWidgets.QLabel("Verlauf (zeitliche Folge)", self.block_verlauf), 0, 2)
        self.verfuegbar = QtWidgets.QListWidget(self.block_verlauf)
        self.verfuegbar.setToolTip("Lastfälle und Kombinationen ohne Alternativen – "
                                   "Doppelklick fügt an")
        self.verfuegbar.itemDoubleClicked.connect(self.anfuegen)
        self.verlauf = QtWidgets.QListWidget(self.block_verlauf)
        self.verlauf.setToolTip("Doppelklick entfernt; ↑/↓ ändern die Reihenfolge")
        self.verlauf.itemDoubleClicked.connect(self.entfernen)
        for liste in (self.verfuegbar, self.verlauf):
            liste.setMaximumHeight(140)
        gv.addWidget(self.verfuegbar, 1, 0)
        gv.addWidget(self.verlauf, 1, 2)
        spalte = QtWidgets.QVBoxLayout()
        self.btn_anfuegen = QtWidgets.QPushButton("anfügen →", self.block_verlauf)
        self.btn_anfuegen.clicked.connect(lambda: self.anfuegen())
        self.btn_entfernen = QtWidgets.QPushButton("← entfernen", self.block_verlauf)
        self.btn_entfernen.clicked.connect(lambda: self.entfernen())
        self.btn_v_hoch = QtWidgets.QPushButton("↑", self.block_verlauf)
        self.btn_v_hoch.clicked.connect(self.verlauf_hoch)
        self.btn_v_runter = QtWidgets.QPushButton("↓", self.block_verlauf)
        self.btn_v_runter.clicked.connect(self.verlauf_runter)
        for b in (self.btn_anfuegen, self.btn_entfernen, self.btn_v_hoch, self.btn_v_runter):
            spalte.addWidget(b)
        spalte.addStretch(1)
        gv.addLayout(spalte, 1, 1)
        self.folge_text = QtWidgets.QLineEdit(self.block_verlauf)
        self.folge_text.setPlaceholderText("oder als Komma-Liste, z. B. LF0, LF1, LF2, LF1, LF0")
        self.folge_text.textEdited.connect(self._folge_aus_text)
        gv.addWidget(self.folge_text, 2, 0, 1, 3)
        self.lbl_folge = QtWidgets.QLabel("", self.block_verlauf)
        self.lbl_folge.setObjectName("maskenhinweis")
        self.lbl_folge.setWordWrap(True)
        gv.addWidget(self.lbl_folge, 3, 0, 1, 3)
        self.zaehlung = QtWidgets.QComboBox(self.block_verlauf)
        for wert, text in ZAEHLVERFAHREN_TEXT.items():
            self.zaehlung.addItem(text, wert)
        self.zaehlung.setToolTip(ZAEHLUNG_HINWEIS)
        gv.addWidget(QtWidgets.QLabel("Zählverfahren", self.block_verlauf), 4, 0)
        gv.addWidget(self.zaehlung, 5, 0, 1, 3)
        form.addRow(self.block_verlauf)

        self.global_n = QtWidgets.QCheckBox(g)
        self.global_n.toggled.connect(lambda ein: self.n.setEnabled(not ein))
        form.addRow(self.global_n)
        self.lbl_n = QtWidgets.QLabel("Lastspiele n", g)
        self.n = QtWidgets.QLineEdit(g)
        self.n.setToolTip("z. B. 2 000 000, 2000000 oder 2e6")
        self.n.returnPressed.connect(self.anwenden)
        form.addRow(self.lbl_n, self.n)
        self.lbl_faktor = QtWidgets.QLabel("Schwingbeiwert / dynamischer Faktor", g)
        self.faktor = QtWidgets.QLineEdit(g)
        self.faktor.setToolTip("Faktor auf die Spannungsschwingbreite dieser Zeile, "
                               "z. B. Schwingbeiwert φ; 1 = ohne Zuschlag")
        self.faktor.returnPressed.connect(self.anwenden)
        form.addRow(self.lbl_faktor, self.faktor)
        v.addWidget(g)

        self.lbl_meldung = QtWidgets.QLabel("", inhalt)
        self.lbl_meldung.setWordWrap(True)
        v.addWidget(self.lbl_meldung)
        # In die rollbare Mitte des gemeinsamen Maskenrahmens (24.09.2026) -
        # frueher vor die Hinweiszeile am Ende der Maske, die steht jetzt oben
        self.inhalt_einfuegen(inhalt, 1)

    # -- Tabelle -----------------------------------------------------------
    def tabelle_fuellen(self):
        """Tabelle und Auswahllisten aus dem Modell.

        Der Editor bleibt, wie er ist (ungespeicherte Eingaben ueberleben
        etwa einen umbenannten Lastfall) - ausser seine Zeile ist weg oder das
        Modell wurde getauscht (Rueckgaengig/Wiederholen), siehe
        _editor_nachziehen.
        """
        m = self.modell()
        getauscht = self._modell_ref is not None and self._modell_ref() is not m
        try:
            self._modell_ref = weakref.ref(m)
        except TypeError:           # ein Modell ohne weakref-Stelle: nie „getauscht“
            self._modell_ref = None
        t = self.tabelle
        # Stelle der Editorzeile vor dem Fuellen: verschwindet sie (Loeschen
        # von aussen, Rueckgaengig einer Umbenennung), zeigt der Editor die
        # Zeile an derselben Stelle - wie „Zeile löschen“ in der Maske
        vorher = [t.item(r, 0).text() if t.item(r, 0) else "" for r in range(t.rowCount())]
        stelle = vorher.index(self._alt) if self._alt in vorher else 0
        gesperrt = t.blockSignals(True)
        try:
            t.setRowCount(0)
            for r, f in enumerate(m.fatigue_loads.values()):
                t.insertRow(r)
                zellen = [f.name, art_text(f), zustand_text(f), unten_text(f), n_text(f, m),
                          zaehlung_text(f), lastspiele_text(f.factor)]
                for c, text in enumerate(zellen):
                    it = QtWidgets.QTableWidgetItem(text)
                    if c == 2 and f.folge:
                        it.setToolTip(", ".join(f.folge))
                    t.setItem(r, c, it)
            self._tabelle_markieren(self._alt)
        finally:
            t.blockSignals(gesperrt)
        self._zustaende_fuellen()
        self._global_beschriften()
        # Auch nach eigenen Aenderungen (refresh_all im Fenster): danach setzt
        # die aufrufende Methode den Editor ohnehin selbst
        self._editor_nachziehen(getauscht, stelle)

    def _editor_nachziehen(self, getauscht: bool, stelle: int = 0):
        """Den Editor nach einer Aenderung von aussen (Rueckgaengig, Loeschen
        im Baum oder Register) zum Modell passend machen.

        Bis zum 24.09.2026 blieb er stehen: nach dem Rueckgaengig einer
        Umbenennung zeigte er die zurueckgenommene Zeile weiter, und
        „Übernehmen“ legte sie als zweite Zeile an (D am Kragarm 47,6 → 111);
        nach dem Rueckgaengig einer Uebernahme schrieb die naechste den
        zurueckgenommenen Wert wieder hinein.

        Ist die Zeile weg, laedt er die Zeile an ihrer Stelle, unveraendert:
        ein „Übernehmen“ ohne weitere Eingabe aendert dann nichts. Eine neue
        Zeile stattdessen legte beim naechsten „Übernehmen“ wieder eine an.
        """
        alt = self._alt
        if alt is None:
            return                   # neue Zeile: „Übernehmen“ prueft den Namen
        namen = list(self.modell().fatigue_loads)
        if alt not in namen:
            text = f"Die Zeile „{alt}“ gibt es nicht mehr (Rückgängig oder gelöscht)"
            if namen:
                nachfolger = namen[min(stelle, len(namen) - 1)]
                self.zeile_waehlen(nachfolger)
                self.meldung(f"{text} – der Editor zeigt „{nachfolger}“.", fehler=True)
            else:
                self.neue_zeile(fokus=False)
                self.meldung(f"{text} – der Editor zeigt eine neue Zeile.", fehler=True)
        elif getauscht:
            self.zeile_waehlen(alt)
            self.meldung(f"Zeile „{alt}“ neu geladen (Rückgängig/Wiederholen).")

    def _tabelle_markieren(self, name):
        namen = list(self.modell().fatigue_loads)
        t = self.tabelle
        gesperrt = t.blockSignals(True)
        try:
            if name in namen:
                t.setCurrentCell(namen.index(name), 0)
                t.selectRow(namen.index(name))
            else:
                t.clearSelection()
                t.setCurrentCell(-1, -1)
        finally:
            t.blockSignals(gesperrt)

    def _zeile_gewechselt(self, zeile, _spalte, _vorher, _vspalte):
        it = self.tabelle.item(zeile, 0) if zeile >= 0 else None
        if it is not None:
            self.zeile_laden(it.text())

    def zeile_waehlen(self, name: str) -> bool:
        """Diese Zeile in der Tabelle waehlen und in den Editor laden."""
        if name not in self.modell().fatigue_loads:
            return False
        self._tabelle_markieren(name)
        self.zeile_laden(name)
        return True

    # -- Zustaende ---------------------------------------------------------
    def _zustaende(self) -> list:
        return list(self.modell().ermuedungszustaende())

    @staticmethod
    def _wahl_setzen(combo: QtWidgets.QComboBox, wert):
        """Auswahl nach Wert setzen; ein Wert, den es nicht (mehr) gibt, wird
        sichtbar angehaengt statt still ersetzt - „Übernehmen“ meldet ihn."""
        i = combo.findData(wert)
        if i < 0 and wert:
            combo.addItem(f"{wert} (nicht verfügbar)", wert)
            i = combo.count() - 1
        combo.setCurrentIndex(i)

    def _zustaende_fuellen(self):
        zust = self._zustaende()
        oben = self.oben.currentData() if self.oben.currentIndex() >= 0 else None
        unten = self.unten.currentData() if self.unten.currentIndex() >= 0 else ""
        for combo in (self.oben, self.unten):
            combo.blockSignals(True)
            combo.clear()
        self.unten.addItem("Nullzustand", "")
        for z in zust:
            self.oben.addItem(z, z)
            self.unten.addItem(z, z)
        if oben is not None:
            self._wahl_setzen(self.oben, oben)
        else:
            self.oben.setCurrentIndex(-1)
        self._wahl_setzen(self.unten, unten or "")
        for combo in (self.oben, self.unten):
            combo.blockSignals(False)
        self.verfuegbar.clear()
        self.verfuegbar.addItems(zust)
        if not self.je_lastfall_panel.isHidden():
            self._je_lastfall_fuellen()
        self._markieren()

    def _global_beschriften(self):
        g = lastspiele_text(globale_lastspielzahl(self.modell()))
        self.global_n.setText(f"globale Lastspielzahl (n = {g} aus Nachweise → Konfiguration)")

    # -- Editor ------------------------------------------------------------
    def zeile_laden(self, name: str):
        m = self.modell()
        f = m.fatigue_loads.get(name)
        if f is None:
            return
        self._alt = name
        self.name.setText(f.name)
        self.art.setCurrentIndex(self.art.findData(ART_VERLAUF if f.folge else ART_ZWEI))
        if f.folge:
            # Ein Verlauf fuehrt keine Zustaende (B067); die Auswahl steht nur
            # fuer den Fall bereit, dass jemand die Art umschaltet
            self.oben.setCurrentIndex(0 if self.oben.count() else -1)
            self.unten.setCurrentIndex(0)
        else:
            self._wahl_setzen(self.oben, f.case_max or "")
            self._wahl_setzen(self.unten, f.case_min or "")
        self._verlauf_setzen(list(f.folge))
        z = getattr(f, "zaehlung", "spanne") or "spanne"
        if self.zaehlung.findData(z) < 0:
            self.zaehlung.addItem(z, z)
        self.zaehlung.setCurrentIndex(self.zaehlung.findData(z))
        eigen = f.wiederholungen if f.folge else f.cycles
        self.global_n.setChecked(eigen is None)
        self.n.setEnabled(eigen is not None)
        self.n.setText(lastspiele_text(eigen if eigen is not None else globale_lastspielzahl(m)))
        self.faktor.setText(lastspiele_text(f.factor))
        self.gruppe.setTitle(f"Zeile „{f.name}“ bearbeiten")
        self.meldung("")
        if _eigenes_n(f) == 0.0:
            # Sammlung aus dem RFEM-Import: sagen, warum sie nicht zaehlt, und
            # dass der globale Haken sie wirksam machte
            self.meldung(f"{'Durchläufe' if f.folge else 'Lastspiele'} 0: diese Zeile ist "
                         "unwirksam (Sammlung aus dem Import) und zählt im Nachweis nicht mit. "
                         "Der Haken „globale Lastspielzahl“ machte sie wirksam.")
        self._art_umschalten()

    def neue_zeile(self, fokus: bool = True):
        """Den Editor fuer eine neue Zeile vorbereiten; ins Modell kommt sie erst
        mit „Übernehmen“. ``fokus=False`` beim Nachziehen von aussen: die
        Tastatur bleibt, wo der Anwender gerade ist."""
        m = self.modell()
        self._alt = None
        self._tabelle_markieren(None)
        self.name.setText(Model.naechster_name("E", m.fatigue_loads))
        self.art.setCurrentIndex(self.art.findData(ART_ZWEI))
        self.oben.setCurrentIndex(0 if self.oben.count() else -1)
        self.unten.setCurrentIndex(0)
        self._verlauf_setzen([])
        self.zaehlung.setCurrentIndex(self.zaehlung.findData("spanne"))
        self.global_n.setChecked(True)
        self.n.setEnabled(False)
        self.n.setText(lastspiele_text(globale_lastspielzahl(m)))
        self.faktor.setText("1")
        self.gruppe.setTitle("Neue Zeile")
        self.meldung("")
        self._art_umschalten()
        if fokus:
            self.name.setFocus()

    def _art_umschalten(self, *_):
        verlauf = self.art.currentData() == ART_VERLAUF
        self.block_zwei.setVisible(not verlauf)
        self.block_verlauf.setVisible(verlauf)
        self.lbl_n.setText("Durchläufe des Verlaufs" if verlauf else "Lastspiele n")

    def meldung(self, text: str, fehler: bool = False):
        self.lbl_meldung.setText(text)
        self.lbl_meldung.setStyleSheet(f"color: {ROT if fehler else GRUEN};" if text else "")

    # -- Verlauf: Liste und Komma-Text gekoppelt ---------------------------
    def folge(self) -> list:
        return [self.verlauf.item(i).text() for i in range(self.verlauf.count())]

    def _verlauf_setzen(self, namen: list, text_auch: bool = True):
        zeile = self.verlauf.currentRow()
        self.verlauf.clear()
        self.verlauf.addItems([str(x) for x in namen])
        if 0 <= zeile < self.verlauf.count():
            self.verlauf.setCurrentRow(zeile)
        if text_auch:
            self.folge_text.setText(", ".join(namen))
        self._markieren()

    def _folge_aus_text(self, text: str):
        """Getippt: die Liste folgt dem Text (textEdited kommt nur vom Anwender,
        darum schaukelt sich nichts auf)."""
        self._verlauf_setzen(msk.listeneintraege(text), text_auch=False)

    def _markieren(self):
        """Unbekannte Namen und oder-verknuepfte Kombinationen rot - in der
        Liste je Eintrag, im Textfeld als Rahmen, darunter mit Namen."""
        m = self.modell()
        taugt = set(m.ermuedungszustaende())
        namen = self.folge()
        unbekannt = [x for x in dict.fromkeys(namen)
                     if x not in m.load_cases and x not in m.combinations]
        oder = [x for x in dict.fromkeys(namen) if x not in taugt and x in m.combinations]
        for i in range(self.verlauf.count()):
            it = self.verlauf.item(i)
            schlecht = it.text() in unbekannt or it.text() in oder
            it.setForeground(QtGui.QBrush(QtGui.QColor(ROT)) if schlecht else QtGui.QBrush())
        fehler = bool(unbekannt or oder)
        self.folge_text.setProperty("fehler", fehler)
        self.folge_text.setStyleSheet(f"border: 1px solid {ROT}; color: {ROT};" if fehler else "")
        teile = [f"{len(namen)} Glieder"]
        if unbekannt:
            teile.append("unbekannt: " + ", ".join(unbekannt))
        if oder:
            teile.append("oder-verknüpft (kein Einzelergebnis): " + ", ".join(oder))
        self.lbl_folge.setText("; ".join(teile))
        self.lbl_folge.setStyleSheet(f"color: {ROT};" if fehler else "")

    def anfuegen(self, item=None):
        it = item if isinstance(item, QtWidgets.QListWidgetItem) else self.verfuegbar.currentItem()
        if it is None:
            return
        self._verlauf_setzen(self.folge() + [it.text()])
        self.verlauf.setCurrentRow(self.verlauf.count() - 1)

    def entfernen(self, item=None):
        zeile = (self.verlauf.row(item) if isinstance(item, QtWidgets.QListWidgetItem)
                 else self.verlauf.currentRow())
        namen = self.folge()
        if not 0 <= zeile < len(namen):
            return
        del namen[zeile]
        self._verlauf_setzen(namen)
        self.verlauf.setCurrentRow(min(zeile, self.verlauf.count() - 1))

    def _verlauf_schieben(self, schritt: int):
        zeile = self.verlauf.currentRow()
        namen = self.folge()
        ziel = zeile + schritt
        if not (0 <= zeile < len(namen) and 0 <= ziel < len(namen)):
            return
        namen[zeile], namen[ziel] = namen[ziel], namen[zeile]
        self._verlauf_setzen(namen)
        self.verlauf.setCurrentRow(ziel)

    def verlauf_hoch(self):
        self._verlauf_schieben(-1)

    def verlauf_runter(self):
        self._verlauf_schieben(+1)

    # -- Werte und Uebernehmen --------------------------------------------
    def werte(self) -> dict:
        return {"alt": self._alt,
                "name": self.name.text().strip(),
                "art": self.art.currentData(),
                "oben": self.oben.currentData() if self.oben.currentIndex() >= 0 else "",
                "unten": (self.unten.currentData() or None) if self.unten.currentIndex() >= 0 else None,
                "folge": self.folge(),
                "zaehlung": self.zaehlung.currentData() or "spanne",
                "global": self.global_n.isChecked(),
                "n": self.n.text(),
                "faktor": self.faktor.text(),
                "knoten": []}

    def anwenden(self):
        """„Übernehmen“: pruefen, dann ueber aendern() schreiben - bei einem
        Fehler bleibt das Modell, wie es war, und die Meldung steht hier."""
        m = self.modell()
        w = self.werte()
        fl, fehler = pruefen(m, w)
        if fehler:
            self.meldung(fehler, fehler=True)
            self._protokoll("Ermüdungslasten: " + fehler)
            return None
        # pruefen hat eine verschwundene Zeile schon abgewiesen: alt ist None
        # (neue Zeile) oder steht im Modell
        alt = w["alt"] or None
        was = f"Ermüdungslast {fl.name}" + (f" (vorher {alt})" if alt and alt != fl.name else "")
        erg = {}
        self._aendern(was, lambda: erg.update(anschluesse=schreiben(self.modell(), fl, alt)))
        self._alt = fl.name
        self.tabelle_fuellen()
        self.zeile_waehlen(fl.name)
        text = f"Zeile „{fl.name}“ übernommen."
        if erg.get("anschluesse"):
            text += " Umbenannt auch in den Anschlüssen " + ", ".join(erg["anschluesse"]) + "."
        self.meldung(text)
        self._protokoll(text)
        return fl

    # -- Zeilen anlegen, loeschen, ordnen ---------------------------------
    def _je_lastfall_fuellen(self):
        vorher = {self.je_lastfall_liste.item(i).text()
                  for i in range(self.je_lastfall_liste.count())
                  if self.je_lastfall_liste.item(i).checkState() == QtCore.Qt.Checked}
        self.je_lastfall_liste.clear()
        for z in self._zustaende():
            it = QtWidgets.QListWidgetItem(z)
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked if z in vorher else QtCore.Qt.Unchecked)
            self.je_lastfall_liste.addItem(it)

    def _je_lastfall_zeigen(self):
        self._je_lastfall_fuellen()
        self.je_lastfall_panel.setVisible(True)

    def _je_lastfall_alle(self, ein: bool):
        for i in range(self.je_lastfall_liste.count()):
            self.je_lastfall_liste.item(i).setCheckState(QtCore.Qt.Checked if ein else QtCore.Qt.Unchecked)

    def zeilen_je_lastfall(self, namen: list = None) -> list:
        """Je Zustand eine Zeile „Zustand gegen Nullzustand, n = global“.

        Gibt es fuer einen Zustand schon eine solche Zeile, entsteht keine
        zweite: sie zaehlte seine Schaedigung doppelt. Rueckgabe: die Namen
        der neuen Zeilen.
        """
        m = self.modell()
        if namen is None:
            namen = [self.je_lastfall_liste.item(i).text()
                     for i in range(self.je_lastfall_liste.count())
                     if self.je_lastfall_liste.item(i).checkState() == QtCore.Qt.Checked]
        taugt = set(m.ermuedungszustaende())
        vorhanden = {f.case_max: f.name for f in m.fatigue_loads.values()
                     if not f.folge and f.case_min is None}
        neu, uebersprungen = [], []
        belegt = set(m.fatigue_loads)
        for z in dict.fromkeys(namen):
            if z not in taugt:
                uebersprungen.append(f"{z} (kein Einzelergebnis)")
                continue
            if z in vorhanden:
                uebersprungen.append(f"{z} (schon in Zeile {vorhanden[z]})")
                continue
            name, k = z, 2
            while name in belegt:
                name, k = f"{z} ({k})", k + 1
            belegt.add(name)
            neu.append(FatigueLoad(name, z, None, cycles=None, factor=1.0))
        if not neu:
            self.meldung("Keine neue Zeile" + (": " + "; ".join(uebersprungen) if uebersprungen
                                                else " – nichts gewählt."), fehler=True)
            return []

        def anlegen():
            for f in neu:
                self.modell().fatigue_loads[f.name] = f

        self._aendern(f"Ermüdungslasten je Lastfall ({len(neu)})", anlegen)
        self.je_lastfall_panel.hide()
        self.tabelle_fuellen()
        self.zeile_waehlen(neu[0].name)
        text = (f"{len(neu)} Zeilen angelegt: " + ", ".join(f.name for f in neu)
                + (". Übersprungen: " + "; ".join(uebersprungen) if uebersprungen else "")
                + ". Je Zeile die eigene Lastspielzahl eintragen oder die globale lassen.")
        self.meldung(text)
        self._protokoll(text)
        return [f.name for f in neu]

    def zeile_loeschen(self):
        m = self.modell()
        name = self._alt
        if name not in m.fatigue_loads:
            return self.meldung("Keine Zeile gewählt.", fehler=True)
        namen = list(m.fatigue_loads)
        i = namen.index(name)
        self._aendern(f"Ermüdungslast {name} gelöscht",
                      lambda: self.modell().fatigue_loads.pop(name, None))
        self._alt = None
        self.tabelle_fuellen()
        rest = list(self.modell().fatigue_loads)
        if rest:
            self.zeile_waehlen(rest[min(i, len(rest) - 1)])
        else:
            self.neue_zeile()
        self.meldung(f"Zeile „{name}“ gelöscht.")

    def _zeile_schieben(self, schritt: int):
        name = self._alt
        m = self.modell()
        namen = list(m.fatigue_loads)
        if name not in namen or not 0 <= namen.index(name) + schritt < len(namen):
            return
        self._aendern("Reihenfolge der Ermüdungslasten",
                      lambda: verschieben(self.modell(), name, schritt))
        self.tabelle_fuellen()
        self.zeile_waehlen(name)

    def zeile_hoch(self):
        self._zeile_schieben(-1)

    def zeile_runter(self):
        self._zeile_schieben(+1)
