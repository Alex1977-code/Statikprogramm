# Statik3D – Theoriehandbuch

Dieses Handbuch beschreibt die Rechenverfahren, Annahmen und Normbezüge von
Statik3D. Es dient als Grundlage für die Prüfung der Ergebnisse und für die
Dokumentation in statischen Berichten.

## 1 Grundlagen

### 1.1 Einheiten und Vorzeichen

* Einheiten durchgängig SI: Länge m, Kraft N, Spannung Pa, Dichte kg/m³,
  Temperatur K. Die Oberfläche und der Bericht rechnen zur Anzeige in kN,
  kNm, MPa, mm um.
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

| Element | Formulierung | Freiheitsgrade |
|---|---|---|
| beam | Räumlicher Balken, Timoshenko-Schubverformung wenn Schubflächen > 0, Saint-Venant-Torsion, Momentengelenke durch statische Kondensation | 12 |
| truss | Fachwerkstab, nur Normalkraft | 6 (Translation) |
| shell3 | Ebene Schale = CST-Scheibe (Membran) + DKT-Platte (Batoz/Bathe/Ho), künstliche Drillsteifigkeit | 18 |
| shell4 | Viereck als Mittelung beider Diagonalzerlegungen in shell3 | 24 |
| tet4 | Linearer Tetraeder (konstante Dehnung) | 12 |
| tet10 | Quadratischer Tetraeder, 4 Gaußpunkte | 30 |
| hex8 | Trilinearer Hexaeder mit inkompatiblen Moden (Wilson/Taylor), 8 Gaußpunkte | 24 |

Die Elemente sind gegen analytische Lösungen und Patch-Tests verifiziert
(`python -m tests.test_verification`, 26 Benchmarks).

### 1.3 Gleichungslöser

Die globale Steifigkeitsmatrix wird als dünnbesetzte Matrix assembliert und
einmal faktorisiert (SuperLU; optional Intel MKL Pardiso über `pypardiso`
oder CHOLMOD über `scikit-sparse`, wenn installiert). Alle Lastfälle werden
mit derselben Faktorisierung gelöst. Nach dem Lösen wird das Residuum
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

* **Stellung**: die bewegten Knoten werden um die Achse der Stellung gedreht
  (Rotationsmatrix nach Rodrigues, `bridges.positions.drehmatrix`), die in
  der Stellung unwirksamen Lager entfallen. Gerechnet wird auf dieser Kopie
  des Modells; Ergebnisse und Bild beziehen sich auf die gedrehte Lage.
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
`releasedSurfaces` seine Kopien der Fugenfläche, `assignedToObjects` die
Flächen der Gegenseite. Der Vernetzer teilt Knoten nur über **dieselbe**
Fläche; zwei Bauteile mit je eigener Fugenfläche teilen deshalb nur die Knoten
ihrer gemeinsamen **Randlinien**. Daraus folgen zwei Fälle:

| Netze an der Fuge | Woran man es erkennt | Umsetzung |
|---|---|---|
| passen Knoten für Knoten | **jeder** Fugenknoten gehört beiden Bauteilen | Knoten verdoppeln, je Paar ein Spaltelement (und Kopplungen für die Fugenebene) |
| passen nicht | nur der gemeinsame Rand gehört beiden | den Rand trennen, die Fläche über ein **Kontaktpaar** (Knoten–Fläche, Abschnitt 4) |

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

### 4.1 Lager mit Ausfall, Schlupf, Reibung und Grenzkraft

Knoten-, Linien- und Flächenlager werden zunächst einheitlich auf
Knotenfreiheitsgrade umgelegt (`statik3d/supports.py`): Linienlager über die
Einflusslänge (halbe Nachbarabschnitte), Flächenlager über die Einflussfläche
der Knoten. Lineare Anteile (starr, Feder) gehen in die Sperrung bzw. in die
Steifigkeitsmatrix, nichtlineare Anteile in dieselbe Aktivmengen-Iteration wie
der Kontakt.

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

Jede **Linie** wird dabei genau einmal abgetastet — die Teilung gehört der
Linie, nicht der Fläche. Nur so passen die Netze benachbarter Flächen
aufeinander. Gegenüberliegende Seiten einer abgebildet vernetzten Fläche
müssen gleich viele Abschnitte haben; diese Bindung wird über eine
Vereinigungssuche (union-find) durch das ganze Bauteil weitergereicht. Krumme
Linien bekommen zusätzlich zur Längenteilung eine **Krümmungsteilung**: der
gesamte Richtungswechsel wird durch 30° geteilt, ein Kreis bekommt also
mindestens zwölf Abschnitte — ob er 10 mm oder 10 m Durchmesser hat.

**2 Dichtheit.** Die Dreiecke werden vernäht und geprüft: jede Kante muss in
genau zwei Dreiecken liegen. Das Volumen folgt aus dem Gaußschen Satz,

    V = 1/6 · Σ (a × b) · c   über alle Dreiecke,

und muss positiv sein — dann zeigt die Hülle nach außen. Ist sie nicht dicht,
wird **nicht** vernetzt: ein Netz aus einer undichten Hülle ist stillschweigend
falsch, und das ist schlimmer als kein Netz. Fehlt einer Fläche eine
Randstrecke, wird die *Linie* feiner geteilt und alles neu vernetzt.

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

**Gemeinsame Randflächen.** Zwei Körper, die *dieselbe* Fläche berandet,
bekommen dort dieselben Knoten und hängen zusammen. Geteilt wird ausdrücklich
über die Fläche, nicht über die Koordinate: zwei Flächen, die aufeinander
liegen, aber verschiedene Objekte sind, gehören zu einer Kontaktfuge und dürfen
**nicht** verschweißt werden.

**Splitter.** Das Kugel-Kanten-Kriterium erfasst jede schlechte Form außer
einer: vier fast in einer Ebene liegende Knoten können eine ganz gewöhnliche
Umkugel haben. Solche *Splitter* sind fast singulär und verderben die
Kondition der Steifigkeitsmatrix. Sie werden nachträglich herausgeglättet
(*smart Laplacian* mit Mustersuche): ein freier Knoten wandert versuchsweise in
den Schwerpunkt seiner Nachbarn und in zwölf Richtungen um seinen Platz herum,
und der beste Schritt wird nur behalten, wenn die **schlechteste** Güte seiner
Elemente danach höher ist und kein Element umklappt. Randknoten stehen fest —
sie sind die Geometrie, und so bleibt das Volumen unverändert. An einer Platte
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

## 7 Parallelisierung

* Elementschleifen (Assemblierung, Nachlauf) werden ab 1500 Elementen in
  Blöcke zerlegt und auf einen Prozess-Pool verteilt; das Modell wird je
  Prozess einmal übertragen.
* Grobkörnige Aufträge (Kombinationen bei Kontakt, Nachweise vieler Stäbe,
  Parameterstudien) laufen im lokalen Prozess-Pool oder auf der
  Rechnerfarm (siehe Rechnerfarm.md).
* Die Ergebnisse sind unabhängig von der Anzahl der Prozesse (getestet).

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
