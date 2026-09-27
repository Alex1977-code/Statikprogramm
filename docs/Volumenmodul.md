# Volumenmodul `volumen3d`: Stand der Umstellung im Hauptprogramm

Grundlage: `Schnittstellenvertrag_Statik3D_FCM.md` (Vertragsversion 2.0.1) und
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


## Session B: Stand des Volumenmoduls `volumen3d` (Teilprojekt 1, 27.09.2026)

Zweig `feature/volumen3d` (Worktree `Desktop/Statik3D/statik3d-volumen3d`, eigene venv mit
numba und cupy für die späteren Stufen). Entwurf und Zerlegung: `docs/Volumenmodul_Entwurf.md`;
Plan: `docs/superpowers/plans/2026-09-27-volumen3d-tp1-fcm-kern.md`; Theorie und Messwerte:
`docs/Theoriehandbuch.md`, Kapitel 11. Regeln der Sitzung: `packages/volumen3d/CLAUDE.md`.

| Teil | Ort | Stand |
|---|---|---|
| Paket nach Vertrag Abschnitt 1 | `packages/volumen3d/` (geometry, fcm, linalg, postprocess, api) | Entry Points `fcm` (echt) und `hybrid` (Platzhalter bis TP 7), `import-linter` (`.importlinter`) und `mypy --strict api.py` in der CI |
| Geometriekern | `geometry/sdf.py`, `csg.py`, `polyeder.py`, `oberflaeche.py` | CSG aus `GeometrySource.params` (Quader, Zylinder, Kugel, Halbraum; Vereinigung, Differenz, Schnitt), konservative Abstände, lokale konvexe Stücke, Flächenquadratur auf der exakten Oberfläche |
| FCM-Kern | `fcm/basis.py`, `gitter.py`, `quadratur.py`, `aggregation.py`, `elastizitaet.py`, `rand.py`, `problem.py` | Legendre-Basis p = 1…4, Wurzelgitter (Oktree-Ebene 0), ebenen-exakte Schnittzellen-Integration, Zellaggregation, Nitsche (voll / normal / schnitt), Lasten, Direktlöser (pypardiso, sonst SuperLU) |
| Vertragsschicht | `api.py` | `FcmSolver.estimate/prepare/solve`, `FcmDiskretisierung` (summary, preview mit Zellklassen), Kopplungskontrolle je Schnittebene mit Multiplikatoren und Warnung > 5 %, Protokoll |
| Prüfungen | `tests/volumen3d/` | Kernsuite `test_kern` (in `run_all` und CI); Abnahmen `test_patch` (< 10⁻⁶: gemessen 10⁻¹²…10⁻⁸), `test_kragarm` (reine Biegung exakt, Stub gegen Timoshenko −0,9 % / +2,7 %), `test_lame` (p = 3: σ_r 0,32 %, σ_φ 0,03 %), `test_kirsch` (K_tg +1,35 % gegen Howland; **Schnittlagen-Streuung 7,9 % – Abnahme < 1 % offen bis zur Verfeinerung an Bohrungen in TP 2**) |

**Bewusste Abweichungen von der Vorgabe (Messung, Begründung im Entwurf 3.5/3.6 und Theorie 11):**
Punkttest der Schnittzellen nur als Rückfall (erster Ordnung, Patch-Test sonst unerreichbar);
Zellaggregation schon in Stufe 1 und α nur für Zellen ohne Wurzel; an Schnittebenen
Normalkomponente punktweise plus Resultierende in der Ebene statt aller drei Komponenten.

**Vorschläge an den Vertrag** (`docs/vertrag-aenderungen/2026-09-27-lasten-und-schnittgroessen.md`):
Lasten im `DetailModelSpec` (Minor 2.1.0) und Klarstellung der Seite der Schnittgrößen.

**Änderungen außerhalb des Pakets:** `tests/contracts/test_vertrag.py` (Erwartung `fcm` vor
`stub`), `tests/run_all.py`, `.github/workflows/ci.yml`, `requirements.txt`, `.importlinter`,
`docs/Theoriehandbuch.md` Kapitel 11.

**Nächste Schritte (Teilprojekt 2, Stufe 1b):** Oktree-Verfeinerung mit hängenden
Freiheitsgraden (Zwangsmatrix wie bei der Aggregation), STL-Eingang (BVH, Windungszahl),
Geometriekern vektorisieren (die Flächenquadratur dominiert die Aufbauzeit), dann Pull Request 1.
