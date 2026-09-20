"""Fenster mit der Liste der Lastfaelle und Kombinationen einer Rechnung.

Waehrend einer Rechnung zeigte Statik3D bisher einen Balken und das
Protokoll. Bei 422 Lastfaellen sagt das wenig: Welcher laeuft gerade? Wie
lange hat der vorige gebraucht? Wie weit ist er konvergiert? Und auf wie
vielen Rechnern laeuft das ueberhaupt? Dieses Fenster fuehrt je Posten eine
Zeile und fuellt sie aus dem Fortschrittsstrom des Rechenkerns.

Es ist **nicht modal**: die Liste laesst sich waehrend der Rechnung scrollen,
und das uebrige Programm bleibt bedienbar. Der Abbruchknopf ruft denselben
Weg wie der Knopf in der Statuszeile (`_fortschritt_abbrechen` ->
`SolveWorker.abbrechen`): die Rechnung haelt beim naechsten Fortschrittsaufruf
an, eine laufende Faktorisierung laeuft zu Ende.

Der Verstand des Fensters - welche Posten es gibt und was eine Meldung ueber
Schritt, Konvergenz und Farm sagt - steht in den reinen Funktionen dieses
Kopfteils. Sie brauchen kein Qt und sind darum ohne Oberflaeche pruefbar
(tests/test_rechenliste.py).
"""
from __future__ import annotations

import re
import time

#: Nach jedem fertigen Posten meldet der Rechenkern eine Zeile dieser Form
#: (solver._solve_cases_innen, solve_combinations). Sie ist die einzige
#: Marke, an der dieses Fenster einen Posten abschliesst.
MARKE = re.compile(r"^(Lastfall|Kombination) (.+?) \((\d+)/(\d+)\)")

#: Die Schritte innerhalb eines Postens. Beide Zeilen tragen die Zahl, an der
#: man die Konvergenz ablesen kann: die Kontakt-Iteration das bezogene Delta u
#: (solver:2972), die Plastizitaet die Aenderung der plastischen Dehnung
#: (plastizitaet:399).
KONTAKT = re.compile(r"^Kontakt-Iteration (\d+)\s*:")
PLASTISCH = re.compile(r"^Plastizität: Laststufe (\d+)/(\d+), Schritt (\d+)\s*:")
MASS = re.compile(r"(Δu|Änderung)\s+([0-9][0-9.,]*(?:[eE][-+]?[0-9]+)?)")
#: Punkt und Komma duerfen in der Zahl stehen (3.2e-05 wie 3,2e-05), aber
#: nicht an ihrem Ende - dort trennen sie die Angaben der Meldung.

LAEUFT = "läuft"
FERTIG = "fertig"
OFFEN = "offen"
ABGEBROCHEN = "abgebrochen"


def posten_aus_modell(model, kind: str) -> list:
    """[(Name, Art)] der Posten, die eine Rechnung dieser Art abarbeitet.

    `kind` ist die Wahl aus `MainWindow.do_solve`: "all" rechnet alle
    Lastfaelle und danach die Kombinationen, "case" nur den aktiven. Fuer
    "modal" und "buckling" gibt es keine Postenliste - dort ist es ein Lauf,
    und das Fenster bleibt zu.
    """
    if kind == "case":
        aktiv = getattr(model, "active_case", None)
        return [(str(aktiv), "Lastfall")] if aktiv else []
    if kind != "all":
        return []
    posten = [(str(n), "Lastfall") for n in (getattr(model, "load_cases", None) or [])]
    for k in (getattr(model, "combinations", None) or []):
        name = getattr(k, "name", None) or str(k)
        posten.append((str(name), "Kombination"))
    return posten


def marke_lesen(text: str):
    """(Art, Name, Nummer, Gesamt) einer Fertigmeldung, sonst None.

    Der Rechenkern meldet "Lastfall LF3 (2/422)", **nachdem** der Posten
    gerechnet ist - die Zeile schliesst ihn also ab und eroeffnet den
    naechsten.
    """
    m = MARKE.match(str(text).strip())
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3)), int(m.group(4))


def fortschritt_aus_meldung(text: str) -> dict:
    """Was eine Meldung ueber Schritt und Konvergenz des Postens sagt.

    Rueckgabe (leer, wenn die Zeile nichts davon traegt): ``kontakt`` die
    Nummer der Kontakt-Iteration, ``laststufe`` (k, n) und ``plastisch`` der
    Schritt der Plastizitaet, ``mass`` die gemessene Konvergenzzahl als
    fertiger Text ("Δu 3.2e-05").
    """
    t = str(text).strip()
    d: dict = {}
    m = KONTAKT.match(t)
    if m:
        d["kontakt"] = int(m.group(1))
    m = PLASTISCH.match(t)
    if m:
        d["laststufe"] = (int(m.group(1)), int(m.group(2)))
        d["plastisch"] = int(m.group(3))
    m = MASS.search(t)
    if m:
        d["mass"] = "%s %s" % (m.group(1), m.group(2).rstrip(".,"))
    return d


def schritte_text(stand: dict) -> str:
    """Die Spalte "Schritte" aus dem gesammelten Stand eines Postens.

    Beide Zaehler stehen nebeneinander, weil beide Zeit kosten: am Drehlager
    braucht ein warmer Lastfall 46 Kontaktschritte auf 19 Plastizitaets-
    schritte (gemessen 20.09.2026).
    """
    teile = []
    if stand.get("kontakt"):
        teile.append("Kontakt %d" % stand["kontakt"])
    if stand.get("plastisch"):
        stufe = stand.get("laststufe")
        teile.append("Plast. %d" % stand["plastisch"]
                     + (" (Stufe %d/%d)" % stufe if stufe and stufe[1] > 1 else ""))
    return " · ".join(teile)


def zustand_aus_meldung(text: str, bisher: str) -> str:
    """Was eine Meldung ueber den Konvergenzstand des laufenden Postens sagt.

    "NICHT konvergiert" muss vor "konvergiert" geprueft werden, sonst
    verschluckt die Teilzeichenkette die Verneinung.

    Und die Verneinung **klebt**: ein Posten loest mit Plastizitaet viele
    Male, und ein einziger gekappter Lauf zaehlt - genauso haelt es der
    Bericht (solver: "Nicht konvergiert klebt").
    """
    t = str(text)
    if "NICHT konvergiert" in t or "nicht konvergiert" in t:
        return "nicht konvergiert"
    if bisher == "nicht konvergiert":
        return bisher
    if "konvergiert" in t:
        return "konvergiert"
    return bisher


def farm_text(status: dict) -> str:
    """Der Stand der Rechnerfarm in einer Zeile (farm._State.status).

    Ohne Farm rechnet Statik3D im lokalen Prozesspool; dann steht in der
    Kopfzeile nur, was `parallel.describe()` sagt.
    """
    ws = (status or {}).get("workers") or {}
    aktiv = sum(1 for v in ws.values() if v.get("alive"))
    erledigt = sum(int(v.get("jobs", 0) or 0) for v in ws.values())
    wartend = int((status or {}).get("queued", 0) or 0)
    return ("%d von %d Rechnern aktiv, %d Aufträge wartend, %d erledigt"
            % (aktiv, len(ws), wartend, erledigt))


def dauer_text(sekunden: float) -> str:
    """Sekunden als h:mm:ss bzw. m:ss - fuer eine Liste, die man ueberfliegt."""
    s = max(0, int(round(sekunden)))
    if s >= 3600:
        return "%d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)
    return "%d:%02d" % (s // 60, s % 60)


try:                                         # ohne Oberflaeche bleibt der Rest nutzbar
    from PySide6 import QtCore, QtWidgets
except Exception:                            # noqa: BLE001 - Kopfteil ohne Qt pruefbar
    QtCore = QtWidgets = None


if QtWidgets is not None:

    class Rechenliste(QtWidgets.QDialog):
        """Nicht modales Fenster mit einer Zeile je Posten."""

        SPALTEN = ("Posten", "Art", "Zustand", "Schritte", "Konvergenz", "Zeit", "Meldung")
        S_ZUSTAND, S_SCHRITTE, S_KONVERGENZ, S_ZEIT, S_MELDUNG = 2, 3, 4, 5, 6

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Berechnung läuft")
            self.setModal(False)
            self.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)
            self.resize(980, 460)
            self._zeile_von_name: dict = {}
            self._laufend = -1
            self._t_posten = 0.0
            self._zustand: list = []
            #: je Zeile der gesammelte Stand aus `fortschritt_aus_meldung`
            self._schritte: list = []
            #: der letzte Stand aus einer Marke - `beenden` haengt sein Wort
            #: daran, damit nicht eine Nachlaufmeldung darin stehen bleibt
            self._stand = ""
            self._rechner = ""
            #: True, solange die Liste dem laufenden Posten folgt; sobald der
            #: Anwender selbst scrollt, bleibt sie stehen - sonst ruckt sie
            #: ihm beim Lesen unter dem Finger weg.
            self._folgt = True

            self.kopf_rechner = QtWidgets.QLabel("")
            self.kopf_rechner.setToolTip("Prozesspool und Gleichungslöser dieser Rechnung; "
                                         "bei eingeschalteter Rechnerfarm zusätzlich, wie viele "
                                         "Rechner arbeiten und wie viele Aufträge warten")

            self.tabelle = QtWidgets.QTableWidget(0, len(self.SPALTEN), self)
            self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
            self.tabelle.verticalHeader().setVisible(False)
            self.tabelle.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.tabelle.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            kopf = self.tabelle.horizontalHeader()
            for j in range(len(self.SPALTEN) - 1):
                kopf.setSectionResizeMode(j, QtWidgets.QHeaderView.ResizeToContents)
            kopf.setSectionResizeMode(self.S_MELDUNG, QtWidgets.QHeaderView.Stretch)
            self.tabelle.verticalScrollBar().sliderPressed.connect(self._nicht_mehr_folgen)

            self.kopfzeile = QtWidgets.QLabel("")
            self.btn_abbrechen = QtWidgets.QPushButton("Abbrechen")
            self.btn_abbrechen.setToolTip(
                "Rechnung anhalten: sie hält beim nächsten Rechenschritt an, eine laufende "
                "Faktorisierung läuft zu Ende; Ergebnis und Netz bleiben, wie sie waren")
            self.btn_folgen = QtWidgets.QPushButton("Dem Laufenden folgen")
            self.btn_folgen.setToolTip("Die Liste springt wieder zum gerade rechnenden Posten")
            self.btn_folgen.clicked.connect(self._wieder_folgen)

            unten = QtWidgets.QHBoxLayout()
            unten.addWidget(self.kopfzeile, 1)
            unten.addWidget(self.btn_folgen)
            unten.addWidget(self.btn_abbrechen)
            lay = QtWidgets.QVBoxLayout(self)
            lay.addWidget(self.kopf_rechner)
            lay.addWidget(self.tabelle, 1)
            lay.addLayout(unten)

            self._takt = QtCore.QTimer(self)
            self._takt.setInterval(500)
            self._takt.timeout.connect(self._zeit_auffrischen)
            #: Die Farm wird seltener gefragt - jede Abfrage ist ein Ruf ueber
            #: das Netz und laeuft im Oberflaechen-Faden (wie in rechenhilfe).
            self._farm_takt = QtCore.QTimer(self)
            self._farm_takt.setInterval(2000)
            self._farm_takt.timeout.connect(self._farm_auffrischen)

        # ---- Aufbau ------------------------------------------------------
        def rechner_setzen(self, text: str) -> None:
            """Die Kopfzeile: Prozesspool, Loeser - und, wenn eine Farm
            eingeschaltet ist, ihr laufend aufgefrischter Stand."""
            self._rechner = str(text)
            self.kopf_rechner.setText(self._rechner)
            if self._farm_eingeschaltet():
                self._farm_auffrischen()
                self._farm_takt.start()

        def posten_setzen(self, posten) -> None:
            """Die Liste aufbauen; der erste Posten gilt sofort als laufend."""
            self.tabelle.setRowCount(0)
            self._zeile_von_name = {}
            self._zustand = []
            self._schritte = []
            for i, (name, art) in enumerate(posten):
                self.tabelle.insertRow(i)
                for j, wert in enumerate((name, art, OFFEN, "", "", "", "")):
                    self.tabelle.setItem(i, j, QtWidgets.QTableWidgetItem(wert))
                self._zeile_von_name.setdefault((art, name), i)
                self._zustand.append("")
                self._schritte.append({})
            self._stand = "%d Posten" % len(posten)
            self.kopfzeile.setText(self._stand)
            self._laufend = 0 if posten else -1
            self._t_posten = time.time()
            if self._laufend >= 0:
                self._setze(self._laufend, self.S_ZUSTAND, LAEUFT)
            self._takt.start()

        # ---- Fortschritt -------------------------------------------------
        def melden(self, text: str) -> None:
            """Eine Zeile des Rechenkerns einarbeiten."""
            marke = marke_lesen(text)
            if marke is not None:
                self._posten_abschliessen(marke)
                return
            if self._laufend < 0:
                # Hinter dem letzten Posten kommen noch Umhuellende und
                # Nachweise. Ohne diese Zeile saehe das Fenster dabei aus,
                # als haenge es - bei 422 Lastfaellen dauert der Nachlauf.
                self.kopfzeile.setText("%s - %s" % (self._stand, str(text)[:120]))
                return
            i = self._laufend
            self._setze(i, self.S_MELDUNG, str(text)[:160])
            d = fortschritt_aus_meldung(text)
            if d:
                self._schritte[i].update(d)
                self._setze(i, self.S_SCHRITTE, schritte_text(self._schritte[i]))
                if d.get("mass"):
                    self._setze(i, self.S_KONVERGENZ, d["mass"])
            neu = zustand_aus_meldung(text, self._zustand[i])
            if neu != self._zustand[i]:
                self._zustand[i] = neu
                self._setze(i, self.S_ZUSTAND, "%s (%s)" % (LAEUFT, neu))

        def beenden(self, wie: str = FERTIG) -> None:
            """Die Rechnung ist zu Ende - laufende Zeile abschliessen."""
            self._takt.stop()
            self._farm_takt.stop()
            if 0 <= self._laufend < self.tabelle.rowCount():
                self._setze(self._laufend, self.S_ZUSTAND, wie)
                self._setze(self._laufend, self.S_ZEIT, dauer_text(time.time() - self._t_posten))
            self.btn_abbrechen.setEnabled(False)
            self.kopfzeile.setText(self._stand + " - " + wie)

        # ---- innen -------------------------------------------------------
        def _posten_abschliessen(self, marke) -> None:
            art, name, nummer, gesamt = marke
            zeile = self._zeile_von_name.get((art, name), self._laufend)
            if zeile is not None and zeile >= 0:
                self._setze(zeile, self.S_ZUSTAND, self._zustand[zeile] or FERTIG)
                self._setze(zeile, self.S_ZEIT, dauer_text(time.time() - self._t_posten))
            self._stand = "%s %d von %d" % (art, nummer, gesamt)
            self.kopfzeile.setText(self._stand)
            self._t_posten = time.time()
            naechste = (zeile + 1) if zeile is not None else 0
            self._laufend = naechste if naechste < self.tabelle.rowCount() else -1
            if self._laufend >= 0:
                self._setze(self._laufend, self.S_ZUSTAND, LAEUFT)
                self._folgen()

        def _setze(self, zeile: int, spalte: int, wert: str) -> None:
            eintrag = self.tabelle.item(zeile, spalte)
            if eintrag is None:
                eintrag = QtWidgets.QTableWidgetItem("")
                self.tabelle.setItem(zeile, spalte, eintrag)
            eintrag.setText(str(wert))

        def _zeit_auffrischen(self) -> None:
            if 0 <= self._laufend < self.tabelle.rowCount():
                self._setze(self._laufend, self.S_ZEIT, dauer_text(time.time() - self._t_posten))

        def _farm_eingeschaltet(self) -> bool:
            try:
                from .. import parallel
                return parallel.settings().backend == "farm"
            except Exception:                                # noqa: BLE001
                return False

        def _farm_auffrischen(self) -> None:
            """Den Farmstand holen - wie rechenhilfe._stand_holen, und ebenso
            nachsichtig: eine gestoerte Verbindung darf das Fenster nicht
            mitreissen, die Rechnung laeuft ja weiter."""
            try:
                from .. import farm, parallel
                s = parallel.settings()
                st = farm.FarmClient(s.farm_host, s.farm_port, s.farm_key).status()
            except Exception as ex:                          # noqa: BLE001
                self.kopf_rechner.setText("%s - Farm nicht erreichbar: %s" % (self._rechner, ex))
                return
            self.kopf_rechner.setText("%s - %s" % (self._rechner, farm_text(st)))

        def _nicht_mehr_folgen(self) -> None:
            self._folgt = False

        def _wieder_folgen(self) -> None:
            self._folgt = True
            self._folgen()

        def _folgen(self) -> None:
            if not self._folgt or self._laufend < 0:
                return
            eintrag = self.tabelle.item(self._laufend, 0)
            if eintrag is not None:
                self.tabelle.scrollToItem(eintrag, QtWidgets.QAbstractItemView.PositionAtCenter)
