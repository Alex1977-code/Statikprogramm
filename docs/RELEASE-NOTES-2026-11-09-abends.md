# Statik3D – Release-Notes vom 09.11.2026, abends (Gruppe 2 der Befundliste)

Diese Notizen beschreiben, was sich gegenüber der Fassung vom 09.11.2026 (Sammelzweig aab3401) ändert und wo Ergebnisse anders ausfallen können. Jede Änderung, die Ergebnisse berührt, steht als Fehlerkorrektur in der Verfahrenstabelle (Verfahrensstand jetzt 14). Ältere Ergebnisse eines betroffenen Modells tragen beim Öffnen „Ergebnis möglicherweise betroffen – neu rechnen“. Einzelheiten stehen im Benutzerhandbuch.

## Auf einen Blick

* **Altes Schalennetz beim Öffnen erkannt.** Ein Netz von vor dem 09.11.2026, in dem Flächen an gemeinsamen Linien nicht verbunden sind, meldet sich beim Öffnen im Protokoll und als Importhinweis („Schalennetz nicht verbunden … Bitte neu vernetzen“). Nach dem Neuvernetzen gilt der Hinweis als erledigt.
* **Bettung auf den Elementecken** bleibt so, wie sie ist; sie konvergiert mit der Netzweite. Das Handbuch beschreibt es als Festlegung.

## Wo Ergebnisse anders ausfallen

* **Wind auf Flächen (A1, A2).** Auf Schalen wirkte der Wind des Generators gegen die Windrichtung (Gebäude 10 × 20 × 8 m: ΣF −135 statt +135 kN). Jetzt drückt Luv in die Hülle hinein und saugt Lee heraus, unabhängig vom Umlauf der Randlinien und auch bei zwei Baukörpern im selben Lastfall. Baukörper sind dabei die Gebäudeflächen des Winds, die sich berühren, auch ohne gemeinsame Knoten; freie Wände verschieben keine Mitte. Volumenränder und quadratische Schalen bekommen ihre Rollen Luv, Lee, Seite und Dach. Die Kontrollsumme zeigt den tatsächlichen Lastvektor. Gemessen: Fx 135,09 kN gegen die Handrechnung 135,51 kN.
* **Projizierte Flächenlast mit negativem Wert an Volumen (A3).** „Global Z, p = −5 kN/m², auf die Projektion“ traf am Körper die Unterseite statt das Dach. Die Summe stimmte, der Angriffspunkt nicht. Schalen sind nicht betroffen. Das Drehlager ebenfalls nicht: alle 840 projizierten Lasten dort sind positiv.
* **Temperaturunterschied ΔT_z auf Schalen (A4).** Er wurde still verworfen. Jetzt krümmt er die Schale mit α · ΔT_z / t, im Lastvektor und in den Momenten; oben ist die Seite der Elementnormalen. Kragstreifen 1 m, t = 10 mm, ΔT_z = 20 K: −12,0 mm (vorher 0).
* **Abminderungsbeiwert ξ in Regel 6.10b (A6).** ξ = 0,85 traf auch die Vorspannung und das günstige G. Jetzt mindert ξ nur die ungünstigen ständigen Lasten. Beispiel Einfeldträger mit G, P nach oben und Q: max M 67,39 statt 70,09 kNm; wirkt P ungünstig, lag die alte Fassung auf der unsicheren Seite.
* **Zwangsverformung an Federlagern (A11, C1).** Sie wirkte an einer Feder nicht. Jetzt verschiebt sie den Fußpunkt der Feder (Kraft k (u − d)). An einem freien Freiheitsgrad, ohne Lager und an einem Lager mit Ausfall bleibt sie unwirksam, wird aber mit Grund gemeldet. Die falsche Meldung „ohne Lager – unwirksam“ an starren Linienlagern entfällt.
* **Anschlussnachweis ohne f_u oder f_y (A23).** Er rechnete still mit 1,3 · f_y bzw. mit S355 (355/510 N/mm²). Jetzt wird er ohne diese Angaben nicht geführt, und die Meldung nennt den Werkstoff. Mit angegebenem f_u, oder mit Stahlsorte ohne eingetragenes f_y, bleibt alles, wie es war. Steht im Werkstoff f_y und eine Stahlsorte, aber kein Wert f_u, gilt jetzt das f_u der Sorte statt 1,3 · f_y (Lasche S235: 360 statt 305,5 N/mm²; Schraubenstab M16 S355 mit f_y 640: η 1,73 statt 1,06); ältere Ergebnisse solcher Modelle tragen „Ergebnis möglicherweise betroffen – neu rechnen“.
* **Kontaktbedingung nur mit Körpern (A17).** Eine Bedingung, die nur den gelösten Körper und die Gegenkörper nennt, blieb unausgeführt; mit einer zweiten Lagerung lief die Last still daran vorbei. Jetzt sind die Flächen der Gegenkörper die Gegenseite. Das Drehlager hat keine solche Bedingung.

## Nicht enthalten

* **A5, DIN-19704-Kategorien im Generator nach EN 1990.** Die Einordnung wartet auf die Entscheidung des Anwenders.
* **A12, A13, lokales Flächenlager auf gekrümmten oder schrägen Flächen.** Das Lager wird weiter der nächsten globalen Achse zugeschlagen; der Vorschlag (vorerst Fehler statt still) wartet auf die Entscheidung des Anwenders.
* **Gruppen 3 bis 6 der Befundliste** (Theorie II. Ordnung, Volumen, Schalenspannungen in Elementachsen, Robustheit, Exporte) und die Beispielbibliothek im Menüband.
* **Nebenbei notiert, nicht geändert:** Bei Laminaten mit Kopplungsmatrix fehlt in der Momentenrückrechnung der Anteil B · α · ΔT des gleichmäßigen ΔT. Bolzennachweis und Schraubenstab nehmen bei fehlendem f_u weiter 1,3 · f_y. Der Anschlussvorschlag bemisst die Geometrie ohne Werkstoffangaben weiter mit S355.
