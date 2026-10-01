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

### B7: Schale → Volumen (nur Prüfung)
- Kopplung an ein Schalen-Globalmodell ist Sache des Providers im Hauptprogramm; hier nur ein Test mit einem
  Schalen-Provider-Stub über die Vertragsschicht.
- Prüfung: Schnittgrößenkontrolle < 1 % (Vorgabe 13, Kopplung).

## Phase C – Abnahme und Abschluss

### C1: Knotenblech mit Kehlnaht (Abnahme TP 5)
- Modell aus CSG (Blech, Kehlnaht, Anschluss), Lasten über Schnittebene, Hot-Spot entlang der Naht,
  Konvergenzkurve. Referenzwerte nach E2, Ablage nach E3.
- Prüfung: Hot-Spot-Spannung gegen Tet10-Referenz < 3 % (Vorgabe 13).

### C2: Zweite Sicht über Phase A und B
- Unabhängiges Gutachten, nur lesend, anderes Modell als die Umsetzung; Befunde am Quelltext prüfen, dann
  beheben und mit Tests absichern.

### C3: Handbücher
- Theoriehandbuch (neue Abschnitte nach 11.10), Entwurf Abschnitt 4e, `docs/Volumenmodul.md`.

### C4: Gesamtlauf und Pull Request 3
- `run_all`, alle Paketsuiten, GPU-Suite lokal, mypy, lint-imports, CI grün; Pull Request mit den
  Änderungen außerhalb des Pakets einzeln benannt. Gemergt wird nur nach Freigabe.

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
| B5 STEP über gmsh | Sonnet 5 | mittel | Anbindung einer Bibliothek | gebaut; Planprüfung K_t am gekrümmten Körper nicht erfüllt (STL-Weg zu langsam), Entscheidung offen |
| B6 Windungszahl-Baum | Opus 5.5 | hoch | Algorithmus mit Genauigkeitsnachweis | offen |
| B7 Schale → Volumen (Prüfung) | Sonnet 5 | mittel | Test über bestehende Schnittstelle | offen |
| C1 Knotenblech-Abnahme | Opus 5.5 | hoch | Modellbau und Nachweis gegen Referenz | offen |
| C2 Zweite Sicht | Fable 5.1 | hoch | unabhängig von der Umsetzung, tiefste Prüfung | offen |
| C3 Handbücher | Sonnet 5 | niedrig | Texte aus vorhandenen Messwerten | offen |
| C4 Gesamtlauf, Pull Request | Sonnet 5 | mittel | Routine mit Prüfliste | offen |
