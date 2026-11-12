# Statik3D – Release-Notes vom 12.11.2026

Diese Notizen schließen an die Release-Notes vom 11.11.2026 an. Der Verfahrensstand steigt von 28 auf 30. Beide neuen Stände sind Fehlerkorrekturen: Ältere Ergebnisse betroffener Modelle tragen den Status „Ergebnis möglicherweise betroffen – neu rechnen“.

## Wo Ergebnisse anders ausfallen

* **Interne Stabteilung nach Theorie II. und III. Ordnung.** Balken werden für diese Rechnungen intern geteilt, das Modell bleibt unverändert. Jeder Stab bekommt mindestens die Stabteilung der Netzeinstellungen (Vorgabe 10), nach Theorie III. Ordnung doppelt so viele Abschnitte. Geteilt wird nur, wo die Normalkraft nach Theorie I. Ordnung mindestens ein Tausendstel der Euler-Last des Elements erreicht. Am links eingespannten, rechts gelenkigen Einfeldträger (6 m, q = 5 kN/m, Druck 0,6·N_cr) in einem Element ergibt Theorie II. Ordnung jetzt 44,21 statt 22,50 kNm am Lager; die Differentialgleichung gibt 44,207 kNm. Theorie III. Ordnung ergibt 44,07 kNm (−0,3 %). Ein Stab, der schon fein geteilt ist, rechnet wie bisher.
* **Berichtigung zu den Release-Notes vom 11.11.2026.** Dort stand, das Stabendmoment am Gelenkstab mit Feldlast sei jetzt gleich dem Lagermoment, „22,50 statt 27,04 kNm“. Die Gleichheit stimmt, der Wert 22,50 kNm war aber das Ergebnis nach Theorie I. Ordnung, weil ein Element den Anteil der Normalkraft nicht abbilden konnte. Richtig sind 44,21 kNm.
* **Feld eines einzelnen Elements nach Theorie II. Ordnung.** Am selben Träger zeigte das Feld ohne Teilung bis über 10 Millionen kNm, weil die Iteration im Element auseinanderlief. Mit der Teilung stimmt das Feld an jeder Stelle mit zehn von Hand geteilten Elementen überein.
* **Stabendkräfte nach Theorie III. Ordnung am Gelenk mit Stablast.** Das Moment am Gelenk ist 0, vorher stand dort q·L²/12 (15,0 kNm am Prüfträger), am Stabanfang 15,0 statt 22,5 kNm. Das Gleichgewicht der Knoten war schon vorher richtig.

## Meldungen

* **Flächenlager in Flächenachsen auf Schalen.** Ein einzelnes umgedrehtes Schalenelement in einer Schalenfläche ohne Körper löst den FEHLER „hat Facetten nach beiden Seiten“ nicht mehr aus. Die Auflagerkräfte sind bitgleich mit denen ohne das umgedrehte Element.
* **Wind auf einer einzeln stehenden Gebäudefläche.** Der Generator rechnet sie weiter nach ihrer Lage (allein: Luv bzw. Dach) und nennt im Protokoll den Hinweis, dass sie nach DIN EN 1991-1-4 eine freistehende Wand (7.4, c_p,net nach Tabelle 7.9) bzw. ein freistehendes Dach (7.3) ist. Die Rolle setzt der Anwender.
* Der Hinweis „α_cr: Stabteilung zu grob“ betrifft nur noch Elemente, die nicht geteilt werden (Versatz, Wölbkrafttorsion), oder die Stabteilung 1.

## Zweiter Teil: zehn Korrekturen vom Nachmittag (Stände 31 bis 37)

Der Verfahrensstand steigt weiter von 30 auf 37. Alle sieben neuen Stände sind Fehlerkorrekturen; ältere Ergebnisse betroffener Modelle tragen den Status „Ergebnis möglicherweise betroffen – neu rechnen“. Die Prüfmatrix ist zahlengleich mit dem Stand vor diesen Korrekturen.

### Wo Ergebnisse anders ausfallen

* **Lage der Schalenelemente (Stand 31).** Die Lage eines Schalenelements ändert die Rechnung nicht mehr. Beim Vernetzen, beim Import, vor dem Erzeugen von Wind- und Wasserdrucklasten und vor jeder Rechnung richtet das Programm alle Schalenelemente einer Fläche zur Flächennormalen aus dem Randumlauf aus, Elemente ohne Fläche je zusammenhängendem Stück. Was zur Fläche gehört (Lasten, ΔT_z, Schichtaufbau), gilt zur Flächennormalen; was am einzelnen Element hängt, dreht physikalisch gleich mit. Das Protokoll nennt jedes umgedrehte Element. Eine Kontaktfuge an einer Schale findet ihre Gegenfläche jetzt unabhängig von der Richtung der Normalen, und die Flächenachsen in der Ansicht zeigen immer die Normale der Fläche. Bis dahin wirkten an einem gespiegelten Element Flächenlast, ΔT_z, Wasserdruck und Wind verkehrt herum (eine Platte mit einem von 64 Elementen gespiegelt verlor 3 % ihrer Auflagerkraft), und oben, unten, m_x, m_y und n_xy wechselten in der Anzeige das Vorzeichen. Eine unabhängige Prüfsuite rechnet jedes Prüfmodell wie vernetzt und mit gespiegelten Elementen; sie bestand vorher 35 von 77 Prüfungen, jetzt 77 von 77.
* **Wasserdruck an Schalen ohne globale Richtung (Stand 32).** Er wirkte zum Wasser hin statt vom Wasser weg, analytisch wie strömungsnumerisch. An einer Wand 2 × 3 m mit 2,5 m Wasser (½·γ·h²·b = 61,31 kN, gerechnet 61,30 kN) biegt sie sich jetzt 64,7 mm vom Wasser weg statt zum Wasser hin. Fischbauchklappe, Hubtor und Stemmtor haben eine globale Richtung und sind nicht betroffen (Lastvektor bitgleich). Der Zwischenspeicher des Druckfelds erkennt geänderte Geometrie jetzt auch bei gleicher Knotenzahl.
* **Wind (Stand 33).** Freistehende Wände und Anzeigetafeln aus Schalen bekommen die Last immer in Windrichtung, gleich wie herum die Linien eingegeben sind (bisher je nach Umlauf ±26,01 kN an einer Wand 10 × 3 m). Gebäudemaße h, b und d kommen nur noch aus den Gebäudeflächen (ein Quader 10 × 10 × 10 m bekam mit einer freien Wand daneben b/d = 45/30 m und ΣF 151,9 statt 95,4 kN). Eine Flächenlast auf die Projektion mit linearem Verlauf trifft je Stelle die richtige Seite (0 auf −5 kN/m² global Z belastete die Unterseite statt des Dachs).
* **Versatz nach Theorie III. Ordnung (Stand 34).** Der Versatz der Stabenden fiel nach Theorie III. Ordnung still weg. Er wirkt jetzt als starrer, mitdrehender Arm; bei kleinen Lasten gleich Theorie I./II. Ordnung, bei großen Verdrehungen (bis 32°) gleich einem Modell aus starren Kurzstäben auf 0,03 %.
* **Theorie II. Ordnung (Stand 35).** Balken mit Wölbkrafttorsion führen jetzt (k + k_G)·u und N·w im Feld (Kragarm in einem Element: Stabendmoment 22,16 kNm gleich dem Lagermoment, vorher 24,00 kNm; Differentialgleichung 22,23 kNm). Ein Stab mit Längsgelenk geht ohne Scheinnormalkraft in K_G und α_cr ein (Stütze unter Querlast 3,125 kNm = q·L²/8, vorher 3,88 bei Druck und 2,69 bei Zug).
* **Schalen, Beulen, Anschlüsse (Stand 36).** Die Randspannungen geschichteter Schalen folgen der Laminattheorie (Zweischichter unter ΔT 50 K: −60/−180 statt −30/−210 N/mm²). Der Beulnachweis drehte seit dem 09.11.2026 die Flächenspannungen ein zweites Mal mit der ersten Elementkante (bei 90° waren Längs- und Querspannung vertauscht); das ist behoben. Ein Anschluss mit Kehlnähten ohne Stahlsorte wird nicht mehr still mit S355 (β_w = 0,9) nachgewiesen, sondern gemeldet.
* **Netz (Stand 37).** Doppelte Randlinien zweier Schalenflächen sind im Netz immer verbunden (Platte 4 m aus zwei Flächen: 149,6 statt 397,7 mm). Ein Flächenlager mit Elementliste rückt beim Neuvernetzen in der Oberfläche nicht mehr still auf andere Elemente.

### Exporte

* SAF: Stablast je Projektion mit Location „Projection“ (schräge Lasten als gleichwertige Last je wahrer Länge, mit Hinweis), Lastfallkategorien mit Action type, Load type und Lastgruppe, Federsteifigkeiten in MN/m bzw. MNm/rad (bisher kamen sie nach dem Rundlauf 10⁶-fach zurück). SAF-Dateien mit gefederten Knotenlagern, die Statik3D vor dem 12.11.2026 geschrieben hat, bitte neu exportieren.
* Nastran und Abaqus: tetp2 bis tetp4 gehen über die Eckknoten als lineare Tetraeder hinaus, mit Hinweis. Ebene Elemente nennen Nastran und IFC als fehlend, DXF schreibt sie als Flächen. Bis dahin fehlten sie ohne Wort.

### Drehlager, Z-Modell

* Im Z-Modell Z3c sind die vier Trennflächen F1401, F1403, F1411 und F1413 aus dem Flächenlager „Starr“ genommen (Freigabe des Anwenders vom 12.11.2026). Die Geometrie ist unverändert. Die Prüfung vor der Rechnung meldet keinen FEHLER mehr. Die Dateien liegen als Kopien mit dem Zusatz `_ohne_trennflaechen`; die Originale sind unverändert.

### Offen

* Theorie I. und II. Ordnung rechnen einen Stab mit verschiedenem Versatz an Anfang und Ende entlang der Knotenlinie; dabei geht das Momentengleichgewicht verloren (Beispiel: 5,0 statt 0 kNm Einspannmoment). Entscheidung des Anwenders steht aus.
* Eine freie Wand aus einem Volumen, bei der beide Seitenflächen gewählt sind, bekommt die Nettowindlast doppelt. Entscheidung steht aus.
* R-Modell und G0-Dateien des Drehlagers haben die vier Trennflächen weiter im Lager „Starr“ und rechnen mit dem heutigen Stand nicht. Entscheidung steht aus.
