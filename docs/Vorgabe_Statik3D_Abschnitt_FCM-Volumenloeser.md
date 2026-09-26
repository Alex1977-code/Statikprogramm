# Statik3D – Abschnitt: Volumenlöser nach der Finite-Cell-Methode (FCM) mit matrixfreiem GPU-Mehrgitter

> Ergänzung zu `Vorgabe_Statik3D_v3.md`. Dieser Abschnitt beschreibt ein eigenständiges Modul „FCM-Solid“ für lokale Volumen-Detailberechnungen (Knotenbleche, Lagerungen, Kerbdetails, Ermüdung), das an das globale Stab-/Schalenmodell gekoppelt wird. Technologieneutral formuliert; konkrete Bibliotheken sind als Optionen genannt.

---

## 1. Ziel und Abgrenzung

**Ziel:** Volumenbauteile beliebiger Geometrie (CAD, STL, Punktwolke, Voxel/CT) linear-elastisch berechnen, **ohne klassisches Vernetzen**, mit Genauigkeit vergleichbar zu quadratischen Tetraeder-/Hexaedernetzen (Tet10/Hex20) und Rechenzeiten im Sekunden- bis Minutenbereich für 10⁶–10⁸ Freiheitsgrade auf einer GPU.

**Einsatz:**
- Detailnachweise im Stahlwasserbau, Stahlbau, Fördertechnik, beweglichen Brücken
- Struktur- und Kerbspannungen für Ermüdungsnachweise (EC3-1-9, DIN 19704, IIW-Empfehlungen)
- Berechnung von Bestandsbauteilen direkt aus Scan-Daten (Scan-to-Analysis)

**Nicht im Umfang Stufe 1:** Materialnichtlinearität, Kontakt, große Verformungen, Dynamik. Diese sind in Abschnitt 12 als Ausbaustufen vorgesehen; die Datenstrukturen müssen sie aber zulassen. Vollständige nichtlineare Mehrkörpermodelle (z. B. Drehlager mit Kontakt und Plastizität) werden in **Abschnitt 16** als Hybridansatz aus FE-Hexaedern und FCM beschrieben.

**Grundprinzip:** Das Bauteil Ω wird in ein achsparalleles Rechengebiet (Box) eingebettet. Die Box wird mit einem adaptiven Octree zerlegt. Die Geometrie geht **nur über eine Innen/Außen-Funktion** in die Integration ein. Zellen außerhalb entfallen, geschnittene Zellen werden anteilig integriert, Ansatzfunktionen höherer Ordnung (p = 2…4) sorgen für Genauigkeit trotz grober Zellen.

---

## 2. Architekturüberblick

```
Geometrie-Eingang ──► Geometriekern (SDF / Innen-Außen-Test)
                              │
                              ▼
                  Octree-Aufbau & Verfeinerung ◄── Fehlerschätzer (adaptiv)
                              │
                              ▼
              Integration geschnittener Zellen (Quadraturpunkte + Gewichte)
                              │
                              ▼
  Randbedingungen (Nitsche) ◄─┼─► Lasten (Oberflächenquadratur)
                              │
                              ▼
     Matrixfreier Operator K·u (GPU)  +  Mehrgitter-Vorkonditionierer
                              │
                              ▼
                     PCG-Löser (mehrere Lastfälle)
                              │
                              ▼
     Spannungsrückgewinnung ──► Nachweise (Struktur-/Kerbspannung) ──► Ergebnis-UI
```

Kopplung an das Globalmodell (Abschnitt 9) liefert die Randverschiebungen des Detailausschnitts.

---

## 3. Geometrie-Eingang und Geometriekern

Alle Eingänge werden auf **eine gemeinsame Abfrageschnittstelle** abgebildet:

```
interface GeometryQuery {
  inside(p: Vec3) -> bool            // Punkt im Material?
  signedDistance(p: Vec3) -> f64     // optional, beschleunigt Schnittsuche
  surfaceTriangles(cellBox) -> Tri[] // Oberflächenstück für Randintegrale
  boundingBox() -> Box3
}
```

| Eingang | Umsetzung Innen/Außen | Oberfläche für Randintegrale |
|---|---|---|
| STL / Oberflächennetz (wasserdicht) | Generalisierte Winding Number bzw. Strahltest, beschleunigt mit BVH | Dreiecke direkt |
| CAD (STEP/B-Rep) | Tessellierung → wie STL (Stufe 1); exakte B-Rep-Abfrage später | Tessellierung |
| Voxel / CT | Schwellwert auf interpolierte Dichte | Marching Cubes |
| **Punktwolke** | Rekonstruktion einer impliziten Fläche (Screened Poisson oder SDF aus orientierten Normalen), dann Nullniveau | Marching Cubes auf SDF |
| Parametrische Grundkörper (Blech, Bohrung, Kehlnaht) | CSG-Baum aus analytischen SDFs | analytisch / tesselliert |

**Anforderungen:**
- Toleranz gegen nicht perfekt geschlossene Netze (Winding Number statt reinem Strahltest).
- CSG-Operationen (Vereinigung, Differenz, Schnitt) auf SDF-Ebene, damit Nutzer z. B. Bohrungen oder Schweißnahtgeometrien ergänzen können.
- Für Punktwolken: Unsicherheitsinformation (Punktdichte, Rauschen) mitführen und im Ergebnis ausweisen, da Wandstärken aus Scans fehlerbehaftet sein können.
- Beschleunigungsstruktur (BVH) einmalig aufbauen, Abfragen parallelisierbar (auch auf GPU).

---

## 4. Octree-Datenstruktur

- **Linearer Octree** mit Morton-Codes (Z-Order): speichereffizient, GPU-tauglich, einfache Nachbarsuche.
- **2:1-Balancierung:** Nachbarzellen unterscheiden sich um höchstens eine Ebene.
- **Zellklassifikation:** `OUTSIDE` (verworfen), `INSIDE` (Standardintegration), `CUT` (Sonderintegration).
- **Hängende Knoten:** Durch Balancierung entstehen hängende Knoten bzw. Kanten/Flächen. Konformität wird über **Constraint-Gleichungen** hergestellt (Freiheitsgrade der feineren Seite werden aus der gröberen interpoliert). Diese Constraints werden im matrixfreien Operator direkt angewendet, nicht als Matrix assembliert.
- **Verfeinerungskriterien:**
  1. Geometrisch: Zellen mit starker Oberflächenkrümmung, dünnen Wandstärken (weniger als ca. 2 Zellen über die Dicke) und scharfen Kanten.
  2. Nutzervorgabe: Verfeinerungsboxen/-kugeln an Kerben, Schweißnahtübergängen, Bohrungen.
  3. Adaptiv: Fehlerschätzer (Abschnitt 8.3) nach erstem Lösungslauf.
- **Adaptivität in h und p:** Zellgröße (h) und Polynomgrad (p) sind pro Zelle einstellbar; Stufe 1 darf global einheitliches p verwenden, die Struktur muss variables p aber zulassen.

---

## 5. Ansatzfunktionen

**Standard Stufe 1:** Hierarchische Ansätze auf Basis integrierter Legendre-Polynome im Tensorprodukt-Raum (Trunk- oder Tensorprodukt-Raum), p = 2…4, 3 Verschiebungs-Freiheitsgrade je Ansatzfunktion.

Begründung:
- Hierarchische Basis erleichtert p-Adaptivität und p-Mehrgitter.
- Tensorproduktstruktur ermöglicht **Summenfaktorisierung** (Abschnitt 7), was den matrixfreien Operator erst effizient macht.

**Option später:** B-Splines höherer Glattheit (Anknüpfung an isogeometrische Analyse), dann glattere Spannungen ohne Rückgewinnung.

---

## 6. Integration geschnittener Zellen

Kernproblem der FCM: Die Integranden sind in geschnittenen Zellen wegen der Materialgrenze unstetig.

**Verfahren Stufe 1 – rekursive Unterteilung (Integrations-Octree):**
- Geschnittene Zelle wird für die Integration (nicht für die Ansätze) rekursiv bis Tiefe k (Vorgabe 3–5) unterteilt.
- In Teilzellen: Gauß-Quadratur (p+1)³, Punkte außerhalb erhalten Gewicht α·w.
- **Fiktiver Materialfaktor α** = 10⁻⁸ … 10⁻¹⁰ für den Außenbereich (verhindert Singularität, beeinflusst Ergebnis vernachlässigbar). Parameter nutzerseitig einstellbar, Standard 10⁻⁸.

**Verfahren Stufe 2 – Effizienzsteigerung:**
- **Moment Fitting:** Pro geschnittener Zelle ein reduzierter, angepasster Quadratursatz (ca. (p+1)³ Punkte mit angepassten Gewichten), der die Momente des Materialanteils exakt integriert. Das reduziert die Punktanzahl gegenüber rekursiver Unterteilung erheblich.
- Alternativ: Oberflächenbasierte Integration (Divergenzsatz) bei vorhandener Oberflächentriangulierung.

**Vorberechnung:** Quadraturpunkte und Gewichte der geschnittenen Zellen werden einmal berechnet und gespeichert (auf der GPU), da sie für alle Lastfälle gleich sind.

**Qualitätsprüfung:** Für jede geschnittene Zelle wird das integrierte Volumen gegen eine Referenz (feine Unterteilung) geprüft; Abweichungen über Toleranz führen zu lokaler Nachverfeinerung.

---

## 7. Randbedingungen und Lasten

Da Ränder nicht auf Zellgrenzen liegen, können Knotenlagerungen nicht direkt gesetzt werden.

- **Dirichlet-Randbedingungen (Lager, eingeprägte Verschiebungen, Kopplung):** **Nitsche-Verfahren** (variational konsistent, stabil). Stabilisierungsparameter β zellweise aus lokalem Eigenwertproblem oder Heuristik β = C·E·p²/h. Alternativ Penalty als einfachere Rückfalloption.
- **Neumann-Randbedingungen (Flächenlasten, Wasserdruck):** Integration über die Oberflächentriangulierung innerhalb jeder geschnittenen Zelle. Wasserdruck als hydrostatische Funktion der Höhe (Anknüpfung NN/NHN-Bezug aus dem Globalmodell).
- **Volumenlasten:** Eigengewicht über Volumenquadratur.
- **Symmetrierandbedingungen:** auf Box-Ebenen direkt als Freiheitsgrad-Constraint, sonst über Nitsche.

---

## 8. Löser

### 8.1 Matrixfreier Operator
- Es wird **keine globale Steifigkeitsmatrix** gespeichert. Das Produkt v = K·u wird zellweise berechnet:
  - `INSIDE`-Zellen gleicher Größe und gleichen Materials sind bis auf den Maßstab identisch; mit **Summenfaktorisierung** sinkt der Aufwand je Zelle von O(p⁶) auf O(p⁴).
  - `CUT`-Zellen verwenden die vorgespeicherten Quadratursätze aus Abschnitt 6; optional wird für sie die lokale Zellmatrix gespeichert (Abwägung Speicher/Rechenzeit, konfigurierbar).
- Zusammenführung in den globalen Vektor über Atomics oder Graphfärbung (Zellen gleicher Farbe teilen keine Freiheitsgrade).
- Hängende-Knoten- und Dirichlet-Constraints werden im Operator angewendet.

### 8.2 Iteratives Verfahren
- **Vorkonditioniertes CG** (K ist symmetrisch positiv definit).
- **Mehrere Lastfälle:** Block-CG oder parallele PCG-Läufe mit gemeinsam genutztem Vorkonditionierer.
- Abbruch: relatives Residuum ≤ 10⁻⁸ (einstellbar), zusätzlich Energie-Norm-Kontrolle.

### 8.3 Mehrgitter-Vorkonditionierer
- **Stufe 1: p-Mehrgitter** (p → p−1 → … → 1) auf feinster Octree-Ebene, darunter **geometrisches h-Mehrgitter** über die Octree-Ebenen.
- Glätter: **Chebyshev-Jacobi** (gut parallelisierbar, keine Datenabhängigkeiten, GPU-tauglich).
- Grobgitter: direkter Sparse-Löser auf der CPU (kleines System, z. B. CHOLMOD/PARDISO/Eigen).
- **Problem kleiner Schnittzellen:** Zellen mit sehr kleinem Materialanteil verschlechtern die Kondition. Gegenmaßnahmen (mindestens eine umsetzen, Auswahl konfigurierbar):
  1. **Zellaggregation:** Freiheitsgrade kleiner Schnittzellen werden an die Nachbarzelle mit großem Materialanteil gebunden.
  2. **Additiver Schwarz-Glätter** mit Patches um schwach gestützte Freiheitsgrade.
  3. **Ghost-Penalty-Stabilisierung.**
- Ziel: Iterationszahl nahezu unabhängig von Modellgröße und Schnittlage (Richtwert < 100 Iterationen für 10⁻⁸).

### 8.4 Fehlerschätzer
- Residuenbasierter oder Spannungssprung-basierter Schätzer je Zelle.
- Steuert adaptive h- und p-Verfeinerung; 2–4 adaptive Zyklen, danach Konvergenzaussage.

---

## 9. GPU-Umsetzung

- **Abstraktionsschicht** für Rechen-Backends, damit CPU (Referenz, Debugging) und GPU dieselben Ergebnisse liefern. Statik3D ist in Python geschrieben, daher:
  - Array-Schnittstelle nach dem Array-API-Standard, sodass derselbe Code mit `numpy` (CPU) und `cupy` (GPU) läuft; Backend-Wahl über `FcmSettings.backend`.
  - Rechenintensive Kernels (Zelloperator mit Summenfaktorisierung, Glätter): CPU mit `numba` (`@njit(parallel=True)`), GPU mit `cupy.RawKernel` oder `numba.cuda`. Keine Python-Schleifen über Zellen oder Quadraturpunkte.
  - Grobgitterlöser und CPU-Referenz: `scipy.sparse` mit `scikit-sparse` (CHOLMOD) oder `pypardiso`.
  - Geometriekern: `trimesh` bzw. eigene BVH für STL, `open3d` für Punktwolken, `pythonocc-core` bzw. `cadquery` für STEP.
  - Option für spätere Leistungsstufe: Kernels in C++/CUDA über `pybind11`, Python bleibt Steuerschicht.
- **Datenlayout:** Structure of Arrays, Zellen nach Typ (INSIDE je Ebene / CUT) gruppiert, damit Kernels ohne Verzweigung laufen.
- **Genauigkeit:** Operator und Glätter in FP32 zulässig (**Mixed Precision**), äußere CG-Iteration und Residuum in FP64. Endergebnis muss FP64-Referenz auf 10⁻⁶ relativ treffen.
- **Speicherbudget:** Zielgröße 10⁷ Freiheitsgrade auf einer GPU mit 16 GB. Speicherbedarf wird vor dem Lauf abgeschätzt und angezeigt.
- **Fallback:** Ohne geeignete GPU läuft alles auf der CPU (langsamer, aber identische Ergebnisse).

---

## 10. Kopplung an das Globalmodell (Submodelltechnik)

Das Detailmodell wird als **Ausschnitt** des Globalmodells definiert (Schnittebenen bzw. Schnittbox).

- **Stufe 1 – einseitige Kopplung (Global → Lokal):**
  - Aus dem Globalmodell werden am Schnittrand die Verschiebungen interpoliert und über Nitsche als Randverschiebung aufgebracht.
  - **Stab → Volumen:** Querschnittskinematik aus den 6 (bzw. 7 mit Verwölbung) Stab-Freiheitsgraden: Starrkörperverschiebung + Rotation der Querschnittsebene + (optional) Verwölbungsanteil. Schnittstelle muss in ausreichendem Abstand zur Kerbe liegen (Hinweis auf Saint-Venant-Prinzip; Warnung, wenn Abstand < ca. 1× Querschnittshöhe).
  - **Schale → Volumen:** Mittelflächenverschiebung + Rotation → lineare Verteilung über die Dicke.
  - Alternativ Kraftrandbedingungen (Schnittgrößen) mit Starrkörperlagerung, wählbar.
- **Kontrolle:** Vergleich der Schnittgrößen am Schnittrand (Integration der Volumenspannungen) mit den Schnittgrößen des Globalmodells; Abweichung wird im Ergebnis ausgewiesen.
- **Stufe 2 – zweiseitige Kopplung:** Volumen-Steifigkeit wirkt auf das Globalmodell zurück (Schur-Komplement / Mortar-Kopplung), für Bereiche, in denen das Detail die Globalsteifigkeit beeinflusst.
- **Stellungen und Lastfälle:** Für jede Stellung (bewegliche Brücken, Verschlüsse) und jeden Lastfall werden die Randverschiebungen übernommen; das Detailmodell muss **nicht neu aufgebaut** werden, nur die rechte Seite ändert sich. Das ist ein wesentlicher Effizienzvorteil.

---

## 11. Ergebnisse und Nachweise

### 11.1 Spannungsrückgewinnung
- Spannungen an Quadraturpunkten, geglättet über Superconvergent-Patch-Recovery oder L²-Projektion.
- **Auswertung an der echten Oberfläche** (nicht an Zellknoten): Spannungen werden an den Oberflächentriangulierungs-Punkten ausgewertet.

### 11.2 Ermüdungsrelevante Auswertungen
- **Strukturspannung (Hot-Spot):** Lineare Extrapolation aus Referenzpunkten im Abstand 0,4·t und 1,0·t vom Nahtübergang (IIW Typ a); Referenzpunkte werden automatisch entlang eines vom Nutzer definierten Nahtverlaufs erzeugt.
- **Kerbspannung (Effective Notch Stress):** Modellierung mit fiktivem Kerbradius r_ref = 1 mm an Nahtübergang/-wurzel über CSG-Geometrie; lokal automatische Verfeinerung auf mindestens die normativ empfohlene Auflösung.
- **Spannungsschwingbreiten** aus Lastfall-/Stellungsdifferenzen, Übergabe an das Ermüdungsmodul (EC3-1-9, DIN 19704).
- Hauptspannungen, Vergleichsspannung nach von Mises, Spannungskomponenten im Nahtkoordinatensystem.

### 11.3 Darstellung
- Farbverläufe auf der Oberflächentriangulierung, Schnitte, Isoflächen.
- Konvergenzkurve (Spannung am Hotspot über Freiheitsgrade/Zyklen) als Pflichtbestandteil jedes Detailnachweises.
- Ergebnisprotokoll mit Einstellungen (p, Verfeinerung, α, Toleranzen, Kopplungsart), damit Nachweise prüffähig sind.

---

## 12. Ausbaustufen

| Stufe | Inhalt |
|---|---|
| 1 | Linear-elastisch, Geometrie aus STL/CSG, rekursive Integration, Nitsche, CPU-Referenzlöser, Global→Lokal-Kopplung für Stäbe |
| 2 | GPU-Operator mit Summenfaktorisierung, p/h-Mehrgitter, Moment Fitting, Schalenkopplung, Hot-Spot-Auswertung |
| 3 | Punktwolken- und CT-Eingang, adaptive hp-Verfeinerung, Kerbspannungskonzept, Stellungs-Batch-Rechnung |
| 4 | Zweiseitige Kopplung, lineare Beulanalyse (Eigenwertproblem, LOBPCG mit Mehrgitter-Vorkonditionierer) |
| 5 | Mehrkörpermodelle mit Kontakt und Plastizität als Hybrid FE-Hexaeder/FCM, Lastpfade mit Checkpoints, große Verformungen – Details und Reihenfolge in Abschnitt 16 |
| 6 | Reduzierte Modelle / Surrogate für schnelle Variantenstudien über viele Stellungen |

---

## 13. Verifikation und Akzeptanzkriterien

Automatisierte Testsuite, bei jedem Build ausgeführt:

| Test | Referenz | Kriterium |
|---|---|---|
| Patch-Test (konstante Dehnung, schräg geschnittenes Gebiet) | exakt | Fehler < 10⁻⁶ |
| Konvergenz Kragbalken (Volumen) | Balkentheorie mit Schubkorrektur | Konvergenzrate gemäß p nachweisbar |
| Dickwandiger Zylinder unter Innendruck | Lamé-Lösung | Spannungsfehler < 1 % bei moderatem Aufwand |
| Scheibe mit Loch unter Zug | Kirsch-Lösung (K_t → 3 bei unendlicher Scheibe) bzw. Tabellenwerte für endliche Breite | Fehler < 2 % |
| Schnittlagen-Robustheit | gleiches Bauteil, Box um Bruchteile einer Zelle verschoben | Ergebnisstreuung < 1 %, Iterationszahl stabil |
| Kleine Schnittzellen | gezielt erzeugte Schnittanteile 10⁻⁶ | Löser konvergiert, keine Ausreißer |
| Kopplung Stab → Volumen | Schnittgrößenvergleich | Abweichung < 1 % |
| Vergleich mit Referenzprogramm | identisches Detail in RFEM/Ansys mit Tet10 | Hotspot-Spannung < 3 % |
| CPU vs. GPU | CPU-FP64 | relativ < 10⁻⁶ |
| Performance | 10⁶ Freiheitsgrade | Lösung < 60 s auf Referenz-GPU (Ziel) |

---

## 14. Risiken und Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| Schlechte Kondition durch kleine Schnittzellen | Zellaggregation / Schwarz-Glätter (8.3), Robustheitstests (13) |
| Ungenaue Spannungen direkt an der Oberfläche | Auswertung an echter Oberfläche, Recovery, adaptive Verfeinerung, Konvergenznachweis |
| Dünne Bleche (wenige Zellen über die Dicke) | Dickenkriterium in der Verfeinerung; für dünnwandige Bereiche Schale im Globalmodell bevorzugen |
| Fehlerhafte oder offene Eingabegeometrie | Winding Number, Geometrieprüfung mit Warnungen vor dem Rechnen |
| Unsichere Scan-Geometrie | Unsicherheit ausweisen, Sensitivitätsrechnung Wandstärke ±Δ |
| Prüffähigkeit gegenüber Prüfingenieur | vollständiges Protokoll, Konvergenzstudie, Vergleich mit klassischer FEM als Option |

---

## 15. Einbindung in Statik3D (Modellbaum und Ribbons)

Grundsatz: **kein eigenes Ribbon.** Das Volumendetail wird als eigenes Teilsystem geführt; die vorhandenen Ribbons zeigen kontextabhängig passende Gruppen, je nachdem, ob im Modellbaum das Globalmodell, eine Stellung oder ein Detailmodell aktiv ist. Typen und Schnittstellen gemäß `Schnittstellenvertrag_Statik3D_FCM.md`.

### 15.1 Modellbaum
- Neuer Knoten **„Detailmodelle (Volumen)“** auf gleicher Ebene wie die Stellungen als Subsysteme.
- Je Detail (`DetailModelSpec`): Geometriequelle, Material, Schnittebenen, Verfeinerungsbereiche, Nahtverläufe, Einstellungen, Ergebnisse.
- Aktivieren eines Details schaltet die Ribbons in den Detail-Kontext; die 3D-Ansicht zeigt das Detail, das Globalmodell transparent im Hintergrund.

### 15.2 Ribbon „Modellieren“ bzw. „Einfügen“
- Gruppe **„Volumendetail“**: *Aus Globalmodell ausschneiden* (Schnittbox/-ebenen interaktiv), *Geometrie importieren* (STL, STEP, Punktwolke, Voxel), *CSG ergänzen* (Bohrung, Kerbradius, Nahtgeometrie), *Nahtverlauf definieren*.

### 15.3 Ribbon „Netz“
- **Globalmodell aktiv:** unverändert (Stab-/Schalenvernetzung).
- **Detailmodell aktiv:** Gruppe **„Volumen-Diskretisierung“** statt der FE-Vernetzungsgruppen:
  - Basiszellgröße, Polynomgrad p
  - Verfeinerungsbereiche setzen/bearbeiten
  - *Diskretisierung erzeugen* (ruft `prepare`) mit Octree-Vorschau (Zellen farbig nach INSIDE/CUT, Ebene)
  - Kennzahlen aus `estimate`/`summary`: Freiheitsgrade, Schnittzellen, Speicherbedarf, Warnungen (z. B. zu wenige Zellen über die Blechdicke)
- Intern nutzen beide Varianten dieselbe Abstraktion `Discretization` (`FE_MESH` bzw. `FCM_OCTREE`).

### 15.4 Ribbon „Berechnung“
- Neue Berechnungsart **„Volumendetails (FCM)“** neben den bestehenden Berechnungsarten.
- Optionen: Backend (Auto/CPU/GPU), Toleranz, adaptive Zyklen, Konvergenzstudie, Kopplungsart (Verschiebung/Kräfte), Auswahl der Lastfälle/Stellungen/Kombinationen.
- Ablaufsteuerung: Globalmodell muss für die gewählten `ResultKey`s gerechnet sein; sonst Angebot, es zuerst zu rechnen. „Alles berechnen“ rechnet Globalmodell → Details in dieser Reihenfolge.
- Fortschrittsanzeige und Abbruch über `ProgressCallback`/`cancel`.

### 15.5 Ergebnisse, Auslastungspanel, Tabellen
- Ergebnisansicht: Verschiebungen, Spannungskomponenten, Vergleichsspannung, Hauptspannungen auf der Detailoberfläche; Schnitte, Isoflächen.
- Konvergenzkurve und Kopplungskontrolle (Schnittgrößenabweichung) als feste Bestandteile jedes Detailergebnisses.
- **Auslastungspanel:** Ermüdungs- und Spannungsauslastungen der Detailpunkte erscheinen in der Gesamtübersicht, mit Sprung zum Detail.
- **Ergebnistabellen:** Hot-Spot-/Kerbspannungen je Punkt, Lastfall, Stellung, Kombination; Filter und Export wie im übrigen Programm.
- Protokoll (`DetailResult.protocol`) fließt in den Ausdruck bzw. Nachweisbericht ein.

---

## 16. Mehrkörpermodelle mit Kontakt und Plastizität (Hybrid FE/FCM)

Typen und Protokolle: `Schnittstellenvertrag_Statik3D_FCM.md`, Abschnitte 6a und 7a (ab Vertragsversion 1.1).

### 16.1 Ziel und Leitbeispiel
Vollständige nichtlineare Volumenmodelle von Baugruppen, Leitbeispiel **Drehlager im Stahlwasserbau**: Lagerbolzen, Lagerbuchse (Gleitlagerwerkstoff), Lagerbock bzw. Lagerlaschen, ggf. Bolzensicherung. Zu erfassen sind Lagerspiel, Kontakt mit und ohne Reibung, lokale Plastizierung an Kontakt- und Kerbstellen sowie die Lastgeschichte über Stellungsfolgen.

### 16.2 Hybridprinzip
Jeder Körper wählt seine Diskretisierung selbst (`Body.discretization`):

| Körper | Diskretisierung | Begründung |
|---|---|---|
| Rotationskörper (Bolzen, Buchse, Ringe, Scheiben) | **FE-Hexaeder** quadratisch (Hex20/Hex27), strukturiert | Kontaktflächen exakt aufgelöst, beste Genauigkeit für Kontaktdruck, prüffähig |
| Komplexe Körper (geschweißter/gegossener Lagerbock, Bestand aus Scan) | **FCM-Octree** | keine Vernetzung, beliebige Geometrie |
| Einfache prismatische Bleche | wahlweise | Vorgabe FE, FCM als Option |

- **Strukturierter Rotationsvernetzer** (`mesher="revolve"`) im Modul `hex/`: erzeugt Hexaedernetze für Vollzylinder (O-Grid-Kern), Hohlzylinder, Ringe und Absätze aus einer 2D-Kontur mit Rotationsachse; Verdichtung zu Kontaktflächen und Kanten. Allgemeine Geometrien optional über `gmsh` (Python-API).
- Die Kopplung zwischen Körpern (Kontakt und `Tie`) erfolgt **ausschließlich über Oberflächen-Quadraturpunkte**, unabhängig von der Diskretisierungsart. Für FE-Körper stammen sie aus den Elementflächen, für FCM-Körper aus der eingebetteten Oberflächentriangulierung, jeweils mit Rückabbildung auf die Ansatzfunktionen der Zelle bzw. des Elements.
- **Exakte Kontaktgeometrie:** Für zylindrische Flächen wird die exakte Normale und Krümmung verwendet (`Body.exact_surface="cylinder"`), um Druckschwankungen durch Facettierung zu vermeiden.

### 16.3 Materialmodelle
- **Stufe A:** linear elastisch; **J2-Plastizität** (von Mises) mit isotroper, linear kinematischer oder kombinierter Verfestigung, multilineare Fließkurve, kleine Dehnungen.
  - Integration mit **Radial Return** und **konsistenter Tangente** (quadratische Newton-Konvergenz ist Abnahmekriterium).
  - Geschichtsvariablen (plastische Dehnung, Rückspannung, Vergleichsdehnung) je Quadraturpunkt, als zusammenhängende Arrays (SoA) für CPU/GPU.
- **Stufe B:** große Verformungen (logarithmische Dehnungen, multiplikative Zerlegung), zyklische Verfestigung (Chaboche) für Einspiel- und Ermüdungsfragen.
- **FCM-spezifisch:** Plastische Körper verwenden in Schnittzellen die rekursive Unterteilung (kein Moment Fitting, siehe Vertrag 6a). An der Plastizitätsfront wird **h-verfeinert, nicht p-erhöht**; der Fehlerschätzer berücksichtigt die plastische Zone.
- Speicherbedarf der Geschichtsvariablen wird in `estimate` ausgewiesen.

### 16.4 Kontakt
- **Kontaktsuche:** globale Suche über BVH der Oberflächen, lokale Projektion der Slave-Punkte auf die Master-Fläche (Closest-Point), Aktualisierung je Newton-Iteration in Stufe A (kleine Gleitwege), je Inkrement in Stufe B.
- **Formulierungen:**
  - Stufe A: Knoten-/Punkt-zu-Fläche mit **Augmented Lagrange** (Standard) bzw. Penalty; automatischer Penalty-Faktor aus lokaler Steifigkeit.
  - Stufe B: **Mortar** (Segment-zu-Segment), später duale Mortar-Formulierung für bessere Effizienz. Mortar ist Pflicht für nicht passende Diskretisierungen mit hoher Genauigkeitsanforderung und besteht den Kontakt-Patch-Test.
- **Reibung:** reibungsfrei, Coulomb (Return Mapping haften/gleiten), haftend. Unsymmetrische Tangente bei Reibung → Löser muss unsymmetrische Systeme unterstützen.
- **Lagerspiel:** aus Geometrie oder als Vorgabe `initial_clearance_mm`, das die Geometrie für die Kontaktformulierung überschreibt.
- **Ergebnisse:** Kontaktdruck, Klaffung, Schlupf, Status (offen/haftend/gleitend), resultierende Kontaktkraft je Paar.

### 16.5 Nichtlinearer Lösungsablauf
- **Inkrementell-iterativ:** Lastinkremente je `LoadState`, **Newton-Raphson** mit Liniensuche; Kontakt-Aktivmenge innerhalb der Newton-Iteration (semi-glattes Newton-Verfahren) in Stufe B, verschachtelte Aktivmengenschleife in Stufe A.
- **Adaptive Schrittsteuerung:** Halbierung bei Divergenz oder zu vielen Iterationen, Vergrößerung bei schneller Konvergenz; Mindestfaktor laut `NonlinearSettings`.
- **Konvergenzkriterien:** Residuum, Verschiebungsinkrement und Energie, jeweils relativ; alle drei werden protokolliert.
- **Stabilisierung anfangs freier Körper:** Ein Bolzen im Lagerspiel hat vor dem ersten Kontakt keine Lagerung (singuläres System). Vorgehen:
  1. `auto`: schwache Federn gegen Starrkörperbewegung (Steifigkeit ≪ Struktursteifigkeit), die nach Kontaktschluss automatisch auf null zurückgefahren werden,
  2. alternativ viskose Dämpfung, Anteil der Dämpfungsarbeit an der Gesamtenergie < 1 % (sonst Warnung),
  3. alternativ verschiebungsgesteuerter Kontaktschluss im ersten Inkrement.
- **Lineares Gleichungssystem je Newton-Schritt:**
  - Standard: assemblierte Sparse-Matrix, **Direktlöser** (CHOLMOD symmetrisch, PARDISO/MUMPS bei Reibung unsymmetrisch). Für Baugruppen bis ca. 2–3 · 10⁶ Freiheitsgrade.
  - Große Modelle: **PCG bzw. GMRES** mit Mehrgitter-Vorkonditionierer, Neuaufbau des Vorkonditionierers nur bei deutlicher Änderung der Tangente (Kontaktstatus, Plastizierung), sonst Wiederverwendung.
  - Matrixfreier GPU-Operator (Abschnitt 8/9) für FCM-Körper nutzbar; Tangente je Quadraturpunkt (6×6) wird gespeichert statt neu berechnet.

### 16.6 Lastführung und Lastgeschichte
- **Keine Superposition.** Ergebnisse existieren nur entlang eines `LoadPath`.
- Typischer Lastpfad Drehlager: Montage/Vorspannung → Eigengewicht → Wasserdruck → Stellungsfolge (Stellung 1 → 2 → … → n), jeweils mit Faktor und Inkrementzahl.
- **Checkpoints:** Nach jedem `LoadState` wird der vollständige Zustand gespeichert (Verschiebungen, Geschichtsvariablen, Kontaktzustand). Weitere Lastpfade können von einem Checkpoint aus verzweigen (z. B. gemeinsamer Grundzustand Eigengewicht, danach verschiedene Kombinationen) – das spart Rechenzeit und bildet die Lastgeschichte korrekt ab.
- Zyklische Pfade (Stellungsfolge mehrfach durchfahren) für Einspielnachweis: Abbruch, wenn sich die plastische Dehnung zwischen zwei Zyklen nicht mehr ändert (Einspielen) oder weiter wächst (Warnung: Ratcheting).

### 16.7 Kopplung an das Globalmodell
- Randverschiebungen aus dem linearen Globalmodell werden entlang des Lastpfads mit dem Zustandsfaktor inkrementell aufgebracht.
- Einschränkung: Plastiziert das Detail stark, überschätzt das lineare Globalmodell die Steifigkeit. Die Kopplungskontrolle (Schnittgrößenabweichung) wird **je Laststufe** ausgewertet; oberhalb einer Schwelle (Vorgabe 5 %) Warnung mit Empfehlung, auf **Kraftkopplung** (Schnittgrößen am Schnittrand plus Starrkörperlagerung) umzustellen.
- Alternativ Lagerung und Lasten direkt am Modell (`Support`, `SurfaceLoad`) ohne Globalmodell.

### 16.8 Nachweise und Auswertungen
- **Kontaktpressung** gegen zulässige Werte des Lagerwerkstoffs (Materialangabe bzw. DIN 19704), Darstellung als Druckverlauf über Umfang und Lagerbreite.
- **Plastische Vergleichsdehnung** gegen Grenzdehnung (Vorgabe 5 % Hauptdehnung, angelehnt an EC3-1-5 Anhang C; nutzerseitig anpassbar).
- **Tragfähigkeitsreserve:** Lastfaktor-Verschiebungs-Kurve je Lastpfad (Kraft-Weg-Diagramm), Grenzlast bei Nichtkonvergenz bzw. Erreichen der Grenzdehnung.
- **Ermüdung:** Spannungsschwingbreiten aus elastisch-plastischem Zyklus nach dem Einspielen; Übergabe an das Ermüdungsmodul mit Kennzeichnung, dass lokal Plastizität vorlag. Normnahe Nachweise nach EC3-1-9 bleiben auf elastische Spannungen bezogen; das Programm weist aus, welches Konzept verwendet wurde.
- **Lagerreaktionen und Bolzenschnittgrößen** (Integration über Bolzenquerschnitte) zum Abgleich mit Handrechnung.

### 16.9 Verifikation (zusätzlich zu Abschnitt 13)

| Test | Kriterium |
|---|---|
| Kontakt-Patch-Test mit nicht passenden Diskretisierungen (FE–FE, FE–FCM, FCM–FCM) | konstanter Druck exakt übertragen (Mortar), Abweichung < 1 % (Punkt-zu-Fläche) |
| Hertz Zylinder–Ebene und Zylinder–Zylinder | max. Druck und Kontaktbreite < 3 % |
| Bolzen in Bohrung mit Spiel | Druckverlauf gegen Literaturlösung für konformen Kontakt, Kontaktwinkel |
| Elastoplastische Lochscheibe, monoton und zyklisch | Fließbeginn, Kraft-Weg-Kurve gegen Referenz < 2 %; Newton quadratisch konvergent |
| Hybrid-Gleichheitstest | gleicher Körper als FE und FCM → Verschiebungen < 1 %, Spannungen < 3 % |
| NAFEMS-Benchmarks Nichtlinearität (Plastizität, Kontakt) | laut Benchmark-Toleranz |
| Drehlager-Vergleichsmodell | gegen Ansys/RFEM: max. Kontaktdruck < 5 %, max. plastische Dehnung < 10 %, Reaktionen < 1 % |

### 16.10 Umsetzungsreihenfolge
1. J2-Plastizität für einen FE-Hexaederkörper (inkl. Rotationsvernetzer), Newton-Treiber, Schrittsteuerung
2. Reibungsfreier Kontakt FE–FE (Augmented Lagrange), Stabilisierung anfangs freier Körper
3. Lastpfad, Checkpoints, Verzweigung
4. Plastizität in FCM-Körpern
5. Kontakt und Tie FE–FCM
6. Coulomb-Reibung, unsymmetrischer Löser
7. Mortar-Kontakt
8. Iterative Löser, GPU für große Modelle
9. Große Verformungen, zyklische Verfestigung

Nach Schritt 3 ist ein Drehlager mit reibungsfreiem Kontakt und plastizierendem Bolzen bereits rechenbar; mit Schritt 5 kann der Lagerbock als FCM-Körper aus CAD oder Scan hinzukommen.

### 16.11 Einbindung in die Oberfläche
- **Modellbaum:** Unter „Detailmodelle (Volumen)“ zusätzlich der Typ „Baugruppe“ mit Unterknoten Körper, Kontakte, Verbindungen (Tie), Lagerungen, Lasten, Lastpfade, Ergebnisse.
- **Ribbon „Modellieren“:** Gruppe „Baugruppe“: Körper hinzufügen (Import, CSG, Rotationskontur), Kontaktpaar definieren (Flächenauswahl per Klick, Zylinderflächen automatisch erkannt), Tie, Lagerspiel.
- **Ribbon „Netz“:** je Körper Diskretisierungsart umschaltbar (FE-Hexaeder / FCM), passende Einstellgruppe kontextabhängig; Vorschau beider Arten in einer Ansicht.
- **Ribbon „Berechnung“:** Berechnungsart „Nichtlinear (Baugruppe)“; Lastpfad-Editor (Zustände per Drag-and-drop aus Lastfällen, Kombinationen, Stellungen), nichtlineare Einstellungen, Checkpoint-Verwaltung. Angebotene Optionen richten sich nach `AssemblySolver.capabilities`.
- **Ergebnisse:** Laststufen-Regler, Live-Anzeige während der Rechnung (`on_step`), Kraft-Weg-Diagramm, Kontaktdruck-Abwicklung über Bolzenumfang, plastische Zonen, Konvergenzverlauf je Inkrement. Superposition und Kombinationsbildung sind für diese Ergebnisse gesperrt und als „pfadabhängig“ gekennzeichnet.
