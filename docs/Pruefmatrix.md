# Prüfmatrix: rechnet das Programm in jeder Elementstufe richtig?

Stand 25.09.2026, gerechnet auf `main` 562dc3a (Zweig `pruefmatrix-2509`), einkernig
(`MKL_NUM_THREADS=1`, Löser mit `workers=1`). Jede Zahl in diesem Dokument ist am 25.09.2026
gemessen. Die Tabellen am Ende schreibt das Skript selbst. Es lief mit dem endgültigen Stand
zweimal, und beide Läufe gaben dieselben Zahlen; nur die Zeiten wichen ab (Einzelheiten unter
„Wiederholung“):

```
python -m tests.pruefmatrix --md tabellen.md --json ergebnis.json   # Tabellen und Rohwerte
python -m tests.pruefmatrix --fall K1 P2          # nur einzelne Fälle
python -m tests.pruefmatrix --gegenprobe          # Kontrollläufe (ohne das Geprüfte / mit Kur)
```

Das Skript `tests/pruefmatrix.py` misst nur. Es ändert nichts an Rechnung, Elementen, Kontakt,
Plastizität oder Vernetzer. Die Kuren unter „Kontrollläufe“ sind Monkeypatches im Skript selbst,
nach jedem Lauf ist alles wie vorher. Das Skript steht nicht in `tests.run_all`. Der Gesamtlauf
dauert 5 bis 7 min, die Kontrollläufe dauern 0,1 min.

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
* **Die Kontaktpaare** (K3 bis K7, KP2) baut die Matrix wie `tests/test_uebermass.py`: Klötze mit
  eigenen Knoten, strukturiert aus Kuhn-Tetraedern oder aus Sechsflächnern, dazwischen ein
  `ContactPair` (oben die Slave-Knoten, unten die Eckseiten als Master-Facetten).

## Auswertung und Regeln

**Spannung.** Ausgewertet wird die geglättete Knotenspannung aus `res.solid_knoten`. Das ist die
Tabelle, aus der der Nachweis über `Results.solid_rand` liest. Ein Knoten hat dort eine Zeile je
Körper und Werkstoff. Die Matrix wertet **jede Zeile** aus und nimmt den größten Fehler, so wie
`solid_rand` die maßgebende Zeile nimmt. Bis zum Stand 0b17b12 nahm sie das Mittel der Zeilen.
Das konnte einen falschen Körper hinter einem richtigen verstecken (gemessen unter
„Kontrollläufe“). In den exakten Fällen prüft sie zusätzlich die Elementwerte
`res.solid_res` jedes Volumenelements.

**Verschiebung, Kräfte, Konvergenz.** Die Verschiebungen kommen aus `res.u` (nn × 6, die ersten
drei Spalten). Die Kräfte kommen aus `res.reactions` und `res.contact_forces`. Die Konvergenz
lesen wir getrennt ab: für den Kontakt aus `res.info["contact_converged"]`, für die Plastizität
aus `res.info["plastizitaet"]["konvergiert"]`. Die gestörten Pivots stehen in
`res.info["loeser_nachweis"]["gestoerte_pivots_summe"]`. Ob die Reibung Phase 2 durchlaufen hat,
steht im Laufbuch `res.info["laeufe"][..]["runden"]`, erstes Feld je Schritt. Als Unbekannte
zählen 3 × die Knoten am Netz.

**Grenzen:** Spannungen dürfen 1 N/mm² abweichen, denn das ist das Ziel des Anwenders vom
22.09.2026. Verschiebungen und Kräfte dürfen 1 % abweichen. **Exakt** sind Fälle, deren Soll
jedes Element darstellt, also ein homogener Zustand (K1, K2, K3, K6, K7, P1, KP1, KP2), oder
deren Kräfte allein aus Gleichgewicht und Reibgesetz folgen (K4, K5). Dort ist jede
Überschreitung ein falsches Ergebnis. Bei den anderen Fällen ist sie Diskretisierung.

**Ergebnis je Zelle:**

* **grün**: konvergiert, jeder Fehler liegt in seiner Grenze, und das Netz ist knotenkonform.
* **gelb**: konvergiert, aber ein Fehler ist größer, und der Fall ist nicht exakt. Gelb ist auch
  ein Netz, das **nicht knotenkonform** ist (Orte mit zwei Knoten oder offene Innenseiten),
  wenn jeder Fehler in der Grenze liegt. Es steht dann „Netzfehler“ in der Bemerkung. Ein
  solches Netz ist nie grün, denn der Wert kann zufällig stimmen, weil die Messstelle nicht am
  Riss liegt.
* **rot**: nicht konvergiert, abgebrochen, ein falsches Ergebnis, ein Netzfehler zusammen mit
  einem Fehler über der Grenze, eine freie Bewegung in `res.singular` oder gestörte Pivots > 0.
  Eine Ausnahme bei `res.singular`: Ein Eintrag „hebt ab“ mit Kraft 0 und Moment 0 zählt nicht.
  Damit meldet das Programm einen Körper, der nur durch Druck in der Fuge liegt. Das sind in K4
  die beiden Klötze auf der Unterlage, und es geht dabei keine Last ins Nichts. Die Bemerkung
  nennt solche Einträge.
* **gesperrt**: Kontakt an quadratischen Seiten. Diese Rechnung sperrt `fugen.QuadratischeSeiten`,
  denn den Kontakt für tet10 und hex20 baut die Löser-Sitzung.

## Ergebnis in Kürze

* **Plastizität ohne Kontakt läuft in allen drei Stufen.** Der homogene Druckstab P1 ist in allen
  6 Rechnungen exakt, an den Knoten wie an den Elementen: 0,00 N/mm², u 0,00 %. Das Hill-Rohr P2
  konvergiert in jeder Rechnung, ist aber überall gelb (unverändert, siehe „Gelbe Zellen“).
* **Kontakt ist nur in der Stufe Entwurf rechenbar, und dort ist er nicht überall richtig.**
  Richtig rechnen die Fugen mit passenden Netzen, die Presspassung und der **Anfangsspalt**
  (K7): u_oben 1,7826 mm und F_c 82.174 kN auf 0,00 %, über die Geometrie und über
  `ContactPair.spiel` gleich. Falsch rechnen:
  * **Reibung, Bauteil gleitet gegen eine Feder** (K5): Die Feder bekommt nur 14 % (hex8) bzw.
    9 % (tet4) ihrer Kraft. Den Rest trägt die Reststeifigkeit der gleitenden Knoten, und die
    erscheint in keiner Kontaktkraft (Befund 4).
  * **Reibung, ein Klotz haftet und einer gleitet** (K4): Phase 2 läuft, Haften ist exakt. Die
    Feder am gleitenden Klotz weicht −3,45 % (hex8) bzw. −10,16 % (tet4) ab, und die
    Reibkraft hat quer zur Last eine Komponente von 2,51 % bzw. 3,60 % von μN (Befund 5).
  * **Ungleiche Netze an der Fuge** (K6): Bei einem homogenen Druck von 100 N/mm² weicht σ_v mit
    hex8 um +74,16 N/mm² ab, mit tet4 um −13,56 N/mm² (Befund 6).
  * Mit tet4 aus dem freien Vernetzer sind K1 und KP1 rot und K2 gelb, weil das Netz an der
    gemeinsamen Fläche nicht konform ist (Befund 2).

  In den Stufen Mittel und Fein sind alle 28 Kontaktrechnungen gesperrt.
* **Kontakt mit Plastizität:** Die Fuge unter Druck (KP1) mit hex8 ist grün. Die Presspassung bis
  ins Fließen (KP2) rechnet exakt, meldet aber „nicht konvergiert“ (Befund 3). Mittel und Fein
  sind gesperrt.
* **Linear:** Der Kragarm aus einem Körper (L1) ist in jeder Stufe grün, nur tet4 nicht. Das
  Lamé-Rohr (L2) ist überall gelb. Den Kragarm aus **zwei** Körpern (L3) liest die Matrix jetzt
  je Körperzeile. Mit hex20 steht er in Mittel und Fein bei +765,60 bzw. +654,32 N/mm² (Befund
  1), mit hex8 bei +12,33 N/mm² (gelb, siehe „Gelbe Zellen“).

## Korrekturen gegenüber 0b17b12 (erste Gegenprüfung)

* Die Knotenspannung wird je Körperzeile ausgewertet statt gemittelt. Geändert haben sich damit:
  * L3 hex8 Entwurf: von +0,83 auf +12,33 N/mm², also von grün auf gelb.
  * L3 tet10 Mittel: von +0,75 auf +1,65 N/mm², also rot.
  * L3 hex20: von +610,29 auf +765,60 N/mm² (Mittel) und von +514,79 auf +654,32 N/mm² (Fein).
  * L3 tet4: von −94,85 auf −101,95 N/mm².

  Alle anderen Fälle haben je Knoten nur eine Zeile und sind gleich geblieben.
* Die exakten Fälle prüfen auch die Elementwerte. Dadurch stehen neu da: K1 tet4 −25,41 N/mm²
  und KP1 tet4 −10,60 N/mm² an einem Element. Beide Zellen waren schon vorher rot.
* Ein nicht knotenkonformes Netz ist nie mehr grün. Das betrifft L3 tet10 Fein und K2 tet4,
  die jetzt gelb sind („Netzfehler“), und L3 tet10 Mittel, das jetzt rot ist.
* Freie Bewegungen und gestörte Pivots machen eine Zelle rot. In der ganzen Matrix sind die
  gestörten Pivots in jeder Rechnung 0 oder nicht gemeldet. Freie Bewegungen gibt es keine,
  außer den „hebt ab“-Einträgen mit Kraft 0 in K4.
* **K2, eigener Fehler der Matrix:** Die Federn am Deckel waren gleich je Knoten verteilt, die
  Last aber nach Flächenanteil. Der Deckel verzog sich, und der obere Würfel trug bis
  102,29 N/mm². Den homogenen Zustand, den der Fall versprach, gab es also nicht. Das hat erst
  die neue Elementprüfung gezeigt. Die Federn sind jetzt nach Flächenanteil verteilt, und die
  Elemente zeigen 0,00 N/mm².

## Rote Zellen: Befund, Gegenprobe, Vermutung, Besitzer

### Befund 1: hex20 aus zwei Körpern reißt an der gemeinsamen Fläche auf (L3 Mittel und Fein)

**Befund.** Der Kragarm besteht aus zwei Körpern, die die Fläche x = L/2 teilen. Mit hex20
steht an der Oberkante σ_v +765,60 N/mm² zu hoch (Mittel) bzw. +654,32 N/mm² (Fein), jeweils
in der schlechteren Körperzeile. Aus einem Körper sind es +0,00 N/mm². Die Eckknoten der
Fläche teilen sich beide Körper. Die Kantenmitten legt aber jeder Körper selbst an: Es gibt 22
Orte mit zwei Knoten (Mittel) bzw. 76 (Fein). Damit hängen die Körper nur an ihren Ecken
zusammen.

**Gegenprobe (0b17b12).** Wir haben die 22 doppelten Knoten mit `mesher.merge_nodes`
verschmolzen. Danach wich σ_v nur noch +0,01 N/mm² ab (damals als Mittel der Zeilen gemessen).
Das Element rechnet also richtig. Über `mesher.modell_vernetzen`, also den Weg der Oberfläche,
mit der Teilung 4 × 4 × 4 gibt es mit Ordnung 2 40 Orte mit zwei Knoten, mit Ordnung 1 keinen.

**Vermutung.** Der Kanten-Cache des abgebildeten Pfads (`mesher._hex_netz`) teilt die Mitten nur
auf den Randlinien.

**Besitzer: Vernetzer** (`mesher.py`, Fable).

### Befund 2: Freier Vernetzer, zwei Körper mit gemeinsamer Fläche: das Netz ist nicht konform (K1, KP1, K2, L3 mit Tetraedern)

**Befund.** Der freie Vernetzer vernetzt zwei Körper mit einer gemeinsamen Fläche. Dabei
triangulieren beide Körper die Fläche an einzelnen Stellen verschieden: 8 Elementseiten auf der
Fläche gehören nur einem Element. Die Folgen:

* K1 tet4: σ_v soll überall 100 N/mm² sein. An den Knoten weicht er bis +10,32 N/mm² ab, an einem
  Element bis −25,41 N/mm².
* KP1 tet4: bis +6,02 N/mm² an den Knoten und −10,60 N/mm² am Element.
* L3 tet4: −101,95 N/mm². Derselbe Kragarm aus einem Körper hat −71,70 N/mm².
* L3 tet10 Mittel: +1,65 N/mm² bei 2 Orten mit zwei Knoten und 8 offenen Innenseiten.
* K2 tet4 und L3 tet10 Fein: Die Werte liegen in der Grenze, aber das Netz ist nicht konform
  (gelb).

**Gegenprobe (0b17b12).** Wir haben denselben Würfelstapel verschweißt und **ohne** Fuge
gerechnet. Die Elementspannungen wichen bis −24,15 N/mm² ab (tet4). Ein einziger Körper
1 × 1 × 2 m ist exakt. Außerdem wirkt die Kantenlänge bei zwei Körpern nicht. Die Zusatzreihe
von K2 zeigt das: Mit h = 0,5 und 0,25 m sind es gleich viele Unbekannte (1.263) und 8 offene
Innenseiten, mit h = 0,125 m sind es 20. Erst bei h = 0,0625 m ist das Netz konform (59.652
Unbekannte).

**Besitzer: Vernetzer** (`mesher3d.py`, Fable).

### Befund 3: Presspassung mit Fließen meldet „nicht konvergiert“ bei exaktem Ergebnis (KP2 Entwurf, tet4 und hex8)

Unverändert gegenüber 0b17b12. Das Ergebnis stimmt jetzt auch an jedem Element: σ_v −0,00
N/mm². Die Plastizität meldet trotzdem „nicht konvergiert“. Vermutung: Das Konvergenzmaß bezieht
sich auf die äußere Last, und die gibt es hier nicht, weil das Übermaß die einzige Last ist.
**Besitzer: Löser** (`plastizitaet.py`).

### Befund 4: Gleitet ein Bauteil ganz, trägt die Reststeifigkeit statt der Feder (K5 Entwurf, tet4 und hex8)

**Befund.** Ein Klotz 1 × 1 × 0,25 m liegt mit p = 100 N/mm² (N = 100.000 kN) und μ = 0,3 auf
einer Unterlage. Er wird mit H = 1,5 μN = 45.000 kN geschoben und oben von Federn gehalten,
k = 1.000 kN/mm in x und y. Das Soll ergibt sich aus Gleichgewicht und Reibgesetz: Reibkraft
μN = 30.000 kN, Federkraft H − μN = 15.000 kN. Alle 9 Fugenknoten gleiten. Gemessen:

| | Reibkraft x | Federkraft x | Rest (H − Reibung − Feder) |
|---|---|---|---|
| hex8 | 29.970,6 kN (−0,10 %) | 2.086,8 kN (−86,09 %) | 12.942,6 kN |
| tet4 | 29.816,8 kN (−0,61 %) | 1.399,4 kN (−90,67 %) | 13.783,8 kN |

Der Rest steht in keiner Kontaktkraft und in keinem Lager. Er geht über die Reststeifigkeit
1e-3 k_t der gleitenden Knoten ab. Die gibt `_k_res` jeder Gruppe, deren aktive Reibknoten alle
gleiten (`_full_slip_groups`), mit der Begründung „nur sie hält das Bauteil“. Hier hält aber die
Feder das Bauteil. Das Protokoll meldet dazu „alle aktiven Kontaktknoten gleiten - Reibung
reicht nicht für das Gleichgewicht (Bauteil rutscht …)“, und das ist hier falsch.

**Gegenprobe (Kur als Monkeypatch).** `_full_slip_groups` gibt keine Gruppe als ganz rutschend
zurück, und `SLIP_STIFFNESS_FINE` steht auf 1e-12. Damit wird hex8 grün: Reibung −0,10 %,
Feder +0,21 %. tet4 ist dann Reibung −0,74 %, quer +0,83 %, Feder +1,47 %, also noch rot
(Rest wie Befund 5). Die Ursache für die 86 bis 91 % ist damit belegt.

**Besitzer: Löser** (`contact.py`, Löser-Sitzung). Für den Anwender heißt das: Ein Bauteil, das
auf einer Reibfuge rutscht und von etwas anderem gehalten wird (Feder, Anschlag, Schraube),
bekommt in dieses Andere nur einen Bruchteil der Kraft. Das Ergebnis liegt auf der unsicheren
Seite.

### Befund 5: Haften und Gleiten in einem Kontaktpaar: Reststeifigkeit und festgehaltene Gleitrichtung (K4 Entwurf, tet4 und hex8)

**Befund.** Auf einer Unterlage 2 × 1 × 1 m liegen zwei Klötze wie in K4 beschrieben, in
**einem** Kontaktpaar. Klotz A wird mit 0,5 μN geschoben und hat sonst keinen Halt. Klotz B wird
mit 1,5 μN geschoben und hat Federn wie in K5. Phase 2 der Reibung läuft (hex8 6 Schritte, tet4
5 Schritte). A haftet an allen 9 Knoten, B gleitet an allen 9 Knoten.

* **Klotz A ist exakt:** Die Reibkraft ist H_A (−0,00 %), und der Fugenschlupf ist 0,00 % der
  Deckelverschiebung.
* **Klotz B ist falsch:** Die Feder weicht −3,45 % (hex8) bzw. −10,16 % (tet4) ab. Die Reibkraft
  quer zur Last ist −2,51 % bzw. −3,60 % von μN, obwohl das Modell in y symmetrisch ist und die
  Summe dort null sein muss.

**Gegenprobe (Kuren als Monkeypatch).**

* Nur `SLIP_STIFFNESS_FINE` = 1e-12: Die Summe aus Reibung und Feder in x geht auf H_B (hex8
  Feder +1,17 %, tet4 +0,88 %). Das fehlende Stück trug also die Reststeifigkeit 1e-8 k_t der
  gleitenden Knoten. Bei rund 14,5 mm Gleitweg sind das 692 kN (hex8), also 2,3 % von μN, und
  bei tet4 1.658 kN. Die Querkomponente bleibt: −2,49 % bzw. −3,57 %.
* Dazu `GLEIT_ANTEIL` = 1 (alle Kegelverstöße einer Runde gleiten zugleich statt der Reihe
  nach): hex8 wird grün (Feder +0,26 %, quer −0,00 %). tet4 bleibt rot (Feder +1,07 %, quer
  +0,41 %).

Bei hex8 sind damit zwei Ursachen belegt. Erstens: Die Reststeifigkeit trägt proportional zum
Gleitweg. Zweitens: Phase 2 stellt die Knoten der Reihe nach um und hält die Gleitrichtung
dabei fest. Dabei entsteht ein Zwischenzustand, der in y nicht symmetrisch ist, und seine
Richtungen bleiben stehen. Am Knoten (2, 0, 1) hat die Reibkraft zum Beispiel −846 kN quer, am
Spiegelknoten (2, 1, 1) +287 kN. Was bei tet4 übrig bleibt, ist nicht gemessen. Vermutung: auch
dort die festgehaltene Gleitrichtung, weil sie beim Übergang ins Gleiten aus einem kleinen,
noch elastisch geprägten Schlupf gebildet wird.

**Besitzer: Löser** (`contact.py`, Löser-Sitzung).

### Befund 6: Kontaktpaar mit ungleichen Netzen gibt einen gleichmäßigen Druck nicht weiter (K6 Entwurf, tet4 und hex8)

**Befund.** Zwei Würfel mit 1 m Kante haben eigene Knoten. Der untere ist 2 × 2 × 2 geteilt, der
obere 3 × 3 × 3. Die Fuge ist ein Kontaktpaar ohne Reibung, die oberen Knoten sind Slave, die
Last ist p = 100 N/mm². Der Zustand ist homogen, und beide Netze stellen ihn exakt dar.
Gemessen:

* hex8: σ_v +74,16 N/mm² an Knoten und Element, u_oben +1,52 %.
* tet4: σ_v −13,56 N/mm² am Knoten und −13,33 N/mm² am Element, u_oben +0,46 %.
* Die Auflagerkraft stimmt (±0,00 %).

**Gegenprobe (ohne das Geprüfte).** Derselbe Fall mit gleichen Netzen oben und unten ist grün,
mit tet4 und mit hex8 (0,00 N/mm²). Der Fehler kommt also vom Netzwechsel an der Fuge.

**Vermutung.** Knoten gegen Fläche mit einseitiger Zuordnung besteht den Druck-Patch-Test bei
ungleichen Netzen nicht. Dass hex8 fünfmal schlechter ist als tet4, passt dazu, dass eine
viereckige Master-Seite zur Projektion in zwei Dreiecke geteilt wird. Dann gehen die Kräfte
eines Slave-Knotens nur auf drei der vier Ecken. Das ist nicht gemessen.

**Besitzer: Löser** (`contact.py`, Löser-Sitzung). Am Drehlager sind die Netze an den
Kontaktflächen ungleich.

## Gelbe Zellen: was bekannt ist und was auffällt

* **L3 hex8, zwei Körper: +12,33 N/mm² in der Körperzeile, im Mittel +0,83.** Das Netz ist
  konform. Jeder Körper glättet seine Knotenspannung nur aus seinen eigenen Elementen, und an
  der gemeinsamen Fläche kommt jede Zeile von einer Seite. Der Nachweis (`solid_rand`) liest die
  größere Zeile. Aus einem Körper sind es 0,00 N/mm². Das ist Diskretisierung, die an einer
  Körpergrenze stärker ausfällt. Zur Kenntnis für die Stelle, die die Randspannung baut
  (`solver.randspannung_knoten`).
* **tet4 ist zu steif.**
  * Am Kragarm L1: −71,70 N/mm² bei h = 50 mm, −33,87 bei 25 mm, −10,81 bei 12,5 mm (74.634
    Unbekannte).
  * Am Lamé-Rohr L2: −88,59, −47,40, −24,32 und −12,26 N/mm² bei h = 25, 12,5, 6,25 und
    3,125 mm.
* **tet4 im Hill-Rohr (P2) liegt auf der weichen Seite.** u_r(b) +17,26 bis +12,32 %, σ_v(b)
  +99,64 bis +75,35 N/mm² bei h = 25 bis 3,125 mm. Elastisch bei ν = 0,4999 ist tet4 dagegen
  −27,30 % zu steif (0b17b12). Ungeklärt, **Element-Sitzung**.
* **hex20 sperrt bei ν → 0,5** (P2 Mittel: σ_v(b) −45,79 N/mm², u_r(b) −22,48 %; Fein: −5,00
  N/mm², −2,38 %). Die elastische Gegenprobe steht in 0b17b12: u_r(a) −8,98 % (8 × 4) bzw.
  −0,65 % (16 × 8). **Element-Sitzung.**
* **Lamé-Rohr L2, quadratische Elemente.** Fein bleiben 1,58 N/mm² (tet10) bzw. 1,12 N/mm²
  (hex20) an der gekrümmten Innenfläche. Der Fehler sinkt mit h.

## Gesperrte Zellen

Alle Kontaktzellen der Stufen Mittel und Fein sind gesperrt: K1 bis K7, KP1 und KP2, je tet10
und hex20, zusammen 36 Rechnungen. Die Sperre greift für die Kontaktbedingung (Spaltelemente)
genauso wie für das Kontaktpaar, auch für hex20. Sobald die Löser-Sitzung den tet10-Kontakt
liefert, rechnet `python -m tests.pruefmatrix --fall K1 K2 K3 K4 K5 K6 K7 KP1 KP2` diese Zellen
nach.

## Kontrollläufe (`--gegenprobe`, zweimal gerechnet, gleich)

Jede neue Prüfung lief einmal ohne das, was sie prüft, und musste dann fehlschlagen. Jede
Ursache einer neuen roten Zelle haben wir mit einer Kur als Monkeypatch nachgerechnet.

| Kontrolllauf | tet4 | hex8 | erwartet | erfüllt |
|---|---|---|---|---|
| K4 ohne Phase 2 (jede Reibgruppe gilt als ganz rutschend) | rot: „Phase 2 nicht durchlaufen“, Feder −94,45 % | rot: dasselbe, Feder −93,32 % | rot mit dieser Meldung | ja |
| K4 Kur: `SLIP_STIFFNESS_FINE` 1e-12 | Feder +0,88 %, quer −3,57 % | Feder +1,17 %, quer −2,49 % | Summe x = H_B | ja (Rest: Richtung) |
| K4 Kur: dazu `GLEIT_ANTEIL` 1 | rot: Feder +1,07 %, quer +0,41 % | **grün**: Feder +0,26 %, quer −0,00 % | grün | hex8 ja, tet4 nein |
| K5 Kur: keine Gruppe ganz rutschend, `SLIP_STIFFNESS_FINE` 1e-12 | rot: Feder +1,47 % | **grün**: Feder +0,21 % | grün | hex8 ja, tet4 nein |
| K7 Spalt übergangen (`contact.AUFLIEGEND` = 1) | rot: u_oben −51,22 %, Weg Spiel +105,00 % | rot: dasselbe | rot | ja |
| K6 mit gleichen Netzen | grün, 0,00 N/mm² | grün, 0,00 N/mm² | grün | ja |
| L3 hex8 Entwurf, Mittel der Zeilen | +0,83 (je Zeile +12,33) | | Zeile ≥ Mittel | ja |
| L3 tet10 Mittel, Mittel der Zeilen | +0,75 (je Zeile +1,65) | | Zeile ≥ Mittel | ja |
| L3 hex20 Mittel, Mittel der Zeilen | | +610,29 (je Zeile +765,60) | Zeile ≥ Mittel | ja |
| K1 Entwurf, Mittel der Zeilen | +10,32 (je Zeile +10,32) | −0,00 (je Zeile −0,00) | Zeile ≥ Mittel | ja |

In K7 geht der Spalt, wenn er übergangen wird, auch in den Vergleich der beiden Wege ein. Der
Weg über `ContactPair.spiel` gibt weiter 1,7826 mm, der geometrische Weg 0,8696 mm. Die Prüfung
„Weg Spiel“ unterscheidet also die beiden Wege.

## Wiederholung

Mit dem Stand vor der K2-Korrektur liefen die Matrix und die Kontrollläufe je zweimal (Lauf 1
und 2). Ohne die Zeitspalte ist die Ausgabe gleich. Dann haben wir die K2-Federn korrigiert und
die Matrix ein drittes Mal gerechnet: Außer K2 ist Lauf 3 gleich Lauf 2. K2 lief danach noch
einmal allein und gab dieselben Zahlen wie in Lauf 3, einschließlich der Zusatzreihe. Die
Tabellen unten sind Lauf 3. Laufzeiten: 5,9, 6,8 und 5,1 min. Nebenher lief der
Drehlager-Kontrolllauf der Löser-Sitzung.

## Wem was gehört

| Befund | Zellen | Besitzer |
|---|---|---|
| 1 hex20-Mitten an gemeinsamen Flächen nicht geteilt | L3 Mittel/Fein hex20 | Vernetzer (Fable) |
| 2 freier Vernetzer: gemeinsame Fläche nicht konform, h wirkt nicht | K1, KP1, L3 tet4/tet10, K2 tet4 (gelb) | Vernetzer (Fable) |
| 3 Plastizität meldet „nicht konvergiert“ bei Übermaß als einziger Last | KP2 Entwurf | Löser |
| 4 ganz gleitende Gruppe: Reststeifigkeit 1e-3 k_t trägt statt der Feder | K5 Entwurf | Löser (`contact.py`) |
| 5 Phase 2: Reststeifigkeit 1e-8 k_t proportional zum Gleitweg, Gleitrichtung festgehalten | K4 Entwurf | Löser (`contact.py`) |
| 6 ungleiche Netze an der Fuge geben gleichmäßigen Druck nicht weiter | K6 Entwurf | Löser (`contact.py`) |
| hex20 sperrt bei ν → 0,5 (gelb) | P2 Mittel/Fein hex20 | Element-Sitzung |
| tet4 plastisch auf der weichen Seite (gelb) | P2 tet4 | Element-Sitzung |
| Körperzeilen an gemeinsamer Fläche (gelb) | L3 hex8 | zur Kenntnis |
| Kontakt an quadratischen Seiten (gesperrt) | alle Kontaktzellen Mittel/Fein | Löser-Sitzung (Auftrag) |
| abgebildeter Pfad ohne Kantenlänge | Stufe Fein bei Sechsflächnern | Vernetzer (Fable) |

Einen Fehler der Matrix selbst (K2) haben wir gefunden und korrigiert. Nach der Korrektur hängt
keine rote Zelle an der Matrix.

## Tabellen (Lauf 3 vom 25.09.2026)

| Rechenart | Entwurf | Mittel | Fein |
|---|---|---|---|
| linear | 1 grün, 4 gelb, 1 **rot** | 2 grün, 2 gelb, 2 **rot** | 2 grün, 3 gelb, 1 **rot** |
| Kontakt | 6 grün, 1 gelb, 7 **rot** | 14 gesperrt | 14 gesperrt |
| Plastizität | 2 grün, 2 gelb | 2 grün, 2 gelb | 2 grün, 2 gelb |
| Kontakt + Plastizität | 1 grün, 3 **rot** | 4 gesperrt | 4 gesperrt |

Je Fall und Stufe (Tetraeder · Sechsflächner):

| Fall | Rechenart | Entwurf | Mittel | Fein |
|---|---|---|---|---|
| L1 Kragarm aus einem Körper, σ_v an der Oberkante bei L/2 (Saint-Venant) | linear | tet4 gelb · hex8 grün | tet10 grün · hex20 grün | tet10 grün · hex20 grün |
| L2 Lamé-Rohr unter Innendruck, ebene Dehnung (ν = 0,3) | linear | tet4 gelb · hex8 gelb | tet10 gelb · hex20 gelb | tet10 gelb · hex20 gelb |
| L3 Kragarm aus zwei Körpern (gemeinsame Fläche bei L/2), σ_v wie L1 | linear | tet4 **rot** · hex8 gelb | tet10 **rot** · hex20 **rot** | tet10 gelb · hex20 **rot** |
| K1 Fuge ohne Zug, Druck geht durch (zwei Würfel, passende Netze) | Kontakt | tet4 **rot** · hex8 grün | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| K2 Fuge ohne Zug, Zug öffnet (zwei Würfel, oben in Federn) | Kontakt | tet4 gelb · hex8 grün | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| K3 Presspassung, ebene Fuge (Kontaktpaar mit Übermaß) | Kontakt | tet4 grün · hex8 grün | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| K4 Fuge mit Reibung μ 0,3: Klotz A haftet, Klotz B gleitet gegen Federn (ein Kontaktpaar) | Kontakt | tet4 **rot** · hex8 **rot** | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| K5 Fuge mit Reibung μ 0,3: ein Klotz gleitet ganz, der Rest geht in Federn | Kontakt | tet4 **rot** · hex8 **rot** | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| K6 Kontaktpaar mit ungleichen Netzen (oben 1,5-mal feiner als unten), Druck geht durch | Kontakt | tet4 **rot** · hex8 **rot** | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| K7 Anfangsspalt g = 1 mm schließt sich unter Last (Kontaktpaar, oben Federn) | Kontakt | tet4 grün · hex8 grün | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| P1 Druckstab einachsig, bilinear verfestigend (fy 235, E_t/E 5 %) | Plastizität | tet4 grün · hex8 grün | tet10 grün · hex20 grün | tet10 grün · hex20 grün |
| P2 Rohr unter Innendruck nach Hill, ideal plastisch (ν = 0,4999) | Plastizität | tet4 gelb · hex8 gelb | tet10 gelb · hex20 gelb | tet10 gelb · hex20 gelb |
| KP1 Fuge ohne Zug unter Druck, beide Würfel fließen (fy 235, E_t/E 5 %) | Kontakt + Plastizität | tet4 **rot** · hex8 grün | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |
| KP2 Presspassung, ebene Fuge, Übermaß bis ins Fließen (fy 235, E_t/E 5 %) | Kontakt + Plastizität | tet4 **rot** · hex8 **rot** | tet10 gesperrt · hex20 gesperrt | tet10 gesperrt · hex20 gesperrt |

### L1 Kragarm aus einem Körper, σ_v an der Oberkante bei L/2 (Saint-Venant)

Soll: σ_xx = M z/I = 355 N/mm² bei x = L/2 (Oberkante, Mitte der Breite); L 1,0 / B 0,1 / H 0,2 m; ausgewertet am Eckknoten der Oberkante, der (L/2, B/2, H) am nächsten liegt, gegen σ_xx an seinem x (Saint-Venant: an der Oberkante unabhängig von y). Grenze: 1 N/mm² (Ziel des Anwenders).

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,0500 | gelb | σ_v -71,70 N/mm² | – | – | – | 1.836 | 2,5 | Knoten 116 bei x = 0,5000, y = 0,0650 m (Abstand 15,0 mm) |
| Entwurf | hex8 | 0,0500 | grün | σ_v -0,00 N/mm² | – | – | – | 945 | 0,6 | Knoten 163 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Mittel | tet10 | 0,0500 | grün | σ_v +0,29 N/mm² | – | – | – | 13.242 | 5,1 | Knoten 116 bei x = 0,5000, y = 0,0650 m (Abstand 15,0 mm) |
| Mittel | hex20 | 0,0500 | grün | σ_v +0,00 N/mm² | – | – | – | 3.231 | 1,7 | Knoten 163 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Fein | tet10 | 0,0250 | grün | σ_v -0,08 N/mm² | – | – | – | 80.295 | 44,4 | Knoten 349 bei x = 0,4875, y = 0,0459 m (Abstand 13,2 mm) |
| Fein | hex20 | 0,0250 | grün | σ_v -0,00 N/mm² | – | – | – | 20.283 | 3,8 | Knoten 930 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Zusatz | tet4 | 0,0250 | gelb | σ_v -33,87 N/mm² | – | – | – | 10.572 | 9,9 | Knoten 349 bei x = 0,4875, y = 0,0459 m (Abstand 13,2 mm) |
| Zusatz | tet4 | 0,0125 | gelb | σ_v -10,81 N/mm² | – | – | – | 74.634 | 137,6 | Knoten 1176 bei x = 0,4938, y = 0,0513 m (Abstand 6,4 mm) |

### L2 Lamé-Rohr unter Innendruck, ebene Dehnung (ν = 0,3)

Soll: σ_v(a) = 355 N/mm² (p skaliert), u_r(a) nach Lamé; a 0,1 / b 0,2 m. Grenze: 1 N/mm² an jedem Eckknoten der Innenfläche, u_r 1 %.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,0250 | gelb | σ_v -88,59 N/mm²; u_r -3,32 % | – | – | – | 270 | 0,0 | Netz 8 × 4 (n_t × n_r) |
| Entwurf | hex8 | 0,0250 | gelb | σ_v -28,34 N/mm²; u_r -0,65 % | – | – | – | 270 | 0,0 | Netz 8 × 4 (n_t × n_r) |
| Mittel | tet10 | 0,0250 | gelb | σ_v -4,72 N/mm²; u_r +0,02 % | – | – | – | 1.377 | 0,1 | Netz 8 × 4 (n_t × n_r) |
| Mittel | hex20 | 0,0250 | gelb | σ_v -3,80 N/mm²; u_r -0,00 % | – | – | – | 861 | 0,1 | Netz 8 × 4 (n_t × n_r) |
| Fein | tet10 | 0,0125 | gelb | σ_v -1,58 N/mm²; u_r +0,00 % | – | – | – | 5.049 | 0,3 | Netz 16 × 8 (n_t × n_r) |
| Fein | hex20 | 0,0125 | gelb | σ_v -1,12 N/mm²; u_r -0,00 % | – | – | – | 3.057 | 0,2 | Netz 16 × 8 (n_t × n_r) |
| Zusatz | tet4 | 0,0125 | gelb | σ_v -47,40 N/mm²; u_r -0,89 % | – | – | – | 918 | 0,2 | Netz 16 × 8 (n_t × n_r) |
| Zusatz | tet4 | 0,0063 | gelb | σ_v -24,32 N/mm²; u_r -0,23 % | – | – | – | 3.366 | 0,6 | Netz 32 × 16 (n_t × n_r) |
| Zusatz | tet4 | 0,0031 | gelb | σ_v -12,26 N/mm²; u_r -0,06 % | – | – | – | 12.870 | 2,8 | Netz 64 × 32 (n_t × n_r) |

### L3 Kragarm aus zwei Körpern (gemeinsame Fläche bei L/2), σ_v wie L1

Soll: wie L1; die Körper teilen die Fläche x = L/2, der Nachweisknoten liegt auf ihr - misst, ob das Netz über die gemeinsame Fläche trägt. Grenze: 1 N/mm² (Ziel des Anwenders).

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,0500 | **rot** | σ_v -101,95 N/mm² | – | – | – | 1.623 | 1,1 | Netz nicht knotenkonform: 0 Orte mit zwei Knoten, 8 offene Innenseiten; σ_v -101,95 N/mm²; Knoten 50 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Entwurf | hex8 | 0,0500 | gelb | σ_v +12,33 N/mm² | – | – | – | 945 | 0,1 | Knoten 165 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Mittel | tet10 | 0,0500 | **rot** | σ_v +1,65 N/mm² | – | – | – | 11.469 | 1,4 | Netz nicht knotenkonform: 2 Orte mit zwei Knoten, 8 offene Innenseiten; σ_v 1,65 N/mm²; Knoten 50 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Mittel | hex20 | 0,0500 | **rot** | σ_v +765,60 N/mm² | – | – | – | 3.297 | 0,2 | Netz nicht knotenkonform: 22 Orte mit zwei Knoten, 0 offene Innenseiten; σ_v 765,60 N/mm²; Knoten 165 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Fein | tet10 | 0,0250 | gelb | σ_v -0,14 N/mm² | – | – | – | 86.718 | 15,2 | Netzfehler: Netz nicht knotenkonform: 2 Orte mit zwei Knoten, 8 offene Innenseiten; Knoten 132 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |
| Fein | hex20 | 0,0250 | **rot** | σ_v +654,32 N/mm² | – | – | – | 20.511 | 2,4 | Netz nicht knotenkonform: 76 Orte mit zwei Knoten, 0 offene Innenseiten; σ_v 654,32 N/mm²; Knoten 932 bei x = 0,5000, y = 0,0500 m (Abstand 0,0 mm) |

### K1 Fuge ohne Zug, Druck geht durch (zwei Würfel, passende Netze)

Soll: σ_zz = −p = −100 N/mm² überall, u_oben = −p L/E (L = 2 m); Auflager = p A. Grenze: 1 N/mm² an jedem Knoten, u 1 %, Auflager 1 %. Exakt (homogener Zustand, jedes Element stellt ihn exakt dar): jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | **rot** | σ_v +10,32 N/mm²; σ_v Element -25,41 N/mm²; u_oben +0,13 %; Auflager -0,00 % | ja | – | 0 | 1.263 | 0,6 | Netz nicht knotenkonform: 0 Orte mit zwei Knoten, 8 offene Innenseiten; σ_v 10,32 N/mm², σ_v Element -25,41 N/mm²; 24 Spaltelemente |
| Entwurf | hex8 | 0,5000 | grün | σ_v -0,00 N/mm²; σ_v Element +0,00 N/mm²; u_oben +0,00 %; Auflager -0,00 % | ja | – | 0 | 162 | 0,0 | 9 Spaltelemente |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | – | 0,4 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | – | 0,4 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |

### K2 Fuge ohne Zug, Zug öffnet (zwei Würfel, oben in Federn)

Soll: Fundament trägt 0 (Zug −100 N/mm² auf dem Deckel), die Last hängt ganz in den Federn. Grenze: Fundamentkraft ≤ 1 % der Last (entspricht 1 N/mm² mittlerer Fugenspannung). Exakt (homogener Zustand, jedes Element stellt ihn exakt dar): jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | gelb | Fundament 0,00 %; Federn +0,00 %; σ_v Element +0,00 N/mm² | ja | – | 0 | 1.263 | 0,7 | Netzfehler: Netz nicht knotenkonform: 0 Orte mit zwei Knoten, 8 offene Innenseiten; 24 Spaltelemente |
| Entwurf | hex8 | 0,5000 | grün | Fundament 0,00 %; Federn -0,00 %; σ_v Element +0,00 N/mm² | ja | – | 0 | 162 | 0,0 | 9 Spaltelemente |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | – | 1,7 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | – | 0,5 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Zusatz | tet4 | 0,2500 | gelb | Fundament 0,00 %; Federn +0,00 %; σ_v Element +0,00 N/mm² | ja | – | 0 | 1.263 | 0,7 | Netzfehler: Netz nicht knotenkonform: 0 Orte mit zwei Knoten, 8 offene Innenseiten; 24 Spaltelemente |
| Zusatz | tet4 | 0,1250 | gelb | Fundament 0,00 %; Federn +0,00 %; σ_v Element +0,00 N/mm² | ja | – | 0 | 8.406 | 3,8 | Netzfehler: Netz nicht knotenkonform: 0 Orte mit zwei Knoten, 20 offene Innenseiten; 78 Spaltelemente |
| Zusatz | tet4 | 0,0625 | grün | Fundament 0,00 %; Federn +0,00 %; σ_v Element +0,00 N/mm² | ja | – | 0 | 59.652 | 37,2 | 314 Spaltelemente |

### K3 Presspassung, ebene Fuge (Kontaktpaar mit Übermaß)

Soll: σ = δ E/(2 L) = 355 N/mm² überall (δ = 3,38 mm), Auflager σ A. Grenze: 1 N/mm² an jedem Knoten, Auflager 1 %. Exakt (homogener Zustand, jedes Element stellt ihn exakt dar): jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | grün | σ_v -0,01 N/mm²; σ_v Element -0,01 N/mm²; Auflager -0,00 % | ja | – | 0 | 162 | 0,1 | 2³ Zellen je Würfel |
| Entwurf | hex8 | 0,5000 | grün | σ_v -0,01 N/mm²; σ_v Element -0,01 N/mm²; Auflager -0,00 % | ja | – | 0 | 162 | 0,0 | 2³ Zellen je Würfel |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | 750 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | 486 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | 4.374 | 0,1 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | 2.550 | 0,1 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |

### K4 Fuge mit Reibung μ 0,3: Klotz A haftet, Klotz B gleitet gegen Federn (ein Kontaktpaar)

Soll: Unterlage 2 × 1 × 1 m, unten eingespannt; darauf die Klötze A und B, je 1 × 1 × 0,25 m, eigene Knoten, beide in **einem** Kontaktpaar, je p = 100 N/mm² Auflast (N = 100.000 kN). A: Schub H_A = 0,5 μN = 15.000 kN, sonst nichts - Reibkraft = H_A, Fugenschlupf nur elastisch (Penalty). B: Schub H_B = 1,5 μN = 45.000 kN, auf dem Deckel Federn k = 1.000 kN/mm in x und y - Reibkraft = μN = 30.000 kN, Federkraft = H_B − μN = 15.000 kN. Weil A haftet und B gleitet, läuft die Reibung in Phase 2 (contact.py). Grenze: Kräfte 1 %; Fugenschlupf von A 1 % seiner Deckelverschiebung; Phase 2 muss im Laufbuch (res.info['laeufe']) stehen, sonst rot. Exakt (die Kräfte folgen aus Gleichgewicht und Reibgesetz, unabhängig vom Netz; Fehler sind keine Diskretisierung): jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | **rot** | Reibung A -0,00 %; Schlupf A +0,00 %; Reibung B -0,44 %; Reibung B quer -3,60 %; Feder B -10,16 % | ja | – | 0 | 243 | 0,3 | falsches Ergebnis (die Kräfte folgen aus Gleichgewicht und Reibgesetz, unabhängig vom Netz; Fehler sind keine Diskretisierung): Reibung B quer -3,60 %, Feder B -10,16 %; A: 9 Haften; B: 9 Gleiten; Phase-2-Schritte 5; res.singular: 2 × „hebt ab“ mit Kraft 0 |
| Entwurf | hex8 | 0,5000 | **rot** | Reibung A -0,00 %; Schlupf A +0,00 %; Reibung B -0,58 %; Reibung B quer -2,51 %; Feder B -3,45 % | ja | – | 0 | 243 | 0,1 | falsches Ergebnis (die Kräfte folgen aus Gleichgewicht und Reibgesetz, unabhängig vom Netz; Fehler sind keine Diskretisierung): Reibung B quer -2,51 %, Feder B -3,45 %; A: 9 Haften; B: 9 Gleiten; Phase-2-Schritte 6; res.singular: 2 × „hebt ab“ mit Kraft 0 |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | 1.125 | 0,1 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | 729 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | 5.589 | 0,3 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | 3.285 | 0,2 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |

### K5 Fuge mit Reibung μ 0,3: ein Klotz gleitet ganz, der Rest geht in Federn

Soll: Unterlage 1 × 1 × 1 m, darauf nur Klotz B wie in K4 (p = 100 N/mm², H = 1,5 μN, Federn k = 1.000 kN/mm): Reibkraft = μN = 30.000 kN, Federkraft = H − μN = 15.000 kN. Alle Knoten der Gruppe gleiten; für eine ganz gleitende Gruppe nimmt contact.py die grobe Reststeifigkeit 1e-3 k_t (_k_res), gleich ob Phase 1 oder 2. Grenze: Kräfte 1 %. Exakt (die Kräfte folgen aus Gleichgewicht und Reibgesetz, unabhängig vom Netz; Fehler sind keine Diskretisierung): jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | **rot** | Reibung B -0,61 %; Reibung B quer +0,76 %; Feder B -90,67 % | ja | – | 0 | 135 | 0,0 | falsches Ergebnis (die Kräfte folgen aus Gleichgewicht und Reibgesetz, unabhängig vom Netz; Fehler sind keine Diskretisierung): Feder B -90,67 %; B: 9 Gleiten; Phase-2-Schritte 0 |
| Entwurf | hex8 | 0,5000 | **rot** | Reibung B -0,10 %; Reibung B quer +0,00 %; Feder B -86,09 % | ja | – | 0 | 135 | 0,0 | falsches Ergebnis (die Kräfte folgen aus Gleichgewicht und Reibgesetz, unabhängig vom Netz; Fehler sind keine Diskretisierung): Feder B -86,09 %; B: 9 Gleiten; Phase-2-Schritte 3 |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | 600 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | 396 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | 2.916 | 0,1 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | 1.740 | 0,1 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |

### K6 Kontaktpaar mit ungleichen Netzen (oben 1,5-mal feiner als unten), Druck geht durch

Soll: zwei Würfel 1 m mit eigenen Knoten, unten Zellweite h, oben 2/3 h (Entwurf 2 × 2 × 2 gegen 3 × 3 × 3), Kontaktpaar ohne Reibung, oben Slave; σ_zz = −p = −100 N/mm², u_oben = −p L/E (L = 2 m), Auflager p A. Grenze: 1 N/mm² an jedem Knoten und Element, u 1 %, Auflager 1 %. Exakt (homogener Zustand, jedes Element stellt ihn exakt dar): jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | **rot** | σ_v -13,56 N/mm²; σ_v Element -13,33 N/mm²; u_oben +0,46 %; Auflager -0,00 % | ja | – | 0 | 273 | 0,1 | falsches Ergebnis (homogener Zustand, jedes Element stellt ihn exakt dar): σ_v -13,56 N/mm², σ_v Element -13,33 N/mm² |
| Entwurf | hex8 | 0,5000 | **rot** | σ_v +74,16 N/mm²; σ_v Element +74,16 N/mm²; u_oben +1,52 %; Auflager +0,00 % | ja | – | 0 | 273 | 0,1 | falsches Ergebnis (homogener Zustand, jedes Element stellt ihn exakt dar): σ_v 74,16 N/mm², σ_v Element 74,16 N/mm², u_oben 1,52 % |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | 1.404 | 0,1 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | 867 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | 8.778 | 0,4 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | 4.950 | 0,2 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |

### K7 Anfangsspalt g = 1 mm schließt sich unter Last (Kontaktpaar, oben Federn)

Soll: zwei Würfel 1 m, der obere 1 mm angehoben, auf dem Deckel Federn k = 10.000 kN/mm in z (nach Flächenanteil verteilt), Last p A = 100.000 kN: F_c = (F − k g)/(1 + 2 k L/(E A)) = 82.174 kN durch die Fuge, u_oben = g + 2 F_c L/(E A) = 1,7826 mm, σ = F_c/A in beiden Würfeln. Zweiter Weg: derselbe Würfel anliegend mit ContactPair.spiel = g. Grenze: 1 N/mm² an jedem Knoten und Element, u 1 %, Kräfte 1 %; beide Wege gleich auf 0,01 %. Exakt (homogener Zustand, jedes Element stellt ihn exakt dar): jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | grün | σ_v -0,00 N/mm²; σ_v Element +0,00 N/mm²; u_oben +0,00 %; Fuge (Auflager) -0,00 %; Federn +0,00 %; Weg Spiel -0,00 % | ja | – | 0 | 162 | 0,0 | u_oben 1,7826 mm, über spiel 1,7826 mm; Kontakt 2. Weg konv. True |
| Entwurf | hex8 | 0,5000 | grün | σ_v -0,00 N/mm²; σ_v Element -0,00 N/mm²; u_oben +0,00 %; Fuge (Auflager) -0,00 %; Federn +0,00 %; Weg Spiel -0,00 % | ja | – | 0 | 162 | 0,0 | u_oben 1,7826 mm, über spiel 1,7826 mm; Kontakt 2. Weg konv. True |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | 750 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | 486 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | 4.374 | 0,2 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | 2.550 | 0,2 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |

### P1 Druckstab einachsig, bilinear verfestigend (fy 235, E_t/E 5 %)

Soll: p = 300 N/mm²: σ_v = p überall, u_oben = L (p/E + (p − fy)/H), L = 2 m. Grenze: 1 N/mm² an jedem Knoten, u 1 %. Exakt (homogener Zustand, jedes Element stellt ihn exakt dar): jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | grün | σ_v -0,00 N/mm²; σ_v Element -0,00 N/mm²; u_oben +0,00 % | – | ja | 0 | 183 | 0,5 |  |
| Entwurf | hex8 | 0,5000 | grün | σ_v -0,00 N/mm²; σ_v Element +0,00 N/mm²; u_oben -0,00 % | – | ja | 0 | 135 | 0,1 |  |
| Mittel | tet10 | 0,5000 | grün | σ_v +0,00 N/mm²; σ_v Element +0,00 N/mm²; u_oben +0,00 % | – | ja | 0 | 1.083 | 0,4 |  |
| Mittel | hex20 | 0,5000 | grün | σ_v +0,00 N/mm²; σ_v Element +0,00 N/mm²; u_oben +0,00 % | – | ja | 0 | 423 | 0,4 |  |
| Fein | tet10 | 0,2500 | grün | σ_v +0,00 N/mm²; σ_v Element +0,00 N/mm²; u_oben +0,00 % | – | ja | 0 | 8.409 | 2,9 |  |
| Fein | hex20 | 0,2500 | grün | σ_v +0,00 N/mm²; σ_v Element +0,00 N/mm²; u_oben +0,00 % | – | ja | 0 | 2.355 | 2,6 |  |

### P2 Rohr unter Innendruck nach Hill, ideal plastisch (ν = 0,4999)

Soll: c/a = 1,5 bei p = 255,88 N/mm²: σ_v(b) = fy c²/b² = 199,69 N/mm², u_r(b) = k c²/(2 G b); fy 355. Grenze: 1 N/mm² an jedem Eckknoten der Außenfläche, u_r 1 %.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,0250 | gelb | σ_v(b) +99,64 N/mm²; u_r(b) +17,26 % | – | ja | – | 270 | 0,1 | Netz 8 × 4, anfangsdehnung |
| Entwurf | hex8 | 0,0250 | gelb | σ_v(b) -6,87 N/mm²; u_r(b) -1,54 % | – | ja | – | 270 | 0,2 | Netz 8 × 4, anfangsdehnung |
| Mittel | tet10 | 0,0250 | gelb | σ_v(b) +7,55 N/mm²; u_r(b) -0,33 % | – | ja | – | 1.377 | 0,4 | Netz 8 × 4, anfangsdehnung |
| Mittel | hex20 | 0,0250 | gelb | σ_v(b) -45,79 N/mm²; u_r(b) -22,48 % | – | ja | – | 861 | 0,2 | Netz 8 × 4, anfangsdehnung |
| Fein | tet10 | 0,0125 | gelb | σ_v(b) +2,98 N/mm²; u_r(b) -0,08 % | – | ja | – | 5.049 | 2,1 | Netz 16 × 8, anfangsdehnung |
| Fein | hex20 | 0,0125 | gelb | σ_v(b) -5,00 N/mm²; u_r(b) -2,38 % | – | ja | – | 3.057 | 0,6 | Netz 16 × 8, anfangsdehnung |
| Zusatz | tet4 | 0,0125 | gelb | σ_v(b) +98,70 N/mm²; u_r(b) +19,95 % | – | ja | – | 918 | 0,5 | Netz 16 × 8, anfangsdehnung |
| Zusatz | tet4 | 0,0063 | gelb | σ_v(b) +93,38 N/mm²; u_r(b) +19,12 % | – | ja | – | 3.366 | 1,8 | Netz 32 × 16, anfangsdehnung |
| Zusatz | tet4 | 0,0031 | gelb | σ_v(b) +75,35 N/mm²; u_r(b) +12,32 % | – | ja | – | 12.870 | 7,4 | Netz 64 × 32, anfangsdehnung |

### KP1 Fuge ohne Zug unter Druck, beide Würfel fließen (fy 235, E_t/E 5 %)

Soll: p = 300 N/mm²: σ_v = p überall, u_oben = L (p/E + (p − fy)/H), L = 2 m. Grenze: 1 N/mm² an jedem Knoten, u 1 %, Auflager 1 %. Exakt (homogener Zustand, jedes Element stellt ihn exakt dar): jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | **rot** | σ_v +6,02 N/mm²; σ_v Element -10,60 N/mm²; u_oben +0,14 %; Auflager -0,00 % | ja | ja | 0 | 1.263 | 1,2 | Netz nicht knotenkonform: 0 Orte mit zwei Knoten, 8 offene Innenseiten; σ_v 6,02 N/mm², σ_v Element -10,60 N/mm²; 24 Spaltelemente |
| Entwurf | hex8 | 0,5000 | grün | σ_v -0,00 N/mm²; σ_v Element -0,00 N/mm²; u_oben +0,00 %; Auflager -0,00 % | ja | ja | 0 | 162 | 0,1 | 9 Spaltelemente |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | – | 0,5 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | – | 0,4 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | – | 0,0 | fugen.QuadratischeSeiten: Kontaktbedingung Fuge |

### KP2 Presspassung, ebene Fuge, Übermaß bis ins Fließen (fy 235, E_t/E 5 %)

Soll: δ = 2 L ε(300 N/mm²) = 14,62 mm (ε_p 0,588 %): σ_v = 300 N/mm² überall, Auflager σ A. Grenze: 1 N/mm² an jedem Knoten, Auflager 1 %. Exakt (homogener Zustand, jedes Element stellt ihn exakt dar): jede Überschreitung ist rot.

| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |
|---|---|---|---|---|---|---|---|---|---|---|
| Entwurf | tet4 | 0,5000 | **rot** | σ_v -0,00 N/mm²; σ_v Element -0,00 N/mm²; Auflager -0,00 % | ja | **nein** | 0 | 162 | 1,0 | Plastizität konvergiert = False; 2³ Zellen je Würfel |
| Entwurf | hex8 | 0,5000 | **rot** | σ_v -0,00 N/mm²; σ_v Element -0,00 N/mm²; Auflager -0,00 % | ja | **nein** | 0 | 162 | 2,9 | Plastizität konvergiert = False; 2³ Zellen je Würfel |
| Mittel | tet10 | 0,5000 | gesperrt | – | – | – | – | 750 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Mittel | hex20 | 0,5000 | gesperrt | – | – | – | – | 486 | 0,0 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | tet10 | 0,2500 | gesperrt | – | – | – | – | 4.374 | 0,2 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |
| Fein | hex20 | 0,2500 | gesperrt | – | – | – | – | 2.550 | 0,1 | fugen.QuadratischeSeiten: Kontaktpaar Fuge |

Laufzeit gesamt 5,1 min (einkernig, 25.09.2026).
