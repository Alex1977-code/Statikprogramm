# Statik3D – Theoriehandbuch

Dieses Handbuch beschreibt die Rechenverfahren, Annahmen und Normbezüge von
Statik3D. Es dient als Grundlage für die Prüfung der Ergebnisse und für die
Dokumentation in statischen Berichten.

## 1 Grundlagen

### 1.1 Einheiten und Vorzeichen

* Einheiten durchgängig SI: Länge m, Kraft N, Spannung Pa, Dichte kg/m³,
  Temperatur K. Der Bericht rechnet zur Anzeige in kN, kNm, MPa, mm um; in
  der Oberfläche sind Einheiten und Nachkommastellen je Modell einstellbar
  (*Ansicht → Einheiten*, Modul `statik3d/einheiten.py`), gerechnet wird
  davon unberührt in SI.
* Freiheitsgrade je Knoten: ux, uy, uz, rx, ry, rz (Rechtssystem).
* Schnittgrößen der Stäbe nach DIN 1080: Am positiven Schnittufer wirken
  positive Schnittgrößen in Richtung der positiven lokalen Achsen.
  N > 0 ist Zug, My > 0 erzeugt Zug an der +z-Seite des Querschnitts
  (bei horizontalen Stäben die Oberseite). Bei Einfeldträgern unter
  Gleichlast ist My daher negativ (Zug unten).
* Lokale Stabachsen: x von Knoten 1 nach Knoten 2; y und z Hauptachsen.
  Die lokale z-Achse liegt in der Ebene aus Stabachse und globaler z-Achse
  (bei vertikalen Stäben: globale x-Achse), optional um den Winkel `roll`
  verdreht. Iy ist das Trägheitsmoment um die lokale y-Achse (starke Achse
  bei I-Profilen mit Steg in z-Richtung).

### 1.2 Finite Elemente

Welche Elementtypen es gibt, steht an **einer** Stelle: im Verzeichnis
`statik3d/elemente.py` (Familie, Knotenzahl, Freiheitsgrade je Knoten,
VTK-Zelle für die Ansicht, Klartext für den Bericht). Assemblierung, Löser,
Ansicht, Vernetzer, Import, Export und Bericht fragen dieses Verzeichnis;
nirgends sonst steht eine Aufzählung von Elementnamen.

**Stäbe** (2 Knoten, 6 Freiheitsgrade je Knoten)

| Element | Formulierung | FHG |
|---|---|---|
| beam | Räumlicher Balken, Timoshenko-Schubverformung wenn Schubflächen > 0, Saint-Venant-Torsion, Momentengelenke durch statische Kondensation; mit **Exzentrizität** (starrer Versatz der Stabenden) und **Wölbkrafttorsion** (7. Freiheitsgrad je Knoten) | 12 (14) |
| truss | Fachwerkstab, nur Normalkraft; mit `nur` = zug/druck ein **Ausfallstab** | 6 (Translation) |
| seil | Seil: nach Theorie I. Ordnung ein Zugstab mit Ausfall, nach Theorie III. Ordnung die **elastische Kettenlinie** | 6 (Translation) |

**Schalen** (6 Freiheitsgrade je Knoten, Drillsteifigkeit künstlich stabilisiert)

| Element | Formulierung | FHG |
|---|---|---|
| shell3 | Dünn: CST-Scheibe + DKT-Platte (Batoz/Bathe/Ho). Dick (Eigenschaft „mindlin“): MITC3 (Lee/Bathe) | 18 |
| shell4 | Bilineare Scheibe mit inkompatiblen Moden + **MITC4**-Platte (Bathe/Dvorkin, Reissner-Mindlin, schublockierungsfrei). Eigenschaft „dkt“ schaltet auf die alte Zerlegung in zwei DKT-Dreiecke zurück | 24 |
| shell6 | Quadratisches Dreieck, Reissner-Mindlin, Querschub selektiv reduziert | 36 |
| shell8 | Serendipity-Viereck, Reissner-Mindlin, Biegung 3×3, Querschub 2×2 | 48 |

Jede Schale kann **geschichtet** sein: die Eigenschaft trägt statt einer Dicke
eine Liste von Lagen (Dicke, E, ν oder orthotrop E₁, E₂, ν₁₂, G₁₂, G₁₃, G₂₃,
Winkel). Daraus folgen nach der klassischen Laminattheorie die Steifigkeiten
A (Membran), B (Kopplung), D (Biegung) und Ds (Querschub, Schubkorrektur 5/6);
ein unsymmetrischer Aufbau koppelt Dehnung und Krümmung (B ≠ 0).

**Volumen** (3 Verschiebungsfreiheitsgrade je Knoten)

| Element | Formulierung | Integration |
|---|---|---|
| tet4 | Linearer Tetraeder (konstante Dehnung) | 1 Punkt (exakt) |
| tet10 | Quadratischer Tetraeder | 4 Punkte |
| hex8 | Trilinearer Hexaeder mit inkompatiblen Moden (Wilson/Taylor) | 2×2×2 |
| hex20 | Quadratischer Hexaeder (Serendipity, 20 Knoten) | 3×3×3 |
| pent6 | Keil (Prisma), linear | 3 × 2 |
| pent15 | Keil, quadratisch | 6 × 3 |
| pyr5 | Pyramide (rationale Formfunktionen nach Bedrosian) | kollabierte 2×2×2-Regel |

Keil und Pyramide sind die Übergangselemente zwischen Hexaeder- und
Tetraedernetzen: eine Hexaederschicht endet über eine Pyramidenlage im
Tetraedernetz, ohne dass Knoten hängen.

**Ein Dehnungsoperator für Steifigkeit, Spannung und Plastizität (22.09.2026).**
Jeder Volumentyp liefert seine Kinematik an **einer** Stelle:
`elements.solid.dehnungsoperator(model, typ, elemente)` gibt je Integrationspunkt die
Verzerrungsmatrix B (bzw. die Formfunktionsableitungen), das Gewicht w·|det J| und —
beim `hex8` — die inneren Moden; `auswerteoperator` dasselbe an beliebigen Punkten
(den Auswertepunkten). Daraus rechnen die Steifigkeit (`steifigkeit_aus_operator`,
gestapelt für hex8, tet10, hex20, pent6, pent15, pyr5), die Spannungsrückrechnung
(`spannungen_stapel`, samt Elementmittel `solid_mittel`) und die Plastizität
(`plastizitaet._stapel`). Bis dahin stellte jeder Leser sein B selbst auf — dieselben
Zahlen, aber drei Wege; sobald ein Element eine andere Kinematik bekommt (etwa die
projizierte Volumendehnung des hex8, § 4.4), hätten Steifigkeit und Fließen still mit
zwei verschiedenen gerechnet. Geprüft: Steifigkeit aus dem Operator gegen die
Einzelfassung jedes Typs auf ≤ 6,3·10⁻¹⁶, gestapelte Assemblierung gegen
`element_matrix` ebenso, ein umgestülptes Element nennt auch im Stapel seine Nummer
(`tests/test_elemente_volumen.py`, `t_operator`). Der `tet4` bleibt beim Einzelweg
(24,2 µs je Element; mit Knotendilatation rechnet er seinen deviatorischen Anteil
über `element_matrix`).

**Übergang linear/quadratisch (22.09.2026).** Teilt ein quadratisches Element
(tet10, hex20, pent15) eine Seite mit einem linearen (tet4, hex8, pent6) — dieselben
Eckknoten, verbunden, keine Fuge —, kennt das lineare Element dort keinen
Mittelknoten. Läuft die Verschiebung des quadratischen Elements an der Seite frei,
klafft die Grenze, und ein lineares Verschiebungsfeld ist kein Gleichgewicht mehr:
der Mittelknoten trägt aus der konstanten Spannung die Kraft A/3·t (die Ecken des
6-Knoten-Dreiecks nichts), und niemand hält dagegen. Gemessen am Würfel aus tet10
und tet4 mit gestörtem Innenknoten: Patch-Test um 2,5·10⁻¹ daneben (relativ zur größten
Verschiebung). Die Seitenmitten
solcher Seiten werden darum an ihre Kante gebunden, u_m = (u_a + u_b)/2
(`assemble.mittelknoten_bindungen`) — **exakt**, nicht im Strafverfahren (mit der
Strafe 10⁴ blieben 6·10⁻⁶): der Dehnungsoperator schlägt den Gradienten des
Mittelknotens je zur Hälfte auf die beiden Ecken, sodass Steifigkeit, Spannung und
Plastizität dieselbe gebundene Kinematik sehen; Lasten und Massen am Mittelknoten
gehen ebenso auf die Ecken, und seine Verschiebung wird nach dem Lösen aus der
Kante eingetragen. Patch-Test über die Grenze: 2,5·10⁻¹⁶, im Löser Spannung
3,5·10⁻¹⁵ (`tests/test_elemente_volumen.py`, `t_uebergang_linear_quadratisch`).
An einer **Kontaktfuge** wird nichts gebunden — dort hat jede Seite eigene Knoten.

**Gekrümmte Elemente (22.09.2026).** Liegen die Seitenmitten eines tet10 auf der
wahren Geometrie (Bohrung, Ausrundung), kann die Jacobi-Determinante innerhalb des
Elements das Vorzeichen wechseln, zuerst an Ecken und Kanten — an den Gaußpunkten
kann sie dabei noch positiv sein. `elements.solid.jacobi_pruefung(model)` prüft
Integrationspunkte, Ecken und (tet10) Kantenmitten stapelweise und nennt jedes
Element mit det J ≤ 0 mit Nummer; die Netzabnahme ruft sie vor dem Rechnen
(`t_jacobi_pruefung`). Die Assemblierung selbst bricht bei det J ≤ 0 an einem
Integrationspunkt mit Elementnummer ab, auch im Stapel.

Den Patch-Test besteht ein gekrümmter tet10 nur **schwach** (gemessen 23.09.2026,
`t_tet10_patch`): Ein lineares Feld stellt die isoparametrische Abbildung zwar exakt
dar, aber das Gleichgewicht der Innenknoten braucht ∫ ∂N/∂x dV exakt. Der Integrand
∂N/∂ξ · Kofaktor(J) hat beim tet10 den Grad 3, die 4-Punkt-Regel ist nur bis Grad 2
exakt. Mit inneren Kanten, die um 8 % der Kantenlänge gekrümmt sind, liegt u 1,7·10⁻⁴
und die Spannung 1,7·10⁻³ daneben; mit einer Regel vom Grad 3 ist das Ergebnis exakt
(5·10⁻¹⁶). Die 4-Punkt-Regel bleibt, weil sie an der Lamé-Hohlkugel mit Mitten auf der
Kugel das Mittel der Randspannung nur um höchstens 0,06 N/mm² verschiebt (−16,29 gegen
−16,23 bei 915 FHG, −7,28 gegen −7,26 bei 5 859 FHG).

**Ebene Elemente** (3 Verschiebungsfreiheitsgrade je Knoten, Steifigkeit nur in
der Elementebene) als ebene3, ebene4, ebene6, ebene8 mit dem Zustand
**Scheibe** (ebener Spannungszustand, Dicke t), **ebener Dehnungszustand**
(Scheibe je Tiefe t) oder **rotationssymmetrisch** (die Elementebene ist die
x-z-Ebene, r = x, Drehachse = z, Integration über 2π·r). Das Viereck trägt in
den ebenen Zuständen inkompatible Moden; auf der Drehachse (r → 0) wird die
Umfangsdehnung durch ∂u_r/∂r ersetzt.

**Punkt- und Verbindungselemente**

| Element / Objekt | Wirkung |
|---|---|
| feder | Zwei Knoten, sechs Steifigkeiten in lokalen Achsen (Weg und Verdrehung); mit `nur` ein Ausfallelement |
| grenzschicht6/8 | Grenzschicht **ohne Dicke** zwischen zwei Flächen: Normal- und Schubsteifigkeit je Fläche (Klebeschicht, weiche Fuge) |
| Punktmasse | Masse und Drehträgheiten an einem Knoten (Eigenfrequenzen, Eigengewicht m·g) |
| Dämpfer | Viskoser Dämpfer zwischen zwei Knoten oder gegen den Boden (Dämpfungsmatrix) |
| Starrer Körper | RBE2 (die Slaves folgen dem Master starr) und RBE3 (der Master ist der gewichtete Mittelpunkt: eine Last verteilt sich, ohne zu versteifen) - als Zwangsbedingung im Strafverfahren |

Die Elemente sind gegen analytische Lösungen und Patch-Tests verifiziert:
`tests/test_verification.py` (27 Benchmarks), dazu je Familie
`tests/test_elemente_volumen.py`, `tests/test_elemente_schalen.py`,
`tests/test_elemente_ebene.py`, `tests/test_elemente_stab.py` und - für das
Zusammenspiel mit Modell, Löser, Netz, Bericht und Schnittstellen -
`tests/test_elemente.py`.

Der Tet10-Kragträger der Verifikation (2,0 × 0,2 × 0,2 m, 8 × 2 × 2 Zellen zu
je fünf Tetraedern, 393 Knoten, ν = 0) trifft die Timoshenko-Durchbiegung auf
−0,11 % (gemessen 23.09.2026) und wird mit 1 % geprüft. Bis zum 23.09.2026
erzeugte die Prüfung ihr tet4-Ausgangsnetz mit einer eigenen Kopie der
Quaderzerlegung ohne den Schachbrettwechsel aus `mesher.grid_box`: 384 statt
144 freie Dreiecke, also innere Risse, und +3,85 % Abweichung, die die
damalige Toleranz von 5 % durchließ. Jetzt nimmt sie `mesher.grid_box` und
prüft zusätzlich, dass nur die Randdreiecke frei sind.

### 1.2a Ausfallstäbe, Seile und der siebte Freiheitsgrad

**Nur Zug oder nur Druck.** Ein Fachwerkstab, ein Seil oder eine Feder mit
`nur` = „zug“ bzw. „druck“ trägt nur in einer Richtung. Gerechnet wird mit
einer **Aktivmengen-Iteration** (`solver.solve_with_ausfall`): erst tragen
alle, dann wird herausgenommen, wer die falsche Kraft trägt - seine
Steifigkeit wird als Zusatzmatrix wieder abgezogen, das System selbst bleibt
stehen -, und es wird neu gelöst, bis sich die Menge nicht mehr ändert. Wer
herausgenommen wurde, darf im nächsten Schritt wieder hinein. Kontakt läuft
innen weiter mit.

**Seile.** Nach Theorie III. Ordnung ist ein Seil die **elastische
Kettenlinie** (Peyrot/Goulois, Jayaraman/Knudson): aus der ungedehnten Länge
L₀, der Dehnsteifigkeit EA und der Streckenlast w folgen der Horizontalzug H,
der Durchhang und die Tangente ∂f/∂u für das Newton-Verfahren. Das Eigengewicht
steckt in der Kettenlinie selbst und wird nicht noch einmal als Knotenlast
angesetzt. Ist die Sehne länger als L₀, wird das Seil zum Zugstab EA/L₀; ist
sie kürzer, wird es kraftlos.

**Wölbkrafttorsion.** Ein Balken mit dem Haken `woelb` und einem Querschnitt
mit Wölbwiderstand I_w > 0 bekommt an jedem seiner Knoten einen **siebten
Freiheitsgrad**: die Verwölbung ω = θ'. Diese Freiheitsgrade stehen hinter
den 6·n Knotenfreiheitsgraden (`Model.woelb_index`). Die lokale Steifigkeit
ist 14×14: die zwölf des Balkens, in denen der Saint-Venant-Anteil durch die
gemischte Torsion ersetzt ist

  K_t = G·I_t/(30L)·[36, 3L, −36, 3L; …] + E·I_w/L³·[12, 6L, −12, 6L; …]

(Hermite-Ansatz für θ). Ein Lager mit dem Haken „Wölbeinspannung“ sperrt ω an
seinem Knoten (Stirnplatte, Einspannung); ohne ihn ist die Verwölbung frei
(Gabellagerung). Im Ergebnis stehen die **Bimomente** B = −E·I_w·θ'' an beiden
Stabenden und die Verwölbung je Knoten. Ohne I_w rechnet der Stab wie bisher
mit zwölf Freiheitsgraden - ein siebter ohne eigene Steifigkeit würde die
Verwölbung nur künstlich stetig machen.

**Exzentrizität.** Liegt die Stabachse neben dem Knoten (Versatz r in lokalen
Achsen), gilt u_Stab = A·u_Knoten mit u_Ende = u_Knoten + θ×r; Steifigkeit und
Lasten werden mit Aᵀ(…)A auf die Knoten umgerechnet. Eine Normalkraft N
erzeugt dann im Stab das Moment N·e, während der Knoten nur N sieht.

### 1.3 Gleichungslöser

Die globale Steifigkeitsmatrix wird als dünnbesetzte Matrix assembliert und
einmal faktorisiert. Alle Lastfälle werden mit derselben Faktorisierung
gelöst.

Der Löser wird in dieser Reihenfolge gesucht: **Intel MKL PARDISO**
(`pypardiso`), **CHOLMOD** (`scikit-sparse`), **SuperLU** (in scipy immer
vorhanden). Das Windows-Programm bringt MKL mit, so dass PARDISO greift; der
Selbsttest beim Bau bricht ab, wenn es fehlt.

Der Unterschied ist keine Feinheit. PARDISO rechnet über OpenMP auf mehreren
Threads, SuperLU ist **streng einkernig** — daran ändert keine Einstellung
etwas, es ist eine Eigenschaft des Lösers. An einem Würfel aus
Sechsflächnern mit 34.914 Freiheitsgraden gemessen:

| Löser | Faktorisieren | Speicher |
|---|---|---|
| SuperLU (1 Kern) | 12,25 s | +0,49 GB |
| PARDISO (4 Threads) | **1,38 s** | **+0,39 GB** |

Also 8,9-mal schneller bei 20 % weniger Speicher, mit derselben Lösung.
Die Threadzahl ist `cpu_count() − 1`: der eine Kern bleibt der Oberfläche,
damit sich das Fenster während der Faktorisierung noch bedienen lässt. Wer
`MKL_NUM_THREADS` oder `OMP_NUM_THREADS` selbst setzt, behält den Vorrang.

**MUMPS** (CeCILL-C) ist seit 13.09.2026 der dritte direkte Löser unter
Windows — ein eigener Bau von MUMPS 5.8.2 mit gfortran, OpenMP, OpenBLAS
und METIS, angebunden über `ctypes` (Paket `mumps`, Bau und Lizenzlage in
`docs/MUMPS_Windows_Bauanleitung.md`). Er steckt nicht in der exe: das
Programm lädt das Rad beim Start aus dem Release `werkzeuge` nach
(Benutzerhandbuch, „Vernetzer und Nachbesserer nachladen“). Zwei Befunde aus dem
Bau, gemessen am selben Würfel (34.914 Freiheitsgrade, 2,59 Millionen
Einträge, Ryzen 9 5950X mit 16 Kernen / 32 Threads):

* Das fertige conda-forge-Binary (flang, ohne OpenMP in MUMPS, Umordnung
  QAMD) braucht 3,4 s und wird mit keiner Threadzahl schneller. Der eigene
  Bau mit METIS senkt die Flop der Faktorisierung von 7,6·10¹⁰ auf
  2,5·10¹⁰ und den Faktorspeicher von 427 auf 249 MB.
* OpenBLAS' `dgemmt` (Schalter `-DGEMMT_AVAILABLE`) macht den
  symmetrischen Zweig mit jedem Thread langsamer (16 Threads: 4,9 s statt
  1,6 s); der Bau lässt den Schalter weg. Über acht Threads hinaus
  verliert MUMPS ebenfalls — am Würfel 0,86–1,09 s (8) gegen 1,58 s (16)
  und 3,3 s (31), mit 201.720 Freiheitsgraden 8,1 s (8) gegen 9,8 s (16)
  und 22,1 s (1) — darum kappt das Paket die Threadzahl auf acht und nie
  mehr als physische Kerne (`MUMPS_NUM_THREADS` übersteuert).
* Die Threadzahl wird **nur über OpenMP** gesetzt (`omp_set_num_threads`),
  nie über `openblas_set_num_threads()`. OpenBLAS 0.3.34 (OpenMP-Fassung)
  richtet sich sonst nicht mehr nach `omp_in_parallel()`
  (`blas_is_num_threads_set_explicitly` in `common_thread.h`) und öffnet
  aus MUMPS' Baumthreads (ICNTL(48), `dmumps_fac_l0_omp`) heraus
  verschachtelte Regionen, deren Aufrufer sich in `exec_blas` um die
  `MAX_PARALLEL_NUMBER` Puffer drehen: mit 8 Threads und SYM=0 standen fünf
  Baumthreads in derselben Spin-Schleife, ein sechster in einer
  verschachtelten libgomp-Region — 1 959 CPU-Sekunden ohne Fortschritt
  (gdb-Rückverfolgung im Bauverzeichnis, 13.09.2026). Über OpenMP gesteuert
  rechnet OpenBLAS in den Baumthreads einkernig und oben im Baum mit allen
  Threads, so wie MUMPS es vorsieht. Mit einkerniger BLAS wäre MUMPS bei
  3D-Modellen nicht schneller als mit einem Thread (gemessen 1,26 s bei 1
  und 1,2–1,4 s bei 8 Threads): die Arbeit steckt in den großen Fronten
  oben im Baum, und die rechnet die BLAS.

| Löser (13.09.2026) | Faktorisieren | Faktorspeicher |
|---|---|---|
| SuperLU (1 Kern) | 8,25 s | +0,53 GB |
| MUMPS, symmetrisch (SYM=2), 1 Thread | 1,26 s | 249 MB |
| MUMPS, symmetrisch (SYM=2), 8 Threads | 0,86–1,09 s | 249 MB |
| MUMPS, unsymmetrisch (SYM=0), 8 Threads | 0,64–0,73 s | 534 MB |
| PARDISO, 31 Threads (MKL nimmt 16) | 0,45 s | +0,49 GB |

Am Würfel mit 40³ Sechsflächnern (201.720 Freiheitsgrade, 8,0·10¹¹ Flop
symmetrisch, 2,6 GB Faktoren): MUMPS symmetrisch 22,1 s mit einem, 8,1 s
mit acht und 9,8 s mit sechzehn Threads; unsymmetrisch 11,6 s mit
sechzehn Threads bei 1,6·10¹² Flop und 5,7 GB.

Symmetrische Systeme übergibt `LinearSolver._mumps` als unteres Dreieck
(SYM=2, LDLᵀ mit Pivotisierung); ob K symmetrisch ist, wird an
‖K − Kᵀ‖ gemessen (Schranke 10⁻¹² · max|K|), nicht angenommen. Reicht die
Arbeitsspeicher-Schätzung der Analyse wegen der Pivotisierung nicht
(INFOG(1) = −8/−9), wird ICNTL(14) stufenweise auf 50, 100 und 200 %
angehoben und nur die Faktorisierung wiederholt. `freigeben()` ruft
JOB = −2; gemessen in `tests/test_loeser.py` wie bei PARDISO (25
Faktorisierungen ohne Bezug wachsen nicht).

**Der Speicher der Faktorisierung wird zurückgegeben.** MKL hält die
Faktorisierung außerhalb von Python; `pypardiso` gibt sie nur auf
ausdrücklichen Aufruf frei, nie beim Einsammeln des Objekts. Die
Kontakt-Iteration faktorisiert in jedem Schritt neu (Steifigkeit mit den
gerade geschlossenen Kontakten), und am Drehlager (1 028 724 Freiheitsgrade,
44,3 Millionen Einträge, 7 GB je Faktorisierung in 10 bis 13 s auf 31
Threads) wuchs der Prozess je Schritt um diese 7 GB: nach 33 Schritten
113 GB, PARDISO brach mit Fehler −2 (kein Speicher) ab, und der Rückfall auf
SuperLU scheiterte am Speicher (11.09.2026). `LinearSolver.freigeben()` ruft
`free_memory(everything=True)`; der Kontaktschritt ruft es sofort nach dem
Lösen, das Einsammeln des Objekts ebenfalls. Gemessen (`tests/test_loeser.py`,
7-Punkt-Laplace auf 40³ = 64 000 Freiheitsgraden, 255 MB je
Faktorisierung): 25 Faktorisierungen wachsen um 3 MB statt um 6107 MB.

Fällt der Löser doch auf SuperLU zurück, wird **symmetrisch geordnet**
(`MMD_AT_PLUS_A` statt `COLAMD`). Die Steifigkeitsmatrix ist strukturell
symmetrisch, COLAMD ordnet für unsymmetrisches LU und füllt darum mehr auf:
am Würfel mit 19.494 Freiheitsgraden 22,5 statt 25,3 Millionen Einträge in
L+U bei 3,2 statt 4,9 Sekunden.

Was in der Statuszeile steht, ist seit diesem Stand eindeutig getrennt: der
**Prozesspool** („lokal, 31 von 32 Kernen“) gilt für Elementschleifen,
Aufträge und die Vernetzung, der **Gleichungslöser** meldet sich mit Namen
und Threadzahl gesondert. **Der Pool bemisst sich seit dem 27.09.2026 nach
dem freien Speicher** (`parallel.arbeiter_nach_speicher`): höchstens so
viele Arbeiter, wie in den halben freien Commit-Speicher passen, wenn
jeder so viel braucht wie der Hauptprozess beim Start des Pools - er hält
das Modell, und genau das kopiert jeder Arbeiter. Gemessen am Drehlager
(655 000 tet4): je Arbeiter 1,4 GB Arbeitssatz und 2,9 GB Commit, der
Hauptprozess 24 GB Commit in der Faktorisierung; mit der Vorgabe 31
Arbeiter erschöpften 90 GB Pool plus Hauptprozess das Commit-Limit von
166 GB (128 GB RAM plus 38 GB Auslagerung) - PARDISO −2 „kein Speicher“,
davor ein Absturz in der Faktorisierung. Mit 12 Arbeitern blieben 69 GB
frei. Ein kleines Modell (Hauptprozess 0,3 GB) bleibt bei der Vorgabe; die
Begrenzung steht als Hinweis „[parallel] Pool: 12 statt 31 Arbeiter …“ im
Fehlerstrom (`tests/test_pool_speicher`). Vorher stand dort nur die Zahl des Prozesspools,
und die las sich, als rechne auch der Löser so. Nach dem Lösen wird das Residuum
|K u − F| / |F| geprüft; numerisch singuläre Systeme (fehlende Lagerung,
freie Bauteile) werden als Fehler gemeldet statt unbemerkt falsche Ergebnisse
zu liefern. Bevor ein Residuum über 1e-6 als singulär gilt, wird
**nachiteriert** (16.09.2026): x += K⁻¹(F − K·x) mit der vorhandenen
Faktorisierung, bis zu dreimal, solange das Residuum fällt. Straffedern
(1e4-fach die größte Hauptdiagonale, für starre Kopplungen und Kontakt)
kosten die Faktorisierung Stellen; am Drehlager brach LF1 mit Residuum
1,3e-6 ab, obwohl derselbe Aufbau kurz zuvor konvergiert war. Ein wirklich
singuläres System bleibt über der Schranke (`tests/test_nachiteration.py`:
ein Löser mit 3e-6 Fehler je Schritt kommt nach einer Nachiteration unter
1e-6, einer mit 50 % Fehler nicht).

**Spiel geometrisch** (17.09.2026, `statik3d/spiel.py`): ein Zylinder wird
aus den Kreisbögen seiner Flächen erkannt (Kreis durch die drei Punkte jedes
Bogens; gleicher Radius auf 1e-6, Mittelpunkte auf einer Achse, an mindestens
zwei Achslagen). Weil RFEM Stift und Bohrung über dieselben Knoten und Linien
führt, werden geteilte Flächen, Linien und Knoten zuerst für das gewählte
Volumen kopiert (`spiel.trennen`); dann rücken die Knoten auf dem
Schaftradius und die Punkte der Bögen radial um s/2 zur Achse
(`spiel.zylinder_spiel`), ebene Flächen um s längs ihrer Innennormalen
(`spiel.flaechen_spiel`). Das Netz des Volumens wird gelöscht; die
Oberfläche vernetzt neu und führt die Fugen wieder aus. Nachweis
`tests/test_spiel.py`: Stift r = 20 mm in einer Platte, deren Loch seine
Bögen benutzt — nach 0,1 mm Spiel liegen Knoten, Bögen und das neue Netz auf
r = 19,95 mm, das Loch behält 20 mm und seine Linien; die gemeinsame
Trennfläche zweier Blöcke bekommt eine Kopie 0,5 mm höher.

**Passung** (17.09.2026): drei Angaben je Kontaktbedingung, die in den
Aufbau der Bedingungen eingehen (`contact.ContactSystem._bedingung`). Das
**Spiel** s kommt zum bereinigten Anfangsspalt jeder Bedingung dazu
(g₀ → g₀ + s; bei einem Verbund entfällt es) - bei einer Bohrung das radiale
Spiel, so dass ein Stift erst nach s auf der belasteten Seite anliegt. Die
**Lochleibungsgrenze** p_L wird über die Einflussfläche A_i des Slave-Knotens
(Facettenfläche zu gleichen Teilen auf ihre Knoten, `fugen._passungsdaten`)
zur Grenzkraft F_i = p_L·A_i der Bedingung: übersteigt die Druckkraft sie,
fließt die Bedingung mit konstanter Kraft F_i (das vorhandene plastische
Glied `limit`/`yielding`), die Nachbarn tragen den Rest; entlastet sie, wird
sie wieder elastisch. Die **Randabminderung** nimmt den Knoten am Rand der
gepaarten Kontaktseite (Kanten, die nur zu einer gepaarten Facette gehören;
weitere Reihen über die Facettenkanten) das Haften und die Reibung: sie
gleiten reibungsfrei, die Singularität am Ende einer haftenden Fuge fällt
weg. Nachweis `tests/test_passung.py`: Spiel 0,5 mm setzt den Block 0,5 mm
tiefer bei gleichem Gleichgewicht; eine Grenze bei 70 % der Spitzenkraft
kappt jede Knotenkraft dort und lässt die Summe gleich der Last; mit einer
Randreihe haften nur die neun inneren der 25 Knoten, der Schub geht über sie.
Die zweite Reihe wird an einem Netz aus 5 × 5 Knoten (32 Dreiecke) geprüft:
eine Reihe sind die 16 Randknoten, zwei Reihen nehmen den Ring der acht
Nachbarn dazu, der Mittelknoten bleibt frei. An einem kleineren Netz ließe
sich die zweite Reihe nicht von „alle Knoten“ unterscheiden: bei 3 × 3 und
4 × 4 Knoten ist sie schon das ganze Innere.

**Halt für Teile ohne geschlossene Bedingung** (17.09.2026): verliert ein
Teil in der Kontakt-Iteration alle Bedingungen, ist das Gleichungssystem
des nächsten Schritts wirklich singulär - am Drehlager pendelte die Zahl der
aktiven Bedingungen 18 Schritte lang um 13 000, bis in Schritt 27 Passstifte
ohne Halt waren (Residuum 1,1e-3), obwohl Verformung und Spannungen des
Schritts davor unauffällig waren. Ein Stift in einer Bohrung berührt sie
immer irgendwo; dass alle seine Bedingungen offen sind, ist die
Linearisierung des Schritts. Scheitert die Lösung, hält
`solver._freie_teile_halten` je Teil mindestens drei Bedingungen (die mit
dem kleinsten Spalt) geschlossen, zählt das als Zustandswechsel (nach acht
Wechseln friert die Bedingung ohnehin geschlossen ein) und löst denselben
Schritt noch einmal; das Protokoll nennt jedes gehaltene Teil mit Spalt. Eine
Bedingung zählt dabei zum Teil ihres Slave-Knotens und zu dem ihrer
Master-Knoten - ein Stift, auf den nur die Bohrung drückt, hätte sonst keine.
Der Halt gilt dem Schritt, nicht dem Ergebnis: tragen die gehaltenen
Bedingungen am Ende Zug (kn·g über einem Tausendstel der Lastgröße), hebt
das Teil wirklich ab, und die Rechnung bricht ab - mit der gehaltenen Lage
als Teilergebnis und dem Zeiger „hebt ab und hängt an n gehaltenen
Kontaktpunkten unter F kN Zug“. Nachweis `tests/test_kontakthalt.py`: der
nach oben gezogene Block, der ohne den Halt in Schritt 2 singulär abbricht,
konvergiert mit 13 gehaltenen Punkten und wird dann als abhebend gemeldet
(90 kN Zug an den gehaltenen Punkten); `tests/test_solver_ext.py` erwartet
für das vollständige Abheben weiterhin die Fehlermeldung.

**Was eine Faktorisierung gekostet hat.** `Results.info` trägt neben `ndof`
und `nfree` drei Zahlen, die die adaptive Vernetzung braucht, um zu sagen, was
eine Netzrunde an **Löserzeit** gespart hat (Anforderung der Vernetzersitzung,
20.09.2026):

| Feld | Bedeutung |
|---|---|
| `nnz_matrix` | Nichtnullen der zuletzt faktorisierten Matrix |
| `nnz_faktor` | Nichtnullen der Faktorisierung (PARDISO `iparm(18)`; 0 bei anderen Lösern) |
| `zeit_faktorisierung` | Summe der Faktorisierungszeiten dieses Rechensystems [s] |

Die Elementzahl allein sagt es nicht, weil die Faktorisierung **überlinear**
wächst: am Drehlager mit N^1,45 über den Freiheitsgraden. `nnz_faktor` ist das
Maß dafür, wie viel Auffüllung die Knotennummerierung erzeugt hat — es ist die
Größe, die Speicher und Rechenzeit der Faktorisierung bestimmt, nicht `nnz_matrix`.
Gemessen an einer Tridiagonalmatrix (20.09.2026): n = 200 gibt 964, n = 400 gibt
1960, also linear — für ein Band muss es das sein. Die Zeit wird mit
`perf_counter` gestoppt, nicht mit `time`: dessen Uhr steht unter Windows in
Stufen von 15,6 ms, und eine einzelne Faktorisierung am kleinen System dauert
Millisekunden (ein Probelauf meldete damit 0,000 s für eine Faktorisierung, die
es wirklich gab).

**Weniger Elemente können mehr Matrix bedeuten — die Ersparnis eines
Hexaedernetzes darf nicht aus der Elementzahl gerechnet werden.** Gemessen am
Drehlager, LF1, altes Tetraedernetz gegen das gesweepte (Löser-Sitzung,
21.09.2026):

| | altes Netz | neues Netz | |
|---|---|---|---|
| Volumenelemente | 645 934 | 493 432 | −23,6 % |
| Knoten | 158 728 | 159 130 | +0,3 % |
| aktive Freiheitsgrade `nfree` | 475 935 | 475 214 | **−0,2 %** |
| `nnz_matrix` | 17 686 439 | 21 878 201 | **+23,7 %** |
| `nnz_faktor` | 245 394 449 | 272 011 788 | +10,8 % |
| Faktorisierung | 343,1 s | 663,99 s | **+93,5 %** |

Ein Viertel weniger Elemente, und die Faktorisierung wird fast doppelt so
teuer. Der Grund steht in den Zeilen darüber: die **Zeilenzahl** hängt an den
Knoten, und die bleiben gleich — ein Hexaedernetz spart Elemente, keine
Unbekannten. Was wächst, ist die **Kopplung je Zeile**: der `hex8` verbindet
acht Knoten je Element statt vier, und das bei nur 3,14 Elementen je Knoten
statt 4,10. Die Matrix wird **dichter, nicht größer** — und die Faktorisierung
zahlt für Dichte, nicht für Elementzahl.

Der Gewinn eines Hexaedernetzes liegt also nicht im Löser, sondern in den
Elementschleifen (Aufstellen, Kontaktaufbau, Plastizität, Nachlauf), im
Speicher — und vor allem in der **Genauigkeit** (§ 6a: Kragplatte 68,4 %
gegen 97,6 % der Balkenlösung). Wer ihn aus der Faktorisierung rechnet,
rechnet ihn falsch herum.

`zeit_faktorisierung` summiert über das **Rechensystem**, nicht über den
Lastfall. Für die adaptive Schleife ist das genau richtig, weil sie je Runde
ein frisches System aufbaut; in einer Rechenkette, die mehrere Lastfälle auf
demselben System rechnet, wächst der Wert von Lastfall zu Lastfall weiter.
Die Zeit **eines** Lastfalls steht im Löser-Nachweis (nächster Abschnitt).

#### 1.3-1 Löser-Nachweis je Lastfall (`loeser_nachweis`)

*Neu am 22.09.2026 (Zweig `loeser/loeser-nachweis`). Nur Lesen und
Mitschreiben — das Ergebnis bleibt bitgleich (Nachweis am Ende des
Abschnitts).*

**Warum.** Welcher Löser einen Lastfall wirklich gerechnet hat, mit wie vielen
Threads, wie genau und in welcher Zeit, ließ sich hinterher nicht sagen.
`zeit_faktorisierung` ist die Summe des Systems (siehe oben); die Nachprüfung
der Lösersitzung musste die Faktorisierungszeit je Lastfall aus Differenzen
rechnen (1190,1 − 734,8 = 455,3 s für LF3 am Drehlager). Ein Ausweichen bei
den Faktorisierungen der Kontaktschritte stand nur als Fortschrittszeile im
Protokoll, einmal je System — im Ergebnis stand es nicht.

**Wo gezählt wird.** `_solve_loads` beginnt für jeden Lastfall und jede
direkt gerechnete Kombination ein eigenes Buch (`StaticSystem.nachweis_beginnen`)
und legt es am Ende als `Results.info["loeser_nachweis"]` ab. Gezählt wird
**beim Lösen** (`StaticSystem._geloest`), nicht nur beim Faktorisieren: ein
Lastfall kann eine Faktorisierung benutzen, die vor ihm entstand. Ein lineares
Modell faktorisiert beim Aufstellen des Systems, also vor jedem Lastfall, und
die behaltene Kontaktfaktorisierung (`_kontakt_loeser`) überlebt den Wechsel
des Lastfalls — eingefrorene Zustände sind darauf gebaut. Ein Nachweis, der
nur Faktorisierungen zählte, bliebe dort leer. Die Faktorisierungen des
Lastfalls zählen getrennt (`StaticSystem._loeser_merken`).

| Schlüssel | Bedeutung |
|---|---|
| `loesungen` | Löser → Zahl der Lösungen dieses Lastfalls, z. B. `{"pardiso": 22}` |
| `loesungen_gescheitert` | Lösungen, die mit einer Ausnahme endeten |
| `ausweichgruende` | Grund (`LinearSolver.ausweichgrund`) → Zahl der Lösungen, die damit gerechnet wurden |
| `threads` | wirksame Threadzahl → Zahl der Lösungen (bei PARDISO, was MKL nach dem Setzen meldet) |
| `mtype` | PARDISO-Matrixtyp → Zahl der Lösungen; heute immer `11` (reell, unsymmetrisch) |
| `faktorisierungen` | Faktorisierungen **dieses** Lastfalls; 0 bei linearen Modellen |
| `zeit_faktorisierung_lastfall` | Faktorisierungszeit dieses Lastfalls [s], als Differenz der Systemsumme |
| `gestoerte_pivots_summe` | angehobene Pivots über die Faktorisierungen dieses Lastfalls; `None`, wenn kein Löser eine Zahl meldet |
| `gestoerte_pivots_max` | höchster Wert unter allen Faktorisierungen, die der Lastfall gemacht **oder benutzt** hat |
| `faktorisierungen_mit_gestoerten_pivots` | wie viele davon mindestens einen angehobenen Pivot hatten |
| `residuum_linear_max` | größtes relatives Residuum ‖K x − b‖/‖b‖ der Lösungen; `None`, wenn keine Lösung geprüft wurde |
| `residuum_gemessen` | Zahl der Lösungen mit gemessenem Residuum |
| `pardiso_eingabe` | iparm-Eingabefelder 1, 2, 8, 10, 11, 13, 21, 24, 25 der zuletzt benutzten PARDISO-Faktorisierung, so wie MKL sie zurückgibt |
| `mkl_cbwr` | `{umgebung, code, zweig}`: `MKL_CBWR` beim ersten Laden von MKL und was MKL selbst meldet; `None`, solange MKL nicht geladen ist |

`solver` und `zeit_faktorisierung` bleiben, wie oben dokumentiert. Ein
abgebrochener Lastfall (Teilergebnis) trägt den Nachweis noch nicht.

**Gestörte Pivots sind iparm(14).** MKL PARDISO hebt einen zu kleinen Pivot
an (Vorgabe iparm(10) = 13, also auf rund 10⁻¹³ der Matrixnorm), statt
abzubrechen, und zählt das in iparm(14). Das steht in der MKL-Dokumentation;
geprüft ist es an einer kleinen Matrix (`tests/test_loeser.py`,
`test_pardiso_zaehlt_gestoerte_pivots`, gemessen 22.09.2026 mit dem
`mkl_rt.3.dll` der Programmumgebung): Dirichlet-Laplace 6×6 gibt 0; mit einem
entkoppelten Block [[1, 1], [1, 1]], dessen Pivot nach einem
Eliminationsschritt exakt 0 ist, gibt es 1; mit drei solchen Blöcken 3.
Gelesen wird direkt nach `ps.factorize`, vor jedem Lösen — das schreibt iparm
neu. `LinearSolver` führt dazu `mtype`, `gestoerte_pivots` und
`pardiso_kennzahlen` (`_pardiso_kennzahlen`: iparm(14), iparm(18) als `nnz`,
iparm(15)–(17) als Speicher in KB **laut Doku, nicht nachgemessen**, und die
Eingabefelder). Die anderen Löser melden keine Zahl: dort steht `None`, nicht
0 — 0 hieße „keiner angehoben“.

**MKL_CBWR wird beim ersten Laden festgehalten.** MKL liest die Variable nur
beim Laden. Gemessen 22.09.2026: mit `MKL_CBWR=AUTO` gestartet, danach im
Prozess auf `COMPATIBLE` gesetzt, meldet `MKL_CBWR_Get` weiter 2 (AUTO). Der
Wert beim Faktorisieren wäre also nicht der wirksame. Festgehalten werden die
Umgebung beim ersten Laden durch Statik3D und der Code, den MKL selbst meldet
(`MKL_CBWR_Get(MKL_CBWR_BRANCH = 1)`) — aber nur, wenn das geladene `mkl_rt`
die Funktion hat, sonst „unbekannt“. Die Namen der Codes stammen aus
`mkl_cbwr.h` (der Header liegt der Programmumgebung nicht bei; gelesen in der
Kopie in Intels Repository `intel/mklnn`, `src/mkl_cat.h`). Gemessen passt
das: ohne Variable 1 (BRANCH_OFF), `AUTO` 2, `COMPATIBLE` 3.

**`AUTO` ist seit dem 23.09.2026 die Vorgabe** (Entscheidung des Anwenders).
`os.environ.setdefault("MKL_CBWR", "AUTO")` steht an drei Stellen, die alle
vor dem ersten Laden von MKL liegen: ganz oben in `run_gui.py` (Start der
Oberfläche und der exe), beim Import des Pakets (`statik3d/__init__.py`, das
auch jeder Kettenprozess zuerst lädt) und in `solver.mkl_threads`. Ein
gesetzter Wert hat Vorrang. Belegt in `tests/test_loeser.py`: ohne Variable
meldet MKL im eigenen Prozess Code 2, mit `COMPATIBLE` Code 3
(`test_mkl_cbwr_auto_ist_vorgabe`); in zwei Rechenketten meldet jeder der fünf
Lastfälle der Halle Code 2 (`test_mkl_cbwr_in_kettenprozessen`). Gegen den
Stand davor gefahren, scheitern beide mit Code 1. Der Selbsttest der exe
schreibt `MKL_CBWR` ins Protokoll und endet mit Fehler, wenn MKL nicht mit
`AUTO` rechnet, obwohl nichts anderes vorgegeben ist.

**Das Residuum gehört zur Lösung.** `LinearSolver.solve` setzt `residuum` bei
jedem Aufruf auf nan und erst nach der Prüfung auf den gemessenen Wert. Ohne
Prüfung (keine verlangt, mehrere rechte Seiten, b = 0) bliebe sonst die Zahl
der vorigen Lösung stehen und würde diesem Lastfall zugeschrieben. `residuum`
liest nur der Nachweis (und Tests); am Rechenweg hängt es nicht.

**Am Block mit Reibung gemessen** (`test_loeser_nachweis_je_lastfall`, zwei
Lastfälle auf einem System, ein Thread, 22.09.2026): LF1 21 Lösungen und 7
Faktorisierungen, LF2 22 Lösungen und 16 Faktorisierungen — je Kontaktschritt
genau eine Lösung, und die Faktorisierungen gleich `contact_factorisations`.
Die Faktorisierungszeit von LF2 ist genau `zeit_faktorisierung(LF2) −
zeit_faktorisierung(LF1)`. Das größte Residuum lag bei 3,3·10⁻¹⁵ (LF1) und
2,9·10⁻¹³ (LF2), gestörte Pivots 0.

**Bitgleich.** Gerechnet mit Stand 54b6f9a und mit dem neuen Stand, je ein
Thread (`OMP_NUM_THREADS=MKL_NUM_THREADS=1`), an vier Modellen: Block mit
Reibung in zwei Lastfällen mit Warmstart, Zugstab linear, freier Würfel mit
Netto-Last (Hilfsfesselung, also der Lagrange-Rand in `_geloest`) und der
fließende Block mit Kontakt (7 Kontaktläufe, 53 Kontaktschritte). Alle 318
verglichenen Felder — Verschiebungen, Auflager- und Kontaktkräfte, Spannungen,
Kontaktzustand und die Zählwerte in `info` — sind gleich
(`numpy.array_equal`, 22.09.2026). Mit mehreren Threads ist PARDISO schon für
sich nicht bitgleich (§ 9 des Benutzerhandbuchs); dort wurde nicht verglichen.

##### Gegenprüfung 22.09.2026: Threads nach dem Ausweichen

`LinearSolver._aufbauen` setzt die Threadzahl für PARDISO
(`_mkl_threads_setzen`) **vor** `ps.factorize`. Scheiterte die Zerlegung,
blieb `threads` auf diesem Wert, und SuperLU erschien in `beschreibung()`
und im Nachweis mit den Threads von PARDISO — gemessen mit
`solver_threads = 2` und werfendem `factorize`: `threads = {"2": 1}`, Zeile
„1× SuperLU (2 Threads)“. Der Klassenkommentar sagt dagegen: SuperLU meldet
immer 1. Jetzt setzt der Ausweichzweig `threads = 1` und löscht, was PARDISO
vor dem Scheitern eingetragen hat (`mtype`, `gestoerte_pivots`,
`pardiso_kennzahlen`, `nnz_faktor`). `mtype` wird mit `getattr` gelesen: ein
fehlendes Feld in pypardiso darf nicht über das `except` den Löser wechseln
lassen, nur weil mitgeschrieben wird. Die Rechnung berührt das nicht; es sind
nur Angaben (`test_loeser_nachweis_nennt_das_ausweichen`).

Das Zurücksetzen von `residuum` auf nan (oben) hat seither einen eigenen Test,
`test_residuum_gehoert_zur_loesung`: ohne die nan-Zeile meldet `residuum` nach
`solve(b, check=False)` die Zahl der vorigen Lösung, 7,9·10⁻¹⁶, und das Buch
zählte sie als gemessen (3 von 4 Prüfungen rot, gemessen 22.09.2026).


### 1.4 Querschnittswerte freier Profile

Der freie Profileditor vereinigt Teile nach dem **Satz von Steiner**
(`sections.build`): mit den Teilwerten A_i, I_y,i, I_z,i, I_yz,i im
gemeinsamen y-z-Bezug und den Schwerpunktlagen (y_i, z_i) ist

    A = Σ A_i,   y_c = Σ A_i y_i / A,   z_c = Σ A_i z_i / A
    I_y = Σ (I_y,i + A_i (z_i − z_c)²),   I_z = Σ (I_z,i + A_i (y_i − y_c)²)
    I_yz = Σ (I_yz,i + A_i (y_i − y_c)(z_i − z_c))

Daraus die Hauptwerte I_1,2 = (I_y + I_z)/2 ± √(((I_y − I_z)/2)² + I_yz²) und
der Hauptachsenwinkel α = ½·atan2(2 I_yz, I_y − I_z). Gedrehte Teile gehen mit
ihrem gedrehten Tensor R^T I R ein; ein gespiegeltes Teil wechselt das
Vorzeichen von I_yz.

**T-Profil** (`Section.tee`, auch halbierte Doppel-T IPET/HEAT/HEBT): Flansch
b·t_f, Steg (h − t_f)·t_w, Ausrundungen wie beim Doppel-T; z_c von der
Flanschoberkante. W_pl,y folgt aus der plastischen Nulllinie, die die Fläche
halbiert (im Flansch oder im Steg).

**Element (Blechstreifen)** von Knoten 1 nach Knoten 2, Länge L, Dicke t,
Richtung e = (e_y, e_z): mit I_l = t L³/12 (um die Querachse) und
I_q = L t³/12 (um die Längsachse)

    I_y = I_l e_z² + I_q e_y²,   I_z = I_l e_y² + I_q e_z²,   I_yz = (I_l − I_q) e_y e_z
    I_t = L t³/3   (offener dünnwandiger Querschnitt)

**Fläche (Polygon)** mit den Eckpunkten (y_i, z_i), c_i = y_i z_{i+1} − y_{i+1} z_i
(Green über die Kanten, unabhängig vom Umlaufsinn):

    A = ½ Σ c_i,   S_y = ∫z dA = ⅙ Σ (z_i + z_{i+1}) c_i,   S_z = ∫y dA = ⅙ Σ (y_i + y_{i+1}) c_i
    ∫z² dA = 1/12 Σ (z_i² + z_i z_{i+1} + z_{i+1}²) c_i,   ∫y² dA entsprechend
    ∫yz dA = 1/24 Σ (y_i z_{i+1} + 2 y_i z_i + 2 y_{i+1} z_{i+1} + y_{i+1} z_i) c_i

Ein Loch wird mit seinen Werten abgezogen; danach Steiner zum Schwerpunkt.
Für die **Torsion** eines Polygons gibt es keine geschlossene Lösung; genommen
wird die Näherung nach Saint-Venant

    I_t ≈ A⁴ / (4π² I_p),   I_p = I_y + I_z um den eigenen Schwerpunkt,

die für den Kreis exakt ist und für ein Quadrat 8 % zu hoch liegt. Bei
Löchern wird als Differenz von Außen- und Lochwert gerechnet, was für den
dünnen Ring den Bredtschen Wert 2π r_m³ t trifft (`tests/test_sections.py`
prüft Kreis, Ring, Rechteck mit Loch und das aus drei Streifen gebaute I
gegen die geschlossenen Formeln).

**Plastische Widerstandsmomente eines Polygons** (16.09.2026, auch für die
gezeichnete Kontur und die Parameterprofile aus Maßen): die plastische
Nulllinie halbiert die Fläche. Gesucht wird sie durch Halbieren des
Intervalls zwischen Unter- und Oberkante (`sections._wpl`; das Polygon wird
an der Geraden geschnitten, Sutherland-Hodgman, die Fläche der Hälfte über
Green), Löcher gehen mit negativem Vorzeichen ein. W_pl ist die Summe der
Flächenmomente beider Hälften um diese Linie:

    W_pl,y = ∫ |z − z₀| dA,   A(z > z₀) = A/2

exakt für Polygone: Rechteck b·h²/4, das Doppel-T als Polygon trifft die
Katalogformel auf 1e-9 (`tests/test_kontur.py`). Randabstände und W_el
werden in den **Hauptachsen** genommen; Hauptachse „y“ ist seit dem
16.09.2026 die, die der Bezugsachse y näher liegt (|α| ≤ 45°, bei
Symmetrie α = 0) - vorher hieß der größere Hauptwert I_y und ein flach
liegendes Rechteck galt als um 90° gedreht. Da der Stab I_y als Biegung um
seine lokale y-Achse ansetzt (α geht nicht in die Steifigkeit ein),
entscheidet diese Konvention, welche Achse steif ist; ein im Editor um 90°
gedrehtes Profil tauscht I_y und I_z.

### Vorspannung als Anfangsdehnung

Eine Vorspannkraft F_v in einem Stab oder einer Schraube wird nicht als
äußere Kraft, sondern als **Anfangsdehnung** ε₀ = −F_v/(E·A) aufgebracht -
dieselbe Umsetzung wie eine Abkühlung um ΔT = −F_v/(E·A·α). Für Stäbe sind
die äquivalenten Knotenlasten f = [+F_v, 0, …, −F_v, 0, …] in lokalen
Koordinaten (sie ziehen die Enden zusammen); die Stabendkräfte folgen aus
f_l = k·u − f₀ und enthalten damit die Vorspannung: beidseitig gehalten steht
der Stab unter N = F_v ohne Verschiebung, frei verkürzt er sich um F_v·L/(E·A)
ohne Kraft. Für Volumenkörper (Schraubenschaft) ist die Anfangsspannung
einachsig σ₀ = −F_v/A · a⊗a längs der Achse a; die Knotenlasten sind
f = ∫Bᵀσ₀ dV über alle Elemente des Körpers, die Querschnittsfläche A das
Volumen des Körpers geteilt durch seine Länge längs a. Die Spannungen im
Ergebnis sind σ = D·ε − σ₀. Geprüft an geschlossenen Werten (tests/test_lasten.py):
Lagerkräfte F_v, Verkürzung F_v·L/(E·A), σ_z = F_v/A im eingespannten Schaft.

## 2 Lasten

* Knotenlasten, Momente, vorgegebene Verschiebungen, Federlager.
* Streckenlasten auf Stäben, global oder lokal, konstant oder linear
  veränderlich (Trapez), auch **abschnittsweise** auf [a, b] innerhalb eines
  Elements. Die äquivalenten Knotenlasten sind das Integral der Last über die
  Ansatzfunktionen des Stabes, f = ∫ₐᵇ Nᵀ(x) q(x) dx — linear für die
  Längskraft, Hermite-Polynome dritten Grades für die Biegung —, mit
  vier Gauß-Punkten ausgewertet (Integrand höchstens vierten Grades, also
  exakt). Für a = 0, b = L ergibt das die Volleinspannwerte der Trapezlast,
  für b → a die der Einzellast P a b²/L² und P a² b/L². Die Schnittgrößen an
  Zwischenstellen folgen aus den Stabendkräften und den Abschnittslasten
  durch Gleichgewicht am Teilstab: Resultierende Q(x) und ihr Moment um x je
  Abschnitt, stückweise integriert; der Querkraftverlauf knickt an den
  Abschnittsenden.
* **Linienlasten** hängen am Stab (Kette von Elementen) oder an einer Linie.
  Auf dem Stab werden sie in Abschnittslasten der Elemente zerlegt (q am
  Elementanfang und -ende linear interpoliert). Auf einer Linie — dem Rand
  einer Schale, der Kante eines Körpers — gehen sie auf die Netzknoten der
  Linie: je Teilstück zwischen zwei Knoten Resultierende ½(qₐ+q_b)·l und
  Schwerpunkt l(qₐ+2q_b)/(3(qₐ+q_b)), aufgeteilt nach dem Hebelgesetz.
* **Zwangsverformungen** (vorgegebene Verschiebungen und Verdrehungen an
  gelagerten Knoten, je Lastfall): K_ff u_f = F_f − K_fs u_s mit den
  vorgegebenen Werten u_s; die Auflagerkräfte folgen aus R_s = K_sf u_f +
  K_ss u_s − F_s. Ein vorgegebener Freiheitsgrad ohne Lager bleibt unwirksam
  und wird gemeldet. In Kombinationen gehen die Vorgaben mit ihren Faktoren
  ein (lineare Überlagerung).
* **Ungleichmäßige Flächenlast**: p(x) = a + g·x, festgelegt durch zwei
  Stützpunkte (linear entlang ihrer Verbindung, darüber hinaus fortgesetzt)
  oder drei Stützpunkte (Ebene der Lastwerte, Lösung kleinster Norm). Jede
  Elementseite bekommt den Wert an ihrem Schwerpunkt — bei Elementen, die
  klein gegen die Lastveränderung sind, ist das die Resultierende der Seite
  genau, ihr Angriffspunkt weicht um weniger als eine Elementgröße ab.
* **Temperatur als Objektlast** auf Flächen und Volumen: ΔT und ΔT_z
  hängen am Objekt und werden beim Vernetzen auf alle Elemente gelegt.
* Flächenlasten auf Schalen (normal oder in vorgegebener globaler Richtung)
  und auf Volumenoberflächen (Flächennummer).
* **Lasten an der Geometrie** (`Geometrielast`): Eine Last, die an einer Fläche
  oder einem Volumenkörper hängt und beim Vernetzen auf die entstandenen
  Elementseiten verteilt wird. So kommen die Flächenlasten aus RFEM an, wo es
  beim Einlesen noch gar keine Elemente gibt. Zwei Zusätze:
  * ein **Wirkungsbereich** — ein Rechteck in einer eigenen Ebene
    (Ursprung, zwei Achsen u/v, von/bis). Belastet wird jede Elementseite,
    deren Schwerpunkt im Fenster liegt.
  * **auf die Projektion**: p ist dann die Last je Quadratmeter der
    *Projektion* auf die Ebene senkrecht zur Lastrichtung d. Belastet wird
    nur, was der Last zugewandt ist (Außennormale n mit n·d < 0), und zwar mit
    p · A · |n·d| in Richtung d. So sind Schnee, Wind und die **Lagerpressung
    in einer Bohrung** gezählt: über eine Bohrung summiert sich die Last
    genau zu p · d · l — der Lagerkraft. Ohne die Projektion, also als Druck
    senkrecht zur Fläche, höbe sie sich über den Zylinder auf und der
    Lastfall wäre kräftefrei.
* Eigengewicht je Lastfall (Erdbeschleunigungsvektor).

**Eine Last, die nicht wirken kann, sagt es.** Bis zum 22.09.2026 gab es drei
Eingaben, die eine Last **zu 100 %** ausfallen ließen, ohne dass irgendetwas
gemeldet wurde — und in allen drei Fällen stand die Last weiter mit ihrem
vollen Betrag im Bericht und wurde in der Ansicht an einer Fläche gezeichnet:

* eine **Seitennummer außerhalb des Bereichs** (`solid_face_pressure` gab
  einen Nullvektor zurück). Erreichbar von außen über ein Abaqus-`*DLOAD P5`
  am Tetraeder, der nur vier Seiten hat: gemessen 1000 kN → 0 kN;
* der **Nullvektor als Richtung**. Alle drei Zweige normieren mit
  `d/(‖d‖ or 1)`, aus dem Nullvektor wird dabei wieder der Nullvektor;
  erreichbar über eine Nastran-`PLOAD4` mit ausgeschriebenem `0., 0., 0.`;
* ein **einseitiges Lager ohne Richtung**. Die Normale wird zu (0,0,0), die
  Bedingung trägt keinen Freiheitsgrad, und das Ergebnis ist Zeichen für
  Zeichen das eines Systems ohne dieses Lager — während die Ergebniszeile
  „Kontakt" behauptet.

Die ersten beiden brechen jetzt beim Aufstellen mit einer Ausnahme ab, so wie
das ebene Element es seit jeher tut (`ebene.py`: „Kante gibt es nicht",
„richtung darf nicht der Nullvektor sein"). Alle drei stehen zusätzlich in
`Model.check()`, also **vor** dem Rechnen und mit dem Lastfall dabei. Und der
Grund, den eine leer gebliebene Objektlast nennt, ist berichtigt: „liegt ganz
im Windschatten der Last" schickte den Anwender auf die Suche nach einer
verdeckten Fläche, wo in Wahrheit die Richtung fehlte.

Die *entartete* Seite (Fläche null) bricht dagegen **nicht** ab: für eine
Fläche ohne Inhalt ist 0 N das richtige Ergebnis, und eine Ausnahme dort stünde
gegen die Festlegung, dass ein entartetes Element die Rechnung nicht stoppen
darf. Die frühere Annahme, `Model.check()` melde das Element dann ohnehin als
„entartet ohne Ausdehnung", hielt aber nicht für jeden Fall: ein Sechsflächner,
dessen Deckel mit **eigenen** Knotennummern zu einer Linie zusammengelegt ist,
behält ein Volumen (die Entartungsprüfung misst die Streumatrix aller acht
Ecken), seine Steifigkeit lässt sich aufstellen, und die Last auf dem Deckel
ergab gemessen 0 N ohne eine Zeile in der Prüfung. Seit dem 22.09.2026 nennt
`Model.check()` jede solche Last als WARNUNG mit Lastfall, Element und Seite.
Die Fläche wird wie in `solid_face_pressure` aus den Ecken gebildet (Viereck:
beide Dreiecke); die Grenze ist A ≤ 10⁻⁷ · d² mit d der Diagonale der Hüllbox
des Elements (`diagnose.ENTARTET_REL`). Gerechnet wird je (Elementart, Seite)
im Block: 64 000 Seitenlasten 0,34–0,48 s (fünfmal gemessen in zwei
Durchgängen auf der geteilten Maschine). Liegt A knapp über null, nennt die
Zeile die Kraft so, wie der Lastvektor sie aufstellt, und nicht p · A: `solid_face_pressure` integriert |dA| über die Seite. Beim 10⁻⁹
breiten Deckel ist das p · A = 0,001 N. Beim fast verschlungenen Deckel
(Knoten 6 und 7 getauscht, eine Ecke 10⁻⁹ versetzt) heben sich nur die
Flächenvektoren der beiden Dreiecke auf; die Last wirkt gemessen mit
577 350 N, und die Zeile heißt „in sich verschlungen" (p · A hätte 0,001 N
genannt). Die Steifigkeit dieses Elements bricht ohnehin mit „negativer
Jacobi-Determinante" ab. Elemente mit falscher Knotenzahl übergeht die
Prüfung; beim Stapeln der Knoten warfen sie `check()` in der ersten Fassung
mit `ValueError` um, statt eine Liste zurückzugeben (Gegenprüfung,
23.09.2026). `add_element` weist eine falsche Knotenzahl seit dem 23.09.2026
ab (vorher nahm es ein hex8 mit sieben Knoten an); aus einer Modelldatei
kommt so ein Element weiter herein, `check()` nennt es als eigenen FEHLER
(„Element 2 (hex8): 7 Knoten, erwartet 8“), und die Entartungsprüfung
(`diagnose.knotenzahl_falsch`) lässt es aus — ein tet4 mit drei Knoten ließ
sie vorher mit `IndexError` abbrechen.
* Temperatur: gleichmäßige Änderung ΔT (Stäbe, Schalen, Volumen) und
  Temperaturdifferenz über die Stabhöhe ΔT_z (Krümmung α ΔT_z / h). Die
  Anfangsdehnung wird bei der Spannungsrückrechnung abgezogen.

### 2.1 Wasserdruck auf Verschlüsse (`wasserdruck.py`)

Nettodruck p(z) = ρ·g·(h_ow − z) − ρ·g·(h_uw − z) (jeder Anteil nur unter
seinem Wasserspiegel). Resultierende und Angriffspunkt durch Integration
über die Verschlusshöhe: für ein senkrechtes Rechteck F = ½·ρ·g·h²·b,
Hebel h/3 über der Dichtung; mit Unterwasser F = ½·ρ·g·b·(h_ow² − h_uw²),
Hebel (h_ow³ − h_uw³)/(3·(h_ow² − h_uw²)).

* **Überströmen**: h_ü = h_ow − z_ok, Abfluss je Breite nach Poleni
  q = ⅔·μ·√(2g)·h_ü^1,5, auf der Krone kritischer Abfluss h_c = ⅔·h_ü,
  v_c = √(g·h_c), Fr = 1. Mit Absenkung: Druck an der Krone
  ρ·g·h_ü − ρ·v_c²/2 = ⅔·ρ·g·h_ü, der Fehlbetrag ⅓·ρ·g·h_ü klingt linear über
  2·h_ü nach unten ab (Näherung nach Naudascher).
* **Unterströmen**: kontrahierter Strahl μ_a·a, wirksame Fallhöhe
  Δh = h_ow − max(h_uw, z_uk + μ_a·a), v_a = √(2·g·Δh) (Torricelli),
  q = μ_a·a·v_a, Fr = v_a/√(g·μ_a·a). Mit Absenkung: an der Unterkante der
  Druck des Strahls bzw. des Unterwassers statt ρ·g·(h_ow − z_uk), Fehlbetrag
  linear über 2·a nach oben abklingend.
* **Druckschwankung**: Δp = c_p'·ρ·v²/2 mit v = max(v_c, v_a) als Amplitude
  auf der benetzten Fläche (eigener Lastfall).

Die Lasten liegen als Objektlasten mit ``verlauf["art"] == "wasser"`` an den
Flächen; je Elementseite wird p am Schwerpunkt ausgewertet (bei linearem
Druck ist die Resultierende je Element damit exakt). `tests/test_wasserdruck.py`
prüft Druckverlauf, Kennwerte (Rechteckschütz, Netto mit Unterwasser, Poleni,
Torricelli) und die Summe der Elementlasten auf einem Netz.

### 2.1a Strömungsnumerische Berechnung des Wasserdrucks (`stroemung.py`)

Vorgabe des Generierers. Die Strömung um den Verschluss wird in einem
**lotrechten Schnitt** in Strömungsrichtung als **Potentialströmung**
(reibungsfrei, drehungsfrei, inkompressibel) gerechnet: Δφ = 0 auf einem
Rechteckgitter (Finite Volumen, Zellgröße h = Verschlusshöhe/Gitterzahl),
v = ∇φ. Der Verschluss wird aus den benetzten Flächen und Körpern in die
Ebene gerastert (Kanten dicht abgetastet, um eine Zelle verdickt, damit
schräge dünne Wände dicht bleiben), Sohle und Schwelle unter der Dichtung sind
Wand, die Wasserspiegel feste Deckel (Oberwasser links, Unterwasser rechts,
über der Krone die kritische Tiefe h_c = ⅔·h_ü). Randbedingungen: Zufluss
links mit U = q/(h_ow − z_Sohle), Abfluss über die Krone mit q nach Poleni
und unter dem Verschluss mit q = μ_a·a·√(2·g·Δh) nach Torricelli - frei ins
Trockene an der Verschlussrückseite, sonst am rechten Rand ins Unterwasser;
alle übrigen Ränder undurchlässig. Je zusammenhängendem Gebiet wird φ in
einer Zelle festgehalten (reine Neumann-Aufgabe).

Der Druck folgt aus Bernoulli p = ρ·g·(E − z) − ½·ρ·|v|² mit der
Energiehöhe E_ow = h_ow + U²/2g vor und im Verschluss und E_uw hinter ihm;
Unterdruck wird bei 0 gekappt (belüftet), auf Wunsch bis −70 kN/m² angesetzt.
Die Resultierende je Breite ist die Summe der Zelldrücke auf die
Verschlusszellen; die Elementseiten tasten das Feld 1,5 … 3,5 Zellen vor der
Fläche ab, dünne Schalen netto aus beiden Seiten.

Geschlossene Lösungen, die die Rechnung exakt trifft (`tests/test_stroemung.py`):
Kanal ohne Hindernis (v = U überall), geschlossener Verschluss
(F = ½·ρ·g·h², z_R = h/3, mit Unterwasser F = ½·ρ·g·(h_ow² − h_uw²)),
Massenbilanz beim Ausfluss. Näherungsweise geprüft: Druck an der Krone
zwischen ⅔·ρ·g·h_ü (Naudascher) und ρ·g·h_ü, Druckabfall an der Unterkante beim
Unterströmen. Nicht abgebildet: Reibung und Turbulenz, freie Oberfläche
(Absenkung des Spiegels wird nicht iteriert), Wechselsprung im Unterwasser,
Wellen, Luftaufnahme, dreidimensionale Effekte (Pfeiler, Nischen) - der
Schnitt gilt über die ganze Breite.

### 2.2 Wind nach DIN EN 1991-1-4 (`wind.py`)

Strömung: v_b = c_dir·c_season·v_b,0; k_r = 0,19·(z_0/0,05)^0,07,
c_r(z) = k_r·ln(z/z_0) für z_min ≤ z ≤ 200 m; v_m = c_r·c_o·v_b;
I_v = k_I/(c_o·ln(z/z_0)); q_p = (1 + 7·I_v)·½·ρ·v_m² mit ρ = 1,25 kg/m³.
Mischprofile des NA (Tab. NA.B.2) als Vielfache von q_b = ½·ρ·v_b².

Beiwerte: Wände Tab. 7.1 (D: 0,7 … 0,8 und E: −0,3 … −0,7 über h/d
interpoliert; A/B/C = −1,2/−0,8/−0,5 in Bändern e/5, e ab der Luvkante mit
e = min(b, 2h)), Flachdach Tab. 7.2 (F/G/H/I = −1,8/−1,2/−0,7/−0,2 nach
Bild 7.6), freistehende Wand Tab. 7.9 (A–D ab dem freien Ende), Anzeigetafel
c_f = 1,8; Stäbe: Rechteck Bild 7.23 (log-linear über d/b) mit ψ_r,
Kreiszylinder Gl. 7.19 (c_f,0 = 1,2 + 0,18·lg(10k/b)/(1 + 0,4·lg(Re/10⁶)),
mindestens 0,4; unterkritisch 1,2), scharfkantige Profile 2,0, Fachwerk
Bild 7.33/7.34 über φ; ψ_λ nach Bild 7.36 mit λ nach Tab. 7.16. Die Rolle
einer Fläche (Luv, Lee, Seite, Dach) folgt aus ihrer mittleren Normale gegen
die Anströmung; der Druck je Elementseite ist c·q_p(z) am Schwerpunkt,
positiv gegen die Außennormale. `tests/test_wind.py` prüft die Formeln mit
Zahlenwerten der Norm und die Summen der Elementlasten an einem Quader
(Luvdruck + Leesog, Dachsog nach Zonen, Innendruck) sowie die Stablasten
eines Rohrmasts.

### 2.2a Numerischer Windkanal (`stroemung.py`, `wind.py`)

Wahlweise statt der Zonenbeiwerte: die Strömung um die Hindernisse (Flächen,
Stäbe als schmale Vierecke) wird in einem Schnitt mit dem
**Gitter-Boltzmann-Verfahren** (D2Q9, BGK-Stoßoperator) gerechnet. Links
strömt es mit u_∞ ein, rechts frei aus, oben und unten herrscht die freie
Anströmung (im Aufriss unten Haftbedingung am Boden); die Hindernisse
reflektieren die Verteilungen (Rückprall = Haftbedingung). Die Zähigkeit
folgt aus der Modell-Reynolds-Zahl Re = u_∞·L/ν mit L = Querabmessung des
Hindernisses; für die Stabilität des Verfahrens wird τ = 3ν + ½ ≥ 0,52
gehalten (die wirksame Re-Zahl steht im Bericht). Dichte und
Geschwindigkeit werden über die letzten 40 % der Zeitschritte gemittelt;
c_p = (p − p_∞)/(½·ρ·u_∞²) mit p = ρ·c_s² und p_∞ weit vorn.

Die Elementseiten in der Schnittebene tasten c_p vor der Fläche ab (dünne
Schale: netto), der Druck ist c_s·c_d·(c_p − c_pi)·q_p(z) mit dem Höhenprofil
der Norm; Flächen quer zur Ebene (Dächer im Grundriss, Seitenwände im
Aufriss) behalten die Zonenbeiwerte. Stäbe erhalten ihre Norm-Linienlast mal
(v/v_∞)² am Stabmittelpunkt (Abschirmung im Nachlauf). Geprüft
(`tests/test_stroemung.py`, `tests/test_wind.py`): Staupunkt c_p ≈ 1,
Sog und Rückströmung im Nachlauf, Verschattung eines zweiten Körpers und einer
Wand im Nachlauf, Abschirmung eines Stabes, Aufriss mit Dach.

Grenzen: ebene Strömung (kein Umströmen über das Dach im Grundriss, keine
Ecken quer), Modell-Reynolds-Zahl weit unter der des Bauwerks (Ablösung und
Nachlauf sind qualitativ), keine Turbulenz der Anströmung, keine
Grenzschicht des Geländes im Grundriss. Die Beiwerte sind gegen die Norm zu
prüfen; sie zeigen, **wo** Verschattung und Wirbel wirken.

### 2.3 Strömungsinduzierte Schwingungen eines Verschlusses (`schwingung.py`)

Grundlagen: Naudascher/Rockwell, *Flow-Induced Vibrations*; Kolkman;
DIN 19704-1 (Schwingungen); Westergaard (1933).

* **Hydrodynamische Masse.** Für eine senkrechte Wand vor einem Wasserkörper
  der Tiefe H wirkt bei horizontaler Beschleunigung die Massenbelegung
  m''(y) = 7/8·ρ·√(H·y) (y Tiefe unter dem Spiegel), in Summe
  7/12·ρ·H² je Breite. Sie wird je benetztem Schalenelement mit 2×2
  Gauß-Punkten (Dreieck: Seitenmitten) integriert, gleichmäßig auf die
  Knoten verteilt und als Block m·n·nᵀ (n Elementnormale) zur Massenmatrix
  addiert - je Wasserseite (Ober- und Unterwasser) getrennt. Die
  Eigenfrequenzen folgen aus (K − ω²(M + M_h))φ = 0; bei gleichmäßiger
  Zusatzmasse exakt f_w = f_l/√(1 + m_h/m), sonst gibt das modale
  Verhältnis φᵀM_hφ/φᵀMφ die Abminderung an.
* **Wirbelablösung** an der Kante: f_s = St·v/d mit St ≈ 0,2, v aus dem
  Wasserdruck (Ausflussstrahl v_a = √(2gΔh) bzw. Überfall v_c = √(g·h_c)), d
  Kantenbreite in Strömungsrichtung. Resonanz, wenn |f_s/f − 1| ≤ band.
* **Reduzierte Geschwindigkeit** V_r = v/(f·d). Für V_r ≤ V_r,grenz (≈ 1)
  ist die Anregung quasistatisch (f_s/f = St·V_r ≤ 0,2); darüber sind
  instabilitäts- (Scherschichtinstabilität an der Kante) und
  bewegungsinduzierte Schwingungen (Kolkman: Verschlüsse mit Dichtung
  stromab, Unterdruck hinter der Kante) möglich - das Programm gibt den
  Hinweis, ein Ausschluss verlangt Konstruktion oder Versuch.
* **Antwort auf die Druckschwankung** Δp = c_p'·ρ·v²/2 (Lastfall des
  Generierers, statisch gerechnet: σ_amp, u_amp): Vergrößerungsfunktion
  V = 1/√((1 − r²)² + (2ζr)²) mit r = f_s/f₁; σ_dyn = V·σ_amp,
  Δσ = 2·σ_dyn. Ermüdung: N = f_s·3600·h·a Lastspiele, Δσ_Ed = γ_Ff·Δσ,
  N_R aus der Wöhlerlinie des Kerbfalls (EN 1993-1-9, m = 3/5,
  Dauerfestigkeit, Schwellenwert), D = N/N_R ≤ 1.

`tests/test_schwingung.py` prüft die Westergaard-Summe auf dem Netz, die
exakte Frequenzabminderung bei gleichmäßiger Zusatzmasse, die
Rayleigh-Schranke der nassen Grundfrequenz, Strouhal, V_r, V(r = 1) = 1/(2ζ),
die Resonanzerkennung und die Ermüdungskette. Dazu prüft sie, dass der
Nachweis in der gespeicherten Modelldatei steht und beim Laden
zurückkommt. Ins Modell eingetragen wird er von der Oberfläche
(*Nachweise → Schwingung → Verschluss*); die Rechnung `schwingung.nachweis`
selbst ändert das Modell nicht.

## 3 Lastfälle, Kombinationen, Umhüllende

Jeder Lastfall trägt eine Einwirkungskategorie (DIN EN 1990/NA Tabelle
A.1.1) mit Kombinationsbeiwerten ψ0, ψ1, ψ2. Der Kombinationsgenerator
bildet

* GZT (STR/GEO) nach Gl. 6.10 (Standard des deutschen NA) oder 6.10a/6.10b,
  jeweils mit jeder veränderlichen Einwirkung als Leiteinwirkung,
  ständige Lasten ungünstig (γG,sup = 1,35) und günstig (γG,inf = 1,0),
* außergewöhnliche Situationen nach Gl. 6.11b,
* GZG charakteristisch (6.14b), häufig (6.15b), quasi-ständig (6.16b).

Lastfälle derselben Ausschlussgruppe (z. B. Wind aus verschiedenen
Richtungen) wirken nie gemeinsam. Bei linearen Systemen werden Kombinationen
durch Superposition der Lastfallergebnisse gebildet (Verschiebungen,
Lagerkräfte, Stabendkräfte, Schalenschnittkräfte, Volumenspannungen sind
linear). Abgeleitete Größen (Vergleichsspannung, Randspannung, Ausnutzung)
werden aus den überlagerten Rohgrößen berechnet. Bei Kontakt (nichtlinear)
wird jede Kombination einzeln gelöst.

Umhüllende: je Ergebnisgruppe (GZT, GZG …) werden Minimum und Maximum jeder
Größe an jeder Nachweisstelle mit der maßgebenden Kombination gespeichert.

**Kombinationen mit Alternativen.** Eine RFEM-Ergebniskombination „LF1/p oder
LF2/p oder …" ist keine Summe: ihr Ergebnis ist Minimum und Maximum je Größe
über die *Alternativen* (`Combination.alternativen`, jede Alternative ein
Satz Lastfall → Faktor). Der Löser bildet daraus je Kombination eine eigene
Umhüllende und faltet sie in die Umhüllende ihrer Art ein (zur Darstellung;
die Nachweise sehen die Alternativen einzeln, siehe unten). Zwei Dinge
halten das bezahlbar:

* Die Umhüllende wird **inkrementell** gebildet (`Envelope.aufnehmen`): ein
  Ergebnis nach dem anderen geht in das laufende Minimum und Maximum ein,
  mit Herkunft; bei Gleichstand gewinnt das erste Ergebnis, so wie `argmin`
  beim Stapeln. Das laufende Verfahren ist darum **bitgleich** mit dem
  gestapelten (`test_umhuellende`), braucht aber nicht alle Ergebnisse
  gleichzeitig im Speicher — am Drehlager hätten das 128 Alternativen je
  GZT-Kombination und über 3500 in den Ermüdungskombinationen sein müssen.
* Eine Alternative aus genau **einem Lastfall mit Faktor 1** ist dessen
  Lastfallergebnis und wird wiederverwendet. Am Drehlager trifft das auf alle
  720 Einträge der 52 Ergebniskombinationen zu: die Umhüllenden kosten keine
  einzige zusätzliche Lösung. Jede andere Alternative wird als vorübergehende
  Kombination gerechnet (Überlagerung; im Kontaktmodell direkte Lösung) und
  im linearen Modell nach dem Einfalten verworfen; das Protokoll nennt die
  Zahl. Was sich später nicht aus den Lastfällen wiedergewinnen lässt – die
  direkte Lösung im Kontaktmodell, eine Alternative nach Theorie II./III.
  Ordnung, eine Alternative aus Lastfällen, deren lineares Ergebnis danach
  durch II./III. Ordnung ersetzt wird –, bleibt in `Analysis.alternativen`
  und wird mit den Ergebnissen gespeichert.

Belegt am Kragarm mit drei Lastfällen: die Umhüllende über die Alternativen
{LF1}, {LF2}, {1,35·LF1 + 1,5·LF3} ist gleich der Umhüllenden über dieselben,
einzeln gerechneten Kombinationen, in Werten und Herkunft; im Kontaktmodell
wird die zusammengesetzte Alternative direkt gelöst, die Lastfall-Alternative
weiterhin wiederverwendet.

**Nachweise über Ergebniskombinationen.** Ein Nachweis braucht
zusammengehörige Schnittgrößen; die Umhüllende mischt Minimum und Maximum
verschiedener Alternativen und taugt dafür nicht. Jeder Nachweis – Stäbe,
Volumen, Beulen, Lasteinleitung, Anschlüsse, Verformungen – sieht darum jede
Alternative als eigene Kombination „EK [k]" (`ergebnisse_der_alternativen`):
abgelegt aus `Analysis.alternativen`, als Lastfallergebnis (ein Lastfall mit
Faktor 1) oder im linearen Modell aus den Lastfällen neu überlagert. Auf die
Lastfälle selbst fällt ein Nachweis nur zurück, wenn das Modell **gar keine**
Kombination hat; fehlt das Ergebnis einer Kombination oder Alternative, wird
sie als „nicht nachgewiesen" gemeldet (Protokoll, Nachweiszeile, Bericht,
Gesamturteil) und nicht ersetzt. Bis zum 22.09.2026 lasen die Nachweise nur
`Analysis.combinations` und wichen bei leerem `combinations` auf die
Lastfälle aus. Eine Ergebniskombination stand darin nur, wenn das Modell
daneben eine gewöhnliche Kombination hatte (nur dann liefen
`check_theorie2`/`check_theorie3`) und sie dort nach II. oder III. Ordnung
gerechnet wurde, und dann als Nullergebnis (siehe „Theorie II./III. Ordnung
einer Ergebniskombination" unten). Bei „automatisch" entschied darüber das
α_cr ihrer leeren Faktoren. Gemessen am Kragarm
(LF1 Fz = 10 kN, LF2 Fz = 20 kN an der Spitze), nur mit der
Ergebniskombination {1,35·LF1} oder {1,35·LF1 + 1,5·LF2}: Ausnutzung des
Stabes vorher 0,170 (nachgewiesen gegen LF1 und LF2 mit Faktor 1), jetzt
0,370 wie mit der gewöhnlichen Kombination 1,35·LF1 + 1,5·LF2; das Verhältnis
2,175 ist 4,35e4/2e4. Verformungsnachweis (0,1152) und Volumennachweis
(0,3619, Hexaederstab) stimmen ebenso mit der gewöhnlichen Kombination
überein (`test_umhuellende`). Gemessen an der Halle (alle 42
GZT-Kombinationen als eine Ergebniskombination „EK") an einer Kopie des
Standes 54b6f9a (24.09.2026): Mit den 30 GZG-Kombinationen daneben stand
„EK" bei „ein" in `Analysis.combinations`, ebenso bei „aus" mit „EK"
ausdrücklich nach III. Ordnung; in beiden Fällen hatten alle drei Stäbe
η = 0,0000, maßgebend „EK", ohne Warnung, und das Gesamturteil des Berichts
lautete „Alle Nachweise erfüllt.". Bei „automatisch" war α_cr der „EK"
unendlich; sie wurde nicht nach II. Ordnung gerechnet und stand nicht in
`Analysis.combinations`, wie bei „aus". Bei „automatisch" und „aus" wurde
darum kein Stab nachgewiesen („Nachweise EC3: keine Staebe"), weil keine
GZT-Kombination in `Analysis.combinations` stand, und das Gesamturteil
lautete „Es wurden keine Nachweise geführt; die Ergebnisse dienen der
Schnittgrößen- und Verformungsermittlung.". Ohne die GZG-Kombinationen
blieb `Analysis.combinations` in allen vier Fällen leer, und die Stäbe
wurden gegen die Lastfälle mit Faktor 1 nachgewiesen (Riegel 0,2776 aus
LF1, „Alle Nachweise erfüllt."). Am jetzigen Stand, mit und ohne die
GZG-Kombinationen: Riegel 0,9734 bei „ein", 0,9749 mit „EK" nach III.
Ordnung, 0,9654 bei „aus" und „automatisch".

**Gleiche Alternativen im Stabnachweis.** Steht ein Lastfall mit Faktor 1
als Alternative in mehreren Ergebniskombinationen, liefert
`ergebnisse_der_alternativen` unter jedem Namen dasselbe Lastfallergebnis. Der Stabnachweis nach EC3 lief
bis zum 23.09.2026 über jeden Namen (Befund B055). Jetzt fasst
`_gleiche_zusammenfassen` vor dem Nachweis zusammen, was sicher dasselbe
Ergebnis ist: dasselbe Objekt, oder zwei neu überlagerte Alternativen mit
denselben Faktoren. Überlagert wird nur im linearen Modell, und die
Lastfälle einer Kombination gehören zu ihrer Situation; gleiche Faktoren
heißen dort also gleiches Ergebnis. Abgelegte Alternativen (Theorie II./III.
Ordnung, Kontaktmodell) und gewöhnliche Kombinationen werden nur über das
Objekt verglichen. Ihr Ergebnis hängt auch an der Theorie der Kombination
bzw. am Startzustand der direkten Lösung. Der Eintrag heißt „EK_A [1] =
EK_B [1]" (ab fünf Namen gekürzt). Gemessen am Kragarm mit EK_A und EK_B,
je {LF1} oder {1,35·LF1 + 1,5·LF2}, und K2 = 1,35·LF1 + 1,5·LF2: vorher 5 Einträge und 5
Querschnittsnachweise je Stab, jetzt 3; die Ausnutzung bleibt 0,370213,
maßgebend „EK_A [2] = EK_B [2]" statt „EK_A [2]". Im Kontaktmodell bleiben
die beiden direkt gelösten EK_A [2] und EK_B [2] zwei Einträge
(`test_gleiche_alternativen_einmal_nachgewiesen`). Die übrigen Nachweise
(Volumen, Beulen, Lasteinleitung, Anschlüsse, Verformungen) laufen weiter
über jeden Namen.

Die vollen Namenslisten stehen vollständig nur in `DesignResults.gleiche`.
Der Bericht nennt sie unter „Gleiche Ergebnisse, einmal nachgewiesen" nur
für die ersten 40 zusammengefassten Einträge, danach „…", und nur mit der
Berichtsoption „Nachweise EC3". Am Kragarm mit LF1 bis LF42 und EK1 bis
EK5, jede mit den 42 Alternativen {LFi: 1}, sind es 42 Einträge mit je 5
Namen; maßgebend ist der 42., „EK1 [42] = EK2 [42] = EK3 [42] = … (2
weitere)", und „EK5 [42]" kommt im Bericht nicht vor
(`test_gleiche_im_bericht_nur_die_ersten_40`).

Neu überlagert wird eine Alternative nur, wenn die volle Rechnung es genauso
täte. Ist sie nach der Theorie der Ergebniskombination nach II. oder III.
Ordnung zu rechnen, kommt ihr Ergebnis aus `Analysis.alternativen`. Dorthin
legt die volle Rechnung auch jede Alternative mit einem Lastfall, dessen
Ergebnis in `Analysis.cases` durch II./III. Ordnung ersetzt wird: ihre
Überlagerung der linearen Lastfälle lässt sich danach aus `Analysis.cases`
nicht mehr bilden. Überlagert wird sie
dann nur, wenn das Theoriekapitel eine Zeile für sie hat, die beim linearen
Ergebnis blieb: α_cr an oder über der Grenze bei „automatisch", oder ein
Fehler der Rechnung, den die Zeile nennt. So bleibt auch bei einer
gewöhnlichen Kombination das lineare Ergebnis stehen
(`_bei_theorie_I_geblieben`). Sonst wird sie als „nicht nachgewiesen"
gemeldet, etwa nach `solve_all(combinations=False)` oder mit einer
Ergebnisdatei ohne die Gruppe `alternativen` (`ergebnisse._ERGEBNISGRUPPEN`).
So schrieb sie jeder Stand vor fb59de1 (22.09.2026, 23:54), im Hauptzweig
jeder vor dem Merge 21ce779 (23.09.2026, 10:07); `ergebnisse.lesen` lädt
sie mit leerem `Analysis.alternativen`. Gemessen am Druckkragarm mit einer
Datei, die der Stand 54b6f9a (= Hauptzweig 5eb21e6) geschrieben hat: EK1 [1]
und EK1 [2] „nicht nachgewiesen“ mit Theorie II. Ordnung als Grund, K2
nachgewiesen (`test_ergebnisse`, dort mit einer Datei ohne die Gruppe
nachgestellt). In der ersten Fassung der Kur wurde sie
dort still linear überlagert (Gegenprüfung 23.09.2026). Am Druckkragarm stand
EK1 [2] mit 3,321 statt 9,705 mm. An der Halle (theorie2 „ein", alle 42
GZT-Kombinationen als eine Ergebniskombination) kamen Riegel 0,9654 statt
0,9734 und Stiel links 0,6325 statt 0,6454 heraus, ohne Warnung. Die
gewöhnlichen Kombinationen derselben Rechnung meldeten dagegen 42 Warnungen.
Jetzt melden beide Fassungen 42 Warnungen. Die volle Rechnung ist davon
unberührt. An der Halle mit Kranlast gleichen Ergebniskombination und
gewöhnliche Kombinationen einander bei „aus", „automatisch" (26 von 42
Alternativen nach II. Ordnung) und „ein" in den Stab- und
Lasteinleitungsnachweisen auf 1e-9, ohne Warnung.

Gemeldet wird nur, was ein Bauteil verlangt. Hat kein Stab, Volumenbereich
oder Anschluss einen Nachweis und gibt es kein Beulfeld und keine
Lasteinleitungsstelle, wird `_uls_results` gar nicht gefragt. In der ersten
Fassung der Kur (fb59de1) kippte ein Modell nur mit GZG-Kombinationen, Stäben
ohne Nachweis und einem anderen geführten Nachweis (hier einer
Verformungsgrenze) im Gesamturteil von „Alle Nachweise erfüllt." auf „Alle
geführten Nachweise erfüllt – nicht geführt wurden: EC3 (1 Warnung)". Ohne
einen solchen Nachweis stand dort „Es wurden keine Nachweise geführt – nicht
nachgewiesen: EC3 (1 Warnung)" statt „Es wurden keine Nachweise geführt; die
Ergebnisse dienen der Schnittgrößen- und Verformungsermittlung." (Kragarm und
Halle, Gegenprüfung 23.09.2026, nachgemessen an Kopien von fb59de1 und
54b6f9a). Am Stand bis 22.09.2026 meldeten die Stabnachweise keine fehlenden
Kombinationen, und das Gesamturteil kannte den Eintrag „EC3 (n Warnungen)"
nicht. An einem Kragarm (IPE 300, 3 m, nur eine GZG-Kombination mit
Verformungsgrenze, Stab ohne Nachweis) und an der Halle (nur
GZG-Kombinationen, Stäbe ohne Nachweis, eine Verformungsgrenze) stand dort
„Alle Nachweise erfüllt.", ohne die Verformungsgrenze an beiden „Es wurden
keine Nachweise geführt; die Ergebnisse dienen der Schnittgrößen- und
Verformungsermittlung.". Der jetzige Stand gibt in allen vier Fällen
dasselbe Urteil wie der Stand bis 22.09.2026.

**Theorie II./III. Ordnung einer Ergebniskombination.** Nach II. Ordnung gilt
keine Superposition (EN 1993-1-1, 5.2); das gilt auch innerhalb einer
Ergebniskombination. Ist sie nach II. Ordnung (Einstellung „ein" oder
„automatisch", oder ausdrücklich) oder III. Ordnung zu rechnen, rechnen
`check_theorie2`/`check_theorie3` jede Alternative einzeln am verformten
System – auch eine Lastfall-Alternative – als Zeile „EK [k]"; die
Umhüllende wird erst danach aus diesen Ergebnissen gebildet. Bei
„automatisch" entscheidet α_cr je Alternative; liegt es an oder über der
Grenze (10 elastisch, 15 plastisch), bleibt es beim linearen Ergebnis. Nach II. Ordnung wird eine Alternative, die in
mehreren Ergebniskombinationen gleich vorkommt, einmal gerechnet. Vorher
rechnete `check_theorie2` die Ergebniskombination selbst mit leeren Faktoren:
ein Nullergebnis, als „am verformten System gerechnet" gezählt und unter
`Analysis.combinations` abgelegt – von dort ging es in die Art-Umhüllende und
in die Nachweise –, während die Umhüllende der Alternativen linear blieb.
Eine Kombination ohne Faktor ≠ 0 wird jetzt gar nicht mehr nach II./III.
Ordnung abgelegt. Gemessen am Druckkragarm (Querlast in y, α_cr = 1,51 für
1,35·LF1 + 1,5·LF2): Querverschiebung der Umhüllenden 9,705 mm wie bei der
gleichwertigen Kombination nach II. Ordnung, linear 3,321 mm (Zuwachs
+192,3 %); nach III. Ordnung 9,468 mm.

Bleibt eine Alternative bei I. Ordnung (α_cr an oder über der Grenze, oder
ein Fehler der Rechnung, den ihre Zeile nennt), ist ihr Ergebnis die
Überlagerung der **linearen** Lastfallergebnisse – wie bei der gewöhnlichen
Kombination, die `solve_combinations` vor `_lastfaelle_hoeherer_ordnung` aus
denselben linearen Ergebnissen bildet. `solve_all` hält dazu die linearen
Lastfallergebnisse fest, bevor `_lastfaelle_hoeherer_ordnung` die Lastfälle
mit Theorie II./III. ersetzt, und faltet die Umhüllende einer
Ergebniskombination nach II./III. Ordnung damit (`lineare_cases`). Eine
Alternative ist so entweder linear überlagert oder als Ganzes nach II./III.
Ordnung gerechnet, nie ein Gemisch. Eine Zwischenfassung dieser Änderung
(nicht ausgeliefert, gemessen an 9337a3c, Gegenprüfung 23.09.2026) faltete
diese Umhüllende erst nach dem Ersetzen aus `Analysis.cases`: Mit einem
Lastfall W auf Theorie II. Ordnung war eine linear gebliebene Alternative
1,35·G (linear) + 1,5·W (II. Ordnung), und dieses Gemisch ging abgelegt in
die Nachweise.
Gemessen an einem Zweigelenkrahmen (Stiele HEB 200, 5 m, Riegel IPE 300,
8 m; G 8 kN/m und Q 0,5 kN/m auf dem Riegel, W 25 kN am linken Stielkopf;
„automatisch", α_cr der Alternative 19,23): Stielkopf 102,4519 statt
102,1415 mm wie die gewöhnliche Kombination, Ausnutzung Stiel links 0,548474
statt 0,542323, Riegel 1,717078 statt 1,715794, Stiel rechts 1,08153 statt
1,079967. Am Druckkragarm von `test_umhuellende` (Druck 50 kN je Lastfall,
α_cr 15,13, LF2 auf II. Ordnung) EK1 [2] 3,374407 statt 3,320749 mm und die
Lastfall-Alternative 1,0·LF2 1,562553 statt 1,526781 mm. Jetzt gleichen beide
Modelle der gewöhnlichen Kombination. Die gewöhnlichen Kombinationen hatten
das Gemisch nicht, sie entstehen vor dem Ersetzen (am Druckkragarm K2
bitgleich 1,35·LF1 + 1,5·LF2 aus den linearen Lastfällen). Vor dieser
Änderung (Stand 54b6f9a, 22.09.2026) gab es das Gemisch ebenfalls nicht:
`solve_all` faltete die Umhüllende einer Ergebniskombination vor
`_lastfaelle_hoeherer_ordnung`, rechnete aber keine Alternative nach
II. Ordnung und wies keine nach (siehe oben). Am Zweigelenkrahmen war die
Umhüllende am Stielkopf 102,1415 mm wie mit der gewöhnlichen Kombination.
Wogegen die Stäbe nachgewiesen wurden, hing am Modell: `_uls_results` nahm
die GZT-Einträge aus `Analysis.combinations`, sobald dort etwas stand, sonst
die Lastfälle. Am Rahmen („automatisch“) fehlte die Ergebniskombination in
`combinations`; an der Halle („ein“) stand sie dort mit dem Ergebnis null,
gerechnet von `check_theorie2` wie eine Kombination ohne Faktoren (sie steht
in `theorie2.kombinationen`, |u| = 0). Gemessen an 54b6f9a, jedes Mal ohne
Warnung: Hat der Rahmen nur die Ergebniskombination, gelten die Lastfälle
mit Faktor 1, Stiel links 0,497020 aus W statt 0,542323. Hat er daneben
K1 = 1,35 G + 1,5 Q und K2 = 1,35 G + 1,5 W als gewöhnliche Kombinationen
und die Ergebniskombination aus 1,35 G + 1,5 Q + 0,9 W und 1,0 G + 1,5 W,
bleibt die Ergebniskombination unbeachtet, Stiel links 0,480754 aus K2
statt 0,542323 aus EK [2]. An der Halle („ein“, alle 42 GZT-Kombinationen
als eine Ergebniskombination, die 30 GZG-Kombinationen daneben) geht die
Ergebniskombination mit dem Ergebnis null ein: alle drei Stäbe η = 0,0000,
maßgebend „EK“, „alle erfuellt“ (jetzt Stiel links 0,6454, Stiel rechts
0,6398, Riegel 0,9734). Die Zahlen des heutigen Standes am Zweigelenkrahmen
(jeweils nach „statt", dazu α_cr) rechnet `tests/test_theorie2.py` nach,
ebenso die im Benutzerhandbuch. Die Zahlen der Stände 54b6f9a und 9337a3c
sind Messungen an diesen Ständen; kein Test rechnet sie nach, weil der
heutige Stand anders rechnet. Nachrechnen lassen sie sich, indem man diese
Stände aus dem Repository holt und dort rechnet: Am Zweigelenkrahmen ergab
das Modell aus `tests/test_theorie2.py` so am 24.09.2026 an beiden Ständen
die hier genannten Zahlen.

### 3.1 Situationen: Stellung und wirksame Elemente

Jeder Lastfall und jede Kombination gehört zu einer **Situation**; die
Grundstellung (unbewegt, alle Elemente) ist die Vorgabe. Für jede Situation,
in der ein Lastfall steht, wird ein eigenes Gleichungssystem aufgestellt:

* **Stellung**: die Lage entsteht als Kette — erst die Ausgangsstellung
  (rekursiv), dann die eigene Verschiebung der bewegten Knoten und ihre
  Drehung um die Achse der Stellung (Rotationsmatrix nach Rodrigues,
  `bridges.positions.drehmatrix`). Die in der Stellung unwirksamen Lager
  entfallen, die deaktivierten Gelenke werden biegesteif (ihre Freigaben und
  Federn gehen von den Elementen herunter, an denen sie gesetzt wurden), und
  die Elemente der deaktivierten Stäbe, Flächen und Volumen gehen als
  Aktivmaske in das System (wie die deaktivierten Elemente unten). Gerechnet
  wird auf dieser Kopie des Modells; Ergebnisse und Bild beziehen sich auf
  die Lage der Stellung.
* **Deaktivierte Elemente** liefern keinen Beitrag zur Steifigkeitsmatrix,
  keine Elementlasten (Streckenlast, Eigengewicht, Temperatur, Flächenlast)
  und bekommen Schnittgrößen null. Knotenlasten an Knoten, an denen kein
  wirksames Element mehr hängt, entfallen; solche Knoten werden über die
  Regel „Freiheitsgrad ohne Steifigkeit wird festgehalten“ gesperrt.
  Kopplungen einer Kontaktfuge an solchen Knoten entfallen ebenfalls.
* **Kombinationen** überlagern nur Lastfälle derselben Situation (gleiche
  Steifigkeitsmatrix — sonst wäre die Superposition falsch); eine Mischung
  meldet die Modellprüfung als Fehler, der Rechenkern weist sie ab. Die
  Theorie II. Ordnung rechnet jede Kombination mit dem System ihrer
  Situation (geometrische Steifigkeit ebenfalls nur aus wirksamen Elementen).
* **Umhüllende** und Nachweise laufen wie bisher über alle Kombinationen –
  die Stablängen bleiben bei einer Drehung erhalten.
* **Ein einzelner Lastfall** (`solve_static`: „Nur aktiver Lastfall“,
  `--analyse lastfall`, Webserver, Aufträge, adaptive Vernetzung) und das
  **Knicken** (`solve_buckling`, Grundzustand Lastfall oder Kombination)
  bauen ihr System ebenso je Situation (`situationssystem`); die
  geometrische Steifigkeit des Knickens nimmt nur die wirksamen Elemente.
  Bis zum 23.09.2026 bauten beide `StaticSystem(model)` ohne Situation und
  rechneten still in der Grundstellung. `solve_static(case="all")` und
  `solve_buckling(case="all")` über Lastfälle verschiedener Situationen
  werden abgewiesen – ein gemeinsames System gibt es nicht.

`tests/test_situationen.py` prüft das gegen geschlossene Lösungen:
eingespannt-gestützter Balken (7PL³/96EI) gegen den Kragarm nach Abschalten
des zweiten Elements (PL³/3EI), Eigengewicht nur der wirksamen Elemente,
Kragarm um 90° hochgeklappt unter Vertikallast (PL/EA statt PL³/3EI). Für
den einzelnen Lastfall: Rolle am Ende in der Stellung abgebaut, PL³/3EI
bitgleich mit `solve_cases` (vorher 7PL³/96EI, 1,406 statt 6,429 mm); für das
Knicken: Kopfhalterung in der Stellung abgebaut, Kragstütze π²EI/(2L)²
(vorher eingespannt-gelenkig, 7,853 statt 0,9595 MN), und eine abgeschaltete
äußere Stabhälfte trägt nichts zur geometrischen Steifigkeit bei.

**Subsysteme** sind eine Gliederung des Modells (Elemente, Knoten, Linien,
Lager, Kontakte je Teil; Elemente an der Berührungsstelle gehören beiden);
sie ändern die Berechnung nicht.

## 3b Spannungsgrößen und Werteskala der Anzeige

`statik3d/spannungen.py`, geprüft in `tests/test_spannungen.py`

Die Anzeige färbt Knotenwerte. Jede Größe wird **je Element** aus dem
Ergebnis gebildet und **auf die Knoten gemittelt** (arithmetisches Mittel
der angrenzenden Elemente, `knotenmittel`, vektorisiert mit `np.add.at` —
für die 1,8 Mio. Elemente des Drehlagers Sekunden statt der Python-Schleife
von `Results.node_vm`). Volumen: aus dem Tensor der Elementmitte
(`Results.solid_res`, sx, sy, sz, txy, tyz, tzx) die Komponenten, die
Hauptspannungen nach Cardano (`ec3.fatigue.hauptspannungen`, vektorisiert),
σ_v = √(½[(σ₁−σ₂)² + (σ₂−σ₃)² + (σ₃−σ₁)²]), σ_int = σ₁ − σ₃ (Tresca) und
τ_max = σ_int/2. Flächen: aus den Schalenspannungen der Ober- und Unterseite
(`shell_derived`, sx, sy, sxy) die Komponenten, die ebenen Hauptspannungen
σ₁,₂ = (σ_x+σ_y)/2 ± √(((σ_x−σ_y)/2)² + τ²) und σ_v = √(σ_x² − σ_xσ_y + σ_y² +
3τ²); Seite „max“ nimmt je Element den Wert mit dem größeren Betrag,
vorzeichenbehaftet. Stäbe: aus den Stabendkräften σ_N = N/A,
σ_My = |M_y| z_max/I_y, σ_Mz = |M_z| y_max/I_z und die Randspannung
|σ_N| + σ_My + σ_Mz an beiden Enden — dieselbe Bildung wie `sig_max` der
Nachweise, nur je Ende.

**Kontaktdruck.** Die Kontaktbedingungen liefern Knotenkräfte F_n, |F_t| und
den Spalt (`ContactSystem.results`). Ein Druck braucht eine Fläche: die
**Einflussfläche** des Knotens auf der Kontaktfläche (`kontaktflaechen`).
Sie entsteht aus den Außenseiten der Volumen- und Schalenelemente, deren
Eckknoten alle Kontaktknoten sind — vektorisiert über die Seiten je
Elementtyp, innere Seiten (zweimal belegt) verworfen, Dreiecke zu einem
Drittel, Vierecke zu einem Viertel je Ecke. Damit ist Σ p·A = Σ F_n exakt
(Block mit Reibung: 90,00 kN = Auflast, Einflussflächen 0,1600 m² =
Grundfläche) und Σ τ·A = Σ |F_t| = 26,38 kN; das ist mehr als die
Horizontalkraft 20 kN, weil an haftenden Knoten die elastischen
Tangentialkräfte nicht alle parallel wirken — die Resultierende der
Kontaktkräfte bleibt 20,00 kN.

**Werteskala** (`Werteskala`, `grenzen`). Drei Modi: automatisch (Grenzen aus
den endlichen Werten), fest (unten/oben) und Grenzwert. Der Grenzwert G (355
für S355) spannt die Skala 0 … G auf, bei negativen Werten −G … G; Werte
darüber bekommen `above_color` Magenta, darunter `below_color` Cyan — beides
Farben, die in keiner Farbtafel vorkommen —, und die Skala trägt an dieser
Stufe den tatsächlichen Größt- bzw. Kleinstwert als Beschriftung. So ist
der oberste Eintrag das Maximum und der zweite die Grenze, wie es die
Vorgabe verlangt. Die Zahl der Farbstufen ist die von ANSYS (9, `n_colors`),
Beschriftungen an jeder Stufengrenze (`n_labels` = Stufen + 1). „Nur
Überschreitungen“ setzt alle Beträge ≤ G auf NaN (grau) und spannt die
Skala von G bis zum größten Betrag — die Überschreitungen behalten so ihre
Abstufung, statt alle in einer Farbe zu stehen. Die Einstellung liegt am
Modell (`Model.werteskala`) und wird mit ihm gespeichert. Geprüft: Werte
0/100/250/400 mit G = 355 → Skala 0 … 355, oben „400“, eine Überschreitung;
−400/−10/100 → −355 … 355 mit „−400“ unten; nur Überschreitungen → 400 bleibt,
Skala 355 … 400.

## 4 Kontakt

Kontakt wird mit einer Aktivmengen-Iteration berechnet. Für jede
Kontaktbedingung gilt der Spalt

    g(u) = g0 + cᵀ u,

c ist der Koeffizientenvektor der beteiligten Freiheitsgrade.

**Exakte Normalbedingung (seit 26.09.2026, `contact.EXAKTE_NORMALBEDINGUNG`).**
Eine geschlossene Bedingung ohne Feder des Anwenders erzwingt g = 0 **exakt**:
ihre Zeile c steht als Lagrange-Rand im Gleichungssystem, wie die
Hilfsfesselung (`StaticSystem.gerandet`),

    [ K   Cᵀ ] [ u ]   [ F   ]
    [ C   0  ] [ μ ] = [ −g0 ],

und die Kontaktkraft ist der Multiplikator λ = −μ ≥ 0 (Druck). Jede Zeile
ist mit der Diagonalsteifigkeit ihrer Knoten skaliert (dieselbe Größe, aus
der k_n entstand; je Zeile, nicht die größte im Modell, damit starre Teile
und Drehfreiheitsgrade der Stäbe die Zeile nicht verzerren), damit die
Pivotwahl nicht an Einträgen von 1 neben 10¹¹ hängt und das relative
Residuum der Löserprüfung auch ohne äußere Last einen Sinn hat
(Presspassung: rechte Seite nur das Übermaß). Das Sattelpunktsystem lösen MUMPS (SYM = 2),
PARDISO und SuperLU; CHOLMOD scheidet aus (positiv definit verlangt).
Die Aktivmenge entscheidet am Vorzeichen: eine geschlossene Bedingung
öffnet, sobald λ < −f_tol (f_tol = 10⁻⁶ der Bezugskraft ist die
Genauigkeit des Gleichungslösers, keine physikalische Schwelle); eine
offene schließt, sobald g < −tol. Nichts wird festgehalten. Das ist der
primal-duale semiglatte Newton (Hintermüller/Ito/Kunisch 2002;
Hüeber/Wohlmuth 2005) für den Normalkontakt; die Reibung bleibt darunter
Penalty in den zwei Phasen.

Warum nicht mehr die Feder: bis zum 25.09.2026 war jede Bedingung eine
Feder k_n c cᵀ mit k_n = 10⁴-fache Diagonalsteifigkeit (10¹³ bis 10¹⁵ N/m
am Drehlager), die Kraft F_n = −k_n g, und die Aktivmenge entschied am
Vorzeichen von k_n g. 0,5 kN „Zug“ sind bei diesem k_n ein Spalt von 10⁻¹¹
bis 10⁻¹³ m - Größenordnung dessen, was der direkte Löser an Vorwärtsfehler
lässt (Hypothese, am Drehlager-Endzustand noch nicht nachgemessen; der
Nachweis wäre ein Nachlösen mit anderem Löser und Nachiteration und der
Vergleich der Vorzeichen). An Randknoten der Fuge pendelte die Bedingung
jedenfalls, und nach acht Wechseln wurde sie aktiv festgehalten -
mit dem Zug, den sie gerade trug. Am Drehlager-Endzustand vom 25.09.2026:
980 festgehaltene von 13 536 aktiven, 809 davon unter Zug bis 1,6 kN (Median
54 N). Eine Schwelle (1 N/mm² Pressung, Lauf 26.09.) ließ in jedem
Kontaktblock 226 bis 436 davon stehen - sie kaschiert, sie heilt nicht.
Gemessen mit der exakten Bedingung (tests/test_kontakt_exakt, 26.09.2026):
Spalt geschlossener Bedingungen 0 (Feder: 1,4·10⁻¹⁰ m), Summe der
Multiplikatoren gleich der Auflast auf 10⁻⁹, Presspassung K3 σ = 355 N/mm²
auf 5·10⁻¹³ N/mm² in jedem Element, Prüfmatrix KP1 tet4 und KP2 (vorher rot)
grün; K1, K2, K3, KP1, KP2 ohne festgehaltene Bedingung.

**Haftfugen: die Schubbindung steht unabhängig vom Normalzustand
(`Constraint.bindung`, 26.09.2026).** Eine Fuge, die in ihrer Ebene starr
ist (RFEM: u_x, u_y starr, u_z Ausfall bei Zug — am Drehlager „Achse (Typ
4)“, „Montageauge (Typ 4)“, „Lagerbock Auge 1/2“), gleitet nie; ihre
Tangentialsteifigkeit k_t steht darum auch dort, wo die Normalbedingung
offen ist. Bis zu diesem Datum schaltete die Bindung mit dem Normalzustand:
öffnete ein Knoten, fiel mit ihm sein Schub weg, die Nachbarn übernahmen
ihn, und der Knoten drückte sich wieder in die Fuge. Gemessen am Drehlager
(LF1, Modell 25.09., exakte Normalbedingung, 16 Runden): ab Runde 8
pendelten je Runde rund 500 Bedingungen auf und 500 zu, 1 924 Bedingungen
wechselten mehrfach, 1 756 davon an haftenden Fugen; beim Öffnen trugen sie
im Median 2,8 N Zug, ihre Bindung aber 54 N Schub (Verhältnis 19, 10-%- bis
90-%-Quantil 5 bis 71). Mit stehender Bindung klangen die Wechsel ab:
12 218, 4 266, 2 392, 1 564, 1 072, 556, 200, 87, 55, 33, 36, 35, 51, 12,
13, 12 je Runde, 52 Bedingungen mit zwei Wechseln nach Runde 8, keine mit
vier. Ein offener, gebundener Knoten trägt seinen Schub weiter (Ergebnisliste
„gebunden“, Kraft in den Knotenkräften); ob das die Physik einer weit
geöffneten Haftfuge trifft, ist eine Modellentscheidung — sie entspricht
der Freigabe je Richtung, wie RFEM sie führt.

Federn des Anwenders (`stiffness` > 0, elastische Bettung) bleiben Federn:
dort ist die Feder die Physik, Durchdringung = F_n/k. Ebenso rechnet der
Hilfsschritt `stabilise` (kein Halt im ersten Schritt) mit Federn an der
jetzigen Lage. Gehaltene Bedingungen (`solver._freie_teile_halten`, ein Teil,
dessen geschlossene Bedingungen es nicht mehr halten) öffnen nicht unter Zug,
solange das Teil sonst nichts trägt. Ob es getragen wird, entscheidet seit
dem 26.09.2026 der **Rang** und nicht die Zahl: gehalten wird, bis die
geschlossenen Bedingungen und Bindungen so viele Starrkörperbewegungen des
Teils halten wie alle seine Bedingungen zusammen könnten (`_rang_zahl`,
Singulärwerte der Zeilen auf den sechs Moden über `SCHUB_GRENZE`); fünf
Bedingungen auf einer Linie halten die Kippung um die Linie nicht, und die
alte Regel „drei sind zu“ hielt dann nichts, Stufe 2 dagegen die halbe Fuge
samt der Reihe, die zog - der Block hing am Halt, hieß „hebt ab“, und die
Hilfsfesselung übernahm die Last (Reaktionen 144 statt 90 kN). Freigegeben
wird nach Zug geordnet, vom stärksten an, solange der Rang der übrigen
bleibt (`_halt_loesen`), und in einer Runde mit Freigabe wird sonst nichts
umgestellt: Freigabe und Öffnen im selben Schritt schossen über (kippender
Block auf der Haftfuge, tests/test_kontakt_exakt: jetzt 3 Schritte, Summe
der Multiplikatoren 90 kN auf 10⁻⁹). Hängt das Teil am Ende allein am Halt,
heißt das „hebt ab“ (tests/test_kontakthalt) - bei 20 kN Schub am Deckel
des Blocks zu Recht, seine Resultierende läge außerhalb der Fuge. Seit dem
27.09.2026 zählen in der Rangprüfung auch die **linearen Lager** des Teils
(feste und Federn aus Knoten-, Linien- und Flächenlagern, `_lagerzeilen`),
und ein Teil, das sich selbst hält (die starre Platte unter dem Block),
entscheidet nicht über den Halt des Nachbarteils.

**Ganz gleitende Reibgruppen: die Reststeifigkeit trägt keine Kraft mehr
(K5, 27.09.2026).** Bis dahin behielt eine Reibgruppe, deren aktive Knoten
alle gleiten, auch in Phase 2 die grobe Reststeifigkeit 10⁻³ k_t - „sie hält
das Bauteil“. Bei einer starren Bedingung ist k_t die 10⁴-fache
Diagonalsteifigkeit, der „Rest“ also das Zehnfache des Bauteils, und er
trug Kraft, die in keiner Kontaktkraft stand: am Klotz K5 der Prüfmatrix
86 bis 90 % dessen, was die Federn des Klotzes tragen sollten; am Stempel
mit gewölbter Unterseite (tests/test_plastizitaet) 211 kN - so viel wie die
Reibkraft selbst - gemessen als Last + Kontaktkräfte + Reaktionen je Teil;
am Klotz an der starren Knagge 21,5 von 100 kN Vertikallast. Jetzt
entscheidet der Rang (`solver._gruppen_frei`): halten die übrigen
Bedingungen, Bindungen und die linearen Lager des Teils (`_lagerzeilen`)
alle Starrkörpermoden auch ohne die Tangentialsteifigkeit der Gruppe, so
bekommt sie in Phase 2 die feine Reststeifigkeit mit Ausgleich, und die
Iteration geht für sie in Phase 2 (`gruppe_frei` im Kontaktsystem,
Signatur, Sicherung). Nur eine Gruppe, ohne die eine Bewegung frei bliebe,
behält die grobe Feder samt Warnung „Bauteil rutscht“. Gemessen: K5 hex8
Federkraft +0,21 % (vorher −86 %), tet4 +1,45 % (vorher −91 %); Stempel-Rest
107 N statt 211 kN, seine Verschiebung 0,4075 statt 0,3804 mm (die alte
Referenz war die federgehaltene); Knagge R = (50, 0, 100) kN. Drehlager LF1
(vier ganz gleitende Lagergruppen „Starr u_x/u_y“): u 1,2980 mm, ε_p
8,234 %, Bohrungen auf ±0,5 N/mm² wie zuvor, Schlussabnahme bestanden (Rest
6·10⁻⁹), 62 min; nur am Montageauge V35 367 statt 380 N/mm² (25.09.: 368)
und V115 231 statt 209 - dort trug die grobe Feder Kraft. Zwei Kuren
vorher verworfen: die Reststeifigkeit auf die Bauteilsteifigkeit beziehen
(Phase 1 verliert die Dämpfung, Block mit Reibung und Warmstart-Fixtures
laufen in den Deckel) und der Ausgleich an der groben Feder (Fixpunkt zu
langsam, K5 −79 %).

Was die grobe Feder verdeckt hatte: ein Körper, der ganz gleitet und in der
Ebene nur über Reibung auf gewölbter Fläche gehalten ist, ist mechanisch
indifferent. Am Stempel mit Fließen (zwei Körper, μ 0,1) erreichte der
verschachtelte Newton die Schlussabnahme zunächst nicht (Rest 4,6·10⁻³ bei
Toleranz 10⁻³, auch nach fünf Nachschritten vom Abschluss aus,
`plastizitaet.ABSCHLUSS_NACHSCHRITTE`), weil jeder Fließschritt den Kontakt
kalt begann und jeder volle Kontaktlauf die Reibung neu setzte; die
gemeinsame Iteration konvergierte (Rest 1,5·10⁻⁶). Seit der erste
plastische Lauf vom Zustand des Vorlaufs startet (27.09.2026 abends, siehe
„Warmstart als Regel“ unten) konvergiert auch der verschachtelte Weg: Rest
1,27·10⁻⁷ am Stempel mit zwei Körpern, 7,9·10⁻⁸ am Stempel mit einer
Laststufe. Die Reibzustände beider Wege bleiben am indifferenten Stempel
verschieden.

**Warmstart als Regel (27.09.2026).** Innerhalb eines Lastfalls startete
jeder erste Kontaktlauf eines Fließschritts kalt, sobald „viele“ gleitende
Knoten (mehr als ein Zehntel) sich gegen ihre festgehaltene Richtung
bewegten - am Drehlager mit dem Flächenlager „Starr“ als exakter Bedingung
(2 370 gleitende Knoten, deren Richtungen mit jeder Tangente wandern) je
Newton-Schritt 30 bis 48 Runden zu 25 s statt 3 bis 18 warm; und der erste
plastische Lauf begann immer kalt, weil der Zustand des elastischen
Vorlaufs nie weitergegeben wurde (Referenz `k5_probe2`: Lauf 2 mit 21
Runden noch einmal). Entscheidung des Anwenders: kalt nur, wenn unbedingt
nötig. Seither gilt innerhalb desselben Lastfalls (`solve_with_contact`,
`fortsetzung`: der Start ist der Zustand des Vorlaufs oder des vorigen
Fließschritts): Knoten gegen ihre Richtung werden auf Haften
zurückgesetzt und die Iteration wird vom Zustand aus fortgesetzt; kalt erst,
wenn die Fortsetzung selbst nicht konvergiert oder nichts mehr bringt. Ob
sie etwas bringt, sagt das Kraftmaß der Prüfung (unten) im Vergleich zum
vorigen Anlauf: fällt es nicht, ist die Fortsetzung ein Zyklus, und der Lauf
startet kalt („Warmstart verworfen: … Maß 2583 kN nicht unter 2578 kN des
vorigen Anlaufs - Neustart von der Geometrie“). Eine feste Zahl taugt dafür
nicht (gemessen 28.09.2026): drei Anläufe erzwangen am Drehlager
(`starr_warm2`) nach 10, 8, 4 und 2 Runden - fallend, mit fallendem Maß - den
kalten Start mit 35 Runden; acht blinde Anläufe am gequetschten Block
(`tests/test_plastizitaet`, 4 Laststufen) waren ab dem zweiten ein Zyklus
(3,84 - 2,58 - 2,58 - 3,83 - 2,58 MN, siebenmal dieselben drei Knoten am
Rand zwischen Ausbreiten und Querlast, deren Richtung als Fixpunkt kippt)
und brachten gemeinsam und verschachtelt 2,6 mm bei 42,7 mm auseinander.
`FORTSETZUNGEN_MAX` = 8 bleibt als Schutz vor Endlosrekursion bei
kriechendem Maß. Die
Prüfung selbst trägt seit dem 28.09. ein Kraftmaß: liegt die Reibkraft μ F_n
der Knoten gegen ihre Richtung zusammen unter 10⁻⁶ der Kontaktkraft
(`RESIDUUM_ANTEIL`), sind das Richtungen aus Rauschen - Bettungsknoten ohne
Normalkraft -, und der Zustand steht. Ohne das Maß fand der Lauf
`starr_warm` am Drehlager nach jeder Fortsetzung wieder solche Knoten und
startete nach drei Anläufen doch kalt: 10 + 8 + 5 + 2 + 35 Runden statt 10.
Ein Zustand vom Deckel (die Reibungsnachprüfung hat aufgegeben) zählt dabei als
fremd, und ein gedeckelter Vorlauf gibt gar keinen Zustand weiter - sonst
hinge das Ergebnis am Deckel (`tests/test_rechenliste`: mit Deckel im
Vorlauf und ohne treffen sich die Wege auf 7·10⁻²⁰ m; mit dem Deckelzustand
als Start lagen sie 3·10⁻⁹ m bei 3·10⁻⁶ m auseinander). Ein
**fremder** Zustand - Warmstart aus einem anderen Lastfall, eingefrorener
Zustand, der nicht passt - bleibt bei der alten Regel (wenige zurücksetzen,
viele heißen Neustart): am Block mit Reibung endete die Fortsetzung aus
einem fremden Zustand 0,6 bzw. 4 % (u_max) neben der kalten Lösung bei
gleichen Spannungen (0,04 N/mm²) - für die Ermüdung, die Zustände
vergleicht, wäre das ein Weg-Artefakt. Folgen in den Prüfungen: der Block
mit Reibung braucht verschachtelt 12 statt 17 Zerlegungen (gemeinsam 12),
zwei Körper 26 (gemeinsam 23); gemeinsam und verschachtelt treffen sich
auf 10⁻⁵ statt 10⁻⁶.
Seit der Reibung primal-dual (28.09.2026, unten) ist ein konvergierter
Zustand in sich stimmig - die Richtung kommt aus der Versuchskraft, wer
umkehrt, haftet -, und innerhalb desselben Lastfalls gibt es an diesen
Knoten nichts mehr zu prüfen. Einen **fremden** Zustand verraten Knoten, die
sich gegen ihre übernommene Richtung gedreht haben oder vom Gleiten ins
Haften fielen; für sie gilt die alte Regel. Am Block mit Reibung sind das
bei umgekehrter Last zwei Knoten - „wenige“, sie werden zurückgesetzt statt
kalt neu zu rechnen, und das Ergebnis trifft die kalte Lösung auf 1,3·10⁻⁵.

**Reibung primal-dual (28.09.2026, Prüfmatrix K4 und K5).** An exakten
Normalbedingungen (Abschnitt „Exakte Normalbedingung“) wird der Reibzustand
in Phase 2 wie der Normalkontakt aus Multiplikatoren bestimmt
(`contact.REIBUNG_PRIMAL_DUAL`, nach Hüeber, Stadler und Wohlmuth):

* **Versuchskraft** je Knoten w = λ_t + c·d_t mit dem Tangential­multiplikator
  λ_t, dem Weg d_t = C_t·u in der Fugenebene und c = k_n / PENALTY_FACTOR,
  der Diagonalsteifigkeit der Knoten.
* **Haften** (|w| ≤ μ·λ_n): zwei exakte Zeilen c_t·u = 0 im Sattelpunkt, λ_t
  ist ihre Reaktion; keine Haftfeder mehr.
* **Gleiten** (|w| > μ·λ_n): Reibkraft μ·λ_n·w/|w|, in K_c die konsistente
  Tangente c·μ·λ_n/|w| quer zur Richtung (Ableitung der Projektion nach d_t),
  als Feder auf die Änderung seit dem letzten Zustand. Die Richtung folgt je
  Runde der Versuchskraft; solche Richtungsrunden zählen nicht auf den Deckel
  der Zustandswechsel (Grenze 60 Runden). Die Reibkraft steht dazu als Spalte
  −μ·q am Multiplikator der Normalzeile im Gleichungssystem (q die Richtung
  der Tangente): so kommt eine geänderte Normalkraft in derselben Runde an
  (Block mit Reibung, LF3 nach LF2: 6 Runden ohne Zerlegung statt 22 mit 6).
  Das System wird damit unsymmetrisch; mit dem Gleichungslöser ama (LDL^T)
  entfällt die Spalte, und die Reibkraft läuft wie vorher eine Runde nach -
  dasselbe Ergebnis (8,3·10⁻⁶ gegen PARDISO).
* Lagerknoten mit Reibung in nur einer Richtung haben eine leere zweite
  Tangentialzeile; sie bekommen nur die belegte Haftzeile (eine leere machte
  das Sattelpunktsystem singulär). Zeilen, die ganz auf gesperrten
  Freiheitsgraden liegen, werden beim Aufbau genullt. Bis zum 28.09.2026
  abends fielen solche Knoten ganz aus der primal-dualen Reibung und
  rechneten mit der alten Logik, die in Phase 2 ein Gleiten gegen die
  Richtung stehen lässt: am Drehlager 26 Knoten des Flächenlagers
  „Starr uz (Ausfall bei Zug)“ (Diagnose mit Zerlegung des Residuums je
  Fuge und Art). Das Residuum blieb bei 2,2·10⁻⁴ der Kontaktkraft stehen,
  rund 20 kN Reibkraft zeigten in die falsche Richtung, der Lauf hieß
  trotzdem „konvergiert“, und erst die Warmstart-Prüfung am Laufende setzte
  sie zurück - die Schlussrunden, die am Drehlager Zeit kosteten
  (`tests/test_kontakt_exakt`, Reibung in einer Richtung, mit
  Rücknahmeprobe). Drehlager danach (Lauf `einzeilig_18a770d`, zwei
  Auswerter): 53,6 min statt 77,0, alle 18 Kontaktläufe konvergiert, keine
  Warmstart-Korrektur mehr, Runden je Lauf 37 / 8 / 6 / 3 / 9 … statt
  53 / 51 / 6 / 3 / 30 …, Residuum am Ende 0; ε_p 8,291 %, u_max 1,1507 mm,
  Bohrungen innerhalb 3 N/mm² des Laufs davor.
* Ausgenommen sind Fugen, in denen der Löser Punkte hält (gehalten,
  Schubhalt): ihr Reibzustand ist ein Artefakt des Halts. Ein ganz abhebender
  Block pendelte sonst 85 Runden zwischen Haften und Gleiten statt „hebt ab“
  zu melden. Ebenso zählt die Drehung einer Reibkraft unter f_tol nicht als
  Richtungsrunde.

Gemessen am Endzustand (`tests/test_kontakt_exakt`, Coulomb-Prüfung): die
Reibkraft liegt an jedem gleitenden Knoten parallel zu seinem Weg - höchstens
0,07° am Block mit Reibung, 0,00° am Stempel auf gewölbter Unterseite. Mit den
bis dahin in Phase 2 festgehaltenen Richtungen stand sie am Block bis 52°
daneben (Median 9°), am Stempel bis 180° (Median 47°). Folgen: Prüfmatrix K4
tet4 und hex8 grün (vorher quer −3,57 bzw. −2,49 % von μN, Feder +0,87 bzw.
+1,16 %), K5 tet4 grün (vorher Feder +1,45 %); Stempel auf Sockel u_max
0,39253 statt 0,40711 mm (−3,6 %), Block mit Reibung +0,06 %. Der gequetschte
Block (`tests/test_plastizitaet`, 60 MN über der Quetschlast von 37,6 MN)
gibt mit 1, 2, 4 und 8 Laststufen denselben Zustand, u_max 42,667 mm und
ε_p 12,99 %, symmetrisch (mittleres u_y des Deckels unter 10⁻⁷ m); mit den
festgehaltenen Richtungen hing er an der Teilung (42,25 / 42,34 / 42,66 mm)
und endete verschachtelt und gemeinsam in Spiegelbildern (u_y +0,94 bzw.
−0,71 mm). Dazu gehört das Halbieren weglaufender Laststufen (Abschnitt 5e).

Verworfen, jeweils gemessen am 28.09.2026: (1) die Quertangente ohne Rückkehr
ins Haften - die Richtungen kippten jede Runde, u_max 0,64 statt 0,043 m;
(2) ein kondensierter Newton-Schritt für die Richtung (Drehung über w hinaus
um μλ_n/(|w| − μλ_n)) - am Kegelrand ungültig, u_max 0,98 m, auch gedeckelt
nicht besser; (3) Unterrelaxation der Richtung (0,5 und 0,3) - der Zyklus
blieb; (4) „wer sich gegen seine Gleitrichtung bewegt, haftet“ - konvergiert,
aber auf einem anderen Ast, abhängig von der Teilung der Last (42,13 / 42,24
/ 42,58 / 42,67 mm für 1 / 2 / 4 / 8 Stufen); (5) Richtungen festhalten, wenn
das Residuum nicht mehr fällt, oder den Lauf dann abbrechen - beides nicht
nötig bzw. schädlich (Abbruch nach acht Runden schnitt langsam konvergierende
Nachführungen ab: sieben Halbierungen, 42,72 mm, mit einer Stufe „nicht
konvergiert“).

**Offen:** Bettungen und Federn des Anwenders (keine exakte Normalbedingung)
rechnen die Reibung weiter mit Haftfeder und festgehaltener Richtung in
Phase 2 - dort war die Versuchskraft ohne Multiplikator nicht tragfähig (der
Block auf der Platte mit Kippen lief mit ihr um das 230-Fache davon). Der
Gleichungslöser ama scheitert am Sattelpunkt des Stempels auf Sockel schon in
der ersten Kontaktrunde - vorbestehend, auch am Stand ec3b464.

**Mortar-Gewichte bei ungleichen Netzen (28.09.2026, Prüfmatrix K6,
`contact.MORTAR`, `statik3d/mortar.py`).** Die Kopplung Knoten gegen Fläche
projiziert jeden Slave-Knoten auf ein Dreieck der Master-Fläche (Vierecke
dafür geteilt) und verteilt seine Kraft mit den Dreiecksgewichten. Bei
ungleichen Netzen kommt ein gleichmäßiger Druck so nicht gleichmäßig an:
im Fall K6 (zwei Würfel, oben 3 × 3, unten 2 × 2 geteilt, p = 100 N/mm²)
bekamen die unteren Knoten 846 und 661 statt 625 cm² Einflussfläche an den
Ecken und 2255 statt 2500 in der Mitte, unsymmetrisch längs der
Dreiecksdiagonalen; σ_v lag 74,16 N/mm² (hex8) bzw. 13,56 N/mm² (tet4)
daneben. Jetzt kommen die Master-Gewichte eines Slave-Knotens j aus dem
Integral w_ji = ∫Φ_j N_i^m dA / ∫N_j dA über die Slave-Oberfläche, Φ_j die
dualen Formfunktionen der Slave-Facetten (∫_e Φ_j N_k = δ_jk ∫_e N_j je
Facette, Wohlmuth 2000), N_i^m die Formfunktionen der Master-Facetten -
Vierecke bilinear, nicht geteilt. Integriert wird über die Schnittpolygone
von Slave- und projizierter Master-Facette (Sutherland-Hodgman, je
Teildreieck 7 Punkte, Grad 5). Die Bedingung bleibt eine Zeile je
Slave-Knoten mit derselben Normalen und demselben Anfangsspalt wie bisher;
nur wer die Kraft auf der Master-Seite trägt, ändert sich. Für einen
gleichmäßigen Druck p trägt der Slave-Knoten p ∫N_j, und am Master-Knoten
kommt Σ_j p ∫N_j w_ji = p ∫N_i^m an, genau seine Einflussfläche (gemessen:
625 / 1250 / 2500 cm² auf 2,5·10⁻¹⁶ m²). Bei deckungsgleichen Netzen ist
w_ji = δ_ji (gemessen auf 3,9·10⁻¹⁵): Knoten auf Knoten wie bisher, die
Prüfmatrix K1–K5, K7, KP1, KP2 bleibt unverändert grün. K6 ist mit tet4 und
hex8 grün (σ_v 0,00 N/mm²). Knoten, deren Einflussbereich nicht ganz auf der
Gegenfläche liegt (Rand der Überdeckung), behalten die Projektion; Paare mit
quadratischen Elementen (Kontakt dort gesperrt) ebenso. Folge im Test: der
Stempel auf Sockel (4 × 4 gegen 6 × 6) u_max +0,33 %.
Am Drehlager (Lauf `mortar_81e7b64`, 28.09.2026, zwei Auswerter): 803
Slave-Knoten in sechs Fugen bekommen Mortar-Gewichte, die übrigen gepaarten
behalten die Projektion. Die Überdeckung Σ_i M_ji / D_j ist dort
zweigeteilt - je Fuge liegt sie entweder auf 10⁻⁶ bei 1 (Median meist um
10⁻¹³) oder mehr als 1 % daneben, dazwischen fast nichts -, also entscheidet
nicht die Toleranz, sondern ob der Einflussbereich eines Knotens ganz auf der
Gegenfläche liegt. Offen: Knoten mit teilweiser Überdeckung auf den
überdeckten Teil zu beschränken (w = M_ji / Σ_i M_ji) - erst mit einem
Prüffall mit Rand der Überdeckung. Ergebnis gegen den Stand ohne Mortar:
alle Kontaktläufe konvergiert, ε_p 8,291 %, u_max 1,1504 statt 1,1496 mm,
Bohrungen innerhalb 1,5 N/mm² außer dem Montageauge V35 379,8 statt 373,6
und V115 210,7 statt 215,2 N/mm² - dort liegen die meisten Mortar-Knoten.
Aufbau der Gewichte für alle zwölf Paare rund 26 s.

**Flächenlager „starr mit Ausfall“ (27.09.2026).** RFEM lässt „starr“ nur
ohne Nichtlinearität zu; ein Lager mit Ausfall bei Zug trägt dort einen
Federwert - am Drehlager 2,5·10¹¹ N/m³ für das Lager „Starr“. Nach
Entscheidung des Anwenders gilt eine solche Bettung ab
`supports.BETTUNG_STARR` = 10¹¹ N/m³ als starres Lager mit Ausfall (exakte
Bedingung; `supports.bettung_als_starr`, auch im RFEM-Import, Protokollzeile).
Echte Bettungen liegen Größenordnungen darunter (Boden 10⁷ bis 10⁸,
Elastomer 10⁹ bis 10¹⁰). Belegt am Klotz an der Knagge (tests/test_supports):
R = (50, 0, 100) kN - erst seit der Kur für K5 oben, vorher 78,5 kN.

**Die Abhebekante des starren Flächenlagers pendelte (27.09.2026).** Mit der
Regel stand Lauf 1 des Drehlagers 30 Runden bei Δu 10⁻³ (mit der Bettung als
Feder war er nach 18 fertig; dort hielten 244 festgehaltene Federn still).
Die Zyklus-Diagnose (Öffnen und Schließen je Bedingung mitgeschrieben,
`scratchpad/drehlager_zyklus.py`): 250 Bedingungen wechselten ab Runde 8 im
Takt von zwei bis drei Runden, 203 davon Knoten der Bettung „Starr“ (147
mit μ 0,1), die übrigen Nachbarn in Deckel und Montageauge; Zug beim Öffnen
5 bis 50 N, Durchdringung beim Schließen 0,5 bis 1 nm - beides nichts gegen
die Lasten, aber jenseits von f_tol und tol, und die Aktivmenge fand nicht
zur Ruhe. Zwei Kuren, nacheinander gemessen:

1. *Liniensuche fürs Öffnen und Schließen* (`contact.WECHSEL_ANTEIL_MIN`):
   wie beim Gleiten in Phase 2 stellt eine Runde nur den Anteil der
   wechselwilligen Bedingungen um, stärkster Verstoß (Zug bzw.
   Durchdringung mal örtliche Steifigkeit, als Kraft) zuerst; fällt das
   Verstoßmaß nicht um ein Zehntel je Runde, halbiert sich der Anteil,
   sonst verdoppelt er sich bis 1. Solange das Maß fällt, ist das der
   gewöhnliche primal-duale Schritt (Prüfmatrix K1 bis KP2 unverändert,
   Stumpftest in `test_kontaktzustand`). Am Drehlager **allein zu wenig**:
   nach 40 Runden noch 226 Pendler, der Anteil pendelte mit dem Maß mit.
2. *Die Ausgangslage ist kein Anker für einen Knoten, der abgehoben hat*
   (`Constraint.wieder_zu`). Der Mechanismus stand im Quelltext: ein
   Reibknoten, der nach dem Abheben wieder schließt, hat den Weg seines
   Bauteils in der Fugenebene mitgemacht. Seine Haftfeder k_t (starr: die
   10⁴-fache Diagonale) auf diesen Weg ließ ihn in derselben Runde gleiten
   (μ F_n = 0), und die grobe Reststeifigkeit der Phase 1 (10⁻³ k_t, das
   Zehnfache des Bauteils) zog ihn ohne Ausgleich mit demselben Weg in die
   Ausgangslage - Hunderte kN aus einem Knoten ohne Normalkraft, die die
   Nachbarn an der Abhebekante um eben jene 5 bis 50 N verschoben. Mit der
   Bettung als Feder war k_t die 10⁴-fache Federsteifigkeit 2,5·10⁷ N/m,
   nichts gegen das Bauteil - darum fiel es dort nicht auf. Seither bekommt
   ein Knoten, der in diesem Lauf nach dem Abheben geschlossen hat, den
   Ausgleich (`dt_last`) auch an der groben Feder; Knoten, die nie abhoben,
   behalten den Anker (die Dämpfung der Phase 1), ebenso eine ganz gleitende
   Gruppe ohne anderen Halt. Gemessen am Drehlager, Kur 2 allein (40 Runden
   Diagnose): Pendler ab Runde 8 noch 58 statt 250, davon Bettung 9 statt 203,
   keine Bedingung mit mehr als drei Wechseln (vorher 189 mit vier und mehr);
   das Verstoßmaß fiel von Runde 8 bis 19 um vier Zehnerpotenzen auf 10⁻⁶
   (Aktivmenge 12 630 statt 13 150). Was bleibt, ist ein Tröpfeln von ein
   bis zwei Wechseln je Runde in den Fugen Deckel 1 und Montageauge auf dem
   Niveau von f_tol (Maß 10⁻⁷ bis 10⁻⁶), getrieben von einzelnen
   Haft-Gleit-Wechseln (gleitende Knoten 2367 bis 2372) - es hielt Phase 1
   bis Runde 40 offen; im vollen Lauf endete Phase 1 nach 29 Runden, und
   Phase 2 tröpfelte weiter (Runden 32 bis 50 je ein bis zwei Wechsel,
   jede eine Faktorisierung, auf den Deckel von 40 zu). Verworfen: die
   Landelage als fester Anker (`dt_ref`) - pfadabhängig, und der
   Warmstart-Test brach; der Ausgleich für **alle** Knoten der Phase 1 - er
   änderte die Gleitrichtungen des Blocks auf der Platte, LF2 verwarf den
   Warmstart (14 statt 10 Schritte).
3. *Ein Maßstab fürs Öffnen und Schließen* (`_durchdringungskraft`). Die
   Folgen der letzten Pendler zeigten Schließungen bei „0,0000 µm“
   Durchdringung: geschlossen wurde bei g < tol = 10⁻¹²·Modellgröße
   (2·10⁻¹² m), geöffnet bei Zug über f_tol = 10⁻⁶·max|F| (1 N). Mit der
   Diagonale 2·10¹⁰ N/m entsprach tol 0,04 N - das Schließen war 25-mal
   schärfer als das Öffnen. Ein Knoten schloss auf 10⁻¹¹ m, zog in der
   nächsten Runde mit 1 N, öffnete, und sein Nachbar schloss. Seither
   schließt eine offene Bedingung, wenn ihre Durchdringung als Kraft
   (Spalt mal Diagonale bzw. Feder) über f_tol liegt - derselbe Maßstab wie
   beim Öffnen; `tol` bleibt für die Berührung am Anfang und die Entlastung
   beim Fließen. Suiten und Prüfmatrix K1 bis KP2 unverändert. Am
   Drehlager stand Lauf 1 trotzdem nach 40 Runden noch in Phase 1
   (Aktivmenge 12 612 bis 12 619, Δu 10⁻⁵).
4. *Der Zustand steht, wenn das Residuum unter der Lösergenauigkeit liegt*
   (`RESIDUUM_ANTEIL` = 10⁻⁶). Die Diagnose mit den Ereignisfeldern der
   Rundenablage (45 Runden) nannte das Tröpfeln: ab Runde 18 je Runde null
   bis drei Öffnen/Schließen und null bis zwei Haft-Gleit-Wechsel mit
   Verstößen von 10⁻⁶ bis 10⁻⁵ der Bezugskraft (1 bis 10 N), dazu 4 bis 15
   Richtungsnachführungen gleitender Knoten (> 3°), und jeder dieser
   Wechsel hielt Phase 1 offen (Runden 32 bis 45: nur noch „ri 8, 8, 8, 4,
   6, 4“). Bis dahin endete eine Phase erst, wenn eine Runde **gar nichts**
   umstellte. Jetzt summiert der Vorpass alle Verstöße der Lösung als
   Kraft - Zug an geschlossenen, Durchdringung an offenen (mal örtliche
   Steifigkeit), Kegelüberschreitung haftender Knoten und die Reibkraft
   gleitender Knoten, die sich gegen ihre Richtung bewegen - und vergleicht
   sie mit der Kontaktkraft (Summe der Druckkräfte). Liegt die Summe unter
   10⁻⁶ davon, stellt die Runde nichts um, führt keine Richtung nach und
   meldet keinen Wechsel: die Lösung u ist die Lösung, das Protokoll sagt
   „Verstöße unter der Lösergenauigkeit - Summe … N bei … kN Kontaktkraft,
   der Zustand steht“. Das ist derselbe relative Maßstab wie f_tol
   (10⁻⁶ der größten Knotenlast) für eine einzelne Bedingung, angewandt auf
   die Summe; ein Verstoß darüber wird weiter umgestellt. Stumpftest in
   `test_kontaktzustand` (Zug 0,004 N und Durchdringung 0,004 N bei 10 kN
   Kontaktkraft stehen, 0,024 N wechseln; Kegel 0,004 N bleibt haften,
   0,05 N gleitet; ohne Kontaktkraft keine Ruhe). Suiten und Prüfmatrix
   K1 bis KP2 unverändert. Eine Folge im Kleinen: gemeinsame und
   verschachtelte Iteration von Fließen und Kontakt (5e.3) treffen sich am
   gequetschten Block nicht mehr bitgleich, sondern auf 1,2·10⁻⁹ m bei
   u_max 1,5·10⁻³ m - zwei Wege, die beide beim Residuum 10⁻⁶ enden, enden
   bis auf diese Genauigkeit gleich (Bisektion: nur mit dem Residuum
   ausgeschaltet wieder bitgleich; `tests/test_plastizitaet` prüft seither
   auf 10⁻⁶ relativ). Der Block mit Reibung braucht 6 statt 7 Zerlegungen.

Die Liniensuche bleibt als Sicherung im Programm: solange das Maß fällt,
greift sie nicht.

**Voller Lauf mit allen vier Änderungen (Nachtlauf `starr_nacht`, 27./28.09.,
Stand 695843d, 12 Arbeiter):** 9,4 h, Plastizität konvergiert mit ε_p
8,29 % (Referenz 8,23 %), Bohrungen V15/V34/V16/V29 359/359/356/354 N/mm²
(25.09.: 364/366/356/355), V35 366 (368), V115 209 (193); u_max 1,150 mm
statt 1,298 mm - die Differenz ist die Nachgiebigkeit der Bettung
2,5·10¹¹ N/m³, die als starres Lager entfällt (rund 2,5 kN je Knoten bei
2,5·10⁷ N/m). Aber: 9 von 18 Kontaktläufen brachen ab (Läufe 7 bis 10, 16
bis 18 am Deckel, 14 und 15 bei 120 Schritten), 1 187 Zerlegungen, alle
Läufe nach dem Vorlauf kalt (Neustart, alte Warmstartregel). Die
Rundenablage nannte zwei Mechanismen, beide am 28.09. behoben:

5. *Der Halt-Status ganz gleitender Gruppen steht ab Phase 2 fest.* In
   Lauf 7 wechselten nach drei ruhigen Runden die vier Lagergruppen ihren
   Status („ganz rutschend“ 4 → 0): eine einzige Öffnung änderte den Rang,
   die Reststeifigkeit der Gruppen sprang um 10⁵, und die nächste Lösung
   riss 277 Bedingungen um (haftende Knoten 58 → 370, 349 Kegelverstöße,
   Gütemaß 2·10⁴) - der Deckel. Seither bestimmt `solver._gruppen_frei` den
   Status nur in Phase 1 und in der Übergangsrunde; ab Phase 2 steht er wie
   die Gleitrichtungen (`tests/test_supports`, Klotz an der Knagge: nach
   der Übergangsrunde kein Aufruf mehr, Rx 50 kN, Rz 100 kN unverändert).
6. *Wiederschließen gleitet sofort, auch in Phase 2.* Ein Knoten, der in
   derselben Runde wieder schließt, trägt die Haftfeder k_t auf dem
   absoluten Weg, den er offen mit dem Bauteil zurückgelegt hat - ein
   Scheinverstoß, der in Phase 2 in die Liniensuche der Kegelverstöße ging
   (Anteil 0,02 bis 0,5 je Runde): in Lauf 7 je Runde 36 bis 55 solcher
   Knoten („Gleiten nach Wiederschließen“), die den Deckel füllten. Seither
   gleitet er in derselben Runde, wie in Phase 1 (`test_kontaktzustand`:
   zwei wieder geschlossene gleiten sofort, zehn haftende Verstöße weiter
   anteilig). Suiten und Prüfmatrix K4/K5/K7/KP1/KP2 unverändert.

Arten:

* **Einseitiges Lager** (nur Druck): Stützrichtung n, Spalt, optional
  Federsteifigkeit und Reibung.
* **Spaltelement** (Knoten–Knoten): Richtung aus Geometrie oder vorgegeben,
  Anfangsspalt.
* **Knoten–Fläche**: Slave-Knoten werden auf die nächste Facette der
  Master-Oberfläche (Schalen, Volumenoberflächen oder explizite Facetten)
  projiziert (nächster Punkt auf dem Dreieck); die Verschiebung der
  Facette wird mit baryzentrischen Gewichten interpoliert.

Reibung (Coulomb): Bei Haften wirkt eine tangentiale Penalty-Steifigkeit
k_t = k_n; überschreitet die Tangentialkraft μ F_n, gleitet der Knoten mit
der konstanten Reibkraft μ F_n entgegen der Gleitrichtung. Das Verfahren ist
eine elastisch-plastische Näherung ohne Lastgeschichte und für monoton
aufgebrachte Lasten geeignet. Die Iteration läuft in zwei Phasen:

1. **Aktivmenge und Gleitrichtungen.** Gleitende Knoten behalten eine
   Reststeifigkeit von 10⁻³ k_t (Regularisierung), die Gleitrichtung wird
   unterrelaxiert nachgeführt, Knoten mit Bewegung entgegen der
   Gleitrichtung haften wieder. Die Phase endet, wenn sich kein Zustand
   (offen / Kontakt / Haften / Gleiten) mehr ändert. Bedingungen, die mehr
   als achtmal wechseln, werden als aktiv festgehalten und im Protokoll
   vermerkt.
2. **Nachprüfung.** Die Reststeifigkeit wird auf 10⁻⁸ k_t abgesenkt, so
   dass an gleitenden Knoten exakt μ F_n wirkt; die Gleitrichtungen bleiben
   fest. „Exakt“ war das bis zum 25.09.2026 nicht: k_t ist
   eine Penalty-Steifigkeit von der Größenordnung 10¹⁵ N/m, und 10⁻⁸ k_t
   mal dem Gleitweg trug am Ende Kraft, die in keiner Kontaktkraft stand —
   am Klotz K4 der Prüfmatrix (hex8, 14,5 mm Schlupf gegen Federn) 693 kN
   oder 2,3 % von μ N, gemessen als K u an den Gleitknoten gegen
   `contact_forces`; die Federkraft lag darum 3,5 % (tet4: 10 %) unter
   H − μ N. Seither wirkt die feine Reststeifigkeit nur auf die **Änderung**
   der Tangentialverschiebung seit dem letzten Zustand (`Constraint.dt_last`,
   Ausgleich im Kraftvektor): am Ende trägt sie nichts, K u und
   `contact_forces` stimmen überein (K4: 29 826 kN beide, Federkraft +1,2 %).
   Die grobe Feder der Phase 1 und einer ganz gleitenden Gruppe ohne anderen
   Halt bleibt ohne Ausgleich — sie hält das Bauteil, und ihr Fixpunkt wäre
   mit Ausgleich zu langsam; dort steht weiter die Warnung „Bauteil rutscht“
   (anderswo gehaltene Gruppen: seit 27.09.2026 die feine Feder, K5 hex8
   grün; Knoten, die nach dem Abheben wieder schließen: Ausgleich auch an
   der groben Feder, siehe oben „Die Abhebekante des starren Flächenlagers
   pendelte“). Offen:
   die festgehaltene Gleitrichtung lag an einem Eckknoten von K4 20° neben
   der Bewegung (2,5 % von μ N quer zur Last, 0,7 mm Seitenwanderung); eine
   Nachführung in Phase 2 ist als Fixpunkt instabil (weiche Querhaltung:
   der Fehler verdoppelt sich je Runde) und braucht die konsistente Tangente
   μ F_n/|Δt| quer zur Gleitrichtung. Schalter `AUSGLEICH_RESTSTEIFIGKEIT`
   für die Rücknahmeprobe (`test_solver_ext`). Je Runde geht nur der am stärksten über der Reibgrenze liegende
   haftende Knoten ins Gleiten über (monoton, deshalb ohne Flattern), bis
   |F_t| ≤ μ F_n an allen haftenden Knoten gilt. Anschließend laufen
   Setzrunden, bis sich die Normalkräfte in μ F_n nicht mehr ändern.

Ergebnis: Die ausgewiesenen Kontaktkräfte stehen mit den Lasten im
Gleichgewicht (Summe der Reibkräfte = Horizontallast), an gleitenden Knoten
ist |F_t| = μ F_n, an haftenden |F_t| ≤ μ F_n. Weil die Gleitrichtungen der
Nachprüfung fest bleiben, urteilt das Verfahren nahe der Reibkapazität
μ ΣF_n konservativ: Oberhalb von etwa 80 % kann es „rutscht“ melden, obwohl
die Kapazität rechnerisch noch nicht erreicht ist. Gleiten alle aktiven
Knoten einer Kontaktgruppe, hält nur die grobe Reststeifigkeit das Bauteil;
das wird als Warnung „Bauteil rutscht“ gemeldet. Hebt ein Bauteil
vollständig ab, existiert kein statisches Gleichgewicht; das wird als Fehler
mit Hinweis gemeldet.

### 4.0 Kontaktfugen ausführen (RFEM: Flächenfreigaben)

Eine **Kontaktbedingung** sagt, dass zwei Bauteile an einer Fläche nicht
durchverbunden sind: sie liegen aufeinander, können abheben, vielleicht
gleiten. Gelesen wird sie aus der Quelldatei; sie muss aber auch **ausgeführt**
werden, sonst rechnet das Modell an der Fuge durchverbunden – also zu steif –
und überträgt dort Zug, wo in Wirklichkeit ein Spalt aufgeht.

RFEM legt die Fuge so ab: `releasedSolids` nennt den gelösten Körper,
`releasedSurfaces` **dessen ganze Außenhaut** und `assignedToObjects` die
Flächen, an denen die Freigabe hängt — und das ist die Fuge. Nicht die
Außenhaut: an einer Grundplatte sind das 36 Flächen über 1,65 m², von denen nur
ein Bruchteil an einer Fuge liegt (siehe Schnittstellenhandbuch, „Zwei Listen —
und welche die Fuge ist“). Die Fugenflächen des gelösten Körpers werden darum
gesucht: seine Randseiten, die auf den zugeordneten Flächen liegen. Der
Vernetzer teilt Knoten nur über **dieselbe**
Fläche; zwei Bauteile mit je eigener Fugenfläche teilen deshalb nur die Knoten
ihrer gemeinsamen **Randlinien**. Daraus folgen zwei Fälle:

| Netze an der Fuge | Woran man es erkennt | Umsetzung |
|---|---|---|
| passen Knoten für Knoten | **jeder** Fugenknoten gehört beiden Bauteilen | Knoten verdoppeln, je Paar ein Spaltelement (und Kopplungen für die Fugenebene) |
| passen nicht | nur der gemeinsame Rand gehört beiden (oder gar kein Knoten) | den Rand trennen, die Fläche über ein **Kontaktpaar** (Knoten–Fläche, Abschnitt 4) |

**Starr in allen drei Richtungen ist eine Schweißnaht** (seit 15.09.2026).
Eine Bedingung, die Zug, Druck und Schub überträgt (Standardkontakt
„Verbund“), trennt an **gemeinsamen** Flächen nichts: die Knoten zu
verdoppeln und mit unendlich steifen Kopplungen wieder zu verbinden ergäbe
dasselbe Modell mit mehr Unbekannten. Die Knoten bleiben gemeinsam, die
Bedingung gilt ohne Ausführung als „verschweißt“ und ist nie „zu steif“. Sie
darf auch gar nicht den normalen Weg gehen: der löst den Körper samt seiner
angeschweißten Nachbarn — am Drehlager sind die Rippen um den Lagerbock ein
geschlossener Ring, über den der Gegenkörper selbst in die gelöste Gruppe
kam, und dann fand die Fuge keine Gegenseite mehr („keine Gegenfläche im
Suchradius“, 22 von 25 automatischen Kontakten, 15.09.2026). Ebenso bleibt
eine starre Bedingung bei Knoten für Knoten passenden Netzen ohne Trennung. Für die verschweißte Gruppe
eines gelösten Körpers und für den Kerbfall der Naht zählt so eine Bedingung
wie keine — sonst löste jeder der automatischen Kontakte, die das Programm an
jeder Berührung zweier Volumen anlegt (Benutzerhandbuch, „Kontakte entstehen von
selbst“), am Drehlager die angeschweißten Rippen vom Lagerbock. Bei nicht
passenden Netzen (je eigene, aufeinanderliegende Flächen) bleibt es beim
Kontaktpaar mit Zug und Haften. Geprüft in `tests/test_fugen.py`
(`test_naht_bleibt_verschweisst`: kein Knoten verdoppelt, Dehnung unter Zug
wie durchverbunden; `test_naht_loest_nachbarn_mit`).

**Die Gegenseite sind die genannten Gegenflächen.** Nennt die
Kontaktbedingung Gegenflächen — so kommt jede RFEM-Flächenfreigabe herein
(die zugeordneten Flächen), und so wählt man sie in der Maske —, dann besteht
die Gegenseite des Kontaktpaars **nur** aus den Randseiten dieser Flächen;
Kontakt wirkt nirgends sonst (seit 15.09.2026). Bis dahin wurde geometrisch
gesucht, zuletzt im Bauteil der genannten Flächen, weil die Liste als
unvollständig galt. Gemessen am Drehlager (LF1) trifft das nicht zu: die
genannten Flächen decken jede der zwölf Fugen zu 90,6 bis 100 % der gepaarten
Gegenseite, und was daneben trug, lag auf Nachbarflächen desselben Bauteils —
in „Achse (Typ 3)“ 109 kN auf den Bohrungsstreifen F319/F320/F587/F588 neben
den genannten F304/F305/F589/F590, in „Montageauge (Typ 1)“ 2 kN auf F226.
Noch früher lief die Suche über das ganze Modell und nahm, was im Suchradius
am nächsten lag: vier Knoten der Achse V30 hingen an einem Passstift (V76)
statt an der Buchse und trugen 37 von 49 MN, 12,9 MN auf einem einzigen Knoten
(14.09.2026). Geprüft in `tests/test_fugen.py`:
`test_gegenseite_nur_auf_genannten_flaechen` (ein Bauteil mit zweigeteilter
Oberseite, genannt ist eine Hälfte — vorher lagen 30 von 57 Gegenfacetten auf
der anderen) und `test_gegenseite_nur_im_genannten_bauteil`.

**Spätere Fugen nehmen die Gegenseite früherer mit.** Die Fugen werden
nacheinander ausgeführt; jede verdoppelt die Knoten, die ihr gelöstes Bauteil
mit anderen teilt, und hängt dessen Elemente an die Kopien. Löst eine spätere
Fuge genau das Bauteil, auf dem ein früher angelegtes Kontaktpaar seine
Gegenseite hat, bekommen dessen Randfacetten dort neue Knotennummern — das
Kontaktpaar hielt aber die alten, und die gehören danach dem Nachbarn. Am
Drehlager lagen so 58 bis 73 Gegenfacetten in vier Fugen halb auf dem einen
und halb auf dem anderen Bauteil, ohne dass ein Element sie als Seite hatte:
„Deckel 2 (Typ 1)“ etwa mit zwei Knoten der Achse V30 und einem des
Passstifts V101, nachdem „Achse (Typ 4)“ die Achse von den Stiften gelöst
hatte (8 kN in LF1 auf solchen Facetten in „Deckel 2 (Typ 3)“). Jetzt zieht
die Fuge beim Verdoppeln die Gegenfacetten aller bestehenden Kontaktpaare
nach — aber nur die, die mit den neuen Nummern Seite eines Elements des
gelösten Bauteils sind; eine Facette des Nachbarn behält ihre Knoten.
Slave-Knoten brauchen das nicht: eine Fuge verdoppelt jeden Knoten ihrer
Kontaktseite, den ein anderes Bauteil mitbenutzt, danach gehört er dem
gelösten Bauteil allein, und keine spätere Fuge findet ihn noch gemeinsam
(am Drehlager 0 von 32 128 Slave-Knoten fremd). Geprüft in
`test_gegenfacetten_folgen_dem_bauteil`: vorher waren 8 von 28 Gegenfacetten
keine Seite eines Elements ihres Bauteils mehr.

**Ohne genannte Gegenflächen** wird die Gegenseite des Kontaktpaars über die
Geometrie gesucht — unter den Gegenkörpern oder allen anderen Bauteilen —, wie
in ANSYS über einen **Suchradius** (Pinball):
eine Randfacette eines anderen Bauteils gehört zur Fuge, wenn ihre Normale der
Kontaktfacette entgegen zeigt (n·n′ < −0,7) und der **nächste Punkt auf ihr**
höchstens den Suchradius von der Kontaktfacette entfernt liegt. Maßgebend ist
der nächste Punkt, nicht der Schwerpunkt der Gegenfacette: nur so findet ein
2-mm-Netz eine 15-mm-Gegenseite, ein Zylinder seine Bohrung mit Spiel, und
deckungsgleich müssen die Flächen nicht sein. Der Suchradius ist vorgebbar,
sonst die größere mittlere (Median-)Kantenlänge beider Seiten.

**Der Spalt wird längs der Normalen gemessen.** Der Abstand zweier Facetten
zerfällt in einen Anteil senkrecht zur Fuge und einen quer dazu. Nur der erste
ist ein Spalt; der zweite ist Versatz **in** der Fugenebene und bedeutet kein
Abheben. An einem gestuften Anschluss steht eine Flanke des einen Teils
regelmäßig über die des anderen hinaus — im Raum gemessen käme dort ein Spalt
von Zentimetern heraus, obwohl beide Flanken in derselben Ebene liegen und
sich berühren. Am Lagerbock des geprüften Drehlagermodells (V14 gegen V36,
2634 Facetten) waren das:

| Maß | Median | 99 % | größter |
|---|---|---|---|
| Abstand im Raum | 0,000 mm | 28,9 mm | 34,4 mm |
| Abstand längs der Normalen (**der Spalt**) | 0,000 mm | 0,000 mm | 11,5 mm |
| Querversatz | 0,000 mm | 28,9 mm | 34,4 mm |

252 der 271 auffälligen Facetten haben einen Normalabstand unter 0,1 mm: sie
liegen an. Damit eine Facette überhaupt eine Gegenseite hat, muss sie auf ihr
liegen — steht ihr Schwerpunkt weiter als ihren eigenen Umkreis über den Rand
der Gegenfacette hinaus, ist dort nichts mehr, was ihr gegenübersteht, und sie
bleibt ungepaart. Die Randfacette einer Fuge, die zur Hälfte über die Kante
ragt, bleibt so dabei. **Gewählt** wird unter den so verbliebenen Gegenseiten
die räumlich nächste; **gemessen** wird längs der Normalen.

**Im Löser wirkt Kontakt nur auf der Gegenfläche.** Für die Zuordnung Knoten
gegen Master-Facette galt bis zum 15.09.2026 dieselbe Umkreisregel — für einen
**Knoten** heißt sie aber: Kontakt jenseits des Flächenrands. Am Drehlager
trugen so Knoten der Achse bis 25 mm hinter dem Ende der Buchse V29 1982 kN
und 8 mm hinter dem Ende von V16 903 kN; am Montageauge trug der Rand eines
Passstiftlochs, 3 mm hinter dem Stiftende, 708 kN auf einem Knoten. Neben der
ganzen Gegenfläche — keine Randseite des Gegenkörpers darunter — lagen
tragende Knoten in elf von zwölf Fugen. Jetzt wird ein Knoten nur einer
Facette zugeordnet, auf die er **senkrecht fällt**: sein Querversatz q zur
Facette muss

$$ q \le \varepsilon\,L + \tan\frac{\kappa}{2}\; d $$

erfüllen, mit dem Abstand d längs der Normalen, der Rundungsschranke
ε L = 10⁻⁶ der Modellgröße und dem Knickwinkel κ = 30° der glatten
Nachbarschaft. Der zweite Term ist der Kegel einer glatten Kante: steht ein
Knoten um d vor der gemeinsamen Ecke zweier Facetten, die um den Winkel D
abknicken — am Mantel einer Achse jede Ecke —, liegt er neben beiden um
d sin(D/2) bei einem Abstand d cos(D/2), also bis D = κ innerhalb der Schranke.
Ein anliegender Knoten (d = 0) bekommt nichts nachgelassen. Wer daneben liegt,
bekommt keine Bedingung und trägt nicht; das Protokoll zählt diese Knoten
getrennt von denen ohne Facette im Suchradius. Geprüft an einer ebenen Fläche
(jeder Knoten bis zum Rand gepaart, 2,5 bis 30 mm dahinter keiner) und an 48
Fällen Achse/Bohrung über 16, 24 und 36 Facetten, 40 und 57 Knoten, Versatz,
Spiel 0 und 0,5 mm und beide Seiten als Gegenfläche (`tests.test_fugen`,
`test_kontakt_nur_auf_der_gegenflaeche`); mit der alten Regel standen dort je
Fall 240 Knoten hinter dem Ende der Bohrung in Kontakt.

**Formschluss statt Reibung.** Eine Kontaktfuge trägt nur senkrecht zu ihren
Facetten. Ob ein Bauteil ohne Reibung frei gleiten kann, entscheidet darum die
**Form** der Fuge und nicht ihre Einstellung. Gemessen wird die
flächengewichtete Streuung der Normalen

$$ M = \frac{\sum_i A_i\,n_i n_i^{\mathsf T}}{\sum_i A_i} $$

Die Eigenwerte von M sind die Anteile, mit denen die Fuge in ihren drei
Hauptrichtungen trägt. Eine ebene Fuge hat 1 / 0 / 0 — in ihrer Ebene hält
nichts. Ein Absatz, eine Nut oder eine Bohrung haben drei Eigenwerte über
null: sie halten seitlich durch ihre Form, ganz ohne Reibung. Die Fuge des
Lagerbocks hat 0,779 / 0,127 / 0,094 (z, x, y) — die 12,7 % und 9,4 % sind die
Flanken des Absatzes. Ab einem Anteil von 2 % (``fugen.FORMSCHLUSS_MIN``) gilt
eine Richtung als gehalten; das Protokoll nennt die Anteile und warnt nur noch
dort, wo wirklich nichts hält.

**In zwei Durchgängen.** Welche Facetten zur Gegenseite gehören, weiß man
vorher nicht — gesucht wird gegen die Randseiten *aller* anderen Bauteile, und
deren Median ist die Netzweite des **Modells**, nicht die der Fuge. Der Median
hält einen einzelnen groben Ausreißer heraus, eine grobe Mehrheit nicht: an
einem überwiegend grob vernetzten Modell bekäme eine feine Fuge den groben
Wert — im geprüften Drehlagermodell 45 bis 50 mm für Fugen, deren eigenes Netz
viel feiner ist. Ein Suchradius, der größer ist als das Bauteil dick, paart
Knoten über Luft hinweg. Der erste Durchgang dient darum nur dem **Finden**;
danach wird der Radius aus den beiden Seiten **dieser** Fuge neu bestimmt und
die Suche wiederholt. Er darf dabei kleiner werden (der Regelfall) oder größer
— der Median über die ganze Außenhaut eines Bauteils ist nicht der über seine
Fugenfläche, und ein zu enger erster Durchgang hätte einen Teil der Fuge nicht
gesehen. Wiederholt wird, solange sich der Radius um mehr als ein Zehntel
ändert, höchstens viermal. Ein in der Kontaktbedingung **vorgegebener**
Suchradius wird nicht überstimmt. Alle Knoten
der Kontaktfacetten mit Gegenseite werden Slave, die gefundenen Gegenfacetten
Master; der Löser ordnet dann jedem Slave-Knoten die nächste Master-Facette
**im selben Suchradius** zu (nächster Punkt auf dem Dreieck, vektorisiert über
einen KD-Baum). Der Abstand wird zum **Anfangsspalt** g₀ der Bedingung - oder
zu null, wenn die Bedingung „auf Berührung gesetzt“ ist (ANSYS: adjust to
touch) oder ein Verbund ist, der nur die Relativverschiebung misst.

**Der Facettenspalt wird bereinigt** (13.09.2026, „der Bolzen muss in den
Augen gelagert sein“). Eine gekrümmte Gegenseite — Bohrung, Zylinder — liegt
im Netz als Sehnen vor; ihre **Knoten** aber liegen auf der wahren Fläche.
Ein Slave-Knoten, der ebenfalls auf ihr liegt, steht gegen die Sehne um deren
Pfeilhöhe ab: bei 50-mm-Facetten auf r = 300 mm ein Millimeter. Als Spalt
gelesen, lag am Drehlager die passgenaue Achse (Kontaktbedingung „Achse
(Typ 3)“, r 302/298 mm) im Augenblech V16 nur mit 26 von 847 Knoten an —
denen auf einer Ecke der Bohrung —, 821 standen „offen“, und 632 davon, weil
sie hinter der Sehne liegen, mit **umgekehrter Normale** (ins Blech statt in
die Achse). Unter 1000 kN trug die Achse auf 27 von 1194 Knoten, mit 387 kN
auf einem einzigen. Gemessen wird darum zur **wahren Fläche**: durch die Ecken
jeder Master-Facette und die ihrer glatten Nachbarn (Facetten mit gemeinsamer
Ecke, deren Normale höchstens 30° abweicht — eine Kante bleibt eine Kante,
ein Absatz wird nicht verrundet) wird im Rahmen der Facette (x, y in der
Facette, z längs der Normalen) die Quadrik

$$ z + A x^2 + B y^2 + C x y + D x + E y + G z^2 + H x z + J y z + I = 0 $$

nach kleinsten Quadraten gelegt (`contact.Flaechenquadriken`, linear in den
Beiwerten); der nächste Punkt auf der Facette wird auf sie gehoben, die
Richtung ist ihre Normale dort. Die Quadrik enthält die Ebene (alle Beiwerte
null), jeden Zylinder — auch den, dessen Achse schief zur Facette steht, wie
an einem frei triangulierten Mantel (ohne H und J blieben dort 20 µm) —, die
Kugel und das Ellipsoid **exakt**:
eine passgenaue Achse hat in ihrer Bohrung Spalt null, nicht „fast null“ (ein
quadratisches Höhenfeld ließ am 36-Eck mit r = 300 mm noch 19 µm über das
Glied x⁴/8r³ der Nachbarn). Steht nur eine Reihe Facetten zur Verfügung (eine
Bohrung, eine Facette hoch), entfällt das Glied y², dann xy, dann y.
Knotennormalen (Phong-Tessellation) taugen dafür nicht: die
flächengewichtete Mittelung steht an einer unregelmäßig vernetzten Bohrung um
einige Grad neben der Radialen, und der Fehler wächst mit dem Abstand zur
Ecke — am Drehlager blieben so 0,3 mm Durchdringung, als Übermaß gelesen
7 MN Kontaktkraft; verworfen. Dieselbe Bereinigung gilt für die
Spaltstatistik der Fuge (`fugen.gegenseite_finden`), dort auf **beiden**
Seiten: auch der Schwerpunkt einer Facette der Kontaktseite liegt um die
Pfeilhöhe innen. Am Drehlager liegen jetzt in V16 649 von 847 Knoten an statt
26, in V29 253 von 347 statt 115, keine Normale ist gekippt; die Fuge meldet
„62 % aufliegend, Median 0,01 mm“ statt „22 %, Median 0,35 mm“. Die übrigen
Knoten sitzen jenseits der Bohrung oder an der Stufe der Achse und sind zu
Recht offen. Unter 1000 kN tragen 147 + 34 Knoten statt 17 + 10, die größte
Knotenkraft ist 149 kN statt 387 kN, beide Bleche tragen je die Hälfte.

**Bestimmt heißt gut konditioniert, nicht voller Rang** (15.09.2026). Auf dem
gmsh-Netz desselben Drehlagers (646 312 Elemente) lieferte der Kontaktaufbau
trotz Quadrik an 207 von 550 Bedingungen der Achse gegen V16 einen
Anfangsspalt von −51 bis −618 µm, obwohl Bohrung und Achsknoten exakt auf
r = 302 mm liegen. Die Quadrik ging dabei durch alle 9 bis 12 Stützpunkte
(Rest unter 10⁻⁸ µm), lag aber **zwischen** ihnen bis 0,68 mm daneben. Die
Neigung der Facetten war es nicht — alle 528 lagen parallel zur Achse. Die
Stützpunkte lagen auf vier gleichmäßig verteilten Winkellagen (Teilung
9,47°), symmetrisch zur Facette; dort ist z² eine gerade Funktion von x und
von 1 und x² nicht zu unterscheiden. Die Spaltenmatrix der allgemeinen
Quadrik hatte die Kondition 10¹⁴ mit dem Nullvektor rein in z², der Rangtest
von `lstsq` (Maschinengenauigkeit) nannte sie trotzdem voll — ob, entschied
die Rundung. Eine Stufe gilt darum nur, wenn ihr kleinster Singulärwert über
10⁻⁵ mal dem größten liegt (`contact.QUADRIK_GRENZE`); sonst die nächste,
an der Bohrung die Zylinderform (Kondition 97). Die Schranke ist gemessen: an
beiden Netzen des Drehlagers (alle zwölf Fugen, 44 000 Facetten) liegen
bestimmte Quadriken bei Konditionen bis 10⁹, unbestimmte ab 10¹² — dazwischen
nichts. Gewählt ist nicht die Mitte der Lücke, weil gerundete Koordinaten die
unbestimmten nach unten ziehen: mit 0,1 µm Rauschen auf 50-mm-Flecken kippte
10⁻⁷ (313 µm), mit 1 µm 10⁻⁶ (313 µm); 10⁻⁵ hielt beide (Stichprobe über
Mantellinien- und Delaunay-Netze, Radien 150 bis 1000 mm).

| Drehlager, gmsh-Netz, LF1 | vorher | nachher |
|---|---|---|
| Anfangsspalt Achse gegen V16 unter −50 µm | 207 von 550, tiefster −618 µm | 0 |
| tragende Knoten gegen V16 | 49 | 175 |
| Summe der Normalkräfte gegen V16 | 17 726 kN | 5 350 kN |
| größte Knotenkraft gegen V16 | 1 289 kN | 114 kN |
| größte Vergleichsspannung V16 | 1 916 MPa | 407 MPa |
| größte Vergleichsspannung V30, Achsmantel (r > 270 mm) | 1 980 MPa | 234 MPa |
| größte Vergleichsspannung V30, Stirnring „Achse (Typ 4)“ | 2 397 MPa | 739 MPa |

Die Auflagerkräfte bleiben gleich (3 968 / 9 255 kN). Die übrigen Spitzen in
V30 sitzen am haftenden Stirnring der Fuge „Achse (Typ 4)“ — eine
Singularität des Modells (Haften ohne Gleiten), keine des Kontakts; die in V16
an einem Element der Güte 0,135. Geprüft in `tests.test_fugen`,
`test_facettenspalt_unregelmaessig`: 60 Zufallsnetze (gmsh-artiges Gitter
und verwackeltes Delaunay-Netz, Bohrung und Achse als Gegenseite, Radien 150
bis 1000 mm, Kanten 20 und 50 mm, Knoten auf 0,01 µm gerundet); vorher
verfehlte die Fläche den Kreis bis 1 394,73 µm und in 33 Fällen meldete der
Kontaktaufbau eine Durchdringung, jetzt 0,00 µm und keine.

**Durchdringung bleibt Durchdringung.** Master-Facetten sind gerichtet (siehe
unten); ein Slave-Knoten hinter der Facette ist eine Durchdringung — der
Anfangsspalt ist negativ, die Bedingung von Anfang an aktiv —, kein Spalt
mit umgekehrter Richtung. Bisher wurde an expliziten Facetten die Normale
zum Slave-Knoten gedreht, sobald er hinter ihr lag; genau das kippte am
Drehlager die 632 Normalen ins Blech. Nur eine **Schale** hat kein Innen:
dort zeigt die Normale weiter zum Knoten.

**Berührungsband.** Ein Anfangsspalt, der dem Betrag nach unter einem
Tausendstel des Suchradius liegt — Spalt wie Durchdringung —, wird zu null
gesetzt (ANSYS: ICONT). Es ist dieselbe Grenze, bis zu der das Protokoll
einen Knoten „aufliegend“ nennt: was das Protokoll als Berührung zählt,
rechnet der Löser auch so. Der Rest der Bereinigung liegt weit darunter;
ohne das Band wäre er bei Durchdringung ein Übermaß von Mikrometern und
damit eine Pressspannung, die es nicht gibt. Geprüft in
`tests/test_fugen.py::test_facettenspalt_bereinigt` (Achse mit 40 Knoten in
einer 36-eckigen Bohrung: vorher 8 von 80 Knoten anliegend, jetzt alle, jede
Normale zur Achse; Kante, Band, Durchdringung, Schale) und
`test_zylinder_in_bohrung` (0,5 mm Spiel werden 0,5 mm gemessen, nicht
0,22 … 0,5 mm).

**Ein Radius, nicht zwei.** Der Löser hat den Radius früher verdoppelt: das
Protokoll nannte 9 mm, im Kontaktpaar standen 18,5 mm, durchgängig Faktor
zwei. Er paarte damit Knoten, die weiter entfernt lagen als jede Facette, die
die Suche zur Fuge gezählt hatte. Am Drehlagermodell waren das an der Fuge
Lagerbock–Grundplatte 213 von 290 gepaarten Knoten mit mehr als 5 mm Spalt,
der größte 121 mm — Lastpfade, die es in der Konstruktion nicht gibt. Mit dem
einfachen Radius bleiben dort 249 Paarungen, der größte Spalt ist 60 mm (die
Netzweite dieser Fuge); über acht Fugen fallen 127 Paarungen weg, alle mit
einem Spalt größer als das Netz der eigenen Fuge.

**Deckungsgleiche Knoten werden direkt gepaart.** Liegt ein Slave-Knoten auf
einem Master-Knoten (Toleranz 10⁻⁶ der Modellgröße), gibt es nichts zu suchen
und nichts zu projizieren: der Master ist dieser eine Knoten mit vollem
Gewicht, der Anfangsspalt ist exakt null. Das ist der ANSYS-Weg für ein
passendes Netz und erledigt an einer konformen Fuge die ganze Fläche
deterministisch. Was bleibt, ist die **Richtung**. Sie aus einer der Facetten
zu nehmen, die in diesem Knoten zusammenstoßen, wäre Zufall — welche der
Löser fand, entschied bisher die Reihenfolge im Feld: am Drehlagermodell stand
die gewählte Facettennormale im Median 41° neben der Flächennormalen des
Knotens (Fuge Achse, gekrümmter Master), an Fugenkanten bis 90°. Genommen wird
darum die flächengewichtete Mittelung der Master-Facetten in diesem Knoten,

$$ n = \frac{\sum_i A_i\,n_i}{\bigl|\sum_i A_i\,n_i\bigr|} $$

gerechnet über die **ganzen** Facetten und nicht über ihre Dreiecke: ein
Viereck zerfällt in zwei Dreiecke, und die Ecke, die in beiden vorkommt,
bekäme sonst das doppelte Gewicht — am regelmäßigen Zwölfeck genug, um die
Normale um 5,1° zu kippen. Heben sich die Beiträge auf — eine dünne Platte,
deren beide Seiten zum selben Kontaktpaar gehören —, gibt es keine
Flächennormale und es bleibt bei der Suche.

**Berichtet wird die Verteilung, nicht der Mittelwert.** Die Spaltmaße einer
teilweise anliegenden Fuge sind zweigipflig: ein Teil liegt auf null, der Rest
steht ab. Ein Mittelwert darüber beschreibt keinen Zustand — er nennt eine
Zahl, die an keiner Stelle der Fuge vorkommt, und verdeckt, dass ein Teil gar
nicht anliegt. Protokolliert werden darum der Anteil, der aufliegt (Spalt
unter einem Tausendstel des Suchradius), der Median, das 90. Perzentil und der
größte Wert — je Fuge für die Facetten und je Kontaktpaar für die Knoten,
zusammen mit der Zahl der Knoten, die **keine** Gegenfacette im Suchradius
gefunden haben.

**Eine Durchdringung ist kein Spalt.** Die Abstände tragen ihr Vorzeichen;
negativ heißt, der Knoten (bzw. die Gegenfacette) liegt schon vor der Last im
anderen Bauteil. Solche Werte zählen nicht in Median, Perzentil und größten
Spalt, sondern stehen dahinter mit Zahl und tiefster: „…; 207 durchdringend,
tiefste 0.62 mm“. Bis zum 15.09.2026 sammelten Kontaktaufbau und Fugensuche
den **Betrag** — am Drehlager mit gmsh-Netz meldete die Achse „Spalt 67 %
aufliegend … größter 0.62 mm“, obwohl sie an 207 Knoten bis 0,62 mm in der
Buchse stak und dort die zwölf größten Knotenkräfte saßen. Gepaart wird
weiter nach dem Betrag; nur die Auskunft trennt beides
(`tests.test_fugen`, `test_durchdringung_nicht_als_spalt`).

Aus der Wirkung je Freiheitsgrad folgt die Art des Kontaktpaars: Zug *starr*
(oder Feder) → die Bedingung öffnet nie, auch Zug wird übertragen (Verbund,
ohne Trennung); Schub *starr* → **haftend**, die Fugenebene ist eine Feder ohne
Gleiten (Rau, Verbund); sonst Kontakt mit Abheben und Coulomb-Reibung μ.
Verdrehungen wirken nur bei Schalen; zwischen Volumen bleiben sie ohne Wirkung
(das Protokoll sagt es).

Die Verbindung je Freiheitsgrad folgt der Freigabe: *starr* → Kopplung mit
Straffeder, *Feder c* [N/m je m²] → Kopplung mit c · A (A = Einflussfläche des
Knotens: jede anliegende Facette gibt ihren Inhalt gleichmäßig an ihre Knoten,
Dreieck A/3, Viereck A/4 – dieselbe Aufteilung wie bei einer Flächenlast),
*frei mit Ausfall* → Spaltelement. Ein Reibbeiwert geht als
Coulomb-Reibung in das Spaltelement; die Reibkraft hängt damit an der
wirklichen Kontaktkraft.

**Der Inhalt einer Facette ist der ganze, nicht der ihres ersten Dreiecks.**
Bis zum 22.09.2026 bildete `_fuge_knotenweise` die Facettenfläche aus den
**ersten drei** Knoten. Für ein Dreieck stimmt das; die Facettenliste enthält
aber Vierecke, sobald das Netz Hexaeder oder Viereckschalen hat (für eine
Hexaederseite steht in `SOLID_FACES` ein Vierertupel). Bei einem Viereck war A
damit das erste Dreieck — **die halbe Fläche**. Genau dieses A geht in die
Normalfeder (k_n = c · A) und in die Tangentialfedern: jede elastische Fuge auf
einem Sechsflächner- oder Viereckschalennetz war um den **Faktor zwei zu
weich**. Gemessen am ebenen Viereck 2,0 × 1,0 m: 1,0000 m² alt gegen 2,0000 m²
neu, am Dreieck 2,0 × 1,0 m unverändert 1,0000 m². Weil es am Dreiecksnetz
stimmte, sah der Unterschied beim Netzvergleich wie ein Netzeinfluss aus.
Gerechnet wird jetzt als Fächertriangulierung um den ersten Knoten: für ein
Dreieck derselbe eine Term wie vorher, für ein ebenes Viereck exakt, für ein
leicht windschiefes die Summe seiner beiden Dreiecke (Test
`test_viereckfuge_zaehlt_ganz`).

Die Prüfung dazu geht den Weg des Programms, nicht den der Formel: zwei hex8
übereinander mit gemeinsamer Fugenfläche 2,0 × 1,0 m, Federfuge
c_n = 1 · 10⁹ N/m³ normal und c_t = 1 · 10⁸ N/m³ in beiden Tangenten,
ausgeführt durch `fugen.kontaktfuge_ausfuehren`. Gemessen:
Σ k_n = 2,000 · 10⁹ N/m = c_n · A und Σ k_t = 4,000 · 10⁸ N/m = 2 · c_t · A
(Verhältnis je 1,0000). Mit dem alten Stand (nur die ersten drei Knoten)
kommt an derselben Fuge Σ k_n = 1,000 · 10⁹ N/m heraus, Verhältnis 0,5000 –
die Prüfung fällt dann. Ihre erste Fassung rechnete die Formel im Test nach
und rief die Fugenroutine nie auf; sie bestand auch mit dem alten Stand.

**Zum Vorzeichen des Ausfalls.** RFEM schreibt den Ausfall als „bei negativer"
oder „bei positiver" Kraft – bezogen auf die lokale z-Achse der freigegebenen
Fläche, die in der Datei nicht mitgeliefert wird. Dieselbe Fuge steht darum je
nach Lage der Flächenachse einmal als „Ausfall bei Zug" und einmal als „Ausfall
bei Druck" in der Datei; im geprüften Beispielmodell kommen beide
Schreibweisen nebeneinander vor. Zwischen zwei **Volumenkörpern** ist die Frage
aber nicht offen: zwei Bauteile, die aufeinanderliegen, können sich nicht
durchdringen. Die Richtung folgt darum der Geometrie – die Normale des
Spaltelements zeigt in den gelösten Körper hinein –, nicht dem Vorzeichen aus
der Datei. Der Rohwert steht im Protokoll.

**Master-Facetten müssen gerichtet sein.** Beim Kontaktpaar liest der Kontakt
die Richtung einer Facette aus der Reihenfolge ihrer Knoten,
n = (P₁−P₀) × (P₂−P₀). Liegen Slave und Master aufeinander – und genau das ist
eine Kontaktfuge –, ist der Abstand null und die Richtung lässt sich nachträglich
nicht mehr bestimmen. Die Knoten jeder Master-Facette werden darum schon beim
Anlegen so geordnet, dass n aus dem Masterkörper heraus zeigt.

**Lager an Fugenknoten** werden mitgenommen: vor der Trennung hing an einem
Knoten ein Lager und beide Bauteile daran; danach gibt es zwei Knoten und beide
bekommen es. Lasten werden **nicht** verdoppelt – eine verdoppelte Kraft wäre
eine andere Aufgabe.

Was nicht geht, bleibt sichtbar: eine Fuge ohne Gegenfläche, ohne Netz oder
ohne Flächen im Modell wird mit Grund gemeldet; eine Fuge, deren Fugenebene
weder Federn noch Reibung hat, wird als frei gleitend gemeldet, denn dann
braucht das gelöste Bauteil eigene Lager.

**Geprüft** wird in `tests/test_fugen.py` an zwei Würfeln übereinander gegen
geschlossene Werte: unter Druck ist die Fuge zu und die Auflagerkraft gleich der
Last (auf Rechengenauigkeit), unter Zug geht **keine** Kraft mehr durch das
Fundament (Sollwert null, nicht „klein"), und beide Wege – passende und nicht
passende Netze – liefern dieselbe Stauchung.

**Grundlast in der direkten Lösung.** Eine nichtlineare Rechnung kennt keine
Überlagerung: was in einem Zustand wirken soll, muss in ihm gelöst werden.
Ein Lastfall mit `grundlast = True` (Vorspannung der Anker, ständiges
Eigengewicht) geht darum in jede direkt gelöste Rechnung mit Faktor 1 ein
(`solver._solve_loads`: Modelle mit Kontakt oder Ausfallstäben), wenn er
nicht ohnehin in den Faktoren steht; das Ergebnis nennt ihn in
`info["grundlast"]`. Linear bleibt er ein gewöhnlicher Lastfall, denn
dort legt die Überlagerung ihn in die Kombinationen. Geprüft am Block mit
Reibung (Auflast als Grundlast, Horizontalkraft allein gerechnet = die
Kombination aus beiden, Abweichung 0) und am Rahmen ohne Kontakt (die Marke
ändert nichts).

**Kontaktzustand sichern: Warmstart und Einfrieren.** Jede direkt gelöste
Rechnung mit Kontakt sichert am Ende ihren konvergierten Kontaktzustand
(`ContactSystem.zustand`: Aktivmenge, Gleiten mit Richtung, Fließen,
Normalkräfte, festgehaltene Bedingungen; `Results.kontaktzustand`). Zwei
Verwendungen:

*Warmstart* (`solve_with_contact(start=…)`): der nächste Lastfall derselben
Situation beginnt die Iteration in diesem Zustand statt bei der Geometrie,
in Phase 2 mit festen Gleitrichtungen. Die erste Matrix ist dieselbe wie die
letzte des vorigen Lastfalls, und `StaticSystem.solve` behält die
Faktorisierung, solange die Signatur der Kontaktsteifigkeit (Phase,
Aktivmenge, Gleiten, Fließen, **Schubhalt**, rutschende Gruppen;
`ContactSystem.signatur`) gleich bleibt — dann wird nur rückwärts eingesetzt.

**Ein Deckel, der wie Konvergenz aussah (21.09.2026).** Die Nachprüfung der
Reibung in Phase 2 bricht nach `MAX_CYCLES = 40` Zustandswechseln ab
(`ContactSystem.update`). Sie gibt dabei `False` zurück — **denselben Wert wie
bei echter Konvergenz**. `solve_with_contact` las beides als „fertig" und
setzte `contact_converged` auf wahr; die Warnung stand allein im
`contact_log`.

Das ist keine Geschwindigkeitsfrage. Jede Zahl, gegen die geprüft wird, ob
eine Änderung „das Ergebnis nicht ändert", kann aus einem gedeckelten Lauf
stammen — und sah bis dahin aus wie eine auskonvergierte. Der Löser
unterscheidet die beiden Fälle jetzt am Merker `cs.am_deckel` der letzten
Runde (bis zum 22.09.2026 an `cs.cycles`, siehe „Der Deckel gilt für die
Runde, in der die Schleife endet“) und nennt im Protokoll den
Grund statt der Schrittzahl. `tests/test_kontakthalt.py` setzt den Deckel
künstlich auf 1 und prüft, dass `contact_converged` dann **falsch** meldet;
mit dem alten Stand meldet dieselbe Prüfung wahr.

> **Und am Drehlager zieht der Deckel — in mindestens einem Lauf.** Im
> gesammelten `contact_log` von LF1 steht in zwei Läufen wörtlich „Kontakt:
> Nachprüfung der Reibung nach 40 Zustandswechseln abgebrochen" — und daneben,
> mit der alten Meldung, „konvergiert True". LF1 besteht mit Fließen aber aus
> **zwölf** Kontaktläufen, und gleichlautende Zeilen wurden über alle zwölf
> zu einer zusammengefasst. Belegt ist darum nur: **in mindestens einem der
> zwölf Kontaktläufe hat die Nachprüfung der Reibung nach 40
> Zustandswechseln aufgegeben.** Ob der letzte betroffen ist — aus ihm
> stammen u und σ, die 1,2713 mm und 388,0 N/mm² —, ist nicht belegt. Die
> einzige Reibstelle ist das Flächenlager „Starr" mit μ = 0,1; alle zwölf
> Kontaktpaare haben μ = 0. Seit dem 22.09.2026 trägt die Abbruchzeile ihren
> Kontaktlauf und wird nicht mehr zusammengefasst, und `res.info` führt
> `contact_letzter_lauf_konvergiert` und `contact_laeufe_nicht_konvergiert` —
> die Frage lässt sich beim nächsten Lauf ablesen, statt sie zu vermuten.
> (Eine frühere Fassung sagte „LF1 am Drehlager konvergiert im Reibzustand
> nicht"; das war zu scharf. Nachprüfung der Lösersitzung vom 22.09.2026.)
>
> **Wiederholbar — auf demselben Weg.** Das ausgelieferte Programm (unsymmetrische Zerlegung) hat am Drehlager in **drei** Läufen von LF1 denselben Kontaktweg genommen — 150 Schritte, 145 Faktorisierungen —, und die Spannungen lagen höchstens **0,0004 N/mm²** auseinander (Verschiebungen relativ 4,3·10⁻⁷): nicht bitgleich, aber derselbe Weg.
> Die frühere Fassung schloss hier „dieselbe Rechnung gibt dasselbe
> Ergebnis" — bitgleich ist das nicht, aber im Weg traf es zu. Auseinander
> lief nur das Paar B/C einer **Versuchsfassung mit symmetrischer Zerlegung**
> (`mtype -2`; pypardiso nullt dabei `iparm`, laut MKL-Dokumentation gelten
> dann andere Vorgaben: Pivotstörung 10⁻⁸ statt 10⁻¹³, keine Skalierung,
> kein Matching). Zwei ihrer Läufe (C nur mit einem Merker für das
> Symmetrieurteil) wichen in der Vergleichsspannung um bis zu
> **273,08 N/mm²** voneinander ab (Element 623 980: 79,15 gegen
> 352,23 N/mm²), 23 390 Elemente um mehr als 1 N/mm²; C lief zu rund 70 %
> neben einem Gesamttestlauf der Statik3D-Sitzung. Der Verdacht fällt auf die
> ungesetzten Vorgaben der symmetrischen Zerlegung — bewiesen ist er nicht.
> **Diese Fassung ist nicht eingebaut**; die Lösersitzung misst sie mit
> gesetzten `iparm`-Werten und einer Wegeprüfung nach, bevor sie es wird. Die
> 0,0004 N/mm² zwischen A (unsymmetrisch) und B (symmetrisch) zeigen nur,
> dass diese beiden denselben Weg nahmen — über die Wirkung der symmetrischen
> Zerlegung sagen sie nichts.
>
> **Woran es liegt, ist offen.** Die automatische Kontaktsteifigkeit ist
> `PENALTY_FACTOR = 1e4` mal die örtliche Diagonalsteifigkeit; am Drehlager
> steht der **größte Eintrag** der Matrix damit bei 1,05·10¹⁷ gegen 1,9·10¹³
> ohne Kontakt. Das ist nicht die Konditionszahl — die ist in keinem Lauf
> gemessen; für die abgelegte Testmatrix vom 19.09. folgt aus den
> Protokollzahlen nur κ₂ ≥ 1,1·10¹⁵. Dass zwei rechnerisch gleichwertige
> Faktorisierungen dieser Matrix Lösungen liefern, die um 269 %
> auseinanderliegen, während beide Residuen bei 10⁻¹⁵ stehen, heißt: sie ist
> für eine künstliche rechte Seite, die alle Richtungen anregt, numerisch
> fast singulär. Dass die Strafsteifigkeit das verursacht, ist nicht gezeigt.
>
> Gemessen am echten Modell (LF1, sonst unverändert, **je ein Lauf**,
> 22.09.2026):
>
> | `PENALTY_FACTOR` | Zeit | Kontaktschritte | max \|u\| | σ_v | Deckel |
> |---|---|---|---|---|---|
> | 10⁴ | 875,2 s | 150 | 1,2713 mm | 388,0 | gezogen |
> | 10³ | 950,4 s | 155 | 1,2713 mm | 388,0 | **gezogen** |
>
> Feldweise über alle 645 934 Elemente: größte Abweichung der
> Vergleichsspannung **0,1324 N/mm²**, vier Elemente über 0,1, keines über
> 1,0; größte Knotenabweichung 0,00002 mm.
>
> Daraus folgt weniger, als hier früher stand. **Belegt** ist: auch mit
> einem Zehntel der Strafsteifigkeit steht die Abbruchmeldung im Protokoll.
> **Nicht belegt** ist, dass die Strafsteifigkeit nicht die Ursache sei —
> die Kondition wurde in keinem Lauf gemessen, und 10³ verändert zugleich
> das Modell (zehnfache Eindringung), nicht nur die Kondition. Die
> 0,13 N/mm² sind der Unterschied zweier **Modelle** mit verschiedenem
> Kontaktweg (155 gegen 150 Schritte) — kein Maß für Rundungsfehler und
> keine Schranke: dass eine Versuchsfassung mit symmetrischer Zerlegung um
> 273 N/mm² streuen konnte, zeigt der Lauf C oben. Aus max |K| folgt auch keine Schranke; dafür bräuchte es
> die Konditionszahl, bei PARDISO mit Skalierung die der skalierten Matrix.
>
> `PENALTY_FACTOR` bleibt bei 10⁴ — nicht, weil 10³ nachweislich schlechter
> wäre: die 8,6 % mehr Zeit des einen Laufs liegen in der Streuung dieses
> Abends (gleichwertige Läufe 3 bis 17 %), und er lief unter Fremdlast. Es
> gibt schlicht keinen belegten Grund zu wechseln. (Eine frühere Fassung
> sagte, die Konstante habe „jetzt Zahlen hinter sich"; Nachprüfung der Lösersitzung vom 22.09.2026.)

**Zwei Posten daneben, die nichts mit dem Schlüssel zu tun haben, aber mit
derselben Messung gefunden wurden** (21.09.2026, an einer Matrix von
Drehlagergröße: 475 935 Zeilen, 17,6 Mio. Nichtnullen):

| | je Aufruf | je Lastfall | über 422 Lastfälle |
|---|---|---|---|
| doppeltes `tocsr()` im `LinearSolver` | 0,280 s | 40,6 s (145 Faktorisierungen) | **rund 3,0 h** |
| `Kt` und `Ktff` bedingungslos gebaut | 0,577 s | 2,88 s (5 von 150 Schritten) | 0,34 h |

Der erste wandelte dieselbe Matrix zweimal nach CSR um — `self._K` steht
bereits da. (Die 0,280 s sind an einer **Ersatzmatrix** gemessen, am
Drehlager selbst nicht. Eine frühere Fassung der Tabelle schrieb 4,75 h; sie
setzte für alle 422 Lastfälle die 145 Faktorisierungen des kalten LF1 an.
Mit den gemessenen Zahlen — 145 im kalten, im Mittel 91 in den warmen
Lastfällen — sind es 145 + 421 × 91 = 38 456 Umwandlungen, rund 3,0 h;
Nachprüfung der Lösersitzung vom 22.09.2026. Seit demselben Tag wandeln auch die Wege MUMPS und ama nicht mehr
ein zweites Mal um.) Der zweite baute die Tangente und ihren Zuschnitt in **jedem**
Schritt, obwohl `Ktff` nur beim Neufaktorisieren gelesen wird und `Kt` sonst
nur bei einer Verformungsvorgabe; weder der Schlüssel noch der
zwischengespeicherte Löser hängen daran, die Reihenfolge ließ sich also
umstellen. Dass der zweite Posten so klein ausfällt, ist selbst ein Befund:
**145 von 150 Schritten faktorisieren neu**, also gibt es fast nichts
einzusparen. Die Schätzung „1,4 bis 1,9 s je Schritt“ galt der Annahme, die
Faktorisierung würde oft wiederverwendet — sie wird es nicht.

Geprüft wird in beiden Fällen **gezählt, nicht gemessen** (`tests/test_loeser.py`):
eine Umwandlung statt zwei, und null Matrixadditionen im zweiten Lösen mit
gleicher Signatur. Eine Zeitmessung hinge an der Maschine, die Zahl der
Aufrufe nicht.

**Zwei Löcher in diesem Schlüssel, beide am 21.09.2026 geschlossen.** Ein
Schlüssel, der eine Matrixänderung nicht sieht, ist schlimmer als keiner: er
lässt mit der falschen Faktorisierung rechnen, und niemand merkt es.

* Der **Schubhalt** fehlte. `ContactSystem.matrices` legt für eine *inaktive*
  Bedingung mit `schub_halt` einen k_t-Block in K_c — am Prüfstift 144
  Einträge gegen null. `schub_halt_loesen` räumt die Marke ab, sobald die
  Gruppe wieder trägt; fällt das in eine Runde ohne Wechsel von Aktivmenge,
  Gleiten oder Fließen, blieb die Signatur gleich und die Matrix nicht.
  Schärfer noch: der Schubhalt entsteht **nach** einem gescheiterten Lösen,
  und scheitert dieses erst in der Residuumsprüfung, ist die Faktorisierung
  bereits im Zwischenspeicher — dann wird mit genau der Zerlegung gelöst, die
  eben gescheitert ist, und der Schubblock erreicht den Löser nie. Die
  Nachprüfung fängt es nicht, sie misst gegen die alte Matrix.
* Die **Zusatzmatrix** (`solver.zusatz_kenn`) hashte Form, Nichtnullzahl und
  Werte, aber nicht die **Belegung**. Zwei Matrizen mit bitgleichen Werten an
  anderen Stellen waren ununterscheidbar. Greifbar bei baugleichen Stäben in
  `solve_with_ausfall`: derselbe Ausfall liefert dieselben 144 Einträge an
  anderen Indizes.

Beides kostet einen Hash je Aufruf und spart **keine** Faktorisierung ein;
zusätzliche gibt es nur dort, wo die Matrix wirklich eine andere ist.
`tests/test_kontakthalt.py` hält beides fest — mit der Probe, dass die Matrix
sich wirklich ändert, und mit dem Nachweis, dass die alte Signatur die beiden
Zustände für gleich hielt.

Gefunden hat beides die Löser-Sitzung, **am Quelltext, nicht an einer Zahl**:
fünf Leser mit je einem Gegenprüfer, deren Auftrag das Widerlegen war. Das ist
die Lehre daneben — ein Fehler, der nur einen seltenen Pfad trifft, zeigt sich
in keiner Messung, weil die Messung ihn nicht durchläuft. Nach der Konvergenz
prüft `warmstart_verstoesse`, ob gleitende Knoten sich gegen ihre
festgehaltene Richtung bewegen: wenige werden auf Haften zurückgesetzt und
die Iteration läuft weiter, viele verwerfen den Warmstart (Neustart von der
Geometrie, Protokoll „Warmstart verworfen“) - seit dem 27.09.2026 nur noch
bei einem **fremden** Zustand (anderer Lastfall, eingefrorener Zustand);
innerhalb desselben Lastfalls wird immer zurückgesetzt und fortgesetzt,
siehe „Warmstart als Regel“ in Abschnitt 4. Gemessen am 12.09.2026: Block
mit Reibung, Folgezustand 5 statt 21 Schritte, Wiederholung desselben
Lastfalls 1 Schritt ohne Faktorisierung. Varianten, die nicht blieben:
Warmstart in Phase 1 mit grober Reststeifigkeit (20 Schritte, kein Gewinn),
Phase 1 mit feiner Reststeifigkeit (120 Schritte, divergiert), Phase 2 mit
nachgeführten Richtungen (40 Schritte, divergiert). Am Drehlager
(Vorspannung + LF401 kalt: 1063 s, 36 Schritte, 35 Faktorisierungen) passte
der Zustand nicht zu LF404: verworfen, mit Neustart 1250 s und 32 Schritte
— die Gleitrichtungen der Zustände unterscheiden sich, der Warmstart bringt
dort nichts.

*Einfrieren* (`solve_with_contact(einfrieren=…)`, `solve_cases(referenzen=…)`):
der Zustand wird nicht mehr verändert — Kontaktsteifigkeit und -kräfte des
Referenzzustands, eine lineare Lösung ohne Iteration, mit der behaltenen
Faktorisierung eine Rückwärtseinsetzung. Das ist der Weg für die Zustände
einer Ermüdungslast (`solver.ermuedungsreferenzen`,
`DesignSettings.ermuedung_kontakt_einfrieren`, Vorgabe ein): der erste
Zustand jeder Ermüdungslast wird nichtlinear gelöst, die weiteren mit
seinem eingefrorenen Zustand, und zwar unmittelbar nach ihm, damit die
Faktorisierung im Speicher bleibt (`_mit_referenzen_zuerst`; ein Lastfall
dazwischen ersetzt sie, gemessen: 1 statt 0 Faktorisierungen). Die
Voraussetzung: die Zustände sind kleine Änderungen um den Referenzzustand —
die Schwingbreite ist die Differenz zweier Zustände, und für sie zählt die
Steifigkeit des Betriebszustands, nicht ein je Zustand neu gesuchtes
Kontaktbild. Das Ergebnis trägt `info["contact_frozen"]` und
`contact_frozen_from`, die Analyse `info["kontakt_eingefroren"]` mit der
Zuordnung. Geprüft am Block mit Reibung (`tests/test_kontaktzustand.py`,
`test_einfrieren`): H2 = 1,1·H1 eingefroren gegen nichtlinear 7,0 %
Abweichung der Verschiebungen, 1 Schritt, 0 Faktorisierungen, Gleichgewicht
exakt. Am Drehlager (Vorspannung 735 kN je Anker als Grundlast, Ereignis
„Zugüberfahrt und Reibung“, Zustände LF401 und LF404; venv mit Pardiso,
12.09.2026): LF401 nichtlinear 1055 s, 42 Schritte, 41 Faktorisierungen;
LF404 mit dem eingefrorenen Zustand von LF401: 1 Schritt, 0
Faktorisierungen, 15 s für die Lösung und 250 s samt Nachlauf (Spannungen
je Element, bei jedem Zustand gleich; zweite Messung mit LF401 in 1209 s /
41 Schritten); LF404 nichtlinear (Warmstart aus LF401, diesmal
angenommen): 798 s, 40 Schritte, 39 Faktorisierungen. Eingefroren gegen
nichtlinear: Verschiebungen |Δu|max 0,16 % von |u|max (1,657 mm beide),
Auflager Rx 10,8 gegen 9,1 kN, Rz −5420 gegen −5414 kN, Signalspannung
(vorzeichenbehaftete Hauptspannung je Element) Median der Abweichung 0,00,
99 % 0,1 N/mm², größte 216 N/mm² an einer Spannungsspitze von 4656 N/mm²
(Kopplung). Für die Schwingbreite eines Ermüdungsnachweises ist das die
Genauigkeit der Kontaktsteifigkeit selbst; die 164 Zustände des Drehlagers
kosten so 47 nichtlineare Lösungen statt 164.

**Angeschweißte Nachbarn lösen sich mit.** Beim Trennen der Fuge werden
die Knoten verdoppelt, die der gelöste Körper mit anderen teilt. Bis zum
12.09.2026 galt das für *jeden* anderen Körper — auch für die, die mit ihm
über eine gemeinsame Fläche ohne Kontaktbedingung verschweißt sind. Am
Drehlager verdoppelte die Fuge „Lagerbock-Grundplatte“ so auch die Knoten
auf der Kante des Lagerbocks V14 zu den Rippen V5, V6, V23 und V24: der
Lagerbock bekam die Kopien, die Rippen behielten die Originale und verloren
dort den Anschluss (Abnahme: „22 doppelte von 42 Knoten auf der Fuge“).
Jetzt bestimmt `fugen.verschweisste_gruppe` zuerst die Körper, die mit dem
gelösten über gemeinsame Flächen ohne Kontaktbedingung zusammenhängen
(Flächen, die eine Kontaktbedingung nennt, verbinden nicht; Paare mit
Kontaktbedingung sind keine Nachbarn); diese Gruppe löst sich als Ganzes:
verdoppelt werden nur Knoten, die sie mit Körpern *außerhalb* der Gruppe
teilt, und alle Elemente der Gruppe bekommen dieselben Kopien. Das Protokoll
nennt die mitgelösten Nachbarn. Geprüft an drei Blöcken (`test_fugen`,
`test_fuge_laesst_schweissnaht_ganz`): der obere Würfel mit angeschweißter
Rippe auf dem unteren, Fuge zwischen Würfel und Fundament — die fünf Knoten
der Fugenkante gehörten allen dreien; ohne Mitnahme meldete die Abnahme
„Oben und Rippe teilen sich MO1, sind dort aber nicht verbunden: 5
doppelte“, mit Mitnahme bleibt die Rippe am Würfel und kein Knoten gehört
Fundament und Würfel zugleich.

#### Welcher gedeckelte Lauf zählt: der Vorlauf nicht (22.09.2026)

Mit Fließen rechnet ein Lastfall viele Kontaktläufe: zuerst einen
**elastischen Vorlauf** (`_solve_loads`, der erste `_rechnen()`), danach je
Laststufe und Newton-Schritt einen (`_plastizitaet_rechnen`). Der Vorlauf
gibt nichts weiter. Der erste plastische Lauf startet beim Start des
Lastfalls (`halter = {"start": start, …}`), nicht beim Kontaktzustand des
Vorlaufs, und das u des Vorlaufs wird überschrieben. Gemessen am Block mit
Reibung (Streckgrenze 60 % der elastischen Vergleichsspannung, zwei
Laststufen), Deckel 1 nur während des Vorlaufs: der Vorlauf ist gedeckelt,
`contact_converged` meldet falsch, und die Verschiebungen sind **bitgleich**
mit dem Lauf ohne Deckel - max |Δu| = 0 bei max |u| = 2,883·10⁻⁶ m
(`tests/test_rechenliste.test_vorlauf_mit_deckel`).

Jeder **plastische** Lauf dagegen reicht seinen Kontaktzustand an den
nächsten weiter (`halter["start"] = res.kontaktzustand`), und dieser Zustand
bestimmt die plastische Dehnung mit. Darum gilt: jeder gedeckelte Lauf außer
dem Vorlauf macht den Lastfall „NICHT konvergiert“, auch wenn der letzte Lauf
konvergiert ist. Der Löser führt die Zahlen des Vorlaufs eigens in `res.info`
(`contact_vorlauf_laeufe`, `contact_vorlauf_nicht_konvergiert`), damit
`rechenliste.zustand_aus_info` sie herausrechnen kann. `contact_converged`
bleibt, wie es war, und klebt über alle Läufe, den Vorlauf eingeschlossen.

Seit dem 23.09.2026 gibt es den Vorlauf nur noch in der verschachtelten
Iteration (der Vorgabe); die gemeinsame (wählbar, § 5e.3) lässt ihn weg. Dort
gibt es stattdessen **abgekürzte** Läufe: mitten in einer Laststufe mit
Absicht nach einem Kontaktschritt beendet, der nächste setzt ihren Zustand
fort. Sie zählen nicht als „nicht konvergiert“ — entschieden wird an dem
Lauf, mit dem die Stufe endet, und am letzten, und beide sind volle Läufe.
Ebenso **verworfene** Läufe (24.09.2026): gibt die gemeinsame Iteration eine
Laststufe auf, wird die Stufe vom Kontaktzustand nach ihrem Startwert an
verschachtelt wiederholt; weder das u noch der Kontaktzustand der Läufe
dazwischen geht ins Ergebnis ein. Ein gedeckelter voller Lauf, der zählt,
zählt wie bisher, auch mitten im Lastfall.

Eine Zwischenstufe „eingeschränkt“ (letzter Lauf konvergiert, ein
Zwischenlauf gedeckelt) gibt es mit Absicht nicht. Ob ein solcher Lastfall
als Nachweis taugt, ist eine Entscheidung des Anwenders; bis sie getroffen
ist, heißt er „NICHT konvergiert“. Die Rechenliste las die Deckelmeldung bis
zum 22.09.2026 sogar als „konvergiert“ (Benutzerhandbuch, Rechenliste).

#### Der Deckel gilt für die Runde, in der die Schleife endet (22.09.2026)

`ContactSystem.update` gibt in Phase 2 `False` zurück, wenn nichts mehr
wechselt, und wenn die Nachprüfung am Deckel aufgibt. Bis zum 22.09.2026
entschied `solve_with_contact` den Abbruchgrund an
`cs.phase == 2 and cs.cycles >= MAX_CYCLES`. Der Zähler bleibt nach dem
Deckel aber stehen. Löst `schub_halt_loesen()` in der Deckelrunde einen
Schubhalt, setzt der Löser `changed = True`, und die Schleife läuft weiter;
endet eine spätere Runde **echt** ohne Wechsel, stand der Zähler immer noch
auf dem Deckel, und der Lauf hieß „nicht auskonvergiert“.

Jetzt setzt `update()` bei jedem Aufruf den Merker `am_deckel` neu: wahr
genau dann, wenn **dieser** Aufruf am Deckel aufgegeben hat. Der Löser liest
den Grund an der Runde ab, in der die Schleife wirklich endet. Läuft sie nach
einem Deckel weiter, steht das im Protokoll („nach dem Deckel der
Reibungsnachprüfung wurde ein Schubhalt gelöst - die Iteration läuft
weiter“), damit die Abbruchzeile des Kontaktsystems daneben nicht wie das
Ende des Laufs aussieht. Endet die Schleife danach an der Schrittgrenze, heißt
der Grund wie bisher „nach 120 Schritten nicht konvergiert“.

Nachgestellt am Block mit Reibung mit Deckel 1, wobei `schub_halt_loesen` in
jeder Deckelrunde einen gelösten Schubhalt meldet (4 Deckelrunden): die
Schleife geht damit genau den Weg des Laufs ohne Deckel - 21 Schritte,
max |Δu| = 0 - und endet echt ohne Wechsel. Vorher: `contact_converged`
falsch und „nicht auskonvergiert“ im Protokoll; jetzt konvergiert
(`tests/test_kontakthalt.py`, `test_deckel_merker_gilt_fuer_die_letzte_runde`,
`test_deckel_am_tatsaechlichen_austritt`). Ein Lauf, der am Deckel **endet**,
heißt weiter „nicht auskonvergiert“ (`test_der_deckel_gilt_nicht_als_konvergenz`).

#### Folgen des Merkers: Schlussprüfungen und vorsichtiger Rückfall (22.09.2026)

`converged = not deckel` entscheidet mehr als die Kennzahl. Nur ein
konvergierter Lauf durchläuft die Schlussprüfungen von `solve_with_contact`:
`schub_unter_last` und `_gehaltene_unter_zug` (beide brechen mit
`KontaktAbbruch` ab) und nach einem Warmstart `warmstart_verstoesse` (wenige
Verstöße: auf Haften zurück und rekursiv weiter vom Zustand; viele: neu von
der Geometrie). Im Randfall oben liefen sie bis zum 22.09.2026 nicht; jetzt
laufen sie. Dort kann also ein Abbruch oder eine weitere Rechnung stehen, wo
vorher ein gedeckeltes Ergebnis stand - eine Ergebnisänderung genau in
diesem Randfall, in keinem anderen. Am Block des Tests greift keine der
Prüfungen (kalter Start, 21 Schritte, max |Δu| = 0).

Fehlt der Merker - ein Kontaktsystem, dessen `update()` ihn nicht setzt -,
gilt die alte Probe `phase == 2 and cycles >= MAX_CYCLES`. Die erste Fassung
las `getattr(cs, "am_deckel", False)`: ein fehlender Merker hieß „nicht am
Deckel“, also konvergiert. Am Block mit Reibung, Deckel 1 und nach jedem
`update()` entferntem Merker meldete sie `contact_converged` wahr, jetzt
falsch (`tests/test_kontakthalt.py`,
`test_ohne_merker_gilt_die_vorsichtige_probe`). `ContactSystem.update`
setzt den Merker in jedem Aufruf; der Rückfall betrifft keine Rechnung des
Programms, er verhindert nur, dass ein fehlender Wert als Erfolg gelesen wird.

### 4.0a Übermaß: die Presspassung als Last

`model.Uebermass`, `contact.ContactSystem._fugen_uebermass`, `passungen.py`

Ein Passstift hält sein Bauteil nicht, weil er im Loch steckt, sondern weil
er zu dick dafür ist. Das Übermaß erzeugt eine Pressspannung, und über den
Reibbeiwert der Fuge trägt sie Schub. Ohne das ist ein Passstift in einer
reibungsfreien Bohrung ein Bauteil, das in der Fugenebene nichts hält -
und die Rechnung sagt es dann auch (§ 7b).

**Als negativer Anfangsspalt.** Die Kontaktbedingung eines Slave-Knotens
lautet g = g₀ + cₙ·u ≥ 0 mit dem gemessenen Anfangsabstand g₀. Ein Übermaß
ist nichts anderes als ein **negatives** g₀: die Fuge steht schon vor jeder
Last unter Druck. Das ist keine Näherung, sondern genau der Fügezustand; die
Kontaktiteration liefert daraus die Pressverteilung, und der Reibbeiwert
macht daraus Schubtragfähigkeit. Ein Verbund (Zug übertragend) kennt weder
Spalt noch Übermaß - dort bleibt g₀ = 0.

**Gesamtüberdeckung, und was davon radial wirkt.** Angegeben wird immer, was
die beiden Teile **zusammen** zu viel haben:

* **ebene Fuge** - die Überdeckung senkrecht zur Fläche; die Fuge muss sie
  ganz schließen.
* **zylindrische Fuge** - das Übermaß am **Durchmesser**, so wie es in jeder
  Passungstabelle steht. Radial schließt die Fuge davon die Hälfte.

Erkannt wird die Form am Betrag der mittleren Facettennormalen der Fuge:

    |Mittelwert der Einheitsnormalen| < 0,7  →  zylindrisch

Bei einer ebenen Fuge zeigen alle Normalen in dieselbe Richtung, der Betrag
ist 1. Bei einer Bohrung heben sie sich weitgehend auf; für einen Bogen mit
dem halben Öffnungswinkel α ist der Betrag sin α / α, und 0,7 entspricht
einem umschlossenen Bogen von rund 160°. Eine Bohrung und ein Passstift
umschließen mehr, ein leicht gewölbtes Blech weniger.

Gerechnet wird die Form aus den Facetten, die **wirklich gepaart** wurden,
nicht aus allen Außenflächen des Master-Objekts: ein Sechsflächner als Master
hat sechs davon, und alle sechs zusammen sähen aus wie eine Bohrung. Was
erkannt wurde und womit gerechnet wird, steht im Protokoll - eine
Verwechslung wäre sonst ein Faktor zwei in der Pressspannung, den niemand
bemerkt.

**Aus der Passung.** Auf der Zeichnung steht ein Kurzzeichen, „Ø40 H7/s6".
Was das Programm braucht, ist eine Länge. Der Weg dahin führt über die vier
Abmaße der Passungstabelle - oberes und unteres Abmaß der Bohrung (ES, EI)
und der Welle (es, ei), alle auf dasselbe Nennmaß bezogen:

    Höchstübermaß   Ü_max = es − EI      (größte Welle, kleinste Bohrung)
    Mindestübermaß  Ü_min = ei − ES      (kleinste Welle, größte Bohrung)
    mittleres Übermaß = (Ü_max + Ü_min)/2

Ein negativer Wert ist Spiel, kein Übermaß. Maßgebend ist je nach Frage ein
anderer Ansatz: für die **größte Pressung** (Werkstoffnachweis der Nabe) das
Höchstübermaß, für die **kleinste Haltekraft** (Reibschluss) das
Mindestübermaß.

Eine Tabelle nach ISO 286 bringt das Programm **nicht** mit. Sie hat für
jedes Nennmaßfeld und jede Toleranzlage eigene Werte; eine aus zweiter Hand
abgeschriebene Tabelle wäre nicht nachprüfbar, und ein Zahlendreher darin
würde still zu einer falschen Pressspannung führen. Eingegeben werden die
vier Abmaße der Zeichnung - oder gleich die Gesamtüberdeckung. Das
Kurzzeichen wird als Beleg mitgeführt und steht im Bericht.

**Als Lastfall.** Das Übermaß gehört zu einem Lastfall und geht mit dessen
Beiwert in die Kombination ein - wie jede andere Last. Geometrisch ist es
zwar ein Maß und keine Last; wer es nicht vervielfacht sehen will, legt es
in einen ständigen Lastfall mit γ = 1,0.

**Prüfung.** Zwei Würfel übereinander, beide Deckel in z gehalten, Fuge in
der Mitte: jeder Würfel ist eine Feder E·A/L, in Reihe nehmen sie zusammen δ
auf, und die Pressspannung ist σ = δ·E/(2·L). Der lineare Sechsflächner
bildet diesen gleichförmigen Dehnungszustand exakt ab; übrig bleibt nur die
endliche Steifigkeit der Kontaktfeder (Abweichung 6·10⁻⁵). Die Halbierung
bei der zylindrischen Fuge ist ohne Kesselformel nachgewiesen: dasselbe
Modell mit 40 µm Übermaß trifft auf die Stelle genau, die 20 µm
Spaltschluss ergeben, und 40 µm Spaltschluss geben das Doppelte
(`tests/test_uebermass.py`).

#### Zuordnung nur über den genauen Namen (22.09.2026)

`_fugen_uebermass` sucht das Übermaß eines Kontaktpaars unter seinem Namen.
Bis zum 22.09.2026 folgte bei einem Fehltreffer ein Präfixzweig: es galt der
**erste** Eintrag, mit dem der Name des Paars beginnt - begründet damit, dass
eine Fuge in mehrere Paare aufgeteilt sein könne, die den Fugennamen als
Vorsatz tragen. Das trifft nicht zu. Ein Kontaktpaar trägt immer genau den
Namen seiner Bedingung (`fugen.py`: `ContactPair(name=kb.name, …)`; die
einzige andere Stelle, `Model.add_contact_pair`, nimmt den Namen, wie er
kommt), und beim Neuvernetzen werden alte Paare über **Namensgleichheit**
abgeräumt. Der Präfixtreffer war darum nie das gemeinte Paar, sondern ein
fremdes, und bei zwei Treffern entschied die Reihenfolge, in der die
Einträge im Lastfall stehen.

Gemessen an getrennten Würfelpaaren (je 1 m² Fuge, 100 µm, Sollwert der
Presskraft δ·E/(2·L)·A = 10 500 000 N):

| Fall | vorher | jetzt |
|---|---|---|
| „Fuge (2)“, Übermaß nur auf „Fuge“ | 10 499 371 N | 0 N |
| „Deckel_2 (Typ 1)“, Einträge „Deckel“ 100 µm, „Deckel_2“ 20 µm | 10 499 371 N | 0 N |
| dasselbe, Einträge in umgekehrter Reihenfolge | 2 099 874 N | 0 N |

Die Fugen mit genauem Treffer („Fuge“, „Deckel“, „Deckel_2“) rechnen
unverändert (10 499 371 N bzw. 2 099 874 N). Findet sich kein genauer
Eintrag, aber ein Präfix, gilt 0, und das Protokoll nennt die fremden
Einträge („… gehören zu einer anderen Fuge und wirken hier NICHT“); die
Zeile geht über `contact_log` in die Warnungen des Berichts
(`tests/test_uebermass.py`, `test_praefix_ist_keine_zuordnung`,
`test_mehrdeutiger_praefix_haengt_nicht_an_der_reihenfolge`).

#### Übermaß ohne Kontaktpaar dieses Namens (22.09.2026)

Ein Eintrag, dessen Namen **kein** Kontaktpaar trägt, wirkt nirgends - etwa
nach dem Umbenennen oder Aufteilen einer Fuge (RFEM-Import: aus „Achse“
werden „Achse (Typ 3)“ und „Achse (Typ 4)“). Mit dem Präfixzweig galt er
dort noch; ohne ihn nannte die Zeile je Teilfuge ihn „zu einer anderen Fuge
gehörig“, obwohl es keine Fuge „Achse“ gab, und ein Eintrag ohne jede
Namensverwandtschaft fiel ohne Zeile weg. Jetzt:

* `ContactSystem._build` hält die Namen aller Paare (`_paarnamen`), und
  `_fugen_uebermass` nennt als „fremd“ nur Einträge, die eine andere Fuge
  wirklich trägt;
* `_uebermass_ohne_fuge` schreibt nach dem Aufbau aller Paare je Eintrag
  ohne Paar eine Zeile „Übermaß „Achse“: kein Kontaktpaar trägt genau diesen
  Namen - das Übermaß wirkt nirgends, auch nicht an „Achse (Typ 3)“, …“. Das
  Wort „zugeordnet“ steht mit Absicht nicht darin: `report/html.py` lässt
  Zeilen mit diesem Wort aus den Warnungen des Berichts.

Gerechnet wird wie zuvor ohne diesen Eintrag (beide Teilfugen 0 N). Die
Zeile steht im Aufbauprotokoll (`_baulog`) und damit in jedem Lastfall, der
das Kontaktsystem wiederverwendet. Ohne jede Kontaktfuge gibt es kein
Kontaktsystem und keine Zeile - dort müsste `Model.check()` den Eintrag
nennen, das tut es noch nicht (`tests/test_uebermass.py`,
`test_uebermass_ohne_fuge_wird_benannt`).
### 4.0b Laufbuch je Lastfall: jeder Kontaktlauf einzeln, Wechselarten je Runde (22.09.2026)

`solver._kontakt_info_sammeln`, `solver._laufbuch_eintrag`, `solver._fliessarten`,
`solver._startherkunft_eintragen`, `contact.RUNDEN_FELDER`,
`ContactSystem.runden`, `ContactSystem.endzustand_kennung`

**Warum.** Mit Fließen rechnet ein Lastfall viele Kontaktläufe — am
Drehlager zwölf für LF1. `res.info` führte davon nur Summen
(`contact_iterations`, `contact_factorisations`) und seit dem 22.09.2026
drei Zählwerte (`contact_laeufe`, `contact_letzter_lauf_konvergiert`,
`contact_laeufe_nicht_konvergiert`). Welcher der zwölf Läufe gedeckelt war,
in welcher Laststufe, und welche Art Zustandswechsel die 40 Runden des
Deckels gefüllt hat, stand nirgends. Die Abhilfen hängen aber genau daran:
Öffnen und Schließen reibungsfreier Fugen verlangt etwas anderes als neues
Gleiten an der Reibstelle oder Fließen einer Grenzkraft. Das Laufbuch ist
**reine Buchführung** — nichts davon geht in Zustand, Matrix,
Faktorisierungsschlüssel oder Abbruch zurück.

**Je Kontaktlauf ein Eintrag, nie zusammengefasst.** `res.info["laeufe"]` ist
eine Liste; `_kontakt_info_sammeln` baut den Eintrag **vor** der Summierung
aus dem `cinfo` genau dieses Laufs. Felder:

| Feld | Bedeutung |
|---|---|
| `nr` | 1, 2, … in der Reihenfolge der Läufe |
| `art` | `Lastfall` (ohne Fließen), sonst `Vorlauf` (nur verschachtelt, § 5e.3), `Laststufe`, `Newton`, `Abnahme` (gemeinsam: Newton-Schritt mit vollem Kontakt am Ende einer Stufe), `Fliessschritt` (Anfangsdehnung), `Abschluss`; bei einem Abbruch in der Fließ-Iteration vorläufig `Fliessen` |
| `stufe`, `schritt`, `tangente` | nur bei Fließen: Laststufe, Schritt darin, ob mit der konsistenten Tangente gelöst wurde |
| `schritte`, `faktorisierungen` | dieses Laufs (Summe über alle = die bisherigen Summenwerte) |
| `konvergiert`, `grund` | `grund` ist `''` oder `deckel`, `max_iter`, `probelauf`, `eingefroren`, `abbruch`, `abgekuerzt` (seit 23.09.2026) |
| `abgekuerzt` | wahr, wenn die gemeinsame Iteration den Lauf mit Absicht nach einem Schritt beendet hat (§ 5e.3) |
| `verworfen` | nur vorhanden, wenn wahr (seit 24.09.2026): die gemeinsame Iteration hat die Laststufe dieses Laufs aufgegeben und vom Startwert an verschachtelt wiederholt (§ 5e.3) |
| `warm`, `neustart` | Start aus einem Kontaktzustand angenommen; Warmstart verworfen oder zurückgesetzt und neu gerechnet |
| `start_von_lauf` | Nummer des Laufs, dessen Zustand der Start war; 0 = der dem Lastfall angebotene Start; `None` = kalt; −1 = ein von außen übergebener Zustand unbekannter Herkunft |
| `zyklen`, `phase`, `n_aktiv`, `n_gleitet` | Zustand am Ende des Laufs (`cycles`, Phase, geschlossene und gleitende Bedingungen) |
| `runden` | je Kontaktschritt ein Zahlentupel nach `contact.RUNDEN_FELDER` (unten) |
| `endzustand_kennung` | 16 Hexziffern, prozessfest (unten) |
| `u_max` | größte Knotenverschiebung [m], Betrag nur über die drei Verschiebungen — dasselbe Maß wie „max\|u\|" der Drehlager-Messungen |

`contact_laeufe`, `contact_letzter_lauf_konvergiert` und
`contact_laeufe_nicht_konvergiert` werden seitdem aus dem Laufbuch
**abgeleitet** (Länge, letzter Eintrag, Zahl der nicht konvergierten), nicht
mehr getrennt hochgezählt. Seit dem 23.09.2026 zählen abgekürzte Läufe nicht
unter den nicht konvergierten und kleben nicht an `contact_converged`; ihre
Zahl steht in `contact_laeufe_abgekuerzt`, und der letzte Lauf muss
konvergiert sein (§ 5e.3). Seit dem 24.09.2026 ebenso die verworfenen; wird
eine Stufe wiederholt, leitet `_laufbuch_zaehlen` `contact_converged` und die
Zahl der nicht konvergierten neu aus dem Laufbuch ab, und
`contact_laeufe_verworfen` zählt die verworfenen, die nicht schon als
abgekürzt zählen (damit „N von M“ der Rechenliste eine einfache Differenz
bleibt). Ein Kontaktabbruch (`KontaktAbbruch`) bekommt in
`_teilergebnis_anhaengen` einen eigenen Eintrag mit Grund `abbruch`;
`faktorisierungen` ist dort `None`, weil der Lauf kein `cinfo` zurückgab.

**`konvergiert` und `grund`.** Für jeden Eintrag gilt `konvergiert ==
(grund == '')` — mit **einer** Ausnahme: ein eingefrorener Zustand
(`einfrieren=…`) meldet wie bisher `konvergiert = True`, trägt aber den Grund
`eingefroren`. Er hat nicht iteriert; ob seine Referenz konvergiert war, steht
bei der Referenz (`contact_frozen_from`). Der Grund folgt demselben Entscheid
wie der Meldetext am Ende von `solve_with_contact` (Probelauf vor Deckel vor
Schrittgrenze).

**Die Art ohne neue Signatur.** (Seit dem 23.09.2026 schreibt der Newton
mit Kontakt selbst mit, was er ruft — `info["aufrufe"]`, je Aufruf Art,
Laststufe, Schritt —, denn gemeinsam mit dem Kontakt gibt es Aufrufe, die
sich aus dem Verlauf nicht nachzeichnen lassen: die `Abnahme`, den Abschluss
mitten in der letzten Stufe und die Wiederholung einer Stufe. Liegt die Liste
vor, gilt sie; das Nachzeichnen bleibt für den Anfangsdehnungsweg und den
Newton ohne Kontakt.) `plastizitaet.iteration` wird aus Tests mit
einem einfachen `loesen` gerufen; ein zusätzlicher Rückruf hätte jede dieser
Stellen berührt. Stattdessen merkt sich `_plastizitaet_rechnen` je
Löseraufruf, welcher Laufbuch-Eintrag entstand und ob eine Tangente `dK`
dabei war, und `_fliessarten` zeichnet die Folge nach dem Ende aus
`info["verlauf"]` nach: im Newton-Weg je Laststufe ein Aufruf zu Beginn, dann
je Schritt, der die Toleranz verfehlt, einer (`not (diff <= toleranz)`, wie
dort — auch ein NaN zählt gleich), zum Schluss der Abschluss; im
Anfangsdehnungsweg je Schritt ein Aufruf. Stimmt die Zahl der Aufrufe nicht
oder trägt ein Aufruf eine Tangente, wo keiner eine haben kann, bleibt es bei
`Fliessen` — eine falsche Zuordnung wäre schlimmer als eine grobe.
`start_von_lauf` entsteht über **Identität** (`is`) des übergebenen
Kontaktzustands mit dem, den ein früherer Lauf hinterließ — ohne Kopie und
ohne Vergleich von Inhalten.

Am Block mit Reibung und Fließen (`_fliessendes_kontaktmodell`, 2 Laststufen,
22.09.2026) sieht das so aus: Vorlauf 21 Schritte, Laststufe 1 21 Schritte
(kalt, denn sie bekommt den Start des Lastfalls, nicht den des Vorlaufs),
Laststufe 2 6 Schritte mit Neustart, Newton 2/1/1, Abschluss 1 — 53 Schritte
in 7 Läufen, wie `contact_iterations` sagt. Mit `MAX_CYCLES = 1` sind Läufe
1 bis 6 gedeckelt, der Abschluss nicht. Dabei zeigt sich ein Befund, der
bisher nur hergeleitet war: **kein Lauf startet vom Zustand des Vorlaufs**
(`start_von_lauf` ist nie 1). Der Vorlauf kostet mit Fließen einen vollen
Kontaktlauf und reicht nichts weiter.

**Wechselarten je Runde** (`ContactSystem.runden`). `_update_states` hängt je
Aufruf — also je Kontaktschritt — ein Zahlentupel an; `initialize`,
`zustand_setzen` und `__init__` beginnen die Liste neu (ein Stumpf aus
`object.__new__` bekommt sie beim ersten Aufruf). Gezählt werden
**Ereignisse**, nicht Bedingungen:

* `schliessen_reib`/`schliessen_frei`, `oeffnen_reib`/`oeffnen_frei` — Reibstelle
  heißt `ct` vorhanden und μ > 0 oder Haften;
* `fliessen_an`, `fliessen_aus` — Grenzkraft erreicht, Entlastung;
* `gleiten_neu` — Haften → Gleiten mit echtem Kegelverstoß (μ·Fn > 0);
  `gleiten_nach_schliessen` — bei μ·Fn = 0 und in derselben Runde geschlossen;
  `gleiten_ohne_fn` — bei μ·Fn = 0, schon vorher geschlossen. Ein wieder
  geschlossener Reibknoten trägt Fn = 0 aus der offenen Runde; jede
  Schubverschiebung liegt dann „über" der Grenze, und in Phase 2 steht er mit
  dem Verhältnis ∞ ganz vorn in der Reihe. Das ist kein Kegelverstoß und
  wird darum getrennt gezählt;
* `haften_zurueck`, `richtung` — Phase 1: Gleiten → Haften, Gleitrichtung
  nachgeführt;
* `eingefroren_neu` — nach acht Wechseln festgehalten; beim
  **Öffnungsversuch** ändert sich `active` dabei nicht, es zählt dann nur
  hier;
* dazu `bedingungen` (verschiedene Bedingungen mit Ereignis), `verstoesse`
  (Phase 2: haftende Knoten über dem Kegel), `H` (haftende Reibknoten vor der
  Umstellung — dieselbe Zahl wie `haftend` in der Anteilsregel), `a`
  (Gleitanteil der Runde), `guete`, `dF_slip` (beide auf f_ref bezogen) und
  `ganz_rutschend` (Gruppen, deren aktive Reibknoten alle gleiten).

Eine Runde mit mindestens einem Ereignis ist genau eine, die `changed`
meldet — jede Stelle, die `changed` setzt, zählt ein Ereignis. Darum ist die
Zahl der Phase-2-Runden mit Ereignis seit dem letzten Rücksetzen gleich
`cycles`, und die Deckelzeile in `ContactSystem.update` fasst genau die
gezählten Runden zusammen: „Kontakt: Nachpruefung der Reibung nach 40
Zustandswechseln abgebrochen - in 40 Runden: 31 mit Öffnen/Schließen
reibungsfreier Bedingungen (212 Wechsel), 12 mit neuem Gleiten (340 Knoten)"
(Zahlen hier zur Form; am Drehlager noch nicht gemessen). Die Zeile wird in
`_kontakt_info_sammeln` weiterhin wie jede Meldung ohne Laufnummer
zusammengefasst, wenn sie wörtlich gleich ist; die Zuordnung zum Lauf steht
im Laufbuch.

**Endzustand-Kennung** (`ContactSystem.endzustand_kennung`). `signatur()` hasht
mit dem eingebauten `hash()`, und der ist je Prozess anders gesät
(PYTHONHASHSEED) — als Faktorisierungsschlüssel innerhalb eines Laufs richtig,
zum Vergleich zweier Rechnungen unbrauchbar. Die Kennung ist
`hashlib.blake2b` (8 Byte) über Phase, Zahl der Bedingungen, die gepackten
Bitfelder aktiv/gleitet/fließt/Schubhalt und die sortierten ganz rutschenden
Gruppen. **Nicht** darin stehen Normalkräfte und Gleitrichtungen: sie leben
nur im Lastvektor F_c. Gleiche Kennung heißt gleiche Aktivmenge, gleiches
Haften/Gleiten und Fließen — nicht gleiche Kräfte. `test_kontaktzustand`
hält einen festen Wert für einen von Hand gesetzten Zustand fest und prüft
ihn unter zwei Hash-Saatwerten in eigenen Prozessen.

**Warmstart-Herkunft je Lastfall.** `res.info["start_angeboten_von"]`
(„Lastfall LF1", „Kombination K1", „System ‹Situation›" oder `None`) und
`res.info["start_genutzt"]` stehen getrennt, denn angeboten ist nicht
genutzt: `zustand_setzen` lehnt fremde Sicherungen ab, der Warmstart kann
verworfen werden, ein eingefrorener Zustand rechnet mit seiner Referenz.
`start_genutzt` ist wahr, wenn ein Lauf mit `start_von_lauf == 0` warm
endete. Die Herkunft wird nur fortgeschrieben, wenn ein Lastfall wirklich
einen Zustand hinterlässt — nach einem eingefrorenen LF2 startet LF3 vom
Zustand von LF1, und genau das steht dann da. `StaticSystem` trägt dazu
`kontaktzustand_von`. Im **Ausfallweg** (`solve_with_ausfall`) wird kein Start
weitergereicht; dort steht immer `None` mit `start_vermerk = "Ausfallweg ohne
Warmstart"`.

**Bitgleich — gemessen.** Vor dem Einbau (Stand 54b6f9a) und danach wurden
dieselben 13 Rechnungen mit `solver_threads = 1` ausgeführt: Block mit
Reibung; mit Fließen im Newton- und im Anfangsdehnungsweg; beides mit
`MAX_CYCLES = 1`; vier Lastfälle warm hintereinander (einer mit verworfenem
Warmstart); eine Kombination mit Warmstart; drei Lastfälle mit Einfrieren.
Verglichen per `tobytes()`: u, Reaktionen, `solid_res` und Kontaktkräfte —
**65 von 65 Feldern bitgleich**, dazu die acht Kontakt-Kennzahlen je Rechnung
gleich. Dass der Vergleich scharf ist, zeigt die Gegenprobe: mit
`SLIP_STIFFNESS_FINE` um 10⁻⁷ relativ verstellt sind 52 der 65 Felder
verschieden. Zwei Läufe des alten Stands untereinander: 65 von 65 bitgleich.

**Was es kostet.** Je Runde ein Durchlauf mehr über die Gruppen
(`_full_slip_groups`) und einige Zähler in der Schleife; je Lauf die Kennung
(vier Bitfelder). Gegen rund 3,5 s je Faktorisierung am Drehlager ist das
nicht messbar, gemessen ist es dort aber nicht. Ein Rundentupel belegt rund
384 Byte im Speicher und rund 68 Byte gepickelt (gemessen an einem Tupel mit
Drehlager-Größen); bei 150 Runden je Lastfall sind das 57 kB bzw. 10 kB.

**Grenzen.** Der Ausfallweg sammelt nur das `cinfo` des letzten inneren
Kontaktlaufs; ein Deckel in einem früheren Ausfallschritt bleibt unsichtbar.
Ein erster Versuch, der vor der Hilfsfesselung scheitert, hinterlässt keinen
Eintrag (er zählt auch nicht in `contact_laeufe`). `contact_iterations` nach
einem Abbruch ist wie bisher nur die Schrittzahl des abgebrochenen Laufs,
nicht die Summe.

#### 4.0b-1 Gegenprüfung: Bericht, Ketten und Aufträge (22.09.2026)

**Die Rundenbilanz zerlegte die Bündelung im Bericht.** Der Bericht zeigt
für die Ergebnisse ohne eigene Kontakttabelle jede Kontaktmeldung **einmal**,
mit der Zahl der Ergebnisse, die sie tragen (`report/html.py`, Warnungsliste
wächst um höchstens die Zahl der verschiedenen Texte). Gebündelt wird nach
dem Text. Die Deckelzeile des Kontaktsystems war bis zum Laufbuch ein fester
Text; mit der Rundenbilanz („ - in 40 Runden: 31 mit …") hat sie je Lauf und
Lastfall andere Zahlen, und jeder gedeckelte Lauf hätte eine eigene
Warnzeile bekommen — am Drehlager bis zu 422 × 12. Die Bündelung schneidet
die Bilanz deshalb ab wie die Laufnummer „(Kontaktlauf n)"; die Zahlen stehen
je Lauf im Laufbuch. Dabei fiel ein zweiter Fehler auf, der schon mit der
Laufnummer bestand: ein Ergebnis mit mehreren gedeckelten Läufen trägt
dieselbe Art mehrmals und wurde **mehrmals** gezählt („12 weitere Ergebnisse"
für eines). Gezählt werden jetzt Ergebnisse, nicht Zeilen.
`tests/test_report.py::test_deckelzeilen_mit_rundenbilanz_werden_gebuendelt`:
drei Ergebnisse mit je zwei gedeckelten Läufen verschiedener Bilanz ergeben
eine Warnzeile „(3 weitere Ergebnisse …)"; ohne die Änderung waren es sechs
Zeilen zu je „1 weitere Ergebnisse". Im `contact_log` **eines** Ergebnisses
steht die Deckelzeile dagegen je gedeckeltem Lauf einmal — wörtlich gleich
sind zwei Bilanzen selten, und dort gehört die Zahl hin.

**Kette.** Auf dem Kettenweg (`_cases_in_ketten`) trägt jedes Ergebnis
`res.info["kette"]` = (Nummer der Kette, Zahl der Ketten). Der erste Lastfall
jeder Kette startet kalt; ohne diese Angabe stünde mitten in der Reihe ein
`start_angeboten_von = None`, das sich von einem Fehler nicht unterscheiden
lässt (Vorschlag 5 des Entwurfs, von der Gegenprobe bestätigt).

**Auftrag.** Eine nichtlineare Kombination, die als eigener Auftrag rechnet
(`use_jobs`, `jobs._job_solve_combination`), baut ihr System neu und beginnt
kalt; seriell beginnt dieselbe Kombination warm vom Zustand des letzten
Lastfalls. Bei Reibung hängt der Endzustand vom Weg ab (hergeleitet; wie
stark sich das zeigt, ist nicht gemessen). Der Auftrag vermerkt es als
`start_vermerk = "Auftrag ohne Warmstart"`; der Vermerk des Ausfallwegs hat
Vorrang, weil der auch seriell nie einen Start weiterreicht.
`tests/test_kontaktzustand.py::test_kette_und_auftrag_stehen_im_ergebnis`
(ohne Prozesse: `run_jobs` ersetzt, der Auftrag im selben Prozess).

**Bitgleich, unabhängig nachgemessen.** Stand 54b6f9a gegen das Laufbuch
(72698df), je ein frischer Prozess, `workers = 1`, `solver_threads = 1`:
Block mit Reibung, derselbe mit `MAX_CYCLES = 1`, Fließen (Newton) mit und
ohne Deckel 1, Anfangsdehnung, drei Lastfälle warm hintereinander. sha256
über u, Reaktionen, `solid_res` und Kontaktkräfte sowie sechs
Kontakt-Kennzahlen: **80 von 80 gleich**. Fließen ohne Deckel: 53 Schritte in
7 Läufen, mit Deckel 1 sechs Läufe nicht konvergiert und der letzte
konvergiert — wie oben beschrieben.

**Nicht gebaut** (offen für die nächste Stufe): `res.info["nachweis"]` aus
Punkt 6 des Entwurfs (mit `vorlauf_ohne_zustandsuebergabe` und den
gedeckelten Läufen, wie die Gegenprobe es vorschlägt) — die Angaben sind aus
dem Laufbuch ableitbar, die Zusammenfassung gehört aber zur Kennzeichnung
(Vorschlag 2) und wird dort entschieden. Ebenso die Einträge der inneren
Kontaktläufe des Ausfallwegs (siehe „Grenzen").

### 4.1 Lager mit Ausfall, Schlupf, Reibung und Grenzkraft

Knoten-, Linien- und Flächenlager werden zunächst einheitlich auf
Knotenfreiheitsgrade umgelegt (`statik3d/supports.py`): Linienlager über die
Einflusslänge (halbe Nachbarabschnitte), Flächenlager über die Einflussfläche
der Knoten. Lineare Anteile (starr, Feder) gehen in die Sperrung bzw. in die
Steifigkeitsmatrix, nichtlineare Anteile in dieselbe Aktivmengen-Iteration wie
der Kontakt.

**Flächenlager in Flächenachsen** (`SurfaceSupport.lokal`, so setzt RFEM
sie): der Freiheitsgrad 2 des Lagers wirkt in der Normalen der Fläche, 0 und
1 in der Fläche, die Reibung bezieht sich auf die Normale. Nach dem Vernetzen
werden die Knoten je Normalenrichtung gruppiert (`supports.normalengruppen`):
die Normale kommt aus den Facetten des Netzes — die Außennormale des Körpers,
am gegenüberliegenden Knoten geprüft (Kapitel 4.0) —, bei abgebildeten
Hexaedern aus der Facettenebene, vom Schwerpunkt des Körpers weg. Eine Fläche
ohne Körper zeigt zur negativen Achse (das Lager liegt „unten", wie beim
globalen Lager). Schräge Flächen werden der nächsten Achse zugeschlagen und
genannt. Auf der positiven Seite (Normale +) tauschen Zug- und Druckausfall
die Rolle: ins Lager hinein heißt dort u > 0. An einer Kante (Boden/Knagge)
schlägt die Normale die Flächenrichtung der Nachbargruppe, und jede
Flächenrichtung steht je Knoten nur einmal. Geprüft am Klotz 2 × 1 × 1 m auf
Bettung mit Knagge (`tests/test_supports.py`): 50 kN gegen die Knagge gehen
ganz in sie (Rx = 49 999,9 N, u_x = 0,0005 mm), von ihr weg meldet das Modell
das Gleiten (Reibung 10 kN < 50 kN); global gesetzt trug nur die Reibung
(Rx = 10 kN). Am Drehlager sind 44 der 50 Lagerflächen senkrecht (Knaggen);
global gesetzt glitt die Grundplatte unter 3969 kN rechnerisch 3,7 m.

**Lager mit Geometriebezug** (RFEM: Linienlager an Linien, Flächenlager an
Flächen) kennen ihre Linien bzw. Flächen und werden vor jeder Rechnung auf
das aktuelle Netz gebracht (`supports.lager_auf_netz`): Ein Linienlager
bekommt alle Netzknoten, die auf seinen Linien liegen (Abstand zur
abgetasteten Kurve ≤ 0,2 % der Linienlänge), in Reihenfolge der Bogenlänge;
die Einflusslängen folgen daraus. Ein Flächenlager bekommt die Knoten und
Einflussflächen aus den Facetten des Netzes auf seinen Flächen — bei
Schalen die Elemente, bei Volumen die Randseiten des Körpers auf der
Fläche (fehlen sie, die Außenfacetten des Körpers in der Ebene der Fläche);
jede Facette gibt ihren Inhalt gleichmäßig an ihre Knoten (Dreieck A/3,
Viereck A/4). Flächen ohne Netz behalten die Eckknoten der Randlinien mit
dem Flächeninhalt gleich verteilt. Damit ist Σ Einflussflächen = Inhalt der
vernetzten Fläche und Σ Einflusslängen = Linienlänge — die Bettung c·A
wirkt über die ganze Fläche, nicht als vier Eckfedern (Test
`test_lager_folgen_dem_netz`: steife Platte auf Bettung setzt sich um p/c).

Ein Lagerfreiheitsgrad wirkt entlang der positiven Achse. Mit der
Knotenverschiebung u ist die Lagerkraft F = −k·u; u < 0 (Knoten drückt hinein)
bedeutet **Druck**, u > 0 **Zug**. Daraus folgt die Umsetzung als
Kontaktbedingung mit dem Spalt g = g₀ + c·u:

| Einstellung | Bedingung |
|---|---|
| Ausfall bei Zug | c = +1, g₀ = Schlupf – aktiv, solange gedrückt wird |
| Ausfall bei Druck | c = −1, g₀ = Schlupf – aktiv, solange gezogen wird |
| nur Schlupf | zwei Bedingungen (c = ±1), das Lager wirkt außerhalb ±Schlupf |
| Reibung μ | Tangentialrichtungen als eigene Koeffizientenzeilen; die Reibkraft ist auf μ·Fₙ des Bezugsfreiheitsgrads begrenzt (Haften/Gleiten wie in Kap. 4) |
| Grenzkraft | ab F = limit konstante Kraft mit Restfeder (Zustand „Fließen“); bei Entlastung wieder elastisch |

Rotationsfreiheitsgrade werden genauso behandelt (ohne Reibung); ihre Kräfte
erscheinen als Momente in den Auflagerreaktionen, nicht in den
Knotenkontaktkräften.

#### Einseitiges Lager mit dem Nullvektor als Richtung (22.09.2026)

`ContactSystem._build` normierte die Richtung eines einseitigen Lagers mit
`n /= norm(n) or 1.0`. Aus dem Nullvektor wurde so wieder der Nullvektor: die
Bedingung g = g₀ + nᵀu hatte die Zeile null, trug keinen Freiheitsgrad und
stand mit F_n = 0 und Status „Kontakt“ in der Ergebnisliste. Nur
`_tangent_basis` teilte 0 durch 0 (numpy: „invalid value encountered in
divide“, auf stderr, in keinem Protokoll). Das Spaltelement zehn Zeilen tiefer
fing denselben Fall schon ab. Gemessen am Träger 8 m (links eingespannt,
rechts in z gelagert, 10 kN/m, Lager in Feldmitte):

| Richtung | Zeilen in der Kontakttabelle | u_z Feldmitte | F_n |
|---|---|---|---|
| (0, 0, 1) | 1 | −3,62·10⁻¹⁰ m | 45 668,24 N |
| (0, 0, 0), vorher | 1 („Kontakt“) | −4,562031 mm | −0,0 N |
| (0, 0, 0), jetzt | 0 | −4,562031 mm | - |
| ohne Lager | 0 | −4,562031 mm | - |

Mit μ = 0,3 ging die NaN-Tangentenbasis als c_t in die Bedingung, und der Lauf
brach mit „Kontakt-Iteration 1: Gleichungssystem singulär“ ab, ohne das Lager
zu nennen (am Stand vor der Änderung gemessen). Jetzt wird die Bedingung wie
beim Spaltelement weggelassen und ins Protokoll geschrieben („Einseitiges
Lager Knoten 4: Richtung unbestimmt (Nullvektor) - bitte 'direction'
angeben“), mit und ohne Reibung. Der Lauf mit (0, 0, 0) ist seither
**bitgleich** mit dem ohne Lager (vorher wich u_z in der 15. geltenden
Ziffer ab, −0,004562030661418937 m gegen −0,004562030661418983 m, weil er
über die Kontaktiteration lief); die Gegenprobe mit (0, 0, 1) ist bitgleich mit
dem Stand davor (Prüfsumme der Verschiebungen unverändert).
`Model.check()` meldet den Fall schon vor dem Rechnen
(`tests/test_supports.py`, `test_einseitiges_lager_ohne_richtung`).

### 4.1a Halt für Teile ohne geschlossene Bedingung (19.09.2026)

Die Kontakt-Iteration öffnet und schließt Bedingungen, bis nichts mehr wechselt.
In einem Zwischenschritt kann dabei ein Bauteil *alle* seine Bedingungen
verlieren — dann ist es frei und das Gleichungssystem singulär. Das ist die
Linearisierung des Schritts, nicht die Physik: ein Stift in einer Bohrung
berührt sie immer irgendwo. Statik3D hält solche Teile deshalb künstlich fest,
und **wie** es sie hält, entscheidet die Form der Fuge.

Gemessen wird das, nicht vermutet (`solver._schub_traegt`): für die sechs
Starrkörperbewegungen des Teils wird aufgestellt, wie sehr sie die
Tangentialzeilen seiner Haft- und Reibbedingungen dehnen, und aus dem
Verhältnis von kleinstem zu größtem Singulärwert abgelesen, ob die Schubbindung
allein trägt.

* **Eine Bohrung fasst den Stift rundum.** Sie trägt ihn allein über den Schub.
  Am Drehlager (19.09.2026, 2.974.344 Freiheitsgrade, 31.134 Bedingungen, 102
  Teile mit Kontakt) halten die Normalrichtungen der zehn betroffenen Stifte
  für sich genommen 2,2·10⁻¹³ bis 3,6·10⁻¹³ — also nichts —, der Schub aller
  ihrer Bedingungen dagegen 0,536 bis 0,707.
* **Eine ebene Fuge hält quer zu ihrer Ebene nichts**, mit Reibung so wenig wie
  ohne: dort ist das Verhältnis exakt 0. Zwischen beiden Fällen liegen
  Größenordnungen; die Schwelle `SCHUB_GRENZE` = 10⁻³ liegt weit von beiden
  Seiten entfernt.

Trägt der Schub, so bleibt die Tangentialsteifigkeit **aller** bindenden
Bedingungen des Teils wirksam, obwohl sie offen sind — ohne Normalfeder und
ohne den Lastanteil aus dem Spaltmaß. Die Komplementarität in Normalrichtung
bleibt damit unberührt, und es entsteht keine Kraft, die das Teil an die Fuge
zöge. Dass es *alle* sein müssen, ist gemessen: der Schub aus nur drei
Bedingungen — so viele hielt die frühere Fassung fest — kommt an zwei der zehn
Stifte auf 2,3·10⁻¹⁸ und hält sie damit ebenfalls nicht.

Trägt der Schub nicht, bleiben wie bisher `HALT_MINDESTENS` Bedingungen mit dem
kleinsten Spalt geschlossen.

Beide Halte sind für den Schritt gedacht, nicht für das Ergebnis. Sobald das
Teil wieder anliegt, wird der Schubhalt gelöst. Trägt er am Ende der Iteration
noch Kraft, während alle Bedingungen des Teils offen stehen, stützt sich das
Ergebnis auf eine Bindung, die es nicht gibt: dann bricht die Rechnung ab und
nennt die Fuge, die Zahl der Bedingungen und den getragenen Schub — dieselbe
Regel und dieselbe Schwelle wie für Zug an normal gehaltenen Punkten.

Vorher brach das Drehlager nach 33 Kontakt-Iterationen mit zehn angeblich
abhebenden Bauteilen ab. Die Ursache war der Halt selbst: er schloss
Normalbedingungen, deren Lastanteil −kₙ·g₀·cₙ das Teil an die Fuge zieht, und
am Ende fand die Prüfung genau dort Zug.

### 4.2 Federgelenke

Ein Stabendgelenk mit Federsteifigkeit k wird exakt als Reihenschaltung
Stab + Feder gerechnet (`assemble.hinge_springs`): Für den betroffenen lokalen
Freiheitsgrad wird ein innerer Freiheitsgrad eingeführt, den das Element belegt;
die Feder verbindet ihn mit dem äußeren Freiheitsgrad, danach wird der innere
statisch kondensiert. Für k → ∞ ergibt sich die biegesteife Verbindung, für
k → 0 das Gelenk. Die Stabendkräfte werden aus den zurückgerechneten inneren
Verschiebungen bestimmt.

Probe (Einfeldträger, links elastisch eingespannt, Gleichlast q):
M = qL²/8 / (1 + 3EI/(kL)); die Rechnung trifft diesen Wert; die verbleibende
Abweichung von 0,7 % ist die Schubverformung des Timoshenko-Balkens, die in der
Handformel fehlt.

### 4.3 Probelauf: ein Kontaktschritt für die Netzsteuerung (20.09.2026)

Die adaptive Vernetzung (`adaptiv.adaptiv_vernetzen`) rechnet je Durchgang
einen Lastfall, braucht davon aber nur **eines**: den Sprung der Spannung
zwischen Nachbarelementen, aus dem der Zienkiewicz/Zhu-Indikator die neue
Kantenlänge bildet. Das ist ein Netzmaß, kein Nachweis. Ein voller Lastfall am
Drehlager kostet 235 s, davon 48 Kontaktschritte (gemessen 19.09.2026) — für
die Netzsteuerung ist das Geld zum Fenster hinaus.

`solver.solve_static(model, probelauf=True)` rechnet deshalb

* **einen** Kontaktschritt (`solve_with_contact` mit `max_iter = 1`),
* aus dem **Anfangszustand** der Fugen — ein Warmstart aus einem Nachbarlastfall
  wird bewusst nicht genommen, damit jede Netzrunde dieselbe Lage misst,
* **mit Plastizität** — nur der Kontakt bleibt bei einem Schritt,
* und bei Ausfallstäben ebenso nur eine Aktivmengen-Runde.

**Der Warmstart *innerhalb* des Lastfalls bleibt** (berichtigt am 21.09.2026).
Verworfen wird nur der des **vorigen Lastfalls**, damit jede Netzrunde dieselbe
Lage misst. Bis dahin warf dieselbe Zeile auch den Zustand weg, den die
Plastizitätsschleife je Fließschritt durchreicht — jeder Fließschritt fing den
Kontakt wieder bei der Geometrie an. Am Drehlager gemessen (Löser-Sitzung):
**8,97 %** andere Vergleichsspannung und ein um **2,1 %** steiferes Ergebnis
(0,2657 statt 0,2715 mm) — Kontakte, die sich nicht setzen konnten, machen
steifer. Die Rangfolge blieb dabei dieselbe (100 von 100 Spitzenelementen), das
Netzmaß war also brauchbar; der Lauf war nur nicht der, den das Handbuch
beschrieb. Die Zahlen oben (2,3 %, 198,8 s) gelten für den Lauf **mit**
Warmstart, und seit der Berichtigung tut der Schalter genau das.

**Die erste Fassung ließ das Fließen aus, und das war falsch** (berichtigt am
21.09.2026). Die Begründung lautete: für den Sprung zwischen Nachbarelementen
genüge die elastische Spannung. Am Drehlager gemessen stimmt das nicht —
elastisch trifft der Probelauf nur **54 von 100** Spitzenelementen (L2-Abweichung
52,2 %), plastisch **100 von 100** (2,3 %). Er verfeinerte an den falschen
Stellen. Der Preis ist klein: **199 statt 124 s gegen 633 s** für den vollen
Lauf — bei 645 934 Elementen ist das Aufstellen der Matrix der Brocken, nicht
die Zahl der Schritte. Der Faktor gegenüber dem vollen Lauf ist damit rund 3,
nicht 48.

**Das Ergebnis ist ein Netzmaß, kein Rechenergebnis — und das ist schärfer
gemeint, als es klingt.** `res.contact_forces` liegt um **Faktor 834** daneben
(9,276·10⁸ N gegen 1,112·10⁶ N, Drehlager LF1, 21.09.2026), damit auch
Fugenkräfte, Pressungen, Bolzennachweise und die Auflagerkräfte einseitiger
Lager. Verschiebung (0,04 %) und Spannung (2,3 %) stimmen dagegen — warum die
Kontaktkräfte es nicht tun, ist **nicht geklärt**. Wer aus einem Probelauf
etwas anderes als ein Netzmaß liest, liest falsch.

`Results.info["probelauf"]`
steht auf wahr, `contact_converged` auf falsch, und das Kontaktprotokoll sagt
„Probelauf: ein Kontaktschritt gerechnet, nicht auskonvergiert — das Ergebnis
ist ein Netzmaß, kein Nachweis“ statt der gewohnten Meldung über eine nicht
konvergierte Iteration.

**Gemessen am Drehlager, LF1 kalt** (Löser-Sitzung, 21.09.2026):
Vergleichsspannung je Element aus `res.solid_res` gegen den vollen Lauf.

| | Zeit | L2-Abweichung | dieselben Spitzenelemente |
|---|---|---|---|
| ein Kontaktschritt, **elastisch** (so war es gebaut) | 123,8 s | 52,2 % | **54 von 100** |
| ein Kontaktschritt, **plastisch** (so ist es jetzt) | 198,8 s | **2,3 %** | **100 von 100** |
| voller Lauf | 633,4 s | — | — |

**Der Gewinn ist Faktor 3, nicht Faktor 48.** Ein *einziger* Kontaktschritt
kostet am Drehlager schon 123,8 s, weil bei 645 934 Elementen das Aufstellen
der Matrix der Brocken ist und nicht die Zahl der Schritte. Die 75 s, die das
Fließen kostet, bringen dafür die ganze Genauigkeit.

**An einem kleinen Modell spart der Probelauf gar keine Zeit** (Block aus
8 `hex8`, 21.09.2026: 0,57 gegen 0,35 s). Die Plastizität braucht ihre
Schritte so oder so; die Kontaktiteration ist bei zwölf Elementen nicht der
Brocken. Was der Probelauf *immer* spart, sind Kontaktschritte je Fließschritt
— 1,14 statt 8,44 an diesem Block. Danach prüft
`tests/test_solver_ext.py::test_probelauf_und_kennzahlen`, nicht nach der Zeit:
eine Zeitprüfung an einem kleinen Modell hielte etwas fest, das keine
Eigenschaft des Verfahrens ist.

**Der Probelauf ist nicht an jedem Modell billiger — an manchen ist er teurer
als die Wahrheit.** Gemessen am Block aus 8 `hex8` gegen den Drehlager-Lauf
(21.09.2026):

| | Fließschritte | Kontaktschritte | L2 gegen den vollen Lauf |
|---|---|---|---|
| Block, Probelauf | **53** | 58 | 15,83 % |
| Block, voller Lauf | **16** | 135 | — |
| Drehlager, Probelauf | 10 | 12 | 2,3 % |
| Drehlager, voller Lauf | 10 | 98 | — |

Am Drehlager kostet der Probelauf dieselben zehn Fließschritte wie der volle
Lauf und spart die 86 Kontaktschritte — das ist der Fall, für den er gebaut
ist. Am Block braucht er **mehr als dreimal so viele Fließschritte wie der
volle Lauf**; die gesparten Kontaktschritte holen das nicht herein.

**Die Erklärung ist eine Vermutung, keine Messung** (Löser-Sitzung,
21.09.2026): nicht der Warmstart ist der Mechanismus, sondern `max_iter = 1`.
Mit einem einzigen Kontaktschritt je Fließschritt setzt sich der Kontakt nie;
das Ziel der Plastizität wandert mit jedem Schritt weiter, und die Toleranz
wird spät erreicht. Wo der Kontakt sich ohnehin setzt — am Drehlager 12
Kontaktschritte auf 10 Fließschritte, also fast einer je Schritt, und dann
steht er —, passiert nichts. Wo er wandert, weil das Bauteil kippt und
gleitet, jagt die Plastizität hinterher.

**Was das für den Aufrufer heißt:** wer den Probelauf als Sparweg nimmt, muss
nachsehen, ob er einer war. `res.info["plastizitaet"]["iterationen"]` steht
dafür bereit; liegt die Zahl deutlich über der eines vollen Laufs an einem
vergleichbaren Modell, war der Probelauf die teurere Wahl. Die adaptive
Schleife des Vernetzers prüft das Ergebnis ohnehin schon auf die Schlüssel
`probelauf` und `plastizitaet` — die Schrittzahl daneben zu halten, ist eine
Zeile mehr.

**Dass es wirklich eine Eigenschaft des Verfahrens ist, steht unabhängig
gemessen daneben** (Löser-Sitzung am Drehlager, 21.09.2026): dort 12
Kontaktschritte auf 10 Fließschritte im Probelauf gegen 98 auf 10 im vollen
Lauf — **1,2 gegen 9,8**. Zwei Modelle, die drei Größenordnungen auseinander
liegen (12 Elemente gegen 645 934), geben dasselbe Verhältnis. Und die Zeit
erklärt sich damit von selbst: am Drehlager fallen 86 Kontaktschritte zu je
rund 6 s weg, an einem Block aus acht Elementen ist ein Kontaktschritt
kostenlos — übrig bleibt dort nur der Aufbau, und der läuft in beiden Fällen.


### 4.4 Der Sechsflächner: was ihn trägt, und was er kostet (21.09.2026)

`hex8` ist der Sechsflächner — acht Knoten, sechs Vierseitflächen. Er trägt
Biegung über drei **inkompatible Wilson-Moden**, deren neun innere
Freiheitsgrade in der Elementmatrix kondensiert werden
(`elements.solid.hex8_matrices`, `k_hex8`). Die Taylor-Korrektur `detJ0/detJ`
hält dabei den Patch-Test aufrecht.

**Was das bringt** (Kragarm 2,0 × 0,1 × 0,2 m gegen Bernoulli mit Schubanteil):

| Netz | w/w_Balken |
|---|---|
| 4 × 1 × 1 — **ein** Element über Höhe und Breite | **96,2 %** |
| 8 × 2 × 2 | 97,2 % |
| 16 × 4 × 4 | 98,5 % |
| dasselbe 4 × 1 × 1 **ohne** die inkompatiblen Moden | **28,0 %** |

Faktor **3,43** am selben Netz — die Moden sind der ganze Unterschied, nicht
die Verfeinerung. Zum Vergleich brauchen `pent6` und `pyr5` in derselben
Prüfung 10 bzw. 6 Elemente in der Länge für ihre gröbste Stufe.

**Der Keil hat seit dem 22.09.2026 ebenfalls innere Moden** (`solid.PENT6_MODEN`):
die drei Kantenblasen L_a·L_b des Dreiecks — sie geben ihm den quadratischen Anteil
in der Ebene, die Querverschiebung einer Biegung wächst mit x² — und (1 − t²) für die
Querdehnung über die Dicke, je für drei Verschiebungen, zusammen zwölf, im Element
kondensiert wie beim `hex8`. Ihr Gradient wird um den Mittelwert über das Element
vermindert und mit det J₀/det J · J₀⁻¹ abgebildet; dann ist das Integral der
Modendehnung null, und der Patch-Test hält für jede Form (1,7·10⁻¹⁶). In Sweep-Netzen
sind rund 23 % der Elemente Keile. Gemessen am Kragarm-Prüfkörper, jede Zelle in zwei
Keile geteilt, σ_v an der Nachweisstelle (Soll 355 N/mm²):

| FHG | pent6 ohne Moden | pent6 mit Moden | hex8 am selben Gitter |
|---|---|---|---|
| 90 | −150,2 | −50,0 | −9,6 |
| 405 | −56,6 | −15,2 | +0,8 |
| 2 295 | −18,1 | −4,1 | +0,2 |

Das Soll des Auftrags — der Keil erreicht 1 N/mm² mit höchstens so vielen
Freiheitsgraden wie der `hex8` — ist damit **nicht erreicht**; der Keil bleibt rund
eine Verfeinerungsstufe hinter dem Sechsflächner zurück. Versucht und verworfen: nur
(1 − t²) (drei Moden) macht σ_xx eher schlechter (−129 / −44 / −12), nur die Blasen
(neun) endet in σ_xx bei +2,4 statt gegen null; die Projektion der Volumendehnung
wie beim `hex8` ändert am rechtwinkligen Keil nichts (seine Volumendehnung liegt
schon im linearen Raum). Mit Fließen rechnet der Keil wie der `hex8` Lobatto-Punkte
über die Dicke (`solid.pent6_regel_fuer`).

**Nahezu inkompressibel: die Volumendehnung ist linear projiziert (22.09.2026).**
Bis dahin rechnete der `hex8` die Volumendehnung punktweise an seinen 2 × 2 × 2
Gaußpunkten. Bei ν = 0,499 blieben so am Kragarm 8 × 2 × 2 noch 80,3 % der Lösung
bei ν = 0,3 — das sah nach „sperrt kaum“ aus, doch die **Spannung** zeigte es: an der
Nachweisstelle des Prüfkörpers (Kragarm 1,0 × 0,1 × 0,2 m, Oberkante bei L/2, nach
Saint-Venant exakt 355 N/mm²) lag σ_xx am Netz 8 × 2 × 4 um −51 N/mm², am Netz
4 × 1 × 2 um −509 N/mm² daneben — mit falschem Vorzeichen. Das ist der Druck: σ_v
blendet ihn aus, σ_xx nicht, und bei Fließen (volumentreu) trifft es auch die
Vergleichsspannung.

Heute wird die Volumendehnung θ = mᵀε je Element auf die Funktionen {1, ξ, η, ζ}
projiziert (B-bar mit linearem Druckansatz, im Rahmen von Simo/Rifai 1990), der
Deviator bleibt punktweise:

    θ̄(ξ) = q(ξ)ᵀ M⁻¹ Σ_gp w_gp q_gp θ_gp,   q = (1, ξ, η, ζ),   M = Σ_gp w_gp q_gp q_gpᵀ

Für die inneren Moden gilt dieselbe Projektion. `HEX8_VOLUMEN = "voll"` stellt den
alten Weg wieder her (für Vergleiche).

**Warum nicht die mittlere Dilatation** (ein Wert je Element, der übliche Weg für den
trilinearen Hexaeder): Zusammen mit den Wilson-Moden ist sie instabil. Das Feld
u = κ (xz, yz, (z² − x² − y²)/2) hat die Dehnung κ z · I — rein volumetrisch, Deviator
null —, ist mit den Moden darstellbar und hat, um die Elementmitte gemittelt, keine
Volumendehnung: keine Energie. Es setzt sich als Schachbrett über das Netz fort.
Gemessen: 9 statt 6 Nullmoden am regelmäßigen Element, der Kragarm 4 × 1 × 1 biegt
sich 44-fach durch. Der lineare Ansatz behält genau diesen linearen Anteil — 6
Nullmoden am regelmäßigen und am verzerrten Element, bei ν = 0,3 und 0,499.

Gemessen am Prüfkörper (σ_v bzw. σ_xx an der Nachweisstelle, Abweichung in N/mm²,
gemittelter Tensor der Elemente am Punkt, `tests/test_elemente_volumen.py`,
`t_hex8_volumensperre`):

| Netz | ν = 0,3 punktweise / linear | ν = 0,499 σ_v punktweise / linear | ν = 0,499 σ_xx punktweise / linear |
|---|---|---|---|
| 4 × 1 × 2 | −7,7 / −9,6 | −51,1 / −25,7 | −509 / +4,1 |
| 8 × 2 × 4 | +0,73 / +0,77 | −4,2 / −1,6 | −50,7 / +1,6 |
| 16 × 4 × 8 | +0,23 / +0,22 | +0,07 / +0,07 | −2,6 / +0,2 |

Die Biegung bei ν = 0,3 ändert sich ab 8 × 2 × 4 um höchstens 0,04 N/mm². Die
Verschiebung am Kragarm 8 × 2 × 2 bei ν = 0,499 liegt jetzt bei 93,0 % der Lösung
bei ν = 0,3 (vorher 80,3 %); der Rest ist zum Teil die 3D-Lösung selbst, denn die
Einspannung behindert die Querdehnung bei ν → 0,5 stärker. **Nicht erreicht** ist
„kein Unterschied“: am gröbsten Netz 4 × 1 × 2 liegt σ_v bei ν = 0,499 um 25,7
N/mm² daneben gegen 9,6 bei ν = 0,3; ab 8 × 2 × 4 sind beide unter 2 N/mm², ab
16 × 4 × 8 gleich.

Der lineare Tetraeder fällt bei ν = 0,499 auf 2,1 % (§ 6a). Die knotengemittelte
Dilatation, die für den `tet4` gebaut wurde, braucht der `hex8` nicht
(`assemble._dilatationsdaten` filtert ausdrücklich auf `tet4`).

**Verzerrt sperrt er (gemessen 22.09.2026, Auftrag A3).** Nach MacNeal (1987)
sperrt jedes Viereck mit vier Knoten, das den Patch-Test besteht, unter Biegung,
sobald es trapezförmig ist — und der `hex8` ist in jeder Ebene ein solches
Viereck. Am geraden Kragträger von MacNeal/Harder (1985; 6,0 × 0,2 × 0,1,
E = 10⁷, ν = 0,3, 6 × 1 × 1 Elemente, Endlast 1,0; `tests/messung_macneal.py`),
Verschiebung gegen den Sollwert:

| | Streckung | Querkraft in der Ebene | aus der Ebene |
|---|---|---|---|
| hex8 regelmäßig | 0,988 | 0,983 | 0,976 |
| hex8 Trapez (45°) | 0,994 | **0,047** | **0,030** |
| hex8 Parallelogramm (45°) | 0,994 | 0,625 | 0,531 |
| tet10 regelmäßig / Trapez / Parallelogramm | 0,993 | 0,962 / 0,940 / 0,930 | 0,957 / 0,938 / 0,933 |
| pent6 regelmäßig (mit Moden) | 0,984 | 0,031 | 0,099 |

Am Kragarm-Prüfkörper (1,0 × 0,1 × 0,2 m, Innenebenen in der Biegeebene um den
Faktor 0,4 der Zellänge gekippt, die Ebene durch die Nachweisstelle gerade;
σ_v dort gegen 355 N/mm²):

| FHG | hex8 regelmäßig | hex8 Trapez | hex8 Parallelogramm | tet10 Trapez (FHG) |
|---|---|---|---|---|
| 90 / 405 | −9,5 | −169,1 | −169,1 | +1,6 (405) |
| 405 / 2 295 | +0,8 | −32,8 | −34,8 | +0,6 (2 295) |
| 2 295 / 15 147 | +0,2 | −12,9 | −11,9 | −0,3 (15 147) |

Der verzerrte `hex8` konvergiert an der Nachweisstelle nur noch mit der
Elementlänge; die projizierte Volumendehnung (oben) ändert daran nichts (gleiche
Zahlen auf 0,4 N/mm²). Unsymmetrische (Petrov-Galerkin-)Elemente, die MacNeals Satz
umgehen, scheiden aus: `ama` rechnet nur symmetrisch. **Folgerung:** der `hex8` ist
das billigste Element für 1 N/mm² nur, wo der Sweep gute Sechsflächner liefert; an
verzerrten Stellen ist der `tet10` der robuste Weg (die Löser-Sitzung nimmt eine
Netzgüte-Schwelle in die Anweisung an den Vernetzer). Der Keil bleibt auch mit
Moden (oben) unter Biegung schwach, am meisten bei gestreckten Zellen.

**Geprüft ist er seit dem 21.09.2026 wie die übrigen Volumenelemente**
(`tests/test_elemente_volumen.py`): sechs Starrkörpermoden am **verzerrten**
Element, Patch-Test am verzerrten Verband (Verschiebung 8,1·10⁻¹⁷, Spannung
an allen 72 Auswertepunkten 9,7·10⁻¹⁶), monotone Konvergenzreihe. Diese
Prüfungen waren nach Elementtyp parametrisiert vorhanden, wurden für den
`hex8` aber nie aufgerufen — er stand nicht in der Liste der „neuen" Typen,
für die die Suite geschrieben worden war.

**Was er kostet, und was dagegen getan wurde.** Gemessen an verzerrten
Würfeln (21.09.2026):

| | µs je Element |
|---|---|
| `k_tet4` | 24,2 |
| `k_hex8`, einzeln | **571,7** |
| **`k_hex8_stapel`** | **57,5** |

Einzeln ist der Sechsflächner **dreißigmal** so teuer wie ein Tetraeder. Am
Drehlagernetz der Vernetzersitzung trugen damit **sieben Prozent der Elemente
einundsiebzig Prozent der Aufstellzeit** (31 108 `hex8` mit 17,8 s gegen
453 331 `tet4` mit 9,5 s). Der Grund war nicht die Physik, sondern der Aufruf:
acht Gaußpunkte mit kleinen Matrizen, einmal je Element durch Python.

`elements.solid.k_hex8_stapel` rechnet einen ganzen Stapel auf einmal
(`assemble._matrix_chunk` gruppiert die Sechsflächner eines Blocks nach
Werkstoff). Die acht Gaußpunkte bleiben eine Schleife — es sind acht. Zwei
Dinge machten den Faktor 9,9:

* **Stapel statt Einzelaufruf** brachte zunächst nur Faktor 2,7.
* **`matmul` statt `einsum`** brachte den Rest: 258,8 → 57,5 µs. Die
  Stapel-Matrixmultiplikation von numpy geht über BLAS, `einsum` rechnet sie
  bei diesen kleinen Matrizen selbst aus.

Am Drehlager sind das **17,8 s → 1,79 s je Aufstellen**, und das Aufstellen
läuft in jedem Kontakt- und Plastizitätsschritt. Das Ergebnis ist bis auf
6,9·10⁻¹⁶ dasselbe; `tests/test_elemente_volumen.py::t_hex8_stapel` hält es
fest, samt der Probe, dass ein umgestülptes Element auch im Stapel auffällt.

**Der `tet4` bleibt unangetastet.** Er kostet 24,2 µs, dort ist der Aufruf
nicht der Brocken, und ein Stapelweg brächte nichts — er läuft weiter
Element für Element durch `element_matrix`.

**Die Spannungsauswertung** war danach der teuerste Posten und ging
denselben Weg. Sie baute für jedes Element die volle Elementsteifigkeit neu
auf, nur um die inneren Freiheitsgrade α = −K_αα⁻¹ K_uα<sup>T</sup> u zu
bekommen — das K_uu darin liest niemand.

| | µs je Element |
|---|---|
| `stress_points("hex8", …)`, wie es war | **1 375,5** |
| ohne das ungelesene K_uu (`ohne_kuu=True`) | 1 040 |
| **`spannungen_hex8_stapel`** | **58,1** |

Das ist **Faktor 23,7**, und er kommt aus derselben Quelle wie bei der
Steifigkeit: ein Stapel, `matmul` statt `einsum`, und die neun Auswertepunkte
als eine kurze Schleife über den ganzen Stapel statt einer Schleife über die
Elemente. Am Drehlagernetz sind das **42,8 s → 1,81 s je Nachlauf**. Bei
kleinen Modellen, wo der Nachlauf neben dem Lösen mitzählt, schlägt das auf
die ganze Rechnung durch: ein Kragarm aus 864 Sechsflächnern braucht 0,32
statt 1,01 s, also ein Drittel.

`solver._post_chunk` sammelt die Sechsflächner eines Blocks vorweg nach
Werkstoff ein und fällt bei jedem Fehler auf den Einzelweg zurück — der
bleibt die Wahrheit, gegen die geprüft wird. Die Spannungen stimmen bis auf
3,0·10⁻¹⁶ (Element gegen Stapel) und die gerechnete Verschiebung auf
4,9·10⁻²¹ m überein; `tests/test_elemente_volumen.py::t_hex8_stapel` hält
beides fest, samt α und der Probe, dass `ohne_kuu` an K_uα, K_αα und dem
Volumen nichts ändert.

## 5 Nachweise nach DIN EN 1993-1-1

### 5.1 Nachweisstellen und Staebe

Ein Stab (Member) ist eine Kette von Stabelementen. Die Schnittgrößen
werden an `stations` Stellen je Element ausgewertet (Standard 9). Die
Klassifizierung erfolgt an jeder Stelle mit den dort wirkenden Schnittgrößen.

### 5.1a Theorie II. Ordnung und Ersatzimperfektionen (5.2 und 5.3)

**Wann ist sie nötig?** Nach 5.2.1(3) darf nach Theorie I. Ordnung gerechnet
werden, solange

      α_cr = F_cr / F_Ed ≥ 10   (elastische Berechnung)
      α_cr ≥ 15                 (plastische Berechnung)

α_cr folgt je Kombination aus dem linearen Verzweigungsproblem
(K + λ K_g) v = 0 mit dem Spannungszustand **dieser** Kombination als
Grundzustand. Die Einstellung `theorie2` kennt drei Werte: `aus`, `auto`
(α_cr je Kombination bestimmen und nur bei Unterschreitung am verformten
System rechnen) und `ein` (immer).

**Wie α_cr gelöst wird.** Gerechnet wird −K_g v = μ K v mit α = 1/μ;
α_cr ist der Kehrwert des größten positiven μ. K ist nach dem Einbau der
Lager positiv definit und dient dem Eigenwertlöser (ARPACK über `eigsh`)
als Skalarprodukt. −K_g taugt als Skalarprodukt
nicht: Sind Stäbe gezogen und andere gedrückt, ist −K_g indefinit. Genau
so stand es bis zum 23.09.2026 im Aufruf (`eigsh(K, M=−K_g, sigma=0)`).
Gemessen an einem Zweigelenkrahmen (Stiele HEB 200, 5 m, Riegel IPE 300,
8 m, Lastfall W = 25 kN am linken Stielkopf, ein Stiel gezogen, einer
gedrückt): Das dicht gerechnete α_cr ist 77,33. Zwei Läufe mit je 200
Aufrufen am alten Stand gaben je 200 verschiedene Werte, alle unter 3,6.
Unter „automatisch“ wurde damit eine Kombination 1,5·W nach II. Ordnung
gerechnet, obwohl α_cr = 51,55 ≥ 10 ist. Ein nur gezogener Stab gab einen
endlichen Wert statt „kein positiver Verzweigungslastfaktor“. Nicht
betroffen waren Zustände, in denen −K_g semidefinit ist: An der Halle
(42 GZT-Kombinationen, keine mit indefinitem −K_g) liegt der alte Aufruf
höchstens 1,3·10⁻¹³ neben dem dichten Bezug, der jetzige höchstens
5,3·10⁻¹² (24.09.2026); am Zweigelenkrahmen
gaben 1,35·G + 1,5·Q und 1,35·G + 1,5·W (−K_g semidefinit) schon vorher
200-mal den dichten Bezug 18,1837 bzw. 19,2341. Jetzt geben 200 Aufrufe
für W 200-mal 77,3287, gleich dem dichten Bezug (`tests/test_theorie2.py`).

**In drei Schritten, weil sich die größten μ häufen.** Knicken viele
gleiche Stäbe fast gleichzeitig, liegen die größten μ dicht beieinander, und
der Regelmodus (größte μ von −K_g gegen K) trennt sie nur mühsam. Am
symmetrischen Geschossrahmen (4 × 4 Felder zu 6 m, 4 Geschosse zu 4 m,
Stützen HEB 300, Riegel IPE 400, Verbände CHS 88,9 × 5 in den Außenwänden,
jeder Stab in 4 Elemente geteilt, 5856 FHG, 150 kN lotrecht je
Knotenpunkt) liegen die 40 größten μ innerhalb 3,1·10⁻⁴ von μ_max, dicht
gerechnet. Der Regelmodus allein, so gerechnet in einer Zwischenfassung
vom 23.09.2026, brauchte dort 52,5 und 53,5 s für ein α_cr, mit 6 × 6
Feldern und 6 Geschossen (16992 FHG) 1527 s (gemessen 24.09.2026).
Deshalb:

1. Schätzwert θ im Regelmodus mit lockerer Toleranz (10⁻³). θ ist ein
   Rayleigh-Quotient, also θ ≤ μ_max.
2. Verschiebung s = θ·(1 + 10⁻³). Ob s wirklich über μ_max liegt, sagt der
   Trägheitssatz: s·K + K_g ist genau dann positiv definit, wenn kein μ ≥ s
   ist. Geprüft wird das an den Pivots einer Zerlegung ohne Zeilentausch;
   ist einer nicht positiv, rückt s um eine Zehnerpotenz weiter. Das wird
   erzwungen, nicht erhofft: Die Prüfung setzt absichtlich schlechte
   Schätzwerte 0,99·μ_max und 0,3·μ_max ein und bekommt trotzdem μ_max.
3. Shift-invert um s: Das μ nächst s ist μ_max, und über 1/(μ − s) liegen
   die gehäuften μ weit auseinander.

Am Rahmen oben gibt das α_cr = 11,254972 in 0,24 s (mit dem Aufbau von
K_g), bis auf 8·10⁻¹⁵ gleich dem dichten Bezug; mit 16992 FHG
α_cr = 7,503375 in 0,9 bis 1,0 s. Der alte Aufruf `eigsh(K, M=−K_g,
sigma=0)` allein brauchte 0,18 bzw. 0,7 s, gab dort aber in je drei
Aufrufen Werte zwischen 0,07 und 0,42 bzw. 0,16 und 0,32 statt 11,25 bzw.
7,50. Die ganze Rechnung „automatisch“ mit drei
Kombinationen (1,35·G, 1,35·G + 1,5·W, 1,0·G + 1,5·W) am 5856-FHG-Rahmen
dauert 4,4 s, mit dem Regelmodus allein waren es 48,4 s (je einmal
gemessen, 24.09.2026).

**Wiederholbarkeit.** Der Startvektor ist fest, jeder Aufruf nimmt
denselben Rechenweg. Gemessen am 24.09.2026: Am Zweigelenkrahmen gaben
200 Aufrufe für W, 1,5·W und 1,35·G + 1,5·Q in drei Prozessen (einer mit
einem BLAS-Thread) je Zustand einen einzigen Wert, an der Halle je 20
Aufrufe für alle 42 GZT-Kombinationen ebenso. Ohne festen Startvektor
waren es unter 1,35·G + 1,5·Q 198 verschiedene Werte in 200 Aufrufen
(Spanne 8,3·10⁻¹²), an der Halle bei allen 42 Kombinationen mehr als einer.
Bitgleich ist α_cr damit an diesen Modellen, allgemein zugesagt ist es
nicht: Die Zwischenfassung (Regelmodus, vier Eigenwerte) gab trotz festem
Startvektor unter 1,5·W 23 verschiedene Werte in 200 Aufrufen (Spanne
8,4·10⁻¹⁵). An den angezeigten Stellen ändert das nichts.

**Gleichgewicht am verformten System.** Gelöst wird (K + K_g(N)) u = F.
Weil K_g von den Normalkräften abhängt und diese von u, wird iteriert, bis
sich die Verformungen nicht mehr ändern (Abbruch bei einer relativen Änderung
unter 1·10⁻⁶). K_g ist die geometrische Steifigkeit des Stabelements; das
Element rechnet mit Schubverformung, die Verzweigungslast ist deshalb die
nach Engesser

      N_cr = N_E / (1 + N_E/(G A_s)),   N_E = π² E I / L_cr²

und liegt bei gedrungenen Profilen rund ein halbes Prozent unter der
schubstarren Eulerlast — die Verifikation prüft genau das.

**Über der Verzweigungslast (α_cr ≤ 1)** hat (K + K_g) u = F zwar eine
Lösung, aber keine, die das Tragwerk unter wachsender Last erreicht: die
Vergrößerung 1/(1 − 1/α_cr) ist dort negativ, die Verformung zeigt gegen
die Last.
`solve_theorie2` rechnet dann nicht weiter und setzt einen Fehler mit dem
Klartext „α_cr = … ≤ 1: die Last liegt über der Verzweigungslast …“; die
Kombination bzw. der Lastfall behält das lineare Ergebnis, und das
Theoriekapitel führt die Zeile als „nicht geführt“. Bis zum 23.09.2026 wurde
das Ergebnis übernommen. Am Druckkragarm von `test_umhuellende` (Druck
1000 kN je Lastfall, „automatisch“) hatte K2 = 1,35·LF1 + 1,5·LF2 ein
α_cr von 0,756 und galt als gerechnet, ohne Fehler und Hinweis: u_y an der
Spitze −10,100 mm gegen linear +3,321 mm, also mit umgekehrtem Vorzeichen,
in der Zusammenfassung als „Verformungszuwachs +204.2 %“. Ein Lastfall LF1
mit Theorie II und 3000 kN Druck (α_cr 0,72) stand mit −1,907 mm gegen
linear +0,763 mm im Ergebnis. Bei 500 kN (α_cr 1,51) bleibt es wie bisher
bei 9,705 mm nach II. Ordnung.

**Ersatzimperfektionen (5.3.2).** Statt die Geometrie zu verziehen werden
nach 5.3.2(7) gleichwertige Lasten angesetzt:

      Schiefstellung   φ = φ_0 α_h α_m,  φ_0 = 1/200
                       α_h = 2/√h,  2/3 ≤ α_h ≤ 1,0
                       α_m = √(0,5 (1 + 1/m))
                       H_Ed = φ N_Ed  je Stiel, als Kräftepaar Fuß–Kopf
      Vorkrümmung      e_0/L nach Tabelle 5.1 je Knicklinie
                       q = 8 N_Ed e_0 / L²  quer zum Stab
                       V = 4 N_Ed e_0 / L   an beiden Enden entgegengesetzt

Beide Lastbilder sind in sich im Gleichgewicht; die Auflagersumme bleibt
unberührt. h ist die Bauwerkshöhe aus der Bounding-Box, m die Zahl der
Stiele, die mindestens 50 % der mittleren Stielnormalkraft tragen
(5.3.2(3)) — sie wird **je Kombination aus den Normalkräften** bestimmt, nicht
geraten. Als Stiel gilt ein Stab, dessen Achse höchstens 30° von der
Lotrechten abweicht; nur gedrückte Stiele bekommen eine Ersatzlast.

Die Schiefstellung wirkt in der **maßgebenden waagerechten Richtung**
(5.3.2(4)), nicht gleichzeitig in beiden: genommen wird die Richtung, in die
sich die Stielköpfe gegen ihre Füße ohnehin verschieben — so wirkt die
Ersatzlast immer ungünstig. Die Vorkrümmung wird in der lokalen y-Richtung
angesetzt (e_0 stammt aus der Knicklinie der schwachen Achse z, und Knicken
um z heißt Ausweichen in y) und nur für die nach 5.3.2(6) schlanken Stäbe:

      λ̄ > 0,5 √(A f_y / N_Ed)

**Folge für die Ergebnisse**: nach Theorie II. Ordnung gilt die Superposition
nicht mehr. Jede Kombination wird einzeln gerechnet und ersetzt das Ergebnis
der linearen Überlagerung; die Umhüllenden werden erst danach gebildet. Die
Lastfallergebnisse bleiben Ergebnisse nach Theorie I. Ordnung, außer bei
Lastfällen mit eigener Theorie II. oder III. Ordnung (Feld ``theorie``, siehe
5.1b): deren Ergebnis ersetzt das lineare. Überlagert werden dürfen beide nicht
mehr — der Bericht sagt das und nennt die Lastfälle nach II./III. Ordnung
namentlich; maßgebend ist dafür die gerechnete Theorie
(``res.info["theorie"]``), nicht die eingestellte.

**Grenzen**: keine Theorie III. Ordnung (große Verformungen), keine
Fließgelenke, keine Imperfektionsform aus der Knickeigenform nach 5.3.2(11)
(die Eigenform wird berechnet, aber nur als α_cr ausgewertet) und keine
Imperfektionen für Aussteifungsverbände nach 5.3.3.

### 5.1b Theorie III. Ordnung: große Verformungen

`theorie3.py` rechnet Stabtragwerke geometrisch nichtlinear — große
Verschiebungen und endliche Drehungen bei kleinen Dehnungen — in
**korotationaler Formulierung** (Crisfield):

* Jeder Knoten trägt eine Drehmatrix R, die je Iterationsschritt
  multiplikativ fortgeschrieben wird: R ← exp(Δθ)·R (Rodrigues).
* Jedes Stabelement bekommt ein mitgehendes Bezugssystem: e₁ entlang der
  aktuellen Sehne, e₂ aus der mittleren Drehung der beiden Knotentriaden
  (R₁·exp(½·log(R₁ᵀR₂))), auf die Sehnennormale projiziert, e₃ = e₁ × e₂.
* Die im mitgehenden System verbleibende Verformung ist klein:
  d_l = (0, θ₁ˡ, ΔL, θ₂ˡ) mit θᵢˡ = log(Eᵀ·Rᵢ·E₀ᵀ) und ΔL = L − L₀. Darauf
  wirkt die lineare lokale Steifigkeit (Timoshenko/Bernoulli, Federgelenke
  und Gelenke kondensiert): f_l = k_l·d_l, f_int = Tᵀ f_l.
* Gleichgewicht f_int(u, R) = λ·F + F_imp, gelöst mit Newton-Raphson in
  Laststufen λ = 1/n … 1 mit der Tangente Tᵀ(k_l + k_g(N))T. Der Rest der
  konsistenten Tangente fehlt; das Residuum ist exakt, die Iteration
  konvergiert deshalb gegen das richtige Gleichgewicht (linear statt
  quadratisch). Konvergenz: ‖Residuum‖ < 10⁻⁶·‖λF‖.
* Lasten sind richtungstreu (konservativ) und werden als äquivalente
  Knotenlasten der Ausgangslage angesetzt; Ersatzimperfektionen nach 5.3.2
  wie bei Theorie II. Ordnung, je Laststufe aus den Normalkräften.
* Fachwerkstäbe: nur Normalkraft, geometrische Steifigkeit N/L quer zum Stab.

Geprüft (`tests/test_theorie3.py`) gegen geschlossene Lösungen: Kragarm
unter Endmoment M = (π/2)·EI/L wird zum Viertelkreis (Spitze bei 2L/π,
Drehung 90°, Moment konstant), Elastica-Kragarm unter Querlast
PL²/EI = 1 (Mattiasson 1981: w/L = 0,30172, u/L = 0,05643, θ = 0,46135),
Seil aus zwei Fachwerkstäben (exakt), Druckstab mit Querlast bei
P = 0,5·P_cr (II. = III. Ordnung, Vergrößerung 2).

Die **Theorie je Lastfall und Kombination** (Feld ``theorie``: I, II, III,
leer = wie Einstellung) entscheidet im Rechenkern, welches Ergebnis das
lineare ersetzt; nach II. und III. Ordnung gilt keine Superposition.

### 5.2 Querschnittsklassifizierung (5.5, Tabelle 5.2)

* I-Profile: Flansch als einseitig gestütztes Teil c = (b − tw − 2r)/2,
  Steg als innenliegendes Teil c = h − 2tf − 2r; Grenzen 9ε/10ε/14ε bzw.
  für den Steg abhängig von α (plastischer Druckzonenanteil) und ψ
  (elastisches Spannungsverhältnis) mit ε = √(235/fy).
* Hohlprofile RHS: alle Teile innenliegend, c = b − 2t − 2r_i.
* CHS: d/t ≤ 50ε², 70ε², 90ε².
* CHS der Klasse 4 (d/t > 90ε²): für das Kreisrohr gibt es keine wirksamen
  Breiten. Der Nachweis läuft spannungsbasiert nach DIN EN 1993-1-6, 8.5
  (siehe 5.2a).

#### 5.2a Wirksame Querschnitte der Klasse 4 (DIN EN 1993-1-5, Abschnitt 4)

Beult ein Querschnittsteil, bevor die Streckgrenze erreicht wird, wird die
Tragfähigkeit mit dem **wirksamen** Querschnitt geführt. Je Teil gilt

      λ̄_p = (b̄/t) / (28,4 ε √k_σ)
      ρ   = 1                                     für λ̄_p ≤ Grenze
      ρ   = (λ̄_p − 0,055(3+ψ)) / λ̄_p²           innenliegend (4.4(2))
      ρ   = (λ̄_p − 0,188) / λ̄_p²                einseitig gestützt

mit den Beulwerten k_σ nach Tabelle 4.1 (innenliegend) beziehungsweise 4.2
(einseitig) — es ist dieselbe Implementierung wie beim Blechfeldnachweis in
Kapitel 5c. Die Grenzschlankheit ist 0,5 + √(0,085 − 0,055 ψ) innen und
0,748 außen. Die wirksame Breite wird nach Tabelle 4.1 aufgeteilt: bei ψ = 1
je zur Hälfte an beide Ränder, bei ψ = −1 mit b_e1 = 0,4 b_eff am Druckrand
und b_e2 = 0,6 b_eff an der Nulllinie.

Nach DIN EN 1993-1-1, 6.2.9.3 werden **drei** Querschnitte gebildet:

      A_eff     aus reinem Druck (ψ = 1 in allen Teilen)
      W_eff,y   aus reiner Biegung um y
      W_eff,z   aus reiner Biegung um z

Jeder entsteht aus einer Rechteckzerlegung des wirksamen Querschnitts; daraus
folgen Fläche, Schwerpunkt und Trägheitsmoment geschlossen. Die Verschiebung
der Schwerachse

      e_N = z_s(A_eff) − z_s(A)

wird aus dem wirksamen Druckquerschnitt **berechnet**, nicht angenommen. Beim
doppeltsymmetrischen Querschnitt ist die Abminderung symmetrisch und e_N wird
zu null; sonst treten die Zusatzmomente ΔM = N_Ed e_N in 6.2.9.3 (Gl. 6.44)
und in 6.3.3 (Gl. 6.61/6.62) hinzu.

Bewusst auf der sicheren Seite: die Ausrundungen bleiben unberücksichtigt
(Flanschüberstand (b − t_w)/2 statt (b − t_w − 2r)/2), ψ wird nach 4.4(3) am
Bruttoquerschnitt bestimmt, und die Abminderung über λ̄_p,red nach 4.4(5) mit
der tatsächlichen Randspannung wird nicht ausgenutzt. Der Bericht weist jedes
Querschnittsteil mit c/t, ψ, k_σ, λ̄_p, Grenze und ρ aus, dazu b_eff, die
Schwerachse, A → A_eff, W_el → W_eff und e_N.

#### 5.2b Schlanke Kreisrohre (DIN EN 1993-1-6, 8.5)

Für ein CHS der Klasse 4 wird die Meridianspannung aus N und M sowie die
Schubspannung aus V und Torsion gebildet und damit der spannungsbasierte
Schalenbeulnachweis nach Kapitel 5c.5 geführt — mit der Beullänge L_cr,z des
Stabes und der Herstelltoleranzklasse B. Bei einem schlanken Rohr wird dieser
Nachweis regelmäßig maßgebend: für CHS 508×8 in S355 unter N = 2000 kN,
M_y = 300 kNm und V = 200 kN ergibt sich η = 1,47 gegenüber η = 1,00 aus dem
elastischen Spannungsnachweis.

### 5.3 Querschnittsnachweise (6.2)

* Normalkraft 6.2.3/6.2.4, Biegung 6.2.5 (W_pl, W_el, W_eff je Klasse),
  Querkraft 6.2.6 mit Schubflächen (I: A − 2btf + (tw + 2r)tf; RHS:
  A·h/(b+h); CHS: 2A/π), Hinweis auf Schubbeulen bei hw/tw > 72ε/η.
* Torsion 6.2.7: Saint-Venant-Schubspannung, Abminderung der
  Querkrafttragfähigkeit; **Wölbkrafttorsion** siehe 5.3a.
* Biegung + Querkraft 6.2.8: ρ = (2V/Vpl − 1)² bei V > 0,5 Vpl.
* Biegung + Normalkraft 6.2.9: Klasse 1/2 mit M_N,Rd (I: Gl. 6.36–6.38,
  RHS: 6.39/6.40, CHS: M_N = M_pl (1 − n^1,7)), biaxial Gl. 6.41; Klasse
  3/4 linear elastisch (6.2.9.2/6.2.9.3), bei Klasse 4 mit A_eff, W_eff
  und dem Zusatzmoment ΔM = N_Ed e_N nach Gl. (6.44).
* Vergleichsspannung 6.2.1(5) als zusätzlicher elastischer Nachweis bei
  Klasse 3/4 und bei Torsion — dort gehen auch σ_w und τ_w aus der
  Wölbkrafttorsion ein.

### 5.3a Wölbkrafttorsion (6.2.7)

Ein offener dünnwandiger Querschnitt trägt Torsion auf zwei Wegen zugleich:

* **St.-Venant-Torsion** M_t,v = G I_t θ′ — reine Schubspannungen über die
  Wanddicke, die Querschnitte verwölben sich frei.
* **Wölbkrafttorsion** M_t,w = −E I_w θ‴ — wird das Verwölben behindert (an
  einer Einspannung, einer Stirnplatte, einer Querschnittsänderung), entstehen
  **Normalspannungen**. Ihr Maß ist das Wölbbimoment B = −E I_w θ″.

DIN EN 1993-1-1, 6.2.7(7) sagt es deutlich: bei geschlossenen Hohlquerschnitten
darf die Wölbkrafttorsion vernachlässigt werden, bei offenen Querschnitten wie
I und H dagegen die **St.-Venant-Torsion**. Rechnet man einen I-Träger mit
Wölbbehinderung nur mit I_t, kommt eine Verdrehung heraus, die um ein
Vielfaches zu groß ist, und die Wölbnormalspannung fehlt ganz — sie bestimmt
den Nachweis oft allein.

**Wie gerechnet wird.** Das Stabelement hat sechs Freiheitsgrade je Knoten und
kennt damit nur die St.-Venant-Torsion. Der Verlauf M_t(x) aus der Rechnung ist
trotzdem richtig, solange der Torsionsweg **statisch bestimmt** ist — er folgt
dann allein aus dem Gleichgewicht. Auf diesem M_t(x) wird die
Differentialgleichung geschlossen gelöst. Mit ψ = θ′ und λ² = G I_t/(E I_w)
wird aus M_t = G I_t θ′ − E I_w θ‴:

    ψ″ − λ² ψ = −M_t(x)/(E I_w)

    ψ(x) = M_t(x)/(G I_t) + P e^(−λx) + Q e^(−λ(L−x))

Diese Schreibweise ist numerisch stabil: beide Exponentialglieder sind höchstens
1, während cosh(λL) bei langen Trägern überläuft. Daraus folgen

    M_t,v = G I_t ψ
    M_t,w = M_t − M_t,v
    B     = −E I_w ψ′

Die beiden Konstanten kommen aus den Randbedingungen an den Stabenden: **frei**
(Gabellagerung, freies Ende) heißt B = 0, **behindert** (Einspannung,
Stirnplatte) heißt ψ = θ′ = 0. Sind beide Enden frei und ist M_t konstant, wird
P = Q = 0 — dann gibt es keine Wölbkrafttorsion, und das ist richtig so. Das ist
zugleich die Voreinstellung: an einem bestehenden Modell ändert sich dadurch
nichts, bis jemand eine Wölbbehinderung angibt.

**Spannungen.** Mit den Wölbordinaten des Querschnitts:

    σ_w = B ω / I_w              τ_w = M_t,w S_ω /(I_w t)      τ_t = M_t,v t / I_t

Für das I-Profil (Schubmittelpunkt = Schwerpunkt, der Steg liegt auf der Achse
durch den Pol) ist ω_max = h_m b/4 und S_ω,max = t_f h_m b²/16, also
σ_w = 6B/(t_f b² h_m) und τ_w = 1,5 M_t,w/(t_f b h_m) mit h_m = h − t_f. Für das
U-Profil liegt der Schubmittelpunkt um e = 3 t_f b²/(6 t_f b + h_m t_w) neben dem
Steg; dadurch verwölbt sich auch der Steg, und das größte S_ω liegt in
Stegmitte. Für andere Querschnitte werden die Wölbordinaten **nicht geraten**:
der Momentenanteil wird ausgewiesen, die Wölbspannungen nicht, und der Grund
steht dabei.

Die Richtigkeit der Wölbordinaten ist daran zu prüfen, dass I_w = ∫ω² t ds
denselben Wert ergibt wie die Querschnittstabelle — zwei ganz verschiedene Wege
zu derselben Zahl. `tests/test_woelb.py` rechnet das für IPE, HEB, HEA, UPE und
UPN nach (Abweichung 0,000 %) und prüft die Lösung gegen die geschlossene Form
des Kragträgers mit Endtorsionsmoment:

    B(0) = −T tanh(λL)/λ        θ(L) = T (L − tanh(λL)/λ)/(G I_t)

samt beider Grenzfälle (λL → 0: reine Wölbkrafttorsion mit B = −T L; λL → ∞:
B(0) → −T/λ und eine Randschicht der Länge 1/λ).

**Grenze.** Ist der Torsionsweg statisch unbestimmt, verteilt die
Wölbsteifigkeit die Torsionsmomente anders auf die Stäbe, als die Rechnung mit
sechs Freiheitsgraden es tut. Der Anteil je Stab ist dann eine Näherung; das
steht im Bericht.

### 5.4 Stabilitätsnachweise (6.3)

* Biegeknicken 6.3.1: N_cr = π² E I / L_cr² um y und z mit Knicklänge
  L_cr = β L oder explizit; Knicklinien nach Tabelle 6.2 (Walzprofile,
  geschweißte Profile, Hohlprofile warm/kalt, S460), χ nach Gl. 6.49.
  Drillknicken 6.3.1.4 für doppeltsymmetrische I-Profile mit
  N_cr,T = (G I_T + π² E I_w / L²) / i0².
* Biegedrillknicken 6.3.2: M_cr nach der Standardformel doppeltsymmetrischer
  Querschnitte mit k_z, k_w, C1, C2 und Lastangriffshöhe z_g. C1 wird aus
  dem Momentenverlauf bestimmt: linear → 1,77 − 1,04ψ + 0,27ψ² ≤ 2,6,
  sonst nach Kirby/Nethercot aus den Viertelspunktmomenten (≤ 2,5). χ_LT
  nach dem allgemeinen Fall 6.3.2.2 oder für gewalzte Profile 6.3.2.3
  (λ_LT,0 = 0,4, β = 0,75, f-Korrektur mit k_c = 1/√C1). Hohlprofile
  gelten als nicht biegedrillknickgefährdet.
* Biegung und Druck 6.3.3 mit Interaktionsbeiwerten nach Anhang B
  (Methode 2, Tabellen B.1/B.2), äquivalente Momentenbeiwerte C_m nach
  Tabelle B.3 (Gleichlastspalte); Gl. 6.61 und 6.62. Für die Stabilität
  werden je Kombination N_Ed = max. Druckkraft, M_y,Ed und M_z,Ed = max.
  Beträge entlang des Stabes angesetzt (auf der sicheren Seite).
* Teilsicherheitsbeiwerte: γM0 = 1,0, γM1 = 1,1 (deutscher NA), γM2 = 1,25.

#### 5.4a Knicklängen aus der Knickfigur

Aus dem linearen Verzweigungsproblem (K + α·K_g) v = 0 mit dem
Spannungszustand einer Kombination als Grundzustand folgen der
Verzweigungslastfaktor α_cr und die Knickfigur v. Für einen Stab mit der
Druckkraft N_Ed ist die ideale Knicklast N_cr = α_cr·|N_Ed| und damit

    L_cr = π · √(E·I / N_cr),   β = L_cr / L.

Die Eigenform liefert zwei Angaben, die α_cr allein nicht enthält
(`ec3/knicklaengen.py`):

* die **Biegeachse**: die modale Formänderungsenergie ½ vᵀ k v jedes
  Elements wird nach den Biegefreiheitsgraden um die lokale y- und z-Achse
  getrennt; die Knicklänge gilt für die Achse mit dem größeren Anteil, die
  andere bleibt unbestimmt;
* die **Beteiligung**: der Anteil des Stabs an der Gesamtenergie der
  Knickfigur. Ein unbeteiligter Stab bekommt nach der Formel eine viel zu
  große Knicklänge — der Wert wird als Obergrenze gekennzeichnet; für ihn
  ist eine höhere Knickfigur auszuwerten.

Geprüft (`tests/test_knicklaengen.py`) gegen die Eulerfälle β = 1, 2, 0,5
und 0,699 (Abweichung < 0,3 % bei 12 bis 16 Elementen), die Achse bei
gehaltener schwacher Achse, den zweistieligen Rahmen mit starrem Riegel
(β = 1 bei eingespannten Füßen, β = 2 bei Fußgelenken, Beteiligung je 50 %)
und den kaum belasteten Nachbarstiel (unbeteiligt, Obergrenze).

### 5.5 Ermüdung (DIN EN 1993-1-9)

Nennspannungskonzept. Aus zwei Zuständen (Lastfälle oder Kombinationen)
wird an den vier Eckpunkten des Querschnitts die Spannungsschwingbreite
Δσ = |σ_max − σ_min| (σ = N/A ± My/W_el,y ± Mz/W_el,z) sowie die
Schubschwingbreite Δτ bestimmt. Wöhlerlinien nach Bild 7.1:

* Normalspannung: m = 3 bis N_D = 5·10⁶ (Δσ_D = 0,737 Δσ_C),
  m = 5 bis N_L = 10⁸ (Δσ_L = 0,549 Δσ_D), darunter keine Schädigung.
* Schub: m = 5 bis 10⁸ (Δτ_L = 0,457 Δτ_C).

Schadensakkumulation nach Palmgren–Miner D = Σ n_i / N_Ri mit der um γMf
abgeminderten Kerbfallklasse; Nachweis D_σ + D_τ ≤ 1. Zusätzlich wird die
schadensäquivalente Schwingbreite bei 2·10⁶ Lastspielen ausgewiesen. γMf nach
Tabelle 3.1 (Schadenstoleranz/Sicherheit gegen Versagen, geringe/hohe
Schadensfolge), γFf = 1,0.

**Die Schädigung wird am Ort aufsummiert.** Miner zählt, was *ein Punkt* des
Bauteils erlebt. Die größte Schwingbreite aus Last A und die aus Last B liegen
aber im Allgemeinen an verschiedenen Stellen des Stabes; wer sie addiert,
addiert die Schädigung zweier verschiedener Punkte und erhält eine Zahl, die
nirgends auftritt. Gerechnet wird darum D an **jeder** Nachweisstelle und an
jedem der vier Eckpunkte des Querschnitts; maßgebend ist der größte Wert, und
der Ort steht im Nachweis. Die Übersichtstabelle „größte Schwingbreite je
Ermüdungslast" bleibt daneben stehen — als Übersicht, nicht als Summand.

**Palmgren-Miner über das Lastkollektiv.** Jede Ermüdungslast ist eine
Zeile z des Kollektivs, und jede Zeile liefert am Ort x Stufen i mit der
Schwingbreite Δσ_z,i(x) und der Spielzahl n_z,i. Summiert wird über **alle**
Zeilen und Stufen am selben Ort:

  D(x) = Σ_z Σ_i n_z,i / N_R(Δσ_z,i(x)),  maßgebend max_x D(x) ≤ 1.

Ort heißt beim Stab jede Nachweisstelle mit ihren vier Eckpunkten, beim
Volumen jeder Knoten bzw. jedes Element (Regel `ermuedung_volumen`). Die
Spielzahl einer Zeile mit zwei Zuständen ist ihr n. Beim Verlauf ist es die
Spielzahl der gezählten Stufe mal die Durchläufe. Die **eigene Zahl einer
Zeile ersetzt die globale Lastspielzahl** (Nachweise → Konfiguration), sie
kommt nicht dazu. Die Reihenfolge der Zeilen spielt keine Rolle; die lineare
Summe kennt keinen Reihenfolgeeinfluss. Soll jeder Lastfall seine eigene
Lastspielzahl bekommen, ist das eine Zeile je Lastfall gegen den
Nullzustand, jede mit ihrem n (Maske Ermüdungslasten, „Zeile je
Lastfall…“). Geprüft am Kragarm IPE 200 (Kerbfall 71): zwei Zeilen am
selben Stab ergeben D = 2,83695, die Einzelrechnungen 2,37999 und 0,456958,
zusammen also dasselbe (`tests/test_ermuedungsmaske.py`).

#### 5.5-1 Zählverfahren: aus dem Verlauf wird ein Kollektiv (Anhang A)

Zwei Zustände reichen, solange die Beanspruchung zwischen zwei Zuständen
pendelt. Eine Überfahrt, ein Öffnungsvorgang, ein Betriebszyklus haben mehr:
die Zwischenstufen tragen eigene, kleinere Spiele bei, und die zählen mit. Eine
Ermüdungslast darf darum statt zweier Zustände eine **Folge von Lastfällen**
nennen; daraus zählt Statik3D das Kollektiv — mit einem von drei Verfahren.

**Spanne** (Vorgabe seit 11.09.2026). Eine Stufe: Schwingbreite = Maximum
minus Minimum über die Zustände, ein Spiel je Wiederholung. Das ist die
Schwingbreite, die RFEM aus einer Ergebniskombination für die Ermüdung
bildet, und das richtige Verfahren, wenn die Zustände keine Zeitfolge sind —
die 50 FAT-Umhüllenden des Drehlagers mit 2 bis 82 Zuständen. Rainflow zählte
bei drei Zuständen 10 → 25 → 5 kN zwei halbe Spiele verschiedener Größe (am
Kragarm IPE 200: Stufen 205,8 und 154,4 N/mm² zu je 0,5 Spielen statt einer
Stufe 205,8 mit einem Spiel), ein Kollektiv ohne Grundlage. Die Spanne ist von
der Reihenfolge unabhängig, und bei zwei Zuständen gleicht sie der
Zwei-Zustände-Form; Rainflow zählt dort nur ein halbes Spiel (D = 0,609 statt
1,219, `tests/test_ermuedung_verlauf.py`). Die Lastspielzahl kommt je Last
oder — ohne eigene Angabe — global aus den Nachweiseinstellungen
(`ermuedung_lastspiele`); 0 Wiederholungen schalten eine Last ab.

**Rainflow** (Vier-Punkt-Verfahren). Zuerst bleiben nur die Umkehrpunkte
übrig — ein Wert auf dem Weg nach oben ist keine Umkehr. Liegt dann die
mittlere von vier aufeinanderfolgenden Umkehrungen ganz innerhalb der äußeren
(|s₂−s₃| ≤ |s₁−s₂| und ≤ |s₃−s₄|), ist sie ein **geschlossenes Spiel** und wird
herausgenommen; der Rest wird weiterverfolgt. Was übrig bleibt, sind halbe
Spiele (Konvention nach ASTM E1049). Am Lehrbuchbeispiel
[−2, 1, −3, 5, −1, 3, −4, 4, −2] fällt genau das bekannte Kollektiv heraus:
3 (½), 4 (1½), 6 (½), 8 (1), 9 (½) — zusammen 4 Spiele, also (9−1)/2.

**Reservoir.** Der Verlauf ist ein Gefäß, das mit Wasser gefüllt wird; am
tiefsten Punkt zieht man den Stöpsel, und was ausfließt, ist ein Spiel mit der
Höhe des Wasserspiegels. Danach zerfällt das Gefäß an dieser Stelle in **zwei**
Reservoire, links und rechts, und in jedem geht es von vorn los. Genau dieses
Zerfallen macht das Verfahren aus; wer stattdessen weiter gegen die äußeren
Hochpunkte misst, zählt zu große Schwingbreiten.

**Beginnt und endet der Verlauf am größten Wert, liefern beide Verfahren
dasselbe Kollektiv** — das prüft `tests/test_ec3.py` nach, und so gehört eine
Überfahrt angesetzt. Andernfalls dürfen sie auseinandergehen: was bei Rainflow
als Rest offen bleibt und dort mit einem halben Spiel zählt, ist beim Reservoir
schon abgeflossen.

#### 5.5-2 Die Schadensakkumulation im Statikdokument

Der Nachweis zeigt die Miner-Summe **Stufe für Stufe** am maßgebenden Ort: je
Stufe die Schwingbreite, die Lastspielzahl, die ertragbare Lastspielzahl N_R
aus der Wöhlerlinie, der Anteil D_i = n/N und die laufende Summe. Stufen
unterhalb des Schwellenwerts (N_R = ∞) stehen mit D_i = 0 darin — sie sind
damit nicht verschwiegen, sondern nachweislich unschädlich.

Ist ein **Bezugszeitraum** angegeben (Einstellung `ermuedung_bezugsjahre`:
die Lastspielzahlen gelten für so viele Jahre), folgt daraus die rechnerische
**Lebensdauer** als Bezugszeitraum / D — die Schädigung wächst linear. Ohne
Bezugszeitraum gelten die Lastspielzahlen für die ganze Nutzungsdauer, und es
gibt keine Lebensdauer zu nennen.

#### 5.5-3 Volumen: Hauptspannung je Knoten

Ein Volumen hat keine Nennspannung. Als Spannungsgröße je Ort und Zustand
dient die **vorzeichenbehaftete Hauptspannung mit dem größten Betrag**: σ₁,
wenn |σ₁| ≥ |σ₃|, sonst σ₃. Ein
Zugkörper gibt +σ, ein Druckkörper −σ, und die Schwingbreite zwischen zwei
Zuständen ist die Differenz dieser Größe — nicht die Differenz zweier Beträge,
die einen Wechsel von Zug auf Druck verschluckte. Aus dem Verlauf der Größe
entsteht je Ort das Kollektiv wie beim Stab (spanne, Rainflow,
Reservoir), die Schädigung nach Palmgren-Miner mit der Wöhlerlinie für
Normalspannungen und γMf nach Konzept und Schadensfolge des Körpers;
maßgebend je Körper der Ort mit dem größten D, und die Ausnutzung je
Element steht für die Färbung bereit.

**Der Ort ist seit dem 23.09.2026 der Knoten** (Nachweiseinstellung
`ermuedung_volumen`, Vorgabe „knoten“, `ec3/fatigue.py`, `VOLUMEN_REGELN`):
der Spannungstensor ist die geglättete Knotenspannung des Lösers
(`res.solid_knoten`) — das Mittel der Elementwerte gleichen Körpers und
Werkstoffs am Knoten, an freien Oberflächen auf σ·n = 0 gezogen, wenn
`Model.randspannung` „frei“ ist (§ 5d) —, also derselbe, den der statische
Volumennachweis liest. Er ist linear in den Verschiebungen; Kombinationen
tragen ihn überlagert. Die Färbung je Element zeigt das größte D an seinen
Ecken. Mit „element“ rechnet der Nachweis wie bis dahin mit dem Elementwert
`res.solid_res` (dem Element an seinem Auswertepunkt mit der größten
Vergleichsspannung); die Zahlen sind dann bitgleich mit dem Stand vor der
Umstellung (gemessen am Kragarm unten und am Zugstab mit Rainflow). Der
Bericht nennt je Körper die gerechnete Regel. Ein Ergebnis aus der
Ergebnisdatei einer Programmfassung ohne diese Einstellung (vor a4ec83f)
kennt das Feld `regel` nicht (`volumen_regel_unbekannt`); der Bericht nennt
es als Ergebnis einer älteren Programmfassung mit dem Elementwert, nicht neu
gerechnet, und sagt, welche Einstellung beim Neurechnen gilt.

Gemessen 23.09.2026 am Kragarm-Prüfkörper (`tests/pruefkoerper.Kragarm`,
hex8, Endquerkraft; Körper mit Kerbfall sind die Elemente mit x ≥ L/2,
Ermüdungslast 0 → F, Soll 355 N/mm² nach Saint-Venant am Schnitt x = L/2;
`tests/test_ermuedung_verlauf.py`, `test_volumen_randspannung_kragarm`),
größte Schwingbreite des Körpers in N/mm²:

| Netz | FHG | Elementwert (Regel „element“) | Knoten (Regel „knoten“) | Knoten am Nachweispunkt (Oberkante, Breitenmitte) |
|---|---|---|---|---|
| 8 × 2 × 4 | 405 | 314,35 (−40,65) | 355,22 (+0,22) | 355,22 |
| 16 × 4 × 8 | 2 295 | 333,31 (−21,69) | 355,02 (+0,02) | 354,96 |

Die Schwingbreite 0 → F am Nachweispunkt ist gleich dem statischen Wert der
geglätteten Knotenspannung dort. Die Elementregel lag an diesem Körper auf der
unsicheren Seite. Der Elementwert ist der Tensor an einem Auswertepunkt des
Elements, und der hex8 zeigt σxx hier über seine Länge fast gleich. Am
Nachweisknoten (8 × 2 × 4) hat das Element rechts des Schnitts 314,35 N/mm²
an seinem Auswertepunkt bei x = L/2, wo die Balkenlösung 355,00 gibt; das
Element links des Schnitts, zur Einspannung hin, hat 401,94 an seinem
Auswertepunkt bei x = 3L/8 und 400,07 bei x = L/2 — die Balkenlösung dort
443,75 bzw. 355,00. Bei 16 × 4 × 8 sind es 333,26 gegen 355,00 und 377,61
bei x = 7L/16 gegen 399,38. Gegen das Soll bei L/2 gehalten scheint das
Element links des Schnitts zu viel zu zeigen; an seinem eigenen
Auswertepunkt zeigt es weniger als die Balkenlösung.

Andere Körperenden (gemessen 24.09.2026, zwei Läufe bitgleich; Körper = die
Elemente mit x ≥ x₀, Ermüdungslast 0 → F, Soll die Balkenlösung an der
Oberkante bei x₀; ein Netz 32 × 8 × 16 trifft sie dort mit dem Knotenwert
355,00 / 443,75 / 532,48), größte Schwingbreite des Körpers in N/mm²:

| Netz | Körper ab x₀ | Balkenlösung bei x₀ | Elementwert (Regel „element“) | Knoten (Regel „knoten“) |
|---|---|---|---|---|
| 8 × 2 × 4 | L/2 | 355,00 | 314,35 (−40,65) | 355,22 (+0,22) |
| 8 × 2 × 4 | 3L/8 | 443,75 | 401,94 (−41,81) | 447,70 (+3,95) |
| 8 × 2 × 4 | L/4 | 532,50 | 501,25 (−31,25) | 530,78 (−1,72) |
| 16 × 4 × 8 | L/2 | 355,00 | 333,31 (−21,69) | 355,02 (+0,02) |
| 16 × 4 × 8 | 3L/8 | 443,75 | 422,27 (−21,48) | 443,81 (+0,06) |
| 16 × 4 × 8 | L/4 | 532,50 | 513,34 (−19,16) | 532,62 (+0,12) |

An jedem dieser Körperenden lag die Elementregel unter der Balkenlösung. Die
Knotenregel traf sie mit 16 × 4 × 8 auf 0,12 N/mm², mit 8 × 2 × 4 abseits
von L/2 auf 3,95 bzw. 1,72 N/mm² (`test_volumen_randspannung_kragarm` prüft
die Tabelle gegen die Rechnung).

**Abgeschaltete Elemente** (Situationen): Die Knotentabelle eines Zustands
mittelt nur über die wirkenden Elemente; ein Knoten, an dem nur abgeschaltete
Elemente des Körpers liegen, fehlt darin. Er trägt in diesem Zustand die
Spannung 0 — so rechnet auch die Elementregel das abgeschaltete Element
(`solver.postprocess` gibt ihm Nullen) —, alle anderen Knoten die geglättete
Spannung wie im statischen Nachweis. Bis zur Nachbesserung vom 23.09.2026 fiel
der ganze Körper dann auf die Elementregel zurück, bei jedem Neurechnen wieder
(gemessen am Kragarm 8 × 2 × 4, Körper = alle Elemente, Eckelement an der
Einspannung abgeschaltet, 0 → F: größte Schwingbreite 1 141,55 N/mm² nach der
Elementregel, jetzt 1 123,53 nach der Knotenregel;
`test_volumen_abgeschaltete_elemente`).

**Ohne Knotenwerte** rechnet der Körper nach der Elementregel, und der
Hinweis nennt die Ursache, die vorliegt: ein Ergebnis aus einer
Programmfassung vor dem 23.09.2026 (die Knotentabelle `res.solid_knoten` kam
mit dem Merge 21ce779 am 23.09.2026 in das Programm; neu gerechnet gilt die
Knotenregel), eine Überlagerung, deren Lastfälle verschiedene Knotentabellen
führen (`Results.combine` verwirft sie dann), oder ein fehlender Knoten, an
dem ein Element des Körpers wirkt (mit Nummer). Eine unbekannte Einstellung
führt den Nachweis nicht („nicht geführt“ mit Grund). **Fließende Elemente**
sind wie im statischen Nachweis von σ·n = 0 ausgenommen — sie tragen zum
Knotenmittel den Wert ihres nächsten Integrationspunkts bei (§ 5d) —, und der
Nachweis nennt Zustand und Zahl der fließenden Elemente des Körpers
(`test_volumen_regel_rueckfall_und_fliessen`: Balken aus einer hex8-Lage unter
1,20 M_el, 5 fließende Elemente; die Schwingbreite ist dort genau die
Knotenspannung des Lösers).

Die Hauptspannungen kommen geschlossen (Cardano, trigonometrisch) für alle
Elemente auf einmal: 200 000 Tensoren in unter 2 s, gegen `eigvalsh` je
Element in einer Schleife — bei 2 Mio. Elementen und 164 Zuständen des
Drehlagers Minuten je Zustand. Geprüft an 2000 Zufallstensoren gegen
`eigvalsh` (Abweichung unter 10 Pa bei 50 MPa), Patch-Test am Zugstab aus
10 × 2 × 2 Hexaedern: Δσ = ΔF/A = 60,0 N/mm² auf 10⁻⁶ genau, D wie die
Handrechnung mit `sn_life`, Druck wie Zug (`tests/test_ermuedung_verlauf.py`).

**Grenzen.** Wie genau die Knotenspannung den Rand trifft, hängt am Netz
(§ 5d: Kragarm, Kirsch-Loch); die Elementregel nahm bis zum 20.09.2026 die
Elementmitte, beim Sechsflächner unter Biegung den schlechtesten Ort (§ 5d). Die
Größe ist eine Struktur- oder Kerbspannung, keine Nennspannung:
die Kerbfälle der Tabellen 8.1–8.10 gelten nur, wo das Element die
Nennspannung abbildet (glatter Grundwerkstoff); an Nähten und Kerben gehört
ein Kerbfall des Struktur- oder Kerbspannungskonzepts dazu (IIW: FAT 225 für
die Kerbspannung mit r = 1 mm). Der Vorschlag des Programms (160,
Grundwerkstoff; `ec3/kerbfaelle.py`) ist dafür ein Anfang, kein Befund.
Rainflow und Reservoir zählen je Ort einzeln und sind bei großen Körpern
langsam; die Spanne ist vektorisiert.

**Verschweißte Berührungsstellen.** Ein Knoten, den zwei Körper teilen, ist
eine durchverbundene Stelle: der Vernetzer teilt Knoten nur über eine
gemeinsame Fläche (RFEM: eine Fläche zwischen zwei Volumen), und eine
ausgeführte Kontaktfuge verdoppelt sie (Kapitel 4.0). Ohne eingegebene
Kontaktbedingung zwischen den beiden Körpern ist das ein Stoß, der in
Wirklichkeit geschweißt ist (Anweisung des Anwenders vom 11.09.2026). Nach
der Regel „knoten“ trägt ein solcher Knoten selbst, nach der Regel „element“
jedes Element mit einem solchen Knoten — eine Elementlage beiderseits — den
Kerbfall „Naht" seines Körpers, Vorschlag 90 N/mm² nach Anhang B, Tabelle B.1,
Detail 7 (Kreuzstoß mit tragenden Kehlnähten, Strukturspannung); voll
durchgeschweißt wäre Detail 3 mit 100. Die Wöhlerlinie läuft dafür mit einem
Kerbfall je Ort (`_n_vektor` mit Feld). Die Zuordnung ist ein Durchlauf
über alle Elementknoten (`nahtknoten`), am Drehlager 8 Mio. Einträge in
Sekunden; Paare mit Kontaktbedingung (`kontaktpaare`, aus `koerpernamen` und
Gegenkörpern bzw. den Besitzern der Gegenflächen) bleiben außen vor.
Gemessen am Drehlager: 47 gemeinsame Flächen zwischen 25 Körperpaaren,
keine davon von einer der 12 Kontaktbedingungen genannt — die Kontakte
liegen dort auf getrennten, deckungsgleichen Flächen. Grenze: teilen zwei
Körper nur eine Kante, zählt die Elementlage an der Kante mit — sie liegt
ohnehin an einem Stoß. Geprüft an zwei Körpern aus einem Hexaedernetz
(`test_naht_beruehrung`): 9 Nahtknoten in der Ebene x = 1 m, vier Elemente
je Körper an der Naht, maßgebend (Regel „knoten“) ein Nahtknoten mit D nach
der Wöhlerlinie 90 an einem Element der Nahtlage, der Nachbarkörper ohne
Nahtkerbfall mit 160; mit Kontaktbedingung keine Nahtknoten.

#### 5.5a Kerbfälle aus Schweißnähten (`schweissnaehte.py`)

Jede Naht liefert nach Nahtart, Lage zur Beanspruchung und Ausführung den
Kerbfall (Auswahl aus DIN EN 1993-1-9):

| Naht | Kerbfall Δσ_C [N/mm²] | Fundstelle |
|---|---|---|
| Längsnaht automatisch ohne / mit Ansatzstellen; von Hand | 125 / 112; 100 | Tab. 8.2, Details 1–4 |
| Längsnaht unterbrochen; mit Freischnitten; einseitig (geprüft / ungeprüft) | 71; 63; 80 / 71 | Tab. 8.2, Details 8, 9, 6 |
| Querstumpfnaht bearbeitet + geprüft; geprüft; unbearbeitet; einseitig mit Badsicherung; einseitig ungeprüft | 112; 90; 80; 71; 36 | Tab. 8.3, Details 1, 2/3, 5, 9, 11 |
| Kehlnaht quer (Kreuz-/T-Stoß) nach ℓ ≤ 50/80/100/120/200/300/> | 80/71/63/56/50/45/40, Wurzel 36 | Tab. 8.5, Detail 3 |
| Quersteife ℓ ≤ 50 / ≤ 80; Längssteife L ≤ 50/80/100/> | 80 / 71; 80/71/63/56 | Tab. 8.4, Details 6/7, 1/2 |
| Deckblech-Ende t ≤ 20/30/50/>; Stirnnaht bearbeitet (t ≤ 20) | 56/50/45/40; 71 | Tab. 8.5, Details 5, 6 |

Schub: Δτ_C = 100 (durchgeschweißt, Grundwerkstoff) bzw. 80 (Kehlnaht,
Tab. 8.5 Detail 8). Größeneinfluss für Quernähte, Steifen und Kreuzstöße:
k_s = (25/t)^0,2 für t > 25 mm. Je Stab gilt der kleinste Kerbfall aller
Nähte, die ihn nennen, oder einer **äquivalenten** Naht ohne Zuordnung
(Ersatznaht für alle); Δτ_C ebenso. `tests/test_schweissnaehte.py` prüft die
Tabellenwerte, k_s, die Zuordnung, die Übernahme in die Stäbe und den
Ermüdungsnachweis mit dem Kerbfall aus der Naht.

## 5c Plattenbeulen (DIN EN 1993-1-5)

Ein dünnes Blech unter Druck oder Schub versagt nicht durch Fließen, sondern
durch Ausbeulen. Grundlage ist die Bezugsspannung

    σ_E = π² E t² / (12 (1 − ν²) b²)   (= 190 000 (t/b)² N/mm²)

und die Beulwerte k_σ nach Tab. 4.1 (beidseitig gestützt, z. B. Steg zwischen
den Flanschen) beziehungsweise Tab. 4.2 (einseitig gestützt), k_τ nach A.3:

    k_τ = 5,34 + 4,00/α²  (α = a/h_w ≥ 1)      k_τ = 4,00 + 5,34/α²  (α < 1)

### 5c.1 Schubbeulen der Stegbleche (Abschnitt 5)

Geführt wird der Nachweis, sobald h_w/t_w > 72 ε/η (ohne Zwischensteifen)
beziehungsweise > 31 ε √k_τ/η (mit Quersteifen im Abstand a):

    λ̄_w = h_w/(86,4 t_w ε)              nur Endquersteifen
    λ̄_w = h_w/(37,4 t_w ε √k_τ)         mit Quersteifen im Abstand a
    χ_w  nach Tab. 5.1
    V_b,Rd = χ_w f_yw h_w t_w / (√3 γ_M1)   ≤ η f_yw h_w t_w / (√3 γ_M1)

Der Flanschanteil V_bf,Rd wird **nicht** angesetzt — das liegt auf der sicheren
Seite. Bei V_Ed > 0,5 V_bw,Rd und M_Ed > M_f,Rd folgt die Interaktion nach 7.1:

    η_1 + (1 − M_f,Rd/M_pl,Rd)(2 η_3 − 1)² ≤ 1

Dieser Nachweis läuft in den Querschnittsnachweisen jedes Stabes mit; früher
stand dort nur der Hinweis, dass er zu führen sei.

### 5c.2 Blechfelder: Methode der reduzierten Spannungen (Abschnitt 10)

Ein **Beulfeld** ist eine Gruppe von Schalenelementen. Seine Achsen werden aus
der Geometrie gewonnen (u längs = a, v quer = b, Normale n); die Membran­
spannungen jedes Elements werden in diese Achsen gedreht, und über das Feld
werden die größten Druckspannungen σ_x, σ_z sowie die größte Schubspannung τ
genommen (Druck positiv). Aus den Randwerten folgen die Spannungsverhältnisse
ψ_x und ψ_z. Damit:

    1/α_ult,k² = (σ_x/f_y)² + (σ_z/f_y)² − (σ_x/f_y)(σ_z/f_y) + 3(τ/f_y)²   (10.3)
    1/α_cr     = A + √(A² + (1−ψ_x)/2 · 1/α_cr,x² + (1−ψ_z)/2 · 1/α_cr,z²
                        + 1/α_cr,τ²)                                        (10.6)
                 mit A = (1+ψ_x)/(4 α_cr,x) + (1+ψ_z)/(4 α_cr,z)
    λ̄_p       = √(α_ult,k / α_cr)

Die Abminderungsbeiwerte sind ρ nach 4.4(2) für die Längsspannungen und χ_w
nach Tab. 5.1 für den Schub. Nachgewiesen wird nach Gl. (10.5)

    (σ_x/(ρ_x f_yd))² + (σ_z/(ρ_z f_yd))² − (σ_x σ_z)/(ρ_x ρ_z f_yd²)
      + 3(τ/(χ_w f_yd))² ≤ 1

und zusätzlich wird die Vereinfachung 10.5(2) mit einem einzigen Beiwert ρ_min
ausgewiesen, damit beide Wege im Dokument nachvollziehbar sind.

### 5c.3 Längs- und Quersteifen (Anhang A, 4.5 und 9)

Eine Längssteife hebt die Beulspannung des Feldes. Welcher Weg gilt, hängt an
ihrer Zahl:

* **eine oder zwei Steifen** → Anhang A.2.2. Mit b₁ und b₂ als Breiten der
  Teilfelder und A_sl,1, I_sl,1 als Querschnittswerten der Steife **samt
  mitwirkendem Blech** (je 15 ε t, Bild 4.4):

      a_c = 4,33 (I_sl,1 b₁² b₂² / (t³ b))^(1/4)
      a ≥ a_c:  σ_cr,sl = 1,05 E √(I_sl,1 t³ b) / (A_sl,1 b₁ b₂)
      a < a_c:  σ_cr,sl = π² E I_sl,1/(A_sl,1 a²)
                          + E t³ b a² / (4π² (1−ν²) A_sl,1 b₁² b₂²)

* **ab drei Steifen** → Anhang A.1(2), die verschmierte orthotrope Platte mit
  γ = ΣI_sl/I_p und δ = ΣA_sl/(b t), I_p = b t³/(12(1−ν²)).

Der Schubbeulwert bekommt den Zuschlag nach A.3(2):

      k_τ,st = 9 (h_w/a)² ⁴√((I_sl/(t³ h_w))³)   ≥ (2,1/t) ³√(I_sl/h_w)

Zwischen **Plattenbeulen und Knickstabverhalten** wird nach 4.5.4 interpoliert.
Die Knickspannung des Ersatzstabes ist σ_cr,c = π² E I_sl,1/(A_sl,1 a²), bei
Spannungsgradient auf den gedrückten Rand hochgerechnet; damit

      ξ = σ_cr,p/σ_cr,c − 1   (0 ≤ ξ ≤ 1)
      ρ_c = (ρ − χ_c) ξ (2 − ξ) + χ_c

mit χ_c aus der Knicklinie a und α_e = α + 0,09/i. Bei gleichmäßigem Druck
entfällt die Hochrechnung (es gibt keine Nulllinie im Feld).

Die Steifen selbst werden nach **Abschnitt 9** geprüft: Drillknicken einer
Längssteife nach 9.2.1(8) mit I_T/I_p ≥ 5,3 f_y/E, Mindeststeifigkeit einer
starren Quersteife nach 9.3.3(3) mit I_st ≥ 1,5 h_w³t³/a² (a/h_w < √2)
beziehungsweise ≥ 0,75 h_w t³. Fehlen I_T und I_p, sagt das Programm, dass das
Drillknicken gesondert zu prüfen ist — es rät nicht.

### 5c.4 Lasteinleitung (Abschnitt 6)

Eine örtlich eingeleitete Querkraft kann den Steg zum Beulen bringen:

      k_F   nach Bild 6.1 (Art a, b oder c)
      F_cr  = 0,9 k_F E t_w³ / h_w
      m₁    = f_yf b_f/(f_yw t_w),  m₂ = 0,02 (h_w/t_f)² für λ̄_F > 0,5
      ℓ_y   Art a und b: s_s + 2 t_f (1 + √(m₁+m₂)) ≤ a
            Art c:       aus ℓ_e = k_F E t_w²/(2 f_yw h_w) ≤ s_s + c
      λ̄_F  = √(ℓ_y t_w f_yw / F_cr),  χ_F = 0,5/λ̄_F ≤ 1,0
      F_Rd  = f_yw χ_F ℓ_y t_w / γ_M1

Weil m₂ von λ̄_F abhängt, wird wie in 6.5(1) zuerst mit m₂ = 0 gerechnet und
danach einmal nachgezogen. Die Kraft F_Ed kommt aus der Rechnung — wahlweise
als Knotenlast der jeweiligen Kombination oder als Auflagerkraft.

Wirkt gleichzeitig Biegung, wird zusätzlich die Interaktion nach 7.2(1)
geführt:

      η₂    = F_Ed / F_Rd
      η₁    = |N_Ed|/(A f_y/γ_M0) + |M_Ed|/(W_el,y f_y/γ_M0)   nach 4.6(1)
      η₂ + 0,8 η₁ ≤ 1,4

N_Ed und M_Ed werden an der Nachweisstelle des Stabes abgegriffen, die dem
Lasteinleitungsknoten am nächsten liegt; die Interaktion wird über alle
Kombinationen gebildet und der ungünstigste Wert ausgewiesen. η₁ entsteht aus
den **Bruttoquerschnittswerten** A und W_el,y — wirksame Querschnittswerte nach
Abschnitt 4 werden hier nicht gebildet; bei schlanken Stegen ist das auf der
unsicheren Seite und wird im Bericht als Hinweis genannt.

### 5c.5 Schalenbeulen (DIN EN 1993-1-6, Abschnitt 8.5)

Für Kreiszylinderschalen wird der spannungsbasierte Nachweis geführt. Die
kritischen Beulspannungen folgen Anhang D.1 mit dem Längenparameter
ω = l/√(r t) und den Beiwerten C_x, C_θ, C_τ je Längenbereich:

      σ_x,Rcr = 0,605 E C_x t/r
      σ_θ,Rcr = 0,92 E C_θ (t/r)/ω
      τ_Rcr   = 0,75 E C_τ √(1/ω) t/r

Der elastische Imperfektionsbeiwert hängt an der **Herstelltoleranzklasse**
(A: Q = 40, B: 25, C: 16):

      Δw_k = (1/Q)√(r/t)·t,   α_x = 0,62/(1 + 1,91 (Δw_k/t)^1,44)

für Umfangsdruck und Schub α = 0,75 / 0,65 / 0,50 je Klasse. Mit
λ̄ = √(f_yk/σ_Rcr) und λ̄_p = √(α/(1−β)) folgt χ nach 8.5.2(3) und
σ_Rd = χ f_yk/γ_M1. Die Interaktion nach 8.5.3(3) lautet

      (σ_x/σ_x,Rd)^k_x − k_i (σ_x σ_θ)/(σ_x,Rd σ_θ,Rd)
        + (σ_θ/σ_θ,Rd)^k_θ + (τ/τ_Rd)^k_τ ≤ 1

mit k_x = 1,25 + 0,75 χ_x, k_θ = 1,25 + 0,75 χ_θ, k_τ = 1,75 + 0,25 χ_τ und
k_i = (χ_x χ_θ)². Zug beult nicht und geht nicht ein. Ist der Zylinder lang
(ω > 0,5 r/t), weist das Programm darauf hin, dass zusätzlich das Knicken als
Stab nach EN 1993-1-1 zu prüfen ist.

**Grenzen**: nur Kreiszylinder mit konstanter Wanddicke — Kegel, Kugeln und
ringversteifte Schalen fehlen, ebenso die numerischen Verfahren (LA, GNA,
GMNIA) nach 8.6 und 8.7. Beim ebenen Feld sind die wirksamen Breiten nach
Abschnitt 4 nur in der Querschnittsklassifizierung (Klasse 4) enthalten, nicht
als eigener Feldnachweis. Liegen die Elemente eines ebenen Feldes nicht in
einer Ebene, wird das gesagt.

Für **Stabquerschnitte** sind die wirksamen Breiten nach Abschnitt 4 dagegen
vollständig enthalten (Kapitel 5.2a): A_eff, W_eff,y, W_eff,z und e_N gehen in
die Querschnitts- und die Stabilitätsnachweise ein.

## 5d Volumen (DIN EN 1993-1-1, 6.2.1(5))

Ein Volumen hat keinen Querschnitt. Klassifizierung, plastische Widerstands-
momente, Knicklängen und die Interaktionsformeln der Abschnitte 6.2 und 6.3
sind darauf nicht anwendbar. Was anwendbar ist, ist der **Spannungsnachweis
am Punkt**, und den nennt 6.2.1(5) ausdrücklich als konservative Alternative.
Für den allgemeinen räumlichen Spannungszustand ist das die Vergleichsspannung
nach von Mises:

      σ_v = √(½[(σ_1−σ_2)² + (σ_2−σ_3)² + (σ_3−σ_1)²]) ≤ f_y/γ_M0

mit den Hauptspannungen σ_1 ≥ σ_2 ≥ σ_3 als Eigenwerten des Spannungstensors.
**Wo wird ausgewertet? — die Auswerteregel (22.09.2026).** Nachgewiesen wird an
den **Eckknoten**, mit der **geglätteten** Spannung: an jedem Eckknoten das Mittel
der Elementwerte, getrennt nach Körper (`Element.group`) und Werkstoff; je Element
zählt seine größte Ecke (`res.solid_rand`, aus `res.solid_knoten`). Der Elementwert
an der Ecke ist elastisch das Spannungsfeld des Elements dort (beim Hexaeder mit den
inneren Moden, beim tet4 sein einer Wert), bei einem **fließenden** Element der
Wert am nächsten Integrationspunkt.

Warum so, gemessen am Kragarm-Prüfkörper (1,0 × 0,1 × 0,2 m, Oberkante bei L/2,
nach Saint-Venant exakt 355 N/mm², `tests/pruefkoerper.py`), Abweichung in N/mm²:

| FHG | hex8 Element-Maximum (bis 22.09.) | hex8 geglättet | tet10 Element-Maximum | tet10 geglättet |
|---|---|---|---|---|
| 90 / 405 | +173,2 | −9,6 | +156,6 (405) | +14,2 (405) |
| 405 / 2 295 | +64,7 | **+0,8** | +85,2 (2 295) | +4,0 (2 295) |
| 2 295 / 15 147 | +31,1 | +0,2 | +43,4 (15 147) | +1,0 (15 147) |

Ein Element mit linearem Ansatz zeigt an seinen Ecken den Momentenverlauf
versetzt: die Ecke zur Einspannung zu hoch, die andere zu niedrig. Das Maximum
eines Elements konvergiert darum nur mit der Elementlänge (am feinsten hex8-Netz
noch +31 N/mm²), der Mittelwert der Nachbarn an einem Knoten dagegen quadratisch:
der hex8 trifft die 1 N/mm² mit 405 Freiheitsgraden. Über eine Körper- oder
Werkstoffgrenze wird nicht gemittelt — die Spannung springt dort wirklich.

Die **Elementmitte** allein genügte schon früher nicht: am Kragarm aus Hexaedern
mit vier Elementen über die Höhe zeigte sie 43,3 N/mm² gegen M/W = 60,0 N/mm².
Maßgebend ist der größte Wert über alle Knoten des Bereichs und alle
GZT-Kombinationen; der Bericht nennt den Knoten („Knoten 812 (geglättet)“).

**Fließende Elemente** tragen den Wert ihres nächsten Integrationspunkts bei
(`plastizitaet.punktspannungen`): nur dort ist der plastische Zustand bekannt, und
jeder dieser Werte liegt auf oder in der verfestigten Fließfläche — ein Mittel
solcher Werte ebenso (die Fließfläche ist konvex). Bis zum 22.09.2026 stand für
fließende Elemente die Elementmitte im Ergebnis; beim Sechsflächner unter Biegung
ist das der Ort, an dem die Spannung null ist. Mit fünf Lobatto-Punkten über die
Dicke (§ 5e.1) trifft die geglättete Randspannung einer einzigen hex8-Lage unter
1,20 M_el die Momenten-Krümmungs-Lösung auf 1 N/mm²
(`tests/test_volumen.py`, `test_randspannung_fliessend`).

**An freien Oberflächen σ·n = 0 (23.09.2026, Auftrag B6).** Das Knotenmittel am
Rand mischt die Randelemente mit ihrem Inneren, auch in den Komponenten, die der Rand
kennt: an einer freien Oberfläche ist σ·n = 0. Seitdem zieht `solver.rand_projizieren`
die geglättete Knotenspannung dort auf σ·n = 0, mit der kleinsten Änderung im
Frobenius-Maß:

    σ' = σ − n⊗r − r⊗n + (n·r) n⊗n,   r = σ n

— die Tangentialanteile bleiben. An einer konvexen Kante oder Ecke werden alle
Normalen **zugleich** erfüllt (Ecke dreier freier Seiten: σ = 0). Die Normale am
Knoten kommt aus der Geometrie der Seiten am Knoten (tet10/hex20: aus der gekrümmten
Seite), flächengewichtet gemittelt, solange alle innerhalb 30° liegen; mehr ist eine
Kante (die Facettierung eines Bogens ist 18°). **Frei** heißt streng: projiziert wird
nur ein Knoten, der in genau einem Körper und Werkstoff liegt, an dem kein Stab-,
Schalen-, Feder- oder Spaltelement hängt, der kein Lager, keinen Kontakt, keine
Kopplung, keinen Starrkörper, keine Fuge, keine Punktmasse und keine Last des
Lastfalls trägt, und dessen Randseiten alle frei sind (eine Seite mit einem nicht
freien Knoten ist nicht frei). Nicht angefasst werden außerdem **einspringende**
Kanten (die Spannung ist dort singulär, die Projektion würde den Kerbgrund schönen)
und **fließende** Elemente (die Fließfläche begrenzt die Spannung; am Balken mit einer
hex8-Lage unter 1,20 M_el schob die Projektion die Randfaser auf 251,6 N/mm², über die
verfestigte Fließgrenze 236,3). Eigengewicht, Temperatur und Vorspannung wirken im
Volumen und lassen σ·n = 0 stehen. In einer Kombination heißt ein Knoten nur „σ·n = 0“,
wenn er es in jedem Lastfall war; die Summe bleibt linear.

Gemessen 23.09.2026 (`tests/test_randspannung.py`), σ_v in N/mm², Knotenmittel →
σ·n = 0:

| Prüfkörper | Netz | Knotenmittel → σ·n = 0 |
|---|---|---|
| Kirsch-Loch, Zug, freier Lochrand bei 90° (halbe Dicke) | hex8 4 455 FHG | −14,68 → **−1,10** |
| | hex8 16 575 FHG | −5,22 → +0,80 |
| | tet10 8 019 FHG | −30,54 → −19,41 |
| | tet10 29 835 FHG | −5,80 → −4,23 |
| | tet4 16 575 FHG | −24,07 → −14,82 |
| Kragarm, Oberkante bei L/2 (Biegung) | hex8 90 / 405 / 2 295 FHG | −9,48 / +0,77 / +0,22 → −1,62 / +0,21 / −0,03 |
| | tet10 405 / 2 295 / 15 147 FHG | +5,39 / +4,03 / +1,02 → +4,72 / +4,07 / +1,05 |
| | tet4 90 / 405 / 2 295 FHG | −259,9 / −165,6 / −69,9 → −278,0 / −167,3 / −69,5 |

Beim Kragarm liegt bei den Netzen mit einem Element über die Breite (hex8 und tet4
90 FHG, tet10 405 FHG) kein Knoten in Breitenmitte; dort ist der Kantenknoten
y = 0 gemessen — eine konvexe Kante mit zwei freien Seiten, also mit beiden Normalen
projiziert.

Am freien Lochrand rückt der hex8 bei 4 455 FHG von −14,7 auf −1,1 N/mm², bei
16 575 FHG von −5,2 auf +0,8 — das Knotenmittel braucht für 1 N/mm² ein feineres Netz
als gemessen. Der tet10 bleibt dort bei den gemessenen Netzen über 1 N/mm². Unter Biegung an einer ebenen Seite ändert es beim
tet10 weniger als 0,1 N/mm²; **schlechter** wird der grobe tet4 (90 FHG: 18 N/mm²),
dessen Wert ohnehin 260 N/mm² daneben liegt. Kosten: die Randseiten einmal je Rechnung
(0,32 s bei 196 608 Tetraedern), danach 0,03 s je Lastfall. Die Einstellung
`Model.randspannung` = "gemittelt" stellt das Knotenmittel wieder her; das Ergebnis
nennt die gerechnete Art (`res.info["randspannung"]`), der Nachweis an der Stelle
(„Knoten 812 (geglättet, σ·n = 0)“). Die **Ermüdung** der Volumen liest seit dem
23.09.2026 dieselbe Knotenspannung (5.5-3); bis dahin las sie `res.solid_res` je
Element, und so rechnet sie weiter mit der Einstellung `ermuedung_volumen` = „element“.

`res.solid_res` bleibt je Element der maßgebende eigene Punkt (Anzeige, ältere
Ergebnisse); der Fehlerschätzer liest das Elementmittel `res.solid_mittel` (§ 6c).
Ohne Knotenwerte — eine ältere Ergebnisdatei, eine Überlagerung verschiedener
Situationen — nimmt der Nachweis wie bisher `solid_res`.

Zusätzlich ausgewiesen:

      τ_max = (σ_1 − σ_3)/2                  größte Schubspannung
      η_Tresca = (σ_1 − σ_3)/f_yd            Vergleich zu von Mises
      σ_m = (σ_1+σ_2+σ_3)/3                  hydrostatische Spannung
      h   = σ_m/σ_v                          Mehrachsigkeit

Bei **dreiachsigem Zug** (σ_3 > 0) und h > 1/3 ist die Verformungsfähigkeit
stark eingeschränkt: der Werkstoff kann nicht mehr durch Gleiten ausweichen,
und die Bruchgefahr steigt, obwohl σ_v unauffällig bleibt. Statik3D rechnet
den Sprödbruchnachweis nach DIN EN 1993-1-10 nicht, benennt den Fall aber im
Bericht mit den Zahlenwerten. Damit nicht jeder einachsige Zugkörper, dessen
σ_3 rechnerisch bei 10⁻¹⁴ N/mm² landet, als dreiachsig gemeldet wird, muss
σ_3 über 2 % von σ_v und über 1 N/mm² liegen.

**Spannungssingularitäten.** An einspringenden Ecken, unter Einzellasten und
an Punktlagern wächst die Spannung mit jeder Netzverfeinerung; ein Nachweis
gegen f_y ist dort ohne Aussage. Zwei Vorkehrungen:

* Ein Bereich kann als `singular` gekennzeichnet werden. Dann werden die
  Spannungen berichtet, aber kein Nachweis geführt — der Status heißt
  „nur berichtet“, nicht „erfüllt“.
* Unabhängig davon vergleicht das Programm die Spitzenspannung mit dem
  Mittelwert des Bereichs. Liegt sie um mehr als den Faktor 5 darüber, weist
  es auf eine mögliche Singularität hin.

**Die Erzeugnisdicke.** EN 1993-1-1 Tab. 3.1 mindert die Streckgrenze mit der
Erzeugnisdicke ab (S355: 355 N/mm² bis 40 mm, darüber 335; ein aus RFEM 6
übernommener Werkstoff bringt seine eigene Dickentabelle mit). Bis zum
22.09.2026 rechnete der Volumennachweis mit `yield_strength(0.0)`, also
**immer mit der dünnsten Stufe**: ein Lagerblock von 80 mm wies sich mit 355
statt 335 N/mm² nach, η fiel 6,0 % zu klein aus — auf der unsicheren Seite.
Der Stabnachweis macht es seit jeher richtig (`mat.yield_strength(sec.t_max)`).

Ein Volumen hat keine Dicke im Sinne eines Querschnitts. Angesetzt wird darum
die **kleinste Abmessung des umschließenden Quaders des ganzen
zusammenhängenden Körpers**, zu dem die Elemente des Bereichs gehören: bei
einer Platte ihre Dicke, bei einem Rundstahl sein Durchmesser, bei einem Block
seine kürzeste Kante. Der Körper und nicht die Auswahl, weil die Auswahl dem
Anwender gehört: an einem Block 300 × 300 × 200 mm, vernetzt mit 6 × 6 × 8
Elementen, misst der Körper 200 mm (f_y = 335), eine einzelne Elementlage aber
25 mm (f_y = 355) — dieselbe Stelle, 6,0 % auf der unsicheren Seite, nur weil
weniger markiert war. Die Körper werden als Zusammenhangskomponenten des
Graphen Element/Knoten bestimmt (`scipy.sparse.csgraph`), zwei getrennte
Körper im selben Modell bleiben getrennt.

Bei einem **aus Blechen geschweißten** Bauteil ist der Körper umgekehrt zu
dick — dort ist die Blechdicke maßgebend. Die Erzeugnisdicke ist deshalb am
Volumenbereich angebbar und hat dann Vorrang. Die angesetzte Dicke steht in der
Übersicht des Berichts (Spalte t, mit `*` wenn selbst angegeben); mindert sie
f_y ab, sagt der Bericht es zusätzlich als Hinweis, damit ein Prüfer die
Festlegung beurteilen kann (Tests `test_erzeugnisdicke_mindert_die_streckgrenze`
und `test_erzeugnisdicke_ist_angebbar`).

Wird ein **Kerbradius** angegeben, prüft das Programm zusätzlich, ob die
mittlere Elementgröße h ≤ r/3 ist — sonst liegen weniger als drei Elemente
über den Radius und die Kerbspannung wird unterschätzt.

**Grenzen**: Keine Stabilität des Volumenkörpers — die geometrische
Steifigkeit ist nur für Stabelemente gebildet, ein Verzweigungsproblem für
Volumen gibt es nicht. Kein Plastizieren, kein Kriechen und nicht der
Sprödbruchnachweis nach EN 1993-1-10 selbst. Die Ermüdung der Volumen aus der
Hauptspannung je Knoten steht in 5.5-3.

## 5d-2 Passungen: Spiel, Übergang, Presspassung (17.09.2026)

**Warum das hierher gehört.** Ob ein Passstift hält, entscheidet nicht die
Kontakteinstellung, sondern die Passung auf der Zeichnung. Der Anwender:
„Je nach gewähltem Spalt/Passung ergibt sich eine Fügekraft, z. B. aus einer
Übergangspassung heraus, die den Passstift statisch hält; oder der Spalt ist
als Spielpassung ausgeführt, dann könnte sich der Passstift drehen, aber das
System würde dennoch funktionieren, da der Passstift nicht seine Lage ändert
und herausfällt; oder es könnte eine Presspassung sein, die daraus
entstehende Kraft wäre eine zusätzliche Spannung im System und der Passstift
wäre gehalten.“

**Die Rechnung.** Aus den vier Abmaßen folgt die Überdeckung (DIN ISO 286):

    Höchstübermaß  Ü_max = es − EI      Mindestspiel  S_min = −Ü_max
    Mindestübermaß Ü_min = ei − ES      Höchstspiel   S_max = −Ü_min

und daraus die Art: Ü_max ≤ 0 heißt **immer Spiel**, Ü_min ≥ 0 heißt **immer
Übermaß**, dazwischen hängt es am Istmaß (**Übergang**). Entschieden wird an
den Grenzfällen, nicht am Mittelwert — sonst hieße eine Paarung, die im
ungünstigen Fall klemmt, „Spielpassung“.

**Was daraus im Modell wird.** Spiel ist eine Eigenschaft der Fuge (der
Kontakt schließt erst, wenn das Spiel durchfahren ist), Übermaß eine Last
(die Fuge steht vor der äußeren Last unter Druck). Beides gibt es im
Programm schon; neu ist, dass die Abmaße entscheiden, welches von beidem
gesetzt wird. Eine eingebaute Abmaßtabelle gibt es bewusst nicht (Begründung
in `statik3d/passungen.py`): beim Abgleich zweier Quellen wich m6 für
18–30 mm um 8 µm ab. Stattdessen prüft das Programm die eingetragenen Abmaße
gegen den gewählten Einsatzzweck und widerspricht bei Abweichung.

**Halt in der Achsrichtung.** Ein Stift in einer Bohrung ist quer
formschlüssig gehalten, längs seiner Achse aber nur durch Reibung — und
Reibung braucht Anpressung. Gemessen an einem Stift Ø40 in einem außen
gehaltenen Auge, quer mit 20 kN belastet: reibungsfrei mit 0,02 mm Spiel
meldet das Programm die axiale Verschiebung als freie Bewegung
(Abschnitt 7b) und rechnet mit Hilfsfesselung weiter; mit μ = 0,2 ist sie
fort, und 5 kN Zug in Achsrichtung werden abgetragen (Auflagersumme
5,00 kN). Bei Presspassung liefert das Übermaß die Anpressung und damit die
Haftreibung. Die Kontakt-Iteration kostet mit Reibung mehr Schritte: 51
statt 6, weil Knotenzustände zwischen Haften und Gleiten pendeln und der
Oszillationsschutz sie festhält.


**Die Spannung kommt aus dem Ergebnis, nicht aus einer zweiten Rechnung**
(20.09.2026). Der Nachweis bildete σ = D·B·u aus der Verschiebung neu. Das
lässt weg, was der Löser berücksichtigt: die plastische Vorspannung D·ε_p.
Gemessen am Stauchwürfel (384 `tet4`, S355, Fließen an, 370 von 384 Elementen
fließen): σ_v,max **1 566 MPa im Ergebnis gegen 31 934 MPa neu gerechnet** —
Faktor 20,4, und der Nachweis war damit um ebenso viel zu ungünstig, ohne
dass es jemand gesehen hätte.

**Seit dem 20.09.2026 steht die Mehrpunktauswertung im Nachlauf selbst**
(`solver._post_chunk`), nicht mehr im Nachweis. `res.solid_res` trägt den
**maßgebenden** Auswertepunkt — den mit der größten Vergleichsspannung —,
gerechnet mit allem, was der Löser berücksichtigt: plastische Vorspannung und,
mit `Model.knotendilatation`, die gemittelte Volumendehnung. Beim `tet4` ist
das derselbe eine Punkt wie zuvor, das Drehlager rechnet unverändert.

**Warum die Ecken und nicht die Gaußpunkte** (gemessen 21.09.2026 am
Kragträger aus `hex8`, elastisch, **reine Biegung ohne Kontakt** — ein glattes
Problem ohne Singularität; σ_xx am eingespannten Element gegen M/W). Was die
Tabelle deckt, ist genau dieser Fall; für ein Element an einer Kontaktkante
neben einer Fließzone folgt aus ihr nichts:

| Lagen über die Höhe | Balken M/W | Mitte | Gaußpunkte | Ecken |
|---|---|---|---|---|
| 1 | 14,62 N/mm² | 0,0 % | 61,3 % | **110,8 %** |
| 2 | 14,62 N/mm² | 50,9 % | 80,9 % | **105,2 %** |
| 4 | 14,62 N/mm² | 75,5 % | 91,9 % | **104,8 %** |

Die Gaußpunkte wären der numerisch bravere Ort — dort ist die Spannung
superkonvergent, und dort gilt die Fließbedingung. Aber sie liegen **innen**:
der äußerste eines `hex8` sitzt bei 57,7 % der halben Elementhöhe, und unter
Biegung fehlt genau der Rand. Sie unterschätzen um bis zu 39 %. Die Ecken
laufen gegen 105 % und liegen damit leicht auf der sicheren Seite.

**Der Preis steht daneben, und er ist hoch.** An einer Singularität —
Kontaktrand, einspringende Ecke, steifer Einschluss — hat die Spannung keinen
endlichen Wert; sie wächst mit jeder Verfeinerung, und ein Spitzenwert dort ist
keine Größe, sondern eine Eigenschaft des Netzes.

Ein Beispiel dazu, **das aber nichts belegt**: am Drehlager meldete auf dem
gesweepten Netz ein `hex8`, der selbst nicht fließt, 3 006 N/mm² als Eckwert,
während die fließenden Elemente brave Werte zeigten (`tet4` 360,4 mit
ε_p,eq 0,255 %, `pent6` 461,8; Löser-Sitzung, 21.09.2026). Die Fließbedingung
war nicht verletzt — an den Gaußpunkten dieses Elements lag die Spannung unter
f_y. **Dieses Netz ist jedoch unabhängig davon fehlerhaft**: dieselbe Rechnung
liegt rein elastisch bei der Verformung um Faktor 8 daneben (0,1675 gegen
1,3498 mm gegen das alte Netz, beides kontaktkonvergiert), und 992 seiner
9 368 Keile sind entartet. Welcher Teil der 3 006 aus der Kerbe kommt und
welcher aus diesem Fehler, ist **nicht getrennt**. Das Beispiel taugt darum
weder für die Eckwertregel noch gegen sie; die Kragträgertabelle oben trägt sie
allein.

**Daraus folgt für den Anwender:** ein Spitzenwert aus `solid_res` ist an einer
Singularität keine Nachweisgröße. Das ist keine Eigenheit dieser Auswertung,
sondern der Finite-Elemente-Methode; dieselbe Erfahrung steht in § 5d-2 zu den
Passstiften des Drehlagers (4 930 N/mm² gegen einen Handnachweis um Faktor
50 bis 80 darunter). Die Auswertungsregel wurde deshalb **nicht** geändert: an
glatten Problemen ist sie die beste der drei (Tabelle oben), und an
Singularitäten gibt keine der drei eine brauchbare Zahl. Was fehlt, ist nicht
eine andere Regel, sondern eine Erkennung, **ob** ein Spitzenwert an einer
Kerbe sitzt — das ist eine offene Baustelle und wird hier nicht geraten.

**Mit einer Ausnahme: fließende Elemente melden weiter die Elementmitte.** Die
Plastizität wird an den **Gaußpunkten** erzwungen; die Auswertepunkte (Ecken)
liegen außerhalb, und die abgezogene Vorspannung D·ε_p ist das Mittel über die
Gaußpunkte (§ 5e.1). An einer Ecke wächst ε über dieses Mittel hinaus, ε_p
bleibt zurück — die gemeldete Spannung schießt über die Fließfläche hinaus.
Gemessen am Reibblock (20.09.2026): Eckwert **2,93 N/mm² gegen die verfestigte
Fließgrenze 1,42**, und damit über dem **elastischen** Spitzenwert von 2,30 —
was es nicht geben kann, denn Fließen baut Spannung ab. In der Elementmitte ist
das Elementmittel dagegen die richtige Berichtigung. Der Preis: in einer
Fließzone zeigt ein Sechsflächner unter Biegung wieder den Mittelwert, nicht
den Randwert. Wer dort den Randwert braucht, braucht mehr Elemente über die
Dicke — dieselbe Regel wie für das Fließen selbst.

Damit haben Anzeige und Nachweis dieselbe Zahl. Vorher stand in `solid_res`
die Elementmitte, und der Nachweis rechnete sich den Randwert selbst zurück,
indem er den elementkonstanten Versatz Δ = σ_Ergebnis − σ_Nachrechnung(Mitte)
auf alle Punkte addierte. Das war richtig, solange der Versatz wirklich
elementkonstant war — mit der Plastizität je Gaußpunkt (§ 5e.1) ist er es
nicht mehr. Der Nachweis nimmt jetzt den Wert aus dem Ergebnis und benutzt
seine eigene Nachrechnung nur noch, um die Stelle zu **benennen** („Mitte",
„Eckpunkt 3"). Geprüft in `tests/test_volumen.py` (Nachweis gegen Löser
1,0000; `solid_res` trägt den Randwert, nicht die Mitte).

## 5e Plastizität der Volumenkörper (17.09.2026)

**Anlass.** Spannungsspitzen an Passstiften und Bohrungsrändern (V34:
4930 N/mm² am Stift, ein Vielfaches der Streckgrenze) sind elastische
Rechenwerte, die es in der Wirklichkeit nicht gibt: dort fließt der Stahl,
die Spannung bleibt bei der Streckgrenze, die Kraft verteilt sich um und
die Verformung wächst. Der Anwender: „bei zu hohen Spannungen Streckgrenze
und Fließgrenze berücksichtigen und Verschiebung ggf. zulassen“.

**Werkstoffgesetz.** Von Mises mit isotroper linearer Verfestigung. Die
Vergleichsspannung q = √(3/2 s:s) des Spannungsdeviators s bleibt unter
fy + H·ε_p,eq; der Verfestigungsmodul H folgt aus der eingestellten
Tangente E_t = r·E nach dem Fließen: H = E·r/(1 − r) (uniaxial gilt
σ = fy + H·ε_p und ε = σ/E + ε_p, also dσ/dε = E·H/(E + H) = E_t).
Rückführung (radial return) je Element, an der Elementmitte:

    σ_trial = D (ε − ε_p,alt),  s = dev σ_trial,  q = √(3/2 s:s),  f = q − (fy + H ε_p,eq)
    f > 0:  Δγ = f / (3G + H),  n = 3/2 s/q,  σ = σ_trial − 2G Δγ n,  Δε_p = Δγ n,  Δε_p,eq = Δγ

(Voigt-Reihenfolge wie im Element, plastische Gleitungen als
Ingenieurgleitungen, also doppelte Schubanteile). Werkstoffe ohne
Streckgrenze („Starr“, Beton ohne fy) bleiben elastisch; das Protokoll
nennt sie.

**Verfahren: Anfangsdehnungs-Iteration.** Der Löser dieses Programms ist
linear-elastisch plus Kontakt (Aktivmengen-Iteration mit fester
Faktorisierung). Das Fließen sitzt darauf, ohne die
Steifigkeitsmatrix anzufassen: die plastische Dehnung ε_p ist eine
Anfangsdehnung wie eine Temperaturdehnung, ihre äquivalenten Knotenlasten
F_p = Σ ∫ Bᵀ D ε_p dV kommen zur äußeren Last, die Spannung ist
σ = D(ε − ε_p). Iteriert wird

    u_k = K⁻¹ (F + F_p,k−1),   ε_p,k = Rückführung(D ε(u_k) − D ε_p,0)

— das Anfangssteifigkeitsverfahren; ε_p,0 ist der Zustand am **Anfang der
Laststufe** (seit dem 23.09.2026, § 5e.2 — vorher ε_p,k−1). Jeder Schritt
ist eine lineare Lösung mit der vorhandenen Faktorisierung; mit Kontakt
eine Kontakt-Iteration, warm gestartet vom Zustand des vorigen Schritts.
Die Last wird in Laststufen aufgebracht (Vorgabe 3), damit die Rückführung
auf dem Belastungspfad bleibt. Konvergenzmaß ist seit dem 23.09.2026 der
**geschätzte Fehler** der plastischen Knotenlasten gegen die Last,
|F_p,k − F_p,k−1| / |F| · max(1, ρ/(1 − ρ)) ≤ Toleranz (Vorgabe 1e-3), mit
der Rate ρ aus dem Verlauf der Änderungen (§ 5e.2); vorher die Änderung
allein.

**Beschleunigung (Aitken).** Das Anfangssteifigkeitsverfahren zieht sich
mit dem Faktor E_t/E zusammen: bei 2 % Verfestigung 0,98 je Schritt —
gemessen am Zugversuch (ein Hexaeder, 1,1 fy) brachten 60 Schritte 65 %
des Wegs. Die Fixpunktfolge F_p wird deshalb mit Aitken-Δ² relaxiert:
aus zwei Residuen r_k = F_p,neu − F_p folgt ω = −ω·(r_k−1·Δr)/|Δr|², auf
0,5 … 200 begrenzt und je Laststufe neu begonnen. Der Zugversuch trifft
damit ε = σ/E + (σ − fy)/H auf 1e-6 in **4 Schritten in 2 Laststufen**
(`tests/test_plastizitaet.py`); der reibungsgelagerte Block mit fy auf
60 % seiner elastischen Vergleichsspannung (50 fließende Elemente,
Kontakt-Iteration mit 19 Schritten) konvergiert in 27 Schritten bei
Toleranz 1e-4, mit Gleichgewicht der Auflager (Auflager = Last, nicht
Last + F_p: die Reaktion ist K·u − F_p − F, die innere Kraft ∫Bᵀσ dV).

**Wo Aitken nicht mehr reicht (20.09.2026).** Bei **kleiner Verfestigung**
trägt die Beschleunigung nicht. Gemessen am einachsigen Zugversuch (Quader
an drei Symmetrieebenen gehalten, am anderen Ende gezogen, tet4, S355, 1 %
Verfestigung, drei Laststufen zu höchstens 25 Schritten, Toleranz 1e-3):

| Last | Schritte | konvergiert | größte σ_v gegen σ |
|---|---|---|---|
| 1,05 fy | 27 | nein | +0,53 % |
| 1,20 fy | 27 | nein | +1,89 % |
| 1,50 fy | 36 | nein | **+28,49 %** |

Der reine Fixpunkt zieht sich mit 1 − E_t/E zusammen, bei 1 % also 0,99 je
Schritt — rund 700 Schritte für 1e-3. Aitken schätzt den Faktor aus zwei
Residuen, überschießt dort (ω ist bis 200 erlaubt) und bleibt danach bei
einer Änderung von 1e-1 stehen. Die Folge war kein langsames, sondern ein
**falsches** Ergebnis: bei 1,5 fy lag die größte Vergleichsspannung 28,5 %
daneben, die Dehnung am gezogenen Ende 9,5 %. Mehr Schritte helfen nicht —
mit Toleranz 1e-8 wurden es 51 und die Abweichung stieg auf 32,2 %.

**Verfahren: konsistente elastoplastische Tangente (20.09.2026, Vorgabe).**
Statt die Steifigkeit festzuhalten, wird sie je Schritt neu aufgestellt und
faktorisiert — mit der zur Rückführung **konsistenten** Tangente (Simo &
Hughes, Box 3.2), nicht mit der kontinuierlichen:

    D_ep = K δ⊗δ + 2G θ (I − δ⊗δ/3) − 2G θ̄ N⊗N
    θ = 1 − 3G Δγ / q_trial,   θ̄ = 1/(1 + H/3G) − (1 − θ),   N = s_trial/‖s_trial‖

Das ist die Ableitung der Rückführung nach der Gesamtdehnung; geprüft wird
sie gegen die zentrale Differenz über 31 Dehnungszustände (einachsig, Schub,
mehrachsig, mit und ohne vorhandenes ε_p) und 0,1 % bis 50 % Verfestigung —
größte Abweichung 1,4·10⁻⁹. Einachsig kommt aus D_ep exakt E_t heraus.

Gelöst wird in **Gesamtform**, damit Randbedingungen, Kopplungen und
Kontakt beim Löser bleiben:

    (K + ΔK) u_{k+1} = F_k + F_p(u_k) + ΔK u_k,   ΔK = Σ_e V_e Bᵀ (D_ep − D_el) B

Das ist zeilenweise identisch mit dem Newton-Schritt (K + ΔK)Δu = F_k +
F_p − K u auf dem Residuum, nur ohne Inkrementvektor. ΔK geht als
`K_zusatz` denselben Weg wie die abgezogene Steifigkeit ausgefallener
Zugstäbe. Der Kugelanteil fällt heraus (Fließen ist volumentreu), ΔK trägt
also nur dort Einträge, wo Elemente fließen. Für H > 0 ist D_ep
positiv definit — der Eigenwert in Fließrichtung ist 2G(θ − θ̄) =
2G·(H/3G)/(1 + H/3G) > 0 —, also bleibt K + ΔK positiv definit; ohne
Verfestigung wird er null, und dann fällt das Verfahren von selbst auf die
Anfangsdehnungs-Iteration zurück. Bei sehr kleiner Verfestigung rechnet ΔK
seit dem 23.09.2026 mit einem Boden H ≥ 10⁻⁴·3G (`plastizitaet.H_TANGENTE`;
die Rückführung behält das wahre H): mit E_t/E = 10⁻¹² brach der Löser über
der Grenzlast mit „Gleichungssystem singulär“ ab und nannte ein Element als
Splitter, mit dem Boden heißt es „nicht konvergiert“. Ab E_t/E = 1,2·10⁻⁴
greift der Boden nicht, bei jeder üblichen Verfestigung rechnet der Newton
bitgleich wie vorher (`tests/test_plastizitaet.py`).

Zwei Feinheiten, an denen es hängt:

* Die Rückführung geht in jedem Schritt vom Zustand am **Anfang der
  Laststufe** aus, nicht vom vorigen Schritt. Nur dann ist F_p eine Funktion
  von u allein und D_ep wirklich ihre Ableitung. Die Anfangsdehnungs-
  Iteration schreibt ε_p dagegen von Schritt zu Schritt fort — im Grenzwert
  dasselbe, aber nicht differenzierbar.
* ΔK wird mit **B am Auswertepunkt** und dem Elementvolumen gebildet, nicht
  als ∫BᵀΔD B dV über die Gaußpunkte. Denn ε_p hängt allein an der Dehnung
  in der Mitte — dort wird die Spannung ausgewertet —, also ist
  ∂F_p/∂u = [Σ_gp w Bᵀ_gp]·D·(∂ε_p/∂ε_m)·B_m. Bei tet4 sind beide Formen
  gleich; bei hex8 ist die Gaußpunktfassung in den Biegemoden **zu weich**,
  auf die F_p gar nicht reagiert: am Reibblock lief sie mit rund Faktor 100
  je Schritt davon (Änderung 1,7 → 1,0·10³⁶ in 19 Schritten), während die
  Mittelpunktfassung in 4 Schritten konvergiert. Die Mittelpunktfassung ist
  außerdem symmetrisch — CHOLMOD in der Löserkette verträgt nichts anderes.

*(Der vorige Absatz beschreibt den Stand vor dem 20.09.2026, als ε_p an der
Elementmitte hing. Seitdem lebt der plastische Zustand an jedem Gaußpunkt —
§ 5e.1 —, und die Gaußpunktfassung ist die richtige.)*

**ΔK ist für jeden Volumentyp die exakte Ableitung** (gemessen 22.09.2026,
`tests/test_plastizitaet.py`, `test_tangente_exakt_fuer_jeden_typ`): gegen
zentrale Differenzen −∂F_p/∂u weicht ΔK bei tet4, hex8 (mit inneren Moden),
tet10, hex20, pent6, pent15 und pyr5 um 0,6·10⁻⁹ bis 3,2·10⁻⁹ ab — das ist der
Fehler der Differenzen selbst. Newton konvergiert damit quadratisch
(`test_newton_konvergiert_quadratisch`, Kragträger 200 × 200 mm unter
1,20 M_el, eine Laststufe, Änderung je Schritt):

| | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| hex8 (5 × 1 × 4) | 2,2·10⁻¹ | 3,6·10⁻¹ | 1,9·10⁻³ | 2,5·10⁻⁶ | 2,9·10⁻¹² |
| tet10 (5 × 1 × 2) | 9,6·10⁻² | 1,5·10⁻¹ | 2,1·10⁻³ | 2,4·10⁻⁶ | 7,9·10⁻¹² |

Bis zum 22.09.2026 stand hier, ΔK weiche bei hex8 und pent6 um rund 1 %, bei
tet10, hex20 und pent15 um bis zu 53 % ab und bleibe ein Quasi-Newton. Das galt
für die Mittelpunktfassung vor dem 20.09.2026 und ist seitdem falsch; es war im
Quelltext (`plastizitaet.py`) und hier stehen geblieben, ohne neu gemessen zu
werden.

**Gemessen** am selben Zugversuch (1 % Verfestigung, drei Laststufen,
Toleranz 1e-3; „Abweichung“ ist die mittlere Dehnung am gezogenen Ende
gegen ε = σ/E + (σ − fy)/H):

| Last | Weg | Schritte | Faktorisierungen | Abweichung |
|---|---|---|---|---|
| 1,20 fy | Anfangsdehnung | 27, nicht konvergiert | 0 | −7,4 % |
| 1,20 fy | Tangente | 7 | 4 | +0,17 % |
| 1,50 fy | Anfangsdehnung | 36, nicht konvergiert | 0 | +9,5 % |
| 1,50 fy | Tangente | 12 | 9 | +0,10 % |

Die größte Vergleichsspannung der Elementmitten (das Maß des Probelaufs)
geht von 28,49 % auf 1,26 % zurück; der Rest ist Netz, nicht Iteration — er
bleibt bei Toleranz 1e-8 und bei doppelter Netzdichte stehen. Und die
Schrittzahl hängt **nicht mehr an der Verfestigung** (1,2 fy, 6000
Tetraeder):

| E_t/E | Anfangsdehnung | Tangente |
|---|---|---|
| 1 % | 27, nicht konvergiert | 6 Schritte, 3 Faktorisierungen |
| 2 % | 27, nicht konvergiert | 6, 3 |
| 5 % | 15 | 6, 3 |
| 10 % | 10 | 6, 3 |
| 20 % | 8 | 6, 3 |

**Was es kostet.** Eine Faktorisierung je Newton-Schritt statt einer je
Rechnung — genau `Schritte − Laststufen`, denn der letzte Schritt jeder
Laststufe stellt nur noch fest, dass es passt. Am Drehlager kostet eine
Faktorisierung 3,2 s gegen 0,31 s je Rückwärtseinsetzen (476 214 Zeilen),
das Aufstellen von ΔK rund 7,5 µs je fließendem Element (gemessen: 24 576
fließende Tetraeder in 0,184 s). Wo die Anfangsdehnungs-Iteration heute
schon in acht bis zehn Schritten konvergiert (Verfestigung ab 10 %, örtliches
Fließen), ist sie damit die billigere: `Plastizität → Verfahren →
Anfangsdehnung` schaltet zurück. Bei kleiner Verfestigung gibt es diese
Wahl nicht — dort konvergiert sie gar nicht.

**Rechenzeit: blockweise statt Element für Element (19.09.2026).** Die
Plastizität macht an einem großen Modell den Löwenanteil der Rechenzeit — am
Drehlager (646 706 Tetraeder, 2 974 344 Freiheitsgrade) entfielen auf einen
warmen Lastfall 24 % auf den Gleichungslöser und **76 % auf die
Plastizität**. Die Ursache war nicht die Physik: ein Schritt kostete
dieselben 51 Sekunden, ob null oder viele Elemente flossen. Es war der
Aufrufaufwand einer Python-Schleife über alle Elemente, rund 80 µs je Stück.

Drei Befunde und was sie brachten (gemessen am Drehlager, u = 0, ein
Schritt):

| Stand | Zeit je Schritt |
|---|---|
| Schleife, wie zuvor | 51,5 s |
| `stress_tet4` holt B direkt statt über `k_tet4` | 38,5 s |
| dazu D-Matrix je Werkstoff statt je Element, Mittelwert ohne `numpy.mean` | 24,7 s |
| dazu blockweise über den ganzen Stapel | **0,54 s** |

Zum ersten Punkt: die Spannung im Schwerpunkt ist σ = D·B·u_e, dafür braucht
es B, nicht die 12×12-Steifigkeitsmatrix V·BᵀDB. Diese wurde gebaut und
sofort weggeworfen — 24,9 s von 39,4 s eines Schritts (cProfile). Zum
zweiten: die Werkstoffmatrix hängt nur an E und ν, wurde aber 1 940 118 mal
je Schritt erzeugt.

Blockweise heißt: die Formfunktionsableitungen am Auswertepunkt sind für
jeden Elementtyp **eine feste Matrix**, also wird die Jacobi-Matrix als ein
`solve` über ein (n, 3, 3)-Feld behandelt; Dehnungen und Spannungen mit
`einsum`, die Rückführung einschließlich der Fallunterscheidung „fließt /
fließt nicht“ als Maske, die plastischen Knotenlasten als ein Streuzugriff.
Die Geometriedaten des Stapels (Ableitungen, Integrationsgewichte,
Freiheitsgrade, Werkstoffwerte) hängen nicht an der Verschiebung und werden
über die Schritte einer Rechnung wiederverwendet; darum kostet der erste
Schritt 3,3 s und jeder weitere 0,54 s.

**Das gilt für jeden Volumenelementtyp**, nicht nur für Tetraeder: Die
Plastizität wertet je Element genau einen Punkt aus (die Mitte), und dort ist
die Ableitungsmatrix des Typs fest. Nur die plastischen Knotenlasten
integrieren über alle Gaußpunkte — bei hex8 acht statt einem —, und das ist
eine kurze Schleife über die Punkte, jede Runde über den ganzen Stapel. Ein
gemischtes Netz wird Typ für Typ gerechnet und zusammengelegt.

Die Schleife bleibt als `_schritt_schleife` erhalten: sie ist die Referenz
des Vergleichstests und rechnet Elementtypen, die `elements.solid` nicht
kennt. Beide Wege liefern dasselbe — an 20 000 fließenden Elementen des
Drehlagers wich F_p relativ um 9,2·10⁻¹⁵ ab, die plastischen Dehnungen um
3,3·10⁻¹⁶; über alle sieben Typen (tet4, tet10, hex8, hex20, pent6, pent15,
pyr5, je acht verzerrte Elemente) bleibt die Abweichung unter 1,6·10⁻¹⁵, also
Maschinengenauigkeit. Ein Unterschied fiel dabei auf und wurde angeglichen:
die größte Vergleichsspannung zählt nur Werkstoffe mit Streckgrenze, weil die
Schleife die übrigen ganz überspringt.

Für 422 Lastfälle hochgerechnet: ein warmer Lastfall braucht 19
Plastizitätsschritte, vorher rund 980 s, jetzt rund 13 s. Mit den 263 s der
Kontakt-Iteration sinkt er von etwa 1 082 s auf etwa 276 s — aus 5,2 Tagen
werden 1,35. Damit kehrt sich das Verhältnis um: die Plastizität macht noch
5 % der Zeit eines Lastfalls, der Gleichungslöser und die Kontakt-Iteration
die übrigen 95 %.

**Folgen für die Rechnung.** Mit Fließen gilt keine Superposition:
Kombinationen werden direkt gerechnet wie bei Kontakt (`_nichtlinear`),
die Grundlast wirkt mit. Der Spannungsnachlauf zieht D·ε_p ab
(`temp["sigma0"]`, derselbe Weg wie die Vorspannung), die Ergebnisse
zeigen also die wahren Spannungen, nicht E·ε. Die Plastizität ist je
Lastfall monoton: kein Entlasten, keine Übertragung von ε_p zwischen
Lastfällen oder Ermüdungszuständen. Ein Punkt je Element (die Mitte)
genügt für linear-tetraedrische und trilinear-hexaedrische Netze; feiner
aufgelöstes Fließen braucht ein feineres Netz, nicht mehr
Auswertepunkte. Große Verformungen (Theorie II. Ordnung der Volumen)
bleiben außen vor.

### 5e.1 Plastizität am Gaußpunkt, und die Moden des Sechsflächners (20.09.2026)

Bis zum 20.09.2026 wertete die Plastizität **in der Elementmitte** aus — ein
plastischer Zustand je Element. Beim `tet4` ist das exakt: er hat einen
Gaußpunkt, seine Dehnung ist konstant, und der Auswertepunkt (0,25/0,25/0,25)
*ist* dieser Gaußpunkt. Beim Sechsflächner war es falsch, und zwar doppelt:

* Bei reiner Biegung ist die Spannung in der Elementmitte **null**.
* Der Gradient der inkompatiblen Moden ist `diag(−2r, −2s, −2t)` und
  verschwindet bei r = s = t = 0 ebenfalls. Die Mitte ist genau der eine
  Punkt, an dem der `hex8` seine Biegung nicht zeigt.

**Gemessen** (Kragträger 200 × 200 mm, Endmoment 1,20 · M_el, fy = 235 N/mm²,
die Randfaser trägt elastisch 282 N/mm² und *muss* fließen):

| Lagen über die Höhe | 1 | 2 | 4 | 8 |
|---|---|---|---|---|
| fließende Elemente, Stand bis 20.09. | 0 | 0 | **0** | 8 von 40 |
| fließende Elemente, heute | 0 | 0 | **8 von 20** | 16 von 40 |

Mit vier Lagen meldete das Programm **kein** fließendes Element unter einem
Moment, das den Querschnitt plastifiziert. Die Durchbiegung stimmte dabei: das
Element *trug* richtig, es berichtete nur nicht.

**Der plastische Zustand steht deshalb jetzt je Gaußpunkt** (`Zustand.eps_p`
ist ein Feld (P, 6), `eps_p_eq` eines (P,)). Am `tet4` ändert das nichts — ein
Punkt, derselbe Ort —, und das Drehlager mit seinen 645 934 Tetraedern rechnet
unverändert.

**Die inkompatiblen Moden mussten mit.** Der `hex8` trägt seine Biegung über
drei Wilson-Moden, die in der Elementmatrix kondensiert werden. Rechnet die
Plastizität ohne sie, passen plastische Lasten und Steifigkeit nicht zusammen:
die Lasten regen Biegemoden an, in denen die kondensierte Steifigkeit viel
weicher ist. Gemessen an demselben Kragträger mit acht Lagen: **ε_p,eq 25,1 %
statt 0,42 %**, und am Reibblock lief die Iteration auf 10¹⁵ % davon. Die
Formulierung lautet darum

    ε(Gaußpunkt) = B u + B_α α
    K_αα α       = h_p − K_uαᵀ u,     h_p = Σ w |J| B_αᵀ D ε_p
    F_p          = Σ w |J| Bᵀ D ε_p − K_uα K_αα⁻¹ h_p

— dieselbe Kondensation, die `elements.solid.hex8_matrices` für die
Steifigkeit macht, jetzt auch für die plastische Last. **α und ε_p hängen
voneinander ab und werden im Element gemeinsam gelöst** (Newton über
R(α) = Σ w B_αᵀ σ = 0, drei bis vier Runden; `EAS_RUNDEN = 8` ist die
Sicherung). Gestaffelt — α aus dem vorigen ε_p — lief der Reibblock davon.

**Die Tangente wird ebenso kondensiert:**

    ΔK = (K_uu + ΔK_uu) − (K_uα + ΔK_uα)(K_αα + ΔK_αα)⁻¹(K_uα + ΔK_uα)ᵀ
         − [K_uu − K_uα K_αα⁻¹ K_uαᵀ]

Ohne den kondensierten Anteil lief der Newton auf 10⁵⁰ davon. Achtung bei
`tangenten_differenz`: sie ist bei Δγ = 0 **nicht** null (der Term θ̄ bleibt
stehen), die nicht fließenden Punkte müssen ausdrücklich gelöscht werden.

**Ergebnis** (derselbe Kragträger, beide Verfahren):

| | Newton-Schritte | fließend | ε_p,eq max |
|---|---|---|---|
| 4 Lagen, konsistente Tangente | 8 | 8 von 20 | 0,180 % |
| 4 Lagen, Anfangsdehnung | 21 | 8 von 20 | 0,175 % |
| 8 Lagen, konsistente Tangente | 13 | 16 von 40 | 0,420 % |
| 8 Lagen, Anfangsdehnung | 40 | 16 von 40 | 0,390 % |

Zwei voneinander unabhängige Verfahren finden dieselben Elemente und
dieselbe Dehnung. Die plastische Zone reicht rechnerisch bis
z/(h/2) = √(3 − 2·1,20) = 0,775; der äußerste Gaußpunkt der vierten Lage liegt
bei 89,4 %, der der dritten bei 60,6 % — es fließt genau die äußere Lage.

**Eine Lage über die Höhe sah es mit 2 × 2 × 2 Gaußpunkten nicht:** der
äußerste Gaußpunkt liegt bei 57,7 % der halben Höhe und trägt
0,577 · 282 = 163 N/mm², also unter fy. Bis zum 22.09.2026 hieß das: mehrere
Elemente über die Dicke, im Sweep mindestens vier Lagen (`LAGEN_MIN_PLASTISCH`).

**Seit dem 22.09.2026 rechnet der `hex8` mit Fließen Gauss-Lobatto-Punkte über
die Dicke** (Richtung t, im Sweep die Lagenrichtung; `Plastizitaet.dicke_punkte`,
Vorgabe 5, 2 = alte Regel). Lobatto legt die äußersten Punkte **auf** die
Oberfläche — dort, wo die Randfaser fließt und wo der Nachweis sie braucht. In
r und s bleiben es zwei Gaußpunkte. Für ein Parallelepiped ist die elastische
Steifigkeit mit jeder Regel ab zwei Punkten dieselbe (die Integranden sind in t
höchstens quadratisch); Steifigkeit, Spannung und Plastizität nehmen dieselbe
Regel aus dem Dehnungsoperator (`solid.hex8_regel_fuer`), auch der Einzelweg in
`assemble.element_matrix`.

Gemessen gegen die Momenten-Krümmungs-Beziehung des Rechteckquerschnitts
(bilinear, E_t/E = 2 %; Randfaser 236,35 N/mm², ε_p = 0,0315 %), am
Integrationspunkt der obersten Lage bei x ≈ L/2, Abweichung σ_v in N/mm² und
ε_p,eq in Prozent des Sollwerts:

| Lagen | 2 × 2 × 2 Gauß | 2 × 2 × 4 Gauß | Lobatto 3 | Lobatto 4 | **Lobatto 5** |
|---|---|---|---|---|---|
| 1 | −74,2 (fließt nicht) | −0,79 (−59 %)¹ | +45,1 (+3342 %) | +0,25 (+18 %) | **−0,20 (−15 %)** |
| 2 | −17,2 (fließt nicht) | −0,49 (−37 %)¹ | +0,29 (+21 %) | −0,27 (−20 %) | **−0,20 (−15 %)** |
| 4 | −0,57 (−42 %)¹ | −0,21 (−15 %)¹ | −0,16 (−12 %) | +0,03 (+2 %) | **−0,07 (−5 %)** |

¹ unter der Oberfläche (86 bzw. 93 % der halben Höhe), nicht an der Faser.

Drei Lobatto-Punkte reichen bei einer Lage nicht: die Regel kennt nur Rand und
Mitte, die Mitte trägt kein Moment, und das ganze plastische Moment landet auf der
Randfaser (+45 N/mm², ε_p 35-fach). Mit fünf trifft schon **eine** Lage die
Randfaser auf 1 N/mm². ε_p,eq liegt dann um 15 % zu niedrig — der Knick zwischen
elastischem Kern und Fließzone fällt zwischen zwei Punkte; mit vier Lagen sind es
5 %. Der Preis: 20 statt 8 Punkte je Element in jedem Fließschritt; gespart werden
dafür Lagen (vier auf eine bis zwei). Ob `LAGEN_MIN_PLASTISCH` im Sweep dafür sinken
kann, entscheidet der Vernetzer mit einer eigenen Messung.

Nachweis `tests/test_plastizitaet.py::test_sechsflaechner_fliesst_unter_biegung`,
`::test_plastische_randfaser_mit_wenigen_lagen` und
`::test_tet4_wertet_in_seinem_gausspunkt_aus`.

**Was `res.solid_res` zeigt, ist der maßgebende Auswertepunkt** (§ 5d). Die
Anfangsspannung D·ε_p wird dafür über die Gaußpunkte gemittelt — beim `tet4`
derselbe Wert wie zuvor, weil er nur einen hat. Zu beachten: die
Fließbedingung gilt an den **Gaußpunkten**, die Auswertepunkte sind andere
(Mitte und Ecken). Die angezeigte Vergleichsspannung darf darum über fy
liegen, ohne dass etwas falsch ist — sie muss unter der verfestigten
Fließgrenze fy + H·ε_p des am stärksten gedehnten Punktes bleiben. Am
Reibblock: 1,00 gegen die Grenze 1,36 N/mm² bei fy = 0,60.

### 5e.2 Grenzlast mit exaktem Sollwert: das Rohr nach Hill (23.09.2026)

Abnahme 4.3 des Auftrags an die Element-Sitzung: dickwandiges Rohr a = 0,1 m,
b = 0,2 m unter Innendruck, ebene Dehnung, ideal plastisch (von Mises,
fy = 355 N/mm², keine Verfestigung), ν = 0,4999. Für inkompressiblen Werkstoff
ist Hills Lösung exakt (k = fy/√3, plastische Zone a ≤ r ≤ c):

    p(c) = k (2 ln(c/a) + 1 − c²/b²),   Grenzlast p_L = 2 k ln(b/a) = 284,13 N/mm²
    u_r = k c²/(2G r) überall;  plastisch σ_m = −p + 2k ln(r/a) + k,
    ε_p,eq = fy/(3G)·(c²/r² − 1);  elastisch σ_v = fy c²/r²

Gerechnet bei c/a = 1,5 (p = 255,88 N/mm², σ_v an der Außenfläche 199,69 N/mm²).
Gemeldet u_r und σ_v an der Außenfläche (geglättete Knotenspannung), und am
Integrationspunkt, der der Innenfläche am nächsten liegt, σ_m und ε_p,eq gegen
den Sollwert **an seinem Radius** (das misst das Element, nicht die
Extrapolation). `tests/messung_rohr_plastisch.py`, gemessen 23.09.2026, Ablage
`messungen/rohr_hill_2026-09-23.log`:

| Netz | FHG | u_r(b) | σ_v(b) N/mm² | σ_m am Punkt N/mm² | ε_p,eq am Punkt |
|---|---|---|---|---|---|
| hex8 8 × 4 | 270 | 0,9846 | −6,03 | +31,0 | −2,7 % |
| hex8 16 × 8 | 918 | 0,9962 | −1,63 | +15,2 | −0,6 % |
| hex8 32 × 16 | 3 366 | 0,9991 | −0,42 | +7,5 | −0,1 % |
| tet10 8 × 4 | 1 377 | 0,9967 | +0,56 | −19,6 | +14,6 % |
| tet10 16 × 8 | 5 049 | 0,9992 | −0,14 | −4,7 | +9,8 % |
| tet4 8 × 4 | 270 | 1,1726 | +46,6 | +306 | +154 % |
| tet4 16 × 8 | 918 | 1,1995 | +46,8 | +367 | +434 % |

σ_v am Punkt ist bei allen Typen fy (die Rückführung), darum steht er nicht in
der Tabelle. Die **Grenzlast** (mit dem Newton bestimmt, siehe unten): hex8 und
tet10 8 × 4 tragen 0,995 p_L und 1,005 p_L nicht — auf 0,5 % getroffen; tet4
8 × 4 trägt noch 1,005 p_L, 1,03 nicht.

* hex8 und tet10 treffen σ_v an der elastischen Außenfläche auf 1 N/mm² (hex8 ab
  3 366, tet10 ab 1 377 FHG). σ_m konvergiert beim hex8 mit h (die Volumendehnung
  ist linear projiziert, § 4.4), beim tet10 schneller; ε_p,eq am innersten Punkt
  liegt beim tet10 10 bis 15 % zu hoch — die schwache Volumensperre aus § 6b-2.
* **tet4 bei ν → 0,5 fließt falsch:** in der plastischen Zone fließen nur 144 von
  384 Elementen (16 × 8), dafür 48 außerhalb; u_r liegt 20 % zu hoch und wird
  mit dem Netz nicht besser. Bei ν = 0,3 fließen 372 von 384, und u_r konvergiert
  von unten (1,905 → 1,966 → 1,992 gegen 2,002 · 10⁻⁴ m des hex8 32 × 16).
  Gemessen und benannt, nicht behoben: der tet4 steht nicht an den
  Nachweisstellen (§ 6b-2).

**Zwei stille Fehler der Anfangsdehnungs-Iteration, am Rohr gefunden.** Ohne
Verfestigung rechnet das Programm die Anfangsdehnung (§ 5e). Sie meldete
„konvergiert“ und lag daneben:

1. Der Zustand wurde von Schritt zu Schritt fortgeschrieben. Mit der
   Aitken-Überrelaxation (bis ω = 200) sammelte sich plastische Dehnung entlang
   des Iterationswegs an, und der Fixpunkt war nicht die Lösung: tet10 8 × 4 bei
   c/a = 1,5 u_r(b) 0,99933 bei Toleranz 10⁻⁶ statt 0,99863 wie der Newton. Seit
   dem 23.09.2026 geht jede Rückführung vom Zustand am Anfang der Laststufe aus;
   beide Wege liegen jetzt 2·10⁻⁶ auseinander.
2. Abgebrochen wurde an der Änderung. Nahe der Grenzlast zieht sich die Folge
   mit ρ → 1 zusammen, und der Fehler ist ρ/(1 − ρ) mal die Änderung. Seitdem
   bricht sie am geschätzten Fehler ab; ρ ist der größere Wert aus dem größten
   Verhältnis aufeinanderfolgender Änderungen der letzten drei Schritte und der
   mittleren Rate über bis zu acht Schritte (Aitken-Sprünge machen kurze steile
   Abfälle, unter denen die Folge mit rund 0,93 je Schritt weiterkriecht). Das
   Aitken-ω selbst taugt als Schätzer nicht: nach einem Sprung ergab es
   λ = 0,04 in einer Folge, die sichtlich stand.

Größte Abweichung von σ_v an den Knoten gegen den Newton in N/mm², Toleranz 10⁻³,
vorher → jetzt (Schritte):

| | c/a = 1,5 | 0,97 p_L |
|---|---|---|
| hex8 8 × 4 | 0,002 → 0,002 (9 → 9) | 0,39 → 0,00 (15 → 18) |
| tet10 8 × 4 | 0,35 → 0,09 (14 → 19) | 3,86 → 0,44 (26 → 55) |
| hex8 32 × 16 | 0,25 → 0,09 (11 → 13) | 0,67 → 0,00 (22 → 24) |
| tet10 16 × 8 | 0,25 → 0,02 (16 → 26) | 1,97 → 0,03 (26 → 67; nur mit den drei Verhältnissen 0,68) |

Der Preis sind mehr Schritte, weil die Folge jetzt am richtigen Punkt anhält.
Nahe der Grenzlast vergrößert die fast singuläre Tangente jeden Rest in F_p —
dort braucht der Newton 9 bis 13 Schritte. Ob er auch ohne Verfestigung der
schnellere Weg ist, entscheidet am Drehlager die Zeit, nicht die Schrittzahl
(hergeleitet mit den Zahlen der Löser-Sitzung — Zerlegung 3,41 s,
Rücksubstitution 0,32 s, `schritt()` 0,98 s —: beim tet10 spräche es für den
Newton, beim hex8 für die Anfangsdehnung); mit Kontakt ist jeder
Anfangsdehnungsschritt eine volle Kontakt-Iteration. Entschieden wird das mit
dem Umbau der verschachtelten Iteration Plastizität × Kontakt, nicht hier.
Nachweis `tests/test_plastizitaet.py::test_rohr_ideal_plastisch_nach_hill` und
`::test_anfangsdehnung_trifft_den_newton`.

**Laststufe halbieren (28.09.2026, `plastizitaet.HALBIEREN_MAX`).** Läuft
der Newton einer Laststufe weg - die Änderung wächst zweimal hintereinander,
nachdem sie einmal gefallen war - oder endet einer ihrer Kontaktläufe nicht
konvergiert, wird die Stufe vom Startwert an in zwei halben wiederholt
(Lösung, Fließzustand und Kontaktzustand vom Stufenanfang; die Läufe des
verworfenen Versuchs stehen im Laufbuch als verworfen), höchstens viermal je
ursprünglicher Stufe. Am gequetschten Block mit Reibung primal-dual lief mit
vier Laststufen Stufe 3 weg (Änderung 1,6 - 1,8 - 4,4 - 7,2 ... 26, nach 40
Schritten „nicht konvergiert“), mit einer und mit acht nicht - ob eine
Rechnung konvergierte, hing an der Teilung der Last. Mit dem Halbieren (vier
Stufen: zweimal) geben 1, 2, 4 und 8 Laststufen denselben Zustand (u_max
42,667 mm, ε_p 12,99 %) mit 263 Zerlegungen, davon 161 in verworfenen
Versuchen; ohne das sofortige Halbieren nach einem gescheiterten Kontaktlauf
waren es 752, davon 650 verworfen (jeder solche Lauf 69 Runden bis zur Grenze
der Richtungsrunden). In der gemeinsamen Iteration (5e.3) wird eine Stufe,
in der nach abgekürzten Läufen ein voller Kontaktlauf am Deckel endet,
verschachtelt wiederholt.

### 5e.3 Fließen und Kontakt gemeinsam iteriert (23./24.09.2026)

**Stand 24.09.2026: wählbar, nicht die Vorgabe.** Vorgabe ist wieder
`Plastizitaet.kontakt = "verschachtelt"`; die gemeinsame Iteration wählt man
unter *Berechnung → Einstellungen*, „mit Kontakt“. Grund (Gegenprüfung vom
24.09.2026, Messung unten): an Reibung nahe der Grenzlast endet sie in einem
anderen Zustand als die verschachtelte — bis 78 N/mm² Unterschied der
Vergleichsspannung, beide „konvergiert“ —, und dort ist sie auch teurer. Das
Ziel des Anwenders, höchstens 1 N/mm² gegen die verschachtelte Iteration,
hält sie an diesen Modellen nicht. Ob sie Vorgabe wird, entscheidet der
Anwender, frühestens nach einer Messung am Drehlager. Ein unbekannter Wert
der Einstellung rechnet verschachtelt und steht im Protokoll der
Plastizität (`solver._kontakt_weg_melden`).

**Das Problem.** Bis hierher war jede Lösung der Fließ-Iteration eine volle
Kontakt-Iteration: der Newton ruft `loesen`, der Löser iteriert den Kontakt
aus (warm vom letzten Zustand), erst dann kommt der nächste Newton-Schritt.
Vor dem ersten plastischen Lauf stand zudem ein elastischer Vorlauf bei voller
Last, dessen Zustand nie weiterging (§ 4.0b). Am Drehlager, LF1 (cProfile der
Löser-Sitzung, 23.09.2026, Stand 54b6f9a, ruhige Maschine): 965 s, zwölf
Kontaktläufe mit 144 Schritten und **139 Zerlegungen** zu 3,41 s (474,6 s,
49 %) für zehn Newton-Schritte; Vorlauf und Laststufe 1 kalt, der erste
Newton-Lauf nach 40 Zustandswechseln gedeckelt.

**Das Verfahren** (`Plastizitaet.kontakt = "gemeinsam"`;
`plastizitaet._stufe_gemeinsam`, die Regeln in `solver._KontaktImNewton`):

1. Kein elastischer Vorlauf. Was er nebenbei tat — freie Bewegungen finden
   und festhalten — geschieht um den ersten plastischen Lauf. Das gilt auch,
   wenn die Fließ-Iteration mit Anfangsdehnung rechnet (gewählt, ohne
   Verfestigung, Elementtyp ohne Stapel); abgekürzt wird dort nichts, das
   Ergebnis bleibt bitgleich (Block mit Reibung ohne Verfestigung: 9 statt 16
   Zerlegungen, mit Anfangsdehnung und 5 %: Laufbuch ohne den Vorlauf,
   `test_laufbuch_mit_fliessen`).
2. Der Startwert jeder Laststufe (elastisch mit dem bisherigen F_p) wie
   bisher mit **voll auskonvergiertem** Kontakt.
3. Die Newton-Schritte der Stufe mit **abgekürztem** Kontakt: ein
   Kontaktschritt, der Zustand geht an die nächste Lösung weiter
   (`solve_with_contact(kurz=1)`). Gleitende Knoten gegen ihre Richtung
   werden dort auf Haften zurückgesetzt statt neu zu starten; der Lauf gilt
   dann als abgekürzt. Abgekürzt wird höchstens zwölfmal je Stufe
   (`KURZ_MAX`, unabhängig von `iterationen`) und nur, solange die Änderung
   nicht zweimal hintereinander wächst, nachdem sie einmal gefallen war.
4. Eine Stufe endet erst, wenn die Änderung unter der Toleranz liegt **und**
   die Lösung dazu nicht abgekürzt war. Sonst folgt ein Newton-Schritt mit
   vollem Kontakt („Abnahme“), in der letzten Stufe statt dessen der
   **Abschluss** (voller Kontakt, elastisch mit F + F_p), und die Prüfung an
   seiner Lösung. Die Abnahme zählt **nicht** gegen die Schritte je Stufe:
   bis zum 24.09.2026 verbrauchte sie einen, und eine Stufe, die im letzten
   erlaubten Schritt die Toleranz traf, hieß „Plastizität: Laststufe 2 nach
   1 Newton-Schritten nicht konvergiert (Änderung 0.00e+00 > 0.0001)“ — mit
   einem zweiten Abschluss auf demselben F_p (Block mit Reibung, nichts
   fließt, ein Schritt je Stufe; verschachtelt „konvergiert“). Ein
   abgekürzter Lauf, der in seinem einen Schritt auskonvergiert ist, ist
   genau der volle Lauf und zählt als solcher.
5. Verfehlt die Abnahme die Toleranz um mehr als das Zehnfache
   (`ABNAHME_WEITER`), hat der volle Kontakt den Zustand merklich verschoben:
   die Stufe wird wiederholt (6.). Sonst, und nach zwölf abgekürzten
   Schritten, rechnet die Stufe mit vollem Kontakt weiter, solange die
   Änderung von Schritt zu Schritt fällt; fällt sie nicht, oder ist das
   Budget aufgebraucht, wird wiederholt.
6. **Wiederholen** heißt: die Stufe vom Startwert an **verschachtelt** —
   Kontaktzustand nach dem Startwert, F_p und Basis vom Stufenanfang, das
   volle Budget, Schritt für Schritt wie in der Vorgabe. Die Läufe des
   Versuchs heißen im Laufbuch `verworfen` und zählen nicht als nicht
   konvergiert. Wiederholt wird nur, wenn in der Stufe etwas abgekürzt war;
   sonst war der Versuch der verschachtelte Newton selbst.

**Der Bezug der Änderung (25.09.2026).** Die „Änderung“ eines Schritts ist ‖F_p,neu − F_p‖
geteilt durch die äußere Last ‖F‖. Fehlt die äußere Last ganz — ein Übermaß, eine Vorspannung
oder eine Lagerverschiebung als einzige Last, F = 0 —, war der Bezug bis zum 25.09.2026 die
Zahl 1, und die Änderung stand als absolute Zahl in Newton gegen die Toleranz. Die Presspassung
der Prüfmatrix (zwei Würfel, Übermaß bis 300 N/mm²) rechnete exakt und meldete nach 3 × 60
Newton-Schritten trotzdem „nicht konvergiert“: letzte Änderung 0,0972 N gegen Knotenkräfte
von 10⁸ N. Ohne äußere Last ist der Bezug jetzt die plastische Last ‖F_p,neu‖ selbst
(`plastizitaet._bezug`); gibt es auch die nicht, fließt nichts, und jede Änderung ist 0. Mit
äußerer Last ändert sich nichts — der Bezug bleibt ‖F‖, alle Zahlen dieses Kapitels gelten
unverändert. Gemessen am selben Modell: konvergiert in 5 Schritten (drei Stufen) bzw. 3 (eine
Stufe), Rest im Abschluss 4 · 10⁻¹³, σ_zz −296,75 N/mm² bilinear exakt; mit Bezug 1 nach 29
Schritten „nicht konvergiert“ bei demselben Ergebnis. Prüfung
`test_plastizitaet.test_uebermass_als_einzige_last`, Schalter `BEZUG_PLASTISCHE_LAST` für die
Rücknahmeprobe.

Warum der Rückfall die Stufe **wiederholt**, statt vom erreichten Stand mit
vollem Kontakt weiterzurechnen: so rechnete die Fassung vom 23.09.2026 nach
der Hälfte der Schritte weiter — und kam vom weggelaufenen Stand nicht mehr
zurück. Am Block nahe der Grenzlast (unten) 197 statt 61 Zerlegungen, am
gequetschten Block mit vier Laststufen 327 statt 84, beide „nicht
konvergiert“, wo verschachtelt konvergiert; mit Wiederholung 67 und 101,
beide „konvergiert“ und bitgleich mit verschachtelt. Beginnt die
Wiederholung am selben Zustand wie die verschachtelte Rechnung — in der
ersten Laststufe immer —, rechnet sie deren Zahlen; die Mehrkosten sind die
Zerlegungen der verworfenen Läufe (Test
`test_gemeinsam_rueckfall_verschachtelt`). Warum das Zehnfache: am
gequetschten Block mit drei Laststufen verfehlte die Abnahme die Toleranz
10⁻⁴ mit 3,2·10⁻³, und das Weiterrechnen endete in einem anderen Zustand
(27,8 N/mm² neben verschachtelt, „nicht konvergiert“); am abhebenden Block
3,5·10⁻³ bei 10⁻³, und es endete 0,001 N/mm² neben verschachtelt.
**Untersucht, nicht übernommen:** eine lockerere Regel (Weglaufen erst ab
10 % der größten Änderung der Stufe, danach höchstens acht volle Schritte)
spart mehr — 3978 statt 4543 von 5645 Zerlegungen in beiden Stichproben
unten —, aber 9 statt 5 Rechnungen lagen über 1 N/mm², und zweimal statt
einmal war das Urteil schlechter als verschachtelt.

„Konvergiert“ gibt es damit nur, wenn der letzte Schritt mit voll
auskonvergiertem Kontakt gerechnet ist und Plastizität und Kontakt dort ihre
Kriterien erfüllen. Abgekürzte und verworfene Läufe stehen im Laufbuch
(Grund `abgekuerzt`, Feld `verworfen`), kleben aber nicht an
`contact_converged` und zählen nicht unter
`contact_laeufe_nicht_konvergiert`; gedeckelte oder an der Schrittgrenze
beendete Läufe, die zählen, zählen wie bisher, auch unterwegs.

**Absprache mit der Element-Sitzung.** Verabredet war: in `plastizitaet.py`
nur eine Schnittstelle und die Abnahme, die Schleife im Löser. Die Schleife
einer gemeinsamen Laststufe (`_stufe_gemeinsam`) steht trotzdem in
`plastizitaet.py`, weil sie die Newton-Fortschreibung
(K + ΔK) u = F_k + F_p + ΔK u mit der Rückführung von der Basis der Stufe
ist; im Löser wäre sie ein zweiter Newton. **Wann** abgekürzt und wann
wiederholt wird, steht im Löser (`_KontaktImNewton.naechster`). Die
verschachtelte Schleife ist die vom Stand 6a961e5 (nur `loesen` →
`_loesen`, fürs Laufbuch), die drei geschützten Stellen sind unverändert
(Textblöcke gleich, sha256), und ohne Kontakt rechnet `_newton` Aufruf für
Aufruf wie vorher.

**Die Schlussabnahme gilt in beiden Verfahren** — wenn der Lösungsweg selbst
iteriert (Kontakt, ausfallende Zugstäbe). Verschachtelt löste der Abschluss
elastisch mit dem F_p des letzten Newton-Schritts, in einem eigenen vollen
Kontaktlauf — der den Kontaktzustand noch ändern kann, oft als kalter
Neustart („Warmstart verworfen … Neustart von der Geometrie“) —, und niemand
prüfte, ob F_p zu dieser Verschiebung passt. Am gequetschten Block
(`tests/test_solver_ext`, µ 0,3, 60 MN auf 0,4 × 0,4 m, ε_p 12 %) blieb ein
Rest von 2,5·10⁻⁴ bei Toleranz 10⁻⁴, gemeldet wurde „konvergiert“; jetzt
heißt das „nicht konvergiert“, in beiden Verfahren (die Zahlen bleiben
bitgleich). Nachweis
`tests/test_plastizitaet.py::test_gemeinsame_iteration_kein_falsches_konvergiert`
(c) und die Rücknahmeprobe `::test_ruecknahme_der_schlussabnahme`: ohne die
Prüfung meldet derselbe Block wieder „konvergiert“. Das ist nicht der einzige
Fall: in den 74 Rechnungen der beiden Stichproben unten (69 mit Kontakt,
5 ohne) wechselt das Urteil der verschachtelten Rechnung gegen 6a961e5 in
fünf von „konvergiert“ zu „nicht konvergiert“ — der gequetschte Block mit 1
und 2 Laststufen (Rest 2,5·10⁻⁴ > 10⁻⁴) und der kippende Stempel mit 1, 3
und 5 (1,06·10⁻³ bis 1,21·10⁻³ > 10⁻³). Geprüft wird einmal: besteht die
Schlussabnahme nicht, heißt es „nicht konvergiert“, weitergerechnet wird
nicht. (Die Fassung vom 23.09.2026 rechnete gemeinsam weiter; am kippenden
Stempel blieb der Rest dabei stehen, weil jeder volle Abschluss kalt im
selben Zustand endete — dasselbe Urteil mit 171 statt 93 Zerlegungen.) Ohne
Kontakt und Ausfall wird sie nicht gerechnet: dort ist der Abschluss die
Newton-Lösung selbst, der Rest lag in 14 Fällen höchstens bei 1,5·10⁻⁷, und
die Zahl der Rückführungen ist wieder die von 6a961e5 (Zugwürfel 4,
Kragträger 8; `test_gemeinsam_aendert_nichts_ohne_beides`).

**Auch im Weg Anfangsdehnung** (25.09.2026, ideal plastisch immer dieser Weg): mit
Kontakt rechnet sie dieselbe Schlussabnahme. Dort ist das falsche „konvergiert“
seltener — jeder ihrer Schritte löst genau so wie der Abschluss (elastisch, voller
Kontakt), und ihr Abbruch am geschätzten Fehler hält die nächste Änderung unter der
Toleranz; gemessen lag der Rest an allen „konvergiert“ bei höchstens 6,1·10⁻⁶ gegen
10⁻⁴ (gequetschter Block mit Anfangsdehnung, ideal plastischer Block mit Reibung
unter der Grenzlast). Ein Umspringen des Kontakts genau im Abschluss ist aber nicht
ausgeschlossen; ein so gestörter Abschluss (u um 1 % verschoben) heißt jetzt „nicht
konvergiert“, ohne die Prüfung hieße er „konvergiert“
(`tests/test_plastizitaet.py::test_schlussabnahme_anfangsdehnung`).

**Warum der Startwert der Stufe voll auskonvergiert.** Die erste Fassung
(Bau, 23.09.2026) kürzte auch ihn ab (und nahm die letzte Tangente dazu).
Sie sparte mehr (3015 → 1405 Zerlegungen in der Stichprobe des Bauers), lag
aber in neun von 45 Fällen über 1 N/mm²: Block mit Reibung (M1, zwei
Laststufen) 89,6, Stempel mittig (E5) mit einer und zwei Stufen 3,1 und 6,0,
M3 mit einer Stufe 3,3, Klotz M5 mit einer 2,1, K4 mit einer und zwei 1,8,
der gequetschte Block C mit zwei Stufen 26,8, mit drei konvergierte er
nicht. Im Startwert legt die Kontaktiteration Haften, Gleiten und die
Gleitrichtungen fest (Phase 1 führt die Richtungen nach, Phase 2 hält sie
fest und lässt nur Haften → Gleiten zu); rechnet das Fließen schon dort mit,
kommt die Iteration an einem anderen zulässigen Zustand an.

**Warum auch mit vollem Startwert ein anderes Ergebnis möglich ist.** Dieselbe
Ursache wirkt in den abgekürzten Schritten: ein Knoten, der dort ins Gleiten
geht, bekommt seine Richtung aus einer Zwischenlösung und behält sie; die
Prüfung am Ende verwirft sie nur, wenn er **gegen** sie gleitet. Am Block
nahe der Grenzlast (s = 0,8, eine Stufe) endete die Fassung vom 23.09.2026
mit einem gleitenden Knoten, der 89° neben seiner Gleitrichtung glitt
(cos 0,011, verschachtelt kleinster Wert 0,738) — 14,0 N/mm² Unterschied im
Element darüber. Welcher Zustand „richtiger“ ist, entscheidet keine der
beiden Rechnungen: auch die verschachtelte hängt dort am Weg. Mit der
Laststufenzahl ändert sie sich an demselben Block um bis zu 24,6 N/mm² (1
gegen 2, 3, 4, 6, 8 Laststufen: 0,14 / 4,19 / 12,5 / 20,8 / 24,6), mit
s = 0,9 um 13,3 und 24,6 N/mm² (1 gegen 3 und 5 Laststufen), jeweils
„konvergiert“ (Stand 6a961e5); am gequetschten Block um 15 bis 34 N/mm²
(Gegenprüfung). Gleiten gegen die Richtung kommt in beiden Richtungen vor:
am Ende des gequetschten Blocks mit 6 Stufen gemeinsam ein Knoten
(verschachtelt keiner), mit 1 und 2 Stufen verschachtelt einer (gemeinsam
ebenso, die Stufen wurden dort wiederholt), und die Fassung vom 23.09.2026
hatte ihn mit 3 Stufen gemeinsam, verschachtelt nicht.

**Messung** (24.09.2026, einkernig, `OMP_NUM_THREADS=1`, jede Rechnung in
einem eigenen Prozess; alt = `git archive 6a961e5`, neu = Stand 85f1976 mit
beiden Einstellungen; gezählt werden die Aufrufe von `LinearSolver`, nicht
das Laufbuch; Skripte in `%TEMP%\nachb_iter`). Zwei Stichproben.

*Die Stichprobe des Bauers* (23.09.2026): fünfzehn Modelle, jedes mit 1, 2
und 3 Laststufen, 45 Rechnungen:

* A: Block mit Reibung (`examples_lib`), fy = 60 % der elastischen
  Vergleichsspannung, E_t/E 5 %, Toleranz 10⁻⁴ (wie `test_plastizitaet`);
* C: gequetschter Block (oben), 2 %, Toleranz 10⁻⁴;
* sonst fy = 235 N/mm², Last so, dass elastisch σ_v = fy/a, E_t/E 1 %,
  Toleranz 10⁻³, 25 Schritte (die Vorgaben): M1/M3 Block mit Reibung
  (a = 0,3/0,4); M2/M6 Stempel hex8 mit gewölbter Unterseite auf Sockel,
  Fuge µ 0,1 bzw. 0, Last zu 60 % außermittig (a = 0,4/0,3); M4 ebener
  Stempel, µ 0,2 (a = 0,4); E1 wie M2 aus tet4 (das Modell „zwei Körper“ der
  Tests), E2 feiner, E5 hex8 feiner und mittig (a = 0,35), E6 hex8 feiner,
  D1 wie E1 mit 5 % Querlast, der Stempel oben nur quer dazu gehalten;
  M5/K1/K4 Klotz aus tet4 auf einem Lager wie
  „Starr“ am Drehlager (µ 0,1 in der Fläche, Bettung mit Ausfall bei Zug,
  Knagge), 8 × 4 × 4 (a = 0,4), 12 × 6 × 4 (a = 0,4), 16 × 8 × 4 (a = 0,3).

Zerlegungen verschachtelt → gemeinsam, größte Abweichung der
Vergleichsspannung je Element (N/mm²; „bitgleich“: Verschiebungen und
Spannungen gleich), Urteil verschachtelt / gemeinsam und wie viele Stufen
wiederholt wurden, drei Laststufen:

| Modell | Zerlegungen | Anteil | max &#124;Δσ_v&#124; | Urteil | wiederholt |
|---|---|---|---|---|---|
| A | 22 → 15 | 68 % | bitgleich | konv. / konv. | 0 |
| C | 44 → 68 | 155 % | 0,000 | konv. / konv. | 2 |
| M1 | 155 → 169 | 109 % | 0,000 | konv. / konv. | 1 |
| M2 | 121 → 119 | 98 % | 0,000 | konv. / konv. | 1 |
| M3 | 30 → 22 | 73 % | 0,001 | konv. / konv. | 0 |
| M4 | 29 → 22 | 76 % | 0,011 | konv. / konv. | 0 |
| M5 | 27 → 21 | 78 % | 0,000 | konv. / konv. | 0 |
| M6 | 20 → 16 | 80 % | 0,000 | konv. / konv. | 0 |
| E1 | 129 → 78 | 60 % | 0,011 | konv. / konv. | 0 |
| E2 | 141 → 125 | 89 % | 0,000 | konv. / konv. | 1 |
| E5 | 39 → 25 | 64 % | 0,000 | konv. / konv. | 0 |
| E6 | 211 → 199 | 94 % | 0,000 | konv. / konv. | 1 |
| D1 | 137 → 97 | 71 % | 0,000 | konv. / konv. | 1 |
| K1 | 35 → 29 | 83 % | 0,037 | konv. / konv. | 0 |
| K4 | 45 → 32 | 71 % | 0,922 | konv. / konv. | 0 |

Über alle 45 Rechnungen 3015 → 2392 Zerlegungen (79 %; die Fassung vom
23.09.2026 hatte 1741, 58 %). Teurer als verschachtelt sind sieben: M1 mit 2
und 3 Stufen, M2 mit 1 und 2, C mit 1, 2 und 3. Über 1 N/mm² liegen zwei, K4
mit 1 und 2 Stufen (1,58 / 1,37 N/mm²); C, bei der Fassung vom 23.09.2026
noch 27,7 bis 31,1, rechnet jetzt wie verschachtelt, weil seine Stufen
wiederholt werden. Das Urteil ist in allen 45 dasselbe wie verschachtelt.

*Die Gegenprüfung* (24.09.2026): 32 Rechnungen an Modellen, die die
gemeinsame Iteration herausfordern — der gequetschte Block mit 1 bis 8
Laststufen; ein Block 0,4 m aus hex8 4 × 4 × 4 auf einer starren Platte
(µ 0,3) mit Fz = s fy A und 0,2 Fz quer, E_t/E 0,5 %, nahe der Grenzlast
(s = 0,8 und 0,9); derselbe Block unter Querlast 0,25 P, der auf einer Seite
abhebt; ein Stempel tet4 auf Sockel mit µ 0,4 und Querlast 0,3 P, der kippt;
ein Stempel hex8 mit µ 0,15, der gleitet; zwei Lastfälle hintereinander;
dazu der Block mit Reibung, das Modell „zwei Körper“ der Tests und knappe
Schrittzahlen. Auswahl:

| Rechnung | Zerlegungen | Anteil | max &#124;Δσ_v&#124; | Urteil | wiederholt |
|---|---|---|---|---|---|
| C, 4 Stufen | 84 → 101 | 120 % | bitgleich | konv. / konv. | 3 |
| C, 6 Stufen | 115 → 206 | 179 % | 29,45 | konv. / nicht konv. | 4 |
| C, 8 Stufen | 101 → 125 | 124 % | 78,16 | konv. / konv. | 2 |
| Grenzlast s = 0,9, 1 Stufe | 61 → 67 | 110 % | bitgleich | konv. / konv. | 1 |
| … 3 Stufen | 53 → 66 | 125 % | 0,000 | konv. / konv. | 1 |
| … 5 Stufen | 125 → 46 | 37 % | 45,29 | konv. / konv. | 0 |
| Grenzlast s = 0,8, 1 Stufe | 29 → 39 | 134 % | bitgleich | konv. / konv. | 1 |
| abhebender Block, 1 Stufe | 97 → 64 | 66 % | 0,000 | konv. / konv. | 0 |
| kippender Stempel, 1 Stufe | 93 → 108 | 116 % | bitgleich | nicht / nicht | 1 |
| … 5 Stufen | 128 → 155 | 121 % | 0,000 | nicht / nicht | 2 |
| gleitender Stempel, 1 Stufe | 164 → 69 | 42 % | 0,044 | konv. / konv. | 0 |
| … 3 Stufen | 324 → 116 | 36 % | 0,000 | nicht / konv. | 0 |
| zwei Lastfälle | 246 → 208 | 85 % | 0,001 | konv. / konv. | 1 |

Über alle 32: 3101 → 2559 Zerlegungen (83 %); teurer als verschachtelt 15,
über 1 N/mm² drei (C mit 6 und 8 Stufen, Grenzlast s = 0,9 mit 5), das
Urteil einmal schlechter (C mit 6 Stufen: die Schlussabnahme scheitert,
Rest 2,0·10⁻⁴ > 10⁻⁴) und einmal besser (gleitender Stempel, 3 Stufen:
verschachtelt ist ein Lauf gedeckelt). Die Fassung vom 23.09.2026 kam hier
auf 3180 Zerlegungen, lag in 13 Rechnungen über 1 N/mm² (bei den
konvergierten bis 47,3 N/mm²) und meldete in sieben „nicht konvergiert“, wo
verschachtelt konvergiert.
Über beide Stichproben (69 verschiedene Rechnungen) 10 265 → 7 637
Kontaktschritte und 870 → 1 348 Rückführungen.

**Was das für das Drehlager heißt — nicht gemessen.** Die Stichproben zeigen
beides: an den zweikörprigen Modellen mit Fuge µ 0,1 (E1, E2, E6, D1, je 1
bis 3 Laststufen) 26 bis 99 % der Zerlegungen bei höchstens 0,053 N/mm²
Unterschied, an Reibung nahe der Grenzlast Mehrkosten bis 79 % und
Abweichungen bis 78 N/mm². Welches
Bild LF1 zeigt, sagt erst eine Messung dort; die Herleitung der Fassung vom
23.09.2026 (139 → 80 bis 110 Zerlegungen) galt für eine Fassung ohne
Wiederholung und wird hier nicht fortgeschrieben.

**Unverändert.** Verschachtelt (die Vorgabe) rechnet bitgleich wie 6a961e5:
in allen 74 Rechnungen beider Stichproben (69 mit Kontakt, 5 ohne)
dieselben Verschiebungen, Auflager- und Kontaktkräfte, Spannungen und
dieselbe Zahl Zerlegungen; mit Kontakt eine Rückführung mehr je Lastfall
(die Schlussabnahme), ohne Kontakt dieselbe Zahl. Ebenso Kontakt ohne
Fließen und Fließen ohne Kontakt in beiden Einstellungen (Block mit Reibung,
Stempel auf Sockel, Zugwürfel hex8, Kragträger tet4 mit 48 fließenden
Elementen; die Werte von 6a961e5 fest im Test).
Nachweise in `tests/test_plastizitaet.py`: `test_gemeinsame_iteration_spart_zerlegungen`
(A 20 → 13, E1 129 → 78), `…_rechnet_dasselbe` (A 0,0000, E1 0,011 N/mm²),
`…_kein_falsches_konvergiert`, `test_ruecknahme_der_schlussabnahme`,
`test_gemeinsam_aendert_nichts_ohne_beides`, `test_gemeinsam_im_budget`,
`test_gemeinsam_rueckfall_verschachtelt`, `test_hilfsfesselung_ohne_vorlauf`,
`test_vorgabe_verschachtelt_und_unbekannter_wert`.

**Offen, vorbestehend und nicht Teil dieses Umbaus:** kalte Kontaktläufe
werden am Ende nicht darauf geprüft, ob gleitende Knoten gegen ihre
festgehaltene Richtung gleiten — nur warme (`warmstart_verstoesse`). Der
Abschluss endet oft kalt, und dann steht „konvergiert“ an einem Zustand mit
solchen Knoten, in beiden Einstellungen gleich: am Ende des abhebenden
Blocks sechs, des kippenden Stempels fünf, des gleitenden Stempels vier, des
Modells „zwei Körper“ zwei (`zustand_verstoesse` am End-u, 24.09.2026). Ob
das in die Abnahme gehört, entscheiden Anwender und Löser-Sitzung.

## 5a Anschlüsse (DIN EN 1993-1-8)

Ein Anschluss sitzt an einem Stabende. Die Beanspruchung sind die
**Stabendschnittgrößen** N, V_z und M_y an diesem Ende, gedreht so, dass ein
positives N Zug bedeutet (dieselbe Zählweise wie in `beam_end_forces`). Der
Anschluss wird über **alle GZT-Kombinationen** geführt; die ungünstigste ist
maßgebend. Die Aufteilung der Schnittgrößen auf die Bauteile folgt der
üblichen Modellvorstellung:

* Kopfplatte: Flanschkraft F_t = |M_y|/(h − t_f) + N·A_f/A auf die Schrauben
  der Zugzone, Querkraft gleichmäßig auf alle Schrauben, Druckflansch gegen
  b·t_f·f_y. Rippen setzt keiner dieser Nachweise an und auch nicht das
  FE-Teilmodell; der Vorschlag schlägt darum keine vor. Bleibt der Druckflansch
  maßgebend, endet das Nachbessern mit dem Hinweis auf das Profil (Voute oder
  größeres Profil), denn Blech, Schrauben und Nähte ändern diesen Nachweis nicht.
* Laschenstoß: Flanschlaschen tragen Normalkraft und Moment, Steglaschen die
  Querkraft (6.2.7).
* Knotenblech: Stabkraft auf die Schrauben beziehungsweise die Naht; das Blech
  wird über die **Whitmore-Breite** b_w = b + 2·L·tan 30° auf Zug und als
  Ersatzstab auf Druck nachgewiesen.

Nachgewiesen werden

| Bauteil | Nachweise | Abschnitt |
|---|---|---|
| Schraube | F_v,Rd, F_b,Rd, F_t,Rd, B_p,Rd, Interaktion, F_s,Rd (Kat. B/C), β_Lf | 3.6, 3.7, 3.9 |
| Zugzone | äquivalenter T-Stummel, Modus 1–3, l_eff nach Tab. 6.4/6.5 | 6.2.4 |
| Naht | Richtungsbezogen (σ_⊥, τ_⊥, τ_∥, β_w) und Vereinfacht | 4.5.3 |
| Blech | N_pl,Rd, N_u,Rd, Blockversagen V_eff,Rd | 6.2.3, 3.10.2 |

Der **T-Stummel** vergleicht die drei Modi: Modus 1 (Fließen des Blechs)
F = 4 M_pl,1,Rd/m, Modus 2 (Blech und Schraube) F = (2 M_pl,2,Rd + n ΣF_t,Rd)/(m+n),
Modus 3 (Schraube) F = ΣF_t,Rd; maßgebend ist der kleinste Wert, und welcher
es war, steht im Nachweis.

**Ermüdung des Anschlusses**: je Ermüdungslast die Schwingbreite der
Stabendschnittgrößen, daraus Δσ im betrachteten Bauteil (Schraube über den
Spannungsquerschnitt A_s, Naht über a·l, Blech über den Nettoquerschnitt).
Kerbfälle nach Tab. 8.1 und 8.5 — Schraube auf Zug 50, Schraube auf Abscheren
100 (m = 5), Blech mit Loch 90, gleitfeste Verbindung 112, Kehlnaht 80,
Kopfplattenanschluss 71. Die Schädigungen werden nach Palmgren–Miner **über
alle Ermüdungslasten** aufsummiert, getrennt je Kerbfall.

Die Schwingbreiten entstehen wie im Stabnachweis, nur aus der
Stabendschnittgröße (M_y bei der Kopfplatte, N bei Laschenstoß und
Knotenblech) statt aus der Spannung: zwei Zustände geben eine Stufe
|S_max − S_min| mit n Spielen, ein Verlauf das Kollektiv nach seinem
Zählverfahren (Spanne, Rainflow, Reservoir) mal den Wiederholungen. Jede Stufe
geht einzeln in die Wöhlerlinie, und die Anteile n_i/N_Ri werden addiert. Die
Schwingbreite trägt den Faktor der Last und γ_Ff. Fehlt der obere oder der
untere Zustand einer wirksamen Last in den Ergebnissen, geht die Last nicht
in D ein; fehlt einem Verlauf ein Glied, wird die Folge ohne dieses Glied
gezählt. In beiden Fällen gilt der Anschluss als unvollständig nachgewiesen.

Bei vorgespannten Schrauben hält die Vorspannung die Fuge geschlossen; in der
Schraube kommt dann nur ein Bruchteil der äußeren Schwingbreite an. Das
Programm rechnet mit dem Steifigkeitsverhältnis Schraube/Blech (Voreinstellung
1:5) und **sagt diese Annahme im Nachweis dazu**; genau ergibt sich die
Schwingbreite aus der Rechnung am Teilmodell. Ohne Vorspannung wirkt die volle
äußere Schwingbreite — auch das steht als Hinweis im Nachweis.

### 5a.1 Momenten-Rotations-Verhalten (Kap. 5 und 6.3)

Ein Anschluss ist weder starr noch gelenkig. Sein Verhalten wird über das
**Komponentenverfahren** beschrieben: jede Grundkomponente bekommt einen
Steifigkeitsbeiwert k_i nach Tab. 6.11, und die Anfangssteifigkeit folgt aus
der Reihenschaltung

    S_j,ini = E z_eq² / Σ_i (1 / k_i)

Umgesetzt sind

| k_i | Komponente | Formel |
|---|---|---|
| k_1 | Stützensteg als Schubfeld | 0,38 A_vc / (β z) |
| k_2 | Stützensteg auf Druck | 0,7 b_eff,c,wc t_wc / d_c |
| k_3 | Stützensteg auf Zug | 0,7 b_eff,t,wc t_wc / d_c |
| k_4 | Stützenflansch auf Biegung | 0,9 l_eff t_fc³ / m³ |
| k_5 | Stirnplatte auf Biegung | 0,9 l_eff t_p³ / m³ |
| k_10 | Schrauben auf Zug | 1,6 A_s / L_b |

Bei mehreren Schraubenreihen werden die Reihen nach 6.3.3.1 zu einer
Ersatzfeder zusammengefasst:

    k_eff,r = 1 / Σ_i (1 / k_i,r)
    z_eq    = Σ_r k_eff,r h_r² / Σ_r k_eff,r h_r
    k_eq    = Σ_r k_eff,r h_r / z_eq

**Momententragfähigkeit** M_j,Rd nach 6.2.7: Summe der Reihenkräfte F_tr,Rd mal
ihrem Hebelarm h_r zum Druckpunkt (Mitte des Druckflansches). Übersteigt die
Summe der Zugkräfte die Tragfähigkeit der Druckzone F_c,Rd = M_c,Rd/(h − t_f),
werden die Kräfte von der **untersten** Reihe her abgebaut (6.2.7.2(6)).

**Klassifizierung** nach 5.2.2.5 gegen die Biegesteifigkeit des angeschlossenen
Trägers — maßgebend ist die Länge des ganzen Stabes, nicht des einzelnen
Elements:

    starr        S_j,ini ≥ k_b E I_b / L_b     (k_b = 8 ausgesteift, 25 sonst)
    gelenkig     S_j,ini ≤ 0,5 E I_b / L_b
    nachgiebig   dazwischen

und nach 5.2.3 gegen M_pl,Rd des Trägers in voll-, teiltragfähig und gelenkig.

**Rotationsvermögen** nach 6.4.2(2): ein geschraubter Anschluss hat genügend
Rotationskapazität, wenn seine Tragfähigkeit vom Biegen des Blechs bestimmt
wird **und** das Blech dünn genug ist, damit sich die Fließgelenke ausbilden:

    t ≤ 0,36 d √(f_ub / f_y)

Ist das nicht erfüllt, sagt das Programm es und weist darauf hin, dass für eine
plastische Berechnung das Rotationsvermögen nachzuweisen ist.

**In der Berechnung** sitzt der Anschluss als Drehfeder am Stabende. Gerechnet
wird nach der Vereinfachung 5.1.2(4) mit

    S_j = S_j,ini / η        (η = 2 für geschraubte Stirnplatten, Tab. 5.2)

so dass ein einziger Rechendurchgang genügt und das Ergebnis für jedes M_j,Ed
gilt. Die Voreinstellung „automatisch" folgt der Klassifizierung: ein starrer
Anschluss bleibt starr, ein nachgiebiger wird zur Drehfeder, ein gelenkiger zum
Momentengelenk. Die Feder wird über dieselbe exakte Reihenschaltung eingebaut
wie ein Federgelenk (Kapitel 4.2), also ohne Näherung im Element.

Sind keine Angaben zur Stütze vorhanden, entfallen k_1 bis k_4. S_j,ini ist
dann eine **obere Schranke** — der wirkliche Anschluss ist weicher —, und
genau das steht als Hinweis im Nachweis und im Bericht.

Ein Laschenstoß gilt als durchgehend und damit starr; bei Schrauben der
Kategorie A oder D wird darauf hingewiesen, dass der Schlupf des Lochspiels
nicht in der Rechnung steckt. Ein Diagonalanschluss über ein Knotenblech gilt
nach 5.1.5 als gelenkig.

Die Geometrievorschläge (Blechdicken, Schraubenbild, Nahtdicken) sind
**Vorschläge, keine Nachweise**: sie folgen den Konstruktionsregeln
(Rand- und Lochabstände Tab. 3.3, Nahtdicken 4.5.1) und werden so lange
nachgebessert, bis die Nachweise für die eingegebenen Schnittgrößen erfüllt
sind. Maßgebend ist immer die anschließende Rechnung über alle Kombinationen.

## 5b Verformungsnachweise (Grenzzustand der Gebrauchstauglichkeit)

Nachgewiesen wird gegen die GZG-Kombinationen nach DIN EN 1990, 6.5.3 —
charakteristisch (6.14b), häufig (6.15b), quasi-ständig (6.16b). Jeder
Nachweis läuft über alle Kombinationen seiner Bemessungssituation; die
ungünstigste ist maßgebend.

**Durchbiegung eines Stabes** wird auf die **Sehne** zwischen den Stabenden
bezogen — nicht auf die Ausgangslage. Sie folgt aus der Momentenlinie:

    w″(x) = M(x) / (E I)

zweifach integriert, anschließend die Gerade durch die beiden Stabenden
abgezogen. Innerhalb eines Elements ist M(x) bei linear veränderlicher
Streckenlast höchstens ein Polynom dritten Grades und EI konstant; die
Krümmung wird darum durch ein kubisches Polynom exakt beschrieben und
geschlossen integriert. Zwei Folgen:

* Das Ergebnis ist **auch bei nur einem Element je Stab exakt** — geprüft
  gegen 5qL⁴/384EI und PL³/48EI mit Abweichung 0,0000 %.
* Der Starrkörperanteil (Auflagersenkung, Verdrehung des ganzen Stabes) fällt
  beim Abzug der Sehne heraus. Für einen Kragarm ist deshalb nicht die
  Durchbiegung, sondern die **Knotenverschiebung** der richtige Nachweis.

Eine Überhöhung w_c wird abgezogen (DIN EN 1993-1-1, A.1.4.2: w = w_max − w_c).

**Knoten**: Verschiebung oder Verdrehung gegenüber der Ausgangslage —
Kragarmspitze, Stützenkopf, Verdrehung eines Auflagers.

**Punktpaar**: die Verschiebung zweier Knoten **gegeneinander**. Damit werden
Dichtungen, Führungen, Fugen und Anschläge nachgewiesen, wie sie DIN 19704-1
im Stahlwasserbau verlangt.

Grenzwerte sind L/x (L = Stablänge beziehungsweise Abstand der beiden Knoten)
oder ein absoluter Wert in mm beziehungsweise mrad. Fehlt die verlangte
Bemessungssituation im Modell, wird der Nachweis **nicht geführt** und das
gesagt — es wird nichts ersatzweise eingesetzt.

## 6 Modalanalyse und Knicken

* Eigenschwingungen: verallgemeinertes Eigenwertproblem (K − ω² M) φ = 0
  mit konsistenter Balkenmassenmatrix bzw. konzentrierten Massen (Schalen,
  Volumen), Shift-Invert-Lanczos (ARPACK).
* Lineares Knicken: (K + λ K_g) φ = 0 mit der geometrischen Steifigkeit der
  Stäbe (Przemieniecki) aus dem Grundzustand eines Lastfalls oder einer
  Kombination, im System seiner Situation (Abschnitt 3.1). Der
  Knicklastfaktor λ multipliziert die Lasten des Grundzustands.
  Gelöst wird mit K als Metrik: (−K_g) φ = μ K φ, λ = 1/μ, die
  betragsgrößten μ (Lanczos, ARPACK) mit einem festen Startvektor. Jeder
  Lanczos-Schritt löst mit K; dafür dient die Faktorisierung des
  Grundzustands, auch mit dem Lagrange-Rand der Hilfsfesselung. Ein
  iterativer Löser (PyAMG) hat keine Faktorisierung, jeder Schritt wäre eine
  volle Iteration. Dann wird K für das Verzweigungsproblem eigens direkt
  zerlegt (Wahl wie „automatisch“), und PyAMG rechnet nur den Grundzustand.
  Am Portal mit 17 430 Freiheitsgraden (vier Moden, gemessen 24.09.2026)
  dauerte das Knicken mit PyAMG so 7,5 s; mit einer AMG-Iteration in jedem
  Schritt (125 Lösungen) waren es 316,6 s, bei denselben Faktoren auf sechs
  Stellen. Scheitert die direkte Zerlegung, iteriert PyAMG jeden Schritt,
  und das Protokoll sagt es. Ausgegeben werden die betragskleinsten λ beider
  Vorzeichen (negativ: Knicken unter umgekehrter Last), nach Betrag geordnet.
  Bis zum 23.09.2026 stand dort eigsh(K, M = −K_g, σ = 0): ARPACK verlangt in
  diesem Modus ein positiv semidefinites M, und mit Zug und Druck im
  Grundzustand ist −K_g indefinit. Am Zweigelenkrahmen unter Wind
  (`tests/test_knicklaengen.py`) kamen in sechs Läufen erste Faktoren
  zwischen 1,00 und 4,77 heraus; das dichte Problem hat 77,3287, siebenfach.
  Jetzt steht 77,3287 in jedem Lauf; die zweite und dritte Kopie des
  mehrfachen Eigenwerts streuen von Lauf zu Lauf in der 14. Stelle.

## 6a Vernetzung von Volumenkörpern

Ein Volumenkörper aus RFEM ist eine **Randdarstellung**: eine Hülle aus
Flächen, die ihrerseits von Linien berandet sind. Abgebildet (*mapped*)
vernetzen lassen sich davon nur der Sechsflächner (6 Vierecke, 8 Knoten,
trilineare Abbildung) und der Tetraeder (4 Dreiecke, 4 Knoten). Alles andere
geht an den **freien Vernetzer** (`statik3d/mesher3d.py`). Er arbeitet in vier
Schritten, jeder für sich nachrechenbar.

**1 Randnetz.** Jede Randfläche wird in Dreiecke geteilt:

| Randfläche | Weg |
|---|---|
| eben, auch mit Bohrungen | in ihrer Ebene frei vernetzt (Delaunay + Schwerpunktprobe) |
| krumm, vier Randlinien | **Coons-Fleck** zwischen den vier Randkurven; für eine Zylinderhälfte ist er die Fläche selbst, keine Näherung |
| krumm auf einem Zylinder | in der **Abwicklung** (r·φ, Achskoordinate) vernetzt und exakt zurückgelegt |
| krumm, sonst | ebenes Netz auf der Ausgleichsebene, dann **harmonisch** in den Rand eingespannt: div grad w = 0 mit dem Rand als Randbedingung |

Die **Ansicht** geht denselben Weg, wenn kein Netz da ist: eben mit
Innenrändern, krumm über den Coons-Fleck. Ob eine Fläche krumm ist, sagen
**zwei** Zeugen, und die Entscheidung fällt immer zur Wölbung hin: die
Flächenart aus der Quelldatei (`Flaeche.typ` — `regelflaeche` und
`beschnitten` heißen krumm) **oder** die geometrische Probe, ob die
Randpunkte in einer Ebene liegen. So irrt jeder der beiden nur in eine
Richtung — die geometrische Probe kann eine gewölbte Fläche für eben halten,
nie umgekehrt, und eine ohne Angabe geladene Fläche (die Vorgabe ist `eben`)
wird trotzdem richtig gezeichnet. Am Drehlagermodell stimmen beide Zeugen bei
allen 1375 Flächen überein.

Hat der Rand mehr als vier Seiten, wird er in vier geteilt. Maßgebend sind
zuerst die **vier Eckknoten**, die RFEM zum Viereck selbst nennt
(`Flaeche.ecken`; im Drehlagermodell bei allen 782 Vierecken vorhanden) —
sie beschreiben die Topologie und sind damit die verlässliche Auskunft. Fehlen
sie, werden die Seiten an ihren **glatten Ecken** zusammengefasst (Knick
≤ 15°) — RFEM teilt eine gerade Kante schon einmal in zwei Linien, und eine
Vierseitfläche bleibt eine Vierseitfläche. Ohne das griffe der Rückfall auf einen Fächer um den
Schwerpunkt, dessen Dreiecke bei einem Halbkreis quer durch das Bauteil
laufen: am Drehlagermodell wurden die vier Bolzenmäntel (F589, F590, F1670,
F1671) mit 2011 statt 645 cm² gezeichnet, 212 % zu viel. Nach dem
Zusammenfassen trifft die gezeichnete Fläche die Regelfläche (Bogenlänge mal
Höhe) exakt, und keine der 1375 Flächen fällt mehr auf den Fächer zurück.
Steht ein Netz, wird das Netz gezeichnet und die Geometrie nicht mehr
darüber; nur ihre Umrisse bleiben als Linien stehen.

Jede **Linie** wird dabei genau einmal abgetastet — die Teilung gehört der
Linie, nicht der Fläche. Nur so passen die Netze benachbarter Flächen
aufeinander. Gegenüberliegende Seiten einer abgebildet vernetzten Fläche
müssen gleich viele Abschnitte haben; diese Bindung wird über eine
Vereinigungssuche (union-find) durch das ganze Bauteil weitergereicht. Krumme
Linien bekommen zusätzlich zur Längenteilung eine **Krümmungsteilung**: der
gesamte Richtungswechsel wird durch 18° geteilt, ein Kreis bekommt also
mindestens zwanzig Abschnitte — ob er 10 mm oder 10 m Durchmesser hat. Bei
den früheren 30° (zwölf Abschnitte) weicht die Sehne um 3,4 % des
Halbmessers von der Bohrung ab, bei 18° um 1,2 %; für eine Kerbspannung am
Lochrand ist das der Unterschied zwischen brauchbar und nicht.

**Eine Linie neben einer feineren.** Die Mantellinie einer Bohrung ist der
Fall, an dem das auffiel: der Bohrungsrand wird nach der Krümmung geteilt (bei
r = 10 mm und 24 Sehnen sind das 2,6 mm), die Mantellinie aber nach ihrer
Länge — 35 mm bei 50 mm Zielkantenlänge sind **ein** Abschnitt, ein Sprung von
13:1. Kein Größenfeld im Inneren kann das heilen; es findet am Rand schon
nichts Feines vor.

Es gilt dieselbe Regel wie in der Fläche: von der feinen Nachbarlinie aus
wächst die Weite je Lage um 25 %. Wie viele Lagen eine Linie der Länge L
dafür braucht, steht geschlossen da —

    k = ln(1 + L · g / s) / ln(1 + g)

mit s als der feinsten Weite an ihren Enden. Das begrenzt sich selbst: k
wächst nur logarithmisch mit L, und sobald L/k über die Zielkantenlänge käme,
gewinnt ohnehin wieder ⌈L/h⌉. Die 35-mm-Mantellinie bekommt so 10 statt einem
Abschnitt, eine 900-mm-Außenlinie bleibt bei 50 mm. Weitergereicht wird über
gemeinsame Knoten, in drei Durchgängen — genug, um eine Bohrung herum, zu
wenig, um durch das halbe Modell zu wandern. Die Regel gehört zu
**„Intelligent anpassen"**; ohne den Haken bleibt es bei ⌈L/h⌉.

Am Ergebnis gemessen (20-mm-Bohrung, 35 mm tief, in einer 900-mm-Platte bei
50 mm Zielkantenlänge): der Anteil der Tetraeder unter der Güte 0,3 an der
Bohrungswand fällt von **6,8 % auf 1,0 %**, die Formgüte dort steigt im Median
von 0,70 auf 0,81 — für doppelt so viele Elemente an diesem bewusst
bohrungsdominierten Bauteil.

**Übergang von der Bohrung ins Feld.** Die feine Teilung des Bohrungsrandes
setzte sich früher nicht ins Innere fort: das Innengitter war gleichmäßig mit
der Zielkantenlänge, und alles näher als 0,65·h am Rand fiel weg. Gemessen an
einer 20-mm-Bohrung in einer 900-mm-Platte bei 50 mm Zielkantenlänge stand am
Loch ein Kranz winziger Dreiecke (Sehne 3,1 mm) und daran unmittelbar das
50-mm-Feld: im Kranz zwischen r und 2r lag **kein einziger** Knoten, das
Kantenverhältnis der Dreiecke am Loch betrug im Median 17, die Formgüte 0,06,
und 73 % der Dreiecke lagen unter 0,3.

Jetzt werden um jede Öffnung **Kränze** gelegt, deren Weite vom Loch weg um
je 25 % wächst (der Wachstumsfaktor, mit dem ein Vernetzer mit
Größensteuerung üblicherweise arbeitet), bis sie die Zielkantenlänge
erreicht; ab da übernimmt das gleichmäßige Gitter. Das ist dieselbe Regel,
mit der das Tetraedernetz schon arbeitet (Schritt 3), nur jetzt auch in der
Fläche. Am selben Beispiel: 72 Knoten im Kranz r … 2r, Kantenverhältnis im
Median 1,51, Güte 0,81, kein Dreieck unter 0,3 — für 56 % mehr Punkte auf
dieser Fläche (`test_groessenfeld_an_der_bohrung`).

**Randstrecken sind keine Glückssache.** Eine freie Delaunay-Zerlegung kennt
keine Randbedingung: sie *kann* eine Randstrecke überspringen, und ob sie es
tut, hängt an der Lage der Innenpunkte — also an der Phase des Gitters, an der
Drehung der Fläche, an Rundung. Der Fall wurde sichtbar, seit gemeinsame
Linien nicht mehr allein feiner geteilt werden: die Linie bleibt grob, das
Innengitter wird feiner, und bei einer achsparallelen Fläche fiel die
Gitterreihe j = 0 auf `lo[1]` — genau auf die Randlinie. Der alte Filter maß
den Abstand zum nächsten Rand**punkt**; mitten zwischen zwei 50,5 mm
auseinanderliegenden Ringpunkten sind das 25 mm, und die Schranke 0,65·h =
21,7 mm war damit erfüllt, obwohl der Punkt **0,000 mm** von der Strecke
entfernt lag. Die Zerlegung nahm ihn, die Randstrecke war keine Kante mehr,
die Hülle klaffte auf, und fünf Körper des Drehlagermodells endeten ohne Netz,
obwohl ihr erster Anlauf ein gültiges hatte.

Drei Dinge stehen jetzt dagegen, in dieser Reihenfolge:

1. Gemessen wird der Abstand zur Rand**strecke**, nicht zum nächsten
   Randpunkt. (Die Umkreisscheibe der Strecke — die Gabriel/Ruppert-Regel —
   wäre die schärfere Schranke, taugt hier aber nicht: bei einem Quadrat mit
   vier 1-m-Strecken überdecken die Scheiben das ganze Gebiet, und es bliebe
   kein einziger Innenpunkt übrig.)
2. Das Innengitter liegt um eine halbe Zelle versetzt, damit die erste Reihe
   nicht auf der Unterkante des umschließenden Rechtecks liegt. Das allein
   genügt nicht — gedrehte Flächen —, schadet aber nicht.
3. **Erzwungen** statt gehofft: fehlt nach der Zerlegung eine Randstrecke,
   fliegen die Innenpunkte in ihrer Umkreisscheibe heraus und es wird neu
   zerlegt. Jede Runde entfernt mindestens einen Punkt, also endet das
   Verfahren; und es fasst nie einen Randpunkt an. Bleibt danach eine Strecke
   offen, liegt es an der Geometrie selbst — und *das* wird gemeldet.

Geprüft wird das nicht an einem Beispiel, sondern an einer Stichprobe über den
Raum, in dem es schiefging: Größe, Teilung, Zielkantenlänge, Drehung und Lage
zufällig, dazu drei Bauformen (Streifen mit grob festgelegter Langseite,
L-Form mit einspringender Ecke, Platte mit ein bis drei Bohrungen) — 545
gültige Flächen, **keine einzige** mit fehlender Randstrecke
(`test_randstrecken_sind_keine_glueckssache`).

**Größenfeld an einer festgelegten Linie.** Gehört eine Randlinie einem
zweiten Körper, darf sie nicht allein nachgeteilt werden — sie bleibt grob,
während der eigene Körper feiner vernetzt. Ein Dreieck mit 200 mm Grundseite
und 25 mm hohen Nachbarn ist aber ein Splitter, ganz gleich wie brav das
Innengitter liegt. Gemessen am Rechteck 1000 × 500 mm mit festgelegter
Langseite bei h = 25 mm, schlechteste Dreiecksgüte:

| Randstrecke / h | 1 | 2 | 3 | 4 | 6 | 8 |
|---|---|---|---|---|---|---|
| ohne Größenfeld | 0,837 | 0,725 | 0,480 | 0,480 | 0,221 | 0,153 |
| mit Größenfeld  | 0,837 | 0,725 | 0,659 | 0,643 | 0,443 | 0,322 |

Neben einer festgelegten Strecke gilt darum ihre Länge, geteilt durch zwei,
als Sollweite; sie geht mit 25 % je Längeneinheit auf die Zielkantenlänge
zurück — dasselbe Wachstum wie bei den Kränzen und im Tetraedernetz. Bis zum
Verhältnis 2 ist das ein **Nullschritt**, und zwar ohne Schwelle: L/2 läuft
dort gerade auf h hinaus. Eine Schwelle wäre hier fehl am Platz — sie läge
genau auf den Werten, die im Modell vorkommen (`VERHAELTNIS_FEST`,
`test_groessenfeld_an_der_festgelegten_linie`).

**2 Dichtheit.** Die Flächennetze werden über die **Kennung ihrer
Linienpunkte** zusammengesetzt, nicht über die Koordinate. Jeder Punkt einer
geteilten Linie heißt `(Linie, k)` in der eigenen Zählrichtung der Linie, die
beiden Enden nach ihrem Knoten; zwei Nachbarflächen holen ihre gemeinsamen
Randpunkte aus derselben Quelle und finden sich darüber.

Das ist keine Feinheit. Jede Fläche hebt ihre Randpunkte über die **eigene**
Ausgleichsebene aus 2D zurück; die beiden Kopien desselben Linienpunkts sind
danach nur noch auf Maschinengenauigkeit gleich (3·10⁻¹⁶ … 1,3·10⁻¹⁵ m). Ein
Vernähen über ein Rundungsgitter `round(P/tol)` legt sie nur dann zusammen,
wenn keine Zellgrenze dazwischenliegt — und ob eine dazwischenliegt, ist reine
Arithmetik: CAD-Koordinaten sind Vielfache von 0,25 mm, `tol` ist h/10000, und
bei manchem h fällt `x/tol` genau auf eine halbe Ganzzahl. An einem Quader mit
einer Ecke bei x = −421,25 mm und h = 50/1,5² mm riss die Hülle so an **156**
Kanten auf, ohne dass an der Geometrie etwas fehlte
(`test_huelle_ohne_rundungsgitter`).

Was danach noch doppelt daliegt (Ränder ohne Knotennamen), wird nach
**Abstand** vernäht — mit einem KD-Baum und Zusammenhangskomponenten, nicht
mit einem Rundungsgitter. Dann wird geprüft: jede Kante muss in
genau zwei Dreiecken liegen. Ist sie es nicht, nennt das Protokoll jede
offene Kante mit ihren Knoten, Koordinaten und den Randflächen, von denen die
anliegenden Dreiecke stammen — zwei Zeilen mit derselben Koordinate und
verschiedenen Flächen heißen: dort stehen zwei Kopien desselben Punktes.
Das Volumen folgt aus dem Gaußschen Satz,

    V = 1/6 · Σ (a × b) · c   über alle Dreiecke,

und muss positiv sein — dann zeigt die Hülle nach außen. Ist sie nicht dicht,
wird **nicht** vernetzt: ein Netz aus einer undichten Hülle ist stillschweigend
falsch, und das ist schlimmer als kein Netz. Fehlt einer Fläche eine
Randstrecke, wird die *Linie* feiner geteilt und alles neu vernetzt — es sei
denn, sie gehört einem zweiten Körper; dann bliebe die Fuge nicht konform.

Reißt die Hülle erst in einem **späteren** Anlauf, wird das Netz des früheren
nicht verworfen. Es ist gröber, aber es ist eines: V109 hatte nach Anlauf 1
Tetraeder mit 88,6 % Randtreue und endete trotzdem ohne Netz, weil Anlauf 2
(feiner) die Hülle aufriss. Jetzt bleibt das bessere gültige Netz stehen, und
das Protokoll sagt, warum nicht feiner. Nur wenn schon der **erste** Anlauf
scheitert, bleibt der Körper ohne Netz — und dann nennt der Fehlertext die
offenen Kanten mit Koordinaten und Randflächen, höchstens zehn, den Rest im
Protokoll.

**3 Punkte.** Zuerst ein raumzentriertes kubisches Gitter (BCC) mit der
Zielkantenlänge — das Punktmuster, dessen Delaunay-Zerlegung von sich aus gute
Tetraeder liefert (Labelle/Shewchuk). Dann **Delaunay-Verfeinerung**: der
Umkugelmittelpunkt jedes schlechten Tetraeders wird eingefügt. Schlecht heißt
*zu groß* (Umkugelhalbmesser über 0,62·h_lokal — der reguläre Tetraeder mit der
Kante a hat den Halbmesser a·√6/4 = 0,6124 a) oder *schlecht geformt*
(Umkugelhalbmesser über dem Doppelten der kürzesten Kante, Ruppert/Shewchuk).
Die Sollkantenlänge am Ort wächst vom Rand weg:

    h_lokal(x) = min(h, Randkantenlänge am nächsten Randpunkt + 0,35 · Abstand zum Rand)

So bekommt eine 20-mm-Bohrung in einer 900-mm-Platte kleine Elemente, ohne dass
die ganze Platte fein wird.

**4 Tetraeder.** Von der Delaunay-Zerlegung bleiben die Tetraeder, deren
Schwerpunkt im Körper liegt (die Zerlegung füllt immer die konvexe Hülle; alles
in einer Einbuchtung gehört nicht dazu). Ob ein Punkt im Körper liegt, wird auf
zwei völlig verschiedenen Wegen beantwortet:

* **Strahlenzählung** — ein Strahl nach +z schneidet eine geschlossene Hülle
  ungerade oft, wenn der Punkt innen liegt; mit einem Gitterindex über die
  xy-Projektion, damit nicht jeder Punkt gegen jedes Dreieck zu prüfen ist.
  Die Zelle des Index ist das **Doppelte der Median-Kantenlänge** der
  Hülldreiecke, höchstens aber **0,5 h**. Bis zum 10.09.2026 nahm der
  Vernetzer fest 0,5 h (die Vorgabe der Klasse war die Ausdehnung des größten
  Dreiecks). Bei einer Hülle mit 5-mm-Dreiecken um die Bohrungen (V31,
  21 716 Dreiecke, Median 5 mm) sind 25 mm noch das Fünffache des Medians:
  175 Zellen, und `innen()` trug 103,7 von 210 s der Vernetzung dieses
  Körpers. Gemessen für 60 000 Punkte, Ergebnis in jeder Spalte identisch
  (`test_gitterindex_zelle`):

  | Körper | Dreiecke | Median | größtes Dreieck | 0,5 h (vorher) | 1×Med | **2×Med** | 3×Med | 4×Med | 8×Med |
  |---|---|---|---|---|---|---|---|---|---|
  | V31 | 21 716 | 5,0 mm | 4,49 s | 0,66 | 0,26 | **0,19** | 0,27 | 0,43 | 1,64 |
  | V30 | 23 982 | 6,6 mm | 0,93 s | 0,23 | 0,46 | 0,20 | 0,16 | 0,20 | 0,61 |
  | V15 | 11 824 | 5,1 mm | 3,87 s | 0,35 | 0,22 | **0,14** | 0,16 | 0,21 | 0,96 |
  | V6 | 872 | 50 mm | 0,58 s | **0,08** | 0,25 | 0,71 | 1,50 | 1,74 | 2,94 |

  Für die feinen Hüllen, die die Zeit bestimmen, ist 2×Median das Optimum;
  für grobe Hüllen (V6: Median = h) hält die Deckelung durch 0,5 h den
  heutigen Wert. Große Dreiecke liegen in jeder Zelle, die ihr Schatten
  überdeckt — das war schon so und bleibt richtig.
* **Verallgemeinerte Windungszahl** — die Summe der Raumwinkel aller Dreiecke
  (van Oosterom/Strackee) ist 4π innen und 0 außen. Sie kennt keine
  Sonderfälle und ist der Prüfstein für die schnelle Strahlenzählung; die
  Prüfungen vergleichen beide gegeneinander.

Zum Schluss wird **gerechnet, nicht gehofft**. Im Protokoll steht je Körper:

* Summe der Tetraedervolumen gegen das Hüllvolumen aus Schritt 2,
* Güte q = 12·(3V)^(2/3) / Σ l² (1 für den regulären, 0 für den flachen
  Tetraeder) als kleinster und mittlerer Wert und die Zahl der Splitter
  (q < 0,1),
* **Randtreue**: welcher Anteil der freien Elementseiten wirklich auf der Hülle
  liegt, und ihr größter Abstand dazu. Verglichen wird geometrisch, nicht
  Dreieck gegen Dreieck: ein ebenes Viereck lässt sich über beide Diagonalen
  teilen, ohne dass eine der beiden falsch wäre.
  Misslingt die Messung, steht seit 23.09.2026 **0,0** im Bericht („nicht
  gemessen", wie überall im Programm) und der Grund daneben; vorher stand 1,0 —
  die Zusage, der Rand liege auf der Hülle. Aus 83,3 % wurden so 100,0 %, der
  Eintrag „Randtreue unter der Grenze" fiel aus `netzguete()["gerissen"]`, und der
  zweite Anlauf unterblieb (Statik3D-Sitzung, gemessen 22.09.2026).

**Die Lücke im Netzrand (23.09.2026).** Die Statik3D-Sitzung fand an fünf von neun
L-, T- und U-Prismen einen fehlenden Tetraeder an der Oberfläche (0,003 bis 0,113 %
des Körpers) und am Würfel mit angehobener Deckelecke einen ganz eingeschlossenen.
Drei Ursachen, jede gemessen:

1. **Die Strahlenzählung zählte eine Kante doppelt.** Trifft der Strahl vom
   Schwerpunkt genau die gemeinsame Kante zweier Hülldreiecke, zählten beide
   (`l >= 0`): aus einem Durchgang wurden zwei, die Parität kippte, `_innere` warf den
   Tetraeder hinaus. Am L-Prisma lag der Schwerpunkt genau über der Kantenmitte,
   weil die beiden übrigen Ecken im Grundriss denselben Mittelpunkt hatten — kein
   Zufall, sondern Geometrie. Jetzt entscheidet die Kante wie für einen um (ε, ε²)
   verschobenen Punkt: eine baryzentrische Koordinate auf null zählt nach dem
   Vorzeichen ihrer Ableitung nach x, bei null nach y (Simulation of Simplicity,
   `_seite_mit_ausweichung`). Das ist für alle Dreiecke derselbe verschobene Punkt,
   darum stimmt die Parität auch an Ecken und an Faltkanten der Projektion.
2. **Ein Startpunkt stand vor der Hülle.** Die Gitterpunkte hielten Abstand zu den
   Hüll**punkten** (0,65 h), nicht zur Hüllfläche: mitten in einer Facette kann ein
   Punkt 0,85 mm vor der Hülle stehen (Buchse, h = 15 mm). Der flache Tetraeder
   zwischen ihm und der Facette hat eine riesige Umkugel und ist nie Delaunay — das
   Hülldreieck wird nicht zurückgewonnen, im Netz bleibt eine Pyramide über dem
   Hüllviereck (0,0015 %). Jetzt `RANDABSTAND_FLAECHE` = 0,4 h zur Hüllfläche, derselbe
   Abstand, den die Verfeinerung für ihre Umkugelmittelpunkte hält. Nebenwirkung:
   weniger Elemente (L-Prisma h = 0,25: 821 → 634, Würfel 16 461 → 15 995).
3. **Die Nachführung gab zu früh auf.** `tetraedern_treu` hörte bei 0,01 % Fehlbetrag
   und 99,9 % Randtreue auf, nach höchstens drei Runden — genau die Lücken, die die
   Abnahme dann fand. Jetzt gilt der **Rauminhalt** (`TREU_VOLUMEN` = 10⁻⁶: über dem
   Rauschen der aussortierten flachen Tetraeder, 3,6·10⁻⁷ an der Platte mit Bohrung,
   und dreißigfach unter der kleinsten echten Lücke), bis zu acht Runden
   (`TREU_RUNDEN`), Abbruch nach vier Runden ohne Verbesserung (`TREU_STILLSTAND`; die
   Konvergenz ist nicht monoton: 1,37 → 0,12 → 0,12 → 0,03 → 0,06 → 0,0076 %). Und es
   werden nur **echte Dellen** nachgeführt (`echte_dellen`): eine freie Seite, die
   kein Hülldreieck ist und eine Ecke mit Abstand zur Hülle hat oder deren Ecken
   keinen gemeinsamen glatten Fleck haben (`_glatte_flecken`: Herkunftsflächen, die
   an ihren gemeinsamen Hüllkanten unter 30° aneinanderstoßen, sind ein Fleck — RFEM
   legt einen Zylindermantel als zwei Halbzylinder an). Der Diagonaltausch eines
   windschiefen Hüllvierecks ist keine Delle; mit dem Rauminhalt allein als
   Kriterium trieb er den Würfel in acht Runden und 7 % mehr Elemente.

Abnahme (`test_luecke_im_netzrand_geschlossen`): an allen neun Prismen und am Würfel
ist die Summe der Elementvolumina gleich dem Hüllvolumen auf Rundung, die Abnahme
meldet keine „Lücke im Netzrand" mehr. Rücknahmeprobe: alle drei Kuren zurück, und
die Zahlen der Statik3D-Sitzung sind wieder da (821 Tetraeder und 0,079 %,
663 und 0,113 %) — jede allein lässt sich nicht zurücknehmen, die anderen ändern die
Punktmenge, und der Gleichstand tritt nicht ein.

**Was bleibt, und warum.** An einer **rechtwinkligen einspringenden Kante** liegt der
Kantenpunkt nach Thales auf *jeder* Umkugel einer Netzkante quer durch die Aussparung;
die Zerlegung entscheidet den Gleichstand nach den übrigen Punkten, und kein Punkt
auf der Hülle kann ihn brechen. Das Halbieren der Hülldreiecke an der Delle hilft oft
(einer Stichprobe über 69 Ziellängen an drei Prismen blieben 11 statt 18 mit
Fehlbetrag), divergiert aber auch (nach 14 Runden 1 417 Dellen statt 3). Schutzpunkte
außerhalb der Kante wurden gebaut und **verworfen**: 0,2 L vor der Wand liegen sie in
den Umkugeln der Wanddreiecke, und die Wand geht verloren (34 → 237 Dellen). Der
Neustart mit anderer Gitterphase ebenso (0,99 und 1,75 % statt 0,0076 %). Was bleibt,
wird **gemeldet** („Lücke im Netzrand bleibt nach N Durchgängen — x % des Rauminhalts,
k freie Seiten neben der Hülle"), nicht still gelassen.

**Kantenkippen an der Hülle (zweiter Auftrag, 23.09.2026 abends).** Die Lücke an der
rechtwinklig einspringenden Kante hat eine einfache Gestalt, gemessen an jedem der
69 Netze der Stichprobe: in der **ersten** Zerlegung fehlt genau **ein** Hülldreieck,
und genau eine Netzkante durchstößt es, an der genau drei Tetraeder hängen, deren
übrige Ecken die drei Ecken des Dreiecks sind. Das ist der Gleichstand von fünf
Punkten auf einer Kugel (Thales: der Kantenpunkt sieht jede Sehne quer durch die
Kerbe unter 90°); Qhull darf die drei Tetraeder um die Kante nehmen oder die zwei
mit dem Dreieck als Seite. `mesher3d.huelle_kippen` nimmt vor der Frage innen/außen
die zweite Antwort (Kantenkippen 3 → 2, kein neuer Punkt, derselbe Rauminhalt) —
die bedingte Delaunay-Zerlegung für genau den Fall, der vorkommt. Gemessen
23.09.2026: Stichprobe 3 Prismen × 23 Ziellängen **11 → 2 von 69** mit Fehlbetrag,
die Stichprobe der Statik3D-Sitzung (ihre L-, T-, U-Prismen) **1 → 0 von 69**; das
T-Prisma der Statik3D-Sitzung mit h = 0,09 exakt im ersten Durchgang statt 0,0003 %
nach acht. Was bleibt (L h = 0,24: −0,065 %, T h = 0,16: +0,0012 %): dort fehlt eine
**Hüllkante** (das Dreieck wird von einer Tetraederseite gekreuzt, nicht von einer
Kante) oder die Kante trägt vier bis fünf Tetraeder — Segmentrückgewinnung und
4-4-Kippen, offen. Ein Versuch mit Steiner-Punkten an den Durchstoßstellen
(Segment- und Facettenrückgewinnung wie in TetGen) wurde gebaut, gemessen und
zurückgenommen: 11 → 5 an der eigenen Stichprobe, aber 1 → 3 an der der
Statik3D-Sitzung und 3,4-mal so viele Elemente an der Bohrung
(`test_mantellinie_der_bohrung`). Test `test_huelle_kippen`, Schalter `KIPP_RUNDEN`.
**Dritter Auftrag (24.09.2026):** die beiden verbliebenen Netze brauchten zwei weitere
Kippungen, beide ohne neuen Punkt — **2 → 3** für eine fehlende Hüllkante, die eine
Tetraederseite kreuzt, deren zwei Tetraeder die Kantenenden als Spitzen haben
(Segmentrückgewinnung), und **4 → 4** für ein Hülldreieck, dessen stechende Kante vier
Tetraeder trägt und dessen drei Ecken unter den vier Ringecken sind: das Achtflach um die
Kante wird über die Diagonale des Dreiecks neu geteilt, gültig, wenn der Rauminhalt der vier
neuen gleich dem der vier alten ist. Damit L h = 0,24 (368 Tetraeder) und T h = 0,16 (1 212)
exakt im ersten Durchgang; beide Stichproben **0 von 69** (gemessen 24.09.2026). Was an
fehlenden Hülldreiecken bleibt, sind Diagonaltausche ebener Vierecke — kein Rauminhalt, keine
Delle.

**Diagonaltausche ebener Vierecke sind an gemeinsamen Flächen nicht harmlos (25.09.2026).**
Für einen Körper allein stimmt der Satz: Rauminhalt und Randtreue bleiben exakt. Teilen zwei
verschweißte Körper eine Fläche, bekommen beide dasselbe Flächennetz vorgeschrieben
(`flaechennetz`, an zwei Würfeln gemessen: 30 Dreiecke, beide Mengen gleich), und jeder darf
es nur einhalten, nicht neu würfeln — sonst hängen die Körper dort nur noch an den Ecken.
Genau das geschah an Rechteckzellen, deren vier Punkte auf einem Kreis liegen (regelmäßige
Teilung des Randes gegen das Dreiecksgitter im Inneren), auf zwei Wegen: Qhull nahm die andere
Diagonale, und `huelle_kippen` kannte den Fall nicht — die fehlende Hüllkante kreuzt keine
Tetraederseite, sondern die Hüllkante selbst, 2 → 3 greift nicht; oder Qhull gab die vier
Punkte als **flachen Tetraeder** aus, und `flache_aufloesen` tauschte ihn blind auf die andere
Diagonale — nach der Hüllenprüfung, die darum nichts sah. Gemessen an zwei Einheitswürfeln
mit gemeinsamer Fläche (eigener Vernetzer, h = 250 mm, `modell_vernetzen`): **4 offene
Innenseiten** bei `tet4` und bei `tet10` dazu eine hängende Kantenmitte; die Prüfmatrix fand an
denselben Netzen σ_v bis +162 N/mm² neben der Lösung (`tet10`, verschweißt). gmsh + MMG3D
hielten die Hülle ein (0 offene Seiten). Zwei Ergänzungen, beide ohne neuen Punkt:
**Diagonale** in `huelle_kippen` — zur fehlenden Hüllkante a–b nennen die beiden Hülldreiecke
c1 und c2; steht im Netz die Kante c1–c2, wird ihr offener Fächer a, r₁, …, b von a aus (sonst
von b aus) in Dreiecke geteilt, jedes gibt zwei Tetraeder mit c1 und mit c2 (n → 2(n − 1)),
gültig bei positiven Rauminhalten mit derselben Summe; und `flache_aufloesen` bekommt die
Hülle: liegt der flache Tetraeder in einer Hüllfläche und tragen seine Innenseiten schon die
vorgeschriebene Diagonale, fällt er weg, statt getauscht zu werden. Beides zusammen: 0 offene
Innenseiten, `tet4` und `tet10`; jede Ergänzung allein lässt 4 bzw. 8 offen (gemessen
25.09.2026). Am Doppelwürfel kippt der Diagonalfall 9 bzw. 8 Kanten je Körper, auch an den
Außenflächen — dort war er bisher unbemerkt geblieben. Prüfungen `test_huelle_kippen` (2-2 und
3 → 4 am Fächer, Rücknahmeprobe über `KIPP_DIAGONALE`), `test_flache_aufloesen_huelle`,
`test_gemeinsame_flaeche_eigener_vernetzer` (Programmweg, `tet4` und `tet10`, Rücknahmeprobe).

**Gekrümmte tet10 am Drehlager (dritter Auftrag, 24.09.2026).** Verlangt war das gekrümmte
tet10-Netz des ganzen Drehlagers bei 18° und 36° — Seitenmitten auf der wahren Fläche,
Jacobi-Prüfung, örtliche Anläufe — mit Elementen, Knoten, ungültigen tet10 vor den Anläufen,
Rückfällen auf gerade Kanten (getrennt nach eigener und gemeinsamer Fläche), kleinster bezogener
Jacobi-Determinante und Zeit. Der erste Lauf (alter Stand, 18°) ergab 687 807 Elemente mit
**626 Rückfällen** (5 an gemeinsamen Flächen) und einer kleinsten bezogenen Determinante von
**−11,4** — Werte, die keine Krümmung erklärt. Die Diagnose an V30 (227 Rückfälle, 594 gekrümmte
Kanten) zeigte die Ursache: die gekrümmten Kanten waren **Sehnen über 36° bis 180°** auf Zylindern
mit r = 10 mm. Das sind keine Mantelkanten, sondern Kanten der **ebenen Stirnflächen** kleiner
Bohrungen — ein Dreiecksfächer aus Randkreispunkten, jede Kante mit beiden Enden auf dem Kreis.
Die Zuordnung „Kante gehört zur Fläche F, wenn beide Endpunkte über ihre Hülldreiecke zu F
gehören“ hielt sie für Mantelkanten und projizierte ihre Mitten radial auf den Zylinder; ein
Durchmesser bekam seine Mitte auf den Rand. Feiner vernetzen konnte das nie heilen (die drei
örtlichen Anläufe machten aus 899 ungültigen tet10 in V15 immer noch 144), und V30 bekam gar
keinen Anlauf, weil daneben die Güte riss und die Grenze der Elementzahl den ganzen Körper nicht
feiner ließ.

Drei Änderungen (`mesher3d.py`): (1) **Die Zuordnung über die Hülldreiecke**
(`randkanten_flaechen`): eine Kante gehört zu F, wenn sie Kante eines Hülldreiecks von F ist oder
die andere Diagonale eines Hüllvierecks aus zwei F-Dreiecken (die Zerlegung darf ein Viereck anders
teilen); alles andere ist eine Sehne durch das Innere und bleibt gerade. Arbeits- und Hauptprozess
rechnen damit dieselbe Menge. (2) **Innere Punkte gegen umklappende tet10**
(`_krumme_kappenpunkte`): was danach noch umklappt, ist flach gegen den Sehnenpfeil — am Zylinder
in Hohlzylinder (r 50, 36°, h 35 mm) zwei Tetraeder mit Höhe 1,6 mm über einer Sehne mit Pfeil
1,7 mm, zwei innere Ecken und eine Randsehne fast in einer Ebene. Ein Punkt im Schwerpunkt, von der
gekrümmten Mitte weg nach innen geschoben und so weit, dass er in der **Umkugel** des Tetraeders
bleibt (nur dann nimmt die Delaunay-Zerlegung es gewiss heraus — 12 mm tief lag er außerhalb der
Kugel eines 1,6 mm flachen Tetraeders, und das blieb durch drei Durchgänge), löst es auf; er hält
`KRUMM_KAPPEN_RANDABSTAND = 0,25` Sollgrößen Abstand zur Hülle (mit 0,4 wie die Kappen blieb am
Deckelrand kein Punkt übrig) und ändert die **Randfläche nicht** — darum wirkt das auch an einer
mit dem Nachbarn gemeinsamen Fläche, die kein Arbeitsprozess allein feiner machen darf, und die
gemeinsamen Knoten bleiben. Ein zweiter Durchgang im Hauptprozess mit beidseitiger Verfeinerung
ist damit nicht nötig. An eigenen Flächen kommen die Punkte erst nach den örtlichen Anläufen, weil
das feinere Netz die Form besser hält (Buchse r 50/100, 36°, h 35: 2 566 tet10 mit kleinster
bezogener Determinante 0,403 gegen 3 425 mit 0,028, wenn die Punkte zuerst kommen); an
gemeinsamen sofort. Weil Glättung und MMG3D innere Ecken danach wieder an die Fläche rücken
können, kommt am fertigen Netz noch das **Entzerren** (`krumme_entzerren`): jede innere Ecke
eines Tetraeders, das als tet10 umklappen würde, wird vom Ort der gekrümmten Mitte weg
verschoben, in Schritten von 1 bis 6 Sehnenpfeilen, bis das Element gültig ist und kein vorher
gültiges Element am Punkt seinen Rauminhalt verliert; Hüllpunkte bleiben stehen. Auch das
gehorcht der Reihenfolge: gemeinsame Flächen sofort, eigene erst nach den örtlichen Anläufen.
(3) **Die Anlaufschleife**: die örtlichen Anläufe laufen auch, wenn daneben
die Güte reißt; der beste Anlauf ist erst der ohne Lücke im Netzrand, dann der mit den wenigsten
ungültigen tet10, dann der mit dem kleinsten Abstandsmaß; und der Rückfall im Hauptprozess läuft
bis zum Stillstand, weil eine zurückgesetzte Mitte auch den Nachbarelementen gehört (ein tet10
mit det J = −6,9e-7 blieb sonst im Modell). Das Protokoll nennt seither auch die kleinste
bezogene Determinante **im fertigen Netz**. Nebenbei: die Seitenmittenknoten werden gesammelt
angelegt (`_tet10_kanten_anlegen`) — je Knoten ein `np.vstack` an das ganze Knotenfeld war bei
900 000 Kanten quadratisch.

Prüfkörper `test_gemeinsame_gekruemmte_flaeche_ohne_rueckfall`: Zylinder r 50 in Hohlzylinder
r 50/100, fest verbunden (gemeinsame Mantelfläche), 36°, h 35 mm, beide tet10 — **0 Rückfälle**,
größter Weg einer Seitenmitte der Sehnenpfeil 1,704 mm, 2 innere Punkte im Zylinder; ohne die
Punkte 2 Rückfälle an der gemeinsamen Fläche; mit der alten Zuordnung am Bolzen r 10 in Buchse
r 30 wandern Sehnen der Stirnfläche auf den Mantel (größter Weg 1,91 mm gegen den Pfeil 1,022 mm)
und 3 tet10 bleiben gerade. Die Hohlzylinder-Tabelle des zweiten Auftrags bleibt bei 0: h 35 / 20 /
10 mm → 1 758 / 4 972 / 34 327 tet10, 0 Rückfälle, kleinste bezogene Determinante 0,162 / 0,065 /
0,067, keine inneren Punkte nötig.

Am Drehlager (nur vernetzt und gezählt, 3 Arbeitsprozesse, Kontaktfugen-Sperre für quadratische
Elemente umgangen — siehe Befund unten; gemessen 24.09.2026):

| | 18° | 36° |
|---|---|---|
| Elemente (tet10 + 64 Stäbe) | 670 185 | 496 617 |
| Knoten / Unbekannte (3 je Knoten, hergeleitet) | 1 100 877 / 3 302 631 | 805 993 / 2 417 979 |
| ungültige tet10 vor den örtlichen Anläufen (Körper) | 22 (3 Körper) | 160 (10 Körper) |
| örtliche Anläufe | 4 | 22 |
| Rückfälle auf gerade Kanten, eigene / gemeinsame Fläche | **0** / **0** | **17** / **0** |
| kleinste bezogene Jacobi-Determinante, vor Rückfall / im fertigen Netz | 0,001 / 0,001 | −7,0 / 0,000 (positiv, unter 0,0005; V35) |
| Lücken im Netzrand | 0 | 1 |
| Zeit | 334 s | 588 s |

Die sechs großen Platten (Elemente; ungültig je Anlauf; örtliche Anläufe; Rückfälle eigene /
gemeinsame; kleinste bezogene Determinante im fertigen Netz):

| Körper | 18° | 36° |
|---|---|---|
| V14 | 53 783; 0; 0; 0 / 0; 0,222 | 41 879; 5/4; 2; 0 / 0; 0,124 |
| V36 | 38 872; 0; 0; 0 / 0; 0,342 | 94 428; 2/5/3/3/3; 3; 0 / 0; 0,017 |
| V30 | 116 094; 0; 0; 0 / 0; 0,003 | 76 437; 6/2/5/5/3/2; 3; 2 / 0; 0,005 |
| V34 | 52 133; 2; 1; 0 / 0; 0,001 | 10 972; 1/1/1/2/1; 0; 0 / 0; 0,007 |
| V15 | 49 189; 1; 1; 0 / 0; 0,001 | 47 965; 30/7/8/12/3/3; 3; 3 / 0; 0,001 |
| V31 | 78 536; 0; 0; 0 / 0; 0,003 | 46 286; 16/10/8/8/1/1; 3; 1 / 0; 0,001 |

Zum Vergleich der Stand vor den drei Änderungen bei 18°: 687 807 Elemente, 1 126 316 Knoten,
572 ungültig in 4 Körpern, 11 Anläufe, 626 Rückfälle (5 gemeinsam), −11,4, 498 s; bei 36°:
491 511 Elemente, 588 ungültig in 9 Körpern, 279 Rückfälle (10 gemeinsam), −7,4, 290 s.
Bei 18° ist damit die Abnahme erreicht; bei 36° bleiben 17 Rückfälle an eigenen Flächen
(keine an gemeinsamen): 9 davon in fünf kleinen Körpern (V22, V28, V20, V25, V7), in denen der
Arbeitsprozess **kein** ungültiges tet10 sah — der Hauptprozess prüft nach dem Zusammenlegen der
Knoten auf gemeinsamen Flächen, und dort liegen die Ecken um Rundungsbeträge anders —, der Rest in
V30, V15, V31 und V35 nach drei örtlichen Anläufen, inneren Punkten und Entzerren. Und eine
Nebenwirkung der Reihung „erst ohne ungültige tet10“: für V36 wird bei 36° der feinste Anlauf
gewählt, weil erst er ohne ungültiges Element ist — 94 428 statt 11 304 Elemente; das ganze Netz
wächst so von 384 202 (Stand vor dem Entzerren, 19 Rückfälle) auf 496 617 Elemente. Ob ein
gültiges gekrümmtes Netz acht mal so viele Elemente eines Körpers wert ist, ist eine Entscheidung
für die Statik3D-Sitzung; die Stellschraube ist die Reihung in `koerper_vorbereiten`. Kleinste
bezogene Determinanten um 0,001–0,003 bleiben in den Platten mit den kleinen Bohrungen: gültig, aber
knapp — die Stelle für die adaptive Verfeinerung oder einen feineren Bogenwinkel an diesen Linien. **Befund für die Statik3D-Sitzung:** `fugen.QuadratischeSeiten`
bricht die Vernetzung des Drehlagers mit tet10 ab (Kontaktbedingung Lagerbock-Grundplatte an
3 065 quadratischen Elementen); für die Zählung wurde die Sperre umgangen, gerechnet wurde nichts.

**Kappenpunkte halten Abstand (23.09.2026 abends).** An der Bohrung der Buchse r 50/100
mit h = 20 mm behielten vier tet10 gerade Kanten, dazu stand eine Lücke von 0,0023 %
im Protokoll. Die Ursache war kein Bohrungsproblem: eine **Kappe im ebenen Deckel** —
vier Hüllpunkte, zwei am Bohrungsrand, zwei im Deckel, ein Splitter ohne Volumen —
bekam ihren Auflösepunkt um die halbe Kappenkante (bis 36 mm) senkrecht zum Deckel
nach innen geschoben; er landete 0,08 bis 2 mm neben der Bohrungswand, dort
entstanden Splitter mit Höhe 0,04 h, eine Delle im Netzrand und Tetraeder, deren
gekrümmte Bohrungskante die Jacobi-Determinante umklappte. Jetzt geht der Punkt
höchstens `KAPPEN_WEG` = 0,5 Sollgrößen weit und hält wie jeder Gitterpunkt
`KAPPEN_RANDABSTAND` = 0,4 Sollgrößen zur **ganzen** Hülle (`_kappenpunkte`). Damit
ohne weitere Nachhilfe: Hohlzylinder r 50/100, h = 35, 20, 10 mm — **0 Rückfälle**
auf gerade Kanten, kleinste bezogene Jacobi-Determinante 0,16 / 0,065 / 0,067, keine
Lücke (gemessen 23.09.2026). Test `test_kappenpunkte_halten_abstand`.

**Gekrümmte tet10-Kanten: örtlich feiner, bis sie gültig sind (V2, 23.09.2026
abends).** Bevor ein tet10-Körper eingebaut wird, prüft `krumme_kanten_pruefen` im
Arbeitsprozess dasselbe wie der Einbau: die Randkanten des Netzrands auf Zylinder,
Kegel, Kugel oder windschiefer Fläche bekommen ihre Mitte auf die wahre Fläche, und
jedes Tetraeder daran muss als tet10 an allen Integrationspunkten und Ecken eine
positive Jacobi-Determinante behalten (`jacobi_volumen_stapel`). Reißt nur das, wird
**nicht der Körper** feiner, sondern die betroffene Fläche: ihre Kantenlänge und die
ihrer nicht gemeinsamen Linien um `VERFEINERN_FAKTOR`, bis zu `KRUMM_ANLAEUFE` = 3
örtliche Anläufe (`koerper_vorbereiten`, „örtlich feiner vernetzt (MantelI1 13,3
statt 20,0 mm …)"). Eine gemeinsame Fläche gehört auch dem Nachbarn und kann ein
Arbeitsprozess nicht allein ändern — dort bleibt beim Einbau die gerade Kante, mit
Warnung und Grund. Gemessen 23.09.2026 an der Buchse mit **groben** Bögen (36° je
Abschnitt): h = 35 mm 5 ungültige tet10 → 0 (872 → 2 615 Elemente, Mantel 35 →
23,3 mm), h = 20 mm 5 → 0 (Bohrung 20 → 13,3 mm). Test
`test_krumme_kanten_oertlich_feiner`.

**Alle Hüllknoten auf der wahren Fläche (V2, tetp).** Gemessen 23.09.2026 an der
Buchse r 50/100 für 18° und 36° je Abschnitt und h = 50, 70, 100 mm: der größte
Abstand eines Hüllknotens von den Zylinderflächen ist **0,000 µm** — die Randpunkte
kommen von der Abwicklung (`_zylindernetz`), neue Hüllpunkte der Verfeinerung vom
Projektor. Für Kugelflächen (Achtel der Hohlkugel, drei Großkreisbögen) legte das
harmonische Heben die inneren Flächenpunkte bis **45 mm** (a = 100 mm) neben die Kugel —
die Fläche ist weit von jeder Ebene entfernt; seit 23.09.2026 werden alle ihre Punkte auf
die Kugel gesetzt (`_kugelpassung`). Und mit Größenfeld teilt die Linienteilung Bögen
ungleich: die Punkte kommen jetzt **genau** vom Kreis (Parameter = Bogenlänge) statt von
der feinen Näherung, die bis 7·10⁻⁸ m danebenlag (`_linienpunkte`, gemessen 24.09.2026).

**Projektoren: Zylinder, Kegel, Kugel, windschiefes Viereck (23.09.2026 abends).**
`flaechenprojektoren` kannte den Zylinder. `drehlager.json` hat daneben (gezählt
23.09.2026, `projektorarten`): **770 Zylinder, 8 Kegel** (Fasen und Senkungen: zwei
Bögen verschiedener Halbmesser um dieselbe Achse, `_kegelpassung`, Fußpunkt auf der
Mantellinie), **8 windschiefe Vierecke** aus vier Geraden (die bilineare Fläche, die
auch der Coons-Fleck aufspannt, Gauß-Newton in (u, v)) und 525 ebene Flächen; Kugel
oder Torus kommen nicht vor. Jede vorkommende Art ist abgebildet: die tet10-Seitenmitten
liegen auf Kegel und bilinearer Fläche (Kegelstumpf r 100 → 60 mm: 1,23 mm Sehnenpfeil
→ 0,000 mm; windschiefer Deckel z = 1 + 0,1 xy: 1,56 → 0,000 mm). Test
`test_projektor_kegel_und_windschief`.

**Bogenwinkel je Körper (V3, 23.09.2026 abends).** Der Winkel je Bogenabschnitt
(bisher fest 18°) ist einstellbar: `Netzeinstellungen.bogenwinkel` für das Modell,
`Volumenkoerper.bogenwinkel` je Körper; die Vorgabe des Körpers geht vor — auch nach
oben (36 statt 18°) —, an einer Linie zweier Körper mit verschiedener Vorgabe gilt
der **kleinere** Winkel, denn beide brauchen dieselbe Teilung; ein Körper ohne eigene
Vorgabe zählt dabei mit der des Modells (`bogenwinkel_je_linie`). Vorgabe bleibt 18°. Und
eine abgebildete Vierseitfläche (Zylindermantel) bindet ihre gegenüberliegenden Kreise an
dieselbe Teilung — der feinere zieht den gröberen mit (zwei gestapelte Zylinder, unten 36°,
oben 12°: alle drei Kreise 30 Knoten; `test_bogenwinkel_je_koerper`). Zylinder r = 100 mm: 20 Knoten auf dem
Grundkreis bei 18°, 10 bei 36°, 30 bei 12° (Test `test_bogenwinkel_je_koerper`).
Nebenbei: 180/36 ist in Gleitkommazahlen 5,000000000000001; ohne Toleranz bekam der
Halbkreis sechs statt fünf Abschnitte.

**Die Bohrungsplatte (Nachtrag zum dritten Auftrag, 24.09.2026).** Die Statik3D-Sitzung maß
an der Platte R 450 / t 35 mm mit Bohrung r 10 (24 Punkte) für h = 40 mm ohne „intelligent“
FEHLER „Seiten im Inneren 30“ und für h = 50 / 60 mm mit „intelligent“ WARNUNG „Riss im Netz“
mit 216 bzw. 440 Seiten. Drei Ursachen, drei Kuren: (1) `tetraedern_treu` wählte den besten
Durchgang nach dem **Fehlbetrag** — an der Bohrungswand nehmen weggenommene Kappen den
Rauminhalt ihrer Sehnenpfeile mit, und so gewann die vierte Runde mit 32 Dellen gegen die
sechste ohne Delle; jetzt zählen erst die echten Dellen, dann der Fehlbetrag. Ein Fehlbetrag
ohne Delle, den auch die Kappen nicht erklären, steht seither als eigene Warnung im Protokoll.
(2) Die **Rissseiten** waren die vier Seiten von Tetraedern ohne Rauminhalt (54 · 4 = 216,
110 · 4 = 440): vier Punkte in einer Ebene — zwei oben, zwei unten in der einlagigen Platte —,
die Qhull als Tetraeder ausgibt und die nach der Glättung als flach herausflogen, ihre Seiten
blieben als Hohlraum ohne Rauminhalt. `flache_aufloesen` teilt statt dessen die Pyramide
der beiden Nachbarn über die **andere Diagonale** (2-2-Tausch) — kein Hohlraum, kein Riss
(„kein Befund“ in allen drei „intelligent“-Zeilen). (3) Der **Kappenpunkt** hielt Abstand
nach der Sollgröße am Ort (an der Bohrung 3 mm) und stand 1,4 mm neben der Bohrungswand; jetzt
zählt die Größe der Kappe selbst (6 mm → 2,6 mm Abstand) — 16 statt 3 Kappen aufgelöst, 4
statt 17 entfernt. Ergebnis (gemessen 24.09.2026, Abnahme der Statik3D-Sitzung vom
23.09.): h 40 / 50 / 60 mm ohne „intelligent“ nur noch WARNUNG „Netzrand neben der Hülle“
(die Diagonaltausche der entfernten Kappen an der gewölbten Wand, 153 / 128 / 153 Seiten,
ohne Rauminhalt), mit „intelligent“ kein Befund.

**Flache Tetraeder nach eigener Größe (Nachtrag B101, 24.09.2026).** Was nach der
Glättung noch flach ist, fliegt heraus — bisher alles mit V ≤ FLACH·h³, h die Kantenlänge
des **Körpers**. An einer feinen Bohrung (Sehnen 2–7 mm bei h = 50 mm) traf das kleine,
gesunde Tetraeder mit 1,7 bis 11 % Dicke, und die Abnahme meldete dort einen Riss (Befund der
Statik3D-Sitzung am Stand `ec6448c`). Jetzt zählt die Form: V ≤ FLACH·L³ mit der eigenen
längsten Kante L (`flache_tetraeder`); V/L³ ist beim regelmäßigen Tetraeder 0,118, bei einem
Splitter der Dicke t etwa 0,14 t/L, unter 10⁻⁶ liegt nur, was wirklich flach ist. Ein
3-mm-Tetraeder mit 2 % Dicke bleibt, einer mit 10⁻⁷ Dicke fliegt (Test
`test_flache_tetraeder_nach_eigener_groesse`; die Platte R 450 / Bohrung r 10 / t 35 mm mit
h = 50 mm hat auf diesem Stand weder Riss noch Lücke). Zu den beiden anderen Nachtragspunkten:
die neuen Hüllpunkte der Verfeinerung liegen mit den Projektoren auf der Fläche — am Würfel mit
windschiefem Deckel (dz 0,5, h 0,25 und 0,1) 0,000 mm daneben statt 7,55 mm (B102); der Würfel
mit stark angehobener Deckelecke (dz 1,2 / 1,5 / 2,0 / 3,0, h 0,1) hat auf diesem Stand keine
Löcher mehr — 15 625 Stichprobenpunkte im Körper, jeder in einem Tetraeder, Rauminhalt bis
0,03 % neben dem exakten 1 + dz/4 (B103, beides gemessen 24.09.2026).

**Einbaufolge (23.09.2026).** Die Körper werden parallel vernetzt, eingebaut aber in
der **festen** Folge der Körperliste, nicht in der des Fertigwerdens: die Knoten- und
Elementnummern entstehen beim Einbau, und zwei Läufe derselben Datei — oder zwei
Maschinen mit verschiedener Kernzahl — müssen dieselben Nummern ergeben. Am Drehlager
behielten vorher 18 von 3 731 Knoten ihre Nummer zwischen zwei Läufen (Statik3D-
Sitzung). Geprüft mit zwei verschieden feinen Körpern Knoten für Knoten
(`test_nummern_haengen_nicht_am_prozess`); die Stückzahl allein stimmte auch vorher.

**Randknoten und Seitenmitten auf der wahren Fläche (V2, 23.09.2026).** Die Hülle sind
Facetten; ein Punkt mitten auf einer Facette liegt um den Sehnenpfeil neben der Geometrie
(18° je Bogenabschnitt: r·(1 − cos 9°) = 1,23 % des Halbmessers). Für tet4 ist das die
übliche Facettierung. Für gekrümmte Elemente nicht: eine einzige gerade gebliebene
Bohrungskante ließ das Element höchster Ordnung an der Nachweisstelle 23 N/mm² danebenliegen
(Element-Sitzung, gemessen 23.09.2026). Darum gibt es je Randfläche eine Abbildung auf ihre
wahre Fläche (`flaechenprojektoren`, heute der Zylinder aus `zylinderpassung`, radial), und
sie wirkt an zwei Stellen: die **neuen Hüllpunkte** der Nachführung (`huelle_verfeinern`:
Kantenmitte und Schwerpunkt) landen auf dem Zylinder statt auf der Sehne, und die
**Seitenmitten der tet10** auf Randkanten (`_seitenmitten_auf_flaeche`) ebenso — die
Randkanten kommen dabei aus dem Netzrand selbst, nicht aus den Hülldreiecken, weil die
Zerlegung ein Hüllviereck über die andere Diagonale teilen darf. Danach wird jedes berührte
Element geprüft: die Jacobi-Determinante muss an allen Integrationspunkten positiv bleiben
(`solid.jacobi_volumen`); wo nicht, bleibt die Kante gerade, und das Protokoll nennt die
Elemente („4 tet10 behalten gerade Kanten … Elemente [5059, 5061, 5062, 5063]; dort feiner
vernetzen"). Gemessen am Hohlzylinder r = 50/100 mm der Element-Sitzung: h = 35 mm — alle
1 042 Randkanten-Mitten auf dem Zylinder (vorher bis 1,231 mm daneben), kleinste bezogene
Jacobi-Determinante 0,162, kein Rückfall; h = 20 mm — 727 gesetzt, 4 Rückfälle an Splittern
der Bohrung. Der Nachtrag verlangt dort örtliche Verfeinerung statt der geraden Kante; das
steht noch aus, der Rückfall ist laut.

**Ordnung je Körper (V1, 23.09.2026).** `Volumenkoerper.ordnung` (1 oder 2) geht vor
der Netzeinstellung (`mesher.koerper_ordnung`). Ein Körper mit Ordnung 2 bekommt
tet10 und geht dafür an den freien Vernetzer, auch wenn er sonst abgebildet oder
gesweept würde — Sechsflächner zweiter Ordnung neben tet4-Nachbarn koppelt heute
niemand. An der gemeinsamen Fläche stimmen die Eckknoten überein; die Mittenknoten
koppelt `assemble.mittelknoten_bindungen` (Element-Sitzung). Umlauf geprüft:
speichern, laden, dieselbe Elementliste (`test_ordnung_je_koerper`).

**Randseiten je Fläche.** Auf der Randfläche eines Volumenkörpers gibt es
keine Schalenelemente; Flächenlasten, Kontaktfugen und Flächenlager brauchen
darum die Paare (Tetraeder, Seite), die auf der Fläche liegen
(`Flaeche.randseiten`). Gegangen wird vom Netz aus: jede freie Elementseite
sucht unter ihren acht nächsten Hülldreiecken das, das sie **überdeckt** —
alle drei Seitenknoten liegen in der Ebene des Hülldreiecks (Abstand ≤ 10⁻³
der Kantenlänge) und die Normalen sind parallel (|n·n_h| > 0,9); unter
diesen das nächste. Die Nähe allein reicht nicht: an einer dünnen Platte
liegen die Seitenfacetten der Schmalseite näher an der Deckfläche als ein
Viertel der Kantenlänge und hingen früher an ihr — die Deckfläche trug dann
36 % zu viel Fläche (Test `test_duenne_platte_randseiten`). Nur wenn kein
Dreieck überdeckt (Randknoten nicht exakt auf der Hülle), gilt der Rückfall
über die Nähe — und auch der nur, wenn die Seite **beinahe** in der Ebene des
Hülldreiecks liegt (Abstand aller drei Knoten ≤ ein Viertel der Kantenlänge)
und die Normale nicht quer steht. Ohne diese Schranke schluckt der Rückfall
die schrägen Seiten, die im Inneren stehenbleiben, wo eine flache Zerlegung
einen Splitter weggelassen hat: an derselben dünnen Platte hing damit eine
Seitenwand 7 % zu groß am Rand, und ob sie es tat, hing an der Reihenfolge
der Knotennummern.

**Gemeinsame Randflächen.** Zwei Körper, die *dieselbe* Fläche berandet,
bekommen dort dieselben Knoten und hängen zusammen. Geteilt wird ausdrücklich
über die Fläche, nicht über die Koordinate: zwei Flächen, die aufeinander
liegen, aber verschiedene Objekte sind, gehören zu einer Kontaktfuge und dürfen
**nicht** verschweißt werden.

Damit das hält, müssen drei Dinge stimmen; an jedem einzelnen fiel die Fuge
schon auseinander, und von außen sah das Netz jedesmal tadellos aus.

1. **Geschlüsselt wird nach der Herkunft des Punktes**, nicht nach „der ersten
   Fläche, die ihn benutzt". Ein Punkt auf einer gemeinsamen *Randlinie*
   gehört zu zwei oder mehr Flächen des Körpers; welche davon die erste ist,
   entscheidet die Reihenfolge der Randflächenliste — beim Import eine
   beliebige. Ein Linienpunkt heißt darum `(Linie, k)` in der eigenen
   Zählrichtung der Linie, eine Ecke nach ihrem Knoten. Nachgemessen an zwei
   Prismen mit gemeinsamer Fläche: **15 der 33** Fugenknoten waren doppelt,
   nur weil in einem der beiden Körper eine Seitenfläche vorn in der Liste
   stand.
2. **Die Kantenlängenkarten gelten modellweit**, und der parallele Vernetzer
   bekommt sie mit. Ein Arbeitsprozess sieht immer nur *einen* Körper und
   könnte sie nicht bilden; ohne sie bildete jeder seine Teilung selbst.
   Wandte nur einer sein Dickenmaß an, teilte er die gemeinsame Linie feiner
   als der Nachbar — **13 der 33** Fugenknoten hingen dann frei in der Luft.
   Die Karten entstehen **einmal je Lauf** (0,8 s am Drehlager) und gehen an
   jeden Pfad: an die Arbeitsprozesse, an die seriell vernetzten Körper und
   an die, die abgebildet begonnen haben und doch beim freien Vernetzer
   landen. Bis zum 10.09.2026 bildete jeder dieser Körper sie neu — am
   Drehlager 48 Körper × 1,5 s = 36 s in der seriellen Phase vor dem
   Parallelbetrieb (`test_karten_einmal_je_lauf`).
3. **Eine gemeinsame Fläche oder Linie darf kein Körper allein ändern.** Die
   Karte ist für sie bindend; für eigene Flächen ist sie nur eine Obergrenze,
   sonst könnte die Nachvernetzung gar nichts mehr ausrichten. Auch die
   Nachteilung bei offener Hülle und das Nachführen der Hülldreiecke
   (`tetraedern_treu`) lassen gemeinsame Flächen unangetastet und melden das,
   statt still zu trennen.

Geprüft wird das nicht nur beim Bauen: die Abnahme vor dem Rechnen
(*gemeinsame Fläche*) misst je Körperpaar die Randknoten des einen, die auf
dem Rand des anderen liegen, und verlangt dieselben Knotennummern. Doppelte
(gleicher Ort, andere Nummer) und hängende (kein Partner) werden getrennt
genannt, weil sie verschiedene Ursachen haben.

**Splitter.** Das Kugel-Kanten-Kriterium erfasst jede schlechte Form außer
einer: vier fast in einer Ebene liegende Knoten können eine ganz gewöhnliche
Umkugel haben. Solche *Splitter* sind fast singulär und verderben die
Kondition der Steifigkeitsmatrix. Sie werden nachträglich herausgeglättet
(*smart Laplacian* mit Mustersuche): ein freier Knoten wandert versuchsweise in
den Schwerpunkt seiner Nachbarn und in zwölf Richtungen um seinen Platz herum,
und der beste Schritt wird nur behalten, wenn die **schlechteste** Güte seiner
Elemente danach höher ist und kein Element umklappt. Randknoten stehen fest —
sie sind die Geometrie, und so bleibt das Volumen unverändert.

Welche Knoten das sind, wird aus dem **Verband** gelesen und nicht aus der
Punktnummer geraten: fest ist jeder Knoten, der zu einer Seitenfläche gehört,
die nur zu einem Tetraeder zählt. Damit das genau die Hülle ist und kein
Schlitz im Inneren, bleiben die **flachen Tetraeder** (Volumen unter
FLACH · h³) bis nach der Glättung im Netz. Vorher flogen sie zuerst heraus,
und an ihrer Stelle blieb ein volumenloser Schlitz, dessen Knoten
festzuhalten waren, weil sie ihn sonst aufzögen (an einer 2 × 2 m großen
Platte mit Bohrung: acht Knoten, drei verschoben, 0,39 ppm Volumenänderung).
Festgehalten blockierten sie aber die Glättung daneben: am 10.09.2026 blieb
an derselben Platte (26 988 Tetraeder, Windows) ein Splitter der Güte 0,0058
stehen, weil zwei seiner Knoten auf dem Bohrungsmantel und zwei auf so einem
Schlitz lagen. Bleibt der flache Tetraeder drin, ist das Netz eine Zerlegung
ohne Lücke: die Glättung darf seine Knoten bewegen, das Volumen ist von
selbst erhalten, und was danach noch flach ist, wird erst dann aussortiert;
das Protokoll nennt die Zahl. Gemessen an der Platte mit Bohrung: 197 flache
Tetraeder aus der Zerlegung, 6 davon repariert und jetzt Elemente, die
Volumensumme um 1,5 · 10⁻⁸ m³ größer (ihr früher fehlendes Volumen; Schranke
197 · FLACH · h³ = 1,3 · 10⁻⁶ m³), die schlechteste Güte von 0,0058 auf 0,102
(Linux, wo die Zerlegung leicht anders liegt: von 0,0035 auf 0,102), und kein
Element bleibt unter 0,1 (`test_splitter_glaetten`). Ein flacher Tetraeder
mit genau null Volumen hat keine Orientierung; seine Knoten rührt die
Glättung nicht an, weil der Umklapptest jeden Schritt verwirft. Darum bleiben
191 der 197 flach und fliegen danach heraus — wie vorher, nur später. Wo alle
vier Knoten eines Splitters auf der Hülle liegen, lässt er sich nicht glätten;
seine Zahl steht dann im Protokoll.

**Lineare und quadratische Tetraeder.** `Netzeinstellungen.ordnung` wählt
zwischen `tet4` (linear, konstante Dehnung) und `tet10` (quadratisch). Die
Seitenmittenknoten liegen auf den Kantenmitten und werden über das *Knotenpaar*
gemerkt: benachbarte Elemente und Körper mit gemeinsamer Randfläche bekommen
denselben Knoten, an einer Kontaktfuge verschiedene. Der Unterschied ist groß —
ein Kragträger 0,2 × 0,2 × 2,0 m mit derselben Kantenlänge von 100 mm:

| | tet4 | tet10 |
|---|---|---|
| Elemente | 1143 | 1143 |
| Knoten | 285 | 1874 |
| Endverschiebung | 69,5 % der Balkenlösung | 99,0 % |

Der lineare Tetraeder versteift (*locking*); erst bei 50 mm kommt er auf 91 %.
Beide bestehen dagegen den Patchtest exakt: unter einem linearen
Verschiebungsfeld bleibt die Restkraft an jedem inneren Knoten unter 1e-8 N.

**Knotengemittelte Dilatation** (`Model.knotendilatation`, 20.09.2026). Die
Versteifung des `tet4` hat zwei Ursachen, und eine davon lässt sich beheben.
Die **volumetrische** entsteht, weil das Element konstante Dehnung hat: es kann
die Volumenänderung nicht unabhängig von der Gestaltänderung darstellen. Je
näher die Querdehnzahl an 0,5 kommt, desto stärker sperrt es — und genau
dorthin läuft der Werkstoff beim Fließen, denn von-Mises-Fließen ist
volumentreu.

Der Ausweg ist **nicht** elementlokales B-bar: der volumetrische Anteil eines
linearen Tetraeders ist schon konstant, da gibt es nichts zu mitteln. Gemittelt
werden muss über den Verband der Elemente an einem Knoten. Mit
mᵀ = (1, 1, 1, 0, 0, 0), dem Kompressionsmodul K = E/(3(1−2ν)) und der
Volumendehnungszeile mᵀBₑ jedes Elements:

    n_I   = Σ_e (K_e V_e / 4) · mᵀBₑ          (Zeile über die FHG des Verbands)
    w_I   = Σ_e (K_e V_e / 4)
    K_vol = Σ_I (1 / w_I) n_Iᵀ n_I

dazu der deviatorische Anteil je Element, K_dev,e = Vₑ Bₑᵀ D_dev Bₑ mit
D_dev = D − K m mᵀ. Die Aufspaltung D = D_dev + K m mᵀ ist exakt (geprüft auf
0,0 bei ν = 0; 0,2; 0,3; 0,45; 0,499); gehört zu einem Knoten nur **ein**
Element, fällt K_vol genau auf Kₑ Vₑ (mᵀBₑ)ᵀ(mᵀBₑ) zurück, also auf den
gewöhnlichen Tetraeder (gemessen: 1,1e−16 relativ). Die Spannung rechnet mit
derselben gemittelten Volumendehnung, σ = D_dev εₑ + K ε̄ᵥ m — Kräfte und
Spannungen kommen so aus derselben Energie.

Gemessen am Kragträger 0,2 × 0,2 × 2,0 m mit 480 Tetraedern, gegen die
Balkenlösung:

| ν | gewöhnlich | knotengemittelt | |
|---|---|---|---|
| 0,300 | 51,0 % | 67,2 % | 1,3× |
| 0,450 | 30,2 % | 62,4 % | 2,1× |
| 0,490 | 10,6 % | 58,5 % | 5,5× |
| 0,499 | **2,1 %** | **51,1 %** | **23,9×** |

Bei ν = 0,499 ist der gewöhnliche Tetraeder praktisch starr. Zwei Dinge gehören
dazu gesagt:

* **Die Schubversteifung bleibt.** Deshalb 67 % statt der 99 % des `tet10` bei
  ν = 0,3. Ein Element mit konstanter Dehnung kann Biegung nicht abbilden;
  dagegen hilft nur ein feineres Netz oder ein quadratisches Element.
* **Der Preis steht in der Matrix**, und er wächst mit dem Modell. Der Verband
  koppelt Knoten, die vorher nichts miteinander zu tun hatten — Einträge je
  Zeile, gemessen an Würfeln aus Kuhn-Zellen:

  | Elemente | ohne | mit | |
  |---|---|---|---|
  | 1 296 | 17,7 | 57,9 | 3,3× |
  | 6 000 | 19,4 | 69,9 | 3,6× |
  | 16 464 | 20,2 | 75,5 | **3,7×** |

  Am dünnen Kragträger sind es nur 2,6× — dort hat jeder Knoten weniger
  Nachbarn. Die Füllung der Faktorisierung wächst überproportional mit der
  Bandbreite, der Aufwand also stärker als der Faktor 3,7. Ob sich das lohnt,
  entscheidet der Einzelfall — ein gröberes Netz, das dieselbe Genauigkeit
  liefert, macht den breiteren Stern mehr als wett. Der Aufbau von K_vol selbst
  ist blockweise gerechnet und kostet 5,2 µs je Element (646 706 tet4 also
  3,4 s je Aufstellen der Steifigkeit).
* **Die Versteifung ist gemindert, nicht behoben.** Auch volumetrisch bleibt
  ein Rest: die Formulierung ist ein unstabilisiertes P1/P1-Paar und erfüllt
  die LBB-Bedingung nicht. Sichtbar in der eigenen Tabelle — 67,2 % bei
  ν = 0,3 gegen 51,1 % bei ν = 0,499.
* **Der Knotenverband endet an der Werkstoffgrenze.** Je Knoten **und
  Werkstoff** eine Zeile: die Volumendehnung springt dort, und eine gemeinsame
  gemittelte Dehnung erzwänge eine Stetigkeit, die es nicht gibt. Gemessen an
  einem Zugstab aus Stahl und Elastomer (E = 5 MPa, ν = 0,499, 384 tet4 mit
  geteilten Knoten): über die Grenze gemittelt lag σ_xx im Stahl zwischen
  −24,3 und +18,8 mal F/A — mit falschem Vorzeichen; je Werkstoff getrennt
  zwischen 0,78 und 1,18.
* **ν ≥ 0,5 wird abgewiesen, nicht stillschweigend übergangen.** Der
  Kompressionsmodul E/(3(1−2ν)) ist dort nicht endlich und positiv. Ohne
  Prüfung hätte das Element seinen deviatorischen Anteil bekommen und keinen
  volumetrischen zurück — die Steifigkeit hätte sich um 109 % ihres größten
  Eintrags geändert, ohne eine Meldung. Solche Bauteile rechnen mit dem
  gewöhnlichen Tetraeder weiter. **Gesagt wird es seit dem 24.09.2026 im
  Ergebnis** (`res.info["dilatation_hinweise"]`, je Werkstoff mit der Zahl der
  betroffenen tet4), in der Zusammenfassung und in den Hinweisen des Berichts
  (`solver.dilatation_gebuendelt`). Vorher ging es nur über `warnings.warn` und
  erreichte weder Protokoll noch Bericht noch die exe (Befund B032). Die Regel
  verlangt 0 ≤ ν < 0,5; bei ν = 0,5 rechnet schon der gewöhnliche tet4 nicht (laut,
  mit Elementnummer), geprüft ist die Meldung darum mit ν = −0,1
  (`tests/test_dilatation.py`).
* **Temperatur- und Anfangsspannungslasten bleiben elementlokal.** Bei
  gleichmäßiger Erwärmung ist das exakt (gemessen 0,00 MPa, ν = 0,3 und
  0,499); bei veränderlichem Feld ist die äquivalente Last nicht das
  variationelle Gegenstück zur gemittelten Steifigkeit.
* **Die Elementmatrizen anderer Typen bleiben unverändert** — aber in einem
  **gemischten** Netz ändert sich ihre Lösung mit, weil sie Knoten mit
  Tetraedern teilen. Der Satz „nur tet4 ist betroffen“ gilt für die
  Elementmatrix, nicht für das Ergebnis.

Der Patchtest bleibt exakt (gestörtes Netz, 8 innere Knoten: Restkraft
3,4e−15 relativ bei ν = 0,3 und 1,0e−15 bei ν = 0,499), das Gleichgewicht steht
(300 000,0 N gegen 300 000,0 N), und die mittlere Spannung trifft F/A exakt.
Betroffen ist allein `tet4`; alle anderen Elementtypen rechnen unverändert
(geprüft an einem `hex8`-Netz: 0,0). Geprüft in `tests/test_dilatation.py`.

**Grenzen.** Ist eine Zielkantenlänge für ein Bauteil zu grob (weniger als vier
Elemente über seine größte Ausdehnung), wird sie für dieses Bauteil verkleinert
und das gemeldet.

**Größenfeld (`netzfeld.py`, 20.09.2026).** Bis hierher ist die Feinheit eine
Funktion der Hülle: `h_lokal = min(h, Randkante + WACHSTUM · Abstand)`. Es gab keinen
Kanal, über den eine benannte Stelle oder ein Rechenergebnis die Feinheit setzen
konnte. Das **Größenfeld** ist dieser Kanal — eine Wolke von Quellen (Ort x_k,
Kantenlänge h_k, Reichweite r_k), ausgewertet als

    h(x) = min( h_max, min_k [ h_k + WACHSTUM · max(0, |x − x_k| − r_k) ] ).

Weil jede Quelle mit derselben Steigung 0,35 kegelförmig wirkt, ist das Feld von sich
aus gradiert. Die Auswertung geht über die zwölf nächsten Quellen und ist trotzdem
**exakt**: die Lipschitz-Schranke R = (v₁ − h_min)/g + r_max sagt, bis wohin eine
fernere Quelle noch unter den gefundenen Wert v₁ käme; reicht die Suche nicht bis R,
werden alle Quellen bis R geholt. Gemessen an 600 000 Zufallsquellen mit h von 3 bis
70 mm: Abweichung zur Auswertung über alle Quellen 0,00 %, 300 000 Auswertungen 1,0 s
(mit zwölf Nachbarn ohne Schranke wären es bis 18 % gewesen). Überdeckte Quellen
werden vorab entfernt — eine Quelle, deren Kegel überall höchstens 5 % über dem
einer anderen liegt, ändert am Netz nichts; das hält das Feld nach oben um höchstens
diese 5 % (gemessen 0,15 %) und braucht für 200 000 Quellen 0,6 s.

Die Quellen kommen aus den Netzeinstellungen: **Netzverfeinerungen** (Kugel um einen
Punkt, benannte Fläche, Linie oder Körper mit Kantenlänge) und **Feldpunkte**, die der
Fehlerschätzer schreibt (§ 6c). Das Feld hängt am Modell (`model.groessenfeld`), wird
einmal je Lauf gebildet und geht mit dem Modell in die Arbeitsprozesse; gespeichert
werden nur seine Quellen. Es wirkt an allen vier Stellen, an denen die Feinheit
entsteht — denn die Hülle ist der Hebel (3,4 Tetraeder je Randdreieck am Drehlager):

| Stelle | Weg |
|---|---|
| Linien | Zahl der Abschnitte aus ∫ ds / h(s) längs der Linie, die Punkte an gleichen Bruchteilen dieses Integrals — dicht, wo das Feld fein ist (Linie 1 m, h = 50 mm, Kugel 10 mm in der Mitte: 33 statt 20 Abschnitte, 9,9 mm an der Kugel, 49,4 mm am Ende). Beide Körper einer gemeinsamen Linie lesen dasselbe Feld und bekommen dieselben Punkte |
| Flächen | das gleichmäßige Dreiecksgitter wird wie in einem Quadtree verdichtet, wo das Feld unter 70 % der Zellweite fällt (vier Kinder halber Weite, bis acht Stufen), dann auf die Feldweite ausgedünnt und **geglättet**: jeder Innenpunkt wandert um den halben Schritt zum Schwerpunkt seiner Nachbarn, behalten wird nur, was die schlechteste Güte seiner Dreiecke bessert (Quadrat 1 × 1 m, h = 100 mm, geteilter Rand, 20-mm-Stelle: Güte min 0,65 → 0,79 in der Mitte, 0,24 → 0,52 an der Ecke, Stufenfeld 0,22 → 0,35) |
| Tetraeder | dritte Schranke der Sollgröße neben h und der Randkantenregel; die Verfeinerung selbst bleibt (Platte, Kugel 15 mm bei h = 100 mm: 11,9 mm in der Kugel, 79 mm im Feld, Güte min 0,114) |
| gmsh / MMG3D | gmsh bekommt einen Größen-Rückruf mit derselben Sollgröße; MMG3D die Kantenlänge je Knoten als Metrik (`.sol`) und passt das Innere bei fester Hülle an (Quader, Hülle 50 mm, Kugel 5 mm: 12,8 mm im Ziel, Güte min 0,507, 0,4 s). **Der gmsh-Rückruf ist keine Zusage:** an der Platte mit 100-mm-Hülle traf HXT die 10-mm-Kugel je Prozesszustand mit 14,5 oder 38,5 mm — bei identischen Fragen und Antworten bis zur 579. Anfrage; die Abweichung entsteht in gmsh, die Ursache ist nicht gefunden. Verlässlich ist die Metrik von MMG3D; ohne sie warnt das Protokoll |

**Bedeutung der Flächen — Nebenflächen grob.** Am Drehlager stammen 85 % der Elemente
aus acht Körpern, alle mit derselben Ziellänge 50 mm; ihre Elementzahl kommt aus der
Hülle, und die Hülle aus Bohrungen und Ausrundungen mit 18° je Bogenabschnitt — ob die
Bohrung etwas trägt oder nicht. `netzfeld.bedeutung` unterscheidet: **bedeutend** ist
eine Fläche mit Last, Lager, Kontaktbedingung, integriertem Knoten, Netzverfeinerung
oder einem zweiten Körper (gemeinsame Fläche); alles andere ist **Nebenfläche**. Mit
`netz.nebenflaechen_grob` bekommen die Linien der Nebenflächen 45° je Bogenabschnitt
(acht statt zwanzig je Vollkreis). Gemessen an der Platte 1 × 0,6 × 0,2 m mit einer
Bohrung r = 100 mm und vier Durchgangsbohrungen r = 20 mm, h = 50 mm: Randdreiecke
5 384 → 2 260, Tetraeder 40 364 → 17 969, Knoten 7 641 → 3 412, geschätzter Fehler
11,9 → 12,8 %. Der Preis steht daneben: die größte Vergleichsspannung fiel von 490 auf
343 N/mm², weil die große Bohrung hier weder Last noch Kontakt hat und damit
Nebenfläche ist. Darum ist die Vorgabe **aus** — eingeschaltet wird sie von der
adaptiven Vernetzung (§ 6c), die zurückholt, was doch trägt, und vom Anwender, der
weiß, wo er den Nachweis führt.

**Kappen.** Ein Splitter, dessen vier Ecken alle auf der Hülle liegen — zwei
Nachbardreiecke einer gewölbten Wand, zu einem fast flachen Tetraeder verbunden —, ist
für die Verfeinerung unsichtbar (der Umkugelmittelpunkt liegt im Nirgendwo und wird
verworfen, alle Kanten sind ähnlich lang) und für die Glättung unerreichbar
(Hüllknoten stehen fest). An der Bohrungswand einer Platte blieben so Tetraeder mit
Güte 0,005 bis 0,011 durch drei Anläufe der Nachvernetzung stehen (20.09.2026). Zwei
Schritte: erst ein Punkt im Schwerpunkt, um die halbe Kante nach innen geschoben — er
liegt in der riesigen Umkugel und zerlegt die Kappe (Platte, adaptive Runde: 60
Kappen). Wo das nicht greift — auf einer Wand, die vom Körper aus **hohl** ist, ragt die
Umkugel nur um den Sehnenpfeil in den Körper (bei 24-mm-Sehnen auf r = 40 mm knapp
1 mm) —, wird die Kappe **entfernt**: das ist der Diagonalwechsel des Hüllvierecks, die
Knoten bleiben, die Oberfläche ist um den Sehnenpfeil gedellt, dem Netz fehlt der
Rauminhalt der Kappe (Platte 2 × 2 × 0,4 m mit Bohrung: zwei Kappen, 5,8·10⁻⁶ von
1,40 m³). Entfernt wird nur, was mindestens zwei freie Seiten hat — ein Splitter
**zwischen** anderen Tetraedern (in einer dünnen Platte hat fast jeder Tetraeder Knoten
oben und unten) bliebe sonst als Hohlraum zurück — und dessen Knoten alle in anderen
Tetraedern stehen. Das ist der Weg zu einem Netz ohne Splitter; das Protokoll nennt
Zahl und Rauminhalt.

**Sweep: Grundfläche mal Weg (`sweep.py`, 20.09.2026).** Der lineare Tetraeder ist
zum Teil aus Abzählung schlecht: am Drehlager stehen 645 934 Tetraeder auf 158 586
Knoten, 4,07 Elemente je Knoten; Volumentreue ist eine Bedingung je Element, also
4,07 Bedingungen auf 3 Verschiebungen je Knoten — das Netz versteift sich selbst, und
beim Fließen (volumentreu) erst recht. Ein Hexaedernetz hat rund ein Element je Knoten,
ein Keilnetz rund zwei; keines von beiden sperrt so. Darum wird ein Körper, der sich
als **Grundfläche mal Weg** beschreiben lässt, gesweept statt frei vernetzt — Platte,
Ring, Flansch, Rippe, Lasche mit Bohrungen: fast alles, was aus einer Skizze
extrudiert wurde.

Erkannt wird das an der Randdarstellung: zwei ebene Flächen, von denen die eine die
um einen Vektor t verschobene Kopie der anderen ist (Außenrand und Öffnungen, Punkt für
Punkt), und jede weitere Fläche eine Wand aus vier Linien — eine Linie des Grundes, ihre
Kopie im Deckel, zwei gerade Mantellinien längs t (der Bohrungsmantel aus RFEM ist aus
zwei solchen Vierseitflächen gebaut). Das Netz der Grundfläche kommt aus dem
vorhandenen Flächenvernetzer (Dreiecke); benachbarte Dreiecke werden **zu Vierecken
gepaart**, gierig nach der Güte des Vierecks (skalierte Jacobi-Determinante, mindestens
0,3), der Rest bleibt Dreieck. Dann wird in Lagen durchgezogen: Viereck → `hex8`,
Dreieck → `pent6`. Die Zahl der Lagen folgt aus Weg und Kantenlänge (mindestens zwei,
`sweep.LAGEN_MIN`; wird Fließen gerechnet, mindestens vier, `LAGEN_MIN_PLASTISCH`, Messung
unten) — **nicht** aus der Kartenteilung der Mantellinien: die Regel „eine
Linie neben einer feineren" teilt die Mantellinie neben einer feinen Bohrungssehne für
den Tetraeder fein (Platte mit Bohrungen: 10 Lagen statt 4, Kragplatte 4 473 statt
1 491 Knoten); für Hexaeder und Keile ist die Teilung je Richtung frei, das ist gerade
ihr Vorzug. Gehört eine Mantellinie einem zweiten Körper, gilt dessen Teilung für alle
Lagen — und weil die Teilung einer Linie im Modell nur eine ist, werden die Lagen aller
sweepbaren Körper **vorab und modellweit** festgelegt (`sweep.lagenvorgabe`, abgelegt als
`model.linienvorgabe`, gelesen von jeder Linienteilung, auch der der Nachbarn): das
Größte aus Weg/h, der Mindestlagenzahl und der Kartenteilung der *gemeinsamen*
Mantellinien; die eigenen teilt der Sweep frei. Ohne das fiel der Sweep dort aus, wo er
am Drehlager überhaupt greift: `erkennen` fand V18 und V11 (je sieben Wände, Weg 40 mm,
h = 50 mm, zusammen 2 864 Elemente), `vernetzen` lieferte für beide **null** Elemente —
„die Mantellinien gehören zweiten Körpern mit verschiedener Teilung" (Zählung der
Löser-Sitzung, 21.09.2026). Nachgestellt an einer Platte, deren Wand einer Pyramide
gehört und an deren einer Mantellinie eine Kugel des Größenfelds sitzt: ohne Vorgabe
Tetraeder, mit Vorgabe fünf Lagen (so fein teilt die Kugel AV1), Abnahme ohne Befund, alle 48 Wandknoten der Pyramide
sind Knoten der Platte (`test_nachbar_mit_verschiedener_teilung`). Eine Linie mit
Vorgabe zählt wie eine gemeinsame: kein Körper teilt sie allein feiner. Randseiten
werden nicht gesucht, sondern gesetzt: Grund, Deckel und je Wand die Elementseiten längs
der Randkanten. Der Rauminhalt ist Grundfläche mal Höhe und wird gegen die Elemente
geprüft.

Gemessen (20.09.2026, h = 50 mm, ein Prozess):

| Platte 1 × 0,6 × 0,2 m | Elemente | Knoten | je Knoten | Güte min | Netz | \|u\| max | σ_v max |
|---|---|---|---|---|---|---|---|
| Bohrungen r = 100 und 20 mm, tet4 | 20 608 | 3 925 | 5,25 | 0,101 | 0,9 s | 0,560 mm | 340 N/mm² |
| dieselbe, Sweep (4 Lagen) | 1 380 hex8 + 264 pent6 | 2 145 | **0,77** | 0,233 | 0,3 s | 0,568 mm | 237 N/mm² |
| fünf Bohrungen, tet4 | 40 364 | 7 641 | 5,28 | 0,101 | 2,7 s | 0,566 mm | 490 N/mm² |
| dieselbe, Sweep (4 Lagen, 87,6 % Hexaeder) | 2 876 hex8 + 408 pent6 | 4 240 | 0,77 | 0,194 | 0,4 s | 0,574 mm | 239 N/mm² |

Kein umgestülptes Element, Rauminhalt exakt, Abnahme ohne Befund. Die Verschiebungen
stimmen auf 1 % überein; die größte Vergleichsspannung am Bohrungsrand liegt beim
Tetraedernetz um die Hälfte bis das Doppelte höher — welcher Wert der Wahrheit näher
ist, sagt erst ein konvergiertes Netz; hier steht nur, dass die Netze dort verschieden
antworten.

Die Probe, um die es dem Auftrag geht, ist die **Kragplatte** 1 × 0,2 × 0,05 m mit
10 kN Endlast (kleine Bohrung am freien Ende, damit sie kein Quader ist), h = 25 mm,
gegen Bernoulli mit Schubanteil (7,634 mm):

| | Elemente | Knoten | Endverschiebung |
|---|---|---|---|
| tet4, 2 Lagen | 15 720 | 3 128 | 5,218 mm = **68,4 %** |
| Sweep, 2 Lagen | 848 hex8 + 60 pent6 | 1 491 | 7,448 mm = **97,6 %** |

Der Hexaeder mit inkompatiblen Moden trägt die Biegung mit zwei Lagen; der lineare
Tetraeder bleibt bei zwei Lagen um fast ein Drittel zu steif — mit weniger als der
Hälfte der Knoten.

**Ein Keil ist kein halber Sechsflächner.** Der `hex8` trägt Biegung über inkompatible
Moden (Taylor/Beresford/Wilson), der `pent6` hat sie nicht — er läuft über die reine
isoparametrische Formulierung. Am **identischen Knotengitter** gemessen (Statik3D-Sitzung,
22.09.2026, Kragarm 1,0 × 0,1 × 0,2 m gegen die Balkenlösung mit Schub; jeder Würfel
wahlweise als ein `hex8` oder als zwei `pent6`):

| Gitter | Knoten | `hex8` | `pent6` | der Keil ist steifer um |
|---|---|---|---|---|
| 4 × 1 × 1 | 20 | 95,9 % | **56,4 %** | Faktor 1,70 |
| 8 × 1 × 2 | 54 | 96,8 % | **81,8 %** | Faktor 1,18 |
| 16 × 2 × 4 | 255 | 98,2 % | **93,5 %** | Faktor 1,05 |

Damit ist die Paarung der Dreiecke keine Kosmetik, sondern tragend: jedes Dreieck ohne
Partner wird ein Keil und kostet am groben Netz zweistellig. Die gierige Auswahl allein
lässt aber Dreiecke stehen, deren Nachbarn schon vergeben sind — und zwar **nicht** wegen
der Gütegrenze (sie von 0,3 auf 10⁻⁶ zu senken änderte an der Kragplatte keine einzige
Zahl). Darum wird nach dem gierigen Durchgang **umgepaart**: für jedes übrige Dreieck u
wird ein Nachbar v gesucht, dessen Partner w seinerseits ein anderes übriges Dreieck x
hat; dann wird (v, w) gelöst und (u, v) sowie (w, x) genommen — ein erweiternder Weg der
Länge drei, wiederholt, solange es trägt. Gemessen an der Kragplatte 1 × 0,2 × 0,05 m mit
Endlast (22.09.2026, gleiche Knotenzahl in beiden Zeilen):

| | Elemente | Keilanteil | Endverschiebung |
|---|---|---|---|
| h = 50 mm, nur gierig | 406 hex8 + 96 pent6 | 19,1 % | 93,8 % |
| h = 50 mm, **umgepaart** | 424 hex8 + 60 pent6 | **12,4 %** | **95,8 %** |
| h = 25 mm, nur gierig | 818 hex8 + 128 pent6 | 13,5 % | 97,1 % |
| h = 25 mm, **umgepaart** | 850 hex8 + 64 pent6 | **7,0 %** | **97,7 %** |

Zwei Prozentpunkte Genauigkeit am groben Netz, ohne einen einzigen Knoten mehr. Der
**Keilanteil je gesweeptem Körper** ist damit ein Abnahmemaß für sich; er steht im
Protokoll jedes Körpers („n Hexaeder + m Keile (gesweept, L Lagen)").

**Lagen bei Fließen.** Das gilt **elastisch**. Die Löser-Sitzung hat am Zweigstand
a4a7d91 (21.09.2026) den Kragträger 200 × 200 mm, 1,0 m, unter dem Endmoment 1,20 · M_el
gerechnet (fy = 235 N/mm², Verfestigung 2 %; die Randfaser trägt elastisch 282 N/mm² und
muss fließen, die plastische Zone reicht bis z/(h/2) = √(3 − 2 · 1,20) = 0,775):

| Typ | Lagen | Elemente | σ_v max | fließend | ε_p max | u_x max |
|---|---|---|---|---|---|---|
| hex8 | 1 | 5 | 285,3 N/mm² | **0 von 5** | 0 | 1,3327 mm |
| hex8 | 2 | 10 | 300,7 N/mm² | **0 von 10** | 0 | 1,3242 mm |
| hex8 | 3 | 15 | 203,1 N/mm² | 10 von 15 | 0,0963 % | 1,5894 mm |
| hex8 | 4 | 20 | 240,8 N/mm² | 8 von 20 | 0,1799 % | 1,7102 mm |
| hex8 | 6 | 30 | 266,8 N/mm² | 12 von 30 | 0,3469 % | 1,8876 mm |
| hex8 | 8 | 40 | 262,3 N/mm² | 16 von 40 | 0,4196 % | 1,9490 mm |
| tet4 | 4 | 100 | 235,7 N/mm² | 2 von 100 | 0,0164 % | 0,7361 mm |
| tet4 | 8 | 200 | 243,3 N/mm² | 2 von 200 | 0,1943 % | 0,8243 mm |

Mit einer und mit zwei Lagen fließt **nichts**, obwohl der Querschnitt plastifiziert:
die Plastizität wertet an den Gaußpunkten aus, und deren äußerster liegt bei einer Lage
auf 57,7 %, bei zwei Lagen auf 78,9 % der halben Höhe. Ab drei Lagen (85,9 %) wird
gefunden, was da ist. Die Verformung ist mit zwei Lagen ebenfalls falsch: u_x wächst von
1,333 mm (eine Lage) auf 1,949 mm (acht Lagen), 32 %. Darum gilt, sobald
`model.plastizitaet.an` gesetzt ist, `LAGEN_MIN_PLASTISCH = 4` als Untergrenze; sechs bis
acht Lagen sind das Richtige und kommen über die Kantenlänge. Elastische Bauteile zahlen
den Preis nicht mit (`test_lagen_bei_fliessen`). Nebenbefund derselben Messung: der
tet4 findet mit vier Unterteilungen 2 von 100 fließenden Elementen und 0,736 mm gegen
1,710 mm des hex8 mit vier Lagen — die volumetrische Sperre, der Grund für den Sweep.

**Nachbarn.** Ein Tetraeder-Körper an einer Wand des gesweepten Körpers muss dessen
Lagenpunkte treffen; ein freies Dreiecksnetz der Wand täte das nicht. Darum legt der
Sweep seine Flächennetze (Grund, Deckel, Wände: Vierecke über die kürzere Diagonale
geteilt, mit Kennung der Linienpunkte) als **vorgegebene Flächennetze** ab
(`model.flaechennetze`); `flaechennetz` gibt sie jedem Körper zurück, der die Fläche
berandet, und die Knoten werden über dieselben Schlüssel geteilt wie bisher (Kennung
für Linienpunkte, Fläche und Koordinate für Flächenpunkte). Gesweepte Körper laufen
darum im Hauptprozess **vor** den freien, die in den Arbeitsprozessen das Modell mit den
Netzen lesen. An der Grenze steht eine Hexaederseite zwei Tetraederseiten gegenüber:
knotenkonform, mit einer anderen Interpolation auf der Vierecksdiagonale. Pyramiden als
Übergang (`pyr5`) und das Zerlegen nicht sweepbarer Körper in sweepbare Blöcke sind die
nächsten Schritte. Reine Quader (sechs Vierecke, acht Knoten) bleiben beim abgebildeten
Hexaedernetz mit ihrer Teilung; `netz.sweep = False` schaltet den Sweep ab.

**Verjüngter Zug (22.09.2026).** Die Erkennung verlangte, dass der Deckel die um einen
Vektor **verschobene** Kopie des Grundes ist. Ein Kegelstumpf, eine konische Rippe, eine
Nabe mit Anzug fielen darum an die Tetraeder. Jetzt genügt eine **Ähnlichkeit**: der
Deckel ist die um k skalierte, um t verschobene Kopie (`sweep._abbildung_finden`,
`_abbilden`); die reine Verschiebung ist der Sonderfall k = 1 und läuft Zeichen für
Zeichen wie bisher. Die Lage k liegt bei s = k/L auf dem Maßstab 1 + (k−1)·s, die
Mantellinien laufen entsprechend zusammen — die Wandprüfung verlangt darum nicht mehr
„Vektor parallel zu t", sondern „die Mantellinie verbindet einen Grundknoten mit **seinem
Bild**". Der Rauminhalt wird als Pyramidenstumpf geprüft, h/3·(A₁ + A₂ + √(A₁A₂)).
Gemessen (Kegelstumpf l = 200 mm, h = 30 mm):

| r₁ → r₂ | Elemente | Güte min | Rauminhalt |
|---|---|---|---|
| 50 → 30 mm | 91 hex8 | 0,307 | 98,4 % des Kegelstumpfs (Kreise als Vielecke) |
| 50 → 50 mm (Zylinder) | 91 hex8 | 0,309 | 98,4 % |
| 30 → 60 mm | 91 hex8 + 14 pent6 | 0,306 | 98,4 % |

**Drehkörper (22.09.2026).** Rohrbogen, Ringsegment, Kegelrad-Ausschnitt: ein ebenes
Profil, um eine Achse gedreht. Grund und Deckel sind eben, aber **nicht parallel** — sie
stehen um denselben Winkel gegeneinander wie der Körper selbst, und **beide Kappenebenen
enthalten die Achse**. Daraus folgt sie geschlossen: die Achsrichtung steht auf beiden
Kappennormalen senkrecht (d = n_A × n_B), der Achspunkt liegt in beiden Ebenen (zwei
Gleichungen, die dritte ist der Lotpunkt zum Schwerpunktmittel), der Winkel ist der
zwischen den Normalen im Vorzeichen von d (`sweep._abbildung_drehung`). Die Lage k wird um
den Anteil k/L des Winkels gedreht und liegt damit **auf dem Bogen**, nicht auf der Sehne.

Die Mantellinien sind hier **Bögen**. Die Wandprüfung verlangt darum nicht mehr „gerade",
sondern: jeder Punkt der Mantellinie hat denselben Abstand zur Achse und dieselbe Höhe
längs ihr wie der Grundknoten — das ist der Kreisbogen um sie, ohne Annahme über die
Abtastung (`sweep._mantel_auf_bahn`). Der Rauminhalt wird nach **Guldin** geprüft:
Grundfläche mal Weg ihres Schwerpunkts, A · φ · r_s. Gemessen am Ringsegment
r = 100 … 150 mm, Höhe 50 mm, h = 20 mm:

| Winkel | Elemente | Güte min | Rauminhalt |
|---|---|---|---|
| 90° | 36 hex8 + 36 pent6 | 0,641 | 99,5 % des Ringsegments |
| 45° | 20 hex8 + 20 pent6 | 0,641 | 99,6 % |

**Und ein Fehler, den erst dieser Prüfkörper zeigte.** Ein Ringsegment hat sechs
Vierseitflächen und acht Eckknoten — dieselbe Zählung wie ein Quader. Der abgebildete
Quaderpfad (`mesher._hex_netz`) griff ihn deshalb ab und bildete **trilinear zwischen den
acht Ecken** ab: der 90°-Bogen kam so auf **63,7 %** seines Rauminhalts, ohne eine einzige
Meldung — Hülle, Randtreue und Formgüte sahen tadellos aus. Genau die Art stillen Fehlers,
vor der die Statik3D-Sitzung in ihrem Vertrag gewarnt hat. Der Quaderpfad verlangt jetzt
zusätzlich, dass **alle zwölf Kanten gerade** sind (`mesher._gerade_kanten`); krumme gehen
an den Sweep, und das Protokoll sagt es.

**Ein zweiter stiller Fehler desselben Pfads, quadratisch (25.09.2026).** Mit `ordnung = 2`
bekommt der abgebildete Quader Hexaeder mit 20 Knoten; die Kantenmitten merkt sich der
Vernetzer im gemeinsamen Zwischenspeicher unter dem Knotenpaar, damit der Nachbar an einer
gemeinsamen Fläche dieselben trifft (wie beim `tet10`, Abschnitt oben). Der Aufruf reichte
den Zwischenspeicher aber als `(cache or {})` weiter — ein noch **leerer** Zwischenspeicher,
wie ihn `modell_vernetzen` anlegt, zählt in Python als falsch, und der erste Körper schrieb
seine Kantenmitten in ein Wegwerf-Dict. Jede Kantenmitte der gemeinsamen Fläche gab es
darum zweimal, die Körper hingen dort nur an den Ecken zusammen. Gemessen (Prüfmatrix,
Kragarm 1,0 × 0,1 × 0,2 m aus zwei Körpern, 4 × 4 Felder je Fläche): 40 Orte mit zwei
Knoten, σ_v an der Nachweisstelle **+610 N/mm²** neben der Balkenlösung; aus einem Körper
oder mit geteilten Mitten +0,01 N/mm². Hülle, Randtreue und Formgüte meldeten nichts, nur
die Zählung doppelter Knoten in der Abnahme. `test_sweep.test_quader_hex20_gemeinsame_flaeche`
vernetzt zwei Einheitswürfel mit gemeinsamer Fläche über `modell_vernetzen` und verlangt
0 doppelte Knoten und genau 65 Knoten auf der Fläche (25 Ecken, 40 Mitten); vor der
Berichtigung waren es 40 Paare und 105 Knoten.

**Woran die Erkennung sonst scheitert, sagt sie jetzt selbst** (`erkennen_warum_nicht`,
eine Zeile je Körper im Protokoll): zu wenige Randflächen, keine zwei ebenen Kappen,
Kappen ohne gemeinsamen Weg, „decken sich weder verschoben (x mm daneben) noch skaliert
(y mm, Maßstab k)", Wandzahl, Wände nicht aus vier Linien, Mantellinien nicht gerade. Am
Drehlager sind 68 von 108 Körpern sweepbar, aber sie tragen nur 8,2 % der Elemente — die
40 übrigen tragen 91,8 %. Welche Erweiterung sich lohnt, entscheidet diese Zeile und nicht
die Vermutung; dasselbe Vorgehen hat beim Zerlegen und bei den Splittern den Ausschlag
gegeben.

**Kappen aus mehreren Flächen, Zylinder, Zerlegen an Fußabdrücken (21.09.2026).** Drei
Erweiterungen, damit der Sweep über Platten hinauskommt:

1. **Vier Flächen genügen.** Ein Zylinder ist in RFEM zwei Kreise (je zwei Halbbögen) und
   zwei Halbmantel-Flächen — vier Flächen. Die Erkennung verlangte fünf, und jeder Bolzen,
   Stift, jede Achse fiel an die Tetraeder; am Drehlager haben 48 von 108 Körpern vier
   Flächen. Jetzt `KAPPEN_MIN_FLAECHEN = 4` (`test_zylinder_wird_gesweept`: Bolzen
   r = 50 mm, l = 300 mm, h = 30 mm → 120 hex8 + 20 pent6, Abnahme ohne Befund, Deckellast
   7,73 kN kommt an). Dabei fiel auf, dass die Singulärwertzerlegung der Ausgleichsebene
   die Händigkeit zufällig liefert: an den Platten stimmte sie, am Kreis nicht, und alle
   140 Elemente standen auf dem Kopf — der Rahmen wird jetzt rechtshändig erzwungen
   (`sweep._rahmen`). Und zwei Halbbögen eines Kreises teilen sich beide Endknoten: die
   Paarung Grundlinie ↔ Deckellinie vergleicht darum die abgetasteten Kurven, nicht nur
   die Enden.
2. **Der Grund darf eine Gruppe koplanarer Flächen sein** — der Deckel einer Platte mit
   dem Fußabdruck einer Nabe als Öffnung *plus* der Fußabdruck selbst, die Schulter einer
   abgesetzten Welle *plus* die Stirnfläche des dünnen Teils. Rand der Gruppe sind die
   Linien, die nur eine ihrer Flächen benutzt; die inneren Linien fallen heraus. Jede
   Fläche der Gruppe wird für sich vernetzt und **für sich zu Vierecken gepaart** (nie über
   eine Flächengrenze), die Punkte auf den inneren Linien fallen über ihre Kennung
   zusammen. Der Deckel bleibt eine einzelne Fläche: das Netz der Gruppe achtet die
   inneren Linien, verschoben passt es auf die eine Deckelfläche — umgekehrt nicht.
3. **Zerlegen an Fußabdrücken** (`sweep.zerlegen`): ist ein Körper nicht als Ganzes
   Grundfläche mal Weg, wird jede ebene Fläche mit Öffnungen darauf geprüft, ob ein Teil
   des Körpers nur über eine Öffnung mit dem Rest verbunden ist — eine Nabe auf der
   Platte, der dünne Absatz an der Schulter, eine Rippe, die nicht durchläuft. Dann wird
   der Fußabdruck als ebene **Schnittfläche** eingezogen (Hilfsgeometrie nur für diesen
   Lauf, danach wieder aus dem Modell), und beide Teile werden für sich erkannt, bis zu
   zwei Schnitte tief (`ZERLEGEN_TIEFE`). Sweepbare Blöcke laufen zuerst und legen das
   Netz der Schnittfläche samt Vierecken vor (`model.flaechennetze` trägt jetzt fünf
   Glieder: Punkte, Dreiecke, Kennung, Vierecke, Rest-Dreiecke); ein Block, der nicht
   sweepbar bleibt, wird frei mit Tetraedern vernetzt und trifft die Schnittfläche
   knotengenau. Alle Elemente gehören dem Körper; Lasten, Kontakt und Ergebnisse je Körper
   ändern sich nicht. Was nicht geht: eine Bohrung, die durch Aufsatz *und* Träger läuft
   — ihre Mantelfläche müsste geteilt werden, und Linien dafür gibt es nicht; dann bleibt
   der Körper ganz und geht an die Tetraeder.
4. **Zerlegen an einer Ebene** (`sweep.zerlegen_ebene`, 22.09.2026): greift kein
   Fußabdruck, wird an der **Ebene einer Randfläche** geschnitten. Warum gerade dort: an
   einer einspringenden Kante liegt die Trennung zwischen zwei Blöcken immer in der Ebene
   einer der beiden anliegenden Flächen — eine Rippe wird an der Ebene der Plattendecke
   abgeschnitten, ein Absatz an der Ebene seiner Schulter. Andere Ebenen muss man nicht
   raten. Kandidat ist jede ebene Randfläche, deren Ebene den Körper wirklich **trennt**
   (Punkte auf beiden Seiten). Der Fall, den das löst und der Fußabdruck nicht: eine
   Rippe, die bis an den **Rand** der Platte läuft. Sie hängt nicht über einer Öffnung —
   ihr Fußabdruck berührt den Außenrand der Deckfläche, und genau das schließt
   `_fussabdruecke` aus, sonst wäre der Schnitt keine geschlossene Fläche.

   Drei Dinge daran sind nicht offensichtlich:

   * **Eine Kante, die in der Schnittebene liegt, gehört nicht der Seite, von der man sie
     anläuft.** An der T-förmigen Stirnfläche einer Rippe liegen zwei Kanten in der Ebene,
     und *beide* gehören zur Platte darunter, obwohl die eine von unten, die andere von
     oben erreicht wird. Nach den Vorzeichen der Ecken geteilt schlägt man eine davon der
     Rippe zu und bekommt zwei Teile, die nicht aneinanderpassen. Entschieden wird darum
     je **Kante** und geometrisch: einen kleinen Schritt von der Kantenmitte ins Innere
     der Fläche, und die Seite dieses Punktes zählt (`sweep._kantenseiten`).
   * **Eine Randfläche, die ganz in der Ebene liegt, gehört zu genau einem Block — und
     welchem, sieht man ihr nicht an.** Die Deckfläche einer Platte mit Rippe liegt in der
     Schnittebene und gehört zur Platte; ihre Nachbarn zeigen in beide Richtungen (die
     Plattenseiten nach unten, die Rippenwände nach oben), und die Materialseite folgt aus
     keiner lokalen Regel. Darum werden die Zuordnungen **durchprobiert** (bis drei solcher
     Flächen, also acht Versuche), und es entscheidet die **geschlossene Hülle**: jede
     Linie eines Blocks genau zweimal (`sweep._geschlossene_schale`). Diese Probe ist
     scharf und fängt jede falsche Zuordnung ab, bevor daraus ein gültiger, aber
     **anderer** Körper wird als der gemeinte.
   * **Der Rand der Schnittfläche kommt aus zwei Quellen:** den Schnittstrecken der
     geteilten Flächen *und* den Kanten der koplanaren Flächen, hinter denen die andere
     Seite liegt. Am Prüfkörper sind das die drei Kanten des Rippenfußes in der
     Deckfläche; ihr Außenrand gehört nicht dazu. Die Kanten werden zu einem Zug
     verkettet; verzweigt er oder zerfällt er in mehrere Ringe, unterbleibt der Schnitt.

   Nicht geschnitten werden Flächen mit Öffnungen, Flächen mit Bögen oder Polylinien und
   Flächen, die einem **zweiten Körper** gehören — der Schnitt risse sonst die Fuge zum
   Nachbarn auf.
4a. **Zerlegen an einer vorhandenen Schleife** (`sweep._an_schleife_teilen`, 23.09.2026):
   ein Zylinder, dessen Mantel axial in zwei Ringe geteilt ist — an der
   Zwischenkreislinie liegt ein Nachbar an, eine Fläche gibt es dort nicht. Die Kappen
   passen, aber je Randlinie stehen **zwei** Wände übereinander („4 Wandflächen zu
   2 Randlinien"); so scheitern **23 der 40** nicht sweepbaren Drehlagerkörper. Die
   Ebene des Bogens ist Kandidat (`schnittebenen` nimmt jetzt auch die Ebenen der
   Bögen), sie schneidet keine Fläche, aber die Linien in ihr, deren zwei Flächen auf
   verschiedenen Seiten liegen, schließen sich zu Schleifen: die Schnittfläche besteht
   aus **vorhandenen** Linien, mehrere Schleifen werden Außenrand und Öffnungen.
   Prüfkörper: gestapelter Zylinder → 2 Blöcke in 0,01 s, 120 hex8, Güte 0,309.
4b. **Budget.** Die Fußabdrücke suchen kombinatorisch; an V30 des Drehlagers (144 Flächen,
   12 Öffnungen je Kappe) probierten sie 255 s lang, an V34 217 s — und fanden nichts
   (gemessen 23.09.2026). Jetzt zuerst die billigen Schnitte (Ebene, Schleife), dann die
   Fußabdrücke mit dem Rest von `ZERLEGEN_ZEIT_S` = 20 s und `ZERLEGEN_VERSUCHE` = 40; der
   Abbruch steht im Protokoll („Zerlegen nach Zeit (20 s) abgebrochen"), und
   `zerlegbar()` merkt sich sein Ergebnis je Körper, weil `sweepbar()` vor dem Vernetzen
   dieselbe Frage stellt. Dabei fiel ein Fehler auf: der Fußabdruck hieß nach der Zahl
   der Schnitte, nach einem verworfenen Versuch bekam der nächste denselben Namen, und
   das Zurücknehmen räumte den gültigen mit weg (`KeyError 'V30§2'` an fünf der sechs
   dicken Körper). Die Namen zählt jetzt `Schnittwerk.marke` durch und vergibt keinen
   zweimal.
5. **Kappenlinien angleichen** (`sweep.kappenlinien_angleichen`, 22.09.2026): ein Schnitt
   setzt zwei neue Ecken in die eine Kappenschleife; die andere hat sie nicht. Die Kappen
   decken sich weiterhin, aber die Wandprüfung sucht zu **jeder** Grundlinie genau eine
   Deckellinie und findet drei. Am Prüfkörper blieb der Plattenblock darum tetraedrisch,
   obwohl er ein Quader ist. Zwei Schritte heilen das:

   * Die Kappenerkennung misst jetzt die **Figur**, nicht die Ecken: die Verschiebung kommt
     aus dem **Flächenschwerpunkt** des Umrings (`sweep._umringmitte`; der Mittelwert der
     Ecken wandert, wenn eine Ecke mitten auf einer geraden Kante dazukommt), und die
     Deckungsprobe misst den Abstand zur **Kurve** statt zu den Stützpunkten
     (`sweep._abstand_zum_zug`). Damit ist eingelöst, was `_deckungsgleich` seit jeher
     behauptet: zwei Kappen dürfen ihren Rand verschieden in Linien teilen. Die Prüfung
     wird dadurch nur großzügiger — was vorher durchging, geht weiter durch. Und sie
     bleibt so schnell wie zuvor, denn sie läuft in `erkennen` über jedes Flächenpaar
     eines Körpers (bis 144 × 144 am Drehlager): erst Stützpunkt auf Stützpunkt
     (KD-Baum, der häufige Fall), dann der umschriebene Kasten als notwendige
     Bedingung, und nur für die Punkte, die keinen Stützpunkt treffen, der Abstand zur
     Kurve. Dicht gerechnet kostete die Kurve bei 500 Randpunkten 23 ms statt 0,4 ms je
     Paar, bei 1 500 Punkten 196 ms statt 1,1 ms — gemessen am 22.09.2026, bevor die
     Stufen kamen; mit ihnen 0,28 und 0,87 ms.
   * Danach werden die Linien angeglichen: die fehlende Ecke wird auf die andere Schleife
     abgebildet, deren Linie dort geteilt, und die **Wand** dazwischen zerfällt mit — eine
     Wand je Linienpaar, mit neuer Mantellinie dazwischen. Erst dadurch bleibt die
     Wandprüfung so streng, wie sie ist: jede Wand aus genau vier Linien. Angefasst werden
     nur Linien, die allein diesem Block gehören: was einem **zweiten Körper** gehört,
     bleibt unangetastet (`sweep._fremde_flaechen`) — sein Netz kennt die Stücke nicht, und
     die Fuge risse auf. Der Weg wird dann quer dazu gesucht, und wenn es keinen gibt,
     bleibt der Körper bei den Tetraedern (`test_angleichen_schont_den_nachbarn`: derselbe
     Quader gleicht allein über seine Grundfläche an, mit Nachbar darunter über die
     Seitenflächen — 144 hex8, Fuge knotenkonform).

   Das hilft auch ohne Schnitt: ein von Hand gebauter Körper, dessen Deckel eine Kante in
   zwei Linien führt (weil dort ein Nachbar anstößt), war bisher nicht sweepbar. Er ist es
   jetzt (`test_kappen_verschieden_geteilt`: 44 hex8 + 4 pent6 statt Tetraedern).

Gemessen (21.09.2026, ein Prozess, `tests/test_sweep.py`):

| Prüfkörper | ohne Zerlegen | mit Zerlegen | Abnahme | Last → Lager |
|---|---|---|---|---|
| Platte 0,4 × 0,3 × 0,1 m mit Nabe r = 60 mm, h = 80 mm, Kantenlänge 30 mm | 7 595 tet4 | **441 hex8 + 108 pent6**, ein Schnitt, 174 Knoten in der Schnittebene, keiner doppelt | ohne Befund | 11,12 kN = 11,12 kN |
| abgesetzte Welle r = 50/30 mm, l = 200/150 mm, Kantenlänge 25 mm | 2 349 tet4 (+ 66 des dünnen Teils) | **446 hex8 + 28 pent6**, ein Schnitt, 61 Knoten in der Schulterebene, keiner doppelt | ohne Befund | 2,78 kN = 2,78 kN |

Und am Ebenenschnitt (22.09.2026, Platte 0,2 × 0,1 × 0,02 m mit einer Rippe 150 × 20 × 60 mm
bis an den Rand, eingespannt bei x = 0, 10 kN auf die Stirnfläche, Kantenlänge 25 mm):

| Netz | Elemente | Knoten | größte Verschiebung |
|---|---|---|---|
| tet4, Kantenlänge 25 mm | 685 | 219 | 0,5811 mm |
| tet4, 12,5 mm | 5 403 | 1 129 | 1,3437 mm |
| tet4, 8 mm | 18 510 | 3 549 | 1,7955 mm |
| tet4, 6 mm | 39 891 | 7 459 | 1,9674 mm |
| **zerlegt und gesweept, 25 mm** | **124** (96 hex8 + 28 pent6) | **239** | **2,0161 mm** |
| zerlegt und gesweept, 12,5 mm | 340 | 599 | 2,1138 mm |

Das grobe gesweepte Netz steht über dem Tetraedernetz mit **einunddreißigmal so vielen
Knoten**. Rauminhalt 100,0 %, Formgüte 0,352, 54 Knoten in der Schnittebene und keiner
doppelt, Abnahme ohne Befund. Und die Last kommt durch beide Blöcke ins Lager: 1 MN/m² auf
die geschnittene Stirnfläche (3,200 kN), auf den durch das Angleichen ersetzten Boden
(20,000 kN) und auf die koplanare Deckfläche (17,000 kN) ergeben je genau diese
Auflagerkraft — die Randseiten der Teilflächen liegen auf den Ausgangsflächen, über zwei
Stufen (Schnitt, dann Angleichen) hinweg. Das ist die schärfste Messung dieser Arbeit für den Satz,
mit dem sie angefangen hat: der lineare Tetraeder sperrt, und kein Verfeinern holt das
auf.

Der **abgebildete Quader** (`mesher._hex_netz`, sechs Vierecke, acht Ecken) setzt seit
21.09.2026 ebenfalls Randseiten, teilt seine Knoten mit Nachbarn über dieselben Schlüssel
wie Sweep und freier Vernetzer und legt seine sechs Flächennetze vor; seine Kantenteilung
folgt an Kanten, die ein Nachbar mitbenutzt, der Linienvorgabe (Quader 2 × 1 × 1 m mit
Pyramide an der Wand und Feldkugel an einer Kante: 4 × 5 × 10 Hexaeder, 66 Wandknoten
geteilt, Deckellast 2 000,0 kN kommt an — vorher 0 kN, `test_quader_randseiten_und_nachbar`).

**Quadergenerator mit Tetraedern (`mesher.grid_box`, 22.09.2026).** Die Maske
*Quader erzeugen* (und die Web-Operation `box`) teilt mit `typ="tet4"` jede Zelle des
Rasters in fünf Tetraeder: vier Eck-Tetraeder und eines in der Mitte. Die Diagonalen aller
sechs Zellseiten laufen durch die vier Ecken des Mitteltetraeders — in der Grundform die
Ecken 1, 3, 4, 6 der Zelle. Die Nachbarzelle sieht dieselbe Seite von der anderen Seite;
bei gleicher Zerlegung läge ihre Diagonale über die beiden anderen Ecken, die zwei
Dreieckspaare deckten sich nicht, und die Seite bliebe ein innerer Riss, an dem die
Verschiebung springen darf (nur ein linearer Verschiebungszustand ist davon nicht
betroffen). Deshalb wechselt die Zerlegung schachbrettartig mit (i + j + k) mod 2: die
gespiegelte Form hat die Mitte 0, 2, 5, 7 und trifft die Diagonalen der Nachbarn. Sie ist
die x-Spiegelung der Grundform mit zwei getauschten Knoten, damit jedes Tetraeder positiv
orientiert bleibt. Prüfung (`tests/test_elemente.py`, `test_quader_tet4_konform`, zehn
Rastergrößen von 1 × 1 × 1 bis 5 × 4 × 3): frei bleiben genau die 4 (nx·ny + ny·nz + nx·nz)
Randdreiecke, keine Dreiecksseite gehört zu mehr als zwei Tetraedern, alle Volumina sind
positiv, ihre Summe ist lx·ly·lz. Vorher gemessen: 2 × 2 × 2 Zellen 96 statt 48 freie
Dreiecke, 3 × 3 × 3 324 statt 108. Am Kragarm 2 × 0,4 × 0,4 m (Endlast 100 kN, E = 210 GPa)
lag die Spitzendurchbiegung mit Rissen bei 0,43802 statt 0,43741 mm (10 × 3 × 3 Zellen,
+0,14 %) und 0,54363 statt 0,53761 mm (20 × 4 × 4, +1,1 %). Der Abstand zur
Balkenlösung mit Schubanteil (0,61381 mm) besteht auch im rissfreien Netz und nimmt erst
mit dem Verfeinern ab (Verhältnis 0,713 bei 10 × 3 × 3, 0,876 bei 20 × 4 × 4).

**Pyramiden als Übergang (`netz.pyramiden`, 21.09.2026).** An der Grenze zwischen einem
gesweepten (oder abgebildeten) Körper und einem frei vernetzten Nachbarn steht eine
Hexaederseite zwei Tetraederseiten gegenüber: knotenkonform, aber mit anderer Interpolation
auf der Diagonale des Vierecks. Mit dem Schalter bekommt jedes Viereck der vorgegebenen
Nachbarfläche stattdessen eine **Pyramide** (`pyr5`): die Spitze sitzt im Inneren des
Nachbarn, um `PYRAMIDEN_HOEHE = 0,5` mal die mittlere Kantenlänge entlang der Hüllnormale
nach innen; die zwei Hülldreiecke des Vierecks werden durch die vier Seitendreiecke der
Pyramide ersetzt, und der Tetraedervernetzer schließt daran an. Kommt die Spitze einem
anderen Hüllpunkt näher als die halbe Höhe (dünne Bauteile), wird sie zurückgenommen, und
unter `PYRAMIDEN_HOEHE_MIN = 0,15` bleibt das Viereck geteilt — eine flache Pyramide wäre
selbst ein schlechtes Element. Knoten und Randseiten werden mit den **ursprünglichen**
Dreiecken gebildet, damit die gemeinsamen Flächen so geteilt werden wie bisher; das
Grundviereck jeder Pyramide wird als Randseite 0 an die Nachbarfläche gehängt.

Gemessen an der Platte mit Pyramidenkörper an der Wand M2 (h = 50 mm, 21.09.2026):

| | Elemente | Formgüte min | Verschiebung max | Auflagerkraft |
|---|---|---|---|---|
| ohne (Vierecke geteilt) | 280 hex8 + 24 pent6 + 386 tet4 | 0,185 | 0,3588 mm | 117,22 kN |
| **mit Pyramiden** | 280 hex8 + 24 pent6 + **12 pyr5** + 353 tet4 | 0,154 | 0,3589 mm | 117,22 kN |

Der Rauminhalt ist auf 10⁻⁹ derselbe, die Verschiebung ändert sich um 0,03 %, die Abnahme
hat nichts zu beanstanden. Darum ist der Schalter **aus** als Vorgabe: er kostet Elemente
und senkt die kleinste Formgüte, und die Rechnung gewinnt an diesem Beispiel nichts. Wer
den Übergang formgleich haben will — etwa weil eine Kontaktfuge genau dort liegt —,
schaltet ihn ein (`test_pyramiden_als_uebergang`).

**Betriebsart „sauber“ (dritter Auftrag, 24.09.2026).** Der Sweep ist kein Schalter mehr,
sondern ein Feld mit drei Werten: `Netzeinstellungen.sweep = "aus" | "sauber" | "immer"`
(`sweep.betriebsart`; `True`/`False` alter Dateien heißen „immer“/„aus“, ein unbekanntes Wort
„immer“, die Vorgabe bleibt „aus“). In „sauber“ wird ein Körper **nur** als Hexaeder vernetzt,
wenn jedes seiner hex8 und pent6 höchstens `TRAPEZ_GRENZE` Trapezfehler hat und an allen
Integrationspunkten und Ecken eine positive Jacobi-Determinante (`sauber_pruefen`, vor dem
Einbau am Lagenstapel); sonst wird er frei mit Tetraedern vernetzt, das Protokoll nennt den Grund
(„nicht gesweept (Betriebsart „sauber“) – Trapezfehler 27,0° > 5,0° (Winkelfehler 57°)“), und
der Übergang zu jedem gesweepten oder abgebildeten Nachbarn geht **immer über Pyramiden**
(`netz.pyramiden` braucht es dafür nicht). Zerlegen an Fußabdrücken gibt es in „sauber“ nicht: die
Blöcke wären gepflasterte Grundflächen, die die Probe nicht bestehen. Die Probe entscheidet schon
die Verteilung (`sweep.sweepbar` mit `nur_pruefen`): nur ein sauber gesweepter Körper bleibt im
Hauptprozess, ein abgelehnter geht als freier Körper in einen Arbeitsprozess — ohne diese
Vorprüfung liefen die abgelehnten Körper nacheinander im Hauptprozess durch den freien Vernetzer,
mit MMG3D über 14 Minuten für einen einzigen (gemessen 24.09.2026).

**Die Grenze gemessen: Trapez gegen Parallelogramm.** `sweep.WINKELFEHLER_GRENZE` stand mit 15°
ohne Messung. Gemessen am Kragarm wie V5 (`tests/messung_winkelfehler.py`, 1,0 × 0,1 × 0,2 m,
Soll 355 N/mm² an der Nachweisstelle): das regelmäßige hex8-Netz erreicht 1 N/mm² schon mit
8 × 2 × 4 Elementen (+0,77); dann dasselbe Netz mit Parallelogramm- und mit Trapezverzerrung im
Zickzack über die Lagen — jedes Element bekommt den Eckwinkel 90° ± θ, das Trapez dazu je Spalte
wechselnde Vorzeichen, sodass gegenüberliegende Kanten um 2 θ gegeneinander kippen. Fehler an der
Nachweisstelle in N/mm² (Zuwachs gegen 0°):

| θ | 2,5° | 5° | 7,5° | 10° | 15° | 20° | 30° |
|---|---|---|---|---|---|---|---|
| Parallelogramm, 8 × 2 × 4 | −0,06 | −0,10 | −0,13 | −0,14 | −0,10 | +0,01 | +0,37 |
| Trapez, 8 × 2 × 4 | **−2,05** | −6,06 | −11,95 | −19,65 | −39,99 | −65,91 | −128,80 |
| Parallelogramm, 16 × 4 × 8 | 0,00 | 0,00 | 0,00 | −0,01 | −0,01 | −0,01 | +0,01 |
| Trapez, 16 × 4 × 8 | −0,48 | **−1,53** | −3,15 | −5,35 | −11,58 | −20,39 | −46,92 |

Die **Parallelogrammverzerrung ist bis 30° unkritisch**, die **Trapezverzerrung kostet ab 2,5°
mehr als 1 N/mm²** am groben Netz und ab 5° am feinen — der bekannte Trapezlock des hex8. Der
Eckwinkelfehler unterscheidet die beiden nicht (beide θ). Darum zwei Konstanten:
`WINKELFEHLER_GRENZE = 2,5°` (der größte Winkel, bei dem beide Verzerrungen unter 1 N/mm²
bleiben — die Frage des Auftrags, wörtlich; die Netzabnahme liest sie weiter) und das Maß, das den
hex8 wirklich trifft, `sweep.trapezfehler`: der Winkel zwischen **gegenüberliegenden** Kanten
einer Viereckseite, 0 für Rechtecke und Parallelogramme, 2 θ für das Zickzack-Trapez, mit
`TRAPEZ_GRENZE = 2 · WINKELFEHLER_GRENZE = 5°`. Die Betriebsart „sauber“ prüft den Trapezfehler.
Empfehlung an die Netzabnahme: für die Warnung „verzerrte hex8“ ebenfalls `trapezfehler` gegen
`TRAPEZ_GRENZE` lesen, sonst warnt sie vor Parallelogrammen, die nichts kosten.

**Was der Übergang kostet.** Ein pyr5 ist für sich schwach (Element-Sitzung, 23.09.: der Kragarm
als reines Pyramidennetz −193 / −93 / −34 N/mm²). Gemessen mit `tests/messung_uebergang_pyramiden.py`
am zweiteiligen Kragarm, Fuge genau an der Nachweisstelle x = L/2: A der abgebildete hex8-Quader,
B frei mit angehobener Deckelecke (weder abgebildet noch sweepbar), h = 25 mm, Fehler an der
Nachweisstelle und ein Element daneben:

| Netz | Elemente | Unbekannte | Fehler an der Fuge | ein Element in A / in B |
|---|---|---|---|---|
| hex8 durchgehend (V5) | 640 hex8 | 5 535 | +0,26 | +0,24 / +0,27 |
| **Übergang** A hex8, B Tetraeder mit 32 Pyramiden | 640 hex8 + 32 pyr5 + 9 664 tet4 | 8 268 | **−25,9** | +2,0 / +12,4 |
| Tetraeder durchgehend | 18 856 tet4 | 10 662 | −35,9 | −9,7 / +18,2 |

Die Übergangslage kostet an der Fuge 26 N/mm² (7 %) — fast so viel wie das reine tet4-Netz, ein
Element weiter im hex8-Teil noch 2. Wer den Übergang braucht, legt ihn nicht an die Nachweisstelle.
Dabei fiel ein Fehler auf: an der Fuge zum **abgebildeten** Quader kamen alle 32 Pyramiden
**umgestülpt** in den Löser (det J = −9,8e-7 an jedem Punkt), weil `solid_volume` den Betrag nimmt
und den Umlaufsinn nie sah; seit dem 24.09.2026 richtet das Vorzeichen der Jacobi-Determinante
das Grundviereck aus (`test_pyramiden_ausrichtung_am_abgebildeten_nachbarn`: 8 Pyramiden, alle
det J > 0, Abnahme ohne Befund).

**Am Drehlager in der Betriebsart „sauber“** (18°, 3 Arbeitsprozesse, nur vernetzt; gemessen
24.09.2026): von 108 Körpern sind 68 sweepbar, und **keiner** besteht die Probe — Trapezfehler
7,5° bis 72,2° (Median 26,4°), Eckwinkelfehler 5° bis 72° (Median 40°); die drei besten (V101,
V70, V96) liegen mit 7,5° noch anderthalbmal über der Grenze. Der Grund ist der Sweep selbst:
seine Grundfläche ist immer aus gepaarten Dreiecken gepflastert (`_grundnetz`), auch ein
Rechteck — der Quader mit geteilter Deckelkante kommt so auf 30° Trapezfehler, ein 100 × 50 mm-Grund
auf 5,9°, ein Zylinder mit gepflasterter Kreisscheibe auf 70°. Ergebnis: 584 614 tet4 auf
141 466 Knoten (429 666 Unbekannte), 0 Hexaeder, 0 Pyramiden, 188 s; gegen das reine tet10-Netz bei
18° (670 185 Elemente, 3 302 631 Unbekannte) und gegen das tet4-Netz mit `sweep = "aus"`
(672 575 Elemente). Was die Betriebsart mit Hexaedern füllen würde, ist ein **abgebildetes
Grundnetz für vierseitige Grundflächen** (Rechtecke, Ringsektoren mit feiner Winkelteilung) — das
gehört zum Plan des hex8-Vernetzers für die dicken Platten, nicht in diesen Auftrag.

**Am Drehlager** (Zählung der Löser-Sitzung mit `sweep.erkennen` und `netzfeld.bedeutung`,
21.09.2026; 108 Körper, 1 375 Flächen, 2 807 Linien, 645 934 Volumenelemente):

| | |
|---|---|
| sweepbare Körper | **2 von 108** (V18, V11), 2 864 Elemente = **0,4 %** |
| Körper mit 4 Flächen | 48 — unter fünf, `erkennen` steigt aus |
| Körper mit 6 / 9 Flächen | 23 / 18 |
| die acht größten Körper (48 bis 144 Flächen) | 542 391 Elemente = **84,0 %** |
| Nebenflächen (`bedeutung`) | 913 von 1 375 = 66,4 %; Nebenlinien 1 197 von 2 807 = 42,6 % |
| Flächen mit Last | **2**; bedeutend sind fast nur Kontaktflächen (37 Bedingungen) und aus RFEM integrierte Objekte |

**Der Lauf mit dem fertigen Stand** (Löser-Sitzung, 21.09.2026, 16 Arbeitsprozesse,
Vorgaben unverändert: `sweep` an, `pyramiden` aus, `nebenflaechen_grob` aus,
`plastizitaet.an`):

| | altes Netz | mit Größenfeld, Sweep, Lagenvorgabe, Zylindern und Kappen-Gruppen |
|---|---|---|
| Volumenelemente | 645 934 tet4 | **495 593** = 31 108 hex8 + 9 368 pent6 + 455 117 tet4 (**−23,3 %**) |
| Knoten | 158 728 | 159 465 (+0,5 %) |
| Elemente je Knoten | 4,10 | **3,14** |
| gesweepte Körper | 0 | **68 von 108** |
| V33 | 80 600 tet4 | 12 372 hex8 + 3 720 pent6 = 16 092 (**−80,0 %**) |
| V35 | 79 105 tet4 | 12 208 hex8 + 3 552 pent6 = 15 760 (**−80,1 %**) |

Die 48 Körper mit vier Flächen sind als **Zylinder** erkannt, V33 und V35 über eine
**Kappe aus vier koplanaren Flächen**. Was das für die Rechnung heißt, ist nüchtern zu
sagen: die Knotenzahl bleibt gleich, also wird die **Faktorisierung nicht billiger** —
billiger werden das Aufstellen (23 % weniger Elementschleifen, und am Drehlager ist das
Aufstellen der Brocken: 124 s je Kontaktschritt gegen 4,23 s Faktorisierung) und der
Speicher. Der Gewinn ist die **Genauigkeit**: in V33 und V35, zusammen einem Viertel der
alten Elemente, steht jetzt der hex8 statt des tet4 (97,6 gegen 68,4 % der Balkenlösung).
Das **Zerlegen an Fußabdrücken hat an keinem der 108 Körper angesetzt**; seit demselben Tag
sagt jeder Körper im Protokoll, warum (`sweep.zerlegen_warum_nicht`).

Der Sweep, wie er am Morgen des 21.09.2026 stand, erreichte das Drehlager also nicht:
sein Erfolgsmaß (Kragplatte 97,6 % gegen 68,4 %, ein Achtel der Elemente) kam dort bei
0,4 % der Elemente an. Seit dem Abend gelten vier Flächen (die 48 Körper mit vier Flächen
sind, wenn es Zylinder sind, sweepbar), Kappen-Gruppen und das Zerlegen an Fußabdrücken
— was davon an den acht großen Körpern (48 bis 144 Flächen) greift, entscheidet das
Modell und ist **nicht gemessen**. Und `nebenflaechen_grob` spart am Drehlager **0,2 %** der Elemente (646 712 →
645 570; an der Platte waren es 55 %): die Bohrungen, die das Netz fein machen, sind dort
fast alle Bohrungen *mit* Bolzen, Stift oder Achse — Kontaktflächen, und die bleiben fein.
**Die 189 Splitter am Drehlager: keine Kappe, sondern die Hülle.** Am gespeicherten Netz
eingeordnet (Löser-Sitzung, 21.09.2026): von 189 Splittern (Güte < 0,10) in fünf Körpern
haben **0 vier Hüllknoten** (also keine Kappe), **182 drei** und 7 zwei. Bei **allen 189**
ist die kürzeste Kante eine **Hüllkante** von 0,13 bis 1,36 mm — bei `ziellaenge` = 50 mm
also zwischen h/37 und h/385. Das Volumennetz hat sie nicht erzeugt, es hat sie **geerbt**:
die Hüllknoten stehen fest, der Tetraeder muss sie nehmen. Die gebaute Kappen-Kur greift
an keinem einzigen.

Die naheliegende Gegenmaßnahme — eine **Mindestweite** in der Linien- und Flächenteilung,
damit die Krümmungsregel (20 Abschnitte je Vollkreis, gleich wie klein er ist) keine
Sub-Millimeter-Kanten mehr legt — ist gebaut, gemessen und **wieder verworfen worden**.
Sie senkt die Zahl der engen Hüllkanten deutlich (Platte 1 × 0,6 × 0,2 m mit einer Bohrung
r = 1 mm bei h = 50 mm: 1 280 → 586) und die Elementzahl um 6 bis 8 %, macht das Netz aber
**schlechter**, weil die grobe Bohrungssehne dann nicht mehr zum Kranz daneben passt
(deterministisch wiederholt):

| Prüfkörper | Güte min ohne | mit Mindestweite | Splitter ohne | mit |
|---|---|---|---|---|
| Platte, eine Bohrung r = 2 mm | 0,090 | **0,065** | 10 | **15** |
| Platte, fünf Bohrungen (zwei winzige) | 0,071 | **0,039** | 15 | **25** |

0,039 liegt unter der Abnahmegrenze 0,05 — die Kur war schlimmer als das Übel. Geblieben
ist die **Diagnose** (`mesher3d._enge_huellkanten`): je Körper eine Warnung mit Zahl,
kürzester Kante und **Herkunft** der beiden Knoten — auf derselben Linie
(Krümmungsteilung), zwischen zwei Linien (das ist dann die Geometrie: zwei Kanten laufen
eng zusammen) oder am Innennetz einer Fläche. Erst diese Unterscheidung sagt, welche Kur
überhaupt greifen kann; ohne sie ist jede weitere geraten.

**Das Innennetz folgt dem örtlich feinen Rand (`RANDFELD`, 21.09.2026).** Eine Randlinie
darf nicht neben einer viel feineren stehenbleiben — die Regel oben teilt darum die
Nachbarlinien eines feinen Merkmals mit. Das Flächeninnere folgte dem **nicht**: es blieb
bei h. Damit stand ein **Band** feiner Randstrecken gegen ein grobes Inneres, und jedes
Dreieck dazwischen war ein Splitter; der Sweep zog jedes davon über alle Lagen zum Keil
aus. Am Drehlager waren das **992 von 9 368 Keilen unter der Güte 0,10 (10,6 %) bei 0 von
31 108 Hexaedern** (Statik3D-Sitzung, 21.09.2026).

Jetzt gilt in der Fläche dieselbe Regel wie im Tetraedernetz: `h_lokal = min(h, Randkante
+ 0,25 · d)`, wobei `Randkante` die Länge der nächsten Randstrecke ist. Eingeschaltet wird
sie erst, wenn eine Randstrecke höchstens halb so lang ist wie h (`RANDFELD_SCHWELLE`) —
bis zum Verhältnis 2 trägt die gleichmäßige Teilung noch. Nachgestellt an einer gesweepten
Platte 200 × 100 × 35 mm, deren Umriss eine Stufe von 0,45 mm hat (h = 50 mm — derselbe
Fall wie Element 11313 in V35 mit seiner 0,456-mm-Kante):

| | Elemente | Güte min | unter 0,10 |
|---|---|---|---|
| Sweep, ohne Randfeld | 116 | 0,054 | **34** |
| **Sweep, mit Randfeld** | 168 | **0,122** | **0** |
| tet4, ohne Randfeld | 1 646 | 0,052 | 13 |
| **tet4, mit Randfeld** | 2 701 | **0,131** | **0** |

Drei Dinge sind daran wichtig. **Erstens**: die Ursache ist nicht die Paarung. Die
Vermutung, die Paarung lasse die Splitterdreiecke als Keile übrig, ist nachgemessen und
trägt nicht — an einer Platte mit drei Bohrungen sind die 68 übrigen Dreiecke im Mittel
0,774 gut, die 68 schlechtesten hätten 0,664. **Zweitens**: der Tetraederweg war nie die
bessere Wahl. Er kommt am selben Körper auf dieselbe schlechteste Güte (0,052 gegen 0,054)
mit dem **Vierzehnfachen** an Elementen; „lieber ganz Tetraeder" hätte nichts geheilt.
**Drittens**: wo der Rand nicht örtlich fein ist, kostet die Regel nichts (Platte mit
Bohrung: 1 064 Elemente und Güte 0,316 in beiden Fällen).

**MMG3D: Rückfall auf `-optim`.** Schlägt der Lauf **mit** Metrik fehl, wird er ohne sie
wiederholt (`-optim`, der Weg vor dem Größenfeld), bevor der Körper aufgegeben wird. Am
Drehlager war genau das der Unterschied zwischen einem brauchbaren und einem teuren Netz:
V34 scheiterte im Metrik-Lauf, behielt seinen Tetraeder der Güte 0,000, und die
Gütekontrolle erzwang eine Vernetzung mit 33,3 statt 50 mm — **69 589 statt 49 274
Tetraeder**, also teurer als vorher. Dazu wird der **Grund** aus MMGs Ausgabe gelesen und
nicht nur ihr Ende: MMG sucht neben der Eingabedatei von sich aus eine gleichnamige `.sol`
und schreibt, wenn keine da ist, „`** … netz.sol NOT FOUND. USE DEFAULT METRIC.`" — eine
Warnung, die am Schluss steht. Wer die letzten Zeichen meldet, nennt genau sie; so stand
im Drehlager-Protokoll „netz.sol NOT FOUND", obwohl die Metrik geschrieben war
(`vernetzer_extern._mmg_grund`).

## 6b Netzqualität (`netzguete.py`)

Die Formgüte misst, wie nah ein Element an seiner regelmäßigen Gestalt ist;
1 ist die beste Form, 0 die entartete.

Für **Tetraeder** und **Dreiecke** gibt es einen geschlossenen Ausdruck:

    Tetraeder:  q = 12 · (3V)^(2/3) / Σ l_i²
    Dreieck:    q = 4√3 · A / Σ l_i²

Der Vorfaktor ist so gewählt, dass der regelmäßige Tetraeder bzw. das
gleichseitige Dreieck genau 1 bekommt. Das ist das übliche Maß; ANSYS und
RFEM nennen es *element quality*.

Für **Vierecke, Sechsflächner, Keile und Pyramiden** dient die **skalierte
Jacobi-Determinante**: an jeder Ecke werden die Kantenvektoren zu den
Nachbarecken normiert und ihre Determinante gebildet,

    räumlich:  det[ e₁/|e₁|  e₂/|e₂|  e₃/|e₃| ]
    eben:      | e₁/|e₁| × e₂/|e₂| |  =  sin α ,

das Minimum über alle Ecken ist der Wert des Elements. Er wird auf die
**beste Form dieser Art** normiert: beim Würfel und beim Quadrat stoßen die
Kanten rechtwinklig aufeinander (Faktor 1), beim Keil ist die Grundfläche ein
gleichseitiges Dreieck (√3/2), bei der Pyramide mit gleich langen Kanten
√2/2. Ohne diese Normierung bekäme der beste Keil nur 0,866.

Ein **negativer** Wert heißt: die Ecke ist umgestülpt, die Jacobi-Determinante
wechselt im Element das Vorzeichen. Solche Elemente rechnen falsch und werden
eigens gezählt. Unter 0,10 spricht man von einem **Splitter** (*sliver*);
dort sind die Spannungen unbrauchbar, die Verschiebungen meist noch nicht.

Bei quadratischen Elementen (tet10, hex20, shell6, shell8, ebene6, ebene8)
zählen die Eckknoten; die Seitenmittenknoten ändern die Form nicht. Stäbe,
Seile, Federn und Grenzschichten haben keine Form in diesem Sinn und bleiben
unbewertet.

Als zweites Maß steht das **Seitenverhältnis** (kürzeste durch längste Kante)
zur Verfügung, als drittes die längste Kante als Elementgröße. Alles ist je
Elementart vektorisiert: 380 000 Tetraeder brauchen rund 1,5 s.

### 6b-2 Elementwahl je Körper: tet10 an den Nachweisstellen (22.09.2026)

**Wo es schwer wird: die Lamé-Hohlkugel.** Der Kragarm ist ein freundlicher Fall — der
Spannungsverlauf über die Höhe ist linear, und an einem Knoten der Oberkante mitteln
sich die Fehler der Elemente links und rechts heraus. An der Hohlkugel unter Innendruck
(a = 0,1 m, b = 0,2 m, Achtel mit Symmetrie; σ_v ∝ 1/r³, auf 355 N/mm² an der
Innenfläche skaliert; `tests/messung_hohlkugel.py`) steht der steile Verlauf senkrecht
zur Nachweisfläche, und das Knotenmittel ist dort einseitig. Geglättete Knotenspannung
an der Innenfläche, Mittel über ihre Eckknoten, Abweichung in N/mm² (22.09.2026):

| | gleichmäßig | radial gestuft r = a + (b − a)(k/n)³ |
|---|---|---|
| hex8 171 / 915 / 5 859 FHG | −100 / −51 / −25 | 5 859: −4,2; 11 067: −2,3 |
| tet4 171 / 915 / 5 859 FHG | −166 / −101 / −55 | |
| tet10 (Mitten auf der Kugel) 915 / 5 859 / 41 667 FHG | −16 / −7,3 / −2,5 | 5 859 bei Stufung 2: +8,5; bei 3: Elemente umgestülpt (det J < 0, gemeldet) |

Hier konvergiert auch der `hex8` nur mit der Elementlänge, und der `tet10` braucht über
40 000 Unbekannte für −2,5 N/mm². Eine Flickenanpassung der Spannung (SPR) half an der
Kugel nicht (schlechter als das Knotenmittel), am Kragarm dagegen beim `tet10` deutlich
(2 295 FHG: −0,17 statt +4,0 N/mm²). **Folgerung:** an Nachweisstellen mit steilem
Gradienten senkrecht zur Oberfläche entscheidet die örtliche Verfeinerung (Größenfeld,
adaptive Schleife § 6c) mehr als die Elementordnung; die Elementwahl unten ist dafür
eine Hilfe, keine Garantie für 1 N/mm².

**Volumensperre, gemessen und benannt: das Rohr bis ν = 0,4999.** Viertel eines
dickwandigen Rohres a = 0,1 m, b = 0,2 m unter 100 N/mm² Innendruck, ebene Dehnung
(`pruefkoerper.Hohlzylinder`, der Prüfkörper von MacNeal/Harder; beim tet10 liegen die
Kantenmitten auf dem Kreis, beim hex8 ist die Innenfläche ein Vieleck).
`tests/messung_zylinder.py`, gemessen 23.09.2026, 00:46–00:49, Einkern. Gemeldet u_r an
der Innenfläche gegen Lamé (1 = exakt) und die Abweichung von σ_v dort (geglättete
Knotenspannung, Mittel über die Eckknoten) in N/mm²:

| Netz (Teile über 90° × radial) | ν = 0,3: u / σ_v | ν = 0,49 | ν = 0,499 | ν = 0,4999 |
|---|---|---|---|---|
| hex8 8 × 4 (270 FHG) | 0,9935 / −17,6 | 0,9894 / −6,8 | 0,9891 / −6,0 | 0,9891 / −5,9 |
| hex8 16 × 8 (918) | 0,9983 / −8,5 | | | 0,9972 / −1,6 |
| hex8 32 × 16 (3 366) | 0,9996 / −4,1 | | | 0,9993 / −0,4 |
| tet4 8 × 4 (270) | 0,9668 / −40,5 | 0,8367 / −53,0 | 0,7463 / −59,1 | 0,7270 / −59,9 |
| pent6 8 × 4 (270) | 0,9656 / −43,1 | 0,8256 / −55,7 | 0,7406 / −59,5 | 0,7262 / −59,8 |
| tet10 8 × 4 (1 377) | 1,0002 / −2,4 | 0,9993 / −2,9 | 0,9984 / −3,7 | 0,9980 / −4,0 |
| tet10 16 × 8 (5 049) | 1,0000 / −0,75 | | | 0,9994 / −2,3 |

* **hex8 sperrt nicht** (Volumendehnung linear projiziert, § 4.4): die Verschiebung ist
  bei ν = 0,4999 so gut wie bei 0,3. Sein σ_v-Fehler bei 0,3 kommt aus dem Vieleck der
  Innenfläche und halbiert sich mit jeder Teilung.
* **tet4 und Keil sperren:** die Verschiebung fällt auf 73 % der wahren, σ_v liegt
  60 N/mm² daneben.
* **tet10 sperrt schwach:** bei ν = 0,4999 fehlen 0,2 % (1 377 FHG) bzw. 0,06 % (5 049) der
  Verschiebung, und σ_v konvergiert langsamer — bei 5 049 FHG −2,3 statt −0,75 N/mm². Bei
  ν = 0,3 (Stahl elastisch) ist das ohne Belang. In voll plastischen Zonen fließt der
  Werkstoff volumentreu (J2), dort wirkt der Stahl wie ν → 0,5. Gemessen am Rohr nach
  Hill (§ 5e.2): die Grenzlast trifft der tet10 8 × 4 trotzdem auf 0,5 %, ε_p,eq am
  innersten Punkt liegt 10 bis 15 % zu hoch.

Der Wunsch des Anwenders vom 20.09.2026 war ein Element, das erkennt, ob Biegung
gebraucht wird, und die Rechnung danach richtet. Entschieden ist (22.09.2026):
**tet10 an den Nachweisstellen, tet4 sonst.** Der Grund steht in den Zahlen des
Kragarm-Prüfkörpers (σ_v an der Nachweisstelle gegen 355 N/mm², § 5d): der tet4
liegt bei 90 / 405 / 2 295 Freiheitsgraden um −266 / −166 / −70 N/mm² daneben und
konvergiert nur mit der Elementlänge, der tet10 um +14 / +4 / +1 bei 405 / 2 295 /
15 147 und quadratisch. Überall tet10 macht die Matrix aber in jedem Körper größer
und dichter.

`elementwahl.vorschlag(model, vorlauf)` schlägt je Körper (`Element.group`) die
Ordnung vor, aus einem Vorlauf mit dem vorhandenen Netz. tet10 bekommt ein Körper,
wenn (a) an ihm ein Volumennachweis geführt wird und (b) der Vorlauf es verlangt:
**Biegung** — die Normalspannung in der Hauptrichtung wechselt über den Körper das
Vorzeichen mit vergleichbarem Betrag, Biegeanteil β = min(σ_max, −σ_min)/max|σ| ≥ 0,3
(reiner Zug 0, reine Biegung 1; am Kragarm im tet4-Vorlauf 0,85) — **oder** ein
bezogener Fehler des Zienkiewicz/Zhu-Schätzers ≥ 5 %. Ohne Nachweis bleibt es beim
tet4: dort zählt die Steifigkeit fürs Ganze, nicht die Spannung auf 1 N/mm². Eine
Vorgabe am Körper (`Volumenkoerper.ordnung` = 1 oder 2) gewinnt. Das Protokoll nennt
je Körper Ordnung und Grund („Elementwahl Balken: tet10 - Nachweis und Biegung
(Biegeanteil 0.85)“).

Geprüft an drei getrennten Körpern in einem Modell (`tests/test_elementwahl.py`):
Kragarm mit Nachweis → tet10, gezogener Stab mit Nachweis → tet4, Kragarm ohne
Nachweis → tet4. An den Nachweisstellen liegt die Wahl höchstens 0,14 N/mm² neben
„überall tet10“, mit 2 835 statt 5 265 Unbekannten. Am Bauteil setzt der Vernetzer die
Seitenmitten auf die wahre Geometrie; `elementwahl.tet4_zu_tet10` macht es für
Prüfkörper mit geraden Kanten. An der Grenze zu einem tet4-Körper bindet die
Assemblierung die Seitenmitten (§ 1.2, Übergang linear/quadratisch).

**Was tet10 am Drehlager kostet (M1, gemessen 23.09.2026, 00:42).** Ohne zu rechnen:
das Muster der Grundsteifigkeit (freie Translationen ohne Lager, ohne Kontakt und
Lagrange-Rand), PARDISO mtype 11, symbolische Analyse (iparm 18/19) und eine
numerische Faktorisierung mit 16 Threads; Maschine sauber (Fremdlast 0,16 Kerne);
`tests/messung_m1.py`:

| | Unbekannte | nnz(K) | nnz im Faktor | MFlops | Faktorisierung |
|---|---|---|---|---|---|
| heute (tet4) | 475 599 | 17,6 Mio. | 171 Mio. | 79 230 | 0,80 s |
| tet10 überall | 3 170 844 | 242,6 Mio. | 3 112 Mio. | 5 148 139 | 48,45 s |
| Verhältnis | 6,7 | 13,8 | 18,2 | 65 | 61 |

Die Absolutwerte gelten für das Muster, nicht für die Matrix des Lösers (dort mit
Kontakt 243 Mio. im Faktor und 3,41 s, gemessen von der Löser-Sitzung); aussagekräftig
sind die Verhältnisse. **tet10 überall auf dem heutigen Netz kostet rund das
Sechzigfache je Faktorisierung** und verfehlt das Zeitziel. Er lohnt sich nur auf
wenigen Körpern und nur, wenn er dort ein deutlich gröberes Netz trägt als heute;
beides muss M3 zeigen. Das Drehlager trägt heute keinen Volumenbereich mit Nachweis;
nach Angabe des Anwenders (23.09.2026) liegen die Nachweisstellen am Bauteil überall.
Die Teilvariante „tet10 nur in den Nachweiskörpern“ entfällt damit und ist nicht
gemessen.

## 6c Fehlerschätzer und adaptive Vernetzung (`netzfehler.py`, `adaptiv.py`)

„Fein genug" ist ohne Maß nicht entscheidbar. Das Maß ist der **Spannungssprung**
(Zienkiewicz/Zhu 1987): der lineare Tetraeder trägt eine konstante Spannung je
Element, die wahre Spannung ist stetig. Die volumengewichtet auf die Knoten gemittelte
Spannung σ* ist der wahren näher als die Elementspannung σ_e; der Unterschied ist der
Fehlerindikator in der Energienorm, mit C = D⁻¹:

    η_e² = ∫ (σ* − σ_e)ᵀ C (σ* − σ_e) dV = V/20 · [ (Σ_i e_i)ᵀ C (Σ_i e_i) + Σ_i e_iᵀ C e_i ],

e_i = σ*_i − σ_e an den vier Ecken (∫ N_i N_j dV = V/20 für i ≠ j, V/10 für i = j; gegen
eine Zufallsquadratur mit 200 000 Punkten auf 0,17 % genau). Ein gleichförmiger
Spannungszustand hat den Fehler null (gemessen 2·10⁻¹⁶ bei U = 18). Der bezogene
Gesamtfehler

    η_rel = √(Σ η_e²) / √(U² + Σ η_e²),   U² = Σ V_e σ_eᵀ C σ_e,

ist die Zahl, an der entschieden wird (Ziel 5 %). Über mehrere Lastfälle zählt je
Element der größte Fehler. Der Indikator ist eine Schätzung: er sieht den Fehler der
Spannung im Element, nicht den der Verschiebung, und an einer Singularität
(eingespannter Rand, Kontaktrand) bleibt er endlich, wo der wahre Fehler es nicht ist.

**Neue Kantenlänge.** Der zulässige Fehler wird gleich auf die N Elemente verteilt,
e_zul = ziel · √(U² + Σ η²) / √N, und jedes Element bekommt

    h_neu = h · (e_zul / η_e)^(1/p),   p = 1 (tet4), 2 (tet10),

begrenzt auf das Drittel bis Doppelte je Runde. Dazu drei Regeln, jede aus einer
Messung:

* **Budget.** Die Gleichverteilung unterstellt, dass N gleich bleibt; mit dem Drittel als
  kleinstem Schritt gibt ein Element bis zu 27 Kinder. Ohne Schranke lief die Platte mit
  Bohrung von 52 801 auf 1 300 025 Tetraeder in **einer** Runde. Die geschätzte neue
  Elementzahl, 5 · Σ (h/h_neu)³, darf höchstens das Dreifache von N sein; liegt sie
  darüber, werden alle neuen Kantenlängen um denselben Faktor angehoben. Die 5 ist
  gemessen: der Vernetzer legt um jede Quelle einen Kegel, die Hülle folgt mit, die
  Kanten werden etwa 0,8 h — Schätzung 3,0-fach, Netz 14,4- und 15,0-fach an der Platte
  mit fünf Bohrungen. Und die Schleife misst nach: liegt das neue Netz mehr als 15 %
  über dem Budget, vergröbert sie Körperkantenlängen und Feldpunkte um die Kubikwurzel
  des Überschusses und vernetzt einmal neu.
* **Spannungsschutz.** Die Energienorm mittelt über das ganze Bauteil; eine schon
  aufgelöste Kerbe hat dort einen kleinen Fehler und würde wieder vergröbert (Platte:
  σ_v max 497 → 391 N/mm² von einer Runde zur nächsten). Elemente mit mindestens der
  halben größten Vergleichsspannung werden nicht gröber — aber nur, wo es eine
  Konzentration gibt (größte Spannung über dem Doppelten des Mittels); bei
  gleichförmiger Spannung ist jedes Element „hoch", und nichts spricht gegen ein
  gröberes Netz.
* **Körper und Feld.** Je Körper wird das 90. Perzentil seiner neuen Kantenlängen
  seine eigene Kantenlänge (`netz.koerper_h`, vor Dichte und Ziellänge in
  `netzdichte.elementlaenge`) — neun Zehntel der Elemente dürfen so grob sein. Das
  letzte Zehntel hält das Größenfeld fein: Elemente unter 90 % der Körperkantenlänge
  werden Feldpunkte (Schwerpunkt, h_neu, Reichweite halbe alte Kante), vorab über Zellen
  je Größenstufe ausgedünnt, damit die Ausdünnung des Feldes nicht Hunderttausende
  Quellen sieht.

**Die Schleife** (`adaptiv.adaptiv_vernetzen`): vernetzen (`mesher.modell_vernetzen`,
die Folge der Oberfläche ohne Qt: Netzdichte, Fugen zurücksetzen, alte Netzknoten
löschen, Flächen, Volumen, Lasten, Fugen, starre Flächen, Stabenden, Lager) → rechnen
(`solver.solve_static`, die genannten Lastfälle) → schätzen → Körperkantenlängen und
Feldpunkte setzen → von vorn, bis das Ziel erreicht oder die Rundenzahl erschöpft ist.
Für die Dauer der Schleife ist `nebenflaechen_grob` an: der erste Durchgang ist grob,
der Schätzer holt zurück, was trägt. Alles, was die Schleife setzt, steht danach in den
Netzeinstellungen und wird mit dem Modell gespeichert; aus der Datei entsteht dasselbe
Feld wieder. Befehlszeile: `statik3d modell.json --adaptiv 2 --lastfall LF1 --speichern …`
(`--vernetzen` allein vernetzt ohne Schleife).

**Hexaeder, Keile, Pyramiden (21.09.2026).** Der Schätzer las nur Tetraeder; gesweepte und
zerlegte Körper blieben außen vor. Jetzt liest er alle Typen aus `ORDNUNG` (tet4/tet10,
hex8/hex20, pent6/pent15, pyr5): das Knotenmittel ist volumengewichtet über **alle**
Elemente am Knoten, das Integral der Energienorm des linear interpolierten Eckfehlers läuft
für Hexaeder, Keile und Pyramiden über die Gauß-Quadratur des linearen Typs
(`elements.solid._ISO`; das Produkt zweier trilinearer Felder ist je Richtung vom Grad 2,
zwei Punkte je Richtung integrieren es genau), für den Tetraeder weiter geschlossen. Ein
Sechsflächner mit einer Elementspannung wird dabei wie der Tetraeder stückweise konstant
gelesen — das ist konservativ. Prüfung an der gesweepten Platte 0,4 × 0,24 × 0,08 m mit
Bohrung: gleichförmige Spannung → Fehler null, U² = V·sᵀD⁻¹s, Quadraturvolumen = Elementvolumen
auf 10⁻⁹; unter Zug sammelt sich der Fehler an der Bohrung (`test_hexaeder_und_keile_im_schaetzer`).

Zwei Dinge musste die Schleife dafür dazulernen. Erstens **die Lagen des Sweeps folgen dem
Größenfeld** (`sweep._lagen_aus_weg`): die Lagen sind über den ganzen Körper gleich dick, und
wo das Feld die Grundfläche fein teilt, müssen sie mithalten — sonst entstehen flache
Hexaeder, und die Verfeinerung kommt quer zur Platte nicht an. Ohne die Regel fielen die Lagen
in der ersten adaptiven Runde von 3 auf 2 (441 → 482 Elemente, Fehler 13,7 → 12,8 %). Zweitens
**die Kalibrierung hängt am Elementgemisch** (`netzfehler.kalibrierung_fuer`): der Sweep legt
1,46-fach so viele Elemente wie Σ(h/h_neu)³ sagt (1 928 statt 1 323; zweite Runde 1,41-fach),
der Tetraedervernetzer 5-fach — darum `KALIBRIERUNG_HEX = 1,5`, dazwischen anteilig. Gemessen,
zwei Runden, Budget 3× (21.09.2026):

| Durchgang | Elemente | Lagen | η_rel |
|---|---|---|---|
| 1 (h = 30 mm) | 441 hex8/pent6 | 3 à 26,7 mm | 13,7 % |
| 2 | 1 456 | 7–8 à 10–11 mm | 13,4 % |
| 3 | 4 972 | 11–12 à 7 mm | **9,2 %** |

**Woher die Elementspannung kommt — ein Vorbehalt.** `res.solid_res` trägt für ein
**elastisches** Element mit mehreren Auswertepunkten den Punkt mit der **höchsten**
Vergleichsspannung, für ein **fließendes** dagegen nur die **Mitte** (Löser-Sitzung,
21.09.2026; der Grund dort ist ein Nachweis-Argument: an einer Ecke schießt die gemeldete
Spannung sonst über die verfestigte Fließgrenze). In einem Netz mit fließenden und
elastischen Elementen nebeneinander vergleicht der Sprung also **Maximum gegen Mitte** —
genau an der Fließgrenze, und ein Teil des gemessenen Sprungs ist dann der Regelwechsel
und nicht das Netz. Für tet4 ist das gleichgültig (ein Punkt), für hex8/pent6/pyr5 nicht.
Führt der Löser ein einheitliches **Mittel über die Gaußpunkte** als eigenes Feld
(`netzfehler.MITTELFELD`, heute `solid_mittel`), liest der Schätzer es bevorzugt — ohne
weitere Änderung. **Seit dem 22.09.2026 führt er es:** `res.solid_mittel` ist für jedes
Volumenelement das Elementmittel ∫σ dV / V, gewichtet über die Integrationspunkte desselben
Dehnungsoperators, aus dem Steifigkeit und Plastizität rechnen (für den tet4 sein einer Wert),
mit denselben Abzügen wie `solid_res` (Temperatur, D ε_p). Weil es linear in u ist, wird es
in Kombinationen exakt überlagert — anders als `solid_res`, dessen maßgebender Punkt je
Lastfall ein anderer sein kann (`tests/test_volumen.py`, `test_elementmittel`).

**Der Probelauf.** Die Schleife rechnet je Durchgang mit `solve_static(…, probelauf=True)`
— einem Kontaktschritt aus dem Anfangszustand der Fugen; sein Ergebnis ist ein Netzmaß,
kein Rechenergebnis (Kontaktkräfte um Größenordnungen daneben) und geht nur an den
Schätzer. Der Probelauf, wie ihn die Element-Sitzung gebaut hat (357d61d), lässt aber
das **Fließen** aus. Die Löser-Sitzung hat das am Drehlager gegen den vollen Lauf
gemessen (LF1 kalt, Vergleichsspannung je Element, 20./21.09.2026):

| | Zeit | L2 über alle Elemente | L2 über die 100 höchsten | dieselben 100 Spitzenelemente |
|---|---|---|---|---|
| ein Schritt, elastisch (wie gebaut) | 123,8 s | 52,2 % | 126,0 % | **54 von 100** |
| ein Schritt, plastisch | 198,8 s | **2,3 %** | **0,0 %** | **100 von 100** |
| voller Lauf | 633,4 s | – | – | – |

Elastisch liegt die Spitze bei 1 041 statt 387 N/mm² — Faktor 2,7, und zwar dort, wo
der Schätzer hinsieht. Ein elastischer Probelauf verfeinert also an den falschen
Stellen. Darum prüft die Schleife das Ergebnis: trägt es `probelauf` ohne
`plastizitaet`, obwohl das Modell fließt, rechnet sie diesen und die weiteren Lastfälle
**voll** und sagt es im Protokoll (`adaptiv.probelauf_elastisch`; `--probelauf ja`
erzwingt den Probelauf mit Warnung, `--probelauf nein` den vollen Lauf,
`test_probelauf_nur_mit_fliessen`). Sobald der Probelauf das Fließen behält — Bitte an
die Statik3D-Sitzung: Plastizität an, `max_iter = 1` —, ist er die billige Variante:
Faktor 3, nicht 48, denn bei 645 934 Elementen ist das Aufstellen der Matrix der
Brocken (124 s je Schritt), nicht das Lösen. Das Protokoll nennt je Durchgang die
Löserzahlen aus `Results.info` (`ndof`, `nfree`, `nnz_matrix`, `nnz_faktor`,
`zeit_faktorisierung`, `solver`, Kontaktschritte) und bei fließenden Modellen, ob das
Fließen mitgerechnet wurde.

Gemessen an der Platte 1 × 0,6 × 0,2 m mit einer Bohrung r = 100 mm und vier
Durchgangsbohrungen r = 20 mm, Zug 100 N/mm², Einspannung als Flächenlager, ein Prozess
(20.09.2026):

| | Elemente | Knoten | η_rel | σ_v max |
|---|---|---|---|---|
| h = 50 mm, wie bisher | 40 364 | 7 641 | 11,9 % | 490 N/mm² |
| h = 50 mm, Nebenflächen grob | 17 969 | 3 412 | 12,8 % | 343 N/mm² |
| h = 25 mm überall | 116 100 | 21 026 | 8,4 % | 412 N/mm² |
| adaptiv, zwei Runden, Start 50 mm grob, vor Kalibrierung und Spannungsschutz | 17 969 → 69 768 → 256 277 | 3 412 → 11 901 → 42 173 | 12,8 → 9,6 → 6,6 % | 343 → 498 → 392 N/mm² |
| adaptiv, zwei Runden, Start 50 mm grob, **mit** Kalibrierung und Spannungsschutz | 17 969 → 61 758 → 192 235 | 3 412 → 10 615 → 31 799 | 12,8 → 10,0 → 7,2 % | 343 → 351 → 422 N/mm² |

Mit Kalibrierung hält jede Runde das Budget ohne Zwischenlauf (3,4- und 3,1-fach, die
ganze Schleife 77 s statt 302 s), und die Spannung an der Bohrung steigt von Runde zu
Runde statt zu fallen. Auf diesem Beispiel ist das gleichmäßige Netz mit 25 mm
(116 100 Elemente, 8,4 %) dem adaptiven (192 235, 7,2 %) ebenbürtig:
die Einspannung ist eine Liniensingularität, an der sich der Indikator sammelt — ein
gleichmäßig feineres Netz ist an diesem Beispiel deshalb konkurrenzfähig; `netz.h_min`
begrenzt, wie fein die Schleife dort wird. Am Drehlager tun Kontaktränder dasselbe.
Was am Drehlager selbst herauskommt, ist **nicht gemessen** — das Modell lag der
Vernetzer-Sitzung nicht vor.

## 7 Parallelisierung

* Elementschleifen (Assemblierung, Nachlauf) werden ab 1500 Elementen in
  Blöcke zerlegt und auf einen Prozess-Pool verteilt; das Modell wird je
  Prozess einmal übertragen.
* Die Vernetzung übergibt Modell und Netzkarten den Arbeitsprozessen **über
  eine Datei**, nicht als Startargument des Pools. Unter Windows (`spawn`)
  startet der Pool seine Prozesse nacheinander, und Startargumente von 1,7 MB
  passen nicht in die Rohrleitung, bevor das Kind hochgefahren ist: am
  Drehlager mit 31 Prozessen wartete `Pool()` 25,8 s (31 × 0,83 s), bevor der
  erste Arbeiter antwortete. Mit einem Dateipfad steht der Pool nach 1,8 s,
  die Arbeit beginnt nach 4,3 s; die Datei wird nach dem Lauf gelöscht
  (`test_arbeiter_laden_aus_datei`). Die Prüfung sieht auf die Datei, die
  der Lauf selbst angelegt hat (`statik3d_netz_*.pkl`), und nicht auf den
  Inhalt des Temp-Ordners: den teilen sich alle Sitzungen des Anwenders. Der
  frühere Vergleich des Ordners vor und nach dem Lauf fiel am 23.09.2026
  über Dateien, die parallel laufende Prüfungen anderer Sitzungen
  währenddessen dort anlegten, obwohl der Lauf seine eigene gelöscht hatte;
  `test_arbeiterdatei_nur_dieses_laufs` stellt das mit einem zweiten Prozess
  nach und verlangt umgekehrt, dass die Prüfung durchfällt, wenn der
  Vernetzer nicht aufräumt.
* **Bilanz am Drehlager** (108 Körper, 1.812.423 Elemente, 31 Prozesse,
  gleiche Netze in allen Läufen, gemessen am 10.09.2026):

  | Stand | Pool-Lücke | abgebildete Körper | V31 (kritischer Pfad) | Körper gesamt | gesamt |
  |---|---|---|---|---|---|
  | alter Vernetzer (81d9192, 2.477.062 Elemente) | 30 s | 36 s | — | 604 s | 679 s |
  | flache Tetraeder bis nach der Glättung | 30 s | 36 s | 241 s | 315 s | 381 s |
  | + Modell über Datei, Karten einmal je Lauf | 2 s | 3 s | 248 s | 262 s | 328 s |
  | + Gitterzelle 2 × Median, höchstens 0,5 h | 2 s | 3 s | 152 s | 166 s | 236 s |

  Was bleibt, ist der kritische Pfad: ab 120 s rechnen nur noch fünf Körper,
  am Ende V31 allein, während 30 Prozesse warten. Der nächste Schritt dort ist
  die Zahl der Neuaufbauten der Delaunay-Zerlegung (Startpunkte aus dem
  Größenfeld statt gleichmäßig bei h), danach Lasten verteilen (42 s) und
  Kontaktfugen (24 s).
* Grobkörnige Aufträge (Kombinationen bei Kontakt, Nachweise vieler Stäbe,
  Parameterstudien) laufen im lokalen Prozess-Pool oder auf der
  Rechnerfarm (siehe Rechnerfarm.md).
* Die Ergebnisse sind unabhängig von der Anzahl der Prozesse (getestet).
* Fällt der Prozess-Pool aus (kein `fork`/`spawn` möglich, ein
  Arbeitsprozess stirbt), wird derselbe Block seriell nachgerechnet. Ein
  Fehler **aus** der Elementschleife dagegen ist ein Befund am Modell und
  wird unverändert weitergereicht - er darf nicht in einem stillen
  seriellen Neuversuch verschwinden. Hinweise gehen nur dann nach
  `sys.stderr`, wenn es einen gibt: die gepackte Windows-Fassung läuft ohne
  Konsole.

### 7.1 Ein Auftrag trägt kein Modell (21.09.2026)

Die Stabnachweise werden ab 24 Stäben auf Aufträge verteilt
(`ec3.design.check_members`). Bis zum 21.09.2026 stand in **jedem** Auftrag ein
eigenes `model.to_dict()`. Das ist harmlos bei einem Rahmen und fatal bei einem
Modell, das fast nur aus Netz besteht.

Am Drehlager des Anwenders — 162 166 Knoten, 662 889 Elemente, 239 MB als
Datei — waren das rund **228 MB je Auftrag bei 64 Aufträgen, etwa 14,6 GB**
durch die Prozess-Pipes. Der Lauf stand nach **698 Minuten bei 94 %** und kam
nicht weiter; ein Arbeitsprozess war vorher gestorben mit

    AssertionError   multiprocessing/connection.py, _get_more_data

— die Pipe brach beim Lesen des Auftrags. Die Rechnung selbst war zu diesem
Zeitpunkt fertig (das Protokoll endet mit „Umhüllende gebildet"); es hingen
allein die 64 Nachweise von 64 Rundstäben, die seriell Sekunden gebraucht
hätten.

Modell und Ergebnisse gehen jetzt **einmal** in eine Datei
(`ec3.design._paket_schreiben`), der Auftrag trägt nur ihren Pfad, und jeder
Arbeitsprozess liest sie **einmal** und behält sie (`jobs._NACHWEIS_PAKET`).
Das ist dieselbe Lösung wie im stehenden Pool
(`parallel._init_worker_datei`). Gemessen an Prüfkörpern, ein Auftrag:

| Modell | alt | neu | Faktor |
|---|---|---|---|
| 17 Knoten, 16 Elemente | 0,058 MB | 76 Byte | 757 |
| 360 Knoten, 1 096 Elemente | 0,478 MB | 76 Byte | 6 286 |
| 2 214 Knoten, 8 656 Elemente | 2,996 MB | 76 Byte | 39 416 |

Die alte Last wächst linear mit dem Netz, die neue nicht. Nachweis
`tests/test_ec3.py::test_nachweisauftrag_traegt_kein_modell`. Der alte Weg
(`model`/`results` im Auftrag) bleibt bestehen — die Farm schickt Aufträge
über das Netz, wo kein gemeinsamer Dateipfad gilt.

**Dazu gehört ein zweiter Punkt, der den Fehler unlesbar machte.** Die gepackte
Oberfläche läuft ohne Konsole; PyInstaller setzt `sys.stdout` und `sys.stderr`
dann auf `None`. Fällt in einem Arbeitsprozess eine Ausnahme an, schreibt
**CPython selbst** den Traceback nach `sys.stderr`
(`multiprocessing/process.py`, `_bootstrap`) — und stirbt dabei an

    AttributeError: 'NoneType' object has no attribute 'write'

Der Anwender sieht dann einen Dialog „Unhandled exception in script" mit
diesem nichtssagenden Fehler, während der eigentliche Grund verdeckt bleibt.
`run_gui._stroeme_sichern` legt vor `freeze_support()` einen stillen
Ersatzstrom unter, den die Arbeitsprozesse erben. `parallel._melden` tat das
schon für die eigenen Meldungen; die Bibliothek erreichte es nicht.

### 7.2 Ein neu vernetztes Modell muss dasselbe rechnen (21.09.2026)

Diese Prüfung fehlte, und ihr Fehlen hat einen Tag gekostet. Am Drehlager
sprang die größte Verschiebung beim Neuvernetzen von **0,2716 auf 1,2718 mm** —
Faktor 4,7, rein elastisch, beide Läufe kontaktkonvergiert. Die Spannung blieb
dabei richtig (388,0 gegen 387,4 N/mm²): das Tragwerk **wandert als Ganzes**
(Mittelvektor −0,685; −0,057; −0,242 mm, Körpermaxima alle um 1,15 mm), es
verformt sich nicht anders. Durch Messung ausgeschlossen wurden der Sweep, die
entarteten Keile, die Plastizität, `Model.netzknoten_loeschen` und der
Messweg; der Fehler tritt auch auf dem Stand **vor** dem neuen Vernetzer auf.

`tests/test_neuvernetzen.py` ist die Prüfung, die das hätte finden müssen:
zwei Körper mit **eigenen** Trennflächen (so kommt es aus RFEM, die Netze
passen nicht Knoten für Knoten), eine Kontaktbedingung dazwischen, ein
**geometriegebundenes** Flächenlager und Eigengewicht — vernetzen, rechnen,
noch einmal vernetzen, wieder rechnen, vergleichen. Geometriegebunden ist der
Kern: Lager und Lasten müssen das Neuvernetzen überleben, ohne dass jemand sie
nachsetzt, und genau das tut `mesher.modell_vernetzen` im letzten Schritt.

**Ein Fehler ist damit gefunden und behoben.**
`Model._knotenverweise_abbilden` zog `ContactPair.slave_nodes` nach, aber
**nicht `master_faces`** — und das sind Knotenlisten (drei oder vier Knoten je
Facette, `contact.py` liest sie als Knotennummern). Nach dem Löschen eines
Knotens zeigten die Facetten auf fremde Knoten: die Fuge trug an der falschen
Stelle, **ohne dass eine Spannung falsch geworden wäre** — genau das Bild einer
Starrkörperbewegung. Ohne die Behebung wandern in der Prüfung 16 von 16
Facetten nicht mit.

**Der Faktor 4,7 ist erklärt — und er hatte mit dem Vernetzen nichts zu
tun.** Die Auflösung steht in § 7.3: das **gespeicherte** Modell hatte seine
Bemessungslast verloren. 1,2717 mm ist der belastete Zustand, 0,2716 mm der
nahezu unbelastete; die gerechnete Auflagersumme des geladenen Modells war
2717 N gegen rund 10 MN Sollast. Auch die Kontaktschritte (167 gegen 95)
folgen daraus: unter Last braucht die Aktivmenge länger.

Der Weg dahin ist es wert, festgehalten zu werden, weil auf ihm **vier**
Vermutungen gefallen sind, die alle plausibel klangen:

1. *Der Sprung kommt vom Netz.* Gefallen: derselbe Netzstand rechnet im
   Prozess anders als nach Speichern und Laden — ein Prozess, ein Netz.
2. *`to_dict` verliert einen Modellzustand.* Verengt statt gefallen: 63 Felder
   des Modellobjekts unterscheiden sich **nicht**. Genau ein Feld tat es,
   und es war `load_cases['LF1'].face_loads` — 2750 gegen 0.
3. *Das Tragwerk wandert als Ganzes.* **Gefallen**, obwohl der Mittelvektor
   der Verschiebung (−0,685; −0,057; −0,242 mm, Betrag 0,7287 mm) genau zum
   Mittel der Beträge (0,7425 mm) passte und damit eine reine Verschiebung
   nahelegte. Eine Ausgleichsrechnung u ≈ t + ω × x über alle Knoten hat es
   widerlegt: nach Abzug von t und ω blieben die **Reste** beider Läufe um
   803 % verschieden. Die Läufe tragen wirklich anders ab — weil der eine
   belastet war und der andere nicht.
4. *Ein Bauteil hält nur über den Kontakt und rutscht.* Unnötig geworden.

Die Lehre daran ist nicht „mehr messen", sondern **was** man misst: die
Verschiebung war drei Sitzungen lang das Maß, und sie zeigt nur die Wirkung.
Die Ursache stand in der **Last**, und die hat vorher niemand nachgezählt —
eine Zeile `solver.case_loads(m, {"LF1": 1.0}, None)` hätte es an jedem Tag
davor gezeigt.

### 7.3 Ein geladenes Modell muss dieselbe Last tragen (21.09.2026)

Lasten, die an der **Geometrie** hängen — eine Flächenlast auf einer Fläche,
eine Linienlast auf einer Linie —, können erst wirken, wenn es dort Elemente
gibt. `Model.lasten_verteilen` legt sie auf die Elementseiten und kennzeichnet
die entstandenen Elementlasten mit `_geo`. Gespeichert werden sie
**absichtlich nicht** (`LoadCase.to_dict` schreibt nur `eigene(...)`): sonst
lägen sie nach dem nächsten Verteilen doppelt auf dem Netz.

Erzeugt hat sie beim Laden aber **niemand wieder.** `lasten_verteilen` hing am
Vernetzen, und ein geladenes Modell hat schon ein Netz — die Oberfläche
vernetzt vor der Rechnung nur, was keines hat (`_vor_rechnung_vernetzen`
kehrt bei vollständigem Netz sofort zurück). Der Anwender öffnete seine Datei,
drückte Berechnen und rechnete **ohne seine Bemessungslast**.

| Drehlager, LF1 „Bemessungslast im GZT" | Σ F_x | Σ F_z | `face_loads` |
|---|---|---|---|
| gespeichertes Modell, wie geladen | 0,0 N | 0,0 N | 0 |
| dasselbe Modell nach dem Vernetzen | −3 968 599 N | −9 259 435 N | 2 750 |
| nach Speichern und Laden | 0,0 N | 0,0 N | 0 |

Die **Norm** des Lastvektors täuschte dabei (5,385·10⁶ gegen 5,424·10⁶ N) —
sie steckt fast ganz in sechzehn Temperaturlasten, die sich selbst ausgleichen.
Erst die **Resultierende** zeigt es: 9,26 MN senkrecht fielen auf exakt null.

**Behoben** in `Model.from_dict`: hat das geladene Modell Elemente und
Objektlasten, wird einmal verteilt. Das Verteilen ist wiederholbar (es räumt
die `_geo`-Lasten vorher weg), und ohne Netz oder ohne Objektlasten kostet es
nichts.

**Was es kostet, und was das kostete.** Die erste Fassung machte das Laden des
Drehlagers von 6,6 auf **77,8 s** — 1 013 100 verteilte Lasten über 422
Lastfälle. Gemessen an einem Balken mit einem Lastfall waren es 7,9 µs je
Last, am Drehlager aber 69 µs. Der Unterschied lag nicht an der Modellgröße
(von 250 auf 128 000 Elemente ändert sich nichts) und nicht an der Müllabfuhr
(abgeschaltet dieselbe Zeit) — **840 der 2262 Geometrielasten sind
projiziert**, und keine einzige hat Bereich oder Verlauf. Zwei Dinge waren
daran teuer:

* `_geometrielast_legen.nimm` berechnete die **Seitenmitte für jede Seite** —
  auch für Lasten, die sie ohne Bereich und Verlauf nie lesen, und auch für
  die Hälfte der Seiten, die unmittelbar danach am Windschatten scheitert.
  Jetzt steht die Windschattenprobe zuerst, und die Mitte wird nur berechnet,
  wenn jemand sie liest.
* `_seitennormale` rief `np.cross` auf. Für einen Dreivektor geht das über
  `moveaxis` und `normalize_axis_tuple` und kostete im Profil **0,150 von
  0,312 s**. Ausgeschrieben ist es dieselbe Rechnung.

| Drehlager laden | |
|---|---|
| JSON lesen | 3,0 s |
| `from_dict` ohne Verteilen | 2,89 s |
| Verteilen, erste Fassung | rund 70 s |
| **Verteilen, jetzt** | **12,48 s** (12,3 µs je Last) |
| `from_dict` mit Verteilen | **14,94 s** |

Faktor 5,6, und die Resultierende bleibt auf die Stelle dieselbe
(−3 968 598,9 / −0,0 / −9 259 435,0 N). Die verbleibenden 12,3 µs sind die
Arbeit selbst: Normale je Seite, Ablehnung im Windschatten, ein `FaceLoad`.

**Warum die Prüfungen es nicht fanden**, obwohl es zwei gab, die genau
hinsahen — das ist der lehrreiche Teil:

* `test_lasten.test_speichern_linienlast_zwang` prüfte
  `len(lc.beam_loads) == 0` und rief danach `m2.lasten_verteilen()` **von
  Hand** auf. Sie hielt damit die *Speicherregel* fest und schrieb den Fehler
  fest: dass niemand von selbst verteilt, hat sie nie geprüft.
* `test_lasten.test_temperatur_objektlast` trug den Namen „Speichern ohne die
  abgeleiteten Lasten, **Laden verteilt neu**" — und prüfte
  `len(lc.temp_loads) == 0`. Name und Zusicherung widersprachen sich seit dem
  Tag, an dem sie geschrieben wurde. Der Name hatte recht.

Die neue Prüfung `test_geladenes_modell_traegt_dieselbe_last` sieht darum
nicht auf die **Zahl** der Lastobjekte, sondern auf den **Lastvektor** selbst
(`solver.case_loads`): gespeichert und geladen muss dieselbe Resultierende
herauskommen, in allen drei Richtungen, und zweimaliges Laden darf sie nicht
verdoppeln.

### 7.3a Der Lastverlust hatte Geschwister (22.09.2026)

Die Frage des Anwenders nach § 7.3 lautete: *„oder ist das wieder ein
Zählfehler? ggf auch ein Speicher- und Öffnen-Fehler im Format"*. Beides war
zu beantworten, und die Antwort ist zweigeteilt.

**Ein Zählfehler war es nicht.** Gemessen wurde die Wirkung — der Lastvektor
selbst über `solver.case_loads`, ohne zu rechnen. Zählfehler waren die drei
*Prüfungen*, die es nie fanden: sie zählten `len(face_loads)` statt die
Resultierende zu messen.

**Ein Formatfehler war es sehr wohl — und nicht der einzige.** Eine
systematische Durchsicht des Speicher- und Ladewegs (sieben Bereiche, jeder
Befund von einem Gegenprüfer zu widerlegen versucht) fand **sechs weitere
Stellen** desselben Musters. Die schwerste ändert die Physik:

> **Die Lochleibungsgrenze verschwand beim Speichern.**
> `ContactPair.knotenflaechen` ist {Knotennummer: Einflussfläche}, mit
> **ganzzahligen** Schlüsseln gebaut (`fugen._passungsdaten`) und mit
> ganzzahligen gelesen (`contact.py`, Lochleibungsgrenze). JSON kennt nur
> Zeichenketten als Schlüssel; nach dem Öffnen fand die Abfrage nichts und
> gab 0,0 zurück — und **0,0 heißt dort „keine Grenze"**. Gemessen:
> **2,100 kN vor dem Umlauf, 0,000 kN danach.** Die Passung trug damit
> unbegrenzt, statt bei der Grenzpressung zu fließen. Still, ohne Meldung, in
> jedem gespeicherten Modell mit Passung.
>
> Dasselbe Muster ist beim Lagerverhalten (`behaviour`) seit jeher behoben
> (`model.py`, `_lager_aus_dict`: `{int(k): ...}`) — hier war es vergessen.
> Behoben in `Model.from_dict`;
> `tests/test_kopie.py::test_ganzzahlige_schluessel_ueberleben_den_umlauf`
> prüft die **Wirkung** (die Grenzkraft), nicht den Schlüsseltyp: ein Typ ist
> leicht zu prüfen und sagt nichts darüber, ob jemand ihn liest.

Die übrigen fünf, alle belegt, keiner widerlegt — sie sind aufgeschrieben,
damit sie nicht verlorengehen:

| | Stelle | Folge |
|---|---|---|
| Ein im Browser **kopierter Lastfall** verliert seine Geometrielasten | `web/server.py` `_op_copy_case` | derselbe Ausfall wie § 7.3, nur beim Kopieren statt beim Öffnen; der Desktop macht es mit `copy.deepcopy` richtig |
| Die Weboberfläche **zählt abgeleitete Lasten als eingegebene** | `web/server.py` `_loads_of` (`asdict` kennt `_geo` nicht) | „Last entfernen" trifft über den Index eine abgeleitete Last: der Klick sieht erfolgreich aus, ist folgenlos und verschiebt den Index der echten Last |
| **Eigenfrequenzen, Eigenformen, Knicklastfaktoren** werden nicht gespeichert | `ergebnisse.py` packt nur Lastfälle und Kombinationen | nach dem Öffnen fehlen die Berichtskapitel ersatzlos; die Rechnung sieht vollständig aus |
| Die gerechnete **Stellungsreihe** fehlt nach dem Öffnen | `gui/main.py` schreibt nur `self.analysis` | die ZTV-ING-Prüfliste meldet „keine Stellungsreihe angelegt", obwohl die Stellungen in der Datei stehen |
| **Knicklängen** werden geschrieben, aber nicht zurückgelesen | `ergebnisse.py` | der Bericht druckt sie, die Oberfläche sagt, es gebe sie nicht — zwei Aussagen über dieselbe Rechnung |

**Was diese sieben gemeinsam haben, ist die Lehre.** Keiner stürzt ab, keiner
meldet etwas, jeder gibt eine plausible Zahl zurück. Ein Format, das
abgeleitete Daten bewusst weglässt, ist richtig — aber jede weggelassene
Größe braucht eine Stelle, die sie beim Laden **wieder erzeugt**, und eine
Prüfung, die die **Wirkung** misst statt die Anwesenheit.

### 7.4 Rechenketten trotz eingefrorener Zustände (22.09.2026)

Am Drehlager liefen **alle 422 Lastfälle hintereinander in einem Prozess** —
die Elementschleifen parallel im Pool, die Lastfälle nacheinander. Der erste
Grund dafür ist die Vorgabe `ketten = 1` (`parallel.py`, „nacheinander");
beim Anwender ist nichts anderes eingestellt. Wären die Ketten
eingeschaltet gewesen, hätte eine zweite Zeile sie gesperrt (eine frühere
Fassung nannte nur diese und sagte „nicht, weil die Rechnung es verlangte,
sondern wegen einer Zeile"; Nachprüfung der Lösersitzung vom 22.09.2026):

```python
if system is None and not referenzen and len(names) > 1:
```

`referenzen` sind die eingefrorenen Zustände der Ermüdungslasten
(`ermuedungsreferenzen`): der erste Zustand jeder Ermüdungslast wird
nichtlinear gerechnet, die weiteren mit seinem eingefrorenen Kontaktzustand
linear. Am Drehlager sind das **161 von 164 Zuständen** (Programmprotokoll
vom 19.09.2026: „161 Zustände werden mit dem eingefrorenen Kontaktzustand
des ersten Zustands ihrer Ermüdungslast linear gelöst"); 261 der 422
Lastfälle rechnen nichtlinear. `referenzen` war also nie leer, und die
Sperre hätte immer gegriffen. (Eine frühere Fassung schrieb 117 — ebenso der
Kommentar im Löser und die Nachricht zu 7d03525; Nachprüfung der Lösersitzung vom 22.09.2026.)

**Der Grund für die Sperre war echt.** `_einfrieren` findet den eingefrorenen
Zustand nur, wenn seine Referenz **in demselben Lauf** schon gerechnet wurde;
liegt sie in einer anderen Kette, gibt es still `(None, None)` und der Zustand
rechnet voll nichtlinear. Kein falsches Ergebnis — aber der ganze Gewinn ist
weg, und **niemand sieht es**. Ein stiller Rückfall ist schlimmer als ein
lauter Fehler.

**Die Kur ist nicht, die Sperre zu lösen, sondern anders zu schneiden.**
`_referenzgruppen` fasst eine Referenz und alle Zustände, die sie einfrieren,
zu einer **unteilbaren Gruppe** zusammen — über Zusammenhangskomponenten, weil
ein Zustand grundsätzlich selbst Referenz eines dritten sein könnte.
`_ketten_teilen` schneidet nur an Gruppengrenzen. Eine Gruppe, die größer ist
als die Zielgröße, bekommt ihre eigene Kette; die Ketten werden dadurch
ungleich lang. Das ist die richtige Seite zum Irren: **ungleiche Ketten kosten
Wartezeit, eine verlorene Referenz kostet einen vollen nichtlinearen
Lastfall.**

Der zweite Teil der Sperre saß im Auftrag: `jobs._job_solve_kette` gab
`referenzen` nicht weiter. Ohne das hätte die neue Aufteilung nichts genützt —
in der Kette wäre jeder Zustand voll gerechnet worden, und zwar still.

**Wo der Hebel wirklich sitzt — und wie klein er am Drehlager ist.** Die
Zustände **einer** Ermüdungslast hängen alle an derselben Referenz und bilden
damit eine einzige Gruppe — da gibt es nichts zu teilen. Der Gewinn entstünde
**zwischen** den Lasten. Am Drehlager sind es zwar 50 Ermüdungslasten, sie
fallen aber zu nur **drei** Referenzgruppen zusammen (LF401 mit 79, LF601 mit
81 und LF402 mit 1 eingefrorenen Zustand), weil spätere Lasten den schon
eingefrorenen ersten Zustand weiterreichen. Bei sechs Ketten ergibt
`_ketten_teilen` — nur über die Namen nachgebildet, ohne Löser — Ketten mit
80/2/82/71/71/116 Lastfällen, davon nichtlinear 1/1/1/71/71/116: drei Ketten
haben kaum etwas zu tun, die längste trägt 116 der 261 nichtlinearen. Ein
Gewinn durch Ketten ist am Drehlager **nicht gemessen**; nach der Kernlast
auf 16 physischen Kernen ist er auf höchstens rund Faktor 1,4 geschätzt
(eine frühere Nachricht nannte „Faktor 2,6, 81 h → 30 h" und rechnete dabei
mit 32 statt 16 Kernen).

**Die Threads der Ketten.** Bis zum 22.09.2026 bekam jede Kette die volle
eingestellte Threadzahl: beim Anwender stehen 31 in `einstellungen.json`,
sechs Ketten forderten damit je 31 Löser-Threads — MKL kappt nur innerhalb
eines Prozesses auf die 16 physischen Kerne, also bis zu 96 Threads auf 16
Kernen. Jetzt ist die Einstellung das Budget des Rechners und wird geteilt
(`threads_je_kette`: 31 bei sechs Ketten → je 5), wie es ohne Einstellung
schon immer war.

**Und sie ändert die Zahlen.** Das ist der Punkt, der dazugehört:

| | eine Kette | zwei Ketten |
|---|---|---|
| eingefrorene Zustände | 8 | **8, dieselben** |
| erste Kette, max \|Δu\| | — | **0,000 (bitgleich)** |
| zweite Kette, max \|Δu\| | — | 4,70·10⁻⁹ m (**1,2·10⁻³** relativ) |
| Kontaktschritte des zweiten Kopfes | 5 (warm) | **21 (kalt)** |

Die erste Kette sieht dieselbe Folge wie der Einzellauf und rechnet bitgleich.
Die zweite beginnt mit einem **kalten Kopf**: ihr erster Lastfall startet aus
der Geometrie statt aus dem Kontaktzustand des Vorgängers, braucht 21 statt 5
Schritte — und landet in einem geringfügig anderen Zustand, den die
eingefrorenen Zustände dahinter erben.

Der Warmstart ist also nicht nur eine Beschleunigung; er bestimmt mit, **wo**
die Kontaktiteration zur Ruhe kommt. Dass der kalte Kopf dabei der
unabhängigere und damit eher vertrauenswürdigere Wert ist, macht die Sache
nicht kleiner: **wer die Zahl der Ketten ändert, ändert die Ergebnisse in der
dritten Stelle.** Wer zwei Läufe streng vergleichen will, lässt die Kettenzahl
gleich — und setzt zusätzlich `MKL_CBWR=AUTO` (§ 7.5).

`tests/test_solver_ext.py::test_ketten_mit_eingefrorenen_zustaenden` hält alles
davon fest: keine Gruppe wird zerschnitten (k = 1, 2, 3, 4, 9), jeder Lastfall
kommt genau einmal vor, es entstehen nie mehr Ketten als angefordert, dieselben
Zustände sind eingefroren wie ohne Ketten, die erste Kette ist bitgleich, die
zweite weicht ab — aber nur in der dritten Stelle.

**Ein Fehler, der beim Bauen auffiel und hier steht, weil er wiederkommen
wird:** die erste Fassung schnitt jede Gruppe ab, die die Zielgröße sprengte,
und erzeugte damit **mehr Ketten als angefordert** — aus k = 3 wurden vier. Da
`_cases_in_ketten` so viele Prozesse startet, wie es Blöcke gibt, und eine
Kette am Drehlager 9,5 GB belegt, wären das 38 statt 28,5 GB gewesen. Eine
Aufteilung, die mehr Teile macht als bestellt, ist kein Randfall — sie ist ein
Speicherfehler mit Anlauf.

**Und was zwei Gegenlesungen daran gefunden haben.** Der Umbau wurde nach dem
Bauen zweimal angegriffen — einmal er selbst, einmal die Kuren, die aus der
ersten Runde folgten; jeder Vorwurf ging an einen Gegenprüfer, dessen Auftrag
das Widerlegen war. Von 33 Vorwürfen der ersten Runde hielten 7, von 26 der
zweiten 8. **Drei davon waren neue Fehler, die der Umbau selbst eingeführt
hatte:**

| | |
|---|---|
| Der Kettenaufruf lag **vor** dem `try`, das jeden fertigen Lastfall rettet (`_teil_merken`, § 19.09.2026). Brach eine Kette, waren die Ergebnisse **aller anderen** weg — auf genau dem Weg, der für das Drehlager gebaut wurde. |
| Der neue Auftragsschlüssel `referenzen` brachte eine Rechenhilfe älteren Stands mit `TypeError` zu Fall. Er wird jetzt nur mitgegeben, wenn es welche gibt. |
| Die Referenzordnung galt über **alle** Lastfälle und zerriss damit die Ordnung nach Situationen, die derselbe Docstring zusichert. Drei unabhängige Blickrichtungen fanden das getrennt. |

Die zweite Runde traf eine dieser Kuren selbst: eine Fassung zog die
Lastfallmarken nach, damit die Rechenliste ihre Posten abschließt. Sie ist
**zurückgenommen** — die Schleife stand vor der Rettung und in keinem `try`,
also hätte ein Abbruch genau das mitgenommen, was die Rettung sichern sollte;
der gemeldete Anteil sprengte das Fenster der Lastfälle (Balken auf 100 %, dann
zurück auf 60 %); und die Marken kommen ohnehin erst, wenn alle Ketten zurück
sind, sodass ein Lastfall 4:12:00 behauptet hätte und 421 je 0:00.

**Was davon als Einschränkung bleibt, steht hier statt in einer Anzeige:** auf
dem Kettenweg schließen die Zeilen der Rechenliste erst am Ende des Laufs, und
der Abbruch greift zwischen den Ketten, nicht zwischen den Lastfällen. Eine
falsche Anzeige wäre schlechter als eine ausbleibende.

### 7.5 Zwei Läufe sind nicht bitgleich (22.09.2026)

Der Gleichungslöser ist **mit mehreren Kernen nicht wiederholbar**. Gemessen an
einem 50×50×50-Laplace (125 000 Zeilen, 860 000 Nichtnullen), dreimal dieselbe
Matrix und dieselbe rechte Seite, Threadzahl über `_mkl_threads_setzen`; die
Zeiten an einem 60³-Gitter (216 000 Zeilen, 16 Threads):

| `MKL_CBWR` | 1 Thread | 16 Threads | Zeit |
|---|---|---|---|
| nicht gesetzt | bitgleich | **nicht bitgleich** (2,22·10⁻¹⁵, 4,9·10⁻¹⁶ relativ) | 3,707 s |
| `AUTO` | bitgleich | bitgleich | 4,186 s (+13 %) |
| `AVX2` | bitgleich | bitgleich | 4,123 s (+11 %) |
| `COMPATIBLE` | bitgleich | bitgleich | 5,078 s (+37 %) |

MKL summiert die Zahlenphase der Faktorisierung parallel; wie die Arbeit auf
die Threads fällt, hängt am Zeitverhalten. Das ist Intels *conditional
numerical reproducibility* — und `AUTO` ist der richtige Schalter, wenn zwei
Läufe **auf derselben Maschine** vergleichbar sein müssen: er bindet an deren
Befehlssatzbranche, statt wie `COMPATIBLE` auf SSE2 zurückzufallen.

**Das Aufstellen ist davon nicht betroffen — auch nicht bei verschiedener
Prozesszahl.** `parallel.Arbeiter.map` benutzt `pool.map` (reihenfolgetreu),
jeder Block legt seine Elementmatrizen an ihrer **Position** ab
(`_matrix_chunk`: `out[pos] = …`), und die Blöcke werden der Reihe nach
aneinandergehängt. Die Tripel stehen damit bei jeder Blockgröße in derselben
Elementreihenfolge, und die Summation von `coo` nach `csr` ist festgelegt.
Abweichen kann nur, **ob ein Sechsflächner im Stapel oder einzeln**
gerechnet wird: gestapelt wird ab acht Sechsflächnern gleichen Werkstoffs in
einem Block, und das hängt an den Blockgrenzen; beide Wege unterscheiden sich
um bis zu 6·10⁻¹⁶. (Eine frühere Fassung sagte, andere Blöcke hießen andere
Summationsreihenfolge — das ist falsch; Nachprüfung der Lösersitzung vom 22.09.2026.)

**Warum das mehr ist als eine Fußnote.** 4,9·10⁻¹⁶ ändern keine Spannung —
solange nichts an einer Schwelle steht. Ob sie am Drehlager genügen, um den
Kontaktweg zu verzweigen, ist **nicht belegt**. Gemessen ist: das
ausgelieferte Programm nahm dort in drei Läufen denselben Weg (höchstens
0,0004 N/mm² auseinander); zwei Läufe einer Versuchsfassung mit symmetrischer
Zerlegung nahmen verschiedene Wege und lagen um bis zu 273 N/mm² auseinander
(§ 3, Deckel). Eine frühere Fassung sprach hier von
„derselbe Lauf, 150 und 162 Kontaktschritte, vierte Stelle der Verformung":
die beiden Läufe stammten aus zwei verschiedenen Programmständen, einen
wiederholten Lauf gab es nicht, und die Abweichung lag in den Spannungen weit
über der vierten Stelle (Nachprüfung der Lösersitzung vom 22.09.2026). Ein Lauf, der als „ergebnisgleich"
abgenommen wird, ohne dass diese Streuung ausgeschlossen wurde, sagt nichts
über die Änderung aus, die er belegen sollte — sondern nur, dass zwei Läufe
zufällig denselben Weg genommen haben. Ob `MKL_CBWR=AUTO` die Wege am
Drehlager gleich macht, misst die Lösersitzung gerade.

Für die Praxis heißt das: **jede Gleichheitszusage an einem Kontaktmodell
gehört mit `MKL_CBWR=AUTO` gemessen**, und wenn sie es nicht wurde, gehört das
dazugesagt. In der Auslieferung steht der Schalter nicht — 13 % zahlt man nicht
dauernd für eine Eigenschaft, die man nur beim Vergleichen braucht.

### 7.6 Ein nicht geführter Nachweis ist kein erfüllter (22.09.2026)

Nach dem Lastverlust (§ 7.3) und seinen sechs Geschwistern (§ 7.3a) wurde das
ganze Programm nach **derselben Art Fehler** durchgesehen: solchen, die still
sind. Kein Absturz, keine Meldung, eine plausible Zahl. Zehn Blickrichtungen
lasen den Quelltext, **jeder** Befund ging an einen Gegenprüfer, dessen Auftrag
das Widerlegen war: **44 geprüft, 36 gehalten, 8 widerlegt.**

Fünf davon sind hier behoben — die, bei denen ein Statikdokument etwas
behauptet, das nicht stimmt.

**Ein Stab ohne Streckgrenze stand als „erfüllt" im Bericht.**
`MemberCheck.status()` kannte zwei Fälle. Ein übersprungener Stab bekam
Ausnutzung 0,000 und damit „erfüllt"; seine Null berührte weder die größte
Ausnutzung noch die Liste der nicht erfüllten. Der Nachbarnachweis Volumen
(`VolumenCheck`) unterscheidet an derselben Stelle seit jeher **drei** Fälle —
hier waren es zwei. Jetzt gibt es `MemberCheck.fehler` und den Zustand „nicht
geführt".

Zwei Stellen hatte diese erste Kur nicht erreicht (nachgemessen am selben Tag,
Einfeldträger IPE 300 S235 mit Ausnutzung 0,633 und daneben ein Stab aus einem
Werkstoff ohne f_y):

* `DesignResults.summary()` zählte weiter nur Ausnutzung > 1 und schrieb
  „… max. Ausnutzung 0.633 … - alle erfuellt". Diese Zeile steht in der
  Oberfläche nach *Nachweise EC3*, im Etikett der Maske *Nachweise* (Gruppe
  „Nachweise führen (nach der Berechnung)“) und in der Zusammenfassung der
  Berechnung. Jetzt zählen nicht geführte Stäbe weder
  für „alle erfuellt" noch für die größte Ausnutzung; die Zeile endet mit
  „- 1 nicht geführt: *Stab* (Werkstoff … ohne Streckgrenze)", höchstens zehn
  Namen. Ist kein Stab geführt, nennt sie keine Ausnutzung.
* Der Grund stand nur in `mc.warnings`, und die kamen allein über den
  Detailblock je Stab in die Hinweisliste des Berichts. Den gibt es im Umfang
  „kurz" (der Vorgabe) nicht, in „mittel" nur für die 20 am höchsten
  ausgenutzten Stäbe — ein Stab mit 0,000 fällt zuerst heraus. Gemessen:
  „kurz" mit 2 Stäben und „mittel" mit 22 Stäben ergaben **0 Hinweise**, und
  unter der Statuszeile, die auf „die Hinweise unten" verweist, stand „Es
  liegen keine offenen Hinweise oder Warnungen vor." Seitdem gibt es für jeden
  nicht geführten Stab einen Hinweis, unabhängig vom Umfang, mit demselben
  Text wie der Detailblock (er steht darum nur einmal in der Liste) und mit
  dem, was zu tun ist: Streckgrenze am Werkstoff eintragen oder am Stab
  „Nachweis nach EC3" ausschalten.

Die Gegenprüfung dieser Kur (23.09.2026) fand denselben Fehler auf drei
weiteren Wegen, jeweils gemessen am Stand 97df705:

* **Berichtsoption „Nachweise EC3" aus.** Der Hinweis entstand im
  Nachweiskapitel, und das kehrt bei ausgeschalteter Option früh zurück. Die
  Zusammenfassung liest die Nachweisergebnisse aber unabhängig von der Option.
  Stütze S355 und Riegel ohne f_y, Umfang „kurz" und ebenso „lang": Statuszeile
  „… nicht geführt wurden: 1 Stäbe (EC3) (siehe die Hinweise unten)." (Wortlaut
  jenes Stands; seit dem 23.09.2026 „1 Stab (EC3)"),
  darunter „Es liegen keine offenen Hinweise oder Warnungen vor." Jetzt legt
  die Zusammenfassung den Hinweis an, an der Stelle, an der sie die nicht
  geführten Stäbe für die Statuszeile zählt — beides kommt aus derselben
  Liste.
* **Kein einziger Stab geführt.** Die Wesentlichen Ergebnisse bildeten die
  größte Ausnutzung über alle Stäbe, auch über die nicht geführten. Mit einem
  einzigen Riegel ohne f_y standen dort „max. Ausnutzung Nachweise EC3" mit
  0.000 und „maßgebend" mit „Stab Riegel_ohne_fy: , Kombination , x = 0.00 m", die
  Statuszeile sagte „Alle \*\*geführten\*\* Nachweise erfüllt – nicht geführt
  wurden: 1 Stäbe (EC3)" (Wortlaut jenes Stands, die Sternchen standen wörtlich
  im Bericht), obwohl kein Nachweis geführt war. Jetzt zählt nur
  ein geführter Stab für Ausnutzung und maßgebende Stelle; ist keiner geführt
  und auch sonst kein Nachweis, fehlen beide Zeilen, und die Statuszeile heißt
  „Kein Nachweis geführt – nicht geführt wurden: …" (rot, nicht grün wie „Es
  wurden keine Nachweise geführt").
* **Bedienung im Browser.** Die Oberfläche färbte die Nachweiszeile im
  Register *Ergebnisse* über `/NICHT/.test(...)` am Text und im Register
  *Nachweise* über `util_max > 1`. „nicht geführt" ist klein geschrieben, ein
  nicht geführter Stab hat Ausnutzung 0 — beide Zeilen waren grün (ohne
  Browser gerendert, `tests/render_nachweiszeile.js`). Jetzt liefert der
  Server das Urteil aus den Stabnachweisen mit (`err` bei Ausnutzung über 1,
  `warn` bei einem nicht geführten Stab, sonst `ok`), und die Oberfläche liest
  den Text nicht mehr aus (`test_nachweiszeile_nicht_gefuehrt_nicht_gruen`).

Ein weiterer Weg, gemessen am Stand ec6448c (Befund B054): die Färbung
„Ausnutzung EC3" und das Balkendiagramm. `DesignResults.util_by_element()`
gab den Elementen eines nicht geführten Stabes dessen Ausnutzung 0,0 mit. Am
Einfeldträger IPE 300 mit dem Stab „Ohne_fy" daneben waren im Bericht alle
6 Linien dieses Stabes im Bild „Ausnutzung der Stäbe" grün (#2e8b57, Klasse
< 0,50), und das Balkendiagramm „Ausnutzung je Stab" zeigte für ihn einen
grünen Balken mit „0.000" — wie ein unbeanspruchter Stab. Jetzt bekommt ein
nicht geführter Stab in `util_by_element()` keinen Eintrag. In der
Oberfläche bleiben seine Zellen ohne Wert (NaN, grau wie jedes Element ohne
Wert), die Stabtabelle der Maske *Ergebnisse* zeigt „-". Im Bericht stehen
seine Linien in Stabfarbe, im Balkendiagramm fehlt er, und beide
Bildunterschriften nennen ihn (`test_ec3`,
`test_nicht_gefuehrt_ohne_ausnutzung_in_bildern`). Das gilt, solange
mindestens ein Stab geführt ist: nur dann zeichnet der Bericht die beiden
Bilder. Ist keiner geführt – am selben Modell, wenn auch der Träger aus dem
Werkstoff ohne f_y ist –, entfallen Balkendiagramm und Bild samt
Bildunterschriften, denn sie hätten keinen Wert zu zeigen
(`test_kein_stab_gefuehrt_keine_bilder`). Am Stand ec6448c waren an diesem
Modell beide Bilder da, alle 12 Linien grün und zwei Balken „0.000".

Weitere Befunde am Gesamturteil und seinen Hinweisen, gemessen am Stand
ec6448c (23.09.2026), geprüft in `tests/test_report.py` und
`tests/test_theorie3.py`:

* **„… NICHT erfüllt für" nur im Kapitel.** Dasselbe Muster wie oben bei den
  nicht geführten Stäben, jetzt bei den nicht erfüllten: der Hinweis
  entstand im Nachweiskapitel, und das kehrt bei ausgeschalteter
  Berichtsoption früh zurück. Einfeldträger IPE 300 mit Ausnutzung 9,5 und
  „Nachweise EC3" aus: Statuszeile „Nachweise NICHT erfüllt – siehe die
  Nachweiskapitel.", Hinweisliste leer, darunter „Es liegen keine offenen
  Hinweise oder Warnungen vor."; mit „Ermüdung" aus am Kragarm (D = 12 185)
  ebenso. Jetzt bildet die Zusammenfassung alle diese Hinweise (EC3, Beulen,
  Volumen, Ermüdung, Anschlüsse, Verformung) aus denselben Listen, aus denen
  sie das Gesamturteil bildet, und die Statuszeile verweist auf „die Hinweise
  unten", sobald das Kapitel eines nicht erfüllten Nachweises aus ist. Geprüft
  je Option einzeln an einem Träger, an dem jede Nachweisart reißt
  (Beulen, Anschlüsse und Volumen als Ergebnisobjekte von Hand). Die
  Lasteinleitung behält ihren Hinweis im Abschnitt: sie hat keine eigene
  Option und steht auch bei ausgeschalteten Beulnachweisen im Bericht.
* **Lauter nicht geführte Ermüdungseinträge zählten als geführt.** Als
  geführt galt die Ermüdung, sobald es überhaupt Einträge gab. Mit der
  einzigen Ermüdungslast auf einem nicht gerechneten Höchstzustand hieß es am
  Kragarm „Alle \*\*geführten\*\* Nachweise erfüllt – nicht geführt wurden:
  1 Stäbe (Ermüdung) …", am Zugstab-Volumen ebenso mit „1 Volumenkörper
  (Ermüdung)" — geführt war keiner. Dasselbe galt für Volumenbereiche, die
  alle nicht geführt oder alle nur berichtet (singulär) waren; ein
  Modell ohne andere Nachweise mit nur einem singulären Bereich bekam „Alle
  Nachweise erfüllt.". Jetzt zählt ein Eintrag nur ohne Fehler (Volumen: und
  nicht singulär); die Statuszeile heißt dann „Kein Nachweis geführt – …"
  bzw. „Es wurden keine Nachweise geführt; …".
* **Wortlaut.** „1 Stäbe (EC3)", „1 Stäbe (Ermüdung)", „1 Volumenbereiche"
  heißen jetzt „1 Stab", „1 Volumenbereich"; ebenso zählt die
  Zusammenfassung die unvollständigen Anschlüsse (Ermüdung, Befund B094) als
  „1 Anschluss". Die Sternchen um „geführten"
  standen in HTML und PDF wörtlich und gaben in Markdown verschachteltes
  Fett, ebenso „\*\*am Ort\*\*" (Ermüdung) und „\*\*Sehne\*\*" (Verformung)
  in den Grundlagen. Absätze und Listenpunkte des Berichts tragen keine
  Auszeichnung — sie gehen durch die Maskierung.
* **Gescheiterte Theorie III. Ordnung fehlte in den offenen Hinweisen.** Mit
  erzwungenem `info.fehler` am Kragarm aus zwei Stäben stand der Grund bei
  II. Ordnung in den Hinweisen der Zusammenfassung, bei III. Ordnung nur in
  der Spalte „Hinweis" des Theoriekapitels — und darunter „Es liegen keine
  offenen Hinweise oder Warnungen vor.". Jetzt trägt chapter_theorie3 ihn
  ein wie chapter_theorie2.
* **Spalte „Löser" im Anhang.** Sie zeigte `info["solver"]`, den Löser der
  letzten Faktorisierung, auch wenn das Ergebnis ein Ausweichen trug
  („pardiso", während Anhangzeile und Hinweis „ausgewichen auf SuperLU"
  nannten; Angaben am Ergebnis von Hand gesetzt, wie sie `ausweich_info` bei
  einem Teilausfall hinterlässt). Jetzt: „pardiso – ausgewichen auf SuperLU
  (direkt, einkernig)". Eine überlagerte Kombination hat keinen eigenen
  Löser, trägt aber das Ausweichen ihrer Lastfälle; die erste Fassung der
  Kur schrieb dort „– – ausgewichen auf SuperLU (direkt, einkernig)"
  (gemessen 24.09.2026 an einer echten Rechnung mit werfendem
  `factorize`). Jetzt steht dort nur „ausgewichen auf SuperLU (direkt,
  einkernig)".

**Die Renderprüfung braucht `node`.**
`test_nachweiszeile_nicht_gefuehrt_nicht_gruen` und `test_oberflaeche_rendert`
führen `app.js` mit `node` aus. Ohne `node` trugen beide bis ec6448c eine
bestandene Prüfung ein und ließen das Rendern aus. Am Stand 97df705 gibt es
die Prüfung der Nachweiszeile noch nicht; gemessen ist darum mit
`tests/test_web.py` vom Stand ec6448c und `app.js` vom Stand 97df705, vor der
Kur der Nachweiszeile (23.09.2026, am 24.09.2026 nachgemessen): mit `node` 232 von 255 Prüfungen bestanden, unter den 23
Fehlschlägen die vier der Nachweiszeile; ohne `node` 142 von 142 — die
zurückgenommene `app.js` fiel ohne `node` nicht auf. Jetzt reißt die Suite
ohne `node`; nur `STATIK3D_OHNE_NODE=1` erlaubt das Auslassen, und die
Zusammenfassung zählt es dann als „übersprungen“, nicht als bestanden
(`test_ohne_node_nicht_bestanden`).

**„Alle Nachweise erfüllt." galt auch bei gerissenem Volumennachweis.**
`self.volumen` fehlte im Gesamturteil **doppelt**: in der Statusprüfung und in
der Liste der geführten Nachweise. Ein Modell, das nur aus Volumen besteht — am
Drehlager der Regelfall —, bekam entweder „Es wurden keine Nachweise geführt"
oder „Alle Nachweise erfüllt", während der geführte Nachweis riss. Die eine
Zeile, die ein Prüfer als Gesamturteil liest, sagt jetzt:
*„Alle geführten Nachweise erfüllt – nicht geführt wurden: …"* (bis zum
23.09.2026 mit Sternchen um „geführten", die in HTML und PDF wörtlich standen
und in Markdown verschachteltes Fett ergaben).

Geprüft wird das am reinen Volumenmodell selbst, nicht nur am Balken mit Stab:
dort fällt ein fehlender Eintrag „Volumen" in der Liste der geführten
Nachweise nicht auf, weil der Stab den Nachweis schon als geführt zählt.
Zugkörper 100 × 100 mm aus S355 ohne Stäbe: bei N = 4000 kN ist die
Ausnutzung 1,194 und die Statuszeile „Nachweise NICHT erfüllt", bei
N = 2500 kN 0,746 und „Alle Nachweise erfüllt.". Mit dem alten Stand stand in
beiden Fällen „Es wurden keine Nachweise geführt; …" mit grüner Kennung
(`test_gesamturteil_reines_volumenmodell`).

**Ein ausgeschalteter Volumenbereich galt als nicht geführt** (Befund B058,
23.09.2026). `check_volumen` schrieb bei `Volumenbereich.design = False` den
Text „Nachweis für diesen Bereich ausgeschaltet" in `VolumenCheck.fehler`, und
das Gesamturteil zählt jeden Bereich mit `fehler` als „nicht geführt". Ein Stab
mit `design = False` kommt dagegen gar nicht erst in `check_members`. Am
Zugkörper (N = 2500 kN) mit „Schaft" und einem ausgeschalteten Bereich stand
„Alle **geführten** Nachweise erfüllt – nicht geführt wurden: 1 Volumenbereiche"
(Kennung `nok`) statt „Alle Nachweise erfüllt.". Mit dem ausgeschalteten Bereich allein
stand dieselbe Zeile da, obwohl kein Nachweis lief. Jetzt trägt der Bereich ein
eigenes Merkmal `VolumenCheck.ausgeschaltet` mit dem Status „ausgeschaltet"
und keinen Fehler, und das Gesamturteil lässt ihn ganz weg. Mit dem
ausgeschalteten Bereich allein heißt es darum „Es wurden keine Nachweise
geführt; …" – dieselbe Zeile wie an einem Balkenmodell, dessen Stäbe alle ohne
Nachweis sind (gemessen). Im Kapitel der Volumennachweise und in `summary()`
bleibt er sichtbar („– 1 ausgeschaltet: Aus"). Gegenprobe im selben Test: ein
Bereich ohne Werkstoff mit Streckgrenze zählt weiter als nicht geführt; neben
einem ausgeschalteten Bereich heißt es „nicht geführt wurden: 1
Volumenbereiche" (am alten Stand 2). Eine Ergebnisdatei vom alten Stand trägt
noch den alten Fehlertext; `VolumenCheck.__setstate__` erkennt ihn am
wörtlichen Text, wenn das Feld fehlt. Gemessen: eine mit `ec6448c`
geschriebene Ergebnisdatei ergibt nach dem Lesen „ausgeschaltet" und „Alle
Nachweise erfüllt." (`test_ausgeschalteter_bereich_im_gesamturteil` bildet die
alte Datei nach).

**Theorie II./III. Ordnung scheiterte still.** Der `ValueError` landete in
`an.info["warnungen"]` — einem Schlüssel, der im ganzen Programm **einmal
geschrieben und nirgends gelesen** wird. Das **lineare** Ergebnis blieb unter
demselben Namen stehen, und die Lastfalltabelle druckte weiter die
*eingestellte* Theorie. Zusatzmomente aus der Verformung und die
Vorkrümmungen fehlten vollständig; alle darauf aufbauenden Nachweise rechneten
mit zu kleinen Momenten. Der Kombinationszweig macht es seit jeher richtig
(`Th3Info(fehler=…)`) — nur der Lastfallzweig nicht. Jetzt trägt das Ergebnis
`info["theorie"]`, `info["theorie_gewuenscht"]` und `info["theorie_fehler"]`,
das Theoriekapitel bekommt einen Eintrag, und die Tabellenspalte zeigt
*„I (statt III: nicht gerechnet)"*.

**Nachbesserung derselben Kur.** Die Spalte verglich den Text aus
`info["theorie"]` unmittelbar mit der Einstellung. Die Löser für II. und
III. Ordnung schreiben dort aber „II. Ordnung" bzw. „III. Ordnung", die
Einstellung heißt „II"/„III" — damit stand jeder **gelungen** gerechnete
Lastfall als *„II. Ordnung (statt II: nicht gerechnet)"* im Bericht. Jetzt
werden nur die römischen Zahlen verglichen. Zweitens markierte der Löser das
stehenbleibende lineare Ergebnis nur beim `ValueError`, nicht aber, wenn die
Rechnung mit `info.fehler` endet (II. Ordnung: Gleichungssystem singulär;
III. Ordnung: keine Konvergenz oder singulär). Dort wird das nichtlineare
Ergebnis zu Recht verworfen; die Spalte zeigte aber weiter „II"/„III", obwohl
nach I. Ordnung gerechnet war. Beide Zweige markieren jetzt gleich.
Geprüft in `tests/test_theorie3.py` am Kragarm aus zwei Stäben (gelungen: II
und III; gescheitert: erzwungenes `info.fehler`); an einem großen Modell nicht
gemessen.

**Gescheiterte Kombinationen blieben still linear (B132).** Der Satz oben,
der Kombinationszweig mache es „seit jeher richtig", stimmte nur halb:
`check_theorie2`/`check_theorie3` tragen den Fehler ins Theoriekapitel ein und
übernehmen das Ergebnis zu Recht nur ohne Fehler — das stehende Ergebnis
der Kombination nach I. Ordnung aus `solve_combinations` markierten sie aber
nicht. Das ist die Überlagerung der Lastfälle, wo `_nichtlinear` gilt
(Kontakt, Ausfallstäbe oder Seile, Plastizität), aber die direkte Lösung der
Kombination (`solve_combination` → `_solve_loads`). Die
Kombinationstabelle des Berichts druckte `model.theorie_von`, also die
Einstellung, und die GZT-Nachweise liefen ohne Warnung mit dem linearen
Ergebnis. Gemessen am 23.09.2026 am Stand ec6448c, Kragarm aus zwei Stäben,
K1 = 1,35 · LF nach III. Ordnung mit Zwangsverformung (`ValueError`) bzw.
nach II. Ordnung mit erzwungenem `info.fehler`: Tabelle „III" bzw. „II",
`_uls_results` liefert K1 ohne Warnung; mit einem Stab mit Nachweis lautete
das Gesamturteil „Alle Nachweise erfüllt." bei Ausnutzung 0,053 aus dem
linearen Ergebnis. Jetzt markiert `solve_all` nach `check_theorie2` und
`check_theorie3` jede gewöhnliche Kombination mit `info.fehler` wie einen
Lastfall (`info["theorie"] = "I"`, `theorie_gewuenscht`, `theorie_fehler`;
`_gescheiterte_kombinationen_markieren`), beide Kombinationstabellen des
Berichts zeigen die gerechnete Theorie („I (statt III: nicht gerechnet)"),
und `_uls_results` nennt die Kombination in den Warnungen als „nur nach
Theorie I. Ordnung nachgewiesen". Am selben Kragarm lautet das Gesamturteil
damit „Alle **geführten** Nachweise erfüllt – nicht geführt wurden: EC3
(1 Warnung)". Maßgebend ist allein `info.fehler`, nicht „nicht gerechnet":
bei `theorie2 = "auto"` und α_cr über der Grenze bleibt die Kombination nach
5.2.1(3) zulässig linear und unmarkiert (Gegenprobe am Kragarm aus zehn
Stäben, α_cr = 49,98). Die Alternativen einer Ergebniskombination („EK [k]")
deckt diese Kur nicht ab, und auch der Verformungsnachweis meldet nichts:
`gzg._sls_results` übernimmt eine GZG-Kombination ohne `_nur_linear_melden`.
Gemessen am 24.09.2026 am Stand d9f42db, derselbe Kragarm mit
Zwangsverformung bzw. erzwungenem `info.fehler`: S1 = 1,0 · LF (SLS_CH)
nach III. bzw. II. Ordnung mit einer Verformungsgrenze am Endknoten — die
Tabelle zeigt richtig „I (statt …: nicht gerechnet)", aber `gzg.warnungen`
ist leer und das Gesamturteil lautet „Alle Nachweise erfüllt."; EK1 mit zwei
Alternativen nach III. bzw. II. Ordnung — Zellen „III" bzw. „II",
`_uls_results` liefert „EK1 [1]", „EK1 [2]" ohne Warnung. Den Grund nennt
in diesen Fällen das Theoriekapitel. Das Benutzerhandbuch nennt beide
Ausnahmen. Im Kontaktmodell bleibt die direkte Lösung stehen, nicht die
Überlagerung: gemessen am 24.09.2026 am Stand d55789c (zwei Läufe gleich),
Kragarm 3 m mit Spaltelement an der Spitze (Spalt 2 mm), LF1 und LF2 je
Fz = −12 kN schließen den Spalt je allein (2,0000 mm), K1 = LF1 + LF2 nach
III. Ordnung scheitert mit „Theorie III. Ordnung nicht zusammen mit
Kontakt" — K1 steht bei 2,0000 mm ohne `info["superposition"]`, die
Überlagerung ergäbe 4,0000 mm; Zelle „I (statt III: nicht gerechnet)",
`_uls_results` warnt. Geprüft in `tests/test_theorie3.py`
(`test_gescheiterte_kombination_markiert_das_lineare_ergebnis`; den
Einklang von Handbuchtext und Programm prüfen für beide Ausnahmen
`test_handbuch_nennt_die_ausnahmen_der_kombinationsmeldung` und für das
Kontaktmodell `test_handbuch_kontaktmodell_rechnet_die_kombination_direkt`);
an einem großen Modell nicht gemessen.

**Ermüdung: ein fehlender Mindestzustand wurde still zu null.** `case_min`
angegeben, aber nicht gerechnet, fiel in denselben Zweig wie „kein
Mindestzustand angegeben". Gemessen an einem Kragarm:

| | Schädigung D |
|---|---|
| beide Zustände gerechnet | **14,0785** |
| alter Stand (still genullt) | **2,4140** |

**Faktor 5,8 zu klein, auf der unsicheren Seite** — und mit m = 5 wäre es mehr.
Der fehlende **Höchst**zustand wurde immer gemeldet, der Mindestzustand nicht;
diese Unsymmetrie war der Fehler.

**Ausfallstäbe und Seile machen das System nichtlinear.** `_nichtlinear()`
kannte nur Kontakt und Fließen, obwohl das Modell `hat_ausfallstaebe()` seit
jeher hat und der Löser es an zwei anderen Stellen abfragt. Jeder Lastfall
wurde mit einer **anderen** Menge tragender Stäbe gerechnet, und die Summe
solcher Ergebnisse steht in keinem Gleichgewicht eines wirklichen Zustands. An
einem Balken auf zwei Nur-Zug-Hängern gemessen:

| | max \|u\| |
|---|---|
| direkt gerechnet | **0,9401 mm** |
| überlagert | **2,0794 mm** |

**121 % daneben.** In Lastfall A fällt kein Hänger aus, in B fallen beide aus —
die Überlagerung mischt zwei unvereinbare Zustände. Die Abfrage läuft über alle
Elemente (4,5 ms bei 67 500); bei Kontakt oder Fließen schließt `or` kurz, und
im linearen Fall gibt `solve_combinations` die Antwort einmal mit, statt sie je
Kombination neu zu suchen.

**Drei eigene Fehler beim Beheben**, hier aufgeschrieben, weil sie die Art
zeigen, die auch ohne Absicht entsteht:

* Eine erste Prüfung rief eine Funktion auf, **die es nicht gibt** — der Zweig
  lief leer durch und bestand vakuum. Genau die Art Prüfung, gegen die dieser
  ganze Abschnitt geschrieben ist.
* Eine erste Kur ließ den Stab samt Warnung **ganz aus dem Nachweis fallen**
  (`if not sammlung: continue`) — ein stiller Fehler gegen einen anderen
  getauscht. Jetzt bleibt er als „nicht geführt" stehen, im Stab- und im
  Volumenzweig.
* Im Volumenzweig stand `name` statt `k.name` — ein `NameError`, den **kein
  Test gefunden hätte**, weil der Zweig nicht durchlaufen wird. Gefunden durch
  Lesen.

**Nachtrag: die Reste der Ermüdung (Befunde FE2, FE5, FE13, SV5).** Die
Rechenstelle war behoben, drei Dinge nicht:

* *Der Volumenzweig war ungeprüft.* Jetzt hält ihn ein Test am Zugstab-Volumen
  (σ = 100 gegen −40 N/mm²). Mit der alten Zeile
  `b = signal(case_min) if case_min in all_res else 0.0` weist er für den
  fehlenden Mindestzustand D = 0,1397 statt 0 aus, mit zwei Lasten
  0,52304 statt 0,38334 (gemessen durch Zurücknehmen).
* *Die Ursache lag vor der Rechnung.* Die Maske bot eine oder-verknüpfte
  Ergebniskombination als Zustand an, die Modellprüfung ließ sie durch — sie
  steht in `model.combinations`, der Löser legt aber nur ihre Umhüllende ab
  (`an.envelopes`), nie ein Einzelergebnis. `Model.ermuedungszustaende()`
  nimmt sie aus der Auswahl, `Model.check()` meldet sie als FEHLER, auch als
  Glied eines Verlaufs. Geprüft werden dabei nur die Zustände, die der
  Nachweis liest: bei einem Verlauf dessen Glieder, sonst `case_max` und
  `case_min`. Die erste Fassung prüfte bei einem Verlauf auch ein
  mitgeführtes `case_max`, das `ec3.fatigue` nie liest (gemessen: D = 0,38334
  mit und ohne), und ihr FEHLER hätte die CLI (Exit 2) und den Rechenstart
  über die Web-Schnittstelle abgewiesen.
* *Der Bericht las den Status aus D allein.* Ein nicht gerechneter Eintrag
  (D = 0) hieß „Nachweis erfüllt“. `FatigueMember`/`FatigueVolumen.status()`
  unterscheidet jetzt vier Fälle: nicht geführt (`fehler`), NICHT erfüllt
  (D > 1), unvollständig (`fehlende_lasten`), erfüllt. Die Reihenfolge folgt
  aus Miner: eine ganz fehlende Last trägt an jedem Ort einen Summanden ≥ 0
  bei, D > 1 bleibt also auch mit ihr überschritten, D ≤ 1 sagt ohne sie
  nichts. Für einen Verlauf, dem nur ein Zustand fehlt, gilt das bei der
  Spanne ebenso (die Spanne einer Teilmenge ist nicht größer); für Rainflow
  und Reservoir ist es nicht gezeigt. Eine unwirksame Last (0 Lastspiele bzw.
  Wiederholungen) fehlt nie in D, auch wenn ihr Ergebnis fehlt — die erste
  Fassung der Kur machte daraus „unvollständig“, eine Gegenprobe im Test hat
  es gezeigt. Ist sie die einzige Last eines Stabs oder Volumens, steht er
  trotzdem als „nicht geführt“ da, mit ihrem fehlenden Ergebnis als Grund
  (ohne fehlendes Ergebnis: kein Eintrag, „ohne wirksame Ermüdungslast“).
* *Und die erste Fassung dieser Kur prüfte nur einen Teil der Wege.* Ihre
  Tests auf „unvollständig“ hielten allein den Volumenkörper mit fehlendem
  Mindestzustand. Sechs Stellen ließen sich auf die alte bloße Warnung bzw.
  den alten Stand zurücksetzen, ohne dass eine Prüfung fiel, nämlich die
  ursprüngliche Fehlerstelle im Stabzweig, das Gesamturteil für Stäbe, beide
  Verläufe mit fehlendem Glied, die Reihenfolge in `_status` und die Maske
  (Mutationsproben der Gegenprüfung, von uns wiederholt; dazu zwei eigene für
  den fehlenden Höchstzustand). `test_unvollstaendig_je_weg` rechnet jetzt
  jeden der vier Wege an Stab und Volumen neben einer gerechneten Last.

**Die übrigen 31 Befunde waren mit dieser Runde nicht behoben** (250de7a),
aber aufgeschrieben (mit Datei, Zeile und der Gegenprüfung, die sie nicht
widerlegen konnte). Darunter: die Netzabnahme meldet „bestanden", obwohl
Prüfungen ausgefallen sind; der RFEM-6-Import lässt Stablasten still weg und
wirft die Lastrichtung von Flächenlasten weg; eine Viereckfuge wird nur zur
Hälfte gezählt; der Volumennachweis rechnet ohne Dickenabminderung.

Die beiden Punkte zum RFEM-6-Import sind noch am 22.09.2026 behoben worden:
die Stablasten in db19cf2, die Lastrichtung der Flächenlasten in 83671bd, das
Abzählen der Stablasten in 2f0427c (beschrieben in `docs/Schnittstellen.md`,
RFEM 6, „Lastfälle und Lasten"). Nachgemessen am 23.09.2026 mit den
Prüfungen `test_stab_und_knotenlasten` und `test_flaechenlast_richtung` aus
`tests.test_rfem6` gegen den Importer von 250de7a: Von 2 Stabgleichlasten
kam keine an. Die Last einer senkrechten Fläche (global Z, 12 000 N) wirkte
ganz in der Flächennormalen (Lagerkräfte ΣR_y = −12 000 N, ΣR_z = 0 N), und
an einer waagerechten hing das Vorzeichen am Umlaufsinn des Randes
(ΣR_z = +8000 N gegen −8000 N). Am jetzigen Stand bestehen beide Prüfungen,
`tests.test_rfem6` meldet 318 von 318.

### 7.7 Objekt-Nummern reisen nicht mit (24.09.2026)

Der stehende Pool (`parallel.Arbeiter`) pickelt das Modell beim Öffnen, samt seinen
Zwischenspeichern. Ein Zwischenspeicher, der Elemente über `id(Objekt)` findet, ist im
Arbeitsprozess wertlos: dort sind es andere Objekte, auch wenn Größen und
Versionszähler gleich bleiben. So geschah es beim Tetraeder mit Ordnung p
(`tetp.index_von`, Zuordnung `_nach_id` in der Anreicherung): Rechnete der
Hauptprozess dasselbe Modell schon einmal — Fables adaptive Messung V5 wiederholt die
Rechnung nach „Kante gerade gelassen“ —, brach die nächste parallele Rechnung mit
„tetp: Element gehoert nicht zum Modell“ ab, im Nachlauf mit Pythons leerem
„max() iterable argument is empty“. Seitdem prüft `index_von`, ob die gefundene
Nummer noch dasselbe Objekt meint, und baut die Zuordnung sonst einmal neu; der
Nachlauf nennt ein Element ohne Auswertepunkte mit Nummer und Typ. Geprüft an der
Hohlkugel mit tetp4 innen und tetp2 außen (1 152 Elemente, acht Blöcke, zwei Arbeiter):
erst seriell, dann parallel, die geglättete Knotenspannung bitgleich; ohne die
Behebung bricht die parallele Rechnung ab (`tests/test_nachlauf_parallel.py`).

## 7a Entartete Elemente

Ein Element ohne Ausdehnung hat keine Steifigkeit; seine Jacobi-Matrix ist
singulär und die Formulierung bricht ab. Zwei Fälle treten auf:

* **Doppelte Knoten** - zwei Ecken zeigen auf denselben Modellknoten. Beim
  Vernetzen entsteht das, wenn die Knoten auf einer gemeinsamen Fläche
  zusammengelegt werden und dabei zwei Ecken eines flachen Tetraeders auf
  denselben Punkt fallen.
* **Verschwindendes Maß** - die Punkte liegen auf einer Geraden bzw. in
  einer Ebene.

Geprüft wird je Familie das natürliche Maß: Länge bei Stäben, Fläche bei
Schalen und Scheiben, Volumen bei Tetraedern. Für Sechsflächner, Keile und
Pyramiden dient die Streumatrix **C** der Eckpunkte,

    C = (1/n) · Σ (x_i − x̄)(x_i − x̄)ᵀ ,     Maß = √det C  ,

deren Determinante genau dann verschwindet, wenn die Punkte in einer Ebene
liegen; die Wurzel hat die Einheit eines Volumens. Das läuft für alle
Elemente auf einmal und kostet bei 380 000 Tetraedern rund 1,5 s - die
exakte Integration je Element bräuchte Minuten, und geprüft wird vor jeder
Rechnung.

Die Grenzen (10⁻⁹ m, 10⁻¹² m², 10⁻¹⁵ m³) liegen weit unter allem, was ein
Bauteil je ist - ein Würfel mit 0,1 µm Kante hat 10⁻²¹ m³ -, sodass nur
wirklich entartete Elemente anschlagen, kein dünnes Blech. Federn und
Grenzschichten sind ausgenommen: sie dürfen die Dicke null haben.

**Behandlung.** Solche Elemente werden in `assemble.aktive_indizes`
übergangen, also aus Steifigkeit, Masse und Nachlauf herausgenommen. Das ist
keine Näherung: aus einem verschwindenden Maß folgt

    K_e = ∫ Bᵀ D B dV = 0 ,   M_e = ∫ ρ Nᵀ N dV = 0 ,

das Gleichungssystem bleibt Zeichen für Zeichen dasselbe. Nur die
Elementmatrix selbst wäre singulär und brächte die Assemblierung zu Fall.
Die Modellprüfung meldet sie als Warnung - nicht als Fehler, denn ein
Modell darf daran nicht scheitern -, weil sie auf eine Schwäche im Netz
oder in der Quelldatei zeigen.

Entstehen können sie an drei Stellen, alle drei prüfen jetzt vorher:

* Ein Volumenkörper aus vier Dreiecksflächen, dessen vier Eckknoten in einer
  Ebene liegen, bzw. ein Sechsflächner ohne Rauminhalt (`mesher.mesh_koerper`).
  In Dateien aus RFEM stehen solche Null-Volumen als Hilfsobjekte.
* Der freie Vernetzer, wenn beim Zusammenlegen der Knoten auf gemeinsamen
  Flächen zwei Ecken eines flachen Tetraeders auf denselben Modellknoten
  fallen (`mesher3d._entartete_weglassen`).
* Importierte Netze mit doppelten Knoten.

**Doppelte Knoten mit Volumen (23.09.2026).** Nicht jedes Element mit doppeltem
Knoten ist leer. Ein Sechsflächner, bei dem zwei gegenüberliegende Seiten zu
Dreiecken zusammenfallen, ist ein Keil; einer, dessen eine Seite auf einen Punkt
fällt, eine Pyramide; mit vier verschiedenen Knoten ein Tetraeder. So entarten der
VQ83 von InfoGraph und Nastran-CHEXA oder Abaqus-C3D8 mit wiederholten Knoten, und
das Zusammenlegen doppelter Knoten beim Import kann sie erzeugen. Bis zum
23.09.2026 galten auch sie als „ohne Ausdehnung“ und fielen weg: ein Kragarm aus
128 Keil-Sechsflächnern (408 FHG) rechnete mit **0,0 mm** Durchbiegung, gemeldet nur
als Warnung. Seitdem ordnet `solid.entartung_aufloesen` jedes Volumenelement mit
doppeltem Knoten nach seiner Topologie ein, und `diagnose.entartete_menge` wandelt
vor der Rechnung um (Typ und Knoten, die Elementnummer bleibt; Umlauf so, dass das
Volumen positiv ist, geprüft gegen das Volumen des entarteten Elements):

| entartet | wird |
|---|---|
| hex8, zwei gegenüberliegende Seiten zu Dreiecken, an denselben Kanten | pent6 |
| hex8, eine Seite auf einen Punkt, die Gegenseite ein Viereck | pyr5 |
| pent6, eine Längskante zusammengezogen | pyr5 |
| hex8, pent6 oder pyr5 mit vier verschiedenen Knoten | tet4 |

Weggelassen wird nur noch, was danach wirklich kein Volumen hat (höchstens drei
verschiedene Knoten oder unter 10⁻¹⁵ m³). Hat ein Element Volumen und keine
eindeutige Deutung — etwa ein Sechsflächner mit nur **einer** zusammengezogenen
Kante (sieben Knoten), oder ein quadratisches Element —, ist das ein FEHLER mit
Elementnummer, und die Rechnung hält dort an. Die Modellprüfung nennt die
Umwandlung mit Anzahl je Art („hex8→pent6: 128“) und den Preis: der Kragarm aus
Keilen liegt bei 90 / 405 / 2 295 FHG −64,6 / −15,8 / −4,3 N/mm² daneben, der aus
Sechsflächnern −1,6 / +0,2 / −0,03. Nach der Umwandlung rechnet der Keil-Kragarm
bitgleich wie das pent6-Netz (`tests/test_entartung.py`). Umgewandelt wird, **bevor**
das Modell in einen anderen Prozess geht (`parallel.vor_dem_pickeln`: beim Öffnen des
stehenden Pools und vor den Rechenketten). Sonst rechneten die Arbeiter mit den
entarteten hex8 und der Hauptprozess mit pent6 — am Keil-Kragarm mit zwei Arbeitern
brach die Rechnung so mit „Singular matrix“ ab; seither ist sie seriell und parallel
bitgleich zum pent6-Netz.

**VQ83 und VQ203: umwandeln statt entartet rechnen (23.09.2026).** InfoGraph rechnet
seinen VQ83 als Sechsflächner, bei dem bis zu vier Knoten zusammenfallen dürfen. Ob
das direkt gerechnete entartete Element (innere Moden, projizierte Volumendehnung,
dieselbe Gaußregel; die Ecken an der zusammengefallenen Kante knapp innen
ausgewertet, dort ist det J = 0) mithält, ist am Kragarm gemessen, σ_v gegen
355 N/mm² in N/mm², w in mm:

| FHG | hex8 regelmäßig | Keil, als pent6 umgewandelt | Keil, als hex8 entartet gerechnet |
|---|---|---|---|
| 90 | −1,6 (10,90) | −64,6 (9,53) | −246,6 (7,25) |
| 405 | +0,2 (11,26) | −15,8 (10,77) | −122,2 (9,90) |
| 2 295 | −0,03 (11,42) | −4,3 (11,27) | −55,3 (11,01) |

Der entartet gerechnete Sechsflächner ist steifer und in der Spannung rund dreizehnmal
schlechter als der umgewandelte Keil; zur Pyramide entartet scheitert er an der Spitze
(det J ≤ 0). Beim quadratischen Gegenstück ist es dasselbe: der zum Keil entartete hex20,
direkt gerechnet, liegt bei (4,1,2) / (8,2,4) −213,3 / −95,6 daneben (w 10,16 / 11,13),
dieselben Keile als pent15 −4,7 / −0,02 (303 / 1 599 FHG) — so gut wie der hex20 (+6,2 /
−0,02 bei 267 / 1 359 FHG) und besser als der tet10 (+4,7 / +4,1 bei 405 / 2 295 FHG).
Darum sind **VQ83 und VQ203** in Statik3D keine eigenen Kinematiken, sondern hex8 und
hex20, die entarten dürfen: sie rechnen als der Keil, die Pyramide oder der Tetraeder, der
sie sind. Für den hex20 (`solid._entartung_quadratisch`) werden die Ecken wie beim hex8
eingeordnet und die Kanten des Ziels auf ihre Kantenmitten abgebildet — hex20 → pent15
oder tet10. Streng: die Mitte einer zusammengefallenen Kante muss derselbe Knoten wie
ihre Ecke sein, und Kanten, die auf dieselbe Zielkante fallen, dieselbe Mitte haben;
sonst bliebe ein Knoten ohne Element. Eine Pyramide aus einem hex20 hat kein
quadratisches Gegenstück (kein pyr13) und ist ein FEHLER. Am Kragarm aus Keil-hex20
(8,2,4) rechnet die Umwandlung wie das pent15-Netz (1,0·10⁻¹² relativ, die Rundung der
anderen Knotennummerierung). Nebenbefund: die lineare Pyramide pyr5 ist schwach — sechs
Pyramiden je Würfelzelle liegen am Kragarm −193 / −93 / −34 N/mm² daneben.

**Verträglichkeit an einer gemeinsamen Seite** (`elemente.VERTRAEGLICH`, 23.09.2026).
Welche Typen in einem Netz aneinanderstoßen dürfen, hängt an der Form ihrer Seiten:
tri3/quad4 (linear), tri6/quad8 (mit Kantenmitten), die Seite des Tetraeders mit
Ordnung p (ohne Mittenknoten). Gleiche Form und Ordnung passen **direkt**; linear gegen
quadratisch passt mit **Bindung** der Kantenmitten (u_m = (u_a + u_b)/2, § 1.2, dort
wirkt die Seite linear); tetp gegen eine lineare Seite passt, weil es die Seite
**linear** hält; tetp gegen tet10 oder pent15 passt **nicht**, die Rechnung hält dort
an. Dreieck gegen Viereck geht nur über Pyramiden als **Übergang** (Viereck unten,
Dreiecke seitlich), die der Sweep setzt:

| | tet4 | tet10 | tetp | hex8 | hex20 | pent6 | pent15 | pyr5 |
|---|---|---|---|---|---|---|---|---|
| tet4 | direkt | Bindung | linear | Übergang | Übergang | direkt | Bindung | direkt |
| tet10 | Bindung | direkt | nein | Übergang | Übergang | Bindung | direkt | Bindung |
| tetp | linear | nein | direkt | Übergang | Übergang | linear | nein | linear |
| hex8 | Übergang | Übergang | Übergang | direkt | Bindung | direkt | Bindung | direkt |
| hex20 | Übergang | Übergang | Übergang | Bindung | direkt | Bindung | direkt | Bindung |
| pent6 | direkt | Bindung | linear | direkt | Bindung | direkt | Bindung | direkt |
| pent15 | Bindung | direkt | nein | Bindung | direkt | Bindung | direkt | Bindung |
| pyr5 | direkt | Bindung | linear | direkt | Bindung | direkt | Bindung | direkt |

Die Elementstufen der Oberfläche (25.09.2026) sind damit zulässig: Entwurf (tet4 neben
hex8/pent6/pyr5 direkt) und Mittel/Fein (tet10 neben hex20/pent15 direkt oder mit
Bindung); ein gesweeptes hex8 neben tet10 geht über Pyramiden, neben dessen Keilen und
Tetraedern mit Bindung. Geprüft wird die Tabelle
gegen die Rechnung (`tests/test_vertraeglich.py`): für 50 Typpaare mit gleich geformter
Seite ist die Spur der Verschiebung von beiden Seiten gleich, genau wo die Tabelle
„direkt“ oder „Bindung“ sagt, mit den Bindungen, die die Assemblierung wirklich setzt;
ohne sie klafft sie bei „Bindung“. tetp neben tet4 rechnet, neben tet10 hält es an.

**Elementstufe in der Oberfläche: was der Vernetzer daraus macht** (25.09.2026). Der
Vernetzer hat **eine** Ordnung (`Netzeinstellungen.ordnung`) für frei vernetzte Körper
(tet4/tet10), abgebildete Sechsflächner (hex8/hex20) und Flächen (shell3/4 bzw.
shell6/8); der Sweep erzeugt immer hex8/pent6; tetp entstehen nur durch Umwandlung eines
tet10-Netzes (`tetp.aus_tet10`). Die Haken der Maske *Elemente wählen* (am Vormittag des
25.09.2026, nach dieser Tabelle ausgegraut) sind darum den Stufen gewichen
(`statik3d.elementstufe`): **Entwurf** = `ordnung 1` (tet4, hex8 als VQ83, Schalen
linear), **Mittel** = `ordnung 2` (tet10, hex20 als VQ203, Schalen quadratisch),
**Fein** = Mittel mit halber Kantenlänge beim Vernetzen (`elementstufe.wirksam`); jede
Stufe setzt den Sweep „sauber“. An einem Modell mit Kontaktbedingung, Kontaktpaar oder
Flächenlager sind Mittel und Fein gesperrt (`elementstufe.quadratisch_gesperrt`, die
eine Stelle), solange Kontakt nur die Eckknoten einer Seite nimmt
(`fugen.QuadratischeSeiten`); das Modell wird mit Entwurf vernetzt, mit Zeile im
Protokoll. Messwerte zu den Stufen: Benutzerhandbuch, „Elementstufe: Entwurf, Mittel,
Fein“.

Ein Volumenkörper, der so nie ein Netz bekommen kann, gilt auch nicht als
**unvernetzt** (`Model.koerper_traegt`). Sonst forderte die
Rechenbarkeitsprüfung vor jeder Rechnung ein Netz, das nicht entstehen kann.
Er erscheint stattdessen als Hinweis „Volumen ohne Rauminhalt“ - das
Gegenstück zu `flaeche_traegt` für Randflächen ohne Dicke.

**Eine Wahrheit, und sie ist relativ.** Zwei Stellen, die dieselbe Frage mit
verschiedenen Maßen beantworten, widersprechen sich früher oder später - und
dann verlangt das Programm ein Netz, das der Vernetzer gerade abgelehnt hat.
Darum gilt:

* Hat der Vernetzer entschieden, hält er das in der Bemerkung des Körpers
  fest (Vorsatz `Model.OHNE_NETZ`), und `koerper_traegt` übernimmt diese
  Entscheidung, statt eine eigene zu treffen.
* Wo noch nichts entschieden ist, wird der **kleinste Singulärwert** der
  zentrierten Randknoten gemessen - die Ausdehnung senkrecht zur besten
  Ebene - und ins Verhältnis zur Größe des Körpers gesetzt:

      s_min / √n  ≤  10⁻⁷ · d ,      d = Diagonale der Hüllbox .

  Die Singulärwertzerlegung ist rückwärtsstabil. Die zuvor benutzte
  Determinante der Streumatrix multipliziert drei Eigenwerte und hebt damit
  das Rauschen der letzten Bits in die dritte Potenz: bei einer absoluten
  Schranke von 10⁻¹⁵ entschied die Lage im Raum. Gespiegelte Kopien
  desselben flachen Bauteils - 14 × 26 × 8 mm, geometrisch identisch -
  bekamen so gegensätzliche Urteile (√det C zwischen 0 und 2,2·10⁻¹⁵).
* Auch die Volumenschranke des Vernetzers ist relativ, `V ≤ 10⁻⁹ · d³`. Eine
  absolute Schranke in m³ hängt sonst an der gewählten Längeneinheit und
  liegt bei Metern unter dem, was sich überhaupt auflösen lässt.

**Wann das abgebildete Muster greifen darf.** Ein Körper wird nur dann
abgebildet vernetzt, wenn seine Randflächen wirklich die Form haben, die das
Muster voraussetzt - Zählen allein reicht nicht:

* Sechsflächner: sechs Randflächen, acht Eckknoten, **jeder** Ring mit vier
  Knoten.
* Tetraeder: vier Randflächen, vier Eckknoten, **jeder** Ring mit drei Knoten
  und alle Randlinien Strecken.

Die zweite Bedingung fehlte und kostete ein Modell die Rechnung: ein
**Zylinder** aus zwei Mantelflächen (je vier Knoten) und zwei Kreisen hat
ebenfalls vier Randflächen und vier Eckknoten. Die Kreise liefern gar keinen
Ring - ein aus zwei Bögen geschlossener Kreis lässt sich nicht als Kette aus
Strecken lesen -, sodass die Ringe [4, 4, 0, 0] ergeben und die Vereinigung
vier Knoten. Das Muster griff und las die vier Ecken, die auf zwei Kreisen
liegen, als flachen Tetraeder.

Greift ein Muster und stellt sich der Körper dabei als volumenlos heraus,
heißt das nicht, dass er kein Volumen **hat** - es heißt, dass das Muster
nicht passt. Darum übernimmt dann der **freie Vernetzer**; erst wenn auch der
nichts findet, bleibt der Körper ohne Netz.

Bleiben nach dem Vernetzen Objekte ohne Netz, wird die Rechnung **nicht mehr
abgewiesen**: was der Vernetzer eben nicht vernetzen konnte, kann er auch
beim nächsten Versuch nicht, und ein erneuter Abbruch wäre eine Sackgasse.
Die Objekte werden benannt, die Folge (Lasten darauf gehen verloren) gesagt,
und gerechnet wird ohne sie. Ob das Tragwerk ohne sie noch hält, beantwortet
die Prüfung auf Teiltragwerke ohne Lager.

## 7a-2 Abnahme des Netzes vor dem Rechnen

**Grundsatz: ein Bauteil ist vollständig angebunden, oder es ist ein Fehler
mit Namen.** Nichts halb Gekoppeltes, nichts stillschweigend Übergangenes. Ein
ehrlicher Fehler vor dem Lauf ist mehr wert als ein unzuverlässiges Ergebnis
nach neun Minuten. `diagnose.abnahme(model)` prüft:

| Prüfung | Grenze | woher |
|---|---|---|
| Elemente, die eine ausgeführte Kontaktfuge überspannen | 0 | `Model.getrennte_knoten` |
| Abdeckung der Kontaktseite | ≥ 95 % (`ABNAHME_ABDECKUNG`) | `ContactPair.abdeckung` |
| Gegenkörper der Kontaktbedingung ohne eine einzige Facette | 0 | `ContactPair.gegenkoerper` |
| Haltegüte λ_min/λ_max je Teiltragwerk | ≥ 10⁻⁴ (`singular.HALTEGUETE_MIN`) | § 7b.1 |
| Knoten im Rechennetz ohne Element | 0 | die Elementliste; nicht gezählt, was über Kopplungen (wirksame Richtungen) oder starre Körper (RBE2) in allen drei Richtungen am Netz gehalten ist, der Master eines RBE3, soweit seine gehaltenen Slaves ihn festlegen (`_rbe3_master_raum`), und ein in x, y, z gelagerter Anschlag am Spaltelement (`_angeschlossene_knoten`) |
| Formgüte des schlechtesten Elements je Körper | ≥ 0,05 (`ABNAHME_ELEMENTGUETE`) | `netzguete.guete` |
| Netz gefaltet: an einer gemeinsamen Seite zweier tet4 liegen beide Gegenknoten auf derselben Seite der Ebene | 0 | `_abnahme_faltung`, siehe unten |
| Randtreue je Körper | ≥ 99 % (`ABNAHME_RANDTREUE`) | `Volumenkoerper.randtreue` |
| Volumenbilanz je Körper | ≤ 0,5 % (`ABNAHME_VOLUMENBILANZ`), an windschiefen Flächen zuzüglich Σ A · Abstand der Netzseiten | `elementvolumina` gegen `_polyederhuelle` |
| Seiten im Inneren (FEHLER) / Lücke im Netzrand (WARNUNG, über 0,5 % des Körpers FEHLER) / Riss im Netz, Netzrand neben der Hülle (WARNUNG) | 0 | freie Elementseiten gegen die Randflächen, Abstand ≤ 1 % der Seitengröße (`ABNAHME_HUELLABSTAND`), an windschiefen Flächen zuzüglich der örtlichen Sehnengrenze (`_sehnengrenze`, `ABNAHME_SCHIEF_RINGE`) und nur in Richtung der Fläche (`ABNAHME_SCHIEF_RICHTUNG`); Gruppen im Inneren: `_gruppen_im_inneren` (Riss: t/L ≤ 5 % `ABNAHME_RISS_DICKE`, t ≤ 0,65 · Dicke der Nachbarn `ABNAHME_RISS_NACHBAR`, V ≤ 2 · FLACH · L³ je vier Seiten `ABNAHME_RISS_FLACH`, kein verdrehtes Element, keine doppelten Knoten; Lücke: t/L über 1 % `ABNAHME_KNOTENNAEHE`, kein verdrehtes Element, keine doppelten oder hängenden Knoten `ABNAHME_KNOTENNAEHE`, `_haengende_gruppen`; sonst FEHLER mit der gefundenen Ursache) |
| Volumenbilanz nicht geprüft (WARNUNG) | – | `_polyederhuelle` gibt keine Hülle (krumme Randlinie, gewölbte Fläche ohne vier Ecken, Hülle nicht dicht) oder Volumenelemente gehören zu keinem Körper |

**Volumenbilanz und freie Seiten gegen die Randflächen** (22.09.2026). Ein
Sechsflächner, dessen Deckel um eine Ecke verdreht ist (4, 5, 6, 7 → 5, 6, 7,
4), ist ein gültiger Körper, nur ein anderer als der gemeinte: det J an allen
acht Gaußpunkten positiv, skalierte Jacobi-Determinante 0,707, Volumen 0,6667
statt 1,0. Elementseitig ist er nicht zu finden. Gefunden wird er am Vergleich
des Netzes mit den **Randflächen** des Körpers:

* **Netzvolumen** V_N = Σ_e Σ_g w_g |det J_e(ξ_g)| — dieselbe Summe wie
  `solid.solid_volume`, aber gestapelt je Elementart: je Gaußpunkt ein Produkt
  dN_gᵀ X über alle Elemente und eine ausgeschriebene 3 × 3-Determinante
  (größte Abweichung zu `solid_volume` 2,2 · 10⁻¹⁶ an je drei verzerrten
  Elementen aller sieben Volumentypen).
* **Hüllvolumen** V_H = ⅓ Σ_f c_f · A_f aus den Randflächen: jeder Rand als
  Fächer um den Schwerpunkt seiner Ecken, Öffnungen gegenläufig zum
  Außenrand, die Flächen über gemeinsame Randkanten gegeneinander gerichtet,
  dann `mesher3d.huellvolumen`. Für eine ebene Fläche ist der Fächer exakt;
  für ein nicht ebenes Viereck mit geraden Kanten ist ⅓ c·A (A = ½ d₁ × d₂)
  genau der Beitrag der bilinearen Fläche — so bildet der Sechsflächner sie
  ab (seine Knoten liegen darauf; ein 4 × 4 × 4 abgebildetes Netz mit
  windschiefem Deckel, Ecke 0,2 angehoben, besteht ohne Befund). Der freie
  Vernetzer legt sein Netz nur genähert darauf, siehe *Sehnen auf
  windschiefen Flächen* unten. Körper mit krummen Randlinien (Bogen, Kreis, Spline)
  werden nicht geprüft: ihre Sehnenteilung hängt an der Netzweite, die
  Abweichung läge in derselben Größe wie das Gesuchte. Dafür steht seit dem
  23.09.2026 eine WARNUNG „Volumenbilanz nicht geprüft“ mit dem Grund da
  (`_polyederhuelle(…, grund)`), ebenso für jede andere Hülle ohne Darstellung
  und für Volumenelemente, die zu keinem Körper gehören (reiner Netzimport).
  Vorher gab `abnahme(warnungen=True)` dort eine leere Liste – „bestanden“:
  am Würfelpaar mit verdrehtem zweitem Würfel ohne Körper und ebenso mit einer
  Randlinie vom Typ Bogen (mit Körper und geraden Linien FEHLER Volumenbilanz
  und Seiten im Inneren). In den Modellen von test_mesher3d und test_sweep
  bekommen 32 von 80 Körpern diese Zeile (31 krumme Randlinie, 1 Hülle nicht
  dicht); sonst sind dort alle Befunde dieselben wie bei ec6448c.
* **Nicht** als Bezug taugt das Randvolumen der freien Elementseiten desselben
  Netzes: bilinear gerechnet ist es mit V_N identisch (gemessen 1,6667 gegen
  1,6667 am verdrehten Würfelpaar), gefächert hängt es an der Diagonale
  (1,3333 oder 2,0000).

Am Würfelpaar 2 × 1 × 1 mit verdrehtem zweitem Würfel: V_N = 1,6667 gegen
V_H = 2,0 (16,7 %). Zweites Merkmal sind die **freien Seiten, die auf keiner
Randfläche liegen** (Schwerpunkt der Ecken weiter als 1 % der Seitengröße von
jeder Randfläche; eben: Abstand zur Ebene und Punkt im Vieleck, bilinear:
Fußpunkt nach Newton und Sehnengrenze, siehe unten): dort 5 von 12. Sie finden auch
**ein** verdrehtes Element im Inneren, bei dem die Bilanz nur um ein Drittel
seines Volumens verschöbe (4 × 4 × 4-Netz: 8 Seiten, das Element mit Nummer).
Ob der Körper hinter einer solchen Seite weitergeht, sagt die Windungszahl der
feinen Hülle (windschiefe Flächen in 16 × 16 Teilvierecken) an einem Punkt
knapp vor ihr (1 % der Seitengröße, auf der vom eigenen
Element abgewandten Seite — die Tupel in `solid.FLAECHEN` sind gemischt
orientiert, gerichtet wird deshalb am Elementschwerpunkt): geht er weiter, ist
es ein FEHLER („Seiten im Inneren", über sie geht keine Kraft); steht die Seite
über die Hülle hinaus, eine WARNUNG („Netzrand neben der Hülle"). So schnitt der
freie Vernetzer an einem Prisma mit eckigem Loch eine einspringende Ecke ab:
3 von 1024 Seiten, Netzvolumen 0,012 % über dem Hüllvolumen (zweimal
gemessen). Seiten im Inneren sind dagegen nur ein **Riss ohne Weite**
(WARNUNG, „Riss im Netz", `_gruppen_im_inneren`), wenn sie über gemeinsame
Kanten eine Gruppe bilden, die

1. **geschlossen** ist: die gerichteten Kanten der Seiten (umlaufend wie ihr
   Flächenvektor S, vom eigenen Element weg) heben sich auf; was bleibt, ist
   der Rand, und seine Schleifen spannen zusammen höchstens 10 % der
   Seitenfläche auf (`ABNAHME_RISS_UFER`, `_randflaeche`), und
2. **dünn gegen die eigenen Seiten** ist: die mittlere Dicke t = 2 V / Σ A,
   mit V = |Σ ⅓ (q − c) · S| (c der Schwerpunkt der Seiten), ist höchstens
   5 % der längsten Kante L der Gruppe (`ABNAHME_RISS_DICKE`),
3. **dünn gegen die Elemente daneben** ist: t ist höchstens 0,65-mal der
   Median der Dicken 2 V_e / Σ A_e der Elemente, deren Seiten die Gruppe
   bilden, je Seite gezählt (`ABNAHME_RISS_NACHBAR`, `_elementdicke`),
4. **kein verdrehtes Element und keine doppelten Knoten** enthält: kein
   Sechsflächner, Keil oder keine Pyramide der Gruppe mit einer Kante, die
   kein anderes Element hat und nicht auf der Hülle liegt
   (`_verdrehte_elemente`, dieselbe Prüfung wie bei der Lücke im Netzrand),
   und keine zwei Knoten der Seiten im Inneren mit verschiedener Nummer am
   selben Ort – näher beieinander als 1 % der kürzesten Kante an den beiden
   (`ABNAHME_KNOTENNAEHE`) – und kein Knoten der Gruppe, den im Körper nur
   ein Element benutzt, und
5. **klein wie die Lücken des Vernetzers** ist (seit 23.09.2026): V höchstens
   2 · FLACH · L³ je vier Seiten der Gruppe, mindestens einmal
   (`ABNAHME_RISS_FLACH`, FLACH = 10⁻⁶ aus `mesher3d`), L die längste
   Elementkante des Körpers (`_laengste_kante`).

Bis zum 23.09.2026 hieß „am selben Ort“ fest 10⁻⁶ m (`ABNAHME_FUGENNAEHE`,
das die Fugenprüfung weiter benutzt), gleich wie groß die Elemente sind. Im
Block 6 × 6 × 6 über 0,75 m (Zelle 125 mm), in Kuhn-Tetraeder zerlegt, war
Tetraeder 554 an Knoten 0 oder 1 losgelöst und der neue Knoten 2 · 10⁻⁶ oder
10⁻⁵ m versetzt nur eine WARNUNG „Riss im Netz 6“ ohne Rückfrage (ec6448c).
Heute FEHLER 6, gemessen bei Versatz 2 · 10⁻⁶ m bis 1 cm (Anteil an der Kante
1,6 · 10⁻⁵ bis 0,08); ab 1,25 mm (1 %) findet ihn nur noch die Bedingung
„nur ein Element“. In den 29 geschlossenen Gruppen der Modelle von
test_mesher3d und test_sweep lagen zwei verschiedene Knoten mindestens das
0,995-Fache der kürzesten Kante an ihnen auseinander, und keinen ihrer
Knoten benutzte nur ein Element; ihre Befunde sind mit der neuen Bedingung
dieselben. Die relative Nähe hielt bis zur dritten Gegenprüfung vom
24.09.2026 keine Prüfung fest (M3): Auf fest 10⁻⁶ m verfälscht, bestand
test_diagnose ganz. Seither prüft
`test_abnahme_riss_mit_knoten_naeher_als_ein_prozent` einen Körper, der in
Kuhn-Tetraedern von unten bis zur Mitte eingerissen ist (Ebene x = 0,5 für
z < 0,5, die Seite x > 0,5 mit eigenen Knoten): im 8 × 8 × 8-Netz über 1 m
bei 2 · 10⁻⁶ bis 10⁻³ m Versatz, dazu über 10 m bzw. 0,1 m bei 0,8 % der
Zellkante, je FEHLER „Seiten im Inneren 128“ (doppelte Knoten); verfälscht
je WARNUNG „Riss im Netz 128“ ohne Rückfrage (6 Fehlschläge). Bei 2 bis
5 mm (1,6 bis 4 % der Kante) ist derselbe Körper heute ein „Riss im Netz“:
Jeden Knoten benutzen mehrere Elemente, und die Gruppe ist geschlossen
(gemessen am 24.09.2026, nicht geändert).

Bedingung 2 allein trägt an länglichen Zellen nicht: Die Dicke eines
Hohlraums folgt der kurzen Seite, L der langen. Gemessen am 23.09.2026, t/L:

| Hohlraum | t/L |
|---|---|
| Lücken des freien Vernetzers (30 geschlossene Gruppen der Modelle der Suiten test_mesher3d und test_sweep: Platte mit Bohrung, Keile am feinen Rand, Risse ohne Volumen) | 0 bis 3,31 % einzeln, bis 3,55 % als Haufen aus zehn Seiten |
| verdrehter Sechsflächner, gleichmäßiges Netz, Zelle 100 × 100 × 100 / 150 / 170 / 200 / 300 mm | 6,90 / 5,42 / 4,95 / 4,37 / 3,09 % |
| verdrehter Sechsflächner, abgestuftes Netz 5:1, 20:1, 50:1 (je alle 512 inneren Zellen) | 0,47 bis 9,75 % |
| fehlender Sechsflächner, ebenso | 2,33 bis 33,3 % |
| fehlender Tetraeder der Kuhn-Zerlegung (sechs je Zelle), gleichmäßig 100 × 100 × 100 bis 300 mm und abgestuft | 0,79 bis 7,97 % |
| fehlender Tetraeder der Platte mit Bohrung, die 40 kleinsten mit V/L³ über 0,04 (eigenes t/L) | 8,5 bis 12,8 % |

Bedingung 3 misst an der Stelle selbst. In den hex8-Netzen und ihrer
Kuhn-Zerlegung war der Hohlraum eines fehlenden Elements etwa so dick wie
seine Nachbarn, auch in länglichen Zellen; im frei vernetzten Tetraedernetz
nicht immer (Platte mit Bohrung, 34 600 tet4, die beiden letzten Zeilen).
Gemessen, t durch den Median der Nachbardicke:

| Hohlraum | t / Dicke der Nachbarn |
|---|---|
| Lücken des freien Vernetzers (dieselben 30 Gruppen), als ganze Gruppe | 0 bis 0,482 |
| Stücke solcher Gruppen: zerfällt eine Gruppe an einer Kante mit mehr als zwei Seiten in geschlossene Stücke, wird jedes für sich beurteilt (Platte mit Bohrung ohne „intelligent“, 12 925 tet4, Modell aus test_mantellinie_der_bohrung: sechs Haufen, geteilt in 12 Stücke; die beiden dicksten aus zwei verschiedenen Haufen, je 4 Seiten, 0,579 und 0,570, eines aus 6 Seiten 0,507) | 0,074 bis 0,579 |
| fehlender Sechsflächner, gleichmäßig 100 × 100 × 100 bis 500 mm und abgestuft wie oben | 1,00 bis 1,01 |
| fehlender Kuhn-Tetraeder, gleichmäßig und abgestuft wie oben | 0,865 bis 1,07 |
| verdrehter Sechsflächner, gleichmäßig und abgestuft wie oben | 0,21 bis 2,7 |
| fehlender Tetraeder der Platte mit Bohrung, die 40 kleinsten mit V/L³ über 0,04 | 0,55 bis 1,34 |
| fehlender flacher Tetraeder derselben Platte, Elemente 22584 / 2514 / 28444 (eigenes t/L 0,90 / 2,92 / 4,96 %) | 0,100 / 0,390 / 0,529 |

Die Grenze 0,65 liegt zwischen 0,579 und 0,865 (Faktor 1,12 und 1,33); nach
unten bestimmen den Abstand die Stücke der zweiten Zeile, nicht die ganzen
Gruppen (gemessen am 23.09.2026 an jeder Abnahme der beiden Suiten und an je
einer Abnahme nach jedem freien Vernetzen darin — test_mantellinie_der_bohrung
nimmt sein Netz selbst nicht ab). Bis zum 23.09.2026 stand hier 0,482 und
Faktor 1,35: gemessen an den ganzen Gruppen, nicht an den Stücken, in die die
Abnahme einen Haufen teilt (siehe unten). Beide Enden legt `test_diagnose`
fest: die Platte mit Bohrung ohne „intelligent“ als WARNUNG Riss (mit der
Grenze 0,58 noch so, mit 0,57 dazu „FEHLER Seiten im Inneren 8“) - geprüft
am Netz des Vernetzers vom Stand ec6448c, das dafür in
`tests/netz_platte_bohrung_ec6448c.npz` festgehalten ist. Der Vernetzer vom
23.09.2026 gibt für dieselbe Platte ein anderes Netz (13 708 tet4), an dem er
selbst eine verbliebene Lücke im Netzrand meldet und die Abnahme „FEHLER
Seiten im Inneren 366“ (gemessen 24.09.2026 mit der Regel für dünne Lücken,
die seit diesem Tag gilt, vorher 376; den FEHLER gibt es ebenso mit h 0,04
und 0,06 m); an ihm ist die Grenze nicht festzulegen. Das andere Ende ist der
fehlende Kuhn-Tetraeder mit 0,865 (abgestuft 50:1, Element 710, t/L 0,79 %)
als FEHLER. Ebenso, dass der Median zählt und nicht der dickste oder dünnste
Nachbar. Die
drei flachen Tetraeder der letzten Zeile liegen unter 0,65 und unter 5 % t/L;
einzeln entfernt war jeder ein Riss (siehe die Kehrseite unten). Allein
trägt auch Bedingung 3 nicht: An der Platte mit Bohrung sind die kleinsten
fehlenden Tetraeder kleiner als ihre Nachbarn (bis 0,55), dort trennt t/L. Und
den verdrehten Sechsflächner trennt keines der beiden Maße, er wird an seiner
Kante erkannt (Bedingung 4). Ebenso ein Element, das an Knoten losgelöst ist:
Erkannt wird es an den doppelten Knoten (Bedingung 4). Gemessen mit allen
vier Bedingungen, alle FEHLER „Seiten im Inneren“: die verdrehten und
fehlenden Sechsflächner und Kuhn-Tetraeder der beiden Tabellen, verdrehte
Sechsflächner unter einem windschiefen Deckel (324 Fälle: Abstufung 1:1, 5:1,
20:1, 50:1, Ecke um 0,3, 0,5 und 1,0 m angehoben, neun Zellen der beiden
obersten Lagen, drei Verdrehungen), die 40 kleinsten fehlenden Tetraeder der
Platte mit Bohrung und Elemente, die an Knoten losgelöst sind: im
gleichmäßigen 8 × 8 × 8-Netz jeder der sechs Kuhn-Tetraeder einer inneren
Zelle und einer Zelle an der Seite x = 0 an einem bis vier Knoten, der
Sechsflächner innen an einem bis vier und an allen acht Knoten, an der Seite
x = 0 an einem, zwei, vier und acht Knoten (dort mit der Bedingung „keine
doppelten Knoten“ der Lücke im Netzrand, unten). Die Gruppen der Suiten
test_mesher3d und test_sweep geben dieselben Befunde wie vorher, ebenso die
Anwendermodelle modell.json (eine WARNUNG Riss 4, Hohlraum 3,6e-19 m³) und
drehlager.json (keiner).

Bedingung 5 misst die Größe. Die Bedingungen 1 bis 4 sagen nur, dass der
Hohlraum dünn und geschlossen ist, und so ist auch der Hohlraum eines
fehlenden Tetraeders, der selbst so flach ist wie die, die der Vernetzer
aussortiert – gleich wie groß (Nebenbefund B050). An der Platte mit Bohrung
(34 600 tet4, h 50 mm) waren das 1413 von 28 046 inneren Tetraedern (innen:
alle vier Seiten mit einem Nachbarn), bis 2,05e-6 m³ (Element 17625), das
43-Fache des Medians der inneren Tetraeder. Einzeln entfernt war das ebenso
ein Riss am frei vernetzten Würfel mit um 0,5 m angehobener Ecke (h 0,25,
1483 tet4) bei 20 von 541 inneren Tetraedern, an der Platte mit Keilen (2701
tet4) bei 75 von 947 (innen heißt dort: kein Knoten auf der Hülle), an der
Platte mit Bohrung bei 4 von 40 zufällig gezogenen und bei den 15 flachsten
(eigenes t/L 0,44 bis 0,71 %). Die Zahl ist aus t/L und t/T_med
vorhergesagt, mit der Abnahme sind je Modell sechs Fälle bestätigt (alle
„WARNUNG Riss“, `abnahme()` leer). Und der Text nannte als Herkunft den
Vernetzer, auch für einen von Hand gelöschten Tetraeder (L-Prisma h 0,12,
35 728 mm³, t/L 3,65 %), wo der Vernetzer nur V ≤ FLACH · h³ = 1,7 mm³
aussortiert (Nebenbefund B051). Das Volumen gegen den Median der
Nachbarvolumina (je Seite) trennt nicht: die Lücken des Vernetzers erreichen
das 1,65-Fache (ein Haufen aus 15 Seiten), mehr als ein fehlender Tetraeder
so groß wie seine Nachbarn. Gemessen wird deshalb gegen die Regel des Vernetzers, V ≤ FLACH · h³ je
Tetraeder, mit L für h. L ist nicht h: An den gemessenen freien Netzen lag
L beim 1,02- bis 2,00-Fachen von h (`_laengste_kante`, 24.09.2026: Platte
mit Bohrung h 50 mm, L 50,9 mm; Würfel mit angehobener Ecke h 0,25 m bei
dz 0,3 / 0,5 / 1,0: 1,72 / 1,72 / 1,68 h, h 0,5 m: 2,00 h, h 0,1 m bei dz
0,3 / 1,0: 1,72 / 1,77 h; L-Prisma h 0,25 / 0,12 / 0,1 m: 2,00 / 1,76 /
1,72 h). Die Grenze 2 · FLACH · L³ ist dort also das 2,1- bis 16-Fache von
FLACH · h³; gesetzt ist sie an den Messwerten der Tabelle, nicht aus h
hergeleitet. Gemessen am 23.09.2026, V / (FLACH · L³) je vier
Seiten:

| Hohlraum | V / (FLACH · L³) |
|---|---|
| Lücken des freien Vernetzers (dieselben 30 Gruppen; L 50,9 bis 257 mm) | 0 bis 0,87 (Haufen aus 8 bis 15 Seiten bis 0,26) |
| fehlender flacher Tetraeder, Platte mit Bohrung (1413, vorhergesagt) | 0,35 bis 15 490, 48 bis 2 |
| ebenso Platte mit Keilen (2701 tet4, 183 von 2099) | 1,10 bis 13 250, 7 bis 2 |
| ebenso L-Prisma h 0,12 (6173 tet4, 306 von 5275) | 525 bis 10 261 |
| ebenso Würfel mit angehobener Ecke, h 0,25 (1483 tet4, 58 von 1208) | 560 bis 11 496 |

Die Grenze 2 liegt um den Faktor 2,3 über den Lücken des Vernetzers. Mit der
Abnahme gerechnet: die Platte ohne Element 17625 FEHLER „Seiten im Inneren 4“
(dazu die 8 Rissseiten des Vernetzers), an der Grenze das 1,97- und
1,99-Fache ein Riss, das 2,01- und 2,03-Fache ein FEHLER; am L-Prisma und am
Würfel jeder der je sechs gerechneten ein FEHLER. Die Kehrseite: Fehlende flache Tetraeder
bis 2 · FLACH · L³ bleiben ein Riss, so klein wie die Lücken des Vernetzers
und von ihnen nicht zu trennen (an der Platte mit Bohrung bis 0,26 mm³). Der
Text des Risses nennt deshalb die Größe (2 · 10⁻⁶ · L³ mit dem Wert von L),
nicht die Herkunft; der Text von „Seiten im Inneren“ nennt als eine Ursache
ein fehlendes Element, etwa von Hand gelöscht oder beim Import verloren. L ist
die längste Kante im ganzen Körper: In einem abgestuften Netz ist die Grenze
dort, wo die Elemente viel kleiner als L sind, entsprechend weit. Die
Bedingung macht einen Riss nur strenger, kein FEHLER der Messungen oben wird
dadurch ein Riss. Die fehlenden flachen Tetraeder hatten ein eigenes t/L von
höchstens 4,98 %; jeder entfernte Tetraeder mit eigenem t/L über 5 % war ein
FEHLER.

Die Netze dieser Messungen stammen vom eigenen Vernetzer vor seiner Änderung
vom 23.09.2026 (Vernetzer-Sitzung: Startpunkte mit Abstand zur Hülle,
`tetraedern_treu`). Seither hat die Platte mit Keilen 2502 statt 2701 tet4,
das L-Prisma h 0,12 6155 statt 6173 und der Würfel 1085 statt 1483; die
Zählungen der Tabelle sind daran nicht wiederholt. Nachgemessen am 24.09.2026
sind die Einzelfälle der Prüfungen: An der Platte mit Keilen heißen die
beiden flachen Tetraeder jetzt 58 (1,752e-6 m³, t/L 4,06 %, ohne ihn FEHLER
„Seiten im Inneren 4“ und die 4 Rissseiten des Vernetzers) und 2414
(1,454e-10 m³ = 1,10 FLACH · L³, ohne ihn WARNUNG „Riss im Netz 8“), mit
unverändertem Volumen und t/L; am L-Prisma h 0,12 ist der flachste Tetraeder
unter der Deckelmitte des langen Schenkels 36 097 mm³ groß (t/L 3,67 %), von
Hand gelöscht FEHLER „Seiten im Inneren 4“ mit Rückfrage
(`test_abnahme_luecken_des_vernetzers_sind_risse`,
`test_abnahme_luecke_im_netzrand`).

Seit dem Nachtrag B101 des Vernetzers (24.09.2026) behält er an der Platte mit
Keilen den Tetraeder 2478 (1,151e-10 m³ = 0,87 FLACH · L³, t/L 1,48 %), dessen
Lücke bis dahin der Riss mit 4 Seiten war. Die Platte hat jetzt 2503 tet4 und
ohne Eingriff keinen Befund. Ohne 58 allein meldet die Abnahme dort nur
FEHLER „Seiten im Inneren 4“, ohne 2414 allein WARNUNG „Riss im Netz 4“. Die
Befunde oben (FEHLER 4 mit den 4 Rissseiten, Riss 8) gelten mit dem von Hand
entfernten 2478. So prüft es der Test: am festgehaltenen Netz
`tests/netz_platte_keile_7ce5510.npz`, aus dem er 2478 nach seinen
Eigenschaften herausnimmt (innen, t/L ≤ 5 %, V ≤ FLACH · h³). Dazu prüft er,
dass der dünnste innere Tetraeder (1524, t/L 0,76 %, 88,9 FLACH · L³) ohne
Größenregel ein Riss wäre, mit ihr aber ein FEHLER ist. Am L-Prisma wählt die
Prüfung seither den größten inneren Tetraeder, dessen Hohlraum ohne
Größenregel ein Riss wäre (heute 89 985 mm³, t/L 4,72 %). Mit anderen Phasen
des BCC-Gitters lag unter der Deckelmitte nicht immer ein flacher Tetraeder.
Alles gemessen am 24.09.2026, zweimal.

Rand der Gruppen des Vernetzers 0 bis 5,6 % der Seitenfläche. Offene Gruppen:
drei Würfel in einer Reihe mit verdrehtem mittlerem 41 %, verdrehter Boden
26 %, verdrehtes Eckelement 30 %, eine Trennfläche aus doppelten Knoten, die
bis an die Hülle geht, 100 % (ein Ufer ohne Gegenüber). Ist dagegen nur ein
Sechsflächner im Inneren an den vier Knoten einer Seite losgelöst, ist die
Gruppe geschlossen und hat kein Volumen; das fängt Bedingung 4. Die Summe
der Flächenvektoren taugt als Merkmal nicht: in der Reihe heben sich die
vordere und die hintere Öffnung auf (|Σ S| = 0, scheinbares Volumen 0).

Die erste Fassung (7000048, 23.09.2026) verlangte Ebenheit auf 1 % des
Seitendurchmessers; die Hohlräume sind aber 1,7 bis 11 % dick und standen als
FEHLER da (Platte mit Bohrung, 34 600 tet4: 8 Seiten; Keile am feinen Rand,
2701 tet4: 4 Seiten). Die zweite Fassung (3f5ae87) ließ V ≤ n · FLACH · h_max³
zu, mit h_max der größten Elementdiagonale im ganzen Körper — in abgestuften
Netzen so viel, dass ein verdrehter Sechsflächner (50:1, Hohlraum 448 mm³)
und jeder der 40 fehlenden Tetraeder an der Platte mit Bohrung als Riss
durchgingen (Gegenprüfung, Mangel 1). Die dritte Fassung (e188334) hatte nur
die Bedingungen 1 und 2. Sie hielt t/L für ein Maß „nur an der Gruppe selbst,
nicht an der Abstufung" und hatte den verdrehten Sechsflächner nur an der
Würfelzelle gemessen (6,90 %). In länglichen Zellen ging er als Riss durch
(Zelle 100 × 100 × 200 mm: „WARNUNG Riss im Netz 8 … Der Körper stimmt", keine
Rückfrage vor dem Rechnen; abgestuft 50:1: 357 von 512), ebenso fehlende
Sechsflächner (72 von 512) und Kuhn-Tetraeder (340 von 512) und verdrehte
Elemente unter windschiefem Deckel (75 von 324). Das war die zweite
Gegenprüfung vom 23.09.2026, Mangel 1.

Diese drei Fassungen waren **nie ausgeliefert**: Zwischenstände des
Entwicklungszweigs vom 23.09.2026 (7000048 um 00:10, 3f5ae87 um 03:16,
e188334 um 05:15), abgelöst von 8c7a116 (06:27). Dieselben Stände sind die
erste, zweite und dritte Fassung, die unten bei den windschiefen Flächen und
bei der Laufzeit genannt sind. Der Hauptzweig ging mit dem
Merge 21ce779 (23.09.2026, 10:07) vom Stand 5eb21e6 gleich zu 8c7a116 und
den Nachbesserungen danach; die Abnahme von 5eb21e6 kannte weder die
Volumenbilanz noch „Seiten im Inneren“, „Riss im Netz“, „Lücke im Netzrand“
oder „Netzrand neben der Hülle“ (am Quelltext). Gemessen an einem L-Prisma
(821 tet4, h 0,25) mit einer Lücke von 552 cm³ an der Oberfläche: die
Abnahme von 54b6f9a (gleicher Baum wie 5eb21e6) mit `warnungen=True` ohne
Befund, die heutige mit der WARNUNG „Lücke im Netzrand“.

Zwei Hohlräume, die sich nur an einer Kante berühren (dort liegen vier
Seiten), werden getrennt beurteilt — aber nur, wenn jedes Teil für sich
geschlossen ist. An der Platte mit Bohrung berührte ein fehlender Tetraeder
(4,27e-10 m³) eine Lücke des Vernetzers (3,4e-11 m³); zusammengezählt war
t/L = 4,8 %, ein Riss. Ohne die Bedingung zerfiel dagegen ein Haufen aus
15 Seiten (Rand 5,6 %) in drei geschlossene und zwei offene Stücke, und
3 Seiten wurden ein FEHLER. Getrennt wird nach der Form (Bedingungen 2 und
3); die Größe (Bedingung 5) gilt je Stück. In der seriellen Gegenprobe von
`test_gemeinsame_flaeche_konform` (test_fugen, 2288 tet4) berührte ein
Hohlraum von 3,6e-5 m³ einen Riss ohne Volumen; im Ganzen an der Größe
gemessen, wurde der Riss mit zum FEHLER (27 statt 23 Seiten).

Vorher/nachher an allen Modellen, die die Testfunktionen der Suiten bauen
(Stand am Ende jeder Funktion, `_abnahme_netz` gegen ec6448c, 23.09.2026):
gleich in test_mesher3d (26), test_sweep (42), test_netzfeld (2),
test_netzverfeinerung (2), test_neuvernetzen (3), test_netzdichte (2),
test_vernetzer_extern (3), test_supports (28), test_netzfehler (7),
test_geometrie_kette (5), test_singular (38) und test_lasten (32). Anders
nur, wo es gemeint ist: test_fugen 62 von 63 gleich – die parallele
Gegenprobe ohne modellweite Karten (2655 tet4) hat in V_oben einen Hohlraum
von 9,8 cm³ aus 11 Seiten (das 2700-Fache der Grenze), jetzt FEHLER
„Seiten im Inneren 11“ statt Riss; test_elemente 46 von 47 – der Master
eines RBE3 ohne Element ist kein „Knoten ohne Element“ mehr; test_diagnose
63 von 68 – die neuen Fälle dieser Nachbesserung und das Beispiel „Kontakt:
abhebendes Lager“, dessen Anschlagknoten über ein Spaltelement am Träger
hängt (vorher FEHLER „Knoten ohne Element 1“). Nach der Gegenprüfung vom
24.09.2026 (siehe `_angeschlossene_knoten` unten) für diesen Befund
nachgezählt, lose Knoten bei ec6448c, mit der Fassung vom 23.09. und jetzt:
anders als mit der Fassung vom 23.09. nur die Fälle der neuen Prüfung
`test_abnahme_knoten_in_drei_richtungen`. Gleich geblieben sind das
Beispiel und `test_gap_element` (test_solver_ext; beide ein Anschlag, ohne
Befund), der RBE3-Master (test_elemente), test_stabende (1 statt 3 lose
Knoten), `test_abnahme_knoten_ueber_kopplung` und alle Modelle von
test_joints, test_lasten, test_netzfeld, test_neuvernetzen,
test_randspannung, test_importers, test_supports, test_singular,
test_netzfehler, test_fugen, test_rfem6, test_mesher3d, test_sweep und
test_tetp.

**Lücke im Netzrand** (23.09.2026, Gegenprüfung Mangel 3). Ist eine Gruppe von
Seiten im Inneren offen, und liegt jede ihrer Randschleifen auf der Hülle, fehlt
dem Netz an der Oberfläche ein Stück. Auf der Hülle heißt (`_schliesspunkt`):
Jede Kante der Schleife liegt in einer Randfläche, eben oder bilinear (dann
gilt die Tangentialebene an der Kantenmitte). Es gibt einen Punkt p₀ auf all
diesen Ebenen (an einer Kante des Körpers auf der Kante, in einer Ecke in der
Ecke), und der Fächer von p₀ über die Schleife liegt auf der Hülle. Das
Volumen ist dann V = |Σ (q − p₀) · S − Σ (p₀ − c) · A_Schleife| / 3, wobei
die Fächer auf den Ebenen durch p₀ nichts beitragen. Dazu zählen Seiten, die
über die Hülle hinausstehen, wenn der Rand der Gruppe erst mit ihnen auf der
Hülle liegt. Gezählt wird dann nur, was im Körper fehlt. Am T-Prisma (h 0,1)
an der einspringenden Kante fehlen 2,43e-5 m³, und 1,26e-5 m³ Netz stehen in
die Aussparung; die Bilanz sind 1,17e-5 m³. Keine Lücke ist die Gruppe,

* wenn eines ihrer Elemente **verdreht** ist (`_verdrehte_elemente`): ein
  Sechsflächner, Keil oder eine Pyramide mit einer Kante, die kein anderes
  Element des Körpers hat und die nicht auf der Hülle liegt. Beim verdrehten
  Sechsflächner laufen die Seitenkanten über die Diagonalen der
  Nachbarseiten. Dass beide Knoten auch in einem Nachbarn stehen, genügt
  darum nicht als „gemeinsame Kante": So galt im ersten Entwurf das verdrehte
  Eckelement eines 3 × 2 × 2-Blocks als Lücke. Tetraeder bleiben außen vor:
  Jede Folge von vier Knoten ist derselbe Tetraeder, und ein Netz mit Lücke
  hat Kanten, die nur noch ein Element trägt;
* wenn ihre Seiten **doppelte Knoten** haben (wie Bedingung 4 des Risses,
  gesucht unter allen Seiten im Inneren): Ein Element an der Oberfläche, das an Knoten losgelöst ist, **kann**
  offene Gruppen zurücklassen, deren Rand auf der Hülle liegt, obwohl nichts
  fehlt – gemessen nur bei bestimmten Knotenmengen: der Kuhn-Tetraeder 164
  (ebenso 165) erst, wenn mindestens zwei seiner Hüllknoten losgelöst sind,
  der Tetraeder 162 derselben Zelle bei keiner der 15 Mengen, der
  Sechsflächner 27 bei 39 von 163 Mengen, an einem einzelnen Knoten nie. Gemessen am Kuhn-Tetraeder 2 der Zelle 27
  an der Seite x = 0 des gleichmäßigen 8 × 8 × 8-Netzes (Element 164), an
  seinen drei Knoten auf der Hülle oder an allen vier losgelöst: zwei Gruppen
  mit je dem Volumen des Elements (326 cm³). Mit dieser Bedingung ist das
  ein FEHLER „Seiten im Inneren 6“, ebenso der Sechsflächner der Zelle 27 an
  allen acht Knoten (10 Seiten);
* wenn sie ein **Gegenüber** hat (`_haengende_gruppen`): Ein Knoten einer
  offenen Gruppe liegt auf einer Seite einer anderen Gruppe, ohne ihre Ecke zu
  sein (Abstand ≤ 1 % ihrer längsten Kante, `ABNAHME_KNOTENNAEHE`); dann sind
  beide Gruppen Ufer derselben Stelle, ein T-Stoß mit hängenden Knoten oder
  eine Trennfläche. Jedes Ufer schließt mit der Hülle den vernetzten Block
  dahinter ein und hat darum Volumen. Gemessen am 23.09.2026 im
  8 × 8 × 8-Netz des Würfels 1 × 1 × 1 m: die Eckzelle in 2 × 2 × 2 geteilt
  (T-Stoß an der Oberfläche) war in Kuhn-Tetraedern zwei Lücken von zusammen
  3906 cm³ und sonst nichts (`abnahme()` leer), in hex8 eine Lücke 1953 cm³
  neben FEHLER 12; die Eckzelle mit eigenen Knoten abgetrennt, 10⁻⁵ oder
  10⁻³ m versetzt, eine Lücke 1953 cm³ neben FEHLER 3. Heute FEHLER 15 bzw.
  30 und 6 Seiten;
* wenn sie **kein Volumen** hat: 2 V / A ≤ 1 % von L (`ABNAHME_KNOTENNAEHE`),
  die Seiten liegen dann auf dem Fächer über der Hülle. Bis zum 23.09.2026
  galt hier t/L ≤ 5 % (Bedingung 2 des Risses), und eine dünne echte Lücke
  war ein FEHLER: am L-Prisma (h 0,2, 1493 tet4, ohne Befund) die von Hand
  gelöschten Elemente 62, 69 und 70 (1,643 / 2,495 / 2,245 · 10⁻⁴ m³, t/L
  2,87 / 4,50 / 3,36 %). Heute Lücken mit genau diesen Volumina. Seiten im
  Inneren liegen mit ihrem Schwerpunkt weiter als 1 % ihres Durchmessers
  neben der Hülle, und das Ufer einer Trennfläche fängt das Gegenüber; eine
  Gruppe, an der diese Bedingung mit der Grenze 1 % greift, ist nicht
  gemessen worden. Sie bleibt als Schranke. Gemessen ist dafür, wo sie
  kippt: Die Regel misst die Dicke der Gruppe gegen ihre eigenen Seiten,
  t = 2 V / A durch L, nicht nur „Volumen ja oder nein“ (Befund B029). Am
  verdrehten Sechsflächner am Rand des abgestuften Netzes 5:1 (Element 55,
  Zelle 3,64e-4 m³), mit abgeschalteter Regel „verdreht", die im Programm bei
  ihm vorher greift, hat die Gruppe t/L 4,845 % bei 1,21e-4 m³, einem
  Drittel der Zelle. Mit der Grenze 5 % (bis B044) war das ein FEHLER „Seiten
  im Inneren 7", mit 1 % ist es eine WARNUNG „Lücke im Netzrand“ mit
  1,21e-4 m³; mit `ABNAHME_KNOTENNAEHE` 4,85 % wieder der FEHLER, mit 4,84 %
  die Lücke (gemessen am 24.09.2026; `test_abnahme_luecke_duenn_mit_volumen`);
* wenn sich kein p₀ findet: Die Schleife um einen Körper, den doppelte Knoten
  zerschneiden, läuft über gegenüberliegende Flächen.

Jede dieser Regeln entscheidet in `test_diagnose` mindestens einen Fall
allein. Gemessen mit Verfälschungen in `luecke()` bzw. `_schliesspunkt` am
Stand 84b41ea (121 Prüfungen, 24.09.2026): ohne „verdreht“ bestehen 117,
ohne „doppelte Knoten“ 120, ohne „kein Volumen“ 120 und ohne „kein p₀“ 120.
„Kein p₀“ ist dabei nur als Ganzes festgelegt: Von ihren zwei Abweisungen,
„kein gemeinsamer Punkt“ und „Fächer nicht auf der Hülle“, fängt jede die
Kerbe unten auch allein, und fehlt nur eine von beiden, besteht die Suite
ganz (121). Die alte Suite (ec6448c, 112 Prüfungen) legte nur die ersten
beiden Regeln fest: ohne „verdreht“ bestanden 109, ohne „doppelte Knoten“
111; ohne „kein Volumen“ oder ohne „kein p₀“ bestand sie ganz. Gemessen am
23.09.2026:

* Eine Kerbe durch die ganze Dicke am Rand einer Platte (1 × 1 × 0,125 m,
  16 × 16 × 2 Sechsflächner, zwei Zellen entfernt) hat eine Schleife über
  Deckel, Boden und Seitenfläche, deren Ebenen keinen gemeinsamen Punkt
  haben: FEHLER „Seiten im Inneren 6“. Ohne die beiden Abweisungen „kein
  gemeinsamer Punkt“ und „Fächer nicht auf der Hülle“ wäre sie eine Lücke
  von 3,255e-4 m³, zwei Drittel der fehlenden 4,883e-4 m³, weil der Fächer
  von p₀ in halber Höhe durch den Körper läuft. Jede der beiden
  Abweisungen allein fängt diesen Fall. An dünnen Platten kann eine Kerbe
  durch die ganze Dicke auch eine Lücke sein oder gar nicht gemeldet
  werden. Am Quelltext entscheiden drei Stellen nacheinander.
  (1) `_abnahme_volumenbilanz` zählt eine Seite zur Randfläche, wenn ihr
  Schwerpunkt höchstens `ABNAHME_HUELLABSTAND` mal ihren Durchmesser neben
  der Ebene liegt. Eine Kerbseite der obersten oder untersten Lage
  (Zellweite w, Lagendicke t_L) liegt t_L/2 neben Deckel bzw. Boden, und
  t_L/2 ≤ 0,01·√(w² + t_L²) gilt für w ≥ 49,99·t_L (gemessen an einer
  Lage mit w = 250 mm, Kerbe 0,5 × 0,5 m: bei w/t_L 49 eine Lücke, bei
  50,5 und 51 kein Befund). Solche Seiten kommen nicht zu den Seiten im
  Inneren; liegen alle Kerbseiten so, bleibt nur die Volumenbilanz.
  (2) Die übrigen Seiten bilden eine Gruppe; sie ist geschlossen, wenn
  die Summe der Beträge der Flächenvektoren ihrer
  Randschleifen höchstens `ABNAHME_RISS_UFER` = 10 % ihrer Fläche ist. Bei
  einer rechteckigen Kerbe heben sich die Anteile der Schleife oben und
  unten auf, es bleibt die Öffnung in der Seitenfläche, b·t, gegen die
  Fläche (b + 2a)·t (Breite b, Tiefe a, t die Dicke der Lagen mit Seiten
  im Inneren; gemessen war der Rand in allen Fällen unten genau b·t):
  geschlossen für a > 4,5·b, dann FEHLER „Seiten im Inneren“, ohne dass
  `_schliesspunkt` gefragt wird. Bei a = 4,5·b stehen beide Seiten
  gleich; gemessen war die Kerbe 0,1 × 0,45 m offen und eine Lücke von
  1,5e-4 m³. (3) Eine offene Gruppe hat einen Schließpunkt, wenn die
  halbe Dicke höchstens die Toleranz von `luecke()` ist (1 % des Größeren
  aus der Raumdiagonale des
  Quaders um die Schleife und der längsten Seitenkante der Gruppe); dann
  gilt p₀ in halber Dicke als Punkt auf allen Ebenen. Gemessen am
  24.09.2026 mit `_platte` aus `tests/test_diagnose.py`, Kerbe am
  Rand y = 0: Blech 4 × 4 × 0,005 m aus 80 × 80 × 1 (w = 50 mm), Kerbe 0,2 × 0,2 m
  (2,0e-4 m³): „WARNUNG Lücke im Netzrand 1,333e-4 m³“, zwei Drittel. Im
  selben Blech offen und eine Lücke: Kerbe 0,1 × 0,3 m (Rand 14,29 %,
  1,0e-4 von 1,5e-4 m³) und 0,1 × 0,4 m (11,11 %, 1,333e-4 m³);
  geschlossen und FEHLER, obwohl die halbe Dicke (2,5 mm) unter der
  Toleranz liegt: 0,1 × 0,5 m (9,09 %, „Seiten im Inneren 22“) und
  0,05 × 0,3 m (7,69 %, 13). Blech 2 × 2 × 0,005 m (40 × 40 × 1), Kerbe
  0,1 × 0,1 m: Toleranz 1,42 mm, FEHLER „Seiten im Inneren 6“. Platte
  10 × 10 × 0,01 m, Kerbe 0,5 × 0,5 m (2,5e-3 m³, Toleranz 7,07 mm): bei
  w = 125 mm (80 × 80) mit einer, zwei und drei Lagen je Lücke
  1,667e-3 m³ (w/t_L 12,5 bis 37,5; 12, 24 bzw. 36 Kerbseiten im
  Inneren); bei w = 250 mm (40 × 40) mit einer Lage ebenso (w/t_L 25),
  mit zwei Lagen kein Befund (w/t_L 50, Schwerpunkt 2,5 mm neben der Ebene
  bei 2,5005 mm Toleranz), mit drei Lagen Lücke 5,556e-4 m³ (nur die sechs
  Seiten der mittleren Lage im Inneren, zwei Drittel ihrer 8,333e-4 m³);
  bei w = 500 mm (20 × 20) mit einer, zwei und drei Lagen kein Befund
  (eine Lage: 5 mm bei 5,001 mm Toleranz; bei drei Lagen die mittlere
  Lage 5 mm neben Deckel und Boden bei 5,0001 mm). Die Zahl der Lagen
  wirkt nur über den Abstand der Seitenschwerpunkte zu Deckel und Boden; den
  Ausschlag gibt dieser Abstand gegen 1 % des Seitendurchmessers, also die
  Zellweite gegen die Lagendicke. Kerbe 0,25 × 0,25 m bei w = 250 mm, eine
  Lage: Toleranz 3,54 mm, FEHLER „Seiten im Inneren 3“. Mit
  `ABNAHME_HUELLABSTAND` 0,001 statt 0,01 waren es bei w = 250 mm und
  einer, zwei und drei Lagen FEHLER „Seiten im Inneren“ (6, 12, 18).
* Ein Loch durch die ganze Dicke mitten in derselben Platte hat zwei
  Schleifen, im Deckel und im Boden: Lücke 4,883e-4 m³, das Volumen der
  zwei Zellen. Ohne den Fächer der zweiten Schleife wären es 3,255e-4 m³.
* Eine Schleife im Deckel des L-Prismas, deren eine Kante über die
  Aussparung läuft (Kantenmitte 50 mm neben dem Deckel), hat keinen
  Schließpunkt. Das entscheidet allein die Regel „jede Kante in einer
  Randfläche“: Ohne sie läge p₀ bei (0,34 | 1,04 | 0,4) auf dem Deckel, und
  die Schwerpunkte der fünf Fächerdreiecke lägen auf dem Deckel (Abstand 0).
  Nur diese Schwerpunkte misst die Abweisung „Fächer nicht auf der Hülle“,
  sie ließe die Schleife also durch. Der Fächer selbst liegt nicht ganz auf
  dem Deckel: Zwei seiner Dreiecke reichen über die Aussparung, bis 50 mm
  neben die Hülle bei einer Toleranz von 16,9 mm (gemessen 24.09.2026).
* Den verdrehten Sechsflächner am Rand (abgestuft 5:1, Element 55) hielt
  bis B044 jede der beiden Regeln allein: die Erkennung des verdrehten
  Elements auch mit der Dickengrenze 0,02, die Dünnregel ohne die Erkennung,
  diese knapp (t/L 4,845 %, mit einer Dickengrenze bis 0,04845 eine Lücke
  von 1,212e-4 m³). Mit der Dünnregel von B044 (1 %) hält ihn die Erkennung
  allein; ohne sie ist er die Lücke (`test_abnahme_luecke_im_netzrand`).
* Doppelt sind Knoten näher als 1 % der kürzesten Kante an ihnen
  (`ABNAHME_KNOTENNAEHE`; bis zum 23.09.2026 fest `ABNAHME_FUGENNAEHE` =
  10⁻⁶ m, siehe Bedingung 4 des Risses), nicht nur deckungsgleiche: Ein
  innerer Kuhn-Tetraeder des 8 × 8 × 8-Netzes, an einem Knoten 5 · 10⁻⁷ m
  daneben losgelöst, bleibt FEHLER „Seiten im Inneren 6“.

Eine Folge der neuen Volumenbedingung an einem Netz des eigenen Vernetzers: An der
Platte 1 × 0,6 × 0,2 m mit Bohrung r 0,1 m, mit `mesh_koerper_frei`
vernetzt (Ziellänge 0,04 m, 30 013 tet4), waren zwei offene Gruppen von je 4
Seiten mit geschlossenem Rand auf der Hülle (V je 1,652 · 10⁻⁷ m³, t/L
3,47 %, t / Dicke der Nachbarn 1,07 und 1,15) ein FEHLER; heute zwei Lücken
von zusammen 0,33 cm³ (WARNUNG), die übrigen 4 Seiten bleiben ein FEHLER
(Netzrand verfehlt die Randfläche, unten).

**Die Ursache des FEHLERs** (23.09.2026). Was weder Riss noch Lücke ist,
bekommt je Gruppe eine Ursache, und der Text nennt sie mit der Zahl der
Seiten (`_URSACHEN`), in dieser Reihenfolge der Prüfung: doppelte Knoten
(zwei Nummern näher als 1 % der kürzesten Kante; ein Knoten in nur einem
Element, bei offenen Gruppen nur, wenn er weiter als 1 % seiner kürzesten
Kante von jedem Punkt der Randlinien liegt und ein anderer Knoten der Seiten
im Inneren näher als `ABNAHME_GEGENSTUECK` = 0,5 mal die kürzere der beiden
kürzesten Kanten an ihm; ein Gegenüber über einen
solchen Knoten; oder ein Gegenüber, bei dem keine der Seiten, auf denen die
Knoten liegen, eine Ecke mit dem Ufer des Knotens teilt – bei geschlossenen
Gruppen entscheidet danach noch die Füllung); hängende Knoten (Gegenüber,
siehe oben, ohne losgelösten Knoten, und wenigstens eine dieser Seiten teilt
eine Ecke mit dem Ufer des Knotens; oder eine geteilte Kante in der Gruppe
selbst, `_halbierte_kante`: eine Kante a–b einer ihrer Seiten und eine
Kette von Knoten auf der Strecke a–b, näher als 1 % ihrer Länge, von a nach
b über Kanten der Gruppe verbunden, ohne dass eine Seite a, b und einen
dieser Knoten zugleich hat); verdrehtes Element (nur, wenn die Kante, die
kein anderes Element hat, die Diagonale einer Viereckseite eines anderen
Elements ist; bei offenen Gruppen seit der dritten Gegenprüfung vom
24.09.2026); bei geschlossenen Gruppen doppelte
Knoten, wenn ihre Seiten aus dem umschlossenen Raum hinauszeigen
(Σ (q − c) · S > 0 mit S vom eigenen Element weg: sie umschließen Elemente),
sonst Hohlraum; bei offenen doppelte Knoten, wenn eine ihrer Seiten eine
**Kopie** aus eigenen Knoten neben sich hat (jeder ihrer Knoten hat einen
anderen näher als 0,5 mal die kürzere der kürzesten Kanten, und diese Knoten
bilden eine andere freie Seite); **keine sicher bestimmte Ursache**, wenn
eine Kante bleibt, die kein anderes Element hat (keine Diagonale), oder ein
Knoten in nur einem Element ohne Knoten daneben; sonst **Netzrand verfehlt
die Randfläche**. Zuletzt
die Füllung: Zeigen die Seiten einer geschlossenen Gruppe in den
umschlossenen Raum, und heißt sie nach den Regeln oben „doppelte Knoten“
oder „Hohlraum“ mit einem losgelösten Bereich darin, zählt der Rest
V_rest = V − Σ V_B. V ist ihr umschlossenes Volumen (−Σ (q − c) · S / 3), V_B das der losgelösten
Bereiche darin (Gruppen „doppelte Knoten“ mit Σ (q − c) · S > 0; darin
heißt: die Windungszahl der Gruppe, nach S ausgerichtet, ist am Schwerpunkt
eines Elements des Bereichs nicht 0). Ist V_rest höchstens
`ABNAHME_HOHLRAUM_REST` = 0,5 mal der Median der Volumina ihrer Elemente,
heißt die Gruppe „doppelte Knoten“, sonst „Hohlraum“. Das Gegenüber
wird dafür an allen Gruppen ohne Ursache gesucht und an den Gruppen, die mit
ihnen Knoten teilen, nicht nur an offenen. Die Reihenfolge ist nötig, weil
`_verdrehte_elemente` auch ein losgelöstes Element und die feinen Elemente
eines T-Stoßes nennt: Ihre Kanten teilt kein anderes Element (T-Stoß in der
Ecke, hex8: vier Elemente „verdreht“). Vorher stand für jede Gruppe
„verdrehtes Element, doppelte Knoten oder Hohlraum“ da. Gemessen:

| Fall (23.09.2026) | Befund | Ursache |
|---|---|---|
| T-Stoß hex8 (1 gegen 2 × 2 × 2), Körper 2 × 1 × 1 m | FEHLER 5 (vorher ebenso) | hängende Knoten |
| derselbe in Kuhn-Tetraedern | FEHLER 10 (vorher ebenso) | hängende Knoten |
| U-Prisma 1,5 × 1 × 0,5 m, h 0,3, Standardweg, 1113 tet4, konform | FEHLER 4, WARNUNG Netzrand 9 | Netzrand verfehlt die Randfläche |
| Platte 0,6 × 0,6 × 0,035 m, Bohrung r 6 mm (24-Eck), Ziellänge 0,05 m, `modell_vernetzen`, 24 712 tet4 | FEHLER 110, WARNUNG 29 | Netzrand verfehlt die Randfläche |
| dieselbe mit `mesh_koerper_frei`, 14 242 tet4 | FEHLER 126, WARNUNG 31 | Netzrand verfehlt die Randfläche |
| Stufe d 0,45 mm, t 0,02 m, `mesh_koerper_frei`, 1437 tet4 | FEHLER 5, WARNUNG Riss 4, Netzrand 12 | Netzrand verfehlt die Randfläche |
| Zelle 100 × 100 × 200 mm, Element 444 verdreht | FEHLER 8 | verdrehtes Element |

Die Netze des eigenen Vernetzers in dieser Tabelle stammen von seinem Stand
vor dem 23.09.2026. Der Vernetzer vom 23.09.2026 gibt am U-Prisma h 0,3
317 tet4 ohne Befund und an der Stufe 1626 tet4 mit FEHLER „Seiten im
Inneren 81“ (Ursache Hohlraum; gemessen 24.09.2026). Die Prüfungen der
Ursache „Netzrand verfehlt die Randfläche“ laufen darum an den alten Netzen,
festgehalten in `tests/netze_vernetzer_ec6448c.npz` (U-Prisma 1113 tet4,
Stufe 1437 tet4, dort FEHLER 5, WARNUNG Riss 4 und Netzrand 12).

Die erste Fassung (70614f8) suchte das Gegenüber nur zwischen offenen
Gruppen und Knoten in nur einem Element nur in geschlossenen (Gegenprüfung
vom 23.09.2026). Am 24.09.2026 an diesem Stand und an der Nachbesserung
gemessen, die Befunde sind in beiden gleich, nur die Ursache ändert sich
(8 × 8 × 8-Netz des Würfels 1 × 1 × 1 m, Kante 125 mm; Versatz in Richtung
(0,6 | 0 | 0,8)):

| Fall | Befund | Ursache 70614f8 | Ursache f2bf6c8 |
|---|---|---|---|
| T-Stoß im Inneren: 3 × 3 × 3 hex8, Mittelzelle 2 × 2 × 2, Σ V = 1 | FEHLER 30 | verdrehtes Element 24, Hohlraum 6 | hängende Knoten 30 |
| derselbe in Kuhn-Tetraedern | FEHLER 60 | Hohlraum 60 | hängende Knoten 60 |
| Schachbrett 8 × 8 × 8 hex8, jede zweite Zelle 2 × 2 × 2 | FEHLER 1344, WARNUNG Riss 5376 | Netzrand verfehlt die Randfläche, Rat zum Sweep | hängende Knoten |
| Kuhn-Tetraeder 164 an der Seite x = 0, drei Hüllknoten losgelöst, 1,25 / 1,3 / 1,6 / 2 / 2,5 mm | FEHLER 6 | hängende Knoten | doppelte Knoten |
| Eckzelle mit eigenen Knoten abgetrennt, 2 / 5 mm | FEHLER 6 / 8 | hängende Knoten | doppelte Knoten |
| hex8 27 an der Seite x = 0, vier Hüllknoten losgelöst, 1,3 / 2 / 5 mm | FEHLER 8 / 8 / 9 | verdrehtes Element | doppelte Knoten |
| hex8 292 im Inneren an allen acht Knoten losgelöst, 0 / 0,01 / 2 mm | FEHLER 12 | doppelte Knoten 6, Hohlraum 6 | doppelte Knoten 12 |
| innerer Block 2 × 2 × 2 (Zellen 3 und 4 je Richtung) mit eigenen Knoten auf seiner Oberfläche, hex8, 0 / 0,01 / 1 / 2 mm | FEHLER 48 | doppelte Knoten 24, Hohlraum 24 | doppelte Knoten 48 |
| derselbe in Kuhn-Tetraedern, 0 / 0,01 / 1 mm | FEHLER 96 | Hohlraum 96 | doppelte Knoten 96 |
| derselbe in Kuhn-Tetraedern, 2 mm | FEHLER 96 | Hohlraum 96 | hängende Knoten 96 |
| hex8 0 (Ecke des Würfels) verdreht | FEHLER 6 | verdrehtes Element | verdrehtes Element |

Das verdrehte Eckelement benutzt die Würfelecke allein, wie im richtigen
Netz; ohne die Ausnahme für die Punkte der Randlinien hieße es „doppelte
Knoten“ (gezielt verfälscht gemessen). Den Tetraeder-Block fand an f2bf6c8
bis 1 mm nur die Suche nach doppelten Knoten, die dafür an allen Gruppen
läuft (vorher nur, wenn eine Gruppe sonst Riss oder Lücke hätte werden
können; ohne sie hieß er „hängende Knoten“, gezielt verfälscht gemessen;
heute heißt er auch ohne sie „doppelte Knoten“, siehe unten). Bei 2 mm
(1,6 % der Kante) liegen die Knoten weiter auseinander als
`ABNAHME_KNOTENNAEHE`, und jeden benutzen mindestens zwei Elemente; an
f2bf6c8 blieb das Gegenüber, der Text sagte „hängende Knoten“ (heute
„doppelte Knoten“, siehe unten). Im hex8-Block benutzt jede der acht
Blockecken nur ein Element; er heißt bei allen vier gemessenen Versätzen
„doppelte Knoten“. Alle Zeilen der ersten Tabelle behielten Befund und Ursache
(nachgemessen am 24.09.2026), ebenso verdrehte hex8 an der Seite und im
Inneren (Elemente 36 und 292), ein fehlender hex8 und ein fehlender
Kuhn-Tetraeder im Inneren (Hohlraum), die Lochplatte r 0,1
(`mesh_koerper_frei`, FEHLER 4 neben Lücken von zusammen 0,33 cm³). An den
164 Körpern, die test_diagnose (84), test_mesher3d (30) und test_sweep (50)
bauen, blieben alle Befunde gleich; die Ursache änderte sich nur an den 11
Körpern der Fälle dieser Tabelle, die test_diagnose jetzt prüft.

Die zweite Fassung (f2bf6c8) prüfte nur Versätze in Richtung
(0,6 | 0 | 0,8); deren y-Anteil 0 hält die Knoten für die Seiten quer zu y
in der Ebene (Gegenprüfung vom 24.09.2026, M1/M2). Zwei Grenzen blieben:
Jedes Gegenüber ohne losgelösten Knoten hieß „hängend“, und lagen die
Knoten weiter als `ABNAHME_KNOTENNAEHE` mal die längste Seitenkante von den
Seiten des anderen Ufers entfernt, fand sich kein Gegenüber, und der Nachbar
eines losgelösten Bereichs hieß „Hohlraum“. Seit der dritten Fassung
(1afa712) teilen hängende Knoten eine Ecke mit der Seite (siehe oben), und
eine geschlossene Gruppe, deren Seiten aus dem umschlossenen Raum
hinauszeigen, heißt „doppelt“. Ein Hohlraum, in dem eine solche Gruppe
liegt, hieß an 1afa712 ebenfalls „doppelt“; heute nur noch, wenn sie ihn
ausfüllt (Füllung, siehe oben und unten). Gemessen am 24.09.2026 im selben
Netz (Befund in beiden Ständen gleich; die rechte Spalte gilt am Stand
1afa712 und, nachgemessen am 24.09.2026, auch heute):

| Fall | Befund | Ursache f2bf6c8 | Ursache 1afa712 |
|---|---|---|---|
| innerer Block 2 × 2 × 2, Kuhn-Tetraeder, (1 \| 1 \| 1)/√3, 1 mm | FEHLER 96 | doppelte Knoten 96 | doppelte Knoten 96 |
| derselbe, 2 / 3 mm | FEHLER 96 | hängende Knoten 96 | doppelte Knoten 96 |
| derselbe, 4 / 5 / 10 mm | FEHLER 96 | Hohlraum 96 | doppelte Knoten 96 |
| derselbe, (0,6 \| 0 \| 0,8), 2 / 5 / 10 mm | FEHLER 96 | hängende Knoten 96 | doppelte Knoten 96 |
| derselbe, an einem Knoten (0,375 \| 0,375 \| 0,375) hängend, (1 \| 1 \| 1)/√3, 2 mm | FEHLER 96 | hängende Knoten 96 | hängende Knoten 96 |
| derselbe, an einem Knoten hängend, 5 mm | FEHLER 96 | Hohlraum 96 | doppelte Knoten 96 |
| derselbe Block in hex8, (1 \| 1 \| 1)/√3, 1 / 2 mm, (0,6 \| 0 \| 0,8), 2 / 5 / 10 mm | FEHLER 48 | doppelte Knoten 48 | doppelte Knoten 48 |
| derselbe in hex8, (1 \| 1 \| 1)/√3, 3 / 4 / 5 / 10 mm | FEHLER 48 | doppelte Knoten 24, Hohlraum 24 | doppelte Knoten 48 |
| derselbe in hex8, an einem Knoten hängend, (1 \| 1 \| 1)/√3, 2 / 5 mm | FEHLER 48 | doppelte Knoten 48 / doppelte Knoten 24, Hohlraum 24 | doppelte Knoten 48 |
| hex8 292 an allen acht Knoten, (1 \| 1 \| 1)/√3, 1 / 2 mm, (0,6 \| 0 \| 0,8), 2 / 5 / 10 mm | FEHLER 12 | doppelte Knoten 12 | doppelte Knoten 12 |
| derselbe, (1 \| 1 \| 1)/√3, 3 / 5 / 10 mm | FEHLER 12 | doppelte Knoten 6, Hohlraum 6 | doppelte Knoten 12 |
| hex8 292 an sieben Knoten, (1 \| 1 \| 1)/√3, 2 / 5 mm | FEHLER 12 | doppelte Knoten 12 / doppelte Knoten 6, Hohlraum 6 | doppelte Knoten 12 |
| hex8 292 fehlt | FEHLER 6 | Hohlraum 6 | Hohlraum 6 |
| Tetraeder-Block 2 × 2 × 2 fehlt (48 Tetraeder) | FEHLER Volumenbilanz, Seiten im Inneren 48 | Hohlraum 48 | Hohlraum 48 |
| Ufer 2 × 2 gegen 3 × 3 an x = 0,5 (Körper aus 2 × 2 × 2 Zellen, die vier Zellen x > 0,5 in 3 × 3 × 3), hex8 / Kuhn-Tetraeder | FEHLER 52 / 104 | hängende Knoten | hängende Knoten |
| 3 × 3 × 3 Zellen, die mittlere in 3 × 3 × 3 geteilt, die übrigen in 2 × 2 × 2, hex8 / Kuhn-Tetraeder | FEHLER 78 / 156 | hängende Knoten | hängende Knoten |
| Tetraeder 164 (drei Hüllknoten), hex8 27 (vier Hüllknoten), Eckzelle abgetrennt; 0,01 bis 5 mm, beide Richtungen | unverändert | doppelte Knoten | doppelte Knoten |

Hängt der Tetraeder-Block an einem Knoten, ist das der einzige Knoten, den
beide Ufer haben; bei 2 mm liegen Knoten des einen Ufers auf Seiten des
anderen, die ihn als Ecke haben, und es bleibt „hängend“. Die Ufer 2 × 2
gegen 3 × 3 teilen nur die Ecken ihrer Zellen; verlangte die Regel, dass
**alle** Ecken der Seite Knoten des anderen Ufers sind, hießen sie
„doppelt“ (gezielt verfälscht gemessen), die Regel verlangt darum nur eine.
Gezielt verfälscht gemessen auch die beiden anderen Teile: Ohne die
Ausrichtung heißt der Tetraeder-Block bei 5 und 10 mm, auch an einem Knoten
hängend bei 5 mm, an allen 96 Seiten „Hohlraum“. Ohne den Hohlraum mit
losgelöstem Bereich darin heißen die Seiten der Nachbarn „Hohlraum“: am
Tetraeder-Block 48 von 96, am hex8-Block bei 3 mm 24 von 48, an hex8 292
bei 3 mm (an sieben Knoten bei 5 mm) 6 von 12. An den Körpern, die
test_diagnose (84 gemeinsame), test_mesher3d (30), test_sweep (50),
test_netzfehler (7) und test_netzfeld (2) bauen, blieben alle Befunde und
alle Ursachen gleich; an 26 Körpern von test_diagnose änderte sich nur die
Beschreibung der doppelten Knoten. Laufzeit von `_abnahme_volumenbilanz` am
hex8-Schachbrett 10 × 10 × 10 (4500 hex8), je drei Läufe abwechselnd: 9,2
bis 10,7 s an f2bf6c8, 9,6 bis 9,9 s an 1afa712.

Die dritte Fassung (1afa712) hatte wieder Grenzen (zweite Gegenprüfung vom
24.09.2026). Ein Hohlraum, in dem ein losgelöster Bereich lag, hieß ganz
„doppelt“, ohne dass gefragt wurde, ob der Bereich ihn ausfüllt; fehlte ein
Element neben dem losgelösten, kam der Hohlraum im Text nicht mehr vor. In
hex8 bekam ein Hohlraum, in den ein Element hineinragt, die Ursache
„verdrehtes Element“ (eine Kante, die nach dem Entfernen nur noch dieses
Element trägt, galt als verdreht; Tetraeder fragt `_verdrehte_elemente`
aus diesem Grund gar nicht, bei Sechsflächnern fehlte die Unterscheidung)
oder „doppelte Knoten“ (seine Ecke benutzt nur es). Und war eine Zelle nur
in einer oder zwei Richtungen geteilt, teilen grobe und feine Seiten Kanten und liegen in einer
Gruppe; das Gegenüber wurde nur zwischen verschiedenen Gruppen gesucht.
Seither gelten die geteilte Kante (`_halbierte_kante`), die Diagonale bei
geschlossenen Gruppen und die Füllung (alle drei oben). Gemessen am
24.09.2026; die Hohlräume im 8 × 8 × 8-hex8-Netz über dem Würfel 1 × 1 × 1 m
(Kante 125 mm; „Kuhn“: nach dem Entfernen in Kuhn-Tetraeder zerlegt),
losgelöst heißt mit eigenen Knoten (eine Zelle an allen acht, ein Block auf
seiner Oberfläche), versetzt in Richtung (1 | 1 | 1)/√3; die geteilten
Zellen in 3 × 3 × 3 hex8 über dem Einheitswürfel (Volumen genau 1, det J überall positiv):

| Fall | Befund | Ursache 1afa712 | Ursache jetzt |
|---|---|---|---|
| Mittelzelle in 2 × 1 × 1 bzw. 1 × 1 × 2 hex8 geteilt | FEHLER 12 | verdrehtes Element 12 | hängende Knoten 12 |
| Mittelzelle 2 × 2 × 1 / 3 × 1 × 1 / 3 × 2 × 1 | FEHLER 22 / 16 / 28 | verdrehtes Element | hängende Knoten |
| Eckzelle 2 × 1 × 1 / 1 × 1 × 2 / 2 × 2 × 1 / 3 × 1 × 1 / 3 × 2 × 1 | FEHLER 6 / 6 / 11 / 8 / 14 | verdrehtes Element | hängende Knoten |
| Kuhn, Mittelzelle 2 × 2 × 1 | FEHLER 44 | Hohlraum 44 (f2bf6c8 ebenso) | hängende Knoten 44 |
| Kuhn, Mittelzelle 3 × 2 × 1 | FEHLER 56 | doppelte Knoten 56 (f2bf6c8 Hohlraum 56) | hängende Knoten 56 |
| Kuhn, die übrigen acht Teilungen | WARNUNG Riss 12 bis 32 | – | – (unverändert) |
| 292 fehlt, 293 losgelöst, 0 / 1 mm | FEHLER 16 | doppelte Knoten 16 (f2bf6c8 ebenso) | doppelte Knoten 6, Hohlraum 10 |
| dasselbe, 3 / 5 / 10 mm; 300 statt 293, 5 mm; 292 losgelöst und 293 fehlt, 0 bis 5 mm | FEHLER 16 | doppelte Knoten 16 | doppelte Knoten 6, Hohlraum 10 |
| 292 und 293 fehlen, 294 losgelöst, 5 mm; 292 losgelöst, 293 und 294 fehlen, 0 / 3 mm | FEHLER 20 | doppelte Knoten 20 | doppelte Knoten 6, Hohlraum 14 |
| hex8-Block 2 × 2 × 2 losgelöst, 0 / 5 mm, seine Zelle (3, 3, 3) fehlt | FEHLER 48 | doppelte Knoten 48 | doppelte Knoten 24, Hohlraum 24 |
| Block 2 × 2 × 2 im ganz in Kuhn-Tetraeder zerlegten Netz losgelöst, 0 / 5 mm, ein Tetraeder daneben fehlt | FEHLER 100 | doppelte Knoten 100 | doppelte Knoten 96, Hohlraum 4 |
| Block 3 × 3 × 3 fehlt bis auf die Mittelzelle, die frei schwebt (auch mit eigenen Knoten, 2 mm), hex8 / Kuhn | FEHLER Volumenbilanz 0,05078, Seiten 60 / 120 | doppelte Knoten 60 / 120 | doppelte Knoten 6, Hohlraum 54 / 12, 108 |
| hex8, L aus 3 Zellen fehlt | FEHLER Volumenbilanz 0,005859, Seiten 14 | verdrehtes Element 14 | Hohlraum 14 |
| hex8, Kreuz aus 7 Zellen fehlt | FEHLER Volumenbilanz 0,01367, Seiten 30 | verdrehtes Element 30 | Hohlraum 30 |
| hex8, Block 2 × 2 × 2 ohne eine Ecke fehlt | FEHLER Volumenbilanz 0,01367, Seiten 24 | doppelte Knoten 24 | Hohlraum 24 |
| hex8, L aus 5 Zellen in der Lage z = 1 fehlt | FEHLER Volumenbilanz 0,009766, Seiten 22 | verdrehtes Element 22 | Hohlraum 22 |
| hex8, dasselbe L, daneben (3, 3, 1) losgelöst, 0 mm | FEHLER Volumenbilanz 0,009766, Seiten 34 | verdrehtes Element 22, doppelte Knoten 12 | doppelte Knoten 12, Hohlraum 22 |
| hex8, Lagen 2 und 3 des Blocks 3 × 3 × 3 fehlen bis auf die Mittelzelle, die an der Lage 4 hängt | FEHLER Volumenbilanz 0,0332, Seiten 46 | doppelte Knoten 46 | Hohlraum 46 |
| hex8, L aus 9 Zellen in der Lage z = 1 fehlt | FEHLER Volumenbilanz 0,01758, Seiten 38 | verdrehtes Element 38 | Hohlraum 38 |
| hex8, dasselbe L, die 3 × 3 × 1 Zellen in seiner Ecke je losgelöst, 0 / 5 mm | FEHLER Volumenbilanz 0,01758, Seiten 122 | verdrehtes Element 38, doppelte Knoten 84 | doppelte Knoten 84, Hohlraum 38 |

Unverändert blieben: dieselben Hohlräume in Kuhn-Tetraedern („Hohlraum“),
in hex8 eine Zelle, zwei in Reihe, zwei an einer Kante und der Block
2 × 2 × 2 („Hohlraum“); eine Zelle fehlt, eine andere liegt losgelöst weit
weg (292 und (6, 6, 6), (2, 2, 2) und (5, 5, 6); 0 und 5 mm; „doppelte
Knoten 12, Hohlraum 6“, 292 und (6, 6, 6) in Kuhn-Tetraedern 24 und 12); das
L aus 5 Zellen in Kuhn-Tetraedern mit (3, 3, 1) losgelöst in seinem Kasten
(„doppelte Knoten 24, Hohlraum 44“), ebenso das L aus 9 Zellen mit den
3 × 3 × 1 Zellen („doppelte Knoten 168, Hohlraum 76“); der hex8-Block
4 × 4 × 4 losgelöst, seine inneren 2 × 2 × 2 Zellen fehlen; der innere Block, an einer Seite,
einer Kante oder einem Knoten haftend (hex8 und Kuhn, 1 bis 10 mm, beide
Richtungen, 48 Fälle); die T-Stöße, deren Ufer nur Ecken teilen; alle Fälle
der Tabelle davor und die Fälle am Rand (Tetraeder 164, hex8 27, Eckzelle).
Die Füllung zählt den Rest V_rest gegen den Median der Elementvolumina am
Hohlraum. Gemessen: losgelöste Bereiche, die ihren Hohlraum ausfüllen (hex8
292 an allen acht oder an sieben Knoten, die beiden Blöcke, auch an einem
Knoten hängend; 1 bis 10 mm, auch in Richtung (0,6 | 0 | 0,8)), −0,277 bis
0,000; der Spalt am losgelösten Knoten 1 des Kuhn-Tetraeders 554 (B042,
6 × 6 × 6 über 0,75 m, 1 bis 30 mm in Richtung (0,6 | 0 | 0,8)) 0,006 bis
0,212; ein Element fehlt neben oder in einem losgelösten Bereich 0,965 bis
156; ein Element ragt in einen Hohlraum, nichts ist losgelöst (Block ohne
Ecke, Lagen 2 und 3) 7,0 und 17,0. Die Grenze 0,5 liegt dazwischen, Faktor
2,4 über dem Spalt bei 30 mm und 1,9 unter 0,965. Gezielt verfälscht
gemessen, jeweils gegen die sechs Prüfungen dieses Teils in test_diagnose
(83 Einzelprüfungen): ohne die geteilte Kante 13 Fehlschläge, ohne die
Diagonale 5, die Füllung ohne Volumen (jeder Hohlraum mit einem Bereich
darin „doppelt“) 15, die „doppelten“ Hohlräume nicht nachgeprüft 6, Grenze
0,1 statt 0,5 1 (der Spalt bei 30 mm), Grenze 1,0 4, jeder Bereich zählt
als darin 4, nur der Kasten statt der Windungszahl 1 (das L aus 9 Zellen
heißt dann „doppelte Knoten 122“), die Kette auf der Kante nur einen Knoten
lang 2 (Teilung 3 × 1 × 1), das flache Dreieck nicht ausgenommen 1. An den
Körpern, die test_diagnose (140 gemeinsame), test_mesher3d (30), test_sweep
(50), test_netzfehler (7) und test_netzfeld (2) bauen, blieben alle Befunde
gleich; die Ursache änderte sich nur an den 32 Körpern der Fälle dieser
Nachbesserung, die test_diagnose jetzt prüft. Laufzeit von
`_abnahme_volumenbilanz` am hex8-Schachbrett 10 × 10 × 10, je drei Läufe
abwechselnd: 5,92 bis 6,00 s an 1afa712, 5,95 bis 6,00 s jetzt.

Die vierte Fassung (447a5f8) behandelte so nur die geschlossenen Gruppen
(dritte Gegenprüfung vom 24.09.2026). An offenen Gruppen machte ein Knoten
in nur einem Element sie „doppelt“, eine Kante, die kein anderes Element
hat, „verdreht“, und „Netzrand verfehlt die Randfläche“ war der Rest. M1:
Eine Mulde an der Seitenfläche eines hex8-Netzes mit einspringender Kante
hieß „doppelte Knoten“ – den Knoten an der einspringenden Kante benutzt nur
der Würfel dahinter. M2: Ein Körper, den eigene Knoten in Kuhn-Tetraedern
ganz durchtrennen, hieß ab 3 mm Versatz „Netzrand verfehlt die Randfläche“
mit dem Rat zum Sweep. Seither gelten für offene Gruppen der Knoten
daneben, die Diagonale und die Kopie (oben); was dann offen bleibt, heißt
„keine sicher bestimmte Ursache“, und der Text nennt die möglichen (Mulde,
anders verdrehtes Element, weiter versetzt losgelöstes Element). Den
Anteil 0,5 trennen (kleinster Abstand eines Knotens der Gruppe zu einem
anderen Knoten durch die kürzere der kürzesten Kanten, gemessen am
24.09.2026 an 447a5f8): losgelöst an der Oberfläche mit einem Knoten in nur
einem Element (hex8 27 an vier Hüllknoten, Eckzelle abgetrennt, Tetraeder
164; 0,01 bis 30 mm) 8 · 10⁻⁵ bis 0,274; der durchtrennte Körper (1 bis
30 mm) 0,008 bis 0,24; die Mulden 1,0; offene Gruppen richtiger Netze des
eigenen Vernetzers 0,27 (Stufe) bis 1,0, dort ohne Knoten in nur einem
Element und ohne Kopie einer Seite. Die Nähe allein reicht darum nicht;
entscheidend ist der Knoten in nur einem Element bzw. die Kopie. Gemessen im
8 × 8 × 8-Netz des Würfels 1 × 1 × 1 m (Kante 125 mm):

| Fall | Befund (unverändert) | Ursache 447a5f8 | Ursache jetzt |
|---|---|---|---|
| hex8, L aus 3 Zellen an z = 0 fehlt | FEHLER Volumenbilanz 0,005859, Seiten 11 | doppelte Knoten 11 | keine sicher bestimmte Ursache 11 |
| hex8, T aus 4 Zellen / L zwei Lagen tief / L an der Kante x = 0 | FEHLER Volumenbilanz, Seiten 14 / 19 / 9 | doppelte Knoten | keine sicher bestimmte Ursache |
| hex8, L aus 3 Zellen an z = 0 und darunter (3, 3, 1) | FEHLER Volumenbilanz 0,0078, Seiten 15 | doppelte Knoten 15 | keine sicher bestimmte Ursache 15 |
| dieselben Mulden in Kuhn-Tetraedern | Lücke im Netzrand | – | – |
| Kuhn, Hälfte x > 0,5 mit eigenen Knoten, (0,6 \| 0 \| 0,8), 3 / 5 / 10 / 30 mm | FEHLER 256 / 264 / 272 / 272 | Netzrand verfehlt die Randfläche, Rat zum Sweep | doppelte Knoten |
| derselbe, (1 \| 1 \| 1)/√3, 5 / 10 / 30 mm | FEHLER 272 / 288 / 288 | Netzrand verfehlt die Randfläche, Rat zum Sweep | doppelte Knoten |
| Kuhn, von unten bis z = 0,5 eingerissen, beide Richtungen, 10 / 30 mm | FEHLER 144 bzw. 152 | Netzrand verfehlt die Randfläche, Rat zum Sweep | doppelte Knoten |
| derselbe Schnitt in hex8, 1 bis 30 mm; in Kuhn bis 2 mm, in Richtung (1 \| 1 \| 1)/√3 bis 3 mm | FEHLER | doppelte Knoten | doppelte Knoten |
| derselbe Schnitt, rechts die Kuhn-Zerlegung in y gespiegelt (Schnittfläche beiderseits verschieden geteilt), 3 bis 30 mm | FEHLER 256 | Netzrand verfehlt die Randfläche, Rat zum Sweep | Netzrand verfehlt die Randfläche; der Text nennt doppelte Knoten an verschieden geteilter Schnittfläche als nicht ausgeschlossen (die Kopie einer Seite gibt es dort nicht) |
| hex8 verdreht, Deckel um eine Ecke vor oder zurück (8 × 8 × 8 und abgestuft 20:1 mit windschiefem Deckel, jede siebte Zelle, an der Seitenfläche und im Inneren) | FEHLER 6 bis 8 | verdrehtes Element | verdrehtes Element |
| dieselben Zellen, Deckel um zwei Ecken versetzt, offene Gruppe an der Seitenfläche (32 bzw. 39 Fälle) | FEHLER 6 / 7 | verdrehtes Element | keine sicher bestimmte Ursache |
| dieselben Zellen, Deckel um zwei Ecken versetzt, geschlossene Gruppe (42 bzw. 104 Fälle) | FEHLER 7 / 8 | Hohlraum | Hohlraum (unverändert) |
| hex8 27 an vier Hüllknoten losgelöst, Eckzelle abgetrennt; 10 / 30 mm | FEHLER 9 / 8 | doppelte Knoten | doppelte Knoten |
| U-Prisma h 0,3; Platte mit Bohrung r 6 mm; Lochplatte r 0,1; Stufe d 0,45 mm, t 0,02 m | wie oben | Netzrand verfehlt die Randfläche | Netzrand verfehlt die Randfläche |

Beim Deckel um zwei Ecken laufen die Seitenkanten durch die Zellmitte (det J
dort 0, gemessen), nicht über die Diagonale einer Nachbarseite; die einsame
Kante allein unterscheidet ihn nicht von der Mulde. Bildet er eine
geschlossene Gruppe, heißt er an 447a5f8 und jetzt „Hohlraum“ – das ist
falsch und bleibt es (nicht Teil dieser Nachbesserung). Gezielt verfälscht
gemessen, jeweils gegen die drei neuen Prüfungen (38 Einzelprüfungen): ein
Knoten in nur einem Element genügt ohne Knoten daneben 4 Fehlschläge (die
Mulden), verdreht ohne die Diagonale 4, ohne die Kopie 9 (der durchtrennte
Körper), die Nähe allein statt der Kopie 1 (die Stufe heißt dann „doppelte
Knoten“), Anteil 0,25 statt 0,5 1 (hex8 27 bei 30 mm), Anteil 1,0 4 (die
Mulden); die relative Knotennähe auf fest 10⁻⁶ m 6 (der Riss von unten,
siehe Bedingung 4 des Risses). An den Körpern, die test_diagnose (179),
test_mesher3d (30), test_sweep (50), test_fugen (115), test_netzfehler (7)
und test_netzfeld (2) bauen, blieben alle Befunde gleich (zweimal gemessen,
gegen 447a5f8); die Ursache änderte sich nur an den 13 Körpern der beiden
neuen Prüfungen zu M1 und M2, und nur der Wortlaut „Netzrand verfehlt die
Randfläche“ an U-Prisma und Stufe. Laufzeit von `_abnahme_volumenbilanz` am
hex8-Schachbrett 10 × 10 × 10: Die Diagonale wird nur für die Gruppen
gefragt, die bis dahin keine Ursache haben; über alle gefragt, waren es in
einer Messung 6,79 bis 6,90 s gegen 5,96 bis 6,00 s an 447a5f8 (je drei
Läufe abwechselnd). So ist kein Unterschied zu sehen: vier Läufe
abwechselnd (Gegenprüfung vom 24.09.2026) 5,88 bis 5,97 s an 447a5f8 gegen
5,87 bis 6,01 s jetzt.

Am U-Prisma liegen Netzknoten wie (0,404 | 0,23 | 0,083) im Körper neben der
einspringenden Kante x = 0,4, y = 0,3; die Seiten von dort zu den Wänden der
Aussparung laufen durch den Körper, andere stehen in die Aussparung
(Netzvolumen 0,505338 gegen 0,505 m³). Für diese Ursache nennt der Text die
Abhilfe, die gemessen wirkt: „Sechsflächner sweepen“ – U-Prisma 32 hex8 und
16 pent6, Platte mit Bohrung 908 hex8 und 24 pent6, beide ohne Befund. Für
die anderen Ursachen steht sie nicht da.

Die Lücken eines Körpers sind eine WARNUNG mit Ort (Mitte der größten
Schleife), Volumen und Anteil am Körper. Ein FEHLER werden sie, wenn sie
zusammen mehr als `ABNAHME_VOLUMENBILANZ` = 0,5 % des Körpers ausmachen.
Gemessen an den Netzen des eigenen Vernetzers mit Lücke (L-, T- und
U-Prismen, Standardweg): Lücken von 0,006 bis 0,113 % des Körpers. Der
Text nennt die Abhilfen, die an diesen fünf Prismen gemessen halfen (Sweep,
gmsh, Netgen: 5 von 5; andere
Ziellänge 3 bis 4 von 5; MMG3D 0 von 5), beim Sweep seit 23.09.2026 mit dem
Hinweis, dass er ab Werk aus ist, weil er am Drehlager entartete Keile
erzeugte, und dass nach dem Einschalten die Abnahme zu lesen ist
(Nebenbefund B049: die Abhilfe ist nur an den Prismen gemessen, am
Drehlager nicht). gmsh und Netgen ergeben mit
derselben Netzweite (hs-Weg) nur 22 bis 37 % der Elemente des eigenen
Vernetzers (L-Prisma h 0,25: 821 gegen 203 und 187 tet4); so war die
Abhilfe zuerst gemessen. Nachgemessen am 23.09.2026 mit der Netzweite, die
der Elementzahl des eigenen Vernetzers am nächsten kommt (0,6- bis 0,7-fach,
Elementzahl 0,87- bis 1,05-fach; L h 0,25 / L h 0,1 / T h 0,2 / T h 0,1 /
U h 0,1: gmsh 843 / 11 025 / 698 / 6078 / 7921, Netgen 713 / 10 566 / 628 /
5548 / 8106 gegen 821 / 10 729 / 663 / 5997 / 8005): alle ohne Befund (die Elementzahlen des eigenen Vernetzers sind die vor
seiner Änderung vom 23.09.2026; die Vergleiche mit dem L-Prisma h 0,25
laufen am festgehaltenen Netz von damals). Der
Text sagt das so. Und er sagt, dass neu vernetzen mit denselben
Einstellungen dasselbe Netz ergibt: Der Vernetzer rechnet mit fester Saat,
und gemessen wurden dieselbe Elementzahl und derselbe Befund. Das gilt nur
für Netze, die unverändert vom eigenen Vernetzer stammen; der Text rät darum
wie bei „Seiten im Inneren" und beim Riss, ein importiertes oder von Hand
geändertes Netz neu zu vernetzen. Gemessen (zweite Gegenprüfung, Mangel 4):
L-Prisma, h = 0,12, 6173 tet4 ohne Befund; ein Tetraeder mit einer Seite im
Deckel mit `Model.elemente_loeschen` entfernt (so löscht auch „Elemente
löschen" in der Oberfläche) ergibt eine Lücke von 115 cm³, neu vernetzt mit
denselben Einstellungen über `mesher.modell_vernetzen` sind es wieder 6173 tet4
ohne Befund. Dieser Weg entfernt die Knoten des alten Netzes
(`Model.netzknoten_loeschen`); „Netz → Vernetzen" in der Oberfläche
(`gui.main._vernetzen`) löschte bis zum 23.09.2026 nur die Elemente. So
nachgestellt, ohne Qt: 6173 tet4, aber 1229 Knoten ohne Element, FEHLER.
Seither ruft auch `_vernetzen` nach dem Löschen der alten Netze
`Model.netzknoten_loeschen` - mit den Knoten der gelöschten Elemente als
Kandidaten, damit ein gesetzter Knoten ohne Anschluss stehen bleibt: zweites
Netz 1241 Knoten wie das erste, ohne „Knoten ohne Element" (Befund B062,
ebenso ohne Qt nachgestellt). Knoten mit Knotenlager
schützt `netzknoten_loeschen` auf beiden Wegen; liegen sie neben dem neuen Netz, koppelt der
Vernetzer sie starr daran. Am abgestuften hex8-Netz 20:1 (121 gelagerte
Bodenknoten) neu vernetzt: 117 Knoten ohne Element, alle in 306 starren
Kopplungen, und das Modell trägt (Fz = −100 kN und Fx = 100 kN an einer
Deckelecke, Summe der Lagerkräfte in z
100 000,0 N). Die Abnahme meldete sie bis zum 23.09.2026 als FEHLER „Knoten
ohne Element 117“ (Nebenbefund B099). Seither zählt `_angeschlossene_knoten`
einen Knoten ohne Element als angeschlossen, wenn er in allen drei
Verschiebungsrichtungen am Netz gehalten ist. Je offenem Knoten wird der
Raum der gehaltenen Richtungen gesammelt, bis sich nichts mehr ändert
(Elementknoten: alle drei):

- Kopplung: ihre wirksamen Richtungen (`Kopplung.paare`), geschnitten mit
  dem, was am Partner gehalten ist; so auch über eine Kette.
- RBE2: die Glieder bewegen sich als starrer Körper, u_s = u_m + θ_m × r_s.
  Die gehaltenen Richtungen der Glieder legen einen Teil dieser sechs
  Freiheiten fest, dazu die Verdrehungen, die Elemente und Drehlager am
  Master halten (`_drehsteife_knoten`, unter der Voraussetzung, dass jeder
  Elementknoten in x, y, z gehalten ist): am Schalenknoten alle drei; ein
  starres Knotenlager um die Achse, um die es sperrt; am Stabende die
  Biegung um die lokalen Achsen y und z, soweit an diesem Ende kein
  Momentengelenk sitzt – Gelenk 3 + 6 j + k gibt am Ende j die Drehung um
  die lokale Achse k frei, Achsen aus `beam3d.local_axes` samt roll. Die
  Torsion (lokal x) hält ein Stab nicht allein: Ohne Gelenk 3 und 9
  koppelt er die Drehung beider Enden um seine Achse, mit einem davon gar
  nicht (nach der Kondensation GJ/L − GJ/L = 0). Gehalten ist sie an einem
  Ende erst, wenn sie am anderen gehalten ist – von einem Drehlager, einer
  Schale, der Biegung eines weiteren Stabs oder so weiter über eine Kette;
  gesammelt wird, bis sich nichts mehr ändert. Gehalten ist an jedem Glied,
  was die festgelegten Freiheiten bestimmen.
- RBE3: nur der Master, nur wenn alle Slaves mit Gewicht gehalten sind,
  und nur in den Richtungen, in denen sie ihn festlegen
  (`_rbe3_master_raum`). Mit gehaltenen Slaves bleibt von den sechs
  Gleichungen des RBE3 (`verbindung.starrkoerper_matrix`, dieselben wie
  beim Rechnen) G_m · [u_m, θ_m] = 0 mit den sechs Spalten des Masters;
  gehalten ist das Komplement der Verschiebungsanteile des Nullraums von
  G_m. Drei Slaves, die nicht auf einer Linie liegen, machen G_m regulär.
  Ein einziger Slave neben dem Master, zwei Slaves und Slaves auf einer
  Linie legen die Drehung um ihre Linie nicht fest; steht der Master neben
  der Linie, bewegt ihn diese Drehung quer dazu, steht er auf ihr, nicht.
  Der Master ist das gewichtete Mittel der Slaves und versteift sie nicht.
- Spaltelemente zählen nicht: sie halten nur in ihrer Richtung und nur
  auf Druck. Ausgenommen ist der Anschlag, ein Knoten, den ein Knotenlager
  in x, y und z starr hält und der über ein Spaltelement an einem
  gehaltenen Knoten hängt (`_starr_gelagert`; so im Beispiel „Kontakt:
  abhebendes Lager“ und in `test_gap_element`): eine Last auf ihm geht in
  sein Lager, und das Lager wirkt, wie das Spaltelement es vorgibt. Ein
  gelagerter Knoten, der nur über eine Kopplung in einem Teil der
  Richtungen hängt, bleibt dagegen lose – ob sein Lager das Tragwerk nur
  in diesen Richtungen halten soll, sieht die Abnahme nicht
  (`fugen.stabenden_koppeln` koppelt Lagerknoten in allen dreien).

Bis zur Gegenprüfung vom 24.09.2026 (Mängel 1 und 4 zu B099) zählte jede
Verbindung, gleich in welcher Richtung (Zusammenhangskomponenten über
Kopplungen, starre Körper und Spaltelemente). Gemessen am 24.09.2026 an
einem Würfel aus 2 × 2 × 2 hex8, unten gelagert, 1000 N in x, y und z am
Knoten ohne Element (`tests.test_diagnose._knoten_am_wuerfel`):

| Anschluss | Rechnung | Abnahme bis dahin | jetzt |
|---|---|---|---|
| Kopplung nur in z an einem Deckelknoten | z trägt; x und y bleiben als Reaktion am Knoten selbst | kein Befund | FEHLER |
| RBE3, loser Master, Slaves: neun Deckelknoten und ein loser Knoten | jede Last am losen Slave: Gleichungssystem singulär | kein Befund | FEHLER, beide |
| RBE2 am Deckelknoten, ein Slave 0,5 m daneben in x | x trägt; y und z: singulär | kein Befund | FEHLER |
| Spaltelement allein, 0,2 m über einem Deckelknoten | x und y bleiben am Knoten; Zug: Kontakt bricht ab | kein Befund | FEHLER |
| Kopplung in x und y, z über einen Zwischenknoten, der nur in z hängt | am Knoten trägt alles; am Zwischenknoten nur z | kein Befund | FEHLER für den Zwischenknoten |
| Kopplung in x, y und z an einen Zwischenknoten, der nur in z hängt | z trägt; x und y: singulär | kein Befund | FEHLER, beide |
| RBE3 mit losem Master an den neun Deckelknoten | trägt | kein Befund | kein Befund |
| RBE2, loser Master und loser Slave neben den Deckelknoten | trägt | kein Befund | kein Befund |
| Kopplungen in x+y und z, dazu x−y an einem zweiten Deckelknoten | trägt | kein Befund | kein Befund |
| Anschlag: Knoten 0,2 m über einem Deckelknoten in x, y, z gelagert, Spaltelement | trägt (die Last geht in sein Lager) | kein Befund | kein Befund |
| ebenso, Knoten nur in z gelagert | z geht in sein Lager; x und y bleiben am Knoten, in Richtungen ohne Lager | kein Befund | FEHLER |
| loser Knoten 0,2 m über dem Anschlag, Spaltelement dorthin | x und y bleiben am Knoten; Zug: Kontakt bricht ab; Druck trägt | kein Befund | FEHLER |
| RBE3 mit dem Master an einem Deckelknoten, ein loser Slave | trägt | kein Befund | FEHLER |

Die letzte Zeile ist Absicht: Die sechs Gleichungen des RBE3 legen einen
einzelnen losen Slave neben einem gehaltenen Master rechnerisch fest (Lasten
in +x, +y, +z, −z und −x gingen ganz in die Lager, am Knoten selbst blieb
0), das RBE3 soll ihn aber nicht halten: Es verteilt eine Last am Master
auf die Slaves, ohne sie zu versteifen (`model.StarrKoerper`). Der Text des
Befunds nennt solche Knoten darum eigens („Davon als Slave eines RBE3 …
auch wo die Rechnung ihn über einen gehaltenen Master festlegt“). Bis zur
2. Gegenprüfung vom 24.09.2026 (Mangel 2) sagte er für jeden genannten
Knoten, er sei „nicht in allen drei Richtungen am Netz gehalten – eine Last
darauf ginge ganz oder zum Teil verloren“; jetzt sagt er, dass die Abnahme
keinen Halt in allen drei Richtungen findet, und was folgt, wo der Halt
wirklich fehlt.

Die Fassung d7553e4 ließ den Master eines RBE3 gelten, sobald alle Slaves
gehalten waren, auch wo sie ihn nicht festlegen (2. Gegenprüfung vom
24.09.2026, Mangel 1). Gemessen am 24.09.2026 am selben Würfel, loser
Master, Slaves aus der Deckelreihe y = 1 (x = 0 / 0,5 / 1), 1000 N am
Master in x, y und z:

| Slaves, Master | Rechnung | ec6448c | d7553e4 | jetzt |
|---|---|---|---|---|
| ein Slave (x = 0,5), Master 0,3 m darüber | z trägt; x und y: singulär | FEHLER | kein Befund | FEHLER |
| zwei Slaves (x = 0 und 1), Master 0,3 m über der Mitte | x und z tragen; y: singulär | FEHLER | kein Befund | FEHLER |
| drei Slaves auf der Reihe, Master 0,3 m darüber | x und z tragen; y: singulär | FEHLER | kein Befund | FEHLER |
| drei Slaves auf der Reihe, Master auf ihr (x = 0,25) | trägt | FEHLER | kein Befund | kein Befund |
| ein Slave, Master auf dem Slave | trägt | FEHLER | kein Befund | kein Befund |
| drei Slaves nicht auf einer Linie, Master 0,3 m darüber | trägt | FEHLER | kein Befund | kein Befund |
| ein Slave, Master 0,3 m darüber, dazu in x und y an einen Deckelknoten gekoppelt | trägt | FEHLER | kein Befund | kein Befund |

Die Zufallsprobe der 2. Gegenprüfung, hier nachgerechnet (400 Modelle aus
dem Würfel mit 1 bis 4 Knoten ohne Element, Kopplungen in Achsen- und schrägen Richtungen, RBE2 und
RBE3, auch mit Slaves auf einer Deckelreihe; Wahrheit aus dem Nullraum der
Zeilen von Elementsteifigkeit, Kopplungsrichtungen und
`starrkoerper_matrix`) ergab bei d7553e4 42 bzw. 47 Knoten ohne Befund, die
nicht in allen drei Richtungen gehalten sind (Saat 7: 981 Knoten, Saat 11:
1000 Knoten), jetzt 0 bei beiden. Die andere Seite: gemeldet, obwohl in
allen drei Richtungen gehalten, bei d7553e4 24 bzw. 35, jetzt 31 bzw. 40
Knoten, davon 13 bzw. 14 keine RBE3-Slaves. Einzeln nachgestellt sind
zwei davon; dort legen erst zwei starre Körper zusammen den Knoten fest,
über eine gemeinsame Verdrehung: ein RBE2 unter Elementknoten hält deren
Verdrehung, die ein zweites RBE2 an den Knoten weitergibt, bzw. ein RBE3
und ein RBE2 am selben Master lassen je eine andere Drehung frei. Ohne den
einen der beiden ist der Knoten in z nicht gehalten. Die Abnahme vereinigt
die gehaltenen Richtungen je Verbindung und verfolgt Verdrehungen nur an
Schalen- und Stabknoten und an Drehlagern; ein FEHLER dort ist eine
unnötige Rückfrage, kein stiller Verlust.

Dazu RBE2 mit einem Slave 0,5 m neben dem Master: am Ende eines am
Anfang eingespannten Stabs (IPE 200) und an einem Schalenknoten tragen die
Lasten in x, y und z bei jedem Versatz in x, y oder z, an einem Stabende
mit den Gelenken 9, 10, 11 nur die Last in Richtung des Versatzes. Mit
einem Teil der Gelenke am Master-Ende hält das Stabende dort die übrigen
Drehungen, der Slave bleibt nur in Richtung Gelenkachse × Versatz frei –
aber nur, solange die Torsion am anderen Ende gehalten ist (unten). Bis
zur 2. Gegenprüfung (Mangel 2) galt ein Stabende mit irgendeinem
Momentengelenk als gar nicht drehsteif. Gemessen am 24.09.2026 (Stab in x,
eingespannt am Anfang, RBE2 am Ende; getragen heißt: alle drei Lasten
gehen in die Lager, ohne Hilfsfesselung des Lösers):

| Gelenke am Ende | Slave in x | Slave in y | Slave in z |
|---|---|---|---|
| 11 (lokal z) | y bricht ab – FEHLER | x bricht ab – FEHLER | getragen – kein Befund (d7553e4: FEHLER) |
| 10 (lokal y) | z bricht ab – FEHLER | getragen – kein Befund (d7553e4: FEHLER) | x bricht ab – FEHLER |
| 9 (Torsion) | getragen – kein Befund (d7553e4: FEHLER) | z bricht ab – FEHLER | y bricht ab – FEHLER |
| 10 und 11 | y und z brechen ab – FEHLER | x bricht ab – FEHLER | x bricht ab – FEHLER |

Am schrägen Stab (Richtung (1, 1, 1)) und am um 30° gerollten Stab mit
Gelenk 11 brach bei jedem Versatz in x, y oder z mindestens eine Last ab
(FEHLER), mit dem Slave in Richtung der lokalen z-Achse trugen alle drei
(kein Befund). Nicht Sache dieser Prüfung ist ein Stab, der selbst
verschieblich ist: Mit Gelenk 5 am eingespannten Anfang bricht schon eine
Last in y am Stabende ab, ohne RBE2; die Abnahme meldet dort nichts.

Die Torsion eines Stabs hängt an beiden Enden (3. Gegenprüfung vom
24.09.2026, Mangel 1). Bis dahin galt sie am Master-Ende schon als
gehalten, wenn dort kein Torsionsgelenk saß; mit einem Torsionsgelenk am
anderen Ende oder einem anderen Ende, das nur in x, y, z gelagert ist,
dreht sich aber der ganze Stab frei um seine Achse. Gemessen am 24.09.2026
(RBE2 am Ende, Slave 0,5 m daneben, 1000 N am Slave; wo nichts anderes
steht, ist der Anfang (0|0|0) eingespannt und der Stab 2 m lang in x):

| Stab | Slave in x | Slave in y | Slave in z |
|---|---|---|---|
| Gelenk 3 am Anfang | getragen – kein Befund | z bricht ab – FEHLER (8c4fb14: kein Befund) | y bricht ab – FEHLER (8c4fb14: kein Befund) |
| Gelenke 3 und 11 | y bricht ab – FEHLER | x und z brechen ab – FEHLER | y bricht ab – FEHLER (8c4fb14: kein Befund) |
| Gelenke 3 und 9 | getragen – kein Befund | z bricht ab – FEHLER | y bricht ab – FEHLER |
| beide Enden nur in x, y, z gelagert | getragen – kein Befund | z: die Kraft geht in die Lager, das Moment 500 Nm um die Stabachse nimmt die Hilfsfesselung – FEHLER (8c4fb14: kein Befund) | y: ebenso, −500 Nm – FEHLER (8c4fb14: kein Befund) |
| Gelenk 5 am Anfang, Ende in x, y, z gelagert | getragen – kein Befund | getragen – kein Befund | getragen – kein Befund |
| zwei Stäbe hintereinander bis (4\|0\|0), RBE2 am freien Ende | getragen – kein Befund | getragen – kein Befund | getragen – kein Befund |
| ebenso, Gelenk 3 am Anfang des ersten | getragen – kein Befund | z bricht ab – FEHLER (8c4fb14: kein Befund) | y bricht ab – FEHLER (8c4fb14: kein Befund) |
| Rahmenecke: Gelenk 3 am Anfang, zweiter Stab von (2\|0\|0) nach (2\|2\|0), dort in x, y, z gelagert | getragen – kein Befund | getragen – kein Befund | getragen – kein Befund |
| ebenso, Gelenk 4 am Anfang des zweiten Stabs | getragen – kein Befund | z bricht ab – FEHLER (8c4fb14: kein Befund) | y bricht ab – FEHLER (8c4fb14: kein Befund) |

Die Biegung hält ein Stab dagegen selbst, sobald beide Enden in x, y, z
gehalten sind: Mit festgehaltenen Verschiebungen bleibt von seiner
Biegesteifigkeit um eine Achse (`beam3d.k_local_beam`) für die beiden
Enddrehungen die Matrix EI/(L (1 + Φ)) · [[4 + Φ, 2 − Φ], [2 − Φ, 4 + Φ]]
mit dem Schubparameter Φ ≥ 0. Sie ist regulär, und mit einem Gelenk um
dieselbe Achse am anderen Ende bleibt am gehaltenen Ende eine positive
Steifigkeit (ohne Schub 3 EI/L); gemessen ist das an der Zeile „Gelenk 5“.
Die Torsion zählt `_drehsteife_knoten` darum nur an
einem Stab ohne Gelenk 3 und 9 und nur, wenn sie am anderen Ende gehalten
ist; in der Rahmenecke hält sie der zweite Stab über seine Biegung um die
globale x-Achse, mit Gelenk 4 dort nicht mehr. Die „Hilfsfesselung“ ist
die des Lösers (`solver.hilfsfesselung`): Sie hält eine Bewegung fest, die
das Modell nicht hält, und nimmt den Teil der Last auf, der an ihr Arbeit
leistet – die Lagerkräfte allein sehen dann vollständig aus. Die Prüfung
zählt einen solchen Lauf darum als nicht getragen.

Dass eine Schale die Torsion eines an ihr hängenden Stabs hält, zählt
`_drehsteife_knoten` wie am Schalenknoten selbst, sauber nachgemessen ist
es nicht. An einer Platte 1 × 1 m, t = 20 mm (`grid_plate` 2 × 2, Rand
x = 0 eingespannt) mit einem IPE 200 daran, 2 m lang in der Ebene oder
senkrecht dazu, RBE2 am Stabende, Slave 0,5 m daneben, brach die Rechnung
ohne Gelenk bei 4 von 18 Lasten ab, als „numerisch singulär“. Bei zwei
davon nachgesehen: Residuum 1,7 · 10⁻⁶ bzw. 2,0 · 10⁻⁶ bei der Schranke
10⁻⁶; der Löser nannte einmal eine Bewegung des Stabs mit 5 % seiner
mittleren Steifigkeit, einmal keine Ursache. Das traf auch eine Last, die
nur die Biegung des Stabs beansprucht; ohne RBE2 trug das Stabende alle drei Lasten (gemessen
24.09.2026). Mit Gelenk 3 an der Platte meldete die Abnahme die Slaves,
deren Lasten quer brachen ab, die übrigen trugen.

Die Zufallsprobe der 3. Gegenprüfung, hier nachgerechnet am 24.09.2026
(je 1500 Modelle aus ein oder zwei Stäben IPE 200 in beliebiger Richtung
und Rolllage mit zufälligen Momentengelenken, Anfang eingespannt, das Ende
teils in x, y, z gelagert, dazu ein bis drei Knoten ohne Element an RBE2,
RBE3 und Kopplungen; übersprungen, wo die Stabknoten schon ohne diese
Verbindungen eine Last nicht tragen; Wahrheit aus der Rechnung und aus dem
Nullraum wie oben), fand bei 8c4fb14 6 bzw. 5 Knoten ohne Befund, die
nicht in allen drei Richtungen gehalten sind (Saat 3: 1596 Knoten, Saat 5:
1640 Knoten), jetzt 0 bei beiden.

Die Prüfung `test_abnahme_knoten_in_drei_richtungen` rechnet die Fälle der
vier Tabellen und die am schrägen und am gerollten Stab nach: nennt die
Abnahme den Knoten nicht, gehen alle drei Lasten in die Lager, ohne
Hilfsfesselung, nennt sie ihn, mindestens eine nicht (außer beim Slave
eines RBE3 an einem gehaltenen Master). Eine Kopplung ohne wirksame Richtung oder
eine, die nur lose Knoten verbindet, schließt nichts an. Einen Hohlraum,
der ringsum von Nachbarseiten eingeschlossen ist, meldet die Abnahme
weiter als „Seiten im Inneren", auch wenn er die Oberfläche an einer Kante
berührt. Gemessen am Würfel mit um 0,5 m angehobener Ecke, frei mit h = 0,1:
4 Seiten in der Ecke (1|1|1,5). Die Ursache der Lücken im Vernetzer steht im
Befund an die Vernetzer-Sitzung vom 23.09.2026: Am L-Prisma (h = 0,25)
zählt `innen()` einen Strahl, der die Kante zweier Hülldreiecke trifft,
doppelt. Die entfernten Kappen haben dort 0 m³.

Freie Seiten werden über die sortierten Eckennummern gefunden, in zwei int64
gepackt und mit `np.lexsort` sortiert.

**Sehnen auf windschiefen Flächen** (Nachbesserung 23.09.2026). Ein
Tetraedernetz liegt auf einer bilinearen Fläche auf Sehnen, und der freie
Vernetzer setzt Knoten auf Sehnen seines groben Dreiecksnetzes
(`huelle_verfeinern` halbiert Hülldreiecke an der längsten Kante; der neue
Punkt liegt auf dem groben Dreieck). Am Würfel 1 × 1 × 1 mit um dz angehobener Deckelecke (eine
Bodenkante geteilt, damit er frei vernetzt wird) liegen die Deckelknoten bis
4,65 / 7,55 / 6,55 / 27,0 mm neben der Fläche (dz = 0,3 / 0,5 / 1,0 / 1,0 bei
h = 0,25 / 0,25 / 0,25 / 0,5); bei dz = 0,5 knapp unter dz · h² / 4 =
7,81 mm, der Abweichung einer Zellendiagonale in ihrer Mitte. Die erste Fassung meldete diese richtigen Netze — jede innere Seite
genau zweimal vorhanden — als FEHLER: 2 bis 53 „Seiten im Inneren", bei
dz = 1,0 und h = 0,5 dazu „Volumenbilanz 0,782 %" (Gegenprüfung). Drei Gründe,
drei Änderungen:

* Die Windungszahl rechnete gegen den groben Fächer der windschiefen Fläche,
  der bis |d| / 16 neben ihr liegt (d = x₀ − x₁ + x₂ − x₃; 31,25 mm bei
  dz = 0,5 — die Seitenschwerpunkte lagen −0,87 bis 5,21 mm daneben). Jetzt
  rechnet sie gegen die Fläche in 16 × 16 Teilvierecken, jedes als Fächer um
  seine Mitte (Abweichung ≤ |d| / 4096).
* Eine flache Seite über die Parameterweiten Δu, Δv weicht um höchstens
  |d| Δu Δv / 4 von der Fläche ab, und Δu, Δv ≤ D / σ_min (σ_min kleinster
  Singulärwert von [x_u, x_v] auf 9 × 9 Punkten). Eine Seite gilt als auf der
  windschiefen Fläche, wenn ihr Schwerpunkt und – bei Dreiecksseiten – ihre
  Ecken höchstens 1 % ihres Durchmessers plus s_b H² danebenliegen,
  s_b = |d| / (4 σ_min²); die Ecken einer Viereckseite höchstens 1 % (siehe
  unten, *Der Preis*). H ist
  **örtlich**: der größte Seitendurchmesser unter den Seiten dieser Fläche,
  die höchstens drei Ringe (Nachbarn über gemeinsame Knoten) entfernt sind
  (`ABNAHME_SCHIEF_RINGE`, `_ringmax`). Gezählt werden dabei nur Seiten, die
  eine Vorauswahl bestehen: Schwerpunkt nicht weiter als s_b (2 D_e)² daneben
  (D_e die Diagonale des eigenen Elements) und die Richtung stimmt. Die Knoten
  liegen auf Sehnen des groben Netzes, das größer ist als die Seiten, die
  daraus werden. Am freien Würfel, an den Seiten des Deckels, Ecken-Abstand
  weniger 1 % durch s_b H² (größter Wert je Netz, H aus der eigenen Seite /
  einem / zwei / drei Ringen; nachgemessen 23.09.2026):

  | Netz | Abnahme | eigene Seite / 1 / 2 / 3 Ringe |
  |---|---|---|
  | dz 0,3, h 0,25 (1384 tet4) | ohne Befund | 1,22 / 1,17 / 0,47 / 0,45 |
  | dz 0,5, h 0,25 (1483 tet4) | ohne Befund | 1,83 / 1,33 / 1,21 / 0,46 |
  | dz 1,0, h 0,25 (2533 tet4) | ohne Befund | 1,46 / 1,07 / 0,45 / 0,36 |
  | dz 1,0, h 0,5 (209 tet4) | ohne Befund | 0,66 / 0,61 / 0,28 / 0,18 |
  | dz 0,3, h 0,1 (15 846 tet4) | ohne Befund | −0,01 / −0,01 / −0,01 / 0,00 |
  | dz 1,0, h 0,1 (19 181 tet4) | Lücke 177 cm³, Netzrand 40 mm | 0,30 / 0,30 / 0,18 / 0,17 |

  Größter Wert: 1,83 / 1,33 / 1,21 / 0,46, mit und ohne das letzte Netz
  derselbe (alle vier am Netz dz 0,5, h 0,25). Das Netz dz 1,0, h 0,1 zählte
  bis zum 23.09.2026 unter den richtigen, hat aber am ebenen Boden eine Beule
  (Knoten 3601 bei (0,065 | 0,25 | −0,040)) und daneben eine Delle von
  177 cm³ (Nebenbefund B104; bei 3f5ae87 meldete die Abnahme dort „Seiten im
  Inneren 4“). Die Eichung misst nur Seiten am windschiefen Deckel, und dort
  ist es unauffällig; als richtiges Netz gilt es nicht mehr. Die Grenze liegt
  bei dz = 0,5 (h 0,25) zwischen 13,2 und 19,7 mm, gegen Ecken bis 7,55 mm.
* Eine Seite auf der Fläche muss auch in ihre Richtung zeigen: der Winkel
  zwischen Seite und Fläche (Normale am Fußpunkt ihres Schwerpunkts) höchstens
  arctan(0,577 + 2 s_b D_e) (`ABNAHME_SCHIEF_RICHTUNG`, 30° und mehr); 2 s_b D
  ist, wie weit sich die Flächennormale über eine Sehne der Weite D dreht.
  Gemessen: Seiten richtiger Netze bis 9,7° (frei, dz 1,0, h 0,5), abgebildete
  0,0°; die Seiten verdrehter Elemente unter dem Deckel abgestufter Netze
  (1:1, 20:1, 50:1) 56,9 bis 89,9°.

  Die zweite Fassung (3f5ae87) nahm als D den größten Seitendurchmesser der
  **ganzen** Fläche und keine Richtung. Am abgestuften Netz (20:1, Deckel
  z = 1 + 0,5 x y, alle Lagen bilinear, also exakt) lag die Grenze so bei rund
  24 mm, und die 8 Seiten eines verdrehten Elements der obersten Lage
  (Ecken 0 und 14,8 mm daneben, 81 bis 90° gegen den Deckel) galten als
  Deckel. Das war kein Befund, bei 50:1 ebenso (Gegenprüfung, Mangel 2).
  Heute: FEHLER „Seiten im Inneren 8" für die Elemente 119 und 559 bei 20:1
  und 50:1. Die Ecken zählen mit, weil am Schwerpunkt allein eine 50-mm-Beule
  verschwand (die Schwerpunkte ihrer vier Seiten wandern nur 12,5 mm). Der
  Preis: kleinere Abweichungen des Netzrands meldet die Abnahme an
  windschiefen Flächen nicht. Die Grenze gilt für den Abstand zur Fläche
  (`_bilinear_abstand`), nicht für die Verschiebung in z. Die Sehnenzulage
  gehört aber nur zwischen die Knoten (Schwerpunkt) und an die Ecken von
  Dreiecksseiten, deren Knoten der freie Vernetzer auf Sehnen setzt. Bis zum
  23.09.2026 galt sie auch für die Ecken abgebildeter Netze, deren Knoten
  gemessen 0,0000 mm neben der Fläche liegen (Nebenbefund B053). Am
  abgebildeten 4 × 4 × 4-Netz blieb so bei dz = 0,5 ein Deckelknoten 25 mm
  außerhalb ungenannt, bei 30 mm war es eine WARNUNG (an allen 21
  Deckelknoten außer den Ecken, in z wie entlang der Flächennormale). Bei
  dz = 1,0 blieben an den neun inneren Deckelknoten 80 mm entlang der
  Normalen nach außen ungenannt (Grenze halbiert 82,9 bis 84,2 mm), ein
  Knoten 100 mm in z nach oben an den sechs steileren (68 bis 81 mm neben der
  Fläche); eine Delle entlang der Normalen bis 82,9 bis 83,6 mm, an
  (0,75|0,75) bis 100,2 mm, dort in z bis 133,4 mm Abstand, weil die Delle
  H in s_b·H² wachsen ließ (Messungen zu Nebenbefund B020 am 24.09.2026,
  Code ohne die Kur von B053). Seither gilt für die Ecken von Viereckseiten (Sechsflächner,
  Keil, Pyramide) die 1-%-Grenze (`ABNAHME_HUELLABSTAND` mal
  Seitendurchmesser). Gemessen am 24.09.2026, Grenzen halbiert an allen neun
  inneren Deckelknoten (`test_abnahme_beule_windschief_nach_richtung`): Die
  erste WARNUNG „Netzrand neben der Hülle" kommt entlang der Normalen nach
  außen wie nach innen bei dz = 0,5 bei 3,55 bis 3,88 mm, bei dz = 1,0 bei
  3,60 bis 4,74 mm; in z nach oben bei 3,61 bis 4,40 bzw. 3,82 bis 6,95 mm.
  Als Abstand zur Fläche liegen die Grenzen in z und entlang der Normalen je
  Knoten höchstens 0,2 mm auseinander; in z so weit verschoben, dass der
  Knoten 3,5 mm neben der Fläche liegt, bleibt er an allen neun ungenannt,
  bei 5 mm ist er an allen neun eine WARNUNG. Am Knoten (0,75 | 0,75) in z
  verschoben: nach außen ab 5 mm (dz 0,5) bzw. 7 mm (dz 1,0) WARNUNG, 4 bzw.
  6 mm ohne Befund; nach innen ebenso ab 5 bzw. 7 mm WARNUNG, bei 20 mm
  (dz 0,5) bzw. 25 mm (dz 1,0) WARNUNG „Lücke im Netzrand“, FEHLER „Seiten im
  Inneren“ erst bei 40 bzw. 80 mm (bei ec6448c: nach außen erst ab 30 bzw.
  150 mm, nach innen bei dz 0,5 ab 60 mm, bei dz 1,0 bis 100 mm nichts). Eine
  Delle, die deutlich über die Grenze geht, zählt nicht als Netzrand neben
  der Hülle: Der Punkt knapp hinter ihren Seiten liegt im Körper
  (Windungszahl), sie zählen zu den Seiten im Inneren, und weil ihr Rand auf
  der Hülle liegt und sie Volumen hat, ist sie eine Lücke im Netzrand. 20 mm
  entlang der Normalen nach innen (dz = 0,5) sind an allen neun inneren
  Knoten eine WARNUNG „Lücke im Netzrand“. Mit der Dünnregel der Lücke vor
  B044 (t/L ≤ 5 % statt ≤ 1 %, siehe dort) waren es an sieben Knoten FEHLER
  „Seiten im Inneren", an (0,25|0,75) und (0,75|0,25) die Lücke, und am
  Knoten (0,75|0,75) in z ab 20 bzw. 30 mm FEHLER (gemessen 24.09.2026, vor
  und nach dem Zusammenführen). Die zwölf Randknoten des Deckels zwischen den
  Ecken haben dieselbe kleine Grenze: 3,5 mm entlang der Normalen oder in z
  nach außen ohne Befund, 5 mm (dz 0,5) bzw. 7 mm entlang der Normalen und
  8,5 mm in z (dz 1,0) an allen zwölf WARNUNG mit 2 Seiten
  (`test_abnahme_beule_windschief_randknoten`). Entlang der Deckelnormalen
  nach außen verschoben, verlassen sie auch die ebene Seitenfläche, bei
  80 mm um 13,9 bis 48,0 mm. Seiten auf ebenen Flächen prüft die Abnahme am
  Schwerpunkt gegen 1 % des Seitendurchmessers (`ABNAHME_HUELLABSTAND`); der
  Schwerpunkt einer anliegenden Seite wandert um ein Viertel des Anteils
  senkrecht zur Seitenfläche. Bei dz = 1,0 und 80 mm: WARNUNG „Netzrand neben
  der Hülle" mit 4 Seiten auf x = 0 und y = 0 (nach außen, Deckel- und
  Seitenfläche), mit 2 Seiten an (1|0,25) und (0,25|1), dazu FEHLER „Seiten
  im Inneren" mit 1 Seite an (1|0,5) und (0,5|1), mit 2 an (1|0,75) und
  (0,75|1) (nach innen). Zerlegt gibt der Anteil senkrecht zur Seitenfläche
  allein bei 80 mm an allen zwölf denselben Befund, außer an (1|0,25) und
  (0,25|1), wo er ohne Befund bleibt; der Rest in ihrer Ebene gibt bei 60 und
  80 mm an allen zwölf nur die WARNUNG mit 2 Seiten (24.09.2026). Vor der
  Kur von B053 waren es bei 80 mm WARNUNG mit 2 Seiten auf x = 0 und y = 0,
  die beiden FEHLER nach innen und kein Befund an (1|0,25) und (0,25|1). Die
  freien Würfelnetze der Tabelle oben mit h 0,25 und 0,5 bleiben ohne
  Befund, ebenso die Modelle der Suiten (Vorher/nachher-Vergleich beim Riss
  oben). Ein fehlender Tetraeder am windschiefen Deckel des freien Netzes
  ist eine Lücke im Netzrand (2,892e-4 m³ gemeldet, der Tetraeder hat
  2,841e-4 m³; die Lücke reicht bis zur Fläche, der Tetraeder nur bis zu
  seiner Sehne).
* Die Volumenbilanz lässt zu den 0,5 % das Volumen zu, das der Netzrand an
  windschiefen Flächen erklären kann: Σ A · (größter Abstand von Ecken,
  Kantenmitten und Schwerpunkt zur Fläche), eine obere Schranke. Gerechnet
  wird sie nur, wenn die Bilanz über 0,5 % liegt. Bei dz = 1,0 und h = 0,5:
  0,782 % Abweichung, zugelassen 2,264 %.

Den Fußpunkt auf der bilinearen Fläche sucht ein gestapeltes
Newton-Verfahren (`_bilinear_fuss`: Start am nächsten Punkt eines
5 × 5-Rasters, höchstens zwölf Schritte, geklemmt auf das Einheitsquadrat,
dazu der Abstand zu den vier geraden Randkanten). Gegen eine Zerlegung in
256 × 256 Teilvierecke liegt er nie weiter als deren eigener Fehler
|d| / (16 · 256²); er misst einen Punkt der Fläche und ist darum nie kleiner
als der wahre Abstand. Er ersetzt eine Schleife über 1024 Dreiecke je Fläche
mit je einem Aufruf von `punkt_dreieck_abstand`.

Laufzeit von `_abnahme_volumenbilanz` an einem abgebildeten Sechsflächner
(zwei Threads, die Maschine geteilt mit drei weiteren Sitzungen, die Zeiten
schwanken darum): 64 000 hex8 mit ebenen Flächen 0,16 s, mit sechs
windschiefen 0,23–0,24 s (in der ersten Fassung 4,5–5,4 s, Gegenprüfung);
216 000 hex8 eben 0,57–0,74 s, windschief 0,97–1,30 s (erste Fassung
8,5–8,8 s). Für 1 Mio Elemente **nicht gemessen**; aus 216 000 linear
hochgerechnet eben 2,6–3,4 s, windschief 4,5–6,0 s. Nach der dritten Fassung
(örtliche Sehnengrenze, Richtung, Gruppen und Lücken) nachgemessen, alter und
neuer Stand nacheinander, je dreimal: 64 000 hex8 eben 0,15–0,16 s (alt
ebenso), windschief 0,23–0,24 s (alt 0,22–0,25 s); 216 000 hex8 eben
0,54–0,56 s (alt 0,54–0,55 s), windschief 0,74–0,78 s (alt ebenso). Die
Gruppen im Inneren kosten nur, wo es Seiten im Inneren gibt. Am nicht
konformen tet4-Netz n = 20 (40 000 Elemente, dieselbe Fünferzerlegung in
jeder Zelle, jede innere Zellseite ein Riss, 91 200 Seiten) braucht
`_abnahme_netz` 7,6–7,7 s gegen 7,0–7,1 s im alten Stand. Mit Dicke der
Nachbarn, verdrehten Elementen und doppelten Knoten (vierte Fassung)
nachgemessen, je viermal: 7,72–7,87 s gegen 7,59–7,72 s. Das Netz baute
damals `grid_box`; seit c85b9cc ist `grid_box` konform (n = 20: kein Befund,
0,41 s), das Messnetz steht darum als `_nicht_konform` in
`tests/test_diagnose.py` (Nebenbefund B052). Im Profil bei ec6448c (n = 20)
entfielen 23,2 von 28,5 s auf `_randschleifen` (782 Aufrufe) – je Seite eine
Python-Schleife mit np.cross, 282 985 Aufrufe mit 18,5 s – und 2,8 s auf
`_seitengruppen`. Beide sind jetzt
gestapelt: die Ringnormalen aller Seiten einer Gruppe mit einem np.cross, die
gerichteten Kanten mit np.unique gezählt, in Python verkettet wird nur der
Rand; die Gruppen über `scipy.sparse.csgraph.connected_components`. Dieselben
Gruppen und Randschleifen wie vorher, in derselben Reihenfolge (verglichen an
11 364 Gruppen, Test `test_abnahme_riss_gestapelt`). Gemessen im selben
Prozess, abwechselnd, zweimal (die Maschine geteilt): 2,3 / 2,7 s gegen
15,0 / 14,7 s bei ec6448c, derselbe Befund „Riss im Netz 91 200“; n = 10
(5000 Elemente) 0,31–0,36 s gegen 1,68–1,83 s. Im Profil danach bleiben
0,9 s für die Schwerpunkte der Elemente an den Seiten neben der Hülle, je
Seite in Python (91 219 Aufrufe). Für 1 Mio Elemente **nicht gemessen**. Die Dicke wird nur für die Elemente an Seiten im Inneren
gerechnet, die Suche nach verdrehten Elementen nur für Gruppen, die sonst
ein Riss oder eine Lücke wären oder eine Ursache brauchen; die Suche nach
doppelten Knoten läuft seit dem 24.09.2026, sobald es Seiten im Inneren gibt
(vorher nur bei dünnen geschlossenen oder offenen Gruppen). Ein Körper mit krummen Randlinien wird an der
ersten krummen Linie verlassen, bevor ein Element angefasst wird (mit der
WARNUNG „Volumenbilanz nicht geprüft“). Mit relativer Knotennähe, Gegenüber
und Ursachen (23.09.2026) am selben nicht konformen Netz (fünf Tetraeder je
Zelle, 20 × 20 × 20, 91 200 Rissseiten), alter und neuer Stand abwechselnd,
je zweimal drei Läufe auf einer stark belasteten Maschine: alt 9,2–15,4 s,
neu 14,1–16,5 s – der Unterschied liegt in der Streuung. Mit dem Gegenüber
für alle Gruppen ohne Ursache (24.09.2026; die Suche danach gestapelt statt
in Python-Schleifen), gegen 70614f8 abwechselnd je drei Läufe: dasselbe Netz
12,2–14,1 s gegen 13,1–14,2 s; Schachbrett 6 × 6 × 6 (`_abnahme_volumenbilanz`)
2,2–2,7 s gegen 3,0–3,8 s, 8 × 8 × 8 6,1–6,9 s gegen 5,8–6,2 s (mit den
Schleifen 8,4 und 8,6 s); `abnahme` an drehlager.json (645 998 Elemente,
108 Körper, je zwei Läufe) 37,4–40,5 s gegen 37,0–37,5 s. Die Befunde waren
jeweils dieselben.

**Elemente, die eine Fuge überspannen.** Beim Ausführen einer Fuge werden die
gemeinsamen Randknoten verdoppelt und die Elemente der gelösten Seite auf die
neuen Nummern umgehängt. Danach darf kein Element einen Knoten der alten und
einen der neuen Seite zugleich benutzen — sonst überbrückt es genau die
Trennung, die eben entstanden ist, und die Fuge wirkt dort nicht. Die Prüfung
ist billig: für jedes getrennte Paar (alt, neu) darf kein Element beide
Nummern enthalten; ein Durchgang über die Elemente genügt (0,44 s bei 489 376
Elementen). Das ist der Fall, den man von außen als „halb vernetzt" sieht.

**Gefaltetes Tetraedernetz** (23.09.2026, `_abnahme_faltung`). Beim tet4
nehmen Formgüte q = 12 (3V)^(2/3) / Σ l², Netzvolumen und Steifigkeit
(`solid.tet4_shape_grad`) den Betrag des Volumens. Ein Knoten, der durch die
Gegenseite seiner Tetraeder geschoben ist, stülpt sie um; sie überdecken ihre
Nachbarn. Am Kuhn-Netz 10 × 10 × 10 (Zellen 0,1 m, 6000 tet4), Knoten 665 um
1,2 h verschoben, sechs Tetraeder mit det J < 0, sah es keine der übrigen
Prüfungen: Abnahme ohne Befund (vor dieser Prüfung, 23.09.2026). Um 1,5 h
verschoben, waagerechte Last oben: σ_v an den sechs 192,5 bis 247,3 kPa, an
den Elementen um Knoten 665 im unverschobenen Netz 281,0 bis 329,1 kPa,
mittlere Verschiebung oben −0,055 %.

Übervolumen und Volumenbilanz. Ein umgestülptes Tetraeder geht mit +|V|
statt −|V| in Σ |V| ein: Σ |V| liegt um 2 Σ |V_um| über Σ V, der Summe mit
Vorzeichen. Σ V ist das Volumen innerhalb des Netzrands; ein verschobener
innerer Knoten ändert es nicht (am Zylinder unten vor und nach dem Schub
gleich bis auf 1,1 · 10⁻¹⁶ m³). Gegen den Körper ist das gefaltete Netz also
nur dort um 2 Σ |V_um| zu groß, wo schon Σ V das Körpervolumen trifft. In
einer Volumenbilanz steht das nur, wo sie läuft: für Elemente eines Körpers
(`_abnahme_netz` geht `model.koerper` durch), dessen Hülle `_polyederhuelle`
ohne Näherung liefert (nicht bei krummen Randlinien, siehe Volumenbilanz
oben). Gemessen am 24.09.2026, jeweils Σ |V| − Σ V = 2 Σ |V_um| bis auf
höchstens 1,5 · 10⁻¹⁶ m³. Bei den Würfeln ist Σ V = V_Körper = 1 m³, die
Anteile beziehen sich auf 1 m³: Kuhn-Netz 10 × 10 × 10 im Quader K1, 1,2 h:
400 cm³ = 0,04 % < 0,5 %, kein Befund; Kuhn-Netz 4 × 4 × 4, derselbe Schub:
6250 cm³ = 0,625 %, FEHLER „Volumenbilanz“ neben „Netz gefaltet“; dasselbe
4 × 4 × 4-Netz als Nastran-BDF gelesen (`importers.nastran.import_bdf`:
384 tet4, kein Körper): 0,625 %, nur „Netz gefaltet“; freies Netz des oberen
Würfels aus `test_fugen.zwei_bloecke` ("eigene", h 0,5, oben 0,15;
4458 tet4): 17 umgestülpte in sechs Gruppen, Volumenbilanz 0,800 % =
8004 cm³, dazu „Elementgüte“ 0,0195 an Element 2871, einem der 17, das
zugleich flach ist. Beim Zylinder aus Bogenlinien (`test_mesher3d.buchse`,
r 0,5 m, H 1 m, h 0,3; 1022 tet4, `_polyederhuelle` = None), innerer Knoten
142 um 1,3 h, sind es 8 umgestülpte mit 2 Σ |V_um| = 12 693 cm³ = 1,643 %
von Σ V = 0,772542 m³, nur „Netz gefaltet“. Hier liegt das Sehnennetz schon
ungefaltet 1,637 % unter π r² H = 0,785398 m³, das gefaltete
(Σ |V| = 0,785236 m³) noch 0,021 % darunter: Σ |V| − π r² H = −162 cm³
statt 2 Σ |V_um|. Gemessen am 24.09.2026 mit dem Vernetzer vom 23.09.2026;
am Stand af2fb40 (Vernetzer davor) waren es 4454 tet4, 0,767 % = 7671 cm³
und „Elementgüte“ 0,020 an Element 2745 bzw. 1006 tet4, Knoten 143,
12 685 cm³ = 1,642 %, Σ |V| = 0,785227 m³, −171 cm³ = −0,022 %. Gegen den
Körper gemessen ist dieses gefaltete Netz also nicht zu groß; sein
Übervolumen gleicht das Sehnendefizit fast aus.
Der Befund „Netz gefaltet“ nennt deshalb 2 Σ |V| seiner Gruppe und dazu, was
die Volumenbilanz in dieser Abnahme tat: `_abnahme_volumenbilanz` trägt je
Körper Abweichung und Grenze in das Wörterbuch `bilanz` ein, sobald beide
gerechnet sind (bricht sie danach ab, nimmt `_abnahme_netz` den Eintrag
wieder heraus, denn ihr Befund ist dann verloren). Steht der Körper darin,
nennt der Befund Abweichung und Grenze, sonst „für Volumen … lief keine
Volumenbilanz“; ohne Körper „zu keiner Volumenbilanz“. Die Gruppen eines
Körpers ergeben zusammen den Anteil der Faltung an der Volumenbilanz (bei
den zwei Würfeln 3169 + 1337 + 285 + 169 + 1212 + 1833 ≈ 8004 cm³, je auf
ganze cm³ gerundet; am Stand af2fb40 3167 + 1510 + 283 + 167 + 1336 + 1208 =
7671 cm³).

Abhilfe nennt der Befund nur, soweit gemessen. Bis 24.09.2026 stand dort
„Die Knoten zurücksetzen oder neu vernetzen.“; das setzt einen von Hand
verschobenen Knoten voraus. Eine Faltung des Vernetzers selbst bleibt: er
rechnet mit fester Saat und gibt mit denselben Einstellungen dasselbe Netz.
Gemessen am 24.09.2026 an `zwei_bloecke("eigene", 0,5, h_oben)`, jeder
Aufbau zweimal, bitgleich samt Befunden: gefaltet bei h_oben 0,12 bis 0,18 (Schritt 0,01: 19, 20, 15, 17,
12, 13, 14 umgestülpte), frei bei 0,19, 0,2 und 0,25; bei 0,15 mit gmsh und
Netgen je 10, mit der Nachbesserung MMG3D 17 umgestülpte. Über
`mesher.modell_vernetzen` ein Würfel mit aufgesetzter Pyramide (eigene
Trennflächen, oben 0,15 bzw. 0,12: 11 bzw. 18 umgestülpte), zweimal vernetzt:
dieselben Knoten und Befunde. Jede der sechs Gruppen bei 0,15 hängt an einem
Knoten des Rings z = 1, den auch der untere Körper benutzt; auf der Kante
y = 0 liegen dort die Teilungspunkte beider Körper ineinander (unten 0,25,
0,5 und 0,75, dazwischen oben 0,5714, 0,7143 und 0,8571). Der Befund nennt
die Zahlen der zwei Würfel für Tetraeder in einem Körper;
`test_faltungsbefund_nennt_nur_gemessene_abhilfe` hält sie fest.

Das Merkmal ist die Lage zu den Nachbarn, nicht det J je Element: zwei
vertauschte Knoten geben det J < 0, sind aber dasselbe Tetraeder mit anderer
Nummerierung und rechnen gleich (Element 3330, max |Δu| = 1,5 · 10⁻²⁰ m bei
max |u| = 4,4 · 10⁻⁶ m). Für jede Seite (a, b, c), die genau zwei Tetraeder
mit den Gegenknoten p und q teilen, ist mit n = (x_b − x_a) × (x_c − x_a)

  h_p = n · (x_p − x_a),  h_q = n · (x_q − x_a).

Haben h_p und h_q dasselbe Vorzeichen und sind beide dem Betrag nach größer
als 10⁻⁹ · |n| · L, also |h_p|, |h_q| > 10⁻⁹ · |n| · L (beide Vorzeichen
kommen vor: am Kuhn-Netz 10 × 10 × 10 mit 1,2 h sind von den 12 gefalteten
Seiten 6 mit h_p, h_q > 0 und 6 mit h_p, h_q < 0, gemessen am 24.09.2026;
L die längste Seitenkante; `ABNAHME_FALTUNG_EBENE`, nur gegen Rundung — ein
Knoten so nahe an der Ebene gibt ohnehin Formgüte ≈ 0), liegen
beide Tetraeder auf derselben Seite: das Netz ist dort gefaltet. Die Seiten
werden wie in `_freie_seiten_ecken` sortiert gepackt und mit `lexsort`
gepaart. Welche Tetraeder umgestülpt sind, folgt aus einer Zweifärbung über
die Seiten (über einer gefalteten Seite verschiedene, sonst gleiche Farbe;
Breitensuche und Parität durch Zeigerspringen); je zusammenhängendem Netz ist
die seltenere Farbe die umgestülpte. Je Gruppe umgestülpter Tetraeder mit
gemeinsamen Knoten ein FEHLER „Netz gefaltet“ mit allen Elementnummern
(`Befund.elemente`) und den gemeinsamen Knoten. Am Kuhn-Netz: genau die sechs
mit det J < 0 (3266, 3267, 3271, 3328, 3330, 3335, gemeinsam die Kante
665–786), bei 0,5 h und beim Knotentausch kein Befund. Nur tet4:
tet10 und die übrigen isoparametrischen Elemente brechen bei det J ≤ 0 laut
Quelltext selbst ab (`solid._k_iso`, `solid._iso_an_punkten`). Aufwand am Kuhn-Netz
48 × 48 × 48 (663 552 tet4) 1,45–1,50 s, am Drehlagermodell (645 934 tet4,
kein Befund) 1,6–2,8 s bei 37,6 s für die ganze Abnahme (23.09.2026).

Jede Verletzung nennt Prüfung, Bauteil, Element, Knoten, gemessenen Wert und
Grenze — **einzeln**, ohne Sammelmeldung und ohne Auslassungspunkte: sind
zwölf Bauteile betroffen, stehen zwölf Zeilen da. Angehalten wird nicht
stillschweigend: die Oberfläche legt alles ins Protokoll, fasst in der
Rückfrage zusammen, wie viele Verletzungen je Prüfung anstehen, und überlässt
die Entscheidung dem Anwender. Wer mit 17 % Abdeckung rechnen will, soll es
können — aber nachdem er gelesen hat, dass es 17 % sind.

## 7b Freie Bewegungen: Singularitäten auffinden statt abbrechen

`singular.py`

„Factor is exactly singular" nennt weder das Bauteil noch die Richtung. Bei
108 Volumen und 88 Netzteilen ist eine Liste von Vermutungen nicht prüfbar.
Statt dessen wird gesagt, **welches** Bauteil sich **wie** bewegen kann,
**warum** und **was** dabei ins Nichts geht - und danach wird gerechnet.

### 7b.1 Stufe 1a: Restfreiheiten je Teiltragwerk

Ein Teil, das nur über Elemente und Kopplungen zusammenhängt (§ 7a,
`diagnose.teiltragwerke`), ist in sich starr. Eine Starrkörperbewegung ist

    u(p) = t + ω × r ,      r = p − c   (c = Schwerpunkt der Knoten des Teils)

Eine Halterung am Knoten p in Richtung d sperrt d·u(p) = d·t + ω·(r × d).
Auf den Unbekannten **x** = [t, L·ω] ist das die Zeile

    a = [ d , (r × d) / L ] ,     L = halbe Diagonale des umschließenden Kastens

Die Skalierung mit L ist nicht kosmetisch: ohne sie hinge die Rangentscheidung
von der Längeneinheit ab - dasselbe Modell wäre in Millimetern gehalten und in
Metern beweglich.

Alle Zeilen werden auf Norm 1 gebracht, **A** = Σ a aᵀ (6 × 6) aufgestellt und
zerlegt. Eigenwerte unter 10⁻⁶ mal dem größten spannen den Nullraum:
Bewegungen, die keine einzige Halterung dehnt oder staucht - das Teil
**gleitet**.

Zeilen liefern Knoten-, Linien- und Flächenlager, einseitige Knotenlager,
Kontaktpaare und Spaltelemente. Eine Feder hält dabei wie ein starres Lager -
nur weicher; für die Frage, **ob** gehalten wird, zählt sie mit.

**Kontaktzeilen nach der Regel des Lösers.** Die Vorabprüfung läuft, bevor es
ein Kontaktsystem gibt, und paart Slave-Knoten und Master-Facetten selbst -
aber nach derselben Regel wie der Löser (§ 4.0): eine Zeile gibt es nur gegen
eine Facette, auf die der Knoten **senkrecht fällt**,

    q ≤ ε·L + tan(κ/2)·d      (q Querversatz, d Abstand längs der Normalen)

und der Suchradius zählt längs der Normalen. ε und κ kommen aus `contact.py`
(`DECKUNGSGLEICH`, `KANTENKEGEL`) und sind nicht abgeschrieben. Bis zum
15.09.2026 nahm die Vorabprüfung die räumlich nächste Facette, gleich ob der
Knoten auf ihr oder hinter ihrem Rand lag: ein Teil, das nur über solche
Knoten an seiner Unterlage hängt, stand als gehalten da, obwohl der Löser ihm
dort keine einzige Bedingung gibt. Gesucht wird wie im Löser über **alle**
Facetten, deren Schwerpunkt höchstens Suchradius plus Umkreis entfernt liegt.
Die acht nächsten Schwerpunkte wie zuvor reichen mit der neuen Regel nicht:
neben einem fein vernetzten Streifen gehören sie alle dem Streifen, und der
Knoten fiele neben seiner eigenen Auflage heraus.

Geprüft an einer Leiste (0,1 m breit, seitlich gehalten, 1 MN Druck) an der
Kante einer Unterlage, Suchradius 0,2 m (`tests.test_singular`,
`test_neben_der_gegenflaeche_haelt_nichts`). 5 und 15 cm vor dem Rand liegt
sie auf: sie hebt höchstens ab, 0 N gehen ins Nichts. 5 und 15 cm dahinter
meldete die alte Paarung dasselbe; jetzt sind drei Bewegungen frei, darunter
das reine Heben, und die ganzen 1 MN gehen ins Nichts. Anliegend mit 15 cm
Abstand hält die Fuge bei einem Querversatz bis zur Hälfte des Kegels, beim
Doppelten nicht; bei 19,5 cm Abstand und 0,9 Kegel - räumlich schon 20,06 cm -
hält sie, weil der Radius längs der Normalen zählt. Mit der Fassung vor der
Änderung schlagen vier dieser sieben Prüfungen fehl. Die mit dem feinen
Streifen besteht die alte Fassung; sie schlägt fehl, sobald die Regel nur über
die acht nächsten Schwerpunkte angewandt wird.

**Der Rang sagt nur, ob - die Eigenwerte sagen, wie fest.** Aus derselben
Zerlegung folgt die **Haltegüte**

    g = λ_min / λ_max

also der Kehrwert der Konditionszahl von **A**. Ein Teil kann in allen sechs
Richtungen angefasst und in einer davon trotzdem tausendmal weicher gehalten
sein als in der steifsten; der Rang sieht das nicht, denn er zählt nur, ob
eine Richtung überhaupt vorkommt. Genau daran hing die Frage, warum von zwölf
gleich definierten Passstiften nur einige als beweglich gemeldet werden.

Weil alle Zeilen auf Norm 1 gebracht sind, ist λ in einer Richtung praktisch
die **Zahl** der Halterungen, die dort wirken. Halten n Knoten einer Platte in
z und nur zwei quer, ist λ_max von der Ordnung n und λ_min von der Ordnung
eins - die Güte fällt wie 1/n. Gemessen an einer Platte mit 9, 25, 49 und 121
Knoten der Unterseite: g·n = 0,517 / 0,471 / 0,456 / 0,444. Ist dieselbe
Platte allseitig gehalten, bleibt g bei 0,15 bis 0,23, unabhängig von der
Netzweite - die verbleibende Streuung ist der geometrische Anteil (r × d)/L
der Drehzeilen, der nie den vollen Betrag erreicht.

Unter `singular.HALTEGUETE_MIN` (10⁻⁴) wird gewarnt, mit Bauteil, Richtung
und Wert - **vor** dem Lösen und ohne Lösermatrix. Zum Vergleich: am
geprüften Drehlagermodell liegen die 17 Teiltragwerke zwischen 4,1·10⁻³ und
6,3·10⁻². Ein Teil eine Zehnerpotenz darunter fällt aus der Familie und ist
der Kandidat für die Meldung aus Stufe 2.

### 7b.2 Stufe 1b: die Kegelprüfung

Stufe 1a nimmt Kontaktnormalen als beidseitig. Ein geschlossener Kontakt kann
aber nur drücken; zulässig ist der Kegel

    C = { x :  a_i·x = 0   (Lager, haftende Tangenten)
               a_j·x ≥ 0   (Kontaktnormalen; ≥ 0 heißt: die Fuge öffnet) }

Das Teil ist gehalten genau dann, wenn C = {0}. Geprüft wird als kleines
lineares Programm im Nullraum der Gleichungszeilen - höchstens sechs
Veränderliche. Eine Bewegung im Kegel, die nicht schon im Nullraum aus 1a
liegt, öffnet mindestens einen Kontakt: das Teil **hebt ab**.

**Wozu diese Trennung.** „Hebt ab" und „rutscht" haben verschiedene Ursachen
und verschiedene Abhilfen: gegen das eine hilft ein Lager oder ein Verbund,
gegen das andere Reibung oder eine Führung. Eine gemeinsame Meldung nennt
keine von beiden.

**Und ihre Grenze.** Nach diesem Maßstab ist jedes Bauteil, das auf einer
Unterlage liegt, „nicht gehalten" - anheben lässt es sich immer. Das ist
kinematisch richtig und praktisch nutzlos. Erst die Last entscheidet
(§ 7b.4).

### 7b.3 Stufe 2: die Matrixdiagnose

Nicht jede Singularität ist eine Starrkörperbewegung. Zwei Würfel, die sich
**einen** Knoten teilen, hängen topologisch zusammen: Stufe 1 sieht ein
einziges, gelagertes Teil und meldet nichts. Beweglich ist der zweite
trotzdem - er dreht sich um den gemeinsamen Knoten.

Für solche Fälle - weiche Mechanismen, Splitterelemente, Nullsteifigkeit -
läuft eine inverse Iteration auf **K** + ε·**I**. Die konvergiert gegen den
betragskleinsten Eigenvektor, und das ist die Bewegung, die fast keine
Energie kostet; die Knoten mit der größten Amplitude nennen das Bauteil.
Kosten: eine Faktorisierung. Stufe 2 läuft darum erst, wenn weder die
Topologie noch Stufe 1 etwas gefunden haben.

**Zu jedem Befund gehört das Element, nicht nur das Bauteil.** Aus dem Modus
**u** folgen je Element zwei Kennzahlen:

    Ausschlag   a_e = max |u| über die Knoten von e     - wo die Bewegung sichtbar ist
    Energie     E_e = u_eᵀ K_e u_e                      - wo sie kaum Widerstand findet

Genannt wird das Element mit dem größten a_e, und E_e steht daneben - großer
Ausschlag bei fast keiner Energie **ist** die Diagnose. Damit die Zahl ohne
Kenntnis des Werkstoffs lesbar ist, steht sie zusätzlich dimensionslos als
E_e / (a_e² · mittlere Diagonale von K_e). **K**_e ist positiv semidefinit;
ein negatives Ergebnis wäre Auslöschung um die Null herum und wird auf null
gesetzt - und genau die Null ist hier der Befund: die Bewegung ist eine
Starrkörperbewegung dieses Elements und kostet nichts. Gesucht wird nur unter
den Elementen an den Knoten der Bewegung, und **K**_e wird nur für den
Gewinner aufgestellt; über alle 489 376 Elemente eines Volumenmodells wäre es
eine eigene Rechnung.

**Wenn Stufe 2 nicht rechnen kann.** Scheitert die Faktorisierung von
**K** + ε·**I**, wirft ein Schritt der inversen Iteration eine Ausnahme oder
liefert er keinen endlichen Vektor, dann gibt es keinen Modus - und daraus
folgt nicht, dass es keinen weichen Modus gibt. Die Meldung sagt dann
„Matrixdiagnose nicht möglich“ mit dem Grund, statt auf „keinen auffällig
weichen Modus“ zu schließen. Weicht die Faktorisierung nur auf einen anderen
Löser aus (etwa von PARDISO auf SuperLU), rechnet dieser den Modus; der
Ausweichgrund steht dann am Befund und als Hinweiszeile
„Diagnose-Faktorisierung: Gleichungslöser ausgewichen - …“ in der Meldung,
auch wenn kein Fortschrittsempfänger da ist (Rechenketten, Skripte, Aufträge).

### 7b.4 Die unausgeglichene Last: was wirklich ins Nichts geht

Zu jeder Bewegung gehört die verallgemeinerte Kraft der Last:

    Q = t · Σ F_k  +  ω · Σ (p_k − c) × F_k

über die Knoten des Teils. Sie ist genau das, was keine Halterung aufnimmt.
Ausgewiesen werden ihre beiden Anteile getrennt: **Kraft** (Σ F)·t̂ in Newton
und **Moment** (Σ r × F)·ω̂ in Newtonmetern.

* **Q = 0** - die Last auf dem Teil steht in sich im Gleichgewicht.
  Spannungen und Verformungen gelten; unbestimmt ist nur die Lage des Teils
  im Raum. Ein Bauteil, an dem gar nichts angreift, fällt immer hierunter.
* **Q ≠ 0** - diese Kraft geht ins Nichts. Im wirklichen Bauwerk würde sich
  das Teil bewegen; für dieses Bauteil liefert die Rechnung nichts
  Brauchbares.

Bei **gleitet** sind beide Richtungen frei, es zählt der Betrag. Bei **hebt
ab** ist nur eine Richtung frei, und die Frage lautet: gibt es im Kegel
überhaupt eine Richtung, die die Last antreibt? Gesucht wird

    max  g·x   über  x ∈ C ,  |x| ≤ 1  ,     g = [ Σ F , Σ (r × F) / L ]

Mit orthonormalem **N** (Nullraumbasis, x = N y) ist das die **Projektion auf
den Kegel**: nach Moreau zerfällt g̃ = Nᵀg in den Anteil im Kegel und den im
Polarkegel K° = {−Bᵀμ : μ ≥ 0}, das Maximum ist |P_K(g̃)| und wird bei
y = P_K(g̃)/|P_K(g̃)| angenommen. P_K° ist eine nichtnegative
Ausgleichsrechnung (`nnls`) mit höchstens sechs Zeilen - sie bricht nach
höchstens sechs Schritten ab, gleichgültig wie viele Ungleichungen der Kegel
hat.

Ein lineares Programm über dem Kasten |y| ≤ 1 täte es hier nicht: es zieht
die Richtung in die Ecken des Kastens und meldete für einen Würfel, an dem
100 kN ziehen, nur 82 kN. Die Projektion trifft die 100 kN genau - und
nennt als Bewegung das reine Abheben statt eines schrägen Kippens.

Damit ist auch die Grenze aus § 7b.2 aufgehoben: der Würfel unter Eigengewicht
findet im Kegel keine angetriebene Richtung (die Last drückt in die Fuge) und
wird als liegend gemeldet, nicht als abhebend.

### 7b.5 Rechnen statt abbrechen

Ein Abbruch hilft niemandem: ohne Verformungen kann niemand beurteilen, ob
die freie Bewegung das eigene Ergebnis überhaupt berührt. Darum wird
gerechnet. Jede gefundene Bewegung bekommt **eine** Zeile als Hilfsfesselung -
die Projektion der Knotenverschiebungen auf ihren Starrkörpermodus v,
normiert auf |v| = 1 - und die Steifigkeit dazu ist

    K* = K + k · Vᵀ V ,      k = 10⁻⁶ · max |K_ii|

Das ist der kleinstmögliche Eingriff: ein Freiheitsgrad je Bewegung, sonst
bleibt das Modell unverändert. **Und es fälscht nichts.** Für eine
Starrkörperbewegung eines ungehaltenen Teils ist K·v = 0; die
Zusatzsteifigkeit wirkt allein auf den Starrkörperanteil der Lösung, nicht
auf Dehnungen und Spannungen. Der Betrag von k geht darum auch nur in die
Größe dieses Anteils ein - und der wird nach der Rechnung wieder abgezogen
(u ← u − Vᵀ V u). Die Zeilen von **V** werden dafür orthonormiert
(modifiziertes Gram-Schmidt); sie stehen ohnehin fast senkrecht aufeinander -
Verschiebungen und Drehungen um den Schwerpunkt tun das exakt, verschiedene
Teile berühren verschiedene Knoten -, sodass aus einer benannten Bewegung
keine andere wird.

Was die Fesselung bewirkt, lässt sich in einer Zeile nachrechnen und ist im
Test verankert: Ein freier Würfel, an dessen Oberseite F zieht, bekommt die
Restkraft gleichmäßig auf alle Knoten zurückverteilt (v ist die
gleichförmige Verschiebung) - oben bleibt F/4 − F/8, unten −F/8. Durch den
Mittelschnitt geht also genau **F/2**, und die Verlängerung ist
(F/2)·L/(E·A). Der trilineare Sechsflächner bildet diesen gleichförmigen
Dehnungszustand exakt ab; die Prüfschranke ist darum 10⁻⁹ und nicht ein
Prozent.

Das ist dieselbe Idee wie die Trägheitsentlastung („inertia relief"), nur mit
gleichverteilter statt massenproportionaler Rückstellung - und ohne den
Anspruch, ein Ergebnis zu sein: die zugehörige Kraft steht daneben in der
Meldung.

### 7b.6 Anzeige

Gesucht und gefesselt werden **alle** Bewegungen - was ungefesselt bliebe,
ließe die Matrix weiter singulär. Angezeigt werden höchstens 40, und zwar die
schwersten zuerst: erst, wo wirklich Last ins Nichts geht (die größte
zuerst), dann die folgenlosen. So steht bei 88 losen Teilen oben, was die
Rechnung zunichte macht, und nicht das erstbeste Teil nach Knotennummer.

Ein Teiltragwerk ohne Lager weist die Rechnung darum nicht mehr ab. Das
Programm fragt, ob trotzdem gerechnet werden soll, und stellt die Bewegungen
danach in den Modellbaum unter *Ergebnisse → Freie Bewegungen*; ein Klick
zeichnet sie als Pfeil (Verschiebung) bzw. Drehpfeil (Drehung) an den
Bezugspunkt - bei einer Verschiebung der Schwerpunkt des Teils, bei einer
Drehung ein Punkt auf der Drehachse.

### 7b.7 Zur Reibung

Reibung ist kraftabhängig: vor der Rechnung ist die Normalkraft null und die
Tangentialhaltung damit formal auch. Für die Vorabprüfung zählt µ > 0
trotzdem als Haltung - sonst meldete jede reibungsbehaftete Fuge eine
Bewegung, die es unter Last nicht gibt. Der Text sagt es dazu, damit niemand
die Meldung für einen Freibrief hält.

## 8 Gültigkeitsbereich

* Kleine Verformungen, linear-elastisches Material (keine Plastizität,
  kein Kriechen); Theorie II. Ordnung nur als lineares Verzweigungsproblem.
* Kontakt als Penalty-Näherung ohne Lastgeschichte (monotone Lasten).
* Volumen: nachgewiesen wird der Spannungszustand nach 6.2.1(5) für die im
  Modell angelegten Volumenbereiche (Kapitel 5d). Eine Stabilitätsuntersuchung
  des Volumenkörpers gibt es nicht.
* Vernetzung: Tetraeder, linear oder quadratisch (Kapitel 6a). Die linearen
  sind steifer; für Biegung und für Spannungsspitzen an Kerben gehören die
  quadratischen genommen oder entsprechend fein vernetzt. Die Netzgüte steht
  je Körper im Protokoll.
* Schalen: ebene Elemente. Nachgewiesen werden das Schubbeulen der Stegbleche
  (Abschnitt 5), ebene Blechfelder mit und ohne Steifen (Abschnitt 10 mit
  Anhang A und 4.5), die Steifen selbst (Abschnitt 9), die Lasteinleitung
  (Abschnitt 6) und Kreiszylinderschalen nach EN 1993-1-6, 8.5 — siehe
  Kapitel 5c und die dort genannten Grenzen.
* Anschlüsse: nachgewiesen werden die im Modell angelegten Anschlüsse der drei
  Vorlagen (Kopfplatte, Laschenstoß, Knotenblech) aus den Stabendschnitt-
  größen. Die Nachgiebigkeit geht über die Anfangssteifigkeit S_j,ini als
  Drehfeder in die Rechnung ein (Kapitel 5a.1). Nicht enthalten sind die
  nichtlineare M-φ-Kurve (gerechnet wird linear mit S_j = S_j,ini/η nach
  5.1.2(4)), die Komponenten von Fußplatten auf Beton und die Interaktion
  benachbarter Schraubenreihen als Gruppe (6.2.7.2(8)) — die Reihen werden
  einzeln geführt.
* Nachweise gelten für die implementierten Querschnittstypen (I, RHS, CHS,
  Rechteck, Kreis); bei freien Querschnitten wird elastisch (Klasse 3)
  gerechnet.
* Verformungen: nachgewiesen werden Stabdurchbiegungen, Knotenverschiebungen
  und Punktpaare. Verformungen von Flächen (Plattendurchbiegung) und
  Schwingungsnachweise (Eigenfrequenz als Gebrauchstauglichkeitskriterium)
  sind nicht enthalten.
* Das Programm ist verifiziert, aber nicht bauaufsichtlich zugelassen. Die
  Verantwortung für die Anwendung und die Prüfung der Ergebnisse liegt beim
  Anwender.

## 9 Verifikation

| Test | Umfang |
|---|---|
| `tests/test_verification.py` | 27 Benchmarks Stab/Schale/Volumen (analytisch, Patch-Tests) |
| `tests/test_supports.py` | Lager mit Ausfall bei Zug/Druck, Schlupf, Reibung, Grenzkraft; Linien- und Flächenlager; Federgelenke gegen Handrechnungen |
| `tests/test_sections.py` | Profildatenbank nach Land gegen Katalogwerte, Hauptachsen der Winkel, zusammengesetzte Querschnitte |
| `tests/test_gzg.py` | Verformungsnachweise gegen 5qL⁴/384EI, PL³/48EI und den Kragarm; Grenzwertbildung L/x, absolut, Überhöhung, Punktpaar; Tabelle „Verformungen“ (Verdrehung in der mrad-Spalte, auch bei Verformung in cm), ohne das Hauptfenster zu laden |
| `tests/test_beulen.py` | Beulwerte k_σ und k_τ gegen Tab. 4.1/4.2 und A.3, σ_E = 190000 (t/b)², ρ und χ_w gegen 4.4(2) und Tab. 5.1, Schubbeulen, Methode der reduzierten Spannungen, Steifen nach A.1/A.2.2/A.3(2) und Abschnitt 9, Lasteinleitung nach Abschnitt 6, Schalenbeulen nach EN 1993-1-6, dazu der Patch-Test des Viereckelements |
| `tests/test_joints.py` | Schrauben, Nähte, T-Stummel gegen EN-Zahlenwerte; Steifigkeitsbeiwerte Tab. 6.11, Klassifizierung 5.2.2.5, Drehfeder gegen die geschlossene Kragarmlösung |
| `tests/test_volumen.py` | Vergleichsspannung, Hauptspannungen und Mehrachsigkeit gegen die geschlossenen Werte (einachsiger Zug, reiner Schub √3 τ, hydrostatischer Druck σ_v = 0, Tresca/Mises = 2/√3), σ_v = N/A am Zugkörper aus Hexaedern, Singularitäts- und Netzfeinheitshinweise |
| `tests/test_theorie2.py` | α_cr der Kragstütze und des Pendelstabes gegen die Knicklast nach Engesser, α_cr bei Zug und Druck zugleich (Zweigelenkrahmen) und bei reinem Zug gegen das dicht gelöste Problem, bitgleich wiederholbar, bei gehäuften größten μ (Geschossrahmen) richtig und höchstens das Zehnfache von Aufbau und Lösung, auch aus schlechten Schätzwerten, Vergrößerung der Verformung gegen 1/(1−N/N_cr), φ und e_0 gegen 5.3.2 und Tabelle 5.1, Gleichgewicht der Ersatzlastbilder, Feldmoment aus der Vorkrümmung, Kriterium 5.3.2(6) |
| `tests/test_klasse4.py` | wirksame Querschnitte der Klasse 4: Beulwerte, Grenzschlankheiten und ρ nach 4.4(2), Aufteilung b_e1/b_e2, W_eff,y und A_eff eines geschweißten Blechträgers gegen eine unabhängige Handrechnung, Zusatzmoment aus e_N, Schalenbeulen schlanker Kreisrohre |
| `tests/test_rfem.py` | native RFEM/RSTAB-Dateien (SQLite, ZIP, unbekanntes Binärformat) und erweiterter Tabellenimport |
| `tests/test_solver_ext.py` | Gelenke, Trapezlasten, Temperatur, Zwischenstellen, Superposition, Umhüllende, Kombinationsgenerator, einseitige Lager, Spaltelement, Flächenkontakt mit Reibung, parallele Assemblierung, Rechnerfarm |
| `tests/test_ec3.py` | Klassifizierung, Querschnittsnachweise, Knicken (χ), M_cr, χ_LT, C1/C_m, Interaktion, Wöhlerlinien, Nachweisführung |
| `tests/test_importers.py` | Import DXF, IFC, SAF, RFEM-Tabellen, INP, BDF |
| `tests/test_report.py` | Berichtserzeugung |
| `tests/test_tetp.py` | Tetraeder mit Ordnung p: Integrationsregeln gegen alle Monome, Vollständigkeit bis p = 4, sechs Starrkörpermoden, Patch-Test (verzerrt, gemischte Ordnung, lineare Pflichtseite, gekrümmt), Stapel gegen Einzelweg, Masse und Lasten, Kragarm auf 1 N/mm², umgeklapptes Element; am Modell Übergang zu tet4, Kontakt- und Lagerseiten, getrennte Fuge, laute Pflichtprüfung, Importreihenfolge, tet10-Nachbar, Jacobi-Prüfung gekrümmter Elemente, Pflichtprüfung ohne Suche je Seite (16.464 Elemente unter 0,5 s, vorher 3,1 s) |
| `tests/test_tetp_rechnung.py` | dasselbe Element durch den Löser: Model.ndof mit und ohne tetp (ohne Lauf über die Elemente), laute Abweisung veralteter FHG-Zahlen, Kragarm-Knotenmittel auf 1 N/mm², Lastsummen, Patch-Test tet4/tetp3 gemischt, Symmetrieebenen, Temperatur; je Lastart tetp2/3/4 gegen geschlossene Lösung und tet10; Linienlager starr und federnd; gekrümmte Geometrie (Hohlkugel aus tet10) über Speichern und Laden und als Auftrag bitgleich |

**Gleichzeitige Prüfläufe.** `tests/test_report.py` schreibt seine Berichte in
einen eigenen temporären Ordner je Prozess (`statik3d_report_test_…` im
TEMP-Verzeichnis), der beim Beenden des Prozesses gelöscht wird. Am Stand vor
dem 23.09.2026 war es der feste Ordner `statik3d_report_test`, in den alle
gleichzeitig laufenden Suiten des Rechners dieselben Dateinamen schrieben. Der
zeichengenaue Vergleich zweier Berichte in `test_fortschritt` las dann
gelegentlich eine Datei, die ein anderer Prozess gerade neu schrieb. Gemessen
am 23.09.2026 mit zwei gleichzeitigen Prozessen und je 150 Läufen von
`test_fortschritt` im selben TEMP-Verzeichnis: mit dem festen Ordner 27 und 51
Fehlschläge, in der Wiederholung 13 und 8; mit dem Ordner je Prozess zweimal
0 und 0. Geprüft in `test_eigener_ordner_je_prozess`: Ein zweiter Prozess
bekommt einen anderen Ordner und räumt ihn beim Beenden weg.

## 10 Tetraeder mit Ordnung p (`elements/tetp.py`, 22./23.09.2026)

Der Anwender will ein eigenes Element, „schnell und im Toleranzbereich von
1 N/mm²“ Vergleichsspannung an den Nachweisstellen. Gütemaß ist, mit wie vielen
Unbekannten und welcher Rechenzeit ein Element die 1 N/mm² erreicht. Die
Formulierung war frei und ist per Messung gewählt worden.

**Was es ist.** Ein Tetraeder mit vier Eckknoten. Die höheren Ansätze sind
**hierarchische** Funktionen an Kanten (p − 1 je Kante), Flächen
((p − 1)(p − 2)/2) und im Inneren ((p − 1)(p − 2)(p − 3)/6), für p = 2 bis 4.
Ihre Freiheitsgrade hängen an keinem Knoten, sondern liegen wie die
Wölb-Freiheitsgrade hinter den Knotenfreiheitsgraden. p = 2 ist genau der Raum
des tet10, p = 1 der des tet4. Die Geometrie ist quadratisch: Kantenmitten auf
der wahren Fläche machen das Element gekrümmt.

**Was davon aus der Literatur stammt, und was nicht.** Die Ansätze der
p-Version (Szabó/Babuška, *Finite Element Analysis*, 1991; Zienkiewicz, Gago,
Kelly 1983), die quadratische Geometrie wie beim isoparametrischen tet10 und die
Integrationsregeln mit 14 und 24 Punkten (Walkington bzw. Keast) sind bekannt.
Die Regeln sind hier aus den Momentengleichungen neu bestimmt und gegen alle
Monome geprüft. Neu ist nur der Einbau: Ordnung je Element, Übergang zu
tet4-Nachbarn und Kontaktflächen ohne Kopplung. Eine Seite, die ein Nachbar
ohne Anreicherung mitbenutzt oder an der Kontakt, Fuge oder Kopplung hängt,
bleibt linear. Ihre Spur ist dann dieselbe wie beim tet4, und der Kontakt sieht
nur Ecken.

**Warum nicht der lineare, geglättete Tetraeder.** Jeder lineare Tetraeder
(tet4, tet4 mit Knotendilatation, FS/NS-geglättet) konvergiert in der Spannung
mit O(h). Am Kragarm lag der tet4 bei 2.295 Unbekannten noch 70 N/mm² daneben
(gemessen, erste Element-Sitzung). 1 N/mm² ist so nicht erreichbar.

**Messungen** (Labor, einkernig, unter Fremdlast: Die Genauigkeit gilt, Zeiten
sind nicht gemessen. Faktorgröße und Faktorisierungsarbeit sind die Angaben
von PARDISO, iparm(18) und iparm(19)):

* **Kragarm** 1,0 × 0,1 × 0,2 m, σ_v an der Oberkante bei x = L/2 auf
  355 N/mm² (Saint-Venant): p = 3 auf 5 × 1 × 1 Kuhn-Zellen (30 Tetraeder,
  720 freie FHG) liegt jedes Element an der Stelle höchstens 0,18 N/mm²
  daneben. Der tet10 braucht für +1,0 N/mm² im Mittel 14.688 FHG. Der Fall ist
  für p = 3 günstig, denn die Balkenlösung ist fast ein kubisches Polynom.
* **Lamé-Hohlzylinder** (ebener Dehnungszustand, Innendruck, exakte Lösung;
  Netz aus dem Statik3D-Vernetzer, unstrukturiert; Knotenmittel am Innenrand):

  | Ordnung | FHG | Faktorisierung [MFlop] | Fehler |
  |---|---|---|---|
  | p = 2 überall (tet10-Raum), h = 0,018 m | 103.732 | 191.028 | 5,06 N/mm² |
  | p = 2 überall, h = 0,013 m | 260.421 | 1.352.107 | 2,71 N/mm² |
  | p = 4 überall, h = 0,05 m | 48.129 | 38.053 | 0,40 N/mm² |
  | p = 4 in einer Lage am Innenrand, sonst p = 2, h = 0,05 m | 19.067 | 4.598 | 1,05 N/mm² |
  | p = 4 in zwei Lagen am Innenrand, sonst p = 2, h = 0,05 m | 35.121 | 19.878 | 0,36 N/mm² |
  | p = 4 in einer Lage, sonst p = 1 | 15.096 | 2.259 | 15,0 N/mm² |

  Die Mischungen sind mit der Mindestregel gerechnet (siehe unten). Mit der
  zuvor benutzten Höchstregel lag eine Lage p = 4 bei 0,94 N/mm² und
  22.131 FHG; mit der Mindestregel reicht eine Lage hier knapp nicht, zwei
  reichen sicher. Hohe Ordnung an der Nachweisstelle genügt also, der Rest
  braucht aber mindestens p = 2: Ein tet4-Rest verdirbt die Spannung dort.
* **Lamé-Hohlkugel** (Prüfkörper der ersten Element-Sitzung,
  `tests/pruefkoerper.Hohlkugel`, gleiches Netz, Kantenmitten auf der Kugel;
  Auswertung wie dort: geglättete Knotenspannung des Lösers an allen
  Eckknoten der Innenfläche, größte Abweichung; `tests/messung_tetp_hohlkugel.py`,
  gemessen 23.09.2026):

  | Ordnung, Netz | FHG | größte Abweichung |
  |---|---|---|
  | p = 2 (tet10-Raum), 2×2 / 4×4 / 8×8 | 915 / 5.859 / 41.667 | 27,9 / 10,1 / 3,2 N/mm² |
  | p = 3, 4×4 / 8×8 | 18.291 / 135.075 | 1,20 / 0,16 N/mm² |
  | p = 4, 4×4 | 41.667 | 0,37 N/mm² |
  | p = 4 innen (Elemente mit einer Ecke auf der Innenfläche), sonst p = 2, 4×4 | 14.361 | 0,66 N/mm² |

  p = 2 gibt die Mittelwerte des tet10 der ersten Element-Sitzung wieder
  (−16,3 / −7,3 / −2,5 gegen −16 / −7,3 / −2,5 N/mm²); das ist die Probe,
  dass der Raum derselbe ist. Der tet10 erreicht 1 N/mm² dort bis 41.667 FHG
  nicht, das eigene Element mit p = 4 an der Innenfläche mit 14.361.

**Drei Bedingungen, gemessen:**

1. **Gekrümmte Geometrie.** Mit geraden Elementflächen ist die Bohrung ein
   Vieleck. Jede Ecke ist eine leicht einspringende Kante mit schwacher
   Singularität, und höhere Ordnung löst genau diese auf. Am Hohlzylinder mit
   gerader Bohrung (40 Abschnitte) wurde p = 2 25 bis 47 N/mm², p = 3 61 bis
   93 N/mm² und p = 4 97 bis 114 N/mm² daneben gemessen, ohne Konvergenz.
   Das gilt für jedes Element, auch für den tet10.
2. **Lückenlose Krümmung.** Musste eine einzige Kante an der Bohrung gerade
   bleiben, weil ihr Element sonst umgeklappt wäre, lag der Eckwert dort bis
   153 N/mm² daneben (p = 2, h = 0,035 m). Das Element prüft det J an Ecken
   und Kantenmitten und wirft sonst einen Fehler mit Elementnummer. An den
   Integrationspunkten allein fiele ein umgeklapptes Element nicht auf:
   gemessen mit einer Kantenmitte zwischen Viertelpunkt und Ecke, dort ist
   det J an allen 14 Punkten ≥ 0,245, an der Ecke −0,200.
3. **Knotenmittel.** Die Eckwerte einzelner Elemente streuen mehr als ihr
   Mittel über die Elemente am Knoten (p = 4: je Element bis 1,22 N/mm²,
   Knotenmittel 0,40 N/mm²). Gemittelt wird nur innerhalb eines Werkstoffs.

**Ordnung an Kante und Fläche: die Mindestregel.** Eine Kante bzw. Fläche
bekommt die kleinste Ordnung der Elemente, die sie berühren. Damit hat jedes
Element höchstens seine eigene Ordnung, und alle Elemente eines Typs `tetpN`
haben gleich viele Ansatzfunktionen. Die gestapelten Leser (Steifigkeit,
Spannung, Plastizität) schneiden ihre Felder je Typ gleich breit; mit der
Höchstregel hätte ein `tetp2` neben einem `tetp4` 35 statt 10 Funktionen
gehabt, und der Stapel wäre zerfallen. Die Mischungen oben sind mit der
Mindestregel gerechnet.

**Anbindung (23.09.2026).** Die Typen `tetp2`, `tetp3` und `tetp4` stehen im
Elementverzeichnis mit vier Knoten. `Model.ndof` zählt die Zusatz-FHG mit;
`res.u` bleibt (Knoten, 6). Steifigkeit, Spannung und Plastizität lesen den
gemeinsamen Dehnungsoperator, der die Zusatz-FHG über `Dehnungsoperator.fhg`
adressiert. Seitendruck, Eigengewicht (konsistent, ∫ N ρ g dV), Temperatur
und die Vorspannung eines Körpers sind angebunden, ebenso die Masse
(konsistent, denn eine Zeilensummenmasse gäbe den hierarchischen Funktionen
keine). Je Lastart geben `tetp2`, `tetp3`, `tetp4` und der tet10
am Würfel dieselben Zahlen wie die geschlossene Lösung (gemessen 23.09.2026:
Eigengewicht ρ g V, Seitendruck normal und schräg, Temperatur allseitig
behindert −E α ΔT/(1 − 2ν) = −189,000 MPa, Vorspannung 1 MN auf 1 m²
behindert +1,0000 MPa, frei 0). Durch den Löser gemessen
(tests/test_tetp_rechnung.py): Kragarm 10 × 2 × 2 Kuhn-Zellen, Knotenmittel an
der Nachweisstelle tet4 127,2 N/mm², `tetp2` 361,1 N/mm², `tetp3`
355,0002 N/mm² (Soll 355). Lastsummen und Patch-Test (auch mit tet4 und
`tetp3` gemischt) stimmen auf Rundung.

**Lager.** Bei einem starren Lager sind an einer gelagerten Randseite oder
Randkante die Zusatz-FHG in der gelagerten Richtung null. An einer
Symmetrieebene bleiben sie in der Ebene frei, denn dort liegen oft
Nachweisstellen. Federnde, einseitige und nichtlineare Lager wirken je Knoten
wie beim tet4: Seiten und Kanten zwischen solchen Knoten bleiben linear, denn
zwischen den Ecken hält dort nichts. Ebenso bleiben Kontakt-, Fugen- und
Kopplungsseiten linear. Trägt eine solche Seite oder Kante doch einen
Zusatzansatz, bricht die Rechnung mit Knotennummern ab. Teilt ein
quadratisches Element mit Mittenknoten (tet10, hex20, pent15) eine Kante mit
einem `tetp`, wird das Netz abgewiesen, denn der Mittenknoten hätte dort kein
Gegenüber.

**Freiheitsgrade.** `Model.ndof` fragt einen Zwischenspeicher (Elementzahl
und `_tetp_version`). Ohne `tetp` ist es wörtlich 6·nn + Wölb-FHG und läuft
nicht über die Elemente. Wer Elementtypen an Ort und Stelle ändert, erhöht
`_tetp_version`. `assemble.stiffness` zählt einmal je Aufstellen voll nach und
bricht ab, wenn das vergessen wurde.

**Fehlerschätzer.** `netzfehler` behandelt `tetp` vorerst **wie einen tet4**
(Eckfehler linear über die vier Ecken); die Ordnung ist darin nicht
berücksichtigt; der Bericht des Schätzers sagt das in einer eigenen Zeile.

**Indikator der nächsten Ordnung** (`tetp.naechste_ordnung`). Die Funktionen
der Ordnung p + 1 kommen je Element dazu, die Nachbarn halten still, und die
Energie der lokalen Korrektur ordnet die Elemente. Gemessen am Kragarm
(10 × 2 × 2 Zellen, p = 2): die fünf größten Werte liegen an der Einspannung,
wo die Singularität sitzt. Die aus der lokalen Korrektur folgende
**Spannungsänderung** taugt dagegen nicht: an der Nachweisstelle 80 bis
311 N/mm² geschätzt, wirklich änderte sich σ_v beim Übergang auf p = 3 um 2,5
bis 18 N/mm². Der Indikator liefert darum nur die Energie zum Ordnen. Ob eine
Nachweisstelle auf 1 N/mm² steht, zeigt der Vergleich der Lösungen mit p und
p + 1 an der Stelle selbst.

**Plastizität.** Sie läuft über den gemeinsamen Dehnungsoperator an den
Integrationspunkten der Steifigkeit (4, 14 bzw. 24 Punkte je Element),
Zustand je Punkt wie beim hex8 und tet10. Gemessen 23.09.2026
(tests/test_tetp_rechnung.py): die plastische Tangente ist für `tetp2`,
`tetp3` und `tetp4` die Ableitung der Rückführung (gegen zentrale Differenzen
bis 1·10⁻⁹); der plastische Zugstab bei 1,3 f_y trifft σ und die Verlängerung
exakt; der Newton konvergiert am Kragträger unter 1,20 M_el quadratisch
(2,7·10⁻² → 1,4·10⁻² → 3,6·10⁻⁵ → 2,8·10⁻⁹ → 1,3·10⁻¹³).

**Gekrümmte Geometrie aus einem tet10-Netz** (`tetp.aus_tet10`). Der
Vernetzer setzt beim tet10 die Mittenknoten auf die wahre Fläche (Anweisung
V2). Der Umwandler macht aus solchen tet10 `tetpN`-Elemente: Die Ecken bleiben
Knoten, ein Mittenknoten neben der Sehnenmitte wird zur Kantenmitte der
Geometrie (`model.tetp_kantenmitten`), die Mittenknoten selbst tragen danach
nichts. Hängt an einem Mittenknoten noch eine Knotenlast, oder ein Lager, das
die Ecken der Kante nicht ebenso tragen, bricht er ab; die Last ginge sonst
mit dem Knoten verloren. Beim `tetp` gehört eine Last als Flächenlast auf die
Seite. Gemessen 23.09.2026 an der Hohlkugel der ersten Element-Sitzung
(tet10 mit Kantenmitten auf der Kugel, 2 × 2, p = 3): 144 Elemente, 126
gekrümmte Kanten, dieselbe Abweichung (−4,09 bis +8,17 N/mm²) wie der direkte
Aufbau.

**Gekrümmte Geometrie in der Modelldatei (23.09.2026).** Die Kantenmitten
stehen in der Modelldatei unter `tetp_kantenmitten`: je gekrümmter Kante
`[Knoten a, Knoten b, x, y, z]` (Knotennummern ab 0, Koordinaten in m) in der
Reihenfolge des Modells. JSON schreibt jede Koordinate in der kürzesten
Darstellung, die beim Lesen denselben Wert ergibt; der Umlauf ist bitgleich.
Bis dahin lebte die Geometrie nur zur Laufzeit: Ein gespeichertes und wieder
geladenes Modell rechnete still mit geraden Kanten, ebenso jeder Auftrag an
Prozess-Pool oder Rechnerfarm, der das Modell auf demselben Weg verschickt
(`to_dict`/`from_dict`, `jobs.py`). Gemessen an der Hohlkugel oben (zweimal,
23.09.2026): nach dem Laden 0 statt 126 gekrümmte Kanten, Verschiebung bis
4,87 µm anders bei größter Verschiebung 79,4 µm, Knotenspannung bis
45,3 N/mm² anders. Jetzt sind Kantenmitten, Verschiebungen und
Knotenspannungen vor und nach Speichern und Laden bitgleich, ebenso der
Auftrag `solve_case` (`tests/test_tetp_rechnung.py`). Eine Datei ohne den
Schlüssel lädt wie bisher mit geraden Kanten. Die Ergebnisdatei
(`.ergebnisse`) trägt das Modell nicht – es steht dort nur als Marke – und
bleibt, wie sie ist. Geschrieben und gelesen werden nur die Einträge, die
ein tetp-Element liest (deren Kante Kante eines tetp-Elements ist); warum,
steht unten bei den verwaisten Einträgen.

Beim Anhängen einer Modelldatei kommen die gekrümmten Kanten mit dem
Knotenversatz der Quelle mit; das Zusammenführen mit dem Ziel hängt sie auf
die neuen Knotennummern um (`importers/_common._kantenmitten_umhaengen`,
ebenso in `merge_duplicate_nodes`). Fallen dabei zwei Kanten von
`tetp`-Elementen auf eine, gilt die Kante des `tetp`-Elements, das im Modell
zuerst steht – beim Anhängen die des Ziels –, gerade oder gekrümmt. Eine
gerade Kante hat keinen Eintrag; als ihre Kantenmitte zählt die Sehnenmitte.
Liegen die beiden Kantenmitten weiter als 10⁻⁹ der Kantenlänge auseinander
(die Grenze, mit der `aus_tet10` gekrümmt von gerade trennt), warnt das
Protokoll und sagt, an wie vielen dieser Kanten eine Seite gerade war.
Geprüft an der Hohlkugel mit einem Zielknoten auf einer Ecke einer
gekrümmten Kante: die Geometrie jedes angehängten Elements ist bitgleich die
der Quelle (`tests/test_importers.py`).

Diese Regel gilt nur zwischen `tetp`-Elementen; das Zusammenführen sieht nur
deren Kanten. Teilt die Kante danach ein Volumenelement ohne Anreicherung
(etwa ein tet4), ist sie gerade (unten: Geometrie an der Grenze zum tet4),
gleich welche Seite zuerst steht, und das Protokoll warnt nicht. Die
Kantenmitte bleibt eingetragen, `geometrie_modell` übergeht sie dort. Gemessen
(zweimal, 24.09.2026) am Viertel-Hohlzylinder 4 × 1 (tet10 mit Kantenmitten
auf dem Kreisbogen, `aus_tet10`, p = 3) mit demselben Zylinder als tet4 um h
darüber, in beiden Reihenfolgen: 10 Knoten zusammengeführt, 17
Anschlusskanten, davon 8 gekrümmt; dort liegt die Geometrie genau auf der
Sehnenmitte, die Kantenmitten der `tetp`-Elemente rücken um bis zu 3,843 mm
(größte Koordinatenänderung 3,769 mm; die Pfeilhöhe b (1 − cos 11,25°) des
Bogens am Außenradius b = 0,2 m), sonst bitgleich, keine Warnung (`tests/test_importers.py`). Mit
demselben Zylinder als tet10 darüber bricht die Rechnung ab (Mittenknoten ohne
Gegenüber, siehe oben unter Lager). Schalen und Stäbe zählen dabei nicht:
`tetp.pflichtseiten` sieht nur Volumenelemente. Am selben gekrümmten Zylinder
(zweimal, 24.09.2026) blieben die 8 gekrümmten Deckkanten gekrümmt mit einem
shell3 auf jedem der 8 Deckdreiecke oder einem beam auf jeder dieser Kanten;
mit einem tet4 auf jedem Deckdreieck oder einem hex8 an jeder dieser Kanten
wurden sie gerade.

Bis zur Nachbesserung vom 24.09.2026 galt der zuerst eingetragene Eintrag,
und eine gerade Seite zählte nicht: Es galt still die gekrümmte Kante, auch
wenn die des Ziels gerade war. Gemessen am Stand bc1dfe0 (zweimal am 23.09.,
einmal am 24.09.2026): die Hohlkugel an sich selbst gehängt, eine Kante in
einer der beiden Dateien gerade – je nach Seite die Elemente des Ziels oder
die angehängten um bis zu 1,921 mm (größte Koordinatenänderung 1,885 mm)
verschoben, ohne Warnung; ein Hohlzylinder mit geraden Kanten als Ziel und
darüber derselbe Zylinder mit gekrümmten Kanten als Quelle (19 Knoten
zusammengeführt) – die Elemente des Ziels um bis zu 3,843 mm (größte
Koordinatenänderung 3,769 mm) verschoben, ohne Warnung. Jetzt bleiben in
beiden Abläufen die Elemente des Ziels bitgleich, die angehängten nehmen an
der Anschlusskante die Kante des Ziels an, und das Protokoll warnt
(`tests/test_importers.py`).

Mitgenommen werden beim Zusammenführen nur die Kantenmitten, deren Kante vor
dem Zusammenführen Kante eines tetp-Elements ist; die übrigen fallen weg.
Solche verwaisten Einträge lässt `Model.netzknoten_loeschen` stehen, das die
Kantenmitten nicht mitführt – zum Teil mit Knotennummern hinter dem Ende der
Knotenliste. An ihnen brach das Zusammenführen bis zur Nachbesserung vom
23.09.2026 mit einem IndexError ab: gemessen (zweimal) beim Anhängen eines
JSON-Modells an die gespeicherte Hohlkugel mit einem Stab, deren tetp-Netz
entfernt war; vor der Speicherung der Kantenmitten (Stand ec6448c) lief
derselbe Ablauf durch. Nur die Einträge hinter dem Ende zu verwerfen genügt
nicht: Ein verwaister Eintrag mit gültigen Nummern wird zur Kante eines
tetp-Elements, sobald beim Zusammenführen ein neuer Knoten auf deren Ecke
fällt. Mit dieser Variante gemessen (zweimal, 23.09.2026) nach
`netzknoten_loeschen` und sieben hinzugefügten Knoten, der letzte auf einer
Ecke: eine gerade Kante lag danach 45,79 mm daneben, ohne Warnung.

Das allein genügte beim Anhängen nicht. Der Filter sieht nur die Nummern vor
dem Zusammenführen, und ohne zusammenfallende Knoten läuft er gar nicht. Ein
verwaister Eintrag des Ziels, dessen Nummern die einer Kante eines
angehängten Elements waren, galt dann dort. Gemessen am Stand bc1dfe0
(zweimal am 23.09., einmal am 24.09.2026): Ziel die gespeicherte Hohlkugel
mit Stab, geladen, tetp-Netz entfernt (38 Knoten, 126 Kantenmitten), Quelle
ein Kragarm aus tetp3 ohne gekrümmte Kante – 8 angehängte Elemente bis
5556 mm neben der Quelle, wenn kein Knoten zusammenfiel, bis 2556 mm, wenn
einer auf das Stabende fiel, je 7 davon mit det J ≤ 0, ohne Warnung; Ziel
ganz geleert, Quelle eine Hohlkugel aus geraden tetp3 – bis 89,90 mm
daneben (größte Koordinatenänderung 87,12 mm), die Rechnung brach ab
(Element umgeklappt). Am Stand ec6448c blieben dieselben Abläufe bei 0 mm.
Seit der Nachbesserung vom 24.09.2026 nimmt das Anhängen von Ziel und Quelle
nur die Einträge mit, die eines ihrer tetp-Elemente liest, bevor es die
Quelle anfügt (`model.tetp_kantenmitten_gelesen`), und `to_dict` und
`from_dict` schreiben und lesen nur diese: Ein verwaister Eintrag übersteht
Speichern und Laden nicht mehr. In diesen Abläufen ist die Geometrie der
angehängten Elemente jetzt bitgleich die der Quelle (`tests/test_importers.py`).
Dass `netzknoten_loeschen` die Kantenmitten nicht mitführt, ist damit nicht
behoben: im laufenden Modell entstehen verwaiste Einträge weiterhin.

**Nachweisstellen auf Kontaktflächen.** Gemessen 23.09.2026 (Labor,
Hohlzylinder h = 0,05 m, Bohrungsfläche als Kontaktseite, dort nur linearer
Ansatz, die Geometrie bleibt gekrümmt), Knotenmittel am Innenrand:

| Ordnung | ohne Kontaktregel | Bohrung als Kontaktseite |
|---|---|---|
| p = 2 überall | 14,8 N/mm² | 16,0 N/mm² |
| p = 4 in einer Lage, sonst p = 2 | 1,05 N/mm² | 19,5 N/mm² |
| p = 4 in zwei Lagen, sonst p = 2 | 0,36 N/mm² | 19,9 N/mm² |
| p = 4 überall | 0,40 N/mm² | 19,9 N/mm² |

Liegt die Nachweisstelle **direkt auf** einer Kontaktseite, bringt das
Element heute also nichts gegenüber dem tet10: Der lineare Ansatz auf der
Seite begrenzt den Fehler auf 15 bis 20 N/mm², egal welches p im Inneren
steckt. Abhilfe wäre ein Kontakt über Punkte der Seite mit allen Funktionen
der Seite (Ecken, Kanten, Fläche) statt über die Ecken. Das gilt für den
tet10 genauso und ist ein Umbau des Kontakts (Löser-Sitzung, B4). Die
Schnittstelle dafür liefert `tetp.flaechenschnittstelle`: Punkte, dA,
Außennormalen, Ansatzwerte und FHG je Seite, geprüft gegen Fläche, Normale,
lineares Feld und die Seitenlast. Solange der Kontakt sie nicht nutzt,
bleiben Kontaktseiten linear.

**Geometrie an der Grenze zum tet4.** Eine Kante, die ein `tetp` mit einem
Element ohne Anreicherung teilt, ist auch geometrisch gerade, sonst klaffte
die Geometrie. Kontakt- und Fugenkanten bleiben gekrümmt: Dort liegt kein
Nachbar, dessen Geometrie passen müsste, und Nachweisstellen an Bohrungen
brauchen die Krümmung. Gemessen am Hohlzylinder: Musste eine einzige
Bohrungskante gerade bleiben (Umklappschutz, h = 0,035 m), lag dort selbst
p = 4 überall 23 N/mm² daneben.

**Kosten am Drehlager (M1, 23.09.2026).** Gemessen ohne zu rechnen
(`tests/messung_m1_tetp.py`, dieselben Spalten wie `tests/messung_m1.py`):
Muster der Steifigkeit über die Inzidenz Element–Funktion, dann die
symbolische Analyse von PARDISO (Phase 11). `drehlager.json`: 158.728 Knoten,
645.934 tet4. Gekrümmt sind 786 der 1.311 Modellflächen (Winkel einer
Seitennormale zur mittleren Normale über 0,5°, gemessen am Netz). Die Lage
daran (Elemente mit einer Ecke auf der Fläche) umfasst 251.007 Elemente, 39 %.

| Variante | Unbekannte | nnz(K) | nnz(Faktor) | MFlops Faktor |
|---|---|---|---|---|
| heute (tet4) | 475.599 | 17.598.267 | 171.056.601 | 79.231 |
| p = 2 überall | 2.662.476 | 201.087.810 | 2.562.688.524 | 4.166.926 (52,6 × heute) |
| p = 4 in der Lage, Rest tet4 | 7.324.635 | 1.143.391.563 | – | – |
| p = 4 in der Lage, sonst p = 2 | 8.845.266 | 1.346.891.508 | – | – |

Die letzten beiden wurden nur gezählt: Über nnz(K) = 6·10⁸ baut das Skript die
Matrix nicht (die Maschine teilen sich mehrere Sitzungen). Die letzte Zeile
enthält alle Funktionen der zweiten, kostet also mehr als das 52,6-Fache.
nnz(Faktor) meldet PARDISO in iparm(18) als int32; bei p = 2 lief die Zahl
über und ist um 2³² berichtigt. Im Muster gleicht p = 2 überall dem tet10
überall genau (am Quader 1.176 FHG und nnz 76.176 in beiden).

**Folgerung:** Auf dem heutigen Netz des Drehlagers bleibt keine Variante mit
höherer Ordnung an allen Krümmungen in der Rechenzeit von heute. Das Element
kann sich dort nur auf einem deutlich gröberen, gekrümmten Netz lohnen.
Hergeleitet, nicht gemessen: Wächst der Faktoraufwand wie n², braucht p = 2
für die Kosten von heute etwa 14 % seiner Unbekannten, also etwa doppelt so
große Elemente. Ob ein solches Netz die 1 N/mm² hält, zeigt erst M2/M3.

**Aufbau der Anreicherung.** Beim Messen fiel auf, dass `anreicherung` am
Drehlager (alles tetp2) 489 bis 564 s brauchte (zwei Läufe): Die Pflichtprüfung suchte für jede
der 110.089 gebundenen Seiten ihre Kanten in der ganzen Kantenliste. Die Suche
war überflüssig, denn die Kanten einer gebundenen Seite haben zwei gebundene
Ecken und stehen schon in der Menge daneben. Ohne sie: 22,7 s. Mit Feldern
statt Schleifen je Element in `pflichtseiten` und einem Schlüssel statt
`np.unique(axis=0)`: 5,8 s; gemischt tet4/p2/p4 16,1 statt 280 s. Die
Nummerierung ist dieselbe; geprüft
wurden alle Felder der Anreicherung, die gesperrten FHG und der
Fingerabdruck gegen die alte Fassung, an vier Quadern und am Drehlager
(p = 2 überall und gemischt tet4/p2/p4).

**Kosten je Körper (M1, 23.09.2026).** `tests/messung_m1_tetp.py --koerper`:
jeder Körper ab 1 % der Elemente einzeln als `tetp`, der Rest bleibt tet4.
Faktorisierung gegen heute (79.231 MFlops), in Klammern die Unbekannten:

| Körper | Elemente | p = 2 | p = 3 |
|---|---|---|---|
| V30 | 116.438 (18,0 %) | 29,6 × (1,80 ×) | 327 × (4,03 ×) |
| V33 | 80.600 (12,5 %) | 4,27 × (1,62 ×) | 33,4 × (3,28 ×) |
| V35 | 79.105 (12,2 %) | 3,75 × (1,61 ×) | 33,4 × (3,24 ×) |
| V31 | 78.176 (12,1 %) | 3,20 × (1,56 ×) | 27,8 × (3,10 ×) |
| V14 | 53.258 (8,2 %) | 6,70 × (1,38 ×) | 53,0 × (2,44 ×) |
| V34 | 49.274 (7,6 %) | 2,55 × (1,35 ×) | 16,5 × (2,30 ×) |
| V15 | 46.976 (7,3 %) | 2,35 × (1,33 ×) | 16,1 × (2,23 ×) |
| V36 | 38.564 (6,0 %) | 2,11 × (1,25 ×) | 10,4 × (1,97 ×) |

Nach der Löser-Sitzung (LF1, gemessen 23.09.2026) sind die Zerlegungen 49 %
der Laufzeit (139 × 3,41 s von 965 s). Auf dem heutigen Netz verlängert also
schon der kleinste Körper mit p = 2 die Rechnung deutlich. Die Faktorgröße
meldet PARDISO in iparm(18) als int32; sie lief bei V30 mit p = 3 einmal ganz
um 2³² und ist über den Faktorspeicher iparm(17) berichtigt (Verhältnis
KB · 128 / nnz = 1,06 bis 1,15 an großen Faktoren, gemessen).

**Wie genau ist tet4 an einer Bohrung? (Labor, 23.09.2026.)** Lamé-Hohlzylinder
(r = 0,1/0,2 m, Innendruck, σ_v am Innenrand auf 355 N/mm², Netz aus dem
Statik3D-Vernetzer, alle Netze konform geprüft), Knotenmittel am Innenrand:

| tet4, h | Knoten auf dem Ring (Bogen) | FHG | MFlop | Fehler |
|---|---|---|---|---|
| 0,050 m | 20 (18,0°) | 888 | 8 | 121,0 N/mm² |
| 0,035 m | 20 (18,0°) | 2.107 | 55 | 105,6 N/mm² |
| 0,025 m | 26 (13,8°) | 5.243 | 371 | 81,1 N/mm² |
| 0,018 m | 34 (10,6°) | 13.224 | 2.397 | 67,4 N/mm² |
| 0,013 m | 48 (7,5°) | 33.042 | 16.290 | 48,9 N/mm² |
| 0,010 m | 62 (5,8°) | 70.072 | 71.262 | 40,7 N/mm² |
| 0,008 m | 78 (4,6°) | 132.185 | 267.503 | 31,3 N/mm² |

Auf dem Netz der ersten Zeile, gekrümmt: `tetp` mit p = 4 in einer Lage und
sonst p = 2 liegt 1,05 N/mm² daneben (19.067 FHG, 4.598 MFlop), mit zwei Lagen
0,36 N/mm² (35.121 FHG, 19.878 MFlop). tet4 erreicht die 1 N/mm² auf keiner
Stufe; bei 58-fachem Aufwand liegt er noch 31 N/mm² daneben.

**Wie grob darf das gekrümmte Netz sein? (Labor, gleicher Körper.)** Bogenwinkel
des Vernetzers (`mesher3d.BOGENWINKEL`, im Labor gesetzt) und Kantenlänge
gegen den Fehler, nur Netze ohne gerade gebliebene Kante an der Bohrung:

| Bogen, h | Tetraeder | kleinste det J/6V | p = 4 in 1 Lage, sonst 2 | p = 4 überall | p = 3 überall |
|---|---|---|---|---|---|
| 18°, 0,05 m | 1.400 | 0,218 | 1,05 N/mm², 4.598 MFlop | 0,40 N/mm², 38.053 MFlop | 1,85 N/mm², 7.059 MFlop |
| 36°, 0,07 m | 405 | 0,260 | 2,89 N/mm², 899 MFlop | 2,59 N/mm², 3.788 MFlop | 15,0 N/mm², 649 MFlop |
| 36°, 0,10 m | 136 | 0,772 | 3,24 N/mm², 278 MFlop | 3,26 N/mm², 493 MFlop | 9,27 N/mm², 94 MFlop |

Bei 36° bleibt jede Ordnung bei etwa 2,6 N/mm² stehen: Die quadratische
Geometrie trifft den Bogen nicht genauer. Für 1 N/mm² mit quadratischer
Geometrie reicht nach dieser Messung ein Bogen von 18°; zwischen 18° und 36°
ist nicht sauber gemessen. Die Elementgröße ist dort nicht die Grenze: Bei 36°
änderte h = 0,7 statt 1,0 × Bohrungsradius wenig (2,89 gegen 3,24 N/mm²); bei
18° ist nur h = 0,5 × Bohrungsradius gültig gemessen. Was die Messung unbrauchbar machte, und damit die
Anforderung an den Vernetzer (V2): Eine einzige gerade gebliebene
Bohrungskante (30°, h = 0,05 m) ergab 11 bis 34 N/mm² für jedes p. Geglättete
innere Kantenmitten mit kleinster det J/6V = 0,062 (30°, h = 0,07 m) ergaben
157 bis 890 N/mm². Und Knoten, die der Vernetzer bei grober Kantenlänge auf die
ebenen Facetten setzt (r = R·cos(Bogen/2) statt r = R), müssen ebenfalls auf
die wahre Fläche. Das Labor hat sie nicht verschoben (18° und 30° bei
h = 0,07 bis 0,10 m), diese Zeilen sind ungültig und fehlen oben.

**Offen.** Kantenmitten und Randknoten auf der wahren Geometrie an Bauteilen liefert erst der
Vernetzer (V2, siehe oben); aus dessen tet10 macht `aus_tet10` gekrümmte `tetp`. Weiter offen
sind die Wahl der Ordnung je Element in der Oberfläche und automatisch sowie ein Fehlerschätzer für höhere Ordnung
(`netzfehler` behandelt das Element vorerst wie einen tet4). Der Anwender hat
festgelegt, dass die Rechnung am Drehlager nicht länger werden darf als heute.
Nach M1 geht das nur mit einem gröberen gekrümmten Netz in den Nachweiskörpern
(Labor: Bogen 18° bei h = 0,5 × Bohrungsradius gemessen). Ob das Element es dann am
Bauteil schafft, zeigen erst M2 und M3. Nachweisstellen auf Kontaktseiten
bleiben ohne Kontakt über Punkte der Seite (B4) bei 15 bis 20 N/mm².


## 11 Finite-Cell-Methode: Volumenmodul `volumen3d` (Teilprojekte 1 bis 6, 27.09. bis 06.10.2026)

Das Volumenmodul rechnet Volumenbauteile ohne klassisches Vernetzen: Der Körper wird in ein
achsparalleles Gitter würfelförmiger Zellen eingebettet, die Geometrie geht nur über eine
vorzeichenbehaftete Abstandsfunktion (SDF) ein. Verbindlich sind
`docs/Vorgabe_Statik3D_Abschnitt_FCM-Volumenloeser.md` und der Schnittstellenvertrag
(`docs/Schnittstellenvertrag_Statik3D_FCM.md`, seit 28.09.2026 Version 2.1.0); die Umsetzungsentscheidungen stehen in
`packages/volumen3d/docs/Entwurf.md`. Dieses Kapitel hält die Formeln und die gemessenen Zahlen
fest, geordnet nach den Teilprojekten: 11.1 bis 11.7 Teilprojekt 1 (CPU-Referenz: assemblierte Steifigkeit, Direktlöser), 11.8 Teilprojekt 2
(Oktree, hängende Freiheitsgrade, STL), 11.9 Teilprojekt 3 (matrixfreier Operator, PCG), 11.10 Teilprojekt 4 (p-Mehrgitter, mit den Leistungsarbeiten A1 bis A6 des Plans TP 5), 11.11 bis 11.21
Teilprojekt 5 (Moment Fitting, Spannungsrückgewinnung, Hot-Spot, adaptive Zyklen, STEP, Hüllenintegration, Schale, Knotenblech, zweite Sicht,
Streuung mit der Gitterlage, Konsistenz der Schnittzellen) und 11.22 Teilprojekt 6a (Fehlerschätzer). Beobachtungen und Entscheidungen, die später dazukamen, stehen als „Nachtrag“ im Abschnitt, auf den sie sich
beziehen (oder in 11.19 und 11.20); ein früherer Absatz kann dadurch überholt sein. Einheiten im Modul: mm, N, N/mm².

### 11.1 Ansatz und Freiheitsgrade

Je Zelle (Kante h) ein volles Tensorprodukt hierarchischer Ansätze aus integrierten
Legendre-Polynomen, p = 1…4: `N1 = (1−ξ)/2`, `N2 = (1+ξ)/2`,
`N_{j+1} = (P_j − P_{j−2}) / sqrt(2(2j−1))` für j = 2…p, sodass `∫ φ_i' φ_j' dξ = δ_ij`.
Die (p+1)³ Moden hängen an Ecken (8), Kanten (12·(p−1)), Flächen (6·(p−1)²) und dem Zellinneren
((p−1)³); Nachbarzellen teilen die Moden ihrer gemeinsamen Entität ohne Vorzeichenwechsel, weil
alle Kanten und Flächen kanonisch in +Achsrichtung parametrisiert sind. Freiheitsgrade
`3·Mode + Komponente`. Ein voller Quader mit n_x × n_y × n_z Zellen hat genau
(n_x p+1)(n_y p+1)(n_z p+1) Moden (`packages/volumen3d/volumen3d/tests/test_gitter.py`).

### 11.2 Zellklassifikation

Mit d dem Abstand der Zellmitte und r der halben Raumdiagonale gilt: d > r → OUTSIDE (keine
Freiheitsgrade), d < −r → INSIDE (Gauß (p+1)³), sonst CUT. Das ist nur zulässig, weil die
CSG-Kombinationen (Vereinigung = min, Schnitt = max, Differenz = max(d_a, −d_b)) den Abstand zur
Gesamtoberfläche **nie überschätzen**: Jeder Punkt der Gesamtoberfläche liegt auf einer
Grundform-Oberfläche, und der Weg dorthin kreuzt die Flächen, die in min/max den Ausschlag geben
(Skizze in `geometry/csg.py`). Stichprobe: 300 Zufallspunkte je Zelle einer Kugel, keine
INSIDE-Zelle mit Außenpunkt, keine OUTSIDE-Zelle mit Werkstoff.

### 11.3 Integration geschnittener Zellen

Die Vorgabe (Abschnitt 6) nennt rekursive Teilung mit Punkttest je Gauß-Punkt. Gemessen:
Würfel 100³, schräg durch eine Ebene halbiert, h = 20, Tiefe 4, 6,5·10⁶ Punkte – Volumenfehler
0,5 %. Der Punkttest ist erster Ordnung in der Blattkante; der Patch-Test der Vorgabe
(< 10⁻⁶) ist damit unerreichbar. Umgesetzt sind darum **ebenen-exakte Blätter**: In einer
geschnittenen Teilbox nennen die aktiven Grundformen (|d| ≤ r) ihre lokalen Ebenen – Halbraum
und Quaderseiten exakt, Zylinder und Kugel als Tangentialebene –, der CSG-Baum prüft an den
Gauß-Punkten, ob sich der Gesamtabstand als „Schnitt der positiven Formen minus Löcher“ (max)
oder als Vereinigung (min) rekonstruieren lässt, und zerlegt die Teilbox in disjunkte konvexe
Stücke (Box ∩ Halbräume, Löcher über S ∖ ∩h_j = ∪_j S ∩ ¬h_j ∩ h_1…h_{j−1}). Jedes Stück wird
gegen seine Halbräume geclippt (Sutherland–Hodgman auf den Polyederflächen, Deckelpolygon aus
den Schnittkanten), vom Schwerpunkt aus in Tetraeder zerlegt und mit der konischen Produktregel
(Gauß–Jacobi in u und v, Gauß–Legendre in w, n = ⌈3p/2⌉ Punkte je Richtung, exakt bis
Gesamtgrad 2n−1 ≥ 3p−1) integriert; achsparallele Stücke direkt mit Tensor-Gauß. (Stand Teilprojekt 1. Seit O5, 03.10.2026, gehen schräg geschnittene Stücke bei Moment Fitting mit ihren
exakten Momenten ein, 11.21: die Regel bis zum Gesamtgrad 3p − 1 genügt dem linearen Patch-Test, aber keinem Feld höheren Grades.)

| Prüfkörper (h = 10 bzw. 20, `test_quadratur`) | Volumenfehler |
|---|---|
| Würfel schräg halbiert, Tiefe 0/1/2 | 500000,000000 (exakt) |
| Würfel mit zwei Ebenen und Kante, Tiefe 0 = Tiefe 3 | < 10⁻¹⁰, gegen Monte-Carlo 2,7·10⁻⁴ |
| Quader mit Kanten und Ecken in den Zellen | 11424,000000 (exakt) |
| Kugel R 43, Tiefe 0/1/2/3 | 1,4·10⁻² / 3,4·10⁻³ / 8,5·10⁻⁴ / 2,1·10⁻⁴ (Faktor 4: zweite Ordnung) |
| Lochplatte 800×400×10, Loch 40, Tiefe 1/2 | 2,0·10⁻⁵ / 5,2·10⁻⁶ |
| Platte 100×100×10, alle Zellen geschnitten | 64 Punkte je Zelle, exakt |

Der fiktive Bereich kommt ohne negative Gewichte aus: ganze Teilbox mit Gewicht α, Stücke mit
(1−α). Lässt sich die lokale Semantik nicht rekonstruieren, teilt die Rekursion zwei Stufen
tiefer und fällt auf den Punkttest zurück (Zähler `blaetter_punkttest` im Protokoll; in allen
Prüfkörpern 0).

### 11.4 Kleine Schnittzellen: Zellaggregation statt α

Patch-Test-Gitter (Quader durch zwei schräge Halbräume, 113 von 118 Zellen geschnitten): 10 Zellen
mit Werkstoffanteil unter 10⁻⁴, drei mit 0. Der Fehler der FCM-Lösung skaliert mit α/Anteil:
Spannung 1,4·10⁻² bei α = 10⁻⁸, 1,4·10⁻⁴ bei 10⁻¹⁰. (Nachtrag O5, 03.10.2026: das Wertepaar war kein Gesetz. Über α = 10⁻⁶ … 10⁻¹² ist der Fehler ohne Aggregation nicht monoton – mit der
Tetraederregel 3,5·10⁻² / 6,0·10⁻³ / 1,4·10⁻² / 4,1·10⁻⁴ / 1,4·10⁻⁴ / 1,0·10⁻⁵, mit den exakten Stückmomenten 3,2·10⁻² / 5,1·10⁻² / 7,8·10⁻⁴ / 4,3·10⁻⁴ / 1,8·10⁻⁴ / 2,5·10⁻⁵;
α kleiner zu wählen hilft also nicht verlässlich, 11.21.) Abhilfe nach Vorgabe 8.3 (Zellaggregation,
Prinzip der aggregierten finiten Elemente, Badia/Verdugo/Martín 2018): Zellen mit Anteil unter
der Schwelle (bis 28.09.2026 abends 0,25, seither 0,4, siehe 11.10) bekommen eine wohlgestellte Wurzelzelle (Nachbar mit größtem Anteil, Fläche vor Kante vor
Ecke, Ketten aufgelöst); Moden, die keine wohlgestellte Zelle trägt, werden an die Fortsetzung
des Wurzelpolynoms gebunden: `M = V_c⁻¹ V_R` (Modalprojektion an Tensor-Chebyshev-Lobatto-Punkten,
gleiche Zellgröße). Gelöst wird `CᵀKC`. Zwei weitere Befunde zwangen α aus dem Verfahren:
gebundene Zellen dürfen keine α-Punkte tragen (α wirkt sonst auf die extrapolierten Wurzelmoden,
die wie (2ξ)ᵖ wachsen: 2·10⁻⁵ statt 3·10⁻⁸), und in wohlgestellten Zellen tragen hohe Moden nur
etwa Anteil^(2p+1) ihrer Energie im Werkstoff (0,28⁷ ≈ 10⁻⁴ bei p = 3), sodass α = 10⁻⁸ dort
10⁻⁴ Fehler macht. Mit Aggregation erhält darum nur eine Zelle **ohne Wurzel** (isolierter
Splitter) den Faktor α; alle anderen Schnittzellen werden ohne fiktives Gebiet integriert.

| Patch-Test (lineares Feld über Nitsche auf dem ganzen Rand) | u relativ | σ innen | σ am Rand |
|---|---|---|---|
| p = 1 (681 FHG, 438 frei) | 5·10⁻¹⁵ | 8·10⁻¹³ | 2·10⁻¹² |
| p = 2 (4023 FHG, 2469 frei) | 8·10⁻¹⁴ | 5·10⁻¹¹ | 1·10⁻¹⁰ |
| p = 3 (12153 FHG, 7320 frei) | 5·10⁻¹² | 5·10⁻⁹ | 1·10⁻⁸ |
| p = 2, Schnittanteil 10⁻⁶ (Vorgabe 13) | 9·10⁻¹⁴ | 4·10⁻¹¹ | 9·10⁻¹¹ |
| p = 2, α = 10⁻¹⁰ bzw. β-Faktor 100 statt 10 | 7·10⁻¹⁴ / 3·10⁻¹³ | 3·10⁻¹¹ / 4·10⁻¹¹ | – |

### 11.5 Verschiebungsränder: symmetrisches Nitsche

Je Quadraturpunkt der Randfläche mit Verschiebungsinterpolation Nm (3×3m), Traktionsoperator
`T = Nn D B` (3×3m; Nn bildet den Voigt-Spannungsvektor auf σ·n ab), Projektion P (Einheit oder
n nᵀ) und Gewicht w:
`K += w [ −Tᵀ P Nm − Nmᵀ P T + β Nmᵀ P Nm ]`, `f += w [ −Tᵀ P g + β Nmᵀ P g ]`,
β = 10·E·p²/h. Das Verfahren ist konsistent (Patch-Test unabhängig von β, Tabelle oben); die
Normalprojektion liefert Symmetrie- und Gleitränder (einachsiger Zug mit drei Symmetrieebenen:
8·10⁻¹⁶). Flächenquadratur: Dreiecke der Grundformen an die Zellbox geclippt, lokale Stücke
clippen das Polygon gegen fremde Halbräume, Gauß auf Fächerdreiecken (exakt bis Gesamtgrad
2n−1 ≥ 3p, damit ∫(σ*n)·v exakt ist), Punkte auf die exakte Grundform projiziert, Gewichte mit
dem Flächenfaktor dA_wahr/dA_Facette (Zylinder R/ρ·n_f·e_r, Kugel (R/ρ)²·n_f·e_r): Bohrungsmantel
und Kugeloberfläche auf 10⁻⁸ bei Facette 0,5 h, Sechseck einer schrägen Schnittebene exakt.

### 11.6 Kopplung an Stabquerschnitte

Die ebene Querschnittskinematik eines Stabs enthält weder Querkontraktion noch
Schubverwölbung. Mit allen drei Komponenten punktweise vorgegeben ist die Schnittebene seitlich
gesperrt: am Stub-Kragarm des Vertrags (b 100, h 200, Segment x = 200…800) war das Moment um
53 % zu hoch. An Schnittebenen gilt darum: Normalkomponente punktweise über Nitsche (trägt
Biegung, Längskraft, Verwölbung), in der Ebene nur die drei Resultierenden – zwei Querkräfte
und die Torsion – als Mittelwertzwänge `∫(u − g)·m_k dA = 0` mit drei Lagrange-Multiplikatoren
je Ebene; λ·A ist die übertragene Zwangskraft (Kontrolle: 7512 N gegen 7625 N aus den
Spannungen). Reine Biegung mit dem exakten 3D-Feld (`u_x = −Mxz/EI`, `u_y = νMyz/EI`,
`u_z = M(x² + ν(z² − y²))/2EI`) bleibt exakt: Schnittmoment 5·10⁶ auf 10⁻⁶, Multiplikatoren 10⁻¹⁴.

Grenze der Verschiebungskopplung: Für ein schubweiches Segment mit Euler-Bernoulli-Endwerten
folgen andere Schnittgrößen als aus der Balkentheorie. Mit `M_y = −EI φ'`,
`Q_z = κGA (w' − φ)`, `dM_y/dx = Q_z` und den Endwerten φ(x0), φ(x1), w(x0), w(x1) des Stubs
liefert die Timoshenko-Rechnung (κ = 5/6, Φ = 12EI/(κGAl²) = 0,35 bei l = 3h) M = 2,77·10⁶ N·mm
und Q = 7426 N; die FCM ergibt 2,75·10⁶ (−0,9 %) und 7625 N (+2,7 %), der schubstarre Stub
2,00·10⁶ und 10000 N. Die Kopplungskontrolle im Ergebnis (`DetailResult.coupling_check`) weist
solche Abweichungen aus und warnt ab 5 %. Empfehlung: Schnittebenen mindestens vier bis fünf
Querschnittshöhen auseinander, sonst Kraftkopplung (Teilprojekt 5). Kraft und Moment haben seit B7 ein gemeinsames
Lastmaß als Bezug (11.17, Befund 1): max(Moment, Kraft mal √Schnittfläche).

### 11.7 Lamé-Zylinder und Kirsch-Platte

Viertel eines dickwandigen Zylinders (r_i 50, r_a 100, Dicke 20, Innendruck 100 N/mm²), ebener
Dehnungszustand über Normalen-Nitsche auf vier Symmetrieebenen, Druck über die Flächenquadratur
der Bohrung; Referenz `σ_r = k(1 − r_a²/r²)`, `σ_φ = k(1 + r_a²/r²)`, k = p r_i²/(r_a² − r_i²),
Gegenprobe Kesselformel `∫σ_φ dr = p r_i`. Auswertung auf einem Strahl bei 37° in halber Dicke
(Zahlen aus `packages/volumen3d/volumen3d/tests/test_lame.py`, Stand siehe dort):

| p, h = 10 | Tiefe der Tangentialebenen | σ_r (von p_i) | σ_φ | Freiheitsgrade (frei) | Zeit |
|---|---|---|---|---|---|
| 2 | 2 | 1,41 % | 0,95 % | 8961 (4431) | 36 s |
| 3 | 2 | 0,32 % | 0,03 % | 27768 (13296) | 50 s |
| 4 | 2 | 0,28 % | 0,09 % | 62991 (29643) | 149 s |
| 3 | 3 | 0,087 % | 0,06 % | 27768 (13296) | 256 s |
| 4 | 3 | 0,071 % | 0,07 % | 62991 (29643) | 636 s |

Die Abnahme der Vorgabe (< 1 % bei moderatem Aufwand) erfüllt p = 3, der Standard des Vertrags.
Von p = 3 auf p = 4 verbessert sich bei Tiefe 2 nichts mehr: Die Tangentialebenen der
Schnittzellen nähern die Zylinderflächen mit einem Fehler ~(Blattkante/R)² = (2,5/50)², und erst
Tiefe 3 senkt σ_r um den Faktor 3,6 (zweite Ordnung). Für hohe p braucht die gekrümmte Geometrie
also feinere Blätter oder – wirtschaftlicher – die Oktree-Verfeinerung an der Oberfläche
(Teilprojekt 2); der Standard bleibt Tiefe 2.
**Kirsch-Platte** (Viertel 400×200×10, Loch d 40, d/W 0,1, Zug 100 N/mm²; Referenz K_tg nach
Heywood 3,032 und Pilkey 3,023, Howland 3,03; 3D-Effekt in Plattenmitte bei t/d = 0,25 etwa
+1 %): p = 4, h = 10 (zwei Zellen je Lochradius), 378 675 Freiheitsgrade (194 895 frei),
52 s: K_tg in Plattenmitte 3,069 (+1,35 % gegen 3,028), an der Oberfläche 2,981.

**Schnittlagen-Robustheit (Vorgabe 13: Streuung < 1 %):** dasselbe Modell mit dem Wurzelgitter um
0 / 0,2 / 0,4 / 0,6 / 0,8 Zellen verschoben ergibt K_tg = 3,069 / 3,012 / 3,262 / 3,200 / 3,142,
Streuung **7,9 %** – die Abnahme ist mit dem gleichmäßigen Gitter bei h = r/2 **nicht erfüllt**.
Ursache ist nicht die Zellaggregation (p = 3: Schwelle 0,25 → 7,7 %, 0,10 → 5,6 %, 0,02 → 18,5 %
mit einem Ausreißer 3,75), sondern die Auflösung des Lochs: am freien Lochrand bleibt |σ_r| bis
0,15·σ₀ stehen (müsste 0 sein), und je nach Lage der Schnittzelle stammt der Randwert aus einem
eigenen schwach gestützten Polynom oder aus der Fortsetzung der Wurzelzelle. Mit h = 5 (vier
Zellen je Radius, p = 3, drei Lagen 0 / 0,4 / 0,8) sinkt die Streuung auf **1,42 %**
(K_tg 3,098 / 3,111 / 3,142) und |σ_r|/σ₀ am Rand auf 0,02…0,05 – etwa quadratisch mit der
Zellgröße; unter 1 % braucht es acht Zellen je Radius. Zwei Zellen je Radius reichen für einen
prüffähigen Kerbwert nicht; die Vorgabe sieht dafür die Verfeinerung an Bohrungen vor
(Abschnitt 4, Nutzervorgabe und Fehlerschätzer), die mit Teilprojekt 2 (Oktree, hängende
Freiheitsgrade) kommt. Bis dahin gilt für Kerbwerte: mindestens vier Zellen je Radius und eine
Konvergenzstudie je Lage; der Zähler `blaetter_unteraufgeloest` im Protokoll (Krümmungsradius
kleiner als fünf Blattkanten) weist unteraufgelöste Stellen aus. Mit der lokalen Verfeinerung
aus Teilprojekt 2 ist die Abnahme erfüllt (Abschnitt 11.8).

### 11.8 Teilprojekt 2: Oktree, hängende Freiheitsgrade, STL

**Oktree.** Das Wurzelgitter aus 11.1 bleibt; jede Wurzelzelle kann in Ebenen l = 1, 2, …
geviertelt werden (Blattkante h/2^l). Verfeinerungsregeln (`Verfeinerung`): Schnittzellen bis
Ebene `schnitt_ebenen`, Nutzerbereiche (Kugel um einen Punkt mit Zielkantenlänge, aus
`RefinementRegion` des Vertrags), dünne Wände (Zellen mit Werkstoff, deren Nachbarn beidseits
leer sind), Höchstebene. Nach jeder Regel wird auf 2:1 über alle 26 Nachbarrichtungen
balanciert, damit an keiner Fläche, Kante oder Ecke mehr als eine Ebene springt. Die
Modennummerierung bleibt entitätsbasiert; Ecken tragen ebenenfreie Schlüssel im feinsten
verdoppelten Gitter, sodass eine Ecke, die grobe und feine Zelle teilen, dieselbe Nummer
bekommt, während eine hängende Ecke (nur von feinen Zellen getragen) eine eigene erhält.
Kugel r 43 in h 10: gleichmäßig 549 Blätter; `schnitt_ebenen=1` 172 + 2145 Blätter, keine
Schnittzelle mehr auf Ebene 0, 0 Verstöße gegen 2:1; Bereich Radius 8 mit Ziel 2,6 mm → Ebene 2
im Bereich, Übergangsring Ebene 1, 0 Verstöße.

**Hängende Freiheitsgrade als Zwänge.** An einer hängenden Fläche (Kante, Ecke) sind die Moden
der feinen Seite keine eigenen Unbekannten: ihre Spur muss der Spur des groben Polynoms gleichen.
Der Zwangsauflöser (`fcm/zwaenge.py`) löst dazu je hängender Entität das kleine System
V_F·M = N_C (Werte der feinen Basis an Chebyshev-Lobatto-Punkten gegen die grobe Basis) und
schreibt jede gebundene Mode als Linearkombination der Moden der groben Zelle; Vorrang Fläche >
Kante > Ecke > Aggregation, Ketten werden bis zu freien Moden aufgelöst (Kettenlänge im
Protokoll). Die Zellaggregation aus 11.4 läuft durch dieselbe Matrix. Ihre Wurzeln sind nie
feiner als die aggregierte Zelle, und ein Mode, den mehrere schlechte Zellen teilen, gehört der
gröbsten von ihnen: sonst hängen die Moden der feineren Wurzel ihrerseits an der groben Zelle,
und die Kette wird zirkulär (im verfeinerten Patch-Test mit dünner Wand 53 Selbstbezüge mit
Koeffizient 1 und Rest bis 2,45, gemessen 27.09.2026). Mit beiden Regeln laufen alle Ketten
monoton zu gröberen Ebenen und können nicht zurückkehren; ein Selbstbezug ist seither ein
Fehler mit Ausnahme, und in allen Abnahmen sind es 0 bei Kettenlänge 2. Findet eine schlechte
Zelle keine Wurzel gleicher oder gröberer Ebene, obwohl feinere wohlgestellte Nachbarn da sind,
wird sie geteilt und das Gitter neu gebaut (`wurzel_teilungen` im Protokoll; bisher nie nötig). Die
Spurbindung reproduziert Polynome vom Grad p exakt (p = 1…3: 1,1e-16 … 4,4e-16), der Patch-Test
auf lokal verfeinerten Gittern (eine Ebene an einer Ecke, dünne Wand, Schnittanteil 10⁻⁶) hält
u und σ unter 10⁻⁶ – auch dort, wo hängende Kanten oder Ecken ohne hängende Fläche vorkommen
(Vorrangregel geprüft).

**Nahe Wurzeln und leere Zellen (28.09.2026).** Die Koeffizienten der Fortsetzung wachsen mit dem
Abstand zur Wurzel etwa wie Abstandᵖ. Beim Mehrgitter fiel auf, dass die reduzierte Matrix der
Kirsch-Scheibe Diagonalwerte bis 2,5·10²¹ hatte, bei einem Median von 1,4·10⁵; die Zellmatrizen
selbst reichten nur bis 2,5·10⁶, der Nitsche-Anteil bis 2,8·10⁷. Die Ursache lag in C: Koeffizienten
bis 3,5·10⁹ (h 8, Versatz 0,6), in allen Kirsch-Größen zwischen 5·10⁵ und 1,4·10⁸. Zellen ohne
wohlgestellten Nachbarn erbten die Wurzel eines Nachbarn, und zwar die mit dem größten Anteil, auch
wenn sie in derselben Runde gerade erst weitergereicht worden war. Dazu kamen leere Zellen im Loch
nahe der Symmetrieecke, 19 mm vom nächsten Werkstoff: die Abstandsfunktion der Mengenoperation ist
dort nur eine untere Schranke (0,6 mm), und die Klassifikation nannte sie geschnitten. Über sie lief
die Kette bis 38 Halbweiten weit, das Wurzelpolynom wurde über elf Zellen fortgesetzt. Regeln
seither: Ketten wachsen schichtweise aus den Wurzeln der Vorrunde, und die nächstgelegene Wurzel
gewinnt; leere Zellen, die keine Zelle mit Werkstoff berühren, bekommen keine Wurzel, und ihre Moden
werden null gesetzt, soweit sie keinen Werkstoffpunkt beeinflussen (von keiner Werkstoffzelle
getragen und kein Meister eines solchen hängenden Modes). Leere Zellen am Werkstoff bleiben in den
Ketten: ihre Moden sind Meister hängender Moden von Werkstoffzellen, und ohne Wurzel bekamen sie nur
deren Steifigkeit (Patch-Test dünne Wand p 3: Randspannung 2,8·10⁻⁶ statt 5,8·10⁻⁸). Gemessen an
sechs Kirsch-Größen von h 20 bis h 8: Wurzelabstand höchstens 4 Halbweiten, |C| höchstens 3,4·10⁴;
die Patch-Tests bleiben unter 10⁻⁶. Die Exaktheit linearer Felder auf der Kirsch-Geometrie selbst
war schon vorher nicht gegeben (σ-Fehler 10⁻³ bis 2,5·10⁻² nahe dem Loch, nach der Änderung 10⁻³
bis 6,6·10⁻³): Volumen- und Randquadratur nähern die gekrümmte Lochfläche verschieden an. Das ist
ein eigener, offener Punkt.

**Ränder auf Zellflächen.** Fällt eine Symmetrie- oder Schnittebene genau auf eine Zellfläche –
in der verfeinerten Kirsch-Platte bei Versatz 0,4 liegen x = 0 und y = 0 auf Flächen der Ebenen
1 und 2 –, wurden ihre Randpolygone beiden Nachbarzellen zugeschlagen: sym_x 2050 statt 1800 mm²,
sym_y 4050 statt 3800 mm², und K_tg stieg auf 3,63 (statt 3,08), weil die Nitsche-Terme an x = 0
doppelt und zusätzlich mit dem extrapolierten Polynom der leeren Nachbarzelle eingingen. Die
gleichmäßigen Gitter waren nur zufällig verschont (Ursprung −1 oder −5 bei h 10). Regel seither:
ein Polygon in einer Zellfläche gehört allein der Zelle auf der Werkstoffseite (Außennormale der
Geometrie zeigt aus ihr heraus); Prüfung mit Würfelflächen auf Zellflächen der Ebenen 0, 1 und 2
(600 mm² genau einmal, ohne die Regel 1200 mm²).

**Kirsch-Platte mit Bereichsverfeinerung (Abnahme U3).** Bereich Radius r + 10 mm um die Lochachse
mit Zielkante 2,5 mm (Ebene 2 = acht Blätter je Radius), sonst h = 10, p = 3, Versatz 0 / 0,4 /
0,8: K_tg = 3,085 / 3,076 / 3,074, Streuung **0,34 %** (Vorgabe < 1 %), Mittel 3,078 = +1,7 % gegen
3,028 (3D-Effekt +1 % enthalten); 199 095 freie Freiheitsgrade gegen 5 659 752 für ein
gleichmäßiges Gitter h = 2,5 (3,5 %), Blätter {0: 2704, 1: 101, 2: 595}, 206 hängende Flächen,
179 s für drei Lagen auf der durch die Hauptsitzung belegten Maschine. σ_xx/σ₀ über die Dicke am
Lochrand (d = 0,1 mm): 2,95 am Rand bis 3,04 in der Mitte, symmetrisch.

**STL-Eingang.** Vorzeichen des Abstands aus der verallgemeinerten Windungszahl (Jacobson u. a.
2013, Raumwinkel nach Van Oosterom/Strackee): geschlossener Würfel innen 1, außen 0, auf einer
Fläche ½, Kante ¼, Ecke ⅛; fehlt eine Facette (1/12 der Oberfläche), bleibt innen 11/12 und
außen 1/12 – die Klassifikation hält, ein Strahltest durch die Lücke nicht. Die Facetten werden
über gemeinsame Kanten einheitlich gewickelt (eine einzeln verkehrte Facette überdeckt mit ihrem
eigenen Raumwinkel ±½ jede Windungszahl-Probe an ihr selbst und wäre so nicht zu finden), jede
Zusammenhangskomponente über ihr Vorzeichenvolumen nach außen und Hohlraumschalen (ungerade
Verschachtelungstiefe) nach innen gerichtet; Prüfung: Würfel mit einer verkehrten Facette,
Hohlwürfel 30/10. Die größte Abweichung von w von 0/1 beidseits einer Stichprobe ist der
`defekt` (Würfel mit Lücke 0,097; die Vertragsschicht lehnt > ¼ ab und warnt ab 10⁻³). Lokal ist ein STL eben; die Facetten, die die
Umkugel einer Teilbox berühren, liefern die Ebenen, und ihre Ecken sagen, wie der Werkstoff
daraus entsteht: liegen alle auf der Werkstoffseite aller Ebenen, ist er der Schnitt der
Halbräume (konvex, wie bei den Grundformen); liegen alle auf der Leerseite, ist der Leerraum
der Schnitt der gespiegelten Ebenen und der Werkstoff ihre Vereinigung (konkav: Bohrungswand,
einspringende Kante – ohne diesen Fall fiel jede tessellierte Bohrungswand auf den Punkttest
zurück: Viertelring h 10 mit 6573 Punkttest-Blättern und 10,5 Mio. Randpunkten durch die
Vierteilung der Facetten); gemischt (Deckel trifft Bohrungswand) ist der Werkstoff der Schnitt
der Halbräume vom Schnitt-Typ (alle Ecken auf ihrer Werkstoffseite) mit der Vereinigung der
übrigen – an den Proben der Teilbox gegen das Vorzeichen des Abstands geprüft; scheitert das,
zerlegt eine binäre Raumteilung an den lokalen Ebenen (höchstens sechs) den Würfel um die
Teilbox in konvexe Zellen, deren Zeuge die Windungszahl klassifiziert, und erst danach kommt
der Punkttest. Die Raumteilung allein war zu teuer (Viertelring: 29 895 Aufrufe, 1010 s, weil
jedes Wandfacetten-Polygon mit r ≈ 10 mm beide Deckel berührt); mit der Schnitt/Vereinigungs-
Regel baut derselbe Viertelring (h 10, p 3) in 43,7 s mit 368 050 Randpunkten, 245 Blättern
und keinem Punkttest (belegte Maschine). Ergebnis: Würfel-STL 30³ gerade und um 30°/20° gedreht
in h 10 Volumen 27 000 auf 10⁻¹⁰, L-Körper mit einspringender Kante 12 000 mm³ auf 10⁻¹⁰,
jeweils ohne einen Punkttest. **Lamé aus dem tessellierten Viertelring** (Facette 1 mm, 1268
Facetten, geschnitten mit vier Symmetrie-Halbräumen, h 10, p 3): σ_r 0,066 %, σ_φ 0,022 %,
u_r 0,003 % gegen Lamé – genauer als die CSG-Rechnung (0,316 / 0,032 %), weil die Facetten
exakte Ebenen des STL-Körpers sind (Sagitta 0,0025 mm), während die CSG-Zylinderfläche bei
Tiefe 2 durch Tangentialebenen mit Fehler (2,5/50)² genähert wird; 1 188 116 Randpunkte (die
Deckel- und Seitenfacetten des STL liegen doppelt zu den Halbraum-Polygonen, ungenutzt), 119 s
mit Lösen auf der belegten Maschine. Kosten der Kernfunktionen: 1268 Facetten,
10 000 Punkte, belegte Maschine – volle Suche 6,9 s, Windungszahl numpy 5,4 s; mit BVH (Median-
Teilung, Boxabstand, numba) 0,001 s für die nächsten Punkte (identisch bis 3·10⁻¹⁴) und 0,011 s
für die Windungszahl (numba, identisch bis 10⁻¹²). Ohne numba bleibt ein k-d-Baum-Index über
Facettenschwerpunkte mit exakter Kugelschranke (Ergebnis gleich, nur 2,2-mal schneller als die
volle Suche, weil die Schranke eine Schale der Dicke 2 R_max durchlässt).

**Nachtrag (O15, 02.10.2026): Reihenfolgefehler in der 2:1-Balancierung.** `Gitter._aufbauen` wandte die Maske aus `_unbalanciert` – sie gilt für die von `_indizieren` sortierten Felder – auf die unsortierten lokalen Felder an und teilte damit andere Zellen als gemeint. Bei zwei Ebenen unter der Basiszelle hatte das keine Folge: 393 Gitter aus 26 Suiten verglichen (alte und neue Reihenfolge, Blattmengen aus `ebene` und `ijk` exakt): 391 gleich, 0 verschieden, 2 Kaskade im alten Verfahren – das ist der absichtlich gebaute Dreiebenenfall des neuen Tests (2 100 Blätter in 519 / 155 / 306 / 1 120), gebaut in `test_oktree` und `test_kern`; mit der Korrektur ändert sich kein Gitter der Suiten. Bei drei Ebenen entstanden Blätter über der Obergrenze und eine Kaskade ohne Ende (Kugel Radius 43, Bereich Radius 8 mit Ziel 1,3 mm: nach 40 Durchläufen Blätter der Ebenen 4 und 5 bei Obergrenze 3; Nahtziel t/8 am Knotenblech, 11.20). Jetzt werden die sortierten Felder geteilt, und eine Durchlaufgrenze von 2·`max_ebene` + 2 macht einen Rückfall zu einem `RuntimeError`: ein Durchlauf löst alle Verstöße, ein neuer entsteht nur an einem Nachbarn, der dem geteilten Blatt um zwei Ebenen nachhinkt, und die Kette läuft eine Ebene tiefer – gemessen 1 Durchlauf bei zwei, 2 bei drei Ebenen. Prüfung `test_oktree.test_verfeinerung_drei_ebenen` (Kernsuite): Kugel mit Ziel 2,6 mm (zwei Ebenen, 873 Blätter) und 1,3 mm (drei Ebenen, 2 100 Blätter in 519 / 155 / 306 / 1 120): der Aufbau endet, kein Blatt liegt über der Obergrenze, Überlappungen, Lücken und 2:1-Verstöße über 26 Richtungen je 0 – geprüft ohne die Methoden des Aufbaus über eine Abbildung der feinsten Teilzellen auf ihr Blatt; die Durchlaufgrenze schlägt bei einer nie endenden Balancierung an; mit der alten Reihenfolge schlägt der Test fehl (Kaskade nach 8 Durchläufen).

### 11.9 Teilprojekt 3: matrixfreier Operator und vorkonditioniertes CG

**Operator ohne globale Matrix.** Das Produkt v = K·u wird zellweise gebildet (Vorgabe 8.1).
INSIDE-Zellen einer Ebene sind bis auf den Maßstab gleich: K ∝ h, also K_e = h_l/h₀·K_ref mit
einer Referenz-Zellmatrix je p und Werkstoff (Tensor-Gauß (p+1)³ ist für Polynome vom Grad 2p
exakt und stimmt darum mit der Quadratur der INSIDE-Zellen überein). CUT-Zellen behalten ihre
Zellmatrix aus der Schnittzellen-Quadratur (Vorgabe 8.1 „optional“; Kirsch h 10 p 3 verfeinert:
2159 Schnittzellen, 637 MB). Eingesammelt wird nicht per Atomics oder Graphfärbung, sondern per
Gather: der Zellkern schreibt sein Ergebnis in einen Puffer (Zellen × 3m), eine vorab gebaute
Inzidenz Freiheitsgrad → (Zelle, lokaler Index) summiert je Freiheitsgrad parallel – kein
Wettlauf, auf CPU und GPU gleich. Zwänge (hängende Freiheitsgrade, Aggregation) bleiben die
Zwangsmatrix C, die Nitsche-Ränder die dünnbesetzte Matrix K_rand: A = Cᵀ(K + K_rand)C.
Gemessen (28.09.2026): Operator = assemblierte Matrix auf 10⁻¹⁵ (Kirsch verfeinert, Lamé, Patch
mit dünner Wand); Kirsch h 10 p 3 verfeinert mit 229 608 Freiheitsgraden 18,7 ms je Anwendung
(numba, Ziel < 200 ms), Zelldaten in 10,7 s. Die Summenfaktorisierung für INSIDE-Zellen ist
zurückgestellt: sie stellen dort unter 10 % der Zellen.

**PCG.** Vorkonditioniertes CG in FP64 mit relativer Residuumsschranke und Energienorm der
letzten Korrektur (für x₀ = 0 ist ‖x_k‖²_A = Σ α_j r_jᵀz_j, die Energienorm läuft ohne weitere
Operatoranwendung mit); Jacobi mit der exakten Diagonale von A aus den Zellmatrizen
(C_eᵀK_eC_e je Zelle). Die drei Mittelwertzwänge je Schnittebene (Projektion `schnitt`, bisher
Sattelpunkt) laufen als projizierter CG: x = x_p + z mit x_p = Bᵀ(BBᵀ)⁻¹d und z im Kern von B,
Operator und Vorkonditionierer mit P = I − Bᵀ(BBᵀ)⁻¹B projiziert; die Multiplikatoren folgen aus
λ = (BBᵀ)⁻¹B(b − Ax) und stimmen mit denen des Sattelpunkts überein (Kragarmsegment: 548
Iterationen, Verschiebungen auf 2·10⁻⁷).

**Kondition – die Messlatte für das Mehrgitter.** Die Jacobi-vorkonditionierte Matrix
D^−½AD^−½ hat Kondition 1,45·10⁶ (Patch h 20 p 2, 2469 freie Freiheitsgrade) und 5,0·10⁷ (Lamé
h 20 p 3, 2316); A selbst 1,9·10⁷ bzw. 3,8·10⁹, die Diagonale spannt 3,7·10² bzw. 3,3·10⁴
(Nitsche-Strafterm β = 10·E·p²/h auf den Randmoden). PCG braucht bis 10⁻¹⁰ 5 045 bzw. 20 373
Iterationen (Kirsch h 20 p 2 verfeinert 4 420) und trifft die direkte Lösung in den Spannungen
auf 2·10⁻⁶, 2·10⁻⁹ und 3·10⁻⁹; in den Verschiebungen weichen Kirsch-Lösungen um einen freien
Starrkörperanteil ab (u_z ist dort nicht gehalten, beide Löser wählen ihn verschieden – ein
Hinweis für die Vertragsschicht, nicht für den Löser). Die kleinsten Eigenvektoren verteilen
sich über wenige Moden schwach gestützter Schnittzellen und Moden hoher Ordnung; genau das ist
das Ziel von p-Mehrgitter und Chebyshev-Jacobi-Glätter in Teilprojekt 4 (Vorgabe 8.3, Richtwert
unter 100 Iterationen). Bis dahin bleibt der Direktlöser der Standard; `FcmProblem(loeser="pcg")`
ist geprüft und liefert Protokoll mit Iterationen und Residuum.

**GPU.** Dieselben Zelldaten laufen als CuPy-RawKernel: ein Block je Zelle lädt u_e in den
gemeinsamen Speicher, jeder Thread bildet eine Zeile von K_e·u_e und liest K_e dabei spaltenweise
(K_e ist symmetrisch, so sind die Zugriffe der Threads zusammenhängend); das Einsammeln je
Freiheitsgrad ist der zweite Kern; C und K_rand liegen als cupyx-CSR, der CG-Code ist für numpy
und cupy derselbe. Gemessen auf der RTX 3070 in FP64 (28.09.2026): GPU-Operator = Matrix auf
10⁻¹⁵; Kirsch h 10 p 3 verfeinert (229 608 Freiheitsgrade) 3,1 ms je Anwendung gegen 18,8 ms auf
der CPU bei 652 MB GPU-Speicher; kleine Modelle (6 069 Freiheitsgrade) 0,05 gegen 0,17 ms, ganz
kleine (14 961, viele Schnittzellen) 0,63 gegen 0,22 ms. Die PCG-Lösung auf der GPU ist mit der
CPU identisch (5·10⁻¹²), braucht bei 2 316 freien Freiheitsgraden aber 6,8 s gegen 0,1 s, weil je
Iteration mehrere Kernstarts und dünnbesetzte Produkte mit festen Startkosten anfallen – die
GPU lohnt sich ab Modellen mit einigen 10⁵ Freiheitsgraden, und erst mit dem Mehrgitter aus
Teilprojekt 4 sinkt die Iterationszahl so weit, dass die Startkosten nicht mehr zählen.

**Lasten am Detail (Vertrag 2.1.0, 28.09.2026).** `DetailModelSpec.loads` sind Flächenlasten
je Lastfall-ID: die Fläche wählt ein `SurfaceSelector` (benannte CSG-Grundform, Box oder
Zylinder mit 2 % Radiustoleranz) unter den Quadraturpunkten der Oberfläche, die Traktion ist
Druck (t = −p·n), globale Traktion oder eine Resultierende. Die Resultierende wird verteilt als
konstante Traktion F/A für die Kraft und als lineares Feld ω × (P − c) für das Moment mit
ω = (tr J·I − J)⁻¹·M und J = ∫(P − c)(P − c)ᵀ dA um den Flächenschwerpunkt c; so gilt
∫ t dA = F und ∫ (P − c) × t dA = M, und keiner der beiden Anteile erzeugt die jeweils andere
Größe. Eine Last wirkt nur auf Ergebnisschlüssel mit derselben `load_case_id`; `body_load` (N/mm³)
wirkt auf alle. Das Protokoll nennt je Last Fläche, Schwerpunkt, Kraft und Moment aus der
Quadratur. Prüfung am Kragarmsegment: Druck über eine Box auf der Oberseite (60 000 mm² auf
10⁻⁶, Resultierende exakt), Resultierende mit Moment auf der benannten Fläche (F und M um den
Schwerpunkt auf 10⁻⁹), Eigengewicht. Gegen die Schnittkräfte der Kopplungskontrolle stimmt das
Gleichgewicht nur auf 5 %, weil ∫σ·n dA den Strafanteil des Nitsche-Randes nicht enthält
(Abschnitt 11.6); eine Box zur Flächenauswahl ist dünn zu halten, da sie Quadraturpunkte wählt
(0,1 mm Dicke griff 34 mm² der Seitenflächen mit, 0,001 mm nichts).

### 11.10 Teilprojekt 4: p-Mehrgitter mit Zellblock-Glätter

**Schachtelung statt Interpolation.** Die hierarchische Basis (11.1) enthält den Raum vom Grad
p−1 als die Moden mit 1D-Indizes ≤ p−1. Der Übergang zwischen den Polynomgraden ist darum eine
Injektion (Auswahl von Moden), der Galerkin-Grobgitteroperator der Teilblock der Zellmatrizen aus
11.9 (keine neue Integration), und die Zwänge aus 11.8 sind geschachtelt: die Spur eines
Polynoms vom Grad d auf einer hängenden Fläche und seine Fortsetzung in eine aggregierte Zelle
haben wieder Grad d, ein Meister vom Grad d bindet also nur Sklaven vom Grad ≤ d. Deshalb sind
die freien groben Moden eine Teilmenge der freien feinen, P̃ ist die Injektion zwischen den
freien Koordinaten und A_grob = P̃ᵀ A_fein P̃ gilt exakt; gemessen 0 bis 3·10⁻¹⁶ (Patch mit dünner
Wand, Kragarmsegment, Lamé, Kirsch verfeinert). Das Grobgitter p = 1 (Eckmoden) löst der
Direktlöser; die Mittelwertzwänge der Schnittebenen werden auf jede Ebene injiziert und dort als
Sattelpunkt mitgeführt, sonst ist A am Grobgitter singulär (Starrkörper in der Ebene) und der
Direktlöser liefert Zahlen um 10¹².

**Warum Jacobi als Glätter nicht reicht.** Mit Chebyshev-Jacobi (Grad 3, Spektrum
[λ_max/8, λ_max]) reduziert ein V-Zyklus das Residuum zwar um den Faktor 0,03 bis 0,08, der PCG
brauchte aber 637 (Kirsch h 20 p 2) bis über 2000 Iterationen. Das explizite Spektrum von M⁻¹A am
Patch h 20 p 2 (2469 freie Koordinaten) zeigt 210 Eigenwerte unter 0,01, die kleinsten bei 10⁻⁵;
ihre Eigenvektoren sitzen auf Moden, die nur zu Schnittzellen mit Werkstoffanteil ≈ 0 gehören und
auf dem Nitsche-Rand liegen (die Zellen selbst sind wohlgestellt, der Anteil nahe der geteilten
Fläche ist es nicht). Solche lokalen Cluster erreicht kein Punkt-Glätter (α = 30 oder Grad 6:
min 1,9·10⁻⁵ bzw. 2,4·10⁻⁵) und kein Grobgitter aus Eckmoden.

**Zellblock-Schwarz.** Die Vorgabe 8.3 nennt als zweite Gegenmaßnahme den additiven Schwarz-
Glätter mit Patches um schwach gestützte Freiheitsgrade. Hier wird je Zelle der Block A[S,S] der
freien Koordinaten, die die Zelle berührt, exakt invertiert (aus der nur hierfür assemblierten
Matrix je Ebene); die Überlappung regelt keine Dämpfung, sondern die Chebyshev-Beschleunigung um
den Glätter mit λ_max von M_AS·A aus der Potenzmethode. Damit fallen die lokalen Cluster aus dem
Spektrum, und der PCG braucht (28.09.2026, bis 10⁻¹⁰, Spannungen wie der Direktlöser auf
10⁻⁹…10⁻¹⁰): Patch h 20 p 2 **29** Iterationen (Jacobi 5 045), Kragarmsegment p 3 mit
Schnittebenen **53** (2 580), Lamé h 20 p 3 **26** (20 373), Kirsch h 20 p 2 verfeinert **38**
(4 420), Kirsch h 20 p 3 verfeinert **43** (über 40 000). Der Richtwert der Vorgabe (unter 100)
ist erfüllt, und die Iterationszahl hängt kaum von p und Verfeinerung ab.

**Einrichten, Grobgitter und Robustheit (28.09.2026, nach Gutachten).** Das Profil der ersten
Fassung am Kirsch-Modell h 10 p 3 (130 611 freie Koordinaten) zeigte 90 von 147 s Einrichtzeit in
4 732 einzelnen LAPACK-Inversionen der Zellblöcke. Eine parallele Inversion über numba mit
LAPACK-Aufrufen aus 32 Threads überschrieb Speicher (OpenBLAS ist für so viele gleichzeitige
Aufrufer nicht gebaut); die Blöcke werden darum mit einer eigenen Cholesky-Inversion in numba
invertiert (A = LLᵀ, A⁻¹ = L⁻ᵀL⁻¹, exakt symmetrisch): 2 000 Blöcke der Größe 192 in 0,55 s statt
42 s, Abweichung 3·10⁻¹⁵. Die groben Zwänge werden nicht mehr je Ebene neu gebaut, sondern aus den
feinen abgeleitet (C_grob = P₃ᵀ C_fein P̃, Schachtelung beim Aufbau geprüft, gegen unabhängig
gebaute Zwänge auf 10⁻¹³ gleich). Bei Schnittlage 0,2 stagnierte die erste Fassung (500
Iterationen ohne Konvergenz): das Kirsch-Modell hat eine freie z-Verschiebung, das Grobgitter
p = 1 ist singulär, und Pardiso störte die Pivots still, sodass die Grobkorrektur Nullraumanteile
der Größe 1/Pivot bekam. Seither wird das Grobgitter um δ = 10⁻¹⁰·max diag verschoben (der
Nullraumanteil bleibt r₀/δ, r₀ ist für konsistente Systeme Rundung) und eine Zufallsprobe meldet
die Singularität im Protokoll. Fünf Schnittlagen (Kirsch h 20 p 3 verfeinert, 26 400 bis 33 060
freie Koordinaten): 43 / 53 / 58 / 47 / 39 Iterationen, Einrichten 4,9 bis 12,8 s, K_t identisch
mit dem Direktlöser. Der V-Zyklus ist symmetrisch auf 2·10⁻⁹ (Grenze der LU-Lösung am
Grobgitter) und positiv (kleinster Rayleigh-Quotient 7·10⁻⁵).

**CPU gegen Direktlöser.** Bei 30 000 freien Koordinaten löst der Direktlöser in 1 bis 2 s, der
PCG mit V-Zyklus braucht 10 bis 25 s. Der Grund ist die Speicherbandbreite: die Blockinversen
belegen 150 bis 325 MB und werden je V-Zyklus zwölfmal gelesen (je drei Chebyshev-Schritte vor und
nach der Grobkorrektur auf zwei Ebenen). Auf der CPU bleibt der Direktlöser darum Standard; das
Mehrgitter ist für die Grafikkarte gebaut (Vorgabe 9, 448 GB/s auf der RTX 3070 gegen rund
20 GB/s), und die Blöcke dürfen dort in FP32 liegen (gemischte Genauigkeit im Glätter, Vorgabe 9).
`FcmProblem(loeser="mehrgitter")` ist geprüft: Kragarmsegment p 3 mit Zug und mit reiner
Verdrehung ohne Last, je 54 Iterationen, Verschiebungen und Multiplikatoren wie der Sattelpunkt
auf 10⁻⁶.

**V-Zyklus auf der GPU und singuläre Modelle (28.09.2026).** Das eingerichtete CPU-Mehrgitter
wird auf die Grafikkarte gespiegelt: Operator je Ebene als CuPy-Kern (11.9), Schwarz-Blöcke je
Größe gestapelt (gebündelte Matrixprodukte, Scatter-Add), Injektionen als cupyx-CSR, Chebyshev in
cupy; das Grobgitter p = 1 bleibt auf der CPU (eine Übertragung hin und zurück je Zyklus). Der
GPU-Zyklus stimmt in FP64 mit der CPU auf 1,4·10⁻⁹ überein (Summationsreihenfolge). Blöcke in FP32
(Vorgabe 9 erlaubt es für Glätter) divergieren bei h 10: die Blockinversen haben Konditionen bis
10⁸, und die Rundung auf 6·10⁻⁸ macht ihre kleinsten Eigenwerte negativ – der Glätter bleibt FP64.
Beim Kirsch-Modell h 10 p 3 (130 611 freie Koordinaten) sprang das Residuum nach 10⁻⁸ wieder auf
10⁻⁶, und die Iterationszahl schwankte zwischen 147 und 243 je nach Einstellung und Summations-
reihenfolge. Ursache ist die freie z-Verschiebung dieses Modells (nur Normalen-Nitsche auf den
Symmetrieebenen): der Vorkonditionierer blähte den Nullraumanteil auf, der über Rundung ins
Residuum zurückwirkte; weder eine schärfere λ_max-Schätzung (60 Potenzschritte: 151, Sicherheit
1,5: 243) noch eine andere Grobgitterverschiebung (10⁻¹³: 159, 10⁻⁷: 174) halfen. Der Nullraum wird
darum am Grobgitter per zweifacher inverser Iteration aus sechs Zufallsproben bestimmt, auf die
feinste Ebene injiziert, dort am Operator bestätigt (‖A n‖ < 10⁻⁶ des Bezugs; ein nur fast
singulärer echter Modus darf nicht wegfallen) und vor und nach dem V-Zyklus symmetrisch
herausprojiziert (z = Π M Π r). Damit: 81 Iterationen, in der Iterationszahl reproduzierbar (die GPU
summiert Blockbeiträge mit atomaren Additionen, die Zahlen selbst sind nicht bitgleich), das Residuum fällt
gleichmäßig. Entschieden wird über die Singulärwerte des Probenblocks nach den zwei Schritten: ein
Nullvektor n bleibt dabei unverändert stehen (R₂ ≈ n nᵀX, Singulärwert ≈ √χ²₆, unter 0,1 mit
Wahrscheinlichkeit 2·10⁻⁸), jeder andere Modus schrumpft um (δ/λ)². Gemessen am Kirsch-Modell p 3,
h 10 bis 14: Nullvektor 2,4 bis 3,8, zweitgrößter Wert 5·10⁻⁶ bis 4·10⁻⁴; die Schwelle liegt bei
0,1. Die erste Fassung entschied über das Residuum einer einzelnen Probe (> 10⁻³). Das ist der
Nullanteil eines Zufallsvektors, |nᵀx|/‖x‖ ≈ 1/√N₁, und fällt mit der Größe des Grobgitters: bei
h 12 und h 14 (Versatz 0) lag er bei 9,8·10⁻⁴ und 8,5·10⁻⁴, der Nullraum blieb unerkannt, das
Residuum fiel bis 1,6·10⁻⁸ und wuchs danach exponentiell, bis der CG mit pᵀAp < 0 abbrach (h 12)
bzw. erst nach 113 Iterationen zufällig konvergierte (h 14). Eine Prüfung an einer Laplace-Kette
mit 20 000 Unbekannten, deren erste Probe senkrecht zum Nullraum liegt, hält das fest; die gelagerte
Kette (kleinster Eigenwert 6·10⁻⁹, also fast singulär) bleibt mit 3·10⁻³ klar unter der Schwelle. Gelagerte Modelle (Patch, Kragarm mit Schnittebenen – über die Vertragsschicht immer
der Fall) haben keinen Nullraum; das Protokoll meldet die Bewegung mit Warnung. Zeiten Kirsch h 10
p 3 bei belasteter Maschine: GPU-PCG 9 bis 11 s gegen 37 s Direktlöser; das Einrichten auf der CPU
(Zelldaten, Blöcke, Grobgitter) kostet 30 bis 35 s und wird von allen Lastfällen eines Details
geteilt. Kirsch h 20 p 3 (33 060 frei): GPU 3,8 s gegen CPU-Mehrgitter 12,1 s und Direktlöser 6,0 s.
Über fünf Schnittlagen bei h 10 (128 724 bis 199 095 freie Koordinaten) brauchte der GPU-PCG mit
Chebyshev-Grad 3 auf [λ_max/8, λ_max] 81 / 125 / 112 / 129 / 59 Iterationen. Am schwierigsten Fall
(Versatz 0,6) gemessen: Grad 3/α 8 129 Iterationen in 14,6 s, Grad 5/α 8 92 in 16,7 s, Grad 5/α 16
86 in 15,0 s, Grad 8/α 30 58 in 16,4 s – die Zeit hängt kaum am Grad, die Iterationszahl schon.
Standard war danach Grad 5 auf [λ_max/16, λ_max] (seit 30.09.2026 [λ_max/100, λ_max], siehe unten); damit: 51 / 82 / 72 / 86 / 49 Iterationen, alle
unter dem Richtwert 100 der Vorgabe, GPU-PCG 7,7 bis 16,9 s gegen 9 bis 30 s für das Lösen des
Direktlösers nach seiner Faktorisierung, K_t jeweils identisch; bei h 20 p 3 19 bis 37 Iterationen.
Offen bleibt das Einrichten auf der CPU. Nach der Entdopplung (Matrix aus den Zelldaten, feine
Matrix und Diagonale wiederverwendet), einem Tensorprodukt der Basis per Broadcasting und einem
parallelen Blockauszug kostet das Mehrgitter-Einrichten bei Kirsch h 10 p 3 rund 13 s. Im selben
Prozess gemessen (Aufbau + Lösen, Maschine belegt): Versatz 0 Direktlöser 25,5 s gegen Mehrgitter
auf der GPU 42,1 s (51 Iterationen), Versatz 0,6 53,7 s gegen 57,6 s (86 Iterationen). Das Lösen ist
auf der GPU schneller (8,8 gegen 10,0 s und 21,6 gegen 28,1 s), der Gesamtweg noch nicht; darum
bleibt der Direktlöser Standard der Vertragsschicht, bis das Einrichten auf die GPU wandert.

**Einrichten auf der GPU und automatische Wahl (28.09.2026).** Weil die Zwänge geschachtelt sind und
P̃ nur Koordinaten auswählt, ist die grobe Matrix eine Teilmatrix der feinen: A_grob = A_fein[S, S]
mit S den ausgewählten Koordinaten (gegen C_kᵀ K_k C_k aus den Teilblöcken der Zellmatrizen auf
10⁻¹² geprüft). Die groben Ebenen werden darum nicht mehr assembliert, und die Jacobi-Diagonale ist
die Diagonale dieser Matrizen. Mit `geraet="gpu"` werden die Glätterblöcke per RawKernel aus der
feinen Matrix auf der GPU ausgezogen, mit cuBLAS gestapelt invertiert und bleiben dort; λ_max, die
groben Operatoren (cuSPARSE) und der V-Zyklus laufen ebenfalls auf der GPU, nur das Grobgitter p = 1
auf der CPU. Das auf der GPU eingerichtete Mehrgitter stimmt mit dem CPU-Mehrgitter auf 2·10⁻¹⁰
überein. Das Einrichten kostet bei Kirsch h 10 p 3 nun 4 s statt 13 s.

Beim Messen der Umschaltschwelle kamen drei Fehler zutage, die vorher behoben werden mussten: die
Nullraumerkennung hing an der Modellgröße (oben), die Aggregation setzte Wurzeln bis 38 Halbweiten
entfernt fort (11.4) und verdarb damit die Kondition, und der GPU-Speicher lief über. Nach den beiden
ersten Korrekturen braucht das Mehrgitter bei der Kirsch-Scheibe 23 bis 43 Iterationen statt 51 bis
125, auch der Direktlöser wurde schneller (h 10, Versatz 0,6: 20,8 statt 37,2 s). Zum Speicher: die
Glätterblöcke wurden je Größengruppe auf einmal ausgezogen und invertiert, die Arbeitskopien der
gestapelten Inversion und die Symmetrisierung ließen den Speicherpool auf das Doppelte der Blöcke
wachsen (Kirsch h 9: 5,9 GB gehalten, 2,9 GB belegt), und mehrere Modelle in einem Prozess sammelten
sich im Pool, bis die 8-GB-Karte auslagerte (1,5 statt 0,13 s je Iteration). Seither laufen Auszug
und Inversion in Teilstapeln von höchstens 256 MB, und der Pool wird nach dem Einrichten freigegeben;
Spitze und Belegung stehen in der Statistik. Die Schätzung der Vertragsschicht lag bis 50 % unter der
Spitze und zählt jetzt die Zellmatrizen der Schnittzellen, die Glätterblöcke (mittlere Blockgröße
1,1·3(p+1)³), die feine Matrix während des Auszugs samt grober Matrix (360 Einträge je freier
Koordinate) und 700 MB Arbeitsfelder; an acht Fällen von 1,4 bis 5,3 GB liegt sie 2 bis 10 % über
der gemessenen Spitze, gewählt wird mit 20 % Reserve gegen den freien Speicher.

Gesamtweg (Aufbau + Lösen) auf freier Maschine, je Fall ein eigener Prozess (Commit d669b9f); die
Scheibe ist nur ein bis zwei Zellen dick und damit für den Direktlöser günstig, der Block mit Bohrung
(200 mm Würfel, r 40) ist ein kompakter Körper:

| Modell | Freiheitsgrade | Direktlöser | Mehrgitter GPU | Iterationen |
|---|---|---|---|---|
| Block h 25, Versatz 0 / 0,3 | 65 040 / 65 616 | 16,6 / 15,4 s | 19,0 / 16,9 s | 50 / 26 |
| Block h 20 | 116 187 / 115 728 | 20,6 / 22,4 s | 22,7 / **21,1** s | 26 / 22 |
| Block h 16 | 185 856 / 232 296 | 39,0 / 39,7 s | **33,7** / **39,2** s | 22 / 27 |
| Block h 14 | 281 292 / 340 476 | 57,5 / 61,1 s | **41,7** / **52,5** s | 22 / 26 |
| Kirsch h 14, Versatz 0 / 0,3 / 0,6 | 81 183 – 135 327 | 7,7 / 8,3 / 9,7 s | 9,6 / 10,7 / 12,4 s | 23 / 24 / 31 |
| Kirsch h 12 | 165 501 – 173 862 | 10,5 / 11,3 / 13,1 s | 13,6 / 14,9 / 14,3 s | 24 / 23 / 29 |
| Kirsch h 10 | 229 608 – 330 705 | 15,6 / 19,3 / 20,8 s | 17,9 / **18,4** / 21,4 s | 23 / 29 / 26 |
| Kirsch h 9 | 283 896 – 390 018 | 20,0 / 25,9 / 25,4 s | 22,2 / **25,2** / **25,2** s | 24 / 43 / 31 |
| Kirsch h 8 | 360 204 – 497 244 | 30,8 / 34,6 / 33,5 s | **26,1** / 42,3 / **33,3** s | 35 / 114 / 26 |

Das Lösen selbst ist auf der GPU beim Block ab 116 000 Freiheitsgraden 1,9- bis 9,4-mal schneller, bei
der Scheibe erst ab 230 000 Freiheitsgraden 1,6- bis 2,8-mal (bis 174 000 etwa gleich schnell); den
Abstand im Gesamtweg macht das Einrichten des iterativen Wegs (Zellmatrizen, Matrix, Blöcke), das 2 bis
12 s länger dauert als Assemblieren und Faktorisieren beim Direktlöser. Beim Block wächst der Vorsprung des
Mehrgitters mit der Größe (281 000 Freiheitsgrade: 16 s), bei der Scheibe liegen beide ab 230 000
gleichauf. Ein Ausreißer ist Kirsch h 8, Versatz 0,3 mit 114 Iterationen (unten behoben). Auf diesem
Stand wählte die Vertragsschicht mit `FcmSettings.backend = "auto"` das Mehrgitter auf der GPU ab 200 000
Freiheitsgraden; über alle 23 Fälle verschenkte diese Schwelle 19 s gegen die jeweils bessere Wahl. Die
Schlussmessung nach den Korrekturen unten hat die Wahl umgedreht. Nach oben begrenzt der Speicher der Karte
das Mehrgitter (8 GB: etwa 500 000 Freiheitsgrade bei p 3).
`"gpu"` erzwingt das Mehrgitter und fällt ohne GPU oder bei zu wenig Speicher mit Warnung auf den
Direktlöser zurück (Vorgabe 9), `"cpu"` rechnet immer direkt; das Mehrgitter auf der CPU ist in allen
Messungen langsamer als der Direktlöser und wird nicht gewählt. Die Vertragstoleranz (relatives
Residuum) wird für das Mehrgitter auf 10⁻¹² geschärft, damit die Verschiebungen den Direktlöser auf
10⁻⁶ treffen (Vorgabe 9): gemessen auf dem endgültigen Stand (Aggregationsschwelle 0,4) am Kragarm-
Ausschnitt über die Vertragsschicht (h 25 und 16) und am eingespannten Block (h 25 und 20) weichen sie bei
10⁻¹⁰ um 1,5·10⁻¹⁰ bis 1,7·10⁻⁸ ab, bei 10⁻¹² um 7,6·10⁻¹³ bis 9,7·10⁻¹¹, das Lösen dauert 19 bis 29 %
länger. Vor der Aggregationskorrektur lagen sie bei 10⁻¹⁰ bis 4,3·10⁻⁶ daneben. Die Spannungen stimmen in allen 23 Fällen der Tabelle auf die angegebenen
Stellen überein. Protokoll und `summary()` nennen den gewählten Weg und die Begründung.

**Zweite Sicht über Teilprojekt 3 und 4 (28.09.2026 abends).** Ein unabhängiges Gutachten fand keinen
falsch gebauten Kern, aber Lücken, die seither geschlossen sind. Die Nullraumerkennung war mit
Schnittebenen abgeschaltet, im Vertragsweg also nie aktiv; ein zweiter, von keiner Ebene berührter
Körper wäre ohne Projektion und ohne Warnung geblieben. Sie läuft jetzt immer: der Sattelpunktlöser
des Grobgitters trifft eine von den Mittelwertzwängen gesperrte Bewegung exakt und filtert sie so
heraus, bestätigt werden nur Vektoren mit A q ≈ 0 und B q ≈ 0 (dann vertauschen die Projektionen des
CG und des V-Zyklus). Sechs Zufallsproben reichten für mehrere freie Bewegungen nicht: die
Singulärwerte der Nullvektoren sind die einer k × m-Gaußmatrix, und bei sechs freien Bewegungen ging
mit sechs Proben in drei von zehn Zufallsständen einer verloren; mit sechzehn Proben in keinem.
Fehler der GPU außer Speichermangel (fehlendes NVRTC in der gepackten exe, cuBLAS, Treiber) führten
zum Abbruch statt zum Rückfall. Die GPU gilt jetzt erst als verfügbar, wenn eine Kleinrechnung samt
RawModule-Kompilat läuft, und jeder Fehler des GPU-Wegs beim Aufbau oder Lösen fällt mit Warnung auf
den Direktlöser zurück; die Felder des gescheiterten Versuchs werden vorher freigegeben, der Pool auch
nach einem Fehler. NaN aus einem singulären Block wurde weder bei der Inversion noch im CG erkannt
(Vergleiche mit NaN sind falsch; der CG wäre 1000 V-Zyklen gelaufen); beides bricht jetzt sofort mit
Meldung ab. Eine Last mit Anteil in Richtung einer freien Bewegung wird vor dem CG gemeldet („Last
nicht im Gleichgewicht“). `"auto"` wählt das Mehrgitter nur bei p = 3, dem gemessenen Grad: bei p = 1
gibt es nur eine Ebene, und p = 2 und 4 sind weder für die Schwelle noch für den Speicher gemessen; die
Speicherschätzung setzt die Einträge je Zeile nach p an und zählt alle Glätterebenen.

**Aggregationsschwelle 0,4 (28.09.2026 abends).** Der Ausreißer Kirsch h 8, Versatz 0,3 mit 109 bis 114
Iterationen ließ sich an den Ritz-Werten des vorkonditionierten Operators festmachen: rund acht
Eigenwerte zwischen 0,002 und 0,016, alle anderen über 0,03 (Kondition 559). Ihre Eigenvektoren
sitzen auf rund 400 freien Moden am belasteten Plattenende, in Zellen mit Werkstoffanteil 0,26, also
knapp über der Schwelle 0,25 und damit wohlgestellt; ihre hohen Moden tragen aber nur etwa
Anteil^(2p+1) ihrer Energie im Werkstoff und teilen sich die Nachbarschaft mit leeren Zellen. Mit der
Schwelle 0,4 (Plan TP 4, Aufgabe 3) werden solche Zellen aggregiert (GPU-Mehrgitter, CG bis zum relativen
Residuum 10⁻¹⁰):

| Kirsch p 3 | Schwelle 0,25 | Schwelle 0,4 |
|---|---|---|
| h 8, Versatz 0,3: Iterationen / Kondition / Lösen | 109 / 559 / 15,7 s | 40 / 42 / 5,7 s |
| h 8, Versatz 0,3: K_tg | 3,0735 | 3,0744 |
| h 10, Versatz 0 / 0,2 / 0,4 / 0,6 / 0,8: Iterationen | 22 / 27 / 36 / 25 / 24 | 22 / 22 / 31 / 22 / 24 |
| h 10: K_tg (Referenz 3,028) | 3,0849 / 3,0837 / 3,0760 / 3,0740 / 3,0744 | 3,0798 / 3,0837 / 3,0760 / 3,0744 / 3,0744 |

Die Genauigkeit bleibt (K_tg gleich oder bis 0,17 % näher an der Referenz), die Patch-Tests bleiben
unter 10⁻⁶; die freien Koordinaten nehmen ab (h 10, Versatz 0,2: 122 430 statt 184 809). Die Forderung
des Plans, dass die Iterationen über fünf Schnittlagen um höchstens 20 % streuen, erfüllt auch 0,4 nicht
ganz (31 gegen im Mittel 24, +28 %); vorher waren es +34 %.

**Schlussmessung auf dem endgültigen Stand (Commit c4694d6, 29.09.2026).** Mit der Schwelle 0,4 und der
Toleranz 10⁻¹² dieselben 23 Fälle, freie Maschine, je Fall ein Prozess:

| Modell | Freiheitsgrade | Direktlöser | Mehrgitter GPU | Iterationen |
|---|---|---|---|---|
| Block h 25, Versatz 0 / 0,3 | 65 040 / 65 616 | 14,5 / 15,2 s | 17,8 / 17,6 s | 45 / 28 |
| Block h 20 | 116 187 / 115 728 | 20,6 / 22,3 s | 23,0 / 22,8 s | 32 / 28 |
| Block h 16 | 185 856 / 232 296 | 38,8 / 38,5 s | **33,4** / 40,2 s | 27 / 33 |
| Block h 14 | 281 292 / 340 476 | 49,4 / 61,0 s | **44,4** / 61,8 s | 33 / 32 |
| Kirsch h 14, Versatz 0 / 0,3 / 0,6 | 81 183 – 135 327 | 7,4 / 8,1 / 8,3 s | 11,8 / 11,4 / 12,1 s | 33 / 29 / 32 |
| Kirsch h 12 | 165 501 – 173 862 | 10,4 / 11,0 / 11,3 s | 15,9 / 16,2 / 13,4 s | 31 / 33 / 28 |
| Kirsch h 10 | 229 608 – 330 705 | 15,6 / 18,9 / 17,4 s | 17,7 / 19,5 / 23,1 s | 29 / 38 / 30 |
| Kirsch h 9 | 283 896 – 390 018 | 19,4 / 24,3 / 20,8 s | 21,8 / **23,4** / 23,9 s | 31 / 41 / 35 |
| Kirsch h 8 | 360 204 – 497 244 | 26,0 / 32,2 / 27,6 s | 27,5 / 33,4 / 31,7 s | 43 / 55 / 29 |

Die Schwelle 0,4 nimmt vor allem dem Direktlöser Arbeit ab: sie senkt die Zahl der freien Koordinaten
(Kirsch h 10, Versatz 0,6: 125 562 statt 187 239, Direktlöser 17,4 statt 20,8 s), während der Aufbau des
iterativen Wegs an den Zellen hängt. Der Direktlöser ist jetzt in 20 von 23 Fällen schneller, meist um 1
bis 6 s; das Mehrgitter gewinnt nur beim Block mit 186 000 und 281 000 Freiheitsgraden (je etwa 5 s) und
einmal bei der Scheibe (0,9 s). Zusammen braucht der Direktlöser 519 s, das Mehrgitter 564 s, die jeweils
bessere Wahl 508 s; die Schwelle 200 000 verschenkt 28,6 s, 400 000 16,6 s, „immer direkt“ 11,3 s (aus
dem Protokoll per Skript nachgerechnet). `"auto"` wählt darum den Direktlöser; `"gpu"` erzwingt das
Mehrgitter weiterhin, und der Mechanismus der Schwelle bleibt abgeschaltet stehen (`_AUTO_MEHRGITTER`).
Lohnen wird sich die GPU auf dieser Karte erst mit einem schnelleren Aufbau des iterativen Wegs: er
dauert 2 bis 20 s länger als Assemblieren und Faktorisieren; das Lösen selbst ist auf der GPU beim Block
ab 186 000 Freiheitsgraden 3- bis 6-mal schneller, darunter 0,5- bis 2,6-mal.

**Aufbau vermessen und beschleunigt (Plan TP 5, A1 und A2, 29.09.2026).** Zwei unabhängige Messskripte – eines
liest die im Code eingebauten Zeitwerte, eines hängt Zeitmesser mit GPU-Synchronisation von außen um die
Funktionen – stimmen in acht Läufen auf 10 % überein. Ergebnis: Zellintegration und Matrix kosten auf dem
iterativen Weg nicht mehr als das Assemblieren (die vermutete doppelte Arbeit gibt es nicht); der Nachteil des
Mehrgitters kam aus zwei anderen Quellen. Erstens kostete beim Block h 14 ein einzelner Glätterblock der Größe
2 463 in der gestapelten Inversion von CuPy 8,6 s (cuBLAS getrfBatched ist für viele kleine Blöcke gebaut und
wächst für große schlechter als s⁴: s 256, 20 Blöcke gestapelt 0,014 s, einzeln 0,026 s; s 400 0,043 gegen
0,016 s; s 2 463 8,57 gegen 0,17 s); Blöcke über 320 werden seither einzeln invertiert, auf der CPU mit LAPACK
im Hauptfaden statt in der numba-Cholesky. Zweitens suchten die Aggregation ihre 26 Nachbarn und der
Zwangsauflöser seine 98 Probepunkte je feiner Zelle einzeln (81 380 Aufrufe der Punktsuche, 12 s von 23 s
Konstruktor bei Kirsch h 8); beide werden jetzt in einem Aufruf gesucht, Zwangsmatrix und Wurzeln sind an fünf
Modellen bitgleich. Danach: Einrichten des Mehrgitters in allen vier Fällen unter 4,5 s (Block h 14: 20,8 →
3,8 s), Konstruktor bei den verfeinerten Gittern 40 bis 50 % kürzer (Kirsch h 8: 23,1 → 11,8 s), Gesamtweg am
Block h 14 Mehrgitter 58,1 s gegen direkt 74,7 s.

**Eine Million Freiheitsgrade auf der 8-GB-Karte (Plan TP 5, A3, 30.09.2026).** Nach alter Bauart hätten die
Modelle um 10⁶ Freiheitsgrade 10,8 bis 12,2 GB GPU-Speicher gebraucht: Zellmatrizen der Schnittzellen
(295 KB je Zelle bei p 3), Glätterblöcke (rund 350 KB je Zelle für die Ebenen 3 und 2) und die feine Matrix
für den Blockauszug (3,4 bis 4,2 GB). Drei Maßnahmen, alle in FP64 und ohne Änderung der Rechnung (FP32 im
Glätter divergierte schon einmal, siehe oben): (1) Zellmatrizen und Blockinversen liegen symmetrisch gepackt
auf der GPU, nur das untere Dreieck, spaltenweise – die Hälfte. Ein Faden je Zeile, der das Dreieck über die
Symmetrie ergänzt, liest die gespiegelte Hälfte längs seiner eigenen Spalte, und 32 Fäden eines Warps greifen
dann auf 32 verschiedene Speicherzeilen zu: 4 000 Blöcke der Größe 192 brauchten 8,7 ms statt 3,1 ms. Der Kern
rechnet darum in zwei Teilen: die untere Hälfte mit einem Faden je Zeile (für festes b lesen die Fäden a ≥ b
aufeinanderfolgende Adressen der Spalte b), die gespiegelte Hälfte mit einem Warp je Spalte als Skalarprodukt
längs der Spalte mit Summe über den Warp; damit 3,3 ms bei halbem Speicher, der Operator bei 229 608
Freiheitsgraden 1,9 statt 3,1 ms je Anwendung. Große Blöcke werden in Aufträge von höchstens 256 Zeilen
zerlegt; eingesammelt wird über die Inzidenz in fester Reihenfolge, die Anwendung ist damit bitgleich
wiederholbar (das Aufaddieren mit atomaren Additionen war es nicht). Derselbe Kern dient Operator und Glätter
(`fcm/bloecke_gpu.py`). (2) Der Blockauszug läuft auf der CPU in Teilstapeln, die feine Matrix geht nicht mehr
auf die GPU; das kostet am Block h 14 0,64 statt 0,48 s. (3) Der Speicherpool wird nach jeder Größengruppe
des Glätters freigegeben, sobald die Karte weniger als 2 GB frei hat – unter Windows meldet sie keinen Mangel,
sondern lagert aus (1,5 statt 0,13 s je Iteration); die Freigabe kostet bei 33 Gruppen rund 1 s und senkt den
Höchststand um 200 bis 750 MB (Block h 14: 2 295 → 2 094 MB, Kirsch h 8: 3 311 → 2 689 MB, bei 10⁶: 5 158 →
4 425 und 5 574 → 4 822 MB). Gemessen (freie Maschine, je Fall ein Prozess; Höchststand des Pools, die
Karte selbst liegt 50 bis 80 MB darüber, alle 10 ms abgetastet):

| Kirsch p 3 | Freiheitsgrade | Höchststand vorher | Höchststand jetzt (knapp) | belegt vorher → jetzt |
|---|---|---|---|---|
| h 14, Versatz 0 | 81 183 | 1 340 MB | 967 MB | 581 → 328 MB |
| h 12, Versatz 0,6 | 172 128 | 2 172 MB | 1 549 MB | 1 251 → 690 MB |
| h 8, Versatz 0,3 | 472 611 | 5 189 MB | 2 689 MB | 3 503 → 1 924 MB |
| h 5,5, Versatz 0 | 1 002 528 | – (12,2 GB geschätzt) | 4 822 MB | 4 066 MB |
| Block h 9, Versatz 0 | 967 992 | – (10,8 GB geschätzt) | 4 425 MB | 3 673 MB |

Bei den beiden Modellen um 10⁶ Freiheitsgrade braucht das Mehrgitter 29 (Block) und 36 (Kirsch) Iterationen
und löst in 9,0 bzw. 11,1 s; der Direktlöser braucht am Block 46 GB Hauptspeicher und 169 s (Kirsch, dünn:
27 GB, 36 s). Die Ergebnisse stimmen überein: am Block Verschiebungen an 3 000 Punkten auf 2,8·10⁻¹⁴,
Spannungen auf 5,8·10⁻¹³; an der Kirsch-Scheibe Spannungen auf 1,6·10⁻¹², die Verschiebungen unterscheiden
sich um die freie z-Bewegung, die das Mehrgitter herausprojiziert und der Direktlöser beliebig festlegt.
Ist der Speicher nicht knapp, hält der Pool die Zwischenstücke fest, und der Höchststand liegt höher (Block
5 158 MB, Kirsch 5 574 MB) – unschädlich, weil dann Platz ist. Anteile am Lösen bei 10⁶: gepackte Blöcke
(Operator und Glätter) 69 %, Grobgitter p = 1 auf der CPU 12 % – das Grobgitter ist kein Engpass, ein
h-Mehrgitter darunter (Plan A4) entfällt. Die Schätzung der Vertragsschicht ist neu geeicht (gepackte
Posten, Matrizen der Ebenen p−1 bis 2, Indexfelder, 900 MB Arbeitsfelder) und liegt an elf Fällen von 81 000
bis 1 000 000 Freiheitsgraden 3 bis 26 % über dem Höchststand im knappen Betrieb (10⁶: 7 bis 8 %).
Gegenprobe: der Höchststand der Karte (alle Prozesse) lag in einem Lauf 683 MB über dem Pool, in den
Wiederholungen 50 bis 80 MB – der Unterschied kam von anderen Programmen auf der Karte, deren Belegung
zwischen 1,15 und 1,42 GB schwankte.

**Streuung über die Schnittlagen und Chebyshev-Fenster (Plan TP 5, A5, 30.09.2026).** Gemessen an der
Kirsch-Scheibe p 3 (verfeinert) mit fünf Schnittlagen (Versatz 0 bis 0,8) bei h 10 und h 8, GPU, Abbruch
bei 10⁻¹² in Residuum und Energie, je Fall ein Prozess aus einem festen Arbeitsbaum; zwei unabhängige
Skripte (eigener CG mit Ritzwerten, Produktweg `FcmProblem.loesen`) liefern dieselben Iterationszahlen.
Mit dem bisherigen Fenster [λ_max/16, λ_max] brauchte der CG bei h 10 29 / 31 / 43 / 30 / 32 Iterationen
(Mittel 33,0, Versatz 0,4 bei +30 %) und bei h 8 43 / 41 / 34 / 29 / 51 (Mittel 39,6, −27 % bis +29 %).
Die langsamste Mode (Ritzvektor zum kleinsten Ritzwert, als Energieanteile je Zelle) sitzt je nach Lage an
verschiedenen Stellen: sieben Mal im verfeinerten Bereich am Loch (Ebenen 1 und 2, meist volle Zellen), drei
Mal in teilgefüllten Zellen der groben Scheibe (Werkstoffanteil 0,5 bis 0,7) nahe dem belasteten Rand, bei
h 10, Versatz 0,4 mit einem über die Dicke schwingenden u_z (je Zellschicht ein Polynom höheren Grades in z,
das p = 1 nicht darstellt). Nur an den zwei Lagen mit Versatz 0 liegt sie überwiegend in Zellen an oder unter der
Aggregationsschwelle (Werkstoffanteil 0,4 an der Oberseite im verfeinerten Bereich); das sind nicht die
langsamen Lagen (29 und 43 Iterationen). An den beiden langsamsten (h 10 Versatz 0,4, h 8 Versatz 0,8)
sitzt sie in halb bzw. voll gefüllten Zellen – eine andere Stabilisierung (Ghost Penalty statt Aggregation)
träfe sie nicht. λ_max von M⁻¹A (33 bis 65) sitzt an den drei daraufhin
untersuchten Lagen im Übergangsgürtel des Oktrees am Loch (Ebene 1, volle Zellen) und wandert mit der
Schnittlage.

Zuerst gemessen wurde ein gewichteter additiver Schwarz-Glätter, W (Σ R_kᵀ A_k⁻¹ R_k) W mit W = diag(1/√m)
und m der Zahl der Blöcke je Koordinate. Er ist verworfen: bei h 10, Versatz 0 stiegen die Iterationen von
29 auf 230, weil λ_max auf der feinsten Ebene von 33 auf 394 sprang (auf der Ebene darunter sank es wie
erwartet von 36 auf 5,9). Wo der große Eigenwert entsteht, ist nicht weiter untersucht; nach der vor der
Messung festgelegten Regel (keine Lage um mehr als zwei Iterationen schlechter) ist die Variante verworfen.

Wirksam ist dagegen ein breiteres Chebyshev-Fenster. Bei α 16 glättet Chebyshev nur oberhalb von λ_max/16,
also 2 bis 4; darunter bleibt alles dem Grobgitter. An vier Lagen gemessen (Lösezeit bei h 10, Versatz 0,4):
α 16 3,09 s, α 30 2,75 s, α 60 2,42 s, α 100 2,29 s, α 200 2,21 s – das Fenster sättigt ab etwa 100; Grad 6
statt 5 spart Iterationen, aber keine Zeit (am 28.09. bei der alten Blockablage war Grad 8/α 30 noch
langsamer als Grad 5/α 16). Standard ist seither Grad 5 auf [λ_max/100, λ_max]:

| Kirsch p 3 | Iterationen α 16 | Iterationen α 100 | Lösen α 16 | Lösen α 100 |
|---|---|---|---|---|
| h 10, fünf Lagen | 29 / 31 / 43 / 30 / 32 (Mittel 33,0) | 22 / 23 / 32 / 23 / 24 (24,8) | 15,0 s | 11,7 s |
| h 8, fünf Lagen | 43 / 41 / 34 / 29 / 51 (39,6) | 34 / 31 / 26 / 23 / 39 (30,6) | 26,6 s | 21,2 s |

(Lösezeiten über `FcmProblem.loesen` in Summe über die fünf Lagen; der reine CG des ersten Skripts 12,8 → 9,6
und 23,7 → 18,1 s. Das Einrichten, 15 bis 27 s je Lage, hängt nicht am Fenster.)

Der kleinste Ritzwert des vorkonditionierten Operators verdoppelt sich an allen zehn Lagen (h 10: 0,061
bis 0,100 auf 0,116 bis 0,188), die Spannungen am Lochrand sind auf sechs Stellen gleich, K_t streut über
die Lagen um 0,3 % (Vorgabe: Ergebnisstreuung unter 1 %). Die relative Streuung der Iterationen bleibt
dagegen: h 10 −11 % bis +29 %, h 8 −25 % bis +27 %. Das breitere Fenster verkürzt alle Lagen etwa im selben
Verhältnis; die Ursachen sind die beiden Stellen, an denen die langsamen Moden sitzen (Oktree-Übergang am
Loch und die dünne Scheibe mit zwei halb gefüllten Zellschichten über die Dicke), nicht die Aggregation. Das
selbst gesetzte Ziel ±20 % (Plan TP 4) ist damit nicht erreicht; die Vorgabe verlangt eine stabile
Iterationszahl unter 100 bei 10⁻⁸, die mit höchstens 39 Iterationen bei 10⁻¹² eingehalten ist.

**Löserwahl und Leistungsabnahme (Plan TP 5, A6, 30.09.2026).** Die Schlussmessung vom 29.09. ist mit dem Stand
nach A2, A3 und A5 (Commit a0a5c74) wiederholt worden, dazu p 2 und p 4 und die Modelle um eine Million
Freiheitsgrade. Die Regeln standen vor der ersten Messung im Plan (Commit a0a5c74). Freie Maschine, je Fall ein
Prozess, Toleranz 10⁻¹²; „Gesamt“ ist wie am 29.09. Aufbau plus Lösen ohne den Konstruktor des Problems, der
getrennt genannt wird. Beim Direktlöser enthält das Lösen die Faktorisierung, denn PARDISO faktorisiert erst beim
ersten Lösen. Die Kontrollspannung σ_x am Lochrand bzw. an der Bohrung stimmt zwischen beiden Wegen in allen 23
Fällen auf die ausgegebenen vier Nachkommastellen überein (die im Plan genannte Schwelle 10⁻⁹ ließ sich mit dieser
Ausgabe nicht prüfen; die Genauigkeit des Mehrgitters bis 10⁻¹² ist in A3 und A5 gesondert belegt). Zwei unabhängige Skripte (eines mit den eingebauten Zeitwerten des Protokolls, eines mit
Zeitmessern von außen um die Funktionen des Aufbaus, an sechs Fällen) weichen im Aufbau um höchstens 6 % und im
Lösen um höchstens 8 % voneinander ab.

*Serie S, 23 Fälle bei p 3 (65 000 bis 497 000 Freiheitsgrade, Zeit in s je Lage im Mittel):*

| Modell | Lagen | Freiheitsgrade | Gesamt direkt (Mittel) | Gesamt Mehrgitter (Mittel) | Verhältnis je Lage | Iterationen |
|---|---|---|---|---|---|---|
| Block h 25 | 2 | 65.040 bis 65.616 | 15,0 s | 16,9 s | 1,05 bis 1,20 | 21 bis 32 |
| Block h 20 | 2 | 115.728 bis 116.187 | 21,6 s | 20,7 s | 0,91 bis 1,01 | 21 bis 24 |
| Block h 16 | 2 | 185.856 bis 232.296 | 41,1 s | 33,3 s | 0,75 bis 0,88 | 20 bis 25 |
| Block h 14 | 2 | 281.292 bis 340.476 | 55,4 s | 42,5 s | 0,73 bis 0,81 | 24 bis 25 |
| Kirsch h 14 | 3 | 81.183 bis 135.327 | 7,9 s | 10,0 s | 1,21 bis 1,28 | 23 bis 25 |
| Kirsch h 12 | 3 | 165.501 bis 173.862 | 10,8 s | 13,2 s | 1,17 bis 1,28 | 21 bis 25 |
| Kirsch h 10 | 3 | 229.608 bis 330.705 | 17,4 s | 18,7 s | 0,97 bis 1,21 | 22 bis 28 |
| Kirsch h 9 | 3 | 283.896 bis 390.018 | 21,2 s | 22,6 s | 0,96 bis 1,16 | 23 bis 32 |
| Kirsch h 8 | 3 | 360.204 bis 497.244 | 28,3 s | 29,4 s | 1,01 bis 1,09 | 23 bis 44 |

Das GPU-Mehrgitter ist im Gesamtweg in 7 von 23 Fällen schneller; die Summe beträgt 523 s für den Direktlöser
und 509 s für das Mehrgitter. Der Unterschied liegt an der Bauteilform: am kompakten Block (Summe der acht Fälle
266 s gegen 227 s, Verhältnis 0,85) liegt das Mehrgitter ab 185 000 Freiheitsgraden bei 0,73 bis 0,88, an der
dünnen Kirsch-Scheibe (Summe 257 s gegen 282 s, Verhältnis 1,10) ist es nur in 2 von 15 Fällen schneller (0,96 und
0,97). Die vorher festgelegte Regel (kleinste Zahl aller Freiheitsgrade N₀, ab der das Mehrgitter in jedem Fall
höchstens das 1,05-fache des Direktlösers braucht und in der Summe mindestens 10 % schneller ist) findet kein N₀:
der größte Fall der Serie (Kirsch h 8, Versatz 0,6, 497 244 Freiheitsgrade) liegt bei 1,09. **`auto` bleibt beim
Direktlöser**, `_AUTO_MEHRGITTER` bleibt ausgeschaltet, und damit entfällt die Erweiterung der Polynomgrade.

*Serie G, p 2 und p 4:*

| Modell | p | Freiheitsgrade | Gesamt direkt | Gesamt Mehrgitter | Verhältnis | Iterationen |
|---|---|---|---|---|---|---|
| Block h 16 (Versatz 0,3) | 2 | 71.568 | 5,1 s | 5,9 s | 1,16 | 24 |
| Block h 16 (Versatz 0,3) | 4 | 539.778 | 159,1 s | 128,3 s | 0,81 | 44 |
| Block h 20 (Versatz 0) | 2 | 36.096 | 3,0 s | 4,0 s | 1,35 | 23 |
| Block h 20 (Versatz 0) | 4 | 268.818 | 77,9 s | 77,1 s | 0,99 | 41 |
| Kirsch h 9 (Versatz 0,3) | 2 | 94.695 | 4,0 s | 5,3 s | 1,33 | 29 |
| Kirsch h 9 (Versatz 0,3) | 4 | 672.045 | 106,9 s | 97,2 s | 0,91 | 57 |
| Kirsch h 12 (Versatz 0,3) | 2 | 55.938 | 2,1 s | 3,5 s | 1,66 | 21 |
| Kirsch h 12 (Versatz 0,3) | 4 | 394.620 | 46,1 s | 55,2 s | 1,20 | 41 |

Bei p 2 ist das Mehrgitter in allen vier Fällen langsamer (1,16 bis 1,66), bei p 4 in drei von vier schneller (0,81
bis 0,99) und beim Kirsch h 12 langsamer (1,20). Die Zahl der Iterationen steigt mit p (p 2: 21 bis 29, p 3: 20 bis
44, p 4: 41 bis 57). Für die Löserwahl folgt daraus nichts, weil `auto` ohnehin beim Direktlöser bleibt.

*Serie M, eine Million Freiheitsgrade bei p 3:*

| Modell | Weg | Konstruktor | Aufbau | Lösen | Aufbau + Lösen | Iterationen |
|---|---|---|---|---|---|---|
| Block h 9 (967.992 FHG) | direkt | 33,4 s | 107,2 s | 173,0 s | 280,2 s | – |
| Block h 9 (967.992 FHG) | mehrgitter-gpu | 33,7 s | 107,8 s | 7,1 s | 115,0 s | 22 |
| Kirsch h 5,5 (1.002.528 FHG) | direkt | 21,0 s | 49,2 s | 34,2 s | 83,4 s | – |
| Kirsch h 5,5 (1.002.528 FHG) | mehrgitter-gpu | 21,7 s | 53,6 s | 8,3 s | 62,0 s | 27 |

Hier liegt das Mehrgitter in beiden Familien vorn: am Block 115 statt 280 s (0,41; der Direktlöser braucht dazu
46 GB Hauptspeicher, am 30.09. in A3 gemessen, und das Lösen allein 173 s), an der Kirsch-Scheibe 62 statt 83 s (0,74). Zwischen 497 000
(letzter Fall der Serie S) und 968 000 Freiheitsgraden fehlt die Messung; ein N₀ zwischen beiden Grenzen ist mit
diesen Zahlen nicht festzulegen. Das ist ein Befund nach der Messung und nicht Teil der vorher festgelegten Regel.

*Verlustrechnung (Zeitmesser von außen, Zeiten ohne Konstruktor in s):*

| Fall | Direktlöser | davon Aufbau der Zellmatrizen und Assemblierung | davon Faktorisierung + Substitution | Mehrgitter | davon Zelldaten | davon Zelldaten.matrix, Einrichten, PCG |
|---|---|---|---|---|---|---|
| Block h 14, Versatz 0,3 (340 476 FHG) | 59,2 | 34,4 | 19,8 + 1,4 | 45,0 | 30,0 | 3,4 + 4,7 + 2,9 |
| Kirsch h 10, Versatz 0,3 (229 830 FHG) | 18,6 | 9,7 | 5,3 + 0,9 | 17,9 | 7,3 | 2,0 + 3,4 + 2,1 (+ 0,4) |

Die Zellmatrizen sind auf beiden Wegen der größte Posten und von ähnlicher Größe (am Block 34,4 gegen 30,0 s, an der
Scheibe 9,7 gegen 7,3 s). Das Mehrgitter spart die Faktorisierung und die Substitution (am Block 21,2 s, an der
Scheibe 6,1 s) und braucht dafür die Matrix aus den Zelldaten, das Einrichten und den PCG (11,0 s am Block, 7,5 s
plus 0,4 s Rest an der Scheibe). Am Block bleibt es damit 10 s unter dem Direktlöser, mit den Zellmatrizen
zusammen 14,2 s; an der Scheibe fällt der Gewinn aus der Faktorisierung weg (6,1 gegen 7,9 s), und nur die
billigeren Zellmatrizen (2,4 s) lassen einen Vorsprung von 0,8 s stehen. Gemessen ist der Unterschied der
Faktorisierung: am Block 19,8 s bei 265 284 freien Koordinaten, an der Scheibe 5,3 s bei 181 797, und bei 10⁶
Freiheitsgraden 173 s gegen 34 s für das Lösen des Direktlösers; darum die Trennung nach Bauteilform. Die Summen
des Zeitbaums stimmen mit dem ersten Skript auf 5 % überein (59,2 und 45,0 gegen 61,2 und 44,7 s; 18,6 und
17,9 gegen 19,4 und 18,8 s).

**Leistungskriterium (Vorgabe 13: eine Million Freiheitsgrade, Lösung unter 60 s).** In der Lesart (a), das Lösen
allein, ist es erfüllt: 7,1 s am Block (22 Iterationen) und 8,3 s an der Scheibe (27 Iterationen). In der Lesart (b),
Aufbau plus Lösen, ist es nicht erfüllt: 115,0 s am Block und 62,0 s an der Scheibe; mit dem Konstruktor 148,6 und
83,6 s. Die Lesart (b) zählt das Einrichten einmal je Bauteil, jeder weitere Lastfall kostet nur das Lösen. Der
Zeitbaum zeigt, wo die Zeit steht: am Block 78,4 s in `Zelldaten` (Zellsteifigkeiten der Schnittzellen, 68 % der
115 s; der Aufbau insgesamt liegt auf beiden Wegen bei 107,2 und 107,8 s), 10,2 s in der Matrix aus den Zelldaten, 8,8 s im Einrichten des Mehrgitters, 6,3 s
im PCG; im Konstruktor 19,8 s im Problem selbst (nicht weiter aufgeschlüsselt), 11,4 s in der Aggregation und
2,6 s in den Zwängen. An der Scheibe 25,5 s in `Zelldaten` (41 % der 62 s), 9,3 s Matrix, 9,8 s Einrichten, 7,8 s PCG.
Eine Verkürzung von (b) unter 60 s setzt bei den Zellsteifigkeiten an, nicht beim Löser; sie hängt vom
Momentenfitting (TP 5, B1) ab, das die Integration der Schnittzellen ersetzt, und wird danach neu gemessen.

### 11.11 Teilprojekt 5: Moment Fitting für Schnittzellen (30.09.2026)

**Warum.** Die ebenen-exakte Integration aus 11.3 teilt eine gekrümmt geschnittene Zelle bis Tiefe 2 in
Blätter und zerlegt jedes geschnittene Blatt in Tetraeder mit einer konischen Produktregel. Das ist genau,
aber teuer: am Lamé-Zylinder h 20 p 3 liegen 10 541 Punkte in einer Schnittzelle, an der Kirsch-Scheibe h 20
776 bis 1 471 im Mittel über alle Schnittzellen (die gekrümmt geschnittenen am Loch tragen bis zu 12 000). Die
Zellsteifigkeiten der Schnittzellen waren in der Messung A6 mit 78 s der größte Posten des Modells mit einer
Million Freiheitsgraden (68 % von Aufbau und Lösen). Die Vorgabe (Abschnitt 6, Stufe 2) nennt dafür Moment
Fitting: je Schnittzelle ein kleiner Satz fester Punkte mit angepassten Gewichten, der die Momente der
Werkstoffdomäne exakt integriert.

**Verfahren** (`fcm/momentfitting.py`, Schalter `Zellquadratur(momentfitting=..., fit_grad=q)`). Die bisherige
Integration liefert je Schnittzelle die Referenzpunkte und damit die Momente μ_abc = Σ W_k N_a N_b N_c der
Werkstoffdomäne in der Tensor-Legendre-Basis vom Grad q je Richtung (die 1D-Basis aus 11.1; sie spannt dieselben
Polynome auf wie die Monome, ist auf [−1, 1] aber gut konditioniert). Die gefittete Regel liegt auf den
Tensor-Gauß-Punkten (q+1)³ der ganzen Zelle, ihre Gewichte w lösen Σ_i w_i N_a(x_i) N_b(y_i) N_c(z_i) = μ_abc.
Weil Punkte und Basis Tensorprodukte sind, ist die Momentenmatrix ein Kronecker-Produkt A₁ ⊗ A₁ ⊗ A₁ mit der
eindimensionalen Matrix A₁[i,a] = N_a(x_i) an den q+1 Gauß-Punkten; die Lösung sind drei eindimensionale
Kontraktionen mit A₁⁻ᵀ statt einer (q+1)³-dimensionalen Gleichung, und sie ist gut konditioniert. Der fiktive
α-Anteil bleibt ein Satz Tensor-Gauß-Punkte (p+1)³ mit Gewicht α über die ganze Zelle; das ist derselbe Wert wie
die α-Punkte aller Blätter, da beide Regeln bis Grad 2p+1 exakt sind. Gefittet wird nur, wo es Punkte spart:
achsparallel geschnittene Zellen (Kragarmsegment) haben schon (p+1)³ Punkte und behalten sie.

**Warum q = 2p.** Die Integranden der Zellsteifigkeit sind Produkte zweier Ableitungen von Basisfunktionen, in
jeder Richtung vom Grad höchstens 2p. Mit q = 2p liegen sie im Raum, den die gefittete Regel exakt integriert –
exakt im Sinne der Referenz: die Regel reproduziert für jedes f aus diesem Raum den Wert Σ W_k f(P_k) der
Referenzregel, auch dort, wo die Referenz selbst (Tetraeder bis Gesamtgrad 3p−1) nicht exakt ist. Die Zellmatrix
ist damit bis auf Rundung dieselbe, unabhängig davon, wie die Gewichte aussehen. (Diese Ungenauigkeit der Referenz war die Ursache des
Konsistenzfehlers quadratischer Felder; seit O5 kommen die Momente der schrägen Stücke exakt aus dem Divergenzsatz, 11.21.) Und die sehen wild aus: an einer
zu 65 % gefüllten, eben geschnittenen Zelle ist das kleinste Gewicht −0,16 des mittleren, an Schnittzellen der
Lamé- und Kirsch-Geometrie −17 bis −29, die negative Gewichtsmasse erreicht 87 % der positiven. Für q < 2p ist
die Exaktheit nicht gegeben, und die negativen Gewichte schlagen durch: mit q = p sind Zellmatrizen indefinit
(kleinster relativer Eigenwert −1,9·10⁻³ am Lamé-Zylinder, −3,3·10⁻³ an der Kirsch-Scheibe), der Lamé-Fehler in
σ_r steigt von 3,32 auf 5,96 % (p 2), und die vorgesehene Reparatur – NNLS auf (q+2)³ Punkten, sonst Rückfall auf
die Referenz – greift so oft (Kirsch h 20: 17 bis 22 von 27 gefitteten Zellen), dass kaum Punkte gespart werden
(Faktor 1,3 bis 1,8). Mit q = p+1 und p+2 bleiben Abweichungen von 10⁻⁴ bis 10⁻³ in den Spannungen und
Eigenwerte bis −1,3·10⁻⁴. Darum ist 2p die Vorgabe (`fit_grad_standard`), und die NNLS-Stufe bleibt nur für
kleinere q im Code.

**Messung** (h 20, freie Wahl q ∈ {p, …, 2p}, Direktlöser, je Fall Referenz gegen gefittet; „σ gegen Referenz“
ist die größte Abweichung der Spannungen an 1 500 Werkstoffpunkten bzw. an den Randpunkten, bezogen auf die
größte Spannung; Zeiten der Zellmatrizen aller Schnittzellen bei belegter Maschine, nur als Anhalt):

| Fall | Schnittzellen | Punkte je Schnittzelle: Referenz → q = 2p | Faktor | σ gegen Referenz innen / Rand | Zellmatrizen |
|---|---|---|---|---|---|
| Patch p 2 (schräge Ebenen) | 113 | 240 → 94 | 2,6 | 1,6·10⁻¹¹ / 5,7·10⁻¹¹ | 0,27 → 0,37 s |
| Patch p 3 | 113 | 1 097 → 260 | 4,2 | 8,0·10⁻¹⁰ / 5,9·10⁻⁹ | 2,0 → 0,26 s |
| Lamé p 2 | 56 | 2 517 → 112 | 22,6 | 6,2·10⁻¹⁴ / 2,0·10⁻¹³ | 0,23 → 0,04 s |
| Lamé p 3 | 56 | 10 541 → 306 | 34,4 | 1,3·10⁻¹² / 7,5·10⁻¹² | 2,14 → 0,13 s |
| Kirsch p 3 verfeinert, Versatz 0 | 382 | 1 471 → 79 | 18,6 | 7,1·10⁻¹³ / 1,3·10⁻¹⁰ | 2,24 → 0,76 s |
| Kirsch p 3 verfeinert, Versatz 0,4 | 720 | 776 → 46 | 16,7 | 2,2·10⁻¹² / 1,0·10⁻¹¹ | 2,66 → 0,79 s |
| Kragarmsegment p 3 (achsparallel) | 75 | 64 → 64 | 1,0 | 4,3·10⁻¹² / 3,5·10⁻¹¹ | 0,18 → 0,17 s |

Patch-Tests bleiben unter 10⁻⁸ (p 3) bzw. 10⁻¹⁰ (p 2), K_t der Kirsch-Scheibe ist auf fünf Stellen gleich (3,15666
und 3,10770), die Lamé-Fehler sind unverändert (p 3: σ_r 1,187 %, σ_φ 0,412 %). Die Zellmatrizen stimmen an jeder
Schnittzelle auf 2·10⁻¹³ überein, das Werkstoffvolumen auf 10⁻¹⁵; kein Rückfall, kein NNLS. Das Ziel des Plans,
mindestens fünfmal weniger Punkte, ist an allen gekrümmten Geometrien weit übertroffen (17- bis 34-fach) und an den
eben geschnittenen Patch-Zellen verfehlt (2,6- und 4,2-fach); dort war die Referenz schon vergleichsweise billig.
Nach der vorher festgelegten Regel wäre die Referenz Standard geblieben; der Anwender hat das Fitting am
30.09.2026 zur Vorgabe gemacht (`MOMENTFITTING_STANDARD = True`), weil es die Ergebnisse nicht ändert und nie mehr
Punkte erzeugt als die Referenz. `momentfitting=False` schaltet zurück; plastische Körper brauchen nach Vertrag 6a
die Unterteilung (im Modul gibt es noch keine Plastizität).

**Zeiten auf freier Maschine (30.09.2026, Commit efc9686, je Fall ein Prozess).** Referenzquadratur gegen Fitting an
den Modellen der Messung A6, p 3; „gesamt“ ist hier Konstruktor plus Aufbau plus Lösen:

| Modell | Freiheitsgrade | Quadraturpunkte | Konstruktor | Aufbau direkt / Mehrgitter | Gesamt direkt / Mehrgitter |
|---|---|---|---|---|---|
| Kirsch h 10, Versatz 0,3 | 229 830 | 2 126 504 → 169 545 | 6,7 → 9,4 s | 12,5 → 6,4 / 17,1 → 10,2 s | 25,7 → 22,1 / 26,1 → 22,7 s |
| Kirsch h 8, Versatz 0,3 | 472 611 | 3 187 976 → 266 066 | 11,9 → 16,2 s | 21,1 → 12,0 / 26,1 → 16,8 s | 43,8 → 39,0 / 44,6 → 39,5 s |
| Block h 14, Versatz 0,3 | 340 476 | 9 485 160 → 327 150 | 14,7 → 27,8 s | 37,9 → 9,4 / 41,9 → 13,3 s | 74,9 → 59,8 / 59,7 → 44,1 s |
| Block h 9 | 967 992 | 24 551 712 → 972 601 | 33,7 → 67,4 s | 107,0 → 32,9 / 108,3 → 34,3 s | 323,4 → 277,2 / 148,7 → 108,9 s |

Die Spannungen sind in allen acht Paaren auf die ausgegebenen vier Stellen gleich. Die Quadraturpunkte sinken um 92
bis 96 %, der Aufbau wird 1,8- bis 4-mal schneller; ein Teil der Ersparnis wandert in den
Konstruktor, der die Referenzintegration weiter braucht und daraus die Momente bildet (Block h 9: 34 → 67 s). Im
Gesamtweg bleiben 11 bis 27 % Gewinn. Für das Leistungskriterium der Vorgabe 13 (Messung A6, Lesart b: Aufbau plus
Lösen bei 10⁶ Freiheitsgraden) heißt das am Block 34,3 + 6,9 = 41,2 s statt 115 s – die Lesart b ist mit dem
Fitting erfüllt, mit dem Konstruktor sind es 109 s. Der nächste Hebel ist der Konstruktor selbst (Momente ohne den
Umweg über alle Referenzpunkte).

**Befund am Rande: die Wurzelwahl der Aggregation hing an der Rundung.** Vor der Kur unterschieden sich die
Lösungen mit und ohne Fitting am Lamé-Zylinder um 4·10⁻³ in den Randspannungen, obwohl alle Zellmatrizen auf
10⁻¹³ gleich waren. Ursache: die Wurzel einer schlecht geschnittenen Zelle ist der wohlgestellte Nachbar mit dem
größten Werkstoffanteil, und zwei volle Nachbarn unterschieden sich je nach Quadratur um 3·10⁻¹⁵ im Anteil – der
Sieger war Zufall der Rundung, mit ihm die Zwangsmatrix. Seither entscheidet der auf neun Stellen gerundete
Anteil, bei Gleichstand die feste Nachbarreihenfolge (Flächen-, dann Kanten-, dann Eckennachbarn); Gewichte mal
(1 ± 3·10⁻¹⁵) lassen die Wurzeln unverändert (test_zwaenge), und beide Quadraturen liefern jetzt auf 10⁻¹²
dieselben Spannungen. Ebenfalls gemessen und unverändert: das lineare Feld auf der gekrümmten Kirsch-Geometrie
ist mit beiden Quadraturen gleich weit von exakt entfernt (Spannungen innen 9,3·10⁻³, an einzelnen Randpunkten
bis 0,19) – erwartet, weil die Momente aus derselben Integration stammen; die Ursache liegt in der
Verträglichkeit von Volumen- und Randquadratur an gekrümmten Flächen (offen, siehe 11.8, Aggregationsketten).

### 11.12 Teilprojekt 5: Spannungsrückgewinnung durch L²-Projektion (30.09.2026)

**Warum.** Die Rohspannung σ_h = D B u ist in jeder Zelle ein Polynom und springt an den Zellgrenzen. An der
Oberfläche, wo die Nachweise ansetzen, ist sie am unsichersten: dort liegen die Schnittzellen, oft mit wenig
Werkstoff, und die aggregierten Zellen, deren Verschiebungen die Fortsetzung des Wurzelpolynoms sind. Am
Lamé-Zylinder h 20 p 2 lag der größte Fehler der Rohspannung an den Oberflächenpunkten bei 57 % des Innendrucks,
im Mittel bei 3,7 %. Die Vorgabe (Abschnitt 11.1) verlangt eine Glättung über Superconvergent Patch Recovery oder
L²-Projektion und die Auswertung an der echten Oberfläche.

**Verfahren** (`postprocess/rueckgewinnung.py`). Jede der sechs Spannungskomponenten wird auf den stetigen skalaren
Ansatzraum vom Grad p derselben Zellen projiziert: M X = B mit M = Cᵀ(Σ ∫ Nᵀ N dΩ)C und B = Cᵀ Σ ∫ Nᵀ σ_h dΩ. C ist
die skalare Fassung der Zwangsmatrix; die Zwänge der Verschiebungen (hängende Moden des Oktrees und Aggregation)
sind für alle drei Komponenten gleich, darum genügt jede dritte Zeile und Spalte. Integriert wird mit der
Zellquadratur der Steifigkeit, Werkstoff- und α-Punkte, sodass das Werkstoffgebiet M genauso bestimmt wie die
Steifigkeit: gebundene Moden schlecht geschnittener Zellen hängen an ihrer Wurzel, isolierte Splitter behalten α.
M wird einmal je Problem aufgebaut und faktorisiert, jeder Lastfall kostet nur rechte Seiten; mehrere Lastfälle
laufen in einem Aufruf. Konstante Spannungen gehören zum Ansatzraum und werden exakt wiedergegeben. SPR ist nicht
gebaut: Patches um Knoten vertragen sich schlecht mit Schnittzellen, hängenden Moden und Aggregation, die
L²-Projektion erbt alle drei ohne Sonderfälle. Die Massenmatrix hat am Patch-Modell die Kondition 2,2·10⁸
(Schnittzellen, hierarchische Basis); zwei Lastfälle in einem Aufruf und einzeln unterscheiden sich darum um
10⁻⁹ bis 3·10⁻⁸ (verschiedene Summationsreihenfolge der rechten Seiten), das ist Kondition mal
Maschinengenauigkeit und für Spannungen belanglos.

**Messung** (Direktlöser, Auswertepunkte sind die Punkte der Flächenquadratur, 1e-7·h nach innen gerückt, wie im
Vertragsweg; die Regel stand vorher im Plan):

| Fall | Oberflächenpunkte | Rohwert | geglättet |
|---|---|---|---|
| Patch p 2 / p 3, Fehler gegen σ exakt | 6 720 / 10 500 | 2,0·10⁻¹⁰ / 6,3·10⁻⁸ | 8,5·10⁻¹¹ / 2,1·10⁻⁸ |
| Reine Biegung p 3, Fehler gegen −M z / I | 7 800 | 8,3·10⁻¹¹ | 8,7·10⁻¹¹ |
| Lamé p 2 h 20, größter / mittlerer Fehler (bezogen auf p_i) | 49 604 | 56,6 % / 3,66 % | 15,2 % / 2,93 % |
| Lamé p 3 h 20 | 77 469 | 5,27 % / 0,62 % | 5,24 % / 0,54 % |
| Lamé p 2 h 10 | 139 640 | 5,51 % / 0,81 % | 5,36 % / 0,79 % |
| Lamé p 3 h 10 | 218 143 | 2,29 % / 0,22 % | 2,23 % / 0,21 % |
| Kirsch p 3 h 20, Versatz 0: K_t / mittleres Randresiduum | 45 850 | 3,1567 / 1,87·10⁻³ | 3,1437 / 1,55·10⁻³ |
| Kirsch p 3 h 20, Versatz 0,4 | 39 525 | 3,1077 / 1,49·10⁻³ | 3,1009 / 1,20·10⁻³ |

Das Randresiduum ist |σ·n| auf den freien Flächen (Loch, Ober- und Unterseite, freie Längsseite), bezogen auf die
Nennspannung S₀; die geglättete Spannung verletzt die Randbedingung im Mittel um 17 bis 20 % weniger, das größte
Residuum sinkt von 2,8 auf 1,9 % bzw. von 4,2 auf 2,6 %. K_t verschiebt sich um 0,41 bzw. 0,22 %, beide Male zur
Tabellenreferenz 3,028 hin. Der große Gewinn liegt beim groben Lamé-Fall mit p 2; bei p 3 und h 10 ist die
Rohspannung schon gut, und die Glättung bessert nur wenig (2,29 auf 2,23 %). Im größten Fehler wird kein gemessener
Fall schlechter, auf einzelnen Flächen schon: an der unbelasteten Außenfläche des Lamé-Zylinders steigt er bei p 2 h 20
von 2,1 auf 3,8 % und bei p 2 h 10 von 0,50 auf 0,52 %, auf der Symmetriefläche y = 0 bei p 3 h 10 von 0,54 auf 0,56 %.

Nach der Regel ist die L²-Projektion seither die Ausgabe des Vertragswegs: `DetailResult.stress` und
`von_mises` sind geglättet, das Protokoll nennt es unter `stress_recovery` mit den Zeiten; `_SPANNUNG_GEGLAETTET`
in `api.py` schaltet zurück. `Auswertung.spannung(P, geglaettet=True)` gibt die geglätteten Werte an beliebigen
Punkten, die Rohwerte bleiben die Vorgabe dieser Funktion (Kopplungskontrolle, Schnittgrößen und alle bisherigen
Abnahmen rechnen weiter mit ihnen). Kosten an den gemessenen Modellen bis 72 000 Freiheitsgrade: Aufbau von M
0,02 bis 0,23 s, rechte Seiten 0,03 bis 0,6 s je Aufruf. Auf freier Maschine mit Fitting (Commit efc9686):

| Modell | freie skalare Moden | Aufbau von M | rechte Seiten | Auswertung an der Oberfläche |
|---|---|---|---|---|
| Kirsch h 10, Versatz 0,3 | 60 653 | 0,95 s | 1,68 s | 0,63 s (154 975 Punkte) |
| Kirsch h 8, Versatz 0,3 | 95 528 | 1,57 s | 2,84 s | 0,76 s (223 725 Punkte) |
| Block h 14, Versatz 0,3 | 88 428 | 1,29 s | 3,29 s | 0,90 s (277 275 Punkte) |
| Block h 9 (10⁶ FHG) | 269 232 | 4,89 s | 12,95 s | 1,96 s (640 850 Punkte) |

Ohne Fitting kosten die rechten Seiten 17 bis 204 s, weil sie über alle Referenzpunkte laufen. Die rechten Seiten
sind eine Zellschleife, deren Kosten kaum von der Zahl der Lastfälle abhängen; der Vertragsweg berechnet sie darum
seit B3 für alle Keys in einem Aufruf statt je Key.

### 11.13 Teilprojekt 5: Strukturspannung am Nahtübergang nach IIW Typ a (30.09.2026)

**Verfahren** (`postprocess/hotspot.py`, Vorgabe 11.2). Je Punkt der Nahtpolylinie (`WeldLine.points`, Nahtübergang)
liegen die Referenzpunkte bei 0,4·t und 1,0·t auf der Blechoberfläche, senkrecht zur Naht; maßgebend ist
σ_⊥ = d·σ·d mit d der Richtung auf dem Blech von der Naht weg, und σ_hs = 5/3·σ(0,4t) − 2/3·σ(1,0t) (die Beiwerte 1,67
und 0,67 der IIW sind diese Brüche gerundet). Die Spannung ist dieselbe wie in `DetailResult.stress` (geglättet,
11.12). Der Vertrag liefert nur die Polylinie und die Blechdicke; auf welcher Seite des Übergangs das Blech liegt,
bestimmt die Geometrie: in der Ebene senkrecht zur Naht schneidet ein Kreis vom Radius 0,05·t um den Übergang die
Oberfläche in zwei Ästen (Blech und Nahtoberfläche). Unter dem Blechast ist der Werkstoff längs der Innennormalen so
tief wie das Blech dick (auf 20 %), unter der Nahtoberfläche tiefer – am T-Stoß mit Kehlnaht 45° und Schenkel 8
sind es (0,7·t/√2 + t)·√2 = 21,1 mm, gemessen auf 4·10⁻¹⁴ mm. Passt kein oder beide Äste, oder sind die Äste
gegenläufig (ebene Fläche, kein Knick), gibt es für diesen Punkt keinen Wert, sondern eine Warnung; geraten wird
nicht. `method = "effective_notch"` wird mit Warnung übergangen. Der Vertragsweg füllt `DetailResult.hot_spots` je
gültigem Nahtpunkt, das Protokoll nennt unter `hot_spot` Verfahren, Spannungsart und je Naht die Werte bei 0,4·t und
1,0·t, `convergence` trägt `hotspot_max`.

**Verschachtelte CSG-Bäume (Befund in B3).** Ein T-Stoß mit Kehlnähten ist eine Vereinigung, deren Teile Schnitte
sind (Naht = Quader ∩ Halbraum). Die ebenen-exakte Zerlegung (11.3) kannte nur „Schnitt aller Formen minus
Löcher“ und „Vereinigung aller Formen“; hier fiel jedes Blatt auf den Punkttest erster Ordnung (h 20: 18 401
Blätter, Volumen +0,13 %, 2,6 Mio. Oberflächenpunkte, 61 s Konstruktor), und das exakt darstellbare Feld wich um
3,7 % ab. Seither bildet `Csg._baum_stuecke` die lokalen Stücke über den Baum selbst: Schnitt schneidet die Stücke
der Kinder, Vereinigung hängt jedes Kind ohne die vorigen an, Differenz zieht ab; ohne gekrümmte aktive Form werden
die Stücke an den Proben gegen das Vorzeichen des Abstands geprüft (sonst Rückfall wie bisher). Die Flächenquadratur
teilt ein Polygon auf diesem Weg an allen beteiligten Ebenen, bevor die Zeugenpunkte entscheiden – sonst fiel eine
Grundblech-Oberseite, deren Schwerpunkt unter der Naht lag, ganz weg, und Stirnflächen wurden doppelt gezählt. Am
T-Stoß auf drei Gittern: kein Punkttest-Blatt, Volumen exakt (133 200 mm³), alle sechs Flächen auf 3·10⁻¹², Konstruktor
1,3 statt 61 s bei h 20. Die flachen Muster bleiben unverändert; alle übrigen Suiten sind grün geblieben.

**Prüfungen.** (1) Synthetisches Feld linear in x auf dem T-Stoß: Blechseite an allen 18 Punkten richtig,
Referenzpunkte auf 3·10⁻¹⁶ mm, σ_hs = σ_xx am Übergang auf 2·10⁻¹⁶. (2) Finite Zellen mit exakt darstellbarem
Feld (u = (c x²/2, 0, 0), konstante Volumenkraft, Dirichlet überall, p 3): σ_hs trifft σ_xx am Übergang auf 1,6·10⁻⁷
roh und 6,2·10⁻⁸ geglättet. (3) T-Stoß unter Zug σ_n = 100 N/mm² (Grundblech t 10, einseitiges Querblech 10 mm,
beidseitige Kehlnähte, nicht tragend, Symmetrie x = 0 und y = 0):

| | h 10 (316 827 FHG) | h 5 (1 832 523 FHG) |
|---|---|---|
| σ_xx fern der Naht (x 180), Ober-/Unterseite | 100,01 / 100,05 | 100,01 / 100,05 |
| σ_hs an 18 Nahtpunkten | 98,75 bis 101,92 | 100,04 bis 101,97 |
| Mittel rechts / links | 100,43 / 99,65 | 100,93 / 100,77 |
| über die Dicke linearisiert, Schnitt x 113 (Oberseite) | 93,42 | 96,58 |

Fernfeld und Konvergenz halten die vorher festgelegte Regel (1 % und 3 %, gemessen 0,05 % und 1,3 %). Die Spanne
σ_n ≤ σ_hs ≤ 1,5·σ_n hält nicht: bei h 10 liegt der kleinste Wert 1,25 % unter σ_n. Die Annahme dahinter war, dass das
Querblech die Strukturspannung nur erhöhen kann; die über die Dicke linearisierte Strukturspannung im Übergangsschnitt
(93 bis 97 N/mm²) zeigt aber, dass die Oberseite dort örtlich entlastet wird – das einseitige Querblech hebt die
Schwerachse, die Zugkraft greift darunter an und biegt die Oberseite zurück. σ_hs ≈ σ_n ist damit plausibel, aber
nicht gegen eine unabhängige Referenz belegt. Auf Entscheidung des Anwenders (30.09.2026) gilt seither die Spanne
0,95 bis 1,5·σ_n mit dieser Begründung, und den Absolutwert prüft die Abnahme C1 gegen die Tet10-Referenz des
Hauptprogramms. Die Prüfung rechnet h 10 (rund 70 s); die Konvergenz h 10 → h 5 (1,8 Mio. Freiheitsgrade, 25 Minuten)
läuft nur auf Verlangen (`VOLUMEN3D_LANG=1`).

**Nachtrag (C2, 02.10.2026): Anwendbarkeit.** Die Blechseite wird nicht mehr allein an der Werkstofftiefe erkannt, sondern daran, dass die Oberfläche längs des Asts
von 0,05 t bis 1,0 t eben bleibt und darunter t Werkstoff liegt; vorher blieben Kehlnähte mit Schenkel unter 0,495 t und Stumpfnähte ohne Wert, und ein Blechende
vor 1,0 t gab still +70 %. Gültig für ebene Bleche und Rohre mit Radius über 5,7 t (11.19, G2-1/G2-2).

### 11.14 Teilprojekt 5: adaptive Zyklen und Konvergenzkurve (30.09.2026)

**Was der Vertrag verlangt.** `FcmSettings.adaptive_cycles` wählt die Zahl der Zyklen, `DetailResult.convergence` trägt je
Zyklus Freiheitsgrade, Hot-Spot und weitere Größen, und das Protokoll soll „alle Einstellungen“ nennen, damit der Nachweis
prüffähig ist (Vorgabe 8.4 und 11.3). Die Kurve über die Freiheitsgrade ist Pflichtbestandteil jedes Detailnachweises.

**Zyklen** (`FcmSolver.solve`, ohne Fehlerschätzer – der kommt mit TP 6). Zyklus 0 ist die Rechnung der Einstellungen. Jeder
weitere Zyklus ändert genau eine Sache, damit der Schritt an der Kurve ablesbar bleibt. Ungerade Zyklen halbieren lokal die
Zellgröße: um Punkte der Nahtlinien im Abstand höchstens t (Kugeln vom Radius 2·t) wird die Zielzellgröße gegenüber dem
Vorzyklus halbiert. Gerade Zyklen erhöhen p um eins, bis p = 4; danach wird stattdessen verfeinert (Fahrplan bis 01.10.2026; seither gilt „zuerst
lokal h bis t/4, dann p + 1“, siehe unten, und ein h-Schritt ohne Wirkung auf das Netz wird übersprungen, 11.19). Ohne Naht gibt es
keine Stelle für die lokale Verfeinerung: dann nur p + 1, und bei p = 4 endet die Folge mit einer Warnung. Jeder Zyklus ist
eine vollständige Diskretisierung (neues Gitter, eigene Zwangsmatrix, eigene Löserwahl), das Ergebnis des Vertragswegs ist der
letzte Zyklus; die früheren bleiben als Einträge der Kurve. Mehr als vier Zyklen lehnt der Vertragsweg ab (Vorgabe: 2 bis 4).
Ein Abbruch zwischen den Zyklen meldet `SolverCancelled`; der Fortschritt teilt jeden Zyklus in Vorbereitung (40 %) und Lösen.

**Kurve.** Je Zyklus ein Eintrag: `cycle`, `step` (Start, h-Halbierung Naht, p-Erhöhung), `dofs`, `p`, `cells`, `cut_cells`,
`h_min_mm`, `hotspot_max`, `hotspot_mean`, `stress_max` (größte Von-Mises-Spannung an den Oberflächenpunkten; an scharfen
Kerben wächst sie mit der Verfeinerung und ist darum kein Konvergenzkriterium), `solver_path`, `iterations`, `t_s` und
`hotspot_change` (relative Änderung gegenüber dem Vorzyklus).

**Konvergenzaussage** (`postprocess/konvergenz.py`, `protocol["convergence_statement"]`; Kriterium seit O4, 02.10.2026, begründet im Nachtrag unten). Aus `hotspot_max` der
Zyklen, ohne Raten: bei weniger als drei Werten „zu wenige Zyklen“; sonst bewertet die Aussage die **letzte relative Änderung** r = |σ_n − σ_(n−1)|/|σ_(n−1)| gegen die
Schranke 3 % (die Zahl der Vorgabe 13 für den Hot-Spot gegen Tet10, für die Konvergenz übernommen (O4); die Vorgabe verlangt für die Konvergenz nur die Kurve, 11.3) – „konvergiert“ bei r < 3 %, sonst „nicht konvergiert“ (dazu `kein_hotspot` und `ohne_aenderung`). Die Monotonie (mit Δ_k = σ_k − σ_{k−1} alle Δ_k
mit demselben Vorzeichen und |Δ_{k+1}| < |Δ_k|) wird zusätzlich genannt, ist aber keine Bedingung. Nur bei einer monotonen Folge gilt die Aitken-Extrapolation
σ_∞ = σ_n + Δ_n·q/(1 − q) mit q = Δ_n/Δ_{n−1}, die für
eine geometrische Folge den Grenzwert exakt trifft (Prüfung: 100 + 10·0,5ᵏ und 100 − 10·0,6ᵏ ergeben 100 auf 10⁻¹²), und die
Restabweichung |σ_n − σ_∞|/σ_∞ sagt, wie weit der letzte Zyklus noch entfernt ist. Eine schwingende oder wachsende Folge
bekommt keinen Grenzwert; die Änderungen und die Monotonie stehen im Text, `nicht_konvergiert` und `ohne_aenderung` tragen eine Warnung, und die Werte stehen im Protokoll. Dass ein Hot-Spot von unten
gegen den Grenzwert läuft, ist normal (T-Stoß h 10 → h 5: 100,43 → 100,93 N/mm²); das „fällt“ der ursprünglichen Planzeile
war als „konvergiert monoton“ gemeint.

**Protokoll der Einstellungen** (`protocol["settings"]`, je Zyklus): p, Zellgröße, Verfeinerungsbereiche mit Mitte, Radius
und Zielgröße, α, Toleranz des Vertrags und die verwendete (das Mehrgitter rechnet bis 10⁻¹²), Kopplungsart, Zyklenzahl und
Schritt, angeforderter und benutzter Rechenweg mit Löserweg, Moment Fitting und sein Grad, Art der ausgegebenen Spannung
(geglättet oder roh), Aggregationsschwelle, Nähte mit Kennung, Punktzahl, Blechdicke und Verfahren, Vertrags- und Paketversion.
Dazu trägt das Protokoll `cycles`, `convergence_statement`, `hot_spot` (11.13) und `stress_recovery` (11.12).

**Prüfungen** (`tests/test_adaptiv.py`, die schnellen in der Kernsuite). (1) Die Aussage als reine Funktion gegen geschlossene
Formen (geometrisch von oben und unten, schwingend, wachsend, zwei Werte, fehlender Wert, konstant, Null nach monotoner Annäherung) und gegen die gemessenen Folgen von
Knotenblech und T-Stoß (Nachtrag O4). (2) Kragarm-Ausschnitt ohne Naht
mit zwei Zyklen: p 2 → 3 → 4 mit 6 237 → 19 200 → 43 407 Freiheitsgraden, alle Felder der Kurve und des Protokolls, der letzte Zyklus
stimmt mit der Rechnung mit p 4 ohne Zyklen auf 4,5·10⁻⁹ überein, der Fortschritt steigt monoton bis 1. (3) Grenzen: Zyklenzahl
außerhalb 0 bis 4 wird abgelehnt, p 4 ohne Naht endet mit Warnung, der Abbruch greift zwischen den Zyklen. (4) T-Stoß unter Zug
über den Vertragsweg (nur mit `VOLUMEN3D_LANG=1`, 27 s auf vier Kernen): Schritte, Freiheitsgrade und Kopplungskontrolle
(Kraft 1,32 % seit C2, bei B4 1,38 %) stimmen, alle Hot-Spot-Werte liegen zwischen 0,5 und 1,5·σ_n, die Aussage stimmt mit der nachgerechneten letzten Änderung (13 %: nicht konvergiert) und der
Monotonie überein, und die nicht konvergierte Kurve trägt die Warnung.

**Messung in B4: die Konvergenzforderung des Plans war nicht erfüllt** (die Folgen daraus stehen unten: Fahrplan seit 01.10.2026, Kriterium seit O4). Vorab festgelegt war: am T-Stoß (Basiszellgröße 20, p 2, drei Zyklen)
konvergiert `hotspot_max` monoton, die letzte Änderung liegt unter 3 %. Gemessen:

| Start | Zyklen (Freiheitsgrade, `hotspot_max` in N/mm²) | Aussage |
|---|---|---|
| h 20, p 2, drei Zyklen | Start 2 079: 81,1 → h/2 6 240: 119,0 → p 3 18 639: 134,2 → h/2 80 388: 91,0 | nicht monoton |
| h 20, p 2, vier Zyklen | dazu p 4 182 493: 121,5 | nicht monoton |
| h 10, p 2, zwei Zyklen | Start 10 725: 119,8 → h/2 29 514: 127,6 → p 3 92 208: 110,1 | nicht monoton |
| h 10, p 3, ein Zyklus | Start 32 718: 138,3 → h/2 92 208: 110,1 | zwei Werte |

Die Werte sind längs der Naht glatt (am letzten Zyklus 120,2 bis 121,5 an der rechten, 116,2 bis 117,4 an der linken Naht), es ist
also kein Punktrauschen. Zwei Wege zur selben Diskretisierung (Start h 10 mit p 2 und Zyklen, Start h 10 mit p 3 und einem
Zyklus: lokale Zellgröße 5, p 3, 92 208 Freiheitsgrade) liefern denselben Wert 110,073. Die Schwankung von ±15 % zwischen
ähnlich feinen Gittern (91, 110 und 122 bei 5 mm lokal und p 3, p 3, p 4) kommt von der Lage der Referenzpunkte: Sie liegen bei
0,4 t = 4 mm und 1,0 t = 10 mm vom Nahtübergang, also bei Zellen von 5 bis 20 mm in der ersten Zellschicht an der
Kerbe, und die Spannung dort hängt an der singulären Stelle. Eine monotone Kurve braucht lokal Zellen von etwa 2 mm
(0,4 t reicht dann über zwei Zellen), und das sind bei zwei Nähten mehr als eine Million Freiheitsgrade; das ist auf der belegten
Maschine nicht gerechnet. Die Zykluslogik selbst (Wechsel h/p) ist damit nicht als Ursache belegt und nicht als unschuldig; sie wechselt
Schritte, deren Wirkung sich überlagert. **Folge (Anwender, 01.10.2026):** der Fahrplan wurde auf „h zuerst“ umgestellt, lokale Zellgröße
bis t/4 an den Nähten (Referenzpunkt 0,4 t mindestens 1,6 Zellen vom Übergang), dann p + 1; die Konvergenz am echten Knotenblech der Abnahme
C1 wurde danach gemessen (11.18), und das Kriterium der Aussage änderte sich mit O4 (oben und Nachtrag).

Dazu zwei Beobachtungen zur geglätteten Spannung. Die größte Von-Mises-Spannung an den Oberflächenpunkten wächst roh mit der
Verfeinerung (123,5 → 133,5 → 131,8 → 170,9 → 202,9 N/mm² über fünf Zyklen, die singuläre Kerbe), die geglättete bleibt bei 123 bis 134:
die L²-Projektion kappt die Spitze. Das ist für den Hot-Spot gewollt, für eine Kerbspannung (Vorgabe 11.2) nicht; dafür gibt es
die Rohspannung (`Auswertung.spannung`). Und: rohe und geglättete Hot-Spots unterscheiden sich im letzten Zyklus um 10 % (121,5 gegen
110,5 bei p 4), ein weiteres Zeichen, dass die Referenzpunkte noch in der Zone der Kerbstörung liegen.

**Befund in B4: Zwangszyklus bei lokaler Verfeinerung an Nähten.** Schon der erste h-Schritt (Ziel 10 an den Nähten, Basis 20, p 2
und p 3) brach den Konstruktor mit „Zwangszyklus an Mode … (Koeffizient 1, Rest 2,45)“. Ursache: eine grobe, schlecht geschnittene Zelle
ohne Wurzel (Ebene 0, Anteil 0,18; sie behält α) teilt eine Ecke mit feineren, an eine Wurzel gebundenen Zellen. Die feinere Zelle
band die gemeinsame Ecke an ihre Wurzel, während ein hängender Mode ihrer Nachbarzelle an der groben Zelle hängt und die Wurzel denselben
Mode enthält: 803 → 192 → 803, und mit Rest ungleich null ist das keine Tautologie, sondern ein widersprüchlicher Zwang. Die Regel
„Eigentümer eines geteilten Modes ist die gröbste schlechte Zelle“ lief nur über Zellen mit Wurzel. Seither zählt auch die unverwurzelte
schlechte Zelle (ohne die werkstoffferne); ist sie gröber als die Zelle, die den Mode binden würde, bleibt der Mode frei. Am T-Stoß mit
zwei lokalen Halbierungen (829 Zellen) sind das 12 Moden. `test_zwaenge.test_unverwurzelte_grobe_zelle` schlägt ohne die Änderung fehl.
Die Änderung liegt in `Zellaggregation.roh_zwaenge` und trifft nur Konstellationen, die vorher entweder einen Zyklus oder eine
Bindung über die feinere Zelle hatten; alle leichten Suiten sind unverändert grün. An den 23 Modellen der schweren Suiten (Kirsch h 20, 14 und 10
mit fünf Lagen, Lamé p 2 und 3, Kragarm, Block h 25, 20, 14, Patch, Operator-Kirsch) sperrt die Änderung nur an einem Modell Moden, Kirsch h 20
mit Versatz 0,6 (zwei Moden); dort sind K_t (3,12035926) und 802 Spannungen bitgleich mit und ohne Änderung. Die schweren Suiten rechnen
damit dieselben Zahlen und wurden nicht wiederholt.

**Offener Punkt: Konsistenzfehler am T-Stoß mit lokaler Verfeinerung.** Ein Feld im Ansatzraum wird am T-Stoß nicht auf Rundungsniveau
reproduziert, wie es die Patch-Tests (10⁻¹⁰ bis 10⁻¹³, auch mit Verfeinerung) zeigen: das quadratische Feld u = (c x²/2, 0, 0) mit
konstanter Volumenkraft ergibt an 1 500 Werkstoffpunkten σ_xx-Fehler von 3,3·10⁻⁶ (p 2, Ziel 5), 9,5·10⁻⁶ (p 2, Ziel 10) und 2,6·10⁻⁵
(p 3, Ziel 10); ein lineares Feld 5,6·10⁻⁷ (p 2) und 6,6·10⁻⁵ (p 3). Es ist keine Rundung (Residuum des Gleichungssystems 4·10⁻¹⁶,
ein Nachiterationsschritt ändert nichts) und sitzt nicht an den freigelassenen Moden (dort höchstens 3,7·10⁻⁷), sondern breit in den feinen
Zellen um die Naht, auch in vollen Zellen. Teilursachen sind belegt: die Tetraederregel der Schnittzellen (Grad 3p − 1; mit Ordnung 8 sinkt der
p-2-Fehler auf 3,7·10⁻⁷) und α (p 3: 1,1·10⁻⁵ bei 10⁻⁸, 1,2·10⁻⁶ bei 10⁻¹²); ein Rest ist ungeklärt. Gegen den Diskretisierungsfehler der
Strukturspannung (1 %) ist das klein, gegen das Patch-Niveau nicht; die Prüfung nimmt die gemessene Schranke 10⁻⁴.

**Nachtrag (O5, 03.10.2026): geklärt in 11.21.** Der Fehler des quadratischen Felds bei p 2 kam von der Tetraederregel der schräg geschnittenen Stücke (behoben), der Fehler des linearen Felds und der ganze Fehler bei p 3
von α in drei bzw. neun schlecht geschnittenen Zellen ohne Wurzel am Querblech (10 mm dick in 20-mm-Zellen, Nachbarn feiner); dort ist der Fehler bei p 2 genau proportional zu α. Der „ungeklärte Rest“ war dieser α-Anteil
und, bei α 10⁻¹², die Rundung über die schwach gestützten Moden. „Kein Rundungsfehler, weil das Residuum 4·10⁻¹⁶ ist“ war kein gültiger Schluss: das Residuum sagt nichts über die Verstärkung.

**Neuer Fahrplan seit 01.10.2026 (Entscheidung des Anwenders: zuerst lokal h bis t/4, dann p + 1).** Die Zielzellgröße an der Naht i ist
nach k Halbierungen max(h₀/2ᵏ, tᵢ/4); gehalbiert wird, solange eine Naht darüber liegt (`_fahrplan` in `api.py`, als reine Funktion gegen die Formel
geprüft: sechs Fälle mit Basis 20, 10 und 2,5, einer und zwei Nähten, ohne Naht, p 4), danach p + 1 bis p = 4, dann Ende mit Warnung. Am T-Stoß
(Basis 10 = t, p 2, vier Zyklen, freie Maschine) ergibt das:

| Zyklus | Schritt | p | Freiheitsgrade | kleinste Zelle | `hotspot_max` | `hotspot_mean` | Zeit |
|---|---|---|---|---|---|---|---|
| 0 | Start | 2 | 10 725 | 10 mm | 119,80 | 116,58 | 1 s |
| 1 | h-Halbierung Naht | 2 | 29 514 | 5 mm | 127,58 | 122,29 | 5 s |
| 2 | h-Halbierung Naht | 2 | 120 699 | 2,5 mm (= t/4) | 110,99 | 108,96 | 19 s |
| 3 | p-Erhöhung | 3 | 387 672 | 2,5 mm | 107,45 | 106,62 | 96 s |
| 4 | p-Erhöhung | 4 | 895 569 | 2,5 mm | 107,93 | 107,51 | 370 s |

Längs der Naht ist der letzte Zyklus glatt (106,9 bis 107,9 N/mm² an beiden Nähten). Die Änderungen sind +7,78, −16,59, −3,54 und +0,49 N/mm²: Mit der
Zellgröße t/4 ist die Zahl stabil, die p-Phase ändert sie um −3,2 % und dann um +0,45 %, der Hot-Spot liegt bei etwa 107,9 N/mm² (±0,5 %). Die Aussage
lautete in B4 „nicht monoton“ (seit O4: „konvergiert, Folge nicht monoton“), weil die frühen, noch groben Halbierungen überschwingen (119,8 → 127,6 → 111,0); die vor der Messung festgelegte Forderung
„monoton konvergent, letzte Änderung unter 3 %“ ist damit in der zweiten Hälfte erfüllt (0,45 %) und in der ersten nicht. **Vorschlag aus B4, durch O4 ersetzt (Nachtrag):** die Aussage nur über die p-Phase bei fester feinster Zellgröße zu bilden (ab dem ersten Zyklus mit h_min = t/4) und dort eine kleine letzte Änderung
(unter 1 %) statt strenger Monotonie zu verlangen – sie wäre hier erfüllt (110,99 → 107,45 → 107,93). Die frühere Schätzung „über eine Million Freiheitsgrade“ für
Zellen von 2 mm war zu pessimistisch: bei p 2 sind es 120 699, erst p 4 erreicht 895 569 (370 s, 17 GB Hauptspeicher). Die größte geglättete Von-Mises-Spannung wächst
auch geglättet mit der Verfeinerung (132,7 → 158,2 → 172,6 → 189,2 N/mm² von Zyklus 1 bis 4): die Kerbe ist singulär. Die Messung am Knotenblech bleibt C1.

**Nachtrag (O4, 02.10.2026): Kriterium der Konvergenzaussage.** Entscheidung des Anwenders: die Aussage bewertet die **letzte relative Änderung** r = |σ_n − σ_(n−1)|/|σ_(n−1)|
(wie `hotspot_change`) gegen die Schranke **3 %** (`KONVERGENZ_SCHRANKE`; die Zahl der Vorgabe 13 für den Hot-Spot gegen Tet10, für die Konvergenz übernommen (O4); die Vorgabe verlangt für die Konvergenz nur die Kurve, 11.3): `konvergiert` bei r < 3 %, sonst `nicht_konvergiert`; `kein_hotspot`, `zu_wenige_zyklen` und `ohne_aenderung`
bleiben. Die **Monotonie** (alle Änderungen mit demselben Vorzeichen, betragsmäßig abnehmend) wird zusätzlich genannt (`monoton`), ist aber keine Bedingung; nur bei monotoner Folge gibt es den
Aitken-Grenzwert mit der Restabweichung (wie oben). Der Text nennt immer beides – „letzte relative Änderung 0,44 % < 3 %: konvergiert; Folge nicht monoton (Änderungen −5,64, −18,28, −14,53,
+0,63 N/mm²)“. Die Warnung im Ergebnis gilt `nicht_konvergiert` und `ohne_aenderung`; eine konvergierte, nicht monotone Folge trägt nur den Hinweis im Text. Warum: die Folgen der frühen h-Schritte
schwingen immer (Knotenblech 181,1 → 175,4 → 157,1 → 142,6 → 143,2, T-Stoß 119,8 → 127,6 → 111,0 → 107,4 → 107,9); „nicht monoton, keine Aussage“ sagte dem Anwender nicht, was er wissen muss, obwohl der
letzte Schritt unter 0,5 % lag. Mit dem neuen Kriterium: Knotenblech r 0,44 % und T-Stoß (p-Phase) r 0,45 % konvergiert, beide nicht monoton; das T-Stoß-Ergebnis mit zwei Zyklen
(119,8 → 127,6 → 111,0, r 13 %) nicht konvergiert (Warnung). (Die erste Fassung dieses Nachtrags und der Planregeln nannte für den T-Stoß 0,47 %: gerechnet aus den auf eine
Stelle gerundeten Werten 107,4 und 107,9; mit den gemessenen 107,446 und 107,932 N/mm² sind es 0,45 %. Berichtigt bei C3; der Test rechnet jetzt mit den ungerundeten Werten.) **Bekannte Schwäche:** eine Folge mit großem Überschwinger vor einer kleinen letzten Änderung gilt als konvergiert ([100, 120, 90, 90]:
r = 0, konvergiert, nicht monoton) – die Änderungen und die Monotonie stehen deshalb daneben im Text, und die Kurve selbst (`convergence`) liegt dem Nachweis bei. Geprüft in
`test_adaptiv.test_konvergenzaussage` (Erwartungswerte von Hand: 110/105/102,5/101,25 r 1,22 %, [100, 103, 101, 102] r 0,99 %, [100, 101, 103, 107] r 3,88 %, die gemessenen Folgen) und in
`test_zyklen_t_stoss`.

### 11.15 Teilprojekt 5: STEP-Eingang über gmsh-Tessellierung (01.10.2026)

**Verfahren** (`geometry/step.py`, Vorgabe 3). `GeometrySourceType.STEP` liest die Datei mit gmsh (OpenCASCADE), tesselliert die Oberfläche zu Dreiecken
und gibt sie als Hülle an den bestehenden STL-Weg (Windungszahl für innen und außen, Orientierung, Abstand, Facettenprüfung): die Geometrie bleibt eine
Innen/Außen-Funktion, die Krümmung steckt nur in der Tessellierung. Angaben in `GeometrySource.params`: `tessellation_mm` (größte Facette, Vorgabe die
Basiszellgröße) und `elements_per_circle` (Dreiecke je Vollkreis, Vorgabe 120), `name`. Die Einheit rechnet gmsh beim Lesen von der in der Datei
deklarierten nach mm um (`Geometry.OCCTargetUnit = MM`; geprüft mit einer Datei, deren Kopf auf Meter umdeklariert ist: die Ausdehnung wird tausendfach).
Mehrere Körper werden zu einer Hülle zusammengefasst, sich durchdringende sind nicht zulässig (Stand B5; seit C2 werden STEP-Körper vereinigt und durchdringende STL-Schalen mit einem Fehler abgewiesen, 11.19). gmsh ist **optional** (Extra `step` in
`packages/volumen3d/pyproject.toml`, `pip install "gmsh>=4.11"`, GPL-Lizenz, nicht gebündelt); ohne gmsh gibt es `SolverError` mit dem Installationshinweis. Die
Bibliothek wird nicht unterbrechbar und ohne Konfigurationsdateien initialisiert (Arbeitsfäden), ein schon laufendes gmsh des Aufrufers bleibt unberührt
(eigenes Modell, Optionen und aktuelles Modell werden zurückgesetzt). Fehlerfälle mit klarer Meldung: Datei fehlt, kein Pfad, keine STEP-Datei, nur eine
Fläche statt eines Körpers, zu grobe Tessellierung. Die Tessellierung steht im Protokoll (`step_tessellation`: Quelle, Dreiecke, Körper, Flächen, Facettengröße,
Dreiecke je Vollkreis, gmsh-Version, Hüllquader); Ergebnisse einer Datei werden zwischengespeichert, damit `estimate` und `prepare` einmal tessellieren.

**Genauigkeit der Tessellierung** (Block 210 × 200 × 200 mm mit Bohrung r 40, Facette 25 mm): Die Ecken liegen auf der Fläche (einbeschriebenes Polygon), der
Volumenfehler der Bohrung ist (2π/N)²/6 ihres Volumens:

| Dreiecke je Vollkreis N | Dreiecke | Volumen gegen die geschlossene Form | Grenze (2π/N)²/6 des Bohrungsvolumens |
|---|---|---|---|
| 60 | 7 810 | +0,0188 % | +0,0248 % |
| 120 | 27 788 | +0,0047 % | +0,0062 % |
| 240 | 107 636 | +0,0012 % | – |

Die Hülle ist wasserdicht (jede Kante gehört zu genau zwei Dreiecken), die Dreiecke der Stirnfläche zeigen nach außen, der Hüllquader stimmt auf 10⁻⁹ mm.
Durch den ganzen Vertragsweg stimmt ein STEP-Quader mit der CSG-Fassung überein: Volumen gleich, σ_xx an allen Oberflächenpunkten 100 N/mm² auf 1,3·10⁻¹⁰, Verschiebung
gegen das Zugfeld 1,3·10⁻⁸, Kopplungskontrolle 7·10⁻¹⁵ (ebene Flächen sind im STL-Weg exakt).

**Befund: gekrümmte STEP-Flächen sind im STL-Weg langsam und nur in erster Ordnung.** Ein Block mit Bohrung als STEP durch den Konstruktor des Problems
(Gitter, Quadratur, Aggregation, Zwänge, Oberflächenquadratur): N 16 mit 1 004 Dreiecken bei Zellen von 50 mm 206 s (CSG-Block bei Zellen von 25 mm: 4,6 s, Messung A6);
N 32 bei Zellen von 100 mm und ein Vollzylinder (konvex) mit N 48 bei 50 mm waren nach 580 s nicht fertig, der Vollzylinder mit N 24 bei 100 mm nach 70 s auch nicht. Beim
N-16-Lauf stecken 198 der 206 s in der Flächenquadratur der Polygonstücke, davon 174 s in `_bsp_teile`. Ursache: gmsh
tesselliert gekrümmte Flächen unstrukturiert, die Knoten liegen verstreut auf der Fläche, und ein solches Dreiecksnetz hat Kanten mit wechselndem Knickvorzeichen, also
kein konvexes oder konkaves Ebenenarrangement. Am Vollzylinder meldet `lokale_lage` bei Kugeln mit Radius 5 mm in 163 von 200 Fällen „konvex“, bei 15 mm in 128 von 200 Fällen
„gemischt“ und bei 43 mm in allen 200 (im Mittel 154 Ebenen je Kugel). Die Zerlegung an höchstens sechs Ebenen scheitert, die Flächenstücke werden rekursiv geviertelt, und
am Ende steht der Punkttest erster Ordnung. Das bestehende STL-Netz des Lamé-Tests (regelmäßig, Sehnen 1 mm) rechnet dagegen in 78 s. **Folgen:** Der Vertragsweg
meldet eine Warnung, wenn Blätter im Punkttest oder Flächenstücke im Rückfall stehen (`_integrationswarnung`, geprüft als reine Funktion; sie schweigt bei
ebenen Flächen), und die Prüfung läuft am ebenen STEP-Quader und an der Tessellierung des Blocks mit Bohrung, nicht am gekrümmten Körper. Ein Block mit Bohrung gegen CSG
(K_t) steht damit in B5 nicht im Test; B6 hat das nachgeholt (11.16: 0,12 % bei p 2). **Abhilfe (Entscheidung des Anwenders), in B6 umgesetzt:** eine Integration über die Dreiecke selbst (Divergenzsatz für das Volumen, Vorgabe 6
„oberflächenbasierte Integration“, Fläche je Dreieck exakt) statt der Zerlegung an lokalen Ebenen – ein eigener Schritt, naheliegend zusammen mit dem schnellen Windungszahl-Baum (B6).
Das galt bis B6; seither (11.16) behalten nur Zellen, in denen die Hülle auf eine andere aktive Form trifft (Schnitt- oder Symmetrieebene; bei ebenen Facetten exakt), und die Zellen offener Hüllen (11.19) den bisherigen Weg;
der Punkttest bleibt dort, wo eine Ebene durch den gekrümmten Teil der Hülle läuft.

**Prüfungen** (`tests/test_step.py`, in der Kernsuite, ohne gmsh übersprungen außer den Fehlerfällen und der Warnung, die ohne gmsh simuliert laufen): Tessellierung (Volumen
gegen die Formel, wasserdicht, Orientierung, Hüllquader, Einheit), Vertragsweg STEP-Quader gegen CSG, Integrationswarnung, Fehlerfälle.

### 11.16 Teilprojekt 5: exakte Integration tessellierter Hüllen und schneller Windungszahl-Baum (01.10.2026)

**Ausgangslage.** Nach 11.15 war der STL-Weg an gekrümmten, unstrukturiert tessellierten Hüllen langsam und nur erster Ordnung, weil die Zerlegung an
lokalen Ebenen bei gemischter Lage scheitert und am Ende der Punkttest steht. Der Anwender nahm die Empfehlung an: die Integration läuft über die Dreiecke
selbst, zusammen mit dem aus Teilprojekt 2 offenen Windungszahl-Baum (Plan TP 5 B6).

**Teil 1: Hüllenintegration über den Divergenzsatz** (`geometry/huelle.py`). Für eine achsparallele Zelle B = [lo, hi] und eine geschlossene, nach außen
orientierte Hülle Ω gilt mit G = (G_x, 0, 0), G_x(x, y, z) = ∫_{x_lo}^{x} g χ_B dx′ für polynomiales g

    ∫_{Ω∩B} g dV = Σ_Dreiecke T ∫_T G_x n_x dA,

denn div G = g χ_B, G_x ist in x stetig, und die Sprünge von G über die Ebenen y = const und z = const haben keinen Fluss (Normale senkrecht zu G); der Gaußsche
Satz über Ω braucht darum nur den Rand von Ω, nicht den Werkstoffteil der Zellflächen. Je Dreieck genügen das Clippen an den y- und z-Scheiben der Zelle und das
Teilen bei x_lo und x_hi: Teile mit x < x_lo tragen null, Teile mit x > x_hi den vollen, in x konstanten Wert ∫_{x_lo}^{x_hi} g dx′ – darum braucht die Zelle **alle**
Dreiecke der Säule x ≥ x_lo in ihrer y-z-Scheibe (`Dreiecksbaum.in_box` mit +∞), nicht nur die berührenden. Alles sind exakte Polygonoperationen ohne Zerlegung an
lokalen Ebenen und ohne Punkttest. Die Momente der Tensor-Legendre-Basis vom Grad q = 2p (Moment Fitting, 11.11) folgen in geschlossener Form: mit den Stammfunktionen
S_a(ξ) = ∫_{−1}^{ξ} N_a der hierarchischen 1D-Basis (S_0 = ξ/2 − ξ²/4 + 3/4, S_1 = ξ/2 + ξ²/4 + 1/4, S_j = (∫P_j − ∫P_{j−2})/√(2(2j−1)) über ∫_{−1}^{ξ} P_k = (P_{k+1} − P_{k−1})/(2k+1))
ist der Integrand auf einem ebenen Polygonstück ein Polynom vom Gesamtgrad 3q + 1 (laufende Stücke) bzw. 2q (volle Stücke, S_a konstant), den die kollabierte
Gauß-Jacobi-Regel der Fächerdreiecke exakt integriert; für die vollen Stücke ist die Punktsumme nur zweidimensional (das sparte am Block mit Bohrung N 120 16 von 22 s
der Hüllenmomente: 106 384 volle gegen 41 574 laufende Fächerdreiecke in 573 Zellen). Eine Zelle geht diesen Weg, wenn in ihrer Umkugel genau **eine** aktive
Grundform eine Hülle ist und der CSG-Baum über den vier Werten {leer, voll, Hülle, Komplement} (Schnitt = und, Vereinigung = oder, Differenz = und nicht; `Csg.huellenzelle`)
Hülle oder Komplement ergibt; beim Komplement (Hülle als Loch) sind die Momente Tensor-Gauß der Box minus Hülle. Zellen, in denen die Hülle eine andere aktive Form
trifft (Schnittebenen, Symmetrieebenen), behalten den bisherigen Weg. Flächenquadratur: ein Polygon auf einer Hüllenfacette wird nur von den **anderen** Formen geclippt
(`Csg.lokale_stuecke(..., ohne=form)`); ohne andere aktive Form ist es ohne Zeugentest Rand des Werkstoffs, die Normale ist die Facettennormale (mit dem Vorzeichen der Form im
Baum), der Abstandsfilter entfällt für Hüllenpunkte – das waren je Polygon bzw. je Punkt Windungszahlen über alle Facetten (Block mit Bohrung N 120: 35 000 Aufrufe
mit 47 s und 1 039 150 Punkte mit 59 s vor dem Umbau).

**Genauigkeit** (`tests/test_huelle.py`, Prüfung (1) des Plans, Schranke 10⁻¹²): Stammfunktionen bis Grad 10 an 17 Stellen gegen Gauß 3,3·10⁻¹⁶; achsparalleler
Würfel in sechs Lagen zur Zelle (Hülle gleich Zellbox, Zelle ganz innen, Ecke in der Zelle, Hülle ganz in der Zelle, Berührung bei x_hi von außen, Hüllenfläche auf einer
Zellfläche) alle Momente bis Grad 6 gegen Tensor-Gauß ≤ 2,2·10⁻¹⁶ des Zellvolumens; gedrehter Würfel in vier Lagen gegen Clippen und Tetraeder-Zerlegung ≤ 1,4·10⁻¹⁵;
gedrehtes L-Prisma (einspringende Kante) gegen die Summe der Teilquader ≤ 2,6·10⁻¹⁷; Quaderzelle 1:2:3 6,5·10⁻¹⁶; eine nach innen gewickelte Hülle liefert das negative
Volumen (kein Betrag). Im CSG-Baum: Block minus Loch, Loch im Schnitt, Hülle über einer Platte in der Vereinigung, Loch in einem Block 80³ (Lochzellen Hüllenzellen, ebene
Blätter wie ohne Loch), Hülle ∩ Halbraum (Hüllenzellen und ebene Blätter nebeneinander) – alle Volumen exakt. Die STL-Suite rechnet unverändert (Würfel, gedrehter Würfel,
L-Körper exakt, Lamé aus STL mit σ_r 0,070 % und σ_φ 0,024 % gegen Lamé), nur sind Schnittzellen einer reinen Hülle jetzt Hüllenzellen ohne Blätter; Lamé aus
STL (Viertelring, Sehnen 1 mm, p 3) braucht 44 s statt 78 s, die ganze STL-Suite 48 s statt rund 3 min.

**Zeiten** (Block 210 × 200 × 200 mm mit Bohrung r 40 als STEP, Konstruktor von `FcmProblem` mit Gitter, Quadratur, Aggregation, Zwängen und Oberflächenquadratur, 01.10.2026):

| Fall | vor B6 | nach B6 |
|---|---|---|
| N 16 (1 004 Dreiecke), Zellen 50 mm, p 2 | 206 s | 11,9 s |
| N 60 (7 810 Dreiecke), Zellen 25 mm, p 2 | 56,6 s (Netz regelmäßiger als bei N 16) | 16,8 s |
| N 120 (27 788 Dreiecke), Zellen 25 mm, p 3 | 388 s | 26,8 s (Planmarke 30 s; CSG-Block 4,6 s in A6) |

Beim N-120-Lauf sind alle 573 Schnittzellen Hüllenzellen (9 leer), kein Blatt im Punkttest, kein Flächenstück im Rückfall, das Werkstoffvolumen gleich dem Volumen der
Tessellierung auf 2,2·10⁻¹⁶. Im Profil (35,2 s unter cProfile) entfallen 24,5 s auf die Oberflächenquadratur der 27 788 Facetten (1 039 150 Punkte, 173 395 Polygonstücke, davon
8,9 s in `np.cross` an winzigen Feldern – seither als drei Skalarprodukte, 18,9 → 8,9 µs je Polygon) und 10,1 s auf die Hüllenzellen. **Durch den Vertragsweg** (Schnittebenen
x 0 und 200, Zug σ_n = 100 N/mm², h 25) gegen CSG mit dem exakten Zylinder – die in 11.15 offene Prüfung: K_t = max σ_xx am Bohrungsrand / σ_n bei p 2 2,7158 (STEP) gegen 2,7190
(CSG), 0,12 %; bei p 3 2,7503 gegen 2,7573, 0,25 % (Schranke 0,5 %); `prepare` 20 s gegen 7 s (p 2) bzw. 27 s gegen 13 s (p 3); 351 Hüllenzellen, kein Punkttest-Blatt. Die
Zellen an den Schnittebenen treffen dort nur ebene Facetten (Stirnflächen x = −5 und 205), die der alte Weg mit ebenen Blättern exakt integriert; Teil 3 des Plans
(Ebenenbereiche innerhalb der Hülle über den Divergenzsatz eine Dimension tiefer) ist darum nicht gebaut – er wird nötig, wenn eine Schnitt- oder Symmetrieebene durch den
gekrümmten Teil einer Hülle läuft; dort gilt weiter der Punkttest mit der Warnung aus 11.15.

**Teil 2: schneller Windungszahl-Baum** (`geometry/windung.py`, nach Barill, Dickson, Schmidt, Levin, Jacobson, „Fast Winding Numbers for Soups and Clouds“, ACM TOG 37(4), 2018).
Die Windungszahl w(q) = ∫_S f·n dA mit dem Dipolkern f(p) = (p − q)/(4π|p − q|³) wird je Knoten der vorhandenen BVH (`dreiecksbaum.py`) um den flächengewichteten Schwerpunkt p̃
bis zur zweiten Ordnung entwickelt; der Knoten braucht nur seine Momente N = Σ a_t n_t, M1[ij] = Σ n_ti ∫_T (p − p̃)_j dA und M2[ijk] = Σ n_ti ∫_T (p − p̃)_j (p − p̃)_k dA, die
hier **exakt über die Dreiecke** gebildet werden (∫_T (p − c) dA = 0, ∫_T (p − c)(p − c)ᵀ dA = (a/12) Σ_v (v − c)(v − c)ᵀ; Barill nehmen den Schwerpunkt als Punktmasse) und aus
Präfixsummen über die Dreiecke in Baumordnung ohne Rekursion folgen. Ein Knoten gilt als fern, wenn |p̃ − q| > β mal seiner Umkugel um p̃ (obere Schranke über die acht
Boxecken), sonst steigt die Suche ab; Blätter rechnen exakt (Van Oosterom und Strackee). Eingesetzt wird der Baum nur für die Innen/Außen-Entscheidung (`Stl.innen`, also
Abstand und Gradient) ab 20 000 Facetten; `Stl.windungszahl` und die Facettenprüfung beim Laden rechnen weiter exakt. Ohne numba gibt es keine BVH und keinen Baum.

**Messung** (Prüfung (4) des Plans: Tessellierung N 240 mit 107 636 Dreiecken, 100 000 Zufallspunkte, 60 % im Hüllquader mit 10 % Rand, 40 % bis 0,5 mm beidseits der Facetten;
BVH 0,63 s, Momente 0,13 s, exakte numba-Summe 11,1 s):

| β | |Δw| max | 99,9-%-Quantil | Zeit | gegen exakt | innen/außen gleich |
|---|---|---|---|---|---|
| 2 (Plan, nach Barill) | 9,9·10⁻³ | 8,0·10⁻³ | 0,150 s | 73-mal schneller | 100 000 / 100 000 |
| 2,5 | 2,9·10⁻³ | 2,0·10⁻³ | 0,223 s | 50-mal | 100 000 / 100 000 |
| 3 | 1,2·10⁻³ | 8,5·10⁻⁴ | 0,286 s | 39-mal | 100 000 / 100 000 |
| **4 (Vorgabe)** | 2,6·10⁻⁴ | 2,1·10⁻⁴ | 0,397 s | 28-mal | 100 000 / 100 000 |

Die Innen/Außen-Entscheidung stimmte bei jedem β an allen Punkten, die vorab gesetzte Schranke |Δw| < 10⁻³ hält erst mit β 4 – darum ist β 4 Vorgabe (`BETA_STANDARD`), nicht
das im Plan genannte β 2; die Geschwindigkeitsforderung (zehnmal) hält auch dort. Dass die Ordnungen stimmen, zeigt der Fehler mit abgeschnittener Reihe (20 000 Punkte, β 4):
nur Dipol 9,8·10⁻³, bis erste Ordnung 8,3·10⁻³, bis zweite Ordnung 2,5·10⁻⁴ (im Mittel 1,9·10⁻³ → 8,1·10⁻⁴ → 3,3·10⁻⁵; die erste Ordnung ist für ebene Flecken um den
flächengewichteten Schwerpunkt null). Mit β = ∞ liefert der Baum die exakte Summe auf 10⁻¹² (Blattrechnung und Durchlauf). In der Suite (`test_huelle.test_windungsbaum`,
Kugelschale r 50 mit 25 088 Facetten, 20 000 Punkte): gleiche Entscheidung, |Δw| max 1,5·10⁻⁴, 22-mal schneller. Am Block mit Bohrung N 120 bringt der Baum nur noch 1,5 s
(28,3 → 26,8 s), weil Teil 1 die meisten Windungszahl-Aufrufe schon beseitigt hat; er trägt bei feineren Netzen und überall dort, wo Zellen Hülle und andere Formen zugleich sehen.

**Regel (Plan B6) und Stand.** Die Hüllenintegration ersetzt für Hüllenformen die Zerlegung an lokalen Ebenen (`HUELLEN_EXAKT_STANDARD = True`, Schalter `huellen_exakt`
der Zellquadratur; Prüfungen (1) bis (3) halten), der Windungszahl-Baum ist Vorgabe ab 20 000 Facetten (Prüfung (4) hält mit β 4). Für gekrümmte CAD-Teile gilt die Empfehlung
„CSG verwenden“ aus 11.15 nicht mehr, solange keine Schnitt- oder Symmetrieebene den gekrümmten Teil der Hülle kreuzt; Volumen und Zellregeln sind für die Tessellierung
exakt, die Krümmung steckt nur in ihr (Bohrung N 120: Volumenfehler +0,0047 %, 11.15).

**Nachtrag (B7, 01.10.2026): Fehler im Flächenweg der Hüllen, behoben.** Mit dem Entfernen des Gesamtabstandsfilters für Hüllenfacetten blieben Facettenpolygone in Zellen stehen, in
denen eine Schnittebene für das Polygon inaktiv war, aber dahinter lag (Ausgabepunkte und Flächenlasten außerhalb des Details; das Volumen war nicht betroffen). Siehe 11.17,
Befund 2; die Zeiten und Genauigkeiten dieses Abschnitts bleiben gültig (die Flächenquadratur des Blocks N 120 hat keine Facetten hinter den Schnittebenen im Gitter).

**Prüfungen** (`tests/test_huelle.py` in der Kernsuite: Stammfunktionen, Polyeder-Momente, CSG-Baum und Zellquadratur, Windungsbaum; `tests/test_stl.py` mit der
Unterscheidung Hüllenzellen/alter Weg; `tests/test_step.py`: Block mit Bohrung durch den Vertragsweg gegen CSG mit `VOLUMEN3D_LANG=1`).

### 11.17 Teilprojekt 5: Schale → Volumen über die Vertragsschicht (01.10.2026)

**Prüfaufbau** (`tests/test_schale.py`, Plan TP 5 B7; die Kopplung an ein echtes Schalenmodell ist Sache des Providers im Hauptprogramm). Der Provider ist
ein Stub der Suite: ein Plattenstreifen (t = 10 mm, b = 100 mm, 200 mm zwischen den Schnittebenen) als Schalenmodell mit Reissner-Mindlin-Kinematik. `displacement_at`
liefert die Mittelflächenverschiebung u₀ plus Rotation θ mal Normalenabstand z′ (lineare Verteilung über die Dicke, u = u₀ + θ × z′e_z), `section_forces` die
Schalenresultierenden je Breite (n_x = E t ε₀, m_x = E t³ κ/12) über die Schnittbreite integriert, mit der Seitenkonvention des Vertrags. Zustand: Membrandehnung ε₀ und
Krümmung κ bei freien Längsrändern (n_y = m_y = 0): u₀ = (ε₀x′, −νε₀y′, w) mit w = −κ(x′² − νy′²)/2, θ = (νκy′, κx′, 0). Das ist die exakte 3D-Lösung des freien Streifens
bis auf die Dickendehnung (u_z′ ∋ −νκz′²/2 und −νε₀z′), die die Schalentheorie nicht kennt; der Vertragsweg legt an den Schnittebenen nur die Normalkomponente
punktweise und die Mittelwerte der Tangentialkomponenten fest (11.6), die fehlende Dickendehnung verschiebt darum den Streifen nur starr (Mittelwert νκt²/24 = 5·10⁻⁴ mm).
Fälle: (A) achsparallel (CSG-Quader, Schnittebenen x 0 und 200), (B) um 10° und 30° um die y-Achse geneigt (STL-Hülle, schräge Schnittebenen, prüft B6 und die schräge
Kopplung zugleich); je Fall Membran (σ_m = 100 N/mm²), Biegung (Randspannung 150 N/mm²) und beides; Zellen 25 mm.

**Messwerte** (h 25; Kraft und Moment sind die Abweichungen der Kopplungskontrolle gegen den Provider, σ die größte Abweichung von σ_x′ = E(ε₀ + κz′) in lokalen
Schalenachsen an allen Oberflächenpunkten bezogen auf den Größtwert, Gleichgewicht der Resultierenden beider Ebenen um die Streifenmitte):

| Fall | Kraft | Moment | σ_x′ | übrige Komponenten | Gleichgewicht |
|---|---|---|---|---|---|
| A, p 2, drei Lastfälle | ≤ 2,1·10⁻¹² | ≤ 2,7·10⁻¹² | ≤ 5,0·10⁻⁷ | ≤ 6,4·10⁻¹² | ≤ 1,9·10⁻¹¹ |
| B 30°, p 2 | ≤ 6,7·10⁻⁴ | ≤ 2,3·10⁻⁴ | ≤ 2,2·10⁻⁴ | ≤ 8,2·10⁻⁵ | ≤ 4,2·10⁻³ |
| B 10°, p 2 | ≤ 7,7·10⁻⁵ | ≤ 3,5·10⁻⁵ | ≤ 3,5·10⁻³ | ≤ 1,3·10⁻³ | ≤ 4,6·10⁻⁴ |
| B 30°, p 3 | ≤ 2,4·10⁻⁸ | ≤ 6,0·10⁻⁸ | ≤ 5,3·10⁻⁷ | ≤ 1,4·10⁻⁷ | ≤ 2,2·10⁻⁷ |
| B 10°, p 3 | ≤ 2,4·10⁻⁸ | ≤ 1,8·10⁻⁸ | ≤ 2,5·10⁻⁶ | ≤ 1,0·10⁻⁶ | ≤ 1,2·10⁻⁷ |

Die Vorgabe (Schnittgrößenabweichung unter 1 %) ist in allen Fällen mit mindestens zwei Größenordnungen Abstand erfüllt, ohne Kopplungswarnung. Die Verschiebung der Lösung
stimmt mit der exakten 3D-Lösung nach Abzug des Starrkörperanteils auf 2,5·10⁻⁸ (A und p 3) bzw. 9,9·10⁻⁷ (10°, p 2) des Größtwerts überein; die größeren Spannungsabweichungen bei p 2 am
schrägen Schnitt sind also Konsistenzfehler der Schnittzellen, die in der Spannung (Gradient) stärker auftreten.

**Befund 1: die Kopplungskontrolle meldete bei reiner Biegung 100 % Kraftabweichung.** Der Kraftbezug war die größere der beteiligten Kräfte; bei reiner Biegung ist die Kraft im
Globalmodell null und im Detail nur ein Rest (2·10⁻⁸ N achsparallel, 0,01 und 5,3 N an den beiden Ebenen des geneigten Streifens, Moment 2,5·10⁵ N·mm), also |F|/|F| = 1,0 und eine Warnung „> 5 %“. Das Moment hatte seit dem Gutachten vom 27.09. einen Bezug mit Kraft mal Länge. Jetzt
haben beide ein gemeinsames Lastmaß (`api._kopplungsabweichung`; Stand B7, seit C2 werden die Abweichungen als Spannungen bewertet, Nachtrag unten): ref_m = max(|M|, |m_g|, f₀·l), ref_f = ref_m/l mit l = √Schnittfläche, f₀ die größte beteiligte Kraft; ein Kraftrest wird
also gegen die Kraft gemessen, die dasselbe Moment am Hebel l aufbrächte. Folge: bei momentbestimmten Zuständen wird eine Querkraftabweichung gegen das größere Lastmaß M/l bezogen,
die Warnschwelle 5 % liegt entsprechend später (z. B. Querkraft 900 gegen 1000 N bei 4·10⁵ N·mm: 2,5 % statt 10 %); eine Kraft, die das Globalmodell nicht kennt, bleibt als Abweichung 1,0
sichtbar (geprüft als reine Funktion).

**Befund 2: Hüllenfacetten hinter einer Schnittebene blieben als Oberfläche stehen (Fehler aus B6, behoben).** Für Facettenpolygone einer Hülle hatte B6 den Gesamtabstandsfilter
entfernt (11.16); `Csg._stuecke_ohne` gab bei „keine andere Form aktiv“ die ganze Kugel zurück, auch wenn die Mitte hinter einer inaktiven Schnittebene lag. Facetten kleiner als der
Abstand zur Ebene (bei Tessellierungen fast alle) galten so als Rand des Werkstoffs: an der Kugelhülle mit Halbraum 6 030 Oberflächenpunkte hinter der Ebene und 30 324,6 statt
28 513,3 mm²; am geneigten Streifen lagen Ausgabepunkte außerhalb des Details, deren Spannung extrapoliert war (in zwei Läufen dort der größte gemessene Fehler: 2,8·10⁻⁴ bei h 25 und 1,6·10⁻³ bei h 12,5, nach der Korrektur 2,2·10⁻⁴ und 2,4·10⁻⁴).
Der Baum entscheidet jetzt auch ohne aktive Form (inaktive Formen zählen als voll oder leer nach dem Vorzeichen des Abstands), und ein Polygon ohne Werkstoff in der Kugel entfällt.
Das Volumen war nicht betroffen (Zellklassifikation), wohl aber Ausgabepunkte und Flächenlasten auf Hüllenflächen hinter Schnittebenen. Prüfung: Kugelhülle ∩ Halbraum, Oberfläche
gegen die unabhängige Summe aus geclippten Facetten und konvexer Kappe auf 3·10⁻¹⁵, keine Punkte hinter der Ebene (`test_huelle.test_flaeche_hinter_schnittebene`).

**Befund 3 (geklärt und behoben mit O5, 11.21): Konsistenzfehler des p-2-Ansatzes am schrägen Schnitt.** Das Feld liegt im Ansatzraum (quadratisch), p 2 reproduziert es am geneigten Streifen aber nur auf
2·10⁻⁴ bis 3,5·10⁻³ in der Spannung, p 3 auf 10⁻⁶, der achsparallele Fall auf 10⁻⁷. Ohne Einfluss sind α (10⁻⁸ gegen 10⁻¹²), Moment Fitting (an/aus), die Flächenquadraturordnung (Vorgabe, 6, 10) und die
Teilungstiefe (2, 3); deutlichen Einfluss hat die Aggregationsschwelle (Spannung bei 10°: Schwelle 0,4 → 3,5·10⁻³, 0,2 → 1,7·10⁻², ohne Aggregation 1,3·10⁻¹). Die Hüllenintegration (B6) verbessert den Fall
(30°: 1,2·10⁻³ → 2,2·10⁻⁴). Das passt zum schon bekannten offenen Konsistenzfehler 10⁻⁶ bis 10⁻⁴ am T-Stoß (Theorie 11.14); die Ursache ist nicht geklärt und kein Teil von B7. Der Fehler
liegt deutlich unter der Vorgabeschranke; Gleichgewichtsrest und Schnittgrößenabweichung treten mit ihm auf und verschwinden bei p 3 gemeinsam mit ihm (am geneigten Streifen p 2 bleibt ein Kraftrest von 5,3 N bei 7 906 N Lastmaß).

**Schranken.** Die im Plan vorab gesetzte Schranke 10⁻⁶ für das Gleichgewicht der Resultierenden war geraten und wird für p 2 am schrägen Schnitt nicht gehalten (4,2·10⁻³); sie gilt
achsparallel mit 10⁻⁹ (gemessen 1,9·10⁻¹¹) und bei p 3 mit 10⁻⁵ (gemessen ≤ 2,5·10⁻⁶); für p 2 geneigt gilt die Vorgabeschranke 1 % (vom Anwender am 01.10.2026 angenommen).

**Prüfungen** (`tests/test_schale.py` in der Kernsuite: Kontrollgröße als reine Funktion, achsparallel, geneigt p 2 mit Punkten zwischen den Ebenen, geneigt p 3; `tests/test_huelle.py`:
Hüllenfläche hinter der Schnittebene).

**Nachtrag (C2, 02.10.2026): Kopplungskontrolle als Spannung.** Das gemeinsame Lastmaß mit dem Hebel √A (Befund 1 oben) verschleierte Momentfehler an dünnen
Blechen: am Plattenstreifen b 100, t 10 mit Membran 100 und Biegung 150 N/mm² ist F·√A das Zwölffache des Moments, ein Detail mit nur 40 % des Moments meldete
4,7 % statt einer Warnung (Gutachten C2, G3-3). Jetzt werden die Abweichungen als Spannungen bewertet (`api._schnittkennwerte`, `_kopplungsabweichung`):
Querschnittswerte der Schnittquadratur (Fläche, Schwerpunkt, Trägheiten), Moment auf den Schwerpunkt umgerechnet, Kraftanteil (|ΔN| + |ΔQ|)/A, Momentanteil die
größte Randspannung aus ΔM (Biegung, dazu Torsion über das polare Moment), beides bezogen auf die größere der Referenzspannungen von Detail und Globalmodell.
Am Streifen meldet derselbe Fall jetzt 36 %, ein ganz fehlendes Moment bei b/t = 30 60 %; reine Biegung, reiner Zug und Nullwerte bleiben ohne Scheinabweichung.
Die Messwerte dieses Abschnitts ändern sich dadurch: geneigt p 2 Kraft 3,7·10⁻⁵, Moment 4,8·10⁻⁵; Kragarm-Stub 24,6 % (vorher 10 bis 60 % erwartet, erfüllt).

### 11.18 Teilprojekt 5: Abnahme am Knotenblech mit Kehlnaht (01.10.2026)

**Modell** (Plan TP 5 C1, vor der Messung festgelegt; `tests/test_knotenblech.py`, `MODELL`). Längssteife auf einem Zugblech, der IIW-Fall „nicht tragende
Längsrippe“ mit Hot-Spot Typ a am Stirnnaht-Übergang: Grundblech 200 × 80 × 10 zwischen den Schnittebenen x 0 und 200 (CSG mit Polster bis −5 und 205),
Knotenblech 60 × 8 × 40 bei x 70…130, Kehlnaht rundum mit Schenkel 6 als Pyramidenstumpf (Quader [64,136]×[30,50]×[0,6] ∩ vier 45°-Halbräume, Ecken auf
Gehrung); Zug σ_n = 100 N/mm² über die Schnittebenen (Geber u = (εx, −νε(y − 40), −νε(z + 5)), Schnittkraft 80 kN); Nahtlinien „stirn_rechts“ (136, y, 0) und
„stirn_links“ (64, y, 0), y = 32…48, Referenzpunkte 0,4 t und 1,0 t auf der Blechoberseite. Volumen 181 936 mm³ (Prismatoid des Stumpfs 5 616 = h/6 (A₁ + 4A_m + A₂);
die Pyramidenstumpf-Formel gilt nicht, weil Grund- und Deckfläche nicht ähnlich sind – der erste Entwurf des Tests hatte sie, die Zellquadratur hatte recht).
Das Modell ist in x spiegelsymmetrisch zu x = 100.

**Referenz** (E2: Tet10 des Hauptprogramms; E3: Ablage durch die Hauptsitzung als Pull Request 13 auf `main`, `tests/reference_models/knotenblech_kehlnaht/`,
Vorschlag `docs/vertrag-aenderungen/2026-10-01-referenzmodell-knotenblech.md`). Session B hatte vorab denselben Lauf des Hauptprogramms aus einem festen Arbeitsbaum
von `main` (7da3571, nur lesend) gerechnet; die Hauptsitzung bestätigte die Werte auf die Stelle genau, mit zwei an der exakten Lösung geeichten Auswertungen
(2,6·10⁻⁹ N/mm², höchstens 0,86 % auseinander; Primärwert das Elementfeld am Punkt). Netz und Lauf: gmsh-Netz
(OpenCASCADE-Körper identisch mit der CSG ohne Polster, 1 mm Tet10 in 12 mm Umkreis der Nahtübergänge, 2,5 mm im Blech, 5 mm fern; 247 636 Elemente,
363 048 Knoten, 1,09 Mio. Freiheitsgrade) über den Abaqus-Import, u_x = εx auf beiden Stirnflächen, Starrkörper statisch bestimmt, σ_xx am Punkt als Mittel
der Elementfelder (`tests.pruefkoerper.punktspannung`), Lösen 294 s. **Einschränkung der Hauptsitzung:** die gemessene Kantenlänge am Übergang liegt im Median bei 1,33 mm
(90 % unter 1,75, Maximum 2,2 mm) – das gmsh-Größenfeld ist ein Ziel, keine Garantie; die Anforderung t/10 hält dieses Netz nicht. Netzkonvergenz der Referenz: mit 2,5 mm am Übergang σ_hs(y = 40) 148,0 / 149,1, mit 1 mm
142,74 / 143,14 N/mm² (rechts / links) – 3,6 % Änderung; bei Fehlerordnung h² läge der Grenzwert bei etwa 141,7 (Richardson), also rund 0,7 % unter dem 1-mm-Wert.
Die Referenz ist in sich symmetrisch (0,28 %). Der 0,5-mm-Lauf (1 554 780 Tet10, 2 149 968 Knoten, 6,45 Mio. Freiheitsgrade) passt nicht in den Speicher: die Hauptsitzung maß am 1-mm-Netz (1 087 659 Gleichungen)
33,6 GB für das Aufstellen und 30,6 GB für die PARDISO-Zerlegung (`lauf_05mm/ABNAHME-05MM.md`, `lauf_05mm/bedarf_1mm/bedarf.json`). Der Anwender hat deshalb entschieden, nur am Übergang auf 0,5 mm zu verfeinern (O2); Session B lieferte
dafür am 02.10.2026 ein lokal verfeinertes Netz (445 946 Knoten, 305 689 Tet10, 1,34 Mio. Freiheitsgrade; Feldwert 0,5 mm in vier Zonen um die beiden Nahtübergänge, tatsächliche
Kantenlänge am Übergang im Median 0,66 mm gegen 1,23 mm im 1-mm-Netz, gemessen an den Kanten mit Mitte höchstens 1 mm von der Übergangslinie – die Hauptsitzung nennt für das 1-mm-Netz 1,33 mm nach einer anderen Vorschrift, siehe oben;
`REFERENZ-KNOTENBLECH-2026-10-01/LIEFERUNG-LOKAL05.md`). Der Lauf der Hauptsitzung am lokal verfeinerten Netz (fertig am 02.10.2026 um 19:12, `lauf_05mm/abend_lokal05/erwartung_lokal05.json`, Programmstand main f56281a) erfüllt alle vorab festgelegten Kriterien: Eichung an der exakten Lösung höchstens 3,8·10⁻⁹ N/mm² (Reaktion 80 000,0000 N), Gleichgewicht 3,3·10⁻¹⁴, die beiden Auswertungen (Elementfeld und geglättete Knotenspannung) höchstens 0,19 % auseinander (beim 1-mm-Netz 0,86 %), Symmetrie rechts/links 0,11 %, Kantenlänge am Übergang im Median 0,687 mm (90 % unter 0,894, Maximum 1,259 mm). σ_hs(y 40) ist 143,03 / 143,00 N/mm² (rechts / links), die Reaktion 81 843,40 N. **Die Netzkonvergenz der Referenz ist belegt:** gegenüber dem 1-mm-Netz ändert sich σ_hs an keinem der 18 Nahtpunkte um mehr als 0,31 %, und die 1-mm-Werte auf main sind damit auf diese 0,31 % genau. Der Anwender hat das Ersetzen freigegeben: Pull Request 18 der Hauptsitzung (gemergt am 03.10.2026, b6f96a6) hat die lokal-0,5-mm-Werte zu `erwartung_tet10.json` gemacht und die 1-mm-Werte als `erwartung_tet10_1mm.json` behalten; `test_knotenblech` liest die Datei ohne Änderung des Lesers und besteht mit beiden (gegen 1 mm rechts +0,34 %, links −2,93 %; gegen die feinere rechts +0,14 %, links −2,84 %, mit beiden Dateien am Lader geprüft).

**FCM** (Vertragsweg, Basiszellgröße 10 = t, p 2, `adaptive_cycles` 4 nach dem Fahrplan aus B4):

| Zyklus | Schritt | p | Freiheitsgrade | kleinste Zelle | σ_hs,max | Zeit |
|---|---|---|---|---|---|---|
| 0 | Start | 2 | 14 295 | 10 | 181,06 | 1 s |
| 1 | h-Halbierung Naht | 2 | 36 009 | 5 | 175,42 | 6 s |
| 2 | h-Halbierung Naht | 2 | 150 411 | 2,5 | 157,14 | 21 s |
| 3 | p-Erhöhung | 3 | 477 702 | 2,5 | 142,60 | 75 s |
| 4 | p-Erhöhung | 4 | 1 096 107 | 2,5 | 143,23 | 329 s (59 GB) |

Letzte Änderung +0,44 % (Schranke 3 %), Konvergenzaussage „konvergiert, Folge nicht monoton“ (−5,6, −18,3, −14,5, +0,6 N/mm²; Kriterium seit O4, 11.14). Kopplungskontrolle Kraft 2,25 % (Schnittkraft 81 844,7 N; Tet10 81 845,2 N), keine Integrationswarnung. Fern der Naht (x 180)
oben 111,1 und unten 94,9 N/mm², Tet10 111,1 / 95,0: das exzentrische Knotenblech biegt das Blech, und die ebenen Schnittebenen halten die Enden gegen
Verdrehung – darum gilt die Planregel „σ_xx = σ_n ± 1 %“ hier für den Membrananteil (Mittel beider Seiten 103,1 gegen Schnittkraft/(b t) 102,4, 0,7 %), nicht für
jede Seite.

**Abnahme (Vorgabe 13, Schranke 3 %) gegen die Referenz**, letzter Zyklus, σ_hs in N/mm²:

| y | 32 | 34 | 36 | 38 | 40 | 42 | 44 | 46 | 48 |
|---|---|---|---|---|---|---|---|---|---|
| FCM rechts | 130,63 | 136,76 | 140,54 | 142,58 | 143,23 | 142,58 | 140,54 | 136,76 | 130,63 |
| Tet10 rechts | 130,14 | 136,46 | 140,33 | 142,43 | 142,74 | 142,55 | 140,15 | 136,67 | 130,42 |
| FCM links | 126,94 | 132,71 | 136,33 | 138,31 | 138,94 | 138,31 | 136,34 | 132,71 | 126,94 |
| Tet10 links | 130,48 | 136,56 | 140,63 | 142,78 | 143,14 | 142,16 | 140,46 | 137,01 | 130,33 |

Rechts stimmen FCM und Tet10 an allen neun Punkten auf 0,4 % überein (y = 40: +0,34 %), links liegt die FCM um 2,7 bis 3,0 % darunter (y = 40: −2,93 %).
**Die Abnahme hält an beiden Stirnnähten, links knapp.** Die Differenz zwischen rechts und links (3,1 %) ist kein Modellfehler – Geometrie, Last und die Tet10-Lösung
sind symmetrisch –, sondern die Gitterphase: das Gitter beginnt bei lo − 0,1 h = −1, der linke Übergang x 64 liegt bei Zellen von 2,5 mm genau auf einer Zellgrenze,
der rechte x 136 0,5 mm vor einer. Der Referenzpunkt 0,4 t = 4 mm liegt damit höchstens zwei Zellen vor der Spannungssingularität am Übergang, und dort entscheidet
die Lage der Zellgrenzen über Prozente. Die Planschranke „rechts und links auf 1 % gleich“ hält nicht; sie misst dasselbe wie die Schnittlagen-Robustheit der
Vorgabe 13 (Streuung unter 1 %), die für den Hot-Spot bei t/4 und p 4 also nicht erreicht ist. Hebel (nicht Teil von C1; Messung und Entscheidung O3 in 11.20): Nahtziel t/8
statt t/4 (ein h-Zyklus mehr; Freiheitsgrade und Speicher steigen deutlich – bei p 4 wären es über 2 Mio.) oder ein Hot-Spot-Verfahren mit größerem Abstand zur Kerbe
(IIW Typ a grob: 0,5 t / 1,5 t).

**Zwei unabhängige Auswertungen.** Die Planregel (6) sah eine zweite Auswertung aus den Oberflächenpunkten des Ergebnisses vor (lineare Interpolation der
Eckwerte an die Referenzpunkte): sie wich rechts 3,3 % und links 9 % vom Hot-Spot-Modul ab – zwischen Eckpunkten 2,5 mm auseinander im steilen Gradienten
4 mm vor dem Übergang ist lineare Interpolation untauglich, und die Oberflächenpunkte sind nicht der Weg zum Hot-Spot. Die rohe Spannung σ = D B u (ohne
L²-Projektion) an den Referenzpunkten weicht bei h 10 um 7,8 % vom geglätteten Wert ab (Information im Kerntest). Die unabhängige zweite Auswertung ist die Tet10-Referenz
(anderes Programm, anderes Netz, eigene Extrapolation aus Rohwerten), gegen die auf beiden Seiten verglichen wird.

**Befunde aus dem Modellbau, behoben (mit Test, `test_quadratur.test_innere_trennflaeche`):** (1) Die Probenprüfung der Baumzerlegung (`Csg._baum_stuecke`) zählte
Proben genau auf einer inneren Trennfläche zweier abgeschlossener Stücke (Knotenblech-Seitenfläche im Inneren des Nahtstumpfs) doppelt und verwarf die richtige
Zerlegung: 1 534 Flächenstücke im Rückfall, Integrationswarnung, Oberfläche 8 382,7 statt 7 901,6 mm². Jetzt prüft die Abdeckung mit abgeschlossenen und die Disjunktheit
mit offenen Stücken. (2) Deckungsgleiche Flächen zweier Formen auf derselben Seite (Knotenblech und Nahtstumpf stehen beide auf z = 0) zählten doppelt (480 mm²);
jetzt behält eine Form das Stück – eine analytische vor einer Hülle (die benannten Symmetrie-Halbräume um das Lamé-STL tragen Lager und Lasten; mit dem reinen Rang
verlor „sym_x“ seine Punkte), sonst die mit dem kleineren Rang (`_zeugen_pruefen`, Statistik `doppelt_verworfen`). Am T-Stoß (11.13) verbesserte das die Flächenexaktheit
von 3,2·10⁻¹² auf 2·10⁻¹⁶ – dort waren 27 Punkte doppelt.

**Prüfungen** (`tests/test_knotenblech.py`: Kernteil h 10 in der Kernsuite – Volumen, Kopplung, Membrananteil, 18 Hot-Spots im Band 1,0 bis 2,0 σ_n;
Konvergenz mit vier Zyklen und Abnahme gegen die Referenzdatei der Hauptsitzung (Pull Request 13) nur mit `VOLUMEN3D_LANG=1`, 436 s und 59 GB bei der ersten Messung, 572 s
am 02.10.2026; die Aussage „konvergiert“ gehört zur Prüfung, die Symmetrie rechts/links wird als Information gemeldet (die Planschranke 1 % gilt nicht, entschieden mit O3), und der Lauf muss im
gemessenen Streuband der Gitterlage (11.20) liegen – eine Regressionsprüfung, keine Abnahmeschranke).

**Nachtrag (O1, 02.10.2026).** Pull Request 13 der Hauptsitzung (Referenzmodell, Merge-Commit f56281a) ist auf main; `test_knotenblech` liest die Referenz seither aus
`tests/reference_models/knotenblech_kehlnaht/erwartung_tet10.json` (Hilfsfunktion `lade_referenz`) statt aus eingetragenen Zahlen – dieselben Werte (142,74 / 143,14 N/mm²). Ersetzt der
0,5-mm-Lauf der Hauptsitzung die Datei, folgt der Test ohne Änderung; die Abnahme hängt von der Gitterlage ab (11.20).

**Nachtrag (C2, 02.10.2026).** Mit der Kopplungskontrolle als Spannung (Nachtrag zu 11.17) meldet das Knotenblech jetzt an beiden Schnittebenen „Moment 7,9 % > 5 %“:
die ebenen Schnittebenen halten das Blech gegen die Verdrehung, die das exzentrische Knotenblech erzeugt, und im Detail entsteht dort ein Biegemoment von 1,2·10⁴ N·mm
(Randspannung ±8,8 N/mm²), das der Zug-Geber (reiner Zug) nicht kennt. Die Warnung ist richtig – das Globalmodell bildet die Exzentrizität nicht ab –, und
die Tet10-Referenz hat dieselben Randbedingungen; der Vergleich FCM gegen Tet10 bleibt davon unberührt. Die Kraftabweichung liegt bei 2,2 % (h 10).

**Nachtrag (O4, 02.10.2026).** Die Konvergenzaussage des Knotenblechs lautet jetzt „letzte relative Änderung 0,44 % < 3 %: konvergiert; Folge nicht monoton (Änderungen −5,64, −18,28, −14,53, +0,63 N/mm²)“
(Kriterium siehe 11.14). Die Streuung der Abnahme mit der Gitterlage steht in 11.20.

**Nachtrag (O2, 02.10.2026).** FCM (Nahtziel t/4, p 4, Schnittebenen bei 0 und 200, der Lauf aus C1) gegen diese verfeinerte Referenz: y 40 rechts +0,14 %, links −2,84 %; über alle neun Punkte je Seite rechts −0,01 bis +0,20 %, links −2,95 bis −2,70 %. Die Abnahme (Schranke 3 %) hält damit an beiden Stirnnähten, links mit 0,05 % Reserve. Zwei Quellen für die FCM-Werte (Rohlauf der O3-Reihe, Tabelle oben) geben dieselben Abweichungen; die Referenzseite ist die Datei der Hauptsitzung. Die Referenz ist in sich symmetrisch (143,03 / 143,00), die linke FCM-Naht liegt wegen der Gitterlage darunter (11.20).

### 11.19 Teilprojekt 5: zweite Sicht über Phase A und B (02.10.2026)

**Vorgehen** (Plan TP 5 C2, Regeln vor dem Gutachten festgelegt). Alles, was Teilprojekt 5 im Paket geändert hat (34 Dateien, +4 439 Zeilen), haben drei
Gutachter ohne Kenntnis des Sitzungsverlaufs gelesen, jeder ein anderes Modell als die Umsetzung seines Teils: G1 (Opus 5.5) die von Fable 5.1 gebauten
Teile (GPU-Blöcke, Moment Fitting, Hüllenintegration, Windungsbaum, Kuren aus C1), G2 (Fable 5.1) die von Opus 5.5 gebauten (Mehrgitter, L²-Projektion,
Hot-Spot, verschachtelte CSG-Bäume), G3 (Opus 5.5) die von Sonnet 5.5 gebauten (Löserwahl, adaptive Zyklen, STEP, Kopplungskontrolle). Jeder Befund
wurde mit einem Skript oder Test nachgestellt; jede Kur hat einen Test, der ohne sie fehlschlägt. Von 25 Befunden (23 verschiedene: G3-1 = G1-3 und G3-5 = G2-6 sind doppelt) waren alle bestätigt;
behoben sind alle hohen und mittleren und die niedrigen mit kleiner Kur.

**Hohe Befunde.**

*Sich durchdringende Körper (G3-1, auch G1-3).* Eine STEP-Datei mit zwei sich durchdringenden Körpern lief still durch und rechnete „A minus B“: die Hülle
hatte doppelte Wände, und die Verschachtelungstiefe jeder Schale wurde an einer einzigen Facette bestimmt – die lag bei B zufällig in A, also wurde B zum
Hohlraum gewendet (Volumen 805 400 statt 1 288 000 mm³, in jeder Reihenfolge; am Quader mit Stutzen σ 306 statt 100 N/mm², nur eine Kopplungswarnung). Kur:
mehrere Körper einer STEP-Datei werden vor dem Tessellieren vereinigt (OpenCASCADE `fuse`; Protokoll `vereinigt`); für STL prüft `_durchdringung`, ob eine Kante
einer Schale eine Facette einer anderen kreuzt (echter Vorzeichenwechsel des Ebenenabstands, Schnittpunkt in der Facette, bestätigt durch Punkte knapp im
Inneren der eigenen Schale, die im Inneren der fremden liegen), und meldet dann einen Fehler; die Tiefe wird an bis zu acht Facetten knapp innerhalb der
eigenen Schale bestimmt (auf einer berührenden fremden Fläche ist die Windungszahl je nach Facette 0, ½ oder 1). Berührende Schalen (gemeinsame Fläche,
Teilfläche, Kante) und echte Hohlräume bleiben gültig. Kosten: Hohlkugel aus 2 × 25 088 Facetten 1,9 s beim Laden.

*Deckungsgleiche Flächen auf dem flachen Weg (G1-1).* Die C1-Kur (11.18) half nur im Baumweg. Bei einer Vereinigung zweier Formen auf derselben Ebene liefert
das Stück „B ohne A“ = B ∩ {z < 0} eine Ebene durch das Polygon mit entgegengesetzter Normale; die Regel für parallele Ebenen behielt es, der Fußabdruck kam
doppelt oder – mit dem Abgleich nach Rang am Zeugen eines nur teilweise überdeckten Polygons – teilweise doppelt, abhängig von Reihenfolge und Gitterphase:
Quader auf Quader 5 306 bis 5 552 statt 5 440 mm², Knotenblech auf Nahtquader 8 571 bis 8 861 statt 8 608. Kur: ein Polygon mit einer solchen Gegen-Ebene geht wie
im Baumweg den Weg „an allen Ebenen teilen, Zeuge, Abgleich“. Dazu verlangt der Zeuge jetzt auch Werkstoff knapp innerhalb: über einer bündigen Tasche (Lochfläche
deckungsgleich mit der Oberseite) ist der CSG-Abstand max(d_C, −d_B) null und außen frei, der Deckel blieb als Scheinfläche stehen (1 600 statt 1 550 mm²).
Alle Fälle sind jetzt exakt (10⁻⁹), in beiden Reihenfolgen und bei drei Zellgrößen.

*Offene Hüllen im Divergenzweg (G1-2).* Der Divergenzsatz (11.16) gilt nur für geschlossene Hüllen; eine Lücke verfälscht die ganze x-Säule hinter ihr (Würfel
30³ ohne eine Facette auf einer x-Seite: 13 859 statt 27 000 mm³, 24 Zellen „leer“; eine fehlende Facette auf einer y- oder z-Seite wirkt nicht, weil n_x = 0).
Kur: `Stl.offene_kanten` zählt die Kanten mit nur einer Facette; offene Hüllen gehen den alten Weg (Zerlegung an lokalen Ebenen, Fehler örtlich an der Lücke:
27 981 mm³ wie vor B6), dazu prüft jede Hüllenzelle 0 ≤ V ≤ V_Zelle und fällt sonst zurück. Die Warnung nennt die offenen Kanten und den Weg.

*Blechseite am Nahtübergang (G2-1).* Die Blechseite wurde allein an der Werkstofftiefe 0,7 t längs beider Äste erkannt. Bei Kehlnähten mit Schenkel unter
0,495 t liegt dieser Punkt schon auf dem Anschlussblech (Tiefe = dessen Dicke), bei flachen Überhöhungen von Stumpfnähten unter der Überhöhung (t + Höhe):
beide Äste passten, kein Wert (T-Stoß t 10 mit Schenkel 4, 3, 2 und alle geprüften Stumpfnähte). Kur: der Blechast ist der, dessen Oberfläche von 0,05 t bis
1,0 t eben bleibt (Normalen innerhalb 10°, Punkte auf der Ebene, Projektion verschiebt nicht) und unter dem der Werkstoff t tief ist; die Nahtoberfläche knickt
innerhalb 1,0 t ab. Mit derselben Prüfung fällt G2-2 weg: endete das Blech vor 1,0 t, wurde der Referenzpunkt still auf die Stirnfläche gezogen (σ_hs +70 %);
jetzt kein Wert mit der Warnung „weniger als 1,0 t ebene Blechoberfläche“. Grenze: an Rohren muss der Radius über 5,7 t liegen (10° über 1,0 t).

**Mittlere Befunde.** *Hülle in einem abgezogenen Teilbaum (G1-4):* `_stuecke_ohne` übersprang ein Loch, das selbst eine Operation ist und die Hülle enthält;
Facetten außerhalb des Lochrands blieben als Fläche im Werkstoff (A − (H ∩ {x ≤ 20}) 11 634 statt 11 200 mm²). Jetzt Schnitt mit den Randstücken des Teilbaums.
*Konvergenzaussage (G3-2):* eine letzte Änderung null galt vor der Monotonieprüfung als Konvergenz ([100, 120, 90, 90] „konvergent“), und hatte der Anwender die
Naht selbst schon auf t/4 verfeinert, rechneten die h-Zyklen dasselbe Netz zweimal und meldeten „konvergent, letzte Änderung null“. Jetzt: eine Folge ohne
Änderung heißt `ohne_aenderung` (mit Warnung, ohne Grenzwert), eine Null nach monotoner Annäherung bleibt konvergent, und ein h-Schritt ohne Wirkung wird
übersprungen und im Ergebnis genannt. *Kopplungskontrolle (G3-3):* siehe den Nachtrag zu 11.17. *Prüfungen ohne Aussage (G3-4):* der Vergleich „letzter Zyklus
= Rechnung mit p 4“ stand als `A and … if 'cycles' in protocol else E` und prüfte nur E, der Abbruch zwischen den Zyklen war nicht geprüft; beides ist jetzt
ausdrücklich, und ohne Zyklen stehen `cycles` 0 und die Konvergenzaussage im Protokoll. *Maßgebender Hot-Spot (G3-5/G2-6):* `hotspot_max` und `sigma_hs_max`
sind jetzt der betragsgrößte Wert mit Vorzeichen (vorher unter Druck der betragskleinste).

**Niedrige Befunde, behoben.** Die Hüllenzelle fittet mit q = max(fit_grad, 2p), unabhängig vom Schalter (G1-5); der Windungsbaum bildet seine Momente relativ zur
Mitte des Hüllquaders (Versatz 10⁶ mm: |Δw| 1,5·10⁻⁴ statt 3,5·10⁻³, G1-6); leere Nahtpolylinie gibt einen Fehler statt eines IndexError aus dem ganzen Lauf (G2-3);
geschlossene Polylinien werden zyklisch behandelt (G2-4); die L²-Projektion mit hängenden Moden und Aggregation ist geprüft (2 501 hängende, 1 018 aggregierte
Moden: 2,5·10⁻¹⁰ an der Oberfläche, 2,3·10⁻¹¹ in den feinen Zellen, G2-5; auf den CI-Läufern, Ubuntu mit SuperLU auf zwei Runner-Arten, 5,6·10⁻⁹ und 1,7·10⁻⁸ an der Oberfläche und
2,7·10⁻¹⁰ bis 7,2·10⁻¹⁰ in den feinen Zellen – zwei CI-Läufe fielen an der zuerst gesetzten Schranke 10⁻⁸ durch, sie gilt seit C4 mit 10⁻⁷ an der Oberfläche und 10⁻⁸ in den feinen Zellen); ein Referenzpunkt außerhalb der Zellen kostet nur seinen Nahtpunkt (G2-7); die
gebündelte Nachbarsuche ist an allen 98 Proben je feiner Zelle gegen Einzelabfragen geprüft (G2-8); `L2Rueckgewinnung.spannung` wirft für Punkte außerhalb statt
still die letzte Zelle zu nehmen (G2-9); Glätterblöcke über 320 Koordinaten werden über Cholesky invertiert, ein nicht positiv definiter fällt auf (G2-10); der
STEP-Cache hängt am Inhalt (Hash), eigene Netzoptionen gelten auch bei laufendem gmsh und werden danach zurückgestellt, eine Sperre verhindert zwei
Tessellierungen zugleich (G3-6); Blechdicke ≤ 0 wird in `prepare` abgewiesen, ein Fehler in einem späteren Zyklus liefert den letzten fertigen mit Warnung, die
Faktorisierung des Vorzyklus wird vor dem nächsten Aufbau freigegeben (G3-7); `estimate` sagt, dass seine Größen für Zyklus 0 gelten, und der Begründungstext
der Löserwahl folgt der Messung aus A6 (G3-8); Docstrings und 11.14 beschreiben den geltenden Fahrplan (G3-9).

**Aufgelistet, nicht behoben.** Abbruch während `prepare` eines Zyklus (der Vertrag gibt `prepare` keinen Abbruch; Aufbau bis Minuten); `summary()` beschreibt
nach `solve` weiter Zyklus 0 (Klarstellung „mit derselben Diskretisierung“ im Vertrag nötig); eine Vereinigung mit mehreren Kindern, die dieselbe Hülle
enthalten (nur programmatisch erreichbar); `t_s` von Zyklus 0 enthält die Vorbereitung nicht, die späteren schon; die Torsion geht in die Kopplungskontrolle
über das polare Moment ein, an dünnen Querschnitten eine Unterschätzung.

**Prüfungen.** Neue und geänderte Tests: `test_step.test_mehrere_koerper`, `test_step.test_cache_und_gmsh_zustand`, `test_stl.test_durchdringende_schalen`,
`test_quadratur.test_deckungsgleiche_flaechen`, `test_huelle.test_offene_huelle`, `test_huelle.test_huelle_in_abgezogenem_teilbaum`, `test_huelle.test_windungsbaum`
(Versatz), `test_hotspot.test_anwendbarkeit`, `test_hotspot.test_polylinien`, `test_adaptiv.test_konvergenzaussage`, `test_adaptiv.test_zyklen_ohne_wirkung`,
`test_adaptiv.test_massgebender_hotspot`, `test_adaptiv.test_zyklen_ohne_naht`, `test_adaptiv.test_zyklen_grenzen`, `test_schale.test_kopplungsabweichung`,
`test_rueckgewinnung.test_haengende_moden`, `test_zwaenge.test_gebuendelte_nachbarsuche`, `test_mehrgitter.test_grosse_bloecke_spd`.

### 11.20 Teilprojekt 5: Streuung des Hot-Spots mit der Gitterlage (O3, 02.10.2026)

**Frage.** Am Knotenblech (11.18) unterschieden sich die spiegelgleichen Stirnnähte im letzten Zyklus um 3,1 %, die vorab gesetzte Schranke war 1 %. Ist das ein
Ausreißer der einen Gitterlage, oder streut der Hot-Spot bei Nahtziel t/4 mit der Lage des Gitters zur Naht so stark? Die Regeln (Verschiebungen, Größen, Auswertung)
sind im Plan TP 5 (O3) vor der Messung festgelegt.

**Verfahren.** Das Gitter beginnt an der Hülle der beschnittenen Geometrie und wandert deshalb mit den Schnittebenen; ein Verschieben des ganzen Modells ändert die
Lage zur Naht nicht (im Schnelllauf identische Werte – die erste Fassung der Messregel war darin falsch und ist berichtigt). Verschoben werden darum nur die beiden
Schnittebenen um δ = 0, 0,625, 1,25 und 1,875 mm (ein Viertel der feinsten Zelle 2,5 mm je Schritt); Naht, Blech und Last bleiben. Jeder Lauf ist der Fahrplan aus B4
(h 5, h 2,5, p 3, p 4) über den Vertragsweg; die Hot-Spots jedes Zyklus werden mitgeschnitten. Aus derselben Lösung werden die Referenzpunkte (a) 0,4 t / 1,0 t
(Vorgabe 11.2, σ_hs = 5/3 σ₀,₄ − 2/3 σ₁,₀) und (c) 0,5 t / 1,5 t (IIW für grobe Netze, σ_hs = 1,5 σ₀,₅ − 0,5 σ₁,₅) ausgewertet. Gegenprobe: σ_xx an den Referenzpunkten
unabhängig aus der geglätteten Spannung gelesen, größte Abweichung zu den Werten des Hot-Spot-Moduls über alle Zyklen, Nähte und Punkte 1,3·10⁻¹⁴. Der Lauf mit δ = 0
reproduziert den Lauf aus C1 bis auf die letzte Stelle (143,229 / 138,943 bei 1 096 107 Freiheitsgraden).

**Messwerte** (letzter Zyklus, p 4, N/mm²; φ ist die Lage der Naht zur nächsten Zellgrenze der feinsten Zellen in Bruchteilen der Zelle, Gitterursprung 2,5 mm):

| Verschiebung δ der Ebenen | 0 | 0,625 | 1,25 | 1,875 |
|---|---|---|---|---|
| Lage der Naht zur Zellgrenze φ (rechts / links) | 0,80 / 0,00 | 0,55 / 0,75 | 0,30 / 0,50 | 0,05 / 0,25 |
| Freiheitsgrade im letzten Zyklus | 1 096 107 | 1 091 244 | 1 088 472 | 1 092 108 |
| σ_hs(y 40), (a), rechts | 143,23 | 143,66 | 147,17 | 143,43 |
| σ_hs(y 40), (a), links | 138,94 | 145,93 | 143,12 | 143,02 |
| σ_hs(y 40), (c), rechts | 138,42 | 138,41 | 139,00 | 138,94 |
| σ_hs(y 40), (c), links | 134,60 | 139,13 | 138,53 | 138,83 |
| gegen Tet10 (PR 13), (a), rechts / links | +0,34 % / −2,93 % | +0,65 % / +1,95 % | +3,10 % / −0,01 % | +0,48 % / −0,08 % |

**Streuung S = (max − min)/Mittel über die acht Proben** (4 Verschiebungen × 2 Nähte) von σ_hs(y 40):

| | (a) 0,4 t / 1,0 t | (c) 0,5 t / 1,5 t |
|---|---|---|
| p 3 | 4,21 % (137,57 … 143,53) | 4,66 % (133,69 … 140,14) |
| p 4 | **5,73 %** (138,94 … 147,17) | **3,27 %** (134,60 … 139,13) |
| p 4, ohne die Probe φ = 0,00 | 2,9 % (143,02 … 147,17) | 0,52 % (138,41 … 139,13) |
| p 4, Mittel über y 32 … 48 statt y 40 | 5,66 % | 3,22 % |

**Auswertung nach den Regeln des Plans.** Regel (3) greift: S(a) bei p 4 ist mit 5,7 % größer als 3 %, die Schranke 1 % wie auch die der Vorgabe (3 %) gelten also nicht;
die Variante (c) erfüllt „S(c) bei p 4 ≤ 1 %“ nicht (3,3 %), obwohl sieben der acht Proben auf 0,5 % beieinander liegen – die achte, die linke Naht mit der Naht genau auf einer
Zellgrenze (φ = 0,00), liegt 3 % darunter, in (a) ebenfalls (138,94 gegen 143,0 bis 147,2). Gegen Tet10 liegen sieben der acht Proben innerhalb 3 % (−2,93 % bis +1,95 %), die
Probe rechts bei δ = 1,25 mit +3,10 % knapp außerhalb: **die Abnahme C1 hält also nicht bei jeder Gitterlage**; mit dem Lauf δ = 0 (−2,93 %) bestand sie nur knapp (gegen die später gerechnete verfeinerte Referenz der Hauptsitzung hält sie an allen vier Lagen, Nachtrag O2 unten).

**Herkunft der Streuung.** Sie kommt allein vom Referenzpunkt 0,4 t, der 1,6 Zellen von der Spannungssingularität am Nahtübergang liegt: σ(0,4 t) streut bei p 4 um 3,6 %
(132,4 … 137,3 N/mm²), σ(1,0 t) – genau vier Zellen vom Übergang – um 0,40 % (122,5 … 123,0). Im Hot-Spot (a) wirkt der Beiwert 5/3: 8,2 N/mm² Streuung aus σ(0,4 t) gegen 0,3 aus
σ(1,0 t). In (c) liegt der erste Punkt bei 2,0 Zellen, σ(0,5 t) streut bei p 4 um 2,3 % (129,0 … 132,1), der Beiwert ist 1,5. Die Abhängigkeit ist nicht glatt: die Probe mit φ = 0,00 (Naht genau auf der
Zellgrenze) liegt in (a) um 3 % unter der mit φ = 0,05 (andere Naht des spiegelsymmetrischen Modells), die Proben bei φ = 0,25 bis 0,30 liegen 1,5 bis 2,5 % darüber. Mit p 3 nach p 4 nimmt die Streuung nicht ab (4,2 → 5,7 %), p-Verfeinerung hilft also nicht,
es ist eine Frage der Zellgröße am Übergang.

**Berichtsform (O3, Entscheidung des Anwenders 02.10.2026).** Bis das Nahtziel t/8 gemessen ist, wird die Streuung als Band berichtet: σ_hs(y 40) bei Nahtziel t/4 und p 4 im Mittel 143,6 N/mm²
mit der Spanne 138,9 bis 147,2 N/mm² über die Gitterlage (S = 5,7 %), gegen die Tet10-Referenz je Lage −2,93 % bis +3,10 %. Eine Rechnung liefert einen Wert aus diesem Band; die Abnahme „unter 3 %“
gilt für die Lagen 0, 0,625 und 1,875 mm der Schnittebenen, bei 1,25 mm liegt die rechte Naht mit +3,10 % knapp außerhalb (gegen die 1-mm-Referenz; gegen die verfeinerte Referenz liegen alle Lagen innerhalb, Nachtrag O2 unten).

**Größe von t/8.** Der Aufbau des Gitters für das Nahtziel 1,25 mm endete nicht (zwei Versuche, der erste nach 30 Minuten durch die Zeitgrenze des Werkzeugs beendet, der zweite von mir abgebrochen), während die Gitter für 2,5 mm in 0,1 s stehen. Die Ursache war ein Fehler im Gitteraufbau, kein Rechenaufwand (Plan O15, behoben mit Commit 250e607; Nachtrag in 11.8): `Gitter._aufbauen` (seit Teilprojekt 2) wendet in der 2:1-Balancierung die Maske aus `_unbalanciert` – sie gilt für die von `_indizieren` sortierten Felder `self.ebene`, `self.ijk`, `self.klasse` – auf die unsortierten lokalen Felder an und teilt damit andere Zellen als gemeint. Bei zwei Ebenen unter der Basiszelle (Nahtziel 2,5 mm) bleibt das ohne Folge: mit der korrigierten Reihenfolge (seit Commit 250e607 im Repository) entstehen dieselben 5 146 Blätter und dieselben 150 411 / 477 702 / 1 096 107 Freiheitsgrade bei p 2 / 3 / 4 wie in den Läufen aus C1. Bei drei Ebenen (1,25 mm) entstehen Blätter der Ebene 4 über der Obergrenze 3, und die Balancierung teilt in jedem Durchlauf weitere (219 Zellen je Durchlauf, 38 Durchläufe in 13 s gemessen, die Zahl der Blätter wächst weiter) – sie endet nicht. Seit der Korrektur steht das Gitter in 0,9 s (mit dem Code des Repositorys gemessen, dieselben Zahlen wie vorab mit einem Monkeypatch im Scratchpad): 31 531 Blätter (Ebenen 0 bis 3: 208 / 622 / 1 721 / 28 980), 2:1 nach zwei Durchläufen erfüllt, kein Blatt über der Obergrenze, **841 032 / 2 747 052 / 6 398 538 Freiheitsgrade bei p 2 / 3 / 4**. Die Zählung ist an den bekannten Werten für 2,5 mm geeicht (exakt gleich). Nahtziel t/8 ist damit bei p 4 mit 6,4 Mio. Freiheitsgraden auf dieser Maschine nicht zu rechnen (zum Vergleich: 1,10 Mio. Freiheitsgrade brauchten 59 GB beim Direktlöser und 4,4 bis 4,8 GB auf der Grafikkarte beim Mehrgitter); bei p 3 sind es 2,7 Mio., bei p 2 0,84 Mio. Freiheitsgrade, aber p 2 ist nicht der Abnahmezustand.

**Entschieden und offen (O3).** Entschieden am 02.10.2026: die Streuung wird als Band berichtet (oben); die Schranke 3 % ist nicht belegt (5,7 %) und wird nicht behauptet. Offen und zu messen,
sobald die Maschine frei ist: (b) Nahtziel t/8 und seine Wirkung auf die Streuung (Größe siehe oben: bei p 4 auf dieser Maschine nicht rechenbar, der Gitterfehler ist behoben, Plan O15 und 11.8); (c) 0,5 t / 1,5 t, das die Vorgabe 11.2 (0,4 t / 1,0 t) ändert, im Wert 3,7 % unter (a) liegt und
in der PR-13-Referenz keine Vergleichspunkte hat (Tet10 an 0,5 t und 1,5 t müsste die Hauptsitzung liefern, am besten zusammen mit dem Lauf am lokal verfeinerten Netz, O2).

**Nachtrag (O2, 02.10.2026): die Lagen gegen die verfeinerte Referenz.** Die Hauptsitzung hat die Referenz am lokal verfeinerten Netz gerechnet (11.18; Median der Kantenlänge am Übergang 0,687 mm, σ_hs(y 40) 143,03 / 143,00 N/mm², gegenüber dem 1-mm-Netz höchstens 0,31 % Änderung). Gegen sie liegen die vier Lagen der Streuungsmessung bei y 40 so: δ = 0 rechts +0,14 %, links −2,84 %; δ = 0,625 rechts +0,44 %, links +2,05 %; δ = 1,25 rechts +2,90 %, links +0,08 %; δ = 1,875 rechts +0,28 %, links +0,01 %. Über alle vier Lagen und je 18 Punkte liegen die Abweichungen zwischen −2,95 % und +2,96 %. **Die Abnahme „unter 3 %“ hält damit an allen gemessenen Lagen, mit 0,04 % Reserve;** dass sie gegen die 1-mm-Referenz bei einer Lage mit +3,10 % verfehlt wurde, lag an der Netzabhängigkeit dieser Referenz (rechts bei y 40 +0,20 % Änderung zum feineren Netz): mit ihr sinkt die Abweichung der Lage δ = 1,25 rechts von +3,10 % auf +2,90 %. Die Streuung der FCM-Werte selbst (S 5,7 %) ändert sich nicht – nur der Bezug. Der Bezug ist die verfeinerte Referenz der Hauptsitzung; sie ist seit Pull Request 18 (b6f96a6, 03.10.2026) die Referenz auf `main`.

### 11.21 Teilprojekt 5: Konsistenz der Schnittzellen-Integration (O5, 03.10.2026)

**Frage.** Ein Feld, das im Ansatzraum liegt, muss die Rechnung bis auf Rundung zurückgeben. Für lineare Felder tat sie das (Patch-Test, 10⁻¹⁰ bis 10⁻¹³). Für quadratische nicht: am
T-Stoß mit lokaler Verfeinerung 3,3·10⁻⁶ (11.14), am schräg geschnittenen Plattenstreifen über den Vertragsweg 2,2·10⁻⁴ bis 3,5·10⁻³ bei p 2 und bis 2,5·10⁻⁶ bei p 3 (11.17). Gesucht waren
die Ursachen mit ihrem Anteil und eine Kur. Hypothesen, Vorhersagen und Auswertung sind im Plan TP 5 (O5) vor der Messung festgelegt.

**Bedingung.** Das Verfahren ist konsistent, wenn für das exakte Feld u und jede Testfunktion v die Volumen- und die Flächenregel zusammen den Gaußschen Satz erfüllen:
[∫σ(u):ε(v) dV] − [∫(σ(u)n)·v dA] − [∫f·v dV] = 0. Die Strafterme des Nitsche-Verfahrens verschwinden für u = g an jedem Punkt und stören nicht. Für ein Feld vom Gesamtgrad k und den Ansatz
vom Tensorgrad p (v bis zum Gesamtgrad 3p) hat der Volumenintegrand den Gesamtgrad 3p + k − 2, der Flächenintegrand 3p + k − 1. Ausgelegt waren beide Regeln auf k = 1: die Tetraederregel
der schräg geschnittenen Stücke mit n = ⌈1,5 p⌉ Punkten je Richtung (exakt bis 2n − 1 = 5 / 9 / 11 bei p 2 / 3 / 4), die Flächenregel mit n = ⌈(3p + 1)/2⌉ (exakt bis 7 / 9 / 13).
Für k = 2 sind 6 / 9 / 12 im Volumen und 7 / 10 / 13 auf der Fläche nötig: im Volumen fehlt bei geradem p ein Grad, auf der Fläche bei ungeradem p.

**Messung.** Zwei Modelle mit Verschiebungsrand auf der ganzen Oberfläche: (T) der T-Stoß mit Kehlnähten und lokaler Verfeinerung (Basis 20, Nahtziel 5 bei p 2 und 10 bei p 3), (S) der
Plattenstreifen als STL-Hülle, um 10° und 30° geneigt und mit den beiden schrägen Halbräumen des Vertragswegs geschnitten (Basis 25). Felder: linear (k 1), quadratisch (k 2: an T u = (c x²/2, 0, 0)
mit Volumenlast, an S die reine Biegung), kubisch (k 3, nur T bei p 3). Zwei unabhängige Größen: (A1) der größte relative Fehler der rohen Spannung an 1 500 Werkstoffpunkten, über die Lösung;
(A2) der Konsistenzrest des exakten Felds ohne Lösung, r = Cᵀ(K_vol a − f − ∫(σ n)·v), mit den exakten Koeffizienten a je Zelle, bezogen auf den größten Betrag von Cᵀ K_vol a.
Die erste Fassung von A2 (Rest des ganzen Systems, bezogen auf die rechte Seite) war blind, weil die Strafterme β mal die Rundung der Zwangsmatrix eintragen; die zweite (mit C x statt a) hatte am
Biegefeld einen Boden von 1,3·10⁻⁷. Beides wurde vor der vollständigen Reihe berichtigt und steht im Plan.

| Modell | p | Feld | Vorgabe A1 / A2 | nur Tetraeder 2p | nur Fläche 2p | beide, α 10⁻¹² | nach der Kur A1 / A2 |
|---|---|---|---|---|---|---|---|
| S 10° | 2 | k 2 | 2,5·10⁻⁴ / 8,2·10⁻⁵ | 1,2·10⁻¹⁰ | (unverändert 4) | 3,4·10⁻¹⁰ | 2,3·10⁻¹⁰ / 2,1·10⁻¹⁰ |
| S 30° | 2 | k 2 | 2,5·10⁻⁵ / 9,5·10⁻⁶ | 1,7·10⁻¹⁰ | (unverändert 4) | 2,8·10⁻¹⁰ | 2,4·10⁻¹⁰ / 8,8·10⁻¹¹ |
| S 10° | 3 | k 2 | 6,9·10⁻⁸ / 1,9·10⁻⁹ | 6,9·10⁻⁸ | 2,1·10⁻⁹ | 4,5·10⁻⁹ | 2,4·10⁻⁹ / 2,0·10⁻⁹ |
| S 30° | 3 | k 2 | 2,5·10⁻⁸ / 5,9·10⁻¹⁰ | 2,5·10⁻⁸ | 2,4·10⁻⁸ | 3,2·10⁻⁸ | 2,5·10⁻⁸ / 4,0·10⁻¹⁰ |
| T (3 Zellen ohne Wurzel) | 2 | k 1 | 1,0·10⁻⁶ / 6,0·10⁻⁹ | 1,0·10⁻⁶ | (unverändert 4) | 9,3·10⁻¹¹ | 1,0·10⁻⁶ / 6,0·10⁻⁹ |
| T | 2 | k 2 | 3,3·10⁻⁶ / 4,8·10⁻⁸ | 3,7·10⁻⁷ | (unverändert 4) | 3,5·10⁻¹¹ | 3,7·10⁻⁷ / 5,6·10⁻⁹ |
| T (9 Zellen ohne Wurzel) | 3 | k 1 | 6,6·10⁻⁵ / 1,4·10⁻¹⁰ | 6,6·10⁻⁵ | 6,7·10⁻⁵ | 2,6·10⁻⁷ | 6,7·10⁻⁵ / 1,4·10⁻¹⁰ |
| T | 3 | k 2 | 2,6·10⁻⁵ / 1,3·10⁻⁹ | 2,6·10⁻⁵ | 2,6·10⁻⁵ | 2,4·10⁻⁷ | 2,6·10⁻⁵ / 1,6·10⁻¹⁰ |
| T | 3 | k 3 | 1,1·10⁻⁵ / 2,4·10⁻⁹ | 1,1·10⁻⁵ | 1,1·10⁻⁵ | 9,2·10⁻⁸ | 1,1·10⁻⁵ / 1,8·10⁻¹⁰ |

Das lineare Feld liegt am Streifen überall auf Rundungsniveau (A1 7·10⁻¹² bis 1,5·10⁻⁹). Über den Vertragsweg (Schalen-Geber, Kopplung über die Schnittebenen) dieselben Ursachen: der Rest der
Spannungskomponenten fällt bei p 2 von 1,3·10⁻³ (10°) und 8,2·10⁻⁵ (30°) auf 8·10⁻¹² und 1,2·10⁻¹⁰, das Gleichgewicht der Resultierenden von 4,6·10⁻⁴ und 4,2·10⁻³ auf 1,3·10⁻¹⁰ und 1,9·10⁻⁹;
bei p 3 und 10° der Rest von 1,0·10⁻⁶ auf 4,2·10⁻¹⁰.

**Ursachen.** (H1) *Tetraederregel.* Bei p 2 trägt sie den ganzen Fehler des quadratischen Felds: mit n = 4 fällt er am Streifen um den Faktor 2·10⁶ (10°) und 1,5·10⁵ (30°), die Flächenordnung und α
ändern nichts. Umgekehrt erzeugt n = 4 bei p 3 (statt 5) denselben Fehler dort, wo vorher keiner war (Vertragsweg 10°: 2,8·10⁻³). Die Aggregationsschwelle, an der der Fehler in B7 hing, bestimmt
nur die Verstärkung des Rests durch schwach gestützte Moden, nicht den Rest. (H2) *Flächenregel.* Bei p 3 trägt sie den Fehler des quadratischen Felds, wo er über dem Boden liegt (Streifen 10°: 6,9·10⁻⁸ → 2,1·10⁻⁹,
Vertragsweg 1,0·10⁻⁶ → 4,2·10⁻¹⁰); an einem allgemeinen quadratischen Feld mit Traktion auf allen Flächen ist sie groß (Patch-Körper, Spannung am Rand 1,9·10⁻⁴). (H3) *α in Zellen ohne Wurzel.*
Der Fehler des linearen Felds an T ist bei p 2 genau proportional zu α (1,0·10⁻⁶ / 1,0·10⁻⁸ / 1,2·10⁻¹⁰ bei α 10⁻⁸ / 10⁻¹⁰ / 10⁻¹²). Die Zellen sind schlecht geschnittene Zellen der Ebene 0 am Querblech
(10 mm dick in 20-mm-Zellen), deren Nachbarn alle schlecht geschnitten oder feiner sind; sie behalten α, weil keine Wurzel gleicher oder gröberer Ebene da ist. In den Modellen des Vertragswegs mit Basiszelle
gleich der Blechdicke (Knotenblech in allen Zyklen, T-Stoß Basis 10) gibt es keine solche Zelle. (H4) *Rundung über die Zwangsmatrix.* Was bleibt (Streifen 30° p 3: 2,5·10⁻⁸ bei einem Konsistenzrest von 4·10⁻¹⁰), hängt
an der Genauigkeit, mit der die Zwangsmatrix das Feld wiedergibt (Fortsetzung der Wurzelpolynome über bis zu zwei Zellen, 78 von 89 Zellen aggregiert): derselbe Spannungszustand mit einem Viertel der
Verschiebung gibt 3,7·10⁻⁹, mit einer zusätzlichen Starrkörperverschiebung von 30 mm 4,7·10⁻⁷ (p 2: 2,4·10⁻¹⁰, 4,4·10⁻¹¹, 6,3·10⁻⁹). Am Patch-Körper bei p 4 liegt dieser Boden bei 1,6·10⁻⁸ im Inneren und 2,7·10⁻⁷ am
Rand, auch für das lineare Feld. Der Direktlöser kommt dazu (CI am 03.10.2026, lokal nachgestellt): mit SuperLU – ohne `pypardiso`, so rechnet die CI – gibt der Vertragsweg am Streifen 30° p 3 einen Rest von
1,0·10⁻⁵ und ein Gleichgewicht von 1,0·10⁻⁵ (CI: 8,2·10⁻⁶ und 1,2·10⁻⁵) statt 2,5·10⁻⁸ und 5,6·10⁻⁷ mit PARDISO. Mit einer Nachiteration (Residuum mit der Matrix, noch einmal lösen) gibt SuperLU 1,6·10⁻⁸ und 7,3·10⁻⁸,
mit zweien 2,7·10⁻⁸ und 7,7·10⁻⁸. Der Boden von rund 2·10⁻⁸ ist also bei beiden Lösern derselbe und gehört zur Zwangsmatrix; SuperLU allein löst das schlecht konditionierte System nur auf 10⁻⁵. Die anderen
Fälle sind mit beiden Lösern gleich (10° p 3: Rest 4,2·10⁻¹⁰ und 1,8·10⁻⁹; p 2 unter 10⁻¹⁰).

**Urteil nach der vorab gesetzten Regel.** Die Regel verlangte, dass der Fehler mit dem vorhergesagten Schalter auf höchstens das Dreifache des linearen Felds fällt und vorher mindestens das Zehnfache betrug.
Nach diesem Wortlaut ist keine der Vorhersagen erfüllt, obwohl die Fehler um bis zu sechs Größenordnungen fallen: am Streifen liegen lineares und quadratisches Feld nach dem Schalter beide unter Rundungsniveau
(10⁻¹¹ und 10⁻¹⁰, Verhältnis 12), an T trägt das lineare Feld selbst den α-Fehler. Die Regel hätte das Rundungsniveau als Boden nennen und das lineare Feld nicht als Maßstab nehmen dürfen, wo es einen eigenen
Fehler hat. In der Sache: V1 (p 2: Tetraederordnung, nicht Flächenordnung) bestätigt; V2 (p 3, k 2: Flächenordnung) bestätigt, wo der Fehler über dem Boden liegt (10°), nicht messbar bei 30°;
V3 (p 3, k 3: beide Ordnungen nötig) nicht bestätigt – der Rest hängt nur an der Flächenordnung (2,4·10⁻⁹ → 1,8·10⁻¹⁰), die Tetraederordnung ändert ihn nicht; V4 (α) bestätigt.

**Kur.** (K1) *Exakte Momente der schrägen Stücke.* Mit Moment Fitting merkt die Zellquadratur von jedem schräg geschnittenen Stück nur die Polygone; `geometry/huelle.polyedermomente` rechnet die Momente
der Tensor-Legendre-Basis vom Grad 2p über den Divergenzsatz (dieselbe Formel wie für Hüllen in 11.16, Flächen ohne x-Komponente der Normalen tragen nichts), und `gefittete_regel` nimmt sie zu den Momenten der
übrigen Punkte. Die Zellmatrix ist damit auf ebener Geometrie für den ganzen Ansatzraum exakt, nicht nur bis zu einem Feldgrad: an der Eckzelle (Würfel, Ecke x + y + z ≤ 1,5) stimmen alle zentrierten Monome
bis Grad 2p je Richtung mit der Dirichlet-Formel auf 8·10⁻¹⁶ des Volumens und die Zellmatrix mit der Tetraederregel der Ordnung 3p + 1 auf 4·10⁻¹⁵ überein; der alte Weg wich in den Momenten um 2,5·10⁻⁴ (p 2)
und 2,6·10⁻⁶ (p 3), in der Zellmatrix um 3,6·10⁻⁴ und 1,3·10⁻⁵ ab. Am Patch-Körper (110 Schnittzellen, p 2) weichen die Zellmatrizen des neuen Wegs von der exakten Referenz um höchstens 10⁻¹⁴ des
Vollzellmaßstabs ab, auch bei einem Werkstoffanteil von 2,8·10⁻⁵; die des alten Wegs um bis zu 5,7·10⁻³ (fast volle, schräg geschnittene Zellen). Ohne Moment Fitting (Schalter, künftig plastische Körper)
bleibt die Tetraederregel. *Wächter:* Der Divergenzsatz setzt geschlossene, nach außen orientierte Stücke voraus – die Tetraederzerlegung nicht. Der erste Suitenlauf der Kur fand den Unterschied: liegt eine
Ebene genau auf einer Zellfläche (Kirsch-Platte, Symmetrieebenen auf Zellflächen bei Versatz 0,4), berührt die Nachbarbox den Halbraum nur mit dieser Fläche, und `polyeder.clippen` lässt genau diese eine Fläche
als „Stück“ stehen – ohne Volumen, aber nicht geschlossen. Die Tetraederregel gab dafür null, der Divergenzsatz Fläche mal Abstand: zwei Zellen mit je 61,6 mm³ zu viel, K_t 1,77 statt 3,75 (h 10, p 2; in der
Suite 1,67 bis 1,85 statt 3,1). Seither gilt: Stücke ohne Volumen werden übersprungen (`stuecke_leer`), nur geschlossene Stücke (`polyeder.geschlossen`: mindestens vier Flächen, Summe der Flächenvektoren null)
gehen in den Divergenzweg, andere über die Tetraederregel (`stuecke_offen`), und je Zelle muss das Volumen aus dem Divergenzsatz das der Tetraederzerlegung sein, sonst fällt die Zelle auf die Tetraederregel
zurück (`stuecke_rueckfall`). Kirsch h 10 p 2 bei Versatz 0,4 danach: K_t 3,7541 und Volumen 796 854,089184 wie der alte Weg; die Suite gibt alle K_t wie vor der Kur.
Die Prüfungen laufen je schrägem Stück und kosten an der Kugel R 43 in h 10 mit Tiefe 3 (23 999 Stücke) 2,6 von 21 s der Zellquadratur. Die erste Fassung der Geschlossenheitsprüfung (Schleife über die Dreiecke) kostete dort
9,0 von 30 s und wurde vektorisiert (bc0dc59: 1,4 s); die Zellquadratur ist dabei an sechs Modellen (Kugel, Patch-Körper, verfeinerter Patch-Körper, Kirsch mit Versatz 0 und 0,4, Knotenblech) Bit für Bit dieselbe geblieben
(SHA-256 über Punkte, Gewichte und Masken aller Zellen). In keinem dieser Modelle kommt ein offenes Stück oder ein Rückfall vor; leere Reste gibt es am Knotenblech (14) und an der Kirsch-Platte mit Versatz 0,4 (54). (K2) *Flächenordnung 2p* (exakt bis 4p − 1, also für alle
Felder bis zum Gesamtgrad p): unverändert bei p 1 und p 2, 6 statt 5 bei p 3, 8 statt 7 bei p 4; die Quadraturpunkte der Oberfläche werden bei p 3 um 44 %, bei p 4 um 31 % mehr, die Ausgabepunkte
des Ergebnisses (Ecken der Oberflächendreiecke) bleiben dieselben. Am Lamé-Zylinder, dessen Zellen bei h 10 alle Schnittzellen sind (286 von 286; Flächenpunkte bei p 3 218 143 → 314 046, bei p 4 427 382 → 558 137, bei p 2 unverändert 139 640), braucht die Suite mit p 2 bis p 4 222 statt 221 s (+1 %; eigene CPU-Zeit +3 %; unmittelbar nacheinander gemessen, Fremdlast 9,8 und 5,6 Kerne – der alte Stand lief unter der größeren Fremdlast, der Unterschied ist also eher größer). Die Phasen, in denen die Flächenpunkte zählen, brauchen länger: Assemblierung bei p 3 6,6 → 8,2 s und bei p 4 26,0 → 32,0 s, Lösen mit Lastvektor 4,9 → 6,5 s und 18,3 → 22,2 s (+22 bis +32 %); bei p 2 bleiben sie gleich. Die Gesamtzeit bestimmt der Aufbau der Quadratur, der sich nicht verlängert (je Fall 34,1 → 34,8 s, 46,9 → 47,1 s und 93,4 → 97,5 s).
(K3) Für α in Zellen ohne Wurzel gibt es keine Kur in O5 (Liste).

**Patch-Test höherer Ordnung** (`test_patch.test_patch_hoeherer_ordnung`; Patch-Körper mit zwei schrägen Halbräumen, allgemeine Polynomfelder mit allen Komponenten, Volumenlast aus dem Differenzenquotienten
der Spannung, am quadratischen Feld gegen die Formel auf 2·10⁻¹⁴ geprüft). Spannungsfehler innen / am Rand:

| p | Feldgrad | vorher | mit der Kur |
|---|---|---|---|
| 2 | 2 | 1,1·10⁻⁴ / 2,6·10⁻⁴ | 9,4·10⁻¹² / 2,3·10⁻¹¹ |
| 3 | 2 | 1,8·10⁻⁵ / 1,9·10⁻⁴ | 2,9·10⁻¹⁰ / 2,2·10⁻⁹ |
| 3 | 3 | 1,7·10⁻⁵ / 2,2·10⁻⁴ | 2,1·10⁻¹⁰ / 8,1·10⁻¹⁰ |
| 4 | 1 | 1,8·10⁻⁸ / 3,5·10⁻⁷ | 1,6·10⁻⁸ / 2,7·10⁻⁷ |
| 4 | 3 | 2,1·10⁻⁶ / 1,4·10⁻⁵ | 8,5·10⁻⁹ / 5,5·10⁻⁸ |

Bei p 4 ist das der Boden des linearen Felds (H4), nicht mehr die Quadratur. Die Werte nach der Kur liegen auf Rundungsniveau und streuen von Lauf zu Lauf um etwa den Faktor 2 (p 3, Feldgrad 2, am Rand in
sechs Läufen 1,2·10⁻⁹ bis 2,3·10⁻⁹; p 2 2,0·10⁻¹¹ bis 2,6·10⁻¹¹).

**Kontrolllauf am Knotenblech** (Stand auf `main` 372ac59 gegen die Kur 79d4a4f, je aus einem festen Arbeitsbaum, nacheinander; vier Zyklen bis p 4):

| Zyklus | Schritt | p | Freiheitsgrade | σ_hs,max vorher | mit der Kur | Änderung | Zeit vorher (s) | mit der Kur (s) |
|---|---|---|---|---|---|---|---|---|
| 0 | Start | 2 | 14 295 | 181,060 | 181,067 | +0,004 % | 1,4 | 1,9 |
| 1 | h-Halbierung Naht | 2 | 36 009 | 175,419 | 175,420 | +0,001 % | 10,1 | 10,4 |
| 2 | h-Halbierung Naht | 2 | 150 411 | 157,135 | 157,132 | −0,001 % | 31,0 | 32,7 |
| 3 | p-Erhöhung | 3 | 477 702 | 142,601 | 142,601 | +0,000 % | 94,3 | 92,7 |
| 4 | p-Erhöhung | 4 | 1 096 107 | 143,229 | 143,229 | +0,000 % | 401,6 | 409,0 |

σ_hs(y 40) ändert sich im letzten Zyklus rechts von 143,2290 auf 143,2291 N/mm² und links von 138,9425 auf 138,9421 N/mm²
(beides unter 0,001 %); über alle 18 Nahtpunkte höchstens 0,002 %. Im Zyklus 0 (h 10, p 2) sind es höchstens 0,011 %. Die Konvergenzaussage bleibt
„letzte relative Aenderung 0.44 % < 3 %: konvergiert; Folge nicht monoton (Aenderungen -5.647, -18.29, -14.53, +0.6283 N/mm2)“. Das Ergebnis hat unverändert 3 050 Oberflächenpunkte (vorher 3 050). Die Rechenzeit ist getrennt nachgemessen, weil der Lauf auf 79d4a4f unter fremder Last stand (573,9 s gegen 496,5 s, alle fünf Zyklen langsamer): viermal unmittelbar nacheinander aus den festen Arbeitsbäumen, je Lauf mit der belegten CPU-Zeit fremder Prozesse – alt a 543,3 s (Fremdlast 7,4 Kerne), neu a 553,2 s (Fremdlast 8,0 Kerne), alt b 549,3 s (Fremdlast 9,0 Kerne), neu b 551,1 s (Fremdlast 10,9 Kerne). Gewertet nach der vorab im Plan festgelegten Regel nur Paar a, weil die Fremdlast der vier Läufe weiter als einen Kern auseinanderliegt: Wanduhr +1,8 %, eigene CPU-Zeit −1,6 %; die Regel (höchstens +10 %) ist erfüllt. Die Zykluszeiten der Tabelle sind die der gewerteten Läufe. Im Zyklus 0 gehen 28 schräge
Stücke mit exakten Momenten ein, 14 Reste ohne Volumen werden übersprungen, kein Stück ist offen oder im Rückfall; die Referenzpunkte gehen von 34 074 auf 23 814 zurück.
Gegen die Tet10-Referenz auf `main` (lokal 0,5 mm) bleibt die Abnahme unverändert: rechts +0,14 %, links −2,84 %, über alle 18 Punkte 2,95 %. Für das Knotenblech ist die Kur also ohne praktische Wirkung – die schräg geschnittenen Zellen sind die wenigen an den Nahtflanken (28 von 476 Stücken im Zyklus 0), und der Hot-Spot wird auf der Blechseite ausgewertet.

**Nicht behandelt (Liste im Plan).** Zellen ohne Wurzel behalten α und begrenzen dort selbst das lineare Feld auf α mal Verstärkung (T: 10⁻⁶ bei p 2, 7·10⁻⁵ bei p 3) – sie entstehen, wenn die Basiszelle gröber ist als
die Wanddicke und die Nachbarn feiner sind; das Protokoll nennt ihre Zahl (`aggregation.zellen_ohne_wurzel`), eine Warnung gibt es bewusst nicht (O16, Nachtrag am Ende dieses Abschnitts). Die Zwangsmatrix gibt Polynome nur auf 10⁻¹⁰ (p 2) bis 3·10⁻⁸ (p 3) wieder,
wenn fast alle Zellen aggregiert sind (O17 zeigte später: nicht wegen ihrer Einträge, sondern wegen der Größe der Fortsetzung, Nachtrag am Ende dieses Abschnitts). Ohne Moment Fitting bleibt die Tetraederregel mit n = ⌈1,5 p⌉ und damit der alte Konsistenzfehler; `ordnung_tet` lässt sich setzen. Gekrümmte Geometrie bleibt durch die
Tangentialebenen genähert (11.3); exakt ist die Integration des genäherten Körpers. Beim Suitenvergleich fiel außerdem auf: der Schwellenvergleich der Aggregation hängt bei einem Werkstoffanteil genau an der Schwelle 0,4 an der
letzten Rundungsstelle. Im verfeinerten Patch-Körper (`test_zwaenge`) wechselt eine Zelle mit den exakten Momenten von 0,4 − 2·10⁻¹⁶ auf 0,4 + 2·10⁻¹⁶ und gilt jetzt als wohlgestellt (aggregierte Moden bei p 2: 1 758 → 1 746);
beide Einteilungen bestehen den Patch-Test (behoben mit O19, Nachtrag am Ende dieses Abschnitts). Der SuperLU-Weg des Direktlösers bekam am selben Tag eine Nachiteration (O20, Nachtrag am Ende dieses Abschnitts); `test_schale` prüft den Fall 30° p 3 für beide Löser gegen 10⁻⁵, mit erzwungenem SuperLU mit und ohne
Nachiteration, und den Fall 10° p 3 im Rest gegen 10⁻⁷ (CI vor O20: 2,1·10⁻⁹).

**Zwei Prüfungen hingen am alten Weg.** `test_patch.test_ohne_aggregation` verlangte, dass der Fehler ohne Aggregation mit α skaliert (Faktor über 30 zwischen 10⁻⁸ und 10⁻¹⁰). Über α = 10⁻⁶ … 10⁻¹² ist er in beiden
Wegen nicht monoton (alt 3,5·10⁻² / 6,0·10⁻³ / 1,4·10⁻² / 4,1·10⁻⁴ / 1,4·10⁻⁴ / 1,0·10⁻⁵, neu 3,2·10⁻² / 5,1·10⁻² / 7,8·10⁻⁴ / 4,3·10⁻⁴ / 1,8·10⁻⁴ / 2,5·10⁻⁵); das eine Wertepaar war kein Gesetz. Geprüft wird jetzt,
dass der Fehler ohne Aggregation über 10⁻⁵ liegt. `test_pcg` verglich am Patch-Körper den Jacobi-PCG bei Toleranz 10⁻¹⁰ mit dem Direktlöser auf 10⁻⁴ und lag nur um den Faktor 2 über seinem Messwert; der Abstand hängt an
der Abbruchtoleranz (neu 1,2·10⁻⁴ / 6,3·10⁻⁶ / 1,6·10⁻⁶ bei 10⁻¹⁰ / 10⁻¹¹ / 10⁻¹², alt 4,5·10⁻⁵ / 3,7·10⁻⁵ / 1,4·10⁻⁶). Jetzt Toleranz 10⁻¹² und Schranke 10⁻⁵.

**Prüfungen.** `test_quadratur.test_stuecke_exakt` (Eckzelle gegen die Dirichlet-Formel in Brüchen und gegen die Tetraederregel der Ordnung 3p + 1; der alte Weg zum Vergleich; Ebene auf Zellflächen; Geschlossenheit, die vektorisierte Fassung gegen die Schleife je Dreieck an 385 zufällig geclippten Boxen; Rückfall
des Wächters), `test_patch.test_patch_hoeherer_ordnung`
(Feldgrad bis p; Schranke 10⁻⁸ bei p 2 und 10⁻⁷ bei p 3, gemessen höchstens 2,6·10⁻¹¹ und 2,3·10⁻⁹ – die engere Schranke 10⁻⁸ ließe bei p 3 nur das Vierfache Abstand, und eine Prüfung gleicher Art fiel am selben Tag
in der CI mit 1,7·10⁻⁸ gegen 10⁻⁸ durch; ohne K1 bzw. mit der alten Flächenordnung über 10⁻⁵ bzw. 10⁻⁶), `test_schale` mit Schranken aus den neuen Messwerten (geneigt p 2: Schnittgrößen und Rest unter 10⁻⁸ statt 1 %),
`test_quadratur.test_momentfitting` gegen die exakte Referenz. Alle 26 Paketsuiten grün auf 79d4a4f (fester Arbeitsbaum, nacheinander): `kern` 362/362, `quadratur` 54/54, `patch` 19/19, `schale` 18/18, `oktree` 30/30, `gitter` 26/26, `zwaenge` 24/24, `stl` 27/27, `step` 12/12, `huelle` 22/22, `rueckgewinnung` 6/6, `vertrag_fcm` 51/51, `hotspot` 10/10, `basis` 22/22, `elastizitaet` 6/6, `geometrie` 46/46, `operator` 10/10, `paket` 4/4, `pcg` 7/7, `lame` 7/7, `kragarm` 15/15, `adaptiv` 18/18, `mehrgitter` 27/27, `operator_gpu` 14/14, `knotenblech` 9/9, `kirsch` 8/8. Nach der Vektorisierung der Geschlossenheitsprüfung (bc0dc59, Zellquadratur Bit für Bit gleich) liefen die Kernsuite und die Suiten, in denen der Wächter greift, erneut: `kern` 363/363, `quadratur` 55/55, `patch` 19/19, `kirsch` 8/8, `knotenblech` 9/9; `mypy --strict` und `lint-imports` sauber.

**Geänderte dokumentierte Zahlen** (Regel 3: über die letzte angegebene Stelle hinaus, Stand vor der Kur → nach der Kur). (a) Lamé h 10 – p 3: σ_r 0,380 → 0,379 %, σ_φ 0,062 → 0,069 %, u_r 0,014 → 0,029 %, σ_z 0,143 → 0,147 %; p 4: σ_φ 0,093 → 0,085 %, u_r 0,037 → 0,006 %, σ_z 0,137 → 0,138 %; p 2 unverändert (Flächenordnung 6 und 8 statt 5 und 7); Lamé aus STL p 3: σ_r 0,070 → 0,069 %, σ_φ 0,024 → 0,023 %. (b) Hot-Spot am exakten Feld p 3: roh 1,6·10⁻⁷ → 5,8·10⁻¹¹, geglättet 6,2·10⁻⁸ → 5,6·10⁻¹¹. (c) Knotenblech h 10 p 2: σ_hs(y 40) rechts 164,802 → 164,803, links 180,111 → 180,097 N/mm², Symmetrie 8,79 → 8,78 %; der lange Lauf wie in der Tabelle oben. (d) Quadratisches Feld am T-Stoß mit zwei lokalen Halbierungen (11.14): 3,3·10⁻⁶ → 3,7·10⁻⁷. (e) Geneigter Plattenstreifen über den Vertragsweg (11.17): 30° p 2 Schnittgrößen 3,7·10⁻⁵ / 4,7·10⁻⁵ → 1,6·10⁻¹¹ / 7,1·10⁻¹¹, σ_x′ 2,2·10⁻⁴ → 5,0·10⁻⁷ (Versatz des Auswertepunkts), übrige Komponenten 8,2·10⁻⁵ → 1,2·10⁻¹⁰, Gleichgewicht 4,2·10⁻³ → 1,9·10⁻⁹; 10° p 3 Rest 1,0·10⁻⁶ → 4,2·10⁻¹⁰; 30° p 3 Rest 1,4·10⁻⁷ → 2,5·10⁻⁸, Gleichgewicht 2,2·10⁻⁷ → 5,6·10⁻⁷. (f) Aggregierte Moden im verfeinerten Patch-Körper (`test_zwaenge`): eine Ebene p 2 1 758 → 1 746, p 3 5 661 → 5 589; Bereich an einer Ecke p 1 158 → 152, p 2 1 008 → 1 004, p 3 3 189 → 3 225 – im Fall „eine Ebene“ bei p 2 nachgemessen: eine Zelle mit dem Werkstoffanteil genau 0,4 wechselt die Seite der Schwelle (Liste O19); die übrigen Fälle sind nicht einzeln nachgemessen. (g) Iterationszahlen des Jacobi-PCG um höchstens 1 % (Patch-Körper 5 060 → 5 015, Kirsch h 20 p 3 26 007 → 25 942), des Mehrgitter-PCG um höchstens zwei Schritte. (h) Nullwerte des Globalmodells in `test_vertrag_fcm` (Verhältnisse von Rundungsgrößen): 0,660 / 0,340 → 0,751 / 0,249. Auf alle angegebenen Stellen unverändert: Kirsch (alle K_t, Streuungen 6,98 %, 1,34 % und 0,17 %), Kragarm, Lamé p 2, die Abnahme des Knotenblechs gegen Tet10 (+0,14 % / −2,84 %). Neu gefasst und darum nicht vergleichbar: `test_patch.test_ohne_aggregation` und der Patch-Fall in `test_pcg` (siehe oben).

**Nachtrag (O20, 03.10.2026): Nachiteration im SuperLU-Weg des Direktlösers.** `linalg/direkt.Direktloeser` rechnet ohne `pypardiso` (CI, künftig Linux) mit SuperLU und COLAMD. Am schlecht konditionierten System des
geneigten Streifens (30°, p 3) gibt das einfache Lösen einen Rückwärtsfehler von ω = 2,6·10⁻⁷ und einen Spannungsfehler von 1·10⁻⁵; PARDISO, das selbst nachiteriert, 2,5·10⁻⁸. Nach der Lösung bildet der Direktlöser
jetzt R = F − K U und das komponentenweise Rückwärtsfehlermaß ω = max_i |r_i| / (|K| |U| + |F|)_i und ergänzt U um K⁻¹ R, solange ω über 10⁻¹⁴ liegt, höchstens dreimal; ein Schritt, der ω nicht senkt, wird verworfen, ein Schritt,
der es nicht halbiert, beendet die Iteration. Am Streifen sind es ein bis zwei Schritte: ω fällt von 2,6·10⁻⁷ auf 6,9·10⁻¹⁴ und 6,8·10⁻¹⁵, der Spannungsfehler von 1,0·10⁻⁵ auf 2,7·10⁻⁸ (Kraft 7,2·10⁻¹⁰, Moment 3,9·10⁻⁹, Rest
2,7·10⁻⁸, Gleichgewicht 7,7·10⁻⁸). Das normweise Residuum taugt nicht als Maß: es liegt vor dem ersten Schritt bei 6,4·10⁻¹³, danach bei 4,1·10⁻¹³ und ist damit der Boden seiner eigenen Auswertung. Der PARDISO-Weg bleibt
unverändert; das Grobgitter des Mehrgitters nimmt `nachiteration=0`, weil es ein fester, symmetrischer Vorkonditionierer ist und seine Nullraumerkennung am Verhalten der einfachen Zerlegung hängt. Die Mehrkosten sind ein
Matrix-Vektor-Produkt mit K und |K| und eine Rücksubstitution je Schritt: 4 % von Faktorisierung und Lösen bei 22 584 Unbekannten, 7 bis 10 % bei 1 734 (|K| liegt als zweites Datenfeld mit denselben Indexfeldern vor, 8 Byte je
Eintrag). Messung, Regeln und Berichtigung der Abbruchregel stehen im Plan TP 5 (O20). `test_direkt` prüft den Löser an Zerlegungen mit bekanntem Fehler, `test_schale.test_schale_geneigt_p3_superlu` den Streifen mit
erzwungenem SuperLU mit und ohne Nachiteration; die Kernsuite läuft mit beiden Lösern (374/374 und 374/374).

**Nachtrag (O19 und O16, 03. und 04.10.2026): Schwellenvergleich der Aggregation und Zellen ohne Wurzel.** *O19.* `Zellaggregation` verglich den ungerundeten Werkstoffanteil mit der Schwelle 0,4. Eine Zelle, deren Anteil
geometrisch genau auf der Schwelle liegt (Ebene durch eine Zellfläche oder die Zellmitte), schwankte darum je nach Quadraturweg und je nach α um 10⁻¹⁶ auf beide Seiten, und die Einteilung in schlecht und wohl gestellt hing an der letzten
Rundungsstelle: in 5 von 9 verfeinerten Patch-Körpern war sie zwischen Tetraederregel und exakten Stückmomenten verschieden (1 bis 3 Zellen), an der Kirsch-Scheibe mit 20-mm-Zellen zählte sie 625, 719 und 625 schlechte Zellen bei
α = 10⁻⁸, 10⁻¹⁰ und 10⁻¹². `fcm/aggregation.schlecht_gestellt` vergleicht jetzt den auf neun Stellen gerundeten Anteil (derselbe Wert wie `_rang`, der die Rangfolge der Wurzeln bestimmt); ein Anteil innerhalb von 5·10⁻¹⁰ der Schwelle
gilt als auf ihr und damit als wohlgestellt. Danach ist die Einteilung in allen neun Fällen vom Weg und von α unabhängig, und K_t der Kirsch-Scheibe bleibt gleich. Im Haken über 19 Suiten stellt die Rundung nur in den Modellen von
`test_zwaenge` Zellen um (16 Zellen in 6 Endaufbauten, aggregierte Moden z. B. eine Ebene p 2 1 746 → 1 734); alle anderen Zahlen der Suiten bleiben, die Kernsuite hat 377 Prüfungen. *O16.* Zellen ohne Wurzel (`zellen_ohne_wurzel` > 0)
behalten α; in den Suiten gibt es sie nur im T-Stoß mit 20-mm-Basiszelle (3 Zellen) und in der Kirsch-Scheibe mit 20-mm-Zellen bei 10 mm Dicke (454 von 865), nicht bei Basiszelle gleich Wanddicke. Ihre Wirkung ist klein: 10⁻⁶ und
7·10⁻⁵ in der Spannung am T-Stoß (p 2 und p 3), an der Kirsch-Scheibe ändert sich K_t zwischen α = 10⁻⁸ und 10⁻¹² nicht (vier Stellen). Eine Warnung wäre ein Fehlalarm (an der Kirsch-Scheibe hat keine der 454 Zellen einen messbaren Einfluss, am T-Stoß liegt die Wirkung zwei bis drei Größenordnungen unter dem Diskretisierungsfehler), und die Größe der Wirkung ist nicht vorhersagbar (die Schätzung α / Anteil^(2p+1) liegt um das 300-Fache und mehr als das 4·10⁵-Fache zu hoch). Deshalb gibt es keine Warnung (Entscheidung des Anwenders am 04.10.2026); die Zahl steht im Protokoll (`aggregation.zellen_ohne_wurzel`). Eine gebaute und zurückgenommene Warnung erfüllte die Regeln für Erscheinen, Prüfungen und Bitgleichheit der Rechnung, nicht die für Fehlalarme (Plan TP 5, Ergebnis O16).

**Nachtrag (O17, 04.10.2026): Genauigkeit der Zwangsmatrix.** Der Boden von einigen 10⁻⁸ in der Spannung (Streifen 30° p 3, Patch-Körper p 4) kommt nicht aus der Genauigkeit der Zwangsmatrix. Gemessen mit einer Referenz C_ref, deren
Fortsetzungs- und Spurabbildungen exakt in rationalen Zahlen als Kronecker-Produkt dreier 1D-Abbildungen gebaut sind: die Einträge der jetzigen C weichen um bis zu 2,7·10⁻¹¹ relativ ab (p 3; volles (p+1)³-System statt Kronecker-Produkt), und
C_ref gibt lineare Felder und Starrkörperverschiebungen zehn- bis vierzigmal genauer wieder (bis auf den Rundungsboden der Auswertung, 10⁻¹⁵), aber der Spannungsfehler der Lösung fällt an keinem Modell um mehr als den Faktor 2,5 und steigt an einigen um bis zu 5,7.
Der Boden ist der Vorwärtsfehler der Lösung in den freien Koeffizienten, verstärkt durch die Größe der Fortsetzung in die aggregierten Zellen: ein Polynom vom Grad p wächst außerhalb seiner Zelle in der Entfernung d (in Halbweiten)
wie d^p je Richtung, die größten Fortsetzungskoeffizienten sind 118 / 353 (p 2) und 6 831 / 34 153 (p 3) an den Streifen mit 10° und 30°. Der Spannungsfehler einer Starrkörperverschiebung von 30 mm geteilt durch diesen Koeffizienten
ist in allen vier Fällen 0,7·10⁻⁹ bis 1,5·10⁻⁹ N/mm², und Rauschen der Größe eps · 30 mm in den freien Koeffizienten allein erzeugt ein Siebtel bis ein Fünfzigstel davon. Darum skaliert der Boden mit dem Betrag der Verschiebung
(Starrkörperanteil) und mit p. Er liegt mit höchstens 5,5·10⁻⁷ relativ vier bis fünf Größenordnungen unter dem Diskretisierungsfehler; die Zwangsmatrix bleibt unverändert (Plan TP 5, Ergebnis O17).

### 11.22 Teilprojekt 6a, Phase 1: residuenbasierter Fehlerschätzer (06.10.2026)

Teilprojekt 6 ist in vier Teile zerlegt (6a Fehlerschätzer und lokale hp-Adaptivität, 6b Kerbspannung mit Referenzradius 1 mm, 6c Stellungen als Mehrfach-rechte-Seiten,
6d Punktwolke und Voxel; Entwurf 4f). 6a läuft in drei Phasen: Phase 1 der Schätzer bei einheitlichem p mit h-Adaptivität, Phase 2 eine echte variable Modenzahl je Zelle,
Phase 3 der hp-Treiber. Der Anwender entschied am 04.10.2026 für einen residuenbasierten Schätzer (gegen Zienkiewicz-Zhu und gegen zielorientierte Schätzer) und für echtes
lokales hp. Dieser Abschnitt beschreibt Phase 1 (`fcm/schaetzer.py`, Plan `packages/volumen3d/docs/plaene/2026-10-06-tp6a-phase1-schaetzer.md`).

**Schätzer.** Je Zelle K mit Kantenlänge h und Grad p

η_K² = (1/E) [ (h/p)² ‖f + div σ_h‖²_{K∩Ω} + ½ Σ_F (h_F/p) ‖[σ_h n]‖²_{F∩Ω} + (h/p) ‖t − σ_h n‖²_{Γ_N∩K} ] + E (p²/h) ‖P (u_h − g)‖²_{Γ_D∩K},

Einheit N mm wie die Energienorm ‖e‖_E² = ∫ (σ_h − σ) · D⁻¹ (σ_h − σ) dV, mit der er verglichen wird; η = (Σ η_K²)^½. Das Zellresiduum braucht zweite Ableitungen: für die
hierarchische Basis ist N_j'' = √((2j−1)/2) P'_{j−1} mit P'_k = Σ (2i+1) P_i über i = k−1, k−3, …, und bei festem Werkstoff div σ = μ Δu + (λ+μ) ∇ div u. Integriert wird über die
Werkstoffpunkte der Zellquadratur, also mit derselben Regel wie die Steifigkeit. Die Sprünge [σ_h n] laufen über alle Flächen zwischen zwei aktiven Zellen, jede Fläche einmal und
von der feineren Zelle aus; an einer hängenden Fläche wird die feine Teilfläche gegen die grobe Nachbarzelle integriert, der Beitrag geht je zur Hälfte an beide Zellen. Den
Werkstoffanteil einer Fläche liefert eine Tensor-Gauß-Regel mit (p+1)² Punkten auf 4 × 4 Unterquadraten und ein Punkttest gegen die Geometrie, das ist erste Ordnung in der
Geometrie. Die Flächenquadratur mit 16 × 16 Unterquadraten ändert η um 0,01 % (Lamé h 5 p 2) und 0,05 % (Kirsch, Ziel 5); eine eben-exakte Flächenintegration ist nicht nötig.

**Ränder.** Freie und belastete Oberfläche sind alle Oberflächenpunkte, die zu keinem Verschiebungsrand gehören; ihre Soll-Traktion t zeichnet `FcmProblem` neben dem
Lastvektor auf (`flaechenlasten`, `volumenlasten`), unbelastet ist sie null. Auf Verschiebungsrändern misst der Nitsche-Rest die verletzte Vorgabe, mit P = I (voll) oder P = n nᵀ
(Normalenrand und Schnittebene). Dazu kommt auf Normalenrändern der tangentiale Traktionsrest (I − n nᵀ) σ_h n und auf Schnittebenen derselbe Rest nach Abzug seiner L²-Projektion auf die
drei Starrkörpermoden in der Ebene: Querkraft und Torsion sind dort als Mittelwertzwänge gehalten (11.6), ihr Anteil an der Tangentialtraktion ist Reaktion und kein Fehler.

**Markieren und teilen.** Dörfler mit θ = 0,5 (kleinste Menge der Zellen mit den größten η_K², die die Hälfte von η² trägt). Markierte Zellen werden über die erzwungenen Teilungen
der Verfeinerung (`Verfeinerung.zellen`, wie bei den Wurzelteilungen der Aggregation, 11.4) geteilt; die 2:1-Balancierung folgt wie sonst.

**Messung** (fester Arbeitsbaum 9fc6966, 8 Threads, nach Regeln, die im Plan vor der Messung feststanden; zwei unabhängige Auswertungen, gleiche Urteile). Lamé gegen die exakte
Lösung (im ebenen Dehnungszustand σ_z = ν (σ_r + σ_φ)), Kirsch und Kragarm (L 1000, B 100, H 200, links voll eingespannt, rechts Querkraft 10 kN als Traktion) gegen die Lösung
desselben Gitters mit p + 2:

| Folge | h bzw. Zielgröße | freie Freiheitsgrade | η | ‖e‖_E | θ = η / ‖e‖_E |
|---|---|---|---|---|---|
| Lamé p 2 | 20 / 10 / 5 | 765 / 4 395 / 28 215 | 9,230 / 2,026 / 0,519 | 2,049 / 0,467 / 0,121 | 4,50 / 4,34 / 4,27 |
| Lamé p 3 | 20 / 10 / 5 | 2 100 / 13 188 / 89 310 | 1,489 / 0,505 / 0,276 | 0,327 / 0,101 / 0,048 | 4,56 / 5,02 / 5,74 |
| Kirsch p 2 | 20 / 10 / 5 | 7 713 / 8 037 / 10 677 | 18,30 / 5,725 / 1,580 | 4,886 / 1,486 / 0,436 | 3,74 / 3,85 / 3,62 |
| Kragarm p 2 | 50 / 25 | 5 535 / 37 179 | 7,445 / 4,506 | 1,420 / 0,851 | 5,24 / 5,30 |

Der Effektivitätsindex θ schwankt je Folge um höchstens den Faktor 1,26 (Regel: 3), η fällt mit derselben Rate wie der wahre Fehler (Steigungen über h: Lamé p 2 2,08 und 2,04,
Lamé p 3 1,22 und 1,38, Kragarm 0,72 und 0,74; Regel: Differenz höchstens 0,3), und von den 10 % Zellen mit größtem η liegen an Lamé h 10 p 2 alle unter den 20 % mit größtem
wahrem Fehler (Regel: die Hälfte). Felder im Ansatzraum ergeben am schräg geschnittenen Patch-Körper η / ‖u‖_E = 7·10⁻¹² bis 1·10⁻¹¹ (linear, p 2), 3,5·10⁻¹² bis 4,1·10⁻¹² (quadratisch, p 2) und
1,8·10⁻¹⁰ bis 2,1·10⁻¹⁰ (kubisch, p 3, je drei Läufe); die Schranken 10⁻⁸ bei p 2 und 10⁻⁷ bei p 3 sind die der Patch-Prüfung (11.21). θ zwischen 4 und 6 heißt: η überschätzt den Energiefehler um diesen Faktor,
gleichbleibend über die Verfeinerung. Bei Lamé ist das Zellresiduum der größte Anteil (p 2 auf h 5: 0,506 von 0,519), bei p 3 wächst der Nitsche-Rest mit der Verfeinerung und mit
ihm θ. Die Kirsch-Folge ist nach der vorab festgelegten Referenzprüfung nicht gewertet: auf dem gröbsten Glied weicht θ mit der Referenz p 3 um 50 % von θ mit der Referenz p 4 ab,
das Loch mit 20 mm Radius ist mit 20-mm-Zellen auch bei p 4 nicht auskonvergiert; auf den feineren Gliedern sind es 4 % und 1 %. Die Kragarm-Folge endet bei h 25, weil die Referenz
bei h 12,5 2,5 Mio. Freiheitsgrade hätte; die niedrige Rate kommt aus den singulären Kanten der voll eingespannten Stirnfläche.

**h-adaptiv: Regel verfehlt.** Die Regel verlangte, dass Dörfler-Teilung ab dem gröbsten Glied nach drei Zyklen den Fehler des feinsten Glieds mit weniger Freiheitsgraden erreicht.
An der Kirsch-Platte fällt der Fehler in drei Zyklen von 4,886 auf 1,347 bei 7 713 → 8 085 freien Freiheitsgraden; das ist bei gleicher Größe besser als das feste Gitter (Ziel 10:
8 037 und 1,486), erreicht aber nicht das feinste Glied (0,436). Am Lamé-Zylinder mit h 20 **steigt** der Fehler mit jedem Zyklus (2,049 / 2,184 / 2,888 / 3,116 bei 765 / 1 065 / 1 674 /
2 388 freien Freiheitsgraden), was bei geschachtelten Ansatzräumen in der Energienorm ausgeschlossen ist. Die Ursache ist die Zellaggregation (11.4). Für den ersten Schritt
(4 Zellen geteilt) fällt der Fehler ohne Aggregation (α = 10⁻⁸) von 1,610 auf 1,263; mit Aggregation fällt er in den geteilten Zellen (e² 1,809 → 1,467), steigt aber in den
ungeteilten (2,390 → 3,303). Im geteilten Gitter sind 52 von 81 Zellen aggregiert, und bei 42 davon liegt die Wurzel außerhalb der eigenen Elternzelle. Die Dicke des Modells (20 mm)
ist gleich der Basiszelle, fast jede Zelle ist an den Ebenen z = 0 und z = 20 geschnitten. Die zuerst vermutete Erklärung (die Teilung hängt die Wurzeln ungeteilter aggregierter Zellen um) hat die Messung widerlegt: sie erklärt 19 % der Zunahme, 63 % liegen in wohlgestellten ungeteilten Zellen mit freien Polynomen (Plan O21, Teil A). Wo die Schachtelung bricht, ist nicht gemessen. Das ist kein Fehler des Schätzers, der die richtigen Zellen markiert, sondern eine Eigenschaft der Aggregation bei lokaler Teilung (Liste O21). Der
Anwender entschied am 06.10.2026, Phase 1 so abzuschließen und O21 vor Phase 2 zu beheben; danach wird die Regel mit denselben Zahlen erneut geprüft.

**Zeit.** Der Schätzer braucht bei Lamé 2 bis 21 % und bei Kirsch 18 bis 32 % der Zeit für Aufbau und Lösen, am Kragarm mit h 25 aber 143 % (5,2 gegen 3,6 s): er läuft in
Python-Schleifen je Zelle und je Fläche, und am kompakten Quader mit vielen inneren Zellen ist der Direktlöser schneller (Liste O22). Flächenlasten, die die Schnittstelle je Lastfall als
fertige Lastvektoren übergibt (`zusatzlasten`), kennt der Schätzer noch nicht (Liste O23); er ist bisher nur über `FcmProblem` erreichbar, nicht über den Vertrag.

**Prüfungen.** `test_schaetzer` (14 Prüfungen): Hesse-Matrizen der Basis gegen den Differenzenquotienten der Gradienten und gegen die geschlossenen 1D-Formen; Aufzeichnung der Lasten;
Flächenpaare gegen eine unabhängige Zählung über die Zellboxen (384 Paare über zwei Ebenen); Werkstoffanteil der Flächen exakt im Werkstoff und auf erste Ordnung gegen das exakt
geclippte Polygon; Felder im Ansatzraum; Lamé p 2 auf h 20 und h 10 (θ 4,50 und 4,34); Dörfler; Teilung einer markierten Zelle. Bis auf Lamé laufen sie in der Kernsuite (390 Prüfungen). Alle Paketsuiten sind mit und ohne den Schätzer grün; der Vergleich Zahl für Zahl findet nur Zeiten und Rundungsunterschiede, die genauso zwischen zwei Läufen desselben Stands auftreten (MKL mit mehreren Threads streut in den letzten Stellen), also keine geänderte Rechnung.

**Nachtrag (O21, 07.10.2026): ganze Aggregate teilen.** Werden markierte Zellen um ihr ganzes Aggregat ergänzt (die Wurzel und alle Zellen mit derselben Wurzel,
`schaetzer.aggregate_ergaenzen`), fällt der wahre Fehler in jedem Zyklus. Gemessen mit Dörfler 0,5 aus einem festen Arbeitsbaum:

| Zyklus | Lamé: freie FHG | Lamé: ‖e‖_E | Kirsch: freie FHG | Kirsch: ‖e‖_E |
|---|---|---|---|---|
| 0 | 765 | 2,049 | 7 713 | 4,886 |
| 1 | 1 701 | 0,994 | 7 821 | 2,549 |
| 2 | 2 229 | 0,715 | 8 319 | 1,126 |
| 3 | 5 397 | 0,534 | 8 961 | 0,669 |
| 4 | 9 399 | 0,293 | 10 149 | 0,477 |
| 5 | 15 345 | 0,204 | 12 879 | 0,293 |
| 6 | 31 485 | 0,179 | 15 837 | 0,224 |
| Vergleichsglied | 28 215 (gleichmäßig h 5) | 0,1215 | 10 677 (Ziel 5 am Loch) | 0,4363 |

Ohne die Ergänzung stieg der Fehler an Lamé in drei Zyklen auf 3,116 (siehe oben). Die Ursache ist eingegrenzt, aber nicht bis ins Letzte gemessen: die Aggregation wählt nie eine
feinere Wurzel, wird eine Wurzel allein geteilt, binden sich die an ihr hängenden Zellen an andere Nachbarn (im ersten Lamé-Schritt drei Zellen), und die Zunahme zeigt sich vor allem
in wohlgestellten Nachbarzellen. Bindet man stattdessen schlecht gestellte Kinder bevorzugt an Geschwister derselben Elternzelle, bleibt der Fehleranstieg. Die Regel, adaptiv das feinste
Vergleichsglied mit weniger Freiheitsgraden zu erreichen, bleibt verfehlt: an Lamé liegen adaptives und gleichmäßiges Gitter bei gleicher Größe etwa gleich (der Fehler ist über den ganzen
Querschnitt verteilt), an Kirsch erreicht die adaptive Folge bei gleicher Größe etwa das von Hand am Loch verfeinerte Gitter (auf 10 677 Freiheitsgrade interpoliert etwa 0,43 gegen 0,436),
mit 10 149 Freiheitsgraden 0,477. Die Aggregation selbst ist unverändert, Rechnungen ohne adaptive Teilung bleiben gleich; `test_schaetzer.test_teilen_ohne_fehlerzunahme` prüft den
ersten Lamé-Schritt mit Ergänzung (2,049 → 0,994) und ohne (2,049 → 2,184).
