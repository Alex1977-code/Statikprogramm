# Volumenmodul `volumen3d`: Stand der Umstellung im Hauptprogramm

Grundlage: `Schnittstellenvertrag_Statik3D_FCM.md` (Vertragsversion 2.0.0) und
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

## Abweichungen vom Vertrag, bewusst

- **Repository-Aufbau (Abschnitt 1):** `statik3d/` bleibt vorerst an der Wurzel, nicht unter
  `packages/statik3d/`; der Umzug würde Importe, Tests und den exe-Bau (`packaging/Statik3D.spec`)
  auf einmal ändern. `packages/statik3d_contracts/` liegt wie vereinbart; `packages/volumen3d/`
  legt Session B an.
- **Einheiten:** Statik3D rechnet intern in SI (m, N, Pa); der Vertrag verlangt mm und N/mm².
  Die Umrechnung liegt beim Hauptprogramm an der Grenze zum Volumenmodul
  (`diskretisierung.MM`); die Kopplung (`GlobalFieldProvider`) muss sie ebenso leisten.
- **Stub-Registrierung:** Der Vertrag sieht Entry Points nur in `volumen3d/pyproject.toml` vor.
  Damit die Registrierung ohne `volumen3d` prüfbar ist, trägt das Vertragspaket seine Stubs
  unter `stub` ein; `volumenloeser()` bevorzugt jeden anderen registrierten Löser.

## Offen (Abschnitt 10, Session A)

- 10.3 `GlobalFieldProvider` des Hauptprogramms (punktweise Abfrage der Ergebnisse, zunächst
  für Stäbe: Querschnittskinematik aus den Stabfreiheitsgraden).
- 10.4 Modellbaum-Knoten „Detailmodelle (Volumen)“ aus `DetailModelSpec`; Ribbons nach
  Vorgabe Abschnitt 15.
- 10.2 weiter: Stellen, die direkt auf Knoten-/Elementlisten zugreifen, nach und nach über
  das Protokoll führen.
- Referenzmodelle `tests/reference_models/` (Vertrag Abschnitt 8) als JSON/YAML mit
  Erwartungswerten – gemeinsam mit Session B.
