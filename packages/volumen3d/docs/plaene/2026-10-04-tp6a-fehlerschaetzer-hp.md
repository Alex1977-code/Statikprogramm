# Teilprojekt 6a: residuenbasierter Fehlerschätzer und lokale hp-Adaptivität (Entwurf)

Stand 04.10.2026. Teilprojekt 6 (Stufe 3 der Vorgabe, Abschnitte 3, 8.4 und 11.2) ist in vier Teile zerlegt, die je für sich entworfen, geplant, gebaut und abgenommen
werden: **6a** Fehlerschätzer mit adaptiven hp-Zyklen, **6b** Kerbspannungskonzept (r_ref = 1 mm), **6c** Stellungs-Batch (die Rechnung mehrerer Lastfälle und Stellungen mit
einer Zerlegung gibt es schon; zu leisten sind Nachweis und Zeitmessung), **6d** Punktwolke und Voxel als Geometriequelle. Die Reihenfolge 6a → 6b → 6c → 6d hat der Anwender
am 04.10.2026 festgelegt; 6b baut auf der lokalen Verfeinerung aus 6a auf.

## 1. Entscheidungen des Anwenders (04.10.2026)

Drei Entscheidungen stehen fest. Zuerst kommt der Fehlerschätzer (6a). Die hp-Adaptivität ist echt lokal: p ist je Zelle verschieden. Der Schätzer ist residuenbasiert
(Zellresiduum, Traktionssprünge über die Zellflächen, Randterme), nicht rückgewinnungsbasiert und nicht zielorientiert. Für das variable p gilt **Ansatz B**: jede Zelle hat genau die
Moden ihres eigenen p, die Modennummerierung, die Quadratur, die Assemblierung, die Zwänge und die Aggregation rechnen je Zelle mit deren p. Verworfen wurde Ansatz A (Basis beim
größten p überall, Gradbegrenzung über Nullbindungen in der Zwangsmatrix), weil er die Arbeit je Zelle beim größten p leistet.

## 2. Ziel und Abnahme von 6a

Am Ende von 6a steuert der Fehlerschätzer die adaptiven Zyklen: er markiert Zellen, ein Glattheitsmaß entscheidet je markierter Zelle zwischen Teilen und Erhöhen von p, und nach
2 bis 4 Zyklen gibt es eine Konvergenzaussage wie heute. Abgenommen wird am Knotenblech gegen die Tet10-Referenz (Vorgabe 13: σ_hs auf 3 %) und im Vergleich mit dem festen
Fahrplan von Teilprojekt 5 (lokale h-Halbierung an den Nähten bis t/4, dann p + 1): der neue Treiber muss mindestens dieselbe Genauigkeit mit nicht mehr Freiheitsgraden
erreichen. Bis er das zeigt, bleibt der feste Fahrplan Vorgabe; der neue Treiber wird über einen Schalter im Paket eingeschaltet. Der Vertrag ändert sich nicht
(`FcmSettings.adaptive_cycles` bleibt der einzige Parameter).

## 3. Phase 1: Fehlerschätzer bei einheitlichem p, h-adaptiv

**Schätzer je Zelle K** (in der Energienorm, Einheit N·mm, mit dem Elastizitätsmodul E zur Umrechnung):

η_K² = (1/E) · [ (h_K/p_K)² ‖f + div σ_h‖²_{K∩Ω} + ½ Σ_F (h_F/p_F) ‖[σ_h n]‖²_{F∩Ω} + (h_K/p_K) ‖t − σ_h n‖²_{Γ_N∩K} ] + E · (p_K²/h_K) ‖u_h − g‖²_{Γ_D∩K}

Der erste Term ist das Zellresiduum im Werkstoffteil der Zelle; div σ_h braucht zweite Ableitungen der Basis (die Legendre-Basis liefert sie geschlossen:
φ_j'' = sqrt((2j − 1)/2) P'_{j−1}). Der zweite Term sind die Sprünge der Traktion über die Zellflächen, soweit sie im Werkstoff liegen, auch über hängende Flächen (Sprung zwischen
feiner und grober Zelle über der feinen Fläche) und zwischen aggregierten Zellen und ihren Nachbarn (jede Zelle mit ihrem eigenen Polynom). Der dritte Term ist der Traktionsrest auf
belasteten Oberflächen, der vierte der Nitsche-Rand (Verschiebungsrand und die Normalkomponente an Schnittebenen). Ein Feld im Ansatzraum ergibt η auf Rundungsniveau.

**Flächenintegrale über Zellflächen im Werkstoff** sind neu. Gewählt ist Tensor-Gauß auf der Zellfläche mit Unterteilung und Punkttest (erste Ordnung in der Geometrie): für einen
Schätzer, der ohnehin nur bis auf Konstanten gilt, reicht das voraussichtlich; die Messung in Phase 1 prüft es (Wirksamkeit an geschnittenen Modellen gegen ungeschnittene).

**Markieren:** nach Dörfler mit θ = 0,5 (die kleinste Menge von Zellen, deren η² mindestens die Hälfte der Summe trägt). **Verfeinern:** markierte Zellen werden geteilt
(lokale Verfeinerung über die vorhandenen Zwangsteilungen `Verfeinerung.zellen`, 2:1-Balancierung wie bisher).

**Abnahme Phase 1:** (1) der Effektivitätsindex η / ‖e‖_E bleibt über drei bis vier Verfeinerungen innerhalb eines Faktors 3 konstant, gemessen an Lamé (exakte Lösung),
Kragarm (Balkenlösung mit Schubkorrektur, Energie aus der Lösung auf einem sehr feinen Gitter) und Kirsch (Referenz aus einer sehr feinen Rechnung); (2) η fällt mit derselben Rate
wie der wahre Fehler; (3) für Felder im Ansatzraum (Patch-Test höherer Ordnung) liegt η unter 10⁻⁸ relativ zur Energie des Felds; (4) die lokalen Indikatoren treffen die Zellen
mit dem größten wahren Fehler (von den 10 % Zellen mit größtem η liegen mindestens die Hälfte unter den 20 % mit größtem wahren Fehler); (5) h-adaptive Zyklen erreichen an Lamé und
Kirsch dieselbe Genauigkeit wie gleichmäßige Verfeinerung mit weniger Freiheitsgraden. Die genauen Schranken legt der Plan vor der Messung fest.

## 4. Phase 2: variables p je Zelle (Ansatz B)

**Datenstruktur.** `Gitter` bekommt eine p-Karte je Zelle (Vorgabe: alle Zellen gleich, wie heute). Die lokalen Moden einer Zelle sind die Tensor-Moden (a, b, c) mit a, b, c ≤ p_K.
Die globale Nummerierung ordnet jeden Mode über den Entitätsschlüssel (Ecke, Kante, Fläche, Zellinneres) und seine hohen Indizes zu, unabhängig vom p der einzelnen Zelle.
**Minimumregel:** der Grad einer Entität ist das kleinste p aller Zellen, deren Rand sie geometrisch enthält – auch der feinen Zellen an einer hängenden Fläche, damit die Spur der groben
Zelle von den feinen dargestellt werden kann. Moden einer Zelle oberhalb des Grads ihrer Entität gibt es nicht. Damit ist das Feld stetig über Flächen mit p-Sprung. Die Modentabelle
wird je Zelle variabel lang (gepolstert mit −1 oder als Listen; entschieden im Plan nach Messung der Zugriffe). **Aggregierte Zellen übernehmen das p ihrer Wurzel**, weil ihr Polynom
die Fortsetzung des Wurzelpolynoms ist; die Fortsetzungsabbildung wird rechteckig, wenn Wurzel und Zelle verschieden große Modensätze haben.

**Umbau je Modul, Weg des Direktlösers:** Quadratur (Ordnung und Moment-Fitting-Grad 2p je Zelle), Assemblierung (Zellen nach p gruppiert), Nitsche-Rand und Lasten
(`fcm/rand.py`), hängende Freiheitsgrade (`fcm/zwaenge.py`: Spur der feinen Zelle mit deren p, Moden der groben Zelle mit deren p), Aggregation (`fcm/aggregation.py`),
Spannungsrückgewinnung (`postprocess/rueckgewinnung.py`), Auswertung und Hot-Spot (`postprocess/auswertung.py`, `postprocess/hotspot.py`), Protokoll und Zusammenfassung (`api.py`:
p-Verteilung statt eines p). **Matrixfreier Operator, Mehrgitter und GPU** (`fcm/operator.py`, `fcm/mehrgitter.py`, `fcm/mehrgitter_gpu.py`, `fcm/bloecke_gpu.py`) setzen
gleiches p in allen Zellen voraus (Summenfaktorisierung, p-Ebenen). Bei variablem p fällt die Löserwahl auf den Direktlöser zurück und nennt das in den Warnungen; bei
einheitlichem p bleiben sie unverändert. Ob sie variables p brauchen, entscheidet eine Messung an großen Modellen nach 6a.

**Sicherung:** bei einheitlichem p muss alles Bit für Bit gleich bleiben – Modentabelle, Zwangsmatrix, Zellquadratur (SHA-256 über Punkte, Gewichte, Masken), Lösung –, in allen Suiten.

**Abnahme Phase 2:** (1) bei einheitlichem p Bit für Bit wie vorher; (2) Patch-Tests mit zufällig verteiltem p je Zelle: lineares Feld auf Rundungsniveau, ein Feld vom Grad k
überall dort, wo alle beteiligten Zellen p ≥ k haben; (3) die Spur über eine Fläche mit p-Sprung ist beidseits gleich (10⁻¹²), auch an hängenden Flächen und an aggregierten Zellen;
(4) die Zahl der Freiheitsgrade ist die Summe der Moden der Entitäten nach der Minimumregel (unabhängig gezählt); (5) die Rechenzeit von Aufbau und Lösung bei gemischtem p liegt
zwischen der bei einheitlich kleinstem und einheitlich größtem p (gemessen an Kirsch und Knotenblech).

## 5. Phase 3: hp-Treiber

**Glattheitsmaß** je markierter Zelle aus dem Abklingen der Legendre-Koeffizienten der Lösung (Betrag der Koeffizienten je Grad k = 2 … p_K): klingen sie schnell ab, wird p um 1
erhöht (höchstens bis 4), sonst wird die Zelle geteilt. Die Schwelle wird vor der Messung im Plan festgelegt und an zwei Fällen mit bekanntem Charakter geeicht: Lamé-Zylinder (glatt, p
soll gewinnen) und Nahtübergang am Knotenblech (singulär, h soll gewinnen). Bei p_K = 2 steht nur ein Grad zur Verfügung; der Plan legt fest, wie dort entschieden wird.

**Zyklen:** 2 bis 4 wie heute (`adaptive_cycles`), Konvergenzkurve und Konvergenzaussage wie heute. Der feste Fahrplan bleibt Vorgabe, der hp-Treiber kommt über einen Schalter
im Paket; nach bestandener Abnahme entscheidet der Anwender über den Wechsel der Vorgabe.

**Abnahme Phase 3:** (1) Knotenblech: σ_hs gegen die Tet10-Referenz auf 3 % an beiden Stirnnähten (wie Vorgabe 13); (2) gegenüber dem festen Fahrplan mindestens dieselbe Genauigkeit
der Strukturspannung mit nicht mehr Freiheitsgraden (Knotenblech und T-Stoß); (3) Konvergenzaussage „konvergiert“ nach höchstens 4 Zyklen; (4) Lamé und Kirsch: hp erreicht die
Genauigkeit gleichmäßiger p-Erhöhung mit weniger Freiheitsgraden.

## 6. Risiken

Der Schätzer könnte am Nahtübergang zu spät verfeinern, weil die Strukturspannung aus Punkten bei 0,4·t und 1,0·t kommt und der Schätzer die Energie misst; dann wird die
Mindestauflösung t/4 an der Naht aus dem festen Fahrplan als Regel übernommen. Ansatz B berührt 14 Module; das Risiko, bestehende Ergebnisse zu verändern, fängt die
Bit-Sicherung bei einheitlichem p. Die Flächenintegrale mit Punkttest sind erster Ordnung; zeigt Phase 1, dass der Schätzer an geschnittenen Flächen unbrauchbar ist, werden die Flächen
wie die Zellen eben-exakt integriert. Variables p im matrixfreien Weg ist in 6a nicht enthalten; große Modelle mit variablem p rechnen dann mit dem Direktlöser.

## 7. Modell je Schritt

| Schritt | Modell | Denkstufe | Stand |
|---|---|---|---|
| Entwurf 6a | Opus 5.5 | hoch | zur Durchsicht durch den Anwender |
| Phase 1: Plan, Schätzer, h-adaptiv, Messung der Wirksamkeit | Opus 5.5 | hoch | nach Freigabe des Entwurfs |
| Phase 2: variables p je Zelle (Ansatz B), Direktlöser-Weg | Opus 5.5 | hoch | nach Phase 1 |
| Phase 3: hp-Treiber, Abnahme Knotenblech und T-Stoß | Opus 5.5 | hoch | nach Phase 2 |
| Pull Request nach 6a | Sonnet 5.5 | niedrig | nur auf Anweisung, Merge nur auf Freigabe |
