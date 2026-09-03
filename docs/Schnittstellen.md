# Statik3D – Import-Schnittstellen

Datei → Importieren (GUI), `python -m statik3d.cli --import datei` (CLI) oder

```python
from statik3d import importers
log = []
model = importers.import_file("modell.ifc", log=log, unit_scale=1.0)
```

Der Import erkennt das Format an der Dateiendung (bei `.xlsx` an den
Blattnamen). Meldungen und Warnungen werden in `log` gesammelt. Mit
`model=` wird an ein vorhandenes Modell angehängt. Nach dem Import werden
doppelte Knoten zusammengeführt, Stäbe automatisch erkannt (für die
Nachweise) und die Herkunft in `model.meta["quelle"]` vermerkt.

Einheiten im Modell sind m, N, Pa. `unit_scale` skaliert Längen der Datei
(DXF-Standard mm → 0,001; alle anderen Formate m → 1).

## Übersicht

| Endung | Format | Typische Herkunft | Übernommen wird |
|---|---|---|---|
| `.json` | Statik3D | – | vollständiges Modell (Format 1 und 2) |
| `.dxf` | AutoCAD DXF (ASCII, R12–2018) | InfoCAD, RFEM, CAD | LINE, LWPOLYLINE, POLYLINE (2D/3D, Polyface), 3DFACE |
| `.ifc` | IFC 2x3 / IFC 4 STEP-Datei | InfoCAD, RFEM, Allplan, Revit, Tekla | Statikmodell (Structural Analysis View) oder Bauteilachsen |
| `.xlsx` | SAF – Structural Analysis Format | RFEM 6, SCIA, Allplan, AxisVM, Frilo | Materialien, Querschnitte, Knoten, Stäbe, Flächen, Lager, Lastfälle, Lastgruppen, Kombinationen, Lasten |
| `.xlsx`, `.csv`, Ordner | RFEM 5/6, RSTAB Tabellenexport | Dlubal | Knoten, Linien, Materialien, Querschnitte, Stäbe, Flächen, Knotenlager, Lastfälle, Kombinationen, Knoten-/Stablasten |
| `.inp` | Abaqus / CalculiX | FE-Programme | Netz, Sets, Materialien, Beam/Shell/Solid Sections, Boundary, CLOAD, DLOAD, Steps |
| `.bdf`, `.nas`, `.dat` | Nastran Bulk Data | FE-Programme | GRID, CBAR/CBEAM, CROD, CTRIA3/CQUAD4, CTETRA/CHEXA, PBAR/PBARL/PBEAM/PSHELL/PSOLID, MAT1, SPC/SPC1, FORCE/MOMENT, PLOAD2/PLOAD4, GRAV, LOAD |
| `.step`, `.stp`, `.iges`, `.igs`, `.brep`, `.stl` | CAD-Geometrie | CAD | Vernetzung mit gmsh (Volumen Tet4/Tet10 oder Schalen) |
| `.rf6` | RFEM 6 Projektdatei (ZIP + SQLite `model.db`) | RFEM 6 | Knoten, Linien, Stäbe, Querschnitte, Materialien, Knoten-/Linien-/Flächenlager mit Nichtlinearität, Gelenke, Lastfälle |
| `.rf5`, `.rfem`, `.rstab`, `.fem`, `.ifm` | proprietär (binär) | RFEM 5, RSTAB, InfoCAD | Behälter wird untersucht; sonst Meldung mit Exportweg |

## InfoCAD

InfoCAD-Projektdateien sind binär. Exportwege:

* **IFC-Statikmodell** (Datei → Export → IFC, Statikmodell / Structural
  Analysis View): Knoten, Stäbe mit Profil, Flächen mit Dicke, Lager,
  Lasten und Lastfälle werden übernommen. Empfohlen.
* **DXF**: Systemlinien und Flächen als Geometrie; Querschnitte werden
  über Layer zugewiesen (`layer_sections={"Stuetzen": "HEB 200"}`) oder
  aus dem Standardquerschnitt.

## RFEM / RSTAB (Dlubal)

* **SAF** (RFEM 6: Datei → Exportieren → SAF): vollständigstes Format,
  einschließlich Lastfällen, Lastgruppen (ψ-Werte, Ausschlussgruppen) und
  Kombinationen. Profilnamen werden über die Profildatenbank aufgelöst
  (IPE, HEA/HEB/HEM, SHS/RHS/CHS; RFEM-Schreibweisen wie `HE A 200`,
  `QRO 100x5`, `RO 168.3x5` werden normalisiert), sonst aus den
  Kennwerten der Tabelle gebildet.
* **IFC** (Statikmodell): wie InfoCAD.
* **Tabellen nach Excel/CSV** (RFEM 5/6, RSTAB 8/9): Blätter „1.1 Knoten“,
  „1.2 Linien“, „1.3 Materialien“, „1.5 Querschnitte“, „1.7 Stäbe“,
  „1.8 Knotenlager“, „2.1 Lastfälle“, „2.5 Lastkombinationen“,
  „3.1 Knotenlasten“, „3.2 Stablasten“ (deutsch oder englisch). Der Parser
  ist kopfzeilengesteuert und liest Einheiten aus den Kopfzeilen
  (`[kN]`, `[mm]`). RFEM-Achsen: Z nach unten wird unverändert übernommen;
  Option `z_up=True` spiegelt.

## IFC-Statikmodell – Details

* Einheiten aus `IfcUnitAssignment` (Längen-, Kraft-, abgeleitete Einheiten).
* `IfcStructuralPointConnection` → Knoten; `IfcStructuralCurveMember` →
  Stab (PIN_JOINED/TENSION/COMPRESSION → Fachwerkstab), Gelenke aus den
  Verbindungsbedingungen; `IfcStructuralSurfaceMember` → Schalen
  (Polygone mit 3/4 Ecken direkt, größere als Fächer mit Warnung).
* Lager: `IfcBoundaryNodeCondition` (IFC4: Boolean = starr, Steifigkeitsmaß =
  Feder; IFC2x3: negativ/sehr groß = starr, positiv = Feder, 0 = frei).
* Lasten: `IfcStructuralPointAction` (Kräfte/Momente),
  `IfcStructuralLinearAction` (Streckenlasten), Flächenlasten; Lastfälle
  aus `IfcStructuralLoadCase`/`IfcStructuralLoadGroup` mit Kategorie aus
  ActionType/ActionSource (DEAD_LOAD_G → G, LIVE_LOAD_Q → Q, SNOW_S → S,
  WIND_W → W, TEMPERATURE_T → T, PRESTRESSING_P → P); Kombinationen aus
  Lastgruppen mit Faktoren.
* Materialien: Stahlsorten S235–S460 werden erkannt, sonst S235 mit
  Warnung. Profile: `IfcIShapeProfileDef`, `IfcRectangleHollowProfileDef`,
  `IfcCircleHollowProfileDef`, `IfcRectangleProfileDef`,
  `IfcCircleProfileDef`, sonst Datenbank über den Profilnamen.
* Fällt kein Statikmodell vor, werden `IfcBeam`/`IfcColumn`/`IfcMember`
  über ihre Achse bzw. Extrusion als Stäbe übernommen (Warnung im Protokoll).

## Abaqus / CalculiX (.inp)

Elementtypen B31/B32/B33 → beam, T3D2 → truss, S3/S3R/STRI3 → shell3,
S4/S4R → shell4, C3D4 → tet4, C3D10 → tet10 (Knotenreihenfolge wird
normalisiert), C3D8/C3D8I/C3D8R → hex8. `*BEAM SECTION` (RECT, CIRC, PIPE,
BOX, I), `*SHELL SECTION`, `*SOLID SECTION`, `*MATERIAL` (ELASTIC, DENSITY,
EXPANSION), `*BOUNDARY` (auch ENCASTRE/PINNED), `*CLOAD`, `*DLOAD` (P/Pn,
GRAV, PX/PY/PZ), `*NSET`/`*ELSET` (GENERATE), `*INCLUDE`; jeder `*STEP`
wird ein Lastfall. Einheiten: SI angenommen (`unit_scale`).

## Nastran (.bdf/.nas/.dat)

Small-, Large- und Free-Field-Format, Fortsetzungszeilen, Zahlen wie
`1.2-3`, `THRU`, `INCLUDE`. Lastkarten mit SID werden Lastfälle „SID n“;
`LOAD`-Karten werden Kombinationen. Nastran-Ebene 1 entspricht der lokalen
y-Achse (I1 → Iz, I2 → Iy); die Stabverdrehung folgt dem Orientierungsvektor.

## CAD (gmsh)

`pip install gmsh` (Linux zusätzlich `libglu1-mesa`). Optionen: `size`
(Netzweite), `order` (1 = Tet4, 2 = Tet10), `dim` (3 = Volumen, 2 = Schale),
`mat`, `shell_prop`.

## Eigene Formate

Jeder Importer ist eine Funktion `import_xxx(path, model=None, log=None,
**options) -> Model` in `statik3d/importers/`. Neue Formate werden in
`SUPPORTED` eingetragen und in `import_file` verzweigt. Hilfsfunktionen in
`_common.py`: Knotenindex mit Toleranz, Zahlen mit Dezimalkomma, Einheiten
aus Kopfzeilen, Polygon → Schalen, Standardmaterial/-querschnitt.


## RFEM 6 (.rf6): vollständiger Import aus der Modelldatenbank

Eine `.rf6`-Datei ist ein ZIP-Behälter; darin liegt `model.db`, eine
SQLite-Datenbank mit dem objektrelationalen Abbild des Modells. Dieser Aufbau
wurde an einer echten Projektdatei (RFEM 6.11/6.12) ausgelesen und wird von
`statik3d.importers.rfem6_db` vollständig gelesen — ohne Umweg über einen
Export. `import_file("modell.rf6")` genügt.

Aufbau der Datenbank (durchgehend dasselbe Muster):

| Ebene | Tabellen | Inhalt |
|---|---|---|
| Griff | `Node`, `Line`, `Member`, `Surface`, `Solid`, `Section`, `Material`, `NodalSupport`, `LineSupport`, `SurfaceSupport`, `MemberHinge`, `LoadCase` | `id`, `userID` (die Nummer in RFEM), `impl_id`, `impl_table` |
| Umsetzung | `NodeImplStandard`, `LineImplPolyline`, `LineImplArc`, `MemberImplTension`, `SurfaceImplPlane`, `NodalSupportImpl`, … | die eigentlichen Felder, z. B. `coordinates_x/y/z` |
| Listen | `<Umsetzung>_<Feld>`, z. B. `NodalSupportImpl_nodes`, `LineImplPolyline_definitionNodes` | Zielspalte je nach Tabelle `value_id` oder `reference_id` |
| Federn | `SpringConstants` (`owner_id`/`owner_table`), `SpringConstants_partialActivities` | Steifigkeiten, Nichtlinearität, Reibbeiwerte, teilweise Wirkung |

Federwerte: **`inf` = starr, `0` = frei, endlicher Wert = Federsteifigkeit**.

Übernommen werden Knoten, Linien (Polygonzüge und Bögen), Stäbe mit
Querschnitt, Material, Verdrehung und Gelenken, Knoten-, Linien- und
Flächenlager mit ihren Nichtlinearitäten, die Geometrie der Flächen sowie die
Lastfälle mit Name, Einwirkungskategorie und Eigengewichtsfaktor.

Querschnitte kommen aus `SectionData_parameterValues` mit ihren SI-Kennwerten
(A, A_y, A_z, I_y, I_z, I_t); der Name entsteht aus den Bemaßungssymbolen der
Parameterform, etwa `Rund 40` aus `d = 40 mm`. Materialnamen führt RFEM in der
Projektdatei nicht mit – nur Kennwerte und die Nummer des Eintrags in der
Dlubal-Materialdatenbank. Statik3D bildet den Namen deshalb aus E-Modul und
Streckgrenze (`S355`) und nennt die Datenbanknummer im Protokoll.

**Was ausdrücklich Annahme ist:** die Zahlenwerte der
Nichtlinearitäts-Aufzählung (`nonlinearityType…`). Belegt ist nur `0 = linear`.
Für alles andere gilt die Reihenfolge des RFEM-Dialogs; jede Kennzahl steht mit
Rohwert **und** Deutung im Importprotokoll, unbekannte Kennzahlen lassen den
Freiheitsgrad linear und erzeugen eine Warnung. Die Zuordnung lässt sich
ersetzen:

    m = import_file("modell.rf6", nonlinearity_map={1: ("druck", "Ausfall bei Druck")})
    # oder aus einem XSD/WSDL der RFEM-Web-Services (Namen sind dort veröffentlicht):
    from statik3d.importers.rfem6_db import nonlinearity_map_from_xsd
    m = import_file("modell.rf6", nonlinearity_map="C:/.../nodal_support.xsd")

Reibung steht in RFEM an dem Freiheitsgrad, dessen Kraft begrenzt wird
(`nonlinearityFrictionCoefficient_XZ` begrenzt F_x auf μ·|F_z|). Trägt ein
solcher Freiheitsgrad die Steifigkeit 0, hält er starr bis μ·|N| und gleitet
danach – so, wie RFEM es rechnet.

**Flächen und Volumen** werden als Geometrie gelesen, aber nicht vernetzt.
Flächenlager werden über das Randpolygon der zugewiesenen Flächen auf deren
Knoten gelegt, mit der Einflussfläche je Knoten (Newell-Formel, Summe = wahre
Fläche). Trägt ein Modell seine Lasten über Flächen und Volumen, sagt das
Protokoll das ausdrücklich:

    1831 Knoten tragen kein Element (Rand von Flaechen und Volumen).
    Das Stabtragwerk zerfaellt in 64 Teile (groesster Teil 2 Knoten).
    WARNUNG: 48 Teiltragwerke ohne Lager - so ist das Modell nicht rechenbar.

Mit `structure_only=True` bleibt nur das Stabtragwerk übrig; das Modell ist dann
unmittelbar rechenbar, die Flächengeometrie entfällt.

Ein Inhaltsverzeichnis ohne Modellaufbau liefert `rfem6_db.report(pfad)`:

    modell.rf6: programm RFEM version 6.11.0004 (RFEM 6-Schema, 4678 Tabellen)
      Knoten: 1959
      Linien: 2807
      Staebe: 64
      Flaechen: 1375
      Volumen: 108
      ...

## RFEM 5 / RSTAB: weitere native Projektdateien

`.rf5 .rfem .rs5 .rs6 .rs8 .rs9 .rstab` werden nicht pauschal
abgelehnt. Statik3D untersucht zuerst den Behälter der Datei
(`statik3d.importers.rfem_native.probe`) und liest ihn aus, soweit er
zugänglich ist:

| Befund | Vorgehen |
|---|---|
| SQLite-Datenbank | Tabellen werden gelesen und über Namensmuster zugeordnet |
| ZIP | enthaltene CSV-, XML-, JSON- und eingebettete SQLite-Dateien werden gelesen |
| OLE2-Verbunddatei | Datenströme werden aufgelistet und lesbare Inhalte ausgewertet |
| XML / JSON | direkt gelesen |
| unbekanntes Binärformat | genauer Befund: Kennung, Größe, gefundene Zeichenketten, eingebettete Behälter – **es wird nichts geraten** – dazu der Exportweg |

Dlubal veröffentlicht den Aufbau dieser Dateien nicht. Ob eine bestimmte Datei
gelesen werden kann, hängt deshalb an ihrem Behälter. Die Meldung sagt in jedem
Fall genau, was gefunden wurde. Sicher funktioniert immer der Export aus
RFEM/RSTAB nach **SAF (.xlsx)**, **IFC (Statikmodell)** oder **Tabellen nach
Excel/CSV**.

Erkannt werden Knoten, Linien, Stäbe, Materialien, Querschnitte,
Knotenlager, Linienlager, Flächenlager und Gelenke – jeweils mit deutschen und
englischen Spaltennamen. Lagerzellen dürfen Zusätze enthalten:

    starr, Ausfall bei Zug, Schlupf 0.003
    1.5e8                                     (Federsteifigkeit)
    rigid, failure in tension, friction mu 0.35

Steht der Reibbeiwert am Freiheitsgrad mit dem Ausfall (z. B. uz), wird er auf
die beiden Querrichtungen gelegt und auf ihn bezogen – so, wie die Reibung an
einer Lagerfläche wirkt.

## Profildatenbank nach Land

`statik3d.profiles` führt 442 Profile in 18 Reihen:

| Land | Norm | Reihen |
|---|---|---|
| Europa / Deutschland | EN 10365, DIN 1026, EN 10056, EN 10210 | IPE, HEA, HEB, HEM, UPN, UPE, L (gleich- und ungleichschenklig), SHS, RHS, CHS |
| Großbritannien | BS 4-1 | UB, UC, PFC |
| USA / Kanada | AISC | W, C, HSS, Pipe |

Alle Querschnittswerte werden aus den Nennabmessungen gerechnet. Gegen die
Herstellertabellen: EN- und BS-Profile unter 1 %, UPN bis 5 % (die
Zehenausrundung der geneigten Flansche ist nicht erfasst), AISC-Profile 1–4 %
(Ausrundung geschätzt, Hohlprofile mit der Bemessungswanddicke 0,93 t).

Winkel haben geneigte Hauptachsen: `Iy`/`Iz` sind die **Hauptträgheitsmomente**,
`alpha` ist deren Drehung gegen die Schenkel. Der Stab muss mit `roll = alpha`
eingebaut werden; `Iy_geo`, `Iz_geo`, `Iyz_geo` sind die Katalogwerte in
Schenkelrichtung.

## Zusammengesetzte Querschnitte

    from statik3d.sections import build, double_angle, double_channel, plated_i, box_from_plates
    s = double_channel("2 UPE 200", "UPE 200", gap=0.100, back_to_back=False)
    s = build("Kasten", [("UPE 300", -0.15, 0), ("UPE 300", 0.15, 0, 180)])

Teile werden mit Versatz, Drehung und Spiegelung zusammengesetzt; Fläche,
Schwerpunkt, Steiner-Anteile und Hauptachsen werden berechnet. `It` und `Iw`
sind die Summen der Teile (offene Profile ohne Verbund, bei Kästen auf der
sicheren Seite), `Wpl` eine Näherung; Nachweise laufen für zusammengesetzte
Querschnitte elastisch.
