# Referenzmodell „Knotenblech mit Kehlnaht“

Gemeinsames Referenzmodell nach Abschnitt 8 des Schnittstellenvertrags. Es prüft die Hot-Spot-Auswertung
(IIW Typ a) und ist die Grundlage der Abnahme C1 des Volumenmoduls (Hot-Spot-Spannung gegen Tet10 unter
3 %). Nach den Entscheidungen des Anwenders vom 29.09.2026 ist die Referenz die Tet10-Rechnung des
Hauptprogramms `statik3d` (E2), abgelegt als eigener Pull Request der Hauptsitzung (E3).

Seit dem 03.10.2026 gelten die Werte des Netzes mit 0,5 mm am Nahtübergang. Sie ersetzen die Werte des
1-mm-Netzes vom 01.10.2026, die als `erwartung_tet10_1mm.json` daneben liegen bleiben. Beide liegen an
jedem Nahtpunkt höchstens 0,31 % auseinander. Damit ist die Netzkonvergenz belegt.

| Datei | Inhalt | Herkunft |
|---|---|---|
| `knotenblech_kehlnaht.json` | Eingabedaten: Geometrie, Werkstoff, Last, Nahtlinien, Referenzpunkte, Formel, Toleranzen | Session B |
| `knotenblech.step` | Körper zwischen den Schnittebenen x 0 und x 200, Volumen 181 936 mm³ | Session B (gmsh/OpenCASCADE) |
| `erwartung_tet10.json` | Erwartungswerte: σ_xx an den 36 Punkten, σ_hs je Nahtpunkt, Reaktionskraft, Netz, Programmstand, Änderung gegen das 1-mm-Netz | Hauptsitzung |
| `erwartung_tet10_1mm.json` | die abgelösten Erwartungswerte des 1-mm-Netzes | Hauptsitzung |
| `werkzeug/` | die Skripte, mit denen die Erwartungswerte erzeugt und geprüft wurden | Hauptsitzung |

## Rechnung

Gerechnet wurde mit `main` f56281a aus einem festen Arbeitsbaum, mit fest eingestelltem Direktlöser
PARDISO. Das Netz ist `knotenblech_tet10_lokal05.inp` von Session B: 305 689 Tet10-Elemente und
445 946 Knoten, also 1,34 Mio. Freiheitsgrade. gmsh hat es mit einem Größenfeld von 0,5 mm in Kästen um
Nahtübergang und Auswertepunkte erzeugt, sonst wie das 1-mm-Netz (1 mm in 12 mm Umkreis der
Nahtübergänge, 2,5 mm im Blech und 5 mm fern). Die Datei liegt wegen ihrer Größe nicht im Repository;
ihr SHA-256 steht in `erwartung_tet10.json`. Die CPS6-Flächen, die gmsh an den Stirnseiten mitschreibt,
sind weggelassen, weil der Abaqus-Import sie als Scheiben rechnen würde.

Werkstoff E = 210 000 N/mm², ν = 0,3. Auf der Stirnfläche x = 0 ist u_x = 0 vorgegeben, auf x = 200
u_x = 200 ε = 0,095238 mm mit ε = 100/210 000; die Querbewegung ist frei. Den Starrkörper halten
u_y = u_z = 0 am Knoten nächst (0, 40, −5) und u_z = 0 am Knoten (0, 80, −5); die tatsächlich gewählten
Knoten stehen in der Erwartungsdatei.

## Auswertung

Der Primärwert `sigma_xx` ist das Spannungsfeld des Tet10-Elements am Punkt, also ein an den Punkt
interpolierter Rohwert und kein Knotenwert. Jeder der 36 Punkte liegt in genau einem Element. Daneben steht
`sigma_xx_knoten`, die geglättete Eckspannung des Lösers (`res.solid_knoten`, dieselbe, die der
Volumennachweis liest), linear im Dreieck der Blechoberseite interpoliert. Beide Wege sind getrennte
Skripte (`werkzeug/auswertung_b.py` und `werkzeug/auswertung_a.py`).

Vor der Rechnung wurden die Kriterien festgelegt. Beide Wege wurden an einem Lauf mit exakt bekannter
Lösung geeicht: Das lineare Feld auf allen Randknoten ergibt überall σ_xx = 100 N/mm². Die Abweichung lag
höchstens bei 3,8·10⁻⁹ N/mm², die Reaktion an x = 200 bei 80 000 N. Im Referenzlauf liegen die beiden
Wege bei σ_hs höchstens 0,19 % und bei σ_xx höchstens 0,12 % auseinander. Rechts und links unterscheiden
sich die σ_hs um höchstens 0,11 %, gespiegelt um y = 40 ebenfalls um höchstens 0,11 %. Beim 1-mm-Netz
waren es 0,28 % und 0,43 %; dieser Netzeinfluss ist also fast verschwunden.

| y [mm] | σ_hs rechts [N/mm²] | σ_hs links [N/mm²] | 1-mm-Netz rechts | 1-mm-Netz links |
|---|---|---|---|---|
| 32 | 130,55 | 130,46 | 130,14 | 130,48 |
| 36 | 140,25 | 140,39 | 140,33 | 140,63 |
| 40 | 143,03 | 143,00 | 142,74 | 143,14 |
| 44 | 140,32 | 140,32 | 140,15 | 140,46 |
| 48 | 130,50 | 130,55 | 130,42 | 130,33 |

Reaktionskraft in x an x = 200: 81 843,40 N (1-mm-Netz 81 845,23 N).

## Netz am Nahtübergang

Die Anfrage verlangt am Nahtübergang eine Kantenlänge von höchstens t/10 = 1 mm. Gemessen an allen Kanten
der Tetraeder mit einer Ecke höchstens 1,5 mm vom Übergang liegt sie bei diesem Netz im Median bei
0,687 mm, 90 % sind kürzer als 0,894 mm, die längste ist 1,259 mm lang. Beim 1-mm-Netz waren es 1,33 mm
im Median. Die Änderung von σ_hs gegen das 1-mm-Netz steht je Nahtpunkt in `aenderung_gegen_1mm`. Sie
ist am größten rechts bei y = 32 mit 0,31 %. Als Schranke für die Konvergenz war vor der Rechnung 1 %
festgelegt.

Das gleichmäßige 0,5-mm-Netz mit 6,45 Mio. Freiheitsgraden ist nicht gerechnet. Gemessen am 1-mm-Netz
braucht das Aufstellen 33,6 GB und die Zerlegung mit PARDISO weitere 30,6 GB, weil das Programm die
symmetrische Matrix als unsymmetrisch zerlegt. Hochgerechnet wären es für 0,5 mm mehrere hundert GB.

## Nachrechnen

```
python werkzeug/lauf_pardiso.py <Arbeitsbaum main> knotenblech_tet10_lokal05.inp <ordner_eichung> eichung
python werkzeug/lauf_pardiso.py <Arbeitsbaum main> knotenblech_tet10_lokal05.inp <ordner_referenz> referenz
python werkzeug/auswertung_a.py <ordner>     (je Ordner)
python werkzeug/auswertung_b.py <ordner>     (je Ordner)
python werkzeug/vergleich_05mm.py <ordner_eichung> <ordner_referenz> <ordner>/erwartung_neu.json erwartung_tet10_1mm.json
```

Das Vergleichsskript prüft die Kriterien und schreibt die Erwartungswerte neu nach `<ordner>/erwartung_neu.json`;
diese Datei vergleicht man dann mit `erwartung_tet10.json`. Die Felder `status`, `vorgaenger` und die
Kantenanforderung unter `netz` sind von Hand ergänzt.

`lauf_pardiso.py` ruft `knotenblech_lauf.py` aus dem Arbeitsbaum auf und stellt vorher PARDISO fest ein.
Mit der Vorgabe „auto“ wiche der Löser bei Speichermangel auf einen Direktlöser aus, der noch mehr
Speicher braucht. Speicher und Laufzeit schreibt es nach `<ordner>/speicher.json`. Ein Lauf dauert etwa
sieben Minuten. Der Hauptprozess kam am 02.10.2026 auf höchstens 42,5 GB Arbeitssatz; vorher gemessen
waren bis 81 GB Bedarf, der Rechner sollte also so viel frei haben.

Für das 1-mm-Netz gilt derselbe Weg mit `knotenblech_tet10_1mm.inp` und `werkzeug/vergleich.py`
(`python werkzeug/vergleich.py <ordner_eichung> <ordner_referenz> <ordner>/erwartung_neu.json`). Die frühere
Angabe von rund 17 GB für diesen Lauf war zu niedrig. Gemessen sind 33,6 GB für das Aufstellen und weitere
30,6 GB für die Zerlegung.
