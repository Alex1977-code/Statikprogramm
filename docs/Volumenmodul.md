# Volumenmodul `volumen3d`: Stand der Umstellung im Hauptprogramm

Grundlage: `Schnittstellenvertrag_Statik3D_FCM.md` (Vertragsversion 2.1.0) und
`Vorgabe_Statik3D_Abschnitt_FCM-Volumenloeser.md` (beide in `docs/`, Stand 26.09.2026).
Der Vertrag ist verbindlich für beide Entwicklungsstränge; Änderungen daran nur per eigenem
Pull Request mit Versionserhöhung (Vertrag, Abschnitt 9).

## Umgesetzt (Vertrag Abschnitt 10, 26.09.2026)

| Schritt | Ort | Stand |
|---|---|---|
| 10.1 Paket `statik3d_contracts` | `packages/statik3d_contracts/` – alle Module des Vertrags (`units`, `model`, `discretization`, `coupling`, `detail`, `nonlinear`, `solver`, `testing`), `CONTRACT_VERSION = "2.0.0"`, `py.typed`, `mypy --strict` sauber | fertig; `pip install -e packages/statik3d_contracts`, in `requirements.txt` eingetragen |
| 10.2 Netz hinter `Discretization` | `statik3d/diskretisierung.py`: `FeNetzDiskretisierung` mit `kind = FE_MESH` (Freiheitsgrade, Hüllquader und Vorschau in **mm**, Zusammenfassung je Elementtyp) | Adapter fertig; die Rechenwege greifen weiter direkt auf `model.nodes`/`model.elements` zu |
| 10.5 Registrierung über Entry Points | `statik3d/volumenloeser.py`: Gruppen `statik3d.solid_solvers` und `statik3d.assembly_solvers` über `importlib.metadata.entry_points`, Versionsprüfung (Major), Protokollprüfung, Rückfall auf die Stubs des Vertragspakets ohne Metadaten (exe) | fertig; der Stub ist als `stub` registriert |
| Prüfungen | `tests/contracts/test_vertrag.py` (im Gesamtlauf) und `.github/workflows/ci.yml` (Ubuntu: mypy --strict, Vertragsprüfungen) | fertig |

Stubs des Vertrags (Abschnitt 8) in `statik3d_contracts/testing.py`: `StubSolidSolver`
(Würfel, konstante Spannung), `StubGlobalFieldProvider` (Kragarm unter Endlast nach
Balkentheorie, vektorisiert), `StubAssemblySolver` (zwei Zylinder, Lastpfad mit Hertz-Druck und
wachsender plastischer Dehnung, `on_step`).

## Seit Vertrag 2.0.1 (27.09.2026) im Vertrag selbst geregelt

- **Repository-Aufbau (Abschnitt 1):** `statik3d/` liegt an der Wurzel, `packages/statik3d_contracts/`
  und `packages/volumen3d/` darunter; `.importlinter` prüft die Abhängigkeitsregeln in der CI.
- **Einheiten (Abschnitt 2):** SI intern, Umrechnung ausschließlich in
  `statik3d/vertragseinheiten.py` (benutzt vom `Discretization`-Adapter und künftig vom
  `GlobalFieldProvider`); Rundreisetest in `tests/contracts/test_vertrag.py`.
- **Stub (Abschnitt 7):** echte Löser haben immer Vorrang; der Stub greift nur ohne andere
  Registrierung und dann mit Warnung des Laders, Zustand „STUB – keine echte Berechnung“ in
  `uebersicht()`, Kennzeichnung in `protocol["stub"]`/`["kennzeichen"]` und als erste Warnung;
  `volumenloeser.ist_stub()` für Nachweise und Oberfläche.
- **Vertragsänderungen:** Vorschläge in `docs/vertrag-aenderungen/`, eigener PR auf `main`.

## Offen (Abschnitt 10, Session A)

- 10.3 `GlobalFieldProvider` des Hauptprogramms (punktweise Abfrage der Ergebnisse, zunächst
  für Stäbe: Querschnittskinematik aus den Stabfreiheitsgraden).
- 10.4 Modellbaum-Knoten „Detailmodelle (Volumen)“ aus `DetailModelSpec`; Ribbons nach
  Vorgabe Abschnitt 15.
- 10.2 weiter: Stellen, die direkt auf Knoten-/Elementlisten zugreifen, nach und nach über
  das Protokoll führen.
- Referenzmodelle `tests/reference_models/` (Vertrag Abschnitt 8) als JSON/YAML mit
  Erwartungswerten – das Knotenblech mit Kehlnaht liegt seit Pull Request 13 (02.10.2026) dort, weitere gemeinsam mit Session B.


## Session B: Stand des Volumenmoduls `volumen3d` (Stufe 1 bis 2c, Stand 02.10.2026)

Zweig `feature/volumen3d` (Worktree `Desktop/Statik3D/statik3d-volumen3d`, eigene venv mit numba und cupy). Entwurf und Zerlegung: `packages/volumen3d/docs/Entwurf.md`
(Abschnitt 4b: Teilprojekt 2, 4c: Teilprojekt 3, 4d: Teilprojekt 4, 4e: Teilprojekt 5); Pläne: `packages/volumen3d/docs/plaene/`; Theorie und Messwerte:
`docs/Theoriehandbuch.md`, Kapitel 11 (11.8: Teilprojekt 2, 11.9: Teilprojekt 3, 11.10: Teilprojekt 4 mit den Leistungsarbeiten A1 bis A6 des Plans TP 5, 11.11 bis 11.20: Teilprojekt 5). Regeln der Sitzung:
`packages/volumen3d/CLAUDE.md`.

| Stufe | Inhalt | Stand |
|---|---|---|
| 1 (Teilprojekte 1 und 2) | Gitter, Integration, Nitsche, Oktree, hängende Freiheitsgrade, STL | auf `main` seit 28.09.2026 (Pull Request 8, Merge c54af91) |
| 2a und 2b (Teilprojekte 3 und 4) | matrixfreier Operator, PCG, p-Mehrgitter (CPU und GPU), Löserwahl | auf `main` seit 29.09.2026 (Pull Request 10, Merge 7a6c922) |
| 2c (Teilprojekt 5, Plan TP 5) | Leistung des Mehrgitters (A1 bis A6), Moment Fitting, Spannungsrückgewinnung, Hot-Spot, adaptive Zyklen, STEP, Hüllenintegration, Schale, Abnahme am Knotenblech | auf `feature/volumen3d`, Pull Request (der dritte, Plan C4) noch nicht angelegt; Merge nur auf Freigabe des Anwenders |

### Bausteine

| Teil | Ort | Stand |
|---|---|---|
| Paket nach Vertrag Abschnitt 1 | `packages/volumen3d/` (geometry, fcm, linalg, postprocess, api) | Entry Points `fcm` (echt) und `hybrid` (Platzhalter bis TP 7), `import-linter` (`.importlinter`) und `mypy --strict api.py` in der CI |
| Geometriekern | `geometry/sdf.py`, `csg.py`, `polyeder.py`, `oberflaeche.py`, `stl.py`, `dreiecksbaum.py`, `huelle.py`, `windung.py`, `step.py` | CSG aus `GeometrySource.params` (Quader, Zylinder, Kugel, Halbraum, **STL**; Vereinigung, Differenz, Schnitt) und als eigene Quelle **STEP** (`GeometrySourceType.STEP`, wird wie ein STL-Knoten behandelt), konservative Abstände, lokale konvexe Stücke (STL: konvex / konkav / gemischt per binärer Raumteilung), Flächenquadratur auf der exakten Oberfläche; Randpolygone auf Zellflächen zählen genau einmal. STL: Windungszahl (robust gegen Lücken, `defekt` im Protokoll), BVH mit numba (ohne numba k-d-Baum-Index, gleiche Ergebnisse) |
| FCM-Kern | `fcm/basis.py`, `gitter.py`, `zwaenge.py`, `quadratur.py`, `momentfitting.py`, `aggregation.py`, `elastizitaet.py`, `rand.py`, `problem.py` | Legendre-Basis p = 1…4, **Oktree** (Schnittzellen, `RefinementRegion`, dünne Wände, 2:1 über 26 Nachbarn), **hängende Freiheitsgrade** und Zellaggregation in einer Zwangsmatrix, ebenen-exakte Schnittzellen-Integration, Moment Fitting, Nitsche (voll / normal / schnitt) mit β je Zelle, Lasten, Direktlöser (pypardiso, sonst SuperLU) |
| Löser | `fcm/operator.py`, `operator_gpu.py`, `mehrgitter.py`, `mehrgitter_gpu.py`, `bloecke_gpu.py`, `linalg/direkt.py`, `linalg/pcg.py` | Direktlöser, matrixfreies PCG, p-Mehrgitter mit Zellblock-Schwarz-Glätter (CPU und GPU); Wahl über `FcmSettings.backend` |
| Nachbearbeitung | `postprocess/auswertung.py`, `rueckgewinnung.py`, `hotspot.py`, `konvergenz.py` | Auswertung an Punkten, L²-Projektion der Spannungen, Hot-Spot nach IIW Typ a, Konvergenzaussage |
| Vertragsschicht | `api.py` | `FcmSolver.estimate/prepare/solve` mit adaptiven Zyklen, `FcmDiskretisierung` (summary mit Ebenen, hängenden Flächen, freien Freiheitsgraden; preview mit Zellklassen), `GeometrySourceType.CSG`, `STL` und `STEP` (`path`), Lasten nach Vertrag 2.1.0, Kopplungskontrolle je Schnittebene mit Multiplikatoren und Warnung > 5 %, Protokoll |
| Prüfungen Stufe 1 | `packages/volumen3d/volumen3d/tests/` | Kernsuite `test_kern` (in `run_all` und CI, enthält Oktree, Zwänge, STL-Kurzfassung); Abnahmen `test_patch` (< 10⁻⁶ auch mit hängenden Freiheitsgraden), `test_zwaenge`, `test_oktree`, `test_kragarm` (reine Biegung exakt, Stub gegen Timoshenko −0,9 % / +2,7 %), `test_lame` (p = 3: σ_r 0,32 %, σ_φ 0,03 %), `test_kirsch` (K_tg +1,35 % gegen Howland; **mit Bereichsverfeinerung am Loch Schnittlagen-Streuung 0,34 % bei 3,5 % der Freiheitsgrade des gleichmäßigen Gitters – Abnahme erfüllt**), `test_stl` (Würfel-STL und L-Körper exakt; Lamé aus tesselliertem Ring mit Facette 1 mm: σ_r 0,066 %, σ_φ 0,022 % (seit der Hüllenintegration B6 0,070 % / 0,024 %), genauer als CSG mit Tangentialebenen) |
| Prüfungen Stufen 2a bis 2c | dieselbe Stelle | Stand 02.10.2026: Kernsuite 347 Prüfungen, Vertragsschicht (`test_vertrag_fcm`) 51, Knotenblech mit `VOLUMEN3D_LANG=1` 9; mit der zweiten Sicht (C2, Commit 0ee938c) liefen alle 25 Suiten und die GPU-Suite grün; Liste in Entwurf 4e.7 |

**Bewusste Abweichungen von der Vorgabe (Messung, Begründung im Entwurf 3.5/3.6 und Theorie 11):**
Punkttest der Schnittzellen nur als Rückfall (erster Ordnung, Patch-Test sonst unerreichbar);
Zellaggregation schon in Stufe 1 und α nur für Zellen ohne Wurzel; an Schnittebenen
Normalkomponente punktweise plus Resultierende in der Ebene statt aller drei Komponenten.

**Vorschläge an den Vertrag** (`docs/vertrag-aenderungen/`): Lasten im `DetailModelSpec` und Klarstellung der Seite der Schnittgrößen
(`2026-09-27-lasten-und-schnittgroessen.md`, vom Anwender angenommen, als Vertrag 2.1.0 auf `main`, Merge bdac39d vom 28.09.2026). Das Referenzmodell Knotenblech
(`2026-10-01-referenzmodell-knotenblech.md`, nur Daten) hat die Hauptsitzung als Pull Request 13 abgelegt. Offen: Volumenlast je Lastfall (2.2.0, `2026-09-28-volumenlast-je-lastfall.md`,
Entscheidung beim Anwender, Plan O7) sowie zwei noch nicht geschriebene Vorschläge: Abbruch in `prepare` (Plan O8) und Klarstellung zu `summary()` nach Zyklen (O9).

**Änderungen außerhalb des Pakets:** `tests/contracts/test_vertrag.py` (Erwartung `fcm` vor
`stub`), `tests/run_all.py`, `.github/workflows/ci.yml`, `requirements.txt`, `.importlinter`,
`docs/Theoriehandbuch.md` Kapitel 11, `docs/Volumenmodul.md`. Das optionale Extra `step` (gmsh, GPL) steht in der `pyproject.toml` des Pakets.

### Stufen 2a und 2b: Löser (Teilprojekte 3 und 4)

- **Aufbau und Operator (28.09.2026):** Zwangszyklen strukturell beseitigt (Wurzeln der Aggregation nie feiner, gröbste Zelle als Eigentümer geteilter Moden), Aufbauzeit halbiert
  (Lamé CSG 21,4 s, STL 18,0 s), matrixfreier Operator mit numba (`fcm/operator.py`, = Matrix auf 10⁻¹⁵, 18,7 ms je Anwendung bei 229 608 Freiheitsgraden) und PCG mit Jacobi und
  projizierten Mittelwertzwängen (`linalg/pcg.py`, `FcmProblem(loeser="pcg")`). Befund: Kondition der Jacobi-vorkonditionierten Matrix 10⁶ bis 5·10⁷, 5 000 bis 20 000 Iterationen –
  die Messlatte für das Mehrgitter. GPU-Kerne mit CuPy: 3,1 ms je Anwendung bei 229 608 Freiheitsgraden gegen 18,8 ms CPU.
- **Lasten nach Vertrag 2.1.0 (Merge bdac39d, 28.09.):** `DetailModelSpec.loads` je Lastfall-ID (Druck, Traktion, Resultierende über benannte Fläche, Box oder Zylinder) und `body_load`,
  mit Protokoll je Last (Fläche, Schwerpunkt, Kraft, Moment).
- **p-Mehrgitter (Teilprojekt 4, `fcm/mehrgitter.py`, 28.09.):** senkt die Iterationszahlen mit Zellblock-Schwarz-Glätter auf 26 bis 53 in allen Abnahmefällen (Jacobi: 2 580 bis über
  40 000), `FcmProblem(loeser="mehrgitter")`; mit `backend="gpu"` läuft der V-Zyklus auf der Grafikkarte (Kirsch h 10 p 3: 8,6 bis 21 s gegen 7 bis 25 s Lösen des Direktlösers), freie
  Starrkörperbewegungen werden erkannt und herausprojiziert.
- **Löserwahl:** `FcmSettings.backend = "auto"` (Standard) wählt den im Gesamtweg schnelleren Weg; auf der gemessenen Karte (RTX 3070, 8 GB) ist das bis zur Speichergrenze des Mehrgitters der
  Direktlöser: in der Schlussmessung vom 29.09.2026 (23 Fälle, kompakter Block und dünne Kirsch-Scheibe, 65 000 bis 497 000 Freiheitsgrade) war er in 20 Fällen schneller (Theorie 11.10).
  `"gpu"` erzwingt das Mehrgitter auf der Grafikkarte, mit Rückfall auf den Direktlöser bei fehlender GPU, zu wenig Speicher oder jedem GPU-Fehler; `"cpu"` rechnet direkt.
- **Behoben vorher:** Nullraumerkennung größenunabhängig und auch mit Schnittebenen, Aggregationswurzeln höchstens zwei Zellen entfernt und Aggregationsschwelle 0,4, GPU-Speicher in
  Teilstapeln und richtig geschätzt.

### Stufe 2c: Leistung und Nachweise (Teilprojekt 5)

- **Leistung des Mehrgitters (A1 bis A6, 29. und 30.09.2026, Theorie 11.10):** Zellmatrizen und Glätterblöcke liegen symmetrisch gepackt auf der Grafikkarte, die feine Matrix bleibt auf der CPU: Modelle mit
  einer Million Freiheitsgraden rechnen mit 4,4 bis 4,8 GB auf der 8-GB-Karte (vorher 10,8 bis 12,2 GB geschätzt), in 29 bis 36 Iterationen und mit denselben Ergebnissen wie der Direktlöser. Das Mehrgitter
  glättet mit einem breiteren Chebyshev-Fenster und löst dadurch 20 bis 22 % schneller bei gleichen Ergebnissen; die Iterationszahl streut über die Schnittlagen der dünnen Kirsch-Scheibe weiter um −25 bis
  +29 %. Die Löserwahl wurde neu gemessen: `auto` bleibt beim Direktlöser; das Mehrgitter ist am kompakten Block ab 185 000 Freiheitsgraden 12 bis 27 % schneller und bei 10⁶ Freiheitsgraden in beiden
  Modellfamilien vorn (Block 115 statt 280 s), an der dünnen Scheibe darunter langsamer. Lösen allein unter 60 s bei 10⁶ Freiheitsgraden (7 bis 8 s); Aufbau plus Lösen 62 bis 115 s, der Hauptposten sind die
  Zellsteifigkeiten der Schnittzellen – dagegen das Moment Fitting (nächster Punkt).
- **Moment Fitting (B1, Theorie 11.11):** je Schnittzelle eine Regel mit (2p+1)³ Punkten, die dieselben Zellmatrizen liefert wie die rekursive Integration (auf 10⁻¹³) und auf gekrümmten
  Rändern 17- bis 34-mal weniger Punkte braucht; seit dem 30.09.2026 Vorgabe (Entscheidung des Anwenders), `momentfitting=False` schaltet zurück.
- **Spannungsrückgewinnung (B2, Theorie 11.12):** die Oberflächenspannungen in `DetailResult.stress` sind geglättet (L²-Projektion); das Protokoll nennt das unter `stress_recovery`.
  Form und Einheit ändern sich nicht, nur die Werte an der Oberfläche werden glatter; die Rohspannung bleibt in `Auswertung.spannung`.
- **Hot-Spot (B3, Theorie 11.13):** `DetailResult.hot_spots` trägt die Strukturspannung nach IIW Typ a je Punkt einer `WeldLine` (Blechseite aus der Geometrie, Warnung statt Wert bei
  Mehrdeutigkeit); CSG-Geometrien mit verschachtelten Bäumen (Kehlnähte als Schnitt aus Quader und Halbraum) werden exakt integriert.
- **Adaptive Zyklen und Konvergenzaussage (B4 und O4, Theorie 11.14):** `solve` fährt mit `FcmSettings.adaptive_cycles` (0 bis 4) mehrere Zyklen (lokale h-Halbierung an den Nähten und p + 1,
  ohne Fehlerschätzer) und liefert die Konvergenzkurve in `DetailResult.convergence`, alle Einstellungen im Protokoll (`settings`) und eine Konvergenzaussage (`convergence_statement`):
  sie bewertet die letzte relative Änderung gegen die Schranke 3 % (`konvergiert` / `nicht_konvergiert`); Monotonie und Aitken-Grenzwert stehen zusätzlich. Knotenblech 0,44 %,
  T-Stoß in der p-Phase 0,45 %, beide konvergiert und nicht monoton; `nicht_konvergiert` und `ohne_aenderung` tragen eine Warnung.
- **Streuung des Hot-Spots mit der Gitterlage (O3, Theorie 11.20):** bei Zellgröße t/4 und p 4 im Mittel 143,6 N/mm² mit der Spanne 138,9 bis 147,2 N/mm² (5,7 %), gegen die Tet10-Referenz
  je Lage −2,93 % bis +3,10 %; als Band berichtet, die Schranke 3 % ist nicht belegt.
- **STEP und Hüllenintegration (B5 und B6, Theorie 11.15 und 11.16):** `GeometrySourceType.STEP` liest Dateien über gmsh (optionales Extra `step`, GPL; ohne gmsh `SolverError` mit Hinweis):
  Tessellierung, Einheit nach mm, dann der STL-Weg. Der STL-Weg integriert tessellierte Hüllen (STL und STEP) je Zelle exakt über den Divergenzsatz: Volumen und Zellregeln sind für die
  Tessellierung exakt, kein Punkttest, Block mit Bohrung N 120 bei h 25 in 27 s statt 388 s, K_t durch den Vertragsweg gegen CSG auf 0,12 % (p 2); die Krümmung steckt nur in der
  Tessellierung (`elements_per_circle`, Vorgabe 120: Volumenfehler der Bohrung +0,0047 %). Läuft eine Schnitt- oder Symmetrieebene durch den gekrümmten Teil der Hülle, gilt in diesen Zellen
  weiter der alte Weg mit Punkttest und Warnung. Große Netze (ab 20 000 Facetten) entscheiden innen/außen über den Windungszahl-Baum nach Barill (28-mal schneller, gleiche Entscheidung an
  100 000 Punkten).
- **Schale → Volumen (B7, Theorie 11.17):** die Kopplung von einem Schalen-Globalmodell (lineare Verteilung über die Dicke) mit einem Provider-Stub ist geprüft: Schnittgrößenabweichung
  unter 10⁻³ bei p 2 und 10⁻⁷ bei p 3 (Vorgabe 1 %); die Kopplungskontrolle bezieht Kraft und Moment auf ein gemeinsames Lastmaß, damit reine Biegung keine Scheinabweichung der Kraft meldet (seit C2 bewertet sie Abweichungen als Spannungen, siehe unten).
  Der Provider selbst ist Sache des Hauptprogramms.
- **Abnahme am Knotenblech mit Kehlnaht (C1, Theorie 11.18):** hält gegen die Tet10-Referenz des Hauptprogramms (Pull Request 13 auf `main`; rechts +0,3 %, links −2,9 %, Schranke 3 %);
  Paket in `Desktop/Statik3D/REFERENZ-KNOTENBLECH-2026-10-01/`. Für den 0,5-mm-Lauf der Hauptsitzung liegt dort ein lokal verfeinertes Netz (`knotenblech_tet10_lokal05.inp`, 445 946 Knoten,
  1,34 Mio. Freiheitsgrade); der Lauf steht aus (Plan O2).
- **Zweite Sicht (C2, Theorie 11.19):** 23 verschiedene Befunde bestätigt, die wesentlichen behoben. Für das Hauptprogramm sichtbar: STEP-Dateien mit mehreren Körpern werden vereinigt (durchdringende
  STL-Schalen geben einen Fehler); die Kopplungskontrolle bewertet Abweichungen als Spannungen (`reference_stress`, `deviation_measure` im `coupling_check`; Momentfehler an dünnen Blechen
  werden jetzt gemeldet, das Knotenblech meldet „Moment 7,9 % > 5 %“ – richtig, das Globalmodell bildet die Exzentrizität nicht ab); `hotspot_max` ist der betragsgrößte Wert mit Vorzeichen;
  die Konvergenzaussage kennt `ohne_aenderung`; Hot-Spots haben eine Anwendbarkeitsprüfung (ebene Blechoberfläche über 1,0 t).

### Was das Hauptprogramm sieht

- An der Schnittstelle ändert sich nichts; `summary()` und das Protokoll nennen den Rechenweg (`solver_path`, `backend`, `solver_choice`).
- Neu im Protokoll: `settings` (alle Einstellungen je Zyklus), `cycles`, `convergence_statement`, `hot_spot`, `stress_recovery`, `step_tessellation`, im `coupling_check`
  `reference_stress` und `deviation_measure`. Neu im Ergebnis: `DetailResult.convergence` und `hot_spots`.
- Warnungen, die ein Nachweis lesen muss: `nicht_konvergiert` und `ohne_aenderung` der Konvergenzaussage, Kopplungsabweichung über 5 %, Integrationswarnung (Punkttest oder Rückfall in
  Zellen an Ebenen durch gekrümmte Hüllen). Der Stub bleibt nie eine Berechnung (Vertrag Abschnitt 7).
- STEP braucht das optionale Extra `step` (gmsh ab 4.11, GPL-Lizenz); ohne gmsh gibt `GeometrySourceType.STEP` einen Fehler mit dem Hinweis `pip install "gmsh>=4.11"` und dem Verweis auf CSG, STL oder einen tessellierten Export.

### Offen (Session B)

Entscheidungen und Empfehlungen stehen im Plan, Abschnitt „Offene Entscheidungen nach C2“, und in Entwurf 4e.8: die Messung von Nahtziel t/8 (Größe gemessen: 6,4 Mio. Freiheitsgrade bei p 4, nicht rechenbar) und 0,5 t / 1,5 t (O3), der Lauf der Hauptsitzung am
lokal verfeinerten Netz (O2), der Konsistenzfehler des p-2-Ansatzes am schrägen Schnitt (2·10⁻⁴ bis 3,5·10⁻³ in der Spannung) und am T-Stoß mit lokaler Verfeinerung (O5), Ebenen durch gekrümmte
Hüllen (O6), der Vertragsvorschlag 2.2.0 (O7), Abbruch in `prepare` und `summary()` nach Zyklen (O8, O9), Torsion in der Kopplungskontrolle (O10), Zeiten je Zyklus (O11), mehrere Kinder derselben
Hülle (O12), GPU-Einrichtzeit nach der Cholesky-Umstellung (O13), Leistung der Oberflächenquadratur der Hüllenfacetten (O14). Aus Teilprojekt 2 offen: die Vierteilung der Randpolygone an
gekrümmten Formen. **Behoben (O15, 02.10.2026, Commit 250e607):** `Gitter._aufbauen` teilte in der 2:1-Balancierung andere Zellen als gemeint; bei Verfeinerung über zwei Ebenen unter der Basiszelle (alle bisherigen Messungen) ohne Folge – 391 von 393 Gittern der
Suiten sind mit der Korrektur unverändert –, bei drei Ebenen (etwa Nahtziel t/8) endete der Aufbau nie. Jetzt werden die sortierten Felder geteilt, mit Durchlaufgrenze und Test.
