"""Absaetze der Handbuecher fuer Pruefungen, die einen Handbuchsatz an einer
Messung festhalten.

Ein Handbuchsatz, der eine gemessene Zahl oder ein Verhalten nennt, wird von
der Suite gegen die Messung geprueft, die ihn belegt. Anlass: Nebenbefunde der
Fehlerrunden vom 22./23.09.2026 (am Stand ec6448c nachgeprueft), in denen das
Benutzerhandbuch „die Knoten eines Rahmens“ statt 15 von 17 hob, einen
Zwischenstand des Zweigs als frueheres Verhalten beschrieb und eine Abhilfe
nannte, die die Kombinationsmaske nicht kann.
"""
import os

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def absatz(anfang: str, datei: str = "Benutzerhandbuch.md") -> str:
    """Der Absatz oder Listenpunkt, dessen erste Zeile ``anfang`` enthaelt, in
    einer Zeile.

    Zeilenumbrueche und Einrueckung werden zu je einem Leerzeichen, damit eine
    Pruefung nicht am Umbruch haengt. Er endet an einer Leerzeile, einer
    Ueberschrift oder dem naechsten Listenpunkt. "" wenn es ihn nicht gibt -
    dann schlaegt die Pruefung fehl, statt still nichts zu pruefen.
    """
    with open(os.path.join(DOCS, datei), encoding="utf-8") as f:
        zeilen = f.read().splitlines()
    for i, z in enumerate(zeilen):
        if anfang in z:
            teil = [z]
            for w in zeilen[i + 1:]:
                if not w.strip() or w.startswith(("* ", "- ", "#")):
                    break
                teil.append(w)
            return " ".join(" ".join(teil).split())
    return ""


def zahl(wert: float, stellen: int = 4) -> str:
    """4.75716 -> '4,7572' wie im Handbuch (Dezimalkomma, feste Stellen)."""
    return f"{wert:.{stellen}f}".replace(".", ",")
