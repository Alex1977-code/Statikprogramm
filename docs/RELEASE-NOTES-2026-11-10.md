# Statik3D – Release-Notes vom 10.11.2026 (Rest der Befundliste: A5, A12/A13, A16, A19, Nebenbefunde, Gruppen 5 und 6)

Diese Notizen schließen an die Release-Notes vom 09.11.2026 nachts an (Beispielbibliothek, Gruppen 3 und 4, Verfahrensstand 20). Sie beschreiben, was dort unter „Nicht enthalten“ stand und inzwischen entschieden und gebaut ist. Jede Änderung, die Ergebnisse berührt, steht als Fehlerkorrektur in der Verfahrenstabelle; der Verfahrensstand ist jetzt 28. Ältere Ergebnisse eines betroffenen Modells tragen beim Öffnen „Ergebnis möglicherweise betroffen – neu rechnen“. Einzelheiten stehen im Benutzerhandbuch.

## Wo Ergebnisse anders ausfallen

* **Einwirkungen der DIN 19704 im Generator (A5, Stand 21).** G_A und W_S zählen als ständig, W_V, EIS, SCHWALL, WIND_B, A_M und A_MG als veränderlich, ANPRALL und KLEMM als außergewöhnlich. Für ERD und MONT bildet der Generator keine Kombination und sagt das, statt den Lastfall still wegzulassen.
* **Geschichtete Schale unter Temperatur (Stand 22).** Die Rückrechnung der Momente zieht bei einem unsymmetrischen Aufbau den Anteil B·α·ΔT ab. Eine frei gedehnte Platte aus 5 mm mit E = 210 000 und 5 mm mit E = 70 000 N/mm² zeigte unter ΔT = 50 K ein Moment von 1 500 Nm/m und 90 N/mm² Vergleichsspannung, jetzt 0. Verformungen und Lagerkräfte waren richtig.
* **Stab mit Gewinde und Anschlussvorschlag ohne f_u (Stand 23).** Fehlt im Werkstoff f_u, gibt es keinen Nachweis und keinen Vorschlag, sondern eine Meldung mit dem Namen des Werkstoffs. Vorher rechnete der Stab mit Gewinde mit 1,3·f_y (640 → 832 N/mm²), der Anschlussvorschlag ohne Festigkeiten mit S355.
* **Stäbe mit Versatz in α_cr und Theorie II. Ordnung (Stand 24).** Die geometrische Steifigkeit wirkt an den Stabenden. Druckstab 0,2 m neben seiner Knotenlinie: α_cr 2,000 statt 1,158.
* **Schubweiche Balken im Feld nach Theorie II. Ordnung (Stand 25).** Der Feldanteil N·w nimmt die Schubdurchbiegung mit. Einfeldträger mit N_E/(G·A_s) = 0,1 und Druck 0,6·N_cr in einem Element: Feldmoment 57,21 statt 50,30 kNm (geschlossen 57,23 kNm).
* **Stabendgelenke nach Theorie III. Ordnung (Stand 26).** Die Tangente kondensiert die geometrische Steifigkeit an Gelenken. Mit einer Pendelstütze als Balken mit Gelenken neben einem Kragstiel fand die Rechnung vorher ab 5/6 der Knicklast kein Gleichgewicht; bei 0,9 der Knicklast jetzt 19,843 mm (von Hand 19,841 mm).
* **Schalenflächen ohne gemeinsame Linie (A19, Stand 27).** Der Vernetzer teilt im Netz an fremden Knoten und Linien, wie in RFEM „Knoten auf Linie“ und „Linie in Fläche“. Stoß mit ungeteilter Linie: 0,143 statt 0,742 mm; Rippe auf ungeteilter Platte: 0,51 statt 33,1 mm. Knoten, Linien und Flächen des Modells bleiben unverändert. Wirkt nach dem Neuvernetzen.
* **Deckungsgleiche Trennflächen zweier Körper (A16, Stand 28).** Nennt keine Kontaktbedingung die Stelle, vernetzt das Programm beide Flächen als eine gemeinsame. Zwei Würfel unter Zug: 0,0952 statt 0,1446 mm. Mit Kontaktbedingung gilt der Kontakt. Wirkt nach dem Neuvernetzen.

## Neue Meldungen und Sperren

* **Flächenlager in Flächenachsen auf schräger, gekrümmter oder beidseitiger Fläche (A12, A13).** Ein solches Lager wirkt je Fläche entlang einer globalen Achse. Weicht die Normale um mehr als 1° davon ab, ist die Fläche gekrümmt oder liegt sie zwischen zwei Körpern, meldet die Modellprüfung einen Fehler, und die Rechnung startet nicht. Ausgenommen ist ein Lager, das in allen drei Richtungen gleich wirkt. **Das Drehlager (Z-Modell) ist betroffen:** Das Lager „Starr“ nennt vier Trennflächen zwischen zwei Körpern (F1401, F1403, F1411, F1413) und rechnet in diesem Stand erst wieder, wenn sie aus dem Lager genommen sind.
* **Eingabeprüfung vor dem Rechnen (Gruppe 5: A21, A22, A24, C10 bis C14).** Fehler mit Namen und Wert bei E-Modul null oder negativ, Querdehnzahl außerhalb des möglichen Bereichs, Dicke oder Querschnittswerten null oder negativ, tragender Fläche ohne Dicke, Lasten und Lagern auf Dingen, die es nicht gibt, und Kombinationen mit unbekanntem Lastfall. Ein Flächenlager zieht beim Löschen von Elementen mit (vorher zeigte es auf andere Elemente). Warnung, wenn die größte Verformung über 10 % der größten Modellabmessung liegt. Elementnummern in Meldungen zählen wie in den Tabellen ab 0.

## Exporte und Importe (Gruppe 6: B2 bis B6)

IFC, SAF, Abaqus, Nastran und DXF übertragen Gelenke, Fachwerkstäbe, Linienlager, Werkstoff, Profil und Lasten, soweit das Format sie trägt; alles Übrige nennt der Export als Hinweis mit Anzahl („nicht übertragen: …“). IFC-Knoten liegen nicht mehr an doppelter Stelle, Nastran schreibt mit voller Genauigkeit (Großfeld), DXF führt die Einheit, und der erste importierte Lastfall heißt LF1 statt LF1_2. Ein Rahmen kam vorher über SAF, Nastran und Abaqus ohne die Gelenke zurück (−0,62, −0,35 und −0,35 statt −1,45 mm).

## Nicht enthalten

* **Wasserdruck senkrecht zur Fläche auf Schalen:** Ohne globale Lastrichtung wirkt er an Schalen entgegen der Beschriftung der Maske, beim strömungsnumerischen Verfahren zum Oberwasser hin. Mit globaler Lastrichtung ist er richtig; die Testmodelle Fischbauchklappe, Hubtor und Stemmtor sind nicht betroffen. Die Korrektur wartet auf die Entscheidung des Anwenders.
* **Zwischenspeicher des Druckfelds** (strömungsnumerisches Verfahren): Eine geänderte Geometrie bei gleicher Knoten-, Element- und Flächenzahl wird nicht erkannt. Die Korrektur wartet auf die Entscheidung des Anwenders.
* **Theorie III. Ordnung kennt den Versatz der Stabenden nicht** (7,6 mm gegen 0,0 mm am Prüfkörper). Wartet auf die Entscheidung des Anwenders.
* **Längslasten entlang des Stabes** bleiben im Feldanteil nach Theorie II. Ordnung außen vor (ein Element bis +22,6 %, vier Elemente unter 1 %).
* **Gruppe 5, Meldungen C2 bis C9**, ist in Arbeit.
* **Flächenlager** schreibt kein Exportformat; sie stehen im Hinweis „nicht übertragen“. Die exportierten Dateien sind mit dem eigenen Import geprüft, nicht in fremden Programmen.
* **Drehlager:** Die Wirkung von A16 am Drehlager (Trennflächen ohne Kontaktbedingung werden beim Neuvernetzen zusammengelegt) ist am Modell nicht gemessen.
