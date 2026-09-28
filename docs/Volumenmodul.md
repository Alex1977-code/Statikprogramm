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
| Geometriekern | `geometry/sdf.py`, `csg.py`, `polyeder.py`, `oberflaeche.py`, `stl.py`, `dreiecksbaum.py` | CSG aus `GeometrySource.params` (Quader, Zylinder, Kugel, Halbraum, **STL**; Vereinigung, Differenz, Schnitt), konservative Abstände, lokale konvexe Stücke (STL: konvex / konkav / gemischt per binärer Raumteilung), Flächenquadratur auf der exakten Oberfläche; Randpolygone auf Zellflächen zählen genau einmal. STL: Windungszahl (robust gegen Lücken, `defekt` im Protokoll), BVH mit numba (ohne numba k-d-Baum-Index, gleiche Ergebnisse) |
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
bewegungen werden erkannt und herausprojiziert. Seit dem 28.09.2026 abends wählt die Vertragsschicht mit
`FcmSettings.backend = "auto"` (Standard) den schnelleren Weg: das Mehrgitter auf der GPU ab 200 000
Freiheitsgraden bei genug GPU-Speicher, sonst den Direktlöser; `"gpu"` erzwingt das Mehrgitter (Rückfall
ohne GPU mit Warnung), `"cpu"` den Direktlöser. Gemessen (Kirsch h 10 p 3, Gesamtweg): 32,9 gegen 34,4 s
und 35,3 gegen 57,4 s; darunter bleibt der Direktlöser schneller. `summary()` und Protokoll nennen den Weg
(`solver_path`, `backend`, `solver_choice`); für das Hauptprogramm ändert sich an der Schnittstelle nichts. Offen aus Teilprojekt 2: der schnelle Windungszahl-Baum für STL-Netze
über 10⁵ Facetten (Teilprojekt 5) und die Vierteilung der Randpolygone an gekrümmten Formen.
