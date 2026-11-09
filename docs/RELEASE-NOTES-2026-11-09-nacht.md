# Statik3D – Release-Notes vom 09.11.2026, nachts (Beispielbibliothek, Gruppen 3 und 4 der Befundliste)

Diese Notizen schließen an die Release-Notes vom 09.11.2026 abends an (Gruppe 2, Verfahrensstand 14). Sie beschreiben die Beispielbibliothek und die Korrekturen der Gruppen 3 (Theorie II. Ordnung) und 4 (Volumen und Schalen). Jede Änderung, die Ergebnisse berührt, steht als Fehlerkorrektur in der Verfahrenstabelle; der Verfahrensstand ist jetzt 20. Ältere Ergebnisse eines betroffenen Modells tragen beim Öffnen „Ergebnis möglicherweise betroffen – neu rechnen“. Einzelheiten stehen im Benutzerhandbuch.

## Beispielbibliothek

Der Knopf **Datei → Beispielbibliothek…** ersetzt das Menü „Beispiel öffnen ▾“. Der Dialog zeigt 14 Beispiele nach Stabwerk, Flächentragwerk und Volumen, jeweils mit Beschreibung und einer Tabelle der Parameter (Wert, Einheit, Grenzen). Ein Wert außerhalb der Grenzen oder unpassend zu einem anderen Wert sperrt „Übernehmen“ und nennt den Grund. „Übernehmen“ baut das Modell; ist etwas ungespeichert, fragt das Programm vorher. Eingebaut sind die acht bisherigen Beispiele und die sechs Testmodelle vom 09.11.2026 (Doppellenkerwippkran, Förderbandbrücke, Stemmtor, Hubtor, Fischbauchklappe, Spurlager). Mit den Vorgabewerten entsteht jeweils dasselbe Modell wie vorher. Eigene Beispiele sind Python-Dateien im Ordner `Dokumente\Statik3D\Beispiele`; das Programm führt sie beim Öffnen der Bibliothek aus.

## Wo Ergebnisse anders ausfallen

* **Stabendgelenke in α_cr und Theorie II. Ordnung (A7).** Die geometrische Steifigkeit eines Balkens mit Gelenk oder Federgelenk wird jetzt wie die elastische kondensiert. Pendelstütze als Balken mit Gelenken neben einem Kragstiel: α_cr 2,000 statt 1,667, Kopfverschiebung 3,968 statt 4,960 mm. Gezogener Gelenkstab: α_cr wie mit Fachwerkstab (vorher bis 37 % zu hoch, unsichere Seite). Ein Balken aus einem Element, beidseits gelenkig, steht jetzt im Einzelknicken.
* **Schnittgrößen nach Theorie II. Ordnung (A8).** Stabendkräfte mit elastischer plus geometrischer Steifigkeit, im Feld der Anteil N·w. Einfeldträger, Druck 0,6·N_cr, ein Element: Feldmoment 57,25 statt 37,11 kNm (geschlossen 57,27 kNm). Kragarm: Stabendmoment gleich Lagermoment (vorher +7,9 %).
* **Federgelenk mit k = 0 (A10).** Es ist ein Gelenk. Bis dahin wirkte es biegesteif, wenn es im Skript oder über die Web-Schnittstelle angelegt war. Ältere Dateien ziehen es beim Öffnen nach und melden das im Protokoll.
* **Achsen der Flächenspannungen (A20).** σ_x, σ_y, τ_xy, n_x, m_x stehen im Flächensystem (x = globale X-Achse in der Elementebene), nicht mehr in der Achse der ersten Elementkante. Patchtest Zug 10 N/mm²: σ_x 10,00 an jedem Knoten (vorher 0,8 bis 9,3). Hauptspannungen und σ_v ändern sich nicht.
* **Teilung des abgebildeten Quaders (A14).** [nx, ny, nz] gilt in x, y, z, nicht mehr in der Reihenfolge der Randflächen.
* **Flächenlast auf gekrümmten Volumenseiten (A15).** Druck senkrecht auf tet10/hex20-Seiten längs der örtlichen Normale (vorher Eckennormale, bis +0,56 % Kraft). Das Drehlager hat solche Lasten; seine Ergebnisse tragen darum „möglicherweise betroffen“. Am Drehlager selbst ist die Änderung nicht gemessen; am Prüfkörper waren es 0,56 % (grob) bis 0,06 % (fein) der Last auf den gekrümmten Seiten.

## Neue Meldungen

* **Trennfläche doppelt (A16)** und **Flächen ohne gemeinsame Linie (A19)**: Warnungen der Abnahme, wenn zwei Körper je eine eigene, deckungsgleiche Trennfläche ohne Kontaktbedingung haben bzw. Schalenflächen sich ohne gemeinsame Linie berühren (Knoten auf Linie, Rippe auf ungeteilter Platte). Verbunden wird dort weiterhin nichts.
* **Stabteilung für α_cr (A9).** Liegt eine Knickhalbwelle in einem Balkenelement (α_cr·|N| ≥ 30 % der Euler-Last des Elements), steht „α_cr: Stabteilung zu grob“ in den Hinweisen und der Zusammenfassung. Mit einem Element je Halbwelle liegt α_cr bis 21,6 % zu hoch. Das Ergebnis selbst ändert sich nicht.

## Nicht enthalten

* **A5** (DIN-19704-Kategorien im Generator nach EN 1990) und **A12, A13** (lokales Flächenlager auf gekrümmten oder schrägen Flächen) warten auf die Entscheidung des Anwenders.
* **Gruppen 5 und 6** der Befundliste (Robustheit, Meldungen, Exporte).
* **A16 und A19 verbinden noch nicht**: deckungsgleiche Trennflächen zusammenlegen bzw. Flächen an fremden Knoten und Linien teilen, wartet auf die Entscheidung des Anwenders; bis dahin warnt die Abnahme.
* **Nicht geändert:** Die geometrische Steifigkeit eines Stabs mit Versatz (Exzentrizität) nimmt den Versatz weiter nicht mit. Theorie III. Ordnung kondensiert die geometrische Steifigkeit an Gelenken weiter nicht. Der Feldanteil N·w lässt Schubverformung und Längslasten entlang des Stabs aus.
