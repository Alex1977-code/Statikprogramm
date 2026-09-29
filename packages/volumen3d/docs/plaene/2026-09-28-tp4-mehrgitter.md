# Plan Teilprojekt 4 (Stufe 2b): p-Mehrgitter als Vorkonditionierer

> Vorgehen: `superpowers:executing-plans` (Aufgaben nacheinander, Prüfung nach jeder Aufgabe,
> Commit je Aufgabe). Entwurf: `packages/volumen3d/docs/Entwurf.md`, Abschnitt 4d. Vorgabe 8.3.
> Messlatte aus Teilprojekt 3: Jacobi-PCG braucht 5 045 (Patch h 20 p 2), 20 373 (Lamé h 20 p 3)
> und 4 420 Iterationen (Kirsch h 20 p 2 verfeinert); Richtwert der Vorgabe unter 100.

**Ziel:** PCG mit einem symmetrischen V-Zyklus über die Polynomgrade p → p−1 → … → 1 als
Vorkonditionierer, Chebyshev-Jacobi-Glätter, direkter Grobgitterlöser bei p = 1; Iterationszahlen
nahezu unabhängig von Modellgröße und Schnittlage; danach dieselben Kerne auf der GPU.

**Kern der Konstruktion (keine neue Integration):** Die hierarchische Basis ist geschachtelt – der
Raum vom Grad p−1 besteht aus den Moden, deren drei 1D-Indizes ≤ p−1 sind. Der Übergang ist
darum eine **Injektion** (Auswahl von Moden, keine Interpolation), der Galerkin-Grobgitteroperator
ist der Teilblock der Zellmatrizen (K_ref und K_cut auf die groben Moden eingeschränkt), und die
Zwänge sind geschachtelt: ein Meister vom Grad d trägt nur zu Sklaven vom Grad ≤ d bei (Spur
eines Polynoms vom Grad d ist vom Grad d; Fortsetzung der Aggregation ebenso), also gilt
C_fein·P̃ = P·C_grob und A_grob = P̃ᵀ A_fein P̃ exakt. Freie grobe Moden sind eine Teilmenge der
freien feinen Moden; P̃ ist die Injektion zwischen den freien Koordinaten.

### Aufgabe 1: p-Ebenen (`fcm/mehrgitter.py`, `tests/test_mehrgitter.py`)
- `PEbenen(problem)`: je Grad p_k = p, p−1, …, 1 eine Ebene mit eigener Modennummerierung (Kopie
  des Gitters mit `moden_nummerieren(p_k)` auf einem flachen Duplikat, Arrays geteilt), `Zwaenge`
  auf dieser Ebene (Aggregation mit derselben Wurzelwahl), Zelldaten mit Teilblöcken (INSIDE
  K_ref[sub, sub], CUT K_cut[:, sub, sub]), Nitsche-Matrix K_rand,k = P_kᵀ K_rand P_k, Injektion
  P_k (Moden) und P̃_k (freie Koordinaten) aus den lokalen Modenindizes je Zelle.
- `Zwaenge` bekommt `moden_frei_liste` (Modennummer je freier Spalte von C).
- Prüfung: P̃ injiziert (Spalten sind Einheitsvektoren); A_grob x = P̃ᵀ A_fein P̃ x auf 10⁻¹² für
  Zufallsvektoren (Patch dünne Wand, Lamé, Kirsch verfeinert) – das prüft die Schachtelung der
  Zwänge; Grobgitter p = 1 als explizite Matrix stimmt mit `Zelldaten.matrix()` überein.

### Aufgabe 2: Glätter und V-Zyklus (`linalg/mehrgitter.py`)
- Chebyshev-Jacobi vom Grad 2–4 auf dem Spektrum [λ_max/α, λ_max] von D⁻¹A, λ_max je Ebene aus
  10–20 Schritten Potenzmethode bei der Einrichtung (im Protokoll); α = 8 (Standard, gemessen
  gegen 4 und 16).
- Symmetrischer V-Zyklus: Vorglätten, Residuum, P̃ᵀ, rekursiv, P̃, Nachglätten; Grobgitter p = 1
  mit `Direktloeser` (pardiso/SuperLU) auf der assemblierten Matrix; als M⁻¹ im PCG
  (`linalg/pcg.py` unverändert). Mittelwertzwänge der Schnittebenen: der projizierte CG bleibt
  außen, der V-Zyklus wirkt auf P·r.
- Prüfung: ein V-Zyklus reduziert das Residuum (Faktor < 0,5 auf Patch h 20 p 2); PCG mit V-Zyklus
  trifft den Direktlöser (Spannungen 10⁻⁶) auf Patch, Kragarm (schnitt), Lamé, Kirsch verfeinert
  – Iterationen und Zeit je Fall im Protokoll, Ziel < 100 (Vorgabe 8.3), Vergleich mit Jacobi in
  der Theorie; p = 4 (Kirsch h 10) und Schnittlagen 0 / 0,4 / 0,8 als Robustheitsprobe.

### Stand 28.09.2026 mittags
Aufgaben 1 und 2 umgesetzt: Schachtelung exakt (0 … 3·10⁻¹⁶), V-Zyklus mit Chebyshev um einen
Glätter, Grobgitter p = 1 mit Sattelpunkt für die Mittelwertzwänge. Befund: Jacobi-Glätter
reicht nicht (637 bis über 2000 Iterationen, Cluster auf Moden von Schnittzellen mit Anteil ≈ 0
am Nitsche-Rand, λ ≈ 10⁻⁵); mit Zellblock-Schwarz 26 bis 53 Iterationen in allen fünf Fällen
(Entwurf 4d.2, Theorie 11.10). `FcmProblem(loeser="mehrgitter")` steht. Offen aus Aufgabe 2:
Einrichtzeit und Speicher der Blöcke (Kirsch h 20 p 3: 32 s), Blöcke aus Nachbar-Zellmatrizen,
nur Schnittzellen blocken; Aufgabe 3 damit teilweise vorweggenommen.

### Aufgabe 3: Kleine Schnittzellen und Kondition
- Messen, welche Moden nach dem V-Zyklus die Konvergenz bremsen (Ritz-Werte aus dem CG):
  Aggregation deckt Anteile < 0,25 ab; bleibt die Iterationszahl schnittlagenabhängig, Schwelle
  0,25 → 0,4 messen, ersatzweise Ghost Penalty auf den Schnittzellenflächen (Vorgabe 8.3, Wahl
  konfigurierbar).
- Prüfung: fünf Schnittlagen der Kirsch-Platte (h 10, p 3, verfeinert): Iterationen innerhalb ±20 %.

### Aufgabe 4: Vertragsschicht und Speicher (`api.py`, `fcm/problem.py`)
- `FcmProblem(loeser="mehrgitter")` als Standard, sobald PCG + V-Zyklus den Direktlöser in Zeit
  und Speicher schlägt (gemessen an Kirsch h 10 p 3 verfeinert: Direktlöser 51 s, 379 k FHG); sonst
  bleibt „direkt“. `estimate` schätzt Zellmatrizen (alle Ebenen ≈ 1,3 × fein), Grobgitter und
  Vektoren; Protokoll `iterationen`, `mehrgitter` (Ebenen, λ_max, Glättergrad).
- Prüfung: `test_vertrag_fcm`, Kernsuite, Abnahmen unverändert; `backend='cpu'` liefert dieselben
  Spannungen wie der Direktlöser auf 10⁻⁶.

### Aufgabe 5: GPU
- V-Zyklus mit `OperatorGpu` je Ebene, Chebyshev auf cupy, Grobgitter auf der CPU (Transfer p = 1
  klein); `backend='gpu'` in der Vertragsschicht; Speicherabschätzung gegen `mem_info`.
- Prüfung: GPU-Lösung = CPU auf 10⁻⁸, Zeiten CPU/GPU je Iteration und gesamt; Kirsch h 5 p 3
  (≈ 1,5 Mio. FHG) als Größenprobe gegen das Speicherbudget der RTX 3070.

### Aufgabe 6: Abschluss
- Theoriehandbuch 11.10 (Schachtelung, Glätter, Messreihen), Entwurf 4d, `docs/Volumenmodul.md`;
  Kernsuite um `test_mehrgitter.test_kern`; zweite Sicht über Teilprojekte 3 und 4; Pull Request 2
  (Stufe 2) mit grüner CI.
