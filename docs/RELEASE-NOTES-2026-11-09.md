# Statik3D – Release-Notes vom 09.11.2026

Diese Notizen beschreiben, was sich gegenüber der Fassung vom 08.11.2026 (Sammelzweig 0f2cc1f) ändert und wo Ergebnisse anders ausfallen können. Einzelheiten stehen im Benutzerhandbuch.

## Auf einen Blick

* **Flächen mit gemeinsamer Randlinie sind verbunden.** Bis jetzt legte jede Schalenfläche auf ihren Randlinien eigene Zwischenknoten an. Zwei Flächen hingen dadurch nur an den Linienenden zusammen. Jetzt wird jede Linie einmal geteilt, und alle Flächen an ihr benutzen dieselben Knoten. Vierecke mit gleich geteilten Gegenseiten werden weiter abgebildet vernetzt (Vierecke), alle anderen frei mit Dreiecken in der eingestellten Netzgröße. Eine einzelne Fläche ohne Nachbarn wird vernetzt wie bisher.
* **Dreiecksflächen richten sich nach der Netzgröße.** Eine Fläche mit drei Randlinien war bisher ein einziges Dreieckelement. Jetzt wird sie in der eingestellten Netzgröße vernetzt.
* **Flächen mit Öffnung.** Eine einzelne Fläche mit Öffnung wurde über den Außenrand vernetzt, das Loch war gefüllt. Jetzt wird die Öffnung ausgespart.
* **Sicheres Speichern.** Modell- und Ergebnisdatei werden erst in eine Zwischendatei geschrieben und dann ausgetauscht. Scheitert das Schreiben, bleibt die alte Datei unverändert. Bisher war sie dann zerstört.

## Wo Ergebnisse anders ausfallen

* **Schalenmodelle aus mehreren Flächen müssen neu vernetzt werden.** Ein Netz, das vor dieser Fassung erzeugt wurde, steht in der Modelldatei und rechnet unverändert, also weiter mit den unverbundenen Flächen. Erst „Vernetzen“ erzeugt das verbundene Netz. Gemessen: Platte 4 × 2 m aus zwei Flächen, allseits gelenkig, 8,07 mm vorher gegen 6,49 mm jetzt (Navier 6,49 mm); Hubtor-Testmodell 1 523 und Stemmtor-Testmodell 1 596 vorher unverbundene Knotenpaare, jetzt keine.
* **Mehr Elemente.** Weil die Teilung an gemeinsamen Linien durch das ganze Tragwerk weitergereicht wird, kann ein Modell aus vielen Flächen feiner werden als bisher (Stemmtor bei Netzdichte mittel: rund 56 000 Elemente).
* **Volumenkörper** sind nicht betroffen; sie wurden schon immer über gemeinsame Linien vernetzt.

## Nicht enthalten

* **Die übrigen Befunde der Prüfagenten vom 09.11.2026** (Befundliste auf dem Desktop: Wind auf Schalen, Kombinationen mit DIN-19704-Kategorien, Theorie II. Ordnung, Lager, Volumen, Kontakt, Robustheit, Exporte). Sie folgen in der vereinbarten Reihenfolge als eigene Änderungen.
* **Flächen, die sich ohne gemeinsamen Linienzug berühren** (Knoten auf einer Linie, Rippe auf ungeteilter Platte), bleiben unverbunden (Befund A19).
* **σ_x, σ_y, τ_xy der Flächen** stehen weiter in Elementachsen; bei frei vernetzten Dreiecken sind die gemittelten Knotenwerte dieser Komponenten darum nicht aussagekräftig, die Hauptspannungen sind richtig (Befund A20).
* **Eine Prüfung beim Öffnen**, die alte unverbundene Schalennetze erkennt und zum Neuvernetzen auffordert.
