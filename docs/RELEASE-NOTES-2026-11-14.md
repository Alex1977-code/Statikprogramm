# Release-Notes 14.11.2026: Behebungen nach der Prüfung mit zehn Agenten (Stände 41 bis 43)

Am 14.11.2026 haben zehn Prüfagenten den Stand vom 12.11.2026 (Stände 31 bis 40) geprüft. Die Fehler, die die eigenen Korrekturen dieser Stände erzeugt oder unvollständig gelassen haben, sind hier behoben. Der Verfahrensstand steigt von 40 auf 43; alle Stände sind Fehlerkorrekturen, ältere Ergebnisse betroffener Modelle tragen den Status „Ergebnis möglicherweise betroffen – neu rechnen“. Jede Zahl ist auf zwei Wegen geprüft (Handrechnung, Kurzstabmodell oder dieselbe Größe auf einem zweiten Programmweg).

## Wo Ergebnisse anders ausfallen

* **Stäbe mit Versatz (Stand 41).** Seit Stand 38 konnte der Querschnitt einer lotrechten Stütze mit verschiedenem Versatz an Kopf und Fuß um 90° oder 180° springen (Kopfverdrehung 0,96 statt 3,82 mrad; Kurzstabmodell 3,818 mrad). Die Querschnittsachsen kommen jetzt aus denen der Knotenlinie: die y-Achse wird senkrecht zur versetzten Stabachse projiziert (eine Projektion, nicht die kleinste Drehung). Nach Theorie III. Ordnung dreht eine Stablast auf einem Stab mit Versatz mit dem Arm mit (3171 statt 3061 kNm, Kurzstabmodell 3171 kNm). Knicken und α_cr im Modus „automatisch“ berücksichtigen eine Sollkraft mit Verriegelung (Knickfaktor 817,7 statt 1038,8; α_cr „automatisch“ war „∞“). Stockt Theorie II. Ordnung an einem Stab mit Versatz, rechnet sie mit voller Matrix weiter; bleibt sie unkonvergiert, gibt es eine Fehlermeldung statt eines Ergebnisses. Ein Versatz, der die Stabenden aufeinanderlegt, ist ein FEHLER der Modellprüfung.
* **Gewölbte Schalenflächen (Stand 42).** Eine gewölbte Fläche aus mehreren Netzstücken wird je Stück nach dem Randumlauf ausgerichtet (Zylindersegment 300° mit gelöschtem Streifen: 21,8 statt 47,5 kN). In einer Situation mit Stellung behalten die Elemente die Lage des Grundmodells, und die Stellung dreht die Geometrie der Bögen mit (die Last wirkte vorher in Gegenrichtung). Wasserdruck an einem Mantel über 180° wirkt überall auf derselben Seite (43,3 kN, von Hand 43,4 kN; vorher 78,4 kN).
* **Wind an freien Wänden (Stand 43).** Eine freie Wand oder Tafel aus mehreren Flächen, die sich berühren und in derselben Richtung stehen, ist eine Wand: Zonen ab den Enden der ganzen Wand (30 × 3 m aus drei Flächen 68,5 statt 80,3 kN). Volumenflächen nahezu parallel zum Wind bekommen keine Nettolast (Stirnfläche bisher 1,18 kN quer zum Wind).

## Meldungen und Status

* Der Status bleibt stehen, solange das Modell selbst erneuert werden muss: getrenntes Netz an doppelten Randlinien („Netz neu erzeugen“), altes Druckfeld eines strömungsnumerischen Wasserdrucks an Schalen („Wasserdruck neu erzeugen“), alte Kontaktfuge an Schalen („Kontaktfugen neu ausführen“). Bisher verschwand er nach „neu rechnen“.
* Eine Kontaktfuge zwischen zwei Schalen mit Spalt meldet nicht mehr „durchdringend“. Wind und Wasserdruck schreiben umgedrehte Elemente ins Protokoll. Der Ladehinweis zu Windabmessungen erscheint an freien Wänden nur noch bei einer echten Änderung. Stand 38 trägt in der Verfahrenstabelle das richtige Datum 14.11.2026.

## Zweiter Teil: ältere Fehler aus der Prüfung (Stände 45 bis 50)

Diese Fehler bestanden schon vor dem 12.11.2026; die Prüfagenten haben sie am 14.11.2026 gefunden. Der Verfahrensstand steigt auf 50.

### Wo Ergebnisse anders ausfallen

* **Nachweise und Werkstoff (Stand 45).** Umfangsbeulspannung langer Zylinder nach EN 1993-1-6 D.1.3.1 (r 1 m, t 10 mm, l 100 m: 5,78 statt 39 222 N/mm², Ausnutzung 5,86 statt 0,06). Ebene Beulfelder mit gegenläufiger Normale (25,9 statt 11,7 N/mm²). Anschlussbleche mit f_y/f_u ihrer eigenen Dicke (Naht an 50-mm-Kopfplatte 417,8 statt 453,3 N/mm²). Über 80 mm ohne Dickentabelle kein still angenommener Wert mehr, sondern „f_y nach Erzeugnisnorm eintragen“; dafür hat der Werkstoffdialog die Zeile „f_y/f_u über 80 mm (Erzeugnisnorm)“. Ermüdung von Schrauben über M30 mit k_s = (30/d)^0,25 (M36: Schädigung 0,031 statt 0,025; am Drehlager Kerbfall-Vorschlag der Zugstäbe Rund 40 46,5 statt 50). I_w der U-Profile auf der Mittellinie (UPN 200: 10 499 statt 12 277 cm⁶), beim Öffnen auf Nachfrage umzustellen. Anschlussmeldungen zählen Elemente ab 0.
* **Import (Stand 46).** RFEM-6-Eigengewicht aus der Wichte γ wie in RFEM (Stahl 78,5 statt 77,0 kN/m³). IFC/SDNF übernehmen die Einheit der Datei (vorher 1000-fach zu groß über den Dialog), IFC Flächen- und Trägheitsmomenteinheiten, Nastran/Abaqus in mm vollständig umgerechnet, Tabellen im RFEM-Aufbau im Rundlauf vollständig, unbekannte Einheiten gewarnt, alte Statik3D-SAF-Federn richtig, SAF-Kategorien ohne Spalte „Category“. Das Drehlager V15_4 ist von der Eigengewichtsänderung nicht betroffen (kein Lastfall mit Eigengewicht).
* **Anzeige und Eingabe (Stand 47).** Verformungsnachweis „Stab“ mit φ wird abgewiesen (zeigte 0,00 mrad „erfüllt“ statt 10,32 mrad „nicht erfüllt“). Eigenes Feld für die Drehfedersteifigkeit im Register Lager. Browser: Antriebsmoment einer Stellung in kNm, Knoten ab 0. Tabellen „Lasten“ und „Umhüllende“ mit eingestellter Einheit, Beschriftungen bei 0 Nachkommastellen, keine wissenschaftliche Schreibweise in Bericht und Farbskala.
* **Theorie II./III. Ordnung (Stand 48).** Längsgelenk mit Last in Stabrichtung: N in K_G, α_cr, Stabteilung und Feldanteil als Mittel der Stabend-Normalkräfte (α_cr 2,60 statt „∞“; Theorie III. Ordnung 5,06 statt 3,13 kNm). Gelenke an Wölbbalken in der Steifigkeit (0 statt 16,9 kNm am Gelenk). Theorie III. Ordnung mit Wölbkrafttorsion wird mit Klartext abgewiesen.
* **Wind und Wasserdruck (Stand 49).** Nordsee nach NA.B.2 mit festen Werten (1,50 statt 0,84 kN/m² bei 10 m). Tab. 7.9 nach l/h (Wand 30 × 3 m: 94,4 statt 68,5 kN). Zonen entlang der Wand, keine Nettolast bei Wind parallel zur Wand, auch an Schalen. Strömungsnumerik rechnet geneigte (> 0,1°) und waagerechte Schalen analytisch, mit Meldung (80°: 61,3 statt −2,6 kN).
* **Netz (Stand 50).** Eine einzeln neu vernetzte Fläche nimmt ihre vernetzten Nachbarn mit (149,6 statt 397,7 mm); gerade Linie und Polylinie auf derselben Strecke werden verbunden (150,0 statt 407,0 mm); Warnung vor der Rechnung bei getrenntem Netz.
* **Flächenlager.** Dateien von vor dem 12.11.2026 mit Flächenlagern mit Elementliste zeigen den Hinweis „Flächenlager nach Neuvernetzen prüfen“, bis er per Rechtsklick bestätigt ist.

### Berichtigung früherer Zahlen

Die Summen der freistehenden Wand in den Release-Notes vom 12.11.2026 (Stand 39: Wand 10 × 0,3 × 3 m 26,8 kN) und im ersten Teil oben (Stand 43: Wand 30 × 3 m 68,5 kN, 10 × 3 m 26,8 kN) rechneten mit der falschen Zeile l/h ≤ 3 der Tab. 7.9. Richtig sind 28,0 kN (l/h = 3,3) und 94,4 kN (l/h = 10). Die Aussagen „einmal statt doppelt“ und „als eine Wand“ bleiben richtig.

## Dritter Teil: zweite Prüfrunde (Stände 51 bis 58)

Zehn Prüfagenten haben den Sammelzweig nach PR #45 und #46 geprüft (Befundliste `BEFUNDE-2026-11-14-RUNDE2.md` auf dem Desktop). Acht Agenten haben die Befunde behoben; der Verfahrensstand steigt auf 58. Jede Zahl ist auf zwei Wegen geprüft.

* **Ermüdung und U-Profile (Stand 51).** Die Stabmaske behält den Kerbfall-Vorschlag mit k_s (am Drehlager 16 Zugstäbe Rund 40, 46,53 N/mm²); bis dahin löschte OK ihn. I_w der UPN mit Flanschneigung (UPN 200: 9 559,6 statt 10 499,5 cm⁶, M_cr bis −2,4 %), S_ω des U-Profils mit richtigem Vorzeichen (τ_w bisher etwa doppelt), Doppel-U erkannt.
* **Netz (Stand 52).** Mitvernetzte Nachbarflächen behalten Elementlasten, Abschaltungen und Teil-Flächenlager (bisher 6,2 statt 86,2 kN Auflagerkraft ohne Meldung). Fuge zwischen Schalen nicht mehr als „nicht verbunden“ gewarnt, Rippen und Polylinien gemeldet, Flächenlager-Hinweis übersteht Umbenennen.
* **Werkstoff und Anschluss (Stand 53).** Kopfplatte über 80 mm behält ihre Drehfeder (Kragarm 39,97 statt 25,88 mm); Sortenwechsel leert die Werte über 80 mm; Kreisring meldet „Auflage nicht beurteilt“; Bericht zeigt C_θ,s; Anschlussorte ab 0.
* **Import (ohne eigenen Stand).** IFC mm² richtig (vorher 1000-fach), SAF ständige Gruppen bleiben ständig, RFEM-Eigengewicht mit reinen Wichte-Werkstoffen, Tabellen-Rundlauf mit Seil und Kombinationen.
* **Schalenlage und Wasserdruck (Stand 55).** Gewölbte Flächen mit Loch richtig ausgerichtet; Wasserdruck mit globaler Richtung auf die Projektion (Entscheidung des Anwenders, 45°: 61,3 statt 86,6 kN); geneigte Volumenränder analytisch (bisher −7,1 %); Protokoll mit richtiger Breite und Resultierender.
* **Status und Wind (Stand 56).** Erhöhte freie Wand mit h = Wandhöhe (Entscheidung des Anwenders; 30 × 3 m auf 10–13 m: 157,7 statt 140,2 kN, Tafel-Hinweis bei Abstand ≥ h/4); alte schräge Wände vor Stand 33 und Importkorrekturen behalten ihren Status nach „neu rechnen“; Versatz mit nur Eigengewicht nach Th III gemeldet. „Kleinste Drehung“ heißt richtig „Projektion“ (Rechnung unverändert).
* **Anzeige (Stand 57).** Verformungsnachweis „Stab“ nur uy, uz, u; Verdrehungen nur absolut; Browser behält das Antriebsmoment; Zählung ab 0; Umhüllende mit eingestellter Genauigkeit; Bericht ohne wissenschaftliche Schreibweise.
* **Theorie II. Ordnung (Stand 58).** Mittel der Normalkraft bei Last in Stabrichtung, unabhängig von Gelenk und Elementrichtung (ein Element: 4,95 statt 11,56 bzw. 3,13 kNm); mit der Vorgabe-Teilung höchstens 0,1 % Änderung.

## Nicht enthalten

* Nebenbefunde der Agenten, je eine Zeile in der Befundliste und in den Berichten, unter anderem: Schubbeulen von Zylindern mit den Bereichen des Meridiandrucks, Beulnachweise ohne Werkstoff fallen auf 235 zurück, Sonderregeln der Anzeigetafel nach 7.4.3, Feldanteil ohne Gelenk mit der Kraft am Stabanfang, Eckausbildung der freien Wand, Stellungsmaske zählt Knoten ab 1.
* Vorschlag an den Anwender offen: beim Neuvernetzen einer Fläche die Knoten der Nachbarn wiederverwenden, damit zusammenhängende Konstruktionen nicht ganz neu vernetzt werden.
