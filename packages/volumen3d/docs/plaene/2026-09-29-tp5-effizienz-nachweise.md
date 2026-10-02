# Plan Teilprojekt 5 (Stufe 2c) samt Rest aus Stufe 2: Leistung, Effizienz, Nachweise

> Vorgehen: je Schritt eine Sitzung mit dem angegebenen Modell (der Anwender stellt es von Hand ein),
> Prüfung nach jedem Schritt, Commit je Schritt, Messungen aus einem festen Arbeitsbaum auf dem Commit
> (ein Prozess je Fall), Zahlen erst nach Gegenprobe. Entwurf: `packages/volumen3d/docs/Entwurf.md`,
> Abschnitt 2 (TP 5) und 4d; Vorgabe Abschnitte 3, 6 (Stufe 2), 8.3, 9, 11, 13.

**Ziel:** Die Stufe 2 der Vorgabe vollständig machen und Teilprojekt 5 bauen. Offen aus Stufe 2 sind die
Leistungsabnahme (10⁶ Freiheitsgrade unter 60 s auf der Referenz-GPU), ein Aufbau des iterativen Wegs,
der das GPU-Mehrgitter gegenüber dem Direktlöser konkurrenzfähig macht, und die Streuung der Iterationen
über die Schnittlagen. Teilprojekt 5 bringt Moment Fitting, Spannungsrückgewinnung, Hot-Spot-Auswertung an
Nahtlinien, Konvergenzkurve und Protokoll, STEP über gmsh und die Abnahme am Knotenblech mit Kehlnaht.

**Stand vor dem Plan (29.09.2026, main 7a6c922):** `"auto"` wählt den Direktlöser, weil er in der
Schlussmessung in 20 von 23 Fällen schneller war (Theorie 11.10). Der Aufbau des iterativen Wegs dauert
2 bis 20 s länger als Assemblieren und Faktorisieren; das Lösen ist auf der GPU beim Block ab
186 000 Freiheitsgraden drei- bis sechsmal schneller. Die 8-GB-Karte begrenzt das Mehrgitter auf etwa
500 000 Freiheitsgrade bei p 3. Die Iterationen streuen über fünf Schnittlagen um 28 % (Plan TP 4 verlangt
20 %). Der Vertrag enthält `WeldLine`, `HotSpotResult` und `DetailResult.convergence` schon; die gemeinsamen
Referenzmodelle aus Vertrag Abschnitt 8 (`tests/reference_models/`) fehlen im Repository.

## Entscheidungen des Anwenders (29.09.2026)

| Nr. | Frage | Entscheidung |
|---|---|---|
| E1 | Reihenfolge: zuerst der Rest aus Stufe 2 (Phase A), dann Teilprojekt 5 (Phase B)? | ja |
| E2 | Referenzwerte für das Knotenblech (Hot-Spot, Vorgabe 13: Tet10 in RFEM oder Ansys) | **Hauptprogramm**: Tet10-Rechnung von `statik3d/` als Referenz, im Protokoll so benannt |
| E3 | Ablage der Referenzmodelle in `tests/reference_models/` (für Session B nur lesbar) | ja: Vorschlag in `docs/vertrag-aenderungen/`, eigener Pull Request der Hauptsitzung |
| E4 | gmsh als optionale Abhängigkeit für STEP (`pip install gmsh`, Extra `step`) | ja, nur optional; ohne gmsh klare Fehlermeldung |

## Phase A – Rest aus Stufe 2 (Leistung, Vorgabe 8.3, 9, 13)

### A1: Aufbau des iterativen Wegs vermessen
- Zeit je Posten an Kirsch h 10/h 8 und Block h 16/h 14 (p 3): Zelldaten (Integration der Schnittzellen),
  `Zelldaten.matrix()`, CᵀKC, Mehrgitter (Ebenen, Glätterblöcke, Grobgitter, Nullraum, λ_max) gegen
  Assemblieren und Pardiso beim Direktlöser. Zwei unabhängige Messskripte, nur Übereinstimmendes zählt.
- Ergebnis: Tabelle je Posten im Plan und in Theorie 11.10, daraus die Ziele für A2.
- Prüfung: beide Skripte stimmen auf 10 % überein; Summe der Posten = gemessener Aufbau auf 5 %.

**Ergebnis A1 (29.09.2026, Commit cbe0e09, freie Maschine, je Lauf ein Prozess).** Zwei Skripte – eines liest
die im Code eingebauten Zeitwerte, eines hängt Zeitmesser mit GPU-Synchronisation von außen um die Funktionen –
stimmen in allen acht Läufen auf 10 % überein; die Posten erklären den Aufbau bis auf 3 %. Sekunden:

| Posten | Kirsch h 10 V 0,3 | Kirsch h 8 V 0,3 | Block h 16 V 0 | Block h 14 V 0,3 |
|---|---|---|---|---|
| Freiheitsgrade (frei) | 229 830 (181 797) | 472 611 (286 584) | 185 856 (171 720) | 340 476 (265 284) |
| Konstruktor, beide Wege | 10,7 | 23,1 | 11,1 | 17,0 |
| davon Randquadratur / Werkstoffanteile / Wurzelwahl / hängende Zwänge | 3,9 / 1,6 / 1,1 / 3,2 | 5,3 / 2,6 / 5,3 / 6,1 | 6,7 / 3,6 / 0,3 / 0,0 | 8,8 / 4,9 / 1,4 / 0,0 |
| direkt: Assemblieren / CᵀKC / Faktorisieren + Lösen | 10,1 / 1,8 / 6,3 | 17,0 / 2,6 / 9,1 | 24,8 / 1,5 / 10,0 | 34,1 / 2,3 / 21,2 |
| Mehrgitter: Zelldaten + Matrix / CᵀKC / Einrichten / PCG | 9,6 / 1,7 / 3,0 / 3,1 | 15,7 / 2,6 / 4,4 / 7,8 | 24,6 / 1,4 / 3,5 / 1,6 | 33,5 / 2,4 / 20,8 / 4,0 |
| davon Glätterblöcke (Auszug, Inversion) | 1,4 | 2,1 | 2,3 | 19,0 |
| Gesamt direkt / Mehrgitter | 28,9 / 30,1 | 50,8 / 53,6 | 48,2 / 43,0 | 74,0 / 78,1 |

Befunde: (1) Zellintegration plus Matrix kostet auf dem iterativen Weg nicht mehr als das Assemblieren – die im
Plan vermutete doppelte Arbeit gibt es nicht. (2) Beim Block h 14 kostet ein einzelner Glätterblock der Größe
2 463 in der gestapelten Inversion von CuPy 8,6 s, Blöcke um 1 200 bis 1 350 je 1 bis 1,5 s; so große Blöcke
entstehen, wo eine Zelle über die Aggregation an mehrere Wurzeln gebunden ist (Schwelle 0,4). (3) Grobgitter
(0,3 s) und Nullraumprobe (unter 0,1 s) sind vernachlässigbar. (4) Konstruktor und Zellintegration tragen auf
beiden Wegen 40 bis 60 % der Gesamtzeit; sie zu senken hilft beiden Wegen gleich (Zellintegration auch über B1).

### A2: Aufbau beschleunigen
- Nach A1: (a) große Glätterblöcke nicht in der gestapelten Inversion, sondern einzeln per Cholesky (oder auf der
  CPU) invertieren; (b) die reduzierte feine Matrix auf dem iterativen Weg direkt aus den Zelldaten bauen statt
  K zu assemblieren und CᵀKC zu bilden, wenn das messbar spart (heute 3,5 bis 6,8 s); (c) im Konstruktor die
  Wurzelwahl (bis 5,3 s) und die hängenden Zwänge (bis 6,1 s) beschleunigen – das hilft beiden Wegen.
- Ziel: Einrichten des Mehrgitters an allen vier Fällen höchstens 4,5 s, Mehrgitter-Gesamtweg am Block h 14
  schneller als direkt; Konstruktor spürbar kürzer.
- Prüfung: bestehende Suiten (Operator = Matrix auf 10⁻¹², Mehrgitter, GPU, Zwänge, Patch), Gesamtweg an den
  vier A1-Fällen mit beiden Skripten.

**Ergebnis A2 (29.09.2026, Commit d0e6c37, freie Maschine, je Lauf ein Prozess, beide Messskripte auf 10 % gleich).**
Sekunden, vorher (cbe0e09) → nachher:

| Posten | Kirsch h 10 V 0,3 | Kirsch h 8 V 0,3 | Block h 16 V 0 | Block h 14 V 0,3 |
|---|---|---|---|---|
| Konstruktor | 10,7 → 6,5 | 23,1 → 11,8 | 11,1 → 9,9 | 17,0 → 14,1 |
| Mehrgitter einrichten | 3,0 → 2,5 | 4,4 → 3,9 | 3,5 → 2,0 | 20,8 → 3,8 |
| Gesamt direkt | 28,9 → 24,7 | 50,8 → 42,5 | 48,2 → 47,4 | 74,0 → 74,7 |
| Gesamt Mehrgitter GPU | 30,1 → 24,6 | 53,6 → 44,1 | 43,0 → 41,6 | 78,1 → 58,1 |

Die Ziele sind erreicht: das Einrichten des Mehrgitters bleibt in allen vier Fällen unter 4,5 s, am Block h 14 ist
das Mehrgitter jetzt 16,6 s schneller als der Direktlöser, und der Konstruktor ist bei den verfeinerten Gittern
um 40 bis 50 % kürzer. Zwangsmatrix und Wurzeln sind an fünf Modellen bitgleich mit dem alten Stand. Nicht
umgesetzt ist Teil (b), die reduzierte Matrix direkt aus den Zelldaten (heute 3,2 bis 6,7 s für Matrix und CᵀKC):
A3 ändert den Umgang mit der feinen Matrix ohnehin, der Punkt wandert dorthin.

### A3: GPU-Speicher für 10⁶ Freiheitsgrade
- Posten heute: Zellmatrizen der Schnittzellen (295 KB je Zelle bei p 3), Glätterblöcke (etwa 0,35 MB je
  Zelle), feine Matrix während des Auszugs. Optionen messen: Schwarz-Blöcke nur für Schnittzellen und
  Chebyshev-Jacobi für innere Zellen, Zellmatrizen in FP32 gespeichert und in FP64 gerechnet, Auszug ohne
  die ganze feine Matrix auf der GPU. FP32 im Glätter divergierte schon einmal (Blockkondition 10⁸) –
  jede Option gegen die FP64-Lösung prüfen.
- Ziel: 10⁶ Freiheitsgrade p 3 mit Spitze unter 7 GB, Iterationen unter 100, Ergebnis wie CPU auf 10⁻⁶.
- Prüfung: `test_gpu_speicher` um den neuen Fall erweitert, Schätzformel neu geeicht.

**Ergebnis A3 (30.09.2026).** Symmetrisch gepackte Blöcke mit zweiteiligem Kern (`fcm/bloecke_gpu.py`, halber
Speicher in FP64, gleich schnell wie vorher, bitgleich wiederholbar), Blockauszug auf der CPU, Pool-Freigabe je
Größengruppe bei knapper Karte; Schätzung neu geeicht. Höchststand des Pools im knappen Betrieb (Karte 50 bis 80 MB
darüber), Iterationen und Vergleich mit dem Direktlöser:

| Modell | Freiheitsgrade | Höchststand | belegt | Schätzung | Iterationen | Lösen GPU | gegen direkt |
|---|---|---|---|---|---|---|---|
| Block h 9, V 0 | 967 992 | 4 425 MB | 3 673 MB | 4 719 MB | 29 | 9,0 s | u 2,8·10⁻¹⁴, σ 5,8·10⁻¹³ (direkt 46 GB, 169 s) |
| Kirsch h 5,5, V 0 | 1 002 528 | 4 822 MB | 4 066 MB | 5 227 MB | 36 | 11,1 s | σ 1,6·10⁻¹² (u: freie z-Bewegung; direkt 27 GB, 36 s) |

Ziele erreicht: unter 7 GB, unter 100 Iterationen, Ergebnis wie CPU. FP32 war nicht nötig. Teil (b) aus A2
(reduzierte Matrix direkt aus den Zelldaten) bleibt zurückgestellt: Nutzen 2 bis 3 s, kein Speichergewinn.
Test `test_million_gpu` (Kirsch h 5,5, 90 s, nur bei ≥ 6,5 GB freier Karte).

**Entscheidung A4:** entfällt. Das Grobgitter p = 1 (Pardiso auf der CPU) kostet beim Lösen mit 10⁶
Freiheitsgraden 1,0 bis 1,2 s von 9 bis 11 s (12 %) und beim Einrichten 1 bis 5 s; die gepackten Blöcke
(Operator und Glätter) tragen 69 %. Ein h-Mehrgitter unter p = 1 brächte hier nichts.

### A4: h-Mehrgitter unter p = 1 (nur wenn nötig)
- Entscheidungspunkt nach A3: ist das Grobgitter p = 1 (Pardiso) bei 10⁶ Freiheitsgraden der Engpass in
  Zeit oder Speicher? Nur dann h-Ebenen über den Oktree mit hängenden Knoten (Vorgabe 8.3 „p/h“).
- Prüfung: Iterationen unabhängig von der Größe (h 10 bis h 5), Galerkin-Eigenschaft wie bei den p-Ebenen.

### A5: Streuung der Iterationen über die Schnittlagen auf 20 %
- Ritz-Analyse der Lage mit den meisten Iterationen (Kirsch h 10, Versatz 0,4: 31 gegen im Mittel 24).
  Optionen: gewichteter Schwarz-Glätter, Ghost Penalty als Alternative zur Aggregation (Vorgabe 8.3).
- Prüfung: fünf Lagen h 10 und h 8 innerhalb ±20 %, K_tg unverändert auf 0,2 %.

**Vorgehen, vor der Messung festgelegt (30.09.2026):** Gemessen werden die fünf Lagen (Versatz 0; 0,2;
0,4; 0,6; 0,8) bei h 10 und h 8, je Fall ein Prozess aus einem festen Arbeitsbaum, mit zwei unabhängigen
Skripten: einem eigenen CG (Abbruch wie `linalg/pcg.py`, dazu Ritzwerte und die Lage des Ritzvektors zum
kleinsten Ritzwert, als Energieanteile je Zelle nach Werkstoffanteil) und dem Produktweg
`FcmProblem.loesen` als Gegenprobe. Die Iterationszahlen beider Skripte müssen übereinstimmen, sonst gilt
die Messung nicht. Verglichen werden der bisherige Glätter und der gewichtete additive Schwarz-Glätter
W M⁻¹ W mit W = diag(1/√Vielfachheit) (Schalter `glaetter_gewicht`, Vorgabe aus). Der gewichtete Glätter
wird zur Vorgabe, wenn er bei h 10 und h 8 jeweils alle fünf Lagen in ±20 % um den Mittelwert bringt oder
die größte Abweichung mindestens halbiert, keine Lage um mehr als zwei Iterationen verschlechtert, K_t auf
0,2 % gleich lässt und die Lösezeit um höchstens 5 % erhöht. Trifft das nicht zu, entscheidet die Lage des
langsamen Ritzvektors über die nächste Maßnahme: sitzt seine Energie in Zellen knapp über der
Aggregationsschwelle, ist das ein Fall für die Stabilisierung (Ghost Penalty oder Aggregation), verteilt
sie sich über das Gebiet, ist es eine Frage des Glätters.

**Ergebnis A5 (30.09.2026, Messcommit b0a08a8, beide Skripte mit gleichen Iterationszahlen in allen 20
Fällen):** Der gewichtete Schwarz-Glätter fällt nach der Regel durch (h 10, Versatz 0: 29 → 230 Iterationen,
λ_max der feinsten Ebene 33 → 394). Die langsamen Moden sitzen an den langsamsten Lagen nicht an der
Aggregationsschwelle, sondern im Oktree-Übergang am Loch (volle Zellen) und in den halb gefüllten
Zellschichten der dünnen Scheibe; es ist also eine Frage des Glätters. Ein breiteres Chebyshev-Fenster
[λ_max/100, λ_max] senkt Iterationen und Lösezeit an allen Lagen um 20 bis 25 % bei gleichen Spannungen und
ist Standard geworden. Die relative Streuung bleibt aber bei −25 bis +29 %, weil das Fenster alle Lagen im
selben Verhältnis verkürzt. Das Ziel ±20 % ist nicht erreicht; ob es gilt oder durch „stabil unter 100
Iterationen“ der Vorgabe ersetzt wird, entscheidet der Anwender (Alternative: Glätterblöcke über die Dicke
bzw. um Knoten, ein eigener größerer Schritt).

**Entscheidung A5 (Anwender, 30.09.2026):** Die Vorgabe (stabile Iterationszahl unter 100) gilt als erfüllt, das
selbst gesetzte Ziel ±20 % entfällt. Glätterblöcke über die Dicke werden nicht gebaut; die Streuung wird am
echten Knotenblech (C1) noch einmal angesehen.

### A6: Leistungsabnahme und Löserwahl neu messen
- 10⁶ Freiheitsgrade unter 60 s (Vorgabe 13) am Block; Schlussmessung der 23 Fälle wiederholen, dazu
  p 2 und p 4. `_AUTO_MEHRGITTER` nur einschalten und die Schwelle nur setzen, wenn die Messung es trägt.
- Prüfung: Tabelle in Theorie 11.10, Verlustrechnung per Skript aus dem Protokoll.

**Vorgehen und Regeln, vor der Messung festgelegt (30.09.2026):**

*Messstand.* Fester Arbeitsbaum (`git worktree`) auf dem Commit dieses Planabschnitts, Etikett mit Commit; je
Fall ein Prozess, nacheinander, Prozessliste vorher leer, Hauptsitzung vorher benachrichtigt. „Gesamt“ heißt
wie am 29.09. Aufbau plus Lösen ohne den Konstruktor des Problems; der Konstruktor wird getrennt ausgewiesen.

*Serien.* (S) Die 23 Fälle der Schlussmessung vom 29.09. (Block h 25/20/16/14 mit Versatz 0 und 0,3; Kirsch
h 14/12/10/9/8 mit Versatz 0/0,3/0,6), p 3, Direktlöser und GPU-Mehrgitter, Toleranz 1e-12. (G) Grade: p 2
und p 4 an vier Fällen (Kirsch h 12 und h 9 mit Versatz 0,3, Block h 20 mit Versatz 0 und h 16 mit Versatz
0,3), beide Wege. (M) Eine Million Freiheitsgrade: Block h 9 (967 992 Freiheitsgrade, p 3), beide Wege, dazu
Kirsch h 5,5 (1 002 528 Freiheitsgrade), ebenfalls beide Wege (am 30.09. lag der Direktlöser dort bei 27 GB und
36 s; ob das im Gesamtweg unter dem Mehrgitter liegt, zeigt die Serie).

*Zwei Skripte.* Skript 1 (`a1_skript1`): Gesamtzeiten mit `perf_counter` und den eingebauten Zeitwerten des
Protokolls. Skript 2 (`a1_skript2`): Zeitmesser von außen um die Funktionen des Aufbaus, ohne eingebaute
Zeitwerte zu lesen, Zeitbaum; läuft an sechs Fällen (Kirsch h 10 Versatz 0,3 und Block h 14 Versatz 0,3 je beide
Wege, Block h 9 nur Mehrgitter, Kirsch h 5,5 nur Mehrgitter). Weichen beide in Aufbau oder Lösen um mehr als
10 % ab, gilt der Fall nicht und wird wiederholt. Verschiebungs- und Spannungswerte beider Wege müssen je Fall
auf 1e-9 übereinstimmen (Kontrollwert σ_x).

*Regel R1 (Löserwahl `auto`).* Das Mehrgitter wird für `auto` eingeschaltet, wenn es in Serie S (Gesamtzeit)
oberhalb einer Schwelle N0 im Mittel mindestens 10 % schneller ist als der Direktlöser und in keinem Fall
langsamer als das 1,05-fache. N0 ist die kleinste Zahl aller Freiheitsgrade eines Falls (die Größe, nach der
`auto` wählt), für die das für alle größeren Fälle der Serie gilt. Gibt es kein N0 unterhalb des größten Falls
der Serie, bleibt `auto` beim Direktlöser. Der Hauptspeicher des Direktlösers (am Block h 9 46 GB) geht als
Zahl in den Bericht ein, entscheidet aber nicht, weil er von der Rechnerausstattung abhängt.

*Regel R2 (Grade).* `_AUTO_GRADE` wird nur dann um p 2 oder p 4 erweitert, wenn R1 einschaltet und Serie G für
dieses p dieselbe Bedingung an allen vier Fällen erfüllt.

*Regel R3 (Leistungskriterium Vorgabe 13: 10⁶ Freiheitsgrade, Lösung unter 60 s).* Zwei Lesarten, beide
berichtet: (a) das Lösen allein, (b) der Gesamtweg Aufbau plus Lösen. Die Lesart (b) zählt das Einrichten
einmal je Bauteil; jeder weitere Lastfall kostet nur das Lösen. Erfüllt ist das Kriterium, wenn (a) unter
60 s liegt und (b) angegeben ist; liegt (b) darüber, geht die Zahl mit der Verlustrechnung an den Anwender.

*Verlustrechnung.* Per Skript aus Protokoll (Skript 1) und Zeitbaum (Skript 2): Zeit je Posten (Gitter,
Quadratur, Zelldaten, Nitsche, Einrichten des Mehrgitters mit Blöcken, Lösen) und Anteil an der Gesamtzeit für
Mehrgitter gegen Direktlöser; der Abstand beider Wege wird den Posten zugeordnet.

## Phase B – Teilprojekt 5 (Vorgabe 3, 6 Stufe 2, 11)

### B1: Moment Fitting für Schnittzellen
- Je Schnittzelle ein angepasster Satz von etwa (p+1)³ Punkten, dessen Gewichte die Momente der
  Werkstoffdomäne exakt treffen; Referenzmomente aus der bestehenden ebenen-exakten Integration.
  Nicht-negative Gewichte (NNLS), Rückfall auf die bestehende Quadratur bei schlechter Kondition,
  Volumenprüfung je Zelle (Vorgabe 6). Zu prüfen ist dabei auch, ob die Konsistenz von Volumen und Rand auf
  gekrümmten Flächen besser wird (lineares Feld auf der Kirsch-Geometrie heute 10⁻³ daneben).
- Ziel: Quadraturpunkte mindestens um den Faktor 5 weniger bei gleicher Genauigkeit.
- Prüfung: Patch-Tests < 10⁻⁶, Lamé und Kirsch auf 0,1 % wie vorher, Punktzahl und Aufbauzeit im Protokoll.

**Vorgehen und Regeln, vor der Messung festgelegt (30.09.2026):**

*Verfahren.* Neues Modul `fcm/momentfitting.py`; `Zellquadratur(momentfitting=..., fit_grad=q)`. Je Schnittzelle
liefert die bisherige ebenen-exakte Integration die Referenzpunkte; daraus die Momente der Werkstoffdomäne in der
Tensor-Legendre-Basis vom Grad q je Richtung (die 1D-Basis aus `fcm/basis.py`, sie spannt dieselben Polynome auf wie
die Monome). Die gefittete Regel liegt auf den Tensor-Gauß-Punkten (q+1)³ der Zelle; ihre Gewichte lösen das
Momentensystem exakt, und weil Punkte und Basis Tensorprodukte sind, zerfällt es in drei eindimensionale Lösungen
(Kronecker-Struktur, gut konditioniert). Die fiktiven α-Punkte bleiben wie bisher (Tensor-Gauß (p+1)³ mit α).
Wählt man q = 2p, sind alle Integranden der Zellsteifigkeit (Grad ≤ 2p je Richtung) mit der Regel exakt
integriert, die Zellmatrix ist bis auf Rundung die der Referenz, und negative Gewichte können ihr nichts anhaben;
für q < 2p ist das nicht gesichert. Negative Gewichte: bei q ≥ 2p werden sie hingenommen; sonst gilt eine Zelle als
schlecht gefittet, wenn die negative Gewichtsmasse 1 % der positiven übersteigt – dann NNLS auf den Gauß-Punkten
(q+2)³, und bleibt ein Residuum über 10⁻¹⁰ (relativ), fällt die Zelle auf die Referenzquadratur zurück. Die Statistik
zählt gefittet / NNLS / Rückfall, das kleinste Gewicht, die negative Gewichtsmasse und die Punkte je Schnittzelle
vorher und nachher. Der Schalter bleibt, weil plastische Körper nach Vertrag 6a die Unterteilung brauchen.

*Messung.* q ∈ {p, p+1, p+2, 2p} an Patch (p 2 und 3), Lamé (p 2 und 3), Kirsch h 20 p 3 verfeinert (Versatz 0 und
0,4), Kragarmsegment; Größen: Abweichung der Spannungen gegen die Referenzquadratur, K_t, Punkte je Schnittzelle,
kleinster Eigenwert der Zellmatrizen, später (freie Maschine) die Zeit für Zelldaten und Assemblierung an Kirsch h 10
und Block h 14. Dazu das lineare Feld auf der gekrümmten Kirsch-Geometrie vorher und nachher; Erwartung: unverändert,
weil die Momente aus derselben Integration stammen wie bisher (dann steht das so im Handbuch).

*Regel.* Vorgabe wird das kleinste q, bei dem die Patch-Tests unter 10⁻⁶ bleiben, Lamé- und Kirsch-Spannungen um
höchstens 0,1 % von der Referenzquadratur abweichen und alle Zellmatrizen positiv semidefinit bleiben (kleinster
Eigenwert ≥ −10⁻¹⁰ des größten). Die Punktzahl je Schnittzelle muss dabei mindestens um den Faktor 5 sinken; sonst
bleibt die Referenzquadratur Standard und das Fitting ein Schalter.

**Ergebnis B1 (30.09.2026, Theorie 11.11):** q = 2p ist die Vorgabe des Fits: Zellmatrizen wie die Referenz auf
2·10⁻¹³, Patch-Tests, Lamé und K_t unverändert, keine Rückfälle; q < 2p liefert indefinite Zellmatrizen und Fehler
bis 10⁻³ und ist damit aus. Punkte je Schnittzelle: Lamé 22- bis 34-fach, Kirsch 17- bis 19-fach weniger, ebener
Patch nur 2,6- bis 4,2-fach (Referenz dort schon billig), achsparallel unverändert (Fitting nur, wo es spart). Die
Regel „Faktor 5 an allen Fällen“ ist damit an den gekrümmten Geometrien übertroffen und am Patch verfehlt: nach
der Regel bleibt die Referenz Standard (`MOMENTFITTING_STANDARD = False`), der Anwender entscheidet über die
Vorgabe. Zeiten der Zellmatrizen an Kirsch h 10 und Block h 14 folgen auf freier Maschine. Nebenbefund behoben:
Wurzelwahl der Aggregation hing an der Rundung des Werkstoffanteils (Test in test_zwaenge).

**Entscheidung B1 (Anwender, 30.09.2026):** „fitting einschalten“ – `MOMENTFITTING_STANDARD = True`.

### B2: Spannungsrückgewinnung (Vorgabe 11.1)
- Superconvergent Patch Recovery oder L²-Projektion der Spannungen, ausgewertet an den Oberflächenpunkten.
- Prüfung: Patch-Test exakt; Kirsch und Lamé an der Oberfläche näher an der Referenz als der Rohwert.

**Vorgehen und Regeln, vor der Messung festgelegt (30.09.2026):**

*Verfahren.* Globale L²-Projektion der sechs Spannungskomponenten auf den stetigen skalaren Ansatzraum vom Grad p
derselben Zellen, mit derselben skalaren Zwangsmatrix wie die Verschiebungen (hängende Moden und Aggregation;
C ist komponentenweise gleich, die skalare Fassung ist C[0::3, 0::3]): M X = B mit M = Cᵀ(Σ ∫ Nᵀ N dΩ)C über die
Zellquadratur (Werkstoff- und α-Punkte, wie die Steifigkeit) und B = Cᵀ Σ ∫ Nᵀ σ_h dΩ. M wird einmal je Problem
faktorisiert (Direktlöser), jeder Lastfall kostet nur rechte Seiten. SPR wird nicht gebaut: Patches um Knoten
vertragen sich schlecht mit Schnittzellen, hängenden Moden und Aggregation; die L²-Projektion erbt alle drei.
Neues Modul `postprocess/rueckgewinnung.py`, `Auswertung.spannung(P, geglaettet=...)`.

*Messung (FcmProblem-Ebene, Direktlöser, Auswertepunkte auf der echten Oberfläche wie im Vertragsweg: die Punkte
der Flächenquadratur, 1e-7·h nach innen gerückt).* (1) Patch p 2 und p 3: Spannungen gegen die exakten. (2) Lamé
p 2 und p 3, h 20 und h 10: σ_r, σ_φ, σ_z gegen Lamé an allen Oberflächenpunkten, größter und mittlerer Fehler
bezogen auf p_i. (3) Kirsch p 3 verfeinert, h 20 mit Versatz 0 und 0,4: K_t am Lochrand, Streuung über die beiden
Lagen, und das Randresiduum |σ·n| auf den freien Flächen (Loch, freie Längsseite, Ober- und Unterseite) bezogen auf
S₀ – die Rückgewinnung soll die Randbedingung nicht verschlechtern. (4) Kragarmsegment p 3 reine Biegung: σ_x an
der Oberfläche gegen Balkentheorie. Dazu Zeit für Aufbau und Faktorisierung von M und je Lastfall.

*Regel.* Die Rückgewinnung wird der Vorgabewert für die Oberflächenspannungen des Vertragswegs (`DetailResult.stress`),
wenn (a) die Patch-Tests unter 10⁻⁶ bleiben, (b) an allen vier Lamé-Fällen der größte Oberflächenfehler kleiner
ist als roh, (c) K_t an beiden Kirsch-Lagen sich um höchstens 0,5 % vom Rohwert unterscheidet und das mittlere
Randresiduum nicht größer ist als roh, (d) die reine Biegung auf 10⁻⁶ exakt bleibt. Sonst bleibt der Rohwert
Vorgabe und die Rückgewinnung ein Schalter; das Protokoll nennt in jedem Fall, welche Spannung ausgegeben wird.

**Ergebnis B2 (30.09.2026, Theorie 11.12):** alle vier Punkte erfüllt – Patch und reine Biegung exakt, Lamé an allen
vier Fällen besser als roh (größter Fehler 15,2 statt 56,6 %, 5,24 statt 5,27 %, 5,36 statt 5,51 %, 2,23 statt 2,29 %),
K_t um 0,41 und 0,22 % verschoben, Randresiduum im Mittel 17 bis 20 % kleiner. Die L²-Projektion ist Ausgabe des
Vertragswegs. Kosten an großen Modellen folgen auf freier Maschine.

### B3: Hot-Spot nach IIW Typ a (Vorgabe 11.2)
- Referenzpunkte im Abstand 0,4·t und 1,0·t vom Nahtübergang, senkrecht zur Naht auf der Blechoberfläche,
  lineare Extrapolation, maßgebende Komponente senkrecht zur Naht; Richtung aus Oberflächennormale und
  Nahttangente, Seite ohne Nahtwulst aus der Geometrie. `HotSpotResult` je Nahtpunkt füllen.
- Prüfung: lineares Spannungsfeld wird exakt extrapoliert; Blech mit Kehlnaht unter Zug gegen die
  Handrechnung. Ist die Seite geometrisch nicht eindeutig, Vertragsvorschlag für eine Richtungsangabe.

**Vorgehen und Regeln, vor der Messung festgelegt (30.09.2026):**

*Verfahren* (`postprocess/hotspot.py`). Je Punkt der Nahtpolylinie: Tangente aus den Nachbarpunkten; in der Ebene
senkrecht dazu ein Kreis vom Radius 0,05·t um den Nahtübergang, auf dem die Vorzeichenwechsel des Geometrieabstands
die beiden Oberflächenäste liefern (Blech und Nahtoberfläche; andere Anzahl → Warnung, kein Wert). Blechseite ist
der Ast, unter dem die Werkstofftiefe längs der Innennormalen bei 0,7·t vom Übergang gleich der Blechdicke t ist
(auf 20 %), während sie es beim anderen Ast nicht ist; sonst Warnung „Blechseite nicht eindeutig“, kein Wert, und
für diesen Fall ein Vertragsvorschlag für eine Richtungsangabe. Referenzpunkte bei 0,4·t und 1,0·t längs des
Blechastes, auf die Oberfläche projiziert; maßgebend ist σ_⊥ = d·σ·d mit d der Richtung auf dem Blech senkrecht zur
Naht, aus der Spannung, die der Vertragsweg ausgibt (geglättet nach B2); σ_hs = 5/3·σ(0,4t) − 2/3·σ(1,0t) (die
Beiwerte 1,67 und 0,67 der IIW sind diese Brüche gerundet). `method = "effective_notch"` wird mit Warnung
übergangen (Kerbspannung ist nicht Teil von B3).

*Prüfungen.* (1) Synthetisches lineares Spannungsfeld auf einem T-Stoß (Grundblech t 10, Querblech, beidseitige
Kehlnähte): σ_hs gleich σ_⊥ am Übergang auf 10⁻¹², Blechseite an allen Punkten beider Nahtübergänge richtig.
(2) Finite Zellen mit exakt darstellbarem quadratischem Verschiebungsfeld (σ_xx linear in x, konstante
Volumenkraft, Dirichlet überall), p 3: σ_hs gleich σ_⊥ am Übergang auf 10⁻⁶, roh und geglättet. (3) T-Stoß unter
Zug σ_n = 100 N/mm² (nicht tragende Nähte): Handrechnung σ_n = F/(b·t); geprüft wird, dass die Oberflächenspannung
fern der Naht σ_n auf 1 % trifft, σ_hs zwischen σ_n und 1,5·σ_n liegt und sich zwischen h und h/2 um weniger als
3 % ändert; zum Vergleich (ohne Kriterium) die über die Dicke linearisierte Strukturspannung im Nahtübergangsschnitt.
(4) Vertragsweg: `DetailResult.hot_spots` je Nahtpunkt gefüllt, Protokoll nennt Verfahren und Spannungsart.

**Ergebnis B3 (30.09.2026, Theorie 11.13, Zweig feature/volumen3d-b3):** (1), (2) und (4) erfüllt (synthetisch 2·10⁻¹⁶,
exaktes Feld 1,6·10⁻⁷, Vertragsweg mit Warnungen). (3): Fernfeld 0,05 %, Konvergenz h 10 → h 5 1,3 % erfüllt; die Spanne
σ_n ≤ σ_hs ≤ 1,5·σ_n verfehlt (h 10: 98,75 bis 101,92 N/mm²). Die Linearisierung über die Dicke (93–97 N/mm²) zeigt eine
örtliche Entlastung der Oberseite durch das einseitige Querblech; die Annahme der Regel war falsch, ein unabhängiger
Beleg des Absolutwerts fehlt. Entscheidung des Anwenders offen. Befund während B3 behoben: verschachtelte CSG-Bäume
fielen auf den Punkttest zurück (siehe Theorie 11.13). Die Prüfung (3) mit h 5 dauert 25 Minuten und muss vor dem Merge
kleiner werden.

**Entscheidung B3 (Anwender, 30.09.2026):** Empfehlung angenommen – Spanne 0,95 bis 1,5·σ_n mit der Begründung aus der
Linearisierung, Absolutwert in C1 gegen die Tet10-Referenz des Hauptprogramms. Die Prüfung rechnet h 10; die Konvergenz
h 10 → h 5 läuft nur mit `VOLUMEN3D_LANG=1`.

### B4: Konvergenzkurve und Protokoll (Vorgabe 11.3)
- `DetailResult.convergence` je Zyklus (Hot-Spot und Maximalspannung über Freiheitsgrade), Zyklen aus
  `FcmSettings.adaptive_cycles` als p-Erhöhung und h-Halbierung in Nahtnähe (ohne Fehlerschätzer, der kommt
  in TP 6); Protokoll aller Einstellungen (p, Verfeinerung, α, Toleranz, Kopplungsart, Löserweg).
- Prüfung: Kurve fällt monoton gegen den Grenzwert am Knotenblech-Vorversuch; Protokoll vollständig.

**Vorgehen und Regeln, vor der Messung festgelegt (30.09.2026):**

*Zyklen.* `adaptive_cycles = N` (0 bis 4, Vorgabe 8.4 nennt 2 bis 4): Zyklus 0 ist die Rechnung der Einstellungen, jeder
weitere ändert genau eine Sache, damit der Schritt an der Kurve ablesbar bleibt. Ungerade Zyklen: lokale
h-Halbierung – um Punkte der Nahtlinien im Abstand höchstens t (Kugeln vom Radius 2·t) wird die Zielzellgröße gegenüber
dem Vorzyklus halbiert. Gerade Zyklen: p + 1 bis p = 4, danach h-Halbierung. Ohne Naht (keine Stelle für die lokale
Verfeinerung) nur p + 1; ist p = 4 erreicht, endet die Folge mit Warnung. Das Ergebnis des Vertragswegs ist der letzte
Zyklus. Fehlerschätzer und Auswahl der Zellen bleiben TP 6.

*Kurve.* Je Zyklus ein Eintrag in `DetailResult.convergence`: `cycle`, `step` (Start, h-Halbierung Naht,
p-Erhöhung), `dofs`, `p`, `cells`, `cut_cells`, `h_min_mm`, `hotspot_max`, `hotspot_mean`, `stress_max` (größte
Von-Mises-Spannung an den Oberflächenpunkten – an scharfen Kerben nicht konvergent, deshalb kein Kriterium),
`solver_path`, `iterations`, `t_s`, `hotspot_change` (relativ zum Vorzyklus). Die Kurve über Freiheitsgrade ist Pflicht
jedes Detailnachweises (Vorgabe 11.3).

*Konvergenzaussage* (`protocol["convergence_statement"]`, aus `hotspot_max`; kein Raten): bei weniger als drei Werten
„zu wenige Zyklen“; sonst mit Δ_k = σ_k − σ_{k−1}: „monoton konvergent“, wenn alle Δ_k dasselbe Vorzeichen haben und
|Δ_{k+1}| < |Δ_k| – dann der Grenzwert nach Aitken σ_∞ = σ_n + Δ_n·r/(1 − r) mit r = Δ_n/Δ_{n−1} und die Restabweichung
|σ_n − σ_∞|/σ_∞; andernfalls „nicht monoton, keine Konvergenzaussage“ mit den Werten. Das „fällt“ der Planzeile
lese ich als „konvergiert monoton“: der Hot-Spot an einem Blech mit Naht kann von unten wie von oben gegen den Grenzwert
laufen (T-Stoß: h 10 → h 5 von 100,43 auf 100,93 N/mm²).

*Protokoll.* `protocol["settings"]` enthält: p, Zellgröße, Verfeinerungsbereiche, α, Toleranz des Vertrags und die
verwendete, Kopplungsart, angeforderter und benutzter Rechenweg mit Löserweg, Moment Fitting (Grad), Spannungsart,
Aggregationsschwelle, Zyklenzahl, Nähte (Kennung, Punkte, Blechdicke, Verfahren), Vertrags- und Paketversion.

*Prüfungen.* (1) Kernsuite, Kragarm-Ausschnitt ohne Naht mit `adaptive_cycles = 2`: drei Einträge, p 2 → 3 → 4, Freiheitsgrade
wachsend, Protokoll vollständig. (2) T-Stoß unter Zug (Geber mit gleichmäßigem Zug, Schnittebenen an den Enden),
Basiszellgröße 20, p 2, drei Zyklen (h-Halbierung, p + 1, h-Halbierung): `hotspot_max` monoton konvergent im Sinn der
Aussage, letzte Änderung unter 3 %, Kopplungskontrolle Kraft unter 5 %; das „Knotenblech-Vorversuch“ der Planzeile ist
dieser T-Stoß, das Knotenblech selbst kommt in C1. (3) Fehlerfälle: `adaptive_cycles` außerhalb 0 bis 4 →
`SolverError`; Abbruch zwischen den Zyklen meldet `SolverCancelled`.

**Ergebnis B4 (30.09.2026, Theorie 11.14):** Zyklen, Kurve, Protokoll der Einstellungen und Konvergenzaussage gebaut und geprüft
(Kernsuite 268/268, `test_adaptiv` 9/9), Fortschritt und Abbruch zwischen den Zyklen, Grenzen der Zyklenzahl. **Die Konvergenzforderung ist nicht
erfüllt:** am T-Stoß 81,1 → 119,0 → 134,2 → 91,0 N/mm² (nicht monoton), mit vier Zyklen und mit feinerem Start ebenso; die Referenzpunkte
bei 0,4 t liegen bei Zellen von 5 bis 20 mm in der ersten Zellschicht an der Kerbe. Empfehlung „h zuerst bis t/4, dann p + 1“ mit Messung am
Knotenblech in C1; Entscheidung beim Anwender. Befund während B4 behoben: Zwangszyklus in der Aggregation (unverwurzelte grobe schlechte Zelle
mit feineren verwurzelten Nachbarn); an den 23 Modellen der schweren Suiten sperrt sie höchstens zwei Moden, dort bitgleich. Offen: Konsistenzfehler 10⁻⁶ bis 10⁻⁴ am T-Stoß mit lokaler
Verfeinerung (Ursache teilweise geklärt).

**Entscheidung B4 (Anwender, 01.10.2026):** „zuerst lokal h bis t/4, dann p + 1, Messung am Knotenblech in C1“ – die
Empfehlung ist angenommen. **Neuer Fahrplan** (ersetzt den abwechselnden): Jeder Zyklus ändert genau eine Sache, aber zuerst nur h:
die Zielzellgröße an der Naht i ist im Zyklus k gleich max(h₀/2ᵏ, tᵢ/4) mit h₀ der Basiszellgröße und tᵢ der Blechdicke der Naht
(Referenzpunkt 0,4·t liegt dann mindestens 1,6 Zellen vom Übergang); gehalbiert wird, solange es eine Naht gibt, deren Zielgröße
noch über tᵢ/4 liegt. Danach folgt p + 1 bis p = 4, danach endet die Folge mit Warnung. Ohne Naht nur p + 1. Das Maximum von
vier Zyklen bleibt. Geprüft wird der Fahrplan als reine Funktion (Schritte, Zielgrößen, Ende) und der Vertragsweg an einem Modell, dessen
Basiszellgröße schon bei t/2 liegt; die Konvergenz selbst misst C1 am Knotenblech.

**Ergebnis B4 mit dem neuen Fahrplan (01.10.2026, Theorie 11.14):** Zyklen h(5) h(2,5) p3 p4 am T-Stoß: 119,8 – 127,6 – 111,0 – 107,4 – 107,9 N/mm², letzte Änderung 0,45 %; die
Aussage bleibt wegen der groben Anfangsschritte „nicht monoton“ (Vorschlag: Aussage über die p-Phase bei fester Zellgröße, Entscheidung beim Anwender).

### B5: STEP über gmsh-Tessellierung (Vorgabe 3)
- Optionales Extra `step` mit gmsh; `GeometrySourceType.STEP` → Tessellierung → bestehender STL-Weg;
  ohne gmsh `SolverError` mit Hinweis. Die neue optionale Abhängigkeit im Pull Request benennen.
- Prüfung: Würfel mit Bohrung als STEP gegen CSG (Volumen, K_t); Test überspringt ohne gmsh.

**Vorgehen und Ergebnis B5 (01.10.2026, Theorie 11.15):** `geometry/step.py`, Extra `step`; Prüfungen: Tessellierung des Blocks mit Bohrung gegen die Formel
(N 60 +0,019 %, N 120 +0,0047 %, wasserdicht, Orientierung, Einheit), STEP-Quader durch den Vertragsweg gleich CSG (Volumen exakt, σ 1,3·10⁻¹⁰), Fehlerfälle,
Integrationswarnung; ohne gmsh übersprungen. **Die Planprüfung „Würfel mit Bohrung als STEP gegen CSG (Volumen, K_t)“ ist nicht erfüllt:** gekrümmte, unstrukturiert
tessellierte STEP-Flächen laufen im STL-Weg in Minuten bis Stunden (N 16: 206 s gegen 4,6 s CSG bei feineren Zellen) und in erster Ordnung, weil die lokale Lage der gmsh-Netze „gemischt“ ist.
Das Volumen der Tessellierung selbst stimmt; K_t steht aus. Vorschlag: Integration über die Dreiecke (Divergenzsatz), zusammen mit B6; Entscheidung beim Anwender.
Die neue optionale Abhängigkeit (gmsh ≥ 4.11, GPL, Extra `step`) steht im Pull Request einzeln.

### B6: Schneller Windungszahl-Baum (Rest aus TP 2)
- Näherung nach Barill u. a. 2018 (Dipole je BVH-Knoten) für STL-Netze über 10⁵ Facetten.
- Prüfung: dieselbe Innen/Außen-Entscheidung wie exakt an 10⁵ Zufallspunkten, mindestens zehnmal schneller
  bei 10⁶ Facetten.

**Entscheidung B5 (Anwender, 01.10.2026):** Empfehlung angenommen – die Integration tessellierter Hüllen läuft über die
Dreiecke selbst, zusammen mit B6 als ein Schritt (Fable 5.1, sehr hoch). Die Aussage der Konvergenzkurve über die p-Phase
(Vorschlag aus B4) ist damit nicht entschieden und bleibt offen.

**Vorgehen und Regeln B6, vor der Messung festgelegt (01.10.2026):**

*Teil 1, exakte Integration tessellierter Hüllen (`geometry/huelle.py`).* Für eine Zelle B = [lo, hi] (achsparallel) und eine
geschlossene, nach außen orientierte Hülle Ω gilt mit G = (∫_{x_lo}^{x} g χ_B dx', 0, 0) für polynomiales g

    ∫_{Ω∩B} g dV = Σ_Dreiecke ∫_T G_x n_x dA,

weil G_x in x stetig ist und die Sprünge von G über die Ebenen y = const, z = const keinen Fluss haben (Normale senkrecht zu G).
Je Dreieck genügen also das Clippen an den y- und z-Scheiben der Zelle und das Teilen bei x_lo und x_hi (Teile mit x < x_lo
tragen null, mit x > x_hi den vollen x-Integralwert) – alles exakte Polygonoperationen, keine Zerlegung an lokalen Ebenen, kein
Punkttest. Die Momente der Tensor-Legendre-Basis vom Grad q = 2p folgen so in geschlossener Form (Stammfunktionen der
hierarchischen 1D-Basis über die Legendre-Rekursion), und das Moment Fitting aus B1 liefert daraus die Zellregel. Gilt für
Zellen, in denen genau eine aktive Grundform eine Hülle (STL oder STEP) ist und die übrigen Formen die Zelle ganz enthalten
oder ganz ausschließen (eine kleine Boolesche Auswertung des CSG-Baums über {leer, voll, Form, Komplement}); ist das Ergebnis
das Komplement der Hülle (Hülle als Loch), sind die Momente Box minus Hülle. Zellen, in denen die Hülle eine andere aktive
Form trifft (Schnittebenen, Symmetrieebenen), behalten vorerst den bisherigen Weg; wie viel Zeit sie kosten, wird gemessen
(Teil 3 entscheidet). Flächenquadratur: ein Polygon auf einer Hüllenfacette wird nur noch von den **anderen** Formen geclippt,
die eigenen lokalen Ebenen der Hülle entfallen (`lokale_stuecke(..., ohne=form)`).

*Teil 2, schneller Windungszahl-Baum (`geometry/windung.py`).* Nach Barill, Dickson, Schmidt, Levin, Jacobson 2018 („Fast Winding
Numbers for Soups and Clouds“): je Knoten der vorhandenen BVH (`geometry/dreiecksbaum.py`) der flächengewichtete Normalenvektor, der
flächengewichtete Schwerpunkt und die Momente zweiter Ordnung; ein Knoten, dessen Abstand zum Punkt mehr als β = 2 seiner
Umkugel beträgt, wird durch die Taylor-Näherung zweiter Ordnung ersetzt, sonst abgestiegen, Blätter exakt (Van Oosterom und
Strackee). Nur wenn die Hülle mehr als 20 000 Facetten hat (darunter ist die exakte Summe mit numba schnell genug) und nur für die
Innen/Außen-Entscheidung des Abstands; die Facettenprüfung der Hülle (Defekt) rechnet weiter exakt.

*Teil 3 (nur wenn Teil 1 die Zellen an Schnittebenen nicht abdeckt und sie die Zeit bestimmen).* Ebenenbereiche innerhalb der Hülle
über den Divergenzsatz eine Dimension tiefer: die Schnittsegmente Dreieck ∩ Ebene bilden geschlossene Schleifen, die 2D-Scheibenformel
gibt die Flächenmomente des Ebenenpolygons innerhalb der Hülle, Randkanten liefern 1D-Intervalle über Segment-Dreieck-Schnitte.

*Prüfungen.* (1) Polyeder mit geschlossener Form als Hülle (Würfel, gedrehter Würfel, L-Prisma, Hülle gleich Zellbox): Volumen und
alle Tensor-Momente bis Grad 6 gegen die exakte Integration (Zerlegung in Tetraeder) auf 10⁻¹²; Stammfunktionen der 1D-Basis gegen
Gauß-Integration auf 10⁻¹⁴. (2) Bestehende STL-Suite (Lamé aus STL, Würfel, L-Körper) unverändert grün, Lamé aus STL schneller.
(3) Block mit Bohrung als STEP (N 120, 27 788 Dreiecke) durch `FcmProblem`: Konstruktor unter 30 s bei h 25 (CSG 4,6 s), keine
Punkttest-Blätter in Zellen, die nur die Hülle schneidet, Werkstoffvolumen gleich dem Volumen der Tessellierung auf 10⁻¹⁰; durch
den Vertragsweg gegen CSG: K_t auf 0,5 % (die offene Planprüfung aus B5). (4) Windungszahl: an 10⁵ Zufallspunkten um die
Tessellierung mit 107 636 Dreiecken (N 240) dieselbe Innen/Außen-Entscheidung wie exakt für alle Punkte, |Δw| < 10⁻³, mindestens
zehnmal schneller als die exakte numba-Summe. (5) Alle Suiten grün, mypy, lint-imports.

*Regel.* Die Hüllenintegration ersetzt für Hüllenformen die Zerlegung an lokalen Ebenen, wenn (1) bis (3) halten; der Windungszahl-Baum
wird Vorgabe ab 20 000 Facetten, wenn (4) hält; sonst bleiben beide Schalter mit Vorgabe aus.

**Ergebnis B6 (01.10.2026, Theorie 11.16):** (1) hält auf 10⁻¹⁵ (Stammfunktionen 3,3·10⁻¹⁶; Würfel, gedrehter Würfel, L-Prisma, Hülle gleich Zellbox ≤ 1,4·10⁻¹⁵).
(2) STL-Suite grün mit unveränderten Werten; Lamé aus STL 44 s statt 78 s, die Suite 48 s statt rund 3 min. (3) Block mit Bohrung N 120 bei h 25: Konstruktor 26,8 s (p 3; vorher 388 s),
alle 573 Schnittzellen Hüllenzellen ohne Punkttest, Volumen = Tessellierung auf 2,2·10⁻¹⁶; durch den Vertragsweg gegen CSG K_t 0,12 % (p 2) und 0,25 % (p 3).
(4) N 240, 107 636 Dreiecke, 100 000 Punkte: Innen/Außen-Entscheidung bei jedem β für alle Punkte gleich, Geschwindigkeit 28- bis 73-mal; die Schranke |Δw| < 10⁻³
hält mit dem im Plan genannten β 2 **nicht** (9,9·10⁻³), erst mit β 4 (2,6·10⁻⁴, 28-mal schneller) – Vorgabe darum β 4 (Anwender 01.10.2026: Empfehlung angenommen).
(5) Kernsuite 298/298, alle 21 Paketsuiten grün (darunter Lamé 7/7, Kirsch 8/8, Kragarm 15/15, Mehrgitter 26/26), mypy, lint-imports grün. Teil 3 nicht gebaut: die Zellen an den Schnittebenen des Blocks
treffen nur ebene Facetten, die Zeit steckt in der Oberflächenquadratur der Facetten (17 von 27 s), nicht in Ebenenzellen. Beide Schalter sind Vorgabe
(`HUELLEN_EXAKT_STANDARD`, `WINDUNG_BAUM_AB = 20 000`).

### B7: Schale → Volumen (nur Prüfung)
- Kopplung an ein Schalen-Globalmodell ist Sache des Providers im Hauptprogramm; hier nur ein Test mit einem
  Schalen-Provider-Stub über die Vertragsschicht.
- Prüfung: Schnittgrößenkontrolle < 1 % (Vorgabe 13, Kopplung).

**Vorgehen und Regeln B7, vor der Messung festgelegt (01.10.2026).** Der Provider ist ein Stub der Suite (`tests/test_schale.py`), kein Teil des
Pakets: ein Plattenstreifen (Dicke t = 10 mm, Breite b = 100 mm, Länge 200 mm zwischen den Schnittebenen) als Schalenmodell in lokalen Achsen
(x′ Länge, y′ Breite, z′ Normale, Mittelfläche z′ = 0), Reissner-Mindlin-Kinematik: `displacement_at` liefert Mittelflächenverschiebung u₀(x′, y′) plus
Rotation θ(x′, y′) mal Normalenabstand, also die lineare Verteilung über die Dicke (Vertrag Abschnitt 5, Vorgabe 10 Stufe 1); `section_forces` kommt
aus den Schalenresultierenden je Breite (n_x, m_x), über die Schnittbreite integriert, mit der Seitenkonvention des Vertrags (Kraft des abgeschnittenen
Teils auf das Detail, n aus dem Detail heraus). Zustand: Membrandehnung ε₀ und Krümmung κ in x′ bei freien Längsrändern (n_y = m_y = 0, also
Querkontraktion ε_y = −ν ε₀ und antiklastische Krümmung κ_y = −ν κ): u₀ = (ε₀ x′, −ν ε₀ y′, w) mit w = −κ (x′² − ν y′²)/2, θ = (ν κ y′, κ x′, 0);
Schalenresultierende n_x = E t ε₀, m_x = E t³ κ/12 je Breite, Spannung σ_x′ = E (ε₀ + κ z′). Die Dickendehnung der Schalentheorie fehlt dem Provider
bewusst (nur ein Starrkörperanteil der Querrichtung, keine Spannung): der Vertragsweg legt nur die Normalkomponente punktweise und die Mittelwerte der
Tangentialkomponenten fest.

*Fälle.* (A) Streifen achsparallel (CSG, Schnittebenen x 0 und 200); (B) derselbe Streifen um 30° um die y-Achse geneigt (STL-Hülle, schräge
Schnittebenen; prüft B6 und die schräge Kopplung zusammen). Je drei Lastfälle: Membran (σ_m = 100 N/mm², κ = 0), Biegung (Randspannung σ_b = 150 N/mm²,
ε₀ = 0) und beides. Zellgröße 25 mm, p = 2.

*Schranken.* (1) Schnittgrößenkontrolle des Vertragswegs (`coupling_check`) für Kraft und Moment je Ebene, Fall und Lastfall unter 1 % (Vorgabe 13,
Kopplung Stab → Volumen, hier für die Schale) und keine Kopplungswarnung; (2) σ_x′ (in lokalen Schalenachsen) an allen Oberflächenpunkten gleich
σ_m + σ_b z′/(t/2) auf 1 % des Größtwerts, alle anderen lokalen Komponenten unter 1 % des Größtwerts (die Felder liegen im Ansatzraum, erwartet sind
Rundung bis Konsistenzfehler der Schnittzellen; die Schranke ist die der Vorgabe, die gemessenen Werte werden berichtet); (3) die Resultierenden beider
Ebenen sind im Gleichgewicht (Σ Kraft und Σ Moment um den Streifenmittelpunkt unter 1e-6 des Bezugs).

*Befundregel.* Meldet die Kontrolle bei verschwindender Referenz (reine Biegung: Kraft 0, reine Membran: Moment um die Mittelfläche 0) eine Scheinabweichung,
ist das ein Fehler der Kontrolle, nicht des Verfahrens: er wird mit einem fehlschlagenden Test behoben und im Ergebnis genannt. Nicht Teil von B7: die
Kopplung an ein echtes Schalenmodell des Hauptprogramms (Provider dort), Querkraft mit Schubverformung (Timoshenko-Anteil im Kragarmtest erklärt) und
Verwölbung.

**Ergebnis B7 (01.10.2026, Theorie 11.17):** Schranke (1) hält mit zwei bis zehn Größenordnungen Abstand: Schnittgrößenabweichung Kraft/Moment höchstens 6,7·10⁻⁴ / 2,3·10⁻⁴ (geneigt 30°, p 2) bzw.
2,4·10⁻⁸ / 6,0·10⁻⁸ (p 3), achsparallel 2,1·10⁻¹² / 2,7·10⁻¹², keine Kopplungswarnung. Schranke (2) hält: σ_x′ gegen die Schalenverteilung ≤ 3,5·10⁻³ (10°, p 2), ≤ 5,3·10⁻⁷ (30°, p 3),
übrige Komponenten ≤ 1,3·10⁻³. Schranke (3) (Gleichgewicht 10⁻⁶, vorab geraten) hält achsparallel (1,9·10⁻¹¹) und bei p 3 (≤ 2,2·10⁻⁷), **nicht für p 2 am schrägen Schnitt (4,2·10⁻³)**: dort gilt die
Vorgabeschranke 1 %, Gleichgewichtsrest und Spannungsfehler verschwinden bei p 3 gemeinsam; Anwender 01.10.2026: Empfehlung angenommen (Vorgabeschranke 1 % für p 2 am schrägen Schnitt, Band 10⁻⁵ bei p 3).
**Befundregel angewendet:** (a) Kopplungskontrolle: reine Biegung meldete 100 % Kraftabweichung → gemeinsames Lastmaß für Kraft und Moment (`api._kopplungsabweichung`, Test); (b) Fehler aus B6 gefunden und
behoben: Hüllenfacetten hinter einer Schnittebene blieben als Oberfläche stehen (6 030 Punkte hinter der Ebene an der Kugelhülle; Test `test_flaeche_hinter_schnittebene`). Offen (nicht Teil von B7):
Konsistenzfehler des p-2-Ansatzes am schrägen Schnitt (Spannung 2,2·10⁻⁴ bis 3,5·10⁻³, Verschiebung 10⁻⁶; ohne Einfluss: α, Fitting, Flächenordnung, Tiefe; Einfluss: Aggregationsschwelle).

## Phase C – Abnahme und Abschluss

### C1: Knotenblech mit Kehlnaht (Abnahme TP 5)
- Modell aus CSG (Blech, Kehlnaht, Anschluss), Lasten über Schnittebene, Hot-Spot entlang der Naht,
  Konvergenzkurve. Referenzwerte nach E2, Ablage nach E3.
- Prüfung: Hot-Spot-Spannung gegen Tet10-Referenz < 3 % (Vorgabe 13).

**Modell und Regeln C1, vor der Messung festgelegt (01.10.2026).** Längssteife (Knotenblech) auf einem Zugblech, der klassische
IIW-Fall „nicht tragende Längsrippe“ mit Hot-Spot Typ a am Stirnnaht-Übergang. Alle Maße in mm, Werkstoff E 210 000, ν 0,3:

| Teil | Abmessung |
|---|---|
| Grundblech | x −5…205 (Schnittebenen x 0 und 200), y 0…80, z −10…0 (t = 10) |
| Knotenblech | x 70…130, y 36…44 (t_a = 8), z 0…40 |
| Kehlnaht rundum, Schenkel 6 (45°) | Pyramidenstumpf: Quader [64,136]×[30,50]×[0,6] ∩ {x + z ≤ 136} ∩ {−x + z ≤ −64} ∩ {y + z ≤ 50} ∩ {−y + z ≤ −30}; Ecken damit auf Gehrung |
| Nahtübergänge | Stirnnähte x = 136 und x = 64 (y 30…50), Längsnähte y = 30 und y = 50 (x 64…136), alle auf z = 0 |
| Nahtlinien (`WeldLine`) | „stirn_rechts“: (136, y, 0), „stirn_links“: (64, y, 0), y = 32, 34, …, 48; Blechdicke 10 |
| Last | Zug σ_n = 100 N/mm² (F = 80 kN auf 80 × 10) über die Schnittebenen: Geber u = (εx, −νε(y − 40), −νε(z + 5)), ε = σ_n/E, Schnittkraft ±80 kN |

Referenzpunkte nach IIW Typ a bei 0,4 t = 4 und 1,0 t = 10 mm vom Übergang auf der Blechoberseite senkrecht zur Naht, also (140, y, 0) und (146, y, 0) für
die rechte, (60, y, 0) und (54, y, 0) für die linke Stirnnaht; σ_hs = 5/3 σ_xx(0,4 t) − 2/3 σ_xx(1,0 t). Erwartung aus der Literatur (Niemi/Fricke, Längsrippe):
σ_hs/σ_n zwischen 1,2 und 1,6 – nur Plausibilität, keine Schranke.

*FCM-Seite* (`tests/test_knotenblech.py`, Vertragsweg): CSG wie oben, Basiszellgröße 10 (= t), p 2, `adaptive_cycles` 4 nach dem Fahrplan aus B4
(h 5, h 2,5 = t/4, p 3, p 4); je Zyklus σ_hs,max, σ_hs(y = 40), Freiheitsgrade, Zeit, Kopplungskontrolle; Konvergenzaussage. Zusätzlich derselbe Körper als
STEP-Hülle (B6) im letzten Zellstand als zweite Diskretisierung derselben Seite.

*Referenz* (Hauptprogramm nach E2, Tet10 von `statik3d/`): dasselbe Volumen, Netz mit Kantenlänge 1 mm (t/10) in 12 mm Umkreis der Nahtübergänge, 2,5 mm im
Blech, 5 mm fern; Randbedingungen wie der Vertragsweg: u_x = εx auf den Stirnflächen x 0 und x 200, Querbewegung frei bis auf die Starrkörperlagerung;
Auswertung σ_xx an den Blechoberflächenpunkten (140, y, 0), (146, y, 0), (60, y, 0), (54, y, 0) für y = 32…48 (Rohwerte liefern, nicht nur σ_hs), dazu die
Schnittkraft bei x 200, Knoten- und Elementzahl. Das Netz liefert Session B als Angebot aus gmsh (Tet10, `.inp`), die Hauptsitzung darf ihr eigenes nehmen.
Ablage nach E3 (`tests/reference_models/knotenblech_kehlnaht/`: Eingabe als JSON, Erwartungswerte, Toleranz) durch die Hauptsitzung; der Vorschlag mit der
vollständigen JSON liegt in `docs/vertrag-aenderungen/2026-10-01-referenzmodell-knotenblech.md`.

*Schranken.* (1) Abnahme: σ_hs(y = 40) des letzten Zyklus gegen die Tet10-Referenz unter 3 % (Vorgabe 13), an beiden Stirnnähten. (2) Symmetrie: rechte
und linke Stirnnaht im selben Zyklus auf 1 % gleich (Modell ist in x spiegelsymmetrisch). (3) Konvergenz: letzte Änderung der Kurve unter 3 % (Vorgabe 13,
Konvergenzkurve). (4) Kopplungskontrolle Kraft unter 5 %, keine Integrationswarnung. (5) Fern der Naht (x 180, Ober- und Unterseite) σ_xx = σ_n ± 1 %.
(6) Zwei unabhängige Auswertungen: σ_hs aus dem Hot-Spot-Modul (`DetailResult.hot_spots`) und aus einer eigenen Extrapolation der Oberflächenspannung
`DetailResult.stress` an den Referenzpunkten (Interpolation über die nächsten Oberflächenpunkte), Übereinstimmung auf 1 %; auf der Referenzseite dieselbe
Extrapolation aus den gelieferten Rohwerten.

*Befundregel.* Verfehlt (1) bei erfüllter (2)–(6), wird zuerst die Referenz mit halbiertem Netz an den Übergängen wiederholt (Netzkonvergenz der Referenz),
dann erst das Verfahren hinterfragt; Entscheidung beim Anwender. Solange die Referenz der Hauptsitzung fehlt, gilt ein eigener Tet10-Lauf des Hauptprogramms aus einem
festen Arbeitsbaum von `main` (nur lesend, über den Abaqus-Import des gmsh-Netzes) als **vorläufig** und wird im Protokoll so benannt.

**Ergebnis C1 (01.10.2026, Theorie 11.18):** (1) **hält** gegen die Tet10-Referenz der Hauptsitzung (Pull Request 13 auf main; gmsh-Netz 1 mm, 1,09 Mio. FHG, main 7da3571, zwei geeichte Auswertungen; Session B hatte denselben Lauf vorab mit identischem Ergebnis):
σ_hs(y = 40) FCM 143,23 / 138,94 gegen Tet10 142,74 / 143,14 N/mm², also +0,34 % rechts und −2,93 % links; rechts alle neun Punkte auf 0,4 %. Die Referenz selbst wanderte von
2,5 auf 1 mm um 3,6 % (Richardson-Grenzwert ≈ 141,7), und die Kantenlänge am Übergang ist im Median 1,33 mm statt der geforderten 1 mm (Befund der Hauptsitzung); der 0,5-mm-Lauf
(6,45 Mio. FHG, Netz liegt bereit, ~100 GB direkt) liegt beim Anwender. (2) **verfehlt**: rechts/links 3,1 % (Gitterphase: linker Übergang auf einer Zellgrenze, rechter 0,5 mm davor) – das ist die Schnittlagen-Streuung des
Hot-Spots bei t/4 und p 4; Hebel t/8 oder Hot-Spot-Variante mit größerem Kerbabstand, Entscheidung beim Anwender. (3) hält: letzte Änderung 0,44 %; Aussage „nicht monoton“
(B4-Frage offen). (4) hält: Kraft 2,25 %, keine Integrationswarnung – nach zwei Kuren am Geometriekern (Probenprüfung an inneren Trennflächen, deckungsgleiche Flächen).
(5) **umgedeutet**: fern der Naht biegt das exzentrische Knotenblech das Blech (111,1 oben, 94,9 unten, Tet10 ebenso); die Regel gilt für den Membrananteil (0,7 %).
(6) **verfehlt in der geplanten Form** (Interpolation der Oberflächenpunkte: 3,3 % / 9 %); die unabhängige zweite Auswertung ist die Tet10-Referenz. Kurve: 181,1 → 175,4 →
157,1 → 142,6 → 143,2 bei 14 295 → 36 009 → 150 411 → 477 702 → 1 096 107 FHG, 329 s und 59 GB im letzten Zyklus.

### C2: Zweite Sicht über Phase A und B
- Unabhängiges Gutachten, nur lesend, anderes Modell als die Umsetzung; Befunde am Quelltext prüfen, dann
  beheben und mit Tests absichern.

**Vorgehen und Regeln C2, vor dem Gutachten festgelegt (02.10.2026).** Umfang: alles, was Teilprojekt 5 in `packages/volumen3d/volumen3d/`
geändert hat (`git diff 7a6c922..e64a52d`, 34 Dateien, +4 439 Zeilen). Drei Gutachter als eigenständige Unteragenten ohne Kenntnis des
Sitzungsverlaufs, jeder ein anderes Modell als die Umsetzung seines Teils:

| Gruppe | Inhalt (umgesetzt von) | Gutachter |
|---|---|---|
| G1 | A3 gepackte GPU-Blöcke, B1 Moment Fitting, B6 Hüllenintegration und Windungsbaum, C1 Kuren im Geometriekern (Fable 5.1) | Opus 5.5 |
| G2 | A2/A5 Mehrgitter und Glätter, B2 L²-Projektion, B3 Hot-Spot und verschachtelte CSG-Bäume (Opus 5.5) | Fable 5.1 |
| G3 | A6 Löserwahl, B4 adaptive Zyklen und Konvergenzaussage, B5 STEP, B7 Kopplungskontrolle (Sonnet 5.5) | Opus 5.5 |

Die Gutachter lesen nur; kleine Nachrechnungen (ein Prozess, unter einer Minute, ohne GPU) sind erlaubt, Suiten und Dateiänderungen nicht. Gesucht
sind vor allem stille Fehler (falsches Ergebnis ohne Meldung), Abhängigkeit von Rundung, Gitterphase oder Reihenfolge, Verstöße gegen den
Vertrag und Tests, die nicht fehlschlagen können oder deren Schranken geraten sind. Jeder Befund nennt Datei und Zeile, ein konkretes Szenario
(Eingabe → falsches Ergebnis), Schwere (hoch/mittel/niedrig) und ob er gelesen oder nachgerechnet ist. Bekannte offene Punkte sind den Gutachtern
genannt und zählen nicht als Befund.

*Prüfung der Befunde und Ausgang.* Jeden Befund prüfe ich am Quelltext mit einem Skript oder Test, der ihn nachstellt. Bestätigte Befunde der
Schwere hoch und mittel werden behoben, jeweils mit einem Test, der ohne die Kur fehlschlägt, und einem Absatz im Handbuch; bestätigte niedrige
werden behoben, wenn die Kur klein ist, sonst aufgelistet. Nicht bestätigte werden mit Begründung zurückgewiesen. C2 ist fertig, wenn alle
bestätigten hohen und mittleren Befunde behoben sind, Kernsuite und alle betroffenen Suiten grün laufen und die Liste mit Entscheidung je Befund im
Plan und in Theorie 11.19 steht. Was beim Beheben neu auffällt, kommt auf die Liste und wird nicht in C2 nachgezogen, außer es ist ein Fehler der Kur.

**Ergebnis C2 (02.10.2026, Theorie 11.19).** 25 Befunde, davon einer doppelt (G3-1 = G1-3, G3-5 = G2-6); alle am Quelltext bestätigt, jede Kur mit einem Test, der
ohne sie fehlschlägt.

| ID | Schwere | Befund | Entscheidung |
|---|---|---|---|
| G3-1 / G1-3 | hoch | STEP mit durchdringenden Körpern rechnete still „A minus B“ (805 400 statt 1 288 000 mm³); überlappende STL-Schalen doppelt | behoben: STEP vereinigen (`fuse`), STL Kantenkreuzung → Fehler, Tiefenproben innen |
| G1-1 | hoch | deckungsgleiche Flächen auf dem flachen Weg doppelt/teilweise doppelt, reihenfolge- und gitterabhängig; Scheindeckel über bündiger Tasche | behoben: Gegen-Ebene → Teilen + Zeuge; Zeuge verlangt Werkstoff innen |
| G1-2 | hoch | offene Hülle im Divergenzweg still falsch (13 859 statt 27 000 mm³) | behoben: offene Kanten → alter Weg, Volumenwächter je Zelle |
| G2-1 | hoch | Blechseite „nicht eindeutig“ bei Kehlnaht-Schenkel < 0,495 t und Stumpfnähten → kein Hot-Spot | behoben: Blechast eben über 1,0 t + Tiefe t |
| G1-4 | mittel | Hülle in abgezogenem Operations-Teilbaum → Scheinflächen im Werkstoff | behoben |
| G2-2 | mittel | Referenzpunkt hinter Blechkante still auf Stirnfläche (+70 %) | behoben mit G2-1 (Warnung, kein Wert) |
| G3-2 | mittel | Konvergenzaussage „Änderung 0“ vor Monotonie; wirkungslose h-Zyklen | behoben: `ohne_aenderung`, h-Schritt ohne Wirkung übersprungen |
| G3-3 | mittel | Kopplungskontrolle verschleierte Momentfehler an dünnen Blechen (40 % Moment → 4,7 %) | behoben: Abweichung als Spannung (36 %) |
| G3-4 | mittel | zwei Prüfungen in `test_adaptiv` ohne Aussage | behoben |
| G3-5 / G2-6 | mittel | `hotspot_max` vorzeichenbehaftet | behoben: betragsgrößter Wert mit Vorzeichen |
| G1-5, G1-6, G2-3, G2-4, G2-5, G2-7, G2-8, G2-9, G2-10, G3-6, G3-8, G3-9 | niedrig | siehe Theorie 11.19 | behoben |
| G3-7 | niedrig | Zyklen: Fehler verwirft fertige, Speicher der Vorzyklen, Nahtdicke spät, kein Abbruch in `prepare` | behoben bis auf Abbruch in `prepare` (aufgelistet) |

Aufgelistet, nicht in C2: Abbruch in `prepare`, `summary()` nach Zyklen (Vertragsklarstellung), Vereinigung mit mehreren Kindern derselben Hülle, `t_s` von Zyklus 0,
Torsion in der Kopplungskontrolle über das polare Moment. Sichtbare Folge für den Anwender: das Knotenblech meldet jetzt „Moment 7,9 % > 5 %“ an den Schnittebenen
(Endeinspannung gegen das exzentrische Blech, die der Zug-Geber nicht kennt) – richtig, der Vergleich gegen Tet10 bleibt unberührt.

### C3: Handbücher
- Theoriehandbuch (neue Abschnitte nach 11.10), Entwurf Abschnitt 4e, `docs/Volumenmodul.md`.

### C4: Gesamtlauf und Pull Request 3
- `run_all`, alle Paketsuiten, GPU-Suite lokal, mypy, lint-imports, CI grün; Pull Request mit den
  Änderungen außerhalb des Pakets einzeln benannt. Gemergt wird nur nach Freigabe.

## Offene Entscheidungen nach C2 (02.10.2026)

Die Punkte sind nach dem Zeitpunkt geordnet, zu dem sie entschieden sein sollten: O1 bis O4 vor C3 und C4 (sie ändern Tests, Code oder
Handbuchtext des Pull Requests 3), O5 bis O14 können danach kommen. Je Punkt: was zu entscheiden ist, die Möglichkeiten, die Empfehlung und das
Modell für die Arbeit, die aus der Entscheidung folgt.

*O1 – Referenz Knotenblech nach main (Pull Request 13 der Hauptsitzung).* Zu entscheiden ist die Freigabe des Merge von `tests/reference_models/
knotenblech_kehlnaht/` (JSON, STEP, `erwartung_tet10.json`) nach main. Danach holt Session B main per Rebase ab, und `test_knotenblech` liest die
Erwartungswerte aus der Datei statt aus den eingetragenen Zahlen (heute dieselben Werte, 142,74 / 143,14 N/mm²). Empfehlung: freigeben, weil die Werte
von zwei Seiten unabhängig bestätigt sind. Folgearbeit Sonnet 5.5, niedrig.

*O2 – Tet10-Referenz mit 0,5 mm am Übergang.* Die Referenz wanderte zwischen 2,5 und 1 mm um 3,6 %, und das 1-mm-Netz hält am Übergang nur 1,33 mm im
Median; die linke Stirnnaht liegt mit −2,93 % knapp unter der Schranke 3 %. Zu entscheiden ist, ob der Lauf mit dem bereitliegenden 0,5-mm-Netz
(1,55 Mio. Tet10, 6,45 Mio. Freiheitsgrade) gerechnet wird, und wie: mit dem Direktlöser (rund 100 GB, Maschine exklusiv, etwa nachts) oder mit dem
iterativen Löser der Hauptsitzung. Rechnen würde die Hauptsitzung (Entscheidung E2). Empfehlung: ja, mit dem Direktlöser bei freier Maschine, weil erst
dann feststeht, ob die Abnahme links wirklich hält. Hauptsitzung Sonnet 5.5, mittel; die Auswertung in Session B Sonnet 5.5, niedrig.

*O3 – Streuung des Hot-Spots mit der Gitterlage.* Am Knotenblech unterscheiden sich die spiegelgleichen Stirnnähte im letzten Zyklus um 3,1 %; die
Planschranke 1 % ist verfehlt. Zu entscheiden ist zwischen (a) der Schranke der Vorgabe (3 %) als Abnahmewert, (b) einem feineren Nahtziel t/8 (ein
h-Zyklus mehr; der letzte Zyklus hat heute bei p 4 1,1 Mio. Freiheitsgrade und braucht 59 GB, mit t/8 mehr – wie viel, ist nicht gemessen), und
(c) einer Hot-Spot-Variante mit größerem
Abstand zur Kerbe (IIW für grobe Netze: Referenzpunkte 0,5 t und 1,5 t). Empfehlung: zuerst messen – die Gitterlage in drei Schritten verschieben, p 3 und
p 4, je Stirnnaht – und dann zwischen (a), (b) und (c) wählen. Messung Sonnet 5.5, mittel; Umsetzung von (b) oder (c) Opus 5.5, hoch.

*Entscheidung O1 bis O4 (Anwender 02.10.2026):* Empfehlungen angenommen. O1: Merge von Pull Request 13 freigegeben (die Umstellung des Tests folgt nach dem
Rebase auf main). O2: Referenzlauf mit 0,5 mm, Direktlöser, Maschine exklusiv. O3: erst messen (unten). O4: Kriterium „letzte relative Änderung unter 3 %“, die
Monotonie wird zusätzlich genannt.

*Messregeln O3, vor der Messung festgelegt (02.10.2026).* Modell und Last wie C1 (`tests/test_knotenblech.py`), Basiszellgröße 10 (= t), Fahrplan wie dort
(h 5, h 2,5, p 3, p 4), Vertragsweg. Die Gitterlage wird verschoben, indem die beiden Schnittebenen um δ in x verschoben werden (Naht, Blech und Last bleiben; das Blech behält sein Polster
von 5 mm hinter der rechten Ebene): δ = 0, 0,625, 1,25, 1,875 mm (ein Viertel der feinsten Zelle 2,5 mm je Schritt, zusammen eine Periode der feinsten Zellen).
Das Gitter beginnt an der Hülle der beschnittenen Geometrie und wandert deshalb mit den Ebenen; ein Verschieben des ganzen Modells ändert die Lage zur Naht nicht
(gemessen im Schnelllauf: identische Werte bei δ = 0 und 0,625). Die Ebenen liegen 64 mm von den Nähten entfernt, die Verschiebung um 1,9 mm ändert die
Physik nicht (Abklingen der Störung der Einspannung in der Größenordnung e^(−2π·6)). Das Gitter beginnt bei
lo − 0,1 h; die Lage des Übergangs zur Zellgrenze φ = ((x_Naht − Ursprung) mod h_fein)/h_fein wird je Lauf mitgeschrieben. Je Verschiebung ein Lauf bis p 4;
aus den Zyklen werden die Hot-Spots des Zyklus mit p 3 und des Zyklus mit p 4 festgehalten (ein Mitschnitt von `FcmSolver._zyklus`, ohne Änderung am Paket).
Größen je Lauf, Zyklus und Naht: σ_hs bei y = 40 und Mittel über y 32…48 für (a) die Referenzpunkte 0,4 t / 1,0 t (Vorgabe des Pakets, σ_hs = 5/3 σ₀,₄ − 2/3 σ₁,₀)
und (c) 0,5 t / 1,5 t (IIW für grobe Netze, σ_hs = 1,5 σ₀,₅ − 0,5 σ₁,₅); beide aus derselben Lösung (die Konstanten der Hot-Spot-Geometrie werden im Mitschnitt für den
zweiten Aufruf umgestellt). Gegenprobe: σ_xx an den Referenzpunkten (140, 40, 0) und (146, 40, 0) usw. unabhängig aus `Auswertung.spannung_geglaettet` gelesen
und mit den Protokollwerten des Hot-Spot-Moduls verglichen (Übereinstimmung auf 1e-6 relativ, sonst werden die Zahlen nicht berichtet). Streuung
S = (max − min)/Mittelwert über alle acht Proben (4 Verschiebungen × 2 Nähte) von σ_hs(y 40), getrennt nach p, nach (a)/(c).

*Auswertung (Regeln).* (1) S(a) bei p 4 ≤ 1 %: die Planschranke gilt, die 3,1 % waren ein Ausreißer der einen Lage – keine Maßnahme. (2) 1 % < S(a) ≤ 3 %:
Empfehlung (a): Schranke der Vorgabe 3 %, die Abnahme gegen Tet10 wird mit dem gemessenen Streuband berichtet. (3) S(a) > 3 %: Maßnahme nötig; (c) gilt als
wirksam, wenn S(c) bei p 4 ≤ 1 % bleibt (dann Entscheidung über (c) mit Vergleich gegen die Tet10-Referenz an 0,5 t und 1,5 t, die die Hauptsitzung liefern müsste
– PR 13 hat nur 0,4 t und 1,0 t); sonst (b) t/8, dessen Größe vorab mit `estimate` (Freiheitsgrade, ohne Lösen) für p 3 und p 4 berichtet wird. Nicht im Plan der
Messung: Verschiebungen in y und z, Netzfeinheit über t/4 hinaus rechnen.

*Betrieb.* Je Lauf rund 440 s und bis 59 GB (Direktlöser, p 4); die Läufe nacheinander, vorher die Prozessliste prüfen und die Hauptsitzung benachrichtigen
(etwa 30 Minuten, 59 GB von 128 GB, 104 GB frei).

*O4 – Konvergenzaussage.* Der Vorschlag aus B4 war, die Aussage nur über die p-Phase zu treffen. Die Messungen zeigen, dass auch die p-Phase nicht monoton
ist (Knotenblech 157,1 → 142,6 → 143,2; T-Stoß 111,0 → 107,4 → 107,9): die Aitken-Aussage bliebe „nicht monoton“. Zu entscheiden ist das Kriterium:
(a) wie bisher nur bei monotoner Folge eine Aussage, (b) Aussage über die letzte relative Änderung mit der Schranke der Vorgabe (unter 3 % gilt als
konvergiert, die Monotonie wird zusätzlich genannt), (c) nur p-Phase mit (b). Empfehlung: (b) – es ist das Kriterium, das C1 schon verwendet, und es sagt
dem Anwender, was er wissen muss. Folgearbeit Sonnet 5.5, mittel.

*O5 – Konsistenzfehler der Schnittzellen.* Offen sind 10⁻⁶ bis 10⁻⁴ am T-Stoß mit lokaler Verfeinerung und 2·10⁻⁴ bis 3,5·10⁻³ in der Spannung bei p 2 am
schrägen Schnitt (abhängig von der Aggregationsschwelle, nicht von α, Moment Fitting, Flächenordnung oder Tiefe). Beides liegt unter den Schranken der
Vorgabe. Zu entscheiden ist, ob die Ursache jetzt oder vor Teilprojekt 6 (Fehlerschätzer, der davon gestört würde) gesucht wird. Empfehlung: vor Teilprojekt 6,
nicht vor Pull Request 3. Fable 5.1, sehr hoch.

*O6 – Ebenen durch den gekrümmten Teil einer Hülle (B6 Teil 3).* Läuft eine Schnitt- oder Symmetrieebene durch eine gekrümmte STL- oder STEP-Fläche,
gilt dort der Punkttest erster Ordnung mit Warnung. Zu entscheiden ist, ob der Divergenzweg eine Dimension tiefer gebaut wird. Empfehlung: bauen, sobald ein
Anwendungsfall mit gekrümmtem CAD-Teil und Schnittebene ansteht. Fable 5.1, sehr hoch.

*O7 – Vertragsvorschlag 2.2.0 (Volumenlast je Lastfall, liegt seit 28.09.2026).* Heute wirkt `body_load` auf jeden Lastfall; ein Lastfall ohne Eigengewicht
(etwa Wind) bekommt im Detail eine Last, die das Globalmodell nicht trägt, und Kombinationen bekommen keine Faktoren. Der Vorschlag: `body_loads` je Lastfall
und Faktoren für Kombinationen (oder das Hauptprogramm löst Kombinationen selbst auf). Zu entscheiden ist Annahme, Annahme nur von Punkt 1 (Kombinationen löst
das Hauptprogramm auf) oder Ablehnung; bei Annahme setzt die Hauptsitzung ihn als eigenen Pull Request um, Session B schließt ihn an. Empfehlung: Punkt 1
annehmen, Kombinationen im Hauptprogramm auflösen. Hauptsitzung Sonnet 5.5, mittel; Anschluss in Session B Sonnet 5.5, mittel.

*O8 – Abbruch während `prepare` eines Zyklus.* Der Vertrag gibt `prepare` keinen Abbruch; ein Abbruch wird erst nach dem Aufbau des nächsten Zyklus bemerkt
(am T-Stoß Minuten). Zu entscheiden ist ein Vertragsvorschlag (Minor, optionaler Parameter `cancel` in `prepare`) oder das Hinnehmen. Empfehlung: zusammen mit
O9 als ein Vorschlag. Sonnet 5.5, mittel.

*O9 – `summary()` nach Zyklen.* Nach `solve` mit Zyklen beschreibt `disc.summary()` weiter Zyklus 0; der Vertrag (Abschnitt 7) sagt „mit derselben
Diskretisierung“. Zu entscheiden ist, ob der Vertrag klarstellt, dass `summary()` die übergebene Diskretisierung beschreibt und die Zyklen nur in
`convergence` und im Protokoll stehen (Patch), oder ob `solve` die Diskretisierung des letzten Zyklus zurückgibt (Minor). Empfehlung: Klarstellung (Patch).
Sonnet 5.5, niedrig.

*O10 – Torsion in der Kopplungskontrolle.* Die Torsion geht über das polare Moment ein und wird an dünnen Rechteckquerschnitten um etwa den Faktor b/(2t)
unterschätzt (Streifen b/t = 10: fünffach, b/t = 30: fünfzehnfach).
Zu entscheiden ist, ob ein Torsionswiderstand aus der Schnittfläche gebaut wird (dünnwandige Näherung oder Spannungsfunktion) oder die Unterschätzung als
Grenze der Kontrollgröße dokumentiert bleibt. Empfehlung: dokumentiert lassen, bis ein Detail mit Torsion ansteht. Opus 5.5, hoch.

*O11 – Zeiten je Zyklus.* `t_s` von Zyklus 0 enthält die Vorbereitung nicht, die der späteren Zyklen schon. Zu entscheiden ist die Festlegung. Empfehlung:
je Zyklus Vorbereitung und Lösen getrennt ausweisen. Sonnet 5.5, niedrig.

*O12 – Vereinigung mit mehreren Kindern derselben Hülle.* Nur programmatisch erreichbar (`aus_params` erzeugt je Knoten ein eigenes Objekt). Keine
Entscheidung nötig; Empfehlung: mit klarem Fehler abweisen. Sonnet 5.5, niedrig.

*O13 – Einrichtzeit der großen Glätterblöcke auf der GPU nach der Cholesky-Umstellung (C2, G2-10).* Richtig geprüft, Zeit nicht gemessen. Keine
Entscheidung, nur eine Messung (Kirsch h 8 und Block h 14 gegen die Werte aus A3). Sonnet 5.5, mittel.

*O14 – Nächster Leistungshebel am STEP-Weg.* Die Oberflächenquadratur der Hüllenfacetten trägt 17 von 27 s am Block mit Bohrung N 120. Zu entscheiden ist,
ob sie jetzt beschleunigt wird (Schleifen über 173 000 Polygone in numba). Empfehlung: nach Pull Request 3. Opus 5.5, hoch.

## Modell je Schritt

Der Anwender stellt Modell und Denkstufe vor jedem Schritt von Hand ein; der Stand wird nach jedem Schritt
nachgetragen.

| Schritt | Modell | Denkstufe | Warum | Stand |
|---|---|---|---|---|
| A1 Aufbau vermessen | Sonnet 5 | mittel | klar umrissene Messaufgabe | erledigt (5381f71) |
| A2 Aufbau beschleunigen | Opus 5.5 | hoch | Umbau in bekanntem Code mit vielen Prüfungen | erledigt (d0e6c37), Teil (b) nach A3 |
| A3 GPU-Speicher für 10⁶ FHG | Fable 5.1 | sehr hoch | numerisch heikel (FP32, Glätter), Entwurf und Umsetzung | erledigt (d47d4a1) |
| A4 h-Mehrgitter (nur wenn nötig) | Fable 5.1 | sehr hoch | hängende Knoten im Mehrgitter, höchstes Risiko | entfällt (Grobgitter 12 % des Lösens) |
| A5 Streuung über Schnittlagen | Opus 5.5 | hoch | Ritz-Analyse und Glätterabstimmung | erledigt (f2bf8e7): α 100 (−20 bis −25 %); Vorgabe als erfüllt anerkannt |
| A6 Leistungsabnahme, Löserwahl | Sonnet 5 | mittel | Messreihe nach festem Schema | erledigt: `auto` bleibt direkt; Lösen 10⁶ FHG 7–8 s, Aufbau + Lösen 62–115 s |
| B1 Moment Fitting | Fable 5.1 | sehr hoch | Stabilität der Gewichte, Konsistenz Volumen/Rand | erledigt: Vorgabe an; schwere Suiten grün, Zeiten in Theorie 11.11 |
| B2 Spannungsrückgewinnung | Opus 5.5 | hoch | bekanntes Verfahren, sorgfältige Umsetzung | erledigt: L²-Projektion ist Ausgabe; Kosten in Theorie 11.12 |
| B3 Hot-Spot IIW Typ a | Opus 5.5 | hoch | Geometrie der Referenzpunkte, Normbezug | erledigt: Spanne korrigiert (Anwender), Absolutwert in C1 gegen Tet10 |
| B4 Konvergenzkurve, Protokoll | Sonnet 5 | mittel | überschaubar, baut auf B2/B3 | gebaut; Fahrplan h zuerst bis t/4 umgesetzt (Anwender), T-Stoß p 2–4 bei 2,5 mm: 111,0 → 107,4 → 107,9; Messung am Knotenblech in C1 |
| B5 STEP über gmsh | Sonnet 5 | mittel | Anbindung einer Bibliothek | erledigt; die offene Planprüfung K_t am gekrümmten Körper hat B6 erfüllt (0,12 %) |
| B6 Windungszahl-Baum + Hüllenintegration | Fable 5.1 | sehr hoch | Divergenzsatz über Dreiecke, Barill-Baum, Genauigkeitsnachweis | erledigt: (1)–(3) halten, Block N 120 388 → 26,8 s, K_t 0,12 %; Baum mit β 4 statt 2 (Anwender 01.10.: angenommen) |
| B7 Schale → Volumen (Prüfung) | Sonnet 5.5 | mittel | Test über bestehende Schnittstelle | erledigt: Schnittgrößen < 7·10⁻⁴ (p 2), 6·10⁻⁸ (p 3); Kopplungskontrolle und Hüllenfacetten-Fehler behoben; Schranke p 2 geneigt 1 % (Anwender) |
| C1 Knotenblech-Abnahme | Fable 5.1 | sehr hoch | Modellbau und Nachweis gegen Referenz | erledigt: +0,34 % / −2,93 % gegen Tet10-Referenz PR 13 (Schranke 3 %); Symmetrie 3,1 % (Gitterphase) und 0,5-mm-Referenzlauf beim Anwender |
| C2 Zweite Sicht | Opus 5.5 (Prüfung und Kuren), Gutachter je Gruppe ein anderes Modell | hoch | unabhängig von der Umsetzung, tiefste Prüfung | erledigt: 24 Befunde bestätigt, 4 hohe und 6 mittlere behoben, 12 niedrige behoben, 1 teilweise; Liste in Theorie 11.19 |
| O1 Referenz Knotenblech nach main | Sonnet 5.5 | niedrig | Test auf `erwartung_tet10.json` umstellen | erledigt: PR 13 auf main (f56281a), main in den Zweig gemergt (c37cd91), Test liest die Datei |
| O2 Tet10-Referenz 0,5 mm | Sonnet 5.5 (Hauptsitzung) | mittel | Lauf und Auswertung nach festem Schema | angenommen: rechnen, Direktlöser, Maschine exklusiv (Hauptsitzung legt den Zeitpunkt fest) |
| O3 Hot-Spot-Streuung mit der Gitterlage | Sonnet 5.5 (Messung), Opus 5.5 (Umsetzung) | mittel / hoch | erst messen, dann t/8 oder 0,5 t / 1,5 t | Empfehlung angenommen; Messregeln festgelegt, Messung läuft (4 Verschiebungen, p 3 und p 4, a und c) |
| O4 Konvergenzaussage | Sonnet 5.5 | mittel | Kriterium in `konvergenz.py`, Tests, Handbuch | angenommen: letzte Änderung unter 3 %, Monotonie zusätzlich genannt; Umsetzung offen |
| C3 Handbücher | Sonnet 5.5 | mittel | Texte aus vorhandenen Messwerten, viele Zahlen | offen; nach O1 bis O4 |
| C4 Gesamtlauf, Pull Request | Sonnet 5.5 | mittel | Routine mit Prüfliste | offen; Merge nur auf Freigabe |
| O5 Konsistenzfehler der Schnittzellen | Fable 5.1 | sehr hoch | Ursachensuche in Aggregation und Quadratur | Entscheidung offen: wann (Empfehlung: vor TP 6, nach PR 3) |
| O6 Ebenen durch gekrümmte Hülle (B6 Teil 3) | Fable 5.1 | sehr hoch | Divergenzweg eine Dimension tiefer | Entscheidung offen: bauen oder Warnung lassen (Empfehlung: bei Bedarf) |
| O7 Vertragsvorschlag 2.2.0 Volumenlast je Lastfall | Sonnet 5.5 | mittel | Anschluss in `api.py` nach dem Vertrags-PR | Entscheidung offen: ganz, nur Punkt 1 oder ablehnen (Empfehlung: Punkt 1, Kombinationen im Hauptprogramm) |
| O8 Abbruch in `prepare` | Sonnet 5.5 | mittel | Vertragsvorschlag schreiben | Entscheidung offen: Vorschlag (Minor) oder hinnehmen (Empfehlung: Vorschlag mit O9) |
| O9 `summary()` nach Zyklen | Sonnet 5.5 | niedrig | Klarstellung im Vertrag | Entscheidung offen: Klarstellung (Patch) oder letzte Diskretisierung zurückgeben (Minor) |
| O10 Torsion in der Kopplungskontrolle | Opus 5.5 | hoch | Torsionswiderstand aus der Schnittfläche | Entscheidung offen: bauen oder dokumentiert lassen (Empfehlung: dokumentiert lassen) |
| O11 Zeiten je Zyklus | Sonnet 5.5 | niedrig | Protokollfelder | Entscheidung offen: Festlegung (Empfehlung: Vorbereitung und Lösen getrennt) |
| O12 mehrere Kinder derselben Hülle | Sonnet 5.5 | niedrig | Prüfung in `Csg` | keine Entscheidung nötig; Empfehlung: mit Fehler abweisen |
| O13 GPU-Einrichtzeit nach Cholesky | Sonnet 5.5 | mittel | Messreihe gegen A3 | keine Entscheidung, nur Messung |
| O14 Oberflächenquadratur der Hüllenfacetten | Opus 5.5 | hoch | numba-Schleifen, Leistung | Entscheidung offen: jetzt oder nach PR 3 (Empfehlung: nach PR 3) |
