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

## 2 Lasten

* Knotenlasten, Momente, vorgegebene Verschiebungen, Federlager.
* Streckenlasten auf Stäben, global oder lokal, konstant oder linear
  veränderlich (Trapez). Die äquivalenten Knotenlasten folgen aus den
  Volleinspannwerten; die Schnittgrößen an Zwischenstellen werden aus den
  Stabendkräften und der Streckenlast durch Gleichgewicht am Teilstab
  berechnet (Momentenverlauf quadratisch bzw. kubisch).
* Flächenlasten auf Schalen (normal oder in vorgegebener globaler Richtung)
  und auf Volumenoberflächen (Flächennummer).
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

### 5.2 Querschnittsklassifizierung (5.5, Tabelle 5.2)

* I-Profile: Flansch als einseitig gestütztes Teil c = (b − tw − 2r)/2,
  Steg als innenliegendes Teil c = h − 2tf − 2r; Grenzen 9ε/10ε/14ε bzw.
  für den Steg abhängig von α (plastischer Druckzonenanteil) und ψ
  (elastisches Spannungsverhältnis) mit ε = √(235/fy).
* Hohlprofile RHS: alle Teile innenliegend, c = b − 2t − 2r_i.
* CHS: d/t ≤ 50ε², 70ε², 90ε².
* Klasse 4: wirksame Breiten nach DIN EN 1993-1-5, 4.4 (ρ für innen-
  liegende und einseitig gestützte Teile), wirksame Fläche A_eff und
  wirksames Widerstandsmoment W_eff aus der Rechteckzerlegung des
  Querschnitts (Schwerachsenverschiebung bei Biegung berücksichtigt).

### 5.3 Querschnittsnachweise (6.2)

* Normalkraft 6.2.3/6.2.4, Biegung 6.2.5 (W_pl, W_el, W_eff je Klasse),
  Querkraft 6.2.6 mit Schubflächen (I: A − 2btf + (tw + 2r)tf; RHS:
  A·h/(b+h); CHS: 2A/π), Hinweis auf Schubbeulen bei hw/tw > 72ε/η.
* Torsion 6.2.7: Saint-Venant-Schubspannung (Wölbkrafttorsion vernach-
  lässigt), Abminderung der Querkrafttragfähigkeit.
* Biegung + Querkraft 6.2.8: ρ = (2V/Vpl − 1)² bei V > 0,5 Vpl.
* Biegung + Normalkraft 6.2.9: Klasse 1/2 mit M_N,Rd (I: Gl. 6.36–6.38,
  RHS: 6.39/6.40, CHS: M_N = M_pl (1 − n^1,7)), biaxial Gl. 6.41; Klasse
  3/4 linear elastisch (6.2.9.2/6.2.9.3).
* Vergleichsspannung 6.2.1(5) als zusätzlicher elastischer Nachweis bei
  Klasse 3/4 und bei Torsion.

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

Die Geometrievorschläge (Blechdicken, Schraubenbild, Nahtdicken) sind
**Vorschläge, keine Nachweise**: sie folgen den Konstruktionsregeln
(Rand- und Lochabstände Tab. 3.3, Nahtdicken 4.5.1) und werden so lange
nachgebessert, bis die Nachweise für die eingegebenen Schnittgrößen erfüllt
sind. Maßgebend ist immer die anschließende Rechnung über alle Kombinationen.

## 6 Modalanalyse und Knicken

* Eigenschwingungen: verallgemeinertes Eigenwertproblem (K − ω² M) φ = 0
  mit konsistenter Balkenmassenmatrix bzw. konzentrierten Massen (Schalen,
  Volumen), Shift-Invert-Lanczos (ARPACK).
* Lineares Knicken: (K + λ K_g) φ = 0 mit der geometrischen Steifigkeit der
  Stäbe (Przemieniecki) aus dem Grundzustand eines Lastfalls oder einer
  Kombination. Der Knicklastfaktor λ multipliziert die Lasten des
  Grundzustands.

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
* Schalen: ebene Elemente; Beulnachweise von Blechfeldern (EN 1993-1-5)
  sind nicht enthalten (Hinweis im Nachweis).
* Anschlüsse: nachgewiesen werden die im Modell angelegten Anschlüsse der drei
  Vorlagen (Kopfplatte, Laschenstoß, Knotenblech) aus den Stabendschnitt-
  größen. Die Nachgiebigkeit des Anschlusses geht **nicht** in die Rechnung
  ein (starre oder gelenkige Modellierung ist über die Stabendgelenke zu
  wählen); Momenten-Rotations-Kennlinien nach 6.3 sind nicht enthalten.
* Nachweise gelten für die implementierten Querschnittstypen (I, RHS, CHS,
  Rechteck, Kreis); bei freien Querschnitten wird elastisch (Klasse 3)
  gerechnet.
* Das Programm ist verifiziert, aber nicht bauaufsichtlich zugelassen. Die
  Verantwortung für die Anwendung und die Prüfung der Ergebnisse liegt beim
  Anwender.

## 9 Verifikation

| Test | Umfang |
|---|---|
| `tests/test_verification.py` | 26 Benchmarks Stab/Schale/Volumen (analytisch, Patch-Tests) |
| `tests/test_supports.py` | Lager mit Ausfall bei Zug/Druck, Schlupf, Reibung, Grenzkraft; Linien- und Flächenlager; Federgelenke gegen Handrechnungen |
| `tests/test_sections.py` | Profildatenbank nach Land gegen Katalogwerte, Hauptachsen der Winkel, zusammengesetzte Querschnitte |
| `tests/test_rfem.py` | native RFEM/RSTAB-Dateien (SQLite, ZIP, unbekanntes Binärformat) und erweiterter Tabellenimport |
| `tests/test_solver_ext.py` | Gelenke, Trapezlasten, Temperatur, Zwischenstellen, Superposition, Umhüllende, Kombinationsgenerator, einseitige Lager, Spaltelement, Flächenkontakt mit Reibung, parallele Assemblierung, Rechnerfarm |
| `tests/test_ec3.py` | Klassifizierung, Querschnittsnachweise, Knicken (χ), M_cr, χ_LT, C1/C_m, Interaktion, Wöhlerlinien, Nachweisführung |
| `tests/test_importers.py` | Import DXF, IFC, SAF, RFEM-Tabellen, INP, BDF |
| `tests/test_report.py` | Berichtserzeugung |
