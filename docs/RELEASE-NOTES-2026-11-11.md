# Statik3D – Release-Notes vom 11.11.2026 (Prüfung durch zehn Agenten am 11.11.2026)

Diese Notizen schließen an die Release-Notes vom 10.11.2026 an (Verfahrensstand 28). Zehn Agenten haben das Programm am 11.11.2026 geprüft und 47 Befunde gemeldet, davon 32 aus den unveröffentlichten Änderungen seit der letzten exe. Diese 32 sind alle behoben, jeder mit einer Prüfung. Einzelheiten stehen im Benutzerhandbuch und in den Schnittstellen.

## Wo Ergebnisse anders ausfallen

Gegenüber dem, was die Release-Notes vom 09. bis 10.11.2026 beschreiben, fallen diese Ergebnisse anders aus.

* **Wind auf Schalen.** Die Mitte, nach der der Generator jede Fläche nach außen ausrichtet, kommt nur noch aus den Gebäudeflächen des Winds; freie Wände und Schilder verschieben sie nicht mehr. Baukörper sind Gebäudeflächen, die sich berühren, auch ohne gemeinsame Knoten. An einem Gebäude mit freier Wand ist ΣF_x des Gebäudes +110,73 statt −44,29 kN, an zwei Baukörpern aus Einzelschalen je 110,73 kN. Bei einer Fläche allein gibt die Rolle das Vorzeichen vor.
* **Stabendkräfte nach Theorie II. Ordnung an Gelenk und Federgelenk.** An Stäben mit Gelenk oder Federgelenk und Feldlast ist das Stabendmoment gleich dem Lagermoment (22,50 statt 27,04 kNm).
* **Quaderteilung mit Sweep.** Die Teilung [nx, ny, nz] eines abgebildeten Quaders gilt auch bei eingeschaltetem Sweep in x, y und z: [2, 3, 5] ergibt 2 × 3 × 5 statt 2 × 2 × 4 Elemente.
* **IFC-Export einer Stablast je Projektion.** Sie geht als gleichwertige Last je wahrer Länge hinaus; am Prüfstab kommt die Summe nach Export und Import mit 30 000 statt 36 056 N zurück.
* **Abaqus-Export und -Import.** n1 ist die lokale y-Achse jedes Stabs, die Stabverdrehung geht damit hinaus und kommt beim Import aus n1 zurück.
* **Nastran-Import von PLOAD1 je Projektion.** LEPR und FRPR bleiben je Richtung eine eigene Last: (4000; 0; −3000) statt (4950; 0; −4950) N.
* **Nastran-Import einer geerdeten Feder.** Eine CELAS- oder CBUSH-Feder gegen den Grund wird Lagerfeder.

## Status

* **f_u bei Stahlsorte und f_y ohne Wert f_u.** Steht im Werkstoff f_y und eine Stahlsorte, aber kein Wert f_u, gilt im Anschluss- und im Schraubennachweis das f_u der Sorte statt 1,3 · f_y. Ältere Ergebnisse solcher Modelle tragen „Ergebnis möglicherweise betroffen – neu rechnen“.
* **ξ in 6.10b, Einwirkungen der DIN 19704, Erdbeben und Montage.** Der Status bleibt, auch nach einer neuen Rechnung, bis die Kombinationen neu erzeugt sind.
* **Theorie III. Ordnung** wird im Status nicht mehr als Theorie II. Ordnung gemeldet.
* **Alte Windlasten.** Windlasten aus einem älteren Programmstand nennt das Programm beim Öffnen; ihr Status bleibt, bis sie neu erzeugt sind.
* **Federgelenk mit k = 0.** Nachgezogen werden nur Dateien, die vor diesem Stand gespeichert sind; ein am Element entferntes Gelenk bleibt weg. Ältere Ergebnisse werden mit „Ergebnis möglicherweise betroffen – neu rechnen“ geladen statt verworfen.

## Meldungen

* Element- und Knotennummern in Meldungen zählen ab 0, auch in den Meldungen zur Stabteilung für α_cr und zu Flächen ohne gemeinsame Linie (A19).
* Eine nicht ausgeführte Kontaktbedingung (C4) nennt die Folge in der richtigen Richtung: Sind die Seiten nur am gemeinsamen Rand verbunden, heißt das zu weich.
* Die Warnung zum Steifigkeitsunterschied (C9) lässt entartete Elemente aus, wie die Rechnung.
* Der Hinweis zur Plastizität (C5) zählt Stäbe in „Stabelementen“.
* Ein fremder Knoten mitten auf einem Bogen steht im Protokoll und als Warnung der Abnahme (A19).
* Ein Flächenlager mit einem einzelnen Element, das es nicht gibt, steht in der Einzahl („nennt 1 Element, das es nicht gibt“).

## Sonst

* Ein Flächenlager in Flächenachsen an einer ebenen Schalenplatte meldet keinen falschen Fehler mehr.
* Stemmtor und Hubtor der Beispielbibliothek verlangen eine Höhe von mindestens 2,19 m bzw. 1,54 m; darunter meldet der Dialog das und sperrt „Übernehmen“.
* Der Speicher der Knotenfelder ist begrenzt: Gehalten werden die Felder der zuletzt vier angesehenen Ergebnisse.
* Die Kommandozeile stürzt mit `--kombinationen` bei einem Erdbeben- oder Montagelastfall nicht mehr ab, sondern meldet den Grund und gibt 2 zurück.
