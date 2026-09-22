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
`tests/test_verification.py` (26 Benchmarks), dazu je Familie
`tests/test_elemente_volumen.py`, `tests/test_elemente_schalen.py`,
`tests/test_elemente_ebene.py`, `tests/test_elemente_stab.py` und - für das
Zusammenspiel mit Modell, Löser, Netz, Bericht und Schnittstellen -
`tests/test_elemente.py`.

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
und Threadzahl gesondert. Vorher stand dort nur die Zahl des Prozesspools,
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
Jacobi-Determinante" ab. Elemente mit falscher Knotenzahl (`add_element` nimmt
ein hex8 mit sieben Knoten an) übergeht die Prüfung; beim Stapeln der Knoten
warfen sie `check()` in der ersten Fassung mit `ValueError` um, statt eine
Liste zurückzugeben (Gegenprüfung, 23.09.2026).
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
`Analysis.combinations`, in dem Ergebniskombinationen nicht stehen, und
wichen bei leerem `combinations` auf die Lastfälle aus. Gemessen am Kragarm
(LF1 Fz = 10 kN, LF2 Fz = 20 kN an der Spitze), nur mit der
Ergebniskombination {1,35·LF1} oder {1,35·LF1 + 1,5·LF2}: Ausnutzung des
Stabes vorher 0,170 (nachgewiesen gegen LF1 und LF2 mit Faktor 1), jetzt
0,370 wie mit der gewöhnlichen Kombination 1,35·LF1 + 1,5·LF2; das Verhältnis
2,175 ist 4,35e4/2e4. Verformungsnachweis (0,1152) und Volumennachweis
(0,3619, Hexaederstab) stimmen ebenso mit der gewöhnlichen Kombination
überein (`test_umhuellende`).

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
Ergebnisdatei von vor dem 22.09.2026. In der ersten Fassung der Kur wurde sie
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
Fassung der Kur kippte ein Modell nur mit GZG-Kombinationen und Stäben ohne
Nachweis im Gesamturteil von „Alle Nachweise erfüllt." auf „nicht geführt:
EC3 (1 Warnung)" (Kragarm und Halle, Gegenprüfung 23.09.2026). Am Stand bis
22.09.2026 meldeten die Stabnachweise keine fehlenden Kombinationen, und das
Gesamturteil kannte den Eintrag „EC3 (n Warnungen)" nicht. An einem Kragarm
(IPE 300, 3 m, nur eine GZG-Kombination mit Verformungsgrenze, Stab ohne
Nachweis) und an der Halle (nur GZG-Kombinationen, Stäbe ohne Nachweis, eine
Verformungsgrenze) stand dort „Alle Nachweise erfüllt.".

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
(nicht ausgeliefert, Gegenprüfung 23.09.2026) faltete diese Umhüllende erst
nach dem Ersetzen aus `Analysis.cases`: Mit einem Lastfall W auf Theorie
II. Ordnung war eine linear gebliebene Alternative 1,35·G (linear) +
1,5·W (II. Ordnung), und dieses Gemisch ging abgelegt in die Nachweise.
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
Änderung (Stand bis 22.09.2026) gab es das Gemisch ebenfalls nicht:
`solve_all` faltete die Umhüllende einer Ergebniskombination vor
`_lastfaelle_hoeherer_ordnung`, rechnete aber keine Alternative nach
II. Ordnung und wies keine nach (siehe oben). Am Zweigelenkrahmen war die
Umhüllende am Stielkopf 102,1415 mm wie mit der gewöhnlichen Kombination;
die Stäbe wurden ohne Warnung gegen die Lastfälle mit Faktor 1 nachgewiesen,
Stiel links 0,49702 aus W statt 0,542323.

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

`tests/test_situationen.py` prüft das gegen geschlossene Lösungen:
eingespannt-gestützter Balken (7PL³/96EI) gegen den Kragarm nach Abschalten
des zweiten Elements (PL³/3EI), Eigengewicht nur der wirksamen Elemente,
Kragarm um 90° hochgeklappt unter Vertikallast (PL/EA statt PL³/3EI).

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

Kontakt wird mit dem Penalty-Verfahren und einer Aktivmengen-Iteration
berechnet. Für jede Kontaktbedingung gilt der Spalt

    g(u) = g0 + cᵀ u,

c ist der Koeffizientenvektor der beteiligten Freiheitsgrade. Ist g < 0,
werden die Steifigkeit k_n c cᵀ und die Last −k_n g0 c hinzugefügt; die
Kontaktkraft ist F_n = −k_n g ≥ 0. Die Kontaktsteifigkeit wird automatisch
als 10⁴-faches der Diagonalsteifigkeit der beteiligten Knoten gewählt
(Durchdringung etwa 10⁻⁴ der freien Verschiebung) oder vom Anwender
vorgegeben (elastische Bettung).

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
   fest. Je Runde geht nur der am stärksten über der Reibgrenze liegende
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
Geometrie, Protokoll „Warmstart verworfen“). Gemessen am 12.09.2026: Block
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
| `art` | `Lastfall` (ohne Fließen), sonst `Vorlauf`, `Laststufe`, `Newton`, `Fliessschritt` (Anfangsdehnung), `Abschluss`; bei einem Abbruch in der Fließ-Iteration vorläufig `Fliessen` |
| `stufe`, `schritt`, `tangente` | nur bei Fließen: Laststufe, Schritt darin, ob mit der konsistenten Tangente gelöst wurde |
| `schritte`, `faktorisierungen` | dieses Laufs (Summe über alle = die bisherigen Summenwerte) |
| `konvergiert`, `grund` | `grund` ist `''` oder `deckel`, `max_iter`, `probelauf`, `eingefroren`, `abbruch` |
| `warm`, `neustart` | Start aus einem Kontaktzustand angenommen; Warmstart verworfen oder zurückgesetzt und neu gerechnet |
| `start_von_lauf` | Nummer des Laufs, dessen Zustand der Start war; 0 = der dem Lastfall angebotene Start; `None` = kalt; −1 = ein von außen übergebener Zustand unbekannter Herkunft |
| `zyklen`, `phase`, `n_aktiv`, `n_gleitet` | Zustand am Ende des Laufs (`cycles`, Phase, geschlossene und gleitende Bedingungen) |
| `runden` | je Kontaktschritt ein Zahlentupel nach `contact.RUNDEN_FELDER` (unten) |
| `endzustand_kennung` | 16 Hexziffern, prozessfest (unten) |
| `u_max` | größte Knotenverschiebung [m], Betrag nur über die drei Verschiebungen — dasselbe Maß wie „max\|u\|" der Drehlager-Messungen |

`contact_laeufe`, `contact_letzter_lauf_konvergiert` und
`contact_laeufe_nicht_konvergiert` werden seitdem aus dem Laufbuch
**abgeleitet** (Länge, letzter Eintrag, Zahl der nicht konvergierten), nicht
mehr getrennt hochgezählt. Ein Kontaktabbruch (`KontaktAbbruch`) bekommt in
`_teilergebnis_anhaengen` einen eigenen Eintrag mit Grund `abbruch`;
`faktorisierungen` ist dort `None`, weil der Lauf kein `cinfo` zurückgab.

**`konvergiert` und `grund`.** Für jeden Eintrag gilt `konvergiert ==
(grund == '')` — mit **einer** Ausnahme: ein eingefrorener Zustand
(`einfrieren=…`) meldet wie bisher `konvergiert = True`, trägt aber den Grund
`eingefroren`. Er hat nicht iteriert; ob seine Referenz konvergiert war, steht
bei der Referenz (`contact_frozen_from`). Der Grund folgt demselben Entscheid
wie der Meldetext am Ende von `solve_with_contact` (Probelauf vor Deckel vor
Schrittgrenze).

**Die Art ohne neue Signatur.** `plastizitaet.iteration` wird aus Tests mit
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

**Gleichgewicht am verformten System.** Gelöst wird (K + K_g(N)) u = F.
Weil K_g von den Normalkräften abhängt und diese von u, wird iteriert, bis
sich die Verformungen nicht mehr ändern (Abbruch bei einer relativen Änderung
unter 1·10⁻⁶). K_g ist die geometrische Steifigkeit des Stabelements; das
Element rechnet mit Schubverformung, die Verzweigungslast ist deshalb die
nach Engesser

      N_cr = N_E / (1 + N_E/(G A_s)),   N_E = π² E I / L_cr²

und liegt bei gedrungenen Profilen rund ein halbes Prozent unter der
schubstarren Eulerlast — die Verifikation prüft genau das.

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
Lastfallergebnisse bleiben Ergebnisse nach Theorie I. Ordnung und dürfen nicht
mehr überlagert werden — der Bericht sagt das.

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

#### 5.5-3 Volumen: Hauptspannung im Element

Ein Volumen hat keine Nennspannung. Als Spannungsgröße je Element und Zustand
dient die **vorzeichenbehaftete Hauptspannung mit dem größten Betrag** aus dem
Spannungstensor der Elementmitte: σ₁, wenn |σ₁| ≥ |σ₃|, sonst σ₃. Ein
Zugkörper gibt +σ, ein Druckkörper −σ, und die Schwingbreite zwischen zwei
Zuständen ist die Differenz dieser Größe — nicht die Differenz zweier Beträge,
die einen Wechsel von Zug auf Druck verschluckte. Aus dem Verlauf der Größe
entsteht je Element das Kollektiv wie beim Stab (spanne, Rainflow,
Reservoir), die Schädigung nach Palmgren-Miner mit der Wöhlerlinie für
Normalspannungen und γMf nach Konzept und Schadensfolge des Körpers;
maßgebend je Körper das Element mit dem größten D, und die Ausnutzung je
Element steht für die Färbung bereit.

Die Hauptspannungen kommen geschlossen (Cardano, trigonometrisch) für alle
Elemente auf einmal: 200 000 Tensoren in unter 2 s, gegen `eigvalsh` je
Element in einer Schleife — bei 2 Mio. Elementen und 164 Zuständen des
Drehlagers Minuten je Zustand. Geprüft an 2000 Zufallstensoren gegen
`eigvalsh` (Abweichung unter 10 Pa bei 50 MPa), Patch-Test am Zugstab aus
10 × 2 × 2 Hexaedern: Δσ = ΔF/A = 60,0 N/mm² auf 10⁻⁶ genau, D wie die
Handrechnung mit `sn_life`, Druck wie Zug (`tests/test_ermuedung_verlauf.py`).

**Grenzen.** Es ist die Spannung in der Elementmitte: bei Biegung durch den
Körper liegt der Rand höher (Kapitel 5d: 43,3 gegen 60,3 N/mm² am Kragarm aus
Hexaedern) — für Ermüdung unter Biegung ist das Netz über die Höhe fein zu
wählen. Die Größe ist eine Struktur- oder Kerbspannung, keine Nennspannung:
die Kerbfälle der Tabellen 8.1–8.10 gelten nur, wo das Element die
Nennspannung abbildet (glatter Grundwerkstoff); an Nähten und Kerben gehört
ein Kerbfall des Struktur- oder Kerbspannungskonzepts dazu (IIW: FAT 225 für
die Kerbspannung mit r = 1 mm). Der Vorschlag des Programms (160,
Grundwerkstoff; `ec3/kerbfaelle.py`) ist dafür ein Anfang, kein Befund.
Rainflow und Reservoir zählen je Element einzeln und sind bei großen Körpern
langsam; die Spanne ist vektorisiert.

**Verschweißte Berührungsstellen.** Ein Knoten, den zwei Körper teilen, ist
eine durchverbundene Stelle: der Vernetzer teilt Knoten nur über eine
gemeinsame Fläche (RFEM: eine Fläche zwischen zwei Volumen), und eine
ausgeführte Kontaktfuge verdoppelt sie (Kapitel 4.0). Ohne eingegebene
Kontaktbedingung zwischen den beiden Körpern ist das ein Stoß, der in
Wirklichkeit geschweißt ist (Anweisung des Anwenders vom 11.09.2026). Die
Elemente mit einem solchen Knoten — eine Elementlage beiderseits — tragen den
Kerbfall „Naht" ihres Körpers, Vorschlag 90 N/mm² nach Anhang B, Tabelle B.1,
Detail 7 (Kreuzstoß mit tragenden Kehlnähten, Strukturspannung); voll
durchgeschweißt wäre Detail 3 mit 100. Die Wöhlerlinie läuft dafür mit einem
Kerbfall je Element (`_n_vektor` mit Feld). Die Zuordnung ist ein Durchlauf
über alle Elementknoten (`nahtknoten`), am Drehlager 8 Mio. Einträge in
Sekunden; Paare mit Kontaktbedingung (`kontaktpaare`, aus `koerpernamen` und
Gegenkörpern bzw. den Besitzern der Gegenflächen) bleiben außen vor.
Gemessen am Drehlager: 47 gemeinsame Flächen zwischen 25 Körperpaaren,
keine davon von einer der 12 Kontaktbedingungen genannt — die Kontakte
liegen dort auf getrennten, deckungsgleichen Flächen. Grenze: teilen zwei
Körper nur eine Kante, zählt die Elementlage an der Kante mit — sie liegt
ohnehin an einem Stoß. Geprüft an zwei Körpern aus einem Hexaedernetz
(`test_naht_beruehrung`): 9 Nahtknoten in der Ebene x = 1 m, vier Elemente
je Körper an der Naht, maßgebend eines davon mit D nach der Wöhlerlinie 90,
der Nachbarkörper ohne Nahtkerbfall mit 160; mit Kontaktbedingung keine
Nahtknoten.

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
(„Knoten 812 (geglättet, σ·n = 0)“). Die **Ermüdung** der Volumen liest nicht die
Randspannung, sondern `res.solid_res` je Element — sie ändert sich dadurch nicht.

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
Hauptspannung im Element steht in 5.5-3.

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

## 5a Anschlüsse (DIN EN 1993-1-8)

Ein Anschluss sitzt an einem Stabende. Die Beanspruchung sind die
**Stabendschnittgrößen** N, V_z und M_y an diesem Ende, gedreht so, dass ein
positives N Zug bedeutet (dieselbe Zählweise wie in `beam_end_forces`). Der
Anschluss wird über **alle GZT-Kombinationen** geführt; die ungünstigste ist
maßgebend. Die Aufteilung der Schnittgrößen auf die Bauteile folgt der
üblichen Modellvorstellung:

* Kopfplatte: Flanschkraft F_t = |M_y|/(h − t_f) + N·A_f/A auf die Schrauben
  der Zugzone, Querkraft gleichmäßig auf alle Schrauben, Druckflansch gegen
  b·t_f·f_y.
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
  Kombination. Der Knicklastfaktor λ multipliziert die Lasten des
  Grundzustands.

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
  gewöhnlichen Tetraeder weiter, und das Protokoll sagt es.
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
  (`test_arbeiter_laden_aus_datei`).
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
  „… nicht geführt wurden: 1 Stäbe (EC3) (siehe die Hinweise unten).",
  darunter „Es liegen keine offenen Hinweise oder Warnungen vor." Jetzt legt
  die Zusammenfassung den Hinweis an, an der Stelle, an der sie die nicht
  geführten Stäbe für die Statuszeile zählt — beides kommt aus derselben
  Liste.
* **Kein einziger Stab geführt.** Die Wesentlichen Ergebnisse bildeten die
  größte Ausnutzung über alle Stäbe, auch über die nicht geführten. Mit einem
  einzigen Riegel ohne f_y standen dort „max. Ausnutzung Nachweise EC3" mit
  0.000 und „maßgebend" mit „Stab Riegel_ohne_fy: , Kombination , x = 0.00 m", die
  Statuszeile sagte „Alle **geführten** Nachweise erfüllt – nicht geführt
  wurden: 1 Stäbe (EC3)", obwohl kein Nachweis geführt war. Jetzt zählt nur
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

**„Alle Nachweise erfüllt." galt auch bei gerissenem Volumennachweis.**
`self.volumen` fehlte im Gesamturteil **doppelt**: in der Statusprüfung und in
der Liste der geführten Nachweise. Ein Modell, das nur aus Volumen besteht — am
Drehlager der Regelfall —, bekam entweder „Es wurden keine Nachweise geführt"
oder „Alle Nachweise erfüllt", während der geführte Nachweis riss. Die eine
Zeile, die ein Prüfer als Gesamturteil liest, sagt jetzt:
*„Alle **geführten** Nachweise erfüllt – nicht geführt wurden: …"*

Geprüft wird das am reinen Volumenmodell selbst, nicht nur am Balken mit Stab:
dort fällt ein fehlender Eintrag „Volumen" in der Liste der geführten
Nachweise nicht auf, weil der Stab den Nachweis schon als geführt zählt.
Zugkörper 100 × 100 mm aus S355 ohne Stäbe: bei N = 4000 kN ist die
Ausnutzung 1,194 und die Statuszeile „Nachweise NICHT erfüllt", bei
N = 2500 kN 0,746 und „Alle Nachweise erfüllt.". Mit dem alten Stand stand in
beiden Fällen „Es wurden keine Nachweise geführt; …" mit grüner Kennung
(`test_gesamturteil_reines_volumenmodell`).

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

**Die übrigen 31 Befunde sind nicht behoben**, aber aufgeschrieben (mit Datei,
Zeile und der Gegenprüfung, die sie nicht widerlegen konnte). Darunter: die
Netzabnahme meldet „bestanden", obwohl Prüfungen ausgefallen sind; der
RFEM-6-Import lässt Stablasten still weg und wirft die Lastrichtung von
Flächenlasten weg; eine Viereckfuge wird nur zur Hälfte gezählt; der
Volumennachweis rechnet ohne Dickenabminderung.

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
| Knoten im Rechennetz ohne Element | 0 | die Elementliste |
| Formgüte des schlechtesten Elements je Körper | ≥ 0,05 (`ABNAHME_ELEMENTGUETE`) | `netzguete.guete` |
| Randtreue je Körper | ≥ 99 % (`ABNAHME_RANDTREUE`) | `Volumenkoerper.randtreue` |
| Volumenbilanz je Körper | ≤ 0,5 % (`ABNAHME_VOLUMENBILANZ`), an windschiefen Flächen zuzüglich Σ A · Abstand der Netzseiten | `elementvolumina` gegen `_polyederhuelle` |
| Seiten im Inneren (FEHLER) / Lücke im Netzrand (WARNUNG, über 0,5 % des Körpers FEHLER) / Riss im Netz, Netzrand neben der Hülle (WARNUNG) | 0 | freie Elementseiten gegen die Randflächen, Abstand ≤ 1 % der Seitengröße (`ABNAHME_HUELLABSTAND`), an windschiefen Flächen zuzüglich der örtlichen Sehnengrenze (`_sehnengrenze`, `ABNAHME_SCHIEF_RINGE`) und nur in Richtung der Fläche (`ABNAHME_SCHIEF_RICHTUNG`); Gruppen im Inneren: `_gruppen_im_inneren` (Riss: t/L ≤ 5 % `ABNAHME_RISS_DICKE`, t ≤ 0,65 · Dicke der Nachbarn `ABNAHME_RISS_NACHBAR`, kein verdrehtes Element, keine doppelten Knoten) |

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
  Abweichung läge in derselben Größe wie das Gesuchte.
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
   bilden, je Seite gezählt (`ABNAHME_RISS_NACHBAR`, `_elementdicke`), und
4. **kein verdrehtes Element und keine doppelten Knoten** enthält: kein
   Sechsflächner, Keil oder keine Pyramide der Gruppe mit einer Kante, die
   kein anderes Element hat und nicht auf der Hülle liegt
   (`_verdrehte_elemente`, dieselbe Prüfung wie bei der Lücke im Netzrand),
   und keine zwei Knoten der Seiten im Inneren mit verschiedener Nummer am
   selben Ort (`ABNAHME_FUGENNAEHE` = 10⁻⁶ m).

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
| Lücken des freien Vernetzers (dieselben 30 Gruppen) | 0 bis 0,482 |
| fehlender Sechsflächner, gleichmäßig 100 × 100 × 100 bis 500 mm und abgestuft wie oben | 1,00 bis 1,01 |
| fehlender Kuhn-Tetraeder, gleichmäßig und abgestuft wie oben | 0,865 bis 1,07 |
| verdrehter Sechsflächner, gleichmäßig und abgestuft wie oben | 0,21 bis 2,7 |
| fehlender Tetraeder der Platte mit Bohrung, die 40 kleinsten mit V/L³ über 0,04 | 0,55 bis 1,34 |
| fehlender flacher Tetraeder derselben Platte, Elemente 22584 / 2514 / 28444 (eigenes t/L 0,90 / 2,92 / 4,96 %) | 0,100 / 0,390 / 0,529 |

Die Grenze 0,65 liegt zwischen 0,482 und 0,865 (Faktor 1,35 und 1,33). Die
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

Die Kehrseite: Fehlt ein Tetraeder, der selbst so flach ist wie die, die der
Vernetzer aussortiert, ist auch das ein Riss. Einzeln entfernt am frei
vernetzten Würfel mit um 0,5 m angehobener Ecke (h 0,25, 1483 tet4) bei 20 von
541 inneren Tetraedern, an der Platte mit Keilen (2701 tet4) bei 75 von 947,
an der Platte mit Bohrung bei 4 von 40 zufällig gezogenen und bei den 15
flachsten (eigenes t/L 0,44 bis 0,71 %). Die so entfernten Tetraeder hatten
ein eigenes t/L von höchstens 4,98 %; jeder entfernte Tetraeder mit eigenem
t/L über 5 % war in diesen Messungen ein FEHLER.

Rand der Gruppen des Vernetzers 0 bis 5,6 % der Seitenfläche. Offene Gruppen:
drei Würfel in einer Reihe mit verdrehtem mittlerem 41 %, verdrehter Boden
26 %, verdrehtes Eckelement 30 %, eine Trennfläche aus doppelten Knoten, die
bis an die Hülle geht, 100 % (ein Ufer ohne Gegenüber). Ist dagegen nur ein
Sechsflächner im Inneren an den vier Knoten einer Seite losgelöst, ist die
Gruppe geschlossen und hat kein Volumen; das fängt Bedingung 4. Die Summe
der Flächenvektoren taugt als Merkmal nicht: in der Reihe heben sich die
vordere und die hintere Öffnung auf (|Σ S| = 0, scheinbares Volumen 0).

Die erste Fassung (22.09.2026) verlangte Ebenheit auf 1 % des
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

Zwei Hohlräume, die sich nur an einer Kante berühren (dort liegen vier
Seiten), werden getrennt beurteilt — aber nur, wenn jedes Teil für sich
geschlossen ist. An der Platte mit Bohrung berührte ein fehlender Tetraeder
(4,27e-10 m³) eine Lücke des Vernetzers (3,4e-11 m³); zusammengezählt war
t/L = 4,8 %, ein Riss. Ohne die Bedingung zerfiel dagegen ein Haufen aus
15 Seiten (Rand 5,6 %) in drei geschlossene und zwei offene Stücke, und
3 Seiten wurden ein FEHLER.

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
* wenn sie **kein Volumen** hat (t/L ≤ 5 %, Bedingung 2 des Risses): ein
  Ufer, dessen Rand auf der Hülle liegt, ist ein Schnitt;
* wenn sich kein p₀ findet: Die Schleife um einen Körper, den doppelte Knoten
  zerschneiden, läuft über gegenüberliegende Flächen.

Die Lücken eines Körpers sind eine WARNUNG mit Ort (Mitte der größten
Schleife), Volumen und Anteil am Körper. Ein FEHLER werden sie, wenn sie
zusammen mehr als `ABNAHME_VOLUMENBILANZ` = 0,5 % des Körpers ausmachen.
Gemessen an den Netzen des eigenen Vernetzers mit Lücke (L-, T- und
U-Prismen, Standardweg): Lücken von 0,006 bis 0,113 % des Körpers. Der
Text nennt die Abhilfen, die an diesen fünf Prismen gemessen halfen (Sweep,
gmsh, Netgen: 5 von 5; andere
Ziellänge 3 bis 4 von 5; MMG3D 0 von 5), und dass neu vernetzen mit denselben
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
(`gui.main._vernetzen`) löscht nur die Elemente. So nachgestellt, ohne Qt:
6173 tet4, aber 1229 Knoten ohne Element, FEHLER. Einen Hohlraum,
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
  windschiefen Fläche, wenn Schwerpunkt **und Ecken** höchstens 1 % ihres
  Durchmessers plus s_b H² danebenliegen, s_b = |d| / (4 σ_min²). H ist
  **örtlich**: der größte Seitendurchmesser unter den Seiten dieser Fläche,
  die höchstens drei Ringe (Nachbarn über gemeinsame Knoten) entfernt sind
  (`ABNAHME_SCHIEF_RINGE`, `_ringmax`). Gezählt werden dabei nur Seiten, die
  eine Vorauswahl bestehen: Schwerpunkt nicht weiter als s_b (2 D_e)² daneben
  (D_e die Diagonale des eigenen Elements) und die Richtung stimmt. Die Knoten
  liegen auf Sehnen des groben Netzes, das größer ist als die Seiten, die
  daraus werden. Am freien Würfel (dz 0,3 / 0,5 / 1,0 bei h 0,25, dz 1,0 bei
  h 0,5, dz 0,3 und 1,0 bei h 0,1), Ecken-Abstand weniger 1 % durch s_b H²:
  mit H aus der eigenen Seite bis 1,83, aus einem Ring 1,33, aus zwei 1,21,
  aus drei 0,46. Die Grenze liegt dort bei dz = 0,5 zwischen 13,2 und
  19,7 mm, gegen Ecken bis 7,55 mm.
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
  windschiefen Flächen nicht. Am abgebildeten 4 × 4 × 4-Netz (dz = 0,5) bleibt
  eine Beule von 25 mm ungenannt, eine von 30 mm ist eine WARNUNG; bei
  dz = 1,0 bleibt auch eine von 100 mm ungenannt (nachgemessen mit der
  örtlichen Grenze). Ein fehlender Tetraeder am windschiefen Deckel des freien
  Netzes ist eine Lücke im Netzrand (2,892e-4 m³ gemeldet, der Tetraeder hat
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
konformen tet4-Netz aus `grid_box` (40 000 Elemente, jede innere Zellseite
ein Riss, 91 200 Seiten) braucht `_abnahme_netz` 7,6–7,7 s gegen 7,0–7,1 s
im alten Stand. Mit Dicke der Nachbarn, verdrehten Elementen und doppelten
Knoten (vierte Fassung) nachgemessen, je viermal: 7,72–7,87 s gegen
7,59–7,72 s. Die Dicke wird nur für die Elemente an Seiten im Inneren
gerechnet, die Suche nach doppelten Knoten und verdrehten Elementen nur, wenn
eine Gruppe sonst ein Riss wäre. Ein Körper mit krummen Randlinien wird an der
ersten krummen Linie verlassen, bevor ein Element angefasst wird.

**Elemente, die eine Fuge überspannen.** Beim Ausführen einer Fuge werden die
gemeinsamen Randknoten verdoppelt und die Elemente der gelösten Seite auf die
neuen Nummern umgehängt. Danach darf kein Element einen Knoten der alten und
einen der neuen Seite zugleich benutzen — sonst überbrückt es genau die
Trennung, die eben entstanden ist, und die Fuge wirkt dort nicht. Die Prüfung
ist billig: für jedes getrennte Paar (alt, neu) darf kein Element beide
Nummern enthalten; ein Durchgang über die Elemente genügt (0,44 s bei 489 376
Elementen). Das ist der Fall, den man von außen als „halb vernetzt" sieht.

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
| `tests/test_verification.py` | 26 Benchmarks Stab/Schale/Volumen (analytisch, Patch-Tests) |
| `tests/test_supports.py` | Lager mit Ausfall bei Zug/Druck, Schlupf, Reibung, Grenzkraft; Linien- und Flächenlager; Federgelenke gegen Handrechnungen |
| `tests/test_sections.py` | Profildatenbank nach Land gegen Katalogwerte, Hauptachsen der Winkel, zusammengesetzte Querschnitte |
| `tests/test_gzg.py` | Verformungsnachweise gegen 5qL⁴/384EI, PL³/48EI und den Kragarm; Grenzwertbildung L/x, absolut, Überhöhung, Punktpaar |
| `tests/test_beulen.py` | Beulwerte k_σ und k_τ gegen Tab. 4.1/4.2 und A.3, σ_E = 190000 (t/b)², ρ und χ_w gegen 4.4(2) und Tab. 5.1, Schubbeulen, Methode der reduzierten Spannungen, Steifen nach A.1/A.2.2/A.3(2) und Abschnitt 9, Lasteinleitung nach Abschnitt 6, Schalenbeulen nach EN 1993-1-6, dazu der Patch-Test des Viereckelements |
| `tests/test_joints.py` | Schrauben, Nähte, T-Stummel gegen EN-Zahlenwerte; Steifigkeitsbeiwerte Tab. 6.11, Klassifizierung 5.2.2.5, Drehfeder gegen die geschlossene Kragarmlösung |
| `tests/test_volumen.py` | Vergleichsspannung, Hauptspannungen und Mehrachsigkeit gegen die geschlossenen Werte (einachsiger Zug, reiner Schub √3 τ, hydrostatischer Druck σ_v = 0, Tresca/Mises = 2/√3), σ_v = N/A am Zugkörper aus Hexaedern, Singularitäts- und Netzfeinheitshinweise |
| `tests/test_theorie2.py` | α_cr der Kragstütze und des Pendelstabes gegen die Knicklast nach Engesser, Vergrößerung der Verformung gegen 1/(1−N/N_cr), φ und e_0 gegen 5.3.2 und Tabelle 5.1, Gleichgewicht der Ersatzlastbilder, Feldmoment aus der Vorkrümmung, Kriterium 5.3.2(6) |
| `tests/test_klasse4.py` | wirksame Querschnitte der Klasse 4: Beulwerte, Grenzschlankheiten und ρ nach 4.4(2), Aufteilung b_e1/b_e2, W_eff,y und A_eff eines geschweißten Blechträgers gegen eine unabhängige Handrechnung, Zusatzmoment aus e_N, Schalenbeulen schlanker Kreisrohre |
| `tests/test_rfem.py` | native RFEM/RSTAB-Dateien (SQLite, ZIP, unbekanntes Binärformat) und erweiterter Tabellenimport |
| `tests/test_solver_ext.py` | Gelenke, Trapezlasten, Temperatur, Zwischenstellen, Superposition, Umhüllende, Kombinationsgenerator, einseitige Lager, Spaltelement, Flächenkontakt mit Reibung, parallele Assemblierung, Rechnerfarm |
| `tests/test_ec3.py` | Klassifizierung, Querschnittsnachweise, Knicken (χ), M_cr, χ_LT, C1/C_m, Interaktion, Wöhlerlinien, Nachweisführung |
| `tests/test_importers.py` | Import DXF, IFC, SAF, RFEM-Tabellen, INP, BDF |
| `tests/test_report.py` | Berichtserzeugung |
| `tests/test_tetp.py` | Tetraeder mit Ordnung p: Integrationsregeln gegen alle Monome, Vollständigkeit bis p = 4, sechs Starrkörpermoden, Patch-Test (verzerrt, gemischte Ordnung, lineare Pflichtseite, gekrümmt), Stapel gegen Einzelweg, Masse und Lasten, Kragarm auf 1 N/mm², umgeklapptes Element; am Modell Übergang zu tet4, Kontakt- und Lagerseiten, getrennte Fuge, laute Pflichtprüfung, Importreihenfolge, tet10-Nachbar, Jacobi-Prüfung gekrümmter Elemente |
| `tests/test_tetp_rechnung.py` | dasselbe Element durch den Löser: Model.ndof mit und ohne tetp (ohne Lauf über die Elemente), laute Abweisung veralteter FHG-Zahlen, Kragarm-Knotenmittel auf 1 N/mm², Lastsummen, Patch-Test tet4/tetp3 gemischt, Symmetrieebenen, Temperatur; je Lastart tetp2/3/4 gegen geschlossene Lösung und tet10; Linienlager starr und federnd |

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

**Offen.** Kantenmitten auf der wahren Geometrie an Bauteilen liefert erst der
Vernetzer (V2); aus dessen tet10 macht `aus_tet10` gekrümmte `tetp`, die Wahl der Ordnung je Element in der
Oberfläche und automatisch, ein Fehlerschätzer für höhere Ordnung
(`netzfehler` behandelt das Element vorerst wie einen tet4) und die Messung
der Rechenzeit am Drehlager. Der Anwender hat festgelegt, dass die Rechnung dort nicht länger werden darf als heute. Ob das
Element das schafft, zeigt erst die Messung M3.
