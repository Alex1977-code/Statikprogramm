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
startet sie den Browser-Server (Kap. 11), mit `offline` ohne Aktualisierung.
Eigene Modelle gehören in den Ordner `Projekte` daneben.

Einheiten im Programm: **m, N, Pa, kg/m³**. Eingabefelder mit anderer Einheit
sind beschriftet (z. B. E-Modul in GPa, fy in MPa). Ergebnisse werden in kN,
kNm, MPa und mm angezeigt.

## 2 Die Oberfläche

Links die Eingabe-Registerkarten, in der Mitte der 3D-Viewport, unten das
Protokoll und die Ergebnistabellen.

| Register | Inhalt |
|---|---|
| **Modell** | Projektdaten (für den Bericht), Materialien (Stahlsorten S235–S460 mit fy/fu), Querschnitte aus der Profildatenbank (IPE, HEA, HEB, HEM, SHS, RHS, CHS) oder parametrisch, Schalendicken, Querschnitt/Material zuweisen, Gelenke setzen |
| **Netz** | Stabzüge, Platten, Quader erzeugen; Import (siehe Kap. 6); doppelte Knoten zusammenführen |
| **Lager/Lasten** | Knoten auswählen (Klick im Viewport, Koordinatenfenster, Nummern); Lager (starr, Feder, Einspannung, gelenkig); Knoten-, Strecken- (auch trapezförmig, lokal/global), Flächen-, Temperaturlasten und Eigengewicht **in den aktiven Lastfall** |
| **Lastfälle** | Lastfälle mit Einwirkungskategorie (ψ-Werte), Ausschlussgruppen, Kombinationen automatisch (DIN EN 1990) oder manuell, Ermüdungslasten |
| **Kontakt** | Einseitige Lager, Spaltelemente, Kontaktpaare Knoten–Fläche mit Reibung |
| **Nachweise** | Stäbe (Knicklängen, seitliche Halterung, Kerbfall …), Einstellungen γM, Nachweise starten |
| **Berechnung** | Analyseart, Parallelisierung (Kerne, Rechnerfarm), BERECHNEN (F5) |
| **Ergebnisse** | Ergebnis (Lastfall / Kombination / Umhüllende) wählen, Färbung, Schnittgrößenverläufe, Überhöhung, Export, Bericht |

Der Viewport: linke Maustaste dreht, rechte zoomt, mittlere verschiebt.
**Klick auf einen Knoten** wählt ihn aus (nochmals klicken hebt die Auswahl
auf). Ansicht → Knotennummern / Elementnummern blendet Beschriftungen ein.

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

## 5 Kontakt

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

## 6 Import

Datei → Importieren (Details in `Schnittstellen.md`):

| Format | Herkunft | Inhalt |
|---|---|---|
| `.json` | Statik3D | vollständiges Modell |
| `.dxf` | CAD, InfoCAD, RFEM | Linien → Stäbe, 3DFACE → Schalen, Layer → Gruppen |
| `.ifc` | InfoCAD, RFEM, Allplan … (IFC Structural Analysis View) | Knoten, Stäbe, Flächen, Profile, Lager, Lasten, Lastfälle |
| `.xlsx` SAF | RFEM 6, SCIA, Allplan, AxisVM | Structural Analysis Format |
| `.xlsx`/`.csv` | RFEM 5/6, RSTAB Tabellenexport | Knoten, Linien, Stäbe, Querschnitte, Lager, Lastfälle, Lasten |
| `.inp` | Abaqus, CalculiX | Netz, Materialien, Sections, Randbedingungen, Lasten je Step |
| `.bdf`/`.nas`/`.dat` | Nastran | GRID, CBAR/CBEAM, CQUAD4/CTRIA3, CTETRA/CHEXA, SPC, FORCE, PLOAD |
| `.step`/`.iges`/`.stl` | CAD | Vernetzung mit gmsh (Volumen oder Schale) |

Native Binärformate (`.rf5`, `.rf6`, `.fem`) können nicht gelesen werden;
das Programm nennt den Exportweg (RFEM: IFC-Statikmodell, SAF oder
Tabellen; InfoCAD: IFC-Statikmodell oder DXF).

## 7 Nachweise nach EC3

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

## 8 Berechnung und Parallelisierung

* **Alle Lastfälle + Kombinationen**: Standard. Eine Faktorisierung, alle
  Lastfälle, Superposition, Umhüllende, optional Nachweise.
* **Nur aktiver Lastfall**, **Eigenschwingungen**, **Knicken** (Grundzustand
  = aktiver Lastfall).
* Prozesse: Anzahl der Kerne; Backend „Rechnerfarm“ mit Server, Port und
  Schlüssel (siehe `Rechnerfarm.md`). „Lokalen Server + Worker starten“
  macht den eigenen Rechner zum Farm-Server.
* Die Berechnung läuft im Hintergrund; Fortschritt im Protokoll.

## 9 Ergebnisse und Bericht

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

## 10 Tastenkürzel

Strg+N neu, Strg+O öffnen, Strg+S speichern, Strg+I importieren,
Strg+R Bericht, F5 berechnen.

Browser/Handy: siehe Kapitel 11.

## 11 Bedienung im Browser und auf dem Handy

Statik3D lässt sich ohne Installation auf dem Handy oder Tablet bedienen: Der
Rechenkern läuft als kleiner Web-Server auf dem PC (oder einem Server im
Netz), das Handy zeigt die Oberfläche im Browser. Modell, Berechnung,
Ergebnisse, Nachweise und Bericht sind dieselben wie in der Desktop-GUI.

### 11.1 Starten

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

### 11.2 Die Arbeitsfläche

Am PC gliedert sich die Oberfläche in vier Bereiche:

* **Werkzeugleiste** oben mit den Bereichen und dem Knopf **Berechnen** (F5),
* **Modellbaum** links: Bauteile, Stellungen, Lastfälle und Stäbe. Ein Klick
  wählt den Eintrag – bei einer Stellung folgen Ansicht, Lagerung und Lasten,
  bei einem Stab wechselt das Kontextpanel rechts,
* **3D-Ansicht** in der Mitte, darunter bei beweglichen Systemen die
  **Stellungsleiste** und die **Register**,
* **Kontextpanel** rechts mit dem gewählten Stab: Querschnitt und
  Nachweisparameter, die Ausnutzung je Einzelnachweis als Balken und – wenn
  Stellungen gerechnet wurden – die Kurve η über die Stellungen.

Die Höhe der Register lässt sich am Griff ziehen, Doppelklick klappt sie ein
und aus. Unter 1100 px Fensterbreite (Handy, schmales Fenster) rücken die
Register nach unten und die Bedienung wird gestapelt; Modellbaum und Auswahl
lassen sich dann über die Knöpfe **Baum** und **Auswahl** einblenden.

| Register | Inhalt |
|---|---|
| **Modell** | Projektdaten, Materialien, Querschnitte (Profildatenbank und parametrisch), Schalendicken, Netzgeneratoren (Stabzug, Platte, Quader), Knoten, Elemente (Stab, Schale, Zuweisen, Gelenke, Löschen), Lager, Stäbe mit Nachweisparametern, Kontakt, Nachweiseinstellungen |
| **Lasten** | Lastfälle mit Einwirkungskategorie, Lasten des aktiven Lastfalls (Knoten-, Strecken-, Flächen-, Temperaturlast, Eigengewicht), Kombinationen (automatisch/manuell), Ermüdungslasten |
| **Stellungen** | Stellungen des Systems für bewegliche Brücken (Kap. 12) |
| **Rechnen** | Analyseart, Nachweise, Prozesse, Rechnerfarm, Start; Fortschritt und Zusammenfassung |
| **Ergebnisse** | Ergebnis (Umhüllende / Kombination / Lastfall / Eigenform), Färbung, Überhöhung, Schnittgrößenverlauf, Stabdiagramm N/Vz/My, Tabellen Stabkräfte, Umhüllende, Auflagerkräfte, Kontakt |
| **Nachweise** | Nachweise EC3 und Ermüdung starten, Tabellen; Zeile anklicken zeigt alle Zwischenwerte. Bei beweglichen Systemen zusätzlich die Umhüllende über die Stellungen |
| **Mehr** | Datei öffnen/importieren (alle Formate aus Kap. 6), Modell speichern, Bericht (HTML/PDF/Markdown), Modellprüfung, Beispiele, Ansicht, Protokoll, Zugangsschlüssel |

3D-Ansicht: Ziehen dreht, Mausrad zoomt, die rechte oder mittlere Taste
schiebt, Doppelklick zeigt alles; am Touchgerät drehen ein Finger und zoomen
zwei Finger. Die Knöpfe oben schalten Ansichten (3D, XY, XZ, YZ) und Nummern.
**Klicken wählt Knoten** (Umschalter „Kn/El“ für Elemente); die Auswahl wird
in die Eingabefelder der Register übernommen (Lager, Lasten, Zuweisen, Stäbe,
Kontakt) und stellt rechts den zugehörigen Stab ein. Ergebnisse werden
verformt und farbig gezeichnet, Schnittgrößen als Verläufe am Stab.

### 11.3 Sicherheit

Der Server spricht unverschlüsseltes HTTP und ist für das eigene Netz (WLAN,
Firmennetz) gedacht. Immer einen Schlüssel setzen, sobald `--host 0.0.0.0`
verwendet wird. Für den Zugriff über das Internet ein VPN oder einen
Reverse-Proxy mit HTTPS vorschalten; den Port nicht direkt am Router
freigeben. Hochgeladene Dateien landen in einem temporären Ordner des
Servers.

### 11.4 Grenzen

Die Darstellung zeichnet mit dem Canvas des Browsers; sehr große
Volumenmodelle (mehr als etwa 50 000 Außenflächen) werden auf älteren Handys
träge. Ordner-Importe (RFEM-CSV-Ordner) gehen nur über die Desktop-GUI oder
die Kommandozeile. Der PDF-Bericht benötigt `reportlab` auf dem Server; der
HTML-Bericht lässt sich am Handy über Teilen → Drucken als PDF sichern.

## 12 Stellungen des Systems (bewegliche Brücken)

Eine bewegliche Brücke – Klapp-, Dreh-, Hub- oder Faltbrücke – ist statisch
nicht **ein** System, sondern eine Schar von Systemen. In jeder Stellung steht
das bewegte Bauteil anders, ist anders gelagert und trägt andere Lasten:
in der Verkehrsstellung tragen Endauflager und Riegel mit und es wirkt
Verkehrslast, geöffnet hängt die Klappe im Drehlager, wird vom Antrieb
gehalten und der Wind greift an der aufgestellten Fläche an. Maßgebend für
die Bemessung ist die **Umhüllende über alle Stellungen** – und welche
Stellung maßgebend wird, lässt sich vorher nicht sagen.

### 12.1 Eine Stellung beschreiben

Jede Stellung besteht aus:

| Angabe | Bedeutung |
|---|---|
| **Bewegung** | Drehung um eine Achse (Klapp-, Dreh-, Faltbrücke) oder Verschiebung längs einer Richtung (Hub-, Schiebebrücke) |
| **Winkel / Weg** | Drehwinkel in Grad bzw. Verschiebung in Meter, jeweils gegenüber der Ausgangsgeometrie |
| **Drehachse** | Punkt und Richtung; die Drehung folgt der Rechtsschraube um die Achsrichtung |
| **Bewegtes Bauteil** | Elementgruppen (und zusätzlich einzelne Knoten), die sich mitbewegen |
| **Lager der Stellung** | Lager, die nur in dieser Stellung wirken – wahlweise zusätzlich zu den Lagern des Modells oder an deren Stelle |
| **Wirkende Lastfälle** | Auswahl der Lastfälle; Kombinationen mit einem nicht wirkenden Lastfall entfallen in dieser Stellung |

Die Bewegung ist eine reine Starrkörperlage der Ausgangsgeometrie. Die
Querschnittslage der mitbewegten Stäbe wird mitgedreht – der Steg eines
aufgestellten Trägers bleibt also im Bauteil und richtet sich nicht neu nach
der globalen z-Achse aus.

### 12.2 Vorgehen

1. Modell in der Ausgangslage (meist geschlossen) aufbauen und dem bewegten
   Teil eine eigene **Elementgruppe** geben.
2. Register **Stellungen**: erste Stellung anlegen, Drehachse und bewegtes
   Bauteil eintragen. Für den Öffnungsvorgang legt **Stellungsserie** in einem
   Schritt gleichmäßig verteilte Stellungen an (z. B. 0° bis 82° in sechs
   Schritten); Achse, Bauteil, Lager und Lastfälle kommen aus der aktiven
   Stellung.
3. Je Stellung die abweichende Lagerung setzen und die wirkenden Lastfälle
   ankreuzen.
4. **Alle Stellungen rechnen.** Jede Stellung wird als eigenes System gelöst
   und nachgewiesen, danach werden die Nachweise umhüllt.

### 12.3 Ergebnisse

Die Stellungsleiste unter der Ansicht zeigt je Stellung die größte
Ausnutzung; ein Klick stellt die Ansicht auf diese Stellung um. Das
Kontextpanel rechts zeigt für den gewählten Stab die maßgebende Stellung und
die Kurve η über die Stellungen. Das Register **Stellungen** enthält die
Umhüllende: je Stab die maßgebende Stellung, den maßgebenden Nachweis, die
Kombination und die Stelle. Im Bericht steht dazu ein eigenes Kapitel mit der
Übersicht der Stellungen, der Ausnutzung je Stellung, der Umhüllenden, der
Matrix Stab × Stellung und einer Systemdarstellung jeder Stellung.

Das Beispiel **Klappbrücke mit Stellungen** (Register *Mehr* → Beispiele)
zeigt den Ablauf an einer Klappbrücke mit fünf Stellungen von 0° bis 82°.
Dort ist nicht die offene Endlage maßgebend, sondern die Stellung kurz nach
dem Entriegeln – genau der Grund, warum alle Stellungen zu rechnen sind.

### 12.4 Grenzen

Die Stellungen werden in der **Browser-Oberfläche** (Kap. 11), im Bericht und
über die Python-API bedient. Die PySide6-Desktop-GUI kennt sie noch nicht:
Sie zeigt und rechnet ein Modell mit Stellungen in dessen Ausgangslage, ohne
die Stellungen zu berücksichtigen.

Gerechnet werden die definierten Stellungen, nicht der Bewegungsvorgang: die
Berechnung ist je Stellung statisch und geometrisch linear, Massenkräfte aus
dem Anfahren und Abbremsen sind gegebenenfalls als eigene Lastfälle
anzusetzen. Beim Ermüdungsnachweis werden die Lastwechsel je Stellung aus den
Ermüdungslasten des Modells gebildet; ein Lastspiel, das über zwei Stellungen
läuft (Spannungswechsel geschlossen → offen), entsteht dabei nicht von
selbst, sondern ist als Lastfallpaar innerhalb einer Stellung anzulegen.

## 13 Grenzen

Kleine Verformungen, linear-elastisches Material, Kontakt als
Penalty-Näherung ohne Lastgeschichte (Reibung nahe der Reibkapazität
konservativ, siehe Theoriehandbuch Kap. 4), keine Schalenbeulnachweise, keine
Plastizität, keine Zeitbereichsdynamik. Das Programm ist verifiziert
(Testsuiten im Ordner `tests`), aber nicht bauaufsichtlich zugelassen; die
Verantwortung für die Nachweise liegt beim Anwender.
