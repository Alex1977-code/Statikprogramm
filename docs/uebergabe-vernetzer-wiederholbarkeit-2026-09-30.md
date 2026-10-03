# Für die Vernetzersitzung: dasselbe Drehlager wird bei jedem Lauf anders vernetzt

Übergabe aus der Kontakt-/Lösersitzung, gemessen am 29.09.2026, abgelegt am 30.09.2026.
Zweig `claude/statikprogramm-analog-ansys-bzfhij`, Stand `7da3571`.

Ich fasse den Vernetzer **nicht** an — das ist euer Thema (`docs/Mitarbeit.md`,
Abschnitt 5a). Hier steht nur, was ich gemessen habe, damit ihr es aufgreifen
könnt, ohne es nochmal zu messen.

## Was gemessen ist

Der Drehlager-Kontrolllauf (`Gleichungsloeser/bench/drehlager_kontrolllauf.py`)
lädt jedes Mal dieselbe Datei (`modell_20260925_0638/drehlager.json`, sha256
`769e71877aba…`), schaltet den Sweep aus und vernetzt mit
`mesher.modell_vernetzen(m, log=log, workers=12)` neu — dieselbe Folge wie die
Oberfläche. Jeder Lauf kam aus einem festen `git worktree` des genannten Commits.
Die vier Läufe vom 28.09.2026:

| Lauf | Commit | Tetraeder (tet4) | Knoten | Vernetzen |
|---|---|---|---|---|
| fortschritt | `ec3b464` | 654 957 | 160 857 | 481 s |
| reibung_pd | `00763ae` | 655 092 | 160 850 | 333 s |
| mortar | `81e7b64` | 654 951 | 160 837 | 253 s |
| einzeilig | `18a770d` | 655 420 | 160 903 | 252 s |

Zwischen `ec3b464` und `18a770d` haben sich nur `statik3d/contact.py`,
`mortar.py`, `plastizitaet.py` und `solver.py` geändert (`git diff --stat
ec3b464 18a770d -- statik3d`) — nichts, was vor dem Rechnen läuft. Das Netz
ist trotzdem jedes Mal ein anderes: vier Läufe, vier Elementzahlen, Spanne
469 Tetraeder (0,07 %).

Was das kostet: zwei PARDISO-Läufe mit verschiedenen Netzen (`81e7b64` gegen
`18a770d`) unterscheiden sich an den Bohrungskörpern um bis zu 1,74 % in σ_v
(V35: 373,3 gegen 379,8 N/mm²), an u_max nur um 0,023 %. Ein Vergleich zweier
Rechenstände am Drehlager misst damit immer das Netz mit. Für die Vergleiche
der Löser habe ich seither das gespeicherte Netz eines Laufs geladen
(`modell_vernetzt.json` von `18a770d`), statt neu zu vernetzen.

## Was nicht gemessen ist

* Ob es an der Arbeiterzahl hängt (alle vier mit 12 Arbeitern) oder auch mit
  einem Arbeiter auftritt.
* Wo die Reihenfolge herkommt — Rückgabe der Arbeiter in Ankunftsreihenfolge,
  Iteration über ein `set` (Python mischt Hashwerte von Zeichenketten je
  Prozess neu, solange `PYTHONHASHSEED` nicht gesetzt ist) oder Rundung in
  einer parallelen Summe wären Kandidaten; keiner davon ist geprüft.

Nach `CLAUDE.md` („Robust statt Glückssache“) wäre das Ziel, dass dieselbe
Datei mit demselben Stand dasselbe Netz ergibt — belegt mit zwei Vernetzungen
hintereinander und einem Vergleich der Knotenkoordinaten.
