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
| `.json` | Statik3D | – | vollständiges Modell (Format 1 bis 5; Format 3 brachte Linien und Gelenke, Format 4 die **Anschlüsse**, die **Verformungsgrenzen**, die **Beulfelder** (mit Steifen) und die **Lasteinleitungsstellen**, Format 5 die **Volumenbereiche** und die Einstellungen zur **Theorie II. Ordnung**, Format 6 die **Flächen** und **Volumenkörper** der Geometriekette, die **Kontaktbedingungen** (früher „Flächenfreigaben“, der alte Schlüssel wird weiter gelesen) und die in den **Bericht übernommenen Ergebnisbilder**. Ältere Dateien werden gelesen) |
| `.dxf` | AutoCAD DXF (ASCII, R12–2018) | InfoCAD, RFEM, CAD | LINE, LWPOLYLINE, POLYLINE (2D/3D, Polyface), 3DFACE |
| `.ifc` | IFC 2x3 / IFC 4 STEP-Datei | InfoCAD, RFEM, Allplan, Revit, Tekla | Statikmodell (Structural Analysis View) oder Bauteilachsen |
| `.xlsx` | SAF – Structural Analysis Format | RFEM 6, SCIA, Allplan, AxisVM, Frilo | Materialien, Querschnitte, Knoten, Stäbe, Flächen, Lager, Lastfälle, Lastgruppen, Kombinationen, Lasten |
| `.xlsx`, `.csv`, Ordner | RFEM 5/6, RSTAB Tabellenexport | Dlubal | Knoten, Linien, Materialien, Querschnitte, Stäbe, Flächen, Knotenlager, Lastfälle, Kombinationen, Knoten-/Stablasten |
| `.inp` | Abaqus / CalculiX | FE-Programme | Netz, Sets, Materialien, Beam/Shell/Solid Sections, Boundary, CLOAD, DLOAD, Steps |
| `.bdf`, `.nas`, `.dat` | Nastran Bulk Data | FE-Programme | GRID, CBAR/CBEAM, CROD, CTRIA3/CQUAD4, CTETRA/CHEXA, PBAR/PBARL/PBEAM/PSHELL/PSOLID, MAT1, SPC/SPC1, FORCE/MOMENT, PLOAD2/PLOAD4, GRAV, LOAD |
| `.step`, `.stp`, `.iges`, `.igs`, `.brep`, `.stl` | CAD-Geometrie | CAD | Vernetzung mit gmsh (Volumen Tet4/Tet10 oder Schalen) |
| `.rf6` | RFEM 6 Projektdatei (ZIP + SQLite `model.db`) | RFEM 6 | Knoten, Linien, Stäbe mit Typ, Querschnitte, Materialien, Knoten-/Linien-/Flächenlager mit Nichtlinearität, Gelenke, Flächen mit Dicke, Volumenkörper, Kontaktbedingungen mit Typeinstellung, Lastfälle mit Flächenlasten |
| `.sdnf`, `.sdn` | SDNF – Steel Detailing Neutral Format | HiCAD, Tekla, SDS/2, Advance Steel | Bauteile mit Lage im Bauwerk, Profil, Werkstoff, Bleche |
| `.nc`, `.nc1`, `.nc2`, `.dstv` | DSTV-NC (Stahlbau-NC) | HiCAD, Tekla, bocad, Advance Steel | Teileliste: Profil, Länge, Werkstoff, Bohrungen, Konturen |
| `.sza`, `.kra`, `.fga`, `.fig` | HiCAD-Archiv (`!HFA##`, zstd) | HiCAD | Teileliste, Profile mit Katalogwerten, Blechdicken, Werkstoffe, Verbindungsmittel |
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

Übernommen werden Knoten, Linien (Polygonzüge, Bögen, Kreise, Parabeln,
Ellipsen und NURBS — jeweils über ihre Kontrollpunkte), Stäbe mit
Querschnitt, Material, Verdrehung, Typ und Gelenken, Knoten-, Linien- und
Flächenlager mit ihren Nichtlinearitäten, Flächen mit Dicke als Schalenelemente,
Volumenkörper einfacher Topologie als Volumenelemente, die Kontaktbedingungen mit
ihren Typeinstellungen sowie die Lastfälle mit Name, Einwirkungskategorie,
Eigengewichtsfaktor und den Flächenlasten.

### Linienarten: Bögen über ihre Kontrollpunkte

Eine krumme Linie ist in RFEM **nicht** durch ihre Definitionsknoten
bestimmt. Der dritte Punkt eines Bogens steht als *Kontrollpunkt* in einer
eigenen Tabelle:

    LineImplArc.controlPoint_id → ControlPoint.impl_id
                                → ControlPointImpl.coordinates_x/y/z

Ohne diesen Punkt bleibt von einem Bogen nur die Sehne durch seine beiden
Knoten. Das trifft nicht nur die Darstellung: eine **Bohrung, eine Buchse,
ein Bolzen oder ein Augenblech** ist in RFEM ein Kreis aus *zwei Halbbögen
zwischen denselben zwei Knoten*. Über die Knotenfolge sind das zwei Punkte
und damit kein Polygon — die Fläche fällt in ihre Sehne zusammen und ist
weder sichtbar noch anklickbar. In einer Lagerkonstruktion waren das
320 von 1375 Flächen.

Übernommen werden:

| RFEM-Tabelle | Linienart | woher die Form kommt |
|---|---|---|
| `LineImplPolyline` | Polylinie | die Definitionsknoten |
| `LineImplArc` | Bogen | Anfang, **Kontrollpunkt**, Ende |
| `LineImplCircle` | Kreis | `center_x/y/z`, `radius`, `normal_x/y/z` |
| `LineImplParabola` | Parabel | Anfang, **Kontrollpunkt**, Ende |
| `LineImplEllipticalArc`, `LineImplEllipse` | Ellipse | die beiden Hauptachsenpunkte und der Umfangspunkt |
| `LineImplNurbs` | NURBS | `LineImplNurbs_controlPoints` mit Gewichten, `degree` |
| `LineImplSpline` | Spline | genähert über die Definitionsknoten (wird gemeldet) |

Die Form steht danach in `Line.geometrie` und wird überall auf ihrer wahren
Kurve ausgewertet: beim Zeichnen, beim Zusammensetzen des Flächenrandes, beim
Flächeninhalt und beim Vernetzen. Was sich nicht rekonstruieren lässt, wird
zur Geraden — **mit** Meldung im Protokoll, nie stillschweigend:

    2807 Linien gelesen (1356x arc, ueber ihre Kontrollpunkte gefuehrt)

### Flächenarten

RFEM legt je Flächenart eine eigene Umsetzungstabelle an — der Tabellenname
**ist** die Art. Statik3D hält den Namen als Angabe fest (`SURFACE_ART` →
`Flaeche.quellart`) und leitet daraus ab, ob die Fläche **eben oder gewölbt**
ist (`SURFACE_TYP` → `Flaeche.typ`):

| RFEM-Tabelle | Art | `Flaeche.typ` | im Drehlagermodell |
|---|---|---|---|
| `SurfaceImplQuadrangle` | Viereck | `regelflaeche` | 782 |
| `SurfaceImplPlane` | Ebene | `eben` | 589 |
| `SurfaceImplTrimmed` | beschnitten | `beschnitten` | 4 |
| `SurfaceImplNurbs`, `…Rotated`, `…Pipe` | NURBS, Rotationsfläche, Rohrmantel | `regelflaeche` | — |

`Flaeche.typ` entscheidet **nur über das Bild**: eine Fläche mit `eben` wird
als ebenes Vieleck gezeichnet, eine mit `regelflaeche` oder `beschnitten` als
Coons-Fläche über ihre vier Randseiten, so dass sie auf dem Zylinder liegt.
Die Angabe darf dabei nur **zur Wölbung hin** entscheiden: findet die
geometrische Prüfung die Randpunkte nicht in einer Ebene, wird auch eine als
`eben` geführte Fläche gewölbt gezeichnet. Beide Wege irren so nur in eine
Richtung — die geometrische Prüfung kann eine gewölbte Fläche für eben
halten, nie umgekehrt. Am Drehlagermodell stimmen alle 1375 Flächen zwischen
RFEM-Art und geometrischer Prüfung überein.

`SurfaceImplQuadrangle` nennt außerdem seine vier **Eckknoten**
(`SurfaceImplQuadrangle_cornerNodes` → `Flaeche.ecken`) — im Drehlagermodell
bei allen 782 genau vier, auch bei denen mit fünf Randlinien. Daran wird der
Rand in die vier Seiten der Coons-Fläche geteilt; eine in zwei Linien
geteilte Gerade zählt damit nicht als eigene Seite. Die Eckknoten beschreiben
die **Topologie**, nie die Ebenheit.

Gerechnet und vernetzt wird weiterhin über die **Randlinien**, und die tragen
ihre wahre Form (Bogen, Gerade, Kontrollpunkte) selbst. Das ist nachprüfbar:
das Hüllvolumen von V29 — 10 seiner 13 Flächen sind Vierecke — trifft den
exakt gerechneten Ring auf 0,4 %.

### Stabtypen

RFEM 6 legt je Stabtyp eine eigene Umsetzungstabelle an — der Tabellenname
**ist** der Typ. Statik3D bildet ihn wie folgt ab (`rfem6_db.MEMBER_TYPES`):

| RFEM-Tabelle | Typ | Element | Hinweis im Protokoll |
|---|---|---|---|
| `MemberImplBeam` | Balken | `beam` | — |
| `MemberImplRigid` | starrer Stab | `beam` | — |
| `MemberImplRib` | Rippe | `beam` | die mitwirkende Plattenbreite fehlt |
| `MemberImplTruss`, `MemberImplTrussOnlyN` | Fachwerkstab | `truss` | — |
| `MemberImplTension` | Zugstab | `truss` | fällt in RFEM bei Druck aus – hier trägt er auch Druck |
| `MemberImplCompression` | Druckstab | `truss` | fällt in RFEM bei Zug aus – hier trägt er auch Zug |
| `MemberImplCable` | Seil | `truss` | Seiltheorie (Durchhang, Ausfall bei Druck) fehlt |
| `MemberImplBuckling` | Knickstab | `beam` | — |
| `MemberImplSpring`, `MemberImplDamper` | Feder-/Dämpferstab | `truss` | nur die Achssteifigkeit |
| `MemberImplCoupling…` | Kopplungen | `beam` bzw. `truss` | — |
| `MemberImplResultBeam`, `…ResultLine`, `…DesignStrip` | Auswerteobjekte | — | nicht übernommen |
| `MemberImplLoadTransfer`, `…SurfaceModel` | kein Tragglied | — | nicht übernommen |

Die gezählten Typen, die Hinweise und die nicht übernommenen Objekte stehen im
Importprotokoll:

    64 Staebe mit 64 Stabelementen gelesen
      Stabtypen: 64x Zugstab
    WARNUNG:   Stabtyp Zugstab: faellt in RFEM bei Druck aus - hier traegt er auch Druck.

Ein unbekannter Tabellenname wird als Balken übernommen und mit seinem Namen
genannt — eine neue RFEM-Version bleibt so lesbar.

### Netzeinstellungen

Die Vernetzungsvorgaben liegen **nicht** in der Modelldatenbank, sondern als
eigene Datei `mesh.xml` im Behälter. Ohne sie würde Statik3D mit seiner
eigenen Vorgabe vernetzen und ein Netz erzeugen, das mit dem in RFEM nichts
zu tun hat. Übernommen werden:

| Schlüssel in `mesh.xml` | Bedeutung |
|---|---|
| `E_VALUE_GENERAL_TARGET_LENGTH_OF_FE` | angestrebte Elementkantenlänge [m] |
| `E_VALUE_GENERAL_MAXIMUM_DISTANCE_BETWEEN_NODE_AND_LINE` | Fangabstand Knoten–Linie [m] |
| `E_VALUE_MEMBERS_NUMBER_OF_DIVISIONS_FOR_SPECIAL_TYPES` | Stabteilung |
| `E_VALUE_SURFACES_MAXIMUM_RATIO_OF_FE` | größtes Seitenverhältnis |
| `E_VALUE_SURFACES_SHAPE_OF_FINITE_ELEMENTS` | 0 Dreiecke, 1 Vierecke, 2 gemischt |
| `E_VALUE_SURFACES_MAPPED_MESH_PREFERRED` | abgebildetes Netz bevorzugen |

Fehlt die Datei, gilt die Programmvorgabe — und das Protokoll sagt es.

### Flächen: Dicke und Steifigkeitsart

Die Fläche zeigt über `stiffness_id`/`stiffness_table` auf ihr
Steifigkeitsobjekt; nur `SurfaceStiffnessStandard` (und die Membranformen)
tragen über `Thickness` → `ThicknessImplUniform` eine Dicke und ein Material.
Der Zeiger steht in **beiden Richtungen** in der Datenbank — rückwärts als
`SurfaceStiffness*.owner_id`/`owner_table`. In manchen Dateien ist die
Vorwärtsspalte leer; dann wird der Rückweg genommen. Ohne ihn wäre jede
Fläche „unbekannt" und rutschte als Null-Element durch.
**Jede** Fläche wird ein Modellobjekt `Flaeche` — mit ihren Randlinien
(`SurfaceImplPlane_boundaryLines` bzw. `…Quadrangle_boundaryLines`), ihrer
Dicke und ihrem Werkstoff. Sie steht damit im Modellbaum und in der Tabelle
„Flächen" und lässt sich dort weiterbearbeiten und vernetzen, auch wenn der
Import selbst kein Netz erzeugen konnte. Flächen mit Dicke werden zusätzlich
gleich vernetzt; gleiche Dicken teilen sich eine Schalenkennung (`d12` für
12 mm).

| Steifigkeitsart | trägt Dicke | Vorgehen |
|---|---|---|
| `SurfaceStiffnessStandard` | ja | Schalenelemente |
| `SurfaceStiffnessMembrane`, `…WithoutMembraneTension` | ja | Schalenelemente |
| `SurfaceStiffnessWithoutThickness` | nein | Null-Element, keine Elemente |
| `SurfaceStiffnessRigid` | nein | starre Fläche, keine Elemente |
| `SurfaceStiffnessLoadTransfer`, `…LoadDistribution` | nein | reine Lastverteilung |
| `SurfaceStiffnessGroundwater`, `…Discontinuity`, `…Modifications` | nein | keine Elemente |
| `SurfaceStiffnessFloor`, `…FloorDiaphragm(Version1)`, `…FloorFlexibleDiaphragm(Version1)`, `…FloorSemirigid(Version1)` | nein | Deckenscheiben, keine Elemente |

Alle 18 Arten, die RFEM 6.11 kennt, stehen in `rfem6_db.SURFACE_STIFFNESS`.
Eine Art, die dort fehlt (neue RFEM-Version), wird **nicht** stillschweigend
zum Null-Element: trägt ihre Tabelle eine `thickness_id`, wird die Dicke
übernommen und die Art im Protokoll beim Namen genannt.

Zwei Fälle bleiben **absichtlich** ohne Elemente, weil ein stillschweigend zu
steifes Modell schlimmer ist als eine sichtbare Lücke:

* Flächen mit **Öffnung** — das Randpolygon allein würde die Öffnung schließen.
* Flächen mit **veränderlicher Dicke** werden mit dem Mittelwert gerechnet und
  gemeldet.

### Flächenlasten ohne Netz

RFEM hängt eine Flächenlast an die **Fläche**. Ist die Fläche beim Import noch
nicht vernetzt — in einem Volumenmodell ist sie das nie, dort ist sie die
Randfläche eines Körpers —, gäbe es kein Element, an das die Last gehen könnte.
Sie wird darum als `Geometrielast` am Objekt gehalten und beim Vernetzen
verteilt (`Model.lasten_verteilen`). Auf einer Volumen-Randfläche geht sie auf
die Seitenflächen der anliegenden Tetraeder; welche das sind, merkt sich der
Vernetzer beim Vernetzen (`Flaeche.randseiten`).

Die Probe ist das Gleichgewicht: die Summe der Auflagerkräfte muss p · A sein.

### Öffnungen

Eine Bohrung ist in RFEM kein Loch im Randpolygon, sondern ein eigenes Objekt:
`Opening` → `OpeningImpl_boundaryLines`. Die Fläche zeigt über
`SurfaceImpl*_integratedOpenings` darauf. Die Randlinien der Öffnung gehören an
die Fläche (`Flaeche.oeffnungen`), sonst würde ein Flansch mit 28
Schraubenlöchern beim Vernetzen zubetoniert — eine viel zu steife Platte, und
niemand sähe es. Im Beispielmodell sind es 376 Öffnungen auf 100 Flächen.

### Volumenkörper

Ein Volumenkörper steht in `Solid` → `SolidImplStandard` mit seinen
Randflächen (`SolidImplStandard_boundarySurfaces`). Ohne 3D-Vernetzer lassen
sich daraus nur die beiden einfachen Topologien bilden:

| Randflächen | Eckknoten | Element |
|---|---|---|
| 6 Vierecke | 8 | `hex8` |
| 4 Dreiecke | 4 | `tet4` |

Die Reihenfolge der Randflächen ist beliebig; Boden und Deckel des Hexaeders
werden über die gemeinsamen Knoten der Seitenflächen zugeordnet und die
Jacobi-Determinante geprüft (bei negativem Vorzeichen werden Boden und Deckel
getauscht).

Alles andere geht an den **freien Vernetzer** (`statik3d/mesher3d.py`, siehe
Theoriehandbuch Kapitel 6a): die Randflächen werden in Dreiecke geteilt, die
Hülle auf Dichtheit geprüft und mit Tetraedern gefüllt. Im Beispielmodell einer
Lagerkonstruktion sind das alle 108 Körper — 427 717 Tetraeder in 67 s, mit
einer Volumenabweichung von 0,0008 % gegenüber den Randhüllen.

Beide abgebildeten Topologien gelten nur, wenn **jede** Randfläche ein ebenes
Vieleck mit mindestens drei Knoten ist. Eine Buchse hat vier Randflächen und vier Knoten
— zwei Kreisdeckel und zwei Zylinderhälften — und sähe sonst aus wie ein
Tetraeder; sie wäre ein Element ohne Volumen und eine singuläre Matrix. Ein
Körper mit krummen Randflächen bleibt darum ohne Netz, und das steht an ihm
und im Protokoll. Ebenso wird ein „Tetraeder", dessen vier Knoten in einer
Ebene liegen, verworfen und gemeldet. Auch hier wird **jeder** Körper ein Modellobjekt
`Volumenkoerper` mit seinen Randflächen — Körper mit Bohrungen, Zylinder und
Freiformflächen bekommen nur kein Netz, und der Grund steht dabei:

    108 Volumenkoerper nicht uebernommen (Randflaechenzahl 4: 48x, 6: 23x, 9: 18x, …)
    - dafuer waere ein 3D-Vernetzer noetig.

### Kontaktbedingungen und ihre Typeinstellungen

Was RFEM „Flächenfreigabe“ nennt (`SurfaceRelease`), heißt in Statik3D
**Kontaktbedingung** — es ist eine Kontaktfuge. Sie trennt in RFEM die freigegebenen
Flächen von den Objekten, an denen sie hängen, und verbindet beide über die
Federn des Freigabetyps (`SurfaceReleaseType` →
`SurfaceReleaseTypeImplVersion1` → `SpringConstants`, hier **unmittelbar** über
`springConstants_id`, nicht über `owner_id` wie bei den Lagern). Ist
`defineReleaseTypeForEachObject` gesetzt, gilt **je Objekt ein eigener Typ**:
`SurfaceReleaseImpl_releaseTypeForObjects_values` ist dann so geordnet wie
`assignedToObjects`, der i-te Typ gehört zum i-ten Objekt (beide Container
werden nach `container_order` gelesen).

Statik3D **teilt eine solche Freigabe auf** — je Typ eine Kontaktbedingung mit
ihren eigenen Gegenflächen, benannt „<Name> (Typ n)". Einen Typ für alle zu
nehmen wäre in beide Richtungen falsch: an der Fuge „Achse" des geprüften
Drehlagers tragen 48 von 52 Objekten den haftenden Typ (die Passstifte) und 4
den freien — der erste Typ hätte 48 Passstiften das Haften genommen. Am
„Montageauge" ist es umgekehrt: 32 haftende gegen 9 freie Objekte, und ein
Haften wäre auf Fugen gekommen, die es in der Datei nicht haben. Lässt sich die
Zuordnung nicht herstellen (verschieden viele Typen und Objekte), bleibt es
beim ersten Typ und das Protokoll warnt.

Statik3D liest alles heraus — Name, Ort, freigegebene Flächen und Volumen,
Zuordnung, Federkonstante je Freiheitsgrad samt Ausfalltyp und Reibbeiwert —
und legt jede Freigabe als **Modellobjekt** `Kontaktbedingung` an (der alte
Name `Flaechenfreigabe` bleibt als Zweitname stehen). Sie steht damit im
Modellbaum unter „Kontaktbedingungen → Flächenkontakte" und in der
gleichnamigen Tabelle, wird mitgespeichert und überlebt Rückgängig:

    Achse: 56 freigegebene Flaechen, 1 Volumen, zugeordnet an 52 Objekte, Ort Anfang
      Typ 3: ux=frei, uy=frei, uz=frei (Ausfall bei Zug), phix=frei, …
      Typ 4: ux=starr, uy=starr, uz=frei (Ausfall bei Zug), phix=frei, …

#### Zwei Listen — und welche die Fuge ist

Eine Flächenfreigabe führt zwei Listen, und sie bedeuten Verschiedenes:

| Tabelle | Inhalt |
|---|---|
| `SurfaceReleaseImpl_releasedSolids` | **was** gelöst wird: der Körper |
| `SurfaceReleaseImpl_releasedSurfaces` | dessen Flächen — bei einem gelösten Volumen seine **ganze Außenhaut** |
| `SurfaceReleaseImpl_assignedToObjects` | **woran** die Freigabe hängt: die Flächen der Fuge (`reference_table = 'Surface'`); stehen dort Volumen, sind es Zielkörper |

**Die Fuge ist `assignedToObjects`.** `releasedSurfaces` ist es nicht: für die
Grundplatte eines Lagerbocks stehen dort 36 Flächen über 1,65 m² — Ober- und
Unterseite, alle Schmalseiten, alle Buchsenmäntel —, von denen nur ein
Bruchteil an einer Fuge liegt. Die zugeordneten Flächen sind dagegen genau die
Fuge; bei einem Passstift steuert er exakt seine beiden Mantelhälften bei.

Statik3D setzt darum: gibt es einen gelösten Körper **und** zugeordnete
Flächen, ist `flaechennamen` (die Kontaktseite) **leer**, `koerpernamen` der
gelöste Körper und `gegenflaechen` die Fuge; beim Ausführen werden die
Randseiten des Körpers gesucht, die auf diesen Flächen liegen. Fehlt
`releasedSolids`, wird der gelöste Körper aus den freigegebenen Flächen
erschlossen, sofern sie alle zu einem Körper gehören. Nur wenn weder ein
gelöster Körper noch zugeordnete Flächen dastehen — eine reine
Flächen-an-Flächen-Freigabe —, sind die freigegebenen Flächen selbst die
Kontaktseite.

    Lagerbock-Grundplatte: 36 freigegebene Flaechen, 1 Volumen, zugeordnet an 5 Objekte
      Fuge: der Koerper V14 wird an den 5 zugeordneten Flaechen der Gegenseite
      getrennt (beim Vernetzen); die 36 freigegebenen Flaechen sind die
      Aussenhaut dieses Koerpers und nicht die Fuge

*Bis Version 1.x* galten die freigegebenen Flächen als Kontaktseite. Das
trennte das Netz an Flächen ohne Gegenüber und paarte Knoten über Zentimeter
Luft hinweg: an der genannten Grundplatte fanden nur 24 % der Kontaktseite eine
Gegenseite, bei einem mittleren Spalt von 28,9 mm und einem Suchradius von
45 mm. Modelle, die vorher eingelesen wurden, sind **neu zu importieren**.

Zum Ausführen der Fuge bleibt die Gegenseite trotzdem eine **geometrische**
Suche (aufeinanderliegend, entgegengesetzt gerichtet): die zugeordneten Flächen
sagen, **wo** die Fuge liegt, nicht Knoten für Knoten, welcher gegen welchen
steht.

**Ausgeführt** wird die Trennung beim Vernetzen von selbst — oder von Hand über
„Kontaktfugen ausführen". Wie das geschieht, steht im Theoriehandbuch,
Abschnitt 4.0. Das Feld `ausgefuehrt` und die Tabellenspalte „Trennung
ausgeführt" sagen, ob und wie:

    Kontaktbedingung Achse: 58 Randknoten getrennt, Kontaktpaar mit 438 Knoten
      gegen 272 Gegenflaechen (geloest: V30)
    7 Kontaktfugen ausgefuehrt: 335 Fugenknoten, 0 Spaltelemente, 0 Kopplungen,
      7 Kontaktpaare

### Lastfälle und Lasten

Jeder Lastfall kommt mit Name (als Beschreibung), Einwirkungskategorie
(`actionCategoryId` → G/Q) und Eigengewichtsfaktor. Die Lasten hängen über
`parentModelObject_id`/`_table` am Lastfall:

| Last | Vorgehen |
|---|---|
| Knotenlast (`NodalLoad`) | Kraft und Moment je Achse, an alle zugewiesenen Knoten |
| Flächenlast (`SurfaceLoad` → `SurfaceTypeLoadImplForce`) | auf die Schalenelemente der vernetzten Zielfläche gelegt; ist die Fläche noch nicht vernetzt, bleibt die Last als **Geometrielast** an ihr hängen und wird beim Vernetzen verteilt |
| **Freie Rechtecklast** (`FreeRectangularLoad`) | als Geometrielast mit Fenster und Richtung – siehe unten |
| **Stabvorspannung** (`MemberTypeLoadImplInitialPrestress`) | als gleichwertige Temperaturlast (siehe unten) |
| Linienlast, Volumenlast | gemeldet – sie brauchen das Linien- bzw. Volumennetz |

**Freie Rechtecklasten.** RFEM legt das Lastfenster in die uv-Ebene eines
eigenen Koordinatensystems (`coordinateSystem_id` → `CoordinateSystem…
2PointsAndAngle`: Ursprung, ein Punkt auf der u-Achse, Drehwinkel der
uw-Ebene). Übernommen wird das Rechteck als Wirkungsbereich, die dritte Achse
w als **Lastrichtung**, und die Last wirkt auf die **projizierte** Fläche.

Dass das so gemeint ist, lässt sich am Modell ablesen und nicht nur vermuten:
die Zielfläche ist eine Bohrung (Halbzylinder, r = 0,3 m, Länge 0,23 m), das
Fenster misst 0,23 × 0,6 m — Länge mal Durchmesser, also genau die Projektion
der Bohrung. Die Achse w steht senkrecht auf der Bohrungsachse und dreht sich
von Lastfall zu Lastfall: die Lastrichtung eines Drehlagers. Die Summe kommt
damit auf p · d · l heraus, die Lagerkraft. Als Druck senkrecht zur Fläche
gedeutet höbe sich dieselbe Last über den Zylinder auf, und alle 420 Lastfälle
wären kräftefrei. Der Rohwert von `loadDirection` steht im Protokoll.

**Vorspannung.** Eine Vorspannkraft N₀ im Stab ist mechanisch gleichwertig zu
einer aufgezwungenen Verkürzung ε₀ = −N₀/(EA), also einer Temperaturänderung

    ΔT = −N₀ / (E · A · α)

Am voll behinderten Stab kommt damit genau N₀ heraus; im statisch
unbestimmten System verteilt die Rechnung die Kraft richtig um. So kommt die
Vorspannung an, ohne dass das Programm eine eigene Vorspannlast bräuchte —
und das Protokoll sagt es, damit niemand die Temperaturlast für ein Versehen
hält.

### Strukturmodifikation: das Ausfallszenario

`StructureModification` schaltet Stäbe, Flächen, Volumen und Lager ab; die
Lastfälle, deren `isStructureModificationEnabled` gesetzt ist, rechnen mit
diesem **verkleinerten System**. Statik3D legt daraus eine **Stellung** (sie
verschiebt nichts, sie schaltet nur ab) und eine **Situation** an, und jeder
betroffene Lastfall bekommt sie.

Welche Objekte gemeint sind, steht in zwei `ObjectSelection`-Listen: je
Objektart ein Wähler, und nur der mit `typeActive` zählt. Sein Wert ist eine
gepackte Nummernliste (`ObjectListConditionValue.objects_packed`,
`"288-290,293,304-307"`), und die Nummern sind die **benutzersichtbaren**
(`userID`), nicht die Datenbankschlüssel.

Im Drehlagermodell heißt die eine „Ankerausfall": sie nimmt Stab 14 und das
Knotenlager an Knoten 775 heraus — nicht alle 16 Knoten des Lagers „Fest",
sondern genau dieses eine —, und 128 der 422 Lastfälle verweisen darauf.

Zwei Dinge werden dabei gesagt statt verschwiegen:

* Ändert die Modifikation außerdem **Steifigkeiten** (Faktoren auf E, G,
  Querschnitts- und Flächensteifigkeit), bildet Statik3D das nicht ab und
  meldet es. Im Drehlagermodell stehen alle 15 Faktoren auf 0.
* Eine **Kombination folgt ihren Lastfällen** in die Situation. Mischt sie
  Lastfälle aus zwei Situationen, sind das zwei verschiedene Tragwerke; sie
  lässt sich nicht in einem Zug rechnen. In RFEM ist so eine
  Ergebniskombination eine Umhüllende über beide Systeme, und so wird sie
  übernommen: **je Situation ein Teil** („… (Grundstellung)“,
  „… (Ankerausfall)“) mit den Lastfällen dieser Situation, derselben Art und
  derselben Bemessungssituation; die Teile stehen an der Stelle des Originals
  und gemeinsam in derselben Umhüllenden. Im Drehlagermodell betrifft das
  2 der 52 Kombinationen mit je 64 Lastfällen aus dem Ausfall — bis zum
  10.09.2026 blieben sie ungeteilt in der Grundstellung stehen, der Löser
  wies sie ab, und die ganze Rechnung stand. Eine von Hand gemischte
  Kombination weist er weiterhin ab.

### Liniengelenke

`LineHinge` sagt, was eine Fläche entlang einer ihrer Randlinien weitergibt;
die Zuweisung steht in `SurfaceImplPlane_surfaceLineHingeAssignments`.
Übernommen wird sie als Angabe an der Fläche (`Flaeche.gelenklinien` und
`Flaeche.gelenkwirkung` im Klartext).

Im Drehlagermodell trägt das eine Gelenk `ux = uy = uz = starr` und keine
Drehfeder — Verschiebungen durch, Verdrehungen frei — und ist 128-mal
zugewiesen, je zweimal an genau die 64 Flächen mit `SurfaceStiffnessRigid`.
Das sind die Kreisscheiben, über die die Zugstäbe an den Volumen hängen.

**Die Rechnung ändert das nicht, und zwar nachweislich:** die starre Scheibe
wird als Kopplung umgesetzt, die drei Richtungen führt und in der
Steifigkeitsmatrix ausschließlich auf Verschiebungsfreiheitsgraden steht
(`assemble.kopplungen` verwendet `_trans_dofs`). Ein Moment geht dort nicht
durch — die Freigabe der Verdrehungen hat nichts freizugeben. Die
Volumenelemente unter der Scheibe haben ohnehin keine
Verdrehungsfreiheitsgrade.

### Kombinationen

`LoadCombination` überlagert in RFEM die Lasten vor der Rechnung,
`ResultCombination` die Ergebnisse danach. Eine Lastkombination wird als
Kombination mit ihren Faktoren (`modelObjectFactor` × `groupFactor`)
übernommen. Eine **Ergebniskombination** ist in der Regel keine Summe,
sondern eine **Umhüllende**: ihre Zeilen sind mit „oder" verknüpft, und das
Ergebnis ist Minimum und Maximum je Ergebnisgröße über die Alternativen.

**Operatoren, gemessen an allen 52 Ergebniskombinationen des
Drehlagermodells:** `ResultCombinationImpl_items.operator` ist zwischen allen
Zeilen 0 und auf der jeweils letzten Zeile 2 (127 × 0, dann 2). Der
RFEM-Dialog zeigt dazu „oder" und die Syntax `LF1/p oder bis LF24/p oder …`:
**0 = oder**, **2 = Ende der Liste**. Jeder andere Wert (vermutlich „und")
kommt in der Datei nicht vor; solche Zeilen werden summiert und das Protokoll
nennt den Wert. `modelObjectLoadType` ist an allen 720 Einträgen 1 =
**ständig** (`/p`, immer wirksam); andere Lasttypen (veränderlich: nur wenn
ungünstig) werden als ständig übernommen und genannt. Einträge, die keine
Lastfälle sind, werden gezählt und genannt.

So wird aus „Bemessungskombination im GZT" eine Kombination mit **64
Alternativen je Situation** (Grundstellung und Ankerausfall, siehe oben), jede
ein einzelner Lastfall mit Faktor 1; der Löser bildet daraus die Umhüllende,
ohne einen einzigen Lastfall neu zu lösen (Theoriehandbuch, Kapitel 3). Bis
zum 10.09.2026 wurden die 128 Zeilen **summiert** — die GZT-Werte wären um
ein Vielfaches zu groß gewesen. Das Protokoll nennt jede Umhüllende mit der
Zahl ihrer Alternativen.

Die **Bemessungssituation** steht entweder als Kennzahl an der Kombination
(`designSituationType`, ältere Dateien) oder — so im Drehlagermodell — an
einer eigenen `DesignSituation`, auf die `designSituation_id` zeigt. Aus ihr
kommen zwei Dinge: die **Art** der Kombination (`DesignSituationImpl.
designSituationTypeId`; **7505 = Ermüdung**, daraus wird `typ = "FAT"`;
**7007 = GZT** und **6193 = GZG charakteristisch**, abgelesen an EK1
„Bemessungskombination im GZT" und EK2 „Maßgebende char.Kombination" des
Drehlagermodells, deren Bemessungssituationen in der Datei keinen Namen
tragen) und ihr **Name** (`Combination.bemessungssituation`). Unbekannte
Kennzahlen werden als GZT geführt **und genannt**.

> **Zwei verschiedene Dinge heißen „Situation".** `Combination.situation` ist
> die *bauliche* Situation — Stellung und abgeschaltete Elemente —, mit ihr
> wird gerechnet. `Combination.bemessungssituation` ist der Name aus der
> Norm bzw. der Quelldatei („GZT (FAT) – Ermüdung – …"); sie ändert am
> Gleichungssystem nichts. Wer beides verwechselt, lässt den Löser nach einer
> Stellung suchen, die es nicht gibt.

Im Drehlagermodell sind **50 der 52 Kombinationen Ermüdungssituationen**: das
Modell ist die Ermüdungsuntersuchung eines Brückendrehlagers. Sie bekommen
eine eigene Umhüllende „FAT" und gehen nicht in die Querschnittsnachweise im
GZT ein.

**Ermüdungslasten aus den Ermüdungskombinationen.** Jede FAT-Kombination
wird eine Ermüdungslast (`fatigue_loads`) mit einem Verlauf über ihre
Zustände in Dateireihenfolge und der Zählung `spanne`: Schwingbreite =
Maximum minus Minimum über die Zustände, ein Spiel je Wiederholung — die
Schwingbreite, die RFEM aus der Ergebniskombination bildet. Lastspielzahlen
führt die Datei nicht (0 von 422 Lastfällen): die Lasten tragen
`wiederholungen = None`, es gilt die **globale Lastspielzahl** der
Nachweiseinstellungen (`ermuedung_lastspiele`, Nachweise → Konfiguration),
je Last im Dialog Ermüdungslast überschreibbar. Enthält die Zustandsmenge
einer Kombination die einer anderen mit mindestens zwei Zuständen
vollständig, ist sie eine **Sammlung** von Ereignissen und bekommt 0
Wiederholungen (unwirksam), damit nichts doppelt zählt; ein einzelner
Zustand wird gegen den Nullzustand angesetzt; ein Zustand, der selbst eine
Summe mehrerer Lastfälle ist, wird genannt und übergangen. Am Drehlager: 50
Ermüdungslasten, 47 Verläufe mit 2 bis 82 Zuständen und 3 Sammlungen
(„Ermüdungslastfalle – Drehlager Ost/West" mit je 82 Zuständen über 26
Ereignissen, „… Ost – Offen" mit 9 über 6); „… Ost – Öffnen/Schließen" (65
Zustände) enthält kein Ereignis vollständig und bleibt ein Verlauf. Alles
steht im Protokoll.

**Kerbfälle** führt die Datei ebenfalls nicht. Der Import ruft
`ec3.kerbfaelle.anwenden`: Zugstäbe mit Rundquerschnitt 50 N/mm² (Tabelle
8.1, Kerbfall 14), gewalzte Querschnitte 160 N/mm² (Kerbfall 1,
Grundwerkstoff), Volumen 160 N/mm² mit dem Konzept Strukturspannung — als
Vorschlag markiert (`kerbfall_vorschlag`), in Stab- und Volumenmaske zu
prüfen. Am Drehlager: 64 Zugstäbe (Rund 16/20/40) mit 50, 108 Volumen mit
160.

**Vorspannung.** Die Datei enthält keine (0 von 422 Lastfällen,
`MemberTypeLoadImplEndPrestress` leer). Eine Minderung der Schwingbreite
durch Vorspannung entsteht erst durch die Nichtlinearität der verspannten
Fuge und verlangt je Zustand eine Kombination „Vorspannung + Zustand" mit
Kontakt im Verlauf; in der linearen Überlagerung hebt sich eine konstante
Vorspannung in der Differenz zweier Zustände heraus.

Enthält eine Ergebniskombination Klammern oder Zwischenergebnisse, wird das
gemeldet: die Überlagerung innerhalb einer Alternative trifft die Absicht
dann nur bei linearer Rechnung.

Die Lastrichtung (`loadDirection`) steht mit Rohwert und Deutung im Protokoll
(`0 = lokal z`, `1 = global Z`, `2 = global X`, `3 = global Y`) — die Deutung
folgt der Reihenfolge des RFEM-Dialogs und ist damit Annahme.

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

Flächenlager werden über das Randpolygon der zugewiesenen Flächen auf deren
Knoten gelegt, mit der Einflussfläche je Knoten (Newell-Formel, Summe = wahre
Fläche). Trägt ein Modell seine Lasten über Flächen ohne eigene Dicke und über
Volumenkörper, die ein 3D-Netz brauchen, sagt das Protokoll das ausdrücklich:

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

## HiCAD (ISD Software und Systeme)

### Archivdateien .SZA / .KRA / .FGA / .FIG

Diese Dateien tragen die Kennung `!HFA##` (HiCAD File Archive). Der Aufbau
wurde an echten Dateien aus HiCAD 2024 ausgelesen:

| Bereich | Inhalt |
|---|---|
| Kopf `0x00` | `!HFA##`, Versionsfelder, Erzeuger („ISD Software & Systeme GmbH – Dortmund", UTF‑16LE) |
| Einträge ab `0x198` | je Eintrag **1024 Byte Name** (UTF‑16LE, mit 0 aufgefüllt), **72 Byte Kopf**, dann die Daten |
| Kopf | `u32[1]` = Beginn des nächsten Eintrags, `u32[13]` = Packverfahren (**3 = Zstandard**), `u32[16]` = gepackte, `u32[17]` = rohe Größe, drei FILETIME‑Zeitstempel |
| große Teile | über 1 MiB folgen weitere Blöcke mit je 8 Byte Vorspann (gepackt/roh) |

Ein `.SZA` enthält typischerweise:

    <nr>.SZN            Szene (Geometrie, Behälter „FILE-CONTAINER ISD 1.0")
    <nr>.POM            Bauteilmodell („ISD_POM_3.1")
    <nr>.SZN.ATC        Attribute – hier stehen die Bauteilbezeichnungen
    <nr>.SZN.DBA2/DBA3  Bemaßung,  .DVI Darstellung,  .ANS Ansichten
    <nr>.SZN.ELREF      Bauteilverweise (XML),  .ITM_* Positionsnummern (XML)
    VIEWER.GFIG         Anzeigegeometrie („HiGDI")
    PREVIEW.DIB         Vorschaubild (Windows-Bitmap)
    *.IPT               Teiletabellen: die im Modell benutzten Profile,
                        Bleche, Werkstoffe und Verbindungsmittel

**Was gelesen wird:** das Archiv vollständig, dazu alle Teile mit offenem
Format. Aus den mitgelieferten Teiletabellen (`ISD Part Table File`) werden die
**tatsächlich verwendeten Profile mit ihren Katalogwerten** übernommen –
Fläche, I_y, I_z, Abmessungen – ebenso Blechdicken, Werkstoffe und die
Verbindungsmittel. Die Bauform steht in der Kategorie der Tabelle
(`U-PROFIL_GENEIGTE_FLANSCHE`, `I-PROFIL_PARALLELE_FLANSCHE`,
`L-PROFIL_GLEICHSCHENKLIG`, `FLACHSTAHL`, `RUNDSTAHL`, `HOHLPROFIL_QUADRATISCH`,
`BLECH`, `SECHSKANTSCHRAUBE` …); daraus folgen die Spalten.

Beispiel aus einer echten Datei:

    Profil 'HEB 700': A = 306,38 cm², I_y = 256888 cm⁴, I_z = 14441 cm⁴
    Profil 'L 100x75x8': A = 13,57 cm², I_y = 165,5 cm⁴
    Blech 'Bl 20': t = 20 mm
    Verbindungsmittel: ISO 4017-M12x35 (M12), ISO 4032-M16 (M16), DIN 910-M36x1.5

Führt die Werkstofftabelle andere Festigkeiten als die Norm zur Bezeichnung,
gilt die Norm (EN 10025‑2) und die Abweichung steht im Protokoll.

#### Geometrie aus dem Szenenteil (SZN)

Der Szenenteil ist **kein undurchdringliches Binärformat**. Er beginnt mit der
Kennung `FILE-CONTAINER ISD  1.0` und ist ein Strom aus **Fortran‑Sätzen**: jeder
Satz steht zwischen zwei gleichen 32‑Bit‑Längen, wie es die unformatierte
sequentielle Ausgabe von Fortran schreibt. Die Satzkette endet in beiden
Prüffiles punktgenau am Dateiende – das ist der Beleg, dass der Aufbau stimmt.

Der Behälter ist in Abschnitte geteilt (`FILE-CONT-SECTION`, dann Größe,
Namenslänge, Name): `SZN_HEA` (Kopf), `SZN_KRP` (Körper), je Bauteil ein
`SZ_LEAF` mit `CESF_LF` und `TFBF_LF`, am Ende `ENDTREE`. Ein `SZ_LEAF` führt
Nummer, Anzahl und die Eintragsliste mit **40 Byte je Eintrag**: drei `float64`
als Koordinate in Millimetern, dann vier `uint32`. Der zweite davon ist die Art:

| Art | Bedeutung |
|---|---|
| 1 | Konstruktionspunkt (Kontur, Hilfspunkt) |
| 2 | Eckpunkt des Körpers |
| 5 | Richtungsvektor (Einheitsvektor) |
| **4003** | **Achse des Bauteils – zwei Punkte, Anfang und Ende** |
| 50003 | Bezugssystem (Ursprung und zwei Achspunkte) |

Die Art 4003 ist der Schlüssel: **HiCAD nennt die Stabachse selbst.** Sie wird
unmittelbar übernommen, der Querschnitt senkrecht dazu aus den Eckpunkten
gemessen und in den benutzten Teiletabellen gesucht:

```
Teil  8: L =  5518 mm, gemessen 206.0 x  78.9 mm -> 'U 200'      (Abw. +6.0 / +3.9 mm)
Teil 14: L =   928 mm, gemessen 100.1 x  20.0 mm -> 'Fl 100x10'  (Abw. +0.1 / +10.0 mm)
Teil 57: L = 12900 mm, gemessen 701.2 x 302.8 mm -> 'HEB 700'    (Abw. +1.2 / +2.8 mm)
```

Die große Abmessung steht in der Punktwolke genau; die kleine darf nur **nach
oben** abweichen, weil die Wolke auch Punkte angeschweißter Nachbarteile
enthält. Ein Profil, das breiter wäre als gemessen, kann es darum nicht sein und
wird verworfen. Passt kein Katalogprofil, entsteht ein Ersatzrechteck aus den
gemessenen Maßen – benannt `gemessen 91x26`, damit es niemand für ein
Katalogprofil hält. Führt HiCAD ein Bauteil und die daran angeschweißte
Baugruppe mit **derselben** Achse, wird das Blatt mit dem kleineren Querschnitt
behalten – das Profil selbst, nicht die Baugruppe. Teile unter 100 mm Länge
(Schrauben, Stifte) werden nicht zu Stäben.

**Anschlüsse.** Ein Querstab endet in HiCAD an der Außenkante des Pfostens;
seine Achse läuft um die halbe Profilhöhe daneben vorbei. Das Stabmodell
zerfällt dadurch zunächst in Teile – das steht mit dem gemessenen Abstand im
Protokoll. Die Option `anschluss=0.06` (in der Oberfläche „Freie Stabenden
anschließen", Suchradius 60 mm) lotet jedes freie Ende auf die Achse des
nächsten Stabes und teilt diesen dort. Der Versatz steht im Protokoll; die
**Ausmitte des Anschlusses wird nicht abgebildet**.

**Was das ist und was nicht.** Ein Stabmodell an der richtigen Stelle, kein
Nachbau des Volumenmodells: Bleche, Verbindungsmittel, Ausschnitte und die
Flächen‑/Kantentopologie (`CESF_LF`/`TFBF_LF`, `VIEWER.GFIG`) sind nicht
enthalten. Wer die genaue Geometrie braucht, nimmt weiterhin den von HiCAD
vorgesehenen Weg: **SDNF** (Bauteile mit Lage im Bauwerk), **DSTV‑NC**
(Einzelteile), **IFC** oder **STEP**.

An den beiden Prüffiles:

| Datei | Ergebnis |
|---|---|
| `OH_ÄUSSERE DAMMTAFEL_RECHTS_BESTAND.SZA` (3,1 MB) | 18 Stäbe, 36 Knoten: 4 × U 200, 10 × Fl 100x10, 2 × Fl 60x20, 1 × Fl 65x12, 1 Ersatzrechteck (Notenprofil) |
| `TAFELLEHNE_BESTAND.SZA` (11,2 MB) | 76 Stäbe, 150 Knoten, darunter ein HEB 700 mit 12,90 m |

Zum Entpacken wird das Paket `zstandard` benötigt (in `requirements.txt` und in
der Windows‑exe enthalten).

### SDNF – Steel Detailing Neutral Format (.sdnf, .sdn)

Textformat mit der Lage im Bauwerk; HiCAD, Tekla, SDS/2 und Advance Steel
schreiben es. Gelesen werden Paket 00 (Einheit), Paket 10 (lineare Bauteile mit
beiden Endpunkten, Profil, Werkstoff, Verdrehung) und Paket 20/21/22 (Bleche
mit vier Eckpunkten und Dicke).

Der Satzaufbau wird aus der Datei selbst bestimmt: Das Paket nennt die Anzahl
seiner Sätze, die Zeilenzahl je Satz folgt daraus. Innerhalb eines Satzes sind
die Zeichenketten in Anführungszeichen die Bezeichner und der längste
zusammenhängende Zahlenblock die Geometrie. So werden alle SDNF‑Fassungen
gelesen, ohne eine feste Feldreihenfolge zu unterstellen.

### DSTV‑NC (.nc, .nc1, .nc2, .dstv)

„Standardbeschreibung Stahlbau-Teile für die NC-Steuerung" des DSTV. Eine Datei
beschreibt ein Teil: Kopfblock `ST` mit Auftrag, Position, Werkstoff, Profil,
Profilcode und Länge, dann `BO` (Bohrungen), `AK`/`IK` (Konturen), `EN`.

Gelesen werden Datei, Ordner und ZIP. Je Teil entsteht ein Stab der richtigen
Länge mit Profil und Werkstoff; ist die Bezeichnung nicht in der
Profildatenbank, wird der Querschnitt aus den Kopfmaßen gebildet (Profilcode
I, U, L, M, R, RU/RO, B, C, T). NC‑Dateien führen **keine Lage im Bauwerk** –
die Teile liegen nebeneinander, es entsteht eine Teileliste. Für das
zusammengebaute Tragwerk ist SDNF oder IFC der Weg.

## Export: Modelle in fremde Formate schreiben

`statik3d.exporters.export_model(modell, "ziel.endung")` — das Format folgt aus
der Endung. In der Oberfläche: **Datei → Exportieren…** (Strg+E), auf der
Kommandozeile `--export DATEI` (mehrfach möglich, `--formate` listet auf), im
Browser unter **Mehr → Export** (Format wählen, „Herunterladen“).

Über die Web-API gibt es zwei Wege:

* `POST /api/op {"op": "export", "path": "…"}` schreibt die Datei **auf dem
  Rechner, auf dem der Server läuft** (für die Desktop-GUI und den eigenen PC).
* `GET /api/export?fmt=.sdnf` liefert die Datei als Download an den Browser —
  ohne Datei auf dem Server. Formate, die einen Ordner schreiben (`.csv`,
  `.nc1`), kommen dabei als ZIP. `GET /api/state` nennt unter
  `export_formats` alle Endungen mit Klartext.

| Endung | Format | Inhalt |
|---|---|---|
| `.json` | Statik3D-Modell | **verlustfrei**, alles |
| `.sdnf` | SDNF 3.0 | Bauteile mit Lage im Bauwerk, Profil, Werkstoff, Verdrehung; Bleche mit Eckpunkten und Dicke |
| `.nc1` / `.zip` | DSTV-NC | je Stab eine Datei: Kopfblock, Profil, Länge, Werkstoff, Kontur |
| `.ifc` | IFC 4 (Structural Analysis View) | Knoten, Stäbe, Flächen, Lagerbedingungen, Lastfälle mit Knotenlasten |
| `.xlsx` | SAF | Knoten, Stäbe, Flächen, Querschnitte, Materialien, Lager, Lastfälle, Kombinationen, Lasten |
| `.csv` | Tabellen im RFEM-Aufbau | zehn Blätter in einem Ordner, vom eigenen Tabellenimport wieder lesbar |
| `.dxf` | AutoCAD DXF | Stäbe als LINE, Schalen und Volumenaußenflächen als 3DFACE, Lager und Beschriftung auf eigenen Layern |
| `.inp` | Abaqus / CalculiX | Knoten, Elemente, Materialien, Querschnitte, Randbedingungen, ein Step je Lastfall |
| `.bdf` | Nastran Bulk Data | GRID, CBAR/CTRIA3/CQUAD4/CTETRA/CHEXA, PBAR/PSHELL/PSOLID, MAT1, SPC1, FORCE/MOMENT/GRAV |
| `.stl` | STL (binär oder ASCII) | Schalen und Volumenaußenflächen als Dreiecke |
| `.vtu` | VTK für ParaView | Netz **mit Ergebnissen**: Verformung, Verdrehung, Auflagerkräfte, Normalkraft, Moment, Vergleichsspannung |
| `.sza` | HiCAD-Archiv | Behälter mit SDNF, DSTV-NC, Teiletabellen und XML-Teilen |

**Der Rückweg ist geprüft:** Was Statik3D auch lesen kann, wird in
`tests/test_exporters.py` exportiert, wieder eingelesen und verglichen —
Knotenzahl, Stäbe, Profilkennwerte, Lager, Lastfälle.

### Zum HiCAD-Archiv (.sza)

Der Behälter wird richtig geschrieben und liest sich wieder ein. Die
**Körpergeometrie** (Flächen, Kanten, Ausschnitte) steht in Teilen, die hier
nicht gedeutet werden – nur die Bauteilachsen werden gelesen (siehe oben).
Eine hier geschriebene `.sza`
enthält deshalb **kein von HiCAD lesbares Modell**, sondern die enthaltene
SDNF-Datei, die DSTV-NC-Teile, die Teiletabellen der benutzten Profile und
Werkstoffe sowie die XML-Teile. Wer das Modell **in HiCAD** haben will, nimmt
die SDNF-Datei — das ist der Weg, den HiCAD selbst vorsieht.

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
