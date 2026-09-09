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
zu liefern.

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
die Resonanzerkennung und die Ermüdungskette.

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

**Die Gegenseite des Kontaktpaars** wird nicht über die Liste der Flächen
gesucht, an denen die Freigabe hängt (die ist in RFEM-Dateien unvollständig),
sondern über die Geometrie - wie in ANSYS über einen **Suchradius** (Pinball):
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
die räumlich nächste; **gemessen** wird längs der Normalen. Dasselbe gilt im
Löser für die Zuordnung Knoten gegen Master-Facette.

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

Aus der Wirkung je Freiheitsgrad folgt die Art des Kontaktpaars: Zug *starr*
(oder Feder) → die Bedingung öffnet nie, auch Zug wird übertragen (Verbund,
ohne Trennung); Schub *starr* → **haftend**, die Fugenebene ist eine Feder ohne
Gleiten (Rau, Verbund); sonst Kontakt mit Abheben und Coulomb-Reibung μ.
Verdrehungen wirken nur bei Schalen; zwischen Volumen bleiben sie ohne Wirkung
(das Protokoll sagt es).

Die Verbindung je Freiheitsgrad folgt der Freigabe: *starr* → Kopplung mit
Straffeder, *Feder c* [N/m je m²] → Kopplung mit c · A (A = Einflussfläche des
Knotens, ein Drittel der anliegenden Dreiecke – dieselbe Aufteilung wie bei
einer Flächenlast), *frei mit Ausfall* → Spaltelement. Ein Reibbeiwert geht als
Coulomb-Reibung in das Spaltelement; die Reibkraft hängt damit an der
wirklichen Kontaktkraft.

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

### 4.1 Lager mit Ausfall, Schlupf, Reibung und Grenzkraft

Knoten-, Linien- und Flächenlager werden zunächst einheitlich auf
Knotenfreiheitsgrade umgelegt (`statik3d/supports.py`): Linienlager über die
Einflusslänge (halbe Nachbarabschnitte), Flächenlager über die Einflussfläche
der Knoten. Lineare Anteile (starr, Feder) gehen in die Sperrung bzw. in die
Steifigkeitsmatrix, nichtlineare Anteile in dieselbe Aktivmengen-Iteration wie
der Kontakt.

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
nennen; daraus zählt Statik3D das Kollektiv nach EN 1993-1-9, Anhang A.

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
**Wo wird ausgewertet?** Je Element an der Mitte **und** an den Eckpunkten
(Hexaeder 9 Punkte, Tet10 5, Tet4 einer — dort ist die Spannung konstant).
Die Elementmitte allein genügt nicht: bei Biegung durch den Körper liegt die
Randspannung deutlich höher. Am Kragarm aus Hexaedern mit vier Elementen über
die Höhe gibt die Mitte 43,3 N/mm², der Eckpunkt 60,3 N/mm² — die
Balkenlösung M/W ist 60,0 N/mm². Ein Nachweis aus Mittelpunktspannungen läge
also um rund 28 % auf der unsicheren Seite. Maßgebend ist der größte Wert
über alle Elemente, Punkte und GZT-Kombinationen.

Für den Hexaeder werden die inkompatiblen Moden dabei einmal je Element
gelöst und danach alle Punkte damit ausgewertet.

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

Wird ein **Kerbradius** angegeben, prüft das Programm zusätzlich, ob die
mittlere Elementgröße h ≤ r/3 ist — sonst liegen weniger als drei Elemente
über den Radius und die Kerbspannung wird unterschätzt.

**Grenzen**: Keine Stabilität des Volumenkörpers — die geometrische
Steifigkeit ist nur für Stabelemente gebildet, ein Verzweigungsproblem für
Volumen gibt es nicht. Kein Plastizieren, kein Kriechen, keine Ermüdung aus
dem räumlichen Spannungszustand (dafür wären Kerbspannungs- oder Struktur-
spannungskonzepte nötig) und nicht der Sprödbruchnachweis nach EN 1993-1-10
selbst.

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
die nur zu einem Tetraeder zählt. Das sind zuerst die Hüllpunkte, aber nicht
nur sie. Beim Aussortieren fällt auch der eine oder andere fast flache
Tetraeder im Inneren heraus, und an seiner Stelle bleibt ein volumenloser
Schlitz; dessen Knoten liegen ebenfalls auf dem Netzrand, und sie zu
verschieben zöge den Schlitz auf. An einer 2 × 2 m großen Platte mit Bohrung
(26 980 Tetraeder) waren das acht Knoten, drei davon wurden verschoben, und
das Volumen änderte sich dabei um 0,39 ppm — nach der Korrektur um **0,00
ppm** (`test_splitter_glaetten`). An einer Platte
mit Bohrung steigt die schlechteste Güte damit von 0,0035 auf 0,102, und kein
Element bleibt unter 0,1. Wo alle vier Knoten eines Splitters auf dem Rand
liegen, lässt er sich nicht glätten; seine Zahl steht dann im Protokoll.

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

**Grenzen.** Ist eine Zielkantenlänge für ein Bauteil zu grob (weniger als vier
Elemente über seine größte Ausdehnung), wird sie für dieses Bauteil verkleinert
und das gemeldet.

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

## 7 Parallelisierung

* Elementschleifen (Assemblierung, Nachlauf) werden ab 1500 Elementen in
  Blöcke zerlegt und auf einen Prozess-Pool verteilt; das Modell wird je
  Prozess einmal übertragen.
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
