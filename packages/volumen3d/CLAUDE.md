# Volumenmodul `volumen3d` – Regeln für die Sitzung, die hier arbeitet (Session B)

Alles auf Deutsch (Bezeichner ohne Umlaute, Anwendertexte mit), Kommentare sagen warum,
Zahlen nur gemessen – wie in der `CLAUDE.md` an der Repository-Wurzel.

## Grenzen

* **Arbeiten nur in diesem Paket** (`packages/volumen3d/`), auf einem eigenen Zweig
  (`feature/volumen3d…`). Nichts außerhalb ändern.
* **Nur lesen:** `packages/statik3d_contracts/` (der Vertrag als Code), `tests/reference_models/`,
  und das Hauptprogramm `statik3d/` an der Repository-Wurzel – lesen erlaubt, nie anfassen.
  Insbesondere `statik3d/contact.py` und `statik3d/solver.py`: das Hauptprogramm hat einen
  eigenen Kontaktlöser (exakte Normalbedingung, Reibung, Plastizität; er rechnet das Drehlager).
  **Kein zweiter Kontaktlöser daneben, ohne dass das entschieden ist.** Ob der bestehende
  Kontaktcode hinter das `AssemblySolver`-Protokoll wandert oder `volumen3d` ihn ablöst,
  entscheidet der Anwender; bis dahin: lesen, am Ende von Stufe 5 dagegen vergleichen.
* `volumen3d` importiert `statik3d_contracts`, **niemals** `statik3d` (import-linter in der CI).

## Verbindlich

* `docs/Schnittstellenvertrag_Statik3D_FCM.md` (Vertragsversion, Abschnitt 9) und
  `docs/Vorgabe_Statik3D_Abschnitt_FCM-Volumenloeser.md`; Umsetzung nach Abschnitt 12 bzw.
  16.10 der Vorgabe, stufenweise.
* Braucht diese Sitzung etwas Neues im Vertrag: **nicht selbst ändern**, sondern einen Vorschlag
  nach `docs/vertrag-aenderungen/` legen (siehe README dort). Der Anwender entscheidet, die
  Änderung kommt als eigener Pull Request auf `main`, beide Sitzungen holen sie per Rebase ab.
* Löser werden über die Entry-Point-Gruppen `statik3d.solid_solvers` (`fcm`) und
  `statik3d.assembly_solvers` (`hybrid`) registriert (`pyproject.toml`), Vertragsversion
  `contract_version` gesetzt; das Hauptprogramm zieht echte Löser immer dem Stub vor.

## Zusammenführen

Nach jeder abgeschlossenen Stufe ein Pull Request mit grüner CI (`tests/contracts`,
`mypy --strict` für das Vertragspaket, `lint-imports`). Kleine Unterschiede, früh gegen den
echten Löser statt gegen den Stub prüfen.

## Arbeitsstand und Prüfen (Session B, seit 27.09.2026)

* Entwurf, Zerlegung in Teilprojekte und Plan liegen im Paket: `docs/Entwurf.md`,
  `docs/plaene/`. Theorie mit Messwerten steht im `docs/Theoriehandbuch.md` der Wurzel,
  Kapitel 11 (Handbuchpflicht der Wurzel-`CLAUDE.md`); Stand für die Hauptsitzung in
  `docs/Volumenmodul.md`. Änderungen außerhalb des Pakets bleiben auf die Einbindung
  beschränkt (Eintrag der Kernsuite in `tests/run_all.py` und der CI, `requirements.txt`,
  `.importlinter`-Regel für `volumen3d`, Handbuchkapitel) und werden im Pull Request einzeln
  benannt.
* Die Prüfsuiten liegen im Paket (`volumen3d/tests/`), Aufruf aus der Repository-Wurzel:
  ```
  py -3.11 -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
  .venv\Scripts\pip install -e packages/statik3d_contracts -e packages/volumen3d
  .venv\Scripts\pip install numba cupy-cuda12x mypy import-linter   # GPU: CUDA-12-Treiber genügt

  .venv\Scripts\python.exe -m volumen3d.tests.test_kern        # Kernsuite (in run_all und CI)
  .venv\Scripts\python.exe -m volumen3d.tests.test_<suite>     # einzelne Suite; Abnahmen: test_kragarm, test_lame, test_kirsch
  .venv\Scripts\python.exe -m mypy --strict --follow-imports=silent packages/volumen3d/volumen3d/api.py
  lint-imports
  ```
* Erwartungswerte in den Suiten mit Quelle und Formel nennen und im Test selbst ein zweites Mal
  unabhängig berechnen. GPU-Prüfungen laufen nur lokal (RTX 3070, 8 GB); die CI hat keine GPU.
* Session A rechnet lokal im Klon `Desktop/Statik3D/Statikprogramm` (Drehlager-Läufe mit vielen
  Arbeitsprozessen); dieser Worktree liegt in `Desktop/Statik3D/statik3d-volumen3d`. Vor großen
  Läufen die Prozessliste prüfen und nacheinander rechnen.
