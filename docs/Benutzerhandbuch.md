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
| **Lager / Kontakt** | Knoten-, Linien-, Flächenlager, Nichtlinearität, Kontakt, Anschlüsse |
| **Lasten** | Lastfälle, Kombinationen, Knoten-, Stab-, Flächen-, Temperaturlast, Eigengewicht |
| **Netz** | Netz erzeugen und löschen |
| **Berechnung** | Berechnen (F5), einzelner Lastfall, Eigenschwingungen, Knicken, alle Stellungen, DIN 19704, Einstellungen, Bedienung im Browser |
| **Nachweise** | EC3, Ermüdung, Konfiguration |
| **Ergebnisse** | Ergebniswahl und die Tabellen |
| **Bericht** | Statischer Bericht |
| **Ansicht** | Blickrichtungen, Kanten, Nummern, Lasten, Stäbe farbig |
| **Extras** | Handbücher, Info, Update |

Links über dem Ribbon die **Schnellzugriffsleiste** (Speichern, Berechnen,
Auswahl aufheben) — dieselben Befehle, nur schneller erreichbar. Rechts die
**Befehlssuche**: Namen eintippen, Eingabetaste, der Befehl läuft und sein
Register kommt nach vorn.

Die Arbeitsfläche in drei Spalten:

* **links der Modellbaum** — Elemente nach Art, Querschnitte, Werkstoffe,
  Lager, Lastfälle, Kombinationen, Kontakt, Stellungen und die Stäbe für die
  Nachweise, jeweils mit Anzahl. Ein Klick führt zur Eingabe oder zur Tabelle.
  Die **Stellungen stehen nur hier**, mit „+ Stellung anlegen" am Ende des
  Zweiges; die maßgebende trägt ★.
* **in der Mitte die 3D-Ansicht** — frei für die Grafik.
* **rechts die Eingabemaske** — es ist immer genau **eine** sichtbar, gewählt
  über den Befehl im Ribbon; der Titel der Maske nennt sie. Eine Registerleiste
  mit denselben Namen wie im Ribbon gibt es nicht mehr.

Unten die **Tabellen**: Protokoll, Werkstoffe, Querschnitte, Dicken,
Stabkräfte, Auflagerkräfte, Umhüllende, Nachweise EC3, Ermüdung, Kontakt.
Werkstoffe, Querschnitte und Dicken werden hier gepflegt — nicht mehr zusätzlich
in einem Panel rechts.

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
| `.step`/`.iges`/`.stl` | CAD | Vernetzung mit gmsh (Volumen oder Schale) |

Native Binärformate (`.rf5`, `.rf6`, `.fem`) können nicht gelesen werden;
Aus HiCAD übernommene Stäbe enden an der **Außenkante** des angeschlossenen
Bauteils – ihre Achsen laufen um die halbe Profilhöhe daneben vorbei, das Modell
zerfällt zunächst in Teile. Im Register **Mehr → Aus CAD übernommenes Modell**
schließt „Freie Stabenden anschließen" (Suchradius 60 mm) jedes freie Ende an die
Achse des nächsten Stabes an und teilt diesen dort; der Versatz steht im
Protokoll, die Ausmitte des Anschlusses wird nicht abgebildet.

das Programm nennt den Exportweg (RFEM: IFC-Statikmodell, SAF oder
Tabellen; InfoCAD: IFC-Statikmodell oder DXF).

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
  Kontakt. Export CSV, VTK (ParaView).
* Statischer Bericht: Projektdaten, System, Einwirkungen, Kombinationen,
  Ergebnisse, Nachweise mit allen Zwischenwerten, Ermüdung, Kontakt,
  Zusammenfassung – HTML (Browser: Drucken → PDF), PDF (reportlab) oder
  Markdown.

## 11 Tastenkürzel

Strg+N neu, Strg+O öffnen, Strg+S speichern, Strg+I importieren,
Strg+R Bericht, F5 berechnen.

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
