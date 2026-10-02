# Referenzmodell „Knotenblech mit Kehlnaht“

Gemeinsames Referenzmodell nach Abschnitt 8 des Schnittstellenvertrags. Es prüft die Hot-Spot-Auswertung
(IIW Typ a) und ist die Grundlage der Abnahme C1 des Volumenmoduls (Hot-Spot-Spannung gegen Tet10 unter
3 %). Nach den Entscheidungen des Anwenders vom 29.09.2026 ist die Referenz die Tet10-Rechnung des
Hauptprogramms `statik3d` (E2), abgelegt als eigener Pull Request der Hauptsitzung (E3).

| Datei | Inhalt | Herkunft |
|---|---|---|
| `knotenblech_kehlnaht.json` | Eingabedaten: Geometrie, Werkstoff, Last, Nahtlinien, Referenzpunkte, Formel, Toleranzen | Session B |
| `knotenblech.step` | Körper zwischen den Schnittebenen x 0 und x 200, Volumen 181 936 mm³ | Session B (gmsh/OpenCASCADE) |
| `erwartung_tet10.json` | Erwartungswerte: σ_xx an den 36 Punkten, σ_hs je Nahtpunkt, Reaktionskraft, Netz, Programmstand | Hauptsitzung |
| `werkzeug/` | die Skripte, mit denen die Erwartungswerte erzeugt und geprüft wurden | Hauptsitzung |

## Rechnung

Gerechnet wurde mit `main` 7da3571 aus einem festen Arbeitsbaum, mit dem Direktlöser PARDISO. Das Netz ist
`knotenblech_tet10_1mm.inp` von Session B: 247 636 Tet10-Elemente und 363 048 Knoten, erzeugt mit gmsh
mit einem Größenfeld von 1 mm in 12 mm Umkreis der Nahtübergänge, 2,5 mm im Blech und 5 mm fern. Die Datei
liegt wegen ihrer Größe (46 MB) nicht im Repository; ihr SHA-256 steht in `erwartung_tet10.json`. Die
CPS6-Flächen, die gmsh an den Stirnseiten mitschreibt, sind weggelassen, weil der Abaqus-Import sie als
Scheiben rechnen würde.

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
höchstens bei 2,6·10⁻⁹ N/mm², die Reaktion an x = 200 bei 80 000 N auf 10⁻⁹ N. Im Referenzlauf liegen die
beiden Wege bei σ_hs höchstens 0,86 % und bei σ_xx höchstens 0,53 % auseinander. Rechts und links
unterscheiden sich die σ_hs um höchstens 0,28 %, gespiegelt um y = 40 um höchstens 0,43 %. Das ist
Netzeinfluss, denn das Modell ist in beiden Richtungen symmetrisch.

| y [mm] | σ_hs rechts [N/mm²] | σ_hs links [N/mm²] |
|---|---|---|
| 32 | 130,14 | 130,48 |
| 36 | 140,33 | 140,63 |
| 40 | 142,74 | 143,14 |
| 44 | 140,15 | 140,46 |
| 48 | 130,42 | 130,33 |

Reaktionskraft in x an x = 200: 81 845,23 N.

## Grenzen dieses Stands

Die Anfrage verlangt am Nahtübergang eine Kantenlänge von höchstens t/10 = 1 mm. Gemessen an allen Kanten
der Tetraeder mit einer Ecke höchstens 1,5 mm vom Übergang liegt sie bei diesem Netz im Median bei 1,33 mm
(90 % unter 1,75 mm, größte 2,20 mm). Zwischen dem 2,5-mm-Netz und diesem Netz ändert sich σ_hs nach
Session B um 3,6 %. Die Netzkonvergenz ist damit nicht belegt. Ein Lauf auf dem 0,5-mm-Netz (6,45 Mio.
Freiheitsgrade) ist vorbereitet, braucht mit dem Direktlöser aber geschätzt rund 100 GB Speicher und ist
deshalb noch nicht gerechnet. Wenn er gerechnet ist, ersetzen seine Werte diese.

## Nachrechnen

```
python werkzeug/knotenblech_lauf.py <Arbeitsbaum main> knotenblech_tet10_1mm.inp <ordner_eichung> eichung
python werkzeug/knotenblech_lauf.py <Arbeitsbaum main> knotenblech_tet10_1mm.inp <ordner_referenz> referenz
python werkzeug/auswertung_a.py <ordner>     (je Ordner)
python werkzeug/auswertung_b.py <ordner>     (je Ordner)
python werkzeug/vergleich.py <ordner_eichung> <ordner_referenz> erwartung_tet10.json
```

Ein Lauf dauert etwa sechs Minuten und braucht rund 17 GB.
