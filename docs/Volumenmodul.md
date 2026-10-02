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
  Erwartungswerten – gemeinsam mit Session B.


## Session B: Stand des Volumenmoduls `volumen3d` (Teilprojekte 1 und 2 = Stufe 1, 27.09.2026)

Zweig `feature/volumen3d` (Worktree `Desktop/Statik3D/statik3d-volumen3d`, eigene venv mit
numba und cupy für die späteren Stufen). Entwurf und Zerlegung: `packages/volumen3d/docs/Entwurf.md`
(Abschnitt 4b: Teilprojekt 2); Pläne: `packages/volumen3d/docs/plaene/`; Theorie und Messwerte:
`docs/Theoriehandbuch.md`, Kapitel 11 (11.8: Teilprojekt 2). Regeln der Sitzung:
`packages/volumen3d/CLAUDE.md`.

| Teil | Ort | Stand |
|---|---|---|
| Paket nach Vertrag Abschnitt 1 | `packages/volumen3d/` (geometry, fcm, linalg, postprocess, api) | Entry Points `fcm` (echt) und `hybrid` (Platzhalter bis TP 7), `import-linter` (`.importlinter`) und `mypy --strict api.py` in der CI |
| Geometriekern | `geometry/sdf.py`, `csg.py`, `polyeder.py`, `oberflaeche.py`, `stl.py`, `dreiecksbaum.py`, `huelle.py`, `windung.py`, `step.py` | CSG aus `GeometrySource.params` (Quader, Zylinder, Kugel, Halbraum, **STL**; Vereinigung, Differenz, Schnitt), konservative Abstände, lokale konvexe Stücke (STL: konvex / konkav / gemischt per binärer Raumteilung), Flächenquadratur auf der exakten Oberfläche; Randpolygone auf Zellflächen zählen genau einmal. STL: Windungszahl (robust gegen Lücken, `defekt` im Protokoll), BVH mit numba (ohne numba k-d-Baum-Index, gleiche Ergebnisse) |
| FCM-Kern | `fcm/basis.py`, `gitter.py`, `zwaenge.py`, `quadratur.py`, `aggregation.py`, `elastizitaet.py`, `rand.py`, `problem.py` | Legendre-Basis p = 1…4, **Oktree** (Schnittzellen, `RefinementRegion`, dünne Wände, 2:1 über 26 Nachbarn), **hängende Freiheitsgrade** und Zellaggregation in einer Zwangsmatrix, ebenen-exakte Schnittzellen-Integration, Nitsche (voll / normal / schnitt) mit β je Zelle, Lasten, Direktlöser (pypardiso, sonst SuperLU) |
| Vertragsschicht | `api.py` | `FcmSolver.estimate/prepare/solve`, `FcmDiskretisierung` (summary mit Ebenen, hängenden Flächen, freien Freiheitsgraden; preview mit Zellklassen), `GeometrySourceType.CSG` und `STL` (`path`), Kopplungskontrolle je Schnittebene mit Multiplikatoren und Warnung > 5 %, Protokoll |
| Prüfungen | `packages/volumen3d/volumen3d/tests/` | Kernsuite `test_kern` (in `run_all` und CI, enthält Oktree, Zwänge, STL-Kurzfassung); Abnahmen `test_patch` (< 10⁻⁶ auch mit hängenden Freiheitsgraden), `test_zwaenge`, `test_oktree`, `test_kragarm` (reine Biegung exakt, Stub gegen Timoshenko −0,9 % / +2,7 %), `test_lame` (p = 3: σ_r 0,32 %, σ_φ 0,03 %), `test_kirsch` (K_tg +1,35 % gegen Howland; **mit Bereichsverfeinerung am Loch Schnittlagen-Streuung 0,34 % bei 3,5 % der Freiheitsgrade des gleichmäßigen Gitters – Abnahme erfüllt**), `test_stl` (Würfel-STL und L-Körper exakt; Lamé aus tesselliertem Ring mit Facette 1 mm: σ_r 0,066 %, σ_φ 0,022 %, genauer als CSG mit Tangentialebenen) |

**Bewusste Abweichungen von der Vorgabe (Messung, Begründung im Entwurf 3.5/3.6 und Theorie 11):**
Punkttest der Schnittzellen nur als Rückfall (erster Ordnung, Patch-Test sonst unerreichbar);
Zellaggregation schon in Stufe 1 und α nur für Zellen ohne Wurzel; an Schnittebenen
Normalkomponente punktweise plus Resultierende in der Ebene statt aller drei Komponenten.

**Vorschläge an den Vertrag** (`docs/vertrag-aenderungen/2026-09-27-lasten-und-schnittgroessen.md`):
Lasten im `DetailModelSpec` (Minor 2.1.0) und Klarstellung der Seite der Schnittgrößen. Vom
Anwender am 27.09.2026 angenommen; die Umsetzung kommt als eigener Pull Request auf `main`
(Vertragsversion 2.1.0, Änderungsprotokoll, `tests/contracts`), beide Sitzungen holen sie per
Rebase ab.

**Änderungen außerhalb des Pakets:** `tests/contracts/test_vertrag.py` (Erwartung `fcm` vor
`stub`), `tests/run_all.py`, `.github/workflows/ci.yml`, `requirements.txt`, `.importlinter`,
`docs/Theoriehandbuch.md` Kapitel 11.

**Stand Teilprojekt 3 (28.09.2026, auf `feature/volumen3d`, noch kein Pull Request):**
Pull Request 8 (Stufe 1) ist am 28.09. nach `main` gegangen (Merge c54af91). Seither: Zwangszyklen
strukturell beseitigt (Wurzeln der Aggregation nie feiner, gröbste Zelle als Eigentümer geteilter
Moden), Aufbauzeit halbiert (Lamé CSG 21,4 s, STL 18,0 s), matrixfreier Operator mit numba
(`fcm/operator.py`, = Matrix auf 10⁻¹⁵, 18,7 ms je Anwendung bei 229 608 Freiheitsgraden) und
PCG mit Jacobi und projizierten Mittelwertzwängen (`linalg/pcg.py`, `FcmProblem(loeser="pcg")`).
Befund: Kondition der Jacobi-vorkonditionierten Matrix 10⁶ bis 5·10⁷, 5 000 bis 20 000
Iterationen – die Messlatte für das Mehrgitter (Teilprojekt 4); der Direktlöser bleibt Standard
der Vertragsschicht. GPU-Kerne mit CuPy sind da (3,1 ms je Anwendung bei 229 608
Freiheitsgraden gegen 18,8 ms CPU). Vertrag 2.1.0 (Merge bdac39d, 28.09.) ist angeschlossen:
`DetailModelSpec.loads` je Lastfall-ID (Druck, Traktion, Resultierende über benannte Fläche, Box
oder Zylinder) und `body_load`, mit Protokoll je Last (Fläche, Schwerpunkt, Kraft, Moment).
Teilprojekt 4 (p-Mehrgitter, `fcm/mehrgitter.py`, 28.09.) senkt die Iterationszahlen mit
Zellblock-Schwarz-Glätter auf 26 bis 53 in allen Abnahmefällen (Jacobi: 2 580 bis über 40 000),
`FcmProblem(loeser="mehrgitter")`; mit `backend="gpu"` läuft der V-Zyklus auf der Grafikkarte
(Kirsch h 10 p 3: 8,6 bis 21 s gegen 7 bis 25 s Lösen des Direktlösers), freie Starrkörper-
bewegungen werden erkannt und herausprojiziert. `FcmSettings.backend = "auto"` (Standard) wählt den im
Gesamtweg schnelleren Weg; auf der gemessenen Karte (RTX 3070, 8 GB) ist das bis zur Speichergrenze des
Mehrgitters der Direktlöser: in der Schlussmessung vom 29.09.2026 (23 Fälle, kompakter Block und dünne
Kirsch-Scheibe, 65 000 bis 497 000 Freiheitsgrade) war er in 20 Fällen schneller (Theorie 11.10). `"gpu"`
erzwingt das Mehrgitter auf der Grafikkarte, mit Rückfall auf den Direktlöser bei fehlender GPU, zu wenig
Speicher oder jedem GPU-Fehler; `"cpu"` rechnet direkt. Vorher behoben: Nullraumerkennung größenunabhängig
und auch mit Schnittebenen, Aggregationswurzeln höchstens zwei Zellen entfernt und Aggregationsschwelle
0,4, GPU-Speicher in Teilstapeln und richtig geschätzt. Seit dem 30.09.2026 (Plan Teilprojekt 5, A3) liegen Zellmatrizen und
Glätterblöcke symmetrisch gepackt auf der Grafikkarte, und die feine Matrix bleibt auf der CPU: Modelle mit
einer Million Freiheitsgraden rechnen mit 4,4 bis 4,8 GB auf der 8-GB-Karte (vorher 10,8 bis 12,2 GB
geschätzt), in 29 bis 36 Iterationen und mit denselben Ergebnissen wie der Direktlöser. Seit A5 glättet das Mehrgitter mit einem breiteren Chebyshev-Fenster und löst dadurch 20 bis 22 % schneller bei gleichen Ergebnissen; die Iterationszahl streut über die Schnittlagen der dünnen Kirsch-Scheibe weiter um −25 bis +29 % (Ursachen in Theorie 11.10). Die Löserwahl wurde am 30.09.2026 neu gemessen (A6): `auto` bleibt beim Direktlöser; das Mehrgitter ist am kompakten Block ab 185 000 Freiheitsgraden 12 bis 27 % schneller und bei 10⁶ Freiheitsgraden in beiden Modellfamilien vorn (Block 115 statt 280 s), an der dünnen Scheibe darunter langsamer. Lösen allein unter 60 s bei 10⁶ Freiheitsgraden (7 bis 8 s); Aufbau plus Lösen 62 bis 115 s, der Hauptposten sind die Zellsteifigkeiten der Schnittzellen. Dagegen gibt es seit dem 30.09.2026 das Moment Fitting (Theorie 11.11): je Schnittzelle eine Regel mit (2p+1)³ Punkten, die dieselben Zellmatrizen liefert wie die rekursive Integration (auf 10⁻¹³) und auf gekrümmten Rändern 17- bis 34-mal weniger Punkte braucht; seit dem 30.09.2026 Vorgabe (Entscheidung des Anwenders), `momentfitting=False` schaltet zurück. Die
Oberflächenspannungen in `DetailResult.stress` sind seit demselben Tag geglättet (L²-Projektion, Theorie 11.12); das
Protokoll nennt das unter `stress_recovery`. Für das Hauptprogramm ändern sich Form und Einheit nicht, nur die Werte
an der Oberfläche werden glatter. `DetailResult.hot_spots` trägt seit B3 die Strukturspannung nach IIW Typ a je
Punkt einer `WeldLine` (Blechseite aus der Geometrie, Warnung statt Wert bei Mehrdeutigkeit); CSG-Geometrien mit
verschachtelten Bäumen (Kehlnähte als Schnitt aus Quader und Halbraum) werden seither exakt integriert. Seit B4 fährt `solve` mit
`FcmSettings.adaptive_cycles` (0 bis 4) mehrere Zyklen (lokale h-Halbierung an den Nähten und p + 1, ohne Fehlerschätzer) und liefert die
Konvergenzkurve in `DetailResult.convergence`, alle Einstellungen im Protokoll (`settings`) und eine Konvergenzaussage
(`convergence_statement`): die Aussage bewertet die letzte relative Änderung gegen die Schranke 3 % (`konvergiert` / `nicht_konvergiert`; Monotonie und Aitken-Grenzwert
stehen zusätzlich, Theorie 11.14, Entscheidung O4) – Knotenblech 0,44 %, T-Stoß in der p-Phase 0,47 %, beide konvergiert und nicht monoton; `nicht_konvergiert` und `ohne_aenderung`
tragen eine Warnung. Der Hot-Spot streut mit der Lage des Gitters zur Naht: bei Zellgröße t/4 und p 4 im Mittel 143,6 N/mm² mit der Spanne 138,9 bis 147,2 N/mm² (5,7 %), gegen die
Tet10-Referenz je Lage −2,93 % bis +3,10 % (Theorie 11.20, Entscheidung O3: als Band berichtet). Seit B5 liest `GeometrySourceType.STEP` Dateien über gmsh (optionales Extra `step`, GPL; ohne gmsh `SolverError` mit Hinweis): Tessellierung, Einheit nach mm, dann der STL-Weg. Seit B6 integriert der STL-Weg tessellierte Hüllen (STL und STEP) je Zelle exakt über den Divergenzsatz (Theorie 11.16): Volumen und Zellregeln sind für die Tessellierung exakt, kein Punkttest, Block mit Bohrung N 120 bei h 25 in 27 s statt 388 s, K_t durch den Vertragsweg gegen CSG auf 0,12 % (p 2); die Krümmung steckt nur in der Tessellierung (`elements_per_circle`, Vorgabe 120: Volumenfehler der Bohrung +0,0047 %). Läuft eine Schnitt- oder Symmetrieebene durch den gekrümmten Teil der Hülle, gilt in diesen Zellen weiter der alte Weg mit Punkttest und Warnung. Große Netze (ab 20 000 Facetten) entscheiden innen/außen über den Windungszahl-Baum nach Barill (28-mal schneller, gleiche Entscheidung an 100 000 Punkten). `summary()` und Protokoll nennen den Weg
(`solver_path`, `backend`, `solver_choice`); für das Hauptprogramm ändert sich an der Schnittstelle nichts. Seit B7 ist die Kopplung von einem Schalen-Globalmodell (lineare Verteilung über die Dicke) mit einem Provider-Stub geprüft: Schnittgrößenabweichung unter 10⁻³ bei p 2 und 10⁻⁷ bei p 3 (Vorgabe 1 %, Theorie 11.17); die Kopplungskontrolle bezieht Kraft und Moment auf ein gemeinsames Lastmaß, damit reine Biegung keine Scheinabweichung der Kraft meldet. Der Provider selbst ist Sache des Hauptprogramms. Die Abnahme von Teilprojekt 5 am Knotenblech mit Kehlnaht (C1, Theorie 11.18) hält gegen die Tet10-Referenz des Hauptprogramms (Pull Request 13 auf main; rechts +0,3 %, links −2,9 %, Schranke 3 %); abgelegt von der Hauptsitzung nach E2/E3 (Vorschlag `docs/vertrag-aenderungen/2026-10-01-referenzmodell-knotenblech.md`, Paket in `Desktop/Statik3D/REFERENZ-KNOTENBLECH-2026-10-01/`). Die Streuung des Hot-Spots mit der Gitterphase (3 % bei t/4 und p 4) ist der offene Punkt der Hot-Spot-Robustheit. Die zweite Sicht (C2, Theorie 11.19) hat 24 Befunde bestätigt und die wesentlichen behoben; für das Hauptprogramm sichtbar sind: STEP-Dateien mit mehreren Körpern werden vereinigt (durchdringende STL-Schalen geben einen Fehler), die Kopplungskontrolle bewertet Abweichungen als Spannungen (`reference_stress`, `deviation_measure` im `coupling_check`; Momentfehler an dünnen Blechen werden jetzt gemeldet), `hotspot_max` ist der betragsgrößte Wert mit Vorzeichen, die Konvergenzaussage kennt `ohne_aenderung`, und Hot-Spots haben eine Anwendbarkeitsprüfung (ebene Blechoberfläche über 1,0 t). Offen aus Teilprojekt 2: die Vierteilung der Randpolygone an gekrümmten Formen; offen aus B7: Konsistenzfehler des p-2-Ansatzes am schrägen Schnitt (10⁻⁴ bis 3,5·10⁻³ in der Spannung).
