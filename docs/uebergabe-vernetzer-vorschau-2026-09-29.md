# Für die Vernetzersitzung: die Elementzahl-Vorschau eines Volumens ist um Faktor 2 bis 41 daneben

Übergabe aus der Hauptprogramm-Sitzung, 29.09.2026.
Zweig `claude/statikprogramm-analog-ansys-bzfhij`, Stand `c44ea0e`.

Ich fasse `statik3d/netzdichte.py` und den Vernetzer **nicht** an — das ist euer
Thema (`docs/Mitarbeit.md`, Abschnitt 5). Hier steht nur, was ich gemessen habe,
damit ihr es aufgreifen könnt, ohne es nochmal zu messen.

## Was gemessen ist

`netzdichte.vorschau` sagt für ein Volumen eine Elementzahl voraus; verglichen
mit dem, was `mesher3d.mesh_koerper_frei` danach wirklich erzeugt (29.09.2026,
Stand `c44ea0e`, Voreinstellungen):

| Körper | h | Vorschau | wirklich | Faktor |
|---|---|---|---|---|
| Quader 900 × 900 × 35 mm | 50 mm | 469 | 2 219 | **4,7** |
| derselbe, mit 20-mm-Bohrung | 50 mm | 469 | 19 192 | **40,9** |
| Würfel 1 × 1 × 1 m | 100 mm | 6 569 | 14 203 | **2,2** |

Zwei Dinge fallen auf:

1. **Auch ohne Loch liegt sie um Faktor 2 bis 5 zu niedrig.** Das ist der
   Umrechnungsfaktor Zelle → Tetraeder: ein Würfel der Kante h zerfällt nicht in
   einen Tetraeder, und die Delaunay-Verfeinerung setzt zusätzlich Innenpunkte.
2. **Mit Loch ist sie um Faktor 41 daneben, bei unverändertem Vorschauwert
   (469).** Die Vorschau sieht das Größenfeld gar nicht: die Kränze um die
   Bohrung und `h_lokal = min(h, Randkante + WACHSTUM · d)` verfeinern das Netz
   örtlich um ein Vielfaches, und genau das geht in die Schätzung nicht ein.

Die Reihenfolge der Größe ist also nicht das Problem — das Größenfeld ist es.

## Was daraus folgen würde

Eine Vorschau, die stimmt, muss von demselben Feld ausgehen, mit dem der
Vernetzer arbeitet. Seit `netzfeld.py` gibt es das Feld als eigenes Modul; die
naheliegende Form ist das Integral

    n ≈ c · ∫ dV / h_lokal(x)³

mit c aus einer Messung an einfachen Körpern (nicht geschätzt — der Faktor
enthält sowohl die Tetraeder je Zelle als auch die Verfeinerung). Abgetastet
auf demselben Gitter, das der Vernetzer ohnehin legt, kostet das Integral
nichts Nennenswertes.

Ob das der Weg ist, entscheidet ihr — ihr habt das Feld gebaut.

## Nachzurechnen

Das Skript, mit dem die Tabelle entstanden ist, hängt nicht am Modell des
Anwenders; es baut die drei Körper selbst (`tests.test_mesher3d.prisma`,
`kreis_punkte`) und ruft `netzdichte.vorschau` gegen
`mesher3d.mesh_koerper_frei`. Drei Fälle, je eine Zeile.

## Nebenbei aufgefallen

`python -m tests.test_mesher3d` ist auf diesem Stand bei **241 von 246**. Die
fünf Fehlschläge sind vier Rücknahmeproben und eine Bolzen-Buchsen-Probe:

```
Ruecknahmeprobe: ohne die drei Kuren und ohne Kippen fehlen am L-Prisma wieder 0,079 %
  Ruecknahmeprobe: ohne Kippen bleibt die Luecke (gemessen 0,0003 bis 0,0024 %) und wird gemeldet
  Ruecknahmeprobe: mit der alten Kappenregel kommen die geraden Kanten wieder
  ohne oertliche Anlaeufe retten innere Punkte und Entzerren die Elemente, aber mit schlechterer Form
Bolzen r 10 in Buchse r 30 (h 25 mm, 36 Grad): kein Rueckfall, groesster Weg der Sehnenpfeil 1,022 mm
```

Sie kommen nicht von meinem Commit: `c44ea0e` unterscheidet sich von `bdac39d`
ausschließlich um 18 Zeilen Docstring in `randkantenlaenge`, ohne eine Zeile
Code (`git diff bdac39d c44ea0e`). Falls das laufende Arbeit ist, ist alles
gut; falls nicht, wisst ihr es jetzt.

## Und eine Bitte zur Abstimmung

Am 29.09. habe ich Befund C (RFEMs `ResultCombination` als Umhüllende) gebaut
und wieder verworfen, weil ihr dasselbe schon vollständiger gelöst hattet
(`Combination.alternativen`, `ist_umhuellende`, Teilung je Situation). Das waren
ein paar Stunden für nichts. Der Grund: ich habe auf dem gemeinsamen Zweig
gearbeitet, ohne vorher zu holen, und ihr führt eure Arbeit über Themenzweige
mit Pull Request dorthin.

Die Regel dagegen steht in `docs/Mitarbeit.md` — sie ist nur nicht befolgt
worden. Abschnitt 7 sagt jetzt, wer welchen Bereich in der Hand hat.
