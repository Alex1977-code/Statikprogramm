# Release-Notes 14.11.2026: Behebungen nach der Prüfung mit zehn Agenten (Stände 41 bis 43)

Am 14.11.2026 haben zehn Prüfagenten den Stand vom 12.11.2026 (Stände 31 bis 40) geprüft. Die Fehler, die die eigenen Korrekturen dieser Stände erzeugt oder unvollständig gelassen haben, sind hier behoben. Der Verfahrensstand steigt von 40 auf 43; alle Stände sind Fehlerkorrekturen, ältere Ergebnisse betroffener Modelle tragen den Status „Ergebnis möglicherweise betroffen – neu rechnen“. Jede Zahl ist auf zwei Wegen geprüft (Handrechnung, Kurzstabmodell oder dieselbe Größe auf einem zweiten Programmweg).

## Wo Ergebnisse anders ausfallen

* **Stäbe mit Versatz (Stand 41).** Seit Stand 38 konnte der Querschnitt einer lotrechten Stütze mit verschiedenem Versatz an Kopf und Fuß um 90° oder 180° springen (Kopfverdrehung 0,96 statt 3,82 mrad; Kurzstabmodell 3,818 mrad). Die Querschnittsachsen bleiben jetzt die der Knotenlinie, nur auf die versetzte Stabachse gedreht. Nach Theorie III. Ordnung dreht eine Stablast auf einem Stab mit Versatz mit dem Arm mit (3171 statt 3061 kNm, Kurzstabmodell 3171 kNm). Knicken und α_cr im Modus „automatisch“ berücksichtigen eine Sollkraft mit Verriegelung (Knickfaktor 817,7 statt 1038,8; α_cr „automatisch“ war „∞“). Stockt Theorie II. Ordnung an einem Stab mit Versatz, rechnet sie mit voller Matrix weiter; bleibt sie unkonvergiert, gibt es eine Fehlermeldung statt eines Ergebnisses. Ein Versatz, der die Stabenden aufeinanderlegt, ist ein FEHLER der Modellprüfung.
* **Gewölbte Schalenflächen (Stand 42).** Eine gewölbte Fläche aus mehreren Netzstücken wird je Stück nach dem Randumlauf ausgerichtet (Zylindersegment 300° mit gelöschtem Streifen: 21,8 statt 47,5 kN). In einer Situation mit Stellung behalten die Elemente die Lage des Grundmodells, und die Stellung dreht die Geometrie der Bögen mit (die Last wirkte vorher in Gegenrichtung). Wasserdruck an einem Mantel über 180° wirkt überall auf derselben Seite (43,3 kN, von Hand 43,4 kN; vorher 78,4 kN).
* **Wind an freien Wänden (Stand 43).** Eine freie Wand oder Tafel aus mehreren Flächen, die sich berühren und in derselben Richtung stehen, ist eine Wand: Zonen ab den Enden der ganzen Wand (30 × 3 m aus drei Flächen 68,5 statt 80,3 kN). Volumenflächen nahezu parallel zum Wind bekommen keine Nettolast (Stirnfläche bisher 1,18 kN quer zum Wind).

## Meldungen und Status

* Der Status bleibt stehen, solange das Modell selbst erneuert werden muss: getrenntes Netz an doppelten Randlinien („Netz neu erzeugen“), altes Druckfeld eines strömungsnumerischen Wasserdrucks an Schalen („Wasserdruck neu erzeugen“), alte Kontaktfuge an Schalen („Kontaktfugen neu ausführen“). Bisher verschwand er nach „neu rechnen“.
* Eine Kontaktfuge zwischen zwei Schalen mit Spalt meldet nicht mehr „durchdringend“. Wind und Wasserdruck schreiben umgedrehte Elemente ins Protokoll. Der Ladehinweis zu Windabmessungen erscheint an freien Wänden nur noch bei einer echten Änderung. Stand 38 trägt in der Verfahrenstabelle das richtige Datum 14.11.2026.

## Nicht enthalten

* Die übrigen Befunde der Prüfung vom 14.11.2026 (Gruppe B: ältere Fehler, unter anderem Zylinderbeulen, Nordsee-Wind, f_y über 80 mm, Längsgelenk, Tab. 7.9, Strömungsnumerik an geneigten Flächen, Importeinheiten, Anzeige) kommen in einem eigenen PR. Die Befundliste steht in `BEFUNDE-2026-11-14.md` auf dem Desktop.
* Offene Vorschläge an den Anwender: Werkstoffzeile „f_y/f_u über 80 mm“, I_w der U-Profile beim Öffnen neu berechnen, Hinweis „Flächenlager nach Neuvernetzen prüfen“ für Dateien vor Stand 37.
