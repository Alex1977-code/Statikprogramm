# Prüfmatrix: rechnet das Programm in jeder Elementstufe richtig?

Stand 25.09.2026, gerechnet auf `main` 562dc3a (Zweig `pruefmatrix-2509`), einkernig
(`MKL_NUM_THREADS=1`, Löser mit `workers=1`). Jede Zahl in diesem Dokument ist am 25.09.2026
gemessen. Die Tabellen am Ende schreibt das Skript selbst (zweimal gerechnet, Lauf 2 und 3 gleich bis auf die Zeiten):

```
python -m tests.pruefmatrix --md tabellen.md --json ergebnis.json   # Tabellen und Rohwerte
python -m tests.pruefmatrix --fall K1 P2          # nur einzelne Fälle
```

Das Skript `tests/pruefmatrix.py` misst nur. Es ändert nichts an Rechnung, Elementen, Kontakt,
Plastizität oder Vernetzer. Es steht nicht in `tests.run_all`. Der Gesamtlauf dauerte 4,6 min.

## Auftrag

Der Anwender schrieb am 25.09.2026: „hier soll die berechnung erst einmal korrekt laufen mit
kontakt linear nichtlinear plastizität etc“ und „kontakt und plastizität muss in allen stufen
funktionieren“. Die Stufen sind so festgelegt:

| Stufe | Tetraeder | Sechsflächner | Kantenlänge |
|---|---|---|---|
| Entwurf | tet4 | hex8 | h |
| Mittel | tet10 | hex20 | h |
| Fein | tet10 | hex20 | h/2 |

Jede Zelle aus Stufe und Fall rechnet beide Familien, also 2 Rechnungen je Zelle. Die Oberfläche
für die Stufen ist noch nicht in `main`. Deshalb stellt die Matrix die Stufe direkt ein, über
`model.netz.ordnung` und die Kantenlänge, mit Sweep aus.

* **Quaderförmige Körper** (Kragarm, Würfel, Druckstab) baut die Matrix als Geometrie: Linien,
  Flächen, Volumenkörper. Das Netz macht der Vernetzer des Programms. Tetraeder kommen aus
  `mesher3d.mesh_koerper_frei` mit h und Ordnung. Sechsflächner kommen aus dem abgebildeten
  Pfad `mesher.mesh_koerper`. Die Fugen entstehen wie im Programm, über eine
  Kontaktbedingung und `fugen.kontaktfuge_ausfuehren`.
* **Das gekrümmte Rohr** (L2, P2) kommt aus den Prüfkörper-Bausteinen (`tests/pruefkoerper.py`).
  Dieses Netz ist strukturiert, und die Kantenmitten liegen auf dem Bogen. hex20 entsteht aus
  demselben Gitter. Mit Sweep aus lehnt der abgebildete Pfad krumme Kanten ab.
* **Die Presspassung** (K3, KP2) baut die Matrix wie `tests/test_uebermass.py`: zwei Würfel mit
  eigenen Knoten und dazwischen ein Kontaktpaar. Die Würfel sind aus Kuhn-Tetraedern oder aus
  Sechsflächnern.

**Ausgewertet** wird die geglättete Knotenspannung aus `res.solid_knoten`. Das ist die Tabelle,
aus der der Nachweis über `res.solid_rand` liest. Die Randspannung ist „frei“, so wie es das
Programm vorgibt. Die Verschiebungen kommen aus `res.u`. Die Konvergenz lesen wir getrennt ab:
für den Kontakt aus `res.info["contact_converged"]`, für die Plastizität aus
`res.info["plastizitaet"]["konvergiert"]`. Die gestörten Pivots stehen in
`res.info["loeser_nachweis"]["gestoerte_pivots_summe"]`. Als Unbekannte zählen 3 × die Knoten
am Netz.

**Grenzen:** Spannungen dürfen 1 N/mm² abweichen, denn das ist das Ziel des Anwenders vom
22.09.2026. Verschiebungen dürfen 1 % abweichen. Kräfte dürfen 1 % abweichen, und bei den
Fugenfällen mit p = 100 N/mm² ist das dieselbe Grenze wie 1 N/mm² mittlere Fugenspannung. Die
Fälle K1, K3, P1, KP1 und KP2 haben einen **homogenen Zustand**, den jedes Element exakt
darstellt. Dort ist jede Überschreitung ein falsches Ergebnis und die Zelle wird rot. Bei den
anderen Fällen ist eine Überschreitung ein Diskretisierungsfehler und die Zelle wird gelb.

**Ergebnis je Zelle:**

* **grün**: konvergiert, und jeder Fehler liegt in seiner Grenze.
* **gelb**: konvergiert, aber ein Fehler ist größer.
* **rot**: nicht konvergiert, abgebrochen oder falsches Ergebnis. Rot ist auch ein Netz, das
  nicht knotenkonform ist (Orte mit zwei Knoten oder offene Innenseiten), wenn der Fehler
  zugleich über der Grenze liegt.
* **gesperrt**: Kontakt an quadratischen Seiten. Diese Rechnung sperrt `fugen.QuadratischeSeiten`,
  denn den Kontakt für tet10 und hex20 baut die Löser-Sitzung.

## Ergebnis in Kürze

* **Plastizität ohne Kontakt läuft in allen drei Stufen.** Der homogene Druckstab P1 ist in allen
  6 Rechnungen exakt: σ_v weicht 0,00 N/mm² ab, u 0,00 %. Das Hill-Rohr P2 konvergiert in jeder
  Rechnung, ist aber überall gelb. Fein kommt es mit tet10 auf +2,98 N/mm² und mit hex20 auf
  −5,00 N/mm². hex20 sperrt bei ν = 0,4999: In der Stufe Mittel ist u_r(b) um 22,48 % zu klein.
* **Kontakt läuft nur in der Stufe Entwurf.** hex8 ist in K1 bis K3 grün, tet4 in K2 und K3. K1
  mit tet4 ist rot, und das liegt am Vernetzer, nicht am Kontakt (Befund 2). In den Stufen Mittel
  und Fein sind alle 12 Kontaktzellen gesperrt, wie erwartet.
* **Kontakt mit Plastizität läuft in der Stufe Entwurf nur mit hex8 an der Fuge (KP1).** Bei der
  Presspassung, die bis ins Fließen geht (KP2), ist das Ergebnis exakt: σ_v weicht +0,00 N/mm² ab.
  Die Plastizität meldet trotzdem „nicht konvergiert“ (Befund 3). Mittel und Fein sind gesperrt.
* **Linear:** Der Kragarm aus einem Körper (L1) ist in jeder Stufe grün, nur tet4 nicht. Das
  Lamé-Rohr (L2) ist überall gelb. Fein bleiben 1,58 N/mm² mit tet10 und 1,12 N/mm² mit hex20
  an der gekrümmten Innenfläche. Der Kragarm aus **zwei** Körpern (L3) ist mit hex20 in Mittel
  und Fein rot: +610,29 und +514,79 N/mm², weil das Netz an der gemeinsamen Fläche aufreißt
  (Befund 1).

## Rote Zellen: Befund, Gegenprobe, Vermutung, Besitzer

### Befund 1: hex20 aus zwei Körpern reißt an der gemeinsamen Fläche auf (L3 Mittel und Fein)

**Befund.** Der Kragarm besteht aus zwei Körpern, die die Fläche x = L/2 teilen. Mit hex20
steht an der Oberkante σ_v +610,29 N/mm² zu hoch (Mittel) bzw. +514,79 N/mm² (Fein). Aus einem
Körper sind es +0,00 N/mm². Die Eckknoten der Fläche teilen sich beide Körper. Die Kantenmitten
legt aber jeder Körper selbst an: Es gibt 22 Orte mit zwei Knoten (Mittel) bzw. 76 (Fein). Damit
hängen die Körper nur an ihren Ecken zusammen. Mit hex8 teilen sie alle 15 Knoten der Fläche,
und das Ergebnis weicht +0,83 N/mm² ab.

**Gegenprobe.** Wir haben die 22 doppelten Knoten mit `mesher.merge_nodes` verschmolzen. Danach
weicht σ_v nur noch +0,01 N/mm² ab. Das Element rechnet also richtig. Dann derselbe Aufbau über
`mesher.modell_vernetzen`, also den Weg der Oberfläche, mit der Teilung 4 × 4 × 4: Mit Ordnung 2
gibt es 40 Orte mit zwei Knoten, mit Ordnung 1 keinen.

**Vermutung.** Der Kanten-Cache des abgebildeten Pfads (`mesher._hex_netz`) teilt die Mitten nur
auf den Randlinien. Die Gitterkanten im Inneren einer gemeinsamen Fläche bekommen je Körper eigene
Mitten.

**Besitzer: Vernetzer** (`mesher.py`, Fable). Betroffen ist jedes Modell mit mehreren
abgebildeten Körpern in der Stufe Mittel oder Fein. Das Programm meldet dabei nichts.

### Befund 2: Freier Vernetzer, zwei Körper mit gemeinsamer Fläche: das Netz ist nicht konform (K1, KP1, L3 Entwurf tet4)

**Befund.** Der freie Vernetzer vernetzt zwei Körper mit einer gemeinsamen Fläche. Dabei
triangulieren beide Körper die Fläche an einzelnen Stellen verschieden: 8 Elementseiten auf der
Fläche gehören nur einem Element. Die Folgen:

* K1 tet4: Die Fuge ist ohne Zug, der Spannungszustand homogen, und σ_v soll überall 100 N/mm²
  sein. Gemessen sind bis +10,32 N/mm² Abweichung, u_oben weicht +0,13 % ab.
* KP1 tet4: bis +6,02 N/mm².
* L3 tet4: −94,85 N/mm². Derselbe Kragarm aus einem Körper hat −71,70 N/mm².

Der Kontakt selbst ist dabei konvergiert. K2 rechnet auf demselben Netz grün.

**Gegenprobe.** Derselbe Würfelstapel, verschweißt und **ohne** Fuge, also ohne jeden Kontakt:
Die Elementspannungen weichen bis −24,15 N/mm² von 100 ab (tet4). Mit tet10 über
`modell_vernetzen` sind es +162,48 N/mm². Ein einziger Körper 1 × 1 × 2 m ist exakt, die
Abweichung ist 0,00 N/mm². Mit dem vorhandenen Baustein `tests/test_fugen.zwei_bloecke` gibt es
12 offene Innenseiten auf der Fuge. Der Test dort prüft die Stauchung mit 3 % Toleranz und
bemerkt das deshalb nicht.

Dabei fiel auf: Die Kantenlänge wirkt bei zwei Körpern nicht. h = 0,5 und h = 0,25 ergeben beide
1.912 Tetraeder, bei `zwei_bloecke` beide 1.904. Ein einzelner Körper ergibt 202 bzw. 1.868
Tetraeder.

**Vermutung.** Die gemeinsame Fläche wird nicht einmal vernetzt und dann von beiden Körpern
übernommen. Jeder Körper verändert sie noch einmal, etwa beim Nachvernetzen oder Glätten.

**Besitzer: Vernetzer** (`mesher3d.py`, Fable).

### Befund 3: Presspassung mit Fließen meldet „nicht konvergiert“ bei exaktem Ergebnis (KP2 Entwurf, tet4 und hex8)

**Befund.** Das Übermaß ist δ = 14,62 mm, gewählt so, dass σ = 300 N/mm² wird, bei fy 235 und
E_t/E 5 %. Das Ergebnis stimmt: σ_v weicht +0,00 N/mm² ab, die Auflagerkraft −0,00 %, ε_p,eq max
0,588 %. Die Plastizität meldet trotzdem „nicht konvergiert“. Das tut sie für tet4 und hex8, nach
3 × 60 Newton-Schritten (180 Faktorisierungen). Die Änderung sinkt in den drei Laststufen nur
auf 0,0972, 0,00351 und 0,00109. Dagegen bleibt u_max schon ab dem zweiten Newton-Schritt auf 12
Stellen gleich.

**Gegenprobe.** Wir haben dasselbe Modell mit anderen Einstellungen gerechnet. Mit Toleranz 0,001
statt 0,000001 konvergiert es nicht. Mit dem Verfahren Anfangsdehnung konvergiert es auch nicht,
und das Protokoll meldet „geschätzter Fehler inf“. Das Ergebnis ist dabei jedes Mal dasselbe. Die
Fuge unter äußerem Druck (KP1, hex8) konvergiert mit denselben Einstellungen.

**Vermutung.** Das Konvergenzmaß bezieht die Änderung der plastischen Knotenlasten auf die äußere
Last. In einem Lastfall ist das Übermaß manchmal die einzige Last, und es ist ein Anfangsspalt
und keine Knotenlast. Dann gibt es keine Bezugsgröße.

**Besitzer: Löser** (`plastizitaet.py`, Löser-Sitzung). Für den Anwender heißt das: Eine
Presspassung, die fließt, steht als „NICHT KONVERGIERT“ in der Zusammenfassung, obwohl sie
richtig gerechnet ist.

## Gelbe Zellen: was bekannt ist und was auffällt

* **tet4 ist zu steif.**
  * Am Kragarm L1: −71,70 N/mm² bei h = 50 mm, −33,87 bei 25 mm, −10,81 bei 12,5 mm
    (74.634 Unbekannte, 154,7 s). Innerhalb der Laufzeitgrenze erreicht tet4 1 N/mm² nicht.
  * Am Lamé-Rohr L2: −88,59, −47,40, −24,32 und −12,26 N/mm² bei h = 25, 12,5, 6,25 und
    3,125 mm. Der Fehler halbiert sich mit jeder Halbierung von h, erreicht die Grenze aber nicht.
* **tet4 im Hill-Rohr (P2) liegt auf der weichen Seite.** Er ist dort für keine Aussage brauchbar:
  u_r(b) +17,26 %, +19,95 %, +19,12 % und +12,32 %, σ_v(b) +99,64 bis +75,35 N/mm² bei h = 25
  bis 3,125 mm. Zur Gegenprobe haben wir dasselbe Rohr elastisch gerechnet, mit ν = 0,4999. Dort
  ist tet4 um −27,30 % zu steif (8 × 4) bzw. −25,52 % (16 × 8), das volumetrische Sperren. Dass
  das plastische Ergebnis auf die andere Seite fällt, ist nicht geklärt. **Element-Sitzung**,
  zur Kenntnis.
* **hex20 sperrt bei ν → 0,5** (P2 Mittel: σ_v(b) −45,79 N/mm², u_r(b) −22,48 %; Fein: −5,00
  N/mm², −2,38 %). In der Stufe Mittel ist hex20 damit schlechter als hex8 in der Stufe Entwurf
  (−6,87 N/mm², −1,54 %). Zur Gegenprobe haben wir dasselbe Rohr elastisch mit ν = 0,4999
  gerechnet. Die Abweichung von u_r(a) ist:

  | Element | 8 × 4 | 16 × 8 |
  |---|---|---|
  | hex20 | −8,98 % | −0,65 % |
  | hex8 | −1,09 % | −0,28 % |
  | tet10 | −0,20 % | −0,06 % |

  Vermutung: Der hex20 wird voll integriert und hat kein B-bar. Das haben wir nicht nachgelesen.
  **Besitzer: Element-Sitzung.** Für die Stufe Mittel wiegt das schwer, denn fließender Stahl
  ist volumentreu.
* **Lamé-Rohr L2, quadratische Elemente.** Fein bleiben an der gekrümmten Innenfläche 1,58 N/mm²
  (tet10) bzw. 1,12 N/mm² (hex20). u_r stimmt auf 0,00 %. Das ist Diskretisierung an einer
  gekrümmten Oberfläche mit geglätteter Knotenspannung. Der Fehler sinkt mit h: bei tet10 von
  −4,72 auf −1,58 N/mm², bei hex20 von −3,80 auf −1,12 N/mm².

## Gesperrte Zellen

Alle Kontaktzellen der Stufen Mittel und Fein sind gesperrt: K1, K2, K3, KP1 und KP2, je tet10
und hex20, zusammen 20 Rechnungen. Die Sperre greift für die Kontaktbedingung (Spaltelemente)
genauso wie für das Kontaktpaar (Übermaß). Sie greift auch für **hex20**. Dafür gibt es bisher
keinen eigenen Test (Bestandsaufnahme 25.09.2026), hier ist es gemessen. Sobald die
Löser-Sitzung den tet10-Kontakt liefert, rechnet `python -m tests.pruefmatrix --fall K1 K2 K3 KP1
KP2` diese Zellen nach.

## Weitere Beobachtungen (gemessen, ohne eigene Zelle)

* **Der abgebildete Pfad liest die Kantenlänge nicht.** Er teilt nach `Volumenkoerper.teilung`
  (Vorgabe 4 × 4 × 4). Am Quader 1,0 × 0,1 × 0,2 m ergeben h = 0,05 und h = 0,025 beide 64 hex8
  bzw. 64 hex20, und zwar über `modell_vernetzen`. Die Stufe Fein, also die halbe Kantenlänge,
  wirkt auf abgebildete Körper deshalb heute nicht. Die Matrix setzt die Teilung über
  `model.linienvorgabe`. **Besitzer: Vernetzer.**
* **Gestörte Pivots** meldet der Löser nur bei Rechnungen mit Kontakt, und dort waren es in jeder
  Rechnung 0. Ohne Kontakt (L1, L2, L3, P1, P2) hat PARDISO gelöst (`loesungen: pardiso`), aber
  `gestoerte_pivots_summe` ist None. In der Tabelle steht dann „–“. **Besitzer: Löser**, zur
  Kenntnis.
* **Singularitäten, Abbrüche:** keine. Keine Rechnung der Matrix brach ab.

## Wem was gehört

| Befund | Zellen | Besitzer |
|---|---|---|
| 1 hex20-Mitten an gemeinsamen Flächen nicht geteilt | L3 Mittel/Fein hex20 | Vernetzer (Fable) |
| 2 freier Vernetzer: gemeinsame Fläche nicht konform, h wirkt nicht | K1, KP1, L3 Entwurf tet4 | Vernetzer (Fable) |
| 3 Plastizität meldet „nicht konvergiert“ bei Übermaß als einziger Last | KP2 Entwurf tet4/hex8 | Löser (Löser-Sitzung) |
| hex20 sperrt bei ν → 0,5 (gelb) | P2 Mittel/Fein hex20 | Element-Sitzung |
| tet4 plastisch auf der weichen Seite (gelb) | P2 tet4 | Element-Sitzung |
| Kontakt an quadratischen Seiten (gesperrt) | alle Kontaktzellen Mittel/Fein | Löser-Sitzung (Auftrag) |
| abgebildeter Pfad ohne Kantenlänge | Stufe Fein bei Sechsflächnern | Vernetzer (Fable) |

Für die Statik3D-Sitzung selbst ist keine Zelle rot.

## Tabellen (Lauf vom 25.09.2026)

| Rechenart | Entwurf | Mittel | Fein |
|---|---|---|---|
| linear | 2 grün, 3 gelb, 1 **rot** | 3 grün, 2 gelb, 1 **rot** | 3 grün, 2 gelb, 1 **rot** |
| Kontakt | 5 grün, 1 **rot** | 6 gesperrt | 6 gesperrt |
| Plastizität | 2 grün, 2 gelb | 2 grün, 2 gelb | 2 grün, 2 gelb |
| Kontakt + Plastizität | 1 grün, 3 **rot** | 4 gesperrt | 4 gesperrt |

Je Fall und Stufe (Tetraeder · Sechsflächner):

| Fall | Rechenart | Entwurf | Mittel | Fein |
|---|---|---|---|---|
| L1 Kragarm aus einem Körper, σ_v an der Oberkante bei L/2 (Saint-Venant) | linear | tet4 gelb · hex8 grün | tet10 grün · hex20 grün | tet10 grün · hex20 grün |
| L2 Lamé-Rohr unter Innendruck, ebene Dehnung (ν = 0,3) | linear | tet4 gelb · hex8 gelb | tet10 gelb · hex20 gelb | tet10 gelb · hex20 gelb |
| L3 Kragarm aus zwei Körpern (gemeinsame Fläche bei L/2), σ_v wie L1 | linear | tet4 **rot** · hex8 grün | tet10 grün · hex20 **rot** | tet10 grün · hex20 **rot** |
| K1 Fuge ohne Zug, Druck geht durch (zwei Würfel, passende Netze) | Kontakt | tet4 **rot** · hex8 grün | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| K2 Fuge ohne Zug, Zug öffnet (zwei Würfel, oben in Federn) | Kontakt | tet4 grün · hex8 grün | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| K3 Presspassung, ebene Fuge (Kontaktpaar mit Übermaß) | Kontakt | tet4 grün · hex8 grün | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| P1 Druckstab einachsig, bilinear verfestigend (fy 235, E_t/E 5 %) | Plastizität | tet4 grün · hex8 grün | tet10 grün · hex20 grün | tet10 grün · hex20 grün |
| P2 Rohr unter Innendruck nach Hill, ideal plastisch (ν = 0,4999) | Plastizität | tet4 gelb · hex8 gelb | tet10 gelb · hex20 gelb | tet10 gelb · hex20 gelb |
| KP1 Fuge ohne Zug unter Druck, beide Würfel fließen (fy 235, E_t/E 5 %) | Kontakt + Plastizität | tet4 **rot** · hex8 grün | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| KP2 Presspassung, ebene Fuge, Übermaß bis ins Fließen (fy 235, E_t/E 5 %) | Kontakt + Plastizität | tet4 **rot** · hex8 **rot** | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |

### L1 Kragarm aus einem Körper, σ_v an der Oberkante bei L/2 (Saint-Venant)

Soll: σ_xx = M z/I = 355 N/mm² bei x = L/2 (Oberkante, Mitte der Breite); L 1,0 / B 0,1 / H 0,2 m; ausgewertet am Eckknoten der Oberkante, der (L/2, B/2, H) am nächsten liegt, gegen σ_xx an seinem x (Saint-Venant: an der Oberkante unabhängig von y). Grenze: 1 N/mm² (Ziel des Anwenders).

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,0500 | gelb | σ_v -71,70 N/mm² | – | – | – | 1.836 | 1,3 | Knoten 116 bei x = 0,5000, y = 0,0650 m (Abstand 15,0 mm) |
| Entwurf | hex8 | 0,0500 | grün | σ_v -0,00 N/mm² | – | – | – | 945 | 0,1 | Knoten 163 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Mittel | tet10 | 0,0500 | grün | σ_v +0,29 N/mm² | – | – | – | 13.242 | 1,8 | Knoten 116 bei x = 0,5000, y = 0,0650 m (Abstand 15,0 mm) |
| Mittel | hex20 | 0,0500 | grün | σ_v +0,00 N/mm² | – | – | – | 3.231 | 0,3 | Knoten 163 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Fein | tet10 | 0,0250 | grün | σ_v -0,08 N/mm² | – | – | – | 80.295 | 25,4 | Knoten 349 bei x = 0,4875, y = 0,0459 m (Abstand 13,2 mm) |
| Fein | hex20 | 0,0250 | grün | σ_v -0,00 N/mm² | – | – | – | 20.283 | 2,6 | Knoten 930 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Zusatz | tet4 | 0,0250 | gelb | σ_v -33,87 N/mm² | – | – | – | 10.572 | 9,3 | Knoten 349 bei x = 0,4875, y = 0,0459 m (Abstand 13,2 mm) |
| Zusatz | tet4 | 0,0125 | gelb | σ_v -10,81 N/mm² | – | – | – | 74.634 | 162,2 | Knoten 1176 bei x = 0,4938, y = 0,0513 m (Abstand 6,4 mm) |

### L2 Lamé-Rohr unter Innendruck, ebene Dehnung (ν = 0,3)

Soll: σ_v(a) = 355 N/mm² (p skaliert), u_r(a) nach Lamé; a 0,1 / b 0,2 m. Grenze: 1 N/mm² an jedem Eckknoten der Innenfläche, u_r 1 %.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,0250 | gelb | σ_v -88,59 N/mm²; u_r -3,32 % | – | – | – | 270 | 0,1 | Netz 8 × 4 (n_t × n_r) |
| Entwurf | hex8 | 0,0250 | gelb | σ_v -28,34 N/mm²; u_r -0,65 % | – | – | – | 270 | 0,0 | Netz 8 × 4 (n_t × n_r) |
| Mittel | tet10 | 0,0250 | gelb | σ_v -4,72 N/mm²; u_r +0,02 % | – | – | – | 1.377 | 0,1 | Netz 8 × 4 (n_t × n_r) |
| Mittel | hex20 | 0,0250 | gelb | σ_v -3,80 N/mm²; u_r -0,00 % | – | – | – | 861 | 0,1 | Netz 8 × 4 (n_t × n_r) |
| Fein | tet10 | 0,0125 | gelb | σ_v -1,58 N/mm²; u_r +0,00 % | – | – | – | 5.049 | 0,5 | Netz 16 × 8 (n_t × n_r) |
| Fein | hex20 | 0,0125 | gelb | σ_v -1,12 N/mm²; u_r -0,00 % | – | – | – | 3.057 | 0,3 | Netz 16 × 8 (n_t × n_r) |
| Zusatz | tet4 | 0,0125 | gelb | σ_v -47,40 N/mm²; u_r -0,89 % | – | – | – | 918 | 0,2 | Netz 16 × 8 (n_t × n_r) |
| Zusatz | tet4 | 0,0063 | gelb | σ_v -24,32 N/mm²; u_r -0,23 % | – | – | – | 3.366 | 0,6 | Netz 32 × 16 (n_t × n_r) |
| Zusatz | tet4 | 0,0031 | gelb | σ_v -12,26 N/mm²; u_r -0,06 % | – | – | – | 12.870 | 3,5 | Netz 64 × 32 (n_t × n_r) |

### L3 Kragarm aus zwei Körpern (gemeinsame Fläche bei L/2), σ_v wie L1

Soll: wie L1; die Körper teilen die Fläche x = L/2, der Nachweisknoten liegt auf ihr - misst, ob das Netz über die gemeinsame Fläche trägt. Grenze: 1 N/mm² (Ziel des Anwenders).

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,0500 | **rot** | σ_v -94,85 N/mm² | – | – | – | 1.623 | 4,2 | Netz nicht knotenkonform: 0 Orte mit zwei Knoten, 8 offene Innenseiten; σ_v -94,85 N/mm²; Knoten 50 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Entwurf | hex8 | 0,0500 | grün | σ_v +0,83 N/mm² | – | – | – | 945 | 0,1 | Knoten 165 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Mittel | tet10 | 0,0500 | grün | σ_v +0,75 N/mm² | – | – | – | 11.469 | 1,1 | Hinweis: Netz nicht knotenkonform: 2 Orte mit zwei Knoten, 8 offene Innenseiten; Knoten 50 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Mittel | hex20 | 0,0500 | **rot** | σ_v +610,29 N/mm² | – | – | – | 3.297 | 0,2 | Netz nicht knotenkonform: 22 Orte mit zwei Knoten, 0 offene Innenseiten; σ_v 610,29 N/mm²; Knoten 165 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Fein | tet10 | 0,0250 | grün | σ_v -0,07 N/mm² | – | – | – | 86.718 | 20,7 | Hinweis: Netz nicht knotenkonform: 2 Orte mit zwei Knoten, 8 offene Innenseiten; Knoten 132 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Fein | hex20 | 0,0250 | **rot** | σ_v +514,79 N/mm² | – | – | – | 20.511 | 2,2 | Netz nicht knotenkonform: 76 Orte mit zwei Knoten, 0 offene Innenseiten; σ_v 514,79 N/mm²; Knoten 932 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |

### K1 Fuge ohne Zug, Druck geht durch (zwei Würfel, passende Netze)

Soll: σ_zz = −p = −100 N/mm² überall, u_oben = −p L/E (L = 2 m); Auflager = p A. Grenze: 1 N/mm² an jedem Knoten, u 1 %, Auflager 1 %. Homogener Zustand: jedes Element stellt ihn exakt dar, jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | **rot** | σ_v +10,32 N/mm²; u_oben +0,13 %; Auflager -0,00 % | ja | – | 0 | 1.263 | 1,3 | Netz nicht knotenkonform: 0 Orte mit zwei Knoten, 8 offene Innenseiten; σ_v 10,32 N/mm²; 24 Spaltelemente |
| Entwurf | hex8 | 0,5000 | grün | σ_v +0,00 N/mm²; u_oben +0,00 %; Auflager -0,00 % | ja | – | 0 | 162 | 0,0 | 9 Spaltelemente |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | – | 0,3 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | – | 0,3 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |

### K2 Fuge ohne Zug, Zug öffnet (zwei Würfel, oben in Federn)

Soll: Fundament trägt 0 (Zug −100 N/mm² auf dem Deckel), die Last hängt ganz in den Federn. Grenze: Fundamentkraft ≤ 1 % der Last (entspricht 1 N/mm² mittlerer Fugenspannung). Homogener Zustand: jedes Element stellt ihn exakt dar, jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | grün | Fundament 0,00 %; Federn +0,00 % | ja | – | 0 | 1.263 | 0,7 | Hinweis: Netz nicht knotenkonform: 0 Orte mit zwei Knoten, 8 offene Innenseiten; 24 Spaltelemente |
| Entwurf | hex8 | 0,5000 | grün | Fundament 0,00 %; Federn -0,00 % | ja | – | 0 | 162 | 0,0 | 9 Spaltelemente |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | – | 0,3 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | – | 0,3 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |

### K3 Presspassung, ebene Fuge (Kontaktpaar mit Übermaß)

Soll: σ = δ E/(2 L) = 355 N/mm² überall (δ = 3,38 mm), Auflager σ A. Grenze: 1 N/mm² an jedem Knoten, Auflager 1 %. Homogener Zustand: jedes Element stellt ihn exakt dar, jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | grün | σ_v +0,01 N/mm²; Auflager -0,00 % | ja | – | 0 | 162 | 0,0 | 2³ Zellen je Würfel |
| Entwurf | hex8 | 0,5000 | grün | σ_v +0,01 N/mm²; Auflager -0,00 % | ja | – | 0 | 162 | 0,0 | 2³ Zellen je Würfel |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | 750 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | 486 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | 4.374 | 0,1 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | 2.550 | 0,1 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |

### P1 Druckstab einachsig, bilinear verfestigend (fy 235, E_t/E 5 %)

Soll: p = 300 N/mm²: σ_v = p überall, u_oben = L (p/E + (p − fy)/H), L = 2 m. Grenze: 1 N/mm² an jedem Knoten, u 1 %. Homogener Zustand: jedes Element stellt ihn exakt dar, jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | grün | σ_v +0,00 N/mm²; u_oben +0,00 % | – | ja | 0 | 183 | 0,1 |  |
| Entwurf | hex8 | 0,5000 | grün | σ_v +0,00 N/mm²; u_oben -0,00 % | – | ja | 0 | 135 | 0,1 |  |
| Mittel | tet10 | 0,5000 | grün | σ_v +0,00 N/mm²; u_oben +0,00 % | – | ja | 0 | 1.083 | 0,3 |  |
| Mittel | hex20 | 0,5000 | grün | σ_v +0,00 N/mm²; u_oben +0,00 % | – | ja | 0 | 423 | 0,3 |  |
| Fein | tet10 | 0,2500 | grün | σ_v +0,00 N/mm²; u_oben +0,00 % | – | ja | 0 | 8.409 | 3,0 |  |
| Fein | hex20 | 0,2500 | grün | σ_v +0,00 N/mm²; u_oben +0,00 % | – | ja | 0 | 2.355 | 3,7 |  |

### P2 Rohr unter Innendruck nach Hill, ideal plastisch (ν = 0,4999)

Soll: c/a = 1,5 bei p = 255,88 N/mm²: σ_v(b) = fy c²/b² = 199,69 N/mm², u_r(b) = k c²/(2 G b); fy 355. Grenze: 1 N/mm² an jedem Eckknoten der Außenfläche, u_r 1 %.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,0250 | gelb | σ_v(b) +99,64 N/mm²; u_r(b) +17,26 % | – | ja | – | 270 | 0,3 | Netz 8 × 4, anfangsdehnung |
| Entwurf | hex8 | 0,0250 | gelb | σ_v(b) -6,87 N/mm²; u_r(b) -1,54 % | – | ja | – | 270 | 0,2 | Netz 8 × 4, anfangsdehnung |
| Mittel | tet10 | 0,0250 | gelb | σ_v(b) +7,55 N/mm²; u_r(b) -0,33 % | – | ja | – | 1.377 | 0,5 | Netz 8 × 4, anfangsdehnung |
| Mittel | hex20 | 0,0250 | gelb | σ_v(b) -45,79 N/mm²; u_r(b) -22,48 % | – | ja | – | 861 | 0,2 | Netz 8 × 4, anfangsdehnung |
| Fein | tet10 | 0,0125 | gelb | σ_v(b) +2,98 N/mm²; u_r(b) -0,08 % | – | ja | – | 5.049 | 2,9 | Netz 16 × 8, anfangsdehnung |
| Fein | hex20 | 0,0125 | gelb | σ_v(b) -5,00 N/mm²; u_r(b) -2,38 % | – | ja | – | 3.057 | 0,6 | Netz 16 × 8, anfangsdehnung |
| Zusatz | tet4 | 0,0125 | gelb | σ_v(b) +98,70 N/mm²; u_r(b) +19,95 % | – | ja | – | 918 | 1,0 | Netz 16 × 8, anfangsdehnung |
| Zusatz | tet4 | 0,0063 | gelb | σ_v(b) +93,38 N/mm²; u_r(b) +19,12 % | – | ja | – | 3.366 | 3,1 | Netz 32 × 16, anfangsdehnung |
| Zusatz | tet4 | 0,0031 | gelb | σ_v(b) +75,35 N/mm²; u_r(b) +12,32 % | – | ja | – | 12.870 | 7,9 | Netz 64 × 32, anfangsdehnung |

### KP1 Fuge ohne Zug unter Druck, beide Würfel fließen (fy 235, E_t/E 5 %)

Soll: p = 300 N/mm²: σ_v = p überall, u_oben = L (p/E + (p − fy)/H), L = 2 m. Grenze: 1 N/mm² an jedem Knoten, u 1 %, Auflager 1 %. Homogener Zustand: jedes Element stellt ihn exakt dar, jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | **rot** | σ_v +6,02 N/mm²; u_oben +0,14 %; Auflager -0,00 % | ja | ja | 0 | 1.263 | 1,1 | Netz nicht knotenkonform: 0 Orte mit zwei Knoten, 8 offene Innenseiten; σ_v 6,02 N/mm²; 24 Spaltelemente |
| Entwurf | hex8 | 0,5000 | grün | σ_v +0,00 N/mm²; u_oben +0,00 %; Auflager -0,00 % | ja | ja | 0 | 162 | 0,1 | 9 Spaltelemente |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | – | 1,6 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | – | 0,6 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |

### KP2 Presspassung, ebene Fuge, Übermaß bis ins Fließen (fy 235, E_t/E 5 %)

Soll: δ = 2 L ε(300 N/mm²) = 14,62 mm (ε_p 0,588 %): σ_v = 300 N/mm² überall, Auflager σ A. Grenze: 1 N/mm² an jedem Knoten, Auflager 1 %. Homogener Zustand: jedes Element stellt ihn exakt dar, jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | **rot** | σ_v +0,00 N/mm²; Auflager -0,00 % | ja | **nein** | 0 | 162 | 0,9 | Plastizität konvergiert = False; 2³ Zellen je Würfel |
| Entwurf | hex8 | 0,5000 | **rot** | σ_v +0,00 N/mm²; Auflager -0,00 % | ja | **nein** | 0 | 162 | 3,5 | Plastizität konvergiert = False; 2³ Zellen je Würfel |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | 750 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | 486 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | 4.374 | 0,2 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | 2.550 | 0,2 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |

Laufzeit gesamt 4,6 min (einkernig, 25.09.2026).
