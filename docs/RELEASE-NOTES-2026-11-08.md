# Statik3D – Release-Notes vom 08.11.2026

Diese Notizen beschreiben, was sich gegenüber der Fassung vom 07.11.2026 ändert und wo Ergebnisse anders
ausfallen können. Einzelheiten stehen im Benutzerhandbuch.

## Auf einen Blick

* **Namen LF, LK und EK.** Lastfälle heißen jetzt LF1, LF2 usw., Kombinationen LK1 usw. und Ergebniskombinationen EK1 usw. Ein früherer Name bleibt als Bezeichnung erhalten. Alte Dateien werden beim Öffnen umgestellt, und die Lastfall-Generatoren vergeben die neuen Namen.
* **Lastbezug.** Flächen- und Linienlasten beziehen sich auf eine globale Achse, auf die lokalen Flächenachsen oder auf ein eigenes Koordinatensystem. Neue Flächenlasten sind in der Vorgabe global Z: −5 kN/m² wirkt also nach unten, wenn Z nach oben zeigt. Bestehende Lasten und alte Dateien bleiben unverändert. Wählt man „senkrecht zur Fläche“, nennt die Maske jetzt das Vorzeichen: Bei einer Schale wirkt die Last positiv in lokaler z-Richtung, am Rand eines Volumens drückt positiv hinein.
* **Eigene Koordinatensysteme.** Man legt sie im Modellbaum unter „Koordinatensysteme“ an, entweder aus Ursprung und drei Winkeln oder aus drei Punkten. Löschen geht nur, solange keine Last darauf verweist.
* **Flächenachsen anzeigen.** Unter *Ansicht → Anzeigen ▾ → Flächenachsen* erscheinen die lokalen Achsen jeder Fläche als Pfeile.
* **Druckfähige Lastdarstellung.** Flächenlasten werden als Pfeilfeld gezeigt, Linienlasten als Pfeilreihe. Jede Lastart hat einen eigenen Maßstab, jeder Lastfall eine Farbe, und der Schalter „Lasten beschriften“ zeigt Wert und Einheit.
* **Oberfläche.** Neu sind „+ … anlegen“ in allen Gruppen des Modellbaums, Knoten und Linien in der Ansicht anklicken statt Nummern abtippen, Knoten- und Linienfelder in Stab- und Lagermasken, „Neu“ in der rechten Maske und Linien- und Flächenlager immer im Modellbaum. Die Einstellungsmaske hat einklappbare Gruppen. Das Mausrad verstellt nur noch Felder, die man vorher angeklickt hat. Ein Klick auf eine Stellung zeigt das Modell in dieser Stellung. Zu den Lagerkräften kommen die Lagermomente.
* **Reibkontakt.** Hohe Reibbeiwerte werden fortgesetzt angefahren (μ 0 → 0,3 → 0,6 → Ziel, warm gestartet), dazu eine Line Search auf das Residuum. Vier Benchmarks sind jetzt feste Prüfungen: Hertz, schiefe Ebene, Gleitfront und Zapfen.
* **Berührungsband.** Ein Knoten gilt jetzt erst bis zu 10⁻⁶ des Suchradius als aufliegend, vorher waren es 10⁻³. Am Drehlager (μ-1-Testmodell) rechnete der Lauf mit und ohne diese Änderung bitgleich.

## Wo Ergebnisse anders ausfallen

* **Verfahrenstabelle Stand 6.** Der Gleichgewichtsbezug im Spannschritt (PR #39) ist als Verbesserung eingetragen. Ergebnisse bleiben gültig, mit Hinweis. Als Fehlerkorrekturen eingetragen sind die Gaußpunktwerte plastischer Rechnungen und die Kräfte nur numerisch gehaltener Freiheitsgrade in der Gleichgewichtskontrolle. Ältere Ergebnisse mit diesen Merkmalen tragen „Ergebnis möglicherweise betroffen – neu rechnen“.
* **Berührungsband.** Wo zwei Netze an einer Fuge zwischen 10⁻⁶ und 10⁻³ des Suchradius voneinander entfernt liegen, gilt das jetzt als Spalt und nicht mehr als Berührung. In den Prüfmodellen ändert sich dadurch die größte Verschiebung des Stempels auf dem Sockel von 0,394 auf 0,434 mm (elastisch) bzw. von 0,540 auf 0,577 mm (plastisch).

## Nicht enthalten

* **Z-Fassung des Drehlagers.** Das sind Modelldaten und keine Programmänderung; der Mittel-Lauf steht noch aus.
* **Projizierte Flächenlasten auf Schalen und Koordinatensysteme beim Drehen um x.** Die Korrekturen liegen auf einem eigenen Zweig und warten auf Freigabe.
* **Offene Punkte:** test_gleitweg (die Prüfung erwartet noch Verfahrensstand 4), die schiefe Ebene bei 50°, die wissenschaftliche Schreibweise in der Rechenliste, die Auflagerkräfte der Linien- und Flächenlager und der VTK-Export.
