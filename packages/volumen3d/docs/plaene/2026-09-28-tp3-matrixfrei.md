# Plan Teilprojekt 3 (Stufe 2a): Matrixfreier Operator und vorkonditioniertes CG

> Vorgehen: `superpowers:executing-plans` (Aufgaben nacheinander, Prüfung nach jeder Aufgabe,
> Commit je Aufgabe). Entwurf: `packages/volumen3d/docs/Entwurf.md`, Abschnitt 4c.
> Vorgabe 8.1, 8.2, 9. Alles nur in `packages/volumen3d/`; Ergebnisse werden gegen die
> assemblierte Matrix aus Teilprojekt 1 gemessen, nicht gegen Erwartungen.

**Ziel:** v = K·u ohne globale Matrix, Zwänge (hängende Freiheitsgrade, Aggregation) und Nitsche-
Ränder im Operator, Lösung mit vorkonditioniertem CG (Jacobi) auf der CPU mit numba; danach
derselbe Operator als CuPy-Kern. Abnahme: Operator gegen Matrix auf 10⁻¹², PCG trifft den
Direktlöser auf 10⁻⁸ (relatives Residuum), Kirsch p 3 und Lamé p 3 unverändert.

**Reihenfolge (jede Aufgabe: Prüfung schreiben → rot → umsetzen → grün → Kernsuite → Commit):**

### Aufgabe 1: Zellbeschreibung im SoA-Layout (`fcm/operator.py`, `tests/test_operator.py`)
- `Zelldaten(problem)`: INSIDE-Zellen je Ebene (Indizes, Freiheitsgradtabelle `dofs` (nz, 3m)
  int32), eine Referenz-Zellmatrix K_ref(h₀) je p und Werkstoff (K ∝ h, also K_e = (h_l/h₀)·K_ref);
  CUT-Zellen mit gespeicherter Zellmatrix K_e (3m×3m, FP64) – Speicherabschätzung im Protokoll
  (Kirsch h 10 p 3: 1722 Schnittzellen × 295 KB = 0,5 GB; p 4: 1,9 GB → Grenze prüfen, sonst
  Quadratursätze statt Matrizen, Vorgabe 8.1 „konfigurierbar“).
- Einsammeln ohne Wettlauf: Inzidenz „Freiheitsgrad → (Zelle, lokaler Index)“ als CSR; der
  Zellkern schreibt in einen Puffer (nz, 3m), das Einsammeln läuft je Freiheitsgrad parallel
  (Gather statt Scatter, keine Atomics, keine Färbung).
- Prüfung: `dofs` und Inzidenz stimmen mit `gitter.zell_dofs`; Summe der Zellmatrizen über die
  Inzidenz = assemblierte Matrix aus `elastizitaet.assemblieren` (Kirsch h 20 p 2, Lamé h 20 p 2:
  max |ΔK| < 10⁻¹² relativ).

### Aufgabe 2: Operator auf der CPU (`fcm/operator.py`, numba)
- `Operator.anwenden(u) -> v` für den vollen Vektor (n_dof): INSIDE-Kern `K_ref @ u_e` skaliert
  mit h_l/h₀, CUT-Kern `K_e @ u_e`, beide als `numba.njit(parallel=True)` über Zellen; ohne numba
  ein numpy-Rückfall (Blockmultiplikation je Ebene). Nitsche-Steifigkeit (`rand.nitsche_steifigkeit`)
  bleibt eine dünnbesetzte Matrix K_rand (Randanteil klein) und wird addiert.
- Freier Operator A = Cᵀ (K + K_rand) C mit der Zwangsmatrix C aus `Zwaenge` (scipy.sparse);
  `Operator.frei_anwenden(x)`.
- Prüfung: für 20 Zufallsvektoren ‖A x − (Cᵀ K_ges C) x‖ / ‖K_ges x‖ < 10⁻¹² auf Kirsch h 10 p 3
  (verfeinert), Lamé h 10 p 3, Patch-Test dünne Wand (hängende Zwänge + Aggregation);
  Zeit je Anwendung im Protokoll (`t_operator_s`), Ziel Kirsch h 10 p 3 (199 095 freie
  Freiheitsgrade) < 0,2 s auf der CPU.

### Aufgabe 3: Summenfaktorisierung für INSIDE-Zellen
- Tensorstruktur der Basis: u_e (p+1)³×3 → Gradienten über drei 1D-Matrizen (Werte/Ableitungen an
  den Gauß-Punkten), Spannung punktweise (λ, μ), Rückweg transponiert: O(p⁴) statt O(p⁶); als
  numba-Kern mit festen Feldern je Zelle.
- Prüfung: Ergebnis identisch zu K_ref @ u_e (< 10⁻¹³); Messung p 2, 3, 4 gegen die dichte
  Zellmatrix (erwartet: Faktor 2 bis 4 ab p 3; bleibt die dichte Matrix schneller, bleibt sie der
  Standard und die Summenfaktorisierung eine Option – gemessen, nicht angenommen).

### Aufgabe 4: PCG mit Jacobi (`linalg/pcg.py`)
- Diagonale von A exakt aus den Zellmatrizen: je Zelle C_e (lokale Zeilen von C, dicht klein)
  und diag(C_eᵀ K_e C_e) aufsummiert; K_rand-Diagonale dazu.
- PCG (FP64) mit relativer Residuumsschranke `FcmSettings.tolerance` (Standard 10⁻⁸) und
  Energienormkontrolle (Vorgabe 8.2); mehrere Lastfälle nacheinander mit gemeinsamem
  Vorkonditionierer (Block-CG später).
- 'schnitt'-Projektion (drei Mittelwertzwänge je Schnittebene, bisher Sattelpunkt): projizierter
  CG – Nebenbedingung B x = b (3 Zeilen je Ebene) über P = I − Bᵀ(BBᵀ)⁻¹B, Startwert als
  Partikulärlösung; kein Sattelpunkt, A bleibt symmetrisch positiv definit.
- Prüfung: Lösung gegen Direktlöser auf 10⁻⁸ (relativ) für Patch, Kragarm (schnitt), Lamé, Kirsch;
  Iterationszahlen im Protokoll und in der Theorie (Erwartung mit Jacobi allein: Hunderte bis
  Tausende – das ist der Ausgangspunkt für das Mehrgitter in Teilprojekt 4, kein Mangel dieser
  Stufe); Abbruch über `ProgressCallback` (SolverCancelled).

### Aufgabe 5: Anschluss an die Vertragsschicht (`api.py`, `fcm/problem.py`)
- `FcmSettings.backend`: 'cpu' → matrixfrei + PCG als Standard, wenn die Zellmatrizen ins
  Speicherbudget passen (`estimate` nennt beides: Matrix und matrixfrei); Direktlöser bleibt als
  `loeser="direkt"` erreichbar (Referenz, kleine Modelle, Sattelpunkt-Sonderfälle).
- Protokoll: `loeser`, `iterationen`, `residuum_rel`, `t_operator_s`, Speicher.
- Prüfung: `test_vertrag_fcm` und Kernsuite grün, `FcmSolver.solve` liefert mit PCG dieselben
  Spannungen wie mit dem Direktlöser (10⁻⁶ relativ) am Vertragsbeispiel.

### Aufgabe 6: GPU mit CuPy (`fcm/operator_gpu.py`, `linalg/pcg.py` mit `xp`)
- Zellkerne als `cupy.RawKernel` (dichte Zellmatrix je Zelle, ein Block je Zelle, Puffer +
  Gather), C und K_rand als `cupyx.scipy.sparse`; PCG mit `xp = cupy`. Nur lokal prüfbar
  (RTX 3070, 8 GB), in der CI übersprungen.
- Prüfung: GPU-Operator gegen CPU auf 10⁻¹² (FP64), PCG-Lösung identisch auf 10⁻⁸; Zeiten CPU/GPU
  je Anwendung; Speicherabschätzung gegen `cupy.cuda.Device().mem_info`.

### Aufgabe 7: Abschluss
- Theoriehandbuch 11.9 (Operator, Zwänge im Operator, projizierter CG, Messwerte), Entwurf 4c
  mit Zahlen, `docs/Volumenmodul.md`; Kernsuite um `test_operator.test_kern` (klein, CPU);
  zweite Sicht (Subagent); Commit-Folge auf `feature/volumen3d`, Pull Request erst nach
  Teilprojekt 4 (Stufe 2, Vorgabe 12).
