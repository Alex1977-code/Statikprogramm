"""Verzeichnis der Elementtypen.

Hier steht **einmal**, welche finiten Elemente es gibt, zu welcher Familie
sie gehoeren, wie viele Knoten und Freiheitsgrade je Knoten sie haben und wie
die Ansicht sie zeichnet (VTK-Zelltyp). Assemblierung, Loeser, Ansicht,
Vernetzer, Import und Bericht fragen dieses Verzeichnis - nirgends sonst
stehen Aufzaehlungen wie ("tet4", "tet10", "hex8").

Familien:
    stab        Balken, Fachwerkstab, Seil (2 Knoten, 6 FHG je Knoten)
    schale      Schalen (3, 4, 6, 8 Knoten; 6 FHG je Knoten)
    volumen     Volumenelemente (nur Verschiebungen: 3 FHG je Knoten)
    ebene       ebene Kontinuumselemente: Scheibe, ebener Dehnungszustand,
                rotationssymmetrisch (3 Verschiebungs-FHG je Knoten, die
                Steifigkeit wirkt nur in der Elementebene)
    verbindung  Feder (2 Knoten, 6 FHG) und Grenzschicht ohne Dicke
                (6 oder 8 Knoten, 3 FHG)

Knotenreihenfolgen folgen der VTK-/Abaqus-Konvention (Ecken zuerst, dann
Kantenmitten in Kantenreihenfolge, beim Hexaeder unten, oben, senkrecht).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Elementart:
    typ: str
    familie: str          # stab | schale | volumen | ebene | verbindung
    knoten: int
    fhg: int              # Freiheitsgrade je Knoten: 6 oder 3
    vtk: int              # VTK-Zelltyp fuer die Ansicht
    name: str             # Klartext fuer Bericht und Tabellen
    ordnung: int = 1      # 1 linear, 2 quadratisch


#: VTK-Zelltypen
VTK_LINE, VTK_TRI, VTK_QUAD, VTK_TETRA, VTK_HEX, VTK_WEDGE, VTK_PYRAMID = 3, 5, 9, 10, 12, 13, 14
VTK_TRI6, VTK_QUAD8, VTK_TET10, VTK_HEX20, VTK_WEDGE15 = 22, 23, 24, 25, 26

ELEMENTE: dict[str, Elementart] = {a.typ: a for a in (
    Elementart("beam", "stab", 2, 6, VTK_LINE, "Balken 3D (12 FHG, Timoshenko-Schub; "
               "mit Exzentrizität und Wölbkrafttorsion als 7. FHG)"),
    Elementart("truss", "stab", 2, 6, VTK_LINE, "Fachwerkstab (nur Normalkraft; auch nur Zug "
               "oder nur Druck)"),
    Elementart("seil", "stab", 2, 6, VTK_LINE, "Seil (nur Zug; elastische Kettenlinie nach "
               "Theorie III. Ordnung)"),
    Elementart("shell3", "schale", 3, 6, VTK_TRI, "Schale, Dreieck (CST + DKT; dick: MITC3)"),
    Elementart("shell4", "schale", 4, 6, VTK_QUAD, "Schale, Viereck (bilinear mit inkompatiblen "
               "Moden + MITC4, Reissner-Mindlin)"),
    Elementart("shell6", "schale", 6, 6, VTK_TRI6, "Schale, quadratisches Dreieck "
               "(Reissner-Mindlin)", 2),
    Elementart("shell8", "schale", 8, 6, VTK_QUAD8, "Schale, quadratisches Viereck "
               "(Reissner-Mindlin)", 2),
    Elementart("tet4", "volumen", 4, 3, VTK_TETRA, "Tetraeder, linear"),
    Elementart("tet10", "volumen", 10, 3, VTK_TET10, "Tetraeder, quadratisch", 2),
    Elementart("hex8", "volumen", 8, 3, VTK_HEX, "Hexaeder mit inkompatiblen Moden"),
    Elementart("hex20", "volumen", 20, 3, VTK_HEX20, "Hexaeder, quadratisch (20 Knoten)", 2),
    Elementart("pent6", "volumen", 6, 3, VTK_WEDGE, "Keil (Prisma), linear"),
    Elementart("pent15", "volumen", 15, 3, VTK_WEDGE15, "Keil (Prisma), quadratisch", 2),
    Elementart("pyr5", "volumen", 5, 3, VTK_PYRAMID, "Pyramide, linear"),
    Elementart("ebene3", "ebene", 3, 3, VTK_TRI, "Scheibe/ebenes Element, Dreieck (CST)"),
    Elementart("ebene4", "ebene", 4, 3, VTK_QUAD, "Scheibe/ebenes Element, Viereck "
               "(inkompatible Moden)"),
    Elementart("ebene6", "ebene", 6, 3, VTK_TRI6, "Scheibe/ebenes Element, quadratisches "
               "Dreieck", 2),
    Elementart("ebene8", "ebene", 8, 3, VTK_QUAD8, "Scheibe/ebenes Element, quadratisches "
               "Viereck", 2),
    Elementart("feder", "verbindung", 2, 6, VTK_LINE, "Feder (6 Steifigkeiten in lokalen Achsen)"),
    Elementart("grenzschicht6", "verbindung", 6, 3, VTK_WEDGE, "Grenzschicht ohne Dicke, "
               "Dreieck (Klebe-/Kontaktschicht)"),
    Elementart("grenzschicht8", "verbindung", 8, 3, VTK_HEX, "Grenzschicht ohne Dicke, "
               "Viereck (Klebe-/Kontaktschicht)"),
)}


def familie(typ: str) -> str:
    a = ELEMENTE.get(typ)
    return a.familie if a is not None else ""


def typen(familie_: str) -> tuple:
    """Alle Typen einer Familie, in Verzeichnisreihenfolge."""
    return tuple(t for t, a in ELEMENTE.items() if a.familie == familie_)


def knotenzahl(typ: str) -> int:
    return ELEMENTE[typ].knoten


def fhg_je_knoten(typ: str) -> int:
    a = ELEMENTE.get(typ)
    return a.fhg if a is not None else 6


def ist_quadratisch(typ: str) -> bool:
    a = ELEMENTE.get(typ)
    return a is not None and a.ordnung >= 2


#: Zustaende der ebenen Elemente
EBENE_ZUSTAENDE = {
    "spannung": "ebener Spannungszustand (Scheibe mit Dicke t)",
    "dehnung": "ebener Dehnungszustand (Scheibe je Tiefe t)",
    "rotation": "rotationssymmetrisch (x = r, z = Achse; je Radiant)",
}

#: Ausfall eines Stabes (Fachwerkstab, Seil, Feder): nur Zug oder nur Druck
NUR_ARTEN = {"": "immer wirksam", "zug": "nur Zug (faellt bei Druck aus)",
             "druck": "nur Druck (faellt bei Zug aus)"}

#: Stab-, Schalen-, Volumen-, Ebenen- und Verbindungstypen
STAB_TYPEN = typen("stab")
SCHALEN_TYPEN = typen("schale")
VOLUMEN_TYPEN = typen("volumen")
EBENE_TYPEN = typen("ebene")
VERBINDUNG_TYPEN = typen("verbindung")
#: Typen mit nur drei Verschiebungs-FHG je Knoten
VERSCHIEBUNGS_TYPEN = tuple(t for t, a in ELEMENTE.items() if a.fhg == 3)
#: Typen, die als Stab gezeichnet und behandelt werden (Linie zwischen zwei Knoten)
LINIEN_TYPEN = STAB_TYPEN + ("feder",)

#: Bezugsflaechen der Volumenelemente werden in elements.solid gefuehrt
#: (FLAECHEN, FLAECHEN_ECKEN).
