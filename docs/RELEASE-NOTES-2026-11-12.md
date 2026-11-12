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

## Offen

* **Lage einzelner Schalenelemente.** Außer am Flächenlager hängt die Rechnung noch an der Lage des einzelnen Elements. Betroffen sind Flächenlasten in lokal z und lokal y, Wasserdruck nach der Näherungsformel ohne Richtung, Wind auf freien Wänden und Schildern, der Temperaturunterschied oben − unten, unsymmetrische Laminate, Kontakt und Fugen an Schalen sowie die Anzeige von „oben“, „unten“, m_x, m_y und n_xy. Der Vernetzer erzeugt einheitlich orientierte Netze, betroffen sind von Hand gedrehte oder so importierte Elemente (Nastran, Abaqus).
