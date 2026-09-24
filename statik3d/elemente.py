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
    # Tetraeder mit Ordnung p (elements/tetp.py): vier Eckknoten, die hoeheren
    # Ansaetze als hierarchische Zusatz-FHG hinter den Knoten-FHG
    Elementart("tetp2", "volumen", 4, 3, VTK_TETRA, "Tetraeder mit Ordnung p = 2 "
               "(hierarchisch, nur Eckknoten)", 2),
    Elementart("tetp3", "volumen", 4, 3, VTK_TETRA, "Tetraeder mit Ordnung p = 3 "
               "(hierarchisch, nur Eckknoten)", 3),
    Elementart("tetp4", "volumen", 4, 3, VTK_TETRA, "Tetraeder mit Ordnung p = 4 "
               "(hierarchisch, nur Eckknoten)", 4),
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


#: Seitenformen der Volumentypen, mit denen sie an einen Nachbarn stossen
#: (Auftrag VQ83/VQ203, 23.09.2026): tri3/quad4 linear, tri6/quad8 quadratisch
#: mit Kantenmitten, "trip" die Seite eines Tetraeders mit Ordnung p (ohne
#: Mittenknoten; seine Spur richtet sich nach dem Nachbarn, tetp.pflichtseiten).
#: VQ83 und VQ203 sind in der Oberflaeche die Namen von hex8 und hex20, die
#: entarten duerfen; gerechnet werden sie als der Keil, die Pyramide oder der
#: Tetraeder, der sie sind (solid.entartung_aufloesen) - darum haben sie hier
#: die Seitenformen von hex8/pent6/pyr5/tet4 bzw. hex20/pent15/tet10.
SEITENFORMEN: dict = {
    "tet4": ("tri3",), "tet10": ("tri6",),
    "tetp2": ("trip",), "tetp3": ("trip",), "tetp4": ("trip",),
    "hex8": ("quad4",), "hex20": ("quad8",),
    "pent6": ("tri3", "quad4"), "pent15": ("tri6", "quad8"),
    "pyr5": ("quad4", "tri3"),
}

#: Vertraeglichkeit zweier Seitenformen an einer gemeinsamen Seite:
#:   "direkt"  - dieselbe Spur, konform ohne Zutat;
#:   "bindung" - konform, weil die Assemblierung die Kantenmitten der
#:               quadratischen Seite an ihre Ecken bindet (u_m = (u_a + u_b)/2,
#:               assemble.mittelknoten_bindungen, B5);
#:   "linear"  - konform, weil das tetp die Seite linear haelt (tetp.pflichtseiten);
#:   "nein"    - nicht konform: verschiedene Form (Dreieck gegen Viereck), oder
#:               tet10 neben tetp (die Rechnung haelt dort laut an).
SEITEN_VERTRAEGLICH: dict = {
    frozenset(("tri3",)): "direkt", frozenset(("quad4",)): "direkt",
    frozenset(("tri6",)): "direkt", frozenset(("quad8",)): "direkt",
    frozenset(("trip",)): "direkt",
    frozenset(("tri3", "tri6")): "bindung", frozenset(("quad4", "quad8")): "bindung",
    frozenset(("trip", "tri3")): "linear", frozenset(("trip", "tri6")): "nein",
}

#: Rangfolge, wenn zwei Typen ueber mehrere Seitenformen stossen koennen
_RANG = {"direkt": 0, "linear": 1, "bindung": 2, "uebergang": 3, "nein": 4}

#: Klartext der Vertraeglichkeit fuer Oberflaeche und Bericht
VERTRAEGLICH_TEXT: dict = {
    "direkt": "passen direkt aneinander",
    "linear": "passen aneinander, die Seite des Tetraeders mit Ordnung p bleibt linear",
    "bindung": "passen aneinander, die Kantenmitten der quadratischen Seite werden an die Ecken "
               "gebunden (dort wirkt die Seite linear)",
    "uebergang": "Dreieck gegen Viereck: nur über Pyramiden (pyr5) als Übergang, die der Sweep setzt",
    "nein": "passen nicht aneinander",
}


def _form(seite: str) -> str:
    """Dreieck (tri3, tri6, trip) oder Viereck (quad4, quad8)."""
    return "viereck" if seite.startswith("quad") else "dreieck"


def seiten_vertraeglich(a: str, b: str) -> str:
    """Vertraeglichkeit zweier Seitenformen (SEITEN_VERTRAEGLICH), sonst "nein"."""
    return SEITEN_VERTRAEGLICH.get(frozenset((a, b)), "nein")


def vertraeglich(typ_a: str, typ_b: str) -> str:
    """Vertraeglichkeit zweier Volumentypen im selben Netz: die beste ueber
    ihre gemeinsamen Seitenformen. Haben sie keine gleich geformte Seite
    (Dreieck gegen Viereck), fuehrt nur eine Pyramide (pyr5: Viereck unten,
    Dreiecke seitlich) von einem zum anderen - "uebergang", wenn beide Seiten
    der Pyramide passen. Haben sie gleich geformte Seiten, die nicht passen
    (tet10 neben tetp), ist es "nein": dort stossen sie direkt aneinander."""
    fa, fb = SEITENFORMEN.get(typ_a, ()), SEITENFORMEN.get(typ_b, ())
    if not fa or not fb:
        return "nein"
    gleich = [(x, y) for x in fa for y in fb if _form(x) == _form(y)]
    if gleich:
        return min((seiten_vertraeglich(x, y) for x, y in gleich), key=_RANG.__getitem__)
    ueber_a = min((seiten_vertraeglich(x, "tri3") for x in fa if _form(x) == "dreieck"),
                  key=_RANG.__getitem__, default="nein")
    ueber_b = min((seiten_vertraeglich(y, "quad4") for y in fb if _form(y) == "viereck"),
                  key=_RANG.__getitem__, default="nein")
    if _RANG[ueber_a] < _RANG["nein"] and _RANG[ueber_b] < _RANG["nein"]:
        return "uebergang"
    ueber_a = min((seiten_vertraeglich(x, "quad4") for x in fa if _form(x) == "viereck"),
                  key=_RANG.__getitem__, default="nein")
    ueber_b = min((seiten_vertraeglich(y, "tri3") for y in fb if _form(y) == "dreieck"),
                  key=_RANG.__getitem__, default="nein")
    if _RANG[ueber_a] < _RANG["nein"] and _RANG[ueber_b] < _RANG["nein"]:
        return "uebergang"
    return "nein"


#: Vertraeglichkeit je Paar von Volumentypen - daraus liest die Oberflaeche,
#: welche angehakten Elemente zusammen gehen (Ausgrauen); ein Test prueft die
#: Tabelle gegen die Rechnung (tests/test_vertraeglich.py).
VERTRAEGLICH: dict = {(a, b): vertraeglich(a, b) for a in SEITENFORMEN for b in SEITENFORMEN}


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
