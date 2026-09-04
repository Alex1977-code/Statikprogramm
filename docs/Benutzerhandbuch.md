# Statik3D – Benutzerhandbuch

Statik3D ist ein Finite-Elemente-Programm für Stab-, Flächen- und
Volumentragwerke mit Lastfällen und Kombinationen nach DIN EN 1990, Kontakt,
Nachweisen nach DIN EN 1993-1-1 (Stahlbau) und DIN EN 1993-1-9 (Ermüdung),
Mehrkernrechnung, Rechnerfarm und statischem Bericht.

## 1 Installation und Start

```bash
pip install -r requirements.txt        # numpy, scipy, PySide6, pyvista, pyvistaqt
pip install gmsh                       # optional: CAD-Import STEP/IGES/STL
pip install pypardiso mkl              # optional: schneller Mehrkern-Gleichungslöser (Intel MKL)
pip install reportlab svglib           # optional: PDF-Bericht direkt aus dem Programm

python run_gui.py                      # oder: python -m statik3d.gui
python -m statik3d.cli --beispiel hall --nachweise --ermuedung --bericht halle.html
```

Windows-Programm ohne Python: `Statik3D.exe` von
https://github.com/Alex1977-code/Statikprogramm/releases/latest/download/Statik3D.exe
(eine Datei, doppelklicken; SmartScreen beim ersten Start mit „Weitere
Informationen → Trotzdem ausführen“ bestätigen). Der Knopf **Update suchen**
unten rechts holt die neueste Version: prüfen, herunterladen, austauschen,
Neustart. Dasselbe leistet Hilfe → Nach Update suchen… in jeder Installation.

Der Austausch läuft über ein kleines Skript `statik3d_update.bat` neben der
exe: Statik3D beendet sich, das Skript ersetzt die Datei und startet die neue
Fassung. Es räumt dabei die internen Umgebungsvariablen des Programmpackers
weg (`_PYI_…`, `_MEIPASS2`) — erbte die neue exe sie, hielte sie sich für
einen Unterprozess der alten und bräche mit „Security validation failure:
parent process has different executable!“ ab. Ein Protokoll des Austauschs
liegt als `statik3d_update.log` daneben; klappt etwas nicht, bleibt das
Fenster mit der Begründung stehen und die neue Datei liegt bereit.

Windows ohne Kommandozeile, aber mit Python: `Statik3D-Windows.bat` aus dem Repository in einen
eigenen Ordner speichern und doppelklicken. Die Datei lädt bei jedem Start die
neueste Version von GitHub (Ordner `Statikprogramm`, wird ersetzt), legt einmalig
die Python-Umgebung `.venv` an und startet die GUI. Mit dem Zusatz `handy`
startet sie den Browser-Server (Kap. 12), mit `offline` ohne Aktualisierung.
Eigene Modelle gehören in den Ordner `Projekte` daneben.

Einheiten im Programm: **m, N, Pa, kg/m³**. Eingabefelder mit anderer Einheit
sind beschriftet (z. B. E-Modul in GPa, fy in MPa). Ergebnisse werden in kN,
kNm, MPa und mm angezeigt.

## 2 Die Oberfläche

Oben eine dunkle Kopfzeile: links **Statik3D**, daneben Bauteil und Fassung,
rechts zwei Marken mit dem Umfang des Modells und dem Zustand („bereit",
„rechnet…", „berechnet · 12,4 s").

Darunter das **Ribbon** — die Befehlsleiste. Jeder Befehl steht dort genau
einmal; es gibt keine Menüleiste und keine zweite Werkzeugleiste daneben.
Dreizehn Register nach Arbeitsschritt:

| Register | Inhalt |
|---|---|
| **Datei** | Neu, Öffnen, Speichern, Projektangaben, Übernehmen aus fremden Formaten, Exportieren, Beispiele |
| **Start** | Auswahl, Modellprüfung, doppelte Knoten, freie Stabenden anschließen, Berechnen |
| **Geometrie** | Knoten, Netzgeneratoren (Stabzug, Platte, Quader) |
| **Struktur** | Stab, Schale, Querschnitte, Werkstoffe, Dicken, Zuweisen, Stäbe für Nachweise |
| **Lager / Kontakt** | Knoten-, Linien-, Flächenlager, Nichtlinearität, Kontakt, Anschlüsse (anlegen, zeigen, löschen) |
| **Lasten** | Lastfälle, Kombinationen, Knoten-, Stab-, Flächen-, Temperaturlast, Eigengewicht |
| **Netz** | Netz erzeugen und löschen |
| **Berechnung** | Berechnen (F5), einzelner Lastfall, Eigenschwingungen, Knicken, alle Stellungen, DIN 19704, Einstellungen, Bedienung im Browser |
| **Nachweise** | EC3, Ermüdung, Verformung (GZG), Beulen (EC3-1-5/-1-6), Lasteinleitung, Konfiguration |
| **Ergebnisse** | Ergebniswahl und die Tabellen |
| **Bericht** | Statischer Bericht |
| **Ansicht** | Blickrichtungen, Darstellungsart (Voll, Transparent, Hidden-Line, Drahtmodell), FE-Netz, Knoten, Nummern, Lasten, Stäbe farbig, Lagergröße |
| **Extras** | Handbücher, Info, Update |

Links über dem Ribbon die **Schnellzugriffsleiste** (Speichern, Berechnen,
Auswahl aufheben) — dieselben Befehle, nur schneller erreichbar. Rechts die
**Befehlssuche**: Namen eintippen, Eingabetaste, der Befehl läuft und sein
Register kommt nach vorn.

Die Arbeitsfläche in drei Spalten:

* **links der Modellbaum** — **alles, was modelliert werden kann**, mit Anzahl:

  | Zweig | Inhalt |
  |---|---|
  | Geometrie | Knoten (mit Koordinaten), Linien, **Flächen**, **Volumenkörper** |
  | Elemente | Stäbe, Flächen, Volumen — je nach Elementart, dazu die Stäbe für die Nachweise |
  | Eigenschaften | Querschnitte, Werkstoffe, Dicken |
  | Lager | Knoten-, Linien- und Flächenlager, einzeln mit Name und Wirkung |
  | Gelenke | Stabendgelenke mit den freigegebenen Freiheitsgraden |
  | Flächenfreigaben | Kontaktfugen aus RFEM mit ihrer Wirkung je Freiheitsgrad |
  | Lasten | alle Lasten aller Lastfälle, je Lastfall gezählt |
  | Kontaktbedingungen | einseitige Lager, Spaltelemente, Kontaktpaare |
  | Einwirkungen | Lastfälle und Kombinationen |
  | Stellungen, Anschlüsse, Verformungsnachweise, Beulfelder, Volumenbereiche, Lasteinleitung | die Nachweisobjekte |
  | **Ergebnisse** | Umhüllende, Kombinationen, Lastfälle, Nachweise, Eigenformen, Knickfiguren |
  | **Bericht** | die aus der Ansicht übernommenen Ergebnisbilder |

  **Ein Klick** wählt aus: der Zweig holt seine Tabelle nach vorn, öffnet
  rechts die Maske, die dazu gehört, und lässt das Objekt in der Ansicht
  **aufleuchten**. **Ein Doppelklick bearbeitet**: er öffnet die
  Maske des Objekts (Knotenkoordinaten, Linie, Querschnitt, Werkstoff, Dicke,
  Lager, Gelenk, Lastfall, Kombination …). Ein Doppelklick auf den
  Sammelzweig — „Werkstoffe“, „Gelenke“, „Linien“ — legt ein **neues** Objekt an.
  Zweige mit vielen Einträgen zeigen die ersten 60 und verweisen für den Rest
  auf die Tabelle unten, wo gefiltert werden kann.
  Die **Stellungen stehen nur hier**, mit „+ Stellung anlegen" am Ende des
  Zweiges; die maßgebende trägt ★.
* **in der Mitte die 3D-Ansicht** — frei für die Grafik.
* **rechts die Eingabemaske** — es ist immer genau **eine** sichtbar, gewählt
  über den Befehl im Ribbon; der Titel der Maske nennt sie. Eine Registerleiste
  mit denselben Namen wie im Ribbon gibt es nicht mehr.

Unten die **Tabellen**. Erst die Eingaben — Protokoll, Werkstoffe,
Querschnitte, Dicken, **Knoten, Linien, Elemente, Lager, Gelenke, Lastfälle,
Kombinationen** —, dann die Ergebnisse: Stabkräfte, Auflagerkräfte, Umhüllende,
Nachweise EC3, Ermüdung, Kontakt, Anschlüsse, Verformungen, Beulfelder,
Volumen, Lasteinleitung. **Das gesamte Modell steht damit tabellarisch da und
lässt sich dort auch ändern** — nicht nur die Ergebnisse. Wie die Tabellen zu
bedienen sind, steht im nächsten Abschnitt.

| Tabelle | editierbar |
|---|---|
| Knoten | x, y, z; dazu Elementzahl am Knoten und Lagername (Doppelklick öffnet die Maske) |
| Linien | über die Maske (Doppelklick): Name, Art, Knoten, Bemerkung |
| Elemente | Werkstoff, Querschnitt bzw. Dicke, Drehung der lokalen Achsen |
| Lager | Name und Symbolgröße; Doppelklick öffnet die Wirkung je Freiheitsgrad |
| Gelenke | über die Maske (Doppelklick) |
| Lastfälle | Beschreibung; Doppelklick öffnet Name, Einwirkung, Ausschlussgruppe |
| Kombinationen | über die Maske (Doppelklick) |
| Flächenfreigaben | nur Anzeige — sie kommen aus RFEM |
| Flächen, Volumenkörper | über die Maske (Doppelklick): Randlinien bzw. Randflächen, Dicke, Werkstoff, Teilung |
| Bericht | Name, Bildunterschrift, Bemerkung; Reihenfolge mit ▲/▼ |
| Lasten | nur Anzeige und Löschen; das Auswahlfeld links zeigt einen einzelnen Lastfall |

**Flächenfreigaben** sind Kontaktfugen: in der Fugenebene starr, senkrecht dazu
frei mit Ausfall bei Zug. Statik3D liest sie aus der RFEM-Datei vollständig ein
und zeigt sie mit ihrer Wirkung je Freiheitsgrad, **führt die Trennung im Netz
aber nicht aus** — dafür müssten die beteiligten Flächen vernetzt und die
Knoten an der Fuge verdoppelt werden. Die Spalte „Trennung ausgeführt" steht
deshalb auf „nein", und der Zweig im Modellbaum trägt ein ⚠. An diesen Stellen
rechnet das Modell durchverbunden — also **zu steif**.

Ein Knoten wird nur gelöscht, wenn **kein** Element mehr an ihm hängt — sonst
sagt das Programm, welches Element im Weg ist. Beim Löschen eines Elements
oder Knotens werden Stabzüge, Lager und Lasten mitgeführt.

### Die Geometriekette: Knoten → Linien → Flächen → Volumen

Modelliert wird wie in RFEM, in vier Stufen. Jede Stufe nimmt, was in der
Ansicht ausgewählt ist:

| Stufe | Befehl | Voraussetzung |
|---|---|---|
| Knoten | *Geometrie → Knoten* | – |
| Linie aus Knoten | *Geometrie → Linien → Linie aus Knoten* | mindestens zwei Knoten ausgewählt |
| **Fläche aus Linien** | *Geometrie → Flächen und Volumen* | die ausgewählten Linien bilden einen **geschlossenen** Rand |
| **Volumen aus Flächen** | *Geometrie → Flächen und Volumen* | mindestens vier Flächen ausgewählt |

Wonach ein Klick in der Ansicht greift, stellt das Auswahlfeld
**Geometrie → Auswahl in der Ansicht** ein: *Knoten, Linie, Fläche, Volumen,
Stab*. Ein zweiter Klick auf dasselbe Objekt nimmt es wieder aus der Auswahl;
das Gewählte ist orange hervorgehoben.

Fläche und Volumenkörper sind **Geometrie** — sie tragen erst dann Elemente,
wenn sie **vernetzt** werden (*Vernetzen* in derselben Gruppe, oder das
Häkchen „gleich vernetzen" in der Maske). Im Modellbaum trägt ein noch nicht
vernetztes Objekt ein ○.

| Form | Netz |
|---|---|
| Fläche mit vier Randabschnitten | abgebildetes Vierecknetz mit der eingestellten Teilung (längs × quer) |
| Fläche mit drei Randknoten | ein Dreieckelement |
| Volumen: 6 Vierecke, 8 Eckknoten | abgebildetes Hexaedernetz (x × y × z) |
| Volumen: 4 Dreiecke, 4 Knoten | ein Tetraeder |
| alles andere | wird **nicht** vernetzt; der Grund steht im Protokoll |

Ist eine Randlinie ein **Bogen, Kreis, Spline, Parabel oder eine Ellipse**,
folgen die neuen Netzknoten der wahren Kurve — nicht den Sehnen zwischen den
Stützknoten. Eine Polylinie bleibt dagegen eine Polylinie: dort laufen die
Knoten auf den Sehnen, denn etwas anderes hat der Anwender nicht angegeben.

„Netz löschen" nimmt die Elemente wieder weg, die Geometrie bleibt stehen.
Eine Fläche, die noch einen Volumenkörper berandet, lässt sich nicht löschen —
das Programm sagt, welcher es ist.

### Ergebnisse und Bericht

Was gerechnet wurde, steht im **Modellbaum unter „Ergebnisse"**: Umhüllende,
Kombinationen, Lastfälle, die Nachweise, Eigenformen und Knickfiguren. Ein
Klick stellt das Ergebnis in der Ansicht ein — dieselbe Auswahl, die auch die
Maske *Ergebnisse* rechts führt. Dort werden Färbung, Schnittgrößenverlauf und
Überhöhung eingestellt.

**Ergebnisse in den Bericht übernehmen**: Ansicht einstellen, dann
*Bericht → Ansicht übernehmen* (**Strg+B**), ein Doppelklick auf den
Ergebniszweig oder „+ Ansicht übernehmen" im Modellbaum. Aufgenommen wird das
Bild **und** die Einstellung, aus der es entstanden ist — welches Ergebnis,
wonach eingefärbt, welcher Verlauf, welche Überhöhung. Ohne diese Angabe wäre
eine Farbgrafik im Statikdokument nicht prüfbar.

Die übernommenen Bilder stehen im Modellbaum unter „Bericht" und in der
Tabelle **Bericht** unten: dort lassen sich Name, Bildunterschrift und
Bemerkung ändern, die Reihenfolge mit ▲/▼ verschieben und einzelne Bilder
löschen. Im Statikdokument erscheinen sie als eigenes Kapitel „Übernommene
Ergebnisbilder", jeweils mit einer Tabelle, die die Einstellung nennt. Das
Kapitel lässt sich in der Berichtsmaske abwählen.

### Darstellung in der Ansicht

Vier Darstellungsarten, im Register *Ansicht* nebeneinander und auf
**Strg+1 … Strg+4**, dazu im Rechtsklickmenü der Ansicht:

| Art | Taste | Bild |
|---|---|---|
| Voll | Strg+1 | gefüllte Flächen, farbig |
| Transparent | Strg+2 | durchscheinend — man sieht die innen liegenden Teile |
| Hidden-Line | Strg+3 | weiße Flächen mit dunklen Kanten, wie eine Zeichnung |
| Drahtmodell | Strg+4 | nur die Kanten |

**F9** blendet das **FE-Netz** (die Elementkanten) ein und aus. Der Schalter
„Knoten" zeigt die gesetzten Knoten als Punkte: Knoten, an denen noch **kein
Element** hängt, sind orange und etwas größer — so sieht man beim Modellieren,
wo man schon war, auch wenn dort noch nichts steht.

**Die Glasleiste** liegt oben links über der Ansicht und trägt die Griffe, die
man beim Modellieren dauernd braucht: die vier Darstellungsarten, FE-Netz,
Knoten, Linien, Lasten, Fang, die Auswahlart und „alles ins Bild". Es sind
dieselben Befehle wie im Ribbon, nur näher an der Maus.

**Der Ansichtswürfel** oben rechts schaltet die Blickrichtung: **O**
Draufsicht, **V** Vorderansicht, **S** Seitenansicht, ein Klick daneben
isometrisch.

**Linien** sind Geometrie, keine Elemente — der Schalter „Linien" zeigt sie.
Bei einem aus RFEM übernommenen Modell besteht die Geometrie fast nur aus
Linien; ohne den Schalter sähe man ein leeres Bild.

**Der Fang** lässt sich einzeln umstellen: F3 schaltet ihn ganz aus,
Umschalt+F1 den Knotenfang, Umschalt+F2 den Fang auf Kantenmitten,
Umschalt+F3 den Rasterfang. Was gerade gefangen wird, steht in der
Statuszeile.

**Lagersymbole**: Die Form sagt, was das Lager hält — Würfel für die
Einspannung, Kegel für das gelenkige Lager, Zylinder für ein Federlager.
Linienlager und Flächenlager werden kleiner und in eigener Farbe gezeichnet.
Die **Größe** stellt der Schieber „Lager" im Register *Ansicht* für alle
zusammen ein; **ein Rechtsklick auf ein Lagersymbol** öffnet dessen eigenes
Menü mit „Größe dieses Lagers…", „Größe aller Lager…", „Lager bearbeiten…" und
„Lager löschen". Die eingestellte Größe wird mitgespeichert.

### Tabellen: filtern, sortieren, ausgeben

Jede Tabelle unten hat über der Kopfzeile eine **Filterzeile** — ein Feld je
Spalte. Was dort steht, gilt sofort; mehrere Felder wirken zusammen (und, nicht
oder). Die Zählung links („17 von 240 Zeilen") sagt, wie viel übrig ist.

| Eingabe | wirkt |
|---|---|
| `> 0,9` | größer als 0,9 — auch `>=`, `<`, `<=`, `!=` |
| `= HEB 200` | genau dieser Wert (Zahl oder Text) |
| `1..5` | Bereich einschließlich der Grenzen |
| `HEB` | Text kommt vor (Groß- und Kleinschreibung egal) |
| `!HEB` | Text kommt **nicht** vor |

`> 1` in der Spalte „Ausnutzung" zeigt in einem Griff alle Überschreitungen.

**Sortieren**: Klick auf die Spaltenüberschrift; Zahlen werden der Größe nach
sortiert, nicht als Text. **Spalten** lassen sich über „Spalten…" ein- und
ausblenden und mit der Maus verschieben.

Unter jeder Ergebnistabelle steht eine feste **Zeile „Max"/„Min"**. Sie
bezieht sich auf das, was der Filter gerade übrig lässt, und bleibt beim
Sortieren an ihrem Platz.

**Ausgeben** — „Kopieren", „CSV…", „Excel…" in der Tabelle selbst oder die
Gruppe „Tabelle ausgeben" im Register *Ergebnisse* (Strg+Umschalt+C kopiert).
Ausgegeben wird immer nur das, was gerade zu sehen ist, samt Max- und
Min-Zeile. CSV kommt mit Semikolon und deutschem Dezimalkomma, xlsx mit echten
Zahlen (nicht als Text) — in Excel lässt sich damit sofort weiterrechnen.

**Tabelle und Ansicht hängen zusammen**: ein Klick auf eine Zeile wählt das
Element beziehungsweise den Knoten in der 3D-Ansicht; umgekehrt markiert eine
Auswahl in der Ansicht die zugehörigen Zeilen und rollt die erste ins Bild.

**Eingabetabellen sind editierbar.** In Werkstoffe, Querschnitte, Dicken,
Knoten, Elementen, Lagern und Lastfällen sind die hellen Spalten zum
Hineinschreiben da: Zelle anklicken, Wert tippen,
Eingabetaste. Gerechnet werden darf dabei — `= 210/1,05` ergibt 200. Erlaubt
sind die vier Grundrechenarten, Klammern, Potenz und `pi`; mehr nicht, damit
aus einer Tabellenzelle kein Programm wird. Ein unmöglicher Wert (E ≤ 0,
ν ≥ 0,5, eine negative Fläche) wird **nicht** übernommen; die Zelle behält
ihren Inhalt, und die Statuszeile sagt, warum. Jede Änderung geht über den
Rückgängig-Stapel (Strg+Z) und verwirft die vorhandenen Ergebnisse — gerechnet
werden muss danach neu. Wer A, Iy, Iz, It oder Wpl,y von Hand ändert, löst den
Querschnitt von der Profildatenbank; sein Typ wird `free`, die Nachweise
laufen dann elastisch.

### Maske oder Klick

Jeder Erzeuge-Befehl — Knoten, Stab, Schale, Lager, Knotenlast — öffnet eine
**kompakte Maske am rechten Rand der Ansicht**. Sie legt sich nicht über das
Modell und blockiert nichts. Beide Wege führen zum selben Ziel:

* **tippen**: Werte eintragen, „Anlegen" (oder Eingabetaste) — die Maske bleibt
  offen und ist gleich für das nächste Objekt bereit;
* **klicken**: in der Ansicht die Knoten anklicken. Sobald genug beisammen
  sind, entsteht das Objekt; die gewählten Knoten stehen in der Maske. Ein
  zweiter Klick auf denselben Knoten nimmt ihn wieder heraus.

Querschnitt, Material, Dicke und Lastfall gelten für alle folgenden Objekte,
bis man sie ändert. **Esc** schließt die Maske. Ein neuer Erzeuge-Befehl löst
die vorige Maske ab — es ist immer höchstens eine offen.

### Rückgängig und Wiederholen

**Strg+Z** nimmt die letzte Änderung zurück, **Strg+Y** stellt sie wieder her —
für alles: Geometrie, Netz, Lager, Lasten, Linien. Gesichert wird jeweils das
ganze Modell, darum bleibt auch eine Änderung umkehrbar, die viele Stellen auf
einmal betrifft. Die letzten 50 Schritte werden vorgehalten; die Schnellzugriffs-
leiste zeigt im Hinweistext, worum es beim nächsten Schritt geht.

### Koordinatensysteme, Arbeitsebene, Fang

Im Register **Geometrie** stehen drei Gruppen für die Eingabehilfen:

* **Koordinatensystem** — das aktive System wählen, ein neues über Ursprung und
  Drehwinkel anlegen oder aus drei gewählten Knoten aufspannen (Ursprung,
  x-Richtung, ein Punkt in der xy-Ebene). Neben kartesisch gibt es
  **zylindrisch** (r, θ, z — für Rohre und Segmentverschlüsse) und
  **sphärisch** (r, θ, φ). Alle Koordinateneingaben beziehen sich auf das
  aktive System; die Statusleiste nennt es.
* **Arbeitsebene** — xy, yz oder xz des aktiven Systems, mit einstellbarer
  Rasterweite (0 = kein Raster).
* **Fang** — ein Klick in der Ansicht wird auf die nächste markante Stelle
  gezogen: erst Knoten, dann Kantenmitte, dann Rasterpunkt. Der Schalter im
  Ribbon nimmt ihn zurück; die Statusleiste zeigt seinen Zustand.

### Linien: Bogen, Kreis, Spline, Parabel

**Geometrie → Linie** öffnet die Maske. Art wählen, dann in der Ansicht die
Knoten anklicken:

| Art | Eingabe | Ergebnis |
|---|---|---|
| Polylinie | 2 oder mehr Knoten | gerader Zug |
| Bogen | 3 Knoten: Anfang, Zwischenpunkt, Ende | Kreisbogen durch die drei Punkte; Radius und Öffnungswinkel folgen daraus |
| Kreis | 1 Knoten (Mittelpunkt) + Radius | Vollkreis in der Arbeitsebene |
| Spline | 3 oder mehr Knoten | B-Spline vom gewählten Grad durch den ersten und letzten Punkt |
| Parabel | 2 Knoten + Stich | Parabel mit dem angegebenen Stich in der Mitte |

Mit „Stäbe daraus erzeugen" wird die Linie gleich in Stabelemente geteilt — die
Teilung steht in der Maske. Die Linie bleibt als Geometrie erhalten und kennt
ihre exakte Länge (ein Halbkreis r = 2 m misst 6,283 m, nicht die Länge des
Sehnenzugs).

### Register „Auswahl"

Sobald Knoten gewählt sind, erscheint rechts im Ribbon ein zusätzliches
Register **„Auswahl: n Knoten"** mit genau den Befehlen, die auf die Auswahl
passen: Querschnitt und Material zuweisen, Gelenke setzen, Elemente oder Knoten
löschen, Lager setzen, Last aufbringen, Auswahl umkehren oder aufheben. Wird
die Auswahl aufgehoben, verschwindet das Register wieder. Einen Bereich
„Elemente ändern" im rechten Panel gibt es dafür nicht mehr.

Ganz unten die **Statusleiste**: Fang · aktives Koordinatensystem · Einheiten ·
Netzstand · Solverstand. Die Fassung steht unter **Extras → Info**; ein Hinweis
auf ein Update erscheint nur, wenn wirklich eines vorliegt.

## 3 Arbeitsablauf

1. **Modell**: Materialien und Querschnitte anlegen (Profildatenbank).
2. **Netz**: Stabzüge (werden automatisch als Stäbe für die Nachweise
   registriert), Platten, Quader oder Import.
3. **Lager/Lasten**: Knoten wählen, Lager setzen. Lasten gehören immer zum
   *aktiven Lastfall* (Register Lastfälle, angezeigt in grün).
4. **Lastfälle**: weitere Lastfälle anlegen (z. B. `S` Schnee, `W_links`,
   `W_rechts` mit Ausschlussgruppe „Wind“), dann „Automatisch (DIN EN 1990)“.
5. **Nachweise**: Stäbe prüfen (Doppelklick: Knicklängenbeiwerte βy/βz,
   Abstand seitlicher Halterungen L_LT, Lastangriff, Kerbfall für Ermüdung).
6. **Berechnung**: „Alle Lastfälle + Kombinationen“, Häkchen für Nachweise
   und Ermüdung, BERECHNEN.
7. **Ergebnisse**: Umhüllende GZT zeigt Extremwerte mit maßgebender
   Kombination; Färbung „Ausnutzung EC3“ zeigt die Stabausnutzung; Verlauf
   „My“ zeichnet den Momentenverlauf.
8. **Bericht**: Datei → Statischer Bericht (HTML, im Browser druckbar/als PDF
   speichern; PDF direkt bei installiertem reportlab).

Beispiele im Menü **Beispiele** zeigen jeden dieser Schritte fertig
aufgebaut, u. a. der Hallenrahmen (Kombinationen, EC3, Ermüdung), die
Stauwand (Stahlwasserbau, Schalen + Riegel, Wasserdruck) und zwei
Kontaktbeispiele.

## 4 Lastfälle und Kombinationen

* Einwirkungskategorien: G (ständig), Q_A … Q_H (Nutzlasten), Q_K (Kran),
  S / S_H (Schnee), W (Wind), T (Temperatur), H (Wasserdruck), A
  (außergewöhnlich), P (Vorspannung), SET (Setzung), FAT (nur Ermüdung).
  Die ψ-Beiwerte nach DIN EN 1990/NA sind hinterlegt und je Lastfall
  überschreibbar.
* Ausschlussgruppe: Lastfälle derselben Gruppe wirken nie gleichzeitig
  (Wind aus verschiedenen Richtungen, Laststellungen).
* Automatische Kombinationen: GZT nach 6.10 (oder 6.10a/b), ständige Lasten
  günstig und ungünstig, jede veränderliche Einwirkung als Leiteinwirkung;
  GZG charakteristisch/häufig/quasi-ständig; außergewöhnlich 6.11b.
  Beschreibung „auto: …“ kennzeichnet erzeugte Kombinationen; sie werden bei
  erneuter Erzeugung ersetzt, manuelle bleiben erhalten.
* Ergebnisse: jeder Lastfall, jede Kombination, Umhüllende je Gruppe (GZT,
  GZG …) mit maßgebender Kombination je Extremwert.

## 5 Lager: Ausfall, Schlupf, Reibung

Jedes Lager wirkt je Freiheitsgrad **starr**, als **Feder** oder ist **frei**;
zusätzlich lassen sich Nichtlinearitäten einstellen (Register Lager/Lasten →
**Nichtlinearität…**, auf dem Handy Modell → Nichtlineare Lager):

| Einstellung | Bedeutung |
|---|---|
| **Ausfall bei Zug** | Das Lager nimmt nur Druck auf (klassisches abhebendes Auflager). |
| **Ausfall bei Druck** | Das Lager nimmt nur Zug auf (Zuganker, Hänger). |
| **Schlupf** | Freier Weg, bevor das Lager wirkt (Lagerspiel, Fuge). |
| **Reibung μ** | Die Kraft quer zur Stützrichtung ist auf μ·|F| der Bezugskraft begrenzt; „μ bezogen auf“ nennt den Freiheitsgrad der Normalkraft (meist uz). |
| **Grenzkraft** | Ab dieser Kraft fließt das Lager plastisch weiter (Zustand „Fließen“). |

**Vorzeichen:** Das Lager wirkt entlang der positiven Achse seines
Freiheitsgrads. Bewegt sich der Knoten in das Lager hinein, entsteht **Druck**;
zieht er daran, **Zug**.

**Linienlager** (Knopf *Linienlager…*): Lager entlang der gewählten Knoten in
Auswahlreihenfolge. Die Steifigkeit wird **je Meter** angegeben und über die
Einflusslänge (halbe Nachbarabschnitte) auf die Knoten verteilt.

**Flächenlager / Bettung** (Knopf *Flächenlager…*): Lager auf Schalen- oder
Volumenelementen. Die Steifigkeit wird **je m²** angegeben (Bettungsmodul) und
über die Einflussfläche verteilt; bei Volumen wird die gewählte Fläche belegt
(-1 = alle Außenflächen).

Alle drei Lagerarten nutzen dieselbe Iteration wie der Kontakt (Kapitel 6): Die
Ergebnisse zeigen je Bedingung Zustand (offen / Kontakt / Haften / Gleiten /
Fließen), Spalt und Kräfte.

**Gelenke**: Stabendgelenke je lokalem Freiheitsgrad biegesteif, gelenkig oder
als **Drehfeder**. Eine Drehfeder wirkt nur, wenn der Knoten selbst gehalten ist
(sonst ist die Kette Stab–Feder–freier Knoten wieder ein Gelenk).

## 6 Kontakt

* **Einseitiges Lager**: Knoten auswählen, Stützrichtung (z. B. 0 0 1 =
  stützt nach oben), optional Spalt, Federsteifigkeit (elastische Bettung,
  nur Druck) und Reibbeiwert μ.
* **Spaltelement**: genau zwei Knoten auswählen; Anschlag mit Spalt.
* **Kontaktpaar**: Slave-Knoten auswählen (z. B. Unterseite eines
  Bauteils), Master = Schalen, Volumenoberflächen oder Elementgruppe,
  μ und Spalt angeben.
* Kontakt macht die Berechnung nichtlinear: Kombinationen werden einzeln
  gelöst (parallel/Farm). Ergebnisse: Status je Kontaktknoten (offen,
  Kontakt, Haften, Gleiten), Kontaktkräfte (Tabelle „Kontakt“, farbige
  Marker im Viewport). Hebt ein Bauteil vollständig ab oder rutscht es ohne
  Halt, wird das als Fehler gemeldet – dann Lagerung oder Lasten prüfen.

## 7 Import

Datei → Importieren (Details in `Schnittstellen.md`):

| Format | Herkunft | Inhalt |
|---|---|---|
| `.json` | Statik3D | vollständiges Modell |
| `.dxf` | CAD, InfoCAD, RFEM | Linien → Stäbe, 3DFACE → Schalen, Layer → Gruppen |
| `.ifc` | InfoCAD, RFEM, Allplan … (IFC Structural Analysis View) | Knoten, Stäbe, Flächen, Profile, Lager, Lasten, Lastfälle |
| `.xlsx` SAF | RFEM 6, SCIA, Allplan, AxisVM | Structural Analysis Format |
| `.xlsx`/`.csv` | RFEM 5/6, RSTAB Tabellenexport | Knoten, Linien, Stäbe, Querschnitte, Lager, Lastfälle, Lasten |
| `.sza`/`.kra`/`.fga` | HiCAD | Profile mit Katalogwerten, Blechdicken, Werkstoffe, Teileliste **und die Stabachsen aus dem Szenenteil** (siehe Schnittstellenhandbuch) |
| `.inp` | Abaqus, CalculiX | Netz, Materialien, Sections, Randbedingungen, Lasten je Step |
| `.bdf`/`.nas`/`.dat` | Nastran | GRID, CBAR/CBEAM, CQUAD4/CTRIA3, CTETRA/CHEXA, SPC, FORCE, PLOAD |
| `.rf6` | RFEM 6 Projektdatei | Knoten, Linien, Stäbe mit Typ, Flächen mit Dicke, Volumenkörper, Lager mit Nichtlinearität, Gelenke, Flächenfreigaben, Lastfälle mit Flächenlasten |
| `.step`/`.iges`/`.stl` | CAD | Vernetzung mit gmsh (Volumen oder Schale) |

Eine **RFEM-6-Projektdatei** (`.rf6`) wird unmittelbar gelesen – kein Export
nötig. Übernommen werden Knoten, Linien, Stäbe, **jede Fläche und jeder
Volumenkörper als Objekt** (mit Randlinien, Dicke und Werkstoff), die Lager,
die Flächenfreigaben, alle Lastfälle mit ihren Lasten (Vorspannung als
gleichwertige Temperaturlast), die Kombinationen und die **Netzeinstellungen**
aus `mesh.xml`. Was kein Netz bekommen konnte, steht trotzdem im Modellbaum
und lässt sich dort vernetzen.

**Krumme Linien** kommen mit ihrer wahren Form: Bögen, Kreise, Parabeln,
Ellipsen und NURBS werden über ihre Kontrollpunkte gelesen, nicht als Sehne
durch die Stützknoten. Das ist keine Kleinigkeit der Darstellung — eine
Bohrung, eine Buchse, ein Bolzen oder ein Augenblech besteht in RFEM aus
*zwei Halbbögen zwischen denselben zwei Knoten*; über die Knoten allein wäre
das kein Polygon, und die Fläche fehlte im Bild wie im Modellbaum.

**Aufeinanderliegende Knoten werden nicht zusammengeführt.** In einem
RFEM-Volumenmodell liegen sie an jeder Kontaktfuge und jeder Flächenfreigabe
absichtlich aufeinander; verschweißt wäre das Modell dort zu steif und die
Freigaben liefen ins Leere. Wie viele es sind, steht im Protokoll; wer sie
doch zusammenführen will, liest die Datei mit `merge_nodes=True`. Was gar nicht ging, steht Zeile für Zeile im
Importprotokoll; Einzelheiten im Schnittstellenhandbuch. Die älteren nativen Formate (`.rf5`, `.rs6`, `.fem`)
werden untersucht und, soweit ihr Behälter zugänglich ist, ausgelesen –
andernfalls nennt das Programm den Exportweg (RFEM: IFC-Statikmodell, SAF oder
Tabellen; InfoCAD: IFC-Statikmodell oder DXF).

Aus HiCAD übernommene Stäbe enden an der **Außenkante** des angeschlossenen
Bauteils – ihre Achsen laufen um die halbe Profilhöhe daneben vorbei, das Modell
zerfällt zunächst in Teile. Im Register **Mehr → Aus CAD übernommenes Modell**
schließt „Freie Stabenden anschließen" (Suchradius 60 mm) jedes freie Ende an die
Achse des nächsten Stabes an und teilt diesen dort; der Versatz steht im
Protokoll, die Ausmitte des Anschlusses wird nicht abgebildet.

## 8 Nachweise nach EC3

Stäbe (Kette von Stabelementen) werden beim Erzeugen von Stabzügen und beim
Import automatisch angelegt („Stäbe automatisch erkennen“ verkettet
kollineare Elemente gleichen Querschnitts). Je Stab:

* Querschnittsnachweise an allen Nachweisstellen (Klasse, N, V, M, M+V, M+N,
  Torsion, Vergleichsspannung),
* Biegeknicken um y und z (Knicklängen βy·L, βz·L oder explizit),
  Drillknicken, Biegedrillknicken (L_LT, kz, kw, C1 automatisch aus dem
  Momentenverlauf, Lastangriff oben/unten), Interaktion Gl. 6.61/6.62,
* Ermüdung: Kerbfall wählen (Δσc mit Beispielen aus den Tabellen 8.1–8.5),
  Schadensfolge/Konzept für γMf; Ermüdungslasten im Register Lastfälle.

Ergebnis: Tabelle „Nachweise EC3“ mit Ausnutzung, maßgebendem Nachweis,
Kombination und Stelle; Färbung „Ausnutzung EC3“ im Viewport; alle Details
im Bericht.

### Anschlüsse nach EC3-1-8

Ein Anschluss gehört zum Modell wie ein Stab: er wird mitgespeichert, steht im
Modellbaum und in der Tabelle „Anschlüsse“, überlebt Rückgängig und wird bei
**jeder** Berechnung mit nachgewiesen.

**Anlegen**: Stabende wählen (die beiden Knoten des Stabelements markieren),
dann Register *Lager / Kontakt* → „Anschluss“ — oder im Modellbaum
„+ Anschluss anlegen“, oder in der Tabelle „Anschluss anlegen…“.
Es gibt drei Vorlagen:

| Vorlage | Anwendung |
|---|---|
| **Kopfplatte** | geschraubte Stirnplatte am Stabende, mit Rippen |
| **Laschenstoß** | Flansch- und Steglaschen, geschraubt |
| **Knotenblech** | Diagonalanschluss (Gusset), geschraubt oder geschweißt |

Der Dialog schlägt aus Profil und Schnittgrößen eine vollständige Geometrie vor
— Blechdicken, Schraubenbild, Nahtdicken — und bessert sie nach, bis die
Nachweise erfüllt sind; jeder Wert lässt sich danach ändern. Die Vorschläge
folgen den Regeln der EN 1993-1-8 (Rand- und Lochabstände Tab. 3.3, Nahtdicken
4.5.1, Blechdicke so, dass der T-Stummel nicht im Modus 1 versagt). Der
Vorschlag ist **kein Nachweis** — maßgebend ist immer die Rechnung.

**Schnittgrößen**: standardmäßig aus der Berechnung. Der Anschluss wird über
**alle GZT-Kombinationen** geführt; die ungünstigste ist maßgebend, und die
Tabelle nennt sie. Wer feste Werte will (Vorbemessung, Handrechnung), setzt im
Dialog den Haken „Diese Schnittgrößen festhalten“.

**Nachgewiesen wird** je Anschluss:

* Schrauben: Abscheren F_v,Rd, Lochleibung F_b,Rd, Zug F_t,Rd, Durchstanzen
  B_p,Rd, Interaktion Abscheren + Zug (Tab. 3.4), Gleitfestigkeit F_s,Rd der
  Kategorien B und C, Abminderung langer Anschlüsse β_Lf;
* Zugzone der Kopfplatte über den äquivalenten T-Stummel (6.2.4) mit den
  Versagensmodi 1 bis 3 und den wirksamen Längen nach Tab. 6.4/6.5;
* Kehl- und Stumpfnähte nach dem Richtungsbezogenen Verfahren (σ_⊥, τ_⊥, τ_∥
  mit β_w) und dem Vereinfachten Verfahren;
* Bleche: Zug im Brutto- und Nettoquerschnitt, Blockversagen (3.10.2),
  Knotenblech auf Druck über die Whitmore-Breite;
* Rand- und Lochabstände als Prüfliste (Hinweise, keine stille Korrektur).

**Ermüdung**: aus den Ermüdungslasten des Modells. Je Last die Schwingbreite
der Stabendschnittgrößen, daraus Δσ im jeweiligen Bauteil, Kerbfall nach
EN 1993-1-9 Tab. 8.1 (Schrauben, Bleche mit Loch) und 8.5 (Nähte); die
Schädigungen werden nach Palmgren-Miner **über alle Ermüdungslasten**
aufsummiert. Wichtig: eine nicht vorgespannte Schraube bekommt die volle
äußere Schwingbreite ab — das Programm sagt das als Hinweis dazu.

**Momenten-Rotations-Verhalten**: Statik3D bestimmt für jeden Anschluss die
Anfangssteifigkeit S_j,ini nach dem Komponentenverfahren (6.3.1), die
Momententragfähigkeit M_j,Rd (6.2.7), die Klasse (starr, nachgiebig, gelenkig
nach 5.2.2.5) und das Rotationsvermögen (6.4.2) — und **rechnet damit**: ein
nachgiebiger Anschluss sitzt als Drehfeder S_j = S_j,ini/η am Stabende
(5.1.2(4)), ein gelenkiger als Momentengelenk.

Im Dialog gehören dazu drei Angaben:

* **Stützenquerschnitt** — das Profil, an das angeschlossen wird. Ohne ihn
  entfallen die Komponenten k_1 bis k_4 (Stützensteg auf Schub, Druck und Zug,
  Stützenflansch auf Biegung); S_j,ini ist dann eine **obere Schranke**, der
  wirkliche Anschluss ist weicher. Das Programm sagt es dazu.
* **Rahmen** ausgesteift (k_b = 8) oder nicht ausgesteift (k_b = 25) — die
  Grenze, ab der ein Anschluss als starr gilt.
* **in der Berechnung**: „automatisch“ folgt der Klassifizierung; wahlweise
  fest „starr“, „Drehfeder“ oder „gelenkig“.

Ergebnis: Tabelle „Anschlüsse“ mit Ausnutzung, maßgebendem Nachweis,
Kombination und Schädigungssumme D, dazu S_j,ini, Klasse, M_j,Rd und wie der
Anschluss in der Rechnung sitzt; „Nachweise zeigen“ gibt alles im Klartext;
Kapitel 7 des Berichts führt jede Schraube und jede Naht mit E_d, R_d und η,
die Ausnutzung je Kombination, die Steifigkeitsbeiwerte k_i und die
Schraubenreihen der Zugzone.

### Beulnachweise nach EC3-1-5

**Stegbleche** brauchen nichts weiter: sobald ein Steg schlanker ist als
72 ε/η, führt Statik3D den Schubbeulnachweis nach Abschnitt 5 in den
Querschnittsnachweisen mit — mit λ̄_w, χ_w, V_b,Rd und, wenn nötig, der
Interaktion Biegung–Schubbeulen nach 7.1. Der Abstand der Quersteifen und eine
starre Endquersteife lassen sich am Stab angeben (Felder ``a_steifen`` und
``starre_endsteife``); ohne Angabe wird konservativ mit Steifen nur an den
Auflagern gerechnet.

**Blechfelder** aus Flächenelementen werden als **Beulfeld** festgelegt:
die Elemente des Feldes auswählen (Knoten markieren), dann Register
*Nachweise* → „Beulfeld“ oder in der Tabelle „Beulfeld aus Auswahl…“.
Abmessungen a und b sowie die Dicke kommen aus der Geometrie; anzugeben ist
nur die Lagerung der Ränder (beidseitig oder einseitig gestützt).

Nachgewiesen wird nach der **Methode der reduzierten Spannungen**
(Abschnitt 10): aus dem Spannungszustand des Feldes werden α_ult,k und α_cr
gebildet, daraus λ̄_p und die Abminderungsbeiwerte ρ_x, ρ_z und χ_w.
Die Tabelle „Beulfelder“ zeigt Abmessungen, Spannungen, λ̄_p und die
Ausnutzung; Kapitel 6 des Berichts führt jeden Zwischenwert auf — Beulwerte,
kritische Spannungen, α-Werte und beide Nachweisformen (Gl. 10.5 und die
Vereinfachung mit ρ_min).

**Steifen** gehören zum Feld: im Dialog lassen sich Längs- und Quersteifen
zeilenweise eintragen (Lage, A_sl, I_sl, für das Drillknicken zusätzlich I_T
und I_p). Eine Längssteife hebt σ_cr,p (Anhang A.2.2 bei einer oder zwei
Steifen, A.1 ab drei) und den Schubbeulwert (k_τ,st nach A.3(2)); zwischen
Platten- und Knickstabverhalten wird nach 4.5.4 interpoliert. Die Steifen
selbst werden nach Abschnitt 9 geprüft — Drillknicken der Längssteife,
Mindeststeifigkeit der starren Quersteife. Fehlen I_T und I_p, sagt das
Programm, dass das Drillknicken gesondert zu prüfen ist.

**Zylinderschalen**: im selben Dialog auf „Zylinderschale“ umstellen. Radius
und Beullänge kommen aus der Geometrie oder werden von Hand gesetzt; dazu
gehören die **Herstelltoleranzklasse** (A, B oder C) und die Randbedingung.
Nachgewiesen wird nach DIN EN 1993-1-6, Abschnitt 8.5 — Meridian, Umfang und
Schub je für sich und in der Interaktion.

**Schlanke Stege und Gurte (Klasse 4)**: Wird ein Querschnittsteil so schlank,
dass es vor dem Erreichen der Streckgrenze beult, ordnet Statik3D den
Querschnitt der Klasse 4 zu und rechnet mit den **wirksamen** Querschnittswerten
nach DIN EN 1993-1-5, Abschnitt 4 — A_eff aus reinem Druck, W_eff,y und W_eff,z
aus reiner Biegung. Dazu ist nichts einzustellen; es geschieht von selbst,
sobald die Schnittgrößen es verlangen. Der Bericht führt die Herleitung
vollständig auf: je Querschnittsteil c/t, ψ, k_σ, λ̄_p, Grenzschlankheit und ρ,
dann die wirksame Stegbreite mit ihrer Aufteilung, die verschobene Schwerachse,
A → A_eff, W_el → W_eff und die Schwerachsenverschiebung e_N. Ist e_N ungleich
null, tritt das Zusatzmoment ΔM = N_Ed e_N in den Nachweisen 6.2.9.3 und
6.3.3 hinzu.

Bei einem **schlanken Kreisrohr** (d/t > 90ε²) gibt es keine wirksamen Breiten.
Statik3D führt dort den spannungsbasierten Schalenbeulnachweis nach
DIN EN 1993-1-6, 8.5 — mit der Beullänge L_cr,z des Stabes und der
Herstelltoleranzklasse B. Dieser Nachweis wird bei schlanken Rohren
regelmäßig maßgebend.

**Lasteinleitung**: Register *Nachweise* → „Lasteinleitung“. Anzugeben sind
der Knoten, der Stab (für die Stegabmessungen), die Art nach Bild 6.1 (a, b
oder c), die Lasteinleitungslänge s_s und der Abstand der Quersteifen. Die
Kraft F_Ed kommt aus der Rechnung: wahlweise als Knotenlast der jeweiligen
Kombination oder als **Auflagerkraft** — das ist der übliche Fall am Endauflager.
Neben η₂ = F_Ed/F_Rd wird die Interaktion mit der Biegung nach 7.2(1) geführt
(η₂ + 0,8 η₁ ≤ 1,4); η₁ folgt aus N und M_y an der nächstgelegenen
Nachweisstelle des Stabes, gebildet mit den Bruttoquerschnittswerten. Beide
Nachweise gehen in den Status der Stelle ein.

Was **nicht** enthalten ist: Kegel- und Kugelschalen, ringversteifte Schalen
und die numerischen Verfahren (GMNIA) nach EN 1993-1-6, 8.7. Liegen die
Elemente eines ebenen Feldes nicht in einer Ebene, sagt das Programm es.

### Volumennachweise

Volumenkörper bekommen keine Querschnittsnachweise — es gibt keinen
Querschnitt. Nachgewiesen wird der **Spannungszustand** nach
DIN EN 1993-1-1, 6.2.1(5): die Vergleichsspannung nach von Mises gegen
f_y/γ_M0.

Anlegen: die Knoten des Bereichs in der Ansicht auswählen, dann Register
*Nachweise* → „Volumen“ (oder in der Tabelle „Volumen“ auf
„Bereich aus Auswahl…“). Es werden alle Volumenelemente aufgenommen, die
vollständig in der Auswahl liegen.

Im Dialog gibt es zwei Schalter, die den Unterschied zwischen einem
brauchbaren und einem wertlosen Nachweis ausmachen:

* **Spannungssingularität**: An einspringenden Ecken, unter Einzellasten und
  an Punktlagern wächst die Spannung mit jeder Netzverfeinerung. Ein Nachweis
  gegen f_y ist dort ohne Aussage. Ist der Schalter gesetzt, werden die
  Spannungen berichtet, aber kein Nachweis geführt — der Status heißt „nur
  berichtet“. Statik3D weist von sich aus darauf hin, wenn die
  Spitzenspannung um mehr als den Faktor 5 über dem Mittel des Bereichs liegt.
* **Kerbradius**: Wird er angegeben, prüft das Programm, ob mindestens drei
  Elemente über den Radius liegen. Sonst sagt es, dass das Netz dort zu grob
  ist und die Kerbspannung unterschätzt wird.

Ausgewertet wird je Element an der Mitte **und** an den Eckpunkten; maßgebend
ist der größte Wert. Die Elementmitte allein würde die Randspannung bei
Biegung um rund ein Viertel unterschätzen.

Der Bericht führt je Bereich den vollen Spannungstensor, die Hauptspannungen,
τ_max, die hydrostatische Spannung, die Mehrachsigkeit h = σ_m/σ_v, σ_v und
die Ausnutzung auf, dazu den Vergleich nach Tresca. Bei **dreiachsigem Zug**
kommt der Hinweis, dass die Zähigkeit nach DIN EN 1993-1-10 zu beurteilen ist
— diesen Nachweis führt Statik3D nicht.

**Nicht enthalten**: Stabilität des Volumenkörpers. Das Verzweigungsproblem
ist nur für Stabtragwerke gebildet.

### Theorie II. Ordnung und Imperfektionen

Register *Nachweise* → „Einstellungen“. Unter **Theorie II. Ordnung** gibt es
drei Möglichkeiten:

* **aus** – es wird nur nach Theorie I. Ordnung gerechnet (Voreinstellung).
* **automatisch nach 5.2.1(3)** – Statik3D bestimmt für jede GZT-Kombination
  den Verzweigungslastfaktor α_cr und rechnet nur die Kombinationen am
  verformten System, bei denen α_cr unter der Grenze liegt (10 elastisch,
  15 plastisch). Das ist der empfohlene Weg: er kostet wenig und beantwortet
  die Frage, ob Theorie I. Ordnung überhaupt zulässig war.
* **ein** – alle GZT-Kombinationen werden am verformten System gerechnet.

Dazu die **Ersatzimperfektionen nach 5.3.2**: Schiefstellung φ und
Vorkrümmung e_0 werden als gleichwertige Lasten angesetzt, die Geometrie
bleibt unberührt. Wer die Vorkrümmung auch für gedrungene Stäbe ansetzen
will, schaltet „5.3.2(6) übergehen“ ein.

Der Bericht bekommt ein eigenes Kapitel: α_cr je Kombination mit dem
Kriterium, das gewählte Verfahren, die Zahl der Iterationen, der
Verformungszuwachs gegenüber Theorie I. Ordnung, dann φ mit α_h, α_m und der
Richtung, die Ersatzhorizontalkraft je Stiel und die Vorkrümmung je Stab mit
Knicklinie, e_0, q und V.

**Wichtig**: Nach Theorie II. Ordnung gilt keine Superposition mehr. Jede
Kombination wird einzeln gerechnet — das dauert länger als eine lineare
Überlagerung. Die Ergebnisse der einzelnen **Lastfälle** bleiben Ergebnisse
nach Theorie I. Ordnung und dürfen nicht mehr von Hand überlagert werden.

### Verformungsnachweise (GZG)

Die Kombinationen des Grenzzustands der Gebrauchstauglichkeit rechnet Statik3D
ohnehin; mit einer **Verformungsgrenze** werden sie gegen einen Grenzwert
gehalten. Anlegen über Register *Nachweise* → „Verformung“, über den
Modellbaum („+ Verformungsgrenze“) oder in der Tabelle „Verformungen“.

| Bezug | wofür |
|---|---|
| **Stab** | Durchbiegung w bezogen auf die Sehne zwischen den Stabenden |
| **Knoten** | Verschiebung oder Verdrehung gegenüber der Ausgangslage (Kragarmspitze, Stützenkopf) |
| **Punktpaar** | Verschiebung zweier Knoten gegeneinander — Dichtungen, Führungen, Fugen, Anschläge (DIN 19704) |

Der Grenzwert ist entweder **L/x** (L = Stablänge beziehungsweise Abstand der
beiden Knoten) oder ein **absoluter Wert** in mm beziehungsweise mrad. Dazu
gehören die Bemessungssituation (charakteristisch, häufig, quasi-ständig oder
alle GZG-Kombinationen) und wahlweise eine **Überhöhung w_c**, die abgezogen
wird (EN 1993-1-1, A.1.4.2).

Wichtig für den Kragarm: die Durchbiegung eines Stabes bezieht sich auf die
**Sehne** — dreht der ganze Stab mit, fällt das heraus. Für eine Kragarmspitze
ist der Bezug „Knoten“ der richtige.

Ergebnis: Tabelle „Verformungen“ mit Wert, Grenzwert, Ausnutzung,
maßgebender Kombination und Stelle; Kapitel 8 des Berichts führt jeden
Nachweis mit seiner Verformung je Kombination.

## 9 Berechnung und Parallelisierung

* **Alle Lastfälle + Kombinationen**: Standard. Eine Faktorisierung, alle
  Lastfälle, Superposition, Umhüllende, optional Nachweise.
* **Nur aktiver Lastfall**, **Eigenschwingungen**, **Knicken** (Grundzustand
  = aktiver Lastfall).
* Prozesse: Anzahl der Kerne; Backend „Rechnerfarm“ mit Server, Port und
  Schlüssel (siehe `Rechnerfarm.md`). „Lokalen Server + Worker starten“
  macht den eigenen Rechner zum Farm-Server.
* Die Berechnung läuft im Hintergrund; Fortschritt im Protokoll.

## 10 Ergebnisse und Bericht

* Färbung: |u|, ux/uy/uz, Vergleichsspannung (Schalen/Volumen, Randspannung
  bei Stäben), Ausnutzung EC3 / Ermüdung / elastisch.
* Schnittgrößenverläufe N, Vy, Vz, Mt, My, Mz an den Stäben (bei Umhüllenden
  der betragsmäßig größere Extremwert).
* Tabellen: Stabkräfte, Auflagerkräfte, Umhüllende, Nachweise, Ermüdung,
  Kontakt, Anschlüsse — filterbar, sortierbar, mit Max-/Min-Zeile, ausgebbar nach
  Zwischenablage, CSV und Excel (Kapitel 2, „Tabellen"). Modellexport
  außerdem CSV, VTK (ParaView).
* Statischer Bericht: Projektdaten, System, Einwirkungen, Kombinationen,
  Ergebnisse, Nachweise mit allen Zwischenwerten, Beulen (EC3-1-5), Ermüdung,
  Anschlüsse (jede Schraube, jede Naht), Verformungen (GZG), Kontakt,
  Zusammenfassung – HTML (Browser: Drucken → PDF), PDF (reportlab) oder
  Markdown.

## 11 Tastenkürzel

Strg+N neu, Strg+O öffnen, Strg+S speichern, Strg+I importieren,
Strg+R Bericht, F5 berechnen, Strg+Z rückgängig, Strg+Y wiederholen,
Strg+Umschalt+C vordere Tabelle kopieren.

Ansicht: Strg+1 voll, Strg+2 transparent, Strg+3 Hidden-Line,
Strg+4 Drahtmodell, F9 FE-Netz ein/aus.
Strg+B übernimmt die Ansicht in den Bericht.
Fang: F3 ein/aus, Umschalt+F1 Knoten, Umschalt+F2 Kantenmitte,
Umschalt+F3 Raster.

Browser/Handy: siehe Kapitel 12.

## 12 Bedienung im Browser und auf dem Handy

Statik3D lässt sich ohne Installation auf dem Handy oder Tablet bedienen: Der
Rechenkern läuft als kleiner Web-Server auf dem PC (oder einem Server im
Netz), das Handy zeigt die Oberfläche im Browser. Modell, Berechnung,
Ergebnisse, Nachweise und Bericht sind dieselben wie in der Desktop-GUI.

### 12.1 Starten

```bash
python run_web.py --schluessel geheim              # oder: python -m statik3d.web
python run_web.py --beispiel hall --port 8080
python run_web.py --modell halle.json --kerne 8
```

Der Server meldet zwei Adressen:

```
Statik3D - Bedienung im Browser / auf dem Handy
  Auf diesem Rechner : http://127.0.0.1:8080/
  Im Netzwerk (Handy): http://192.168.1.23:8080/
  Schlüssel          : geheim   (im Browser einmalig eingeben)
```

Auf dem Handy (gleiches WLAN) die Netzwerk-Adresse im Browser öffnen und den
Schlüssel eingeben; er wird auf dem Gerät gespeichert. Mit `pip install qrcode`
druckt der Server zusätzlich einen QR-Code, den das Handy direkt scannt.
Browser-Menü → **Zum Startbildschirm hinzufügen** legt ein App-Symbol an;
Statik3D startet dann bildschirmfüllend wie eine App.

Aus der Desktop-GUI: **Berechnung → Bedienung im Browser / auf dem Handy…**
startet den Server für das geöffnete Modell. Handy und PC arbeiten dann am
selben Modell: Eingaben vom Handy erscheinen in der GUI, Ergebnisse vom PC
auf dem Handy.

| Option | Bedeutung |
|---|---|
| `--port 8080` | Port des Servers |
| `--host 0.0.0.0` | im ganzen Netz erreichbar; `127.0.0.1` = nur dieser Rechner |
| `--schluessel …` | Zugangsschlüssel (empfohlen, sobald der Server im Netz erreichbar ist) |
| `--modell datei` | Modell (.json) oder Importdatei beim Start laden |
| `--beispiel hall` | eingebautes Beispiel laden |
| `--kerne 8` | Anzahl Prozesse für die Berechnung |
| `--laut` | jede Anfrage im Terminal protokollieren |

Unter Windows: PowerShell im Programmordner, `.venv\Scripts\activate`,
`python run_web.py --schluessel geheim`. Beim ersten Start fragt die
Windows-Firewall, ob Python im privaten Netz Verbindungen annehmen darf –
zulassen, sonst erreicht das Handy den PC nicht.

### 12.2 Die Oberfläche

Oben die 3D-Ansicht, unten die Register. Der Bereich dazwischen lässt sich am
Griff ziehen (klein / halb / groß); auf Tablets und PCs liegen die Register
links neben der Ansicht. Ab 1100 px Fensterbreite schaltet die Oberfläche in
die **Werkbank**: links der Modellbaum (Elemente nach Art, Querschnitte,
Werkstoffe, Lager, Lastfälle, Kombinationen, Kontakt, Stellungen, Stäbe für
Nachweise), in der Mitte die Ansicht mit dem Filmstreifen der Stellungen
darunter, rechts die Register als Arbeitsblatt.

| Register | Inhalt |
|---|---|
| **Modell** | Projektdaten, Materialien, Querschnitte (Profildatenbank und parametrisch), Schalendicken, Netzgeneratoren (Stabzug, Platte, Quader), Knoten, Elemente (Stab, Schale, Zuweisen, Gelenke, Löschen), Lager, Stäbe mit Nachweisparametern, Kontakt, Nachweiseinstellungen |
| **Lasten** | Lastfälle mit Einwirkungskategorie, Lasten des aktiven Lastfalls (Knoten-, Strecken-, Flächen-, Temperaturlast, Eigengewicht), Kombinationen (automatisch/manuell), Ermüdungslasten |
| **Rechnen** | Analyseart, Nachweise, Prozesse, Rechnerfarm, Start; Fortschritt und Zusammenfassung |
| **Ergebnisse** | Ergebnis (Umhüllende / Kombination / Lastfall / Eigenform), Färbung, Überhöhung, Schnittgrößenverlauf, Stabdiagramm N/Vz/My, Tabellen Stabkräfte, Umhüllende, Auflagerkräfte, Kontakt |
| **Nachweise** | Nachweise EC3 und Ermüdung starten, Tabellen; Zeile antippen zeigt alle Zwischenwerte |
| **Stellungen** | Stellungen beweglicher Brücken anlegen und rechnen, Umhüllende, Kurve η über den Stellungswinkel, DIN-19704-Beiwerte, ZTV-ING-Prüfliste (siehe „Bewegliche Brücken“) |
| **Mehr** | Datei öffnen/importieren (alle Formate aus Kap. 6), Modell speichern, **Export in dreizehn Formate** (herunterladen), Bericht (HTML/PDF/Markdown), Modellprüfung, Beispiele, Ansicht, Protokoll, Zugangsschlüssel |

3D-Ansicht: Ziehen dreht, zwei Finger zoomen und verschieben, Doppeltipp
zeigt alles, die Knöpfe oben schalten Ansichten (3D, XY, XZ, YZ) und
Nummern. **Antippen wählt Knoten** (Umschalter „Kn/El“ für Elemente); die
Auswahl wird in die Eingabefelder der Register übernommen (Lager, Lasten,
Zuweisen, Stäbe, Kontakt). Ergebnisse werden verformt und farbig gezeichnet,
Schnittgrößen als Verläufe am Stab.

### 12.3 Sicherheit

Der Server spricht unverschlüsseltes HTTP und ist für das eigene Netz (WLAN,
Firmennetz) gedacht. Immer einen Schlüssel setzen, sobald `--host 0.0.0.0`
verwendet wird. Für den Zugriff über das Internet ein VPN oder einen
Reverse-Proxy mit HTTPS vorschalten; den Port nicht direkt am Router
freigeben. Hochgeladene Dateien landen in einem temporären Ordner des
Servers.

### 12.4 Grenzen

Die Darstellung zeichnet mit dem Canvas des Browsers; sehr große
Volumenmodelle (mehr als etwa 50 000 Außenflächen) werden auf älteren Handys
träge. Ordner-Importe (RFEM-CSV-Ordner) gehen nur über die Desktop-GUI oder
die Kommandozeile. Der PDF-Bericht benötigt `reportlab` auf dem Server; der
HTML-Bericht lässt sich am Handy über Teilen → Drucken als PDF sichern.

## 13 Grenzen

Kleine Verformungen, linear-elastisches Material, Kontakt als
Penalty-Näherung ohne Lastgeschichte (Reibung nahe der Reibkapazität
konservativ, siehe Theoriehandbuch Kap. 4), keine Schalenbeulnachweise, keine
Plastizität, keine Zeitbereichsdynamik. Das Programm ist verifiziert
(Testsuiten im Ordner `tests`), aber nicht bauaufsichtlich zugelassen; die
Verantwortung für die Nachweise liegt beim Anwender.

## Bewegliche Brücken und Stahlwasserbauten

Eine Klappbrücke, eine Drehbrücke oder ein Hubtor ist in jeder Stellung ein
**anderes Tragwerk**: Lager greifen oder nicht, Riegel sind gezogen, das
Eigengewicht wirkt unter einem anderen Winkel, der Antrieb hält ein anderes
Moment. Deshalb wird jede Stellung als eigener Rechenlauf geführt und am Ende
die Umhüllende über alle Stellungen gebildet — mit der Angabe, **welche
Stellung für welchen Nachweis maßgebend ist**.

### Stellungen anlegen

```python
from statik3d.bridges import Stellung, Stellungsreihe

reihe = Stellungsreihe(modell, "Klappbrücke Hafenkanal")
reihe.add(Stellung("S1", 0.0, "geschlossen"))
for w in (20, 45, 70, 82):
    reihe.add(Stellung(f"S{w}", w, f"geöffnet {w}°",
                       lager_aus=["Endauflager"],          # Riegel gezogen
                       dreh_achse=(0, 1, 0), dreh_punkt=(0, 0, 0),
                       dreh_winkel=-w, dreh_gruppen=["klappe"],
                       antrieb=(knoten_drehachse, (0, 250e3, 0))))
umh = reihe.rechnen(nachweise=True)
print(umh.bericht())
```

Je Stellung lässt sich einstellen:

| Angabe | Wirkung |
|---|---|
| `lager_aktiv` / `lager_aus` | welche benannten Lager in dieser Stellung greifen |
| `dreh_achse`, `dreh_punkt`, `dreh_winkel`, `dreh_gruppen` | die bewegten Bauteile werden gedreht; das Eigengewicht wirkt dadurch anders |
| `faelle`, `kombinationen` | welche Lastfälle in dieser Stellung überhaupt gelten |
| `antrieb` | Antriebsmoment als Knotenlast in einem eigenen Lastfall |

Die Umhüllende nennt die größte Ausnutzung, die größte Verformung und die
größte Auflagerkraft je Knoten — **jeweils mit der Stellung, in der sie
auftritt**. `umh.kurve()` liefert `(Winkel, η, u_max)` für die Kurve über den
Stellungswinkel. Eine Stellung ohne ausreichende Lagerung wird als Fehler
ausgewiesen, nicht stillschweigend übergangen.

### Lastfallklassen nach DIN 19704

```python
from statik3d.bridges import Regelwerk
rw = Regelwerk()
rw.faktor("LF1", "G", 1.35, "DIN 19704-1, geprüft")   # eigenen Wert bestätigen
kombis = rw.kombinationen(modell)                     # DIN LF1.1, DIN LF2.3, …
print(rw.bericht())
```

| Klasse | Bedeutung |
|---|---|
| LF1 | Normalfall — regelmäßiger Betrieb |
| LF2 | Sonderfall — seltene, planmäßig mögliche Zustände |
| LF3 | außergewöhnlicher Fall — Bau-, Revisions- und Störfall |

Die Einwirkungen des Stahlwasserbaus sind als Einwirkungskategorien verfügbar:
`G_A` (Ausrüstung und Antrieb), `W_S`/`W_V` (Wasserdruck ständig/veränderlich),
`Q_BEW` (Betriebslast beim Bewegen), `A_M`/`A_MG` (Antriebsmoment planmäßig /
Grenzmoment der Rutschkupplung), `WIND_B` (Wind während der Bewegung), `EIS`,
`SCHWALL`, `ANPRALL`, `KLEMM` (Verklemmen), `MONT`, `ERD`.

> **Wichtig — die Zahlenwerte sind zu bestätigen.** Statik3D bildet das
> *Verfahren* ab: die Einteilung der Einwirkungen, die drei Lastfallklassen und
> die Kombinationsbildung daraus. Die *Beiwerte* γ_F, γ_M und ψ₀ sind als
> **Voreinstellung** mitgeliefert und ausdrücklich gegen die geltende Fassung
> der Norm zu prüfen. `rw.offen()` nennt jeden noch nicht bestätigten Wert,
> `rw.bericht()` schreibt die Tabelle mit Herkunft, und das Importprotokoll
> weist darauf hin. Ein Programm, das Beiwerte aus dem Gedächtnis behauptet,
> wäre schlimmer als eines, das die Tabelle offen zur Bestätigung vorlegt.

### Stellungen im Programmfenster

Im Register **⟳ Stellungen** stehen alle Stellungen in einer Tabelle mit Winkel,
ausgefallenen Lagern, geltenden Lastfällen, η und größter Verformung.
„+ Stellung" öffnet den Dialog (Name, Winkel, Lager, Lastfälle, Drehung des
bewegten Bauteils, Antriebsmoment), „Ändern" und „Entfernen" arbeiten auf der
gewählten Zeile. **▶ Alle Stellungen rechnen** rechnet jede Stellung einzeln
und schreibt die Umhüllende darunter; der Filmstreifen unter der 3D-Ansicht
zeigt danach je Karte das η, die maßgebende mit ★.

„Kombinationen nach DIN 19704 bilden" legt die Kombinationen der drei
Lastfallklassen an und schreibt darunter **jeden Beiwert mit seinem Zustand**
(„bestätigt" oder „zu bestätigen") und die ZTV-ING-Prüfliste.

### Stellungen im Browser: Register „Stellungen“

Alles davon gibt es auch ohne Python, im Browser (`python run_web.py`,
Kapitel 12). Das Register **⟳ Stellungen** führt den ganzen Ablauf:

1. **+ Stellung** legt eine Stellung an: Name, Stellungswinkel, welche Lager
   ausfallen, welche Lastfälle gelten, um welchen Winkel welche Gruppe gedreht
   wird und an welchem Knoten das Antriebsmoment angreift. Ein zweites Anlegen
   unter demselben Namen **ändert** die Stellung, statt sie zu verdoppeln; die
   Liste bleibt nach Winkel sortiert.
2. **▶ Alle Stellungen rechnen** rechnet jede Stellung einzeln und bildet die
   Umhüllende. Jede Karte zeigt danach ihr η, die maßgebende Stellung ist
   hervorgehoben, und die Kurve **η über den Stellungswinkel** steht darunter.
   Eine Stellung, die nicht rechenbar ist — etwa weil ein genannter Lastfall
   im Modell fehlt —, wird mit ihrer Fehlermeldung ausgewiesen; die übrigen
   Stellungen werden trotzdem gerechnet.
3. **DIN 19704: Kombinationen bilden** legt die Kombinationen der drei
   Lastfallklassen an und zeigt darunter **jeden Beiwert mit seinem Zustand**:
   „zu bestätigen“ oder „bestätigt“. Ein Beiwert lässt sich im selben Register
   setzen; damit gilt er als bestätigt und verschwindet aus der Liste der
   offenen Werte.
4. Die **ZTV-ING-Prüfliste** steht darunter — mit Haken nur bei dem, was das
   Programm wirklich sehen kann.

Am breiten Bildschirm (ab 1100 px) schaltet die Oberfläche in die
**Werkbank**: links der Modellbaum, in der Mitte die 3D-Ansicht mit dem
Filmstreifen der Stellungen darunter, rechts die Register. Der Filmstreifen
zeigt jede Stellung als Karte mit Winkel und Ausnutzung; ein Klick wählt sie
aus. Am Handy bleibt es beim gewohnten Aufbau mit dem Bereich von unten.

### ZTV-ING-Prüfliste

```python
from statik3d.bridges import pruefliste, bewegungen
for thema, erfuellt, hinweis in pruefliste(reihe, modell):
    print("OK " if erfuellt else "OFFEN", thema, hinweis)
print("Lastwechsel:", bewegungen(4 * 365, 100))   # 4 Bewegungen/Tag, 100 Jahre
```

Geprüft wird, ob Zwischenstellungen untersucht sind, ob ein Antriebsmoment
angesetzt ist (und ob auch das Grenzmoment der Rutschkupplung als LF3
vorliegt), ob Wind während der Bewegung und das Verklemmen eines
Antriebsstrangs als Einwirkung geführt werden und ob die Lagerzustände je
Stellung unterschieden sind. Was das Programm nicht selbst sehen kann — etwa
die Zahl der Bewegungen über die Nutzungsdauer — wird als **offen** ausgewiesen
und nicht als erfüllt behauptet.
