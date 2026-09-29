# Plan Teilprojekt 5 (Stufe 2c) samt Rest aus Stufe 2: Leistung, Effizienz, Nachweise

> Vorgehen: je Schritt eine Sitzung mit dem angegebenen Modell (der Anwender stellt es von Hand ein),
> Prüfung nach jedem Schritt, Commit je Schritt, Messungen aus einem festen Arbeitsbaum auf dem Commit
> (ein Prozess je Fall), Zahlen erst nach Gegenprobe. Entwurf: `packages/volumen3d/docs/Entwurf.md`,
> Abschnitt 2 (TP 5) und 4d; Vorgabe Abschnitte 3, 6 (Stufe 2), 8.3, 9, 11, 13.

**Ziel:** Die Stufe 2 der Vorgabe vollständig machen und Teilprojekt 5 bauen. Offen aus Stufe 2 sind die
Leistungsabnahme (10⁶ Freiheitsgrade unter 60 s auf der Referenz-GPU), ein Aufbau des iterativen Wegs,
der das GPU-Mehrgitter gegenüber dem Direktlöser konkurrenzfähig macht, und die Streuung der Iterationen
über die Schnittlagen. Teilprojekt 5 bringt Moment Fitting, Spannungsrückgewinnung, Hot-Spot-Auswertung an
Nahtlinien, Konvergenzkurve und Protokoll, STEP über gmsh und die Abnahme am Knotenblech mit Kehlnaht.

**Stand vor dem Plan (29.09.2026, main 7a6c922):** `"auto"` wählt den Direktlöser, weil er in der
Schlussmessung in 20 von 23 Fällen schneller war (Theorie 11.10). Der Aufbau des iterativen Wegs dauert
2 bis 20 s länger als Assemblieren und Faktorisieren; das Lösen ist auf der GPU beim Block ab
186 000 Freiheitsgraden drei- bis sechsmal schneller. Die 8-GB-Karte begrenzt das Mehrgitter auf etwa
500 000 Freiheitsgrade bei p 3. Die Iterationen streuen über fünf Schnittlagen um 28 % (Plan TP 4 verlangt
20 %). Der Vertrag enthält `WeldLine`, `HotSpotResult` und `DetailResult.convergence` schon; die gemeinsamen
Referenzmodelle aus Vertrag Abschnitt 8 (`tests/reference_models/`) fehlen im Repository.

## Entscheidungen des Anwenders vor dem Start

| Nr. | Frage | Vorschlag |
|---|---|---|
| E1 | Reihenfolge: zuerst der Rest aus Stufe 2 (Phase A), dann Teilprojekt 5 (Phase B)? | ja, weil A2 und A3 bestimmen, ob sich die GPU überhaupt lohnt |
| E2 | Referenzwerte für das Knotenblech (Hot-Spot, Vorgabe 13: Tet10 in RFEM oder Ansys) | vom Anwender aus RFEM oder Ansys; ersatzweise Tet10 des Hauptprogramms, dann im Protokoll so benannt |
| E3 | Ablage der Referenzmodelle in `tests/reference_models/` (für Session B nur lesbar) | Vorschlag in `docs/vertrag-aenderungen/`, eigener Pull Request der Hauptsitzung |
| E4 | gmsh als optionale Abhängigkeit für STEP (`pip install gmsh`, Extra `step`) | ja, nur optional; ohne gmsh klare Fehlermeldung |

## Phase A – Rest aus Stufe 2 (Leistung, Vorgabe 8.3, 9, 13)

### A1: Aufbau des iterativen Wegs vermessen
- Zeit je Posten an Kirsch h 10/h 8 und Block h 16/h 14 (p 3): Zelldaten (Integration der Schnittzellen),
  `Zelldaten.matrix()`, CᵀKC, Mehrgitter (Ebenen, Glätterblöcke, Grobgitter, Nullraum, λ_max) gegen
  Assemblieren und Pardiso beim Direktlöser. Zwei unabhängige Messskripte, nur Übereinstimmendes zählt.
- Ergebnis: Tabelle je Posten im Plan und in Theorie 11.10, daraus die Ziele für A2.
- Prüfung: beide Skripte stimmen auf 10 % überein; Summe der Posten = gemessener Aufbau auf 5 %.

### A2: Aufbau beschleunigen
- Die teuersten Posten aus A1 angehen (Kandidaten: doppelte Arbeit zwischen Zelldaten und Matrix, CᵀKC in
  scipy, Blockauszug, Grobgitterzerlegung, Nullraumprobe).
- Ziel: Aufbau des iterativen Wegs höchstens 1 s länger als Assemblieren und Faktorisieren bei
  300 000 Freiheitsgraden.
- Prüfung: bestehende Suiten (Operator = Matrix auf 10⁻¹², Mehrgitter, GPU), Gesamtweg an vier Fällen.

### A3: GPU-Speicher für 10⁶ Freiheitsgrade
- Posten heute: Zellmatrizen der Schnittzellen (295 KB je Zelle bei p 3), Glätterblöcke (etwa 0,35 MB je
  Zelle), feine Matrix während des Auszugs. Optionen messen: Schwarz-Blöcke nur für Schnittzellen und
  Chebyshev-Jacobi für innere Zellen, Zellmatrizen in FP32 gespeichert und in FP64 gerechnet, Auszug ohne
  die ganze feine Matrix auf der GPU. FP32 im Glätter divergierte schon einmal (Blockkondition 10⁸) –
  jede Option gegen die FP64-Lösung prüfen.
- Ziel: 10⁶ Freiheitsgrade p 3 mit Spitze unter 7 GB, Iterationen unter 100, Ergebnis wie CPU auf 10⁻⁶.
- Prüfung: `test_gpu_speicher` um den neuen Fall erweitert, Schätzformel neu geeicht.

### A4: h-Mehrgitter unter p = 1 (nur wenn nötig)
- Entscheidungspunkt nach A3: ist das Grobgitter p = 1 (Pardiso) bei 10⁶ Freiheitsgraden der Engpass in
  Zeit oder Speicher? Nur dann h-Ebenen über den Oktree mit hängenden Knoten (Vorgabe 8.3 „p/h“).
- Prüfung: Iterationen unabhängig von der Größe (h 10 bis h 5), Galerkin-Eigenschaft wie bei den p-Ebenen.

### A5: Streuung der Iterationen über die Schnittlagen auf 20 %
- Ritz-Analyse der Lage mit den meisten Iterationen (Kirsch h 10, Versatz 0,4: 31 gegen im Mittel 24).
  Optionen: gewichteter Schwarz-Glätter, Ghost Penalty als Alternative zur Aggregation (Vorgabe 8.3).
- Prüfung: fünf Lagen h 10 und h 8 innerhalb ±20 %, K_tg unverändert auf 0,2 %.

### A6: Leistungsabnahme und Löserwahl neu messen
- 10⁶ Freiheitsgrade unter 60 s (Vorgabe 13) am Block; Schlussmessung der 23 Fälle wiederholen, dazu
  p 2 und p 4. `_AUTO_MEHRGITTER` nur einschalten und die Schwelle nur setzen, wenn die Messung es trägt.
- Prüfung: Tabelle in Theorie 11.10, Verlustrechnung per Skript aus dem Protokoll.

## Phase B – Teilprojekt 5 (Vorgabe 3, 6 Stufe 2, 11)

### B1: Moment Fitting für Schnittzellen
- Je Schnittzelle ein angepasster Satz von etwa (p+1)³ Punkten, dessen Gewichte die Momente der
  Werkstoffdomäne exakt treffen; Referenzmomente aus der bestehenden ebenen-exakten Integration.
  Nicht-negative Gewichte (NNLS), Rückfall auf die bestehende Quadratur bei schlechter Kondition,
  Volumenprüfung je Zelle (Vorgabe 6). Zu prüfen ist dabei auch, ob die Konsistenz von Volumen und Rand auf
  gekrümmten Flächen besser wird (lineares Feld auf der Kirsch-Geometrie heute 10⁻³ daneben).
- Ziel: Quadraturpunkte mindestens um den Faktor 5 weniger bei gleicher Genauigkeit.
- Prüfung: Patch-Tests < 10⁻⁶, Lamé und Kirsch auf 0,1 % wie vorher, Punktzahl und Aufbauzeit im Protokoll.

### B2: Spannungsrückgewinnung (Vorgabe 11.1)
- Superconvergent Patch Recovery oder L²-Projektion der Spannungen, ausgewertet an den Oberflächenpunkten.
- Prüfung: Patch-Test exakt; Kirsch und Lamé an der Oberfläche näher an der Referenz als der Rohwert.

### B3: Hot-Spot nach IIW Typ a (Vorgabe 11.2)
- Referenzpunkte im Abstand 0,4·t und 1,0·t vom Nahtübergang, senkrecht zur Naht auf der Blechoberfläche,
  lineare Extrapolation, maßgebende Komponente senkrecht zur Naht; Richtung aus Oberflächennormale und
  Nahttangente, Seite ohne Nahtwulst aus der Geometrie. `HotSpotResult` je Nahtpunkt füllen.
- Prüfung: lineares Spannungsfeld wird exakt extrapoliert; Blech mit Kehlnaht unter Zug gegen die
  Handrechnung. Ist die Seite geometrisch nicht eindeutig, Vertragsvorschlag für eine Richtungsangabe.

### B4: Konvergenzkurve und Protokoll (Vorgabe 11.3)
- `DetailResult.convergence` je Zyklus (Hot-Spot und Maximalspannung über Freiheitsgrade), Zyklen aus
  `FcmSettings.adaptive_cycles` als p-Erhöhung und h-Halbierung in Nahtnähe (ohne Fehlerschätzer, der kommt
  in TP 6); Protokoll aller Einstellungen (p, Verfeinerung, α, Toleranz, Kopplungsart, Löserweg).
- Prüfung: Kurve fällt monoton gegen den Grenzwert am Knotenblech-Vorversuch; Protokoll vollständig.

### B5: STEP über gmsh-Tessellierung (Vorgabe 3)
- Optionales Extra `step` mit gmsh; `GeometrySourceType.STEP` → Tessellierung → bestehender STL-Weg;
  ohne gmsh `SolverError` mit Hinweis. Die neue optionale Abhängigkeit im Pull Request benennen.
- Prüfung: Würfel mit Bohrung als STEP gegen CSG (Volumen, K_t); Test überspringt ohne gmsh.

### B6: Schneller Windungszahl-Baum (Rest aus TP 2)
- Näherung nach Barill u. a. 2018 (Dipole je BVH-Knoten) für STL-Netze über 10⁵ Facetten.
- Prüfung: dieselbe Innen/Außen-Entscheidung wie exakt an 10⁵ Zufallspunkten, mindestens zehnmal schneller
  bei 10⁶ Facetten.

### B7: Schale → Volumen (nur Prüfung)
- Kopplung an ein Schalen-Globalmodell ist Sache des Providers im Hauptprogramm; hier nur ein Test mit einem
  Schalen-Provider-Stub über die Vertragsschicht.
- Prüfung: Schnittgrößenkontrolle < 1 % (Vorgabe 13, Kopplung).

## Phase C – Abnahme und Abschluss

### C1: Knotenblech mit Kehlnaht (Abnahme TP 5)
- Modell aus CSG (Blech, Kehlnaht, Anschluss), Lasten über Schnittebene, Hot-Spot entlang der Naht,
  Konvergenzkurve. Referenzwerte nach E2, Ablage nach E3.
- Prüfung: Hot-Spot-Spannung gegen Tet10-Referenz < 3 % (Vorgabe 13).

### C2: Zweite Sicht über Phase A und B
- Unabhängiges Gutachten, nur lesend, anderes Modell als die Umsetzung; Befunde am Quelltext prüfen, dann
  beheben und mit Tests absichern.

### C3: Handbücher
- Theoriehandbuch (neue Abschnitte nach 11.10), Entwurf Abschnitt 4e, `docs/Volumenmodul.md`.

### C4: Gesamtlauf und Pull Request 3
- `run_all`, alle Paketsuiten, GPU-Suite lokal, mypy, lint-imports, CI grün; Pull Request mit den
  Änderungen außerhalb des Pakets einzeln benannt. Gemergt wird nur nach Freigabe.

## Modell je Schritt

| Schritt | Modell | Warum |
|---|---|---|
| A1 Aufbau vermessen | Sonnet 5 | klar umrissene Messaufgabe |
| A2 Aufbau beschleunigen | Opus 5.5 | Umbau in bekanntem Code mit vielen Prüfungen |
| A3 GPU-Speicher für 10⁶ FHG | Fable 5.1 | numerisch heikel (FP32, Glätter), Entwurf und Umsetzung |
| A4 h-Mehrgitter (nur wenn nötig) | Fable 5.1 | hängende Knoten im Mehrgitter, höchstes Risiko |
| A5 Streuung über Schnittlagen | Opus 5.5 | Ritz-Analyse und Glätterabstimmung |
| A6 Leistungsabnahme, Löserwahl | Sonnet 5 | Messreihe nach festem Schema |
| B1 Moment Fitting | Fable 5.1 | Stabilität der Gewichte, Konsistenz Volumen/Rand |
| B2 Spannungsrückgewinnung | Opus 5.5 | bekanntes Verfahren, sorgfältige Umsetzung |
| B3 Hot-Spot IIW Typ a | Opus 5.5 | Geometrie der Referenzpunkte, Normbezug |
| B4 Konvergenzkurve, Protokoll | Sonnet 5 | überschaubar, baut auf B2/B3 |
| B5 STEP über gmsh | Sonnet 5 | Anbindung einer Bibliothek |
| B6 Windungszahl-Baum | Opus 5.5 | Algorithmus mit Genauigkeitsnachweis |
| B7 Schale → Volumen (Prüfung) | Sonnet 5 | Test über bestehende Schnittstelle |
| C1 Knotenblech-Abnahme | Opus 5.5 | Modellbau und Nachweis gegen Referenz |
| C2 Zweite Sicht | Fable 5.1 | unabhängig von der Umsetzung, tiefste Prüfung |
| C3 Handbücher | Sonnet 5 | Texte aus vorhandenen Messwerten |
| C4 Gesamtlauf, Pull Request | Sonnet 5 | Routine mit Prüfliste |
