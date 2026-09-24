"""
Tabelle „Verformungen“ (Verformungsnachweise, GZG): Spalten und Zeilen.

Steht ausserhalb von gui.main, damit tests/test_gzg.py Kopf, Einheit und
Inhalt dieser Tabelle ohne das Hauptfenster pruefen kann. gui.main zieht
pyvista, pyvistaqt und VTK nach; das kostete die fensterlose Suite den
groessten Teil ihrer Laufzeit (Befund B147, 23.09.2026). Der Zeilenbau
braucht kein Qt; nur die Spaltenbeschreibung ``Spalte`` kommt aus
gui.tabellen. MainWindow.gzg_spalten und MainWindow.refresh_verformungen
rufen diese beiden Funktionen - Spalten und Zeilen stehen hier nebeneinander,
weil sie zusammenpassen muessen.
"""
from __future__ import annotations

from ..gzg import SITUATIONEN
from .tabellen import Spalte


def spalten() -> list:
    """Spalten der Tabelle „Verformungen“ (Befund FM8 vom 22.09.2026: die
    Oberflaechenpruefung hielt nur die Gegenrichtung)."""
    return [
        Spalte("Nachweis"), Spalte("Bezug"), Spalte("Größe"),
        Spalte("Situation"),
        # Zwei Zahlenspalten statt einer: eine Verdrehung steht in mrad
        # und hat unter einem Kopf "mm" nichts zu suchen. Wer den Wert
        # gegen eine mm-Grenze haelt (Dichtung, Fuehrung, Anschlag nach
        # DIN 19704), vergleicht sonst Winkel mit Weg - und bei der
        # Einheitenwahl "cm" wurde die Zahl zusaetzlich mit 0,1
        # malgenommen (12,97 -> 1,30) und als cm beschriftet. "mrad" steht
        # nicht in einheiten.GRUND, die Verdrehung wird von der
        # Einheitenwahl also nicht mehr angefasst.
        Spalte("Wert", "mm", "zahl", 2,
               hinweis="größte Verschiebung über alle GZG-Kombinationen"),
        Spalte("Verdrehung", "mrad", "zahl", 2,
               hinweis="größte Verdrehung über alle GZG-Kombinationen "
                       "(φx, φy, φz)"),
        Spalte("Grenzwert"),
        # Ampel wie in allen Nachweistabellen (24.09.2026, tabellen.ampelstufe)
        Spalte("Ausnutzung", "", "zahl", 3, hinweis="Filter z. B. > 1", ampel=True),
        Spalte("Kombination"), Spalte("Stelle"), Spalte("Status", ampel=True)]


def zeilen(model, analysis) -> list:
    """Eine Zeile je Verformungsgrenze des Modells, in der Folge von spalten().

    ``analysis`` darf None sein (noch nicht gerechnet): dann stehen Grenzwert
    und „nicht gerechnet“ in der Zeile, die Zahlenfelder bleiben leer.
    """
    erg = getattr(analysis, "gzg", None) if analysis is not None else None
    ergebnis = []
    for name, g in model.verformungsgrenzen.items():
        c = erg.checks.get(name) if erg is not None else None
        ergebnis.append([name, g.bezug(), g.groesse,
                         SITUATIONEN.get(g.situation, g.situation or "alle GZG"),
                         ("" if c is None or c.fehler or c.winkel
                          else c.wert * 1e3),
                         (c.wert * 1e3 if c is not None and not c.fehler
                          and c.winkel else ""),
                         (c.grenztext if c is not None else g.grenztext()),
                         (c.util if c is not None else ""),
                         (c.kombination if c is not None else ""),
                         (c.stelle if c is not None else ""),
                         (c.status() if c is not None else "nicht gerechnet")])
    return ergebnis
