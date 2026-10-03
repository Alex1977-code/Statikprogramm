"""
Erscheinungsbild des Programmfensters (Entwurf „Werkbank").

Hier steht alles, was nur mit dem Aussehen und der Anordnung zu tun hat:
die Farben, das Stilblatt fuer Qt, die dunkle Kopfzeile, die Werkzeugleiste,
der Modellbaum und der Filmstreifen der Stellungen. Die Rechen- und
Eingabelogik bleibt in main.py.

Die Aufteilung folgt dem Entwurf: oben die dunkle Kopfzeile mit Programmname,
Bauteil und Zustand, darunter die Werkzeugleiste, dann drei Spalten -
Modellbaum links, 3D-Ansicht mit dem Filmstreifen der Stellungen in der Mitte,
die Eingaben rechts - und unten Protokoll und Tabellen.
"""
from __future__ import annotations

import contextlib
import os
import re

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from .. import elemente as EL
from .. import zahlen as zl
from ..knotenrollen import konstruktionsknoten

#: Farben des Entwurfs
FARBEN = {
    "kopf": "#1c2733",
    "kopf_text": "#ffffff",
    "kopf_matt": "#b9c4cf",
    "grund": "#f4f6f8",
    "flaeche": "#ffffff",
    "linie": "#dde3e8",
    "text": "#1d2731",
    "matt": "#66717c",
    "akzent": "#1467c6",
    "akzent_hell": "#eaf2fc",
    "akzent2": "#e5701c",
    "gut": "#2e8b3a",
    "schlecht": "#c62828",
    "warn": "#b7791f",
    # Warnfarbe fuer Text (Protokoll, 11 px): dunkler als "warn" - Kontrast auf
    # Weiss 4,8 zu 1 statt 3,6, WCAG AA verlangt 4,5 fuer kleine Schrift.
    # "warn" bleibt fuer Modellbaum und Filmstreifen (Teilpaket 9a)
    "warn_text": "#b35a00",
    "ansicht": "#e9edf1",
    # Eingabetabellen (Teilpaket 10a): editierbare Zelle weiss, feste grau
    "zelle_edit": "#ffffff",
    "zelle_fest": "#eceff2",
    # Pfeile gesperrter Felder und Drehfelder am Anschlag (Teilpaket 11f); dieselbe
    # Farbe wie die Schrift gesperrter Knoepfe (QPushButton:disabled)
    "gesperrt": "#a9b6c2",
}

#: Stilblatt fuer das ganze Fenster
STIL = """
QMainWindow, QWidget {{ background: {grund}; color: {text};
    font-family: "Segoe UI", -apple-system, Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px; }}
/* Kopfbereich: der Grund kommt vom Behaelter, die Beschriftungen bleiben
   durchsichtig - sonst zieht die allgemeine QWidget-Regel oben sie hell. */
QWidget#kopfhalter {{ background: {kopf}; }}
Kopfzeile {{ background: {kopf}; }}
Kopfzeile QLabel {{ background: transparent; color: {kopf_matt}; }}
/* Schnellzugriff in der dunklen Kopfzeile (25.09.2026): die Symbole sind
   dunkel gezeichnet, darum ein heller Streifen darunter */
Kopfzeile QToolBar#schnellzugriff {{ background: {grund}; border: 0;
    border-radius: 7px; padding: 0px 2px; spacing: 1px; }}
Kopfzeile QToolBar#schnellzugriff QToolButton {{ padding: 2px; margin: 0px; }}
Filmstreifen {{ background: {flaeche}; border-top: 1px solid {linie}; }}
Filmstreifen > QLabel {{ background: transparent; }}
QMenuBar {{ background: {kopf}; color: {kopf_matt}; border: 0; padding: 2px 6px; }}
QMenuBar::item {{ background: transparent; padding: 5px 10px; border-radius: 6px; }}
QMenuBar::item:selected, QMenuBar::item:pressed {{ background: #39485a; color: #fff; }}
QMenuBar::item:disabled {{ color: #6b7885; }}
QMenu {{ background: {flaeche}; border: 1px solid {linie}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {akzent_hell}; color: {akzent}; }}
QMenu::separator {{ height: 1px; background: {linie}; margin: 4px 6px; }}

QToolBar {{ background: {flaeche}; border: 0; border-bottom: 1px solid {linie};
    spacing: 6px; padding: 6px 10px; }}
QToolBar QToolButton {{ background: #f7f9fb; border: 1px solid {linie};
    border-radius: 8px; padding: 6px 11px; font-weight: 600; color: {text}; }}
QToolBar QToolButton:hover {{ background: {akzent_hell}; border-color: {akzent};
    color: {akzent}; }}
QToolBar QToolButton:checked {{ background: {akzent_hell}; border-color: {akzent};
    color: {akzent}; }}
QToolBar QToolButton#start {{ background: {akzent}; border-color: {akzent};
    color: #fff; padding: 6px 13px; }}
QToolBar QToolButton#start:hover {{ background: #0f4f9a; }}

QDockWidget {{ titlebar-close-icon: none; titlebar-normal-icon: none; }}
QDockWidget::title {{ background: {flaeche}; color: {matt}; padding: 7px 10px;
    border-bottom: 1px solid {linie}; text-transform: uppercase;
    font-size: 11px; font-weight: 600; letter-spacing: 0.5px; }}

QTabWidget::pane {{ border: 0; border-top: 1px solid {linie}; background: {flaeche}; }}
QTabBar {{ background: {flaeche}; }}
QTabBar::tab {{ background: transparent; color: {matt}; padding: 8px 12px;
    border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {akzent}; border-bottom: 2px solid {akzent}; }}
QTabBar::tab:hover {{ color: {text}; }}
QTabWidget#tabellenregister::pane {{ border-top: 0; }}
QTabWidget#tabellenregister QTabBar::tab {{ padding: 5px 11px; font-weight: 500; }}

QGroupBox {{ background: {flaeche}; border: 1px solid {linie}; border-radius: 10px;
    margin-top: 12px; padding: 10px 10px 8px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
    color: {text}; }}

QPushButton {{ background: #f7f9fb; border: 1px solid {linie}; border-radius: 8px;
    padding: 7px 12px; font-weight: 600; min-height: 20px; }}
QPushButton:hover {{ background: {akzent_hell}; border-color: {akzent}; color: {akzent}; }}
QPushButton:pressed {{ background: #dce9f8; }}
QPushButton:disabled {{ color: #a9b6c2; background: #f2f4f6; }}
QPushButton[rolle="start"] {{ background: {akzent}; border-color: {akzent}; color: #fff; }}
QPushButton[rolle="start"]:hover {{ background: #0f4f9a; }}
QPushButton[rolle="warn"] {{ background: {akzent2}; border-color: {akzent2}; color: #fff; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {flaeche}; border: 1px solid {linie}; border-radius: 8px;
    padding: 5px 7px; selection-background-color: {akzent}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {akzent}; }}
QComboBox::drop-down {{ border: 0; width: 18px; }}
{pfeile}
QCheckBox, QRadioButton {{ spacing: 6px; }}

QTableWidget, QTreeWidget, QListWidget {{ background: {flaeche};
    border: 1px solid {linie}; border-radius: 8px; gridline-color: {linie};
    selection-background-color: {akzent_hell}; selection-color: {text}; }}
QHeaderView::section {{ background: #f0f3f6; color: {text}; border: 0;
    border-bottom: 1px solid {linie}; border-right: 1px solid {linie};
    padding: 5px 8px; font-weight: 600; }}
QTreeWidget {{ border: 0; }}
QTreeWidget::item {{ padding: 3px 2px; }}

QScrollArea {{ border: 0; background: {grund}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #c5cdd5; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #c5cdd5; border-radius: 5px; min-width: 24px; }}

QStatusBar {{ background: {flaeche}; border-top: 1px solid {linie}; color: {matt}; }}
QStatusBar::item {{ border: 0; }}
QProgressBar {{ border: 1px solid {linie}; border-radius: 6px; background: {grund};
    height: 14px; text-align: center; }}
QProgressBar::chunk {{ background: {akzent}; border-radius: 5px; }}
QSplitter::handle {{ background: {linie}; }}
QToolTip {{ background: {kopf}; color: #fff; border: 0; padding: 5px 7px; }}
"""


#: Ordner der Pfeilbilder (Teilpaket 11f). Er gehoert in die exe: Statik3D.spec
#: sammelt statik3d/gui/bilder ein, pyproject.toml nimmt ihn ins Paket. Gefunden
#: wird er wie statik3d/web/static ueber den Ort dieser Datei.
BILDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bilder")

#: die Pfeilbilder: Name -> (Dateiname, Pfeil nach unten?, Farbe aus FARBEN). Die
#: grauen gehoeren zu gesperrten Feldern und zu einem Drehfeld am Anschlag.
PFEILE = {"ab": ("pfeil_ab.png", True, "matt"), "auf": ("pfeil_auf.png", False, "matt"),
          "ab_grau": ("pfeil_ab_grau.png", True, "gesperrt"),
          "auf_grau": ("pfeil_auf_grau.png", False, "gesperrt")}

#: Kantenlaenge des Pfeilbilds in logischen Bildpunkten
PFEIL_KANTE = 10


def pfeil_bild(runter: bool, faktor: int = 1, farbe: str = "matt") -> QtGui.QImage:
    """Das Bild eines Pfeils (Winkel, wie Windows sie an Auswahlfeldern zeichnet).

    Unter einem Stilblatt zeichnet Qt an Aufklappliste und Drehfeld **keinen**
    Pfeil mehr, sobald ``drop-down`` bzw. ``up-button`` einen eigenen Rahmen
    bekommen (gemessen 02.10.2026: ohne die Bilder 0 dunkle Punkte im
    Pfeilbereich). Ein Dreieck aus Rahmenstrichen (``border-top: 5px solid``)
    ging nicht: Qt zeichnet daraus Balken, keine Spitze. Darum Bilder.
    ``faktor`` 2 ist die Fassung fuer hohe Bildschirmdichte (Name mit ``@2x``,
    die Qt dort selbst waehlt), ``farbe`` ein Schluessel aus FARBEN. Neu schreiben:
    ``python -c "from statik3d.gui import design; design.pfeilbilder_schreiben()"``"""
    s = PFEIL_KANTE * faktor
    bild = QtGui.QImage(s, s, QtGui.QImage.Format_ARGB32_Premultiplied)
    bild.fill(0)
    p = QtGui.QPainter(bild)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    stift = QtGui.QPen(QtGui.QColor(FARBEN[farbe]), 1.8 * faktor)
    stift.setCapStyle(QtCore.Qt.RoundCap)
    stift.setJoinStyle(QtCore.Qt.RoundJoin)
    p.setPen(stift)
    # 10 x 10: Spitze in der Mitte, Schenkel 3 Bildpunkte hoch, 6,8 breit
    oben, unten = (0.36 * s, 0.66 * s) if runter else (0.66 * s, 0.36 * s)
    p.drawPolyline([QtCore.QPointF(0.16 * s, oben), QtCore.QPointF(0.5 * s, unten),
                    QtCore.QPointF(0.84 * s, oben)])
    p.end()
    return bild


def pfeilbilder_schreiben(ordner: str = None) -> list:
    """Die Pfeilbilder (je Pfeil einfach und ``@2x``) in den Ordner schreiben;
    ohne Angabe nach :data:`BILDER`. Gibt die Dateinamen zurueck. Braucht eine
    Qt-Anwendung (QGuiApplication) nicht - QImage und QPainter genuegen."""
    ordner = ordner or BILDER
    os.makedirs(ordner, exist_ok=True)
    namen = []
    for datei, runter, farbe in PFEILE.values():
        stamm, endung = os.path.splitext(datei)
        for faktor, zusatz in ((1, ""), (2, "@2x")):
            name = stamm + zusatz + endung
            pfeil_bild(runter, faktor, farbe).save(os.path.join(ordner, name))
            namen.append(name)
    return namen


def _pfeilregeln() -> str:
    """Stilregeln fuer die Pfeile von Aufklappliste und Drehfeld - leer, wenn die
    Bilder fehlen (Qt meldete sonst bei jedem Feld eine Warnung, und die Felder
    sind dann so unschoen wie bisher, aber nicht kaputt).

    Die Pfeile stehen auf der Flaeche der Knoepfe ohne eigenen Rahmen: ein
    Drehfeld zeichnete sonst die Trennlinien der Windows-Knoepfe mit
    (gemessen: 25 dunkle Punkte am Rand des Pfeilbereichs). Der Pfad hat
    Schraegstriche und steht in Anfuehrungszeichen - der Ordner der exe
    liegt unter dem Benutzernamen, und der darf ein Leerzeichen haben."""
    k = PFEIL_KANTE
    pfade = {k: os.path.join(BILDER, v[0]).replace("\\", "/") for k, v in PFEILE.items()}
    if not all(os.path.isfile(p) for p in pfade.values()):
        return ""
    # Der Knopf ohne Rahmen hat keine Rueckmeldung mehr, die Qt selbst zeichnet:
    # beim Ueberfahren die helle Akzentflaeche, beim Druecken die dunklere der
    # Knoepfe (QPushButton:pressed). Die Rundung folgt der des Feldes (8 px
    # abzueglich 1 px Rand), sonst ragte die Flaeche ueber die Ecke.
    # ":off" ist der Zustand eines Drehfelds am Anschlag (Qt-Dokumentation).
    return (
        'QComboBox::down-arrow {{ image: url("{ab}"); width: {k}px; height: {k}px; }}\n'
        'QComboBox::down-arrow:disabled {{ image: url("{ab_grau}"); }}\n'
        'QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border;\n'
        '    subcontrol-position: top right; width: 18px; border: 0;\n'
        '    border-top-right-radius: 7px; }}\n'
        'QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border;\n'
        '    subcontrol-position: bottom right; width: 18px; border: 0;\n'
        '    border-bottom-right-radius: 7px; }}\n'
        'QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,\n'
        'QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{\n'
        '    background: {akzent_hell}; }}\n'
        'QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,\n'
        'QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{\n'
        '    background: {gedrueckt}; }}\n'
        'QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{auf}");\n'
        '    width: {k}px; height: {k}px; }}\n'
        'QSpinBox::up-arrow:disabled, QSpinBox::up-arrow:off,\n'
        'QDoubleSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:off {{\n'
        '    image: url("{auf_grau}"); }}\n'
        'QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{ab}");\n'
        '    width: {k}px; height: {k}px; }}\n'
        'QSpinBox::down-arrow:disabled, QSpinBox::down-arrow:off,\n'
        'QDoubleSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:off {{\n'
        '    image: url("{ab_grau}"); }}'
    ).format(k=k, akzent_hell=FARBEN["akzent_hell"], gedrueckt="#dce9f8", **pfade)


def stil() -> str:
    # Die Pfeilregeln kommen fertig gesetzt als Wert in die Vorlage; ihre
    # Klammern liest format() dort nicht noch einmal
    return STIL.format(pfeile=_pfeilregeln(), **FARBEN)


# ---- Protokoll: Festbreitenschrift und Faerbung (Teilpaket 9a, 02.10.2026) -------

#: Festbreitenschriften in der Reihenfolge der Vorliebe: Consolas (auf jedem
#: Windows seit Vista), Cascadia Mono (Windows 11), dann die ueblichen unter
#: Linux und macOS, zuletzt Courier New
FESTSCHRIFTEN = ("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Liberation Mono",
                 "Menlo", "Courier New")

#: die gewaehlte Familie, einmal je Programmlauf (die Schriftdatenbank aendert
#: sich nicht); None, solange es noch keine Anwendung gibt
_FAMILIE = None


def _schriften_vorhanden() -> list:
    """Die Namen der installierten Schriften. Ohne Anwendung (Qt verlangt eine
    fuer die Schriftdatenbank) und offscreen unter Windows, wo es gar keine
    Schriften gibt, ist die Liste leer."""
    if QtGui.QGuiApplication.instance() is None:
        return []
    return list(QtGui.QFontDatabase.families())


def waehle_festschrift(vorhanden, ist_fest, vorrang=FESTSCHRIFTEN):
    """Die erste Schrift aus *vorrang*, die installiert **und** wirklich
    festbreit ist - sonst None. Reine Wahl ohne Qt: *vorhanden* sind die Namen
    der installierten Schriften, *ist_fest* fragt eine Familie, ob sie fest ist.
    Der Name kommt so zurueck, wie ihn die Schriftdatenbank schreibt."""
    echt = {n.lower(): n for n in vorhanden}
    for name in vorrang:
        gefunden = echt.get(name.lower())
        if gefunden is not None and ist_fest(gefunden):
            return gefunden
    return None


def festschrift_familie() -> str:
    """Die Familie fuer Protokoll und Textfelder mit Spalten.

    „monospace“ ist unter Windows kein Schriftname: die Stilzeile
    ``font-family: monospace`` wurde dort zu Tahoma, einer Proportionalschrift
    (gemessen 02.10.2026) - Spalten im Protokoll standen schief. Darum die
    erste wirklich festbreite Schrift aus FESTSCHRIFTEN, sonst die
    Festbreitenschrift des Systems, sonst bleibt es bei „monospace“."""
    global _FAMILIE
    if _FAMILIE is not None:
        return _FAMILIE
    if QtGui.QGuiApplication.instance() is None:
        return "monospace"
    name = waehle_festschrift(_schriften_vorhanden(), QtGui.QFontDatabase.isFixedPitch)
    if name is None:
        name = (QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont).family()
                or "monospace")
    _FAMILIE = name
    return name


def festschrift_stil(px=11) -> str:
    """Stilzeile fuer ein Textfeld in der Festbreitenschrift. Die Schrift gehoert
    in die Stilzeile des Feldes, nicht in setFont: das Stilblatt des Fensters
    (STIL, Segoe UI fuer jedes QWidget) hebt ein gesetztes Schriftbild wieder auf
    (Dialoge mit setFamily("Courier New") standen so in Segoe UI, gemessen
    02.10.2026). ``px=None`` laesst die Groesse des Fensters stehen."""
    gross = f" font-size: {px}px;" if px else ""
    return f'font-family: "{festschrift_familie()}";{gross}'


#: Anfang einer Meldungszeile: FEHLER, WARNUNG oder ABBRUCH als erstes Wort, auch
#: eingerueckt (Importhinweise stehen als „  WARNUNG:   ...“, die Zusammenfassung
#: als „ABBRUCH                 : ...“); „FEHLERFREI“ zaehlt nicht
_MELDUNG = re.compile(r"\s*(FEHLER|WARNUNG|ABBRUCH)\b")

#: dasselbe nach einem Namen als erstem Wort („  S1: WARNUNG ...“ aus der
#: Stellungsreihe, bridges/positions.py): das erste Wort endet mit „:“. Was
#: danach mitten im Satz steht („... - WARNUNG: ...“), zaehlt nicht.
_MELDUNG_MIT_NAME = re.compile(r"\s*\S+:\s+(FEHLER|WARNUNG)\b")


def protokollzeile_art(text: str):
    """Wie das Protokoll die Zeile zeigt: ``"fehler"`` (rot), ``"warnung"``
    (orange), ``"abschnitt"`` (fett) oder None (unveraendert).

    Die Regel ist klein und steht im Handbuch: ein **Abschnitt** beginnt mit
    ``--- `` am Zeilenanfang („--- Beispiel 'hall' (Datum) ---“,
    „--- Freie Bewegungen ---“, „--- Berechnung gestartet ---“); eine **Meldung**
    hat FEHLER, WARNUNG oder ABBRUCH als erstes Wort der Zeile (ABBRUCH zaehlt
    wie FEHLER) oder FEHLER/WARNUNG als zweites Wort nach einem ersten Wort, das
    mit „:“ endet („  S1: WARNUNG ...“). Das Stichwort mitten im Satz faerbt
    nichts. Folgezeilen einer mehrzeiligen Meldung sind eigene Zeilen und
    bleiben, wie sie sind."""
    if text.startswith("--- "):
        return "abschnitt"
    m = _MELDUNG.match(text) or _MELDUNG_MIT_NAME.match(text)
    if m is None:
        return None
    return "warnung" if m.group(1) == "WARNUNG" else "fehler"


class ProtokollFaerber(QtGui.QSyntaxHighlighter):
    """Faerbt und fettet Zeilen des Protokolls, ohne den Text anzufassen.

    Rot ist FARBEN["schlecht"], Orange FARBEN["warn_text"] (nicht "warn": das ist
    fuer Flaechen und grosse Zeichen und liegt als 11-px-Text mit 3,6 zu 1 unter
    der Grenze 4,5 der WCAG).

    Ein Syntaxfaerber legt seine Formate ueber das Layout des Blocks; der Text
    des Dokuments und das Zeichenformat der Zeile bleiben unberuehrt -
    ``toPlainText()`` liefert genau das Geschriebene, und die rote Sammelzeile
    der Nachweise (eigenes Zeichenformat) behaelt es. Gearbeitet wird je Block,
    ohne Zustand von Zeile zu Zeile: eine neue Zeile kostet eine Regelpruefung,
    nicht einen Lauf ueber das Dokument."""

    def __init__(self, dokument):
        super().__init__(dokument)
        fehler = QtGui.QTextCharFormat()
        fehler.setForeground(QtGui.QColor(FARBEN["schlecht"]))
        warnung = QtGui.QTextCharFormat()
        warnung.setForeground(QtGui.QColor(FARBEN["warn_text"]))
        abschnitt = QtGui.QTextCharFormat()
        abschnitt.setFontWeight(QtGui.QFont.Bold)
        self._formate = {"fehler": fehler, "warnung": warnung, "abschnitt": abschnitt}

    def highlightBlock(self, text):          # noqa: N802 - Qt-Schreibweise
        fmt = self._formate.get(protokollzeile_art(text))
        if fmt is not None:
            # Qt zaehlt in UTF-16-Einheiten, Python in Codepunkten: ein Zeichen
            # ausserhalb der Grundebene (Emoji im Pfad) hat dort zwei - mit
            # len(text) bliebe das Zeilenende ungefaerbt. Die Blocklaenge
            # (ohne den Absatzumbruch) ist Qts eigene Zahl.
            self.setFormat(0, max(0, self.currentBlock().length() - 1), fmt)


class Marke(QtWidgets.QLabel):
    """Rundes Etikett wie im Entwurf (z. B. „5 Stellungen", „berechnet")."""

    def __init__(self, text: str = "", art: str = "matt", parent=None):
        super().__init__(text, parent)
        self.setArt(art)

    def setArt(self, art: str):
        farbe = {"matt": ("#39485a", "#e6edf3"), "gut": (FARBEN["gut"], "#fff"),
                 "warn": (FARBEN["akzent2"], "#fff"),
                 "schlecht": (FARBEN["schlecht"], "#fff"),
                 "akzent": (FARBEN["akzent"], "#fff")}.get(art, ("#39485a", "#e6edf3"))
        self.setStyleSheet(f"background:{farbe[0]}; color:{farbe[1]}; border-radius:10px;"
                           f"padding:3px 10px; font-size:12px;")


def kopfhalter(parent, *widgets) -> QtWidgets.QWidget:
    """Behaelter fuer Kopfzeile und Menueleiste, durchgehend dunkel.

    Ohne eigenen Grund zeichnet Qt hier die Fensterfarbe; unter Windows wird die
    Zeile dadurch weiss, sobald ein Menue geoeffnet ist.
    """
    w = QtWidgets.QWidget(parent)
    w.setObjectName("kopfhalter")
    w.setAttribute(QtCore.Qt.WA_StyledBackground, True)
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    for x in widgets:
        lay.addWidget(x)
    return w


class Kopfzeile(QtWidgets.QWidget):
    """Dunkle Kopfzeile: Programmname, Bauteil und Zustand."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setFixedHeight(40)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 12, 0)
        lay.setSpacing(12)
        self.logo = QtWidgets.QLabel("Statik3D")
        self.logo.setStyleSheet(f"color:{FARBEN['kopf_text']}; font-weight:700;"
                                "font-size:16px; letter-spacing:.3px;")
        self.titel = QtWidgets.QLabel("")
        self.titel.setStyleSheet(f"color:{FARBEN['kopf_matt']}; font-size:13px;")
        lay.addWidget(self.logo)
        lay.addWidget(self.titel, 1)
        self.marke_modell = Marke("", "matt")
        self.marke_zustand = Marke("bereit", "matt")
        lay.addWidget(self.marke_modell)
        lay.addWidget(self.marke_zustand)
        self._lay = lay
        self._eingebettet = False

    def einbetten(self, schnellzugriff: QtWidgets.QWidget, suche: QtWidgets.QWidget) -> None:
        """Schnellzugriff und Befehlssuche in diese Zeile nehmen (25.09.2026).

        Eine Zeile statt zwei: Name, Schnellzugriff, Titel, Suche, Zustand.
        Die eigene Zeile des Ribbons darueber kostete 31 px Hoehe. Der
        Modellumfang steht nur noch in der Statusleiste - die Marke bleibt als
        Objekt, wird aber nicht mehr gezeigt."""
        lay = self._lay
        # Der Titel gibt nach, wenn die Zeile knapp wird: Suche und Zustand
        # bleiben stehen, der Titel wird abgeschnitten (er steht ganz am Zeiger)
        self.titel.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.titel.setMinimumWidth(0)
        # Mittig in ihrer Wunschhoehe, damit der helle Streifen nicht die ganze
        # Zeile fuellt. Keine feste Hoehe (Gegenpruefung 25.09.2026): die Leiste
        # braucht 20 px fuer Rand und Abstand, bei setFixedHeight(30) blieben
        # den Knoepfen 10 px und von den Symbolen nur Punkte. Kleiner wird sie
        # ueber die Stilregel (Kopfzeile QToolBar#schnellzugriff, ohne Rand).
        # Die Leiste rechnet ihre Raender nur bei einer Stilaenderung neu; ohne
        # sie behielt sie die 10 px Rand der Regel fuer QToolBar aus der Zeit
        # im Ribbon (offscreen gemessen: Leiste 47 statt 31 px hoch).
        lay.insertWidget(1, schnellzugriff, 0, QtCore.Qt.AlignVCenter)
        if isinstance(schnellzugriff, QtWidgets.QToolBar):
            schnellzugriff.setMovable(False)
        st = schnellzugriff.style()
        st.unpolish(schnellzugriff)
        st.polish(schnellzugriff)
        QtWidgets.QApplication.sendEvent(schnellzugriff, QtCore.QEvent(QtCore.QEvent.StyleChange))
        lay.insertWidget(lay.indexOf(self.marke_modell), suche, 0, QtCore.Qt.AlignVCenter)
        self.marke_modell.setVisible(False)
        self._eingebettet = True

    def setzen(self, titel: str, modell: str = "", zustand: str = "",
               art: str = "matt"):
        self.titel.setText(titel)
        self.titel.setToolTip(titel)
        self.marke_modell.setText(modell)
        self.marke_modell.setVisible(bool(modell) and not self._eingebettet)
        if zustand:
            self.marke_zustand.setText(zustand)
            self.marke_zustand.setArt(art)
        self.marke_zustand.setVisible(bool(zustand))


class Stellungskarte(QtWidgets.QFrame):
    """Eine Karte des Filmstreifens: Kennung, Winkel, Name und Ausnutzung."""

    geklickt = QtCore.Signal(str)

    def __init__(self, kennung: str, name: str, winkel: float, eta=None,
                 fuehrt: bool = False, parent=None):
        super().__init__(parent)
        self.name = name
        self.fuehrt = bool(fuehrt)
        self.aktiv = False
        self.setFixedWidth(140)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._faerben()
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(9, 7, 9, 7)
        lay.setSpacing(2)
        oben = QtWidgets.QHBoxLayout()
        kn = QtWidgets.QLabel(kennung + (" ★" if fuehrt else ""))
        kn.setStyleSheet(f"background:{FARBEN['kopf']}; color:#fff; border-radius:4px;"
                         "padding:2px 6px; font-size:11px; font-weight:600;")
        oben.addWidget(kn)
        oben.addStretch(1)
        if eta is not None:
            farbe = (FARBEN["schlecht"] if eta > 1 else
                     FARBEN["warn"] if eta > 0.85 else FARBEN["gut"])
            e = QtWidgets.QLabel(f"η {eta:.2f}".replace(".", ","))
            e.setStyleSheet(f"background:{farbe}; color:#fff; border-radius:9px;"
                            "padding:2px 7px; font-size:11px; font-weight:600;")
            oben.addWidget(e)
        lay.addLayout(oben)
        gr = QtWidgets.QLabel(f"{winkel:.1f}°".replace(".", ","))
        gr.setStyleSheet("font-size:19px; font-weight:600; border:0;")
        lay.addWidget(gr)
        nm = QtWidgets.QLabel(name)
        nm.setStyleSheet(f"color:{FARBEN['matt']}; font-size:12px; border:0;")
        nm.setToolTip(name)
        lay.addWidget(nm)

    def _faerben(self):
        """Rand nach Zustand: gewaehlt (Akzent), massgebend (Akzent 2), sonst Linie."""
        rand = (FARBEN["akzent"] if self.aktiv else
                FARBEN["akzent2"] if self.fuehrt else FARBEN["linie"])
        dicke = 2 if self.aktiv else 1
        self.setStyleSheet(
            f"QFrame {{ background:{FARBEN['flaeche']}; border:{dicke}px solid {rand};"
            f"border-radius:10px; }}")

    def setzen_aktiv(self, an: bool):
        if bool(an) != self.aktiv:
            self.aktiv = bool(an)
            self._faerben()

    def mousePressEvent(self, ev):
        self.geklickt.emit(self.name)
        super().mousePressEvent(ev)


class Filmstreifen(QtWidgets.QWidget):
    """Die Stellungen des Systems als Karten unter der Ansicht."""

    gewaehlt = QtCore.Signal(str)
    neu = QtCore.Signal()
    rechnen = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        aussen = QtWidgets.QVBoxLayout(self)
        aussen.setContentsMargins(12, 8, 12, 10)
        aussen.setSpacing(6)
        kopf = QtWidgets.QHBoxLayout()
        t = QtWidgets.QLabel("STELLUNGEN DES SYSTEMS")
        t.setStyleSheet(f"color:{FARBEN['matt']}; font-size:11px; font-weight:600;"
                        "letter-spacing:.5px;")
        kopf.addWidget(t)
        self.lbl_umh = QtWidgets.QLabel("")
        self.lbl_umh.setStyleSheet(f"color:{FARBEN['matt']}; font-size:12px;")
        kopf.addStretch(1)
        kopf.addWidget(self.lbl_umh)
        b_neu = QtWidgets.QPushButton("+ Stellung")
        b_neu.clicked.connect(self.neu.emit)
        b_rech = QtWidgets.QPushButton("▶ rechnen")
        b_rech.setProperty("rolle", "start")
        b_rech.clicked.connect(self.rechnen.emit)
        kopf.addWidget(b_neu)
        kopf.addWidget(b_rech)
        aussen.addLayout(kopf)
        self.bereich = QtWidgets.QScrollArea()
        self.bereich.setWidgetResizable(True)
        self.bereich.setFixedHeight(96)
        self.bereich.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.bereich.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.inhalt = QtWidgets.QWidget()
        self.reihe = QtWidgets.QHBoxLayout(self.inhalt)
        self.reihe.setContentsMargins(0, 0, 0, 0)
        self.reihe.setSpacing(8)
        self.reihe.addStretch(1)
        self.bereich.setWidget(self.inhalt)
        aussen.addWidget(self.bereich)

    def fuellen(self, stellungen: list, umhuellende: str = ""):
        """stellungen: [{name, winkel, eta, fuehrt}]"""
        while self.reihe.count():
            p = self.reihe.takeAt(0)
            if p.widget():
                # Nur ausblenden und zum Loeschen vormerken: setParent(None)
                # wuerde die Karte zu einem eigenen Fenster machen.
                p.widget().hide()
                p.widget().deleteLater()
        if not stellungen:
            hin = QtWidgets.QLabel("noch keine Stellung angelegt – „+ Stellung“")
            hin.setStyleSheet(f"color:{FARBEN['matt']};")
            self.reihe.addWidget(hin)
        for i, s in enumerate(stellungen, 1):
            k = Stellungskarte(f"S{i}", s.get("name", ""), float(s.get("winkel", 0.0)),
                               s.get("eta"), bool(s.get("fuehrt")))
            k.geklickt.connect(self.gewaehlt.emit)
            self.reihe.addWidget(k)
        self.reihe.addStretch(1)
        self.lbl_umh.setText(umhuellende)
        if getattr(self, "_gewaehlt", ""):
            self.waehlen(self._gewaehlt)

    def waehlen(self, name: str):
        """Die Karte dieser Stellung hervorheben, die anderen zuruecknehmen."""
        self._gewaehlt = name
        for k in self.inhalt.findChildren(Stellungskarte):
            k.setzen_aktiv(k.name == name)


def _kurz(punkt) -> str:
    """Koordinaten knapp: „2 | 0 | 0". Rundungsschrott wie 1.2e-16 wird zu 0."""
    teile = []
    for v in np.asarray(punkt, float).ravel()[:3]:
        v = 0.0 if abs(v) < 1e-12 else float(v)
        teile.append(zl.zahl_text(v, stellen=4))       # nie „1.235e+04“ (25.09.2026)
    return " | ".join(teile)


#: Wie viele Einzeleintraege ein Zweig hoechstens ausklappt. Darueber steht
#: eine Sammelzeile; die vollstaendige Liste steht in der Tabelle unten, wo
#: sie gefiltert und sortiert werden kann.
#: So viele Eintraege je Zweig - alle Knoten, Linien, Staebe, Flaechen und
#: Volumen stehen numerisch untereinander; erst jenseits dieser Zahl kommt
#: der Verweis auf die Tabelle.
BAUM_MAX = 20000


def natuerlich(name) -> list:
    """Sortierschluessel, der Zahlen als Zahlen liest: K2 vor K10, F9 vor F10.

    Alphabetisch sortiert steht „V10“ vor „V2“, weil die 1 vor der 2 kommt -
    eine Liste von hundert Volumen wirkt dann ungeordnet. Der Schluessel
    zerlegt den Namen darum in Text- und Zahlstuecke und vergleicht die Zahlen
    als Zahlen; die Stellenzahl spielt dann keine Rolle mehr. Die Zerlegung
    wechselt sich immer ab (Text, Zahl, Text, ...), darum treffen beim
    Vergleich zweier Namen nie eine Zahl und ein Text aufeinander.

    Dieselbe Reihenfolge gilt ueberall, wo Objekte aufgezaehlt werden:
    Modellbaum, Modelltabellen, Aufklapplisten der Masken.
    """
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(name))]


#: Alter Name desselben Schluessels.
_natuerlich = natuerlich


def namen(verzeichnis) -> list:
    """Die Namen eines Objektverzeichnisses in natuerlicher Reihenfolge.

    Der eine Weg fuer alle Aufzaehlungen in der Oberflaeche: Modellbaum,
    Modelltabellen, Aufklapplisten der Masken. So steht ueberall dieselbe
    Reihenfolge, und „V2“ nie hinter „V10“.
    """
    return sorted(verzeichnis or (), key=natuerlich)


class _Rest:
    """Die Eintraege einer gekuerzten Liste ab BAUM_MAX (Teilpaket 8d,
    03.10.2026): der Baum zeigt sie nicht, findet sie aber - fuer die Ansicht
    (die eine Zeile wird nachgeladen) und fuer den Filter (seine Treffer werden
    nachgeladen). Schluessel und Namen entstehen erst, wenn jemand sucht; die
    ganze Zeile mit Zusatz und Hinweis nur fuer einen nachgeladenen Eintrag. Am
    Drehlager kostete der Text aller Knoten 2,5 s je Aufbau (8c).

    ``schluessel()`` liefert die Schluessel in der Folge der Liste, ``name(j)``
    den Text der Zeile j, ``bauen(j)`` die ganze Zeile (Text, Zusatz,
    Schluessel, Hinweis[, Farbe]) wie in :meth:`Modellbaum._liste`."""

    def __init__(self, eltern, zeile, art, anzahl, schluessel, name, bauen):
        self.eltern = eltern            # der Zweig
        self.zeile = zeile              # seine Sammelzeile „… N weitere“
        self.art = art                  # die Art der Eintraege
        self.anzahl = int(anzahl)       # so viele stehen hinter BAUM_MAX
        self._schluessel_quelle = schluessel
        self.name = name
        self.bauen = bauen
        self._schluessel = None         # die Schluessel, beim ersten Suchen
        self._stellen = None            # Schluessel -> Stelle
        self._namen = None              # Namen in Kleinbuchstaben, beim ersten Filtern
        #: nachgeladene Zeilen: Schluessel -> Zeile
        self.geladen: dict = {}
        #: die Schluessel davon, die der Filter nachgeladen hat (er nimmt sie
        #: beim Aufheben wieder heraus, ausser sie sind gewaehlt)
        self.vom_filter: set = set()
        #: Treffer des laufenden Filters, die nicht nachgeladen sind (FILTER_MAX)
        self.treffer_offen = 0

    def _alle_schluessel(self) -> list:
        if self._schluessel is None:
            self._schluessel = [str(k) for k in self._schluessel_quelle()]
        return self._schluessel

    def schluessel(self, j: int) -> str:
        return self._alle_schluessel()[j]

    def stelle(self, key) -> "int | None":
        """Die Stelle des Eintrags mit diesem Schluessel, sonst ``None``."""
        if self._stellen is None:
            self._stellen = {k: j for j, k in enumerate(self._alle_schluessel())}
        return self._stellen.get(str(key))

    def treffer(self, such: str) -> list:
        """Die Stellen der Eintraege, deren Name ``such`` enthaelt (klein)."""
        if self._namen is None:
            self._namen = [str(self.name(j)).lower() for j in range(self.anzahl)]
        return [j for j, n in enumerate(self._namen) if such in n]


class Modellbaum(QtWidgets.QTreeWidget):
    """Der Modellbaum links: **alles**, was im Modell modelliert werden kann.

    Knoten, Linien, Staebe, Flaechen, Volumen, Lager (Knoten, Linie, Flaeche),
    Gelenke, Kontaktbedingungen, Querschnitte, Werkstoffe, Dicken, Lastfaelle,
    Kombinationen und die Nachweisobjekte stehen hier mit ihrer Anzahl,
    seit 03.10.2026 in Gruppen nach dem Ablauf (:attr:`GRUPPEN`).

    Ein **Klick auf einen Eintrag** waehlt das Objekt aus und zeigt rechts
    seine Maske, ein **Doppelklick** oeffnet es zum Bearbeiten. Ein **Klick auf
    einen Zweig** waehlt nichts und legt nichts an (Teilpaket 8b, 03.10.2026;
    Antwort 4 vom 24.09.2026): rechts steht die Uebersicht des Zweigs mit
    Anzahl und Liste, unten seine Tabelle. Der **Doppelklick auf einen Zweig**
    oeffnet die Anlegemaske „Neu …“, nicht modal; angelegt wird erst mit OK
    (Antwort 11). Bis zum 03.10.2026 waehlte der Klick auf neun Zweige alle
    Objekte der Art aus, und vier Zweige oeffneten schon beim einfachen Klick
    ihre Anlegemaske. Alles laeuft ueber Signale, damit das Fenster entscheidet,
    was daraus wird; :meth:`zweig_finden` sagt ihm, welcher Zweig gemeint ist.

    **Ansicht -> Baum** (Teilpaket 8d, 03.10.2026): was in der Ansicht gewaehlt
    wird, markiert :meth:`auswahl_nachfuehren` hier, ohne Signale und ohne die
    Tastatur zu nehmen. Gesucht wird im Suchverzeichnis ``_verzeichnis`` (Art
    und Schluessel -> Zeile), das :meth:`_zweig` beim Aufbau mitbaut; hinter
    einer Sammelzeile „… N weitere“ wird die Zeile nachgeladen (:class:`_Rest`).
    Die **Filterzeile** darueber (:class:`Baumfilter`, Strg+F im Baum) filtert
    die Zeilen nach dem Namen (:meth:`filtern`).
    """

    angeklickt = QtCore.Signal(str, str)      # (Art, Name)
    bearbeiten = QtCore.Signal(str, str)      # (Art, Name) - Doppelklick
    neu = QtCore.Signal(str)                  # Zweigart: ein neues Objekt anlegen
    loeschen = QtCore.Signal(str, str)        # (Art, Name): Objekt loeschen
    #: Mehrere Eintraege derselben Art gewaehlt (Strg-Klick, Umschalt-Klick,
    #: Umschalt-Pfeiltaste): (Art, [Namen]). Das Fenster waehlt sie zusammen
    #: aus, statt nur den zuletzt angeklickten.
    mehrfach = QtCore.Signal(str, list)
    viele_bearbeiten = QtCore.Signal(str, list)   # (Art, [Namen]) - Sammelmaske
    viele_loeschen = QtCore.Signal(str, list)     # (Art, [Namen]) - auf einmal loeschen

    #: Zweige, unter denen sich per Rechtsklick ein neues Objekt anlegen laesst.
    #: „Stab“ ist seit 03.10.2026 der Stab im Sinn von RFEM (mit Nachweis), das
    #: FE-Element darunter heisst „Stabelement“ (Antwort 2 vom 24.09.2026).
    NEU_ARTEN = {"querschnitte": "Querschnitt", "subsysteme": "Subsystem",
                 "situationen": "Situation", "generierer": "Wasserdruck",
                 "layerliste": "Layer aus Auswahl", "unterlagen": "Skizze",
                 "knoten": "Knoten", "linien": "Linie", "stabelemente": "Stabelement",
                 "staebe": "Stab", "geoflaechen": "Fläche",
                 "geokoerper": "Volumen", "schweissnaehte": "Schweißnaht",
                 "bemassungen": "Linearmaß", "lastfaelle": "Lastfall",
                 "kombinationen": "Kombination", "ermuedungslasten": "Ermüdungslast",
                 "werkstoffe": "Werkstoff", "dicken": "Dicke",
                 "gelenke": "Gelenk", "stellungen": "Stellung",
                 "kontaktbedingungen": "Kontaktbedingung",
                 "lager": "Knotenlager", "linienlager": "Linienlager", "flaechenlager": "Flächenlager",
                 # seit 03.10.2026 (8b): die Anlegemaske nimmt die Ansicht erst mit OK auf
                 "bericht": "Berichtsbild"}
    #: Eintraege, die sich per Rechtsklick oder Entf loeschen lassen
    LOESCH_ARTEN = {"querschnitt", "knoten", "linie", "stabelement", "stab", "geoflaeche",
                    "geokoerper_einzeln", "subsystem", "layer", "unterlage", "situation", "wasserdruck", "wind",
                    "schweissnaht", "bemassung", "lastfall", "kombination", "ermuedungslast",
                    "werkstoff", "dicke",
                    "gelenk", "stellung", "berichtseintrag", "kontaktbedingung",
                    "lager_einzeln", "linienlager_einzeln", "flaechenlager_einzeln"}
    #: Eintragsart -> Zweigart (fuer "Neu" aus einem Eintrag heraus)
    ELTERNART = {"knoten": "knoten", "linie": "linien", "stabelement": "stabelemente",
                 "stab": "staebe", "geoflaeche": "geoflaechen",
                 "geokoerper_einzeln": "geokoerper", "querschnitt": "querschnitte",
                 "subsystem": "subsysteme", "situation": "situationen",
                 "layer": "layerliste", "unterlage": "unterlagen",
                 "wasserdruck": "generierer", "wind": "generierer",
                 "schweissnaht": "schweissnaehte", "bemassung": "bemassungen",
                 "lastfall": "lastfaelle", "kombination": "kombinationen",
                 "ermuedungslast": "ermuedungslasten",
                 "werkstoff": "werkstoffe", "dicke": "dicken",
                 "gelenk": "gelenke", "stellung": "stellungen", "berichtseintrag": "bericht",
                 "kontaktbedingung": "kontaktbedingungen",
                 "lager_einzeln": "lager", "linienlager_einzeln": "linienlager",
                 "flaechenlager_einzeln": "flaechenlager"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        self.setRootIsDecorated(True)
        # 10 statt 14 px seit 03.10.2026: die Gruppen (Teilpaket 8c) setzen
        # alles eine Ebene tiefer. Bei 1366 x 768 und 260 px Baum waren mit
        # 14 px 7 Zeilen abgeschnitten, mit 12 px 4, mit 10 px 2 - vor den
        # Gruppen 3 (gemessen, tests.test_fensteraufteilung)
        self.setIndentation(10)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        # Die zweite Spalte traegt Zusatzangaben (Anzahl, Koordinaten, Bezug).
        # Ohne Deckel frisst eine lange Angabe die ganze Breite und der Name in
        # Spalte 0 verschwindet - der Baum waere dann unlesbar.
        self.header().setMaximumSectionSize(120)
        self.setTextElideMode(QtCore.Qt.ElideRight)
        # Mehrfachauswahl: Strg nimmt einzelne dazu, Umschalt eine Strecke -
        # so, wie es die Tabellen unten schon koennen.
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.itemClicked.connect(self._klick)
        self.itemDoubleClicked.connect(self._doppelklick)
        self.itemSelectionChanged.connect(self._auswahl_geaendert)
        #: Hat _auswahl_geaendert fuer den laufenden Klick schon gemeldet?
        self._gemeldet = False
        #: Aufklappzustand ueber den **Pfad** der Zweige (:meth:`pfad_von`), nicht
        #: ueber ihren Text; er ueberlebt jeden Neuaufbau (:meth:`fuellen`) und
        #: wird nur von :meth:`zustand_vergessen` geleert
        self._offen: dict[tuple, bool] = {}
        #: Die Eintraege des laufenden Aufbaus, unter denen etwas haengen kann -
        #: nur sie werden beim naechsten Aufbau gemerkt (Zweige, Lastfaelle,
        #: Ergebnisgruppen), nie die bis zu 20 000 Zeilen einer Liste
        self._zweige: list = []
        #: Das Modell ist ein anderes: der naechste Aufbau beginnt im Grundzustand
        self._vergessen = False
        #: Rueckgaengig/Wiederholen: der naechste Aufbau behaelt Aufklappzustand
        #: und Rolle, aber nicht die Auswahl (die Ansicht leert ihre auch)
        self._auswahl_verwerfen = False
        #: Suchverzeichnis (Teilpaket 8d): (Art, Schluessel) -> Zeile, von
        #: :meth:`_zweig` beim Aufbau mitgebaut und mit ihm geleert. Bis zum
        #: 03.10.2026 ging :meth:`eintrag_waehlen` ueber alle Zeilen des Baums.
        self._verzeichnis: dict = {}
        #: Die nicht gezeigten Eintraege gekuerzter Listen: Art -> [_Rest]
        self._reste: dict = {}
        #: Der Filter in Kleinbuchstaben, "" = kein Filter (:meth:`filtern`)
        self._filter = ""
        #: die Zeile, die vor dem Filter oben stand (fuer das Aufheben)
        self._filter_oben = None
        #: Art -> Zweig (:meth:`_zweig_der_art`), je Aufbau beim ersten Bedarf
        self._zweig_je_art = None
        #: > 0, solange das Fenster ein Signal des Baums behandelt (ein Klick,
        #: eine Taste, ein Eintrag des Rechtsklickmenues): dann fuehrt nichts
        #: den Baum nach, die Zeile des Klicks bleibt (:meth:`meldet`, 8d G3)
        self._meldet = 0
        #: Texte der Zeilen, die das letzte Nachfuehren nicht markiert hat, weil
        #: der Filter sie ausblendet (:meth:`auswahl_nachfuehren`, 8d G1)
        self.ausgeblendet: list = []
        #: Die Filterzeile ueber dem Baum (:class:`Baumfilter` setzt sie)
        self.filterzeile = None

    #: Die Gruppen der obersten Ebene in dieser Folge, je (Kennung, Text)
    #: (Teilpaket 8c, 03.10.2026; Antworten 2 bis 4 des Anwenders vom
    #: 24.09.2026: nach Gruppen, Eigenschaften vor der Geometrie, Nachweise
    #: gebuendelt). Die Folge ist die des Ablaufs und die der Navigation in
    #: RFEM 6: dort beginnen die Basisobjekte mit Werkstoffen, Querschnitten und
    #: Dicken, auf die Staebe, Flaechen und Volumen verweisen; es folgen Lager
    #: und Gelenke, die Lastfaelle und Kombinationen, die Ergebnisse und zuletzt
    #: die Hilfsobjekte (Bemassungen, Objektselektionen = Layer). Das FE-Netz
    #: steht nach den Einwirkungen, weil in dieser Folge gearbeitet wird
    #: (Register Start: Lastfaelle, Vernetzen, Berechnen), die Stellungen danach,
    #: weil sie Teile des fertigen Modells ab- und zuschalten. Die Gruppen
    #: tragen die Art „modell“ und ihre Kennung (:meth:`pfad_von`); nur
    #: „Ergebnisse“ behaelt seine Art und damit seinen Pfad von vorher.
    GRUPPEN = (("eigenschaften", "Eigenschaften"), ("geometrie", "Geometrie"),
               ("lager_verbindungen", "Lager und Verbindungen"), ("einwirkungen", "Einwirkungen"),
               ("fe_netz", "FE-Netz"), ("systeme", "Systeme und Stellungen"),
               ("nachweise", "Nachweise"), ("ergebnisse", "Ergebnisse"),
               ("bericht_unterlagen", "Bericht und Unterlagen"), ("hilfsobjekte", "Hilfsobjekte"))
    #: Die Zweige der Gruppe „Systeme und Stellungen“ in dieser Folge: erst
    #: die Teile, dann die Lagen, dann die Situationen, die einer Stellung ihre
    #: Lastfaelle zuordnen. „detailmodelle“ ist der Platz fuer den Knoten
    #: „Detailmodelle (Volumen)“ (Vorgabe FCM-Volumenloeser, Abschnitt 15.1:
    #: „auf gleicher Ebene wie die Stellungen als Subsysteme“; Vertrag 10.4,
    #: gespeist aus DetailModelSpec). Gebaut wird er erst, wenn das Modell
    #: Detailmodelle kennt - Teilpaket 8c laesst nur den Platz (in
    #: :meth:`fuellen` zwischen Subsystemen und Stellungen).
    SYSTEM_ZWEIGE = ("subsysteme", "detailmodelle", "stellungen", "situationen")

    #: Grundzustand eines Modells: nur diese Zweige sind aufgeklappt (Pfade).
    #: Die Wurzel, damit man den Baum sieht; „Lager“ und „Stellungen“ waren im
    #: Quelltext schon immer als offen gedacht (``(lg, True)`` und
    #: ``st.setExpanded(True)``) und blieben es nur wegen der doppelt belegten
    #: Namen nicht (Teilpaket 8a, 02.10.2026). Seit 8c (03.10.2026) stehen sie
    #: in Gruppen; offen sind darum auch diese Gruppen und die Geometrie, deren
    #: Zweige bis dahin direkt unter der Wurzel zu sehen waren.
    GRUNDZUSTAND_OFFEN = frozenset({
        (("modell", ""),),
        (("modell", ""), ("modell", "geometrie")),
        (("modell", ""), ("modell", "lager_verbindungen")),
        (("modell", ""), ("modell", "lager_verbindungen"), ("lager", "")),
        (("modell", ""), ("modell", "systeme")),
        (("modell", ""), ("modell", "systeme"), ("stellungen", "")),
    })
    #: So viele gewaehlte Eintraege merkt der Baum ueber einen Neuaufbau; wer
    #: mehr gewaehlt hat (Strg+A in der Knotenliste), behaelt nur den aktuellen
    AUSWAHL_MAX = 200
    #: Arten, deren Schluessel die laufende Nummer ist: nach dem Loeschen ruecken
    #: die Nummern auf, und dieselbe Nummer meint ein anderes Objekt. Hat sich die
    #: Zahl der Eintraege der Liste geaendert, wird ihre Auswahl nicht
    #: wiederhergestellt (ein zweites Entf loeschte sonst die falschen).
    NUMMERIERT = frozenset({"knoten", "stabelement", "lager_einzeln", "linienlager_einzeln",
                            "flaechenlager_einzeln", "punktmasse", "daempfer", "starrkoerper",
                            "berichtseintrag"})

    @staticmethod
    def _schluessel(item) -> tuple[str, str]:
        art = str(item.data(0, QtCore.Qt.UserRole) or "")
        name = item.data(0, QtCore.Qt.UserRole + 1)
        return art, str(name if name is not None else item.text(0))

    @staticmethod
    def _ist_eintrag(item) -> bool:
        """Ein Eintrag meint ein einzelnes Objekt (traegt einen Schluessel);
        ein Zweig meint die Art."""
        return item is not None and item.data(0, QtCore.Qt.UserRole + 1) is not None

    #: Datenrolle der Zeilen, die fuer ihren Zweig stehen: die Sammelzeile
    #: „… N weitere“ und „noch nicht gerechnet“ (Teilpaket 8b). Ihr Klick
    #: meint den Zweig darueber.
    FUER_ZWEIG = QtCore.Qt.UserRole + 5
    #: Datenrolle der Gruppen (fett: die Wurzel und die Zweige, die nur
    #: Unterzweige zusammenfassen, :meth:`_zweig`)
    GRUPPE = QtCore.Qt.UserRole + 6

    @classmethod
    def ist_gruppe(cls, item) -> bool:
        """Fasst der Zweig nur Unterzweige zusammen (Gruppe, „Lager“,
        „Verbindungen“, „Kontaktbedingungen“, „Ergebnisse“)?"""
        return item is not None and bool(item.data(0, cls.GRUPPE))

    def zweig_finden(self, art: str, name: str = ""):
        """Der Zweig zu einem Zweigklick (Art, Name), sonst ``None``.

        Gesucht wird im aktuellen Eintrag (dem angeklickten), dann unter den
        Zweigen des letzten Aufbaus (``_zweige``, wenige hundert) und den
        Zeilen der Gruppen (die Zaehlzeile „Netzknoten“) - nie in den Zeilen
        der Listen, am Drehlager sind das Zehntausende. Eine Zeile, die fuer
        ihren Zweig steht (:attr:`FUER_ZWEIG`), meint den Zweig darueber.
        Passt kein Name (Aufruf ohne Namen), gilt der erste Zweig dieser Art,
        der keine Gruppe ist - „lager“ ist dann „Knotenlager“, nicht „Lager“.
        """
        ziel = (str(art), str(name))

        def fuer(it):
            return it.parent() if it.data(0, self.FUER_ZWEIG) and it.parent() is not None else it

        try:
            it = self.currentItem()
            if it is not None and self._schluessel(it) == ziel:
                return fuer(it)
            kandidaten = []
            for z in self._zweige:
                kandidaten.append(z)
                if self.ist_gruppe(z):
                    kandidaten += [z.child(i) for i in range(z.childCount())]
            for z in kandidaten:
                if self._schluessel(z) == ziel:
                    return fuer(z)
            gleich = [z for z in kandidaten if self._schluessel(z)[0] == ziel[0]
                      and not z.data(0, self.FUER_ZWEIG)]
            return next((z for z in gleich if not self.ist_gruppe(z)), gleich[0] if gleich else None)
        except RuntimeError:            # ein Eintrag war schon weg (Neuaufbau)
            return None

    def zeile_waehlen(self, item) -> None:
        """Eine Zeile waehlen und die Tastatur dorthin legen, ohne Signale -
        wie :meth:`eintrag_waehlen`, wenn die Zeile schon bekannt ist (Klick
        in die Liste einer Uebersicht, Teilpaket 8b)."""
        gesperrt = self.blockSignals(True)
        try:
            self.clearSelection()
            item.setSelected(True)
            self.setCurrentItem(item)
            self.scrollToItem(item)
        finally:
            self.blockSignals(gesperrt)
        self._gemeldet = False
        self.setFocus(QtCore.Qt.OtherFocusReason)

    def zeile_finden(self, art: str, name, nachladen: bool = True):
        """Die Zeile des Eintrags (Art, Schluessel), sonst ``None`` (8d).

        Gesucht wird im Suchverzeichnis, das der Aufbau mitbaut - ohne
        Schleife ueber die Zeilen. Steht der Eintrag hinter einer Sammelzeile
        „… N weitere“, wird seine Zeile vor ihr nachgeladen (``nachladen``)."""
        ziel = (str(art), str(name))
        it = self._verzeichnis.get(ziel)
        if it is not None:
            try:
                if it.treeWidget() is self:
                    return it
            except RuntimeError:            # die Zeile gibt es nicht mehr
                pass
            self._verzeichnis.pop(ziel, None)
        if nachladen:
            for rest in self._reste.get(ziel[0], ()):
                j = rest.stelle(ziel[1])
                if j is not None:
                    return self._nachladen(rest, j)
        return None

    def _nachladen(self, rest, j: int, vom_filter: bool = False):
        """Den Eintrag j hinter der Sammelzeile als Zeile vor sie setzen; sie
        zaehlt danach einen weniger. Nachgeladene Zeilen bleiben bis zum
        naechsten Aufbau (die des Filters bis zu seinem Aufheben). Sie stehen an
        ihrem Platz in der Folge der Liste, nicht in der Folge des Ladens (8d,
        Nachbesserung S3): K3 vor K10, auch wenn K10 zuerst kam."""
        e = rest.bauen(j)
        text, zahl, key, tip = e[:4]
        farbe = e[4] if len(e) > 4 else None
        vor, vor_j = rest.zeile, None
        for k, z in rest.geladen.items():
            jj = rest.stelle(k)
            if jj is not None and jj > j and (vor_j is None or jj < vor_j):
                vor, vor_j = z, jj
        it = self._zweig(rest.eltern, text, zahl, rest.art, schluessel=key, hinweis=tip,
                         farbe=farbe, blatt=True, vor=vor)
        rest.geladen[str(key)] = it
        if vom_filter:
            rest.vom_filter.add(str(key))
        elif self._filter:
            # waehrend eines Filters: ausgeblendet, wenn der Name nicht passt
            it.setHidden(self._filter not in str(text).lower())
            if not it.isHidden():
                p = it.parent()
                while p is not None:
                    p.setHidden(False)
                    p = p.parent()
        if not self._filter:
            self._rest_text(rest)
        return it

    @staticmethod
    def _rest_text(rest) -> None:
        """Die Sammelzeile ohne Filter: „… N weitere“, ohne Rest ausgeblendet."""
        n = rest.anzahl - len(rest.geladen)
        rest.zeile.setText(0, f"… {n} weitere")
        rest.zeile.setHidden(n <= 0)

    def _zeile_zu(self, alternativen):
        """Die erste vorhandene Zeile zu (Art, Schluessel)-Paaren; ein leerer
        Schluessel meint den Zweig der Art (:meth:`_zweig_der_art`)."""
        for art, key in alternativen:
            it = self._zweig_der_art(art) if str(key) == "" else self.zeile_finden(art, key)
            if it is not None:
                return it
        return None

    def _zweig_der_art(self, art: str):
        """Der Zweig einer Art wie :meth:`zweig_finden` ohne Namen: der erste,
        der keine Gruppe ist, sonst die erste Gruppe; Sammelzeilen nie. Das
        Verzeichnis entsteht beim ersten Aufruf nach einem Aufbau (eine Schleife
        ueber die Zweige, nie ueber die Listen); danach kostet ein Klick auf
        einen Netzknoten keine Schleife mehr (gemessen am Drehlager: 10 ms je
        Klick mit zweig_finden, 03.10.2026)."""
        je = self._zweig_je_art
        if je is None:
            kandidaten = []
            for z in self._zweige:
                kandidaten.append(z)
                if self.ist_gruppe(z):
                    kandidaten += [z.child(i) for i in range(z.childCount())]
            erste, gruppen = {}, {}
            for z in kandidaten:
                if z.data(0, self.FUER_ZWEIG):
                    continue
                (gruppen if self.ist_gruppe(z) else erste).setdefault(self._schluessel(z)[0], z)
            je = self._zweig_je_art = {**gruppen, **erste}
        it = je.get(str(art))
        try:
            return it if it is not None and it.treeWidget() is self else None
        except RuntimeError:            # ein Aufbau hat die Zeile schon freigegeben
            return None

    def auswahl_nachfuehren(self, ziele, aktuell=None) -> int:
        """Ansicht -> Baum (Teilpaket 8d, 03.10.2026; Plan vom 24.09.2026: „Eine
        Auswahl in der Ansicht markiert den Eintrag im Baum, ohne ihm die
        Tastatur zu geben“).

        ``ziele``: je gewaehltes Objekt die Zeilen, die es meinen koennen, als
        (Art, Schluessel)-Paare in dieser Folge - die erste vorhandene gilt
        (ein Netzknoten: sein Eintrag fehlt, also die Zaehlzeile
        „Netzknoten“). ``aktuell``: das zuletzt gewaehlte Objekt; seine Zeile
        wird die aktuelle und ins Bild geholt (aufgeklappt, gerollt). Die
        Zeilen werden markiert, ohne Signale - kein Klick im Baum, keine Maske,
        keine Leiste „Übernehmen | Verwerfen“ - und ohne die Tastatur zu
        nehmen. Mehr als :attr:`AUSWAHL_MAX` Objekte (ein Auswahlfenster ueber
        Tausende Knoten) markieren nichts. Rueckgabe: die Zahl der Zeilen.

        Der Baum wirkt nie auf etwas, das man nicht sieht (Nachbesserung 8d,
        G1): eine Zeile, die der Filter ausblendet, wird nicht markiert und
        nicht aktuell, ihr Text steht danach in :attr:`ausgeblendet` (das
        Fenster sagt es in der Statuszeile). Ist nichts zu markieren, hat der
        Baum keine aktuelle Zeile - auch nach „Auswahl aufheben“ und dem Klick
        ins Leere; bis dahin blieb die alte aktuelle Zeile, und Entf im Baum
        loeschte sie."""
        gefunden = {}

        def zu(alt):
            alt = tuple(tuple(x) for x in alt)
            if alt not in gefunden:
                gefunden[alt] = self._zeile_zu(alt)
            return gefunden[alt]

        zeilen, schon, verdeckt = [], set(), []
        cur = None
        if len(ziele) <= self.AUSWAHL_MAX:
            for alt in ziele:
                it = zu(alt)
                if it is None or id(it) in schon:
                    continue
                schon.add(id(it))
                if self._filter and not self._nicht_ausgeblendet(it):
                    verdeckt.append(it)
                    continue
                zeilen.append(it)
            cur = zu(aktuell) if aktuell else None
            if cur is not None and id(cur) not in schon:
                schon.add(id(cur))
                if self._filter and not self._nicht_ausgeblendet(cur):
                    verdeckt.append(cur)
                else:
                    zeilen.append(cur)
            if cur is not None and not any(z is cur for z in zeilen):
                cur = None              # ausgeblendet: nicht aktuell (G1)
            if cur is None and zeilen:
                cur = zeilen[-1]
        self.ausgeblendet = [it.text(0) for it in verdeckt]
        gesperrt = self.blockSignals(True)
        try:
            self.clearSelection()
            for it in zeilen:
                it.setSelected(True)
            if cur is not None:
                self.setCurrentItem(cur, 0, QtCore.QItemSelectionModel.NoUpdate)
                self.scrollToItem(cur)
            else:
                self.setCurrentItem(None)
        finally:
            self.blockSignals(gesperrt)
        self._gemeldet = False
        return len(zeilen)

    def meldet(self) -> bool:
        """Behandelt das Fenster gerade ein Signal des Baums (einen Klick, eine
        Taste, einen Eintrag des Rechtsklickmenues)?"""
        return self._meldet > 0

    @contextlib.contextmanager
    def klick_laeuft(self):
        """Solange der Block laeuft, gilt ein Klick im Baum als laufend (eine
        Zeile der Uebersicht waehlt ihre Baumzeile wie ein Klick, 8b)."""
        self._meldet += 1
        try:
            yield
        finally:
            self._meldet -= 1

    def als_klick(self, fn):
        """``fn`` spaeter so ausfuehren, als liefe der Klick im Baum noch -
        fuer den Wunsch, der an der Leiste „Übernehmen | Verwerfen“ wartet."""
        def lauf(*a, **k):
            with self.klick_laeuft():
                return fn(*a, **k)
        return lauf

    def _melden(self, signal, *werte) -> None:
        """Ein Signal des Baums senden; waehrend das Fenster es behandelt, gilt
        der Klick als laufend (:meth:`meldet`)."""
        self._meldet += 1
        try:
            signal.emit(*werte)
        finally:
            self._meldet -= 1

    def gruppe(self, kennung: str):
        """Die Gruppe der obersten Ebene mit dieser Kennung (:attr:`GRUPPEN`),
        sonst ``None``; „ergebnisse“ ist der Zweig der Ergebnisse."""
        wurzel = self.topLevelItem(0)
        for i in range(wurzel.childCount() if wurzel is not None else 0):
            k = wurzel.child(i)
            if self._element(k) == ("modell", kennung) or (
                    kennung == "ergebnisse" and self._element(k) == ("ergebnisse", "")):
                return k
        return None

    def gewaehlte_eintraege(self) -> tuple[str, list]:
        """(Art, [Namen]) der gewaehlten **Eintraege** einer gemeinsamen Art.

        Zweige (die nur eine Art meinen) zaehlen nicht mit, und Eintraege
        verschiedener Art auch nicht: „drei Flaechen" ist eine Auswahl, „eine
        Flaeche und ein Lastfall" ist keine. Massgebend ist die Art des zuletzt
        angeklickten Eintrags. Nur sichtbare Zeilen zaehlen (8d, G1): was der
        Filter ausblendet, bleibt gewaehlt, aber keine Taste und kein Menue
        wirkt darauf.
        """
        eintraege = [it for it in self.selectedItems() if self._ist_eintrag(it)
                     and (not self._filter or self._nicht_ausgeblendet(it))]
        if not eintraege:
            return "", []
        aktuell = self.currentItem()
        art = self._schluessel(aktuell)[0] if aktuell in eintraege \
            else self._schluessel(eintraege[-1])[0]
        namen = [self._schluessel(it)[1] for it in eintraege
                 if self._schluessel(it)[0] == art]
        return art, list(dict.fromkeys(namen))

    def mousePressEvent(self, ev):
        """Vor jedem Klick vergessen, was zuletzt gemeldet wurde.

        Damit unterscheidet :meth:`_klick` einen Klick, der die Auswahl
        **geaendert** hat (dann hat :meth:`_auswahl_geaendert` schon gemeldet),
        von einem erneuten Klick auf den bereits gewaehlten Eintrag - der soll
        seine Maske wieder oeffnen.
        """
        self._gemeldet = False
        super().mousePressEvent(ev)

    def _auswahl_geaendert(self) -> None:
        """Die Auswahl hat sich geaendert - hier laeuft alles zusammen.

        **Auch der einzelne Eintrag.** Sonst bewegen die Pfeiltasten zwar den
        aktuellen Eintrag - Qt tut das von selbst -, aber niemand erfaehrt
        davon: der Einzelfall haengt dann allein an ``itemClicked``, und den
        loest keine Taste aus. Genau daran liess sich der Baum nicht mit der
        Tastatur bedienen.

        Doppelmeldungen verhindert ``_gemeldet``: hat dieser Weg gemeldet,
        schweigt :meth:`_klick` fuer denselben Klick.
        """
        art, namen = self.gewaehlte_eintraege()
        if not art or not namen:
            return
        self._gemeldet = True
        if len(namen) > 1:
            self._melden(self.mehrfach, art, namen)
        else:
            self._melden(self.angeklickt, art, namen[0])

    def _klick(self, item, _spalte):
        """Klick, der die Auswahl nicht geaendert hat - derselbe Eintrag noch einmal."""
        if getattr(self, "_gemeldet", False):
            self._gemeldet = False
            return
        art, namen = self.gewaehlte_eintraege()
        if art and len(namen) > 1:
            return                      # _auswahl_geaendert hat schon gemeldet
        art, name = self._schluessel(item)
        if art:
            self._melden(self.angeklickt, art, name)

    def _alle_eintraege(self) -> list:
        """Alle Eintraege des Baums von oben nach unten - fuer Pos1 und Ende."""
        out = []

        def hinab(it):
            for i in range(it.childCount()):
                k = it.child(i)
                if self._ist_eintrag(k):
                    out.append(k)
                hinab(k)

        for i in range(self.topLevelItemCount()):
            w = self.topLevelItem(i)
            if self._ist_eintrag(w):
                out.append(w)
            hinab(w)
        return out

    def eintrag_waehlen(self, art: str, name) -> bool:
        """Den Eintrag (Art, Name) auswaehlen und den Fokus dorthin legen.

        Aufgerufen von „Im Baum zeigen“, nach dem Speichern einer Maske und aus
        der Liste einer Uebersicht: der Baum zieht nach, und die Tastatur landet
        dort, damit die Pfeiltasten gleich weiterschalten koennen. Die Signale
        sind dabei gesperrt - sonst schaukelte sich Ansicht -> Baum -> Ansicht
        auf. Ein Klick in der Ansicht nimmt :meth:`auswahl_nachfuehren`, das die
        Tastatur nicht nimmt.

        Gesucht wird seit 03.10.2026 im Suchverzeichnis (:meth:`zeile_finden`),
        auch hinter einer Sammelzeile; bis dahin ging eine Schleife ueber alle
        Eintraege des Baums (``_alle_eintraege``), und ein Eintrag hinter „… N
        weitere“ wurde nicht gefunden.
        """
        it = self.zeile_finden(art, name)
        if it is None:
            return False
        self.zeile_waehlen(it)
        return True

    def _menu(self, pos):
        """Rechtsklick: Neu am Zweig, Bearbeiten und Loeschen am Eintrag."""
        item = self.itemAt(pos)
        if item is None:
            return
        art, name = self._schluessel(item)
        menu = QtWidgets.QMenu(self)
        eintrag = self._ist_eintrag(item)
        zweigart = self.ELTERNART.get(art, art) if eintrag else art
        v_art, v_namen = self.gewaehlte_eintraege()
        if eintrag and v_art == art and len(v_namen) > 1:
            # Mehrere Eintraege gewaehlt: die Sammelbefehle stehen zuerst
            b = menu.addAction(f"Bearbeiten … ({len(v_namen)})")
            b.triggered.connect(lambda _c=False, a=v_art, n=list(v_namen):
                                self._melden(self.viele_bearbeiten, a, n))
            if art in self.LOESCH_ARTEN:
                d = menu.addAction(f"Löschen ({len(v_namen)}, Entf)")
                d.triggered.connect(lambda _c=False, a=v_art, n=list(v_namen):
                                    self._melden(self.viele_loeschen, a, n))
            menu.addSeparator()
        if zweigart in self.NEU_ARTEN:
            a = menu.addAction(f"Neu: {self.NEU_ARTEN[zweigart]} …")
            a.triggered.connect(lambda _c=False, z=zweigart: self._melden(self.neu, z))
        if eintrag and art in self.LOESCH_ARTEN:
            b = menu.addAction("Bearbeiten …")
            b.triggered.connect(lambda _c=False: self._melden(self.bearbeiten, art, name))
            menu.addSeparator()
            d = menu.addAction("Löschen (Entf)")
            d.triggered.connect(lambda _c=False: self._melden(self.loeschen, art, name))
        if menu.actions():
            menu.exec(self.viewport().mapToGlobal(pos))

    @staticmethod
    def _ist_strg_f(ev) -> bool:
        return ev.key() == QtCore.Qt.Key_F and ev.modifiers() == QtCore.Qt.ControlModifier

    def event(self, ev):
        """Strg+F gehoert dem Baum, solange er die Tastatur hat (8d): die
        Befehlssuche traegt es als Kuerzel fuer das ganze Programm, das den
        Tastendruck sonst verbraucht, bevor der Baum ihn sieht
        (``ShortcutOverride`` wie im Fenster der Tastenkuerzel)."""
        if (ev.type() == QtCore.QEvent.ShortcutOverride and self.filterzeile is not None
                and self._ist_strg_f(ev)):
            ev.accept()
            return True
        return super().event(ev)

    def keyPressEvent(self, ev):
        if self._ist_strg_f(ev) and self.filter_oeffnen():
            return
        if ev.key() in (QtCore.Qt.Key_Home, QtCore.Qt.Key_End):
            alle = self._alle_eintraege()
            if self._filter:
                alle = [i for i in alle if self._nicht_ausgeblendet(i)]
            if alle:
                self.setCurrentItem(alle[0] if ev.key() == QtCore.Qt.Key_Home else alle[-1])
                return
        if ev.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            it = self._tastenziel()
            if it is not None:
                art, name = self._schluessel(it)
                if art:
                    self._melden(self.bearbeiten, art, name)
                    return
        if ev.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            v_art, v_namen = self.gewaehlte_eintraege()
            if len(v_namen) > 1 and v_art in self.LOESCH_ARTEN:
                self._melden(self.viele_loeschen, v_art, v_namen)
                return
            item = self._tastenziel()
            if item is not None:
                art, name = self._schluessel(item)
                if art in self.LOESCH_ARTEN:
                    self._melden(self.loeschen, art, name)
                    return
        super().keyPressEvent(ev)

    def _tastenziel(self):
        """Die eine Zeile, auf die Entf oder die Eingabetaste wirkt (8d, G1):
        die aktuelle, wenn sie ein sichtbarer Eintrag ist, sonst der einzige
        sichtbare gewaehlte Eintrag - nie eine Zeile, die der Filter
        ausblendet. Bis zur Nachbesserung vom 03.10.2026 nahmen beide Tasten
        die aktuelle Zeile auch dann, wenn der Filter sie ausblendete: die
        Rueckfrage nannte S2, obwohl nur S1 zu sehen war."""
        cur = self.currentItem()
        if cur is not None and self._ist_eintrag(cur) and self._nicht_ausgeblendet(cur):
            return cur
        gew = [it for it in self.selectedItems() if self._ist_eintrag(it) and self._nicht_ausgeblendet(it)]
        return gew[0] if len(gew) == 1 else None

    def _doppelklick(self, item, _spalte):
        art, name = self._schluessel(item)
        if art:
            self._melden(self.bearbeiten, art, name)

    # -- Zustand: Aufklappen, Rollposition, gewaehlter Eintrag --------------
    @staticmethod
    def _element(item) -> tuple[str, str]:
        """Art und Kennung eines Eintrags: der Schluessel, bei einem Zweig
        seine feste Kennung (``kennung`` in :meth:`_zweig`), sonst leer."""
        art = str(item.data(0, QtCore.Qt.UserRole) or "")
        key = item.data(0, QtCore.Qt.UserRole + 1)
        if key is None:
            key = item.data(0, QtCore.Qt.UserRole + 2)
        return art, ("" if key is None else str(key))

    @classmethod
    def pfad_von(cls, item) -> tuple:
        """Der Pfad eines Eintrags von der Wurzel an: je Stufe (Art, Kennung).

        Er ist der Schluessel des Aufklappzustands. Der angezeigte Text taugt
        dafuer nicht: er traegt den Modellnamen (die Wurzel), Zusaetze wie „○“
        und „⚠“ und kommt mehrfach vor („Lastfälle“ und „Kombinationen“ stehen
        unter „Einwirkungen“ und unter „Ergebnisse“).
        """
        teile = []
        while item is not None:
            teile.append(cls._element(item))
            item = item.parent()
        teile.reverse()
        return tuple(teile)

    @staticmethod
    def _stand(item) -> str:
        """Der Zaehler einer Liste fuer :meth:`_auffinden`: ein eigener Stand
        (``stand`` in :meth:`_zweig`), sonst der Zusatz in Spalte 1. Der Zweig
        „Knoten“ zeigt seit 03.10.2026 nur die Konstruktionsknoten; sein Stand
        nennt auch die Zahl aller Knoten, weil die Nummern beim Loeschen eines
        Netzknotens ebenso aufruecken."""
        v = item.data(0, QtCore.Qt.UserRole + 4)
        return str(v) if v is not None else item.text(1)

    def _ort(self, item) -> tuple:
        """(Pfad des Elternteils, Art und Kennung, Stelle unter dem Elternteil,
        Zaehler des Elternteils): wiederzufinden, ohne die Kinder durchzugehen
        (die Stelle wird zuerst geprueft). Der Zaehler (:meth:`_stand`, meist
        Spalte 1 des Zweigs, die Zahl der Objekte, nicht der Zeilen) zeigt bei
        nummerierten Arten, ob sich die Liste geaendert hat."""
        eltern = item.parent()
        if eltern is None:
            return (), self._element(item), 0, ""
        return (self.pfad_von(eltern), self._element(item), eltern.indexOfChild(item),
                self._stand(eltern))

    def _auffinden(self, ort: tuple, verzeichnis: dict, naechster: bool = False,
                   pruefen: bool = True, nachladen: bool = False):
        """Den Eintrag zu einem Ort im neuen Baum, sonst ``None``.

        Zweige stehen im Verzeichnis. Ein Eintrag in einer Liste wird zuerst an
        seiner alten Stelle gesucht, dann im Suchverzeichnis (8d), dann in der
        Umgebung der Stelle; nur in kurzen Listen geht die Suche ueber alle (am
        Drehlager hat „Knoten“ 20 000 Eintraege). ``naechster``: ist er weg, der
        Eintrag an seiner Stelle. ``pruefen``: bei nummerierten Arten
        (:attr:`NUMMERIERT`) nichts finden, wenn sich der Zaehler der Liste
        geaendert hat; fuer die Rollposition gilt das nicht, sie braucht nur die
        Stelle. ``nachladen``: ein Eintrag hinter der Sammelzeile (eine
        nachgeladene Zeile war gewaehlt) wird wieder nachgeladen.
        """
        eltern_pfad, element, nr, zaehler = ort
        zweig = verzeichnis.get(eltern_pfad + (element,))
        if zweig is not None:
            return zweig
        eltern = verzeichnis.get(eltern_pfad)
        if eltern is None:
            return None
        if pruefen and element[0] in self.NUMMERIERT and self._stand(eltern) != zaehler:
            return None
        n = eltern.childCount()
        if 0 <= nr < n and self._element(eltern.child(nr)) == element:
            return eltern.child(nr)
        k = self._verzeichnis.get(element)
        if k is not None and k.parent() is eltern:
            return k
        if nachladen and k is None:
            for rest in self._reste.get(element[0], ()):
                j = rest.stelle(element[1]) if rest.eltern is eltern else None
                if j is not None:
                    return self._nachladen(rest, j)
        suche = list(range(max(0, nr - 50), min(n, nr + 51)))
        if n <= 2000:
            suche += list(range(n))
        for i in suche:
            k = eltern.child(i)
            if self._element(k) == element:
                return k
        return eltern.child(min(max(nr, 0), n - 1)) if naechster and n else None

    def zustand_vergessen(self) -> None:
        """Das Modell ist ein anderes (Neu, Öffnen, Beispiel, Import): der
        naechste Aufbau beginnt im Grundzustand - Aufklappzustand, gewaehlter
        Eintrag und Rollposition des vorigen Modells gelten nicht mehr. Ein
        Filter auch nicht (8d): er ueberlebt jeden Neuaufbau desselben Modells,
        ein anderes Modell beginnt ohne."""
        if self._filter:
            self.filtern("")
        z = self.filterzeile
        if z is not None:
            if callable(getattr(z, "anhalten", None)):
                z.anhalten()
            gesperrt = z.blockSignals(True)
            z.clear()
            z.blockSignals(gesperrt)
            z.hide()
        self._offen.clear()
        self._vergessen = True

    def auswahl_vergessen(self) -> None:
        """Rueckgaengig und Wiederholen: der naechste Aufbau behaelt
        Aufklappzustand und Rolle, aber nicht die Auswahl. Die Ansicht leert
        ihre Auswahl dabei (``_objektauswahl_leeren``); der Baum darf nicht
        auf Objekten markiert bleiben, die dort nicht mehr gewaehlt sind."""
        self._auswahl_verwerfen = True

    def _ansicht_merken(self):
        """Vor dem Neuaufbau: Aufklappzustand, Auswahl und Rollposition.

        Gemerkt wird nur an den Eintraegen, unter denen etwas haengen kann
        (``_zweige``, wenige Dutzend bis einige hundert) - nie ueber die Zeilen
        der Listen. Am Drehlager hat der Zweig „Knoten“ 20 000 Eintraege, und
        die Schleife ueber alle Kinder lief bei jedem Neuaufbau.
        Gibt Auswahl und Anker zurueck, ``None`` nach :meth:`zustand_vergessen`.
        """
        if self._vergessen:
            self._vergessen = False
            self._offen.clear()
            return None
        try:
            if not self._filter:
                # mit Filter gilt der Aufklappzustand von vor dem Filter (8d):
                # was der Filter aufgeklappt hat, merkt sich der Baum nicht
                self._offen_merken()
            gewaehlt = self.selectedItems()
            aktuell = self.currentItem()
            if len(gewaehlt) > self.AUSWAHL_MAX:
                gewaehlt = [aktuell] if aktuell is not None else []
            anker = None
            if self.verticalScrollBar().value() > 0:
                oben = self.itemAt(2, 2)
                if oben is not None:
                    anker = self._ort(oben)
            if self._auswahl_verwerfen:
                self._auswahl_verwerfen = False
                gewaehlt, aktuell = [], None
            return {"auswahl": [self._ort(i) for i in gewaehlt],
                    "aktuell": self._ort(aktuell) if aktuell is not None else None,
                    "anker": anker}
        except RuntimeError:            # ein Eintrag war schon weg (Aufbau abgebrochen)
            return None

    def _offen_merken(self) -> None:
        """Den Aufklappzustand der Zweige des laufenden Aufbaus merken - nur
        an ``_zweige``, nie ueber die Zeilen der Listen."""
        for it in self._zweige:
            if it.childCount():
                self._offen[self.pfad_von(it)] = it.isExpanded()

    def _ansicht_herstellen(self, ansicht) -> None:
        """Nach dem Neuaufbau: aufklappen, auswaehlen, rollen - in dieser
        Reihenfolge, denn das Rollen braucht die aufgeklappten Zeilen.

        Die Signale schweigen: eine wiederhergestellte Auswahl ist keine neue
        und soll keine Maske oeffnen. Das Selbstrollen der Ansicht ist aus,
        sonst klappt ``setCurrentItem`` die Eltern wieder auf.
        """
        verzeichnis = {self.pfad_von(it): it for it in self._zweige}
        for pfad, it in verzeichnis.items():
            offen = self._offen.get(pfad)
            if offen is None:
                offen = pfad in self.GRUNDZUSTAND_OFFEN
            if offen and it.childCount():
                it.setExpanded(True)
        if self._filter:
            # der Filter ueberlebt den Neuaufbau (8d); er wirkt vor Auswahl und
            # Rolle, damit die Rolle auf den sichtbaren Zeilen steht
            self._filter_anwenden()
        if ansicht is None:
            self.scrollToTop()
            return
        gesperrt = self.blockSignals(True)
        auto = self.hasAutoScroll()
        self.setAutoScroll(False)
        try:
            for ort in ansicht["auswahl"]:
                it = self._auffinden(ort, verzeichnis, nachladen=True)
                if it is not None:
                    it.setSelected(True)
            aktuell = (self._auffinden(ansicht["aktuell"], verzeichnis, nachladen=True)
                       if ansicht["aktuell"] is not None else None)
            if aktuell is not None:
                self.setCurrentItem(aktuell, 0, QtCore.QItemSelectionModel.NoUpdate)
            if self._filter:
                self._aktuelle_sichtbar_halten()
        finally:
            self.setAutoScroll(auto)
            self.blockSignals(gesperrt)
        self._gemeldet = False
        if ansicht["anker"] is not None:
            ziel = self._auffinden(ansicht["anker"], verzeichnis, naechster=True, pruefen=False)
            if ziel is not None:
                self.scrollToItem(ziel, QtWidgets.QAbstractItemView.PositionAtTop)

    def _zweig(self, eltern, text, zahl="", art="", fett=False, farbe=None,
               schluessel=None, hinweis="", kennung=None, blatt=False, stand=None, vor=None):
        """Einen Eintrag anlegen.

        Schriftregel (02.10.2026): **grau = leer** (Zaehler 0), **normal =
        gefuellt**, **fett nur fuer Gruppen** (``fett``: die Wurzel und die
        Zweige, die nur Unterzweige zusammenfassen). Eine ausdrueckliche
        ``farbe`` (Warnung, „+ … anlegen“) geht vor.

        Ein Zweig mit Zaehler 0 hat seit 03.10.2026 keinen gefuellten
        Unterzweig mehr: die FE-Elemente stehen unter „FE-Netz“, die
        Schweissnaehte unter „Nachweise“, und die Zaehler von Lager,
        Verbindungen und Kontaktbedingungen schliessen ihre Unterzweige ein.
        Bis dahin setzte hier ein eigener Zweig die Zweige ueber einem
        gefuellten Unterzweig wieder in die Normalfarbe („Volumen 0“ ueber
        „Volumenelemente 960“); test_baum_ruhig.test_grau_nur_wenn_der_zweig_leer_ist
        haelt fest, dass es den Fall nicht mehr gibt.

        ``kennung``: feste Kennung eines Zweigs, wo Art und Elternpfad ihn nicht
        eindeutig machen (:meth:`pfad_von`). ``blatt``: der Eintrag bekommt nie
        Kinder (Zeilen der Listen) und wird nicht fuer den Aufklappzustand
        vorgemerkt. ``stand``: der Zaehler der Liste fuer die Auswahl nach
        einem Neuaufbau, wenn ihn ``zahl`` nicht ganz sagt (:meth:`_stand`).
        ``vor``: die Zeile vor diese Zeile von ``eltern`` setzen (eine
        nachgeladene Zeile vor die Sammelzeile, 8d).

        Jeder Eintrag mit Schluessel kommt ins Suchverzeichnis (8d); kommt
        derselbe Schluessel zweimal vor, gilt der erste.
        """
        if vor is None:
            it = QtWidgets.QTreeWidgetItem(eltern, [text, str(zahl)])
        else:
            it = QtWidgets.QTreeWidgetItem([text, str(zahl)])
            eltern.insertChild(eltern.indexOfChild(vor), it)
        it.setData(0, QtCore.Qt.UserRole, art)
        if stand is not None:
            it.setData(0, QtCore.Qt.UserRole + 4, str(stand))
        if schluessel is not None:
            it.setData(0, QtCore.Qt.UserRole + 1, str(schluessel))
            self._verzeichnis.setdefault((str(art), str(schluessel)), it)
        elif kennung is not None:
            it.setData(0, QtCore.Qt.UserRole + 2, str(kennung))
        if not blatt:
            self._zweige.append(it)
        if fett:
            f = it.font(0)
            f.setBold(True)
            it.setFont(0, f)
            it.setData(0, self.GRUPPE, True)
        it.setForeground(1, QtGui.QColor(FARBEN["matt"]))
        if farbe is None and schluessel is None and str(zahl) == "0":
            farbe = FARBEN["matt"]
        if farbe:
            it.setForeground(0, QtGui.QColor(farbe))
        if hinweis:
            it.setToolTip(0, hinweis)
        if str(zahl):
            # Spalte 1 ist auf 120 px gedeckelt und wird mit … gekuerzt - wer
            # den Zusatz ueberfaehrt, liest ihn ganz (24.09.2026: die
            # Erklaerung an grauen phi-Eintraegen war sonst nicht zu lesen)
            it.setToolTip(1, str(zahl))
        return it

    def _liste(self, eltern, eintraege, art, sammelart="", sortieren=True, gesamt=None,
               rest=None):
        """Eintraege unter einen Zweig haengen, gedeckelt auf BAUM_MAX.

        ``gesamt``: so viele Eintraege gibt es wirklich, wenn der Aufrufer nur
        die ersten BAUM_MAX + 1 gebaut hat - die Sammelzeile nennt dann den
        Rest der ganzen Liste, und ``rest`` (Schluessel, Name, Zeile, wie in
        :class:`_Rest`) beschreibt die Eintraege ab BAUM_MAX. Sonst sind sie
        die Eintraege der Liste selbst. Ansicht und Filter finden sie so auch
        hinter der Sammelzeile (8d).

        Sortiert wird nach dem Schluessel des Eintrags, und zwar **natuerlich**
        (:func:`natuerlich`): „V2“ steht vor „V10“, nicht dahinter. Das ist
        nicht nur Schoenheit - die Liste ist auf BAUM_MAX Eintraege gedeckelt,
        und in einer alphabetisch sortierten Liste waere schon der abgeschnittene
        Rest ein anderer. Wo die Reihenfolge selbst eine Aussage ist
        (Ergebnisse, Berichtsbilder), schaltet ``sortieren=False`` sie ab.
        """
        if sortieren:
            eintraege = sorted(eintraege, key=lambda e: natuerlich(e[2]))
        anzahl = len(eintraege) if gesamt is None else int(gesamt)
        for i, e in enumerate(eintraege):
            # ein fuenfter Wert ist die Textfarbe (Kontakte: die Wirkung)
            text, zahl, key, tip = e[:4]
            farbe = e[4] if len(e) > 4 else None
            if i >= BAUM_MAX:
                # steht fuer den Zweig: ihr Klick zeigt dessen Uebersicht (8b)
                z = self._zweig(eltern, f"… {anzahl - BAUM_MAX} weitere",
                                "", sammelart or art, farbe=FARBEN["matt"], blatt=True,
                                hinweis="Die vollständige Liste steht in der "
                                        "Tabelle unten – dort mit Filter.")
                z.setData(0, self.FUER_ZWEIG, True)
                if rest is None:
                    hinten = eintraege[BAUM_MAX:]
                    rest = (lambda h=hinten: [x[2] for x in h], lambda j, h=hinten: h[j][0],
                            lambda j, h=hinten: h[j])
                self._reste.setdefault(art, []).append(
                    _Rest(eltern, z, art, anzahl - BAUM_MAX, *rest))
                break
            self._zweig(eltern, text, zahl, art, schluessel=key, hinweis=tip, farbe=farbe,
                        blatt=True)

    def ergebnisse_nachziehen(self, ergebnisse: dict) -> bool:
        """Nach einem Ergebniswechsel nur die Zusaetze (Spalte 1), Hinweise
        und Farben der Ergebniseintraege neu setzen, ohne den Baum neu
        aufzubauen.

        Das geht nur, wenn Gruppen und Schluessel dieselben geblieben sind
        (etwa Umhuellende -> Lastfall: „Verformungen“ und „Schnittgrößen“
        bleiben, ihre Werte nicht). Sonst ``False`` - dann baut der Aufrufer
        den Baum neu (:meth:`fuellen`). Befund 24.09.2026: der Zusatz blieb
        beim alten Ergebnis stehen.
        """
        ew = None
        for i in range(self.topLevelItemCount()):
            w = self.topLevelItem(i)
            for j in range(w.childCount()):
                if w.child(j).data(0, QtCore.Qt.UserRole) == "ergebnisse":
                    ew = w.child(j)
        if ew is None:
            return False
        erg = {k: v for k, v in (ergebnisse or {}).items() if v}
        gruppen = [ew.child(i) for i in range(ew.childCount())
                   if ew.child(i).data(0, QtCore.Qt.UserRole) == "ergebnisgruppe"]
        if [g.text(0) for g in gruppen] != list(erg):
            return False
        paare = []
        for g in gruppen:
            eintraege = erg[g.text(0)]
            kinder = [g.child(i) for i in range(g.childCount()) if self._ist_eintrag(g.child(i))]
            if g.text(1) != str(len(eintraege)) or                     [k.data(0, QtCore.Qt.UserRole + 1) for k in kinder]                     != [str(e[2]) for e in eintraege[:BAUM_MAX]]:
                return False
            paare.extend(zip(kinder, eintraege))
        for it, e in paare:
            # wie fuellen: ein vierter Wert ist die Textfarbe (grau), der
            # Zusatz steht dann auch im Hinweis
            zusatz, tip = str(e[1]), (e[1] if len(e) > 3 else e[0])
            it.setText(1, zusatz)
            it.setToolTip(0, tip)
            it.setToolTip(1, zusatz)
            if len(e) > 3 and e[3]:
                it.setForeground(0, QtGui.QColor(e[3]))
            else:
                it.setData(0, QtCore.Qt.ForegroundRole, None)
        return True

    # -- Filter (Teilpaket 8d, 03.10.2026) -----------------------------------
    #: So viele Treffer laedt der Filter je gekuerzter Liste hinter der
    #: Sammelzeile nach; den Rest nennt sie („… N weitere Treffer“)
    FILTER_MAX = 500

    def filter_aktiv(self) -> bool:
        return bool(self._filter)

    def filtern(self, text: str) -> None:
        """Die Zeilen nach dem Namen filtern: Teiltext, Gross- und
        Kleinschreibung gleich. Treffer sind Eintraege und Zweige, nie die
        Wurzel (Modellname) und die Gruppen der obersten Ebene - sie bleiben
        nur als Eltern von Treffern sichtbar und klappen dann auf. Ein Zweig,
        dessen Name passt, bleibt sichtbar und zugeklappt mit seiner Zahl;
        darunter bleiben nur Eintraege, die selbst passen (Nachbesserung 8d,
        G2; bis dahin zeigte ein passender Name alles darunter, und „modell“
        oder „e“ blendeten ueber Wurzel und Gruppen nichts aus). Hinter einer
        Sammelzeile „… N weitere“ sucht der Filter mit und laedt die Treffer
        nach - alle, wenn es hoechstens :attr:`FILTER_MAX` sind, sonst keinen
        (die Sammelzeile nennt sie). Ein leerer Text hebt den Filter auf und
        stellt den Aufklappzustand von davor wieder her. Der Filter ueberlebt
        jeden Neuaufbau (:meth:`fuellen`)."""
        such = str(text or "").strip().lower()
        if such == self._filter:
            return
        if such and not self._filter:
            # Beginn: Aufklappzustand und die oberste Zeile merken
            try:
                self._offen_merken()
                self._filter_oben = self.itemAt(2, 2)
            except RuntimeError:
                self._filter_oben = None
        self._filter = such
        if such:
            self._filter_anwenden()
        else:
            self._filter_aufheben()

    def _alle_reste(self) -> list:
        return [r for reste in self._reste.values() for r in reste]

    def _filter_anwenden(self) -> None:
        such = self._filter
        reste = self._alle_reste()
        self._rest_je_zeile = {id(r.zeile): r for r in reste}
        self.setUpdatesEnabled(False)
        try:
            for rest in reste:
                # was ein frueherer Filtertext nachgeladen hat und nicht mehr
                # passt, geht wieder (sonst fuellte „K“ das Kontingent fuer „K12“)
                self._rest_raeumen(rest, such)
                # Treffer hinter der Sammelzeile: alle nachladen, wenn es
                # hoechstens FILTER_MAX sind, sonst keinen - „k“ laedt bei 21 000
                # Knoten keine 500 nach (Nachbesserung 8d, D7)
                neu = [j for j in rest.treffer(such) if rest.schluessel(j) not in rest.geladen]
                if len(rest.vom_filter) + len(neu) <= self.FILTER_MAX:
                    for j in neu:
                        self._nachladen(rest, j, vom_filter=True)
                    rest.treffer_offen = 0
                else:
                    rest.treffer_offen = len(neu)
                if rest.treffer_offen:
                    rest.zeile.setText(0, f"… {rest.treffer_offen} weitere Treffer")
            for i in range(self.topLevelItemCount()):
                self._filter_zeile(self.topLevelItem(i), such, 0)
            self._aktuelle_sichtbar_halten()
        finally:
            self.setUpdatesEnabled(True)

    def _filter_zeile(self, it, such: str, ebene: int) -> bool:
        """Eine Zeile und alles darunter filtern; True, wenn sie sichtbar
        bleibt. Treffer ist eine Zeile ab der Ebene 2, deren Name passt: die
        Wurzel (0) und die Gruppen (1) nie, Sammelzeilen nie - die Sammelzeile
        einer Liste bleibt, solange hinter ihr Treffer warten. Ein Zweig, der
        selbst passt, bleibt zu; ein Zweig mit Treffern darunter klappt auf."""
        selbst = ebene >= 2 and such in it.text(0).lower() and not it.data(0, self.FUER_ZWEIG)
        darunter = False
        for j in range(it.childCount()):
            if self._filter_zeile(it.child(j), such, ebene + 1):
                darunter = True
        rest = self._rest_je_zeile.get(id(it))
        if rest is not None and rest.treffer_offen:
            darunter = True
        if selbst:
            if it.childCount():
                it.setExpanded(False)
        elif darunter and it.childCount():
            it.setExpanded(True)
        it.setHidden(not (selbst or darunter))
        return selbst or darunter

    def _aktuelle_sichtbar_halten(self) -> None:
        """Keine ausgeblendete aktuelle Zeile (8d, G1): blendet der Filter sie
        aus, wird die erste sichtbare gewaehlte Zeile aktuell, sonst gar keine -
        ohne Signale."""
        cur = self.currentItem()
        if cur is None or self._nicht_ausgeblendet(cur):
            return
        sichtbar = [it for it in self.selectedItems() if self._nicht_ausgeblendet(it)]
        gesperrt = self.blockSignals(True)
        try:
            if sichtbar:
                self.setCurrentItem(sichtbar[0], 0, QtCore.QItemSelectionModel.NoUpdate)
            else:
                self.setCurrentItem(None)
        finally:
            self.blockSignals(gesperrt)

    def erster_treffer(self):
        """Die erste sichtbare Trefferzeile in der Folge des Baums (Pfeil nach
        unten aus der Filterzeile), sonst ``None``."""
        such = self._filter
        if not such:
            return None

        def hinab(it, ebene):
            if it.isHidden():
                return None
            if ebene >= 2 and such in it.text(0).lower() and not it.data(0, self.FUER_ZWEIG):
                return it
            for j in range(it.childCount()):
                t = hinab(it.child(j), ebene + 1)
                if t is not None:
                    return t
            return None
        for i in range(self.topLevelItemCount()):
            t = hinab(self.topLevelItem(i), 0)
            if t is not None:
                return t
        return None

    def _zeigen(self, it) -> None:
        """Eine Zeile und alles darunter wieder zeigen."""
        it.setHidden(False)
        for j in range(it.childCount()):
            self._zeigen(it.child(j))

    def _nicht_ausgeblendet(self, it) -> bool:
        while it is not None:
            if it.isHidden():
                return False
            it = it.parent()
        return True

    def _filter_aufheben(self) -> None:
        """Alles zeigen, die nachgeladenen Treffer wieder heraus (ausser
        gewaehlte), den Aufklappzustand von vor dem Filter herstellen und
        dorthin rollen, wo der Baum vorher stand."""
        aktuell = self.currentItem()
        self.setUpdatesEnabled(False)
        try:
            for rest in self._alle_reste():
                self._rest_raeumen(rest)
                rest.treffer_offen = 0
            for i in range(self.topLevelItemCount()):
                self._zeigen(self.topLevelItem(i))
            for rest in self._alle_reste():
                self._rest_text(rest)
            for it in self._zweige:
                if it.childCount():
                    pfad = self.pfad_von(it)
                    offen = self._offen.get(pfad)
                    if offen is None:
                        offen = pfad in self.GRUNDZUSTAND_OFFEN
                    it.setExpanded(bool(offen))
        finally:
            self.setUpdatesEnabled(True)
        oben, self._filter_oben = self._filter_oben, None
        try:
            if aktuell is not None and aktuell.isSelected():
                # die gewaehlte Zeile ist sichtbar, auch wenn ihr Zweig vor dem
                # Filter zu war (Nachbesserung 8d, S4): scrollToItem klappt auf
                self.scrollToItem(aktuell)
            elif oben is not None and oben.treeWidget() is self and self._ganz_offen(oben):
                self.scrollToItem(oben, QtWidgets.QAbstractItemView.PositionAtTop)
        except RuntimeError:            # die Zeile gab ein Neuaufbau schon frei
            pass

    def _rest_raeumen(self, rest, such=None) -> None:
        """Die vom Filter nachgeladenen Zeilen wieder herausnehmen - mit
        ``such`` nur die, deren Name nicht mehr passt. Gewaehlte Zeilen und die
        aktuelle bleiben als gewoehnlich nachgeladene bis zum naechsten Aufbau."""
        aktuell = self.currentItem()
        for key in list(rest.vom_filter):
            it = rest.geladen.get(key)
            if it is not None and such is not None and such in it.text(0).lower():
                continue
            rest.vom_filter.discard(key)
            if it is None or it.isSelected() or it is aktuell:
                continue
            rest.eltern.removeChild(it)      # gehoert danach Python und geht mit der letzten Referenz
            del rest.geladen[key]
            if self._verzeichnis.get((rest.art, key)) is it:
                del self._verzeichnis[(rest.art, key)]

    @staticmethod
    def _ganz_offen(it) -> bool:
        """Sind alle Eltern der Zeile aufgeklappt (sie steht im Baum)?"""
        p = it.parent()
        while p is not None:
            if not p.isExpanded():
                return False
            p = p.parent()
        return True

    def filter_oeffnen(self) -> bool:
        """Strg+F im Baum: die Filterzeile zeigen und den Cursor hineinsetzen;
        was darin steht, ist markiert."""
        z = self.filterzeile
        if z is None:
            return False
        z.show()
        z.setFocus(QtCore.Qt.ShortcutFocusReason)
        z.selectAll()
        return True

    def filter_schliessen(self) -> None:
        """Esc in der Filterzeile: Filter aufheben, Zeile zu, Tastatur in den Baum."""
        z = self.filterzeile
        if z is not None:
            gesperrt = z.blockSignals(True)
            z.clear()
            z.blockSignals(gesperrt)
            z.hide()
        self.filtern("")
        self.setFocus(QtCore.Qt.OtherFocusReason)

    # -- Beschriftungen ---------------------------------------------------
    @staticmethod
    def _lagertext(support) -> str:
        namen = ["ux", "uy", "uz", "φx", "φy", "φz"]
        teile = []
        for d in range(6):
            b = support.dof_behaviour(d)
            if getattr(b, "acts", False):
                teile.append(namen[d])
        return ", ".join(teile) or "frei"

    @staticmethod
    def _koerperzeile(name: str, x) -> tuple:
        """Die Zeile eines Volumens: (Text, Zusatz, Schluessel, Hinweis, Farbe).

        Der Grund, warum ein Koerper kein Netz hat, steht in ``netzgrund`` (vom
        Vernetzer gesetzt):

        * ``""`` - nie versucht: vor dem Vernetzen der Normalfall, nur ein „○“;
        * ``"kein_volumen"`` - er kann keines bekommen (Hilfskoerper, in RFEM
          Null-Volumen): grau, ohne Warnzeichen, er traegt nichts und fehlt nicht;
        * ``"abgebrochen"``, ``"gescheitert"``, ``"vernetzer_aus"`` - es haette
          eines geben muessen: ⚠ vor dem Namen (hinten ginge es mit dem „…“ der
          Spalte verloren), Warnfarbe und der Grund im Hinweis.
        """
        bezug = x.bezug()
        if x.elemente:
            return name, bezug, name, f"{name}: {bezug}", None
        from ..model import OHNE_NETZ
        grund = str(getattr(x, "netzgrund", "") or "")
        kom = str(getattr(x, "kommentar", "") or "")
        if grund == "kein_volumen" or (not grund and kom.startswith(f"{OHNE_NETZ} kein Rauminhalt")):
            rest = kom[len(OHNE_NETZ):].strip() if kom.startswith(OHNE_NETZ) else ""
            return (name, bezug, name,
                    f"{name}: {bezug}\nHilfskörper ohne Rauminhalt: bekommt kein Netz und trägt "
                    "nichts." + (f"\n{rest}" if rest else ""),
                    FARBEN["matt"])
        if grund:
            from ..diagnose import _netzgrund_text
            return ("⚠ " + name, bezug, name,
                    f"{name}: {bezug}\n⚠ Kein Netz: {_netzgrund_text(x)}.\n"
                    "Das Volumen trägt nichts, solange es kein Netz hat.",
                    FARBEN["warn"])
        return name + " ○", bezug, name, f"{name}: {bezug}\nnoch nicht vernetzt", None

    def fuellen(self, model, stellungen: list = None, ergebnisse: dict = None):
        """Den Baum aus dem Modell neu aufbauen.

        Aufklappzustand, gewaehlter Eintrag und Rollposition bleiben erhalten
        (:meth:`_ansicht_merken`, :meth:`_ansicht_herstellen`), es sei denn, der
        Aufrufer hat :meth:`zustand_vergessen` gerufen, weil das Modell ein
        anderes ist. Bis zum 02.10.2026 merkte sich der Baum den Zustand ueber
        den Text jedes Eintrags, ging dafuer ueber alle Kinder und stellte nur
        acht Zweige wieder her - ein neues Modell erbte ihn dabei, soweit die
        Texte gleich waren.

        Gegliedert ist der Baum nach :attr:`GRUPPEN` (Teilpaket 8c,
        03.10.2026): die Gruppen entstehen zuerst in ihrer Folge, dann werden
        sie gefuellt. Bis dahin hingen Knoten, Linien, Staebe, Flaechen,
        Volumen, Bemassungen, Lager, Gelenke, Stellungen und die
        Nachweisobjekte einzeln an der Wurzel, die FE-Elemente unter ihren
        Geometrieobjekten, und „Knoten“ zeigte auch jeden Netzknoten.

        Fett stehen nur Gruppen, also Zweige, die Unterzweige zusammenfassen
        (Wurzel, die Gruppen der obersten Ebene, Lager, Verbindungen,
        Kontaktbedingungen).
        """
        ansicht = self._ansicht_merken()
        # Suchverzeichnis und Reste gelten fuer genau einen Aufbau (8d)
        self._verzeichnis = {}
        self._reste = {}
        self._filter_oben = None
        self._zweig_je_art = None
        self.clear()
        self._zweige = []
        wurzel = self._zweig(self, model.name or "Modell", f"{model.nn} Kn",
                             "modell", fett=True)

        # ---- Die Gruppen in ihrer Folge (GRUPPEN) ----------------------------
        # „Ergebnisse“ behaelt seine Art „ergebnisse“ (und damit den Pfad von
        # vorher), die anderen tragen „modell“ und ihre Kennung.
        erg = ergebnisse or {}
        anzahl = sum(len(v) for v in erg.values())
        hinweise = {
            "eigenschaften": "Werkstoffe, Querschnitte und Dicken – Stäbe, Flächen und Volumen "
                             "verweisen auf sie, darum stehen sie wie in RFEM vor der Geometrie",
            "geometrie": "Knoten der Konstruktion, Linien, Stäbe, Flächen und Volumen; die finiten "
                         "Elemente stehen unter „FE-Netz“",
            "lager_verbindungen": "Knoten-, Linien- und Flächenlager, Verbindungselemente, Gelenke, "
                                  "Liniengelenke und Kontaktbedingungen",
            "einwirkungen": "Lastfälle, Kombinationen, Ermüdungslasten und Lastgenerierer",
            "fe_netz": "Die finiten Elemente des Modells, vom Vernetzen erzeugt oder direkt gesetzt "
                       "(Stab-, Flächen- und Volumenelemente), und die Netzknoten als Zählzeile",
            "systeme": "Teile des Tragwerks, ihre Lagen und die Situationen, die einer Stellung "
                       "ihre Lastfälle zuordnen",
            "nachweise": "Was die Nachweise brauchen: Schweißnähte, Anschlüsse, Verformungsgrenzen, "
                         "Beulfelder, Volumenbereiche und Lasteinleitung. Die Stäbe mit Nachweis "
                         "stehen als „Stäbe“ unter „Geometrie“.",
            "bericht_unterlagen": "Die übernommenen Ergebnisbilder und die Dateien, Ansichten und "
                                  "Skizzen zum Modell",
            "hilfsobjekte": "Bemaßungen und Layer (in RFEM: Hilfsobjekte, dort heißen die Layer "
                            "Objektselektionen)",
        }
        gr = {}
        for kennung, text in self.GRUPPEN:
            if kennung == "ergebnisse":
                gr[kennung] = self._zweig(wurzel, text, anzahl or "", "ergebnisse", fett=True,
                                          farbe=None if anzahl else FARBEN["matt"],
                                          hinweis="Ein Ergebnis anklicken stellt es in der Ansicht ein. "
                                                  "In den Bericht: Strg+B oder „Bericht → "
                                                  "+ Ansicht übernehmen“")
            else:
                n_el = len(model.elements) if kennung == "fe_netz" else 0
                gr[kennung] = self._zweig(wurzel, text, f"{n_el} El" if n_el else "", "modell",
                                          fett=True, kennung=kennung, hinweis=hinweise.get(kennung, ""))
        geo, netz, nw = gr["geometrie"], gr["fe_netz"], gr["nachweise"]

        # ---- Geometrie: Knoten, Linien, Staebe, Flaechen, Volumen -----------
        # Je ein eigener Zweig, alle Eintraege numerisch untereinander.
        # „Knoten“ zeigt nur die Knoten der Konstruktion (Antwort 3 vom
        # 24.09.2026), nach dem Kriterium in statik3d.knotenrollen - dasselbe
        # fuer Baum und Ansicht: jeder Knoten, der an keinem Element eines
        # Flaechen- oder Koerpernetzes haengt, und jeder, auf den ein
        # Modellobjekt ausser einem Netzelement verweist. Die Netzknoten
        # zaehlt eine Zeile unter „FE-Netz“. Der teure Teil wird einmal je
        # Netzstand gerechnet (knotenrollen.netz_teile); der Aufbau bekommt
        # dadurch keine neue Schleife ueber alle Knoten.
        kons = konstruktionsknoten(model) if model.nn else np.zeros(0, int)
        n_kons = len(kons)
        kn = self._zweig(geo, "Knoten", n_kons, "knoten", stand=f"{n_kons}/{model.nn}",
                         hinweis="Die Knoten der Konstruktion: Linienknoten, Knoten der Stäbe und direkt "
                                 "gesetzten Elemente, frei gesetzte Knoten und jeder Knoten mit Lager, "
                                 "Last, Punktmasse, Dämpfer, Feder oder starrem Körper. Die übrigen "
                                 "Knoten der Flächen- und Körpernetze zählt „FE-Netz → Netzknoten“. "
                                 "Klick zeigt rechts die Übersicht und wählt nichts, ein Eintrag wählt "
                                 "den einen Knoten. Rechtsklick: Neu, Löschen; der Doppelklick legt "
                                 "keinen Knoten an.")
        # Nur die Knoten bauen, die der Zweig zeigt - sie stehen schon in ihrer
        # Nummernfolge, das natuerliche Sortieren ueber alle entfaellt. Am
        # Drehlager entstanden sonst 158 780 Eintraege samt Koordinatentext und
        # Sortierschluessel fuer 20 000 sichtbare (2,5 s je Aktualisierung).
        # Die Knoten dahinter beschreibt ``rest`` nur: Ansicht und Filter
        # finden sie, gebaut wird eine Zeile erst, wenn sie gebraucht wird (8d).
        def knotenzeile(i):
            return (f"K{i}", _kurz(model.nodes[i]), str(i),
                    "Knoten {}: x = {:.4f}  y = {:.4f}  z = {:.4f} m".format(i, *model.nodes[i]))
        kn_hinten = kons[BAUM_MAX:]
        self._liste(kn, [knotenzeile(i) for i in kons[:BAUM_MAX + 1].tolist()], "knoten",
                    sortieren=False, gesamt=n_kons,
                    rest=(lambda h=kn_hinten: h.tolist(), lambda j, h=kn_hinten: f"K{int(h[j])}",
                          lambda j, h=kn_hinten: knotenzeile(int(h[j]))))
        # Die Netzknoten als eine Zaehlzeile (Antwort 3) statt bis zu BAUM_MAX
        # Eintraegen. Ihr Klick zeigt ihre Zahl und holt die Knotentabelle
        # (BAUM_TABELLE im Fenster), dort stehen alle Knoten.
        n_netz = int(model.nn) - n_kons
        self._zweig(netz, "Netzknoten", n_netz, "netzknoten", blatt=True,
                    hinweis=f"Die Knoten der Flächen- und Körpernetze, auf die außer dem Netz nichts "
                            f"verweist (keine Linie, kein Stab, kein Lager, keine Last): {n_netz} von "
                            f"{model.nn} Knoten. Sie stehen in der Tabelle „Knoten“ unten; die Ansicht "
                            "zeigt sie mit Netz → Netzknoten.")
        lin = self._zweig(geo, "Linien", len(model.lines), "linien")
        self._liste(lin, [(name, f"{ln.typ} · {len(ln.nodes)}", name,
                           f"{name}: {ln.typ} über {len(ln.nodes)} Knoten")
                          for name, ln in sorted(model.lines.items(),
                                                 key=lambda kv: natuerlich(kv[0]))],
                    "linie", "linien")
        # „Stäbe“ im Sinn von RFEM (Antwort 2 vom 24.09.2026): die Staebe mit
        # Nachweis. Ihre FE-Stabelemente stehen unter „FE-Netz“, die
        # Schweissnaehte bei den Nachweisen. Bis zum 03.10.2026 hiess der Zweig
        # der Stabelemente „Stäbe“ und trug „Stäbe mit Nachweis“ und die
        # Schweissnaehte als Unterzweige.
        mem = self._zweig(geo, "Stäbe", len(model.members), "staebe",
                          hinweis="Stäbe im Sinn von RFEM: physische Stäbe mit Querschnitt und "
                                  "Nachweis nach EC3, je eine Kette von Stabelementen "
                                  "(FE-Netz → Stabelemente)")
        self._liste(mem, [(name, f"{len(mm.elements)} El", name,
                           f"{name}: {len(mm.elements)} Elemente")
                          for name, mm in sorted(model.members.items(),
                                                 key=lambda kv: natuerlich(kv[0]))],
                    "stab", "staebe")
        # Die finiten Elemente nach Familie in einem Durchgang (bis zum
        # 03.10.2026 drei Schleifen ueber alle Elemente)
        stab_els, n_schalen, n_vol = [], 0, 0
        for i, e in enumerate(model.elements):
            if e.typ in EL.STAB_TYPEN:
                stab_els.append((i, e))
            elif e.typ in EL.SCHALEN_TYPEN:
                n_schalen += 1
            elif e.typ in EL.VOLUMEN_TYPEN:
                n_vol += 1
        stb = self._zweig(netz, "Stabelemente", len(stab_els), "stabelemente",
                          hinweis="Die finiten Stabelemente (Balken, Fachwerkstäbe, Seile); ein Stab "
                                  "unter „Geometrie“ besteht aus einem oder mehreren davon")
        self._liste(stb, [(f"E{i}", (e.sec or "") if e.typ == "beam" else f"Fachwerk {e.sec or ''}",
                           str(i), "Element {}: {} K{}–K{}, {}, {}".format(
                               i, "Balken" if e.typ == "beam" else "Fachwerkstab",
                               e.nodes[0], e.nodes[-1], e.sec or "-", e.mat or "-"))
                          for i, e in stab_els], "stabelement", "stabelemente")
        gf = getattr(model, "flaechen", {}) or {}
        flae = self._zweig(geo, "Flächen", len(gf), "geoflaechen")
        if n_schalen:
            self._zweig(netz, "Flächenelemente", n_schalen, "flaechen",
                        hinweis="Schalenelemente aller Flächen")
        self._liste(flae, [(name + ("" if x.elemente else " ○"), x.bezug(), name,
                            f"{name}: {x.bezug()}"
                            + ("" if x.elemente else "\nnoch nicht vernetzt"))
                           for name, x in sorted(gf.items(), key=lambda kv: natuerlich(kv[0]))],
                      "geoflaeche", "geoflaechen")
        gk = getattr(model, "koerper", {}) or {}
        koerper_zeilen = [self._koerperzeile(name, x)
                          for name, x in sorted(gk.items(), key=lambda kv: natuerlich(kv[0]))]
        # Warnfarbe am Zweig, solange ein Koerper ohne Netz geblieben ist, den
        # der Vernetzer haette vernetzen sollen - so sieht man es auch zugeklappt
        mangel = any(z[4] == FARBEN["warn"] for z in koerper_zeilen)
        vo = self._zweig(geo, "Volumen", len(gk), "geokoerper",
                         farbe=FARBEN["warn"] if mangel else None,
                         hinweis=("⚠ Bei mindestens einem Volumen ist das Vernetzen gescheitert "
                                  "oder abgebrochen - der Hinweis am Eintrag nennt den Grund."
                                  if mangel else ""))
        if n_vol:
            self._zweig(netz, "Volumenelemente", n_vol, "volumen",
                        hinweis="Volumenelemente (Tetraeder, Hexaeder) aller Körper")
        self._liste(vo, koerper_zeilen, "geokoerper_einzeln", "geokoerper")

        # ---- Hilfsobjekte: Bemassungen (die Layer folgen unten) -------------
        bms = getattr(model, "bemassungen", {}) or {}
        bmz = self._zweig(gr["hilfsobjekte"], "Bemaßungen", len(bms), "bemassungen",
                          hinweis="Linearmaße, Maßketten, Höhenkoten, Winkel und Radien "
                                  "(Register Messen). Ein Maß anklicken bearbeitet es, Entf löscht; "
                                  "Doppelklick auf den Zweig: Neu: Linearmaß")
        self._liste(bmz, [(name, x.bezug(), name, f"{name}: {x.bezug()}")
                          for name, x in bms.items()], "bemassung", "bemassungen")
        self._zweig(bmz, "+ Linearmaß anlegen", "", "bemassung_neu", farbe=FARBEN["akzent"])

        # ---- Eigenschaften: Werkstoffe, Querschnitte, Dicken -----------------
        # Werkstoffe zuerst, wie in RFEM und in der Tabellengruppe
        # „Eigenschaften“ unten (bis zum 03.10.2026 Querschnitte zuerst)
        eig = gr["eigenschaften"]
        wk = self._zweig(eig, "Werkstoffe", len(model.materials), "werkstoffe")
        self._liste(wk, [(name, getattr(x, "grade", "") or "", name,
                          f"{name}: E = {getattr(x, 'E', 0) / 1e9:.0f} GPa")
                         for name, x in model.materials.items()], "werkstoff",
                    "werkstoffe")
        qs = self._zweig(eig, "Querschnitte", len(model.sections), "querschnitte")
        self._liste(qs, [(name, getattr(x, "typ", "") or "", name,
                          f"{name}: A = {getattr(x, 'A', 0) * 1e4:.1f} cm²")
                         for name, x in model.sections.items()], "querschnitt",
                    "querschnitte")
        dk = self._zweig(eig, "Dicken", len(model.shells), "dicken")
        self._liste(dk, [(name, f"{zl.zahl_text(getattr(x, 't', 0) * 1e3, punkt=True)} mm", name,
                          f"{name}: t = {zl.zahl_text(getattr(x, 't', 0) * 1e3, punkt=True)} mm")
                         for name, x in model.shells.items()], "dicke", "dicken")

        # ---- Lager und Verbindungen: Lager, Verbindungselemente, Gelenke,
        # Liniengelenke, Kontaktbedingungen --------------------------------
        lv = gr["lager_verbindungen"]
        n_lager = (len(model.supports) + len(model.line_supports)
                   + len(model.surface_supports))
        lag = self._zweig(lv, "Lager", n_lager, "lager", fett=True)
        kl = self._zweig(lag, "Knotenlager", len(model.supports), "lager")
        self._liste(kl, [(x.name or f"Lager {i + 1}", f"K{x.node}", str(i),
                          f"Knoten {x.node}: {self._lagertext(x)}")
                         for i, x in enumerate(model.supports)], "lager_einzeln",
                    "lager")
        if model.line_supports:
            ll = self._zweig(lag, "Linienlager", len(model.line_supports),
                             "linienlager")
            self._liste(ll, [(x.name or f"Linienlager {i + 1}",
                              f"{len(x.nodes)} Kn", str(i),
                              f"{len(x.nodes)} Knoten: {self._lagertext(x)}")
                             for i, x in enumerate(model.line_supports)],
                        "linienlager_einzeln", "linienlager")
        if model.surface_supports:
            fll = self._zweig(lag, "Flächenlager", len(model.surface_supports),
                              "flaechenlager")
            self._liste(fll, [(x.name or f"Flächenlager {i + 1}",
                               f"{len(x.nodes)} Kn", str(i),
                               f"{len(x.nodes)} Knoten: {self._lagertext(x)}")
                              for i, x in enumerate(model.surface_supports)],
                         "flaechenlager_einzeln", "flaechenlager")
        # ---- Punkt- und Verbindungselemente -------------------------------
        pm = getattr(model, "punktmassen", None) or []
        dp = getattr(model, "daempfer", None) or []
        fed = getattr(model, "federn", None) or {}
        sk = getattr(model, "starrkoerper", None) or []
        gs = getattr(model, "grenzschichten", None) or {}
        n_verb = len(pm) + len(dp) + len(fed) + len(sk) + len(gs)
        if n_verb:
            vbd = self._zweig(lv, "Verbindungen", n_verb, "kontakt", fett=True,
                              kennung="verbindungen",
                              hinweis="Punktmassen, Dämpfer, Federn, starre Körper "
                                      "(RBE2/RBE3) und Grenzschichten ohne Dicke")
            if pm:
                z = self._zweig(vbd, "Punktmassen", len(pm), "punktmassen")
                self._liste(z, [(x.name or f"Punktmasse {i + 1}",
                                 f"{zl.zahl_text(x.masse, punkt=True)} kg", str(i),
                                 f"Knoten {x.node}: m = {zl.zahl_text(x.masse, punkt=True)} kg, "
                                 f"J = {', '.join(zl.zahl_text(v, punkt=True) for v in (x.traegheit or []))} kg m²")
                                for i, x in enumerate(pm)], "punktmasse", "punktmassen")
            if dp:
                z = self._zweig(vbd, "Dämpfer", len(dp), "daempfer")
                self._liste(z, [(x.name or f"Dämpfer {i + 1}",
                                 f"K{x.node_a}" + (f"–K{x.node_b}" if int(x.node_b) >= 0 else ""),
                                 str(i),
                                 f"c = {', '.join(zl.zahl_text(v) for v in (x.c or []))}")
                                for i, x in enumerate(dp)], "daempfer", "daempfer")
            if fed:
                z = self._zweig(vbd, "Federn", len(fed), "federn")
                # Federn in N/m sind gross: ausgeschrieben statt „1e+08“ (25.09.2026)
                self._liste(z, [(name, "; ".join(zl.zahl_text(v) for v in (x.k or [])[:3]), name,
                                 f"{name}: k = {'; '.join(zl.zahl_text(v) for v in (x.k or []))}")
                                for name, x in fed.items()], "feder", "federn")
            if sk:
                z = self._zweig(vbd, "Starre Körper", len(sk), "starrkoerper")
                self._liste(z, [(x.name or f"Starrkörper {i + 1}",
                                 f"{x.art}, {len(x.slaves)} Kn", str(i),
                                 f"{x.art}: Master K{x.master}, "
                                 f"{len(x.slaves)} angeschlossene Knoten")
                                for i, x in enumerate(sk)], "starrkoerper", "starrkoerper")
            if gs:
                z = self._zweig(vbd, "Grenzschichten", len(gs), "grenzschichten")
                self._liste(z, [(name, f"kn = {zl.zahl_text(x.kn)}", name,
                                 f"{name}: kn = {zl.zahl_text(x.kn)} N/m je m², kt = {zl.zahl_text(x.kt)}")
                                for name, x in gs.items()], "grenzschicht", "grenzschichten")

        # Der Zweig steht immer (16.09.2026, „im Modellbaum muessen auch Gelenke
        # sein"): ohne Gelenke bietet er das Anlegen an, wie die Kontakte.
        # Weg nachgezogen 25.09.2026: „Gelenke setzen…“ hat im Register
        # Struktur keinen Knopf mehr (Paket 7)
        gel = self._zweig(lv, "Gelenke", len(model.hinges), "gelenke",
                          hinweis="Stabendgelenke: je Freiheitsgrad biegesteif, gelenkig oder Feder; "
                                  "gesetzt an Stabelementen (Kontextregister „Auswahl“ → Gelenke, "
                                  "oder Befehlssuche „Gelenke setzen“).")
        self._liste(gel, [(name, ", ".join(["ux", "uy", "uz", "φx", "φy", "φz"][d % 6]
                                           for d in h.released()) or "starr",
                           name, f"{name}: freigegeben {h.released()}")
                          for name, h in model.hinges.items()], "gelenk", "gelenke")
        self._zweig(gel, "+ Gelenk anlegen", "", "gelenk_neu", farbe=FARBEN["akzent"],
                    hinweis="Ein neues Stabendgelenk: rechts die Maske mit den sechs Freiheitsgraden.")
        # Liniengelenke (RFEM: LineHinge) stehen an der Flaeche - der Zweig
        # zeigt jede Flaeche mit ihren Gelenklinien und der Wirkung
        lg_fl = [(n, f) for n, f in model.flaechen.items() if getattr(f, "gelenklinien", None)]
        if lg_fl:
            lgz = self._zweig(lv, "Liniengelenke", len(lg_fl), "liniengelenke",
                              hinweis="Liniengelenke (RFEM: LineHinge) an den Randlinien von Flächen: "
                                      "was die Fläche dort an die Nachbarschaft weitergibt. Am Drehlager "
                                      "die Ränder der starren Kreisscheiben.")
            self._liste(lgz, [(n, f"{len(f.gelenklinien)} Linien", n,
                               f"{n}: {', '.join(f.gelenklinien[:6])}{' …' if len(f.gelenklinien) > 6 else ''}"
                               + (f"\n{f.gelenkwirkung}" if f.gelenkwirkung else ""))
                              for n, f in lg_fl], "liniengelenk", "liniengelenke")
        # Kontaktbedingungen: die Flaechenkontakte (in RFEM heissen sie
        # "Flaechenfreigaben") und die knotenweisen Bedingungen stehen unter
        # einem Zweig - es ist dieselbe Sache auf zwei Ebenen.
        flaechenkontakte = getattr(model, "kontaktbedingungen", {}) or {}
        n_kontakt = (len(flaechenkontakte) + len(model.contact_supports)
                     + len(model.gap_elements) + len(model.contact_pairs))
        # Der Zweig steht auch ohne Kontakte, sobald es Volumen gibt: dort legt
        # man einen an („+ Kontaktbedingung anlegen“).
        if n_kontakt or model.koerper:
            # Ein Warnzeichen nur, wo es einen Mangel gibt: Netz da, Fuge nicht
            # getrennt. Vor dem Vernetzen ist „noch nicht getrennt" der Normalfall.
            offen_noch = sum(1 for x in flaechenkontakte.values() if x.zu_steif(model))
            kt = self._zweig(lv, "Kontaktbedingungen", n_kontakt, "kontakt",
                             fett=True,
                             farbe=FARBEN["warn"] if offen_noch else None,
                             hinweis="Kontaktfugen zwischen Flächen und Körpern "
                                     "(in RFEM „Flächenfreigaben“) sowie die "
                                     "knotenweisen Bedingungen.")
            if flaechenkontakte or model.koerper:
                fk = self._zweig(kt, "Flächenkontakte", len(flaechenkontakte),
                                 "kontaktbedingungen",
                                 farbe=FARBEN["warn"] if offen_noch else None,
                                 hinweis="Die Fugen werden beim Vernetzen getrennt. "
                                         "Ist das Netz da und eine Fuge trotzdem nicht "
                                         "getrennt, rechnet das Modell dort durchverbunden "
                                         "– also zu steif (⚠).")
                # Das Warnzeichen steht **vor** dem Namen: hinten wuerde es
                # bei langen Namen mit dem „…“ der Spalte verschwinden, und
                # dann sahe es aus, als seien nur die kurzen Namen betroffen
                # Jeder Eintrag in der Farbe seiner Wirkung (starr grau, nur
                # Druck rot, ...) - dieselbe wie im Bild (15.09.2026, „ggf.
                # arbeiten wir auch mit Farben, das sieht man immer schnell")
                from ..kontakte import wirkungsfarbe, wirkungstext
                self._liste(fk, [(("⚠ " if x.zu_steif(model) else "") + name,
                                  x.bezug(model) + (" ⚠" if x.zu_steif(model) else ""),
                                  name, f"{name}: {wirkungstext(x)} - {x.describe()}"
                                  + ("\nAutomatisch angelegt: die Körper berühren sich. Löschen merkt "
                                     "sich das Paar - der Kontakt kommt nicht von selbst wieder."
                                     if getattr(x, "automatisch", False) else "")
                                  + ("" if x.ausgefuehrt else
                                     ("\nWird beim Vernetzen getrennt (Netz → Vernetzen)."
                                      if x.wartet_auf_netz(model) else
                                      "\n⚠ Trennung nicht ausgeführt – das Modell rechnet hier "
                                      "durchverbunden, also zu steif. Lager / Kontakt → „Kontaktfugen ausführen“.")),
                                  wirkungsfarbe(x))
                                 for name, x in flaechenkontakte.items()],
                            "kontaktbedingung", "kontaktbedingungen")
                self._zweig(fk, "+ Kontaktbedingung anlegen", "", "kontaktbedingung_neu",
                            farbe=FARBEN["akzent"],
                            hinweis="Kontakt zwischen zwei Körpern: Körper A und B, Kontaktflächen, "
                                    "Standardkontakt (Verbund, ohne Trennung, reibungsfrei, "
                                    "reibungsbehaftet, rau) - jede Richtung von Hand änderbar")
            if model.contact_supports:
                self._zweig(kt, "einseitige Lager", len(model.contact_supports),
                            "kontakt", schluessel="supports")
            if model.gap_elements:
                self._zweig(kt, "Spaltelemente", len(model.gap_elements),
                            "kontakt", schluessel="gaps")
            if model.contact_pairs:
                self._zweig(kt, "Kontaktpaare", len(model.contact_pairs),
                            "kontakt", schluessel="pairs")

        # ---- Einwirkungen -------------------------------------------------
        ew = gr["einwirkungen"]
        from ..model import LASTARTEN_NAMEN
        lf = self._zweig(ew, "Lastfälle", len(model.load_cases), "lastfaelle")

        def lastfallzeile(name, lc):
            nr = int(getattr(lc, "nummer", 0) or 0)
            return (name, f"{lc.category} · {lc.n_loads}"
                    + (f" · {lc.situation}" if getattr(lc, "situation", "") else "")
                    + (f" · {lc.theorie.upper()}. O." if getattr(lc, "theorie", "") else ""),
                    name, (f"Lastfall {nr}: " if nr else "") + f"{name}: "
                    f"{lc.description or lc.category}, {lc.n_loads} Lasten"
                    + (f", Situation {lc.situation}" if getattr(lc, "situation", "") else ""))
        for i, (name, lc) in enumerate(model.load_cases.items()):
            if i >= BAUM_MAX:
                z = self._zweig(lf, f"… {len(model.load_cases) - BAUM_MAX} weitere", "", "lastfaelle",
                                farbe=FARBEN["matt"], blatt=True,
                                hinweis="Die vollständige Liste steht in der Tabelle unten.")
                z.setData(0, self.FUER_ZWEIG, True)
                # die Lastfaelle dahinter: nachgeladen ohne ihre Lasten (8d)
                hinten = list(model.load_cases.items())[BAUM_MAX:]
                self._reste.setdefault("lastfall", []).append(
                    _Rest(lf, z, "lastfall", len(hinten), lambda h=hinten: [n for n, _x in h],
                          lambda j, h=hinten: h[j][0], lambda j, h=hinten: lastfallzeile(*h[j])))
                break
            text, zusatz, _key, tip = lastfallzeile(name, lc)
            it = self._zweig(lf, text, zusatz, "lastfall", schluessel=name, hinweis=tip)
            # Die Lasten des Lastfalls nach Art als Unterpunkte - jeder einzeln
            # anklickbar: rechts stehen dann nur diese Lasten
            je_art = lc.lasten_je_art()
            for art, titel in LASTARTEN_NAMEN:
                lasten = je_art.get(art)
                if not lasten:
                    continue
                if art == "eigengewicht":
                    g = lasten[0]
                    zahl = (f"g = ({zl.zahl_text(g[0], punkt=True)}, {zl.zahl_text(g[1], punkt=True)}, {zl.zahl_text(g[2], punkt=True)}) m/s²" if (g[0] or g[1])
                            else f"g_z = {zl.zahl_text(g[2], punkt=True)} m/s²")
                else:
                    zahl = len(lasten)
                self._zweig(it, titel, zahl, "lastart", schluessel=f"{name}|{art}", blatt=True,
                            hinweis=f"{titel} im Lastfall {name} - ein Klick zeigt sie rechts, "
                                    "in der Tabelle unten und in der Ansicht")
        kb = self._zweig(ew, "Kombinationen", len(model.combinations), "kombinationen")
        self._liste(kb, [(name, " · ".join(x for x in (getattr(c, "situation", "") or "",
                                                       (f"{c.theorie.upper()}. O."
                                                        if getattr(c, "theorie", "") else "")) if x),
                          name,
                          name + (f": Situation {c.situation}" if getattr(c, "situation", "") else ""))
                         for name, c in model.combinations.items()], "kombination",
                    "kombinationen")
        # Ermuedungslasten neben Lastfaellen und Kombinationen: bis zum
        # 24.09.2026 fehlten sie im Baum ganz, und der Anwender fand das Menue
        # nicht („wo definiere ich … die zuweisung zu den ermüdungslasten“).
        # Reihenfolge wie in der Maske (dort mit ↑/↓ geordnet), nicht sortiert.
        from .ermuedungsmaske import kurztext, n_text
        fls = getattr(model, "fatigue_loads", {}) or {}
        el = self._zweig(ew, "Ermüdungslasten", len(fls), "ermuedungslasten",
                         hinweis="Lastkollektiv für den Ermüdungsnachweis (Palmgren-Miner: "
                                 "D = Σ nᵢ / Nᵢ über alle Zeilen am selben Ort). Eine Last "
                                 "anklicken öffnet die Maske mit ihrer Zeile; Doppelklick oder "
                                 "Rechtsklick auf den Zweig: Neu, Rechtsklick auf die Last: Löschen.")
        self._liste(el, [(name, n_text(f, model), name, f"Ermüdungslast {name}: {kurztext(f, model)}")
                         for name, f in fls.items()], "ermuedungslast", "ermuedungslasten",
                    sortieren=False)
        self._zweig(el, "+ Ermüdungslast anlegen", "", "ermuedungslast_neu", farbe=FARBEN["akzent"])

        # ---- Lastgenerierer -------------------------------------------------
        wds = getattr(model, "wasserdruecke", {}) or {}
        winde = getattr(model, "winde", {}) or {}
        lgen = self._zweig(ew, "Lastgenerierer", len(wds) + len(winde), "generierer",
                           hinweis="Wasserdruck (statisch, überströmt, unterströmt) und Wind "
                                   "(DIN EN 1991-1-4) je Situation")
        self._liste(lgen, [(name, x.bezug(), name, f"Wasserdruck {name}: {x.bezug()}")
                           for name, x in wds.items()], "wasserdruck", "generierer")
        self._liste(lgen, [(name, x.bezug(), name, f"Wind {name}: {x.bezug()}")
                           for name, x in winde.items()], "wind", "generierer")
        self._zweig(lgen, "+ Wasserdruck anlegen", "", "wasserdruck_neu", farbe=FARBEN["akzent"])
        self._zweig(lgen, "+ Wind anlegen", "", "wind_neu", farbe=FARBEN["akzent"])

        # ---- Ergebnisse -------------------------------------------------
        # Ergebnisse gehoeren in denselben Baum wie das Modell: was gerechnet
        # wurde, steht dort, wo man es sucht. Ein Klick stellt das Ergebnis in
        # der Ansicht ein; ein Doppelklick tut dasselbe und legt seit dem
        # 25.09.2026 kein Berichtsbild mehr an. Der Zweig selbst entsteht mit
        # den Gruppen (oben).
        ew2 = gr["ergebnisse"]
        if not anzahl:
            self._zweig(ew2, "noch nicht gerechnet", "", "ergebnisse",
                        farbe=FARBEN["matt"], blatt=True).setData(0, self.FUER_ZWEIG, True)
        for gruppe, eintraege in erg.items():
            if not eintraege:
                continue
            z = self._zweig(ew2, gruppe, len(eintraege), "ergebnisgruppe",
                            schluessel=gruppe)
            # ein vierter Wert ist die Textfarbe (grau: kein Wert, der Zusatz
            # sagt warum - er steht dann auch im Hinweis)
            self._liste(z, [(e[0], e[1], e[2], e[1] if len(e) > 3 else e[0], *e[3:4])
                            for e in eintraege],
                        "ergebnis", "ergebnisgruppe", sortieren=False)
        eintraege = list(getattr(model, "bericht", None) or [])
        ber = self._zweig(gr["bericht_unterlagen"], "Bericht", len(eintraege), "bericht",
                          hinweis="Die aus der Ansicht übernommenen Ergebnisse")
        self._liste(ber, [(x.name or f"Bild {i + 1}", x.bezug(), str(i),
                           f"{x.name}: {x.bezug()}")
                          for i, x in enumerate(eintraege)], "berichtseintrag",
                     "bericht", sortieren=False)
        self._zweig(ber, "+ Ansicht übernehmen", "", "bericht_neu",
                    farbe=FARBEN["akzent"])

        # ---- Unterlagen: Dateien, Ansichten, Skizzen (16.09.2026) ------------
        unt = getattr(model, "unterlagen", {}) or {}
        uz = self._zweig(gr["bericht_unterlagen"], "Unterlagen", len(unt), "unterlagen",
                         hinweis="Dateien (PDF, Bilder, Word, Excel), übernommene Ansichten und Skizzen "
                                 "zum Modell - mit dem Modell gespeichert, auf Wunsch im Bericht. "
                                 "Doppelklick auf eine Unterlage öffnet sie; Rechtsklick: Neu "
                                 "(Skizze), Löschen.")
        self._liste(uz, [(name, x.bezug(), name,
                          f"{name}: {x.bezug()}" + (f"\n{x.beschriftung}" if x.beschriftung else ""))
                         for name, x in unt.items()], "unterlage", "unterlagen")
        self._zweig(uz, "+ Skizze anlegen", "", "unterlage_neu", farbe=FARBEN["akzent"])

        # ---- Subsysteme, Stellungen, Situationen ---------------------------
        # Das Gesamtsystem und die Grundstellung sind immer da; alles weitere
        # legt der Anwender an (Rechtsklick: Neu, oder der Eintrag "+ …").
        # Reihenfolge (SYSTEM_ZWEIGE): erst die Teile (Subsysteme), dann die
        # Lagen (Stellungen), dann die Situationen, die einer Stellung ihre
        # Lastfaelle zuordnen.
        from ..model import GRUNDSTELLUNG, GESAMTSYSTEM
        sy = gr["systeme"]
        subs = getattr(model, "subsysteme", {}) or {}
        sz = self._zweig(sy, "Subsysteme", 1 + len(subs), "subsysteme",
                         hinweis="Teile des Tragwerks mit allem, was dazugehört; "
                                 "Berührungselemente gehören beiden")
        self._zweig(sz, GESAMTSYSTEM, f"{len(model.elements)} El", "subsystem",
                    schluessel=GESAMTSYSTEM, hinweis="die ganze Struktur", blatt=True)
        self._liste(sz, [(name, f"{len(s.elemente)} El", name, f"{name}: {s.bezug()}")
                         for name, s in subs.items()], "subsystem", "subsysteme")
        self._zweig(sz, "+ Subsystem anlegen", "", "subsystem_neu", farbe=FARBEN["akzent"])

        # ---- Platz fuer „Detailmodelle (Volumen)“ ---------------------------
        # Hier, nach den Subsystemen und vor den Stellungen (SYSTEM_ZWEIGE;
        # Vorgabe FCM-Volumenloeser 15.1, Vertrag 10.4): ein Zweig mit je einem
        # Eintrag je DetailModelSpec, sobald das Modell Detailmodelle kennt.
        # Teilpaket 8c baut ihn nicht.

        # Stellungen stehen ausschliesslich hier (Vorgabe Kap. 16.1 Nr. 3);
        # der Zweig traegt die Schaltflaeche zum Anlegen.
        stl = self._zweig(sy, "Stellungen", len(stellungen or []), "stellungen",
                          hinweis="Lagen des Systems: Ausgangsstellung, Verschiebung, "
                                  "Verdrehung, deaktivierte Stäbe, Flächen, Volumen, "
                                  "Gelenke und Lager")
        for i, x in enumerate(stellungen or [], 1):
            eta = x.get("eta")
            text = f"S{i} · {x.get('name', '')}" + (" ★" if x.get("fuehrt") else "")
            zweig = self._zweig(stl, text, f"{float(x.get('winkel', 0)):.0f}°",
                                "stellung", schluessel=x.get("name", ""), blatt=True)
            if eta is not None:
                zweig.setToolTip(0, f"Ausnutzung η = {float(eta):.3f}".replace(".", ","))
        self._zweig(stl, "+ Stellung anlegen", "", "stellung_neu",
                    farbe=FARBEN["akzent"], blatt=True)

        sits = getattr(model, "situationen", {}) or {}
        siz = self._zweig(sy, "Situationen", 1 + len(sits), "situationen",
                          hinweis="Eine Stellung und die Lastfälle und Kombinationen, "
                                  "die in ihr gelten")
        self._zweig(siz, GRUNDSTELLUNG, "alles aktiv", "situation", schluessel=GRUNDSTELLUNG,
                    hinweis="unbewegt, alle Elemente wirken", blatt=True)
        self._liste(siz, [(name, s.bezug(), name, f"{name}: {s.bezug()}")
                          for name, s in sits.items()], "situation", "situationen")
        self._zweig(siz, "+ Situation anlegen", "", "situation_neu", farbe=FARBEN["akzent"])

        # ---- Hilfsobjekte: Layer (RFEM: Objektselektionen) ------------------
        lay = getattr(model, "layer", {}) or {}
        lyz = self._zweig(gr["hilfsobjekte"], "Layer", len(lay), "layerliste",
                          hinweis="Benannte Objektgruppen (RFEM: Objektselektionen) - sichtbar oder "
                                  "ausgeblendet, gesperrt oder frei. Ein Layer angeklickt wählt seine "
                                  "Objekte, doppelt angeklickt öffnet er die Layerliste; Rechtsklick: "
                                  "Neu, Löschen.")
        self._liste(lyz, [(name, ("ausgeblendet · " if not L.sichtbar else "")
                           + ("gesperrt · " if L.gesperrt else "") + L.bezug(), name,
                           f"{name}: {L.bezug()}" + ("\nausgeblendet" if not L.sichtbar else "")
                           + ("\ngesperrt - nicht wählbar, nicht änderbar" if L.gesperrt else "")
                           + ("\naus der RFEM-Objektselektion" if L.quelle == "rfem" else ""),
                           FARBEN["matt"] if not L.sichtbar else None)
                          for name, L in lay.items()], "layer", "layerliste")
        self._zweig(lyz, "+ Layer aus Auswahl", "", "layer_neu", farbe=FARBEN["akzent"])

        # ---- Nachweise, gebuendelt (Antwort 4 vom 24.09.2026) ---------------
        # Die Schweissnaehte zuerst; bis zum 03.10.2026 hingen sie am Zweig der
        # Stabelemente, die uebrigen Nachweisobjekte einzeln an der Wurzel.
        naehte = getattr(model, "schweissnaehte", {}) or {}
        nz = self._zweig(nw, "Schweißnähte", len(naehte), "schweissnaehte",
                         hinweis="Nahtart, Lage und Ausführung → Kerbfall nach EN 1993-1-9; "
                                 "„äquivalent“ = Ersatznaht für alle nicht einzeln "
                                 "modellierten Nähte. Rechtsklick: Neu, Löschen.")
        self._liste(nz, [(name, x.bezug(), name, f"Schweißnaht {name}: {x.bezug()}")
                         for name, x in naehte.items()], "schweissnaht", "schweissnaehte")
        self._zweig(nz, "+ Schweißnaht anlegen", "", "schweissnaht_neu", farbe=FARBEN["akzent"])
        # Anschluesse gehoeren zum Modell und stehen darum hier - der Zweig
        # traegt wie bei den Stellungen die Schaltflaeche zum Anlegen.
        an = self._zweig(nw, "Anschlüsse", len(getattr(model, "joints", {}) or {}),
                         "anschluesse")
        self._liste(an, [(name, j.ort(), name, f"{name}: {j.typ} an {j.ort()}")
                         for name, j in (getattr(model, "joints", {}) or {}).items()],
                    "anschluss", "anschluesse")
        self._zweig(an, "+ Anschluss anlegen", "", "anschluss_neu",
                    farbe=FARBEN["akzent"])
        grenzen = getattr(model, "verformungsgrenzen", {}) or {}
        vf = self._zweig(nw, "Verformungsnachweise", len(grenzen), "verformungen")
        self._liste(vf, [(name, g.grenztext(), name,
                          f"{g.bezug()}: {g.groesse} ≤ {g.grenztext()}")
                         for name, g in grenzen.items()], "verformung", "verformungen")
        self._zweig(vf, "+ Verformungsgrenze", "", "verformung_neu",
                    farbe=FARBEN["akzent"])
        felder = getattr(model, "beulfelder", {}) or {}
        if felder:
            bl = self._zweig(nw, "Beulfelder", len(felder), "beulfelder")
            self._liste(bl, [(name, x.bezug(), name, f"{name}: {x.bezug()}")
                             for name, x in felder.items()], "beulfeld", "beulfelder")
        bereiche = getattr(model, "volumenbereiche", {}) or {}
        if bereiche:
            vbe = self._zweig(nw, "Volumenbereiche", len(bereiche),
                              "volumenbereiche")
            self._liste(vbe, [(name, x.bezug(), name, f"{name}: {x.bezug()}")
                              for name, x in bereiche.items()], "volumenbereich",
                        "volumenbereiche")
        stellen = getattr(model, "lasteinleitungen", {}) or {}
        if stellen:
            li = self._zweig(nw, "Lasteinleitung", len(stellen), "lasteinleitung")
            self._liste(li, [(name, x.bezug(), name, f"{name}: {x.bezug()}")
                             for name, x in stellen.items()], "lasteinleitung_einzeln",
                        "lasteinleitung")
        self._ansicht_herstellen(ansicht)


class Baumfilter(QtWidgets.QLineEdit):
    """Die Filterzeile ueber dem Modellbaum (Teilpaket 8d, 03.10.2026; Plan vom
    24.09.2026: „Filterzeile: Sie steht über dem Baum (Strg+F)“).

    Zu Beginn zu - sie kostet dem Baum sonst eine Zeile, und bei 1366 x 768
    fehlen ihm schon welche (test_fensteraufteilung). Strg+F im Baum oeffnet
    sie (:meth:`Modellbaum.filter_oeffnen`), jede Eingabe filtert sofort
    (:meth:`Modellbaum.filtern`). Esc hebt den Filter auf, schliesst die Zeile
    und gibt die Tastatur dem Baum; Strg+F markiert den Text. Beide Tasten
    sind sonst Kuerzel des ganzen Programms (Alles deselektieren,
    Befehlssuche) - die Zeile nimmt sie darum selbst an (``ShortcutOverride``).
    Pfeil nach unten und die Eingabetaste geben die Tastatur dem Baum und
    machen die erste sichtbare Trefferzeile aktuell.

    Getippt wird nach einer Ruhezeit gefiltert (:attr:`RUHEZEIT_MS`), nicht bei
    jedem Tastendruck; Leeren und Esc wirken sofort (Nachbesserung 8d, G4: bei
    20 000 Knoten lief bis dahin jeder Buchstabe einzeln durch den Baum)."""

    #: so lange nach dem letzten Tastendruck wird gefiltert
    RUHEZEIT_MS = 150

    def __init__(self, baum: "Modellbaum", parent=None):
        super().__init__(parent)
        self.baum = baum
        self.setObjectName("baumfilter")
        self.setPlaceholderText("Filter: Name im Baum …")
        self.setClearButtonEnabled(True)
        self.setToolTip("Zeigt nur die Zeilen, deren Name den Text enthält (Groß- und Kleinschreibung "
                        "gleich), mit ihren Zweigen. Esc hebt den Filter auf, ↓ oder die Eingabetaste "
                        "gehen in den Baum.")
        self._ruhe = QtCore.QTimer(self)
        self._ruhe.setSingleShot(True)
        self._ruhe.setInterval(self.RUHEZEIT_MS)
        # gebundene Methoden, keine Lambdas (Nachpruefung 8b/C15)
        self._ruhe.timeout.connect(self.jetzt_filtern)
        self.textChanged.connect(self._getippt)
        baum.filterzeile = self
        self.hide()

    def _getippt(self, text: str) -> None:
        """Leer: sofort aufheben; sonst nach der Ruhezeit filtern."""
        if not str(text or "").strip():
            self._ruhe.stop()
            self.baum.filtern("")
        else:
            self._ruhe.start()

    def jetzt_filtern(self) -> None:
        """Den Text jetzt filtern (Ablauf der Ruhezeit, Pfeil, Eingabetaste)."""
        self._ruhe.stop()
        self.baum.filtern(self.text())

    def anhalten(self) -> None:
        """Eine wartende Eingabe verwerfen (Esc, ein anderes Modell)."""
        self._ruhe.stop()

    @staticmethod
    def _gehoert_mir(ev) -> bool:
        if ev.type() != QtCore.QEvent.ShortcutOverride:
            return False
        if ev.key() == QtCore.Qt.Key_Escape and ev.modifiers() == QtCore.Qt.NoModifier:
            return True
        return ev.key() == QtCore.Qt.Key_F and ev.modifiers() == QtCore.Qt.ControlModifier

    def event(self, ev):
        if self._gehoert_mir(ev):
            ev.accept()          # kein Kuerzel: der Tastendruck kommt als KeyPress an
            return True
        return super().event(ev)

    def keyPressEvent(self, ev):
        taste, mod = ev.key(), ev.modifiers()
        if taste == QtCore.Qt.Key_F and mod == QtCore.Qt.ControlModifier:
            self.selectAll()
            return
        if taste == QtCore.Qt.Key_Escape and mod == QtCore.Qt.NoModifier:
            self.anhalten()
            self.baum.filter_schliessen()
            return
        if taste in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if self._ruhe.isActive():
                self.jetzt_filtern()
            self.baum.setFocus(QtCore.Qt.OtherFocusReason)
            erster = self.baum.erster_treffer()
            if erster is not None:
                # wie ein Pfeil im Baum: waehlen, melden, ins Bild holen
                self.baum.setCurrentItem(erster)
                self.baum.scrollToItem(erster)
            return
        super().keyPressEvent(ev)


class Uebersichtsliste(QtWidgets.QTreeWidget):
    """Die Liste in der Uebersicht eines Zweigs (Teilpaket 8b): Name und
    Kennzahl je Zeile, ohne Kopf, so hoch wie ihre Zeilen - bis
    :attr:`ZEILEN_MAX`, darueber rollt sie.

    Die Hoehe folgt der Zeilenhoehe, die die Liste **im Fenster** hat. Das
    Stilblatt (``QTreeWidget::item`` mit Polster) haengt am Hauptfenster; die
    Zeilenhoehe vor dem Einsetzen in die Maske war darum zu klein: 14 statt
    23 px mit Segoe UI, sichtbar waren 9,3 von 15 Zeilen und 0,8 von einer
    (Gegenpruefung 03.10.2026, gemessen mit Schrift). Darum rechnet
    :meth:`sizeHint` bei jedem Abruf mit der aktuellen Zeilenhoehe, und nach
    jedem Stil- oder Schriftwechsel fragt das Layout neu. Waagerecht rollt die
    Liste nie - ein Rollbalken verdeckte die einzige Zeile („Flächenkontakte“);
    lange Namen enden mit „…“, der Hinweis am Zeiger nennt sie ganz."""

    #: so viele Zeilen zeigt die Liste ganz, mehr rollen senkrecht
    ZEILEN_MAX = 15
    #: die Kennzahl (Spalte 1) hoechstens so breit wie im Modellbaum
    KENNZAHL_MAX = 120

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setTextElideMode(QtCore.Qt.ElideRight)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.header().setMaximumSectionSize(self.KENNZAHL_MAX)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

    def zeilenhoehe(self) -> int:
        """Die Hoehe einer Zeile, wie sie jetzt gezeichnet wird."""
        if not self.topLevelItemCount():
            return 0
        return max(1, self.sizeHintForRow(0))

    def _hoehe(self) -> int:
        n = min(self.topLevelItemCount(), self.ZEILEN_MAX)
        rand = self.contentsMargins()
        innen = self.viewportMargins()
        return (n * self.zeilenhoehe() + rand.top() + rand.bottom() + innen.top() + innen.bottom())

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(super().sizeHint().width(), self._hoehe())

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(super().minimumSizeHint().width(), self._hoehe())

    def event(self, ev):
        erg = super().event(ev)
        if ev.type() in (QtCore.QEvent.Polish, QtCore.QEvent.StyleChange, QtCore.QEvent.FontChange,
                         QtCore.QEvent.Show):
            self.updateGeometry()
        return erg


# ==========================================================================
# Tabellenbereich unten
# ==========================================================================
def __getattr__(name):
    """Der untere Bereich (Tabellenbereich) steht seit 03.10.2026 (Teilpaket
    10b) in tabellen.py bei den Tabellen, die er traegt; der Name bleibt hier
    als Verweis fuer aeltere Aufrufer (dsg.Tabellenbereich)."""
    if name in ("Tabellenbereich", "Reiterleiste"):
        from . import tabellen
        return getattr(tabellen, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
