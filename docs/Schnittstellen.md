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
| `.rf5`, `.rf6`, `.rfem`, `.rstab`, `.fem`, `.ifm` | proprietär (binär) | RFEM, RSTAB, InfoCAD | **nicht lesbar** – Meldung mit Exportweg |

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
