# Statik3D — Hinweise für Claude Code

Finite-Elemente-Statikprogramm in Python (numpy/scipy) mit Qt-Oberfläche.
Einheiten durchgängig SI: **m, N, Pa, kg/m³**.

## Sprache

**Alles auf Deutsch**: Bezeichner, Kommentare, Docstrings, Oberflächentexte,
Protokollzeilen, Handbücher, Commit-Nachrichten. Im Quelltext ohne Umlaute
(`Randflaeche`, `Guete`); in allem, was der Anwender liest, mit Umlauten.

Kommentare sagen **warum**, nicht was. Wo eine Entscheidung an Zahlen hängt,
stehen die Zahlen dabei — gemessen, nicht geschätzt.

## Arbeitsweise

* **Nicht raten.** Jede Behauptung über das Verhalten des Programms wird an
  einer Messung belegt, bevor sie in Code oder Text steht. Auch die
  Behauptungen aus einer Anweisung: erst am Quelltext prüfen, dann handeln;
  was sich nicht bestätigt, wird begründet zurückgewiesen.
* **Robust statt Glückssache.** Ein Verfahren, dessen Ergebnis an Rundung,
  Gitterphase oder Reihenfolge hängt, ist keines. Wo möglich wird die
  Eigenschaft erzwungen und nicht gehofft — und mit einer Stichprobe über
  den Parameterraum belegt, nicht an einem Beispiel.
* Zu jeder Änderung am Verhalten: ein Test, der ohne sie fehlschlägt, und
  ein Absatz im passenden Handbuch.

## Tests

```
python -m tests.run_all          # alle Suiten ohne Oberfläche
python -m tests.run_all --gui    # mit Oberfläche
python -m tests.test_mesher3d    # eine einzelne Suite
```

`run_all` nimmt die Oberflächenprüfung **nur mit `--gui`** mit; unter Linux
ohne `DISPLAY` startet sie selbst `xvfb-run`. Die Oberflächenprüfung schreibt
`tests/_gui_smoke.png` und `tests/_gui_fenster.png` neu — `tests/_gui_fenster.png`
ist eingecheckt und wird vor dem Commit zurückgesetzt:

```
git checkout HEAD -- tests/_gui_fenster.png
```

Vor jedem Commit läuft der Gesamtlauf durch (`ALLE TESTS BESTANDEN`) und die
Oberflächenprüfung getrennt.

## Einrichten

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
```

Python 3.11 ist der Stand, mit dem gebaut wird (`requires-python >= 3.9`).
`pypardiso`/`mkl` sind kein Beiwerk: ohne sie fällt der Löser auf SuperLU
zurück und rechnet auf **einem** Kern (Würfel mit 34.914 FHG: 12,25 s statt
1,38 s). Unter Linux fehlen sie oft — dann laufen die Tests trotzdem, nur
langsamer.

Starten: `python run_gui.py` (Desktop), `python run_web.py` (Handy/Browser).

## Zweig und Bau

Entwickelt wird auf `claude/statikprogramm-analog-ansys-bzfhij`. Ein Merge
nach `main` erfolgt **nur auf ausdrückliche Freigabe** und stößt
`.github/workflows/windows-exe.yml` an: der baut `Statik3D.exe`, führt sie mit
`--selbsttest` aus und veröffentlicht das Release `latest` neu.

## Aufbau

| Ort | Inhalt |
|---|---|
| `statik3d/model.py` | Datenmodell (Knoten, Linien, Flächen, Volumen, Lasten, Lager, Situationen) |
| `statik3d/mesher3d.py` | freier Vernetzer: Randhülle, Flächennetz, Tetraeder, Güte |
| `statik3d/mesher.py` | Netzsteuerung, modellweite Kantenlängenkarten, Parallelbetrieb |
| `statik3d/diagnose.py` | Abnahme des Netzes vor dem Rechnen, Meldungen im Klartext |
| `statik3d/solver.py`, `assemble.py`, `contact.py` | Rechnung |
| `statik3d/ec3/` | Nachweise nach EC3, Ermüdung |
| `statik3d/importers/` | RFEM/RSTAB, IFC, SAF, DXF, HiCAD, Abaqus, Nastran |
| `statik3d/gui/` | Qt-Oberfläche (`main.py`, `viewport.py`, `masken.py`, `symbole.py`) |
| `docs/` | Benutzer-, Theorie-, Schnittstellen- und Farm-Handbuch |

`docs/Theoriehandbuch.md` ist die Begründung des Verfahrens mit Messwerten,
`docs/Benutzerhandbuch.md` beschreibt, was der Anwender sieht und tut. Beide
werden mit jeder Verhaltensänderung fortgeschrieben.
